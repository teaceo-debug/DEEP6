from __future__ import annotations

from dataclasses import fields

from deep6v2.signals.dom.taxonomy import (
    DETECTOR_TAXONOMY,
    DetectorClassification,
    DetectorTier,
    ReplaySafety,
    get_first_release_detectors,
    get_heuristic_detectors,
    get_mechanical_detectors,
    get_replay_safe_detectors,
)


def test_enums_have_exact_members() -> None:
    assert [member.name for member in ReplaySafety] == [
        "REPLAY_SAFE",
        "LIVE_ONLY",
        "REPLAY_DEGRADED",
    ]
    assert [member.name for member in DetectorTier] == [
        "MECHANICAL",
        "HEURISTIC",
        "DISCRETIONARY_OVERLAY",
    ]


def test_all_detectors_have_required_fields() -> None:
    required = {
        "detector_id",
        "name",
        "tier",
        "replay_safety",
        "description",
        "first_release",
    }
    assert {field.name for field in fields(DetectorClassification)} == required

    for detector_id, classification in DETECTOR_TAXONOMY.items():
        assert classification.detector_id == detector_id
        assert classification.name
        assert classification.description
        assert isinstance(classification.tier, DetectorTier)
        assert isinstance(classification.replay_safety, ReplaySafety)
        assert isinstance(classification.first_release, bool)


def test_tier_one_detectors_are_replay_safe() -> None:
    detectors = get_mechanical_detectors()
    assert len(detectors) == 6
    assert all(detector.replay_safety is ReplaySafety.REPLAY_SAFE for detector in detectors)


def test_tier_three_detectors_are_not_first_release() -> None:
    detectors = [detector for detector in DETECTOR_TAXONOMY.values() if detector.tier is DetectorTier.DISCRETIONARY_OVERLAY]
    assert len(detectors) == 5
    assert all(detector.first_release is False for detector in detectors)


def test_first_release_helper_returns_only_first_release_detectors() -> None:
    detectors = get_first_release_detectors()
    assert len(detectors) == 11
    assert all(detector.first_release for detector in detectors)


def test_no_duplicate_detector_ids_exist() -> None:
    detector_ids = [detector.detector_id for detector in DETECTOR_TAXONOMY.values()]
    assert len(detector_ids) == len(set(detector_ids)) == len(DETECTOR_TAXONOMY)


def test_helper_counts_match_taxonomy() -> None:
    assert len(get_mechanical_detectors()) == 6
    assert len(get_heuristic_detectors()) == 5
    assert len(get_replay_safe_detectors()) == 6
