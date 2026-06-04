import pytest

from deep6.backtest.discovery_schema import (
    create_discovery_db,
    get_best_strategies,
    get_iteration_history,
    strategy_already_tested,
)


def test_create_discovery_db_memory_works():
    db = create_discovery_db(":memory:")
    tables = db.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name").fetchall()
    assert tables == [("iterations",), ("strategies",), ("trades",)]


def test_insert_iteration_and_select_back():
    db = create_discovery_db(":memory:")
    db.execute(
        "INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'abc123', '{}', 'completed')"
    )
    row = db.execute("SELECT id, timestamp, strategy_hash, config_json, status FROM iterations").fetchone()
    assert row == (1, "2026-01-01", "abc123", "{}", "completed")


def test_invalid_iteration_status_rejected():
    db = create_discovery_db(":memory:")
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'x', '{}', 'INVALID')"
        )


def test_invalid_trade_split_rejected():
    db = create_discovery_db(":memory:")
    db.execute("INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'x', '{}', 'completed')")
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO trades (id, iteration_id, split) VALUES (1, 1, 'bad')"
        )


def test_strategy_already_tested_returns_expected_boolean():
    db = create_discovery_db(":memory:")
    assert strategy_already_tested(db, "abc") is False
    db.execute("INSERT INTO strategies (hash, config_json) VALUES ('abc', '{}')")
    assert strategy_already_tested(db, "abc") is True


def test_get_best_strategies_sorted_by_best_oos_fitness():
    db = create_discovery_db(":memory:")
    db.execute("INSERT INTO strategies (hash, config_json, best_oos_fitness, times_tested) VALUES ('a', '{}', 0.2, 1)")
    db.execute("INSERT INTO strategies (hash, config_json, best_oos_fitness, times_tested) VALUES ('b', '{}', 0.9, 2)")
    db.execute("INSERT INTO strategies (hash, config_json, best_oos_fitness, times_tested) VALUES ('c', '{}', 0.5, 3)")
    rows = get_best_strategies(db, 3)
    assert [r[0] for r in rows] == ["b", "c", "a"]


def test_get_iteration_history_ordered():
    db = create_discovery_db(":memory:")
    db.execute("INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (2, '2026-01-02', 'b', '{}', 'completed')")
    db.execute("INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'a', '{}', 'running')")
    rows = get_iteration_history(db)
    assert [r[0] for r in rows] == [1, 2]
