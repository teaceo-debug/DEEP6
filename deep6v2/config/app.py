from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from deep6v2.config.execution import ExecutionConfig
from deep6v2.config.kronos import KronosConfig
from deep6v2.config.rithmic import RithmicConfig
from deep6v2.config.scoring import ScoringConfig
from deep6v2.config.signals import SignalConfig


class AppConfig(BaseSettings):
    rithmic: RithmicConfig = RithmicConfig()
    signals: SignalConfig = SignalConfig()
    scoring: ScoringConfig = ScoringConfig()
    execution: ExecutionConfig = ExecutionConfig()
    kronos: KronosConfig = KronosConfig()

    model_config = SettingsConfigDict(env_nested_delimiter="__")

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls()


__all__ = ["AppConfig"]
