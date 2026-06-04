"""Structured logging setup for GEX Terminal."""
from __future__ import annotations

import json
import logging
import logging.handlers
import time
from pathlib import Path

LOG_DIR = Path.home() / ".deep6"
LOG_FILE = LOG_DIR / "gexdoctor_v2.log"
AUDIT_FILE = LOG_DIR / "gexdoctor_v2_audit.jsonl"


def setup_logging(log_level: str = "INFO") -> None:
    """Configure rotating file handler + console handler."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    root.addHandler(console)
    root.addHandler(file_handler)


def write_audit(record: dict) -> None:
    """Append a record to the JSONL audit trail."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(record)
    payload["ts"] = time.time()
    try:
        with AUDIT_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


__all__ = ["setup_logging", "write_audit", "LOG_FILE", "AUDIT_FILE"]
