from __future__ import annotations

from deep6v2.signals.dom.features.calibration import CALIBRATION_INPUT_REFERENCE, ThresholdCalibrator
from deep6v2.signals.dom.taxonomy import get_heuristic_detectors, get_mechanical_detectors
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.signal import Direction, SignalId


def _event(detector_id: str, tier: DetectorTier, timestamp_ns: int) -> DOMIntelligenceEvent:
    return DOMIntelligenceEvent(
        signal_id=SignalId.PIN_REGIME,
        tier=tier,
        replay_safety=ReplaySafety.REPLAY_DEGRADED if tier is DetectorTier.HEURISTIC else ReplaySafety.REPLAY_SAFE,
        direction=Direction.NEUTRAL,
        confidence=0.5,
        price=21000.25,
        timestamp_ns=timestamp_ns,
        detector_id=detector_id,
    )


def test_heuristic_detector_report_counts_and_fire_rate() -> None:
    detector_id = get_heuristic_detectors()[0].detector_id
    calibrator = ThresholdCalibrator()

    for index in range(100):
        calibrator.add_observation(_event(detector_id, DetectorTier.HEURISTIC, index), float(index))

    report = calibrator.generate_report()[0]

    assert report.detector_id == detector_id
    assert report.fire_count == 100
    assert report.total_snapshots == 100
    assert report.fire_rate == 1.0
    assert report.recommended_threshold == 94.05


def test_same_input_sequence_is_deterministic_and_serializable() -> None:
    detector_id = get_heuristic_detectors()[0].detector_id

    first = ThresholdCalibrator()
    second = ThresholdCalibrator()

    for index in range(100):
        event = _event(detector_id, DetectorTier.HEURISTIC, index)
        first.add_observation(event, float(index))
        second.add_observation(event, float(index))

    first_report = first.generate_report()
    second_report = second.generate_report()

    assert first_report == second_report
    assert first_report[0].to_json() == second_report[0].to_json()


def test_report_references_task_6b_labeled_set() -> None:
    detector_id = get_heuristic_detectors()[0].detector_id
    calibrator = ThresholdCalibrator()
    calibrator.add_observation(_event(detector_id, DetectorTier.HEURISTIC, 1), 1.25)

    report = calibrator.generate_report()[0]

    assert CALIBRATION_INPUT_REFERENCE in report.calibration_input
    assert "Task 6B" in report.calibration_input


def test_tier_one_mechanical_detector_is_rejected() -> None:
    detector_id = get_mechanical_detectors()[0].detector_id
    calibrator = ThresholdCalibrator()

    try:
        calibrator.add_observation(_event(detector_id, DetectorTier.MECHANICAL, 1), 1.0)
    except ValueError as exc:
        assert "Tier-1 mechanical" in str(exc)
    else:
        raise AssertionError("Expected Tier-1 mechanical detector calibration to be rejected")
