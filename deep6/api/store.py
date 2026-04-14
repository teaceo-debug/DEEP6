"""EventStore — aiosqlite CRUD for signal_events and trade_events.

Per D-03: SQLite via aiosqlite, reusing the Phase 1 pattern from
deep6/state/persistence.py (new connection per operation, no global
connection object — safe for single event loop use).

Per T-09-03: insert methods are designed to be wrapped in asyncio.shield()
by callers in the hot loop so a slow DB never blocks the signal pipeline.

Note on in-memory testing: SQLite ":memory:" databases are scoped to a single
connection. For tests, EventStore holds a persistent connection when db_path
is ":memory:" so all operations share the same in-memory state. For file-based
DBs the per-operation connection pattern (Phase 1 style) is used.
"""
from __future__ import annotations

import json
import time
from typing import Optional

import aiosqlite

from deep6.api.schemas import SignalEventIn, TradeEventIn

SIGNAL_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               REAL NOT NULL,
    bar_index        INTEGER NOT NULL,
    total_score      REAL NOT NULL,
    tier             TEXT NOT NULL,
    direction        INTEGER NOT NULL,
    engine_agreement REAL NOT NULL,
    category_count   INTEGER NOT NULL,
    categories       TEXT NOT NULL,
    gex_regime       TEXT NOT NULL DEFAULT 'NEUTRAL',
    kronos_bias      REAL NOT NULL DEFAULT 0.0,
    inserted_at      REAL NOT NULL
)
"""

TRADE_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS trade_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    position_id  TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    side         TEXT NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL NOT NULL,
    pnl          REAL NOT NULL,
    bars_held    INTEGER NOT NULL,
    signal_tier  TEXT NOT NULL,
    signal_score REAL NOT NULL DEFAULT 0.0,
    regime_label TEXT NOT NULL DEFAULT 'UNKNOWN',
    inserted_at  REAL NOT NULL
)
"""

# Phase 12-04: setup_transitions — one row per SetupTracker state change.
# Queryable by time window for post-session forensics; never modified after
# insert (append-only). Independent of signal_events / trade_events.
SETUP_TRANSITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS setup_transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timeframe   TEXT NOT NULL,
    setup_id    TEXT NOT NULL,
    from_state  TEXT NOT NULL,
    to_state    TEXT NOT NULL,
    trigger     TEXT NOT NULL,
    weight      REAL NOT NULL,
    bar_index   INTEGER NOT NULL,
    ts          REAL NOT NULL,
    inserted_at REAL NOT NULL
)
"""

# Closed trade event types — used by count_oos_trades_per_signal
_CLOSED_TYPES = ("'STOP_HIT'", "'TARGET_HIT'", "'TIMEOUT_EXIT'", "'MANUAL_EXIT'")
_CLOSED_IN = f"({', '.join(_CLOSED_TYPES)})"


class EventStore:
    """Async SQLite event store for signal and trade history.

    For file-based DBs: uses the Phase 1 per-operation connection pattern —
    each method opens a fresh aiosqlite connection, executes, commits, closes.
    Safe for single asyncio event loop; not safe for concurrent writers.

    For ":memory:" DBs (tests): holds a single persistent aiosqlite connection
    since in-memory databases are scoped to one connection.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._is_memory = db_path == ":memory:"
        self._mem_conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Create signal_events and trade_events tables if they don't exist.

        For in-memory DBs: opens and holds the persistent connection.
        For file DBs: opens a connection, creates tables, closes.
        Call once at startup (inside lifespan context manager).
        """
        if self._is_memory:
            self._mem_conn = await aiosqlite.connect(self.db_path)
            await self._mem_conn.execute(SIGNAL_EVENTS_SCHEMA)
            await self._mem_conn.execute(TRADE_EVENTS_SCHEMA)
            await self._mem_conn.execute(SETUP_TRANSITIONS_SCHEMA)
            await self._mem_conn.commit()
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(SIGNAL_EVENTS_SCHEMA)
                await db.execute(TRADE_EVENTS_SCHEMA)
                await db.execute(SETUP_TRANSITIONS_SCHEMA)
                await db.commit()

    def _conn(self):
        """Context manager: returns persistent conn for memory, new conn for file."""
        if self._is_memory:
            return _BorrowedConnection(self._mem_conn)
        return aiosqlite.connect(self.db_path)

    async def insert_signal_event(self, ev: SignalEventIn) -> int:
        """Insert a signal event row. Returns the autoincrement id."""
        now = time.time()
        async with self._conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO signal_events
                    (ts, bar_index, total_score, tier, direction,
                     engine_agreement, category_count, categories,
                     gex_regime, kronos_bias, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.ts,
                    ev.bar_index_in_session,
                    ev.total_score,
                    ev.tier,
                    ev.direction,
                    ev.engine_agreement,
                    ev.category_count,
                    json.dumps(ev.categories_firing),
                    ev.gex_regime,
                    ev.kronos_bias,
                    now,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def insert_trade_event(self, ev: TradeEventIn) -> int:
        """Insert a trade event row. Returns the autoincrement id."""
        now = time.time()
        async with self._conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO trade_events
                    (ts, position_id, event_type, side, entry_price,
                     exit_price, pnl, bars_held, signal_tier, signal_score,
                     regime_label, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.ts,
                    ev.position_id,
                    ev.event_type,
                    ev.side,
                    ev.entry_price,
                    ev.exit_price,
                    ev.pnl,
                    ev.bars_held,
                    ev.signal_tier,
                    ev.signal_score,
                    ev.regime_label,
                    now,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def fetch_signal_events(
        self,
        limit: int = 5000,
        tier_filter: str | None = None,
    ) -> list[dict]:
        """Fetch signal events ordered by ts DESC.

        Args:
            limit: Maximum rows to return.
            tier_filter: If provided, only return rows with this tier value.

        Returns:
            List of dicts with column names as keys.
        """
        if tier_filter is not None:
            sql = (
                "SELECT * FROM signal_events WHERE tier = ? "
                "ORDER BY ts DESC LIMIT ?"
            )
            params: tuple = (tier_filter, limit)
        else:
            sql = "SELECT * FROM signal_events ORDER BY ts DESC LIMIT ?"
            params = (limit,)

        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def fetch_trade_events(
        self,
        limit: int = 2000,
        tier_filter: str | None = None,
    ) -> list[dict]:
        """Fetch trade events ordered by ts DESC.

        Args:
            limit: Maximum rows to return.
            tier_filter: If provided, only return rows with this signal_tier value.

        Returns:
            List of dicts with column names as keys.
        """
        if tier_filter is not None:
            sql = (
                "SELECT * FROM trade_events WHERE signal_tier = ? "
                "ORDER BY ts DESC LIMIT ?"
            )
            params = (tier_filter, limit)
        else:
            sql = "SELECT * FROM trade_events ORDER BY ts DESC LIMIT ?"
            params = (limit,)

        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Phase 12-04: setup_transitions persistence
    # ------------------------------------------------------------------

    async def record_setup_transition(
        self,
        timeframe: str,
        setup_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        weight: float,
        bar_index: int,
        ts: float | None = None,
    ) -> int:
        """Append a setup state-machine transition row.

        One row per SetupTracker transition (see deep6.orderflow.setup_tracker).
        Called from SharedState.on_bar_close (via SetupTracker.update) and
        from SharedState.close_trade (via SetupTracker.close_trade).

        Returns the autoincrement id. Non-blocking aiosqlite — safe inside
        the bar-close coroutine for single transition per bar per timeframe
        (at most ~2 writes per bar close, well within event-loop budget).
        """
        now = time.time()
        ts_val = ts if ts is not None else now
        async with self._conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO setup_transitions
                    (timeframe, setup_id, from_state, to_state,
                     trigger, weight, bar_index, ts, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timeframe,
                    setup_id,
                    from_state,
                    to_state,
                    trigger,
                    float(weight),
                    int(bar_index),
                    float(ts_val),
                    now,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def query_setup_transitions(
        self,
        session_start_ts: float,
        session_end_ts: float,
    ) -> list[dict]:
        """Fetch setup transitions whose ts falls within [start, end].

        Ordered by ts ASC for replay semantics (a session's transitions
        walk forward in time). Used for post-session forensics and the
        phase 12-05 walk-forward tracker.
        """
        sql = (
            "SELECT * FROM setup_transitions "
            "WHERE ts BETWEEN ? AND ? "
            "ORDER BY ts ASC, id ASC"
        )
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, (session_start_ts, session_end_ts)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def count_oos_trades_per_signal(self) -> dict[str, int]:
        """Return count of closed trades grouped by signal_tier.

        Closed = event_type in (STOP_HIT, TARGET_HIT, TIMEOUT_EXIT, MANUAL_EXIT).
        Used by ML training gate (D-17: minimum 200 OOS trades per signal).

        Returns:
            Dict mapping signal_tier → count of closed trades.
        """
        sql = (
            f"SELECT signal_tier, COUNT(*) as cnt FROM trade_events "
            f"WHERE event_type IN {_CLOSED_IN} "
            f"GROUP BY signal_tier"
        )
        async with self._conn() as db:
            async with db.execute(sql) as cursor:
                return {row[0]: row[1] async for row in cursor}


class _BorrowedConnection:
    """Thin async context manager that wraps an existing aiosqlite connection
    without closing it on __aexit__. Used for in-memory DB mode so the
    persistent connection survives across per-operation calls.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def __aenter__(self) -> aiosqlite.Connection:
        return self._conn

    async def __aexit__(self, *args) -> None:
        # Do NOT close — connection is persistent for in-memory DB
        pass
