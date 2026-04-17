#!/usr/bin/env python3
"""
opt5_loss_breaker.py — Circuit Breaker & Drawdown Management for ChNavy6 VWAP Bounce
Tests: consecutive loss breakers, drawdown pause, monthly loss cap,
       win-required resume, reduced size after losses, best combination.
"""

import pandas as pd
import numpy as np
from datetime import time, timedelta
from copy import deepcopy
import sys

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
SL_TICKS = 160
TP_TICKS = 560
SESSION_START = time(9, 30)
SESSION_END = time(14, 30)
FLATTEN_TIME = time(16, 0)
VWAP_CROSS_MIN = 5.0  # points above/below VWAP required

CSV_PATH = "/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv"
OUT_PATH = "/Users/teaceo/DEEP6/scripts/opt5_loss_breaker.txt"


def load_data():
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("US/Eastern")
    df = df[["ts_event", "open", "high", "low", "close", "volume"]].copy()
    df = df.sort_values("ts_event").reset_index(drop=True)
    return df


def resample_30m(df):
    """Resample 1-min bars to 30-min bars per calendar date."""
    df = df.set_index("ts_event")
    bars_30 = df.resample("30min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna(subset=["open"]).reset_index()
    return bars_30


def generate_signals(bars):
    """
    Run ChNavy6 VWAP Bounce on 30-min bars.
    Returns list of trade dicts with entry info + outcome.
    """
    trades = []
    cum_tp_vol = 0.0
    cum_vol = 0
    prev_close = None
    prev_vwap = None
    trade_today = False
    current_date = None

    for i, row in bars.iterrows():
        bar_time = row["ts_event"]
        bar_date = bar_time.date()
        t = bar_time.time()

        # New day reset
        if bar_date != current_date:
            current_date = bar_date
            trade_today = False
            cum_tp_vol = 0.0
            cum_vol = 0
            prev_close = None
            prev_vwap = None

        # Accumulate VWAP
        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        cum_tp_vol += typical * row["volume"]
        cum_vol += row["volume"]
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else row["close"]

        # Check session window
        if t < SESSION_START or t >= SESSION_END:
            prev_close = row["close"]
            prev_vwap = vwap
            continue

        if trade_today:
            prev_close = row["close"]
            prev_vwap = vwap
            continue

        if prev_close is None or prev_vwap is None:
            prev_close = row["close"]
            prev_vwap = vwap
            continue

        was_below = prev_close < prev_vwap
        was_above = prev_close > prev_vwap
        cross_dist = abs(row["close"] - vwap)

        direction = None
        if was_below and row["close"] > vwap and cross_dist >= VWAP_CROSS_MIN:
            direction = "LONG"
        elif was_above and row["close"] < vwap and cross_dist >= VWAP_CROSS_MIN:
            direction = "SHORT"

        if direction:
            trade_today = True
            slip = SLIPPAGE_TICKS * TICK_SIZE
            if direction == "LONG":
                entry = row["close"] + slip
                sl_price = entry - SL_TICKS * TICK_SIZE
                tp_price = entry + TP_TICKS * TICK_SIZE
            else:
                entry = row["close"] - slip
                sl_price = entry + SL_TICKS * TICK_SIZE
                tp_price = entry - TP_TICKS * TICK_SIZE

            # Resolve trade using subsequent bars
            outcome = resolve_trade(bars, i, direction, entry, sl_price, tp_price)
            trade = {
                "date": bar_date,
                "month": bar_date.month,
                "time": t,
                "direction": direction,
                "entry": entry,
                "sl": sl_price,
                "tp": tp_price,
                **outcome,
            }
            trades.append(trade)

        prev_close = row["close"]
        prev_vwap = vwap

    return trades


def resolve_trade(bars, entry_idx, direction, entry, sl_price, tp_price):
    """Walk forward from entry bar to determine SL/TP/flatten outcome."""
    entry_date = bars.iloc[entry_idx]["ts_event"].date()
    comm = COMMISSION_PER_SIDE * 2  # round trip

    for j in range(entry_idx + 1, len(bars)):
        row = bars.iloc[j]
        if row["ts_event"].date() != entry_date:
            break
        t = row["ts_event"].time()

        # Check flatten
        if t >= FLATTEN_TIME:
            exit_price = row["close"]
            if direction == "LONG":
                pnl_ticks = (exit_price - entry) / TICK_SIZE
            else:
                pnl_ticks = (entry - exit_price) / TICK_SIZE
            pnl = pnl_ticks * TICK_VALUE - comm
            return {"exit": exit_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "FLATTEN", "won": pnl > 0}

        # Check SL/TP hit within bar
        if direction == "LONG":
            if row["low"] <= sl_price:
                pnl_ticks = -SL_TICKS
                pnl = pnl_ticks * TICK_VALUE - comm
                return {"exit": sl_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "SL", "won": False}
            if row["high"] >= tp_price:
                pnl_ticks = TP_TICKS
                pnl = pnl_ticks * TICK_VALUE - comm
                return {"exit": tp_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "TP", "won": True}
        else:
            if row["high"] >= sl_price:
                pnl_ticks = -SL_TICKS
                pnl = pnl_ticks * TICK_VALUE - comm
                return {"exit": sl_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "SL", "won": False}
            if row["low"] <= tp_price:
                pnl_ticks = TP_TICKS
                pnl = pnl_ticks * TICK_VALUE - comm
                return {"exit": tp_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "TP", "won": True}

    # End of data — flatten at last bar
    last = bars.iloc[min(entry_idx + 1, len(bars) - 1)]
    exit_price = last["close"]
    if direction == "LONG":
        pnl_ticks = (exit_price - entry) / TICK_SIZE
    else:
        pnl_ticks = (entry - exit_price) / TICK_SIZE
    pnl = pnl_ticks * TICK_VALUE - comm
    return {"exit": exit_price, "pnl_ticks": pnl_ticks, "pnl": pnl, "exit_type": "FLATTEN", "won": pnl > 0}


def calc_metrics(pnls, label=""):
    """Calculate standard metrics from a list of PnLs."""
    if not pnls:
        return {"trades": 0, "net_pnl": 0, "win_pct": 0, "pf": 0, "sharpe": 0, "max_dd": 0}
    arr = np.array(pnls)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gross_win = wins.sum() if len(wins) else 0
    gross_loss = abs(losses.sum()) if len(losses) else 0.001
    cum = np.cumsum(arr)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = dd.max() if len(dd) else 0
    sharpe = (arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0
    return {
        "trades": len(pnls),
        "net_pnl": round(sum(pnls), 2),
        "win_pct": round(len(wins) / len(pnls) * 100, 1),
        "pf": round(gross_win / gross_loss, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
    }


def march_pnl(trades_taken, all_trades):
    """Sum PnL for March trades."""
    march = [t for t in trades_taken if t["month"] == 3]
    return round(sum(t["pnl"] for t in march), 2), len(march)


# ── Circuit Breaker Engines ───────────────────────────────────────────────

def apply_consecutive_loss_breaker(all_trades, n_trigger, m_cooldown_days):
    """After N consecutive losses, stop for M calendar days."""
    taken = []
    skipped = []
    consec_losses = 0
    pause_until = None

    for t in all_trades:
        if pause_until and t["date"] < pause_until:
            skipped.append(t)
            continue

        if pause_until and t["date"] >= pause_until:
            pause_until = None

        taken.append(t)
        if not t["won"]:
            consec_losses += 1
            if consec_losses >= n_trigger:
                pause_until = t["date"] + timedelta(days=m_cooldown_days)
                consec_losses = 0
        else:
            consec_losses = 0

    return taken, skipped


def apply_drawdown_pause(all_trades, threshold):
    """Pause when cumulative PnL drops $threshold from peak. Resume when paper trades recover."""
    taken = []
    skipped = []
    cum_pnl = 0.0
    peak_pnl = 0.0
    paused = False
    paper_pnl_at_pause = 0.0
    paper_cum = 0.0

    for t in all_trades:
        if paused:
            # Paper trade: track what would have happened
            paper_cum += t["pnl"]
            if paper_cum >= 0:  # recovered from pause point
                paused = False
                paper_cum = 0.0
                # Resume with this trade
                taken.append(t)
                cum_pnl += t["pnl"]
                peak_pnl = max(peak_pnl, cum_pnl)
            else:
                skipped.append(t)
            continue

        taken.append(t)
        cum_pnl += t["pnl"]
        peak_pnl = max(peak_pnl, cum_pnl)

        if peak_pnl - cum_pnl >= threshold:
            paused = True
            paper_cum = 0.0

    return taken, skipped


def apply_monthly_loss_cap(all_trades, cap):
    """Stop trading for rest of month after losing $cap in that month."""
    taken = []
    skipped = []
    monthly_pnl = {}
    capped_months = set()

    for t in all_trades:
        month_key = (t["date"].year, t["month"])
        if month_key in capped_months:
            skipped.append(t)
            continue

        taken.append(t)
        monthly_pnl[month_key] = monthly_pnl.get(month_key, 0) + t["pnl"]
        if monthly_pnl[month_key] <= -cap:
            capped_months.add(month_key)

    return taken, skipped


def apply_win_required_resume(all_trades, n_trigger):
    """After N consecutive losses, paper trade next signal. Resume only if it's a winner."""
    taken = []
    skipped = []
    consec_losses = 0
    waiting_for_win = False

    for t in all_trades:
        if waiting_for_win:
            if t["won"]:
                waiting_for_win = False
                # This winning paper trade is skipped (it was paper)
                skipped.append(t)
            else:
                skipped.append(t)
            continue

        taken.append(t)
        if not t["won"]:
            consec_losses += 1
            if consec_losses >= n_trigger:
                waiting_for_win = True
                consec_losses = 0
        else:
            consec_losses = 0

    return taken, skipped


def apply_reduced_size(all_trades, n_trigger):
    """After N consecutive losses, trade at 0.5 size. Resume full after a win."""
    taken = []
    skipped = []  # none skipped, all taken
    consec_losses = 0
    half_size = False
    pnls = []

    for t in all_trades:
        if half_size:
            scaled_pnl = t["pnl"] * 0.5
            t_copy = dict(t)
            t_copy["pnl"] = scaled_pnl
            t_copy["half_size"] = True
            taken.append(t_copy)
            if t["won"]:
                half_size = False
                consec_losses = 0
            else:
                consec_losses += 1
        else:
            t_copy = dict(t)
            t_copy["half_size"] = False
            taken.append(t_copy)
            if not t["won"]:
                consec_losses += 1
                if consec_losses >= n_trigger:
                    half_size = True
            else:
                consec_losses = 0

    return taken, skipped


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("Loading data...")
    df = load_data()
    print(f"  {len(df)} 1-min bars loaded")

    print("Resampling to 30-min bars...")
    bars = resample_30m(df)
    print(f"  {len(bars)} 30-min bars")

    print("Generating baseline signals...")
    all_trades = generate_signals(bars)
    print(f"  {len(all_trades)} trades generated")

    baseline_pnls = [t["pnl"] for t in all_trades]
    baseline = calc_metrics(baseline_pnls)
    march_base_pnl, march_base_n = march_pnl(all_trades, all_trades)

    lines = []
    def out(s=""):
        lines.append(s)
        print(s)

    out("=" * 90)
    out("OPT5: CIRCUIT BREAKER & DRAWDOWN MANAGEMENT — ChNavy6 VWAP Bounce (30m)")
    out("=" * 90)
    out(f"Data: {len(df)} 1-min bars → {len(bars)} 30-min bars (Jan 2 – Apr 10, 2026)")
    out(f"Strategy: SL={SL_TICKS}t, TP={TP_TICKS}t, 1 trade/day max")
    out()

    out("── BASELINE ──────────────────────────────────────────────────────────────")
    out(f"  Trades: {baseline['trades']}  |  Net PnL: ${baseline['net_pnl']:,.2f}  |  "
        f"Win%: {baseline['win_pct']}%  |  PF: {baseline['pf']}  |  "
        f"Sharpe: {baseline['sharpe']}  |  Max DD: ${baseline['max_dd']:,.2f}")
    out(f"  March: {march_base_n} trades, PnL: ${march_base_pnl:,.2f}")
    out()

    # Show monthly breakdown
    out("── BASELINE MONTHLY BREAKDOWN ────────────────────────────────────────────")
    for m in [1, 2, 3, 4]:
        mt = [t for t in all_trades if t["month"] == m]
        if mt:
            mp = calc_metrics([t["pnl"] for t in mt])
            out(f"  Month {m}: {mp['trades']} trades, ${mp['net_pnl']:,.2f}, "
                f"Win%: {mp['win_pct']}%, PF: {mp['pf']}, Max DD: ${mp['max_dd']:,.2f}")
    out()

    # Show loss streaks in baseline
    out("── BASELINE LOSS STREAKS ─────────────────────────────────────────────────")
    streak = 0
    max_streak = 0
    streaks = []
    for t in all_trades:
        if not t["won"]:
            streak += 1
        else:
            if streak > 0:
                streaks.append(streak)
            streak = 0
    if streak > 0:
        streaks.append(streak)
    max_streak = max(streaks) if streaks else 0
    streak_counts = {}
    for s in streaks:
        streak_counts[s] = streak_counts.get(s, 0) + 1
    out(f"  Max consecutive losses: {max_streak}")
    out(f"  Streak distribution: {dict(sorted(streak_counts.items()))}")
    out()

    results = []  # (label, metrics_dict, march_pnl, march_n, trades_taken, trades_skipped)

    # ── 1. Consecutive Loss Breaker ───────────────────────────────────────
    out("=" * 90)
    out("1. CONSECUTIVE LOSS BREAKER (N losses → pause M days)")
    out("=" * 90)
    out(f"{'N':>3} {'M':>3} {'Trades':>7} {'Skipped':>8} {'Net PnL':>12} {'Win%':>7} "
        f"{'PF':>6} {'Sharpe':>7} {'Max DD':>10} {'Mar PnL':>10} {'Mar N':>6}")
    out("-" * 90)

    best_clb = None
    best_clb_pnl = -999999
    for n in [2, 3, 4, 5]:
        for m in [1, 2, 3, 5]:
            taken, skipped = apply_consecutive_loss_breaker(all_trades, n, m)
            pnls = [t["pnl"] for t in taken]
            met = calc_metrics(pnls)
            mp, mn = march_pnl(taken, all_trades)
            out(f"{n:>3} {m:>3} {met['trades']:>7} {len(skipped):>8} ${met['net_pnl']:>10,.2f} "
                f"{met['win_pct']:>6.1f}% {met['pf']:>5.2f} {met['sharpe']:>7.2f} "
                f"${met['max_dd']:>9,.2f} ${mp:>9,.2f} {mn:>5}")
            if met['net_pnl'] > best_clb_pnl:
                best_clb_pnl = met['net_pnl']
                best_clb = (n, m, met, mp, mn, taken, skipped)
            results.append(("CLB", n, m, met, mp, mn))
    out()
    if best_clb:
        out(f"  >> Best: N={best_clb[0]}, M={best_clb[1]} → ${best_clb[2]['net_pnl']:,.2f} "
            f"(+${best_clb[2]['net_pnl'] - baseline['net_pnl']:,.2f} vs baseline)")
    out()

    # ── 2. Drawdown Pause ─────────────────────────────────────────────────
    out("=" * 90)
    out("2. DRAWDOWN PAUSE (pause when DD from peak exceeds $X, resume on paper recovery)")
    out("=" * 90)
    out(f"{'Threshold':>10} {'Trades':>7} {'Skipped':>8} {'Net PnL':>12} {'Win%':>7} "
        f"{'PF':>6} {'Sharpe':>7} {'Max DD':>10} {'Mar PnL':>10} {'Mar N':>6}")
    out("-" * 90)

    best_ddp = None
    best_ddp_pnl = -999999
    for thresh in [2000, 3000, 4000, 5000]:
        taken, skipped = apply_drawdown_pause(all_trades, thresh)
        pnls = [t["pnl"] for t in taken]
        met = calc_metrics(pnls)
        mp, mn = march_pnl(taken, all_trades)
        out(f"${thresh:>9,} {met['trades']:>7} {len(skipped):>8} ${met['net_pnl']:>10,.2f} "
            f"{met['win_pct']:>6.1f}% {met['pf']:>5.2f} {met['sharpe']:>7.2f} "
            f"${met['max_dd']:>9,.2f} ${mp:>9,.2f} {mn:>5}")
        if met['net_pnl'] > best_ddp_pnl:
            best_ddp_pnl = met['net_pnl']
            best_ddp = (thresh, met, mp, mn, taken, skipped)
        results.append(("DDP", thresh, 0, met, mp, mn))
    out()
    if best_ddp:
        out(f"  >> Best: ${best_ddp[0]:,} threshold → ${best_ddp[1]['net_pnl']:,.2f} "
            f"(+${best_ddp[1]['net_pnl'] - baseline['net_pnl']:,.2f} vs baseline)")
    out()

    # ── 3. Monthly Loss Cap ───────────────────────────────────────────────
    out("=" * 90)
    out("3. MONTHLY LOSS CAP (stop trading for rest of month after -$X)")
    out("=" * 90)
    out(f"{'Cap':>10} {'Trades':>7} {'Skipped':>8} {'Net PnL':>12} {'Win%':>7} "
        f"{'PF':>6} {'Sharpe':>7} {'Max DD':>10} {'Mar PnL':>10} {'Mar N':>6}")
    out("-" * 90)

    best_mlc = None
    best_mlc_pnl = -999999
    for cap in [2000, 3000, 4000, 5000]:
        taken, skipped = apply_monthly_loss_cap(all_trades, cap)
        pnls = [t["pnl"] for t in taken]
        met = calc_metrics(pnls)
        mp, mn = march_pnl(taken, all_trades)
        out(f"${cap:>9,} {met['trades']:>7} {len(skipped):>8} ${met['net_pnl']:>10,.2f} "
            f"{met['win_pct']:>6.1f}% {met['pf']:>5.2f} {met['sharpe']:>7.2f} "
            f"${met['max_dd']:>9,.2f} ${mp:>9,.2f} {mn:>5}")
        if met['net_pnl'] > best_mlc_pnl:
            best_mlc_pnl = met['net_pnl']
            best_mlc = (cap, met, mp, mn, taken, skipped)
        results.append(("MLC", cap, 0, met, mp, mn))
    out()
    if best_mlc:
        out(f"  >> Best: ${best_mlc[0]:,} cap → ${best_mlc[1]['net_pnl']:,.2f} "
            f"(+${best_mlc[1]['net_pnl'] - baseline['net_pnl']:,.2f} vs baseline)")
    out()

    # ── 4. Win-Required Resume ────────────────────────────────────────────
    out("=" * 90)
    out("4. WIN-REQUIRED RESUME (after N losses, paper trade 1 → resume only if winner)")
    out("=" * 90)
    out(f"{'N':>3} {'Trades':>7} {'Skipped':>8} {'Net PnL':>12} {'Win%':>7} "
        f"{'PF':>6} {'Sharpe':>7} {'Max DD':>10} {'Mar PnL':>10} {'Mar N':>6}")
    out("-" * 90)

    best_wrr = None
    best_wrr_pnl = -999999
    for n in [2, 3, 4, 5]:
        taken, skipped = apply_win_required_resume(all_trades, n)
        pnls = [t["pnl"] for t in taken]
        met = calc_metrics(pnls)
        mp, mn = march_pnl(taken, all_trades)
        out(f"{n:>3} {met['trades']:>7} {len(skipped):>8} ${met['net_pnl']:>10,.2f} "
            f"{met['win_pct']:>6.1f}% {met['pf']:>5.2f} {met['sharpe']:>7.2f} "
            f"${met['max_dd']:>9,.2f} ${mp:>9,.2f} {mn:>5}")
        if met['net_pnl'] > best_wrr_pnl:
            best_wrr_pnl = met['net_pnl']
            best_wrr = (n, met, mp, mn, taken, skipped)
        results.append(("WRR", n, 0, met, mp, mn))
    out()
    if best_wrr:
        out(f"  >> Best: N={best_wrr[0]} → ${best_wrr[1]['net_pnl']:,.2f} "
            f"(+${best_wrr[1]['net_pnl'] - baseline['net_pnl']:,.2f} vs baseline)")
    out()

    # ── 5. Reduced Size After Losses ──────────────────────────────────────
    out("=" * 90)
    out("5. REDUCED SIZE (0.5x after N losses, full size after win)")
    out("=" * 90)
    out(f"{'N':>3} {'Trades':>7} {'Half':>6} {'Net PnL':>12} {'Win%':>7} "
        f"{'PF':>6} {'Sharpe':>7} {'Max DD':>10} {'Mar PnL':>10} {'Mar N':>6}")
    out("-" * 90)

    best_rs = None
    best_rs_pnl = -999999
    for n in [2, 3, 4]:
        taken, skipped = apply_reduced_size(all_trades, n)
        pnls = [t["pnl"] for t in taken]
        met = calc_metrics(pnls)
        half_count = sum(1 for t in taken if t.get("half_size", False))
        mp, mn = march_pnl(taken, all_trades)
        out(f"{n:>3} {met['trades']:>7} {half_count:>6} ${met['net_pnl']:>10,.2f} "
            f"{met['win_pct']:>6.1f}% {met['pf']:>5.2f} {met['sharpe']:>7.2f} "
            f"${met['max_dd']:>9,.2f} ${mp:>9,.2f} {mn:>5}")
        if met['net_pnl'] > best_rs_pnl:
            best_rs_pnl = met['net_pnl']
            best_rs = (n, met, mp, mn, taken, skipped, half_count)
        results.append(("RS", n, 0, met, mp, mn))
    out()
    if best_rs:
        out(f"  >> Best: N={best_rs[0]} → ${best_rs[1]['net_pnl']:,.2f} "
            f"(+${best_rs[1]['net_pnl'] - baseline['net_pnl']:,.2f} vs baseline)")
    out()

    # ── 6. Best Combination ───────────────────────────────────────────────
    out("=" * 90)
    out("6. BEST COMBINATION TESTS")
    out("=" * 90)
    out()

    # Identify best from each category
    combo_configs = []

    # Combo A: Best CLB + Monthly Loss Cap
    if best_clb and best_mlc:
        out("  Combo A: Best CLB + Best Monthly Cap")
        taken_a, _ = apply_consecutive_loss_breaker(all_trades, best_clb[0], best_clb[1])
        taken_a2, skipped_a = apply_monthly_loss_cap(taken_a, best_mlc[0])
        pnls_a = [t["pnl"] for t in taken_a2]
        met_a = calc_metrics(pnls_a)
        mp_a, mn_a = march_pnl(taken_a2, all_trades)
        skipped_total = len(all_trades) - len(taken_a2)
        out(f"    CLB(N={best_clb[0]},M={best_clb[1]}) + MLC(${best_mlc[0]:,})")
        out(f"    Trades: {met_a['trades']}  Skipped: {skipped_total}  Net: ${met_a['net_pnl']:,.2f}  "
            f"Win%: {met_a['win_pct']}%  PF: {met_a['pf']}  Sharpe: {met_a['sharpe']}  "
            f"Max DD: ${met_a['max_dd']:,.2f}  Mar: ${mp_a:,.2f} ({mn_a}t)")
        combo_configs.append(("A", met_a, mp_a))
        out()

    # Combo B: Best Drawdown Pause + Reduced Size
    if best_ddp and best_rs:
        out("  Combo B: Best Drawdown Pause + Best Reduced Size")
        taken_b, _ = apply_drawdown_pause(all_trades, best_ddp[0])
        taken_b2, _ = apply_reduced_size(taken_b, best_rs[0])
        pnls_b = [t["pnl"] for t in taken_b2]
        met_b = calc_metrics(pnls_b)
        mp_b, mn_b = march_pnl(taken_b2, all_trades)
        skipped_total = len(all_trades) - len(taken_b2)
        out(f"    DDP(${best_ddp[0]:,}) + RS(N={best_rs[0]})")
        out(f"    Trades: {met_b['trades']}  Skipped: {skipped_total}  Net: ${met_b['net_pnl']:,.2f}  "
            f"Win%: {met_b['win_pct']}%  PF: {met_b['pf']}  Sharpe: {met_b['sharpe']}  "
            f"Max DD: ${met_b['max_dd']:,.2f}  Mar: ${mp_b:,.2f} ({mn_b}t)")
        combo_configs.append(("B", met_b, mp_b))
        out()

    # Combo C: Monthly Cap + Win-Required Resume
    if best_mlc and best_wrr:
        out("  Combo C: Best Monthly Cap + Win-Required Resume")
        taken_c, _ = apply_monthly_loss_cap(all_trades, best_mlc[0])
        taken_c2, skipped_c = apply_win_required_resume(taken_c, best_wrr[0])
        pnls_c = [t["pnl"] for t in taken_c2]
        met_c = calc_metrics(pnls_c)
        mp_c, mn_c = march_pnl(taken_c2, all_trades)
        skipped_total = len(all_trades) - len(taken_c2)
        out(f"    MLC(${best_mlc[0]:,}) + WRR(N={best_wrr[0]})")
        out(f"    Trades: {met_c['trades']}  Skipped: {skipped_total}  Net: ${met_c['net_pnl']:,.2f}  "
            f"Win%: {met_c['win_pct']}%  PF: {met_c['pf']}  Sharpe: {met_c['sharpe']}  "
            f"Max DD: ${met_c['max_dd']:,.2f}  Mar: ${mp_c:,.2f} ({mn_c}t)")
        combo_configs.append(("C", met_c, mp_c))
        out()

    # Combo D: CLB + Drawdown Pause + Reduced Size (triple layer)
    if best_clb and best_ddp and best_rs:
        out("  Combo D: CLB + Drawdown Pause + Reduced Size (triple layer)")
        taken_d, _ = apply_consecutive_loss_breaker(all_trades, best_clb[0], best_clb[1])
        taken_d2, _ = apply_drawdown_pause(taken_d, best_ddp[0])
        taken_d3, _ = apply_reduced_size(taken_d2, best_rs[0])
        pnls_d = [t["pnl"] for t in taken_d3]
        met_d = calc_metrics(pnls_d)
        mp_d, mn_d = march_pnl(taken_d3, all_trades)
        skipped_total = len(all_trades) - len(taken_d3)
        out(f"    CLB(N={best_clb[0]},M={best_clb[1]}) + DDP(${best_ddp[0]:,}) + RS(N={best_rs[0]})")
        out(f"    Trades: {met_d['trades']}  Skipped: {skipped_total}  Net: ${met_d['net_pnl']:,.2f}  "
            f"Win%: {met_d['win_pct']}%  PF: {met_d['pf']}  Sharpe: {met_d['sharpe']}  "
            f"Max DD: ${met_d['max_dd']:,.2f}  Mar: ${mp_d:,.2f} ({mn_d}t)")
        combo_configs.append(("D", met_d, mp_d))
        out()

    # ── Summary ───────────────────────────────────────────────────────────
    out("=" * 90)
    out("SUMMARY — ALL CATEGORY WINNERS vs BASELINE")
    out("=" * 90)
    out(f"{'Category':<30} {'Trades':>7} {'Net PnL':>12} {'Win%':>7} {'PF':>6} "
        f"{'Sharpe':>7} {'Max DD':>10} {'vs Base':>10} {'Mar PnL':>10}")
    out("-" * 107)
    out(f"{'BASELINE':<30} {baseline['trades']:>7} ${baseline['net_pnl']:>10,.2f} "
        f"{baseline['win_pct']:>6.1f}% {baseline['pf']:>5.2f} {baseline['sharpe']:>7.2f} "
        f"${baseline['max_dd']:>9,.2f} {'---':>10} ${march_base_pnl:>9,.2f}")

    winners = []
    if best_clb:
        label = f"CLB(N={best_clb[0]},M={best_clb[1]})"
        m = best_clb[2]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${best_clb[3]:>9,.2f}")
        winners.append((label, m, delta))

    if best_ddp:
        label = f"DDP(${best_ddp[0]:,})"
        m = best_ddp[1]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${best_ddp[2]:>9,.2f}")
        winners.append((label, m, delta))

    if best_mlc:
        label = f"MLC(${best_mlc[0]:,})"
        m = best_mlc[1]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${best_mlc[2]:>9,.2f}")
        winners.append((label, m, delta))

    if best_wrr:
        label = f"WRR(N={best_wrr[0]})"
        m = best_wrr[1]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${best_wrr[2]:>9,.2f}")
        winners.append((label, m, delta))

    if best_rs:
        label = f"RS(N={best_rs[0]})"
        m = best_rs[1]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${best_rs[3]:>9,.2f}")
        winners.append((label, m, delta))

    for cfg in combo_configs:
        label = f"Combo {cfg[0]}"
        m = cfg[1]
        delta = m['net_pnl'] - baseline['net_pnl']
        out(f"{label:<30} {m['trades']:>7} ${m['net_pnl']:>10,.2f} "
            f"{m['win_pct']:>6.1f}% {m['pf']:>5.2f} {m['sharpe']:>7.2f} "
            f"${m['max_dd']:>9,.2f} ${delta:>9,.2f} ${cfg[2]:>9,.2f}")

    out()

    # Write to file
    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
