"""Replay the downloaded Databento MBO file through ReplaySession.

Exercises the Phase 13 backtest engine end-to-end on real data and writes
results to a DuckDB file for inspection.

Usage:
    python scripts/replay_downloaded_mbo.py [--events 5000000] [--out data/backtests/run.duckdb]
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import duckdb

from deep6.backtest.config import BacktestConfig
from deep6.backtest.session import ReplaySession
from deep6.config import Config
from deep6.state.shared import SharedState


DEFAULT_DBN = "data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst"


async def run(dbn_path: str, max_events: int, out_db: str) -> None:
    os.environ.setdefault("DEEP6_DB_PATH", ":memory:")
    os.environ.setdefault("RITHMIC_USER", "unused")
    os.environ.setdefault("RITHMIC_PASSWORD", "unused")
    os.environ.setdefault("RITHMIC_SYSTEM_NAME", "unused")
    os.environ.setdefault("RITHMIC_URI", "unused")

    # Build a SharedState — needed so DOM engines can consult state.dom.
    config = Config.from_env()
    state = SharedState.build(config)
    await state.persistence.initialize()

    # Open the DBN store and cap the event count for a bounded run.
    store = db.DBNStore.from_file(dbn_path)
    event_iter = itertools.islice(store, max_events)

    # Find the real time range of the slice so BacktestConfig is meaningful.
    # Peek first event for start; use now for end (adapter walks events anyway).
    start = datetime(2026, 4, 5, tzinfo=timezone.utc)
    end = datetime(2026, 4, 11, tzinfo=timezone.utc)

    cfg = BacktestConfig(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=start,
        end=end,
        tf_list=["1m", "5m"],
        duckdb_path=out_db,
        git_sha="replay-real",
    )

    Path(out_db).parent.mkdir(parents=True, exist_ok=True)
    if Path(out_db).exists():
        Path(out_db).unlink()

    t0 = time.time()
    async with ReplaySession(cfg, state, event_source=event_iter) as session:
        await session.run()
    elapsed = time.time() - t0

    print(f"Replay done in {elapsed:.1f}s")
    print(f"  bars_written    = {session.bars_written}")
    print(f"  dom_signal_fires = {session.dom_signal_fires}")
    print(f"  run_id          = {session.run_id}")
    print(f"  duckdb          = {out_db}")

    # Quick stats query
    con = duckdb.connect(out_db, read_only=True)
    print("\n--- backtest_runs ---")
    rows = con.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()
    print(f"run rows: {rows[0]}")

    print("\n--- backtest_bars ---")
    total = con.execute("SELECT COUNT(*) FROM backtest_bars").fetchone()
    print(f"bar rows: {total[0]}")

    cols = [r[0] for r in con.execute("DESCRIBE backtest_bars").fetchall()]
    print(f"columns: {cols}")

    for col in ("tier", "timeframe", "tf"):
        if col in cols:
            dist = con.execute(
                f"SELECT {col}, COUNT(*) FROM backtest_bars GROUP BY {col} ORDER BY 2 DESC"
            ).fetchall()
            print(f"\n{col} distribution: {dist}")
            break

    # Signal flag summary if present
    if "signal_flags" in cols:
        nonzero = con.execute(
            "SELECT COUNT(*) FROM backtest_bars WHERE signal_flags != 0"
        ).fetchone()[0]
        print(f"\nbars with any signal flag set: {nonzero} / {total[0]}")

    print("\n--- backtest_trades ---")
    try:
        trades = con.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]
        print(f"trade rows: {trades}")
    except Exception as exc:
        print(f"(no trades table or empty: {exc})")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dbn", default=DEFAULT_DBN)
    p.add_argument("--events", type=int, default=5_000_000)
    p.add_argument("--out", default="data/backtests/replay_5m.duckdb")
    args = p.parse_args()

    asyncio.run(run(args.dbn, args.events, args.out))


if __name__ == "__main__":
    main()
