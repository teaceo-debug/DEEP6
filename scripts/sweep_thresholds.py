"""Phase 7 parameter sweep — Optuna Bayesian optimization over ScorerConfig thresholds.

Uses identical Databento replay code path as live engine (D-06).
Sweeps ScorerConfig + AbsorptionConfig + ImbalanceConfig + DeltaConfig thresholds.
Outputs ranked CSV by total 3-bar P&L for TYPE_A/B signals (TEST-04, TEST-06).

Signal P&L attribution per category (absorption vs delta vs auction etc) is printed
after the sweep and visible in the output CSV via categories_list column.

Security note (T-07-04): DATABENTO_API_KEY read from env/dotenv only — never hardcoded.

Usage:
    python scripts/sweep_thresholds.py \\
        --start 2026-04-09 --end 2026-04-10 \\
        --trials 100 --output sweep_results.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np
import optuna

optuna.logging.set_verbosity(optuna.logging.WARNING)

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import databento as db

from deep6.engines.signal_config import (
    AbsorptionConfig,
    DeltaConfig,
    ExhaustionConfig,
    ImbalanceConfig,
    ScorerConfig,
)
from deep6.engines.auction import AuctionEngine
from deep6.engines.delta import DeltaEngine
from deep6.engines.exhaustion import reset_cooldowns
from deep6.engines.narrative import classify_bar
from deep6.engines.poc import POCEngine
from deep6.engines.volume_profile import SessionProfile
from deep6.scoring.scorer import score_bar, SignalTier
from deep6.state.footprint import FootprintBar

# Re-use build_bars from existing backtest pipeline (D-06: same code path)
from scripts.backtest_signals import build_bars


# ---------------------------------------------------------------------------
# Core backtest runner with injectable configs
# ---------------------------------------------------------------------------

def run_backtest_with_configs(
    bars: list[FootprintBar],
    scorer_cfg: ScorerConfig,
    abs_cfg: AbsorptionConfig,
    exh_cfg: ExhaustionConfig,
    delta_cfg: DeltaConfig,
) -> list[dict]:
    """Run full signal pipeline with injected configs — mirrors backtest_signals.run_backtest.

    D-06: uses the same engine code path as the live system.
    ImbalanceConfig is not yet injectable via classify_bar (no imb_cfg kwarg in narrative.py);
    TODO: wire ImbalanceConfig when classify_bar is updated to accept it.
    """
    # Engines with config injection
    delta_eng = DeltaEngine(config=delta_cfg)
    auction_eng = AuctionEngine()
    poc_eng = POCEngine()
    profile = SessionProfile()
    reset_cooldowns()

    results = []
    vol_ema = 1000.0

    for i, bar in enumerate(bars):
        if i > 0:
            vol_ema = vol_ema * 0.95 + bar.total_vol * 0.05

        # Volume profile
        profile.add_bar(bar)
        if i > 0 and i % 10 == 0:
            profile.detect_zones(bar.close)
        profile.update_zones(bar, i)

        # Narrative cascade with abs + exh config injection
        # Note: ImbalanceConfig not yet accepted by classify_bar — uses engine defaults
        narrative = classify_bar(
            bar,
            prior_bar=bars[i - 1] if i > 0 else None,
            bar_index=i,
            atr=15.0,
            vol_ema=vol_ema,
            abs_config=abs_cfg,
            exh_config=exh_cfg,
        )

        delta_sigs = delta_eng.process(bar)
        auction_sigs = auction_eng.process(bar)
        poc_sigs = poc_eng.process(bar)
        active_zones = profile.get_active_zones(min_score=20)

        bar_index_in_session = i % 390
        result = score_bar(
            narrative=narrative,
            delta_signals=delta_sigs,
            auction_signals=auction_sigs,
            poc_signals=poc_sigs,
            active_zones=active_zones,
            bar_close=bar.close,
            scorer_config=scorer_cfg,
            abs_config=abs_cfg,
            bar_delta=bar.bar_delta,
            bar_index_in_session=bar_index_in_session,
        )

        close_3 = bars[i + 3].close if i + 3 < len(bars) else bar.close

        results.append({
            "tier": result.tier.name,
            "direction": result.direction,
            "score": round(result.total_score, 1),
            "categories": result.category_count,
            "categories_list": "|".join(result.categories_firing),
            "pnl_3bar": round((close_3 - bar.close) * result.direction, 2),
        })

    return results


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------

def make_objective(bars: list[FootprintBar]):
    """Factory returning an Optuna objective over ScorerConfig + signal configs."""

    def objective(trial: optuna.Trial) -> float:
        # --- ScorerConfig thresholds ---
        scorer_cfg = ScorerConfig(
            type_a_min=trial.suggest_float("type_a_min", 70.0, 90.0),
            type_b_min=trial.suggest_float("type_b_min", 55.0, 75.0),
            type_c_min=trial.suggest_float("type_c_min", 42.0, 58.0),
            confluence_threshold=trial.suggest_int("confluence_threshold", 4, 6),
            zone_high_min=trial.suggest_float("zone_high_min", 40.0, 60.0),
            zone_high_bonus=trial.suggest_float("zone_high_bonus", 6.0, 10.0),
            zone_mid_bonus=trial.suggest_float("zone_mid_bonus", 4.0, 8.0),
        )

        # --- AbsorptionConfig thresholds ---
        abs_cfg = AbsorptionConfig(
            absorb_wick_min=trial.suggest_float("absorb_wick_min", 20.0, 45.0),
            absorb_delta_max=trial.suggest_float("absorb_delta_max", 0.08, 0.18),
            stop_vol_mult=trial.suggest_float("stop_vol_mult", 1.5, 3.0),
            evr_vol_mult=trial.suggest_float("evr_vol_mult", 1.2, 2.0),
        )

        # --- ExhaustionConfig thresholds ---
        exh_cfg = ExhaustionConfig(
            exhaust_wick_min=trial.suggest_float("exhaust_wick_min", 25.0, 50.0),
            fade_threshold=trial.suggest_float("fade_threshold", 0.50, 0.75),
        )

        # --- DeltaConfig thresholds ---
        delta_cfg = DeltaConfig(
            tail_threshold=trial.suggest_float("tail_threshold", 0.85, 0.98),
            trap_delta_ratio=trial.suggest_float("trap_delta_ratio", 0.2, 0.45),
        )

        results = run_backtest_with_configs(bars, scorer_cfg, abs_cfg, exh_cfg, delta_cfg)

        # Objective: total 3-bar P&L for TYPE_A and TYPE_B signals only (TEST-04)
        tradeable = [r for r in results if r["tier"] in ("TYPE_A", "TYPE_B")]
        if not tradeable:
            return -9999.0  # Penalize configs that produce zero tradeable signals

        return sum(r["pnl_3bar"] for r in tradeable)

    return objective


# ---------------------------------------------------------------------------
# Signal P&L attribution (TEST-06)
# ---------------------------------------------------------------------------

def compute_attribution(results: list[dict]) -> dict:
    """Per-category signal attribution — which categories drove P&L.

    TEST-06: Signal P&L attribution per category type visible in output.
    Categories: absorption, exhaustion, imbalance, delta, auction, poc,
                volume_profile, trapped.
    """
    attr: dict[str, dict] = {}
    for r in results:
        if r["tier"] in ("TYPE_A", "TYPE_B", "TYPE_C"):
            for cat in r["categories_list"].split("|"):
                cat = cat.strip()
                if cat:
                    if cat not in attr:
                        attr[cat] = {"count": 0, "total_pnl": 0.0, "wins": 0}
                    attr[cat]["count"] += 1
                    attr[cat]["total_pnl"] += r["pnl_3bar"]
                    if r["pnl_3bar"] > 0:
                        attr[cat]["wins"] += 1
    return attr


# ---------------------------------------------------------------------------
# Portfolio metrics (numpy fallback — avoids vectorbt heavy deps in CI)
# ---------------------------------------------------------------------------

def compute_portfolio_metrics(results: list[dict], tier_filter: tuple[str, ...] = ("TYPE_A", "TYPE_B")) -> dict:
    """Compute basic portfolio metrics for a backtest result set.

    Uses numpy directly — vectorbt is available (0.28.5) for deeper analysis
    but numpy gives portable metrics without numba JIT warm-up cost.
    """
    pnls = np.array([r["pnl_3bar"] for r in results if r["tier"] in tier_filter], dtype=float)
    if len(pnls) == 0:
        return {"n_trades": 0, "total_pnl": 0.0, "win_rate": 0.0, "sharpe": 0.0, "avg_pnl": 0.0}

    wins = np.sum(pnls > 0)
    total = len(pnls)
    avg = float(np.mean(pnls))
    std = float(np.std(pnls))
    sharpe = (avg / std * np.sqrt(252)) if std > 0 else 0.0  # annualized approximation

    return {
        "n_trades": total,
        "total_pnl": float(np.sum(pnls)),
        "win_rate": float(wins / total),
        "sharpe": round(sharpe, 3),
        "avg_pnl": round(avg, 3),
    }


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="DEEP6 Threshold Sweep via Optuna — Bayesian optimization of ScorerConfig + signal thresholds"
    )
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD (Databento fetch)")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD (Databento fetch)")
    parser.add_argument("--trials", type=int, default=50, help="Number of Optuna trials (default 50)")
    parser.add_argument("--output", default="sweep_results.csv", help="Output CSV path")
    parser.add_argument("--bar-seconds", type=int, default=60, help="Bar duration in seconds (default 60)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip Databento fetch — use 200 synthetic bars for import/syntax verification"
    )
    args = parser.parse_args()

    # --- Load Databento API key (T-07-04: env/dotenv only — never hardcoded) ---
    api_key = os.environ.get("DATABENTO_API_KEY", "")
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.environ.get("DATABENTO_API_KEY", "")
        except ImportError:
            pass

    if args.dry_run:
        print("[dry-run] Generating synthetic bars for import verification...")
        bars = _make_synthetic_bars(200)
    else:
        if not api_key:
            print("ERROR: DATABENTO_API_KEY not set. Use .env file or export the variable.")
            sys.exit(1)

        # Fetch data via Databento — D-06: identical code path as live engine
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

    # --- Run Optuna study ---
    print(f"Starting {args.trials} Optuna trials (TPE sampler, seed=42)...")
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name="deep6_threshold_sweep",
    )
    study.optimize(make_objective(bars), n_trials=args.trials, show_progress_bar=True)

    best = study.best_trial
    print(f"\nBest trial #{best.number}: P&L = {best.value:.2f}")
    print("Best params:")
    for k, v in sorted(best.params.items()):
        print(f"  {k}: {v}")

    # --- Export all trials ranked by P&L ---
    trials_data = []
    for t in study.trials:
        if t.value is not None and t.value > -9999.0:
            row = {"trial": t.number, "pnl": round(t.value, 2)}
            row.update(t.params)
            trials_data.append(row)
    trials_data.sort(key=lambda r: r["pnl"], reverse=True)

    if trials_data:
        with open(args.output, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=trials_data[0].keys())
            writer.writeheader()
            writer.writerows(trials_data)
        print(f"\nWrote {len(trials_data)} trial results to {args.output}")

    # --- Portfolio metrics for best config ---
    if best.params:
        best_scorer_cfg = ScorerConfig(
            type_a_min=best.params.get("type_a_min", 80.0),
            type_b_min=best.params.get("type_b_min", 65.0),
            type_c_min=best.params.get("type_c_min", 50.0),
            confluence_threshold=best.params.get("confluence_threshold", 5),
            zone_high_min=best.params.get("zone_high_min", 50.0),
            zone_high_bonus=best.params.get("zone_high_bonus", 8.0),
            zone_mid_bonus=best.params.get("zone_mid_bonus", 6.0),
        )
        best_abs_cfg = AbsorptionConfig(
            absorb_wick_min=best.params.get("absorb_wick_min", 30.0),
            absorb_delta_max=best.params.get("absorb_delta_max", 0.12),
            stop_vol_mult=best.params.get("stop_vol_mult", 2.0),
            evr_vol_mult=best.params.get("evr_vol_mult", 1.5),
        )
        best_exh_cfg = ExhaustionConfig(
            exhaust_wick_min=best.params.get("exhaust_wick_min", 35.0),
            fade_threshold=best.params.get("fade_threshold", 0.60),
        )
        best_delta_cfg = DeltaConfig(
            tail_threshold=best.params.get("tail_threshold", 0.95),
            trap_delta_ratio=best.params.get("trap_delta_ratio", 0.3),
        )

        best_results = run_backtest_with_configs(
            bars, best_scorer_cfg, best_abs_cfg, best_exh_cfg, best_delta_cfg
        )

        metrics = compute_portfolio_metrics(best_results)
        print(f"\nPORTFOLIO METRICS (best config, TYPE_A + TYPE_B):")
        print(f"  Trades:    {metrics['n_trades']}")
        print(f"  Total P&L: {metrics['total_pnl']:+.2f} pts")
        print(f"  Win rate:  {metrics['win_rate']:.1%}")
        print(f"  Avg P&L:   {metrics['avg_pnl']:+.3f} pts/trade")
        print(f"  Sharpe:    {metrics['sharpe']:.3f} (annualized approx)")

        # --- Signal P&L attribution per category (TEST-06) ---
        attribution = compute_attribution(best_results)
        if attribution:
            print(f"\nSIGNAL P&L ATTRIBUTION (best config, TYPE_A/B/C signals):")
            print(f"{'Category':<22} {'Count':>6} {'Total P&L':>12} {'Win%':>8}")
            print(f"{'-' * 52}")
            for cat, d in sorted(attribution.items(), key=lambda x: x[1]["total_pnl"], reverse=True):
                win_pct = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
                print(f"{cat:<22} {d['count']:>6} {d['total_pnl']:>+12.2f} {win_pct:>7.1f}%")
        else:
            print("\nNo TYPE_A/B/C signals found with best config — check threshold ranges.")


def _make_synthetic_bars(n: int = 200) -> list[FootprintBar]:
    """Generate synthetic FootprintBars for dry-run / import verification.

    Bars have realistic NQ price (18000-19000 range), non-zero volume,
    and a mix of sides to exercise all signal engines.
    """
    rng = np.random.default_rng(seed=0)
    bars = []
    price = 18500.0
    cvd = 0.0

    for i in range(n):
        bar = FootprintBar()
        # Simulate ~30 trades per bar
        n_trades = int(rng.integers(15, 45))
        for _ in range(n_trades):
            price += float(rng.normal(0, 0.5))
            price = max(17500.0, min(19500.0, price))
            size = int(rng.integers(1, 8))
            side = 1 if rng.random() > 0.5 else 2  # 1=ask, 2=bid
            bar.add_trade(price, size, side)

        bar.finalize(prior_cvd=cvd)
        bar.timestamp = 1744200000 + i * 60  # synthetic epoch
        cvd = bar.cvd
        bars.append(bar)

    return bars


if __name__ == "__main__":
    main()
