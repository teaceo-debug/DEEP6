"""
Backtest — TIER 3 Follow-Signal (Gray-Tier Direction Trade)

Hypothesis: TYPE_C signals are predictive when traded mechanically in the direction
of the underlying absorption / exhaustion detection.

Trigger:
  - Bar scores TYPE_C (50-72 range, the gray tier)
  - AND one of these fires: Absorption (wick-defending, effort-vs-result) OR
    Exhaustion (failed thrust, volume climax at extreme)

Direction:
  - LONG  if absorption is bullish (lower wick defends bid) OR exhaustion is bearish
           (sell exhaustion: high-volume thrust to low, closed strong)
  - SHORT if absorption is bearish (upper wick) OR exhaustion is bullish
           (buy exhaustion: high-volume thrust to high, closed weak)

Entry: market order at next bar open
Max hold: 30 bars (time-stop)

Variants:
  A — Aggressive:  stop 8pts (32t),  target 15pts   (60t),  R:R 1.875
  B — Balanced:    stop 10pts (40t), target 20pts   (80t),  R:R 2.0
  C — Tight stop:  stop 5pts  (20t), target 17.5pts (70t),  R:R 3.5

Data: data/backtests/nq_3mo_1m.csv  (Jan 2 – Apr 10, 2026, ~85 sessions)
Out:  data/backtests/tier3_followsignal_{A|B|C}_trades.csv
      data/backtests/tier3_followsignal_{A|B|C}_equity.png
      .planning/backtest-tier3-followsignal-results.md
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── constants ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH  = ROOT / "data/backtests/nq_3mo_1m.csv"
OUT_DIR   = ROOT / "data/backtests"
REPORT_PATH = ROOT / ".planning/backtest-tier3-followsignal-results.md"

TICK_SIZE  = 0.25          # NQ
TICK_VALUE = 5.0           # $ per tick
COMMISSION = 0.70          # round-trip $/contract
SLIPPAGE   = 1 * TICK_SIZE # 1-tick slippage on entry

RTH_START_H = 9.5          # 09:30 ET — restrict to RTH
RTH_END_H   = 16.0         # flatten before 16:00 ET
ATR_PERIOD  = 14           # bars for ATR / volume baseline
VOL_MA_PERIOD = 20         # bars for volume moving average

# Tier thresholds (matching ConfluenceScorer.cs)
THRESH_A = 80.0
THRESH_B = 72.0
THRESH_C = 50.0

# R:R variant configs: (stop_pts, target_pts, label)
VARIANTS: list[tuple[float, float, str]] = [
    (8.0,  15.0,   "A"),
    (10.0, 20.0,   "B"),
    (5.0,  17.5,   "C"),
]

MAX_HOLD_BARS = 30


# ── data structures ────────────────────────────────────────────────────────────

@dataclass
class Trade:
    variant:      str
    bar_idx:      int
    bar_ts:       pd.Timestamp
    session_date: object
    side:         str          # "LONG" | "SHORT"
    entry_price:  float
    stop_price:   float
    target_price: float
    exit_price:   float = 0.0
    exit_reason:  str   = ""
    exit_bar_idx: int   = -1
    pnl:          float = 0.0  # net of commission + slippage
    signal_type:  str   = ""   # "absorption" | "exhaustion" | "both"
    score:        float = 0.0

    def close(self, price: float, reason: str, bar_idx: int) -> None:
        self.exit_price  = price
        self.exit_reason = reason
        self.exit_bar_idx = bar_idx
        ticks = (price - self.entry_price) / TICK_SIZE
        if self.side == "SHORT":
            ticks = -ticks
        self.pnl = ticks * TICK_VALUE - COMMISSION


# ── signal detection ───────────────────────────────────────────────────────────

def _wick_ratios(o: float, h: float, l: float, c: float) -> tuple[float, float, float]:
    """Returns (lower_wick_ratio, upper_wick_ratio, close_position) in [0,1]."""
    bar_range = h - l
    if bar_range < 1e-9:
        return 0.0, 0.0, 0.5
    body_lo = min(o, c)
    body_hi = max(o, c)
    lower_wick = body_lo - l
    upper_wick = h - body_hi
    close_pos  = (c - l) / bar_range
    return lower_wick / bar_range, upper_wick / bar_range, close_pos


def detect_signals(
    o: float, h: float, l: float, c: float, vol: float,
    vol_ma: float, atr: float,
    prev_highs: list[float], prev_lows: list[float],
) -> tuple[float, str | None]:
    """
    Returns (score, direction | None).
    direction is "LONG", "SHORT", or None (no trade).
    Score is 0-100.
    """
    if atr < 1e-9 or vol_ma < 1e-9:
        return 0.0, None

    bar_range = h - l
    if bar_range < 1e-9:
        return 0.0, None

    lwr, uwr, close_pos = _wick_ratios(o, h, l, c)
    vol_ratio = vol / vol_ma  # >1 = above average

    # ── absorption detection ─────────────────────────────────────────────────
    # Bullish: lower wick >= 40% of range, close in upper half, vol >= 1.2x avg
    abs_bullish = (
        lwr >= 0.40
        and close_pos >= 0.45
        and vol_ratio >= 1.2
        and bar_range >= 0.5 * atr
    )
    # Bearish: upper wick >= 40%, close in lower half
    abs_bearish = (
        uwr >= 0.40
        and close_pos <= 0.55
        and vol_ratio >= 1.2
        and bar_range >= 0.5 * atr
    )

    # ── exhaustion detection ─────────────────────────────────────────────────
    # Buy exhaustion at high → SHORT: bar makes 3-bar high, closes in bottom 35%
    made_3bar_high = len(prev_highs) >= 2 and h > max(prev_highs[-2:])
    exh_at_high = (
        made_3bar_high
        and close_pos <= 0.35
        and vol_ratio >= 1.4
    )
    # Sell exhaustion at low → LONG: bar makes 3-bar low, closes in top 65%
    made_3bar_low = len(prev_lows) >= 2 and l < min(prev_lows[-2:])
    exh_at_low = (
        made_3bar_low
        and close_pos >= 0.65
        and vol_ratio >= 1.4
    )

    # ── score calculation ────────────────────────────────────────────────────
    score = 0.0
    abs_fires = abs_bullish or abs_bearish
    exh_fires = exh_at_high or exh_at_low

    if abs_fires:
        wick = lwr if abs_bullish else uwr
        score += 20.0                              # base absorption weight
        score += min(8.0, (wick - 0.40) * 40.0)   # wick quality bonus
        score += min(5.0, (vol_ratio - 1.2) * 5.0)  # volume bonus

    if exh_fires:
        score += 15.7                              # base exhaustion weight
        score += min(6.3, (vol_ratio - 1.4) * 4.0)  # volume bonus

    if vol_ratio >= 2.0:
        score += min(10.0, (vol_ratio - 2.0) * 5.0)  # extreme volume bonus

    # ── direction resolution ─────────────────────────────────────────────────
    long_signals  = (1 if abs_bullish else 0) + (1 if exh_at_low else 0)
    short_signals = (1 if abs_bearish else 0) + (1 if exh_at_high else 0)

    if long_signals == 0 and short_signals == 0:
        return score, None

    direction = "LONG" if long_signals >= short_signals else "SHORT"

    # Require score >= TYPE_C threshold
    if score < THRESH_C:
        return score, None

    # Require at least one of absorption or exhaustion fires (not both quiet)
    if not abs_fires and not exh_fires:
        return score, None

    return score, direction


def signal_type_label(
    o: float, h: float, l: float, c: float, vol: float,
    vol_ma: float, atr: float,
    prev_highs: list[float], prev_lows: list[float],
) -> str:
    lwr, uwr, close_pos = _wick_ratios(o, h, l, c)
    if atr < 1e-9 or vol_ma < 1e-9:
        return "unknown"
    vol_ratio = vol / vol_ma
    bar_range = h - l
    abs_fires = (
        (lwr >= 0.40 and close_pos >= 0.45 and vol_ratio >= 1.2 and bar_range >= 0.5 * atr)
        or (uwr >= 0.40 and close_pos <= 0.55 and vol_ratio >= 1.2 and bar_range >= 0.5 * atr)
    )
    made_3bar_high = len(prev_highs) >= 2 and h > max(prev_highs[-2:])
    made_3bar_low  = len(prev_lows)  >= 2 and l < min(prev_lows[-2:])
    exh_fires = (
        (made_3bar_high and close_pos <= 0.35 and vol_ratio >= 1.4)
        or (made_3bar_low  and close_pos >= 0.65 and vol_ratio >= 1.4)
    )
    if abs_fires and exh_fires:
        return "both"
    if abs_fires:
        return "absorption"
    if exh_fires:
        return "exhaustion"
    return "unknown"


# ── exit simulation ────────────────────────────────────────────────────────────

def simulate_exit(
    bars: pd.DataFrame,
    entry_idx: int,
    trade: Trade,
    flatten_hour: float,
) -> None:
    """Walks forward from entry_idx, checks SL/TP/time-stop on each bar."""
    n = len(bars)
    bars_held = 0

    for j in range(entry_idx, n):
        row = bars.iloc[j]

        # Session boundary: exit at prior bar close
        if j > entry_idx and row["session_date"] != trade.session_date:
            prev_close = bars.iloc[j - 1]["close"]
            trade.close(prev_close, "SESSION_END", j - 1)
            return

        hour = row["bar_ts"].hour + row["bar_ts"].minute / 60.0

        # Flatten before RTH close
        if hour >= flatten_hour:
            trade.close(row["open"], "FLATTEN", j)
            return

        # Time-stop
        bars_held = j - entry_idx
        if bars_held >= MAX_HOLD_BARS:
            trade.close(row["open"], "TIME_STOP", j)
            return

        # Check SL / TP within bar
        lo, hi = row["low"], row["high"]
        if trade.side == "LONG":
            if lo <= trade.stop_price:
                trade.close(trade.stop_price, "STOP", j)
                return
            if hi >= trade.target_price:
                trade.close(trade.target_price, "TARGET", j)
                return
        else:
            if hi >= trade.stop_price:
                trade.close(trade.stop_price, "STOP", j)
                return
            if lo <= trade.target_price:
                trade.close(trade.target_price, "TARGET", j)
                return

    # Last bar in dataset
    last = bars.iloc[-1]
    trade.close(last["close"], "DATA_END", len(bars) - 1)


# ── load data ─────────────────────────────────────────────────────────────────

def load_bars() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "bar_ts"})
    df = df[["bar_ts", "open", "high", "low", "close", "volume"]].copy()
    # UTC-5 (EST) / UTC-4 (EDT) — use fixed offset; tzdata not available in WSL
    df["bar_ts"] = df["bar_ts"].dt.tz_localize("UTC") if df["bar_ts"].dt.tz is None else df["bar_ts"]
    df["bar_ts"] = df["bar_ts"] - pd.Timedelta(hours=4)  # EDT offset (Mar-Nov); close enough for session filtering
    df["bar_ts"] = df["bar_ts"].dt.tz_localize(None)     # drop tz for simple comparison
    df["session_date"] = df["bar_ts"].dt.date
    df = df.sort_values("bar_ts").reset_index(drop=True)

    # ATR (true range; for 1m bars close≈prev_close so TR≈range)
    df["tr"] = df["high"] - df["low"]
    df["atr"] = df["tr"].rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    df["vol_ma"] = df["volume"].rolling(VOL_MA_PERIOD, min_periods=VOL_MA_PERIOD).mean()

    # Filter to RTH only for signal detection + entry
    df["hour"] = df["bar_ts"].dt.hour + df["bar_ts"].dt.minute / 60.0
    df = df[df["hour"] >= RTH_START_H].copy()
    df = df.reset_index(drop=True)

    unique_dates = sorted(df["session_date"].unique())
    print(f"Loaded {len(df)} RTH 1m bars across {len(unique_dates)} sessions")
    print(f"Date range: {unique_dates[0]} → {unique_dates[-1]}")
    return df


# ── run backtest ───────────────────────────────────────────────────────────────

def run_backtest(bars: pd.DataFrame) -> list[Trade]:
    """Main loop: detect signals, queue entries, simulate exits."""
    all_trades: list[Trade] = []
    n = len(bars)

    # Track session state
    prev_highs: list[float] = []
    prev_lows:  list[float] = []
    prev_session = None
    open_trades: list[Trade] = []   # trades awaiting exit

    for i in range(n):
        row = bars.iloc[i]
        sess = row["session_date"]
        hour = row["hour"]

        # Session reset
        if sess != prev_session:
            prev_highs = []
            prev_lows  = []
            prev_session = sess

        atr    = row["atr"]
        vol_ma = row["vol_ma"]
        o, h, l, c, vol = row["open"], row["high"], row["low"], row["close"], float(row["volume"])

        # Close any open trades at this bar (they were queued at prior bar close)
        still_open = []
        for t in open_trades:
            if t.exit_reason == "":
                simulate_exit(bars, i, t, RTH_END_H)
        open_trades = []  # all dispatched to simulate_exit which fills them in-loop

        # Detect signal on this bar (only if after warm-up period)
        if pd.notna(atr) and pd.notna(vol_ma) and hour < RTH_END_H - 0.5:
            score, direction = detect_signals(
                o, h, l, c, vol, vol_ma, atr, prev_highs, prev_lows
            )

            if direction is not None and i + 1 < n:
                sig_type = signal_type_label(o, h, l, c, vol, vol_ma, atr, prev_highs, prev_lows)
                entry_bar = bars.iloc[i + 1]

                # Only enter if next bar is in RTH and same session
                if entry_bar["session_date"] == sess and entry_bar["hour"] < RTH_END_H:
                    entry_price = entry_bar["open"]
                    if direction == "LONG":
                        entry_price += SLIPPAGE
                    else:
                        entry_price -= SLIPPAGE

                    for stop_pts, target_pts, label in VARIANTS:
                        if direction == "LONG":
                            stop_px   = entry_price - stop_pts
                            target_px = entry_price + target_pts
                        else:
                            stop_px   = entry_price + stop_pts
                            target_px = entry_price - target_pts

                        t = Trade(
                            variant=label,
                            bar_idx=i,
                            bar_ts=row["bar_ts"],
                            session_date=sess,
                            side=direction,
                            entry_price=entry_price,
                            stop_price=stop_px,
                            target_price=target_px,
                            signal_type=sig_type,
                            score=score,
                        )
                        simulate_exit(bars, i + 1, t, RTH_END_H)
                        all_trades.append(t)

        prev_highs.append(h)
        prev_lows.append(l)
        if len(prev_highs) > 10:
            prev_highs.pop(0)
            prev_lows.pop(0)

    return all_trades


# ── metrics ────────────────────────────────────────────────────────────────────

def compute_metrics(trades: list[Trade]) -> dict:
    if not trades:
        return {k: 0 for k in ["trades","net_pnl","win_rate","avg_pnl","max_dd",
                                "pf","sharpe","longest_losing","expectancy"]}
    pnls = [t.pnl for t in trades]
    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    max_dd = float(np.max(peak - equity))

    gp = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    wins = sum(1 for p in pnls if p > 0)
    losses = len(pnls) - wins

    # Longest losing streak
    longest_losing = cur_losing = 0
    for p in pnls:
        if p < 0:
            cur_losing += 1
            longest_losing = max(longest_losing, cur_losing)
        else:
            cur_losing = 0

    mean_pnl = float(np.mean(pnls))
    std_pnl  = float(np.std(pnls, ddof=1)) if len(pnls) > 1 else 1.0
    sharpe   = mean_pnl / std_pnl * np.sqrt(252) if std_pnl > 0 else 0.0

    avg_win  = gp / wins   if wins   > 0 else 0.0
    avg_loss = gl / losses if losses > 0 else 0.0
    win_rate = wins / len(pnls)
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    return {
        "trades":          len(trades),
        "net_pnl":         round(sum(pnls), 2),
        "win_rate":        round(win_rate * 100, 1),
        "avg_pnl":         round(mean_pnl, 2),
        "max_dd":          round(max_dd, 2),
        "pf":              round(gp / gl, 2) if gl > 0 else 999.0,
        "sharpe":          round(sharpe, 2),
        "longest_losing":  longest_losing,
        "expectancy":      round(expectancy, 2),
    }


# ── output ─────────────────────────────────────────────────────────────────────

def save_csv(trades: list[Trade], variant: str) -> None:
    path = OUT_DIR / f"tier3_followsignal_{variant}_trades.csv"
    rows = []
    cum = 0.0
    for t in trades:
        cum += t.pnl
        rows.append({
            "bar_ts": str(t.bar_ts),
            "session": str(t.session_date),
            "side": t.side,
            "entry": round(t.entry_price, 2),
            "exit": round(t.exit_price, 2),
            "exit_reason": t.exit_reason,
            "pnl": round(t.pnl, 2),
            "cum_pnl": round(cum, 2),
            "signal_type": t.signal_type,
            "score": round(t.score, 1),
        })
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  Saved {path.name}")


def save_equity_png(trades: list[Trade], variant: str, metrics: dict) -> None:
    path = OUT_DIR / f"tier3_followsignal_{variant}_equity.png"
    pnls  = [t.pnl for t in trades]
    eq    = np.cumsum(pnls) if pnls else np.array([0.0])
    peak  = np.maximum.accumulate(eq)
    dd    = peak - eq

    fig, axes = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]})

    # Equity curve
    ax = axes[0]
    ax.plot(eq, color="#2196F3", linewidth=1.2, label="Equity ($)")
    ax.fill_between(range(len(eq)), eq, alpha=0.08, color="#2196F3")
    ax.axhline(0, color="#888", linewidth=0.7, linestyle="--")
    ax.set_title(
        f"DEEP6 Tier3 Follow-Signal — Variant {variant}  |  "
        f"{metrics['trades']} trades, ${metrics['net_pnl']:,.0f} net, "
        f"WR {metrics['win_rate']}%, PF {metrics['pf']}",
        fontsize=10,
    )
    ax.set_ylabel("Cumulative PnL ($)")
    ax.legend(loc="upper left", fontsize=9)

    # Drawdown
    ax2 = axes[1]
    ax2.fill_between(range(len(dd)), -dd, color="#F44336", alpha=0.6)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Trade #")

    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  Saved {path.name}")


def tod_buckets(trades: list[Trade]) -> dict:
    """Time-of-day breakdown: winners vs losers."""
    buckets: dict[str, dict] = {}
    for t in trades:
        h = t.bar_ts.hour
        label = f"{h:02d}:00"
        if label not in buckets:
            buckets[label] = {"wins": 0, "losses": 0}
        if t.pnl > 0:
            buckets[label]["wins"] += 1
        else:
            buckets[label]["losses"] += 1
    return dict(sorted(buckets.items()))


def write_report(
    trades_by_variant: dict[str, list[Trade]],
    metrics_by_variant: dict[str, dict],
) -> None:
    lines: list[str] = []
    W = lines.append

    W("# Backtest Results — TIER 3 Follow-Signal")
    W("")
    W("**Hypothesis:** TYPE_C bars (score 50-72) are predictive when traded in the")
    W("direction of the underlying absorption / exhaustion signal.")
    W("")
    W("**Data:** NQ.c.0 1-min OHLCV, Jan 2 – Apr 10, 2026 (~85 RTH sessions)")
    W("**Signals:** Bar-structure absorption (wick ≥40%, vol ≥1.2x avg) + exhaustion")
    W("(failed 3-bar thrust, vol ≥1.4x avg, close ≥60% against direction)")
    W("")

    # Side-by-side summary
    W("## Summary — All Variants")
    W("")
    W("| Metric | A (Aggressive) | B (Balanced) | C (Tight stop) |")
    W("|--------|---------------|--------------|----------------|")
    keys = ["trades","net_pnl","win_rate","avg_pnl","max_dd","pf","sharpe",
            "longest_losing","expectancy"]
    labels = ["Trades","Net PnL ($)","Win Rate (%)","Avg PnL ($)","Max DD ($)",
              "Profit Factor","Sharpe","Longest Losing Streak","Expectancy ($)"]
    for key, label in zip(keys, labels):
        row = f"| {label} |"
        for v in ["A","B","C"]:
            val = metrics_by_variant[v][key]
            if isinstance(val, float):
                row += f" {val:,.2f} |"
            else:
                row += f" {val} |"
        W(row)

    # Best variant
    best = max(metrics_by_variant, key=lambda v: metrics_by_variant[v]["net_pnl"])
    W("")
    W(f"**Best variant:** {best} (Net PnL ${metrics_by_variant[best]['net_pnl']:,.2f})")
    W("")

    # Signal type split (using variant B as representative)
    W("## Signal Type Split (Variant B)")
    W("")
    trades_b = trades_by_variant["B"]
    for sig in ["absorption","exhaustion","both"]:
        group = [t for t in trades_b if t.signal_type == sig]
        if not group:
            continue
        m = compute_metrics(group)
        W(f"**{sig.title()}:** {m['trades']} trades — "
          f"WR {m['win_rate']}%, net ${m['net_pnl']:,.2f}, PF {m['pf']}")
    W("")

    # Time-of-day distribution (variant B)
    W("## Time-of-Day Distribution — Winners vs Losers (Variant B)")
    W("")
    W("| Hour | Winners | Losers | Win% |")
    W("|------|---------|--------|------|")
    tod = tod_buckets(trades_b)
    for label, counts in tod.items():
        total = counts["wins"] + counts["losses"]
        wr = counts["wins"] / total * 100 if total else 0
        W(f"| {label} | {counts['wins']} | {counts['losses']} | {wr:.0f}% |")
    W("")

    # Per-variant detail
    for v in ["A","B","C"]:
        m = metrics_by_variant[v]
        trades = trades_by_variant[v]
        stop_pts, tgt_pts, _ = [(s,t,l) for s,t,l in VARIANTS if l == v][0]
        W(f"## Variant {v} — Stop {stop_pts}pts / Target {tgt_pts}pts")
        W("")
        W(f"- Trades: **{m['trades']}**, Win%: **{m['win_rate']}%**")
        W(f"- Net PnL: **${m['net_pnl']:,.2f}**, Avg: ${m['avg_pnl']:,.2f}")
        W(f"- Max DD: ${m['max_dd']:,.2f}, PF: {m['pf']}, Sharpe: {m['sharpe']}")
        W("")
        # Exit reason breakdown
        reasons: dict[str, int] = {}
        for t in trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        W("Exit reasons: " + ", ".join(f"{k}={v}" for k,v in sorted(reasons.items())))
        W("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport: {REPORT_PATH}")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("DEEP6 — Tier 3 Follow-Signal Backtest")
    print("=" * 70)

    bars = load_bars()

    print("\nRunning signal detection + all 3 variants…")
    all_trades = run_backtest(bars)

    # Split by variant
    trades_by_variant: dict[str, list[Trade]] = {"A": [], "B": [], "C": []}
    for t in all_trades:
        trades_by_variant[t.variant].append(t)

    metrics_by_variant: dict[str, dict] = {}
    for v in ["A", "B", "C"]:
        stop_pts, tgt_pts, _ = [(s,t,l) for s,t,l in VARIANTS if l == v][0]
        trades = trades_by_variant[v]
        m = compute_metrics(trades)
        metrics_by_variant[v] = m
        print(f"\n{'─' * 60}")
        print(f"Variant {v}  stop={stop_pts}pts  target={tgt_pts}pts")
        print(f"{'─' * 60}")
        print(f"  Trades: {m['trades']}  |  Win%: {m['win_rate']}%  |  PF: {m['pf']}  |  Sharpe: {m['sharpe']}")
        print(f"  Net PnL: ${m['net_pnl']:,.2f}  |  Avg: ${m['avg_pnl']:,.2f}  |  MaxDD: ${m['max_dd']:,.2f}")
        print(f"  Expectancy: ${m['expectancy']:,.2f}  |  Longest losing streak: {m['longest_losing']}")

        # Signal type breakdown
        for sig in ["absorption","exhaustion","both"]:
            group = [t for t in trades if t.signal_type == sig]
            if group:
                gm = compute_metrics(group)
                print(f"  [{sig:11s}] {gm['trades']:3d} trades  WR {gm['win_rate']:5.1f}%  net ${gm['net_pnl']:>9,.2f}")

        save_csv(trades, v)
        save_equity_png(trades, v, m)

    write_report(trades_by_variant, metrics_by_variant)

    print("\n" + "=" * 70)
    best = max(metrics_by_variant, key=lambda v: metrics_by_variant[v]["net_pnl"])
    print(f"Best variant: {best}  ${metrics_by_variant[best]['net_pnl']:,.2f} net")
    print("=" * 70)


if __name__ == "__main__":
    main()
