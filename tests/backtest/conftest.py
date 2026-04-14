"""Shared fixtures for backtest tests.

FakeMBOEvent is a minimal stand-in for a Databento MBOMsg — only the
fields MBOAdapter reads (ts_event, action, side, price, size,
instrument_id). Lets us drive the adapter in-process with synthetic
streams, no network required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pytest


@dataclass
class FakeMBOEvent:
    """Duck-typed stand-in for databento_dbn.MBOMsg.

    Price is in Databento wire format (fixed-point int / 1e9).
    ``ts_event`` is nanoseconds since epoch.
    ``action``/``side`` are single-char strings.
    """

    ts_event: int
    action: str
    side: str
    price: int
    size: int
    instrument_id: int = 1


def _p(dollars: float) -> int:
    """Convert a human dollar price to Databento fixed-point int."""
    return int(round(dollars * 1e9))


@pytest.fixture
def make_event():
    """Factory for FakeMBOEvent with sensible defaults."""

    def _make(
        ts_ns: int = 1_700_000_000_000_000_000,
        action: str = "T",
        side: str = "A",
        price: float = 21000.0,
        size: int = 1,
        instrument_id: int = 1,
    ) -> FakeMBOEvent:
        return FakeMBOEvent(
            ts_event=ts_ns,
            action=action,
            side=side,
            price=_p(price),
            size=size,
            instrument_id=instrument_id,
        )

    return _make


@pytest.fixture
def price_to_wire():
    """Helper to turn a dollar price into Databento wire format."""
    return _p
