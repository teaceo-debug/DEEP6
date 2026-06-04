from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["get_logger", "AuditTrail"]


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            doc["exception"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Return a configured logger with console and optional JSONL file output."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    logger.addHandler(console)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / f"gexdoctor-{date_str}.jsonl",
            maxBytes=10 * 1024 * 1024,
            backupCount=7,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_JsonFormatter())
        logger.addHandler(file_handler)

    return logger


class AuditTrail:
    """Writes per-cycle audit records to a JSONL file."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.log_path = log_dir / f"audit-{date_str}.jsonl"

    def record(
        self,
        sources_polled: list[str],
        levels_received: int,
        magnet_selected: float | None,
        confidence: float,
        bias_direction: str = "no_vote",
        errors: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        doc: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sources_polled": sources_polled,
            "levels_received": levels_received,
            "magnet_selected": magnet_selected,
            "confidence": confidence,
            "bias_direction": bias_direction,
            "errors": errors or [],
        }
        if extra:
            doc.update(extra)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")
