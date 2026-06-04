from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

BRAIN_DIR = Path(__file__).parent.parent / "brain"
REFERENCE_DIR = Path(__file__).parent.parent / "reference"


def test_brain_files_exist():
    assert (BRAIN_DIR / "flashalpha_knowledge.yaml").exists()
    assert (BRAIN_DIR / "flashalpha_interpreter.md").exists()
    assert (BRAIN_DIR / "flashalpha_snapshot_schema.json").exists()


def test_knowledge_yaml_loadable():
    import yaml
    data = yaml.safe_load((BRAIN_DIR / "flashalpha_knowledge.yaml").read_text())
    assert "lookups" in data
    assert "heuristics" in data
    assert "routine" in data


def test_snapshot_schema_valid_json():
    data = json.loads((BRAIN_DIR / "flashalpha_snapshot_schema.json").read_text())
    assert data.get("title") == "FlashAlphaSnapshot"
    assert "properties" in data


def test_reference_producer_exists():
    assert (REFERENCE_DIR / "gex_producer.py").exists()


def test_gex_nq_sample_valid_json():
    data = json.loads((REFERENCE_DIR / "gex_nq_sample.json").read_text())
    assert "flip" in data
    assert "call_wall" in data
    assert "put_wall" in data


def test_dry_run_exits_zero(tmp_path):
    env = {
        **os.environ,
        "FLASHALPHA_API_KEY": "test-key-for-dry-run",
        "GEXDOCTOR_FLASHALPHA_API_KEY": "test-key-for-dry-run",
    }
    result = subprocess.run(
        [sys.executable, "-m", "gexdoctor", "--dry-run"],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True, text=True,
        env=env,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "OK" in result.stdout
