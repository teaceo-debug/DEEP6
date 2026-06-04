from __future__ import annotations

import json
import os
from pathlib import Path

from deep6.engines.bias_contracts import BiasMode, BiasState, MarketBiasSnapshot
from deep6.engines.bias_json_writer import BiasJsonWriter, default_bias_v3_path


def _snapshot() -> MarketBiasSnapshot:
    return MarketBiasSnapshot(
        symbol="NQ",
        asof_ts=1710000000.25,
        bias_label="STRONG BULL",
        bias_state=BiasState.STRONG_BULL,
        bias_score=8,
        confidence=0.86,
        setup_quality=5,
        mode=BiasMode.GO.value,
        mode_reason="all domains aligned",
        session_label="A+ OPEN",
        xamd_phase="ACCUMULATION",
        intermarket_alignment=0.8,
        kronos_confidence=0.91,
        nearest_support=16000.0,
        nearest_resistance=16125.0,
        domain_detail={
            "ict": {"score": 3},
            "macro": {"score": 2},
            "flow": {"score": 1},
            "kronos": {"score": 2},
        },
        meta={"source": "test"},
    )


def test_default_nt8_path_helper() -> None:
    path = default_bias_v3_path()
    assert path.name == "bias_v3.json"
    assert "NinjaTrader 8" in str(path)


def test_write_snapshot(tmp_path: Path) -> None:
    writer = BiasJsonWriter()
    target = tmp_path / "bias_v3.json"
    writer.write(_snapshot(), target)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data == {
        "bias_label": "STRONG BULL",
        "bias_score": 8,
        "confidence": 0.86,
        "confidence_pct": 86,
        "domain_scores": {"ict": 3, "macro": 2, "flow": 1, "kronos": 2},
        "mode": "GO",
        "mode_reason": "all domains aligned",
        "session_label": "A+ OPEN",
        "setup_quality": 5,
        "updated_ts": 1710000000.25,
        "version": "v3",
        "xamd_phase": "ACCUMULATION",
    }


def test_atomic_write_uses_temp_then_replace(tmp_path: Path, monkeypatch) -> None:
    writer = BiasJsonWriter()
    target = tmp_path / "bias_v3.json"
    seen = {}
    real_replace = os.replace

    def fake_replace(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        seen["src_exists_before_replace"] = src_path.exists()
        seen["dst_exists_before_replace"] = dst_path.exists()
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fake_replace)

    writer.write(_snapshot(), target)

    assert seen["src_exists_before_replace"] is True
    assert seen["dst_exists_before_replace"] is False
    assert target.exists()
    assert not any(target.parent.glob(".bias_v3.*.tmp"))
