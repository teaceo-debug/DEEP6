"""Atomic JSON writer for v3 market-bias snapshots."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

from deep6.engines.bias_contracts import MarketBiasSnapshot

VERSION = "v3"


def default_bias_v3_path() -> Path:
    return Path(
        os.path.expandvars(
            r"%USERPROFILE%\Documents\NinjaTrader 8\templates\DEEP6\bias_v3.json"
        )
    )


class BiasJsonWriter:
    """Serialize MarketBiasSnapshot into NT8-friendly JSON."""

    def __init__(self, version: str = VERSION) -> None:
        self.version = version

    def write(self, snapshot: MarketBiasSnapshot, path: Path) -> None:
        payload = self._payload(snapshot)
        self._atomic_write_json(path, payload)

    def _payload(self, snapshot: MarketBiasSnapshot) -> dict[str, Any]:
        domain_detail = snapshot.domain_detail or {}
        return {
            "bias_label": snapshot.bias_label,
            "bias_score": snapshot.bias_score,
            "confidence": snapshot.confidence,
            "confidence_pct": int(round(snapshot.confidence * 100)),
            "mode": snapshot.mode,
            "mode_reason": snapshot.mode_reason,
            "session_label": snapshot.session_label,
            "xamd_phase": snapshot.xamd_phase,
            "domain_scores": {
                "ict": self._extract_score(domain_detail.get("ict")),
                "macro": self._extract_score(domain_detail.get("macro")),
                "flow": self._extract_score(domain_detail.get("flow")),
                "kronos": self._extract_score(domain_detail.get("kronos")),
                "gex": self._extract_score(domain_detail.get("gex")),
            },
            "setup_quality": snapshot.setup_quality,
            "updated_ts": snapshot.asof_ts,
            "version": self.version,
        }

    @staticmethod
    def _extract_score(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, dict):
            raw = value.get("score", 0)
            return int(raw or 0)
        if is_dataclass(value):
            return int(getattr(value, "score", 0) or 0)
        return int(value)

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(serialized)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)


__all__ = ["BiasJsonWriter", "default_bias_v3_path", "VERSION"]
