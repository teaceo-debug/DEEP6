"""Tests for deep6.backtest.fitness module."""

from __future__ import annotations

import math

import pytest

from deep6.backtest.fitness import (
    COMMISSION_PER_RT,
    SLIPPAGE_DOLLARS,
    FitnessResult,
    Metrics,
    Trade,
    compare_strategies,
    compute_metrics,
    compute_trade_pnl,
    evaluate_fitness,
    split_sessions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(
    direction: str = "LONG",
    entry: float = 20000.0,
    exit_price: float = 20010.0,
    exit_reason: str = "target",
    bars_held: int = 5,
    split: str = "is",
    date: str = "2026-03-17",
) -> Trade:
    pnl = compute_trade_pnl(direction, entry, exit_price)
    return Trade(
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        entry_time=0,
        exit_time=1,
        exit_reason=exit_reason,
        bars_held=bars_held,
        pnl=pnl,
        split=split,
        date=date,
    )


# ---------------------------------------------------------------------------
# Transaction cost tests
# ---------------------------------------------------------------------------

class TestComputeTradePnl:
    def test_long_winner(self) -> None:
        pnl = compute_trade_pnl("LONG", 20000, 20010)
        # raw = 10/0.25*5 = $200, net = 200 - 4.12 - 5.00 = $190.88
        assert abs(pnl - 190.88) < 0.01

    def test_long_loser(self) -> None:
        pnl = compute_trade_pnl("LONG", 20000, 19995)
        # raw = -5/0.25*5 = -$100, net = -100 - 4.12 - 5.00 = -$109.12
        assert abs(pnl - (-109.12)) < 0.01

    def test_short_winner(self) -> None:
        pnl = compute_trade_pnl("SHORT", 20010, 20000)
        assert abs(pnl - 190.88) < 0.01

    def test_short_loser(self) -> None:
        pnl = compute_trade_pnl("SHORT", 20000, 20005)
        # raw = -5/0.25*5 = -$100, net = -$109.12
        assert abs(pnl - (-109.12)) < 0.01

    def test_breakeven_is_negative(self) -> None:
        pnl = compute_trade_pnl("LONG", 20000, 20000)
        # raw = 0, net = -$9.12
        assert abs(pnl - (-COMMISSION_PER_RT - SLIPPAGE_DOLLARS)) < 0.01


# ---------------------------------------------------------------------------
# Known metrics test (10 trades: 6 winners, 4 losers)
# ---------------------------------------------------------------------------

class TestComputeMetrics:
    @pytest.fixture()
    def ten_trades(self) -> list[Trade]:
        trades: list[Trade] = []
        for _ in range(6):
            trades.append(_make_trade(exit_price=20010.0, exit_reason="target"))
        for _ in range(4):
            trades.append(_make_trade(exit_price=19995.0, exit_reason="stop"))
        return trades

    def test_win_rate(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        assert abs(m.win_rate - 0.60) < 0.01

    def test_avg_rr(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        # avg_win=190.88, avg_loss=109.12, rr=1.749...
        assert abs(m.avg_rr - (190.88 / 109.12)) < 0.01

    def test_profit_factor(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        expected_pf = (6 * 190.88) / (4 * 109.12)
        assert abs(m.profit_factor - expected_pf) < 0.05

    def test_total_pnl(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        expected = 6 * 190.88 + 4 * (-109.12)
        assert abs(m.total_pnl - expected) < 0.10

    def test_trade_count(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        assert m.trade_count == 10

    def test_avg_bars_held(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        assert abs(m.avg_bars_held - 5.0) < 0.01

    def test_sharpe_positive(self, ten_trades: list[Trade]) -> None:
        m = compute_metrics(ten_trades)
        assert m.sharpe_ratio != 0.0

    def test_empty_trades(self) -> None:
        m = compute_metrics([])
        assert m.trade_count == 0
        assert m.win_rate == 0.0

    def test_all_winners(self) -> None:
        trades = [_make_trade(exit_price=20010.0) for _ in range(5)]
        m = compute_metrics(trades)
        assert m.win_rate == 1.0
        assert m.max_drawdown_dollars == 0.0

    def test_single_trade(self) -> None:
        trades = [_make_trade(exit_price=20010.0)]
        m = compute_metrics(trades)
        assert m.trade_count == 1
        assert m.sharpe_ratio == 0.0  # Can't compute std with 1 sample


# ---------------------------------------------------------------------------
# Split sessions
# ---------------------------------------------------------------------------

class TestSplitSessions:
    def test_ten_dates(self) -> None:
        dates = [f"2026-03-{d:02d}" for d in range(1, 11)]
        is_dates, oos_dates = split_sessions(dates)
        assert len(is_dates) == 6
        assert len(oos_dates) == 4
        assert is_dates[-1] < oos_dates[0]

    def test_empty(self) -> None:
        is_dates, oos_dates = split_sessions([])
        assert is_dates == []
        assert oos_dates == []

    def test_single_date(self) -> None:
        is_dates, oos_dates = split_sessions(["2026-01-01"])
        assert len(is_dates) == 1
        assert len(oos_dates) == 0

    def test_unsorted_input(self) -> None:
        dates = ["2026-03-05", "2026-03-01", "2026-03-10", "2026-03-03"]
        is_dates, oos_dates = split_sessions(dates)
        assert is_dates == sorted(is_dates)
        assert is_dates[-1] < oos_dates[0]

    def test_custom_ratio(self) -> None:
        dates = [f"2026-03-{d:02d}" for d in range(1, 11)]
        is_dates, oos_dates = split_sessions(dates, is_ratio=0.50)
        assert len(is_dates) == 5
        assert len(oos_dates) == 5


# ---------------------------------------------------------------------------
# Evaluate fitness
# ---------------------------------------------------------------------------

class TestEvaluateFitness:
    def test_passes_when_criteria_met(self) -> None:
        is_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=3.0,
            trade_count=50, total_pnl=1000.0,
        )
        oos_m = Metrics(
            win_rate=0.58, avg_rr=1.8, profit_factor=2.5,
            trade_count=20, total_pnl=500.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert r.passed
        assert r.score > 0
        assert r.rejection_reasons == []

    def test_rejects_insufficient_is_trades(self) -> None:
        is_m = Metrics(
            win_rate=0.70, avg_rr=2.0, profit_factor=3.0,
            trade_count=20, total_pnl=500.0,
        )
        oos_m = Metrics(
            win_rate=0.65, avg_rr=1.8, profit_factor=2.5,
            trade_count=8, total_pnl=200.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert not r.passed
        assert any("Insufficient IS" in reason for reason in r.rejection_reasons)

    def test_rejects_insufficient_oos_trades(self) -> None:
        is_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=3.0,
            trade_count=50, total_pnl=1000.0,
        )
        oos_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=2.5,
            trade_count=3, total_pnl=100.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert not r.passed
        assert any("Insufficient OOS" in reason for reason in r.rejection_reasons)

    def test_rejects_low_win_rate(self) -> None:
        is_m = Metrics(
            win_rate=0.50, avg_rr=2.0, profit_factor=2.0,
            trade_count=50, total_pnl=500.0,
        )
        oos_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=2.5,
            trade_count=20, total_pnl=300.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert not r.passed
        assert any("IS win_rate" in reason for reason in r.rejection_reasons)

    def test_rejects_low_avg_rr(self) -> None:
        is_m = Metrics(
            win_rate=0.60, avg_rr=1.2, profit_factor=2.0,
            trade_count=50, total_pnl=500.0,
        )
        oos_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=2.5,
            trade_count=20, total_pnl=300.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert not r.passed
        assert any("IS avg_rr" in reason for reason in r.rejection_reasons)

    def test_rejects_oos_low_win_rate(self) -> None:
        is_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=3.0,
            trade_count=50, total_pnl=1000.0,
        )
        oos_m = Metrics(
            win_rate=0.40, avg_rr=2.0, profit_factor=1.5,
            trade_count=20, total_pnl=200.0,
        )
        r = evaluate_fitness(is_m, oos_m, min_trades=30)
        assert not r.passed
        assert any("OOS win_rate" in reason for reason in r.rejection_reasons)

    def test_score_range(self) -> None:
        is_m = Metrics(
            win_rate=0.60, avg_rr=2.0, profit_factor=3.0,
            trade_count=50, total_pnl=1000.0,
        )
        oos_m = Metrics(
            win_rate=0.58, avg_rr=1.8, profit_factor=2.5,
            trade_count=20, total_pnl=500.0,
        )
        r = evaluate_fitness(is_m, oos_m)
        assert 0.0 <= r.score <= 1.0


# ---------------------------------------------------------------------------
# Compare strategies
# ---------------------------------------------------------------------------

class TestCompareStrategies:
    def test_passed_first(self) -> None:
        passed = FitnessResult(passed=True, score=0.5)
        failed = FitnessResult(passed=False, score=0.9)
        ranked = compare_strategies([failed, passed])
        assert ranked[0].passed is True

    def test_sorted_by_score(self) -> None:
        a = FitnessResult(passed=True, score=0.8)
        b = FitnessResult(passed=True, score=0.6)
        c = FitnessResult(passed=True, score=0.9)
        ranked = compare_strategies([a, b, c])
        assert ranked[0].score == 0.9
        assert ranked[1].score == 0.8
        assert ranked[2].score == 0.6

    def test_empty_list(self) -> None:
        assert compare_strategies([]) == []
