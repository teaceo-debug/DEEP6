#!/usr/bin/env python3
"""
Zone Entry — Deep Decomposition (Variant D)
Re-runs the winning config (Variant D: 10:00-15:00, score>=6) then performs
6-axis decomposition to find what makes a zone entry a near-certain winner.

Run:
  python scripts/backtest_zones_decompose.py
"""

from __future__ import annotations

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

ROOT      = Path(__file__).resolve().parents[1]
CSV_1YR   = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_TXT   = ROOT / "scripts/results_zones_decompose.txt"

RTH_START_MIN = 9 * 60 + 30
RTH_END_MIN   = 16 * 60 + 15

# Variant D params
WICK_THRESH   = 0.35
CLOSE_REJECT  = 0.40
TP_MULTIPLE   = 1.0
SL_BUF_TICKS  = 4
MAX_ZONE_AGE  = 500
MAX_TOUCHES   = 2
SMALL_BODY    = 0.50
SCORE_GATE    = 6
TOD_START     = 10 * 60
TOD_END       = 15 * 60


class ZoneKind(Enum):
    Supply = "Supply"; Demand = "Demand"; RBR = "RBR"; DBD = "DBD"


@dataclass
class Zone:
    kind: ZoneKind; top: float; bot: float
    formed_ts: object; score: int; depart_ratio: float
    formed_bar_idx: int = 0

    @property
    def is_sell(self):  return self.kind in (ZoneKind.Supply, ZoneKind.DBD)
    @property
    def proximal(self): return self.bot if self.is_sell else self.top
    @property
    def distal(self):   return self.top if self.is_sell else self.bot

    def sl_price(self) -> float:
        buf = SL_BUF_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)

    @property
    def height_ticks(self) -> float:
        return (self.top - self.bot) / TICK_SIZE


@dataclass
class Trade:
    month: str; date: str; direction: str
    zone_kind: str; zone_score: int
    zone_height_ticks: float; depart_ratio: float
    zone_age_bars: int; touch_number: int
    entry_px: float; exit_px: float
    sl_px: float; tp_px: float
    exit_reason: str; risk_ticks: float; pnl: float
    # entry bar characteristics
    wick_pct: float; vol_ratio: float; bar_range_atr: float
    entry_hour: int; entry_dow: int; entry_week_of_month: int
    # regime
    trend_regime: str   # bullish / bearish / neutral
    vol_regime: str     # high_vol / low_vol


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i-1] * (1.0 - k)
    return out


def _sma(x: np.ndarray, period: int) -> np.ndarray:
    out = np.full_like(x, np.nan, dtype=float)
    cs = np.cumsum(x, dtype=float)
    out[period-1:] = (cs[period-1:] - np.concatenate([[0], cs[:-(period)]]) ) / period
    return out


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

    def _score_and_dr(dr, trend_ok):
        sc = (3 + (3 if dr >= 5 else 2 if dr >= 3 else 1 if dr >= 1.5 else 0)
              + 2 + (2 if trend_ok else 0))
        return sc, dr

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
                sc, dr_ = _score_and_dr(dr, ema50[i-1] < ema50[i-2])
                z = Zone(ZoneKind.Supply, top, bot, ts, sc, dr_, formed_bar_idx=i)
                zones.append(z); active.append(z)

        if pR and C[i-1] > O[i-1] and min(O[i], C[i]) >= L[i-1]-1e-9:
            top, bot = max(C[i-1],L[i-1]), min(C[i-1],L[i-1])
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.Demand):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                sc, dr_ = _score_and_dr(dr, ema50[i-1] > ema50[i-2])
                z = Zone(ZoneKind.Demand, top, bot, ts, sc, dr_, formed_bar_idx=i)
                zones.append(z); active.append(z)

        if pG and svp and svn and tall and max(O[i], C[i]) > H[i-1]+1e-9:
            top = O[i-1] if C[i-1] < O[i-1] else C[i-1]; bot = L[i-1]
            if top < bot: top, bot = bot, top
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.RBR):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                sc, dr_ = _score_and_dr(dr, ema50[i-1] > ema50[i-2])
                z = Zone(ZoneKind.RBR, top, bot, ts, sc, dr_, formed_bar_idx=i)
                zones.append(z); active.append(z)

        if pR and svp and svn and tall and min(O[i], C[i]) < L[i-1]-1e-9:
            top = H[i-1]; bot = C[i-1] if C[i-1] < O[i-1] else O[i-1]
            if top < bot: top, bot = bot, top
            if top-bot >= TICK_SIZE and not _overlap(top, bot, ZoneKind.DBD):
                dr = abs(C[i]-C[i-1]) / max(top-bot, 1e-6)
                sc, dr_ = _score_and_dr(dr, ema50[i-1] < ema50[i-2])
                z = Zone(ZoneKind.DBD, top, bot, ts, sc, dr_, formed_bar_idx=i)
                zones.append(z); active.append(z)

    return zones


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
    # 5-session ATR (rolling on 1m bars — approx via high-low range EMA)
    atr5 = _ema(rng, 75)   # ~75 1m bars ≈ 5 RTH sessions of 15-bar chunks
    atr_14 = _ema(rng, 14)
    # SMA50 on 1m bars (regime from 50-bar SMA)
    sma50 = _sma(C, 50)
    return {
        "upper_wick_pct": uw / rng,
        "lower_wick_pct": lw / rng,
        "close_pct":      (C - L) / rng,
        "vol_ratio":      V / np.where(vol_ema > 0, vol_ema, 1.0),
        "bar_range":      rng,
        "atr14":          atr_14,
        "atr5_session":   atr5,
        "sma50":          sma50,
        "tm":             df["bar_ts"].values,
        "O": O, "H": H, "L": L, "C": C,
        "month":          df["month"].values,
        "date":           df["session_date"].values,
    }


def week_of_month(dt: pd.Timestamp) -> int:
    first_day = dt.replace(day=1)
    dom = dt.day + first_day.weekday()
    return int(np.ceil(dom / 7.0))


def scan_zone(zone: Zone, px: dict, n1: int) -> Optional[Trade]:
    if zone.score < SCORE_GATE:
        return None
    sl_px = zone.sl_price()
    tm = px["tm"]
    start_idx = int(np.searchsorted(tm, np.datetime64(zone.formed_ts), side="right"))
    if start_idx >= n1:
        return None
    end_idx = min(start_idx + MAX_ZONE_AGE, n1)
    touch_count = 0

    for j in range(start_idx, end_idx):
        h, lo = px["H"][j], px["L"][j]
        o, c  = px["O"][j], px["C"][j]

        bmax, bmin = max(o, c), min(o, c)
        if zone.is_sell and bmax > zone.distal + 1e-9: return None
        if not zone.is_sell and bmin < zone.distal - 1e-9: return None

        if h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9:
            touch_count += 1
            if touch_count > MAX_TOUCHES: return None

        ts = pd.Timestamp(tm[j])
        bar_min = ts.hour * 60 + ts.minute
        if bar_min < TOD_START or bar_min >= TOD_END:
            continue

        if zone.is_sell:
            if h < zone.proximal - 1e-9: continue
        else:
            if lo > zone.proximal + 1e-9: continue

        rng = h - lo
        if rng < TICK_SIZE: continue
        uw_pct = (h - max(o, c)) / rng
        lw_pct = (min(o, c) - lo) / rng
        cp = (c - lo) / rng

        if zone.is_sell:
            if uw_pct < WICK_THRESH or cp > CLOSE_REJECT: continue
        else:
            if lw_pct < WICK_THRESH or cp < (1.0 - CLOSE_REJECT): continue

        if j + 1 >= n1: continue
        entry_px = px["O"][j + 1]
        risk = abs(entry_px - sl_px)
        if risk < TICK_SIZE: continue
        tp_px = (entry_px - risk * TP_MULTIPLE) if zone.is_sell \
                else (entry_px + risk * TP_MULTIPLE)

        entry_date = pd.Timestamp(tm[j+1]).date()
        max_hold = min(j + 2 + 240, n1)
        exit_px = px["C"][-1]; reason = "EXPIRE"
        for k in range(j + 2, max_hold):
            bar_date = pd.Timestamp(tm[k]).date()
            if bar_date > entry_date:
                exit_px = px["O"][k]; reason = "EXPIRE"; break
            elif zone.is_sell:
                if px["H"][k] >= sl_px - 1e-9:
                    exit_px = sl_px; reason = "SL"; break
                if px["L"][k] <= tp_px + 1e-9:
                    exit_px = tp_px; reason = "TP"; break
            else:
                if px["L"][k] <= sl_px + 1e-9:
                    exit_px = sl_px; reason = "SL"; break
                if px["H"][k] >= tp_px - 1e-9:
                    exit_px = tp_px; reason = "TP"; break
            if k == max_hold - 1:
                exit_px = px["C"][k]; reason = "EXPIRE"; break

        risk_ticks = abs(entry_px - sl_px) / TICK_SIZE
        raw = ((entry_px - exit_px) if zone.is_sell else (exit_px - entry_px)) / TICK_SIZE * TICK_VALUE

        # Extra decomp metadata from signal bar j
        entry_ts  = pd.Timestamp(tm[j+1])
        entry_hour = entry_ts.hour
        entry_dow  = entry_ts.weekday()
        entry_wom  = week_of_month(entry_ts)
        vol_ratio  = float(px["vol_ratio"][j])
        bar_range  = float(px["bar_range"][j])
        atr14      = float(px["atr14"][j])
        bar_range_atr = bar_range / atr14 if atr14 > 0 else 0.0
        wick_for_dir = float(uw_pct if zone.is_sell else lw_pct)

        # Regime at entry bar j+1
        sma50_val = float(px["sma50"][j+1]) if not np.isnan(px["sma50"][j+1]) else float(px["C"][j+1])
        close_val = float(px["C"][j+1])
        pct_from_sma = (close_val - sma50_val) / sma50_val if sma50_val > 0 else 0.0
        if abs(pct_from_sma) <= 0.005:
            trend_regime = "neutral"
        elif close_val > sma50_val:
            trend_regime = "bullish"
        else:
            trend_regime = "bearish"

        # Vol regime: compare today's atr5 to rolling average
        atr5_now = float(px["atr5_session"][j+1])
        atr5_avg = float(np.nanmean(px["atr5_session"][max(0, j+1-75*20):j+1])) if j > 75 else atr5_now
        vol_regime = "high_vol" if atr5_now > atr5_avg * 1.15 else "low_vol"

        zone_age_bars = j - zone.formed_bar_idx

        return Trade(
            month=str(px["month"][j+1]),
            date=str(entry_date),
            direction="SHORT" if zone.is_sell else "LONG",
            zone_kind=zone.kind.value,
            zone_score=zone.score,
            zone_height_ticks=zone.height_ticks,
            depart_ratio=zone.depart_ratio,
            zone_age_bars=zone_age_bars,
            touch_number=touch_count,
            entry_px=entry_px, exit_px=exit_px,
            sl_px=sl_px, tp_px=tp_px,
            exit_reason=reason,
            risk_ticks=risk_ticks,
            pnl=raw - COMMISSION,
            wick_pct=wick_for_dir,
            vol_ratio=vol_ratio,
            bar_range_atr=bar_range_atr,
            entry_hour=entry_hour,
            entry_dow=entry_dow,
            entry_week_of_month=entry_wom,
            trend_regime=trend_regime,
            vol_regime=vol_regime,
        )
    return None


def run_variant_d(zones: List[Zone], px: dict, n1: int) -> List[Trade]:
    return [t for z in zones
            if (t := scan_zone(z, px, n1)) is not None]


def metrics(trades) -> dict:
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


def bucket_table(trades: List[Trade], key_fn, buckets: list, bucket_labels: list,
                 W, title: str) -> None:
    W(f"\n  {title}")
    W(f"  {'Bucket':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for label, lo, hi in zip(bucket_labels, [None]*len(buckets), [None]*len(buckets)):
        pass
    # Bucket by index
    for i, (lo, hi) in enumerate(buckets):
        label = bucket_labels[i]
        if lo is None and hi is None:
            sub = trades
        elif lo is None:
            sub = [t for t in trades if key_fn(t) < hi]
        elif hi is None:
            sub = [t for t in trades if key_fn(t) >= lo]
        else:
            sub = [t for t in trades if lo <= key_fn(t) < hi]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {label:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")


def group_table(trades: List[Trade], key_fn, sorted_keys, W, title: str,
                key_labels: dict = None) -> None:
    W(f"\n  {title}")
    W(f"  {'Group':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for k in sorted_keys:
        sub = [t for t in trades if key_fn(t) == k]
        if not sub:
            continue
        label = key_labels.get(k, str(k)) if key_labels else str(k)
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {label:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")


def main() -> None:
    import time
    t0 = time.time()
    lines: List[str] = []
    W = lines.append

    W("=" * 90)
    W("  DEEP6 Zone Entry — Deep Decomposition  (Variant D: 10:00-15:00, score>=6)")
    W("  Goal: isolate what separates near-certain winners from coin flips")
    W("=" * 90)
    W("")

    print("Loading 1-year data...", flush=True)
    bars = load_bars(CSV_1YR)
    print(f"  {len(bars):,} 1m RTH bars, {bars['session_date'].nunique()} sessions", flush=True)

    print("Resampling to 15m and detecting zones...", flush=True)
    bars_15m = resample_15m(bars)
    zones = detect_zones(bars_15m)
    print(f"  {len(zones)} zones detected", flush=True)

    print("Running Variant D with decomposition metadata...", flush=True)
    px = compute_proxies(bars)
    n1 = len(bars)

    # Map 15m formed_bar_idx to 1m frame using timestamps
    tm_1m = px["tm"]
    for zone in zones:
        ts_np = np.datetime64(zone.formed_ts)
        idx_1m = int(np.searchsorted(tm_1m, ts_np, side="right"))
        zone.formed_bar_idx = idx_1m

    trades = run_variant_d(zones, px, n1)
    m_all  = metrics(trades)
    print(f"  {m_all['n']} trades, WR {m_all['wr']}%, PF {m_all['pf']}, "
          f"net ${m_all['net']:,.0f}", flush=True)

    W(f"  1m bars: {len(bars):,}  |  sessions: {bars['session_date'].nunique()}")
    W(f"  Date range: {bars['session_date'].iloc[0]} -> {bars['session_date'].iloc[-1]}")
    W(f"  15m bars: {len(bars_15m):,}  |  zones: {len(zones)}")
    W(f"  Variant D trades: {m_all['n']}  |  WR: {m_all['wr']}%  |  PF: {m_all['pf']}")
    W(f"  Net PnL: ${m_all['net']:,.2f}  |  Sharpe: {m_all['sharpe']}  "
      f"|  MaxDD: ${m_all['maxdd']:,.2f}")
    W("")

    # ── SECTION 1: Zone Characteristics ────────────────────────────────────────
    W("=" * 90)
    W("  SECTION 1 — Zone Characteristic Analysis")
    W("=" * 90)

    # 1a. Zone height
    bucket_table(
        trades,
        key_fn=lambda t: t.zone_height_ticks,
        buckets=[(None, 10), (10, 20), (20, 40), (40, None)],
        bucket_labels=["<10 ticks", "10-20 ticks", "20-40 ticks", ">40 ticks"],
        W=W, title="1a. Zone Height (ticks)"
    )

    # 1b. Zone score
    W(f"\n  1b. Zone Score Distribution")
    W(f"  {'Score':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for sc in [6, 7, 8, 9, 10]:
        sub = [t for t in trades if t.zone_score == sc]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {str(sc):<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")
    sub_high = [t for t in trades if t.zone_score >= 8]
    m = metrics(sub_high)
    W(f"  {'>=8 (combined)':<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
      f"{m['net']:>10,.0f} {m['avg']:>7.0f}")

    # 1c. Depart ratio
    bucket_table(
        trades,
        key_fn=lambda t: t.depart_ratio,
        buckets=[(None, 1.5), (1.5, 3.0), (3.0, 5.0), (5.0, None)],
        bucket_labels=["<1.5 (weak)", "1.5-3 (moderate)", "3-5 (strong)", ">5 (explosive)"],
        W=W, title="1c. Zone Depart Ratio (departure strength)"
    )

    # 1d. Zone age at entry (in 15m bars — convert from 1m via /15)
    W(f"\n  1d. Zone Age at Entry (approx 15m bars since formation)")
    W(f"  {'Age Bucket':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    age_buckets = [(None,20), (20,50), (50,100), (100,200), (200,None)]
    age_labels  = ["<20 bars (fresh)", "20-50 bars", "50-100 bars", "100-200 bars", ">200 bars (stale)"]
    for label, (lo, hi) in zip(age_labels, age_buckets):
        age_15m_fn = lambda t: t.zone_age_bars / 15.0
        if lo is None:
            sub = [t for t in trades if age_15m_fn(t) < hi]
        elif hi is None:
            sub = [t for t in trades if age_15m_fn(t) >= lo]
        else:
            sub = [t for t in trades if lo <= age_15m_fn(t) < hi]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {label:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # 1e. Touch number
    W(f"\n  1e. Touch Number at Entry (1st vs 2nd touch)")
    W(f"  {'Touch':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for tc, label in [(1, "1st touch"), (2, "2nd touch")]:
        sub = [t for t in trades if t.touch_number == tc]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {label:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # ── SECTION 2: Entry Bar Characteristics ──────────────────────────────────
    W("")
    W("=" * 90)
    W("  SECTION 2 — Entry Bar Characteristics")
    W("=" * 90)

    # 2a. Wick size
    bucket_table(
        trades,
        key_fn=lambda t: t.wick_pct,
        buckets=[(None, 0.35), (0.35, 0.45), (0.45, 0.55), (0.55, None)],
        bucket_labels=["<35% wick", "35-45% wick", "45-55% wick", ">55% wick"],
        W=W, title="2a. Wick Size at Entry (directional wick %)"
    )

    # 2b. Volume at entry
    bucket_table(
        trades,
        key_fn=lambda t: t.vol_ratio,
        buckets=[(None, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, None)],
        bucket_labels=["<1.5x avg vol", "1.5-2x avg vol", "2-3x avg vol", ">3x avg vol"],
        W=W, title="2b. Volume at Entry Bar (ratio vs 20-bar EMA)"
    )

    # 2c. Bar range vs ATR
    bucket_table(
        trades,
        key_fn=lambda t: t.bar_range_atr,
        buckets=[(None, 0.5), (0.5, 1.0), (1.0, None)],
        bucket_labels=["<0.5x ATR (quiet)", "0.5-1x ATR", ">1x ATR (wide)"],
        W=W, title="2c. Entry Bar Range vs ATR14"
    )

    # ── SECTION 3: Market Regime ───────────────────────────────────────────────
    W("")
    W("=" * 90)
    W("  SECTION 3 — Market Regime at Entry")
    W("=" * 90)

    # 3a. Trend regime
    W(f"\n  3a. Trend Regime (50-bar 1m SMA)")
    W(f"  {'Regime':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for regime in ["bullish", "neutral", "bearish"]:
        sub = [t for t in trades if t.trend_regime == regime]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {regime:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # Also split by with-trend / counter-trend
    W(f"\n  3a-2. With-Trend vs Counter-Trend (zone direction vs SMA regime)")
    W(f"  {'Category':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    def trend_alignment(t: Trade) -> str:
        if t.trend_regime == "neutral":
            return "neutral"
        if t.direction == "LONG" and t.trend_regime == "bullish":
            return "with-trend"
        if t.direction == "SHORT" and t.trend_regime == "bearish":
            return "with-trend"
        return "counter-trend"
    for cat in ["with-trend", "counter-trend", "neutral"]:
        sub = [t for t in trades if trend_alignment(t) == cat]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {cat:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # 3b. Volatility regime
    W(f"\n  3b. Volatility Regime (5-session ATR proxy)")
    W(f"  {'Regime':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for regime in ["high_vol", "low_vol"]:
        sub = [t for t in trades if t.vol_regime == regime]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {regime:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # ── SECTION 4: Time Decomposition ─────────────────────────────────────────
    W("")
    W("=" * 90)
    W("  SECTION 4 — Time Decomposition")
    W("=" * 90)

    # 4a. Hour of day
    W(f"\n  4a. Hour of Day (10:xx - 14:xx ET)")
    W(f"  {'Hour':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for hour in [10, 11, 12, 13, 14]:
        sub = [t for t in trades if t.entry_hour == hour]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {str(hour)+':xx':<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # 4b. Day of week
    dow_labels = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
    W(f"\n  4b. Day of Week")
    W(f"  {'Day':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for dow in [0, 1, 2, 3, 4]:
        sub = [t for t in trades if t.entry_dow == dow]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {dow_labels[dow]:<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # 4c. Week of month
    W(f"\n  4c. Week of Month")
    W(f"  {'Week':<22} {'N':>5} {'WR%':>7} {'PF':>6} {'Net$':>10} {'Avg$':>7}")
    W("  " + "─" * 62)
    for wom in [1, 2, 3, 4]:
        sub = [t for t in trades if t.entry_week_of_month == wom]
        m = metrics(sub)
        flag = " <--" if m["n"] >= 5 and m["wr"] >= 85 else ""
        W(f"  {'Week '+str(wom):<22} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['net']:>10,.0f} {m['avg']:>7.0f}{flag}")

    # ── SECTION 5: Losing Trade Autopsy ───────────────────────────────────────
    W("")
    W("=" * 90)
    W("  SECTION 5 — Losing Trade Autopsy")
    W("=" * 90)
    W("")

    losers = [t for t in trades if t.pnl < 0]
    W(f"  Total losers: {len(losers)} / {len(trades)} trades ({len(losers)/len(trades)*100:.1f}%)")
    W("")

    # Loser profile vs winner profile
    winners = [t for t in trades if t.pnl > 0]

    def mean_attr(tlist, attr):
        vals = [getattr(t, attr) for t in tlist]
        return np.mean(vals) if vals else 0.0

    W("  Loser vs Winner — Average Attributes:")
    W(f"  {'Attribute':<28} {'Losers':>10} {'Winners':>10} {'Delta':>10}")
    W("  " + "─" * 62)
    attrs_to_compare = [
        ("zone_height_ticks", "Zone height (ticks)"),
        ("zone_score",        "Zone score"),
        ("depart_ratio",      "Depart ratio"),
        ("zone_age_bars",     "Zone age (1m bars)"),
        ("touch_number",      "Touch number"),
        ("wick_pct",          "Wick %"),
        ("vol_ratio",         "Volume ratio"),
        ("bar_range_atr",     "Bar range / ATR"),
    ]
    for attr, label in attrs_to_compare:
        lv = mean_attr(losers, attr)
        wv = mean_attr(winners, attr)
        delta = lv - wv
        W(f"  {label:<28} {lv:>10.2f} {wv:>10.2f} {delta:>+10.2f}")

    W("")
    W("  Loser distribution by zone type:")
    for zt in ["Supply", "Demand", "RBR", "DBD"]:
        l_sub = [t for t in losers  if t.zone_kind == zt]
        w_sub = [t for t in winners if t.zone_kind == zt]
        total = len(l_sub) + len(w_sub)
        if total == 0: continue
        wr_zt = len(w_sub) / total * 100 if total else 0
        W(f"    {zt:8s}: {len(l_sub)} losers / {total} total  ({wr_zt:.0f}% WR)")

    W("")
    W("  Loser distribution by trend alignment:")
    for cat in ["with-trend", "counter-trend", "neutral"]:
        l_sub = [t for t in losers  if trend_alignment(t) == cat]
        w_sub = [t for t in winners if trend_alignment(t) == cat]
        total = len(l_sub) + len(w_sub)
        if total == 0: continue
        wr_cat = len(w_sub) / total * 100 if total else 0
        W(f"    {cat:<18}: {len(l_sub)} losers / {total} total  ({wr_cat:.0f}% WR)")

    W("")
    W("  Full loser log:")
    W(f"  {'Date':<12} {'Dir':<6} {'Zone':<8} {'Sc':>3} {'HtT':>5} {'DR':>5} "
      f"{'Wick':>6} {'VolR':>5} {'Touch':>5} {'Trend':<12} {'Hour':>5} {'PnL':>8}")
    W("  " + "─" * 90)
    for t in sorted(losers, key=lambda x: x.date):
        W(f"  {t.date:<12} {t.direction:<6} {t.zone_kind:<8} {t.zone_score:>3} "
          f"{t.zone_height_ticks:>5.1f} {t.depart_ratio:>5.2f} "
          f"{t.wick_pct:>6.2f} {t.vol_ratio:>5.2f} {t.touch_number:>5} "
          f"{t.trend_regime:<12} {t.entry_hour:>5} {t.pnl:>8.2f}")

    # Loser commonality summary
    W("")
    W("  Loser pattern flags (occurrences among all losers):")
    flags = {
        "score == 6 (minimum)": sum(1 for t in losers if t.zone_score == 6),
        "wick < 40%":           sum(1 for t in losers if t.wick_pct < 0.40),
        "height < 10t":         sum(1 for t in losers if t.zone_height_ticks < 10),
        "height > 40t":         sum(1 for t in losers if t.zone_height_ticks > 40),
        "counter-trend":        sum(1 for t in losers if trend_alignment(t) == "counter-trend"),
        "2nd touch":            sum(1 for t in losers if t.touch_number == 2),
        "DR < 1.5":             sum(1 for t in losers if t.depart_ratio < 1.5),
        "vol < 1.5x":           sum(1 for t in losers if t.vol_ratio < 1.5),
        "high_vol day":         sum(1 for t in losers if t.vol_regime == "high_vol"),
        "Friday trade":         sum(1 for t in losers if t.entry_dow == 4),
    }
    for flag, cnt in sorted(flags.items(), key=lambda x: -x[1]):
        pct = cnt / len(losers) * 100 if losers else 0
        W(f"    {flag:<30}: {cnt:>3} / {len(losers)}  ({pct:.0f}%)")

    # ── SECTION 6: Optimal Filter Recommendations ─────────────────────────────
    W("")
    W("=" * 90)
    W("  SECTION 6 — Score Filter v2 Recommendations")
    W("=" * 90)
    W("")
    W("  Testing increasingly strict filter combinations:")
    W("")

    filter_configs = [
        # (label, filter_fn)
        ("Baseline (D): score>=6",
         lambda t: True),
        ("F1: score>=7",
         lambda t: t.zone_score >= 7),
        ("F2: score>=7 + height>10t",
         lambda t: t.zone_score >= 7 and t.zone_height_ticks > 10),
        ("F3: score>=7 + wick>40%",
         lambda t: t.zone_score >= 7 and t.wick_pct > 0.40),
        ("F4: score>=7 + 1st touch",
         lambda t: t.zone_score >= 7 and t.touch_number == 1),
        ("F5: score>=7 + wick>40% + 1st touch",
         lambda t: t.zone_score >= 7 and t.wick_pct > 0.40 and t.touch_number == 1),
        ("F6: score>=7 + wick>40% + height>10t",
         lambda t: t.zone_score >= 7 and t.wick_pct > 0.40 and t.zone_height_ticks > 10),
        ("F7: score>=7 + wick>40% + height>10t + 1st touch",
         lambda t: t.zone_score >= 7 and t.wick_pct > 0.40
                   and t.zone_height_ticks > 10 and t.touch_number == 1),
        ("F8: score>=8",
         lambda t: t.zone_score >= 8),
        ("F9: score>=8 + wick>40%",
         lambda t: t.zone_score >= 8 and t.wick_pct > 0.40),
        ("F10: score>=8 + wick>40% + 1st touch",
         lambda t: t.zone_score >= 8 and t.wick_pct > 0.40 and t.touch_number == 1),
        ("F11: score>=8 + wick>40% + height>10t + 1st touch",
         lambda t: t.zone_score >= 8 and t.wick_pct > 0.40
                   and t.zone_height_ticks > 10 and t.touch_number == 1),
        ("F12: score>=7 + DR>1.5",
         lambda t: t.zone_score >= 7 and t.depart_ratio > 1.5),
        ("F13: score>=7 + DR>1.5 + wick>40% + 1st touch",
         lambda t: t.zone_score >= 7 and t.depart_ratio > 1.5
                   and t.wick_pct > 0.40 and t.touch_number == 1),
        ("F14: with-trend only",
         lambda t: trend_alignment(t) == "with-trend"),
        ("F15: with-trend + score>=7",
         lambda t: trend_alignment(t) == "with-trend" and t.zone_score >= 7),
        ("F16: with-trend + score>=7 + wick>40%",
         lambda t: trend_alignment(t) == "with-trend" and t.zone_score >= 7
                   and t.wick_pct > 0.40),
    ]

    W(f"  {'Filter':<44} {'N':>5} {'WR%':>7} {'PF':>6} {'Sharpe':>7} {'Net$':>10} {'vs_base':>8}")
    W("  " + "─" * 92)
    base_net = m_all["net"]
    for label, fn in filter_configs:
        sub = [t for t in trades if fn(t)]
        m = metrics(sub)
        vs_base = m["net"] - base_net
        flag = " ***" if m["n"] >= 15 and m["wr"] >= 85 else \
               " **"  if m["n"] >= 10 and m["wr"] >= 85 else \
               " *"   if m["n"] >= 5  and m["wr"] >= 85 else ""
        W(f"  {label:<44} {m['n']:>5} {m['wr']:>7.1f} {m['pf']:>6.2f} "
          f"{m['sharpe']:>7.2f} {m['net']:>10,.0f} {vs_base:>+8,.0f}{flag}")

    # Best filter recommendation
    W("")
    W("  Finding highest-WR filter with N>=20 trades...")
    best = None; best_wr = 0.0
    for label, fn in filter_configs[1:]:  # skip baseline
        sub = [t for t in trades if fn(t)]
        m = metrics(sub)
        if m["n"] >= 20 and m["wr"] > best_wr:
            best_wr = m["wr"]; best = (label, m)
    if best:
        W(f"  => Best filter (N>=20): [{best[0]}]")
        W(f"     N={best[1]['n']}, WR={best[1]['wr']}%, PF={best[1]['pf']}, "
          f"Sharpe={best[1]['sharpe']}, Net=${best[1]['net']:,.0f}")
    else:
        W("  => No filter with N>=20 exceeded baseline WR")

    W("")
    W("  Finding highest-PF filter with N>=10 trades...")
    best_pf = None; best_pf_val = 0.0
    for label, fn in filter_configs[1:]:
        sub = [t for t in trades if fn(t)]
        m = metrics(sub)
        if m["n"] >= 10 and m["pf"] > best_pf_val:
            best_pf_val = m["pf"]; best_pf = (label, m)
    if best_pf:
        W(f"  => Best PF filter (N>=10): [{best_pf[0]}]")
        W(f"     N={best_pf[1]['n']}, WR={best_pf[1]['wr']}%, PF={best_pf[1]['pf']}, "
          f"Net=${best_pf[1]['net']:,.0f}")

    # ── SECTION 6b: Weak Month Analysis ───────────────────────────────────────
    W("")
    W("  Weak Month Analysis (Aug-2025, Jul-2025, Oct-2025) under filters:")
    W("")
    weak_months = ["2025-08", "2025-07", "2025-10"]
    for mo in weak_months:
        mo_trades = [t for t in trades if t.month == mo]
        if not mo_trades:
            W(f"  {mo}: no trades")
            continue
        mo_m = metrics(mo_trades)
        W(f"  {mo}: N={mo_m['n']}, WR={mo_m['wr']}%, Net=${mo_m['net']:,.0f}")
        for label, fn in [("  score>=7", lambda t: t.zone_score >= 7),
                          ("  score>=7+wick>40%", lambda t: t.zone_score >= 7 and t.wick_pct > 0.40),
                          ("  score>=7+wick>40%+1st", lambda t: t.zone_score >= 7 and t.wick_pct > 0.40 and t.touch_number == 1)]:
            sub = [t for t in mo_trades if fn(t)]
            m2 = metrics(sub)
            W(f"    {label:<26}: N={m2['n']}, WR={m2['wr']}%, Net=${m2['net']:,.0f}")
        W("")

    # ── Final summary ──────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    W("=" * 90)
    W(f"  Decomposition complete in {elapsed:.1f}s")
    W("=" * 90)

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
