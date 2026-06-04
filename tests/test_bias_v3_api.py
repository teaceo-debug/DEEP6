"""Tests for v3 bias API routes."""
from __future__ import annotations

import importlib.util
import sys
import types
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from deep6.engines.bias_contracts import BiasState, MarketBiasSnapshot


def _make_snapshot(symbol: str = "NQ", asof_ts: float | None = None, bias_score: int = 7) -> MarketBiasSnapshot:
    return MarketBiasSnapshot(
        symbol=symbol,
        asof_ts=asof_ts or time.time(),
        bias_label="LEAN BULL",
        bias_state=BiasState.LEAN_BULL,
        bias_score=bias_score,
        confidence=0.72,
        setup_quality=8,
        mode="GO",
        mode_reason="All domains aligned",
        session_label="A+ OPEN",
        xamd_phase="ACCUMULATION",
        intermarket_alignment=0.6,
        kronos_confidence=0.8,
        nearest_support=21000.0,
        nearest_resistance=21100.0,
        domain_detail={"ict": {"score": 3}},
        meta={"active_domains": 4},
    )


def _load_bias_v3_module():
    path = Path(__file__).resolve().parents[1] / "deep6" / "api" / "routes" / "bias_v3.py"
    spec = importlib.util.spec_from_file_location("bias_v3_test_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TestBiasV3Api:
    def setup_method(self):
        sys.modules.setdefault("lightgbm", types.SimpleNamespace(LGBMClassifier=object))
        self.bias_v3 = _load_bias_v3_module()

        self.bias_v3._latest_snapshot = None
        self.bias_v3._snapshot_history.clear()
        self.bias_v3._domain_scores = {}

    def test_bias_returns_503_when_uninitialized(self):
        app = FastAPI()
        app.include_router(self.bias_v3.router)

        with TestClient(app) as client:
            resp = client.get("/api/v3/bias")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Bias engine not initialized"

    def test_update_snapshot_enables_latest_snapshot_endpoint(self):
        app = FastAPI()
        app.include_router(self.bias_v3.router)

        self.bias_v3.update_snapshot(_make_snapshot(), {"ict": {"score": 3}, "macro": {"score": 2}})

        with TestClient(app) as client:
            resp = client.get("/api/v3/bias")

        assert resp.status_code == 200
        body = resp.json()
        assert body["symbol"] == "NQ"
        assert body["bias_score"] == 7
        assert body["mode"] == "GO"

    def test_domains_endpoint_returns_latest_domain_scores(self):
        app = FastAPI()
        app.include_router(self.bias_v3.router)

        self.bias_v3.update_snapshot(_make_snapshot(), {"ict": {"score": 3}, "macro": {"score": 2}})

        with TestClient(app) as client:
            resp = client.get("/api/v3/bias/domains")

        assert resp.status_code == 200
        assert resp.json()["ict"]["score"] == 3

    def test_history_limit_returns_last_n_snapshots(self):
        app = FastAPI()
        app.include_router(self.bias_v3.router)

        for i in range(5):
            self.bias_v3.update_snapshot(_make_snapshot(bias_score=i, asof_ts=1000.0 + i), {"ict": {"score": i}})

        with TestClient(app) as client:
            resp = client.get("/api/v3/bias/history?limit=2")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["bias_score"] == 3
        assert body[1]["bias_score"] == 4

    def test_v3_router_registered_in_app(self):
        app_py = (Path(__file__).resolve().parents[1] / "deep6" / "api" / "app.py").read_text(encoding="utf-8")
        assert "bias_v3_router.router" in app_py
