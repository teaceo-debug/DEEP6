from __future__ import annotations

import json
import logging

from gexdoctor.monitor.logger import AuditTrail, get_logger


def test_get_logger_returns_logger(tmp_path):
    logger = get_logger("gexdoctor.test.logger", tmp_path)
    assert isinstance(logger, logging.Logger)


def test_audit_trail_creates_file(tmp_path):
    audit = AuditTrail(tmp_path)
    assert audit.log_path.parent == tmp_path
    assert audit.log_path.name.startswith("audit-")


def test_audit_trail_record_writes_json(tmp_path):
    audit = AuditTrail(tmp_path)
    audit.record(["qqq"], 3, 22100.0, 0.9)
    line = audit.log_path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["levels_received"] == 3


def test_audit_trail_record_fields(tmp_path):
    audit = AuditTrail(tmp_path)
    audit.record(["qqq", "ndx"], 2, None, 0.7, bias_direction="bullish", errors=["x"])
    payload = json.loads(audit.log_path.read_text(encoding="utf-8").strip())
    assert set(payload) >= {
        "timestamp",
        "sources_polled",
        "levels_received",
        "magnet_selected",
        "confidence",
        "bias_direction",
        "errors",
    }


def test_audit_trail_timestamp_present(tmp_path):
    audit = AuditTrail(tmp_path)
    audit.record(["qqq"], 1, 1.0, 0.5)
    payload = json.loads(audit.log_path.read_text(encoding="utf-8").strip())
    assert "T" in payload["timestamp"]
