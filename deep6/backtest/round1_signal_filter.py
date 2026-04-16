"""Round 1 Signal Filter Optimization for DEEP6 NQ system.

Analyzes the 50-session backtest to answer six filter questions:
  1. Drop-one signal pruning — which signal removals improve Sharpe?
  2. Minimum signal count filter (N=1..5)
  3. Signal recency — does stale signal support weaken entry quality?
  4. Category diversity — require signals from K different categories (K=1..4)
  5. Directional agreement — strict vs permissive
  6. Essential signal set — minimum set capturing 95%+ of profitable trades

Outputs:
  ninjatrader/backtests/results/round1/SIGNAL-FILTER.md
  ninjatrader/backtests/results/round1/signal_filter_stats.csv

Usage:
  python3 -m deep6.backtest.round1_signal_filter
  # or directly:
  .venv/bin/python3 deep6/backtest/round1_signal_filter.py
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Import core machinery from signal_attribution
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from deep6.backtest.signal_attribution import (
    SESSIONS_DIR,
    RESULTS_DIR,
    SCORE_ENTRY_THRESHOLD,
    MIN_TIER_INT,
    STOP_LOSS_TICKS,
    TARGET_TICKS,
    MAX_BARS_IN_TRADE,
    SLIPPAGE_TICKS,
    TICK_SIZE,
    TICK_VALUE,
    CONTRACTS,
    EXIT_ON_OPPOSING_SCORE,
    score_bar,
    extract_primary_signal,
    Trade,
)

ROUND1_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round1"
ROUND1_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def sharpe(pnl_list: list[float]) -> float:
    """Annualised Sharpe on per-trade tick P&L (assume 252 trading days, ~2 trades/day avg)."""
    if len(pnl_list) < 2:
        return 0.0
    n = len(pnl_list)
    mu = sum(pnl_list) / n
    var = sum((x - mu) ** 2 for x in pnl_list) / (n - 1)
    if var <= 0:
        return 0.0
    std = math.sqrt(var)
    # Scale to annual: sqrt(504) assumes ~504 trades/year baseline
    return (mu / std) * math.sqrt(504)


def profit_factor(pnl_list: list[float]) -> float:
    gross_win = sum(x for x in pnl_list if x > 0)
    gross_loss = abs(sum(x for x in pnl_list if x < 0))
    return gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)


def win_rate(pnl_list: list[float]) -> float:
    if not pnl_list:
        return 0.0
    return sum(1 for x in pnl_list if x > 0) / len(pnl_list)


def avg_pnl(pnl_list: list[float]) -> float:
    return sum(pnl_list) / len(pnl_list) if pnl_list else 0.0


def metrics(pnl_list: list[float]) -> dict:
    return {
        "trades": len(pnl_list),
        "win_rate": win_rate(pnl_list),
        "avg_pnl": avg_pnl(pnl_list),
        "sharpe": sharpe(pnl_list),
        "profit_factor": profit_factor(pnl_list),
        "total_pnl": sum(pnl_list),
    }


# ---------------------------------------------------------------------------
# Session loader
# ---------------------------------------------------------------------------

def load_sessions() -> list[list[dict]]:
    """Load all 50 session files. Returns list of bar lists."""
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))
    sessions = []
    for sf in session_files:
        with open(sf) as f:
            bars = [json.loads(line) for line in f if line.strip()]
        sessions.append(bars)
    return sessions


# ---------------------------------------------------------------------------
# Flexible replay engine — supports signal masking and entry filters
# ---------------------------------------------------------------------------

def replay_sessions(
    sessions: list[list[dict]],
    *,
    blocked_signals: set[str] | None = None,
    min_signal_count: int = 1,
    max_signal_age_bars: int | None = None,   # None = no recency filter
    min_categories: int = 1,
    require_directional_agreement: bool = False,
) -> list[float]:
    """Replay all sessions with optional filters; return per-trade P&L list (ticks)."""
    blocked = blocked_signals or set()
    pnl_list: list[float] = []

    for bars in sessions:
        in_trade = False
        entry_bar_idx = 0
        entry_price = 0.0
        trade_dir = 0

        # Track last bar each signal fired (for recency filter)
        signal_last_fire: dict[str, int] = {}

        for bar in bars:
            bar_idx = bar["barIdx"]
            bars_since_open = bar.get("barsSinceOpen", bar_idx)
            bar_delta = bar.get("barDelta", 0)
            bar_close = bar["barClose"]
            zone_score = bar.get("zoneScore", 0.0)
            zone_dist = bar.get("zoneDistTicks", 999.0)
            raw_signals = bar.get("signals", [])

            # Update signal recency tracker (before masking)
            for s in raw_signals:
                signal_last_fire[s["signalId"]] = bar_idx

            # Apply signal mask
            signals = [s for s in raw_signals if s["signalId"] not in blocked]

            scored = score_bar(signals, bars_since_open, bar_delta, bar_close, zone_score, zone_dist)

            if in_trade:
                exit_reason = None

                if trade_dir == +1 and bar_close <= entry_price - (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"

                if exit_reason is None:
                    if trade_dir == +1 and bar_close >= entry_price + (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"

                if exit_reason is None and scored.direction != 0 and scored.direction != trade_dir:
                    if scored.total_score >= EXIT_ON_OPPOSING_SCORE:
                        exit_reason = "OPPOSING_SIGNAL"

                if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS_IN_TRADE:
                    exit_reason = "MAX_BARS"

                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    pnl_list.append(pnl_ticks)
                    in_trade = False
            else:
                if (scored.direction != 0
                        and scored.total_score >= SCORE_ENTRY_THRESHOLD
                        and scored.tier_int >= MIN_TIER_INT):

                    # --- Apply entry filters ---

                    # 1. Minimum signal count (signals in agreed direction)
                    agreed_signals = [s for s in signals if s["direction"] == scored.direction]
                    if len(agreed_signals) < min_signal_count:
                        continue

                    # 2. Directional agreement — block mixed direction entries
                    if require_directional_agreement:
                        opposing = [s for s in signals if s["direction"] == -scored.direction]
                        if len(opposing) > 0:
                            continue

                    # 3. Category diversity
                    if len(scored.categories) < min_categories:
                        continue

                    # 4. Signal recency — require at least one agreed signal fired within age window
                    if max_signal_age_bars is not None:
                        recent_enough = any(
                            (bar_idx - signal_last_fire.get(s["signalId"], -9999)) <= max_signal_age_bars
                            for s in agreed_signals
                        )
                        if not recent_enough:
                            continue

                    entry_price = scored.entry_price + (scored.direction * SLIPPAGE_TICKS * TICK_SIZE)
                    entry_bar_idx = bar_idx
                    trade_dir = scored.direction
                    in_trade = True

        # Session-end force exit
        if in_trade and bars:
            last_bar = bars[-1]
            exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            pnl_list.append(pnl_ticks)

    return pnl_list


# ---------------------------------------------------------------------------
# Analysis 1: Baseline
# ---------------------------------------------------------------------------

def baseline_analysis(sessions: list[list[dict]]) -> dict:
    pnl = replay_sessions(sessions)
    m = metrics(pnl)
    print(f"  Baseline: {m['trades']} trades, {m['win_rate']:.1%} win, {m['avg_pnl']:.2f}t avg, Sharpe={m['sharpe']:.3f}")
    return m


# ---------------------------------------------------------------------------
# Analysis 2: Drop-one pruning
# ---------------------------------------------------------------------------

def drop_one_analysis(sessions: list[list[dict]], all_signal_ids: list[str], baseline: dict) -> list[dict]:
    """Remove each signal in turn; record delta vs baseline."""
    results = []
    baseline_sharpe = baseline["sharpe"]
    baseline_pf = baseline["profit_factor"]

    for sig in sorted(all_signal_ids):
        pnl = replay_sessions(sessions, blocked_signals={sig})
        m = metrics(pnl)
        delta_sharpe = m["sharpe"] - baseline_sharpe
        delta_pf = m["profit_factor"] - baseline_pf
        verdict = "NOISE" if delta_sharpe > 0.05 else ("ALPHA" if delta_sharpe < -0.05 else "NEUTRAL")
        results.append({
            "signal": sig,
            "trades": m["trades"],
            "win_rate": m["win_rate"],
            "avg_pnl": m["avg_pnl"],
            "sharpe": m["sharpe"],
            "profit_factor": m["profit_factor"],
            "delta_sharpe": delta_sharpe,
            "delta_pf": delta_pf,
            "verdict": verdict,
        })
        print(f"  Drop {sig:12s}: {m['trades']:3d} trades  Sharpe={m['sharpe']:.3f}  delta={delta_sharpe:+.3f}  [{verdict}]")

    return sorted(results, key=lambda x: -x["delta_sharpe"])


# ---------------------------------------------------------------------------
# Analysis 3: Minimum signal count
# ---------------------------------------------------------------------------

def min_signal_count_analysis(sessions: list[list[dict]], baseline: dict) -> list[dict]:
    results = []
    for n in range(1, 7):
        pnl = replay_sessions(sessions, min_signal_count=n)
        m = metrics(pnl)
        delta_sharpe = m["sharpe"] - baseline["sharpe"]
        results.append({
            "min_signals": n,
            "trades": m["trades"],
            "win_rate": m["win_rate"],
            "avg_pnl": m["avg_pnl"],
            "sharpe": m["sharpe"],
            "delta_sharpe": delta_sharpe,
            "profit_factor": m["profit_factor"],
        })
        print(f"  min_signals={n}: {m['trades']:3d} trades  WR={m['win_rate']:.1%}  Sharpe={m['sharpe']:.3f}  delta={delta_sharpe:+.3f}")
    return results


# ---------------------------------------------------------------------------
# Analysis 4: Signal recency
# ---------------------------------------------------------------------------

def recency_analysis(sessions: list[list[dict]], baseline: dict) -> list[dict]:
    results = []
    for age in [1, 2, 3, 5, 8, 999]:
        label = str(age) if age < 999 else "unlimited"
        pnl = replay_sessions(sessions, max_signal_age_bars=age if age < 999 else None)
        m = metrics(pnl)
        delta_sharpe = m["sharpe"] - baseline["sharpe"]
        results.append({
            "max_age_bars": age,
            "label": label,
            "trades": m["trades"],
            "win_rate": m["win_rate"],
            "avg_pnl": m["avg_pnl"],
            "sharpe": m["sharpe"],
            "delta_sharpe": delta_sharpe,
        })
        print(f"  recency<={label:10s}: {m['trades']:3d} trades  WR={m['win_rate']:.1%}  Sharpe={m['sharpe']:.3f}  delta={delta_sharpe:+.3f}")
    return results


# ---------------------------------------------------------------------------
# Analysis 5: Category diversity
# ---------------------------------------------------------------------------

def category_diversity_analysis(sessions: list[list[dict]], baseline: dict) -> list[dict]:
    results = []
    for k in range(1, 6):
        pnl = replay_sessions(sessions, min_categories=k)
        m = metrics(pnl)
        delta_sharpe = m["sharpe"] - baseline["sharpe"]
        results.append({
            "min_categories": k,
            "trades": m["trades"],
            "win_rate": m["win_rate"],
            "avg_pnl": m["avg_pnl"],
            "sharpe": m["sharpe"],
            "delta_sharpe": delta_sharpe,
        })
        print(f"  min_categories={k}: {m['trades']:3d} trades  WR={m['win_rate']:.1%}  Sharpe={m['sharpe']:.3f}  delta={delta_sharpe:+.3f}")
    return results


# ---------------------------------------------------------------------------
# Analysis 6: Directional agreement
# ---------------------------------------------------------------------------

def directional_agreement_analysis(sessions: list[list[dict]], baseline: dict) -> dict:
    pnl_mixed = replay_sessions(sessions, require_directional_agreement=False)
    pnl_strict = replay_sessions(sessions, require_directional_agreement=True)
    m_mixed = metrics(pnl_mixed)
    m_strict = metrics(pnl_strict)
    print(f"  mixed  : {m_mixed['trades']:3d} trades  WR={m_mixed['win_rate']:.1%}  Sharpe={m_mixed['sharpe']:.3f}")
    print(f"  strict : {m_strict['trades']:3d} trades  WR={m_strict['win_rate']:.1%}  Sharpe={m_strict['sharpe']:.3f}")
    return {"mixed": m_mixed, "strict": m_strict}


# ---------------------------------------------------------------------------
# Helper: replay requiring at least one essential signal on entry bar
# (does NOT block signals from scoring engine — only gates entry)
# ---------------------------------------------------------------------------

def _replay_require_essential(sessions: list[list[dict]], essential_set: set[str]) -> list[float]:
    """Replay sessions; only enter when at least one essential signal fires on entry bar."""
    pnl_list: list[float] = []

    for bars in sessions:
        in_trade = False
        entry_bar_idx = 0
        entry_price = 0.0
        trade_dir = 0

        for bar in bars:
            bar_idx = bar["barIdx"]
            bars_since_open = bar.get("barsSinceOpen", bar_idx)
            bar_delta = bar.get("barDelta", 0)
            bar_close = bar["barClose"]
            zone_score = bar.get("zoneScore", 0.0)
            zone_dist = bar.get("zoneDistTicks", 999.0)
            signals = bar.get("signals", [])

            scored = score_bar(signals, bars_since_open, bar_delta, bar_close, zone_score, zone_dist)

            if in_trade:
                exit_reason = None
                if trade_dir == +1 and bar_close <= entry_price - (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                if exit_reason is None:
                    if trade_dir == +1 and bar_close >= entry_price + (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                if exit_reason is None and scored.direction != 0 and scored.direction != trade_dir:
                    if scored.total_score >= EXIT_ON_OPPOSING_SCORE:
                        exit_reason = "OPPOSING_SIGNAL"
                if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS_IN_TRADE:
                    exit_reason = "MAX_BARS"
                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    pnl_list.append(pnl_ticks)
                    in_trade = False
            else:
                if (scored.direction != 0
                        and scored.total_score >= SCORE_ENTRY_THRESHOLD
                        and scored.tier_int >= MIN_TIER_INT):
                    # Gate: at least one essential signal present on this bar
                    bar_sig_ids = {s["signalId"] for s in signals}
                    if not bar_sig_ids.intersection(essential_set):
                        continue
                    entry_price = scored.entry_price + (scored.direction * SLIPPAGE_TICKS * TICK_SIZE)
                    entry_bar_idx = bar_idx
                    trade_dir = scored.direction
                    in_trade = True

        if in_trade and bars:
            last_bar = bars[-1]
            exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            pnl_list.append(pnl_ticks)

    return pnl_list


# ---------------------------------------------------------------------------
# Analysis 7: Essential signal set
# ---------------------------------------------------------------------------

def essential_signal_set(sessions: list[list[dict]], all_signal_ids: list[str], baseline: dict) -> dict:
    """Find minimum signal set capturing 95%+ of profitable trades.

    Approach: greedy forward selection — start empty, add one signal at a time
    picking the one that maximises coverage of the profitable baseline trades.
    """
    # First, identify which entry bars produced profitable baseline trades
    # We need to capture trade entry fingerprints (session, bar_idx)
    baseline_winning_entries: set[tuple[str, int]] = set()
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))

    # Replay baseline to collect winning trade entry fingerprints
    for sf in session_files:
        with open(sf) as f:
            bars = [json.loads(line) for line in f if line.strip()]
        in_trade = False
        entry_bar_idx = 0
        entry_price = 0.0
        trade_dir = 0
        for bar in bars:
            bar_idx = bar["barIdx"]
            bars_since_open = bar.get("barsSinceOpen", bar_idx)
            bar_delta = bar.get("barDelta", 0)
            bar_close = bar["barClose"]
            zone_score = bar.get("zoneScore", 0.0)
            zone_dist = bar.get("zoneDistTicks", 999.0)
            signals = bar.get("signals", [])
            scored = score_bar(signals, bars_since_open, bar_delta, bar_close, zone_score, zone_dist)
            if in_trade:
                exit_reason = None
                if trade_dir == +1 and bar_close <= entry_price - (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                if exit_reason is None:
                    if trade_dir == +1 and bar_close >= entry_price + (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                if exit_reason is None and scored.direction != 0 and scored.direction != trade_dir:
                    if scored.total_score >= EXIT_ON_OPPOSING_SCORE:
                        exit_reason = "OPPOSING_SIGNAL"
                if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS_IN_TRADE:
                    exit_reason = "MAX_BARS"
                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    if pnl_ticks > 0:
                        baseline_winning_entries.add((sf.stem, entry_bar_idx))
                    in_trade = False
            else:
                if (scored.direction != 0
                        and scored.total_score >= SCORE_ENTRY_THRESHOLD
                        and scored.tier_int >= MIN_TIER_INT):
                    entry_price = scored.entry_price + (scored.direction * SLIPPAGE_TICKS * TICK_SIZE)
                    entry_bar_idx = bar_idx
                    trade_dir = scored.direction
                    in_trade = True
        if in_trade and bars:
            last_bar = bars[-1]
            exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            if pnl_ticks > 0:
                baseline_winning_entries.add((sf.stem, entry_bar_idx))

    total_winners = len(baseline_winning_entries)
    target_coverage = 0.95
    target_count = int(total_winners * target_coverage)

    print(f"  Total winning trades in baseline: {total_winners}")
    print(f"  Target: capture {target_count} ({target_coverage:.0%}) winning entries")

    # Build signal → winning_entry coverage map
    sig_coverage: dict[str, set[tuple[str, int]]] = {s: set() for s in all_signal_ids}
    for sf in session_files:
        with open(sf) as f:
            bars = [json.loads(line) for line in f if line.strip()]
        for bar in bars:
            bar_idx = bar["barIdx"]
            for s in bar.get("signals", []):
                key = (sf.stem, bar_idx)
                if key in baseline_winning_entries:
                    sig_coverage[s["signalId"]].add(key)

    # Greedy forward selection
    selected: list[str] = []
    covered: set[tuple[str, int]] = set()
    remaining_signals = set(all_signal_ids)
    selection_steps = []

    while len(covered) < target_count and remaining_signals:
        best_sig = None
        best_new = 0
        for sig in sorted(remaining_signals):
            new_coverage = len(sig_coverage[sig] - covered)
            if new_coverage > best_new:
                best_new = new_coverage
                best_sig = sig
        if best_sig is None or best_new == 0:
            break
        selected.append(best_sig)
        covered |= sig_coverage[best_sig]
        remaining_signals.discard(best_sig)
        pct = len(covered) / total_winners
        selection_steps.append({
            "step": len(selected),
            "signal": best_sig,
            "new_entries": best_new,
            "cumulative_covered": len(covered),
            "coverage_pct": pct,
        })
        print(f"  Step {len(selected)}: add {best_sig:12s} → covers {len(covered)}/{total_winners} ({pct:.1%})")

    # Validate essential set performance:
    # Require at least one essential signal present on entry bar (don't block scoring engine).
    essential_set = set(selected)
    pnl_essential = _replay_require_essential(sessions, essential_set)
    m_essential = metrics(pnl_essential)
    delta_sharpe = m_essential["sharpe"] - baseline["sharpe"]

    print(f"  Essential set ({len(selected)} signals): {m_essential['trades']} trades  "
          f"WR={m_essential['win_rate']:.1%}  Sharpe={m_essential['sharpe']:.3f}  delta={delta_sharpe:+.3f}")

    return {
        "essential_signals": selected,
        "selection_steps": selection_steps,
        "coverage_pct": len(covered) / total_winners if total_winners > 0 else 0.0,
        "total_winners": total_winners,
        "covered": len(covered),
        "essential_metrics": m_essential,
        "delta_sharpe": delta_sharpe,
    }


# ---------------------------------------------------------------------------
# VOLP-03 regime gate analysis (from SIGNAL-ATTRIBUTION findings)
# ---------------------------------------------------------------------------

def volp03_gate_analysis(sessions: list[list[dict]], baseline: dict) -> dict:
    """Block entries when VOLP-03 has fired on the current or previous bar."""
    pnl_gated: list[float] = []
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))

    for sf in session_files:
        with open(sf) as f:
            bars = [json.loads(line) for line in f if line.strip()]

        in_trade = False
        entry_bar_idx = 0
        entry_price = 0.0
        trade_dir = 0
        volp03_fired_bars: set[int] = set()

        for bar in bars:
            bar_idx = bar["barIdx"]
            bars_since_open = bar.get("barsSinceOpen", bar_idx)
            bar_delta = bar.get("barDelta", 0)
            bar_close = bar["barClose"]
            zone_score = bar.get("zoneScore", 0.0)
            zone_dist = bar.get("zoneDistTicks", 999.0)
            signals = bar.get("signals", [])

            # Track VOLP-03 fires
            for s in signals:
                if s["signalId"] == "VOLP-03":
                    volp03_fired_bars.add(bar_idx)

            scored = score_bar(signals, bars_since_open, bar_delta, bar_close, zone_score, zone_dist)

            if in_trade:
                exit_reason = None
                if trade_dir == +1 and bar_close <= entry_price - (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + (STOP_LOSS_TICKS * TICK_SIZE):
                    exit_reason = "STOP_LOSS"
                if exit_reason is None:
                    if trade_dir == +1 and bar_close >= entry_price + (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - (TARGET_TICKS * TICK_SIZE):
                        exit_reason = "TARGET"
                if exit_reason is None and scored.direction != 0 and scored.direction != trade_dir:
                    if scored.total_score >= EXIT_ON_OPPOSING_SCORE:
                        exit_reason = "OPPOSING_SIGNAL"
                if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS_IN_TRADE:
                    exit_reason = "MAX_BARS"
                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    pnl_gated.append(pnl_ticks)
                    in_trade = False
            else:
                if (scored.direction != 0
                        and scored.total_score >= SCORE_ENTRY_THRESHOLD
                        and scored.tier_int >= MIN_TIER_INT):
                    # Gate: block if VOLP-03 fired on this bar or previous 2 bars
                    volp03_recent = any(
                        (bar_idx - b) <= 2 for b in volp03_fired_bars
                    )
                    if volp03_recent:
                        continue
                    entry_price = scored.entry_price + (scored.direction * SLIPPAGE_TICKS * TICK_SIZE)
                    entry_bar_idx = bar_idx
                    trade_dir = scored.direction
                    in_trade = True

        if in_trade and bars:
            last_bar = bars[-1]
            exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            pnl_gated.append(pnl_ticks)

    m = metrics(pnl_gated)
    delta_sharpe = m["sharpe"] - baseline["sharpe"]
    print(f"  VOLP-03 gate: {m['trades']:3d} trades  WR={m['win_rate']:.1%}  "
          f"Sharpe={m['sharpe']:.3f}  delta={delta_sharpe:+.3f}")
    return {"gated_metrics": m, "delta_sharpe": delta_sharpe}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_report(
    baseline: dict,
    drop_one: list[dict],
    min_count: list[dict],
    recency: list[dict],
    diversity: list[dict],
    dir_agreement: dict,
    essential: dict,
    volp03: dict,
) -> str:
    lines: list[str] = []

    lines.append("# DEEP6 Round 1: Signal Filter Optimization")
    lines.append("")
    lines.append("**Sessions:** 50 | **Bars:** 19,500 | **Analysis date:** 2026-04-15")
    lines.append("**Config:** ScoreEntryThreshold=40, MinTier=TYPE_C, Stop=8t, Target=16t")
    lines.append("")

    # Baseline
    lines.append("## Baseline (no filters)")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Trades | {baseline['trades']} |")
    lines.append(f"| Win Rate | {baseline['win_rate']:.1%} |")
    lines.append(f"| Avg P&L | {baseline['avg_pnl']:.2f}t |")
    lines.append(f"| Sharpe | {baseline['sharpe']:.3f} |")
    lines.append(f"| Profit Factor | {baseline['profit_factor']:.2f} |")
    lines.append(f"| Total P&L | {baseline['total_pnl']:.1f}t |")
    lines.append("")

    # Drop-one
    lines.append("## 1. Drop-One Signal Pruning")
    lines.append("")
    lines.append("Removing each signal in turn. Delta Sharpe = (new Sharpe) − (baseline Sharpe).")
    lines.append("**Positive delta = removing this signal IMPROVES performance (noise signal).**")
    lines.append("")
    lines.append("| Signal | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe | Delta PF | Verdict |")
    lines.append("|--------|--------|------|---------|--------|-------------|---------|---------|")
    noise_sigs = []
    alpha_sigs = []
    for r in drop_one:
        symbol = "+" if r["delta_sharpe"] > 0.05 else ("-" if r["delta_sharpe"] < -0.05 else "~")
        lines.append(
            f"| {r['signal']} | {r['trades']} | {r['win_rate']:.1%} | "
            f"{r['avg_pnl']:.2f}t | {r['sharpe']:.3f} | {r['delta_sharpe']:+.3f} | "
            f"{r['delta_pf']:+.2f} | **{r['verdict']}** {symbol} |"
        )
        if r["verdict"] == "NOISE":
            noise_sigs.append(r["signal"])
        elif r["verdict"] == "ALPHA":
            alpha_sigs.append(r["signal"])
    lines.append("")
    lines.append(f"**Noise signals (removing improves Sharpe):** {', '.join(noise_sigs) if noise_sigs else 'None'}")
    lines.append(f"**Alpha signals (removing hurts Sharpe):** {', '.join(alpha_sigs) if alpha_sigs else 'None'}")
    lines.append("")

    # Min signal count
    lines.append("## 2. Minimum Signal Count Filter")
    lines.append("")
    lines.append("Require N signals in agreed direction on the entry bar.")
    lines.append("")
    lines.append("| Min Signals | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe | Profit Factor |")
    lines.append("|-------------|--------|------|---------|--------|-------------|---------------|")
    best_min_sig = max(min_count, key=lambda x: x["sharpe"])
    for r in min_count:
        marker = " **<-- BEST**" if r["min_signals"] == best_min_sig["min_signals"] else ""
        lines.append(
            f"| {r['min_signals']} | {r['trades']} | {r['win_rate']:.1%} | "
            f"{r['avg_pnl']:.2f}t | {r['sharpe']:.3f} | {r['delta_sharpe']:+.3f} | "
            f"{r['profit_factor']:.2f} |{marker}"
        )
    lines.append("")
    lines.append(
        f"**Sweet spot:** min_signals={best_min_sig['min_signals']} → "
        f"Sharpe {best_min_sig['sharpe']:.3f} ({best_min_sig['delta_sharpe']:+.3f} vs baseline)"
    )
    lines.append("")

    # Recency
    lines.append("## 3. Signal Recency Filter")
    lines.append("")
    lines.append("Require at least one agreed-direction signal that fired within N bars of the entry bar.")
    lines.append("max_age=unlimited is the baseline (no recency filter).")
    lines.append("")
    lines.append("| Max Age (bars) | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe |")
    lines.append("|---------------|--------|------|---------|--------|-------------|")
    best_recency = max(recency, key=lambda x: x["sharpe"])
    for r in recency:
        marker = " **<-- BEST**" if r["max_age_bars"] == best_recency["max_age_bars"] else ""
        lines.append(
            f"| {r['label']} | {r['trades']} | {r['win_rate']:.1%} | "
            f"{r['avg_pnl']:.2f}t | {r['sharpe']:.3f} | {r['delta_sharpe']:+.3f} |{marker}"
        )
    lines.append("")
    # Only claim recency matters if the best finite age is strictly better than unlimited
    unlimited_recency = next((r for r in recency if r["max_age_bars"] == 999), None)
    unlimited_sharpe = unlimited_recency["sharpe"] if unlimited_recency else baseline["sharpe"]
    rec_verdict = (
        f"Signal recency matters: max_age={best_recency['label']} bars is optimal "
        f"(Sharpe {best_recency['sharpe']:.3f}, delta vs unlimited: {best_recency['sharpe'] - unlimited_sharpe:+.3f})."
        if best_recency["max_age_bars"] < 999 and best_recency["sharpe"] > unlimited_sharpe + 0.05
        else "Signal recency has no measurable impact — all signals fire on the current entry bar. Recency filter not recommended."
    )
    lines.append(f"**Finding:** {rec_verdict}")
    lines.append("")

    # Category diversity
    lines.append("## 4. Category Diversity Filter")
    lines.append("")
    lines.append("Require signals from at least K different scoring categories.")
    lines.append("")
    lines.append("| Min Categories | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe |")
    lines.append("|---------------|--------|------|---------|--------|-------------|")
    best_div = max(diversity, key=lambda x: x["sharpe"])
    for r in diversity:
        marker = " **<-- BEST**" if r["min_categories"] == best_div["min_categories"] else ""
        lines.append(
            f"| {r['min_categories']} | {r['trades']} | {r['win_rate']:.1%} | "
            f"{r['avg_pnl']:.2f}t | {r['sharpe']:.3f} | {r['delta_sharpe']:+.3f} |{marker}"
        )
    lines.append("")
    lines.append(
        f"**Sweet spot:** min_categories={best_div['min_categories']} → "
        f"Sharpe {best_div['sharpe']:.3f} ({best_div['delta_sharpe']:+.3f} vs baseline)"
    )
    lines.append("")

    # Directional agreement
    lines.append("## 5. Directional Agreement Filter")
    lines.append("")
    dm = dir_agreement["mixed"]
    ds = dir_agreement["strict"]
    winner = "strict" if ds["sharpe"] > dm["sharpe"] else "mixed"
    lines.append("| Mode | Trades | Win% | Avg P&L | Sharpe | Profit Factor |")
    lines.append("|------|--------|------|---------|--------|---------------|")
    lines.append(
        f"| Mixed (allow opposing signals) | {dm['trades']} | {dm['win_rate']:.1%} | "
        f"{dm['avg_pnl']:.2f}t | {dm['sharpe']:.3f} | {dm['profit_factor']:.2f} |"
    )
    lines.append(
        f"| Strict (all signals agree) | {ds['trades']} | {ds['win_rate']:.1%} | "
        f"{ds['avg_pnl']:.2f}t | {ds['sharpe']:.3f} | {ds['profit_factor']:.2f} |"
    )
    lines.append("")
    lines.append(f"**Winner: {winner.upper()}** — "
                 f"delta Sharpe = {ds['sharpe'] - dm['sharpe']:+.3f} in favor of strict")
    lines.append("")

    # VOLP-03 regime gate
    lines.append("## 6. VOLP-03 Regime Gate")
    lines.append("")
    lines.append("From the P0 analysis: VOLP-03 co-occurrence = 0% win, -53.7t avg P&L.")
    lines.append("Block any entry where VOLP-03 fired within the last 2 bars.")
    lines.append("")
    vg = volp03["gated_metrics"]
    lines.append("| Mode | Trades | Win% | Avg P&L | Sharpe | Total P&L |")
    lines.append("|------|--------|------|---------|--------|-----------|")
    lines.append(
        f"| No gate (baseline) | {baseline['trades']} | {baseline['win_rate']:.1%} | "
        f"{baseline['avg_pnl']:.2f}t | {baseline['sharpe']:.3f} | {baseline['total_pnl']:.1f}t |"
    )
    lines.append(
        f"| VOLP-03 gate active | {vg['trades']} | {vg['win_rate']:.1%} | "
        f"{vg['avg_pnl']:.2f}t | {vg['sharpe']:.3f} | {vg['total_pnl']:.1f}t |"
    )
    lines.append("")
    lines.append(f"**Delta Sharpe: {volp03['delta_sharpe']:+.3f}** — "
                 f"VOLP-03 gate {'RECOMMENDED' if volp03['delta_sharpe'] > 0 else 'not additive at this window'}")
    lines.append("")

    # Essential signal set
    lines.append("## 7. Essential Signal Set")
    lines.append("")
    lines.append(f"Greedy forward selection to capture {essential['coverage_pct']:.1%} "
                 f"of winning trades with minimum signals.")
    lines.append("")
    lines.append("### Selection Steps")
    lines.append("")
    lines.append("| Step | Signal Added | New Entries Captured | Cumulative | Coverage % |")
    lines.append("|------|-------------|---------------------|-----------|-----------|")
    for step in essential["selection_steps"]:
        lines.append(
            f"| {step['step']} | **{step['signal']}** | +{step['new_entries']} | "
            f"{step['cumulative_covered']}/{essential['total_winners']} | {step['coverage_pct']:.1%} |"
        )
    lines.append("")
    em = essential["essential_metrics"]
    lines.append("### Essential Set Performance")
    lines.append("")
    lines.append(f"**Essential signals ({len(essential['essential_signals'])}):** "
                 f"{', '.join(essential['essential_signals'])}")
    lines.append("")
    lines.append("| Metric | Essential Set | Baseline | Delta |")
    lines.append("|--------|--------------|----------|-------|")
    lines.append(f"| Trades | {em['trades']} | {baseline['trades']} | {em['trades'] - baseline['trades']:+d} |")
    lines.append(f"| Win Rate | {em['win_rate']:.1%} | {baseline['win_rate']:.1%} | "
                 f"{em['win_rate'] - baseline['win_rate']:+.1%} |")
    lines.append(f"| Avg P&L | {em['avg_pnl']:.2f}t | {baseline['avg_pnl']:.2f}t | "
                 f"{em['avg_pnl'] - baseline['avg_pnl']:+.2f}t |")
    lines.append(f"| Sharpe | {em['sharpe']:.3f} | {baseline['sharpe']:.3f} | "
                 f"{essential['delta_sharpe']:+.3f} |")
    lines.append(f"| Profit Factor | {em['profit_factor']:.2f} | {baseline['profit_factor']:.2f} | "
                 f"{em['profit_factor'] - baseline['profit_factor']:+.2f} |")
    lines.append(f"| Coverage | {essential['coverage_pct']:.1%} | 100% | — |")
    lines.append("")

    # Combined recommendation
    lines.append("## 8. Recommended Filter Combination")
    lines.append("")
    lines.append("Based on the analysis above, the optimal entry filter configuration:")
    lines.append("")
    lines.append("```")
    lines.append(f"1. VOLP-03 regime gate: block entry if VOLP-03 fired within last 2 bars")
    lines.append(f"2. Min signal count: {best_min_sig['min_signals']} signals in agreed direction")
    lines.append(f"3. Min categories: {best_div['min_categories']} distinct scoring categories")
    lines.append(f"4. Directional agreement: {winner} mode")
    if best_recency["max_age_bars"] < 999:
        lines.append(f"5. Signal recency: max {best_recency['label']} bars")
    lines.append(f"6. Essential signal set: {', '.join(essential['essential_signals'])}")
    lines.append("```")
    lines.append("")
    lines.append("### Expected Impact vs Baseline")
    lines.append("")
    lines.append("| Filter | Delta Sharpe | Trade Reduction | Recommendation |")
    lines.append("|--------|-------------|-----------------|---------------|")
    lines.append(f"| VOLP-03 gate | {volp03['delta_sharpe']:+.3f} | "
                 f"{baseline['trades'] - vg['trades']} | **APPLY** |")
    lines.append(f"| Min signals={best_min_sig['min_signals']} | "
                 f"{best_min_sig['delta_sharpe']:+.3f} | "
                 f"{baseline['trades'] - best_min_sig['trades']} | "
                 f"{'**APPLY**' if best_min_sig['delta_sharpe'] > 0 else 'NEUTRAL'} |")
    lines.append(f"| Min categories={best_div['min_categories']} | "
                 f"{best_div['delta_sharpe']:+.3f} | "
                 f"{baseline['trades'] - best_div['trades']} | "
                 f"{'**APPLY**' if best_div['delta_sharpe'] > 0 else 'NEUTRAL'} |")
    lines.append(f"| Directional={winner} | {ds['sharpe'] - dm['sharpe']:+.3f} | "
                 f"{dm['trades'] - ds['trades'] if winner == 'strict' else 0} | "
                 f"{'**APPLY**' if ds['sharpe'] > dm['sharpe'] else 'KEEP MIXED'} |")
    if best_recency["max_age_bars"] < 999:
        lines.append(f"| Recency<={best_recency['label']}bars | {best_recency['delta_sharpe']:+.3f} | "
                     f"{baseline['trades'] - best_recency['trades']} | "
                     f"{'**APPLY**' if best_recency['delta_sharpe'] > 0 else 'NEUTRAL'} |")
    lines.append("")
    lines.append("*Generated by `deep6/backtest/round1_signal_filter.py`*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_csv(
    drop_one: list[dict],
    min_count: list[dict],
    recency: list[dict],
    diversity: list[dict],
) -> None:
    out = ROUND1_DIR / "signal_filter_stats.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["analysis", "param", "trades", "win_rate", "avg_pnl_ticks",
                    "sharpe", "profit_factor", "delta_sharpe", "verdict"])
        for r in drop_one:
            w.writerow(["drop_one", r["signal"], r["trades"], f"{r['win_rate']:.4f}",
                        f"{r['avg_pnl']:.4f}", f"{r['sharpe']:.4f}",
                        f"{r['profit_factor']:.4f}", f"{r['delta_sharpe']:.4f}", r["verdict"]])
        for r in min_count:
            w.writerow(["min_signals", r["min_signals"], r["trades"], f"{r['win_rate']:.4f}",
                        f"{r['avg_pnl']:.4f}", f"{r['sharpe']:.4f}",
                        f"{r['profit_factor']:.4f}", f"{r['delta_sharpe']:.4f}", ""])
        for r in recency:
            w.writerow(["recency", r["label"], r["trades"], f"{r['win_rate']:.4f}",
                        f"{r['avg_pnl']:.4f}", f"{r['sharpe']:.4f}",
                        "", f"{r['delta_sharpe']:.4f}", ""])
        for r in diversity:
            w.writerow(["min_categories", r["min_categories"], r["trades"], f"{r['win_rate']:.4f}",
                        f"{r['avg_pnl']:.4f}", f"{r['sharpe']:.4f}",
                        "", f"{r['delta_sharpe']:.4f}", ""])
    print(f"CSV exported: {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("DEEP6 Round 1: Signal Filter Optimization")
    print("=" * 60)

    print("\nLoading sessions...")
    sessions = load_sessions()
    print(f"Loaded {len(sessions)} sessions")

    # Collect all signal IDs seen across sessions
    all_signal_ids: set[str] = set()
    for sf in sorted(SESSIONS_DIR.glob("*.ndjson")):
        with open(sf) as f:
            for line in f:
                if line.strip():
                    bar = json.loads(line)
                    for s in bar.get("signals", []):
                        all_signal_ids.add(s["signalId"])
    all_signal_ids_list = sorted(all_signal_ids)
    print(f"Signal universe: {all_signal_ids_list}")

    print("\n[1] Baseline...")
    baseline = baseline_analysis(sessions)

    print("\n[2] Drop-one analysis...")
    drop_one = drop_one_analysis(sessions, all_signal_ids_list, baseline)

    print("\n[3] Min signal count analysis...")
    min_count = min_signal_count_analysis(sessions, baseline)

    print("\n[4] Recency analysis...")
    recency = recency_analysis(sessions, baseline)

    print("\n[5] Category diversity analysis...")
    diversity = category_diversity_analysis(sessions, baseline)

    print("\n[6] Directional agreement analysis...")
    dir_agreement = directional_agreement_analysis(sessions, baseline)

    print("\n[7] VOLP-03 regime gate...")
    volp03 = volp03_gate_analysis(sessions, baseline)

    print("\n[8] Essential signal set...")
    essential = essential_signal_set(sessions, all_signal_ids_list, baseline)

    print("\nGenerating report...")
    report = build_report(baseline, drop_one, min_count, recency, diversity,
                          dir_agreement, essential, volp03)

    report_path = ROUND1_DIR / "SIGNAL-FILTER.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report written: {report_path}")

    export_csv(drop_one, min_count, recency, diversity)

    # Print summary to stdout
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    noise = [r["signal"] for r in drop_one if r["verdict"] == "NOISE"]
    alpha = [r["signal"] for r in drop_one if r["verdict"] == "ALPHA"]
    best_mc = max(min_count, key=lambda x: x["sharpe"])
    best_div = max(diversity, key=lambda x: x["sharpe"])
    print(f"Noise signals (drop improves): {', '.join(noise) if noise else 'none'}")
    print(f"Alpha signals (drop hurts):    {', '.join(alpha) if alpha else 'none'}")
    print(f"Best min_signals: {best_mc['min_signals']} (Sharpe {best_mc['sharpe']:.3f})")
    print(f"Best min_categories: {best_div['min_categories']} (Sharpe {best_div['sharpe']:.3f})")
    print(f"VOLP-03 gate delta: {volp03['delta_sharpe']:+.3f}")
    print(f"Essential set: {', '.join(essential['essential_signals'])}")
    print(f"Essential coverage: {essential['coverage_pct']:.1%} of winning trades")
    print(f"\nOutputs:")
    print(f"  {ROUND1_DIR}/SIGNAL-FILTER.md")
    print(f"  {ROUND1_DIR}/signal_filter_stats.csv")


if __name__ == "__main__":
    main()
