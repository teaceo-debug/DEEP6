"""DuckDBResultStore tests — schema creation, batched writes, round-trip.

Phase 13-01 T-13-01-08. Validates:
  - 3 tables (backtest_runs, backtest_bars, backtest_trades) created on connect
  - record_bar writes buffer, auto-flushes every 1000 rows, final flush on exit
  - signal_flags int64 bitmask round-trips byte-exact
  - config_json nested dict round-trips via DuckDB JSON column
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from deep6.backtest.result_store import DuckDBResultStore


def test_schema_created(tmp_path: Path) -> None:
    db_path = tmp_path / "r.duckdb"
    with DuckDBResultStore(str(db_path)) as store:
        pass
    con = duckdb.connect(str(db_path))
    rows = con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    names = {r[0] for r in rows}
    assert "backtest_runs" in names
    assert "backtest_bars" in names
    assert "backtest_trades" in names
    con.close()


def test_record_bar_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "r.duckdb"
    run_id = str(uuid.uuid4())
    with DuckDBResultStore(str(db_path)) as store:
        store.record_run(
            run_id=run_id,
            symbol="NQ.c.0",
            dataset="GLBX.MDP3",
            config_json={"k": "v"},
            git_sha="abc",
        )
        base = datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc)
        # 1500 bars -> one auto-flush at 1000, final flush of 500 at __exit__
        for i in range(1500):
            store.record_bar(
                run_id=run_id,
                bar_ts=base,
                tf="1m",
                ohlcv=(21000.0 + i, 21005.0 + i, 20995.0 + i, 21001.0 + i, 100 + i),
                signal_flags=0,
                score=50.0,
                tier="NONE",
                direction="NONE",
                bar_key=i,  # disambiguate PK
            )
    con = duckdb.connect(str(db_path))
    n = con.execute(
        "SELECT COUNT(*) FROM backtest_bars WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    con.close()
    assert n == 1500


def test_signal_flags_pack_int64(tmp_path: Path) -> None:
    db_path = tmp_path / "r.duckdb"
    run_id = str(uuid.uuid4())
    flags = (1 << 43) | (1 << 22) | 1
    with DuckDBResultStore(str(db_path)) as store:
        store.record_run(
            run_id=run_id, symbol="NQ.c.0", dataset="GLBX.MDP3",
            config_json={}, git_sha="",
        )
        store.record_bar(
            run_id=run_id,
            bar_ts=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
            tf="1m",
            ohlcv=(1.0, 2.0, 0.5, 1.5, 10),
            signal_flags=flags,
            score=88.0,
            tier="TIER_1",
            direction="LONG",
        )
    con = duckdb.connect(str(db_path))
    got = con.execute(
        "SELECT signal_flags FROM backtest_bars WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    con.close()
    assert int(got) == flags


def test_record_run_json_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "r.duckdb"
    run_id = str(uuid.uuid4())
    cfg = {
        "dataset": "GLBX.MDP3",
        "symbol": "NQ.c.0",
        "nested": {"tf_list": ["1m", "5m"], "fill_model": "perfect"},
    }
    with DuckDBResultStore(str(db_path)) as store:
        store.record_run(
            run_id=run_id, symbol="NQ.c.0", dataset="GLBX.MDP3",
            config_json=cfg, git_sha="deadbeef",
        )
    con = duckdb.connect(str(db_path))
    row = con.execute(
        "SELECT config_json, git_sha FROM backtest_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    con.close()
    # DuckDB JSON column returns a JSON string
    got = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    assert got == cfg
    assert row[1] == "deadbeef"
