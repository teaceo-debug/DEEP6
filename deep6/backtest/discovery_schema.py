import os

import duckdb


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS iterations (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    strategy_hash TEXT NOT NULL,
    config_json TEXT NOT NULL,
    is_win_rate REAL,
    is_avg_rr REAL,
    is_profit_factor REAL,
    is_max_dd REAL,
    oos_win_rate REAL,
    oos_avg_rr REAL,
    oos_profit_factor REAL,
    oos_max_dd REAL,
    is_trade_count INTEGER,
    oos_trade_count INTEGER,
    status TEXT CHECK(status IN ('running','completed','failed','rejected')),
    parent_iteration_id INTEGER REFERENCES iterations(id),
    fitness_passed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    iteration_id INTEGER REFERENCES iterations(id),
    split TEXT CHECK(split IN ('is','oos')),
    date TEXT,
    direction TEXT CHECK(direction IN ('LONG','SHORT')),
    entry_price REAL,
    exit_price REAL,
    pnl REAL,
    exit_reason TEXT,
    bars_held INTEGER,
    entry_time TEXT,
    exit_time TEXT,
    commission REAL DEFAULT 4.12
);

CREATE TABLE IF NOT EXISTS strategies (
    hash TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    generation INTEGER DEFAULT 0,
    parent_hash TEXT,
    mutation_type TEXT,
    best_is_fitness REAL,
    best_oos_fitness REAL,
    first_seen TEXT,
    last_seen TEXT,
    times_tested INTEGER DEFAULT 1
);
"""


def create_discovery_db(path: str) -> duckdb.DuckDBPyConnection:
    """Create or connect to the discovery DuckDB database."""
    if path != ":memory:":
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    conn = duckdb.connect(path)
    conn.execute(SCHEMA_SQL)
    return conn


def get_best_strategies(conn: duckdb.DuckDBPyConnection, n: int = 5) -> list:
    """Return top N strategies by best OOS fitness."""
    return conn.execute(
        "SELECT hash, config_json, best_oos_fitness, times_tested FROM strategies "
        "WHERE best_oos_fitness IS NOT NULL ORDER BY best_oos_fitness DESC LIMIT ?", [n]
    ).fetchall()


def get_iteration_history(conn: duckdb.DuckDBPyConnection) -> list:
    """Return all iterations ordered by id."""
    return conn.execute(
        "SELECT id, timestamp, strategy_hash, status, fitness_passed, "
        "is_win_rate, oos_win_rate, is_avg_rr, oos_avg_rr FROM iterations ORDER BY id"
    ).fetchall()


def strategy_already_tested(conn: duckdb.DuckDBPyConnection, strategy_hash: str) -> bool:
    """Check if a strategy with this hash has already been tested."""
    result = conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE hash = ?", [strategy_hash]
    ).fetchone()
    return result[0] > 0


DEFAULT_DB_PATH = "data/backtests/discovery_loop.duckdb"
