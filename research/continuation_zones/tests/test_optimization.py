from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.continuation_zones.backtest_engine import Trade
from research.continuation_zones.optimization import (
    ContinuationZoneOptimizer,
    OptimizationResult,
    WalkForwardSplit,
    _compute_fitness,
)


def _make_trade(pnl_dollars: float) -> Trade:
    timestamp = pd.Timestamp("2026-01-05 14:30:00+00:00")
    direction = "long" if pnl_dollars >= 0 else "short"
    return Trade(
        entry_time=timestamp,
        exit_time=timestamp + pd.Timedelta(minutes=5),
        zone_kind="RBR",
        zone_timeframe=5,
        zone_score=8,
        zone_score_at_entry=8,
        entry_price=100.0,
        exit_price=101.0,
        direction=direction,
        stop_price=99.0,
        target_price=102.0,
        pnl_ticks=pnl_dollars / 5.0,
        pnl_dollars=pnl_dollars,
        exit_reason="target" if pnl_dollars >= 0 else "stop",
        bars_held=1,
        mae_ticks=0.0,
        mfe_ticks=0.0,
    )


def _make_frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 100,
        },
        index=index,
    )


def test_walk_forward_split_dates() -> None:
    index = pd.date_range("2025-05-25", "2026-05-25", freq="D", tz="UTC", name="ts_event")
    df = _make_frame(index)

    split = WalkForwardSplit.from_df(df)

    assert split.is_start == pd.Timestamp("2025-05-25 00:00:00+00:00")
    assert split.is_end == pd.Timestamp("2026-01-25 00:00:00+00:00")
    assert split.oos_start == pd.Timestamp("2026-01-25 00:00:00+00:00")
    assert split.oos_end == pd.Timestamp("2026-05-25 00:00:00+00:00")


def test_compute_fitness_all_wins() -> None:
    trades = [_make_trade(pnl) for pnl in [10, 12, 14, 16, 18, 20, 22, 24, 26, 28]]

    sharpe, win_rate, total_pnl, n_trades = _compute_fitness(trades)

    assert sharpe > 0
    assert win_rate == 1.0
    assert total_pnl == sum([10, 12, 14, 16, 18, 20, 22, 24, 26, 28])
    assert n_trades == 10


def test_compute_fitness_all_losses() -> None:
    trades = [_make_trade(pnl) for pnl in [-10, -12, -14, -16, -18, -20, -22, -24, -26, -28]]

    sharpe, win_rate, total_pnl, n_trades = _compute_fitness(trades)

    assert sharpe < 0
    assert win_rate == 0.0
    assert total_pnl == sum([-10, -12, -14, -16, -18, -20, -22, -24, -26, -28])
    assert n_trades == 10


def test_compute_fitness_too_few_trades() -> None:
    trades = [_make_trade(10.0) for _ in range(9)]

    assert _compute_fitness(trades) == (-999.0, 0.0, 0.0, 9)


def test_overfit_flag() -> None:
    result = OptimizationResult(
        params={},
        is_sharpe=2.5,
        oos_sharpe=1.0,
        is_win_rate=0.6,
        oos_win_rate=0.5,
        is_trades=250,
        oos_trades=220,
        is_total_pnl=1000.0,
        oos_total_pnl=500.0,
        fitness=0.5,
        is_overfit=2.5 > 2 * 1.0,
        trial_number=1,
    )

    assert result.is_overfit is True


def test_no_overfit_flag() -> None:
    result = OptimizationResult(
        params={},
        is_sharpe=1.5,
        oos_sharpe=1.0,
        is_win_rate=0.6,
        oos_win_rate=0.5,
        is_trades=250,
        oos_trades=220,
        is_total_pnl=1000.0,
        oos_total_pnl=500.0,
        fitness=0.5,
        is_overfit=1.5 > 2 * 1.0,
        trial_number=1,
    )

    assert result.is_overfit is False


def test_optimizer_runs_with_synthetic_data() -> None:
    index_5m = pd.date_range("2025-05-25", periods=120, freq="3D", tz="UTC", name="ts_event")
    index_15m = pd.date_range("2025-05-25", periods=120, freq="3D", tz="UTC", name="ts_event")
    df_5m = _make_frame(index_5m)
    df_15m = _make_frame(index_15m)
    split = WalkForwardSplit.from_df(df_5m)
    optimizer = ContinuationZoneOptimizer(df_5m, df_15m, split, n_trials=3, min_oos_trades=0, seed=7)

    results = optimizer.optimize()

    assert isinstance(results, list)
    assert len(results) <= 3


def test_save_results_creates_csv(tmp_path: Path) -> None:
    index = pd.date_range("2025-05-25", periods=10, freq="D", tz="UTC", name="ts_event")
    df = _make_frame(index)
    split = WalkForwardSplit.from_df(df)
    optimizer = ContinuationZoneOptimizer(df, df, split, n_trials=1, min_oos_trades=0)
    results = [
        OptimizationResult(
            params={
                "small_body_ratio": 0.35,
                "min_zone_ticks": 2,
                "max_zone_age_bars_5m": 100,
                "max_zone_age_bars_15m": 40,
                "max_touch_count": 2,
                "min_score": 5,
                "stop_ticks": 8,
                "target_ticks": 16,
                "breakeven_ticks": 6,
                "trail_ticks": 2,
                "trail_activation_ticks": 8,
                "rth_only": True,
            },
            is_sharpe=1.1,
            oos_sharpe=0.9,
            is_win_rate=0.55,
            oos_win_rate=0.52,
            is_trades=250,
            oos_trades=220,
            is_total_pnl=900.0,
            oos_total_pnl=450.0,
            fitness=0.468,
            is_overfit=False,
            trial_number=3,
        )
    ]

    optimizer.save_results(results, tmp_path)

    csv_path = tmp_path / "top10_param_sets.csv"
    assert csv_path.exists()
    exported = pd.read_csv(csv_path)
    assert list(exported.columns) == [
        "rank",
        "trial_number",
        "fitness",
        "oos_sharpe",
        "oos_win_rate",
        "oos_trades",
        "oos_total_pnl",
        "is_sharpe",
        "is_win_rate",
        "is_trades",
        "is_overfit",
        "small_body_ratio",
        "min_zone_ticks",
        "max_zone_age_bars_5m",
        "max_zone_age_bars_15m",
        "max_touch_count",
        "min_score",
        "stop_ticks",
        "target_ticks",
        "breakeven_ticks",
        "trail_ticks",
        "trail_activation_ticks",
        "rth_only",
    ]
    assert exported.loc[0, "trial_number"] == 3
    assert exported.loc[0, "small_body_ratio"] == 0.35
