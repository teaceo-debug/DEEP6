from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from gexdoctor.monitor.schemas import (
    BiasResult,
    EnrichedGexOutput,
    FADealerRisk,
    FAFeedQuality,
    FAHigherOrder,
    FAOISimulator,
    FAPinData,
    FAProfileShape,
    FARegime,
    FAVolContext,
    FlashAlphaSnapshot,
    MagnetCandidate,
    MagnetResult,
    NQQuote,
    SourceHealth,
)


def test_all_models_importable():
    assert FlashAlphaSnapshot is not None
    assert MagnetCandidate is not None
    assert MagnetResult is not None
    assert BiasResult is not None
    assert EnrichedGexOutput is not None
    assert NQQuote is not None
    assert SourceHealth is not None


def test_flashalpha_snapshot_creation():
    snapshot = FlashAlphaSnapshot(
        timestamp="2026-04-26T14:30:00Z",
        symbol="NQ",
        underlying_price=22150.5,
        session_phase="open",
        regime=FARegime(net_gex=1.0, gex_sign="positive", gamma_flip=22000.0),
    )
    assert snapshot.symbol == "NQ"
    assert snapshot.regime.gex_sign == "positive"


def test_flashalpha_snapshot_frozen():
    snapshot = FlashAlphaSnapshot(
        timestamp="2026-04-26T14:30:00Z",
        symbol="NQ",
        underlying_price=22150.5,
        session_phase="open",
        regime=FARegime(net_gex=1.0, gex_sign="positive", gamma_flip=22000.0),
    )

    with pytest.raises(ValidationError):
        snapshot.symbol = "ES"


def test_flashalpha_snapshot_serialization():
    snapshot = FlashAlphaSnapshot(
        timestamp="2026-04-26T14:30:00Z",
        symbol="NQ",
        underlying_price=22150.5,
        session_phase="intraday",
        regime=FARegime(net_gex=1.0, gex_sign="positive", gamma_flip=22000.0),
    )
    payload = json.loads(snapshot.model_dump_json())
    assert payload["symbol"] == "NQ"
    assert payload["regime"]["gamma_flip"] == 22000.0


def test_magnet_result_creation():
    result = MagnetResult(
        primary_magnet=22100.0,
        magnet_confidence=0.82,
        invalidation_level=21980.0,
        invalidation_reason="below support",
        supporting_levels=[
            MagnetCandidate(
                level=22100.0,
                level_type="call_wall",
                score=0.9,
                confidence=0.8,
                invalidation_level=21980.0,
                invalidation_reason="below support",
            )
        ],
        status="valid",
    )
    no_magnet = MagnetResult(
        primary_magnet=None,
        magnet_confidence=0.0,
        invalidation_level=None,
        invalidation_reason="none",
        supporting_levels=[],
        status="no_magnet",
    )
    assert result.supporting_levels[0].level_type == "call_wall"
    assert no_magnet.status == "no_magnet"


@pytest.mark.parametrize("direction", ["bullish", "bearish", "neutral", "no_vote"])
def test_bias_result_all_directions(direction: str):
    bias = BiasResult(
        direction=direction,
        regime="PositiveGamma",
        lean="fade downside",
        confidence_label="medium",
        caveats=["stale data"],
        price_zone="22100-22200",
    )
    assert bias.direction == direction


def test_enriched_gex_output_creation():
    output = EnrichedGexOutput(
        flip=22000.0,
        call_wall=22300.0,
        put_wall=21800.0,
        next_call=22350.0,
        next_put=21750.0,
        net_gex=5000000000.0,
        regime="PositiveGamma",
        primary_magnet=22100.0,
        magnet_confidence=0.82,
        bias_direction="bullish",
        invalidation_level=21980.0,
        invalidation_reason="below support",
        lean="bullish with caution",
        pin_risk=35.0,
        max_pain=22050.0,
        caveats=["stale data"],
        as_of="2026-04-26T14:30:00Z",
        source="flashalpha",
    )
    assert output.instrument == "NQ"
    assert output.bias_direction == "bullish"


def test_enriched_gex_output_serializable():
    output = EnrichedGexOutput(
        flip=22000.0,
        call_wall=22300.0,
        put_wall=21800.0,
        next_call=None,
        next_put=None,
        net_gex=5000000000.0,
        regime="PositiveGamma",
        primary_magnet=None,
        magnet_confidence=0.0,
        bias_direction="neutral",
        invalidation_level=None,
        invalidation_reason="none",
        lean="wait",
        pin_risk=None,
        max_pain=None,
        caveats=[],
        as_of="2026-04-26T14:30:00Z",
        source="flashalpha",
    )
    payload = json.loads(output.model_dump_json())
    restored = EnrichedGexOutput.model_validate(payload)
    assert restored.source == "flashalpha"
    assert restored.as_of == "2026-04-26T14:30:00Z"


def test_nq_quote_creation():
    quote = NQQuote(
        nq_price=22150.5,
        qqq_price=470.25,
        ndx_price=19875.0,
        nq_qqq_factor=47.0,
        nq_ndx_basis=15.5,
        source="rithmic",
        timestamp="2026-04-26T14:30:00Z",
    )
    assert quote.nq_price == 22150.5


def test_source_health_creation():
    health = SourceHealth(
        source="flashalpha",
        fresh_sec=42.0,
        stale=False,
        latency_ms=180.0,
        read_status="valid",
    )
    assert health.read_status == "valid"


def test_nested_defaults_are_constructible():
    snapshot = FlashAlphaSnapshot(
        timestamp="2026-04-26T14:30:00Z",
        symbol="NQ",
        underlying_price=22150.5,
        session_phase="pre_market",
        regime=FARegime(net_gex=1.0, gex_sign="negative", gamma_flip=22000.0),
    )
    assert snapshot.dealer_risk == FADealerRisk()
    assert snapshot.pin == FAPinData()
    assert snapshot.oi_simulator == FAOISimulator()
    assert snapshot.profile_shape == FAProfileShape()
    assert snapshot.higher_order == FAHigherOrder()
    assert snapshot.vol_context == FAVolContext()
    assert snapshot.feed_quality == FAFeedQuality()
