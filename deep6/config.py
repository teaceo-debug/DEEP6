"""Centralised configuration loaded from environment variables.

Per T-01-01: rithmic_password must NEVER be logged. The Config dataclass does not
implement __repr__ for this reason — use structlog.bind with explicit field selection
and exclude password from all log context.
"""
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


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
    # Front-month code: M=June, U=Sep, Z=Dec, H=Mar. Roll ~8 days before expiry.
    # 2026-04-14: NQM6 (June 2026). Override with RITHMIC_INSTRUMENT env var.
    instrument: str = "NQM6"
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
    databento_api_key_glbx: str = ""  # Phase 14: CME MDP3.0-specific key (live MBO)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables.

        Auto-loads ``.env`` from the project root if present (so callers don't
        have to shell-source it). Existing env vars win — .env is fallback only.
        """
        if load_dotenv is not None:
            dotenv_path = Path(__file__).resolve().parents[1] / ".env"
            if dotenv_path.exists():
                load_dotenv(dotenv_path, override=False)
        return cls(
            rithmic_user=os.environ.get("RITHMIC_USER", ""),
            rithmic_password=os.environ.get("RITHMIC_PASSWORD", ""),
            rithmic_system_name=os.environ.get("RITHMIC_SYSTEM_NAME", "Rithmic Test"),
            rithmic_uri=os.environ.get("RITHMIC_URI", "wss://rituz00100.rithmic.com:443"),
            db_path=os.environ.get("DEEP6_DB_PATH", "./deep6_session.db"),
            api_host=os.environ.get("DEEP6_API_HOST", "127.0.0.1"),
            api_port=int(os.environ.get("DEEP6_API_PORT", "8765")),
            instrument=os.environ.get("RITHMIC_INSTRUMENT", cls.__dataclass_fields__["instrument"].default),
            exchange=os.environ.get("RITHMIC_EXCHANGE", cls.__dataclass_fields__["exchange"].default),
            data_source=os.environ.get("DEEP6_DATA_SOURCE", "databento"),
            databento_api_key=os.environ.get("DATABENTO_API_KEY", ""),
            databento_api_key_glbx=os.environ.get("DATABENTO_API_KEY_GLBX", ""),
        )

    def databento_live_key(self) -> str:
        """Return the GLBX.MDP3-authorised key, with fallback to primary.

        Phase 14 (D-01): CME MDP 3.0 live MBO typically requires a dataset-
        scoped key (``DATABENTO_API_KEY_GLBX``). We fall back to the
        primary account key if the GLBX-specific one isn't set — handy for
        dev boxes where a single key is entitled for both historical and
        live feeds.
        """
        return self.databento_api_key_glbx or self.databento_api_key

    def safe_log_fields(self) -> dict:
        """Return loggable config fields excluding password (T-01-01)."""
        return {
            "rithmic_user": self.rithmic_user,
            "rithmic_system_name": self.rithmic_system_name,
            "rithmic_uri": self.rithmic_uri,
            "instrument": self.instrument,
            "exchange": self.exchange,
        }
