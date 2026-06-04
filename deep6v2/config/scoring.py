from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringConfig(BaseSettings):
    # R3-optimized category weights (LOCKED)
    absorption_weight: float = 20.0
    exhaustion_weight: float = 15.7
    imbalance_weight: float = 25.0
    delta_weight: float = 14.3
    volume_profile_weight: float = 20.2
    auction_weight: float = 12.6
    trapped_weight: float = 10.0
    poc_weight: float = 0.0

    confluence_multiplier: float = 1.25
    ib_multiplier: float = 1.15
    midday_block_start_bar: int = 60
    midday_block_end_bar: int = 210
    type_a_threshold: float = 80.0
    type_b_threshold: float = 72.0
    type_c_threshold: float = 50.0

    model_config = SettingsConfigDict(env_prefix="SCORING_")

    @field_validator("type_a_threshold", "type_b_threshold", "type_c_threshold")
    @classmethod
    def _threshold_must_be_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("threshold must be non-negative")
        return value


__all__ = ["ScoringConfig"]
