#!/usr/bin/env python3
"""
Round 2: Walk-Forward & Per-Session Analysis
Tests ChNavy6, Ch2Navy6, CHTrendNavy6 VWAP strategies across 3 RTH sessions.
"""

import duckdb
import pandas as pd
import numpy as np
from itertools import product
from datetime import datetime, time
import os

# ── Constants ──
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
TOTAL_COMMISSION = COMMISSION_PER_SIDE * 2  # round trip
SLIPPAGE_COST = SLIPPAGE_TICKS * TICK_VALUE * 2  # entry + exit

DB_PATH = "/Users/teaceo/DEEP6/data/backtests/replay_full_5sessions.duckdb"
OUTPUT_PATH = "/Users/teaceo/DEEP6/scripts/results_r2_walkforward.txt"

SESSION_DATES = ["2026-04-08", "2026-04-09", "2026-04-10"]

# ── Parameter ranges ──
SL_TICKS = [120, 160, 200, 240, 280, 320]
TP_TICKS = [160, 200, 280, 360, 480]
BOUNCE_CONFIRMS = [10, 20, 30, 40]
SLOPE_LBS = [2, 3, 4, 5]
PULLBACK_TICKS = [10, 20, 40, 60]
START_TIMES = [9.5, 10.0]
END_TIMES = [14.0, 14.5, 15.0]


def load_data():
    """Load 1m bars from DuckDB."""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("""
        SELECT bar_ts, open, high, low, close, volume
        FROM backtest_bars
        WHERE tf = '1m'
        ORDER BY bar_ts
    """).fetchdf()
    con.close()
    df['bar_ts'] = pd.to_datetime(df['bar_ts'])
    return df


def resample_30m(df_1m):
    """Resample 1m bars to 30m bars."""
    df = df_1m.set_index('bar_ts')
    resampled = df.resample('30min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()
    return resampled.reset_index()


def get_session_bars(df_1m, date_str):
    """Extract RTH bars (9:00-16:00) for a calendar date, resample to 30m."""
    date = pd.Timestamp(date_str)
    rth_start = date + pd.Timedelta(hours=9)
    rth_end = date + pd.Timedelta(hours=16)
    mask = (df_1m['bar_ts'] >= rth_start) & (df_1m['bar_ts'] < rth_end)
    session_1m = df_1m[mask].copy()
    if len(session_1m) == 0:
        return None, None
    # Also keep 1m bars for exit simulation
    bars_30m = resample_30m(session_1m)
    return bars_30m, session_1m


def compute_vwap(bars):
    """Compute running VWAP from bar data. Returns array of VWAP values."""
    typical = (bars['high'].values + bars['low'].values + bars['close'].values) / 3.0
    vol = bars['volume'].values.astype(float)
    cum_tp_vol = np.cumsum(typical * vol)
    cum_vol = np.cumsum(vol)
    vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, typical)
    return vwap


def time_from_hours(h):
    """Convert decimal hours to hour,minute tuple."""
    hours = int(h)
    minutes = int((h - hours) * 60)
    return hours, minutes


def bar_time_hours(ts):
    """Convert timestamp to decimal hours."""
    return ts.hour + ts.minute / 60.0


def simulate_exit(bars_1m, entry_time, entry_price, direction, sl_ticks, tp_ticks, date_str):
    """Walk forward through 1m bars to simulate SL/TP/EOD exit."""
    sl_pts = sl_ticks * TICK_SIZE
    tp_pts = tp_ticks * TICK_SIZE

    if direction == 'long':
        sl_price = entry_price - sl_pts
        tp_price = entry_price + tp_pts
    else:
        sl_price = entry_price + sl_pts
        tp_price = entry_price - tp_pts

    date = pd.Timestamp(date_str)
    eod = date + pd.Timedelta(hours=16)

    mask = (bars_1m['bar_ts'] > entry_time) & (bars_1m['bar_ts'] <= eod)
    future_bars = bars_1m[mask]

    for _, bar in future_bars.iterrows():
        if direction == 'long':
            # Check SL first (adverse)
            if bar['low'] <= sl_price:
                return sl_price, 'SL'
            if bar['high'] >= tp_price:
                return tp_price, 'TP'
        else:
            if bar['high'] >= sl_price:
                return sl_price, 'SL'
            if bar['low'] <= tp_price:
                return tp_price, 'TP'

    # EOD flatten at last bar close
    if len(future_bars) > 0:
        return future_bars.iloc[-1]['close'], 'EOD'
    return entry_price, 'EOD'


def calc_pnl(entry_price, exit_price, direction):
    """Calculate P&L in dollars."""
    if direction == 'long':
        raw_pnl = (exit_price - entry_price) / TICK_SIZE * TICK_VALUE
    else:
        raw_pnl = (entry_price - exit_price) / TICK_SIZE * TICK_VALUE
    return raw_pnl - TOTAL_COMMISSION - SLIPPAGE_COST


# ── Strategy implementations ──

def run_chnavy6(bars_30m, bars_1m, date_str, sl, tp, confirm, start_h, end_h):
    """ChNavy6: OnBarClose cross with bounce confirm."""
    vwap = compute_vwap(bars_30m)
    traded = False

    for i in range(1, len(bars_30m)):
        if traded:
            break
        bt = bar_time_hours(bars_30m.iloc[i]['bar_ts'])
        if bt < start_h or bt >= end_h:
            continue

        prev_close = bars_30m.iloc[i-1]['close']
        prev_vwap = vwap[i-1]
        cur_close = bars_30m.iloc[i]['close']
        cur_vwap = vwap[i]
        confirm_pts = confirm * TICK_SIZE

        was_below = prev_close < prev_vwap
        was_above = prev_close > prev_vwap

        direction = None
        if was_below and cur_close > cur_vwap and (cur_close - cur_vwap) >= confirm_pts:
            direction = 'long'
        elif was_above and cur_close < cur_vwap and (cur_vwap - cur_close) >= confirm_pts:
            direction = 'short'

        if direction:
            entry_price = cur_close  # OnBarClose entry
            entry_time = bars_30m.iloc[i]['bar_ts']
            # Apply slippage
            if direction == 'long':
                entry_price += SLIPPAGE_TICKS * TICK_SIZE
            else:
                entry_price -= SLIPPAGE_TICKS * TICK_SIZE

            exit_price, exit_type = simulate_exit(bars_1m, entry_time, entry_price, direction, sl, tp, date_str)
            pnl = calc_pnl(entry_price, exit_price, direction)
            traded = True
            return pnl, direction, exit_type

    return 0.0, None, None  # no trade


def run_ch2navy6(bars_30m, bars_1m, date_str, sl, tp, confirm, start_h, end_h):
    """Ch2Navy6: bar[2]/bar[1] cross, enter at bar[0] open."""
    vwap = compute_vwap(bars_30m)
    traded = False

    for i in range(2, len(bars_30m)):
        if traded:
            break
        bt = bar_time_hours(bars_30m.iloc[i]['bar_ts'])
        if bt < start_h or bt >= end_h:
            continue

        bar2 = bars_30m.iloc[i-2]
        bar1 = bars_30m.iloc[i-1]
        vwap_prior = vwap[i-1]
        confirm_pts = confirm * TICK_SIZE

        direction = None
        # Long: bar2.close < vwapPrior AND bar1.low <= vwapPrior AND bar1.close > vwapPrior AND confirm
        if (bar2['close'] < vwap_prior and
            bar1['low'] <= vwap_prior and
            bar1['close'] > vwap_prior and
            (bar1['close'] - vwap_prior) >= confirm_pts):
            direction = 'long'
        # Short: bar2.close > vwapPrior AND bar1.high >= vwapPrior AND bar1.close < vwapPrior AND confirm
        elif (bar2['close'] > vwap_prior and
              bar1['high'] >= vwap_prior and
              bar1['close'] < vwap_prior and
              (vwap_prior - bar1['close']) >= confirm_pts):
            direction = 'short'

        if direction:
            entry_price = bars_30m.iloc[i]['open']
            entry_time = bars_30m.iloc[i]['bar_ts']
            if direction == 'long':
                entry_price += SLIPPAGE_TICKS * TICK_SIZE
            else:
                entry_price -= SLIPPAGE_TICKS * TICK_SIZE

            exit_price, exit_type = simulate_exit(bars_1m, entry_time, entry_price, direction, sl, tp, date_str)
            pnl = calc_pnl(entry_price, exit_price, direction)
            traded = True
            return pnl, direction, exit_type

    return 0.0, None, None


def run_chtrendnavy6(bars_30m, bars_1m, date_str, sl, tp, slope_lb, pullback_ticks, start_h, end_h):
    """CHTrendNavy6: VWAP slope + pullback entry."""
    vwap = compute_vwap(bars_30m)
    traded = False
    band = pullback_ticks * TICK_SIZE

    for i in range(slope_lb + 1, len(bars_30m)):
        if traded:
            break
        bt = bar_time_hours(bars_30m.iloc[i]['bar_ts'])
        if bt < start_h or bt >= end_h:
            continue

        slope = vwap[i-1] - vwap[i-1 - slope_lb]
        bar1 = bars_30m.iloc[i-1]
        cur_vwap = vwap[i-1]

        direction = None
        # Long: slope>0, bar1.close > vwap, bar1.low <= vwap+band
        if slope > 0 and bar1['close'] > cur_vwap and bar1['low'] <= cur_vwap + band:
            direction = 'long'
        # Short: slope<0, bar1.close < vwap, bar1.high >= vwap-band
        elif slope < 0 and bar1['close'] < cur_vwap and bar1['high'] >= cur_vwap - band:
            direction = 'short'

        if direction:
            entry_price = bars_30m.iloc[i]['open']
            entry_time = bars_30m.iloc[i]['bar_ts']
            if direction == 'long':
                entry_price += SLIPPAGE_TICKS * TICK_SIZE
            else:
                entry_price -= SLIPPAGE_TICKS * TICK_SIZE

            exit_price, exit_type = simulate_exit(bars_1m, entry_time, entry_price, direction, sl, tp, date_str)
            pnl = calc_pnl(entry_price, exit_price, direction)
            traded = True
            return pnl, direction, exit_type

    return 0.0, None, None


def main():
    print("Loading data...")
    df_1m = load_data()

    # Prepare session data
    sessions = {}
    for d in SESSION_DATES:
        bars_30m, bars_1m_session = get_session_bars(df_1m, d)
        if bars_30m is not None and len(bars_30m) > 0:
            sessions[d] = (bars_30m, bars_1m_session)
            print(f"  {d}: {len(bars_30m)} 30m bars, {len(bars_1m_session)} 1m bars")
        else:
            print(f"  {d}: NO DATA")

    active_dates = sorted(sessions.keys())
    n_sessions = len(active_dates)
    print(f"\nActive sessions: {active_dates}")

    results = {'ChNavy6': [], 'Ch2Navy6': [], 'CHTrendNavy6': []}

    # ── ChNavy6 sweep ──
    print("\nRunning ChNavy6 sweep...")
    combos = list(product(SL_TICKS, TP_TICKS, BOUNCE_CONFIRMS, START_TIMES, END_TIMES))
    print(f"  {len(combos)} parameter combos x {n_sessions} sessions")
    for sl, tp, confirm, st, et in combos:
        session_pnls = {}
        for d in active_dates:
            bars_30m, bars_1m_s = sessions[d]
            pnl, direction, exit_type = run_chnavy6(bars_30m, bars_1m_s, d, sl, tp, confirm, st, et)
            session_pnls[d] = pnl
        results['ChNavy6'].append({
            'params': f"SL={sl} TP={tp} BC={confirm} ST={st} ET={et}",
            'sl': sl, 'tp': tp, 'confirm': confirm, 'st': st, 'et': et,
            'session_pnls': session_pnls,
            'total_pnl': sum(session_pnls.values()),
            'avg_pnl': sum(session_pnls.values()) / n_sessions,
            'profitable_sessions': sum(1 for v in session_pnls.values() if v > 0),
            'robustness': sum(1 for v in session_pnls.values() if v > 0) / n_sessions,
        })

    # ── Ch2Navy6 sweep ──
    print("Running Ch2Navy6 sweep...")
    combos = list(product(SL_TICKS, TP_TICKS, BOUNCE_CONFIRMS, START_TIMES, END_TIMES))
    print(f"  {len(combos)} parameter combos x {n_sessions} sessions")
    for sl, tp, confirm, st, et in combos:
        session_pnls = {}
        for d in active_dates:
            bars_30m, bars_1m_s = sessions[d]
            pnl, direction, exit_type = run_ch2navy6(bars_30m, bars_1m_s, d, sl, tp, confirm, st, et)
            session_pnls[d] = pnl
        results['Ch2Navy6'].append({
            'params': f"SL={sl} TP={tp} BC={confirm} ST={st} ET={et}",
            'sl': sl, 'tp': tp, 'confirm': confirm, 'st': st, 'et': et,
            'session_pnls': session_pnls,
            'total_pnl': sum(session_pnls.values()),
            'avg_pnl': sum(session_pnls.values()) / n_sessions,
            'profitable_sessions': sum(1 for v in session_pnls.values() if v > 0),
            'robustness': sum(1 for v in session_pnls.values() if v > 0) / n_sessions,
        })

    # ── CHTrendNavy6 sweep ──
    print("Running CHTrendNavy6 sweep...")
    combos = list(product(SL_TICKS, TP_TICKS, SLOPE_LBS, PULLBACK_TICKS, START_TIMES, END_TIMES))
    print(f"  {len(combos)} parameter combos x {n_sessions} sessions")
    for sl, tp, slb, pb, st, et in combos:
        session_pnls = {}
        for d in active_dates:
            bars_30m, bars_1m_s = sessions[d]
            pnl, direction, exit_type = run_chtrendnavy6(bars_30m, bars_1m_s, d, sl, tp, slb, pb, st, et)
            session_pnls[d] = pnl
        results['CHTrendNavy6'].append({
            'params': f"SL={sl} TP={tp} SLB={slb} PB={pb} ST={st} ET={et}",
            'sl': sl, 'tp': tp, 'slope_lb': slb, 'pullback': pb, 'st': st, 'et': et,
            'session_pnls': session_pnls,
            'total_pnl': sum(session_pnls.values()),
            'avg_pnl': sum(session_pnls.values()) / n_sessions,
            'profitable_sessions': sum(1 for v in session_pnls.values() if v > 0),
            'robustness': sum(1 for v in session_pnls.values() if v > 0) / n_sessions,
        })

    # ── Write results ──
    print("\nWriting results...")
    lines = []
    lines.append("=" * 100)
    lines.append("DEEP6 Round 2: Walk-Forward & Per-Session Analysis")
    lines.append(f"Sessions: {', '.join(active_dates)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 100)

    for strat_name in ['ChNavy6', 'Ch2Navy6', 'CHTrendNavy6']:
        strat_results = results[strat_name]
        lines.append("")
        lines.append("=" * 100)
        lines.append(f"STRATEGY: {strat_name}")
        lines.append("=" * 100)

        # Count by robustness tier
        r3 = [r for r in strat_results if r['profitable_sessions'] == 3]
        r2 = [r for r in strat_results if r['profitable_sessions'] == 2]
        r1 = [r for r in strat_results if r['profitable_sessions'] == 1]
        r0 = [r for r in strat_results if r['profitable_sessions'] == 0]
        total = len(strat_results)

        lines.append(f"\nRobustness Distribution ({total} total configs):")
        lines.append(f"  3/3 sessions profitable: {len(r3)} configs ({100*len(r3)/total:.1f}%)")
        lines.append(f"  2/3 sessions profitable: {len(r2)} configs ({100*len(r2)/total:.1f}%)")
        lines.append(f"  1/3 sessions profitable: {len(r1)} configs ({100*len(r1)/total:.1f}%)")
        lines.append(f"  0/3 sessions profitable: {len(r0)} configs ({100*len(r0)/total:.1f}%)")

        # ── 3/3 robust configs ──
        lines.append(f"\n--- 3/3 ROBUST CONFIGS (sorted by avg P&L) ---")
        if r3:
            r3_sorted = sorted(r3, key=lambda x: x['avg_pnl'], reverse=True)
            lines.append(f"{'Params':<50} {'Avg PnL':>10} {'Total':>10}  " +
                         "  ".join(f"{d:>12}" for d in active_dates))
            lines.append("-" * (80 + 14 * n_sessions))
            for r in r3_sorted[:20]:
                sess_str = "  ".join(f"${r['session_pnls'][d]:>10.2f}" for d in active_dates)
                lines.append(f"{r['params']:<50} ${r['avg_pnl']:>9.2f} ${r['total_pnl']:>9.2f}  {sess_str}")
        else:
            lines.append("  (none)")

        # ── 2/3 robust configs ──
        lines.append(f"\n--- 2/3 ROBUST CONFIGS (sorted by avg P&L, top 20) ---")
        if r2:
            r2_sorted = sorted(r2, key=lambda x: x['avg_pnl'], reverse=True)
            lines.append(f"{'Params':<50} {'Avg PnL':>10} {'Total':>10}  " +
                         "  ".join(f"{d:>12}" for d in active_dates))
            lines.append("-" * (80 + 14 * n_sessions))
            for r in r2_sorted[:20]:
                sess_str = "  ".join(f"${r['session_pnls'][d]:>10.2f}" for d in active_dates)
                lines.append(f"{r['params']:<50} ${r['avg_pnl']:>9.2f} ${r['total_pnl']:>9.2f}  {sess_str}")
        else:
            lines.append("  (none)")

        # ── Most Robust Config ──
        # Best avg PnL among configs profitable on >= 2/3 sessions
        robust_pool = [r for r in strat_results if r['profitable_sessions'] >= 2]
        if robust_pool:
            best = max(robust_pool, key=lambda x: x['avg_pnl'])
            lines.append(f"\n>>> MOST ROBUST CONFIG: {best['params']}")
            lines.append(f"    Avg PnL: ${best['avg_pnl']:.2f}  |  Total: ${best['total_pnl']:.2f}  |  "
                         f"Robustness: {best['profitable_sessions']}/{n_sessions}")
            for d in active_dates:
                lines.append(f"    {d}: ${best['session_pnls'][d]:.2f}")
        else:
            lines.append(f"\n>>> NO ROBUST CONFIG FOUND (no config profitable on >= 2 sessions)")

        # ── Top 5 by total PnL with session breakdown ──
        lines.append(f"\n--- TOP 5 BY TOTAL P&L (session breakdown) ---")
        all_sorted = sorted(strat_results, key=lambda x: x['total_pnl'], reverse=True)
        for rank, r in enumerate(all_sorted[:5], 1):
            lines.append(f"\n  #{rank}: {r['params']}")
            lines.append(f"      Total: ${r['total_pnl']:.2f}  |  Avg: ${r['avg_pnl']:.2f}  |  "
                         f"Robustness: {r['profitable_sessions']}/{n_sessions}")
            for d in active_dates:
                pnl = r['session_pnls'][d]
                flag = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT")
                lines.append(f"      {d}: ${pnl:>10.2f}  [{flag}]")

        # ── Best config per session ──
        lines.append(f"\n--- BEST CONFIG PER SESSION ---")
        for d in active_dates:
            best_for_session = max(strat_results, key=lambda x: x['session_pnls'][d])
            pnl = best_for_session['session_pnls'][d]
            lines.append(f"  {d}: {best_for_session['params']}  ->  ${pnl:.2f}")

    # ── Cross-strategy summary ──
    lines.append("\n" + "=" * 100)
    lines.append("CROSS-STRATEGY SUMMARY")
    lines.append("=" * 100)

    for strat_name in ['ChNavy6', 'Ch2Navy6', 'CHTrendNavy6']:
        strat_results = results[strat_name]
        robust_pool = [r for r in strat_results if r['profitable_sessions'] >= 2]
        if robust_pool:
            best = max(robust_pool, key=lambda x: x['avg_pnl'])
            lines.append(f"\n{strat_name}:")
            lines.append(f"  Best robust config: {best['params']}")
            lines.append(f"  Avg PnL: ${best['avg_pnl']:.2f}  |  Robustness: {best['profitable_sessions']}/{n_sessions}")
            for d in active_dates:
                lines.append(f"    {d}: ${best['session_pnls'][d]:.2f}")
        else:
            lines.append(f"\n{strat_name}: No config profitable on >= 2/3 sessions")

    # ── Overfitting warnings ──
    lines.append("\n" + "-" * 100)
    lines.append("OVERFITTING ANALYSIS")
    lines.append("-" * 100)
    for strat_name in ['ChNavy6', 'Ch2Navy6', 'CHTrendNavy6']:
        strat_results = results[strat_name]
        best_total = max(strat_results, key=lambda x: x['total_pnl'])
        r3_count = sum(1 for r in strat_results if r['profitable_sessions'] == 3)
        total_configs = len(strat_results)
        lines.append(f"\n{strat_name}:")
        lines.append(f"  Best total P&L config robustness: {best_total['profitable_sessions']}/{n_sessions}")
        if best_total['profitable_sessions'] < n_sessions:
            lines.append(f"  WARNING: Best total P&L config is NOT profitable on all sessions - possible overfit")
        lines.append(f"  {r3_count}/{total_configs} configs ({100*r3_count/total_configs:.1f}%) profitable on all 3 sessions")

    output = "\n".join(lines)
    with open(OUTPUT_PATH, 'w') as f:
        f.write(output)
    print(f"\nResults written to {OUTPUT_PATH}")
    print(f"\nPreview (first 60 lines):")
    for line in lines[:60]:
        print(line)


if __name__ == "__main__":
    main()
