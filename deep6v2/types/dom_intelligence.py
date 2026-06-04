"""DOM intelligence contracts for the DEEP6 SuperDOM Intelligence Layer.

DOM STATE OWNERSHIP RULE:
The SuperDOM Intelligence Layer consumes DOMState from deep6v2/state/dom.py.
It MUST NOT instantiate a parallel or shadow DOMState.
All detectors receive DOMSnapshot instances — they do not own DOM reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.signal import Direction, SignalId


class DetectorTier(str, Enum):
    MECHANICAL = "MECHANICAL"
    HEURISTIC = "HEURISTIC"
    DISCRETIONARY_OVERLAY = "DISCRETIONARY_OVERLAY"


class ReplaySafety(str, Enum):
    REPLAY_SAFE = "REPLAY_SAFE"
    LIVE_ONLY = "LIVE_ONLY"
    REPLAY_DEGRADED = "REPLAY_DEGRADED"


@dataclass(slots=True)
class DOMIntelligenceEvent:
    signal_id: SignalId
    tier: DetectorTier
    replay_safety: ReplaySafety
    direction: Direction
    confidence: float
    price: float
    timestamp_ns: int
    detector_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    dom_state_snapshot: DOMSnapshot | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.timestamp_ns < 0:
            raise ValueError("timestamp_ns must be non-negative")
        if not self.detector_id:
            raise ValueError("detector_id must be non-empty")


@dataclass(slots=True)
class DOMIntelligenceFeatureRow:
    timestamp_ns: int
    feature_names: list[str]
    feature_values: np.ndarray
    bar_index: int
    session_id: str
    source_detector_ids: list[str]

    def __post_init__(self) -> None:
        self.feature_values = np.asarray(self.feature_values, dtype=np.float64)
        if self.feature_values.ndim != 1:
            raise ValueError("feature_values must be a 1D float64 array")
        if len(self.feature_names) != len(self.feature_values):
            raise ValueError("feature_names and feature_values must have the same length")
        if self.timestamp_ns < 0:
            raise ValueError("timestamp_ns must be non-negative")
        if not self.session_id:
            raise ValueError("session_id must be non-empty")


@dataclass(slots=True)
class DOMIntelligenceOutput:
    events: list[DOMIntelligenceEvent] = field(default_factory=list)
    feature_row: DOMIntelligenceFeatureRow | None = None
    evaluated_at_ns: int = 0
    bar_index: int = 0
    dom_state_version: int = 0

    def __post_init__(self) -> None:
        if self.evaluated_at_ns < 0:
            raise ValueError("evaluated_at_ns must be non-negative")
        if self.dom_state_version < 0:
            raise ValueError("dom_state_version must be non-negative")


__all__ = [
    "DOMIntelligenceEvent",
    "DOMIntelligenceFeatureRow",
    "DOMIntelligenceOutput",
    "DetectorTier",
    "ReplaySafety",
]
