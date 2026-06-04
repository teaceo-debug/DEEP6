#!/usr/bin/env python3
"""
NQ Continuation Zone Backtest Pipeline
Usage: python run_backtest.py [--n-trials N] [--output-dir DIR] [--skip-download]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd


def _ensure_repo_root_on_path() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    return repo_root


def _build_local_cache(csv_path: Path, cache_path: Path, write_cache) -> pd.DataFrame:
    df = pd.read_csv(csv_path, usecols=["ts_event", "open", "high", "low", "close", "volume"])
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df = df.set_index("ts_event").sort_index()
    df.index.name = "ts_event"
    write_cache(df, cache_path)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="NQ Continuation Zone Backtest Pipeline")
    parser.add_argument("--n-trials", type=int, default=200, help="Optuna trials (default: 200)")
    parser.add_argument("--min-oos-trades", type=int, default=20, help="Minimum OOS trades required")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research/continuation_zones/results"),
        help="Output directory",
    )
    parser.add_argument("--skip-download", action="store_true", help="Skip data download if cache exists")
    parser.add_argument("--dry-run", action="store_true", help="Run with n_trials=3 for testing")
    parser.add_argument(
        "--csv-path",
        type=Path,
        default=Path("data/backtests/nq_1yr_1m.csv"),
        help="Local 1m CSV source used to build parquet cache",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=Path("data/nq_ohlcv_1m_2025-2026.parquet"),
        help="Parquet cache destination",
    )
    args = parser.parse_args()

    if args.dry_run:
        args.n_trials = 3

    _ensure_repo_root_on_path()

    from research.continuation_zones.backtest_engine import BacktestConfig, BacktestEngine
    from research.continuation_zones.data_loader import apply_rth_filter, build_ohlcv, load_1m_bars, write_ohlcv_cache
    from research.continuation_zones.optimization import ContinuationZoneOptimizer, OptimizationResult, WalkForwardSplit
    from research.continuation_zones.results_analyzer import ResultsAnalyzer

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Step 1/5: Loading NQ data...")
    if not args.csv_path.exists():
        raise FileNotFoundError(f"Local CSV not found: {args.csv_path}")
    df_1m = _build_local_cache(args.csv_path, args.cache_path, write_ohlcv_cache)
    print(f"Cached {len(df_1m):,} rows to {args.cache_path}")

    df_1m = load_1m_bars(cache_path=args.cache_path)
    df_5m = apply_rth_filter(build_ohlcv(df_1m, "5min"))
    df_15m = apply_rth_filter(build_ohlcv(df_1m, "15min"))
    split = WalkForwardSplit.from_df(df_5m, is_months=12, oos_months=4)
    print(f"5m bars: {len(df_5m):,}  range: {df_5m.index.min()} to {df_5m.index.max()}")
    print(f"15m bars: {len(df_15m):,}  range: {df_15m.index.min()} to {df_15m.index.max()}")
    print(f"IS: {split.is_start.date()} -> {split.is_end.date()}")
    print(f"OOS: {split.oos_start.date()} -> {split.oos_end.date()}")

    print("Step 2/5: Running baseline backtest...")
    baseline_config = BacktestConfig()
    baseline_trades = BacktestEngine(baseline_config).run(df_5m, df_15m)
    if len(baseline_trades) < 10:
        baseline_config = BacktestConfig(small_body_ratio=0.50)
        baseline_trades = BacktestEngine(baseline_config).run(df_5m, df_15m)
    print(f"Baseline trades: {len(baseline_trades)}")
    if baseline_trades:
        baseline_wins = sum(1 for trade in baseline_trades if trade.pnl_dollars > 0)
        baseline_pnl = sum(trade.pnl_dollars for trade in baseline_trades)
        print(f"Baseline win rate: {baseline_wins / len(baseline_trades):.1%}")
        print(f"Baseline total P&L: ${baseline_pnl:,.2f}")

    print("Step 3/5: Running optimization sweep...")
    optimizer = ContinuationZoneOptimizer(
        df_5m=df_5m,
        df_15m=df_15m,
        split=split,
        n_trials=args.n_trials,
        min_oos_trades=args.min_oos_trades,
    )
    optimization_results = optimizer.optimize()
    if not optimization_results:
        print("Optimization produced no valid results. Falling back to baseline configuration.")
        pnls = [trade.pnl_dollars for trade in baseline_trades]
        mean_pnl = (sum(pnls) / len(pnls)) if pnls else 0.0
        std_pnl = ((sum((pnl - mean_pnl) ** 2 for pnl in pnls) / len(pnls)) ** 0.5) if pnls else 0.0
        sharpe = (mean_pnl / std_pnl * (252 ** 0.5)) if std_pnl > 0 else 0.0
        win_rate = (sum(1 for pnl in pnls if pnl > 0) / len(pnls)) if pnls else 0.0
        optimization_results = [
            OptimizationResult(
                params=asdict(baseline_config),
                is_sharpe=sharpe,
                oos_sharpe=sharpe,
                is_win_rate=win_rate,
                oos_win_rate=win_rate,
                is_trades=len(baseline_trades),
                oos_trades=len(baseline_trades),
                is_total_pnl=sum(pnls),
                oos_total_pnl=sum(pnls),
                fitness=sharpe * win_rate,
                is_overfit=False,
                trial_number=0,
            )
        ]
    optimizer.save_results(optimization_results, output_dir)

    print("Step 4/5: Analyzing results...")
    best_result = optimization_results[0]
    best_config = BacktestConfig(**best_result.params)
    best_trades = BacktestEngine(best_config).run(df_5m, df_15m)
    analyzer = ResultsAnalyzer(
        trades=best_trades,
        optimization_results=optimization_results,
        tick_size=best_config.tick_size,
        tick_value=best_config.tick_value,
        min_oos_trades=args.min_oos_trades,
    )
    profiles = analyzer.derive_atm_profiles()

    print("Step 5/5: Saving outputs...")
    analyzer.save_atm_recommendations(profiles, output_dir / "atm_recommendations.md")
    analyzer.save_trade_csv(output_dir / "all_trades_best_params.csv")
    analyzer.save_equity_curve(output_dir / "equity_curve_best_params.png")

    expected_files = [
        args.cache_path,
        output_dir / "top10_param_sets.csv",
        output_dir / "all_trades_best_params.csv",
        output_dir / "equity_curve_best_params.png",
        output_dir / "atm_recommendations.md",
    ]
    for path in expected_files:
        status = f"OK {path.stat().st_size:,}B" if path.exists() else "MISSING"
        print(f"{status}  {path}")

    print(f"\nDone. Results saved to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
