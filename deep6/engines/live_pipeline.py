"""LiveSignalPipeline — run the full 44-signal stack on a closed FootprintBar.

Mirrors ``deep6.backtest.session.ReplaySession._run_full_pipeline`` but packaged
for the live bar-close hook. One instance is constructed at startup in
``scripts/run_live.py`` (or ``deep6.__main__``) and assigned into
``state._on_bar_close_fn`` via a thin async closure.

Responsibilities per bar (fired by BarBuilder → SharedState.on_bar_close):
    1. Run the narrative cascade (classify_bar) and per-category engines
       (delta / auction / poc / trap / volpat) for the timeframe.
    2. Update the timeframe's volume profile and compute its active zones.
    3. Call score_bar() with all resulting signals → ScorerResult.
    4. Return the ScorerResult to the caller (which then hands it to the
       LiveBridge for WS fan-out).

Design:
  - Per-timeframe state (one copy per label) is isolated so 1m and 5m
    histories never cross.
  - Failures in any single engine are logged and degraded to empty / default
    outputs; the bar-close path MUST NOT raise.
  - VPIN is already advanced by SharedState.on_bar_close on the 1m path, so
    we read state.vpin.get_confidence_modifier() rather than double-feeding.
    5m falls back to modifier=1.0 (matches ReplaySession behaviour where 5m
    VPIN is deferred).
  - D-03 (aggressor), D-06 (RTH) and D-17 (FreezeGuard) gates all live
    upstream in BarBuilder / tick_feed; by the time we're called the bar has
    already passed them.
"""
from __future__ import annotations

from typing import Any

import structlog

from deep6.engines.auction import AuctionEngine
from deep6.engines.delta import DeltaEngine
from deep6.engines.narrative import (
    NarrativeResult,
    NarrativeType,
    classify_bar,
)
from deep6.engines.poc import POCEngine
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig
from deep6.engines.trap import TrapEngine
from deep6.engines.vol_patterns import VolPatternEngine
from deep6.engines.volume_profile import SessionProfile
from deep6.scoring.scorer import ScorerResult, SignalTier, score_bar
from deep6.state.footprint import FootprintBar

log = structlog.get_logger()

# Keep the same rolling window the replay session uses. ReplaySession trims
# bar_history to the last 20 bars per timeframe (see session.py L486).
_BAR_HISTORY_WINDOW = 20


class LiveSignalPipeline:
    """Per-bar signal stack for live (or backtest-free) bar-close events.

    One instance per process. Holds per-timeframe engines and rolling state.

    Parameters
    ----------
    timeframes:
        Labels this pipeline will receive from BarBuilder. Default ("1m","5m")
        matches the production BarBuilder set built in deep6.__main__.
    """

    def __init__(self, timeframes: tuple[str, ...] = ("1m", "5m")) -> None:
        self.timeframes = timeframes

        # Per-timeframe engines.
        self._delta_eng: dict[str, DeltaEngine] = {
            tf: DeltaEngine() for tf in timeframes
        }
        self._auction_eng: dict[str, AuctionEngine] = {
            tf: AuctionEngine() for tf in timeframes
        }
        self._poc_eng: dict[str, POCEngine] = {
            tf: POCEngine() for tf in timeframes
        }
        self._trap_eng: dict[str, TrapEngine] = {
            tf: TrapEngine() for tf in timeframes
        }
        self._volpat_eng: dict[str, VolPatternEngine] = {
            tf: VolPatternEngine() for tf in timeframes
        }
        self._profile: dict[str, SessionProfile] = {
            tf: SessionProfile() for tf in timeframes
        }

        self._abs_config = AbsorptionConfig()
        self._exh_config = ExhaustionConfig()

        # Per-timeframe caller-maintained state.
        self._bar_index: dict[str, int] = {tf: 0 for tf in timeframes}
        self._prior_bar: dict[str, FootprintBar | None] = {tf: None for tf in timeframes}
        self._atr_values: dict[str, list[float]] = {tf: [] for tf in timeframes}
        self._vol_ema: dict[str, float] = {tf: 1000.0 for tf in timeframes}
        self._cvd_history: dict[str, list[int]] = {tf: [] for tf in timeframes}
        self._bar_history: dict[str, list[FootprintBar]] = {tf: [] for tf in timeframes}
        self._poc_history: dict[str, list[float]] = {tf: [] for tf in timeframes}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_bar(self, label: str, bar: FootprintBar, state: Any) -> ScorerResult | None:
        """Run the full signal stack for one closed bar.

        Returns a ScorerResult (even for QUIET bars so the dashboard gets a
        score update every bar). Returns None only if the label is not
        registered with this pipeline.
        """
        if label not in self.timeframes:
            log.debug("live_pipeline.unknown_label", label=label)
            return None

        i = self._bar_index[label]
        prior_bar = self._prior_bar[label]

        # Rolling ATR from prior bars only (no look-ahead). Matches replay.
        self._atr_values[label].append(bar.bar_range)
        atrs = self._atr_values[label]
        if len(atrs) >= 20:
            atr = sum(atrs[-20:]) / 20.0
        elif len(atrs) >= 5:
            atr = sum(atrs) / len(atrs)
        else:
            atr = 15.0

        # Volume EMA — α=0.05 (same as replay).
        if i > 0:
            self._vol_ema[label] = self._vol_ema[label] * 0.95 + bar.total_vol * 0.05
        vol_ema = self._vol_ema[label]

        # Volume profile — feed, periodic zone detection, per-bar update.
        profile = self._profile[label]
        try:
            profile.add_bar(bar)
            if i > 0 and i % 10 == 0:
                try:
                    profile.detect_zones(bar.close)
                except Exception:
                    log.exception("live_pipeline.profile.detect_zones_failed",
                                  label=label, i=i)
            try:
                profile.update_zones(bar, i)
            except Exception:
                log.exception("live_pipeline.profile.update_zones_failed",
                              label=label, i=i)
        except Exception:
            log.exception("live_pipeline.profile.add_bar_failed", label=label, i=i)

        # Narrative cascade (absorption / exhaustion / imbalance / ...).
        try:
            narrative = classify_bar(
                bar,
                prior_bar=prior_bar,
                bar_index=i,
                atr=atr,
                vol_ema=vol_ema,
                abs_config=self._abs_config,
                exh_config=self._exh_config,
            )
        except Exception:
            log.exception("live_pipeline.classify_bar_failed", label=label, i=i)
            narrative = NarrativeResult(
                bar_type=NarrativeType.QUIET,
                direction=0,
                label="QUIET",
                strength=0.0,
                price=bar.close,
                absorption=[],
                exhaustion=[],
                imbalances=[],
                all_signals_count=0,
            )

        # Per-category engines.
        try:
            delta_sigs = self._delta_eng[label].process(bar)
        except Exception:
            log.exception("live_pipeline.delta_failed", label=label, i=i)
            delta_sigs = []
        try:
            auction_sigs = self._auction_eng[label].process(bar)
        except Exception:
            log.exception("live_pipeline.auction_failed", label=label, i=i)
            auction_sigs = []
        try:
            poc_sigs = self._poc_eng[label].process(bar)
        except Exception:
            log.exception("live_pipeline.poc_failed", label=label, i=i)
            poc_sigs = []

        # Trap / VolPat — caller-maintained state.
        try:
            self._trap_eng[label].process(
                bar,
                prior_bar=prior_bar,
                vol_ema=vol_ema,
                cvd_history=self._cvd_history[label],
            )
        except Exception:
            log.exception("live_pipeline.trap_failed", label=label, i=i)
        try:
            self._volpat_eng[label].process(
                bar,
                bar_history=list(self._bar_history[label]),
                vol_ema=vol_ema,
                poc_history=self._poc_history[label],
            )
        except Exception:
            log.exception("live_pipeline.volpat_failed", label=label, i=i)

        # VPIN modifier — 1m read from SharedState (already advanced upstream
        # in SharedState.on_bar_close). 5m deferred → modifier=1.0.
        vpin_modifier = 1.0
        if label == "1m":
            try:
                vpin_modifier = state.vpin.get_confidence_modifier()
            except Exception:
                log.exception("live_pipeline.vpin_modifier_failed", label=label, i=i)
                vpin_modifier = 1.0

        # Active zones for the scorer.
        try:
            active_zones = profile.get_active_zones(min_score=20)
        except Exception:
            log.exception("live_pipeline.active_zones_failed", label=label, i=i)
            active_zones = []

        bar_index_in_session = i % 390

        # Score.
        try:
            scorer_result = score_bar(
                narrative=narrative,
                delta_signals=delta_sigs,
                auction_signals=auction_sigs,
                poc_signals=poc_sigs,
                active_zones=active_zones,
                bar_close=bar.close,
                bar_delta=bar.bar_delta,
                bar_index_in_session=bar_index_in_session,
                vpin_modifier=vpin_modifier,
            )
        except Exception:
            log.exception("live_pipeline.score_bar_failed", label=label, i=i)
            scorer_result = ScorerResult(
                total_score=0.0,
                tier=SignalTier.QUIET,
                direction=0,
                engine_agreement=0.0,
                category_count=0,
                confluence_mult=1.0,
                zone_bonus=0.0,
                narrative=NarrativeType.QUIET,
                label="QUIET",
            )

        # Advance rolling state — mirrors ReplaySession.post-bar maintenance.
        self._prior_bar[label] = bar
        self._cvd_history[label].append(bar.cvd)
        self._bar_history[label].append(bar)
        if len(self._bar_history[label]) > _BAR_HISTORY_WINDOW:
            self._bar_history[label] = self._bar_history[label][-_BAR_HISTORY_WINDOW:]
        self._poc_history[label].append(bar.poc_price)
        self._bar_index[label] += 1

        return scorer_result
