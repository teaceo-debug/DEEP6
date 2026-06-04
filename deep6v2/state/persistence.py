"""Dual-database persistence layer for DEEP6 v2.

EventWriter (DuckDB) — append-only analytics store for bars, signals, scores,
FSM events, and trade executions.

StateStore (SQLite) — transactional key-value state for sessions and paper-gate.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from deep6v2.types.bar import FootprintBar
from deep6v2.types.scoring import ScorerResult
from deep6v2.types.signal import SignalResult


# ---------------------------------------------------------------------------
# EventWriter — DuckDB append-only analytics
# ---------------------------------------------------------------------------

class EventWriter:
    """Append-only analytics store using DuckDB.

    Tables: bars, signals, scores, fsm_events, executions.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = duckdb.connect(self._db_path)
        self._create_schema()

    # -- schema -------------------------------------------------------------

    def _create_schema(self) -> None:
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_bars START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                id INTEGER DEFAULT nextval('seq_bars') PRIMARY KEY,
                session_id VARCHAR,
                bar_index INTEGER,
                timestamp TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                delta INTEGER,
                total_volume INTEGER,
                poc_price DOUBLE,
                vah DOUBLE,
                val DOUBLE,
                cvd DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_signals START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER DEFAULT nextval('seq_signals') PRIMARY KEY,
                session_id VARCHAR,
                bar_index INTEGER,
                timestamp TIMESTAMP,
                signal_id VARCHAR,
                direction VARCHAR,
                strength DOUBLE,
                detail VARCHAR,
                price DOUBLE
            )
        """)
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_scores START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER DEFAULT nextval('seq_scores') PRIMARY KEY,
                session_id VARCHAR,
                bar_index INTEGER,
                timestamp TIMESTAMP,
                tier VARCHAR,
                raw_score DOUBLE,
                final_score DOUBLE,
                category_scores_json VARCHAR,
                active_signal_ids_json VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_fsm START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS fsm_events (
                id INTEGER DEFAULT nextval('seq_fsm') PRIMARY KEY,
                session_id VARCHAR,
                timestamp TIMESTAMP,
                from_state VARCHAR,
                to_state VARCHAR,
                transition VARCHAR,
                reason VARCHAR
            )
        """)
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_exec START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id INTEGER DEFAULT nextval('seq_exec') PRIMARY KEY,
                session_id VARCHAR,
                timestamp TIMESTAMP,
                action VARCHAR,
                symbol VARCHAR,
                side VARCHAR,
                size INTEGER,
                price DOUBLE,
                pnl DOUBLE
            )
        """)

    # -- inserts ------------------------------------------------------------

    def insert_bar(self, bar: FootprintBar, session_id: str = "default") -> None:
        self._conn.execute(
            """
            INSERT INTO bars (session_id, bar_index, timestamp, open, high, low, close,
                              delta, total_volume, poc_price, vah, val, cvd)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id, bar.bar_index, bar.timestamp,
                bar.open, bar.high, bar.low, bar.close,
                bar.delta, bar.total_volume, bar.poc_price,
                bar.vah, bar.val, bar.cvd,
            ],
        )

    def insert_signal(
        self, signal: SignalResult, bar_index: int, session_id: str = "default",
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        self._conn.execute(
            """
            INSERT INTO signals (session_id, bar_index, timestamp, signal_id,
                                 direction, strength, detail, price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id, bar_index, now,
                signal.signal_id.value, signal.direction.name,
                signal.strength, signal.detail, signal.price,
            ],
        )

    def insert_score(
        self,
        score: ScorerResult,
        bar_index: int,
        timestamp: datetime,
        session_id: str = "default",
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO scores (session_id, bar_index, timestamp, tier, raw_score,
                                final_score, category_scores_json, active_signal_ids_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                session_id, bar_index, timestamp,
                score.tier.value, score.raw_score, score.final_score,
                json.dumps(score.category_scores),
                json.dumps([s.signal_id.value for s in score.active_signals]),
            ],
        )

    def insert_fsm_event(
        self,
        from_state: str,
        to_state: str,
        transition: str,
        reason: str,
        session_id: str = "default",
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        self._conn.execute(
            """
            INSERT INTO fsm_events (session_id, timestamp, from_state, to_state,
                                    transition, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [session_id, now, from_state, to_state, transition, reason],
        )

    def insert_execution(
        self,
        action: str,
        symbol: str,
        side: str,
        size: int,
        price: float,
        pnl: float = 0.0,
        session_id: str = "default",
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        self._conn.execute(
            """
            INSERT INTO executions (session_id, timestamp, action, symbol,
                                    side, size, price, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [session_id, now, action, symbol, side, size, price, pnl],
        )

    # -- queries ------------------------------------------------------------

    def query_bars(self, session_id: str = "default") -> list[dict]:
        return (
            self._conn.execute(
                "SELECT * FROM bars WHERE session_id = ?", [session_id],
            )
            .fetchdf()
            .to_dict("records")
        )

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# StateStore — SQLite transactional state
# ---------------------------------------------------------------------------

class StateStore:
    """Transactional key-value state store using SQLite.

    Tables: sessions, paper_gate.
    """

    _SESSIONS_COLS = ("id", "bar_count", "cvd", "state", "created_at", "updated_at")
    _PAPER_GATE_COLS = (
        "id", "session_count", "cumulative_pnl", "max_drawdown",
        "win_rate", "promoted",
    )

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_schema()

    # -- schema -------------------------------------------------------------

    def _create_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                bar_count INTEGER DEFAULT 0,
                cvd REAL DEFAULT 0.0,
                state TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_gate (
                id INTEGER PRIMARY KEY,
                session_count INTEGER DEFAULT 0,
                cumulative_pnl REAL DEFAULT 0.0,
                max_drawdown REAL DEFAULT 0.0,
                win_rate REAL DEFAULT 0.0,
                promoted INTEGER DEFAULT 0
            )
        """)
        self._conn.commit()

    # -- sessions -----------------------------------------------------------

    def upsert_session(
        self, session_id: str, bar_count: int = 0, cvd: float = 0.0,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO sessions (id, bar_count, cvd, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                bar_count = excluded.bar_count,
                cvd = excluded.cvd,
                updated_at = datetime('now')
            """,
            [session_id, bar_count, cvd],
        )
        self._conn.commit()

    def get_session(self, session_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id = ?", [session_id],
        ).fetchone()
        if row is None:
            return None
        return dict(zip(self._SESSIONS_COLS, row))

    # -- paper gate ---------------------------------------------------------

    def upsert_paper_gate(
        self,
        session_count: int = 0,
        cumulative_pnl: float = 0.0,
        max_drawdown: float = 0.0,
        win_rate: float = 0.0,
        promoted: bool = False,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO paper_gate (id, session_count, cumulative_pnl,
                                    max_drawdown, win_rate, promoted)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                session_count = excluded.session_count,
                cumulative_pnl = excluded.cumulative_pnl,
                max_drawdown = excluded.max_drawdown,
                win_rate = excluded.win_rate,
                promoted = excluded.promoted
            """,
            [session_count, cumulative_pnl, max_drawdown, win_rate, int(promoted)],
        )
        self._conn.commit()

    def get_paper_gate(self) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM paper_gate WHERE id = 1",
        ).fetchone()
        if row is None:
            return None
        return dict(zip(self._PAPER_GATE_COLS, row))

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


__all__ = ["EventWriter", "StateStore"]
