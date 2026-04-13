"""E1a: Absorption signal detection — 4 variants.

ABSORPTION is the highest-alpha reversal signal in order flow.
It detects passive limit orders absorbing aggressive market orders
without price movement — the strongest sign of institutional defense.

Variants (per ABS-01..04):
  1. Classic:      Wick has high volume + balanced delta (both sides active)
  2. Passive:      High volume concentrates at price extreme while price holds
  3. Stopping Vol: POC falls in wick + volume exceeds ATR-scaled peak threshold
  4. Effort/Result: High volume + narrow range (effort without result)

All thresholds are ATR-adaptive (ARCH-03, SCOR-05).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from deep6.state.footprint import FootprintBar, tick_to_price, price_to_tick


class AbsorptionType(Enum):
    CLASSIC = auto()
    PASSIVE = auto()
    STOPPING_VOLUME = auto()
    EFFORT_VS_RESULT = auto()


@dataclass
class AbsorptionSignal:
    """Detected absorption event."""
    bar_type: AbsorptionType
    direction: int          # +1 = bullish (sellers absorbed), -1 = bearish (buyers absorbed)
    price: float            # Price level of absorption
    wick: str               # "upper" or "lower"
    strength: float         # 0-1 normalized strength
    wick_pct: float         # Wick volume as % of total
    delta_ratio: float      # |delta| / volume in the wick zone
    detail: str             # Human-readable description


def detect_absorption(
    bar: FootprintBar,
    atr: float = 15.0,
    absorb_wick_min: float = 30.0,
    absorb_delta_max: float = 0.12,
    passive_extreme_pct: float = 0.20,
    passive_vol_pct: float = 0.60,
    stop_vol_mult: float = 2.0,
    evr_vol_mult: float = 1.5,
    evr_range_cap: float = 0.30,
    vol_ema: float = 500.0,
) -> list[AbsorptionSignal]:
    """Detect all absorption variants in a single bar.

    Args:
        bar: Finalized FootprintBar with levels populated
        atr: Current ATR(20) value for adaptive thresholds
        absorb_wick_min: Min wick volume % for classic absorption
        absorb_delta_max: Max |delta|/volume ratio for balanced wick
        passive_extreme_pct: Top/bottom % of range to check for passive absorption
        passive_vol_pct: Min % of total volume in extreme zone for passive
        stop_vol_mult: Volume must exceed this × vol_ema for stopping volume
        evr_vol_mult: Volume must exceed this × vol_ema for effort vs result
        evr_range_cap: Max bar range as fraction of ATR for effort vs result
        vol_ema: Running average volume for comparison

    Returns:
        List of AbsorptionSignal (usually 0 or 1 per bar; rarely 2)
    """
    signals: list[AbsorptionSignal] = []

    if not bar.levels or bar.total_vol == 0 or bar.bar_range == 0:
        return signals

    # Compute wick zones
    body_top = max(bar.open, bar.close)
    body_bot = min(bar.open, bar.close)

    upper_wick_vol = 0
    upper_wick_delta = 0
    lower_wick_vol = 0
    lower_wick_delta = 0
    body_vol = 0

    for tick, level in bar.levels.items():
        px = tick_to_price(tick)
        vol = level.ask_vol + level.bid_vol
        delta = level.ask_vol - level.bid_vol

        if px > body_top:
            upper_wick_vol += vol
            upper_wick_delta += delta
        elif px < body_bot:
            lower_wick_vol += vol
            lower_wick_delta += delta
        else:
            body_vol += vol

    total = bar.total_vol

    # --- 1. CLASSIC ABSORPTION (ABS-01) ---
    # Wick has high volume + balanced delta (both sides active = absorption)
    for wick_name, wick_vol, wick_delta, direction in [
        ("upper", upper_wick_vol, upper_wick_delta, -1),  # Upper wick absorption = bearish
        ("lower", lower_wick_vol, lower_wick_delta, +1),  # Lower wick absorption = bullish
    ]:
        if wick_vol == 0:
            continue
        wick_pct = (wick_vol / total) * 100
        delta_ratio = abs(wick_delta) / wick_vol if wick_vol > 0 else 1.0

        # Scale thresholds with ATR
        eff_wick_min = absorb_wick_min * (1.2 if bar.bar_range > atr * 1.5 else 1.0)

        if wick_pct >= eff_wick_min and delta_ratio < absorb_delta_max:
            strength = min(wick_pct / 60.0, 1.0) * (1.0 - delta_ratio / absorb_delta_max)
            signals.append(AbsorptionSignal(
                bar_type=AbsorptionType.CLASSIC,
                direction=direction,
                price=bar.low if wick_name == "lower" else bar.high,
                wick=wick_name,
                strength=strength,
                wick_pct=wick_pct,
                delta_ratio=delta_ratio,
                detail=f"CLASSIC {'BULL' if direction > 0 else 'BEAR'} ABSORB: "
                       f"wick={wick_pct:.1f}% delta_ratio={delta_ratio:.3f}",
            ))

    # --- 2. PASSIVE ABSORPTION (ABS-02) ---
    # High volume concentrates at price extreme while price holds
    if bar.bar_range > 0:
        extreme_range = bar.bar_range * passive_extreme_pct
        top_zone_vol = 0
        bot_zone_vol = 0

        for tick, level in bar.levels.items():
            px = tick_to_price(tick)
            vol = level.ask_vol + level.bid_vol
            if px >= bar.high - extreme_range:
                top_zone_vol += vol
            if px <= bar.low + extreme_range:
                bot_zone_vol += vol

        # Top zone passive: heavy volume at top but price didn't break higher
        if top_zone_vol / total >= passive_vol_pct and bar.close < bar.high - extreme_range:
            signals.append(AbsorptionSignal(
                bar_type=AbsorptionType.PASSIVE,
                direction=-1,  # Bearish — passive sellers at top
                price=bar.high,
                wick="upper",
                strength=min(top_zone_vol / total, 1.0),
                wick_pct=(top_zone_vol / total) * 100,
                delta_ratio=0.0,
                detail=f"PASSIVE BEAR ABSORB: {top_zone_vol/total*100:.1f}% vol at top 20%",
            ))

        # Bottom zone passive: heavy volume at bottom but price didn't break lower
        if bot_zone_vol / total >= passive_vol_pct and bar.close > bar.low + extreme_range:
            signals.append(AbsorptionSignal(
                bar_type=AbsorptionType.PASSIVE,
                direction=+1,  # Bullish — passive buyers at bottom
                price=bar.low,
                wick="lower",
                strength=min(bot_zone_vol / total, 1.0),
                wick_pct=(bot_zone_vol / total) * 100,
                delta_ratio=0.0,
                detail=f"PASSIVE BULL ABSORB: {bot_zone_vol/total*100:.1f}% vol at bottom 20%",
            ))

    # --- 3. STOPPING VOLUME (ABS-03) ---
    # POC falls in wick + volume exceeds ATR-scaled peak threshold
    if bar.total_vol > vol_ema * stop_vol_mult:
        poc_in_upper_wick = bar.poc_price > body_top
        poc_in_lower_wick = bar.poc_price < body_bot

        if poc_in_upper_wick:
            signals.append(AbsorptionSignal(
                bar_type=AbsorptionType.STOPPING_VOLUME,
                direction=-1,  # Bearish — stopping at top
                price=bar.poc_price,
                wick="upper",
                strength=min(bar.total_vol / (vol_ema * stop_vol_mult * 2), 1.0),
                wick_pct=(upper_wick_vol / total) * 100 if total > 0 else 0,
                delta_ratio=0.0,
                detail=f"STOPPING VOL BEAR: POC={bar.poc_price:.2f} in upper wick, "
                       f"vol={bar.total_vol} ({bar.total_vol/vol_ema:.1f}x avg)",
            ))
        elif poc_in_lower_wick:
            signals.append(AbsorptionSignal(
                bar_type=AbsorptionType.STOPPING_VOLUME,
                direction=+1,  # Bullish — stopping at bottom
                price=bar.poc_price,
                wick="lower",
                strength=min(bar.total_vol / (vol_ema * stop_vol_mult * 2), 1.0),
                wick_pct=(lower_wick_vol / total) * 100 if total > 0 else 0,
                delta_ratio=0.0,
                detail=f"STOPPING VOL BULL: POC={bar.poc_price:.2f} in lower wick, "
                       f"vol={bar.total_vol} ({bar.total_vol/vol_ema:.1f}x avg)",
            ))

    # --- 4. EFFORT VS RESULT (ABS-04) ---
    # High volume + narrow range (lots of effort, no price movement)
    if (bar.total_vol > vol_ema * evr_vol_mult
            and atr > 0
            and bar.bar_range < atr * evr_range_cap):
        # Direction based on delta
        direction = +1 if bar.bar_delta < 0 else -1  # Negative delta + narrow = bull absorb
        signals.append(AbsorptionSignal(
            bar_type=AbsorptionType.EFFORT_VS_RESULT,
            direction=direction,
            price=(bar.high + bar.low) / 2,
            wick="body",
            strength=min(bar.total_vol / (vol_ema * evr_vol_mult * 2), 1.0),
            wick_pct=0.0,
            delta_ratio=abs(bar.bar_delta) / bar.total_vol if bar.total_vol > 0 else 0,
            detail=f"EFFORT VS RESULT: vol={bar.total_vol} ({bar.total_vol/vol_ema:.1f}x avg) "
                   f"range={bar.bar_range:.2f} ({bar.bar_range/atr*100:.0f}% ATR)",
        ))

    return signals
