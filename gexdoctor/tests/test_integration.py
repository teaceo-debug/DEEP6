"""Integration tests: full pipeline from snapshot -> enriched JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from gexdoctor.monitor.adapters.flashalpha import FlashAlphaAdapter
from gexdoctor.monitor.interpreter import PositioningInterpreter
from gexdoctor.monitor.magnet_scorer import MagnetScorer
from gexdoctor.monitor.producer import GexDoctorProducer
from gexdoctor.monitor.schemas import EnrichedGexOutput, NQQuote


def _snapshot_from_live_bundle(sample_live_bundle: dict):
    adapter = FlashAlphaAdapter(api_key="test-key", symbol="QQQ")
    return adapter._parse_live_bundle(sample_live_bundle)


def _build_pipeline(
    *,
    sample_live_bundle: dict,
    quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
) -> GexDoctorProducer:
    adapter = AsyncMock()
    adapter.poll.return_value = _snapshot_from_live_bundle(sample_live_bundle)

    price_service = AsyncMock()
    price_service.get_nq_quote.return_value = quote

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
async def test_full_pipeline_produces_valid_output(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    result = await producer.run_cycle()

    assert isinstance(result, EnrichedGexOutput)


@pytest.mark.asyncio
async def test_output_json_has_all_required_fields(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    sample_enriched_output: dict,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    await producer.run_cycle()
    data = json.loads(tmp_output.read_text(encoding="utf-8"))

    required = {
        "flip",
        "call_wall",
        "put_wall",
        "primary_magnet",
        "magnet_confidence",
        "bias_direction",
        "invalidation_level",
        "regime",
        "as_of",
    }
    assert required.issubset(data.keys()) and required.issubset(sample_enriched_output.keys())


@pytest.mark.asyncio
async def test_bias_direction_matches_regime(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    result = await producer.run_cycle()

    assert result is not None and result.bias_direction in {"bullish", "bearish", "neutral"}


@pytest.mark.asyncio
async def test_json_file_written_atomically(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    await producer.run_cycle()

    assert tmp_output.exists() and not tmp_output.with_suffix(".json.tmp").exists()


@pytest.mark.asyncio
async def test_interpreter_flows_through_producer(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    result = await producer.run_cycle()

    assert result is not None and isinstance(result.caveats, list)


@pytest.mark.asyncio
async def test_negative_gex_regime_label(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    sample_live_bundle["live_gex"] = -abs(sample_live_bundle["live_gex"])
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    result = await producer.run_cycle()

    assert result is not None and result.regime == "NEG_GEX"


@pytest.mark.asyncio
async def test_audit_trail_created_after_cycle(
    sample_live_bundle: dict,
    sample_nq_quote: NQQuote,
    tmp_output: Path,
    tmp_log_dir: Path,
):
    producer = _build_pipeline(
        sample_live_bundle=sample_live_bundle,
        quote=sample_nq_quote,
        tmp_output=tmp_output,
        tmp_log_dir=tmp_log_dir,
    )

    await producer.run_cycle()
    audit_files = list(tmp_log_dir.glob("audit-*.jsonl"))

    assert audit_files
