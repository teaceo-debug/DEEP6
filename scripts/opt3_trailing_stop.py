"""
opt3_trailing_stop.py — Trailing stop optimization for ChNavy6 (VWAP Bounce) on 30m NQ bars.

Baseline: SL=160t, TP=560t, +$4,762, 29.8% WR, 47 trades.
Problem:  Fixed TP=560t (140pts) is often unreachable — only 10/47 hit target.

Tests five trailing stop mechanisms to lock in profits and replace the fixed TP.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable
from itertools import product
import sys, os

# ── constants ────────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
CSV_PATH = "/Users/teaceo/DEEP6/data/backtests/nq_3mo_1m.csv"
OUT_PATH = "/Users/teaceo/DEEP6/scripts/opt3_trailing_stop.txt"

# ── load & resample ──────────────────────────────────────────────────────────

def load_30m_bars() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "bar_ts"})
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True).dt.tz_convert("US/Eastern")
    df = df.set_index("bar_ts").sort_index()
    df["session_date"] = df.index.date

    frames = []
    for sd, grp in df.groupby("session_date"):
        r = grp.resample("30min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum", "session_date": "first",
        }).dropna(subset=["open"])
        frames.append(r)
    bars = pd.concat(frames).sort_index()
    bars = bars.reset_index()
    print(f"Loaded {len(bars)} 30-min bars across {bars['session_date'].nunique()} sessions")
    return bars


# ── trade dataclass ──────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    exit_time: object = None
    max_favorable: float = 0.0   # max favorable excursion in ticks

    def close(self, exit_price: float, reason: str, exit_time=None):
        slip = SLIPPAGE_TICKS * TICK_SIZE
        if self.side == "LONG":
            self.exit_price = exit_price - slip
            self.pnl = (self.exit_price - self.entry_price) / TICK_SIZE * TICK_VALUE
        else:
            self.exit_price = exit_price + slip
            self.pnl = (self.entry_price - self.exit_price) / TICK_SIZE * TICK_VALUE
        self.pnl -= 2 * COMMISSION_PER_SIDE
        self.exit_reason = reason
        self.exit_time = exit_time


# ── exit simulators ──────────────────────────────────────────────────────────

def _exit_baseline(bars, start_idx, trade, sl_ticks, tp_ticks, flatten_h):
    """Fixed SL + fixed TP (baseline)."""
    sl_px = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]
    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"])
            return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"])
            return
        if trade.side == "LONG":
            if b["low"] <= sl_px:
                trade.close(sl_px, "STOP", b["bar_ts"]); return
            if b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            if b["high"] >= sl_px:
                trade.close(sl_px, "STOP", b["bar_ts"]); return
            if b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


def _exit_breakeven_trail(bars, start_idx, trade, sl_ticks, tp_ticks,
                          flatten_h, be_trigger, trail_dist):
    """Variant 1: After +be_trigger ticks, move SL to breakeven. Then trail by trail_dist."""
    initial_sl = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE if tp_ticks else None
    current_sl = initial_sl
    best_price = trade.entry_price
    be_activated = False
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"]); return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"]); return

        # Update best price seen so far (using close as conservative proxy for intrabar)
        if trade.side == "LONG":
            best_price = max(best_price, b["high"])
            favorable_ticks = (best_price - trade.entry_price) / TICK_SIZE
            # Check breakeven trigger
            if not be_activated and favorable_ticks >= be_trigger:
                be_activated = True
                current_sl = trade.entry_price  # move to breakeven
            # If activated, trail from best price
            if be_activated:
                trail_sl = best_price - trail_dist * TICK_SIZE
                current_sl = max(current_sl, trail_sl)
            # Check exits
            if b["low"] <= current_sl:
                trade.close(current_sl, "TRAIL" if be_activated else "STOP", b["bar_ts"]); return
            if tp_px and b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            best_price = min(best_price, b["low"])
            favorable_ticks = (trade.entry_price - best_price) / TICK_SIZE
            if not be_activated and favorable_ticks >= be_trigger:
                be_activated = True
                current_sl = trade.entry_price
            if be_activated:
                trail_sl = best_price + trail_dist * TICK_SIZE
                current_sl = min(current_sl, trail_sl)
            if b["high"] >= current_sl:
                trade.close(current_sl, "TRAIL" if be_activated else "STOP", b["bar_ts"]); return
            if tp_px and b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return

    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


def _exit_stepped_trail(bars, start_idx, trade, sl_ticks, tp_ticks,
                        flatten_h, step_size):
    """Variant 2: Move SL in fixed steps. After +step, SL=entry. After +2*step, SL=+step. etc."""
    initial_sl = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE if tp_ticks else None
    current_sl = initial_sl
    best_price = trade.entry_price
    step_px = step_size * TICK_SIZE
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"]); return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"]); return

        if trade.side == "LONG":
            best_price = max(best_price, b["high"])
            move_ticks = best_price - trade.entry_price
            steps_completed = int(move_ticks / step_px)
            if steps_completed >= 1:
                new_sl = trade.entry_price + (steps_completed - 1) * step_px
                current_sl = max(current_sl, new_sl)
            if b["low"] <= current_sl:
                reason = "STEP_TRAIL" if steps_completed >= 1 else "STOP"
                trade.close(current_sl, reason, b["bar_ts"]); return
            if tp_px and b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            best_price = min(best_price, b["low"])
            move_ticks = trade.entry_price - best_price
            steps_completed = int(move_ticks / step_px)
            if steps_completed >= 1:
                new_sl = trade.entry_price - (steps_completed - 1) * step_px
                current_sl = min(current_sl, new_sl)
            if b["high"] >= current_sl:
                reason = "STEP_TRAIL" if steps_completed >= 1 else "STOP"
                trade.close(current_sl, reason, b["bar_ts"]); return
            if tp_px and b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return

    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


def _exit_atr_trail(bars, start_idx, trade, sl_ticks, tp_ticks,
                    flatten_h, atr_mult, atr_period=14):
    """Variant 3: Trail = N * ATR from current high/low."""
    initial_sl = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE if tp_ticks else None
    current_sl = initial_sl
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"]); return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"]); return

        # Compute ATR over last atr_period bars
        lookback_start = max(0, j - atr_period)
        tr_vals = []
        for k in range(lookback_start, j + 1):
            bk = bars.iloc[k]
            if k > 0:
                prev_close = bars.iloc[k-1]["close"]
                tr = max(bk["high"] - bk["low"],
                         abs(bk["high"] - prev_close),
                         abs(bk["low"] - prev_close))
            else:
                tr = bk["high"] - bk["low"]
            tr_vals.append(tr)
        atr = np.mean(tr_vals) if tr_vals else 10 * TICK_SIZE

        trail_dist = atr_mult * atr

        if trade.side == "LONG":
            atr_sl = b["high"] - trail_dist
            current_sl = max(current_sl, atr_sl)
            if b["low"] <= current_sl:
                trade.close(current_sl, "ATR_TRAIL", b["bar_ts"]); return
            if tp_px and b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            atr_sl = b["low"] + trail_dist
            current_sl = min(current_sl, atr_sl)
            if b["high"] >= current_sl:
                trade.close(current_sl, "ATR_TRAIL", b["bar_ts"]); return
            if tp_px and b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return

    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


def _exit_time_profit_lock(bars, start_idx, trade, sl_ticks, tp_ticks,
                           flatten_h, lock_after_bars):
    """Variant 4: After N bars in trade, if profitable, tighten SL to breakeven."""
    initial_sl = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE if tp_ticks else None
    current_sl = initial_sl
    bars_in_trade = 0
    locked = False
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"]); return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"]); return

        bars_in_trade += 1

        # Check if we should lock to breakeven
        if not locked and bars_in_trade >= lock_after_bars:
            if trade.side == "LONG" and b["close"] > trade.entry_price:
                current_sl = trade.entry_price
                locked = True
            elif trade.side == "SHORT" and b["close"] < trade.entry_price:
                current_sl = trade.entry_price
                locked = True

        if trade.side == "LONG":
            if b["low"] <= current_sl:
                trade.close(current_sl, "TIME_LOCK" if locked else "STOP", b["bar_ts"]); return
            if tp_px and b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            if b["high"] >= current_sl:
                trade.close(current_sl, "TIME_LOCK" if locked else "STOP", b["bar_ts"]); return
            if tp_px and b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return

    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


def _exit_hybrid(bars, start_idx, trade, sl_ticks, tp_ticks,
                 flatten_h, trigger_ticks, trail_dist, use_tp_cap):
    """Variant 5: Initial SL=160t. After +trigger ticks, switch to trailing.
    Optionally keep TP=560t as maximum cap, or remove TP entirely."""
    initial_sl = trade.entry_price + (-1 if trade.side == "LONG" else 1) * sl_ticks * TICK_SIZE
    tp_px = None
    if use_tp_cap and tp_ticks:
        tp_px = trade.entry_price + (1 if trade.side == "LONG" else -1) * tp_ticks * TICK_SIZE
    current_sl = initial_sl
    best_price = trade.entry_price
    trailing_active = False
    sess = bars.iloc[min(start_idx, len(bars)-1)]["session_date"]

    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            trade.close(bars.iloc[j-1]["close"], "SESSION_END", bars.iloc[j-1]["bar_ts"]); return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= flatten_h:
            trade.close(b["open"], "FLATTEN", b["bar_ts"]); return

        if trade.side == "LONG":
            best_price = max(best_price, b["high"])
            favorable = (best_price - trade.entry_price) / TICK_SIZE
            if not trailing_active and favorable >= trigger_ticks:
                trailing_active = True
                current_sl = trade.entry_price  # at least breakeven
            if trailing_active:
                trail_sl = best_price - trail_dist * TICK_SIZE
                current_sl = max(current_sl, trail_sl)
            if b["low"] <= current_sl:
                trade.close(current_sl, "HYBRID_TRAIL" if trailing_active else "STOP", b["bar_ts"]); return
            if tp_px and b["high"] >= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return
        else:
            best_price = min(best_price, b["low"])
            favorable = (trade.entry_price - best_price) / TICK_SIZE
            if not trailing_active and favorable >= trigger_ticks:
                trailing_active = True
                current_sl = trade.entry_price
            if trailing_active:
                trail_sl = best_price + trail_dist * TICK_SIZE
                current_sl = min(current_sl, trail_sl)
            if b["high"] >= current_sl:
                trade.close(current_sl, "HYBRID_TRAIL" if trailing_active else "STOP", b["bar_ts"]); return
            if tp_px and b["low"] <= tp_px:
                trade.close(tp_px, "TARGET", b["bar_ts"]); return

    trade.close(bars.iloc[-1]["close"], "DATA_END", bars.iloc[-1]["bar_ts"])


# ── strategy runner ──────────────────────────────────────────────────────────

def run_chnavy6(bars: pd.DataFrame, exit_fn, exit_kwargs: dict) -> list[Trade]:
    """Run ChNavy6 VWAP bounce strategy with pluggable exit function."""
    trades = []
    cum_tpv = cum_vol = 0.0
    was_below = was_above = False
    trade_taken = False
    prev_session = None
    bounce_confirm = 20  # 5 pts = 20 ticks (fixed from baseline)
    start_h, end_h, flatten_h = 9.5, 14.5, 16.0
    sl_ticks = 160  # baseline SL

    for i in range(1, len(bars)):
        row = bars.iloc[i]
        prev = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sess = row["session_date"]

        if sess != prev_session:
            cum_tpv = cum_vol = vwap = 0.0
            was_below = was_above = False
            trade_taken = False
            prev_session = sess

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

        if prev["close"] < prior_vwap:
            was_below = True
            was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True
            was_below = False

        confirm = bounce_confirm * TICK_SIZE

        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px)
            exit_fn(bars, i + 1, t, sl_ticks=sl_ticks, flatten_h=flatten_h, **exit_kwargs)
            trades.append(t)
            trade_taken = True

        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px)
            exit_fn(bars, i + 1, t, sl_ticks=sl_ticks, flatten_h=flatten_h, **exit_kwargs)
            trades.append(t)
            trade_taken = True

    return trades


# ── metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "pf": 0,
                "sharpe": 0, "max_dd": 0, "avg_winner": 0, "avg_loser": 0}

    pnls = np.array([t.pnl for t in trades])
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.max(peak - equity))

    winners = pnls[pnls > 0]
    losers = pnls[pnls <= 0]
    gross_profit = float(np.sum(winners)) if len(winners) else 0
    gross_loss = float(np.abs(np.sum(losers))) if len(losers) else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    avg_winner = float(np.mean(winners)) if len(winners) else 0
    avg_loser = float(np.mean(losers)) if len(losers) else 0
    sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(252)) if np.std(pnls) > 0 else 0

    return {
        "trades": len(trades),
        "net_pnl": round(float(np.sum(pnls)), 2),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "pf": round(pf, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "avg_winner": round(avg_winner, 2),
        "avg_loser": round(avg_loser, 2),
    }


def exit_reasons_summary(trades: list[Trade]) -> dict:
    reasons = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return reasons


# ── main optimization ────────────────────────────────────────────────────────

def main():
    import io
    buf = io.StringIO()

    def out(s=""):
        print(s)
        buf.write(s + "\n")

    bars = load_30m_bars()

    all_results = []

    # ════════════════════════════════════════════════════════════════════════
    # BASELINE
    # ════════════════════════════════════════════════════════════════════════
    out("=" * 90)
    out("OPT3: TRAILING STOP OPTIMIZATION — ChNavy6 VWAP Bounce, 30m NQ")
    out("=" * 90)

    def baseline_exit(bars, start_idx, trade, sl_ticks, flatten_h, tp_ticks):
        _exit_baseline(bars, start_idx, trade, sl_ticks, tp_ticks, flatten_h)

    baseline_trades = run_chnavy6(bars, baseline_exit, {"tp_ticks": 560})
    bm = compute_metrics(baseline_trades)
    br = exit_reasons_summary(baseline_trades)

    out(f"\nBASELINE: SL=160t, TP=560t")
    out(f"  Trades: {bm['trades']}  Net PnL: ${bm['net_pnl']:,.2f}  Win%: {bm['win_rate']}%  "
        f"PF: {bm['pf']}  Sharpe: {bm['sharpe']}  MaxDD: ${bm['max_dd']:,.2f}")
    out(f"  Avg Winner: ${bm['avg_winner']:,.2f}  Avg Loser: ${bm['avg_loser']:,.2f}")
    out(f"  Exit reasons: {br}")

    # ════════════════════════════════════════════════════════════════════════
    # VARIANT 1: Breakeven + Trail
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("VARIANT 1: BREAKEVEN + TRAIL")
    out(f"{'=' * 90}")

    be_triggers = [80, 120, 160, 200]
    trail_dists = [60, 80, 100, 120, 160]
    v1_results = []

    for be_trig, trail_d in product(be_triggers, trail_dists):
        def v1_exit(bars, si, trade, sl_ticks, flatten_h, _bt=be_trig, _td=trail_d):
            _exit_breakeven_trail(bars, si, trade, sl_ticks, 560, flatten_h, _bt, _td)

        trades = run_chnavy6(bars, v1_exit, {})
        m = compute_metrics(trades)
        m["config"] = f"BE={be_trig}t, Trail={trail_d}t"
        m["be_trigger"] = be_trig
        m["trail_dist"] = trail_d
        m["variant"] = "V1-BE+Trail"
        m["exit_reasons"] = exit_reasons_summary(trades)
        m["_trades"] = trades
        v1_results.append(m)
        all_results.append(m)

    v1_results.sort(key=lambda x: x["net_pnl"], reverse=True)
    out(f"\n{'Config':>25s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9} | {'AvgW':>8} | {'AvgL':>8}")
    out("-" * 105)
    for r in v1_results:
        out(f"  {r['config']:>23s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f} | ${r['avg_winner']:>7,.2f} | ${r['avg_loser']:>7,.2f}")

    # ════════════════════════════════════════════════════════════════════════
    # VARIANT 2: Stepped Trail
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("VARIANT 2: STEPPED TRAIL")
    out(f"{'=' * 90}")

    step_sizes = [60, 80, 100, 120]
    v2_results = []

    for step in step_sizes:
        def v2_exit(bars, si, trade, sl_ticks, flatten_h, _step=step):
            _exit_stepped_trail(bars, si, trade, sl_ticks, 560, flatten_h, _step)

        trades = run_chnavy6(bars, v2_exit, {})
        m = compute_metrics(trades)
        m["config"] = f"Step={step}t"
        m["step_size"] = step
        m["variant"] = "V2-Stepped"
        m["exit_reasons"] = exit_reasons_summary(trades)
        m["_trades"] = trades
        v2_results.append(m)
        all_results.append(m)

    out(f"\n{'Config':>25s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9} | {'AvgW':>8} | {'AvgL':>8}")
    out("-" * 105)
    for r in v2_results:
        out(f"  {r['config']:>23s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f} | ${r['avg_winner']:>7,.2f} | ${r['avg_loser']:>7,.2f}")

    # ════════════════════════════════════════════════════════════════════════
    # VARIANT 3: ATR-Based Trail
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("VARIANT 3: ATR-BASED TRAIL")
    out(f"{'=' * 90}")

    atr_mults = [1.0, 1.5, 2.0, 2.5, 3.0]
    v3_results = []

    for atr_n in atr_mults:
        def v3_exit(bars, si, trade, sl_ticks, flatten_h, _n=atr_n):
            _exit_atr_trail(bars, si, trade, sl_ticks, 560, flatten_h, _n)

        trades = run_chnavy6(bars, v3_exit, {})
        m = compute_metrics(trades)
        m["config"] = f"ATR x{atr_n:.1f}"
        m["atr_mult"] = atr_n
        m["variant"] = "V3-ATR"
        m["exit_reasons"] = exit_reasons_summary(trades)
        m["_trades"] = trades
        v3_results.append(m)
        all_results.append(m)

    out(f"\n{'Config':>25s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9} | {'AvgW':>8} | {'AvgL':>8}")
    out("-" * 105)
    for r in v3_results:
        out(f"  {r['config']:>23s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f} | ${r['avg_winner']:>7,.2f} | ${r['avg_loser']:>7,.2f}")

    # ════════════════════════════════════════════════════════════════════════
    # VARIANT 4: Time-Based Profit Lock
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("VARIANT 4: TIME-BASED PROFIT LOCK")
    out(f"{'=' * 90}")

    lock_bars = [2, 3, 4, 5]
    v4_results = []

    for lb in lock_bars:
        def v4_exit(bars, si, trade, sl_ticks, flatten_h, _lb=lb):
            _exit_time_profit_lock(bars, si, trade, sl_ticks, 560, flatten_h, _lb)

        trades = run_chnavy6(bars, v4_exit, {})
        m = compute_metrics(trades)
        m["config"] = f"Lock@{lb}bars"
        m["lock_bars"] = lb
        m["variant"] = "V4-TimeLock"
        m["exit_reasons"] = exit_reasons_summary(trades)
        m["_trades"] = trades
        v4_results.append(m)
        all_results.append(m)

    out(f"\n{'Config':>25s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9} | {'AvgW':>8} | {'AvgL':>8}")
    out("-" * 105)
    for r in v4_results:
        out(f"  {r['config']:>23s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f} | ${r['avg_winner']:>7,.2f} | ${r['avg_loser']:>7,.2f}")

    # ════════════════════════════════════════════════════════════════════════
    # VARIANT 5: Hybrid (Initial SL + Trail after trigger)
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("VARIANT 5: HYBRID — SL=160t + Trail after trigger (with/without TP cap)")
    out(f"{'=' * 90}")

    hybrid_triggers = [120, 160, 200, 240]
    hybrid_trails = [80, 100, 120, 160]
    v5_results = []

    for trig, trail_d, use_cap in product(hybrid_triggers, hybrid_trails, [True, False]):
        cap_label = "cap560" if use_cap else "noTP"
        def v5_exit(bars, si, trade, sl_ticks, flatten_h, _trig=trig, _td=trail_d, _cap=use_cap):
            _exit_hybrid(bars, si, trade, sl_ticks, 560, flatten_h, _trig, _td, _cap)

        trades = run_chnavy6(bars, v5_exit, {})
        m = compute_metrics(trades)
        m["config"] = f"Trig={trig}t,Trail={trail_d}t,{cap_label}"
        m["trigger"] = trig
        m["trail_dist"] = trail_d
        m["use_tp_cap"] = use_cap
        m["variant"] = "V5-Hybrid"
        m["exit_reasons"] = exit_reasons_summary(trades)
        m["_trades"] = trades
        v5_results.append(m)
        all_results.append(m)

    v5_results.sort(key=lambda x: x["net_pnl"], reverse=True)
    out(f"\n{'Config':>40s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9} | {'AvgW':>8} | {'AvgL':>8}")
    out("-" * 120)
    for r in v5_results:
        out(f"  {r['config']:>38s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f} | ${r['avg_winner']:>7,.2f} | ${r['avg_loser']:>7,.2f}")

    # ════════════════════════════════════════════════════════════════════════
    # OVERALL COMPARISON
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("OVERALL RANKING — ALL VARIANTS vs BASELINE ($4,762)")
    out(f"{'=' * 90}")

    all_results.sort(key=lambda x: x["net_pnl"], reverse=True)
    out(f"\n{'#':>3} | {'Variant':>14} | {'Config':>40s} | {'Trades':>6} | {'Net PnL':>10} | {'Win%':>5} | {'PF':>5} | {'Sharpe':>6} | {'MaxDD':>9}")
    out("-" * 120)
    for i, r in enumerate(all_results[:25], 1):
        delta = r["net_pnl"] - bm["net_pnl"]
        sign = "+" if delta >= 0 else ""
        out(f"  {i:>2} | {r['variant']:>14} | {r['config']:>40s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f}  ({sign}${delta:,.2f} vs baseline)")

    out(f"\n  ... bottom 5:")
    for i, r in enumerate(all_results[-5:], len(all_results) - 4):
        delta = r["net_pnl"] - bm["net_pnl"]
        sign = "+" if delta >= 0 else ""
        out(f"  {i:>2} | {r['variant']:>14} | {r['config']:>40s} | {r['trades']:>6} | ${r['net_pnl']:>9,.2f} | {r['win_rate']:>4.1f}% | {r['pf']:>5.2f} | {r['sharpe']:>6.2f} | ${r['max_dd']:>8,.2f}  ({sign}${delta:,.2f} vs baseline)")

    # ════════════════════════════════════════════════════════════════════════
    # BEST CONFIG TRADE LOG — February and March
    # ════════════════════════════════════════════════════════════════════════
    best = all_results[0]
    best_trades = best["_trades"]

    out(f"\n{'=' * 90}")
    out(f"BEST CONFIG TRADE LOG: {best['variant']} — {best['config']}")
    out(f"Net PnL: ${best['net_pnl']:,.2f}  Trades: {best['trades']}  Win%: {best['win_rate']}%")
    out(f"Exit reasons: {best['exit_reasons']}")
    out(f"{'=' * 90}")

    for month_num, month_name in [(2, "FEBRUARY (best month)"), (3, "MARCH (worst month)")]:
        month_trades = [t for t in best_trades
                        if hasattr(t.entry_time, 'month') and t.entry_time.month == month_num]
        mm = compute_metrics(month_trades)
        out(f"\n  --- {month_name} ---")
        out(f"  Trades: {mm['trades']}  Net PnL: ${mm['net_pnl']:,.2f}  Win%: {mm['win_rate']}%  PF: {mm['pf']}")
        out(f"  {'Entry Time':>22} | {'Side':>5} | {'Entry':>10} | {'Exit':>10} | {'PnL':>10} | {'Reason':>14}")
        out(f"  {'-'*80}")
        for t in month_trades:
            out(f"  {str(t.entry_time):>22} | {t.side:>5} | {t.entry_price:>10.2f} | {t.exit_price:>10.2f} | ${t.pnl:>+9.2f} | {t.exit_reason:>14}")

    # ════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════════════════════════════
    out(f"\n{'=' * 90}")
    out("SUMMARY")
    out(f"{'=' * 90}")

    # Best per variant
    variant_names = ["V1-BE+Trail", "V2-Stepped", "V3-ATR", "V4-TimeLock", "V5-Hybrid"]
    for vn in variant_names:
        vr = [r for r in all_results if r["variant"] == vn]
        if vr:
            best_v = max(vr, key=lambda x: x["net_pnl"])
            delta = best_v["net_pnl"] - bm["net_pnl"]
            sign = "+" if delta >= 0 else ""
            out(f"  Best {vn:>14}: {best_v['config']:>40}  PnL=${best_v['net_pnl']:>9,.2f}  ({sign}${delta:,.2f} vs baseline)  Win%={best_v['win_rate']}%  PF={best_v['pf']}")

    out(f"\n  BASELINE:                                     SL=160t, TP=560t                          PnL=${bm['net_pnl']:>9,.2f}                           Win%={bm['win_rate']}%  PF={bm['pf']}")

    # Write to file
    with open(OUT_PATH, "w") as f:
        f.write(buf.getvalue())
    out(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
