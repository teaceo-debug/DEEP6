#!/usr/bin/env python3
"""
opt6_multi_tf.py — Multi-Timeframe Confirmation for ChNavy6 VWAP Bounce

Uses the proven baseline approach from opt1 (30m bar exit simulation),
then layers lower-timeframe confirmations on top.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

# === Constants (match opt1 exactly) ===
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
BOUNCE_CONFIRM = 5.0  # 20 ticks = 5 pts

SESSION_START_H = 9.5   # 09:30 ET
SESSION_END_H = 14.5    # 14:30 ET
FLATTEN_H = 16.0        # 16:00 ET

BASELINE_SL = 160 * TICK_SIZE  # 40 pts
BASELINE_TP = 560 * TICK_SIZE  # 140 pts

CSV_PATH = "/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv"
OUT_PATH = "/Users/teaceo/DEEP6/scripts/opt6_multi_tf.txt"

# === Load & prep ===
print("Loading data...")
df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
df["ts_event"] = df["ts_event"].dt.tz_convert("US/Eastern")
df = df.sort_values("ts_event").reset_index(drop=True)
df["date"] = df["ts_event"].dt.date
df["time_h"] = df["ts_event"].dt.hour + df["ts_event"].dt.minute / 60.0
print(f"Loaded {len(df)} 1m bars, {df['date'].nunique()} dates")


def resample_bars(df_src, freq_min, start_h=SESSION_START_H, end_h=FLATTEN_H):
    """Resample 1m bars to Nm within each date."""
    mask = (df_src["time_h"] >= start_h) & (df_src["time_h"] < end_h)
    sdf = df_src[mask].copy()

    bars = []
    for date, gdf in sdf.groupby("date"):
        gdf = gdf.set_index("ts_event")
        r = gdf.resample(f"{freq_min}min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()
        r["date"] = date
        r["time_h"] = r.index.hour + r.index.minute / 60.0
        bars.append(r)

    result = pd.concat(bars).reset_index()
    return result


print("Resampling...")
bars30 = resample_bars(df, 30)
bars10 = resample_bars(df, 10)
bars15 = resample_bars(df, 15)
print(f"  30m: {len(bars30)} bars, 10m: {len(bars10)} bars, 15m: {len(bars15)} bars")


def compute_vwap_col(day_bars):
    """Compute cumulative VWAP for a day's bars. Returns Series."""
    typical = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3.0
    cum_tv = (typical * day_bars["volume"]).cumsum()
    cum_vol = day_bars["volume"].cumsum()
    return cum_tv / cum_vol


# === ChNavy6 Signal Generation (matches opt1 exactly) ===
def generate_signals(bars30_df):
    """Generate ChNavy6 signals on 30m bars. Returns list of signal dicts."""
    signals = []
    dates = sorted(bars30_df["date"].unique())

    for date in dates:
        day_bars = bars30_df[bars30_df["date"] == date].sort_values("ts_event").reset_index(drop=True)
        if len(day_bars) < 2:
            continue

        # Compute cumulative VWAP
        day_bars = day_bars.copy()
        day_bars["vwap"] = compute_vwap_col(day_bars)

        trade_taken = False
        for i in range(1, len(day_bars)):
            if trade_taken:
                break

            bar = day_bars.iloc[i]
            prev = day_bars.iloc[i - 1]

            if bar["time_h"] < SESSION_START_H or bar["time_h"] >= SESSION_END_H:
                continue

            prev_vwap = day_bars.iloc[i - 1]["vwap"]
            curr_vwap = bar["vwap"]

            was_below = prev["close"] < prev_vwap
            was_above = prev["close"] > prev_vwap

            direction = 0
            if was_below and bar["close"] > curr_vwap and (bar["close"] - curr_vwap) >= BOUNCE_CONFIRM:
                direction = 1
            elif was_above and bar["close"] < curr_vwap and (curr_vwap - bar["close"]) >= BOUNCE_CONFIRM:
                direction = -1

            if direction != 0:
                trade_taken = True
                signals.append({
                    "date": date,
                    "direction": direction,
                    "bar_time": bar["ts_event"] if isinstance(bar["ts_event"], pd.Timestamp) else pd.Timestamp(bar["ts_event"]),
                    "bar_idx": i,
                    "close": bar["close"],
                    "vwap": curr_vwap,
                    "time_h": bar["time_h"],
                })

    return signals


# === Trade simulation (matches opt1: walk forward on 30m bars) ===
def simulate_trade_30m(sig, day_bars_30m, sl_pts=BASELINE_SL, tp_pts=BASELINE_TP,
                       override_entry=None, override_time=None):
    """Simulate trade using 30m bars for exit (matches opt1)."""
    direction = sig["direction"]

    if override_entry is not None:
        entry = override_entry
        entry_idx_time = override_time
    else:
        entry = sig["close"] + SLIPPAGE_TICKS * TICK_SIZE * direction
        entry_idx_time = sig["bar_time"]

    if direction == 1:
        sl_level = entry - sl_pts
        tp_level = entry + tp_pts
    else:
        sl_level = entry + sl_pts
        tp_level = entry - tp_pts

    # Find start index in day_bars
    start_found = False
    exit_price = None
    exit_reason = None

    for j in range(len(day_bars_30m)):
        fbar = day_bars_30m.iloc[j]
        fbar_time = fbar["ts_event"] if isinstance(fbar["ts_event"], pd.Timestamp) else pd.Timestamp(fbar["ts_event"])

        if fbar_time <= entry_idx_time:
            continue

        if direction == 1:
            if fbar["low"] <= sl_level:
                exit_price = sl_level
                exit_reason = "SL"
                break
            if fbar["high"] >= tp_level:
                exit_price = tp_level
                exit_reason = "TP"
                break
        else:
            if fbar["high"] >= sl_level:
                exit_price = sl_level
                exit_reason = "SL"
                break
            if fbar["low"] <= tp_level:
                exit_price = tp_level
                exit_reason = "TP"
                break

        if fbar["time_h"] >= FLATTEN_H:
            exit_price = fbar["close"]
            exit_reason = "FLAT"
            break

    if exit_price is None:
        exit_price = day_bars_30m.iloc[-1]["close"]
        exit_reason = "EOD"

    if direction == 1:
        pnl_ticks = (exit_price - entry) / TICK_SIZE
    else:
        pnl_ticks = (entry - exit_price) / TICK_SIZE

    pnl_dollar = pnl_ticks * TICK_VALUE - 2 * COMMISSION_PER_SIDE

    return {
        "date": sig["date"],
        "direction": "LONG" if direction == 1 else "SHORT",
        "entry": entry,
        "exit": exit_price,
        "exit_reason": exit_reason,
        "pnl": pnl_dollar,
    }


def compute_stats(trades):
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_pct": 0, "pf": 0, "sharpe": 0, "max_dd": 0,
                "avg_win": 0, "avg_loss": 0, "winners": 0, "losers": 0}

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = np.max(dd) if len(dd) > 0 else 0

    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = (np.mean(pnls) / np.std(pnls)) * np.sqrt(252)
    else:
        sharpe = 0

    return {
        "trades": len(trades),
        "net_pnl": sum(pnls),
        "win_pct": len(wins) / len(trades) * 100,
        "pf": gross_win / gross_loss if gross_loss > 0 else float("inf"),
        "sharpe": sharpe,
        "max_dd": max_dd,
        "avg_win": np.mean(wins) if wins else 0,
        "avg_loss": np.mean(losses) if losses else 0,
        "winners": len(wins),
        "losers": len(losses),
    }


# === Pre-compute 10m and 15m VWAP per day ===
print("Computing VWAP on 10m and 15m bars...")
bars10_with_vwap = []
for date, grp in bars10.groupby("date"):
    grp = grp.sort_values("ts_event").copy()
    grp["vwap"] = compute_vwap_col(grp)
    bars10_with_vwap.append(grp)
bars10v = pd.concat(bars10_with_vwap).reset_index(drop=True)

bars15_with_vwap = []
for date, grp in bars15.groupby("date"):
    grp = grp.sort_values("ts_event").copy()
    grp["vwap"] = compute_vwap_col(grp)
    # EMA(20) for variant 3
    grp["ema20"] = grp["close"].ewm(span=20, adjust=False).mean()
    bars15_with_vwap.append(grp)
bars15v = pd.concat(bars15_with_vwap).reset_index(drop=True)

# Pre-build day lookups
bars30_by_date = {date: grp.sort_values("ts_event").reset_index(drop=True)
                  for date, grp in bars30.groupby("date")}

# Add VWAP to 30m day bars
for date in bars30_by_date:
    day = bars30_by_date[date].copy()
    day["vwap"] = compute_vwap_col(day)
    bars30_by_date[date] = day

bars10v_by_date = {date: grp.sort_values("ts_event").reset_index(drop=True)
                   for date, grp in bars10v.groupby("date")}
bars15v_by_date = {date: grp.sort_values("ts_event").reset_index(drop=True)
                   for date, grp in bars15v.groupby("date")}


# === Generate signals ===
print("Generating 30m ChNavy6 signals...")
# Use pre-computed VWAP bars for signal generation
all_bars30_vwap = pd.concat(bars30_by_date.values()).sort_values("ts_event").reset_index(drop=True)
signals = generate_signals(all_bars30_vwap)
print(f"  {len(signals)} signals generated")


# === Run baseline ===
print("\nRunning baseline...")
baseline_trades = []
for sig in signals:
    day30 = bars30_by_date.get(sig["date"])
    if day30 is not None:
        baseline_trades.append(simulate_trade_30m(sig, day30))
baseline_stats = compute_stats(baseline_trades)


# === Helper: run filtered variant ===
def run_filtered(signals, filter_fn, label):
    """Run variant with filter. Returns (trades, filtered_out, stats)."""
    trades = []
    filtered_winners = 0
    filtered_losers = 0

    for sig in signals:
        date = sig["date"]
        day30 = bars30_by_date.get(date)
        if day30 is None:
            continue

        if filter_fn(sig):
            trades.append(simulate_trade_30m(sig, day30))
        else:
            # Ghost trade to see what we filtered
            ghost = simulate_trade_30m(sig, day30)
            if ghost["pnl"] > 0:
                filtered_winners += 1
            else:
                filtered_losers += 1

    stats = compute_stats(trades)
    filt = {"winners": filtered_winners, "losers": filtered_losers}
    return trades, filt, stats


# === VARIANT 1: 10m VWAP slope confirmation ===
def make_v1_filter(lookback):
    def filt(sig):
        date = sig["date"]
        sig_time = sig["bar_time"]
        day10 = bars10v_by_date.get(date)
        if day10 is None:
            return False
        before = day10[day10["ts_event"] <= sig_time]
        if len(before) < lookback + 1:
            return False
        vwaps = before["vwap"].values[-(lookback + 1):]
        slope = vwaps[-1] - vwaps[0]
        return (sig["direction"] == 1 and slope > 0) or (sig["direction"] == -1 and slope < 0)
    return filt


# === VARIANT 2: 10m momentum filter ===
def make_v2_filter(lookback):
    def filt(sig):
        date = sig["date"]
        sig_time = sig["bar_time"]
        day10 = bars10v_by_date.get(date)
        if day10 is None:
            return False
        before = day10[day10["ts_event"] <= sig_time]
        if len(before) <= lookback:
            return False
        momentum = before["close"].values[-1] - before["close"].values[-lookback - 1]
        return (sig["direction"] == 1 and momentum > 0) or (sig["direction"] == -1 and momentum < 0)
    return filt


# === VARIANT 3: 15m EMA(20) trend ===
def v3_filter(sig):
    date = sig["date"]
    sig_time = sig["bar_time"]
    day15 = bars15v_by_date.get(date)
    if day15 is None:
        return False
    before = day15[day15["ts_event"] <= sig_time]
    if len(before) < 1:
        return False
    last = before.iloc[-1]
    return (sig["direction"] == 1 and last["close"] > last["ema20"]) or \
           (sig["direction"] == -1 and last["close"] < last["ema20"])


# === VARIANT 4: 10m VWAP bounce delayed entry ===
def run_v4(signals_list):
    """Delayed entry: wait for next 10m bar on right side of VWAP."""
    trades = []
    filtered_winners = 0
    filtered_losers = 0

    for sig in signals_list:
        date = sig["date"]
        day30 = bars30_by_date.get(date)
        day10 = bars10v_by_date.get(date)
        if day30 is None or day10 is None:
            continue

        sig_time = sig["bar_time"]
        after = day10[day10["ts_event"] > sig_time].sort_values("ts_event")

        confirmed = False
        if len(after) >= 1:
            next_bar = after.iloc[0]
            if sig["direction"] == 1 and next_bar["close"] > next_bar["vwap"]:
                confirmed = True
            elif sig["direction"] == -1 and next_bar["close"] < next_bar["vwap"]:
                confirmed = True

            if confirmed:
                # Delayed entry at next 10m bar close
                delayed_entry = next_bar["close"] + SLIPPAGE_TICKS * TICK_SIZE * sig["direction"]
                delayed_time = next_bar["ts_event"]
                trades.append(simulate_trade_30m(sig, day30,
                    override_entry=delayed_entry, override_time=delayed_time))
            else:
                ghost = simulate_trade_30m(sig, day30)
                if ghost["pnl"] > 0:
                    filtered_winners += 1
                else:
                    filtered_losers += 1
        else:
            ghost = simulate_trade_30m(sig, day30)
            if ghost["pnl"] > 0:
                filtered_winners += 1
            else:
                filtered_losers += 1

    return trades, {"winners": filtered_winners, "losers": filtered_losers}, compute_stats(trades)


# === VARIANT 5: Dual TF VWAP bounce ===
def v5_filter(sig):
    """Both 30m AND 10m show VWAP cross pattern."""
    date = sig["date"]
    day10 = bars10v_by_date.get(date)
    if day10 is None:
        return False

    sig_time = sig["bar_time"]
    before = day10[day10["ts_event"] <= sig_time].sort_values("ts_event")
    if len(before) < 2:
        return False

    prev_10 = before.iloc[-2]
    curr_10 = before.iloc[-1]

    if sig["direction"] == 1:
        return prev_10["close"] < prev_10["vwap"] and curr_10["close"] > curr_10["vwap"]
    else:
        return prev_10["close"] > prev_10["vwap"] and curr_10["close"] < curr_10["vwap"]


# === VARIANT 6: 10m bar count filter ===
def make_v6_filter(N, threshold):
    def filt(sig):
        date = sig["date"]
        sig_time = sig["bar_time"]
        day10 = bars10v_by_date.get(date)
        if day10 is None:
            return False
        before = day10[day10["ts_event"] <= sig_time]
        if len(before) < N:
            return False
        last_n = before.tail(N)
        if sig["direction"] == 1:
            count = (last_n["close"] > last_n["open"]).sum()
        else:
            count = (last_n["close"] < last_n["open"]).sum()
        return count >= threshold
    return filt


# ================================================================
# RUN ALL VARIANTS
# ================================================================
all_results = []  # (label, stats, filtered)

print("Running all variants...")

# Baseline
all_results.append(("Baseline (no filter)", baseline_stats, None))

# V1: VWAP slope
for lb in [3, 4, 6]:
    label = f"V1: 10m VWAP slope (lb={lb})"
    _, filt, stats = run_filtered(signals, make_v1_filter(lb), label)
    all_results.append((label, stats, filt))

# V2: Momentum
for lb in [3, 6, 9]:
    label = f"V2: 10m momentum (lb={lb})"
    _, filt, stats = run_filtered(signals, make_v2_filter(lb), label)
    all_results.append((label, stats, filt))

# V3: 15m EMA(20)
label = "V3: 15m EMA(20) trend"
_, filt, stats = run_filtered(signals, v3_filter, label)
all_results.append((label, stats, filt))

# V4: Delayed entry
label = "V4: 10m VWAP delayed entry"
_, filt, stats = run_v4(signals)
all_results.append((label, stats, filt))

# V5: Dual TF VWAP
label = "V5: Dual TF VWAP bounce"
_, filt, stats = run_filtered(signals, v5_filter, label)
all_results.append((label, stats, filt))

# V6: Bar count
for N, thresh in [(6, 4), (6, 3), (9, 6), (9, 5), (12, 8)]:
    label = f"V6: 10m bar count (N={N}, t>={thresh})"
    _, filt, stats = run_filtered(signals, make_v6_filter(N, thresh), label)
    all_results.append((label, stats, filt))


# ================================================================
# FORMAT OUTPUT
# ================================================================
lines = []
p = lines.append

p("=" * 76)
p("OPT6: MULTI-TIMEFRAME CONFIRMATION FOR ChNavy6 VWAP BOUNCE")
p("=" * 76)
p(f"Data: {len(df)} 1m bars, {df['date'].nunique()} trading days")
p(f"Base: 30m ChNavy6, SL=160t ({BASELINE_SL:.0f} pts), TP=560t ({BASELINE_TP:.0f} pts)")
p(f"Signals generated: {len(signals)}")
p("")

for label, stats, filt in all_results:
    p("-" * 76)
    p(label)
    p("-" * 76)
    p(f"  {'Trades:':<18} {stats['trades']}")
    p(f"  {'Net PnL:':<18} ${stats['net_pnl']:,.2f}")
    p(f"  {'Win %:':<18} {stats['win_pct']:.1f}%  ({stats['winners']}W / {stats['losers']}L)")
    p(f"  {'Profit Factor:':<18} {stats['pf']:.2f}")
    p(f"  {'Sharpe (ann.):':<18} {stats['sharpe']:.2f}")
    p(f"  {'Max Drawdown:':<18} ${stats['max_dd']:,.2f}")
    p(f"  {'Avg Winner:':<18} ${stats['avg_win']:,.2f}")
    p(f"  {'Avg Loser:':<18} ${stats['avg_loss']:,.2f}")
    if filt:
        total_filt = filt['winners'] + filt['losers']
        p(f"  {'Filtered out:':<18} {filt['winners']}W + {filt['losers']}L = {total_filt} trades")
        if total_filt > 0:
            loser_pct = filt['losers'] / total_filt * 100
            p(f"  {'Filter quality:':<18} {loser_pct:.0f}% of filtered were losers (higher = better filter)")
    p("")

# === Comparison table ===
p("=" * 76)
p("COMPARISON TABLE — ALL VARIANTS vs BASELINE (sorted by Net PnL)")
p("=" * 76)
hdr = f"{'Variant':<38} {'#':>3} {'Net PnL':>10} {'W%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>9}"
p(hdr)
p("-" * len(hdr))

sorted_results = sorted(all_results, key=lambda x: x[1]["net_pnl"], reverse=True)
bl_pnl = baseline_stats["net_pnl"]

for label, st, filt in sorted_results:
    tag = ""
    if "Baseline" in label:
        tag = " <-- BASE"
    elif st["net_pnl"] > bl_pnl:
        tag = " +"
    line = f"{label:<38} {st['trades']:>3} {st['net_pnl']:>10,.2f} {st['win_pct']:>5.1f}% {st['pf']:>6.2f} {st['sharpe']:>7.2f} {st['max_dd']:>9,.2f}{tag}"
    p(line)

p("")

# === Filter effectiveness ===
p("=" * 76)
p("FILTER EFFECTIVENESS — How many losers did each filter remove?")
p("=" * 76)
hdr2 = f"{'Variant':<38} {'Kept':>4} {'Filt':>4} {'FiltL':>5} {'FiltW':>5} {'L%':>5}"
p(hdr2)
p("-" * len(hdr2))
for label, st, filt in all_results:
    if filt is None:
        continue
    total_filt = filt['winners'] + filt['losers']
    lpct = filt['losers'] / total_filt * 100 if total_filt > 0 else 0
    p(f"{label:<38} {st['trades']:>4} {total_filt:>4} {filt['losers']:>5} {filt['winners']:>5} {lpct:>4.0f}%")

p("")

# === Key findings ===
p("=" * 76)
p("KEY FINDINGS")
p("=" * 76)

best = sorted_results[0]
p(f"1. Best by PnL: {best[0]}")
p(f"   Net PnL: ${best[1]['net_pnl']:,.2f}  (baseline: ${bl_pnl:,.2f}, delta: ${best[1]['net_pnl'] - bl_pnl:+,.2f})")
p("")

# Best PF (min 5 trades)
pf_candidates = [(l, s, f) for l, s, f in all_results if s["trades"] >= 5]
if pf_candidates:
    best_pf = max(pf_candidates, key=lambda x: x[1]["pf"])
    p(f"2. Best Profit Factor (>=5 trades): {best_pf[0]}")
    p(f"   PF: {best_pf[1]['pf']:.2f}, {best_pf[1]['trades']} trades")
    p("")

# Best Sharpe
best_sh = max(all_results, key=lambda x: x[1]["sharpe"])
p(f"3. Best Sharpe: {best_sh[0]}")
p(f"   Sharpe: {best_sh[1]['sharpe']:.2f}")
p("")

# Best filter quality (highest % losers filtered, min 10 filtered)
filter_quality = []
for label, st, filt in all_results:
    if filt and (filt['winners'] + filt['losers']) >= 10:
        total = filt['winners'] + filt['losers']
        filter_quality.append((label, filt['losers']/total*100, filt, st))

if filter_quality:
    filter_quality.sort(key=lambda x: x[1], reverse=True)
    p(f"4. Best filter quality (>=10 filtered): {filter_quality[0][0]}")
    p(f"   {filter_quality[0][1]:.0f}% of filtered trades were losers")
    p(f"   Filtered: {filter_quality[0][2]['losers']}L + {filter_quality[0][2]['winners']}W")
    p("")

# Trade-by-trade for baseline
p("=" * 76)
p("BASELINE TRADE LOG")
p("=" * 76)
p(f"{'Date':<12} {'Dir':>5} {'Entry':>10} {'Exit':>10} {'Reason':>6} {'PnL':>10}")
p("-" * 60)
for t in baseline_trades:
    p(f"{t['date']!s:<12} {t['direction']:>5} {t['entry']:>10.2f} {t['exit']:>10.2f} {t['exit_reason']:>6} ${t['pnl']:>9.2f}")

output = "\n".join(lines)
print("\n" + output)

Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w") as f:
    f.write(output)

print(f"\nResults written to {OUT_PATH}")
