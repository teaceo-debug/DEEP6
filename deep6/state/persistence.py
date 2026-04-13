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
        """Create session_state table if not exists. Call once at startup."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(SCHEMA)
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
