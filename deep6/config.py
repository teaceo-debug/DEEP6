"""Centralised configuration loaded from environment variables.

Per T-01-01: rithmic_password must NEVER be logged. The Config dataclass does not
implement __repr__ for this reason — use structlog.bind with explicit field selection
and exclude password from all log context.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    rithmic_user: str
    rithmic_password: str
    rithmic_system_name: str
    rithmic_uri: str
    db_path: str

    # DEEP6 API (FastAPI) — unified on port 8765 across backend + dashboard.
    api_host: str = "127.0.0.1"
    api_port: int = 8765

    # NQ instrument constants
    instrument: str = "NQM5"  # update to front month as needed
    exchange: str = "CME"
    tick_size: float = 0.25   # NQ minimum tick size in points

    # Bar timeframes (seconds)
    primary_bar_seconds: int = 60    # 1-minute bars (D-04)
    secondary_bar_seconds: int = 300 # 5-minute bars (D-04, D-05)

    # Aggressor gate parameters (D-03)
    aggressor_sample_size: int = 50
    aggressor_max_unknown_pct: float = 0.10

    # Phase 14: data source selection — "databento" (default) or "rithmic".
    data_source: str = "databento"
    databento_api_key: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        Raises KeyError if required env vars are missing.
        """
        return cls(
            rithmic_user=os.environ.get("RITHMIC_USER", ""),
            rithmic_password=os.environ.get("RITHMIC_PASSWORD", ""),
            rithmic_system_name=os.environ.get("RITHMIC_SYSTEM_NAME", "Rithmic Test"),
            rithmic_uri=os.environ.get("RITHMIC_URI", "wss://rituz00100.rithmic.com:443"),
            db_path=os.environ.get("DEEP6_DB_PATH", "./deep6_session.db"),
            api_host=os.environ.get("DEEP6_API_HOST", "127.0.0.1"),
            api_port=int(os.environ.get("DEEP6_API_PORT", "8765")),
            data_source=os.environ.get("DEEP6_DATA_SOURCE", "databento"),
            databento_api_key=os.environ.get("DATABENTO_API_KEY", ""),
        )

    def safe_log_fields(self) -> dict:
        """Return loggable config fields excluding password (T-01-01)."""
        return {
            "rithmic_user": self.rithmic_user,
            "rithmic_system_name": self.rithmic_system_name,
            "rithmic_uri": self.rithmic_uri,
            "instrument": self.instrument,
            "exchange": self.exchange,
        }
