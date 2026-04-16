"""deep6/backtest/round1_entry_timing.py — Round 1 Entry Timing Optimization.

Analyzes 50 NDJSON sessions (pre-scored bar data) to answer four questions:

1. Bar-of-day distribution — which 30-min windows have the best edge?
2. Confirmation filter — does delaying entry 1-2 bars after signal fire improve win rate?
3. Signal confluence — do entries with 3+ signals on same bar outperform 1-2?
4. Pullback entry — does waiting for 2-4 tick retrace from signal bar close improve fills?

Output: ninjatrader/backtests/results/round1/ENTRY-TIMING.md

Assumptions:
  - barsSinceOpen is 1-min bar index from session open (0 = open bar)
  - NQ sessions: 390 bars = 0930-1600 ET (6.5 hours × 60 mins)
  - 30-min windows: bars 0-29, 30-59, ..., 360-389 (13 windows)
  - Baseline config: P0-fixed defaults from BacktestConfig.cs
    score_entry_threshold=60, min_tier=TYPE_B (ord 2),
    stop_loss=20t, target=40t, max_bars=30, slippage=1t
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
OUTPUT_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round1"

# ---------------------------------------------------------------------------
# Simulation constants (P0-fixed baseline from BacktestConfig.cs)
# ---------------------------------------------------------------------------
TICK_SIZE  = 0.25   # NQ
TICK_VALUE = 5.0    # $/tick
SLIPPAGE_T = 1.0    # ticks, applied at entry and exit
STOP_LOSS_T  = 20
TARGET_T     = 40
MAX_BARS     = 30
SCORE_THRESH = 60.0
MIN_TIER_ORD = 2    # TYPE_B = ordinal 2

# For entry-timing analysis we run TWO modes:
#  - STRICT: P0 defaults (TYPE_B+, VOLP-03 veto on) — matches live system
#  - RELAXED: score>=50, min_tier=any(0), VOLP-03 veto OFF — for statistical power
#    The synthetic sessions have VOLP-03 every 40 bars (data artifact) and only
#    18 TYPE_B signals total, giving only 1 trade in strict mode.
#    Relaxed mode surfaces time-of-day / confirmation / confluence patterns
#    that are invisible at strict settings.
RELAX_SCORE_THRESH = 50.0
RELAX_MIN_TIER_ORD = 0    # accept any directional bar

_TIER_ORDINALS = {"DISQUALIFIED": -1, "QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}

# 30-min window labels (13 windows covering full RTH session 0930-1600 ET)
# window index = barsSinceOpen // 30
WINDOW_LABELS = {
    0:  "0930-1000",
    1:  "1000-1030",
    2:  "1030-1100",
    3:  "1100-1130",
    4:  "1130-1200",
    5:  "1200-1230",
    6:  "1230-1300",
    7:  "1300-1330",
    8:  "1330-1400",
    9:  "1400-1430",
    10: "1430-1500",
    11: "1500-1530",
    12: "1530-1600",
}


# ---------------------------------------------------------------------------
# Loader + Scorer (reuse vbt_harness logic directly)
# ---------------------------------------------------------------------------

def _load_session(path: Path) -> list[dict]:
    bars = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "scored_bar":
                bars.append(obj)
    return bars


def _score_bar(bar: dict) -> dict:
    """Python scorer — mirrors vbt_harness._score_bar_simple exactly."""
    signals = bar.get("signals", []) or []
    zone_score = float(bar.get("zoneScore", 0.0))
    zone_dist = float(bar.get("zoneDistTicks", 1e9))
    bars_since_open = int(bar.get("barsSinceOpen", 0))
    bar_delta = int(bar.get("barDelta", 0))
    bar_close = float(bar.get("barClose", 0.0))

    W = {
        "absorption": 25.0, "exhaustion": 18.0, "trapped": 14.0,
        "delta": 13.0, "imbalance": 12.0, "volume_profile": 10.0,
        "auction": 8.0, "poc": 1.0,
    }
    VOTING_DELTA = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
    VOTING_AUCT  = {"AUCT-01", "AUCT-02", "AUCT-05"}
    VOTING_POC   = {"POC-02",  "POC-07",  "POC-08"}

    bull_w = bear_w = 0.0
    cats_bull: set[str] = set()
    cats_bear: set[str] = set()
    stacked_bull = stacked_bear = 0
    max_bull_str = max_bear_str = 0.0

    def _add(is_bull: bool, cat: str, s: float) -> None:
        nonlocal bull_w, bear_w, max_bull_str, max_bear_str
        if is_bull:
            bull_w += s
            cats_bull.add(cat)
            max_bull_str = max(max_bull_str, s)
        else:
            bear_w += s
            cats_bear.add(cat)
            max_bear_str = max(max_bear_str, s)

    for sig in signals:
        sid = sig.get("signalId", "")
        d   = int(sig.get("direction", 0))
        s   = float(sig.get("strength", 0.0))
        if d == 0:
            continue
        if sid.startswith("ABS"):
            _add(d > 0, "absorption", s)
        elif sid.startswith("EXH"):
            _add(d > 0, "exhaustion", s)
        elif sid.startswith("TRAP"):
            _add(d > 0, "trapped", s)
        elif sid.startswith("IMB"):
            tier_n = 0
            detail = sig.get("detail", "")
            for sfx in ("-T3", "-T2", "-T1"):
                if sid.endswith(sfx):
                    tier_n = int(sfx[-1])
                    break
            if tier_n == 0 and "STACKED_T" in detail:
                idx = detail.find("STACKED_T")
                if idx >= 0 and idx + 9 < len(detail):
                    try:
                        tier_n = int(detail[idx + 9])
                    except ValueError:
                        tier_n = 1
            if tier_n > 0:
                if d > 0:
                    stacked_bull = max(stacked_bull, tier_n)
                    max_bull_str = max(max_bull_str, s)
                else:
                    stacked_bear = max(stacked_bear, tier_n)
                    max_bear_str = max(max_bear_str, s)
        elif sid in VOTING_DELTA:
            _add(d > 0, "delta", s)
        elif sid in VOTING_AUCT:
            _add(d > 0, "auction", s)
        elif sid in VOTING_POC:
            _add(d > 0, "poc", s)

    if stacked_bull > 0:
        bull_w += 0.5
        cats_bull.add("imbalance")
    if stacked_bear > 0:
        bear_w += 0.5
        cats_bear.add("imbalance")

    if bull_w > bear_w:
        direction = 1
        cats = cats_bull
        max_str = max_bull_str
    elif bear_w > bull_w:
        direction = -1
        cats = cats_bear
        max_str = max_bear_str
    else:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close, "cat_count": 0}

    if bar_delta != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close, "cat_count": 0}

    zone_bonus = 0.0
    if zone_score >= 50.0:
        zone_bonus = 4.0 if zone_dist <= 0.5 else 8.0
        cats.add("volume_profile")
    elif zone_score >= 30.0:
        zone_bonus = 6.0
        cats.add("volume_profile")

    cat_count = len(cats)
    confluence_mult = 1.25 if cat_count >= 5 else 1.0
    ib_mult = 1.15 if 0 <= bars_since_open < 60 else 1.0

    base_score = sum(W.get(c, 5.0) for c in cats)
    total_score = min((base_score * confluence_mult + zone_bonus) * ib_mult, 100.0)
    total_score = max(0.0, total_score)

    if 240 <= bars_since_open <= 330:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET", "entry_price": bar_close, "cat_count": 0}

    has_abs  = "absorption" in cats
    has_exh  = "exhaustion" in cats
    has_zone = zone_bonus > 0.0
    trap_count  = sum(1 for sig in signals if sig.get("signalId", "").startswith("TRAP"))
    delta_chase = abs(bar_delta) > 50 and (
        (direction > 0 and bar_delta > 0) or (direction < 0 and bar_delta < 0)
    )

    if (total_score >= 80.0 and (has_abs or has_exh) and has_zone
            and cat_count >= 5 and trap_count < 3 and not delta_chase):
        tier = "TYPE_A"
    elif total_score >= 72.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_B"
    elif total_score >= 50.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_C"
    else:
        tier = "QUIET"

    entry_price = bar_close
    for sig in signals:
        sid = sig.get("signalId", "")
        if sig.get("direction", 0) == direction and float(sig.get("price", 0.0)) != 0.0:
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = float(sig["price"])
                break

    return {
        "direction": direction,
        "total_score": total_score,
        "tier": tier,
        "entry_price": entry_price,
        "cat_count": cat_count,
        "signal_count": len([s for s in signals if int(s.get("direction", 0)) == direction]),
    }


# ---------------------------------------------------------------------------
# Trade simulation helper
# ---------------------------------------------------------------------------

class Trade(NamedTuple):
    session: str
    entry_bar: int
    exit_bar: int
    direction: int
    pnl_ticks: float
    pnl_dollars: float
    exit_reason: str
    signal_bar: int          # original bar index where signal fired
    window_idx: int          # 30-min window index (0-12)
    cat_count: int           # number of categories on signal bar
    signal_count: int        # number of signals on signal bar in trade direction
    entry_delay_bars: int    # bars after signal before entry (0 = immediate)
    retrace_ticks: float     # retrace from signal bar close at entry (0 = no retrace)
    score: float


def _simulate_session(
    bars: list[dict],
    scored: list[dict],
    session_name: str,
    entry_delay_bars: int = 0,
    retrace_ticks: float = 0.0,
    volp03_veto: bool = True,
    score_thresh: float = SCORE_THRESH,
    min_tier_ord: int = MIN_TIER_ORD,
) -> list[Trade]:
    """Run a single session through the simulator with configurable entry timing.

    entry_delay_bars: wait N bars after signal before entering
    retrace_ticks: wait until price retraces N ticks from signal bar close
                   before entering (checked on subsequent bars)
    """
    sl_pts = STOP_LOSS_T  * TICK_SIZE
    tp_pts = TARGET_T     * TICK_SIZE
    slip_pts = SLIPPAGE_T * TICK_SIZE

    trades: list[Trade] = []
    in_trade = False
    entry_price = 0.0
    entry_bar_idx = 0
    trade_dir = 0
    trade_meta: dict = {}

    # Pending entry state (for delayed / retrace modes)
    pending = False
    pending_bar_idx = 0
    pending_direction = 0
    pending_scored: dict = {}
    pending_bar_close = 0.0
    pending_window_idx = 0

    # VOLP-03 session veto
    volp03_fired = False

    n = len(bars)
    for i, (bar, sc) in enumerate(zip(bars, scored)):
        bar_idx = int(bar.get("barIdx", 0))
        bar_close = float(bar.get("barClose", 0.0))
        bso = int(bar.get("barsSinceOpen", 0))

        # VOLP-03 veto check
        if volp03_veto:
            for sig in (bar.get("signals") or []):
                if sig and sig.get("signalId", "").startswith("VOLP-03"):
                    volp03_fired = True
                    break

        if in_trade:
            # Exit checks
            exit_reason = None
            if trade_dir == 1 and bar_close <= entry_price - sl_pts:
                exit_reason = "STOP_LOSS"
            elif trade_dir == -1 and bar_close >= entry_price + sl_pts:
                exit_reason = "STOP_LOSS"

            if exit_reason is None:
                if trade_dir == 1 and bar_close >= entry_price + tp_pts:
                    exit_reason = "TARGET"
                elif trade_dir == -1 and bar_close <= entry_price - tp_pts:
                    exit_reason = "TARGET"

            if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS:
                exit_reason = "MAX_BARS"

            if exit_reason is not None:
                exit_p = bar_close - trade_dir * slip_pts
                pnl_t = (exit_p - entry_price) / TICK_SIZE * trade_dir
                trades.append(Trade(
                    session=session_name,
                    entry_bar=entry_bar_idx,
                    exit_bar=bar_idx,
                    direction=trade_dir,
                    pnl_ticks=pnl_t,
                    pnl_dollars=pnl_t * TICK_VALUE,
                    exit_reason=exit_reason,
                    signal_bar=trade_meta["signal_bar"],
                    window_idx=trade_meta["window_idx"],
                    cat_count=trade_meta["cat_count"],
                    signal_count=trade_meta["signal_count"],
                    entry_delay_bars=trade_meta["entry_delay_bars"],
                    retrace_ticks=trade_meta["retrace_ticks"],
                    score=trade_meta["score"],
                ))
                in_trade = False
                pending = False
        else:
            # Handle pending entry (delayed or retrace mode)
            if pending and not (volp03_veto and volp03_fired):
                bars_since_signal = bar_idx - pending_bar_idx
                retrace_met = False

                if retrace_ticks > 0.0:
                    # Wait for price to retrace N ticks from signal bar close
                    if pending_direction == 1:
                        retrace_met = bar_close <= pending_bar_close - retrace_ticks * TICK_SIZE
                    else:
                        retrace_met = bar_close >= pending_bar_close + retrace_ticks * TICK_SIZE
                    # Expire after max_bars
                    if bars_since_signal > MAX_BARS:
                        pending = False
                else:
                    # Delay mode: enter exactly at bars_since_signal == entry_delay_bars
                    retrace_met = (bars_since_signal == entry_delay_bars)
                    if bars_since_signal > entry_delay_bars:
                        pending = False  # expired

                if retrace_met and pending:
                    actual_delay = bars_since_signal
                    actual_retrace = abs(bar_close - pending_bar_close) / TICK_SIZE

                    entry_price = bar_close + pending_direction * slip_pts
                    entry_bar_idx = bar_idx
                    trade_dir = pending_direction
                    trade_meta = {
                        "signal_bar": pending_bar_idx,
                        "window_idx": pending_window_idx,
                        "cat_count": pending_scored.get("cat_count", 0),
                        "signal_count": pending_scored.get("signal_count", 0),
                        "entry_delay_bars": actual_delay,
                        "retrace_ticks": actual_retrace,
                        "score": pending_scored.get("total_score", 0.0),
                    }
                    in_trade = True
                    pending = False
                    continue

            # Check for new signal if not already pending
            if not pending and not (volp03_veto and volp03_fired):
                direction = sc["direction"]
                total_score = sc["total_score"]
                tier_ord = _TIER_ORDINALS.get(sc["tier"], 0)

                if (direction != 0
                        and total_score >= score_thresh
                        and tier_ord >= min_tier_ord):
                    window_idx = bso // 30

                    if entry_delay_bars == 0 and retrace_ticks == 0.0:
                        # Immediate entry
                        entry_price = sc["entry_price"] + direction * slip_pts
                        entry_bar_idx = bar_idx
                        trade_dir = direction
                        trade_meta = {
                            "signal_bar": bar_idx,
                            "window_idx": window_idx,
                            "cat_count": sc.get("cat_count", 0),
                            "signal_count": sc.get("signal_count", 0),
                            "entry_delay_bars": 0,
                            "retrace_ticks": 0.0,
                            "score": total_score,
                        }
                        in_trade = True
                    else:
                        # Queue a pending entry
                        pending = True
                        pending_bar_idx = bar_idx
                        pending_direction = direction
                        pending_scored = sc
                        pending_bar_close = bar_close
                        pending_window_idx = window_idx

    # Force-close at session end
    if in_trade and bars:
        last_close = float(bars[-1].get("barClose", 0.0))
        last_idx   = int(bars[-1].get("barIdx", 0))
        exit_p = last_close - trade_dir * slip_pts
        pnl_t  = (exit_p - entry_price) / TICK_SIZE * trade_dir
        trades.append(Trade(
            session=session_name,
            entry_bar=entry_bar_idx,
            exit_bar=last_idx,
            direction=trade_dir,
            pnl_ticks=pnl_t,
            pnl_dollars=pnl_t * TICK_VALUE,
            exit_reason="SESSION_END",
            signal_bar=trade_meta["signal_bar"],
            window_idx=trade_meta["window_idx"],
            cat_count=trade_meta["cat_count"],
            signal_count=trade_meta["signal_count"],
            entry_delay_bars=trade_meta["entry_delay_bars"],
            retrace_ticks=trade_meta["retrace_ticks"],
            score=trade_meta["score"],
        ))

    return trades


# ---------------------------------------------------------------------------
# Load all sessions
# ---------------------------------------------------------------------------

def load_all() -> dict[str, tuple[list[dict], list[dict]]]:
    """Returns {session_name: (bars, scored)} for all 50 sessions."""
    sessions: dict[str, tuple[list[dict], list[dict]]] = {}
    for path in sorted(SESSIONS_DIR.glob("*.ndjson")):
        bars = _load_session(path)
        scored = [_score_bar(b) for b in bars]
        sessions[path.name] = (bars, scored)
    return sessions


# ---------------------------------------------------------------------------
# Analysis 1: Bar-of-day distribution (30-min windows)
# ---------------------------------------------------------------------------

def analyze_time_windows(all_trades: list[Trade]) -> pd.DataFrame:
    """Win rate + edge metrics per 30-min window."""
    rows = []
    by_window: dict[int, list[Trade]] = defaultdict(list)
    for t in all_trades:
        if 0 <= t.window_idx <= 12:
            by_window[t.window_idx].append(t)

    for w_idx in range(13):
        trades = by_window.get(w_idx, [])
        label = WINDOW_LABELS.get(w_idx, str(w_idx))
        if not trades:
            rows.append({
                "window": label, "count": 0, "win_rate": 0.0,
                "avg_pnl_ticks": 0.0, "profit_factor": 0.0, "net_ticks": 0.0,
            })
            continue
        pnls = np.array([t.pnl_ticks for t in trades])
        wins = (pnls > 0).sum()
        gross_profit = pnls[pnls > 0].sum()
        gross_loss    = abs(pnls[pnls < 0].sum())
        pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
        rows.append({
            "window": label,
            "count": len(trades),
            "win_rate": round(float(wins / len(trades)), 3),
            "avg_pnl_ticks": round(float(pnls.mean()), 2),
            "profit_factor": round(pf, 2),
            "net_ticks": round(float(pnls.sum()), 1),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 2: Confirmation filter (entry delay 0, 1, 2 bars)
# ---------------------------------------------------------------------------

def _sim_all(
    sessions: dict,
    entry_delay_bars: int = 0,
    retrace_ticks: float = 0.0,
) -> list[Trade]:
    """Run all sessions with RELAXED thresholds (VOLP-03 veto OFF, score>=50, any tier).

    NOTE on synthetic data: All 50 sessions contain VOLP-03 every 40 bars (volume
    surge data artifact). With the P0 strict config (TYPE_B+ only) this leaves only
    1 trade total across 50 sessions — statistically meaningless for entry-timing.
    Relaxed mode (score>=50, any tier, no VOLP-03 veto) provides 200+ trades for
    distribution analysis. Findings apply to signal quality / timing regardless of
    tier cutoff; re-validate against live TYPE_B+ signals when real session data
    is available.
    """
    trades: list[Trade] = []
    for name, (bars, scored) in sessions.items():
        trades.extend(_simulate_session(
            bars, scored, name,
            entry_delay_bars=entry_delay_bars,
            retrace_ticks=retrace_ticks,
            volp03_veto=False,
            score_thresh=RELAX_SCORE_THRESH,
            min_tier_ord=RELAX_MIN_TIER_ORD,
        ))
    return trades


def _stats_row(trades: list[Trade], **extra) -> dict:
    pnls = np.array([t.pnl_ticks for t in trades]) if trades else np.array([])
    wins = int((pnls > 0).sum()) if len(pnls) else 0
    gross_profit = float(pnls[pnls > 0].sum()) if len(pnls) else 0.0
    gross_loss   = float(abs(pnls[pnls < 0].sum())) if len(pnls) else 0.0
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    return {
        **extra,
        "total_trades": len(trades),
        "win_rate": round(float(wins / len(pnls)), 3) if len(pnls) else 0.0,
        "avg_pnl_ticks": round(float(pnls.mean()), 2) if len(pnls) else 0.0,
        "profit_factor": round(pf, 2),
        "net_ticks": round(float(pnls.sum()), 1) if len(pnls) else 0.0,
    }


def analyze_confirmation_delay(sessions: dict) -> pd.DataFrame:
    rows = []
    for delay in [0, 1, 2]:
        trades = _sim_all(sessions, entry_delay_bars=delay)
        rows.append(_stats_row(trades, delay_bars=delay))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 3: Signal confluence (1-2 signals vs 3+ signals on entry bar)
# ---------------------------------------------------------------------------

def analyze_signal_confluence(all_trades: list[Trade]) -> pd.DataFrame:
    """Compare entries with 1-2 vs 3+ signals (in trade direction) on signal bar."""
    buckets = {
        "1 signal":  [t for t in all_trades if t.signal_count == 1],
        "2 signals": [t for t in all_trades if t.signal_count == 2],
        "3 signals": [t for t in all_trades if t.signal_count == 3],
        "4+ signals":[t for t in all_trades if t.signal_count >= 4],
        "3+ signals":[t for t in all_trades if t.signal_count >= 3],
    }
    rows = []
    for label, trades in buckets.items():
        rows.append(_stats_row(trades, signal_count_bucket=label))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis 4: Pullback / retrace entry (0, 2, 3, 4 ticks retrace)
# ---------------------------------------------------------------------------

def analyze_retrace_entry(sessions: dict) -> pd.DataFrame:
    rows = []
    for retrace in [0.0, 2.0, 3.0, 4.0]:
        trades = _sim_all(sessions, retrace_ticks=retrace)
        fill_note = "100% (immediate)" if retrace == 0.0 else f"{len(trades)} trades triggered"
        row = _stats_row(trades, retrace_ticks=retrace)
        row["fill_rate"] = fill_note
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Combined: Time window × Confirmation delay cross-table
# ---------------------------------------------------------------------------

def analyze_time_x_delay(sessions: dict) -> pd.DataFrame:
    """Best delay per time window — which window + delay combos have highest edge?"""
    rows = []
    for delay in [0, 1, 2]:
        trades = _sim_all(sessions, entry_delay_bars=delay)

        by_window: dict[int, list[Trade]] = defaultdict(list)
        for t in trades:
            if 0 <= t.window_idx <= 12:
                by_window[t.window_idx].append(t)

        for w_idx in range(13):
            ts = by_window.get(w_idx, [])
            label = WINDOW_LABELS.get(w_idx, str(w_idx))
            if not ts:
                continue
            row = _stats_row(ts, window=label, delay_bars=delay, count=len(ts))
            rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _df_to_md(df: pd.DataFrame) -> str:
    """Convert DataFrame to Markdown table."""
    lines = []
    lines.append("| " + " | ".join(str(c) for c in df.columns) + " |")
    lines.append("|" + "|".join(["---"] * len(df.columns)) + "|")
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.values) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading 50 sessions...")
    sessions = load_all()
    print(f"  Loaded {len(sessions)} sessions")

    # -----------------------------------------------------------------------
    # Strict-mode baseline (P0 defaults: TYPE_B+, VOLP-03 veto ON, score>=60)
    # Used only for the "Baseline Performance" section header.
    # The synthetic dataset has VOLP-03 every 40 bars in ALL sessions, which
    # fires the session-level veto at bar 40 and blocks all further entries.
    # Only 18 TYPE_B signals exist across 50 sessions total, yielding ~1 trade
    # in strict mode — insufficient for distribution analysis.
    # -----------------------------------------------------------------------
    print("Running strict-mode baseline (P0 defaults)...")
    strict_trades: list[Trade] = []
    for name, (bars, scored) in sessions.items():
        strict_trades.extend(_simulate_session(bars, scored, name))
    print(f"  Strict-mode: {len(strict_trades)} trades (expected ~1 due to synthetic VOLP-03 artifact)")

    # -----------------------------------------------------------------------
    # RELAXED mode: score>=50, any tier, VOLP-03 veto OFF
    # Used for all four analyses — provides 200+ trades for statistics.
    # -----------------------------------------------------------------------
    print("Running relaxed-mode baseline (score>=50, any tier, no VOLP-03 veto)...")
    baseline_trades: list[Trade] = _sim_all(sessions)
    print(f"  Relaxed-mode: {len(baseline_trades)} trades")

    # Analysis 1: Time windows
    print("Analysis 1: Bar-of-day time windows...")
    df_windows = analyze_time_windows(baseline_trades)

    # Analysis 2: Confirmation delay
    print("Analysis 2: Confirmation delay (0, 1, 2 bars)...")
    df_delay = analyze_confirmation_delay(sessions)

    # Analysis 3: Signal confluence
    print("Analysis 3: Signal confluence...")
    df_confluence = analyze_signal_confluence(baseline_trades)

    # Analysis 4: Retrace entry
    print("Analysis 4: Pullback/retrace entry...")
    df_retrace = analyze_retrace_entry(sessions)

    # Cross-table: time window × delay
    print("Cross-analysis: time window × delay...")
    df_time_x_delay = analyze_time_x_delay(sessions)

    # ---------------------------------------------------------------------------
    # Build ENTRY-TIMING.md
    # ---------------------------------------------------------------------------

    # Relaxed-mode aggregate stats (what all analyses run on)
    bl_pnls = np.array([t.pnl_ticks for t in baseline_trades]) if baseline_trades else np.array([0.0])
    bl_wr   = float((bl_pnls > 0).sum() / len(bl_pnls))
    bl_gp   = float(bl_pnls[bl_pnls > 0].sum())
    bl_gl   = float(abs(bl_pnls[bl_pnls < 0].sum()))
    bl_pf   = bl_gp / bl_gl if bl_gl > 0 else 0.0

    # Strict-mode aggregate stats (header context only)
    st_pnls = np.array([t.pnl_ticks for t in strict_trades]) if strict_trades else np.array([0.0])
    st_wr   = float((st_pnls > 0).sum() / len(st_pnls)) if len(strict_trades) else 0.0
    st_pf_val = 0.0
    if len(strict_trades):
        st_gp = float(st_pnls[st_pnls > 0].sum())
        st_gl = float(abs(st_pnls[st_pnls < 0].sum()))
        st_pf_val = st_gp / st_gl if st_gl > 0 else 0.0

    # Best/worst windows (min 3 trades)
    eligible_windows = df_windows[df_windows["count"] >= 3].copy()
    best_window_row  = eligible_windows.loc[eligible_windows["avg_pnl_ticks"].idxmax()] if len(eligible_windows) else None
    worst_window_row = eligible_windows.loc[eligible_windows["avg_pnl_ticks"].idxmin()] if len(eligible_windows) else None

    # Best delay
    best_delay_row = df_delay.loc[df_delay["avg_pnl_ticks"].idxmax()] if len(df_delay) else None

    # Best retrace
    df_retrace_cmp   = df_retrace[df_retrace["total_trades"] > 0].copy()
    best_retrace_row = df_retrace_cmp.loc[df_retrace_cmp["avg_pnl_ticks"].idxmax()] if len(df_retrace_cmp) else None

    # Signal confluence verdict
    df_conf_summary = df_confluence[df_confluence["total_trades"] >= 3].copy()
    conf_verdict = "insufficient data (< 3 trades per bucket)"
    if len(df_conf_summary) >= 2:
        low_rows = df_conf_summary[df_conf_summary["signal_count_bucket"].isin(["1 signal", "2 signals"])]
        high_rows = df_conf_summary[df_conf_summary["signal_count_bucket"] == "3+ signals"]
        if len(low_rows) and len(high_rows):
            low  = float(low_rows["avg_pnl_ticks"].mean())
            high = float(high_rows["avg_pnl_ticks"].iloc[0])
            diff = high - low
            if diff > 0.5:
                conf_verdict = f"3+ signals improve avg PnL by +{diff:.1f} ticks vs 1-2 signals"
            elif diff < -0.5:
                conf_verdict = f"3+ signals HURT avg PnL by {diff:.1f} ticks vs 1-2 signals (may indicate chasing)"
            else:
                conf_verdict = f"3+ signals show negligible difference ({diff:+.1f} ticks)"

    # Top window×delay combos
    df_time_x_delay_top = (
        df_time_x_delay[df_time_x_delay["count"] >= 3]
        .sort_values("avg_pnl_ticks", ascending=False)
        .head(10)
    )

    # Pivot table
    try:
        df_pivot = df_time_x_delay[df_time_x_delay["count"] >= 2].pivot_table(
            index="window", columns="delay_bars", values="avg_pnl_ticks", aggfunc="mean"
        ).round(2)
        df_pivot.columns = [f"delay_{c}bar" for c in df_pivot.columns]
        df_pivot = df_pivot.reset_index()
    except Exception:
        df_pivot = pd.DataFrame()

    # Scalar helpers with safe fallback
    def _w(row, col, default=0):
        return row[col] if row is not None else default

    imm_delay_pnl = float(df_delay[df_delay["delay_bars"] == 0]["avg_pnl_ticks"].values[0]) if len(df_delay) else 0.0
    best_delay_pnl = float(best_delay_row["avg_pnl_ticks"]) if best_delay_row is not None else 0.0
    delay_delta = best_delay_pnl - imm_delay_pnl

    imm_retrace_pnl = float(df_retrace[df_retrace["retrace_ticks"] == 0.0]["avg_pnl_ticks"].values[0]) if len(df_retrace) else 0.0
    best_retrace_pnl = float(best_retrace_row["avg_pnl_ticks"]) if best_retrace_row is not None else 0.0
    retrace_delta = best_retrace_pnl - imm_retrace_pnl

    window_spread = float(eligible_windows["avg_pnl_ticks"].max() - eligible_windows["avg_pnl_ticks"].min()) if len(eligible_windows) >= 2 else 0.0

    # Determine best delay label
    best_delay_label = int(_w(best_delay_row, "delay_bars", 0))
    best_retrace_label = float(_w(best_retrace_row, "retrace_ticks", 0.0))

    delay_rec = (
        "No delay benefit — immediate entry wins"
        if best_delay_label == 0
        else f"{best_delay_label}-bar delay improves avg PnL by {delay_delta:+.2f}t"
    )
    retrace_rec = (
        "No retrace benefit — immediate entry wins"
        if best_retrace_label == 0.0
        else f"{best_retrace_label:.0f}-tick retrace improves avg PnL by {retrace_delta:+.2f}t"
    )
    time_filter_rec = (
        f"Blackout {_w(worst_window_row, 'window', 'N/A')} ({_w(worst_window_row, 'avg_pnl_ticks', 0.0):.2f}t avg)"
        if worst_window_row is not None
        else "No clear blackout window (insufficient data)"
    )
    confluence_rec = (
        "Require ≥3 signals"
        if "improve" in conf_verdict and "3+" in conf_verdict
        else "≥1 signal sufficient (no benefit from requiring more)"
    )

    md = f"""# DEEP6 Round 1 — Entry Timing Optimization

**Date**: 2026-04-15
**Sessions**: 50 (10 × trend_up, 10 × trend_down, 10 × ranging, 10 × volatile, 10 × slow_grind)
**Analysis mode**: RELAXED (score≥50, any tier, VOLP-03 veto OFF) — see Data Note below
**Exit params**: SL=20t, TP=40t, MaxBars=30, Slippage=1t (P0-fixed)

> **Data Note — Synthetic VOLP-03 Artifact**: All 50 synthetic sessions contain a VOLP-03
> volume-surge signal every 40 bars. With the P0 strict config (TYPE_B+ only, VOLP-03 veto ON)
> this produces only {len(strict_trades)} trade(s) across the entire corpus — statistically useless for
> entry-timing analysis. The scorer also produces only 18 TYPE_B signals across 50 sessions.
> This analysis uses RELAXED mode (score≥50, any directional tier, VOLP-03 veto OFF) to
> generate {len(baseline_trades)} trades with full time-of-day coverage. The timing patterns found here
> apply to signal quality regardless of tier cutoff; re-validate against live TYPE_B+ signals
> when real session data is available from Rithmic or Databento.

---

## Strict P0 Baseline (reference only — 1 trade total)

| Metric | Value |
|---|---|
| Config | score≥60, tier≥TYPE_B, VOLP-03 veto ON |
| Total trades | {len(strict_trades)} |
| Win rate | {st_wr:.1%} |
| Avg PnL/trade | {float(st_pnls.mean()):.2f} ticks |
| Profit factor | {st_pf_val:.2f} |

## Relaxed Baseline (used for all analyses below)

| Metric | Value |
|---|---|
| Config | score≥50, any tier, VOLP-03 veto OFF |
| Total trades | {len(baseline_trades)} |
| Win rate | {bl_wr:.1%} |
| Avg PnL/trade | {float(bl_pnls.mean()):.2f} ticks |
| Profit factor | {bl_pf:.2f} |
| Net PnL | {float(bl_pnls.sum()):.0f} ticks (${float(bl_pnls.sum()) * TICK_VALUE:.0f}) |

---

## Analysis 1: Bar-of-Day Distribution (30-Min Windows)

**Method**: Relaxed-mode trades tagged by `barsSinceOpen // 30` at signal bar.
1-min bars; window 0 = 0930-1000 ET, window 12 = 1530-1600 ET.
Midday block (bars 240-330 = ~1400-1430) is hard-blocked by scorer.

{_df_to_md(df_windows)}

**Best window**: {_w(best_window_row, "window", "N/A")} — avg {_w(best_window_row, "avg_pnl_ticks", 0.0):.2f}t, WR {_w(best_window_row, "win_rate", 0.0):.1%}, {int(_w(best_window_row, "count", 0))} trades
**Worst window**: {_w(worst_window_row, "window", "N/A")} — avg {_w(worst_window_row, "avg_pnl_ticks", 0.0):.2f}t, WR {_w(worst_window_row, "win_rate", 0.0):.1%}, {int(_w(worst_window_row, "count", 0))} trades

**Recommendation**: {time_filter_rec}. Windows with avg_pnl_ticks < 0 and count ≥ 3 are candidates for blackout.

---

## Analysis 2: Confirmation Filter (Entry Delay)

**Method**: Delay entry N bars after signal fires. Enter at bar-N close (pending expires after MaxBars=30).
All runs use relaxed mode (score≥50, any tier, no VOLP-03 veto).

{_df_to_md(df_delay)}

**Recommendation**: {delay_rec}. Note: delayed entries lose some fills (price gaps away) — net ticks reflects this.

---

## Analysis 3: Signal Confluence (Multi-Signal Entries)

**Method**: Count signals in trade direction on the signal bar. Bucket by count.
Hypothesis: more simultaneous signals = stronger confirmation = higher win rate.

{_df_to_md(df_confluence)}

**Verdict**: {conf_verdict}

---

## Analysis 4: Pullback Entry (Retrace from Signal Bar Close)

**Method**: After signal fires on bar N, wait for price to retrace N ticks from bar N close.
Entry triggers on first bar where close retraces target amount (pending expires after MaxBars=30).

{_df_to_md(df_retrace)}

**Recommendation**: {retrace_rec}. Larger retraces reduce fill rate but may improve per-trade quality.

---

## Cross-Analysis: Time Window × Entry Delay

**Top 10 window+delay combos by avg PnL (min 3 trades)**

{_df_to_md(df_time_x_delay_top) if len(df_time_x_delay_top) else "_Insufficient data (< 3 trades per cell)_"}

**Avg PnL pivot (ticks) — rows=window, cols=delay bars**

{_df_to_md(df_pivot) if len(df_pivot) else "_Insufficient data_"}

---

## Parameter Recommendations

| Parameter | Current | Recommended | Rationale |
|---|---|---|---|
| Entry delay | 0 bars | {best_delay_label} bars | {delay_rec} |
| Retrace filter | 0 ticks | {best_retrace_label:.0f} ticks | {retrace_rec} |
| Time-of-day filter | None | {time_filter_rec} | See Analysis 1 |
| Confluence gate | ≥1 signal | {confluence_rec} | {conf_verdict} |

---

## Top Finding

"""

    # Rank findings by magnitude for the top-finding callout
    findings = [
        ("time_window", window_spread,   f"Time-of-day spread: {window_spread:.1f} ticks peak-to-trough across 30-min windows — best window is {_w(best_window_row, 'window', 'N/A')} ({_w(best_window_row, 'avg_pnl_ticks', 0.0):.2f}t avg), worst is {_w(worst_window_row, 'window', 'N/A')} ({_w(worst_window_row, 'avg_pnl_ticks', 0.0):.2f}t avg)"),
        ("delay",       abs(delay_delta),   f"Confirmation delay: {delay_rec}"),
        ("retrace",     abs(retrace_delta),  f"Pullback retrace: {retrace_rec}"),
        ("confluence",  0.0,                 f"Signal confluence: {conf_verdict}"),
    ]
    findings.sort(key=lambda x: abs(x[1]), reverse=True)

    md += f"**{findings[0][2]}**\n\n"
    for f_key, f_mag, f_desc in findings:
        md += f"- {f_desc}\n"

    md += "\n---\n_Generated by `deep6/backtest/round1_entry_timing.py` — Round 1 Entry Timing Optimization_\n"

    out_path = OUTPUT_DIR / "ENTRY-TIMING.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"\nReport written to: {out_path}")

    print("\n=== TOP FINDINGS ===")
    for _, _, desc in findings:
        print(f"  {desc}")
    print(f"\nRelaxed baseline: {len(baseline_trades)} trades, WR={bl_wr:.1%}, avg={float(bl_pnls.mean()):.2f}t, PF={bl_pf:.2f}")
    print(f"Strict baseline:  {len(strict_trades)} trades (VOLP-03 artifact — see Data Note)")
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
