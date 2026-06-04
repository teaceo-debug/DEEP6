"""Shared pytest fixtures for tests_v2."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.session import SessionContext

ET = ZoneInfo("America/New_York")


@pytest.fixture
def sample_footprint_bar():
    """A basic NQ footprint bar for testing."""
    return FootprintBar(
        open=21450.0,
        high=21475.0,
        low=21440.0,
        close=21465.0,
        delta=150,
        total_volume=2000,
        bid_volumes={21440.0: 200, 21440.25: 100, 21445.0: 150, 21450.0: 300},
        ask_volumes={21440.0: 50, 21440.25: 30, 21445.0: 100, 21450.0: 250},
        poc_price=21450.0,
        poc_volume=300,
        vah=21468.0,
        val=21445.0,
        cvd=300.0,
        bar_index=30,
        timestamp=datetime(2026, 5, 13, 10, 0, 0, tzinfo=ET),
        session_type=SessionType.RTH,
    )


@pytest.fixture
def sample_session_context(sample_footprint_bar):
    """A basic SessionContext with minimal history."""
    ctx = SessionContext(
        atr=12.0,
        cvd=300.0,
        vah=21468.0,
        val=21445.0,
        poc=21450.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
    )
    ctx.bar_history.append(sample_footprint_bar)
    ctx.price_history.append(21465.0)
    ctx.cvd_history.append(300.0)
    ctx.delta_history.append(150)
    ctx.poc_history.append(21450.0)
    ctx.vol_history.append(2000)
    return ctx


@pytest.fixture
def sample_dom_snapshot():
    """A basic DOM snapshot with 5 bid and 5 ask levels."""
    bids = [
        DOMLevel(price=21450.0, volume=100),
        DOMLevel(price=21449.75, volume=80),
        DOMLevel(price=21449.50, volume=120),
        DOMLevel(price=21449.25, volume=60),
        DOMLevel(price=21449.0, volume=90),
    ]
    asks = [
        DOMLevel(price=21450.25, volume=70),
        DOMLevel(price=21450.50, volume=110),
        DOMLevel(price=21450.75, volume=50),
        DOMLevel(price=21451.0, volume=130),
        DOMLevel(price=21451.25, volume=40),
    ]
    return DOMSnapshot(
        bids=bids,
        asks=asks,
        timestamp=datetime(2026, 5, 13, 10, 0, 0, tzinfo=ET),
    )
