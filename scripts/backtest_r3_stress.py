#!/usr/bin/env python3
"""
Round 3: Robustness & Stress Testing for VWAP strategies on NQ futures.
Tests top configs from initial optimization under adverse conditions.
"""

import duckdb
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional
import sys
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0  # $5 per tick for NQ
POINT_VALUE = TICK_VALUE / TICK_SIZE  # $20 per point
DB_PATH = Path(__file__).parent.parent / "data" / "backtests" / "replay_full_5sessions.duckdb"
RESULTS_PATH = Path(__file__).parent / "results_r3_stress.txt"

RTH_START_HOUR = 9   # 09:00 CT
RTH_END_HOUR = 16    # 16:00 CT
RTH_DATES = ["2026-04-08", "2026-04-09", "2026-04-10"]


# ── Data Loading ───────────────────────────────────────────────────────────
def load_1m_bars() -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("""
        SELECT bar_ts, open, high, low, close, volume
        FROM backtest_bars
        WHERE tf = '1m'
        ORDER BY bar_ts
    """).fetchdf()
    con.close()
    df["bar_ts"] = pd.to_datetime(df["bar_ts"])
    df.set_index("bar_ts", inplace=True)
    return df


def get_rth_sessions(df_1m: pd.DataFrame) -> dict:
    """Return dict of date_str -> 30m OHLCV DataFrame for RTH hours."""
    sessions = {}
    for date_str in RTH_DATES:
        start = pd.Timestamp(f"{date_str} 09:00:00")
        end = pd.Timestamp(f"{date_str} 16:00:00")
        mask = (df_1m.index >= start) & (df_1m.index < end)
        session_1m = df_1m.loc[mask].copy()
        if session_1m.empty:
            continue
        # Resample to 30m
        ohlcv = session_1m.resample("30min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        sessions[date_str] = ohlcv
    return sessions


# ── VWAP Calculation ───────────────────────────────────────────────────────
def compute_vwap_series(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP from start of session."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    return cum_tp_vol / cum_vol


# ── Trade Simulation ──────────────────────────────────────────────────────
@dataclass
class TradeResult:
    date: str
    direction: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    pnl_points: float
    exit_reason: str


def simulate_exit(bars_after_entry: pd.DataFrame, direction: int,
                  entry_price: float, sl_ticks: float, tp_ticks: float,
                  flatten_time_hour: float = 16.0) -> Tuple[float, str]:
    """Walk forward bar-by-bar checking SL/TP on high/low. Flatten at 16:00."""
    sl_points = sl_ticks * TICK_SIZE
    tp_points = tp_ticks * TICK_SIZE

    if direction == 1:  # long
        sl_price = entry_price - sl_points
        tp_price = entry_price + tp_points
    else:  # short
        sl_price = entry_price + sl_points
        tp_price = entry_price - tp_points

    for ts, bar in bars_after_entry.iterrows():
        hour_frac = ts.hour + ts.minute / 60.0
        if hour_frac >= flatten_time_hour:
            return bar["close"], "FLATTEN"

        if direction == 1:
            if bar["low"] <= sl_price:
                return sl_price, "SL"
            if bar["high"] >= tp_price:
                return tp_price, "TP"
        else:
            if bar["high"] >= sl_price:
                return sl_price, "SL"
            if bar["low"] <= tp_price:
                return tp_price, "TP"

    # End of data
    last_bar = bars_after_entry.iloc[-1]
    return last_bar["close"], "EOD"


# ── Strategy Implementations ──────────────────────────────────────────────

def run_chnavy6(session_bars: pd.DataFrame, date_str: str,
                sl: float, tp: float, bounce_ticks: float,
                start_hour: float, end_hour: float,
                slippage_ticks: float = 0, commission_per_side: float = 0.35,
                entry_delay_bars: int = 0, adverse_fill: bool = False,
                tp_scale: float = 1.0) -> Optional[TradeResult]:
    """
    ChNavy6: OnBarClose. Track wasBelowVWAP/wasAboveVWAP via prior bar close vs prior VWAP.
    Long when wasBelowVWAP and close > vwap and (close-vwap) >= confirm.
    Short opposite. 1 trade/day.
    """
    confirm = bounce_ticks * TICK_SIZE
    effective_tp = tp * tp_scale
    vwap = compute_vwap_series(session_bars)

    for i in range(1, len(session_bars)):
        bar_time = session_bars.index[i]
        hour_frac = bar_time.hour + bar_time.minute / 60.0
        if hour_frac < start_hour or hour_frac > end_hour:
            continue

        prev_close = session_bars.iloc[i - 1]["close"]
        prev_vwap = vwap.iloc[i - 1]
        curr_close = session_bars.iloc[i]["close"]
        curr_vwap = vwap.iloc[i]

        was_below = prev_close < prev_vwap
        was_above = prev_close > prev_vwap

        direction = 0
        if was_below and curr_close > curr_vwap and (curr_close - curr_vwap) >= confirm:
            direction = 1
        elif was_above and curr_close < curr_vwap and (curr_vwap - curr_close) >= confirm:
            direction = -1

        if direction == 0:
            continue

        # Entry bar index (with delay)
        entry_idx = i + 1 + entry_delay_bars
        if entry_idx >= len(session_bars):
            continue

        entry_bar = session_bars.iloc[entry_idx]
        if adverse_fill:
            entry_price = entry_bar["high"] if direction == 1 else entry_bar["low"]
        else:
            entry_price = entry_bar["open"]

        # Apply slippage
        entry_price += direction * slippage_ticks * TICK_SIZE

        remaining = session_bars.iloc[entry_idx + 1:]
        if remaining.empty:
            continue

        exit_price, reason = simulate_exit(remaining, direction, entry_price, sl, effective_tp)

        # Apply slippage on exit
        exit_price -= direction * slippage_ticks * TICK_SIZE

        pnl_points = direction * (exit_price - entry_price)
        pnl_dollars = pnl_points * POINT_VALUE - 2 * commission_per_side

        return TradeResult(date_str, direction, entry_price, exit_price, pnl_dollars, reason)

    return None


def run_ch2navy6(session_bars: pd.DataFrame, date_str: str,
                 sl: float, tp: float, bounce_ticks: float,
                 start_hour: float, end_hour: float,
                 slippage_ticks: float = 0, commission_per_side: float = 0.35,
                 entry_delay_bars: int = 0, adverse_fill: bool = False,
                 tp_scale: float = 1.0) -> Optional[TradeResult]:
    """
    Ch2Navy6: Uses bar[2] and bar[1]. VWAP computed from bar[1].
    Long setup: bar2.close < vwapPrior AND bar1.low <= vwapPrior AND bar1.close > vwapPrior
                AND (bar1.close - vwapPrior) >= confirm.
    Short opposite. Enter at next bar open. 1 trade/day.
    """
    confirm = bounce_ticks * TICK_SIZE
    effective_tp = tp * tp_scale
    vwap = compute_vwap_series(session_bars)

    for i in range(2, len(session_bars)):
        bar_time = session_bars.index[i]
        hour_frac = bar_time.hour + bar_time.minute / 60.0
        if hour_frac < start_hour or hour_frac > end_hour:
            continue

        bar2 = session_bars.iloc[i - 2]
        bar1 = session_bars.iloc[i - 1]
        vwap_prior = vwap.iloc[i - 1]

        direction = 0
        # Long setup
        if (bar2["close"] < vwap_prior and
            bar1["low"] <= vwap_prior and
            bar1["close"] > vwap_prior and
            (bar1["close"] - vwap_prior) >= confirm):
            direction = 1
        # Short setup
        elif (bar2["close"] > vwap_prior and
              bar1["high"] >= vwap_prior and
              bar1["close"] < vwap_prior and
              (vwap_prior - bar1["close"]) >= confirm):
            direction = -1

        if direction == 0:
            continue

        # Enter at bar[i] open (next bar after signal), with optional delay
        entry_idx = i + entry_delay_bars
        if entry_idx >= len(session_bars):
            continue

        entry_bar = session_bars.iloc[entry_idx]
        if adverse_fill:
            entry_price = entry_bar["high"] if direction == 1 else entry_bar["low"]
        else:
            entry_price = entry_bar["open"]

        entry_price += direction * slippage_ticks * TICK_SIZE

        remaining = session_bars.iloc[entry_idx + 1:]
        if remaining.empty:
            continue

        exit_price, reason = simulate_exit(remaining, direction, entry_price, sl, effective_tp)
        exit_price -= direction * slippage_ticks * TICK_SIZE

        pnl_points = direction * (exit_price - entry_price)
        pnl_dollars = pnl_points * POINT_VALUE - 2 * commission_per_side

        return TradeResult(date_str, direction, entry_price, exit_price, pnl_dollars, reason)

    return None


def run_chtrendnavy6(session_bars: pd.DataFrame, date_str: str,
                     sl: float, tp: float, slope_lb: int, pb_ticks: float,
                     start_hour: float, end_hour: float,
                     slippage_ticks: float = 0, commission_per_side: float = 0.35,
                     entry_delay_bars: int = 0, adverse_fill: bool = False,
                     tp_scale: float = 1.0) -> Optional[TradeResult]:
    """
    CHTrendNavy6: VWAP slope = vwap[now] - vwap[N bars ago].
    Long: slope>0, bar1.close > vwap, bar1.low <= vwap+band.
    Short: slope<0, bar1.close < vwap, bar1.high >= vwap-band.
    Enter at next bar open. 1 trade/day.
    """
    band = pb_ticks * TICK_SIZE
    effective_tp = tp * tp_scale
    vwap = compute_vwap_series(session_bars)

    for i in range(slope_lb + 1, len(session_bars)):
        bar_time = session_bars.index[i]
        hour_frac = bar_time.hour + bar_time.minute / 60.0
        if hour_frac < start_hour or hour_frac > end_hour:
            continue

        curr_vwap = vwap.iloc[i - 1]
        prev_vwap = vwap.iloc[i - 1 - slope_lb]
        slope = curr_vwap - prev_vwap

        bar1 = session_bars.iloc[i - 1]

        direction = 0
        if slope > 0 and bar1["close"] > curr_vwap and bar1["low"] <= curr_vwap + band:
            direction = 1
        elif slope < 0 and bar1["close"] < curr_vwap and bar1["high"] >= curr_vwap - band:
            direction = -1

        if direction == 0:
            continue

        entry_idx = i + entry_delay_bars
        if entry_idx >= len(session_bars):
            continue

        entry_bar = session_bars.iloc[entry_idx]
        if adverse_fill:
            entry_price = entry_bar["high"] if direction == 1 else entry_bar["low"]
        else:
            entry_price = entry_bar["open"]

        entry_price += direction * slippage_ticks * TICK_SIZE

        remaining = session_bars.iloc[entry_idx + 1:]
        if remaining.empty:
            continue

        exit_price, reason = simulate_exit(remaining, direction, entry_price, sl, effective_tp)
        exit_price -= direction * slippage_ticks * TICK_SIZE

        pnl_points = direction * (exit_price - entry_price)
        pnl_dollars = pnl_points * POINT_VALUE - 2 * commission_per_side

        return TradeResult(date_str, direction, entry_price, exit_price, pnl_dollars, reason)

    return None


# ── Config Definitions ─────────────────────────────────────────────────────

@dataclass
class StrategyConfig:
    name: str
    strategy: str  # "chnavy6", "ch2navy6", "chtrendnavy6"
    sl: float
    tp: float
    bounce: float  # or pb for trend
    start: float
    end: float
    slope_lb: int  # only for trend


CONFIGS = [
    StrategyConfig("ChNavy6", "chnavy6", sl=200, tp=480, bounce=20, start=9.5, end=14.5, slope_lb=0),
    StrategyConfig("Ch2Navy6", "ch2navy6", sl=200, tp=480, bounce=20, start=9.5, end=14.5, slope_lb=0),
    StrategyConfig("CHTrendNavy6", "chtrendnavy6", sl=240, tp=200, bounce=20, start=10.0, end=14.5, slope_lb=2),
    StrategyConfig("CHTrendNavy6-alt", "chtrendnavy6", sl=120, tp=480, bounce=20, start=10.0, end=14.5, slope_lb=2),
]


def run_config(cfg: StrategyConfig, sessions: dict,
               slippage_ticks=0, commission_per_side=0.35,
               entry_delay_bars=0, adverse_fill=False,
               tp_scale=1.0) -> List[TradeResult]:
    """Run a config across all sessions with given stress parameters."""
    trades = []
    for date_str, bars in sessions.items():
        if cfg.strategy == "chnavy6":
            t = run_chnavy6(bars, date_str, cfg.sl, cfg.tp, cfg.bounce,
                            cfg.start, cfg.end, slippage_ticks, commission_per_side,
                            entry_delay_bars, adverse_fill, tp_scale)
        elif cfg.strategy == "ch2navy6":
            t = run_ch2navy6(bars, date_str, cfg.sl, cfg.tp, cfg.bounce,
                             cfg.start, cfg.end, slippage_ticks, commission_per_side,
                             entry_delay_bars, adverse_fill, tp_scale)
        elif cfg.strategy == "chtrendnavy6":
            t = run_chtrendnavy6(bars, date_str, cfg.sl, cfg.tp, cfg.slope_lb, cfg.bounce,
                                 cfg.start, cfg.end, slippage_ticks, commission_per_side,
                                 entry_delay_bars, adverse_fill, tp_scale)
        else:
            raise ValueError(f"Unknown strategy: {cfg.strategy}")
        if t is not None:
            trades.append(t)
    return trades


# ── Metrics ────────────────────────────────────────────────────────────────

def compute_metrics(trades: List[TradeResult]) -> dict:
    if not trades:
        return {"net_pnl": 0, "win_rate": 0, "profit_factor": 0, "n_trades": 0}
    pnls = [t.pnl_points for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    return {
        "net_pnl": sum(pnls),
        "win_rate": len(wins) / len(trades) * 100,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "n_trades": len(trades),
    }


# ── Stress Test Scenarios ──────────────────────────────────────────────────

def define_stress_scenarios():
    scenarios = []

    # Baseline
    scenarios.append(("Baseline", dict(slippage_ticks=0, commission_per_side=0.35,
                                        entry_delay_bars=0, adverse_fill=False, tp_scale=1.0)))

    # 1. Slippage sensitivity
    for slip in [0, 1, 2, 3, 4, 5]:
        scenarios.append((f"Slip={slip}t", dict(slippage_ticks=slip, commission_per_side=0.35,
                                                 entry_delay_bars=0, adverse_fill=False, tp_scale=1.0)))

    # 2. Commission sensitivity
    for comm in [0.35, 1.00, 2.00, 3.50]:
        scenarios.append((f"Comm=${comm:.2f}", dict(slippage_ticks=0, commission_per_side=comm,
                                                     entry_delay_bars=0, adverse_fill=False, tp_scale=1.0)))

    # 3. Entry delay
    for delay in [1, 2, 3]:
        scenarios.append((f"Delay={delay}bar", dict(slippage_ticks=0, commission_per_side=0.35,
                                                     entry_delay_bars=delay, adverse_fill=False, tp_scale=1.0)))

    # 4. Adverse fill
    scenarios.append(("AdverseFill", dict(slippage_ticks=0, commission_per_side=0.35,
                                           entry_delay_bars=0, adverse_fill=True, tp_scale=1.0)))

    # 5. Reduced TP (partial fill simulation)
    for pct in [0.75, 0.50, 0.25]:
        scenarios.append((f"TP@{int(pct*100)}%", dict(slippage_ticks=0, commission_per_side=0.35,
                                                       entry_delay_bars=0, adverse_fill=False, tp_scale=pct)))

    # 6. Combined worst case
    scenarios.append(("WORST_CASE", dict(slippage_ticks=3, commission_per_side=2.00,
                                          entry_delay_bars=0, adverse_fill=True, tp_scale=1.0)))

    return scenarios


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Loading 1m bars from DuckDB...")
    df_1m = load_1m_bars()
    print(f"  Loaded {len(df_1m)} bars, range {df_1m.index.min()} to {df_1m.index.max()}")

    print("Building RTH 30m sessions...")
    sessions = get_rth_sessions(df_1m)
    for d, s in sessions.items():
        print(f"  {d}: {len(s)} bars ({s.index.min()} - {s.index.max()})")

    scenarios = define_stress_scenarios()
    print(f"\nRunning {len(scenarios)} scenarios x {len(CONFIGS)} configs = {len(scenarios)*len(CONFIGS)} tests\n")

    # results[config_name][scenario_name] = metrics dict
    results = {}
    for cfg in CONFIGS:
        results[cfg.name] = {}
        for scenario_name, params in scenarios:
            trades = run_config(cfg, sessions, **params)
            metrics = compute_metrics(trades)
            results[cfg.name][scenario_name] = metrics

    # ── Format Output ──────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 120)
    lines.append("DEEP6 v2.0 — Round 3: Robustness & Stress Testing Results")
    lines.append(f"Data: NQ futures, 30-min bars, RTH sessions: {', '.join(RTH_DATES)}")
    lines.append("=" * 120)

    # Per-config tables
    for cfg in CONFIGS:
        lines.append("")
        lines.append(f"{'─' * 120}")
        lines.append(f"CONFIG: {cfg.name}  |  Strategy: {cfg.strategy}  |  SL={cfg.sl}  TP={cfg.tp}  "
                      f"Bounce/PB={cfg.bounce}  Start={cfg.start}  End={cfg.end}"
                      + (f"  SlopeLB={cfg.slope_lb}" if cfg.slope_lb else ""))
        lines.append(f"{'─' * 120}")
        hdr = f"{'Scenario':<20} {'Trades':>6} {'Net PnL ($)':>12} {'Win Rate':>10} {'Profit Factor':>14} {'Status':>10}"
        lines.append(hdr)
        lines.append("-" * 75)

        for scenario_name, _ in scenarios:
            m = results[cfg.name][scenario_name]
            status = "OK" if m["net_pnl"] > 0 else "LOSS"
            pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "INF"
            lines.append(f"{scenario_name:<20} {m['n_trades']:>6} {m['net_pnl']:>12.2f} "
                          f"{m['win_rate']:>9.1f}% {pf_str:>14} {status:>10}")

    # Combined worst-case summary
    lines.append("")
    lines.append("=" * 120)
    lines.append("COMBINED WORST-CASE SURVIVAL CHECK  (slippage=3t, commission=$2.00/side, adverse fill)")
    lines.append("=" * 120)
    lines.append(f"{'Config':<20} {'Net PnL ($)':>12} {'Win Rate':>10} {'Profit Factor':>14} {'Survives?':>12}")
    lines.append("-" * 70)

    survival = []
    for cfg in CONFIGS:
        m = results[cfg.name]["WORST_CASE"]
        survives = m["net_pnl"] > 0
        pf_str = f"{m['profit_factor']:.2f}" if m['profit_factor'] != float('inf') else "INF"
        marker = ">>> YES <<<" if survives else "    NO"
        lines.append(f"{cfg.name:<20} {m['net_pnl']:>12.2f} {m['win_rate']:>9.1f}% {pf_str:>14} {marker:>12}")
        survival.append((cfg.name, m["net_pnl"], m["profit_factor"], survives))

    # Stress-adjusted ranking
    lines.append("")
    lines.append("=" * 120)
    lines.append("STRESS-ADJUSTED RANKING")
    lines.append("=" * 120)
    lines.append("")
    lines.append("Methodology: Score = sum of net PnL across ALL stress scenarios (lower = more fragile).")
    lines.append("Configs that survive worst-case get a bonus marker.")
    lines.append("")

    ranking = []
    for cfg in CONFIGS:
        total_pnl = sum(results[cfg.name][s][("net_pnl")] for s, _ in scenarios)
        worst_pnl = results[cfg.name]["WORST_CASE"]["net_pnl"]
        baseline_pnl = results[cfg.name]["Baseline"]["net_pnl"]
        # Degradation: how much does worst case reduce from baseline
        degradation = ((baseline_pnl - worst_pnl) / abs(baseline_pnl) * 100) if baseline_pnl != 0 else 0
        ranking.append((cfg.name, total_pnl, worst_pnl, baseline_pnl, degradation,
                         worst_pnl > 0))

    ranking.sort(key=lambda x: x[1], reverse=True)

    lines.append(f"{'Rank':<6} {'Config':<20} {'Agg PnL ($)':>12} {'Baseline ($)':>13} {'WorstCase ($)':>14} "
                  f"{'Degradation':>12} {'Survives':>10}")
    lines.append("-" * 90)
    for rank, (name, agg, worst, base, deg, surv) in enumerate(ranking, 1):
        surv_str = "YES" if surv else "NO"
        lines.append(f"  {rank:<4} {name:<20} {agg:>12.2f} {base:>13.2f} {worst:>14.2f} "
                      f"{deg:>11.1f}% {surv_str:>10}")

    lines.append("")
    lines.append("=" * 120)
    lines.append("CONCLUSION")
    lines.append("=" * 120)

    survivors = [r for r in ranking if r[5]]
    if survivors:
        best = survivors[0]
        lines.append(f"  Top stress-adjusted config: {best[0]}")
        lines.append(f"    Aggregate PnL across all scenarios: ${best[1]:.2f}")
        lines.append(f"    Baseline PnL: ${best[3]:.2f}")
        lines.append(f"    Worst-case PnL: ${best[2]:.2f}")
        lines.append(f"    Worst-case degradation: {best[4]:.1f}%")
        lines.append(f"    SURVIVES combined worst case: YES")
    else:
        lines.append("  WARNING: No config survives the combined worst-case scenario.")
        lines.append(f"  Most resilient config: {ranking[0][0]} (least negative aggregate PnL)")
        lines.append(f"    Aggregate PnL: ${ranking[0][1]:.2f}")

    non_survivors = [r for r in ranking if not r[5]]
    if non_survivors:
        lines.append("")
        lines.append("  Configs that do NOT survive worst case:")
        for name, _, worst, base, deg, _ in non_survivors:
            lines.append(f"    - {name}: worst-case PnL ${worst:.2f} ({deg:.1f}% degradation from baseline)")

    lines.append("")
    lines.append("END OF REPORT")
    lines.append("=" * 120)

    report = "\n".join(lines)

    # Write to file
    with open(RESULTS_PATH, "w") as f:
        f.write(report)

    # Also print
    print(report)
    print(f"\nResults written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
