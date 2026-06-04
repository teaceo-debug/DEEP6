"""Pine-Sidecar Synchronization + Disagreement Handling.

Maps HERMES verdicts to Pine state transitions, detects disagreements
when Pine deterministic rules and HERMES conflict, and produces
chart-visible state change payloads for the Pine alert pipeline.

Contract references:
  - .sisyphus/contracts/hermes-authority.md (HERMES authority boundary)
  - .sisyphus/contracts/anchor-contract.md  (anchor state machine)

Key invariants:
  - Pine is the ONLY chart drawer. HERMES governs state but never draws.
  - Disagreements are always logged, never silent.
  - Human override always wins.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from deep6.sd_anchor.label_store import LabelStore
from deep6.sd_anchor.sidecar import HermesVerdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Pine confidence threshold for deterministic pass (anchor-contract.md)
_CONFIDENCE_THRESHOLD = 70

# Pine states that indicate deterministic rules passed
_DETERMINISTIC_PASS_STATES = frozenset({"confirmed", "active"})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SyncResult:
    """Result of applying a HERMES verdict to a Pine candidate.

    Attributes:
        anchor_id: Stable identifier for the anchor.
        pine_state_transition: Target Pine lifecycle state after verdict.
        chart_action: Pine chart-visible action to execute.
        disagreement: Whether Pine and HERMES disagree on this candidate.
        log_entry: Structured log dict for audit trail.
    """

    anchor_id: str
    pine_state_transition: str
    chart_action: str
    disagreement: bool
    log_entry: dict[str, Any]


# ---------------------------------------------------------------------------
# AnchorSyncManager
# ---------------------------------------------------------------------------

class AnchorSyncManager:
    """Maps HERMES verdicts to Pine state transitions with disagreement tracking.

    This is the handshake layer between the HERMES sidecar and Pine's
    chart-visible behavior. It:

      1. Receives a HERMES verdict for a candidate anchor.
      2. Determines the Pine state transition (active / invalidated / hold).
      3. Detects disagreements (Pine passed deterministic rules but HERMES vetoed).
      4. Logs every disagreement with full context — never silent.
      5. Produces Pine alert payloads for chart state updates.

    State transition rules (from the sync contract):

      - HERMES ``approve``  → Pine state ``active``; chart ``promote_to_active``
      - HERMES ``veto``     → Pine state ``invalidated``; chart ``mark_invalidated``
      - HERMES ``abstain``  → Pine state ``candidate`` (hold); chart ``hold_candidate``

    Disagreement definition (hermes-authority.md §Disagreement):

      - Type 1 (detected here): Pine confidence ≥ 70 in confirmed/active state,
        but HERMES returns ``veto``.
      - Type 2 (detected downstream): HERMES approves, but Pine later
        invalidates under deterministic lifecycle rules.
    """

    def __init__(self) -> None:
        self._disagreement_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_verdict(
        self,
        anchor_id: str,
        verdict: HermesVerdict,
        store: LabelStore,
    ) -> SyncResult:
        """Apply a HERMES verdict and determine the Pine state transition.

        Reads the candidate record from the store, resolves the transition,
        detects disagreements, writes the verdict to the store, and returns
        a ``SyncResult`` that Pine uses to update chart-visible state.

        Args:
            anchor_id: UUID of the candidate anchor to update.
            verdict: HERMES verdict (approve / veto / abstain).
            store: LabelStore containing the candidate record.

        Returns:
            SyncResult with transition, chart action, disagreement flag,
            and structured log entry.

        Raises:
            KeyError: If *anchor_id* is not found in the store.
        """
        record = store.get_record(anchor_id)

        pine_state, chart_action = self._resolve_transition(verdict)
        disagreement = self._detect_disagreement(record, verdict)

        log_entry = self._build_log_entry(
            anchor_id=anchor_id,
            record=record,
            verdict=verdict,
            pine_state=pine_state,
            chart_action=chart_action,
            disagreement=disagreement,
        )

        # Write verdict to store (write-once; skip gracefully if already set)
        try:
            store.write_hermes_verdict(
                anchor_id=anchor_id,
                hermes_verdict=verdict.verdict,
                hermes_reasons=verdict.reasons,
                hermes_version=verdict.version,
            )
        except Exception as exc:
            logger.warning(
                "sync.verdict_write_skipped anchor_id=%s reason=%s",
                anchor_id, exc,
            )

        if disagreement:
            self._log_disagreement(log_entry)

        logger.info(
            "sync.verdict_applied anchor_id=%s verdict=%s "
            "pine_state=%s chart_action=%s disagreement=%s",
            anchor_id,
            verdict.verdict,
            pine_state,
            chart_action,
            disagreement,
        )

        return SyncResult(
            anchor_id=anchor_id,
            pine_state_transition=pine_state,
            chart_action=chart_action,
            disagreement=disagreement,
            log_entry=log_entry,
        )

    @staticmethod
    def get_pine_alert_payload(sync_result: SyncResult) -> dict:
        """Produce the payload Pine needs to update its chart state.

        Schema::

            {
                "anchor_id": str,
                "action": "promote_active" | "mark_invalidated" | "hold_candidate",
                "reason": str
            }

        Args:
            sync_result: Result from :meth:`apply_verdict`.

        Returns:
            Dict consumable by Pine via alert webhook or polling.
        """
        action_map = {
            "promote_to_active": "promote_active",
            "mark_invalidated": "mark_invalidated",
            "hold_candidate": "hold_candidate",
        }
        action = action_map.get(sync_result.chart_action, sync_result.chart_action)

        reasons = sync_result.log_entry.get("hermes_reasons", [])
        reason_str = "; ".join(reasons) if reasons else "no reason provided"

        if sync_result.disagreement:
            reason_str = f"[DISAGREEMENT] {reason_str}"

        return {
            "anchor_id": sync_result.anchor_id,
            "action": action,
            "reason": reason_str,
        }

    @property
    def disagreement_log(self) -> list[dict[str, Any]]:
        """Read-only copy of the in-memory disagreement log."""
        return list(self._disagreement_log)

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_transition(verdict: HermesVerdict) -> tuple[str, str]:
        """Map a HERMES verdict to ``(pine_state, chart_action)``.

        Rules:
          - ``approve``  → ``("active", "promote_to_active")``
          - ``veto``     → ``("invalidated", "mark_invalidated")``
          - ``abstain``  → ``("candidate", "hold_candidate")``
        """
        if verdict.verdict == "approve":
            return "active", "promote_to_active"
        if verdict.verdict == "veto":
            return "invalidated", "mark_invalidated"
        return "candidate", "hold_candidate"

    @staticmethod
    def _detect_disagreement(
        record: dict[str, Any],
        verdict: HermesVerdict,
    ) -> bool:
        """Return True when Pine passed deterministic rules but HERMES vetoed.

        Disagreement per hermes-authority.md:
          Pine candidate in ``confirmed`` or ``active`` state with
          ``pine_confidence_score >= 70``, yet HERMES returned ``veto``.
        """
        if verdict.verdict != "veto":
            return False

        pine_state = record.get("pine_state", "")
        score = record.get("pine_confidence_score", 0)

        return (
            pine_state in _DETERMINISTIC_PASS_STATES
            and isinstance(score, (int, float))
            and score >= _CONFIDENCE_THRESHOLD
        )

    @staticmethod
    def _build_log_entry(
        *,
        anchor_id: str,
        record: dict[str, Any],
        verdict: HermesVerdict,
        pine_state: str,
        chart_action: str,
        disagreement: bool,
    ) -> dict[str, Any]:
        """Build a structured log entry for the sync event."""
        return {
            "anchor_id": anchor_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": record.get("symbol"),
            "timeframe": record.get("timeframe_primary"),
            "direction": record.get("direction"),
            "pine_state_before": record.get("pine_state"),
            "pine_confidence_score": record.get("pine_confidence_score"),
            "hermes_verdict": verdict.verdict,
            "hermes_reasons": list(verdict.reasons),
            "hermes_version": verdict.version,
            "pine_state_after": pine_state,
            "chart_action": chart_action,
            "disagreement": disagreement,
        }

    def _log_disagreement(self, log_entry: dict[str, Any]) -> None:
        """Log a disagreement with full context. Never silent per contract."""
        self._disagreement_log.append(log_entry)
        logger.warning(
            "sync.DISAGREEMENT anchor_id=%s pine_state=%s score=%s "
            "hermes_verdict=%s reasons=%s",
            log_entry["anchor_id"],
            log_entry["pine_state_before"],
            log_entry["pine_confidence_score"],
            log_entry["hermes_verdict"],
            log_entry["hermes_reasons"],
        )


__all__ = ["AnchorSyncManager", "SyncResult"]
