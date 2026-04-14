"""Shared fixtures for Phase 15-05 integration tests.

Re-exports ``session_source`` from ``phase15_fixtures`` so every test under
``tests/integration/`` receives the day-type fixture selector without an
explicit import.
"""
from __future__ import annotations

from tests.integration.fixtures.phase15_fixtures import session_source  # noqa: F401
