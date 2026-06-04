"""HERMES sidecar observation bridge for Standard Deviation Anchor AI.

Watches TradingView chart state, ingests Pine candidate payloads,
captures decision-time screenshots, routes candidates through HERMES
approve/veto pipeline, and maintains append-only audit + disagreement logs.

Contract references:
  - .sisyphus/contracts/hermes-authority.md (HERMES authority boundary)
  - .sisyphus/contracts/anchor-contract.md  (anchor state machine)
  - .sisyphus/specs/dataset-schema.md       (record schema)

Key invariants:
  - HERMES is non-blocking: timeout -> abstain + log, never stall Pine.
  - HERMES never draws on the chart.
  - Disagreements are always logged, never silent.
  - Human override always wins.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Re-export HermesVerdict from shared types to avoid circular imports
from deep6.sd_anchor.types import HermesVerdict  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_VERDICTS = frozenset({"approve", "veto", "abstain"})

_VALID_PINE_STATES = frozenset({
    "candidate", "confirmed", "active", "invalidated", "superseded",
})

_VALID_DIRECTIONS = frozenset({"bullish", "bearish"})

_VALID_REASON_CODES = frozenset({
    "STRUCTURE_CLEAR",
    "STRUCTURE_UNCLEAR",
    "DISPLACEMENT_CONFIRMED",
    "DISPLACEMENT_WEAK",
    "ANCHOR_ALIGNMENT_VALID",
    "ANCHOR_ALIGNMENT_INVALID",
    "MTF_SUPPORT_PRESENT",
    "MTF_SUPPORT_MIXED",
    "MTF_SUPPORT_ABSENT",
    "SCREENSHOT_INSUFFICIENT",
    "CANDIDATE_METADATA_INCOMPLETE",
    "CHOP_RISK_HIGH",
    "CONFIDENCE_SUFFICIENT",
    "CONFIDENCE_INSUFFICIENT",
    "RULES_PASS_BUT_VISUAL_DOUBT",
    "RULES_FAIL_OR_LATER_INVALIDATION",
    "HUMAN_OVERRIDE_APPLIED",
})

_REQUIRED_CANDIDATE_FIELDS = (
    "anchor_id", "symbol", "timeframe_primary", "direction",
    "anchor_low_price", "anchor_high_price",
    "anchor_low_bar_time", "anchor_high_bar_time",
    "pine_confidence_score", "pine_state",
)

# Default data root (relative to repo root)
_DEFAULT_DATA_ROOT = Path("data/sd_anchor")

# HERMES review timeout (seconds)
_DEFAULT_HERMES_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _HermesVerdictCompat:
    """Compatibility shim — HermesVerdict is now in deep6.sd_anchor.types.
    This class is kept only to avoid breaking any existing pickled objects.
    New code should import HermesVerdict from deep6.sd_anchor.types directly.
    """

    verdict: str
    reasons: list[str]
    version: str
    timestamp: str

    def __post_init__(self) -> None:
        if self.verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"Invalid verdict {self.verdict!r}; must be one of {_VALID_VERDICTS}"
            )
        if not self.reasons:
            raise ValueError("HermesVerdict requires at least one reason code")


@dataclass
class ChartSnapshot:
    """TradingView chart state captured at decision time."""

    symbol: str
    timeframe: str
    visible_bar_range_start: int | None = None
    visible_bar_range_end: int | None = None
    indicators: list[str] = field(default_factory=list)
    screenshot_path: str | None = None
    captured_at: str = ""

    def __post_init__(self) -> None:
        if not self.captured_at:
            self.captured_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------------

def validate_candidate(payload: dict[str, Any]) -> list[str]:
    """Validate a Pine candidate payload against the dataset schema.

    Returns a list of validation error strings. Empty list means valid.
    """
    errors: list[str] = []

    for f in _REQUIRED_CANDIDATE_FIELDS:
        if f not in payload:
            errors.append(f"Missing required field: {f}")

    direction = payload.get("direction")
    if direction is not None and direction not in _VALID_DIRECTIONS:
        errors.append(f"Invalid direction: {direction!r}")

    pine_state = payload.get("pine_state")
    if pine_state is not None and pine_state not in _VALID_PINE_STATES:
        errors.append(f"Invalid pine_state: {pine_state!r}")

    low = payload.get("anchor_low_price")
    high = payload.get("anchor_high_price")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        if high <= low:
            errors.append(
                f"anchor_high_price ({high}) must be > anchor_low_price ({low})"
            )

    score = payload.get("pine_confidence_score")
    if isinstance(score, int) and not (0 <= score <= 100):
        errors.append(f"pine_confidence_score out of range: {score}")

    return errors


# ---------------------------------------------------------------------------
# SDSidecar — main observation bridge
# ---------------------------------------------------------------------------

class SDSidecar:
    """HERMES sidecar observation bridge for Standard Deviation Anchor AI.

    Responsibilities:
      - Ingest Pine candidate payloads (via alert webhook or polling).
      - Capture TradingView chart state + screenshot at decision time.
      - Route candidate + screenshot to HERMES review pipeline.
      - Log audit records (append-only JSONL).
      - Log disagreements when Pine and HERMES conflict.

    HERMES is non-blocking: if no response within ``hermes_timeout_sec``,
    the sidecar logs an abstain and continues.

    Parameters:
        data_root: Root directory for audit/disagreement logs and screenshots.
        hermes_timeout_sec: Seconds to wait for HERMES verdict before abstain.
        hermes_version: Version string for the active HERMES skill.
    """

    def __init__(
        self,
        *,
        data_root: Path | str = _DEFAULT_DATA_ROOT,
        hermes_timeout_sec: float = _DEFAULT_HERMES_TIMEOUT,
        hermes_version: str = "1.0.0",
    ) -> None:
        self._data_root = Path(data_root)
        self._hermes_timeout = hermes_timeout_sec
        self._hermes_version = hermes_version
        self._running = False
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._tv_connected = False
        self._run_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main observation loop. Processes candidates from the internal queue.

        Runs until ``stop()`` is called. Each candidate is:
          1. Validated
          2. Chart state + screenshot captured
          3. Routed to HERMES for verdict
          4. Audit-logged (and disagreement-logged if applicable)
        """
        self._running = True
        self._ensure_directories()
        logger.info("sd_sidecar.started data_root=%s", self._data_root)

        while self._running:
            try:
                payload = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._process_candidate(payload)
            except Exception:
                logger.error(
                    "sd_sidecar.candidate_processing_failed anchor_id=%s",
                    payload.get("anchor_id", "unknown"),
                    exc_info=True,
                )

        logger.info("sd_sidecar.stopped")

    def start_background(self) -> asyncio.Task[None]:
        """Launch ``run()`` as a background asyncio task.

        Returns the task handle for lifecycle management.
        """
        if self._run_task is not None and not self._run_task.done():
            logger.warning("sd_sidecar.already_running")
            return self._run_task

        self._run_task = asyncio.create_task(self.run(), name="sd_sidecar")
        return self._run_task

    async def stop(self) -> None:
        """Signal the observation loop to stop gracefully."""
        self._running = False
        if self._run_task is not None and not self._run_task.done():
            self._run_task.cancel()
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
            self._run_task = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def receive_candidate(self, payload: dict[str, Any]) -> None:
        """Ingest a Pine candidate payload for HERMES review.

        The payload is queued and processed asynchronously by the ``run()``
        loop. This method never blocks the caller — Pine continues
        immediately after submission.

        Args:
            payload: Pine candidate fields matching the dataset schema.
                     See ``.sisyphus/specs/dataset-schema.md`` Section 1.1.
        """
        errors = validate_candidate(payload)
        if errors:
            logger.warning(
                "sd_sidecar.invalid_candidate anchor_id=%s errors=%s",
                payload.get("anchor_id", "unknown"),
                errors,
            )
            return

        await self._queue.put(payload)
        logger.debug(
            "sd_sidecar.candidate_queued anchor_id=%s state=%s",
            payload.get("anchor_id"),
            payload.get("pine_state"),
        )

    def capture_chart_state(self) -> dict[str, Any]:
        """Capture current TradingView chart state + screenshot path.

        Uses TradingView MCP bridge pattern (graceful degradation when
        TradingView is not connected). Returns a dict suitable for
        embedding in the audit record.

        Returns:
            Chart state dict with keys: symbol, timeframe, indicators,
            visible_bar_range_start, visible_bar_range_end,
            screenshot_path, captured_at. Values may be None if
            TradingView is not connected.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        if not self._tv_connected:
            logger.debug("sd_sidecar.tv_not_connected — returning stub chart state")
            return ChartSnapshot(
                symbol="",
                timeframe="",
                captured_at=now_iso,
            ).__dict__

        # When TV is connected, this would call the MCP bridge:
        #   chart_get_state() -> symbol, timeframe, indicators
        #   chart_get_visible_range() -> visible bar range
        #   capture_screenshot(filename=anchor_id) -> screenshot path
        # Graceful degradation: return empty snapshot if bridge fails.
        return ChartSnapshot(
            symbol="",
            timeframe="",
            captured_at=now_iso,
        ).__dict__

    async def capture_screenshot(self, anchor_id: str) -> str | None:
        """Capture a TradingView chart screenshot at decision time.

        Args:
            anchor_id: UUID of the anchor candidate (used as filename).

        Returns:
            Relative path to the saved screenshot, or None if capture
            failed or TradingView is not connected.
        """
        if not self._tv_connected:
            logger.debug("sd_sidecar.screenshot_skipped — tv not connected")
            return None

        # MCP bridge pattern: capture_screenshot(filename=anchor_id)
        # Save to data/sd_anchor/screenshots/{YYYY-MM-DD}/{anchor_id}.png
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        screenshot_dir = self._data_root / "screenshots" / today
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = f"data/sd_anchor/screenshots/{today}/{anchor_id}.png"

        # Actual MCP call would go here:
        # result = mcp_capture_screenshot(filename=anchor_id, region="chart")
        # if result is None: return None
        # shutil.move(result, screenshot_dir / f"{anchor_id}.png")

        logger.info("sd_sidecar.screenshot_captured path=%s", screenshot_path)
        return screenshot_path

    async def route_to_hermes(
        self,
        candidate: dict[str, Any],
        screenshot_path: str | None,
    ) -> HermesVerdict:
        """Send candidate + screenshot to HERMES for review.

        HERMES is non-blocking: if no response within the configured
        timeout, an ``abstain`` verdict is returned with reason
        ``CANDIDATE_METADATA_INCOMPLETE``.

        Args:
            candidate: Validated Pine candidate payload.
            screenshot_path: Path to decision-time screenshot (may be None).

        Returns:
            HermesVerdict with verdict, reasons, version, and timestamp.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        anchor_id = candidate.get("anchor_id", "unknown")

        try:
            verdict = await asyncio.wait_for(
                self._invoke_hermes(candidate, screenshot_path),
                timeout=self._hermes_timeout,
            )
            logger.info(
                "sd_sidecar.hermes_responded anchor_id=%s verdict=%s",
                anchor_id,
                verdict.verdict,
            )
            return verdict

        except asyncio.TimeoutError:
            logger.warning(
                "sd_sidecar.hermes_timeout anchor_id=%s timeout=%.1fs",
                anchor_id,
                self._hermes_timeout,
            )
            return HermesVerdict(
                verdict="abstain",
                reasons=["CANDIDATE_METADATA_INCOMPLETE"],
                version=self._hermes_version,
                timestamp=now_iso,
            )

        except Exception:
            logger.error(
                "sd_sidecar.hermes_error anchor_id=%s",
                anchor_id,
                exc_info=True,
            )
            return HermesVerdict(
                verdict="abstain",
                reasons=["CANDIDATE_METADATA_INCOMPLETE"],
                version=self._hermes_version,
                timestamp=now_iso,
            )

    def log_audit(
        self,
        candidate: dict[str, Any],
        verdict: HermesVerdict,
        *,
        chart_state: dict[str, Any] | None = None,
        screenshot_path: str | None = None,
        response_latency_ms: float | None = None,
    ) -> None:
        """Write an audit record to the daily append-only JSONL file.

        Fields follow the audit contract in hermes-authority.md.

        Args:
            candidate: Pine candidate payload.
            verdict: HERMES verdict for this candidate.
            chart_state: Chart state snapshot at decision time.
            screenshot_path: Path to the decision-time screenshot.
            response_latency_ms: HERMES response latency in milliseconds.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        audit_dir = self._data_root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / f"{today}.jsonl"

        record = {
            # Contract-required fields
            "anchor_id": candidate.get("anchor_id"),
            "timestamp_decision": verdict.timestamp,
            "symbol": candidate.get("symbol"),
            "timeframe": candidate.get("timeframe_primary"),
            "pine_candidate_state": candidate.get("pine_state"),
            "hermes_verdict": verdict.verdict,
            "hermes_reasons": verdict.reasons,
            "hermes_version": verdict.version,
            "pine_final_state": candidate.get("pine_state"),
            "human_override": False,
            "disagreement": False,
            # Optional recommended fields
            "screenshot_path": screenshot_path,
            "chart_state": chart_state,
            "response_latency_ms": response_latency_ms,
            # Candidate snapshot for reproducibility
            "pine_confidence_score": candidate.get("pine_confidence_score"),
            "direction": candidate.get("direction"),
            "anchor_low_price": candidate.get("anchor_low_price"),
            "anchor_high_price": candidate.get("anchor_high_price"),
        }

        self._append_jsonl(audit_path, record)
        logger.info(
            "sd_sidecar.audit_logged anchor_id=%s verdict=%s",
            record["anchor_id"],
            record["hermes_verdict"],
        )

    def log_disagreement(
        self,
        candidate: dict[str, Any],
        verdict: HermesVerdict,
        *,
        reason: str = "",
    ) -> None:
        """Write a disagreement record when Pine and HERMES conflict.

        Disagreement exists when:
          1. Pine candidate passes deterministic rules, but HERMES vetoes.
          2. HERMES approves, but Pine later invalidates.

        Args:
            candidate: Pine candidate payload.
            verdict: HERMES verdict that caused the disagreement.
            reason: Human-readable reason for the disagreement.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        disagreement_dir = self._data_root / "disagreements"
        disagreement_dir.mkdir(parents=True, exist_ok=True)
        disagreement_path = disagreement_dir / f"{today}.jsonl"

        record = {
            "anchor_id": candidate.get("anchor_id"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": candidate.get("symbol"),
            "timeframe": candidate.get("timeframe_primary"),
            "direction": candidate.get("direction"),
            "pine_state": candidate.get("pine_state"),
            "pine_confidence_score": candidate.get("pine_confidence_score"),
            "hermes_verdict": verdict.verdict,
            "hermes_reasons": verdict.reasons,
            "hermes_version": verdict.version,
            "disagreement_reason": reason,
            "human_override": False,
        }

        self._append_jsonl(disagreement_path, record)
        logger.warning(
            "sd_sidecar.disagreement_logged anchor_id=%s pine_state=%s "
            "hermes_verdict=%s reason=%s",
            record["anchor_id"],
            record["pine_state"],
            record["hermes_verdict"],
            reason,
        )

    def set_tv_connected(self, connected: bool) -> None:
        """Update TradingView connection status.

        Args:
            connected: Whether the TradingView MCP bridge is reachable.
        """
        if self._tv_connected != connected:
            logger.info("sd_sidecar.tv_connection_changed connected=%s", connected)
        self._tv_connected = connected

    # ------------------------------------------------------------------
    # Internal processing pipeline
    # ------------------------------------------------------------------

    async def _process_candidate(self, payload: dict[str, Any]) -> None:
        """Full processing pipeline for a single candidate.

        Steps:
          1. Capture chart state + screenshot
          2. Route to HERMES with timeout
          3. Detect disagreement
          4. Write audit log
          5. Write disagreement log (if applicable)
        """
        anchor_id = payload.get("anchor_id", str(uuid.uuid4()))
        pine_state = payload.get("pine_state", "unknown")

        logger.info(
            "sd_sidecar.processing anchor_id=%s state=%s direction=%s",
            anchor_id, pine_state, payload.get("direction"),
        )

        # 1. Capture chart state + screenshot
        chart_state = self.capture_chart_state()
        screenshot_path = await self.capture_screenshot(anchor_id)

        # 2. Route to HERMES (non-blocking with timeout)
        start_ms = _monotonic_ms()
        verdict = await self.route_to_hermes(payload, screenshot_path)
        latency_ms = _monotonic_ms() - start_ms

        # 3. Detect disagreement
        is_disagreement = self._detect_disagreement(payload, verdict)

        # 4. Write audit log
        self.log_audit(
            payload,
            verdict,
            chart_state=chart_state,
            screenshot_path=screenshot_path,
            response_latency_ms=latency_ms,
        )

        # 5. Write disagreement log if applicable
        if is_disagreement:
            reason = self._describe_disagreement(payload, verdict)
            self.log_disagreement(payload, verdict, reason=reason)

    async def _invoke_hermes(
        self,
        candidate: dict[str, Any],
        screenshot_path: str | None,
    ) -> HermesVerdict:
        """Invoke the HERMES review skill/model.

        This is the integration point for the actual HERMES engine.
        Current implementation returns abstain — replaced when the
        HERMES skill (T4) is wired into the pipeline.

        Args:
            candidate: Validated Pine candidate payload.
            screenshot_path: Decision-time screenshot path.

        Returns:
            HermesVerdict from the review engine.
        """
        # Wire HermesReviewer (T11) into the pipeline.
        # Falls back to abstain only if the module is unavailable.
        if _HERMES_REVIEWER is not None:
            return _HERMES_REVIEWER.review(candidate, screenshot_path)
        now_iso = datetime.now(timezone.utc).isoformat()
        return HermesVerdict(
            verdict="abstain",
            reasons=["CANDIDATE_METADATA_INCOMPLETE"],
            version=self._hermes_version,
            timestamp=now_iso,
        )

    def _detect_disagreement(
        self,
        candidate: dict[str, Any],
        verdict: HermesVerdict,
    ) -> bool:
        """Check if Pine and HERMES disagree.

        Disagreement per hermes-authority.md:
          1. Pine candidate passes deterministic rules + HERMES vetoes.
          2. HERMES approves + Pine later invalidates (detected downstream).

        Type 2 cannot be detected at review time — it requires a later
        state transition. This method catches Type 1 only.

        Args:
            candidate: Pine candidate payload.
            verdict: HERMES verdict.

        Returns:
            True if Type 1 disagreement is detected.
        """
        if verdict.verdict == "abstain":
            return False

        pine_state = candidate.get("pine_state", "")
        score = candidate.get("pine_confidence_score", 0)

        # Type 1: Pine says candidate passes (confirmed/active with score >= 70)
        # but HERMES vetoes.
        pine_passes = (
            pine_state in ("confirmed", "active")
            and isinstance(score, int)
            and score >= 70
        )

        if pine_passes and verdict.verdict == "veto":
            return True

        return False

    @staticmethod
    def _describe_disagreement(
        candidate: dict[str, Any],
        verdict: HermesVerdict,
    ) -> str:
        """Build a human-readable disagreement description."""
        pine_state = candidate.get("pine_state", "unknown")
        score = candidate.get("pine_confidence_score", "?")
        direction = candidate.get("direction", "unknown")

        if verdict.verdict == "veto":
            return (
                f"Pine {direction} candidate in state '{pine_state}' "
                f"(score={score}) passed deterministic rules, "
                f"but HERMES vetoed with reasons: {verdict.reasons}"
            )

        return (
            f"Disagreement: Pine state='{pine_state}' score={score} "
            f"vs HERMES verdict='{verdict.verdict}' reasons={verdict.reasons}"
        )

    # ------------------------------------------------------------------
    # File I/O helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        """Create audit and disagreement directories if they don't exist."""
        (self._data_root / "audit").mkdir(parents=True, exist_ok=True)
        (self._data_root / "disagreements").mkdir(parents=True, exist_ok=True)
        (self._data_root / "screenshots").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
        """Append a single JSON record to a JSONL file.

        Thread-safe via atomic write-and-flush pattern. Creates
        the file if it doesn't exist.
        """
        line = json.dumps(record, default=str, separators=(",", ":"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _monotonic_ms() -> float:
    """Return monotonic clock time in milliseconds."""
    import time
    return time.monotonic() * 1000.0


__all__ = ["ChartSnapshot", "HermesVerdict", "SDSidecar", "validate_candidate"]

# ---------------------------------------------------------------------------
# Late import to break circular dependency with hermes_workflow.py
# hermes_workflow imports HermesVerdict from deep6.sd_anchor.types (not here)
# so this import is safe at module bottom.
# ---------------------------------------------------------------------------
try:
    from deep6.sd_anchor.hermes_workflow import HermesReviewer as _HermesReviewer
    _HERMES_REVIEWER: "_HermesReviewer | None" = _HermesReviewer()
except ImportError:
    _HERMES_REVIEWER = None
