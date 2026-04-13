"""SessionPersistence: async SQLite key-value store for session state.

Per D-15: aiosqlite for async SQLite access.
Per D-07: session_id is the date string "YYYYMMDD"; keys are session state fields.
Schema: session_state(session_id TEXT, key TEXT, value TEXT, updated_at REAL)

PRIMARY KEY (session_id, key) enforces one row per (session, field).
INSERT OR REPLACE upserts — last write wins.
"""
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_state (
    session_id TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (session_id, key)
);
"""

AUCTION_SCHEMA = """
CREATE TABLE IF NOT EXISTS auction_levels (
    session_id TEXT NOT NULL,
    price      REAL NOT NULL,
    direction  INTEGER NOT NULL,
    strength   REAL NOT NULL,
    timestamp  REAL NOT NULL,
    resolved   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, price)
);
"""

# Canonical session keys — all fields of SessionContext (D-07)
SESSION_KEYS = [
    "cvd",
    "vwap_numerator",
    "vwap_denominator",
    "ib_high",
    "ib_low",
    "ib_complete",
    "opening_range_high",
    "opening_range_low",
    "day_type",
]


class SessionPersistence:
    """Async key-value store backed by SQLite. One row per (session_id, key).

    Usage:
        p = SessionPersistence("./deep6_session.db")
        await p.initialize()
        await p.write("20260411", "cvd", "42")
        data = await p.read_all("20260411")
        ctx = SessionContext.from_dict(data)

    Thread safety: aiosqlite opens a new connection per operation — safe for
    single-event-loop use (no concurrent writes from multiple threads).

    In-memory SQLite (":memory:") is supported for tests.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create session_state and auction_levels tables if not exists. Call once at startup."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(SCHEMA)
            await db.execute(AUCTION_SCHEMA)
            await db.commit()

    async def write(self, session_id: str, key: str, value: str) -> None:
        """Insert or replace a session state entry.

        Per D-07: value is always a string — SessionContext.to_dict() handles
        serialisation; from_dict() handles casting on read.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO session_state "
                "(session_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, key, value, time.time()),
            )
            await db.commit()

    async def write_many(self, session_id: str, data: dict) -> None:
        """Write all key-value pairs from a dict atomically (single transaction).

        More efficient than calling write() N times when persisting an entire
        SessionContext at session close.
        """
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.executemany(
                "INSERT OR REPLACE INTO session_state "
                "(session_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
                [(session_id, k, v, now) for k, v in data.items()],
            )
            await db.commit()

    async def read_all(self, session_id: str) -> dict:
        """Return all key-value pairs for the given session_id.

        Returns empty dict when no rows exist for session_id — never raises.
        Caller (SessionContext.from_dict) handles missing keys with defaults.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT key, value FROM session_state WHERE session_id = ?",
                (session_id,),
            ) as cursor:
                return {row[0]: row[1] async for row in cursor}

    async def persist_session_context(self, session_id: str, ctx) -> None:
        """Convenience: persist a SessionContext to SQLite atomically.

        Equivalent to write_many(session_id, ctx.to_dict()).
        """
        await self.write_many(session_id, ctx.to_dict())

    async def restore_session_context(self, session_id: str):
        """Convenience: restore a SessionContext from SQLite.

        Returns None if no state exists for this session_id (fresh session).
        Returns a SessionContext populated from stored values otherwise.
        """
        from deep6.state.session import SessionContext
        data = await self.read_all(session_id)
        if not data:
            return None
        return SessionContext.from_dict(data)

    async def persist_auction_levels(self, session_id: str, levels: list[dict]) -> None:
        """Persist unfinished auction levels for cross-session tracking.

        Each level dict: {price: float, direction: int, strength: float, timestamp: float}

        Per D-07: unfinished business levels must survive process restart.
        Uses INSERT OR REPLACE so repeated calls are idempotent.
        """
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            for level in levels:
                await db.execute(
                    "INSERT OR REPLACE INTO auction_levels "
                    "(session_id, price, direction, strength, timestamp, resolved) "
                    "VALUES (?, ?, ?, ?, ?, 0)",
                    (session_id, level["price"], level["direction"],
                     level["strength"], level.get("timestamp", now)),
                )
            await db.commit()

    async def restore_auction_levels(self, max_sessions: int = 5) -> list[dict]:
        """Restore unresolved auction levels from recent sessions.

        Returns levels from the most recent max_sessions sessions that
        have not been resolved (price has not returned to that level).

        Per T-03-05: limits rows to max_sessions * 50 to prevent unbounded growth.
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT session_id, price, direction, strength, timestamp "
                "FROM auction_levels WHERE resolved = 0 "
                "ORDER BY timestamp DESC LIMIT ?",
                (max_sessions * 50,),  # generous limit per T-03-05
            ) as cursor:
                return [
                    {"session_id": row[0], "price": row[1], "direction": row[2],
                     "strength": row[3], "timestamp": row[4]}
                    async for row in cursor
                ]

    async def resolve_auction_level(self, price: float) -> None:
        """Mark an auction level as resolved (price returned to it).

        Sets resolved=1 for all unresolved rows at this price across all sessions.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE auction_levels SET resolved = 1 WHERE price = ? AND resolved = 0",
                (price,),
            )
            await db.commit()
