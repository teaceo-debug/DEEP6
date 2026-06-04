from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    massive_api_key: str
    anthropic_api_key: str
    flashalpha_api_key: Optional[str] = None
    anthropic_model: str = "claude-haiku-4-5-20251001"
    refresh_interval_sec: int = 10
    flashalpha_refresh_sec: int = 15
    ai_refresh_sec: int = 15
    host: str = "0.0.0.0"
    port: int = 8766
    underlying: str = "QQQ"
    min_oi: int = 100
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="NQ_ATLAS_",
        env_file=".env.atlas",
        env_file_encoding="utf-8",
        extra="ignore",
    )


__all__ = ["Settings"]
