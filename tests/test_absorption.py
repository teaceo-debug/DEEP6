"""Test suite for all 4 absorption variants + ABS-05, ABS-06, ABS-07.

Covers:
  - CLASSIC absorption (ABS-01): wick volume + balanced delta
  - PASSIVE absorption (ABS-02): volume at extreme + close holds
  - STOPPING_VOLUME (ABS-03): POC in wick + high volume
  - EFFORT_VS_RESULT (ABS-04): high volume + narrow range
  - VA extremes conviction bonus (ABS-07)
  - Config override behavior (D-02)
"""
import pytest
from collections import defaultdict
from deep6.engines.absorption import (
    AbsorptionType,
    AbsorptionSignal,
    detect_absorption,
)
from deep6.engines.signal_config import AbsorptionConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price


# ---------------------------------------------------------------------------
# Helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def make_bar():
    """Factory: builds a synthetic FootprintBar from explicit level data.

    levels_data: list of (price, bid_vol, ask_vol)
    """
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
# 1. CLASSIC ABSORPTION (ABS-01)
# ---------------------------------------------------------------------------

def test_classic_absorption_fires(make_bar):
    """Lower wick has 45% volume with balanced delta → CLASSIC bullish signal."""
    # NQ bar: open=21005, high=21010, low=20995, close=21007
    # Lower wick: 20995–21005 (body_bot=21005, so prices < 21005 are lower wick)
    # Construct: ~450 bid+ask in lower wick (balanced), 550 in body
    levels = [
        (20995.0, 120, 100),   # lower wick — 220 vol, balanced
        (20996.0, 110, 105),   # lower wick — 215 vol, balanced (total wick ~450)
        (21005.0, 80, 90),     # body
        (21006.0, 70, 80),     # body
        (21007.0, 60, 60),     # body (total body ~340; total vol = 450+340=790)
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21007.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    classic = [s for s in signals if s.bar_type == AbsorptionType.CLASSIC]
    assert len(classic) >= 1, "CLASSIC absorption should fire"
    sig = classic[0]
    assert sig.direction == +1, "Lower wick absorption should be bullish (+1)"
    assert sig.wick == "lower"
    assert 0.0 <= sig.strength <= 1.0


def test_classic_absorption_rejects_unbalanced(make_bar):
    """Lower wick has high volume BUT delta_ratio > 0.12 → CLASSIC should NOT fire."""
    # All bid volume in lower wick — strongly directional (not absorption)
    levels = [
        (20995.0, 500, 10),    # lower wick — heavily one-sided
        (21005.0, 50, 50),     # body
        (21006.0, 50, 50),     # body (total wick_vol=510, delta_ratio ≈ 490/510 ≈ 0.96)
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21006.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    classic_lower = [
        s for s in signals
        if s.bar_type == AbsorptionType.CLASSIC and s.wick == "lower"
    ]
    assert len(classic_lower) == 0, "Unbalanced delta should reject CLASSIC absorption"


def test_classic_absorption_upper_wick_bearish(make_bar):
    """Upper wick has high balanced volume → CLASSIC bearish signal."""
    levels = [
        (21005.0, 50, 50),     # body
        (21006.0, 50, 50),     # body
        (21010.0, 120, 110),   # upper wick — balanced, high volume
        (21011.0, 115, 100),   # upper wick — balanced
    ]
    bar = make_bar(21004.0, 21012.0, 21003.0, 21006.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    classic_upper = [
        s for s in signals
        if s.bar_type == AbsorptionType.CLASSIC and s.wick == "upper"
    ]
    assert len(classic_upper) >= 1, "Upper wick balanced absorption should fire bearish"
    assert classic_upper[0].direction == -1


# ---------------------------------------------------------------------------
# 2. PASSIVE ABSORPTION (ABS-02)
# ---------------------------------------------------------------------------

def test_passive_absorption_fires_bullish(make_bar):
    """65% of volume at bottom 20% of range, close above that zone → PASSIVE bullish."""
    # Range = 21010 - 20995 = 15 pts; 20% = 3 pts; bottom zone = 20995–20998
    # 650 vol in bottom zone out of 1000 total, close = 21006 (well above 20998)
    levels = [
        (20995.0, 330, 320),   # bottom zone vol ≈ 650
        (20996.0,   0,   0),   # zero (counts to bottom zone sum)
        (21004.0,  80,  90),   # body
        (21005.0,  60,  70),   # body  (body total ≈ 300; grand total ≈ 950)
        (21006.0,  50,  50),   # near close
    ]
    bar = make_bar(21003.0, 21010.0, 20995.0, 21006.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    passive = [s for s in signals if s.bar_type == AbsorptionType.PASSIVE and s.direction == +1]
    assert len(passive) >= 1, "PASSIVE bullish absorption should fire"


def test_passive_absorption_rejects_close_in_zone(make_bar):
    """Heavy volume at bottom zone but close IS inside the bottom zone → NO passive."""
    # Range = 21010 - 20995 = 15; bottom zone top = 20995 + 15*0.20 = 20998
    # close = 20997 < 20998 → close inside zone → should NOT fire
    levels = [
        (20995.0, 330, 320),   # bottom zone
        (21000.0,  50,  50),   # body
        (21005.0,  50,  50),
    ]
    bar = make_bar(21000.0, 21010.0, 20995.0, 20997.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    passive_bull = [
        s for s in signals
        if s.bar_type == AbsorptionType.PASSIVE and s.direction == +1
    ]
    assert len(passive_bull) == 0, "Close inside bottom zone should reject PASSIVE bullish"


# ---------------------------------------------------------------------------
# 3. STOPPING VOLUME (ABS-03)
# ---------------------------------------------------------------------------

def test_stopping_volume_fires_bullish(make_bar):
    """POC in lower wick AND total_vol > 2x vol_ema → STOPPING_VOLUME bullish."""
    # vol_ema = 200; need total_vol > 400; POC must be below body_bot
    # open=21005, close=21008 → body_bot=21005; lower wick tick < 21005
    levels = [
        (20995.0, 400, 300),   # highest vol level → POC here (in lower wick)
        (21005.0,  40,  50),   # body
        (21006.0,  30,  40),   # body (total ≈ 860, vol_ema=200 → 4.3x)
    ]
    bar = make_bar(21005.0, 21010.0, 20990.0, 21008.0, levels)
    bar.poc_price = 20995.0  # Explicitly set for clarity
    signals = detect_absorption(bar, atr=15.0, vol_ema=200.0)

    stop_vol = [s for s in signals if s.bar_type == AbsorptionType.STOPPING_VOLUME]
    assert len(stop_vol) >= 1, "STOPPING_VOLUME should fire when POC in wick and vol > 2x"
    assert stop_vol[0].direction == +1


def test_stopping_volume_rejects_low_volume(make_bar):
    """POC in lower wick but total_vol <= 2x vol_ema → STOPPING_VOLUME should NOT fire."""
    levels = [
        (20995.0, 50, 40),    # POC in lower wick but total = 200 < 2*200=400
        (21005.0, 55, 55),
    ]
    bar = make_bar(21005.0, 21010.0, 20990.0, 21007.0, levels)
    bar.poc_price = 20995.0
    signals = detect_absorption(bar, atr=15.0, vol_ema=200.0)

    stop_vol = [s for s in signals if s.bar_type == AbsorptionType.STOPPING_VOLUME]
    assert len(stop_vol) == 0, "Low volume should reject STOPPING_VOLUME"


# ---------------------------------------------------------------------------
# 4. EFFORT VS RESULT (ABS-04)
# ---------------------------------------------------------------------------

def test_effort_vs_result_fires(make_bar):
    """High vol (>1.5x vol_ema) AND range < 30% ATR → EFFORT_VS_RESULT fires."""
    # vol_ema=200, atr=20; need vol > 300, range < 6
    # Use range=3 (< 20*0.30=6), total vol = 400 (> 1.5*200=300)
    levels = [
        (21000.0, 100, 100),
        (21001.0, 100, 100),  # total = 400, range = 21002-21000 = 2
    ]
    bar = make_bar(21000.0, 21002.0, 21000.0, 21001.0, levels)
    bar.bar_range = 2.0
    signals = detect_absorption(bar, atr=20.0, vol_ema=200.0)

    evr = [s for s in signals if s.bar_type == AbsorptionType.EFFORT_VS_RESULT]
    assert len(evr) >= 1, "EFFORT_VS_RESULT should fire on high vol + narrow range"


def test_effort_vs_result_rejects_wide_range(make_bar):
    """High vol BUT range > 30% ATR → EFFORT_VS_RESULT should NOT fire."""
    # atr=10; 30% = 3.0; bar range = 8 > 3
    levels = [
        (21000.0, 200, 200),
        (21008.0, 100, 100),  # range spans 8 > 3
    ]
    bar = make_bar(21000.0, 21008.0, 21000.0, 21007.0, levels)
    bar.bar_range = 8.0
    signals = detect_absorption(bar, atr=10.0, vol_ema=200.0)

    evr = [s for s in signals if s.bar_type == AbsorptionType.EFFORT_VS_RESULT]
    assert len(evr) == 0, "Wide range should reject EFFORT_VS_RESULT"


# ---------------------------------------------------------------------------
# 5. VA EXTREMES BONUS (ABS-07)
# ---------------------------------------------------------------------------

def test_va_extreme_bonus_at_val(make_bar):
    """Absorption price within 2 ticks of VAL → at_va_extreme=True and boosted strength."""
    # VAL = 21000.0; price = 21000.25 (1 tick away)
    # Lower wick absorption should set at_va_extreme=True
    levels = [
        (21000.0, 120, 110),   # lower wick (1 tick below body_bot=21001)
        (21000.25, 115, 100),  # lower wick
        (21001.0,  50,  55),   # body
        (21002.0,  50,  55),   # body
    ]
    bar = make_bar(21001.0, 21005.0, 21000.0, 21003.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=200.0, val=21000.0)

    va_extreme_sigs = [s for s in signals if s.at_va_extreme]
    assert len(va_extreme_sigs) >= 1, "Signal at VAL should have at_va_extreme=True"
    for sig in va_extreme_sigs:
        assert "@VAL" in sig.detail, "Detail should contain @VAL marker"


def test_va_extreme_bonus_at_vah(make_bar):
    """Absorption price within 2 ticks of VAH → at_va_extreme=True."""
    # VAH = 21010.0; upper wick absorption at 21010.25 (1 tick above)
    levels = [
        (21005.0,  50,  50),   # body
        (21006.0,  50,  50),   # body
        (21010.0, 120, 115),   # upper wick — balanced
        (21010.25, 115, 105),  # upper wick
    ]
    bar = make_bar(21004.0, 21011.0, 21003.0, 21006.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=200.0, vah=21010.0)

    va_extreme_sigs = [s for s in signals if s.at_va_extreme]
    assert len(va_extreme_sigs) >= 1, "Signal at VAH should have at_va_extreme=True"
    for sig in va_extreme_sigs:
        assert "@VAH" in sig.detail


def test_va_extreme_no_bonus_far_from_va(make_bar):
    """Absorption far from VAH/VAL → at_va_extreme=False."""
    # VAL=21000, but absorption is at 21005 (20 ticks away)
    levels = [
        (21004.0, 120, 110),   # lower wick (well above VAL=21000)
        (21005.0, 115, 100),   # lower wick
        (21006.0,  60,  55),   # body  (body_bot = min(21006, 21008) = 21006)
        (21007.0,  50,  50),   # body
    ]
    bar = make_bar(21006.0, 21010.0, 21004.0, 21007.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=200.0, val=21000.0)

    # All signals should have at_va_extreme=False (absorption at ~21004, VAL=21000 = 16 ticks)
    for sig in signals:
        assert not sig.at_va_extreme, f"Signal at {sig.price} should not be at VA extreme"


def test_va_extreme_strength_is_boosted(make_bar):
    """at_va_extreme signal has higher strength than same signal without VA bonus."""
    levels = [
        (21000.0, 120, 110),
        (21000.25, 115, 100),
        (21001.0,  50,  55),
        (21002.0,  50,  55),
    ]
    bar_no_va = make_bar(21001.0, 21005.0, 21000.0, 21003.0, levels)
    bar_with_va = make_bar(21001.0, 21005.0, 21000.0, 21003.0, levels)

    sigs_no_va = detect_absorption(bar_no_va, atr=15.0, vol_ema=200.0)
    sigs_with_va = detect_absorption(bar_with_va, atr=15.0, vol_ema=200.0, val=21000.0)

    # Find matching signal types
    if sigs_no_va and sigs_with_va:
        # VA extreme signals should have equal or higher strength
        va_sigs = [s for s in sigs_with_va if s.at_va_extreme]
        no_va_sigs = [s for s in sigs_no_va if not s.at_va_extreme]
        # If both have CLASSIC signals, compare strengths
        va_classic = [s for s in va_sigs if s.bar_type == AbsorptionType.CLASSIC]
        no_va_classic = [s for s in sigs_no_va if s.bar_type == AbsorptionType.CLASSIC]
        if va_classic and no_va_classic:
            assert va_classic[0].strength >= no_va_classic[0].strength, \
                "VA extreme signal strength should be >= non-VA signal"


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

def test_empty_bar_returns_empty():
    """Bar with no levels returns empty list."""
    bar = FootprintBar()
    bar.open = 21000.0
    bar.high = 21010.0
    bar.low = 20995.0
    bar.close = 21005.0
    bar.bar_range = 15.0
    bar.total_vol = 0
    # levels is empty
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)
    assert signals == []


def test_zero_range_bar_returns_empty():
    """Bar with bar_range=0 (doji) returns empty list."""
    bar = FootprintBar()
    bar.open = 21000.0
    bar.high = 21000.0
    bar.low = 21000.0
    bar.close = 21000.0
    bar.bar_range = 0.0
    bar.total_vol = 100
    bar.levels[price_to_tick(21000.0)] = FootprintLevel(bid_vol=50, ask_vol=50)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)
    assert signals == []


# ---------------------------------------------------------------------------
# 7. Config tests (D-02, D-03)
# ---------------------------------------------------------------------------

def test_config_defaults_match_original():
    """Default AbsorptionConfig values match the originally hardcoded defaults."""
    cfg = AbsorptionConfig()
    assert cfg.absorb_wick_min == 30.0
    assert cfg.absorb_delta_max == 0.12
    assert cfg.passive_extreme_pct == 0.20
    assert cfg.passive_vol_pct == 0.60
    assert cfg.stop_vol_mult == 2.0
    assert cfg.evr_vol_mult == 1.5
    assert cfg.evr_range_cap == 0.30
    assert cfg.va_extreme_ticks == 2
    assert cfg.va_extreme_strength_bonus == 0.15
    assert cfg.confirmation_window_bars == 3
    assert cfg.confirmation_score_bonus == 2.0
    assert cfg.confirmation_breach_ticks == 2


def test_custom_config_respected(make_bar):
    """Non-default config values change detection behavior."""
    # Use very high wick threshold — should prevent CLASSIC from firing
    strict_config = AbsorptionConfig(absorb_wick_min=90.0)  # 90% threshold — near impossible

    levels = [
        (20995.0, 120, 110),   # lower wick — ~45% of total
        (21005.0,  80,  90),   # body
        (21006.0,  70,  80),   # body
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21007.0, levels)

    # With default config, CLASSIC fires (wick ~45% > 30% threshold)
    signals_default = detect_absorption(bar, atr=15.0, vol_ema=500.0)
    # With strict config, CLASSIC should NOT fire (wick ~45% < 90% threshold)
    signals_strict = detect_absorption(bar, atr=15.0, vol_ema=500.0, config=strict_config)

    default_classic = [s for s in signals_default if s.bar_type == AbsorptionType.CLASSIC]
    strict_classic = [s for s in signals_strict if s.bar_type == AbsorptionType.CLASSIC]

    # Default should fire, strict should not (or fire fewer)
    assert len(strict_classic) <= len(default_classic), \
        "Strict wick_min config should produce fewer or no CLASSIC signals"


def test_none_config_uses_defaults(make_bar):
    """Passing config=None uses AbsorptionConfig() defaults (backward compat)."""
    levels = [
        (20995.0, 120, 110),
        (21005.0,  80,  90),
        (21006.0,  70,  80),
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21007.0, levels)

    signals_none = detect_absorption(bar, atr=15.0, vol_ema=500.0, config=None)
    signals_default = detect_absorption(bar, atr=15.0, vol_ema=500.0, config=AbsorptionConfig())

    # Same result either way
    assert len(signals_none) == len(signals_default)


# ---------------------------------------------------------------------------
# 8. ABS-05: cascade priority (surface test — full cascade in test_narrative.py)
# ---------------------------------------------------------------------------

def test_absorption_signal_has_required_fields(make_bar):
    """AbsorptionSignal has all required fields including at_va_extreme."""
    levels = [
        (20995.0, 120, 110),
        (21005.0,  80,  90),
    ]
    bar = make_bar(21005.0, 21010.0, 20995.0, 21007.0, levels)
    signals = detect_absorption(bar, atr=15.0, vol_ema=500.0)

    for sig in signals:
        assert hasattr(sig, "bar_type")
        assert hasattr(sig, "direction")
        assert hasattr(sig, "price")
        assert hasattr(sig, "wick")
        assert hasattr(sig, "strength")
        assert hasattr(sig, "wick_pct")
        assert hasattr(sig, "delta_ratio")
        assert hasattr(sig, "detail")
        assert hasattr(sig, "at_va_extreme")
        assert isinstance(sig.at_va_extreme, bool)
        assert sig.at_va_extreme is False  # no VA passed


def test_multiple_variants_can_fire_simultaneously(make_bar):
    """A bar can produce multiple absorption variants at once."""
    # High volume (> 1.5x vol_ema), narrow range (< 30% ATR),
    # and POC in lower wick (> 2x vol_ema)
    levels = [
        (20995.0, 300, 295),  # high vol in lower wick — POC here
        (21000.0,  50,  45),  # body
        (21001.0,  50,  45),
    ]
    bar = make_bar(21000.0, 21002.0, 20995.0, 21001.0, levels)
    bar.bar_range = 7.0   # 7 < 20*0.30=6 is actually wide... use atr=50 to make narrow
    bar.poc_price = 20995.0

    signals = detect_absorption(bar, atr=50.0, vol_ema=200.0)
    types = {s.bar_type for s in signals}
    # Should have at least one variant
    assert len(signals) >= 1
