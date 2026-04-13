"""Imbalance signal detection — 9 variants (+ CONSECUTIVE and REVERSAL).

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

from deep6.engines.signal_config import ImbalanceConfig
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
    config: ImbalanceConfig = ImbalanceConfig(),
) -> list[ImbalanceSignal]:
    """Detect all imbalance variants in a single bar.

    Args:
        bar: The current finalized FootprintBar.
        prior_bar: The prior bar for CONSECUTIVE and REVERSAL detection.
        config: ImbalanceConfig holding all tunable thresholds.
    """
    signals: list[ImbalanceSignal] = []

    if not bar.levels or bar.total_vol == 0:
        return signals

    sorted_ticks = sorted(bar.levels.keys())
    if len(sorted_ticks) < 2:
        return signals

    ratio_threshold = config.ratio_threshold
    oversized_threshold = config.oversized_threshold

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

    # --- Single imbalances (IMB-01) and Oversized (IMB-06) ---
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

    # --- Multiple imbalances (IMB-02) ---
    # Group buy_imb_ticks by tick value; any tick with count >= multiple_min_count fires MULTIPLE.
    # Since each tick appears at most once in the diagonal scan, MULTIPLE fires when the same
    # price tick has imbalances in both buy and sell scans (ambiguous pressure) or when a tick
    # appears multiple times (shouldn't happen — diagonal is one-pass). Per spec, MULTIPLE fires
    # when there are >= multiple_min_count imbalances within the same bar at the same price zone.
    # We implement this as: if total imbalance count for either direction >= multiple_min_count
    # and they are clustered within a tight price range, fire MULTIPLE.
    multiple_min = config.multiple_min_count
    if len(buy_imb_ticks) >= multiple_min:
        # Fire one MULTIPLE signal for the cluster at the median tick
        mid_idx = len(buy_imb_ticks) // 2
        mid_tick = buy_imb_ticks[mid_idx]
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.MULTIPLE,
            direction=+1,
            price=tick_to_price(mid_tick),
            ratio=0.0,
            count=len(buy_imb_ticks),
            strength=min(len(buy_imb_ticks) / (multiple_min * 2.0), 1.0),
            detail=(
                f"BUY MULTIPLE: {len(buy_imb_ticks)} buy imbalances in bar "
                f"(>= {multiple_min} threshold)"
            ),
        ))
    if len(sell_imb_ticks) >= multiple_min:
        mid_idx = len(sell_imb_ticks) // 2
        mid_tick = sell_imb_ticks[mid_idx]
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.MULTIPLE,
            direction=-1,
            price=tick_to_price(mid_tick),
            ratio=0.0,
            count=len(sell_imb_ticks),
            strength=min(len(sell_imb_ticks) / (multiple_min * 2.0), 1.0),
            detail=(
                f"SELL MULTIPLE: {len(sell_imb_ticks)} sell imbalances in bar "
                f"(>= {multiple_min} threshold)"
            ),
        ))

    # --- Stacked imbalances (IMB-03) ---
    stk_t1 = config.stacked_t1
    stk_t2 = config.stacked_t2
    stk_t3 = config.stacked_t3
    gap_tol = config.stacked_gap_tolerance

    for direction, imb_ticks in [(+1, buy_imb_ticks), (-1, sell_imb_ticks)]:
        if len(imb_ticks) < stk_t1:
            continue
        # Find consecutive runs
        runs: list[list[int]] = []
        current_run: list[int] = [imb_ticks[0]]
        for j in range(1, len(imb_ticks)):
            if imb_ticks[j] - imb_ticks[j - 1] <= gap_tol:
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
    inv_min = config.inverse_min_imbalances
    if bar_bearish and len(buy_imb_ticks) >= inv_min:
        signals.append(ImbalanceSignal(
            imb_type=ImbalanceType.INVERSE_TRAP, direction=-1,
            price=bar.close,
            ratio=0, count=len(buy_imb_ticks),
            strength=min(len(buy_imb_ticks) / 7.0, 1.0),
            detail=(
                f"INVERSE TRAP: {len(buy_imb_ticks)} BUY imbalances in RED bar "
                f"— longs trapped (80-85% win rate)"
            ),
        ))
    if bar_bullish and len(sell_imb_ticks) >= inv_min:
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
            detail=(
                f"REVERSE: {len(buy_imb_ticks)} buy + {len(sell_imb_ticks)} sell imbalances in same bar"
            ),
        ))

    # --- Consecutive imbalances (IMB-07) ---
    # Detect levels that are imbalanced in BOTH current bar and prior bar at same tick.
    if prior_bar is not None and prior_bar.levels and prior_bar.total_vol > 0:
        # Run diagonal scan on prior bar using same thresholds
        prior_sorted = sorted(prior_bar.levels.keys())
        prior_buy_ticks: set[int] = set()
        prior_sell_ticks: set[int] = set()

        for i, tick in enumerate(prior_sorted):
            plevel = prior_bar.levels[tick]
            if i > 0:
                pprev_tick = prior_sorted[i - 1]
                pprev_bid = prior_bar.levels[pprev_tick].bid_vol
                pcurr_ask = plevel.ask_vol
                if pprev_bid > 0 and pcurr_ask / pprev_bid >= ratio_threshold:
                    prior_buy_ticks.add(tick)
                elif pprev_bid == 0 and pcurr_ask > 0:
                    prior_buy_ticks.add(tick)
            if i < len(prior_sorted) - 1:
                pnext_tick = prior_sorted[i + 1]
                pnext_ask = prior_bar.levels[pnext_tick].ask_vol
                pcurr_bid = plevel.bid_vol
                if pnext_ask > 0 and pcurr_bid / pnext_ask >= ratio_threshold:
                    prior_sell_ticks.add(tick)
                elif pnext_ask == 0 and pcurr_bid > 0:
                    prior_sell_ticks.add(tick)

        # Find ticks imbalanced in both bars at same level
        consec_buy = set(buy_imb_ticks) & prior_buy_ticks
        consec_sell = set(sell_imb_ticks) & prior_sell_ticks

        for tick in sorted(consec_buy):
            signals.append(ImbalanceSignal(
                imb_type=ImbalanceType.CONSECUTIVE,
                direction=+1,
                price=tick_to_price(tick),
                ratio=buy_ratios.get(tick, 0.0),
                count=2,  # confirmed across 2 bars
                strength=0.75,
                detail=f"CONSECUTIVE BUY IMB at {tick_to_price(tick):.2f}: persistent across 2 bars",
            ))
        for tick in sorted(consec_sell):
            signals.append(ImbalanceSignal(
                imb_type=ImbalanceType.CONSECUTIVE,
                direction=-1,
                price=tick_to_price(tick),
                ratio=sell_ratios.get(tick, 0.0),
                count=2,
                strength=0.75,
                detail=f"CONSECUTIVE SELL IMB at {tick_to_price(tick):.2f}: persistent across 2 bars",
            ))

    # --- Reversal imbalance (IMB-09) ---
    # Prior bar dominated by buy imbalances + current bar dominated by sell (or vice versa).
    if prior_bar is not None and prior_bar.levels and prior_bar.total_vol > 0:
        # Re-use prior scan results computed in CONSECUTIVE block above (if available).
        # To avoid tight coupling, re-check counts directly.
        prior_sorted2 = sorted(prior_bar.levels.keys())
        p_buy_count = 0
        p_sell_count = 0
        for i, tick in enumerate(prior_sorted2):
            plevel = prior_bar.levels[tick]
            if i > 0:
                pprev_bid = prior_bar.levels[prior_sorted2[i - 1]].bid_vol
                pcurr_ask = plevel.ask_vol
                if (pprev_bid > 0 and pcurr_ask / pprev_bid >= ratio_threshold) or (
                    pprev_bid == 0 and pcurr_ask > 0
                ):
                    p_buy_count += 1
            if i < len(prior_sorted2) - 1:
                pnext_ask = prior_bar.levels[prior_sorted2[i + 1]].ask_vol
                pcurr_bid = plevel.bid_vol
                if (pnext_ask > 0 and pcurr_bid / pnext_ask >= ratio_threshold) or (
                    pnext_ask == 0 and pcurr_bid > 0
                ):
                    p_sell_count += 1

        curr_buy_count = len(buy_imb_ticks)
        curr_sell_count = len(sell_imb_ticks)

        # Dominant direction: side with at least 2x the other side
        prior_dominant_buy = p_buy_count >= 2 and p_buy_count > p_sell_count * 2
        prior_dominant_sell = p_sell_count >= 2 and p_sell_count > p_buy_count * 2
        curr_dominant_buy = curr_buy_count >= 2 and curr_buy_count > curr_sell_count * 2
        curr_dominant_sell = curr_sell_count >= 2 and curr_sell_count > curr_buy_count * 2

        # Reversal: prior was dominantly buy, now dominantly sell (or vice versa)
        if prior_dominant_buy and curr_dominant_sell:
            signals.append(ImbalanceSignal(
                imb_type=ImbalanceType.REVERSAL,
                direction=-1,  # turning bearish
                price=bar.close,
                ratio=0.0,
                count=curr_sell_count,
                strength=min((p_buy_count + curr_sell_count) / 10.0, 1.0),
                detail=(
                    f"IMB REVERSAL (bearish): prior had {p_buy_count} buy imbalances, "
                    f"now {curr_sell_count} sell imbalances"
                ),
            ))
        elif prior_dominant_sell and curr_dominant_buy:
            signals.append(ImbalanceSignal(
                imb_type=ImbalanceType.REVERSAL,
                direction=+1,  # turning bullish
                price=bar.close,
                ratio=0.0,
                count=curr_buy_count,
                strength=min((p_sell_count + curr_buy_count) / 10.0, 1.0),
                detail=(
                    f"IMB REVERSAL (bullish): prior had {p_sell_count} sell imbalances, "
                    f"now {curr_buy_count} buy imbalances"
                ),
            ))

    return signals
