"""EventStore schema extensions for Phase 15-04 TradeDecisionMachine.

Adds the ``fsm_transitions`` table (D-19): one row per FSM state change.
Schema is idempotent (``CREATE TABLE IF NOT EXISTS``) and designed to be
installed alongside the existing Phase-9 tables in ``deep6/api/store.py``.

Production callers can either:
1. Reuse the ``deep6.api.store.EventStore`` instance and invoke
   ``install_fsm_transitions_schema(db)`` at startup, OR
2. Pass a duck-typed writer (any object with an ``insert_fsm_transition``
   async method) to ``TradeDecisionMachine`` — the in-memory recorder used
   in tests satisfies this contract.

The non-blocking design follows T-09-03: callers MAY wrap inserts in
``asyncio.shield`` so a slow DB never blocks the signal pipeline.
"""
from __future__ import annotations

import json
import time
from typing import Protocol


FSM_TRANSITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS fsm_transitions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    bar_ts           REAL NOT NULL,
    bar_index        INTEGER NOT NULL,
    from_state       TEXT NOT NULL,
    to_state         TEXT NOT NULL,
    transition_id    TEXT NOT NULL,
    trigger          TEXT,
    regime           TEXT,
    confluence_score REAL,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    inserted_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fsm_transitions_ts
    ON fsm_transitions(bar_ts);
"""


async def install_fsm_transitions_schema(db) -> None:
    """Create fsm_transitions table + index on an aiosqlite connection.

    Idempotent — safe to call on every startup.
    """
    await db.executescript(FSM_TRANSITIONS_SCHEMA)
    await db.commit()


async def insert_fsm_transition(
    db,
    *,
    bar_ts: float,
    bar_index: int,
    from_state: str,
    to_state: str,
    transition_id: str,
    trigger: str | None = None,
    regime: str | None = None,
    confluence_score: float | None = None,
    payload: dict | None = None,
) -> None:
    """Insert one fsm_transitions row via aiosqlite.

    ``payload`` is JSON-encoded. Common keys: ``level_uids``, ``order_intents``,
    ``bar_close``, ``flags``. Non-serializable values are stringified.
    """
    payload_json = json.dumps(payload or {}, default=str)
    await db.execute(
        """
        INSERT INTO fsm_transitions
            (bar_ts, bar_index, from_state, to_state, transition_id, trigger,
             regime, confluence_score, payload_json, inserted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bar_ts,
            bar_index,
            from_state,
            to_state,
            transition_id,
            trigger,
            regime,
            confluence_score,
            payload_json,
            time.time(),
        ),
    )
    await db.commit()


class FsmTransitionWriter(Protocol):
    """Duck-type contract TradeDecisionMachine uses.

    Both the in-memory test recorder and the Phase-9 aiosqlite-backed
    EventStore satisfy this shape. The FSM never imports aiosqlite directly.
    """

    def record_transition(
        self,
        *,
        bar_ts: float,
        bar_index: int,
        from_state: str,
        to_state: str,
        transition_id: str,
        trigger: str | None,
        regime: str | None,
        confluence_score: float | None,
        payload: dict,
    ) -> None:
        ...  # pragma: no cover


class InMemoryFsmWriter:
    """Synchronous in-memory recorder used in tests and deferred flushing.

    Each call appends a dict to ``self.rows``. The FSM treats ``record_transition``
    as side-effecting only — return value ignored.
    """

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record_transition(
        self,
        *,
        bar_ts: float,
        bar_index: int,
        from_state: str,
        to_state: str,
        transition_id: str,
        trigger: str | None,
        regime: str | None,
        confluence_score: float | None,
        payload: dict,
    ) -> None:
        self.rows.append(
            {
                "bar_ts": bar_ts,
                "bar_index": bar_index,
                "from_state": from_state,
                "to_state": to_state,
                "transition_id": transition_id,
                "trigger": trigger,
                "regime": regime,
                "confluence_score": confluence_score,
                "payload": dict(payload),
            }
        )
