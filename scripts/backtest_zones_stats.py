#!/usr/bin/env python3
"""
Zone Entry — Statistical Validity Analysis
Runs Variant D (the winner) and applies rigorous statistical tests to determine
whether the observed edge is real or an artifact of overfitting.

Tests:
  1. Re-run Variant D to get exact 101-trade PnL sequence
  2. Bootstrap CIs (10,000 resamples) on WR, PF, Sharpe, Net PnL, Max DD
  3. Permutation test on Sharpe (10,000 shuffles)
  4. Monte Carlo forward simulation (10,000 paths, 12 months)
  5. Autocorrelation / runs test
  6. Minimum edge / break-even WR analysis

Run (Windows):
  python scripts/backtest_zones_stats.py
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple
import sys

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

# ── Constants (identical to backtest_zones_1yr.py) ─────────────────────────────
TICK_SIZE    = 0.25
TICK_VALUE   = 5.0
COMMISSION   = 0.70
NQ_MIN_PRICE = 10_000.0
NQ_MAX_PRICE = 35_000.0

ROOT    = Path(__file__).resolve().parents[1]
CSV_1YR = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_TXT = ROOT / "scripts/results_zones_stats.txt"

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

VARIANT_D_SCORE_GATE = 6
VARIANT_D_TOD_START  = 10 * 60
VARIANT_D_TOD_END    = 15 * 60

N_BOOTSTRAP   = 10_000
N_PERMUTATION = 10_000
N_MC_PATHS    = 10_000
MC_TRADES     = 84   # ~7/month * 12 months


# ── Zone detection (copied verbatim from backtest_zones_1yr.py) ─────────────────

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


def _ema(x: np.ndarray, period: int) -> np.ndarray:
    out = np.empty_like(x, dtype=float)
    k = 2.0 / (period + 1); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = x[i] * k + out[i-1] * (1.0 - k)
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

        bmax, bmin = max(o, c), min(o, c)
        if zone.is_sell and bmax > zone.distal + 1e-9: return None
        if not zone.is_sell and bmin < zone.distal - 1e-9: return None

        if h >= zone.bot - 1e-9 and lo <= zone.top + 1e-9:
            touch_count += 1
            if touch_count > MAX_TOUCHES: return None

        ts = pd.Timestamp(tm[j])
        bar_min = ts.hour * 60 + ts.minute
        if bar_min < tod_start or bar_min >= tod_end:
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


# ── Core metrics helpers ─────────────────────────────────────────────────────────

def calc_metrics_from_pnls(pnls: np.ndarray) -> dict:
    """Compute metrics from a raw PnL array."""
    if len(pnls) == 0:
        return dict(n=0, net=0.0, wr=0.0, pf=0.0, sharpe=0.0, maxdd=0.0)
    eq   = np.cumsum(pnls)
    peak = np.maximum.accumulate(eq)
    maxdd = float(np.max(peak - eq))
    wins  = pnls[pnls > 0]; loss = pnls[pnls <= 0]
    gp = wins.sum() if len(wins) else 0.0
    gl = -loss.sum() if len(loss) else 0.0
    wr = len(wins) / len(pnls)
    pf = gp / gl if gl > 0 else 999.0
    mu = float(pnls.mean())
    sd = float(pnls.std(ddof=1)) if len(pnls) > 1 else 1e-9
    # Use trade-count-based Sharpe (annualised at 252 trading days, ~7 trades/day proxy)
    # More meaningful: annualise by sqrt(252) on per-trade Sharpe
    sharpe = (mu / sd) * np.sqrt(252) if sd > 0 else 0.0
    return dict(n=len(pnls), net=float(gp-gl), wr=wr, pf=pf, sharpe=sharpe, maxdd=maxdd)


# ── 1. Observed metrics ──────────────────────────────────────────────────────────

def compute_observed(pnls: np.ndarray) -> dict:
    return calc_metrics_from_pnls(pnls)


# ── 2. Bootstrap CIs ────────────────────────────────────────────────────────────

def bootstrap_ci(pnls: np.ndarray, n_boot: int = N_BOOTSTRAP,
                 ci_pct: float = 95.0, rng: np.random.Generator = None) -> dict:
    if rng is None:
        rng = np.random.default_rng(42)
    n = len(pnls)
    alpha = (100.0 - ci_pct) / 2.0

    boot_wr     = np.empty(n_boot)
    boot_pf     = np.empty(n_boot)
    boot_sharpe = np.empty(n_boot)
    boot_net    = np.empty(n_boot)
    boot_maxdd  = np.empty(n_boot)

    for i in range(n_boot):
        sample = rng.choice(pnls, size=n, replace=True)
        m = calc_metrics_from_pnls(sample)
        boot_wr[i]     = m["wr"]
        boot_pf[i]     = m["pf"]
        boot_sharpe[i] = m["sharpe"]
        boot_net[i]    = m["net"]
        boot_maxdd[i]  = m["maxdd"]

    def ci(arr):
        lo = np.percentile(arr, alpha)
        hi = np.percentile(arr, 100.0 - alpha)
        return float(lo), float(hi)

    return {
        "wr":     ci(boot_wr),
        "pf":     ci(boot_pf),
        "sharpe": ci(boot_sharpe),
        "net":    ci(boot_net),
        "maxdd":  ci(boot_maxdd),
        "boot_wr": boot_wr,       # keep full distributions for reporting
        "boot_sharpe": boot_sharpe,
    }


# ── 3. Permutation test on Sharpe ───────────────────────────────────────────────
#
# Classic shuffle-order permutation leaves mean/std unchanged → Sharpe unchanged.
# The correct null hypothesis tests are:
#
#   (a) Sign-randomization / sign-flip test:
#       H0: mean PnL == 0 (each trade equally likely to be + or -)
#       Randomly flip the sign of each trade independently.
#       p-value = fraction of sign-flip samples where mean >= observed mean.
#       This is the most powerful test for "is the mean return > 0?"
#
#   (b) Win-rate permutation:
#       H0: WR is consistent with 50/50
#       Binomial exact test: P(≥81 wins in 101 trials | p=0.5)
#
# Both are reported. The primary p-value is the sign-flip test on mean PnL.

def permutation_test_sharpe(pnls: np.ndarray, n_perm: int = N_PERMUTATION,
                             rng: np.random.Generator = None) -> dict:
    if rng is None:
        rng = np.random.default_rng(123)
    n = len(pnls)
    obs_mean   = float(pnls.mean())
    obs_sharpe = calc_metrics_from_pnls(pnls)["sharpe"]

    # (a) Sign-flip test on mean PnL
    # Under H0: each trade is equally likely win or loss of the same magnitude.
    # We draw n random ±1 signs and compute mean of sign-flipped trades.
    perm_means = np.empty(n_perm)
    abs_pnls   = np.abs(pnls)
    for i in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=n, replace=True)
        perm_means[i] = float((abs_pnls * signs).mean())

    # p-value: fraction of null-distribution means >= observed (one-tailed, right)
    p_signflip = float(np.mean(perm_means >= obs_mean))

    # (b) Binomial exact test: P(WR >= observed | p=0.5)
    n_wins = int(np.sum(pnls > 0))
    # scipy binom.sf gives P(X > k); we want P(X >= k) = P(X > k-1)
    from scipy.stats import binom as scipy_binom
    p_binomial = float(scipy_binom.sf(n_wins - 1, n, 0.5))

    # (c) t-test: is mean significantly > 0?
    t_stat, p_ttest = scipy_stats.ttest_1samp(pnls, popmean=0.0, alternative="greater")

    return {
        "observed_mean":     obs_mean,
        "observed_sharpe":   obs_sharpe,
        "n_wins":            n_wins,
        "n_trades":          n,
        # sign-flip test
        "p_signflip":        p_signflip,
        "perm_mean_mean":    float(perm_means.mean()),
        "perm_mean_p95":     float(np.percentile(perm_means, 95)),
        "perm_means":        perm_means,
        # binomial test
        "p_binomial":        p_binomial,
        # t-test
        "t_stat":            float(t_stat),
        "p_ttest":           float(p_ttest),
        # combined verdict: use sign-flip as primary, back with binomial + t-test
        "p_value":           p_signflip,
        "significant_001":   p_signflip < 0.01 and p_binomial < 0.01,
        "significant_005":   p_signflip < 0.05 and p_binomial < 0.05,
    }


# ── 4. Monte Carlo forward simulation ──────────────────────────────────────────

def monte_carlo_forward(pnls: np.ndarray, n_paths: int = N_MC_PATHS,
                        n_trades: int = MC_TRADES,
                        rng: np.random.Generator = None) -> dict:
    if rng is None:
        rng = np.random.default_rng(456)

    final_pnls = np.empty(n_paths)
    max_dds    = np.empty(n_paths)

    for i in range(n_paths):
        path = rng.choice(pnls, size=n_trades, replace=True)
        eq   = np.cumsum(path)
        peak = np.maximum.accumulate(eq)
        dd   = np.max(peak - eq)
        final_pnls[i] = eq[-1]
        max_dds[i]    = dd

    p_profitable   = float(np.mean(final_pnls > 0))
    p_dd_5k        = float(np.mean(max_dds > 5_000))
    p_dd_10k       = float(np.mean(max_dds > 10_000))
    expected_net   = float(np.mean(final_pnls))
    net_p10        = float(np.percentile(final_pnls, 10))
    net_p90        = float(np.percentile(final_pnls, 90))

    return {
        "n_paths":       n_paths,
        "n_trades":      n_trades,
        "p_profitable":  p_profitable,
        "p_dd_5k":       p_dd_5k,
        "p_dd_10k":      p_dd_10k,
        "expected_net":  expected_net,
        "net_p10":       net_p10,
        "net_p90":       net_p90,
        "final_pnls":    final_pnls,
        "max_dds":       max_dds,
    }


# ── 5. Autocorrelation / runs test ──────────────────────────────────────────────

def autocorrelation_analysis(pnls: np.ndarray) -> dict:
    """Lag-1 autocorrelation + Wald-Wolfowitz runs test."""
    n = len(pnls)

    # Lag-1 autocorrelation (Pearson on consecutive pairs)
    if n > 2:
        lag1_corr = float(np.corrcoef(pnls[:-1], pnls[1:])[0, 1])
    else:
        lag1_corr = 0.0

    # Runs test (Wald-Wolfowitz)
    # Convert to binary win/loss sequence
    wl = (pnls > 0).astype(int)
    n_wins  = int(wl.sum())
    n_loss  = n - n_wins

    # Count runs
    runs = 1
    for i in range(1, n):
        if wl[i] != wl[i-1]:
            runs += 1

    # Expected runs and variance under H0 (random sequence)
    if n_wins > 0 and n_loss > 0:
        mu_r  = (2 * n_wins * n_loss) / n + 1
        var_r = (2 * n_wins * n_loss * (2 * n_wins * n_loss - n)) / (n**2 * (n - 1))
        if var_r > 0:
            z_runs = (runs - mu_r) / np.sqrt(var_r)
            p_runs = 2.0 * (1.0 - scipy_stats.norm.cdf(abs(z_runs)))
        else:
            z_runs = 0.0; p_runs = 1.0
    else:
        mu_r = runs; var_r = 0.0; z_runs = 0.0; p_runs = 1.0

    # Interpretation
    # If p < 0.05 → sequence is NOT random (clustering or alternating pattern)
    clustered  = (z_runs < -1.96 and p_runs < 0.05)
    alternating = (z_runs >  1.96 and p_runs < 0.05)

    return {
        "lag1_autocorr": lag1_corr,
        "runs":          runs,
        "expected_runs": float(mu_r),
        "z_runs":        float(z_runs),
        "p_runs":        float(p_runs),
        "independent":   p_runs >= 0.05,
        "clustered":     clustered,
        "alternating":   alternating,
        "n_wins":        n_wins,
        "n_loss":        n_loss,
    }


# ── 6. Minimum edge / break-even WR ─────────────────────────────────────────────

def min_edge_analysis(pnls: np.ndarray) -> dict:
    """
    At current avg win/loss, what WR is needed for PF > 1.0?
    At what observed WR should trading stop?
    """
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    avg_win  = float(wins.mean())  if len(wins)   else 0.0
    avg_loss = float(-losses.mean()) if len(losses) else 0.0

    # PF > 1 requires: WR * avg_win > (1 - WR) * avg_loss
    # WR > avg_loss / (avg_win + avg_loss)
    if avg_win + avg_loss > 0:
        breakeven_wr = avg_loss / (avg_win + avg_loss)
    else:
        breakeven_wr = 0.5

    # Stop threshold: we want to be confident WR hasn't fallen below breakeven
    # Use 2-sigma safety margin: stop at breakeven + 1 std of observed WR
    # Observed WR standard error: sqrt(WR*(1-WR)/n)
    n = len(pnls)
    observed_wr = len(wins) / n
    wr_se = np.sqrt(observed_wr * (1 - observed_wr) / n)
    stop_wr = breakeven_wr + 2.0 * wr_se   # stop if WR degrades to this level

    # Win/loss ratio (RR)
    rr = avg_win / avg_loss if avg_loss > 0 else float("inf")

    # Expectancy
    expectancy = observed_wr * avg_win - (1.0 - observed_wr) * avg_loss

    # At current WR, how many consecutive losses wipe 5% of $25k account?
    account_size = 25_000.0
    pct_risk = 0.05
    max_tolerable_loss = account_size * pct_risk
    if avg_loss > 0:
        max_consecutive_losses = int(max_tolerable_loss / avg_loss)
    else:
        max_consecutive_losses = 0

    return {
        "avg_win":                 avg_win,
        "avg_loss":                avg_loss,
        "rr":                      rr,
        "observed_wr":             observed_wr,
        "breakeven_wr":            breakeven_wr,
        "stop_wr":                 stop_wr,
        "expectancy_per_trade":    expectancy,
        "max_consecutive_losses":  max_consecutive_losses,
    }


# ── Report formatting ────────────────────────────────────────────────────────────

def fmt_pct(x):  return f"{x*100:.1f}%"
def fmt_ci(lo, hi): return f"[{lo:.3g}, {hi:.3g}]"


def build_report(trades: List[Trade], obs: dict, boot: dict,
                 perm: dict, mc: dict, ac: dict, edge: dict) -> str:
    pnls = np.array([t.pnl for t in trades])
    lines = []
    W = lines.append

    W("=" * 80)
    W("  DEEP6 Zone Entry — Variant D Statistical Validity Analysis")
    W("  Wick=0.35  Close<=40%  TP=1:1  SL=distal+4t  Score>=6  10:00-15:00 ET")
    W("=" * 80)
    W("")

    # ── Section 1: Observed Results ────────────────────────────────────────────
    W("─" * 80)
    W("  1. OBSERVED RESULTS  (Variant D re-run)")
    W("─" * 80)
    W(f"  Trades:        {obs['n']}")
    W(f"  Win Rate:      {fmt_pct(obs['wr'])}")
    W(f"  Profit Factor: {obs['pf']:.2f}")
    W(f"  Sharpe Ratio:  {obs['sharpe']:.2f}  (annualised, per-trade)")
    W(f"  Net PnL:       ${obs['net']:>10,.2f}")
    W(f"  Max Drawdown:  ${obs['maxdd']:>10,.2f}")
    W("")

    # Individual trade listing
    W("  Trade sequence (chronological):")
    W(f"  {'#':>4}  {'Date':<12} {'Dir':<6} {'Zone':<8} {'Score':>5}  "
      f"{'Entry':>8}  {'Exit':>8}  {'Risk_t':>6}  {'Exit_R':<7}  {'PnL':>8}")
    W("  " + "─" * 76)
    for i, t in enumerate(trades, 1):
        W(f"  {i:>4}  {t.date:<12} {t.direction:<6} {t.zone_kind:<8} {t.zone_score:>5}  "
          f"{t.entry_px:>8.2f}  {t.exit_px:>8.2f}  {t.risk_ticks:>6.1f}  "
          f"{t.exit_reason:<7}  ${t.pnl:>7.2f}")
    W("")

    # ── Section 2: Bootstrap CIs ───────────────────────────────────────────────
    W("─" * 80)
    W(f"  2. BOOTSTRAP CONFIDENCE INTERVALS  ({N_BOOTSTRAP:,} resamples, 95% CI)")
    W("─" * 80)
    W("")

    wr_lo, wr_hi = boot["wr"]
    pf_lo, pf_hi = boot["pf"]
    sh_lo, sh_hi = boot["sharpe"]
    net_lo, net_hi = boot["net"]
    dd_lo, dd_hi = boot["maxdd"]

    W(f"  {'Metric':<20} {'Observed':>12}  {'95% CI Lower':>14}  {'95% CI Upper':>14}  {'Verdict'}")
    W("  " + "─" * 72)
    W(f"  {'Win Rate':<20} {fmt_pct(obs['wr']):>12}  {fmt_pct(wr_lo):>14}  {fmt_pct(wr_hi):>14}  "
      f"{'BEATS 50%' if wr_lo > 0.50 else 'CI TOUCHES <50%'}")
    W(f"  {'Profit Factor':<20} {obs['pf']:>12.2f}  {pf_lo:>14.2f}  {pf_hi:>14.2f}  "
      f"{'PF>1 even at lower' if pf_lo > 1.0 else 'PF<1 possible'}")
    W(f"  {'Sharpe Ratio':<20} {obs['sharpe']:>12.2f}  {sh_lo:>14.2f}  {sh_hi:>14.2f}  "
      f"{'Positive' if sh_lo > 0 else 'Could be zero'}")
    W(f"  {'Net PnL ($)':<20} ${obs['net']:>11,.0f}  ${net_lo:>13,.0f}  ${net_hi:>13,.0f}  "
      f"{'Profitable lower' if net_lo > 0 else 'Loss possible'}")
    W(f"  {'Max Drawdown ($)':<20} ${obs['maxdd']:>11,.0f}  ${dd_lo:>13,.0f}  ${dd_hi:>13,.0f}  "
      f"{'Manageable' if dd_hi < 5000 else 'DD can be significant'}")
    W("")
    W(f"  WR lower bound {fmt_pct(wr_lo)} vs 50% threshold: "
      f"{'PASSES — edge survives worst-case resampling' if wr_lo > 0.50 else 'WARN — lower bound touches or below 50%'}")
    W("")

    # ── Section 3: Permutation test ────────────────────────────────────────────
    W("─" * 80)
    W(f"  3. PERMUTATION TEST  ({N_PERMUTATION:,} iterations)")
    W("─" * 80)
    W("")
    W(f"  (a) Sign-flip test  (H0: mean PnL == 0, each trade equally likely +/-)")
    W(f"      Observed mean PnL/trade:   ${perm['observed_mean']:.2f}")
    W(f"      Null mean (sign-flip):     ${perm['perm_mean_mean']:.4f}  (should ~= 0)")
    W(f"      95th pct of null dist:     ${perm['perm_mean_p95']:.2f}")
    W(f"      p-value (one-tailed):      {perm['p_signflip']:.6f}")
    W("")
    W(f"  (b) Binomial test   (H0: WR == 50%)")
    W(f"      Wins: {perm['n_wins']} / {perm['n_trades']}  ({perm['n_wins']/perm['n_trades']*100:.1f}%)")
    W(f"      p-value (exact binomial):  {perm['p_binomial']:.2e}")
    W("")
    W(f"  (c) One-sample t-test (H0: mean PnL == 0)")
    W(f"      t-statistic:               {perm['t_stat']:.4f}")
    W(f"      p-value (one-tailed):      {perm['p_ttest']:.6f}")
    W("")
    W(f"  COMBINED:  Significant at p<0.01: {'YES' if perm['significant_001'] else 'NO'}")
    W(f"             Significant at p<0.05: {'YES' if perm['significant_005'] else 'NO'}")
    W("")
    if perm["significant_001"]:
        W("  VERDICT: Edge is statistically significant (p<0.01 on all three tests).")
        W("  Less than 1% chance that observed performance arose from zero-edge coin flips.")
    elif perm["significant_005"]:
        W("  VERDICT: Edge is significant at p<0.05.")
        W("  Treat with moderate confidence; more trades will tighten the estimate.")
    else:
        W("  VERDICT: One or more tests suggest edge is NOT significant.")
        W("  Observed performance could plausibly arise by chance.")
    W("")

    # ── Section 4: Monte Carlo forward sim ─────────────────────────────────────
    W("─" * 80)
    W(f"  4. MONTE CARLO FORWARD SIMULATION  ({N_MC_PATHS:,} paths, {MC_TRADES} trades = 12 months)")
    W("─" * 80)
    W("")
    W(f"  P(profitable at 12 months):   {mc['p_profitable']*100:.1f}%")
    W(f"  P(max drawdown > $5,000):     {mc['p_dd_5k']*100:.1f}%")
    W(f"  P(max drawdown > $10,000):    {mc['p_dd_10k']*100:.1f}%")
    W(f"  Expected net PnL (12 months): ${mc['expected_net']:>10,.0f}")
    W(f"  10th percentile net PnL:      ${mc['net_p10']:>10,.0f}")
    W(f"  90th percentile net PnL:      ${mc['net_p90']:>10,.0f}")
    W("")
    W("  Interpretation:")
    W(f"  - In {mc['p_profitable']*100:.0f}% of simulated futures, you finish 12 months profitable.")
    W(f"  - Worst-case 10th percentile: ${mc['net_p10']:,.0f}")
    W(f"  - In {mc['p_dd_10k']*100:.1f}% of paths, max DD exceeds $10k — size accordingly.")
    W("")

    # Distribution summary (approximate percentiles)
    fps = np.sort(mc["final_pnls"])
    W(f"  Net PnL distribution (12-month paths):")
    for pct in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        val = float(np.percentile(fps, pct))
        W(f"    P{pct:>2}: ${val:>10,.0f}")
    W("")

    # ── Section 5: Autocorrelation / runs test ─────────────────────────────────
    W("─" * 80)
    W("  5. AUTOCORRELATION / RUNS TEST")
    W("─" * 80)
    W("")
    W(f"  Total trades:         {ac['n_wins'] + ac['n_loss']}")
    W(f"  Wins:                 {ac['n_wins']}")
    W(f"  Losses:               {ac['n_loss']}")
    W(f"  Runs observed:        {ac['runs']}")
    W(f"  Runs expected (H0):   {ac['expected_runs']:.1f}")
    W(f"  Z-statistic (runs):   {ac['z_runs']:.4f}")
    W(f"  p-value (runs test):  {ac['p_runs']:.4f}")
    W(f"  Lag-1 autocorrelation of PnL: {ac['lag1_autocorr']:.4f}")
    W("")

    if ac["independent"]:
        W("  VERDICT: Trades appear INDEPENDENT (runs test p >= 0.05).")
        W("  Win/loss sequence shows no significant clustering or alternation.")
        W("  Bootstrap and Monte Carlo assumptions are valid.")
    elif ac["clustered"]:
        W("  VERDICT: Trades show CLUSTERING (fewer runs than expected).")
        W("  Wins and losses tend to come in streaks. Bootstrap CIs may be optimistic.")
        W("  Consider block-bootstrap or position sizing adjustments for streaks.")
    elif ac["alternating"]:
        W("  VERDICT: Trades show ALTERNATING pattern (more runs than expected).")
        W("  Wins and losses alternate more than chance predicts.")

    lag1 = ac["lag1_autocorr"]
    if abs(lag1) < 0.1:
        W(f"  Lag-1 autocorr {lag1:.3f} is near zero — consistent with independence.")
    elif lag1 > 0.1:
        W(f"  Lag-1 autocorr {lag1:.3f} > 0 — positive serial correlation (win follows win).")
    else:
        W(f"  Lag-1 autocorr {lag1:.3f} < 0 — negative serial correlation (loss follows win).")
    W("")

    # ── Section 6: Minimum edge analysis ──────────────────────────────────────
    W("─" * 80)
    W("  6. MINIMUM EDGE / BREAK-EVEN ANALYSIS")
    W("─" * 80)
    W("")
    W(f"  Average winning trade:  ${edge['avg_win']:>8,.2f}")
    W(f"  Average losing trade:   ${edge['avg_loss']:>8,.2f}")
    W(f"  Win/Loss ratio (RR):    {edge['rr']:.2f}x")
    W(f"  Observed WR:            {fmt_pct(edge['observed_wr'])}")
    W(f"  Break-even WR:          {fmt_pct(edge['breakeven_wr'])}")
    W(f"  Stop-trading WR:        {fmt_pct(edge['stop_wr'])}  (break-even + 2-sigma)")
    W(f"  Expectancy/trade:       ${edge['expectancy_per_trade']:>8,.2f}")
    W(f"  Max tolerable consec losses (5% of $25k): {edge['max_consecutive_losses']}")
    W("")
    margin = edge["observed_wr"] - edge["breakeven_wr"]
    W(f"  MARGIN ABOVE BREAK-EVEN: {fmt_pct(margin)}")
    W(f"  Current WR ({fmt_pct(edge['observed_wr'])}) is {fmt_pct(margin)} above break-even ({fmt_pct(edge['breakeven_wr'])}).")
    W(f"  WR can deteriorate by up to {fmt_pct(margin)} before system loses edge.")
    W(f"  Stop trading if rolling 30-trade WR drops below {fmt_pct(edge['stop_wr'])}.")
    W("")

    # ── Summary verdict ────────────────────────────────────────────────────────
    W("=" * 80)
    W("  OVERALL VERDICT")
    W("=" * 80)
    W("")

    # Scorecard
    checks = []
    # 1. WR CI lower > 50%
    checks.append(("WR CI lower > 50%",           wr_lo > 0.50))
    # 2. PF CI lower > 1.0
    checks.append(("PF CI lower > 1.0",           pf_lo > 1.0))
    # 3. Sharpe CI lower > 0
    checks.append(("Sharpe CI lower > 0",         sh_lo > 0))
    # 4. Net PnL CI lower > 0
    checks.append(("Net PnL CI lower > $0",       net_lo > 0))
    # 5. Permutation p < 0.01
    checks.append(("Permutation p < 0.01",        perm["significant_001"]))
    # 6. MC P(profitable) > 80%
    checks.append(("MC P(profit 12m) > 80%",      mc["p_profitable"] > 0.80))
    # 7. Trades independent (runs test)
    checks.append(("Trades independent",          ac["independent"]))
    # 8. Margin above break-even > 10%
    checks.append(("WR margin > 10% above b/e",   margin > 0.10))

    passed = sum(1 for _, v in checks)
    score  = sum(1 for _, v in checks if v)

    W(f"  Scorecard: {score}/{passed} checks passed")
    W("")
    for label, result in checks:
        marker = "PASS" if result else "FAIL"
        W(f"  [{marker}]  {label}")
    W("")

    if score >= 7:
        W("  CONCLUSION: STRONG EVIDENCE FOR REAL EDGE")
        W("  The statistical tests consistently support a genuine trading edge.")
        W("  The observed performance is very unlikely to be a product of overfitting")
        W("  given 101 trades over 16 months with independent signals.")
    elif score >= 5:
        W("  CONCLUSION: MODERATE EVIDENCE — PROCEED WITH CAUTION")
        W("  Most tests pass but some uncertainty remains. Trade at reduced size initially.")
        W("  Collect 50 more live trades before committing full allocation.")
    else:
        W("  CONCLUSION: INSUFFICIENT EVIDENCE — DO NOT TRADE LIVE")
        W("  Multiple statistical tests fail. The edge may be an artifact of parameter")
        W("  fitting or data snooping. Requires further investigation.")
    W("")

    # ── Honest forward expectation summary ────────────────────────────────────
    W("─" * 80)
    W("  HONEST FORWARD EXPECTATION (12 months)")
    W("─" * 80)
    W("")
    W(f"  Based on {N_MC_PATHS:,} Monte Carlo paths sampling the empirical PnL distribution:")
    W(f"  Expected trades/year:  {MC_TRADES} (~7/month)")
    W(f"  Most likely outcome:   ${np.percentile(mc['final_pnls'], 50):>8,.0f}  (median)")
    W(f"  Realistic range:       ${mc['net_p10']:,.0f} to ${mc['net_p90']:,.0f}  (10th-90th pct)")
    W(f"  Chance of profit:      {mc['p_profitable']*100:.0f}%")
    W(f"  Chance DD > $5k:       {mc['p_dd_5k']*100:.0f}%")
    W(f"  Chance DD > $10k:      {mc['p_dd_10k']*100:.0f}%")
    W("")
    W("  KEY CAVEATS:")
    W("  - 16-month backtest is substantial but not infinite; regime change possible")
    W("  - Zone detection uses price-only proxies (no actual order flow confirmation)")
    W("  - Walk-forward testing not yet performed — in-sample optimisation bias possible")
    W("  - Execution slippage assumed = 0; real fills at market open may differ")
    W("  - Commission $0.70/trade assumed; verify against your actual broker rate")
    W("")
    W("=" * 80)

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    import time
    t0 = time.time()

    print("=" * 60, flush=True)
    print("  DEEP6 Zone Entry — Statistical Validity Analysis", flush=True)
    print("=" * 60, flush=True)

    # ── Step 1: Load data and run Variant D ───────────────────────────────────
    print("\nLoading 1-year data...", flush=True)
    bars = load_bars(CSV_1YR)
    print(f"  {len(bars):,} 1m bars, {bars['session_date'].nunique()} sessions", flush=True)

    print("Resampling to 15m and detecting zones...", flush=True)
    bars_15m = resample_15m(bars)
    zones = detect_zones(bars_15m)
    print(f"  {len(bars_15m):,} 15m bars, {len(zones)} zones detected", flush=True)

    print("Running Variant D...", flush=True)
    px = compute_proxies(bars)
    n1 = len(bars)
    trades = run_variant(zones, px, n1,
                         VARIANT_D_SCORE_GATE,
                         VARIANT_D_TOD_START,
                         VARIANT_D_TOD_END)
    print(f"  {len(trades)} trades generated", flush=True)

    pnls = np.array([t.pnl for t in trades])
    obs  = compute_observed(pnls)
    print(f"  WR={obs['wr']*100:.1f}%  PF={obs['pf']:.2f}  "
          f"Sharpe={obs['sharpe']:.2f}  Net=${obs['net']:,.0f}", flush=True)

    # ── Step 2: Bootstrap ─────────────────────────────────────────────────────
    print(f"\nRunning bootstrap ({N_BOOTSTRAP:,} resamples)...", flush=True)
    boot = bootstrap_ci(pnls)
    print(f"  WR CI: [{boot['wr'][0]*100:.1f}%, {boot['wr'][1]*100:.1f}%]", flush=True)

    # ── Step 3: Permutation test ──────────────────────────────────────────────
    print(f"Running permutation/significance tests ({N_PERMUTATION:,} sign-flip iterations)...", flush=True)
    perm = permutation_test_sharpe(pnls)
    print(f"  sign-flip p={perm['p_signflip']:.2e}  binomial p={perm['p_binomial']:.2e}  t-test p={perm['p_ttest']:.2e}  "
          f"{'SIGNIFICANT p<0.01' if perm['significant_001'] else 'not significant at 0.01'}", flush=True)

    # ── Step 4: Monte Carlo ───────────────────────────────────────────────────
    print(f"Running Monte Carlo ({N_MC_PATHS:,} paths, {MC_TRADES} trades each)...", flush=True)
    mc = monte_carlo_forward(pnls)
    print(f"  P(profit): {mc['p_profitable']*100:.1f}%  "
          f"Expected net: ${mc['expected_net']:,.0f}", flush=True)

    # ── Step 5: Autocorrelation ───────────────────────────────────────────────
    print("Running autocorrelation / runs test...", flush=True)
    ac = autocorrelation_analysis(pnls)
    print(f"  Runs: {ac['runs']} (expected {ac['expected_runs']:.1f}), "
          f"p={ac['p_runs']:.4f}, lag-1={ac['lag1_autocorr']:.4f}", flush=True)

    # ── Step 6: Minimum edge ──────────────────────────────────────────────────
    edge = min_edge_analysis(pnls)

    # ── Build and save report ─────────────────────────────────────────────────
    print("\nBuilding report...", flush=True)
    report = build_report(trades, obs, boot, perm, mc, ac, edge)

    OUT_TXT.write_text(report, encoding="utf-8")
    print(f"\nSaved -> {OUT_TXT}", flush=True)

    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s", flush=True)

    # Print to stdout for immediate review
    print("\n" + report)


if __name__ == "__main__":
    main()
