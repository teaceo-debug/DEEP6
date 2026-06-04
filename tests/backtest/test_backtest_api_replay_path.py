from __future__ import annotations

from fastapi.testclient import TestClient


def _get_app():
    from deep6.api.app import app
    return app


def test_backtest_run_uses_research_runner(monkeypatch, tmp_path) -> None:
    import deep6.api.routes.backtest as backtest_module
    from deep6.backtest.research_runner import ReplayRunResult

    backtest_module._backtest_jobs.clear()

    captured = {}

    async def fake_run(self, request):
        captured["request"] = request
        return ReplayRunResult(
            run_id="run-123",
            status="complete",
            started_at=1.0,
            completed_at=2.0,
            duckdb_path=str(tmp_path / "fake.duckdb"),
            total_bars=3,
            rows=[{"tf": "1m", "tier": "TYPE_B", "score": 72.0}],
            metrics={"bars_written": 3, "dom_signal_fires": 1, "scorer_signal_fires": 1, "trades_written": 1},
            summary={"TYPE_B": 1},
            request={"symbol": "NQ.c.0"},
        )

    monkeypatch.setattr(backtest_module.ResearchRunner, "run", fake_run)

    with TestClient(_get_app()) as client:
        resp = client.post(
            "/backtest/run",
            json={"start_date": "2026-04-07", "end_date": "2026-04-10", "bar_seconds": 60},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        result = client.get(f"/backtest/results/{job_id}")

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "complete"
    assert body["run_id"] == "run-123"
    assert body["total_bars"] == 3
    assert body["metrics"]["bars_written"] == 3
    assert captured["request"].start.isoformat().startswith("2026-04-07T13:30:00")
