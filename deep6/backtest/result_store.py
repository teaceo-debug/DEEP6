"""DuckDBResultStore — backtest run artifact writer.

Phase 13-01 T-13-01-08. Write-only store for replay outputs:
  - ``backtest_runs``   one row per replay session (run_id, symbol, config_json…)
  - ``backtest_bars``   one row per closed bar with signal_flags bitmask + score
  - ``backtest_trades`` one row per simulated fill (populated in phase 14)

Design:
    - Synchronous (DuckDB driver is sync) — wrapped in a context manager.
    - Buffered writes: ``record_bar`` appends to an in-memory list; auto-flushes
      every ``batch_size`` (default 1000) rows and on ``__exit__``.
    - Single-writer contract: one process writes to one DuckDB file at a time.
      DuckDB file-locks the database, so concurrent writers would fail loudly.
    - Schema is idempotent via ``CREATE TABLE IF NOT EXISTS``.

FOOTGUN 4 mitigation: unflushed rows are bounded to <``batch_size`` (<=1000 by
default). Catastrophic interrupt (kill -9) mid-batch can still lose the current
buffer; this is documented and accepted in the plan threat register (T-13-01-04).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import duckdb
import structlog

log = structlog.get_logger(__name__)


_RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id VARCHAR PRIMARY KEY,
    start_ts TIMESTAMP,
    end_ts TIMESTAMP,
    symbol VARCHAR,
    dataset VARCHAR,
    config_json JSON,
    git_sha VARCHAR
)
"""

_BARS_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_bars (
    run_id VARCHAR,
    bar_ts TIMESTAMP,
    bar_key BIGINT,
    tf VARCHAR,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume BIGINT,
    signal_flags BIGINT,
    score DOUBLE,
    tier VARCHAR,
    direction VARCHAR,
    dom_blob BLOB,
    PRIMARY KEY (run_id, bar_ts, tf, bar_key)
)
"""

_TRADES_SCHEMA = """
CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id VARCHAR,
    run_id VARCHAR,
    entry_ts TIMESTAMP,
    exit_ts TIMESTAMP,
    side VARCHAR,
    qty INTEGER,
    entry_price DOUBLE,
    exit_price DOUBLE,
    pnl DOUBLE,
    tier VARCHAR,
    fill_model VARCHAR,
    exit_reason VARCHAR
)
"""

# Columns added in Phase 13-03 — tolerated ALTER on existing dev databases.
_TRADES_ALTERS = (
    "ALTER TABLE backtest_trades ADD COLUMN IF NOT EXISTS trade_id VARCHAR",
    "ALTER TABLE backtest_trades ADD COLUMN IF NOT EXISTS exit_reason VARCHAR",
)


class DuckDBResultStore:
    """Synchronous context-manager DuckDB writer for backtest artifacts.

    Usage:
        with DuckDBResultStore("backtest_results.duckdb") as store:
            store.record_run(run_id, "NQ.c.0", "GLBX.MDP3", {...}, git_sha)
            store.record_bar(run_id, bar_ts, tf="1m",
                             ohlcv=(o, h, l, c, v),
                             signal_flags=flags, score=s,
                             tier="TIER_1", direction="LONG")
            # ...
        # __exit__ flushes remaining rows and closes the connection.
    """

    def __init__(self, path: str, batch_size: int = 1000) -> None:
        self.path = path
        self.batch_size = batch_size
        self._con: duckdb.DuckDBPyConnection | None = None
        self._bar_buffer: list[tuple] = []
        self._trade_buffer: list[tuple] = []

    # -- context manager -------------------------------------------------

    def __enter__(self) -> "DuckDBResultStore":
        self._con = duckdb.connect(self.path)
        self._con.execute(_RUNS_SCHEMA)
        self._con.execute(_BARS_SCHEMA)
        self._con.execute(_TRADES_SCHEMA)
        # Tolerant upgrade for dev DBs created before Phase 13-03 added
        # trade_id / exit_reason. No-op on fresh schemas created above.
        for stmt in _TRADES_ALTERS:
            try:
                self._con.execute(stmt)
            except Exception:
                # DuckDB versions without IF NOT EXISTS for ADD COLUMN will
                # throw if the column already exists — safe to ignore.
                pass
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.flush()
        finally:
            if self._con is not None:
                self._con.close()
                self._con = None

    # -- writers ---------------------------------------------------------

    def record_run(
        self,
        run_id: str,
        symbol: str,
        dataset: str,
        config_json: dict[str, Any],
        git_sha: str = "",
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> None:
        """Insert a single backtest_runs row. Idempotent via INSERT OR REPLACE."""
        self._require_con().execute(
            "INSERT OR REPLACE INTO backtest_runs "
            "(run_id, start_ts, end_ts, symbol, dataset, config_json, git_sha) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                start_ts,
                end_ts,
                symbol,
                dataset,
                json.dumps(config_json),
                git_sha,
            ],
        )

    def record_bar(
        self,
        run_id: str,
        bar_ts: datetime,
        tf: str,
        ohlcv: tuple[float, float, float, float, int],
        signal_flags: int,
        score: float,
        tier: str,
        direction: str,
        dom_blob: bytes | None = None,
        bar_key: int = 0,
    ) -> None:
        """Buffer a bar row; auto-flush when batch_size is reached.

        ``bar_key`` disambiguates the PK when multiple bars land on the same
        ``(bar_ts, tf)`` — e.g. back-to-back replay of a synthetic stream.
        Production callers typically leave it 0 because the bar boundary is
        unique per timeframe.
        """
        o, h, l, c, v = ohlcv
        self._bar_buffer.append(
            (
                run_id, bar_ts, int(bar_key), tf,
                float(o), float(h), float(l), float(c), int(v),
                int(signal_flags), float(score), tier, direction,
                dom_blob,
            )
        )
        if len(self._bar_buffer) >= self.batch_size:
            self._flush_bars()

    def record_trade(
        self,
        run_id: str,
        entry_ts: datetime,
        exit_ts: datetime | None,
        side: str,
        qty: int,
        entry_price: float,
        exit_price: float | None,
        pnl: float,
        tier: str,
        fill_model: str = "perfect",
        trade_id: str | None = None,
        exit_reason: str | None = None,
    ) -> None:
        self._trade_buffer.append(
            (
                trade_id, run_id, entry_ts, exit_ts, side, int(qty),
                float(entry_price),
                float(exit_price) if exit_price is not None else None,
                float(pnl), tier, fill_model, exit_reason,
            )
        )
        if len(self._trade_buffer) >= self.batch_size:
            self._flush_trades()

    def update_trade_exit(
        self,
        trade_id: str,
        exit_ts: datetime,
        exit_price: float,
        pnl: float,
        exit_reason: str,
    ) -> None:
        """Fill in exit_ts / exit_price / pnl / exit_reason for a trade.

        Phase 13-03. ReplaySession inserts trades open (exit columns NULL)
        when the signal bar closes, then calls this once the bracket
        resolves (subsequent bar touches stop or target) or ``on_exit``
        force-closes at stream end.

        The update flushes the trade buffer first so newly-inserted rows
        are visible. This makes bracket-resolution O(flush_per_exit) in
        the worst case — acceptable for replay throughput and keeps the
        schema simple (no separate trade_exits side-table).
        """
        # Ensure the open row exists in the DB before updating.
        self._flush_trades()
        self._require_con().execute(
            "UPDATE backtest_trades "
            "SET exit_ts = ?, exit_price = ?, pnl = ?, exit_reason = ? "
            "WHERE trade_id = ?",
            [exit_ts, float(exit_price), float(pnl), exit_reason, trade_id],
        )

    def flush(self) -> None:
        """Flush both bar and trade buffers."""
        self._flush_bars()
        self._flush_trades()

    # -- internal --------------------------------------------------------

    def _require_con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            raise RuntimeError("DuckDBResultStore used outside of context manager")
        return self._con

    def _flush_bars(self) -> None:
        if not self._bar_buffer:
            return
        con = self._require_con()
        con.executemany(
            "INSERT OR REPLACE INTO backtest_bars "
            "(run_id, bar_ts, bar_key, tf, open, high, low, close, volume, "
            " signal_flags, score, tier, direction, dom_blob) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self._bar_buffer,
        )
        log.debug("result_store.flush_bars", n=len(self._bar_buffer))
        self._bar_buffer.clear()

    def _flush_trades(self) -> None:
        if not self._trade_buffer:
            return
        con = self._require_con()
        con.executemany(
            "INSERT INTO backtest_trades "
            "(trade_id, run_id, entry_ts, exit_ts, side, qty, entry_price, "
            " exit_price, pnl, tier, fill_model, exit_reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self._trade_buffer,
        )
        log.debug("result_store.flush_trades", n=len(self._trade_buffer))
        self._trade_buffer.clear()
