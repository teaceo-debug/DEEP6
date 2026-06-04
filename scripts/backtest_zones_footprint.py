#!/usr/bin/env python3
"""
Institutional Zones + Footprint Signals — Combined Entry Model Backtest

Combines InstitutionalZones_MTF v4.5 zone detection with OHLCV-based proxies
for DEEP6 absorption and exhaustion signals.

Signal proxies (from actual DEEP6 signal definitions):
  ABS-04 (Effort vs Result):   vol > 1.5× ema  AND  range < 0.30 × ATR
  ABS-01 (Classic Absorption): wick vol balance proxy via close position
  EXH-02 (Exhaustion Print):   large wick (>= 35%) at bar extreme
  EXH-05 (Fading Momentum):    delta proxy opposes price direction
  EXH-06 (Bid/Ask Fade):       volume declining on zone approach

Entry models:
  PROXIMAL_BASE   baseline — limit at proximal edge, no footprint filter
  ABS_EDGE        absorption bar enters zone (high vol + narrow range + aligned close)
  EXHAUST_EDGE    exhaustion wick into zone (EXH-02 proxy, wick >= 35%)
  ABS_OR_EXHAUST  either absorption or exhaustion signal
  ABS_INSIDE      absorption bar closes inside zone (strongest confirmation)
  VOL_FADE        volume climax at zone then fading bar (EXH-05/06 proxy)
  COMPOSITE       absorption + vol >= 2x + zone score >= 6 + wick confirm

Run (WSL):
  /mnt/c/Users/Tea/DEEP6/.venv/bin/python scripts/backtest_zones_footprint.py
"""

import sys
import time
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0
COMMISSION_RT = 0.70

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/nq_3mo_1m.csv"
OUT_PATH = ROOT / "scripts/results_zones_footprint.txt"

# Zone detection params
SMALL_BODY_RATIO = 0.50
MIN_ZONE_TICKS = 1
SL_BUFFER_TICKS = 4
MAX_ZONE_AGE_1M = 500
MAX_TOUCHES = 2

# Footprint proxy thresholds
# NOTE: ATR on RTH-filtered 1m bars is inflated by cross-session gaps,
# so we use body_ratio (body / range) instead of range/ATR — this maps
# directly to what absorption looks like: high volume + small body =
# balanced tug-of-war at price level (ABS-01/ABS-04 combined proxy).
ABS_VOL_MULT = 1.3           # elevated volume (ABS-04: 1.5x, relaxed for OHLCV)
ABS_BODY_RATIO = 0.40        # body < 40% of range = indecision / balanced delta
ABS_CLOSE_PCT_SUPPLY = 0.55  # close in upper half = buyers absorbed by sellers
ABS_CLOSE_PCT_DEMAND = 0.45  # close in lower half = sellers absorbed by buyers
EXHAUST_WICK_PCT = 0.35      # EXH-02: wick >= 35% of bar range
VOL_CLIMAX_MULT = 1.8        # VOL_FADE: climax bar needs 1.8× vol ema
VOL_FADE_RATIO = 0.75        # VOL_FADE: fade bar must be < 75% of climax vol
COMPOSITE_VOL_MULT = 1.5     # COMPOSITE: requires 1.5× vol
COMPOSITE_BODY_RATIO = 0.35  # COMPOSITE: tighter body filter
COMPOSITE_SCORE_MIN = 6      # COMPOSITE: zone score filter

# Test parameters
TP_RISK_MULTIPLES = [1.5, 2.0, 3.0]
DETECTION_TFS = ["5m", "15m", "30m"]

RTH_START_MIN = 9 * 60 + 30
RTH_END_MIN = 16 * 60 + 15


# ── Zone structures ────────────────────────────────────────────────────────

class ZoneKind(Enum):
    Supply = "Supply"
    Demand = "Demand"
    RBR = "RBR"
    DBD = "DBD"


class EntryModel(Enum):
    PROXIMAL_BASE  = "PROXIMAL_BASE"   # baseline: no footprint filter
    ABS_EDGE       = "ABS_EDGE"        # absorption at proximal edge
    EXHAUST_EDGE   = "EXHAUST_EDGE"    # exhaustion wick at edge
    ABS_OR_EXHAUST = "ABS_OR_EXHAUST"  # either signal
    ABS_INSIDE     = "ABS_INSIDE"      # absorption + close inside zone
    VOL_FADE       = "VOL_FADE"        # vol climax then fade
    COMPOSITE      = "COMPOSITE"       # abs + 2× vol + quality zone


@dataclass
class Zone:
    kind: ZoneKind
    top: float
    bot: float
    formed_ts: pd.Timestamp
    depart_ratio: float
    score: int
    touch_count: int = 0

    @property
    def height(self) -> float:
        return self.top - self.bot

    @property
    def mid(self) -> float:
        return (self.top + self.bot) / 2.0

    @property
    def is_sell(self) -> bool:
        return self.kind in (ZoneKind.Supply, ZoneKind.DBD)

    @property
    def proximal(self) -> float:
        return self.bot if self.is_sell else self.top

    @property
    def distal(self) -> float:
        return self.top if self.is_sell else self.bot

    def sl_price(self) -> float:
        buf = SL_BUFFER_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    date: str
    direction: str
    model: str
    tf: str
    zone_kind: str
    zone_score: int
    signal_type: str    # what footprint signal fired
    entry_price: float
    exit_price: float
    sl_price: float
    tp_price: float
    exit_reason: str
    risk_ticks: float
    pnl: float


# ── Math utils ─────────────────────────────────────────────────────────────

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i - 1] * (1.0 - k)
    return out


# ── Footprint proxy computation ─────────────────────────────────────────────

def compute_proxies(bars: pd.DataFrame) -> pd.DataFrame:
    """
    Add DEEP6 footprint proxy columns to a 1m OHLCV DataFrame.
    All calculations are causal (look back only).

    Uses body_ratio (body / range) as the absorption proxy instead of
    range/ATR — ATR on RTH-filtered 1m data is inflated by cross-session
    gaps, making the DEEP6 ABS-04 range/ATR gate unusable without
    intraday ATR resets.
    """
    O = bars["open"].values
    H = bars["high"].values
    L = bars["low"].values
    C = bars["close"].values
    V = bars["volume"].values.astype(float)

    # Volume EMA(20)
    vol_ema = _ema(V, 20)

    # Bar geometry
    rng = H - L
    rng = np.where(rng < TICK_SIZE, TICK_SIZE, rng)  # floor at 1 tick
    body = np.abs(C - O)
    body_ratio = body / rng  # 0 = doji, 1 = no wicks

    # Close position in range: 0 = at low, 1 = at high
    close_pct = (C - L) / rng

    # Delta proxy: -1 (all selling) to +1 (all buying)
    delta_proxy = 2.0 * close_pct - 1.0

    # Wick ratios
    upper_wick = H - np.maximum(O, C)
    lower_wick = np.minimum(O, C) - L
    upper_wick_pct = upper_wick / rng
    lower_wick_pct = lower_wick / rng

    # Volume ratio vs EMA
    vol_ratio = V / np.where(vol_ema > 0, vol_ema, 1.0)

    df = bars.copy()
    df["vol_ema"] = vol_ema
    df["rng"] = rng
    df["body_ratio"] = body_ratio
    df["close_pct"] = close_pct
    df["delta_proxy"] = delta_proxy
    df["upper_wick_pct"] = upper_wick_pct
    df["lower_wick_pct"] = lower_wick_pct
    df["vol_ratio"] = vol_ratio

    return df


# ── Signal detection functions ──────────────────────────────────────────────

def _touches_zone(H: float, L: float, zone: Zone) -> bool:
    """Bar enters the zone (reaches proximal edge)."""
    if zone.is_sell:
        return H >= zone.proximal - 1e-9
    else:
        return L <= zone.proximal + 1e-9


def _is_invalidated(body_max: float, body_min: float, zone: Zone) -> bool:
    """Body close through distal edge — zone is dead."""
    if zone.is_sell:
        return body_max > zone.distal + 1e-9
    else:
        return body_min < zone.distal - 1e-9


def sig_absorption(row, zone: Zone) -> Tuple[bool, str]:
    """
    ABS-01/ABS-04 combined proxy (OHLCV-adapted).
    High volume + small body (balanced tug-of-war) + close aligned.

    ABS-04 (Effort vs Result): high volume + narrow range → OHLCV proxy:
      body_ratio < 0.40 (small body = result is small despite volume effort)
    ABS-01 (Classic Absorption): close position indicates which side absorbed:
      supply → close near top = buyers active = being absorbed by sellers
      demand → close near bottom = sellers active = being absorbed by buyers
    """
    if row["vol_ratio"] < ABS_VOL_MULT:
        return False, ""
    if row["body_ratio"] > ABS_BODY_RATIO:
        return False, ""
    if zone.is_sell and row["close_pct"] >= ABS_CLOSE_PCT_SUPPLY:
        return True, "ABS_EDGE"
    if not zone.is_sell and row["close_pct"] <= ABS_CLOSE_PCT_DEMAND:
        return True, "ABS_EDGE"
    return False, ""


def sig_exhaustion_wick(row, zone: Zone) -> Tuple[bool, str]:
    """
    EXH-02 (Exhaustion Print) proxy.
    Large wick at bar extreme with rejection close.
    For supply: large upper wick (buyers exhausted at top).
    For demand: large lower wick (sellers exhausted at bottom).
    """
    if zone.is_sell:
        # Large upper wick = buyers pushed high, rejected
        if row["upper_wick_pct"] >= EXHAUST_WICK_PCT:
            # Close should be below the midpoint (confirmed rejection)
            if row["close_pct"] <= 0.55:
                return True, "EXHAUST_WICK"
    else:
        # Large lower wick = sellers pushed low, rejected
        if row["lower_wick_pct"] >= EXHAUST_WICK_PCT:
            # Close should be above the midpoint
            if row["close_pct"] >= 0.45:
                return True, "EXHAUST_WICK"
    return False, ""


def sig_abs_inside(row, zone: Zone, C: float) -> Tuple[bool, str]:
    """
    ABS_INSIDE: absorption bar that also closes INSIDE the zone.
    Absorption at zone interior = strong confirmation of absorption.
    """
    close_inside = zone.bot - 1e-9 <= C <= zone.top + 1e-9
    if not close_inside:
        return False, ""
    found, _ = sig_absorption(row, zone)
    if found:
        return True, "ABS_INSIDE"
    return False, ""


def sig_vol_fade(
    rows,  # list of last 2 rows (rows[-2] = signal bar, rows[-1] = current)
    zone: Zone,
    H_prev: float, L_prev: float, C_prev: float, V_prev: float,
    H_curr: float, L_curr: float, C_curr: float, V_curr: float,
    vol_ema: float,
) -> Tuple[bool, str]:
    """
    VOL_FADE: Two-bar pattern.
    Bar 1 (prev): volume climax (vol > 2× ema) while bar enters zone.
    Bar 2 (curr): volume fades (vol < 70% of bar1 vol) AND direction reversal.
    Models EXH-05 (Fading Momentum) and EXH-06 (Bid/Ask Fade).
    """
    if vol_ema <= 0:
        return False, ""
    # Bar 1: climax
    vol1_ratio = V_prev / vol_ema
    if vol1_ratio < VOL_CLIMAX_MULT:
        return False, ""
    # Bar 1 must enter zone
    if not _touches_zone(H_prev, L_prev, zone):
        return False, ""
    # Bar 2: fade (volume drops significantly)
    if V_curr >= V_prev * VOL_FADE_RATIO:
        return False, ""
    # Bar 2: reversal direction
    if zone.is_sell:
        # Supply: bar1 was pushing UP (bullish close), bar2 closes DOWN (reversal)
        bar1_bullish = C_prev > (H_prev + L_prev) / 2
        bar2_reversal = C_curr < C_prev
        if bar1_bullish and bar2_reversal:
            return True, "VOL_FADE"
    else:
        # Demand: bar1 was pushing DOWN, bar2 closes UP (reversal)
        bar1_bearish = C_prev < (H_prev + L_prev) / 2
        bar2_reversal = C_curr > C_prev
        if bar1_bearish and bar2_reversal:
            return True, "VOL_FADE"
    return False, ""


def sig_composite(row, zone: Zone, C: float) -> Tuple[bool, str]:
    """
    COMPOSITE: Absorption + stronger volume filter + zone quality gate.
    Requires vol >= 1.5×, body_ratio < 0.35, close aligned, score >= 6.
    Optionally adds wick into zone for maximum conviction.
    """
    if zone.score < COMPOSITE_SCORE_MIN:
        return False, ""
    if row["vol_ratio"] < COMPOSITE_VOL_MULT:
        return False, ""
    if row["body_ratio"] > COMPOSITE_BODY_RATIO:
        return False, ""
    dir_ok = (zone.is_sell and row["close_pct"] >= ABS_CLOSE_PCT_SUPPLY) or \
             (not zone.is_sell and row["close_pct"] <= ABS_CLOSE_PCT_DEMAND)
    if not dir_ok:
        return False, ""
    if zone.is_sell and row["upper_wick_pct"] >= 0.15:
        return True, "COMPOSITE_ABS+WICK"
    if not zone.is_sell and row["lower_wick_pct"] >= 0.15:
        return True, "COMPOSITE_ABS+WICK"
    return True, "COMPOSITE_ABS"


# ── Zone detection ─────────────────────────────────────────────────────────

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

        pb = abs(pC - pO)
        bb = abs(bC - bO)
        nb = abs(nC - nO)
        br = bH - bL

        if pb <= 0 or nb <= 0:
            continue

        svp = bb <= SMALL_BODY_RATIO * pb
        svn = bb <= SMALL_BODY_RATIO * nb
        tall = br >= MIN_ZONE_TICKS * TICK_SIZE
        if not (svp and svn and tall):
            continue

        pG, pR = pC > pO, pC < pO
        bR, bG = bC < bO, bC > bO
        ts = T[i]

        if pG and bR and max(nO, nC) <= bH + 1e-9:
            top, bot = max(bH, bC), min(bH, bC)
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Supply):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.Supply, top, bot, ts, dr,
                         _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and bG and min(nO, nC) >= bL - 1e-9:
            top, bot = max(bC, bL), min(bC, bL)
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Demand):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.Demand, top, bot, ts, dr,
                         _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pG and svp and svn and tall and max(nO, nC) > bH + 1e-9:
            top = bO if bR else bC; bot = bL
            if top < bot: top, bot = bot, top
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.RBR):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.RBR, top, bot, ts, dr,
                         _score(dr, ema50[i-1] > ema50[i-2]))
                zones.append(z); active.append(z)

        if pR and svp and svn and tall and min(nO, nC) < bL - 1e-9:
            top = bH; bot = bC if bR else bO
            if top < bot: top, bot = bot, top
            if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.DBD):
                dr = abs(nC - bC) / max(top - bot, 1e-6)
                z = Zone(ZoneKind.DBD, top, bot, ts, dr,
                         _score(dr, ema50[i-1] < ema50[i-2]))
                zones.append(z); active.append(z)

    return zones


# ── Trade simulation ────────────────────────────────────────────────────────

def _sim_trade(
    O1, H1, L1, C1, tm,
    start_idx, n1, zone,
    entry_px, sl_px, tp_px,
    model, tf, sig_type, entry_ts,
) -> Optional[Trade]:
    entry_date = entry_ts.date() if hasattr(entry_ts, "date") else pd.Timestamp(entry_ts).date()
    max_hold = min(start_idx + 240, n1)

    for k in range(start_idx, max_hold):
        bar_date = tm[k].date()
        if bar_date > entry_date:
            exit_px = O1[k]
            exit_reason = "EXPIRE"
        else:
            if zone.is_sell:
                sl_hit = H1[k] >= sl_px - 1e-9
                tp_hit = L1[k] <= tp_px + 1e-9
            else:
                sl_hit = L1[k] <= sl_px + 1e-9
                tp_hit = H1[k] >= tp_px - 1e-9

            if sl_hit and tp_hit:
                exit_px = sl_px; exit_reason = "SL"
            elif sl_hit:
                exit_px = sl_px; exit_reason = "SL"
            elif tp_hit:
                exit_px = tp_px; exit_reason = "TP"
            elif k == max_hold - 1:
                exit_px = C1[k]; exit_reason = "EXPIRE"
            else:
                continue

        risk_ticks = abs(entry_px - sl_px) / TICK_SIZE
        raw = ((entry_px - exit_px) if zone.is_sell else (exit_px - entry_px)) / TICK_SIZE * TICK_VALUE
        return Trade(
            date=str(entry_date),
            direction="SHORT" if zone.is_sell else "LONG",
            model=model.value,
            tf=tf,
            zone_kind=zone.kind.value,
            zone_score=zone.score,
            signal_type=sig_type,
            entry_price=entry_px,
            exit_price=exit_px,
            sl_price=sl_px,
            tp_price=tp_px,
            exit_reason=exit_reason,
            risk_ticks=risk_ticks,
            pnl=raw - COMMISSION_RT,
        )
    return None


# ── Per-zone scanner ────────────────────────────────────────────────────────

def scan_zone(
    zone: Zone,
    O1, H1, L1, C1, V1, tm,
    fp_df: pd.DataFrame,
    n1: int,
    model: EntryModel,
    tp_multiple: float,
    tf: str,
) -> Optional[Trade]:
    """
    Scan 1m bars forward from zone formation looking for a footprint entry signal.
    Returns the first qualifying Trade, or None.
    """
    start_idx = int(tm.searchsorted(zone.formed_ts, side="right"))
    if start_idx >= n1:
        return None

    sl_px = zone.sl_price()
    end_idx = min(start_idx + MAX_ZONE_AGE_1M, n1)

    # Pre-extract proxy arrays for speed
    close_pct_arr = fp_df["close_pct"].values
    delta_arr = fp_df["delta_proxy"].values
    vol_ratio_arr = fp_df["vol_ratio"].values
    body_ratio_arr = fp_df["body_ratio"].values
    rng_arr = fp_df["rng"].values
    upper_wick_arr = fp_df["upper_wick_pct"].values
    lower_wick_arr = fp_df["lower_wick_pct"].values
    vol_ema_arr = fp_df["vol_ema"].values

    touch_count = 0

    for j in range(start_idx, end_idx):
        o, h, lo, c = O1[j], H1[j], L1[j], C1[j]
        v = V1[j]

        # Zone invalidation
        body_max, body_min = max(o, c), min(o, c)
        if _is_invalidated(body_max, body_min, zone):
            return None

        # Touch tracking
        enters = h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9
        if enters:
            touch_count += 1
            if touch_count > MAX_TOUCHES:
                return None

        # Row proxy dict (avoid pandas overhead in inner loop)
        row = {
            "vol_ratio":       vol_ratio_arr[j],
            "body_ratio":      body_ratio_arr[j],
            "rng":             rng_arr[j],
            "close_pct":       close_pct_arr[j],
            "delta_proxy":     delta_arr[j],
            "upper_wick_pct":  upper_wick_arr[j],
            "lower_wick_pct":  lower_wick_arr[j],
        }

        touched_zone = _touches_zone(h, lo, zone)

        # ── PROXIMAL_BASE ──────────────────────────────────────────────────
        if model == EntryModel.PROXIMAL_BASE:
            if not touched_zone:
                continue
            entry_px = zone.proximal
            risk = abs(entry_px - sl_px)
            if risk < TICK_SIZE:
                return None
            tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                    else (entry_px + risk * tp_multiple)
            return _sim_trade(O1, H1, L1, C1, tm, j + 1, n1, zone,
                              entry_px, sl_px, tp_px, model, tf, "PROXIMAL", tm[j])

        # ── ABS_EDGE ───────────────────────────────────────────────────────
        elif model == EntryModel.ABS_EDGE:
            if not touched_zone:
                continue
            found, sig = sig_absorption(row, zone)
            if found and j + 1 < n1:
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

        # ── EXHAUST_EDGE ───────────────────────────────────────────────────
        elif model == EntryModel.EXHAUST_EDGE:
            if not touched_zone:
                continue
            found, sig = sig_exhaustion_wick(row, zone)
            if found and j + 1 < n1:
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

        # ── ABS_OR_EXHAUST ─────────────────────────────────────────────────
        elif model == EntryModel.ABS_OR_EXHAUST:
            if not touched_zone:
                continue
            found_a, sig_a = sig_absorption(row, zone)
            found_e, sig_e = sig_exhaustion_wick(row, zone)
            if (found_a or found_e) and j + 1 < n1:
                sig = sig_a if found_a else sig_e
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

        # ── ABS_INSIDE ────────────────────────────────────────────────────
        elif model == EntryModel.ABS_INSIDE:
            found, sig = sig_abs_inside(row, zone, c)
            if found and j + 1 < n1:
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

        # ── VOL_FADE ──────────────────────────────────────────────────────
        elif model == EntryModel.VOL_FADE:
            if j < 1:
                continue
            # Requires checking previous bar
            H_prev, L_prev, C_prev = H1[j - 1], L1[j - 1], C1[j - 1]
            V_prev = V1[j - 1]
            vol_ema_j = vol_ema_arr[j]
            found, sig = sig_vol_fade(
                None, zone,
                H_prev, L_prev, C_prev, V_prev,
                h, lo, c, v,
                vol_ema_j,
            )
            if found and j + 1 < n1:
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

        # ── COMPOSITE ─────────────────────────────────────────────────────
        elif model == EntryModel.COMPOSITE:
            if not touched_zone:
                continue
            found, sig = sig_composite(row, zone, c)
            if found and j + 1 < n1:
                entry_px = O1[j + 1]
                risk = abs(entry_px - sl_px)
                if risk < TICK_SIZE:
                    continue
                tp_px = (entry_px - risk * tp_multiple) if zone.is_sell \
                        else (entry_px + risk * tp_multiple)
                return _sim_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                  entry_px, sl_px, tp_px, model, tf, sig, tm[j + 1])

    return None


# ── Backtest runner ─────────────────────────────────────────────────────────

def run_backtest(
    bars_1m: pd.DataFrame,
    fp_df: pd.DataFrame,
    detection_tf: str,
    model: EntryModel,
    tp_multiple: float,
) -> List[Trade]:
    freq_map = {"5m": "5min", "15m": "15min", "30m": "30min"}
    bars_tf = bars_1m.resample(freq_map[detection_tf]).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open"])

    all_zones = detect_zones(bars_tf)
    if not all_zones:
        return []

    tm = bars_1m.index
    O1 = bars_1m["open"].values
    H1 = bars_1m["high"].values
    L1 = bars_1m["low"].values
    C1 = bars_1m["close"].values
    V1 = bars_1m["volume"].values.astype(float)
    n1 = len(bars_1m)

    trades: List[Trade] = []
    for zone in all_zones:
        if zone.height < TICK_SIZE:
            continue
        t = scan_zone(zone, O1, H1, L1, C1, V1, tm, fp_df, n1,
                      model, tp_multiple, detection_tf)
        if t:
            trades.append(t)
    return trades


# ── Reporting ───────────────────────────────────────────────────────────────

def _report(trades: List[Trade], label: str) -> str:
    if not trades:
        return f"  {label}: — no trades —\n"

    n = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    net = sum(t.pnl for t in trades)
    wp = sum(t.pnl for t in wins)
    lp = sum(t.pnl for t in losses)
    wr = len(wins) / n * 100
    pf = abs(wp / lp) if lp != 0 else float("inf")
    avg_risk = sum(t.risk_ticks for t in trades) / n
    avg_win = wp / len(wins) if wins else 0
    avg_loss = lp / len(losses) if losses else 0
    tp_n = sum(1 for t in trades if t.exit_reason == "TP")
    sl_n = sum(1 for t in trades if t.exit_reason == "SL")

    lines = [
        f"{'─'*64}",
        f"  {label}",
        f"{'─'*64}",
        f"  Trades: {n}  |  Wins: {len(wins)}  Losses: {len(losses)}",
        f"  Win Rate: {wr:.1f}%  |  Profit Factor: {pf:.2f}",
        f"  Net PnL: ${net:>10,.0f}  |  Avg Risk: {avg_risk:.1f} ticks",
        f"  Avg Win: ${avg_win:>8,.0f}  |  Avg Loss: ${avg_loss:>8,.0f}",
        f"  Exits → TP: {tp_n}  SL: {sl_n}  Expire: {n - tp_n - sl_n}",
    ]

    # By zone type
    lines.append("  ── Zone type breakdown:")
    for kind in ZoneKind:
        kt = [t for t in trades if t.zone_kind == kind.value]
        if not kt:
            continue
        kw = sum(1 for t in kt if t.pnl > 0)
        knet = sum(t.pnl for t in kt)
        lines.append(
            f"    {kind.value:<8}: {len(kt):3d} trades  "
            f"{kw/len(kt)*100:5.1f}% WR  ${knet:>8,.0f}"
        )

    # Score filter
    lines.append("  ── Score-filtered subsets:")
    for thr in [6, 8, 10]:
        ht = [t for t in trades if t.zone_score >= thr]
        if not ht:
            continue
        hw = sum(1 for t in ht if t.pnl > 0)
        hnet = sum(t.pnl for t in ht)
        lines.append(
            f"    Score≥{thr}: {len(ht):3d} trades  "
            f"{hw/len(ht)*100:5.1f}% WR  ${hnet:>8,.0f}"
        )

    # Signal type breakdown (for footprint models)
    sigs = {}
    for t in trades:
        sigs[t.signal_type] = sigs.get(t.signal_type, [])
        sigs[t.signal_type].append(t)
    if len(sigs) > 1:
        lines.append("  ── Signal type breakdown:")
        for sname, st in sorted(sigs.items()):
            sw = sum(1 for t in st if t.pnl > 0)
            lines.append(
                f"    {sname:<22}: {len(st):3d}  "
                f"{sw/len(st)*100:5.1f}% WR  ${sum(t.pnl for t in st):>8,.0f}"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    t0 = time.time()
    print("Loading NQ 1m data ...")
    df = pd.read_csv(CSV_PATH, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.set_index("ts").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open"])
    df = df[(df["close"] >= 10_000) & (df["close"] <= 35_000)]

    # RTH filter
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
        df_et = df.tz_convert(et_tz)
        et_min = df_et.index.hour * 60 + df_et.index.minute
        bars_1m = df[(et_min >= RTH_START_MIN) & (et_min <= RTH_END_MIN)].copy()
    except Exception:
        approx = ((df.index.hour - 4) % 24) * 60 + df.index.minute
        bars_1m = df[(approx >= RTH_START_MIN) & (approx <= RTH_END_MIN)].copy()

    print(f"RTH bars: {len(bars_1m):,}  |  {bars_1m.index[0].date()} → {bars_1m.index[-1].date()}")

    print("Computing footprint proxies (vol_ema, ATR, close_pct, wick ratios) ...")
    fp_df = compute_proxies(bars_1m)

    # ── Header ──────────────────────────────────────────────────────────
    lines = [
        "=" * 64,
        "  INSTITUTIONAL ZONES + FOOTPRINT SIGNALS — COMBINED BACKTEST",
        f"  NQ Futures  |  {bars_1m.index[0].date()} → {bars_1m.index[-1].date()}",
        f"  RTH 1m bars: {len(bars_1m):,}",
        "",
        "  Footprint signal proxies (from DEEP6 signal_config defaults):",
        f"  ABS-01/04: vol > {ABS_VOL_MULT}× ema  AND  body_ratio < {ABS_BODY_RATIO} (indecision bar)",
        f"  EXH-02:  wick >= {EXHAUST_WICK_PCT:.0%} of bar range at zone extreme",
        f"  VOL_FADE: vol climax >= {VOL_CLIMAX_MULT}×, fade bar < {VOL_FADE_RATIO:.0%} of climax",
        f"  COMPOSITE: vol >= {COMPOSITE_VOL_MULT}× + body_ratio < {COMPOSITE_BODY_RATIO} + score ≥ {COMPOSITE_SCORE_MIN}",
        "",
        "  SL: zone distal + 4 ticks  |  TP: 1.5x / 2.0x / 3.0x risk",
        "=" * 64,
    ]

    summary_rows = []

    # ── Primary: all models × all TFs × all TP multiples ────────────────
    for tf in DETECTION_TFS:
        lines.append(f"\n{'═'*64}")
        lines.append(f"  DETECTION TF: {tf}")
        lines.append(f"{'═'*64}")

        for model in EntryModel:
            for tp_mult in TP_RISK_MULTIPLES:
                label = f"{model.value:<16}  TF={tf}  TP={tp_mult}x"
                sys.stdout.write(f"  {label} ...")
                sys.stdout.flush()
                trades = run_backtest(bars_1m, fp_df, tf, model, tp_mult)
                sys.stdout.write(f" {len(trades)} trades\n")
                sys.stdout.flush()

                lines.append(_report(trades, label))
                summary_rows.append((tf, model.value, tp_mult, trades))

    # ── Summary table ────────────────────────────────────────────────────
    lines.append("=" * 78)
    lines.append("  SUMMARY TABLE  (sorted by Net PnL)")
    lines.append("=" * 78)
    lines.append(
        f"  {'Model':<16}  {'TF':<5}  {'TP':>4}  {'N':>5}  "
        f"{'WR%':>6}  {'PF':>5}  {'Net$':>10}  {'AvgRisk':>7}"
    )
    lines.append("  " + "─" * 73)

    summary_rows.sort(key=lambda r: -sum(t.pnl for t in r[3]))
    for (tf, model, tp_mult, trades) in summary_rows:
        if not trades:
            continue
        n = len(trades)
        wr = sum(1 for t in trades if t.pnl > 0) / n * 100
        net = sum(t.pnl for t in trades)
        wp = sum(t.pnl for t in trades if t.pnl > 0)
        lp = sum(t.pnl for t in trades if t.pnl <= 0)
        pf = abs(wp / lp) if lp != 0 else 99.9
        ar = sum(t.risk_ticks for t in trades) / n
        lines.append(
            f"  {model:<16}  {tf:<5}  {tp_mult:>4.1f}  {n:>5}  "
            f"{wr:>6.1f}  {pf:>5.2f}  {net:>10,.0f}  {ar:>7.1f}"
        )

    elapsed = time.time() - t0
    lines.append(f"\n  Completed in {elapsed:.1f}s")

    output = "\n".join(lines)
    print("\n" + output)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(output, encoding="utf-8")
    print(f"\nResults → {OUT_PATH}")


if __name__ == "__main__":
    main()
