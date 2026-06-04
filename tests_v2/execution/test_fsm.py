from __future__ import annotations

from deep6v2.execution.fsm import TradeDecisionMachine
from deep6v2.execution.rithmic_broker import Fill
from deep6v2.types.execution import OrderSide, TradeState, TradeTransition
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


def _score_result(*, tier: SignalTier, direction: Direction, midday_blocked: bool = False) -> ScorerResult:
    return ScorerResult(
        tier=tier,
        raw_score=82.0,
        final_score=82.0,
        category_scores={"absorption": 82.0},
        category_count=1,
        confluence_mult=1.0,
        zone_bonus=0.0,
        gex_mult=1.0,
        agreement_mult=1.0,
        ib_mult=1.0,
        vpin_mult=1.0,
        midday_blocked=midday_blocked,
        active_signals=[
            SignalResult(
                signal_id=SignalId.ABS_01,
                direction=direction,
                strength=1.0,
                detail="test",
                price=21000.0,
                flag_bit=SignalFlagBits.ABS_01,
            )
        ],
        veto_reasons=[],
        e10_agreement=True,
        e10_caution=False,
    )


def _fill(side: OrderSide, size: int = 1, price: float = 21000.0) -> Fill:
    return Fill(
        order_id="oid",
        symbol="NQ",
        side=side,
        size=size,
        price=price,
        timestamp=1.0,
    )


def test_reachability_drives_all_seven_states() -> None:
    machine = TradeDecisionMachine(cooldown_bars=2)
    seen = {machine.state}

    machine.on_session_open()
    seen.add(machine.state)
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 10, 21000.0, 10.0)
    seen.add(machine.state)
    machine.on_bar_close(11)
    seen.add(machine.state)
    machine.on_fill(_fill(OrderSide.BUY))
    seen.add(machine.state)
    machine.on_exit_trigger("target")
    seen.add(machine.state)
    machine.on_position_flat()
    seen.add(machine.state)

    assert seen == {
        TradeState.IDLE,
        TradeState.WATCHING,
        TradeState.ARMED,
        TradeState.PENDING_ENTRY,
        TradeState.IN_POSITION,
        TradeState.EXITING,
        TradeState.CLOSED,
    }


def test_d20_confirmation_delay_requires_next_bar_close() -> None:
    machine = TradeDecisionMachine()
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_B, direction=Direction.BEARISH), 20, 21000.0, 8.0)

    assert machine.state is TradeState.ARMED

    machine.on_bar_close(20)
    assert machine.state is TradeState.ARMED

    machine.on_bar_close(21)
    assert machine.state is TradeState.PENDING_ENTRY


def test_setup_expiry_returns_armed_to_watching_after_four_bars() -> None:
    machine = TradeDecisionMachine(max_setup_age=3)
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 0, 21000.0, 10.0)

    machine.on_bar_close(4)

    assert machine.state is TradeState.WATCHING
    assert machine.setup is None
    assert machine.transitions[-1] == (TradeState.ARMED, TradeState.WATCHING, TradeTransition.T8.value)


def test_midday_block_invalidation_forces_armed_to_watching() -> None:
    machine = TradeDecisionMachine()
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 59, 21000.0, 10.0)

    machine.on_bar_close(100)

    assert machine.state is TradeState.WATCHING
    assert machine.setup is None


def test_cooldown_requires_two_closed_bars_before_watching() -> None:
    machine = TradeDecisionMachine(cooldown_bars=2)
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 10, 21000.0, 10.0)
    machine.on_bar_close(11)
    machine.on_fill(_fill(OrderSide.BUY))
    machine.on_exit_trigger("manual")
    machine.on_position_flat()

    assert machine.state is TradeState.CLOSED

    machine.on_bar_close(12)
    assert machine.state is TradeState.CLOSED
    assert machine.cooldown_remaining == 1

    machine.on_bar_close(13)
    assert machine.state is TradeState.WATCHING
    assert machine.cooldown_remaining == 0


def test_all_eleven_transitions_are_exercised() -> None:
    machine = TradeDecisionMachine(cooldown_bars=2)
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 10, 21000.0, 10.0)
    machine.check_invalidation(opposing_tier=SignalTier.TYPE_A)
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 20, 21000.0, 10.0)
    machine.on_bar_close(21)
    machine.check_invalidation(spoof_veto=True)
    machine.on_score(_score_result(tier=SignalTier.TYPE_B, direction=Direction.BEARISH), 30, 21000.0, 10.0)
    machine.on_bar_close(31)
    machine.on_fill(_fill(OrderSide.SELL))
    machine.on_fill(_fill(OrderSide.SELL, size=1, price=20995.0))
    machine.on_exit_trigger("target")
    machine.on_position_flat()
    machine.on_bar_close(32)
    machine.on_bar_close(33)
    machine.on_session_close()

    transition_ids = [transition for _, _, transition in machine.transitions]

    assert transition_ids == [
        TradeTransition.T1.value,
        TradeTransition.T2.value,
        TradeTransition.T8.value,
        TradeTransition.T2.value,
        TradeTransition.T3.value,
        TradeTransition.T9.value,
        TradeTransition.T2.value,
        TradeTransition.T3.value,
        TradeTransition.T4.value,
        TradeTransition.T11.value,
        f"{TradeTransition.T5.value}:target",
        TradeTransition.T6.value,
        TradeTransition.T7.value,
        TradeTransition.T10.value,
    ]


def test_transition_history_recorded_in_order() -> None:
    machine = TradeDecisionMachine()
    machine.on_session_open()
    machine.on_score(_score_result(tier=SignalTier.TYPE_A, direction=Direction.BULLISH), 5, 21000.0, 12.0)
    machine.on_bar_close(6)

    assert machine.transitions == [
        (TradeState.IDLE, TradeState.WATCHING, TradeTransition.T1.value),
        (TradeState.WATCHING, TradeState.ARMED, TradeTransition.T2.value),
        (TradeState.ARMED, TradeState.PENDING_ENTRY, TradeTransition.T3.value),
    ]
