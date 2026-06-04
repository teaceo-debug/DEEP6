"""Fitness evaluator for DEEP6 backtest strategies.

Splits sessions into IS/OOS, computes performance metrics,
and determines if a strategy passes fitness criteria (>55% WR, >1.5 R:R).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# NQ constants
NQ_TICK_SIZE = 0.25
NQ_TICK_VALUE = 5.00
COMMISSION_PER_RT = 4.12
SLIPPAGE_TICKS = 1
SLIPPAGE_DOLLARS = SLIPPAGE_TICKS * NQ_TICK_VALUE  # $5.00


@dataclass
class Trade:
    """A single completed trade with P&L already computed (after costs)."""

    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    entry_time: int  # nanoseconds
    exit_time: int
    exit_reason: str  # 'target', 'stop', 'max_bars', 'session_end', 'level_exit'
    bars_held: int
    pnl: float  # Net P&L after commission + slippage
    split: str = "is"  # 'is' or 'oos'
    date: str = ""
    config_hash: str = ""


def compute_trade_pnl(direction: str, entry_price: float, exit_price: float) -> float:
    """Compute net P&L for a trade including commission and slippage."""
    if direction == "LONG":
        raw_pnl = (exit_price - entry_price) / NQ_TICK_SIZE * NQ_TICK_VALUE
    else:
        raw_pnl = (entry_price - exit_price) / NQ_TICK_SIZE * NQ_TICK_VALUE
    return raw_pnl - COMMISSION_PER_RT - SLIPPAGE_DOLLARS


@dataclass
class Metrics:
    """Performance metrics for a set of trades."""

    win_rate: float = 0.0
    avg_rr: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_dollars: float = 0.0
    total_pnl: float = 0.0
    trade_count: int = 0
    avg_bars_held: float = 0.0
    avg_pnl_per_trade: float = 0.0


@dataclass
class FitnessResult:
    """Result of fitness evaluation across IS and OOS splits."""

    passed: bool
    score: float  # Composite score 0-1
    is_metrics: Metrics = field(default_factory=Metrics)
    oos_metrics: Metrics = field(default_factory=Metrics)
    rejection_reasons: list[str] = field(default_factory=list)


def split_sessions(
    session_dates: list[str], is_ratio: float = 0.68
) -> tuple[list[str], list[str]]:
    """Split session dates into IS and OOS by date order."""
    if not session_dates:
        return [], []
    sorted_dates = sorted(session_dates)
    split_idx = max(1, int(len(sorted_dates) * is_ratio))
    return sorted_dates[:split_idx], sorted_dates[split_idx:]


def compute_metrics(trades: list[Trade]) -> Metrics:
    """Compute performance metrics from a list of trades."""
    if not trades:
        return Metrics()

    pnls = [t.pnl for t in trades]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    win_rate = len(winners) / len(pnls) if pnls else 0.0

    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 1.0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else 0.0

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else float("inf") if gross_profit > 0 else 0.0
    )

    total_pnl = sum(pnls)
    avg_pnl = total_pnl / len(pnls)

    # Sharpe ratio (per-trade, annualized with sqrt(252))
    if len(pnls) > 1:
        std = math.sqrt(sum((p - avg_pnl) ** 2 for p in pnls) / (len(pnls) - 1))
        sharpe = (avg_pnl / std) * math.sqrt(252) if std > 0 else 0.0
    else:
        sharpe = 0.0

    # Max drawdown (cumulative equity curve)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    avg_bars = sum(t.bars_held for t in trades) / len(trades)

    return Metrics(
        win_rate=win_rate,
        avg_rr=avg_rr,
        profit_factor=min(profit_factor, 99.0),  # Cap infinite profit factor
        sharpe_ratio=sharpe,
        max_drawdown_dollars=max_dd,
        total_pnl=total_pnl,
        trade_count=len(trades),
        avg_bars_held=avg_bars,
        avg_pnl_per_trade=avg_pnl,
    )


def evaluate_fitness(
    is_metrics: Metrics, oos_metrics: Metrics, min_trades: int = 30
) -> FitnessResult:
    """Evaluate whether a strategy meets fitness criteria on both IS and OOS."""
    rejection_reasons: list[str] = []

    # Minimum trades check (IS)
    if is_metrics.trade_count < min_trades:
        rejection_reasons.append(
            f"Insufficient IS trades: {is_metrics.trade_count} < {min_trades}"
        )

    # OOS minimum (prorated: at least 32% of IS minimum)
    oos_min = max(5, int(min_trades * 0.32))
    if oos_metrics.trade_count < oos_min:
        rejection_reasons.append(
            f"Insufficient OOS trades: {oos_metrics.trade_count} < {oos_min}"
        )

    # IS fitness criteria
    if is_metrics.win_rate < 0.55:
        rejection_reasons.append(f"IS win_rate {is_metrics.win_rate:.1%} < 55%")
    if is_metrics.avg_rr < 1.5:
        rejection_reasons.append(f"IS avg_rr {is_metrics.avg_rr:.2f} < 1.5")

    # OOS fitness criteria
    if oos_metrics.win_rate < 0.55:
        rejection_reasons.append(f"OOS win_rate {oos_metrics.win_rate:.1%} < 55%")
    if oos_metrics.avg_rr < 1.5:
        rejection_reasons.append(f"OOS avg_rr {oos_metrics.avg_rr:.2f} < 1.5")

    passed = len(rejection_reasons) == 0

    # Composite score (weighted)
    oos_dd_pct = min(
        oos_metrics.max_drawdown_dollars / max(abs(oos_metrics.total_pnl), 1), 1.0
    )
    score = (
        oos_metrics.win_rate * 0.30
        + min(oos_metrics.avg_rr / 5.0, 1.0) * 0.30
        + min(oos_metrics.profit_factor / 10.0, 1.0) * 0.20
        + (1.0 - oos_dd_pct) * 0.20
    )

    return FitnessResult(
        passed=passed,
        score=round(score, 4),
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        rejection_reasons=rejection_reasons,
    )


def compare_strategies(results: list[FitnessResult]) -> list[FitnessResult]:
    """Rank strategies by composite score (passed strategies first, then by score)."""
    return sorted(results, key=lambda r: (r.passed, r.score), reverse=True)
