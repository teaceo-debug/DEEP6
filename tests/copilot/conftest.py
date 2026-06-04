"""Copilot test fixtures."""

from __future__ import annotations

import pytest

from deep6.copilot.config import CopilotConfig


@pytest.fixture()
def copilot_config(monkeypatch: pytest.MonkeyPatch) -> CopilotConfig:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    return CopilotConfig.from_env()
