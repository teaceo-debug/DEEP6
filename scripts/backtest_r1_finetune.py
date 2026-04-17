#!/usr/bin/env python3
"""
Round 1 Fine-Grained Parameter Sweep for VWAP Strategies on NQ 30-min bars.
Reads 1m bars from DuckDB, resamples to 30m per calendar-date session,
runs ChNavy6 / Ch2Navy6 / CHTrendNavy6 with parameter grids, writes results.
"""

import duckdb
import numpy as np
import pandas as pd
from itertools import product
from dataclasses import dataclass
from typing import List, Optional
import time

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
SLIPPAGE = SLIPPAGE_TICKS * TICK_SIZE
COMMISSION_RT = COMMISSION_PER_SIDE * 2  # round-trip

DB_PATH = "/Users/teaceo/DEEP6/data/backtests/replay_full_5sessions.duckdb"
OUT_PATH = "/Users/teaceo/DEEP6/scripts/results_r1_finetune.txt"

FLATTEN_HOUR = 16.0  # flatten at 16:00 ET


@dataclass
class Trade:
    date: str
    direction: str  # 'LONG' or 'SHORT'
    entry_price: float
    exit_price: float
    exit_reason: str  # 'TP', 'SL', 'FLATTEN', 'SESSION_END'
    entry_bar_idx: int
    exit_bar_idx: int
    pnl: float  # net of commissions and slippage


def ticks_to_price(ticks: int) -> float:
    return ticks * TICK_SIZE


def load_data() -> pd.DataFrame:
    """Load 1m bars, return DataFrame with bar_ts, open, high, low, close, volume."""
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute(
        "SELECT bar_ts, open, high, low, close, volume "
        "FROM backtest_bars WHERE tf='1m' ORDER BY bar_ts"
    ).fetchdf()
    con.close()
    df['bar_ts'] = pd.to_datetime(df['bar_ts'])
    return df


def resample_to_30m(df_1m: pd.DataFrame, date: str) -> pd.DataFrame:
    """Resample 1m bars for a single calendar date to 30m bars."""
    mask = df_1m['bar_ts'].dt.date.astype(str) == date
    day = df_1m[mask].copy()
    if day.empty:
        return pd.DataFrame()

    day = day.set_index('bar_ts')
    bars_30m = day.resample('30min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna(subset=['open'])
    bars_30m = bars_30m.reset_index()
    return bars_30m


def compute_vwap_series(bars: pd.DataFrame) -> np.ndarray:
    """Compute cumulative VWAP for the session. Returns array of VWAP values."""
    typical = (bars['high'].values + bars['low'].values + bars['close'].values) / 3.0
    vol = bars['volume'].values.astype(float)
    cum_tp_vol = np.cumsum(typical * vol)
    cum_vol = np.cumsum(vol)
    # Avoid division by zero
    cum_vol[cum_vol == 0] = 1e-9
    return cum_tp_vol / cum_vol


def simulate_exit(bars: pd.DataFrame, entry_idx: int, entry_price: float,
                  direction: str, sl_ticks: int, tp_ticks: int,
                  flatten_h: float) -> Trade:
    """Walk forward from entry_idx checking SL/TP on each bar's high/low."""
    sl_price_dist = ticks_to_price(sl_ticks)
    tp_price_dist = ticks_to_price(tp_ticks)

    if direction == 'LONG':
        sl_price = entry_price - sl_price_dist
        tp_price = entry_price + tp_price_dist
    else:
        sl_price = entry_price + sl_price_dist
        tp_price = entry_price - tp_price_dist

    date_str = str(bars.iloc[entry_idx]['bar_ts'].date())
    n = len(bars)

    for i in range(entry_idx, n):
        bar = bars.iloc[i]
        bar_hour = bar['bar_ts'].hour + bar['bar_ts'].minute / 60.0

        # Check flatten time
        if bar_hour >= flatten_h:
            exit_price = bar['close']
            gross = (exit_price - entry_price) if direction == 'LONG' else (entry_price - exit_price)
            pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
            return Trade(date_str, direction, entry_price, exit_price, 'FLATTEN', entry_idx, i, pnl)

        # Check SL/TP within bar
        if direction == 'LONG':
            # Check SL first (assume worst case: SL hit before TP if both possible)
            if bar['low'] <= sl_price:
                exit_price = sl_price
                gross = (exit_price - entry_price)
                pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
                return Trade(date_str, direction, entry_price, exit_price, 'SL', entry_idx, i, pnl)
            if bar['high'] >= tp_price:
                exit_price = tp_price
                gross = (exit_price - entry_price)
                pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
                return Trade(date_str, direction, entry_price, exit_price, 'TP', entry_idx, i, pnl)
        else:  # SHORT
            if bar['high'] >= sl_price:
                exit_price = sl_price
                gross = (entry_price - exit_price)
                pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
                return Trade(date_str, direction, entry_price, exit_price, 'SL', entry_idx, i, pnl)
            if bar['low'] <= tp_price:
                exit_price = tp_price
                gross = (entry_price - exit_price)
                pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
                return Trade(date_str, direction, entry_price, exit_price, 'TP', entry_idx, i, pnl)

    # Session end - exit at last bar close
    exit_price = bars.iloc[n - 1]['close']
    gross = (exit_price - entry_price) if direction == 'LONG' else (entry_price - exit_price)
    pnl = (gross / TICK_SIZE) * TICK_VALUE - COMMISSION_RT
    return Trade(date_str, direction, entry_price, exit_price, 'SESSION_END', entry_idx, n - 1, pnl)


# ── Strategy Implementations ──────────────────────────────────────────────

def run_chnavy6(session_bars: pd.DataFrame, sl: int, tp: int, bounce: int,
                start_h: float, end_h: float) -> List[Trade]:
    """ChNavy6: VWAP Bounce. OnBarClose logic, 1 trade/day."""
    trades = []
    vwap = compute_vwap_series(session_bars)
    n = len(session_bars)
    confirm = ticks_to_price(bounce)
    traded_today = False

    for i in range(1, n):
        if traded_today:
            break

        bar_hour = session_bars.iloc[i]['bar_ts'].hour + session_bars.iloc[i]['bar_ts'].minute / 60.0
        if bar_hour < start_h or bar_hour >= end_h:
            continue

        # Prior bar close vs prior VWAP
        prev_close = session_bars.iloc[i - 1]['close']
        prev_vwap = vwap[i - 1]
        cur_close = session_bars.iloc[i]['close']
        cur_vwap = vwap[i]

        was_below = prev_close < prev_vwap
        was_above = prev_close > prev_vwap

        # Long: was below VWAP, now close > VWAP by at least confirm
        if was_below and cur_close > cur_vwap and (cur_close - cur_vwap) >= confirm:
            entry_price = cur_close + SLIPPAGE  # enter at close (OnBarClose) + slippage
            trade = simulate_exit(session_bars, i + 1 if i + 1 < n else i, entry_price, 'LONG', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

        # Short: was above VWAP, now close < VWAP by at least confirm
        elif was_above and cur_close < cur_vwap and (cur_vwap - cur_close) >= confirm:
            entry_price = cur_close - SLIPPAGE  # enter at close - slippage for short
            trade = simulate_exit(session_bars, i + 1 if i + 1 < n else i, entry_price, 'SHORT', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

    return trades


def run_ch2navy6(session_bars: pd.DataFrame, sl: int, tp: int, bounce: int,
                 start_h: float, end_h: float) -> List[Trade]:
    """Ch2Navy6: VWAP Rejection using bar[2] and bar[1]. Enter at next bar open. 1 trade/day."""
    trades = []
    vwap = compute_vwap_series(session_bars)
    n = len(session_bars)
    confirm = ticks_to_price(bounce)
    traded_today = False

    for i in range(2, n):
        if traded_today:
            break

        # Entry bar is i (enter at open of bar i, setup from bars i-2 and i-1)
        bar_hour = session_bars.iloc[i]['bar_ts'].hour + session_bars.iloc[i]['bar_ts'].minute / 60.0
        if bar_hour < start_h or bar_hour >= end_h:
            continue

        bar2 = session_bars.iloc[i - 2]
        bar1 = session_bars.iloc[i - 1]
        vwap_prior = vwap[i - 1]  # VWAP computed from bar[1]

        # Long setup
        if (bar2['close'] < vwap_prior and
            bar1['low'] <= vwap_prior and
            bar1['close'] > vwap_prior and
            (bar1['close'] - vwap_prior) >= confirm):
            entry_price = session_bars.iloc[i]['open'] + SLIPPAGE
            trade = simulate_exit(session_bars, i, entry_price, 'LONG', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

        # Short setup
        elif (bar2['close'] > vwap_prior and
              bar1['high'] >= vwap_prior and
              bar1['close'] < vwap_prior and
              (vwap_prior - bar1['close']) >= confirm):
            entry_price = session_bars.iloc[i]['open'] - SLIPPAGE
            trade = simulate_exit(session_bars, i, entry_price, 'SHORT', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

    return trades


def run_chtrendnavy6(session_bars: pd.DataFrame, sl: int, tp: int,
                     slope_lb: int, pb_ticks: int,
                     start_h: float, end_h: float) -> List[Trade]:
    """CHTrendNavy6: Trend Pullback. VWAP slope + pullback band. 1 trade/day."""
    trades = []
    vwap = compute_vwap_series(session_bars)
    n = len(session_bars)
    band = ticks_to_price(pb_ticks)
    traded_today = False

    for i in range(slope_lb + 1, n):
        if traded_today:
            break

        bar_hour = session_bars.iloc[i]['bar_ts'].hour + session_bars.iloc[i]['bar_ts'].minute / 60.0
        if bar_hour < start_h or bar_hour >= end_h:
            continue

        slope = vwap[i - 1] - vwap[i - 1 - slope_lb]
        bar1 = session_bars.iloc[i - 1]
        cur_vwap = vwap[i - 1]

        # Long: slope > 0, bar1 close > vwap, bar1 low <= vwap + band
        if slope > 0 and bar1['close'] > cur_vwap and bar1['low'] <= cur_vwap + band:
            entry_price = session_bars.iloc[i]['open'] + SLIPPAGE
            trade = simulate_exit(session_bars, i, entry_price, 'LONG', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

        # Short: slope < 0, bar1 close < vwap, bar1 high >= vwap - band
        elif slope < 0 and bar1['close'] < cur_vwap and bar1['high'] >= cur_vwap - band:
            entry_price = session_bars.iloc[i]['open'] - SLIPPAGE
            trade = simulate_exit(session_bars, i, entry_price, 'SHORT', sl, tp, FLATTEN_HOUR)
            trades.append(trade)
            traded_today = True

    return trades


# ── Metrics ────────────────────────────────────────────────────────────────

def compute_metrics(trades: List[Trade]):
    if not trades:
        return {'count': 0, 'net_pnl': 0, 'win_rate': 0, 'pf': 0, 'max_dd': 0}

    pnls = [t.pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))

    # Max drawdown from equity curve
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    max_dd = float(np.max(dd)) if len(dd) > 0 else 0

    return {
        'count': len(trades),
        'net_pnl': sum(pnls),
        'win_rate': wins / len(trades) * 100 if trades else 0,
        'pf': gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0),
        'max_dd': max_dd
    }


# ── Main Sweep ─────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print("Loading data...")
    df_1m = load_data()

    # Get unique dates
    dates = sorted(df_1m['bar_ts'].dt.date.astype(str).unique())
    print(f"Dates: {dates}")

    # Resample to 30m per date
    print("Resampling to 30m bars...")
    sessions_30m = {}
    for d in dates:
        bars = resample_to_30m(df_1m, d)
        if not bars.empty:
            sessions_30m[d] = bars
            print(f"  {d}: {len(bars)} bars, {bars.iloc[0]['bar_ts']} → {bars.iloc[-1]['bar_ts']}")

    # ── Parameter grids ──
    # ChNavy6 and Ch2Navy6
    sl_grid_12 = [160, 180, 200, 220, 240, 260]
    tp_grid_12 = [360, 400, 440, 480, 520, 560]
    bounce_grid = [10, 15, 20, 25, 30, 40]
    start_grid = [9.0, 9.5, 10.0]
    end_grid = [13.0, 13.5, 14.0, 14.5, 15.0]

    # CHTrendNavy6
    sl_grid_3 = [160, 200, 240, 280, 320]
    tp_grid_3 = [160, 180, 200, 220, 240, 280]
    slope_lb_grid = [2, 3, 4, 5, 6]
    pb_grid = [10, 15, 20, 30, 40, 60]

    results = {'ChNavy6': [], 'Ch2Navy6': [], 'CHTrendNavy6': []}

    # ── ChNavy6 sweep ──
    combos_12 = list(product(sl_grid_12, tp_grid_12, bounce_grid, start_grid, end_grid))
    print(f"\nChNavy6: {len(combos_12)} combos x {len(sessions_30m)} sessions...")
    for idx, (sl, tp, bc, sh, eh) in enumerate(combos_12):
        all_trades = []
        for d, bars in sessions_30m.items():
            all_trades.extend(run_chnavy6(bars, sl, tp, bc, sh, eh))
        m = compute_metrics(all_trades)
        results['ChNavy6'].append({
            'sl': sl, 'tp': tp, 'bounce': bc, 'start_h': sh, 'end_h': eh,
            **m, 'trades': all_trades
        })
        if (idx + 1) % 500 == 0:
            print(f"  {idx+1}/{len(combos_12)}")

    # ── Ch2Navy6 sweep ──
    print(f"\nCh2Navy6: {len(combos_12)} combos x {len(sessions_30m)} sessions...")
    for idx, (sl, tp, bc, sh, eh) in enumerate(combos_12):
        all_trades = []
        for d, bars in sessions_30m.items():
            all_trades.extend(run_ch2navy6(bars, sl, tp, bc, sh, eh))
        m = compute_metrics(all_trades)
        results['Ch2Navy6'].append({
            'sl': sl, 'tp': tp, 'bounce': bc, 'start_h': sh, 'end_h': eh,
            **m, 'trades': all_trades
        })
        if (idx + 1) % 500 == 0:
            print(f"  {idx+1}/{len(combos_12)}")

    # ── CHTrendNavy6 sweep ──
    combos_3 = list(product(sl_grid_3, tp_grid_3, slope_lb_grid, pb_grid, start_grid, end_grid))
    print(f"\nCHTrendNavy6: {len(combos_3)} combos x {len(sessions_30m)} sessions...")
    for idx, (sl, tp, slb, pb, sh, eh) in enumerate(combos_3):
        all_trades = []
        for d, bars in sessions_30m.items():
            all_trades.extend(run_chtrendnavy6(bars, sl, tp, slb, pb, sh, eh))
        m = compute_metrics(all_trades)
        results['CHTrendNavy6'].append({
            'sl': sl, 'tp': tp, 'slope_lb': slb, 'pb_ticks': pb,
            'start_h': sh, 'end_h': eh,
            **m, 'trades': all_trades
        })
        if (idx + 1) % 1000 == 0:
            print(f"  {idx+1}/{len(combos_3)}")

    # ── Write results ──
    print(f"\nWriting results to {OUT_PATH}...")
    with open(OUT_PATH, 'w') as f:
        f.write("=" * 100 + "\n")
        f.write("DEEP6 Round 1 Fine-Grained Parameter Sweep Results\n")
        f.write(f"Date range: {dates[0]} to {dates[-1]}\n")
        f.write(f"Sessions: {len(sessions_30m)}\n")
        f.write(f"Timeframe: 30-minute bars (resampled from 1m)\n")
        f.write(f"Constants: TICK_SIZE={TICK_SIZE}, TICK_VALUE={TICK_VALUE}, "
                f"COMMISSION_RT=${COMMISSION_RT:.2f}, SLIPPAGE={SLIPPAGE_TICKS}t\n")
        f.write("=" * 100 + "\n\n")

        for strat_name in ['ChNavy6', 'Ch2Navy6', 'CHTrendNavy6']:
            f.write("=" * 100 + "\n")
            f.write(f"STRATEGY: {strat_name}\n")
            f.write("=" * 100 + "\n\n")

            # Sort by net PnL descending
            sorted_results = sorted(results[strat_name], key=lambda x: x['net_pnl'], reverse=True)

            # Top 20
            f.write(f"TOP 20 CONFIGURATIONS (by Net PnL)\n")
            f.write("-" * 100 + "\n")

            if strat_name == 'CHTrendNavy6':
                f.write(f"{'Rank':>4} | {'SL':>4} | {'TP':>4} | {'SlopeLB':>7} | {'PB':>4} | "
                        f"{'Start':>5} | {'End':>5} | {'#Trades':>7} | {'Net PnL':>10} | "
                        f"{'WR%':>6} | {'PF':>6} | {'MaxDD':>8}\n")
                f.write("-" * 100 + "\n")
                for rank, r in enumerate(sorted_results[:20], 1):
                    f.write(f"{rank:>4} | {r['sl']:>4} | {r['tp']:>4} | {r['slope_lb']:>7} | "
                            f"{r['pb_ticks']:>4} | {r['start_h']:>5.1f} | {r['end_h']:>5.1f} | "
                            f"{r['count']:>7} | ${r['net_pnl']:>9.2f} | "
                            f"{r['win_rate']:>5.1f}% | {r['pf']:>6.2f} | ${r['max_dd']:>7.2f}\n")
            else:
                f.write(f"{'Rank':>4} | {'SL':>4} | {'TP':>4} | {'Bounce':>6} | "
                        f"{'Start':>5} | {'End':>5} | {'#Trades':>7} | {'Net PnL':>10} | "
                        f"{'WR%':>6} | {'PF':>6} | {'MaxDD':>8}\n")
                f.write("-" * 100 + "\n")
                for rank, r in enumerate(sorted_results[:20], 1):
                    f.write(f"{rank:>4} | {r['sl']:>4} | {r['tp']:>4} | {r['bounce']:>6} | "
                            f"{r['start_h']:>5.1f} | {r['end_h']:>5.1f} | "
                            f"{r['count']:>7} | ${r['net_pnl']:>9.2f} | "
                            f"{r['win_rate']:>5.1f}% | {r['pf']:>6.2f} | ${r['max_dd']:>7.2f}\n")

            # Trade-by-trade for #1 config
            f.write(f"\n{'='*80}\n")
            f.write(f"TRADE-BY-TRADE DETAIL: #{strat_name} #1 Config\n")
            if strat_name == 'CHTrendNavy6':
                best = sorted_results[0]
                f.write(f"Params: SL={best['sl']}t, TP={best['tp']}t, "
                        f"SlopeLB={best['slope_lb']}, PB={best['pb_ticks']}t, "
                        f"Start={best['start_h']}, End={best['end_h']}\n")
            else:
                best = sorted_results[0]
                f.write(f"Params: SL={best['sl']}t, TP={best['tp']}t, "
                        f"Bounce={best['bounce']}t, "
                        f"Start={best['start_h']}, End={best['end_h']}\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'#':>3} | {'Date':>12} | {'Dir':>5} | {'Entry':>10} | {'Exit':>10} | "
                    f"{'Reason':>10} | {'PnL':>10}\n")
            f.write("-" * 80 + "\n")
            for tidx, t in enumerate(best['trades'], 1):
                f.write(f"{tidx:>3} | {t.date:>12} | {t.direction:>5} | "
                        f"{t.entry_price:>10.2f} | {t.exit_price:>10.2f} | "
                        f"{t.exit_reason:>10} | ${t.pnl:>9.2f}\n")
            f.write(f"\nTotal PnL: ${best['net_pnl']:.2f}  |  "
                    f"Win Rate: {best['win_rate']:.1f}%  |  "
                    f"Profit Factor: {best['pf']:.2f}  |  "
                    f"Max DD: ${best['max_dd']:.2f}\n")
            f.write("\n\n")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s. Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
