"""Tests for deep6.copilot.session.SessionManager."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.copilot.session import SessionManager, _is_rth_now


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def session(copilot_config, tmp_path: Path) -> SessionManager:
    state_file = tmp_path / ".copilot_state.json"
    return SessionManager(copilot_config, state_path=state_file)


# ------------------------------------------------------------------
# Test 1: startup initialises all components
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_initialises_all_components(session: SessionManager) -> None:
    """start() should connect bridge, start overlay, launch RTH watchdog."""
    session._bridge_client.connect = AsyncMock()
    session._overlay.start = MagicMock()

    await session.start()

    # Bridge connect was called
    session._bridge_client.connect.assert_awaited_once()

    # Overlay was started
    session._overlay.start.assert_called_once()

    # RTH watchdog task is running
    assert session._rth_task is not None
    assert not session._rth_task.done()

    # Session marked as started
    assert session.is_started is True

    # Adapters populated from config (all enabled by default)
    status = session.get_status()
    assert "calendar" in status["adapters"]
    assert "news" in status["adapters"]

    # Cleanup
    await session.stop()


# ------------------------------------------------------------------
# Test 2: shutdown stops all components and saves state
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_calls_all_components_and_saves_state(session: SessionManager) -> None:
    """stop() should disconnect bridge, stop overlay, cancel watchdog, save state."""
    session._bridge_client.connect = AsyncMock()
    session._bridge_client.disconnect = AsyncMock()
    session._overlay.start = MagicMock()
    session._overlay.stop = MagicMock()

    await session.start()
    await session.stop()

    # Bridge disconnected
    session._bridge_client.disconnect.assert_awaited_once()

    # Overlay stopped
    session._overlay.stop.assert_called_once()

    # RTH watchdog cancelled
    assert session._rth_task is None or session._rth_task.done()

    # State file written
    assert session._state_path.exists()
    state = json.loads(session._state_path.read_text(encoding="utf-8"))
    assert "last_run" in state
    assert "session_stats" in state
    assert state["session_stats"]["start_count"] == 1

    # Session no longer started
    assert session.is_started is False


# ------------------------------------------------------------------
# Test 3: RTH watchdog pauses outside trading hours
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rth_watchdog_pauses_outside_rth(session: SessionManager) -> None:
    """RTH watchdog should set paused=True when outside RTH."""
    session._bridge_client.connect = AsyncMock()
    session._overlay.start = MagicMock()
    session._overlay.set_connected = MagicMock()

    await session.start()

    # Cancel existing watchdog so we control the cycle
    if session._rth_task is not None:
        session._rth_task.cancel()
        try:
            await session._rth_task
        except (asyncio.CancelledError, Exception):
            pass

    # Patch RTH check to return outside-RTH, then run one watchdog cycle
    with patch("deep6.copilot.session._is_rth_now", return_value=False), \
         patch("deep6.copilot.session._seconds_until_rth_open", return_value=60.0), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        # Make sleep raise CancelledError after first call to exit the loop
        mock_sleep.side_effect = asyncio.CancelledError

        session._paused = False
        session._started = True

        task = asyncio.create_task(session._rth_watchdog())
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    assert session.is_paused is True
    session._overlay.set_connected.assert_called_with(False)

    await session.stop()
