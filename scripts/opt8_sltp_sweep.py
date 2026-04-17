#!/usr/bin/env python3
"""
opt8_sltp_sweep.py — Exhaustive SL/TP/bounce/session-window sweep for ChNavy6 VWAP Bounce.
6,480 parameter combinations on 96,100 1-min bars (Jan 2 – Apr 10, 2026).
"""

import csv
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import product
from zoneinfo import ZoneInfo

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
SLIPPAGE = SLIPPAGE_TICKS * TICK_SIZE  # 0.25 pts
COMMISSION_RT = COMMISSION_PER_SIDE * 2  # 0.70 round trip
FLATTEN_HOUR = 16  # flatten at 16:00 ET

ET = ZoneInfo("US/Eastern")

# ── Parameter grid ─────────────────────────────────────────────────────────
SL_TICKS = [60, 80, 100, 120, 140, 160, 180, 200, 240, 280, 320, 400]
TP_TICKS = [120, 160, 200, 240, 280, 320, 400, 480, 560, 640, 800, 1000]
BOUNCE_CONFIRM_TICKS = [10, 20, 40]
START_HOURS = [9.0, 9.5, 10.0]
END_HOURS = [11.0, 12.0, 13.0, 14.0, 14.5]

DATA_PATH = "/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv"
OUT_PATH  = "/Users/teaceo/DEEP6/scripts/opt8_sltp_sweep.txt"


def load_1m_bars():
    """Load CSV into list of dicts, convert ts to ET datetime."""
    bars = []
    with open(DATA_PATH, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row["ts_event"]
            # Parse UTC timestamp
            if "+" in ts_str:
                dt_utc = datetime.fromisoformat(ts_str)
            else:
                from zoneinfo import ZoneInfo as ZI
                dt_utc = datetime.fromisoformat(ts_str).replace(tzinfo=ZI("UTC"))
            dt_et = dt_utc.astimezone(ET)
            bars.append({
                "dt": dt_et,
                "date": dt_et.date(),
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
                "v": int(row["volume"]),
            })
    return bars


def resample_30m(bars_1m):
    """Resample 1-min bars to 30-min bars, grouped by calendar date in ET."""
    by_date = defaultdict(list)
    for b in bars_1m:
        by_date[b["date"]].append(b)

    all_30m = {}  # date -> list of 30m bars
    for date, day_bars in sorted(by_date.items()):
        # Group by 30-min bucket
        buckets = defaultdict(list)
        for b in day_bars:
            # Bucket key: hour + (minute // 30) * 30
            bucket_min = (b["dt"].minute // 30) * 30
            bucket_key = b["dt"].replace(minute=bucket_min, second=0, microsecond=0)
            buckets[bucket_key].append(b)

        bars_30m = []
        for bk in sorted(buckets.keys()):
            bb = buckets[bk]
            bars_30m.append({
                "dt": bk,
                "date": date,
                "o": bb[0]["o"],
                "h": max(x["h"] for x in bb),
                "l": min(x["l"] for x in bb),
                "c": bb[-1]["c"],
                "v": sum(x["v"] for x in bb),
            })
        all_30m[date] = bars_30m

    return all_30m, by_date


def run_single_config(all_30m, by_date_1m, sl_ticks, tp_ticks, bounce_ticks, start_h, end_h):
    """Run one config. Returns (trades_list, metrics_dict)."""
    sl_pts = sl_ticks * TICK_SIZE
    tp_pts = tp_ticks * TICK_SIZE
    bounce_pts = bounce_ticks * TICK_SIZE

    trades = []

    for date in sorted(all_30m.keys()):
        bars = all_30m[date]
        if len(bars) < 2:
            continue

        # Build VWAP bar-by-bar
        cum_tv = 0.0
        cum_v = 0
        vwap_prev = None
        close_prev = None
        traded_today = False

        for i, bar in enumerate(bars):
            typical = (bar["h"] + bar["l"] + bar["c"]) / 3.0
            cum_tv += typical * bar["v"]
            cum_v += bar["v"]
            vwap = cum_tv / cum_v if cum_v > 0 else bar["c"]

            if i == 0:
                vwap_prev = vwap
                close_prev = bar["c"]
                continue

            if traded_today:
                vwap_prev = vwap
                close_prev = bar["c"]
                continue

            bar_hour = bar["dt"].hour + bar["dt"].minute / 60.0
            if bar_hour < start_h or bar_hour >= end_h:
                vwap_prev = vwap
                close_prev = bar["c"]
                continue

            # Check cross conditions
            was_below = close_prev < vwap_prev
            was_above = close_prev > vwap_prev
            direction = 0

            if was_below and bar["c"] > vwap and (bar["c"] - vwap) >= bounce_pts:
                direction = 1  # Long
            elif was_above and bar["c"] < vwap and (vwap - bar["c"]) >= bounce_pts:
                direction = -1  # Short

            if direction != 0:
                traded_today = True
                if direction == 1:
                    entry = bar["c"] + SLIPPAGE
                    stop = entry - sl_pts
                    target = entry + tp_pts
                else:
                    entry = bar["c"] - SLIPPAGE
                    stop = entry + sl_pts
                    target = entry - tp_pts

                # Walk forward through 1-min bars for exit
                day_1m = by_date_1m.get(date, [])
                entry_time = bar["dt"] + timedelta(minutes=30)  # next bar after signal bar close
                exit_price = None
                exit_time = None
                exit_reason = None

                for m_bar in day_1m:
                    if m_bar["dt"] < entry_time:
                        continue
                    # Check flatten
                    if m_bar["dt"].hour >= FLATTEN_HOUR:
                        exit_price = m_bar["c"]
                        exit_time = m_bar["dt"]
                        exit_reason = "FLATTEN"
                        break

                    if direction == 1:
                        # Check stop first (conservative)
                        if m_bar["l"] <= stop:
                            exit_price = stop
                            exit_time = m_bar["dt"]
                            exit_reason = "STOP"
                            break
                        if m_bar["h"] >= target:
                            exit_price = target
                            exit_time = m_bar["dt"]
                            exit_reason = "TARGET"
                            break
                    else:  # short
                        if m_bar["h"] >= stop:
                            exit_price = stop
                            exit_time = m_bar["dt"]
                            exit_reason = "STOP"
                            break
                        if m_bar["l"] <= target:
                            exit_price = target
                            exit_time = m_bar["dt"]
                            exit_reason = "TARGET"
                            break

                if exit_price is None:
                    # Use last bar of day
                    if day_1m:
                        exit_price = day_1m[-1]["c"]
                        exit_time = day_1m[-1]["dt"]
                        exit_reason = "EOD"
                    else:
                        continue

                pnl_pts = (exit_price - entry) * direction
                pnl_dollar = pnl_pts / TICK_SIZE * TICK_VALUE - COMMISSION_RT

                trades.append({
                    "date": date,
                    "dir": direction,
                    "entry": entry,
                    "exit": exit_price,
                    "entry_time": bar["dt"],
                    "exit_time": exit_time,
                    "reason": exit_reason,
                    "pnl_pts": pnl_pts,
                    "pnl": pnl_dollar,
                })

            vwap_prev = vwap
            close_prev = bar["c"]

    # Compute metrics
    if not trades:
        return trades, None

    net_pnl = sum(t["pnl"] for t in trades)
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    wr = len(wins) / n * 100 if n > 0 else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else 999.0
    max_dd = 0
    peak = 0
    equity = 0
    for t in trades:
        equity += t["pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Sharpe (daily returns)
    daily_pnl = defaultdict(float)
    for t in trades:
        daily_pnl[t["date"]] += t["pnl"]
    returns = list(daily_pnl.values())
    if len(returns) > 1:
        import statistics
        mean_r = statistics.mean(returns)
        std_r = statistics.stdev(returns)
        sharpe = (mean_r / std_r) * (252 ** 0.5) if std_r > 0 else 0
    else:
        sharpe = 0

    metrics = {
        "net_pnl": net_pnl,
        "trades": n,
        "win_rate": wr,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "max_dd": max_dd,
        "sharpe": sharpe,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
    }
    return trades, metrics


def main():
    t0 = time.time()
    print("Loading 1-min bars...")
    bars_1m = load_1m_bars()
    print(f"  Loaded {len(bars_1m):,} bars in {time.time()-t0:.1f}s")

    print("Resampling to 30-min...")
    all_30m, by_date_1m = resample_30m(bars_1m)
    print(f"  {len(all_30m)} trading days")

    combos = list(product(SL_TICKS, TP_TICKS, BOUNCE_CONFIRM_TICKS, START_HOURS, END_HOURS))
    total = len(combos)
    print(f"Running {total:,} parameter combinations...")

    results = []
    best_pnl = -999999
    milestone = total // 20  # 5% increments

    for idx, (sl, tp, bc, sh, eh) in enumerate(combos):
        trades, metrics = run_single_config(all_30m, by_date_1m, sl, tp, bc, sh, eh)
        if metrics:
            config = {
                "sl": sl, "tp": tp, "bounce": bc, "start_h": sh, "end_h": eh,
                "rr": round(tp / sl, 2),
            }
            results.append((config, metrics, trades))
            if metrics["net_pnl"] > best_pnl:
                best_pnl = metrics["net_pnl"]

        if milestone > 0 and (idx + 1) % milestone == 0:
            pct = (idx + 1) / total * 100
            print(f"  {pct:.0f}% ({idx+1}/{total}) — best PnL so far: ${best_pnl:,.0f}")

    elapsed = time.time() - t0
    print(f"\nDone. {len(results)} configs with trades. Total time: {elapsed:.1f}s")

    # Sort for rankings
    by_pnl = sorted(results, key=lambda x: x[1]["net_pnl"], reverse=True)
    by_sharpe = sorted([r for r in results if r[1]["trades"] >= 20],
                       key=lambda x: x[1]["sharpe"], reverse=True)
    by_pf = sorted([r for r in results if r[1]["trades"] >= 20],
                   key=lambda x: x[1]["profit_factor"], reverse=True)

    # ── Write report ──────────────────────────────────────────────────────
    with open(OUT_PATH, "w") as f:
        f.write("=" * 120 + "\n")
        f.write("OPT8: EXHAUSTIVE SL/TP SWEEP — ChNavy6 VWAP BOUNCE (30m)\n")
        f.write(f"Data: 96,100 1-min bars, Jan 2 – Apr 10, 2026 ({len(all_30m)} trading days)\n")
        f.write(f"Combinations: {total:,} | Configs with trades: {len(results)}\n")
        f.write(f"Elapsed: {elapsed:.1f}s\n")
        f.write("=" * 120 + "\n\n")

        # 1. Top 20 by Net PnL
        f.write("─" * 120 + "\n")
        f.write("1. TOP 20 CONFIGS BY NET PnL\n")
        f.write("─" * 120 + "\n")
        hdr = f"{'Rank':>4} {'SL':>4} {'TP':>5} {'R:R':>5} {'Bnc':>4} {'Start':>5} {'End':>5} {'Net PnL':>10} {'Trades':>6} {'WR%':>6} {'AvgWin':>8} {'AvgLoss':>8} {'PF':>6} {'MaxDD':>8} {'Sharpe':>7}"
        f.write(hdr + "\n")
        for i, (cfg, met, _) in enumerate(by_pnl[:20]):
            line = f"{i+1:>4} {cfg['sl']:>4} {cfg['tp']:>5} {cfg['rr']:>5} {cfg['bounce']:>4} {cfg['start_h']:>5.1f} {cfg['end_h']:>5.1f} ${met['net_pnl']:>9,.0f} {met['trades']:>6} {met['win_rate']:>5.1f}% ${met['avg_win']:>7,.0f} ${met['avg_loss']:>7,.0f} {met['profit_factor']:>5.2f} ${met['max_dd']:>7,.0f} {met['sharpe']:>7.2f}"
            f.write(line + "\n")
        f.write("\n")

        # 2. Top 20 by Sharpe (min 20 trades)
        f.write("─" * 120 + "\n")
        f.write("2. TOP 20 CONFIGS BY SHARPE RATIO (min 20 trades)\n")
        f.write("─" * 120 + "\n")
        f.write(hdr + "\n")
        for i, (cfg, met, _) in enumerate(by_sharpe[:20]):
            line = f"{i+1:>4} {cfg['sl']:>4} {cfg['tp']:>5} {cfg['rr']:>5} {cfg['bounce']:>4} {cfg['start_h']:>5.1f} {cfg['end_h']:>5.1f} ${met['net_pnl']:>9,.0f} {met['trades']:>6} {met['win_rate']:>5.1f}% ${met['avg_win']:>7,.0f} ${met['avg_loss']:>7,.0f} {met['profit_factor']:>5.2f} ${met['max_dd']:>7,.0f} {met['sharpe']:>7.2f}"
            f.write(line + "\n")
        f.write("\n")

        # 3. Top 20 by Profit Factor (min 20 trades)
        f.write("─" * 120 + "\n")
        f.write("3. TOP 20 CONFIGS BY PROFIT FACTOR (min 20 trades)\n")
        f.write("─" * 120 + "\n")
        f.write(hdr + "\n")
        for i, (cfg, met, _) in enumerate(by_pf[:20]):
            line = f"{i+1:>4} {cfg['sl']:>4} {cfg['tp']:>5} {cfg['rr']:>5} {cfg['bounce']:>4} {cfg['start_h']:>5.1f} {cfg['end_h']:>5.1f} ${met['net_pnl']:>9,.0f} {met['trades']:>6} {met['win_rate']:>5.1f}% ${met['avg_win']:>7,.0f} ${met['avg_loss']:>7,.0f} {met['profit_factor']:>5.2f} ${met['max_dd']:>7,.0f} {met['sharpe']:>7.2f}"
            f.write(line + "\n")
        f.write("\n")

        # 4. Heatmap: best TP per SL
        f.write("─" * 120 + "\n")
        f.write("4. SL/TP HEATMAP — Best TP for each SL (across all bounce/session combos)\n")
        f.write("─" * 120 + "\n")

        # Also build full SL x TP matrix (best PnL across bounce/session params)
        sl_tp_best = {}
        for cfg, met, _ in results:
            key = (cfg["sl"], cfg["tp"])
            if key not in sl_tp_best or met["net_pnl"] > sl_tp_best[key]["net_pnl"]:
                sl_tp_best[key] = {**met, **cfg}

        # Per-SL best
        f.write(f"\n{'SL':>5} {'BestTP':>6} {'R:R':>5} {'Net PnL':>10} {'Trades':>6} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'Bnc':>4} {'Start':>5} {'End':>5}\n")
        for sl in SL_TICKS:
            best = None
            for cfg, met, _ in results:
                if cfg["sl"] == sl:
                    if best is None or met["net_pnl"] > best[1]["net_pnl"]:
                        best = (cfg, met)
            if best:
                cfg, met = best
                f.write(f"{sl:>5} {cfg['tp']:>6} {cfg['rr']:>5} ${met['net_pnl']:>9,.0f} {met['trades']:>6} {met['win_rate']:>5.1f}% {met['profit_factor']:>5.2f} {met['sharpe']:>7.2f} {cfg['bounce']:>4} {cfg['start_h']:>5.1f} {cfg['end_h']:>5.1f}\n")

        # Full SL x TP grid
        f.write(f"\nFull SL x TP PnL grid (best across all bounce/session combos):\n")
        f.write(f"{'SL\\TP':>6}")
        for tp in TP_TICKS:
            f.write(f" {tp:>7}")
        f.write("\n")
        for sl in SL_TICKS:
            f.write(f"{sl:>6}")
            for tp in TP_TICKS:
                key = (sl, tp)
                if key in sl_tp_best:
                    val = sl_tp_best[key]["net_pnl"]
                    f.write(f" {val:>7.0f}")
                else:
                    f.write(f" {'---':>7}")
            f.write("\n")
        f.write("\n")

        # 5. Trade-by-trade for #1 config
        f.write("─" * 120 + "\n")
        f.write("5. TRADE-BY-TRADE DETAIL — #1 CONFIG BY NET PnL\n")
        f.write("─" * 120 + "\n")
        if by_pnl:
            top_cfg, top_met, top_trades = by_pnl[0]
            f.write(f"Config: SL={top_cfg['sl']} TP={top_cfg['tp']} R:R={top_cfg['rr']} Bounce={top_cfg['bounce']} Start={top_cfg['start_h']} End={top_cfg['end_h']}\n")
            f.write(f"{'#':>3} {'Date':>12} {'Dir':>5} {'Entry':>10} {'Exit':>10} {'Reason':>8} {'PnL pts':>8} {'PnL $':>9} {'Cum $':>10}\n")
            cum = 0
            for i, t in enumerate(top_trades):
                cum += t["pnl"]
                d = "LONG" if t["dir"] == 1 else "SHORT"
                f.write(f"{i+1:>3} {str(t['date']):>12} {d:>5} {t['entry']:>10.2f} {t['exit']:>10.2f} {t['reason']:>8} {t['pnl_pts']:>8.2f} ${t['pnl']:>8,.0f} ${cum:>9,.0f}\n")
        f.write("\n")

        # 6. Monthly breakdown for top 3
        f.write("─" * 120 + "\n")
        f.write("6. MONTHLY BREAKDOWN — TOP 3 CONFIGS BY NET PnL\n")
        f.write("─" * 120 + "\n")
        for rank, (cfg, met, trades) in enumerate(by_pnl[:3]):
            f.write(f"\n  #{rank+1}: SL={cfg['sl']} TP={cfg['tp']} R:R={cfg['rr']} Bounce={cfg['bounce']} Start={cfg['start_h']} End={cfg['end_h']}\n")
            monthly = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
            for t in trades:
                mk = t["date"].strftime("%Y-%m")
                monthly[mk]["pnl"] += t["pnl"]
                monthly[mk]["trades"] += 1
                if t["pnl"] > 0:
                    monthly[mk]["wins"] += 1
            f.write(f"  {'Month':>8} {'PnL':>10} {'Trades':>7} {'WR%':>6}\n")
            for mk in sorted(monthly.keys()):
                m = monthly[mk]
                wr = m["wins"] / m["trades"] * 100 if m["trades"] > 0 else 0
                f.write(f"  {mk:>8} ${m['pnl']:>9,.0f} {m['trades']:>7} {wr:>5.1f}%\n")
            f.write(f"  {'TOTAL':>8} ${met['net_pnl']:>9,.0f} {met['trades']:>7} {met['win_rate']:>5.1f}%\n")
        f.write("\n")

        # 7. R:R ratio clustering
        f.write("─" * 120 + "\n")
        f.write("7. R:R RATIO CLUSTERING — WHICH RATIOS WIN?\n")
        f.write("─" * 120 + "\n")
        rr_stats = defaultdict(lambda: {"count": 0, "total_pnl": 0, "best_pnl": -999999, "pos": 0})
        for cfg, met, _ in results:
            rr = cfg["rr"]
            rr_stats[rr]["count"] += 1
            rr_stats[rr]["total_pnl"] += met["net_pnl"]
            if met["net_pnl"] > rr_stats[rr]["best_pnl"]:
                rr_stats[rr]["best_pnl"] = met["net_pnl"]
            if met["net_pnl"] > 0:
                rr_stats[rr]["pos"] += 1

        f.write(f"{'R:R':>6} {'Configs':>8} {'Profitable':>11} {'%Pos':>6} {'AvgPnL':>10} {'BestPnL':>10}\n")
        for rr in sorted(rr_stats.keys()):
            s = rr_stats[rr]
            avg = s["total_pnl"] / s["count"]
            pct = s["pos"] / s["count"] * 100
            f.write(f"{rr:>6.2f} {s['count']:>8} {s['pos']:>11} {pct:>5.1f}% ${avg:>9,.0f} ${s['best_pnl']:>9,.0f}\n")
        f.write("\n")

        # Baseline comparison
        f.write("─" * 120 + "\n")
        f.write("BASELINE COMPARISON\n")
        f.write("─" * 120 + "\n")
        baseline = None
        for cfg, met, _ in results:
            if cfg["sl"] == 160 and cfg["tp"] == 560:
                if baseline is None or met["net_pnl"] > baseline[1]["net_pnl"]:
                    baseline = (cfg, met)
        if baseline:
            cfg, met = baseline
            f.write(f"Baseline (SL=160, TP=560): Bounce={cfg['bounce']} Start={cfg['start_h']} End={cfg['end_h']}\n")
            f.write(f"  Net PnL: ${met['net_pnl']:,.0f} | Trades: {met['trades']} | WR: {met['win_rate']:.1f}% | PF: {met['profit_factor']:.2f} | MaxDD: ${met['max_dd']:,.0f} | Sharpe: {met['sharpe']:.2f}\n")
        if by_pnl:
            cfg, met = by_pnl[0][0], by_pnl[0][1]
            f.write(f"\nBest found (SL={cfg['sl']}, TP={cfg['tp']}): Bounce={cfg['bounce']} Start={cfg['start_h']} End={cfg['end_h']}\n")
            f.write(f"  Net PnL: ${met['net_pnl']:,.0f} | Trades: {met['trades']} | WR: {met['win_rate']:.1f}% | PF: {met['profit_factor']:.2f} | MaxDD: ${met['max_dd']:,.0f} | Sharpe: {met['sharpe']:.2f}\n")
            if baseline:
                delta = by_pnl[0][1]["net_pnl"] - baseline[1]["net_pnl"]
                f.write(f"  Delta vs baseline: ${delta:+,.0f}\n")
        f.write("\n" + "=" * 120 + "\n")

    print(f"Results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
