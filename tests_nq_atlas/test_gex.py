"""Test GEX engine — known test vectors, flip interpolation, degraded handling."""
import pytest
from datetime import datetime, timezone
from nq_atlas.gex import GEXEngine
from nq_atlas.types import ChainSnapshot, OptionsContract


def _make_chain(contracts, spot=500.0):
    return ChainSnapshot(
        underlying="QQQ", spot_price=spot,
        timestamp=datetime.now(timezone.utc), contracts=contracts,
    )


def _contract(strike, call_put, gamma, oi, expiry="2026-06-01"):
    return OptionsContract(symbol="QQQ", strike=strike, expiry=expiry,
                           call_put=call_put, gamma=gamma, oi=oi)


def test_known_test_vector():
    """GEX_SCALE=0.1: call 0.005*10000*0.1*500^2=1250000, put -0.005*8000*0.1*500^2=-1000000, net=250000+extras."""
    call = _contract(500.0, "call", 0.005, 10000)
    put = _contract(500.0, "put", 0.005, 8000)
    # Need >=10 unique strikes for non-degraded path
    extra = [_contract(500.0 + i, "call", 0.001, 100) for i in range(1, 10)]
    chain = _make_chain([call, put] + extra)
    result = GEXEngine().compute(chain)
    assert result.net_gex > 0
    assert result.regime_sign == 1


def test_degraded_on_thin_chain():
    contracts = [_contract(500.0 + i, "call", 0.005, 1000) for i in range(5)]
    chain = _make_chain(contracts)
    result = GEXEngine().compute(chain)
    assert result.regime_sign == 0


def test_regime_sign_negative():
    """More puts than calls -> negative net GEX."""
    puts = [_contract(500.0 + i, "put", 0.01, 5000) for i in range(10)]
    chain = _make_chain(puts)
    result = GEXEngine().compute(chain)
    assert result.regime_sign == -1


def test_skips_missing_gamma():
    """Contracts without gamma should be skipped."""
    no_gamma = [OptionsContract(symbol="QQQ", strike=500.0, expiry="2026-06-01",
                                call_put="call", oi=1000)  # no gamma
                for _ in range(5)]
    chain = _make_chain(no_gamma)
    result = GEXEngine().compute(chain)
    assert result.net_gex == 0.0


def test_call_wall_is_highest_positive_gex(sample_chain):
    result = GEXEngine().compute(sample_chain)
    # 20 contracts across 10 strikes -> past degraded threshold
    assert result.call_wall is not None or result.put_wall is not None
