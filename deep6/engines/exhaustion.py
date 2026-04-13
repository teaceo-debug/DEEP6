"""E1b: Exhaustion signal detection — 6 variants.

EXHAUSTION detects when aggressive traders run out of steam.
Unlike absorption (where passive orders defend), exhaustion means
the aggressor simply has no more ammunition — weaker reversal signal
but earlier warning.

Variants (per EXH-01..06):
  1. Zero Print:      Price level with 0 volume on both sides (gap)
  2. Exhaustion Print: High single-side volume at extreme, no follow-through
  3. Thin Print:       Volume at price row < 5% of bar's max (fast move)
  4. Fat Print:        Volume at price row > threshold × average (strong acceptance)
  5. Fading Momentum:  Delta trajectory diverges from price (E8 CVD — stub for now)
  6. Bid/Ask Fade:     Ask volume at extreme < 60% of prior bar's ask

Universal delta trajectory gate (EXH-07 / D-08) applied to variants 2-6.
Zero print (EXH-01) is exempt — it is structural, not delta-dependent.

All thresholds are ATR-adaptive (ARCH-03, SCOR-05).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from deep6.engines.signal_config import ExhaustionConfig
from deep6.state.footprint import FootprintBar, tick_to_price, price_to_tick


class ExhaustionType(Enum):
    ZERO_PRINT = auto()
    EXHAUSTION_PRINT = auto()
    THIN_PRINT = auto()
    FAT_PRINT = auto()
    FADING_MOMENTUM = auto()
    BID_ASK_FADE = auto()


@dataclass
class ExhaustionSignal:
    """Detected exhaustion event."""
    bar_type: ExhaustionType
    direction: int          # +1 = bullish (sellers exhausted), -1 = bearish (buyers exhausted)
    price: float            # Price level of exhaustion
    strength: float         # 0-1 normalized strength
    detail: str             # Human-readable description


# Cooldown state per sub-type (EXH-08)
_cooldown: dict[ExhaustionType, int] = {}


def reset_cooldowns() -> None:
    """Reset all cooldown counters (session start)."""
    _cooldown.clear()


def _check_cooldown(etype: ExhaustionType, bar_index: int, cooldown_bars: int) -> bool:
    """Return True if this sub-type is allowed to fire (not in cooldown)."""
    last_fired = _cooldown.get(etype, -999)
    return (bar_index - last_fired) >= cooldown_bars


def _set_cooldown(etype: ExhaustionType, bar_index: int) -> None:
    """Record that this sub-type fired at bar_index."""
    _cooldown[etype] = bar_index


def _delta_trajectory_gate(bar: FootprintBar, config: ExhaustionConfig) -> bool:
    """Universal delta trajectory divergence gate for exhaustion signals (EXH-07).

    Returns True if the gate PASSES (signal allowed to fire).

    Exhaustion only fires when cumulative delta is fading relative to price
    direction — i.e., the aggressor is running out of steam:
      - Bullish bar (close > open) + negative delta: buyers pushed price up
        but sellers are winning on delta — buyer exhaustion confirmed.
      - Bearish bar (close < open) + positive delta: sellers pushed price down
        but buyers are winning on delta — seller exhaustion confirmed.

    If delta is too small (< delta_gate_min_ratio), the gate does not block
    because tiny delta is noise, not meaningful confirmation.

    Per T-02-03: O(1) cost — safe to call on every bar.
    """
    if not config.delta_gate_enabled:
        return True

    if bar.total_vol == 0:
        return True

    delta_ratio = abs(bar.bar_delta) / bar.total_vol
    if delta_ratio < config.delta_gate_min_ratio:
        # Delta too small to be meaningful — don't block
        return True

    if bar.close > bar.open:
        # Bullish bar: gate passes only if delta is negative (buyers fading)
        return bar.bar_delta < 0
    elif bar.close < bar.open:
        # Bearish bar: gate passes only if delta is positive (sellers fading)
        return bar.bar_delta > 0
    else:
        # Doji (close == open): no directional context — allow
        return True


def detect_exhaustion(
    bar: FootprintBar,
    prior_bar: Optional[FootprintBar] = None,
    bar_index: int = 0,
    atr: float = 15.0,
    config: ExhaustionConfig | None = None,
) -> list[ExhaustionSignal]:
    """Detect all exhaustion variants in a single bar.

    Args:
        bar: Finalized FootprintBar
        prior_bar: Previous bar (needed for bid/ask fade comparison)
        bar_index: Current bar index (for cooldown tracking)
        atr: Current ATR(20) for adaptive thresholds (runtime value)
        config: ExhaustionConfig with all tunable thresholds. If None, uses
                defaults — fully backward compatible with callers that omit config.

    Returns:
        List of ExhaustionSignal (usually 0-2 per bar)
    """
    # Use provided config or create default (backward compat — D-02)
    cfg = config if config is not None else ExhaustionConfig()

    signals: list[ExhaustionSignal] = []

    if not bar.levels or bar.total_vol == 0:
        return signals

    sorted_ticks = sorted(bar.levels.keys())
    if len(sorted_ticks) < 2:
        return signals

    max_level_vol = max(
        lv.ask_vol + lv.bid_vol for lv in bar.levels.values()
    )
    avg_level_vol = bar.total_vol / len(bar.levels) if bar.levels else 1

    body_top = max(bar.open, bar.close)
    body_bot = min(bar.open, bar.close)

    # --- 1. ZERO PRINT (EXH-01) — GATE EXEMPT ---
    # Structural gap: price level within bar body with 0 volume on both sides.
    # Zero prints exist regardless of delta — do NOT apply the delta gate here.
    if _check_cooldown(ExhaustionType.ZERO_PRINT, bar_index, cfg.cooldown_bars):
        for tick in sorted_ticks:
            px = tick_to_price(tick)
            level = bar.levels[tick]
            if level.ask_vol == 0 and level.bid_vol == 0 and body_bot < px < body_top:
                direction = +1 if bar.close > bar.open else -1
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.ZERO_PRINT,
                    direction=direction,
                    price=px,
                    strength=0.6,
                    detail=f"ZERO PRINT at {px:.2f} — price must revisit",
                ))
                _set_cooldown(ExhaustionType.ZERO_PRINT, bar_index)
                break  # One zero print signal per bar

    # --- UNIVERSAL DELTA TRAJECTORY GATE (EXH-07 / D-08) ---
    # Check AFTER zero print, BEFORE variants 2-6.
    # If gate fails, return only zero print signals (if any).
    if not _delta_trajectory_gate(bar, cfg):
        return signals

    # --- 2. EXHAUSTION PRINT (EXH-02) ---
    # High single-side volume at bar extreme, no follow-through
    if _check_cooldown(ExhaustionType.EXHAUSTION_PRINT, bar_index, cfg.cooldown_bars):
        # Check bar high — buyers exhausted if heavy ask vol at top
        high_tick = sorted_ticks[-1]
        high_level = bar.levels[high_tick]
        if high_level.ask_vol > 0:
            high_pct = (high_level.ask_vol / bar.total_vol) * 100
            eff_min = cfg.exhaust_wick_min * (1.2 if bar.bar_range > atr * 1.5 else 1.0)
            if high_pct >= eff_min / 3:  # Lower threshold since it's a single level
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.EXHAUSTION_PRINT,
                    direction=-1,  # Bearish — buyers exhausted at high
                    price=tick_to_price(high_tick),
                    strength=min(high_pct / 20.0, 1.0),
                    detail=f"EXHAUSTION PRINT at high {tick_to_price(high_tick):.2f}: "
                           f"ask_vol={high_level.ask_vol} ({high_pct:.1f}% of total)",
                ))
                _set_cooldown(ExhaustionType.EXHAUSTION_PRINT, bar_index)

        # Check bar low — sellers exhausted if heavy bid vol at bottom
        low_tick = sorted_ticks[0]
        low_level = bar.levels[low_tick]
        if low_level.bid_vol > 0:
            low_pct = (low_level.bid_vol / bar.total_vol) * 100
            if low_pct >= cfg.exhaust_wick_min / 3:
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.EXHAUSTION_PRINT,
                    direction=+1,  # Bullish — sellers exhausted at low
                    price=tick_to_price(low_tick),
                    strength=min(low_pct / 20.0, 1.0),
                    detail=f"EXHAUSTION PRINT at low {tick_to_price(low_tick):.2f}: "
                           f"bid_vol={low_level.bid_vol} ({low_pct:.1f}% of total)",
                ))
                _set_cooldown(ExhaustionType.EXHAUSTION_PRINT, bar_index)

    # --- 3. THIN PRINT (EXH-03) ---
    # Volume at price row < 5% of bar's max — confirms fast move through
    if _check_cooldown(ExhaustionType.THIN_PRINT, bar_index, cfg.cooldown_bars):
        thin_count = 0
        for tick in sorted_ticks:
            px = tick_to_price(tick)
            level = bar.levels[tick]
            vol = level.ask_vol + level.bid_vol
            if body_bot <= px <= body_top and max_level_vol > 0:
                if vol < max_level_vol * cfg.thin_pct:
                    thin_count += 1

        if thin_count >= 3:  # At least 3 thin levels = confirmed fast move
            direction = +1 if bar.close > bar.open else -1
            signals.append(ExhaustionSignal(
                bar_type=ExhaustionType.THIN_PRINT,
                direction=direction,
                price=(bar.high + bar.low) / 2,
                strength=min(thin_count / 7.0, 1.0),
                detail=f"THIN PRINT: {thin_count} levels < {cfg.thin_pct*100:.0f}% max vol — fast move",
            ))
            _set_cooldown(ExhaustionType.THIN_PRINT, bar_index)

    # --- 4. FAT PRINT (EXH-04) ---
    # Volume at price row > threshold × average — strong acceptance level (future S/R)
    if _check_cooldown(ExhaustionType.FAT_PRINT, bar_index, cfg.cooldown_bars):
        for tick in sorted_ticks:
            level = bar.levels[tick]
            vol = level.ask_vol + level.bid_vol
            if vol > avg_level_vol * cfg.fat_mult:
                px = tick_to_price(tick)
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.FAT_PRINT,
                    direction=0,  # Neutral — acceptance, not directional
                    price=px,
                    strength=min(vol / (avg_level_vol * cfg.fat_mult * 2), 1.0),
                    detail=f"FAT PRINT at {px:.2f}: vol={vol} ({vol/avg_level_vol:.1f}x avg) — "
                           f"strong acceptance / future S/R",
                ))
                _set_cooldown(ExhaustionType.FAT_PRINT, bar_index)
                break  # One fat print per bar (the fattest)

    # --- 5. FADING MOMENTUM (EXH-05) ---
    # Delta trajectory diverges from price — requires E8 CVD engine (Phase 3)
    # Stub: will be implemented when E8 CVD engine provides linear regression slope
    # For now, simple version: bar delta opposes bar direction.
    # The universal gate already confirmed delta divergence; keep the 0.15 threshold
    # here as a STRONGER requirement — pronounced divergence, not just any fading.
    if _check_cooldown(ExhaustionType.FADING_MOMENTUM, bar_index, cfg.cooldown_bars):
        if bar.bar_range > 0:
            bar_bullish = bar.close > bar.open
            # Universal gate already confirmed delta_opposes — check stronger threshold
            if abs(bar.bar_delta) > bar.total_vol * 0.15:
                direction = -1 if bar_bullish else +1
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.FADING_MOMENTUM,
                    direction=direction,
                    price=bar.close,
                    strength=min(abs(bar.bar_delta) / bar.total_vol, 1.0),
                    detail=f"FADING MOMENTUM: price {'up' if bar_bullish else 'down'} "
                           f"but delta={bar.bar_delta:+d} opposes — aggression fading",
                ))
                _set_cooldown(ExhaustionType.FADING_MOMENTUM, bar_index)

    # --- 6. BID/ASK FADE (EXH-06) ---
    # Ask volume at bar extreme < 60% of prior bar's ask at same relative position
    if (prior_bar and prior_bar.levels
            and _check_cooldown(ExhaustionType.BID_ASK_FADE, bar_index, cfg.cooldown_bars)):

        # Compare ask at current high vs prior bar's high
        curr_high_tick = sorted_ticks[-1]
        curr_high_ask = bar.levels[curr_high_tick].ask_vol

        prior_sorted = sorted(prior_bar.levels.keys())
        if prior_sorted:
            prior_high_tick = prior_sorted[-1]
            prior_high_ask = prior_bar.levels[prior_high_tick].ask_vol

            if prior_high_ask > 0 and curr_high_ask < prior_high_ask * cfg.fade_threshold:
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.BID_ASK_FADE,
                    direction=-1,  # Bearish — buyers fading at highs
                    price=tick_to_price(curr_high_tick),
                    strength=1.0 - (curr_high_ask / prior_high_ask if prior_high_ask > 0 else 0),
                    detail=f"ASK FADE at high: curr={curr_high_ask} vs prior={prior_high_ask} "
                           f"({curr_high_ask/prior_high_ask*100:.0f}% — below {cfg.fade_threshold*100:.0f}%)",
                ))
                _set_cooldown(ExhaustionType.BID_ASK_FADE, bar_index)

            # Compare bid at current low vs prior bar's low
            curr_low_tick = sorted_ticks[0]
            curr_low_bid = bar.levels[curr_low_tick].bid_vol
            prior_low_tick = prior_sorted[0]
            prior_low_bid = prior_bar.levels[prior_low_tick].bid_vol

            if prior_low_bid > 0 and curr_low_bid < prior_low_bid * cfg.fade_threshold:
                signals.append(ExhaustionSignal(
                    bar_type=ExhaustionType.BID_ASK_FADE,
                    direction=+1,  # Bullish — sellers fading at lows
                    price=tick_to_price(curr_low_tick),
                    strength=1.0 - (curr_low_bid / prior_low_bid if prior_low_bid > 0 else 0),
                    detail=f"BID FADE at low: curr={curr_low_bid} vs prior={prior_low_bid} "
                           f"({curr_low_bid/prior_low_bid*100:.0f}% — below {cfg.fade_threshold*100:.0f}%)",
                ))
                _set_cooldown(ExhaustionType.BID_ASK_FADE, bar_index)

    return signals
