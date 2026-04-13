"""Test suite for all 11 imbalance variants (IMB-01..09 + CONSECUTIVE + REVERSAL).

Covers:
  - IMB-01: Single imbalance (SINGLE) — diagonal ask[P] vs bid[P-1]
  - IMB-02: Multiple imbalances (MULTIPLE) — 3+ in same bar
  - IMB-03: Stacked T1/T2/T3 — 3/5/7 consecutive levels
  - IMB-04: Reverse imbalance (REVERSE) — both directions in same bar
  - IMB-05: Inverse trap (INVERSE_TRAP) — wrong direction in bar direction
  - IMB-06: Oversized imbalance (OVERSIZED) — 10:1+ ratio
  - IMB-07: Consecutive (CONSECUTIVE) — same level in two bars
  - IMB-08: Diagonal algorithm verification — ask[P] vs bid[P-1]
  - IMB-09: Reversal (REVERSAL) — direction change across bars
  - Edge cases: empty bar, single-level bar
  - Config override behavior
"""
from collections import defaultdict

import pytest

from deep6.engines.imbalance import (
    ImbalanceType,
    ImbalanceSignal,
    detect_imbalances,
)
from deep6.engines.signal_config import ImbalanceConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price


# ---------------------------------------------------------------------------
# Helper: build FootprintBar from dict {price: (bid_vol, ask_vol)}
# ---------------------------------------------------------------------------

def make_bar(levels_data: dict, open_px: float = 21000.0, close: float = 21000.0) -> FootprintBar:
    """Build a FootprintBar from a dict of {price: (bid_vol, ask_vol)}.

    levels_data keys are prices; values are (bid_vol, ask_vol) tuples.
    open_px and close control bar direction for inverse trap tests.
    """
    bar = FootprintBar()
    bar.open = open_px
    bar.close = close
    total_bid = total_ask = 0
    prices = sorted(levels_data.keys())

    for price in prices:
        bid, ask = levels_data[price]
        tick = price_to_tick(price)
        bar.levels[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
        total_bid += bid
        total_ask += ask

    bar.total_vol = total_bid + total_ask
    bar.bar_delta = total_ask - total_bid

    if prices:
        bar.high = max(prices)
        bar.low = min(prices)
        bar.bar_range = bar.high - bar.low
        # Find POC
        max_tick = max(
            bar.levels.keys(),
            key=lambda t: bar.levels[t].bid_vol + bar.levels[t].ask_vol,
        )
        bar.poc_price = tick_to_price(max_tick)

    return bar


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

def test_empty_bar_returns_no_signals():
    """Empty bar with no levels returns empty signal list."""
    bar = FootprintBar()
    result = detect_imbalances(bar)
    assert result == []


def test_zero_volume_bar_returns_no_signals():
    """Bar with levels but zero total_vol returns empty list."""
    bar = FootprintBar()
    bar.total_vol = 0
    result = detect_imbalances(bar)
    assert result == []


def test_single_level_bar_returns_no_signals():
    """Single-level bar cannot have diagonal imbalance (need 2+ levels)."""
    bar = make_bar({21000.0: (5, 20)})
    result = detect_imbalances(bar)
    assert result == []


# ---------------------------------------------------------------------------
# IMB-01: Single imbalance
# ---------------------------------------------------------------------------

def test_single_buy_imbalance_detected():
    """IMB-01: ask[P] / bid[P-1] >= 3.0 fires SINGLE buy imbalance.

    P = 21000.0, P-1 = 20999.75
    ask[21000.0] = 30, bid[20999.75] = 5  -> ratio = 6.0 >= 3.0 -> SINGLE
    """
    bar = make_bar({
        20999.75: (5, 2),   # P-1: bid=5 (the reference)
        21000.00: (1, 30),  # P:   ask=30 (imbalanced)
    })
    signals = detect_imbalances(bar)
    buy_singles = [s for s in signals if s.imb_type == ImbalanceType.SINGLE and s.direction == +1]
    assert len(buy_singles) >= 1
    assert buy_singles[0].price == pytest.approx(21000.0)
    assert buy_singles[0].ratio == pytest.approx(6.0)


def test_single_sell_imbalance_detected():
    """IMB-01: bid[P] / ask[P+1] >= 3.0 fires SINGLE sell imbalance.

    P = 21000.0, P+1 = 21000.25
    bid[21000.0] = 30, ask[21000.25] = 5  -> ratio = 6.0 >= 3.0 -> SINGLE
    """
    bar = make_bar({
        21000.00: (30, 1),  # P: bid=30 (imbalanced)
        21000.25: (2, 5),   # P+1: ask=5 (the reference)
    })
    signals = detect_imbalances(bar)
    sell_singles = [s for s in signals if s.imb_type == ImbalanceType.SINGLE and s.direction == -1]
    assert len(sell_singles) >= 1
    assert sell_singles[0].price == pytest.approx(21000.0)


def test_below_threshold_no_single_imbalance():
    """Ratio < 3.0 should not fire SINGLE imbalance."""
    bar = make_bar({
        20999.75: (10, 2),  # bid = 10
        21000.00: (1, 20),  # ask = 20, ratio = 2.0 < 3.0
    })
    signals = detect_imbalances(bar)
    singles = [s for s in signals if s.imb_type == ImbalanceType.SINGLE]
    assert len(singles) == 0


# ---------------------------------------------------------------------------
# IMB-06: Oversized imbalance
# ---------------------------------------------------------------------------

def test_oversized_imbalance():
    """IMB-06: ratio >= 10.0 fires OVERSIZED instead of SINGLE.

    ask[21000.0] = 100, bid[20999.75] = 5  -> ratio = 20.0 >= 10.0 -> OVERSIZED
    """
    bar = make_bar({
        20999.75: (5, 2),
        21000.00: (1, 100),  # ratio = 100/5 = 20.0 -> OVERSIZED
    })
    signals = detect_imbalances(bar)
    oversized = [s for s in signals if s.imb_type == ImbalanceType.OVERSIZED]
    assert len(oversized) >= 1
    # No SINGLE at this price
    singles_at_price = [
        s for s in signals
        if s.imb_type == ImbalanceType.SINGLE and s.price == pytest.approx(21000.0)
    ]
    assert len(singles_at_price) == 0


# ---------------------------------------------------------------------------
# IMB-02: Multiple imbalances
# ---------------------------------------------------------------------------

def test_multiple_imbalance():
    """IMB-02: 3+ buy imbalances in the same bar fires MULTIPLE.

    Create 4 consecutive price levels each with a 3x+ buy imbalance.
    """
    bar = make_bar({
        20999.50: (5, 1),   # P-1
        20999.75: (5, 15),  # ratio 3.0 vs 20999.50.bid -> buy imb tick 1
        21000.00: (5, 15),  # buy imb tick 2
        21000.25: (5, 15),  # buy imb tick 3
        21000.50: (5, 15),  # buy imb tick 4
    })
    signals = detect_imbalances(bar)
    multiples = [s for s in signals if s.imb_type == ImbalanceType.MULTIPLE and s.direction == +1]
    assert len(multiples) >= 1
    assert multiples[0].count >= 3


# ---------------------------------------------------------------------------
# IMB-03: Stacked imbalances
# ---------------------------------------------------------------------------

def test_stacked_t1():
    """IMB-03: 3 consecutive imbalance levels fires STACKED_T1."""
    # Build bar with 3 consecutive buy imbalance levels at prices 21000-21000.75
    bar = make_bar({
        20999.75: (5, 1),   # base reference
        21000.00: (1, 15),  # buy imb (15/5=3.0)
        21000.25: (1, 15),  # buy imb
        21000.50: (1, 15),  # buy imb -> 3 consecutive = T1
        21000.75: (10, 1),  # regular level
    })
    signals = detect_imbalances(bar)
    stacked = [s for s in signals if s.imb_type == ImbalanceType.STACKED_T1]
    assert len(stacked) >= 1


def test_stacked_t2():
    """IMB-03: 5 consecutive imbalance levels fires STACKED_T2."""
    bar = make_bar({
        20999.75: (5, 1),   # base reference
        21000.00: (1, 15),  # buy imb 1
        21000.25: (1, 15),  # buy imb 2
        21000.50: (1, 15),  # buy imb 3
        21000.75: (1, 15),  # buy imb 4
        21001.00: (1, 15),  # buy imb 5 -> 5 consecutive = T2
        21001.25: (10, 1),  # regular level
    })
    signals = detect_imbalances(bar)
    stacked = [s for s in signals if s.imb_type == ImbalanceType.STACKED_T2]
    assert len(stacked) >= 1


def test_stacked_t3():
    """IMB-03: 7 consecutive imbalance levels fires STACKED_T3."""
    bar = make_bar({
        20999.75: (5, 1),   # base reference
        21000.00: (1, 15),  # buy imb 1
        21000.25: (1, 15),  # buy imb 2
        21000.50: (1, 15),  # buy imb 3
        21000.75: (1, 15),  # buy imb 4
        21001.00: (1, 15),  # buy imb 5
        21001.25: (1, 15),  # buy imb 6
        21001.50: (1, 15),  # buy imb 7 -> 7 consecutive = T3
        21001.75: (10, 1),  # regular
    })
    signals = detect_imbalances(bar)
    stacked = [s for s in signals if s.imb_type == ImbalanceType.STACKED_T3]
    assert len(stacked) >= 1


# ---------------------------------------------------------------------------
# IMB-04: Reverse imbalance
# ---------------------------------------------------------------------------

def test_reverse_imbalance():
    """IMB-04: Both buy and sell imbalances in same bar fires REVERSE.

    Upper portion has buy imbalances; lower portion has sell imbalances.
    """
    bar = make_bar({
        21000.00: (30, 1),  # sell imb (bid=30 vs ask[+1]=5 -> ratio 6x)
        21000.25: (1, 5),   # P+1 reference for sell above
        21000.50: (5, 1),   # base reference for buy below
        21000.75: (1, 15),  # buy imb (ask=15 vs bid[P-1]=5 -> 3x)
    })
    signals = detect_imbalances(bar)
    reverses = [s for s in signals if s.imb_type == ImbalanceType.REVERSE]
    assert len(reverses) >= 1


# ---------------------------------------------------------------------------
# IMB-05: Inverse trap
# ---------------------------------------------------------------------------

def test_inverse_trap_bearish():
    """IMB-05: Buy imbalances in a RED (bearish) bar fires INVERSE_TRAP direction=-1.

    Trapped longs: aggressive buyers but price closed lower.
    """
    # Bar: open=21002, close=21000 (bearish)
    # 3 buy imbalances (>= inverse_min_imbalances=3)
    bar = make_bar(
        {
            20999.75: (5, 1),   # base
            21000.00: (1, 15),  # buy imb 1
            21000.25: (1, 15),  # buy imb 2
            21000.50: (1, 15),  # buy imb 3
        },
        open_px=21002.0,
        close=21000.0,  # bearish bar
    )
    signals = detect_imbalances(bar)
    traps = [s for s in signals if s.imb_type == ImbalanceType.INVERSE_TRAP and s.direction == -1]
    assert len(traps) >= 1


def test_inverse_trap_bullish():
    """IMB-05: Sell imbalances in a GREEN (bullish) bar fires INVERSE_TRAP direction=+1.

    Trapped shorts: aggressive sellers but price closed higher.
    """
    # Bar: open=21000, close=21002 (bullish)
    # 3 sell imbalances (>= inverse_min_imbalances=3)
    bar = make_bar(
        {
            21000.00: (15, 1),  # sell imb 1 (bid=15 vs ask[+1]=5 -> 3x)
            21000.25: (3, 5),   # reference for sell above
            21000.50: (15, 1),  # sell imb 2
            21000.75: (3, 5),   # reference
            21001.00: (15, 1),  # sell imb 3
            21001.25: (3, 5),   # reference
        },
        open_px=21000.0,
        close=21002.0,  # bullish bar
    )
    signals = detect_imbalances(bar)
    traps = [s for s in signals if s.imb_type == ImbalanceType.INVERSE_TRAP and s.direction == +1]
    assert len(traps) >= 1


# ---------------------------------------------------------------------------
# IMB-08: Diagonal algorithm verification
# ---------------------------------------------------------------------------

def test_diagonal_algorithm():
    """IMB-08: Verify algorithm uses ask[P] vs bid[P-1] for buy, bid[P] vs ask[P+1] for sell.

    P = 21000.25 (tick 84001)
    ask[21000.25] = 30, bid[21000.00] = 5  -> ratio = 6.0
    This is the standard diagonal comparison, not bid vs bid at same level.
    """
    # Two adjacent levels: lower has bid, upper has ask
    bar = make_bar({
        21000.00: (5, 1),   # P-1: bid=5
        21000.25: (1, 30),  # P: ask=30, ratio=30/5=6.0 >= 3.0 -> BUY SINGLE
    })
    signals = detect_imbalances(bar)
    buy_signals = [s for s in signals if s.imb_type == ImbalanceType.SINGLE and s.direction == +1]
    assert len(buy_signals) >= 1
    # Confirm it's at the upper tick (P), not P-1
    assert buy_signals[0].price == pytest.approx(21000.25)
    assert buy_signals[0].ratio == pytest.approx(6.0)

    # Now verify sell: bid[P] vs ask[P+1]
    bar2 = make_bar({
        21000.00: (30, 1),  # P: bid=30
        21000.25: (1, 5),   # P+1: ask=5, ratio=30/5=6.0 -> SELL SINGLE
    })
    signals2 = detect_imbalances(bar2)
    sell_signals = [s for s in signals2 if s.imb_type == ImbalanceType.SINGLE and s.direction == -1]
    assert len(sell_signals) >= 1
    assert sell_signals[0].price == pytest.approx(21000.0)


# ---------------------------------------------------------------------------
# IMB-07: Consecutive imbalances
# ---------------------------------------------------------------------------

def test_consecutive_across_bars():
    """IMB-07: Same level imbalanced in two bars fires CONSECUTIVE.

    Build a prior bar with a buy imbalance at 21000.25,
    then a current bar with the same imbalance at same tick.
    """
    # Prior bar: buy imbalance at 21000.25
    prior_bar = make_bar({
        21000.00: (5, 1),   # bid = 5
        21000.25: (1, 20),  # ask/bid[P-1] = 20/5 = 4x -> buy imb
    })

    # Current bar: same buy imbalance at 21000.25
    current_bar = make_bar({
        21000.00: (5, 1),
        21000.25: (1, 20),  # same imbalance
    })

    signals = detect_imbalances(current_bar, prior_bar=prior_bar)
    consecutive = [s for s in signals if s.imb_type == ImbalanceType.CONSECUTIVE]
    assert len(consecutive) >= 1
    assert consecutive[0].direction == +1
    assert consecutive[0].price == pytest.approx(21000.25)


# ---------------------------------------------------------------------------
# IMB-09: Reversal imbalance
# ---------------------------------------------------------------------------

def test_reversal_pattern():
    """IMB-09: Prior bar buy-dominant, current sell-dominant fires REVERSAL direction=-1.

    Prior bar: 4 buy imbalances, 0 sell imbalances -> dominant_buy
    Current bar: 4 sell imbalances, 0 buy imbalances -> dominant_sell
    => REVERSAL (bearish)
    """
    # Prior: dominant buy imbalances (4 buy, no sell)
    prior_bar = make_bar({
        20999.75: (5, 1),
        21000.00: (1, 15),  # buy imb 1
        21000.25: (1, 15),  # buy imb 2
        21000.50: (1, 15),  # buy imb 3
        21000.75: (1, 15),  # buy imb 4
    })

    # Current: dominant sell imbalances (4 sell, no buy)
    # sell imb: bid[P] >> ask[P+1]
    current_bar = make_bar({
        21000.00: (15, 1),  # sell imb 1 (bid=15 vs ask[+1]=5 -> 3x)
        21000.25: (2, 5),
        21000.50: (15, 1),  # sell imb 2
        21000.75: (2, 5),
        21001.00: (15, 1),  # sell imb 3
        21001.25: (2, 5),
        21001.50: (15, 1),  # sell imb 4
        21001.75: (2, 5),
    })

    signals = detect_imbalances(current_bar, prior_bar=prior_bar)
    reversals = [s for s in signals if s.imb_type == ImbalanceType.REVERSAL]
    assert len(reversals) >= 1
    # Prior was buy-dominant, current sell-dominant => bearish reversal
    assert reversals[0].direction == -1


def test_reversal_bullish_pattern():
    """IMB-09: Prior bar sell-dominant, current buy-dominant fires REVERSAL direction=+1."""
    # Prior: dominant sell imbalances
    prior_bar = make_bar({
        21000.00: (15, 1),
        21000.25: (2, 5),
        21000.50: (15, 1),
        21000.75: (2, 5),
        21001.00: (15, 1),
        21001.25: (2, 5),
    })

    # Current: dominant buy imbalances
    current_bar = make_bar({
        20999.75: (5, 1),
        21000.00: (1, 15),
        21000.25: (1, 15),
        21000.50: (1, 15),
        21000.75: (1, 15),
    })

    signals = detect_imbalances(current_bar, prior_bar=prior_bar)
    reversals = [s for s in signals if s.imb_type == ImbalanceType.REVERSAL]
    assert len(reversals) >= 1
    assert reversals[0].direction == +1


# ---------------------------------------------------------------------------
# Config override tests
# ---------------------------------------------------------------------------

def test_config_overrides():
    """Config with higher ratio_threshold suppresses imbalances below new threshold.

    Default ratio=3.0 would catch a 4x imbalance.
    Config ratio=5.0 should NOT fire on a 4x imbalance.
    """
    # Ask=20, bid=5 -> ratio=4.0. Default threshold=3.0 would catch it.
    bar = make_bar({
        20999.75: (5, 1),
        21000.00: (1, 20),  # ratio = 4.0
    })

    # Default config — should fire
    signals_default = detect_imbalances(bar)
    singles_default = [s for s in signals_default if s.imb_type == ImbalanceType.SINGLE]
    assert len(singles_default) >= 1

    # Higher threshold config — should NOT fire
    strict_config = ImbalanceConfig(ratio_threshold=5.0)
    signals_strict = detect_imbalances(bar, config=strict_config)
    singles_strict = [s for s in signals_strict if s.imb_type == ImbalanceType.SINGLE]
    assert len(singles_strict) == 0


def test_config_oversized_threshold():
    """Config oversized_threshold override promotes SINGLE to OVERSIZED at custom level."""
    # Ratio = 8.0: with default threshold (10.0) -> SINGLE; with config (6.0) -> OVERSIZED
    bar = make_bar({
        20999.75: (5, 1),
        21000.00: (1, 40),  # ratio = 40/5 = 8.0
    })

    # Default: 8.0 < 10.0 -> SINGLE
    signals_default = detect_imbalances(bar)
    default_singles = [s for s in signals_default if s.imb_type == ImbalanceType.SINGLE]
    assert len(default_singles) >= 1

    # Custom oversized threshold at 6.0: 8.0 >= 6.0 -> OVERSIZED
    custom_config = ImbalanceConfig(oversized_threshold=6.0)
    signals_custom = detect_imbalances(bar, config=custom_config)
    oversized = [s for s in signals_custom if s.imb_type == ImbalanceType.OVERSIZED]
    assert len(oversized) >= 1


def test_stacked_config_override():
    """Config with higher stacked_t1=4 suppresses T1 for a 3-level run."""
    bar = make_bar({
        20999.75: (5, 1),
        21000.00: (1, 15),  # buy imb 1
        21000.25: (1, 15),  # buy imb 2
        21000.50: (1, 15),  # buy imb 3 -> 3 = T1 at default
    })

    # Default: stacked_t1=3 -> T1 fires
    signals_default = detect_imbalances(bar)
    stacked_default = [s for s in signals_default if s.imb_type == ImbalanceType.STACKED_T1]
    assert len(stacked_default) >= 1

    # Stricter: stacked_t1=4 -> 3 levels NOT enough
    stricter_config = ImbalanceConfig(stacked_t1=4)
    signals_strict = detect_imbalances(bar, config=stricter_config)
    stacked_strict = [s for s in signals_strict if s.imb_type == ImbalanceType.STACKED_T1]
    assert len(stacked_strict) == 0


def test_no_prior_bar_no_consecutive():
    """CONSECUTIVE requires prior_bar — without it, no CONSECUTIVE fires."""
    bar = make_bar({
        21000.00: (5, 1),
        21000.25: (1, 20),
    })
    signals = detect_imbalances(bar, prior_bar=None)
    consecutive = [s for s in signals if s.imb_type == ImbalanceType.CONSECUTIVE]
    assert len(consecutive) == 0


def test_strength_capped_at_1():
    """Signal strength should never exceed 1.0 regardless of ratio."""
    bar = make_bar({
        20999.75: (1, 1),
        21000.00: (1, 1000),  # enormous ratio -> strength should still be <= 1.0
    })
    signals = detect_imbalances(bar)
    for s in signals:
        assert s.strength <= 1.0
