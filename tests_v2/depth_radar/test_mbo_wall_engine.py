from __future__ import annotations

import pandas as pd

from deep6.data.databento_live import _ACTION_ADD, _ACTION_CANCEL, _SIDE_ASK, _SIDE_BID
from deep6.ml.depth_radar.mbo_wall_engine import MBOWallEngine


RTH_TS = pd.Timestamp("2026-04-10 14:00:00", tz="UTC")


def _seed_dom(engine: MBOWallEngine, ts: pd.Timestamp = RTH_TS) -> None:
    engine.process_event(_ACTION_ADD, _SIDE_BID, 1, 19999.75, 1, ts)
    engine.process_event(_ACTION_ADD, _SIDE_ASK, 2, 20000.25, 1, ts)


def _add_wall(
    engine: MBOWallEngine,
    order_id: int = 100,
    price: float = 20000.0,
    size: int = 100,
    side: str = _SIDE_BID,
    ts: pd.Timestamp = RTH_TS,
) -> None:
    engine.process_event(_ACTION_ADD, side, order_id, price, size, ts)


def test_engine_init() -> None:
    engine = MBOWallEngine()

    assert engine.active_count == 0
    assert engine.get_active_walls() == []
    assert engine.get_completed_episodes() == []
    assert engine.last_timestamp is None


def test_process_single_add() -> None:
    engine = MBOWallEngine()

    _add_wall(engine)

    assert engine.active_count == 1


def test_wall_detection() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine)

    walls = engine.get_active_walls()

    assert any(w["price"] == 20000.0 for w in walls)


def test_sub_threshold_ignored() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine, size=49)

    walls = engine.get_active_walls()

    assert not any(w["price"] == 20000.0 for w in walls)


def test_cancel_retires_wall() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine, order_id=101)
    engine.process_event(_ACTION_CANCEL, _SIDE_BID, 101, 20000.0, 0, RTH_TS)

    completed = engine.flush_all()

    assert any(ep.price == 20000.0 for ep in completed)


def test_get_active_walls_features() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine)

    wall = next(w for w in engine.get_active_walls() if w["price"] == 20000.0)

    assert {"episode_id", "price", "side", "size", "intent", "state"}.issubset(wall)


def test_flush_all() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine, order_id=201, price=20000.0, size=100)
    _add_wall(engine, order_id=202, price=20000.25, size=100, side=_SIDE_ASK)

    completed = engine.flush_all()

    assert completed
    assert any(ep.price == 20000.0 for ep in completed)


def test_reset() -> None:
    engine = MBOWallEngine()
    _seed_dom(engine)
    _add_wall(engine)

    engine.reset()

    assert engine.active_count == 0
    assert engine.get_active_walls() == []
    assert engine.get_completed_episodes() == []
    assert engine.last_timestamp is None


def test_non_rth_ignored() -> None:
    engine = MBOWallEngine()
    ts = pd.Timestamp("2026-04-10 12:00:00", tz="UTC")

    _add_wall(engine, ts=ts)

    assert engine.active_count == 0
    assert engine.get_active_walls() == []
