from __future__ import annotations

import pytest
from pydantic import ValidationError

from deep6v2.config.app import AppConfig
from deep6v2.config.execution import ExecutionConfig
from deep6v2.config.rithmic import RithmicConfig
from deep6v2.config.scoring import ScoringConfig


def test_default_config_loads():
    config = AppConfig.from_env()

    assert config.scoring.absorption_weight == 20.0
    assert config.execution.dry_run is True


def test_r3_weights_locked():
    config = ScoringConfig()

    assert config.absorption_weight == 20.0
    assert config.exhaustion_weight == 15.7
    assert config.imbalance_weight == 25.0
    assert config.delta_weight == 14.3
    assert config.volume_profile_weight == 20.2
    assert config.auction_weight == 12.6
    assert config.trapped_weight == 0.0
    assert config.poc_weight == 0.0


def test_dry_run_default_true():
    assert ExecutionConfig().dry_run is True


def test_invalid_threshold_rejected():
    with pytest.raises(ValidationError):
        ScoringConfig(type_a_threshold=-1)


def test_rithmic_uri_default():
    assert RithmicConfig().uri == "wss://rituz00100.rithmic.com"
