from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

import confluence_system.confluence_server as cs
from confluence_system.confluence_server import (
    CompositeLayer,
    DarkPoolLayer,
    GexLayer,
    MtfLayer,
    RegimeLayer,
    compute_dp_from_options,
    compute_regime_local,
    detect_alert,
    normalize_dp,
    normalize_gex,
    normalize_mtf,
    normalize_regime,
)
from nq_atlas.state import AtlasState


def test_weight_assertion_passes():
    assert abs(cs.W_DP + cs.W_GEX + cs.W_REGIME + cs.W_MTF - 1.0) < 1e-6


def test_weight_assertion_fails_with_bad_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("W_DP", "0.60")
    monkeypatch.setenv("W_GEX", "0.25")
    monkeypatch.setenv("W_REGIME", "0.20")
    monkeypatch.setenv("W_MTF", "0.15")

    source = Path(cs.__file__).read_text(encoding="utf-8")
    source = source.replace("W_DP        = 0.40", "W_DP        = 0.60")
    bad_file = tmp_path / "bad_confluence_server.py"
    bad_file.write_text(source, encoding="utf-8")

    spec = importlib.util.spec_from_file_location("bad_confluence_server", bad_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(AssertionError, match="weights must sum to 1.0"):
        spec.loader.exec_module(module)


def test_normalize_dp_bullish():
    dp = DarkPoolLayer(raw_offex_pct=0.42, dp_vwap=99.5, bias="BULLISH", confidence=0.8, stale=False)
    assert normalize_dp(dp, 100.0) > 0


def test_normalize_dp_bearish():
    dp = DarkPoolLayer(raw_offex_pct=0.45, dp_vwap=100.8, bias="BEARISH", confidence=0.9, stale=False)
    assert normalize_dp(dp, 100.0) < 0


def test_normalize_dp_neutral():
    dp = DarkPoolLayer(raw_offex_pct=0.35, dp_vwap=100.0, bias="NEUTRAL", confidence=0.0, stale=False)
    assert normalize_dp(dp, 100.0) == pytest.approx(0.0)


def test_normalize_gex_above_flip():
    gex = GexLayer(flip=15000.0, call_wall=15100.0, put_wall=14900.0, net_gex=1_000_000.0, bias="BULLISH")
    assert normalize_gex(gex, 15050.0) > 0


def test_normalize_gex_below_flip():
    gex = GexLayer(flip=15000.0, call_wall=15100.0, put_wall=14900.0, net_gex=-1_000_000.0, bias="BEARISH")
    assert normalize_gex(gex, 14950.0) < 0


def test_normalize_regime_risk_on():
    regime = RegimeLayer(
        macro="RISK_ON",
        vol_regime="LOW",
        thesis_trend="BUILDING",
        pcr_bias="CALL_HEAVY",
        stale=False,
    )
    assert normalize_regime(regime) > 0


def test_normalize_regime_risk_off():
    regime = RegimeLayer(
        macro="RISK_OFF",
        vol_regime="EXTREME",
        thesis_trend="BREAKING",
        pcr_bias="PUT_HEAVY",
        stale=False,
    )
    assert normalize_regime(regime) < 0


def test_normalize_mtf_all_premium():
    mtf = MtfLayer(daily="PREMIUM", h4="PREMIUM", chart="PREMIUM")
    assert normalize_mtf(mtf) == pytest.approx(-1.0)


def test_normalize_mtf_all_discount():
    mtf = MtfLayer(daily="DISCOUNT", h4="DISCOUNT", chart="DISCOUNT")
    assert normalize_mtf(mtf) == pytest.approx(1.0)


def test_detect_alert_stop_buying():
    gex = GexLayer(bias="BULLISH")
    dp = DarkPoolLayer(bias="BEARISH", confidence=0.8, stale=False)
    regime = RegimeLayer(macro="NEUTRAL", stale=False)
    composite = CompositeLayer()
    mtf = MtfLayer(daily="PREMIUM", h4="EQUILIBRIUM", chart="PREMIUM")

    alert, reason = detect_alert(1, gex, dp, regime, composite, mtf, 15000.0)

    assert alert == "STOP_BUYING"
    assert "premium zone" in reason


def test_compute_dp_from_options_empty():
    state = AtlasState()
    result = compute_dp_from_options(state)
    assert result.stale is True


def test_compute_dp_from_options_bullish_call_heavy():
    chain = SimpleNamespace(
        contracts=[
            SimpleNamespace(call_put="call", oi=300),
            SimpleNamespace(call_put="call", oi=200),
            SimpleNamespace(call_put="put", oi=100),
        ]
    )
    state = SimpleNamespace(chain=chain, last_chain_ts=1710000000.0)

    result = compute_dp_from_options(state)

    assert result.stale is False
    assert result.bias == "BULLISH"
    assert result.total_block_val == pytest.approx(600.0)
    assert result.confidence > 0.5


def test_compute_regime_local_risk_on():
    chain = SimpleNamespace(
        contracts=[
            SimpleNamespace(call_put="call", oi=300),
            SimpleNamespace(call_put="call", oi=200),
            SimpleNamespace(call_put="put", oi=100),
        ]
    )
    state = SimpleNamespace(
        chain=chain,
        gex=SimpleNamespace(flip_level=15000.0),
        spots={"VIX": 12.0},
        last_chain_ts=1710000000.0,
    )

    regime = compute_regime_local(state, 15100.0)

    assert regime.stale is False
    assert regime.macro == "RISK_ON"
    assert regime.vol_regime == "LOW"
    assert regime.pcr_bias == "CALL_HEAVY"
    assert regime.thesis_trend == "BUILDING"


def test_detect_alert_full_send_long():
    gex = GexLayer(bias="BULLISH")
    dp = DarkPoolLayer(bias="BULLISH", confidence=0.9, stale=False)
    regime = RegimeLayer(macro="RISK_ON", stale=False)
    composite = CompositeLayer()
    mtf = MtfLayer(daily="DISCOUNT", h4="DISCOUNT", chart="DISCOUNT")

    alert, reason = detect_alert(3, gex, dp, regime, composite, mtf, 15000.0)

    assert alert == "FULL_SEND_LONG"
    assert "aligned bullish" in reason
