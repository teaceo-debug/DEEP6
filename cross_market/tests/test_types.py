"""Verify all Pydantic types validate correctly."""
import pytest
from pydantic import ValidationError
from cross_market.types.mbo_event import MBOEvent, MBOAction, MBOSide
from cross_market.types.detectors import SpoofResult, DetectorSide
from cross_market.types.llm import LLMAssessment


def test_mbo_event_valid(sample_mbo_add):
    assert sample_mbo_add.order_id == "R8841290"
    assert not sample_mbo_add.is_trade
    assert sample_mbo_add.size == 412


def test_mbo_event_rejects_negative_price():
    with pytest.raises(ValidationError):
        MBOEvent(
            timestamp_exchange_ns=1,
            timestamp_recv_ns=2,
            symbol="NQ",
            action=MBOAction.ADD,
            side=MBOSide.BID,
            price=-100.0,
            size=10,
            order_id="X",
            sequence_id=1,
        )


def test_llm_assessment_rejects_trade_commands():
    with pytest.raises(ValidationError):
        LLMAssessment(
            primary_pattern="absorption",
            evidence=["level held"],
            confidence="high",
            trader_read="buy here",  # forbidden!
            confirmation_criteria="price holds above 21550",
            invalidation_criteria="price breaks below 21545",
        )


def test_llm_assessment_watch_only():
    a = LLMAssessment(
        primary_pattern="absorption",
        evidence=["184 contracts absorbed", "level held"],
        confidence="high",
        trader_read="strong absorption at 21550, level likely to hold",
        confirmation_criteria="price stays above 21548 for 30s",
        invalidation_criteria="price closes below 21547",
    )
    assert a.primary_pattern == "absorption"
    assert not a.do_not_trade
