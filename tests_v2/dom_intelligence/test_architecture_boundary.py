from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOM_DIR = ROOT / "deep6v2" / "signals" / "dom"


def _load_boundary_module():
    boundary_path = ROOT / "deep6v2" / "signals" / "dom" / "boundary.py"
    spec = importlib.util.spec_from_file_location("test_dom_boundary", boundary_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BOUNDARY = _load_boundary_module()
APPROVED_IMPORTS = BOUNDARY.APPROVED_IMPORTS
FORBIDDEN_IMPORTS = BOUNDARY.FORBIDDEN_IMPORTS
INTEGRATION_RULES = BOUNDARY.INTEGRATION_RULES


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_dashboard_does_not_import_detector_internals() -> None:
    dashboard_files = [
        "dashboard/components/footprint/FootprintChart.tsx",
        "dashboard/components/signals/SignalFeed.tsx",
        "dashboard/components/layout/HeaderStrip.tsx",
    ]
    forbidden_markers = ("from deep6v2.signals.dom", "import deep6v2.signals.dom")

    for relative_path in dashboard_files:
        contents = _read(relative_path)
        for marker in forbidden_markers:
            assert marker not in contents, f"{relative_path} must not reference detector internals: {marker}"


def test_dom_detector_directory_does_not_import_rithmic_client_directly() -> None:
    forbidden_markers = (
        "from deep6v2.data.rithmic_client import",
        "import deep6v2.data.rithmic_client",
    )

    for file_path in DOM_DIR.rglob("*.py"):
        contents = file_path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in contents, f"{file_path.relative_to(ROOT)} must wrap transport, not recreate it"


def test_depth_radar_is_optional_dependency() -> None:
    init_contents = _read("deep6v2/signals/dom/__init__.py")
    assert "deep6.ml.depth_radar" not in init_contents


def test_all_integration_rules_are_documented() -> None:
    assert len(INTEGRATION_RULES) == 8
    assert len(FORBIDDEN_IMPORTS) >= 3


def test_domstate_ownership_contract_is_documented() -> None:
    assert APPROVED_IMPORTS["deep6v2.state.dom"] == ["DOMState"]
    assert any(
        "parallel DOMState" in text
        for text in [*FORBIDDEN_IMPORTS.keys(), *FORBIDDEN_IMPORTS.values()]
    )
