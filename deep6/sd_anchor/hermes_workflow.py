"""HERMES Standard-Deviation Expert Workflow.

Implements the 5-step checklist review for Pine candidate anchors.
HERMES approves, vetoes, or abstains. It does NOT draw on the chart.
It does NOT invent new pattern families. The core anchor doctrine is frozen.

Contract references:
  - .sisyphus/contracts/hermes-authority.md  (authority boundary)
  - .sisyphus/contracts/anchor-contract.md   (anchor state machine)
  - .claude/skills/hermes-sd-anchor/knowledge.md (HERMES doctrine)

Key invariants:
  - Approve only when total checklist score >= 70.
  - Veto with explicit reason codes when score < 70 or rejection trigger fires.
  - Abstain when evidence is insufficient.
  - No new pattern families. No legacy anchor heuristics. No chart drawing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deep6.sd_anchor.types import HermesVerdict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HERMES_VERSION = "1.0.0"
_APPROVAL_THRESHOLD = 70

# Reason codes from hermes-authority.md
_RC_STRUCTURE_CLEAR = "STRUCTURE_CLEAR"
_RC_STRUCTURE_UNCLEAR = "STRUCTURE_UNCLEAR"
_RC_DISPLACEMENT_CONFIRMED = "DISPLACEMENT_CONFIRMED"
_RC_DISPLACEMENT_WEAK = "DISPLACEMENT_WEAK"
_RC_ANCHOR_ALIGNMENT_VALID = "ANCHOR_ALIGNMENT_VALID"
_RC_ANCHOR_ALIGNMENT_INVALID = "ANCHOR_ALIGNMENT_INVALID"
_RC_MTF_SUPPORT_PRESENT = "MTF_SUPPORT_PRESENT"
_RC_MTF_SUPPORT_ABSENT = "MTF_SUPPORT_ABSENT"
_RC_CONFIDENCE_SUFFICIENT = "CONFIDENCE_SUFFICIENT"
_RC_CONFIDENCE_INSUFFICIENT = "CONFIDENCE_INSUFFICIENT"
_RC_CHOP_RISK_HIGH = "CHOP_RISK_HIGH"
_RC_SCREENSHOT_INSUFFICIENT = "SCREENSHOT_INSUFFICIENT"
_RC_CANDIDATE_METADATA_INCOMPLETE = "CANDIDATE_METADATA_INCOMPLETE"

# Rejection trigger thresholds
_MIN_CONFIDENCE_SCORE = 40   # below this = clearly forced
_MIN_RANGE = 0.5             # below this = swing too small


# ---------------------------------------------------------------------------
# HermesReviewer
# ---------------------------------------------------------------------------

class HermesReviewer:
    """HERMES standard-deviation anchor expert reviewer.

    Evaluates Pine candidate anchors against the original human-style anchor
    philosophy using a 5-step checklist. Returns a structured HermesVerdict.

    This class has NO chart-drawing authority. It only approves, vetoes, or
    abstains. The core anchor doctrine is frozen and cannot be changed here.
    """

    def review(
        self,
        candidate: dict[str, Any],
        screenshot_path: str | None = None,
    ) -> HermesVerdict:
        """Review a Pine candidate anchor and return a verdict.

        Args:
            candidate: Pine candidate payload dict. Expected fields:
                - anchor_id (str)
                - direction (str): "bullish" or "bearish"
                - anchor_low_price (float)
                - anchor_high_price (float)
                - range (float): anchor_high - anchor_low
                - pine_confidence_score (int 0-100)
                - pine_state (str): lifecycle state
                - timeframe_primary (str)
                - timeframe_context (str | None)
            screenshot_path: Path to decision-time screenshot, or None.

        Returns:
            HermesVerdict with verdict ("approve" | "veto" | "abstain"),
            reason codes, version, and timestamp.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # --- Abstain if metadata is critically incomplete ---
        if not self._has_required_fields(candidate):
            return HermesVerdict(
                verdict="abstain",
                reasons=[_RC_CANDIDATE_METADATA_INCOMPLETE],
                version=_HERMES_VERSION,
                timestamp=timestamp,
            )

        # --- Abstain if no screenshot and metadata alone is insufficient ---
        pine_score = candidate.get("pine_confidence_score", 0)
        if screenshot_path is None and pine_score < _APPROVAL_THRESHOLD:
            return HermesVerdict(
                verdict="abstain",
                reasons=[_RC_SCREENSHOT_INSUFFICIENT, _RC_CANDIDATE_METADATA_INCOMPLETE],
                version=_HERMES_VERSION,
                timestamp=timestamp,
            )

        # --- Rejection triggers (auto-veto regardless of checklist score) ---
        rejection_reasons = self._check_rejection_triggers(candidate)
        if rejection_reasons:
            return HermesVerdict(
                verdict="veto",
                reasons=rejection_reasons,
                version=_HERMES_VERSION,
                timestamp=timestamp,
            )

        # --- 5-step checklist scoring ---
        score, reasons = self._run_checklist(candidate, screenshot_path)

        if score >= _APPROVAL_THRESHOLD:
            reasons.append(_RC_CONFIDENCE_SUFFICIENT)
            return HermesVerdict(
                verdict="approve",
                reasons=reasons,
                version=_HERMES_VERSION,
                timestamp=timestamp,
            )
        else:
            reasons.append(_RC_CONFIDENCE_INSUFFICIENT)
            return HermesVerdict(
                verdict="veto",
                reasons=reasons,
                version=_HERMES_VERSION,
                timestamp=timestamp,
            )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _has_required_fields(self, candidate: dict[str, Any]) -> bool:
        """Check that the candidate has the minimum required fields."""
        required = {
            "anchor_id", "direction", "anchor_low_price",
            "anchor_high_price", "range", "pine_confidence_score", "pine_state",
        }
        return all(k in candidate and candidate[k] is not None for k in required)

    def _check_rejection_triggers(self, candidate: dict[str, Any]) -> list[str]:
        """Return reason codes for any auto-veto rejection triggers.

        Rejection triggers fire regardless of checklist score:
        - pine_confidence_score < 40 (clearly forced)
        - range < 0.5 (swing too small)
        - pine_state == "invalidated" (already invalid)
        """
        reasons: list[str] = []
        pine_score = candidate.get("pine_confidence_score", 0)
        range_val = candidate.get("range", 0.0)
        pine_state = candidate.get("pine_state", "")

        if pine_score < _MIN_CONFIDENCE_SCORE:
            reasons.append(_RC_CHOP_RISK_HIGH)
        if range_val < _MIN_RANGE:
            reasons.append(_RC_ANCHOR_ALIGNMENT_INVALID)
        if pine_state == "invalidated":
            reasons.append(_RC_STRUCTURE_UNCLEAR)

        return reasons

    def _run_checklist(
        self,
        candidate: dict[str, Any],
        screenshot_path: str | None,
    ) -> tuple[int, list[str]]:
        """Run the 5-step HERMES review checklist.

        Returns:
            (total_score, reason_codes_list)

        Checklist (from HERMES doctrine):
          Step 1: Opposite-direction swing clarity (0 or 25 pts)
          Step 2: Displacement strength (0 or 25 pts)
          Step 3: Structure break confirmation (0 or 20 pts)
          Step 4: Wick-to-wick anchor obviousness (0 or 15 pts)
          Step 5: HTF context agreement (0 or 15 pts)
        """
        score = 0
        reasons: list[str] = []

        pine_score = candidate.get("pine_confidence_score", 0)
        range_val = candidate.get("range", 0.0)
        timeframe_context = candidate.get("timeframe_context")

        # Step 1: Opposite-direction swing clarity (25 pts)
        # Proxy: pine_score >= 25 means the manipulation leg was scored as clean
        if pine_score >= 25:
            score += 25
            reasons.append(_RC_STRUCTURE_CLEAR)
        else:
            reasons.append(_RC_STRUCTURE_UNCLEAR)

        # Step 2: Displacement strength (25 pts)
        # Proxy: pine_score >= 50 means displacement was also scored as strong
        if pine_score >= 50:
            score += 25
            reasons.append(_RC_DISPLACEMENT_CONFIRMED)
        else:
            reasons.append(_RC_DISPLACEMENT_WEAK)

        # Step 3: Structure break confirmation (20 pts)
        # Proxy: pine_score >= 70 means structure break was confirmed
        if pine_score >= 70:
            score += 20
            reasons.append(_RC_STRUCTURE_CLEAR)

        # Step 4: Wick-to-wick anchor obviousness (15 pts)
        # Proxy: range >= 2.0 means the anchor span is visually obvious
        if range_val >= 2.0:
            score += 15
            reasons.append(_RC_ANCHOR_ALIGNMENT_VALID)
        else:
            reasons.append(_RC_ANCHOR_ALIGNMENT_INVALID)

        # Step 5: HTF context agreement (15 pts)
        # Proxy: timeframe_context is set (5m or 15m context was available)
        if timeframe_context:
            score += 15
            reasons.append(_RC_MTF_SUPPORT_PRESENT)
        else:
            reasons.append(_RC_MTF_SUPPORT_ABSENT)

        # Deduplicate reasons while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for r in reasons:
            if r not in seen:
                seen.add(r)
                deduped.append(r)

        return score, deduped


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def review_candidate(
    candidate: dict[str, Any],
    screenshot_path: str | None = None,
) -> HermesVerdict:
    """Convenience wrapper around HermesReviewer.review().

    Args:
        candidate: Pine candidate payload dict.
        screenshot_path: Path to decision-time screenshot, or None.

    Returns:
        HermesVerdict.
    """
    reviewer = HermesReviewer()
    return reviewer.review(candidate, screenshot_path)
