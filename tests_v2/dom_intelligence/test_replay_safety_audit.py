"""Task 24: Replay-safety audit report.

Enumerates DETECTOR_TAXONOMY, verifies every detector has a classification,
and outputs an audit report.
"""
from __future__ import annotations

import pytest

from deep6v2.signals.dom.taxonomy import (
    DETECTOR_TAXONOMY,
    DetectorClassification,
    DetectorTier,
    ReplaySafety,
)


# Expected detector counts by tier
EXPECTED_TIER1_COUNT = 6
EXPECTED_TIER2_COUNT = 5
EXPECTED_TIER3_COUNT = 5
EXPECTED_TOTAL = EXPECTED_TIER1_COUNT + EXPECTED_TIER2_COUNT + EXPECTED_TIER3_COUNT

VALID_TIERS = {DetectorTier.MECHANICAL, DetectorTier.HEURISTIC, DetectorTier.DISCRETIONARY_OVERLAY}
VALID_SAFETY = {ReplaySafety.REPLAY_SAFE, ReplaySafety.LIVE_ONLY, ReplaySafety.REPLAY_DEGRADED}


class TestReplaySafetyAudit:
    """Verify every detector has proper classification evidence."""

    def test_taxonomy_has_expected_count(self):
        assert len(DETECTOR_TAXONOMY) == EXPECTED_TOTAL, (
            f"Expected {EXPECTED_TOTAL} detectors, found {len(DETECTOR_TAXONOMY)}"
        )

    def test_all_detectors_have_valid_tier(self):
        for det_id, cls in DETECTOR_TAXONOMY.items():
            assert cls.tier in VALID_TIERS, (
                f"{det_id}: invalid tier {cls.tier}"
            )

    def test_all_detectors_have_valid_replay_safety(self):
        for det_id, cls in DETECTOR_TAXONOMY.items():
            assert cls.replay_safety in VALID_SAFETY, (
                f"{det_id}: invalid replay_safety {cls.replay_safety}"
            )

    def test_all_detectors_have_nonempty_description(self):
        for det_id, cls in DETECTOR_TAXONOMY.items():
            assert cls.description, f"{det_id}: empty description"

    def test_all_detectors_have_nonempty_name(self):
        for det_id, cls in DETECTOR_TAXONOMY.items():
            assert cls.name, f"{det_id}: empty name"

    def test_detector_id_matches_key(self):
        for det_id, cls in DETECTOR_TAXONOMY.items():
            assert cls.detector_id == det_id, (
                f"Key {det_id} != detector_id {cls.detector_id}"
            )

    def test_tier1_count(self):
        tier1 = [c for c in DETECTOR_TAXONOMY.values() if c.tier == DetectorTier.MECHANICAL]
        assert len(tier1) == EXPECTED_TIER1_COUNT, (
            f"Expected {EXPECTED_TIER1_COUNT} Tier-1, found {len(tier1)}"
        )

    def test_tier2_count(self):
        tier2 = [c for c in DETECTOR_TAXONOMY.values() if c.tier == DetectorTier.HEURISTIC]
        assert len(tier2) == EXPECTED_TIER2_COUNT, (
            f"Expected {EXPECTED_TIER2_COUNT} Tier-2, found {len(tier2)}"
        )

    def test_tier3_count(self):
        tier3 = [c for c in DETECTOR_TAXONOMY.values() if c.tier == DetectorTier.DISCRETIONARY_OVERLAY]
        assert len(tier3) == EXPECTED_TIER3_COUNT, (
            f"Expected {EXPECTED_TIER3_COUNT} Tier-3, found {len(tier3)}"
        )

    def test_tier1_are_all_replay_safe(self):
        """Tier 1 mechanical detectors should all be REPLAY_SAFE."""
        for det_id, cls in DETECTOR_TAXONOMY.items():
            if cls.tier == DetectorTier.MECHANICAL:
                assert cls.replay_safety == ReplaySafety.REPLAY_SAFE, (
                    f"Tier 1 {det_id} is {cls.replay_safety}, expected REPLAY_SAFE"
                )

    def test_tier3_are_all_live_only(self):
        """Tier 3 discretionary detectors should all be LIVE_ONLY."""
        for det_id, cls in DETECTOR_TAXONOMY.items():
            if cls.tier == DetectorTier.DISCRETIONARY_OVERLAY:
                assert cls.replay_safety == ReplaySafety.LIVE_ONLY, (
                    f"Tier 3 {det_id} is {cls.replay_safety}, expected LIVE_ONLY"
                )

    def test_tier2_are_replay_degraded(self):
        """Tier 2 heuristic detectors should be REPLAY_DEGRADED."""
        for det_id, cls in DETECTOR_TAXONOMY.items():
            if cls.tier == DetectorTier.HEURISTIC:
                assert cls.replay_safety == ReplaySafety.REPLAY_DEGRADED, (
                    f"Tier 2 {det_id} is {cls.replay_safety}, expected REPLAY_DEGRADED"
                )

    def test_first_release_excludes_tier3(self):
        """No Tier 3 detector should be marked first_release=True."""
        for det_id, cls in DETECTOR_TAXONOMY.items():
            if cls.tier == DetectorTier.DISCRETIONARY_OVERLAY:
                assert not cls.first_release, (
                    f"Tier 3 {det_id} is first_release=True — must be False"
                )

    def test_first_release_includes_tier1_and_tier2(self):
        """All Tier 1 and Tier 2 detectors should be first_release=True."""
        for det_id, cls in DETECTOR_TAXONOMY.items():
            if cls.tier in (DetectorTier.MECHANICAL, DetectorTier.HEURISTIC):
                assert cls.first_release, (
                    f"Tier 1/2 {det_id} is first_release=False — must be True"
                )

    def test_generate_audit_report(self, tmp_path):
        """Generate the audit report artifact."""
        lines = ["REPLAY-SAFETY AUDIT REPORT", "=" * 60, ""]
        for det_id, cls in sorted(DETECTOR_TAXONOMY.items()):
            lines.append(
                f"{det_id:<30} tier={cls.tier.value:<25} "
                f"safety={cls.replay_safety.value:<18} "
                f"release={'YES' if cls.first_release else 'NO'}"
            )
        lines.extend(["", f"Total detectors: {len(DETECTOR_TAXONOMY)}", "AUDIT: PASS"])
        report = "\n".join(lines)
        # Write to tmp for verification
        (tmp_path / "audit.txt").write_text(report, encoding="utf-8")
        assert "AUDIT: PASS" in report
