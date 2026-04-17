"""
opt4_time_day_vol.py — Time-of-day, day-of-week, volume, and direction filters
for ChNavy6 (VWAP Bounce) on 30-minute NQ bars.

Data source: nq_3mo_1m.csv (96,100 1-min bars, Jan 2 – Apr 10, 2026)
Baseline: SL=160t, TP=560t, +$4,762, 29.8% WR, 47 trades, 86 days
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
import sys, os

# ── constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_PER_SIDE = 0.35
SLIPPAGE_TICKS = 1

SL_TICKS = 160
TP_TICKS = 560
BOUNCE_CONFIRM_TICKS = 20  # 5 pts
START_H = 9.5
END_H = 14.5
FLATTEN_H = 16.0

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "backtests", "nq_3mo_1m.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "opt4_time_day_vol.txt")

# ── load & resample ───────────────────────────────────────────────────────

def load_30m_bars() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df = df.set_index("ts_event").sort_index()

    # Convert to US/Eastern
    df.index = df.index.tz_convert("US/Eastern")
    df["date"] = df.index.date

    # Resample to 30m within each calendar date
    frames = []
    for dt, grp in df.groupby("date"):
        r = grp.resample("30min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna(subset=["open"])
        r["date"] = dt
        frames.append(r)

    bars = pd.concat(frames).sort_index()
    bars = bars.reset_index().rename(columns={"ts_event": "bar_ts"})
    # Assign integer session IDs
    unique_dates = sorted(bars["date"].unique())
    date_to_id = {d: i for i, d in enumerate(unique_dates)}
    bars["session"] = bars["date"].map(date_to_id)
    return bars, unique_dates


# ── trade object ─────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_time: pd.Timestamp
    side: str
    entry_price: float
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0
    signal_bar_volume: float = 0.0
    signal_bar_slot: str = ""

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


# ── exit simulation ──────────────────────────────────────────────────────

def _simulate_exit(bars: pd.DataFrame, start_idx: int, trade: Trade,
                   sl_price: float, tp_price: float):
    sess = bars.iloc[min(start_idx, len(bars) - 1)]["session"]
    for j in range(start_idx, len(bars)):
        b = bars.iloc[j]
        if b["session"] != sess:
            prev_b = bars.iloc[j - 1]
            trade.close(prev_b["close"], "SESSION_END")
            return
        hour = b["bar_ts"].hour + b["bar_ts"].minute / 60.0
        if hour >= FLATTEN_H:
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
    trade.close(bars.iloc[-1]["close"], "DATA_END")


# ── ChNavy6 strategy with metadata ──────────────────────────────────────

def run_chnavy6(bars: pd.DataFrame,
                allowed_slots=None,       # set of "HH:MM" strings
                allowed_days=None,        # set of day names
                vol_threshold_pct=None,   # e.g. 1.2 means 120% of avg
                vol_avg_by_slot=None,     # dict: (day_of_week, "HH:MM") -> avg_vol
                direction_filter=None,    # "LONG", "SHORT", or None
                ) -> list[Trade]:
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

        # compute VWAP
        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        tpv = typical * row["volume"]
        prior_vwap = cum_tpv / cum_vol if cum_vol > 0 else prev["close"]
        cum_tpv += tpv
        cum_vol += row["volume"]
        vwap = cum_tpv / cum_vol if cum_vol > 0 else row["close"]

        if trade_taken:
            continue
        if hour < START_H or hour > END_H:
            continue

        # track position relative to VWAP
        if prev["close"] < prior_vwap:
            was_below = True
            was_above = False
        elif prev["close"] > prior_vwap:
            was_above = True
            was_below = False

        confirm = BOUNCE_CONFIRM_TICKS * TICK_SIZE

        # Determine signal
        side = None
        if was_below and row["close"] > vwap and (row["close"] - vwap) >= confirm:
            side = "LONG"
        elif was_above and row["close"] < vwap and (vwap - row["close"]) >= confirm:
            side = "SHORT"

        if side is None:
            continue

        # Time slot
        slot = f"{ts.hour:02d}:{ts.minute:02d}"
        day_name = ts.strftime("%A")

        # ── FILTERS ──
        if allowed_slots is not None and slot not in allowed_slots:
            continue
        if allowed_days is not None and day_name not in allowed_days:
            continue
        if direction_filter is not None and side != direction_filter:
            continue
        if vol_threshold_pct is not None and vol_avg_by_slot is not None:
            key = slot  # use slot only (across all days)
            avg_v = vol_avg_by_slot.get(key, None)
            if avg_v is not None and avg_v > 0:
                if row["volume"] < vol_threshold_pct * avg_v:
                    continue

        # Entry
        if side == "LONG":
            entry_px = row["close"] + SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "LONG", entry_px)
            sl_px = entry_px - SL_TICKS * TICK_SIZE
            tp_px = entry_px + TP_TICKS * TICK_SIZE
        else:
            entry_px = row["close"] - SLIPPAGE_TICKS * TICK_SIZE
            t = Trade(ts, "SHORT", entry_px)
            sl_px = entry_px + SL_TICKS * TICK_SIZE
            tp_px = entry_px - TP_TICKS * TICK_SIZE

        t.signal_bar_volume = row["volume"]
        t.signal_bar_slot = slot

        _simulate_exit(bars, i + 1, t, sl_px, tp_px)
        trades.append(t)
        trade_taken = True

    return trades


# ── metrics ──────────────────────────────────────────────────────────────

def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0, "net_pnl": 0, "win_rate": 0, "avg_win": 0,
                "avg_loss": 0, "max_dd": 0, "profit_factor": 0, "sharpe": 0,
                "winners": 0, "losers": 0}

    pnls = [t.pnl for t in trades]
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = peak - equity
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0

    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    avg_win = np.mean(winners) if winners else 0
    avg_loss = np.mean(losers) if losers else 0

    # Annualized Sharpe (daily returns approx)
    sharpe = 0.0
    if len(pnls) > 1 and np.std(pnls) > 0:
        sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252)

    return {
        "trades": len(trades),
        "net_pnl": round(sum(pnls), 2),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_dd": round(max_dd, 2),
        "profit_factor": round(pf, 2),
        "sharpe": round(sharpe, 2),
        "winners": len(winners),
        "losers": len(losers),
    }


def fmt_metrics(m: dict) -> str:
    return (f"Trades={m['trades']:3d}  PnL=${m['net_pnl']:>+9,.2f}  "
            f"WR={m['win_rate']:5.1f}%  PF={m['profit_factor']:5.2f}  "
            f"Sharpe={m['sharpe']:5.2f}  MaxDD=${m['max_dd']:>8,.2f}  "
            f"AvgW=${m['avg_win']:>7,.2f}  AvgL=${m['avg_loss']:>7,.2f}")


# ── compute rolling avg volume by time slot ──────────────────────────────

def compute_avg_vol_by_slot(bars: pd.DataFrame) -> dict:
    """Rolling 20-day average volume for each 30-min time slot."""
    # For simplicity, compute the overall average volume per time slot
    # (since we have ~86 days, a 20-day rolling average approximated as
    #  the mean across all days is reasonable for a first pass)
    bars_copy = bars.copy()
    bars_copy["slot"] = bars_copy["bar_ts"].apply(lambda x: f"{x.hour:02d}:{x.minute:02d}")
    avg_vol = bars_copy.groupby("slot")["volume"].mean().to_dict()
    return avg_vol


# ── main analysis ────────────────────────────────────────────────────────

def main():
    bars, unique_dates = load_30m_bars()
    out_lines = []

    def out(line=""):
        print(line)
        out_lines.append(line)

    out("=" * 90)
    out("OPT4: TIME-OF-DAY, DAY-OF-WEEK, VOLUME & DIRECTION FILTER ANALYSIS")
    out(f"ChNavy6 (VWAP Bounce) | SL=160t TP=560t | 30m bars | {len(unique_dates)} trading days")
    out("=" * 90)

    # ── BASELINE ──
    out("\n" + "─" * 90)
    out("BASELINE (no filters)")
    out("─" * 90)
    baseline_trades = run_chnavy6(bars)
    baseline_m = compute_metrics(baseline_trades)
    out(fmt_metrics(baseline_m))

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 1: TIME OF DAY
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("ANALYSIS 1: TIME-OF-DAY BREAKDOWN")
    out("=" * 90)

    # Tag each trade by time slot
    slot_pnl = {}
    for t in baseline_trades:
        slot = t.signal_bar_slot
        if slot not in slot_pnl:
            slot_pnl[slot] = {"trades": [], "pnls": []}
        slot_pnl[slot]["trades"].append(t)
        slot_pnl[slot]["pnls"].append(t.pnl)

    out(f"\n{'Slot':<8} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'NetPnL':>10} {'AvgPnL':>9} {'PF':>6}")
    out("-" * 58)
    sorted_slots = sorted(slot_pnl.keys())
    for slot in sorted_slots:
        d = slot_pnl[slot]
        n = len(d["pnls"])
        w = sum(1 for p in d["pnls"] if p > 0)
        wr = w / n * 100 if n > 0 else 0
        net = sum(d["pnls"])
        avg = np.mean(d["pnls"])
        gp = sum(p for p in d["pnls"] if p > 0)
        gl = abs(sum(p for p in d["pnls"] if p < 0))
        pf = gp / gl if gl > 0 else float("inf")
        out(f"{slot:<8} {n:>6} {w:>5} {wr:>5.1f}% ${net:>+9,.2f} ${avg:>+8,.2f} {pf:>5.2f}")

    # Test best time slot combinations
    out("\n── Best Time Slot Filters ──")
    # Sort slots by net PnL
    slot_net = {s: sum(slot_pnl[s]["pnls"]) for s in slot_pnl}
    ranked_slots = sorted(slot_net.items(), key=lambda x: x[1], reverse=True)
    out("\nSlots ranked by net PnL:")
    for s, pnl in ranked_slots:
        out(f"  {s}: ${pnl:>+9,.2f}")

    # Test: top-N slots by PnL
    out("\n── Filtered by best N time slots ──")
    for n_slots in [2, 3, 4, 5]:
        best_slots = set(s for s, _ in ranked_slots[:n_slots])
        trades = run_chnavy6(bars, allowed_slots=best_slots)
        m = compute_metrics(trades)
        label = "+".join(sorted(best_slots))
        out(f"  Top-{n_slots} [{label}]")
        out(f"    {fmt_metrics(m)}")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 2: DAY OF WEEK
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("ANALYSIS 2: DAY-OF-WEEK BREAKDOWN")
    out("=" * 90)

    day_pnl = {}
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    for t in baseline_trades:
        day = t.entry_time.strftime("%A")
        if day not in day_pnl:
            day_pnl[day] = {"trades": [], "pnls": []}
        day_pnl[day]["trades"].append(t)
        day_pnl[day]["pnls"].append(t.pnl)

    out(f"\n{'Day':<12} {'Trades':>6} {'Wins':>5} {'WR%':>6} {'NetPnL':>10} {'AvgPnL':>9} {'PF':>6}")
    out("-" * 62)
    for day in day_order:
        if day not in day_pnl:
            out(f"{day:<12} {'0':>6} {'—':>5} {'—':>6} {'$0.00':>10} {'—':>9} {'—':>6}")
            continue
        d = day_pnl[day]
        n = len(d["pnls"])
        w = sum(1 for p in d["pnls"] if p > 0)
        wr = w / n * 100 if n > 0 else 0
        net = sum(d["pnls"])
        avg = np.mean(d["pnls"])
        gp = sum(p for p in d["pnls"] if p > 0)
        gl = abs(sum(p for p in d["pnls"] if p < 0))
        pf = gp / gl if gl > 0 else float("inf")
        out(f"{day:<12} {n:>6} {w:>5} {wr:>5.1f}% ${net:>+9,.2f} ${avg:>+8,.2f} {pf:>5.2f}")

    # Test skipping worst days
    day_net = {d: sum(day_pnl[d]["pnls"]) for d in day_pnl}
    ranked_days = sorted(day_net.items(), key=lambda x: x[1])
    out(f"\nDays ranked worst to best:")
    for d, pnl in ranked_days:
        out(f"  {d}: ${pnl:>+9,.2f}")

    out("\n── Skip worst N days ──")
    for skip_n in [1, 2]:
        skip_days = set(d for d, _ in ranked_days[:skip_n])
        keep_days = set(day_order) - skip_days
        trades = run_chnavy6(bars, allowed_days=keep_days)
        m = compute_metrics(trades)
        out(f"  Skip {skip_days}")
        out(f"    {fmt_metrics(m)}")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 3: ENTRY BAR VOLUME FILTER
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("ANALYSIS 3: ENTRY BAR VOLUME FILTER")
    out("=" * 90)

    avg_vol_by_slot = compute_avg_vol_by_slot(bars)

    out(f"\nAverage 30m volume by slot (RTH):")
    for slot in sorted(avg_vol_by_slot.keys()):
        h = int(slot.split(":")[0])
        if 9 <= h <= 15:
            out(f"  {slot}: {avg_vol_by_slot[slot]:>10,.0f}")

    out(f"\nBaseline trade signal bar volumes:")
    for t in baseline_trades:
        avg_v = avg_vol_by_slot.get(t.signal_bar_slot, 0)
        ratio = t.signal_bar_volume / avg_v if avg_v > 0 else 0
        out(f"  {t.entry_time.strftime('%Y-%m-%d %H:%M')} {t.side:5s} "
            f"vol={t.signal_bar_volume:>8,.0f}  avg={avg_v:>8,.0f}  "
            f"ratio={ratio:5.2f}x  pnl=${t.pnl:>+9,.2f}")

    thresholds = [0.80, 1.00, 1.20, 1.50]
    out(f"\n── Volume threshold filter results ──")
    for thresh in thresholds:
        trades = run_chnavy6(bars, vol_threshold_pct=thresh, vol_avg_by_slot=avg_vol_by_slot)
        m = compute_metrics(trades)
        out(f"  Volume >= {thresh*100:.0f}% of slot avg:")
        out(f"    {fmt_metrics(m)}")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 4: DIRECTION BIAS (LONG vs SHORT)
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("ANALYSIS 4: DIRECTION BIAS (LONG vs SHORT)")
    out("=" * 90)

    for direction in ["LONG", "SHORT"]:
        dir_trades = [t for t in baseline_trades if t.side == direction]
        m = compute_metrics(dir_trades)
        out(f"\n  {direction} only:")
        out(f"    {fmt_metrics(m)}")
        # Exit reason breakdown
        reasons = {}
        for t in dir_trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        out(f"    Exit reasons: {reasons}")

    # Test direction-only strategies
    out("\n── Direction filter results ──")
    for direction in ["LONG", "SHORT"]:
        trades = run_chnavy6(bars, direction_filter=direction)
        m = compute_metrics(trades)
        out(f"  {direction}-only filter:")
        out(f"    {fmt_metrics(m)}")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 5: COMBINED FILTERS
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("ANALYSIS 5: COMBINED FILTERS")
    out("=" * 90)

    # Gather best findings from each analysis
    # We'll test several combinations systematically

    # Identify best slots (positive PnL)
    positive_slots = set(s for s, pnl in slot_net.items() if pnl > 0)
    # Identify best days (positive PnL)
    positive_days = set(d for d, pnl in day_net.items() if pnl > 0)
    # Best direction from baseline
    long_pnl = sum(t.pnl for t in baseline_trades if t.side == "LONG")
    short_pnl = sum(t.pnl for t in baseline_trades if t.side == "SHORT")
    best_dir = "LONG" if long_pnl > short_pnl else "SHORT"

    combos = [
        ("Best slots only", dict(allowed_slots=positive_slots)),
        ("Best days only", dict(allowed_days=positive_days)),
        (f"{best_dir}-only", dict(direction_filter=best_dir)),
        ("Vol >= 100%", dict(vol_threshold_pct=1.0, vol_avg_by_slot=avg_vol_by_slot)),
        ("Vol >= 120%", dict(vol_threshold_pct=1.2, vol_avg_by_slot=avg_vol_by_slot)),
        # Two-way combos
        (f"Best slots + Best days",
         dict(allowed_slots=positive_slots, allowed_days=positive_days)),
        (f"Best slots + {best_dir}",
         dict(allowed_slots=positive_slots, direction_filter=best_dir)),
        (f"Best days + {best_dir}",
         dict(allowed_days=positive_days, direction_filter=best_dir)),
        (f"Best slots + Vol>=100%",
         dict(allowed_slots=positive_slots, vol_threshold_pct=1.0, vol_avg_by_slot=avg_vol_by_slot)),
        (f"Best days + Vol>=120%",
         dict(allowed_days=positive_days, vol_threshold_pct=1.2, vol_avg_by_slot=avg_vol_by_slot)),
        # Three-way combos
        (f"Best slots + Best days + {best_dir}",
         dict(allowed_slots=positive_slots, allowed_days=positive_days, direction_filter=best_dir)),
        (f"Best slots + Best days + Vol>=100%",
         dict(allowed_slots=positive_slots, allowed_days=positive_days,
              vol_threshold_pct=1.0, vol_avg_by_slot=avg_vol_by_slot)),
        (f"Best slots + {best_dir} + Vol>=100%",
         dict(allowed_slots=positive_slots, direction_filter=best_dir,
              vol_threshold_pct=1.0, vol_avg_by_slot=avg_vol_by_slot)),
        # Four-way combo
        (f"Best slots + Best days + {best_dir} + Vol>=100%",
         dict(allowed_slots=positive_slots, allowed_days=positive_days,
              direction_filter=best_dir,
              vol_threshold_pct=1.0, vol_avg_by_slot=avg_vol_by_slot)),
        (f"Best slots + Best days + {best_dir} + Vol>=120%",
         dict(allowed_slots=positive_slots, allowed_days=positive_days,
              direction_filter=best_dir,
              vol_threshold_pct=1.2, vol_avg_by_slot=avg_vol_by_slot)),
    ]

    # Also test top-2/top-3 slots with best day/direction combos
    top2_slots = set(s for s, _ in ranked_slots[-2:]) if len(ranked_slots) >= 2 else positive_slots
    top3_slots = set(s for s, _ in ranked_slots[-3:]) if len(ranked_slots) >= 3 else positive_slots
    # Fix: ranked_slots is sorted by PnL descending, so top are first
    top2_slots = set(s for s, _ in ranked_slots[:2])
    top3_slots = set(s for s, _ in ranked_slots[:3])

    combos.extend([
        (f"Top-2 slots + Best days + {best_dir}",
         dict(allowed_slots=top2_slots, allowed_days=positive_days, direction_filter=best_dir)),
        (f"Top-3 slots + Best days",
         dict(allowed_slots=top3_slots, allowed_days=positive_days)),
        (f"Top-3 slots + {best_dir}",
         dict(allowed_slots=top3_slots, direction_filter=best_dir)),
    ])

    results = []
    for label, kwargs in combos:
        trades = run_chnavy6(bars, **kwargs)
        m = compute_metrics(trades)
        m["label"] = label
        m["kwargs"] = str(kwargs)
        results.append(m)

    # Sort by net PnL
    results.sort(key=lambda x: x["net_pnl"], reverse=True)

    out(f"\nPositive-PnL slots: {sorted(positive_slots)}")
    out(f"Positive-PnL days:  {sorted(positive_days)}")
    out(f"Best direction:     {best_dir} (L=${long_pnl:+,.2f} / S=${short_pnl:+,.2f})")
    out(f"Top-2 slots:        {sorted(top2_slots)}")
    out(f"Top-3 slots:        {sorted(top3_slots)}")

    out(f"\n{'Rank':<5} {'Label':<50} {'Trades':>6} {'PnL':>10} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'MaxDD':>9}")
    out("-" * 100)
    for i, r in enumerate(results, 1):
        out(f"{i:<5} {r['label']:<50} {r['trades']:>6} ${r['net_pnl']:>+9,.2f} "
            f"{r['win_rate']:>5.1f}% {r['profit_factor']:>5.2f} {r['sharpe']:>6.2f} ${r['max_dd']:>8,.2f}")

    # ══════════════════════════════════════════════════════════════════════
    # BEST RESULT — TRADE-BY-TRADE DETAIL
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("BEST COMBINED FILTER — TRADE-BY-TRADE DETAIL")
    out("=" * 90)

    # Find best by PnL with at least 5 trades
    best_viable = [r for r in results if r["trades"] >= 5]
    if not best_viable:
        best_viable = results

    if best_viable:
        best = best_viable[0]
        out(f"\nBest filter: {best['label']}")
        out(f"  {fmt_metrics(best)}")

    # Re-run best combo to get trade details
    # Pick the top result and reconstruct kwargs
    # For simplicity, run the top combos and print details for the best one
    best_label = best_viable[0]["label"] if best_viable else None
    if best_label:
        # Find the kwargs for this label
        for label, kwargs in combos:
            if label == best_label:
                best_trades = run_chnavy6(bars, **kwargs)
                break
        else:
            best_trades = baseline_trades

        out(f"\n{'Date':<18} {'Side':<6} {'Entry':>10} {'Exit':>10} {'PnL':>10} {'Reason':<12} {'Slot':<6} {'Vol':>8}")
        out("-" * 88)
        for t in best_trades:
            out(f"{t.entry_time.strftime('%Y-%m-%d %H:%M'):<18} {t.side:<6} "
                f"{t.entry_price:>10.2f} {t.exit_price:>10.2f} ${t.pnl:>+9,.2f} "
                f"{t.exit_reason:<12} {t.signal_bar_slot:<6} {t.signal_bar_volume:>8,.0f}")

        # Equity curve summary
        equity = np.cumsum([t.pnl for t in best_trades])
        out(f"\nEquity curve:")
        out(f"  Start:   $0.00")
        out(f"  End:     ${equity[-1]:,.2f}")
        out(f"  Peak:    ${np.max(equity):,.2f}")
        out(f"  Trough:  ${np.min(equity):,.2f}")
        out(f"  Max DD:  ${np.max(np.maximum.accumulate(equity) - equity):,.2f}")

    # ══════════════════════════════════════════════════════════════════════
    # SUMMARY vs BASELINE
    # ══════════════════════════════════════════════════════════════════════
    out("\n" + "=" * 90)
    out("SUMMARY: BASELINE vs BEST FILTER")
    out("=" * 90)
    out(f"\n  BASELINE:    {fmt_metrics(baseline_m)}")
    if best_viable:
        out(f"  BEST FILTER: {fmt_metrics(best_viable[0])}")
        out(f"  Filter:      {best_viable[0]['label']}")
        delta_pnl = best_viable[0]["net_pnl"] - baseline_m["net_pnl"]
        out(f"\n  Delta PnL:   ${delta_pnl:>+,.2f}")
        out(f"  Delta WR:    {best_viable[0]['win_rate'] - baseline_m['win_rate']:>+.1f}%")
        out(f"  Delta PF:    {best_viable[0]['profit_factor'] - baseline_m['profit_factor']:>+.2f}")
        out(f"  Delta Sharpe:{best_viable[0]['sharpe'] - baseline_m['sharpe']:>+.2f}")

    # Write output
    with open(OUT_PATH, "w") as f:
        f.write("\n".join(out_lines))
    print(f"\nResults written to {OUT_PATH}")


if __name__ == "__main__":
    main()
