"""Replay evaluation harness for Standard Deviation Anchor AI fixtures."""

from __future__ import annotations

import json
from pathlib import Path


FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_STATES = {"candidate", "confirmed", "active"}


def load_anchor_fixture(name: str) -> dict:
    """Load a replay anchor fixture by filename stem."""
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text())


def compute_deviation_levels(direction: str, anchor_low: float, anchor_high: float) -> dict[str, float]:
    """Compute deterministic deviation targets from a wick-to-wick anchor."""
    anchor_range = anchor_high - anchor_low
    if direction == "bullish":
        return {
            "level_minus2": anchor_high + anchor_range * 2,
            "level_minus2_5": anchor_high + anchor_range * 2.5,
            "level_minus4": anchor_high + anchor_range * 4,
        }
    if direction == "bearish":
        return {
            "level_minus2": anchor_low - anchor_range * 2,
            "level_minus2_5": anchor_low - anchor_range * 2.5,
            "level_minus4": anchor_low - anchor_range * 5,
        }
    raise ValueError(f"Unsupported direction: {direction}")


def pine_accepts(record: dict) -> bool:
    """Pine accepts only sufficiently confident, non-invalidated anchors."""
    return record["pine_confidence_score"] >= 70 and record["pine_state"] in VALID_STATES


def evaluate_record(record: dict) -> dict:
    """Project a fixture into replay-harness metrics without mutating it."""
    deterministic_accept = pine_accepts(record)
    hermes_verdict = record["hermes_verdict"]
    hermes_accept = hermes_verdict == "approve"
    return {
        "anchor_id": record["anchor_id"],
        "mode": record["mode"],
        "label_timing": record["label_timing"],
        "pine_accepts": deterministic_accept,
        "hermes_verdict": hermes_verdict,
        "hermes_accepts": hermes_accept,
        "disagreement": deterministic_accept != hermes_accept,
    }


def run_eval_harness() -> dict:
    """Run replay fixtures through deterministic Pine and HERMES evaluation accounting."""
    records = [
        load_anchor_fixture("valid_bullish_anchor"),
        load_anchor_fixture("valid_bearish_anchor"),
        load_anchor_fixture("invalid_chop_anchor"),
    ]
    evaluations = [evaluate_record(record) for record in records]
    return {
        "total_records": len(records),
        "deterministic_accepts": sum(item["pine_accepts"] for item in evaluations),
        "deterministic_rejects": sum(not item["pine_accepts"] for item in evaluations),
        "hermes_approves": sum(item["hermes_verdict"] == "approve" for item in evaluations),
        "hermes_vetoes": sum(item["hermes_verdict"] == "veto" for item in evaluations),
        "disagreements": sum(item["disagreement"] for item in evaluations),
        "modes": {item["mode"] for item in evaluations},
        "label_timings": {item["label_timing"] for item in evaluations},
        "evaluations": evaluations,
    }


def test_valid_bullish_candidate_accepted() -> None:
    record = load_anchor_fixture("valid_bullish_anchor")
    assert record["pine_confidence_score"] >= 70
    assert record["pine_state"] in {"candidate", "confirmed"}
    assert pine_accepts(record) is True


def test_valid_bearish_candidate_accepted() -> None:
    record = load_anchor_fixture("valid_bearish_anchor")
    assert record["pine_confidence_score"] >= 70
    assert record["pine_state"] in {"candidate", "confirmed"}
    assert pine_accepts(record) is True


def test_chop_candidate_rejected() -> None:
    record = load_anchor_fixture("invalid_chop_anchor")
    assert record["pine_confidence_score"] < 70 or record["pine_state"] == "invalidated"
    assert pine_accepts(record) is False


def test_deviation_formula_bullish() -> None:
    levels = compute_deviation_levels("bullish", anchor_low=100, anchor_high=110)
    assert levels["level_minus2"] == 130
    assert levels["level_minus2_5"] == 135
    assert levels["level_minus4"] == 150


def test_deviation_formula_bearish() -> None:
    levels = compute_deviation_levels("bearish", anchor_low=100, anchor_high=110)
    assert levels["level_minus2"] == 80
    assert levels["level_minus2_5"] == 75
    assert levels["level_minus4"] == 50


def test_record_mode_labels() -> None:
    for fixture_name in ["valid_bullish_anchor", "valid_bearish_anchor", "invalid_chop_anchor"]:
        record = load_anchor_fixture(fixture_name)
        assert record["mode"] == "replay"
        assert record["label_timing"] == "decision_time"


def test_no_outcome_at_capture() -> None:
    for fixture_name in ["valid_bullish_anchor", "valid_bearish_anchor", "invalid_chop_anchor"]:
        record = load_anchor_fixture(fixture_name)
        assert record["outcome_label"] is None
        assert record["outcome_resolved_at"] is None


def test_harness_distinguishes_deterministic_output_from_hermes_verdicts() -> None:
    results = run_eval_harness()
    assert results["total_records"] == 3
    assert results["deterministic_accepts"] == 2
    assert results["deterministic_rejects"] == 1
    assert results["hermes_approves"] == 1
    assert results["hermes_vetoes"] == 2
    assert results["disagreements"] == 1
    assert results["modes"] == {"replay"}
    assert results["label_timings"] == {"decision_time"}
