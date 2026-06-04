from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["GexDoctorConfig"]

_DEFAULT_NT8_OUTPUT = r"C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json"


class GexDoctorConfig(BaseSettings):
    """GEX Doctor configuration. Env vars override yaml defaults."""

    model_config = SettingsConfigDict(env_prefix="GEXDOCTOR_", extra="ignore")

    flashalpha_api_key: str = Field(default="")
    massive_api_key: str = Field(default="")

    interval: int = 15
    source: str = "QQQ"

    output_path: str = _DEFAULT_NT8_OUTPUT

    min_confidence: float = 0.65
    anti_flicker_margin: float = 0.12
    stale_threshold_sec: int = 120

    log_dir: str = "logs"

    @classmethod
    def from_yaml(cls, yaml_path: Path, **overrides: Any) -> "GexDoctorConfig":
        """Load config from yaml file, then apply env var overrides."""
        data: dict[str, Any] = {}
        if yaml_path.exists():
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for section, values in raw.items():
                if isinstance(values, dict):
                    data.update(values)
                else:
                    data[section] = values
        data.update(overrides)
        return cls(**data)

    def validate_required(self) -> list[str]:
        missing: list[str] = []
        if not self.flashalpha_api_key:
            missing.append("FLASHALPHA_API_KEY")
        return missing
