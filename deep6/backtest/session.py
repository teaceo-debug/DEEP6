"""ReplaySession — orchestrator for backtest replay.

Phase 13-01 T-13-01-10. Wires together the four core pieces:

    EventClock  ──▶  SharedState.clock
        │
        │     bar-close events
        ▼
    MBOAdapter ──▶  on_tick / on_dom ──▶ DOMState + BarAccumulator
                                                       │
                                                       ▼
                                            DOM-signal engines (E2/E3/E4)
                                                       │
                                                       ▼
                                            DuckDBResultStore.record_bar

Replay differs from live in one key way: we cannot use ``BarBuilder.run()``
because it ``asyncio.sleep``s to real wall-clock bar boundaries. Replay
must advance bar boundaries with event time. ``ReplaySession`` owns a
lightweight, event-driven accumulator that mirrors ``BarBuilder.on_trade``
semantics and closes a bar the first time an incoming tick's timestamp
exceeds the next boundary.

The ReplaySession is intentionally self-contained: tests construct one
with a synthetic ``event_source`` and assert on the DuckDB outputs
directly. Production callers (phase 14 sweep harness) supply a
Databento-backed adapter.
"""
from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Literal

import structlog

from deep6.backtest.bracket_exit import BracketExitTracker, ClosedTrade
from deep6.backtest.clock import EventClock
from deep6.backtest.config import BacktestConfig
from deep6.backtest.mbo_adapter import MBOAdapter
from deep6.backtest.result_store import DuckDBResultStore
from deep6.engines.auction import AuctionEngine
from deep6.engines.counter_spoof import CounterSpoofEngine
from deep6.engines.delta import DeltaEngine
from deep6.engines.iceberg import IcebergEngine
from deep6.engines.narrative import classify_bar, reset_confirmations
from deep6.engines.exhaustion import reset_cooldowns
from deep6.engines.poc import POCEngine
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig
from deep6.engines.trap import TrapEngine
from deep6.engines.trespass import TrespassEngine
from deep6.engines.vol_patterns import VolPatternEngine
from deep6.engines.volume_profile import SessionProfile
from deep6.orderflow.vpin import VPINEngine
from deep6.scoring.scorer import SignalTier, score_bar
from deep6.state.dom import DOMState
from deep6.state.footprint import FootprintBar

log = structlog.get_logger(__name__)


# Signal bit positions for DOM-dependent engines — only used to pack a
# compact signal_flags mask into DuckDB. Real live code uses
# deep6.signals.flags.SignalFlags; we keep the constants local so
# ReplaySession doesn't need to know which IMB/DELT/AUCT positions are
# currently assigned.
_BIT_E2_TRESPASS = 1 << 12      # co-located with IMB_SINGLE — illustrative
_BIT_E3_COUNTER_SPOOF = 1 << 37  # TRAP region
_BIT_E4_ICEBERG = 1 << 38        # TRAP region


def _tier_to_name(tier: SignalTier) -> str:
    """Map SignalTier to the string persisted in backtest_bars.tier.

    Matches scripts/backtest_signals.py convention (tier.name) so downstream
    tooling sees identical tier labels whether produced via live pipeline or
    replay.
    """
    return tier.name


def _flags_to_signal_flags_mask(
    abs_count: int,
    exh_count: int,
    imb_count: int,
    delta_count: int,
    auction_count: int,
    poc_count: int,
    trap_count: int,
    volpat_count: int,
) -> int:
    """Pack per-category firing counts into the signal_flags bitmask.

    ReplaySession does not know which specific sub-signal fired (narrative
    collapses to counts), so we set the *group primary* bit per category
    to mark presence. This is lossier than the live path but sufficient
    for downstream tools that query ``signal_flags != 0`` or popcount the
    category presence.
    """
    mask = 0
    if abs_count:
        mask |= 1 << 0    # ABS_CLASSIC as group marker
    if exh_count:
        mask |= 1 << 5    # EXH_EXHAUSTION as group marker
    if imb_count:
        mask |= 1 << 12   # IMB_SINGLE as group marker
    if delta_count:
        mask |= 1 << 24   # DELT_DIVERGENCE as group marker
    if auction_count:
        mask |= 1 << 33   # AUCT_FINISHED as group marker
    if poc_count:
        # POC is not its own SignalFlags group today — leave at 0 (handled
        # in score). Documented here so the gap is intentional, not a bug.
        pass
    if trap_count:
        mask |= 1 << 37   # TRAP_INVERSE_I as group marker
    if volpat_count:
        mask |= 1 << 42   # VOLP_SEQUENCING as group marker
    return mask


class ReplaySession(AbstractAsyncContextManager["ReplaySession"]):
    """Drive a full Databento MBO replay through DEEP6 signal engines.

    Usage:
        cfg = BacktestConfig(dataset="GLBX.MDP3", symbol="NQ.c.0",
                             start=..., end=...)
        async with ReplaySession(cfg, state, event_source=ev_iter) as s:
            await s.run()

    If ``event_source`` is None, MBOAdapter opens a live Databento
    historical range (requires ``DATABENTO_API_KEY``).
    """

    def __init__(
        self,
        config: BacktestConfig,
        state: Any,   # SharedState — typed as Any to avoid circular import surface
        event_source: Iterable[Any] | None = None,
        bar_close_hook: Callable[[str, FootprintBar, dict], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.run_id = str(uuid.uuid4())

        # Inject the replay clock. WallClock default is overwritten for the
        # lifetime of the session — callers are expected to either spawn a
        # fresh SharedState per replay or restore state.clock = WallClock()
        # post-run if they reuse a state object.
        self._clock = EventClock()
        state.clock = self._clock

        self._adapter = MBOAdapter(
            dataset=config.dataset,
            symbol=config.symbol,
            start=config.start.isoformat(),
            end=config.end.isoformat(),
            clock=self._clock,
            tick_size=config.tick_size,
            event_source=event_source,
        )

        self._store = DuckDBResultStore(config.duckdb_path)

        # DOM-dependent engines — instantiated fresh per session so their
        # internal history is isolated from prior runs.
        self._trespass = TrespassEngine()
        self._counter_spoof = CounterSpoofEngine()
        self._iceberg = IcebergEngine()

        # Full-signal pipeline (44 signals) — mirrors scripts/backtest_signals.py::run_backtest.
        # classify_bar / score_bar operate on FootprintBar + caller-maintained
        # state. One copy per timeframe so 1m and 5m histories don't cross.
        self._delta_eng: dict[str, DeltaEngine] = {tf: DeltaEngine() for tf in config.tf_list}
        self._auction_eng: dict[str, AuctionEngine] = {tf: AuctionEngine() for tf in config.tf_list}
        self._poc_eng: dict[str, POCEngine] = {tf: POCEngine() for tf in config.tf_list}
        self._trap_eng: dict[str, TrapEngine] = {tf: TrapEngine() for tf in config.tf_list}
        self._volpat_eng: dict[str, VolPatternEngine] = {tf: VolPatternEngine() for tf in config.tf_list}
        self._profile: dict[str, SessionProfile] = {tf: SessionProfile() for tf in config.tf_list}
        self._vpin_eng: dict[str, VPINEngine] = {tf: VPINEngine() for tf in config.tf_list}
        self._abs_config = AbsorptionConfig()
        self._exh_config = ExhaustionConfig()

        # Per-timeframe caller-maintained state (matches run_backtest loop).
        self._bar_index: dict[str, int] = {tf: 0 for tf in config.tf_list}
        self._prior_bar: dict[str, FootprintBar | None] = {tf: None for tf in config.tf_list}
        self._atr_values: dict[str, list[float]] = {tf: [] for tf in config.tf_list}
        self._vol_ema: dict[str, float] = {tf: 1000.0 for tf in config.tf_list}
        self._cvd_history: dict[str, list[int]] = {tf: [] for tf in config.tf_list}
        self._bar_history: dict[str, list[FootprintBar]] = {tf: [] for tf in config.tf_list}
        self._poc_history: dict[str, list[float]] = {tf: [] for tf in config.tf_list}

        # Trades produced by the simple sim-fill hook. Count exposed as a
        # property for test assertions.
        self._trades_written = 0
        self._trades_closed = 0
        self._trades_truncated = 0

        # Bracket-exit simulator (Phase 13-03). Resolves TYPE_A/TYPE_B
        # trades against the high/low of subsequent bars.
        self._bracket = BracketExitTracker(config)
        # Last bar close seen — used to force-close open trades on exit.
        self._last_bar_close: float = 0.0
        self._last_bar_ts: float = 0.0

        # Session-bounded narrative state is global (absorption confirmations).
        # Reset on init so back-to-back replays never see stale trackers.
        reset_confirmations()
        reset_cooldowns()

        # Per-timeframe bar accumulators (seconds).
        self._tf_seconds: dict[str, int] = {"1m": 60, "5m": 300}
        self._tf_seconds = {tf: self._tf_seconds[tf] for tf in config.tf_list if tf in self._tf_seconds}
        self._current_bars: dict[str, FootprintBar] = {tf: FootprintBar() for tf in self._tf_seconds}
        self._next_boundary: dict[str, float] = {tf: 0.0 for tf in self._tf_seconds}
        self._prior_cvd: dict[str, int] = {tf: 0 for tf in self._tf_seconds}

        self._bar_close_hook = bar_close_hook
        self._bars_written = 0
        self._dom_signal_fires = 0   # tracked for integration assertions
        self._scorer_signal_fires = 0  # TIER_A/B/C bars produced by scorer

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ReplaySession":
        self._store.__enter__()
        self._store.record_run(
            run_id=self.run_id,
            symbol=self.config.symbol,
            dataset=self.config.dataset,
            config_json=self.config.model_dump(mode="json"),
            git_sha=self.config.git_sha,
            start_ts=self.config.start,
            end_ts=self.config.end,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Force-close any still-open trades at the last bar's close with
        # exit_reason="TRUNCATED" — so no row dangles with NULL exit
        # columns at stream end.
        if self._bracket.open_count > 0 and self._last_bar_ts:
            closed = self._bracket.force_close_all(
                last_price=self._last_bar_close,
                ts=self._last_bar_ts,
                reason="TRUNCATED",
            )
            for ct in closed:
                self._persist_closed_trade(ct)
        self._store.flush()
        self._store.__exit__(exc_type, exc, tb)

    # ------------------------------------------------------------------
    # Bracket-exit persistence
    # ------------------------------------------------------------------

    def _persist_closed_trade(self, ct: ClosedTrade) -> None:
        """Write a bracket exit back to the backtest_trades row."""
        exit_dt = datetime.fromtimestamp(ct.exit_ts, tz=timezone.utc)
        self._store.update_trade_exit(
            trade_id=ct.trade_id,
            exit_ts=exit_dt,
            exit_price=ct.exit_price,
            pnl=ct.pnl_dollars,
            exit_reason=ct.exit_reason,
        )
        if ct.exit_reason == "TRUNCATED":
            self._trades_truncated += 1
        else:
            self._trades_closed += 1

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Pull every MBO event through the pipeline. Returns on stream exhaust."""
        await self._adapter.run(on_tick=self._on_tick, on_dom=self._on_dom)
        # Finalize any bars still in progress (stream ended mid-bar).
        for tf in list(self._current_bars.keys()):
            if self._current_bars[tf].total_vol > 0:
                await self._close_bar(tf, ts_now=self._clock.now())

    @property
    def bars_written(self) -> int:
        return self._bars_written

    @property
    def dom_signal_fires(self) -> int:
        return self._dom_signal_fires

    @property
    def scorer_signal_fires(self) -> int:
        return self._scorer_signal_fires

    @property
    def trades_written(self) -> int:
        return self._trades_written

    @property
    def trades_closed(self) -> int:
        """Trades resolved by stop / target / hold-expiry (not truncation)."""
        return self._trades_closed

    @property
    def trades_truncated(self) -> int:
        """Trades force-closed at stream end (bracket never resolved)."""
        return self._trades_truncated

    # ------------------------------------------------------------------
    # Callbacks (shape: live-compatible)
    # ------------------------------------------------------------------

    async def _on_tick(
        self,
        price: float,
        size: int,
        aggressor: Literal["BUY", "SELL"],
    ) -> None:
        ts_now = self._clock.now()
        # Close any bars whose boundary is now in the past.
        for tf in self._tf_seconds:
            await self._maybe_close_bar(tf, ts_now)
        aggr_int = 1 if aggressor == "BUY" else 2
        for tf in self._tf_seconds:
            self._current_bars[tf].add_trade(price, size, aggr_int)

    async def _on_dom(
        self,
        bid_levels: list[tuple[float, int]],
        ask_levels: list[tuple[float, int]],
    ) -> None:
        # Update the shared DOMState in-place — same contract as live dom_feed.
        bid_prices = [p for p, _ in bid_levels]
        bid_sizes = [s for _, s in bid_levels]
        ask_prices = [p for p, _ in ask_levels]
        ask_sizes = [s for _, s in ask_levels]
        self.state.dom.update(
            bid_prices, bid_sizes, ask_prices, ask_sizes,
            ts=self._clock.monotonic(),
        )

    # ------------------------------------------------------------------
    # Bar lifecycle
    # ------------------------------------------------------------------

    async def _maybe_close_bar(self, tf: str, ts_now: float) -> None:
        """Close the current bar if ts_now has crossed its boundary."""
        period = self._tf_seconds[tf]
        boundary = self._next_boundary[tf]
        if boundary == 0.0:
            # First event — seed boundary at the next period multiple.
            self._next_boundary[tf] = (int(ts_now // period) + 1) * period
            return
        while ts_now >= boundary:
            await self._close_bar(tf, ts_now=boundary)
            boundary = boundary + period
        self._next_boundary[tf] = boundary

    async def _close_bar(self, tf: str, ts_now: float) -> None:
        bar = self._current_bars[tf]
        bar.timestamp = ts_now
        bar.finalize(self._prior_cvd[tf])
        self._prior_cvd[tf] = bar.cvd

        # Run DOM-dependent engines against the current DOMState snapshot.
        dom_flags, dom_direction_int = self._run_dom_engines(bar)

        # Run the full 44-signal pipeline (mirrors run_backtest in
        # scripts/backtest_signals.py — order is load-bearing).
        scorer_result, narrative = self._run_full_pipeline(tf, bar)

        # Merge DOM-engine flags with scorer-derived category flags.
        scorer_flag_mask = _flags_to_signal_flags_mask(
            abs_count=len(narrative.absorption),
            exh_count=len(narrative.exhaustion),
            imb_count=len(narrative.imbalances),
            delta_count=scorer_result.category_count if "delta" in scorer_result.categories_firing else 0,
            auction_count=scorer_result.category_count if "auction" in scorer_result.categories_firing else 0,
            poc_count=scorer_result.category_count if "poc" in scorer_result.categories_firing else 0,
            trap_count=scorer_result.category_count if "trapped" in scorer_result.categories_firing else 0,
            volpat_count=0,  # volpat not in scorer category set today
        )
        signal_flags = dom_flags | scorer_flag_mask | int(scorer_result.meta_flags)

        # Tier / direction / score come from the scorer when it produced a
        # tradeable signal; otherwise fall back to the DOM-engine tier label
        # so tests relying on TIER_3 semantics keep passing when no scorer
        # signal fires (matches pre-refactor behavior for DOM-only bars).
        if scorer_result.tier != SignalTier.QUIET and scorer_result.tier != SignalTier.DISQUALIFIED:
            tier_name = _tier_to_name(scorer_result.tier)
            direction_int = scorer_result.direction
            score = scorer_result.total_score
            self._scorer_signal_fires += 1
        elif dom_flags != 0:
            tier_name = "TIER_3"
            direction_int = dom_direction_int
            score = 0.0
        else:
            tier_name = _tier_to_name(scorer_result.tier)  # QUIET / DISQUALIFIED
            direction_int = scorer_result.direction
            score = scorer_result.total_score

        if direction_int > 0:
            direction_str = "LONG"
        elif direction_int < 0:
            direction_str = "SHORT"
        else:
            direction_str = "NONE"

        bar_ts = datetime.fromtimestamp(ts_now, tz=timezone.utc)
        self._store.record_bar(
            run_id=self.run_id,
            bar_ts=bar_ts,
            tf=tf,
            ohlcv=(
                bar.open, bar.high, bar.low, bar.close, bar.total_vol,
            ),
            signal_flags=signal_flags,
            score=score,
            tier=tier_name,
            direction=direction_str,
            bar_key=self._bars_written,
        )
        self._bars_written += 1

        # Resolve any previously-open trades against THIS bar's high/low.
        # Done BEFORE opening a new trade so the just-opened trade is
        # never resolved on its own entry bar (entry is at bar.close —
        # we have no intrabar info to fairly evaluate brackets against
        # the same bar's range).
        closed_trades = self._bracket.on_bar(bar, ts_now)
        for ct in closed_trades:
            self._persist_closed_trade(ct)

        # Simple sim-fill hook: any TYPE_A/TYPE_B with a direction opens a
        # trade. TYPE_C is excluded (alert-only tier per scorer.py
        # docstring). Exit is resolved by BracketExitTracker on subsequent
        # bars; see Phase 13-03 bracket_exit.py for fill model + tie-break.
        if (
            scorer_result.tier in (SignalTier.TYPE_A, SignalTier.TYPE_B)
            and scorer_result.direction != 0
        ):
            trade_id = str(uuid.uuid4())
            self._store.record_trade(
                run_id=self.run_id,
                entry_ts=bar_ts,
                exit_ts=None,
                side="LONG" if scorer_result.direction > 0 else "SHORT",
                qty=1,
                entry_price=bar.close,
                exit_price=None,
                pnl=0.0,
                tier=tier_name,
                fill_model=self.config.fill_model,
                trade_id=trade_id,
                exit_reason=None,
            )
            self._bracket.open_trade(
                trade_id=trade_id,
                entry_price=bar.close,
                direction=1 if scorer_result.direction > 0 else -1,
                entry_ts=ts_now,
            )
            self._trades_written += 1

        self._last_bar_close = bar.close
        self._last_bar_ts = ts_now

        if self._bar_close_hook is not None:
            try:
                await self._bar_close_hook(
                    tf, bar, {"signal_flags": signal_flags, "score": score},
                )
            except Exception:
                log.exception("replay.bar_close_hook_failed", tf=tf)

        # Update caller-maintained pipeline state AFTER processing the bar
        # (ordering matches run_backtest loop).
        self._prior_bar[tf] = bar
        self._cvd_history[tf].append(bar.cvd)
        self._bar_history[tf].append(bar)
        if len(self._bar_history[tf]) > 20:
            self._bar_history[tf] = self._bar_history[tf][-20:]
        self._poc_history[tf].append(bar.poc_price)
        self._bar_index[tf] += 1

        # Reset bar accumulator.
        self._current_bars[tf] = FootprintBar()

    # ------------------------------------------------------------------
    # Engine plumbing
    # ------------------------------------------------------------------

    def _run_full_pipeline(self, tf: str, bar: FootprintBar):
        """Run classify_bar + the per-category engines + score_bar.

        Mirrors scripts/backtest_signals.py::run_backtest loop body. Returns
        ``(ScorerResult, NarrativeResult)`` — callers merge the scorer flag
        mask with DOM-engine flags and persist.
        """
        i = self._bar_index[tf]
        prior_bar = self._prior_bar[tf]

        # Rolling ATR from prior bars only (no look-ahead).
        self._atr_values[tf].append(bar.bar_range)
        atrs = self._atr_values[tf]
        if len(atrs) >= 20:
            atr = sum(atrs[-20:]) / 20.0
        elif len(atrs) >= 5:
            atr = sum(atrs) / len(atrs)
        else:
            atr = 15.0

        # Vol EMA — same coefficients as run_backtest (α=0.05).
        if i > 0:
            self._vol_ema[tf] = self._vol_ema[tf] * 0.95 + bar.total_vol * 0.05
        vol_ema = self._vol_ema[tf]

        # Volume profile — feed + periodic zone detection + per-bar update.
        profile = self._profile[tf]
        profile.add_bar(bar)
        if i > 0 and i % 10 == 0:
            try:
                profile.detect_zones(bar.close)
            except Exception:
                log.exception("replay.profile.detect_zones_failed", tf=tf, i=i)
        try:
            profile.update_zones(bar, i)
        except Exception:
            log.exception("replay.profile.update_zones_failed", tf=tf, i=i)

        # Narrative cascade (absorption / exhaustion / imbalance / momentum / rejection).
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
            log.exception("replay.classify_bar_failed", tf=tf, i=i)
            from deep6.engines.narrative import NarrativeResult, NarrativeType
            narrative = NarrativeResult(
                bar_type=NarrativeType.QUIET, direction=0, label="QUIET",
                strength=0.0, price=bar.close,
                absorption=[], exhaustion=[], imbalances=[],
                all_signals_count=0,
            )

        # Per-category engines.
        try:
            delta_sigs = self._delta_eng[tf].process(bar)
        except Exception:
            log.exception("replay.delta_failed", tf=tf, i=i)
            delta_sigs = []
        try:
            auction_sigs = self._auction_eng[tf].process(bar)
        except Exception:
            log.exception("replay.auction_failed", tf=tf, i=i)
            auction_sigs = []
        try:
            poc_sigs = self._poc_eng[tf].process(bar)
        except Exception:
            log.exception("replay.poc_failed", tf=tf, i=i)
            poc_sigs = []

        # Trap / VolPat use caller-maintained state.
        try:
            self._trap_eng[tf].process(
                bar, prior_bar=prior_bar, vol_ema=vol_ema,
                cvd_history=self._cvd_history[tf],
            )
        except Exception:
            log.exception("replay.trap_failed", tf=tf, i=i)
        try:
            self._volpat_eng[tf].process(
                bar, bar_history=list(self._bar_history[tf]),
                vol_ema=vol_ema, poc_history=self._poc_history[tf],
            )
        except Exception:
            log.exception("replay.volpat_failed", tf=tf, i=i)

        # VPIN — modifier folded into total_score by scorer.
        try:
            self._vpin_eng[tf].update_from_bar(bar)
            vpin_modifier = self._vpin_eng[tf].get_confidence_modifier()
        except Exception:
            log.exception("replay.vpin_failed", tf=tf, i=i)
            vpin_modifier = 1.0

        # Score.
        try:
            active_zones = profile.get_active_zones(min_score=20)
        except Exception:
            active_zones = []
        bar_index_in_session = i % 390
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
            log.exception("replay.score_bar_failed", tf=tf, i=i)
            from deep6.scoring.scorer import ScorerResult
            from deep6.engines.narrative import NarrativeType
            scorer_result = ScorerResult(
                total_score=0.0, tier=SignalTier.QUIET, direction=0,
                engine_agreement=0.0, category_count=0,
                confluence_mult=1.0, zone_bonus=0.0,
                narrative=NarrativeType.QUIET, label="QUIET",
            )

        return scorer_result, narrative

    def _run_dom_engines(
        self, bar: FootprintBar
    ) -> tuple[int, int]:
        """Run the three DOM-dependent engines against the current DOMState.

        Returns ``(signal_flags, direction_int)``. Engine failures degrade to
        a no-signal tuple — never kill the replay.
        """
        dom: DOMState = self.state.dom
        dom_snapshot = dom.snapshot()
        flags = 0
        direction_int = 0

        # E2 Trespass — queue imbalance.
        try:
            t = self._trespass.process(dom_snapshot)
            if t.direction != 0:
                flags |= _BIT_E2_TRESPASS
                direction_int = t.direction
                self._dom_signal_fires += 1
        except Exception:
            log.exception("replay.trespass_failed")

        bid_prices, bid_sizes, ask_prices, ask_sizes = dom_snapshot

        # E3 Counter-spoof — cancel-heavy W1 anomaly. The engine is
        # stateful: it's fed each bar-close snapshot and returns alerts
        # via get_spoof_alerts() as they accumulate. We check for any
        # new alerts produced since the prior bar.
        try:
            pre_alerts = len(self._counter_spoof.get_spoof_alerts())
            self._counter_spoof.ingest_snapshot(
                bid_prices, bid_sizes, ask_prices, ask_sizes,
                timestamp=self._clock.monotonic(),
            )
            post_alerts = self._counter_spoof.get_spoof_alerts()
            if len(post_alerts) > pre_alerts:
                flags |= _BIT_E3_COUNTER_SPOOF
                self._dom_signal_fires += 1
        except Exception:
            log.exception("replay.counter_spoof_failed")

        # E4 Iceberg — synthetic refill detection via DOM delta.
        try:
            sigs = self._iceberg.update_dom(
                bid_prices, bid_sizes, ask_prices, ask_sizes,
                timestamp=self._clock.monotonic(),
            )
            if sigs:
                flags |= _BIT_E4_ICEBERG
                self._dom_signal_fires += len(sigs)
        except Exception:
            log.exception("replay.iceberg_failed")

        return flags, direction_int
