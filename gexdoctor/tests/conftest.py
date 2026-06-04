from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_live_bundle(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "sample_live_bundle.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_enriched_output(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "sample_enriched_output.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_snapshot():
    """Minimal valid FlashAlphaSnapshot for testing."""
    from gexdoctor.monitor.schemas import (
        FADealerRisk,
        FAFeedQuality,
        FAOISimulator,
        FAPinData,
        FARegime,
        FlashAlphaSnapshot,
    )

    return FlashAlphaSnapshot(
        timestamp="2026-05-28T14:30:00Z",
        symbol="QQQ",
        underlying_price=480.50,
        session_phase="intraday",
        regime=FARegime(
            net_gex=3_200_000_000.0,
            gex_sign="positive",
            gamma_flip=475.0,
            call_wall=485.0,
            put_wall=470.0,
            max_pain=478.0,
        ),
        dealer_risk=FADealerRisk(
            flow_direction="amplifying",
            flow_gex_pct_shift=0.032,
        ),
        pin=FAPinData(pin_risk=45.0, magnet_strike=478.0),
        oi_simulator=FAOISimulator(oi_delta_confidence=0.72),
        feed_quality=FAFeedQuality(plan="alpha", missing_fields=[]),
    )


@pytest.fixture
def sample_nq_quote():
    from gexdoctor.monitor.schemas import NQQuote

    return NQQuote(
        nq_price=21800.0,
        qqq_price=480.0,
        nq_qqq_factor=45.42,
        source="polygon",
        timestamp="2026-05-28T14:30:00Z",
        stale=False,
    )


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Temporary output path for testing."""
    return tmp_path / "gex_nq.json"


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    path = tmp_path / "logs"
    path.mkdir()
    return path
