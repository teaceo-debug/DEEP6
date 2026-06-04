#!/usr/bin/env python3
"""
DEEP6 Signal Collector — Phase 1 of attribution pipeline.

Runs all detectors on the full 1yr dataset and saves raw signal events
to a CSV. Fast (~3 min). Designed to be run once; analysis runs separately.

Output: data/backtests/signal_events.csv
  Columns: session_date, bar_ts, bar_index, global_index, signal_id,
           category, direction, strength, score_final, score_tier,
           bar_open, bar_high, bar_low, bar_close, bar_delta, bar_volume,
           fwd_close_1b .. fwd_close_30b  (raw closes, not P&L)

Run:
  python scripts/signal_collect.py
"""
from __future__ import annotations

import sys
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT     = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_CSV  = ROOT / "data/backtests/signal_events.csv"

FORWARD_WINDOWS = [1, 2, 5, 10, 15, 30]


def main() -> None:
    sys.path.insert(0, str(ROOT))

    from deep6v2.backtest.ohlcv_synthesizer import synthesize_footprint
    from deep6v2.scoring.scorer import ConfluenceScorer
    from deep6v2.signals.registry import DetectorRegistry
    from deep6v2.types.bar import SessionType
    from deep6v2.types.signal import SIGNAL_TO_CATEGORY
    from deep6v2.types.session import SessionContext

    print("Loading data...", flush=True)
    df = pd.read_csv(
        CSV_PATH,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
    )
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"]    = df["ts_event"].dt.tz_convert("America/New_York")
    mins = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    df   = df.loc[(mins >= 570) & (mins < 960)].reset_index(drop=True)
    df["session_date"] = df["ts_et"].dt.date
    print(f"  {len(df):,} RTH bars across {df['session_date'].nunique()} sessions", flush=True)

    # Pre-extract numpy arrays for O(1) forward-close lookups
    closes  = df["close"].to_numpy(dtype=np.float64)
    n_total = len(closes)

    registry = DetectorRegistry.create_default()
    scorer   = ConfluenceScorer()

    # Write CSV header
    fwd_cols = [f"fwd_close_{w}b" for w in FORWARD_WINDOWS]
    header = [
        "session_date", "bar_ts", "bar_index", "global_index",
        "signal_id", "category", "direction", "strength",
        "score_final", "score_tier",
        "bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume",
    ] + fwd_cols
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    total_fires = 0
    batch: list[list] = []
    FLUSH_EVERY = 50_000

    with OUT_CSV.open("w", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")

        for sess_date, sess_df in df.groupby("session_date", sort=True):
            ctx = SessionContext(
                atr=0.0, cvd=0.0, vah=0.0, val=0.0, poc=0.0,
                session_type=SessionType.RTH, session_open_bar_index=0,
            )
            cvd_accum  = 0.0
            prev_close = None
            true_ranges: deque[float] = deque(maxlen=14)
            first_bar  = True
            sp: dict[float, int] = {}
            global_indices = sess_df.index.tolist()

            for local_idx, (gidx, row) in enumerate(zip(global_indices, sess_df.itertuples(index=False))):
                bar = synthesize_footprint(
                    ts=row.ts_et.to_pydatetime(),
                    open_=row.open, high=row.high, low=row.low, close=row.close,
                    volume=int(row.volume), bar_index=local_idx, cvd_accum=cvd_accum,
                )
                cvd_accum = bar.cvd

                if first_bar:
                    ctx.vah = bar.vah; ctx.val = bar.val; ctx.poc = bar.poc_price
                    first_bar = False

                ctx.current_bar = bar; ctx.cvd = bar.cvd
                tr = bar.high - bar.low if prev_close is None else \
                    max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
                true_ranges.append(tr)
                ctx.atr = sum(true_ranges) / len(true_ranges)
                ctx.bar_history.append(bar)
                ctx.price_history.append(bar.close)
                ctx.cvd_history.append(bar.cvd)
                ctx.delta_history.append(bar.delta)
                ctx.poc_history.append(bar.poc_price)
                ctx.vol_history.append(bar.total_volume)

                # Session volume profile → update POC/VAH/VAL
                for price in set(bar.bid_volumes) | set(bar.ask_volumes):
                    sp[price] = sp.get(price, 0) + bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)
                if sp:
                    poc_p  = max(sp, key=sp.get)
                    tgt    = sum(sp.values()) * 0.70
                    lvls   = sorted(sp); ci = lvls.index(poc_p)
                    incl   = {poc_p}; run = sp[poc_p]; li = ci - 1; ri = ci + 1
                    while run < tgt and (li >= 0 or ri < len(lvls)):
                        lv = sp[lvls[li]] if li >= 0 else -1
                        rv = sp[lvls[ri]] if ri < len(lvls) else -1
                        if rv > lv: incl.add(lvls[ri]); run += rv; ri += 1
                        else:       incl.add(lvls[li]); run += lv; li -= 1
                    ctx.poc = poc_p; ctx.vah = max(incl); ctx.val = min(incl)

                prev_close = bar.close

                try:
                    signals = registry.evaluate_bar(bar, ctx)
                except Exception:
                    signals = []
                if not signals:
                    continue

                score = scorer.score(signals, local_idx)

                # Forward close values (raw, not P&L — analysis script handles that)
                fwd_closes = []
                for w in FORWARD_WINDOWS:
                    fi = gidx + w
                    fwd_closes.append(f"{closes[fi]:.2f}" if fi < n_total else "")

                for sig in signals:
                    cat = SIGNAL_TO_CATEGORY.get(sig.signal_id)
                    row_out = [
                        str(sess_date),
                        str(bar.timestamp),
                        local_idx,
                        gidx,
                        sig.signal_id.value,
                        cat.value if cat else "other",
                        sig.direction.value if sig.direction else "neutral",
                        f"{sig.strength:.4f}",
                        f"{score.final_score:.2f}",
                        score.tier.value,
                        f"{bar.open:.2f}",
                        f"{bar.high:.2f}",
                        f"{bar.low:.2f}",
                        f"{bar.close:.2f}",
                        bar.delta,
                        bar.total_volume,
                    ] + fwd_closes
                    batch.append(row_out)
                    total_fires += 1

                # Flush in batches
                if len(batch) >= FLUSH_EVERY:
                    f.writelines(",".join(str(x) for x in r) + "\n" for r in batch)
                    f.flush()
                    batch.clear()
                    elapsed = time.time() - t0
                    print(f"  {total_fires:>8,} fires | {elapsed:.0f}s", flush=True)

        # Final flush
        if batch:
            f.writelines(",".join(str(x) for x in r) + "\n" for r in batch)

    elapsed = time.time() - t0
    size_mb = OUT_CSV.stat().st_size / 1e6
    print(f"\nDone: {total_fires:,} signal fires in {elapsed:.1f}s")
    print(f"Saved → {OUT_CSV}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
