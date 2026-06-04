from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from deep6.backtest.research_runner import ReplayRunRequest, ResearchRunner


@pytest.mark.asyncio
async def test_research_runner_dry_run_produces_replay_artifacts(tmp_path: Path) -> None:
    request = ReplayRunRequest(
        start=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 9, 13, 35, tzinfo=timezone.utc),
        duckdb_path=str(tmp_path / "research.duckdb"),
        tf_list=["1m"],
    )

    result = await ResearchRunner().run(request)

    assert result.status == "complete"
    assert result.run_id
    assert result.total_bars > 0
    assert result.metrics["bars_written"] > 0
    assert Path(result.duckdb_path).exists()
    assert result.rows, "expected persisted replay rows to be returned"
