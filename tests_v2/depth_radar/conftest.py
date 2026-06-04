"""Shared fixtures for depth_radar integration tests.

Handles the case where lightgbm is not installed: deep6.ml.__init__ imports
from lgbm_trainer which hard-raises on missing lightgbm. We pre-register stub
modules so the depth_radar subpackage (which does NOT need lgbm_trainer) can
load cleanly.
"""
from __future__ import annotations

import importlib
import sys
import types

import numpy as np
import pytest


def _ensure_depth_radar_importable() -> None:
    """Stub out deep6.ml parent imports that require lightgbm."""
    if "deep6.ml.depth_radar.wall_features" in sys.modules:
        return  # already loaded fine

    # Check if deep6.ml can be imported directly
    try:
        importlib.import_module("deep6.ml")
    except ImportError:
        # Stub the modules that fail so deep6.ml.__init__ doesn't block
        for mod_name in (
            "deep6.ml.lgbm_trainer",
            "deep6.ml.feature_builder",
            "deep6.ml.hmm_regime",
        ):
            if mod_name not in sys.modules:
                stub = types.ModuleType(mod_name)
                stub.__package__ = "deep6.ml"
                # Add placeholder attrs that deep6.ml.__init__ tries to import
                if mod_name == "deep6.ml.feature_builder":
                    stub.FEATURE_NAMES = []  # type: ignore[attr-defined]
                    stub.build_feature_matrix = None  # type: ignore[attr-defined]
                elif mod_name == "deep6.ml.lgbm_trainer":
                    stub.LGBMTrainer = None  # type: ignore[attr-defined]
                    stub.WeightFile = None  # type: ignore[attr-defined]
                elif mod_name == "deep6.ml.hmm_regime":
                    stub.HMMRegimeDetector = None  # type: ignore[attr-defined]
                    stub.RegimeState = None  # type: ignore[attr-defined]
                sys.modules[mod_name] = stub

        # Now re-attempt importing deep6.ml (will use stubs)
        if "deep6.ml" in sys.modules:
            del sys.modules["deep6.ml"]
        importlib.import_module("deep6.ml")


_ensure_depth_radar_importable()

from deep6.ml.depth_radar.wall_features import NUM_FEATURES  # noqa: E402


@pytest.fixture
def sample_wall_data() -> dict:
    """Minimal wall lifecycle data for a bid-side wall."""
    return {
        "time_in_book": 10.0,
        "modification_count": 3,
        "cancellation_count": 1,
        "original_size": 200,
        "max_size": 250,
        "current_size": 200,
        "refill_count": 0,
        "price_crossed": False,
        "side": 0,
        "wall_price": 21450.0,
        "first_seen_time": 0,
    }


@pytest.fixture
def sample_market_context() -> dict:
    """Market context snapshot matching NQ-like conditions."""
    return {
        "mid_price": 21450.25,
        "best_bid": 21450.0,
        "best_ask": 21450.50,
        "spread": 0.50,
        "avg_wall_size": 100.0,
        "bid_volumes": [100, 80, 120, 60, 90, 50, 70, 110, 40, 130],
        "ask_volumes": [70, 110, 50, 130, 40, 80, 60, 100, 90, 120],
    }


@pytest.fixture
def spoof_wall_data() -> dict:
    """Wall data exhibiting spoofing patterns."""
    return {
        "time_in_book": 0.5,
        "modification_count": 15,
        "cancellation_count": 8,
        "original_size": 500,
        "max_size": 500,
        "current_size": 0,
        "refill_count": 0,
        "price_crossed": False,
        "side": 1,
        "wall_price": 21455.0,
        "first_seen_time": 0,
    }


@pytest.fixture
def iceberg_wall_data() -> dict:
    """Wall data exhibiting iceberg behavior."""
    return {
        "time_in_book": 120.0,
        "modification_count": 2,
        "cancellation_count": 0,
        "original_size": 100,
        "max_size": 100,
        "current_size": 100,
        "refill_count": 5,
        "price_crossed": True,
        "side": 0,
        "wall_price": 21449.0,
        "first_seen_time": 0,
    }
