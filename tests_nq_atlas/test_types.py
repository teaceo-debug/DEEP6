"""Test types module — model construction, serialization, frozen constraints."""
import pytest
from datetime import datetime, timezone
from nq_atlas.types import (
    BiasDirection, BiasOutput, ChainSnapshot, GEXResult, NQLevels,
    OptionsContract, VannaCharmResult, FlowResult,
)


def test_bias_output_serializes():
    b = BiasOutput(
        direction=BiasDirection.BULLISH, conviction=75,
        levels=NQLevels(gex_flip=21200, call_wall=21400, put_wall=21000),
        narrative="test", updated_at=datetime.now(timezone.utc), degraded=False,
    )
    data = b.model_dump()
    assert data["direction"] == "BULLISH"
    assert data["conviction"] == 75


def test_bias_output_frozen():
    b = BiasOutput(
        direction=BiasDirection.BEARISH, conviction=40,
        levels=NQLevels(), narrative="test",
        updated_at=datetime.now(timezone.utc), degraded=False,
    )
    with pytest.raises(Exception):
        b.direction = BiasDirection.BULLISH


def test_conviction_range():
    with pytest.raises(Exception):
        BiasOutput(
            direction=BiasDirection.NEUTRAL, conviction=150,  # invalid
            levels=NQLevels(), narrative="test",
            updated_at=datetime.now(timezone.utc), degraded=False,
        )


def test_options_contract_optional_greeks():
    c = OptionsContract(symbol="QQQ", strike=520.0, expiry="2026-06-01", call_put="call")
    assert c.gamma is None
    assert c.delta is None
