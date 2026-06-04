#!/usr/bin/env python3
"""
Zone Entry — 1-Year Validation
Optimal params from backtest_zones_optimize.py:
  wick=0.35, close_reject=0.40, tp=1.0 (1:1), sl_buf=4t, score≥0
  15m zone detection, EXHAUST_EDGE entry, full RTH

Tests:
  A) Full RTH, score≥0  (raw winner)
  B) Full RTH, score≥6  (quality filter)
  C) 10:00–15:00, score≥0
  D) 10:00–15:00, score≥6  (recommended live config)

Reports monthly trade breakdown + equity curve for each variant.

Run (Windows):
  python scripts/backtest_zones_1yr.py
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
OUT_TXT   = ROOT / "scripts/results_zones_1yr.txt"
OUT_DIR   = ROOT / "data/backtests"

RTH_START_MIN = 9 * 60 + 30
RTH_END_MIN   = 16 * 60 + 15
DETECTION_TF  = "15m"

# ── Optimal params ─────────────────────────────────────────────────────────────
WICK_THRESH   = 0.35
CLOSE_REJECT  = 0.40
TP_MULTIPLE   = 1.0
SL_BUF_TICKS  = 4
MAX_ZONE_AGE  = 500
MAX_TOUCHES   = 2
SMALL_BODY    = 0.50

VARIANTS = [
    ("A", 0,  RTH_START_MIN, RTH_END_MIN, "Full RTH  score>=0"),
    ("B", 6,  RTH_START_MIN, RTH_END_MIN, "Full RTH  score>=6"),
    ("C", 0,  10*60,         15*60,       "10-15h    score>=0"),
    ("D", 6,  10*60,         15*60,       "10-15h    score>=6  <- recommended"),
]


# ── Zone detection structures ──────────────────────────────────────────────────

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

    def sl_price(self) -> float:
        buf = SL_BUF_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    month: str; date: str; direction: str
    zone_kind: str; zone_score: int
    entry_px: float; exit_px: float
    sl_px: float; tp_px: float
    exit_reason: str; risk_ticks: float; pnl: float


# ── Math ────────────────────────────────────────────────────────────────────────

def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i-1] * (1.0 - k)
    return out


# ── Zone detection ─────────────────────────────────────────────────────────────

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


# ── Signal + trade simulation ──────────────────────────────────────────────────

def scan_zone(zone: Zone, px: dict, n1: int,
              score_gate: int, tod_start: int, tod_end: int) -> Optional[Trade]:
    if zone.score < score_gate:
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

        # Invalidation: body closes through distal
        bmax, bmin = max(o, c), min(o, c)
        if zone.is_sell and bmax > zone.distal + 1e-9: return None
        if not zone.is_sell and bmin < zone.distal - 1e-9: return None

        # Touch counting
        if h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9:
            touch_count += 1
            if touch_count > MAX_TOUCHES: return None

        # TOD gate
        ts = pd.Timestamp(tm[j])
        bar_min = ts.hour * 60 + ts.minute
        if bar_min < tod_start or bar_min >= tod_end:
            continue

        # Must touch proximal edge
        if zone.is_sell:
            if h < zone.proximal - 1e-9: continue
        else:
            if lo > zone.proximal + 1e-9: continue

        # Exhaustion wick signal
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
        tp_px = (entry_px - risk * TP_MULTIPLE) if zone.is_sell \
                else (entry_px + risk * TP_MULTIPLE)

        # Simulate exit
        entry_date = pd.Timestamp(tm[j+1]).date()
        max_hold = min(j + 2 + 240, n1)
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
        else:
            exit_px = px["C"][-1]; reason = "EXPIRE"

        risk_ticks = abs(entry_px - sl_px) / TICK_SIZE
        raw = ((entry_px - exit_px) if zone.is_sell else (exit_px - entry_px)) / TICK_SIZE * TICK_VALUE
        return Trade(
            month=str(px["month"][j+1]),
            date=str(entry_date),
            direction="SHORT" if zone.is_sell else "LONG",
            zone_kind=zone.kind.value,
            zone_score=zone.score,
            entry_px=entry_px, exit_px=exit_px,
            sl_px=sl_px, tp_px=tp_px,
            exit_reason=reason,
            risk_ticks=risk_ticks,
            pnl=raw - COMMISSION,
        )
    return None


def run_variant(zones: List[Zone], px: dict, n1: int,
                score_gate: int, tod_start: int, tod_end: int) -> List[Trade]:
    return [t for z in zones
            if (t := scan_zone(z, px, n1, score_gate, tod_start, tod_end)) is not None]


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


# ── Equity curve PNG ────────────────────────────────────────────────────────────

def save_equity(trades: List[Trade], variant_label: str, m: dict, fname: str) -> None:
    pnls = [t.pnl for t in trades]
    eq   = np.cumsum(pnls) if pnls else np.array([0.0])
    peak = np.maximum.accumulate(eq)
    dd   = peak - eq

    fig, axes = plt.subplots(2, 1, figsize=(14, 7),
                             gridspec_kw={"height_ratios": [3, 1]})
    ax = axes[0]
    ax.plot(eq, color="#2196F3", linewidth=1.3, label="Equity ($)")
    ax.fill_between(range(len(eq)), eq, alpha=0.08, color="#2196F3")
    ax.axhline(0, color="#888", linewidth=0.8, linestyle="--")
    ax.set_title(
        f"Zone Entry — Variant {variant_label}  |  "
        f"{m['n']} trades  WR {m['wr']}%  PF {m['pf']}  "
        f"Sharpe {m['sharpe']}  Net ${m['net']:,.0f}",
        fontsize=10,
    )
    ax.set_ylabel("Cumulative PnL ($)")
    ax.legend(loc="upper left", fontsize=9)

    # Monthly tick marks
    if trades:
        months = sorted(set(t.month for t in trades))
        first_by_month = {}
        for i, t in enumerate(trades):
            if t.month not in first_by_month:
                first_by_month[t.month] = i
        ticks = [first_by_month[m_] for m_ in months if m_ in first_by_month]
        ax.set_xticks(ticks)
        ax.set_xticklabels([m_[-5:] for m_ in months if m_ in first_by_month],
                           rotation=45, fontsize=7)

    ax2 = axes[1]
    ax2.fill_between(range(len(dd)), -dd, color="#F44336", alpha=0.6)
    ax2.set_ylabel("Drawdown ($)")
    ax2.set_xlabel("Trade #")

    plt.tight_layout()
    path = OUT_DIR / fname
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  Saved {path.name}")


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import time
    t0 = time.time()
    lines: List[str] = []
    W = lines.append

    W("=" * 90)
    W("  DEEP6 Zone Entry — 1-Year Validation")
    W("  Optimal params: wick=0.35, close_reject=0.40, tp=1:1, sl=distal+4t, 15m zones")
    W("=" * 90)
    W("")

    print("Loading 1-year data...", flush=True)
    bars = load_bars(CSV_1YR)
    print(f"  {len(bars):,} 1m RTH bars, {bars['session_date'].nunique()} sessions, "
          f"{bars['month'].nunique()} months", flush=True)

    W(f"  1m bars: {len(bars):,}  |  sessions: {bars['session_date'].nunique()}")
    W(f"  Date range: {bars['session_date'].iloc[0]} → {bars['session_date'].iloc[-1]}")
    W(f"  Months: {bars['month'].iloc[0]} → {bars['month'].iloc[-1]}")
    W("")

    print("Resampling to 15m and detecting zones...", flush=True)
    bars_15m = resample_15m(bars)
    zones = detect_zones(bars_15m)
    W(f"  15m bars: {len(bars_15m):,}  |  zones detected: {len(zones)}")
    W("")

    print(f"  {len(zones)} zones — running 4 variants...", flush=True)
    px = compute_proxies(bars)
    n1 = len(bars)

    all_results: List[Tuple[str, List[Trade], dict]] = []

    for vid, score_gate, tod_s, tod_e, label in VARIANTS:
        trades = run_variant(zones, px, n1, score_gate, tod_s, tod_e)
        m = metrics(trades)
        all_results.append((vid, trades, m))
        safe_label = label.encode("ascii", errors="replace").decode()
        print(f"  [{vid}] {safe_label}: {m['n']} trades, WR {m['wr']}%, PF {m['pf']}, "
              f"net ${m['net']:,.0f}", flush=True)

    # ── Summary table ──────────────────────────────────────────────────────────
    W("=" * 90)
    W("  SUMMARY — All Variants")
    W("=" * 90)
    W("")
    W(f"  {'Var':<4} {'Label':<32} {'N':>5} {'WR%':>6} {'PF':>6} {'Sharpe':>7} "
      f"{'Net$':>10} {'Avg$':>7} {'MaxDD$':>9} {'LL':>4}")
    W("  " + "─" * 84)
    for vid, trades, m in all_results:
        label = next(v[4] for v in VARIANTS if v[0] == vid)
        W(f"  {vid:<4} {label:<32} {m['n']:>5} {m['wr']:>6.1f} {m['pf']:>6.2f} "
          f"{m['sharpe']:>7.2f} {m['net']:>10,.0f} {m['avg']:>7.0f} "
          f"{m['maxdd']:>9,.0f} {m['ll']:>4}")
    W("")

    # ── Per-variant detail ─────────────────────────────────────────────────────
    for vid, trades, m in all_results:
        label = next(v[4] for v in VARIANTS if v[0] == vid)
        W("═" * 90)
        W(f"  VARIANT {vid} — {label}")
        W("═" * 90)
        W("")

        if not trades:
            W("  No trades.")
            W("")
            continue

        W(f"  Trades: {m['n']}  |  Win Rate: {m['wr']}%  |  Profit Factor: {m['pf']}")
        W(f"  Sharpe: {m['sharpe']}  |  Net PnL: ${m['net']:,.2f}  |  "
          f"Avg/trade: ${m['avg']:,.2f}")
        W(f"  Max DrawDown: ${m['maxdd']:,.2f}  |  Longest losing streak: {m['ll']}")
        W(f"  Expectancy: ${m['exp']:,.2f}")
        W("")

        # Exit reason breakdown
        reasons: dict = {}
        for t in trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        W("  Exits: " + "  ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
        W("")

        # Zone type breakdown
        W("  Zone-type breakdown:")
        for zt in ["Supply", "Demand", "RBR", "DBD"]:
            sub = [t for t in trades if t.zone_kind == zt]
            if sub:
                sm = metrics(sub)
                W(f"    {zt:8s}: {sm['n']:3d} trades  WR {sm['wr']:5.1f}%  "
                  f"PF {sm['pf']:5.2f}  net ${sm['net']:>9,.0f}")
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
        W("")

        # Profitable months count
        months_pos = sum(1 for mo in all_months
                         if sum(t.pnl for t in trades if t.month == mo) > 0)
        W(f"  Profitable months: {months_pos}/{len(all_months)}")
        W("")

        # Score gate comparison (on this variant's tod/score config)
        score_gate_used = next(v[1] for v in VARIANTS if v[0] == vid)
        tod_s = next(v[2] for v in VARIANTS if v[0] == vid)
        tod_e = next(v[3] for v in VARIANTS if v[0] == vid)
        if score_gate_used == 0:
            W("  Score-gate breakdown:")
            for sg in [0, 4, 6, 8]:
                sub = [t for t in trades if t.zone_score >= sg]
                if sub:
                    sm = metrics(sub)
                    W(f"    score>={sg}: {sm['n']:3d} trades  WR {sm['wr']:5.1f}%  "
                      f"PF {sm['pf']:5.2f}  net ${sm['net']:>9,.0f}  "
                      f"Sharpe {sm['sharpe']:5.2f}")
            W("")

        # Save equity PNG
        save_equity(trades, vid, m, f"zones_1yr_variant_{vid}_equity.png")

    elapsed = time.time() - t0
    W(f"  Completed in {elapsed:.1f}s")
    W("=" * 90)

    result_txt = "\n".join(lines)
    OUT_TXT.write_text(result_txt, encoding="utf-8")

    # Print with safe encoding
    for line in lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode())

    print(f"\nSaved -> {OUT_TXT}")


if __name__ == "__main__":
    main()
