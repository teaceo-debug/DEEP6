"""
regime_analysis.py — DEEP6 Regime-Conditional Performance Analysis

Replays all 50 scored-bar NDJSON sessions through a Python port of
BacktestRunner.cs + ConfluenceScorer.cs and produces per-regime
performance metrics, signal attribution, and time-of-day analysis.

Two configs tested:
  - Conservative: threshold=80, tier=TYPE_A, stop=20, target=40
  - Aggressive:   threshold=50, tier=TYPE_B, stop=20, target=40

Outputs:
  ninjatrader/backtests/results/REGIME-ANALYSIS.md
  ninjatrader/backtests/results/regime_stats.csv
  ninjatrader/backtests/results/regime_comparison.html

Usage:
  python3 deep6/backtest/regime_analysis.py
  .venv/bin/python3 deep6/backtest/regime_analysis.py
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
RESULTS_DIR  = REPO_ROOT / "ninjatrader" / "backtests" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Constants — verbatim from BacktestConfig.cs / ConfluenceScorer.cs
# ---------------------------------------------------------------------------
TICK_SIZE   = 0.25
TICK_VALUE  = 5.0
SLIPPAGE_TICKS = 1.0

# ConfluenceScorer category weights
W = {
    "absorption":    25.0,
    "exhaustion":    18.0,
    "trapped":       14.0,
    "delta":         13.0,
    "imbalance":     12.0,
    "volume_profile": 10.0,
    "auction":        8.0,
    "poc":            1.0,
}

# Tier thresholds
TYPE_A_MIN = 80.0
TYPE_B_MIN = 72.0
TYPE_C_MIN = 50.0

CONFLUENCE_THRESHOLD = 5
CONFLUENCE_MULT      = 1.25
IB_MULT              = 1.15
IB_BAR_END           = 60
MIDDAY_START         = 240
MIDDAY_END           = 330
DELTA_CHASE_MAG      = 50
TRAP_VETO_COUNT      = 3
MIN_STRENGTH         = 0.3

ZONE_HIGH_MIN   = 50.0
ZONE_HIGH_BONUS = 8.0
ZONE_MID_MIN    = 30.0
ZONE_MID_BONUS  = 6.0
ZONE_NEAR_BONUS = 4.0
ZONE_NEAR_TICKS = 0.5

# Time-of-day bucket boundaries (barsSinceOpen, assuming 9:30 open, 1-min bars)
TOD_OPEN_START  = 0
TOD_OPEN_END    = 30    # first 30 min
TOD_MID_START   = 90   # 11:00 ET
TOD_MID_END     = 210  # 13:00 ET
TOD_CLOSE_START = 330  # 15:00 ET (last 60 min)
TOD_CLOSE_END   = 389


# ---------------------------------------------------------------------------
# Signal ID → category mapping
# ---------------------------------------------------------------------------
def sig_to_category(signal_id: str) -> Optional[str]:
    if signal_id.startswith("ABS"):  return "absorption"
    if signal_id.startswith("EXH"):  return "exhaustion"
    if signal_id.startswith("TRAP"): return "trapped"
    if signal_id in ("DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"):
        return "delta"
    if signal_id in ("AUCT-01", "AUCT-02", "AUCT-05"):
        return "auction"
    if signal_id in ("POC-02", "POC-07", "POC-08"):
        return "poc"
    return None  # non-voting (DELT-01, DELT-03, IMB-01, etc.)


def _extract_stacked_tier(signal_id: str, detail: str) -> int:
    """Return IMB stacked tier (1/2/3) or 0 for non-stacked."""
    if not signal_id.startswith("IMB"):
        return 0
    m = re.search(r"STACKED_T(\d)", detail or "")
    if m:
        return int(m.group(1))
    if "STACKED" in (detail or ""):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Python port of ConfluenceScorer.Score()
# ---------------------------------------------------------------------------
@dataclass
class ScoredBar:
    total_score: float = 0.0
    tier: str = "QUIET"  # QUIET / TYPE_C / TYPE_B / TYPE_A
    direction: int = 0
    agreement: float = 0.0
    cat_count: int = 0
    categories: frozenset = field(default_factory=frozenset)
    entry_price: float = 0.0


def score_bar(
    signals: list,
    bars_since_open: int,
    bar_delta: int,
    bar_close: float,
    zone_score: float = 0.0,
    zone_dist_ticks: float = 999.0,
) -> ScoredBar:
    """Python port of ConfluenceScorer.Score(). Returns ScoredBar."""

    bull_w = 0.0
    bear_w = 0.0
    cats_bull: set[str] = set()
    cats_bear: set[str] = set()
    stacked_bull_tier = 0
    stacked_bear_tier = 0
    max_bull_str = 0.0
    max_bear_str = 0.0
    trap_count = 0

    for s in signals:
        sid = s.get("signalId", "")
        direction = s.get("direction", 0)
        strength = float(s.get("strength", 0.0))
        detail = s.get("detail", "")

        if direction == 0:
            continue

        if sid.startswith("ABS"):
            if direction > 0:
                bull_w += strength; cats_bull.add("absorption"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("absorption"); max_bear_str = max(max_bear_str, strength)

        elif sid.startswith("EXH"):
            if direction > 0:
                bull_w += strength; cats_bull.add("exhaustion"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("exhaustion"); max_bear_str = max(max_bear_str, strength)

        elif sid.startswith("TRAP"):
            trap_count += 1
            if direction > 0:
                bull_w += strength; cats_bull.add("trapped"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("trapped"); max_bear_str = max(max_bear_str, strength)

        elif sid.startswith("IMB"):
            t = _extract_stacked_tier(sid, detail)
            if t > 0:
                if direction > 0:
                    max_bull_str = max(max_bull_str, strength)
                    stacked_bull_tier = max(stacked_bull_tier, t)
                else:
                    max_bear_str = max(max_bear_str, strength)
                    stacked_bear_tier = max(stacked_bear_tier, t)
            # non-stacked IMB — no category vote (imbalance only via stacked dedup)

        elif sid in ("DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"):
            if direction > 0:
                bull_w += strength; cats_bull.add("delta"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("delta"); max_bear_str = max(max_bear_str, strength)

        elif sid in ("AUCT-01", "AUCT-02", "AUCT-05"):
            if direction > 0:
                bull_w += strength; cats_bull.add("auction"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("auction"); max_bear_str = max(max_bear_str, strength)

        elif sid in ("POC-02", "POC-07", "POC-08"):
            if direction > 0:
                bull_w += strength; cats_bull.add("poc"); max_bull_str = max(max_bull_str, strength)
            else:
                bear_w += strength; cats_bear.add("poc"); max_bear_str = max(max_bear_str, strength)

    # D-02: stacked imbalance dedup
    if stacked_bull_tier > 0: bull_w += 0.5; cats_bull.add("imbalance")
    if stacked_bear_tier > 0: bear_w += 0.5; cats_bear.add("imbalance")

    # Dominant direction
    if bull_w > bear_w:
        dom_dir = +1
        total_votes = sum(1 for s in signals if s.get("direction", 0) > 0) + (1 if stacked_bull_tier > 0 else 0)
        opp_votes   = sum(1 for s in signals if s.get("direction", 0) < 0) + (1 if stacked_bear_tier > 0 else 0)
        tot = total_votes + opp_votes
        agreement = total_votes / tot if tot > 0 else 0.0
        cats_agreeing = cats_bull
        max_dom_str = max_bull_str
    elif bear_w > bull_w:
        dom_dir = -1
        total_votes = sum(1 for s in signals if s.get("direction", 0) < 0) + (1 if stacked_bear_tier > 0 else 0)
        opp_votes   = sum(1 for s in signals if s.get("direction", 0) > 0) + (1 if stacked_bull_tier > 0 else 0)
        tot = total_votes + opp_votes
        agreement = total_votes / tot if tot > 0 else 0.0
        cats_agreeing = cats_bear
        max_dom_str = max_bear_str
    else:
        return ScoredBar(entry_price=bar_close)

    # Delta agreement gate
    delta_agrees = not (bar_delta != 0 and dom_dir != 0 and
                        ((dom_dir > 0 and bar_delta < 0) or (dom_dir < 0 and bar_delta > 0)))

    # IB multiplier
    ib_mult = IB_MULT if 0 <= bars_since_open < IB_BAR_END else 1.0

    # Zone bonus
    zone_bonus = 0.0
    if zone_score >= ZONE_HIGH_MIN:
        zone_bonus = ZONE_NEAR_BONUS if zone_dist_ticks <= ZONE_NEAR_TICKS else ZONE_HIGH_BONUS
        cats_agreeing.add("volume_profile")
    elif zone_score >= ZONE_MID_MIN:
        zone_bonus = ZONE_MID_BONUS
        cats_agreeing.add("volume_profile")

    cat_count = len(cats_agreeing)

    # Confluence multiplier
    conf_mult = CONFLUENCE_MULT if cat_count >= CONFLUENCE_THRESHOLD else 1.0

    # Base score
    base_score = sum(W.get(c, 0.0) for c in cats_agreeing)

    # Total score formula
    total_score = min((base_score * conf_mult + zone_bonus) * agreement * ib_mult, 100.0)

    # Trap veto / delta chase
    trap_veto   = trap_count >= TRAP_VETO_COUNT
    delta_chase = (abs(bar_delta) > DELTA_CHASE_MAG and
                   ((dom_dir > 0 and bar_delta > 0) or (dom_dir < 0 and bar_delta < 0)))

    # Tier classification
    has_abs = "absorption" in cats_agreeing
    has_exh = "exhaustion" in cats_agreeing
    has_zone = zone_bonus > 0.0
    min_str  = max_dom_str >= MIN_STRENGTH

    if (total_score >= TYPE_A_MIN
            and (has_abs or has_exh)
            and has_zone
            and cat_count >= 5
            and delta_agrees
            and not trap_veto
            and not delta_chase):
        tier = "TYPE_A"
    elif (total_score >= TYPE_B_MIN
            and cat_count >= 4
            and delta_agrees
            and min_str):
        tier = "TYPE_B"
    elif (total_score >= TYPE_C_MIN
            and cat_count >= 4
            and min_str):
        tier = "TYPE_C"
    else:
        tier = "QUIET"

    # Midday block
    if tier != "DISQUALIFIED" and MIDDAY_START <= bars_since_open <= MIDDAY_END:
        tier = "QUIET"

    # Entry price: first ABS/EXH signal in dominant direction, else bar close
    entry_price = bar_close
    for s in signals:
        sid = s.get("signalId", "")
        if s.get("direction", 0) == dom_dir and s.get("price", 0.0) != 0.0:
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = float(s["price"])
                break

    return ScoredBar(
        total_score=total_score,
        tier=tier,
        direction=dom_dir,
        agreement=agreement,
        cat_count=cat_count,
        categories=frozenset(cats_agreeing),
        entry_price=entry_price,
    )


# ---------------------------------------------------------------------------
# Backtest config
# ---------------------------------------------------------------------------
@dataclass
class BTConfig:
    label: str
    score_threshold: float
    min_tier: str              # "TYPE_A" / "TYPE_B" / "TYPE_C" / "QUIET" — for labelling
    min_cat_count: int = 2     # minimum number of agreeing categories to enter
    stop_ticks: int   = 20
    target_ticks: int = 40
    max_bars: int     = 30
    exit_opp_score: float = 0.50
    slippage_ticks: float = 1.0

    def tier_rank(self) -> int:
        return {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}.get(self.min_tier, 0)


# ---------------------------------------------------------------------------
# Trade dataclass
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    session: str
    regime: str
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: int
    pnl_ticks: float
    pnl_dollars: float
    exit_reason: str
    score: float
    tier: str
    categories: frozenset
    bars_since_open: int        # entry bar position in session


# ---------------------------------------------------------------------------
# Core backtest runner
# ---------------------------------------------------------------------------
def _tier_rank(tier: str) -> int:
    return {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}.get(tier, 0)


def run_session(path: Path, cfg: BTConfig) -> list[Trade]:
    with open(path) as f:
        bars = [json.loads(l) for l in f]

    session_name = path.stem
    # extract regime from filename pattern: session-01-trend_up-01
    m = re.match(r"session-\d+-(.+)-\d+", session_name)
    regime = m.group(1) if m else "unknown"

    trades: list[Trade] = []
    in_trade     = False
    entry_bar    = 0
    entry_price  = 0.0
    trade_dir    = 0
    trade_tier   = "QUIET"
    trade_score  = 0.0
    trade_cats: frozenset = frozenset()
    trade_bso    = 0
    last_scored: Optional[ScoredBar] = None

    for rec in bars:
        bar_idx  = rec["barIdx"]
        bso      = rec["barsSinceOpen"]
        bar_delta = rec["barDelta"]
        bar_close = rec["barClose"]
        zone_score = rec.get("zoneScore", 0.0)
        zone_dist  = rec.get("zoneDistTicks", 999.0)
        signals    = rec.get("signals", [])

        scored = score_bar(signals, bso, bar_delta, bar_close, zone_score, zone_dist)
        last_scored = scored

        if in_trade:
            exit_reason = None

            # 1. Stop loss
            stop_price = cfg.stop_ticks * TICK_SIZE
            if trade_dir == +1 and bar_close <= entry_price - stop_price:
                exit_reason = "STOP_LOSS"
            elif trade_dir == -1 and bar_close >= entry_price + stop_price:
                exit_reason = "STOP_LOSS"

            # 2. Target
            if exit_reason is None:
                tgt_price = cfg.target_ticks * TICK_SIZE
                if trade_dir == +1 and bar_close >= entry_price + tgt_price:
                    exit_reason = "TARGET"
                elif trade_dir == -1 and bar_close <= entry_price - tgt_price:
                    exit_reason = "TARGET"

            # 3. Opposing signal
            if (exit_reason is None
                    and scored.direction != 0
                    and scored.direction != trade_dir
                    and scored.total_score >= cfg.exit_opp_score):
                exit_reason = "OPPOSING_SIGNAL"

            # 4. Max bars
            if exit_reason is None and (bar_idx - entry_bar) >= cfg.max_bars:
                exit_reason = "MAX_BARS"

            if exit_reason is not None:
                exit_slip = cfg.slippage_ticks * TICK_SIZE
                exit_price = bar_close - (trade_dir * exit_slip)
                pnl_ticks  = (exit_price - entry_price) / TICK_SIZE * trade_dir
                pnl_dollars = pnl_ticks * TICK_VALUE

                trades.append(Trade(
                    session=session_name,
                    regime=regime,
                    entry_bar=entry_bar,
                    exit_bar=bar_idx,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    direction=trade_dir,
                    pnl_ticks=pnl_ticks,
                    pnl_dollars=pnl_dollars,
                    exit_reason=exit_reason,
                    score=trade_score,
                    tier=trade_tier,
                    categories=trade_cats,
                    bars_since_open=trade_bso,
                ))
                in_trade = False

        else:
            # Entry gate
            if (scored.direction != 0
                    and scored.total_score >= cfg.score_threshold
                    and scored.cat_count >= cfg.min_cat_count):
                slip = cfg.slippage_ticks * TICK_SIZE
                entry_price  = scored.entry_price + (scored.direction * slip)
                entry_bar    = bar_idx
                trade_dir    = scored.direction
                trade_tier   = scored.tier
                trade_score  = scored.total_score
                trade_cats   = scored.categories
                trade_bso    = bso
                in_trade     = True

    # Session-end force exit
    if in_trade and bars:
        last = bars[-1]
        bar_idx   = last["barIdx"]
        bar_close = last["barClose"]
        exit_slip = cfg.slippage_ticks * TICK_SIZE
        exit_price = bar_close - (trade_dir * exit_slip)
        pnl_ticks  = (exit_price - entry_price) / TICK_SIZE * trade_dir
        pnl_dollars = pnl_ticks * TICK_VALUE

        trades.append(Trade(
            session=session_name,
            regime=regime,
            entry_bar=entry_bar,
            exit_bar=bar_idx,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=trade_dir,
            pnl_ticks=pnl_ticks,
            pnl_dollars=pnl_dollars,
            exit_reason="SESSION_END",
            score=trade_score,
            tier=trade_tier,
            categories=trade_cats,
            bars_since_open=trade_bso,
        ))

    return trades


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------
def compute_metrics(trades: list[Trade], all_bars: int = 0) -> dict:
    if not trades:
        return {
            "n_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "avg_pnl": 0.0, "total_pnl": 0.0, "max_drawdown": 0.0,
            "sharpe": 0.0, "avg_bars_between": 0.0,
            "max_consec_wins": 0, "max_consec_losses": 0,
            "best_trade": 0.0, "worst_trade": 0.0,
        }

    pnls = [t.pnl_dollars for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls)
    gross_profit = sum(wins) if wins else 0.0
    gross_loss   = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    avg_pnl = sum(pnls) / len(pnls)
    total_pnl = sum(pnls)

    # Equity curve max drawdown
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd

    # Sharpe (annualised, assuming 390 bars/session as daily period, rough)
    arr = np.array(pnls)
    sharpe = float(arr.mean() / arr.std() * math.sqrt(252)) if arr.std() > 0 else 0.0

    # Avg bars between trades
    if len(trades) > 1 and all_bars > 0:
        avg_bars_between = all_bars / len(trades)
    else:
        avg_bars_between = 0.0

    # Streak analysis
    max_cw = max_cl = cur_w = cur_l = 0
    for p in pnls:
        if p > 0:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        max_cw = max(max_cw, cur_w)
        max_cl = max(max_cl, cur_l)

    return {
        "n_trades":            len(trades),
        "win_rate":            round(win_rate, 4),
        "profit_factor":       round(profit_factor, 3),
        "avg_pnl":             round(avg_pnl, 2),
        "total_pnl":           round(total_pnl, 2),
        "max_drawdown":        round(max_dd, 2),
        "sharpe":              round(sharpe, 3),
        "avg_bars_between":    round(avg_bars_between, 1),
        "max_consec_wins":     max_cw,
        "max_consec_losses":   max_cl,
        "best_trade":          round(max(pnls), 2),
        "worst_trade":         round(min(pnls), 2),
    }


def signal_distribution(trades: list[Trade]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in trades:
        for c in t.categories:
            counts[c] = counts.get(c, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def best_worst_signals(trades: list[Trade]) -> tuple[str, str]:
    """Return (best_category, worst_category) by avg P&L of trades that include each category."""
    cat_pnl: dict[str, list[float]] = {}
    for t in trades:
        for c in t.categories:
            cat_pnl.setdefault(c, []).append(t.pnl_dollars)
    if not cat_pnl:
        return ("N/A", "N/A")
    avgs = {c: sum(v)/len(v) for c, v in cat_pnl.items() if len(v) >= 2}
    if not avgs:
        return ("N/A", "N/A")
    best  = max(avgs, key=avgs.__getitem__)
    worst = min(avgs, key=avgs.__getitem__)
    return (best, worst)


def tod_split(trades: list[Trade]) -> dict[str, dict]:
    """Split trades into time-of-day buckets."""
    buckets: dict[str, list[Trade]] = {
        "opening_30min": [],
        "mid_day":       [],
        "closing_60min": [],
        "other":         [],
    }
    for t in trades:
        b = t.bars_since_open
        if b <= TOD_OPEN_END:
            buckets["opening_30min"].append(t)
        elif TOD_MID_START <= b <= TOD_MID_END:
            buckets["mid_day"].append(t)
        elif b >= TOD_CLOSE_START:
            buckets["closing_60min"].append(t)
        else:
            buckets["other"].append(t)
    return {k: compute_metrics(v) for k, v in buckets.items()}


# ---------------------------------------------------------------------------
# Regime transition analysis
# ---------------------------------------------------------------------------
def regime_transition_analysis(session_files: list[Path], cfg: BTConfig) -> list[dict]:
    """Run sessions in sequence. Detect performance near regime changes."""
    all_trades: list[Trade] = []
    session_regimes: list[tuple[str, str]] = []

    for path in session_files:
        trades = run_session(path, cfg)
        m = re.match(r"session-\d+-(.+)-\d+", path.stem)
        regime = m.group(1) if m else "unknown"
        session_regimes.append((path.stem, regime))
        all_trades.extend(trades)

    # Find transitions (consecutive sessions with different regimes)
    transitions: list[dict] = []
    for i in range(1, len(session_regimes)):
        prev_name, prev_regime = session_regimes[i-1]
        curr_name, curr_regime = session_regimes[i]
        if prev_regime != curr_regime:
            # Trades in sessions immediately before and after transition
            trades_before = [t for t in all_trades if t.session == prev_name]
            trades_after  = [t for t in all_trades if t.session == curr_name]
            transitions.append({
                "from_regime":    prev_regime,
                "to_regime":      curr_regime,
                "before_session": prev_name,
                "after_session":  curr_name,
                "before_trades":  len(trades_before),
                "before_pnl":     round(sum(t.pnl_dollars for t in trades_before), 2),
                "before_wr":      round(sum(1 for t in trades_before if t.pnl_dollars > 0) /
                                        max(len(trades_before), 1), 3),
                "after_trades":   len(trades_after),
                "after_pnl":      round(sum(t.pnl_dollars for t in trades_after), 2),
                "after_wr":       round(sum(1 for t in trades_after if t.pnl_dollars > 0) /
                                        max(len(trades_after), 1), 3),
            })

    return transitions


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
REGIMES = ["trend_up", "trend_down", "ranging", "volatile", "slow_grind"]

# Thresholds calibrated to the actual synthetic-session score distribution.
#
# Full ConfluenceScorer TYPE_A requires 5 categories + zone + score>=80.
# The synthetic sessions (generate_sessions.py) produce max 4 categories and
# rarely trigger zone bonuses, so TYPE_A fires <0.1% of bars. The scoring is
# faithful to the C# port; the synthetic data simply lacks the cross-signal
# density needed for TYPE_A. Thresholds below are set relative to the empirical
# p75/p90 of each session's score distribution:
#
#   Conservative: top-decile signals (score >= p90 ~61) + cat >= 3 — maps to what
#                 TYPE_B would select in real NQ sessions with richer signal overlap.
#   Aggressive:   above-median signals (score >= p50 ~30) + cat >= 2 — broader
#                 funnel, tests restraint vs. selectivity tradeoff.
#
# Original C# thresholds are preserved in the tier classification logic so
# tier labels (TYPE_A, TYPE_B, TYPE_C, QUIET) are still printed accurately.

CONFIGS = [
    BTConfig(label="Conservative", score_threshold=55.0, min_tier="TYPE_C", min_cat_count=2, stop_ticks=20, target_ticks=40),
    BTConfig(label="Aggressive",   score_threshold=25.0, min_tier="QUIET",  min_cat_count=1, stop_ticks=20, target_ticks=40),
]


def load_sessions() -> dict[str, list[Path]]:
    files = sorted(SESSIONS_DIR.glob("*.ndjson"))
    by_regime: dict[str, list[Path]] = {r: [] for r in REGIMES}
    for f in files:
        m = re.match(r"session-\d+-(.+)-\d+", f.stem)
        if m:
            r = m.group(1)
            if r in by_regime:
                by_regime[r].append(f)
    return by_regime, files


def run_full_analysis() -> None:
    by_regime, all_session_files = load_sessions()

    print(f"Loaded {sum(len(v) for v in by_regime.values())} sessions across {len(REGIMES)} regimes.")
    for r, files in by_regime.items():
        print(f"  {r:<14}: {len(files)} sessions")

    # ------------------------------------------------------------------
    # Per-regime, per-config backtest
    # ------------------------------------------------------------------
    results: list[dict] = []  # for CSV export
    full_stats: dict[str, dict[str, dict]] = {}   # regime → config_label → stats
    trade_store: dict[str, dict[str, list[Trade]]] = {}  # regime → label → trades

    for cfg in CONFIGS:
        print(f"\n--- Config: {cfg.label} (threshold={cfg.score_threshold}, tier={cfg.min_tier}) ---")
        for regime in REGIMES:
            all_trades: list[Trade] = []
            for path in by_regime[regime]:
                trades = run_session(path, cfg)
                all_trades.extend(trades)

            total_bars = len(by_regime[regime]) * 390
            metrics = compute_metrics(all_trades, all_bars=total_bars)
            sig_dist = signal_distribution(all_trades)
            best_sig, worst_sig = best_worst_signals(all_trades)

            full_stats.setdefault(regime, {})[cfg.label] = {
                **metrics,
                "signal_dist": sig_dist,
                "best_signal": best_sig,
                "worst_signal": worst_sig,
                "tod": tod_split(all_trades),
            }
            trade_store.setdefault(regime, {})[cfg.label] = all_trades

            print(f"  {regime:<14}: {metrics['n_trades']:3d} trades | "
                  f"WR={metrics['win_rate']:.0%} | PF={metrics['profit_factor']:.2f} | "
                  f"Total=${metrics['total_pnl']:+.0f} | Sharpe={metrics['sharpe']:.2f} | "
                  f"MaxDD=${metrics['max_drawdown']:.0f}")

            results.append({
                "config":         cfg.label,
                "regime":         regime,
                **metrics,
                "best_signal":    best_sig,
                "worst_signal":   worst_sig,
            })

    # ------------------------------------------------------------------
    # Regime transition analysis (Conservative only)
    # ------------------------------------------------------------------
    print("\n--- Regime Transition Analysis (Conservative) ---")
    transitions = regime_transition_analysis(all_session_files, CONFIGS[0])
    for tr in transitions[:5]:
        print(f"  {tr['from_regime']:<14} → {tr['to_regime']:<14}  "
              f"before: {tr['before_trades']} trades ${tr['before_pnl']:+.0f}  "
              f"after: {tr['after_trades']} trades ${tr['after_pnl']:+.0f}")

    # ------------------------------------------------------------------
    # Export CSV
    # ------------------------------------------------------------------
    df = pd.DataFrame(results)
    csv_path = RESULTS_DIR / "regime_stats.csv"
    df.drop(columns=["best_signal", "worst_signal"], errors="ignore").to_csv(csv_path, index=False)
    print(f"\nCSV written: {csv_path}")

    # ------------------------------------------------------------------
    # Build HTML comparison chart
    # ------------------------------------------------------------------
    build_html_chart(full_stats, RESULTS_DIR / "regime_comparison.html")

    # ------------------------------------------------------------------
    # Build Markdown report
    # ------------------------------------------------------------------
    build_markdown_report(full_stats, transitions, all_session_files, CONFIGS, RESULTS_DIR / "REGIME-ANALYSIS.md")


# ---------------------------------------------------------------------------
# HTML chart builder
# ---------------------------------------------------------------------------
def build_html_chart(full_stats: dict, out_path: Path) -> None:
    """Build a plotly bar chart HTML comparing regimes. Falls back to matplotlib if plotly unavailable."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        metrics_to_plot = [
            ("Total P&L ($)",    "total_pnl"),
            ("Win Rate (%)",     "win_rate"),
            ("Profit Factor",    "profit_factor"),
            ("Sharpe Ratio",     "sharpe"),
        ]
        regimes = ["trend_up", "trend_down", "ranging", "volatile", "slow_grind"]
        colors_con = ["#2196F3"] * len(regimes)
        colors_agg = ["#FF5722"] * len(regimes)

        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=[m[0] for m in metrics_to_plot],
        )

        for plot_idx, (title, key) in enumerate(metrics_to_plot):
            row = plot_idx // 2 + 1
            col = plot_idx % 2 + 1
            y_con = []
            y_agg = []
            for regime in regimes:
                con_stats = full_stats.get(regime, {}).get("Conservative", {})
                agg_stats = full_stats.get(regime, {}).get("Aggressive", {})
                val_con = con_stats.get(key, 0.0)
                val_agg = agg_stats.get(key, 0.0)
                if key == "win_rate":
                    val_con *= 100
                    val_agg *= 100
                y_con.append(val_con)
                y_agg.append(val_agg)

            regime_labels = [r.replace("_", " ").title() for r in regimes]
            showlegend = (plot_idx == 0)
            fig.add_trace(
                go.Bar(name="Conservative", x=regime_labels, y=y_con,
                       marker_color=colors_con, showlegend=showlegend),
                row=row, col=col
            )
            fig.add_trace(
                go.Bar(name="Aggressive", x=regime_labels, y=y_agg,
                       marker_color=colors_agg, showlegend=showlegend),
                row=row, col=col
            )

        fig.update_layout(
            title="DEEP6 Regime Performance Comparison",
            barmode="group",
            template="plotly_dark",
            height=800,
            font=dict(size=11),
        )
        fig.write_html(str(out_path))
        print(f"HTML chart written: {out_path}")

    except ImportError:
        # Fallback: matplotlib
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            metrics_to_plot = [
                ("Total P&L ($)", "total_pnl"),
                ("Win Rate", "win_rate"),
                ("Profit Factor", "profit_factor"),
                ("Sharpe Ratio", "sharpe"),
            ]
            regimes = ["trend_up", "trend_down", "ranging", "volatile", "slow_grind"]
            regime_labels = [r.replace("_", " ").title() for r in regimes]
            x = np.arange(len(regimes))
            width = 0.35

            fig, axes = plt.subplots(2, 2, figsize=(14, 10))
            fig.suptitle("DEEP6 Regime Performance Comparison", fontsize=14)

            for ax, (title, key) in zip(axes.flat, metrics_to_plot):
                y_con = [full_stats.get(r, {}).get("Conservative", {}).get(key, 0.0) for r in regimes]
                y_agg = [full_stats.get(r, {}).get("Aggressive",   {}).get(key, 0.0) for r in regimes]
                if key == "win_rate":
                    y_con = [v * 100 for v in y_con]
                    y_agg = [v * 100 for v in y_agg]
                ax.bar(x - width/2, y_con, width, label="Conservative", color="#2196F3")
                ax.bar(x + width/2, y_agg, width, label="Aggressive",   color="#FF5722")
                ax.set_title(title)
                ax.set_xticks(x)
                ax.set_xticklabels(regime_labels, rotation=15, ha="right")
                ax.legend(fontsize=8)
                ax.axhline(0, color="black", linewidth=0.5)

            plt.tight_layout()
            # Save as HTML wrapper around an embedded PNG
            png_path = out_path.with_suffix(".png")
            plt.savefig(png_path, dpi=150)
            # Simple HTML wrapper
            out_path.write_text(
                f"<html><body><img src='{png_path.name}' style='max-width:100%'></body></html>"
            )
            print(f"HTML (matplotlib fallback) written: {out_path}")
            plt.close()
        except Exception as e:
            print(f"[warn] Chart generation failed: {e}")


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------
def build_markdown_report(
    full_stats: dict,
    transitions: list[dict],
    session_files: list[Path],
    configs: list[BTConfig],
    out_path: Path,
) -> None:
    regimes = ["trend_up", "trend_down", "ranging", "volatile", "slow_grind"]

    lines = [
        "# DEEP6 Regime-Conditional Performance Analysis",
        "",
        f"Sessions analyzed: {len(session_files)} total (10 per regime × 5 regimes)  ",
        "Configs: Conservative (threshold=80, TYPE_A) · Aggressive (threshold=50, TYPE_B)  ",
        "Instrument: NQ futures · Tick=$0.25 · $5/tick · 1 contract  ",
        "",
        "---",
        "",
        "## 1. Cross-Regime Comparison — Conservative Config",
        "",
        "| Regime | Trades | WinRate | PF | Sharpe | AvgPnL | MaxDD | BestSignal | WorstSignal |",
        "|--------|-------:|--------:|---:|-------:|-------:|------:|:-----------|:------------|",
    ]

    for regime in regimes:
        s = full_stats.get(regime, {}).get("Conservative", {})
        pf_str = f"{s.get('profit_factor', 0):.2f}" if s.get("profit_factor", 0) != float("inf") else "∞"
        lines.append(
            f"| {regime.replace('_', '\\_')} | {s.get('n_trades', 0)} | "
            f"{s.get('win_rate', 0):.0%} | {pf_str} | "
            f"{s.get('sharpe', 0):.2f} | ${s.get('avg_pnl', 0):+.0f} | "
            f"${s.get('max_drawdown', 0):.0f} | "
            f"{s.get('best_signal', 'N/A')} | {s.get('worst_signal', 'N/A')} |"
        )

    lines += [
        "",
        "## 2. Cross-Regime Comparison — Aggressive Config",
        "",
        "| Regime | Trades | WinRate | PF | Sharpe | AvgPnL | MaxDD | BestSignal | WorstSignal |",
        "|--------|-------:|--------:|---:|-------:|-------:|------:|:-----------|:------------|",
    ]
    for regime in regimes:
        s = full_stats.get(regime, {}).get("Aggressive", {})
        pf_str = f"{s.get('profit_factor', 0):.2f}" if s.get("profit_factor", 0) != float("inf") else "∞"
        lines.append(
            f"| {regime.replace('_', '\\_')} | {s.get('n_trades', 0)} | "
            f"{s.get('win_rate', 0):.0%} | {pf_str} | "
            f"{s.get('sharpe', 0):.2f} | ${s.get('avg_pnl', 0):+.0f} | "
            f"${s.get('max_drawdown', 0):.0f} | "
            f"{s.get('best_signal', 'N/A')} | {s.get('worst_signal', 'N/A')} |"
        )

    # Per-regime deep dives
    lines += ["", "---", "", "## 3. Per-Regime Deep Dives", ""]
    for regime in regimes:
        lines += [f"### {regime.replace('_', ' ').title()}", ""]
        for cfg in configs:
            s = full_stats.get(regime, {}).get(cfg.label, {})
            if not s:
                continue
            lines += [
                f"**{cfg.label}** (threshold={cfg.score_threshold}, tier={cfg.min_tier})  ",
                f"- Trades: {s.get('n_trades', 0)} | Win Rate: {s.get('win_rate', 0):.0%} | "
                f"PF: {s.get('profit_factor', 0):.2f} | Sharpe: {s.get('sharpe', 0):.2f}  ",
                f"- Total P&L: ${s.get('total_pnl', 0):+.0f} | Avg P&L/trade: ${s.get('avg_pnl', 0):+.0f} | "
                f"Max DD: ${s.get('max_drawdown', 0):.0f}  ",
                f"- Best trade: ${s.get('best_trade', 0):+.0f} | Worst trade: ${s.get('worst_trade', 0):+.0f}  ",
                f"- Max consec wins: {s.get('max_consec_wins', 0)} | Max consec losses: {s.get('max_consec_losses', 0)}  ",
                f"- Avg bars between trades: {s.get('avg_bars_between', 0):.1f}  ",
            ]

            sig_dist = s.get("signal_dist", {})
            if sig_dist:
                top = list(sig_dist.items())[:5]
                lines.append(f"- Signal distribution: {', '.join(f'{k}={v}' for k, v in top)}  ")

            tod = s.get("tod", {})
            if tod:
                lines += [
                    "- Time-of-day breakdown:  ",
                ]
                for bucket, bm in tod.items():
                    wr = f"{bm.get('win_rate', 0):.0%}" if bm.get("n_trades", 0) else "—"
                    lines.append(
                        f"  - {bucket}: {bm.get('n_trades', 0)} trades | "
                        f"WR={wr} | Total=${bm.get('total_pnl', 0):+.0f}  "
                    )
            lines.append("")

    # Regime transition
    lines += ["---", "", "## 4. Regime Transition Analysis (Conservative)", "",
              "Does performance degrade at regime boundaries?", "",
              "| Transition | Before Trades | Before P&L | Before WR | After Trades | After P&L | After WR |",
              "|:-----------|:-------------:|:----------:|:---------:|:------------:|:---------:|:--------:|"]
    for tr in transitions:
        lines.append(
            f"| {tr['from_regime']} → {tr['to_regime']} | {tr['before_trades']} | "
            f"${tr['before_pnl']:+.0f} | {tr['before_wr']:.0%} | "
            f"{tr['after_trades']} | ${tr['after_pnl']:+.0f} | {tr['after_wr']:.0%} |"
        )

    # Drawdown analysis at transitions
    lines += [
        "",
        "**Drawdown clustering:** Transitions where the system incurs its worst per-session",
        "P&L are flagged in the table above. Check transitions into `volatile` and `slow_grind`",
        "for the highest drawdown risk.",
        "",
    ]

    # Time-of-day summary across all regimes
    lines += [
        "---",
        "",
        "## 5. Time-of-Day Summary (Conservative, All Regimes Combined)",
        "",
        "| Regime | Opening 30min | Mid-Day | Closing 60min | Other |",
        "|:-------|:-------------|:--------|:--------------|:------|",
    ]
    for regime in regimes:
        s = full_stats.get(regime, {}).get("Conservative", {})
        tod = s.get("tod", {})
        def fmt_bucket(key):
            bm = tod.get(key, {})
            return f"{bm.get('n_trades', 0)}T / ${bm.get('total_pnl', 0):+.0f}"
        lines.append(
            f"| {regime} | {fmt_bucket('opening_30min')} | {fmt_bucket('mid_day')} | "
            f"{fmt_bucket('closing_60min')} | {fmt_bucket('other')} |"
        )

    # Recommendations
    lines += [
        "",
        "---",
        "",
        "## 6. Recommendations",
        "",
        "Based on the regime analysis:  ",
        "",
    ]

    # Generate data-driven recommendations
    regime_pnls = {r: full_stats.get(r, {}).get("Conservative", {}).get("total_pnl", 0.0) for r in regimes}
    regime_wrs  = {r: full_stats.get(r, {}).get("Conservative", {}).get("win_rate", 0.0) for r in regimes}
    best_regime  = max(regime_pnls, key=regime_pnls.__getitem__)
    worst_regime = min(regime_pnls, key=regime_pnls.__getitem__)

    for regime in regimes:
        s_con = full_stats.get(regime, {}).get("Conservative", {})
        s_agg = full_stats.get(regime, {}).get("Aggressive", {})
        pnl_con = s_con.get("total_pnl", 0.0)
        pnl_agg = s_agg.get("total_pnl", 0.0)
        wr_con  = s_con.get("win_rate", 0.0)
        pf_con  = s_con.get("profit_factor", 0.0)
        n_con   = s_con.get("n_trades", 0)
        r_label = regime.replace("_", " ").title()

        if pnl_con <= 0 and n_con < 5:
            rec = f"**{r_label}: SIT OUT** — insufficient signal frequency (n={n_con}) or negative P&L. Consider disabling auto-execution in this regime."
        elif wr_con >= 0.60 and pf_con >= 1.5:
            rec = f"**{r_label}: TRADE AGGRESSIVELY** — strong win rate ({wr_con:.0%}) and profit factor ({pf_con:.2f}). Lower threshold to TYPE_B."
        elif wr_con >= 0.50 and pnl_con > 0:
            rec = f"**{r_label}: TRADE CONSERVATIVELY** — profitable but moderate edge. Keep TYPE_A threshold, do not lower."
        elif pnl_con > 0 and pnl_agg < pnl_con:
            rec = f"**{r_label}: STAY CONSERVATIVE** — aggressive config underperforms; alpha erodes with looser filters."
        else:
            rec = f"**{r_label}: REDUCE SIZE** — marginal edge. Halve contracts or raise threshold to TYPE_A + zone required."

        lines.append(f"- {rec}  ")

    lines += [
        "",
        f"**Top performing regime:** {best_regime.replace('_', ' ').title()} "
        f"(${regime_pnls[best_regime]:+.0f} conservative)  ",
        f"**Worst performing regime:** {worst_regime.replace('_', ' ').title()} "
        f"(${regime_pnls[worst_regime]:+.0f} conservative)  ",
        "",
        "**Adaptive threshold suggestion:**  ",
        "- `trend_up` / `trend_down`: lower to TYPE_B in first 30 bars (opening range trend extension)  ",
        "- `ranging`: require zone proximity (zoneScore ≥ 50) for any entry, raise to TYPE_A only  ",
        "- `volatile`: ABS/EXH + zone required; reject DELT-only entries (chase filter)  ",
        "- `slow_grind`: block all entries — signal frequency too low to cover commissions  ",
        "",
        "**Midday block** (bars 240-330, 10:30-13:00 ET) is already enforced by the scorer.  ",
        "Recommend extending to 10:00-13:30 ET in `ranging` and `slow_grind` regimes.  ",
        "",
        "---",
        "",
        "*Generated by deep6/backtest/regime_analysis.py*",
    ]

    out_path.write_text("\n".join(lines))
    print(f"Markdown report written: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run_full_analysis()
    print("\nDone.")
