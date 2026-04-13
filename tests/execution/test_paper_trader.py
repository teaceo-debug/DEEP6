"""Tests for LiveGate, PaperStats, and PaperTrader (Plan 08-04)."""
from __future__ import annotations

import os
import pytest

from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_type_a_result(direction=1, categories=None) -> ScorerResult:
    return ScorerResult(
        total_score=85.0,
        tier=SignalTier.TYPE_A,
        direction=direction,
        engine_agreement=0.85,
        category_count=3,
        confluence_mult=1.25,
        zone_bonus=0.0,
        narrative=NarrativeType.ABSORPTION,
        label="TYPE_A LONG",
        categories_firing=categories or ["absorption", "exhaustion", "delta"],
    )


def _make_type_b_result(direction=1) -> ScorerResult:
    return ScorerResult(
        total_score=65.0,
        tier=SignalTier.TYPE_B,
        direction=direction,
        engine_agreement=0.7,
        category_count=2,
        confluence_mult=1.0,
        zone_bonus=0.0,
        narrative=NarrativeType.ABSORPTION,
        label="TYPE_B LONG",
        categories_firing=["absorption", "delta"],
    )


def _make_quiet_result() -> ScorerResult:
    return ScorerResult(
        total_score=10.0,
        tier=SignalTier.QUIET,
        direction=0,
        engine_agreement=0.2,
        category_count=0,
        confluence_mult=1.0,
        zone_bonus=0.0,
        narrative=NarrativeType.QUIET,
        label="QUIET",
        categories_firing=[],
    )


# ---------------------------------------------------------------------------
# LiveGate tests
# ---------------------------------------------------------------------------

class TestLiveGate:
    def test_record_trading_day_idempotent(self, tmp_path):
        from deep6.execution.paper_trader import LiveGate
        gate = LiveGate(str(tmp_path / "test.db"))
        gate.record_trading_day("2026-01-01")
        gate.record_trading_day("2026-01-01")  # duplicate — should be ignored
        assert gate.completed_days() == 1

    def test_gate_closed_at_29_days(self, tmp_path):
        from deep6.execution.paper_trader import LiveGate
        gate = LiveGate(str(tmp_path / "test.db"), required_days=30)
        for i in range(29):
            gate.record_trading_day(f"2026-01-{i + 1:02d}")
        assert gate.is_gate_open() is False

    def test_gate_open_at_30_days(self, tmp_path):
        from deep6.execution.paper_trader import LiveGate
        gate = LiveGate(str(tmp_path / "test.db"), required_days=30)
        for i in range(30):
            gate.record_trading_day(f"2026-01-{i + 1:02d}")
        assert gate.is_gate_open() is True

    def test_gate_open_above_30_days(self, tmp_path):
        from deep6.execution.paper_trader import LiveGate
        gate = LiveGate(str(tmp_path / "test.db"), required_days=30)
        for i in range(35):
            gate.record_trading_day(f"2026-02-{i + 1:02d}")
        assert gate.is_gate_open() is True

    def test_gate_persists_across_instances(self, tmp_path):
        from deep6.execution.paper_trader import LiveGate
        db = str(tmp_path / "test.db")
        gate1 = LiveGate(db, required_days=30)
        for i in range(30):
            gate1.record_trading_day(f"2026-03-{i + 1:02d}")
        # New instance reads same DB
        gate2 = LiveGate(db, required_days=30)
        assert gate2.completed_days() == 30
        assert gate2.is_gate_open() is True


# ---------------------------------------------------------------------------
# PaperStats tests
# ---------------------------------------------------------------------------

class TestPaperStats:
    def test_win_rate_no_trades(self):
        from deep6.execution.paper_trader import PaperStats
        stats = PaperStats()
        assert stats.win_rate == 0.0

    def test_paper_stats_win_rate(self):
        from deep6.execution.paper_trader import PaperStats
        stats = PaperStats()
        stats.record_trade(100.0)   # win
        stats.record_trade(50.0)    # win
        stats.record_trade(-80.0)   # loss
        assert stats.win_rate == pytest.approx(2 / 3)
        assert stats.wins == 2
        assert stats.losses == 1

    def test_paper_stats_max_drawdown(self):
        from deep6.execution.paper_trader import PaperStats
        stats = PaperStats()
        stats.record_trade(100.0)   # peak=100, dd=0
        stats.record_trade(-150.0)  # peak=100, total=-50, dd=150
        stats.record_trade(50.0)    # peak=100, total=0, dd=100 (still 150 from before)
        assert stats.max_drawdown == pytest.approx(150.0)

    def test_paper_stats_to_dict_serializable(self):
        from deep6.execution.paper_trader import PaperStats
        stats = PaperStats()
        stats.record_trade(100.0)
        d = stats.to_dict()
        import json
        # Should not raise
        serialized = json.dumps(d)
        assert "total_trades" in d
        assert "win_rate" in d
        assert "max_drawdown" in d
        # All values should be JSON primitives
        for v in d.values():
            assert isinstance(v, (int, float, str, bool, type(None)))

    def test_paper_stats_total_pnl_accumulates(self):
        from deep6.execution.paper_trader import PaperStats
        stats = PaperStats()
        stats.record_trade(100.0)
        stats.record_trade(-50.0)
        assert stats.total_pnl == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# PaperTrader tests
# ---------------------------------------------------------------------------

class TestPaperTrader:
    def _make_paper_trader(self, tmp_path, config=None):
        from deep6.execution.paper_trader import PaperTrader
        cfg = config or ExecutionConfig()
        db_path = str(tmp_path / "gate.db")
        events = []
        pt = PaperTrader(cfg, db_path, on_event=events.append)
        return pt, events

    def test_is_ready_for_live_false_initially(self, tmp_path):
        pt, _ = self._make_paper_trader(tmp_path)
        assert pt.is_ready_for_live is False

    def test_complete_bar_type_a_enters_position(self, tmp_path):
        pt, events = self._make_paper_trader(tmp_path)
        result = _make_type_a_result(direction=1)
        fired = pt.complete_bar(
            result=result,
            bar_close=19000.0,
            bar_high=19005.0,
            bar_low=18990.0,
            atr=20.0,
            date_str="2026-01-02",
        )
        # Should have at least opened a position (ENTRY event)
        from deep6.execution.position_manager import PositionEventType
        entry_events = [e for e in events if e.event_type == PositionEventType.ENTRY]
        assert len(entry_events) == 1

    def test_complete_bar_quiet_does_not_enter(self, tmp_path):
        pt, events = self._make_paper_trader(tmp_path)
        result = _make_quiet_result()
        pt.complete_bar(
            result=result,
            bar_close=19000.0,
            bar_high=19005.0,
            bar_low=18990.0,
            atr=20.0,
            date_str="2026-01-02",
        )
        from deep6.execution.position_manager import PositionEventType
        entry_events = [e for e in events if e.event_type == PositionEventType.ENTRY]
        assert len(entry_events) == 0

    def test_complete_bar_risk_gate_blocks_after_losses(self, tmp_path):
        cfg = ExecutionConfig(consecutive_loss_limit=3, pause_minutes=30.0)
        pt, events = self._make_paper_trader(tmp_path, config=cfg)
        # Manually simulate 3 consecutive losses to trigger pause
        for _ in range(3):
            pt.risk.record_trade(-100.0)
        result = _make_type_a_result(direction=1)
        pt.complete_bar(
            result=result,
            bar_close=19000.0,
            bar_high=19005.0,
            bar_low=18990.0,
            atr=20.0,
            date_str="2026-01-03",
        )
        from deep6.execution.position_manager import PositionEventType
        entry_events = [e for e in events if e.event_type == PositionEventType.ENTRY]
        assert len(entry_events) == 0

    def test_slippage_long_fill_above_entry(self, tmp_path):
        from deep6.execution.paper_trader import PaperTrader
        from deep6.execution.config import ExecutionDecision, OrderSide
        cfg = ExecutionConfig(paper_slippage_fixed_ticks=1, paper_slippage_random_ticks=1)
        pt, _ = self._make_paper_trader(tmp_path, config=cfg)

        decision = ExecutionDecision(
            action="ENTER",
            reason="test",
            side=OrderSide.LONG,
            entry_price=19000.0,
            stop_price=18990.0,
            target_price=19020.0,
            stop_ticks=40.0,
            signal_score=80.0,
            signal_tier="TYPE_A",
        )
        # Run many times to cover random component
        for _ in range(20):
            fill = pt._simulate_fill(decision, tick_size=0.25)
            assert fill >= 19000.0, f"LONG fill {fill} should be >= entry 19000.0"

    def test_slippage_short_fill_below_entry(self, tmp_path):
        from deep6.execution.config import ExecutionDecision, OrderSide
        cfg = ExecutionConfig(paper_slippage_fixed_ticks=1, paper_slippage_random_ticks=1)
        pt, _ = self._make_paper_trader(tmp_path, config=cfg)

        decision = ExecutionDecision(
            action="ENTER",
            reason="test",
            side=OrderSide.SHORT,
            entry_price=19000.0,
            stop_price=19010.0,
            target_price=18980.0,
            stop_ticks=40.0,
            signal_score=80.0,
            signal_tier="TYPE_A",
        )
        for _ in range(20):
            fill = pt._simulate_fill(decision, tick_size=0.25)
            assert fill <= 19000.0, f"SHORT fill {fill} should be <= entry 19000.0"

    def test_stats_updated_on_position_close(self, tmp_path):
        """Open a position then hit the stop to close it — stats should update."""
        cfg = ExecutionConfig(max_hold_bars=10)
        pt, events = self._make_paper_trader(tmp_path, config=cfg)
        # Open a LONG position
        result = _make_type_a_result(direction=1)
        pt.complete_bar(
            result=result,
            bar_close=19000.0,
            bar_high=19005.0,
            bar_low=18995.0,
            atr=20.0,
            date_str="2026-01-04",
        )
        assert pt.positions.position_count == 1
        open_pos = pt.positions.positions[0]

        # Hit the stop on the next bar
        stop = open_pos.stop_price
        bar_low_hit = stop - 0.25  # below stop
        pt.complete_bar(
            result=_make_quiet_result(),
            bar_close=stop - 0.5,
            bar_high=stop + 0.5,
            bar_low=bar_low_hit,
            atr=20.0,
            date_str="2026-01-05",
        )
        assert pt.paper_stats.total_trades == 1

    def test_record_trading_day_called_on_complete_bar(self, tmp_path):
        pt, _ = self._make_paper_trader(tmp_path)
        result = _make_quiet_result()
        pt.complete_bar(
            result=result,
            bar_close=19000.0,
            bar_high=19005.0,
            bar_low=18995.0,
            atr=20.0,
            date_str="2026-01-10",
        )
        assert pt.live_gate.completed_days() == 1

    def test_reset_daily_clears_risk_state(self, tmp_path):
        pt, _ = self._make_paper_trader(tmp_path)
        pt.risk.record_trade(-300.0)
        assert pt.risk.state.daily_pnl == -300.0
        pt.reset_daily()
        assert pt.risk.state.daily_pnl == 0.0
