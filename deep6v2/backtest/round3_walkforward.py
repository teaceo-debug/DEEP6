"""Round 3: walk-forward validation and equity curve analysis."""

from __future__ import annotations

import itertools
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from deep6v2.backtest.param_sweep import DEFAULT_CSV, ScoredBar, SweepParams, SweepResult, scan_signals, simulate_trades
from deep6v2.types.signal import Direction


@dataclass(frozen=True, slots=True)
class Period:
    name: str
    start: date
    end: date
    role: str

    def contains(self, session_date: date) -> bool:
        return self.start <= session_date <= self.end


@dataclass(frozen=True, slots=True)
class Fold:
    name: str
    train_periods: tuple[str, ...]
    test_periods: tuple[str, ...]
    note: str = ""


@dataclass(frozen=True, slots=True)
class DetailedTrade:
    session_date: date
    entry_bar_index: int
    exit_bar_index: int
    direction: str
    entry_price: float
    exit_price: float
    pnl: float
    bars_held: int
    exit_reason: str


PERIODS: tuple[Period, ...] = (
    Period("Q1_2025_IS", date(2025, 1, 1), date(2025, 3, 31), "IS"),
    Period("Q2_2025_OOS", date(2025, 4, 1), date(2025, 6, 30), "OOS"),
    Period("Q3_2025_IS", date(2025, 7, 1), date(2025, 9, 30), "IS"),
    Period("Q4_2025_OOS", date(2025, 10, 1), date(2025, 12, 31), "OOS"),
    Period("Q5_2026_OOS", date(2026, 1, 1), date(2026, 4, 30), "OOS"),
)

FOLDS: tuple[Fold, ...] = (
    Fold("Fold 1", ("Q1_2025_IS",), ("Q2_2025_OOS",), "Strict next-period walk-forward."),
    Fold("Fold 2", ("Q3_2025_IS",), ("Q4_2025_OOS",), "Strict next-period walk-forward."),
    Fold("Fold 3", ("Q3_2025_IS",), ("Q5_2026_OOS",), "Extended terminal holdout using the latest in-sample winner."),
)

SCORE_MINS = [72, 78, 82, 86, 90, 94]
STOP_MULTS = [1.5, 2.0, 2.5, 3.0]
RR_RATIOS = [1.5, 2.0, 2.5, 3.0]
COOLDOWNS = [0, 5, 10, 20]
MIN_SIGNALS = [1, 2, 3]
DOLLARS_PER_POINT = 20.0


def build_param_grid() -> list[SweepParams]:
    return [
        SweepParams(score_min=sc, stop_mult=st, rr_ratio=rr, cooldown=cd, min_signals=ms)
        for sc, st, rr, cd, ms in itertools.product(
            SCORE_MINS,
            STOP_MULTS,
            RR_RATIOS,
            COOLDOWNS,
            MIN_SIGNALS,
        )
    ]


def subset_sessions_by_period_names(
    sessions: dict[date, list[ScoredBar]],
    period_names: tuple[str, ...],
) -> dict[date, list[ScoredBar]]:
    selected: dict[date, list[ScoredBar]] = {}
    wanted = {period.name for period in PERIODS if period.name in period_names}
    for session_date, bars in sessions.items():
        for period in PERIODS:
            if period.name in wanted and period.contains(session_date):
                selected[session_date] = bars
                break
    return selected


def choose_best_result(results: list[SweepResult]) -> SweepResult:
    viable = [result for result in results if result.trades >= 20]
    if not viable:
        viable = [result for result in results if result.trades >= 5]
    if not viable:
        viable = [result for result in results if result.trades > 0]
    if not viable:
        raise RuntimeError("No parameter combination produced any trades in-sample.")

    profitable = [result for result in viable if result.profit_factor > 1.0]
    if profitable:
        return max(
            profitable,
            key=lambda result: (
                result.sharpe,
                result.total_pnl,
                result.win_rate,
                result.max_drawdown,
            ),
        )

    return max(
        viable,
        key=lambda result: (
            result.total_pnl,
            result.sharpe,
            result.win_rate,
            result.max_drawdown,
        ),
    )


def simulate_trades_detailed(
    sessions: dict[date, list[ScoredBar]],
    params: SweepParams,
) -> tuple[SweepResult, list[DetailedTrade]]:
    all_pnl: list[float] = []
    sessions_active = 0
    trades: list[DetailedTrade] = []

    for session_date, bars in sessions.items():
        in_trade = False
        entry_price = 0.0
        entry_dir = Direction.NEUTRAL
        stop_px = 0.0
        target_px = 0.0
        entry_bar = 0
        armed = False
        armed_dir = Direction.NEUTRAL
        bars_since_trade = 999
        session_traded = False

        for i, sb in enumerate(bars):
            bar = sb.bar

            if in_trade:
                if entry_dir == Direction.BULLISH:
                    if bar.low <= stop_px:
                        pnl = (stop_px - entry_price) * DOLLARS_PER_POINT
                        all_pnl.append(pnl)
                        trades.append(
                            DetailedTrade(
                                session_date=session_date,
                                entry_bar_index=entry_bar,
                                exit_bar_index=i,
                                direction="LONG",
                                entry_price=entry_price,
                                exit_price=stop_px,
                                pnl=pnl,
                                bars_held=max(1, i - entry_bar + 1),
                                exit_reason="stop",
                            )
                        )
                        in_trade = False
                        bars_since_trade = 0
                    elif bar.high >= target_px:
                        pnl = (target_px - entry_price) * DOLLARS_PER_POINT
                        all_pnl.append(pnl)
                        trades.append(
                            DetailedTrade(
                                session_date=session_date,
                                entry_bar_index=entry_bar,
                                exit_bar_index=i,
                                direction="LONG",
                                entry_price=entry_price,
                                exit_price=target_px,
                                pnl=pnl,
                                bars_held=max(1, i - entry_bar + 1),
                                exit_reason="target",
                            )
                        )
                        in_trade = False
                        bars_since_trade = 0
                else:
                    if bar.high >= stop_px:
                        pnl = (entry_price - stop_px) * DOLLARS_PER_POINT
                        all_pnl.append(pnl)
                        trades.append(
                            DetailedTrade(
                                session_date=session_date,
                                entry_bar_index=entry_bar,
                                exit_bar_index=i,
                                direction="SHORT",
                                entry_price=entry_price,
                                exit_price=stop_px,
                                pnl=pnl,
                                bars_held=max(1, i - entry_bar + 1),
                                exit_reason="stop",
                            )
                        )
                        in_trade = False
                        bars_since_trade = 0
                    elif bar.low <= target_px:
                        pnl = (entry_price - target_px) * DOLLARS_PER_POINT
                        all_pnl.append(pnl)
                        trades.append(
                            DetailedTrade(
                                session_date=session_date,
                                entry_bar_index=entry_bar,
                                exit_bar_index=i,
                                direction="SHORT",
                                entry_price=entry_price,
                                exit_price=target_px,
                                pnl=pnl,
                                bars_held=max(1, i - entry_bar + 1),
                                exit_reason="target",
                            )
                        )
                        in_trade = False
                        bars_since_trade = 0

                if in_trade and i == len(bars) - 1:
                    if entry_dir == Direction.BULLISH:
                        pnl = (bar.close - entry_price) * DOLLARS_PER_POINT
                        direction = "LONG"
                    else:
                        pnl = (entry_price - bar.close) * DOLLARS_PER_POINT
                        direction = "SHORT"
                    all_pnl.append(pnl)
                    trades.append(
                        DetailedTrade(
                            session_date=session_date,
                            entry_bar_index=entry_bar,
                            exit_bar_index=i,
                            direction=direction,
                            entry_price=entry_price,
                            exit_price=bar.close,
                            pnl=pnl,
                            bars_held=max(1, i - entry_bar + 1),
                            exit_reason="forced_close",
                        )
                    )
                    in_trade = False
                continue

            bars_since_trade += 1

            if armed:
                armed = False
                if not in_trade and bars_since_trade >= params.cooldown:
                    in_trade = True
                    session_traded = True
                    entry_price = bar.open
                    entry_dir = armed_dir
                    entry_bar = i

                    recent = bars[max(0, i - 14):i]
                    if recent:
                        atr = sum(recent_bar.bar.high - recent_bar.bar.low for recent_bar in recent) / len(recent)
                    else:
                        atr = 5.0
                    atr = max(atr, 0.5)

                    stop_dist = max(5.0, params.stop_mult * atr)
                    target_dist = stop_dist * params.rr_ratio

                    if entry_dir == Direction.BULLISH:
                        stop_px = entry_price - stop_dist
                        target_px = entry_price + target_dist
                    else:
                        stop_px = entry_price + stop_dist
                        target_px = entry_price - target_dist
                continue

            if (
                not in_trade
                and sb.score >= params.score_min
                and sb.direction in (Direction.BULLISH, Direction.BEARISH)
                and sb.n_signals >= params.min_signals
                and bars_since_trade >= params.cooldown
            ):
                armed = True
                armed_dir = sb.direction

        if session_traded:
            sessions_active += 1

    if not all_pnl:
        return (
            SweepResult(
                params=params,
                trades=0,
                wins=0,
                losses=0,
                total_pnl=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                sharpe=0.0,
                sessions_with_trades=0,
            ),
            trades,
        )

    wins_pnl = [pnl for pnl in all_pnl if pnl > 0]
    losses_pnl = [pnl for pnl in all_pnl if pnl <= 0]
    total = sum(all_pnl)
    peak = 0.0
    drawdown = 0.0
    running = 0.0
    for pnl in all_pnl:
        running += pnl
        peak = max(peak, running)
        drawdown = min(drawdown, running - peak)

    mean = total / len(all_pnl)
    std = (sum((pnl - mean) ** 2 for pnl in all_pnl) / len(all_pnl)) ** 0.5 if len(all_pnl) > 1 else 0.0

    result = SweepResult(
        params=params,
        trades=len(all_pnl),
        wins=len(wins_pnl),
        losses=len(losses_pnl),
        total_pnl=total,
        avg_win=sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0.0,
        avg_loss=sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0.0,
        profit_factor=abs(sum(wins_pnl) / sum(losses_pnl)) if losses_pnl and sum(losses_pnl) != 0 else 0.0,
        max_drawdown=drawdown,
        win_rate=len(wins_pnl) / len(all_pnl) * 100.0,
        sharpe=(mean / std * (252 ** 0.5)) if std > 0 else 0.0,
        sessions_with_trades=sessions_active,
    )
    return result, trades


def format_params(params: SweepParams) -> str:
    return (
        f"score_min={params.score_min:.0f}, stop_mult={params.stop_mult:.1f}, "
        f"rr_ratio={params.rr_ratio:.1f}, cooldown={params.cooldown}, min_signals={params.min_signals}"
    )


def sweep_subset(sessions: dict[date, list[ScoredBar]], param_grid: list[SweepParams]) -> list[SweepResult]:
    return [simulate_trades(sessions, params) for params in param_grid]


def run_walk_forward(sessions: dict[date, list[ScoredBar]]) -> None:
    print("=" * 100)
    print("ANALYSIS A: WALK-FORWARD VALIDATION")
    print("=" * 100)
    print("Selection rule: same Round 1 grid, best profitable Sharpe with trade-count fallback.")
    print()

    param_grid = build_param_grid()

    for period in PERIODS:
        subset = subset_sessions_by_period_names(sessions, (period.name,))
        print(
            f"{period.name:<12} {period.role:<3} "
            f"{period.start.isoformat()} -> {period.end.isoformat()} : {len(subset):>3} sessions"
        )

    print()
    for fold in FOLDS:
        train_sessions = subset_sessions_by_period_names(sessions, fold.train_periods)
        test_sessions = subset_sessions_by_period_names(sessions, fold.test_periods)
        train_results = sweep_subset(train_sessions, param_grid)
        best_train = choose_best_result(train_results)
        best_test = simulate_trades(test_sessions, best_train.params)

        print("-" * 100)
        print(f"{fold.name}: train {', '.join(fold.train_periods)} -> test {', '.join(fold.test_periods)}")
        if fold.note:
            print(f"Note: {fold.note}")
        print(f"Best in-sample config: {format_params(best_train.params)}")
        print(
            "In-sample : "
            f"trades={best_train.trades}, win_rate={best_train.win_rate:.1f}%, "
            f"pnl=${best_train.total_pnl:,.0f}, pf={best_train.profit_factor:.2f}, sharpe={best_train.sharpe:.2f}"
        )
        print(
            "Out-of-sample: "
            f"trades={best_test.trades}, win_rate={best_test.win_rate:.1f}%, "
            f"pnl=${best_test.total_pnl:,.0f}, pf={best_test.profit_factor:.2f}, sharpe={best_test.sharpe:.2f}"
        )
        delta = best_test.total_pnl - best_train.total_pnl
        sign = "+" if delta >= 0 else ""
        print(f"PnL delta (OOS - IS): {sign}${delta:,.0f}")

    print()


def build_equity_curve_lines(trades: list[DetailedTrade], width: int = 60) -> list[str]:
    if not trades:
        return ["No trades."]

    equity = []
    running = 0.0
    for trade in trades:
        running += trade.pnl
        equity.append(running)

    min_eq = min(equity)
    max_eq = max(equity)
    span = max(max_eq - min_eq, 1.0)

    lines: list[str] = []
    for idx, (trade, eq) in enumerate(zip(trades, equity), start=1):
        pos = int(round((eq - min_eq) / span * (width - 1)))
        bar = [" "] * width
        bar[pos] = "*"
        lines.append(
            f"{idx:03d} {trade.session_date.isoformat()} pnl={trade.pnl:>9.0f} eq={eq:>10.0f} |{''.join(bar)}|"
        )
    return lines


def longest_streaks(trades: list[DetailedTrade]) -> tuple[int, int]:
    longest_wins = 0
    longest_losses = 0
    current_wins = 0
    current_losses = 0
    for trade in trades:
        if trade.pnl > 0:
            current_wins += 1
            current_losses = 0
        else:
            current_losses += 1
            current_wins = 0
        longest_wins = max(longest_wins, current_wins)
        longest_losses = max(longest_losses, current_losses)
    return longest_wins, longest_losses


def max_drawdown_duration(trades: list[DetailedTrade]) -> tuple[int, int, int, float]:
    running = 0.0
    peak_equity = 0.0
    peak_trade_index = 0
    worst_duration = 0
    trough_trade_index = 0
    worst_drawdown = 0.0
    peak_index_for_worst = 0

    for idx, trade in enumerate(trades, start=1):
        running += trade.pnl
        if running >= peak_equity:
            peak_equity = running
            peak_trade_index = idx
        drawdown = running - peak_equity
        duration = idx - peak_trade_index
        if duration > worst_duration or (duration == worst_duration and drawdown < worst_drawdown):
            worst_duration = duration
            trough_trade_index = idx
            worst_drawdown = drawdown
            peak_index_for_worst = peak_trade_index

    return worst_duration, peak_index_for_worst, trough_trade_index, worst_drawdown


def compute_monthly_sharpes(trades: list[DetailedTrade]) -> list[tuple[str, int, float, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for trade in trades:
        month_key = trade.session_date.strftime("%Y-%m")
        grouped[month_key].append(trade.pnl)

    rows: list[tuple[str, int, float, float]] = []
    for month_key in sorted(grouped):
        pnl_values = grouped[month_key]
        total = sum(pnl_values)
        if len(pnl_values) < 2:
            sharpe = 0.0
        else:
            mean = statistics.fmean(pnl_values)
            std = statistics.pstdev(pnl_values)
            sharpe = (mean / std * math.sqrt(len(pnl_values))) if std > 0 else 0.0
        rows.append((month_key, len(pnl_values), total, sharpe))
    return rows


def regime_change_months(monthly_sharpes: list[tuple[str, int, float, float]]) -> list[str]:
    changes: list[str] = []
    previous_sharpe: float | None = None
    for month_key, trades, total, sharpe in monthly_sharpes:
        if previous_sharpe is not None:
            sign_flip = (previous_sharpe > 0 and sharpe < 0) or (previous_sharpe < 0 and sharpe > 0)
            large_shift = abs(sharpe - previous_sharpe) >= 1.0
            pnl_flip = total == 0 or (previous_sharpe != 0 and (previous_sharpe > 0) != (total > 0))
            if sign_flip or large_shift or pnl_flip:
                changes.append(month_key)
        previous_sharpe = sharpe
    return changes


def consecutive_loss_probability(trades: list[DetailedTrade], streak_len: int = 5) -> tuple[float, float, int]:
    if not trades:
        return 0.0, 0.0, 0
    losses = [1 if trade.pnl <= 0 else 0 for trade in trades]
    loss_rate = sum(losses) / len(losses)
    independence_estimate = loss_rate ** streak_len
    if len(losses) < streak_len:
        return independence_estimate, 0.0, 0
    hits = 0
    windows = len(losses) - streak_len + 1
    for start in range(windows):
        if all(losses[start + offset] == 1 for offset in range(streak_len)):
            hits += 1
    empirical = hits / windows if windows else 0.0
    return independence_estimate, empirical, hits


def run_equity_curve_analysis(sessions: dict[date, list[ScoredBar]]) -> None:
    print("=" * 100)
    print("ANALYSIS B: EQUITY CURVE AND REGIME DEPENDENCE")
    print("=" * 100)

    round1_best = SweepParams(score_min=72, stop_mult=3.0, rr_ratio=3.0, cooldown=10, min_signals=1)
    result, trades = simulate_trades_detailed(sessions, round1_best)

    print(f"Round 1 best config: {format_params(round1_best)}")
    print(
        f"Trades={result.trades}, Wins={result.wins}, Losses={result.losses}, "
        f"WinRate={result.win_rate:.1f}%, PnL=${result.total_pnl:,.0f}, "
        f"PF={result.profit_factor:.2f}, Sharpe={result.sharpe:.2f}, MaxDD=${result.max_drawdown:,.0f}"
    )
    print()
    print("Equity curve (running PnL after each trade):")
    for line in build_equity_curve_lines(trades):
        print(line)

    longest_wins, longest_losses = longest_streaks(trades)
    dd_duration, peak_idx, trough_idx, dd_amount = max_drawdown_duration(trades)
    avg_bars_held = statistics.fmean(trade.bars_held for trade in trades) if trades else 0.0
    independence_estimate, empirical_loss_prob, loss_windows = consecutive_loss_probability(trades, streak_len=5)
    monthly = compute_monthly_sharpes(trades)
    regime_months = regime_change_months(monthly)

    print()
    print("Summary metrics:")
    print(f"Longest winning streak : {longest_wins} trades")
    print(f"Longest losing streak  : {longest_losses} trades")
    print(
        f"Max DD duration        : {dd_duration} trades "
        f"(peak trade #{peak_idx} to trough trade #{trough_idx}, dd=${dd_amount:,.0f})"
    )
    print(f"Average bars held      : {avg_bars_held:.2f}")
    print(
        f"5-loss probability     : independent={independence_estimate * 100:.2f}% "
        f"empirical={empirical_loss_prob * 100:.2f}% ({loss_windows} qualifying windows)"
    )

    print()
    print("Monthly trade Sharpe by exit month:")
    for month_key, trade_count, total, sharpe in monthly:
        print(f"{month_key} trades={trade_count:>3} pnl=${total:>8,.0f} sharpe={sharpe:>6.2f}")

    print()
    if regime_months:
        print(f"Possible regime-change months: {', '.join(regime_months)}")
    else:
        print("Possible regime-change months: none detected by Sharpe shift heuristic")
    print()


def main(csv_path: Path = DEFAULT_CSV) -> None:
    print("Scanning signals once across the full dataset...")
    sessions = scan_signals(csv_path)
    total_bars = sum(len(bars) for bars in sessions.values())
    print(f"Loaded {len(sessions)} sessions and {total_bars:,} RTH bars from {csv_path}")
    print()
    run_walk_forward(sessions)
    run_equity_curve_analysis(sessions)


if __name__ == "__main__":
    main()
