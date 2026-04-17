"""
Backtest three VWAP strategies on 30-minute NQ bars.

Strategies:
  1. ChNavy6     — VWAP bounce (wasBelowVWAP/wasAboveVWAP flags + confirmation)
  2. Ch2Navy6    — VWAP rejection (bar[2]/bar[1] structural cross)
  3. CHTrendNavy6 — VWAP trend pullback (slope + pullback band)

Data source: replay_full_5sessions.duckdb (1m bars resampled to 30m)
"""

import duckdb
import pandas as pd
import numpy as np
from itertools import product
from dataclasses import dataclass, field
from typing import Optional
import json, sys

# ── constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0          # $5 per tick for NQ
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
DB_PATH = "data/backtests/replay_full_5sessions.duckdb"

# ── load & resample ───────────────────────────────────────────────────────

def load_30m_bars() -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("""
        SELECT bar_ts, open, high, low, close, volume
        FROM backtest_bars
        WHERE tf = '1m'
        ORDER BY bar_ts
    """).fetchdf()
    con.close()

    df["bar_ts"] = pd.to_datetime(df["bar_ts"])
    df = df.set_index("bar_ts")

    # CME NQ session boundary: 17:00 ET.  Times before 17:00 belong to that
    # calendar date; times >= 17:00 belong to the *next* trading day.
    # For our purposes, since strategies only trade 9:30-16:00, calendar date works.
    df["session"] = df.index.date

    # resample within each session date to 30m
    frames = []
    for sid, grp in df.groupby("session"):
        r = grp.resample("30min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "session": "first",
        }).dropna(subset=["open"])
        frames.append(r)
    bars = pd.concat(frames).sort_index()
    # convert date to integer session id for easier comparison
    unique_dates = sorted(bars["session"].unique())
    date_to_id = {d: i for i, d in enumerate(unique_dates)}
    bars["session"] = bars["session"].map(date_to_id)
    print(f"Loaded {len(bars)} 30-min bars across {len(unique_dates)} sessions")
    print(f"Sessions: {unique_dates}")

    # Show RTH bar counts per session
    bars_reset = bars.reset_index()
    for d, sid in date_to_id.items():
        sess_bars = bars_reset[bars_reset["session"] == sid]
        rth = sess_bars[(sess_bars["bar_ts"].dt.hour >= 9) & (sess_bars["bar_ts"].dt.hour < 16)]
        print(f"  Session {d}: {len(sess_bars)} total bars, {len(rth)} RTH bars (9:00-16:00)")

    return bars.reset_index()


# ── trade result ──────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: pd.Timestamp
    side: str          # "LONG" or "SHORT"
    entry_price: float
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0

    def close(self, exit_price: float, reason: str):
        slip = SLIPPAGE_TICKS * TICK_SIZE
        if self.side == "LONG":
            self.exit_price = exit_price - slip
            self.pnl = (self.exit_price - self.entry_price) / TICK_SIZE * TICK_VALUE
        else:
            self.exit_price = exit_price + slip
            self.pnl = (self.entry_price - self.exit_price) / TICK_SIZE * TICK_VALUE
        self.pnl -= 2 * COMMISSION_PER_SIDE  # round-trip commission
        self.exit_reason = reason


# ── strategy 1: ChNavy6 (VWAP bounce, OnBarClose) ────────────────────────

def run_chnavy6(bars: pd.DataFrame, sl_ticks: int, tp_ticks: int,
                bounce_confirm_ticks: int,
                start_h: int, end_h: int, flatten_h: int) -> list[Trade]:
    trades: list[Trade] = []
    cum_tpv = cum_vol = 0.0
    vwap = 0.0
    was_below = was_above = False
    trade_taken = False
    prev_session = -1

    for i in range(1, len(bars)):
        row = bars.iloc[i]
        prev = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session"]

        # new session reset
        if sess != prev_session:
            cum_tpv = cum_vol = vwap = 0.0
            was_below = was_above = False
            trade_taken = False
            prev_session = sess

        # compute VWAP using current bar (OnBarClose style)
        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        tpv = typical * row["volume"]
        prior_vwap = cum_tpv / cum_vol if cum_vol > 0 else prev["close"]
        cum_tpv += tpv
        cum_vol += row["volume"]
        vwap = cum_tpv / cum_vol if cum_vol > 0 else row["close"]

        if trade_taken:
            continue
        if hour < start_h or hour > end_h:
            continue

        # track position relative to VWAP
        if prev["close"] < prior_vwap:
            was_below = True
            was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True
            was_below = False

        confirm = bounce_confirm_ticks * TICK_SIZE

        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px)
            sl_px = entry_px - sl_ticks * TICK_SIZE
            tp_px = entry_px + tp_ticks * TICK_SIZE
            # simulate exit using next bars
            _simulate_exit(bars, i + 1, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True

        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px)
            sl_px = entry_px + sl_ticks * TICK_SIZE
            tp_px = entry_px - tp_ticks * TICK_SIZE
            _simulate_exit(bars, i + 1, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True

    return trades


# ── strategy 2: Ch2Navy6 (structural VWAP rejection) ─────────────────────

def run_ch2navy6(bars: pd.DataFrame, sl_ticks: int, tp_ticks: int,
                 bounce_confirm_ticks: int,
                 start_h: int, end_h: int, flatten_h: int) -> list[Trade]:
    trades: list[Trade] = []
    cum_tpv = cum_vol = 0.0
    trade_taken = False
    prev_session = -1

    for i in range(2, len(bars)):
        row = bars.iloc[i]       # current (signal bar)
        bar1 = bars.iloc[i - 1]  # bar[1]
        bar2 = bars.iloc[i - 2]  # bar[2]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session"]

        if sess != prev_session:
            cum_tpv = cum_vol = 0.0
            trade_taken = False
            prev_session = sess

        # VWAP from bar[1]
        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        tpv1 = typical1 * bar1["volume"]
        vwap_prior = cum_tpv / cum_vol if cum_vol > 0 else bar2["close"]
        cum_tpv += tpv1
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]

        if trade_taken:
            continue
        if hour < start_h or hour > end_h:
            continue

        confirm = bounce_confirm_ticks * TICK_SIZE

        long_setup = (
            bar2["close"] < vwap_prior and
            bar1["low"] <= vwap_prior and
            bar1["close"] > vwap_prior and
            (bar1["close"] - vwap_prior) >= confirm
        )
        short_setup = (
            bar2["close"] > vwap_prior and
            bar1["high"] >= vwap_prior and
            bar1["close"] < vwap_prior and
            (vwap_prior - bar1["close"]) >= confirm
        )

        if long_setup:
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE  # enter on next bar open
            t = Trade(ts, "LONG", entry_px)
            sl_px = entry_px - sl_ticks * TICK_SIZE
            tp_px = entry_px + tp_ticks * TICK_SIZE
            _simulate_exit(bars, i, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True
        elif short_setup:
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px)
            sl_px = entry_px + sl_ticks * TICK_SIZE
            tp_px = entry_px - tp_ticks * TICK_SIZE
            _simulate_exit(bars, i, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True

    return trades


# ── strategy 3: CHTrendNavy6 (VWAP slope pullback) ───────────────────────

def run_chtrendnavy6(bars: pd.DataFrame, sl_ticks: int, tp_ticks: int,
                     slope_lookback: int, pullback_ticks: int,
                     start_h: int, end_h: int, flatten_h: int) -> list[Trade]:
    trades: list[Trade] = []
    cum_tpv = cum_vol = 0.0
    vwap_hist: list[float] = []
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

        # VWAP from bar[1]
        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        tpv1 = typical1 * bar1["volume"]
        cum_tpv += tpv1
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]
        vwap_hist.append(vwap_now)

        if trade_taken:
            continue
        if hour < start_h or hour > end_h:
            continue
        if len(vwap_hist) <= slope_lookback:
            continue

        vwap_slope = vwap_hist[-1] - vwap_hist[-1 - slope_lookback]
        band = pullback_ticks * TICK_SIZE

        long_setup = (
            vwap_slope > 0 and
            bar1["close"] > vwap_now and
            bar1["low"] <= vwap_now + band
        )
        short_setup = (
            vwap_slope < 0 and
            bar1["close"] < vwap_now and
            bar1["high"] >= vwap_now - band
        )

        if long_setup:
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px)
            sl_px = entry_px - sl_ticks * TICK_SIZE
            tp_px = entry_px + tp_ticks * TICK_SIZE
            _simulate_exit(bars, i, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True
        elif short_setup:
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px)
            sl_px = entry_px + sl_ticks * TICK_SIZE
            tp_px = entry_px - tp_ticks * TICK_SIZE
            _simulate_exit(bars, i, t, sl_px, tp_px, flatten_h)
            trades.append(t)
            trade_taken = True

    return trades


# ── exit simulation (shared) ─────────────────────────────────────────────

def _simulate_exit(bars: pd.DataFrame, start_idx: int, trade: Trade,
                   sl_price: float, tp_price: float, flatten_h: int):
    """Walk forward from start_idx to find SL/TP/time exit."""
    sess = bars.iloc[min(start_idx, len(bars) - 1)]["session"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session"] != sess:
            # session ended — flatten at last bar of session
            prev_b = bars.iloc[j - 1]
            trade.close(prev_b["close"], "SESSION_END")
            return

        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN")
            return

        if trade.side == "LONG":
            if b["low"] <= sl_price:
                trade.close(sl_price, "STOP")
                return
            if b["high"] >= tp_price:
                trade.close(tp_price, "TARGET")
                return
        else:
            if b["high"] >= sl_price:
                trade.close(sl_price, "STOP")
                return
            if b["low"] <= tp_price:
                trade.close(tp_price, "TARGET")
                return

    # end of data
    trade.close(bars.iloc[-1]["close"], "DATA_END")


# ── metrics ───────────────────────────────────────────────────────────────

def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "avg_pnl": 0,
                "max_dd": 0, "profit_factor": 0, "winners": 0, "losers": 0}

    pnls = [t.pnl for t in trades]
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    winners = sum(1 for p in pnls if p > 0)
    losers = sum(1 for p in pnls if p <= 0)

    return {
        "trades": len(trades),
        "net_pnl": round(sum(pnls), 2),
        "win_rate": round(winners / len(trades) * 100, 1),
        "avg_pnl": round(np.mean(pnls), 2),
        "max_dd": round(max_dd, 2),
        "profit_factor": round(pf, 2),
        "winners": winners,
        "losers": losers,
    }


# ── optimizer ─────────────────────────────────────────────────────────────

def optimize():
    bars = load_30m_bars()

    # Parameter ranges scaled for 30-min NQ bars
    # Median 30m bar range = 266 ticks (66 pts), so SL/TP must be wider
    sl_range = [80, 120, 160, 200, 240]        # 20-60 pts
    tp_range = [120, 200, 280, 360, 480]       # 30-120 pts
    bounce_range = [20, 40, 60, 80, 100]       # 5-25 pts confirmation
    start_hours = [9.5, 10.0]                  # 9:30 or 10:00 ET
    end_hours = [14.5, 15.0]                   # 2:30 or 3:00 ET
    flatten_h = 16

    # Trend-specific params (also scaled for 30m)
    slope_lookback_range = [2, 3, 4, 5]        # bars of lookback
    pullback_range = [20, 40, 60, 80]          # 5-20 pts band

    results = []

    # ── Strategy 1: ChNavy6 ──
    print("\n=== Optimizing ChNavy6 (VWAP Bounce) ===")
    combos = list(product(sl_range, tp_range, bounce_range, start_hours, end_hours))
    print(f"  {len(combos)} parameter combinations...")
    best_navy = None
    for sl, tp, bounce, sh, eh in combos:
        trades = run_chnavy6(bars, sl, tp, bounce, sh, eh, flatten_h)
        m = compute_metrics(trades)
        m.update({"strategy": "ChNavy6", "sl": sl, "tp": tp, "bounce": bounce,
                  "start": sh, "end": eh})
        results.append(m)
        if best_navy is None or m["net_pnl"] > best_navy["net_pnl"]:
            best_navy = m

    # ── Strategy 2: Ch2Navy6 ──
    print("\n=== Optimizing Ch2Navy6 (VWAP Rejection) ===")
    combos = list(product(sl_range, tp_range, bounce_range, start_hours, end_hours))
    print(f"  {len(combos)} parameter combinations...")
    best_ch2 = None
    for sl, tp, bounce, sh, eh in combos:
        trades = run_ch2navy6(bars, sl, tp, bounce, sh, eh, flatten_h)
        m = compute_metrics(trades)
        m.update({"strategy": "Ch2Navy6", "sl": sl, "tp": tp, "bounce": bounce,
                  "start": sh, "end": eh})
        results.append(m)
        if best_ch2 is None or m["net_pnl"] > best_ch2["net_pnl"]:
            best_ch2 = m

    # ── Strategy 3: CHTrendNavy6 ──
    print("\n=== Optimizing CHTrendNavy6 (VWAP Trend Pullback) ===")
    combos = list(product(sl_range, tp_range, slope_lookback_range, pullback_range,
                          start_hours, end_hours))
    print(f"  {len(combos)} parameter combinations...")
    best_trend = None
    for sl, tp, slope_lb, pb, sh, eh in combos:
        trades = run_chtrendnavy6(bars, sl, tp, slope_lb, pb, sh, eh, flatten_h)
        m = compute_metrics(trades)
        m.update({"strategy": "CHTrendNavy6", "sl": sl, "tp": tp,
                  "slope_lookback": slope_lb, "pullback_ticks": pb,
                  "start": sh, "end": eh})
        results.append(m)
        if best_trend is None or m["net_pnl"] > best_trend["net_pnl"]:
            best_trend = m

    # ── Report ──
    print("\n" + "=" * 80)
    print("OPTIMIZATION RESULTS — 30-MINUTE NQ CHART")
    print("=" * 80)

    for label, best in [("ChNavy6 (VWAP Bounce)", best_navy),
                         ("Ch2Navy6 (VWAP Rejection)", best_ch2),
                         ("CHTrendNavy6 (Trend Pullback)", best_trend)]:
        print(f"\n{'─' * 60}")
        print(f"  BEST: {label}")
        print(f"{'─' * 60}")
        if best and best["trades"] > 0:
            for k, v in best.items():
                print(f"    {k:20s}: {v}")
        else:
            print("    No trades generated with any parameter combination")

    # Top 10 overall by net PnL (min 2 trades)
    valid = [r for r in results if r["trades"] >= 2]
    valid.sort(key=lambda x: x["net_pnl"], reverse=True)

    print(f"\n{'=' * 80}")
    print("TOP 10 CONFIGURATIONS (min 2 trades)")
    print(f"{'=' * 80}")
    for i, r in enumerate(valid[:10], 1):
        print(f"\n  #{i}: {r['strategy']}")
        print(f"      PnL: ${r['net_pnl']:,.2f} | Trades: {r['trades']} | "
              f"Win%: {r['win_rate']}% | PF: {r['profit_factor']} | MaxDD: ${r['max_dd']:,.2f}")
        params = {k: v for k, v in r.items()
                  if k not in ("trades", "net_pnl", "win_rate", "avg_pnl",
                               "max_dd", "profit_factor", "winners", "losers", "strategy")}
        print(f"      Params: {params}")

    # Top 10 by profit factor (min 2 trades, PF > 1)
    pf_valid = [r for r in valid if r["profit_factor"] > 1]
    pf_valid.sort(key=lambda x: x["profit_factor"], reverse=True)

    print(f"\n{'=' * 80}")
    print("TOP 10 BY PROFIT FACTOR (min 2 trades, PF > 1)")
    print(f"{'=' * 80}")
    for i, r in enumerate(pf_valid[:10], 1):
        print(f"\n  #{i}: {r['strategy']}")
        print(f"      PnL: ${r['net_pnl']:,.2f} | Trades: {r['trades']} | "
              f"Win%: {r['win_rate']}% | PF: {r['profit_factor']} | MaxDD: ${r['max_dd']:,.2f}")
        params = {k: v for k, v in r.items()
                  if k not in ("trades", "net_pnl", "win_rate", "avg_pnl",
                               "max_dd", "profit_factor", "winners", "losers", "strategy")}
        print(f"      Params: {params}")

    # Trade details for each best config
    print(f"\n{'=' * 80}")
    print("TRADE-BY-TRADE DETAIL FOR BEST CONFIGS")
    print(f"{'=' * 80}")

    if best_navy and best_navy["trades"] > 0:
        print(f"\n  ChNavy6 (SL={best_navy['sl']}, TP={best_navy['tp']}, Bounce={best_navy['bounce']})")
        trades = run_chnavy6(bars, best_navy["sl"], best_navy["tp"], best_navy["bounce"],
                             best_navy["start"], best_navy["end"], flatten_h)
        for t in trades:
            print(f"    {t.entry_time} {t.side:5s} entry={t.entry_price:.2f} "
                  f"exit={t.exit_price:.2f} pnl=${t.pnl:+.2f} [{t.exit_reason}]")

    if best_ch2 and best_ch2["trades"] > 0:
        print(f"\n  Ch2Navy6 (SL={best_ch2['sl']}, TP={best_ch2['tp']}, Bounce={best_ch2['bounce']})")
        trades = run_ch2navy6(bars, best_ch2["sl"], best_ch2["tp"], best_ch2["bounce"],
                              best_ch2["start"], best_ch2["end"], flatten_h)
        for t in trades:
            print(f"    {t.entry_time} {t.side:5s} entry={t.entry_price:.2f} "
                  f"exit={t.exit_price:.2f} pnl=${t.pnl:+.2f} [{t.exit_reason}]")

    if best_trend and best_trend["trades"] > 0:
        print(f"\n  CHTrendNavy6 (SL={best_trend['sl']}, TP={best_trend['tp']}, "
              f"SlopeLB={best_trend.get('slope_lookback','?')}, PB={best_trend.get('pullback_ticks','?')})")
        trades = run_chtrendnavy6(bars, best_trend["sl"], best_trend["tp"],
                                   best_trend.get("slope_lookback", 10),
                                   best_trend.get("pullback_ticks", 6),
                                   best_trend["start"], best_trend["end"], flatten_h)
        for t in trades:
            print(f"    {t.entry_time} {t.side:5s} entry={t.entry_price:.2f} "
                  f"exit={t.exit_price:.2f} pnl=${t.pnl:+.2f} [{t.exit_reason}]")


if __name__ == "__main__":
    optimize()
