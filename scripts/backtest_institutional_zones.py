#!/usr/bin/env python3
"""
Institutional Zones Entry Model Backtest
Ports InstitutionalZones_MTF v4.5 zone detection to Python and tests
five entry models: PROXIMAL, DISTAL, MID, PIN_REJECT, CLOSE_IN.

"Entry model is where there is a level. There is an actual border
 laying on the edge of the level." — PROXIMAL is the baseline.

Run from WSL:
  /mnt/c/Users/Tea/DEEP6/.venv/bin/python scripts/backtest_institutional_zones.py
"""

import sys
import time
import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Constants ──────────────────────────────────────────────────────────────
TICK_SIZE = 0.25
TICK_VALUE = 5.0             # $ per tick per contract
COMMISSION_RT = 0.70         # round-trip $ per contract
NQ_MIN_PRICE = 10_000.0      # sanity filter on bars
NQ_MAX_PRICE = 35_000.0

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/nq_3mo_1m.csv"
OUT_PATH = ROOT / "scripts/results_institutional_zones.txt"

# Zone detection parameters (mirrors NinjaScript v4.5 defaults)
SMALL_BODY_RATIO = 0.50
MIN_ZONE_TICKS = 1
SL_BUFFER_TICKS = 4          # ticks beyond distal edge for stop
MAX_ZONE_AGE_1M = 500        # max 1m bars to hold a zone open (~8 RTH hrs)
MAX_TOUCHES = 2              # invalidate zone after this many intra-zone touches

# Backtest parameters
TP_RISK_MULTIPLES = [1.5, 2.0, 3.0]
DETECTION_TFS = ["5m", "15m", "30m"]

# RTH session (minutes since midnight ET)
RTH_START_MIN = 9 * 60 + 30   # 9:30
RTH_END_MIN = 16 * 60 + 15    # 16:15


# ── Enumerations ───────────────────────────────────────────────────────────

class ZoneKind(Enum):
    Supply = "Supply"   # reversal short
    Demand = "Demand"   # reversal long
    RBR = "RBR"         # Rally-Base-Rally continuation long
    DBD = "DBD"         # Drop-Base-Drop continuation short


class EntryModel(Enum):
    PROXIMAL   = "PROXIMAL"    # limit at proximal edge (the near border)
    DISTAL     = "DISTAL"      # limit at distal edge (deep into zone)
    MID        = "MID"         # limit at zone midpoint
    PIN_REJECT = "PIN_REJECT"  # wick enters zone, bar closes outside → next open
    CLOSE_IN   = "CLOSE_IN"   # first bar that closes inside zone → next open


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class Zone:
    kind: ZoneKind
    top: float
    bot: float
    formed_ts: pd.Timestamp
    depart_ratio: float   # immediate next-bar move / zone height
    score: int
    touch_count: int = 0
    active: bool = True

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
        """Near border: price approaches from this side."""
        return self.bot if self.is_sell else self.top

    @property
    def distal(self) -> float:
        """Far border: deeper in zone."""
        return self.top if self.is_sell else self.bot

    def limit_price(self, model: "EntryModel") -> Optional[float]:
        if model == EntryModel.PROXIMAL:
            return self.proximal
        if model == EntryModel.DISTAL:
            return self.distal
        if model == EntryModel.MID:
            return self.mid
        return None  # bar-by-bar models

    def sl_price(self) -> float:
        buf = SL_BUFFER_TICKS * TICK_SIZE
        return (self.distal + buf) if self.is_sell else (self.distal - buf)


@dataclass
class Trade:
    date: str
    direction: str
    entry_model: str
    tf: str
    zone_kind: str
    zone_score: int
    entry_price: float
    exit_price: float
    sl_price: float
    tp_price: float
    exit_reason: str   # TP | SL | EXPIRE
    risk_ticks: float
    pnl: float         # net of commission


# ── EMA ────────────────────────────────────────────────────────────────────

def _ema(series: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(series, dtype=float)
    k = 2.0 / (period + 1)
    out[0] = series[0]
    for i in range(1, len(series)):
        out[i] = series[i] * k + out[i - 1] * (1.0 - k)
    return out


# ── Zone detection ─────────────────────────────────────────────────────────

def detect_zones(bars: pd.DataFrame) -> List[Zone]:
    """
    Detect Supply / Demand / RBR / DBD zones from a OHLCV DataFrame.
    DataFrame must have DatetimeIndex and columns: open, high, low, close.
    Returns zones in chronological order of formation (confirmation bar close).
    """
    n = len(bars)
    if n < 3:
        return []

    O = bars["open"].values
    H = bars["high"].values
    L = bars["low"].values
    C = bars["close"].values
    T = bars.index  # DatetimeIndex

    ema50 = _ema(C, 50)

    zones: List[Zone] = []
    active: List[Zone] = []  # for dedup

    def _overlaps(top: float, bot: float, kind: ZoneKind) -> bool:
        for z in active:
            if z.kind != kind:
                continue
            if bot <= z.top + 1e-9 and top >= z.bot - 1e-9:
                return True
        return False

    def _score(dr: float, trend_ok: bool) -> int:
        scFresh = 3
        scDepart = 3 if dr >= 5 else (2 if dr >= 3 else (1 if dr >= 1.5 else 0))
        scBase = 2
        scTrend = 2 if trend_ok else 0
        return scFresh + scDepart + scBase + scTrend

    for i in range(2, n):
        pO, pC = O[i - 2], C[i - 2]
        bO, bC, bH, bL = O[i - 1], C[i - 1], H[i - 1], L[i - 1]
        nO, nC, nH, nL = O[i], C[i], H[i], L[i]

        prev_body = abs(pC - pO)
        base_body = abs(bC - bO)
        next_body = abs(nC - nO)
        base_range = bH - bL

        if prev_body <= 0 or next_body <= 0:
            continue

        small_vs_prev = base_body <= SMALL_BODY_RATIO * prev_body
        small_vs_next = base_body <= SMALL_BODY_RATIO * next_body
        tall_enough = base_range >= MIN_ZONE_TICKS * TICK_SIZE

        if not (small_vs_prev and small_vs_next and tall_enough):
            continue

        prev_green = pC > pO
        prev_red = pC < pO
        base_red = bC < bO
        base_green = bC > bO
        form_ts = T[i]

        # ── SUPPLY ─────────────────────────────────────────────────────────
        if prev_green and base_red:
            next_body_max = max(nO, nC)
            if next_body_max <= bH + 1e-9:
                top = max(bH, bC)  # = bH for red base
                bot = min(bH, bC)  # = bC
                if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Supply):
                    dr = abs(nC - bC) / max(top - bot, 1e-6)
                    trend_ok = ema50[i - 1] < ema50[i - 2]  # supply aligns with downtrend
                    z = Zone(ZoneKind.Supply, top, bot, form_ts, dr, _score(dr, trend_ok))
                    zones.append(z)
                    active.append(z)

        # ── DEMAND ─────────────────────────────────────────────────────────
        if prev_red and base_green:
            next_body_min = min(nO, nC)
            if next_body_min >= bL - 1e-9:
                top = max(bC, bL)  # = bC for green base
                bot = min(bC, bL)  # = bL
                if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.Demand):
                    dr = abs(nC - bC) / max(top - bot, 1e-6)
                    trend_ok = ema50[i - 1] > ema50[i - 2]  # demand aligns with uptrend
                    z = Zone(ZoneKind.Demand, top, bot, form_ts, dr, _score(dr, trend_ok))
                    zones.append(z)
                    active.append(z)

        # ── RBR ────────────────────────────────────────────────────────────
        if prev_green and (small_vs_prev and small_vs_next and tall_enough):
            next_body_max = max(nO, nC)
            if next_body_max > bH + 1e-9:
                top = bO if base_red else bC
                bot = bL
                if top < bot:
                    top, bot = bot, top
                if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.RBR):
                    dr = abs(nC - bC) / max(top - bot, 1e-6)
                    trend_ok = ema50[i - 1] > ema50[i - 2]
                    z = Zone(ZoneKind.RBR, top, bot, form_ts, dr, _score(dr, trend_ok))
                    zones.append(z)
                    active.append(z)

        # ── DBD ────────────────────────────────────────────────────────────
        if prev_red and (small_vs_prev and small_vs_next and tall_enough):
            next_body_min = min(nO, nC)
            if next_body_min < bL - 1e-9:
                top = bH
                bot = bC if base_red else bO
                if top < bot:
                    top, bot = bot, top
                if top - bot >= TICK_SIZE and not _overlaps(top, bot, ZoneKind.DBD):
                    dr = abs(nC - bC) / max(top - bot, 1e-6)
                    trend_ok = ema50[i - 1] < ema50[i - 2]
                    z = Zone(ZoneKind.DBD, top, bot, form_ts, dr, _score(dr, trend_ok))
                    zones.append(z)
                    active.append(z)

    return zones


# ── Trade simulation ───────────────────────────────────────────────────────

def _simulate_trade(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    times: pd.DatetimeIndex,
    start_idx: int,
    n: int,
    zone: Zone,
    entry_px: float,
    sl_px: float,
    tp_px: float,
    entry_model: EntryModel,
    tf: str,
    entry_ts: pd.Timestamp,
) -> Optional[Trade]:
    """Simulate a trade forward from start_idx."""
    entry_date = entry_ts.date() if hasattr(entry_ts, "date") else pd.Timestamp(entry_ts).date()
    max_hold = min(start_idx + 240, n)  # max 4 RTH hours

    for k in range(start_idx, max_hold):
        h = highs[k]
        lo = lows[k]
        o = opens[k]
        c = closes[k]
        bar_date = times[k].date()

        # Close trade at end of entry session
        if bar_date > entry_date:
            exit_px = o
            exit_reason = "EXPIRE"
        else:
            if zone.is_sell:
                sl_hit = h >= sl_px - 1e-9
                tp_hit = lo <= tp_px + 1e-9
            else:
                sl_hit = lo <= sl_px + 1e-9
                tp_hit = h >= tp_px - 1e-9

            if sl_hit and tp_hit:
                # Ambiguous — assume worst case (SL) unless gap favors TP
                exit_px = sl_px
                exit_reason = "SL"
            elif sl_hit:
                exit_px = sl_px
                exit_reason = "SL"
            elif tp_hit:
                exit_px = tp_px
                exit_reason = "TP"
            elif k == max_hold - 1:
                exit_px = c
                exit_reason = "EXPIRE"
            else:
                continue

        risk_ticks = abs(entry_px - sl_px) / TICK_SIZE
        if zone.is_sell:
            raw = (entry_px - exit_px) / TICK_SIZE * TICK_VALUE
        else:
            raw = (exit_px - entry_px) / TICK_SIZE * TICK_VALUE
        net = raw - COMMISSION_RT

        return Trade(
            date=str(entry_date),
            direction="SHORT" if zone.is_sell else "LONG",
            entry_model=entry_model.value,
            tf=tf,
            zone_kind=zone.kind.value,
            zone_score=zone.score,
            entry_price=entry_px,
            exit_price=exit_px,
            sl_price=sl_px,
            tp_price=tp_px,
            exit_reason=exit_reason,
            risk_ticks=risk_ticks,
            pnl=net,
        )
    return None


# ── Main backtest engine ───────────────────────────────────────────────────

def run_backtest(
    bars_1m: pd.DataFrame,
    detection_tf: str,
    entry_model: EntryModel,
    tp_multiple: float,
) -> List[Trade]:
    freq_map = {"5m": "5min", "15m": "15min", "30m": "30min"}
    bars_tf = bars_1m.resample(freq_map[detection_tf]).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna(subset=["open"])

    all_zones = detect_zones(bars_tf)
    if not all_zones:
        return []

    # Pre-extract 1m arrays for speed
    tm = bars_1m.index
    O1 = bars_1m["open"].values
    H1 = bars_1m["high"].values
    L1 = bars_1m["low"].values
    C1 = bars_1m["close"].values
    n1 = len(bars_1m)

    trades: List[Trade] = []

    for zone in all_zones:
        if zone.height < TICK_SIZE:
            continue

        # Find first 1m bar AFTER zone formation
        start_idx = int(tm.searchsorted(zone.formed_ts, side="right"))
        if start_idx >= n1:
            continue

        sl_px = zone.sl_price()
        limit_px = zone.limit_price(entry_model)  # None for bar-by-bar models

        if limit_px is not None:
            risk = abs(limit_px - sl_px)
            if risk < TICK_SIZE:
                continue

        end_idx = min(start_idx + MAX_ZONE_AGE_1M, n1)
        touch_count = 0

        for j in range(start_idx, end_idx):
            o, h, lo, c = O1[j], H1[j], L1[j], C1[j]

            # Zone invalidation: body closes beyond distal edge
            body_max = max(o, c)
            body_min = min(o, c)
            if zone.is_sell and body_max > zone.distal + 1e-9:
                break
            if not zone.is_sell and body_min < zone.distal - 1e-9:
                break

            # Touch tracking
            enters_zone = h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9
            if enters_zone:
                touch_count += 1
                if touch_count > MAX_TOUCHES:
                    break

            # ── PROXIMAL / DISTAL / MID (limit order models) ──────────────
            if limit_px is not None:
                filled = (zone.is_sell and h >= limit_px - 1e-9) or \
                         (not zone.is_sell and lo <= limit_px + 1e-9)
                if filled:
                    entry_px = limit_px
                    risk_here = abs(entry_px - sl_px)
                    if risk_here < TICK_SIZE:
                        break
                    tp_px = (entry_px - risk_here * tp_multiple) if zone.is_sell \
                            else (entry_px + risk_here * tp_multiple)
                    t = _simulate_trade(O1, H1, L1, C1, tm, j + 1, n1, zone,
                                        entry_px, sl_px, tp_px, entry_model,
                                        detection_tf, tm[j])
                    if t:
                        trades.append(t)
                    break

            # ── PIN_REJECT ─────────────────────────────────────────────────
            elif entry_model == EntryModel.PIN_REJECT:
                if zone.is_sell:
                    # Wick touches proximal edge, bar closes BELOW it (rejection)
                    if h >= zone.proximal - 1e-9 and c < zone.proximal - 1e-9:
                        if j + 1 < n1:
                            entry_px = O1[j + 1]
                            risk_here = abs(entry_px - sl_px)
                            if risk_here < TICK_SIZE:
                                break
                            tp_px = entry_px - risk_here * tp_multiple
                            t = _simulate_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                                entry_px, sl_px, tp_px, entry_model,
                                                detection_tf, tm[j + 1])
                            if t:
                                trades.append(t)
                        break
                else:
                    # Wick touches proximal edge, bar closes ABOVE it (rejection)
                    if lo <= zone.proximal + 1e-9 and c > zone.proximal + 1e-9:
                        if j + 1 < n1:
                            entry_px = O1[j + 1]
                            risk_here = abs(entry_px - sl_px)
                            if risk_here < TICK_SIZE:
                                break
                            tp_px = entry_px + risk_here * tp_multiple
                            t = _simulate_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                                entry_px, sl_px, tp_px, entry_model,
                                                detection_tf, tm[j + 1])
                            if t:
                                trades.append(t)
                        break

            # ── CLOSE_IN ──────────────────────────────────────────────────
            elif entry_model == EntryModel.CLOSE_IN:
                close_inside = zone.bot - 1e-9 <= c <= zone.top + 1e-9
                if close_inside and enters_zone:
                    if j + 1 < n1:
                        entry_px = O1[j + 1]
                        risk_here = abs(entry_px - sl_px)
                        if risk_here < TICK_SIZE:
                            break
                        tp_px = (entry_px - risk_here * tp_multiple) if zone.is_sell \
                                else (entry_px + risk_here * tp_multiple)
                        t = _simulate_trade(O1, H1, L1, C1, tm, j + 2, n1, zone,
                                            entry_px, sl_px, tp_px, entry_model,
                                            detection_tf, tm[j + 1])
                        if t:
                            trades.append(t)
                    break

    return trades


# ── Reporting ──────────────────────────────────────────────────────────────

def _report_block(trades: List[Trade], label: str) -> str:
    if not trades:
        return f"  {label}: — no trades —\n"

    n = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    net = sum(t.pnl for t in trades)
    win_pnl = sum(t.pnl for t in wins)
    loss_pnl = sum(t.pnl for t in losses)
    wr = len(wins) / n * 100
    pf = abs(win_pnl / loss_pnl) if loss_pnl != 0 else float("inf")
    avg_risk = sum(t.risk_ticks for t in trades) / n
    avg_win = win_pnl / len(wins) if wins else 0
    avg_loss = loss_pnl / len(losses) if losses else 0
    tp_n = sum(1 for t in trades if t.exit_reason == "TP")
    sl_n = sum(1 for t in trades if t.exit_reason == "SL")
    exp_n = sum(1 for t in trades if t.exit_reason == "EXPIRE")

    lines = [
        f"{'─'*62}",
        f"  {label}",
        f"{'─'*62}",
        f"  Trades: {n}  |  Wins: {len(wins)}  Losses: {len(losses)}",
        f"  Win Rate: {wr:.1f}%  |  Profit Factor: {pf:.2f}",
        f"  Net PnL: ${net:>10,.0f}  |  Avg Risk: {avg_risk:.1f} ticks",
        f"  Avg Win: ${avg_win:>8,.0f}  |  Avg Loss: ${avg_loss:>8,.0f}",
        f"  Exits → TP: {tp_n}  SL: {sl_n}  Expire: {exp_n}",
    ]

    # By zone type
    lines.append("  ── By zone type:")
    for kind in ZoneKind:
        kt = [t for t in trades if t.zone_kind == kind.value]
        if not kt:
            continue
        kw = sum(1 for t in kt if t.pnl > 0)
        knet = sum(t.pnl for t in kt)
        lines.append(f"    {kind.value:<8}: {len(kt):3d} trades  {kw/len(kt)*100:5.1f}% WR  ${knet:>8,.0f}")

    # Score filters
    lines.append("  ── Score-filtered subsets:")
    for thr in [6, 8, 10]:
        ht = [t for t in trades if t.zone_score >= thr]
        if not ht:
            continue
        hw = sum(1 for t in ht if t.pnl > 0)
        hnet = sum(t.pnl for t in ht)
        lines.append(f"    Score≥{thr}: {len(ht):3d} trades  {hw/len(ht)*100:5.1f}% WR  ${hnet:>8,.0f}")

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

    # Price sanity filter
    df = df[(df["close"] >= NQ_MIN_PRICE) & (df["close"] <= NQ_MAX_PRICE)]

    # RTH filter (9:30–16:15 ET)
    try:
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
        df_et = df.tz_convert(et_tz)
        et_min = df_et.index.hour * 60 + df_et.index.minute
        rth = (et_min >= RTH_START_MIN) & (et_min <= RTH_END_MIN)
        bars_1m = df[rth].copy()
    except Exception:
        # Approximate: EDT offset -4
        approx_et_min = ((df.index.hour - 4) % 24) * 60 + df.index.minute
        rth = (approx_et_min >= RTH_START_MIN) & (approx_et_min <= RTH_END_MIN)
        bars_1m = df[rth].copy()

    print(f"RTH bars: {len(bars_1m):,}  |  {bars_1m.index[0].date()} → {bars_1m.index[-1].date()}")

    lines = [
        "=" * 62,
        "  INSTITUTIONAL ZONES — ENTRY MODEL BACKTEST",
        f"  NQ Futures  |  {bars_1m.index[0].date()} → {bars_1m.index[-1].date()}",
        f"  RTH 1m bars: {len(bars_1m):,}",
        "  Entry models: PROXIMAL | DISTAL | MID | PIN_REJECT | CLOSE_IN",
        "  SL: zone distal + 4 ticks  |  TP: 1.5x / 2.0x / 3.0x risk",
        "=" * 62,
    ]

    summary_rows = []

    for tf in DETECTION_TFS:
        lines.append(f"\n{'═'*62}")
        lines.append(f"  DETECTION TF: {tf}")
        lines.append(f"{'═'*62}")

        for model in EntryModel:
            for tp_mult in TP_RISK_MULTIPLES:
                label = f"{model.value}  TF={tf}  TP={tp_mult}x"
                sys.stdout.write(f"  {label} ...")
                sys.stdout.flush()
                trades = run_backtest(bars_1m, tf, model, tp_mult)
                sys.stdout.write(f" {len(trades)} trades\n")
                sys.stdout.flush()

                lines.append(_report_block(trades, label))
                summary_rows.append((tf, model.value, tp_mult, trades))

    # Summary comparison table sorted by net PnL
    lines.append("=" * 75)
    lines.append("  SUMMARY TABLE  (sorted by Net PnL)")
    lines.append("=" * 75)
    lines.append(f"  {'Model':<12}  {'TF':<5}  {'TP':>4}  {'N':>5}  {'WR%':>6}  {'PF':>5}  {'Net$':>10}  {'AvgRisk':>7}")
    lines.append("  " + "─" * 70)

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
        avg_risk = sum(t.risk_ticks for t in trades) / n
        lines.append(f"  {model:<12}  {tf:<5}  {tp_mult:>4.1f}  {n:>5}  {wr:>6.1f}  {pf:>5.2f}  {net:>10,.0f}  {avg_risk:>7.1f}")

    elapsed = time.time() - t0
    lines.append(f"\n  Completed in {elapsed:.1f}s")

    output = "\n".join(lines)
    print("\n" + output)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(output, encoding="utf-8")
    print(f"\nResults → {OUT_PATH}")


if __name__ == "__main__":
    main()
