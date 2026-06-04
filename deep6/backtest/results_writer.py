"""ResultsWriter — writes backtest iteration results to DuckDB and Obsidian vault.

Dual-output writer for the Hermes backtest discovery loop:
  - DuckDB: iteration metrics, individual trades, strategy lineage
  - Obsidian: human-readable markdown files matching vault templates

DuckDB methods are synchronous (DuckDB driver is sync). Each method opens
and closes its own connection — callers don't need a context manager.

Obsidian methods write markdown files with YAML frontmatter to the trading
vault. Directories are created on demand via mkdir(parents=True).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import structlog

log = structlog.get_logger(__name__)


class ResultsWriter:
    """Writes backtest results to DuckDB and Obsidian vault."""

    def __init__(self, db_path: str, vault_path: str) -> None:
        self.db_path = db_path
        self.vault_path = Path(vault_path)

    # ── DuckDB methods ──────────────────────────────────────────────────

    def write_iteration(self, iteration_data: dict) -> int:
        """Insert iteration into iterations table.

        Args:
            iteration_data: Dict with keys matching iterations schema:
                strategy_hash, config (dict), is_win_rate, is_avg_rr,
                is_profit_factor, is_max_dd, oos_win_rate, oos_avg_rr,
                oos_profit_factor, oos_max_dd, is_trade_count, oos_trade_count,
                status, parent_iteration_id (optional), fitness_passed.

        Returns:
            The assigned iteration id.
        """
        conn = duckdb.connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            next_id: int = conn.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 FROM iterations"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO iterations "
                "(id, timestamp, strategy_hash, config_json, "
                " is_win_rate, is_avg_rr, is_profit_factor, is_max_dd, "
                " oos_win_rate, oos_avg_rr, oos_profit_factor, oos_max_dd, "
                " is_trade_count, oos_trade_count, status, "
                " parent_iteration_id, fitness_passed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    next_id,
                    now,
                    iteration_data.get("strategy_hash"),
                    json.dumps(iteration_data.get("config", {})),
                    iteration_data.get("is_win_rate"),
                    iteration_data.get("is_avg_rr"),
                    iteration_data.get("is_profit_factor"),
                    iteration_data.get("is_max_dd"),
                    iteration_data.get("oos_win_rate"),
                    iteration_data.get("oos_avg_rr"),
                    iteration_data.get("oos_profit_factor"),
                    iteration_data.get("oos_max_dd"),
                    iteration_data.get("is_trade_count", 0),
                    iteration_data.get("oos_trade_count", 0),
                    iteration_data.get("status", "completed"),
                    iteration_data.get("parent_iteration_id"),
                    iteration_data.get("fitness_passed", False),
                ],
            )
            row_id = next_id
            log.info("results_writer.write_iteration", id=row_id,
                     hash=iteration_data.get("strategy_hash"))
            return row_id
        finally:
            conn.close()

    def write_trades(self, iteration_id: int, trades: list[dict]) -> None:
        """Insert trades into trades table.

        Args:
            iteration_id: Parent iteration id from write_iteration().
            trades: List of trade dicts with keys: split, date, direction,
                entry_price, exit_price, pnl, exit_reason, bars_held,
                entry_time, exit_time.
        """
        if not trades:
            return
        conn = duckdb.connect(self.db_path)
        try:
            base_id: int = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM trades"
            ).fetchone()[0]
            rows = [
                (
                    base_id + i + 1,
                    iteration_id,
                    t.get("split", "is"),
                    t.get("date", ""),
                    t.get("direction", ""),
                    t.get("entry_price", 0),
                    t.get("exit_price", 0),
                    t.get("pnl", 0),
                    t.get("exit_reason", ""),
                    t.get("bars_held", 0),
                    str(t.get("entry_time", "")),
                    str(t.get("exit_time", "")),
                    4.12,
                )
                for i, t in enumerate(trades)
            ]
            conn.executemany(
                "INSERT INTO trades "
                "(id, iteration_id, split, date, direction, entry_price, exit_price, "
                " pnl, exit_reason, bars_held, entry_time, exit_time, commission) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            log.info("results_writer.write_trades", iteration_id=iteration_id,
                     count=len(trades))
        finally:
            conn.close()

    def upsert_strategy(
        self,
        config_hash: str,
        config_json: str,
        generation: int,
        parent_hash: str | None,
        mutation_type: str | None,
        is_fitness: float | None,
        oos_fitness: float | None,
    ) -> None:
        """Insert or update strategy in strategies table.

        On first insert: sets first_seen, last_seen, times_tested=1.
        On update: bumps times_tested, updates last_seen, keeps best fitness.
        """
        conn = duckdb.connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            existing = conn.execute(
                "SELECT hash, times_tested FROM strategies WHERE hash = ?",
                [config_hash],
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE strategies SET last_seen = ?, times_tested = times_tested + 1, "
                    "  best_is_fitness = CASE WHEN ? > best_is_fitness "
                    "    OR best_is_fitness IS NULL THEN ? ELSE best_is_fitness END, "
                    "  best_oos_fitness = CASE WHEN ? > best_oos_fitness "
                    "    OR best_oos_fitness IS NULL THEN ? ELSE best_oos_fitness END "
                    "WHERE hash = ?",
                    [now, is_fitness, is_fitness, oos_fitness, oos_fitness, config_hash],
                )
                log.info("results_writer.upsert_strategy", hash=config_hash,
                         action="update")
            else:
                conn.execute(
                    "INSERT INTO strategies "
                    "(hash, config_json, generation, parent_hash, mutation_type, "
                    " best_is_fitness, best_oos_fitness, first_seen, last_seen, times_tested) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    [
                        config_hash, config_json, generation, parent_hash,
                        mutation_type, is_fitness, oos_fitness, now, now,
                    ],
                )
                log.info("results_writer.upsert_strategy", hash=config_hash,
                         action="insert")
        finally:
            conn.close()

    # ── Obsidian methods ────────────────────────────────────────────────

    def write_backtest_result(self, iteration_number: int, iteration_data: dict) -> str:
        """Write backtest iteration result to 04-backtests/ directory.

        Produces markdown matching the backtest-iteration vault template.

        Returns:
            Absolute file path of the written note.
        """
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        strategy_hash = iteration_data.get("strategy_hash", "unknown")
        fitness = iteration_data.get("fitness_passed", False)

        filename = f"backtest-{date_str}-iter-{iteration_number:03d}.md"
        filepath = self.vault_path / "04-backtests" / filename

        is_m = iteration_data.get("is_metrics", {})
        oos_m = iteration_data.get("oos_metrics", {})
        status = "completed" if fitness else "failed"

        config_json = json.dumps(iteration_data.get("config", {}), indent=2)
        rejection_reasons = iteration_data.get("rejection_reasons", [])

        content = f"""---
id: backtest-{date_str}-iter-{iteration_number:03d}
type: backtest-iteration
status: {status}
date: {date_iso}
project: deep6
iteration_number: {iteration_number}
strategy_hash: {strategy_hash}
fitness_passed: {str(fitness).lower()}
tags: [type/backtest-iteration, project/deep6]
---

# Backtest Iteration {iteration_number}

## Strategy Config

- **Strategy hash**: {strategy_hash}
- **Mutation source**: {iteration_data.get('mutation_type', 'RANDOM (initial)')}
- **Key parameters**:

```json
{config_json}
```

## IS Results

| Metric | Value |
|--------|-------|
| Win Rate | {is_m.get('win_rate', 0):.1%} |
| Avg R:R | {is_m.get('avg_rr', 0):.2f} |
| Profit Factor | {is_m.get('profit_factor', 0):.2f} |
| Trade Count | {is_m.get('trade_count', 0)} |
| Total P&L | ${is_m.get('total_pnl', 0):.2f} |
| Max Drawdown | ${is_m.get('max_drawdown', 0):.2f} |

## OOS Results

| Metric | Value |
|--------|-------|
| Win Rate | {oos_m.get('win_rate', 0):.1%} |
| Avg R:R | {oos_m.get('avg_rr', 0):.2f} |
| Profit Factor | {oos_m.get('profit_factor', 0):.2f} |
| Trade Count | {oos_m.get('trade_count', 0)} |
| Total P&L | ${oos_m.get('total_pnl', 0):.2f} |
| Max Drawdown | ${oos_m.get('max_drawdown', 0):.2f} |

## Trade Summary

{"PASSED" if fitness else "FAILED"} fitness criteria (>55% WR, >1.5 R:R on both IS+OOS)

{"Rejection reasons: " + ", ".join(rejection_reasons) if not fitness and rejection_reasons else "All criteria met." if fitness else "Did not meet fitness thresholds."}

## Mutation Applied

- **Mutation type**: {iteration_data.get('mutation_type', 'RANDOM')}
- **Parent strategy**: {iteration_data.get('parent_hash', 'None')}

## Connections

- [[brain/Backtest-Loop]] — Index
- [[02-strategies/strategy-{strategy_hash[:8]}]] — Strategy hypothesis
"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        log.info("results_writer.write_backtest_result", path=str(filepath))
        return str(filepath)

    def write_finding(self, finding_data: dict) -> str:
        """Write a finding to findings/ directory.

        Produces markdown matching the finding vault template.

        Returns:
            Absolute file path of the written note.
        """
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        slug = finding_data.get("slug", "backtest-finding")

        filename = f"finding-{date_str}-{slug}.md"
        filepath = self.vault_path / "findings" / filename

        content = f"""---
id: finding-{date_str}-{slug}
type: finding
status: active
date: {date_iso}
project: deep6
domain: backtesting
confidence: {finding_data.get('confidence', 'medium')}
source_session: "{finding_data.get('source_session', '')}"
evidence_count: 1
tags: [type/finding, domain/backtesting, project/deep6]
---

# Finding: {finding_data.get('title', 'Backtest Discovery')}

## What Was Found

{finding_data.get('description', '')}

## Evidence

| Evidence | Source | Relevance |
|---|---|---|
| {finding_data.get('evidence', 'Backtest results')} | Hermes backtest loop | Strategy performance |

## Reusable Pattern

```
{finding_data.get('pattern', '')}
```

## Connections

- [[brain/Backtest-Loop]] — Index
"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        log.info("results_writer.write_finding", path=str(filepath))
        return str(filepath)

    def write_strategy_hypothesis(
        self,
        config_hash: str,
        config_data: dict,
        generation: int,
        parent_hash: str | None,
        mutation_type: str | None,
    ) -> str:
        """Write a strategy hypothesis to 02-strategies/ directory.

        Idempotent: skips if file already exists (don't overwrite live notes).

        Returns:
            Absolute file path of the strategy note.
        """
        date_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"strategy-{config_hash[:8]}.md"
        filepath = self.vault_path / "02-strategies" / filename

        if filepath.exists():
            return str(filepath)

        config_json = json.dumps(config_data, indent=2)

        content = f"""---
id: strategy-{config_hash[:8]}
type: strategy-hypothesis
status: testing
date: {date_iso}
project: deep6
generation: {generation}
parent_hash: {parent_hash or 'null'}
mutation_type: {mutation_type or 'null'}
tags: [type/strategy-hypothesis, project/deep6]
---

# Strategy {config_hash[:8]}

## Hypothesis

Entry model targeting MBO levels with configuration:

## Config

```json
{config_json}
```

## Test Results

_To be filled by Hermes after backtesting._

## Mutations Spawned

_None yet._

## Verdict

_Pending._

## Connections

- [[brain/Backtest-Loop]] — Index
"""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        log.info("results_writer.write_strategy_hypothesis", path=str(filepath))
        return str(filepath)

    def update_brain_index(self, iteration_number: int, iteration_data: dict) -> None:
        """Append iteration summary row to brain/Backtest-Loop.md iteration log.

        Finds the ``## Iteration Log`` table and appends a pipe-delimited row.
        If the table has a placeholder "No iterations run yet" row, it is replaced.
        """
        brain_path = self.vault_path / "brain" / "Backtest-Loop.md"
        if not brain_path.exists():
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        is_wr = iteration_data.get("is_win_rate", 0)
        oos_wr = iteration_data.get("oos_win_rate", 0)
        fitness = iteration_data.get("fitness_passed", False)
        mutation = iteration_data.get("mutation_type", "RANDOM")

        row = (
            f"| {iteration_number} | {date_str} "
            f"| {iteration_data.get('strategy_hash', '')[:8]} "
            f"| {is_wr:.1%} | {oos_wr:.1%} "
            f"| {'PASS' if fitness else 'FAIL'} | {mutation} |"
        )

        content = brain_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        new_lines: list[str] = []
        in_iteration_log = False
        inserted = False

        for i, line in enumerate(lines):
            # Detect start of Iteration Log section
            if line.strip().startswith("## Iteration Log"):
                in_iteration_log = True
                new_lines.append(line)
                continue

            # Detect next section — insert row before it if still in iteration log
            if in_iteration_log and line.strip().startswith("## ") and not inserted:
                new_lines.append(row)
                new_lines.append("")
                in_iteration_log = False
                inserted = True
                new_lines.append(line)
                continue

            # Replace placeholder row
            if in_iteration_log and "No iterations run yet" in line:
                new_lines.append(row)
                inserted = True
                continue

            new_lines.append(line)

        # If iteration log was the last section, append at end
        if in_iteration_log and not inserted:
            new_lines.append(row)

        brain_path.write_text("\n".join(new_lines), encoding="utf-8")
        log.info("results_writer.update_brain_index", iteration=iteration_number)

    def read_brain_index(self) -> str:
        """Read brain/Backtest-Loop.md content for Hermes context.

        Returns:
            Full markdown content, or a fallback message if not found.
        """
        brain_path = self.vault_path / "brain" / "Backtest-Loop.md"
        if brain_path.exists():
            return brain_path.read_text(encoding="utf-8")
        return "No brain index found."
