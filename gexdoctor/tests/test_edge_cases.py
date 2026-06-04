"""Edge case tests: failure modes, degraded states, unusual inputs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gexdoctor import launch
from gexdoctor.monitor.adapters.flashalpha import FlashAlphaAdapter
from gexdoctor.monitor.interpreter import PositioningInterpreter
from gexdoctor.monitor.magnet_scorer import MagnetResult, MagnetScorer
from gexdoctor.monitor.producer import GexDoctorProducer
from gexdoctor.monitor.schemas import EnrichedGexOutput, NQQuote


def _build_pipeline(adapter, price_service, *, tmp_output: Path, tmp_log_dir: Path) -> GexDoctorProducer:
    return GexDoctorProducer(
        flashalpha_adapter=adapter,
        price_service=price_service,
        scorer=MagnetScorer(),
        interpreter=PositioningInterpreter(),
        output_path=tmp_output,
        log_dir=tmp_log_dir,
        interval_sec=15,
    )


@pytest.mark.asyncio
async def test_flashalpha_down_writes_stale_json(
    sample_snapshot,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    adapter = AsyncMock()
    adapter.poll.side_effect = [sample_snapshot, None]
    price_service = AsyncMock()
    price_service.get_nq_quote.return_value = sample_nq_quote
    producer = _build_pipeline(adapter, price_service, tmp_output=tmp_output, tmp_log_dir=tmp_log_dir)

    await producer.run_cycle()
    result = await producer.run_cycle()

    assert result is not None and "stale" in result.source


def test_all_levels_null_returns_no_magnet(sample_snapshot):
    scorer = MagnetScorer()
    snapshot = sample_snapshot.model_copy(update={
        "regime": sample_snapshot.regime.model_copy(update={
            "gamma_flip": 0.0,
            "call_wall": None,
            "put_wall": None,
            "max_pain": None,
        })
    })

    result = scorer.score(snapshot, current_nq=21800.0)

    assert result.primary_magnet is None and result.magnet_confidence == 0.0


def test_pin_risk_high_0dte_selects_pin_magnet(sample_snapshot):
    scorer = MagnetScorer()
    snapshot = sample_snapshot.model_copy(update={
        "dte": 0,
        "regime": sample_snapshot.regime.model_copy(update={
            "gamma_flip": 21750.0,
            "call_wall": 21950.0,
            "put_wall": 21650.0,
            "max_pain": 21800.0,
        }),
        "pin": sample_snapshot.pin.model_copy(update={
            "pin_risk": 80.0,
            "magnet_strike": 21850.0,
        }),
    })

    result = scorer.score(snapshot, current_nq=21800.0)

    assert result.primary_magnet == 21850.0


def test_anti_flicker_rapid_score_changes_stable(sample_snapshot):
    scorer = MagnetScorer()
    base_snapshot = sample_snapshot.model_copy(update={
        "regime": sample_snapshot.regime.model_copy(update={
            "gamma_flip": 21700.0,
            "call_wall": 21980.0,
            "put_wall": 21620.0,
            "max_pain": 21840.0,
        }),
    })
    first = scorer.score(base_snapshot, current_nq=21800.0)
    second_snapshot = base_snapshot.model_copy(update={
        "regime": base_snapshot.regime.model_copy(update={"call_wall": 21970.0}),
    })
    third_snapshot = base_snapshot.model_copy(update={
        "regime": base_snapshot.regime.model_copy(update={"call_wall": 21965.0}),
    })

    second = scorer.score(second_snapshot, current_nq=21800.0)
    third = scorer.score(third_snapshot, current_nq=21800.0)

    assert first.primary_magnet == second.primary_magnet == third.primary_magnet


@pytest.mark.asyncio
async def test_nq_price_unavailable_uses_fallback(
    sample_snapshot,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    adapter = AsyncMock()
    adapter.poll.return_value = sample_snapshot
    price_service = AsyncMock()
    price_service.get_nq_quote.side_effect = RuntimeError("NQ unavailable")
    producer = _build_pipeline(adapter, price_service, tmp_output=tmp_output, tmp_log_dir=tmp_log_dir)
    producer._last_output = EnrichedGexOutput(
        instrument="NQ",
        flip=21800.0,
        call_wall=22000.0,
        put_wall=21600.0,
        net_gex=3_200_000_000.0,
        regime="POS_GEX",
        primary_magnet=21800.0,
        magnet_confidence=0.8,
        bias_direction="neutral",
        invalidation_level=21810.0,
        invalidation_reason="cached fallback",
        lean="cached fallback",
        pin_risk=45.0,
        max_pain=21780.0,
        caveats=[],
        as_of="2026-05-28T14:30:00Z",
        source="flashalpha-QQQ-x45.42",
    )

    result = await producer.run_cycle()

    assert result is not None  # cycle completes despite price failure using cached fallback


@pytest.mark.asyncio
async def test_division_by_zero_in_conversion_handled(
    sample_snapshot,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    adapter = AsyncMock()
    adapter.poll.return_value = sample_snapshot
    price_service = AsyncMock()
    price_service.get_nq_quote.return_value = NQQuote(
        nq_price=21800.0,
        qqq_price=0.0,
        nq_qqq_factor=None,
        source="polygon",
        timestamp="2026-05-28T14:30:00Z",
        stale=False,
    )
    producer = _build_pipeline(adapter, price_service, tmp_output=tmp_output, tmp_log_dir=tmp_log_dir)

    with patch("gexdoctor.monitor.producer.compute_nq_qqq_factor", side_effect=ValueError("division by zero")):
        result = await producer.run_cycle()

    assert result is not None and result.source.startswith("flashalpha-")


@pytest.mark.asyncio
async def test_malformed_flashalpha_response_adapter_returns_none():
    adapter = FlashAlphaAdapter(api_key="test-key", symbol="QQQ")

    with patch.object(adapter, "_sdk_get_live_bundle", return_value=[]), patch.object(adapter, "_httpx_get_settled", return_value=None):
        result = await adapter.poll()

    assert result is None


def test_config_missing_api_key_dry_run_fails(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join([
            "interval: 15",
            "source: QQQ",
            f"output_path: {tmp_path.as_posix()}/gex_nq.json",
            "log_dir: logs",
            "min_confidence: 0.65",
            "anti_flicker_margin: 0.12",
            "massive_api_key: ''",
        ])
        + "\n",
        encoding="utf-8",
    )

    valid, errors = launch.validate_config(config_path, {})

    assert valid is False and errors and "FLASHALPHA_API_KEY" in errors[0]


def test_magnet_below_threshold_no_magnet_status(sample_snapshot):
    scorer = MagnetScorer()
    snapshot = sample_snapshot.model_copy(update={
        "oi_simulator": sample_snapshot.oi_simulator.model_copy(update={"oi_delta_confidence": 0.1}),
        "regime": sample_snapshot.regime.model_copy(update={
            "gamma_flip": 23000.0,
            "call_wall": 23100.0,
            "put_wall": 20500.0,
            "max_pain": 23200.0,
        }),
    })

    result = scorer.score(snapshot, current_nq=21800.0)

    assert isinstance(result, MagnetResult) and result.status == "no_magnet" and result.primary_magnet is None
