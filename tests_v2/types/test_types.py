from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.dom import DOMLevel, DOMSnapshot, DOMUpdate
from deep6v2.types.execution import OrderSide, OrderType, TradeSetup, TradeState, TradeTransition
from deep6v2.types.interfaces import IAbsorptionZoneReceiver, IDepthConsumingDetector, ISignalDetector
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import (
    SIGNAL_TO_CATEGORY,
    Direction,
    SignalCategory,
    SignalFlagBits,
    SignalId,
    SignalResult,
)


def _sample_bar() -> FootprintBar:
    return FootprintBar(
        open=21000.0,
        high=21010.0,
        low=20995.0,
        close=21005.0,
        delta=125,
        total_volume=1_000,
        bid_volumes={21000.0: 200, 21000.25: 100},
        ask_volumes={21000.0: 300, 21000.25: 400},
        poc_price=21000.25,
        poc_volume=500,
        vah=21008.0,
        val=20998.0,
        cvd=1_250.0,
        bar_index=15,
        timestamp=datetime(2026, 5, 14, 13, 45, tzinfo=UTC),
        session_type=SessionType.RTH,
    )


def test_signal_id_count_and_required_members():
    assert len(SignalId) == 55
    assert SignalId.ABS_01.value == "ABS_01"
    assert SignalId.ENG_06.value == "ENG_06"
    assert SignalId.SPOOF_VETO.value == "SPOOF_VETO"


def test_signal_categories_and_mapping_contract():
    assert len(SignalCategory) == 8
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_02] is None
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_03] is None
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_05] is None
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_07] is None
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_04] == SignalCategory.ABSORPTION
    assert SIGNAL_TO_CATEGORY[SignalId.ENG_06] == SignalCategory.POC

    scored_signals = [
        signal_id
        for signal_id in SignalId
        if signal_id not in {SignalId.PIN_REGIME, SignalId.REGIME_CHANGE, SignalId.SPOOF_VETO}
    ]
    assert len(scored_signals) == 52
    assert set(scored_signals) == set(SIGNAL_TO_CATEGORY)


def test_signal_flag_bits_are_unique_and_exact_masks():
    bit_values = {
        name: value
        for name, value in SignalFlagBits.__dict__.items()
        if name.isupper() and isinstance(value, int)
    }

    assert len(bit_values) == 55
    assert len(set(bit_values.values())) == len(bit_values)
    assert SignalFlagBits.ABS_01 == 1 << 0
    assert SignalFlagBits.VOLP_06 == 1 << 51
    assert SignalFlagBits.ENG_07 == 1 << 57
    assert SignalFlagBits.PIN_REGIME == 1 << 45
    assert SignalFlagBits.REGIME_CHANGE == 1 << 46
    assert SignalFlagBits.SPOOF_VETO == 1 << 47


def test_footprint_bar_round_trip_json_and_is_frozen():
    bar = _sample_bar()

    encoded = bar.model_dump_json()
    decoded = FootprintBar.model_validate_json(encoded)

    assert decoded == bar
    with pytest.raises(ValidationError):
        FootprintBar.model_validate({"open": 1.0})
    with pytest.raises(ValidationError):
        SignalResult(
            signal_id=SignalId.ABS_01,
            direction=Direction.BULLISH,
            strength=1.5,
            detail="bad",
            price=1.0,
            flag_bit=SignalFlagBits.ABS_01,
        )


def test_signal_result_and_scorer_result_models():
    signal = SignalResult(
        signal_id=SignalId.ABS_01,
        direction=Direction.BULLISH,
        strength=0.8,
        detail="classic absorption",
        price=21000.25,
        flag_bit=SignalFlagBits.ABS_01,
    )

    scorer = ScorerResult(
        tier=SignalTier.TYPE_A,
        raw_score=82.5,
        final_score=91.0,
        category_scores={"absorption": 20.0, "delta": 14.3},
        category_count=2,
        confluence_mult=1.25,
        zone_bonus=6.0,
        gex_mult=1.1,
        agreement_mult=1.05,
        ib_mult=1.15,
        vpin_mult=1.0,
        midday_blocked=False,
        active_signals=[signal],
        veto_reasons=[],
        e10_agreement=True,
        e10_caution=False,
        wall_context_applied=True,
        wall_context_details=["reserve_refresh_bid_1.0t"],
    )

    assert scorer.active_signals == [signal]
    assert scorer.tier is SignalTier.TYPE_A
    assert scorer.wall_context_applied is True


def test_signal_tier_threshold_constants():
    assert SignalTier.TYPE_A_MIN_SCORE == 80
    assert SignalTier.TYPE_B_MIN_SCORE == 72
    assert SignalTier.TYPE_C_MIN_SCORE == 50


def test_dom_models_are_frozen_and_structured():
    level = DOMLevel(price=21000.25, volume=125)
    snapshot = DOMSnapshot(
        timestamp=datetime(2026, 5, 14, 13, 45, tzinfo=UTC),
        bids=[level],
        asks=[DOMLevel(price=21000.5, volume=130)],
    )
    update = DOMUpdate(side=OrderSide.BUY, level=1, price=21000.25, volume=150)

    assert snapshot.bids[0] == level
    assert update.volume == 150


def test_execution_models_and_enums():
    setup = TradeSetup(
        state=TradeState.ARMED,
        transition=TradeTransition.T3,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        entry_price=21000.25,
        stop_price=20995.25,
        target_price=21010.25,
        confidence=88.0,
        signal_ids=[SignalId.ABS_01, SignalId.DELT_04],
        bar_index=25,
    )

    assert setup.state is TradeState.ARMED
    assert setup.signal_ids == [SignalId.ABS_01, SignalId.DELT_04]


def test_session_context_rolling_histories_are_bounded():
    context = SessionContext(
        atr=12.5,
        cvd=1_500.0,
        vah=21010.0,
        val=20990.0,
        poc=21000.25,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
    )

    assert isinstance(context.bar_history, deque)
    assert context.bar_history.maxlen == 50
    assert context.price_history.maxlen == 50
    assert context.cvd_history.maxlen == 50
    assert context.delta_history.maxlen == 50
    assert context.poc_history.maxlen == 50
    assert context.vol_history.maxlen == 50
    assert context.imbalance_history.maxlen == 50
    assert context.current_bar is None
    assert context.e10_direction is None
    assert context.e10_strength == 0.0
    assert context.e10_stale is True


def test_protocols_are_runtime_checkable():
    class Detector:
        def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
            return []

    class DepthConsumer:
        def on_depth(self, snapshot: DOMSnapshot) -> None:
            return None

    class ZoneReceiver:
        def mark_absorption_zone(self, price: float, direction: Direction, strength: float) -> None:
            return None

    assert isinstance(Detector(), ISignalDetector)
    assert isinstance(DepthConsumer(), IDepthConsumingDetector)
    assert isinstance(ZoneReceiver(), IAbsorptionZoneReceiver)
