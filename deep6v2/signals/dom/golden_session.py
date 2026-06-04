from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable
import json
from time import time_ns as system_time_ns

import numpy as np
from pydantic import BaseModel

from deep6v2.types.dom import DOMUpdate
from deep6v2.types.dom_intelligence import DOMIntelligenceOutput


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


def _normalize_update(update: DOMUpdate, timestamp_ns: int) -> dict[str, Any]:
    payload = _to_jsonable(update)
    payload["timestamp_ns"] = timestamp_ns
    return payload


@dataclass(slots=True)
class GoldenSessionRecord:
    """Serialized DOM intelligence session for replay/parity comparison."""

    session_id: str
    recorded_at_iso: str
    instrument: str
    dom_updates: list[dict[str, Any]]
    intelligence_outputs: list[dict[str, Any]]
    metadata: dict[str, Any]
    format_version: str = "1.0"


class GoldenSessionRecorder:
    """Records live DOM intelligence session to GoldenSessionRecord."""

    def __init__(self, clock: Callable[[], int] | None = None, metadata: dict[str, Any] | None = None) -> None:
        self._clock = clock or time_ns
        self._dom_updates: list[dict[str, Any]] = []
        self._intelligence_outputs: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._recorded_at_iso: str = datetime.now(UTC).isoformat()

    def record_update(self, update: DOMUpdate) -> None:
        self._dom_updates.append(_normalize_update(update, self._clock()))

    def record_output(self, output: DOMIntelligenceOutput) -> None:
        self._intelligence_outputs.append(_to_jsonable(output))

    def finalize(self, session_id: str, instrument: str = "NQ") -> GoldenSessionRecord:
        return GoldenSessionRecord(
            session_id=session_id,
            recorded_at_iso=self._recorded_at_iso,
            instrument=instrument,
            dom_updates=[dict(item) for item in self._dom_updates],
            intelligence_outputs=[dict(item) for item in self._intelligence_outputs],
            metadata=dict(self._metadata),
        )


class GoldenSessionSerializer:
    """Serializes/deserializes GoldenSessionRecord to/from JSON."""

    @staticmethod
    def to_json(record: GoldenSessionRecord) -> str:
        payload = _to_jsonable(record)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def from_json(json_str: str) -> GoldenSessionRecord:
        payload = json.loads(json_str)
        return GoldenSessionRecord(
            session_id=payload["session_id"],
            recorded_at_iso=payload["recorded_at_iso"],
            instrument=payload["instrument"],
            dom_updates=list(payload.get("dom_updates", [])),
            intelligence_outputs=list(payload.get("intelligence_outputs", [])),
            metadata=dict(payload.get("metadata", {})),
            format_version=payload.get("format_version", "1.0"),
        )

    @staticmethod
    def to_file(record: GoldenSessionRecord, path: str) -> None:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(GoldenSessionSerializer.to_json(record), encoding="utf-8")

    @staticmethod
    def from_file(path: str) -> GoldenSessionRecord:
        return GoldenSessionSerializer.from_json(Path(path).read_text(encoding="utf-8"))


def time_ns() -> int:
    return system_time_ns()


__all__ = [
    "GoldenSessionRecord",
    "GoldenSessionRecorder",
    "GoldenSessionSerializer",
]
