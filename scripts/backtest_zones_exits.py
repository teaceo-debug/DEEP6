#!/usr/bin/env python3
"""
Zone Exit Strategy Comparison
Variant D config (score>=6, 10:00-15:00 ET) — fixed entry, 8 different exits.

Exits tested:
  1. FIXED_1R        — TP = 1.0x risk (baseline)
  2. FIXED_1_5R      — TP = 1.5x risk
  3. FIXED_2R        — TP = 2.0x risk
  4. PARTIAL_HALF    — 50% exits at 1R, 50% trails to 2R; SL BE after first hit
  5. TRAIL_AFTER_1R  — after 1R profit SL trails 1R behind price
  6. BREAKEVEN_TRAIL — after 0.5R move SL to BE; TP at 1.5R
  7. ZONE_MID_TP     — TP at zone midpoint (variable); SL at distal+4t
  8. TIME_EXIT_15    — exit after 15 bars if neither TP(1R) nor SL hit

Run:
  python scripts/backtest_zones_exits.py
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Constants ───────────────────────────────────────────────────────────────────
TICK_SIZE    = 0.25
TICK_VALUE   = 5.0
COMMISSION   = 0.70
NQ_MIN_PRICE = 10_000.0
NQ_MAX_PRICE = 35_000.0

ROOT    = Path(__file__).resolve().parents[1]
CSV_1YR = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_TXT = ROOT / "scripts/results_zones_exits.txt"

RTH_START_MIN = 9 * 60 + 30
RTH_END_MIN   = 16 * 60 + 15

# Variant D fixed params
SCORE_GATE   = 6
TOD_START    = 10 * 60
TOD_END      = 15 * 60
WICK_THRESH  = 0.35
CLOSE_REJECT = 0.40
SL_BUF_TICKS = 4
MAX_ZONE_AGE = 500
MAX_TOUCHES  = 2
SMALL_BODY   = 0.50

EXIT_STRATEGIES = [
    "FIXED_1R",
    "FIXED_1_5R",
    "FIXED_2R",
    "PARTIAL_HALF",
    "TRAIL_AFTER_1R",
    "BREAKEVEN_TRAIL",
    "ZONE_MID_TP",
    "TIME_EXIT_15",
]


# ── Zone structures ─────────────────────────────────────────────────────────────

class ZoneKind(Enum):
    Supply = "Supply"; Demand = "Demand"; RBR = "RBR"; DBD = "DBD"


@dataclass
class Zone:
    kind: ZoneKind; top: float; bot: float
    formed_ts: object; score: int

    @property
    def is_sell(self):  return self.kind in (ZoneKind.Supply, ZoneKind.DBD)
    @property
    def proximal(self): return self.bot if self.is_sell else self.top
    @property
    def distal(self):   return self.top if self.is_sell else self.bot
    @property
    def midpoint(self): return (self.top + self.bot) / 2.0

    def sl_price(self) -> float:
        buf = SL_BUF_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    month: str; date: str; direction: str
    zone_kind: str; zone_score: int
    entry_px: float; exit_px: float
    sl_px: float; tp_px: float
    exit_reason: str; risk_ticks: float
    pnl: float
    exit_strategy: str = ""


# ── Math helpers ────────────────────────────────────────────────────────────────

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i-1] * (1.0 - k)
    return out


# ── Zone detection ──────────────────────────────────────────────────────────────

def detect_zones(bars: pd.DataFrame) -> List[Zone]:
    n = len(bars)
    if n < 3:
        return []
    O = bars["open"].values; H = bars["high"].values
    L = bars["low"].values;  C = bars["close"].values
    T = bars.index
    ema50 = _ema(C, 50)
    zones: List[Zone] = []; active: List[Zone] = []

    def _overlap(top, bot, kind):
        for z in active:
            if z.kind == kind and bot <= z.top + 1e-9 and top >= z.bot - 1e-9:
                return True
        return False

    def _score(dr, trend_ok):
        return (3 + (3 if dr >= 5 else 2 if dr >= 3 else 1 if dr >= 1.5 else 0)
                + 2 + (2 if trend_ok else 0))

    for i in range(2, n):
        pb = abs(C[i-2]-O[i-2]); bb = abs(C[i-1]-O[i-1]); nb = abs(C[i]-O[i])
        br = H[i-1]-L[i-1]
        if pb <= 0 or nb <= 0: continue
        svp = bb <= SMALL_BODY*pb; svn = bb <= SMALL_BODY*nb; tall = br >= TICK_SIZE
        if not (svp and svn and tall): continue
        pG = C[i-2] > O[i-2]; pR = C[i-2] < O[i-2]; ts = T[i]

        if pG and C[i-1] < O[i-1] and max(O[i], C[i]) <= H[i-1]+1e-9:
            top, bot = max(H[i-1],C[i-1]), min(H[i-1],C[i-1])
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.Supply):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                z = Zone(ZoneKind.Supply, top, bot, ts, _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and C[i-1] > O[i-1] and min(O[i], C[i]) >= L[i-1]-1e-9:
            top, bot = max(C[i-1],L[i-1]), min(C[i-1],L[i-1])
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.Demand):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                z = Zone(ZoneKind.Demand, top, bot, ts, _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pG and svp and svn and tall and max(O[i], C[i]) > H[i-1]+1e-9:
            top = O[i-1] if C[i-1] < O[i-1] else C[i-1]; bot = L[i-1]
            if top < bot: top, bot = bot, top
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.RBR):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                z = Zone(ZoneKind.RBR, top, bot, ts, _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and svp and svn and tall and min(O[i], C[i]) < L[i-1]-1e-9:
            top = H[i-1]; bot = C[i-1] if C[i-1] < O[i-1] else O[i-1]
            if top < bot: top, bot = bot, top
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.DBD):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                z = Zone(ZoneKind.DBD, top, bot, ts, _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

    return zones


# ── Data loading ────────────────────────────────────────────────────────────────

def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "bar_ts"})
    df["bar_ts"] = df["bar_ts"].dt.tz_localize("UTC") if df["bar_ts"].dt.tz is None else df["bar_ts"]
    df["bar_ts"] = df["bar_ts"] - pd.Timedelta(hours=4)
    df["bar_ts"] = df["bar_ts"].dt.tz_localize(None)
    df["session_date"] = df["bar_ts"].dt.date
    df["month"] = df["bar_ts"].dt.to_period("M").astype(str)
    df["minute"] = df["bar_ts"].dt.hour * 60 + df["bar_ts"].dt.minute
    df = df[(df["minute"] >= RTH_START_MIN) & (df["minute"] < RTH_END_MIN)].copy()
    df = df[(df["close"] > NQ_MIN_PRICE) & (df["close"] < NQ_MAX_PRICE)].copy()
    df = df.sort_values("bar_ts").reset_index(drop=True)
    return df


def resample_15m(df: pd.DataFrame) -> pd.DataFrame:
    d = df.set_index("bar_ts")
    agg = d[["open","high","low","close","volume"]].resample(
        "15min", closed="left", label="left"
    ).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna()
    return agg[(agg["open"] > NQ_MIN_PRICE) & (agg["close"] > NQ_MIN_PRICE)]


def compute_proxies(df: pd.DataFrame) -> dict:
    H = df["high"].values; L = df["low"].values
    O = df["open"].values; C = df["close"].values
    V = df["volume"].values.astype(float)
    vol_ema = _ema(V, 20)
    rng = np.where(H - L < TICK_SIZE, TICK_SIZE, H - L)
    uw = H - np.maximum(O, C)
    lw = np.minimum(O, C) - L
    return {
        "upper_wick_pct": uw / rng,
        "lower_wick_pct": lw / rng,
        "close_pct":      (C - L) / rng,
        "vol_ratio":      V / np.where(vol_ema > 0, vol_ema, 1.0),
        "tm":             df["bar_ts"].values,
        "O": O, "H": H, "L": L, "C": C,
        "month":          df["month"].values,
        "date":           df["session_date"].values,
    }


def _pnl(entry_px, exit_px, is_sell, n_contracts=1.0) -> float:
    raw_ticks = (entry_px - exit_px) if is_sell else (exit_px - entry_px)
    return (raw_ticks / TICK_SIZE) * TICK_VALUE * n_contracts - COMMISSION


# ── Exit simulators ─────────────────────────────────────────────────────────────

def _sim_exit(strategy: str, zone: Zone, px: dict, entry_j: int,
              entry_px: float, sl_px: float, risk: float, n1: int,
              entry_date) -> Tuple[float, str, float]:
    """
    Returns (exit_px, reason, tp_px_for_record).
    For PARTIAL_HALF: returns blended exit_px and combined PnL scaled to 1 contract.
    """
    is_sell = zone.is_sell
    max_hold = min(entry_j + 1 + 240, n1)

    if strategy == "FIXED_1R":
        tp = (entry_px - risk) if is_sell else (entry_px + risk)
        return _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp, is_sell, entry_date), tp

    elif strategy == "FIXED_1_5R":
        tp = (entry_px - 1.5 * risk) if is_sell else (entry_px + 1.5 * risk)
        return _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp, is_sell, entry_date), tp

    elif strategy == "FIXED_2R":
        tp = (entry_px - 2.0 * risk) if is_sell else (entry_px + 2.0 * risk)
        return _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp, is_sell, entry_date), tp

    elif strategy == "PARTIAL_HALF":
        return _sim_partial_half(px, entry_j, max_hold, entry_px, sl_px,
                                  risk, is_sell, entry_date)

    elif strategy == "TRAIL_AFTER_1R":
        tp = (entry_px - 1.0 * risk) if is_sell else (entry_px + 1.0 * risk)
        return _sim_trail_after_1r(px, entry_j, max_hold, entry_px, sl_px,
                                    tp, risk, is_sell, entry_date)

    elif strategy == "BREAKEVEN_TRAIL":
        tp = (entry_px - 1.5 * risk) if is_sell else (entry_px + 1.5 * risk)
        return _sim_breakeven_trail(px, entry_j, max_hold, entry_px, sl_px,
                                     tp, risk, is_sell, entry_date)

    elif strategy == "ZONE_MID_TP":
        # TP at zone midpoint; for sell = midpoint below entry, for buy = midpoint above
        tp = zone.midpoint
        # Sanity: if mid is beyond entry in wrong direction, fall back to 0.5R
        if is_sell and tp >= entry_px:
            tp = entry_px - 0.5 * risk
        elif not is_sell and tp <= entry_px:
            tp = entry_px + 0.5 * risk
        return _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp, is_sell, entry_date), tp

    elif strategy == "TIME_EXIT_15":
        tp = (entry_px - 1.0 * risk) if is_sell else (entry_px + 1.0 * risk)
        return _sim_time_exit(px, entry_j, max_hold, entry_px, sl_px,
                               tp, is_sell, entry_date, time_bars=15)

    raise ValueError(f"Unknown strategy: {strategy}")


def _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp, is_sell, entry_date):
    """Standard TP/SL with EOD expire."""
    for k in range(entry_j + 1, max_hold):
        bar_date = pd.Timestamp(px["tm"][k]).date()
        if bar_date > entry_date:
            return px["O"][k], "EXPIRE"
        if is_sell:
            if px["H"][k] >= sl_px - 1e-9:
                return sl_px, "SL"
            if px["L"][k] <= tp + 1e-9:
                return tp, "TP"
        else:
            if px["L"][k] <= sl_px + 1e-9:
                return sl_px, "SL"
            if px["H"][k] >= tp - 1e-9:
                return tp, "TP"
        if k == max_hold - 1:
            return px["C"][k], "EXPIRE"
    return px["C"][-1], "EXPIRE"


def _sim_partial_half(px, entry_j, max_hold, entry_px, sl_px,
                       risk, is_sell, entry_date):
    """
    Half exits at 1R; other half trails to 2R with SL moved to BE.
    Returns (blended_exit_px, reason, tp_for_record).
    We simulate the two halves independently and blend.
    """
    tp1 = (entry_px - risk) if is_sell else (entry_px + risk)
    tp2 = (entry_px - 2.0 * risk) if is_sell else (entry_px + 2.0 * risk)

    # Half 1: fixed 1R
    exit1, reason1 = _sim_fixed(px, entry_j, max_hold, entry_px, sl_px, tp1, is_sell, entry_date)

    # Half 2: after 1R hit → SL moves to BE; target 2R; else original SL
    # We check if tp1 was hit first — if so, trail half from that point
    sl2 = sl_px  # starts at original SL
    exit2 = None; reason2 = None
    tp1_hit = False; tp1_hit_idx = None

    for k in range(entry_j + 1, max_hold):
        bar_date = pd.Timestamp(px["tm"][k]).date()
        if bar_date > entry_date:
            exit2 = px["O"][k]; reason2 = "EXPIRE"; break
        if is_sell:
            if px["H"][k] >= sl2 - 1e-9:
                exit2 = sl2; reason2 = "SL" if not tp1_hit else "TRAIL"; break
            if not tp1_hit and px["L"][k] <= tp1 + 1e-9:
                # 1R hit — move SL to entry (breakeven)
                tp1_hit = True; sl2 = entry_px; tp1_hit_idx = k
            if tp1_hit and px["L"][k] <= tp2 + 1e-9:
                exit2 = tp2; reason2 = "TP2"; break
        else:
            if px["L"][k] <= sl2 + 1e-9:
                exit2 = sl2; reason2 = "SL" if not tp1_hit else "TRAIL"; break
            if not tp1_hit and px["H"][k] >= tp1 - 1e-9:
                tp1_hit = True; sl2 = entry_px; tp1_hit_idx = k
            if tp1_hit and px["H"][k] >= tp2 - 1e-9:
                exit2 = tp2; reason2 = "TP2"; break
        if k == max_hold - 1:
            exit2 = px["C"][k]; reason2 = "EXPIRE"; break

    if exit2 is None:
        exit2 = px["C"][-1]; reason2 = "EXPIRE"

    # Blend PnL: 0.5 contracts each
    # Return as a synthetic "blended" exit + reason tuple
    # We pack the half-trade PnLs into a pseudo-exit structure
    # Instead of blending exit prices (misleading for non-linear exits),
    # return a special marker and compute PnL externally.
    # Convention: return (exit1, exit2, reason1+"/"+reason2, tp1) as a 4-tuple
    return (exit1, exit2, f"{reason1}/{reason2}", tp1)


def _sim_trail_after_1r(px, entry_j, max_hold, entry_px, sl_px,
                          tp1, risk, is_sell, entry_date):
    """After price hits 1R, trail SL by 1R behind last extreme."""
    sl = sl_px
    trailing = False
    best_px = entry_px  # tracks best price seen after 1R hit

    for k in range(entry_j + 1, max_hold):
        bar_date = pd.Timestamp(px["tm"][k]).date()
        if bar_date > entry_date:
            return (px["O"][k], "EXPIRE"), tp1

        h, lo, c = px["H"][k], px["L"][k], px["C"][k]

        if is_sell:
            # Check SL first
            if h >= sl - 1e-9:
                return (sl, "TRAIL" if trailing else "SL"), tp1
            # Update trailing
            if trailing:
                if lo < best_px:
                    best_px = lo
                    sl = best_px + risk  # trail SL 1R above best low
            else:
                # Check if 1R hit
                if lo <= tp1 + 1e-9:
                    trailing = True
                    best_px = lo
                    sl = best_px + risk  # SL = 1R above best low
        else:
            # Check SL first
            if lo <= sl + 1e-9:
                return (sl, "TRAIL" if trailing else "SL"), tp1
            # Update trailing
            if trailing:
                if h > best_px:
                    best_px = h
                    sl = best_px - risk  # trail SL 1R below best high
            else:
                # Check if 1R hit
                if h >= tp1 - 1e-9:
                    trailing = True
                    best_px = h
                    sl = best_px - risk  # SL = 1R below best high

        if k == max_hold - 1:
            return (px["C"][k], "EXPIRE"), tp1

    return (px["C"][-1], "EXPIRE"), tp1


def _sim_breakeven_trail(px, entry_j, max_hold, entry_px, sl_px,
                          tp, risk, is_sell, entry_date):
    """After 0.5R profit move SL to BE; TP at 1.5R."""
    be_trigger = (entry_px - 0.5 * risk) if is_sell else (entry_px + 0.5 * risk)
    sl = sl_px
    be_hit = False

    for k in range(entry_j + 1, max_hold):
        bar_date = pd.Timestamp(px["tm"][k]).date()
        if bar_date > entry_date:
            return (px["O"][k], "EXPIRE"), tp

        h, lo = px["H"][k], px["L"][k]

        if is_sell:
            if h >= sl - 1e-9:
                return (sl, "SL" if not be_hit else "BE"), tp
            if not be_hit and lo <= be_trigger + 1e-9:
                be_hit = True; sl = entry_px  # move SL to BE
            if lo <= tp + 1e-9:
                return (tp, "TP"), tp
        else:
            if lo <= sl + 1e-9:
                return (sl, "SL" if not be_hit else "BE"), tp
            if not be_hit and h >= be_trigger - 1e-9:
                be_hit = True; sl = entry_px  # move SL to BE
            if h >= tp - 1e-9:
                return (tp, "TP"), tp

        if k == max_hold - 1:
            return (px["C"][k], "EXPIRE"), tp

    return (px["C"][-1], "EXPIRE"), tp


def _sim_time_exit(px, entry_j, max_hold, entry_px, sl_px,
                    tp, is_sell, entry_date, time_bars: int):
    """Exit at market after time_bars bars if neither TP nor SL hit."""
    expire_idx = entry_j + 1 + time_bars

    for k in range(entry_j + 1, max_hold):
        bar_date = pd.Timestamp(px["tm"][k]).date()
        if bar_date > entry_date:
            return (px["O"][k], "EXPIRE"), tp
        if is_sell:
            if px["H"][k] >= sl_px - 1e-9:
                return (sl_px, "SL"), tp
            if px["L"][k] <= tp + 1e-9:
                return (tp, "TP"), tp
        else:
            if px["L"][k] <= sl_px + 1e-9:
                return (sl_px, "SL"), tp
            if px["H"][k] >= tp - 1e-9:
                return (tp, "TP"), tp
        # Time stop
        if k >= expire_idx - 1:
            return (px["C"][k], "TIME"), tp
        if k == max_hold - 1:
            return (px["C"][k], "EXPIRE"), tp

    return (px["C"][-1], "EXPIRE"), tp


# ── Main scanner — all exit strategies ─────────────────────────────────────────

def scan_zone_all_exits(zone: Zone, px: dict, n1: int) -> Dict[str, Optional[Trade]]:
    """Scan one zone for entry signal, then simulate all exit strategies."""
    if zone.score < SCORE_GATE:
        return {s: None for s in EXIT_STRATEGIES}

    sl_px = zone.sl_price()
    tm = px["tm"]
    start_idx = int(np.searchsorted(tm, np.datetime64(zone.formed_ts), side="right"))
    if start_idx >= n1:
        return {s: None for s in EXIT_STRATEGIES}

    end_idx = min(start_idx + MAX_ZONE_AGE, n1)
    touch_count = 0

    for j in range(start_idx, end_idx):
        h, lo = px["H"][j], px["L"][j]
        o, c  = px["O"][j], px["C"][j]

        # Invalidation
        bmax, bmin = max(o, c), min(o, c)
        if zone.is_sell and bmax > zone.distal + 1e-9: break
        if not zone.is_sell and bmin < zone.distal - 1e-9: break

        # Touch count
        if h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9:
            touch_count += 1
            if touch_count > MAX_TOUCHES: break

        # TOD gate
        ts = pd.Timestamp(tm[j])
        bar_min = ts.hour * 60 + ts.minute
        if bar_min < TOD_START or bar_min >= TOD_END:
            continue

        # Proximal edge touch
        if zone.is_sell:
            if h < zone.proximal - 1e-9: continue
        else:
            if lo > zone.proximal + 1e-9: continue

        # Exhaustion wick
        rng = h - lo
        if rng < TICK_SIZE: continue
        uw_pct = (h - max(o, c)) / rng
        lw_pct = (min(o, c) - lo) / rng
        cp = (c - lo) / rng

        if zone.is_sell:
            if uw_pct < WICK_THRESH or cp > CLOSE_REJECT: continue
        else:
            if lw_pct < WICK_THRESH or cp < (1.0 - CLOSE_REJECT): continue

        # Entry on next bar open
        if j + 1 >= n1: continue
        entry_px = px["O"][j + 1]
        risk = abs(entry_px - sl_px)
        if risk < TICK_SIZE: continue

        entry_date = pd.Timestamp(tm[j+1]).date()
        risk_ticks = risk / TICK_SIZE

        # Simulate each exit strategy
        results: Dict[str, Optional[Trade]] = {}
        for strat in EXIT_STRATEGIES:
            result = _sim_exit(strat, zone, px, j + 1, entry_px, sl_px,
                               risk, n1, entry_date)

            if strat == "PARTIAL_HALF":
                # result = (exit1, exit2, reason_combo, tp1)
                exit1, exit2, reason_combo, tp_rec = result
                pnl1 = _pnl(entry_px, exit1, zone.is_sell, 0.5)
                pnl2 = _pnl(entry_px, exit2, zone.is_sell, 0.5)
                total_pnl = pnl1 + pnl2 - COMMISSION  # one extra comm for second leg
                # Use blended exit price for record keeping
                blended_exit = (exit1 + exit2) / 2.0
                results[strat] = Trade(
                    month=str(px["month"][j+1]),
                    date=str(entry_date),
                    direction="SHORT" if zone.is_sell else "LONG",
                    zone_kind=zone.kind.value,
                    zone_score=zone.score,
                    entry_px=entry_px, exit_px=blended_exit,
                    sl_px=sl_px, tp_px=tp_rec,
                    exit_reason=reason_combo,
                    risk_ticks=risk_ticks,
                    pnl=total_pnl,
                    exit_strategy=strat,
                )
            else:
                # result = ((exit_px, reason), tp) or (exit_px, reason), tp
                if isinstance(result[0], tuple):
                    (exit_px, reason), tp_rec = result
                else:
                    exit_px, reason = result[0], result[1]
                    tp_rec = result[2] if len(result) > 2 else 0.0
                    # For fixed exits, _sim_exit returns (exit_result, tp)
                    # but fixed returns directly a tuple not nested. Re-unpack:
                    # Actually _sim_fixed returns (exit_px, reason) directly.
                    # _sim_exit wraps it as: return _sim_fixed(...), tp
                    # So result = ((exit_px, reason), tp) — covered above.
                    # This branch won't be reached for correct returns.

                raw_pnl = _pnl(entry_px, exit_px, zone.is_sell, 1.0)
                results[strat] = Trade(
                    month=str(px["month"][j+1]),
                    date=str(entry_date),
                    direction="SHORT" if zone.is_sell else "LONG",
                    zone_kind=zone.kind.value,
                    zone_score=zone.score,
                    entry_px=entry_px, exit_px=exit_px,
                    sl_px=sl_px, tp_px=tp_rec if isinstance(tp_rec, float) else float(tp_rec),
                    exit_reason=reason,
                    risk_ticks=risk_ticks,
                    pnl=raw_pnl,
                    exit_strategy=strat,
                )
        return results

    return {s: None for s in EXIT_STRATEGIES}


def run_all_exits(zones: List[Zone], px: dict, n1: int) -> Dict[str, List[Trade]]:
    all_trades: Dict[str, List[Trade]] = {s: [] for s in EXIT_STRATEGIES}
    for zone in zones:
        result = scan_zone_all_exits(zone, px, n1)
        for strat, trade in result.items():
            if trade is not None:
                all_trades[strat].append(trade)
    return all_trades


# ── Metrics ─────────────────────────────────────────────────────────────────────

def metrics(trades: List[Trade]) -> dict:
    if not trades:
        return dict(n=0, net=0.0, wr=0.0, pf=0.0, sharpe=0.0,
                    avg=0.0, maxdd=0.0, exp=0.0, ll=0)
    pnls = np.array([t.pnl for t in trades])
    eq   = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    maxdd = float(np.max(peak - eq))
    wins  = pnls[pnls > 0]; loss = pnls[pnls < 0]
    gp = wins.sum() if len(wins) else 0.0
    gl = -loss.sum() if len(loss) else 0.0
    wr = len(wins) / len(pnls)
    pf = gp / gl if gl > 0 else 999.0
    mu = float(pnls.mean())
    sd = float(pnls.std(ddof=1)) if len(pnls) > 1 else 1.0
    sharpe = mu / sd * np.sqrt(252) if sd > 0 else 0.0
    avg_w = wins.mean()  if len(wins)  else 0.0
    avg_l = -loss.mean() if len(loss) else 0.0
    exp_  = wr * avg_w - (1.0 - wr) * avg_l
    ll = cur = 0
    for p in pnls:
        cur = cur + 1 if p < 0 else 0
        ll = max(ll, cur)
    return dict(n=len(trades), net=round(gp-gl,2), wr=round(wr*100,1),
                pf=round(pf,2), sharpe=round(sharpe,2), avg=round(mu,2),
                maxdd=round(maxdd,2), exp=round(exp_,2), ll=ll)


def exit_breakdown(trades: List[Trade]) -> str:
    if not trades: return ""
    cnt: dict = {}
    for t in trades:
        for r in t.exit_reason.split("/"):
            cnt[r] = cnt.get(r, 0) + 1
    return "  ".join(f"{k}={v}" for k, v in sorted(cnt.items()))


# ── Report writer ────────────────────────────────────────────────────────────────

def main() -> None:
    import time
    t0 = time.time()
    lines: List[str] = []
    W = lines.append

    W("=" * 95)
    W("  DEEP6 Zone Exits — Strategy Comparison")
    W("  Variant D: score>=6, 10:00-15:00 ET, wick=0.35, close_reject=0.40, sl=distal+4t")
    W("=" * 95)
    W("")

    print("Loading 1-year data...", flush=True)
    bars = load_bars(CSV_1YR)
    print(f"  {len(bars):,} 1m bars, {bars['session_date'].nunique()} sessions", flush=True)
    W(f"  1m bars: {len(bars):,}  |  sessions: {bars['session_date'].nunique()}")
    W(f"  Date range: {bars['session_date'].iloc[0]} to {bars['session_date'].iloc[-1]}")
    W("")

    print("Resampling to 15m and detecting zones...", flush=True)
    bars_15m = resample_15m(bars)
    zones = detect_zones(bars_15m)
    qualifying = [z for z in zones if z.score >= SCORE_GATE]
    W(f"  15m bars: {len(bars_15m):,}  |  zones detected: {len(zones)}  "
      f"|  score>={SCORE_GATE}: {len(qualifying)}")
    W("")

    print(f"  {len(zones)} zones — running all exit strategies...", flush=True)
    px = compute_proxies(bars)
    n1 = len(bars)

    all_trades = run_all_exits(zones, px, n1)

    # Verify FIXED_1R matches reference (should be 101 trades, 80.2% WR)
    ref = all_trades["FIXED_1R"]
    rm = metrics(ref)
    print(f"  FIXED_1R (reference check): {rm['n']} trades, WR {rm['wr']}%, "
          f"Net ${rm['net']:,.0f}", flush=True)
    W(f"  Reference check FIXED_1R: {rm['n']} trades, WR {rm['wr']}%, Net ${rm['net']:,.0f}")
    W("")

    # ── Summary comparison table ───────────────────────────────────────────────
    W("=" * 95)
    W("  SUMMARY — Exit Strategy Comparison (101 shared entry signals)")
    W("=" * 95)
    W("")
    W(f"  {'Strategy':<20} {'N':>5} {'WR%':>6} {'PF':>6} {'Sharpe':>7} "
      f"{'Net$':>10} {'Avg$':>7} {'MaxDD$':>9} {'LL':>4}  Exits")
    W("  " + "─" * 91)

    strategy_metrics = {}
    for strat in EXIT_STRATEGIES:
        trades = all_trades[strat]
        m = metrics(trades)
        strategy_metrics[strat] = m
        eb = exit_breakdown(trades)
        W(f"  {strat:<20} {m['n']:>5} {m['wr']:>6.1f} {m['pf']:>6.2f} "
          f"{m['sharpe']:>7.2f} {m['net']:>10,.0f} {m['avg']:>7.0f} "
          f"{m['maxdd']:>9,.0f} {m['ll']:>4}  {eb}")

    W("")

    # Rank by Net PnL
    ranked = sorted(EXIT_STRATEGIES, key=lambda s: strategy_metrics[s]["net"], reverse=True)
    W("  Ranked by Net PnL:")
    for rank, strat in enumerate(ranked, 1):
        m = strategy_metrics[strat]
        W(f"    #{rank}  {strat:<20}  Net ${m['net']:>9,.0f}  "
          f"WR {m['wr']:5.1f}%  PF {m['pf']:5.2f}  Sharpe {m['sharpe']:5.2f}")
    W("")

    # Rank by Profit Factor
    ranked_pf = sorted(EXIT_STRATEGIES, key=lambda s: strategy_metrics[s]["pf"], reverse=True)
    W("  Ranked by Profit Factor:")
    for rank, strat in enumerate(ranked_pf, 1):
        m = strategy_metrics[strat]
        W(f"    #{rank}  {strat:<20}  PF {m['pf']:5.2f}  "
          f"WR {m['wr']:5.1f}%  Net ${m['net']:>9,.0f}  MaxDD ${m['maxdd']:>8,.0f}")
    W("")

    # Rank by Sharpe
    ranked_sh = sorted(EXIT_STRATEGIES, key=lambda s: strategy_metrics[s]["sharpe"], reverse=True)
    W("  Ranked by Sharpe:")
    for rank, strat in enumerate(ranked_sh, 1):
        m = strategy_metrics[strat]
        W(f"    #{rank}  {strat:<20}  Sharpe {m['sharpe']:5.2f}  "
          f"Net ${m['net']:>9,.0f}  MaxDD ${m['maxdd']:>8,.0f}")
    W("")

    # ── Detailed per-strategy section ──────────────────────────────────────────
    W("=" * 95)
    W("  DETAILED BREAKDOWN — All 8 Strategies")
    W("=" * 95)

    for strat in EXIT_STRATEGIES:
        trades = all_trades[strat]
        m = strategy_metrics[strat]
        W("")
        W("─" * 70)
        W(f"  {strat}")
        W("─" * 70)
        W(f"  Trades: {m['n']}  WR: {m['wr']}%  PF: {m['pf']}  Sharpe: {m['sharpe']}")
        W(f"  Net PnL: ${m['net']:,.2f}  Avg/trade: ${m['avg']:,.2f}  "
          f"Max DD: ${m['maxdd']:,.2f}  Longest losing streak: {m['ll']}")
        W(f"  Expectancy: ${m['exp']:,.2f}/trade")
        W("")
        W(f"  Exit reasons: {exit_breakdown(trades)}")
        W("")

        # Zone type breakdown
        W("  Zone-type breakdown:")
        for zt in ["Supply", "Demand", "RBR", "DBD"]:
            sub = [t for t in trades if t.zone_kind == zt]
            if sub:
                sm = metrics(sub)
                W(f"    {zt:8s}: {sm['n']:3d} trades  WR {sm['wr']:5.1f}%  "
                  f"PF {sm['pf']:5.2f}  Net ${sm['net']:>9,.0f}  Avg ${sm['avg']:>6.0f}")
        W("")

        # Monthly breakdown
        all_months = sorted(set(t.month for t in trades))
        W("  Monthly breakdown:")
        W(f"  {'Month':<10} {'N':>4} {'WR%':>6} {'PF':>6} {'Net$':>9} {'Cum$':>9}")
        W("  " + "─" * 50)
        cumulative = 0.0
        for mo in all_months:
            sub = [t for t in trades if t.month == mo]
            sm = metrics(sub)
            cumulative += sm["net"]
            W(f"  {mo:<10} {sm['n']:>4} {sm['wr']:>6.1f} {sm['pf']:>6.2f} "
              f"{sm['net']:>9,.0f} {cumulative:>9,.0f}")
        months_pos = sum(1 for mo in all_months
                         if sum(t.pnl for t in trades if t.month == mo) > 0)
        W(f"  Profitable months: {months_pos}/{len(all_months)}")

    # ── Per-zone-type deep dive for top 2 strategies ───────────────────────────
    W("")
    W("=" * 95)
    top2 = ranked[:2]
    W(f"  PER-ZONE-TYPE DEEP ANALYSIS — Top 2 strategies: {top2[0]} vs {top2[1]}")
    W("=" * 95)

    for strat in top2:
        trades = all_trades[strat]
        W("")
        W(f"  [{strat}]")
        W(f"  {'Zone':<10} {'N':>4} {'WR%':>6} {'PF':>6} {'Sharpe':>7} "
          f"{'Net$':>9} {'Avg$':>7} {'MaxDD':>8}  Exit distribution")
        W("  " + "─" * 80)
        for zt in ["Supply", "Demand", "RBR", "DBD"]:
            sub = [t for t in trades if t.zone_kind == zt]
            if not sub:
                continue
            sm = metrics(sub)
            eb = exit_breakdown(sub)
            W(f"  {zt:<10} {sm['n']:>4} {sm['wr']:>6.1f} {sm['pf']:>6.2f} "
              f"{sm['sharpe']:>7.2f} {sm['net']:>9,.0f} {sm['avg']:>7.0f} "
              f"{sm['maxdd']:>8,.0f}  {eb}")

        # Direction breakdown per zone type
        W("")
        W(f"  [{strat}] — direction breakdown per zone:")
        for zt in ["Supply", "Demand", "RBR", "DBD"]:
            sub = [t for t in trades if t.zone_kind == zt]
            if not sub:
                continue
            longs  = [t for t in sub if t.direction == "LONG"]
            shorts = [t for t in sub if t.direction == "SHORT"]
            long_wr  = f"{sum(1 for t in longs  if t.pnl>0)/len(longs)*100:.0f}%" if longs  else "n/a"
            short_wr = f"{sum(1 for t in shorts if t.pnl>0)/len(shorts)*100:.0f}%" if shorts else "n/a"
            W(f"    {zt:<8}: LONG={len(longs)} WR={long_wr}  SHORT={len(shorts)} WR={short_wr}")
        W("")

    # ── Cross-strategy: zone type × exit strategy matrix ──────────────────────
    W("")
    W("=" * 95)
    W("  ZONE TYPE x EXIT STRATEGY MATRIX — Net PnL")
    W("=" * 95)
    W("")
    col_w = 14
    header = f"  {'Zone':<10}" + "".join(f"{s[:col_w]:>{col_w}}" for s in EXIT_STRATEGIES)
    W(header)
    W("  " + "─" * (10 + col_w * len(EXIT_STRATEGIES) + 2))
    for zt in ["Supply", "Demand", "RBR", "DBD", "ALL"]:
        row = f"  {zt:<10}"
        for strat in EXIT_STRATEGIES:
            trades = all_trades[strat]
            sub = trades if zt == "ALL" else [t for t in trades if t.zone_kind == zt]
            net = sum(t.pnl for t in sub) if sub else 0.0
            row += f"{net:>{col_w},.0f}"
        W(row)
    W("")

    W("=" * 95)
    W("  MATRIX — Win Rate %")
    W("=" * 95)
    W("")
    W(header)
    W("  " + "─" * (10 + col_w * len(EXIT_STRATEGIES) + 2))
    for zt in ["Supply", "Demand", "RBR", "DBD", "ALL"]:
        row = f"  {zt:<10}"
        for strat in EXIT_STRATEGIES:
            trades = all_trades[strat]
            sub = trades if zt == "ALL" else [t for t in trades if t.zone_kind == zt]
            if sub:
                wr = sum(1 for t in sub if t.pnl > 0) / len(sub) * 100
                row += f"{wr:>{col_w}.1f}"
            else:
                row += f"{'n/a':>{col_w}}"
        W(row)
    W("")

    # ── Final verdict ──────────────────────────────────────────────────────────
    W("=" * 95)
    W("  VERDICT")
    W("=" * 95)
    W("")
    best_net  = ranked[0]
    best_pf   = ranked_pf[0]
    best_sh   = ranked_sh[0]
    bm_net    = strategy_metrics[best_net]
    bm_pf     = strategy_metrics[best_pf]
    bm_sh     = strategy_metrics[best_sh]
    base      = strategy_metrics["FIXED_1R"]

    W(f"  Best by Net PnL   : {best_net}  "
      f"${bm_net['net']:,.0f}  (+${bm_net['net']-base['net']:,.0f} vs 1R baseline)")
    W(f"  Best by PF        : {best_pf}  PF {bm_pf['pf']:.2f}")
    W(f"  Best by Sharpe    : {best_sh}  {bm_sh['sharpe']:.2f}")
    W("")
    W("  BASELINE (FIXED_1R):")
    W(f"    N={base['n']}  WR={base['wr']}%  PF={base['pf']}  "
      f"Sharpe={base['sharpe']}  Net=${base['net']:,.0f}  MaxDD=${base['maxdd']:,.0f}")
    W("")

    for strat in ranked:
        m = strategy_metrics[strat]
        delta = m["net"] - base["net"]
        W(f"  {strat:<20}  Delta vs 1R: {'+' if delta>=0 else ''}{delta:,.0f}  "
          f"WR {m['wr']}%  PF {m['pf']}  Sharpe {m['sharpe']}  MaxDD ${m['maxdd']:,.0f}")
    W("")

    elapsed = time.time() - t0
    W(f"  Completed in {elapsed:.1f}s")
    W("=" * 95)

    result_txt = "\n".join(lines)
    OUT_TXT.write_text(result_txt, encoding="utf-8")

    for line in lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode())

    print(f"\nSaved -> {OUT_TXT}")


if __name__ == "__main__":
    main()
