"""Utility to load fixture JSON files into Pydantic types."""

from __future__ import annotations

import json
from pathlib import Path

from deep6v2.types.bar import FootprintBar

FIXTURES_DIR = Path(__file__).parent


def load_signal_fixture(name: str) -> dict:
    """Load a signal fixture by filename stem (e.g. 'abs_01')."""
    path = FIXTURES_DIR / "signals" / f"{name}.json"
    return json.loads(path.read_text())


def load_scoring_fixture(name: str) -> dict:
    """Load a scoring scenario fixture by filename stem."""
    path = FIXTURES_DIR / "scoring" / f"{name}.json"
    return json.loads(path.read_text())


def fixture_bar(data: dict) -> FootprintBar:
    """Deserialize a bar from fixture data."""
    return FootprintBar.model_validate(data["bar"])
