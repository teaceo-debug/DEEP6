from __future__ import annotations

from pathlib import Path

import pytest

from gexdoctor.monitor.config import GexDoctorConfig


def test_config_loads_from_yaml():
    config = GexDoctorConfig.from_yaml(Path(__file__).resolve().parents[1] / "config.yaml")
    assert config.interval == 15


def test_config_validate_required_missing_key():
    config = GexDoctorConfig()
    assert config.validate_required() == ["FLASHALPHA_API_KEY"]


def test_config_validate_required_with_key():
    config = GexDoctorConfig(flashalpha_api_key="abc123")
    assert config.validate_required() == []


def test_config_defaults():
    config = GexDoctorConfig()
    assert "NinjaTrader" in config.output_path


def test_config_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEXDOCTOR_INTERVAL", "30")
    config = GexDoctorConfig()
    assert config.interval == 30
