"""Test flow engine — aggressor classification, premium accumulation, z-score."""
import pytest
from nq_atlas.flow import FlowEngine


def test_buyer_initiated_call_is_bullish():
    engine = FlowEngine()
    engine.update({"price": 5.25, "bid": 5.10, "ask": 5.30, "volume": 10, "call_put": "call"})
    result = engine.compute()
    assert result.signed_premium_5m > 0


def test_seller_initiated_put_is_bullish():
    """Put sold by seller = aggressor=-1 * option_sign=-1 = +1 (bullish)."""
    engine = FlowEngine()
    engine.update({"price": 4.95, "bid": 5.00, "ask": 5.10, "volume": 10, "call_put": "put"})
    result = engine.compute()
    # seller-initiated put = -1 * -1 = +1 (bullish)
    assert result.signed_premium_5m > 0


def test_empty_engine_returns_zeros():
    result = FlowEngine().compute()
    assert result.signed_premium_5m == 0.0
    assert result.net_direction == 0
    assert result.z_score == 0.0


def test_net_direction_threshold():
    """Trade at midpoint gets aggressor=0, skipped entirely -> stays neutral."""
    engine = FlowEngine()
    engine.update({"price": 1.0, "bid": 0.9, "ask": 1.1, "volume": 5, "call_put": "call"})
    result = engine.compute()
    assert result.net_direction == 0


def test_mixed_flow_premium():
    engine = FlowEngine()
    # 7 call buys (price above midpoint -> aggressor=+1, call -> direction=+1)
    for _ in range(7):
        engine.update({"price": 5.15, "bid": 4.9, "ask": 5.1, "volume": 10, "call_put": "call"})
    # 3 put buys (price above midpoint -> aggressor=+1, put -> direction=-1)
    for _ in range(3):
        engine.update({"price": 3.15, "bid": 2.9, "ask": 3.1, "volume": 10, "call_put": "put"})
    result = engine.compute()
    # Call premium: 7 * 5.15 * 10 * 100 * 1 = 36050
    # Put premium: 3 * 3.15 * 10 * 100 * -1 = -9450
    # Net = 26600 > 1000 threshold -> bullish
    assert result.signed_premium_5m > 0
    assert result.net_direction == 1
