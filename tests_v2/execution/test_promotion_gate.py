from __future__ import annotations

import pytest

from deep6v2.execution.promotion_gate import PromotionConfig, PromotionGate, PromotionStatus


@pytest.fixture
def gate() -> PromotionGate:
    return PromotionGate()


@pytest.fixture
def lenient_gate() -> PromotionGate:
    return PromotionGate(config=PromotionConfig(required_sessions=5, min_win_rate=0.30))


class TestPromotionGateIneligible:
    def test_not_eligible_with_zero_sessions(self, gate: PromotionGate) -> None:
        status = gate.evaluate()
        assert status.eligible is False
        assert status.sessions_completed == 0
        assert any("need_30_sessions" in r for r in status.blocking_reasons)

    def test_not_eligible_with_few_sessions(self, gate: PromotionGate) -> None:
        for _ in range(10):
            gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-500.0)
        status = gate.evaluate()
        assert status.eligible is False
        assert "need_30_sessions_have_10" in status.blocking_reasons

    def test_not_eligible_with_negative_pnl(self, gate: PromotionGate) -> None:
        for _ in range(30):
            gate.record_session(pnl=-50.0, win_rate=0.60, max_dd=-500.0)
        status = gate.evaluate()
        assert status.eligible is False
        assert "negative_cumulative_pnl" in status.blocking_reasons

    def test_not_eligible_with_excessive_drawdown(self, gate: PromotionGate) -> None:
        for _ in range(30):
            gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-3000.0)
        status = gate.evaluate()
        assert status.eligible is False
        assert "max_drawdown_exceeded" in status.blocking_reasons

    def test_not_eligible_with_low_win_rate(self, gate: PromotionGate) -> None:
        for _ in range(30):
            gate.record_session(pnl=100.0, win_rate=0.20, max_dd=-500.0)
        status = gate.evaluate()
        assert status.eligible is False
        assert "win_rate_below_minimum" in status.blocking_reasons

    def test_not_eligible_with_crash(self, gate: PromotionGate) -> None:
        for i in range(30):
            gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-500.0, crashed=(i == 15))
        status = gate.evaluate()
        assert status.eligible is False
        assert "session_crash_detected" in status.blocking_reasons


class TestPromotionGateEligible:
    def test_eligible_with_30_good_sessions(self, gate: PromotionGate) -> None:
        for _ in range(30):
            gate.record_session(pnl=100.0, win_rate=0.55, max_dd=-500.0)
        status = gate.evaluate()
        assert status.eligible is True
        assert status.blocking_reasons == []
        assert status.sessions_completed == 30
        assert status.cumulative_pnl == pytest.approx(3000.0)
        assert status.crash_free is True
        assert status.risk_gates_exercised is True

    def test_eligible_with_custom_config(self, lenient_gate: PromotionGate) -> None:
        for _ in range(5):
            lenient_gate.record_session(pnl=50.0, win_rate=0.40, max_dd=-1000.0)
        status = lenient_gate.evaluate()
        assert status.eligible is True


class TestPromotionGateStatus:
    def test_status_fields_populated(self, gate: PromotionGate) -> None:
        gate.record_session(pnl=200.0, win_rate=0.70, max_dd=-300.0)
        gate.record_session(pnl=-50.0, win_rate=0.40, max_dd=-800.0)
        status = gate.evaluate()
        assert status.sessions_completed == 2
        assert status.cumulative_pnl == pytest.approx(150.0)
        assert status.max_drawdown == pytest.approx(-800.0)
        assert status.win_rate == pytest.approx(0.55)
        assert status.crash_free is True

    def test_max_drawdown_uses_worst_session(self, gate: PromotionGate) -> None:
        gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-200.0)
        gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-1500.0)
        gate.record_session(pnl=100.0, win_rate=0.60, max_dd=-500.0)
        status = gate.evaluate()
        assert status.max_drawdown == pytest.approx(-1500.0)

    def test_multiple_blocking_reasons(self, gate: PromotionGate) -> None:
        for _ in range(5):
            gate.record_session(pnl=-200.0, win_rate=0.10, max_dd=-5000.0, crashed=True)
        status = gate.evaluate()
        assert status.eligible is False
        assert len(status.blocking_reasons) >= 4  # sessions, pnl, drawdown, win_rate, crash
