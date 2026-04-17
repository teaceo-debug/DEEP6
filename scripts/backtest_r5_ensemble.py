"""
Round 5: Ensemble Strategies & Advanced Risk Metrics

Tests voting, sequential, and confirmation ensembles across 3 VWAP strategies,
then computes advanced risk metrics and equity curve analysis for all variants.

Data: replay_full_5sessions.duckdb  (1m bars -> 30m resample, RTH 9:00-16:00)
Sessions: Apr 8, 9, 10  (3 RTH calendar dates)
"""

import duckdb
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import math, sys, os

# ── constants ────────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                       "data/backtests/replay_full_5sessions.duckdb")
FLATTEN_H = 16
TRADING_DAYS_PER_YEAR = 252

# Best configs from prior rounds
CFG_CHNAVY6     = dict(sl=200, tp=480, bounce=20, start_h=9.5, end_h=14.5)
CFG_CH2NAVY6    = dict(sl=200, tp=480, bounce=20, start_h=9.5, end_h=14.5)
CFG_CHTRENDNAVY6 = dict(sl=240, tp=200, slope_lb=2, pb=20, start_h=10.0, end_h=14.5)

# ── load & resample ─────────────────────────────────────────────────────────

def load_30m_bars() -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    df = con.execute("""
        SELECT bar_ts, open, high, low, close, volume
        FROM backtest_bars WHERE tf = '1m' ORDER BY bar_ts
    """).fetchdf()
    con.close()

    df["bar_ts"] = pd.to_datetime(df["bar_ts"])
    df = df.set_index("bar_ts")
    df["session_date"] = df.index.date

    frames = []
    for sid, grp in df.groupby("session_date"):
        r = grp.resample("30min").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum", "session_date": "first",
        }).dropna(subset=["open"])
        frames.append(r)
    bars = pd.concat(frames).sort_index().reset_index()
    return bars


# ── Trade dataclass ──────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    session_date: object = None
    strategy: str = ""

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


# ── exit simulation ──────────────────────────────────────────────────────────

def _simulate_exit(bars, start_idx, trade, sl_price, tp_price):
    sess = bars.iloc[min(start_idx, len(bars) - 1)]["session_date"]
    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session_date"] != sess:
            prev_b = bars.iloc[j - 1]
            trade.close(prev_b["close"], "SESSION_END")
            return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= FLATTEN_H:
            trade.close(b["open"], "FLATTEN")
            return
        if trade.side == "LONG":
            if b["low"] <= sl_price:
                trade.close(sl_price, "STOP"); return
            if b["high"] >= tp_price:
                trade.close(tp_price, "TARGET"); return
        else:
            if b["high"] >= sl_price:
                trade.close(sl_price, "STOP"); return
            if b["low"] <= tp_price:
                trade.close(tp_price, "TARGET"); return
    trade.close(bars.iloc[-1]["close"], "DATA_END")


# ── Strategy 1: ChNavy6 ─────────────────────────────────────────────────────

def run_chnavy6(bars, cfg, one_per_day=True):
    trades = []
    cum_tpv = cum_vol = vwap = 0.0
    was_below = was_above = False
    trade_taken_date = None
    prev_date = None

    for i in range(1, len(bars)):
        row = bars.iloc[i]
        prev = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = row["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = vwap = 0.0
            was_below = was_above = False
            trade_taken_date = None
            prev_date = sd

        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        prior_vwap = cum_tpv / cum_vol if cum_vol > 0 else prev["close"]
        cum_tpv += typical * row["volume"]
        cum_vol += row["volume"]
        vwap = cum_tpv / cum_vol if cum_vol > 0 else row["close"]

        if one_per_day and trade_taken_date == sd:
            continue
        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            continue

        if prev["close"] < prior_vwap:
            was_below = True; was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True; was_below = False

        confirm = cfg["bounce"] * TICK_SIZE

        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=sd, strategy="ChNavy6")
            sl_px = entry_px - cfg["sl"] * TICK_SIZE
            tp_px = entry_px + cfg["tp"] * TICK_SIZE
            _simulate_exit(bars, i + 1, t, sl_px, tp_px)
            trades.append(t)
            trade_taken_date = sd

        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=sd, strategy="ChNavy6")
            sl_px = entry_px + cfg["sl"] * TICK_SIZE
            tp_px = entry_px - cfg["tp"] * TICK_SIZE
            _simulate_exit(bars, i + 1, t, sl_px, tp_px)
            trades.append(t)
            trade_taken_date = sd

    return trades


# ── Strategy 2: Ch2Navy6 ────────────────────────────────────────────────────

def run_ch2navy6(bars, cfg, one_per_day=True):
    trades = []
    cum_tpv = cum_vol = 0.0
    trade_taken_date = None
    prev_date = None

    for i in range(2, len(bars)):
        row = bars.iloc[i]
        bar1 = bars.iloc[i - 1]
        bar2 = bars.iloc[i - 2]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = row["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = 0.0
            trade_taken_date = None
            prev_date = sd

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        vwap_prior = cum_tpv / cum_vol if cum_vol > 0 else bar2["close"]
        cum_tpv += typical1 * bar1["volume"]
        cum_vol += bar1["volume"]

        if one_per_day and trade_taken_date == sd:
            continue
        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            continue

        confirm = cfg["bounce"] * TICK_SIZE
        long_setup = (bar2["close"] < vwap_prior and bar1["low"] <= vwap_prior
                      and bar1["close"] > vwap_prior and (bar1["close"] - vwap_prior) >= confirm)
        short_setup = (bar2["close"] > vwap_prior and bar1["high"] >= vwap_prior
                       and bar1["close"] < vwap_prior and (vwap_prior - bar1["close"]) >= confirm)

        if long_setup:
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=sd, strategy="Ch2Navy6")
            _simulate_exit(bars, i, t, entry_px - cfg["sl"] * TICK_SIZE,
                           entry_px + cfg["tp"] * TICK_SIZE)
            trades.append(t); trade_taken_date = sd
        elif short_setup:
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=sd, strategy="Ch2Navy6")
            _simulate_exit(bars, i, t, entry_px + cfg["sl"] * TICK_SIZE,
                           entry_px - cfg["tp"] * TICK_SIZE)
            trades.append(t); trade_taken_date = sd

    return trades


# ── Strategy 3: CHTrendNavy6 ────────────────────────────────────────────────

def run_chtrendnavy6(bars, cfg, one_per_day=True):
    trades = []
    cum_tpv = cum_vol = 0.0
    vwap_hist = []
    trade_taken_date = None
    prev_date = None

    for i in range(2, len(bars)):
        row = bars.iloc[i]
        bar1 = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = row["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = 0.0
            vwap_hist = []
            trade_taken_date = None
            prev_date = sd

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        cum_tpv += typical1 * bar1["volume"]
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]
        vwap_hist.append(vwap_now)

        if one_per_day and trade_taken_date == sd:
            continue
        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            continue
        if len(vwap_hist) <= cfg["slope_lb"]:
            continue

        vwap_slope = vwap_hist[-1] - vwap_hist[-1 - cfg["slope_lb"]]
        band = cfg["pb"] * TICK_SIZE

        long_setup = vwap_slope > 0 and bar1["close"] > vwap_now and bar1["low"] <= vwap_now + band
        short_setup = vwap_slope < 0 and bar1["close"] < vwap_now and bar1["high"] >= vwap_now - band

        if long_setup:
            entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px, session_date=sd, strategy="CHTrendNavy6")
            _simulate_exit(bars, i, t, entry_px - cfg["sl"] * TICK_SIZE,
                           entry_px + cfg["tp"] * TICK_SIZE)
            trades.append(t); trade_taken_date = sd
        elif short_setup:
            entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px, session_date=sd, strategy="CHTrendNavy6")
            _simulate_exit(bars, i, t, entry_px + cfg["sl"] * TICK_SIZE,
                           entry_px - cfg["tp"] * TICK_SIZE)
            trades.append(t); trade_taken_date = sd

    return trades


# ── Signal extraction (no trade, just signal + direction per bar) ────────────

def get_signals_chnavy6(bars, cfg):
    """Return list of (bar_index, session_date, side) for every signal."""
    signals = []
    cum_tpv = cum_vol = vwap = 0.0
    was_below = was_above = False
    prev_date = None

    for i in range(1, len(bars)):
        row = bars.iloc[i]
        prev = bars.iloc[i - 1]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = row["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = vwap = 0.0
            was_below = was_above = False
            prev_date = sd

        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        prior_vwap = cum_tpv / cum_vol if cum_vol > 0 else prev["close"]
        cum_tpv += typical * row["volume"]
        cum_vol += row["volume"]
        vwap = cum_tpv / cum_vol if cum_vol > 0 else row["close"]

        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            if prev["close"] < prior_vwap:
                was_below = True; was_above = False
            elif prev["close"] > prior_vwap:
                was_above = True; was_below = False
            continue

        if prev["close"] < prior_vwap:
            was_below = True; was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True; was_below = False

        confirm = cfg["bounce"] * TICK_SIZE

        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            signals.append((i, sd, "LONG"))
        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            signals.append((i, sd, "SHORT"))

    return signals


def get_signals_ch2navy6(bars, cfg):
    signals = []
    cum_tpv = cum_vol = 0.0
    prev_date = None

    for i in range(2, len(bars)):
        row = bars.iloc[i]
        bar1 = bars.iloc[i - 1]
        bar2 = bars.iloc[i - 2]
        ts = row["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = row["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = 0.0
            prev_date = sd

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        vwap_prior = cum_tpv / cum_vol if cum_vol > 0 else bar2["close"]
        cum_tpv += typical1 * bar1["volume"]
        cum_vol += bar1["volume"]

        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            continue

        confirm = cfg["bounce"] * TICK_SIZE
        if (bar2["close"] < vwap_prior and bar1["low"] <= vwap_prior
                and bar1["close"] > vwap_prior and (bar1["close"] - vwap_prior) >= confirm):
            signals.append((i, sd, "LONG"))
        elif (bar2["close"] > vwap_prior and bar1["high"] >= vwap_prior
              and bar1["close"] < vwap_prior and (vwap_prior - bar1["close"]) >= confirm):
            signals.append((i, sd, "SHORT"))

    return signals


def get_signals_chtrendnavy6(bars, cfg):
    signals = []
    cum_tpv = cum_vol = 0.0
    vwap_hist = []
    prev_date = None

    for i in range(2, len(bars)):
        bar1 = bars.iloc[i - 1]
        ts = bars.iloc[i]["bar_ts"]
        hour = ts.hour + ts.minute / 60.0
        sd = bars.iloc[i]["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = 0.0
            vwap_hist = []
            prev_date = sd

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        cum_tpv += typical1 * bar1["volume"]
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]
        vwap_hist.append(vwap_now)

        if hour < cfg["start_h"] or hour > cfg["end_h"]:
            continue
        if len(vwap_hist) <= cfg["slope_lb"]:
            continue

        vwap_slope = vwap_hist[-1] - vwap_hist[-1 - cfg["slope_lb"]]
        band = cfg["pb"] * TICK_SIZE

        if vwap_slope > 0 and bar1["close"] > vwap_now and bar1["low"] <= vwap_now + band:
            signals.append((i, sd, "LONG", vwap_slope))
        elif vwap_slope < 0 and bar1["close"] < vwap_now and bar1["high"] >= vwap_now - band:
            signals.append((i, sd, "SHORT", vwap_slope))

    return signals


# ── Ensemble: Voting ─────────────────────────────────────────────────────────

def ensemble_voting(bars):
    """Only trade when 2+ strategies agree on direction on same session date.
    Takes the first agreeing bar index and enters there."""
    sig1 = get_signals_chnavy6(bars, CFG_CHNAVY6)
    sig2 = get_signals_ch2navy6(bars, CFG_CH2NAVY6)
    sig3_raw = get_signals_chtrendnavy6(bars, CFG_CHTRENDNAVY6)
    sig3 = [(s[0], s[1], s[2]) for s in sig3_raw]  # strip slope

    # Group first signal per session per strategy
    def first_per_session(sigs):
        seen = {}
        for s in sigs:
            idx, sd, side = s[0], s[1], s[2]
            if sd not in seen:
                seen[sd] = (idx, side)
        return seen

    s1 = first_per_session(sig1)
    s2 = first_per_session(sig2)
    s3 = first_per_session(sig3)

    all_dates = set(list(s1.keys()) + list(s2.keys()) + list(s3.keys()))
    trades = []

    for sd in sorted(all_dates):
        votes = {}
        entries = {}  # side -> list of (bar_idx, strategy_name)
        for name, smap in [("ChNavy6", s1), ("Ch2Navy6", s2), ("CHTrendNavy6", s3)]:
            if sd in smap:
                idx, side = smap[sd]
                votes[name] = side
                entries.setdefault(side, []).append((idx, name))

        # Need 2+ agreeing
        for side, elist in entries.items():
            if len(elist) >= 2:
                # Use earliest bar index among agreeing strategies
                entry_idx = min(e[0] for e in elist)
                row = bars.iloc[entry_idx]
                # Use ChNavy6 config for SL/TP (most common)
                cfg = CFG_CHNAVY6
                if side == "LONG":
                    entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
                    t = Trade(row["bar_ts"], "LONG", entry_px,
                              session_date=sd, strategy="Voting")
                    _simulate_exit(bars, entry_idx, t,
                                   entry_px - cfg["sl"] * TICK_SIZE,
                                   entry_px + cfg["tp"] * TICK_SIZE)
                else:
                    entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
                    t = Trade(row["bar_ts"], "SHORT", entry_px,
                              session_date=sd, strategy="Voting")
                    _simulate_exit(bars, entry_idx, t,
                                   entry_px + cfg["sl"] * TICK_SIZE,
                                   entry_px - cfg["tp"] * TICK_SIZE)
                trades.append(t)
                break  # 1 trade per day

    return trades


# ── Ensemble: Sequential ────────────────────────────────────────────────────

def ensemble_sequential(bars):
    """If Strategy A (ChNavy6) hits SL, allow Strategy B (Ch2Navy6) that day.
    If B also hits SL, allow C (CHTrendNavy6)."""
    # Run all 3 with 1-per-day
    t1 = run_chnavy6(bars, CFG_CHNAVY6, one_per_day=True)
    t2 = run_ch2navy6(bars, CFG_CH2NAVY6, one_per_day=True)
    t3 = run_chtrendnavy6(bars, CFG_CHTRENDNAVY6, one_per_day=True)

    # Map by session_date
    def by_date(tlist):
        d = {}
        for t in tlist:
            d[t.session_date] = t
        return d

    d1, d2, d3 = by_date(t1), by_date(t2), by_date(t3)
    all_dates = sorted(set(list(d1.keys()) + list(d2.keys()) + list(d3.keys())))

    trades = []
    for sd in all_dates:
        # Try A first
        if sd in d1:
            t = d1[sd]
            t_copy = Trade(t.entry_time, t.side, t.entry_price,
                           t.exit_price, t.exit_reason, t.pnl, sd, "Seq-A(ChNavy6)")
            trades.append(t_copy)
            if t.exit_reason == "STOP":
                # A stopped out, try B
                if sd in d2 and d2[sd].entry_time > t.entry_time:
                    t2t = d2[sd]
                    t_copy2 = Trade(t2t.entry_time, t2t.side, t2t.entry_price,
                                    t2t.exit_price, t2t.exit_reason, t2t.pnl,
                                    sd, "Seq-B(Ch2Navy6)")
                    trades.append(t_copy2)
                    if t2t.exit_reason == "STOP" and sd in d3 and d3[sd].entry_time > t2t.entry_time:
                        t3t = d3[sd]
                        t_copy3 = Trade(t3t.entry_time, t3t.side, t3t.entry_price,
                                        t3t.exit_price, t3t.exit_reason, t3t.pnl,
                                        sd, "Seq-C(CHTrend)")
                        trades.append(t_copy3)
        else:
            # No A signal, try B
            if sd in d2:
                t2t = d2[sd]
                t_copy2 = Trade(t2t.entry_time, t2t.side, t2t.entry_price,
                                t2t.exit_price, t2t.exit_reason, t2t.pnl,
                                sd, "Seq-B(Ch2Navy6)")
                trades.append(t_copy2)
                if t2t.exit_reason == "STOP" and sd in d3 and d3[sd].entry_time > t2t.entry_time:
                    t3t = d3[sd]
                    t_copy3 = Trade(t3t.entry_time, t3t.side, t3t.entry_price,
                                    t3t.exit_price, t3t.exit_reason, t3t.pnl,
                                    sd, "Seq-C(CHTrend)")
                    trades.append(t_copy3)
            elif sd in d3:
                t3t = d3[sd]
                t_copy3 = Trade(t3t.entry_time, t3t.side, t3t.entry_price,
                                t3t.exit_price, t3t.exit_reason, t3t.pnl,
                                sd, "Seq-C(CHTrend)")
                trades.append(t_copy3)

    return trades


# ── Ensemble: Confirmation (CHTrend slope filter for bounce/rejection) ──────

def ensemble_confirmation(bars):
    """Use CHTrendNavy6 slope as directional filter for ChNavy6/Ch2Navy6.
    Only take bounce/rejection trades in the direction of the VWAP slope."""
    # Get slope per session from CHTrend signals
    sig_trend_raw = get_signals_chtrendnavy6(bars, CFG_CHTRENDNAVY6)

    # Compute slope for each session using CHTrend's VWAP
    # We need session-level slope, so compute rolling VWAP slope per bar
    cum_tpv = cum_vol = 0.0
    vwap_hist = []
    prev_date = None
    slope_by_bar = {}  # bar_index -> slope value

    for i in range(2, len(bars)):
        bar1 = bars.iloc[i - 1]
        sd = bars.iloc[i]["session_date"]

        if sd != prev_date:
            cum_tpv = cum_vol = 0.0
            vwap_hist = []
            prev_date = sd

        typical1 = (bar1["high"] + bar1["low"] + bar1["close"]) / 3.0
        cum_tpv += typical1 * bar1["volume"]
        cum_vol += bar1["volume"]
        vwap_now = cum_tpv / cum_vol if cum_vol > 0 else bar1["close"]
        vwap_hist.append(vwap_now)

        if len(vwap_hist) > CFG_CHTRENDNAVY6["slope_lb"]:
            slope_by_bar[i] = vwap_hist[-1] - vwap_hist[-1 - CFG_CHTRENDNAVY6["slope_lb"]]

    # Get all ChNavy6 and Ch2Navy6 signals (no 1-per-day filter yet)
    sig_ch = get_signals_chnavy6(bars, CFG_CHNAVY6)
    sig_ch2 = get_signals_ch2navy6(bars, CFG_CH2NAVY6)

    trades = []
    trade_taken_dates = set()

    # Merge and sort all signals by bar index
    all_sigs = []
    for idx, sd, side in sig_ch:
        all_sigs.append((idx, sd, side, "ChNavy6"))
    for idx, sd, side in sig_ch2:
        all_sigs.append((idx, sd, side, "Ch2Navy6"))
    all_sigs.sort(key=lambda x: x[0])

    for idx, sd, side, strat_name in all_sigs:
        if sd in trade_taken_dates:
            continue

        # Get slope at this bar index (use nearest available)
        slope = slope_by_bar.get(idx, None)
        if slope is None:
            # Try nearby bars
            for offset in range(-2, 3):
                slope = slope_by_bar.get(idx + offset, None)
                if slope is not None:
                    break
        if slope is None:
            continue

        # Filter: only take LONG if slope > 0, SHORT if slope < 0
        if side == "LONG" and slope <= 0:
            continue
        if side == "SHORT" and slope >= 0:
            continue

        row = bars.iloc[idx]
        cfg = CFG_CHNAVY6 if strat_name == "ChNavy6" else CFG_CH2NAVY6

        if side == "LONG":
            if strat_name == "ChNavy6":
                entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            else:
                entry_px = row["open"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(row["bar_ts"], "LONG", entry_px,
                      session_date=sd, strategy=f"Confirm({strat_name})")
            _simulate_exit(bars, idx + 1 if strat_name == "ChNavy6" else idx,
                           t, entry_px - cfg["sl"] * TICK_SIZE,
                           entry_px + cfg["tp"] * TICK_SIZE)
        else:
            if strat_name == "ChNavy6":
                entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            else:
                entry_px = row["open"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(row["bar_ts"], "SHORT", entry_px,
                      session_date=sd, strategy=f"Confirm({strat_name})")
            _simulate_exit(bars, idx + 1 if strat_name == "ChNavy6" else idx,
                           t, entry_px + cfg["sl"] * TICK_SIZE,
                           entry_px - cfg["tp"] * TICK_SIZE)

        trades.append(t)
        trade_taken_dates.add(sd)

    return trades


# ── Advanced Risk Metrics ────────────────────────────────────────────────────

def compute_advanced_metrics(trades, label=""):
    """Compute all Part B + Part C metrics."""
    result = {"label": label, "trades": len(trades)}

    if len(trades) == 0:
        for k in ["net_pnl", "win_rate", "avg_pnl", "max_dd", "profit_factor",
                   "sharpe", "sortino", "calmar", "avg_winner", "avg_loser",
                   "win_loss_ratio", "expectancy", "max_consec_losers",
                   "recovery_factor", "risk_of_ruin", "kelly_pct",
                   "eq_r2", "time_in_dd_pct", "largest_trade_impact"]:
            result[k] = 0.0
        result["winners"] = 0
        result["losers"] = 0
        return result

    pnls = [t.pnl for t in trades]
    n = len(pnls)

    # Basic
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    net_pnl = sum(pnls)
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    win_rate = len(winners) / n
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    result["net_pnl"] = round(net_pnl, 2)
    result["winners"] = len(winners)
    result["losers"] = len(losers)
    result["win_rate"] = round(win_rate * 100, 1)
    result["profit_factor"] = round(pf, 2)

    # Equity curve
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
    result["max_dd"] = round(max_dd, 2)

    # Daily returns (group trades by session_date)
    daily_pnl = {}
    for t in trades:
        sd = t.session_date
        daily_pnl[sd] = daily_pnl.get(sd, 0.0) + t.pnl
    daily_returns = list(daily_pnl.values())
    n_days = len(daily_returns)

    # Sharpe ratio (annualized)
    if n_days > 1 and np.std(daily_returns, ddof=1) > 1e-10:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns, ddof=1)) * np.sqrt(TRADING_DAYS_PER_YEAR)
    elif np.mean(daily_returns) > 0:
        sharpe = float("inf")
    else:
        sharpe = 0.0
    result["sharpe"] = round(sharpe, 3) if not np.isinf(sharpe) else "inf"

    # Sortino ratio (downside deviation)
    downside = [r for r in daily_returns if r < 0]
    if len(downside) > 0:
        downside_std = np.sqrt(np.mean(np.array(downside) ** 2))
        sortino = (np.mean(daily_returns) / downside_std) * np.sqrt(TRADING_DAYS_PER_YEAR) if downside_std > 0 else 0.0
    else:
        sortino = float("inf") if np.mean(daily_returns) > 0 else 0.0
    result["sortino"] = round(sortino, 3) if not np.isinf(sortino) else "inf"

    # Calmar ratio
    ann_return = np.mean(daily_returns) * TRADING_DAYS_PER_YEAR if n_days > 0 else 0.0
    if max_dd > 0:
        calmar = ann_return / max_dd
    elif ann_return > 0:
        calmar = float("inf")
    else:
        calmar = 0.0
    result["calmar"] = round(calmar, 3) if not np.isinf(calmar) else "inf"

    # Avg winner / avg loser
    avg_w = np.mean(winners) if winners else 0.0
    avg_l = abs(np.mean(losers)) if losers else 0.0
    result["avg_winner"] = round(avg_w, 2)
    result["avg_loser"] = round(avg_l, 2)
    result["win_loss_ratio"] = round(avg_w / avg_l, 3) if avg_l > 0 else "inf"
    result["avg_pnl"] = round(np.mean(pnls), 2)

    # Expectancy
    expectancy = win_rate * avg_w - (1 - win_rate) * avg_l
    result["expectancy"] = round(expectancy, 2)

    # Max consecutive losers
    max_consec = 0
    consec = 0
    for p in pnls:
        if p <= 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    result["max_consec_losers"] = max_consec

    # Recovery factor
    result["recovery_factor"] = round(net_pnl / max_dd, 3) if max_dd > 0 else "inf"

    # Risk of ruin (simplified formula using win rate and avg win/loss ratio)
    # Using the formula: RoR = ((1-edge)/(1+edge))^units
    # where edge = win_rate * (avg_w/avg_l) - (1-win_rate)
    # Simplified: if edge <= 0, ruin = 100%
    if avg_l > 0 and win_rate < 1.0:
        wl_ratio = avg_w / avg_l
        edge = win_rate * wl_ratio - (1 - win_rate)
        if edge > 0:
            # Using simpler formula: RoR = ((1-p)/(p))^N where p=adjusted win rate
            # Approximation via Kelly: if Kelly is positive, ruin decreases exponentially
            q = 1 - win_rate
            if wl_ratio > 0:
                ror = (q / (win_rate * wl_ratio)) ** 3 if (win_rate * wl_ratio) > q else 1.0
                ror = min(ror, 1.0)
            else:
                ror = 1.0
        else:
            ror = 1.0
    else:
        ror = 0.0 if win_rate == 1.0 else 1.0
    result["risk_of_ruin"] = round(ror * 100, 1)

    # Kelly criterion
    if avg_l > 0:
        wl_ratio = avg_w / avg_l
        kelly = win_rate - (1 - win_rate) / wl_ratio if wl_ratio > 0 else 0.0
    else:
        kelly = 1.0 if win_rate > 0 else 0.0
    result["kelly_pct"] = round(kelly * 100, 1)

    # Equity curve smoothness (R^2 of linear fit)
    if len(equity) >= 2:
        x = np.arange(len(equity))
        coeffs = np.polyfit(x, equity, 1)
        fitted = np.polyval(coeffs, x)
        ss_res = np.sum((equity - fitted) ** 2)
        ss_tot = np.sum((equity - np.mean(equity)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    else:
        r2 = 0.0
    result["eq_r2"] = round(r2, 4)

    # Time in drawdown
    in_dd = np.sum(drawdown > 0)
    result["time_in_dd_pct"] = round(in_dd / len(drawdown) * 100, 1) if len(drawdown) > 0 else 0.0

    # Largest single trade impact
    if len(pnls) > 0:
        largest_abs = max(pnls, key=abs)
        impact = abs(largest_abs) / abs(net_pnl) * 100 if net_pnl != 0 else 0.0
        result["largest_trade_impact"] = f"${largest_abs:+.2f} ({impact:.1f}% of net PnL)"
    else:
        result["largest_trade_impact"] = "$0.00"

    return result


# ── Formatting ───────────────────────────────────────────────────────────────

def format_metrics(m, indent="  "):
    lines = []
    lines.append(f"{indent}Trades: {m['trades']}  (W: {m.get('winners',0)} / L: {m.get('losers',0)})")
    lines.append(f"{indent}Net PnL:          ${m['net_pnl']:>10,.2f}")
    lines.append(f"{indent}Win Rate:         {m['win_rate']:>10}%")
    lines.append(f"{indent}Profit Factor:    {m['profit_factor']:>10}")
    lines.append(f"{indent}Avg PnL/trade:    ${m['avg_pnl']:>10,.2f}")
    lines.append(f"{indent}Max Drawdown:     ${m['max_dd']:>10,.2f}")
    lines.append(f"")
    lines.append(f"{indent}--- Advanced Risk Metrics ---")
    lines.append(f"{indent}Sharpe (ann.):    {m['sharpe']:>10}")
    lines.append(f"{indent}Sortino (ann.):   {str(m['sortino']):>10}")
    lines.append(f"{indent}Calmar (ann.):    {m['calmar']:>10}")
    lines.append(f"{indent}Avg Winner:       ${m['avg_winner']:>10,.2f}")
    lines.append(f"{indent}Avg Loser:        ${m['avg_loser']:>10,.2f}")
    lines.append(f"{indent}Win/Loss Ratio:   {str(m['win_loss_ratio']):>10}")
    lines.append(f"{indent}Expectancy:       ${m['expectancy']:>10,.2f}")
    lines.append(f"{indent}Max Consec Losers:{m['max_consec_losers']:>10}")
    lines.append(f"{indent}Recovery Factor:  {str(m['recovery_factor']):>10}")
    lines.append(f"{indent}Risk of Ruin:     {m['risk_of_ruin']:>10}%")
    lines.append(f"{indent}Kelly %:          {m['kelly_pct']:>10}%")
    lines.append(f"")
    lines.append(f"{indent}--- Equity Curve Analysis ---")
    lines.append(f"{indent}Eq. Smoothness R²:{m['eq_r2']:>10}")
    lines.append(f"{indent}Time in Drawdown: {m['time_in_dd_pct']:>10}%")
    lines.append(f"{indent}Largest Trade:    {m['largest_trade_impact']}")
    return "\n".join(lines)


def format_trade_list(trades, indent="    "):
    lines = []
    for t in trades:
        lines.append(f"{indent}{t.entry_time}  {t.side:5s}  "
                      f"entry={t.entry_price:.2f}  exit={t.exit_price:.2f}  "
                      f"pnl=${t.pnl:+,.2f}  [{t.exit_reason}]  {t.strategy}")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    bars = load_30m_bars()
    print(f"Loaded {len(bars)} 30-min bars")

    out = []
    out.append("=" * 90)
    out.append("ROUND 5: ENSEMBLE STRATEGIES & ADVANCED RISK METRICS")
    out.append(f"Data: 3 RTH sessions (Apr 8-10, 2026)  |  30-min NQ bars")
    out.append("=" * 90)

    # ── Part A: Individual strategies ──
    out.append("\n" + "=" * 90)
    out.append("PART A: INDIVIDUAL STRATEGIES (Best Configs)")
    out.append("=" * 90)

    t_ch = run_chnavy6(bars, CFG_CHNAVY6)
    t_ch2 = run_ch2navy6(bars, CFG_CH2NAVY6)
    t_trend = run_chtrendnavy6(bars, CFG_CHTRENDNAVY6)

    all_individual = [
        ("ChNavy6", t_ch, f"SL={CFG_CHNAVY6['sl']}, TP={CFG_CHNAVY6['tp']}, Bounce={CFG_CHNAVY6['bounce']}, Start={CFG_CHNAVY6['start_h']}, End={CFG_CHNAVY6['end_h']}"),
        ("Ch2Navy6", t_ch2, f"SL={CFG_CH2NAVY6['sl']}, TP={CFG_CH2NAVY6['tp']}, Bounce={CFG_CH2NAVY6['bounce']}, Start={CFG_CH2NAVY6['start_h']}, End={CFG_CH2NAVY6['end_h']}"),
        ("CHTrendNavy6", t_trend, f"SL={CFG_CHTRENDNAVY6['sl']}, TP={CFG_CHTRENDNAVY6['tp']}, SlopeLB={CFG_CHTRENDNAVY6['slope_lb']}, PB={CFG_CHTRENDNAVY6['pb']}, Start={CFG_CHTRENDNAVY6['start_h']}, End={CFG_CHTRENDNAVY6['end_h']}"),
    ]

    metrics_individual = []
    for name, trades, params in all_individual:
        m = compute_advanced_metrics(trades, name)
        metrics_individual.append(m)
        out.append(f"\n{'─' * 70}")
        out.append(f"  {name}  ({params})")
        out.append(f"{'─' * 70}")
        out.append(format_metrics(m))
        out.append(f"\n  Trade Detail:")
        out.append(format_trade_list(trades))

    # ── Part A: Ensembles ──
    out.append("\n\n" + "=" * 90)
    out.append("PART A: ENSEMBLE STRATEGIES")
    out.append("=" * 90)

    # Voting
    t_voting = ensemble_voting(bars)
    m_voting = compute_advanced_metrics(t_voting, "Voting (2+ agree)")
    out.append(f"\n{'─' * 70}")
    out.append(f"  VOTING ENSEMBLE: Trade when 2+ strategies agree on direction")
    out.append(f"{'─' * 70}")
    out.append(format_metrics(m_voting))
    out.append(f"\n  Trade Detail:")
    out.append(format_trade_list(t_voting))

    # Sequential
    t_seq = ensemble_sequential(bars)
    m_seq = compute_advanced_metrics(t_seq, "Sequential (A->B->C)")
    out.append(f"\n{'─' * 70}")
    out.append(f"  SEQUENTIAL ENSEMBLE: If A stops out, try B; if B stops out, try C")
    out.append(f"{'─' * 70}")
    out.append(format_metrics(m_seq))
    out.append(f"\n  Trade Detail:")
    out.append(format_trade_list(t_seq))

    # Confirmation
    t_conf = ensemble_confirmation(bars)
    m_conf = compute_advanced_metrics(t_conf, "Confirmation (slope filter)")
    out.append(f"\n{'─' * 70}")
    out.append(f"  CONFIRMATION ENSEMBLE: CHTrend slope filters ChNavy6/Ch2Navy6 direction")
    out.append(f"{'─' * 70}")
    out.append(format_metrics(m_conf))
    out.append(f"\n  Trade Detail:")
    out.append(format_trade_list(t_conf))

    # ── Comparison ──
    out.append("\n\n" + "=" * 90)
    out.append("ENSEMBLE vs INDIVIDUAL COMPARISON")
    out.append("=" * 90)

    all_metrics = metrics_individual + [m_voting, m_seq, m_conf]
    header = f"{'Strategy':<30s} {'Trades':>6s} {'Net PnL':>10s} {'Win%':>6s} {'PF':>6s} {'Sharpe':>7s} {'MaxDD':>10s} {'Kelly%':>7s} {'Expect':>8s}"
    out.append(f"\n  {header}")
    out.append(f"  {'─' * len(header)}")
    for m in all_metrics:
        sharpe_s = str(m['sharpe']) if not isinstance(m['sharpe'], float) else f"{m['sharpe']:.3f}"
        pf_s = str(m['profit_factor']) if not isinstance(m['profit_factor'], float) else f"{m['profit_factor']:.2f}"
        out.append(f"  {m['label']:<30s} {m['trades']:>6d} ${m['net_pnl']:>9,.2f} "
                    f"{m['win_rate']:>5}% {pf_s:>6} "
                    f"{sharpe_s:>7} ${m['max_dd']:>9,.2f} "
                    f"{m['kelly_pct']:>6}% ${m['expectancy']:>7,.2f}")

    # ── Part B: Summary table of advanced metrics ──
    out.append("\n\n" + "=" * 90)
    out.append("PART B: ADVANCED RISK METRICS SUMMARY")
    out.append("=" * 90)

    for m in all_metrics:
        out.append(f"\n  {m['label']}:")
        out.append(f"    Sharpe={m['sharpe']}, Sortino={m['sortino']}, Calmar={m['calmar']}")
        out.append(f"    AvgW=${m['avg_winner']:.2f}, AvgL=${m['avg_loser']:.2f}, W/L Ratio={m['win_loss_ratio']}")
        out.append(f"    Expectancy=${m['expectancy']:.2f}/trade, MaxConsecLosers={m['max_consec_losers']}")
        out.append(f"    RecoveryFactor={m['recovery_factor']}, RiskOfRuin={m['risk_of_ruin']}%, Kelly={m['kelly_pct']}%")

    # ── Part C: Equity Curve Analysis ──
    out.append("\n\n" + "=" * 90)
    out.append("PART C: EQUITY CURVE ANALYSIS")
    out.append("=" * 90)

    all_trade_sets = [
        ("ChNavy6", t_ch), ("Ch2Navy6", t_ch2), ("CHTrendNavy6", t_trend),
        ("Voting", t_voting), ("Sequential", t_seq), ("Confirmation", t_conf),
    ]

    for name, trades in all_trade_sets:
        m = [x for x in all_metrics if x["label"] == name or
             (name == "Voting" and x["label"] == "Voting (2+ agree)") or
             (name == "Sequential" and x["label"] == "Sequential (A->B->C)") or
             (name == "Confirmation" and x["label"] == "Confirmation (slope filter)")][0]

        out.append(f"\n  {name}:")
        if len(trades) == 0:
            out.append(f"    No trades — equity curve is flat")
            continue

        pnls = [t.pnl for t in trades]
        equity = np.cumsum(pnls)
        out.append(f"    Equity curve: {' -> '.join([f'${e:,.2f}' for e in equity])}")
        out.append(f"    Smoothness (R²):       {m['eq_r2']}")
        out.append(f"    Time in Drawdown:      {m['time_in_dd_pct']}%")
        out.append(f"    Largest Trade Impact:   {m['largest_trade_impact']}")

    # ── Final verdict ──
    out.append("\n\n" + "=" * 90)
    out.append("ROUND 5 VERDICT")
    out.append("=" * 90)

    best = max(all_metrics, key=lambda x: x["net_pnl"])
    out.append(f"\n  Best by Net PnL:    {best['label']} (${best['net_pnl']:,.2f})")

    profitable = [m for m in all_metrics if m["net_pnl"] > 0]
    if profitable:
        def _numeric(v):
            if isinstance(v, (int, float)):
                return v if not np.isinf(v) else 1e12
            if v == "inf":
                return 1e12
            return 0
        best_sharpe = max(profitable, key=lambda x: _numeric(x["sharpe"]))
        out.append(f"  Best by Sharpe:     {best_sharpe['label']} ({best_sharpe['sharpe']})")
        best_pf = max(profitable, key=lambda x: _numeric(x["profit_factor"]))
        out.append(f"  Best by PF:         {best_pf['label']} ({best_pf['profit_factor']})")

    # Risk assessment
    out.append(f"\n  Risk Assessment:")
    for m in all_metrics:
        kelly = m["kelly_pct"]
        ror = m["risk_of_ruin"]
        verdict = "FAVORABLE" if kelly > 0 and ror < 50 else "MARGINAL" if kelly > 0 else "UNFAVORABLE"
        out.append(f"    {m['label']:<30s}  Kelly={kelly}%  RoR={ror}%  -> {verdict}")

    out.append("\n" + "=" * 90)
    out.append("END OF ROUND 5 REPORT")
    out.append("=" * 90)

    report = "\n".join(out)
    print(report)

    results_path = os.path.join(os.path.dirname(__file__), "results_r5_ensemble.txt")
    with open(results_path, "w") as f:
        f.write(report)
    print(f"\nResults written to {results_path}")


if __name__ == "__main__":
    main()
