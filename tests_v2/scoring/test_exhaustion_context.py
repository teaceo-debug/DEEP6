"""Tests for ExhaustionContextFilter — validates research findings.

Research baseline:
- Absorption without exhaustion context: WR=46.3%, Avg=-3.2 ticks
- Absorption WITH exhaustion context: WR=50.2%, Avg=+24.3 ticks (N=321)
- ABS_04 + prior TRAP_05: N=11, WR=55%, Avg=+563 ticks
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime

import pytest

from deep6v2.scoring.exhaustion_context import (
    ExhaustionContextFilter,
    ExhaustionContextResult,
)
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


def _ts() -> datetime:
    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)


def _signal(
    signal_id: SignalId,
    direction: Direction = Direction.BULLISH,
    strength: float = 0.7,
    flag_bit: int = 0,
) -> SignalResult:
    return SignalResult(
        signal_id=signal_id,
        direction=direction,
        strength=strength,
        detail="test",
        price=21490.0,
        flag_bit=flag_bit,
    )


def _ctx_with_delta(deltas: list[int]) -> SessionContext:
    """Create context with pre-populated delta history."""
    ctx = SessionContext(
        atr=10.0,
        cvd=0.0,
        vah=21500.0,
        val=21480.0,
        poc=21490.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
    )
    ctx.delta_history = deque(deltas, maxlen=50)
    return ctx


class TestExhaustionContextFilter:
    """Core filter logic tests."""

    def test_returns_none_without_absorption_signals(self):
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.DELT_01, Direction.BULLISH)]
        ctx = _ctx_with_delta([-100] * 10)

        result = f.evaluate(signals, ctx)

        assert result is None

    def test_returns_none_with_insufficient_history(self):
        f = ExhaustionContextFilter(lookback=10, min_bars=5)
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        ctx = _ctx_with_delta([-100] * 3)  # Only 3 bars, need 5

        result = f.evaluate(signals, ctx)

        assert result is None

    def test_bullish_absorption_with_negative_delta_confirms(self):
        """Bullish absorption + prior sellers exhausted (negative delta sum) = CONFIRMED."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        # Prior 10 bars show sellers dominated (negative delta)
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is True
        assert result.prior_delta_sum < 0
        assert result.signal_direction is Direction.BULLISH
        assert "CONFIRMED" in result.detail

    def test_bearish_absorption_with_positive_delta_confirms(self):
        """Bearish absorption + prior buyers exhausted (positive delta sum) = CONFIRMED."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BEARISH, flag_bit=SignalFlagBits.ABS_04)]
        # Prior 10 bars show buyers dominated (positive delta)
        ctx = _ctx_with_delta([60, 80, 40, 50, 70, 30, 55, 65, 45, 75])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is True
        assert result.prior_delta_sum > 0
        assert result.signal_direction is Direction.BEARISH
        assert "CONFIRMED" in result.detail

    def test_bullish_absorption_with_positive_delta_rejects(self):
        """Bullish absorption + prior buyers dominant (positive delta) = no exhaustion context."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        # Prior 10 bars show BUYERS dominated — no exhaustion
        ctx = _ctx_with_delta([60, 80, 40, 50, 70, 30, 55, 65, 45, 75])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is False
        assert result.prior_delta_sum > 0
        assert "ABSENT" in result.detail

    def test_bearish_absorption_with_negative_delta_rejects(self):
        """Bearish absorption + prior sellers dominant = no exhaustion context."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BEARISH, flag_bit=SignalFlagBits.ABS_04)]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is False
        assert result.prior_delta_sum < 0
        assert "ABSENT" in result.detail

    def test_neutral_delta_sum_rejects(self):
        """Zero delta sum = no clear exhaustion direction."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        ctx = _ctx_with_delta([50, -50, 30, -30, 20, -20, 10, -10, 5, -5])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is False
        assert result.prior_delta_sum == 0

    def test_uses_lookback_window(self):
        """Only uses last N bars, not full history."""
        f = ExhaustionContextFilter(lookback=5, min_bars=5)
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        # Old bars: positive, recent 5 bars: negative (sellers exhausted)
        ctx = _ctx_with_delta([100, 200, 300, 400, 500, -50, -60, -70, -80, -90])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is True  # Only last 5 bars matter
        assert result.lookback_bars == 5

    def test_multiple_absorption_signals_uses_consensus(self):
        """Multiple ABS signals with same direction should confirm."""
        f = ExhaustionContextFilter()
        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01),
            _signal(SignalId.ABS_04, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_04),
        ]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx)

        assert result is not None
        assert result.has_context is True


class TestKillerCombo:
    """ABS_04 + TRAP_05 killer combo tests."""

    def test_abs04_with_prior_trap05_is_killer_combo(self):
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_04)]
        recent_traps = [_signal(SignalId.TRAP_05, Direction.BULLISH, flag_bit=SignalFlagBits.TRAP_05)]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx, recent_trap_signals=recent_traps)

        assert result is not None
        assert result.killer_combo is True
        assert "KILLER_COMBO" in result.detail

    def test_abs04_without_trap05_is_not_killer(self):
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_04)]
        recent_traps = [_signal(SignalId.TRAP_01, Direction.BULLISH, flag_bit=SignalFlagBits.TRAP_01)]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx, recent_trap_signals=recent_traps)

        assert result is not None
        assert result.killer_combo is False

    def test_abs01_with_trap05_is_not_killer(self):
        """Only ABS_04 qualifies for the killer combo."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_01)]
        recent_traps = [_signal(SignalId.TRAP_05, Direction.BULLISH, flag_bit=SignalFlagBits.TRAP_05)]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx, recent_trap_signals=recent_traps)

        assert result is not None
        assert result.killer_combo is False

    def test_killer_combo_without_exhaustion_context(self):
        """Killer combo fires even without exhaustion context."""
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_04)]
        recent_traps = [_signal(SignalId.TRAP_05, Direction.BULLISH, flag_bit=SignalFlagBits.TRAP_05)]
        # Positive delta = no exhaustion context for bullish signal
        ctx = _ctx_with_delta([50, 80, 30, 60, 40, 70, 20, 55, 45, 35])

        result = f.evaluate(signals, ctx, recent_trap_signals=recent_traps)

        assert result is not None
        assert result.killer_combo is True
        assert result.has_context is False  # No exhaustion context, but combo still flagged

    def test_no_recent_traps_means_no_combo(self):
        f = ExhaustionContextFilter()
        signals = [_signal(SignalId.ABS_04, Direction.BULLISH, flag_bit=SignalFlagBits.ABS_04)]
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        result = f.evaluate(signals, ctx, recent_trap_signals=None)

        assert result is not None
        assert result.killer_combo is False


class TestEntryGateIntegration:
    """Verify ExhaustionContextFilter integrates correctly with EntryGate."""

    def test_absorption_without_context_vetoed(self):
        """Absorption entry without exhaustion context should be vetoed."""
        from deep6v2.scoring.entry_gate import EntryGate
        from deep6v2.types.scoring import ScorerResult, SignalTier

        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8, SignalFlagBits.ABS_01),
            _signal(SignalId.EXH_01, Direction.BULLISH, 0.7, SignalFlagBits.EXH_01),
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.6, SignalFlagBits.IMB_01),
            _signal(SignalId.DELT_01, Direction.BULLISH, 0.5, SignalFlagBits.DELT_01),
            _signal(SignalId.VOLP_01, Direction.BULLISH, 0.6, SignalFlagBits.VOLP_01),
            _signal(SignalId.AUCT_01, Direction.BULLISH, 0.5, SignalFlagBits.AUCT_01),
        ]
        scorer_result = ScorerResult(
            tier=SignalTier.TYPE_A,
            raw_score=85.0,
            final_score=85.0,
            category_scores={},
            category_count=6,
            confluence_mult=1.0,
            zone_bonus=0.0,
            gex_mult=1.0,
            agreement_mult=1.0,
            ib_mult=1.0,
            vpin_mult=1.0,
            midday_blocked=False,
            active_signals=signals,
            veto_reasons=[],
            e10_agreement=None,
            e10_caution=False,
        )
        bar = FootprintBar(
            open=21490.0,
            high=21500.0,
            low=21480.0,
            close=21490.0,
            delta=10,
            total_volume=2000,
            bid_volumes={21480.0: 500, 21485.0: 300},
            ask_volumes={21495.0: 300, 21500.0: 400},
            poc_price=21490.0,
            poc_volume=600,
            vah=21498.0,
            val=21484.0,
            cvd=10.0,
            bar_index=5,
            timestamp=_ts(),
            session_type=SessionType.RTH,
        )
        # Prior buyers dominated — no exhaustion context for bullish absorption
        ctx = _ctx_with_delta([60, 80, 40, 50, 70, 30, 55, 65, 45, 75])

        gate = EntryGate()
        decision = gate.evaluate(scorer_result, bar, ctx)

        assert decision.eligible is False
        assert any("exhaustion_context_absent" in r for r in decision.veto_reasons)

    def test_absorption_with_context_passes(self):
        """Absorption entry WITH exhaustion context should pass."""
        from deep6v2.scoring.entry_gate import EntryGate
        from deep6v2.types.scoring import ScorerResult, SignalTier

        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8, SignalFlagBits.ABS_01),
            _signal(SignalId.EXH_01, Direction.BULLISH, 0.7, SignalFlagBits.EXH_01),
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.6, SignalFlagBits.IMB_01),
            _signal(SignalId.DELT_01, Direction.BULLISH, 0.5, SignalFlagBits.DELT_01),
            _signal(SignalId.VOLP_01, Direction.BULLISH, 0.6, SignalFlagBits.VOLP_01),
            _signal(SignalId.AUCT_01, Direction.BULLISH, 0.5, SignalFlagBits.AUCT_01),
        ]
        scorer_result = ScorerResult(
            tier=SignalTier.TYPE_A,
            raw_score=85.0,
            final_score=85.0,
            category_scores={},
            category_count=6,
            confluence_mult=1.0,
            zone_bonus=0.0,
            gex_mult=1.0,
            agreement_mult=1.0,
            ib_mult=1.0,
            vpin_mult=1.0,
            midday_blocked=False,
            active_signals=signals,
            veto_reasons=[],
            e10_agreement=None,
            e10_caution=False,
        )
        bar = FootprintBar(
            open=21490.0,
            high=21500.0,
            low=21480.0,
            close=21490.0,
            delta=10,
            total_volume=2000,
            bid_volumes={21480.0: 500, 21485.0: 300},
            ask_volumes={21495.0: 300, 21500.0: 400},
            poc_price=21490.0,
            poc_volume=600,
            vah=21498.0,
            val=21484.0,
            cvd=10.0,
            bar_index=5,
            timestamp=_ts(),
            session_type=SessionType.RTH,
        )
        # Prior sellers exhausted — confirms bullish absorption
        ctx = _ctx_with_delta([-50, -80, -30, -60, -40, -70, -20, -55, -45, -35])

        gate = EntryGate()
        decision = gate.evaluate(scorer_result, bar, ctx)

        assert decision.eligible is True
        assert decision.exhaustion_context is not None
        assert decision.exhaustion_context.has_context is True

    def test_insufficient_history_passes_through(self):
        """With < min_bars history, filter is not applied (passes through)."""
        from deep6v2.scoring.entry_gate import EntryGate
        from deep6v2.types.scoring import ScorerResult, SignalTier

        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8, SignalFlagBits.ABS_01),
            _signal(SignalId.EXH_01, Direction.BULLISH, 0.7, SignalFlagBits.EXH_01),
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.6, SignalFlagBits.IMB_01),
            _signal(SignalId.DELT_01, Direction.BULLISH, 0.5, SignalFlagBits.DELT_01),
            _signal(SignalId.VOLP_01, Direction.BULLISH, 0.6, SignalFlagBits.VOLP_01),
            _signal(SignalId.AUCT_01, Direction.BULLISH, 0.5, SignalFlagBits.AUCT_01),
        ]
        scorer_result = ScorerResult(
            tier=SignalTier.TYPE_A,
            raw_score=85.0,
            final_score=85.0,
            category_scores={},
            category_count=6,
            confluence_mult=1.0,
            zone_bonus=0.0,
            gex_mult=1.0,
            agreement_mult=1.0,
            ib_mult=1.0,
            vpin_mult=1.0,
            midday_blocked=False,
            active_signals=signals,
            veto_reasons=[],
            e10_agreement=None,
            e10_caution=False,
        )
        bar = FootprintBar(
            open=21490.0,
            high=21500.0,
            low=21480.0,
            close=21490.0,
            delta=10,
            total_volume=2000,
            bid_volumes={21480.0: 500, 21485.0: 300},
            ask_volumes={21495.0: 300, 21500.0: 400},
            poc_price=21490.0,
            poc_volume=600,
            vah=21498.0,
            val=21484.0,
            cvd=10.0,
            bar_index=5,
            timestamp=_ts(),
            session_type=SessionType.RTH,
        )
        # Only 2 bars of history — filter should not apply
        ctx = _ctx_with_delta([50, 60])

        gate = EntryGate()
        decision = gate.evaluate(scorer_result, bar, ctx)

        # Should pass through (filter not applied due to insufficient history)
        assert decision.eligible is True
        assert decision.exhaustion_context is None
