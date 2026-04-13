"""Tests for VolPatternEngine — VOLP-01..06 (6 volume pattern signal variants)."""
from __future__ import annotations

from collections import defaultdict

import pytest

from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bar(
    open_: float = 21000.0,
    high: float = 21010.0,
    low: float = 20990.0,
    close: float = 21000.0,
    bar_delta: int = 0,
    total_vol: int = 100,
    poc_price: float = 21000.0,
    levels: dict | None = None,
) -> FootprintBar:
    """Build a minimal FootprintBar for tests."""
    bar = FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        bar_delta=bar_delta,
        total_vol=total_vol,
        bar_range=high - low,
        poc_price=poc_price,
    )
    if levels is not None:
        bar.levels = levels
    else:
        # Provide minimal levels so empty-bar guard doesn't trigger
        d = defaultdict(FootprintLevel)
        d[price_to_tick(21000.0)] = FootprintLevel(bid_vol=total_vol // 2, ask_vol=total_vol // 2)
        bar.levels = d
    return bar


def make_levels(ticks_vols: dict[float, tuple[int, int]]) -> dict:
    """Build levels dict from {price: (bid_vol, ask_vol)}."""
    d = defaultdict(FootprintLevel)
    for price, (bid, ask) in ticks_vols.items():
        tick = price_to_tick(price)
        d[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return d


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_imports():
    from deep6.engines.vol_patterns import VolPatternEngine, VolPatternSignal, VolPatternType
    from deep6.engines.signal_config import VolPatternConfig
    assert VolPatternConfig
    assert VolPatternEngine


def test_vol_pattern_config_fields():
    from deep6.engines.signal_config import VolPatternConfig
    c = VolPatternConfig()
    assert hasattr(c, "vol_seq_step_ratio")
    assert hasattr(c, "vol_seq_min_bars")
    assert hasattr(c, "bubble_mult")
    assert hasattr(c, "surge_mult")
    assert hasattr(c, "surge_delta_min_ratio")
    assert hasattr(c, "poc_wave_bars")
    assert hasattr(c, "delta_velocity_mult")
    assert hasattr(c, "big_delta_level_threshold")
    # Frozen
    with pytest.raises(Exception):
        c.surge_mult = 99.9  # type: ignore[misc]


def test_vol_pattern_type_variants():
    from deep6.engines.vol_patterns import VolPatternType
    assert VolPatternType.SEQUENCING
    assert VolPatternType.BUBBLE
    assert VolPatternType.SURGE
    assert VolPatternType.POC_MOMENTUM_WAVE
    assert VolPatternType.DELTA_VELOCITY_SPIKE
    assert VolPatternType.BIG_DELTA_PER_LEVEL


def test_vol_pattern_signal_fields():
    from deep6.engines.vol_patterns import VolPatternSignal, VolPatternType
    sig = VolPatternSignal(
        pattern_type=VolPatternType.SURGE,
        direction=1,
        price=21000.0,
        strength=0.7,
        detail="test",
    )
    assert sig.pattern_type == VolPatternType.SURGE
    assert sig.direction == 1
    assert 0.0 <= sig.strength <= 1.0


# ---------------------------------------------------------------------------
# Empty bar guard
# ---------------------------------------------------------------------------

def test_empty_bar_returns_empty():
    from deep6.engines.vol_patterns import VolPatternEngine
    engine = VolPatternEngine()
    empty_bar = FootprintBar(total_vol=0)
    result = engine.process(empty_bar, bar_history=[], vol_ema=100.0, poc_history=[])
    assert result == []


def test_empty_levels_returns_empty():
    """T-04-02: empty levels dict must not crash."""
    from deep6.engines.vol_patterns import VolPatternEngine
    engine = VolPatternEngine()
    bar = FootprintBar(total_vol=0)
    bar.levels = {}
    result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
    assert result == []


# ---------------------------------------------------------------------------
# VOLP-01: Volume sequencing
# ---------------------------------------------------------------------------

class TestVolumeSequencing:
    def _make_seq_history(self, n: int = 4, base_vol: int = 100, step: float = 1.2) -> list:
        """Make bar_history where each bar's vol is step * prior vol."""
        bars = []
        vol = base_vol
        for _ in range(n):
            bars.append(make_bar(total_vol=int(vol), bar_delta=10))
            vol *= step
        return bars

    def test_fires_on_3_bar_escalating_volume(self):
        """3+ bars each with vol >= prior * 1.15 — sequencing fires."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        # 3 escalating bars: 100, 116, 134 (each >= prior * 1.15)
        history = [
            make_bar(total_vol=100, bar_delta=10),
            make_bar(total_vol=116, bar_delta=12),
        ]
        current = make_bar(total_vol=134, bar_delta=15)
        result = engine.process(current, bar_history=history, vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.SEQUENCING in pattern_types

    def test_does_not_fire_on_2_bar_sequence(self):
        """Only 2 bars qualify — below min_bars=3 threshold."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        history = [make_bar(total_vol=100, bar_delta=10)]
        current = make_bar(total_vol=116, bar_delta=12)
        result = engine.process(current, bar_history=history, vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.SEQUENCING not in pattern_types

    def test_does_not_fire_when_step_too_small(self):
        """Each bar only 5% above prior — below 15% threshold."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        history = [
            make_bar(total_vol=100, bar_delta=5),
            make_bar(total_vol=105, bar_delta=5),
        ]
        current = make_bar(total_vol=110, bar_delta=5)
        result = engine.process(current, bar_history=history, vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.SEQUENCING not in pattern_types

    def test_direction_follows_dominant_delta(self):
        """Direction = sign of dominant bar_delta in the sequence."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        # All bars with positive delta
        history = [
            make_bar(total_vol=100, bar_delta=20),
            make_bar(total_vol=116, bar_delta=22),
        ]
        current = make_bar(total_vol=134, bar_delta=25)
        result = engine.process(current, bar_history=history, vol_ema=100.0, poc_history=[])
        sig = next((s for s in result if s.pattern_type == VolPatternType.SEQUENCING), None)
        assert sig is not None
        assert sig.direction == 1


# ---------------------------------------------------------------------------
# VOLP-02: Volume bubble
# ---------------------------------------------------------------------------

class TestVolumeBubble:
    def test_fires_on_single_level_spike(self):
        """One level has vol > avg_level_vol * 4.0."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        # 4 levels: 3 with 10 vol each, 1 with 200 vol
        # avg_level_vol = 230/4 = 57.5. 200 / 57.5 = 3.48 < 4.0 — let's use 5 levels
        # 4 levels with 10 each + 1 with 400: avg = 440/5 = 88, 400/88 = 4.5 > 4.0
        levels = make_levels({
            21000.0: (5, 5),
            21005.0: (5, 5),
            21010.0: (5, 5),
            21015.0: (5, 5),
            21020.0: (200, 200),  # 400 vol at this level
        })
        bar = make_bar(
            total_vol=440,
            levels=levels,
        )
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.BUBBLE in pattern_types

    def test_does_not_fire_when_no_bubble(self):
        """All levels roughly equal — no bubble."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (50, 50),
            21005.0: (50, 50),
            21010.0: (50, 50),
        })
        bar = make_bar(total_vol=300, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.BUBBLE not in pattern_types

    def test_fires_at_bubble_price(self):
        """Signal price equals the bubble level price."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType
        from deep6.state.footprint import tick_to_price

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (5, 5),
            21005.0: (5, 5),
            21010.0: (5, 5),
            21015.0: (5, 5),
            21020.0: (200, 200),
        })
        bar = make_bar(total_vol=440, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        bubble_sigs = [s for s in result if s.pattern_type == VolPatternType.BUBBLE]
        assert len(bubble_sigs) >= 1
        assert bubble_sigs[0].price == 21020.0


# ---------------------------------------------------------------------------
# VOLP-03: Volume surge
# ---------------------------------------------------------------------------

class TestVolumeSurge:
    def test_fires_on_high_volume(self):
        """bar.total_vol > vol_ema * 3.0 — surge fires."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        bar = make_bar(total_vol=350, bar_delta=0)  # 350 > 100*3.0
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.SURGE in pattern_types

    def test_does_not_fire_below_surge_threshold(self):
        """Volume below 3× vol_ema — no surge."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        bar = make_bar(total_vol=250, bar_delta=0)  # 250 < 300 (3×100)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.SURGE not in pattern_types

    def test_direction_from_delta_when_strong(self):
        """Strong delta (>15%) → direction from delta sign."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        bar = make_bar(total_vol=350, bar_delta=70)  # 70/350 = 20% > 15%
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        sig = next(s for s in result if s.pattern_type == VolPatternType.SURGE)
        assert sig.direction == 1

    def test_direction_zero_when_delta_weak(self):
        """Weak delta (< 15%) → direction = 0 (ambiguous surge)."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        bar = make_bar(total_vol=350, bar_delta=10)  # 10/350 ≈ 3% < 15%
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        sig = next(s for s in result if s.pattern_type == VolPatternType.SURGE)
        assert sig.direction == 0


# ---------------------------------------------------------------------------
# VOLP-04: POC momentum wave
# ---------------------------------------------------------------------------

class TestPOCMomentumWave:
    def test_fires_on_3_bar_poc_migration_up(self):
        """POC has migrated upward for 3+ consecutive bars."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        # POC history: 21000, 21005, 21010 — strictly ascending
        poc_history = [21000.0, 21005.0, 21010.0]
        bar = make_bar(poc_price=21010.0)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=poc_history)
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.POC_MOMENTUM_WAVE in pattern_types

    def test_fires_on_3_bar_poc_migration_down(self):
        """POC has migrated downward for 3+ bars."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        poc_history = [21010.0, 21005.0, 21000.0]
        bar = make_bar(poc_price=21000.0)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=poc_history)
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.POC_MOMENTUM_WAVE in pattern_types

    def test_does_not_fire_when_poc_choppy(self):
        """POC oscillates — no directional wave."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        poc_history = [21000.0, 21010.0, 21000.0]
        bar = make_bar(poc_price=21000.0)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=poc_history)
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.POC_MOMENTUM_WAVE not in pattern_types

    def test_does_not_fire_insufficient_poc_history(self):
        """Not enough POC history."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        poc_history = [21000.0, 21005.0]  # only 2 entries
        bar = make_bar(poc_price=21005.0)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=poc_history)
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.POC_MOMENTUM_WAVE not in pattern_types

    def test_direction_from_poc_migration(self):
        """Direction = sign of (last_poc - first_poc_in_window)."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        poc_history = [21000.0, 21005.0, 21010.0]  # rising
        bar = make_bar(poc_price=21010.0)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=poc_history)
        sig = next(s for s in result if s.pattern_type == VolPatternType.POC_MOMENTUM_WAVE)
        assert sig.direction == 1


# ---------------------------------------------------------------------------
# VOLP-05: Delta velocity spike
# ---------------------------------------------------------------------------

class TestDeltaVelocitySpike:
    def test_fires_on_large_delta_velocity(self):
        """velocity = |current_delta - prior_delta| > vol_ema * 0.6."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        prior = make_bar(bar_delta=10, total_vol=100)
        current = make_bar(bar_delta=80, total_vol=100)
        # velocity = |80 - 10| = 70 > 100 * 0.6 = 60 → fires
        result = engine.process(current, bar_history=[prior], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.DELTA_VELOCITY_SPIKE in pattern_types

    def test_does_not_fire_when_velocity_too_small(self):
        """Small delta change — below threshold."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        prior = make_bar(bar_delta=10, total_vol=100)
        current = make_bar(bar_delta=20, total_vol=100)
        # velocity = |20 - 10| = 10 < 60
        result = engine.process(current, bar_history=[prior], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.DELTA_VELOCITY_SPIKE not in pattern_types

    def test_no_prior_bar_no_velocity_spike(self):
        """No history — can't compute velocity."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        current = make_bar(bar_delta=80, total_vol=100)
        result = engine.process(current, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.DELTA_VELOCITY_SPIKE not in pattern_types

    def test_direction_from_velocity_sign(self):
        """Direction = sign of velocity."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        prior = make_bar(bar_delta=-10, total_vol=100)
        current = make_bar(bar_delta=80, total_vol=100)
        # velocity = 80 - (-10) = +90 → direction = +1
        result = engine.process(current, bar_history=[prior], vol_ema=100.0, poc_history=[])
        sig = next(s for s in result if s.pattern_type == VolPatternType.DELTA_VELOCITY_SPIKE)
        assert sig.direction == 1


# ---------------------------------------------------------------------------
# VOLP-06: Big delta per level
# ---------------------------------------------------------------------------

class TestBigDeltaPerLevel:
    def test_fires_when_single_level_has_large_net_delta(self):
        """One level has |ask_vol - bid_vol| > 80 contracts."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (5, 90),   # net_delta = 85 > 80 threshold
            21005.0: (10, 10),
        })
        bar = make_bar(total_vol=120, bar_delta=80, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.BIG_DELTA_PER_LEVEL in pattern_types

    def test_does_not_fire_when_all_levels_small_delta(self):
        """No single level exceeds threshold."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (40, 60),  # net_delta = 20 < 80
            21005.0: (35, 55),  # net_delta = 20 < 80
        })
        bar = make_bar(total_vol=190, bar_delta=40, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.BIG_DELTA_PER_LEVEL not in pattern_types

    def test_direction_from_net_delta_sign(self):
        """Direction = sign of net_delta at the dominant level."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (5, 90),   # net_delta = +85 → direction +1
            21005.0: (10, 10),
        })
        bar = make_bar(total_vol=120, bar_delta=80, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        sig = next(s for s in result if s.pattern_type == VolPatternType.BIG_DELTA_PER_LEVEL)
        assert sig.direction == 1

    def test_direction_bear_when_bid_dominates(self):
        """Large bid volume at one level → direction -1."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        levels = make_levels({
            21000.0: (95, 5),   # net_delta = 5 - 95 = -90 → direction -1
            21005.0: (10, 10),
        })
        bar = make_bar(total_vol=120, bar_delta=-85, levels=levels)
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        sig = next(s for s in result if s.pattern_type == VolPatternType.BIG_DELTA_PER_LEVEL)
        assert sig.direction == -1

    def test_no_levels_no_big_delta(self):
        """Empty levels dict — T-04-02 guard fires."""
        from deep6.engines.vol_patterns import VolPatternEngine, VolPatternType

        engine = VolPatternEngine()
        bar = FootprintBar(total_vol=0)
        bar.levels = {}
        result = engine.process(bar, bar_history=[], vol_ema=100.0, poc_history=[])
        pattern_types = [s.pattern_type for s in result]
        assert VolPatternType.BIG_DELTA_PER_LEVEL not in pattern_types
