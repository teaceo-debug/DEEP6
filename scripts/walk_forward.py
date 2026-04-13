"""Phase 7 walk-forward validation — TEST-05, TEST-07.

Implements purged walk-forward efficiency (WFE) gate:
- Split bars into N folds (train + OOS with purge gap)
- Per fold: optimize thresholds on IS bars via Optuna (30 trials)
- Test best IS params on OOS bars
- WFE = mean(OOS P&L) / mean(IS P&L) — must be >= 0.70 to pass gate
- Passing: writes best_params.json; Failing: sys.exit(1)

TEST-07: determinism check — two runs on same bars must produce identical results.

Usage:
    python scripts/walk_forward.py \\
        --start 2026-04-07 --end 2026-04-11 \\
        --folds 5 --trials 30 --output best_params.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep6.engines.signal_config import (
    ScorerConfig,
    AbsorptionConfig,
    ExhaustionConfig,
    DeltaConfig,
)
from scripts.sweep_thresholds import run_backtest_with_configs, make_objective


# ---------------------------------------------------------------------------
# Fold splitting with purge gap (D-10: prevents future leakage, TEST-05)
# ---------------------------------------------------------------------------

def split_folds(
    bars: list,
    n_folds: int = 5,
    oos_frac: float = 0.20,
    purge_bars: int = 10,
) -> list[tuple[list, list]]:
    """Split bars into (train, oos) fold pairs with purge gaps.

    Purge gap prevents leakage from signals with multi-bar lookback.
    Per D-10: purged splits prevent future leakage (TEST-05).

    Walk-forward structure:
        [=====IS=====][PURGE][===OOS===][PURGE][=====IS=====][PURGE][===OOS===]
         fold 1 train  gap   fold 1 test gap    fold 2 train  gap   fold 2 test

    Each fold's OOS window is a non-overlapping slice at the end of the data.
    The train window uses all bars before the purge gap preceding OOS.

    Returns: list of (train_bars, oos_bars) tuples
    """
    n = len(bars)
    oos_size = int(n * oos_frac)
    folds = []

    for fold_idx in range(n_folds):
        # Walk forward: each fold's OOS is a non-overlapping window from the end
        oos_start = n - (n_folds - fold_idx) * oos_size
        oos_end = oos_start + oos_size
        if oos_start <= 0:
            continue

        # Purge: exclude bars immediately before OOS start
        train_end = oos_start - purge_bars
        if train_end <= 10:
            continue

        train_bars = bars[:train_end]
        oos_bars = bars[oos_start:oos_end]

        if len(oos_bars) < 20:  # min meaningful OOS window
            continue

        folds.append((train_bars, oos_bars))

    return folds


# ---------------------------------------------------------------------------
# WFE computation and gate (D-09: WFE > 70% gate)
# ---------------------------------------------------------------------------

def compute_wfe(is_pnls: list[float], oos_pnls: list[float]) -> float:
    """Walk-forward efficiency = mean(OOS) / mean(IS).

    Returns 0.0 if IS P&L mean is <= 0 (avoids division by near-zero / negative).
    Per D-09: WFE > 70% is required before any weight file is applied.
    """
    mean_is = float(np.mean(is_pnls)) if is_pnls else 0.0
    mean_oos = float(np.mean(oos_pnls)) if oos_pnls else 0.0
    if mean_is <= 0:
        return 0.0
    return float(mean_oos / mean_is)


def wfe_gate(wfe: float, threshold: float = 0.70) -> bool:
    """Return True if WFE meets or exceeds threshold. False = GATE FAILED.

    T-07-07: best_params.json is written ONLY when this gate passes.
    Human checkpoint additionally gates application to live engine.
    """
    return wfe >= threshold


# ---------------------------------------------------------------------------
# Single fold runner
# ---------------------------------------------------------------------------

def run_fold(
    train_bars: list,
    oos_bars: list,
    n_trials: int = 30,
    fold_idx: int = 0,
) -> dict:
    """Optimize on IS bars via Optuna, evaluate best params on OOS bars.

    Returns fold metrics dict with is_pnl, oos_pnl, best_params, signal counts.
    """
    print(f"  Fold {fold_idx + 1}: IS={len(train_bars)} bars, OOS={len(oos_bars)} bars")

    # In-sample Optuna optimization
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42 + fold_idx),
    )
    study.optimize(make_objective(train_bars), n_trials=n_trials)

    best_params = study.best_trial.params
    is_pnl = study.best_value

    # Reconstruct config objects from best trial params (use defaults for missing keys)
    def get(key, default):
        return best_params.get(key, default)

    scorer_cfg = ScorerConfig(
        type_a_min=get("type_a_min", 80.0),
        type_b_min=get("type_b_min", 65.0),
        type_c_min=get("type_c_min", 50.0),
        confluence_threshold=int(get("confluence_threshold", 5)),
        zone_high_min=get("zone_high_min", 50.0),
        zone_high_bonus=get("zone_high_bonus", 8.0),
        zone_mid_bonus=get("zone_mid_bonus", 6.0),
    )
    abs_cfg = AbsorptionConfig(
        absorb_wick_min=get("absorb_wick_min", 30.0),
        absorb_delta_max=get("absorb_delta_max", 0.12),
        stop_vol_mult=get("stop_vol_mult", 2.0),
        evr_vol_mult=get("evr_vol_mult", 1.5),
    )
    exh_cfg = ExhaustionConfig(
        exhaust_wick_min=get("exhaust_wick_min", 35.0),
        fade_threshold=get("fade_threshold", 0.60),
    )
    delta_cfg = DeltaConfig(
        tail_threshold=get("tail_threshold", 0.95),
        trap_delta_ratio=get("trap_delta_ratio", 0.3),
    )

    # OOS evaluation with best IS params
    oos_results = run_backtest_with_configs(oos_bars, scorer_cfg, abs_cfg, exh_cfg, delta_cfg)
    tradeable_oos = [r for r in oos_results if r["tier"] in ("TYPE_A", "TYPE_B")]
    oos_pnl = sum(r["pnl_3bar"] for r in tradeable_oos) if tradeable_oos else 0.0

    print(f"    IS P&L={is_pnl:.2f}, OOS P&L={oos_pnl:.2f}, OOS signals={len(tradeable_oos)}")

    return {
        "fold": fold_idx + 1,
        "is_bars": len(train_bars),
        "oos_bars": len(oos_bars),
        "is_pnl": round(is_pnl, 2),
        "oos_pnl": round(oos_pnl, 2),
        "oos_signals": len(tradeable_oos),
        "best_params": best_params,
    }


# ---------------------------------------------------------------------------
# TEST-07: Determinism check
# ---------------------------------------------------------------------------

def check_determinism(bars: list) -> bool:
    """TEST-07: Two runs on same bars + same config must produce identical results.

    Non-deterministic signals indicate stateful shared global state that would
    produce different backtest results across session restarts.
    Returns True if deterministic, False if mismatch found.
    """
    cfg = ScorerConfig()
    abs_cfg = AbsorptionConfig()
    exh_cfg = ExhaustionConfig()
    delta_cfg = DeltaConfig()

    sample_bars = bars[:100] if len(bars) >= 100 else bars

    r1 = run_backtest_with_configs(sample_bars, cfg, abs_cfg, exh_cfg, delta_cfg)
    r2 = run_backtest_with_configs(sample_bars, cfg, abs_cfg, exh_cfg, delta_cfg)

    for i, (a, b) in enumerate(zip(r1, r2)):
        if abs(a["pnl_3bar"] - b["pnl_3bar"]) > 0.001:
            print(f"  DETERMINISM FAIL at bar {i}: run1={a['pnl_3bar']} run2={b['pnl_3bar']}")
            return False
        if a["tier"] != b["tier"]:
            print(f"  DETERMINISM FAIL at bar {i}: tier {a['tier']} vs {b['tier']}")
            return False

    print(f"  Determinism: PASS ({len(r1)} bars identical across 2 runs)")
    return True


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DEEP6 Walk-Forward Validation (TEST-05, TEST-07)")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--folds", type=int, default=5, help="Number of walk-forward folds (default 5)")
    parser.add_argument("--trials", type=int, default=30, help="Optuna trials per fold (default 30)")
    parser.add_argument("--output", default="best_params.json", help="Output JSON path for gate-passing params")
    parser.add_argument("--bar-seconds", type=int, default=60, help="Bar duration in seconds (default 60)")
    parser.add_argument("--wfe-threshold", type=float, default=0.70, help="WFE gate threshold (default 0.70)")
    args = parser.parse_args()

    # Security: API key from env only (T-07-04)
    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("DATABENTO_API_KEY", "")
        except ImportError:
            pass
    if not api_key:
        print("ERROR: Set DATABENTO_API_KEY in environment or .env file")
        sys.exit(1)

    import databento as db
    from scripts.backtest_signals import build_bars

    print(f"Fetching NQ trades {args.start} to {args.end}...")
    client = db.Historical(key=api_key)
    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        schema="trades",
        stype_in="continuous",
        symbols=["NQ.c.0"],
        start=f"{args.start}T13:30:00",
        end=f"{args.end}T20:00:00",
    )
    bars = build_bars(data, bar_seconds=args.bar_seconds)
    print(f"Built {len(bars)} bars")

    if len(bars) < 50:
        print("ERROR: Not enough bars for walk-forward validation (need >= 50)")
        sys.exit(1)

    # TEST-07: Determinism check first
    print("\nChecking signal determinism (TEST-07)...")
    det_ok = check_determinism(bars)
    if not det_ok:
        print("WARNING: Non-deterministic signals detected — investigate before relying on backtest results")

    # Split and run walk-forward folds
    print(f"\nRunning {args.folds}-fold walk-forward (purge=10 bars, {args.trials} trials/fold)...")
    folds = split_folds(bars, n_folds=args.folds, oos_frac=0.20, purge_bars=10)
    if not folds:
        print("ERROR: Not enough bars to create valid folds")
        sys.exit(1)

    print(f"Created {len(folds)} folds")
    fold_results = []
    for i, (train, oos) in enumerate(folds):
        result = run_fold(train, oos, n_trials=args.trials, fold_idx=i)
        fold_results.append(result)

    # Compute WFE
    is_pnls = [f["is_pnl"] for f in fold_results]
    oos_pnls = [f["oos_pnl"] for f in fold_results]
    wfe = compute_wfe(is_pnls, oos_pnls)

    # Print summary table
    print(f"\n{'=' * 60}")
    print(f"WALK-FORWARD RESULTS: {len(fold_results)} folds")
    print(f"{'=' * 60}")
    print(f"{'Fold':<6} {'IS P&L':>10} {'OOS P&L':>10} {'OOS Sigs':>10}")
    print(f"{'-' * 40}")
    for f in fold_results:
        print(f"{f['fold']:<6} {f['is_pnl']:>+10.2f} {f['oos_pnl']:>+10.2f} {f['oos_signals']:>10}")
    print(f"{'-' * 40}")
    print(f"{'MEAN':<6} {np.mean(is_pnls):>+10.2f} {np.mean(oos_pnls):>+10.2f}")
    print(f"\nWFE = {wfe:.3f} (threshold: {args.wfe_threshold})")

    # WFE gate decision (D-09, T-07-07)
    gate_pass = wfe_gate(wfe, args.wfe_threshold)
    if gate_pass:
        print(f"GATE PASSED: WFE={wfe:.3f} >= {args.wfe_threshold}")
        # Select best fold by highest OOS P&L
        best_fold = max(fold_results, key=lambda f: f["oos_pnl"])
        output = {
            "wfe": round(wfe, 4),
            "gate_threshold": args.wfe_threshold,
            "gate_status": "PASS",
            "best_fold": best_fold["fold"],
            "fold_count": len(fold_results),
            "params": best_fold["best_params"],
            "fold_breakdown": [
                {"fold": f["fold"], "is_pnl": f["is_pnl"], "oos_pnl": f["oos_pnl"]}
                for f in fold_results
            ],
        }
        with open(args.output, "w") as fp:
            json.dump(output, fp, indent=2)
        print(f"Wrote {args.output}")
        print("NOTE: Human checkpoint required before treating best_params.json as authoritative (T-07-07)")
    else:
        print(f"GATE FAILED: WFE={wfe:.3f} < {args.wfe_threshold}")
        print("No best_params.json written. Investigate signal quality before rerunning.")
        sys.exit(1)


if __name__ == "__main__":
    main()
