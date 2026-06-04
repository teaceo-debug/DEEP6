#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = ROOT / 'data/backtests/signal_events.csv'
BARS_PATH = ROOT / 'data/backtests/nq_1yr_1m.csv'
OUT_DIR = ROOT / 'data/backtests/analysis/absorption_trade_management'

TICK_SIZE = 0.25
MAX_HORIZON = 30
FIXED_SL = [5, 10, 15, 20, 30, 50, 75, 100]
FIXED_TP = [5, 10, 15, 20, 30, 50, 75, 100, 150, 200]
ATR_MULTS = [0.5, 1.0, 1.5, 2.0]
TIME_EXITS = [1, 2, 3, 5, 10, 15, 30]
TRAIL_X = [10, 20, 30]
TRAIL_Y = [10, 15, 20]
R_CHOICES = [1.0, 1.5, 2.0, 3.0]


def load_bars() -> pd.DataFrame:
    bars = pd.read_csv(
        BARS_PATH,
        usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume'],
        low_memory=False,
    )
    bars['bar_ts'] = pd.to_datetime(bars['ts_event'], utc=True).dt.tz_convert('America/New_York')
    bars = bars.sort_values('bar_ts').reset_index(drop=True)
    prev_close = bars['close'].shift(1)
    tr = pd.concat(
        [
            bars['high'] - bars['low'],
            (bars['high'] - prev_close).abs(),
            (bars['low'] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    bars['atr20'] = tr.rolling(20, min_periods=20).mean()
    bars['bar_idx'] = np.arange(len(bars))
    return bars


def load_absorption_events(bars: pd.DataFrame) -> pd.DataFrame:
    cols = [
        'session_date', 'bar_ts', 'bar_index', 'global_index', 'signal_id', 'category',
        'direction', 'strength', 'score_final', 'score_tier', 'bar_open', 'bar_high',
        'bar_low', 'bar_close', 'bar_delta', 'bar_volume'
    ]
    ev = pd.read_csv(EVENTS_PATH, usecols=cols, low_memory=False)
    ev = ev[ev['category'] == 'absorption'].copy()
    ev['bar_ts'] = pd.to_datetime(ev['bar_ts'], utc=True).dt.tz_convert('America/New_York')
    ev['direction'] = pd.to_numeric(ev['direction'], errors='coerce')
    ev = ev.merge(
        bars[['bar_ts', 'bar_idx', 'close', 'atr20']],
        on='bar_ts',
        how='left',
        validate='many_to_one',
    )
    missing = int(ev['bar_idx'].isna().sum())
    if missing:
        raise RuntimeError(f'{missing} absorption events could not be aligned to nq_1yr_1m.csv')
    close_mismatch = (ev['bar_close'].sub(ev['close']).abs() > 1e-9).sum()
    if close_mismatch:
        raise RuntimeError(f'{close_mismatch} aligned events have bar_close mismatches')
    ev['bar_idx'] = ev['bar_idx'].astype(int)
    return ev.drop(columns=['close'])


def build_future_matrices(events: pd.DataFrame, bars: pd.DataFrame) -> dict[str, np.ndarray]:
    n = len(events)
    highs = np.full((n, MAX_HORIZON), np.nan, dtype=np.float64)
    lows = np.full((n, MAX_HORIZON), np.nan, dtype=np.float64)
    closes = np.full((n, MAX_HORIZON), np.nan, dtype=np.float64)
    for i, bar_idx in enumerate(events['bar_idx'].to_numpy()):
        future = bars.iloc[bar_idx + 1: bar_idx + 1 + MAX_HORIZON]
        m = len(future)
        if m:
            highs[i, :m] = future['high'].to_numpy(dtype=np.float64)
            lows[i, :m] = future['low'].to_numpy(dtype=np.float64)
            closes[i, :m] = future['close'].to_numpy(dtype=np.float64)
    return {'highs': highs, 'lows': lows, 'closes': closes}


def max_consecutive_losses(pnls: np.ndarray) -> int:
    streak = 0
    worst = 0
    for pnl in pnls:
        if pnl <= 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return int(worst)


def compute_metrics(pnls: list[float]) -> dict[str, Any]:
    arr = np.asarray(pnls, dtype=np.float64)
    wins = arr[arr > 0]
    losses = arr[arr <= 0]
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    if gross_loss == 0:
        pf = float('inf') if gross_profit > 0 else 0.0
    else:
        pf = gross_profit / gross_loss
    std = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    sharpe = float(arr.mean() / std) if std > 0 else 0.0
    return {
        'trade_count': int(len(arr)),
        'win_rate': float((arr > 0).mean()),
        'profit_factor': float(pf),
        'expectancy_ticks': float(arr.mean()),
        'median_ticks': float(np.median(arr)),
        'net_ticks': float(arr.sum()),
        'sharpe': sharpe,
        'max_consecutive_losses': max_consecutive_losses(arr),
    }


def simulate_fixed(indices: np.ndarray, events: pd.DataFrame, mats: dict[str, np.ndarray], sl_ticks: int, tp_ticks: int) -> dict[str, Any]:
    highs = mats['highs']
    lows = mats['lows']
    closes = mats['closes']
    sl_dist = sl_ticks * TICK_SIZE
    tp_dist = tp_ticks * TICK_SIZE
    pnls: list[float] = []

    for i in indices:
        entry = float(events.at[i, 'bar_close'])
        direction = int(events.at[i, 'direction'])
        stop = entry - sl_dist if direction == 1 else entry + sl_dist
        target = entry + tp_dist if direction == 1 else entry - tp_dist
        exit_price = float(closes[i, 29])

        for j in range(MAX_HORIZON):
            hi = highs[i, j]
            lo = lows[i, j]
            if np.isnan(hi) or np.isnan(lo):
                break
            if direction == 1:
                hit_stop = lo <= stop
                hit_target = hi >= target
                if hit_stop and hit_target:
                    exit_price = stop
                    break
                if hit_stop:
                    exit_price = stop
                    break
                if hit_target:
                    exit_price = target
                    break
            else:
                hit_stop = hi >= stop
                hit_target = lo <= target
                if hit_stop and hit_target:
                    exit_price = stop
                    break
                if hit_stop:
                    exit_price = stop
                    break
                if hit_target:
                    exit_price = target
                    break

        pnl_ticks = direction * (exit_price - entry) / TICK_SIZE
        pnls.append(float(pnl_ticks))

    out = compute_metrics(pnls)
    out.update({'sl_ticks': sl_ticks, 'tp_ticks': tp_ticks, 'r_multiple': tp_ticks / sl_ticks})
    return out


def simulate_atr(indices: np.ndarray, events: pd.DataFrame, mats: dict[str, np.ndarray], sl_mult: float, tp_mult: float) -> dict[str, Any]:
    highs = mats['highs']
    lows = mats['lows']
    closes = mats['closes']
    pnls: list[float] = []
    sl_ticks_used: list[int] = []
    tp_ticks_used: list[int] = []

    for i in indices:
        atr = float(events.at[i, 'atr20'])
        sl_ticks = max(1, int(round((atr * sl_mult) / TICK_SIZE)))
        tp_ticks = max(1, int(round((atr * tp_mult) / TICK_SIZE)))
        sl_dist = sl_ticks * TICK_SIZE
        tp_dist = tp_ticks * TICK_SIZE
        sl_ticks_used.append(sl_ticks)
        tp_ticks_used.append(tp_ticks)

        entry = float(events.at[i, 'bar_close'])
        direction = int(events.at[i, 'direction'])
        stop = entry - sl_dist if direction == 1 else entry + sl_dist
        target = entry + tp_dist if direction == 1 else entry - tp_dist
        exit_price = float(closes[i, 29])

        for j in range(MAX_HORIZON):
            hi = highs[i, j]
            lo = lows[i, j]
            if np.isnan(hi) or np.isnan(lo):
                break
            if direction == 1:
                hit_stop = lo <= stop
                hit_target = hi >= target
                if hit_stop and hit_target:
                    exit_price = stop
                    break
                if hit_stop:
                    exit_price = stop
                    break
                if hit_target:
                    exit_price = target
                    break
            else:
                hit_stop = hi >= stop
                hit_target = lo <= target
                if hit_stop and hit_target:
                    exit_price = stop
                    break
                if hit_stop:
                    exit_price = stop
                    break
                if hit_target:
                    exit_price = target
                    break

        pnl_ticks = direction * (exit_price - entry) / TICK_SIZE
        pnls.append(float(pnl_ticks))

    out = compute_metrics(pnls)
    out.update({
        'sl_mult': sl_mult,
        'tp_mult': tp_mult,
        'avg_sl_ticks': float(np.mean(sl_ticks_used)) if sl_ticks_used else np.nan,
        'avg_tp_ticks': float(np.mean(tp_ticks_used)) if tp_ticks_used else np.nan,
        'r_multiple': tp_mult / sl_mult,
    })
    return out


def simulate_time_exit(indices: np.ndarray, events: pd.DataFrame, mats: dict[str, np.ndarray], n_bars: int) -> dict[str, Any]:
    closes = mats['closes']
    pnls: list[float] = []
    bar_ix = n_bars - 1
    for i in indices:
        entry = float(events.at[i, 'bar_close'])
        direction = int(events.at[i, 'direction'])
        exit_price = float(closes[i, bar_ix])
        pnl_ticks = direction * (exit_price - entry) / TICK_SIZE
        pnls.append(float(pnl_ticks))
    out = compute_metrics(pnls)
    out.update({'n_bars': n_bars})
    return out


def simulate_trailing(indices: np.ndarray, events: pd.DataFrame, mats: dict[str, np.ndarray], trigger_ticks: int, trail_ticks: int) -> dict[str, Any]:
    highs = mats['highs']
    lows = mats['lows']
    closes = mats['closes']
    trigger_dist = trigger_ticks * TICK_SIZE
    trail_dist = trail_ticks * TICK_SIZE
    pnls: list[float] = []

    for i in indices:
        entry = float(events.at[i, 'bar_close'])
        direction = int(events.at[i, 'direction'])
        stop = entry - trail_dist if direction == 1 else entry + trail_dist
        armed = False
        peak = entry
        trough = entry
        exit_price = float(closes[i, 29])

        for j in range(MAX_HORIZON):
            hi = highs[i, j]
            lo = lows[i, j]
            if np.isnan(hi) or np.isnan(lo):
                break
            if direction == 1:
                if lo <= stop:
                    exit_price = stop
                    break
                peak = max(peak, hi)
                if not armed and peak - entry >= trigger_dist:
                    armed = True
                    stop = max(stop, entry)
                if armed:
                    stop = max(stop, peak - trail_dist)
            else:
                if hi >= stop:
                    exit_price = stop
                    break
                trough = min(trough, lo)
                if not armed and entry - trough >= trigger_dist:
                    armed = True
                    stop = min(stop, entry)
                if armed:
                    stop = min(stop, trough + trail_dist)

        pnl_ticks = direction * (exit_price - entry) / TICK_SIZE
        pnls.append(float(pnl_ticks))

    out = compute_metrics(pnls)
    out.update({'trigger_ticks': trigger_ticks, 'trail_ticks': trail_ticks})
    return out


def pareto_frontier(df: pd.DataFrame) -> pd.DataFrame:
    best_by_n = (
        df.sort_values(['trade_count', 'profit_factor', 'expectancy_ticks'], ascending=[True, False, False])
          .groupby('trade_count', as_index=False)
          .head(1)
          .sort_values('trade_count')
    )
    frontier_rows = []
    running_pf = -np.inf
    for _, row in best_by_n.iterrows():
        pf = row['profit_factor']
        if pf > running_pf:
            frontier_rows.append(row)
            running_pf = pf
    return pd.DataFrame(frontier_rows)


def pick_best(df: pd.DataFrame, primary: str = 'expectancy_ticks') -> pd.Series:
    qualified = df[df['profit_factor'] >= 1.0]
    target = qualified if not qualified.empty else df
    sort_cols = [primary, 'profit_factor', 'win_rate', 'trade_count']
    return target.sort_values(sort_cols, ascending=[False, False, False, False]).iloc[0]


def pick_best_ratio(fixed_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in R_CHOICES:
        subset = fixed_df[np.isclose(fixed_df['r_multiple'], r)]
        if subset.empty:
            continue
        best = pick_best(subset, primary='expectancy_ticks')
        row = best.to_dict()
        row['ratio_choice'] = r
        rows.append(row)
    return pd.DataFrame(rows).sort_values('ratio_choice') if rows else pd.DataFrame()


def run_subset(name: str, mask: np.ndarray, events: pd.DataFrame, mats: dict[str, np.ndarray], out_dir: Path) -> dict[str, Any]:
    subset_dir = out_dir / name
    subset_dir.mkdir(parents=True, exist_ok=True)

    valid_30 = mask & ~np.isnan(mats['closes'][:, 29])
    valid_atr = valid_30 & events['atr20'].notna().to_numpy()
    subset_n = int(mask.sum())
    subset_n_30 = int(valid_30.sum())
    subset_n_atr = int(valid_atr.sum())

    fixed_rows = [simulate_fixed(np.flatnonzero(valid_30), events, mats, sl, tp) for sl in FIXED_SL for tp in FIXED_TP]
    fixed_df = pd.DataFrame(fixed_rows).sort_values(['profit_factor', 'expectancy_ticks'], ascending=[False, False])
    fixed_df.to_csv(subset_dir / 'fixed_bracket_sweep.csv', index=False)
    frontier_df = pareto_frontier(fixed_df)
    frontier_df.to_csv(subset_dir / 'fixed_pareto_frontier.csv', index=False)

    atr_rows = [simulate_atr(np.flatnonzero(valid_atr), events, mats, slm, tpm) for slm in ATR_MULTS for tpm in ATR_MULTS]
    atr_df = pd.DataFrame(atr_rows).sort_values(['profit_factor', 'expectancy_ticks'], ascending=[False, False])
    atr_df.to_csv(subset_dir / 'atr_scaled_sweep.csv', index=False)

    time_rows = []
    for n_bars in TIME_EXITS:
        valid_n = mask & ~np.isnan(mats['closes'][:, n_bars - 1])
        time_rows.append(simulate_time_exit(np.flatnonzero(valid_n), events, mats, n_bars))
    time_df = pd.DataFrame(time_rows).sort_values(['sharpe', 'expectancy_ticks'], ascending=[False, False])
    time_df.to_csv(subset_dir / 'time_exit_sweep.csv', index=False)

    trail_rows = [simulate_trailing(np.flatnonzero(valid_30), events, mats, x, y) for x in TRAIL_X for y in TRAIL_Y]
    trail_df = pd.DataFrame(trail_rows).sort_values(['profit_factor', 'expectancy_ticks'], ascending=[False, False])
    trail_df.to_csv(subset_dir / 'trailing_stop_sweep.csv', index=False)

    ratio_df = pick_best_ratio(fixed_df)
    ratio_df.to_csv(subset_dir / 'r_multiple_summary.csv', index=False)

    best_fixed_pf = fixed_df.iloc[0]
    best_fixed_exp = pick_best(fixed_df, primary='expectancy_ticks')
    best_atr = pick_best(atr_df, primary='expectancy_ticks')
    best_time = pick_best(time_df, primary='sharpe')
    best_trail = pick_best(trail_df, primary='expectancy_ticks')

    family_rows = pd.DataFrame([
        {'family': 'fixed', **best_fixed_exp.to_dict()},
        {'family': 'atr', **best_atr.to_dict()},
        {'family': 'time', **best_time.to_dict()},
        {'family': 'trailing', **best_trail.to_dict()},
    ])
    family_rows.to_csv(subset_dir / 'best_by_family.csv', index=False)
    overall = pick_best(family_rows, primary='expectancy_ticks')

    summary = {
        'subset': name,
        'signals': subset_n,
        'signals_with_30b_path': subset_n_30,
        'signals_with_atr': subset_n_atr,
        'best_fixed_pf': best_fixed_pf.to_dict(),
        'best_fixed_expectancy': best_fixed_exp.to_dict(),
        'best_atr': best_atr.to_dict(),
        'best_time': best_time.to_dict(),
        'best_trailing': best_trail.to_dict(),
        'best_overall': overall.to_dict(),
        'best_r_multiple': ratio_df.sort_values(['expectancy_ticks', 'profit_factor'], ascending=[False, False]).iloc[0].to_dict() if not ratio_df.empty else None,
    }
    with open(subset_dir / 'summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    return summary


def clean_float(value: Any) -> Any:
    if isinstance(value, float):
        if np.isinf(value):
            return 'inf'
        if np.isnan(value):
            return None
        return round(value, 4)
    if isinstance(value, dict):
        return {k: clean_float(v) for k, v in value.items()}
    return value


def print_summary(summary: dict[str, Any]) -> None:
    print(f"\n[{summary['subset']}] n={summary['signals']} (30b={summary['signals_with_30b_path']}, atr={summary['signals_with_atr']})")
    for label in ['best_fixed_pf', 'best_fixed_expectancy', 'best_atr', 'best_time', 'best_trailing', 'best_overall', 'best_r_multiple']:
        row = summary.get(label)
        if not row:
            continue
        row = clean_float(row)
        print(f"  {label}: {row}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bars = load_bars()
    events = load_absorption_events(bars)
    mats = build_future_matrices(events, bars)

    subset_defs = {
        'all_absorption': np.ones(len(events), dtype=bool),
        'type_a': (events['score_tier'] == 'TYPE_A').to_numpy(),
        'type_b': (events['score_tier'] == 'TYPE_B').to_numpy(),
        'type_c': (events['score_tier'] == 'TYPE_C').to_numpy(),
        'strength_ge_0_10': (events['strength'] >= 0.10).to_numpy(),
        'type_b_strength_ge_0_10': ((events['score_tier'] == 'TYPE_B') & (events['strength'] >= 0.10)).to_numpy(),
    }

    summaries = [run_subset(name, mask, events, mats, OUT_DIR) for name, mask in subset_defs.items() if mask.sum() > 0]
    with open(OUT_DIR / 'summary_all.json', 'w', encoding='utf-8') as f:
        json.dump(summaries, f, indent=2)

    overview_rows = []
    for s in summaries:
        best = s['best_overall']
        overview_rows.append({
            'subset': s['subset'],
            'signals': s['signals'],
            'best_family': best.get('family'),
            'expectancy_ticks': best.get('expectancy_ticks'),
            'profit_factor': best.get('profit_factor'),
            'win_rate': best.get('win_rate'),
            'max_consecutive_losses': best.get('max_consecutive_losses'),
        })
        print_summary(s)
    pd.DataFrame(overview_rows).to_csv(OUT_DIR / 'overview.csv', index=False)
    print(f"\nSaved detailed outputs to {OUT_DIR}")


if __name__ == '__main__':
    main()
