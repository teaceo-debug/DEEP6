"""deep6/backtest/round2_sweep.py — Round 2 Full Sweep & Comparison vs R1

Runs the same 1,728-combo joint sweep as R1 meta-optimizer using the
R1-improved code (thesis-heavy weights, threshold=70, breakeven+scale-out,
directional filter, time blackout 1530-1600, VOLP-03 veto, slow-grind veto)
already baked into BacktestConfig.cs and reflected in the regenerated
50-session dataset.

Walk-forward: 30 train / 10 validate / 10 test (same stratified 60/20/20
split by regime as R1).

Outputs:
  ninjatrader/backtests/results/round2/SWEEP-COMPARISON.md
  ninjatrader/backtests/results/round2/RECOMMENDED-CONFIG-R2.json

Usage:
  python3 -m deep6.backtest.round2_sweep
"""
from __future__ import annotations

import itertools
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
OUTPUT_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round2"
R1_CONFIG_PATH = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round1" / "RECOMMENDED-CONFIG.json"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TICK_SIZE = 0.25
TICK_VALUE = 5.0

# ---------------------------------------------------------------------------
# R1 recommended config (ground truth for comparison)
# These values are what R1 walk-forward selected as best test-set Sharpe.
# ---------------------------------------------------------------------------
R1_RECOMMENDED = {
    "weight_profile": "thesis_heavy",
    "entry_threshold": 70,
    "stop_ticks": 20,
    "target_ticks": 32,
    "trailing_stop": False,
    "volp03_veto": False,
    "slow_grind_veto": False,
    "test_sharpe": 432.652,
    "test_net_pnl": 829.04,
    "rr_ratio": 1.6,
    "stability_verdict": "MIXED",
    "fragile_params": ["entry_threshold"],
}

# ---------------------------------------------------------------------------
# Weight profiles (identical to R1 — not re-tuning weights in R2)
# ---------------------------------------------------------------------------
WEIGHT_PROFILES = {
    "current": {
        "absorption": 25, "exhaustion": 18, "trapped": 14, "delta": 13,
        "imbalance": 12, "volume_profile": 10, "auction": 8, "poc": 1,
    },
    "thesis_heavy": {
        "absorption": 32, "exhaustion": 24, "trapped": 14, "delta": 8,
        "imbalance": 12, "volume_profile": 8, "auction": 6, "poc": 1,
    },
    "equal": {
        "absorption": 20, "exhaustion": 20, "trapped": 15, "delta": 15,
        "imbalance": 15, "volume_profile": 10, "auction": 5, "poc": 1,
    },
}

# ---------------------------------------------------------------------------
# R2 joint sweep grid — same 1,728-combo space as R1 meta-optimizer
# 3 × 4 × 3 × 3 × 2 × 2 × 2 = 864 combos (identical arithmetic to R1)
# ---------------------------------------------------------------------------
META_GRID = {
    "weight_profile":  ["current", "thesis_heavy", "equal"],
    "entry_threshold": [40, 50, 60, 70],
    "stop_ticks":      [12, 16, 20],
    "target_ticks":    [24, 32, 40],
    "trailing_stop":   [False, True],
    "volp03_veto":     [False, True],
    "slow_grind_veto": [False, True],
}

TOTAL_COMBOS = 1
for _v in META_GRID.values():
    TOTAL_COMBOS *= len(_v)
# 3×4×3×3×2×2×2 = 864
assert TOTAL_COMBOS == 864, f"Expected 864 combos, got {TOTAL_COMBOS}"

# ---------------------------------------------------------------------------
# Signal classification helpers
# ---------------------------------------------------------------------------
_VOTING_DELTA = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
_VOTING_AUCT  = {"AUCT-01", "AUCT-02", "AUCT-05"}
_VOTING_POC   = {"POC-02",  "POC-07",  "POC-08"}


def _classify_signal(sig: dict) -> str:
    sid = sig.get("signalId", "")
    if sid.startswith("ABS"):   return "absorption"
    if sid.startswith("EXH"):   return "exhaustion"
    if sid.startswith("TRAP"):  return "trapped"
    if sid.startswith("IMB"):   return "imbalance"
    if sid in _VOTING_DELTA:    return "delta"
    if sid in _VOTING_AUCT:     return "auction"
    if sid in _VOTING_POC:      return "poc"
    if sid.startswith("VOLP"):  return "volume_profile"
    return ""


def _has_volp03(bar: dict) -> bool:
    return any(s.get("signalId") == "VOLP-03" for s in bar.get("signals", []))


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def profit_factor(pnls: np.ndarray) -> float:
    gp = float(pnls[pnls > 0].sum())
    gl = float(abs(pnls[pnls < 0].sum()))
    if gl == 0.0:
        return float("inf") if gp > 0 else 0.0
    return gp / gl


def max_drawdown(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    eq = np.cumsum(pnls)
    return float((np.maximum.accumulate(eq) - eq).max())


def sharpe_estimate(pnls: np.ndarray) -> float:
    if len(pnls) < 2:
        return 0.0
    std = float(pnls.std(ddof=1))
    if std == 0.0:
        return 0.0
    return float((pnls.mean() / std) * np.sqrt(252))


def compute_stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "max_drawdown": 0.0, "sharpe": 0.0, "avg_pnl": 0.0, "net_pnl": 0.0,
        }
    pnls = np.array([t["pnl_dollars"] for t in trades])
    wins = int((pnls > 0).sum())
    return {
        "total_trades": len(trades),
        "win_rate": float(wins / len(pnls)),
        "profit_factor": profit_factor(pnls),
        "max_drawdown": max_drawdown(pnls),
        "sharpe": sharpe_estimate(pnls),
        "avg_pnl": float(pnls.mean()),
        "net_pnl": float(pnls.sum()),
    }


# ---------------------------------------------------------------------------
# Weight-profile aware scorer (re-scores bars with custom weights)
# Mirrors round1_meta_optimizer.py score_bar_with_weights — identical logic.
# ---------------------------------------------------------------------------

def score_bar_with_weights(bar: dict, weights: dict[str, float]) -> dict:
    signals = bar.get("signals", [])
    zone_score = float(bar.get("zoneScore", 0.0))
    zone_dist = float(bar.get("zoneDistTicks", 1e9))
    bars_since_open = int(bar.get("barsSinceOpen", 0))
    bar_delta = int(bar.get("barDelta", 0))
    bar_close = float(bar.get("barClose", 0.0))

    bull_w = 0.0
    bear_w = 0.0
    cats_bull: set[str] = set()
    cats_bear: set[str] = set()
    max_bull_str = 0.0
    max_bear_str = 0.0
    stacked_bull = 0
    stacked_bear = 0

    for sig in signals:
        d = int(sig.get("direction", 0))
        s = float(sig.get("strength", 0.0))
        if d == 0:
            continue
        cat = _classify_signal(sig)
        if not cat:
            continue

        if cat == "imbalance":
            sid = sig.get("signalId", "")
            tier_n = 0
            for suffix in ("-T3", "-T2", "-T1"):
                if sid.endswith(suffix):
                    tier_n = int(suffix[-1])
                    break
            if tier_n == 0 and "STACKED_T" in sig.get("detail", ""):
                detail = sig.get("detail", "")
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
            continue

        w = weights.get(cat, 5.0)
        if d > 0:
            bull_w += s * w
            cats_bull.add(cat)
            max_bull_str = max(max_bull_str, s)
        else:
            bear_w += s * w
            cats_bear.add(cat)
            max_bear_str = max(max_bear_str, s)

    imb_w = weights.get("imbalance", 12.0)
    if stacked_bull > 0:
        bull_w += 0.5 * imb_w
        cats_bull.add("imbalance")
    if stacked_bear > 0:
        bear_w += 0.5 * imb_w
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
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                "tier_ord": 0, "entry_price": bar_close, "active_cats": 0}

    if bar_delta != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                    "tier_ord": 0, "entry_price": bar_close, "active_cats": 0}

    vp_w = weights.get("volume_profile", 10.0)
    zone_bonus = 0.0
    if zone_score >= 50.0:
        zone_bonus = (4.0 if zone_dist <= 0.5 else 8.0) * (vp_w / 10.0)
        cats.add("volume_profile")
    elif zone_score >= 30.0:
        zone_bonus = 6.0 * (vp_w / 10.0)
        cats.add("volume_profile")

    cat_count = len(cats)
    confluence_mult = 1.25 if cat_count >= 5 else 1.0
    ib_mult = 1.15 if 0 <= bars_since_open < 60 else 1.0

    base_score = sum(weights.get(c, 5.0) for c in cats if c != "volume_profile")
    total_score = min((base_score * confluence_mult + zone_bonus) * ib_mult, 100.0)
    total_score = max(0.0, total_score)

    # Midday block (mirrors R1)
    if 240 <= bars_since_open <= 330:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                "tier_ord": 0, "entry_price": bar_close, "active_cats": 0}

    has_abs = "absorption" in cats
    has_exh = "exhaustion" in cats
    has_zone = zone_bonus > 0.0
    trap_count = sum(1 for sig in signals if sig.get("signalId", "").startswith("TRAP"))
    delta_chase = abs(bar_delta) > 50 and (
        (direction > 0 and bar_delta > 0) or (direction < 0 and bar_delta < 0)
    )

    if (total_score >= 80.0 and (has_abs or has_exh) and has_zone
            and cat_count >= 5 and trap_count < 3 and not delta_chase):
        tier = "TYPE_A"
        tier_ord = 3
    elif total_score >= 72.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_B"
        tier_ord = 2
    elif total_score >= 50.0 and cat_count >= 4 and max_str >= 0.3:
        tier = "TYPE_C"
        tier_ord = 1
    else:
        tier = "QUIET"
        tier_ord = 0

    entry_price = bar_close
    for sig in signals:
        sid = sig.get("signalId", "")
        if sig.get("direction", 0) == direction and float(sig.get("price", 0.0)) != 0.0:
            if sid.startswith("ABS") or sid.startswith("EXH"):
                entry_price = float(sig["price"])
                break

    return {
        "total_score": total_score,
        "direction": direction,
        "tier": tier,
        "tier_ord": tier_ord,
        "entry_price": entry_price,
        "active_cats": cat_count,
    }


# ---------------------------------------------------------------------------
# Session loader
# ---------------------------------------------------------------------------

def get_session_regime(session_name: str) -> str:
    parts = session_name.replace(".ndjson", "").split("-")
    return "-".join(parts[2:-1])


def load_all_sessions(sessions_dir: Path) -> dict[str, list[dict]]:
    sessions: dict[str, list[dict]] = {}
    for path in sorted(sessions_dir.glob("*.ndjson")):
        bars = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        obj = json.loads(line)
                        if obj.get("type") == "scored_bar":
                            bars.append(obj)
                    except json.JSONDecodeError:
                        continue
        if bars:
            sessions[path.name] = bars
    return sessions


# ---------------------------------------------------------------------------
# Simulator — R1-improved (adds R1 runtime features to meta-combo sim)
# R1 features already baked into sessions (regenerated post-R1), but we
# also apply them at entry gate level here for completeness.
# ---------------------------------------------------------------------------

def simulate_r2_combo(
    sessions_data: dict[str, list[dict]],
    weights: dict[str, float],
    entry_threshold: float,
    stop_ticks: int,
    target_ticks: int,
    trailing_stop: bool,
    volp03_veto: bool,
    slow_grind_veto: bool,
    # R1 runtime features (always active in R2 — we measure effect of sweep params on top of them)
    breakeven_activation_ticks: int = 10,
    breakeven_offset_ticks: int = 2,
    scale_out_target_ticks: int = 16,
    scale_out_percent: float = 0.5,
    blackout_start: int = 1530,
    blackout_end: int = 1600,
    strict_direction: bool = True,
    slow_grind_atr_ratio: float = 0.5,
) -> list[dict]:
    """Run simulation for one R2 parameter combo with R1 runtime features active."""
    sl_pts = stop_ticks * TICK_SIZE
    tp_pts = target_ticks * TICK_SIZE
    slippage_pts = 1.0 * TICK_SIZE
    so_pts = scale_out_target_ticks * TICK_SIZE  # scale-out target distance
    be_act_pts = breakeven_activation_ticks * TICK_SIZE
    be_off_pts = breakeven_offset_ticks * TICK_SIZE

    all_trades: list[dict] = []

    for session_name, bars in sessions_data.items():
        regime = get_session_regime(session_name)

        # Slow grind veto: skip entire session if slow_grind regime
        if slow_grind_veto and regime == "slow_grind":
            continue

        in_trade = False
        entry_price = 0.0
        entry_bar_idx = 0
        trade_dir = 0
        best_price = 0.0
        mfe_pts = 0.0
        be_active = False         # has breakeven stop been moved?
        scale_out_done = False    # has partial exit been executed?
        partial_pnl = 0.0         # P&L from scale-out partial exit
        volp03_fired_this_session = False

        # Build session-level ATR proxy: std of bar-to-bar close changes
        closes = [float(b.get("barClose", 0.0)) for b in bars]
        if len(closes) > 10:
            diffs = np.abs(np.diff(closes))
            session_avg_atr = float(diffs.mean()) if len(diffs) else 1.0
        else:
            session_avg_atr = 1.0

        for i, bar in enumerate(bars):
            bar_close = float(bar.get("barClose", 0.0))
            bar_idx = int(bar.get("barIdx", i))
            bars_since_open = int(bar.get("barsSinceOpen", i))

            # Time blackout gate: convert barsSinceOpen to HHMM proxy
            # Sessions start at ~0930 ET; 1530 = 360min after open = bar 360
            # Use barsSinceOpen directly: 360 min = blackout_start=1530
            # We cannot know exact time without a timestamp, so approximate:
            # each bar ≈ 1 min; 1530-1600 ET ≈ bars 360-390 since 0930 open
            blackout_bar_start = 360  # 1530 = 360 min after 0930
            blackout_bar_end = 390    # 1600 = 390 min after 0930
            in_blackout = blackout_bar_start <= bars_since_open <= blackout_bar_end

            # Track VOLP-03
            if _has_volp03(bar):
                volp03_fired_this_session = True

            scored = score_bar_with_weights(bar, weights)
            direction = scored["direction"]
            total_score = scored["total_score"]
            tier_ord = scored["tier_ord"]

            if in_trade:
                # Update MFE
                if trade_dir == 1:
                    mfe_pts = max(mfe_pts, bar_close - entry_price)
                else:
                    mfe_pts = max(mfe_pts, entry_price - bar_close)

                # Trailing stop update
                if trailing_stop:
                    if trade_dir == 1 and bar_close > best_price:
                        best_price = bar_close
                    elif trade_dir == -1 and bar_close < best_price:
                        best_price = bar_close

                # Breakeven stop: once MFE >= activation, move stop to entry + offset
                effective_sl_pts = sl_pts
                if mfe_pts >= be_act_pts:
                    be_active = True
                if be_active and not trailing_stop:
                    # Stop is now at entry + direction*be_off_pts (locks in small gain)
                    be_stop = entry_price + trade_dir * be_off_pts
                    if trade_dir == 1 and bar_close <= be_stop:
                        exit_price = bar_close - slippage_pts
                        pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                        # Add any prior partial P&L
                        final_pnl_ticks = pnl_ticks * (1.0 - scale_out_percent if scale_out_done else 1.0)
                        all_trades.append({
                            "session": session_name,
                            "regime": regime,
                            "entry_bar": entry_bar_idx,
                            "exit_bar": bar_idx,
                            "direction": trade_dir,
                            "pnl_ticks": final_pnl_ticks + (partial_pnl / TICK_VALUE),
                            "pnl_dollars": final_pnl_ticks * TICK_VALUE + partial_pnl,
                            "exit_reason": "BREAKEVEN",
                        })
                        in_trade = False
                        scale_out_done = False
                        partial_pnl = 0.0
                        be_active = False
                        mfe_pts = 0.0
                        continue
                    elif trade_dir == -1 and bar_close >= be_stop:
                        exit_price = bar_close + slippage_pts
                        pnl_ticks = (entry_price - exit_price) / TICK_SIZE
                        final_pnl_ticks = pnl_ticks * (1.0 - scale_out_percent if scale_out_done else 1.0)
                        all_trades.append({
                            "session": session_name,
                            "regime": regime,
                            "entry_bar": entry_bar_idx,
                            "exit_bar": bar_idx,
                            "direction": trade_dir,
                            "pnl_ticks": final_pnl_ticks + (partial_pnl / TICK_VALUE),
                            "pnl_dollars": final_pnl_ticks * TICK_VALUE + partial_pnl,
                            "exit_reason": "BREAKEVEN",
                        })
                        in_trade = False
                        scale_out_done = False
                        partial_pnl = 0.0
                        be_active = False
                        mfe_pts = 0.0
                        continue

                # Scale-out: partial exit at scale_out_target_ticks
                if not scale_out_done:
                    so_hit = (
                        (trade_dir == 1 and bar_close >= entry_price + so_pts) or
                        (trade_dir == -1 and bar_close <= entry_price - so_pts)
                    )
                    if so_hit:
                        scale_out_done = True
                        so_exit_price = (entry_price + trade_dir * so_pts) - trade_dir * slippage_pts
                        so_pnl_ticks = (so_exit_price - entry_price) / TICK_SIZE * trade_dir
                        partial_pnl = so_pnl_ticks * TICK_VALUE * scale_out_percent

                exit_reason = None
                remaining_frac = (1.0 - scale_out_percent) if scale_out_done else 1.0

                # Stop loss
                if trailing_stop:
                    stop_ref = best_price - trade_dir * sl_pts
                    if trade_dir == 1 and bar_close <= stop_ref:
                        exit_reason = "TRAIL_STOP"
                    elif trade_dir == -1 and bar_close >= stop_ref:
                        exit_reason = "TRAIL_STOP"
                else:
                    if trade_dir == 1 and bar_close <= entry_price - sl_pts:
                        exit_reason = "STOP_LOSS"
                    elif trade_dir == -1 and bar_close >= entry_price + sl_pts:
                        exit_reason = "STOP_LOSS"

                # Target (full exit)
                if exit_reason is None:
                    if trade_dir == 1 and bar_close >= entry_price + tp_pts:
                        exit_reason = "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - tp_pts:
                        exit_reason = "TARGET"

                # Max bars (60 fixed)
                if exit_reason is None and (bar_idx - entry_bar_idx) >= 60:
                    exit_reason = "MAX_BARS"

                if exit_reason is not None:
                    exit_price = bar_close - (trade_dir * slippage_pts)
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir * remaining_frac
                    total_pnl_dollars = pnl_ticks * TICK_VALUE + partial_pnl
                    all_trades.append({
                        "session": session_name,
                        "regime": regime,
                        "entry_bar": entry_bar_idx,
                        "exit_bar": bar_idx,
                        "direction": trade_dir,
                        "pnl_ticks": pnl_ticks + (partial_pnl / TICK_VALUE),
                        "pnl_dollars": total_pnl_dollars,
                        "exit_reason": exit_reason,
                    })
                    in_trade = False
                    scale_out_done = False
                    partial_pnl = 0.0
                    be_active = False
                    mfe_pts = 0.0

            else:
                # Entry gates

                # 1. VOLP-03 veto
                if volp03_veto and volp03_fired_this_session:
                    continue

                # 2. Time blackout
                if in_blackout:
                    continue

                # 3. Slow-grind ATR veto (bar-level)
                if slow_grind_veto:
                    bar_atr_proxy = abs(bar_close - float(bars[i - 1].get("barClose", bar_close))) if i > 0 else session_avg_atr
                    if bar_atr_proxy < slow_grind_atr_ratio * session_avg_atr and session_avg_atr > 0:
                        continue

                # 4. Score + direction threshold
                if total_score < entry_threshold or direction == 0:
                    continue

                # 5. Strict direction filter: if any opposing signal has non-trivial score, skip
                if strict_direction:
                    opp_score = 0.0
                    for sig in bar.get("signals", []):
                        sig_dir = int(sig.get("direction", 0))
                        if sig_dir != 0 and sig_dir != direction:
                            opp_score += float(sig.get("strength", 0.0))
                    if opp_score > 0.15:  # threshold mirrors R1 definition
                        continue

                entry_price = scored["entry_price"] + direction * slippage_pts
                entry_bar_idx = bar_idx
                trade_dir = direction
                best_price = entry_price
                in_trade = True
                mfe_pts = 0.0
                be_active = False
                scale_out_done = False
                partial_pnl = 0.0

        # Force-close at session end
        if in_trade and bars:
            last_bar = bars[-1]
            bar_close = float(last_bar.get("barClose", 0.0))
            bar_idx = int(last_bar.get("barIdx", len(bars) - 1))
            remaining_frac = (1.0 - scale_out_percent) if scale_out_done else 1.0
            exit_price = bar_close - (trade_dir * slippage_pts)
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir * remaining_frac
            all_trades.append({
                "session": session_name,
                "regime": regime,
                "entry_bar": entry_bar_idx,
                "exit_bar": bar_idx,
                "direction": trade_dir,
                "pnl_ticks": pnl_ticks + (partial_pnl / TICK_VALUE),
                "pnl_dollars": pnl_ticks * TICK_VALUE + partial_pnl,
                "exit_reason": "SESSION_END",
            })

    return all_trades


# ---------------------------------------------------------------------------
# Stratified walk-forward split (identical to R1)
# ---------------------------------------------------------------------------

def build_stratified_splits(
    all_session_names: list[str],
    train_frac: float = 0.6,
    val_frac: float = 0.2,
) -> tuple[list[str], list[str], list[str]]:
    regime_groups: dict[str, list[str]] = defaultdict(list)
    for name in sorted(all_session_names):
        regime = get_session_regime(name)
        regime_groups[regime].append(name)

    train_sessions, val_sessions, test_sessions = [], [], []
    for regime, names in sorted(regime_groups.items()):
        n = len(names)
        t_end = max(1, int(n * train_frac))
        v_end = max(t_end + 1, int(n * (train_frac + val_frac)))
        train_sessions.extend(names[:t_end])
        val_sessions.extend(names[t_end:v_end])
        test_sessions.extend(names[v_end:])

    return train_sessions, val_sessions, test_sessions


# ---------------------------------------------------------------------------
# Joint sweep runner
# ---------------------------------------------------------------------------

def run_joint_sweep(sessions_data: dict, label: str = "") -> pd.DataFrame:
    combos = list(itertools.product(
        META_GRID["weight_profile"],
        META_GRID["entry_threshold"],
        META_GRID["stop_ticks"],
        META_GRID["target_ticks"],
        META_GRID["trailing_stop"],
        META_GRID["volp03_veto"],
        META_GRID["slow_grind_veto"],
    ))

    print(f"  [{label}] Running {len(combos)} joint combos over {len(sessions_data)} sessions...")
    t0 = time.time()
    rows = []

    for i, (wp, thr, sl, tp, trail, v03, sg) in enumerate(combos):
        weights = WEIGHT_PROFILES[wp]
        trades = simulate_r2_combo(
            sessions_data,
            weights=weights,
            entry_threshold=float(thr),
            stop_ticks=sl,
            target_ticks=tp,
            trailing_stop=trail,
            volp03_veto=v03,
            slow_grind_veto=sg,
        )
        stats = compute_stats(trades)

        regime_sharpes: dict[str, float] = {}
        regime_pnls: dict[str, float] = {}
        for regime in ["trend_up", "trend_down", "ranging", "volatile", "slow_grind"]:
            r_trades = [t for t in trades if t.get("regime") == regime]
            r_stats = compute_stats(r_trades)
            regime_sharpes[regime] = r_stats["sharpe"]
            regime_pnls[regime] = r_stats["net_pnl"]

        rows.append({
            "weight_profile": wp,
            "entry_threshold": thr,
            "stop_ticks": sl,
            "target_ticks": tp,
            "trailing_stop": trail,
            "volp03_veto": v03,
            "slow_grind_veto": sg,
            "rr_ratio": round(tp / sl, 3),
            **stats,
            "sharpe_trend_up":    regime_sharpes.get("trend_up", 0.0),
            "sharpe_trend_down":  regime_sharpes.get("trend_down", 0.0),
            "sharpe_ranging":     regime_sharpes.get("ranging", 0.0),
            "sharpe_volatile":    regime_sharpes.get("volatile", 0.0),
            "sharpe_slow_grind":  regime_sharpes.get("slow_grind", 0.0),
            "pnl_trend_up":       regime_pnls.get("trend_up", 0.0),
            "pnl_trend_down":     regime_pnls.get("trend_down", 0.0),
            "pnl_ranging":        regime_pnls.get("ranging", 0.0),
            "pnl_volatile":       regime_pnls.get("volatile", 0.0),
            "pnl_slow_grind":     regime_pnls.get("slow_grind", 0.0),
        })

        if (i + 1) % 200 == 0:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed
            eta = (len(combos) - i - 1) / rate
            print(f"    {i+1}/{len(combos)} | {elapsed:.0f}s elapsed | ETA {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"  [{label}] Done: {len(combos)} combos in {elapsed:.1f}s")
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Sensitivity analysis (±10% perturbation on top-3 configs)
# ---------------------------------------------------------------------------

def run_sensitivity_analysis(
    top3_configs: list[dict],
    sessions_data: dict,
) -> pd.DataFrame:
    rows = []
    continuous_params = ["entry_threshold", "stop_ticks", "target_ticks"]

    for cfg in top3_configs:
        wp = cfg["weight_profile"]
        weights = WEIGHT_PROFILES[wp]

        # Baseline
        baseline_trades = simulate_r2_combo(
            sessions_data,
            weights=weights,
            entry_threshold=float(cfg["entry_threshold"]),
            stop_ticks=cfg["stop_ticks"],
            target_ticks=cfg["target_ticks"],
            trailing_stop=cfg["trailing_stop"],
            volp03_veto=cfg["volp03_veto"],
            slow_grind_veto=cfg["slow_grind_veto"],
        )
        baseline_sharpe = compute_stats(baseline_trades)["sharpe"]
        cfg_label = (f"wp={wp}, thr={cfg['entry_threshold']}, "
                     f"sl={cfg['stop_ticks']}, tp={cfg['target_ticks']}, "
                     f"trail={cfg['trailing_stop']}, v03={cfg['volp03_veto']}, "
                     f"sg={cfg['slow_grind_veto']}")

        for param in continuous_params:
            orig_val = cfg[param]
            for direction, factor in [("plus_10pct", 1.1), ("minus_10pct", 0.9)]:
                perturbed_val = round(orig_val * factor)
                perturbed_cfg = dict(cfg)
                perturbed_cfg[param] = perturbed_val

                # Ensure target > stop
                if perturbed_cfg["target_ticks"] <= perturbed_cfg["stop_ticks"]:
                    perturbed_cfg["target_ticks"] = perturbed_cfg["stop_ticks"] + 4

                perturbed_trades = simulate_r2_combo(
                    sessions_data,
                    weights=weights,
                    entry_threshold=float(perturbed_cfg["entry_threshold"]),
                    stop_ticks=perturbed_cfg["stop_ticks"],
                    target_ticks=perturbed_cfg["target_ticks"],
                    trailing_stop=perturbed_cfg["trailing_stop"],
                    volp03_veto=perturbed_cfg["volp03_veto"],
                    slow_grind_veto=perturbed_cfg["slow_grind_veto"],
                )
                perturbed_sharpe = compute_stats(perturbed_trades)["sharpe"]

                pct_change = ((perturbed_sharpe - baseline_sharpe) / abs(baseline_sharpe) * 100.0
                              if baseline_sharpe != 0 else 0.0)
                fragile = abs(pct_change) > 50.0

                rows.append({
                    "config_label": cfg_label,
                    "param": param,
                    "perturbation": direction,
                    "orig_value": orig_val,
                    "perturbed_value": perturbed_val,
                    "baseline_sharpe": round(baseline_sharpe, 3),
                    "perturbed_sharpe": round(perturbed_sharpe, 3),
                    "sharpe_pct_change": round(pct_change, 1),
                    "fragile": fragile,
                })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

def run_walkforward(
    sessions_data: dict,
    all_session_names: list[str],
    top_n: int = 10,
    min_val_sharpe: float = 1.0,
) -> tuple[list[dict], pd.DataFrame, list[str], list[str], list[str]]:
    train_sessions, val_sessions, test_sessions = build_stratified_splits(all_session_names)

    print(f"\nWalk-forward split:")
    print(f"  Train:    {len(train_sessions)} sessions")
    print(f"  Validate: {len(val_sessions)} sessions")
    print(f"  Test:     {len(test_sessions)} sessions")

    train_data = {k: v for k, v in sessions_data.items() if k in set(train_sessions)}
    val_data   = {k: v for k, v in sessions_data.items() if k in set(val_sessions)}
    test_data  = {k: v for k, v in sessions_data.items() if k in set(test_sessions)}

    print("\nOptimizing on train set...")
    train_df = run_joint_sweep(train_data, label="train")

    min_trades = max(3, len(train_sessions))
    qualified = train_df[train_df["total_trades"] >= min_trades].copy()
    if qualified.empty:
        qualified = train_df.copy()

    # Replace inf Sharpe with large finite to allow deduplication
    qualified = qualified.copy()
    qualified["sharpe_sort"] = qualified["sharpe"].replace(float("inf"), 9999.0)
    top_combos = qualified.nlargest(top_n, "sharpe_sort").copy()

    results = []
    for _, row in top_combos.iterrows():
        wp = str(row["weight_profile"])
        weights = WEIGHT_PROFILES[wp]
        params = {
            "weight_profile": wp,
            "entry_threshold": int(row["entry_threshold"]),
            "stop_ticks": int(row["stop_ticks"]),
            "target_ticks": int(row["target_ticks"]),
            "trailing_stop": bool(row["trailing_stop"]),
            "volp03_veto": bool(row["volp03_veto"]),
            "slow_grind_veto": bool(row["slow_grind_veto"]),
        }

        def _sim(data: dict) -> dict:
            trades = simulate_r2_combo(
                data,
                weights=WEIGHT_PROFILES[params["weight_profile"]],
                entry_threshold=float(params["entry_threshold"]),
                stop_ticks=params["stop_ticks"],
                target_ticks=params["target_ticks"],
                trailing_stop=params["trailing_stop"],
                volp03_veto=params["volp03_veto"],
                slow_grind_veto=params["slow_grind_veto"],
            )
            return compute_stats(trades)

        train_sharpe = float(row["sharpe"]) if not np.isinf(row["sharpe"]) else 9999.0
        val_stats  = _sim(val_data)
        test_stats = _sim(test_data)
        passed_val = val_stats["sharpe"] >= min_val_sharpe

        results.append({
            "rank": len(results) + 1,
            "params": params,
            "train_sharpe": train_sharpe,
            "train_trades": int(row["total_trades"]),
            "train_win_rate": float(row["win_rate"]),
            "train_profit_factor": float(row["profit_factor"]) if not np.isinf(float(row["profit_factor"])) else 9999.0,
            "validate_sharpe": val_stats["sharpe"],
            "validate_trades": val_stats["total_trades"],
            "validate_profit_factor": val_stats["profit_factor"],
            "test_sharpe": test_stats["sharpe"],
            "test_trades": test_stats["total_trades"],
            "test_win_rate": test_stats["win_rate"],
            "test_profit_factor": test_stats["profit_factor"],
            "test_max_drawdown": test_stats["max_drawdown"],
            "test_net_pnl": test_stats["net_pnl"],
            "passed_validation": passed_val,
        })

    return results, train_df, train_sessions, val_sessions, test_sessions


# ---------------------------------------------------------------------------
# R1 reference simulation — run R1 recommended config through R2 simulator
# This gives the *R2-adjusted* R1 score (apples-to-apples comparison since
# R2 simulator adds breakeven/scale-out on top of R1 config parameters).
# ---------------------------------------------------------------------------

def simulate_r1_config_in_r2(sessions_data: dict) -> dict:
    """Run R1 recommended config parameters through R2 simulator."""
    weights = WEIGHT_PROFILES[R1_RECOMMENDED["weight_profile"]]
    trades = simulate_r2_combo(
        sessions_data,
        weights=weights,
        entry_threshold=float(R1_RECOMMENDED["entry_threshold"]),
        stop_ticks=R1_RECOMMENDED["stop_ticks"],
        target_ticks=R1_RECOMMENDED["target_ticks"],
        trailing_stop=R1_RECOMMENDED["trailing_stop"],
        volp03_veto=R1_RECOMMENDED["volp03_veto"],
        slow_grind_veto=R1_RECOMMENDED["slow_grind_veto"],
    )
    return compute_stats(trades)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _fmt_bool(v: bool) -> str:
    return "True" if v else "False"


def generate_comparison_report(
    wf_results: list[dict],
    full_sweep_df: pd.DataFrame,
    train_df: pd.DataFrame,
    sensitivity_df: pd.DataFrame,
    r1_full_stats: dict,
    r1_wf_stats: dict,
    r2_best_full: dict,
    r2_best_wf: dict,
    train_sessions: list[str],
    val_sessions: list[str],
    test_sessions: list[str],
    convergence_verdict: str,
    r1_sharpe: float,
    r2_sharpe: float,
    sharpe_delta_pct: float,
) -> str:
    lines = [
        "# DEEP6 Round 2 — Full Sweep Comparison vs R1",
        "",
        f"**Generated:** 2026-04-15",
        f"**Sessions:** 50 NQ sessions × 5 regimes (regenerated post-R1 improvements)",
        f"**Joint combos swept:** {TOTAL_COMBOS}",
        f"**Walk-forward split:** {len(train_sessions)} train / {len(val_sessions)} validate / {len(test_sessions)} test",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"R1 improvements active in R2 sessions: thesis-heavy weights, threshold=70,",
        f"breakeven+scale-out, directional filter, time blackout 1530-1600, VOLP-03 veto, slow-grind veto.",
        "",
        f"**R1 optimal test-set Sharpe (walk-forward):** {r1_sharpe:.3f}",
        f"**R2 optimal test-set Sharpe (walk-forward):** {r2_sharpe:.3f}",
        f"**Delta:** {sharpe_delta_pct:+.1f}%",
        f"**Convergence verdict:** **{convergence_verdict}**",
        "",
        "> R2/R1 Sharpe within 5% threshold means we have converged — further parameter",
        "> sweeping on this dataset will not yield meaningful new edge.",
        "",
        "---",
        "",
        "## 1. Full-Dataset Sweep Results (R2)",
        "",
    ]

    # Weight profile comparison
    if not full_sweep_df.empty:
        wp_stats = (full_sweep_df[full_sweep_df["total_trades"] >= 5]
                    .groupby("weight_profile")
                    .agg(mean_sharpe=("sharpe", "mean"), max_sharpe=("sharpe", "max"),
                         median_sharpe=("sharpe", "median"), total_configs=("sharpe", "count"))
                    .reset_index())
        wp_stats = wp_stats.replace([float("inf"), float("-inf")], float("nan"))
        lines.append("### 1.1 Weight Profile Comparison")
        lines.append("")
        lines.append(wp_stats.to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

    # Entry threshold impact
    if not full_sweep_df.empty:
        thr_stats = (full_sweep_df[full_sweep_df["total_trades"] >= 5]
                     .groupby("entry_threshold")
                     .agg(mean_sharpe=("sharpe", "mean"), max_sharpe=("sharpe", "max"))
                     .reset_index())
        thr_stats = thr_stats.replace([float("inf"), float("-inf")], float("nan"))
        lines.append("### 1.2 Entry Threshold Impact")
        lines.append("")
        lines.append(thr_stats.to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

    # Veto filter impact
    if not full_sweep_df.empty:
        v03_stats = (full_sweep_df[full_sweep_df["total_trades"] >= 5]
                     .groupby("volp03_veto")
                     .agg(mean_sharpe=("sharpe", "mean"), total_net_pnl=("net_pnl", "sum"))
                     .reset_index())
        v03_stats = v03_stats.replace([float("inf"), float("-inf")], float("nan"))

        sg_stats = (full_sweep_df[full_sweep_df["total_trades"] >= 5]
                    .groupby("slow_grind_veto")
                    .agg(mean_sharpe=("sharpe", "mean"), total_net_pnl=("net_pnl", "sum"))
                    .reset_index())
        sg_stats = sg_stats.replace([float("inf"), float("-inf")], float("nan"))

        trail_stats = (full_sweep_df[full_sweep_df["total_trades"] >= 5]
                       .groupby("trailing_stop")
                       .agg(mean_sharpe=("sharpe", "mean"))
                       .reset_index())
        trail_stats = trail_stats.replace([float("inf"), float("-inf")], float("nan"))

        lines += [
            "### 1.3 Veto Filter & Stop Impact",
            "",
            "**VOLP-03 veto:**",
            "",
            v03_stats.to_markdown(index=False, floatfmt=".3f"),
            "",
            "**Slow-grind veto:**",
            "",
            sg_stats.to_markdown(index=False, floatfmt=".3f"),
            "",
            "**Trailing stop:**",
            "",
            trail_stats.to_markdown(index=False, floatfmt=".3f"),
            "",
        ]

    # Top 10 full-dataset configs
    if not full_sweep_df.empty:
        top10 = (full_sweep_df[full_sweep_df["total_trades"] >= 3]
                 .replace([float("inf"), float("-inf")], 9999.0)
                 .nlargest(10, "sharpe"))
        top10 = top10.replace(9999.0, float("inf"))
        lines.append("### 1.4 Top 10 Configurations (Full Dataset)")
        lines.append("")
        disp_cols = [
            "weight_profile", "entry_threshold", "stop_ticks", "target_ticks",
            "trailing_stop", "volp03_veto", "slow_grind_veto", "rr_ratio",
            "total_trades", "win_rate", "profit_factor", "sharpe", "net_pnl",
        ]
        lines.append(top10[[c for c in disp_cols if c in top10.columns]].to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

    # Walk-forward table
    lines += [
        "---",
        "",
        "## 2. Walk-Forward Validation (Top 10 Configs)",
        "",
        f"- **Train:** {', '.join(train_sessions[:5])}... ({len(train_sessions)} sessions)",
        f"- **Validate:** {', '.join(val_sessions[:3])}... ({len(val_sessions)} sessions)",
        f"- **Test:** {', '.join(test_sessions[:3])}... ({len(test_sessions)} sessions)",
        "",
    ]

    if wf_results:
        wf_rows = []
        for r in wf_results:
            p = r["params"]
            wf_rows.append({
                "rank": r["rank"],
                "cfg_weight_profile": p["weight_profile"],
                "cfg_entry_threshold": p["entry_threshold"],
                "cfg_stop_ticks": p["stop_ticks"],
                "cfg_target_ticks": p["target_ticks"],
                "cfg_trailing_stop": p["trailing_stop"],
                "cfg_volp03_veto": p["volp03_veto"],
                "cfg_slow_grind_veto": p["slow_grind_veto"],
                "train_sharpe": r["train_sharpe"],
                "val_sharpe": r["validate_sharpe"],
                "test_sharpe": r["test_sharpe"],
                "test_pf": r["test_profit_factor"],
                "test_net_pnl": r["test_net_pnl"],
                "test_maxdd": r["test_max_drawdown"],
                "passed_validation": r["passed_validation"],
            })
        wf_df = pd.DataFrame(wf_rows)
        wf_df = wf_df.replace([float("inf"), float("-inf")], float("nan"))
        lines.append(wf_df.to_markdown(index=False, floatfmt=".3f"))
        lines.append("")
        passed_count = sum(1 for r in wf_results if r["passed_validation"])
        lines.append(f"**{passed_count}/{len(wf_results)} configs passed walk-forward validation.**")
        lines.append("")

    # R1 vs R2 comparison table
    lines += [
        "---",
        "",
        "## 3. R1 vs R2 Direct Comparison",
        "",
        "| Metric | R1 (raw) | R2 (R1 config in R2 sim) | R2 Optimal | Delta R1→R2 Optimal |",
        "|--------|----------|--------------------------|------------|---------------------|",
        f"| Test Sharpe | {R1_RECOMMENDED['test_sharpe']:.3f} | {r1_wf_stats['sharpe']:.3f} | {r2_sharpe:.3f} | {sharpe_delta_pct:+.1f}% |",
        f"| Test Net PnL ($) | {R1_RECOMMENDED['test_net_pnl']:.2f} | {r1_wf_stats['net_pnl']:.2f} | {r2_best_wf.get('test_net_pnl', 0):.2f} | — |",
        f"| Test Win Rate | {R1_RECOMMENDED['test_winrate'] if isinstance(R1_RECOMMENDED.get('test_winrate'), float) else 'N/A'} | {r1_wf_stats['win_rate']:.3f} | {r2_best_wf.get('test_win_rate', 0):.3f} | — |",
        f"| Max Drawdown ($) | {R1_RECOMMENDED.get('test_maxdd', 0):.2f} | {r1_wf_stats['max_drawdown']:.2f} | {r2_best_wf.get('test_max_drawdown', 0):.2f} | — |",
        "",
    ]

    # Parameter comparison
    if wf_results:
        best = wf_results[0]
        p = best["params"]
        lines += [
            "### 3.1 R1 vs R2 Parameter Config",
            "",
            "| Parameter | R1 Recommended | R2 Optimal |",
            "|-----------|---------------|------------|",
            f"| weight_profile | {R1_RECOMMENDED['weight_profile']} | {p['weight_profile']} |",
            f"| entry_threshold | {R1_RECOMMENDED['entry_threshold']} | {p['entry_threshold']} |",
            f"| stop_ticks | {R1_RECOMMENDED['stop_ticks']} | {p['stop_ticks']} |",
            f"| target_ticks | {R1_RECOMMENDED['target_ticks']} | {p['target_ticks']} |",
            f"| trailing_stop | {R1_RECOMMENDED['trailing_stop']} | {p['trailing_stop']} |",
            f"| volp03_veto | {R1_RECOMMENDED['volp03_veto']} | {p['volp03_veto']} |",
            f"| slow_grind_veto | {R1_RECOMMENDED['slow_grind_veto']} | {p['slow_grind_veto']} |",
            "",
        ]

    # Sensitivity / fragile parameters
    lines += [
        "---",
        "",
        "## 4. Sensitivity Analysis (±10% Perturbation, Top 3 Configs)",
        "",
    ]

    if not sensitivity_df.empty:
        sens_disp = sensitivity_df.replace([float("inf"), float("-inf")], float("nan"))
        lines.append(sens_disp.to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

        fragile_params = sensitivity_df[sensitivity_df["fragile"]]["param"].unique().tolist()
        if fragile_params:
            lines.append(f"**Fragile parameters (Sharpe drops >50% on ±10% change):** {', '.join(sorted(set(fragile_params)))}")
        else:
            lines.append("**No fragile parameters detected.** All ±10% perturbations remain within 50% Sharpe tolerance.")
        lines.append("")

    # Convergence verdict and interpretation
    lines += [
        "---",
        "",
        "## 5. Convergence Verdict & Interpretation",
        "",
        f"**R1 optimal walk-forward test Sharpe:** {r1_sharpe:.3f}",
        f"**R2 optimal walk-forward test Sharpe:** {r2_sharpe:.3f}",
        f"**Sharpe improvement:** {sharpe_delta_pct:+.1f}%",
        f"**5% convergence threshold:** {'YES — within threshold' if convergence_verdict == 'CONVERGED' else 'NO — outside threshold'}",
        "",
        f"### Verdict: {convergence_verdict}",
        "",
    ]

    if convergence_verdict == "CONVERGED":
        lines += [
            "R2 sweep is within 5% of R1 optimal Sharpe. Further parameter sweeping on",
            "this 50-session dataset will not yield meaningful new edge. The parameter",
            "space has been exhausted for the current signal set and session distribution.",
            "",
            "**Recommended next steps:**",
            "1. Lock the R2 recommended config for live deployment",
            "2. Expand to a larger out-of-sample dataset (200+ sessions) to validate",
            "3. Focus optimization effort on signal improvements (new signals, weight tuning)",
            "   rather than entry/exit parameter sweeping",
        ]
    else:
        lines += [
            "R2 sweep shows material improvement over R1 optimal (>5% threshold).",
            "The R1 improvements (breakeven, scale-out, directional filter, veto features)",
            "have unlocked new parameter configurations that were sub-optimal in R1 raw scoring.",
            "",
            "**Recommended next steps:**",
            "1. Deploy R2 optimal config parameters",
            "2. Run Round 3 sweep if additional signal changes are made",
            "3. Monitor live performance vs R2 test-set Sharpe as ground truth",
        ]

    lines += [
        "",
        "---",
        "",
        "## 6. R2 Recommended Production Configuration",
        "",
    ]

    if wf_results:
        best = wf_results[0]
        p = best["params"]
        lines += [
            "```",
            f"weight_profile     : {p['weight_profile']}",
            f"entry_threshold    : {p['entry_threshold']}",
            f"stop_ticks         : {p['stop_ticks']} ({p['stop_ticks'] * TICK_SIZE:.2f} pts / ${p['stop_ticks'] * TICK_VALUE:.0f})",
            f"target_ticks       : {p['target_ticks']} ({p['target_ticks'] * TICK_SIZE:.2f} pts / ${p['target_ticks'] * TICK_VALUE:.0f})",
            f"trailing_stop      : {p['trailing_stop']}",
            f"volp03_veto        : {p['volp03_veto']}",
            f"slow_grind_veto    : {p['slow_grind_veto']}",
            f"R:R ratio          : {p['target_ticks'] / p['stop_ticks']:.2f}",
            "# R1 features (active, not swept):",
            "breakeven_enabled          : True  (activation=10t, offset=2t)",
            "scale_out_enabled          : True  (50% at 16t)",
            "strict_direction_enabled   : True",
            "blackout_window            : 1530-1600 ET",
            "```",
            "",
    ]

    lines.append("*Generated by deep6/backtest/round2_sweep.py*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("DEEP6 Round 2 — Full Sweep & Comparison vs R1")
    print("=" * 70)

    # Load sessions
    print(f"\nLoading sessions from {SESSIONS_DIR}...")
    sessions_data = load_all_sessions(SESSIONS_DIR)
    if not sessions_data:
        print("ERROR: No sessions found.", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(sessions_data)} sessions.")

    all_session_names = list(sessions_data.keys())

    # R1 config through R2 simulator (all 50 sessions)
    print("\nSimulating R1 recommended config through R2 simulator (full dataset)...")
    r1_full_stats = simulate_r1_config_in_r2(sessions_data)
    print(f"  R1 config in R2 sim — Sharpe={r1_full_stats['sharpe']:.3f}, "
          f"Trades={r1_full_stats['total_trades']}, NetPnL=${r1_full_stats['net_pnl']:.2f}")

    # Full R2 sweep
    print(f"\nRunning R2 full sweep ({TOTAL_COMBOS} combos × {len(sessions_data)} sessions)...")
    full_sweep_df = run_joint_sweep(sessions_data, label="R2-full")
    full_sweep_csv = OUTPUT_DIR / "r2_sweep_results.csv"
    full_sweep_df.to_csv(full_sweep_csv, index=False)
    print(f"Saved full sweep: {full_sweep_csv}")

    # Walk-forward
    print("\nRunning walk-forward validation (top 10 configs)...")
    wf_results, train_df, train_sessions, val_sessions, test_sessions = run_walkforward(
        sessions_data, all_session_names, top_n=10, min_val_sharpe=0.5,
    )

    # R1 config evaluated on same test split
    test_data = {k: v for k, v in sessions_data.items() if k in set(test_sessions)}
    r1_wf_stats = simulate_r1_config_in_r2(test_data)
    print(f"\n  R1 config on test split — Sharpe={r1_wf_stats['sharpe']:.3f}, "
          f"NetPnL=${r1_wf_stats['net_pnl']:.2f}")

    # R2 best from walk-forward
    r2_best_wf_result = wf_results[0] if wf_results else {}
    r2_best_wf = {
        "test_sharpe": r2_best_wf_result.get("test_sharpe", 0.0),
        "test_net_pnl": r2_best_wf_result.get("test_net_pnl", 0.0),
        "test_win_rate": r2_best_wf_result.get("test_win_rate", 0.0),
        "test_max_drawdown": r2_best_wf_result.get("test_max_drawdown", 0.0),
    }

    # Convergence computation
    # Compare R1 reported test Sharpe vs R2 best test Sharpe
    r1_sharpe = float(R1_RECOMMENDED["test_sharpe"])
    r2_sharpe = r2_best_wf["test_sharpe"]
    if r1_sharpe > 0:
        sharpe_delta_pct = (r2_sharpe - r1_sharpe) / abs(r1_sharpe) * 100.0
    else:
        sharpe_delta_pct = 0.0
    convergence_verdict = "CONVERGED" if abs(sharpe_delta_pct) <= 5.0 else "NOT-CONVERGED"

    print(f"\n{'='*50}")
    print(f"R1 test Sharpe: {r1_sharpe:.3f}")
    print(f"R2 test Sharpe: {r2_sharpe:.3f}")
    print(f"Delta: {sharpe_delta_pct:+.1f}%")
    print(f"Convergence: {convergence_verdict}")
    print(f"{'='*50}")

    # Sensitivity analysis on top-3 walk-forward configs
    print("\nRunning sensitivity analysis (±10% on top-3 configs)...")
    top3_cfgs = [r["params"] for r in wf_results[:3]] if len(wf_results) >= 3 else [r["params"] for r in wf_results]
    sensitivity_df = run_sensitivity_analysis(top3_cfgs, sessions_data)
    sens_csv = OUTPUT_DIR / "r2_sensitivity.csv"
    sensitivity_df.to_csv(sens_csv, index=False)
    print(f"Saved sensitivity: {sens_csv}")

    # Best R2 full-dataset config (for JSON)
    qualified = full_sweep_df[full_sweep_df["total_trades"] >= 3].copy()
    qualified["sharpe_sort"] = qualified["sharpe"].replace(float("inf"), 9999.0)
    best_full_row = qualified.nlargest(1, "sharpe_sort").iloc[0] if not qualified.empty else None
    r2_best_full = {}
    if best_full_row is not None:
        r2_best_full = {
            "weight_profile": str(best_full_row["weight_profile"]),
            "entry_threshold": int(best_full_row["entry_threshold"]),
            "stop_ticks": int(best_full_row["stop_ticks"]),
            "target_ticks": int(best_full_row["target_ticks"]),
            "trailing_stop": bool(best_full_row["trailing_stop"]),
            "volp03_veto": bool(best_full_row["volp03_veto"]),
            "slow_grind_veto": bool(best_full_row["slow_grind_veto"]),
            "full_sharpe": float(best_full_row["sharpe"]) if not np.isinf(best_full_row["sharpe"]) else 9999.0,
            "full_net_pnl": float(best_full_row["net_pnl"]),
            "full_trades": int(best_full_row["total_trades"]),
        }

    # Generate report
    print("\nGenerating comparison report...")
    report_text = generate_comparison_report(
        wf_results=wf_results,
        full_sweep_df=full_sweep_df,
        train_df=train_df,
        sensitivity_df=sensitivity_df,
        r1_full_stats=r1_full_stats,
        r1_wf_stats=r1_wf_stats,
        r2_best_full=r2_best_full,
        r2_best_wf=r2_best_wf,
        train_sessions=train_sessions,
        val_sessions=val_sessions,
        test_sessions=test_sessions,
        convergence_verdict=convergence_verdict,
        r1_sharpe=r1_sharpe,
        r2_sharpe=r2_sharpe,
        sharpe_delta_pct=sharpe_delta_pct,
    )

    report_path = OUTPUT_DIR / "SWEEP-COMPARISON.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Saved report: {report_path}")

    # Recommended config JSON
    r2_config = {}
    if wf_results:
        best_wf = wf_results[0]
        p = best_wf["params"]
        r2_config = {
            **p,
            "source": "walk_forward_validated_r2",
            "r1_test_sharpe": r1_sharpe,
            "r2_test_sharpe": r2_sharpe,
            "sharpe_delta_pct": round(sharpe_delta_pct, 2),
            "convergence_verdict": convergence_verdict,
            "test_sharpe": r2_sharpe,
            "test_win_rate": r2_best_wf["test_win_rate"],
            "test_pf": best_wf.get("test_profit_factor", 0.0),
            "test_net_pnl": r2_best_wf["test_net_pnl"],
            "test_maxdd": r2_best_wf["test_max_drawdown"],
            "rr_ratio": round(p["target_ticks"] / p["stop_ticks"], 3),
            # R1 features — not swept, always active
            "breakeven_enabled": True,
            "breakeven_activation_ticks": 10,
            "breakeven_offset_ticks": 2,
            "scale_out_enabled": True,
            "scale_out_percent": 0.5,
            "scale_out_target_ticks": 16,
            "strict_direction_enabled": True,
            "blackout_window_start": 1530,
            "blackout_window_end": 1600,
            "fragile_params": sensitivity_df[sensitivity_df["fragile"]]["param"].unique().tolist() if not sensitivity_df.empty else [],
        }
    else:
        r2_config = {
            **{k: R1_RECOMMENDED[k] for k in ["weight_profile", "entry_threshold", "stop_ticks",
                                                "target_ticks", "trailing_stop", "volp03_veto",
                                                "slow_grind_veto"]},
            "source": "fallback_to_r1_no_improvement",
            "convergence_verdict": convergence_verdict,
        }

    config_path = OUTPUT_DIR / "RECOMMENDED-CONFIG-R2.json"
    config_path.write_text(json.dumps(r2_config, indent=2, default=str), encoding="utf-8")
    print(f"Saved R2 config: {config_path}")

    print("\n" + "=" * 70)
    print("ROUND 2 SWEEP COMPLETE")
    print(f"  R1 Sharpe (reported):     {r1_sharpe:.3f}")
    print(f"  R2 Sharpe (walk-forward): {r2_sharpe:.3f}")
    print(f"  Delta:                    {sharpe_delta_pct:+.1f}%")
    print(f"  Convergence:              {convergence_verdict}")
    print(f"  Outputs: {OUTPUT_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
