from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class KronosConfig(BaseSettings):
    model_name: str = "NeoQuasar/Kronos-small"
    context_length: int = 512
    inference_timeout_ms: int = 2000
    use_gpu: bool = False
    thread_pool_size: int = 1
    inference_frequency_bars: int = 5

    model_config = SettingsConfigDict(env_prefix="KRONOS_")


__all__ = ["KronosConfig"]
