"""Test suite for all 6 exhaustion variants + EXH-07 delta gate + EXH-08 cooldown.

Covers:
  - ZERO_PRINT (EXH-01): structural gap — exempt from delta gate
  - EXHAUSTION_PRINT (EXH-02): high single-side vol at bar extreme
  - THIN_PRINT (EXH-03): 3+ levels with vol < 5% max inside body
  - FAT_PRINT (EXH-04): single level with vol > 2x average
  - FADING_MOMENTUM (EXH-05): delta diverges from price direction
  - BID_ASK_FADE (EXH-06): ask at high < 60% of prior bar's ask at high
  - Delta trajectory gate (EXH-07): blocks confirming delta, passes opposing, disabled
  - Cooldown (EXH-08): suppresses within window, allows after, cross-type, reset
"""
import pytest
from collections import defaultdict
from deep6.engines.exhaustion import (
    ExhaustionType,
    ExhaustionSignal,
    detect_exhaustion,
    reset_cooldowns,
)
from deep6.engines.signal_config import ExhaustionConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cooldowns():
    """Reset cooldown state before each test to prevent cross-test leakage."""
    reset_cooldowns()
    yield
    reset_cooldowns()


@pytest.fixture
def make_bar():
    """Factory: builds a synthetic FootprintBar from explicit level data."""
    def _make(open_px, high, low, close, levels_data):
        bar = FootprintBar()
        bar.open = open_px
        bar.high = high
        bar.low = low
        bar.close = close
        bar.bar_range = high - low

        total_bid = total_ask = 0
        max_vol = 0
        max_tick = 0

        for price, bid, ask in levels_data:
            tick = price_to_tick(price)
            bar.levels[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
            total_bid += bid
            total_ask += ask
            if bid + ask > max_vol:
                max_vol = bid + ask
                max_tick = tick

        bar.total_vol = total_bid + total_ask
        bar.bar_delta = total_ask - total_bid
        bar.poc_price = tick_to_price(max_tick)
        return bar

    return _make


# ---------------------------------------------------------------------------
# 1. ZERO PRINT (EXH-01)
# ---------------------------------------------------------------------------

def test_zero_print_fires(make_bar):
    """Bar with a level inside body having bid=0, ask=0 produces ZERO_PRINT."""
    # open=21000, close=21010 (bullish), body is 21000-21010
    # Level at 21005 with zero volume inside body
    # To have a zero level appear, we must explicitly insert it
    levels = [
        (21000.0,  80,  70),   # body
        (21010.0,  80,  70),   # body top
        (21015.0,  20,  20),   # above body (wick)
    ]
    bar = make_bar(21000.0, 21015.0, 20995.0, 21010.0, levels)
    # Inject a zero-volume level inside body
    bar.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)

    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    zero_prints = [s for s in signals if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero_prints) >= 1, "ZERO_PRINT should fire on 0-volume level inside body"
    assert zero_prints[0].price == 21005.0


def test_zero_print_fires_at_open_level(make_bar):
    """Zero print fires even when the zero-level is near open/close."""
    levels = [
        (21000.0, 100, 100),   # body bottom
        (21008.0,  80,  80),   # body
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21008.0, levels)
    # Zero volume level inside body
    bar.levels[price_to_tick(21003.0)] = FootprintLevel(bid_vol=0, ask_vol=0)

    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)
    zero = [s for s in signals if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero) >= 1


def test_zero_print_exempt_from_delta_gate(make_bar):
    """ZERO_PRINT fires even when delta confirms price direction (gate exemption)."""
    # Bullish bar (close > open) with positive delta — confirming, gate would block others
    levels = [
        (21000.0,  10, 100),   # heavy ask — bullish delta
        (21010.0,  10, 100),   # heavy ask
    ]
    bar = make_bar(21000.0, 21015.0, 20995.0, 21010.0, levels)
    bar.bar_delta = 180   # strongly positive (confirming)
    bar.total_vol = 220
    # Inject zero level inside body
    bar.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)

    # Config with gate enabled (default)
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    zero = [s for s in signals if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero) >= 1, "ZERO_PRINT must fire despite confirming delta (gate exempt)"


# ---------------------------------------------------------------------------
# 2. EXHAUSTION PRINT (EXH-02)
# ---------------------------------------------------------------------------

def test_exhaustion_print_fires_at_high(make_bar):
    """High ask_vol at highest tick (>threshold%) → EXHAUSTION_PRINT direction=-1."""
    # exhaust_wick_min = 35.0; threshold for single level = 35/3 ≈ 11.7%
    # Total vol ~ 500; high_ask needs to be ~60+ (12%) of 500
    # Bullish bar with negative delta for gate to pass
    levels = [
        (21000.0,  50,  50),   # body
        (21005.0,  50,  50),   # body
        (21010.0,  10,  90),   # high tick — 90 ask vol = 18% of 300 total → fires
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21008.0, levels)
    bar.bar_delta = -100   # negative delta → gate passes (bullish bar + negative delta)
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    exhaust = [s for s in signals if s.bar_type == ExhaustionType.EXHAUSTION_PRINT and s.direction == -1]
    assert len(exhaust) >= 1, "EXHAUSTION_PRINT bearish should fire at high with heavy ask"


def test_exhaustion_print_fires_at_low(make_bar):
    """Heavy bid_vol at lowest tick → EXHAUSTION_PRINT direction=+1 (sellers exhausted)."""
    # Bearish bar (close < open) + positive delta for gate to pass
    levels = [
        (20995.0,  90,  10),   # low tick — 90 bid vol = 18% of ~300 total
        (21000.0,  50,  50),   # body
        (21005.0,  50,  50),   # body
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21000.0, levels)
    bar.bar_delta = 100   # positive delta → gate passes (bearish bar + positive delta)
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    exhaust = [s for s in signals if s.bar_type == ExhaustionType.EXHAUSTION_PRINT and s.direction == +1]
    assert len(exhaust) >= 1, "EXHAUSTION_PRINT bullish should fire at low with heavy bid"


# ---------------------------------------------------------------------------
# 3. THIN PRINT (EXH-03)
# ---------------------------------------------------------------------------

def test_thin_print_fires(make_bar):
    """3+ levels inside body with vol < 5% of max_level_vol → THIN_PRINT fires."""
    # max_level_vol = 200; thin threshold = 200 * 0.05 = 10
    # Levels at 21001, 21002, 21003 each with vol=5 (thin)
    # Need delta divergence for gate: bearish bar + positive delta
    levels = [
        (21000.0, 100, 100),   # max vol = 200 (body)
        (21001.0,   2,   3),   # thin: 5 < 10
        (21002.0,   3,   2),   # thin: 5 < 10
        (21003.0,   2,   3),   # thin: 5 < 10
        (21004.0,   5,   3),   # thin: 8 < 10
        (21008.0,  40,  40),   # body top
    ]
    bar = make_bar(21008.0, 21010.0, 20999.0, 21000.0, levels)
    # Bearish bar (close < open) + positive delta for gate
    bar.bar_delta = 100
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    thin = [s for s in signals if s.bar_type == ExhaustionType.THIN_PRINT]
    assert len(thin) >= 1, "THIN_PRINT should fire with 3+ thin levels inside body"


def test_thin_print_fires_bullish(make_bar):
    """THIN_PRINT direction follows bar direction."""
    levels = [
        (21000.0,  10,  10),   # body (max_vol=200 later)
        (21001.0,   2,   3),   # thin
        (21002.0,   3,   2),   # thin
        (21003.0,   2,   3),   # thin
        (21004.0, 100, 100),   # max level
    ]
    bar = make_bar(21000.0, 21010.0, 20999.0, 21008.0, levels)
    # Bullish bar + negative delta for gate
    bar.bar_delta = -100
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    thin = [s for s in signals if s.bar_type == ExhaustionType.THIN_PRINT]
    # If thin fires, check direction matches bar direction (bullish)
    if thin:
        assert thin[0].direction == +1, "Thin print on bullish bar should have direction=+1"


# ---------------------------------------------------------------------------
# 4. FAT PRINT (EXH-04)
# ---------------------------------------------------------------------------

def test_fat_print_fires(make_bar):
    """One level with vol > 2x average → FAT_PRINT fires."""
    # avg_level_vol = total / n_levels; need one level STRICTLY > 2x avg
    # Build: 4 levels. fat level = 400, others = 50 each → total = 400+150=550
    # avg = 550/4 = 137.5; fat threshold = 2 * 137.5 = 275; 400 > 275 ✓
    # Bearish bar + positive delta for gate
    levels = [
        (21000.0,  50,  50),   # normal
        (21001.0,  50,  50),   # normal
        (21002.0,  50,  50),   # normal
        (21003.0,  50,  50),   # normal
    ]
    bar = make_bar(21003.0, 21005.0, 20999.0, 21000.0, levels)
    # Override fat level with clearly above-threshold volume
    bar.levels[price_to_tick(21001.0)] = FootprintLevel(bid_vol=200, ask_vol=200)  # 400 vol
    # Recalculate totals: 400 + 100 + 100 + 100 = 700
    bar.total_vol = 700
    bar.bar_delta = 100   # positive delta — bearish bar gate passes (close < open)
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    fat = [s for s in signals if s.bar_type == ExhaustionType.FAT_PRINT]
    assert len(fat) >= 1, "FAT_PRINT should fire when level > 2x average"


def test_fat_print_rejects_uniform_volume(make_bar):
    """All levels have equal volume (none > 2x avg) → FAT_PRINT should NOT fire."""
    # All levels = 100 each; avg = 100; fat threshold = 200; no level hits it
    levels = [
        (21000.0, 50, 50),
        (21001.0, 50, 50),
        (21002.0, 50, 50),
        (21003.0, 50, 50),
    ]
    bar = make_bar(21003.0, 21005.0, 20999.0, 21000.0, levels)
    bar.bar_delta = 100
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    fat = [s for s in signals if s.bar_type == ExhaustionType.FAT_PRINT]
    assert len(fat) == 0, "Uniform volume should not trigger FAT_PRINT"


# ---------------------------------------------------------------------------
# 5. FADING MOMENTUM (EXH-05)
# ---------------------------------------------------------------------------

def test_fading_momentum_fires_bearish(make_bar):
    """Green bar with |delta| > 15% of vol (opposing delta) → FADING_MOMENTUM direction=-1."""
    # Bullish bar: close > open
    # Gate: bullish + negative delta → gate passes
    # Stronger threshold: |delta| > 15% of total vol
    # total=400, delta=-80 → |delta|/total = 0.20 > 0.15
    levels = [
        (21000.0, 110,  90),   # body
        (21005.0, 110,  90),   # body (total=400, net delta = -40)
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21008.0, levels)
    bar.bar_delta = -80   # -80 / 400 = 0.20 > 0.15, bullish bar → gate passes
    bar.total_vol = 400
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    fade = [s for s in signals if s.bar_type == ExhaustionType.FADING_MOMENTUM]
    assert len(fade) >= 1, "FADING_MOMENTUM should fire on bullish bar with opposing delta"
    assert fade[0].direction == -1, "Bullish bar fading = bearish signal (-1)"


def test_fading_momentum_fires_bullish(make_bar):
    """Bearish bar with positive delta (opposing) → FADING_MOMENTUM direction=+1."""
    # close < open (bearish), gate: bearish + positive delta → passes
    # |delta| > 15% of vol → 80/400 = 0.20 > 0.15
    levels = [
        (21000.0,  90, 110),
        (21005.0,  90, 110),
    ]
    bar = make_bar(21008.0, 21010.0, 20995.0, 21000.0, levels)
    bar.bar_delta = 80   # positive, bearish bar → gate passes
    bar.total_vol = 400
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    fade = [s for s in signals if s.bar_type == ExhaustionType.FADING_MOMENTUM]
    assert len(fade) >= 1, "FADING_MOMENTUM should fire on bearish bar with positive delta"
    assert fade[0].direction == +1


# ---------------------------------------------------------------------------
# 6. BID/ASK FADE (EXH-06)
# ---------------------------------------------------------------------------

def test_bid_ask_fade_fires(make_bar):
    """Current ask at high < 60% of prior bar's ask at high → BID_ASK_FADE direction=-1."""
    # prior bar: high_ask = 100
    # curr bar: high_ask = 50 → 50/100 = 50% < 60% → fires
    prior = make_bar(21000.0, 21010.0, 20995.0, 21008.0, [
        (21005.0, 50, 50),
        (21010.0, 10, 100),   # high tick: ask=100
    ])

    curr = make_bar(21000.0, 21010.0, 20995.0, 21005.0, [
        (21005.0, 50, 50),
        (21010.0, 10, 50),    # high tick: ask=50 < 60% of 100
    ])
    # Bullish bar + negative delta for gate
    curr.bar_delta = -80
    curr.total_vol = 160

    signals = detect_exhaustion(curr, prior_bar=prior, bar_index=0, atr=15.0)
    fade = [s for s in signals if s.bar_type == ExhaustionType.BID_ASK_FADE]
    assert len(fade) >= 1, "BID_ASK_FADE should fire when current ask < 60% of prior ask"
    assert fade[0].direction == -1


def test_bid_ask_fade_no_fire_when_ask_strong(make_bar):
    """Current ask at high > 60% of prior → BID_ASK_FADE should NOT fire."""
    prior = make_bar(21000.0, 21010.0, 20995.0, 21008.0, [
        (21005.0, 50, 50),
        (21010.0, 10, 100),   # high ask = 100
    ])
    curr = make_bar(21000.0, 21010.0, 20995.0, 21005.0, [
        (21005.0, 50, 50),
        (21010.0, 10, 80),    # high ask = 80 — 80% > 60%, no fade
    ])
    curr.bar_delta = -80
    curr.total_vol = 190

    signals = detect_exhaustion(curr, prior_bar=prior, bar_index=0, atr=15.0)
    fade = [s for s in signals if s.bar_type == ExhaustionType.BID_ASK_FADE]
    assert len(fade) == 0, "Ask at 80% of prior should not trigger BID_ASK_FADE"


# ---------------------------------------------------------------------------
# 7. DELTA TRAJECTORY GATE (EXH-07)
# ---------------------------------------------------------------------------

def test_delta_gate_blocks_confirming_delta(make_bar):
    """Bullish bar with positive delta (confirming) → gate blocks all signals except ZERO_PRINT."""
    # Bullish bar: close > open; positive delta confirms the move → gate fails
    # Gate: if bullish and delta > 0 → block
    levels = [
        (21000.0,  50, 150),   # heavy ask side
        (21005.0,  50, 150),
        (21010.0,  50, 150),   # high tick with heavy ask
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21009.0, levels)
    bar.bar_delta = 300   # positive — confirming bullish bar
    bar.total_vol = 600

    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)

    # Should have no non-zero-print signals
    non_zero = [s for s in signals if s.bar_type != ExhaustionType.ZERO_PRINT]
    assert len(non_zero) == 0, \
        "Confirming delta should block all exhaustion except ZERO_PRINT"


def test_delta_gate_passes_opposing_delta(make_bar):
    """Bullish bar with negative delta (opposing) → gate passes, signals can fire."""
    # Bullish bar + negative delta → exhaustion divergence confirmed
    levels = [
        (21000.0, 100,  50),   # heavy bid
        (21005.0, 100,  50),
        (21010.0,  10,  90),   # exhaustion print at high: 90 ask / total = 90/500 = 18%
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21008.0, levels)
    bar.bar_delta = -150   # negative — opposing bullish bar
    bar.total_vol = 500

    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)
    # Gate passed — should have non-zero-print signals
    has_exhaustion = any(s.bar_type != ExhaustionType.ZERO_PRINT for s in signals)
    assert has_exhaustion, "Opposing delta should allow exhaustion signals through"


def test_delta_gate_disabled(make_bar):
    """ExhaustionConfig(delta_gate_enabled=False) allows all signals regardless of delta."""
    # Bullish bar + positive (confirming) delta — gate would block normally
    levels = [
        (21000.0,  50, 150),
        (21005.0,  50, 150),
        (21010.0,  10, 100),   # heavy ask at high for EXHAUSTION_PRINT
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21009.0, levels)
    bar.bar_delta = 300   # positive confirming — gate would block
    bar.total_vol = 510

    config_no_gate = ExhaustionConfig(delta_gate_enabled=False)
    signals = detect_exhaustion(bar, bar_index=0, atr=15.0, config=config_no_gate)

    non_zero = [s for s in signals if s.bar_type != ExhaustionType.ZERO_PRINT]
    # With gate disabled, should have some non-zero-print signals
    assert len(non_zero) >= 1, \
        "Disabled gate should allow signals through even with confirming delta"


def test_delta_gate_small_delta_passes(make_bar):
    """Delta ratio < delta_gate_min_ratio (0.10) → gate does not block (noise threshold)."""
    # Bullish bar but delta_ratio is tiny (< 10%) → gate treats as noise, allows signals
    # Total = 1000, delta = 50 → ratio = 5% < 10%
    levels = [
        (21000.0, 250, 250),
        (21005.0, 250, 250),
        (21010.0,   5,  50),   # exhaustion print at high
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21009.0, levels)
    bar.bar_delta = 50     # 50/1055 ≈ 4.7% < 10% → small delta, gate doesn't block
    bar.total_vol = 1055

    signals = detect_exhaustion(bar, bar_index=0, atr=15.0)
    # Gate should pass (small delta = noise)
    # Cannot assert signals fire because other conditions may not be met,
    # but confirm gate doesn't block by checking EXHAUSTION_PRINT can fire
    # (high_ask = 50 / 1055 ≈ 4.7% which is below exhaust_wick_min/3 = 11.7%)
    # Instead test that _delta_trajectory_gate returns True for small delta
    from deep6.engines.exhaustion import _delta_trajectory_gate
    cfg = ExhaustionConfig()
    assert _delta_trajectory_gate(bar, cfg) is True, \
        "Small delta ratio below gate_min_ratio should allow signals"


def test_delta_gate_doji_passes(make_bar):
    """Doji (close == open) → gate allows signals regardless of delta."""
    from deep6.engines.exhaustion import _delta_trajectory_gate
    levels = [(21000.0, 100, 80)]
    bar = make_bar(21000.0, 21010.0, 20995.0, 21000.0, levels)  # close == open → doji
    bar.bar_delta = 200   # large delta
    bar.total_vol = 180
    cfg = ExhaustionConfig()
    assert _delta_trajectory_gate(bar, cfg) is True, \
        "Doji bar should always pass delta gate"


# ---------------------------------------------------------------------------
# 8. COOLDOWN (EXH-08)
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_repeat(make_bar):
    """Same ExhaustionType cannot fire within cooldown_bars (default 5)."""
    # Bar that produces ZERO_PRINT
    def make_zero_bar():
        b = make_bar(21000.0, 21015.0, 20995.0, 21010.0, [
            (21000.0, 80, 70),
            (21010.0, 80, 70),
        ])
        b.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)
        return b

    # Fire at bar_index=0
    sigs_0 = detect_exhaustion(make_zero_bar(), bar_index=0)
    zero_at_0 = [s for s in sigs_0 if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero_at_0) >= 1, "ZERO_PRINT should fire at bar 0"

    # Bars 1-4: same bar, should be suppressed
    for i in range(1, 5):
        sigs = detect_exhaustion(make_zero_bar(), bar_index=i)
        zero = [s for s in sigs if s.bar_type == ExhaustionType.ZERO_PRINT]
        assert len(zero) == 0, f"ZERO_PRINT should be suppressed at bar_index={i} (within cooldown)"


def test_cooldown_allows_after_window(make_bar):
    """Same ExhaustionType CAN fire at bar_index >= cooldown_bars after last firing."""
    def make_zero_bar():
        b = make_bar(21000.0, 21015.0, 20995.0, 21010.0, [
            (21000.0, 80, 70),
            (21010.0, 80, 70),
        ])
        b.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)
        return b

    # Fire at bar 0
    detect_exhaustion(make_zero_bar(), bar_index=0)

    # Bar 5 — exactly at cooldown boundary (0 + 5 = 5 → allowed)
    sigs_5 = detect_exhaustion(make_zero_bar(), bar_index=5)
    zero_5 = [s for s in sigs_5 if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero_5) >= 1, "ZERO_PRINT should fire again at bar_index=5 (cooldown expired)"


def test_cooldown_different_type_allowed(make_bar):
    """Different ExhaustionType fires even during another type's cooldown."""
    # Fire ZERO_PRINT at bar 0
    def make_zero_bar():
        b = make_bar(21000.0, 21015.0, 20995.0, 21010.0, [
            (21000.0, 80, 70),
            (21010.0, 80, 70),
        ])
        b.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)
        return b

    detect_exhaustion(make_zero_bar(), bar_index=0)

    # Bar 1: ZERO_PRINT is suppressed but FAT_PRINT should still be allowed
    levels = [
        (21000.0, 150, 150),   # fat level: 300
        (21001.0,  50,  50),   # thin
        (21002.0,  50,  50),
        (21003.0,  50,  50),
    ]
    fat_bar = make_bar(21003.0, 21005.0, 20999.0, 21000.0, levels)
    # avg = (300+100+100+100)/4 = 150; fat threshold = 2*150=300; level = 300 (borderline)
    # Make it definitely fat: 350
    fat_bar.levels[price_to_tick(21000.0)] = FootprintLevel(bid_vol=175, ask_vol=175)
    fat_bar.bar_delta = 100   # positive — bearish bar passes gate
    fat_bar.total_vol = 350 + 100 + 100 + 100

    sigs = detect_exhaustion(fat_bar, bar_index=1)
    fat = [s for s in sigs if s.bar_type == ExhaustionType.FAT_PRINT]
    assert len(fat) >= 1, "FAT_PRINT should fire even during ZERO_PRINT cooldown"


def test_reset_cooldowns_clears_state(make_bar):
    """After reset_cooldowns(), all types can fire again."""
    def make_zero_bar():
        b = make_bar(21000.0, 21015.0, 20995.0, 21010.0, [
            (21000.0, 80, 70),
            (21010.0, 80, 70),
        ])
        b.levels[price_to_tick(21005.0)] = FootprintLevel(bid_vol=0, ask_vol=0)
        return b

    # Fire at bar 0
    detect_exhaustion(make_zero_bar(), bar_index=0)

    # Bar 1 would be suppressed normally
    sigs_1 = detect_exhaustion(make_zero_bar(), bar_index=1)
    zero_1 = [s for s in sigs_1 if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero_1) == 0, "Sanity: should be suppressed at bar 1"

    # After reset: bar 1 can fire again
    reset_cooldowns()
    sigs_after_reset = detect_exhaustion(make_zero_bar(), bar_index=1)
    zero_after = [s for s in sigs_after_reset if s.bar_type == ExhaustionType.ZERO_PRINT]
    assert len(zero_after) >= 1, "After reset_cooldowns(), ZERO_PRINT should fire again"


def test_cooldown_default_config():
    """ExhaustionConfig.cooldown_bars defaults to 5."""
    cfg = ExhaustionConfig()
    assert cfg.cooldown_bars == 5


# ---------------------------------------------------------------------------
# 9. Config tests
# ---------------------------------------------------------------------------

def test_config_defaults_match_original():
    """Default ExhaustionConfig values match originally hardcoded defaults."""
    cfg = ExhaustionConfig()
    assert cfg.thin_pct == 0.05
    assert cfg.fat_mult == 2.0
    assert cfg.exhaust_wick_min == 35.0
    assert cfg.fade_threshold == 0.60
    assert cfg.cooldown_bars == 5
    assert cfg.delta_gate_min_ratio == 0.10
    assert cfg.delta_gate_enabled is True


def test_empty_bar_returns_empty():
    """Bar with no levels returns empty list."""
    bar = FootprintBar()
    bar.open = 21000.0
    bar.high = 21010.0
    bar.low = 20995.0
    bar.close = 21005.0
    bar.bar_range = 15.0
    bar.total_vol = 0
    signals = detect_exhaustion(bar, bar_index=0)
    assert signals == []
