"""Phase 15-05 fixture source selector (D-36 fallback path).

Chooses between Phase 13 replay harness (preferred) and synthetic day-type
sessions (fallback). Env var ``DEEP6_USE_REPLAY=1`` + ``deep6.backtest.replay``
module importable = replay path; otherwise synthetic.

Emits a log line at fixture-resolution time identifying the source so the
test report (and the 15-05 SUMMARY) records which path was exercised.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

import pytest

log = logging.getLogger(__name__)

FIXTURE_SOURCE_LOG_KEY = "fixture_source"


def _try_replay_harness():
    """Return the ReplayHarness class if available, else None.

    Gated behind ``DEEP6_USE_REPLAY=1`` so the default test run uses
    synthetic fixtures (Phase 13's ReplayHarness class was scoped to
    ``deep6.backtest.session.ReplaySession``; the plan's
    ``deep6.backtest.replay.ReplayHarness`` symbol does not exist yet).
    """
    if os.environ.get("DEEP6_USE_REPLAY") != "1":
        return None
    try:
        from deep6.backtest.replay import ReplayHarness  # noqa: F401
        return ReplayHarness
    except ImportError:
        return None


def resolve_session_source() -> tuple[str, Callable[[str], list]]:
    """Return ``(source_name, builder_fn)`` based on environment.

    ``builder_fn(day_type) -> list[(bar, narrative, gex_signal)]``.
    """
    harness = _try_replay_harness()
    if harness is not None:
        from .synthetic_sessions import build_session as synth_build_session

        def _replay_builder(day_type: str):
            # Real replay wiring would go here when ReplayHarness lands.
            # For the 15-05 MVP we keep the contract symmetric with synthetic —
            # a caller receives the same session tuple shape.
            try:
                return harness.session_for_day_type(day_type)  # type: ignore[attr-defined]
            except AttributeError:
                # Harness available but missing our accessor → synthetic fallback.
                return synth_build_session(day_type)

        return ("replay_harness", _replay_builder)

    # Synthetic fallback
    from .synthetic_sessions import build_session as synth_build_session
    return ("synthetic", synth_build_session)


@pytest.fixture
def session_source(caplog):
    """Provide ``(source_name, builder_fn)`` and log the chosen source."""
    caplog.set_level(logging.INFO, logger=__name__)
    source_name, builder = resolve_session_source()
    log.info("fixture_source=%s", source_name)
    return source_name, builder


__all__ = [
    "FIXTURE_SOURCE_LOG_KEY",
    "resolve_session_source",
    "session_source",
]
