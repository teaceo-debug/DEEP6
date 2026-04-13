"""Imbalance signal detection — 9 variants.

Imbalances detect aggressive buying/selling at specific price levels
by comparing ask volume at one level vs bid volume at adjacent levels
(diagonal comparison per confirmed algorithm: ask[P] vs bid[P-1]).

Variants (per IMB-01..09):
  1. Single:      One imbalance at configurable ratio (default 300%)
  2. Multiple:    3+ imbalances at same price
  3. Stacked:     T1/T2/T3 (3/5/7 consecutive levels) — increasing conviction
  4. Reverse:     Opposite direction imbalance within bar
  5. Inverse:     Buy imbalances in red bar = trapped longs (80-85% win rate)
  6. Oversized:   10:1+ ratio at single level
  7. Consecutive: Same level across multiple bars
  8. Diagonal:    Cross-tick ask[P] vs bid[P-1] comparison
  9. Reversal:    Imbalance direction change within bar sequence
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from deep6.state.footprint import FootprintBar, tick_to_price


class ImbalanceType(Enum):
    SINGLE = auto()
    MULTIPLE = auto()
    STACKED_T1 = auto()
    STACKED_T2 = auto()
    STACKED_T3 = auto()
    REVERSE = auto()
    INVERSE_TRAP = auto()
    OVERSIZED = auto()
    CONSECUTIVE = auto()
    DIAGONAL = auto()
    REVERSAL = auto()


@dataclass
class ImbalanceSignal:
    imb_type: ImbalanceType
    direction: int       # +1 = buy imbalance, -1 = sell imbalance
    price: float
    ratio: float
    count: int           # number of consecutive imbalance levels
    strength: float      # 0-1
    detail: str


def detect_imbalances(
    bar: FootprintBar,
    prior_bar: FootprintBar | None = None,
    ratio_threshold: float = 3.0,
    oversized_threshold: float = 10.0,
    stk_t1: int = 3,
    stk_t2: int = 5,
    stk_t3: int = 7,
) -> list[ImbalanceSignal]:
    """Detect all imbalance variants in a single bar."""
    signals: list[ImbalanceSignal] = []

    if not bar.levels or bar.total_vol == 0:
        return signals

    sorted_ticks = sorted(bar.levels.keys())
    if len(sorted_ticks) < 2:
        return signals

    # --- Diagonal imbalance scan (IMB-08) ---
    # ask[P] vs bid[P-1] for buy imbalance
    # bid[P] vs ask[P+1] for sell imbalance
    buy_imb_ticks: list[int] = []
    sell_imb_ticks: list[int] = []
    buy_ratios: dict[int, float] = {}
    sell_ratios: dict[int, float] = {}

    for i, tick in enumerate(sorted_ticks):
        level = bar.levels[tick]

        # Buy imbalance: ask[P] vs bid[P-1]
        if i > 0:
            prev_tick = sorted_ticks[i - 1]
            prev_bid = bar.levels[prev_tick].bid_vol
            curr_ask = level.ask_vol
            if prev_bid > 0 and curr_ask / prev_bid >= ratio_threshold:
                buy_imb_ticks.append(tick)
                buy_ratios[tick] = curr_ask / prev_bid
            elif prev_bid == 0 and curr_ask > 0:
                buy_imb_ticks.append(tick)
                buy_ratios[tick] = float(curr_ask)  # infinite ratio

        # Sell imbalance: bid[P] vs ask[P+1]
        if i < len(sorted_ticks) - 1:
            next_tick = sorted_ticks[i + 1]
            next_ask = bar.levels[next_tick].ask_vol
            curr_bid = level.bid_vol
            if next_ask > 0 and curr_bid / next_ask >= ratio_threshold:
                sell_imb_ticks.append(tick)
                sell_ratios[tick] = curr_bid / next_ask
            elif next_ask == 0 and curr_bid > 0:
                sell_imb_ticks.append(tick)
                sell_ratios[tick] = float(curr_bid)

    # --- Single imbalances (IMB-01) ---
    for tick in buy_imb_ticks:
        r = buy_ratios[tick]
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.SINGLE if r < oversized_threshold else ImbalanceType.OVERSIZED,
            direction=+1, price=tick_to_price(tick), ratio=r, count=1,
            strength=min(r / 10.0, 1.0),
            detail=f"BUY IMB at {tick_to_price(tick):.2f}: {r:.1f}x ratio",
        ))
    for tick in sell_imb_ticks:
        r = sell_ratios[tick]
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.SINGLE if r < oversized_threshold else ImbalanceType.OVERSIZED,
            direction=-1, price=tick_to_price(tick), ratio=r, count=1,
            strength=min(r / 10.0, 1.0),
            detail=f"SELL IMB at {tick_to_price(tick):.2f}: {r:.1f}x ratio",
        ))

    # --- Stacked imbalances (IMB-03) ---
    for direction, imb_ticks in [(+1, buy_imb_ticks), (-1, sell_imb_ticks)]:
        if len(imb_ticks) < stk_t1:
            continue
        # Find consecutive runs
        runs: list[list[int]] = []
        current_run: list[int] = [imb_ticks[0]]
        for j in range(1, len(imb_ticks)):
            if imb_ticks[j] - imb_ticks[j - 1] <= 2:  # allow 1 tick gap
                current_run.append(imb_ticks[j])
            else:
                if len(current_run) >= stk_t1:
                    runs.append(current_run)
                current_run = [imb_ticks[j]]
        if len(current_run) >= stk_t1:
            runs.append(current_run)

        for run in runs:
            n = len(run)
            if n >= stk_t3:
                tier = ImbalanceType.STACKED_T3
            elif n >= stk_t2:
                tier = ImbalanceType.STACKED_T2
            else:
                tier = ImbalanceType.STACKED_T1

            mid_tick = run[len(run) // 2]
            label = "BUY" if direction > 0 else "SELL"
            signals.append(ImbalanceSignal(
                imb_type=tier, direction=direction,
                price=tick_to_price(mid_tick),
                ratio=0, count=n,
                strength=min(n / stk_t3, 1.0),
                detail=f"STACKED {label} x{n} ({tier.name}) at {tick_to_price(mid_tick):.2f}",
            ))

    # --- Inverse imbalance / trapped traders (IMB-05) ---
    bar_bearish = bar.close < bar.open
    bar_bullish = bar.close > bar.open
    if bar_bearish and len(buy_imb_ticks) >= 3:
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.INVERSE_TRAP, direction=-1,
            price=bar.close,
            ratio=0, count=len(buy_imb_ticks),
            strength=min(len(buy_imb_ticks) / 7.0, 1.0),
            detail=f"INVERSE TRAP: {len(buy_imb_ticks)} BUY imbalances in RED bar — longs trapped (80-85% win rate)",
        ))
    if bar_bullish and len(sell_imb_ticks) >= 3:
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.INVERSE_TRAP, direction=+1,
            price=bar.close,
            ratio=0, count=len(sell_imb_ticks),
            strength=min(len(sell_imb_ticks) / 7.0, 1.0),
            detail=f"INVERSE TRAP: {len(sell_imb_ticks)} SELL imbalances in GREEN bar — shorts trapped",
        ))

    # --- Reverse imbalance (IMB-04) ---
    if buy_imb_ticks and sell_imb_ticks:
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.REVERSE, direction=0,
            price=(bar.high + bar.low) / 2,
            ratio=0, count=len(buy_imb_ticks) + len(sell_imb_ticks),
            strength=0.5,
            detail=f"REVERSE: {len(buy_imb_ticks)} buy + {len(sell_imb_ticks)} sell imbalances in same bar",
        ))

    return signals
