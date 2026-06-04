"""Backward-compatibility tests: DOM-intelligence outputs must not silently break
existing registry/scorer consumers.

Task 7B — verifies payload shape compatibility, scorer acceptance of Tier-1
signals, Tier-2 exclusion, registry interface compatibility, and the SignalId
freeze policy.
"""

from __future__ import annotations

import inspect
import typing
from typing import get_type_hints

import pytest

from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.signals.dom.compat.signal_contract import (
    DOM_DETECTOR_TO_SIGNAL_ID,
    DOM_SIGNAL_TO_CATEGORY,
    MVP_NEW_SIGNAL_IDS_ALLOWED,
)
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.interfaces import IDepthConsumingDetector, ISignalDetector
from deep6v2.types.signal import (
    SIGNAL_TO_CATEGORY,
    Direction,
    SignalCategory,
    SignalFlagBits,
    SignalId,
    SignalResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Frozen set of ALL SignalId values at test-write time.  If someone sneaks a
# new DOM-specific ID into the enum, Test 5 catches it.
_BASELINE_SIGNAL_IDS: frozenset[str] = frozenset(
    {
        "ABS_01", "ABS_02", "ABS_03", "ABS_04",
        "EXH_01", "EXH_02", "EXH_03", "EXH_04", "EXH_05", "EXH_06",
        "IMB_01", "IMB_02", "IMB_03", "IMB_04", "IMB_05", "IMB_06",
        "IMB_07", "IMB_08", "IMB_09",
        "DELT_01", "DELT_02", "DELT_03", "DELT_04", "DELT_05", "DELT_06",
        "DELT_07", "DELT_08", "DELT_09", "DELT_10", "DELT_11",
        "AUCT_01", "AUCT_02", "AUCT_03", "AUCT_04", "AUCT_05",
        "TRAP_01", "TRAP_02", "TRAP_03", "TRAP_04", "TRAP_05",
        "VOLP_01", "VOLP_02", "VOLP_03", "VOLP_04", "VOLP_05", "VOLP_06",
        "ENG_02", "ENG_03", "ENG_04", "ENG_05", "ENG_06", "ENG_07",
        "PIN_REGIME", "REGIME_CHANGE", "SPOOF_VETO",
    }
)


def _dom_event_to_signal_result(event: DOMIntelligenceEvent) -> SignalResult:
    """Convert a DOMIntelligenceEvent to a SignalResult (old-path shape)."""
    flag_bit = getattr(SignalFlagBits, event.signal_id.name, 0)
    return SignalResult(
        signal_id=event.signal_id,
        direction=event.direction,
        strength=event.confidence,
        detail=f"dom_compat:{event.detector_id}",
        price=event.price,
        flag_bit=flag_bit,
    )


def _make_tier1_event(
    detector_id: str,
    signal_id: SignalId,
    *,
    direction: Direction = Direction.BULLISH,
    confidence: float = 0.72,
    price: float = 21500.0,
) -> DOMIntelligenceEvent:
    """Factory for a Tier-1 mechanical DOMIntelligenceEvent."""
    return DOMIntelligenceEvent(
        signal_id=signal_id,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=direction,
        confidence=confidence,
        price=price,
        timestamp_ns=1_000_000_000,
        detector_id=detector_id,
    )


# ============================================================================
# Test 1: SignalResult shape compatibility
# ============================================================================

class TestSignalResultShapeCompatibility:
    """DOMIntelligenceEvent → SignalResult conversion must produce an object the
    scorer accepts without error."""

    def test_dom_event_converts_to_signal_result(self) -> None:
        event = _make_tier1_event("dom.imbalance.v1", SignalId.IMB_01)
        result = _dom_event_to_signal_result(event)

        assert isinstance(result, SignalResult)
        assert result.signal_id == SignalId.IMB_01
        assert result.direction == Direction.BULLISH
        assert result.strength == pytest.approx(0.72)
        assert result.price == 21500.0
        assert result.detail.startswith("dom_compat:")

    def test_converted_result_has_required_scorer_fields(self) -> None:
        """ConfluenceScorer.score() reads signal_id, direction, strength from
        each SignalResult.  Verify the converted object exposes them."""
        event = _make_tier1_event("dom.absorption.v1", SignalId.ABS_01)
        result = _dom_event_to_signal_result(event)

        required_fields = {"signal_id", "direction", "strength"}
        result_fields = set(type(result).model_fields.keys())
        assert required_fields.issubset(result_fields), (
            f"Missing fields for scorer: {required_fields - result_fields}"
        )

    def test_all_tier1_detectors_convert_cleanly(self) -> None:
        """Every Tier-1 detector with a non-None SignalId mapping must convert
        to a valid SignalResult without raising."""
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items():
            if signal_id is None:
                continue
            event = _make_tier1_event(detector_id, signal_id)
            result = _dom_event_to_signal_result(event)
            assert result.signal_id == signal_id, f"Mismatch for {detector_id}"


# ============================================================================
# Test 2: Scorer accepts Tier-1 DOM signals mapped to existing SignalIds
# ============================================================================

class TestScorerAcceptsTier1:
    """Tier-1 mapped DOM signals must be accepted by ConfluenceScorer.score()
    with correct category routing and non-zero weight."""

    def test_imb01_accepted_by_scorer(self) -> None:
        event = _make_tier1_event("dom.imbalance.v1", SignalId.IMB_01)
        result = _dom_event_to_signal_result(event)

        scorer = ConfluenceScorer()
        scorer_out = scorer.score([result], bar_index=10)

        assert scorer_out.category_count >= 1
        assert "imbalance" in scorer_out.category_scores
        assert scorer_out.category_scores["imbalance"] > 0.0

    def test_imb01_maps_to_imbalance_category(self) -> None:
        assert SIGNAL_TO_CATEGORY[SignalId.IMB_01] == SignalCategory.IMBALANCE

    @pytest.mark.parametrize(
        "detector_id,signal_id,expected_category",
        [
            ("dom.imbalance.v1", SignalId.IMB_01, SignalCategory.IMBALANCE),
            ("dom.absorption.v1", SignalId.ABS_01, SignalCategory.ABSORPTION),
            ("dom.sweep_reload.v1", SignalId.ABS_02, SignalCategory.ABSORPTION),
            ("dom.iceberg.v1", SignalId.ENG_04, SignalCategory.ABSORPTION),
            ("dom.cvd.v1", SignalId.DELT_01, SignalCategory.DELTA),
            ("dom.thinness.v1", SignalId.IMB_02, SignalCategory.IMBALANCE),
        ],
    )
    def test_tier1_category_mapping(
        self, detector_id: str, signal_id: SignalId, expected_category: SignalCategory
    ) -> None:
        """Each Tier-1 detector must land in the correct scorer category."""
        category = SIGNAL_TO_CATEGORY.get(signal_id)
        assert category == expected_category, (
            f"{detector_id} -> {signal_id} expected category "
            f"{expected_category}, got {category}"
        )

    @pytest.mark.parametrize(
        "detector_id,signal_id",
        [
            ("dom.imbalance.v1", SignalId.IMB_01),
            ("dom.absorption.v1", SignalId.ABS_01),
            ("dom.sweep_reload.v1", SignalId.ABS_02),
            ("dom.iceberg.v1", SignalId.ENG_04),
            ("dom.cvd.v1", SignalId.DELT_01),
            ("dom.thinness.v1", SignalId.IMB_02),
        ],
    )
    def test_tier1_has_nonzero_scorer_weight(
        self, detector_id: str, signal_id: SignalId
    ) -> None:
        """Every Tier-1 mapped signal must land in a category with weight > 0."""
        category = SIGNAL_TO_CATEGORY[signal_id]
        assert category is not None
        scorer = ConfluenceScorer()
        weight = scorer._category_weights[category]
        assert weight > 0.0, (
            f"{detector_id} -> {signal_id} -> {category}: scorer weight is 0"
        )

    def test_scorer_does_not_raise_on_full_tier1_payload(self) -> None:
        """Send all 6 Tier-1 signals at once; scorer must not raise."""
        signals: list[SignalResult] = []
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items():
            if signal_id is None:
                continue
            event = _make_tier1_event(detector_id, signal_id)
            signals.append(_dom_event_to_signal_result(event))

        scorer = ConfluenceScorer()
        result = scorer.score(signals, bar_index=10)
        assert result.final_score >= 0.0
        assert result.category_count >= 1


# ============================================================================
# Test 3: Heuristic signals (None mapping) are NOT accidentally scored
# ============================================================================

class TestTier2NotScored:
    """Tier-2 detectors with ``None`` SignalId mapping must never produce a
    scored signal; they must produce feature rows only."""

    _TIER2_DETECTORS: list[str] = [
        detector_id
        for detector_id, sid in DOM_DETECTOR_TO_SIGNAL_ID.items()
        if sid is None
    ]

    def test_tier2_detectors_exist(self) -> None:
        """Sanity: there are at least 5 Tier-2/3 None-mapped detectors."""
        assert len(self._TIER2_DETECTORS) >= 5

    @pytest.mark.parametrize("detector_id", _TIER2_DETECTORS)
    def test_none_mapped_has_no_signal_id(self, detector_id: str) -> None:
        """Verify the mapping is truly None in the contract."""
        assert DOM_DETECTOR_TO_SIGNAL_ID[detector_id] is None, (
            f"{detector_id} should map to None but maps to "
            f"{DOM_DETECTOR_TO_SIGNAL_ID[detector_id]}"
        )

    @pytest.mark.parametrize("detector_id", _TIER2_DETECTORS)
    def test_none_mapped_not_in_dom_signal_to_category(
        self, detector_id: str
    ) -> None:
        """None-mapped detectors must NOT appear in DOM_SIGNAL_TO_CATEGORY
        (derived mapping used for routing)."""
        assert detector_id not in DOM_SIGNAL_TO_CATEGORY, (
            f"{detector_id} must not be in DOM_SIGNAL_TO_CATEGORY"
        )

    def test_none_mapped_cannot_produce_signal_result(self) -> None:
        """Attempting to build a SignalResult for a None-mapped detector should
        be impossible without a SignalId."""
        for detector_id in self._TIER2_DETECTORS:
            signal_id = DOM_DETECTOR_TO_SIGNAL_ID[detector_id]
            assert signal_id is None
            # Cannot construct a valid SignalResult without a real SignalId
            with pytest.raises((ValueError, TypeError, KeyError)):
                SignalResult(
                    signal_id=signal_id,  # type: ignore[arg-type]
                    direction=Direction.NEUTRAL,
                    strength=0.5,
                    detail="should_fail",
                    price=21500.0,
                    flag_bit=0,
                )

    def test_feature_row_is_valid_alternative_for_tier2(self) -> None:
        """Tier-2 detectors should produce DOMIntelligenceFeatureRow (not
        SignalResult).  Verify the feature row type constructs without error."""
        import numpy as np

        row = DOMIntelligenceFeatureRow(
            timestamp_ns=1_000_000_000,
            feature_names=["pull_replace_ratio", "pull_replace_speed"],
            feature_values=np.array([0.65, 1.2], dtype=np.float64),
            bar_index=42,
            session_id="golden_quiet_rth",
            source_detector_ids=["dom.pull_replace.v1"],
        )
        assert len(row.feature_names) == 2
        assert row.feature_values.shape == (2,)


# ============================================================================
# Test 4: Registry interface compatibility
# ============================================================================

class TestRegistryInterfaceCompat:
    """DetectorRegistry interfaces (on_depth, evaluate_bar) must have
    signatures that DOM detectors can satisfy."""

    def test_on_depth_accepts_dom_snapshot(self) -> None:
        """IDepthConsumingDetector.on_depth expects (DOMSnapshot) -> None."""
        hints = get_type_hints(IDepthConsumingDetector.on_depth)
        params = inspect.signature(IDepthConsumingDetector.on_depth).parameters

        # Must have 'snapshot' parameter (or 'self' + 'snapshot')
        param_names = [n for n in params if n != "self"]
        assert len(param_names) == 1, (
            f"on_depth should take exactly 1 param (snapshot), got {param_names}"
        )
        assert "snapshot" in param_names

    def test_on_bar_returns_list_signal_result(self) -> None:
        """ISignalDetector.on_bar must return list[SignalResult]."""
        hints = get_type_hints(ISignalDetector.on_bar)
        return_hint = hints.get("return")
        assert return_hint is not None

        origin = typing.get_origin(return_hint)
        assert origin is list, f"Expected list, got {origin}"

        args = typing.get_args(return_hint)
        assert len(args) == 1
        assert args[0] is SignalResult

    def test_evaluate_bar_signature(self) -> None:
        """DetectorRegistry.evaluate_bar(bar, ctx) -> list[SignalResult]."""
        from deep6v2.signals.registry import DetectorRegistry

        sig = inspect.signature(DetectorRegistry.evaluate_bar)
        params = list(sig.parameters.keys())
        assert "bar" in params
        assert "ctx" in params

        hints = get_type_hints(DetectorRegistry.evaluate_bar)
        assert hints.get("return") == list[SignalResult]

    def test_registry_on_depth_signature(self) -> None:
        """DetectorRegistry.on_depth(snapshot) -> None."""
        from deep6v2.signals.registry import DetectorRegistry

        sig = inspect.signature(DetectorRegistry.on_depth)
        params = [p for p in sig.parameters if p != "self"]
        assert "snapshot" in params


# ============================================================================
# Test 5: No new SignalId added to types/signal.py
# ============================================================================

class TestSignalIdFreeze:
    """No DOM-intelligence-specific SignalId values may be added to the enum
    during MVP."""

    def test_mvp_new_signal_ids_allowed_is_false(self) -> None:
        assert MVP_NEW_SIGNAL_IDS_ALLOWED is False, (
            "MVP_NEW_SIGNAL_IDS_ALLOWED must remain False"
        )

    def test_signal_id_enum_unchanged(self) -> None:
        """Compare current SignalId members against the baseline snapshot."""
        current_ids = frozenset(member.value for member in SignalId)
        assert current_ids == _BASELINE_SIGNAL_IDS, (
            f"SignalId enum has changed!\n"
            f"  Added: {current_ids - _BASELINE_SIGNAL_IDS}\n"
            f"  Removed: {_BASELINE_SIGNAL_IDS - current_ids}"
        )

    def test_no_dom_prefixed_signal_ids(self) -> None:
        """No SignalId member should start with 'DOM_' — that would signal
        someone tried to add DOM-specific IDs."""
        dom_ids = [sid for sid in SignalId if sid.value.startswith("DOM_")]
        assert dom_ids == [], f"Found DOM-specific SignalIds: {dom_ids}"

    def test_all_tier1_mappings_use_preexisting_signal_ids(self) -> None:
        """Every non-None mapping in DOM_DETECTOR_TO_SIGNAL_ID must reference
        a SignalId that exists in the baseline set."""
        for detector_id, signal_id in DOM_DETECTOR_TO_SIGNAL_ID.items():
            if signal_id is None:
                continue
            assert signal_id.value in _BASELINE_SIGNAL_IDS, (
                f"{detector_id} maps to {signal_id.value} which is not in "
                f"the baseline SignalId set"
            )


# ============================================================================
# Aggregate contract assertion
# ============================================================================

class TestAggregateContract:
    """Cross-cutting: scorer round-trip through old path and new (DOM) path
    must produce structurally identical ScorerResult fields."""

    def test_old_path_vs_dom_path_scorer_result_fields(self) -> None:
        """Build a SignalResult the old way and the DOM way; feed both to
        scorer; verify the ScorerResult schema is identical."""
        old_signal = SignalResult(
            signal_id=SignalId.IMB_01,
            direction=Direction.BULLISH,
            strength=0.72,
            detail="old_path:imbalance_classic",
            price=21500.0,
            flag_bit=SignalFlagBits.IMB_01,
        )

        dom_event = _make_tier1_event("dom.imbalance.v1", SignalId.IMB_01)
        dom_signal = _dom_event_to_signal_result(dom_event)

        scorer = ConfluenceScorer()
        old_result = scorer.score([old_signal], bar_index=10)
        dom_result = scorer.score([dom_signal], bar_index=10)

        # Structural equality: same fields, same types
        assert set(type(old_result).model_fields.keys()) == set(
            type(dom_result).model_fields.keys()
        )
        # Category routing identical
        assert old_result.category_scores.keys() == dom_result.category_scores.keys()
        # Scores equal (same strength, same bar_index, same defaults)
        assert old_result.final_score == pytest.approx(dom_result.final_score)
        assert old_result.tier == dom_result.tier
