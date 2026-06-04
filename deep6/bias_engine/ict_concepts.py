"""ICT concept detectors — algorithmic implementations of advanced ICT patterns.

Algorithms:
  OrderBlockDetector     — Finds bullish/bearish order blocks from OHLCV
  FairValueGapDetector   — 3-candle FVG with displacement filter
  BreakOfStructure       — BOS and CHoCH detection
  LiquidityPoolTracker   — Equal highs/lows (external liquidity)
  OTECalculator          — Optimal Trade Entry (61.8–79% Fibonacci retracement)
  IPDALevels             — Interbank Price Delivery 20/40/60-day lookback levels
  PDArray                — Premium/Discount array scoring from all ICT levels

Each detector is stateless — call with a DataFrame of OHLCV bars.
For live bar-by-bar use, the caller maintains the rolling window.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Shared types
# ──────────────────────────────────────────────────────────────────────────────

class ICTDirection(int, Enum):
    BULL =  1
    BEAR = -1
    NONE =  0


@dataclass
class PriceZone:
    """A price region with directional bias."""
    high: float
    low: float
    direction: ICTDirection
    label: str
    strength: float = 1.0          # 0-1 relative importance
    mitigated: bool = False        # True when price has entered the zone
    bar_index: int = 0             # Bar when zone was created


# ──────────────────────────────────────────────────────────────────────────────
# 1. Order Block Detector
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class OrderBlock(PriceZone):
    """ICT Order Block — the last opposite-color candle before a move.

    Bull OB: Last bearish candle before a bullish impulse (BOS up).
    Bear OB: Last bullish candle before a bearish impulse (BOS down).
    """
    candle_body_high: float = 0.0
    candle_body_low: float = 0.0


def detect_order_blocks(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    lookback: int = 50,
    min_displacement: float = 2.0,    # minimum ATR multiples for impulse
    atr: float = 15.0,
) -> list[OrderBlock]:
    """Find bullish and bearish order blocks in recent price data.

    Algorithm:
    1. Find impulse moves (body >= min_displacement * atr_per_bar)
    2. Walk back to find the last opposite-color candle before the impulse
    3. That candle's range is the order block
    """
    n = len(closes)
    if n < 3:
        return []

    start = max(0, n - lookback)
    blocks: list[OrderBlock] = []
    min_move = min_displacement * (atr / 10)  # scale to per-candle

    for i in range(start + 2, n):
        body = abs(closes[i] - opens[i])
        if body < min_move:
            continue

        bull_impulse = closes[i] > opens[i] and closes[i] > highs[i - 1]
        bear_impulse = closes[i] < opens[i] and closes[i] < lows[i - 1]

        if bull_impulse:
            # Find last bearish candle before this impulse
            for j in range(i - 1, max(start, i - 10), -1):
                if closes[j] < opens[j]:  # bearish candle
                    ob = OrderBlock(
                        high=highs[j],
                        low=lows[j],
                        direction=ICTDirection.BULL,
                        label=f"Bull OB @{lows[j]:.2f}–{highs[j]:.2f}",
                        strength=min(body / atr, 1.0),
                        bar_index=j,
                        candle_body_high=max(opens[j], closes[j]),
                        candle_body_low=min(opens[j], closes[j]),
                    )
                    blocks.append(ob)
                    break

        elif bear_impulse:
            for j in range(i - 1, max(start, i - 10), -1):
                if closes[j] > opens[j]:  # bullish candle
                    ob = OrderBlock(
                        high=highs[j],
                        low=lows[j],
                        direction=ICTDirection.BEAR,
                        label=f"Bear OB @{lows[j]:.2f}–{highs[j]:.2f}",
                        strength=min(body / atr, 1.0),
                        bar_index=j,
                        candle_body_high=max(opens[j], closes[j]),
                        candle_body_low=min(opens[j], closes[j]),
                    )
                    blocks.append(ob)
                    break

    # Deduplicate: keep strongest per price region
    return _dedup_zones(blocks)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Fair Value Gap Detector
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class FairValueGap(PriceZone):
    """3-candle imbalance: candle[0].low > candle[2].high (bull)
    or candle[0].high < candle[2].low (bear).

    Displacement filter: the middle candle body must be >= displacement_filter
    to exclude minor gaps.
    """
    gap_size: float = 0.0          # gap size in price points
    equilibrium: float = 0.0      # midpoint (50% of gap)


def detect_fvgs(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    opens: list[float],
    lookback: int = 30,
    displacement_filter: float = 5.0,   # minimum gap size in points
    mitigate_on_close: bool = True,
) -> list[FairValueGap]:
    """Detect Fair Value Gaps with displacement filter."""
    n = len(closes)
    if n < 3:
        return []

    start = max(0, n - lookback)
    gaps: list[FairValueGap] = []
    current_close = closes[-1]

    for i in range(start + 2, n):
        # Bullish FVG: gap between candle[i-2].high and candle[i].low
        if lows[i] > highs[i - 2]:
            gap = lows[i] - highs[i - 2]
            if gap >= displacement_filter:
                mitigated = mitigate_on_close and current_close <= lows[i]
                eq = highs[i - 2] + gap / 2.0
                gaps.append(FairValueGap(
                    high=lows[i],
                    low=highs[i - 2],
                    direction=ICTDirection.BULL,
                    label=f"Bull FVG @{highs[i-2]:.2f}–{lows[i]:.2f}",
                    strength=min(gap / 20.0, 1.0),
                    mitigated=mitigated,
                    bar_index=i - 1,
                    gap_size=gap,
                    equilibrium=eq,
                ))

        # Bearish FVG: gap between candle[i-2].low and candle[i].high
        elif highs[i] < lows[i - 2]:
            gap = lows[i - 2] - highs[i]
            if gap >= displacement_filter:
                mitigated = mitigate_on_close and current_close >= highs[i]
                eq = highs[i] + gap / 2.0
                gaps.append(FairValueGap(
                    high=lows[i - 2],
                    low=highs[i],
                    direction=ICTDirection.BEAR,
                    label=f"Bear FVG @{highs[i]:.2f}–{lows[i-2]:.2f}",
                    strength=min(gap / 20.0, 1.0),
                    mitigated=mitigated,
                    bar_index=i - 1,
                    gap_size=gap,
                    equilibrium=eq,
                ))

    return [g for g in gaps if not g.mitigated]


# ──────────────────────────────────────────────────────────────────────────────
# 3. Break of Structure / Change of Character
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StructureBreak:
    """BOS or CHoCH signal."""
    bar_index: int
    price: float
    direction: ICTDirection      # direction of the break (+1 = bullish BOS)
    is_choch: bool               # True = Change of Character (first reversal)
    is_bos: bool                 # True = Break of Structure (continuation)
    label: str = ""
    strength: float = 1.0


def detect_structure_breaks(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    swing_lookback: int = 5,
    lookback: int = 50,
) -> list[StructureBreak]:
    """Detect BOS (continuation) and CHoCH (reversal) signals.

    Algorithm:
    1. Find swing highs/lows using left/right lookback
    2. A bullish BOS occurs when price closes above the most recent swing high
    3. A bearish CHoCH occurs when price closes below the most recent swing low
       after a series of higher highs (trend reversal)
    """
    n = len(closes)
    if n < swing_lookback * 2 + 1:
        return []

    start = max(0, n - lookback)
    breaks: list[StructureBreak] = []

    # Find swing points
    swing_highs: list[tuple[int, float]] = []  # (bar_index, price)
    swing_lows: list[tuple[int, float]] = []

    for i in range(start + swing_lookback, n - swing_lookback):
        # Swing high: highest in [i-lb, i+lb]
        window_h = highs[i - swing_lookback:i + swing_lookback + 1]
        if highs[i] == max(window_h):
            swing_highs.append((i, highs[i]))

        # Swing low: lowest in [i-lb, i+lb]
        window_l = lows[i - swing_lookback:i + swing_lookback + 1]
        if lows[i] == min(window_l):
            swing_lows.append((i, lows[i]))

    if not swing_highs or not swing_lows:
        return []

    # Detect breaks on recent bars
    for i in range(start + swing_lookback + 1, n):
        # Bullish BOS: close above most recent swing high
        recent_sh = [sh for sh in swing_highs if sh[0] < i]
        recent_sl = [sl for sl in swing_lows if sl[0] < i]

        if recent_sh:
            last_sh_price = recent_sh[-1][1]
            if closes[i] > last_sh_price:
                # CHoCH if prior trend was bearish (lower highs)
                is_choch = (
                    len(recent_sh) >= 2
                    and recent_sh[-1][1] < recent_sh[-2][1]
                )
                breaks.append(StructureBreak(
                    bar_index=i,
                    price=last_sh_price,
                    direction=ICTDirection.BULL,
                    is_choch=is_choch,
                    is_bos=not is_choch,
                    label=f"{'CHoCH' if is_choch else 'BOS'} Bull @{last_sh_price:.2f}",
                    strength=abs(closes[i] - last_sh_price) / 20.0,
                ))

        if recent_sl:
            last_sl_price = recent_sl[-1][1]
            if closes[i] < last_sl_price:
                is_choch = (
                    len(recent_sl) >= 2
                    and recent_sl[-1][1] > recent_sl[-2][1]
                )
                breaks.append(StructureBreak(
                    bar_index=i,
                    price=last_sl_price,
                    direction=ICTDirection.BEAR,
                    is_choch=is_choch,
                    is_bos=not is_choch,
                    label=f"{'CHoCH' if is_choch else 'BOS'} Bear @{last_sl_price:.2f}",
                    strength=abs(closes[i] - last_sl_price) / 20.0,
                ))

    # Return most recent unique breaks
    seen: set[tuple[int, int]] = set()
    unique: list[StructureBreak] = []
    for b in reversed(breaks[-20:]):
        key = (b.bar_index, int(b.direction))
        if key not in seen:
            seen.add(key)
            unique.append(b)
    return list(reversed(unique))


# ──────────────────────────────────────────────────────────────────────────────
# 4. Liquidity Pool Tracker
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LiquidityPool:
    """Equal highs or equal lows — external liquidity resting above/below."""
    price: float
    direction: ICTDirection    # BULL = buyside liq above, BEAR = sellside below
    equal_count: int           # how many equal swing points
    label: str = ""
    swept: bool = False


def detect_liquidity_pools(
    highs: list[float],
    lows: list[float],
    tolerance_ticks: float = 2.0,    # NQ: 2 ticks = 0.5 pts
    min_count: int = 2,
    lookback: int = 60,
) -> list[LiquidityPool]:
    """Find equal highs (buyside liquidity) and equal lows (sellside liquidity).

    Equal highs cluster → stops resting above → sweep target.
    Equal lows cluster → stops resting below → sweep target.
    """
    n = len(highs)
    start = max(0, n - lookback)
    pools: list[LiquidityPool] = []
    tol = tolerance_ticks * 0.25  # NQ tick size = 0.25

    # Find swing highs / lows (simplified)
    swing_h: list[float] = []
    swing_l: list[float] = []
    for i in range(start + 2, n - 2):
        if highs[i] >= max(highs[i-2:i]) and highs[i] >= max(highs[i+1:i+3]):
            swing_h.append(highs[i])
        if lows[i] <= min(lows[i-2:i]) and lows[i] <= min(lows[i+1:i+3]):
            swing_l.append(lows[i])

    # Cluster equal highs
    for h in _cluster_levels(swing_h, tol):
        count = sum(1 for x in swing_h if abs(x - h) <= tol)
        if count >= min_count:
            pools.append(LiquidityPool(
                price=h,
                direction=ICTDirection.BULL,
                equal_count=count,
                label=f"BSL @{h:.2f} ({count}x)",
            ))

    # Cluster equal lows
    for l in _cluster_levels(swing_l, tol):
        count = sum(1 for x in swing_l if abs(x - l) <= tol)
        if count >= min_count:
            pools.append(LiquidityPool(
                price=l,
                direction=ICTDirection.BEAR,
                equal_count=count,
                label=f"SSL @{l:.2f} ({count}x)",
            ))

    return pools


# ──────────────────────────────────────────────────────────────────────────────
# 5. Optimal Trade Entry (OTE) Calculator
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class OTEZone:
    """ICT Optimal Trade Entry — 61.8% to 79% Fibonacci retracement of a swing.

    For bull setups: swing from low to high, OTE is 61.8–79% retracement
    For bear setups: swing from high to low, OTE is 61.8–79% retracement
    """
    fib_618: float        # 61.8% retracement level
    fib_705: float        # 70.5% level (ICT's favorite)
    fib_79: float         # 79% retracement level
    swing_high: float
    swing_low: float
    direction: ICTDirection
    label: str = ""


def calculate_ote(
    swing_high: float,
    swing_low: float,
    direction: ICTDirection,
) -> OTEZone:
    """Calculate OTE zone for a given swing.

    Bull OTE (buy zone): price retraces 61.8–79% from low → high swing
    Bear OTE (sell zone): price retraces 61.8–79% from high → low swing
    """
    rng = swing_high - swing_low

    if direction == ICTDirection.BULL:
        # Retracement from high: price dips into 61.8–79% of the up-move
        fib_618 = swing_high - rng * 0.618
        fib_705 = swing_high - rng * 0.705
        fib_79  = swing_high - rng * 0.79
        lbl = f"Bull OTE {fib_79:.2f}–{fib_618:.2f}"
    else:
        # Retracement from low: price pops into 61.8–79% of the down-move
        fib_618 = swing_low + rng * 0.618
        fib_705 = swing_low + rng * 0.705
        fib_79  = swing_low + rng * 0.79
        lbl = f"Bear OTE {fib_618:.2f}–{fib_79:.2f}"

    return OTEZone(
        fib_618=fib_618,
        fib_705=fib_705,
        fib_79=fib_79,
        swing_high=swing_high,
        swing_low=swing_low,
        direction=direction,
        label=lbl,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 6. IPDA Levels (Interbank Price Delivery Algorithm)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class IPDALevel:
    """IPDA lookback level — high or low from the past N trading days.

    ICT's IPDA uses 20, 40, and 60 trading-day lookbacks. These levels
    represent where institutional algorithms are programmed to deliver price.
    """
    price: float
    lookback_days: int      # 20, 40, or 60
    direction: ICTDirection  # BULL = old low (buy-side target), BEAR = old high
    label: str = ""
    swept: bool = False


def calculate_ipda_levels(
    daily_highs: list[float],
    daily_lows: list[float],
    lookbacks: list[int] = None,
) -> list[IPDALevel]:
    """Calculate IPDA 20/40/60-day lookback levels from daily OHLC data.

    These are the highest-timeframe levels where price is "programmed" to go.
    """
    if lookbacks is None:
        lookbacks = [20, 40, 60]

    n = len(daily_highs)
    levels: list[IPDALevel] = []

    for lb in lookbacks:
        if n < lb:
            continue
        window_h = daily_highs[-lb:]
        window_l = daily_lows[-lb:]

        hi = max(window_h)
        lo = min(window_l)

        levels.append(IPDALevel(
            price=hi,
            lookback_days=lb,
            direction=ICTDirection.BEAR,
            label=f"IPDA {lb}D High @{hi:.2f}",
        ))
        levels.append(IPDALevel(
            price=lo,
            lookback_days=lb,
            direction=ICTDirection.BULL,
            label=f"IPDA {lb}D Low @{lo:.2f}",
        ))

    return sorted(levels, key=lambda x: x.price, reverse=True)


# ──────────────────────────────────────────────────────────────────────────────
# 7. PD Array Scorer — Premium / Discount with full ICT level stack
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PDArrayScore:
    """Premium / Discount Array scoring from all ICT levels.

    Combines: FVGs, OBs, IPDA levels, Asia EQ, PD EQ, OTE zone
    into a single -100..+100 bias score.
    """
    score: float                   # -100 (deep premium) to +100 (deep discount)
    nearest_bull_zone: Optional[str] = None   # nearest support label
    nearest_bear_zone: Optional[str] = None   # nearest resistance label
    in_ote_zone: bool = False
    at_ob: bool = False
    at_fvg: bool = False
    at_ipda: bool = False
    detail: str = ""


def score_pd_array(
    current_price: float,
    fvgs: list[FairValueGap],
    order_blocks: list[OrderBlock],
    ipda_levels: list[IPDALevel],
    range_high: float,              # e.g., PDH or session high
    range_low: float,               # e.g., PDL or session low
    ote_zone: Optional[OTEZone] = None,
    proximity_pts: float = 10.0,    # NQ: within 10 pts = "at a level"
) -> PDArrayScore:
    """Score where current price sits in the full ICT premium/discount array."""
    if range_high == range_low:
        return PDArrayScore(score=0.0, detail="No range defined")

    # Base score: where price sits in the range (100 = at low, -100 = at high)
    pct = (current_price - range_low) / (range_high - range_low)
    base_score = (0.5 - pct) * 200    # +100 at low, -100 at high

    bonus = 0.0
    flags: list[str] = []

    # OTE zone presence
    in_ote = False
    if ote_zone:
        lo, hi = sorted([ote_zone.fib_618, ote_zone.fib_79])
        if lo <= current_price <= hi:
            in_ote = True
            mult = 1.0 if ote_zone.direction == ICTDirection.BULL else -1.0
            bonus += 20.0 * mult
            flags.append(f"OTE {ote_zone.label}")

    # Order block presence
    at_ob = False
    for ob in order_blocks[-5:]:
        if abs(current_price - ob.low) <= proximity_pts or ob.low <= current_price <= ob.high:
            at_ob = True
            bonus += 15.0 * float(ob.direction.value)
            flags.append(ob.label)
            break

    # FVG presence
    at_fvg = False
    for fvg in fvgs[-5:]:
        if fvg.low <= current_price <= fvg.high:
            at_fvg = True
            bonus += 10.0 * float(fvg.direction.value)
            flags.append(fvg.label)
            break

    # IPDA level proximity
    at_ipda = False
    for lvl in ipda_levels:
        if abs(current_price - lvl.price) <= proximity_pts:
            at_ipda = True
            bonus += 5.0 * float(lvl.direction.value)
            flags.append(lvl.label)

    total = max(-100.0, min(100.0, base_score + bonus))

    # Find nearest support/resistance zones
    bull_zones = [z for z in order_blocks + fvgs if z.direction == ICTDirection.BULL and z.high < current_price]
    bear_zones = [z for z in order_blocks + fvgs if z.direction == ICTDirection.BEAR and z.low > current_price]

    nearest_bull = max(bull_zones, key=lambda z: z.high, default=None)
    nearest_bear = min(bear_zones, key=lambda z: z.low, default=None)

    return PDArrayScore(
        score=round(total, 1),
        nearest_bull_zone=nearest_bull.label if nearest_bull else None,
        nearest_bear_zone=nearest_bear.label if nearest_bear else None,
        in_ote_zone=in_ote,
        at_ob=at_ob,
        at_fvg=at_fvg,
        at_ipda=at_ipda,
        detail=" | ".join(flags) if flags else "No ICT confluence",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _dedup_zones(zones: list, tol: float = 5.0) -> list:
    """Remove duplicate zones that are within `tol` points of each other."""
    if not zones:
        return []
    result = [zones[0]]
    for z in zones[1:]:
        if not any(abs(z.high - r.high) < tol and z.direction == r.direction for r in result):
            result.append(z)
    return result


def _cluster_levels(prices: list[float], tol: float) -> list[float]:
    """Return representative prices for clusters within tolerance."""
    if not prices:
        return []
    sorted_p = sorted(prices)
    clusters: list[list[float]] = []
    cur = [sorted_p[0]]
    for p in sorted_p[1:]:
        if p - cur[-1] <= tol:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    return [sum(c) / len(c) for c in clusters]
