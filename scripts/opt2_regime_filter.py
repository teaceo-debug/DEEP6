#!/usr/bin/env python3
"""
opt2_regime_filter.py — Regime Filter Optimization for ChNavy6 VWAP Bounce Strategy
Tests 5 independent filters + best combinations to skip chop days.
"""

import pandas as pd
import numpy as np
from itertools import product
import warnings
warnings.filterwarnings('ignore')

# ── Constants ──────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
POINT_VALUE = TICK_VALUE / TICK_SIZE  # $20/point
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
SLIPPAGE_PTS = SLIPPAGE_TICKS * TICK_SIZE  # 0.25 pts
SL_TICKS = 160
TP_TICKS = 560
SL_PTS = SL_TICKS * TICK_SIZE  # 40 pts
TP_PTS = TP_TICKS * TICK_SIZE  # 140 pts
ENTRY_THRESHOLD_TICKS = 20
ENTRY_THRESHOLD_PTS = ENTRY_THRESHOLD_TICKS * TICK_SIZE  # 5 pts

TRADE_START_H = 9.5   # 9:30 ET
TRADE_END_H = 14.5    # 14:30 ET
FLATTEN_H = 16.0      # 16:00 ET

CSV_PATH = '/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv'
OUT_PATH = '/Users/teaceo/DEEP6/scripts/opt2_regime_filter.txt'

# ── Load & Prepare Data ───────────────────────────────────────────
def load_data():
    df = pd.read_csv(CSV_PATH, parse_dates=['ts_event'])
    df['ts_event'] = df['ts_event'].dt.tz_convert('US/Eastern')
    df = df.sort_values('ts_event').reset_index(drop=True)
    df['date'] = df['ts_event'].dt.date
    df['hour'] = df['ts_event'].dt.hour + df['ts_event'].dt.minute / 60.0
    return df

def resample_30m(df):
    """Resample 1m bars to 30m bars per calendar date in US/Eastern."""
    # Filter to RTH only (9:30-16:00)
    rth = df[(df['hour'] >= 9.5) & (df['hour'] < 16.0)].copy()

    # Create 30m groups
    rth['bar_group'] = rth['ts_event'].dt.floor('30min')

    bars_30m = rth.groupby(['date', 'bar_group']).agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
        volume=('volume', 'sum'),
        ts=('ts_event', 'first')
    ).reset_index()

    bars_30m['hour'] = bars_30m['ts'].dt.hour + bars_30m['ts'].dt.minute / 60.0
    bars_30m = bars_30m.sort_values(['date', 'bar_group']).reset_index(drop=True)

    return bars_30m

# ── VWAP Computation ──────────────────────────────────────────────
def compute_vwap_per_day(bars):
    """Compute cumulative VWAP per day using typical price * volume."""
    bars = bars.copy()
    bars['typical'] = (bars['high'] + bars['low'] + bars['close']) / 3.0
    bars['tp_vol'] = bars['typical'] * bars['volume']
    bars['cum_tp_vol'] = bars.groupby('date')['tp_vol'].cumsum()
    bars['cum_vol'] = bars.groupby('date')['volume'].cumsum()
    bars['vwap'] = bars['cum_tp_vol'] / bars['cum_vol']
    return bars

# ── Strategy Simulation ──────────────────────────────────────────
def run_strategy(bars, skip_dates=None):
    """
    ChNavy6 VWAP Bounce strategy on 30m bars.
    Returns list of trade dicts.
    """
    if skip_dates is None:
        skip_dates = set()

    bars = compute_vwap_per_day(bars)
    trades = []

    for date, day_bars in bars.groupby('date'):
        if date in skip_dates:
            continue

        day_bars = day_bars.sort_values('bar_group').reset_index(drop=True)

        wasBelowVWAP = False
        wasAboveVWAP = False
        traded_today = False

        for i in range(1, len(day_bars)):
            if traded_today:
                break

            bar = day_bars.iloc[i]
            prev = day_bars.iloc[i-1]

            h = bar['hour']
            if h < TRADE_START_H or h >= TRADE_END_H:
                continue

            # Track prior bar relationship to VWAP
            if prev['close'] < prev['vwap']:
                wasBelowVWAP = True
            if prev['close'] > prev['vwap']:
                wasAboveVWAP = True

            close = bar['close']
            vwap = bar['vwap']

            # Long signal: was below VWAP, now close > VWAP by threshold
            if wasBelowVWAP and close > vwap and (close - vwap) >= ENTRY_THRESHOLD_PTS:
                entry = close + SLIPPAGE_PTS
                sl = entry - SL_PTS
                tp = entry + TP_PTS
                trade = simulate_trade(date, entry, sl, tp, 1, day_bars, i, bars)
                trades.append(trade)
                traded_today = True
            # Short signal
            elif wasAboveVWAP and close < vwap and (vwap - close) >= ENTRY_THRESHOLD_PTS:
                entry = close - SLIPPAGE_PTS
                sl = entry + SL_PTS
                tp = entry - TP_PTS
                trade = simulate_trade(date, entry, sl, tp, -1, day_bars, i, bars)
                trades.append(trade)
                traded_today = True

    return trades

def simulate_trade(date, entry, sl, tp, direction, day_bars, entry_idx, all_bars):
    """Simulate trade from entry bar forward through the day."""
    # Check subsequent bars for SL/TP/flatten
    for j in range(entry_idx + 1, len(day_bars)):
        bar = day_bars.iloc[j]
        h = bar['hour']

        if direction == 1:  # Long
            # Check SL
            if bar['low'] <= sl:
                pnl_pts = sl - entry
                return make_trade(date, entry, sl, direction, pnl_pts, 'SL')
            # Check TP
            if bar['high'] >= tp:
                pnl_pts = tp - entry
                return make_trade(date, entry, tp, direction, pnl_pts, 'TP')
        else:  # Short
            if bar['high'] >= sl:
                pnl_pts = entry - sl
                return make_trade(date, entry, sl, direction, pnl_pts, 'SL')
            if bar['low'] <= tp:
                pnl_pts = entry - tp
                return make_trade(date, entry, tp, direction, pnl_pts, 'TP')

        # Flatten at 16:00
        if h >= FLATTEN_H - 0.5:  # Last bar before flatten
            exit_price = bar['close']
            if direction == 1:
                pnl_pts = exit_price - entry
            else:
                pnl_pts = entry - exit_price
            return make_trade(date, entry, exit_price, direction, pnl_pts, 'FLAT')

    # If we reach end of day without exit, flatten at last bar
    last_bar = day_bars.iloc[-1]
    exit_price = last_bar['close']
    if direction == 1:
        pnl_pts = exit_price - entry
    else:
        pnl_pts = entry - exit_price
    return make_trade(date, entry, exit_price, direction, pnl_pts, 'FLAT')

def make_trade(date, entry, exit_price, direction, pnl_pts, exit_type):
    pnl_dollar = pnl_pts * POINT_VALUE - 2 * COMMISSION_PER_SIDE
    return {
        'date': date,
        'direction': 'LONG' if direction == 1 else 'SHORT',
        'entry': entry,
        'exit': exit_price,
        'pnl_pts': pnl_pts,
        'pnl': pnl_dollar,
        'exit_type': exit_type,
    }

# ── Metrics ───────────────────────────────────────────────────────
def compute_metrics(trades, total_days, skip_count):
    if not trades:
        return {
            'trades': 0, 'days_skipped': skip_count,
            'net_pnl': 0, 'win_pct': 0, 'pf': 0,
            'sharpe': 0, 'max_dd': 0,
            'march_trades': 0, 'march_pnl': 0, 'march_win_pct': 0,
        }

    tdf = pd.DataFrame(trades)
    wins = tdf[tdf['pnl'] > 0]
    losses = tdf[tdf['pnl'] <= 0]
    gross_win = wins['pnl'].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses['pnl'].sum()) if len(losses) > 0 else 0

    net = tdf['pnl'].sum()
    wr = len(wins) / len(tdf) * 100
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')

    # Daily Sharpe (annualized)
    daily_pnl = tdf.groupby('date')['pnl'].sum()
    if daily_pnl.std() > 0:
        sharpe = (daily_pnl.mean() / daily_pnl.std()) * np.sqrt(252)
    else:
        sharpe = 0

    # Max drawdown
    cum = tdf['pnl'].cumsum()
    peak = cum.cummax()
    dd = (cum - peak).min()

    # March stats
    march_trades = [t for t in trades if hasattr(t['date'], 'month') and t['date'].month == 3]
    march_tdf = pd.DataFrame(march_trades) if march_trades else pd.DataFrame()
    march_pnl = march_tdf['pnl'].sum() if len(march_tdf) > 0 else 0
    march_wins = len(march_tdf[march_tdf['pnl'] > 0]) if len(march_tdf) > 0 else 0
    march_wr = (march_wins / len(march_tdf) * 100) if len(march_tdf) > 0 else 0

    return {
        'trades': len(tdf),
        'days_skipped': skip_count,
        'net_pnl': net,
        'win_pct': wr,
        'pf': pf,
        'sharpe': sharpe,
        'max_dd': dd,
        'march_trades': len(march_tdf),
        'march_pnl': march_pnl,
        'march_win_pct': march_wr,
    }

# ── Filter Implementations ────────────────────────────────────────
def compute_first_hour_range(bars):
    """Range of first 2x 30m bars (9:30-10:30) per day."""
    first_hour = bars[(bars['hour'] >= 9.5) & (bars['hour'] < 10.5)]
    return first_hour.groupby('date').agg(
        fh_high=('high', 'max'),
        fh_low=('low', 'min'),
        fh_vol=('volume', 'sum'),
    ).assign(fh_range=lambda x: x['fh_high'] - x['fh_low'])

def compute_prior_day_atr(bars):
    """ATR from 30m bars per day, shifted to represent prior day's ATR."""
    day_stats = []
    for date, day_bars in bars.groupby('date'):
        day_bars = day_bars.sort_values('bar_group')
        highs = day_bars['high'].values
        lows = day_bars['low'].values
        closes = day_bars['close'].values

        trs = []
        for i in range(len(day_bars)):
            if i == 0:
                tr = highs[i] - lows[i]
            else:
                tr = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i-1]),
                         abs(lows[i] - closes[i-1]))
            trs.append(tr)

        day_stats.append({
            'date': date,
            'atr': np.mean(trs),
            'day_close': closes[-1],
            'day_open': day_bars['open'].iloc[0],
        })

    ds = pd.DataFrame(day_stats).sort_values('date')
    ds['prior_atr'] = ds['atr'].shift(1)
    ds['prior_close'] = ds['day_close'].shift(1)
    ds['gap'] = abs(ds['day_open'] - ds['prior_close'])
    return ds.set_index('date')

def compute_vwap_slope(bars):
    """VWAP slope over 3 bars at each bar. Return max abs slope in trading window per day."""
    bars_v = compute_vwap_per_day(bars)
    slopes = {}
    for date, day_bars in bars_v.groupby('date'):
        day_bars = day_bars.sort_values('bar_group').reset_index(drop=True)
        trading_bars = day_bars[(day_bars['hour'] >= 9.5) & (day_bars['hour'] < 11.0)]
        if len(trading_bars) < 3:
            slopes[date] = 0
            continue
        # Compute slope = (vwap[i] - vwap[i-2]) / 2 for first few bars
        vwaps = trading_bars['vwap'].values
        s = []
        for i in range(2, len(vwaps)):
            s.append(abs(vwaps[i] - vwaps[i-2]) / 2.0)
        slopes[date] = max(s) if s else 0
    return pd.Series(slopes, name='vwap_slope')

def compute_first_hour_volume(bars):
    """First-hour volume per day + 20-day rolling average."""
    fh = compute_first_hour_range(bars)
    fh['fh_vol_ma20'] = fh['fh_vol'].rolling(20, min_periods=5).mean()
    fh['fh_vol_ratio'] = fh['fh_vol'] / fh['fh_vol_ma20']
    return fh

# ── Main ──────────────────────────────────────────────────────────
def main():
    print("Loading data...")
    df = load_data()
    bars = resample_30m(df)
    all_dates = sorted(bars['date'].unique())
    total_days = len(all_dates)

    print(f"Total trading days: {total_days}")
    print(f"30m bars: {len(bars)}")

    # Precompute filter features
    print("Computing filter features...")
    fh_range = compute_first_hour_range(bars)
    day_stats = compute_prior_day_atr(bars)
    vwap_slope = compute_vwap_slope(bars)
    fh_volume = compute_first_hour_volume(bars)

    # ── Baseline ──
    print("Running baseline...")
    baseline_trades = run_strategy(bars)
    baseline = compute_metrics(baseline_trades, total_days, 0)

    results = []

    # ── Filter 1: First-Hour Range ──
    print("Testing Filter 1: First-Hour Range...")
    for thresh in [20, 30, 40, 50, 60, 80]:
        skip = set(fh_range[fh_range['fh_range'] < thresh].index)
        trades = run_strategy(bars, skip)
        m = compute_metrics(trades, total_days, len(skip))
        m['filter'] = f'FH_Range<{thresh}'
        results.append(m)

    # ── Filter 2: Prior-Day ATR ──
    print("Testing Filter 2: Prior-Day ATR...")
    for low_t in [20, 30, 40, 50]:
        for high_t in [100, 120, 150, None]:
            skip = set()
            for date in all_dates:
                if date in day_stats.index:
                    atr = day_stats.loc[date, 'prior_atr']
                    if pd.isna(atr):
                        continue
                    if atr < low_t:
                        skip.add(date)
                    if high_t is not None and atr > high_t:
                        skip.add(date)

            trades = run_strategy(bars, skip)
            m = compute_metrics(trades, total_days, len(skip))
            ht = high_t if high_t else 'none'
            m['filter'] = f'ATR<{low_t}_>{ht}'
            results.append(m)

    # ── Filter 3: Opening Gap ──
    print("Testing Filter 3: Opening Gap...")
    for thresh in [30, 50, 80, 100]:
        # Skip if gap > threshold
        skip = set()
        for date in all_dates:
            if date in day_stats.index:
                gap = day_stats.loc[date, 'gap']
                if pd.isna(gap):
                    continue
                if gap > thresh:
                    skip.add(date)
        trades = run_strategy(bars, skip)
        m = compute_metrics(trades, total_days, len(skip))
        m['filter'] = f'Gap>{thresh}_skip'
        results.append(m)

    for thresh in [30, 50, 80, 100]:
        # Only trade gap days
        skip = set()
        for date in all_dates:
            if date in day_stats.index:
                gap = day_stats.loc[date, 'gap']
                if pd.isna(gap):
                    skip.add(date)
                    continue
                if gap <= thresh:
                    skip.add(date)
        trades = run_strategy(bars, skip)
        m = compute_metrics(trades, total_days, len(skip))
        m['filter'] = f'Gap>{thresh}_only'
        results.append(m)

    # ── Filter 4: VWAP Slope Flatness ──
    print("Testing Filter 4: VWAP Slope Flatness...")
    for thresh in [1, 2, 3, 5, 8]:
        skip = set()
        for date in all_dates:
            if date in vwap_slope.index:
                sl = vwap_slope[date]
                if sl < thresh:
                    skip.add(date)
        trades = run_strategy(bars, skip)
        m = compute_metrics(trades, total_days, len(skip))
        m['filter'] = f'VWAPslope<{thresh}'
        results.append(m)

    # ── Filter 5: Volume Filter ──
    print("Testing Filter 5: First-Hour Volume...")
    for pctl in [25, 40, 50]:
        skip = set()
        for date in all_dates:
            if date in fh_volume.index:
                ratio = fh_volume.loc[date, 'fh_vol_ratio']
                if pd.isna(ratio):
                    continue
                # Below Nth percentile means ratio < pctl/100 roughly
                # More precisely: skip if vol < rolling pctl of 20-day
                vol = fh_volume.loc[date, 'fh_vol']
                ma = fh_volume.loc[date, 'fh_vol_ma20']
                if pd.isna(ma):
                    continue
                if vol < ma * (pctl / 100.0):
                    skip.add(date)
        trades = run_strategy(bars, skip)
        m = compute_metrics(trades, total_days, len(skip))
        m['filter'] = f'Vol<P{pctl}'
        results.append(m)

    # ── Find top filters ──
    rdf = pd.DataFrame(results)
    # Rank by net_pnl, then by march improvement
    rdf['pnl_improvement'] = rdf['net_pnl'] - baseline['net_pnl']
    rdf['march_improvement'] = rdf['march_pnl'] - baseline['march_pnl']
    rdf = rdf.sort_values('net_pnl', ascending=False)

    # ── Combination Tests ──
    print("Testing filter combinations...")
    # Pick top 3-4 individual filters by PnL
    top_filters = rdf.head(6)

    # Manually test promising combinations based on results
    combo_results = []

    # Combination helper
    def combo_skip(filter_list):
        """Union of skip dates from multiple filter configs."""
        skip = set()
        for f_name, f_skip in filter_list:
            skip |= f_skip
        return skip

    # Pre-build skip sets for top filter params
    skip_sets = {}

    # FH Range filters
    for thresh in [30, 40, 50, 60]:
        key = f'FH_Range<{thresh}'
        skip_sets[key] = set(fh_range[fh_range['fh_range'] < thresh].index)

    # ATR filters
    for low_t in [30, 40]:
        for high_t in [120, 150, None]:
            skip = set()
            for date in all_dates:
                if date in day_stats.index:
                    atr = day_stats.loc[date, 'prior_atr']
                    if pd.isna(atr):
                        continue
                    if atr < low_t:
                        skip.add(date)
                    if high_t and atr > high_t:
                        skip.add(date)
            ht = high_t if high_t else 'none'
            skip_sets[f'ATR<{low_t}_>{ht}'] = skip

    # Gap filters
    for thresh in [50, 80]:
        skip = set()
        for date in all_dates:
            if date in day_stats.index:
                gap = day_stats.loc[date, 'gap']
                if pd.isna(gap):
                    continue
                if gap > thresh:
                    skip.add(date)
        skip_sets[f'Gap>{thresh}_skip'] = skip

    # VWAP slope
    for thresh in [2, 3, 5]:
        skip = set()
        for date in all_dates:
            if date in vwap_slope.index:
                sl = vwap_slope[date]
                if sl < thresh:
                    skip.add(date)
        skip_sets[f'VWAPslope<{thresh}'] = skip

    # Volume
    for pctl in [25, 40]:
        skip = set()
        for date in all_dates:
            if date in fh_volume.index:
                vol = fh_volume.loc[date, 'fh_vol']
                ma = fh_volume.loc[date, 'fh_vol_ma20']
                if pd.isna(ma):
                    continue
                if vol < ma * (pctl / 100.0):
                    skip.add(date)
        skip_sets[f'Vol<P{pctl}'] = skip

    # Test all 2-filter combos from a curated list
    combo_keys = list(skip_sets.keys())
    tested_combos = set()

    for i in range(len(combo_keys)):
        for j in range(i+1, len(combo_keys)):
            k1, k2 = combo_keys[i], combo_keys[j]
            # Skip same-category combos
            cat1 = k1.split('<')[0].split('>')[0]
            cat2 = k2.split('<')[0].split('>')[0]
            if cat1 == cat2:
                continue

            combined_skip = skip_sets[k1] | skip_sets[k2]
            if len(combined_skip) > total_days * 0.6:
                continue  # Skip if too many days filtered

            trades = run_strategy(bars, combined_skip)
            m = compute_metrics(trades, total_days, len(combined_skip))
            m['filter'] = f'{k1} + {k2}'
            combo_results.append(m)

    # Test best 3-filter combos
    # Get top 5 2-filter combos
    cdf = pd.DataFrame(combo_results)
    if len(cdf) > 0:
        cdf = cdf.sort_values('net_pnl', ascending=False)

        # Add a 3rd filter to top combos
        triple_results = []
        for _, row in cdf.head(5).iterrows():
            parts = row['filter'].split(' + ')
            for k3 in combo_keys:
                cat3 = k3.split('<')[0].split('>')[0]
                cats = [p.split('<')[0].split('>')[0] for p in parts]
                if cat3 in cats:
                    continue

                combined_skip = set()
                for p in parts:
                    if p in skip_sets:
                        combined_skip |= skip_sets[p]
                combined_skip |= skip_sets[k3]

                if len(combined_skip) > total_days * 0.65:
                    continue

                trades = run_strategy(bars, combined_skip)
                m = compute_metrics(trades, total_days, len(combined_skip))
                m['filter'] = f'{row["filter"]} + {k3}'
                triple_results.append(m)

        combo_results.extend(triple_results)

    combo_df = pd.DataFrame(combo_results)
    if len(combo_df) > 0:
        combo_df['pnl_improvement'] = combo_df['net_pnl'] - baseline['net_pnl']
        combo_df['march_improvement'] = combo_df['march_pnl'] - baseline['march_pnl']
        combo_df = combo_df.sort_values('net_pnl', ascending=False)

    # ── Output ────────────────────────────────────────────────────
    lines = []
    def w(s=''):
        lines.append(s)
        print(s)

    w("=" * 100)
    w("OPT2 REGIME FILTER ANALYSIS — ChNavy6 VWAP Bounce on 30m NQ")
    w(f"Data: {total_days} trading days, Jan 2 – Apr 10, 2026")
    w("=" * 100)

    w()
    w("─" * 100)
    w("BASELINE (no filters)")
    w("─" * 100)
    w(f"  Trades: {baseline['trades']}")
    w(f"  Net PnL: ${baseline['net_pnl']:,.2f}")
    w(f"  Win%: {baseline['win_pct']:.1f}%")
    w(f"  PF: {baseline['pf']:.2f}")
    w(f"  Sharpe: {baseline['sharpe']:.2f}")
    w(f"  Max DD: ${baseline['max_dd']:,.2f}")
    w(f"  MARCH — Trades: {baseline['march_trades']}, PnL: ${baseline['march_pnl']:,.2f}, Win%: {baseline['march_win_pct']:.1f}%")

    # Individual filter results
    w()
    w("=" * 100)
    w("INDIVIDUAL FILTER RESULTS")
    w("=" * 100)

    header = f"{'Filter':<25} {'Skip':>4} {'Trds':>4} {'Net PnL':>10} {'Win%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10} {'MarTr':>5} {'MarPnL':>10} {'MarW%':>6}"
    w(header)
    w("-" * len(header))

    for _, r in rdf.iterrows():
        pf_str = f"{r['pf']:.2f}" if r['pf'] != float('inf') else 'inf'
        w(f"{r['filter']:<25} {r['days_skipped']:>4} {r['trades']:>4} ${r['net_pnl']:>9,.2f} {r['win_pct']:>5.1f}% {pf_str:>6} {r['sharpe']:>7.2f} ${r['max_dd']:>9,.2f} {r['march_trades']:>5} ${r['march_pnl']:>9,.2f} {r['march_win_pct']:>5.1f}%")

    # Combo results
    if len(combo_df) > 0:
        w()
        w("=" * 100)
        w("COMBINATION FILTER RESULTS (top 30)")
        w("=" * 100)

        header2 = f"{'Filter':<55} {'Skip':>4} {'Trds':>4} {'Net PnL':>10} {'Win%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10} {'MarTr':>5} {'MarPnL':>10} {'MarW%':>6}"
        w(header2)
        w("-" * len(header2))

        for _, r in combo_df.head(30).iterrows():
            pf_str = f"{r['pf']:.2f}" if r['pf'] != float('inf') else 'inf'
            w(f"{r['filter']:<55} {r['days_skipped']:>4} {r['trades']:>4} ${r['net_pnl']:>9,.2f} {r['win_pct']:>5.1f}% {pf_str:>6} {r['sharpe']:>7.2f} ${r['max_dd']:>9,.2f} {r['march_trades']:>5} ${r['march_pnl']:>9,.2f} {r['march_win_pct']:>5.1f}%")

    # Summary
    w()
    w("=" * 100)
    w("TOP 5 OVERALL (by Net PnL)")
    w("=" * 100)

    all_results = pd.concat([rdf, combo_df], ignore_index=True) if len(combo_df) > 0 else rdf
    all_results = all_results.sort_values('net_pnl', ascending=False)

    for rank, (_, r) in enumerate(all_results.head(5).iterrows(), 1):
        pf_str = f"{r['pf']:.2f}" if r['pf'] != float('inf') else 'inf'
        w(f"  #{rank}: {r['filter']}")
        w(f"       Skip {r['days_skipped']} days | {r['trades']} trades | ${r['net_pnl']:,.2f} PnL | {r['win_pct']:.1f}% WR | PF {pf_str} | Sharpe {r['sharpe']:.2f} | DD ${r['max_dd']:,.2f}")
        w(f"       March: {r['march_trades']} trades, ${r['march_pnl']:,.2f}, {r['march_win_pct']:.1f}% WR")
        imp = r['net_pnl'] - baseline['net_pnl']
        w(f"       vs Baseline: {'+' if imp >= 0 else ''}${imp:,.2f}")
        w()

    w("=" * 100)
    w("TOP 5 BY MARCH IMPROVEMENT")
    w("=" * 100)
    all_results['march_improvement'] = all_results['march_pnl'] - baseline['march_pnl']
    march_best = all_results.sort_values('march_improvement', ascending=False)

    for rank, (_, r) in enumerate(march_best.head(5).iterrows(), 1):
        pf_str = f"{r['pf']:.2f}" if r['pf'] != float('inf') else 'inf'
        w(f"  #{rank}: {r['filter']}")
        w(f"       Skip {r['days_skipped']} days | {r['trades']} trades | ${r['net_pnl']:,.2f} PnL | {r['win_pct']:.1f}% WR | PF {pf_str}")
        w(f"       March: {r['march_trades']} trades, ${r['march_pnl']:,.2f}, {r['march_win_pct']:.1f}% WR (improved ${r['march_improvement']:+,.2f})")
        w()

    # Baseline trade list for March
    w()
    w("=" * 100)
    w("MARCH TRADE DETAIL (Baseline)")
    w("=" * 100)
    march_baseline = [t for t in baseline_trades if hasattr(t['date'], 'month') and t['date'].month == 3]
    for t in sorted(march_baseline, key=lambda x: x['date']):
        w(f"  {t['date']} {t['direction']:5s} entry={t['entry']:.2f} exit={t['exit']:.2f} {t['exit_type']:4s} PnL=${t['pnl']:+,.2f}")

    # Write output
    with open(OUT_PATH, 'w') as f:
        f.write('\n'.join(lines))

    print(f"\nResults written to {OUT_PATH}")

if __name__ == '__main__':
    main()
