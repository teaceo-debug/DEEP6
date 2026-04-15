"""Tests for FreezeGuard position reconciliation — D-14, D-15."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_config(instrument: str = "NQM6", exchange: str = "CME") -> MagicMock:
    cfg = MagicMock()
    cfg.instrument = instrument
    cfg.exchange = exchange
    return cfg


def _make_position_item(ticker: str, net_quantity: int) -> MagicMock:
    pos = MagicMock()
    pos.ticker = ticker
    pos.net_quantity = net_quantity
    return pos


@pytest.mark.asyncio
async def test_reconcile_success_unfreeze():
    """On reconnect with successful reconciliation, state becomes CONNECTED."""
    from deep6.state.connection import FreezeGuard, ConnectionState

    guard = FreezeGuard()
    guard.on_disconnect()
    assert guard.is_frozen

    client = MagicMock()
    client.connect = AsyncMock()
    client.get_positions = AsyncMock(return_value=[
        _make_position_item("NQM6", 0),  # flat
    ])

    config = _make_config()
    await guard.on_reconnect(client, config)

    assert not guard.is_frozen
    assert guard.get_state() == ConnectionState.CONNECTED
    assert guard.last_known_position == 0


@pytest.mark.asyncio
async def test_reconcile_success_with_open_position():
    """Reconcile with net_quantity != 0 still succeeds — records position."""
    from deep6.state.connection import FreezeGuard, ConnectionState

    guard = FreezeGuard()
    guard.on_disconnect()

    client = MagicMock()
    client.connect = AsyncMock()
    client.get_positions = AsyncMock(return_value=[
        _make_position_item("NQM6", -1),  # short 1 contract
    ])

    config = _make_config()
    await guard.on_reconnect(client, config)

    assert not guard.is_frozen
    assert guard.last_known_position == -1


@pytest.mark.asyncio
async def test_reconcile_failure_stays_frozen():
    """On reconcile failure (exception), FreezeGuard stays frozen (D-15 / T-08-02)."""
    from deep6.state.connection import FreezeGuard, ConnectionState

    guard = FreezeGuard()
    guard.on_disconnect()

    client = MagicMock()
    client.connect = AsyncMock()
    client.get_positions = AsyncMock(side_effect=RuntimeError("Rithmic ORDER_PLANT unavailable"))

    config = _make_config()
    await guard.on_reconnect(client, config)

    # Must stay frozen — safer than assuming clean state
    assert guard.is_frozen
    assert guard.get_state() != ConnectionState.CONNECTED


def test_freeze_on_disconnect():
    """on_disconnect() sets is_frozen immediately (D-14)."""
    from deep6.state.connection import FreezeGuard

    guard = FreezeGuard()
    assert not guard.is_frozen

    guard.on_disconnect()
    assert guard.is_frozen


def test_last_known_position_default():
    """FreezeGuard.last_known_position defaults to 0."""
    from deep6.state.connection import FreezeGuard

    guard = FreezeGuard()
    assert guard.last_known_position == 0


@pytest.mark.asyncio
async def test_sync_position_state_success():
    """sync_position_state returns reconciled=True with correct rithmic_position."""
    from deep6.state.connection import sync_position_state

    client = MagicMock()
    client.get_positions = AsyncMock(return_value=[
        _make_position_item("NQM6", 1),
    ])
    config = _make_config()

    result = await sync_position_state(client, config)
    assert result["reconciled"] is True
    assert result["rithmic_position"] == 1


@pytest.mark.asyncio
async def test_sync_position_state_failure():
    """sync_position_state returns reconciled=False when exception raised."""
    from deep6.state.connection import sync_position_state

    client = MagicMock()
    client.get_positions = AsyncMock(side_effect=ConnectionError("timeout"))
    config = _make_config()

    result = await sync_position_state(client, config)
    assert result["reconciled"] is False
    assert result["rithmic_position"] is None
