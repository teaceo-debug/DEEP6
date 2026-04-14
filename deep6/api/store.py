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

# Phase 11-01: bar_history — one row per closed FootprintBar per session.
# UNIQUE(session_id, bar_index) makes insert idempotent (INSERT OR REPLACE).
# levels_json: {"tick_int_str": {"bid_vol": N, "ask_vol": N}, ...}
# Tick keys are strings so JSON round-trip is lossless; client converts
# back to price via tick_int * 0.25 (D-11).
BAR_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS bar_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    bar_index     INTEGER NOT NULL,
    ts            REAL NOT NULL,
    open          REAL NOT NULL,
    high          REAL NOT NULL,
    low           REAL NOT NULL,
    close         REAL NOT NULL,
    total_vol     INTEGER NOT NULL,
    bar_delta     INTEGER NOT NULL,
    cvd           INTEGER NOT NULL,
    poc_price     REAL NOT NULL,
    bar_range     REAL NOT NULL,
    running_delta INTEGER NOT NULL DEFAULT 0,
    max_delta     INTEGER NOT NULL DEFAULT 0,
    min_delta     INTEGER NOT NULL DEFAULT 0,
    levels_json   TEXT NOT NULL,
    inserted_at   REAL NOT NULL,
    UNIQUE(session_id, bar_index)
);
CREATE INDEX IF NOT EXISTS idx_bar_history_session
    ON bar_history(session_id, bar_index);
"""

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

# Phase 12-05: walk_forward_outcomes — one row per resolved (or EXPIRED) signal
# outcome. Sliced by (category, regime, direction) at entry; labeled CORRECT /
# INCORRECT / NEUTRAL / EXPIRED at bar_index + horizon (5/10/20). EXPIRED rows
# are excluded from rolling-Sharpe statistics (signals fired within the last
# `horizon` bars of the RTH session — see 12-CONTEXT.md FOOTGUN 1).
WALK_FORWARD_OUTCOMES_SCHEMA = """
CREATE TABLE IF NOT EXISTS walk_forward_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_event_id INTEGER,
    category        TEXT NOT NULL,
    regime          TEXT NOT NULL,
    direction       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    entry_bar_index INTEGER NOT NULL,
    session_id      TEXT NOT NULL,
    horizon         INTEGER NOT NULL,
    outcome_label   TEXT NOT NULL,
    pnl_ticks       REAL NOT NULL,
    resolved_at_ts  REAL NOT NULL,
    inserted_at     REAL NOT NULL
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
        """Create all tables if they don't exist.

        For in-memory DBs: opens and holds the persistent connection.
        For file DBs: opens a connection, creates tables, closes.
        Call once at startup (inside lifespan context manager).
        """
        if self._is_memory:
            self._mem_conn = await aiosqlite.connect(self.db_path)
            await self._mem_conn.execute(SIGNAL_EVENTS_SCHEMA)
            await self._mem_conn.execute(TRADE_EVENTS_SCHEMA)
            await self._mem_conn.execute(SETUP_TRANSITIONS_SCHEMA)
            await self._mem_conn.execute(WALK_FORWARD_OUTCOMES_SCHEMA)
            # BAR_HISTORY_SCHEMA has two statements (CREATE TABLE + CREATE INDEX);
            # executescript() handles the semicolon-separated pair.
            await self._mem_conn.executescript(BAR_HISTORY_SCHEMA)
            await self._mem_conn.commit()
        else:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(SIGNAL_EVENTS_SCHEMA)
                await db.execute(TRADE_EVENTS_SCHEMA)
                await db.execute(SETUP_TRANSITIONS_SCHEMA)
                await db.execute(WALK_FORWARD_OUTCOMES_SCHEMA)
                await db.executescript(BAR_HISTORY_SCHEMA)
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

    # ------------------------------------------------------------------
    # Phase 12-05: walk_forward_outcomes persistence
    # ------------------------------------------------------------------

    async def record_walk_forward_outcome(
        self,
        category: str,
        regime: str,
        direction: str,
        entry_price: float,
        entry_bar_index: int,
        session_id: str,
        horizon: int,
        outcome_label: str,
        pnl_ticks: float,
        resolved_at_ts: float | None = None,
        signal_event_id: int | None = None,
    ) -> int:
        """Append a resolved walk-forward outcome row.

        One row per (signal, horizon) resolution. ``outcome_label`` is one of
        CORRECT / INCORRECT / NEUTRAL / EXPIRED. EXPIRED rows are kept on disk
        for forensics but are excluded from rolling-Sharpe computations by the
        WalkForwardTracker (see phase 12-05 FOOTGUN 1).
        """
        now = time.time()
        ts_val = resolved_at_ts if resolved_at_ts is not None else now
        async with self._conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO walk_forward_outcomes
                    (signal_event_id, category, regime, direction,
                     entry_price, entry_bar_index, session_id, horizon,
                     outcome_label, pnl_ticks, resolved_at_ts, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_event_id,
                    category,
                    regime,
                    direction,
                    float(entry_price),
                    int(entry_bar_index),
                    session_id,
                    int(horizon),
                    outcome_label,
                    float(pnl_ticks),
                    float(ts_val),
                    now,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def query_walk_forward_outcomes(
        self,
        category: str | None = None,
        regime: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        """Fetch walk-forward outcomes, newest first.

        Optional filters by category and/or regime. Used by WalkForwardTracker
        for cold-start Sharpe recomputation after process restart and by the
        phase-11 analytics dashboard for per-cell performance views.
        """
        clauses: list[str] = []
        params: list = []
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if regime is not None:
            clauses.append("regime = ?")
            params.append(regime)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT * FROM walk_forward_outcomes{where} "
            f"ORDER BY resolved_at_ts DESC, id DESC LIMIT ?"
        )
        params.append(limit)
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Phase 11-01: bar_history CRUD
    # ------------------------------------------------------------------

    async def insert_bar(
        self,
        session_id: str,
        bar_index: int,
        bar: "FootprintBar",  # noqa: F821 — lazy import below
    ) -> int:
        """Persist a closed FootprintBar row.

        Uses INSERT OR REPLACE so re-ingestion is idempotent
        (per UNIQUE(session_id, bar_index) constraint).

        Returns the autoincrement id of the inserted/replaced row.
        """
        # Lazy import to avoid circular import (footprint → store → schemas → …)
        from deep6.state.footprint import FootprintBar as _FP  # noqa: F401

        levels_serializable = {
            str(tick_int): {"bid_vol": lvl.bid_vol, "ask_vol": lvl.ask_vol}
            for tick_int, lvl in bar.levels.items()
        }
        now = time.time()
        async with self._conn() as db:
            cursor = await db.execute(
                """
                INSERT OR REPLACE INTO bar_history
                    (session_id, bar_index, ts, open, high, low, close,
                     total_vol, bar_delta, cvd, poc_price, bar_range,
                     running_delta, max_delta, min_delta,
                     levels_json, inserted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    bar_index,
                    bar.timestamp,
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.total_vol,
                    bar.bar_delta,
                    bar.cvd,
                    bar.poc_price,
                    bar.bar_range,
                    bar.running_delta,
                    bar.max_delta,
                    bar.min_delta,
                    json.dumps(levels_serializable),
                    now,
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    async def fetch_bars_for_session(
        self,
        session_id: str,
        start_index: int | None = None,
        end_index: int | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        """Fetch bar_history rows for a session, ordered by bar_index ASC.

        Args:
            session_id: Session label (e.g. "2026-04-13").
            start_index: If provided, only rows with bar_index >= start_index.
            end_index:   If provided, only rows with bar_index <= end_index.
            limit:       Maximum rows returned (caps unbounded scans).

        Returns:
            List of dicts; each has a ``levels`` key with parsed dict
            (tick_int_str → {bid_vol, ask_vol}).
        """
        clauses = ["session_id = ?"]
        params: list = [session_id]
        if start_index is not None:
            clauses.append("bar_index >= ?")
            params.append(start_index)
        if end_index is not None:
            clauses.append("bar_index <= ?")
            params.append(end_index)
        params.append(limit)
        sql = (
            f"SELECT * FROM bar_history WHERE {' AND '.join(clauses)} "
            f"ORDER BY bar_index ASC LIMIT ?"
        )
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, tuple(params)) as cursor:
                rows = await cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["levels"] = json.loads(d.pop("levels_json"))
            result.append(d)
        return result

    async def fetch_bar(self, session_id: str, bar_index: int) -> dict | None:
        """Return exactly one bar dict, or None if not found."""
        sql = (
            "SELECT * FROM bar_history "
            "WHERE session_id = ? AND bar_index = ? LIMIT 1"
        )
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, (session_id, bar_index)) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["levels"] = json.loads(d.pop("levels_json"))
        return d

    async def list_sessions(self) -> list[dict]:
        """Return per-session aggregate stats ordered by last_ts DESC.

        Returns:
            List of dicts with keys: session_id, bar_count, first_ts, last_ts.
        """
        sql = (
            "SELECT session_id, "
            "COUNT(*) AS bar_count, "
            "MIN(ts) AS first_ts, "
            "MAX(ts) AS last_ts "
            "FROM bar_history "
            "GROUP BY session_id "
            "ORDER BY last_ts DESC"
        )
        async with self._conn() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql) as cursor:
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
