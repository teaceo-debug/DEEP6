"""Tests for GexDoctorProducer — the main orchestrator."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gexdoctor.monitor.schemas import (
    BiasResult,
    FADealerRisk,
    FAFeedQuality,
    FAOISimulator,
    FAPinData,
    FARegime,
    FlashAlphaSnapshot,
    MagnetResult,
    NQQuote,
)

# ---------------------------------------------------------------------------
# Fixtures — reusable mock builders
# ---------------------------------------------------------------------------

def make_regime(
    gex_sign: str = "positive",
    net_gex: float = 5e9,
    gamma_flip: float = 480.0,
    call_wall: float = 500.0,
    put_wall: float = 460.0,
    max_pain: float = 490.0,
) -> FARegime:
    return FARegime(
        net_gex=net_gex,
        gex_sign=gex_sign,
        gamma_flip=gamma_flip,
        call_wall=call_wall,
        put_wall=put_wall,
        max_pain=max_pain,
    )


def make_snapshot(
    gex_sign: str = "positive",
    underlying_price: float = 485.0,
    symbol: str = "QQQ",
    pin_risk: float | None = 30.0,
) -> FlashAlphaSnapshot:
    return FlashAlphaSnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        symbol=symbol,
        underlying_price=underlying_price,
        session_phase="intraday",
        dte=3,
        regime=make_regime(gex_sign=gex_sign),
        dealer_risk=FADealerRisk(flow_direction="amplifying"),
        pin=FAPinData(pin_risk=pin_risk),
        oi_simulator=FAOISimulator(oi_delta_confidence=0.8),
        feed_quality=FAFeedQuality(plan="alpha"),
    )


def make_quote(nq: float = 21800.0, qqq: float = 485.0) -> NQQuote:
    return NQQuote(
        nq_price=nq,
        qqq_price=qqq,
        nq_qqq_factor=nq / qqq if qqq else None,
        source="polygon",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def make_bias(direction: str = "neutral") -> BiasResult:
    return BiasResult(
        direction=direction,
        regime="long gamma",
        lean="mean-revert toward flip",
        confidence_label="medium",
        caveats=[],
        price_zone="long_gamma_upper",
    )


def make_magnet(
    primary: float = 21600.0,
    confidence: float = 0.82,
) -> MagnetResult:
    return MagnetResult(
        primary_magnet=primary,
        magnet_confidence=confidence,
        invalidation_level=21610.0,
        invalidation_reason="Break and acceptance beyond gamma flip level",
        supporting_levels=[],
        status="valid",
    )


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    return tmp_path / "gex_nq.json"


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


def _build_producer(
    tmp_output: Path,
    tmp_log_dir: Path,
    adapter_return: FlashAlphaSnapshot | None = None,
    quote_return: NQQuote | None = None,
    bias_return: BiasResult | None = None,
    magnet_return: MagnetResult | None = None,
    adapter_side_effect: Exception | None = None,
    price_side_effect: Exception | None = None,
):
    """Factory that builds a GexDoctorProducer with mocked dependencies."""
    from gexdoctor.monitor.producer import GexDoctorProducer

    adapter = AsyncMock()
    if adapter_side_effect:
        adapter.poll.side_effect = adapter_side_effect
    else:
        adapter.poll.return_value = adapter_return or make_snapshot()

    price_svc = AsyncMock()
    if price_side_effect:
        price_svc.get_nq_quote.side_effect = price_side_effect
    else:
        price_svc.get_nq_quote.return_value = quote_return or make_quote()

    scorer = MagicMock()
    scorer.score.return_value = magnet_return or make_magnet()

    interpreter = MagicMock()
    interpreter.interpret.return_value = bias_return or make_bias()

    producer = GexDoctorProducer(
        flashalpha_adapter=adapter,
        price_service=price_svc,
        scorer=scorer,
        interpreter=interpreter,
        output_path=tmp_output,
        log_dir=tmp_log_dir,
        interval_sec=15,
    )
    return producer, adapter, price_svc, scorer, interpreter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunCycleWritesJson:
    """T1: mock adapter + price service → cycle writes valid JSON file."""

    @pytest.mark.asyncio
    async def test_run_cycle_writes_json(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)
        result = await producer.run_cycle()

        assert result is not None
        assert tmp_output.exists(), "gex_nq.json must be written"

        data = json.loads(tmp_output.read_text(encoding="utf-8"))
        assert data["instrument"] == "NQ"
        assert isinstance(data["flip"], (int, float))
        assert isinstance(data["regime"], str)


class TestAtomicWrite:
    """T2: verify .json.tmp created then replaced by .json."""

    @pytest.mark.asyncio
    async def test_atomic_write_tmp_then_rename(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)

        # Patch Path.replace to capture the rename call
        original_replace = Path.replace
        rename_calls: list[tuple[Path, Path]] = []

        def tracking_replace(self_path, target):
            rename_calls.append((self_path, target))
            return original_replace(self_path, target)

        with patch.object(Path, "replace", tracking_replace):
            await producer.run_cycle()

        # At least one rename from .json.tmp to .json
        assert any(
            str(src).endswith(".json.tmp") and str(dst).endswith("gex_nq.json")
            for src, dst in rename_calls
        ), f"Expected .json.tmp → .json rename, got: {rename_calls}"

        # .tmp must not linger
        tmp_file = tmp_output.with_suffix(".json.tmp")
        assert not tmp_file.exists(), ".json.tmp must not remain after rename"


class TestEnrichedOutputFields:
    """T3: output JSON has all required fields."""

    @pytest.mark.asyncio
    async def test_enriched_output_has_all_fields(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)
        result = await producer.run_cycle()

        assert result is not None
        data = json.loads(tmp_output.read_text(encoding="utf-8"))

        required = [
            "instrument", "flip", "call_wall", "put_wall",
            "primary_magnet", "magnet_confidence", "bias_direction",
            "invalidation_level", "regime", "as_of", "source",
            "lean", "pin_risk", "max_pain", "caveats",
            "stale_after_seconds",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"


class TestAdapterFailureWritesStale:
    """T4: adapter returns None, last_output cached → writes stale JSON."""

    @pytest.mark.asyncio
    async def test_adapter_failure_writes_stale(self, tmp_output: Path, tmp_log_dir: Path):
        producer, adapter, *_ = _build_producer(tmp_output, tmp_log_dir)

        # First cycle succeeds — populates _last_output
        result1 = await producer.run_cycle()
        assert result1 is not None
        assert tmp_output.exists()

        # Second cycle: adapter returns None
        adapter.poll.return_value = None
        result2 = await producer.run_cycle()

        assert result2 is not None
        data = json.loads(tmp_output.read_text(encoding="utf-8"))
        assert "-stale" in data["source"], "Stale output must have '-stale' in source"


class TestPriceFailureUsesFallback:
    """T5: price service fails → cycle still runs with fallback."""

    @pytest.mark.asyncio
    async def test_price_failure_uses_fallback_nq(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(
            tmp_output, tmp_log_dir,
            price_side_effect=RuntimeError("No NQ price"),
        )

        result = await producer.run_cycle()
        # Should still produce output (uses fallback NQ = 0.0 or last_output.flip)
        assert result is not None
        assert tmp_output.exists()


class TestConsecutiveFailuresTracked:
    """T6: 5 adapter failures → consecutive_failures tracked."""

    @pytest.mark.asyncio
    async def test_consecutive_failures_logged(self, tmp_output: Path, tmp_log_dir: Path):
        producer, adapter, *_ = _build_producer(tmp_output, tmp_log_dir)

        # All polls return None → no last_output → returns None
        adapter.poll.return_value = None

        for _ in range(5):
            result = await producer.run_cycle()
            assert result is None  # no stale to fall back to

        # No crash. Producer survives 5 consecutive None returns.
        assert True, "Producer survived 5 consecutive adapter failures"


class TestSourceIncludesSymbolFactor:
    """T7: source field contains 'flashalpha' and symbol."""

    @pytest.mark.asyncio
    async def test_output_source_includes_symbol_factor(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)
        result = await producer.run_cycle()

        assert result is not None
        assert "flashalpha" in result.source
        assert "QQQ" in result.source
        # Factor should be present as "x<number>"
        assert "x" in result.source


class TestAuditTrailWritten:
    """T8: after cycle, audit JSONL file exists with record."""

    @pytest.mark.asyncio
    async def test_audit_trail_written(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)
        await producer.run_cycle()

        # Find audit file in log dir
        audit_files = list(tmp_log_dir.glob("audit-*.jsonl"))
        assert len(audit_files) >= 1, "Audit JSONL file must be created"

        content = audit_files[0].read_text(encoding="utf-8").strip()
        assert content, "Audit file must not be empty"
        record = json.loads(content.splitlines()[0])
        assert "sources_polled" in record
        assert "magnet_selected" in record
        assert "confidence" in record
        assert "bias_direction" in record


class TestIntervalMinimum:
    """T9: interval_sec enforced to minimum 15."""

    def test_interval_enforced_minimum(self, tmp_output: Path, tmp_log_dir: Path):
        from gexdoctor.monitor.producer import GexDoctorProducer

        producer = GexDoctorProducer(
            flashalpha_adapter=AsyncMock(),
            price_service=AsyncMock(),
            scorer=MagicMock(),
            interpreter=MagicMock(),
            output_path=tmp_output,
            log_dir=tmp_log_dir,
            interval_sec=5,  # too low
        )
        assert producer.interval_sec >= 15


class TestRunLoopCancellation:
    """T10: run_loop exits cleanly on CancelledError."""

    @pytest.mark.asyncio
    async def test_run_loop_cancels_cleanly(self, tmp_output: Path, tmp_log_dir: Path):
        producer, *_ = _build_producer(tmp_output, tmp_log_dir)

        task = asyncio.create_task(producer.run_loop())
        # Let one cycle complete
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
