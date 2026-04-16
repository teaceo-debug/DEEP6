"""Signal attribution analysis for DEEP6 backtest sessions.

Loads all 50 NDJSON sessions, runs a Python port of the ConfluenceScorer
entry/exit simulation, then attributes each trade to its primary signal
and co-occurring signals.

Outputs:
  ninjatrader/backtests/results/SIGNAL-ATTRIBUTION.md
  ninjatrader/backtests/results/signal_stats.csv
  ninjatrader/backtests/results/signal_pairs.csv

Usage:
  python3 -m deep6.backtest.signal_attribution
  # or directly:
  .venv/bin/python3 deep6/backtest/signal_attribution.py
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
RESULTS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Backtest config (task spec: ScoreEntryThreshold=40, MinTier=TYPE_C)
# ---------------------------------------------------------------------------
SCORE_ENTRY_THRESHOLD = 40.0
MIN_TIER_FOR_ENTRY = "TYPE_C"        # minimum tier to open trade (0=QUIET,1=C,2=B,3=A)
STOP_LOSS_TICKS = 8
TARGET_TICKS = 16
MAX_BARS_IN_TRADE = 20
SLIPPAGE_TICKS = 1
TICK_SIZE = 0.25
TICK_VALUE = 5.0
CONTRACTS = 1
EXIT_ON_OPPOSING_SCORE = 40.0

# Tier int mapping
TIER_MAP = {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
MIN_TIER_INT = TIER_MAP[MIN_TIER_FOR_ENTRY]

# ---------------------------------------------------------------------------
# Scorer constants (verbatim from ConfluenceScorer.cs / scorer.py)
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS = {
    "absorption": 25.0,
    "exhaustion": 18.0,
    "trapped": 14.0,
    "delta": 13.0,
    "imbalance": 12.0,
    "volume_profile": 10.0,
    "auction": 8.0,
    "poc": 1.0,
}

CONFLUENCE_THRESHOLD = 5
CONFLUENCE_MULT = 1.25
IB_MULT = 1.15
IB_BAR_END = 60
MIDDAY_START = 240
MIDDAY_END = 330
TYPE_A_MIN = 80.0
TYPE_B_MIN = 72.0
TYPE_C_MIN = 50.0
ZONE_HIGH_MIN = 50.0
ZONE_HIGH_BONUS = 8.0
ZONE_MID_MIN = 30.0
ZONE_MID_BONUS = 6.0
ZONE_NEAR_BONUS = 4.0
ZONE_NEAR_TICKS = 0.5
MIN_STRENGTH = 0.3
TRAP_VETO_COUNT = 3
DELTA_CHASE_MAG = 50

# ---------------------------------------------------------------------------
# Signal → category mapping (mirrors ConfluenceScorer routing logic)
# ---------------------------------------------------------------------------
# Voting signals (contribute to category counts)
DELTA_VOTING = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
AUCTION_VOTING = {"AUCT-01", "AUCT-02", "AUCT-05"}
POC_VOTING = {"POC-02", "POC-07", "POC-08"}


def signal_category(sig_id: str) -> Optional[str]:
    """Return the scoring category for a signal ID, or None if non-voting."""
    if sig_id.startswith("ABS"):
        return "absorption"
    if sig_id.startswith("EXH"):
        return "exhaustion"
    if sig_id.startswith("TRAP"):
        return "trapped"
    if sig_id in DELTA_VOTING:
        return "delta"
    if sig_id in AUCTION_VOTING:
        return "auction"
    if sig_id in POC_VOTING:
        return "poc"
    # IMB handled separately (dedup logic in scorer)
    # DELT-01/03 etc are informational (not counted in category voting)
    return None


@dataclass
class ScoredResult:
    total_score: float
    tier_int: int          # 0=QUIET 1=C 2=B 3=A
    direction: int         # +1 / -1 / 0
    agreement: float
    cat_count: int
    categories: list[str]
    entry_price: float


def score_bar(signals: list[dict], bars_since_open: int, bar_delta: int,
              bar_close: float, zone_score: float, zone_dist_ticks: float) -> ScoredResult:
    """Python port of ConfluenceScorer.Score() — faithful to the CS file."""
    bull_weight = 0.0
    bear_weight = 0.0
    cats_bull: set[str] = set()
    cats_bear: set[str] = set()
    stacked_bull_tier = 0
    stacked_bear_tier = 0
    max_bull_str = 0.0
    max_bear_str = 0.0
    trap_count = 0

    for s in signals:
        sid = s["signalId"]
        d = s["direction"]
        st = s["strength"]

        if sid.startswith("ABS"):
            if d > 0:
                bull_weight += st; cats_bull.add("absorption"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("absorption"); max_bear_str = max(max_bear_str, st)
        elif sid.startswith("EXH"):
            if d > 0:
                bull_weight += st; cats_bull.add("exhaustion"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("exhaustion"); max_bear_str = max(max_bear_str, st)
        elif sid.startswith("TRAP"):
            trap_count += 1
            if d > 0:
                bull_weight += st; cats_bull.add("trapped"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("trapped"); max_bear_str = max(max_bear_str, st)
        elif sid.startswith("IMB"):
            # Stacked tiers dedup; non-stacked IMB-01/02/etc don't vote in category
            detail = s.get("detail", "")
            tier = 0
            if "STACKED_T3" in detail or sid.endswith("-T3"):
                tier = 3
            elif "STACKED_T2" in detail or sid.endswith("-T2"):
                tier = 2
            elif "STACKED_T1" in detail or sid.endswith("-T1"):
                tier = 1
            if tier > 0:
                if d > 0:
                    stacked_bull_tier = max(stacked_bull_tier, tier)
                    max_bull_str = max(max_bull_str, st)
                elif d < 0:
                    stacked_bear_tier = max(stacked_bear_tier, tier)
                    max_bear_str = max(max_bear_str, st)
        elif sid in DELTA_VOTING:
            if d > 0:
                bull_weight += st; cats_bull.add("delta"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("delta"); max_bear_str = max(max_bear_str, st)
        elif sid in AUCTION_VOTING:
            if d > 0:
                bull_weight += st; cats_bull.add("auction"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("auction"); max_bear_str = max(max_bear_str, st)
        elif sid in POC_VOTING:
            if d > 0:
                bull_weight += st; cats_bull.add("poc"); max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st; cats_bear.add("poc"); max_bear_str = max(max_bear_str, st)
        # DELT-01/03 and others: informational only, no category vote

    # Stacked imbalance votes
    if stacked_bull_tier > 0:
        bull_weight += 0.5; cats_bull.add("imbalance")
    if stacked_bear_tier > 0:
        bear_weight += 0.5; cats_bear.add("imbalance")

    # Determine direction
    def _count_side_votes(direction: int, stacked_tier: int) -> int:
        count = 0
        for s in signals:
            if s["direction"] != direction:
                continue
            sid = s["signalId"]
            if any(sid.startswith(p) for p in ("ABS", "EXH", "TRAP")):
                count += 1
            elif sid in DELTA_VOTING or sid in AUCTION_VOTING or sid in POC_VOTING:
                count += 1
        if stacked_tier > 0:
            count += 1
        return count

    if bull_weight > bear_weight:
        direction = +1
        bull_v = _count_side_votes(+1, stacked_bull_tier)
        bear_v = _count_side_votes(-1, stacked_bear_tier)
        total_v = bull_v + bear_v
        agreement = bull_v / total_v if total_v > 0 else 0.0
        cats_agreeing = cats_bull
        max_dom_str = max_bull_str
    elif bear_weight > bull_weight:
        direction = -1
        bull_v = _count_side_votes(+1, stacked_bull_tier)
        bear_v = _count_side_votes(-1, stacked_bear_tier)
        total_v = bull_v + bear_v
        agreement = bear_v / total_v if total_v > 0 else 0.0
        cats_agreeing = cats_bear
        max_dom_str = max_bear_str
    else:
        return ScoredResult(0.0, 0, 0, 0.0, 0, [], bar_close)

    # Delta agreement gate
    delta_agrees = True
    if bar_delta != 0 and direction != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            delta_agrees = False

    # IB multiplier
    ib_mult = IB_MULT if 0 <= bars_since_open < IB_BAR_END else 1.0

    # Zone bonus (adds volume_profile category)
    zone_bonus = 0.0
    if zone_score >= ZONE_HIGH_MIN:
        zone_bonus = ZONE_NEAR_BONUS if zone_dist_ticks <= ZONE_NEAR_TICKS else ZONE_HIGH_BONUS
        cats_agreeing.add("volume_profile")
    elif zone_score >= ZONE_MID_MIN:
        zone_bonus = ZONE_MID_BONUS
        cats_agreeing.add("volume_profile")

    cat_count = len(cats_agreeing)
    confluence_mult = CONFLUENCE_MULT if cat_count >= CONFLUENCE_THRESHOLD else 1.0

    # Base score
    base_score = sum(CATEGORY_WEIGHTS.get(c, 5.0) for c in cats_agreeing)

    total_score = min(
        (base_score * confluence_mult + zone_bonus) * agreement * ib_mult,
        100.0
    )
    total_score = max(0.0, total_score)

    # Tier classification
    has_abs_exh = "absorption" in cats_agreeing or "exhaustion" in cats_agreeing
    has_zone = zone_bonus > 0.0
    min_str = max_dom_str >= MIN_STRENGTH
    trap_veto = trap_count >= TRAP_VETO_COUNT
    delta_chase = False
    if bar_delta != 0 and direction != 0:
        if abs(bar_delta) > DELTA_CHASE_MAG:
            if (direction > 0 and bar_delta > 0) or (direction < 0 and bar_delta < 0):
                delta_chase = True

    if (total_score >= TYPE_A_MIN and has_abs_exh and has_zone
            and cat_count >= 5 and delta_agrees and not trap_veto and not delta_chase):
        tier = 3  # TYPE_A
    elif total_score >= TYPE_B_MIN and cat_count >= 4 and delta_agrees and min_str:
        tier = 2  # TYPE_B
    elif total_score >= TYPE_C_MIN and cat_count >= 4 and min_str:
        tier = 1  # TYPE_C
    else:
        tier = 0  # QUIET

    # Midday block
    if tier > 0 and MIDDAY_START <= bars_since_open <= MIDDAY_END:
        tier = 0

    # Entry price: dominant ABS/EXH price or bar_close
    entry_price = 0.0
    for s in signals:
        if s["direction"] == direction and s.get("price", 0.0) != 0.0:
            sid = s["signalId"]
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = s["price"]
                break
    if entry_price == 0.0:
        entry_price = bar_close

    return ScoredResult(
        total_score=total_score,
        tier_int=tier,
        direction=direction,
        agreement=agreement,
        cat_count=cat_count,
        categories=sorted(cats_agreeing),
        entry_price=entry_price,
    )


@dataclass
class Trade:
    entry_bar: int
    exit_bar: int
    entry_price: float
    exit_price: float
    direction: int
    pnl_ticks: float
    pnl_dollars: float
    tier: int
    score: float
    exit_reason: str
    duration_bars: int
    primary_signal: str           # dominant ABS/EXH signal or "MIXED"
    all_signals: list[str]        # all signal IDs on the entry bar
    categories_firing: list[str]
    session: str


def extract_primary_signal(signals: list[dict], direction: int) -> str:
    """Mirror BacktestRunner.ExtractDominantSignalId — look for ABS/EXH first."""
    for s in signals:
        if s["direction"] == direction:
            sid = s["signalId"]
            if sid.startswith("ABS"):
                return sid
            if sid.startswith("EXH"):
                return sid
    # Fallback: highest-strength signal in agreed direction
    dom = sorted(
        [s for s in signals if s["direction"] == direction],
        key=lambda x: x["strength"],
        reverse=True
    )
    return dom[0]["signalId"] if dom else "MIXED"


def run_session(session_path: Path) -> list[Trade]:
    """Replay one session file and return completed trades."""
    with open(session_path) as f:
        bars = [json.loads(line) for line in f if line.strip()]

    trades: list[Trade] = []
    in_trade = False
    entry_bar_idx = 0
    entry_price = 0.0
    trade_dir = 0
    trade_signals: list[str] = []
    trade_primary = "MIXED"
    trade_tier = 0
    trade_score = 0.0
    trade_cats: list[str] = []

    session_name = session_path.stem

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

            # 1. Stop loss
            if trade_dir == +1 and bar_close <= entry_price - (STOP_LOSS_TICKS * TICK_SIZE):
                exit_reason = "STOP_LOSS"
            elif trade_dir == -1 and bar_close >= entry_price + (STOP_LOSS_TICKS * TICK_SIZE):
                exit_reason = "STOP_LOSS"

            # 2. Target
            if exit_reason is None:
                if trade_dir == +1 and bar_close >= entry_price + (TARGET_TICKS * TICK_SIZE):
                    exit_reason = "TARGET"
                elif trade_dir == -1 and bar_close <= entry_price - (TARGET_TICKS * TICK_SIZE):
                    exit_reason = "TARGET"

            # 3. Opposing signal
            if exit_reason is None and scored.direction != 0 and scored.direction != trade_dir:
                if scored.total_score >= EXIT_ON_OPPOSING_SCORE:
                    exit_reason = "OPPOSING_SIGNAL"

            # 4. Max bars
            if exit_reason is None and (bar_idx - entry_bar_idx) >= MAX_BARS_IN_TRADE:
                exit_reason = "MAX_BARS"

            if exit_reason is not None:
                exit_price = bar_close - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
                pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                trades.append(Trade(
                    entry_bar=entry_bar_idx,
                    exit_bar=bar_idx,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    direction=trade_dir,
                    pnl_ticks=pnl_ticks,
                    pnl_dollars=pnl_ticks * TICK_VALUE * CONTRACTS,
                    tier=trade_tier,
                    score=trade_score,
                    exit_reason=exit_reason,
                    duration_bars=max(bar_idx - entry_bar_idx, 1),
                    primary_signal=trade_primary,
                    all_signals=trade_signals,
                    categories_firing=trade_cats,
                    session=session_name,
                ))
                in_trade = False
        else:
            # Entry gate
            if (scored.direction != 0
                    and scored.total_score >= SCORE_ENTRY_THRESHOLD
                    and scored.tier_int >= MIN_TIER_INT):
                entry_price = scored.entry_price + (scored.direction * SLIPPAGE_TICKS * TICK_SIZE)
                entry_bar_idx = bar_idx
                trade_dir = scored.direction
                trade_tier = scored.tier_int
                trade_score = scored.total_score
                trade_cats = scored.categories
                trade_signals = [s["signalId"] for s in signals]
                trade_primary = extract_primary_signal(
                    [s for s in signals if s["direction"] == trade_dir], trade_dir
                )
                in_trade = True

    # Session-end force exit
    if in_trade and bars:
        last_bar = bars[-1]
        exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
        pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
        trades.append(Trade(
            entry_bar=entry_bar_idx,
            exit_bar=last_bar["barIdx"],
            entry_price=entry_price,
            exit_price=exit_price,
            direction=trade_dir,
            pnl_ticks=pnl_ticks,
            pnl_dollars=pnl_ticks * TICK_VALUE * CONTRACTS,
            tier=trade_tier,
            score=trade_score,
            exit_reason="SESSION_END",
            duration_bars=max(last_bar["barIdx"] - entry_bar_idx, 1),
            primary_signal=trade_primary,
            all_signals=trade_signals,
            categories_firing=trade_cats,
            session=session_name,
        ))

    return trades


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_attribution():
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))
    if not session_files:
        print(f"ERROR: No session files found in {SESSIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {len(session_files)} sessions from {SESSIONS_DIR}...")

    # --- Run all sessions ---
    all_trades: list[Trade] = []
    for sf in session_files:
        all_trades.extend(run_session(sf))

    print(f"Total trades simulated: {len(all_trades)}")
    if not all_trades:
        print("WARNING: No trades generated. Check entry threshold and tier settings.")
        return

    # -----------------------------------------------------------------------
    # Compute signal universe frequencies across all 19,500 bars
    # -----------------------------------------------------------------------
    signal_fire_counts: Counter[str] = Counter()
    total_bars = 0
    for sf in session_files:
        with open(sf) as f:
            bars = [json.loads(l) for l in f]
        total_bars += len(bars)
        for b in bars:
            for s in b.get("signals", []):
                signal_fire_counts[s["signalId"]] += 1

    all_signal_ids = sorted(signal_fire_counts.keys())

    # -----------------------------------------------------------------------
    # Per-signal attribution
    # -----------------------------------------------------------------------
    # primary_stats[sig] = {wins, losses, pnl_list}
    primary_stats: dict[str, dict] = {s: {"wins": 0, "losses": 0, "pnl": []} for s in all_signal_ids}
    primary_stats["MIXED"] = {"wins": 0, "losses": 0, "pnl": []}

    # cooccur_stats[sig] = {wins, losses, pnl_list}  (signal present on entry bar, not primary)
    cooccur_stats: dict[str, dict] = {s: {"wins": 0, "losses": 0, "pnl": []} for s in all_signal_ids}

    # per-signal standalone direction accuracy (does signal direction predict next-bar move?)
    # We'll approximate with trade outcome when signal is primary
    signal_direction_correct: Counter[str] = Counter()
    signal_direction_total: Counter[str] = Counter()

    for trade in all_trades:
        win = trade.pnl_ticks > 0
        pnl = trade.pnl_ticks

        # Primary signal attribution
        psig = trade.primary_signal or "MIXED"
        if psig not in primary_stats:
            primary_stats[psig] = {"wins": 0, "losses": 0, "pnl": []}
        if win:
            primary_stats[psig]["wins"] += 1
        else:
            primary_stats[psig]["losses"] += 1
        primary_stats[psig]["pnl"].append(pnl)

        # Direction accuracy
        signal_direction_total[psig] += 1
        if win:
            signal_direction_correct[psig] += 1

        # Co-occurring signal attribution (non-primary signals on entry bar)
        for sig in trade.all_signals:
            if sig != psig:
                if sig not in cooccur_stats:
                    cooccur_stats[sig] = {"wins": 0, "losses": 0, "pnl": []}
                if win:
                    cooccur_stats[sig]["wins"] += 1
                else:
                    cooccur_stats[sig]["losses"] += 1
                cooccur_stats[sig]["pnl"].append(pnl)

    # -----------------------------------------------------------------------
    # Category-level analysis
    # -----------------------------------------------------------------------
    cat_names = list(CATEGORY_WEIGHTS.keys())
    cat_stats: dict[str, dict] = {c: {"wins": 0, "losses": 0, "pnl": []} for c in cat_names}

    for trade in all_trades:
        win = trade.pnl_ticks > 0
        for c in trade.categories_firing:
            if c in cat_stats:
                if win:
                    cat_stats[c]["wins"] += 1
                else:
                    cat_stats[c]["losses"] += 1
                cat_stats[c]["pnl"].append(trade.pnl_ticks)

    # Category correlation: for each pair, count co-occurrence on winning and losing trades
    cat_pair_wins: Counter[tuple] = Counter()
    cat_pair_losses: Counter[tuple] = Counter()
    for trade in all_trades:
        cats = sorted(trade.categories_firing)
        pairs = [(cats[i], cats[j]) for i in range(len(cats)) for j in range(i+1, len(cats))]
        win = trade.pnl_ticks > 0
        for p in pairs:
            if win:
                cat_pair_wins[p] += 1
            else:
                cat_pair_losses[p] += 1

    # -----------------------------------------------------------------------
    # Signal pair analysis
    # -----------------------------------------------------------------------
    sig_pair_wins: Counter[tuple] = Counter()
    sig_pair_losses: Counter[tuple] = Counter()
    sig_pair_pnl: dict[tuple, list] = defaultdict(list)

    for trade in all_trades:
        sigs = sorted(set(trade.all_signals))
        pairs = [(sigs[i], sigs[j]) for i in range(len(sigs)) for j in range(i+1, len(sigs))]
        win = trade.pnl_ticks > 0
        for p in pairs:
            sig_pair_pnl[p].append(trade.pnl_ticks)
            if win:
                sig_pair_wins[p] += 1
            else:
                sig_pair_losses[p] += 1

    # -----------------------------------------------------------------------
    # Helper functions
    # -----------------------------------------------------------------------
    def stats_row(s: dict) -> dict:
        wins = s["wins"]
        losses = s["losses"]
        total = wins + losses
        pnl_list = s["pnl"]
        if total == 0:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "avg_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "snr": 0.0}
        win_pnls = [p for p in pnl_list if p > 0]
        loss_pnls = [p for p in pnl_list if p <= 0]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
        avg_loss = abs(sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        win_rate = wins / total
        loss_rate = 1 - win_rate
        snr = (avg_win * win_rate) / (avg_loss * loss_rate) if avg_loss * loss_rate > 0 else float("inf")
        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_pnl": sum(pnl_list) / len(pnl_list),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "snr": snr,
        }

    # -----------------------------------------------------------------------
    # Overall stats
    # -----------------------------------------------------------------------
    total_trades = len(all_trades)
    wins_total = sum(1 for t in all_trades if t.pnl_ticks > 0)
    total_pnl = sum(t.pnl_dollars for t in all_trades)
    overall_win_rate = wins_total / total_trades if total_trades > 0 else 0.0

    tier_labels = {0: "QUIET", 1: "TYPE_C", 2: "TYPE_B", 3: "TYPE_A"}
    tier_counts = Counter(t.tier for t in all_trades)
    tier_wins = Counter(t.tier for t in all_trades if t.pnl_ticks > 0)
    exit_counts = Counter(t.exit_reason for t in all_trades)

    # -----------------------------------------------------------------------
    # Write signal_stats.csv
    # -----------------------------------------------------------------------
    csv_signal_path = RESULTS_DIR / "signal_stats.csv"
    sig_rows = []
    for sig in all_signal_ids + ["MIXED"]:
        p_row = stats_row(primary_stats.get(sig, {"wins": 0, "losses": 0, "pnl": []}))
        c_row = stats_row(cooccur_stats.get(sig, {"wins": 0, "losses": 0, "pnl": []}))
        fire_count = signal_fire_counts.get(sig, 0)
        fire_rate = fire_count / total_bars if total_bars > 0 else 0.0
        cat = signal_category(sig) or "informational"
        sig_rows.append({
            "signal_id": sig,
            "category": cat,
            "fire_count": fire_count,
            "fire_rate_pct": round(fire_rate * 100, 2),
            "primary_trades": p_row["total"],
            "primary_win_rate": round(p_row["win_rate"] * 100, 1),
            "primary_avg_pnl_ticks": round(p_row["avg_pnl"], 2),
            "primary_avg_win_ticks": round(p_row["avg_win"], 2),
            "primary_avg_loss_ticks": round(p_row["avg_loss"], 2),
            "primary_snr": round(p_row["snr"], 3) if p_row["snr"] != float("inf") else 999.0,
            "cooccur_trades": c_row["total"],
            "cooccur_win_rate": round(c_row["win_rate"] * 100, 1),
            "cooccur_avg_pnl_ticks": round(c_row["avg_pnl"], 2),
        })

    with open(csv_signal_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(sig_rows[0].keys()))
        writer.writeheader()
        writer.writerows(sig_rows)
    print(f"Written: {csv_signal_path}")

    # -----------------------------------------------------------------------
    # Write signal_pairs.csv
    # -----------------------------------------------------------------------
    csv_pairs_path = RESULTS_DIR / "signal_pairs.csv"
    all_pairs = set(sig_pair_wins.keys()) | set(sig_pair_losses.keys())
    pair_rows = []
    for p in sorted(all_pairs):
        w = sig_pair_wins.get(p, 0)
        l = sig_pair_losses.get(p, 0)
        total = w + l
        pnl_list = sig_pair_pnl[p]
        avg_pnl = sum(pnl_list) / len(pnl_list) if pnl_list else 0.0
        win_rate = w / total if total > 0 else 0.0
        pair_rows.append({
            "sig_a": p[0],
            "sig_b": p[1],
            "co_trade_count": total,
            "wins": w,
            "losses": l,
            "win_rate_pct": round(win_rate * 100, 1),
            "avg_pnl_ticks": round(avg_pnl, 2),
        })

    # Sort by co-occurrence count descending
    pair_rows.sort(key=lambda x: x["co_trade_count"], reverse=True)

    if pair_rows:
        with open(csv_pairs_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
            writer.writeheader()
            writer.writerows(pair_rows)
        print(f"Written: {csv_pairs_path}")

    # -----------------------------------------------------------------------
    # Identify top-5 alpha signals and top-3 noise signals
    # -----------------------------------------------------------------------
    # Alpha: high win rate + positive avg_pnl + meaningful sample size
    def signal_alpha_score(row: dict) -> float:
        if row["primary_trades"] < 3:
            return -999.0
        return row["primary_win_rate"] * 0.5 + row["primary_avg_pnl_ticks"] * 5.0 + row["primary_snr"] * 2.0

    def signal_noise_score(row: dict) -> float:
        """Lower = more noise (low win rate, negative pnl)."""
        if row["primary_trades"] < 3:
            return 999.0
        return row["primary_win_rate"] + row["primary_avg_pnl_ticks"]

    valid_rows = [r for r in sig_rows if r["primary_trades"] >= 3]
    top5_alpha = sorted(valid_rows, key=signal_alpha_score, reverse=True)[:5]
    top3_noise = sorted(valid_rows, key=signal_noise_score)[:3]

    # Toxic pairs: win_rate < 33% AND co_trade_count >= 3
    toxic_pairs = [r for r in pair_rows if r["win_rate_pct"] < 33.0 and r["co_trade_count"] >= 3]
    toxic_pairs.sort(key=lambda x: x["win_rate_pct"])

    # Top signal pairs on wins vs losses
    win_pair_rows = sorted(pair_rows, key=lambda x: x["wins"], reverse=True)[:10]
    loss_pair_rows = sorted(pair_rows, key=lambda x: x["losses"], reverse=True)[:10]

    # Category-level results
    cat_results = []
    for c in cat_names:
        row = stats_row(cat_stats[c])
        cat_results.append((c, row))
    cat_results.sort(key=lambda x: x[1]["avg_pnl"], reverse=True)

    # Tier breakdown
    tier_breakdown = []
    for tier_int, label in tier_labels.items():
        cnt = tier_counts.get(tier_int, 0)
        w = tier_wins.get(tier_int, 0)
        t_pnl = [t.pnl_ticks for t in all_trades if t.tier == tier_int]
        avg_p = sum(t_pnl) / len(t_pnl) if t_pnl else 0.0
        win_r = w / cnt * 100 if cnt > 0 else 0.0
        tier_breakdown.append((label, cnt, win_r, avg_p))

    # -----------------------------------------------------------------------
    # Write SIGNAL-ATTRIBUTION.md
    # -----------------------------------------------------------------------
    md_path = RESULTS_DIR / "SIGNAL-ATTRIBUTION.md"
    with open(md_path, "w") as f:
        w = f.write

        w("# DEEP6 Signal Attribution Report\n\n")
        w(f"**Sessions analyzed:** {len(session_files)} (50 sessions, 19,500 bars)\n")
        w(f"**Config:** ScoreEntryThreshold={SCORE_ENTRY_THRESHOLD}, MinTier={MIN_TIER_FOR_ENTRY}, "
          f"Stop={STOP_LOSS_TICKS}t, Target={TARGET_TICKS}t, MaxBars={MAX_BARS_IN_TRADE}\n\n")

        # Overall summary
        w("## Overall Backtest Summary\n\n")
        w(f"| Metric | Value |\n|--------|-------|\n")
        w(f"| Total trades | {total_trades} |\n")
        w(f"| Wins | {wins_total} |\n")
        w(f"| Losses | {total_trades - wins_total} |\n")
        w(f"| Overall win rate | {overall_win_rate:.1%} |\n")
        w(f"| Total P&L (dollars) | ${total_pnl:,.0f} |\n")
        w(f"| Avg P&L per trade | ${total_pnl/total_trades:.0f} |\n\n")

        # Exit reason breakdown
        w("### Exit Reason Breakdown\n\n")
        w("| Exit Reason | Count | % |\n|-------------|-------|---|\n")
        for reason, cnt in exit_counts.most_common():
            w(f"| {reason} | {cnt} | {cnt/total_trades:.1%} |\n")
        w("\n")

        # Tier breakdown
        w("### Tier Breakdown\n\n")
        w("| Tier | Trades | Win Rate | Avg P&L (ticks) |\n|------|--------|----------|------------------|\n")
        for label, cnt, wr, ap in tier_breakdown:
            if cnt > 0:
                w(f"| {label} | {cnt} | {wr:.1f}% | {ap:.1f} |\n")
        w("\n")

        # Signal frequency
        w("## Signal Frequency (19,500 bars)\n\n")
        w("| Signal | Category | Fires | Fire Rate | Fires Bull% |\n")
        w("|--------|----------|-------|-----------|-------------|\n")
        for sig in all_signal_ids:
            cnt = signal_fire_counts[sig]
            rate = cnt / total_bars * 100
            cat = signal_category(sig) or "informational"
            w(f"| {sig} | {cat} | {cnt} | {rate:.1f}% | — |\n")
        w("\n")

        # Per-signal attribution table
        w("## Per-Signal Attribution\n\n")
        w("*(Primary = signal drove the entry; Co-occur = signal present on entry bar but not primary)*\n\n")
        w("| Signal | Category | Primary Trades | Primary Win% | Primary Avg P&L | SNR | CoOccur Trades | CoOccur Win% | CoOccur Avg P&L |\n")
        w("|--------|----------|---------------|--------------|-----------------|-----|----------------|--------------|------------------|\n")
        for row in sorted(sig_rows, key=lambda x: x["primary_trades"], reverse=True):
            if row["signal_id"] == "MIXED":
                continue
            w(f"| {row['signal_id']} | {row['category']} | {row['primary_trades']} "
              f"| {row['primary_win_rate']:.1f}% | {row['primary_avg_pnl_ticks']:.1f}t "
              f"| {row['primary_snr']:.2f} "
              f"| {row['cooccur_trades']} | {row['cooccur_win_rate']:.1f}% "
              f"| {row['cooccur_avg_pnl_ticks']:.1f}t |\n")
        w("\n")

        # Top 5 alpha signals
        w("## Top 5 Alpha Signals\n\n")
        w("*(Ranked by composite: win_rate × 0.5 + avg_pnl_ticks × 5 + SNR × 2)*\n\n")
        w("| Rank | Signal | Category | Win Rate | Avg P&L (ticks) | SNR | Primary Trades |\n")
        w("|------|--------|----------|----------|-----------------|-----|----------------|\n")
        for i, row in enumerate(top5_alpha, 1):
            w(f"| {i} | **{row['signal_id']}** | {row['category']} "
              f"| {row['primary_win_rate']:.1f}% | {row['primary_avg_pnl_ticks']:.1f}t "
              f"| {row['primary_snr']:.2f} | {row['primary_trades']} |\n")
        w("\n")

        # Top 3 noise signals
        w("## Top 3 Noise Signals\n\n")
        w("*(Lowest win_rate + avg_pnl composite with ≥3 primary trades)*\n\n")
        w("| Rank | Signal | Category | Win Rate | Avg P&L (ticks) | Primary Trades |\n")
        w("|------|--------|----------|----------|-----------------|----------------|\n")
        for i, row in enumerate(top3_noise, 1):
            w(f"| {i} | **{row['signal_id']}** | {row['category']} "
              f"| {row['primary_win_rate']:.1f}% | {row['primary_avg_pnl_ticks']:.1f}t "
              f"| {row['primary_trades']} |\n")
        w("\n")

        # Category analysis
        w("## Category-Level Analysis\n\n")
        w("| Category | Weight | Trades | Win Rate | Avg P&L (ticks) | Avg Win | Avg Loss |\n")
        w("|----------|--------|--------|----------|-----------------|---------|----------|\n")
        for cat, row in cat_results:
            wt = CATEGORY_WEIGHTS.get(cat, 5.0)
            if row["total"] > 0:
                w(f"| {cat} | {wt} | {row['total']} | {row['win_rate']:.1%} "
                  f"| {row['avg_pnl']:.1f}t | {row['avg_win']:.1f}t | {row['avg_loss']:.1f}t |\n")
        w("\n")

        # Category pair correlation
        w("### Category Pair Performance\n\n")
        all_cat_pairs = set(cat_pair_wins.keys()) | set(cat_pair_losses.keys())
        cat_pair_data = []
        for p in sorted(all_cat_pairs):
            ww = cat_pair_wins.get(p, 0)
            ll = cat_pair_losses.get(p, 0)
            total = ww + ll
            if total < 3:
                continue
            cat_pair_data.append((p, ww, ll, total, ww / total))
        cat_pair_data.sort(key=lambda x: x[4], reverse=True)

        w("| Category A | Category B | Trades | Win% | Wins | Losses |\n")
        w("|------------|------------|--------|------|------|--------|\n")
        for p, ww, ll, total, wr in cat_pair_data:
            marker = " ← HIGH" if wr >= 0.65 else (" ← TOXIC" if wr < 0.35 else "")
            w(f"| {p[0]} | {p[1]} | {total} | {wr:.1%} | {ww} | {ll} |{marker}\n")
        w("\n")

        # Signal pair analysis
        w("## Signal Pair Analysis\n\n")
        w("### Top 10 Signal Pairs on Winning Trades\n\n")
        w("| Signal A | Signal B | Wins | Total | Win% | Avg P&L |\n")
        w("|----------|----------|------|-------|------|--------|\n")
        for r in win_pair_rows:
            if r["wins"] == 0:
                continue
            w(f"| {r['sig_a']} | {r['sig_b']} | {r['wins']} | {r['co_trade_count']} "
              f"| {r['win_rate_pct']:.1f}% | {r['avg_pnl_ticks']:.1f}t |\n")
        w("\n")

        w("### Top 10 Signal Pairs on Losing Trades\n\n")
        w("| Signal A | Signal B | Losses | Total | Win% | Avg P&L |\n")
        w("|----------|----------|--------|-------|------|--------|\n")
        for r in loss_pair_rows:
            if r["losses"] == 0:
                continue
            w(f"| {r['sig_a']} | {r['sig_b']} | {r['losses']} | {r['co_trade_count']} "
              f"| {r['win_rate_pct']:.1f}% | {r['avg_pnl_ticks']:.1f}t |\n")
        w("\n")

        # Toxic pairs
        w("### Toxic Signal Pairs\n\n")
        if toxic_pairs:
            w("*(Win rate < 33% with ≥3 co-occurring trades)*\n\n")
            w("| Signal A | Signal B | Win% | Trades | Avg P&L |\n")
            w("|----------|----------|------|--------|--------|\n")
            for r in toxic_pairs[:10]:
                w(f"| **{r['sig_a']}** | **{r['sig_b']}** | {r['win_rate_pct']:.1f}% "
                  f"| {r['co_trade_count']} | {r['avg_pnl_ticks']:.1f}t |\n")
        else:
            w("No toxic pairs identified (all pairs with ≥3 trades have win rate ≥ 33%).\n")
        w("\n")

        # Session type breakdown
        w("## Session-Type Breakdown\n\n")
        session_types = {}
        for t in all_trades:
            # session name like "session-01-trend_up-01"
            parts = t.session.split("-")
            stype = parts[2] if len(parts) > 2 else "unknown"
            if stype not in session_types:
                session_types[stype] = {"wins": 0, "losses": 0, "pnl": []}
            if t.pnl_ticks > 0:
                session_types[stype]["wins"] += 1
            else:
                session_types[stype]["losses"] += 1
            session_types[stype]["pnl"].append(t.pnl_ticks)

        w("| Session Type | Trades | Win% | Avg P&L (ticks) | Total P&L |\n")
        w("|-------------|--------|------|-----------------|----------|\n")
        for stype, d in sorted(session_types.items()):
            total_t = d["wins"] + d["losses"]
            wr = d["wins"] / total_t * 100 if total_t > 0 else 0.0
            ap = sum(d["pnl"]) / len(d["pnl"]) if d["pnl"] else 0.0
            tp = sum(d["pnl"]) * TICK_VALUE * CONTRACTS
            w(f"| {stype} | {total_t} | {wr:.1f}% | {ap:.1f}t | ${tp:,.0f} |\n")
        w("\n")

        # Standalone alpha note
        w("## Standalone Alpha Analysis\n\n")
        w("Standalone alpha measures whether a signal, when it is the *sole* trigger "
          "(no co-occurring signals on entry bar), still predicts direction.\n\n")
        w("| Signal | Standalone Trades | Standalone Win% | Avg P&L |\n")
        w("|--------|------------------|-----------------|--------|\n")
        for trade in []:  # pre-compute below
            pass

        # Recompute: trades where all_signals has exactly one signal
        standalone: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": []})
        for trade in all_trades:
            if len(set(trade.all_signals)) == 1:
                sig = trade.all_signals[0]
                if trade.pnl_ticks > 0:
                    standalone[sig]["wins"] += 1
                else:
                    standalone[sig]["losses"] += 1
                standalone[sig]["pnl"].append(trade.pnl_ticks)

        standalone_rows = []
        for sig, d in standalone.items():
            total_t = d["wins"] + d["losses"]
            wr = d["wins"] / total_t * 100 if total_t > 0 else 0.0
            ap = sum(d["pnl"]) / len(d["pnl"]) if d["pnl"] else 0.0
            standalone_rows.append((sig, total_t, wr, ap))
        standalone_rows.sort(key=lambda x: x[2], reverse=True)

        for sig, cnt, wr, ap in standalone_rows:
            if cnt > 0:
                w(f"| {sig} | {cnt} | {wr:.1f}% | {ap:.1f}t |\n")
        w("\n")

        # Key findings summary
        w("## Key Findings Summary\n\n")
        w("### Top 5 Alpha Signals\n")
        for i, row in enumerate(top5_alpha, 1):
            w(f"{i}. **{row['signal_id']}** ({row['category']}) — "
              f"{row['primary_win_rate']:.1f}% win, {row['primary_avg_pnl_ticks']:.1f}t avg P&L, "
              f"SNR={row['primary_snr']:.2f}, {row['primary_trades']} trades\n")
        w("\n")
        w("### Top 3 Noise Signals\n")
        for i, row in enumerate(top3_noise, 1):
            w(f"{i}. **{row['signal_id']}** ({row['category']}) — "
              f"{row['primary_win_rate']:.1f}% win, {row['primary_avg_pnl_ticks']:.1f}t avg P&L, "
              f"{row['primary_trades']} trades\n")
        w("\n")
        w("### Toxic Signal Pairs\n")
        if toxic_pairs:
            for r in toxic_pairs[:5]:
                w(f"- **{r['sig_a']} + {r['sig_b']}**: {r['win_rate_pct']:.1f}% win "
                  f"over {r['co_trade_count']} trades, avg {r['avg_pnl_ticks']:.1f}t\n")
        else:
            w("- No toxic pairs found.\n")
        w("\n")

        w("### Category Insights\n")
        best_cat = cat_results[0] if cat_results else None
        worst_cat = cat_results[-1] if cat_results else None
        if best_cat and best_cat[1]["total"] > 0:
            w(f"- **Best category:** {best_cat[0]} — "
              f"{best_cat[1]['win_rate']:.1%} win rate, {best_cat[1]['avg_pnl']:.1f}t avg P&L\n")
        if worst_cat and worst_cat[1]["total"] > 0:
            w(f"- **Worst category:** {worst_cat[0]} — "
              f"{worst_cat[1]['win_rate']:.1%} win rate, {worst_cat[1]['avg_pnl']:.1f}t avg P&L\n")
        w("\n")

        w(f"*Generated by `deep6/backtest/signal_attribution.py` — {total_bars} bars, {total_trades} trades*\n")

    print(f"Written: {md_path}")

    # -----------------------------------------------------------------------
    # Console summary
    # -----------------------------------------------------------------------
    print("\n" + "="*60)
    print("ATTRIBUTION SUMMARY")
    print("="*60)
    print(f"Total bars: {total_bars} | Total trades: {total_trades} | Win rate: {overall_win_rate:.1%}")
    print(f"Total P&L: ${total_pnl:,.0f}")
    print()
    print("TOP 5 ALPHA SIGNALS:")
    for i, row in enumerate(top5_alpha, 1):
        print(f"  {i}. {row['signal_id']:12s} win={row['primary_win_rate']:.1f}% "
              f"avg_pnl={row['primary_avg_pnl_ticks']:.1f}t SNR={row['primary_snr']:.2f} "
              f"n={row['primary_trades']}")
    print()
    print("TOP 3 NOISE SIGNALS:")
    for i, row in enumerate(top3_noise, 1):
        print(f"  {i}. {row['signal_id']:12s} win={row['primary_win_rate']:.1f}% "
              f"avg_pnl={row['primary_avg_pnl_ticks']:.1f}t n={row['primary_trades']}")
    print()
    print("TOXIC PAIRS:")
    if toxic_pairs:
        for r in toxic_pairs[:5]:
            print(f"  {r['sig_a']} + {r['sig_b']}: win={r['win_rate_pct']:.1f}% n={r['co_trade_count']}")
    else:
        print("  None found.")
    print()

    return top5_alpha, top3_noise, toxic_pairs


if __name__ == "__main__":
    run_attribution()
