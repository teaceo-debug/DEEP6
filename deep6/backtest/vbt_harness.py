"""vbt_harness: vectorbt integration CLI for DEEP6 backtest engine.

Modes:
  import      -- Read a CSV of trades produced by CsvTradeExporter, build a
                 vectorbt Portfolio, emit stats JSON + HTML report.
  sweep       -- Run a parameter grid over session NDJSON files using the
                 Python-side trade simulator; produce a Sharpe heatmap.
  walkforward -- 60/20/20 train/validate/test split on session files;
                 find best params on train, validate, report out-of-sample.

Usage:
  python3 -m deep6.backtest.vbt_harness --mode import  --trades-csv PATH   --output-dir DIR
  python3 -m deep6.backtest.vbt_harness --mode sweep   --sessions-dir DIR  --output-dir DIR
  python3 -m deep6.backtest.vbt_harness --mode walkforward --sessions-dir DIR --output-dir DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Soft-import vectorbt — harness still importable even if vbt not installed
# ---------------------------------------------------------------------------
try:
    import vectorbt as vbt
    _VBT_AVAILABLE = True
except ImportError:
    _VBT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Python-side scorer imports (used by sweep/walkforward)
# ---------------------------------------------------------------------------
try:
    from deep6.scoring.replay_scorer import build_scorer_inputs  # type: ignore
    _SCORER_AVAILABLE = True
except ImportError:
    _SCORER_AVAILABLE = False


# ===========================================================================
# Shared: Python-side trade simulator
# Mirrors BacktestRunner.cs exit priority: stop-loss → target → opposing → max_bars → session_end
# ===========================================================================

class _SimConfig:
    """Lightweight backtest config for the Python-side simulator."""

    def __init__(
        self,
        slippage_ticks: float = 1.0,
        stop_loss_ticks: int = 20,
        target_ticks: int = 40,
        max_bars_in_trade: int = 30,
        exit_on_opposing_score: float = 0.50,
        score_entry_threshold: float = 80.0,
        min_tier: str = "TYPE_A",
        tick_size: float = 0.25,
        tick_value: float = 5.0,
        initial_capital: float = 50_000.0,
        contracts_per_trade: int = 1,
    ):
        self.slippage_ticks = slippage_ticks
        self.stop_loss_ticks = stop_loss_ticks
        self.target_ticks = target_ticks
        self.max_bars_in_trade = max_bars_in_trade
        self.exit_on_opposing_score = exit_on_opposing_score
        self.score_entry_threshold = score_entry_threshold
        # Map tier string to ordinal matching C# SignalTier enum
        _TIER_ORDINALS = {"DISQUALIFIED": -1, "QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
        self.min_tier_ordinal = _TIER_ORDINALS.get(min_tier, 3)
        self.tick_size = tick_size
        self.tick_value = tick_value
        self.initial_capital = initial_capital
        self.contracts_per_trade = contracts_per_trade


_TIER_ORDINALS = {"DISQUALIFIED": -1, "QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}


def _load_scored_bars_from_ndjson(path: Path) -> list[dict]:
    """Load scored_bar records from an NDJSON file."""
    bars = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "scored_bar":
                bars.append(obj)
    return bars


def _score_bar_simple(bar: dict) -> dict:
    """Lightweight scorer: derive direction + score from signal strengths.

    This mirrors the C# ConfluenceScorer category logic but uses a simplified
    formula sufficient for parameter sweep purposes. The C# engine is the
    canonical scorer; this Python version is used only for sweep/walkforward.

    Returns dict with keys: direction (int), total_score (float), tier (str),
    entry_price (float).
    """
    signals = bar.get("signals", [])
    zone_score = float(bar.get("zoneScore", 0.0))
    zone_dist = float(bar.get("zoneDistTicks", 1e9))
    bars_since_open = int(bar.get("barsSinceOpen", 0))
    bar_delta = int(bar.get("barDelta", 0))
    bar_close = float(bar.get("barClose", 0.0))

    # Category weights (verbatim from ConfluenceScorer.cs)
    W = {
        "absorption": 25.0, "exhaustion": 18.0, "trapped": 14.0,
        "delta": 13.0, "imbalance": 12.0, "volume_profile": 10.0,
        "auction": 8.0, "poc": 1.0,
    }
    VOTING_DELTA  = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
    VOTING_AUCT   = {"AUCT-01", "AUCT-02", "AUCT-05"}
    VOTING_POC    = {"POC-02",  "POC-07",  "POC-08"}

    bull_w = 0.0
    bear_w = 0.0
    cats_bull: set[str] = set()
    cats_bear: set[str] = set()
    stacked_bull = 0
    stacked_bear = 0
    max_bull_str = 0.0
    max_bear_str = 0.0

    for sig in signals:
        sid = sig.get("signalId", "")
        d = int(sig.get("direction", 0))
        s = float(sig.get("strength", 0.0))
        if d == 0:
            continue

        def _add(direction_is_bull: bool, cat: str) -> None:
            nonlocal bull_w, bear_w, max_bull_str, max_bear_str
            if direction_is_bull:
                bull_w += s
                cats_bull.add(cat)
                max_bull_str = max(max_bull_str, s)
            else:
                bear_w += s
                cats_bear.add(cat)
                max_bear_str = max(max_bear_str, s)

        if sid.startswith("ABS"):
            _add(d > 0, "absorption")
        elif sid.startswith("EXH"):
            _add(d > 0, "exhaustion")
        elif sid.startswith("TRAP"):
            _add(d > 0, "trapped")
        elif sid.startswith("IMB"):
            # Stacked imbalance dedup
            tier_n = 0
            for suffix in ("-T3", "-T2", "-T1"):
                if sid.endswith(suffix):
                    tier_n = int(suffix[-1])
                    break
            if tier_n == 0 and "STACKED_T" in sig.get("detail", ""):
                detail = sig.get("detail", "")
                idx = detail.find("STACKED_T")
                if idx >= 0 and idx + 9 < len(detail):
                    try:
                        tier_n = int(detail[idx + 9])
                    except ValueError:
                        tier_n = 1
            if tier_n > 0:
                if d > 0:
                    stacked_bull = max(stacked_bull, tier_n)
                    max_bull_str = max(max_bull_str, s)
                else:
                    stacked_bear = max(stacked_bear, tier_n)
                    max_bear_str = max(max_bear_str, s)
        elif sid in VOTING_DELTA:
            _add(d > 0, "delta")
        elif sid in VOTING_AUCT:
            _add(d > 0, "auction")
        elif sid in VOTING_POC:
            _add(d > 0, "poc")

    if stacked_bull > 0:
        bull_w += 0.5
        cats_bull.add("imbalance")
    if stacked_bear > 0:
        bear_w += 0.5
        cats_bear.add("imbalance")

    if bull_w > bear_w:
        direction = 1
        cats = cats_bull
        max_str = max_bull_str
    elif bear_w > bull_w:
        direction = -1
        cats = cats_bear
        max_str = max_bear_str
    else:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close}

    # Delta agreement gate
    if bar_delta != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close}

    # Zone bonus
    zone_bonus = 0.0
    if zone_score >= 50.0:
        zone_bonus = 4.0 if zone_dist <= 0.5 else 8.0
        cats.add("volume_profile")
    elif zone_score >= 30.0:
        zone_bonus = 6.0
        cats.add("volume_profile")

    cat_count = len(cats)
    confluence_mult = 1.25 if cat_count >= 5 else 1.0
    ib_mult = 1.15 if 0 <= bars_since_open < 60 else 1.0

    base_score = sum(W.get(c, 5.0) for c in cats)
    total_score = min(
        (base_score * confluence_mult + zone_bonus) * ib_mult,
        100.0,
    )
    total_score = max(0.0, total_score)

    # Midday block 240-330
    if 240 <= bars_since_open <= 330:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close}

    # Tier classification (mirrors C# scorer)
    has_abs = "absorption" in cats
    has_exh = "exhaustion" in cats
    has_zone = zone_bonus > 0.0
    trap_count = sum(1 for sig in signals if sig.get("signalId", "").startswith("TRAP"))
    delta_chase = abs(bar_delta) > 50 and (
        (direction > 0 and bar_delta > 0) or (direction < 0 and bar_delta < 0)
    )

    if (total_score >= 80.0 and (has_abs or has_exh) and has_zone
            and cat_count >= 5 and trap_count < 3 and not delta_chase):
        tier = "TYPE_A"
    elif total_score >= 72.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_B"
    elif total_score >= 50.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_C"
    else:
        tier = "QUIET"

    # Entry price from dominant ABS/EXH signal
    entry_price = bar_close
    for sig in signals:
        sid = sig.get("signalId", "")
        if sig.get("direction", 0) == direction and float(sig.get("price", 0.0)) != 0.0:
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = float(sig["price"])
                break

    return {
        "direction": direction,
        "total_score": total_score,
        "tier": tier,
        "entry_price": entry_price,
        "cat_count": cat_count,
    }


def _simulate_trades(scored_bars_with_scores: list[tuple[dict, dict]], config: _SimConfig) -> list[dict]:
    """Simulate trades from a list of (bar_record, scored) pairs.

    Exit priority (mirrors BacktestRunner.cs):
      1. STOP_LOSS
      2. TARGET
      3. OPPOSING_SIGNAL
      4. MAX_BARS
      5. SESSION_END (forced at end of list)
    """
    trades: list[dict] = []
    in_trade = False
    entry_bar_idx = 0
    entry_price = 0.0
    trade_dir = 0

    for bar, scored in scored_bars_with_scores:
        bar_idx = int(bar.get("barIdx", 0))
        bar_close = float(bar.get("barClose", 0.0))
        direction = scored["direction"]
        total_score = scored["total_score"]
        tier_ord = _TIER_ORDINALS.get(scored["tier"], 0)

        if in_trade:
            exit_reason = None

            # 1. Stop loss
            if trade_dir == 1 and bar_close <= entry_price - config.stop_loss_ticks * config.tick_size:
                exit_reason = "STOP_LOSS"
            elif trade_dir == -1 and bar_close >= entry_price + config.stop_loss_ticks * config.tick_size:
                exit_reason = "STOP_LOSS"

            # 2. Target
            if exit_reason is None:
                if trade_dir == 1 and bar_close >= entry_price + config.target_ticks * config.tick_size:
                    exit_reason = "TARGET"
                elif trade_dir == -1 and bar_close <= entry_price - config.target_ticks * config.tick_size:
                    exit_reason = "TARGET"

            # 3. Opposing signal
            if exit_reason is None and direction != 0 and direction != trade_dir:
                if total_score >= config.exit_on_opposing_score:
                    exit_reason = "OPPOSING_SIGNAL"

            # 4. Max bars
            if exit_reason is None and (bar_idx - entry_bar_idx) >= config.max_bars_in_trade:
                exit_reason = "MAX_BARS"

            if exit_reason is not None:
                exit_price = bar_close + (trade_dir * config.slippage_ticks * config.tick_size * -1.0)
                pnl_ticks = (exit_price - entry_price) / config.tick_size * trade_dir
                trades.append({
                    "entry_bar": entry_bar_idx,
                    "exit_bar": bar_idx,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "direction": trade_dir,
                    "pnl_ticks": pnl_ticks,
                    "pnl_dollars": pnl_ticks * config.tick_value * config.contracts_per_trade,
                    "exit_reason": exit_reason,
                })
                in_trade = False

        else:
            # Entry gate
            if (total_score >= config.score_entry_threshold
                    and tier_ord >= config.min_tier_ordinal
                    and direction != 0):
                ep = scored["entry_price"]
                entry_price = ep + direction * config.slippage_ticks * config.tick_size
                entry_bar_idx = bar_idx
                trade_dir = direction
                in_trade = True

    # Session-end forced exit
    if in_trade and scored_bars_with_scores:
        last_bar, _ = scored_bars_with_scores[-1]
        bar_close = float(last_bar.get("barClose", 0.0))
        bar_idx = int(last_bar.get("barIdx", 0))
        exit_price = bar_close + (trade_dir * config.slippage_ticks * config.tick_size * -1.0)
        pnl_ticks = (exit_price - entry_price) / config.tick_size * trade_dir
        trades.append({
            "entry_bar": entry_bar_idx,
            "exit_bar": bar_idx,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "direction": trade_dir,
            "pnl_ticks": pnl_ticks,
            "pnl_dollars": pnl_ticks * config.tick_value * config.contracts_per_trade,
            "exit_reason": "SESSION_END",
        })

    return trades


def _run_sessions(session_paths: list[Path], config: _SimConfig) -> list[dict]:
    """Load and simulate all sessions with the given config."""
    all_trades: list[dict] = []
    for path in session_paths:
        bars = _load_scored_bars_from_ndjson(path)
        scored_pairs = [(b, _score_bar_simple(b)) for b in bars]
        all_trades.extend(_simulate_trades(scored_pairs, config))
    return all_trades


def _trades_to_vbt_portfolio(trades: list[dict], init_cash: float = 50_000.0) -> Any:
    """Convert trade list to a vectorbt Portfolio using from_orders().

    Builds a synthetic price series and places explicit entry/exit orders.
    """
    if not _VBT_AVAILABLE:
        raise RuntimeError("vectorbt is not installed. Run: pip install vectorbt")

    if not trades:
        raise ValueError("No trades to build portfolio from.")

    max_bar = max(max(t["entry_bar"], t["exit_bar"]) for t in trades)
    n = max_bar + 1

    # Build price series: fill with entry/exit prices, linear interpolation elsewhere
    prices = np.full(n, np.nan)
    for t in trades:
        prices[t["entry_bar"]] = t["entry_price"]
        prices[t["exit_bar"]] = t["exit_price"]

    # Forward-fill then backward-fill NaN gaps
    price_series = pd.Series(prices).ffill().bfill()
    if price_series.isna().any():
        price_series = price_series.fillna(prices[~np.isnan(prices)][0] if not np.all(np.isnan(prices)) else 1.0)

    # Build order size and price arrays
    size = np.zeros(n)
    order_price = np.full(n, np.nan)

    for t in trades:
        d = t["direction"]
        # Entry: buy for long (+1 contract), sell for short (-1 contract)
        size[t["entry_bar"]] += d * 1.0
        order_price[t["entry_bar"]] = t["entry_price"]
        # Exit: reverse of entry
        size[t["exit_bar"]] += d * -1.0
        order_price[t["exit_bar"]] = t["exit_price"]

    # Fill order_price gaps with close price
    op_series = pd.Series(order_price).fillna(price_series)

    pf = vbt.Portfolio.from_orders(
        close=price_series,
        size=pd.Series(size),
        price=op_series,
        fees=0.0,
        init_cash=init_cash,
        freq="1min",
    )
    return pf


def _sharpe_for_trades(trades: list[dict]) -> float:
    """Compute Sharpe estimate from trades (mean/std * sqrt(252))."""
    if len(trades) < 2:
        return 0.0
    pnls = np.array([t["pnl_ticks"] for t in trades])
    std = pnls.std(ddof=1)
    if std == 0.0:
        return 0.0
    return float((pnls.mean() / std) * np.sqrt(252))


# ===========================================================================
# Mode 1: import
# ===========================================================================

def mode_import(trades_csv: Path, output_dir: Path, init_cash: float = 50_000.0) -> None:
    """Read CsvTradeExporter output, build vectorbt Portfolio, emit stats + HTML."""
    df = pd.read_csv(trades_csv)
    print(f"Loaded {len(df)} trades from {trades_csv}")

    if df.empty:
        print("No trades in CSV — nothing to analyse.")
        return

    trades = df.to_dict("records")
    # Normalise column names to lowercase for _trades_to_vbt_portfolio
    normalised = []
    for row in trades:
        normalised.append({
            "entry_bar":   int(row.get("EntryBar", row.get("entry_bar", 0))),
            "exit_bar":    int(row.get("ExitBar",  row.get("exit_bar",  1))),
            "entry_price": float(row.get("EntryPrice", row.get("entry_price", 0))),
            "exit_price":  float(row.get("ExitPrice",  row.get("exit_price",  0))),
            "direction":   int(row.get("Direction",   row.get("direction",    1))),
            "pnl_ticks":   float(row.get("PnlTicks",   row.get("pnl_ticks",   0))),
            "pnl_dollars": float(row.get("PnlDollars", row.get("pnl_dollars", 0))),
            "exit_reason": str(row.get("ExitReason",  row.get("exit_reason",  ""))),
        })

    pf = _trades_to_vbt_portfolio(normalised, init_cash=init_cash)
    stats = pf.stats()
    print("\n--- Portfolio Stats ---")
    print(stats.to_string())

    # Save stats as JSON
    stats_path = output_dir / "stats.json"
    stats_dict = stats.to_dict()
    # Serialise non-serialisable types (Timedelta, NaN)
    for k, v in list(stats_dict.items()):
        if hasattr(v, "total_seconds"):
            stats_dict[k] = v.total_seconds()
        elif v != v:  # NaN check
            stats_dict[k] = None
        else:
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                stats_dict[k] = str(v)

    with open(stats_path, "w", encoding="utf-8") as fh:
        json.dump(stats_dict, fh, indent=2)
    print(f"Stats saved to {stats_path}")

    # Save HTML report
    report_path = output_dir / "report.html"
    fig = pf.plot()
    fig.write_html(str(report_path))
    print(f"HTML report saved to {report_path}")


# ===========================================================================
# Mode 2: sweep
# ===========================================================================

_SWEEP_GRID = {
    "score_threshold": [70.0, 75.0, 80.0, 85.0],
    "min_tier":        ["TYPE_A", "TYPE_B"],
    "stop_loss_ticks": [15, 20, 25, 30],
}


def _run_sweep(session_paths: list[Path]) -> pd.DataFrame:
    """Run full parameter grid; return DataFrame with one row per combo."""
    rows = []
    for threshold in _SWEEP_GRID["score_threshold"]:
        for tier in _SWEEP_GRID["min_tier"]:
            for sl in _SWEEP_GRID["stop_loss_ticks"]:
                cfg = _SimConfig(
                    score_entry_threshold=threshold,
                    min_tier=tier,
                    stop_loss_ticks=sl,
                )
                trades = _run_sessions(session_paths, cfg)
                sharpe = _sharpe_for_trades(trades)
                net_pnl = sum(t["pnl_dollars"] for t in trades)
                rows.append({
                    "score_threshold":  threshold,
                    "min_tier":         tier,
                    "stop_loss_ticks":  sl,
                    "sharpe":           sharpe,
                    "trade_count":      len(trades),
                    "net_pnl_dollars":  net_pnl,
                })
    return pd.DataFrame(rows)


def mode_sweep(sessions_dir: Path, output_dir: Path) -> None:
    """Sweep parameter grid over all sessions, produce Sharpe heatmap."""
    session_paths = sorted(sessions_dir.glob("*.ndjson"))
    if not session_paths:
        print(f"No .ndjson files found in {sessions_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Sweep: {len(session_paths)} sessions, {len(_SWEEP_GRID['score_threshold']) * len(_SWEEP_GRID['min_tier']) * len(_SWEEP_GRID['stop_loss_ticks'])} combos")

    results_df = _run_sweep(session_paths)

    # Save full results CSV
    results_csv = output_dir / "sweep_results.csv"
    results_df.to_csv(results_csv, index=False)
    print(f"Sweep results saved to {results_csv}")

    # Heatmap: score_threshold vs stop_loss_ticks for each min_tier
    try:
        import plotly.express as px  # type: ignore
        for tier in _SWEEP_GRID["min_tier"]:
            sub = results_df[results_df["min_tier"] == tier].copy()
            pivot = sub.pivot(index="stop_loss_ticks", columns="score_threshold", values="sharpe")
            fig = px.imshow(
                pivot,
                title=f"Sharpe Heatmap — min_tier={tier}",
                labels={"x": "score_threshold", "y": "stop_loss_ticks", "color": "sharpe"},
                color_continuous_scale="RdYlGn",
            )
            heatmap_path = output_dir / f"sweep_heatmap_{tier.lower()}.html"
            fig.write_html(str(heatmap_path))
            print(f"Heatmap saved to {heatmap_path}")
    except ImportError:
        print("plotly not available — skipping heatmap HTML output.")

    # Print best combo
    best_idx = results_df["sharpe"].idxmax()
    best = results_df.loc[best_idx]
    print(f"\nBest combo: score_threshold={best['score_threshold']}, "
          f"min_tier={best['min_tier']}, stop_loss={best['stop_loss_ticks']}, "
          f"sharpe={best['sharpe']:.3f}, trades={best['trade_count']}")


# ===========================================================================
# Mode 3: walkforward
# ===========================================================================

def mode_walkforward(sessions_dir: Path, output_dir: Path) -> None:
    """60/20/20 walk-forward: optimise on train, validate, report test result."""
    session_paths = sorted(sessions_dir.glob("*.ndjson"))
    if not session_paths:
        print(f"No .ndjson files found in {sessions_dir}", file=sys.stderr)
        sys.exit(1)

    n = len(session_paths)
    train_end = max(1, int(n * 0.60))
    val_end   = max(train_end + 1, int(n * 0.80))

    train_paths    = session_paths[:train_end]
    validate_paths = session_paths[train_end:val_end]
    test_paths     = session_paths[val_end:]

    print(f"Walk-forward: {n} sessions — train={len(train_paths)}, "
          f"validate={len(validate_paths)}, test={len(test_paths)}")

    # Step 1: find best params on training set
    train_results = _run_sweep(train_paths)
    best_idx      = train_results["sharpe"].idxmax()
    best_row      = train_results.loc[best_idx]
    best_params   = {
        "score_threshold": float(best_row["score_threshold"]),
        "min_tier":        str(best_row["min_tier"]),
        "stop_loss_ticks": int(best_row["stop_loss_ticks"]),
    }
    train_sharpe = float(best_row["sharpe"])
    print(f"Best train params: {best_params}, sharpe={train_sharpe:.3f}")

    # Step 2: validate
    val_cfg     = _SimConfig(
        score_entry_threshold=best_params["score_threshold"],
        min_tier=best_params["min_tier"],
        stop_loss_ticks=best_params["stop_loss_ticks"],
    )
    val_trades  = _run_sessions(validate_paths if validate_paths else train_paths, val_cfg)
    val_sharpe  = _sharpe_for_trades(val_trades)
    print(f"Validate sharpe: {val_sharpe:.3f}")

    # Step 3: test (out-of-sample)
    test_trades = _run_sessions(test_paths if test_paths else train_paths, val_cfg)
    test_sharpe = _sharpe_for_trades(test_trades)
    print(f"Test sharpe: {test_sharpe:.3f}")

    passed = val_sharpe > 0 and test_sharpe > 0

    report = {
        "train_params":      best_params,
        "train_sharpe":      train_sharpe,
        "validate_sharpe":   val_sharpe,
        "test_sharpe":       test_sharpe,
        "passed":            passed,
        "train_sessions":    [str(p) for p in train_paths],
        "validate_sessions": [str(p) for p in validate_paths],
        "test_sessions":     [str(p) for p in test_paths],
    }

    report_path = output_dir / "walkforward_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"Walk-forward report saved to {report_path}")
    print(f"Passed: {passed}")


# ===========================================================================
# CLI entry point
# ===========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="vbt_harness",
        description="DEEP6 vectorbt integration harness",
    )
    parser.add_argument(
        "--mode",
        choices=["import", "sweep", "walkforward"],
        required=True,
        help="Execution mode",
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        help="Directory containing .ndjson session files (sweep/walkforward modes)",
    )
    parser.add_argument(
        "--trades-csv",
        type=Path,
        help="Path to CsvTradeExporter CSV output (import mode)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for reports and artefacts",
    )
    parser.add_argument(
        "--init-cash",
        type=float,
        default=50_000.0,
        help="Initial capital for portfolio (import mode, default 50000)",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "import":
        if not args.trades_csv:
            parser.error("--trades-csv is required for import mode")
        mode_import(args.trades_csv, args.output_dir, init_cash=args.init_cash)

    elif args.mode == "sweep":
        if not args.sessions_dir:
            parser.error("--sessions-dir is required for sweep mode")
        mode_sweep(args.sessions_dir, args.output_dir)

    elif args.mode == "walkforward":
        if not args.sessions_dir:
            parser.error("--sessions-dir is required for walkforward mode")
        mode_walkforward(args.sessions_dir, args.output_dir)


if __name__ == "__main__":
    main()
