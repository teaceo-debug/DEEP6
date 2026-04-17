#!/usr/bin/env python3
"""
Round 4: Multi-Timeframe VWAP Strategy Comparison
Tests ChNavy6, Ch2Navy6, CHTrendNavy6 across 5m/10m/15m/20m/30m/60m timeframes.
"""

import duckdb
import pandas as pd
import numpy as np
from itertools import product
from collections import defaultdict
import time

# ── Constants ──────────────────────────────────────────────────────────────
DB_PATH = "/Users/teaceo/DEEP6/data/backtests/replay_full_5sessions.duckdb"
RESULTS_PATH = "/Users/teaceo/DEEP6/scripts/results_r4_multitf.txt"

TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
SLIPPAGE = SLIPPAGE_TICKS * TICK_SIZE

RTH_START_HR = 9.0   # 9:00
RTH_END_HR = 16.0    # 16:00
ENTRY_START = 9.5    # 9:30
ENTRY_END = 14.5     # 14:30

# ── Parameter grids per timeframe ──────────────────────────────────────────
TF_PARAMS = {
    5:  {"SL": [30, 50, 80, 120],    "TP": [60, 100, 160, 240]},
    10: {"SL": [50, 80, 120, 160],   "TP": [100, 160, 240, 320]},
    15: {"SL": [80, 120, 160, 200],  "TP": [160, 240, 320, 400]},
    20: {"SL": [100, 140, 180, 240], "TP": [200, 280, 360, 480]},
    30: {"SL": [120, 180, 240, 320], "TP": [240, 360, 480, 600]},
    60: {"SL": [200, 300, 400, 500], "TP": [400, 600, 800, 1000]},
}
BOUNCE_CONFIRMS = [10, 20, 40]
SLOPE_LBS = [2, 3, 4]
PULLBACK_TICKS = [10, 20, 40]

RTH_DATES = ["2026-04-08", "2026-04-09", "2026-04-10"]


def load_1m_data():
    """Load 1m bars from DuckDB."""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(
        "SELECT bar_ts, open, high, low, close, volume "
        "FROM backtest_bars WHERE tf='1m' ORDER BY bar_ts"
    ).fetchdf()
    con.close()
    df["bar_ts"] = pd.to_datetime(df["bar_ts"])
    return df


def resample_to_tf(df_1m, tf_minutes, date_str):
    """Resample 1m bars to tf_minutes bars for a single RTH session."""
    date = pd.Timestamp(date_str)
    rth_start = date + pd.Timedelta(hours=9)
    rth_end = date + pd.Timedelta(hours=16)

    mask = (df_1m["bar_ts"] >= rth_start) & (df_1m["bar_ts"] < rth_end)
    session = df_1m.loc[mask].copy()
    if session.empty:
        return pd.DataFrame()

    session = session.set_index("bar_ts")

    if tf_minutes == 1:
        result = session.copy()
    else:
        result = session.resample(f"{tf_minutes}min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

    result = result.reset_index()
    return result


def compute_vwap_series(bars_df):
    """Compute cumulative VWAP for each bar (from session start)."""
    typical = (bars_df["high"] + bars_df["low"] + bars_df["close"]) / 3.0
    cum_tv = (typical * bars_df["volume"]).cumsum()
    cum_v = bars_df["volume"].cumsum()
    vwap = cum_tv / cum_v
    vwap = vwap.ffill()
    return vwap.values


def bar_hour(ts):
    """Convert timestamp to fractional hour."""
    return ts.hour + ts.minute / 60.0


def simulate_exit(bars, entry_idx, direction, entry_price, sl_ticks, tp_ticks):
    """
    Walk forward from entry_idx+1 checking SL/TP on each bar's high/low.
    Flatten at 16:00. Returns (pnl_ticks, exit_reason).
    """
    sl_dist = sl_ticks * TICK_SIZE
    tp_dist = tp_ticks * TICK_SIZE

    if direction == "LONG":
        sl_price = entry_price - sl_dist
        tp_price = entry_price + tp_dist
    else:
        sl_price = entry_price + sl_dist
        tp_price = entry_price - tp_dist

    for i in range(entry_idx + 1, len(bars)):
        bar = bars.iloc[i]
        bts = bar["bar_ts"]

        # Flatten at 16:00
        if bar_hour(bts) >= 16.0:
            exit_price = bar["open"]
            if direction == "LONG":
                pnl_ticks = (exit_price - entry_price) / TICK_SIZE
            else:
                pnl_ticks = (entry_price - exit_price) / TICK_SIZE
            return pnl_ticks, "FLATTEN"

        if direction == "LONG":
            # Check SL first (conservative)
            if bar["low"] <= sl_price:
                return -sl_ticks, "SL"
            if bar["high"] >= tp_price:
                return tp_ticks, "TP"
        else:
            if bar["high"] >= sl_price:
                return -sl_ticks, "SL"
            if bar["low"] <= tp_price:
                return tp_ticks, "TP"

    # End of data — close at last bar close
    last_close = bars.iloc[-1]["close"]
    if direction == "LONG":
        pnl_ticks = (last_close - entry_price) / TICK_SIZE
    else:
        pnl_ticks = (entry_price - last_close) / TICK_SIZE
    return pnl_ticks, "EOD"


def run_chnavy6(bars, vwap, sl_ticks, tp_ticks, confirm_ticks):
    """ChNavy6: OnBarClose cross with bounce confirm. 1 trade/day."""
    confirm = confirm_ticks * TICK_SIZE
    trades = []

    for i in range(1, len(bars)):
        bts = bars.iloc[i]["bar_ts"]
        hr = bar_hour(bts)
        if hr < ENTRY_START or hr > ENTRY_END:
            continue

        prior_close = bars.iloc[i - 1]["close"]
        prior_vwap = vwap[i - 1]
        curr_close = bars.iloc[i]["close"]
        curr_vwap = vwap[i]

        wasBelowVWAP = prior_close < prior_vwap
        wasAboveVWAP = prior_close > prior_vwap

        direction = None
        if wasBelowVWAP and curr_close > curr_vwap and (curr_close - curr_vwap) >= confirm:
            direction = "LONG"
        elif wasAboveVWAP and curr_close < curr_vwap and (curr_vwap - curr_close) >= confirm:
            direction = "SHORT"

        if direction:
            entry_price = curr_close + (SLIPPAGE if direction == "LONG" else -SLIPPAGE)
            pnl_ticks, reason = simulate_exit(bars, i, direction, entry_price, sl_ticks, tp_ticks)
            pnl_dollar = pnl_ticks * TICK_VALUE - 2 * COMMISSION_PER_SIDE
            trades.append({"direction": direction, "pnl": pnl_dollar, "reason": reason})
            break  # 1 trade/day

    return trades


def run_ch2navy6(bars, vwap, sl_ticks, tp_ticks, confirm_ticks):
    """Ch2Navy6: 2-bar lookback cross. Enter at next bar open. 1 trade/day."""
    confirm = confirm_ticks * TICK_SIZE
    trades = []

    for i in range(2, len(bars) - 1):
        bts = bars.iloc[i]["bar_ts"]
        hr = bar_hour(bts)
        if hr < ENTRY_START or hr > ENTRY_END:
            continue

        bar2 = bars.iloc[i - 2]
        bar1 = bars.iloc[i - 1]
        vwap_prior = vwap[i - 1]

        direction = None
        # Long setup
        if (bar2["close"] < vwap_prior and
                bar1["low"] <= vwap_prior and
                bar1["close"] > vwap_prior and
                (bar1["close"] - vwap_prior) >= confirm):
            direction = "LONG"
        # Short setup
        elif (bar2["close"] > vwap_prior and
              bar1["high"] >= vwap_prior and
              bar1["close"] < vwap_prior and
              (vwap_prior - bar1["close"]) >= confirm):
            direction = "SHORT"

        if direction:
            entry_bar = bars.iloc[i]
            entry_hr = bar_hour(entry_bar["bar_ts"])
            if entry_hr >= 16.0:
                continue
            entry_price = entry_bar["open"] + (SLIPPAGE if direction == "LONG" else -SLIPPAGE)
            pnl_ticks, reason = simulate_exit(bars, i, direction, entry_price, sl_ticks, tp_ticks)
            pnl_dollar = pnl_ticks * TICK_VALUE - 2 * COMMISSION_PER_SIDE
            trades.append({"direction": direction, "pnl": pnl_dollar, "reason": reason})
            break  # 1 trade/day

    return trades


def run_chtrendnavy6(bars, vwap, sl_ticks, tp_ticks, slope_lb, pullback_ticks):
    """CHTrendNavy6: VWAP slope + pullback. Enter at next bar open. 1 trade/day."""
    band = pullback_ticks * TICK_SIZE
    trades = []

    for i in range(slope_lb + 1, len(bars) - 1):
        bts = bars.iloc[i]["bar_ts"]
        hr = bar_hour(bts)
        if hr < ENTRY_START or hr > ENTRY_END:
            continue

        slope = vwap[i] - vwap[i - slope_lb]
        bar1 = bars.iloc[i]
        curr_vwap = vwap[i]

        direction = None
        if slope > 0 and bar1["close"] > curr_vwap and bar1["low"] <= curr_vwap + band:
            direction = "LONG"
        elif slope < 0 and bar1["close"] < curr_vwap and bar1["high"] >= curr_vwap - band:
            direction = "SHORT"

        if direction:
            entry_bar_idx = i + 1
            if entry_bar_idx >= len(bars):
                continue
            entry_bar = bars.iloc[entry_bar_idx]
            entry_hr = bar_hour(entry_bar["bar_ts"])
            if entry_hr >= 16.0:
                continue
            entry_price = entry_bar["open"] + (SLIPPAGE if direction == "LONG" else -SLIPPAGE)
            pnl_ticks, reason = simulate_exit(bars, entry_bar_idx, direction, entry_price, sl_ticks, tp_ticks)
            pnl_dollar = pnl_ticks * TICK_VALUE - 2 * COMMISSION_PER_SIDE
            trades.append({"direction": direction, "pnl": pnl_dollar, "reason": reason})
            break  # 1 trade/day

    return trades


def compute_metrics(all_trades):
    """Compute PnL, win%, PF, trade count from list of trade dicts."""
    if not all_trades:
        return {"pnl": 0, "win_pct": 0, "pf": 0, "trades": 0, "per_session": 0}

    pnls = [t["pnl"] for t in all_trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)
    win_pct = len(wins) / len(pnls) * 100 if pnls else 0
    gross_win = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0.01
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0

    return {
        "pnl": total_pnl,
        "win_pct": win_pct,
        "pf": pf,
        "trades": len(pnls),
        "per_session": len(pnls) / 3.0,
    }


def main():
    t0 = time.time()
    print("Loading 1m data...")
    df_1m = load_1m_data()
    print(f"  Loaded {len(df_1m)} bars")

    timeframes = [5, 10, 15, 20, 30, 60]

    # Pre-resample all sessions for all timeframes
    print("Resampling sessions...")
    session_bars = {}  # (tf, date) -> DataFrame
    session_vwap = {}  # (tf, date) -> array
    for tf in timeframes:
        for date_str in RTH_DATES:
            bars = resample_to_tf(df_1m, tf, date_str)
            if bars.empty:
                continue
            vwap = compute_vwap_series(bars)
            session_bars[(tf, date_str)] = bars
            session_vwap[(tf, date_str)] = vwap
            # print(f"  TF={tf}m, {date_str}: {len(bars)} bars")

    # Results storage
    # best_configs[strategy][tf] = {params, metrics}
    all_results = defaultdict(list)

    total_combos = 0
    for tf in timeframes:
        p = TF_PARAMS[tf]
        # ChNavy6 & Ch2Navy6: SL x TP x Confirm
        n1 = len(p["SL"]) * len(p["TP"]) * len(BOUNCE_CONFIRMS)
        # CHTrendNavy6: SL x TP x SlopeLB x PullbackTicks
        n2 = len(p["SL"]) * len(p["TP"]) * len(SLOPE_LBS) * len(PULLBACK_TICKS)
        total_combos += 2 * n1 + n2
    print(f"Total parameter combinations: {total_combos}")

    print("Running backtests...")

    for tf in timeframes:
        p = TF_PARAMS[tf]
        print(f"\n  TF={tf}m ...")

        # ── ChNavy6 ──
        for sl, tp, confirm in product(p["SL"], p["TP"], BOUNCE_CONFIRMS):
            all_trades = []
            for date_str in RTH_DATES:
                key = (tf, date_str)
                if key not in session_bars:
                    continue
                trades = run_chnavy6(session_bars[key], session_vwap[key], sl, tp, confirm)
                all_trades.extend(trades)
            m = compute_metrics(all_trades)
            all_results[("ChNavy6", tf)].append({
                "params": f"SL={sl} TP={tp} Confirm={confirm}",
                "sl": sl, "tp": tp, "confirm": confirm,
                **m,
            })

        # ── Ch2Navy6 ──
        for sl, tp, confirm in product(p["SL"], p["TP"], BOUNCE_CONFIRMS):
            all_trades = []
            for date_str in RTH_DATES:
                key = (tf, date_str)
                if key not in session_bars:
                    continue
                trades = run_ch2navy6(session_bars[key], session_vwap[key], sl, tp, confirm)
                all_trades.extend(trades)
            m = compute_metrics(all_trades)
            all_results[("Ch2Navy6", tf)].append({
                "params": f"SL={sl} TP={tp} Confirm={confirm}",
                "sl": sl, "tp": tp, "confirm": confirm,
                **m,
            })

        # ── CHTrendNavy6 ──
        for sl, tp, slb, pb in product(p["SL"], p["TP"], SLOPE_LBS, PULLBACK_TICKS):
            all_trades = []
            for date_str in RTH_DATES:
                key = (tf, date_str)
                if key not in session_bars:
                    continue
                trades = run_chtrendnavy6(session_bars[key], session_vwap[key], sl, tp, slb, pb)
                all_trades.extend(trades)
            m = compute_metrics(all_trades)
            all_results[("CHTrendNavy6", tf)].append({
                "params": f"SL={sl} TP={tp} SlopeLB={slb} PB={pb}",
                "sl": sl, "tp": tp, "slope_lb": slb, "pb": pb,
                **m,
            })

    # ── Find best configs ──
    best = {}  # (strategy, tf) -> best result
    for (strat, tf), results in all_results.items():
        # Sort by PnL descending, then PF
        results.sort(key=lambda x: (x["pnl"], x["pf"]), reverse=True)
        best[(strat, tf)] = results[0]

    # ── Write results ──
    elapsed = time.time() - t0
    strategies = ["ChNavy6", "Ch2Navy6", "CHTrendNavy6"]

    lines = []
    lines.append("=" * 90)
    lines.append("ROUND 4: MULTI-TIMEFRAME VWAP STRATEGY COMPARISON")
    lines.append(f"Data: NQ futures, Apr 8-10 2026 (3 RTH sessions)")
    lines.append(f"Timeframes: {', '.join(str(t)+'m' for t in timeframes)}")
    lines.append(f"Total param combos tested: {total_combos}")
    lines.append(f"Runtime: {elapsed:.1f}s")
    lines.append("=" * 90)

    # ── Best config per strategy per timeframe ──
    for strat in strategies:
        lines.append("")
        lines.append("-" * 90)
        lines.append(f"STRATEGY: {strat}")
        lines.append("-" * 90)
        lines.append(f"{'TF':>4s}  {'PnL':>10s}  {'Win%':>6s}  {'PF':>6s}  {'Trades':>6s}  {'Tr/Sess':>7s}  Best Config")
        lines.append(f"{'----':>4s}  {'----------':>10s}  {'------':>6s}  {'------':>6s}  {'------':>6s}  {'-------':>7s}  -----------")
        for tf in timeframes:
            b = best.get((strat, tf))
            if b:
                lines.append(
                    f"{tf:>3d}m  ${b['pnl']:>9.2f}  {b['win_pct']:>5.1f}%  {b['pf']:>6.2f}  {b['trades']:>6d}  {b['per_session']:>7.2f}  {b['params']}"
                )

    # ── Cross-timeframe comparison table ──
    lines.append("")
    lines.append("=" * 90)
    lines.append("CROSS-TIMEFRAME COMPARISON: Best TF per Strategy")
    lines.append("=" * 90)
    lines.append(f"{'Strategy':<16s}  {'Best TF':>7s}  {'PnL':>10s}  {'Win%':>6s}  {'PF':>6s}  {'Trades':>6s}  Config")
    lines.append(f"{'--------':<16s}  {'-------':>7s}  {'----------':>10s}  {'------':>6s}  {'------':>6s}  {'------':>6s}  ------")
    for strat in strategies:
        best_tf = None
        best_pnl = -999999
        for tf in timeframes:
            b = best.get((strat, tf))
            if b and b["pnl"] > best_pnl:
                best_pnl = b["pnl"]
                best_tf = tf
        if best_tf:
            b = best[(strat, best_tf)]
            lines.append(
                f"{strat:<16s}  {best_tf:>5d}m  ${b['pnl']:>9.2f}  {b['win_pct']:>5.1f}%  {b['pf']:>6.2f}  {b['trades']:>6d}  {b['params']}"
            )

    # ── Trade frequency analysis ──
    lines.append("")
    lines.append("=" * 90)
    lines.append("TRADE FREQUENCY ANALYSIS (trades/session at best config)")
    lines.append("=" * 90)
    lines.append(f"{'TF':>4s}  {'ChNavy6':>10s}  {'Ch2Navy6':>10s}  {'CHTrendNavy6':>14s}")
    lines.append(f"{'----':>4s}  {'----------':>10s}  {'----------':>10s}  {'--------------':>14s}")
    for tf in timeframes:
        vals = []
        for strat in strategies:
            b = best.get((strat, tf))
            if b:
                vals.append(f"{b['per_session']:.2f}")
            else:
                vals.append("N/A")
        lines.append(f"{tf:>3d}m  {vals[0]:>10s}  {vals[1]:>10s}  {vals[2]:>14s}")

    # ── Top 5 configs overall ──
    lines.append("")
    lines.append("=" * 90)
    lines.append("TOP 10 CONFIGS ACROSS ALL STRATEGIES AND TIMEFRAMES")
    lines.append("=" * 90)
    all_flat = []
    for (strat, tf), results in all_results.items():
        for r in results:
            all_flat.append({"strategy": strat, "tf": tf, **r})
    all_flat.sort(key=lambda x: (x["pnl"], x["pf"]), reverse=True)
    lines.append(f"{'#':>2s}  {'Strategy':<16s}  {'TF':>4s}  {'PnL':>10s}  {'Win%':>6s}  {'PF':>6s}  {'Trades':>6s}  Config")
    lines.append(f"{'--':>2s}  {'--------':<16s}  {'----':>4s}  {'----------':>10s}  {'------':>6s}  {'------':>6s}  {'------':>6s}  ------")
    for i, r in enumerate(all_flat[:10]):
        lines.append(
            f"{i+1:>2d}  {r['strategy']:<16s}  {r['tf']:>3d}m  ${r['pnl']:>9.2f}  {r['win_pct']:>5.1f}%  {r['pf']:>6.2f}  {r['trades']:>6d}  {r['params']}"
        )

    # ── PnL heatmap by strategy x tf ──
    lines.append("")
    lines.append("=" * 90)
    lines.append("PNL HEATMAP: Best PnL per Strategy x Timeframe")
    lines.append("=" * 90)
    header = f"{'Strategy':<16s}" + "".join(f"  {tf:>5d}m" for tf in timeframes)
    lines.append(header)
    lines.append("-" * len(header))
    for strat in strategies:
        row = f"{strat:<16s}"
        for tf in timeframes:
            b = best.get((strat, tf))
            if b:
                row += f"  ${b['pnl']:>5.0f}"
            else:
                row += f"  {'N/A':>6s}"
        lines.append(row)

    # ── Overall recommendation ──
    lines.append("")
    lines.append("=" * 90)
    lines.append("OVERALL RECOMMENDATION")
    lines.append("=" * 90)

    # Find which TF wins across strategies
    tf_wins = defaultdict(int)
    tf_total_pnl = defaultdict(float)
    for strat in strategies:
        best_tf = None
        best_pnl = -999999
        for tf in timeframes:
            b = best.get((strat, tf))
            if b and b["pnl"] > best_pnl:
                best_pnl = b["pnl"]
                best_tf = tf
        if best_tf:
            tf_wins[best_tf] += 1
    for tf in timeframes:
        for strat in strategies:
            b = best.get((strat, tf))
            if b:
                tf_total_pnl[tf] += b["pnl"]

    best_overall_tf = max(timeframes, key=lambda t: tf_total_pnl[t])
    lines.append(f"")
    lines.append(f"Timeframe wins (how many strategies each TF is best for):")
    for tf in timeframes:
        marker = " <-- " if tf == best_overall_tf else ""
        lines.append(f"  {tf:>3d}m: {tf_wins.get(tf, 0)} strategy wins, combined best-PnL = ${tf_total_pnl[tf]:.2f}{marker}")

    lines.append(f"")
    if best_overall_tf == 30:
        lines.append(f"VERDICT: 30m IS confirmed as the optimal timeframe (highest combined PnL).")
    else:
        lines.append(f"VERDICT: {best_overall_tf}m outperforms 30m! Consider switching from 30m to {best_overall_tf}m.")
        b30_pnl = tf_total_pnl[30]
        bbest_pnl = tf_total_pnl[best_overall_tf]
        lines.append(f"  30m combined PnL: ${b30_pnl:.2f}")
        lines.append(f"  {best_overall_tf}m combined PnL: ${bbest_pnl:.2f}")
        lines.append(f"  Improvement: ${bbest_pnl - b30_pnl:.2f} ({((bbest_pnl - b30_pnl) / max(abs(b30_pnl), 0.01)) * 100:.1f}%)")

    lines.append(f"")
    lines.append(f"Note: Results based on 3 RTH sessions only. More data needed for confidence.")
    lines.append("=" * 90)

    output = "\n".join(lines)
    with open(RESULTS_PATH, "w") as f:
        f.write(output)

    print(output)
    print(f"\nResults written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
