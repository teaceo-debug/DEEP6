#!/usr/bin/env python3
"""
1-Year NQ Institutional Zones + Wick Backtest — Full Filter Matrix
Downloads from Databento (skips if file exists), then tests every regime
filter individually and in combination:
  Filters: TREND (1h EMA) | ADX15/20/25 | WEEKLY_BIAS | VOL_REGIME
  TFs: 5m, 15m  |  TP: 1.5x, 2.0x, 3.0x
"""

import os
import sys
import time
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT     = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "backtests"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_OUT  = DATA_DIR / "nq_1yr_1m.csv"
RES_OUT  = ROOT / "scripts" / "results_1yr_all_filters.txt"

API_KEY  = "db-b4KxcTPhJmeuxP7arMYbKQY6hvny6"
SYMBOL   = "NQ.c.0"
DATASET  = "GLBX.MDP3"
START    = "2025-01-01"
END      = "2026-04-25"

# ── Constants ──────────────────────────────────────────────────────────────────
TICK_SIZE       = 0.25
TICK_VALUE      = 5.0
COMMISSION_RT   = 0.70
RTH_START_MIN   = 9 * 60 + 30
RTH_END_MIN     = 16 * 60 + 15
MIDDAY_START    = 10 * 60 + 30
MIDDAY_END      = 13 * 60

SMALL_BODY_RATIO = 0.50
MIN_ZONE_TICKS   = 4
SL_BUFFER_TICKS  = 4
MAX_ZONE_AGE_1M  = 500
WICK_MIN_PCT     = 0.35
CLOSE_BUF_TICKS  = 2
MIN_ENTRY_TICKS  = 8

TREND_EMA_PERIOD = 21
ADX_PERIOD       = 14
VOL_REGIME_BARS  = 100   # rolling window for ATR percentile (1h bars)


# ── Download ──────────────────────────────────────────────────────────────────

def download():
    if CSV_OUT.exists():
        print(f"Data exists: {CSV_OUT} ({CSV_OUT.stat().st_size/1e6:.1f} MB) — skipping download")
        return
    import databento as db
    client = db.Historical(API_KEY)
    print(f"Downloading {SYMBOL} ohlcv-1m {START} → {END}...")
    t0 = time.time()
    data = client.timeseries.get_range(
        dataset=DATASET, symbols=[SYMBOL], schema="ohlcv-1m",
        stype_in="continuous", start=START, end=END,
    )
    df = data.to_df()
    print(f"  {len(df):,} rows in {time.time()-t0:.1f}s")
    df.to_csv(CSV_OUT, index=True)
    print(f"  Saved: {CSV_OUT}")


# ── Load & filter RTH ─────────────────────────────────────────────────────────

def load_rth() -> pd.DataFrame:
    print("Loading data...")
    df = pd.read_csv(CSV_OUT)
    ts_col = next((c for c in ["ts_event","ts_recv","timestamp"] if c in df.columns), df.columns[0])
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.rename(columns={ts_col: "ts"}).set_index("ts").sort_index()

    col_map = {}
    for c in df.columns:
        cl = c.lower()
        for n in ["open","high","low","close","volume"]:
            if cl == n or cl.endswith("_"+n):
                col_map[c] = n
    df = df.rename(columns=col_map)[["open","high","low","close","volume"]].copy()
    for c in ["open","high","low","close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open"])
    df = df[(df["close"] >= 10_000) & (df["close"] <= 35_000)]

    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    df_et = df.tz_convert(et)
    et_min = df_et.index.hour * 60 + df_et.index.minute
    bars = df[(et_min >= RTH_START_MIN) & (et_min <= RTH_END_MIN)].copy()
    print(f"RTH bars: {len(bars):,}  {bars.index[0].date()} → {bars.index[-1].date()}")
    return bars


# ── Math helpers ──────────────────────────────────────────────────────────────

def _ema(x: np.ndarray, p: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (p + 1)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i-1] * (1.0 - k)
    return out


def _rma(x: np.ndarray, p: int) -> np.ndarray:
    """Wilder's smoothing (RMA) — used for ADX/ATR."""
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    k = 1.0 / p
    for i in range(1, len(x)):
        out[i] = out[i-1] * (1.0 - k) + x[i] * k
    return out


def compute_adx(H: np.ndarray, L: np.ndarray, C: np.ndarray, p: int = 14):
    n = len(C)
    pH = np.roll(H, 1); pH[0] = H[0]
    pL = np.roll(L, 1); pL[0] = L[0]
    pC = np.roll(C, 1); pC[0] = C[0]

    tr   = np.maximum(H - L, np.maximum(np.abs(H - pC), np.abs(L - pC)))
    up   = H - pH
    down = pL - L
    pdm  = np.where((up > down) & (up > 0), up, 0.0)
    mdm  = np.where((down > up) & (down > 0), down, 0.0)

    str_ = _rma(tr, p)
    spdm = _rma(pdm, p)
    smdm = _rma(mdm, p)

    pdi = 100.0 * spdm / np.where(str_ > 0, str_, 1e-9)
    mdi = 100.0 * smdm / np.where(str_ > 0, str_, 1e-9)
    dx  = 100.0 * np.abs(pdi - mdi) / np.where(pdi + mdi > 0, pdi + mdi, 1e-9)
    adx = _rma(dx, p)
    return adx, pdi, mdi


def compute_atr(H, L, C, p=14):
    pC = np.roll(C, 1); pC[0] = C[0]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pC), np.abs(L - pC)))
    return _rma(tr, p)


# ── Precompute all filter arrays ──────────────────────────────────────────────

def build_filters(bars_1m: pd.DataFrame) -> Dict[str, np.ndarray]:
    print("Building filter arrays (EMA, ADX, weekly bias, vol regime)...")
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")

    # 1h bars
    bars_1h = bars_1m.resample("60min").agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna(subset=["open"])

    H1h = bars_1h["high"].values
    L1h = bars_1h["low"].values
    C1h = bars_1h["close"].values

    # 1h EMA trend
    ema_1h_vals = _ema(C1h, TREND_EMA_PERIOD)
    ema_1h = pd.Series(ema_1h_vals, index=bars_1h.index).reindex(bars_1m.index, method="ffill")

    # 1h ADX
    adx_vals, pdi_vals, mdi_vals = compute_adx(H1h, L1h, C1h, ADX_PERIOD)
    adx_1h = pd.Series(adx_vals, index=bars_1h.index).reindex(bars_1m.index, method="ffill")

    # 1h ATR volatility regime (medium = between rolling 25th-75th pct)
    atr_vals = compute_atr(H1h, L1h, C1h, ADX_PERIOD)
    atr_s = pd.Series(atr_vals, index=bars_1h.index)
    q25 = atr_s.rolling(VOL_REGIME_BARS, min_periods=20).quantile(0.25)
    q75 = atr_s.rolling(VOL_REGIME_BARS, min_periods=20).quantile(0.75)
    vol_ok_1h = (atr_s >= q25) & (atr_s <= q75)
    vol_regime = vol_ok_1h.reindex(bars_1m.index, method="ffill").fillna(False)

    # Weekly bias — is current close above the Monday 9:30 open of this week?
    # Find first bar of each ISO week (Monday RTH open)
    bars_et = bars_1m.tz_convert(et)
    week_key = bars_et.index.isocalendar().week.values.astype(int) + \
               bars_et.index.isocalendar().year.values.astype(int) * 100
    wk_series = pd.Series(week_key, index=bars_1m.index)
    week_opens = bars_1m["open"].groupby(wk_series).first()
    week_open_map = wk_series.map(week_opens)  # each 1m bar gets its week's open
    weekly_bias_bull = (bars_1m["close"] > week_open_map).values  # True = above weekly open

    # ET minute-of-day for time filter
    et_min = (bars_et.index.hour * 60 + bars_et.index.minute).values

    return {
        "ema_1h":       ema_1h.values,
        "adx_1h":       adx_1h.values,
        "weekly_bull":  weekly_bias_bull,
        "vol_regime":   vol_regime.values.astype(bool),
        "et_min":       et_min,
        "close_1m":     bars_1m["close"].values,
    }


# ── Zone detection ────────────────────────────────────────────────────────────

class ZoneKind(Enum):
    Supply = "Supply"
    Demand = "Demand"
    RBR    = "RBR"
    DBD    = "DBD"


@dataclass
class Zone:
    kind: ZoneKind
    top: float; bot: float
    formed_ts: pd.Timestamp
    is_confluent: bool = False
    touch_count: int = 0

    @property
    def height(self): return self.top - self.bot
    @property
    def is_sell(self): return self.kind in (ZoneKind.Supply, ZoneKind.DBD)
    @property
    def proximal(self): return self.bot if self.is_sell else self.top
    @property
    def distal(self):   return self.top if self.is_sell else self.bot
    def sl_price(self):
        buf = SL_BUFFER_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    date: str; direction: str; model: str; tf: str; zone_kind: str
    filters_used: str; entry_price: float; exit_price: float
    exit_reason: str; risk_ticks: float; pnl: float


def detect_zones(bars: pd.DataFrame) -> List[Zone]:
    n = len(bars)
    if n < 3: return []
    O,H,L,C = bars["open"].values,bars["high"].values,bars["low"].values,bars["close"].values
    T = bars.index
    ema50 = _ema(C, 50)
    zones: List[Zone] = []
    active: List[Zone] = []

    def _overlaps(top, bot, kind):
        for z in active:
            if z.kind != kind: continue
            if bot <= z.top + 1e-9 and top >= z.bot - 1e-9: return True
        return False

    for i in range(2, n):
        pO,pC = O[i-2],C[i-2]
        bO,bC,bH,bL = O[i-1],C[i-1],H[i-1],L[i-1]
        nO,nC = O[i],C[i]
        pb,bb,nb = abs(pC-pO),abs(bC-bO),abs(nC-nO)
        br = bH - bL
        if pb<=0 or nb<=0: continue
        if not (bb<=SMALL_BODY_RATIO*pb and bb<=SMALL_BODY_RATIO*nb and br>=MIN_ZONE_TICKS*TICK_SIZE): continue
        pG,pR,bR = pC>pO, pC<pO, bC<bO
        ts = T[i]
        nBMax,nBMin = max(nO,nC),min(nO,nC)

        if pG and bR and nBMax<=bH+1e-9:
            top,bot = max(bH,bC),min(bH,bC)
            if top-bot>=MIN_ZONE_TICKS*TICK_SIZE and not _overlaps(top,bot,ZoneKind.Supply):
                z = Zone(ZoneKind.Supply,top,bot,ts); zones.append(z); active.append(z)
        if pR and not bR and nBMin>=bL-1e-9:
            top,bot = max(bC,bL),min(bC,bL)
            if top-bot>=MIN_ZONE_TICKS*TICK_SIZE and not _overlaps(top,bot,ZoneKind.Demand):
                z = Zone(ZoneKind.Demand,top,bot,ts); zones.append(z); active.append(z)
        if pG and nBMax>bH+1e-9:
            top,bot = bH,bL
            if top-bot>=MIN_ZONE_TICKS*TICK_SIZE and not _overlaps(top,bot,ZoneKind.RBR):
                z = Zone(ZoneKind.RBR,top,bot,ts); zones.append(z); active.append(z)
        if pR and nBMin<bL-1e-9:
            top,bot = bH,bL
            if top-bot>=MIN_ZONE_TICKS*TICK_SIZE and not _overlaps(top,bot,ZoneKind.DBD):
                z = Zone(ZoneKind.DBD,top,bot,ts); zones.append(z); active.append(z)
    return zones


def tag_confluence(z5: List[Zone], z15: List[Zone]):
    for a in z5:
        for b in z15:
            if a.is_sell != b.is_sell: continue
            if a.bot <= b.top+1e-9 and a.top >= b.bot-1e-9:
                a.is_confluent = b.is_confluent = True


# ── Trade simulation ──────────────────────────────────────────────────────────

def _sim(O1,H1,L1,C1,tm,start,n1,zone,entry,sl,tp,model,tf,filt,ets) -> Optional[Trade]:
    entry_date = ets.date()
    end = min(start+240, n1)
    for k in range(start, end):
        if tm[k].date() > entry_date:
            ep,r = O1[k],"EXPIRE"
        else:
            sh = H1[k]>=sl-1e-9 if zone.is_sell else L1[k]<=sl+1e-9
            th = L1[k]<=tp+1e-9 if zone.is_sell else H1[k]>=tp-1e-9
            if sh and th: ep,r = sl,"SL"
            elif sh:      ep,r = sl,"SL"
            elif th:      ep,r = tp,"TP"
            elif k==end-1:ep,r = C1[k],"EXPIRE"
            else: continue
        raw = ((entry-ep) if zone.is_sell else (ep-entry)) / TICK_SIZE * TICK_VALUE
        return Trade(str(entry_date),"SHORT" if zone.is_sell else "LONG",
                     model,tf,zone.kind.value,filt,entry,ep,r,
                     abs(entry-sl)/TICK_SIZE, raw-COMMISSION_RT)
    return None


# ── Core backtest ─────────────────────────────────────────────────────────────

def run(bars_1m: pd.DataFrame, flt: Dict, detection_tf: str,
        tp_mult: float, label: str,
        use_trend=False, adx_thresh=0.0, use_weekly=False,
        use_vol=False, use_time=False, require_conf=False,
        first_touch=False) -> List[Trade]:

    freq = {"5m":"5min","15m":"15min","30m":"30min"}[detection_tf]
    bars_tf = bars_1m.resample(freq).agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna(subset=["open"])

    all_zones = detect_zones(bars_tf)
    if not all_zones: return []

    if require_conf and detection_tf == "15m":
        b5 = bars_1m.resample("5min").agg(
            {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
        ).dropna(subset=["open"])
        tag_confluence(detect_zones(b5), all_zones)

    tm   = bars_1m.index
    O1   = bars_1m["open"].values;  H1 = bars_1m["high"].values
    L1   = bars_1m["low"].values;   C1 = bars_1m["close"].values
    n1   = len(bars_1m)

    ema_v    = flt["ema_1h"]
    adx_v    = flt["adx_1h"]
    wbull_v  = flt["weekly_bull"]
    vol_v    = flt["vol_regime"]
    etmin_v  = flt["et_min"]
    close_v  = flt["close_1m"]
    buf      = CLOSE_BUF_TICKS * TICK_SIZE
    valid_m  = {"5m":5,"15m":15,"30m":30}[detection_tf]
    trades   = []

    for zone in all_zones:
        if zone.height < MIN_ENTRY_TICKS * TICK_SIZE: continue
        if require_conf and not zone.is_confluent: continue

        start_idx = int(tm.searchsorted(zone.formed_ts, side="right"))
        if start_idx >= n1: continue

        sl_px      = zone.sl_price()
        end_idx    = min(start_idx + MAX_ZONE_AGE_1M, n1)
        valid_aft  = zone.formed_ts + pd.Timedelta(minutes=valid_m)
        touches    = 0
        fired      = False

        for j in range(start_idx, end_idx):
            o,h,lo,c = O1[j],H1[j],L1[j],C1[j]
            bmax,bmin = max(o,c),min(o,c)

            if zone.is_sell and bmax > zone.distal+1e-9: break
            if not zone.is_sell and bmin < zone.distal-1e-9: break

            if h>=zone.bot-1e-9 and lo<=zone.top+1e-9:
                touches += 1
                if touches > 2: break

            if fired: continue
            if tm[j] <= valid_aft: continue
            if first_touch and touches > 1: continue
            if use_time and MIDDAY_START <= etmin_v[j] <= MIDDAY_END: continue
            if use_vol  and not vol_v[j]: continue

            rng = h - lo
            if rng < TICK_SIZE: continue
            uw = h - bmax;  lw = bmin - lo

            # Wick signal
            if zone.is_sell:
                if not (h >= zone.proximal-1e-9): continue
                if (uw/rng) < WICK_MIN_PCT: continue
                if c >= zone.proximal - buf: continue
            else:
                if not (lo <= zone.proximal+1e-9): continue
                if (lw/rng) < WICK_MIN_PCT: continue
                if c <= zone.proximal + buf: continue

            # Trend filter (1h EMA)
            if use_trend:
                ema_now = ema_v[j]
                if zone.is_sell and c >= ema_now: continue
                if not zone.is_sell and c <= ema_now: continue

            # ADX filter
            if adx_thresh > 0:
                if adx_v[j] < adx_thresh: continue
                # Also require direction alignment (DI+/DI-)
                # We use close vs EMA as direction proxy when ADX confirms trend
                ema_now = ema_v[j]
                if zone.is_sell and c >= ema_now: continue
                if not zone.is_sell and c <= ema_now: continue

            # Weekly bias filter
            if use_weekly:
                bull_week = wbull_v[j]
                if zone.is_sell and bull_week: continue    # don't short in bullish week
                if not zone.is_sell and not bull_week: continue  # don't buy in bearish week

            if j+1 >= n1: break
            entry_px = O1[j+1]
            risk = abs(entry_px - sl_px)
            if risk < TICK_SIZE: continue
            tp_px = (entry_px - risk*tp_mult) if zone.is_sell else (entry_px + risk*tp_mult)

            t = _sim(O1,H1,L1,C1,tm,j+2,n1,zone,entry_px,sl_px,tp_px,label,
                     detection_tf,label,tm[j+1])
            if t: trades.append(t)
            fired = True
            break

    return trades


# ── Reporting ─────────────────────────────────────────────────────────────────

def _fmt(trades: List[Trade], label: str) -> str:
    if not trades: return f"  {label}: — no trades —\n"
    n   = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    net = sum(t.pnl for t in trades)
    wp  = sum(t.pnl for t in wins)
    lp  = sum(t.pnl for t in losses)
    wr  = len(wins)/n*100
    pf  = abs(wp/lp) if lp else 99.9
    ar  = sum(t.risk_ticks for t in trades)/n
    tp_n= sum(1 for t in trades if t.exit_reason=="TP")
    sl_n= sum(1 for t in trades if t.exit_reason=="SL")
    lines = [
        f"{'─'*68}",
        f"  {label}",
        f"{'─'*68}",
        f"  Trades: {n}  Wins: {len(wins)}  Losses: {len(losses)}",
        f"  WR: {wr:.1f}%  PF: {pf:.2f}  Net: ${net:,.0f}  Avg Risk: {ar:.0f}t",
        f"  AvgWin: ${wp/max(len(wins),1):,.0f}  AvgLoss: ${lp/max(len(losses),1):,.0f}  "
        f"TP:{tp_n} SL:{sl_n} Exp:{n-tp_n-sl_n}",
    ]
    for kind in ZoneKind:
        kt = [t for t in trades if t.zone_kind==kind.value]
        if not kt: continue
        kw = sum(1 for t in kt if t.pnl>0)
        lines.append(f"    {kind.value:<8}: {len(kt):3d}  {kw/len(kt)*100:5.1f}% WR  "
                     f"${sum(t.pnl for t in kt):>8,.0f}")
    return "\n".join(lines)+"\n"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    download()
    bars_1m = load_rth()
    flt     = build_filters(bars_1m)

    # ── Combo matrix ────────────────────────────────────────────────────────
    # (label, tf, tp, trend, adx_thresh, weekly, vol, time, conf, first_touch)
    combos = []

    for tf in ["15m", "5m"]:
        for tp in [1.5, 2.0, 3.0]:
            combos += [
                # Baseline
                (f"BASELINE         TF={tf} TP={tp}x", tf, tp,
                 False, 0,    False, False, False, False, False),
                # Single filters
                (f"+TREND           TF={tf} TP={tp}x", tf, tp,
                 True,  0,    False, False, False, False, False),
                (f"+ADX15           TF={tf} TP={tp}x", tf, tp,
                 False, 15.0, False, False, False, False, False),
                (f"+ADX20           TF={tf} TP={tp}x", tf, tp,
                 False, 20.0, False, False, False, False, False),
                (f"+ADX25           TF={tf} TP={tp}x", tf, tp,
                 False, 25.0, False, False, False, False, False),
                (f"+WEEKLY          TF={tf} TP={tp}x", tf, tp,
                 False, 0,    True,  False, False, False, False),
                (f"+VOL             TF={tf} TP={tp}x", tf, tp,
                 False, 0,    False, True,  False, False, False),
                (f"+TIME            TF={tf} TP={tp}x", tf, tp,
                 False, 0,    False, False, True,  False, False),
                (f"+1ST_TOUCH       TF={tf} TP={tp}x", tf, tp,
                 False, 0,    False, False, False, False, True),
                # Two-filter stacks anchored on trend
                (f"+TREND+ADX15     TF={tf} TP={tp}x", tf, tp,
                 True,  15.0, False, False, False, False, False),
                (f"+TREND+ADX20     TF={tf} TP={tp}x", tf, tp,
                 True,  20.0, False, False, False, False, False),
                (f"+TREND+ADX25     TF={tf} TP={tp}x", tf, tp,
                 True,  25.0, False, False, False, False, False),
                (f"+TREND+WEEKLY    TF={tf} TP={tp}x", tf, tp,
                 True,  0,    True,  False, False, False, False),
                (f"+TREND+VOL       TF={tf} TP={tp}x", tf, tp,
                 True,  0,    False, True,  False, False, False),
                (f"+TREND+TIME      TF={tf} TP={tp}x", tf, tp,
                 True,  0,    False, False, True,  False, False),
                (f"+TREND+1ST       TF={tf} TP={tp}x", tf, tp,
                 True,  0,    False, False, False, False, True),
                # Weekly + other
                (f"+WEEKLY+ADX20    TF={tf} TP={tp}x", tf, tp,
                 False, 20.0, True,  False, False, False, False),
                (f"+WEEKLY+VOL      TF={tf} TP={tp}x", tf, tp,
                 False, 0,    True,  True,  False, False, False),
                # Three-filter stacks
                (f"+TREND+ADX20+WK  TF={tf} TP={tp}x", tf, tp,
                 True,  20.0, True,  False, False, False, False),
                (f"+TREND+ADX20+VOL TF={tf} TP={tp}x", tf, tp,
                 True,  20.0, False, True,  False, False, False),
                (f"+TREND+WK+VOL    TF={tf} TP={tp}x", tf, tp,
                 True,  0,    True,  True,  False, False, False),
                (f"+TREND+ADX20+TIM TF={tf} TP={tp}x", tf, tp,
                 True,  20.0, False, False, True,  False, False),
                # Full stack
                (f"+ALL             TF={tf} TP={tp}x", tf, tp,
                 True,  20.0, True,  True,  True,  False, True),
            ]

    results = []
    total   = len(combos)
    print(f"\nRunning {total} combinations...\n")

    lines = [
        "=" * 68,
        "  INSTITUTIONAL ZONES + WICK — 1-YEAR FULL FILTER MATRIX",
        f"  NQ Futures  {START} → {END}  |  RTH bars: {len(bars_1m):,}",
        f"  Filters: TREND(1h EMA{TREND_EMA_PERIOD}) | ADX(1h,{ADX_PERIOD}) | "
        f"WEEKLY_BIAS | VOL_REGIME | TIME | 1ST_TOUCH",
        "=" * 68,
    ]

    for i, (label, tf, tp, trend, adx, weekly, vol, tim, conf, first) in enumerate(combos, 1):
        sys.stdout.write(f"\r  [{i:3d}/{total}] {label} ...")
        sys.stdout.flush()
        trades = run(bars_1m, flt, tf, tp, label,
                     use_trend=trend, adx_thresh=adx, use_weekly=weekly,
                     use_vol=vol, use_time=tim, require_conf=conf,
                     first_touch=first)
        sys.stdout.write(f" {len(trades)} trades\n")
        sys.stdout.flush()
        lines.append(_fmt(trades, label))
        results.append((label, tf, tp, trades))

    # ── Summary table ────────────────────────────────────────────────────────
    lines.append("\n" + "="*78)
    lines.append("  SUMMARY TABLE  (sorted by Net PnL — all TF/TP combos)")
    lines.append("="*78)
    lines.append(f"  {'Label':<36} {'N':>5} {'WR%':>6} {'PF':>5} {'Net$':>10} {'$/trade':>8}")
    lines.append("  "+"─"*73)

    results.sort(key=lambda r: -sum(t.pnl for t in r[3]))
    for (lbl,tf,tp,trades) in results:
        if not trades: continue
        n   = len(trades)
        wr  = sum(1 for t in trades if t.pnl>0)/n*100
        net = sum(t.pnl for t in trades)
        wp  = sum(t.pnl for t in trades if t.pnl>0)
        lp  = sum(t.pnl for t in trades if t.pnl<=0)
        pf  = abs(wp/lp) if lp else 99.9
        ppt = net/n
        lines.append(f"  {lbl:<36} {n:>5} {wr:>6.1f} {pf:>5.2f} {net:>10,.0f} {ppt:>8,.0f}")

    # ── Top 20 by PF (min 15 trades) ─────────────────────────────────────────
    lines.append("\n" + "="*78)
    lines.append("  TOP 20 BY PROFIT FACTOR  (min 15 trades)")
    lines.append("="*78)
    lines.append(f"  {'Label':<36} {'N':>5} {'WR%':>6} {'PF':>5} {'Net$':>10}")
    lines.append("  "+"─"*73)

    eligible = [(l,t,tr) for (l,_tf,_tp,tr) in results
                if len(tr) >= 15
                for t in [sum(t.pnl for t in tr)]]
    by_pf = sorted([(l,tr) for (l,tf,tp,tr) in results if len(tr)>=15],
                   key=lambda r: -abs(sum(t.pnl for t in r[1] if t.pnl>0) /
                                      (sum(t.pnl for t in r[1] if t.pnl<=0) or -1)))
    for (lbl,trades) in by_pf[:20]:
        n   = len(trades)
        wr  = sum(1 for t in trades if t.pnl>0)/n*100
        net = sum(t.pnl for t in trades)
        wp  = sum(t.pnl for t in trades if t.pnl>0)
        lp  = sum(t.pnl for t in trades if t.pnl<=0)
        pf  = abs(wp/lp) if lp else 99.9
        lines.append(f"  {lbl:<36} {n:>5} {wr:>6.1f} {pf:>5.2f} {net:>10,.0f}")

    # ── Quarterly breakdown of top 5 models ──────────────────────────────────
    lines.append("\n" + "="*68)
    lines.append("  QUARTERLY BREAKDOWN — TOP 5 MODELS BY NET PnL (min 10 trades overall)")
    lines.append("="*68)

    top5 = [(l,tf,tp,tr,t,w,p) for (l,tf,tp,tr) in results
            if len(tr)>=10
            for t in [len(tr)]
            for w in [sum(1 for x in tr if x.pnl>0)/t*100]
            for lp in [sum(x.pnl for x in tr if x.pnl<=0)]
            for p in [abs(sum(x.pnl for x in tr if x.pnl>0)/lp) if lp else 99.9]]
    top5.sort(key=lambda r: -sum(t.pnl for t in r[3]))

    quarters = [
        ("Q1-2025","2025-01-01","2025-04-01"),
        ("Q2-2025","2025-04-01","2025-07-01"),
        ("Q3-2025","2025-07-01","2025-10-01"),
        ("Q4-2025","2025-10-01","2026-01-01"),
        ("Q1-2026","2026-01-01","2026-04-25"),
    ]

    for (lbl,tf,tp,tr,_,_,_) in top5[:5]:
        combo_params = next(
            (trend,adx,weekly,vol,tim,conf,first)
            for (l2,tf2,tp2,trend,adx,weekly,vol,tim,conf,first) in combos
            if l2==lbl and tf2==tf and tp2==tp
        )
        trend,adx,weekly,vol,tim,conf,first = combo_params
        lines.append(f"\n  {lbl}")
        for (qname,qstart,qend) in quarters:
            mask  = (bars_1m.index >= qstart) & (bars_1m.index < qend)
            q_bar = bars_1m[mask]
            if len(q_bar) < 100: continue
            mask_np = np.asarray(mask)
            q_flt = {k: v[mask_np] for k,v in flt.items()}
            qt = run(q_bar, q_flt, tf, tp, lbl,
                     use_trend=trend, adx_thresh=adx, use_weekly=weekly,
                     use_vol=vol, use_time=tim, require_conf=conf,
                     first_touch=first)
            if not qt:
                lines.append(f"    {qname}: — no trades —")
                continue
            qn   = len(qt)
            qwr  = sum(1 for t in qt if t.pnl>0)/qn*100
            qnet = sum(t.pnl for t in qt)
            qwp  = sum(t.pnl for t in qt if t.pnl>0)
            qlp  = sum(t.pnl for t in qt if t.pnl<=0)
            qpf  = abs(qwp/qlp) if qlp else 99.9
            lines.append(f"    {qname}: {qn:3d} trades  {qwr:5.1f}% WR  "
                         f"PF {qpf:.2f}  ${qnet:>8,.0f}")

    elapsed = time.time() - t0
    lines.append(f"\n  Total time: {elapsed:.0f}s")

    output = "\n".join(lines)
    print("\n" + output)
    RES_OUT.write_text(output, encoding="utf-8")
    print(f"\n→ {RES_OUT}")


if __name__ == "__main__":
    main()
