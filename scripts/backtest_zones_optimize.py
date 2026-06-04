#!/usr/bin/env python3
"""
Zones + Exhaustion Parameter Optimizer
15m zone detection + EXHAUST_EDGE entry — systematic grid sweep

Phase 1: wick_thresh × tp_multiple × zone_score_gate  (6×6×4 = 144 combos)
Phase 2: Best Phase-1 params + close_reject × vol_filter × first_touch × tod
          (5×4×2×5 = 200 combos)
Phase 3: Walk-forward validation — train first 60%, test last 40%

Ranking metric: Sharpe ratio (min 15 trades, positive PnL required).
PF and expectancy used as tiebreakers.

Run (WSL):
  /mnt/c/Users/Tea/DEEP6/.venv/bin/python scripts/backtest_zones_optimize.py
"""

from __future__ import annotations

import itertools
import sys
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

TICK_SIZE    = 0.25
TICK_VALUE   = 5.0
COMMISSION   = 0.70
NQ_MIN_PRICE = 10_000.0
NQ_MAX_PRICE = 35_000.0

ROOT     = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/nq_3mo_1m.csv"
OUT_PATH = ROOT / "scripts/results_zones_optimize.txt"

DETECTION_TF   = "15m"        # locked — winner from prior study
SMALL_BODY     = 0.50
MIN_ZONE_TICKS = 1
MAX_ZONE_AGE   = 500          # 1m bars (~8 RTH hours)
MAX_TOUCHES    = 2

RTH_START_MIN = 9 * 60 + 30
RTH_END_MIN   = 16 * 60 + 15

MIN_TRADES_GATE = 15          # combos with fewer trades are excluded from ranking

# ── Enumerations ───────────────────────────────────────────────────────────────

class ZoneKind(Enum):
    Supply = "Supply"
    Demand = "Demand"
    RBR    = "RBR"
    DBD    = "DBD"


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class Zone:
    kind:        ZoneKind
    top:         float
    bot:         float
    formed_ts:   pd.Timestamp
    depart_ratio: float
    score:       int
    touch_count: int = 0

    @property
    def height(self):    return self.top - self.bot
    @property
    def mid(self):       return (self.top + self.bot) / 2.0
    @property
    def is_sell(self):   return self.kind in (ZoneKind.Supply, ZoneKind.DBD)
    @property
    def proximal(self):  return self.bot if self.is_sell else self.top
    @property
    def distal(self):    return self.top if self.is_sell else self.bot

    def sl_price(self, sl_buffer_ticks: int) -> float:
        buf = sl_buffer_ticks * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    date:      str
    direction: str
    zone_kind: str
    zone_score: int
    entry_px:  float
    exit_px:   float
    sl_px:     float
    tp_px:     float
    exit_reason: str
    risk_ticks: float
    pnl:       float


# ── EMA ────────────────────────────────────────────────────────────────────────

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1.0 - k)
    return out


# ── Zone detection (unchanged from backtest_zones_footprint.py) ────────────────

def detect_zones(bars: pd.DataFrame) -> List[Zone]:
    n = len(bars)
    if n < 3:
        return []
    O = bars["open"].values
    H = bars["high"].values
    L = bars["low"].values
    C = bars["close"].values
    T = bars.index
    ema50 = _ema(C, 50)
    zones: List[Zone] = []
    active: List[Zone] = []

    def _overlaps(top, bot, kind):
        for z in active:
            if z.kind != kind:
                continue
            if bot <= z.top + 1e-9 and top >= z.bot - 1e-9:
                return True
        return False

    def _score(dr, trend_ok):
        return (3 + (3 if dr >= 5 else 2 if dr >= 3 else 1 if dr >= 1.5 else 0)
                + 2 + (2 if trend_ok else 0))

    for i in range(2, n):
        pO, pC = O[i-2], C[i-2]
        bO, bC, bH, bL = O[i-1], C[i-1], H[i-1], L[i-1]
        nO, nC = O[i], C[i]
        nH, nL = H[i], L[i]
        pb = abs(pC - pO); bb = abs(bC - bO); nb = abs(nC - nO); br = bH - bL
        if pb <= 0 or nb <= 0:
            continue
        svp = bb <= SMALL_BODY * pb; svn = bb <= SMALL_BODY * nb
        tall = br >= MIN_ZONE_TICKS * TICK_SIZE
        if not (svp and svn and tall):
            continue
        pG, pR = pC > pO, pC < pO
        ts = T[i]

        if pG and (bC < bO) and max(nO, nC) <= bH + 1e-9:
            top, bot = max(bH, bC), min(bH, bC)
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Supply):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.Supply, top, bot, ts, dr,
                         _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and (bC > bO) and min(nO, nC) >= bL - 1e-9:
            top, bot = max(bC, bL), min(bC, bL)
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Demand):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.Demand, top, bot, ts, dr,
                         _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pG and svp and svn and tall and max(nO, nC) > bH + 1e-9:
            top = bO if (bC < bO) else bC; bot = bL
            if top < bot: top, bot = bot, top
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.RBR):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.RBR, top, bot, ts, dr,
                         _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and svp and svn and tall and min(nO, nC) < bL - 1e-9:
            top = bH; bot = bC if (bC < bO) else bO
            if top < bot: top, bot = bot, top
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.DBD):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.DBD, top, bot, ts, dr,
                         _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

    return zones


# ── Data loading + resampling ──────────────────────────────────────────────────

def load_bars() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "bar_ts"})
    df = df[["bar_ts", "open", "high", "low", "close", "volume"]].copy()
    df["bar_ts"] = df["bar_ts"].dt.tz_localize("UTC") if df["bar_ts"].dt.tz is None else df["bar_ts"]
    df["bar_ts"] = df["bar_ts"] - pd.Timedelta(hours=4)
    df["bar_ts"] = df["bar_ts"].dt.tz_localize(None)
    df["session_date"] = df["bar_ts"].dt.date
    df["minute"] = df["bar_ts"].dt.hour * 60 + df["bar_ts"].dt.minute
    df = df[(df["minute"] >= RTH_START_MIN) & (df["minute"] < RTH_END_MIN)].copy()
    df = df[(df["close"] > NQ_MIN_PRICE) & (df["close"] < NQ_MAX_PRICE)].copy()
    df = df.sort_values("bar_ts").reset_index(drop=True)
    return df


def resample_to_tf(df1m: pd.DataFrame, tf: str) -> pd.DataFrame:
    mins = {"5m": 5, "15m": 15, "30m": 30}[tf]
    df = df1m.copy()
    df = df.set_index("bar_ts")
    rule = f"{mins}min"
    agg = df[["open", "high", "low", "close", "volume"]].resample(rule, closed="left", label="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna()
    agg = agg[(agg["open"] > NQ_MIN_PRICE) & (agg["close"] > NQ_MIN_PRICE)]
    return agg


def compute_proxies(df1m: pd.DataFrame) -> pd.DataFrame:
    O = df1m["open"].values
    H = df1m["high"].values
    L = df1m["low"].values
    C = df1m["close"].values
    V = df1m["volume"].values.astype(float)
    vol_ema = _ema(V, 20)
    rng = np.where(H - L < TICK_SIZE, TICK_SIZE, H - L)
    upper_wick = H - np.maximum(O, C)
    lower_wick = np.minimum(O, C) - L
    close_pct = (C - L) / rng
    df = df1m.copy()
    df["vol_ema"]       = vol_ema
    df["vol_ratio"]     = V / np.where(vol_ema > 0, vol_ema, 1.0)
    df["upper_wick_pct"] = upper_wick / rng
    df["lower_wick_pct"] = lower_wick / rng
    df["close_pct"]     = close_pct
    return df


# ── Parametric exhaustion signal ───────────────────────────────────────────────

def sig_exhaust(row_dict, zone: Zone,
                wick_thresh: float,
                close_reject: float,
                vol_mult: float) -> bool:
    if vol_mult > 1.0 and row_dict["vol_ratio"] < vol_mult:
        return False
    if zone.is_sell:
        if row_dict["upper_wick_pct"] >= wick_thresh and row_dict["close_pct"] <= close_reject:
            return True
    else:
        if row_dict["lower_wick_pct"] >= wick_thresh and row_dict["close_pct"] >= (1.0 - close_reject):
            return True
    return False


# ── Trade simulation ────────────────────────────────────────────────────────────

def sim_trade(
    O1, H1, L1, C1, tm, start_idx, n1,
    zone: Zone, entry_px: float, sl_px: float, tp_px: float,
    entry_ts: pd.Timestamp,
) -> Optional[Trade]:
    entry_date = pd.Timestamp(entry_ts).date()
    max_hold = min(start_idx + 240, n1)
    for k in range(start_idx, max_hold):
        bar_date = pd.Timestamp(tm[k]).date()
        if bar_date > entry_date:
            exit_px = O1[k]; reason = "EXPIRE"
        elif zone.is_sell:
            if H1[k] >= sl_px - 1e-9:
                exit_px = sl_px; reason = "SL"
            elif L1[k] <= tp_px + 1e-9:
                exit_px = tp_px; reason = "TP"
            elif k == max_hold - 1:
                exit_px = C1[k]; reason = "EXPIRE"
            else:
                continue
        else:
            if L1[k] <= sl_px + 1e-9:
                exit_px = sl_px; reason = "SL"
            elif H1[k] >= tp_px - 1e-9:
                exit_px = tp_px; reason = "TP"
            elif k == max_hold - 1:
                exit_px = C1[k]; reason = "EXPIRE"
            else:
                continue

        risk_ticks = abs(entry_px - sl_px) / TICK_SIZE
        raw_pnl = ((entry_px - exit_px) if zone.is_sell else (exit_px - entry_px)) / TICK_SIZE * TICK_VALUE
        return Trade(
            date=str(entry_date),
            direction="SHORT" if zone.is_sell else "LONG",
            zone_kind=zone.kind.value,
            zone_score=zone.score,
            entry_px=entry_px, exit_px=exit_px, sl_px=sl_px, tp_px=tp_px,
            exit_reason=reason, risk_ticks=risk_ticks, pnl=raw_pnl - COMMISSION,
        )
    return None


# ── Zone scanner with parametric exhaustion ────────────────────────────────────

def scan_zone_exhaust(
    zone: Zone,
    O1, H1, L1, C1, tm,
    proxy: dict,
    n1: int,
    *,
    tp_multiple: float,
    sl_buffer_ticks: int,
    wick_thresh: float,
    close_reject: float,
    vol_mult: float,
    zone_score_gate: int,
    first_touch_only: bool,
    tod_start_min: int,
    tod_end_min: int,
) -> Optional[Trade]:
    if zone.score < zone_score_gate:
        return None
    sl_px = zone.sl_price(sl_buffer_ticks)
    start_idx = int(np.searchsorted(tm, np.datetime64(zone.formed_ts), side="right"))
    if start_idx >= n1:
        return None
    end_idx = min(start_idx + MAX_ZONE_AGE, n1)

    touch_count = 0
    for j in range(start_idx, end_idx):
        h, lo, o, c = H1[j], L1[j], O1[j], C1[j]

        # Zone invalidation
        body_max, body_min = max(o, c), min(o, c)
        if zone.is_sell and body_max > zone.distal + 1e-9:
            return None
        if not zone.is_sell and body_min < zone.distal - 1e-9:
            return None

        # Touch count gate
        enters = h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9
        if enters:
            touch_count += 1
            if touch_count > MAX_TOUCHES:
                return None
            if first_touch_only and touch_count > 1:
                return None

        # Time-of-day gate
        bar_min = pd.Timestamp(tm[j]).hour * 60 + pd.Timestamp(tm[j]).minute
        if bar_min < tod_start_min or bar_min >= tod_end_min:
            continue

        # Must touch proximal
        touches = (h >= zone.proximal - 1e-9) if zone.is_sell else (lo <= zone.proximal + 1e-9)
        if not touches:
            continue

        row = {
            "upper_wick_pct": proxy["upper_wick_pct"][j],
            "lower_wick_pct": proxy["lower_wick_pct"][j],
            "close_pct":      proxy["close_pct"][j],
            "vol_ratio":      proxy["vol_ratio"][j],
        }
        if not sig_exhaust(row, zone, wick_thresh, close_reject, vol_mult):
            continue

        if j + 1 >= n1:
            continue
        entry_px = O1[j + 1]
        risk = abs(entry_px - sl_px)
        if risk < TICK_SIZE:
            continue
        tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                else (entry_px + risk * tp_multiple)
        return sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                         entry_px, sl_px, tp_px, tm[j + 1])

    return None


# ── Run a single parameter combo ───────────────────────────────────────────────

def run_combo(
    bars1m_full: pd.DataFrame,
    zones_tf: List[Zone],
    O1, H1, L1, C1, tm,
    proxy: dict,
    n1: int,
    *,
    tp_multiple:      float,
    sl_buffer_ticks:  int,
    wick_thresh:      float,
    close_reject:     float,
    vol_mult:         float,
    zone_score_gate:  int,
    first_touch_only: bool,
    tod_start_min:    int,
    tod_end_min:      int,
    date_filter: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> List[Trade]:
    trades: List[Trade] = []
    for zone in zones_tf:
        if date_filter:
            start_dt, end_dt = date_filter
            if zone.formed_ts < start_dt or zone.formed_ts > end_dt:
                continue
        t = scan_zone_exhaust(
            zone, O1, H1, L1, C1, tm, proxy, n1,
            tp_multiple=tp_multiple,
            sl_buffer_ticks=sl_buffer_ticks,
            wick_thresh=wick_thresh,
            close_reject=close_reject,
            vol_mult=vol_mult,
            zone_score_gate=zone_score_gate,
            first_touch_only=first_touch_only,
            tod_start_min=tod_start_min,
            tod_end_min=tod_end_min,
        )
        if t is not None:
            trades.append(t)
    return trades


# ── Metrics ────────────────────────────────────────────────────────────────────

def metrics(trades: List[Trade]) -> dict:
    if not trades:
        return dict(n=0, net=0.0, wr=0.0, pf=0.0, sharpe=0.0,
                    avg=0.0, maxdd=0.0, exp=0.0, ll=0)
    pnls = np.array([t.pnl for t in trades])
    eq   = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    maxdd = float(np.max(peak - eq))
    wins  = pnls[pnls > 0]
    loss  = pnls[pnls < 0]
    gp = wins.sum()  if len(wins) else 0.0
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
    return dict(n=len(trades), net=round(gp - gl, 2), wr=round(wr*100, 1),
                pf=round(pf, 2), sharpe=round(sharpe, 2), avg=round(mu, 2),
                maxdd=round(maxdd, 2), exp=round(exp_, 2), ll=ll)


# ── Report helpers ─────────────────────────────────────────────────────────────

def fmt_row(params: dict, m: dict) -> str:
    return (
        f"  wk={params['wick_thresh']:.2f} cr={params['close_reject']:.2f} "
        f"vl={params['vol_mult']:.1f} tp={params['tp_multiple']:.1f} "
        f"sc≥{params['zone_score_gate']} ft={1 if params['first_touch_only'] else 0} "
        f"tod={params['tod_start_min']//60:02d}-{params['tod_end_min']//60:02d}  "
        f"│ n={m['n']:3d} WR={m['wr']:5.1f}% PF={m['pf']:5.2f} "
        f"Sharpe={m['sharpe']:5.2f} net=${m['net']:>9,.0f} exp=${m['exp']:>7.0f}"
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    lines: List[str] = []
    W = lines.append

    W("=" * 90)
    W("  DEEP6 Zone Entry Optimizer — 15m EXHAUST_EDGE")
    W("  NQ Futures  |  Jan 2 – Apr 10, 2026  |  RTH 1m bars")
    W("=" * 90)
    W("")

    print("Loading data…", flush=True)
    bars1m = load_bars()
    bars_tf = resample_to_tf(bars1m, DETECTION_TF)
    W(f"  1m bars: {len(bars1m):,}   |   {DETECTION_TF} bars: {len(bars_tf):,}")
    W("")

    # Detect zones on detection TF
    print(f"Detecting zones on {DETECTION_TF}…", flush=True)
    zones_tf = detect_zones(bars_tf)
    W(f"  Zones detected ({DETECTION_TF}): {len(zones_tf)}")
    W("")

    # Proxy columns on 1m bars
    fp = compute_proxies(bars1m)

    # Pre-extract numpy arrays for speed
    O1 = fp["open"].values
    H1 = fp["high"].values
    L1 = fp["low"].values
    C1 = fp["close"].values
    V1 = fp["volume"].values.astype(float)
    tm  = fp["bar_ts"].values                          # datetime64[us]
    proxy = {
        "upper_wick_pct": fp["upper_wick_pct"].values,
        "lower_wick_pct": fp["lower_wick_pct"].values,
        "close_pct":      fp["close_pct"].values,
        "vol_ratio":      fp["vol_ratio"].values,
    }
    n1 = len(O1)

    # Walk-forward split (60 / 40 by calendar date)
    all_dates = sorted(fp["session_date"].unique())
    split_idx = int(len(all_dates) * 0.60)
    train_cutoff = pd.Timestamp(all_dates[split_idx])
    test_start   = pd.Timestamp(all_dates[split_idx])
    test_end     = pd.Timestamp(all_dates[-1]) + pd.Timedelta(days=1)
    train_start  = pd.Timestamp(all_dates[0])
    W(f"  Walk-forward split:  train {all_dates[0]} → {all_dates[split_idx-1]}  "
      f"({split_idx} sessions)")
    W(f"                        test  {all_dates[split_idx]} → {all_dates[-1]}  "
      f"({len(all_dates)-split_idx} sessions)")
    W("")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1 — wick_thresh × tp_multiple × zone_score_gate
    # ─────────────────────────────────────────────────────────────────────────
    W("═" * 90)
    W("  PHASE 1 — Wick threshold × TP multiple × Zone score gate")
    W("  Fixed: close_reject=0.55, vol_mult=1.0, first_touch=False, tod=09:30-16:15")
    W("═" * 90)
    W("")

    WICK_THRESH   = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    TP_MULTIPLES  = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    SCORE_GATES   = [0, 4, 6, 8]

    p1_results: List[Tuple[dict, dict]] = []
    combos_p1 = list(itertools.product(WICK_THRESH, TP_MULTIPLES, SCORE_GATES))
    print(f"Phase 1: {len(combos_p1)} combos…", flush=True)

    for wt, tp, sg in combos_p1:
        params = dict(
            wick_thresh=wt, tp_multiple=tp, zone_score_gate=sg,
            close_reject=0.55, vol_mult=1.0, first_touch_only=False,
            sl_buffer_ticks=4, tod_start_min=RTH_START_MIN, tod_end_min=RTH_END_MIN,
        )
        tr = run_combo(
            bars1m, zones_tf, O1, H1, L1, C1, tm, proxy, n1, **params,
            date_filter=(train_start, train_cutoff),
        )
        m = metrics(tr)
        if m["n"] >= MIN_TRADES_GATE and m["net"] > 0:
            p1_results.append((params, m))

    p1_results.sort(key=lambda x: -x[1]["sharpe"])
    W(f"  Qualifying combos (n≥{MIN_TRADES_GATE}, net>0): {len(p1_results)}")
    W("")
    W(f"  {'Rank':>4}  {'wick':>5} {'cr':>5} {'vl':>4} {'tp':>4} {'sc':>4} "
      f"{'ft':>3} {'tod':>8}  │  "
      f"{'N':>4} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'net$':>10} {'exp$':>8}")
    W("  " + "─" * 86)
    for rank, (p, m) in enumerate(p1_results[:30], 1):
        W(f"  {rank:4d}  {fmt_row(p, m)}")
    W("")

    if not p1_results:
        W("  No qualifying combos found in Phase 1.")
        (OUT_PATH).write_text("\n".join(lines), encoding="utf-8")
        return

    best_p1 = p1_results[0][0]
    W(f"  → Best Phase-1 params: wick={best_p1['wick_thresh']} "
      f"tp={best_p1['tp_multiple']} score≥{best_p1['zone_score_gate']}")
    W("")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2 — Refine: close_reject × vol_mult × first_touch × tod
    # ─────────────────────────────────────────────────────────────────────────
    W("═" * 90)
    W("  PHASE 2 — Rejection close × Volume gate × First-touch × Time-of-day")
    W(f"  Fixed: wick={best_p1['wick_thresh']} tp={best_p1['tp_multiple']} "
      f"score≥{best_p1['zone_score_gate']}")
    W("═" * 90)
    W("")

    CLOSE_REJECT = [0.40, 0.45, 0.50, 0.55, 0.60]
    VOL_MULT     = [1.0, 1.3, 1.5, 2.0]
    FIRST_TOUCH  = [False, True]
    TOD_WINDOWS  = [
        (RTH_START_MIN, RTH_END_MIN),           # 09:30–16:15 (full RTH)
        (9*60+30, 12*60),                        # 09:30–12:00 (morning only)
        (10*60, 14*60+30),                       # 10:00–14:30 (avoid open/close)
        (9*60+30, 13*60),                        # 09:30–13:00
        (10*60+30, 15*60),                       # 10:30–15:00
    ]

    p2_results: List[Tuple[dict, dict]] = []
    combos_p2 = list(itertools.product(CLOSE_REJECT, VOL_MULT, FIRST_TOUCH, TOD_WINDOWS))
    print(f"Phase 2: {len(combos_p2)} combos…", flush=True)

    for cr, vm, ft, (ts, te) in combos_p2:
        params = dict(
            wick_thresh=best_p1["wick_thresh"],
            tp_multiple=best_p1["tp_multiple"],
            zone_score_gate=best_p1["zone_score_gate"],
            close_reject=cr, vol_mult=vm,
            first_touch_only=ft, sl_buffer_ticks=4,
            tod_start_min=ts, tod_end_min=te,
        )
        tr = run_combo(
            bars1m, zones_tf, O1, H1, L1, C1, tm, proxy, n1, **params,
            date_filter=(train_start, train_cutoff),
        )
        m = metrics(tr)
        if m["n"] >= MIN_TRADES_GATE and m["net"] > 0:
            p2_results.append((params, m))

    p2_results.sort(key=lambda x: -x[1]["sharpe"])
    W(f"  Qualifying combos (n≥{MIN_TRADES_GATE}, net>0): {len(p2_results)}")
    W("")
    W(f"  {'Rank':>4}  {'wick':>5} {'cr':>5} {'vl':>4} {'tp':>4} {'sc':>4} "
      f"{'ft':>3} {'tod':>8}  │  "
      f"{'N':>4} {'WR%':>6} {'PF':>6} {'Sharpe':>7} {'net$':>10} {'exp$':>8}")
    W("  " + "─" * 86)
    for rank, (p, m) in enumerate(p2_results[:30], 1):
        W(f"  {rank:4d}  {fmt_row(p, m)}")
    W("")

    best_all = p2_results[0][0] if p2_results else best_p1
    bm = metrics(run_combo(
        bars1m, zones_tf, O1, H1, L1, C1, tm, proxy, n1, **best_all,
        date_filter=(train_start, train_cutoff),
    ))
    W(f"  → Best overall: wick={best_all['wick_thresh']} "
      f"cr={best_all['close_reject']} vl={best_all['vol_mult']} "
      f"tp={best_all['tp_multiple']} sc≥{best_all['zone_score_gate']} "
      f"ft={1 if best_all['first_touch_only'] else 0} "
      f"tod={best_all['tod_start_min']//60:02d}-{best_all['tod_end_min']//60:02d}")
    W(f"     TRAIN: n={bm['n']} WR={bm['wr']}% PF={bm['pf']} "
      f"Sharpe={bm['sharpe']} net=${bm['net']:,.0f}")
    W("")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3 — Walk-forward validation
    # ─────────────────────────────────────────────────────────────────────────
    W("═" * 90)
    W("  PHASE 3 — Walk-forward Validation (best combo on held-out test data)")
    W("═" * 90)
    W("")

    # Validate top-5 combos from Phase 2 on test set
    top_n = min(5, len(p2_results))
    W(f"  Validating top {top_n} Phase-2 combos on test set "
      f"({all_dates[split_idx]} → {all_dates[-1]})…")
    W("")

    wf_rows = []
    for rank, (p, train_m) in enumerate(p2_results[:top_n], 1):
        test_trades = run_combo(
            bars1m, zones_tf, O1, H1, L1, C1, tm, proxy, n1, **p,
            date_filter=(test_start, test_end),
        )
        test_m = metrics(test_trades)
        W(f"  Rank-{rank}  wick={p['wick_thresh']} cr={p['close_reject']} "
          f"vl={p['vol_mult']} tp={p['tp_multiple']} "
          f"sc≥{p['zone_score_gate']} ft={1 if p['first_touch_only'] else 0} "
          f"tod={p['tod_start_min']//60:02d}-{p['tod_end_min']//60:02d}")
        W(f"    TRAIN: n={train_m['n']:3d} WR={train_m['wr']:5.1f}% "
          f"PF={train_m['pf']:5.2f} Sharpe={train_m['sharpe']:5.2f} "
          f"net=${train_m['net']:>9,.0f}   "
          f"MaxDD=${train_m['maxdd']:>8,.0f}   LL={train_m['ll']}")
        W(f"    TEST:  n={test_m['n']:3d} WR={test_m['wr']:5.1f}% "
          f"PF={test_m['pf']:5.2f} Sharpe={test_m['sharpe']:5.2f} "
          f"net=${test_m['net']:>9,.0f}   "
          f"MaxDD=${test_m['maxdd']:>8,.0f}   LL={test_m['ll']}")
        dd_pct = (test_m["sharpe"] / train_m["sharpe"] - 1.0) * 100 if train_m["sharpe"] > 0 else -99
        W(f"    Sharpe decay: {dd_pct:+.1f}%   "
          f"{'✓ HOLD' if test_m['pf'] >= 1.5 and test_m['net'] > 0 else '⚠ WATCH'}")
        W("")
        wf_rows.append((rank, p, train_m, test_m))

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3b — Full-period run on the best validated combo
    # ─────────────────────────────────────────────────────────────────────────
    W("─" * 90)
    W("  PHASE 3b — Best combo, full period (train + test combined)")
    W("─" * 90)
    W("")

    # Pick best walk-forward: highest test Sharpe with PF≥1.0
    valid_wf = [(r, p, tm_, te_) for r, p, tm_, te_ in wf_rows
                if te_["pf"] >= 1.0 and te_["net"] > 0]
    winner_p = valid_wf[0][1] if valid_wf else wf_rows[0][1]

    full_trades = run_combo(
        bars1m, zones_tf, O1, H1, L1, C1, tm, proxy, n1, **winner_p,
    )
    full_m = metrics(full_trades)

    W(f"  Winner: wick={winner_p['wick_thresh']} cr={winner_p['close_reject']} "
      f"vl={winner_p['vol_mult']} tp={winner_p['tp_multiple']} "
      f"sc≥{winner_p['zone_score_gate']} ft={1 if winner_p['first_touch_only'] else 0} "
      f"tod={winner_p['tod_start_min']//60:02d}-{winner_p['tod_end_min']//60:02d}")
    W("")
    W(f"  Full period (all {len(all_dates)} sessions):")
    W(f"    Trades:       {full_m['n']}")
    W(f"    Win Rate:     {full_m['wr']}%")
    W(f"    Profit Factor:{full_m['pf']}")
    W(f"    Sharpe:       {full_m['sharpe']}")
    W(f"    Net PnL:      ${full_m['net']:,.2f}")
    W(f"    Avg per trade:${full_m['avg']:,.2f}")
    W(f"    Max DrawDown: ${full_m['maxdd']:,.2f}")
    W(f"    Longest Streak:{full_m['ll']} losses")
    W(f"    Expectancy:   ${full_m['exp']:,.2f}")
    W("")

    # Zone-type breakdown on full period
    W("  Zone-type breakdown:")
    for zt in ["Supply", "Demand", "RBR", "DBD"]:
        sub = [t for t in full_trades if t.zone_kind == zt]
        if sub:
            sm = metrics(sub)
            W(f"    {zt:8s}: {sm['n']:3d} trades  WR {sm['wr']:5.1f}%  "
              f"PF {sm['pf']:4.2f}  net ${sm['net']:>9,.0f}")
    W("")

    # Score breakdown on full period
    W("  Zone-score breakdown:")
    for sg in [0, 4, 6, 8, 10]:
        sub = [t for t in full_trades if t.zone_score >= sg]
        if sub:
            sm = metrics(sub)
            W(f"    score≥{sg}: {sm['n']:3d} trades  WR {sm['wr']:5.1f}%  "
              f"PF {sm['pf']:4.2f}  net ${sm['net']:>9,.0f}")
    W("")

    elapsed = time.time() - t0
    W(f"  Completed in {elapsed:.1f}s")
    W("=" * 90)

    result_txt = "\n".join(lines)
    OUT_PATH.write_text(result_txt, encoding="utf-8")
    print(result_txt)
    print(f"\nSaved → {OUT_PATH}")


if __name__ == "__main__":
    main()
