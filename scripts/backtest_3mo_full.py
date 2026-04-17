"""
3-Month Deep Backtest — VWAP Strategies on 30-Min NQ Bars
Data: Databento NQ.c.0 OHLCV-1m, Jan 2 - Apr 10, 2026 (85 trading days)

Runs CHTrendNavy6 (best from 5-round optimization) with robust + aggressive configs,
plus ChNavy6 and Ch2Navy6 for comparison. Includes walk-forward and Monte Carlo.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from itertools import product
import random, sys, os

TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
CSV_PATH = "data/backtests/nq_3mo_1m.csv"

# ── load & resample ───────────────────────────────────────────────────────

def load_bars(tf_minutes: int = 30) -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "bar_ts"})
    df = df[["bar_ts", "open", "high", "low", "close", "volume"]].copy()

    # Convert UTC to ET (NQ trades on CME in CT but strategies use ET times)
    df["bar_ts"] = df["bar_ts"].dt.tz_convert("US/Eastern") if df["bar_ts"].dt.tz else df["bar_ts"]
    df = df.set_index("bar_ts")

    # Session = calendar date in ET
    df["session_date"] = df.index.date

    # Resample within each session
    frames = []
    for sd, grp in df.groupby("session_date"):
        r = grp.resample(f"{tf_minutes}min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum", "session_date": "first",
        }).dropna(subset=["open"])
        frames.append(r)

    bars = pd.concat(frames).sort_index()
    unique_dates = sorted(bars["session_date"].unique())
    date_to_id = {d: i for i, d in enumerate(unique_dates)}
    bars["session"] = bars["session_date"].map(date_to_id)
    bars = bars.reset_index()
    print(f"Loaded {len(bars)} {tf_minutes}-min bars across {len(unique_dates)} sessions")
    print(f"Date range: {unique_dates[0]} to {unique_dates[-1]}")
    return bars, unique_dates


# ── trade ─────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: object
    side: str
    entry_price: float
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    session_date: object = None

    def close(self, exit_price: float, reason: str):
        slip = SLIPPAGE_TICKS * TICK_SIZE
        if self.side == "LONG":
            self.exit_price = exit_price - slip
            self.pnl = (self.exit_price - self.entry_price) / TICK_SIZE * TICK_VALUE
        else:
            self.exit_price = exit_price + slip
            self.pnl = (self.entry_price - self.exit_price) / TICK_SIZE * TICK_VALUE
        self.pnl -= 2 * COMMISSION_PER_SIDE
        self.exit_reason = reason


# ── exit simulation ───────────────────────────────────────────────────────

def simulate_exit(bars, start_idx, trade, sl_px, tp_px, flatten_h, sess):
    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session"] != sess:
            prev_b = bars.iloc[j - 1]
            trade.close(prev_b["close"], "SESSION_END")
            return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN")
            return
        if trade.side == "LONG":
            if b["low"] <= sl_px:
                trade.close(sl_px, "STOP"); return
            if b["high"] >= tp_px:
                trade.close(tp_px, "TARGET"); return
        else:
            if b["high"] >= sl_px:
                trade.close(sl_px, "STOP"); return
            if b["low"] <= tp_px:
                trade.close(tp_px, "TARGET"); return
    trade.close(bars.iloc[-1]["close"], "DATA_END")


# ── CHTrendNavy6 ─────────────────────────────────────────────────────────

def run_chtrendnavy6(bars, sl_ticks, tp_ticks, slope_lb, pb_ticks,
                      start_h, end_h, flatten_h=16) -> list:
    trades = []
    cum_tpv = cum_vol = 0.0
    vwap_hist = []
    trade_taken = False
    prev_session = -1

    for i in range(2, len(bars)):
        row = bars.iloc[i]
        bar1 = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session"]

        if sess != prev_session:
            cum_tpv = cum_vol = 0.0
            vwap_hist = []
            trade_taken = False
            prev_session = sess

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        tpv1 = typical1 * bar1["volume"]
        cum_tpv += tpv1
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]
        vwap_hist.append(vwap_now)

        if trade_taken: continue
        if hour < start_h or hour > end_h: continue
        if len(vwap_hist) <= slope_lb: continue

        slope = vwap_hist[-1] - vwap_hist[-1 - slope_lb]
        band = pb_ticks * TICK_SIZE

        if slope > 0 and bar1["close"] > vwap_now and bar1["low"] <= vwap_now + band:
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i, t, entry_px - sl_ticks * TICK_SIZE,
                         entry_px + tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
        elif slope < 0 and bar1["close"] < vwap_now and bar1["high"] >= vwap_now - band:
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i, t, entry_px + sl_ticks * TICK_SIZE,
                         entry_px - tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
    return trades


# ── ChNavy6 ───────────────────────────────────────────────────────────────

def run_chnavy6(bars, sl_ticks, tp_ticks, bounce_ticks,
                start_h, end_h, flatten_h=16) -> list:
    trades = []
    cum_tpv = cum_vol = 0.0
    was_below = was_above = False
    trade_taken = False
    prev_session = -1

    for i in range(1, len(bars)):
        row = bars.iloc[i]
        prev = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session"]

        if sess != prev_session:
            cum_tpv = cum_vol = 0.0
            was_below = was_above = False
            trade_taken = False
            prev_session = sess

        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        tpv = typical * row["volume"]
        prior_vwap = cum_tpv / cum_vol if cum_vol > 0 else prev["close"]
        cum_tpv += tpv
        cum_vol += row["volume"]
        vwap = cum_tpv / cum_vol if cum_vol > 0 else row["close"]

        if trade_taken: continue
        if hour < start_h or hour > end_h: continue

        if prev["close"] < prior_vwap:
            was_below = True; was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True; was_below = False

        confirm = bounce_ticks * TICK_SIZE

        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i + 1, t, entry_px - sl_ticks * TICK_SIZE,
                         entry_px + tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i + 1, t, entry_px + sl_ticks * TICK_SIZE,
                         entry_px - tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
    return trades


# ── Ch2Navy6 ──────────────────────────────────────────────────────────────

def run_ch2navy6(bars, sl_ticks, tp_ticks, bounce_ticks,
                 start_h, end_h, flatten_h=16) -> list:
    trades = []
    cum_tpv = cum_vol = 0.0
    trade_taken = False
    prev_session = -1

    for i in range(2, len(bars)):
        row = bars.iloc[i]
        bar1 = bars.iloc[i - 1]
        bar2 = bars.iloc[i - 2]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session"]

        if sess != prev_session:
            cum_tpv = cum_vol = 0.0
            trade_taken = False
            prev_session = sess

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        tpv1 = typical1 * bar1["volume"]
        vwap_prior = cum_tpv / cum_vol if cum_vol > 0 else bar2["close"]
        cum_tpv += tpv1
        cum_vol += bar1["volume"]

        if trade_taken: continue
        if hour < start_h or hour > end_h: continue

        confirm = bounce_ticks * TICK_SIZE

        if (bar2["close"] < vwap_prior and bar1["low"] <= vwap_prior and
            bar1["close"] > vwap_prior and (bar1["close"] - vwap_prior) >= confirm):
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i, t, entry_px - sl_ticks * TICK_SIZE,
                         entry_px + tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
        elif (bar2["close"] > vwap_prior and bar1["high"] >= vwap_prior and
              bar1["close"] < vwap_prior and (vwap_prior - bar1["close"]) >= confirm):
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=row["session_date"])
            simulate_exit(bars, i, t, entry_px + sl_ticks * TICK_SIZE,
                         entry_px - tp_ticks * TICK_SIZE, flatten_h, sess)
            trades.append(t); trade_taken = True
    return trades


# ── metrics ───────────────────────────────────────────────────────────────

def metrics(trades):
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "avg_pnl": 0,
                "max_dd": 0, "pf": 0, "winners": 0, "losers": 0, "sharpe": 0}
    pnls = [t.pnl for t in trades]
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.max(peak - equity))
    gp = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    pf = gp / gl if gl > 0 else float("inf")
    w = sum(1 for p in pnls if p > 0)
    mean_pnl = np.mean(pnls)
    std_pnl = np.std(pnls, ddof=1) if len(pnls) > 1 else 1
    sharpe = mean_pnl / std_pnl * np.sqrt(252) if std_pnl > 0 else 0
    return {
        "trades": len(trades), "net_pnl": round(sum(pnls), 2),
        "win_rate": round(w / len(trades) * 100, 1),
        "avg_pnl": round(mean_pnl, 2), "max_dd": round(max_dd, 2),
        "pf": round(pf, 2), "winners": w, "losers": len(trades) - w,
        "sharpe": round(sharpe, 2),
    }


# ── Monte Carlo ───────────────────────────────────────────────────────────

def monte_carlo(trades, iterations=10000):
    if not trades: return {}
    pnls = [t.pnl for t in trades]
    n = len(pnls)
    mc_finals = []
    mc_max_dds = []
    for _ in range(iterations):
        shuffled = random.choices(pnls, k=n)
        eq = np.cumsum(shuffled)
        mc_finals.append(eq[-1])
        peak = np.maximum.accumulate(eq)
        mc_max_dds.append(float(np.max(peak - eq)))
    return {
        "median_pnl": round(np.median(mc_finals), 2),
        "p5_pnl": round(np.percentile(mc_finals, 5), 2),
        "p95_pnl": round(np.percentile(mc_finals, 95), 2),
        "median_dd": round(np.median(mc_max_dds), 2),
        "p95_dd": round(np.percentile(mc_max_dds, 95), 2),
        "prob_profitable": round(sum(1 for f in mc_finals if f > 0) / iterations * 100, 1),
    }


# ── walk-forward ──────────────────────────────────────────────────────────

def walk_forward(bars, dates, strategy_fn, params, is_days=40, oos_days=20):
    """Rolling walk-forward: optimize on IS window, test on OOS window."""
    results = []
    i = 0
    while i + is_days + oos_days <= len(dates):
        is_dates = set(dates[i:i + is_days])
        oos_dates = set(dates[i + is_days:i + is_days + oos_days])

        is_bars = bars[bars["session_date"].isin(is_dates)]
        oos_bars = bars[bars["session_date"].isin(oos_dates)]

        # Run on IS
        is_trades = strategy_fn(is_bars.reset_index(drop=True), **params)
        is_m = metrics(is_trades)

        # Run on OOS
        oos_trades = strategy_fn(oos_bars.reset_index(drop=True), **params)
        oos_m = metrics(oos_trades)

        results.append({
            "is_start": dates[i], "is_end": dates[i + is_days - 1],
            "oos_start": dates[i + is_days], "oos_end": dates[i + is_days + oos_days - 1],
            "is_trades": is_m["trades"], "is_pnl": is_m["net_pnl"], "is_wr": is_m["win_rate"],
            "oos_trades": oos_m["trades"], "oos_pnl": oos_m["net_pnl"], "oos_wr": oos_m["win_rate"],
        })
        i += oos_days  # step forward by OOS window

    return results


# ── main ──────────────────────────────────────────────────────────────────

def main():
    bars, dates = load_bars(30)
    out = []

    def p(s):
        print(s)
        out.append(s)

    p("=" * 90)
    p("DEEP6 — 3-MONTH NQ BACKTEST (Jan 2 - Apr 10, 2026)")
    p(f"Data: {len(bars)} 30-min bars, {len(dates)} trading days")
    p("=" * 90)

    # ── Run all strategies with configs from 5-round optimization ──
    configs = [
        ("CHTrendNavy6-Robust", run_chtrendnavy6,
         dict(sl_ticks=120, tp_ticks=160, slope_lb=3, pb_ticks=10, start_h=10.0, end_h=14.5)),
        ("CHTrendNavy6-Aggressive", run_chtrendnavy6,
         dict(sl_ticks=240, tp_ticks=240, slope_lb=2, pb_ticks=20, start_h=10.0, end_h=14.5)),
        ("ChNavy6-Best", run_chnavy6,
         dict(sl_ticks=160, tp_ticks=560, bounce_ticks=20, start_h=9.5, end_h=14.5)),
        ("ChNavy6-Robust", run_chnavy6,
         dict(sl_ticks=320, tp_ticks=200, bounce_ticks=20, start_h=10.0, end_h=14.5)),
        ("Ch2Navy6-Best", run_ch2navy6,
         dict(sl_ticks=200, tp_ticks=200, bounce_ticks=20, start_h=9.5, end_h=14.5)),
    ]

    all_results = {}
    for name, fn, params in configs:
        trades = fn(bars, **params)
        m = metrics(trades)
        all_results[name] = (trades, m, params)

        p(f"\n{'─' * 70}")
        p(f"  {name}")
        p(f"{'─' * 70}")
        p(f"  Params: {params}")
        p(f"  Trades: {m['trades']}  |  Win%: {m['win_rate']}%  |  PF: {m['pf']}  |  Sharpe: {m['sharpe']}")
        p(f"  Net PnL: ${m['net_pnl']:,.2f}  |  Avg: ${m['avg_pnl']:,.2f}  |  MaxDD: ${m['max_dd']:,.2f}")
        p(f"  Winners: {m['winners']}  |  Losers: {m['losers']}")

        # Exit reason breakdown
        reasons = {}
        for t in trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        p(f"  Exit reasons: {reasons}")

        # Monthly breakdown
        if trades:
            p(f"\n  Monthly Breakdown:")
            monthly = {}
            for t in trades:
                month = str(t.session_date)[:7] if t.session_date else "?"
                if month not in monthly:
                    monthly[month] = {"trades": 0, "pnl": 0, "wins": 0}
                monthly[month]["trades"] += 1
                monthly[month]["pnl"] += t.pnl
                if t.pnl > 0: monthly[month]["wins"] += 1
            p(f"  {'Month':>10s} {'Trades':>7s} {'PnL':>12s} {'Win%':>7s}")
            for month in sorted(monthly.keys()):
                md = monthly[month]
                wr = md["wins"] / md["trades"] * 100 if md["trades"] > 0 else 0
                p(f"  {month:>10s} {md['trades']:>7d} ${md['pnl']:>10,.2f} {wr:>6.1f}%")

    # ── Comparison table ──
    p(f"\n{'=' * 90}")
    p("STRATEGY COMPARISON")
    p(f"{'=' * 90}")
    p(f"  {'Strategy':<30s} {'Trades':>7s} {'Net PnL':>12s} {'Win%':>7s} {'PF':>7s} {'Sharpe':>8s} {'MaxDD':>10s}")
    p(f"  {'-'*82}")
    for name, (trades, m, _) in all_results.items():
        p(f"  {name:<30s} {m['trades']:>7d} ${m['net_pnl']:>10,.2f} {m['win_rate']:>6.1f}% {m['pf']:>7.2f} {m['sharpe']:>8.2f} ${m['max_dd']:>8,.2f}")

    # ── Walk-Forward for top strategy ──
    p(f"\n{'=' * 90}")
    p("WALK-FORWARD ANALYSIS (40-day IS / 20-day OOS)")
    p(f"{'=' * 90}")

    for name, fn, params in configs[:2]:  # top 2 CHTrendNavy6 configs
        wf = walk_forward(bars, dates, fn, params, is_days=40, oos_days=20)
        p(f"\n  {name}:")
        p(f"  {'IS Period':>25s} {'IS PnL':>10s} {'IS Tr':>6s} {'OOS Period':>25s} {'OOS PnL':>10s} {'OOS Tr':>6s} {'OOS WR':>7s}")
        total_oos_pnl = 0
        total_oos_trades = 0
        oos_wins = 0
        for w in wf:
            is_per = f"{w['is_start']}→{w['is_end']}"
            oos_per = f"{w['oos_start']}→{w['oos_end']}"
            p(f"  {is_per:>25s} ${w['is_pnl']:>8,.2f} {w['is_trades']:>6d} {oos_per:>25s} ${w['oos_pnl']:>8,.2f} {w['oos_trades']:>6d} {w['oos_wr']:>6.1f}%")
            total_oos_pnl += w['oos_pnl']
            total_oos_trades += w['oos_trades']
            if w['oos_pnl'] > 0: oos_wins += 1
        p(f"  Total OOS PnL: ${total_oos_pnl:,.2f} across {total_oos_trades} trades")
        p(f"  OOS Windows Profitable: {oos_wins}/{len(wf)} ({oos_wins/len(wf)*100:.0f}%)" if wf else "  No windows")

    # ── Monte Carlo for top 3 ──
    p(f"\n{'=' * 90}")
    p("MONTE CARLO ANALYSIS (10,000 iterations)")
    p(f"{'=' * 90}")

    for name in list(all_results.keys())[:3]:
        trades, m, _ = all_results[name]
        if trades:
            mc = monte_carlo(trades, 10000)
            p(f"\n  {name}:")
            p(f"    Median PnL: ${mc['median_pnl']:,.2f}")
            p(f"    5th-95th percentile: ${mc['p5_pnl']:,.2f} to ${mc['p95_pnl']:,.2f}")
            p(f"    Median MaxDD: ${mc['median_dd']:,.2f}  |  95th percentile DD: ${mc['p95_dd']:,.2f}")
            p(f"    Probability of profit: {mc['prob_profitable']}%")

    # ── Trade-by-trade for best config ──
    best_name = max(all_results.keys(), key=lambda k: all_results[k][1]["net_pnl"])
    best_trades, best_m, _ = all_results[best_name]
    p(f"\n{'=' * 90}")
    p(f"TRADE LOG — {best_name} ({best_m['trades']} trades)")
    p(f"{'=' * 90}")
    if best_trades:
        p(f"  {'#':>3s} {'Date':>12s} {'Time':>8s} {'Side':>6s} {'Entry':>10s} {'Exit':>10s} {'Reason':>12s} {'PnL':>10s} {'Cum PnL':>10s}")
        cum = 0
        for i, t in enumerate(best_trades, 1):
            cum += t.pnl
            ts = str(t.entry_time)
            date_part = ts[:10] if len(ts) >= 10 else ts
            time_part = ts[11:19] if len(ts) >= 19 else ""
            p(f"  {i:>3d} {date_part:>12s} {time_part:>8s} {t.side:>6s} {t.entry_price:>10.2f} {t.exit_price:>10.2f} {t.exit_reason:>12s} ${t.pnl:>+8.2f} ${cum:>+8.2f}")

    # ── Final Recommendation ──
    p(f"\n{'=' * 90}")
    p("FINAL RECOMMENDATION")
    p(f"{'=' * 90}")

    # Sort by net PnL
    ranked = sorted(all_results.items(), key=lambda x: x[1][1]["net_pnl"], reverse=True)
    p(f"\n  Best overall: {ranked[0][0]}")
    p(f"  Net PnL: ${ranked[0][1][1]['net_pnl']:,.2f} over {len(dates)} days")
    p(f"  Params: {ranked[0][1][2]}")

    # Best risk-adjusted (Sharpe)
    ranked_sharpe = sorted(all_results.items(), key=lambda x: x[1][1]["sharpe"], reverse=True)
    p(f"\n  Best risk-adjusted: {ranked_sharpe[0][0]}")
    p(f"  Sharpe: {ranked_sharpe[0][1][1]['sharpe']} | PnL: ${ranked_sharpe[0][1][1]['net_pnl']:,.2f}")

    # Write to file
    with open("scripts/results_3mo_backtest.txt", "w") as f:
        f.write("\n".join(out))
    print(f"\nResults saved to scripts/results_3mo_backtest.txt")


if __name__ == "__main__":
    main()
