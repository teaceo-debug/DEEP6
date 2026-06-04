#!/usr/bin/env python3
"""
DEEP6 Signal Analyzer — Phase 2 of attribution pipeline.

Reads signal_events.csv (from signal_collect.py) and produces:
  - Per-signal edge table (PF, WR, Sharpe, net P&L at multiple windows)
  - Category summary
  - Signal pair co-occurrence (top pairs)
  - Time-of-day breakdown
  - Score tier breakdown
  - Forward-window decay curves
  - Equity curves for top signals

Usage:
  python scripts/signal_analyze.py [--window 5] [--min-pf 1.0] [--min-n 10]
  python scripts/signal_analyze.py --category absorption
  python scripts/signal_analyze.py --signal ABS_01,EXH_01,IMB_03

All combinations are fast (pandas vectorized, seconds not minutes).
"""
from __future__ import annotations

import argparse
import time
import warnings
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT      = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OUT_DIR    = ROOT / "data/backtests/analysis"

TICK_VAL   = 5.0        # $5 per tick
COMMISSION = 0.70       # per side
DPP        = 20.0       # dollars per point (NQ)
FORWARD_WINDOWS = [1, 2, 5, 10, 15, 30]


def load_events(category: str | None = None, signals: list[str] | None = None) -> pd.DataFrame:
    print(f"Loading {EVENTS_CSV.name}...", flush=True)
    ev = pd.read_csv(EVENTS_CSV, low_memory=False)
    print(f"  {len(ev):,} raw signal fires", flush=True)

    # Compute signed P&L columns from raw forward closes
    for w in FORWARD_WINDOWS:
        fc = pd.to_numeric(ev[f"fwd_close_{w}b"], errors="coerce")
        price_move = fc - ev["bar_close"].astype(float)
        pnl = price_move * DPP
        # Apply sign by direction: BULLISH=+1, BEARISH=-1, neutral=0
        dirs = ev["direction"].map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1}).fillna(0)
        ev[f"pnl_{w}b"] = (dirs * pnl - COMMISSION).where(dirs != 0, 0.0)

    ev["bar_ts"] = pd.to_datetime(ev["bar_ts"], utc=True, errors="coerce")
    ev["hour"]   = ev["bar_ts"].dt.tz_convert("America/New_York").dt.hour

    if category:
        ev = ev[ev["category"] == category]
        print(f"  Filtered to category={category}: {len(ev):,} fires", flush=True)
    if signals:
        ev = ev[ev["signal_id"].isin(signals)]
        print(f"  Filtered to signals={signals}: {len(ev):,} fires", flush=True)

    return ev.dropna(subset=["pnl_5b"])


def signal_stats(ev: pd.DataFrame, pnl_col: str = "pnl_5b", min_n: int = 5) -> pd.DataFrame:
    rows = []
    for sig_id, grp in ev.groupby("signal_id"):
        pnls = grp[pnl_col].values
        n = len(pnls)
        if n < min_n:
            continue
        wins = (pnls > 0).sum()
        gw   = pnls[pnls > 0].sum() if wins else 0.0
        gl   = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        rows.append(dict(
            signal_id    = sig_id,
            category     = grp["category"].iloc[0],
            n            = n,
            win_rate     = wins / n,
            profit_factor= gw / gl if gl > 0 else 999.0,
            avg_pnl      = pnls.mean(),
            net_pnl      = pnls.sum(),
            sharpe       = (pnls.mean() / pnls.std(ddof=1) * np.sqrt(252 * 40)) if pnls.std() > 0 else 0.0,
            avg_strength = grp["strength"].mean(),
        ))
    return pd.DataFrame(rows).sort_values("profit_factor", ascending=False)


def format_table(df: pd.DataFrame, sig_df: pd.DataFrame | None = None) -> list[str]:
    lines = []
    W = lines.append
    W(f"  {'Signal':<12} {'Category':<16} {'N':>6} {'WR%':>6} {'PF':>6} "
      f"{'Avg$':>7} {'Net$':>10} {'Sharpe':>7}")
    W("  " + "─" * 75)
    for _, r in df.iterrows():
        tag = " ◆" if r.profit_factor >= 1.5 and r.n >= 20 else \
              " ●" if r.profit_factor >= 1.2 and r.n >= 10 else ""
        W(f"  {r.signal_id:<12} {str(r.category):<16} {r.n:>6} "
          f"{r.win_rate*100:>5.1f}% {r.profit_factor:>6.2f} {r.avg_pnl:>7.1f} "
          f"{r.net_pnl:>10,.0f} {r.sharpe:>7.2f}{tag}")
    return lines


def forward_decay(ev: pd.DataFrame, signal_ids: list[str]) -> list[str]:
    lines = []
    lines.append(f"  {'Signal':<12} " + "  ".join(f"{w:>6}b" for w in FORWARD_WINDOWS))
    lines.append("  " + "─" * 70)
    for sig_id in signal_ids:
        grp = ev[ev["signal_id"] == sig_id]
        vals = []
        for w in FORWARD_WINDOWS:
            col  = f"pnl_{w}b"
            sub  = grp[col].dropna()
            vals.append(f"{sub.mean():>6.1f}" if len(sub) >= 5 else "     -")
        lines.append(f"  {sig_id:<12}  " + "  ".join(vals))
    return lines


def pair_table(ev: pd.DataFrame, min_n: int = 10) -> list[str]:
    lines = []
    pair_rows = []
    # Group by bar: collect signal IDs + direction per bar
    bar_groups = ev.groupby(["session_date", "bar_index", "direction"])
    for (sess, bidx, d), grp in bar_groups:
        ids = sorted(grp["signal_id"].unique().tolist())
        if len(ids) < 2:
            continue
        pnl = grp["pnl_5b"].mean()
        for a, b in combinations(ids, 2):
            pair_rows.append({"pair": f"{a}+{b}", "pnl": pnl, "direction": d})

    if not pair_rows:
        return ["  No pairs found"]
    pdf = pd.DataFrame(pair_rows)
    stats = []
    for pair, grp in pdf.groupby("pair"):
        pnls = grp["pnl"].values
        n = len(pnls)
        if n < min_n:
            continue
        wins = (pnls > 0).sum()
        gw = pnls[pnls > 0].sum() if wins else 0.0
        gl = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        stats.append(dict(pair=pair, n=n, wr=wins/n, pf=gw/gl, avg=pnls.mean(), net=pnls.sum()))

    sdf = pd.DataFrame(stats).sort_values("pf", ascending=False)
    lines.append(f"  {'Pair':<28} {'N':>6} {'WR%':>6} {'PF':>6} {'Avg$':>7} {'Net$':>10}")
    lines.append("  " + "─" * 72)
    for _, r in sdf.head(30).iterrows():
        lines.append(f"  {r['pair']:<28} {r.n:>6} {r.wr*100:>5.1f}% {r.pf:>6.2f} "
                     f"{r.avg:>7.1f} {r.net:>10,.0f}")
    return lines


def time_of_day_table(ev: pd.DataFrame, signal_ids: list[str]) -> list[str]:
    lines = []
    hours = list(range(9, 16))
    lines.append(f"  {'Signal':<12} " + "".join(f"  {h:02d}h" for h in hours))
    lines.append("  " + "─" * 65)
    for sig_id in signal_ids:
        grp = ev[ev["signal_id"] == sig_id]
        vals = []
        for h in hours:
            sub = grp[grp["hour"] == h]["pnl_5b"].dropna()
            vals.append(f"{sub.mean():>5.0f}" if len(sub) >= 3 else "    -")
        lines.append(f"  {sig_id:<12}  " + "  ".join(vals))
    return lines


def save_equity_charts(ev: pd.DataFrame, sig_df: pd.DataFrame, out_dir: Path) -> None:
    top = sig_df.head(12)["signal_id"].tolist()
    n_cols = 4
    n_rows = (len(top) + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(20, 4 * n_rows))
    axes = axes.flatten()
    for i, sig_id in enumerate(top):
        grp   = ev[ev["signal_id"] == sig_id]["pnl_5b"].dropna()
        eq    = np.cumsum(grp.values)
        ax    = axes[i]
        ax.plot(eq, linewidth=1.2, color="#2196F3")
        ax.fill_between(range(len(eq)), eq, alpha=0.07, color="#2196F3")
        ax.axhline(0, color="#888", linewidth=0.7, linestyle="--")
        r = sig_df[sig_df["signal_id"] == sig_id].iloc[0]
        ax.set_title(f"{sig_id}  PF={r.profit_factor:.2f}  WR={r.win_rate*100:.0f}%  N={r.n}",
                     fontsize=9)
        ax.set_ylabel("Cum $", fontsize=7)
        ax.tick_params(labelsize=6)
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)
    plt.suptitle("DEEP6 Signal Attribution — Equity Curves (5-bar forward P&L)", fontsize=12)
    plt.tight_layout()
    path = out_dir / "signal_equity_curves.png"
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Saved → {path.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window",   type=int, default=5,   help="Primary forward window (bars)")
    ap.add_argument("--min-pf",   type=float, default=1.0, help="Min PF to show in tables")
    ap.add_argument("--min-n",    type=int, default=10,  help="Min fires to include signal")
    ap.add_argument("--category", type=str, default=None)
    ap.add_argument("--signal",   type=str, default=None, help="Comma-separated signal IDs")
    ap.add_argument("--no-pairs", action="store_true",   help="Skip pair co-occurrence (slow)")
    args = ap.parse_args()

    signals_filter = [s.strip() for s in args.signal.split(",")] if args.signal else None

    t0 = time.time()
    ev = load_events(category=args.category, signals=signals_filter)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pnl_col = f"pnl_{args.window}b"
    sig_df  = signal_stats(ev, pnl_col=pnl_col, min_n=args.min_n)
    top_ids = sig_df[sig_df["profit_factor"] >= args.min_pf]["signal_id"].tolist()

    lines: list[str] = []
    W = lines.append

    W("=" * 90)
    W("  DEEP6 SIGNAL ATTRIBUTION")
    W(f"  {ev['session_date'].nunique()} sessions  |  {len(ev):,} fires  |  "
      f"primary window: {args.window}b")
    W("=" * 90)
    W("")

    # ── Per-signal ─────────────────────────────────────────────────────────
    W("─" * 90)
    W("  PER-SIGNAL EDGE TABLE")
    W("─" * 90)
    lines.extend(format_table(sig_df[sig_df["profit_factor"] >= args.min_pf]))
    W("")
    W("  ◆ = PF≥1.5, N≥20  ● = PF≥1.2, N≥10")
    W("")

    # ── Category summary ────────────────────────────────────────────────────
    W("─" * 90)
    W("  CATEGORY SUMMARY")
    W("─" * 90)
    W(f"  {'Category':<18} {'Signals':>7} {'Fires':>8} {'WR%':>6} {'PF':>6} {'Net$':>10}")
    W("  " + "─" * 60)
    valid = ev.dropna(subset=[pnl_col])
    for cat, grp in valid.groupby("category"):
        pnls = grp[pnl_col].values
        n    = len(pnls)
        wins = (pnls > 0).sum()
        gw   = pnls[pnls > 0].sum() if wins else 0.0
        gl   = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        W(f"  {str(cat):<18} {grp['signal_id'].nunique():>7} {n:>8} "
          f"{wins/n*100:>5.1f}% {gw/gl:>6.2f} {pnls.sum():>10,.0f}")
    W("")

    # ── Forward-window decay ────────────────────────────────────────────────
    strong = [s for s in top_ids if sig_df[sig_df["signal_id"] == s]["profit_factor"].iloc[0] >= 1.3]
    if strong:
        W("─" * 90)
        W("  FORWARD WINDOW DECAY  (avg $ per fire at 1/2/5/10/15/30 bars ahead)")
        W("─" * 90)
        lines.extend(forward_decay(valid, strong[:15]))
        W("")

    # ── Score tier ──────────────────────────────────────────────────────────
    W("─" * 90)
    W("  SCORE TIER BREAKDOWN")
    W("─" * 90)
    W(f"  {'Tier':<14} {'Bars':>7} {'WR%':>6} {'PF':>6} {'Net$':>10}")
    W("  " + "─" * 45)
    tier_ev = valid.drop_duplicates(subset=["session_date", "bar_index", "score_tier"])
    for tier, grp in tier_ev.groupby("score_tier"):
        pnls = grp[pnl_col].values; n = len(pnls); wins = (pnls > 0).sum()
        gw = pnls[pnls > 0].sum() if wins else 0.0
        gl = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        W(f"  {str(tier):<14} {n:>7} {wins/n*100:>5.1f}% {gw/gl:>6.2f} {pnls.sum():>10,.0f}")
    W("")

    # ── Time of day ─────────────────────────────────────────────────────────
    if strong:
        W("─" * 90)
        W("  TIME-OF-DAY  (avg $ per fire by ET hour, top signals)")
        W("─" * 90)
        lines.extend(time_of_day_table(valid, strong[:8]))
        W("")

    # ── Pairs ───────────────────────────────────────────────────────────────
    if not args.no_pairs:
        W("─" * 90)
        W("  TOP SIGNAL PAIRS  (same bar, same direction, 5b forward)")
        W("─" * 90)
        lines.extend(pair_table(valid, min_n=10))
        W("")

    # ── Bottom ──────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    alpha_n = len(sig_df[sig_df["profit_factor"] >= 1.4])
    noise_n = len(sig_df[sig_df["profit_factor"] < 1.0])
    W("=" * 90)
    W(f"  Real edge (PF≥1.4): {alpha_n}/{len(sig_df)}  |  "
      f"Noise (PF<1.0): {noise_n}/{len(sig_df)}  |  "
      f"Done in {elapsed:.1f}s")
    W("=" * 90)

    # Save text
    out_txt = OUT_DIR / f"attribution_{args.window}b.txt"
    out_txt.write_text("\n".join(lines), encoding="utf-8")

    # Save CSVs
    sig_df.to_csv(OUT_DIR / "signal_stats.csv", index=False)

    print("\n".join(lines))
    print(f"\nSaved → {out_txt}")

    # Charts
    save_equity_charts(valid, sig_df, OUT_DIR)


if __name__ == "__main__":
    main()
