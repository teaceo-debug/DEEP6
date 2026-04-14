"""Tests for RiskManager circuit breakers and GEX regime gate (Plan 08-03)."""
from __future__ import annotations

import time

import pytest

from deep6.execution.config import ExecutionConfig
from deep6.execution.risk_manager import GateResult, RiskManager, RiskState
from deep6.engines.gex import GexRegime, GexSignal
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(tier=SignalTier.TYPE_A, direction=1, categories=None) -> ScorerResult:
    return ScorerResult(
        total_score=80.0,
        tier=tier,
        direction=direction,
        engine_agreement=0.8,
        category_count=3,
        confluence_mult=1.25,
        zone_bonus=0.0,
        narrative=NarrativeType.ABSORPTION,
        label="TYPE_A LONG",
        categories_firing=categories or [],
    )


def _make_gex(
    regime=GexRegime.NEUTRAL,
    near_call=False,
    near_put=False,
    direction=1,
) -> GexSignal:
    return GexSignal(
        regime=regime,
        direction=direction,
        call_wall=19500.0,
        put_wall=18500.0,
        gamma_flip=19000.0,
        near_call_wall=near_call,
        near_put_wall=near_put,
        strength=0.5,
        detail="test GEX signal",
    )


def _make_rm(config=None) -> RiskManager:
    cfg = config or ExecutionConfig()
    return RiskManager(cfg)


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------

class TestDailyLossLimit:
    def test_daily_loss_limit_blocks_entry(self):
        rm = _make_rm()
        # Record a loss that hits the limit
        rm.record_trade(-500.0)  # hits -500 limit
        gate = rm.can_enter(_make_result())
        assert gate.allowed is False
        assert "Daily loss limit" in gate.reason

    def test_daily_loss_below_limit_allows_entry(self):
        rm = _make_rm()
        # Keep within -1R so graduated DD gates don't fire (risk_per_trade_R default=100)
        rm.record_trade(-50.0)
        gate = rm.can_enter(_make_result())
        assert gate.allowed is True


class TestConsecutiveLossPause:
    def test_consecutive_loss_pause_after_3_losses(self):
        cfg = ExecutionConfig(consecutive_loss_limit=3, pause_minutes=30.0)
        rm = RiskManager(cfg)
        for _ in range(3):
            rm.record_trade(-100.0)
        gate = rm.can_enter(_make_result())
        assert gate.allowed is False
        assert "pause" in gate.reason.lower()

    def test_win_resets_consecutive_counter(self):
        cfg = ExecutionConfig(consecutive_loss_limit=3, pause_minutes=30.0)
        rm = RiskManager(cfg)
        rm.record_trade(-100.0)
        rm.record_trade(-100.0)
        assert rm.state.consecutive_losses == 2
        rm.record_trade(+200.0)  # Win resets counter
        assert rm.state.consecutive_losses == 0
        gate = rm.can_enter(_make_result())
        assert gate.allowed is True

    def test_record_trade_positive_pnl_resets_consecutive(self):
        rm = _make_rm()
        rm.record_trade(-50.0)
        rm.record_trade(-50.0)
        rm.record_trade(100.0)
        assert rm.state.consecutive_losses == 0


class TestMaxTradesPerDay:
    def test_max_trades_per_day_blocks(self):
        cfg = ExecutionConfig(max_trades_per_day=3)
        rm = RiskManager(cfg)
        for _ in range(3):
            rm.record_trade(10.0)  # 3 trades
        gate = rm.can_enter(_make_result())
        assert gate.allowed is False
        assert "Max trades" in gate.reason

    def test_below_max_trades_allows_entry(self):
        cfg = ExecutionConfig(max_trades_per_day=10)
        rm = RiskManager(cfg)
        for _ in range(9):
            rm.record_trade(10.0)
        gate = rm.can_enter(_make_result())
        assert gate.allowed is True


class TestResetDaily:
    def test_reset_daily_clears_state(self):
        rm = _make_rm()
        rm.record_trade(-300.0)
        rm.record_trade(-300.0)
        rm.reset_daily()
        assert rm.state.daily_pnl == 0.0
        assert rm.state.trades_today == 0
        assert rm.state.consecutive_losses == 0
        gate = rm.can_enter(_make_result())
        assert gate.allowed is True


# ---------------------------------------------------------------------------
# GEX gate tests
# ---------------------------------------------------------------------------

class TestGexNegativeAmplifying:
    def test_gex_negative_blocks_type_b(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_B, direction=1)
        gex = _make_gex(regime=GexRegime.NEGATIVE_AMPLIFYING)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is False
        assert "TYPE_B" in gate.reason

    def test_gex_negative_type_a_without_absorption_blocked(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_A, direction=1, categories=["exhaustion"])
        gex = _make_gex(regime=GexRegime.NEGATIVE_AMPLIFYING)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is False
        assert "absorption" in gate.reason

    def test_gex_negative_type_a_with_absorption_allowed(self):
        rm = _make_rm()
        result = _make_result(
            tier=SignalTier.TYPE_A, direction=1, categories=["absorption", "exhaustion"]
        )
        gex = _make_gex(regime=GexRegime.NEGATIVE_AMPLIFYING)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is True

    def test_gex_positive_dampening_type_b_allowed(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_B, direction=1)
        gex = _make_gex(regime=GexRegime.POSITIVE_DAMPENING)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is True


class TestGexWallConflict:
    def test_wall_conflict_long_at_call_wall_blocked(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_A, direction=1)
        gex = _make_gex(near_call=True, direction=1)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is False
        assert "call wall" in gate.reason

    def test_wall_conflict_short_at_put_wall_blocked(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_A, direction=-1)
        gex = _make_gex(near_put=True, direction=-1)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is False
        assert "put wall" in gate.reason

    def test_long_at_put_wall_not_blocked(self):
        """LONG at put wall is NOT a conflict (dealer buying supports longs)."""
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_A, direction=1)
        gex = _make_gex(near_put=True, direction=1)
        gate = rm.can_enter(result, gex)
        assert gate.allowed is True


class TestNoGexSignal:
    def test_no_gex_signal_skips_gex_gate(self):
        rm = _make_rm()
        result = _make_result(tier=SignalTier.TYPE_A)
        gate = rm.can_enter(result, gex_signal=None)
        assert gate.allowed is True


# ---------------------------------------------------------------------------
# Variable sizing tests
# ---------------------------------------------------------------------------

class _FakeNarrative:
    def __init__(self, strength=1.0):
        self.strength = strength


class _FakeVPINRegime:
    def __init__(self, name):
        self.name = name


class _FakeVPIN:
    def __init__(self, name):
        self.flow_regime = _FakeVPINRegime(name)


class TestSizeContracts:
    def test_size_score_95_returns_3(self):
        rm = _make_rm()
        res = _make_result(tier=SignalTier.TYPE_A)
        res = ScorerResult(
            total_score=95.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.3,
            zone_bonus=0, narrative=res.narrative, label="x", categories_firing=[],
        )
        n = _FakeNarrative(strength=1.0)
        assert rm.size_contracts(res, n) == 3

    def test_size_score_72_returns_1(self):
        rm = _make_rm()
        res = ScorerResult(
            total_score=72.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.6, category_count=2, confluence_mult=1.0,
            zone_bonus=0, narrative=None, label="x", categories_firing=[],
        )
        assert rm.size_contracts(res, _FakeNarrative(1.0)) == 1

    def test_size_vpin_toxic_returns_0(self):
        rm = _make_rm()
        res = ScorerResult(
            total_score=95.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.3,
            zone_bonus=0, narrative=None, label="x", categories_firing=[],
        )
        assert rm.size_contracts(res, _FakeNarrative(1.0), vpin=_FakeVPIN("TOXIC")) == 0

    def test_size_hmm_chaotic_returns_0(self):
        rm = _make_rm()
        res = ScorerResult(
            total_score=95.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.3,
            zone_bonus=0, narrative=None, label="x", categories_firing=[],
        )
        assert rm.size_contracts(res, _FakeNarrative(1.0), hmm_regime="CHAOTIC") == 0

    def test_size_type_b_low_score_returns_0(self):
        rm = _make_rm()
        res = ScorerResult(
            total_score=75.0, tier=SignalTier.TYPE_B, direction=1,
            engine_agreement=0.6, category_count=2, confluence_mult=1.0,
            zone_bonus=0, narrative=None, label="x", categories_firing=[],
        )
        assert rm.size_contracts(res, _FakeNarrative(1.0)) == 0


# ---------------------------------------------------------------------------
# Graduated drawdown tests
# ---------------------------------------------------------------------------

class TestGraduatedDrawdown:
    def test_at_minus_2R_rejects_type_b(self):
        rm = _make_rm()
        rm.record_trade(-200.0)  # -2R with default risk_per_trade_R=100
        res = _make_result(tier=SignalTier.TYPE_B)
        res = ScorerResult(
            total_score=85.0, tier=SignalTier.TYPE_B, direction=1,
            engine_agreement=0.8, category_count=3, confluence_mult=1.0,
            zone_bonus=0, narrative=None, label="x", categories_firing=[],
        )
        gate = rm.can_enter(res)
        assert gate.allowed is False
        assert "-2R" in gate.reason or "TYPE_B" in gate.reason

    def test_at_minus_3R_only_type_a_score_90_absorption(self):
        rm = _make_rm()
        rm.record_trade(-300.0)  # -3R
        # TYPE_A score 90 with absorption should pass
        ok = ScorerResult(
            total_score=90.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.2,
            zone_bonus=0, narrative=None, label="x", categories_firing=["absorption"],
        )
        assert rm.can_enter(ok).allowed is True
        # TYPE_A score 90 WITHOUT absorption fails
        no_abs = ScorerResult(
            total_score=90.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.2,
            zone_bonus=0, narrative=None, label="x", categories_firing=["imbalance"],
        )
        assert rm.can_enter(no_abs).allowed is False
        # TYPE_A score 85 fails
        low = ScorerResult(
            total_score=85.0, tier=SignalTier.TYPE_A, direction=1,
            engine_agreement=0.9, category_count=3, confluence_mult=1.2,
            zone_bonus=0, narrative=None, label="x", categories_firing=["absorption"],
        )
        assert rm.can_enter(low).allowed is False


# ---------------------------------------------------------------------------
# Heat management test
# ---------------------------------------------------------------------------

class _FakeOpenPos:
    def __init__(self, r_distance, contracts, entry_price=19000.0, stop_price=0.0):
        self.r_distance = r_distance
        self.contracts = contracts
        self.remaining_contracts = contracts
        self.entry_price = entry_price
        self.stop_price = stop_price


class TestHeatCap:
    def test_two_positions_cant_exceed_2R_combined(self):
        # With max_open_risk_usd=100.0, 2 positions of r_distance=1.0 * 1 contract * $50 = $50 each
        # total = $100 -> at cap. Adding more would exceed.
        cfg = ExecutionConfig(max_open_risk_usd=100.0)
        rm = RiskManager(cfg)
        open_pos = [
            _FakeOpenPos(r_distance=1.0, contracts=1),  # $50
            _FakeOpenPos(r_distance=1.5, contracts=1),  # $75 -> total $125 > $100
        ]
        gate = rm.can_enter(_make_result(), open_positions=open_pos)
        assert gate.allowed is False
        assert "Heat cap" in gate.reason or "open risk" in gate.reason.lower()

    def test_within_heat_cap_allows(self):
        cfg = ExecutionConfig(max_open_risk_usd=100.0)
        rm = RiskManager(cfg)
        open_pos = [_FakeOpenPos(r_distance=1.0, contracts=1)]  # $50 < $100
        gate = rm.can_enter(_make_result(), open_positions=open_pos)
        assert gate.allowed is True
