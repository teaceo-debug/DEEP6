"""LabelStore — SQLite persistence for SD Anchor labeling/review workflow.

Implements strict decision-time/outcome-time separation per dataset-schema.md.
Decision-time fields are immutable after capture. HERMES and outcome fields
are write-once (null -> value). Human override is always mutable.

Schema version: 1.0.0 (matches .sisyphus/specs/dataset-schema.md).

Uses synchronous sqlite3 — this is a labeling/review path, not the hot
signal pipeline. All writes are atomic (single transaction per method).
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Valid enum values (from dataset-schema.md)
# ---------------------------------------------------------------------------
_VALID_DIRECTIONS = frozenset({"bullish", "bearish"})
_VALID_PINE_STATES = frozenset({
    "candidate", "confirmed", "active", "invalidated", "superseded",
})
_VALID_HERMES_VERDICTS = frozenset({"approve", "veto", "abstain"})
_VALID_OUTCOME_LABELS = frozenset({
    "reached_minus2",
    "reached_minus2_5",
    "reached_minus4",
    "invalidated_before_target",
    "pending",
})

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS anchor_records (
    anchor_id              TEXT PRIMARY KEY,
    captured_at            TEXT    NOT NULL,
    symbol                 TEXT    NOT NULL,
    timeframe_primary      TEXT    NOT NULL,
    timeframe_context      TEXT,
    direction              TEXT    NOT NULL,
    anchor_low_price       REAL    NOT NULL,
    anchor_high_price      REAL    NOT NULL,
    anchor_low_bar_time    INTEGER NOT NULL,
    anchor_high_bar_time   INTEGER NOT NULL,
    range_val              REAL    NOT NULL,
    level_minus2           REAL    NOT NULL,
    level_minus2_5         REAL    NOT NULL,
    level_minus4           REAL    NOT NULL,
    pine_confidence_score  INTEGER NOT NULL,
    pine_state             TEXT    NOT NULL,
    screenshot_path        TEXT,
    chart_metadata         TEXT    NOT NULL,

    hermes_verdict         TEXT,
    hermes_reasons         TEXT,
    hermes_version         TEXT,

    human_override         INTEGER NOT NULL DEFAULT 0,
    human_override_reason  TEXT,

    outcome_label          TEXT,
    outcome_resolved_at    TEXT,

    inserted_at            REAL    NOT NULL
);
"""


class LabelStoreError(Exception):
    """Base exception for LabelStore violations."""


class ImmutabilityError(LabelStoreError):
    """Raised when attempting to overwrite an immutable or write-once field."""


class ValidationError(LabelStoreError):
    """Raised when a record fails schema validation."""


class LabelStore:
    """SQLite-backed store for SD Anchor labeling records.

    Enforces the immutability contract from dataset-schema.md:
    - Decision-time fields: immutable after create_record()
    - HERMES fields: write-once (null -> value)
    - Outcome fields: write-once (null -> value)
    - Human override: always mutable

    Args:
        db_path: Path to SQLite database file. Parent directories are
            created automatically. Defaults to ``data/sd_anchor/label_store.db``.
        repo_root: Repository root for resolving relative screenshot paths
            in scan_orphans(). Defaults to current working directory.
    """

    def __init__(
        self,
        db_path: str = "data/sd_anchor/label_store.db",
        repo_root: str | None = None,
    ) -> None:
        self.db_path = db_path
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()

        # Ensure parent directory exists (skip for :memory: test DBs).
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with row_factory set to sqlite3.Row."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        """Create the anchor_records table if it does not exist."""
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_record(
        self,
        anchor_id: str,
        captured_at: str,
        symbol: str,
        timeframe_primary: str,
        timeframe_context: str | None,
        direction: str,
        anchor_low_price: float,
        anchor_high_price: float,
        anchor_low_bar_time: int,
        anchor_high_bar_time: int,
        range_val: float,
        level_minus2: float,
        level_minus2_5: float,
        level_minus4: float,
        pine_confidence_score: int,
        pine_state: str,
        screenshot_path: str,
        chart_metadata: dict[str, Any],
    ) -> str:
        """Create an immutable decision-time record.

        All outcome and HERMES fields are initialized to null. The record
        cannot be modified after creation (decision-time immutability).

        Args:
            anchor_id: UUID v4 string identifying this anchor instance.
            captured_at: ISO 8601 timestamp of capture (decision time).
            symbol: Instrument symbol (e.g. ``"NQ1!"``).
            timeframe_primary: Primary chart timeframe (e.g. ``"1"``).
            timeframe_context: Higher timeframe for context, or None.
            direction: ``"bullish"`` or ``"bearish"``.
            anchor_low_price: Low wick price of the anchor leg.
            anchor_high_price: High wick price of the anchor leg.
            anchor_low_bar_time: Unix seconds of the anchor low bar.
            anchor_high_bar_time: Unix seconds of the anchor high bar.
            range_val: ``anchor_high_price - anchor_low_price`` (positive).
            level_minus2: -2 SD projection from anchor.
            level_minus2_5: -2.5 SD projection from anchor.
            level_minus4: -4 SD projection from anchor.
            pine_confidence_score: 0-100 deterministic confidence.
            pine_state: Lifecycle state at capture.
            screenshot_path: Relative path from repo root to PNG.
            chart_metadata: Chart presentation state dict.

        Returns:
            The ``anchor_id`` of the created record.

        Raises:
            ValidationError: If any field fails schema validation.
        """
        self._validate_decision_fields(
            anchor_id=anchor_id,
            direction=direction,
            anchor_low_price=anchor_low_price,
            anchor_high_price=anchor_high_price,
            range_val=range_val,
            level_minus2=level_minus2,
            level_minus2_5=level_minus2_5,
            level_minus4=level_minus4,
            pine_confidence_score=pine_confidence_score,
            pine_state=pine_state,
        )

        import time
        now = time.time()

        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO anchor_records (
                    anchor_id, captured_at, symbol, timeframe_primary,
                    timeframe_context, direction, anchor_low_price,
                    anchor_high_price, anchor_low_bar_time,
                    anchor_high_bar_time, range_val, level_minus2,
                    level_minus2_5, level_minus4, pine_confidence_score,
                    pine_state, screenshot_path, chart_metadata,
                    hermes_verdict, hermes_reasons, hermes_version,
                    human_override, human_override_reason,
                    outcome_label, outcome_resolved_at,
                    inserted_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    NULL, NULL, NULL,
                    0, NULL,
                    NULL, NULL,
                    ?
                )
                """,
                (
                    anchor_id,
                    captured_at,
                    symbol,
                    timeframe_primary,
                    timeframe_context,
                    direction,
                    anchor_low_price,
                    anchor_high_price,
                    anchor_low_bar_time,
                    anchor_high_bar_time,
                    range_val,
                    level_minus2,
                    level_minus2_5,
                    level_minus4,
                    pine_confidence_score,
                    pine_state,
                    screenshot_path,
                    json.dumps(chart_metadata),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return anchor_id

    def write_hermes_verdict(
        self,
        anchor_id: str,
        hermes_verdict: str,
        hermes_reasons: list[str],
        hermes_version: str,
    ) -> None:
        """Write HERMES validation fields. Write-once: raises if already set.

        Args:
            anchor_id: Target record.
            hermes_verdict: ``"approve"``, ``"veto"``, or ``"abstain"``.
            hermes_reasons: List of human-readable reason strings.
            hermes_version: Version identifier of the HERMES model/skill.

        Raises:
            ImmutabilityError: If hermes_verdict is already non-null.
            KeyError: If anchor_id does not exist.
            ValidationError: If verdict is not a valid enum value.
        """
        if hermes_verdict not in _VALID_HERMES_VERDICTS:
            raise ValidationError(
                f"hermes_verdict must be one of {sorted(_VALID_HERMES_VERDICTS)}, "
                f"got {hermes_verdict!r}"
            )

        record = self._get_row(anchor_id)
        if record["hermes_verdict"] is not None:
            raise ImmutabilityError(
                f"hermes_verdict already set for {anchor_id}: "
                f"{record['hermes_verdict']!r}"
            )

        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE anchor_records
                SET hermes_verdict = ?, hermes_reasons = ?, hermes_version = ?
                WHERE anchor_id = ?
                """,
                (
                    hermes_verdict,
                    json.dumps(hermes_reasons),
                    hermes_version,
                    anchor_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def write_human_override(self, anchor_id: str, reason: str) -> None:
        """Write human override. Always allowed (mutable field).

        Sets ``human_override = True`` and records the reason.

        Args:
            anchor_id: Target record.
            reason: Free-text reason for the override.

        Raises:
            KeyError: If anchor_id does not exist.
        """
        self._get_row(anchor_id)  # Existence check.

        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE anchor_records
                SET human_override = 1, human_override_reason = ?
                WHERE anchor_id = ?
                """,
                (reason, anchor_id),
            )
            conn.commit()
        finally:
            conn.close()

    def write_outcome(
        self,
        anchor_id: str,
        outcome_label: str,
        outcome_resolved_at: str,
    ) -> None:
        """Write outcome fields. Write-once: raises if outcome_label already set.

        Args:
            anchor_id: Target record.
            outcome_label: One of ``"reached_minus2"``, ``"reached_minus2_5"``,
                ``"reached_minus4"``, ``"invalidated_before_target"``, ``"pending"``.
            outcome_resolved_at: ISO 8601 timestamp of resolution.

        Raises:
            ImmutabilityError: If outcome_label is already non-null.
            KeyError: If anchor_id does not exist.
            ValidationError: If outcome_label is not a valid enum value.
        """
        if outcome_label not in _VALID_OUTCOME_LABELS:
            raise ValidationError(
                f"outcome_label must be one of {sorted(_VALID_OUTCOME_LABELS)}, "
                f"got {outcome_label!r}"
            )

        record = self._get_row(anchor_id)
        if record["outcome_label"] is not None:
            raise ImmutabilityError(
                f"outcome_label already set for {anchor_id}: "
                f"{record['outcome_label']!r}"
            )

        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE anchor_records
                SET outcome_label = ?, outcome_resolved_at = ?
                WHERE anchor_id = ?
                """,
                (outcome_label, outcome_resolved_at, anchor_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_record(self, anchor_id: str) -> dict[str, Any]:
        """Return the full record as a dict.

        The ``chart_metadata`` and ``hermes_reasons`` fields are deserialized
        from their JSON storage format.

        Args:
            anchor_id: Target record.

        Returns:
            Dict with all schema fields.

        Raises:
            KeyError: If anchor_id does not exist.
        """
        row = self._get_row(anchor_id)
        return self._row_to_dict(row)

    def query_pending_hermes(self) -> list[dict[str, Any]]:
        """Return records where hermes_verdict is null.

        These are records awaiting HERMES evaluation.

        Returns:
            List of record dicts ordered by captured_at ASC.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM anchor_records
                WHERE hermes_verdict IS NULL
                ORDER BY captured_at ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_dict(row) for row in rows]

    def query_pending_outcome(self) -> list[dict[str, Any]]:
        """Return records where outcome_label is null or ``"pending"``.

        These are records awaiting outcome resolution.

        Returns:
            List of record dicts ordered by captured_at ASC.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT * FROM anchor_records
                WHERE outcome_label IS NULL OR outcome_label = 'pending'
                ORDER BY captured_at ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        return [self._row_to_dict(row) for row in rows]

    def scan_orphans(self) -> list[str]:
        """Return anchor_ids where screenshot is missing.

        An orphan is a record where ``screenshot_path`` is null or the
        referenced file does not exist on disk (resolved relative to
        ``repo_root``).

        Returns:
            List of orphan anchor_id strings.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT anchor_id, screenshot_path FROM anchor_records"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        orphans: list[str] = []
        for row in rows:
            path = row["screenshot_path"]
            if path is None:
                orphans.append(row["anchor_id"])
                continue
            full_path = self.repo_root / path
            if not full_path.exists():
                orphans.append(row["anchor_id"])

        return orphans

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_row(self, anchor_id: str) -> sqlite3.Row:
        """Fetch a single row or raise KeyError."""
        conn = self._connect()
        try:
            cursor = conn.execute(
                "SELECT * FROM anchor_records WHERE anchor_id = ?",
                (anchor_id,),
            )
            row = cursor.fetchone()
        finally:
            conn.close()

        if row is None:
            raise KeyError(f"No record found for anchor_id={anchor_id!r}")
        return row

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert a sqlite3.Row to a dict with JSON fields deserialized."""
        d = dict(row)

        # Deserialize JSON-stored fields.
        if d.get("chart_metadata") is not None:
            d["chart_metadata"] = json.loads(d["chart_metadata"])
        if d.get("hermes_reasons") is not None:
            d["hermes_reasons"] = json.loads(d["hermes_reasons"])
        else:
            d["hermes_reasons"] = []

        # Normalize human_override to bool.
        d["human_override"] = bool(d.get("human_override", 0))

        return d

    def _validate_decision_fields(
        self,
        *,
        anchor_id: str,
        direction: str,
        anchor_low_price: float,
        anchor_high_price: float,
        range_val: float,
        level_minus2: float,
        level_minus2_5: float,
        level_minus4: float,
        pine_confidence_score: int,
        pine_state: str,
    ) -> None:
        """Validate decision-time fields per dataset-schema.md Section 5."""
        # UUID v4 format check.
        try:
            parsed = uuid.UUID(anchor_id, version=4)
            if str(parsed) != anchor_id.lower():
                raise ValueError
        except (ValueError, AttributeError):
            raise ValidationError(
                f"anchor_id must be a valid UUID v4, got {anchor_id!r}"
            )

        if direction not in _VALID_DIRECTIONS:
            raise ValidationError(
                f"direction must be one of {sorted(_VALID_DIRECTIONS)}, "
                f"got {direction!r}"
            )

        if pine_state not in _VALID_PINE_STATES:
            raise ValidationError(
                f"pine_state must be one of {sorted(_VALID_PINE_STATES)}, "
                f"got {pine_state!r}"
            )

        if not (0 <= pine_confidence_score <= 100):
            raise ValidationError(
                f"pine_confidence_score must be 0-100, got {pine_confidence_score}"
            )

        if anchor_high_price <= anchor_low_price:
            raise ValidationError(
                f"anchor_high_price ({anchor_high_price}) must be > "
                f"anchor_low_price ({anchor_low_price})"
            )

        expected_range = anchor_high_price - anchor_low_price
        if abs(range_val - expected_range) > 1e-6:
            raise ValidationError(
                f"range_val ({range_val}) does not match computed range "
                f"({expected_range})"
            )

        # Level ordering per schema Section 5.2.
        if direction == "bullish":
            if not (level_minus4 < level_minus2_5 < level_minus2 < anchor_low_price):
                raise ValidationError(
                    f"Bullish level ordering violated: "
                    f"level_minus4 ({level_minus4}) < level_minus2_5 ({level_minus2_5}) "
                    f"< level_minus2 ({level_minus2}) < anchor_low_price ({anchor_low_price})"
                )
        else:  # bearish
            if not (anchor_high_price < level_minus2 < level_minus2_5 < level_minus4):
                raise ValidationError(
                    f"Bearish level ordering violated: "
                    f"anchor_high_price ({anchor_high_price}) < level_minus2 ({level_minus2}) "
                    f"< level_minus2_5 ({level_minus2_5}) < level_minus4 ({level_minus4})"
                )
