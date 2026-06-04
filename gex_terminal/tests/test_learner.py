"""Tests for the session learner."""
from __future__ import annotations

import json
from pathlib import Path

from gex_terminal.engine import learner as learner_module
from gex_terminal.engine.learner import SessionLearner


def test_save_session_writes_structured_json(tmp_path: Path, monkeypatch):
    learnings_dir = tmp_path / "gex_learnings"
    skill_file = tmp_path / "knowledge.md"
    monkeypatch.setattr(learner_module, "_LEARNINGS_DIR", learnings_dir)
    monkeypatch.setattr(learner_module, "_SKILL_FILE", skill_file)

    learner = SessionLearner()
    learner.record_cycle(
        timestamp=1_748_527_200.0,
        bias_direction="BULLISH",
        confidence=81,
        conviction_grade="A",
        regime="Positive Gamma",
        gamma_flip=17328.85,
        call_wall=17519.43,
        put_wall=17128.57,
        hmm_state="TRENDING",
        flow_direction="bullish",
    )

    learner.save_session(notes="Held bid above flip.", actual_outcome="bullish_follow_through")

    files = list(learnings_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["dominant_bias"] == "BULLISH"
    assert payload["avg_confidence"] == 81
    assert payload["dominant_regime"] == "Positive Gamma"
    assert payload["actual_outcome"] == "bullish_follow_through"
    assert payload["events"][0]["levels"]["gamma_flip"] == 17328.85


def test_recall_context_loads_last_five_sessions(tmp_path: Path, monkeypatch):
    learnings_dir = tmp_path / "gex_learnings"
    learnings_dir.mkdir(parents=True)
    monkeypatch.setattr(learner_module, "_LEARNINGS_DIR", learnings_dir)

    for idx in range(6):
        payload = {
            "date": f"2026-05-0{idx + 1}",
            "dominant_bias": "BULLISH",
            "avg_confidence": 70 + idx,
            "dominant_regime": "Positive Gamma",
            "dominant_hmm": "TRENDING",
            "actual_outcome": "up_day",
            "notes": f"session-{idx}",
        }
        (learnings_dir / f"2026-05-0{idx + 1}.json").write_text(json.dumps(payload), encoding="utf-8")

    learner = SessionLearner()
    context = learner.get_recall_context()

    assert context.startswith("<recent_session_learnings>")
    assert context.endswith("</recent_session_learnings>")
    assert "session-5" in context
    assert "session-0" not in context
