from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SignalConfig(BaseSettings):
    imbalance_ratio: float = 3.0
    absorption_wick_pct: float = 0.3
    delta_neutrality_threshold: float = 0.1
    exhaustion_zero_threshold: int = 0
    fat_print_mult: float = 2.5
    stopping_mult: float = 1.5
    effort_mult: float = 1.5
    effort_range_pct: float = 0.5
    surge_mult: float = 3.0
    big_delta_threshold: int = 200

    model_config = SettingsConfigDict(env_prefix="SIGNAL_")


__all__ = ["SignalConfig"]
