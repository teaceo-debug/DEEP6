"""ATR-scaled triple barrier labeling for DEEP6 backtesting.

Per vectorbt expert review: replaces fixed-N-bar exits with
stop/target/timeout barriers scaled to per-bar ATR, plus trailing.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import numpy as np


class ExitReason(Enum):
    STOP = "stop"
    TARGET = "target"
    TIMEOUT = "timeout"
    TRAIL = "trail"


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: int           # +1 long, -1 short
    pnl_points: float
    r_multiple: float
    bars_held: int
    exit_reason: ExitReason
    stop_price: float
    target_price: float
    max_favorable: float     # peak unrealized in R
    max_adverse: float       # worst unrealized in R


def compute_triple_barrier(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    entry_bar: int,
    direction: int,
    atr: float,
    stop_atr_mult: float = 0.8,
    target_atr_mult: float = 1.5,
    max_hold_bars: int = 15,
    trail_activation_atr: float = 1.0,
    trail_distance_atr: float = 1.0,
) -> Trade:
    """Compute exit for a single trade using triple barrier.

    Stop: entry - 0.8*ATR*direction
    Target: entry + 1.5*ATR*direction (1.875 R:R)
    Trail: once +1 ATR unrealized -> stop moves to breakeven
           once +1.5 ATR unrealized -> trail at 1 ATR behind peak
    Timeout: max_hold_bars

    Exit priority each bar: hard_stop > trail_stop > target > timeout
    Uses bar high/low to check if barriers hit (assumes worst case intra-bar).
    Returns Trade with r_multiple where 1R = stop_atr_mult * ATR.
    """
    entry_price = closes[entry_bar]
    stop = entry_price - stop_atr_mult * atr * direction
    target = entry_price + target_atr_mult * atr * direction
    r_unit = stop_atr_mult * atr  # 1R in points

    # Trail state
    trail_stop = stop  # current active stop (hard or trail)
    trail_activated = False

    peak_favorable = 0.0
    peak_adverse = 0.0

    end_bar = min(entry_bar + max_hold_bars, len(closes) - 1)

    for i in range(entry_bar + 1, end_bar + 1):
        bar_high = highs[i]
        bar_low = lows[i]

        # Unrealized at bar high/low (worst adverse, best favorable)
        if direction == 1:
            favorable = (bar_high - entry_price)  # for long, high is favorable
            adverse = (bar_low - entry_price)
        else:
            favorable = (entry_price - bar_low)
            adverse = (entry_price - bar_high)

        peak_favorable = max(peak_favorable, favorable)
        peak_adverse = min(peak_adverse, adverse)

        # Check stop hit
        if direction == 1 and bar_low <= trail_stop:
            exit_price = trail_stop  # assume stop fills at stop price
            reason = ExitReason.TRAIL if trail_activated else ExitReason.STOP
            pnl = (exit_price - entry_price) * direction
            return Trade(
                entry_bar=entry_bar, exit_bar=i, entry_price=entry_price,
                exit_price=exit_price, direction=direction, pnl_points=pnl,
                r_multiple=pnl / r_unit if r_unit > 0 else 0,
                bars_held=i - entry_bar, exit_reason=reason,
                stop_price=stop, target_price=target,
                max_favorable=peak_favorable / r_unit if r_unit > 0 else 0,
                max_adverse=peak_adverse / r_unit if r_unit > 0 else 0,
            )
        if direction == -1 and bar_high >= trail_stop:
            exit_price = trail_stop
            reason = ExitReason.TRAIL if trail_activated else ExitReason.STOP
            pnl = (exit_price - entry_price) * direction
            return Trade(
                entry_bar=entry_bar, exit_bar=i, entry_price=entry_price,
                exit_price=exit_price, direction=direction, pnl_points=pnl,
                r_multiple=pnl / r_unit if r_unit > 0 else 0,
                bars_held=i - entry_bar, exit_reason=reason,
                stop_price=stop, target_price=target,
                max_favorable=peak_favorable / r_unit if r_unit > 0 else 0,
                max_adverse=peak_adverse / r_unit if r_unit > 0 else 0,
            )

        # Check target
        if direction == 1 and bar_high >= target:
            exit_price = target
            pnl = (target - entry_price)
            return Trade(
                entry_bar=entry_bar, exit_bar=i, entry_price=entry_price,
                exit_price=target, direction=1, pnl_points=pnl,
                r_multiple=pnl / r_unit if r_unit > 0 else 0,
                bars_held=i - entry_bar, exit_reason=ExitReason.TARGET,
                stop_price=stop, target_price=target,
                max_favorable=peak_favorable / r_unit if r_unit > 0 else 0,
                max_adverse=peak_adverse / r_unit if r_unit > 0 else 0,
            )
        if direction == -1 and bar_low <= target:
            exit_price = target
            pnl = (entry_price - target)
            return Trade(
                entry_bar=entry_bar, exit_bar=i, entry_price=entry_price,
                exit_price=target, direction=-1, pnl_points=pnl,
                r_multiple=pnl / r_unit if r_unit > 0 else 0,
                bars_held=i - entry_bar, exit_reason=ExitReason.TARGET,
                stop_price=stop, target_price=target,
                max_favorable=peak_favorable / r_unit if r_unit > 0 else 0,
                max_adverse=peak_adverse / r_unit if r_unit > 0 else 0,
            )

        # Update trailing stop
        if peak_favorable >= trail_activation_atr * atr:
            if not trail_activated:
                # Move to breakeven first
                trail_stop = entry_price
                trail_activated = True
            # Then trail at trail_distance_atr behind peak
            if direction == 1:
                new_trail = closes[i] - trail_distance_atr * atr
                trail_stop = max(trail_stop, new_trail)
            else:
                new_trail = closes[i] + trail_distance_atr * atr
                trail_stop = min(trail_stop, new_trail)

    # Timeout exit at close of end_bar
    exit_price = closes[end_bar]
    pnl = (exit_price - entry_price) * direction
    return Trade(
        entry_bar=entry_bar, exit_bar=end_bar, entry_price=entry_price,
        exit_price=exit_price, direction=direction, pnl_points=pnl,
        r_multiple=pnl / r_unit if r_unit > 0 else 0,
        bars_held=end_bar - entry_bar, exit_reason=ExitReason.TIMEOUT,
        stop_price=stop, target_price=target,
        max_favorable=peak_favorable / r_unit if r_unit > 0 else 0,
        max_adverse=peak_adverse / r_unit if r_unit > 0 else 0,
    )
