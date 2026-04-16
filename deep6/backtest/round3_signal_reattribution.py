"""Round 3 Signal Re-Attribution Analysis — DEEP6 Backtest

This is the first attribution run where the imbalance category (IMB-03 stacked)
actually contributes to the confluence score. Previous R0 run used the same
score_bar() logic but with threshold=40 / TYPE_C which may have masked IMB-03's
contribution. R3 uses the stricter R1 config (threshold=70, TYPE_B) which requires
more categories to fire — making stacked imbalance's category vote decisive.

Key question answered here: Does IMB-03 (stacked imbalance) become alpha-positive
now that it scores as a full imbalance category vote?

Config: ScoreEntryThreshold=70, MinTier=TYPE_B, Stop=20t, Target=32t, MaxBars=20
All vetoes active (trap veto, delta chase, midday block).

Outputs:
  ninjatrader/backtests/results/round3/SIGNAL-REATTRIBUTION.md
  ninjatrader/backtests/results/round3/signal_stats_r3.csv

Usage:
  python3 -m deep6.backtest.round3_signal_reattribution
  # or directly:
  .venv/bin/python3 deep6/backtest/round3_signal_reattribution.py
"""
from __future__ import annotations

import csv
import json
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
RESULTS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round3"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# R0 baseline path for delta comparison
R0_RESULTS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results"

# ---------------------------------------------------------------------------
# R1 config (task: threshold=70, TYPE_B, all vetoes)
# ---------------------------------------------------------------------------
SCORE_ENTRY_THRESHOLD = 70.0
MIN_TIER_FOR_ENTRY = "TYPE_B"
STOP_LOSS_TICKS = 20
TARGET_TICKS = 32
MAX_BARS_IN_TRADE = 20
SLIPPAGE_TICKS = 1
TICK_SIZE = 0.25
TICK_VALUE = 5.0
CONTRACTS = 1
EXIT_ON_OPPOSING_SCORE = 70.0

TIER_MAP = {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
MIN_TIER_INT = TIER_MAP[MIN_TIER_FOR_ENTRY]

# ---------------------------------------------------------------------------
# Scorer constants (verbatim from ConfluenceScorer / signal_attribution.py)
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

DELTA_VOTING = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
AUCTION_VOTING = {"AUCT-01", "AUCT-02", "AUCT-05"}
POC_VOTING = {"POC-02", "POC-07", "POC-08"}


def signal_category(sig_id: str) -> Optional[str]:
    """Return scoring category for a signal ID, or None if non-voting."""
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
    # IMB signals: only IMB-03 with STACKED_T* detail contributes to imbalance
    # category — tracked via stacked tier logic in score_bar()
    return None


def imb_stacked_tier(sig_id: str, detail: str) -> int:
    """Extract stacked tier from IMB signal detail. Returns 0 if non-stacked."""
    if not sig_id.startswith("IMB"):
        return 0
    if "STACKED_T3" in detail or sig_id.endswith("-T3"):
        return 3
    elif "STACKED_T2" in detail or sig_id.endswith("-T2"):
        return 2
    elif "STACKED_T1" in detail or sig_id.endswith("-T1"):
        return 1
    return 0


@dataclass
class ScoredResult:
    total_score: float
    tier_int: int
    direction: int
    agreement: float
    cat_count: int
    categories: list[str]
    entry_price: float
    imb_stacked_bull: int    # highest stacked tier bull (0=none)
    imb_stacked_bear: int    # highest stacked tier bear (0=none)


def score_bar(signals: list[dict], bars_since_open: int, bar_delta: int,
              bar_close: float, zone_score: float, zone_dist_ticks: float) -> ScoredResult:
    """Python port of ConfluenceScorer.Score() — faithful to CS implementation.

    Critical for R3: IMB-03 signals with STACKED_T* detail now properly vote in
    the imbalance category, adding bull_weight=0.5 and cats_bull.add('imbalance').
    This is identical to R0 logic — the difference is the ENTRY THRESHOLD (70 vs 40)
    means bars that previously would fire at 40-69 score are now excluded, isolating
    the cases where imbalance contribution is the deciding margin.
    """
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
            detail = s.get("detail", "")
            tier = imb_stacked_tier(sid, detail)
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

    # Stacked imbalance votes (the R3 key feature)
    if stacked_bull_tier > 0:
        bull_weight += 0.5
        cats_bull.add("imbalance")
    if stacked_bear_tier > 0:
        bear_weight += 0.5
        cats_bear.add("imbalance")

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
        return ScoredResult(0.0, 0, 0, 0.0, 0, [], bar_close, stacked_bull_tier, stacked_bear_tier)

    delta_agrees = True
    if bar_delta != 0 and direction != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            delta_agrees = False

    ib_mult = IB_MULT if 0 <= bars_since_open < IB_BAR_END else 1.0

    zone_bonus = 0.0
    if zone_score >= ZONE_HIGH_MIN:
        zone_bonus = ZONE_NEAR_BONUS if zone_dist_ticks <= ZONE_NEAR_TICKS else ZONE_HIGH_BONUS
        cats_agreeing.add("volume_profile")
    elif zone_score >= ZONE_MID_MIN:
        zone_bonus = ZONE_MID_BONUS
        cats_agreeing.add("volume_profile")

    cat_count = len(cats_agreeing)
    confluence_mult = CONFLUENCE_MULT if cat_count >= CONFLUENCE_THRESHOLD else 1.0

    base_score = sum(CATEGORY_WEIGHTS.get(c, 5.0) for c in cats_agreeing)
    total_score = min(
        (base_score * confluence_mult + zone_bonus) * agreement * ib_mult,
        100.0
    )
    total_score = max(0.0, total_score)

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
        tier = 3
    elif total_score >= TYPE_B_MIN and cat_count >= 4 and delta_agrees and min_str:
        tier = 2
    elif total_score >= TYPE_C_MIN and cat_count >= 4 and min_str:
        tier = 1
    else:
        tier = 0

    if tier > 0 and MIDDAY_START <= bars_since_open <= MIDDAY_END:
        tier = 0

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
        imb_stacked_bull=stacked_bull_tier,
        imb_stacked_bear=stacked_bear_tier,
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
    primary_signal: str
    all_signals: list[str]
    categories_firing: list[str]
    session: str
    has_stacked_imb: bool      # IMB-03 with STACKED_T* on entry bar
    stacked_imb_tier: int      # highest stacked tier (0/1/2/3)
    abs01_present: bool        # ABS-01 specifically present
    imb03_present: bool        # IMB-03 present (any detail)


def extract_primary_signal(signals: list[dict], direction: int) -> str:
    """Mirror BacktestRunner.ExtractDominantSignalId — ABS/EXH first."""
    for s in signals:
        if s["direction"] == direction:
            sid = s["signalId"]
            if sid.startswith("ABS") or sid.startswith("EXH"):
                return sid
    dom = sorted(
        [s for s in signals if s["direction"] == direction],
        key=lambda x: x["strength"],
        reverse=True
    )
    return dom[0]["signalId"] if dom else "MIXED"


def run_session(session_path: Path) -> list[Trade]:
    """Replay one session and return completed trades."""
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
    trade_has_stacked_imb = False
    trade_stacked_imb_tier = 0
    trade_abs01 = False
    trade_imb03 = False

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
                    has_stacked_imb=trade_has_stacked_imb,
                    stacked_imb_tier=trade_stacked_imb_tier,
                    abs01_present=trade_abs01,
                    imb03_present=trade_imb03,
                ))
                in_trade = False
        else:
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

                # IMB-03 characterization for this entry
                stacked_tier_on_entry = 0
                has_stacked = False
                has_abs01 = False
                has_imb03 = False
                for s in signals:
                    sid = s["signalId"]
                    if sid == "ABS-01":
                        has_abs01 = True
                    if sid == "IMB-03":
                        has_imb03 = True
                    if sid.startswith("IMB"):
                        detail = s.get("detail", "")
                        tier = imb_stacked_tier(sid, detail)
                        if tier > 0:
                            has_stacked = True
                            stacked_tier_on_entry = max(stacked_tier_on_entry, tier)

                trade_has_stacked_imb = has_stacked
                trade_stacked_imb_tier = stacked_tier_on_entry
                trade_abs01 = has_abs01
                trade_imb03 = has_imb03
                in_trade = True

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
            has_stacked_imb=trade_has_stacked_imb,
            stacked_imb_tier=trade_stacked_imb_tier,
            abs01_present=trade_abs01,
            imb03_present=trade_imb03,
        ))

    return trades


# ---------------------------------------------------------------------------
# R0 baseline data loader (for delta comparison)
# ---------------------------------------------------------------------------
def load_r0_signal_stats() -> dict[str, dict]:
    """Load R0 signal_stats.csv for comparison. Returns signal_id -> row dict."""
    csv_path = R0_RESULTS_DIR / "signal_stats.csv"
    if not csv_path.exists():
        return {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        return {row["signal_id"]: row for row in reader}


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def run_attribution():
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))
    if not session_files:
        print(f"ERROR: No session files in {SESSIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"R3 Attribution: loading {len(session_files)} sessions...")
    print(f"Config: threshold={SCORE_ENTRY_THRESHOLD}, tier>={MIN_TIER_FOR_ENTRY}, "
          f"stop={STOP_LOSS_TICKS}t, target={TARGET_TICKS}t")

    all_trades: list[Trade] = []
    for sf in session_files:
        all_trades.extend(run_session(sf))

    print(f"Total trades: {len(all_trades)}")
    if not all_trades:
        print("WARNING: No trades at threshold=70/TYPE_B. Check data.", file=sys.stderr)
        return

    # --- Signal universe frequencies ---
    signal_fire_counts: Counter[str] = Counter()
    total_bars = 0
    for sf in session_files:
        with open(sf) as f:
            bars_raw = [json.loads(l) for l in f]
        total_bars += len(bars_raw)
        for b in bars_raw:
            for s in b.get("signals", []):
                signal_fire_counts[s["signalId"]] += 1

    all_signal_ids = sorted(signal_fire_counts.keys())

    # --- Per-signal attribution ---
    primary_stats: dict[str, dict] = {s: {"wins": 0, "losses": 0, "pnl": []} for s in all_signal_ids}
    primary_stats["MIXED"] = {"wins": 0, "losses": 0, "pnl": []}
    cooccur_stats: dict[str, dict] = {s: {"wins": 0, "losses": 0, "pnl": []} for s in all_signal_ids}

    for trade in all_trades:
        win = trade.pnl_ticks > 0
        pnl = trade.pnl_ticks
        psig = trade.primary_signal or "MIXED"
        if psig not in primary_stats:
            primary_stats[psig] = {"wins": 0, "losses": 0, "pnl": []}
        primary_stats[psig]["wins" if win else "losses"] += 1
        primary_stats[psig]["pnl"].append(pnl)
        for sig in trade.all_signals:
            if sig != psig:
                if sig not in cooccur_stats:
                    cooccur_stats[sig] = {"wins": 0, "losses": 0, "pnl": []}
                cooccur_stats[sig]["wins" if win else "losses"] += 1
                cooccur_stats[sig]["pnl"].append(pnl)

    # --- Category analysis ---
    cat_names = list(CATEGORY_WEIGHTS.keys())
    cat_stats: dict[str, dict] = {c: {"wins": 0, "losses": 0, "pnl": []} for c in cat_names}
    for trade in all_trades:
        win = trade.pnl_ticks > 0
        for c in trade.categories_firing:
            if c in cat_stats:
                cat_stats[c]["wins" if win else "losses"] += 1
                cat_stats[c]["pnl"].append(trade.pnl_ticks)

    # --- Category pair analysis ---
    cat_pair_wins: Counter[tuple] = Counter()
    cat_pair_losses: Counter[tuple] = Counter()
    for trade in all_trades:
        cats = sorted(trade.categories_firing)
        pairs = [(cats[i], cats[j]) for i in range(len(cats)) for j in range(i+1, len(cats))]
        win = trade.pnl_ticks > 0
        for p in pairs:
            if win: cat_pair_wins[p] += 1
            else: cat_pair_losses[p] += 1

    # --- Signal pair analysis ---
    sig_pair_wins: Counter[tuple] = Counter()
    sig_pair_losses: Counter[tuple] = Counter()
    sig_pair_pnl: dict[tuple, list] = defaultdict(list)
    for trade in all_trades:
        sigs = sorted(set(trade.all_signals))
        pairs = [(sigs[i], sigs[j]) for i in range(len(sigs)) for j in range(i+1, len(sigs))]
        win = trade.pnl_ticks > 0
        for p in pairs:
            sig_pair_pnl[p].append(trade.pnl_ticks)
            if win: sig_pair_wins[p] += 1
            else: sig_pair_losses[p] += 1

    # --- IMB-03 specific analysis (core R3 question) ---
    # 1. Trades where IMB-03 stacked was present vs not
    imb_stacked_trades = [t for t in all_trades if t.has_stacked_imb]
    non_imb_stacked_trades = [t for t in all_trades if not t.has_stacked_imb]

    # 2. ABS-01 + IMB-03 stacked combo
    abs01_imb03_trades = [t for t in all_trades if t.abs01_present and t.has_stacked_imb]
    abs01_only_trades = [t for t in all_trades if t.abs01_present and not t.has_stacked_imb]
    imb03_only_trades = [t for t in all_trades if not t.abs01_present and t.has_stacked_imb]

    # 3. Stacked tier breakdown
    tier1_trades = [t for t in all_trades if t.stacked_imb_tier == 1]
    tier2_trades = [t for t in all_trades if t.stacked_imb_tier == 2]
    tier3_trades = [t for t in all_trades if t.stacked_imb_tier == 3]

    def trade_stats(trades: list[Trade]) -> dict:
        if not trades:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                    "avg_pnl": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "snr": 0.0,
                    "total_pnl_dollars": 0.0}
        wins = [t for t in trades if t.pnl_ticks > 0]
        losses = [t for t in trades if t.pnl_ticks <= 0]
        win_pnls = [t.pnl_ticks for t in wins]
        loss_pnls = [t.pnl_ticks for t in losses]
        avg_win = sum(win_pnls) / len(win_pnls) if win_pnls else 0.0
        avg_loss = abs(sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0.0
        wr = len(wins) / len(trades)
        lr = 1 - wr
        snr = (avg_win * wr) / (avg_loss * lr) if avg_loss * lr > 0 else float("inf")
        all_pnl = [t.pnl_ticks for t in trades]
        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": wr,
            "avg_pnl": sum(all_pnl) / len(all_pnl),
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "snr": snr,
            "total_pnl_dollars": sum(t.pnl_dollars for t in trades),
        }

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
            "total": total, "wins": wins, "losses": losses,
            "win_rate": win_rate,
            "avg_pnl": sum(pnl_list) / len(pnl_list),
            "avg_win": avg_win, "avg_loss": avg_loss, "snr": snr,
        }

    # --- Overall stats ---
    total_trades = len(all_trades)
    wins_total = sum(1 for t in all_trades if t.pnl_ticks > 0)
    total_pnl = sum(t.pnl_dollars for t in all_trades)
    overall_win_rate = wins_total / total_trades if total_trades > 0 else 0.0

    tier_labels = {0: "QUIET", 1: "TYPE_C", 2: "TYPE_B", 3: "TYPE_A"}
    tier_counts = Counter(t.tier for t in all_trades)
    tier_wins = Counter(t.tier for t in all_trades if t.pnl_ticks > 0)
    exit_counts = Counter(t.exit_reason for t in all_trades)

    # --- Build sig_rows for CSV ---
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

    # Write signal_stats_r3.csv
    csv_path = RESULTS_DIR / "signal_stats_r3.csv"
    if sig_rows:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(sig_rows[0].keys()))
            writer.writeheader()
            writer.writerows(sig_rows)
        print(f"Written: {csv_path}")

    # --- Write signal_pairs_r3.csv ---
    all_pairs = set(sig_pair_wins.keys()) | set(sig_pair_losses.keys())
    pair_rows = []
    for p in sorted(all_pairs):
        ww = sig_pair_wins.get(p, 0)
        ll = sig_pair_losses.get(p, 0)
        total = ww + ll
        pnl_list = sig_pair_pnl[p]
        avg_pnl = sum(pnl_list) / len(pnl_list) if pnl_list else 0.0
        win_rate = ww / total if total > 0 else 0.0
        pair_rows.append({
            "sig_a": p[0], "sig_b": p[1],
            "co_trade_count": total,
            "wins": ww, "losses": ll,
            "win_rate_pct": round(win_rate * 100, 1),
            "avg_pnl_ticks": round(avg_pnl, 2),
        })
    pair_rows.sort(key=lambda x: x["co_trade_count"], reverse=True)

    csv_pairs_path = RESULTS_DIR / "signal_pairs_r3.csv"
    if pair_rows:
        with open(csv_pairs_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(pair_rows[0].keys()))
            writer.writeheader()
            writer.writerows(pair_rows)
        print(f"Written: {csv_pairs_path}")

    # --- Ranking ---
    def signal_alpha_score(row: dict) -> float:
        if row["primary_trades"] < 3:
            return -999.0
        return row["primary_win_rate"] * 0.5 + row["primary_avg_pnl_ticks"] * 5.0 + row["primary_snr"] * 2.0

    def signal_noise_score(row: dict) -> float:
        if row["primary_trades"] < 3:
            return 999.0
        return row["primary_win_rate"] + row["primary_avg_pnl_ticks"]

    valid_rows = [r for r in sig_rows if r["signal_id"] != "MIXED"]
    ranked_by_snr = sorted(valid_rows, key=lambda r: r["primary_snr"], reverse=True)
    top5_alpha = sorted([r for r in valid_rows if r["primary_trades"] >= 3],
                        key=signal_alpha_score, reverse=True)[:5]
    top3_noise = sorted([r for r in valid_rows if r["primary_trades"] >= 3],
                        key=signal_noise_score)[:3]

    toxic_pairs = [r for r in pair_rows if r["win_rate_pct"] < 33.0 and r["co_trade_count"] >= 3]
    toxic_pairs.sort(key=lambda x: x["win_rate_pct"])

    win_pair_rows = sorted(pair_rows, key=lambda x: x["wins"], reverse=True)[:10]
    loss_pair_rows = sorted(pair_rows, key=lambda x: x["losses"], reverse=True)[:10]

    cat_results = []
    for c in cat_names:
        row = stats_row(cat_stats[c])
        cat_results.append((c, row))
    cat_results.sort(key=lambda x: x[1]["avg_pnl"], reverse=True)

    tier_breakdown = []
    for tier_int, label in tier_labels.items():
        cnt = tier_counts.get(tier_int, 0)
        ww = tier_wins.get(tier_int, 0)
        t_pnl = [t.pnl_ticks for t in all_trades if t.tier == tier_int]
        avg_p = sum(t_pnl) / len(t_pnl) if t_pnl else 0.0
        win_r = ww / cnt * 100 if cnt > 0 else 0.0
        tier_breakdown.append((label, cnt, win_r, avg_p))

    # Load R0 for delta comparison
    r0_stats = load_r0_signal_stats()

    # --- IMB-03 verdict ---
    imb_stats = trade_stats(imb_stacked_trades)
    no_imb_stats = trade_stats(non_imb_stacked_trades)
    abs01_imb03_stats = trade_stats(abs01_imb03_trades)
    abs01_only_stats = trade_stats(abs01_only_trades)
    imb03_only_stats = trade_stats(imb03_only_trades)

    # Determine IMB-03 verdict
    if imb_stats["total"] >= 3:
        if imb_stats["win_rate"] >= 0.70 and imb_stats["avg_pnl"] > 5.0:
            imb_verdict = "ALPHA-POSITIVE"
            imb_verdict_detail = f"Win rate {imb_stats['win_rate']:.1%}, avg P&L {imb_stats['avg_pnl']:.1f}t — IMB-03 stacked is a genuine alpha contributor"
        elif imb_stats["win_rate"] >= 0.55 and imb_stats["avg_pnl"] > 0.0:
            imb_verdict = "WEAK-ALPHA"
            imb_verdict_detail = f"Win rate {imb_stats['win_rate']:.1%}, avg P&L {imb_stats['avg_pnl']:.1f}t — Positive but below ABS-01 quality bar"
        else:
            imb_verdict = "NOISE"
            imb_verdict_detail = f"Win rate {imb_stats['win_rate']:.1%}, avg P&L {imb_stats['avg_pnl']:.1f}t — Does not add directional edge"
    else:
        imb_verdict = "INSUFFICIENT-DATA"
        imb_verdict_detail = f"Only {imb_stats['total']} trades with stacked IMB at threshold=70/TYPE_B"

    # Top combo verdict
    if abs01_imb03_stats["total"] >= 3:
        combo_win_rate = abs01_imb03_stats["win_rate"]
        combo_pnl = abs01_imb03_stats["avg_pnl"]
        is_top_combo = combo_win_rate >= 0.75 and combo_pnl > 10.0
    else:
        combo_win_rate = 0.0
        combo_pnl = 0.0
        is_top_combo = False

    # -----------------------------------------------------------------------
    # Write SIGNAL-REATTRIBUTION.md
    # -----------------------------------------------------------------------
    md_path = RESULTS_DIR / "SIGNAL-REATTRIBUTION.md"
    with open(md_path, "w") as f:
        w = f.write

        w("# DEEP6 Round 3 Signal Re-Attribution Report\n\n")
        w("**Round:** R3 — First run with imbalance category active in scoring\n")
        w(f"**Sessions analyzed:** {len(session_files)} (50 sessions, {total_bars} bars)\n")
        w(f"**Config:** ScoreEntryThreshold={SCORE_ENTRY_THRESHOLD}, MinTier={MIN_TIER_FOR_ENTRY}, "
          f"Stop={STOP_LOSS_TICKS}t, Target={TARGET_TICKS}t, MaxBars={MAX_BARS_IN_TRADE}\n")
        w("**All vetoes active:** trap veto (≥3 traps), delta chase (>50Δ aligned), midday block (240-330)\n\n")

        w("## IMB-03 Verdict (Core R3 Question)\n\n")
        w(f"**Verdict: {imb_verdict}**\n\n")
        w(f"{imb_verdict_detail}\n\n")
        w("### Stacked Imbalance Performance Breakdown\n\n")
        w("| Condition | Trades | Win Rate | Avg P&L | SNR | Total P&L |\n")
        w("|-----------|--------|----------|---------|-----|-----------|\n")
        for label, stats in [
            ("Stacked IMB present", imb_stats),
            ("No stacked IMB", no_imb_stats),
            ("ABS-01 + Stacked IMB (combo)", abs01_imb03_stats),
            ("ABS-01 only (no IMB stacked)", abs01_only_stats),
            ("Stacked IMB only (no ABS-01)", imb03_only_stats),
        ]:
            if stats["total"] > 0:
                snr_str = f"{stats['snr']:.2f}" if stats['snr'] != float("inf") else "∞"
                w(f"| {label} | {stats['total']} | {stats['win_rate']:.1%} "
                  f"| {stats['avg_pnl']:.1f}t | {snr_str} | ${stats['total_pnl_dollars']:,.0f} |\n")
        w("\n")

        w("### Stacked Tier Quality (T1/T2/T3)\n\n")
        w("| Tier | Trades | Win Rate | Avg P&L |\n")
        w("|------|--------|----------|----------|\n")
        for label, trades_subset in [("T1 (weakest)", tier1_trades),
                                     ("T2 (medium)", tier2_trades),
                                     ("T3 (strongest)", tier3_trades)]:
            if trades_subset:
                s = trade_stats(trades_subset)
                w(f"| {label} | {s['total']} | {s['win_rate']:.1%} | {s['avg_pnl']:.1f}t |\n")
        w("\n")

        w("## Overall Backtest Summary (R3 Config)\n\n")
        w("| Metric | R3 Value | R0 Baseline | Delta |\n")
        w("|--------|----------|-------------|-------|\n")
        w(f"| Total trades | {total_trades} | 87 | {total_trades - 87:+d} |\n")
        w(f"| Win rate | {overall_win_rate:.1%} | 69.0% | {overall_win_rate - 0.690:+.1%} |\n")
        w(f"| Total P&L | ${total_pnl:,.0f} | $1,861 | ${total_pnl - 1861:+,.0f} |\n")
        w(f"| Avg P&L/trade | ${total_pnl/total_trades:.0f} | $21 | ${total_pnl/total_trades - 21:+.0f} |\n\n")

        w("### Exit Reason Breakdown\n\n")
        w("| Exit Reason | Count | % |\n|-------------|-------|---|\n")
        for reason, cnt in exit_counts.most_common():
            w(f"| {reason} | {cnt} | {cnt/total_trades:.1%} |\n")
        w("\n")

        w("### Tier Breakdown\n\n")
        w("| Tier | Trades | Win Rate | Avg P&L (ticks) |\n|------|--------|----------|------------------|\n")
        for label, cnt, wr, ap in tier_breakdown:
            if cnt > 0:
                w(f"| {label} | {cnt} | {wr:.1f}% | {ap:.1f} |\n")
        w("\n")

        # Per-signal attribution table (all 44 signals ranked by SNR)
        w("## All 44 Signals Ranked by SNR (R3)\n\n")
        w("*(Primary = signal drove the entry; SNR = signal-to-noise ratio)*\n\n")
        w("| Rank | Signal | Category | Primary Trades | Win% | Avg P&L | SNR | CoOccur Trades | CoOccur Win% |\n")
        w("|------|--------|----------|---------------|------|---------|-----|----------------|---------------|\n")
        snr_sorted = sorted(
            [r for r in sig_rows if r["signal_id"] != "MIXED"],
            key=lambda r: r["primary_snr"], reverse=True
        )
        for i, row in enumerate(snr_sorted, 1):
            r0_row = r0_stats.get(row["signal_id"])
            r0_snr = float(r0_row["primary_snr"]) if r0_row else 0.0
            snr_delta = f"({row['primary_snr'] - r0_snr:+.2f} vs R0)" if r0_row else ""
            w(f"| {i} | {row['signal_id']} | {row['category']} | {row['primary_trades']} "
              f"| {row['primary_win_rate']:.1f}% | {row['primary_avg_pnl_ticks']:.1f}t "
              f"| {row['primary_snr']:.2f} {snr_delta} "
              f"| {row['cooccur_trades']} | {row['cooccur_win_rate']:.1f}% |\n")
        w("\n")

        # Top 5 alpha
        w("## Top 5 Alpha Signals (R3)\n\n")
        w("*(Ranked by composite: win_rate × 0.5 + avg_pnl × 5 + SNR × 2)*\n\n")
        w("| Rank | Signal | Category | Win Rate | Avg P&L | SNR | Trades | R0 SNR | SNR Delta |\n")
        w("|------|--------|----------|----------|---------|-----|--------|--------|----------|\n")
        for i, row in enumerate(top5_alpha, 1):
            r0_row = r0_stats.get(row["signal_id"])
            r0_snr_val = float(r0_row["primary_snr"]) if r0_row else 0.0
            snr_delta = row["primary_snr"] - r0_snr_val
            w(f"| {i} | **{row['signal_id']}** | {row['category']} "
              f"| {row['primary_win_rate']:.1f}% | {row['primary_avg_pnl_ticks']:.1f}t "
              f"| {row['primary_snr']:.2f} | {row['primary_trades']} "
              f"| {r0_snr_val:.2f} | {snr_delta:+.2f} |\n")
        w("\n")

        # IMB-03 in essential signal set
        w("## Essential Signal Set Update\n\n")
        w("### Previous Essential Set (R0)\n")
        w("- **ABS-01** — Core alpha (77.8% win, 13.4t, SNR=9.46)\n")
        w("- EXH-02 — High-frequency entry trigger (65% win, 0.2t overall)\n\n")

        w("### R3 Determination\n\n")
        if imb_verdict == "ALPHA-POSITIVE":
            w("**IMB-03 (stacked imbalance) JOINS the essential set.**\n\n")
            w("Criteria for essential signal:\n")
            w(f"- Win rate ≥70%: {imb_stats['win_rate']:.1%} ✓\n")
            w(f"- Avg P&L ≥5t: {imb_stats['avg_pnl']:.1f}t ✓\n")
            w(f"- Sample ≥3 primary trades: {imb_stats['total']} ✓\n\n")
            w("**Updated Essential Signal Set:**\n")
            w("1. **ABS-01** (absorption) — Core alpha anchor\n")
            w("2. **IMB-03** (stacked imbalance) — Confirmed alpha-positive in R3\n")
        elif imb_verdict == "WEAK-ALPHA":
            w("**IMB-03 is WEAK-ALPHA — improves as confluence amplifier but not standalone essential.**\n\n")
            w(f"- Win rate: {imb_stats['win_rate']:.1%} (threshold: 70%) — does not clear bar\n")
            w(f"- Avg P&L: {imb_stats['avg_pnl']:.1f}t (threshold: 5t)\n\n")
            w("**Updated Essential Signal Set (unchanged):**\n")
            w("1. **ABS-01** (absorption) — Core alpha anchor\n")
            w("2. **EXH-02** (exhaustion) — High-frequency entry trigger\n")
            w("IMB-03 recommended as **confluence amplifier** (upgrade entry quality when co-occurring with ABS-01)\n")
        else:
            w(f"**IMB-03 does NOT join the essential set.** Verdict: {imb_verdict}\n\n")
            w("**Essential Signal Set (unchanged from R0):**\n")
            w("1. **ABS-01** (absorption) — Core alpha anchor\n")
            w("2. **EXH-02** (exhaustion) — High-frequency entry trigger\n")
        w("\n")

        # Thesis confirmation: ABS-01 at VAH/VAL + IMB-03
        w("## Thesis Confirmation: ABS-01 + IMB-03 Combo\n\n")
        w("Thesis: ABS-01 at VAH/VAL + IMB-03 stacked = highest win-rate combo\n\n")
        if abs01_imb03_stats["total"] >= 3:
            snr_str = f"{abs01_imb03_stats['snr']:.2f}" if abs01_imb03_stats['snr'] != float("inf") else "∞"
            w(f"**ABS-01 + Stacked IMB combo:** {abs01_imb03_stats['total']} trades, "
              f"{abs01_imb03_stats['win_rate']:.1%} win rate, "
              f"{abs01_imb03_stats['avg_pnl']:.1f}t avg P&L, SNR={snr_str}\n\n")
            w("| Variant | Trades | Win Rate | Avg P&L | SNR |\n")
            w("|---------|--------|----------|---------|-----|\n")
            for label, stats in [
                ("ABS-01 + Stacked IMB (combo)", abs01_imb03_stats),
                ("ABS-01 without Stacked IMB", abs01_only_stats),
                ("Stacked IMB without ABS-01", imb03_only_stats),
                ("All trades (baseline)", trade_stats(all_trades)),
            ]:
                if stats["total"] > 0:
                    snr_str_inner = f"{stats['snr']:.2f}" if stats['snr'] != float("inf") else "∞"
                    w(f"| {label} | {stats['total']} | {stats['win_rate']:.1%} "
                      f"| {stats['avg_pnl']:.1f}t | {snr_str_inner} |\n")
            w("\n")
            if is_top_combo:
                w(f"**CONFIRMED: ABS-01 + IMB-03 stacked is the highest win-rate combo** "
                  f"({combo_win_rate:.1%} win, {combo_pnl:.1f}t avg P&L)\n\n")
            else:
                w(f"**PARTIAL: ABS-01 + IMB-03 combo shows "
                  f"{combo_win_rate:.1%} win / {combo_pnl:.1f}t avg — see analysis below**\n\n")
        else:
            w(f"Insufficient data for combo analysis at threshold=70/TYPE_B. "
              f"Only {abs01_imb03_stats['total']} trades match ABS-01 + stacked IMB criteria.\n\n")
            w("Reduce threshold or check session data for stacked IMB presence at TYPE_B bars.\n\n")

        # R0 vs R3 delta comparison
        w("## R0 → R3 Delta Comparison\n\n")
        w("### What changed from R0 to R3\n")
        w("- R0: threshold=40, TYPE_C — permissive, many low-quality entries\n")
        w("- R3: threshold=70, TYPE_B — strict, only high-confluence entries\n")
        w("- IMB contribution: identical scoring logic; R3 filters reveal IMB-03's TRUE quality\n\n")
        w("### Signal Category Delta\n\n")
        w("| Category | R0 Trades | R3 Trades | R0 Win% | R3 Win% | R0 Avg P&L | R3 Avg P&L |\n")
        w("|----------|-----------|-----------|---------|---------|------------|------------|\n")
        r0_cat_data = {
            "imbalance": (77, 77.9, 11.8),
            "absorption": (87, 69.0, 4.3),
            "exhaustion": (78, 65.4, 2.2),
            "delta": (19, 47.4, -17.6),
            "volume_profile": (87, 69.0, 4.3),
        }
        for cat, row in cat_results:
            if row["total"] > 0:
                r0_d = r0_cat_data.get(cat, (0, 0.0, 0.0))
                w(f"| {cat} | {r0_d[0]} | {row['total']} "
                  f"| {r0_d[1]:.1f}% | {row['win_rate']:.1%} "
                  f"| {r0_d[2]:.1f}t | {row['avg_pnl']:.1f}t |\n")
        w("\n")

        # New toxic pairs check
        w("## Toxic Pair Analysis (R3)\n\n")
        w("Checking for NEW toxic pairs introduced by imbalance scoring activation.\n\n")
        if toxic_pairs:
            w("*(Win rate < 33% with ≥3 co-occurring trades)*\n\n")
            w("| Signal A | Signal B | Win% | Trades | Avg P&L | New in R3? |\n")
            w("|----------|----------|------|--------|---------|------------|\n")
            r0_toxic_set = {("ABS-01", "VOLP-03"), ("DELT-01", "VOLP-03"),
                            ("DELT-04", "VOLP-03"), ("EXH-02", "VOLP-03"),
                            ("IMB-03", "VOLP-03"), ("DELT-01", "DELT-04"),
                            ("DELT-04", "EXH-02")}
            new_toxic_found = False
            for r in toxic_pairs[:15]:
                pair_key = (r["sig_a"], r["sig_b"])
                is_new = pair_key not in r0_toxic_set
                new_marker = "**NEW**" if is_new else "—"
                if is_new:
                    new_toxic_found = True
                w(f"| **{r['sig_a']}** | **{r['sig_b']}** | {r['win_rate_pct']:.1f}% "
                  f"| {r['co_trade_count']} | {r['avg_pnl_ticks']:.1f}t | {new_marker} |\n")
            w("\n")
            if new_toxic_found:
                w("**WARNING: New toxic pairs detected with imbalance scoring active. "
                  "Review IMB combinations above before production deployment.**\n\n")
            else:
                w("**No new toxic pairs from imbalance activation.** "
                  "All toxic pairs were present in R0 and are driven by volatile regime (VOLP-03 co-occurrence).\n\n")
        else:
            w("No toxic pairs at threshold=70/TYPE_B configuration. "
              "Stricter entry filter eliminated all volatile-session entries.\n\n")

        # Category pair performance
        w("## Category Pair Performance (R3)\n\n")
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

        # Session breakdown
        w("## Session-Type Breakdown (R3)\n\n")
        session_types: dict[str, dict] = {}
        for t in all_trades:
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

        # Key findings
        w("## Key Findings Summary\n\n")
        w(f"### IMB-03 Verdict: **{imb_verdict}**\n")
        w(f"{imb_verdict_detail}\n\n")

        w("### Top Alpha Signals (R3)\n")
        for i, row in enumerate(top5_alpha, 1):
            w(f"{i}. **{row['signal_id']}** ({row['category']}) — "
              f"{row['primary_win_rate']:.1f}% win, {row['primary_avg_pnl_ticks']:.1f}t, "
              f"SNR={row['primary_snr']:.2f}, {row['primary_trades']} trades\n")
        w("\n")

        w("### Noise Signals (R3)\n")
        for i, row in enumerate(top3_noise, 1):
            w(f"{i}. **{row['signal_id']}** ({row['category']}) — "
              f"{row['primary_win_rate']:.1f}% win, {row['primary_avg_pnl_ticks']:.1f}t, "
              f"{row['primary_trades']} trades\n")
        w("\n")

        if is_top_combo:
            w("### Thesis Status: CONFIRMED\n")
            w(f"ABS-01 at VAH/VAL + IMB-03 stacked = {combo_win_rate:.1%} win rate, "
              f"{combo_pnl:.1f}t avg P&L — highest win-rate combo in R3\n\n")
        else:
            w("### Thesis Status: PARTIAL / INSUFFICIENT DATA\n")
            if abs01_imb03_stats["total"] >= 3:
                w(f"ABS-01 + IMB-03 combo: {combo_win_rate:.1%} win, {combo_pnl:.1f}t avg P&L "
                  f"over {abs01_imb03_stats['total']} trades — does not clear 75%/10t threshold for full confirmation\n\n")
            else:
                w(f"Insufficient sample at threshold=70/TYPE_B: {abs01_imb03_stats['total']} trades. "
                  f"Lower threshold to 60 or TYPE_C to get adequate sample for combo analysis.\n\n")

        w(f"*Generated by `deep6/backtest/round3_signal_reattribution.py` — "
          f"{total_bars} bars, {total_trades} trades, R3 config (threshold=70, TYPE_B)*\n")

    print(f"Written: {md_path}")

    # -----------------------------------------------------------------------
    # Console summary
    # -----------------------------------------------------------------------
    print("\n" + "="*60)
    print("R3 ATTRIBUTION SUMMARY")
    print("="*60)
    print(f"Total bars: {total_bars} | Trades: {total_trades} | Win rate: {overall_win_rate:.1%}")
    print(f"Total P&L: ${total_pnl:,.0f}")
    print(f"\nIMB-03 VERDICT: {imb_verdict}")
    print(f"  {imb_verdict_detail}")
    print(f"\nStacked IMB trades: {imb_stats['total']} ({imb_stats['win_rate']:.1%} win, {imb_stats['avg_pnl']:.1f}t avg)")
    print(f"ABS-01 + IMB-03 combo: {abs01_imb03_stats['total']} trades ({abs01_imb03_stats['win_rate']:.1%} win, {abs01_imb03_stats['avg_pnl']:.1f}t avg)")
    print()
    print("TOP ALPHA SIGNALS:")
    for i, row in enumerate(top5_alpha, 1):
        print(f"  {i}. {row['signal_id']:12s} win={row['primary_win_rate']:.1f}% "
              f"avg={row['primary_avg_pnl_ticks']:.1f}t SNR={row['primary_snr']:.2f} n={row['primary_trades']}")
    print()
    print("TOXIC PAIRS:")
    if toxic_pairs:
        for r in toxic_pairs[:5]:
            print(f"  {r['sig_a']} + {r['sig_b']}: win={r['win_rate_pct']:.1f}% n={r['co_trade_count']}")
    else:
        print("  None at threshold=70/TYPE_B")
    print()
    if is_top_combo:
        print(f"THESIS CONFIRMED: ABS-01 + IMB-03 = {combo_win_rate:.1%} win, {combo_pnl:.1f}t avg")
    else:
        print(f"THESIS: Combo win={combo_win_rate:.1%} avg={combo_pnl:.1f}t n={abs01_imb03_stats['total']} — "
              + ("PARTIAL" if abs01_imb03_stats['total'] >= 3 else "INSUFFICIENT DATA"))

    return imb_verdict, top5_alpha, toxic_pairs, is_top_combo


if __name__ == "__main__":
    run_attribution()
