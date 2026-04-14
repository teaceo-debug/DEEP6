"""Tests for SlingshotDetector (Phase 12-03 TRAP_SHOT at bit 44).

TRAP_SHOT is a multi-bar trapped-trader reversal pattern — different from
the existing DELT_SLINGSHOT (bit 28, intra-bar compressed→explosive). The
two patterns coexist; bit 28 is NOT touched by this plan.

Design contract (from 12-03-PLAN.md):
  - 2/3/4-bar bull and bear variants
  - Z-score threshold > 2.0 over session-bounded delta history
  - 30-bar warmup gate
  - delta_history resets at RTH session boundary (prevents cross-session drift)
  - triggers_state_bypass set True when firing within gex_proximity_ticks of a wall
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------
# Import surface (T-12-03-01 RED: these will fail until T-12-03-02 lands)
# --------------------------------------------------------------------------
def test_slingshot_detector_importable():
    from deep6.orderflow.slingshot import SlingshotDetector, SlingshotResult  # noqa: F401


def test_slingshot_result_exports_expected_fields():
    from deep6.orderflow.slingshot import SlingshotResult
    # dataclass fields — verify they exist by constructing a neutral result
    r = SlingshotResult(
        fired=False, variant=0, direction=None,
        bias=0.0, strength=0.0, triggers_state_bypass=False,
    )
    assert r.fired is False
    assert r.variant == 0
    assert r.direction is None
    assert r.triggers_state_bypass is False


# --------------------------------------------------------------------------
# Test fixtures — synthetic bars
# --------------------------------------------------------------------------
class _SyntheticBar:
    """Minimal bar shape the detector + on_bar_close logger need.

    Detector fields: open, high, low, close, bar_delta.
    Logger fields: timestamp, cvd, poc_price, total_vol, bar_range.
    Using an ad-hoc class (not FootprintBar) keeps unit tests hermetic.
    """
    __slots__ = ("open", "high", "low", "close", "bar_delta",
                 "timestamp", "cvd", "poc_price", "total_vol", "bar_range")

    def __init__(self, open, high, low, close, bar_delta):
        self.open = float(open)
        self.high = float(high)
        self.low = float(low)
        self.close = float(close)
        self.bar_delta = int(bar_delta)
        # Logger attributes (SharedState.on_bar_close reads these).
        self.timestamp = 0.0
        self.cvd = 0
        self.poc_price = 0.0
        self.total_vol = 0
        self.bar_range = float(high) - float(low)


def _warmup_history(detector, n=35, base_delta=50):
    """Feed `n` low-volatility deltas so std is small and the warmup gate clears."""
    for i in range(n):
        # Small alternating deltas to build std ≈ base_delta
        detector.update_history(base_delta if i % 2 == 0 else -base_delta)


def _bull_2bar_template(extreme_delta: int):
    """Reference impl line 296-307 — b[-2] bearish + negative extreme,
    b[-1] bullish closes above b[-2].high with positive extreme."""
    b2 = _SyntheticBar(open=100.0, high=100.5, low=98.0, close=98.5,
                       bar_delta=-extreme_delta)
    b1 = _SyntheticBar(open=98.8, high=102.0, low=98.6, close=101.5,
                       bar_delta=extreme_delta)
    return [b2, b1]


def _bear_2bar_template(extreme_delta: int):
    """Mirror of bull: b[-2] bullish + positive extreme, b[-1] bearish
    closes below b[-2].low with negative extreme."""
    b2 = _SyntheticBar(open=98.0, high=101.5, low=97.5, close=101.0,
                       bar_delta=extreme_delta)
    b1 = _SyntheticBar(open=100.8, high=101.0, low=96.5, close=97.0,
                       bar_delta=-extreme_delta)
    return [b2, b1]


# --------------------------------------------------------------------------
# Core detection tests
# --------------------------------------------------------------------------
def test_2bar_bull_fires():
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)
    bars = _bull_2bar_template(extreme_delta=400)  # well above 2σ
    result = det.detect(bars, gex_distance_ticks=None)
    assert result.fired is True
    assert result.variant == 2
    assert result.direction == "LONG"
    assert result.bias > 0
    assert result.triggers_state_bypass is False  # no GEX context


def test_2bar_bear_fires():
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)
    bars = _bear_2bar_template(extreme_delta=400)
    result = det.detect(bars, gex_distance_ticks=None)
    assert result.fired is True
    assert result.variant == 2
    assert result.direction == "SHORT"
    assert result.bias < 0


def test_3bar_bull_fires():
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)
    # b3 bearish with neg extreme; b2 consolidates below b3.high;
    # b1 bullish closes above b3.high.
    b3 = _SyntheticBar(open=100.0, high=100.5, low=97.5, close=97.8, bar_delta=-400)
    b2 = _SyntheticBar(open=98.0, high=100.3, low=97.0, close=99.5, bar_delta=20)
    b1 = _SyntheticBar(open=99.5, high=102.0, low=99.3, close=101.5, bar_delta=400)
    result = det.detect([b3, b2, b1], gex_distance_ticks=None)
    assert result.fired is True
    assert result.variant == 3
    assert result.direction == "LONG"


def test_4bar_bull_fires():
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)
    b4 = _SyntheticBar(open=100.0, high=100.5, low=97.0, close=97.5, bar_delta=-400)
    b3 = _SyntheticBar(open=97.8, high=100.0, low=97.0, close=99.5, bar_delta=10)
    b2 = _SyntheticBar(open=99.5, high=100.4, low=98.5, close=99.8, bar_delta=-5)
    b1 = _SyntheticBar(open=99.9, high=103.0, low=99.7, close=102.5, bar_delta=400)
    result = det.detect([b4, b3, b2, b1], gex_distance_ticks=None)
    assert result.fired is True
    assert result.variant == 4
    assert result.direction == "LONG"


def test_below_threshold_no_fire():
    """Delta magnitudes under the 2σ threshold must NOT fire."""
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)  # σ ≈ 50, threshold ≈ 100
    bars = _bull_2bar_template(extreme_delta=60)  # below 2σ
    result = det.detect(bars, gex_distance_ticks=None)
    assert result.fired is False


def test_warmup_30_bars():
    """Fewer than 30 bars of delta_history → no fire even if pattern matches."""
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    for _ in range(15):  # under warmup threshold
        det.update_history(50)
    bars = _bull_2bar_template(extreme_delta=400)
    result = det.detect(bars, gex_distance_ticks=None)
    assert result.fired is False


def test_session_reset_clears_history():
    """reset_session() must clear delta_history AND force warmup restart."""
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector()
    _warmup_history(det, n=40, base_delta=50)
    assert len(det.delta_history) >= 30
    det.reset_session()
    assert len(det.delta_history) == 0
    # Pattern must NOT fire immediately after reset — warmup restarts.
    bars = _bull_2bar_template(extreme_delta=400)
    result = det.detect(bars, gex_distance_ticks=None)
    assert result.fired is False


def test_gex_proximity_sets_bypass():
    """Firing with gex_distance_ticks < gex_proximity_ticks → triggers_state_bypass."""
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector(gex_proximity_ticks=8)
    _warmup_history(det, n=40, base_delta=50)
    bars = _bull_2bar_template(extreme_delta=400)
    result = det.detect(bars, gex_distance_ticks=3.0)
    assert result.fired is True
    assert result.triggers_state_bypass is True


def test_gex_far_does_not_bypass():
    from deep6.orderflow.slingshot import SlingshotDetector
    det = SlingshotDetector(gex_proximity_ticks=8)
    _warmup_history(det, n=40, base_delta=50)
    bars = _bull_2bar_template(extreme_delta=400)
    result = det.detect(bars, gex_distance_ticks=50.0)  # far from wall
    assert result.fired is True
    assert result.triggers_state_bypass is False


def test_coexists_with_delt_slingshot():
    """TRAP_SHOT (bit 44) and DELT_SLINGSHOT (bit 28) are independent.

    Importing one must not affect the other; the bit values are distinct.
    """
    from deep6.signals.flags import SignalFlags
    assert int(SignalFlags.TRAP_SHOT) == 1 << 44
    assert int(SignalFlags.DELT_SLINGSHOT) == 1 << 28
    assert int(SignalFlags.TRAP_SHOT) != int(SignalFlags.DELT_SLINGSHOT)


# --------------------------------------------------------------------------
# Integration tests — SharedState wiring (T-12-03-03)
# --------------------------------------------------------------------------
def _make_state():
    """Build a minimal SharedState with an in-memory persistence db."""
    from deep6.config import Config
    from deep6.state.shared import SharedState
    cfg = Config(
        rithmic_user="test",
        rithmic_password="test",
        rithmic_system_name="Rithmic Test",
        rithmic_uri="wss://localhost:0",
        db_path=":memory:",
    )
    return SharedState.build(cfg)


def _feed_history(detector, n=40, base_delta=50):
    for i in range(n):
        detector.update_history(base_delta if i % 2 == 0 else -base_delta)


@pytest.mark.asyncio
async def test_end_to_end_flag_set_1m():
    """After warmup, a 2-bar bull template driven through on_bar_close
    produces a TRAP_SHOT fire in last_slingshot_1m."""
    from deep6.signals.flags import SignalFlags
    state = _make_state()
    # Pre-seed warmup on the 1m detector directly — faster than feeding 30
    # synthetic bars through on_bar_close.
    _feed_history(state.slingshot_1m, n=40, base_delta=50)

    bars = _bull_2bar_template(extreme_delta=400)
    # Must push the first bar through on_bar_close so it lands in the cache.
    await state.on_bar_close("1m", bars[0])
    await state.on_bar_close("1m", bars[1])

    assert state.last_slingshot_1m is not None
    assert state.last_slingshot_1m.fired is True
    assert state.last_slingshot_1m.variant == 2
    assert state.last_slingshot_1m.direction == "LONG"
    # Confirm bit 44 mask is what _run_slingshot returns. Call the private
    # helper directly with the template (replaces the cache) to get a
    # deterministic mask.
    state._bar_cache_1m.clear()
    state._run_slingshot("1m", bars[0])
    flag_mask = state._run_slingshot("1m", bars[1])
    assert (flag_mask & int(SignalFlags.TRAP_SHOT)) == int(SignalFlags.TRAP_SHOT)


@pytest.mark.asyncio
async def test_end_to_end_flag_set_5m_independent():
    """5m detector has its own history — feeding 1m must not arm 5m."""
    state = _make_state()
    _feed_history(state.slingshot_1m, n=40, base_delta=50)
    # 5m has zero history still → warmup gates fire even on perfect pattern.
    bars = _bull_2bar_template(extreme_delta=400)
    await state.on_bar_close("5m", bars[0])
    await state.on_bar_close("5m", bars[1])
    assert state.last_slingshot_5m is not None
    assert state.last_slingshot_5m.fired is False  # 5m still in warmup


def test_on_session_reset_clears_detectors():
    """SharedState.on_session_reset clears BOTH timeframe histories + caches."""
    state = _make_state()
    _feed_history(state.slingshot_1m, n=40, base_delta=50)
    _feed_history(state.slingshot_5m, n=40, base_delta=50)
    state._bar_cache_1m.append("sentinel")
    state._bar_cache_5m.append("sentinel")
    assert len(state.slingshot_1m.delta_history) > 0
    assert len(state.slingshot_5m.delta_history) > 0

    state.on_session_reset()

    assert len(state.slingshot_1m.delta_history) == 0
    assert len(state.slingshot_5m.delta_history) == 0
    assert state._bar_cache_1m == []
    assert state._bar_cache_5m == []
    assert state.last_slingshot_1m is None
    assert state.last_slingshot_5m is None


@pytest.mark.asyncio
async def test_gex_distance_provider_triggers_bypass():
    """When state.gex_distance_provider returns a small value, the fired
    result has triggers_state_bypass=True."""
    state = _make_state()
    _feed_history(state.slingshot_1m, n=40, base_delta=50)
    state.gex_distance_provider = lambda: 2.0  # within default 8-tick proximity

    bars = _bull_2bar_template(extreme_delta=400)
    await state.on_bar_close("1m", bars[0])
    await state.on_bar_close("1m", bars[1])

    assert state.last_slingshot_1m.fired is True
    assert state.last_slingshot_1m.triggers_state_bypass is True


@pytest.mark.asyncio
async def test_gex_provider_exception_does_not_break_bar_close():
    """A misbehaving GEX provider must not break the bar-close path —
    slingshot should still fire with triggers_state_bypass=False."""
    state = _make_state()
    _feed_history(state.slingshot_1m, n=40, base_delta=50)
    def _boom():
        raise RuntimeError("gex fetch failed")
    state.gex_distance_provider = _boom

    bars = _bull_2bar_template(extreme_delta=400)
    await state.on_bar_close("1m", bars[0])
    await state.on_bar_close("1m", bars[1])

    assert state.last_slingshot_1m.fired is True
    assert state.last_slingshot_1m.triggers_state_bypass is False
