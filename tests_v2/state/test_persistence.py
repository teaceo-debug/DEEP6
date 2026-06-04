from __future__ import annotations

import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.signal import Direction, SignalId, SignalResult
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.state.persistence import EventWriter, StateStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bar(bar_index: int = 0, close: float = 21000.0) -> FootprintBar:
    return FootprintBar(
        open=20990.0,
        high=21010.0,
        low=20980.0,
        close=close,
        delta=150,
        total_volume=5000,
        bid_volumes={20990.0: 1200, 20980.0: 800},
        ask_volumes={21000.0: 1500, 21010.0: 1500},
        poc_price=21000.0,
        poc_volume=3000,
        vah=21005.0,
        val=20985.0,
        cvd=320.0,
        bar_index=bar_index,
        timestamp=datetime(2026, 5, 14, 10, 30, 0, tzinfo=timezone.utc),
        session_type=SessionType.RTH,
    )


def _make_signal() -> SignalResult:
    return SignalResult(
        signal_id=SignalId.ABS_01,
        direction=Direction.BULLISH,
        strength=0.85,
        detail="absorption at bid",
        price=21000.0,
        flag_bit=1,
    )


def _make_score() -> ScorerResult:
    sig = _make_signal()
    return ScorerResult(
        tier=SignalTier.TYPE_A,
        raw_score=85.0,
        final_score=90.0,
        category_scores={"absorption": 0.9, "delta": 0.7},
        category_count=2,
        confluence_mult=1.1,
        zone_bonus=5.0,
        gex_mult=1.0,
        agreement_mult=1.05,
        ib_mult=1.0,
        vpin_mult=1.0,
        midday_blocked=False,
        active_signals=[sig],
        veto_reasons=[],
        e10_agreement=True,
        e10_caution=False,
        wall_context_applied=False,
        wall_context_details=[],
    )


# ---------------------------------------------------------------------------
# EventWriter tests (DuckDB)
# ---------------------------------------------------------------------------

class TestEventWriter:
    def test_bar_insert_query(self) -> None:
        writer = EventWriter(":memory:")
        bar = _make_bar(bar_index=0, close=21000.0)
        writer.insert_bar(bar, session_id="sess1")

        rows = writer.query_bars(session_id="sess1")
        assert len(rows) == 1
        row = rows[0]
        assert row["bar_index"] == 0
        assert row["close"] == 21000.0
        assert row["delta"] == 150
        assert row["total_volume"] == 5000
        assert row["poc_price"] == 21000.0
        assert row["cvd"] == 320.0
        writer.close()

    def test_signal_insert(self) -> None:
        writer = EventWriter(":memory:")
        sig = _make_signal()
        writer.insert_signal(sig, bar_index=5, session_id="sess1")

        rows = writer._conn.execute(
            "SELECT * FROM signals WHERE session_id = 'sess1'"
        ).fetchall()
        assert len(rows) == 1
        # signal_id column
        row = rows[0]
        # Columns: id, session_id, bar_index, timestamp, signal_id, direction, strength, detail, price
        assert row[4] == "ABS_01"  # signal_id
        assert row[5] == "BULLISH"  # direction
        assert abs(row[6] - 0.85) < 1e-9  # strength
        writer.close()

    def test_score_insert(self) -> None:
        writer = EventWriter(":memory:")
        score = _make_score()
        ts = datetime(2026, 5, 14, 10, 30, 0, tzinfo=timezone.utc)
        writer.insert_score(score, bar_index=3, timestamp=ts, session_id="sess1")

        rows = writer._conn.execute(
            "SELECT * FROM scores WHERE session_id = 'sess1'"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        # tier column
        assert row[4] == "TYPE_A"
        writer.close()

    def test_in_memory(self) -> None:
        """Uses :memory: — no disk file needed."""
        writer = EventWriter(":memory:")
        bar = _make_bar()
        writer.insert_bar(bar)
        rows = writer.query_bars()
        assert len(rows) == 1
        writer.close()

    def test_batch_insert_1000(self) -> None:
        writer = EventWriter(":memory:")
        bars = [_make_bar(bar_index=i, close=21000.0 + i) for i in range(1000)]

        start = time.perf_counter()
        for bar in bars:
            writer.insert_bar(bar, session_id="batch")
        elapsed = time.perf_counter() - start

        rows = writer.query_bars(session_id="batch")
        assert len(rows) == 1000
        assert elapsed < 5.0, f"Batch insert took {elapsed:.2f}s (threshold 5s)"
        writer.close()

    def test_fsm_event_insert(self) -> None:
        writer = EventWriter(":memory:")
        writer.insert_fsm_event(
            from_state="SCANNING",
            to_state="ARMED",
            transition="arm",
            reason="Type A signal",
            session_id="sess1",
        )
        rows = writer._conn.execute(
            "SELECT * FROM fsm_events WHERE session_id = 'sess1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][4] == "ARMED"  # to_state
        writer.close()

    def test_execution_insert(self) -> None:
        writer = EventWriter(":memory:")
        writer.insert_execution(
            action="entry",
            symbol="NQ",
            side="BUY",
            size=1,
            price=21000.0,
            pnl=0.0,
            session_id="sess1",
        )
        rows = writer._conn.execute(
            "SELECT * FROM executions WHERE session_id = 'sess1'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][4] == "NQ"  # symbol
        writer.close()


# ---------------------------------------------------------------------------
# StateStore tests (SQLite)
# ---------------------------------------------------------------------------

class TestStateStore:
    def test_session_upsert(self) -> None:
        store = StateStore(":memory:")
        store.upsert_session("sess1", bar_count=10, cvd=100.0)
        row = store.get_session("sess1")
        assert row is not None
        assert row["bar_count"] == 10
        assert row["cvd"] == 100.0

        # Update
        store.upsert_session("sess1", bar_count=20, cvd=200.0)
        row = store.get_session("sess1")
        assert row["bar_count"] == 20
        assert row["cvd"] == 200.0
        store.close()

    def test_session_not_found(self) -> None:
        store = StateStore(":memory:")
        assert store.get_session("nonexistent") is None
        store.close()

    def test_survives_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "state.db"

            store = StateStore(db_path)
            store.upsert_session("sess1", bar_count=42, cvd=999.0)
            store.close()

            store2 = StateStore(db_path)
            row = store2.get_session("sess1")
            assert row is not None
            assert row["bar_count"] == 42
            assert row["cvd"] == 999.0
            store2.close()

    def test_paper_gate_upsert(self) -> None:
        store = StateStore(":memory:")
        store.upsert_paper_gate(
            session_count=5, cumulative_pnl=1500.0,
            max_drawdown=-200.0, win_rate=0.65,
        )
        row = store.get_paper_gate()
        assert row is not None
        assert row["session_count"] == 5
        assert row["cumulative_pnl"] == 1500.0
        assert row["promoted"] == 0
        store.close()
