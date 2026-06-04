#!/usr/bin/env python3
"""
DEEP6 Signal Attribution Engine
================================
Answers: which signals have edge, which work together, what is actual alpha.

For every bar in the 1yr NQ dataset:
  - Run all detectors
  - Record every signal that fires (id, direction, strength)
  - Measure forward P&L at 1, 2, 5, 10, 15, 30 bars
  - Aggregate: per-signal edge, signal pair co-occurrence, tier breakdowns

Output:
  scripts/results_attribution.txt   -- human-readable summary
  data/backtests/signal_events.csv  -- raw signal fire log for further analysis
  data/backtests/pair_cooccurrence.csv -- signal pair win rates

Run:
  python scripts/signal_attribution.py

Takes ~30-60s on the 1yr dataset.
"""
from __future__ import annotations

import time
import warnings
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── paths ────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_TXT  = ROOT / "scripts/results_attribution.txt"
OUT_EVENTS = ROOT / "data/backtests/signal_events.csv"
OUT_PAIRS  = ROOT / "data/backtests/pair_cooccurrence.csv"
OUT_CHART  = ROOT / "data/backtests/signal_edge_chart.png"

# ── constants ────────────────────────────────────────────────────────────────
TICK       = 0.25
TICK_VAL   = 5.0       # $5/tick for NQ
COMMISSION = 0.70      # per side (round-trip = 1.40)
DOLLARS_PER_POINT = 20.0

FORWARD_WINDOWS = [1, 2, 5, 10, 15, 30]  # bars ahead to measure P&L


def main() -> None:
    t0 = time.time()

    # ── import inside main so script fails clearly if deep6v2 not on path
    import sys
    sys.path.insert(0, str(ROOT))

    from deep6v2.backtest.ohlcv_synthesizer import synthesize_footprint
    from deep6v2.scoring.scorer import ConfluenceScorer
    from deep6v2.signals.registry import DetectorRegistry
    from deep6v2.types.bar import SessionType
    from deep6v2.types.signal import Direction, SignalCategory, SIGNAL_TO_CATEGORY
    from deep6v2.types.session import SessionContext

    print("Loading 1yr NQ data...", flush=True)
    df = pd.read_csv(
        CSV_PATH,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
    )
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"]    = df["ts_event"].dt.tz_convert("America/New_York")
    mins = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    df = df.loc[(mins >= 570) & (mins < 960)].copy()
    df["session_date"] = df["ts_et"].dt.date
    df = df.reset_index(drop=True)
    print(f"  {len(df):,} RTH bars, {df['session_date'].nunique()} sessions", flush=True)

    # ── pre-build forward price arrays (close of bar+N) for fast lookup
    closes = df["close"].to_numpy(dtype=float)
    highs  = df["high"].to_numpy(dtype=float)
    lows   = df["low"].to_numpy(dtype=float)
    opens  = df["open"].to_numpy(dtype=float)

    # ── per-session replay
    registry = DetectorRegistry.create_default()
    scorer   = ConfluenceScorer()

    # Raw signal fire log: one row per signal per bar
    event_rows: list[dict] = []

    # Pair co-occurrence tracker: (sig_a, sig_b) -> [forward_returns]
    pair_returns: dict[tuple[str, str], list[float]] = defaultdict(list)

    print("Running signal attribution across all sessions...", flush=True)
    session_groups = df.groupby("session_date", sort=True)
    n_sessions = df["session_date"].nunique()

    for sess_idx, (session_date, sess_df) in enumerate(session_groups):
        if sess_idx % 50 == 0:
            print(f"  Session {sess_idx+1}/{n_sessions}: {session_date}", flush=True)

        # Rebuild context fresh each session
        from collections import deque
        ctx = SessionContext(
            atr=0.0, cvd=0.0, vah=0.0, val=0.0, poc=0.0,
            session_type=SessionType.RTH, session_open_bar_index=0,
        )

        cvd_accum   = 0.0
        prev_close  = None
        true_ranges: deque[float] = deque(maxlen=14)
        first_bar   = True
        session_profile: dict[float, int] = {}

        global_indices = sess_df.index.tolist()

        for local_idx, (global_idx, row) in enumerate(zip(global_indices, sess_df.itertuples(index=False))):

            bar = synthesize_footprint(
                ts=row.ts_et.to_pydatetime(),
                open_=row.open, high=row.high, low=row.low, close=row.close,
                volume=int(row.volume), bar_index=local_idx, cvd_accum=cvd_accum,
            )
            cvd_accum = bar.cvd

            if first_bar:
                ctx.vah = bar.vah; ctx.val = bar.val; ctx.poc = bar.poc_price
                first_bar = False

            ctx.current_bar = bar
            ctx.cvd = bar.cvd

            # ATR
            if prev_close is None:
                tr = bar.high - bar.low
            else:
                tr = max(bar.high - bar.low,
                         abs(bar.high - prev_close),
                         abs(bar.low  - prev_close))
            true_ranges.append(tr)
            ctx.atr = sum(true_ranges) / len(true_ranges)

            # Append bar history
            ctx.bar_history.append(bar)
            ctx.price_history.append(bar.close)
            ctx.cvd_history.append(bar.cvd)
            ctx.delta_history.append(bar.delta)
            ctx.poc_history.append(bar.poc_price)
            ctx.vol_history.append(bar.total_volume)

            # Update session volume profile
            for price in set(bar.bid_volumes) | set(bar.ask_volumes):
                session_profile[price] = session_profile.get(price, 0) + \
                    bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)
            if session_profile:
                poc_p = max(session_profile, key=session_profile.get)
                ctx.poc = poc_p
                tgt = sum(session_profile.values()) * 0.70
                lvls = sorted(session_profile)
                incl = {poc_p}; run = session_profile[poc_p]
                ci = lvls.index(poc_p); li = ci - 1; ri = ci + 1
                while run < tgt and (li >= 0 or ri < len(lvls)):
                    lv = session_profile[lvls[li]] if li >= 0 else -1
                    rv = session_profile[lvls[ri]] if ri < len(lvls) else -1
                    if rv > lv:
                        incl.add(lvls[ri]); run += rv; ri += 1
                    else:
                        incl.add(lvls[li]); run += lv; li -= 1
                ctx.vah = max(incl); ctx.val = min(incl)

            prev_close = bar.close

            # Evaluate signals
            try:
                signals = registry.evaluate_bar(bar, ctx)
            except Exception:
                signals = []
            if not signals:
                continue

            # Score
            score = scorer.score(signals, local_idx)

            # Pre-compute forward returns at each window
            fwd_returns: dict[int, float] = {}
            for w in FORWARD_WINDOWS:
                fwd_idx = global_idx + w
                if fwd_idx < len(closes):
                    fwd_returns[w] = closes[fwd_idx] - bar.close
                else:
                    fwd_returns[w] = None  # type: ignore[assignment]

            # Determine net direction of bar (for signed P&L)
            # If signal direction is BULLISH: long → profit from price rise
            # If signal direction is BEARISH: short → profit from price fall

            # Collect unique signal IDs firing this bar
            fired_ids: list[str] = []
            for sig in signals:
                direction = sig.direction
                fwd_pnl_5 = None
                if 5 in fwd_returns and fwd_returns[5] is not None:
                    price_move = fwd_returns[5]  # close[t+5] - close[t]
                    if direction == Direction.BULLISH:
                        fwd_pnl_5 = price_move * DOLLARS_PER_POINT - COMMISSION
                    elif direction == Direction.BEARISH:
                        fwd_pnl_5 = -price_move * DOLLARS_PER_POINT - COMMISSION

                row_data = {
                    "session_date":   str(session_date),
                    "bar_ts":         str(bar.timestamp),
                    "bar_index":      local_idx,
                    "global_index":   global_idx,
                    "signal_id":      sig.signal_id.value,
                    "category":       (SIGNAL_TO_CATEGORY.get(sig.signal_id) or "other"),
                    "direction":      direction.value if direction else "neutral",
                    "strength":       round(sig.strength, 4),
                    "score_final":    round(score.final_score, 2),
                    "score_tier":     score.tier.value,
                    "bar_close":      bar.close,
                    "bar_delta":      bar.delta,
                }
                # Forward P&L columns (signed by signal direction)
                for w in FORWARD_WINDOWS:
                    if w in fwd_returns and fwd_returns[w] is not None:
                        price_move = fwd_returns[w]
                        if direction == Direction.BULLISH:
                            signed_pnl = price_move * DOLLARS_PER_POINT - COMMISSION
                        elif direction == Direction.BEARISH:
                            signed_pnl = -price_move * DOLLARS_PER_POINT - COMMISSION
                        else:
                            signed_pnl = 0.0
                        row_data[f"fwd_pnl_{w}b"] = round(signed_pnl, 2)
                    else:
                        row_data[f"fwd_pnl_{w}b"] = None

                event_rows.append(row_data)
                fired_ids.append(sig.signal_id.value)

            # Pair co-occurrence: track every unique pair that fires same bar, same direction
            direction_groups: dict[str, list[str]] = defaultdict(list)
            for sig in signals:
                d = sig.direction.value if sig.direction else "neutral"
                direction_groups[d].append(sig.signal_id.value)

            for d, ids in direction_groups.items():
                if len(ids) < 2:
                    continue
                for a, b in combinations(sorted(set(ids)), 2):
                    # 5-bar forward P&L
                    fwd = fwd_returns.get(5)
                    if fwd is None:
                        continue
                    if d == "BULLISH":
                        pnl = fwd * DOLLARS_PER_POINT - COMMISSION
                    elif d == "BEARISH":
                        pnl = -fwd * DOLLARS_PER_POINT - COMMISSION
                    else:
                        pnl = 0.0
                    pair_returns[(a, b)].append(pnl)

    # ── Build DataFrames ──────────────────────────────────────────────────────
    print(f"\nTotal signal fires: {len(event_rows):,}", flush=True)

    if not event_rows:
        print("No signals fired — check detector setup.")
        return

    events = pd.DataFrame(event_rows)
    events.to_csv(OUT_EVENTS, index=False)
    print(f"Signal events saved to {OUT_EVENTS.name}", flush=True)

    # ── Per-signal statistics ─────────────────────────────────────────────────
    lines: list[str] = []
    W = lines.append

    W("=" * 100)
    W("  DEEP6 SIGNAL ATTRIBUTION ENGINE — NQ 1yr (Jan 2025 → Apr 2026)")
    W(f"  {events['session_date'].nunique()} sessions  |  {len(events):,} signal fires  |  "
      f"{events['signal_id'].nunique()} unique signal IDs")
    W("=" * 100)
    W("")

    # Per-signal edge table (using 5-bar forward as primary)
    pnl_col = "fwd_pnl_5b"
    valid = events.dropna(subset=[pnl_col])

    sig_stats: list[dict] = []
    for sig_id, grp in valid.groupby("signal_id"):
        pnls = grp[pnl_col].values
        n = len(pnls)
        if n < 5:
            continue
        wins = (pnls > 0).sum()
        losses = (pnls <= 0).sum()
        gross_win = pnls[pnls > 0].sum() if wins else 0.0
        gross_loss = -pnls[pnls <= 0].sum() if losses else 1e-9
        pf = gross_win / gross_loss if gross_loss > 0 else 999.0
        wr = wins / n
        avg = pnls.mean()
        std = pnls.std(ddof=1) if n > 1 else 0.0
        sharpe = (avg / std * np.sqrt(252 * 6.5)) if std > 0 else 0.0  # annualize by signals/hr * 6.5hr
        category = grp["category"].iloc[0]
        avg_strength = grp["strength"].mean()
        sig_stats.append(dict(
            signal_id=sig_id, category=category, n=n,
            win_rate=wr, profit_factor=pf, avg_pnl=avg, sharpe=sharpe,
            net=pnls.sum(), avg_strength=avg_strength,
        ))

    sig_df = pd.DataFrame(sig_stats).sort_values("profit_factor", ascending=False)

    W("─" * 100)
    W("  PER-SIGNAL EDGE TABLE  (primary: 5-bar forward P&L per signal fire)")
    W("─" * 100)
    W(f"  {'Signal':<12} {'Category':<16} {'N':>6} {'WR%':>6} {'PF':>6} {'Avg$':>7} "
      f"{'Net$':>9} {'Sharpe':>7} {'Str':>5}")
    W("  " + "─" * 80)

    for _, row in sig_df.iterrows():
        tag = " ◆" if row.profit_factor >= 1.5 and row.n >= 20 else \
              " ●" if row.profit_factor >= 1.2 and row.n >= 10 else ""
        W(f"  {row.signal_id:<12} {str(row.category):<16} {row.n:>6} "
          f"{row.win_rate*100:>5.1f}% {row.profit_factor:>6.2f} {row.avg_pnl:>7.1f} "
          f"{row.net:>9,.0f} {row.sharpe:>7.2f} {row.avg_strength:>5.2f}{tag}")

    W("")
    W("  ◆ = PF≥1.5, N≥20 (strong edge)   ● = PF≥1.2, N≥10 (moderate edge)")
    W("")

    # ── Category-level summary ─────────────────────────────────────────────────
    W("─" * 100)
    W("  CATEGORY SUMMARY")
    W("─" * 100)
    W(f"  {'Category':<18} {'Signals':>8} {'Fires':>8} {'WR%':>6} {'PF':>6} {'Net$':>10}")
    W("  " + "─" * 65)
    for cat, grp in valid.groupby("category"):
        pnls = grp[pnl_col].values
        n = len(pnls)
        wins = (pnls > 0).sum()
        gl = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        gw = pnls[pnls > 0].sum() if (pnls > 0).any() else 0.0
        pf = gw / gl
        n_sigs = grp["signal_id"].nunique()
        W(f"  {str(cat):<18} {n_sigs:>8} {n:>8} {wins/n*100:>5.1f}% {pf:>6.2f} {pnls.sum():>10,.0f}")
    W("")

    # ── Forward window analysis for top signals ────────────────────────────────
    strong_sigs = sig_df[sig_df["profit_factor"] >= 1.4]["signal_id"].tolist()
    if strong_sigs:
        W("─" * 100)
        W("  FORWARD WINDOW DECAY  (top signals by PF≥1.4 — avg P&L by lookahead window)")
        W("─" * 100)
        W(f"  {'Signal':<12} " + "".join(f"  {w}b" for w in FORWARD_WINDOWS))
        W("  " + "─" * 70)
        top_events = valid[valid["signal_id"].isin(strong_sigs)]
        for sig_id in strong_sigs[:20]:
            grp = top_events[top_events["signal_id"] == sig_id]
            vals = []
            for w in FORWARD_WINDOWS:
                col = f"fwd_pnl_{w}b"
                sub = grp[col].dropna()
                vals.append(f"{sub.mean():>6.1f}" if len(sub) else "   N/A")
            W(f"  {sig_id:<12} " + "  ".join(vals))
        W("")

    # ── Signal pair co-occurrence ──────────────────────────────────────────────
    W("─" * 100)
    W("  TOP SIGNAL PAIRS BY PROFIT FACTOR  (same bar, same direction, 5b forward)")
    W("─" * 100)
    pair_stats = []
    for (a, b), pnls_list in pair_returns.items():
        pnls = np.array(pnls_list)
        n = len(pnls)
        if n < 5:
            continue
        wins = (pnls > 0).sum()
        gl = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        gw = pnls[pnls > 0].sum() if (pnls > 0).any() else 0.0
        pf = gw / gl
        pair_stats.append(dict(pair=f"{a} + {b}", n=n, wr=wins/n, pf=pf,
                               net=pnls.sum(), avg=pnls.mean()))

    pair_df = pd.DataFrame(pair_stats).sort_values("profit_factor", ascending=False)
    if not pair_df.empty:
        pair_df.to_csv(OUT_PAIRS, index=False)
        W(f"  {'Signal Pair':<30} {'N':>6} {'WR%':>6} {'PF':>6} {'Avg$':>7} {'Net$':>10}")
        W("  " + "─" * 70)
        for _, row in pair_df.head(30).iterrows():
            W(f"  {row['pair']:<30} {row.n:>6} {row.wr*100:>5.1f}% {row.pf:>6.2f} "
              f"{row.avg:>7.1f} {row.net:>10,.0f}")
    W("")

    # ── Score tier breakdown ──────────────────────────────────────────────────
    W("─" * 100)
    W("  SCORE TIER BREAKDOWN  (what happens when multiple signals fire together)")
    W("─" * 100)
    tier_events = valid.drop_duplicates(subset=["session_date", "bar_ts", "score_tier"])
    W(f"  {'Tier':<12} {'Bars':>6} {'WR%':>6} {'PF':>6} {'Net$':>10}")
    W("  " + "─" * 45)
    for tier, grp in tier_events.groupby("score_tier"):
        pnls = grp[pnl_col].values
        n = len(pnls)
        wins = (pnls > 0).sum()
        gl = -pnls[pnls <= 0].sum() if (pnls <= 0).any() else 1e-9
        gw = pnls[pnls > 0].sum() if (pnls > 0).any() else 0.0
        pf = gw / gl if gl > 0 else 999.0
        W(f"  {str(tier):<12} {n:>6} {wins/n*100:>5.1f}% {pf:>6.2f} {pnls.sum():>10,.0f}")
    W("")

    # ── Time-of-day analysis for top signals ──────────────────────────────────
    W("─" * 100)
    W("  TIME-OF-DAY BREAKDOWN  (best performing signals by hour)")
    W("─" * 100)
    if "bar_ts" in valid.columns:
        valid2 = valid.copy()
        valid2["hour"] = pd.to_datetime(valid2["bar_ts"]).dt.hour
        top5 = sig_df.head(5)["signal_id"].tolist()
        top_v = valid2[valid2["signal_id"].isin(top5)]
        W(f"  {'Signal':<12} " + "".join(f"  {h:02d}h" for h in range(9, 16)))
        W("  " + "─" * 70)
        for sig_id in top5:
            grp = top_v[top_v["signal_id"] == sig_id]
            vals = []
            for h in range(9, 16):
                sub = grp[grp["hour"] == h][pnl_col].dropna()
                if len(sub) >= 3:
                    vals.append(f"{sub.mean():>5.0f}")
                else:
                    vals.append("    -")
            W(f"  {sig_id:<12}  " + "   ".join(vals))
    W("")

    # ── Bottom summary ─────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    W("=" * 100)
    alpha_count = len(sig_df[sig_df["profit_factor"] >= 1.4])
    noise_count  = len(sig_df[sig_df["profit_factor"] < 1.0])
    W(f"  Signals with real edge (PF≥1.4):  {alpha_count}/{len(sig_df)}")
    W(f"  Signals with no edge  (PF<1.0):   {noise_count}/{len(sig_df)}")
    W(f"  Completed in {elapsed:.1f}s")
    W("=" * 100)

    result_text = "\n".join(lines)
    OUT_TXT.write_text(result_text, encoding="utf-8")
    for line in lines:
        print(line)

    # ── Equity curve for top-10 signals ──────────────────────────────────────
    _save_chart(valid, sig_df, pnl_col)
    print(f"\nSaved → {OUT_TXT.name}")
    print(f"Saved → {OUT_EVENTS.name}")
    print(f"Saved → {OUT_PAIRS.name}")
    print(f"Saved → {OUT_CHART.name}")


def _save_chart(events: pd.DataFrame, sig_df: pd.DataFrame, pnl_col: str) -> None:
    top_sigs = sig_df.head(10)["signal_id"].tolist()
    fig, axes = plt.subplots(2, 5, figsize=(20, 8))
    axes = axes.flatten()
    for i, sig_id in enumerate(top_sigs):
        grp = events[events["signal_id"] == sig_id][pnl_col].dropna()
        eq = np.cumsum(grp.values)
        ax = axes[i]
        ax.plot(eq, linewidth=1.2, color="#2196F3")
        ax.axhline(0, color="#888", linewidth=0.6, linestyle="--")
        row = sig_df[sig_df["signal_id"] == sig_id].iloc[0]
        ax.set_title(
            f"{sig_id}\nN={row.n}  PF={row.profit_factor:.2f}  WR={row.win_rate*100:.0f}%",
            fontsize=8,
        )
        ax.set_ylabel("Cum $", fontsize=7)
        ax.tick_params(labelsize=6)
    plt.suptitle("DEEP6 Signal Attribution — Top 10 by Profit Factor (5b forward)", fontsize=11)
    plt.tight_layout()
    plt.savefig(OUT_CHART, dpi=120, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
