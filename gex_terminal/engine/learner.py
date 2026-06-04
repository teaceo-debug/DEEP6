"""Daily session learning manager — saves GEX session outcomes and recalls patterns for Claude."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_LEARNINGS_DIR = Path.home() / ".deep6" / "gex_learnings"
_MAX_RECALL_SESSIONS = 5
_SKILL_FILE = (
    Path(__file__).parent.parent.parent / ".claude" / "skills" / "gex-doctor-learnings" / "knowledge.md"
)


class SessionLearner:
    """Records GEX analysis outcomes per trading session and recalls patterns for Claude."""

    def __init__(self) -> None:
        _LEARNINGS_DIR.mkdir(parents=True, exist_ok=True)
        self._today = self._get_trading_date()
        self._session_events: list[dict[str, Any]] = []
        self._recalled_context: str = ""
        self._recall_done = False

    def record_cycle(
        self,
        *,
        timestamp: float,
        bias_direction: str,
        confidence: int,
        conviction_grade: str,
        regime: str,
        gamma_flip: Optional[float],
        call_wall: Optional[float],
        put_wall: Optional[float],
        hmm_state: str = "UNKNOWN",
        flow_direction: str = "neutral",
    ) -> None:
        """Record a single analysis cycle for potential end-of-session saving."""
        self._session_events.append(
            {
                "ts": timestamp,
                "bias": bias_direction,
                "confidence": confidence,
                "conviction": conviction_grade,
                "regime": regime,
                "levels": {
                    "gamma_flip": gamma_flip,
                    "call_wall": call_wall,
                    "put_wall": put_wall,
                },
                "hmm": hmm_state,
                "flow": flow_direction,
                "actual_outcome": "unknown",
            }
        )
        if len(self._session_events) > 50:
            self._session_events = self._session_events[-50:]

    def save_session(self, notes: str = "", actual_outcome: str = "unknown") -> None:
        """Save today's session summary to disk."""
        if not self._session_events:
            return

        date_str = self._get_trading_date()
        out_path = _LEARNINGS_DIR / f"{date_str}.json"
        summary = {
            "date": date_str,
            "saved_at": time.time(),
            "total_cycles": len(self._session_events),
            "dominant_bias": self._dominant(self._session_events, "bias"),
            "avg_confidence": int(sum(e["confidence"] for e in self._session_events) / len(self._session_events)),
            "dominant_regime": self._dominant(self._session_events, "regime"),
            "dominant_hmm": self._dominant(self._session_events, "hmm"),
            "conviction_grades": [e["conviction"] for e in self._session_events],
            "actual_outcome": actual_outcome,
            "notes": notes,
            "events": self._session_events[-10:],
        }
        try:
            with out_path.open("w", encoding="utf-8") as handle:
                json.dump(summary, handle, indent=2)
            logger.info("Session learning saved: %s", out_path)
            self._update_skill_file(summary)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to save session learning: %s", exc)

    def get_recall_context(self) -> str:
        """Load last N sessions and format as Claude context string."""
        if self._recall_done:
            return self._recalled_context
        self._recalled_context = self._build_recall_context()
        self._recall_done = True
        return self._recalled_context

    def _build_recall_context(self) -> str:
        session_files = sorted(_LEARNINGS_DIR.glob("*.json"), reverse=True)[:_MAX_RECALL_SESSIONS]
        if not session_files:
            return ""

        lines = ["<recent_session_learnings>"]
        for path in session_files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                lines.append(
                    f"Date {data.get('date', '?')}: "
                    f"bias={data.get('dominant_bias', '?')} "
                    f"avg_conf={data.get('avg_confidence', '?')}% "
                    f"regime={data.get('dominant_regime', '?')} "
                    f"hmm={data.get('dominant_hmm', '?')} "
                    f"outcome={data.get('actual_outcome', 'unknown')} "
                    f"notes={data.get('notes', '')}"
                )
            except Exception:  # pragma: no cover - skip corrupt files
                continue
        lines.append("</recent_session_learnings>")
        return "\n".join(lines)

    def _dominant(self, events: list[dict[str, Any]], key: str) -> str:
        values = [str(e.get(key, "?")) for e in events]
        return max(set(values), key=values.count) if values else "?"

    def _get_trading_date(self) -> str:
        return datetime.now(_ET).strftime("%Y-%m-%d")

    def _update_skill_file(self, summary: dict[str, Any]) -> None:
        """Append session summary to the learnings skill file."""
        try:
            _SKILL_FILE.parent.mkdir(parents=True, exist_ok=True)
            existing = (
                _SKILL_FILE.read_text(encoding="utf-8")
                if _SKILL_FILE.exists()
                else (
                    "# GEX Doctor Daily Learnings\n\n"
                    "This file is automatically updated after each trading session.\n"
                    "It documents what the GEX Doctor system observed and how the market behaved.\n\n"
                    "## Learning Schema\n"
                    "Each session records:\n"
                    "- Dominant bias direction\n"
                    "- Average confidence level\n"
                    "- Dominant regime (positive/negative/neutral)\n"
                    "- HMM market state\n"
                    "- Actual session outcome\n"
                    "- Notes from the session\n\n"
                    "## Sessions (most recent first)\n"
                    "(auto-populated by SessionLearner)\n"
                )
            )
            entry = (
                f"\n## Session {summary['date']}\n"
                f"- Dominant bias: {summary['dominant_bias']}\n"
                f"- Avg confidence: {summary['avg_confidence']}%\n"
                f"- Dominant regime: {summary['dominant_regime']}\n"
                f"- HMM state: {summary['dominant_hmm']}\n"
                f"- Actual outcome: {summary.get('actual_outcome', 'unknown')}\n"
                f"- Notes: {summary.get('notes', '')}\n"
            )
            with _SKILL_FILE.open("w", encoding="utf-8") as handle:
                handle.write(existing + entry)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.debug("Could not update skill file: %s", exc)


__all__ = ["SessionLearner"]
