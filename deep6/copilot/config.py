"""Copilot configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


@dataclass(frozen=True)
class CopilotConfig:
    claude_api_key: str
    claude_narrative_model: str = "claude-sonnet-4-5-20250929"
    claude_vision_model: str = "claude-opus-4-5-20251101"
    screenshot_interval_sec: int = 30
    narrative_interval_sec: int = 15
    token_budget_per_hour: int = 500000
    overlay_side: str = "right"
    overlay_width: int = 400
    data_bridge_host: str = "127.0.0.1"
    data_bridge_port: int = 9200
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    calendar_enabled: bool = True
    news_enabled: bool = True
    sentiment_enabled: bool = True
    internals_enabled: bool = True
    options_flow_enabled: bool = True

    @classmethod
    def from_env(cls, env_path: str | os.PathLike[str] | None = None) -> "CopilotConfig":
        """Load configuration from environment variables."""
        if load_dotenv is not None:
            dotenv_path = Path(env_path) if env_path else Path(__file__).resolve().parents[2] / ".env"
            if dotenv_path.exists():
                load_dotenv(dotenv_path, override=False)
        return cls(
            claude_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            claude_narrative_model=os.environ.get(
                "CLAUDE_NARRATIVE_MODEL", cls.__dataclass_fields__["claude_narrative_model"].default
            ),
            claude_vision_model=os.environ.get(
                "CLAUDE_VISION_MODEL", cls.__dataclass_fields__["claude_vision_model"].default
            ),
            screenshot_interval_sec=int(os.environ.get("COPILOT_SCREENSHOT_INTERVAL_SEC", "30")),
            narrative_interval_sec=int(os.environ.get("COPILOT_NARRATIVE_INTERVAL_SEC", "15")),
            token_budget_per_hour=int(os.environ.get("COPILOT_TOKEN_BUDGET_PER_HOUR", "500000")),
            overlay_side=os.environ.get("COPILOT_OVERLAY_SIDE", "right"),
            overlay_width=int(os.environ.get("COPILOT_OVERLAY_WIDTH", "400")),
            data_bridge_host=os.environ.get("COPILOT_DATA_BRIDGE_HOST", "127.0.0.1"),
            data_bridge_port=int(os.environ.get("COPILOT_DATA_BRIDGE_PORT", "9200")),
            api_host=os.environ.get("COPILOT_API_HOST", "127.0.0.1"),
            api_port=int(os.environ.get("COPILOT_API_PORT", "8765")),
            calendar_enabled=os.environ.get("COPILOT_CALENDAR_ENABLED", "true").lower() == "true",
            news_enabled=os.environ.get("COPILOT_NEWS_ENABLED", "true").lower() == "true",
            sentiment_enabled=os.environ.get("COPILOT_SENTIMENT_ENABLED", "true").lower() == "true",
            internals_enabled=os.environ.get("COPILOT_INTERNALS_ENABLED", "true").lower() == "true",
            options_flow_enabled=os.environ.get("COPILOT_OPTIONS_FLOW_ENABLED", "true").lower() == "true",
        )
