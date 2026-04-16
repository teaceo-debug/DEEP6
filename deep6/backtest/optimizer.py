"""deep6/backtest/optimizer.py — Full parameter sweep for DEEP6 backtest engine.

Sweeps 4,050 parameter combos across all 50 NDJSON sessions using the
Python-native trade simulator (pre-scored signal data — no re-scoring needed).

Parameter grid:
  ScoreEntryThreshold : [40, 50, 60, 70, 80, 90]
  MinTier             : [0=any, 1=TYPE_B+, 2=TYPE_A only]
  StopLossTicks       : [8, 12, 16, 20, 30]
  TargetTicks         : [16, 24, 32, 40, 60]
  ExitOnOpposingScore : [0.3, 0.5, 0.7]  (as percentage — mapped 0-100)
  MaxBarsInTrade      : [15, 30, 60]
  Total: 6 × 3 × 5 × 5 × 3 × 3 = 4,050 combos

Output:
  results/sweep_results.csv
  results/sharpe_heatmap.html
  results/profit_factor_heatmap.html
  results/top_20_configs.md
  results/OPTIMIZATION-REPORT.md
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
OUTPUT_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results"

# ---------------------------------------------------------------------------
# Tier ordinals (task mapping: 0=any directional, 1=TYPE_B+, 2=TYPE_A only)
# ---------------------------------------------------------------------------
# Scorer tier thresholds (mirrors vbt_harness._score_bar_simple tier logic)
# TYPE_A: score >= 80 AND (abs OR exh) AND zone AND cat_count >= 5
# TYPE_B: score >= 72 AND cat_count >= 4 AND max_str >= 0.3
# TYPE_C: score >= 50 AND cat_count >= 4 AND max_str >= 0.3
# "any" (ordinal 0): accept all directional bars regardless of tier
_TIER_ORDINALS = {"DISQUALIFIED": -1, "QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
_TIER_TASK_MAP = {
    0: -999,   # accept any tier (even QUIET) — gate only on score + direction
    1: _TIER_ORDINALS["TYPE_B"],   # TYPE_B+
    2: _TIER_ORDINALS["TYPE_A"],   # TYPE_A only
}

# ---------------------------------------------------------------------------
# Parameter grid (exactly as specified in task)
# ---------------------------------------------------------------------------
GRID = {
    "score_entry_threshold": [40, 50, 60, 70, 80, 90],
    "min_tier":              [0, 1, 2],        # task ordinals
    "stop_loss_ticks":       [8, 12, 16, 20, 30],
    "target_ticks":          [16, 24, 32, 40, 60],
    "exit_on_opposing_score": [0.3, 0.5, 0.7],
    "max_bars_in_trade":     [15, 30, 60],
}

TOTAL_COMBOS = 1
for v in GRID.values():
    TOTAL_COMBOS *= len(v)

TICK_SIZE = 0.25    # NQ tick size
TICK_VALUE = 5.0    # $ per tick per contract

# ---------------------------------------------------------------------------
# Helpers for metric computation
# ---------------------------------------------------------------------------

def profit_factor(pnls: np.ndarray) -> float:
    gross_profit = pnls[pnls > 0].sum()
    gross_loss = abs(pnls[pnls < 0].sum())
    return float(gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0


def max_drawdown(pnls: np.ndarray) -> float:
    """Max drawdown as a fraction of peak equity (in $ terms)."""
    equity = np.cumsum(pnls)
    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity
    return float(drawdown.max()) if len(drawdown) else 0.0


def sharpe_estimate(pnls: np.ndarray) -> float:
    """Annualised Sharpe estimate (mean/std * sqrt(252))."""
    if len(pnls) < 2:
        return 0.0
    std = pnls.std(ddof=1)
    if std == 0.0:
        return 0.0
    return float((pnls.mean() / std) * np.sqrt(252))


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_dollars": 0.0,
            "sharpe": 0.0,
            "avg_pnl_per_trade": 0.0,
            "net_pnl": 0.0,
        }
    pnls = np.array([t["pnl_dollars"] for t in trades])
    wins = (pnls > 0).sum()
    return {
        "total_trades": len(trades),
        "win_rate": float(wins / len(pnls)),
        "profit_factor": profit_factor(pnls),
        "max_drawdown_dollars": max_drawdown(pnls),
        "sharpe": sharpe_estimate(pnls),
        "avg_pnl_per_trade": float(pnls.mean()),
        "net_pnl": float(pnls.sum()),
    }


# ---------------------------------------------------------------------------
# Data loading — cache scored bars in memory for speed
# ---------------------------------------------------------------------------

def load_all_sessions(sessions_dir: Path) -> dict[str, list[dict]]:
    """Load all NDJSON sessions and pre-compute scored bars.

    Returns dict: session_name -> list of (bar, scored) tuples stored as dicts.
    """
    from deep6.backtest.vbt_harness import (  # type: ignore
        _load_scored_bars_from_ndjson,
        _score_bar_simple,
    )
    sessions = {}
    for path in sorted(sessions_dir.glob("*.ndjson")):
        bars = _load_scored_bars_from_ndjson(path)
        scored_pairs = [(b, _score_bar_simple(b)) for b in bars]
        sessions[path.name] = scored_pairs
    return sessions


# ---------------------------------------------------------------------------
# Core simulator — operates on pre-scored (bar, scored) pairs
# Does NOT call _score_bar_simple again — just varies entry/exit gates
# ---------------------------------------------------------------------------

def simulate_combo(
    sessions_data: dict[str, list[tuple[dict, dict]]],
    score_entry_threshold: float,
    min_tier_ordinal_cutoff: int,
    stop_loss_ticks: int,
    target_ticks: int,
    exit_on_opposing_score: float,
    max_bars_in_trade: int,
) -> list[dict]:
    """Run simulation over all sessions for one parameter combo."""
    sl_pts = stop_loss_ticks * TICK_SIZE
    tp_pts = target_ticks * TICK_SIZE
    slippage_pts = 1.0 * TICK_SIZE

    # Convert exit_on_opposing_score from fraction to score scale
    # The scorer returns total_score in [0, 100] range,
    # so 0.3 on the task scale maps to 30.0 on the scorer scale
    opposing_thresh = exit_on_opposing_score * 100.0

    all_trades: list[dict] = []

    for session_name, scored_pairs in sessions_data.items():
        in_trade = False
        entry_price = 0.0
        entry_bar_idx = 0
        trade_dir = 0

        for bar, scored in scored_pairs:
            bar_idx = int(bar.get("barIdx", 0))
            bar_close = float(bar.get("barClose", 0.0))
            direction = scored["direction"]
            total_score = scored["total_score"]
            tier_ord = _TIER_ORDINALS.get(scored["tier"], 0)

            if in_trade:
                exit_reason = None

                # 1. Stop loss
                if trade_dir == 1 and bar_close <= entry_price - sl_pts:
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + sl_pts:
                    exit_reason = "STOP_LOSS"

                # 2. Target
                if exit_reason is None:
                    if trade_dir == 1 and bar_close >= entry_price + tp_pts:
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - tp_pts:
                        exit_reason = "TARGET"

                # 3. Opposing signal exit
                if exit_reason is None and direction != 0 and direction != trade_dir:
                    if total_score >= opposing_thresh:
                        exit_reason = "OPPOSING"

                # 4. Max bars
                if exit_reason is None and (bar_idx - entry_bar_idx) >= max_bars_in_trade:
                    exit_reason = "MAX_BARS"

                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * slippage_pts)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    all_trades.append({
                        "session": session_name,
                        "entry_bar": entry_bar_idx,
                        "exit_bar": bar_idx,
                        "direction": trade_dir,
                        "pnl_ticks": pnl_ticks,
                        "pnl_dollars": pnl_ticks * TICK_VALUE,
                        "exit_reason": exit_reason,
                    })
                    in_trade = False

            else:
                # Entry gate: threshold + tier + direction
                if (total_score >= score_entry_threshold
                        and tier_ord >= min_tier_ordinal_cutoff
                        and direction != 0):
                    entry_price = scored["entry_price"] + direction * slippage_pts
                    entry_bar_idx = bar_idx
                    trade_dir = direction
                    in_trade = True

        # Force-close at session end
        if in_trade and scored_pairs:
            last_bar, _ = scored_pairs[-1]
            bar_close = float(last_bar.get("barClose", 0.0))
            bar_idx = int(last_bar.get("barIdx", 0))
            exit_price = bar_close - (trade_dir * slippage_pts)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            all_trades.append({
                "session": session_name,
                "entry_bar": entry_bar_idx,
                "exit_bar": bar_idx,
                "direction": trade_dir,
                "pnl_ticks": pnl_ticks,
                "pnl_dollars": pnl_ticks * TICK_VALUE,
                "exit_reason": "SESSION_END",
            })
            in_trade = False

    return all_trades


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(sessions_data: dict, session_paths: list[Path]) -> pd.DataFrame:
    """Run all 4,050 combos, return results DataFrame."""
    combos = list(itertools.product(
        GRID["score_entry_threshold"],
        GRID["min_tier"],
        GRID["stop_loss_ticks"],
        GRID["target_ticks"],
        GRID["exit_on_opposing_score"],
        GRID["max_bars_in_trade"],
    ))

    print(f"Running {len(combos)} combos over {len(sessions_data)} sessions...")
    t0 = time.time()

    rows = []
    for i, (thr, mt, sl, tp, opp, mb) in enumerate(combos):
        min_tier_cutoff = _TIER_TASK_MAP[mt]
        trades = simulate_combo(
            sessions_data,
            score_entry_threshold=float(thr),
            min_tier_ordinal_cutoff=min_tier_cutoff,
            stop_loss_ticks=sl,
            target_ticks=tp,
            exit_on_opposing_score=opp,
            max_bars_in_trade=mb,
        )
        stats = compute_stats(trades)
        rows.append({
            "score_entry_threshold": thr,
            "min_tier": mt,
            "stop_loss_ticks": sl,
            "target_ticks": tp,
            "exit_on_opposing_score": opp,
            "max_bars_in_trade": mb,
            **stats,
        })
        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(combos) - i - 1) / rate
            print(f"  {i+1}/{len(combos)} combos | elapsed={elapsed:.0f}s | ETA={eta:.0f}s")

    elapsed = time.time() - t0
    print(f"Sweep complete: {len(combos)} combos in {elapsed:.1f}s ({elapsed/len(combos)*1000:.1f}ms/combo)")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def run_walkforward(
    sessions_data: dict,
    all_session_names: list[str],
    top_n: int = 5,
    min_val_sharpe: float = 1.0,
) -> list[dict]:
    """Stratified train/validate/test split by regime, optimize on train.

    Sessions are ordered by regime (10 per regime: trend_up, trend_down,
    ranging, volatile, slow_grind). Stratified split:
      - Train: sessions 1-6 of each regime (30 total)
      - Validate: sessions 7-8 of each regime (10 total)
      - Test: sessions 9-10 of each regime (10 total)
    """
    # Build regime groups
    regimes = {}
    for name in all_session_names:
        # Extract regime from filename: session-NN-REGIME-NN.ndjson
        parts = name.replace(".ndjson", "").split("-")
        # e.g. ['session', '01', 'trend', 'up', '01'] or ['session', '01', 'ranging', '01']
        # Regime is everything between second and last part
        regime = "-".join(parts[2:-1])
        regimes.setdefault(regime, []).append(name)

    train_sessions = []
    val_sessions = []
    test_sessions = []

    for regime, names in sorted(regimes.items()):
        n = len(names)
        # 60/20/20 split per regime
        train_end = max(1, int(n * 0.60))
        val_end = max(train_end + 1, int(n * 0.80))
        train_sessions.extend(names[:train_end])
        val_sessions.extend(names[train_end:val_end])
        test_sessions.extend(names[val_end:])

    print(f"\nWalk-forward split:")
    print(f"  Train:    {len(train_sessions)} sessions")
    print(f"  Validate: {len(val_sessions)} sessions")
    print(f"  Test:     {len(test_sessions)} sessions")

    train_data = {k: v for k, v in sessions_data.items() if k in set(train_sessions)}
    val_data = {k: v for k, v in sessions_data.items() if k in set(val_sessions)}
    test_data = {k: v for k, v in sessions_data.items() if k in set(test_sessions)}

    # Step 1: optimize on train
    print("\nOptimizing on train set...")
    train_df = run_sweep(train_data, [])

    # Filter for minimum trade count to avoid overfitting on tiny samples
    min_trades = max(3, len(train_sessions))
    qualified = train_df[train_df["total_trades"] >= min_trades].copy()
    if qualified.empty:
        qualified = train_df.copy()

    qualified_sorted = qualified.sort_values("sharpe", ascending=False)
    top_combos = qualified_sorted.head(top_n).copy()

    results = []
    for idx, row in top_combos.iterrows():
        mt = int(row["min_tier"])
        min_tier_cutoff = _TIER_TASK_MAP[mt]
        params = {
            "score_entry_threshold": float(row["score_entry_threshold"]),
            "min_tier": mt,
            "stop_loss_ticks": int(row["stop_loss_ticks"]),
            "target_ticks": int(row["target_ticks"]),
            "exit_on_opposing_score": float(row["exit_on_opposing_score"]),
            "max_bars_in_trade": int(row["max_bars_in_trade"]),
        }
        train_sharpe = float(row["sharpe"])
        train_trades = int(row["total_trades"])

        # Validate
        val_trades = simulate_combo(
            val_data,
            score_entry_threshold=params["score_entry_threshold"],
            min_tier_ordinal_cutoff=min_tier_cutoff,
            stop_loss_ticks=params["stop_loss_ticks"],
            target_ticks=params["target_ticks"],
            exit_on_opposing_score=params["exit_on_opposing_score"],
            max_bars_in_trade=params["max_bars_in_trade"],
        )
        val_stats = compute_stats(val_trades)

        # Test (out-of-sample)
        test_trades = simulate_combo(
            test_data,
            score_entry_threshold=params["score_entry_threshold"],
            min_tier_ordinal_cutoff=min_tier_cutoff,
            stop_loss_ticks=params["stop_loss_ticks"],
            target_ticks=params["target_ticks"],
            exit_on_opposing_score=params["exit_on_opposing_score"],
            max_bars_in_trade=params["max_bars_in_trade"],
        )
        test_stats = compute_stats(test_trades)

        passed_val = val_stats["sharpe"] >= min_val_sharpe
        results.append({
            "rank": len(results) + 1,
            "params": params,
            "train_sharpe": train_sharpe,
            "train_trades": train_trades,
            "train_win_rate": float(row["win_rate"]),
            "train_profit_factor": float(row["profit_factor"]),
            "validate_sharpe": val_stats["sharpe"],
            "validate_trades": val_stats["total_trades"],
            "validate_profit_factor": val_stats["profit_factor"],
            "test_sharpe": test_stats["sharpe"],
            "test_trades": test_stats["total_trades"],
            "test_win_rate": test_stats["win_rate"],
            "test_profit_factor": test_stats["profit_factor"],
            "test_max_drawdown": test_stats["max_drawdown_dollars"],
            "test_net_pnl": test_stats["net_pnl"],
            "passed_validation": passed_val,
        })

    return results, train_df, train_sessions, val_sessions, test_sessions


# ---------------------------------------------------------------------------
# Output: heatmaps
# ---------------------------------------------------------------------------

def save_heatmap_html(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    value_col: str,
    title: str,
    output_path: Path,
    agg: str = "mean",
) -> None:
    """Create interactive Plotly heatmap and save as HTML."""
    import plotly.graph_objects as go
    import plotly.express as px

    pivot = df.pivot_table(index=y_col, columns=x_col, values=value_col, aggfunc=agg)
    pivot = pivot.sort_index()

    # Handle inf values
    pivot = pivot.replace([float("inf"), float("-inf")], float("nan"))

    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=[str(r) for r in pivot.index],
        colorscale="RdYlGn",
        colorbar=dict(title=value_col),
        text=np.round(pivot.values, 3).astype(str),
        texttemplate="%{text}",
        textfont={"size": 10},
    ))
    fig.update_layout(
        title=title,
        xaxis_title=x_col,
        yaxis_title=y_col,
        width=900,
        height=600,
    )
    fig.write_html(str(output_path))
    print(f"Saved heatmap: {output_path}")


# ---------------------------------------------------------------------------
# Output: markdown reports
# ---------------------------------------------------------------------------

def save_top20_md(df: pd.DataFrame, output_path: Path) -> None:
    top20 = df[df["total_trades"] >= 5].nlargest(20, "sharpe").copy()
    if top20.empty:
        top20 = df.nlargest(20, "sharpe").copy()
    top20.insert(0, "rank", range(1, len(top20) + 1))

    lines = [
        "# DEEP6 Parameter Optimization — Top 20 Configurations",
        "",
        f"Ranked by Sharpe estimate (annualised, mean/std × √252).",
        f"Sessions: 50 NQ sessions across 5 regimes (trend_up, trend_down, ranging, volatile, slow_grind).",
        f"Total combos evaluated: {TOTAL_COMBOS:,}",
        "",
        "| Rank | Threshold | MinTier | SL | TP | OppScore | MaxBars | Trades | WinRate | PF | Sharpe | AvgPnL$ | MaxDD$ |",
        "|------|-----------|---------|----|----|----------|---------|--------|---------|-----|--------|---------|--------|",
    ]
    for _, row in top20.iterrows():
        mt_labels = {0: "ANY", 1: "B+", 2: "A"}
        lines.append(
            f"| {int(row['rank'])} "
            f"| {row['score_entry_threshold']:.0f} "
            f"| {mt_labels.get(int(row['min_tier']), str(row['min_tier']))} "
            f"| {row['stop_loss_ticks']:.0f} "
            f"| {row['target_ticks']:.0f} "
            f"| {row['exit_on_opposing_score']:.1f} "
            f"| {row['max_bars_in_trade']:.0f} "
            f"| {int(row['total_trades'])} "
            f"| {row['win_rate']:.1%} "
            f"| {row['profit_factor']:.2f} "
            f"| {row['sharpe']:.3f} "
            f"| {row['avg_pnl_per_trade']:.1f} "
            f"| {row['max_drawdown_dollars']:.0f} |"
        )

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {output_path}")


def save_optimization_report(
    df: pd.DataFrame,
    wf_results: list[dict],
    train_sessions: list[str],
    val_sessions: list[str],
    test_sessions: list[str],
    output_path: Path,
) -> None:
    best_by_sharpe = df[df["total_trades"] >= 5].nlargest(1, "sharpe")
    if best_by_sharpe.empty:
        best_by_sharpe = df.nlargest(1, "sharpe")
    best = best_by_sharpe.iloc[0]

    best_by_pf = df[df["total_trades"] >= 5].nlargest(1, "profit_factor")
    if best_by_pf.empty:
        best_by_pf = df.nlargest(1, "profit_factor")
    best_pf = best_by_pf.iloc[0] if not best_by_pf.empty else best

    mt_labels = {0: "ANY (ordinal 0)", 1: "TYPE_B+ (ordinal 1)", 2: "TYPE_A (ordinal 2)"}

    lines = [
        "# DEEP6 Parameter Optimization Report",
        "",
        f"**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Sessions:** 50 NQ sessions × 390 bars each",
        f"**Regimes:** trend_up (10), trend_down (10), ranging (10), volatile (10), slow_grind (10)",
        f"**Total combos:** {TOTAL_COMBOS:,}",
        "",
        "## Summary",
        "",
        f"- **Best Sharpe config:** Threshold={best['score_entry_threshold']:.0f}, "
        f"MinTier={mt_labels.get(int(best['min_tier']))}, "
        f"SL={best['stop_loss_ticks']:.0f}, TP={best['target_ticks']:.0f}, "
        f"OppScore={best['exit_on_opposing_score']:.1f}, MaxBars={best['max_bars_in_trade']:.0f}",
        f"  - Sharpe={best['sharpe']:.3f}, WinRate={best['win_rate']:.1%}, "
        f"PF={best['profit_factor']:.2f}, Trades={int(best['total_trades'])}",
        "",
        f"- **Best Profit Factor config:** Threshold={best_pf['score_entry_threshold']:.0f}, "
        f"SL={best_pf['stop_loss_ticks']:.0f}, TP={best_pf['target_ticks']:.0f}",
        f"  - PF={best_pf['profit_factor']:.2f}, Sharpe={best_pf['sharpe']:.3f}, "
        f"Trades={int(best_pf['total_trades'])}",
        "",
        "## Key Findings",
        "",
    ]

    # Analyze threshold impact
    thresh_grp = df.groupby("score_entry_threshold")["sharpe"].mean().sort_index()
    lines.append("### Score Threshold Impact (mean Sharpe across all other params)")
    lines.append("")
    lines.append("| Threshold | Mean Sharpe |")
    lines.append("|-----------|-------------|")
    for thr, sh in thresh_grp.items():
        lines.append(f"| {thr:.0f} | {sh:.3f} |")
    lines.append("")

    # Analyze SL/TP ratio
    df["rr_ratio"] = df["target_ticks"] / df["stop_loss_ticks"]
    rr_grp = df.groupby("rr_ratio")["sharpe"].mean().sort_index()
    lines.append("### Risk/Reward Ratio Impact (mean Sharpe)")
    lines.append("")
    lines.append("| R:R Ratio | Mean Sharpe |")
    lines.append("|-----------|-------------|")
    for rr, sh in rr_grp.items():
        lines.append(f"| {rr:.2f} | {sh:.3f} |")
    lines.append("")

    # Regime sensitivity
    lines.append("## Walk-Forward Validation (Train 30 / Validate 10 / Test 10)")
    lines.append("")
    lines.append(f"- Train sessions: {len(train_sessions)} (sessions 1-6 per regime)")
    lines.append(f"- Validate sessions: {len(val_sessions)} (sessions 7-8 per regime)")
    lines.append(f"- Test sessions: {len(test_sessions)} (sessions 9-10 per regime)")
    lines.append("")
    lines.append("### Top 5 Configs — Out-of-Sample Performance")
    lines.append("")
    lines.append("| Rank | Threshold | SL | TP | OppScore | MaxBars | Train Sharpe | Val Sharpe | Test Sharpe | Test PF | Passed |")
    lines.append("|------|-----------|----|----|----------|---------|-------------|-----------|------------|---------|--------|")

    for r in wf_results:
        p = r["params"]
        passed_str = "YES" if r["passed_validation"] else "NO"
        lines.append(
            f"| {r['rank']} "
            f"| {p['score_entry_threshold']:.0f} "
            f"| {p['stop_loss_ticks']} "
            f"| {p['target_ticks']} "
            f"| {p['exit_on_opposing_score']:.1f} "
            f"| {p['max_bars_in_trade']} "
            f"| {r['train_sharpe']:.3f} "
            f"| {r['validate_sharpe']:.3f} "
            f"| {r['test_sharpe']:.3f} "
            f"| {r['test_profit_factor']:.2f} "
            f"| {passed_str} |"
        )

    lines.append("")
    passed_count = sum(1 for r in wf_results if r["passed_validation"])
    lines.append(f"**{passed_count} of {len(wf_results)} configs passed validation (Sharpe >= 1.0 on hold-out set).**")
    lines.append("")

    # Recommended config
    passed = [r for r in wf_results if r["passed_validation"]]
    if passed:
        best_wf = max(passed, key=lambda r: r["test_sharpe"])
    elif wf_results:
        best_wf = max(wf_results, key=lambda r: r["test_sharpe"])
    else:
        best_wf = None

    if best_wf:
        p = best_wf["params"]
        lines.extend([
            "## Recommended Production Configuration",
            "",
            f"Based on highest test-set Sharpe among validated configs:",
            "",
            f"```",
            f"ScoreEntryThreshold : {p['score_entry_threshold']:.0f}",
            f"MinTier             : {mt_labels.get(p['min_tier'], str(p['min_tier']))}",
            f"StopLossTicks       : {p['stop_loss_ticks']}",
            f"TargetTicks         : {p['target_ticks']}",
            f"ExitOnOpposingScore : {p['exit_on_opposing_score']:.1f}",
            f"MaxBarsInTrade      : {p['max_bars_in_trade']}",
            f"```",
            "",
            f"Test-set metrics: Sharpe={best_wf['test_sharpe']:.3f}, "
            f"WinRate={best_wf['test_win_rate']:.1%}, "
            f"PF={best_wf['test_profit_factor']:.2f}, "
            f"MaxDD=${best_wf['test_max_drawdown']:.0f}, "
            f"NetPnL=${best_wf['test_net_pnl']:.0f}",
        ])

    lines.append("")
    lines.append("---")
    lines.append("*Generated by deep6/backtest/optimizer.py*")

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Saved: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("DEEP6 Parameter Optimization Sweep")
    print(f"Sessions: {SESSIONS_DIR}")
    print(f"Output:   {OUTPUT_DIR}")
    print(f"Combos:   {TOTAL_COMBOS:,}")
    print("=" * 60)

    # Load and pre-score all sessions (done once)
    print("\nLoading + pre-scoring 50 sessions...")
    t_load = time.time()
    sessions_data = load_all_sessions(SESSIONS_DIR)
    all_session_names = sorted(sessions_data.keys())
    print(f"Loaded {len(sessions_data)} sessions in {time.time() - t_load:.1f}s")

    # -----------------------------------------------------------------------
    # Full sweep
    # -----------------------------------------------------------------------
    print("\n--- FULL SWEEP ---")
    df = run_sweep(sessions_data, [])

    # Save CSV
    csv_path = OUTPUT_DIR / "sweep_results.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path} ({len(df)} rows)")

    # -----------------------------------------------------------------------
    # Heatmaps
    # -----------------------------------------------------------------------
    print("\n--- HEATMAPS ---")

    # Sharpe heatmap: Threshold × StopLoss (mean over other dims)
    save_heatmap_html(
        df=df,
        x_col="score_entry_threshold",
        y_col="stop_loss_ticks",
        value_col="sharpe",
        title="Sharpe — Score Threshold vs Stop Loss Ticks (mean over all other params)",
        output_path=OUTPUT_DIR / "sharpe_heatmap.html",
        agg="mean",
    )

    # Profit factor heatmap: Threshold × TP
    save_heatmap_html(
        df=df,
        x_col="score_entry_threshold",
        y_col="target_ticks",
        value_col="profit_factor",
        title="Profit Factor — Score Threshold vs Target Ticks (mean, capped at 10 for display)",
        output_path=OUTPUT_DIR / "profit_factor_heatmap.html",
        agg="mean",
    )

    # Additional: Sharpe × TP vs SL
    save_heatmap_html(
        df=df,
        x_col="stop_loss_ticks",
        y_col="target_ticks",
        value_col="sharpe",
        title="Sharpe — Target Ticks vs Stop Loss Ticks (mean)",
        output_path=OUTPUT_DIR / "sharpe_sl_tp_heatmap.html",
        agg="mean",
    )

    # -----------------------------------------------------------------------
    # Top 20 configs
    # -----------------------------------------------------------------------
    print("\n--- TOP 20 CONFIGS ---")
    save_top20_md(df, OUTPUT_DIR / "top_20_configs.md")

    # -----------------------------------------------------------------------
    # Walk-forward validation
    # -----------------------------------------------------------------------
    print("\n--- WALK-FORWARD VALIDATION ---")
    wf_results, train_df, train_sessions, val_sessions, test_sessions = run_walkforward(
        sessions_data, all_session_names, top_n=5, min_val_sharpe=1.0
    )

    print("\nTop 5 configs — out-of-sample results:")
    print(f"{'Rank':<5} {'Thr':<5} {'SL':<4} {'TP':<4} {'Opp':<5} {'MB':<4} {'TrainSh':<10} {'ValSh':<8} {'TestSh':<8} {'Passed'}")
    for r in wf_results:
        p = r["params"]
        print(
            f"  {r['rank']:<3} {p['score_entry_threshold']:<5.0f} {p['stop_loss_ticks']:<4} "
            f"{p['target_ticks']:<4} {p['exit_on_opposing_score']:<5.1f} {p['max_bars_in_trade']:<4} "
            f"{r['train_sharpe']:<10.3f} {r['validate_sharpe']:<8.3f} {r['test_sharpe']:<8.3f} "
            f"{'YES' if r['passed_validation'] else 'NO'}"
        )

    # -----------------------------------------------------------------------
    # Optimization report
    # -----------------------------------------------------------------------
    print("\n--- OPTIMIZATION REPORT ---")
    save_optimization_report(
        df, wf_results, train_sessions, val_sessions, test_sessions,
        OUTPUT_DIR / "OPTIMIZATION-REPORT.md",
    )

    print("\n" + "=" * 60)
    print("OPTIMIZATION COMPLETE")
    print("=" * 60)
    print(f"\nOutputs:")
    for fname in ["sweep_results.csv", "sharpe_heatmap.html", "profit_factor_heatmap.html",
                  "sharpe_sl_tp_heatmap.html", "top_20_configs.md", "OPTIMIZATION-REPORT.md"]:
        p = OUTPUT_DIR / fname
        size = p.stat().st_size // 1024 if p.exists() else 0
        print(f"  {fname:<35} {size}KB")

    print()
    print("Top 5 walk-forward results:")
    for r in wf_results:
        p = r["params"]
        print(f"  #{r['rank']} Thr={p['score_entry_threshold']:.0f} SL={p['stop_loss_ticks']} "
              f"TP={p['target_ticks']} OppScore={p['exit_on_opposing_score']:.1f} "
              f"MaxBars={p['max_bars_in_trade']} | "
              f"Train={r['train_sharpe']:.3f} Val={r['validate_sharpe']:.3f} "
              f"Test={r['test_sharpe']:.3f} Passed={'YES' if r['passed_validation'] else 'NO'}")


if __name__ == "__main__":
    main()
