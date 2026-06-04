from __future__ import annotations

import subprocess
import sys
from dataclasses import fields
from pathlib import Path

import pandas as pd

from research.continuation_zones.backtest_engine import Trade
from research.continuation_zones.optimization import OptimizationResult
from research.continuation_zones.results_analyzer import ATMProfile, ResultsAnalyzer


def _make_trade(pnl_dollars: float, index: int) -> Trade:
    entry_time = pd.Timestamp("2026-02-03 14:30:00+00:00") + pd.Timedelta(minutes=5 * index)
    direction = "long" if pnl_dollars >= 0 else "short"
    return Trade(
        entry_time=entry_time,
        exit_time=entry_time + pd.Timedelta(minutes=5),
        zone_kind="RBR" if direction == "long" else "DBD",
        zone_timeframe=5 if index % 2 == 0 else 15,
        zone_score=7,
        zone_score_at_entry=7,
        entry_price=100.0,
        exit_price=101.0 if pnl_dollars >= 0 else 99.0,
        direction=direction,
        stop_price=99.0,
        target_price=102.0,
        pnl_ticks=pnl_dollars / 5.0,
        pnl_dollars=pnl_dollars,
        exit_reason="target" if pnl_dollars >= 0 else "stop",
        bars_held=1,
        mae_ticks=1.0,
        mfe_ticks=2.0,
    )


def _make_result(
    trial_number: int,
    *,
    fitness: float,
    oos_win_rate: float,
    oos_sharpe: float,
    stop_ticks: int,
    target_ticks: int,
    breakeven_ticks: int,
    trail_ticks: int,
    trail_activation_ticks: int,
    max_zone_age_bars_5m: int,
    max_zone_age_bars_15m: int,
    min_score: int,
) -> OptimizationResult:
    oos_trades = 240
    expected_ev = round((oos_sharpe * 10.0) + (oos_win_rate * 20.0), 2)
    return OptimizationResult(
        params={
            "small_body_ratio": 0.35 + (trial_number * 0.01),
            "min_zone_ticks": 2 + (trial_number % 2),
            "max_zone_age_bars_5m": max_zone_age_bars_5m,
            "max_zone_age_bars_15m": max_zone_age_bars_15m,
            "max_touch_count": 2,
            "min_score": min_score,
            "stop_ticks": stop_ticks,
            "target_ticks": target_ticks,
            "breakeven_ticks": breakeven_ticks,
            "trail_ticks": trail_ticks,
            "trail_activation_ticks": trail_activation_ticks,
            "rth_only": True,
        },
        is_sharpe=oos_sharpe + 0.1,
        oos_sharpe=oos_sharpe,
        is_win_rate=min(0.95, oos_win_rate + 0.05),
        oos_win_rate=oos_win_rate,
        is_trades=260,
        oos_trades=oos_trades,
        is_total_pnl=expected_ev * 260,
        oos_total_pnl=expected_ev * oos_trades,
        fitness=fitness,
        is_overfit=False,
        trial_number=trial_number,
    )


def _make_results() -> list[OptimizationResult]:
    return [
        _make_result(0, fitness=0.92, oos_win_rate=0.61, oos_sharpe=1.50, stop_ticks=8, target_ticks=12, breakeven_ticks=4, trail_ticks=0, trail_activation_ticks=0, max_zone_age_bars_5m=200, max_zone_age_bars_15m=30, min_score=5),
        _make_result(1, fitness=1.20, oos_win_rate=0.58, oos_sharpe=1.95, stop_ticks=12, target_ticks=16, breakeven_ticks=6, trail_ticks=4, trail_activation_ticks=8, max_zone_age_bars_5m=110, max_zone_age_bars_15m=80, min_score=6),
        _make_result(2, fitness=0.98, oos_win_rate=0.52, oos_sharpe=2.10, stop_ticks=10, target_ticks=20, breakeven_ticks=8, trail_ticks=8, trail_activation_ticks=8, max_zone_age_bars_5m=140, max_zone_age_bars_15m=55, min_score=5),
        _make_result(3, fitness=0.85, oos_win_rate=0.57, oos_sharpe=1.60, stop_ticks=8, target_ticks=14, breakeven_ticks=4, trail_ticks=0, trail_activation_ticks=0, max_zone_age_bars_5m=160, max_zone_age_bars_15m=40, min_score=5),
        _make_result(4, fitness=0.81, oos_win_rate=0.55, oos_sharpe=1.35, stop_ticks=10, target_ticks=14, breakeven_ticks=6, trail_ticks=2, trail_activation_ticks=8, max_zone_age_bars_5m=120, max_zone_age_bars_15m=60, min_score=4),
        _make_result(5, fitness=0.79, oos_win_rate=0.54, oos_sharpe=1.32, stop_ticks=12, target_ticks=18, breakeven_ticks=6, trail_ticks=2, trail_activation_ticks=10, max_zone_age_bars_5m=130, max_zone_age_bars_15m=65, min_score=5),
        _make_result(6, fitness=0.75, oos_win_rate=0.53, oos_sharpe=1.25, stop_ticks=8, target_ticks=16, breakeven_ticks=4, trail_ticks=0, trail_activation_ticks=0, max_zone_age_bars_5m=180, max_zone_age_bars_15m=35, min_score=6),
        _make_result(7, fitness=0.73, oos_win_rate=0.51, oos_sharpe=1.18, stop_ticks=10, target_ticks=18, breakeven_ticks=6, trail_ticks=4, trail_activation_ticks=8, max_zone_age_bars_5m=125, max_zone_age_bars_15m=50, min_score=5),
        _make_result(8, fitness=0.70, oos_win_rate=0.50, oos_sharpe=1.15, stop_ticks=12, target_ticks=20, breakeven_ticks=8, trail_ticks=4, trail_activation_ticks=10, max_zone_age_bars_5m=100, max_zone_age_bars_15m=75, min_score=5),
        _make_result(9, fitness=0.68, oos_win_rate=0.49, oos_sharpe=1.05, stop_ticks=14, target_ticks=22, breakeven_ticks=8, trail_ticks=6, trail_activation_ticks=10, max_zone_age_bars_5m=90, max_zone_age_bars_15m=70, min_score=6),
    ]


def _make_analyzer() -> ResultsAnalyzer:
    trades = [_make_trade(pnl, index) for index, pnl in enumerate([25.0, -10.0, 30.0, 15.0, -5.0, 20.0])]
    return ResultsAnalyzer(trades=trades, optimization_results=_make_results())


def _profiles_by_name(profiles: list[ATMProfile]) -> dict[str, ATMProfile]:
    return {profile.name: profile for profile in profiles}


def test_derive_atm_profiles_returns_three() -> None:
    profiles = _make_analyzer().derive_atm_profiles()
    assert len(profiles) == 3
    assert [profile.name for profile in profiles] == ["Conservative", "Balanced", "Aggressive"]


def test_atm_profile_fields_complete() -> None:
    profiles = _make_analyzer().derive_atm_profiles()
    for profile in profiles:
        for field in fields(ATMProfile):
            value = getattr(profile, field.name)
            assert value is not None
            if isinstance(value, str):
                assert value.strip() != ""


def test_conservative_has_highest_win_rate() -> None:
    profiles = _profiles_by_name(_make_analyzer().derive_atm_profiles())
    assert profiles["Conservative"].expected_win_rate >= profiles["Balanced"].expected_win_rate


def test_balanced_has_best_fitness() -> None:
    results = _make_results()
    profiles = _profiles_by_name(ResultsAnalyzer(trades=[], optimization_results=results).derive_atm_profiles())
    assert profiles["Balanced"].source_param_set == max(results, key=lambda result: result.fitness).trial_number


def test_save_atm_recommendations_creates_file(tmp_path: Path) -> None:
    analyzer = _make_analyzer()
    profiles = analyzer.derive_atm_profiles()
    output_path = tmp_path / "atm_recommendations.md"

    analyzer.save_atm_recommendations(profiles, output_path)

    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "## Profile 1: Conservative" in content
    assert "## Profile 2: Balanced" in content
    assert "## Profile 3: Aggressive" in content
    assert "TODO" not in content
    assert "TBD" not in content


def test_save_trade_csv_creates_file(tmp_path: Path) -> None:
    analyzer = _make_analyzer()
    output_path = tmp_path / "all_trades_best_params.csv"

    analyzer.save_trade_csv(output_path)

    assert output_path.exists()
    exported = pd.read_csv(output_path)
    assert list(exported.columns) == [field.name for field in fields(Trade)]
    assert len(exported) == 6


def test_save_equity_curve_creates_png(tmp_path: Path) -> None:
    analyzer = _make_analyzer()
    output_path = tmp_path / "equity_curve_best_params.png"

    analyzer.save_equity_curve(output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_run_backtest_help() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "research" / "continuation_zones" / "run_backtest.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "NQ Continuation Zone Backtest Pipeline" in result.stdout
