"""Deterministic threshold calibration for Tier-2 DOM detectors.

Calibration is pure and in-memory: it records heuristic detector observations,
computes per-detector fire rates, and recommends a threshold from the 95th
percentile of observed feature values.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Any

from deep6v2.signals.dom.taxonomy import get_heuristic_detectors
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier


CALIBRATION_INPUT_REFERENCE = "Task 6B golden sessions"


def _percentile_95(values: list[float]) -> float:
    if not values:
        raise ValueError("values must not be empty")

    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * 0.95
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    if lower_index == upper_index:
        return ordered[lower_index]

    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    fraction = position - lower_index
    return lower_value + (upper_value - lower_value) * fraction


@dataclass
class CalibrationReport:
    detector_id: str
    fire_count: int
    total_snapshots: int
    fire_rate: float
    recommended_threshold: float
    sample_values: list[float]
    calibration_input: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class ThresholdCalibrator:
    """Runs calibration on heuristic DOM detector observations."""

    def __init__(self, calibration_input: str = CALIBRATION_INPUT_REFERENCE) -> None:
        self._calibration_input = calibration_input
        self._allowed_detector_ids = {
            detector.detector_id for detector in get_heuristic_detectors()
        }
        self._observations: dict[str, list[float]] = {}

    def add_observation(self, event: DOMIntelligenceEvent, feature_value: float) -> None:
        """Record one observation from a heuristic detector."""

        if event.tier is not DetectorTier.HEURISTIC:
            raise ValueError("Tier-1 mechanical and non-heuristic detectors cannot be calibrated")
        if event.detector_id not in self._allowed_detector_ids:
            raise ValueError(f"Detector '{event.detector_id}' is not eligible for threshold calibration")

        self._observations.setdefault(event.detector_id, []).append(float(feature_value))

    def generate_report(self) -> list[CalibrationReport]:
        """Return deterministic per-detector calibration reports."""

        reports: list[CalibrationReport] = []
        for detector_id in sorted(self._observations):
            sample_values = list(self._observations[detector_id])
            total_snapshots = len(sample_values)
            fire_count = total_snapshots
            fire_rate = fire_count / total_snapshots if total_snapshots else 0.0
            reports.append(
                CalibrationReport(
                    detector_id=detector_id,
                    fire_count=fire_count,
                    total_snapshots=total_snapshots,
                    fire_rate=fire_rate,
                    recommended_threshold=_percentile_95(sample_values),
                    sample_values=sample_values,
                    calibration_input=self._calibration_input,
                )
            )
        return reports


__all__ = [
    "CALIBRATION_INPUT_REFERENCE",
    "CalibrationReport",
    "ThresholdCalibrator",
]
