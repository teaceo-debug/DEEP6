"""Tests for /backtest/run + /backtest/results endpoints and WS broadcast wiring.

TDD: Task 2 — backtest.py + events.py broadcast + app.py router registration
"""
from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_app():
    """Return the FastAPI app instance."""
    from deep6.api.app import app
    return app


def _make_signal_event_payload() -> dict:
    return {
        "ts": time.time(),
        "bar_index_in_session": 42,
        "total_score": 75.0,
        "tier": "TYPE_A",
        "direction": 1,
        "engine_agreement": 0.8,
        "category_count": 3,
        "categories_firing": ["absorption", "delta"],
        "gex_regime": "NEUTRAL",
        "kronos_bias": 0.0,
    }


def _make_trade_event_payload() -> dict:
    return {
        "ts": time.time(),
        "position_id": "pos-001",
        "event_type": "TARGET_HIT",
        "side": "LONG",
        "entry_price": 21000.0,
        "exit_price": 21050.0,
        "pnl": 500.0,
        "bars_held": 3,
        "signal_tier": "TYPE_A",
        "signal_score": 75.0,
        "regime_label": "UNKNOWN",
    }


# ---------------------------------------------------------------------------
# POST /backtest/run tests
# ---------------------------------------------------------------------------

class TestBacktestRun:
    """Tests for POST /backtest/run endpoint."""

    def setup_method(self):
        # Clear any running jobs before each test
        import deep6.api.routes.backtest as bt
        bt._backtest_jobs.clear()

    def test_post_run_returns_202_with_job_id(self):
        """POST /backtest/run returns 202 with job_id and status=running."""
        app = _get_app()
        with TestClient(app) as client:
            resp = client.post("/backtest/run", json={
                "start_date": "2026-04-07",
                "end_date": "2026-04-10",
                "bar_seconds": 60,
            })
        assert resp.status_code == 202
        body = resp.json()
        assert "job_id" in body
        assert body["status"] == "running"
        assert len(body["job_id"]) > 0

    def test_post_run_missing_start_date_returns_422(self):
        """POST /backtest/run with missing start_date returns 422 validation error."""
        app = _get_app()
        with TestClient(app) as client:
            # start_date has a default, so send a completely empty body — should
            # still work with defaults. Instead test a truly required field by
            # sending invalid type for bar_seconds.
            resp = client.post("/backtest/run", json={"bar_seconds": "not-an-int"})
        assert resp.status_code == 422

    def test_post_run_returns_409_if_job_already_running(self):
        """POST /backtest/run returns 409 if a backtest is already running."""
        import deep6.api.routes.backtest as bt

        # Manually inject a running job
        bt._backtest_jobs["existing-job"] = {"status": "running", "started_at": time.time()}

        app = _get_app()
        with TestClient(app) as client:
            resp = client.post("/backtest/run", json={
                "start_date": "2026-04-07",
                "end_date": "2026-04-10",
            })
        assert resp.status_code == 409

    def test_post_run_with_defaults_accepted(self):
        """POST /backtest/run with default values returns 202."""
        import deep6.api.routes.backtest as bt
        bt._backtest_jobs.clear()

        app = _get_app()
        with TestClient(app) as client:
            resp = client.post("/backtest/run", json={})
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# GET /backtest/results/{job_id} tests
# ---------------------------------------------------------------------------

class TestBacktestResults:
    """Tests for GET /backtest/results/{job_id} endpoint."""

    def setup_method(self):
        import deep6.api.routes.backtest as bt
        bt._backtest_jobs.clear()

    def test_get_unknown_job_id_returns_404(self):
        """GET /backtest/results/{unknown_id} returns 404."""
        app = _get_app()
        with TestClient(app) as client:
            resp = client.get("/backtest/results/does-not-exist")
        assert resp.status_code == 404

    def test_get_known_job_id_returns_status_dict(self):
        """GET /backtest/results/{known_id} returns dict with 'status' key."""
        import deep6.api.routes.backtest as bt

        job_id = "test-job-123"
        bt._backtest_jobs[job_id] = {
            "status": "running",
            "started_at": time.time(),
        }

        app = _get_app()
        with TestClient(app) as client:
            resp = client.get(f"/backtest/results/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["status"] == "running"

    def test_get_complete_job_includes_rows(self):
        """GET /backtest/results/{job_id} returns rows when status=complete."""
        import deep6.api.routes.backtest as bt

        job_id = "complete-job-456"
        bt._backtest_jobs[job_id] = {
            "status": "complete",
            "started_at": time.time(),
            "completed_at": time.time() + 5,
            "rows": [{"bar_index": 0, "tier": "TYPE_A", "score": 80.0}],
            "summary": {"TYPE_A": 1},
        }

        app = _get_app()
        with TestClient(app) as client:
            resp = client.get(f"/backtest/results/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "complete"
        assert "rows" in body
        assert len(body["rows"]) > 0


# ---------------------------------------------------------------------------
# Router registration tests
# ---------------------------------------------------------------------------

class TestRouterRegistration:
    """Tests confirming /ws and /backtest routers are registered in the app."""

    def test_ws_router_registered_in_app(self):
        """App routes include /ws WebSocket endpoint."""
        from deep6.api.app import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/ws" in paths, f"/ws not found in routes: {paths}"

    def test_backtest_run_router_registered_in_app(self):
        """/backtest/run route is registered in the app."""
        from deep6.api.app import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/backtest/run" in paths, f"/backtest/run not in routes: {paths}"

    def test_backtest_results_router_registered_in_app(self):
        """/backtest/results/{job_id} route is registered in the app."""
        from deep6.api.app import app
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/backtest/results/{job_id}" in paths, f"/backtest/results not in routes: {paths}"


# ---------------------------------------------------------------------------
# WS broadcast wiring tests (events router calls ws_manager.broadcast)
# ---------------------------------------------------------------------------

class TestBroadcastWiring:
    """Tests that events router broadcasts to ws_manager after DB insert."""

    def test_signal_event_triggers_broadcast(self):
        """POST /events/signal calls ws_manager.broadcast after insert."""
        from deep6.api.routes import ws as ws_module

        broadcast_calls = []

        async def mock_broadcast(data: dict) -> None:
            broadcast_calls.append(data)

        original = ws_module.ws_manager.broadcast
        ws_module.ws_manager.broadcast = mock_broadcast

        try:
            app = _get_app()
            with TestClient(app) as client:
                resp = client.post("/events/signal", json=_make_signal_event_payload())
            assert resp.status_code == 200
            assert len(broadcast_calls) == 1
            assert broadcast_calls[0]["type"] == "signal"
        finally:
            ws_module.ws_manager.broadcast = original

    def test_trade_event_triggers_broadcast(self):
        """POST /events/trade calls ws_manager.broadcast after insert."""
        from deep6.api.routes import ws as ws_module

        broadcast_calls = []

        async def mock_broadcast(data: dict) -> None:
            broadcast_calls.append(data)

        original = ws_module.ws_manager.broadcast
        ws_module.ws_manager.broadcast = mock_broadcast

        try:
            app = _get_app()
            with TestClient(app) as client:
                resp = client.post("/events/trade", json=_make_trade_event_payload())
            assert resp.status_code == 200
            assert len(broadcast_calls) == 1
            assert broadcast_calls[0]["type"] == "trade"
        finally:
            ws_module.ws_manager.broadcast = original
