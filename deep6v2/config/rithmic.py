from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RithmicConfig(BaseSettings):
    uri: str = "wss://rituz00100.rithmic.com"
    username: str = ""
    password: str = ""
    system_name: str = "Rithmic Paper Trading"
    app_name: str = "deep6v2"
    gateway: str = "Chicago"
    reconnect_attempts: int = 5
    reconnect_backoff_base: float = 1.0

    model_config = SettingsConfigDict(env_prefix="RITHMIC_")


__all__ = ["RithmicConfig"]
