"""pytest-qt fixtures for depth_radar_desktop tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def mock_walls():
    """Return 3 mock wall dicts matching get_active_walls() shape."""
    return [
        {
            "episode_id": "ep-001",
            "price": 20000.0,
            "side": 0.0,
            "size": 100,
            "max_size": 150,
            "age_sec": 30.0,
            "intent": "PASSIVE_REAL",
            "state": "ESTABLISHED",
            "in_touch_band": False,
            "absorption_ratio": 0.2,
            "delta_2s": -50.0,
            "approach_speed": 0.5,
            "current_size": 100.0,
            "original_size": 150.0,
            "max_size_so_far": 150.0,
            "age_seconds": 30.0,
            "modifications_so_far": 5.0,
            "refills_so_far": 1.0,
            "confidence": 0.85,
        },
        {
            "episode_id": "ep-002",
            "price": 20005.0,
            "side": 1.0,
            "size": 75,
            "max_size": 80,
            "age_sec": 15.0,
            "intent": "SPOOF_LIKE",
            "state": "FRESH",
            "in_touch_band": False,
            "absorption_ratio": 0.0,
            "delta_2s": 30.0,
            "approach_speed": 1.2,
            "current_size": 75.0,
            "original_size": 80.0,
            "max_size_so_far": 80.0,
            "age_seconds": 15.0,
            "modifications_so_far": 2.0,
            "refills_so_far": 0.0,
            "confidence": 0.60,
        },
        {
            "episode_id": "ep-003",
            "price": 19997.5,
            "side": 0.0,
            "size": 200,
            "max_size": 200,
            "age_sec": 120.0,
            "intent": "PASSIVE_REAL",
            "state": "UNDER_ATTACK",
            "in_touch_band": True,
            "absorption_ratio": 0.35,
            "delta_2s": -120.0,
            "approach_speed": 2.1,
            "current_size": 200.0,
            "original_size": 200.0,
            "max_size_so_far": 200.0,
            "age_seconds": 120.0,
            "modifications_so_far": 10.0,
            "refills_so_far": 3.0,
            "confidence": 0.92,
        },
    ]
