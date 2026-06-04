from __future__ import annotations

from types import SimpleNamespace

import pytest

import confluence_system.equilibrium_module as eq
from confluence_system.equilibrium_module import (
    ContractRow,
    EquilibriumInputs,
    EquilibriumPayload,
    GexProfile,
    RegimeQuad,
    bs_gamma,
    classify_regime,
    compute_equilibrium,
    strike_gex,
)


def _profile(
    *,
    timeframe: str,
    net_gex: float,
    call_wall: float | None = None,
    zero_gamma: float | None = None,
    put_wall: float | None = None,
    hvl: float | None = None,
    source: str = "NDX",
) -> GexProfile:
    return GexProfile(
        timeframe=timeframe,
        net_gex=net_gex,
        call_wall=call_wall,
        zero_gamma=zero_gamma,
        put_wall=put_wall,
        hvl=hvl,
        source=source,
        stale=False,
    )


def test_bs_gamma_atm_positive():
    assert bs_gamma(100.0, 100.0, 0.5, 0.045, 0.2) > 0


def test_bs_gamma_deep_itm():
    atm = bs_gamma(100.0, 100.0, 0.5, 0.045, 0.2)
    deep_itm = bs_gamma(100.0, 80.0, 0.5, 0.045, 0.2)
    assert deep_itm < atm


def test_bs_gamma_zero_tte():
    assert bs_gamma(100.0, 100.0, 0.0, 0.045, 0.2) == 0.0


def test_strike_gex_call_positive():
    assert strike_gex("call", 100.0, 100.0, 0.5, 0.2, 100.0) > 0


def test_strike_gex_put_negative():
    assert strike_gex("put", 100.0, 100.0, 0.5, 0.2, 100.0) < 0


def test_sfv_weight_assertion():
    assert abs(eq.W_WEEKLY_ZG + eq.W_DAILY_ZG + eq.W_HVL - 1.0) < 1e-6


@pytest.mark.asyncio
async def test_equilibrium_payload_structure(monkeypatch: pytest.MonkeyPatch):
    contracts = [
        ContractRow("call", 14950.0, "2026-05-27", 200.0, 0.20, 1),
        ContractRow("put", 14950.0, "2026-05-27", 100.0, 0.20, 1),
        ContractRow("call", 15050.0, "2026-06-05", 300.0, 0.20, 5),
        ContractRow("put", 15050.0, "2026-06-05", 100.0, 0.20, 5),
    ]

    async def fake_fetch_chain(client, ticker, spot_price):
        return contracts

    monkeypatch.setattr(eq, "fetch_chain", fake_fetch_chain)
    monkeypatch.setattr(eq, "USE_QQQ_FOR_DAILY", False)

    payload = await compute_equilibrium(
        SimpleNamespace(),
        EquilibriumInputs(
            nq_price=15050.0,
            ndx_price=15000.0,
            realized_vol_5d=0.010,
            realized_vol_30d=0.012,
            implied_vol_atm=0.011,
            ema20_nq=15020.0,
            ema50_nq=14980.0,
        ),
    )

    assert isinstance(payload, EquilibriumPayload)
    assert payload.sfv is not None
    assert payload.weekly.timeframe == "WEEKLY"
    assert payload.daily.timeframe == "DAILY"
    assert "hvl" in payload.sfv_components
    assert payload.regime.institutional_bias in {
        "FADE_PREMIUM",
        "FOLLOW_MOMENTUM",
        "DEFEND_DISCOUNT",
        "CAUTION",
        "NEUTRAL",
    }


def test_regime_classifier_outputs_valid_states():
    weekly = _profile(timeframe="WEEKLY", net_gex=3_000_000_000.0, zero_gamma=15000.0, hvl=15100.0)
    daily = _profile(timeframe="DAILY", net_gex=500_000_000.0, zero_gamma=14950.0, hvl=15050.0)

    regime = classify_regime(
        weekly,
        daily,
        price=15000.0,
        realized_vol_5d=0.015,
        realized_vol_30d=0.010,
        implied_vol_atm=0.011,
        ema20=14990.0,
        ema50=14950.0,
        current_zone="EQUILIBRIUM",
    )

    assert isinstance(regime, RegimeQuad)
    assert regime.gamma_regime in {"POSITIVE", "NEGATIVE", "NEUTRAL"}
    assert regime.volatility_regime in {"EXPANSION", "CONTRACTION", "STABLE"}
    assert regime.trend_alignment in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert regime.institutional_bias in {
        "FADE_PREMIUM",
        "FOLLOW_MOMENTUM",
        "DEFEND_DISCOUNT",
        "CAUTION",
        "NEUTRAL",
    }


def test_classify_regime_defend_discount():
    weekly = _profile(timeframe="WEEKLY", net_gex=3_000_000_000.0, zero_gamma=15000.0, hvl=15100.0)
    daily = _profile(timeframe="DAILY", net_gex=0.0, zero_gamma=14950.0, hvl=15050.0)
    regime = classify_regime(
        weekly,
        daily,
        price=14800.0,
        realized_vol_5d=0.005,
        realized_vol_30d=0.010,
        implied_vol_atm=0.011,
        ema20=14850.0,
        ema50=14900.0,
        current_zone="DISCOUNT",
    )
    assert regime.institutional_bias == "DEFEND_DISCOUNT"


def test_classify_regime_fade_premium():
    weekly = _profile(timeframe="WEEKLY", net_gex=-3_000_000_000.0, zero_gamma=15000.0, hvl=15100.0)
    daily = _profile(timeframe="DAILY", net_gex=0.0, zero_gamma=14950.0, hvl=15050.0)
    regime = classify_regime(
        weekly,
        daily,
        price=15200.0,
        realized_vol_5d=0.005,
        realized_vol_30d=0.010,
        implied_vol_atm=0.011,
        ema20=15150.0,
        ema50=15100.0,
        current_zone="PREMIUM",
    )
    assert regime.institutional_bias == "FADE_PREMIUM"
