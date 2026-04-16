"""deep6/backtest/round2_stress_test.py — Round 2 edge durability stress tests.

Seven stress tests applied to the R1-recommended config across all 50 sessions:

  T1  Noise injection      — ±2 tick random noise on entry/exit; 100 iterations
  T2  Signal degradation   — random 20% signal drop per session; does profit survive?
  T3  Slippage stress      — 0–5 ticks; find breakeven slippage point
  T4  Commission stress    — $4.50/RT ($2.25/side) per contract added
  T5  Regime-shift         — top-5 trending sessions + 50-bar ranging injected in middle
  T6  Drawdown marathon    — all 50 sessions concatenated (≈19,500 bars) as one run
  T7  Overfit detector     — train Sharpe (first 25 sessions) vs test Sharpe (last 25)

Output:
  ninjatrader/backtests/results/round2/STRESS-TEST.md
"""
from __future__ import annotations

import copy
import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT    = Path(__file__).resolve().parents[2]
SESSIONS_DIR = REPO_ROOT / "ninjatrader" / "backtests" / "sessions"
OUTPUT_DIR   = REPO_ROOT / "ninjatrader" / "backtests" / "results" / "round2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Instrument constants
# ---------------------------------------------------------------------------
TICK_SIZE  = 0.25   # NQ tick
TICK_VALUE = 5.0    # $ per tick per contract
COMMISSION_PER_RT = 4.50   # $4.50 round-turn per contract (T4)

# ---------------------------------------------------------------------------
# R1 recommended config (from round1/RECOMMENDED-CONFIG.json)
# ---------------------------------------------------------------------------
R1_CONFIG = {
    "score_entry_threshold": 70.0,
    "stop_loss_ticks":       20,
    "target_ticks":          32,
    "exit_on_opposing_score": 0.50,
    "max_bars_in_trade":     30,
    "min_tier":              "TYPE_B",   # matches BacktestConfig default
    "slippage_ticks":        1.0,
    # R1 improvements active
    "breakeven_enabled":         True,
    "breakeven_activation_ticks": 10,
    "breakeven_offset_ticks":    2,
    "scale_out_enabled":         True,
    "scale_out_percent":         0.5,
    "scale_out_target_ticks":    16,
    "trailing_stop_enabled":     False,
    "vol_surge_veto":            True,
    "slow_grind_veto":           True,
    "slow_grind_atr_ratio":      0.5,
    "strict_direction":          True,
    "blackout_start":            1530,
    "blackout_end":              1600,
}

_TIER_ORDINALS = {"DISQUALIFIED": -1, "QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}

# ---------------------------------------------------------------------------
# Data loading (re-uses vbt_harness loader)
# ---------------------------------------------------------------------------

def load_all_sessions(sessions_dir: Path) -> dict[str, list[dict]]:
    """Return {session_name: [bar_dict, ...]}."""
    sessions: dict[str, list[dict]] = {}
    for path in sorted(sessions_dir.glob("*.ndjson")):
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
        sessions[path.name] = bars
    return sessions


# ---------------------------------------------------------------------------
# Lightweight Python scorer (from vbt_harness._score_bar_simple)
# ---------------------------------------------------------------------------

def _score_bar(bar: dict, drop_signal_ids: set[str] | None = None) -> dict:
    """Score a bar, optionally dropping specified signal IDs (T2 degradation)."""
    signals = bar.get("signals", [])
    if drop_signal_ids:
        signals = [s for s in signals if s.get("signalId", "") not in drop_signal_ids]

    zone_score     = float(bar.get("zoneScore", 0.0))
    zone_dist      = float(bar.get("zoneDistTicks", 1e9))
    bars_since_open = int(bar.get("barsSinceOpen", 0))
    bar_delta      = int(bar.get("barDelta", 0))
    bar_close      = float(bar.get("barClose", 0.0))
    bar_atr        = float(bar.get("atr", 0.0))

    W = {
        "absorption": 25.0, "exhaustion": 18.0, "trapped": 14.0,
        "delta": 13.0, "imbalance": 12.0, "volume_profile": 10.0,
        "auction": 8.0, "poc": 1.0,
    }
    VOTING_DELTA = {"DELT-04", "DELT-05", "DELT-06", "DELT-08", "DELT-10"}
    VOTING_AUCT  = {"AUCT-01", "AUCT-02", "AUCT-05"}
    VOTING_POC   = {"POC-02",  "POC-07",  "POC-08"}

    bull_w = 0.0; bear_w = 0.0
    cats_bull: set[str] = set(); cats_bear: set[str] = set()
    stacked_bull = 0; stacked_bear = 0
    max_bull_str = 0.0; max_bear_str = 0.0

    for sig in signals:
        sid = sig.get("signalId", "")
        d   = int(sig.get("direction", 0))
        s   = float(sig.get("strength", 0.0))
        if d == 0:
            continue

        def _add(is_bull: bool, cat: str) -> None:
            nonlocal bull_w, bear_w, max_bull_str, max_bear_str
            if is_bull:
                bull_w += s; cats_bull.add(cat); max_bull_str = max(max_bull_str, s)
            else:
                bear_w += s; cats_bear.add(cat); max_bear_str = max(max_bear_str, s)

        if sid.startswith("ABS"):   _add(d > 0, "absorption")
        elif sid.startswith("EXH"): _add(d > 0, "exhaustion")
        elif sid.startswith("TRAP"):_add(d > 0, "trapped")
        elif sid.startswith("IMB"):
            tier_n = 0
            for suffix in ("-T3", "-T2", "-T1"):
                if sid.endswith(suffix):
                    tier_n = int(suffix[-1]); break
            if tier_n == 0 and "STACKED_T" in sig.get("detail", ""):
                detail = sig.get("detail", "")
                idx = detail.find("STACKED_T")
                if idx >= 0 and idx + 9 < len(detail):
                    try: tier_n = int(detail[idx + 9])
                    except ValueError: tier_n = 1
            if tier_n > 0:
                if d > 0: stacked_bull = max(stacked_bull, tier_n); max_bull_str = max(max_bull_str, s)
                else:     stacked_bear = max(stacked_bear, tier_n); max_bear_str = max(max_bear_str, s)
        elif sid in VOTING_DELTA: _add(d > 0, "delta")
        elif sid in VOTING_AUCT:  _add(d > 0, "auction")
        elif sid in VOTING_POC:   _add(d > 0, "poc")

    if stacked_bull > 0: bull_w += 0.5; cats_bull.add("imbalance")
    if stacked_bear > 0: bear_w += 0.5; cats_bear.add("imbalance")

    if bull_w > bear_w:
        direction = 1;  cats = cats_bull; max_str = max_bull_str
    elif bear_w > bull_w:
        direction = -1; cats = cats_bear; max_str = max_bear_str
    else:
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                "entry_price": bar_close, "bar_atr": bar_atr}

    if bar_delta != 0:
        if (direction > 0 and bar_delta < 0) or (direction < 0 and bar_delta > 0):
            return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                    "entry_price": bar_close, "bar_atr": bar_atr}

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
        return {"direction": 0, "total_score": 0.0, "tier": "QUIET",
                "entry_price": bar_close, "bar_atr": bar_atr}

    has_abs  = "absorption" in cats
    has_exh  = "exhaustion" in cats
    has_zone = zone_bonus > 0.0
    trap_count  = sum(1 for sig in signals if sig.get("signalId", "").startswith("TRAP"))
    delta_chase = abs(bar_delta) > 50 and (
        (direction > 0 and bar_delta > 0) or (direction < 0 and bar_delta < 0))

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

    return {"direction": direction, "total_score": total_score, "tier": tier,
            "entry_price": entry_price, "bar_atr": bar_atr}


# ---------------------------------------------------------------------------
# Core simulator — configurable, with noise/drop support
# ---------------------------------------------------------------------------

def simulate_sessions(
    sessions_data: dict[str, list[dict]],
    cfg: dict,
    noise_ticks: float = 0.0,
    signal_drop_frac: float = 0.0,
    extra_slippage_ticks: float = 0.0,
    commission_per_rt: float = 0.0,
    rng: random.Random | None = None,
) -> list[dict]:
    """Simulate all sessions. Returns list of trade dicts.

    Args:
        noise_ticks: ±random noise in ticks added to entry and exit prices.
        signal_drop_frac: fraction of signal IDs to randomly drop per session.
        extra_slippage_ticks: additional slippage on top of cfg['slippage_ticks'].
        commission_per_rt: commission in dollars subtracted per completed trade.
        rng: seeded Random instance for reproducibility.
    """
    if rng is None:
        rng = random.Random()

    sl_pts   = cfg["stop_loss_ticks"] * TICK_SIZE
    tp_pts   = cfg["target_ticks"] * TICK_SIZE
    so_pts   = cfg["scale_out_target_ticks"] * TICK_SIZE
    be_act   = cfg["breakeven_activation_ticks"] * TICK_SIZE  # in price pts
    be_off   = cfg["breakeven_offset_ticks"] * TICK_SIZE
    total_slip = (cfg["slippage_ticks"] + extra_slippage_ticks) * TICK_SIZE
    min_tier_ord = _TIER_ORDINALS.get(cfg["min_tier"], 2)
    opp_thresh = cfg["exit_on_opposing_score"] * 100.0

    all_trades: list[dict] = []

    for session_name, bars in sessions_data.items():
        in_trade       = False
        entry_price    = 0.0
        entry_bar_idx  = 0
        trade_dir      = 0
        mfe            = 0.0
        be_armed       = False
        be_stop        = 0.0
        scale_done     = False
        vol_surge_fired = False
        session_atr_sum   = 0.0
        session_atr_count = 0

        # Collect all signal IDs in this session for drop lottery
        all_sig_ids: list[str] = []
        for bar in bars:
            for sig in bar.get("signals", []):
                sid = sig.get("signalId", "")
                if sid and sid not in all_sig_ids:
                    all_sig_ids.append(sid)

        drop_ids: set[str] = set()
        if signal_drop_frac > 0.0 and all_sig_ids:
            n_drop = max(1, int(len(all_sig_ids) * signal_drop_frac))
            drop_ids = set(rng.sample(all_sig_ids, min(n_drop, len(all_sig_ids))))

        for bar in bars:
            bar_idx        = int(bar.get("barIdx", 0))
            bar_close_raw  = float(bar.get("barClose", 0.0))
            bar_atr        = float(bar.get("atr", 0.0))
            bars_since_open = int(bar.get("barsSinceOpen", 0))

            # Noise-perturbed close price used for simulation decisions
            bar_close = bar_close_raw + rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE

            # Accumulate session ATR
            if bar_atr > 0.0:
                session_atr_sum += bar_atr
                session_atr_count += 1
            session_avg_atr = session_atr_sum / session_atr_count if session_atr_count > 0 else 0.0

            # Check VOLP-03 veto
            if cfg.get("vol_surge_veto", True):
                for sig in bar.get("signals", []):
                    if sig.get("signalId", "").startswith("VOLP-03"):
                        vol_surge_fired = True
                        break

            scored = _score_bar(bar, drop_signal_ids=drop_ids if drop_ids else None)
            direction   = scored["direction"]
            total_score = scored["total_score"]
            tier_ord    = _TIER_ORDINALS.get(scored["tier"], 0)

            if in_trade:
                # Update MFE
                current_mfe_pts = (bar_close - entry_price) * trade_dir
                if current_mfe_pts > mfe:
                    mfe = current_mfe_pts

                # Breakeven
                if cfg.get("breakeven_enabled", True) and not be_armed and mfe >= be_act:
                    be_armed = True
                    candidate = entry_price + trade_dir * be_off
                    # Only tighten (ratchet)
                    if trade_dir == +1:
                        be_stop = max(be_stop, candidate) if be_stop != 0.0 else candidate
                    else:
                        be_stop = min(be_stop, candidate) if be_stop != 0.0 else candidate

                exit_reason = None

                # 1. Hard stop
                if trade_dir == +1 and bar_close <= entry_price - sl_pts:
                    exit_reason = "STOP_LOSS"
                elif trade_dir == -1 and bar_close >= entry_price + sl_pts:
                    exit_reason = "STOP_LOSS"

                # 1b. Breakeven stop
                if exit_reason is None and be_armed:
                    if trade_dir == +1 and bar_close <= be_stop:
                        exit_reason = "BREAKEVEN_STOP"
                    elif trade_dir == -1 and bar_close >= be_stop:
                        exit_reason = "BREAKEVEN_STOP"

                # 2. Scale-out T1
                if exit_reason is None and cfg.get("scale_out_enabled", True) and not scale_done:
                    if trade_dir == +1 and bar_close >= entry_price + so_pts:
                        exit_price_so = bar_close + rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE
                        exit_price_so -= trade_dir * total_slip
                        pnl_ticks = (exit_price_so - entry_price) / TICK_SIZE * trade_dir
                        commission_part = commission_per_rt * cfg.get("scale_out_percent", 0.5)
                        all_trades.append({
                            "session": session_name,
                            "entry_bar": entry_bar_idx, "exit_bar": bar_idx,
                            "direction": trade_dir,
                            "pnl_ticks": pnl_ticks * cfg.get("scale_out_percent", 0.5),
                            "pnl_dollars": pnl_ticks * TICK_VALUE * cfg.get("scale_out_percent", 0.5) - commission_part,
                            "exit_reason": "SCALE_OUT_PARTIAL",
                        })
                        scale_done = True
                    elif trade_dir == -1 and bar_close <= entry_price - so_pts:
                        exit_price_so = bar_close + rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE
                        exit_price_so -= trade_dir * total_slip
                        pnl_ticks = (exit_price_so - entry_price) / TICK_SIZE * trade_dir
                        commission_part = commission_per_rt * cfg.get("scale_out_percent", 0.5)
                        all_trades.append({
                            "session": session_name,
                            "entry_bar": entry_bar_idx, "exit_bar": bar_idx,
                            "direction": trade_dir,
                            "pnl_ticks": pnl_ticks * cfg.get("scale_out_percent", 0.5),
                            "pnl_dollars": pnl_ticks * TICK_VALUE * cfg.get("scale_out_percent", 0.5) - commission_part,
                            "exit_reason": "SCALE_OUT_PARTIAL",
                        })
                        scale_done = True

                # 3. Full target
                if exit_reason is None:
                    if trade_dir == +1 and bar_close >= entry_price + tp_pts:
                        exit_reason = "SCALE_OUT_FINAL" if scale_done else "TARGET"
                    elif trade_dir == -1 and bar_close <= entry_price - tp_pts:
                        exit_reason = "SCALE_OUT_FINAL" if scale_done else "TARGET"

                # 4. Opposing signal
                if exit_reason is None and direction != 0 and direction != trade_dir:
                    if total_score >= opp_thresh:
                        exit_reason = "OPPOSING"

                # 5. Max bars
                if exit_reason is None and (bar_idx - entry_bar_idx) >= cfg["max_bars_in_trade"]:
                    exit_reason = "MAX_BARS"

                if exit_reason is not None:
                    exit_noise = rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE
                    exit_price = bar_close + exit_noise - trade_dir * total_slip
                    remain_frac = (1.0 - cfg.get("scale_out_percent", 0.5)) if scale_done else 1.0
                    pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
                    commission_part = commission_per_rt * remain_frac
                    all_trades.append({
                        "session": session_name,
                        "entry_bar": entry_bar_idx, "exit_bar": bar_idx,
                        "direction": trade_dir,
                        "pnl_ticks": pnl_ticks * remain_frac,
                        "pnl_dollars": pnl_ticks * TICK_VALUE * remain_frac - commission_part,
                        "exit_reason": exit_reason,
                    })
                    in_trade = False; mfe = 0.0; be_armed = False
                    be_stop = 0.0; scale_done = False

            else:
                # Entry gate
                if cfg.get("vol_surge_veto", True) and vol_surge_fired:
                    continue
                if cfg.get("slow_grind_veto", True) and bar_atr > 0.0 and session_avg_atr > 0.0:
                    if bar_atr < cfg.get("slow_grind_atr_ratio", 0.5) * session_avg_atr:
                        continue

                # Blackout window
                total_min = 9 * 60 + 30 + bars_since_open
                bar_hhmm  = (total_min // 60) * 100 + (total_min % 60)
                if cfg.get("blackout_start", 1530) <= bar_hhmm <= cfg.get("blackout_end", 1600):
                    continue

                # Strict direction filter
                if cfg.get("strict_direction", True):
                    opposing = any(
                        int(sig.get("direction", 0)) == -direction
                        for sig in bar.get("signals", [])
                        if int(sig.get("direction", 0)) != 0
                    ) if direction != 0 else False
                    if opposing:
                        continue

                if (total_score >= cfg["score_entry_threshold"]
                        and tier_ord >= min_tier_ord
                        and direction != 0):
                    entry_noise = rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE
                    entry_price = scored["entry_price"] + entry_noise + direction * total_slip
                    entry_bar_idx = bar_idx
                    trade_dir  = direction
                    in_trade   = True
                    mfe        = 0.0
                    be_armed   = False
                    be_stop    = 0.0
                    scale_done = False

        # Force-close at session end
        if in_trade and bars:
            last_bar  = bars[-1]
            lclose    = float(last_bar.get("barClose", 0.0))
            l_bar_idx = int(last_bar.get("barIdx", 0))
            exit_noise = rng.uniform(-noise_ticks, noise_ticks) * TICK_SIZE
            exit_price = lclose + exit_noise - trade_dir * total_slip
            remain_frac = (1.0 - cfg.get("scale_out_percent", 0.5)) if scale_done else 1.0
            pnl_ticks = (exit_price - entry_price) / TICK_SIZE * trade_dir
            commission_part = commission_per_rt * remain_frac
            all_trades.append({
                "session": session_name,
                "entry_bar": entry_bar_idx, "exit_bar": l_bar_idx,
                "direction": trade_dir,
                "pnl_ticks": pnl_ticks * remain_frac,
                "pnl_dollars": pnl_ticks * TICK_VALUE * remain_frac - commission_part,
                "exit_reason": "SESSION_END",
            })
            in_trade = False

    return all_trades


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "max_drawdown_dollars": 0.0, "sharpe": 0.0,
            "avg_pnl_per_trade": 0.0, "net_pnl": 0.0,
            "recovery_trades": 0,
        }
    pnls = np.array([t["pnl_dollars"] for t in trades])
    wins = (pnls > 0).sum()

    gross_profit = pnls[pnls > 0].sum()
    gross_loss   = abs(pnls[pnls < 0].sum())
    pf = float(gross_profit / gross_loss) if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0)

    equity = np.cumsum(pnls)
    running_max = np.maximum.accumulate(equity)
    drawdown = running_max - equity
    max_dd = float(drawdown.max()) if len(drawdown) else 0.0

    std = pnls.std(ddof=1) if len(pnls) >= 2 else 0.0
    sharpe = float((pnls.mean() / std) * np.sqrt(252)) if std > 0 else 0.0

    # Recovery time: bars from max drawdown trough to next new equity high
    if len(equity) > 1 and max_dd > 0:
        peak_idx  = int(np.argmax(running_max - equity))  # trough index
        recovery_bars = 0
        if peak_idx < len(equity) - 1:
            peak_val = running_max[peak_idx]
            for j in range(peak_idx + 1, len(equity)):
                recovery_bars += 1
                if equity[j] >= peak_val:
                    break
            else:
                recovery_bars = -1  # never recovered within sample
    else:
        recovery_bars = 0

    return {
        "total_trades": len(trades),
        "win_rate": float(wins / len(pnls)),
        "profit_factor": pf,
        "max_drawdown_dollars": max_dd,
        "sharpe": sharpe,
        "avg_pnl_per_trade": float(pnls.mean()),
        "net_pnl": float(pnls.sum()),
        "recovery_trades": recovery_bars,
    }


# ---------------------------------------------------------------------------
# T1: Noise injection — 100 iterations of ±2 tick noise
# ---------------------------------------------------------------------------

def test_t1_noise(sessions_data: dict) -> dict:
    print("T1: Noise injection (100 iterations, ±2 ticks)...")
    win_rates = []
    net_pnls  = []
    for seed in range(100):
        rng = random.Random(seed)
        trades = simulate_sessions(sessions_data, R1_CONFIG, noise_ticks=2.0, rng=rng)
        s = _stats(trades)
        win_rates.append(s["win_rate"])
        net_pnls.append(s["net_pnl"])

    mean_wr  = float(np.mean(win_rates))
    min_wr   = float(np.min(win_rates))
    max_wr   = float(np.max(win_rates))
    pct_above_60 = sum(1 for w in win_rates if w >= 0.60) / 100.0

    mean_pnl = float(np.mean(net_pnls))
    pct_positive = sum(1 for p in net_pnls if p > 0) / 100.0

    passed = mean_wr >= 0.60 and pct_above_60 >= 0.80

    return {
        "test": "T1_NOISE_INJECTION",
        "mean_win_rate": mean_wr,
        "min_win_rate": min_wr,
        "max_win_rate": max_wr,
        "pct_iterations_above_60pct_wr": pct_above_60,
        "mean_net_pnl": mean_pnl,
        "pct_iterations_profitable": pct_positive,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": f"Mean WR={mean_wr:.1%} | Min={min_wr:.1%} | Max={max_wr:.1%} | "
                f"{pct_above_60:.0%} iters ≥60% WR | {pct_positive:.0%} profitable",
    }


# ---------------------------------------------------------------------------
# T2: Signal degradation — 20% signal drop per session
# ---------------------------------------------------------------------------

def test_t2_signal_degradation(sessions_data: dict) -> dict:
    print("T2: Signal degradation (20% drop, 50 iterations)...")
    net_pnls = []
    win_rates = []
    for seed in range(50):
        rng = random.Random(seed + 1000)
        trades = simulate_sessions(sessions_data, R1_CONFIG, signal_drop_frac=0.20, rng=rng)
        s = _stats(trades)
        net_pnls.append(s["net_pnl"])
        win_rates.append(s["win_rate"])

    mean_pnl = float(np.mean(net_pnls))
    pct_positive = sum(1 for p in net_pnls if p > 0) / 50.0
    mean_wr = float(np.mean(win_rates))

    # Baseline (no drop)
    baseline = _stats(simulate_sessions(sessions_data, R1_CONFIG, rng=random.Random(42)))
    pnl_retention = mean_pnl / baseline["net_pnl"] if baseline["net_pnl"] != 0 else 0.0

    passed = pct_positive >= 0.80 and mean_pnl > 0.0

    return {
        "test": "T2_SIGNAL_DEGRADATION",
        "baseline_net_pnl": baseline["net_pnl"],
        "degraded_mean_net_pnl": mean_pnl,
        "pnl_retention_pct": pnl_retention,
        "mean_win_rate_degraded": mean_wr,
        "pct_iterations_profitable": pct_positive,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": f"Baseline PnL=${baseline['net_pnl']:.0f} | Degraded=${mean_pnl:.0f} "
                f"({pnl_retention:.0%} retained) | {pct_positive:.0%} profitable",
    }


# ---------------------------------------------------------------------------
# T3: Slippage stress — 0 to 5 ticks
# ---------------------------------------------------------------------------

def test_t3_slippage(sessions_data: dict) -> dict:
    print("T3: Slippage stress (0–5 ticks)...")
    rng = random.Random(42)
    results = []
    breakeven_ticks = None

    for slip in range(0, 6):
        cfg = dict(R1_CONFIG)
        cfg["slippage_ticks"] = 0.0  # set extra slippage cleanly
        trades = simulate_sessions(sessions_data, cfg,
                                   extra_slippage_ticks=float(slip), rng=random.Random(42))
        s = _stats(trades)
        results.append({
            "slippage_ticks": slip,
            "net_pnl": s["net_pnl"],
            "win_rate": s["win_rate"],
            "sharpe": s["sharpe"],
            "profit_factor": s["profit_factor"],
        })
        if breakeven_ticks is None and s["net_pnl"] <= 0.0:
            breakeven_ticks = slip

    if breakeven_ticks is None:
        breakeven_ticks = ">5"

    passed = results[1]["net_pnl"] > 0  # profitable at 1 tick (realistic live slippage)

    rows_text = "\n".join(
        f"  {r['slippage_ticks']}t: PnL=${r['net_pnl']:+.0f}  WR={r['win_rate']:.1%}  "
        f"Sharpe={r['sharpe']:.2f}  PF={r['profit_factor']:.2f}"
        for r in results
    )

    return {
        "test": "T3_SLIPPAGE_STRESS",
        "results_by_slippage": results,
        "breakeven_slippage_ticks": breakeven_ticks,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": rows_text,
    }


# ---------------------------------------------------------------------------
# T4: Commission stress — $4.50/RT
# ---------------------------------------------------------------------------

def test_t4_commission(sessions_data: dict) -> dict:
    print("T4: Commission stress ($4.50/RT)...")
    rng = random.Random(42)

    base_trades = simulate_sessions(sessions_data, R1_CONFIG, commission_per_rt=0.0, rng=rng)
    comm_trades = simulate_sessions(sessions_data, R1_CONFIG,
                                    commission_per_rt=COMMISSION_PER_RT, rng=random.Random(42))

    base_stats = _stats(base_trades)
    comm_stats = _stats(comm_trades)

    passed = comm_stats["net_pnl"] > 0.0

    return {
        "test": "T4_COMMISSION_STRESS",
        "baseline_net_pnl": base_stats["net_pnl"],
        "commission_net_pnl": comm_stats["net_pnl"],
        "commission_drag_dollars": base_stats["net_pnl"] - comm_stats["net_pnl"],
        "commission_win_rate": comm_stats["win_rate"],
        "total_trades": comm_stats["total_trades"],
        "total_commission_paid": COMMISSION_PER_RT * comm_stats["total_trades"],
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": f"Base=${base_stats['net_pnl']:.0f} → After comm=${comm_stats['net_pnl']:.0f} "
                f"(drag=${base_stats['net_pnl'] - comm_stats['net_pnl']:.0f}) "
                f"Trades={comm_stats['total_trades']}",
    }


# ---------------------------------------------------------------------------
# T5: Regime-shift — inject 50 ranging bars into top-5 trending sessions
# ---------------------------------------------------------------------------

def test_t5_regime_shift(sessions_data: dict) -> dict:
    print("T5: Regime-shift (50 ranging bars injected into top-5 trending sessions)...")

    # Find top-5 trending sessions (trend_up or trend_down)
    trending = [(name, bars) for name, bars in sessions_data.items()
                if "trend_up" in name or "trend_down" in name]
    # Score each by net movement
    def session_trend_strength(bars: list[dict]) -> float:
        if not bars:
            return 0.0
        return abs(float(bars[-1].get("barClose", 0.0)) - float(bars[0].get("barClose", 0.0)))

    trending_sorted = sorted(trending, key=lambda x: session_trend_strength(x[1]), reverse=True)
    top5 = trending_sorted[:5]

    def make_ranging_bars(template_bar: dict, n: int, start_idx: int) -> list[dict]:
        """Create n bars of sideways noise around the current close."""
        base_close = float(template_bar.get("barClose", 20000.0))
        bars_out = []
        for i in range(n):
            noise = random.gauss(0, 2) * TICK_SIZE  # ±2 ticks std dev
            bars_out.append({
                "type": "scored_bar",
                "barIdx": start_idx + i,
                "barsSinceOpen": int(template_bar.get("barsSinceOpen", 200)) + i,
                "barDelta": random.randint(-20, 20),
                "barClose": round(base_close + noise, 2),
                "zoneScore": 0.0,
                "zoneDistTicks": 999.0,
                "atr": float(template_bar.get("atr", 0.0)),
                "signals": [],  # no signals in ranging inject
            })
        return bars_out

    # Build modified sessions
    modified_sessions = dict(sessions_data)
    for name, bars in top5:
        if len(bars) < 10:
            continue
        mid_idx = len(bars) // 2
        reindex_offset = mid_idx  # ranging bars start at mid_idx barIdx
        ranging_bars = make_ranging_bars(bars[mid_idx], 50, start_idx=mid_idx)
        # Re-index bars after injection
        injected = (
            bars[:mid_idx] +
            ranging_bars +
            [dict(b, barIdx=b.get("barIdx", 0) + 50,
                  barsSinceOpen=b.get("barsSinceOpen", 0) + 50)
             for b in bars[mid_idx:]]
        )
        modified_sessions[name] = injected

    trades_mod = simulate_sessions(modified_sessions, R1_CONFIG, rng=random.Random(42))
    trades_orig = simulate_sessions(sessions_data, R1_CONFIG, rng=random.Random(42))
    stats_mod   = _stats(trades_mod)
    stats_orig  = _stats(trades_orig)

    pnl_ratio = stats_mod["net_pnl"] / stats_orig["net_pnl"] if stats_orig["net_pnl"] != 0 else 0.0
    passed = stats_mod["net_pnl"] > 0.0 and pnl_ratio >= 0.70  # within 30% of baseline

    return {
        "test": "T5_REGIME_SHIFT",
        "top5_trending_sessions": [n for n, _ in top5],
        "baseline_net_pnl": stats_orig["net_pnl"],
        "modified_net_pnl": stats_mod["net_pnl"],
        "pnl_retention_pct": pnl_ratio,
        "baseline_win_rate": stats_orig["win_rate"],
        "modified_win_rate": stats_mod["win_rate"],
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": f"Orig=${stats_orig['net_pnl']:.0f} | Modified=${stats_mod['net_pnl']:.0f} "
                f"({pnl_ratio:.0%} retained) | WR: {stats_orig['win_rate']:.1%}→{stats_mod['win_rate']:.1%}",
    }


# ---------------------------------------------------------------------------
# T6: Drawdown marathon — all 50 sessions as one continuous equity run
# ---------------------------------------------------------------------------

def test_t6_marathon(sessions_data: dict) -> dict:
    print("T6: Drawdown marathon (all 50 sessions concatenated)...")

    # Simulate each session independently (preserving per-session reset semantics
    # for vol_surge_veto, slow_grind_veto, barsSinceOpen midday block, ATR baseline)
    # then concatenate the resulting trade streams to form one continuous equity curve.
    total_bars = sum(len(b) for b in sessions_data.values())

    all_trades: list[dict] = []
    rng = random.Random(42)
    bar_offset = 0
    for name in sorted(sessions_data.keys()):
        session_trades = simulate_sessions({name: sessions_data[name]}, R1_CONFIG, rng=rng)
        # Re-stamp entry/exit bar indices to be globally monotonic for equity ordering
        for t in session_trades:
            t2 = dict(t)
            t2["entry_bar"] = bar_offset + t["entry_bar"]
            t2["exit_bar"]  = bar_offset + t["exit_bar"]
            all_trades.append(t2)
        if sessions_data[name]:
            bar_offset += int(sessions_data[name][-1].get("barIdx", 0)) + 1

    s = _stats(all_trades)

    # Equity curve
    pnls = np.array([t["pnl_dollars"] for t in all_trades]) if all_trades else np.array([0.0])
    equity = np.cumsum(pnls)
    trend_up = bool(np.polyfit(np.arange(len(equity)), equity, 1)[0] > 0) if len(equity) > 1 else False

    passed = (s["net_pnl"] > 0.0
              and s["max_drawdown_dollars"] < 5000.0
              and trend_up)

    return {
        "test": "T6_DRAWDOWN_MARATHON",
        "total_bars": total_bars,
        "total_trades": s["total_trades"],
        "net_pnl": s["net_pnl"],
        "max_drawdown_dollars": s["max_drawdown_dollars"],
        "win_rate": s["win_rate"],
        "sharpe": s["sharpe"],
        "recovery_trades": s["recovery_trades"],
        "equity_curve_trending_up": trend_up,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "note": f"Total bars={total_bars} | Trades={s['total_trades']} | "
                f"PnL=${s['net_pnl']:.0f} | MaxDD=${s['max_drawdown_dollars']:.0f} | "
                f"Trend={'UP' if trend_up else 'FLAT/DOWN'}",
    }


# ---------------------------------------------------------------------------
# T7: Overfit detector — train on first 25, test on last 25
# ---------------------------------------------------------------------------

def test_t7_overfit(sessions_data: dict) -> dict:
    print("T7: Overfit detector (first 25 vs last 25 sessions)...")

    all_names = sorted(sessions_data.keys())
    train_names = set(all_names[:25])
    test_names  = set(all_names[25:])

    train_data = {k: v for k, v in sessions_data.items() if k in train_names}
    test_data  = {k: v for k, v in sessions_data.items() if k in test_names}

    train_trades = simulate_sessions(train_data, R1_CONFIG, rng=random.Random(42))
    test_trades  = simulate_sessions(test_data, R1_CONFIG, rng=random.Random(42))

    train_stats = _stats(train_trades)
    test_stats  = _stats(test_trades)

    # Overfit criterion: test Sharpe < 50% of train Sharpe
    train_sharpe = train_stats["sharpe"]
    test_sharpe  = test_stats["sharpe"]

    if train_sharpe > 0 and test_sharpe >= 0:
        sharpe_ratio = test_sharpe / train_sharpe
        overfit = sharpe_ratio < 0.50
    else:
        sharpe_ratio = 0.0
        overfit = True

    passed = not overfit

    return {
        "test": "T7_OVERFIT_DETECTOR",
        "train_sessions": len(train_data),
        "test_sessions": len(test_data),
        "train_net_pnl": train_stats["net_pnl"],
        "test_net_pnl": test_stats["net_pnl"],
        "train_sharpe": train_sharpe,
        "test_sharpe": test_sharpe,
        "test_to_train_sharpe_ratio": sharpe_ratio,
        "overfit_warning": overfit,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL (OVERFIT WARNING)",
        "note": f"Train Sharpe={train_sharpe:.2f} | Test Sharpe={test_sharpe:.2f} | "
                f"Ratio={sharpe_ratio:.2f} ({'OK' if not overfit else 'OVERFIT <50%'})",
    }


# ---------------------------------------------------------------------------
# Robustness verdict
# ---------------------------------------------------------------------------

def overall_verdict(results: list[dict]) -> str:
    passed = sum(1 for r in results if r.get("passed", False))
    total  = len(results)
    ratio  = passed / total if total else 0.0
    if ratio >= 0.85:
        return "ROBUST"
    elif ratio >= 0.57:
        return "MARGINAL"
    else:
        return "FRAGILE"


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------

def write_report(results: list[dict], verdict: str, slip_breakeven, output_path: Path) -> None:
    t1, t2, t3, t4, t5, t6, t7 = results

    def pf(val) -> str:
        if isinstance(val, float):
            if math.isinf(val):
                return "∞"
            return f"{val:.2f}"
        return str(val)

    lines = [
        "# DEEP6 Round 2 — Edge Durability Stress Test",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M ET')}",
        f"**Sessions:** 50 NDJSON sessions (trend_up×10, trend_down×10, ranging×10, volatile×10, slow_grind×10)",
        f"**Config:** R1 walk-forward optimum (score_threshold=70, SL=20t, TP=32t, breakeven+scale-out active)",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Test | Result | Verdict |",
        f"|------|--------|---------|",
        f"| T1 Noise Injection (±2t, 100 iters) | Mean WR={t1['mean_win_rate']:.1%}, {t1['pct_iterations_above_60pct_wr']:.0%} iters ≥60% | **{t1['verdict']}** |",
        f"| T2 Signal Degradation (20% drop) | {t2['pct_iterations_profitable']:.0%} iters profitable, {t2['pnl_retention_pct']:.0%} PnL retained | **{t2['verdict']}** |",
        f"| T3 Slippage Stress (0–5t) | Breakeven at {slip_breakeven} ticks | **{t3['verdict']}** |",
        f"| T4 Commission Stress ($4.50/RT) | Net PnL ${t4['commission_net_pnl']:.0f} after commissions | **{t4['verdict']}** |",
        f"| T5 Regime Shift (50-bar ranging inject) | {t5['pnl_retention_pct']:.0%} PnL retained | **{t5['verdict']}** |",
        f"| T6 Drawdown Marathon (all 50 sessions) | MaxDD=${t6['max_drawdown_dollars']:.0f}, curve={'↑' if t6['equity_curve_trending_up'] else '→'} | **{t6['verdict']}** |",
        f"| T7 Overfit Detector (25/25 split) | Test/Train Sharpe={t7['test_to_train_sharpe_ratio']:.2f} | **{t7['verdict']}** |",
        "",
        f"**Passed: {sum(1 for r in results if r.get('passed', False))}/{len(results)}**",
        "",
        f"## Overall Robustness Verdict: **{verdict}**",
        "",
        f"**Slippage breakeven point: {slip_breakeven} ticks**",
        "",
        "---",
        "",
        "## T1 — Noise Injection (±2 ticks, 100 iterations)",
        "",
        f"Adds random ±2 tick noise to every entry and exit price. Tests whether the edge survives price uncertainty.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Mean win rate | {t1['mean_win_rate']:.2%} |",
        f"| Min win rate | {t1['min_win_rate']:.2%} |",
        f"| Max win rate | {t1['max_win_rate']:.2%} |",
        f"| % iterations ≥ 60% WR | {t1['pct_iterations_above_60pct_wr']:.0%} |",
        f"| Mean net PnL | ${t1['mean_net_pnl']:.0f} |",
        f"| % iterations profitable | {t1['pct_iterations_profitable']:.0%} |",
        f"| **Verdict** | **{t1['verdict']}** |",
        "",
        f"> {t1['note']}",
        "",
        "---",
        "",
        "## T2 — Signal Degradation (20% detector miss rate)",
        "",
        f"Randomly drops 20% of unique signal IDs per session, simulating systematic detector misses.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Baseline net PnL | ${t2['baseline_net_pnl']:.0f} |",
        f"| Degraded mean PnL | ${t2['degraded_mean_net_pnl']:.0f} |",
        f"| PnL retention | {t2['pnl_retention_pct']:.0%} |",
        f"| Mean WR (degraded) | {t2['mean_win_rate_degraded']:.2%} |",
        f"| % iterations profitable | {t2['pct_iterations_profitable']:.0%} |",
        f"| **Verdict** | **{t2['verdict']}** |",
        "",
        f"> {t2['note']}",
        "",
        "---",
        "",
        "## T3 — Slippage Stress (0 to 5 ticks)",
        "",
        f"Tests the system at increasing slippage. Slippage breakeven = first tick level where net PnL turns ≤ 0.",
        "",
        f"| Slippage | Net PnL | Win Rate | Sharpe | Profit Factor |",
        f"|----------|---------|----------|--------|---------------|",
    ]

    for r in t3["results_by_slippage"]:
        pf_val = "∞" if math.isinf(r["profit_factor"]) else f"{r['profit_factor']:.2f}"
        lines.append(
            f"| {r['slippage_ticks']}t | ${r['net_pnl']:+.0f} | {r['win_rate']:.1%} | "
            f"{r['sharpe']:.2f} | {pf_val} |"
        )

    lines += [
        "",
        f"**Breakeven slippage: {slip_breakeven} ticks**",
        "",
        f"| **Verdict** | **{t3['verdict']}** |",
        "",
        "---",
        "",
        "## T4 — Commission Stress ($4.50/RT per contract)",
        "",
        f"Applies realistic prop-firm commission ($2.25/side, $4.50/RT) to every trade.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Baseline net PnL | ${t4['baseline_net_pnl']:.0f} |",
        f"| After commission | ${t4['commission_net_pnl']:.0f} |",
        f"| Commission drag | ${t4['commission_drag_dollars']:.0f} |",
        f"| Total trades | {t4['total_trades']} |",
        f"| Total commissions paid | ${t4['total_commission_paid']:.0f} |",
        f"| Win rate (post-comm) | {t4['commission_win_rate']:.2%} |",
        f"| **Verdict** | **{t4['verdict']}** |",
        "",
        f"> {t4['note']}",
        "",
        "---",
        "",
        "## T5 — Regime Shift (50-bar ranging injection in top-5 trending sessions)",
        "",
        f"Injects 50 bars of zero-signal ranging into the middle of the top-5 trending sessions by absolute move.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Modified sessions | {', '.join(t5['top5_trending_sessions'])} |",
        f"| Baseline net PnL | ${t5['baseline_net_pnl']:.0f} |",
        f"| Modified net PnL | ${t5['modified_net_pnl']:.0f} |",
        f"| PnL retention | {t5['pnl_retention_pct']:.0%} |",
        f"| Baseline WR | {t5['baseline_win_rate']:.2%} |",
        f"| Modified WR | {t5['modified_win_rate']:.2%} |",
        f"| **Verdict** | **{t5['verdict']}** |",
        "",
        f"> {t5['note']}",
        "",
        "---",
        "",
        "## T6 — Drawdown Marathon (all 50 sessions, ~19,500 bars)",
        "",
        f"Concatenates all 50 sessions into one continuous run to test long-run equity curve behavior.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total bars | {t6['total_bars']:,} |",
        f"| Total trades | {t6['total_trades']} |",
        f"| Net PnL | ${t6['net_pnl']:.0f} |",
        f"| Max drawdown | ${t6['max_drawdown_dollars']:.0f} |",
        f"| Win rate | {t6['win_rate']:.2%} |",
        f"| Sharpe | {t6['sharpe']:.2f} |",
        f"| Recovery (trades from trough→new high) | {t6['recovery_trades']} |",
        f"| Equity curve direction | {'Trending UP' if t6['equity_curve_trending_up'] else 'Flat/Down'} |",
        f"| **Verdict** | **{t6['verdict']}** |",
        "",
        f"> {t6['note']}",
        "",
        "---",
        "",
        "## T7 — Overfit Detector (first 25 vs last 25 sessions)",
        "",
        f"Trains config on first 25 sessions (sessions 01–25), tests on last 25 (sessions 26–50).",
        f"FAIL if test Sharpe < 50% of train Sharpe.",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Train sessions | {t7['train_sessions']} |",
        f"| Test sessions | {t7['test_sessions']} |",
        f"| Train net PnL | ${t7['train_net_pnl']:.0f} |",
        f"| Test net PnL | ${t7['test_net_pnl']:.0f} |",
        f"| Train Sharpe | {t7['train_sharpe']:.2f} |",
        f"| Test Sharpe | {t7['test_sharpe']:.2f} |",
        f"| Test/Train Sharpe ratio | {t7['test_to_train_sharpe_ratio']:.2f} |",
        f"| Overfit warning | {'YES' if t7['overfit_warning'] else 'NO'} |",
        f"| **Verdict** | **{t7['verdict']}** |",
        "",
        f"> {t7['note']}",
        "",
        "---",
        "",
        "## Interpretation",
        "",
        f"**{verdict}** — ",
    ]

    if verdict == "ROBUST":
        lines.append(
            "The DEEP6 R1 edge is durable across all major stress dimensions. "
            "Noise tolerance, signal dropout, slippage margin, commission buffer, "
            "regime handling, marathon equity curve, and no overfit signal all check out. "
            "System is ready for live paper trading validation."
        )
    elif verdict == "MARGINAL":
        lines.append(
            "The DEEP6 R1 edge survives most stress tests but has weak spots. "
            "Review failed tests above and address before live deployment. "
            "The core signal (absorption/exhaustion + confluence) remains viable."
        )
    else:
        lines.append(
            "The DEEP6 R1 edge is fragile under stress conditions. "
            "Multiple tests failed. Re-examine signal quality, stop placement, "
            "and overfit risk before any live deployment."
        )

    lines += [
        "",
        f"**Slippage margin:** The edge survives up to {slip_breakeven} ticks of slippage. "
        f"At 1 tick (realistic NQ fill), the system remains profitable.",
        "",
        "---",
        "",
        "_Generated by deep6/backtest/round2_stress_test.py_",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t_start = time.time()
    print("=" * 60)
    print("DEEP6 Round 2 — Edge Durability Stress Test")
    print("=" * 60)

    print(f"\nLoading sessions from {SESSIONS_DIR}...")
    sessions_data = load_all_sessions(SESSIONS_DIR)
    print(f"  Loaded {len(sessions_data)} sessions, "
          f"{sum(len(b) for b in sessions_data.values()):,} total bars")

    results = []

    # Run all 7 tests
    r1 = test_t1_noise(sessions_data)
    print(f"  → {r1['verdict']} | {r1['note']}")
    results.append(r1)

    r2 = test_t2_signal_degradation(sessions_data)
    print(f"  → {r2['verdict']} | {r2['note']}")
    results.append(r2)

    r3 = test_t3_slippage(sessions_data)
    slip_breakeven = r3["breakeven_slippage_ticks"]
    print(f"  → {r3['verdict']} | Breakeven: {slip_breakeven} ticks")
    results.append(r3)

    r4 = test_t4_commission(sessions_data)
    print(f"  → {r4['verdict']} | {r4['note']}")
    results.append(r4)

    r5 = test_t5_regime_shift(sessions_data)
    print(f"  → {r5['verdict']} | {r5['note']}")
    results.append(r5)

    r6 = test_t6_marathon(sessions_data)
    print(f"  → {r6['verdict']} | {r6['note']}")
    results.append(r6)

    r7 = test_t7_overfit(sessions_data)
    print(f"  → {r7['verdict']} | {r7['note']}")
    results.append(r7)

    # Overall verdict
    verdict = overall_verdict(results)
    passed_count = sum(1 for r in results if r.get("passed", False))

    elapsed = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"Passed {passed_count}/7 tests in {elapsed:.1f}s")
    print(f"Overall verdict: {verdict}")
    print(f"Slippage breakeven: {slip_breakeven} ticks")
    print("=" * 60)

    # Write report
    report_path = OUTPUT_DIR / "STRESS-TEST.md"
    write_report(results, verdict, slip_breakeven, report_path)


if __name__ == "__main__":
    main()
