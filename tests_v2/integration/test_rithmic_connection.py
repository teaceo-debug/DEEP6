"""Integration tests for Rithmic test environment connection."""

from __future__ import annotations

import asyncio
import os

import pytest

try:
    import async_rithmic  # noqa: F401

    HAS_RITHMIC = True
except ImportError:
    HAS_RITHMIC = False

pytestmark = pytest.mark.integration

RITHMIC_CREDS_AVAILABLE = all(
    [
        os.environ.get("RITHMIC_USER"),
        os.environ.get("RITHMIC_PASSWORD"),
        os.environ.get("RITHMIC_SYSTEM_NAME"),
    ]
)


@pytest.fixture
def skip_if_no_rithmic() -> None:
    """Skip integration tests if Rithmic credentials are not configured."""
    if not HAS_RITHMIC:
        pytest.skip("async-rithmic not installed")
    if not RITHMIC_CREDS_AVAILABLE:
        pytest.skip(
            "Rithmic credentials not configured. Set RITHMIC_USER, "
            "RITHMIC_PASSWORD, RITHMIC_SYSTEM_NAME environment variables."
        )


@pytest.mark.asyncio
async def test_rithmic_connection(skip_if_no_rithmic: None) -> None:
    """Skeleton integration test for the Rithmic test environment."""
    from deep6v2.config.rithmic import RithmicConfig
    from deep6v2.data.rithmic_client import RithmicClient

    config = RithmicConfig(
        uri="wss://rituz00100.rithmic.com",
        username=os.environ["RITHMIC_USER"],
        password=os.environ["RITHMIC_PASSWORD"],
        system_name=os.environ["RITHMIC_SYSTEM_NAME"],
    )

    dom_updates: list[object] = []
    trade_ticks: list[object] = []

    client = RithmicClient(
        config=config,
        on_dom_update=lambda update: dom_updates.append(update),
        on_tick=lambda tick: trade_ticks.append(tick),
    )

    try:
        await client.connect()

        for _ in range(30):
            if dom_updates and trade_ticks:
                break
            await asyncio.sleep(1.0)

        assert dom_updates, "No DOM updates received within 30 seconds"
        assert trade_ticks, "No trade ticks received within 30 seconds"
    finally:
        await client.disconnect()
