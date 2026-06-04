"""CalibrationManager — versioned calibration loop for HERMES SD Anchor AI.

Implements the continuous training/calibration review loop:
1. Collect resolved records (hermes_verdict + outcome_label both present).
2. Classify false approves, false vetoes, and ambiguous cases.
3. Produce a versioned CalibrationReport.
4. Gate promotion: new version must match or improve on baseline error rates.

The core anchor doctrine is FROZEN. Calibration refines judgment quality
(how HERMES applies checklist steps) without rewriting the rules.

Reports are saved to data/sd_anchor/calibration/{version_id}.json.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deep6.sd_anchor.label_store import LabelStore

# Outcome labels that count as "anchor worked" (target reached).
_SUCCESS_OUTCOMES = frozenset({
    "reached_minus2",
    "reached_minus2_5",
    "reached_minus4",
})

# Outcome label that counts as "anchor failed before any target".
_FAILURE_OUTCOME = "invalidated_before_target"


@dataclass(frozen=True)
class CalibrationReport:
    """Immutable summary of a single calibration pass.

    Attributes:
        version_id: HERMES skill version being evaluated (e.g. "1.0.0").
        reviewed_count: Total records with both hermes_verdict and outcome.
        false_approve_count: HERMES approved but outcome was invalidated.
        false_veto_count: HERMES vetoed but outcome reached a target.
        ambiguous_count: HERMES abstained or human override was used.
        promotion_eligible: Whether this report passes the promotion gate
            when compared against the baseline at creation time.
        timestamp: ISO 8601 timestamp of when the report was generated.
    """

    version_id: str
    reviewed_count: int
    false_approve_count: int
    false_veto_count: int
    ambiguous_count: int
    promotion_eligible: bool
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationReport:
        """Deserialize from a dict (loaded from JSON)."""
        return cls(
            version_id=d["version_id"],
            reviewed_count=d["reviewed_count"],
            false_approve_count=d["false_approve_count"],
            false_veto_count=d["false_veto_count"],
            ambiguous_count=d["ambiguous_count"],
            promotion_eligible=d["promotion_eligible"],
            timestamp=d["timestamp"],
        )


class CalibrationManager:
    """Versioned calibration loop for HERMES skill evaluation.

    Reads resolved records from LabelStore, classifies errors,
    and gates version promotion on error-rate parity.

    Args:
        reports_dir: Directory for persisting calibration reports.
            Defaults to ``data/sd_anchor/calibration``.
    """

    def __init__(
        self,
        reports_dir: str = "data/sd_anchor/calibration",
    ) -> None:
        self.reports_dir = Path(reports_dir)

    def run_calibration_pass(
        self,
        version_id: str,
        store: LabelStore,
    ) -> CalibrationReport:
        """Run a calibration pass over all resolved records.

        Scans the LabelStore for records where both ``hermes_verdict``
        and ``outcome_label`` are non-null, then classifies each as:
        - **false approve**: HERMES approved, outcome ``invalidated_before_target``
        - **false veto**: HERMES vetoed, outcome in success set (``reached_minus2`` or better)
        - **ambiguous**: HERMES abstained OR human override was used

        Args:
            version_id: HERMES skill version being evaluated.
            store: LabelStore instance to query.

        Returns:
            A CalibrationReport summarizing the pass.
        """
        records = self._query_resolved(store)

        false_approve = 0
        false_veto = 0
        ambiguous = 0

        for rec in records:
            verdict = rec["hermes_verdict"]
            outcome = rec["outcome_label"]
            human_override = rec["human_override"]

            # Ambiguous: abstain or human override used.
            if verdict == "abstain" or human_override:
                ambiguous += 1
                continue

            # False approve: approved but anchor failed.
            if verdict == "approve" and outcome == _FAILURE_OUTCOME:
                false_approve += 1
                continue

            # False veto: vetoed but anchor would have reached target.
            if verdict == "veto" and outcome in _SUCCESS_OUTCOMES:
                false_veto += 1
                continue

        baseline = self.load_baseline(self.reports_dir)
        promotion_eligible = (
            self.check_promotion_gate(
                CalibrationReport(
                    version_id=version_id,
                    reviewed_count=len(records),
                    false_approve_count=false_approve,
                    false_veto_count=false_veto,
                    ambiguous_count=ambiguous,
                    promotion_eligible=False,  # placeholder
                    timestamp="",
                ),
                baseline,
            )
            if baseline is not None
            else True  # No baseline = first version, auto-eligible.
        )

        return CalibrationReport(
            version_id=version_id,
            reviewed_count=len(records),
            false_approve_count=false_approve,
            false_veto_count=false_veto,
            ambiguous_count=ambiguous,
            promotion_eligible=promotion_eligible,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def check_promotion_gate(
        self,
        report: CalibrationReport,
        baseline_report: CalibrationReport | None,
    ) -> bool:
        """Check whether a new version passes the promotion gate.

        Gate logic: the new version must have false_approve_count <=
        baseline AND false_veto_count <= baseline. If no baseline
        exists, returns True (first version is auto-promoted).

        Args:
            report: The new version's calibration report.
            baseline_report: The prior version's report, or None.

        Returns:
            True if the new version may be promoted.
        """
        if baseline_report is None:
            return True

        return (
            report.false_approve_count <= baseline_report.false_approve_count
            and report.false_veto_count <= baseline_report.false_veto_count
        )

    def save_report(self, report: CalibrationReport, path: Path) -> None:
        """Save a calibration report as versioned JSON.

        Creates parent directories if needed. The file is written
        atomically (write to temp then rename not implemented here
        for simplicity — single-writer context).

        Args:
            report: The report to persist.
            path: Destination file path (e.g.
                ``data/sd_anchor/calibration/1.0.0.json``).
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def load_baseline(self, path: Path) -> CalibrationReport | None:
        """Load the most recent baseline report from a directory.

        Scans ``path`` for ``*.json`` files, sorts lexicographically
        (version strings sort correctly for semver with consistent
        digit counts), and returns the last one.

        Args:
            path: Directory containing versioned report JSON files.

        Returns:
            The most recent CalibrationReport, or None if no reports exist.
        """
        if not path.is_dir():
            return None

        report_files = sorted(path.glob("*.json"))
        if not report_files:
            return None

        latest = report_files[-1]
        data = json.loads(latest.read_text(encoding="utf-8"))
        return CalibrationReport.from_dict(data)

    def _query_resolved(self, store: LabelStore) -> list[dict[str, Any]]:
        """Query LabelStore for records with both verdict and outcome.

        Returns records where ``hermes_verdict IS NOT NULL``
        and ``outcome_label IS NOT NULL``.
        """
        conn = store._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM anchor_records
                WHERE hermes_verdict IS NOT NULL
                  AND outcome_label IS NOT NULL
                ORDER BY captured_at ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [store._row_to_dict(row) for row in rows]
