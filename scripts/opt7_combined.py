#!/usr/bin/env python3
"""
opt7_combined.py — Kitchen-sink ChNavy6 VWAP Bounce optimization
Tests 12 combinations (A-L) of: ATR stops, regime filter, trailing stop,
time restriction, loss breaker, direction filter.
Includes walk-forward validation on best combo.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import sys, io

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
POINT_VALUE = TICK_VALUE / TICK_SIZE  # $20/point
COMM_RT = 0.35 * 2  # round-trip commission
SLIPPAGE_TICKS = 1
SLIPPAGE_PTS = SLIPPAGE_TICKS * TICK_SIZE  # 0.25 pts

CSV_PATH = Path("/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv")
OUT_PATH = Path("/Users/teaceo/DEEP6/scripts/opt7_combined.txt")


# ── Feature Flags ──────────────────────────────────────────────────────────
@dataclass
class StrategyConfig:
    name: str = "Baseline"
    # ATR-scaled stops
    use_atr_stops: bool = False
    sl_ticks: int = 160
    tp_ticks: int = 560
    atr_sl_mult: float = 0.7
    atr_tp_mult: float = 2.5
    min_sl_ticks: int = 100
    min_tp_ticks: int = 400
    # Regime filter
    use_regime_filter: bool = False
    regime_min_atr_pts: float = 30.0
    # Trailing stop
    use_trailing: bool = False
    trail_activate_ticks: int = 200  # +200t to activate
    trail_offset_ticks: int = 100   # trail by 100t from best
    # Time restriction
    use_time_filter: bool = False
    entry_start_hour: int = 9
    entry_start_min: int = 30
    entry_end_hour: int = 11
    entry_end_min: int = 0
    # Loss streak breaker
    use_loss_breaker: bool = False
    loss_streak_trigger: int = 3
    skip_days_after: int = 2
    # Direction filter
    use_direction_filter: bool = False
    direction_lookback_days: int = 5


# ── Data Loading ───────────────────────────────────────────────────────────
def load_data():
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df["ts_event"] = df["ts_event"].dt.tz_convert("US/Eastern")
    df = df.sort_values("ts_event").reset_index(drop=True)
    return df


def resample_30m(df_1m):
    """Resample 1m bars to 30m bars per calendar date (US/Eastern)."""
    df = df_1m.copy()
    df["date"] = df["ts_event"].dt.date
    # Filter to RTH-ish (we keep all for VWAP but group by 30m)
    df.set_index("ts_event", inplace=True)
    bars = df.resample("30min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "date": "first"
    }).dropna(subset=["open"]).reset_index()
    bars = bars[bars["volume"] > 0].reset_index(drop=True)
    return bars


def compute_daily_atr(bars_30m, period=14):
    """Compute daily ATR from 30m bars (daily H/L range, then EMA)."""
    daily = bars_30m.groupby("date").agg(
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        open=("open", "first")
    ).reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    daily.sort_values("date", inplace=True)
    # True range
    daily["prev_close"] = daily["close"].shift(1)
    daily["tr"] = np.maximum(
        daily["high"] - daily["low"],
        np.maximum(
            abs(daily["high"] - daily["prev_close"]),
            abs(daily["low"] - daily["prev_close"])
        )
    )
    daily["atr"] = daily["tr"].ewm(span=period, adjust=False).mean()
    return daily[["date", "atr", "close"]].set_index("date")


def compute_daily_vwap_close(bars_30m):
    """Compute end-of-day VWAP for each trading day (for direction filter)."""
    result = {}
    for date, grp in bars_30m.groupby("date"):
        tp = (grp["high"] + grp["low"] + grp["close"]) / 3
        cum_tpv = (tp * grp["volume"]).cumsum()
        cum_v = grp["volume"].cumsum()
        vwap_final = cum_tpv.iloc[-1] / cum_v.iloc[-1] if cum_v.iloc[-1] > 0 else grp["close"].iloc[-1]
        result[date] = vwap_final
    return pd.Series(result)


# ── Strategy Engine ────────────────────────────────────────────────────────
@dataclass
class Trade:
    date: object
    direction: int  # +1 long, -1 short
    entry_price: float
    entry_time: object
    exit_price: float = 0.0
    exit_time: object = None
    exit_reason: str = ""
    pnl_pts: float = 0.0
    pnl_dollar: float = 0.0


def run_strategy(bars_30m, cfg: StrategyConfig, start_date=None, end_date=None):
    """Run ChNavy6 VWAP bounce strategy with configurable features."""
    daily_atr_df = compute_daily_atr(bars_30m)
    daily_vwap = compute_daily_vwap_close(bars_30m)

    dates = sorted(bars_30m["date"].unique())
    if start_date:
        dates = [d for d in dates if d >= start_date]
    if end_date:
        dates = [d for d in dates if d <= end_date]

    trades = []
    consecutive_losses = 0
    skip_until_date = None

    for date in dates:
        date_pd = pd.Timestamp(date)

        # Loss breaker: skip days
        if cfg.use_loss_breaker and skip_until_date and date <= skip_until_date:
            continue

        # Regime filter: check prior day ATR
        if cfg.use_regime_filter:
            if date_pd in daily_atr_df.index:
                prior_atr = daily_atr_df.loc[:date_pd].iloc[-2]["atr"] if len(daily_atr_df.loc[:date_pd]) >= 2 else None
            else:
                # Find closest prior date
                prior_dates = daily_atr_df.index[daily_atr_df.index < date_pd]
                prior_atr = daily_atr_df.loc[prior_dates[-1], "atr"] if len(prior_dates) > 0 else None
            if prior_atr is not None and prior_atr < cfg.regime_min_atr_pts:
                continue

        # Direction filter: compute rolling 5-day VWAP slope
        allowed_direction = 0  # 0 = any
        if cfg.use_direction_filter:
            prior_vwaps = {d: daily_vwap[d] for d in daily_vwap.index if d < date}
            sorted_vwap_dates = sorted(prior_vwaps.keys())
            if len(sorted_vwap_dates) >= cfg.direction_lookback_days:
                recent = sorted_vwap_dates[-cfg.direction_lookback_days:]
                vals = [prior_vwaps[d] for d in recent]
                slope = vals[-1] - vals[0]
                if slope > 0:
                    allowed_direction = 1  # only longs
                elif slope < 0:
                    allowed_direction = -1  # only shorts

        # Determine SL/TP for today
        if cfg.use_atr_stops:
            if date_pd in daily_atr_df.index:
                prior_atr_val = daily_atr_df.loc[:date_pd].iloc[-2]["atr"] if len(daily_atr_df.loc[:date_pd]) >= 2 else None
            else:
                prior_dates = daily_atr_df.index[daily_atr_df.index < date_pd]
                prior_atr_val = daily_atr_df.loc[prior_dates[-1], "atr"] if len(prior_dates) > 0 else None

            if prior_atr_val is not None:
                atr_sl_pts = prior_atr_val * cfg.atr_sl_mult
                atr_tp_pts = prior_atr_val * cfg.atr_tp_mult
                sl_pts = max(cfg.min_sl_ticks * TICK_SIZE, atr_sl_pts)
                tp_pts = max(cfg.min_tp_ticks * TICK_SIZE, atr_tp_pts)
            else:
                sl_pts = cfg.sl_ticks * TICK_SIZE
                tp_pts = cfg.tp_ticks * TICK_SIZE
        else:
            sl_pts = cfg.sl_ticks * TICK_SIZE
            tp_pts = cfg.tp_ticks * TICK_SIZE

        # Get bars for this day
        day_bars = bars_30m[bars_30m["date"] == date].sort_values("ts_event").reset_index(drop=True)
        if len(day_bars) < 2:
            continue

        # Compute running VWAP
        tp_arr = (day_bars["high"] + day_bars["low"] + day_bars["close"]) / 3
        cum_tpv = (tp_arr * day_bars["volume"]).cumsum()
        cum_vol = day_bars["volume"].cumsum()
        day_bars = day_bars.copy()
        day_bars["vwap"] = cum_tpv / cum_vol

        traded_today = False

        for i in range(1, len(day_bars)):
            if traded_today:
                break

            bar = day_bars.iloc[i]
            prev_bar = day_bars.iloc[i - 1]
            bar_time = bar["ts_event"]

            # Time filter
            if cfg.use_time_filter:
                t = bar_time
                start_t = t.replace(hour=cfg.entry_start_hour, minute=cfg.entry_start_min, second=0)
                end_t = t.replace(hour=cfg.entry_end_hour, minute=cfg.entry_end_min, second=0)
                if t < start_t or t >= end_t:
                    continue

            # VWAP bounce logic
            prev_close = prev_bar["close"]
            prev_vwap = prev_bar["vwap"]
            curr_close = bar["close"]
            curr_vwap = bar["vwap"]

            was_below = prev_close < prev_vwap
            was_above = prev_close > prev_vwap
            cross_up = curr_close > curr_vwap and (curr_close - curr_vwap) >= 5.0
            cross_down = curr_close < curr_vwap and (curr_vwap - curr_close) >= 5.0

            direction = 0
            if was_below and cross_up:
                direction = 1
            elif was_above and cross_down:
                direction = -1

            if direction == 0:
                continue

            # Direction filter
            if cfg.use_direction_filter and allowed_direction != 0:
                if direction != allowed_direction:
                    continue

            # Entry
            entry_price = curr_close + direction * SLIPPAGE_PTS
            traded_today = True

            # Simulate exit using remaining 30m bars
            exit_price = None
            exit_reason = ""
            exit_time = None
            best_price = entry_price

            remaining_bars = day_bars.iloc[i + 1:]

            for j, (_, rbar) in enumerate(remaining_bars.iterrows()):
                rbar_time = rbar["ts_event"]

                # Flatten at 16:00
                if rbar_time.hour >= 16:
                    exit_price = rbar["close"] - direction * SLIPPAGE_PTS
                    exit_reason = "FLATTEN_1600"
                    exit_time = rbar_time
                    break

                if direction == 1:
                    # Check SL hit (use low)
                    if cfg.use_trailing:
                        # Track best price
                        best_price = max(best_price, rbar["high"])
                        profit_ticks = (best_price - entry_price) / TICK_SIZE
                        if profit_ticks >= cfg.trail_activate_ticks:
                            # Trailing active: SL = best_price - trail_offset
                            trail_sl = best_price - cfg.trail_offset_ticks * TICK_SIZE
                            # But also keep original SL as floor initially, then BE
                            be_sl = entry_price  # breakeven after activation
                            effective_sl = max(trail_sl, be_sl)
                        else:
                            effective_sl = entry_price - sl_pts

                        if rbar["low"] <= effective_sl:
                            exit_price = effective_sl - SLIPPAGE_PTS
                            if profit_ticks >= cfg.trail_activate_ticks:
                                exit_reason = "TRAIL_SL"
                            else:
                                exit_reason = "SL"
                            exit_time = rbar_time
                            break
                    else:
                        sl_price = entry_price - sl_pts
                        if rbar["low"] <= sl_price:
                            exit_price = sl_price - SLIPPAGE_PTS
                            exit_reason = "SL"
                            exit_time = rbar_time
                            break

                    # Check TP hit (use high)
                    tp_price = entry_price + tp_pts
                    if rbar["high"] >= tp_price:
                        exit_price = tp_price - SLIPPAGE_PTS
                        exit_reason = "TP"
                        exit_time = rbar_time
                        break
                else:  # short
                    if cfg.use_trailing:
                        best_price = min(best_price, rbar["low"])
                        profit_ticks = (entry_price - best_price) / TICK_SIZE
                        if profit_ticks >= cfg.trail_activate_ticks:
                            trail_sl = best_price + cfg.trail_offset_ticks * TICK_SIZE
                            be_sl = entry_price
                            effective_sl = min(trail_sl, be_sl)
                        else:
                            effective_sl = entry_price + sl_pts

                        if rbar["high"] >= effective_sl:
                            exit_price = effective_sl + SLIPPAGE_PTS
                            if profit_ticks >= cfg.trail_activate_ticks:
                                exit_reason = "TRAIL_SL"
                            else:
                                exit_reason = "SL"
                            exit_time = rbar_time
                            break
                    else:
                        sl_price = entry_price + sl_pts
                        if rbar["high"] >= sl_price:
                            exit_price = sl_price + SLIPPAGE_PTS
                            exit_reason = "SL"
                            exit_time = rbar_time
                            break

                    tp_price = entry_price - tp_pts
                    if rbar["low"] <= tp_price:
                        exit_price = tp_price + SLIPPAGE_PTS
                        exit_reason = "TP"
                        exit_time = rbar_time
                        break

            # If no exit yet, flatten at last bar
            if exit_price is None:
                last_bar = day_bars.iloc[-1]
                exit_price = last_bar["close"] - direction * SLIPPAGE_PTS
                exit_reason = "EOD"
                exit_time = last_bar["ts_event"]

            pnl_pts = direction * (exit_price - entry_price)
            pnl_dollar = pnl_pts * POINT_VALUE - COMM_RT

            trade = Trade(
                date=date,
                direction=direction,
                entry_price=entry_price,
                entry_time=bar_time,
                exit_price=exit_price,
                exit_time=exit_time,
                exit_reason=exit_reason,
                pnl_pts=pnl_pts,
                pnl_dollar=pnl_dollar,
            )
            trades.append(trade)

            # Update loss streak
            if cfg.use_loss_breaker:
                if pnl_dollar < 0:
                    consecutive_losses += 1
                    if consecutive_losses >= cfg.loss_streak_trigger:
                        # Skip next N calendar days
                        skip_until_idx = dates.index(date) + cfg.skip_days_after
                        if skip_until_idx < len(dates):
                            skip_until_date = dates[skip_until_idx]
                        consecutive_losses = 0
                else:
                    consecutive_losses = 0

    return trades


# ── Analytics ──────────────────────────────────────────────────────────────
def analyze_trades(trades, label=""):
    if not trades:
        return {
            "label": label, "trades": 0, "pnl": 0, "wr": 0, "pf": 0,
            "sharpe": 0, "max_dd": 0, "avg_win": 0, "avg_loss": 0,
        }

    pnls = [t.pnl_dollar for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)
    wr = len(wins) / len(pnls) * 100 if pnls else 0
    gross_win = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0.01
    pf = gross_win / gross_loss if gross_loss > 0 else 999.0

    # Sharpe (daily PnL)
    pnl_arr = np.array(pnls)
    sharpe = (pnl_arr.mean() / pnl_arr.std() * np.sqrt(252)) if len(pnl_arr) > 1 and pnl_arr.std() > 0 else 0

    # Max DD
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = cum - peak
    max_dd = abs(dd.min()) if len(dd) > 0 else 0

    return {
        "label": label,
        "trades": len(trades),
        "pnl": total_pnl,
        "wr": wr,
        "pf": pf,
        "sharpe": sharpe,
        "max_dd": max_dd,
        "avg_win": np.mean(wins) if wins else 0,
        "avg_loss": np.mean(losses) if losses else 0,
    }


def monthly_breakdown(trades):
    if not trades:
        return ""
    by_month = {}
    for t in trades:
        key = f"{t.date.year}-{t.date.month:02d}" if hasattr(t.date, 'year') else str(t.date)[:7]
        by_month.setdefault(key, []).append(t)

    lines = []
    for month in sorted(by_month.keys()):
        mt = by_month[month]
        pnl = sum(t.pnl_dollar for t in mt)
        w = sum(1 for t in mt if t.pnl_dollar > 0)
        lines.append(f"    {month}: {len(mt):2d} trades, PnL ${pnl:+,.0f}, WR {w/len(mt)*100:.0f}%")
    return "\n".join(lines)


# ── Walk-Forward ───────────────────────────────────────────────────────────
def walk_forward(bars_30m, cfg: StrategyConfig, is_days=40, oos_days=20):
    """Simple rolling walk-forward: IS window trains (just runs), OOS validates."""
    dates = sorted(bars_30m["date"].unique())
    results = []
    i = 0
    while i + is_days + oos_days <= len(dates):
        is_start = dates[i]
        is_end = dates[i + is_days - 1]
        oos_start = dates[i + is_days]
        oos_end = dates[i + is_days + oos_days - 1]

        is_trades = run_strategy(bars_30m, cfg, start_date=is_start, end_date=is_end)
        oos_trades = run_strategy(bars_30m, cfg, start_date=oos_start, end_date=oos_end)

        is_stats = analyze_trades(is_trades, "IS")
        oos_stats = analyze_trades(oos_trades, "OOS")

        results.append({
            "window": f"{is_start}→{oos_end}",
            "is_pnl": is_stats["pnl"],
            "is_trades": is_stats["trades"],
            "is_wr": is_stats["wr"],
            "oos_pnl": oos_stats["pnl"],
            "oos_trades": oos_stats["trades"],
            "oos_wr": oos_stats["wr"],
        })
        i += oos_days  # step by OOS window

    return results


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("Loading data...")
    df_1m = load_data()
    print(f"  {len(df_1m)} 1-min bars loaded")

    print("Resampling to 30m...")
    bars_30m = resample_30m(df_1m)
    print(f"  {len(bars_30m)} 30-min bars")

    # Define all configurations
    configs = {
        "A": StrategyConfig(name="A. Baseline (SL=160, TP=560)"),
        "B": StrategyConfig(name="B. ATR stops only", use_atr_stops=True),
        "C": StrategyConfig(name="C. Regime filter only", use_regime_filter=True),
        "D": StrategyConfig(name="D. Trailing stop only", use_trailing=True),
        "E": StrategyConfig(name="E. Time 9:30-11:00 only", use_time_filter=True),
        "F": StrategyConfig(name="F. Loss breaker only", use_loss_breaker=True),
        "G": StrategyConfig(name="G. ATR + regime", use_atr_stops=True, use_regime_filter=True),
        "H": StrategyConfig(name="H. ATR + trailing", use_atr_stops=True, use_trailing=True),
        "I": StrategyConfig(name="I. Regime + trailing + time",
                            use_regime_filter=True, use_trailing=True, use_time_filter=True),
        "J": StrategyConfig(name="J. Regime + trailing + loss breaker",
                            use_regime_filter=True, use_trailing=True, use_loss_breaker=True),
        "K": StrategyConfig(name="K. ALL combined",
                            use_atr_stops=True, use_regime_filter=True, use_trailing=True,
                            use_time_filter=True, use_loss_breaker=True, use_direction_filter=True),
    }

    # Also test E2: 9:30-12:00
    configs["E2"] = StrategyConfig(name="E2. Time 9:30-12:00 only", use_time_filter=True,
                                    entry_end_hour=12, entry_end_min=0)

    # Run all
    all_results = {}
    all_trades = {}
    for key in ["A", "B", "C", "D", "E", "E2", "F", "G", "H", "I", "J", "K"]:
        cfg = configs[key]
        print(f"Running {cfg.name}...")
        trades = run_strategy(bars_30m, cfg)
        stats = analyze_trades(trades, cfg.name)
        all_results[key] = stats
        all_trades[key] = trades

    # Determine best 3 features for combo L
    # Score by: PnL improvement over baseline, but also check PF and Sharpe
    baseline_pnl = all_results["A"]["pnl"]
    feature_scores = {}
    single_features = {"B": "ATR", "C": "regime", "D": "trailing", "E": "time_1100",
                       "E2": "time_1200", "F": "loss_breaker"}
    for key, fname in single_features.items():
        r = all_results[key]
        # Composite score: PnL improvement + PF bonus + Sharpe bonus
        pnl_delta = r["pnl"] - baseline_pnl
        score = pnl_delta + r["pf"] * 500 + r["sharpe"] * 200
        feature_scores[key] = score

    # Pick top 3 features
    ranked = sorted(feature_scores.items(), key=lambda x: x[1], reverse=True)
    top3_keys = [r[0] for r in ranked[:3]]
    top3_names = [single_features[k] for k in top3_keys]

    print(f"\nTop 3 features by composite score: {top3_names}")

    # Build combo L
    cfg_l = StrategyConfig(name=f"L. Best 3: {'+'.join(top3_names)}")
    for k in top3_keys:
        if k == "B":
            cfg_l.use_atr_stops = True
        elif k == "C":
            cfg_l.use_regime_filter = True
        elif k == "D":
            cfg_l.use_trailing = True
        elif k == "E":
            cfg_l.use_time_filter = True
            cfg_l.entry_end_hour = 11
        elif k == "E2":
            cfg_l.use_time_filter = True
            cfg_l.entry_end_hour = 12
        elif k == "F":
            cfg_l.use_loss_breaker = True

    print(f"Running {cfg_l.name}...")
    trades_l = run_strategy(bars_30m, cfg_l)
    stats_l = analyze_trades(trades_l, cfg_l.name)
    all_results["L"] = stats_l
    all_trades["L"] = trades_l

    # ── Output Report ──────────────────────────────────────────────────────
    out = io.StringIO()

    out.write("=" * 100 + "\n")
    out.write("OPT7 — COMBINED STRATEGY OPTIMIZATION: ChNavy6 VWAP Bounce\n")
    out.write("=" * 100 + "\n\n")

    # Comparison table
    out.write(f"{'Combo':<45} {'Trades':>6} {'PnL':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>9} {'AvgWin':>8} {'AvgLoss':>8}\n")
    out.write("-" * 100 + "\n")

    display_order = ["A", "B", "C", "D", "E", "E2", "F", "G", "H", "I", "J", "K", "L"]
    for key in display_order:
        r = all_results[key]
        out.write(f"{r['label']:<45} {r['trades']:>6} ${r['pnl']:>+9,.0f} {r['wr']:>5.1f}% {r['pf']:>5.2f} {r['sharpe']:>+7.2f} ${r['max_dd']:>8,.0f} ${r['avg_win']:>7,.0f} ${r['avg_loss']:>7,.0f}\n")

    out.write("\n")

    # Rank by PnL
    out.write("RANKING BY PnL:\n")
    ranked_pnl = sorted(all_results.items(), key=lambda x: x[1]["pnl"], reverse=True)
    for i, (key, r) in enumerate(ranked_pnl, 1):
        delta = r["pnl"] - baseline_pnl
        out.write(f"  {i:>2}. {r['label']:<45} ${r['pnl']:>+9,.0f}  (delta: ${delta:>+8,.0f})\n")

    out.write("\n")

    # Rank by Sharpe
    out.write("RANKING BY SHARPE:\n")
    ranked_sharpe = sorted(all_results.items(), key=lambda x: x[1]["sharpe"], reverse=True)
    for i, (key, r) in enumerate(ranked_sharpe, 1):
        out.write(f"  {i:>2}. {r['label']:<45} Sharpe: {r['sharpe']:>+.2f}\n")

    out.write("\n")

    # Monthly breakdown for top 3 by PnL
    out.write("=" * 100 + "\n")
    out.write("MONTHLY BREAKDOWN — TOP 3 BY PnL\n")
    out.write("=" * 100 + "\n")
    for i, (key, r) in enumerate(ranked_pnl[:3], 1):
        out.write(f"\n#{i} {r['label']}  (Total: ${r['pnl']:+,.0f})\n")
        out.write(monthly_breakdown(all_trades[key]) + "\n")

    # Walk-forward on best combo
    best_key = ranked_pnl[0][0]
    best_cfg = configs.get(best_key, cfg_l)
    if best_key == "L":
        best_cfg = cfg_l

    out.write("\n" + "=" * 100 + "\n")
    out.write(f"WALK-FORWARD VALIDATION — {all_results[best_key]['label']}\n")
    out.write(f"  (40-day IS / 20-day OOS, rolling)\n")
    out.write("=" * 100 + "\n\n")

    print(f"Running walk-forward on {best_cfg.name}...")
    wf_results = walk_forward(bars_30m, best_cfg)

    total_is_pnl = 0
    total_oos_pnl = 0
    oos_positive = 0

    out.write(f"{'Window':<40} {'IS Trades':>9} {'IS PnL':>10} {'IS WR':>7} {'OOS Trades':>10} {'OOS PnL':>10} {'OOS WR':>7}\n")
    out.write("-" * 100 + "\n")
    for wf in wf_results:
        out.write(f"{wf['window']:<40} {wf['is_trades']:>9} ${wf['is_pnl']:>+9,.0f} {wf['is_wr']:>6.1f}% {wf['oos_trades']:>10} ${wf['oos_pnl']:>+9,.0f} {wf['oos_wr']:>6.1f}%\n")
        total_is_pnl += wf["is_pnl"]
        total_oos_pnl += wf["oos_pnl"]
        if wf["oos_pnl"] > 0:
            oos_positive += 1

    out.write("-" * 100 + "\n")
    out.write(f"{'TOTALS':<40} {'':>9} ${total_is_pnl:>+9,.0f} {'':>7} {'':>10} ${total_oos_pnl:>+9,.0f}\n")
    out.write(f"\nOOS windows positive: {oos_positive}/{len(wf_results)}\n")
    out.write(f"IS/OOS PnL ratio: {total_oos_pnl/total_is_pnl:.2f}x\n" if total_is_pnl != 0 else "")

    if total_oos_pnl > 0 and oos_positive >= len(wf_results) * 0.5:
        out.write("\n>>> VERDICT: Strategy shows ROBUSTNESS — OOS is profitable and consistent.\n")
    elif total_oos_pnl > 0:
        out.write("\n>>> VERDICT: OOS profitable but inconsistent — possible overfit on some windows.\n")
    else:
        out.write("\n>>> VERDICT: OOS negative — likely OVERFIT. Use simpler combination.\n")

    # Also walk-forward on baseline for comparison
    out.write(f"\n{'─'*100}\n")
    out.write("WALK-FORWARD COMPARISON — Baseline (A)\n\n")
    baseline_cfg = configs["A"]
    wf_base = walk_forward(bars_30m, baseline_cfg)
    base_oos_pnl = sum(w["oos_pnl"] for w in wf_base)
    base_oos_pos = sum(1 for w in wf_base if w["oos_pnl"] > 0)
    out.write(f"  Baseline OOS total: ${base_oos_pnl:>+,.0f}  ({base_oos_pos}/{len(wf_base)} windows positive)\n")
    out.write(f"  Best combo OOS total: ${total_oos_pnl:>+,.0f}  ({oos_positive}/{len(wf_results)} windows positive)\n")

    # Direction filter stats
    if "K" in all_trades:
        k_trades = all_trades["K"]
        if k_trades:
            out.write(f"\n{'─'*100}\n")
            out.write("DIRECTION FILTER IMPACT (Combo K - ALL):\n")
            longs = [t for t in k_trades if t.direction == 1]
            shorts = [t for t in k_trades if t.direction == -1]
            out.write(f"  Longs:  {len(longs)} trades, PnL ${sum(t.pnl_dollar for t in longs):+,.0f}\n")
            out.write(f"  Shorts: {len(shorts)} trades, PnL ${sum(t.pnl_dollar for t in shorts):+,.0f}\n")

    out.write("\n" + "=" * 100 + "\n")
    out.write("END OF REPORT\n")
    out.write("=" * 100 + "\n")

    report = out.getvalue()
    print(report)

    OUT_PATH.write_text(report)
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
