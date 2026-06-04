"""Tests for ResultsWriter — DuckDB + Obsidian vault output."""
from __future__ import annotations

import json
import os
import tempfile

import duckdb
import pytest
import yaml

from deep6.backtest.discovery_schema import create_discovery_db
from deep6.backtest.results_writer import ResultsWriter


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture()
def env(tmp_path):
    """Provide a temporary DuckDB + vault environment."""
    db_path = str(tmp_path / "test.duckdb")
    vault_path = tmp_path / "vault"
    brain_dir = vault_path / "brain"
    brain_dir.mkdir(parents=True)

    # Seed brain index with realistic content
    brain_index = """\
---
id: brain-backtest-loop
type: index
status: active
date: 2026-05-23
project: deep6
domain: backtesting
tags: [type/index, project/deep6, domain/backtesting]
---

# Backtest Loop — Hermes Persistent Memory

## Current Status

- **Iteration count**: 0

## Iteration Log

| Iter # | Date | Strategy Hash | IS WR | OOS WR | Fitness | Notes |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | No iterations run yet |

## Parameter Insights

- No parameter insights yet.
"""
    (brain_dir / "Backtest-Loop.md").write_text(brain_index, encoding="utf-8")

    # Create DuckDB with schema
    conn = create_discovery_db(db_path)
    conn.close()

    return {
        "db_path": db_path,
        "vault_path": str(vault_path),
        "writer": ResultsWriter(db_path, str(vault_path)),
    }


def _make_iteration_data(**overrides) -> dict:
    """Build a valid iteration_data dict with sensible defaults."""
    base = {
        "strategy_hash": "abc12345def67890",
        "config": {"level_target": "LVN", "entry_offset": 2},
        "is_win_rate": 0.60,
        "is_avg_rr": 2.0,
        "is_profit_factor": 3.0,
        "is_max_dd": 100.0,
        "oos_win_rate": 0.55,
        "oos_avg_rr": 1.5,
        "oos_profit_factor": 2.0,
        "oos_max_dd": 50.0,
        "is_trade_count": 40,
        "oos_trade_count": 15,
        "status": "completed",
        "fitness_passed": True,
        "mutation_type": "RANDOM",
    }
    base.update(overrides)
    return base


# ── DuckDB tests ───────────────────────────────────────────────────────


class TestWriteIteration:
    def test_roundtrip(self, env):
        rw = env["writer"]
        data = _make_iteration_data()
        row_id = rw.write_iteration(data)

        assert row_id > 0

        conn = duckdb.connect(env["db_path"])
        row = conn.execute(
            "SELECT strategy_hash, is_win_rate, is_avg_rr, fitness_passed "
            "FROM iterations WHERE id = ?",
            [row_id],
        ).fetchone()
        conn.close()

        assert row[0] == "abc12345def67890"
        assert abs(row[1] - 0.60) < 0.001
        assert abs(row[2] - 2.0) < 0.001
        assert row[3] is True

    def test_multiple_iterations_get_distinct_ids(self, env):
        rw = env["writer"]
        id1 = rw.write_iteration(_make_iteration_data(strategy_hash="hash_a"))
        id2 = rw.write_iteration(_make_iteration_data(strategy_hash="hash_b"))
        assert id1 != id2

    def test_parent_iteration_id(self, env):
        rw = env["writer"]
        parent_id = rw.write_iteration(_make_iteration_data(strategy_hash="parent"))
        child_id = rw.write_iteration(
            _make_iteration_data(strategy_hash="child", parent_iteration_id=parent_id)
        )

        conn = duckdb.connect(env["db_path"])
        row = conn.execute(
            "SELECT parent_iteration_id FROM iterations WHERE id = ?", [child_id]
        ).fetchone()
        conn.close()
        assert row[0] == parent_id


class TestWriteTrades:
    def test_trades_inserted(self, env):
        rw = env["writer"]
        iter_id = rw.write_iteration(_make_iteration_data())
        trades = [
            {
                "split": "is",
                "date": "2026-01-15",
                "direction": "LONG",
                "entry_price": 21000.0,
                "exit_price": 21050.0,
                "pnl": 50.0,
                "exit_reason": "target",
                "bars_held": 5,
                "entry_time": "09:30:00",
                "exit_time": "09:35:00",
            },
            {
                "split": "oos",
                "date": "2026-03-10",
                "direction": "SHORT",
                "entry_price": 21100.0,
                "exit_price": 21080.0,
                "pnl": 20.0,
                "exit_reason": "target",
                "bars_held": 3,
            },
        ]
        rw.write_trades(iter_id, trades)

        conn = duckdb.connect(env["db_path"])
        rows = conn.execute(
            "SELECT iteration_id, split, direction, pnl, commission FROM trades "
            "WHERE iteration_id = ? ORDER BY date",
            [iter_id],
        ).fetchall()
        conn.close()

        assert len(rows) == 2
        assert rows[0][1] == "is"
        assert rows[0][2] == "LONG"
        assert abs(rows[0][3] - 50.0) < 0.01
        assert abs(rows[0][4] - 4.12) < 0.01

    def test_empty_trades_noop(self, env):
        rw = env["writer"]
        iter_id = rw.write_iteration(_make_iteration_data())
        rw.write_trades(iter_id, [])  # Should not raise


class TestUpsertStrategy:
    def test_insert_new(self, env):
        rw = env["writer"]
        rw.upsert_strategy("hash_x", '{"a":1}', 0, None, None, 0.8, 0.7)

        conn = duckdb.connect(env["db_path"])
        row = conn.execute(
            "SELECT times_tested, best_is_fitness, best_oos_fitness FROM strategies "
            "WHERE hash = 'hash_x'"
        ).fetchone()
        conn.close()

        assert row[0] == 1
        assert abs(row[1] - 0.8) < 0.001
        assert abs(row[2] - 0.7) < 0.001

    def test_update_existing_bumps_count(self, env):
        rw = env["writer"]
        rw.upsert_strategy("hash_y", '{"a":1}', 0, None, None, 0.5, 0.4)
        rw.upsert_strategy("hash_y", '{"a":1}', 0, None, None, 0.9, 0.3)

        conn = duckdb.connect(env["db_path"])
        row = conn.execute(
            "SELECT times_tested, best_is_fitness, best_oos_fitness FROM strategies "
            "WHERE hash = 'hash_y'"
        ).fetchone()
        conn.close()

        assert row[0] == 2
        assert abs(row[1] - 0.9) < 0.001  # Updated to higher
        assert abs(row[2] - 0.4) < 0.001  # Kept previous higher

    def test_lineage_fields(self, env):
        rw = env["writer"]
        rw.upsert_strategy("child_h", '{}', 2, "parent_h", "SHIFT", 0.6, 0.5)

        conn = duckdb.connect(env["db_path"])
        row = conn.execute(
            "SELECT generation, parent_hash, mutation_type FROM strategies "
            "WHERE hash = 'child_h'"
        ).fetchone()
        conn.close()

        assert row[0] == 2
        assert row[1] == "parent_h"
        assert row[2] == "SHIFT"


# ── Obsidian tests ─────────────────────────────────────────────────────


def _parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content."""
    lines = content.split("\n")
    in_fm = False
    fm_lines = []
    for line in lines:
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm:
            fm_lines.append(line)
    return yaml.safe_load("\n".join(fm_lines))


class TestWriteBacktestResult:
    def test_creates_file_with_valid_frontmatter(self, env):
        rw = env["writer"]
        data = {
            "strategy_hash": "abc12345def",
            "config": {"level_target": "LVN"},
            "is_metrics": {
                "win_rate": 0.60, "avg_rr": 2.0, "profit_factor": 3.0,
                "trade_count": 40, "total_pnl": 500, "max_drawdown": 100,
            },
            "oos_metrics": {
                "win_rate": 0.55, "avg_rr": 1.5, "profit_factor": 2.0,
                "trade_count": 15, "total_pnl": 200, "max_drawdown": 50,
            },
            "fitness_passed": True,
            "mutation_type": "RANDOM",
        }
        fpath = rw.write_backtest_result(1, data)

        assert os.path.exists(fpath)
        content = open(fpath, encoding="utf-8").read()
        fm = _parse_frontmatter(content)

        assert fm["type"] == "backtest-iteration"
        assert fm["project"] == "deep6"
        assert fm["fitness_passed"] == "true" or fm["fitness_passed"] is True
        assert fm["strategy_hash"] == "abc12345def"
        assert "type/backtest-iteration" in fm["tags"]

    def test_failed_iteration_has_correct_status(self, env):
        rw = env["writer"]
        data = {
            "strategy_hash": "fail_hash",
            "config": {},
            "is_metrics": {"win_rate": 0.40},
            "oos_metrics": {"win_rate": 0.30},
            "fitness_passed": False,
            "rejection_reasons": ["IS WR < 55%", "OOS WR < 55%"],
        }
        fpath = rw.write_backtest_result(2, data)
        content = open(fpath, encoding="utf-8").read()
        fm = _parse_frontmatter(content)

        assert fm["status"] == "failed"
        assert "FAILED" in content
        assert "IS WR < 55%" in content

    def test_creates_directory_if_missing(self, env):
        rw = env["writer"]
        fpath = rw.write_backtest_result(1, {
            "strategy_hash": "test", "config": {},
            "is_metrics": {}, "oos_metrics": {}, "fitness_passed": False,
        })
        assert os.path.exists(fpath)


class TestWriteFinding:
    def test_creates_finding_file(self, env):
        rw = env["writer"]
        data = {
            "slug": "lvn-reversal",
            "title": "LVN levels produce higher R:R reversals",
            "description": "Backtesting shows LVN targets yield 2.1 avg R:R vs 1.4 for HVN.",
            "evidence": "40 IS trades, 15 OOS trades",
            "pattern": "Use level_target=LVN for reversal setups",
            "confidence": "high",
            "source_session": "hermes-backtest-001",
        }
        fpath = rw.write_finding(data)

        assert os.path.exists(fpath)
        content = open(fpath, encoding="utf-8").read()
        fm = _parse_frontmatter(content)

        assert fm["type"] == "finding"
        assert fm["confidence"] == "high"
        assert "LVN levels produce" in content
        assert "domain/backtesting" in fm["tags"]


class TestWriteStrategyHypothesis:
    def test_creates_strategy_file(self, env):
        rw = env["writer"]
        fpath = rw.write_strategy_hypothesis(
            "abc12345", {"level_target": "LVN"}, 0, None, None,
        )
        assert os.path.exists(fpath)
        content = open(fpath, encoding="utf-8").read()
        fm = _parse_frontmatter(content)

        assert fm["type"] == "strategy-hypothesis"
        assert fm["status"] == "testing"
        assert fm["generation"] == 0
        assert "abc12345" in content

    def test_idempotent_no_overwrite(self, env):
        rw = env["writer"]
        fpath1 = rw.write_strategy_hypothesis("same_hash", {}, 0, None, None)

        # Modify the file to prove it won't be overwritten
        with open(fpath1, "a", encoding="utf-8") as f:
            f.write("\n## MANUAL EDIT\n")

        fpath2 = rw.write_strategy_hypothesis("same_hash", {"new": True}, 1, "p", "SHIFT")
        assert fpath1 == fpath2

        content = open(fpath2, encoding="utf-8").read()
        assert "MANUAL EDIT" in content  # Original content preserved

    def test_with_lineage(self, env):
        rw = env["writer"]
        fpath = rw.write_strategy_hypothesis(
            "child123", {"x": 1}, 3, "parent99", "SHIFT",
        )
        content = open(fpath, encoding="utf-8").read()
        fm = _parse_frontmatter(content)

        assert fm["generation"] == 3
        assert fm["parent_hash"] == "parent99"
        assert fm["mutation_type"] == "SHIFT"


class TestUpdateBrainIndex:
    def test_appends_row_replacing_placeholder(self, env):
        rw = env["writer"]
        data = _make_iteration_data()
        rw.update_brain_index(1, data)

        brain = (env["writer"].vault_path / "brain" / "Backtest-Loop.md").read_text(
            encoding="utf-8"
        )
        assert "No iterations run yet" not in brain
        assert "| 1 |" in brain
        assert "abc12345" in brain  # First 8 chars of hash
        assert "60.0%" in brain

    def test_appends_multiple_rows(self, env):
        rw = env["writer"]
        rw.update_brain_index(1, _make_iteration_data(strategy_hash="hash_aaa"))
        rw.update_brain_index(2, _make_iteration_data(strategy_hash="hash_bbb"))

        brain = rw.read_brain_index()
        assert "| 1 |" in brain
        assert "| 2 |" in brain
        assert "hash_aaa" in brain
        assert "hash_bbb" in brain

    def test_missing_brain_file_noop(self, env):
        rw = env["writer"]
        brain_path = rw.vault_path / "brain" / "Backtest-Loop.md"
        brain_path.unlink()
        rw.update_brain_index(1, _make_iteration_data())  # Should not raise


class TestReadBrainIndex:
    def test_returns_content(self, env):
        content = env["writer"].read_brain_index()
        assert "Backtest Loop" in content
        assert "## Iteration Log" in content

    def test_missing_file_returns_fallback(self, env):
        rw = env["writer"]
        brain_path = rw.vault_path / "brain" / "Backtest-Loop.md"
        brain_path.unlink()
        assert rw.read_brain_index() == "No brain index found."
