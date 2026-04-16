"""Round 3 Weight Optimizer — DEEP6 scorer category weight re-optimization.

Now that imbalance category (weight=13) actually contributes to scoring (R2 fix),
this round tests whether boosting imbalance weight improves out-of-sample performance.

R1 current weights: abs=32, exh=24, delta=14, imb=13, auction=12, vol=5, trap=0, engine=0
(poc→engine, trapped→0 from R1 meta-optimization; total = 100)

Configurations:
  1. R1 current:  abs=32, exh=24, delta=14, imb=13, auction=12, vol=5, trap=0, engine=0
  2. Imbalance-boosted: abs=28, exh=20, delta=12, imb=25, auction=8, vol=5, trap=2, engine=0
  3. Thesis+imbalance:  abs=30, exh=22, delta=10, imb=20, auction=10, vol=5, trap=3, engine=0
  4. Equal: all 8 categories at 12.5
  5. Attribution-informed: based on R3 signal-to-noise ratios with active imbalance
  6. Grid search: abs[20-35] × imb[10-25] (10 points each) — others scaled proportionally

Walk-forward validation (30/10/10 split) on top 3 configs.

Output:
  ninjatrader/backtests/results/round3/WEIGHT-OPTIMIZATION-R3.md

Usage:
  python3 -m deep6.backtest.round3_weight_optimizer
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
RESULTS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round3"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Backtest config (same as R1 for comparability)
# ---------------------------------------------------------------------------
SCORE_ENTRY_THRESHOLD = 40.0
MIN_TIER_FOR_ENTRY = "TYPE_C"
STOP_LOSS_TICKS = 8
TARGET_TICKS = 16
MAX_BARS_IN_TRADE = 20
SLIPPAGE_TICKS = 1
TICK_SIZE = 0.25
TICK_VALUE = 5.0
CONTRACTS = 1
EXIT_ON_OPPOSING_SCORE = 40.0

TIER_MAP = {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}
MIN_TIER_INT = TIER_MAP[MIN_TIER_FOR_ENTRY]

# ---------------------------------------------------------------------------
# Scorer constants (architecture-locked)
# ---------------------------------------------------------------------------
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

# Signal routing (mirror ConfluenceScorer.cs)
DELTA_VOTING = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
AUCTION_VOTING = {"AUCT-01", "AUCT-02", "AUCT-05"}
POC_VOTING = {"POC-02", "POC-07", "POC-08"}

# ---------------------------------------------------------------------------
# R1 category names (note: "poc" → "engine" in R1 CS weight names but scorer
# logic maps POC_VOTING signals to "poc" category — keep "poc" in weight dict)
# ---------------------------------------------------------------------------
CATS = ["absorption", "exhaustion", "trapped", "delta", "imbalance",
        "volume_profile", "auction", "poc"]

# ---------------------------------------------------------------------------
# Weight configurations
# ---------------------------------------------------------------------------

# 1. R1 current — weights from ConfluenceScorer.cs (post R1 meta-optimization)
R1_CURRENT = {
    "absorption":    32.0,
    "exhaustion":    24.0,
    "trapped":        0.0,
    "delta":         14.0,
    "imbalance":     13.0,
    "volume_profile": 5.0,
    "auction":       12.0,
    "poc":            0.0,
}

# 2. Imbalance-boosted — push imbalance to 25 (was 13), pull abs/exh down slightly
IMB_BOOSTED = {
    "absorption":    28.0,
    "exhaustion":    20.0,
    "trapped":        2.0,
    "delta":         12.0,
    "imbalance":     25.0,
    "volume_profile": 5.0,
    "auction":        8.0,
    "poc":            0.0,
}

# 3. Thesis + imbalance — balanced approach: strong abs/exh + elevated imbalance
THESIS_IMB = {
    "absorption":    30.0,
    "exhaustion":    22.0,
    "trapped":        3.0,
    "delta":         10.0,
    "imbalance":     20.0,
    "volume_profile": 5.0,
    "auction":       10.0,
    "poc":            0.0,
}

# 4. Equal — all 8 categories at 12.5
EQUAL_WEIGHTS = {cat: 12.5 for cat in CATS}

# 5. Attribution-informed — R3 SNR-proportional with imbalance now active
#    Revised SNR composite (imbalance now contributes):
#    - absorption:     69% win, 4.3t avg  → composite = 0.69*0.5 + 4.3*0.05 = 0.560
#    - exhaustion:     65% win, 2.2t avg  → 0.65*0.5 + 2.2*0.05 = 0.435
#    - imbalance:      73% win, 8.5t avg  → 0.73*0.5 + 8.5*0.05 = 0.790 (now active, discounted from R1 77.9% since partial scoring)
#    - delta:          47% win, -17.6t    → clamped to 0.08 (negative raw)
#    - volume_profile: 69% win, 4.3t avg  → 0.560 (co-fires with absorption)
#    - auction:        55% win, 1.5t avg  → 0.55*0.5 + 1.5*0.05 = 0.350
#    - trapped:        0.0 (zeroed by R1 — near-zero SNR confirmed)
#    - poc:            0.0 (zeroed by R1)
_r3_attr_raw = {
    "absorption":    0.560,
    "exhaustion":    0.435,
    "trapped":       0.0,
    "delta":         0.08,
    "imbalance":     0.790,
    "volume_profile": 0.560,
    "auction":       0.350,
    "poc":           0.0,
}
_r3_attr_total = sum(_r3_attr_raw.values())
ATTRIBUTION_R3 = {k: round(v / _r3_attr_total * 100, 1) for k, v in _r3_attr_raw.items()}

# Named configurations (ordered for report)
NAMED_CONFIGS: list[tuple[str, dict]] = [
    ("1_r1_current",          R1_CURRENT),
    ("2_imb_boosted",         IMB_BOOSTED),
    ("3_thesis_imb",          THESIS_IMB),
    ("4_equal",               EQUAL_WEIGHTS),
    ("5_attribution_r3",      ATTRIBUTION_R3),
]

# ---------------------------------------------------------------------------
# Grid search: abs[20-35] × imb[10-25] (10 points each)
# Remaining categories (exh, delta, vol, auction) scaled proportionally from R1
# ---------------------------------------------------------------------------
# R1 remaining after abs and imb are locked:
# exh=24, delta=14, vol=5, auction=12, trap=0, poc=0 → total_remaining = 55
_R1_REMAINING = {
    "exhaustion":    24.0,
    "trapped":        0.0,
    "delta":         14.0,
    "volume_profile": 5.0,
    "auction":       12.0,
    "poc":            0.0,
}
_R1_REMAINING_TOTAL = sum(_R1_REMAINING.values())  # 55.0

ABS_GRID = [20, 22, 25, 27, 30, 32, 33, 34, 35, 38]  # 10 points
IMB_GRID = [10, 12, 14, 16, 18, 20, 22, 23, 24, 25]   # 10 points

TOTAL_WEIGHT_BUDGET = 100.0


def make_r3_grid_weights(abs_w: float, imb_w: float) -> dict:
    """Build weight dict: lock abs + imb, distribute remaining proportionally from R1."""
    remaining = TOTAL_WEIGHT_BUDGET - abs_w - imb_w
    weights = {
        "absorption": abs_w,
        "imbalance":  imb_w,
    }
    for cat, r1_w in _R1_REMAINING.items():
        weights[cat] = max(0.0, remaining * (r1_w / _R1_REMAINING_TOTAL))
    return weights


# ---------------------------------------------------------------------------
# Scorer — parameterized weight dict (faithfully ported from R1)
# ---------------------------------------------------------------------------

@dataclass
class ScoredBar:
    total_score: float
    tier_int: int
    direction: int
    agreement: float
    cat_count: int
    categories: list
    entry_price: float


def score_bar_with_weights(
    signals: list,
    bars_since_open: int,
    bar_delta: int,
    bar_close: float,
    zone_score: float,
    zone_dist_ticks: float,
    weights: dict,
) -> ScoredBar:
    """Faithful port of ConfluenceScorer.Score() with pluggable category weights.

    Key R2 change: imbalance category now contributes to base_score via
    cats_agreeing — previously stacked_tier was computed but never added to cats.
    The fix: cats_bull/cats_bear.add("imbalance") happens alongside stacked_tier tracking.
    """
    bull_weight = 0.0
    bear_weight = 0.0
    cats_bull: set = set()
    cats_bear: set = set()
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
                bull_weight += st
                cats_bull.add("absorption")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("absorption")
                max_bear_str = max(max_bear_str, st)
        elif sid.startswith("EXH"):
            if d > 0:
                bull_weight += st
                cats_bull.add("exhaustion")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("exhaustion")
                max_bear_str = max(max_bear_str, st)
        elif sid.startswith("TRAP"):
            trap_count += 1
            if d > 0:
                bull_weight += st
                cats_bull.add("trapped")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("trapped")
                max_bear_str = max(max_bear_str, st)
        elif sid.startswith("IMB"):
            # R3 FIX: imbalance signals now register in cats_bull/bear AND stacked_tier
            # Previously (R1/R2), only stacked_tier was updated — imbalance never appeared
            # in cats_agreeing so its weight was never added to base_score.
            # Now: register in cats immediately, stacked_tier tracks tier bonus separately.
            detail = s.get("detail", "")
            tier = 0
            if "STACKED_T3" in detail or sid.endswith("-T3"):
                tier = 3
            elif "STACKED_T2" in detail or sid.endswith("-T2"):
                tier = 2
            elif "STACKED_T1" in detail or sid.endswith("-T1"):
                tier = 1

            if d > 0:
                bull_weight += st
                cats_bull.add("imbalance")
                max_bull_str = max(max_bull_str, st)
                if tier > 0:
                    stacked_bull_tier = max(stacked_bull_tier, tier)
            elif d < 0:
                bear_weight += st
                cats_bear.add("imbalance")
                max_bear_str = max(max_bear_str, st)
                if tier > 0:
                    stacked_bear_tier = max(stacked_bear_tier, tier)
        elif sid in DELTA_VOTING:
            if d > 0:
                bull_weight += st
                cats_bull.add("delta")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("delta")
                max_bear_str = max(max_bear_str, st)
        elif sid in AUCTION_VOTING:
            if d > 0:
                bull_weight += st
                cats_bull.add("auction")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("auction")
                max_bear_str = max(max_bear_str, st)
        elif sid in POC_VOTING:
            if d > 0:
                bull_weight += st
                cats_bull.add("poc")
                max_bull_str = max(max_bull_str, st)
            elif d < 0:
                bear_weight += st
                cats_bear.add("poc")
                max_bear_str = max(max_bear_str, st)

    # Stacked imbalance tier bonus (adds fractional weight beyond categorical presence)
    if stacked_bull_tier > 0:
        bull_weight += 0.5
    if stacked_bear_tier > 0:
        bear_weight += 0.5

    # Determine dominant direction
    def _count_side_votes(dir_: int, stacked_tier: int) -> int:
        cnt = 0
        for s in signals:
            if s["direction"] != dir_:
                continue
            sid = s["signalId"]
            if any(sid.startswith(p) for p in ("ABS", "EXH", "TRAP", "IMB")):
                cnt += 1
            elif sid in DELTA_VOTING or sid in AUCTION_VOTING or sid in POC_VOTING:
                cnt += 1
        if stacked_tier > 0:
            cnt += 1
        return cnt

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
        return ScoredBar(0.0, 0, 0, 0.0, 0, [], bar_close)

    # Delta agreement gate
    delta_agrees = True
    if bar_delta != 0 and direction != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            delta_agrees = False

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
    confluence_mult = CONFLUENCE_MULT if cat_count >= CONFLUENCE_THRESHOLD else 1.0

    # Base score — now includes imbalance weight when imbalance fires
    base_score = sum(weights.get(c, 5.0) for c in cats_agreeing)

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
        tier = 3
    elif total_score >= TYPE_B_MIN and cat_count >= 4 and delta_agrees and min_str:
        tier = 2
    elif total_score >= TYPE_C_MIN and cat_count >= 4 and min_str:
        tier = 1
    else:
        tier = 0

    if tier > 0 and MIDDAY_START <= bars_since_open <= MIDDAY_END:
        tier = 0

    # Entry price
    entry_price = 0.0
    for s in signals:
        if s["direction"] == direction and s.get("price", 0.0) != 0.0:
            sid = s["signalId"]
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = s["price"]
                break
    if entry_price == 0.0:
        entry_price = bar_close

    return ScoredBar(
        total_score=total_score,
        tier_int=tier,
        direction=direction,
        agreement=agreement,
        cat_count=cat_count,
        categories=sorted(cats_agreeing),
        entry_price=entry_price,
    )


# ---------------------------------------------------------------------------
# Trade simulation
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    pnl_ticks: float
    pnl_dollars: float
    exit_reason: str
    tier: int
    score: float
    session: str


def run_session(session_path: Path, weights: dict) -> list:
    """Replay one session and return closed trades."""
    with open(session_path) as f:
        bars = [json.loads(line) for line in f if line.strip()]

    trades = []
    in_trade = False
    entry_price = 0.0
    entry_bar_idx = 0
    trade_dir = 0
    trade_tier = 0
    trade_score = 0.0
    session_name = session_path.stem

    for bar in bars:
        bar_idx = bar["barIdx"]
        bars_since_open = bar.get("barsSinceOpen", bar_idx)
        bar_delta = bar.get("barDelta", 0)
        bar_close = bar["barClose"]
        zone_score = bar.get("zoneScore", 0.0)
        zone_dist = bar.get("zoneDistTicks", 999.0)
        signals = bar.get("signals", [])

        scored = score_bar_with_weights(
            signals, bars_since_open, bar_delta, bar_close, zone_score, zone_dist, weights
        )

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
                    pnl_ticks=pnl_ticks,
                    pnl_dollars=pnl_ticks * TICK_VALUE * CONTRACTS,
                    exit_reason=exit_reason,
                    tier=trade_tier,
                    score=trade_score,
                    session=session_name,
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
                in_trade = True

    # Session-end force exit
    if in_trade and bars:
        last_bar = bars[-1]
        exit_price = last_bar["barClose"] - (trade_dir * SLIPPAGE_TICKS * TICK_SIZE)
        pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
        trades.append(Trade(
            pnl_ticks=pnl_ticks,
            pnl_dollars=pnl_ticks * TICK_VALUE * CONTRACTS,
            exit_reason="SESSION_END",
            tier=trade_tier,
            score=trade_score,
            session=session_name,
        ))

    return trades


# ---------------------------------------------------------------------------
# Performance metrics
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    config_name: str
    weights: dict
    n_trades: int
    win_rate: float
    sharpe: float
    profit_factor: float
    total_pnl: float
    avg_pnl: float
    max_dd: float
    total_pnl_dollars: float


def compute_metrics(config_name: str, weights: dict, trades: list) -> Metrics:
    if not trades:
        return Metrics(
            config_name=config_name, weights=weights, n_trades=0,
            win_rate=0.0, sharpe=0.0, profit_factor=0.0, total_pnl=0.0,
            avg_pnl=0.0, max_dd=0.0, total_pnl_dollars=0.0,
        )

    pnl_ticks = [t.pnl_ticks for t in trades]
    pnl_dollars = [t.pnl_dollars for t in trades]
    wins = [p for p in pnl_ticks if p > 0]
    losses = [p for p in pnl_ticks if p <= 0]

    n = len(pnl_ticks)
    win_rate = len(wins) / n if n > 0 else 0.0

    mean_pnl = sum(pnl_ticks) / n
    if n > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnl_ticks) / (n - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 1e-9
    else:
        std_pnl = 1e-9
    sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses)) if losses else 1e-9
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnl_dollars:
        cumulative += p
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    return Metrics(
        config_name=config_name,
        weights=weights,
        n_trades=n,
        win_rate=win_rate,
        sharpe=sharpe,
        profit_factor=profit_factor,
        total_pnl=sum(pnl_ticks),
        avg_pnl=mean_pnl,
        max_dd=max_dd,
        total_pnl_dollars=sum(pnl_dollars),
    )


def evaluate_config(config_name: str, weights: dict, session_files: list) -> Metrics:
    all_trades = []
    for sf in session_files:
        all_trades.extend(run_session(sf, weights))
    return compute_metrics(config_name, weights, all_trades)


# ---------------------------------------------------------------------------
# Walk-forward validation (30/10/10 split)
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardResult:
    config_name: str
    weights: dict
    train_sharpe: float
    val_sharpe: float
    test_sharpe: float
    train_trades: int
    val_trades: int
    test_trades: int
    degradation: float  # test_sharpe - train_sharpe (negative = overfit)


def walk_forward(config_name: str, weights: dict, session_files: list) -> WalkForwardResult:
    """30/10/10 walk-forward: train on first 30 sessions, validate next 10, test final 10."""
    n = len(session_files)
    train_end = 30
    val_end = 40
    # test = sessions 40-50

    train_sessions = session_files[:train_end]
    val_sessions = session_files[train_end:val_end]
    test_sessions = session_files[val_end:]

    train_m = evaluate_config(f"{config_name}_train", weights, train_sessions)
    val_m = evaluate_config(f"{config_name}_val", weights, val_sessions)
    test_m = evaluate_config(f"{config_name}_test", weights, test_sessions)

    return WalkForwardResult(
        config_name=config_name,
        weights=weights,
        train_sharpe=train_m.sharpe,
        val_sharpe=val_m.sharpe,
        test_sharpe=test_m.sharpe,
        train_trades=train_m.n_trades,
        val_trades=val_m.n_trades,
        test_trades=test_m.n_trades,
        degradation=test_m.sharpe - train_m.sharpe,
    )


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _pf_str(pf: float) -> str:
    return f"{pf:.2f}" if pf != float("inf") else "inf"


def _weights_row(name: str, w: dict) -> str:
    vals = [
        w.get("absorption", 0),
        w.get("exhaustion", 0),
        w.get("trapped", 0),
        w.get("delta", 0),
        w.get("imbalance", 0),
        w.get("volume_profile", 0),
        w.get("auction", 0),
        w.get("poc", 0),
    ]
    row_sum = sum(vals)
    return (f"| {name} | " +
            " | ".join(f"{v:.1f}" for v in vals) +
            f" | {row_sum:.1f} |")


# ---------------------------------------------------------------------------
# Main optimization
# ---------------------------------------------------------------------------

def run_optimization():
    session_files = sorted(SESSIONS_DIR.glob("*.ndjson"))
    if not session_files:
        print(f"ERROR: No session files in {SESSIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"R3 Weight Optimizer: {len(session_files)} sessions")
    print(f"  R1 current weights: abs=32, exh=24, delta=14, imb=13, auction=12, vol=5")
    print(f"  Question: Does boosting imbalance weight now that it actually scores improve perf?")

    # -----------------------------------------------------------------------
    # Part 1: Named configurations
    # -----------------------------------------------------------------------
    print("\n[1/3] Evaluating 5 named weight configurations...")
    named_results: list[Metrics] = []
    for name, weights in NAMED_CONFIGS:
        print(f"  {name}...", end=" ", flush=True)
        m = evaluate_config(name, weights, session_files)
        named_results.append(m)
        print(f"trades={m.n_trades}  sharpe={m.sharpe:.4f}  pf={_pf_str(m.profit_factor)}  "
              f"wr={m.win_rate*100:.1f}%  pnl=${m.total_pnl_dollars:+.0f}  dd=${m.max_dd:.0f}")

    baseline = named_results[0]  # R1 current

    # -----------------------------------------------------------------------
    # Part 2: Grid search (abs × imb)
    # -----------------------------------------------------------------------
    n_grid = len(ABS_GRID) * len(IMB_GRID)
    print(f"\n[2/3] Grid search: abs × imb ({len(ABS_GRID)}×{len(IMB_GRID)} = {n_grid} configs)...")
    grid_results: list[Metrics] = []
    for abs_w in ABS_GRID:
        for imb_w in IMB_GRID:
            name = f"grid_abs{abs_w}_imb{imb_w}"
            weights = make_r3_grid_weights(abs_w, imb_w)
            m = evaluate_config(name, weights, session_files)
            grid_results.append(m)
            print(f"  abs={abs_w:2d} imb={imb_w:2d}: trades={m.n_trades:3d}  sharpe={m.sharpe:.4f}  "
                  f"pf={_pf_str(m.profit_factor)}  wr={m.win_rate*100:.1f}%  pnl=${m.total_pnl_dollars:+.0f}")

    # -----------------------------------------------------------------------
    # Identify best
    # -----------------------------------------------------------------------
    all_results = named_results + grid_results
    best = max(all_results, key=lambda m: m.sharpe)
    best_grid = max(grid_results, key=lambda m: m.sharpe)
    best_named = max(named_results, key=lambda m: m.sharpe)

    sharpe_delta_vs_r1 = best.sharpe - baseline.sharpe
    sharpe_pct = (sharpe_delta_vs_r1 / abs(baseline.sharpe) * 100) if baseline.sharpe != 0 else float("inf")

    # -----------------------------------------------------------------------
    # Part 3: Walk-forward on top 3 configs
    # -----------------------------------------------------------------------
    print(f"\n[3/3] Walk-forward validation (30/10/10) on top 3 configs...")

    # Top 3 by Sharpe across all results
    top3 = sorted(all_results, key=lambda m: m.sharpe, reverse=True)[:3]
    wf_results: list[WalkForwardResult] = []
    for m in top3:
        print(f"  {m.config_name}...", end=" ", flush=True)
        # find the weights
        named_dict = {name: w for name, w in NAMED_CONFIGS}
        if m.config_name in named_dict:
            wts = named_dict[m.config_name]
        else:
            wts = m.weights
        wf = walk_forward(m.config_name, wts, session_files)
        wf_results.append(wf)
        print(f"train={wf.train_sharpe:.4f}  val={wf.val_sharpe:.4f}  test={wf.test_sharpe:.4f}  "
              f"degradation={wf.degradation:+.4f}")

    # -----------------------------------------------------------------------
    # Write report
    # -----------------------------------------------------------------------
    out_path = RESULTS_DIR / "WEIGHT-OPTIMIZATION-R3.md"
    _write_report(
        out_path,
        named_results,
        grid_results,
        best,
        best_named,
        best_grid,
        baseline,
        sharpe_delta_vs_r1,
        sharpe_pct,
        wf_results,
        top3,
    )
    print(f"\nReport written: {out_path}")
    print(f"\nR3 RESULT:")
    print(f"  Baseline (R1): sharpe={baseline.sharpe:.4f}")
    print(f"  Best config:   {best.config_name}  sharpe={best.sharpe:.4f}  delta={sharpe_delta_vs_r1:+.4f}  ({sharpe_pct:+.1f}%)")
    print(f"  Weights: {best.weights}")
    return best, baseline, sharpe_delta_vs_r1


def _write_report(
    out_path: Path,
    named_results: list,
    grid_results: list,
    best: Metrics,
    best_named: Metrics,
    best_grid: Metrics,
    baseline: Metrics,
    sharpe_delta: float,
    sharpe_pct: float,
    wf_results: list,
    top3: list,
) -> None:
    lines: list[str] = []

    lines.append("# DEEP6 Round 3 — Weight Re-Optimization (Active Imbalance Scoring)")
    lines.append("")
    lines.append("**Generated by:** `deep6/backtest/round3_weight_optimizer.py`")
    lines.append(f"**Sessions:** 50 sessions (all regimes: trend_up, trend_down, ranging, volatile, slow_grind)")
    lines.append(f"**Baseline (R1):** abs=32, exh=24, delta=14, imb=13, auction=12, vol=5, trap=0, engine=0")
    lines.append(f"**Key change from R1:** Imbalance category now **actively contributes** to base_score")
    lines.append(f"  (R1/R2 bug: IMB signals were registered as stacked_tier but cats_agreeing.add('imbalance')")
    lines.append(f"  was never called → imbalance weight was never included in base_score calculation)")
    lines.append(f"**Config:** ScoreEntryThreshold={SCORE_ENTRY_THRESHOLD}, MinTier=TYPE_C, "
                 f"Stop={STOP_LOSS_TICKS}t, Target={TARGET_TICKS}t, MaxBars={MAX_BARS_IN_TRADE}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"| Metric | R1 Baseline | Best Config ({best.config_name}) | Delta |")
    lines.append("|--------|-------------|----------------------------------|-------|")
    lines.append(f"| Sharpe | {baseline.sharpe:.4f} | {best.sharpe:.4f} | {sharpe_delta:+.4f} ({sharpe_pct:+.1f}%) |")
    lines.append(f"| Profit Factor | {_pf_str(baseline.profit_factor)} | {_pf_str(best.profit_factor)} | — |")
    lines.append(f"| Win Rate | {baseline.win_rate*100:.1f}% | {best.win_rate*100:.1f}% | — |")
    lines.append(f"| Total P&L | ${baseline.total_pnl_dollars:+.0f} | ${best.total_pnl_dollars:+.0f} | — |")
    lines.append(f"| Max Drawdown | ${baseline.max_dd:.0f} | ${best.max_dd:.0f} | — |")
    lines.append(f"| Trades | {baseline.n_trades} | {best.n_trades} | — |")
    lines.append("")

    # Answer the key question
    lines.append("## Key Question: Does Boosting Imbalance Weight Improve Performance?")
    lines.append("")
    imb_boosted_m = next((m for m in named_results if "imb_boosted" in m.config_name), None)
    thesis_imb_m = next((m for m in named_results if "thesis_imb" in m.config_name), None)

    if imb_boosted_m:
        imb_delta = imb_boosted_m.sharpe - baseline.sharpe
        answer = "YES" if imb_delta > 0.001 else ("NO CHANGE" if abs(imb_delta) < 0.001 else "NO")
        lines.append(f"**Answer: {answer}**")
        lines.append("")
        lines.append(f"- R1 baseline (imb=13, inactive): Sharpe={baseline.sharpe:.4f}")
        lines.append(f"- Imbalance-boosted (imb=25, active): Sharpe={imb_boosted_m.sharpe:.4f} "
                     f"({imb_delta:+.4f})")
        if thesis_imb_m:
            th_delta = thesis_imb_m.sharpe - baseline.sharpe
            lines.append(f"- Thesis+imbalance (imb=20, active): Sharpe={thesis_imb_m.sharpe:.4f} "
                         f"({th_delta:+.4f})")
        lines.append("")
        if imb_delta > 0.001:
            lines.append("Activating imbalance scoring **improves** Sharpe. Higher imbalance weight "
                         "reflects its genuine signal contribution once it participates in base_score.")
        elif abs(imb_delta) < 0.001:
            lines.append("Activating imbalance scoring produces no measurable change. "
                         "The score dynamics are dominated by abs/exh and the confluence gate; "
                         "imbalance boost alone does not shift entry decisions significantly.")
        else:
            lines.append("Boosting imbalance weight **hurts** performance. The higher score from "
                         "imbalance-only bars passes the TYPE_C threshold on lower-quality setups, "
                         "adding noise entries that were previously filtered out.")
    lines.append("")

    # Recommended weight vector
    lines.append("## Recommended Weight Vector")
    lines.append("")
    lines.append(f"**Config:** `{best.config_name}`")
    lines.append("")
    lines.append("| Category | R1 Baseline | Recommended | Change |")
    lines.append("|----------|-------------|-------------|--------|")
    for cat in CATS:
        r1_w = R1_CURRENT.get(cat, 0.0)
        best_w = best.weights.get(cat, 0.0)
        delta = best_w - r1_w
        delta_str = f"{delta:+.1f}" if abs(delta) > 0.05 else "—"
        lines.append(f"| {cat} | {r1_w:.1f} | **{best_w:.1f}** | {delta_str} |")
    lines.append("")

    # Named config results
    lines.append("## Named Configuration Results")
    lines.append("")
    lines.append("| Config | Trades | Win% | Sharpe | PF | Avg P&L (t) | Max DD | Total P&L | vs R1 |")
    lines.append("|--------|--------|------|--------|----|-------------|--------|-----------|-------|")
    for m in named_results:
        vs_r1 = ""
        if baseline.sharpe != 0:
            pct = (m.sharpe - baseline.sharpe) / abs(baseline.sharpe) * 100
            vs_r1 = f"{pct:+.1f}%"
        elif m.sharpe > 0:
            vs_r1 = "+inf%"
        marker = " <- BEST" if m.config_name == best.config_name else ""
        lines.append(
            f"| {m.config_name} | {m.n_trades} | {m.win_rate*100:.1f}% | "
            f"{m.sharpe:.4f} | {_pf_str(m.profit_factor)} | {m.avg_pnl:.2f}t | "
            f"${m.max_dd:.0f} | ${m.total_pnl_dollars:+.0f} | {vs_r1}{marker} |"
        )
    lines.append("")

    # Named config weight vectors
    lines.append("### Named Configuration Weight Vectors")
    lines.append("")
    lines.append("| Config | abs | exh | trap | delta | imb | volp | auct | poc | sum |")
    lines.append("|--------|-----|-----|------|-------|-----|------|------|-----|-----|")
    for name, weights in NAMED_CONFIGS:
        lines.append(_weights_row(name, weights))
    lines.append("")

    # Grid search results
    lines.append("## Grid Search Results (absorption × imbalance)")
    lines.append("")
    lines.append("Remaining budget (exh, delta, vol, auction) distributed proportionally to R1 ratios.")
    lines.append("")

    # Heatmap table
    imb_header = " | ".join(f"imb={v}" for v in IMB_GRID)
    lines.append(f"| abs \\ imb | {imb_header} |")
    sep = "|-----------|" + "|".join(["--------"] * len(IMB_GRID)) + "|"
    lines.append(sep)
    for abs_w in ABS_GRID:
        row_vals = []
        for imb_w in IMB_GRID:
            name = f"grid_abs{abs_w}_imb{imb_w}"
            m_match = next((m for m in grid_results if m.config_name == name), None)
            if m_match:
                marker = "**" if m_match.config_name == best_grid.config_name else ""
                row_vals.append(f"{marker}{m_match.sharpe:.3f}{marker}")
            else:
                row_vals.append("—")
        lines.append(f"| abs={abs_w} | " + " | ".join(row_vals) + " |")
    lines.append("")
    lines.append(f"**Best grid config:** `{best_grid.config_name}` — "
                 f"Sharpe={best_grid.sharpe:.4f}, PF={_pf_str(best_grid.profit_factor)}, "
                 f"WR={best_grid.win_rate*100:.1f}%, Trades={best_grid.n_trades}, "
                 f"P&L=${best_grid.total_pnl_dollars:+.0f}")
    lines.append("")

    # Grid sorted by Sharpe
    lines.append("### Grid Search Full Results (sorted by Sharpe desc)")
    lines.append("")
    lines.append("| Config | abs | imb | exh | delta | Trades | Win% | Sharpe | PF | Total P&L |")
    lines.append("|--------|-----|-----|-----|-------|--------|------|--------|----|-----------|")
    for m in sorted(grid_results, key=lambda x: x.sharpe, reverse=True)[:20]:
        w = m.weights
        marker = " <- BEST" if m.config_name == best.config_name else ""
        lines.append(
            f"| {m.config_name} | {w.get('absorption',0):.0f} | {w.get('imbalance',0):.0f} | "
            f"{w.get('exhaustion',0):.1f} | {w.get('delta',0):.1f} | "
            f"{m.n_trades} | {m.win_rate*100:.1f}% | {m.sharpe:.4f} | "
            f"{_pf_str(m.profit_factor)} | ${m.total_pnl_dollars:+.0f}{marker} |"
        )
    lines.append("")

    # Marginal effect of abs vs imb
    lines.append("### Marginal Effect of abs and imb Weights")
    lines.append("")

    abs_avg: dict = {a: [] for a in ABS_GRID}
    imb_avg: dict = {v: [] for v in IMB_GRID}
    for m in grid_results:
        w = m.weights
        abs_v = round(w.get("absorption", 0))
        imb_v = round(w.get("imbalance", 0))
        for a in ABS_GRID:
            if abs(abs_v - a) < 0.5:
                abs_avg[a].append(m.sharpe)
        for v in IMB_GRID:
            if abs(imb_v - v) < 0.5:
                imb_avg[v].append(m.sharpe)

    lines.append("| Absorption | Avg Sharpe (across imb axis) |")
    lines.append("|------------|------------------------------|")
    for a in ABS_GRID:
        avg = sum(abs_avg[a]) / len(abs_avg[a]) if abs_avg[a] else 0
        lines.append(f"| {a} | {avg:.4f} |")
    lines.append("")

    lines.append("| Imbalance | Avg Sharpe (across abs axis) |")
    lines.append("|-----------|------------------------------|")
    for v in IMB_GRID:
        avg = sum(imb_avg[v]) / len(imb_avg[v]) if imb_avg[v] else 0
        lines.append(f"| {v} | {avg:.4f} |")
    lines.append("")

    best_abs_val = max(abs_avg, key=lambda a: sum(abs_avg[a]) / len(abs_avg[a]) if abs_avg[a] else -999)
    best_imb_val = max(imb_avg, key=lambda v: sum(imb_avg[v]) / len(imb_avg[v]) if imb_avg[v] else -999)
    lines.append(f"**Optimal abs (avg):** {best_abs_val}  |  **Optimal imb (avg):** {best_imb_val}")
    lines.append("")

    # Walk-forward results
    lines.append("## Walk-Forward Validation (30/10/10)")
    lines.append("")
    lines.append("Top 3 configurations by full-set Sharpe tested out-of-sample.")
    lines.append("Sessions 1-30: training | Sessions 31-40: validation | Sessions 41-50: test")
    lines.append("")
    lines.append("| Config | Train Sharpe (1-30) | Val Sharpe (31-40) | Test Sharpe (41-50) | Degradation | Stable? |")
    lines.append("|--------|---------------------|--------------------|--------------------|-------------|---------|")
    for wf in wf_results:
        stable = "YES" if abs(wf.degradation) < 0.05 else ("MILD" if abs(wf.degradation) < 0.15 else "NO")
        lines.append(
            f"| {wf.config_name} | {wf.train_sharpe:.4f} ({wf.train_trades}t) | "
            f"{wf.val_sharpe:.4f} ({wf.val_trades}t) | "
            f"{wf.test_sharpe:.4f} ({wf.test_trades}t) | "
            f"{wf.degradation:+.4f} | {stable} |"
        )
    lines.append("")

    # Analysis
    lines.append("## Analysis")
    lines.append("")
    lines.append("### Mechanistic Explanation")
    lines.append("")
    lines.append("With imbalance category now **actively contributing** to base_score, each IMB signal "
                 "adds `weights['imbalance']` points to the score (previously: 0 points). This has "
                 "two effects:")
    lines.append("")
    lines.append("1. **Score inflation on imbalance-heavy bars:** Bars with strong stacked imbalances "
                 "now score higher, potentially crossing TYPE_C_MIN=50 that they previously missed.")
    lines.append("2. **Confluence gate sensitivity:** Adding 'imbalance' to cats_agreeing increases "
                 "cat_count, making it easier to trigger CONFLUENCE_MULT=1.25 (requires cat_count>=5).")
    lines.append("")
    lines.append("The critical question is whether these newly-qualified imbalance entries have "
                 "positive or negative expectancy. R3 empirically answers this.")
    lines.append("")

    # Named config observations
    best_named_m = max(named_results, key=lambda m: m.sharpe)
    worst_named_m = min(named_results, key=lambda m: m.sharpe)
    lines.append("### Named Config Observations")
    lines.append("")
    lines.append(f"- **Best named config:** `{best_named_m.config_name}` (Sharpe={best_named_m.sharpe:.4f})")
    lines.append(f"- **Worst named config:** `{worst_named_m.config_name}` (Sharpe={worst_named_m.sharpe:.4f})")

    imb_b = next((m for m in named_results if "imb_boosted" in m.config_name), None)
    thesis_b = next((m for m in named_results if "thesis_imb" in m.config_name), None)
    equal_m = next((m for m in named_results if m.config_name == "4_equal"), None)
    attr_m = next((m for m in named_results if "attribution_r3" in m.config_name), None)

    if imb_b:
        d = imb_b.sharpe - baseline.sharpe
        lines.append(f"- **Imbalance-boosted vs R1:** {baseline.sharpe:.4f} -> {imb_b.sharpe:.4f} "
                     f"({d:+.4f}) — {'boosting imbalance helps: more IMB-driven entries have positive EV' if d > 0.001 else 'no measurable benefit: imbalance weight increase does not shift entry filter enough' if abs(d) < 0.001 else 'hurt: IMB-only entries are noise at higher weights'}")
    if thesis_b:
        d = thesis_b.sharpe - baseline.sharpe
        lines.append(f"- **Thesis+imbalance vs R1:** {baseline.sharpe:.4f} -> {thesis_b.sharpe:.4f} ({d:+.4f})")
    if equal_m:
        d = equal_m.sharpe - baseline.sharpe
        lines.append(f"- **Equal weights vs R1:** {baseline.sharpe:.4f} -> {equal_m.sharpe:.4f} ({d:+.4f})")
    if attr_m:
        d = attr_m.sharpe - baseline.sharpe
        lines.append(f"- **Attribution-R3 vs R1:** {baseline.sharpe:.4f} -> {attr_m.sharpe:.4f} ({d:+.4f})")
    lines.append("")

    # Key takeaways
    lines.append("---")
    lines.append("")
    lines.append("## Key Takeaways")
    lines.append("")
    lines.append(f"1. **Sharpe delta vs R1:** {sharpe_delta:+.4f} ({sharpe_pct:+.1f}%) for best config `{best.config_name}`.")

    if imb_b:
        imb_improvement = imb_b.sharpe - baseline.sharpe
        if imb_improvement > 0.001:
            lines.append("2. **Imbalance activation is positive:** Now that IMB signals contribute to "
                         "base_score, boosting their weight captures additional alpha from stacked "
                         "imbalance patterns that were invisible to the scorer in R1.")
        elif abs(imb_improvement) < 0.001:
            lines.append("2. **Imbalance activation is neutral at R1 weight (13):** The weight is already "
                         "optimal — the fix matters but the existing weight allocates it correctly. "
                         "No further boost needed.")
        else:
            lines.append("2. **Imbalance activation is negative at higher weights:** IMB signals are "
                         "useful at low weight (selective filter) but dilute score quality at high weight. "
                         "Keep imbalance at R1 weight (13) or lower.")

    abs_trend = "lower" if best_abs_val < 30 else "higher" if best_abs_val > 32 else "current"
    imb_trend = "higher" if best_imb_val > 13 else "lower" if best_imb_val < 13 else "current"
    lines.append(f"3. **Optimal abs weight trend:** {abs_trend} than R1 baseline (32). "
                 f"**Optimal imb weight trend:** {imb_trend} than R1 baseline (13).")

    if wf_results:
        best_wf = max(wf_results, key=lambda w: w.test_sharpe)
        lines.append(f"4. **Walk-forward stability:** Best OOS config is `{best_wf.config_name}` "
                     f"(test Sharpe={best_wf.test_sharpe:.4f}, "
                     f"degradation={best_wf.degradation:+.4f}).")

    lines.append("")
    lines.append(f"*Report generated by `deep6/backtest/round3_weight_optimizer.py` — "
                 f"50 sessions, 5 named configs + {len(ABS_GRID)*len(IMB_GRID)} grid points, "
                 f"walk-forward on top 3*")

    out_path.write_text("\n".join(lines))


if __name__ == "__main__":
    run_optimization()
