"""
ChNavy6 VWAP Bounce — ATR-Scaled Dynamic Stops Optimization
Compare ATR-scaled SL/TP vs baseline fixed SL=160t TP=560t
"""
import pandas as pd
import numpy as np
from itertools import product
from io import StringIO
import sys

# ── Constants ──
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
BOUNCE_CONFIRM_TICKS = 20  # 5 pts
BOUNCE_CONFIRM = BOUNCE_CONFIRM_TICKS * TICK_SIZE  # 5.0

SESSION_START_H = 9.5   # 09:30 ET
SESSION_END_H = 14.5    # 14:30 ET
FLATTEN_H = 16.0        # 16:00 ET

CSV_PATH = "/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv"
OUT_PATH = "/Users/teaceo/DEEP6/scripts/opt1_atr_stops.txt"

# ── Load & prep ──
print("Loading data...")
df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
df["ts_event"] = df["ts_event"].dt.tz_convert("US/Eastern")
df = df.sort_values("ts_event").reset_index(drop=True)
df["date"] = df["ts_event"].dt.date
df["time_h"] = df["ts_event"].dt.hour + df["ts_event"].dt.minute / 60.0

print(f"Loaded {len(df)} 1m bars, {df['date'].nunique()} dates")

# ── Resample to 30m per calendar date ──
def resample_30m(df):
    """Resample 1m bars to 30m within each date, session hours only."""
    # Filter to session hours (use wider window for ATR calc + flatten)
    mask = (df["time_h"] >= SESSION_START_H) & (df["time_h"] < FLATTEN_H)
    sdf = df[mask].copy()

    # Group by date and resample
    bars = []
    for date, gdf in sdf.groupby("date"):
        gdf = gdf.set_index("ts_event")
        r = gdf.resample("30min").agg({
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

print("Resampling to 30m...")
bars30 = resample_30m(df)
print(f"  {len(bars30)} 30m bars")

# ── Compute ATR per day using different lookback methods ──
def compute_true_range(bars):
    """Compute True Range for each bar."""
    tr = np.maximum(
        bars["high"] - bars["low"],
        np.maximum(
            abs(bars["high"] - bars["close"].shift(1)),
            abs(bars["low"] - bars["close"].shift(1))
        )
    )
    return tr

bars30["tr"] = compute_true_range(bars30)

def get_atr_map(bars30, method):
    """Return dict: date -> ATR value for that session."""
    atr_map = {}
    dates = sorted(bars30["date"].unique())

    if method == "prior_day":
        # Full prior day's average TR
        for i, date in enumerate(dates):
            if i == 0:
                # Use own day's ATR for first day
                day_bars = bars30[bars30["date"] == date]
                atr_map[date] = day_bars["tr"].mean() if len(day_bars) > 0 else 50.0
            else:
                prev_date = dates[i - 1]
                prev_bars = bars30[bars30["date"] == prev_date]
                atr_map[date] = prev_bars["tr"].mean() if len(prev_bars) > 0 else 50.0

    elif method == "first_3_bars":
        # First 3 bars of current day (09:30-11:00)
        for date in dates:
            day_bars = bars30[bars30["date"] == date].sort_values("ts_event")
            first3 = day_bars.head(3)
            atr_map[date] = first3["tr"].mean() if len(first3) > 0 else 50.0

    elif method == "rolling_5d":
        # Rolling 5-day average ATR
        daily_atrs = []
        for date in dates:
            day_bars = bars30[bars30["date"] == date]
            daily_atrs.append((date, day_bars["tr"].mean() if len(day_bars) > 0 else 50.0))

        for i, date in enumerate(dates):
            lookback = [a for _, a in daily_atrs[max(0, i-5):i]]
            if len(lookback) == 0:
                atr_map[date] = daily_atrs[i][1]
            else:
                atr_map[date] = np.mean(lookback)

    return atr_map

# Pre-compute all ATR maps
print("Computing ATR maps...")
atr_maps = {}
for method in ["prior_day", "first_3_bars", "rolling_5d"]:
    atr_maps[method] = get_atr_map(bars30, method)

# ── VWAP + Signal generation on 30m bars ──
def run_strategy(bars30, sl_price, tp_price, is_dynamic=False, atr_map=None,
                 sl_mult=1.0, tp_mult=2.0, floor_sl=None, floor_tp=None):
    """
    Run ChNavy6 VWAP bounce strategy on 30m bars.

    If is_dynamic: SL = ATR * sl_mult, TP = ATR * tp_mult (in price terms)
    If floor_sl/floor_tp set: use max(floor, ATR*mult) -- hybrid mode
    Otherwise: fixed SL/TP in price terms.
    """
    trades = []
    dates = sorted(bars30["date"].unique())

    for date in dates:
        day_bars = bars30[bars30["date"] == date].sort_values("ts_event").reset_index(drop=True)
        if len(day_bars) < 2:
            continue

        # Determine SL/TP for this day
        if is_dynamic and atr_map is not None:
            day_atr = atr_map.get(date, 50.0)
            day_sl = day_atr * sl_mult
            day_tp = day_atr * tp_mult
            if floor_sl is not None:
                day_sl = max(floor_sl, day_sl)
            if floor_tp is not None:
                day_tp = max(floor_tp, day_tp)
        else:
            day_sl = sl_price
            day_tp = tp_price

        # Compute cumulative VWAP
        typical = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3.0
        cum_tv = (typical * day_bars["volume"]).cumsum()
        cum_vol = day_bars["volume"].cumsum()
        day_bars = day_bars.copy()
        day_bars["vwap"] = cum_tv / cum_vol

        trade_taken = False

        for i in range(1, len(day_bars)):
            if trade_taken:
                break

            bar = day_bars.iloc[i]
            prev = day_bars.iloc[i - 1]

            # Only enter during session window
            if bar["time_h"] < SESSION_START_H or bar["time_h"] >= SESSION_END_H:
                continue

            prev_vwap = day_bars.iloc[i - 1]["vwap"] if i >= 1 else bar["vwap"]
            curr_vwap = bar["vwap"]

            was_below = prev["close"] < prev_vwap
            was_above = prev["close"] > prev_vwap

            # Long signal
            if was_below and bar["close"] > curr_vwap and (bar["close"] - curr_vwap) >= BOUNCE_CONFIRM:
                direction = 1
                entry = bar["close"] + SLIPPAGE_TICKS * TICK_SIZE
                sl_level = entry - day_sl
                tp_level = entry + day_tp
                trade_taken = True
            # Short signal
            elif was_above and bar["close"] < curr_vwap and (curr_vwap - bar["close"]) >= BOUNCE_CONFIRM:
                direction = -1
                entry = bar["close"] - SLIPPAGE_TICKS * TICK_SIZE
                sl_level = entry + day_sl
                tp_level = entry - day_tp
                trade_taken = True
            else:
                continue

            # Walk forward to find exit
            exit_price = None
            exit_reason = None

            for j in range(i + 1, len(day_bars)):
                fbar = day_bars.iloc[j]

                if direction == 1:
                    # Check SL first (conservative)
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

                # Flatten at 16:00
                if fbar["time_h"] >= FLATTEN_H:
                    exit_price = fbar["close"]
                    exit_reason = "FLAT"
                    break

            if exit_price is None:
                # End of day
                exit_price = day_bars.iloc[-1]["close"]
                exit_reason = "EOD"

            # PnL
            if direction == 1:
                pnl_ticks = (exit_price - entry) / TICK_SIZE
            else:
                pnl_ticks = (entry - exit_price) / TICK_SIZE

            pnl_dollar = pnl_ticks * TICK_VALUE - 2 * COMMISSION_PER_SIDE

            trades.append({
                "date": date,
                "direction": "LONG" if direction == 1 else "SHORT",
                "entry": entry,
                "exit": exit_price,
                "exit_reason": exit_reason,
                "sl_pts": day_sl,
                "tp_pts": day_tp,
                "pnl_ticks": pnl_ticks,
                "pnl": pnl_dollar,
                "atr": atr_map.get(date, 0) if atr_map else 0,
            })

    return trades

def compute_metrics(trades):
    """Compute strategy metrics from trade list."""
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_pct": 0, "pf": 0,
                "sharpe": 0, "max_dd": 0, "monthly": {}}

    tdf = pd.DataFrame(trades)
    n = len(tdf)
    wins = (tdf["pnl"] > 0).sum()
    gross_profit = tdf.loc[tdf["pnl"] > 0, "pnl"].sum()
    gross_loss = abs(tdf.loc[tdf["pnl"] < 0, "pnl"].sum())
    net = tdf["pnl"].sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe (daily returns)
    daily_pnl = tdf["pnl"].values
    sharpe = (daily_pnl.mean() / daily_pnl.std() * np.sqrt(252)) if daily_pnl.std() > 0 else 0

    # Max drawdown
    cumulative = np.cumsum(daily_pnl)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_dd = drawdowns.max()

    # Monthly breakdown
    tdf["month"] = pd.to_datetime(tdf["date"]).dt.to_period("M")
    monthly = {}
    for m, mdf in tdf.groupby("month"):
        mw = (mdf["pnl"] > 0).sum()
        mn = len(mdf)
        monthly[str(m)] = {
            "trades": mn,
            "net": round(mdf["pnl"].sum(), 2),
            "win_pct": round(100 * mw / mn, 1) if mn > 0 else 0,
        }

    return {
        "trades": n,
        "net_pnl": round(net, 2),
        "win_pct": round(100 * wins / n, 1),
        "pf": round(pf, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "monthly": monthly,
    }

# ── Run baseline ──
print("\n=== BASELINE: Fixed SL=160t ($40), TP=560t ($140) ===")
baseline_sl = 160 * TICK_SIZE  # 40 pts
baseline_tp = 560 * TICK_SIZE  # 140 pts
baseline_trades = run_strategy(bars30, baseline_sl, baseline_tp)
baseline_metrics = compute_metrics(baseline_trades)
print(f"  Trades: {baseline_metrics['trades']}, Net: ${baseline_metrics['net_pnl']:,.2f}, "
      f"Win%: {baseline_metrics['win_pct']}%, PF: {baseline_metrics['pf']}, "
      f"Sharpe: {baseline_metrics['sharpe']}, MaxDD: ${baseline_metrics['max_dd']:,.2f}")
for m, v in baseline_metrics["monthly"].items():
    print(f"    {m}: {v['trades']} trades, ${v['net']:,.2f}, {v['win_pct']}% WR")

# ── ATR-Scaled Grid Search ──
sl_mults = [0.3, 0.5, 0.7, 1.0, 1.2, 1.5]
tp_mults = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
atr_methods = ["prior_day", "first_3_bars", "rolling_5d"]

results = []
total = len(sl_mults) * len(tp_mults) * len(atr_methods)
print(f"\n=== ATR-SCALED GRID: {total} configs ===")

count = 0
for method in atr_methods:
    atr_map = atr_maps[method]
    for sl_m, tp_m in product(sl_mults, tp_mults):
        count += 1
        trades = run_strategy(bars30, 0, 0, is_dynamic=True, atr_map=atr_map,
                              sl_mult=sl_m, tp_mult=tp_m)
        metrics = compute_metrics(trades)
        results.append({
            "method": method,
            "sl_mult": sl_m,
            "tp_mult": tp_m,
            "mode": "pure_atr",
            **metrics
        })
        if count % 18 == 0:
            print(f"  {count}/{total} done...")

# ── HYBRID: max(floor, ATR*mult) ──
# Floor = baseline * 0.5 (half the original fixed stops)
floor_sl_pts = baseline_sl * 0.5  # 20 pts
floor_tp_pts = baseline_tp * 0.5  # 70 pts

hybrid_configs = [
    (0.5, 2.0), (0.7, 2.0), (0.7, 2.5), (1.0, 2.5), (1.0, 3.0), (1.2, 3.0),
    (0.5, 1.5), (0.7, 1.5), (1.0, 2.0), (1.5, 3.0), (1.5, 4.0), (0.3, 1.0),
]
print(f"\n=== HYBRID (floor SL={floor_sl_pts}pts, TP={floor_tp_pts}pts): {len(hybrid_configs) * len(atr_methods)} configs ===")

for method in atr_methods:
    atr_map = atr_maps[method]
    for sl_m, tp_m in hybrid_configs:
        trades = run_strategy(bars30, 0, 0, is_dynamic=True, atr_map=atr_map,
                              sl_mult=sl_m, tp_mult=tp_m,
                              floor_sl=floor_sl_pts, floor_tp=floor_tp_pts)
        metrics = compute_metrics(trades)
        results.append({
            "method": method,
            "sl_mult": sl_m,
            "tp_mult": tp_m,
            "mode": "hybrid",
            **metrics
        })

# ── Sort and report ──
results_df = pd.DataFrame(results)
results_df = results_df.sort_values("net_pnl", ascending=False)

# ── Write output ──
buf = StringIO()
def p(s=""):
    buf.write(s + "\n")

p("=" * 90)
p("ChNavy6 VWAP Bounce — ATR-Scaled Dynamic Stops Optimization Results")
p("=" * 90)
p()

p("BASELINE (Fixed SL=160t/$40, TP=560t/$140):")
p(f"  Trades: {baseline_metrics['trades']}  |  Net PnL: ${baseline_metrics['net_pnl']:,.2f}  |  "
  f"Win%: {baseline_metrics['win_pct']}%  |  PF: {baseline_metrics['pf']}  |  "
  f"Sharpe: {baseline_metrics['sharpe']}  |  MaxDD: ${baseline_metrics['max_dd']:,.2f}")
p("  Monthly:")
for m, v in baseline_metrics["monthly"].items():
    p(f"    {m}: {v['trades']} trades, ${v['net']:+,.2f}, {v['win_pct']}% WR")
p()

# Print ATR summary stats
p("ATR STATISTICS (30m bars):")
for method in atr_methods:
    atr_vals = list(atr_maps[method].values())
    p(f"  {method:15s}: mean={np.mean(atr_vals):.1f} pts, "
      f"min={np.min(atr_vals):.1f}, max={np.max(atr_vals):.1f}, "
      f"std={np.std(atr_vals):.1f}")
p()

p("=" * 90)
p("TOP 20 CONFIGURATIONS (by Net PnL)")
p("=" * 90)
p(f"{'Rk':>3} {'Mode':>7} {'ATR Method':>14} {'SL_m':>5} {'TP_m':>5} "
  f"{'Trades':>6} {'Net PnL':>10} {'Win%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>9}")
p("-" * 90)

for rank, (_, row) in enumerate(results_df.head(20).iterrows(), 1):
    p(f"{rank:3d} {row['mode']:>7s} {row['method']:>14s} {row['sl_mult']:5.1f} {row['tp_mult']:5.1f} "
      f"{row['trades']:6d} ${row['net_pnl']:>9,.2f} {row['win_pct']:5.1f}% {row['pf']:5.2f} "
      f"{row['sharpe']:6.2f} ${row['max_dd']:>8,.2f}")

p()
p("=" * 90)
p("TOP 5 — MONTHLY BREAKDOWN")
p("=" * 90)

for rank, (_, row) in enumerate(results_df.head(5).iterrows(), 1):
    p(f"\n#{rank}: {row['mode']} | {row['method']} | SL={row['sl_mult']}x ATR, TP={row['tp_mult']}x ATR")
    p(f"     Net: ${row['net_pnl']:,.2f} | Win%: {row['win_pct']}% | PF: {row['pf']} | Sharpe: {row['sharpe']} | MaxDD: ${row['max_dd']:,.2f}")

    # Re-run to get monthly detail
    if row["mode"] == "hybrid":
        trades = run_strategy(bars30, 0, 0, is_dynamic=True, atr_map=atr_maps[row["method"]],
                              sl_mult=row["sl_mult"], tp_mult=row["tp_mult"],
                              floor_sl=floor_sl_pts, floor_tp=floor_tp_pts)
    else:
        trades = run_strategy(bars30, 0, 0, is_dynamic=True, atr_map=atr_maps[row["method"]],
                              sl_mult=row["sl_mult"], tp_mult=row["tp_mult"])
    metrics = compute_metrics(trades)
    p(f"     Monthly:")
    for m, v in metrics["monthly"].items():
        flag = " <<<" if v["net"] < -2000 else ""
        p(f"       {m}: {v['trades']:2d} trades, ${v['net']:>+8,.2f}, {v['win_pct']:5.1f}% WR{flag}")

# ── Comparison vs baseline ──
best = results_df.iloc[0]
p()
p("=" * 90)
p("BEST ATR-SCALED vs BASELINE COMPARISON")
p("=" * 90)
p(f"  Baseline Fixed:  ${baseline_metrics['net_pnl']:>+10,.2f}  |  Win%: {baseline_metrics['win_pct']}%  |  PF: {baseline_metrics['pf']}  |  MaxDD: ${baseline_metrics['max_dd']:,.2f}")
p(f"  Best ATR-Scaled: ${best['net_pnl']:>+10,.2f}  |  Win%: {best['win_pct']}%  |  PF: {best['pf']}  |  MaxDD: ${best['max_dd']:,.2f}")
diff = best["net_pnl"] - baseline_metrics["net_pnl"]
p(f"  Delta:           ${diff:>+10,.2f}  ({'+' if diff > 0 else ''}{100*diff/abs(baseline_metrics['net_pnl']):.1f}%)")
p(f"  Config:          {best['mode']} | {best['method']} | SL={best['sl_mult']}x, TP={best['tp_mult']}x")

# ── Bottom configs for reference ──
p()
p("=" * 90)
p("WORST 5 CONFIGURATIONS (avoid these)")
p("=" * 90)
for rank, (_, row) in enumerate(results_df.tail(5).iterrows(), 1):
    p(f"  {row['mode']:>7s} {row['method']:>14s} SL={row['sl_mult']:.1f}x TP={row['tp_mult']:.1f}x "
      f"-> ${row['net_pnl']:>+9,.2f}, {row['win_pct']}% WR, MaxDD ${row['max_dd']:,.2f}")

# Check if any config fixes March
p()
p("=" * 90)
p("MARCH PERFORMANCE ACROSS ALL CONFIGS")
p("=" * 90)
march_results = []
for _, row in results_df.iterrows():
    monthly = row.get("monthly", {})
    march = monthly.get("2026-03", None)
    if march:
        march_results.append({
            "mode": row["mode"],
            "method": row["method"],
            "sl_mult": row["sl_mult"],
            "tp_mult": row["tp_mult"],
            "march_pnl": march["net"],
            "march_wr": march["win_pct"],
            "march_trades": march["trades"],
            "total_pnl": row["net_pnl"],
        })

mdf = pd.DataFrame(march_results).sort_values("march_pnl", ascending=False)
p(f"{'Mode':>7} {'ATR Method':>14} {'SL_m':>5} {'TP_m':>5} {'Mar PnL':>10} {'Mar WR':>7} {'Mar Tr':>6} {'Total PnL':>10}")
p("-" * 80)
for _, row in mdf.head(15).iterrows():
    p(f"{row['mode']:>7s} {row['method']:>14s} {row['sl_mult']:5.1f} {row['tp_mult']:5.1f} "
      f"${row['march_pnl']:>+9,.2f} {row['march_wr']:5.1f}% {row['march_trades']:5.0f} ${row['total_pnl']:>+9,.2f}")

output = buf.getvalue()
print(output)

with open(OUT_PATH, "w") as f:
    f.write(output)
print(f"\nResults written to {OUT_PATH}")
