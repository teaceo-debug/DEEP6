"""Integration test for the full-scorer ReplaySession wiring (phase 13-02).

Verifies that:
  1. ReplaySession._close_bar routes through classify_bar + score_bar and
     persists scorer-derived tier labels (not just TIER_3/NONE).
  2. When the scorer returns TYPE_A / TYPE_B, a corresponding row lands in
     backtest_trades with the correct entry_price and side.

Because crafting a synthetic MBO stream that genuinely triggers a
multi-category TYPE_A signal is brittle (scorer gates include
min_strength, delta-agreement, 4+ categories, zone proximity, etc.), we
force the scorer to return TYPE_A via monkey-patching on the
deep6.backtest.session.score_bar binding. This isolates the wiring under
test from the downstream scoring thresholds, which are exercised by the
dedicated scorer tests under tests/scoring/.

A second test exercises the pipeline end-to-end without monkey-patching
to confirm no engine raises and that tier-column values come from the
scorer's SignalTier enum names (QUIET is the expected default for
synthetic low-signal flow).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

import deep6.backtest.session as session_mod
from deep6.backtest.config import BacktestConfig
from deep6.backtest.session import ReplaySession
from deep6.config import Config
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.state.shared import SharedState
from tests.backtest.conftest import FakeMBOEvent


# -------------------------------------------------------------------------
# Helpers (mirror test_replay_session.py)
# -------------------------------------------------------------------------

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
              size: int, instrument_id: int = 1) -> FakeMBOEvent:
    return FakeMBOEvent(
        ts_event=ts_ns,
        action=action,
        side=side,
        price=int(round(price_dollars * 1e9)),
        size=size,
        instrument_id=instrument_id,
    )


def _synthetic_stream(base_ns: int, n_bars: int = 3) -> list[FakeMBOEvent]:
    """Minimal multi-bar stream — seeds a book and generates trade flow."""
    events: list[FakeMBOEvent] = []
    step_ns = 100_000_000
    t = base_ns
    mid = 21000.0

    # Seed a 10-level book on both sides.
    for i in range(10):
        events.append(_mk_event(t, "A", "B", mid - (i + 1) * 0.25, 50))
        t += step_ns
        events.append(_mk_event(t, "A", "A", mid + (i + 1) * 0.25, 50))
        t += step_ns

    for bar_idx in range(n_bars):
        # Mix of trades across the mid so FootprintBar accumulates volume
        # on multiple levels — required for POC / delta calculations.
        for i in range(20):
            price = mid + (0.25 if i % 3 == 0 else -0.25 if i % 3 == 1 else 0.0)
            events.append(_mk_event(t, "T", "A" if i % 2 == 0 else "B", price, 5))
            t += step_ns
        # Jump forward to next bar boundary.
        t = base_ns + (bar_idx + 1) * 60_000_000_000 + step_ns

    # Trailing tick to flush the final bar.
    events.append(_mk_event(
        base_ns + n_bars * 60_000_000_000 + 5_000_000_000,
        "T", "A", mid, 5,
    ))
    return events


# -------------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replay_writes_scorer_tier_column(tmp_path: Path) -> None:
    """Full pipeline runs without error; tier values come from SignalTier names."""
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
    stream = _synthetic_stream(base_ns, n_bars=3)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        run_id = s.run_id

    con = duckdb.connect(cfg.duckdb_path)
    rows = con.execute(
        "SELECT tier, score, direction FROM backtest_bars WHERE run_id = ?",
        [run_id],
    ).fetchall()
    con.close()

    assert len(rows) > 0, "replay wrote zero bars"
    valid_tiers = {"QUIET", "TYPE_A", "TYPE_B", "TYPE_C", "TIER_3", "DISQUALIFIED"}
    for tier, score, direction in rows:
        assert tier in valid_tiers, f"unexpected tier={tier!r}"
        assert direction in {"LONG", "SHORT", "NONE"}
        assert score is not None


@pytest.mark.asyncio
async def test_forced_type_a_produces_trade_row(tmp_path: Path, monkeypatch) -> None:
    """Monkey-patch score_bar → TYPE_A; verify trade row lands in backtest_trades."""
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
    stream = _synthetic_stream(base_ns, n_bars=3)

    # Force every scored bar into TYPE_A LONG so the sim-fill hook fires.
    def _fake_score_bar(*args, **kwargs) -> ScorerResult:
        return ScorerResult(
            total_score=85.0,
            tier=SignalTier.TYPE_A,
            direction=+1,
            engine_agreement=1.0,
            category_count=5,
            confluence_mult=1.25,
            zone_bonus=8.0,
            narrative=NarrativeType.ABSORPTION,
            label="TYPE A — FORCED",
            categories_firing=["absorption", "delta", "imbalance", "auction", "volume_profile"],
        )
    monkeypatch.setattr(session_mod, "score_bar", _fake_score_bar)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        run_id = s.run_id
        trades_written = s.trades_written
        scorer_fires = s.scorer_signal_fires

    assert scorer_fires > 0, "scorer_signal_fires did not increment despite forced TYPE_A"
    assert trades_written > 0, "no trades written despite forced TYPE_A"

    con = duckdb.connect(cfg.duckdb_path)
    bar_rows = con.execute(
        "SELECT tier, score, direction FROM backtest_bars "
        "WHERE run_id = ? AND tier NOT IN ('QUIET', 'TIER_3', 'DISQUALIFIED')",
        [run_id],
    ).fetchall()
    trade_rows = con.execute(
        "SELECT side, entry_price, exit_price, pnl, tier, fill_model "
        "FROM backtest_trades WHERE run_id = ?",
        [run_id],
    ).fetchall()
    con.close()

    assert len(bar_rows) > 0, "backtest_bars has no non-TIER_3 rows"
    for tier, score, direction in bar_rows:
        assert tier == "TYPE_A"
        assert direction == "LONG"
        assert score == pytest.approx(85.0)

    assert len(trade_rows) == trades_written
    for side, entry_price, exit_price, pnl, tier, fill_model in trade_rows:
        assert side == "LONG"
        assert entry_price > 0
        # Phase 13-03: trades are either bracket-resolved or flushed as
        # TRUNCATED on session exit — exit_price is always populated.
        assert exit_price is not None
        assert tier == "TYPE_A"
        assert fill_model == "perfect"


@pytest.mark.asyncio
async def test_forced_type_b_short_emits_short_trade(tmp_path: Path, monkeypatch) -> None:
    """TYPE_B SHORT also populates backtest_trades (side='SHORT')."""
    state = _build_state(tmp_path)
    cfg = BacktestConfig(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 9, 13, 33, tzinfo=timezone.utc),
        duckdb_path=str(tmp_path / "r.duckdb"),
        tf_list=["1m"],
    )
    base_ns = int(cfg.start.timestamp() * 1e9)
    stream = _synthetic_stream(base_ns, n_bars=2)

    def _fake_score_bar(*args, **kwargs) -> ScorerResult:
        return ScorerResult(
            total_score=74.0,
            tier=SignalTier.TYPE_B,
            direction=-1,
            engine_agreement=0.8,
            category_count=4,
            confluence_mult=1.0,
            zone_bonus=6.0,
            narrative=NarrativeType.EXHAUSTION,
            label="TYPE B — FORCED",
            categories_firing=["exhaustion", "delta", "imbalance", "auction"],
        )
    monkeypatch.setattr(session_mod, "score_bar", _fake_score_bar)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        run_id = s.run_id

    con = duckdb.connect(cfg.duckdb_path)
    sides = con.execute(
        "SELECT DISTINCT side FROM backtest_trades WHERE run_id = ?", [run_id]
    ).fetchall()
    tier_vals = con.execute(
        "SELECT DISTINCT tier FROM backtest_trades WHERE run_id = ?", [run_id]
    ).fetchall()
    con.close()

    assert sides == [("SHORT",)]
    assert tier_vals == [("TYPE_B",)]


@pytest.mark.asyncio
async def test_type_c_does_not_produce_trade(tmp_path: Path, monkeypatch) -> None:
    """TYPE_C is alert-only — must NOT insert into backtest_trades."""
    state = _build_state(tmp_path)
    cfg = BacktestConfig(
        dataset="GLBX.MDP3",
        symbol="NQ.c.0",
        start=datetime(2026, 4, 9, 13, 30, tzinfo=timezone.utc),
        end=datetime(2026, 4, 9, 13, 33, tzinfo=timezone.utc),
        duckdb_path=str(tmp_path / "r.duckdb"),
        tf_list=["1m"],
    )
    base_ns = int(cfg.start.timestamp() * 1e9)
    stream = _synthetic_stream(base_ns, n_bars=2)

    def _fake_score_bar(*args, **kwargs) -> ScorerResult:
        return ScorerResult(
            total_score=55.0,
            tier=SignalTier.TYPE_C,
            direction=+1,
            engine_agreement=0.6,
            category_count=4,
            confluence_mult=1.0,
            zone_bonus=0.0,
            narrative=NarrativeType.MOMENTUM,
            label="TYPE C — FORCED",
            categories_firing=["delta", "auction", "imbalance", "poc"],
        )
    monkeypatch.setattr(session_mod, "score_bar", _fake_score_bar)

    async with ReplaySession(cfg, state, event_source=iter(stream)) as s:
        await s.run()
        run_id = s.run_id
        trades_written = s.trades_written

    assert trades_written == 0

    con = duckdb.connect(cfg.duckdb_path)
    trade_count = con.execute(
        "SELECT COUNT(*) FROM backtest_trades WHERE run_id = ?", [run_id]
    ).fetchone()[0]
    con.close()
    assert trade_count == 0
