from __future__ import annotations

from deep6v2.signals.dom.compat.signal_contract import (
    DOM_DETECTOR_COMPATIBILITY_RULES,
    DOM_DETECTOR_TO_SIGNAL_ID,
    DOM_ENTRY_GATE_POLICY,
    DOM_SIGNAL_TO_CATEGORY,
    MVP_NEW_SIGNAL_IDS_ALLOWED,
    ROLLBACK_RULE,
)
from deep6v2.signals.dom.taxonomy import DETECTOR_TAXONOMY, DetectorTier
from deep6v2.types.signal import SIGNAL_TO_CATEGORY, SignalCategory, SignalId


def test_mvp_disallows_new_signal_ids() -> None:
    assert MVP_NEW_SIGNAL_IDS_ALLOWED is False


def test_mapping_covers_all_dom_detectors() -> None:
    assert set(DOM_DETECTOR_TO_SIGNAL_ID) == set(DETECTOR_TAXONOMY)
    assert set(DOM_DETECTOR_COMPATIBILITY_RULES) == set(DETECTOR_TAXONOMY)


def test_tier_one_detectors_all_map_to_existing_signal_ids() -> None:
    mapped = {
        detector_id: signal_id
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items()
        if DETECTOR_TAXONOMY[detector_id].tier is DetectorTier.MECHANICAL
    }

    assert len(mapped) == 6
    assert all(signal_id is not None for signal_id in mapped.values())


def test_tier_two_detectors_are_feature_only_in_mvp() -> None:
    mapped = {
        detector_id: signal_id
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items()
        if DETECTOR_TAXONOMY[detector_id].tier is DetectorTier.HEURISTIC
    }

    assert len(mapped) == 5
    assert all(signal_id is None for signal_id in mapped.values())


def test_tier_three_detectors_are_overlay_only_in_mvp() -> None:
    mapped = {
        detector_id: signal_id
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items()
        if DETECTOR_TAXONOMY[detector_id].tier is DetectorTier.DISCRETIONARY_OVERLAY
    }

    assert len(mapped) == 5
    assert all(signal_id is None for signal_id in mapped.values())


def test_entry_gate_policy_mentions_all_replay_safety_modes() -> None:
    assert "REPLAY_SAFE" in DOM_ENTRY_GATE_POLICY
    assert "REPLAY_DEGRADED" in DOM_ENTRY_GATE_POLICY
    assert "LIVE_ONLY" in DOM_ENTRY_GATE_POLICY
    assert "entry_gate.py" in DOM_ENTRY_GATE_POLICY


def test_rollback_rule_mentions_feature_flag_mechanism() -> None:
    assert "feature flag" in ROLLBACK_RULE.lower()
    assert "DOM_INTELLIGENCE_ENABLED" in ROLLBACK_RULE
    assert "DetectorRegistry.create_default()" in ROLLBACK_RULE


def test_mapped_signal_ids_are_valid_signal_enum_members() -> None:
    valid_members = set(SignalId)
    for signal_id in DOM_DETECTOR_TO_SIGNAL_ID.values():
        if signal_id is not None:
            assert signal_id in valid_members


def test_category_mapping_matches_existing_signal_category_table() -> None:
    expected = {
        detector_id: SIGNAL_TO_CATEGORY[signal_id]
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items()
        if signal_id is not None
    }

    assert DOM_SIGNAL_TO_CATEGORY == expected
    assert all(isinstance(category, SignalCategory) for category in DOM_SIGNAL_TO_CATEGORY.values())


def test_every_detector_has_an_explicit_compatibility_rule() -> None:
    for detector_id in DETECTOR_TAXONOMY:
        rule = DOM_DETECTOR_COMPATIBILITY_RULES[detector_id]
        assert rule
        if DOM_DETECTOR_TO_SIGNAL_ID[detector_id] is None:
            assert "None" in rule or "feature" in rule.lower() or "overlay" in rule.lower()
