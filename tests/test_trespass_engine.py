"""Tests for E2 TrespassEngine (ENG-02) — multi-level weighted DOM queue imbalance."""
import pytest
from deep6.engines.trespass import TrespassEngine, TrespassResult
from deep6.engines.signal_config import TrespassConfig
from deep6.state.dom import LEVELS


def _make_snapshot(bid_sizes, ask_sizes, n=10):
    """Build a synthetic DOM snapshot with given bid/ask sizes for top N levels."""
    bid_prices = [21000.0 - i * 0.25 for i in range(LEVELS)]
    ask_prices = [21000.25 + i * 0.25 for i in range(LEVELS)]
    # Pad or truncate to LEVELS
    b_sizes = list(bid_sizes) + [0.0] * (LEVELS - len(bid_sizes))
    a_sizes = list(ask_sizes) + [0.0] * (LEVELS - len(ask_sizes))
    return (bid_prices, b_sizes, ask_prices, a_sizes)


class TestTrespassConfig:
    def test_default_config_fields(self):
        cfg = TrespassConfig()
        assert cfg.trespass_depth == 10
        assert cfg.bull_ratio_threshold == 1.2
        assert cfg.bear_ratio_threshold == 0.8

    def test_config_is_frozen(self):
        cfg = TrespassConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.trespass_depth = 5  # type: ignore


class TestTrespassEngineInit:
    def test_default_instantiation(self):
        e = TrespassEngine()
        assert e is not None

    def test_weights_pre_computed(self):
        e = TrespassEngine()
        assert len(e._weights) == LEVELS
        assert e._weights[0] == pytest.approx(1.0)
        assert e._weights[1] == pytest.approx(0.5)
        assert e._weights[2] == pytest.approx(1.0 / 3)

    def test_custom_config(self):
        cfg = TrespassConfig(trespass_depth=5)
        e = TrespassEngine(cfg)
        assert e.config.trespass_depth == 5


class TestTrespassEngineNeutralFallback:
    """D-13: Return neutral when DOM is unavailable."""

    def test_process_none_returns_neutral(self):
        e = TrespassEngine()
        r = e.process(None)
        assert isinstance(r, TrespassResult)
        assert r.direction == 0
        assert r.imbalance_ratio == pytest.approx(1.0)
        assert r.probability == pytest.approx(0.5)
        assert r.detail == "DOM_UNAVAILABLE"

    def test_process_all_zeros_returns_neutral(self):
        e = TrespassEngine()
        snap = _make_snapshot([0.0] * LEVELS, [0.0] * LEVELS)
        r = e.process(snap)
        assert r.direction == 0
        assert r.imbalance_ratio == pytest.approx(1.0)
        assert r.detail == "DOM_EMPTY"


class TestTrespassEngineDirectional:
    def test_balanced_sides_returns_neutral(self):
        e = TrespassEngine()
        # Equal sizes on both sides → ratio = 1.0 → direction = 0
        snap = _make_snapshot([50.0] * 10, [50.0] * 10)
        r = e.process(snap)
        assert r.direction == 0
        assert r.imbalance_ratio == pytest.approx(1.0)

    def test_heavy_bid_returns_bull(self):
        e = TrespassEngine()
        # 100 contracts bid vs 10 ask → ratio >> 1.2 → direction = +1
        snap = _make_snapshot([100.0] * 10 + [0.0] * 30, [10.0] * 10 + [0.0] * 30)
        r = e.process(snap)
        assert r.direction == 1
        assert r.imbalance_ratio > 1.2
        assert r.probability > 0.5

    def test_heavy_ask_returns_bear(self):
        e = TrespassEngine()
        # 10 contracts bid vs 100 ask → ratio << 0.8 → direction = -1
        snap = _make_snapshot([10.0] * 10 + [0.0] * 30, [100.0] * 10 + [0.0] * 30)
        r = e.process(snap)
        assert r.direction == -1
        assert r.imbalance_ratio < 0.8
        assert r.probability < 0.5

    def test_directional_test_from_plan_verification(self):
        """Exact test from plan verification block."""
        e = TrespassEngine()
        snap = ([21000.0] * 40, [100.0] * 10 + [0.0] * 30, [21000.25] * 40, [10.0] * 10 + [0.0] * 30)
        r = e.process(snap)
        assert r.direction == 1, f"Expected bull direction, got {r.direction}"


class TestTrespassEngineDepthGradient:
    def test_depth_gradient_computed(self):
        e = TrespassEngine()
        # Thinning book: first level 100, falls off
        bid_sizes = [100.0, 80.0, 60.0, 40.0, 20.0, 10.0, 5.0, 2.0, 1.0, 0.5] + [0.0] * 30
        ask_sizes = [50.0] * 10 + [0.0] * 30
        snap = _make_snapshot(bid_sizes, ask_sizes)
        r = e.process(snap)
        # depth_gradient = (bid[0] - bid[depth-1]) / depth = (100 - 0.5) / 10 = 9.95
        assert r.depth_gradient == pytest.approx((100.0 - 0.5) / 10, rel=1e-6)

    def test_flat_book_zero_gradient(self):
        e = TrespassEngine()
        snap = _make_snapshot([50.0] * 10 + [0.0] * 30, [50.0] * 10 + [0.0] * 30)
        r = e.process(snap)
        assert r.depth_gradient == pytest.approx(0.0)


class TestTrespassResultFields:
    def test_result_has_all_fields(self):
        r = TrespassResult(imbalance_ratio=1.0, direction=0, probability=0.5,
                           depth_gradient=0.0, detail="")
        assert hasattr(r, "imbalance_ratio")
        assert hasattr(r, "direction")
        assert hasattr(r, "probability")
        assert hasattr(r, "depth_gradient")
        assert hasattr(r, "detail")
