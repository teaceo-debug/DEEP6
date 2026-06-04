from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Find the project root by walking up from __file__ until deep6/ or .git/ found."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "deep6").exists() or (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd().resolve()


PROJECT_ROOT = _find_project_root()


class DepthRadarConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="",
    )

    # Rithmic connection
    rithmic_user: str = ""
    rithmic_password: str = ""
    rithmic_system_name: str = ""
    rithmic_url: str = Field(
        default="",
        validation_alias=AliasChoices("RITHMIC_URL", "RITHMIC_URI"),
    )
    rithmic_symbol: str = "NQM6"
    rithmic_exchange: str = "CME"

    # Engine settings
    source: str = "rithmic"
    min_wall_size: int = 10
    update_interval_ms: int = 500
    rth_only: bool = False

    # NT8 integration
    nt8_output_path: str = str(
        Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "depth_radar_walls.json"
    )

    # Paths (stored as relative, resolved to absolute in validator)
    model_dir: Path = Path("deep6/models")
    training_output_dir: Path = Path("training_output")
    replay_file: str = ""

    @model_validator(mode="after")
    def resolve_paths(self) -> "DepthRadarConfig":
        """Resolve relative paths to absolute using project root."""
        if not self.model_dir.is_absolute():
            self.model_dir = (PROJECT_ROOT / self.model_dir).resolve()
        if not self.training_output_dir.is_absolute():
            self.training_output_dir = (PROJECT_ROOT / self.training_output_dir).resolve()
        return self

    @property
    def intent_model_path(self) -> Path:
        return self.model_dir / "intent_classifier_v4.joblib"

    @property
    def interaction_model_path(self) -> Path:
        return self.model_dir / "interaction_predictor_v4.joblib"

    @property
    def rithmic_configured(self) -> bool:
        return bool(
            self.rithmic_user
            and self.rithmic_password
            and self.rithmic_system_name
            and self.rithmic_url
        )


def load_config() -> DepthRadarConfig:
    """Load configuration from .env file and environment variables."""
    return DepthRadarConfig()
