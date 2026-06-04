from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
import yaml


class Settings(BaseSettings):
    """Load from settings.yaml with env override support."""

    model_config = SettingsConfigDict(env_prefix="CROSS_MARKET_")

    @classmethod
    def from_yaml(cls, path: Path | None = None) -> "Settings":
        config_path = path or Path(__file__).parent / "settings.yaml"
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text())
            return cls(**{k: v for section in data.values()
                         if isinstance(section, dict)
                         for k, v in section.items()})
        return cls()
