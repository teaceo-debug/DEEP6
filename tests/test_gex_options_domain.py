"""Tests for GEXOptionsDomain — GEX/options bias scoring for v3 engine."""
from __future__ import annotations

import time

import pytest

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.gex_options_domain import GEXOptionsDomain, GEXSnapshot
from deep6.engines.signal_config import GEXOptionsDomainConfig


@pytest.fixture
def domain() -> GEXOptionsDomain:
    return GEXOptionsDomain()


def _snap(
    spot: float = 21000.0,
    flip: float = 20800.0,
    call_wall: float = 21200.0,
    put_wall: float = 20600.0,
    net_gex: float = 1e9,
    regime: int = 1,
    flow_dir: int = 0,
    ts: float | None = None,
) -> GEXSnapshot:
    return GEXSnapshot(
        spot=spot,
        flip_level=flip,
        call_wall=call_wall,
        put_wall=put_wall,
        net_gex=net_gex,
        regime_sign=regime,
        flow_direction=flow_dir,
        updated_at=ts if ts is not None else time.time(),
    )


# ── Cold start / unavailable ──────────────────────────────────────────


def test_none_snapshot_returns_unavailable(domain: GEXOptionsDomain) -> None:
    result = domain.compute(None)
    assert result.available is False
    assert result.score == 0
    assert result.max_range == 0
    assert result.detail["reason"] == "gex_unavailable"


def test_zero_price_returns_unavailable(domain: GEXOptionsDomain) -> None:
    snap = _snap(spot=0.0)
    result = domain.compute(snap)
    assert result.available is False


# ── Wall proximity scoring ────────────────────────────────────────────


def test_near_call_wall_is_bearish(domain: GEXOptionsDomain) -> None:
    """Price near call wall = resistance = bearish component."""
    snap = _snap(spot=21180.0, call_wall=21200.0, put_wall=20600.0)
    result = domain.compute(snap)
    wall_component = result.detail["wall_component"]
    assert wall_component == -1


def test_near_put_wall_is_bullish(domain: GEXOptionsDomain) -> None:
    """Price near put wall = support = bullish component."""
    snap = _snap(spot=20620.0, call_wall=21200.0, put_wall=20600.0)
    result = domain.compute(snap)
    wall_component = result.detail["wall_component"]
    assert wall_component == 1


def test_middle_of_walls_is_neutral(domain: GEXOptionsDomain) -> None:
    """Price in middle of walls = no directional signal."""
    snap = _snap(spot=20900.0, call_wall=21200.0, put_wall=20600.0)
    result = domain.compute(snap)
    wall_component = result.detail["wall_component"]
    assert wall_component == 0


# ── Flip relationship scoring ─────────────────────────────────────────


def test_above_flip_positive_gamma_is_bullish(domain: GEXOptionsDomain) -> None:
    """Above flip in positive gamma = bullish."""
    snap = _snap(spot=21000.0, flip=20800.0, regime=1)
    result = domain.compute(snap)
    flip_component = result.detail["flip_component"]
    assert flip_component == 1


def test_below_flip_negative_gamma_is_bearish(domain: GEXOptionsDomain) -> None:
    """Below flip in negative gamma = bearish."""
    snap = _snap(spot=20700.0, flip=20800.0, regime=-1)
    result = domain.compute(snap)
    flip_component = result.detail["flip_component"]
    assert flip_component == -1


def test_above_flip_negative_gamma_is_bullish(domain: GEXOptionsDomain) -> None:
    """Above flip in negative gamma = bullish (trending up)."""
    snap = _snap(spot=21000.0, flip=20800.0, regime=-1)
    result = domain.compute(snap)
    flip_component = result.detail["flip_component"]
    assert flip_component == 1


# ── Flow scoring ──────────────────────────────────────────────────────


def test_bullish_flow_adds_one(domain: GEXOptionsDomain) -> None:
    snap = _snap(flow_dir=1)
    result = domain.compute(snap)
    assert result.detail["flow_component"] == 1


def test_bearish_flow_subtracts_one(domain: GEXOptionsDomain) -> None:
    snap = _snap(flow_dir=-1)
    result = domain.compute(snap)
    assert result.detail["flow_component"] == -1


def test_neutral_flow_is_zero(domain: GEXOptionsDomain) -> None:
    snap = _snap(flow_dir=0)
    result = domain.compute(snap)
    assert result.detail["flow_component"] == 0


# ── Composite scoring ─────────────────────────────────────────────────


def test_all_bullish_components_sum_to_three(domain: GEXOptionsDomain) -> None:
    """Near put wall + above flip + bullish flow = +3."""
    snap = _snap(
        spot=20620.0,
        flip=20600.0,
        call_wall=21200.0,
        put_wall=20600.0,
        regime=1,
        flow_dir=1,
    )
    result = domain.compute(snap)
    assert result.score == 3
    assert result.max_range == 3
    assert result.available is True


def test_all_bearish_components_sum_to_negative_three(domain: GEXOptionsDomain) -> None:
    """Near call wall + below flip + bearish flow = -3."""
    snap = _snap(
        spot=21180.0,
        flip=21200.0,
        call_wall=21200.0,
        put_wall=20600.0,
        regime=1,
        flow_dir=-1,
    )
    result = domain.compute(snap)
    assert result.score == -3


def test_score_clamped_to_range(domain: GEXOptionsDomain) -> None:
    """Score must never exceed ±3."""
    snap = _snap(
        spot=20620.0,
        flip=20600.0,
        call_wall=21200.0,
        put_wall=20600.0,
        regime=1,
        flow_dir=1,
    )
    result = domain.compute(snap)
    assert -3 <= result.score <= 3


# ── Staleness ─────────────────────────────────────────────────────────


def test_fresh_data_not_stale(domain: GEXOptionsDomain) -> None:
    snap = _snap(ts=time.time())
    result = domain.compute(snap)
    assert result.stale is False


def test_old_data_is_stale(domain: GEXOptionsDomain) -> None:
    snap = _snap(ts=time.time() - 300)
    result = domain.compute(snap)
    assert result.stale is True


def test_custom_staleness_threshold() -> None:
    config = GEXOptionsDomainConfig(stale_threshold_sec=10.0)
    domain = GEXOptionsDomain(config)
    snap = _snap(ts=time.time() - 15)
    result = domain.compute(snap)
    assert result.stale is True


# ── Domain metadata ───────────────────────────────────────────────────


def test_domain_name_is_gex(domain: GEXOptionsDomain) -> None:
    snap = _snap()
    result = domain.compute(snap)
    assert result.domain == "gex"


def test_nq_price_override(domain: GEXOptionsDomain) -> None:
    """nq_price should override snapshot.spot."""
    snap = _snap(spot=500.0)  # QQQ price
    result = domain.compute(snap, nq_price=21000.0)
    assert result.detail["spot"] == 21000.0
    assert result.available is True
