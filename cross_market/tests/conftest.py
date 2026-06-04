"""Shared pytest fixtures for cross_market tests."""
import pytest
from cross_market.types.mbo_event import MBOEvent, MBOAction, MBOSide
from cross_market.types.detectors import SpoofResult, IcebergResult, DetectorSide


@pytest.fixture
def sample_mbo_add():
    return MBOEvent(
        timestamp_exchange_ns=1_000_000_000,
        timestamp_recv_ns=1_000_000_100,
        symbol="NQ.c.0",
        action=MBOAction.ADD,
        side=MBOSide.BID,
        price=21550.00,
        size=412,
        order_id="R8841290",
        sequence_id=1001,
        priority=5,
    )


@pytest.fixture
def sample_spoof_result():
    return SpoofResult(
        side=DetectorSide.BID,
        price=21550.00,
        order_id="R8841290",
        life_ms=2840.0,
        size=412,
        distance_to_touch_ticks=3.0,
        spoof_probability=0.87,
        reason_codes=["short_life", "no_fill", "oversized"],
    )


@pytest.fixture
def sample_iceberg_result():
    return IcebergResult(
        price=21555.25,
        side=DetectorSide.ASK,
        traded_cum=247,
        peak_visible=12,
        ratio=20.58,
        refresh_count=9,
        confidence=0.94,
        reason_codes=["high_hvr", "refresh_pattern"],
    )
