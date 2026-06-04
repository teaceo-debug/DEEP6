"""GEX Terminal configuration — Pydantic BaseSettings with GEX_TERMINAL_ prefix."""
from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Keys (default empty — adapters handle missing keys gracefully)
    flashalpha_api_key: str = ""
    massive_api_key: str = ""
    uw_api_key: str = ""
    anthropic_api_key: str = ""

    # Server
    server_port: int = 8780
    refresh_interval_sec: int = 30
    static_dir: str = ""  # empty = auto-detect ui/out/ relative to package

    # Integration
    deep6_bias_url: str = "http://localhost:8765"

    # Optional Rithmic NQ price feed (falls back to QQQ estimation when unavailable)
    rithmic_enabled: bool = True
    rithmic_user: str = Field(default="", validation_alias=AliasChoices("GEX_TERMINAL_RITHMIC_USER", "RITHMIC_USER"))
    rithmic_password: str = Field(
        default="",
        validation_alias=AliasChoices("GEX_TERMINAL_RITHMIC_PASSWORD", "RITHMIC_PASSWORD"),
    )
    rithmic_system_name: str = Field(
        default="Rithmic Paper Trading",
        validation_alias=AliasChoices("GEX_TERMINAL_RITHMIC_SYSTEM_NAME", "RITHMIC_SYSTEM_NAME"),
    )
    rithmic_uri: str = Field(
        default="wss://rprotocol.rithmic.com:443",
        validation_alias=AliasChoices("GEX_TERMINAL_RITHMIC_URI", "RITHMIC_URI"),
    )
    rithmic_app_name: str = Field(
        default="migo:DEEP6-sim",
        validation_alias=AliasChoices("GEX_TERMINAL_RITHMIC_APP_NAME", "RITHMIC_APP_NAME"),
    )

    # GEX/VIX thresholds
    vix_threshold_low: float = 15.0
    vix_threshold_high: float = 25.0
    vix_threshold_extreme: float = 35.0

    # FlashAlpha — disabled by default (use Massive + UW GEX instead)
    flashalpha_enabled: bool = False
    flashalpha_poll_every_n_cycles: int = 5

    # Claude
    claude_model: str = "claude-haiku-4-5-20251001"
    claude_budget_daily_usd: float = 10.0
    flashalpha_mcp_enabled: bool = False

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="GEX_TERMINAL_",
        env_file=".env.gex_terminal",
        env_file_encoding="utf-8",
        extra="ignore",
    )


__all__ = ["Settings"]
