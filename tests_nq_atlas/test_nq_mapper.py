"""Test NQ mapper math."""
import pytest
from nq_atlas.nq_mapper import map_qqq_to_nq, map_chain_levels
from nq_atlas.types import GEXResult


def test_map_qqq_to_nq_basic():
    result = map_qqq_to_nq(520.0, 518.0, 21240.0)
    assert abs(result - 21322.0) < 10  # 520/518 * 21240 ~ 21322


def test_map_qqq_to_nq_same_price():
    """When QQQ level == QQQ spot, NQ level equals NQ spot."""
    result = map_qqq_to_nq(500.0, 500.0, 21000.0)
    assert result == 21000.0


def test_map_qqq_to_nq_zero_spot_raises():
    with pytest.raises(ValueError):
        map_qqq_to_nq(500.0, 0.0, 21000.0)


def test_map_chain_levels_with_none_levels():
    gex = GEXResult(spot=520.0, flip_level=None, call_wall=525.0, put_wall=515.0, net_gex=1e9)
    levels = map_chain_levels(gex, 520.0, 21240.0)
    assert levels.gex_flip is None
    assert levels.call_wall is not None
    assert levels.put_wall is not None
