"""ReplaySession end-to-end integration test.

Phase 13-01 T-13-01-10. Exercises the full pipeline:

    synthetic MBO iterator → MBOAdapter → ReplaySession → DuckDB

Critical acceptance gate (from plan + phase 13 CONTEXT):
  - backtest_bars row count > 0 after replay
  - at least one DOM-dependent signal (E2 / E3 / E4) fires at least once
    during the replay (previously impossible with trades-only
    databento_feed.py)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

from deep6.backtest.clock import WallClock
from deep6.backtest.config import BacktestConfig
from deep6.backtest.session import ReplaySession
from deep6.config import Config
from deep6.state.shared import SharedState


def _build_state(tmp_db: Path) -> SharedState:
    cfg = Config(
        rithmic_user="",
        rithmic_password="",
        rithmic_system_name="",
        rithmic_uri="",
        db_path=str(tmp_db / "session.sqlite"),
    )
    return SharedState.build(cfg)


def _mk_event(ts_ns: int, action: str, side: str, price_dollars: float,
              size: int, instrument_id: int = 1):
    from tests.backtest.conftest import FakeMBOEvent
    return FakeMBOEvent(
        ts_event=ts_ns,
        action=action,
        side=side,
        price=int(round(price_dollars * 1e9)),
        size=size,
        instrument_id=instrument_id,
    )


def _rth_stream(base_ns: int, n_bars: int = 3) -> list:
    """Emit synthetic RTH MBO events spanning n_bars * 60s.

    Each minute carries:
      - a dense book build-up (A events both sides)
      - a sequence of trades  (T events)
      - a mid-minute cancel burst on the bid side (C events) to trigger
        E2 (imbalance) and give E3 a W1 anomaly to see
      - additional refill A events to give E4 a synthetic-refill pattern
    """
    events: list = []
    step_ns = 100_000_000  # 100ms between events
    t = base_ns
    mid_price = 21000.0

    # Seed a 10-level book on both sides — required so TrespassEngine has
    # something to read.
    for i in range(10):
        events.append(_mk_event(t, "A", "B", mid_price - (i + 1) * 0.25, 50))
        t += step_ns
        events.append(_mk_event(t, "A", "A", mid_price + (i + 1) * 0.25, 50))
        t += step_ns

    for bar_idx in range(n_bars):
        # Pull ask-side liquidity — creates strong bid-side imbalance →
        # TrespassEngine direction != 0.
        for i in range(3):
            events.append(_mk_event(t, "C", "A", mid_price + (i + 1) * 0.25, 40))
            t += step_ns

        # Add back to bid side (refill pattern that exercises E4).
        for i in range(3):
            events.append(_mk_event(t, "A", "B", mid_price - (i + 1) * 0.25, 80))
            t += step_ns

        # A burst of cancels on the bid side (drives W1 for E3).
        for i in range(5):
            events.append(_mk_event(t, "C", "B", mid_price - (i + 1) * 0.25, 30))
            t += step_ns

        # Replenish the bids (synthetic iceberg refill).
        for i in range(5):
            events.append(_mk_event(t, "A", "B", mid_price - (i + 1) * 0.25, 30))
            t += step_ns

        # A handful of trades so bars have volume to finalize.
        for i in range(10):
            side = "A" if i % 2 == 0 else "B"
            events.append(_mk_event(t, "T", side, mid_price, 5))
            t += step_ns

        # Jump forward one full minute so the next event triggers bar close.
        t = base_ns + (bar_idx + 1) * 60_000_000_000 + step_ns

    # Final tick firmly inside the last-bar+1 boundary to flush the final bar.
    events.append(
        _mk_event(base_ns + n_bars * 60_000_000_000 + 5_000_000_000,
                  "T", "A", mid_price, 5)
    )
    return events


@pytest.mark.asyncio
async def test_replay_produces_bars(tmp_path: Path) -> None:
    state = _build_state(tmp_path)
    cfg = BacktestConfig(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 9, 13, 35, tzinfo=timezone.utc),
        duckdb_path=str(tmp_path / "r.duckdb"),
        tf_list=["1m"],
    )
    base_ns = int(cfg.start.timestamp() * 1e9)
    stream = _rth_stream(base_ns, n_bars=3)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        run_id = s.run_id

    con = duckdb.connect(cfg.duckdb_path)
    n = con.execute(
        "SELECT COUNT(*) FROM backtest_bars WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    con.close()
    assert n > 0, f"replay produced 0 bars in backtest_bars (run_id={run_id})"


@pytest.mark.asyncio
async def test_dom_signals_fire_in_replay(tmp_path: Path) -> None:
    """Marquee phase-13 acceptance gate.

    At least one of E2/E3/E4 must fire during replay. Previously
    impossible with trades-only databento_feed.py.
    """
    state = _build_state(tmp_path)
    cfg = BacktestConfig(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 9, 13, 40, tzinfo=timezone.utc),
        duckdb_path=str(tmp_path / "r.duckdb"),
        tf_list=["1m"],
    )
    base_ns = int(cfg.start.timestamp() * 1e9)
    stream = _rth_stream(base_ns, n_bars=5)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        fires = s.dom_signal_fires
        run_id = s.run_id

    assert fires > 0, "No DOM-dependent signal (E2/E3/E4) fired during replay"

    con = duckdb.connect(cfg.duckdb_path)
    n_flagged = con.execute(
        "SELECT COUNT(*) FROM backtest_bars "
        "WHERE run_id = ? AND signal_flags <> 0",
        [run_id],
    ).fetchone()[0]
    con.close()
    assert n_flagged > 0, "No bar row carries a non-zero signal_flags mask"


def test_wallclock_default_preserved(tmp_path: Path) -> None:
    """SharedState.clock is WallClock by default (regression guard)."""
    state = _build_state(tmp_path)
    assert isinstance(state.clock, WallClock)
