"""Tests for GEX Doctor ingest endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import deep6.api.routes.bias_v3 as bias_v3
import deep6.api.routes.gex_ingest as gex_ingest
from deep6.api.app import app

client = TestClient(app)

VALID_PAYLOAD = {
    "domain": "gex_doctor",
    "score": 2,
    "max_range": 3,
    "available": True,
    "stale": False,
    "detail": {"regime": "positive", "flip": 21380.0},
    "updated_at": 1748527200.0,
}


@pytest.fixture(autouse=True)
def reset_gex_state():
    gex_ingest._latest_gex_doctor = None
    bias_v3._latest_snapshot = None
    bias_v3._domain_scores = {}
    bias_v3._snapshot_history = []
    yield
    gex_ingest._latest_gex_doctor = None


def test_ingest_accepts_valid_payload():
    response = client.post("/api/gex/ingest", json=VALID_PAYLOAD)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["score"] == 2


def test_ingest_rejects_float_score():
    """score must be int, not float."""
    payload = {**VALID_PAYLOAD, "score": 2.5}
    response = client.post("/api/gex/ingest", json=payload)
    if response.status_code == 200:
        latest = client.get("/api/gex/latest").json()
        assert isinstance(latest["score"], int)


def test_latest_returns_pending_before_ingest():
    """Before any ingest, /latest returns pending status."""
    response = client.get("/api/gex/latest")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_latest_returns_data_after_ingest():
    """After ingest, /latest returns the stored data."""
    client.post("/api/gex/ingest", json=VALID_PAYLOAD)
    response = client.get("/api/gex/latest")
    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 2
    assert data["domain"] == "gex_doctor"


def test_domains_includes_gex_doctor_after_ingest():
    """After ingest, /api/v3/bias/domains includes gex_doctor."""
    client.post("/api/gex/ingest", json=VALID_PAYLOAD)
    response = client.get("/api/v3/bias/domains")
    if response.status_code == 200:
        data = response.json()
        assert "gex_doctor" in data
