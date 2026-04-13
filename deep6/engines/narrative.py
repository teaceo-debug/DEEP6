"""Narrative cascade — priority-based signal classification per bar.

Per ABS-05: absorption > exhaustion > momentum > rejection > quiet
One primary signal per bar. Multiple signals detected but only the
highest-priority one drives the narrative label and zone creation.

From Andrea Chimmy's orderflow framework:
  ABSORPTION: strongest reversal — passive orders absorbed aggression
  EXHAUSTION: weaker reversal — aggressor ran out of steam
  MOMENTUM:   continuation — "toxic orderflow" to market makers
  REJECTION:  price explored and was rejected (wick dominated)
  QUIET:      nothing noteworthy
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from deep6.engines.absorption import AbsorptionSignal, detect_absorption
from deep6.engines.exhaustion import ExhaustionSignal, detect_exhaustion
from deep6.engines.imbalance import ImbalanceSignal, detect_imbalances
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig
from deep6.state.footprint import FootprintBar, tick_to_price


class NarrativeType(IntEnum):
    """Priority order — lower value = higher priority."""
    ABSORPTION = 1
    EXHAUSTION = 2
    MOMENTUM = 3
    REJECTION = 4
    QUIET = 5


@dataclass
class AbsorptionConfirmation:
    """Tracks whether an absorption zone was defended within the confirmation window.

    ABS-06 / D-06 / D-07: After an absorption signal fires, watch the next
    confirmation_window_bars bars. If the zone holds (price doesn't breach by more
    than confirmation_breach_ticks) AND a same-direction delta bar appears, mark confirmed.

    NOTE: When confirmed=True, scorer.py should add AbsorptionConfig.confirmation_score_bonus
    (+2.0) to the zone score. This class is the data carrier — scoring happens in scorer.py.
    """
    signal: AbsorptionSignal       # Original signal that triggered this tracker
    bar_fired: int                  # bar_index when absorption fired
    zone_price: float               # Absorption price level (reference for defense check)
    direction: int                  # +1 bullish (sellers absorbed), -1 bearish (buyers absorbed)
    confirmed: bool = False         # True when defense + same-direction delta observed
    expired: bool = False           # True when window elapsed without confirmation


# --- ABS-06 module-level confirmation state (T-02-05: reset at session start) ---
_pending_confirmations: list[AbsorptionConfirmation] = []


def reset_confirmations() -> None:
    """Clear all pending confirmation trackers.

    Call at session start to prevent cross-session state leakage (T-02-05).
    """
    _pending_confirmations.clear()


@dataclass
class NarrativeResult:
    """The classified narrative for one bar."""
    bar_type: NarrativeType
    direction: int              # +1 = bullish, -1 = bearish, 0 = neutral
    label: str                  # Human-readable (e.g., "SELLERS ABSORBED @VAL")
    strength: float             # 0-1
    price: float                # Signal price level
    absorption: list[AbsorptionSignal]
    exhaustion: list[ExhaustionSignal]
    imbalances: list[ImbalanceSignal]
    all_signals_count: int      # total signals detected before cascade
    confirmed_absorptions: list[AbsorptionConfirmation] = field(default_factory=list)
    # ABS-06: Confirmations that triggered on this bar (defense + same-direction delta observed).
    # scorer.py should add AbsorptionConfig.confirmation_score_bonus to zone score for each entry.


def classify_bar(
    bar: FootprintBar,
    prior_bar: FootprintBar | None = None,
    bar_index: int = 0,
    atr: float = 15.0,
    vol_ema: float = 500.0,
    vwap: float | None = None,
    vah: float | None = None,
    val: float | None = None,
    abs_config: AbsorptionConfig | None = None,
    exh_config: ExhaustionConfig | None = None,
) -> NarrativeResult:
    """Classify a bar using the narrative cascade.

    Detects all signal types, then selects the highest-priority one
    as the bar's narrative. All detected signals are still available
    in the result for confluence scoring.

    Args:
        bar: Finalized FootprintBar
        prior_bar: Previous bar for multi-bar signals
        bar_index: Current bar index
        atr: ATR(20) for adaptive thresholds
        vol_ema: Running average volume
        vwap/vah/val: Value area levels for context labels
        abs_config: AbsorptionConfig for threshold tuning (Phase 7 sweeps).
                    If None, uses AbsorptionConfig() defaults — backward compat.
        exh_config: ExhaustionConfig for threshold tuning (Phase 7 sweeps).
                    If None, uses ExhaustionConfig() defaults — backward compat.
    """
    # Detect all signal types — pass config objects through to engines
    abs_signals = detect_absorption(bar, atr=atr, vol_ema=vol_ema, config=abs_config, vah=vah, val=val)
    exh_signals = detect_exhaustion(bar, prior_bar=prior_bar, bar_index=bar_index, atr=atr, config=exh_config)
    imb_signals = detect_imbalances(bar, prior_bar=prior_bar)

    total_signals = len(abs_signals) + len(exh_signals) + len(imb_signals)

    # --- ABS-06: Absorption confirmation tracking (D-06, D-07) ---
    # Resolve config for confirmation params (use defaults if not provided).
    _abs_cfg = abs_config if abs_config is not None else AbsorptionConfig()
    tick_size = 0.25
    breach_points = _abs_cfg.confirmation_breach_ticks * tick_size

    # 1. Register new absorption signals as pending confirmations
    for sig in abs_signals:
        _pending_confirmations.append(AbsorptionConfirmation(
            signal=sig,
            bar_fired=bar_index,
            zone_price=sig.price,
            direction=sig.direction,
        ))

    # 2. Evaluate existing pending confirmations against current bar
    newly_confirmed: list[AbsorptionConfirmation] = []
    for conf in _pending_confirmations:
        if conf.confirmed or conf.expired:
            continue

        # Expire if window has elapsed
        if bar_index - conf.bar_fired > _abs_cfg.confirmation_window_bars:
            conf.expired = True
            continue

        # Skip the bar the signal fired on (bar_index == conf.bar_fired)
        if bar_index == conf.bar_fired:
            continue

        # Defense check: price must not breach zone by more than breach_points
        if conf.direction > 0:
            # Bullish absorption: zone at low — bar.low must stay above zone - breach
            price_holds = bar.low >= conf.zone_price - breach_points
        else:
            # Bearish absorption: zone at high — bar.high must stay below zone + breach
            price_holds = bar.high <= conf.zone_price + breach_points

        # Same-direction delta check
        if conf.direction > 0:
            delta_confirms = bar.bar_delta > 0
        else:
            delta_confirms = bar.bar_delta < 0

        if price_holds and delta_confirms:
            conf.confirmed = True
            newly_confirmed.append(conf)

    # --- CASCADE: absorption > exhaustion > momentum > rejection > quiet ---

    # 1. ABSORPTION — highest priority
    if abs_signals:
        best = max(abs_signals, key=lambda s: s.strength)
        label = _absorption_label(best, vwap, vah, val)
        return NarrativeResult(
            bar_type=NarrativeType.ABSORPTION,
            direction=best.direction,
            label=label,
            strength=best.strength,
            price=best.price,
            absorption=abs_signals,
            exhaustion=exh_signals,
            imbalances=imb_signals,
            all_signals_count=total_signals,
            confirmed_absorptions=newly_confirmed,
        )

    # 2. EXHAUSTION
    if exh_signals:
        best = max(exh_signals, key=lambda s: s.strength)
        label = _exhaustion_label(best)
        return NarrativeResult(
            bar_type=NarrativeType.EXHAUSTION,
            direction=best.direction,
            label=label,
            strength=best.strength,
            price=best.price,
            absorption=abs_signals,
            exhaustion=exh_signals,
            imbalances=imb_signals,
            all_signals_count=total_signals,
            confirmed_absorptions=newly_confirmed,
        )

    # 3. MOMENTUM — body dominates + strong directional delta
    body_pct = 0.0
    if bar.bar_range > 0:
        body = abs(bar.close - bar.open)
        body_pct = (body / bar.bar_range) * 100

    delta_ratio = abs(bar.bar_delta) / bar.total_vol if bar.total_vol > 0 else 0

    if body_pct >= 72.0 and delta_ratio >= 0.25:
        direction = +1 if bar.close > bar.open else -1
        extended = False
        if vwap is not None and vah is not None and val is not None:
            extended = (direction > 0 and bar.close > vah) or (direction < 0 and bar.close < val)

        if extended:
            label = f"MOMENTUM EXTENDED — DON'T CHASE {'LONGS' if direction > 0 else 'SHORTS'}"
        else:
            label = f"MOMENTUM IGNITION — JOIN {'BUYERS' if direction > 0 else 'SELLERS'}"

        return NarrativeResult(
            bar_type=NarrativeType.MOMENTUM,
            direction=direction,
            label=label,
            strength=min(body_pct / 90.0, 1.0) * min(delta_ratio / 0.5, 1.0),
            price=bar.close,
            absorption=abs_signals,
            exhaustion=exh_signals,
            imbalances=imb_signals,
            all_signals_count=total_signals,
            confirmed_absorptions=newly_confirmed,
        )

    # 4. REJECTION — wick volume dominates
    if bar.bar_range > 0 and bar.total_vol > 0:
        body_top = max(bar.open, bar.close)
        body_bot = min(bar.open, bar.close)
        uw_vol = sum(
            lv.ask_vol + lv.bid_vol
            for t, lv in bar.levels.items()
            if tick_to_price(t) > body_top
        )
        lw_vol = sum(
            lv.ask_vol + lv.bid_vol
            for t, lv in bar.levels.items()
            if tick_to_price(t) < body_bot
        )
        wick_pct = (uw_vol + lw_vol) / bar.total_vol * 100

        if wick_pct >= 55.0:
            if uw_vol > lw_vol:
                direction = -1
                label = "REJECTED HIGH — WATCH FOR SHORT"
            else:
                direction = +1
                label = "REJECTED LOW — WATCH FOR LONG"

            if vah is not None and val is not None:
                mid = (bar.high + bar.low) / 2
                if abs(mid - vah) < atr * 0.5:
                    label = f"REJECTED @VAH — HIGH PROB SHORT"
                elif abs(mid - val) < atr * 0.5:
                    label = f"REJECTED @VAL — HIGH PROB LONG"

            return NarrativeResult(
                bar_type=NarrativeType.REJECTION,
                direction=direction,
                label=label,
                strength=min(wick_pct / 80.0, 1.0),
                price=bar.high if uw_vol > lw_vol else bar.low,
                absorption=abs_signals,
                exhaustion=exh_signals,
                imbalances=imb_signals,
                all_signals_count=total_signals,
                confirmed_absorptions=newly_confirmed,
            )

    # 5. QUIET
    return NarrativeResult(
        bar_type=NarrativeType.QUIET,
        direction=0,
        label="QUIET",
        strength=0.0,
        price=bar.close,
        absorption=abs_signals,
        exhaustion=exh_signals,
        imbalances=imb_signals,
        all_signals_count=total_signals,
        confirmed_absorptions=newly_confirmed,
    )


def _absorption_label(sig: AbsorptionSignal, vwap, vah, val) -> str:
    """Generate context-aware absorption label.

    Uses sig.at_va_extreme (set by detect_absorption via ABS-07) rather than
    recomputing proximity — ensures label threshold is consistent with the 2-tick
    bonus threshold in AbsorptionConfig.va_extreme_ticks.
    """
    base = "SELLERS ABSORBED" if sig.direction > 0 else "BUYERS ABSORBED"
    suffix = ""

    if sig.at_va_extreme:
        # Determine which VA extreme from price proximity (vah/val may be None if one is missing)
        if sig.direction > 0:
            suffix = " @VAL — HIGH CONVICTION LONG ZONE"
        else:
            suffix = " @VAH — HIGH CONVICTION SHORT ZONE"
    elif vah is not None or val is not None:
        suffix = " — WAIT FOR CONTROL"

    return f"{base}{suffix}"


def _exhaustion_label(sig: ExhaustionSignal) -> str:
    """Generate exhaustion label."""
    if sig.direction == -1:
        return "BUYERS LOSING STEAM — NOT A TRADE YET"
    elif sig.direction == +1:
        return "SELLERS LOSING STEAM — NOT A TRADE YET"
    return sig.detail
