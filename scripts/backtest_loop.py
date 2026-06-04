"""Run one DEEP6 discovery-loop backtest iteration.

Thin orchestrator only:
- reads discovery loop state from DuckDB
- decides generate/mutate/random action
- validates config
- runs the backtest harness subprocess
- computes fitness
- persists results to DuckDB + Obsidian
- prints a Hermes-readable summary block
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb
import yaml

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deep6.backtest.config_validator import ValidationResult, validate
from deep6.backtest.discovery_schema import (
    create_discovery_db,
    get_best_strategies,
    get_iteration_history,
    strategy_already_tested,
)
from deep6.backtest.fitness import FitnessResult, Metrics, evaluate_fitness
from deep6.backtest.mutation_engine import MutationEngine
from deep6.backtest.results_writer import ResultsWriter
from deep6.backtest.strategy_config import StrategyConfig

LOGGER = logging.getLogger("backtest_loop")
DEFAULT_TIMEOUT_SECONDS = 900
MAX_DEDUP_ATTEMPTS = 20


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one DEEP6 backtest discovery iteration"
    )
    parser.add_argument("--db", required=True, help="DuckDB path (created if missing)")
    parser.add_argument(
        "--data-dir", required=True, help="Pre-processed session files directory"
    )
    parser.add_argument("--vault", required=True, help="Obsidian vault path")
    parser.add_argument(
        "--action",
        choices=["generate", "mutate", "random", "auto"],
        default="auto",
    )
    parser.add_argument(
        "--parent-hash", help="Parent strategy hash (for mutate action)"
    )
    parser.add_argument(
        "--budget", type=int, default=50, help="Max iterations before checkpoint"
    )
    return parser


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def load_state(db_path: str) -> dict[str, Any]:
    conn = create_discovery_db(db_path)
    try:
        history = get_iteration_history(conn)
        best = get_best_strategies(conn, n=3)
        iteration_count = len(history)
        best_hash = best[0][0] if best else None
        best_score = best[0][2] if best else None
        latest_hash = history[-1][2] if history else None
        return {
            "iteration_count": iteration_count,
            "best_hash": best_hash,
            "best_score": best_score,
            "latest_hash": latest_hash,
            "best_strategies": best,
            "history": history,
        }
    finally:
        conn.close()


def decide_action(state: dict[str, Any], args: argparse.Namespace) -> str:
    if args.action != "auto":
        return args.action
    n = state["iteration_count"]
    if n == 0 or state["best_hash"] is None:
        return "generate"
    if n % 5 == 0:
        return "random"
    return "mutate"


def check_budget(db_path: str, budget: int) -> tuple[bool, dict[str, Any]]:
    state = load_state(db_path)
    return state["iteration_count"] >= budget, state


def fetch_strategy_config(db_path: str, strategy_hash: str) -> StrategyConfig:
    conn = duckdb.connect(db_path)
    try:
        row = conn.execute(
            "SELECT config_json FROM strategies WHERE hash = ?", [strategy_hash]
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError(f"Parent strategy not found: {strategy_hash}")
    return StrategyConfig.model_validate_json(row[0])


def find_parent_iteration_id(db_path: str, parent_hash: str | None) -> int | None:
    if not parent_hash:
        return None
    conn = duckdb.connect(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(id) FROM iterations WHERE strategy_hash = ?", [parent_hash]
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return row[0]


def ensure_unique_config(
    db_path: str,
    candidate: StrategyConfig,
    engine: MutationEngine,
    *,
    generation: int = 0,
    parent_hash: str | None = None,
) -> tuple[StrategyConfig, bool]:
    conn = create_discovery_db(db_path)
    try:
        if not strategy_already_tested(conn, candidate.config_hash()):
            return candidate, False
    finally:
        conn.close()

    for _ in range(MAX_DEDUP_ATTEMPTS):
        fresh = engine._make_random_config(generation=generation, parent_hash=parent_hash)
        conn = create_discovery_db(db_path)
        try:
            if not strategy_already_tested(conn, fresh.config_hash()):
                return fresh, True
        finally:
            conn.close()

    raise RuntimeError("Could not generate a unique strategy config after dedup attempts")


def get_or_generate_config(
    db_path: str, state: dict[str, Any], action: str, args: argparse.Namespace
) -> tuple[StrategyConfig, str | None, bool]:
    engine = MutationEngine()

    if action in {"generate", "random"}:
        base = engine.generate_initial_population(1)[0]
        unique, deduped = ensure_unique_config(db_path, base, engine)
        return unique, unique.parent_hash, deduped

    parent_hash = args.parent_hash or state["best_hash"] or state.get("latest_hash")
    if not parent_hash:
        raise ValueError("Mutate action requires --parent-hash or an existing best strategy")

    parent = fetch_strategy_config(db_path, parent_hash)
    child = engine.mutate(parent)
    unique, deduped = ensure_unique_config(
        db_path,
        child,
        engine,
        generation=parent.generation + 1,
        parent_hash=parent_hash,
    )
    return unique, parent_hash, deduped


def serialize_config(config: StrategyConfig) -> str:
    data = json.loads(config.model_dump_json())
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as handle:
        yaml.safe_dump(data, handle, sort_keys=False)
        return handle.name


def run_harness(config_path: str, data_dir: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "deep6.backtest.harness",
            "--config",
            config_path,
            "--data-dir",
            data_dir,
        ],
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return {"status": "failed", "error": result.stderr[:500]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "failed",
            "error": f"Could not parse harness output: {result.stdout[:200]}",
        }


def compute_fitness(harness_output: dict[str, Any]) -> FitnessResult:
    is_raw = harness_output.get("is_metrics") or {}
    oos_raw = harness_output.get("oos_metrics") or {}
    is_metrics = Metrics(
        win_rate=float(is_raw.get("win_rate", 0.0) or 0.0),
        avg_rr=float(is_raw.get("avg_rr", 0.0) or 0.0),
        profit_factor=float(is_raw.get("profit_factor", 0.0) or 0.0),
        total_pnl=float(is_raw.get("total_pnl", 0.0) or 0.0),
        trade_count=int(is_raw.get("trade_count", 0) or 0),
        max_drawdown_dollars=float(is_raw.get("max_drawdown", 0.0) or 0.0),
    )
    oos_metrics = Metrics(
        win_rate=float(oos_raw.get("win_rate", 0.0) or 0.0),
        avg_rr=float(oos_raw.get("avg_rr", 0.0) or 0.0),
        profit_factor=float(oos_raw.get("profit_factor", 0.0) or 0.0),
        total_pnl=float(oos_raw.get("total_pnl", 0.0) or 0.0),
        trade_count=int(oos_raw.get("trade_count", 0) or 0),
        max_drawdown_dollars=float(oos_raw.get("max_drawdown", 0.0) or 0.0),
    )
    return evaluate_fitness(is_metrics, oos_metrics)


def build_validation_failure_output(validation: ValidationResult) -> dict[str, Any]:
    return {
        "status": "rejected",
        "error": "; ".join(validation.errors),
        "fitness_passed": False,
        "rejection_reasons": list(validation.errors),
        "validation_warnings": list(validation.warnings),
        "is_metrics": {},
        "oos_metrics": {},
    }


def write_results(
    db_path: str,
    vault_path: str,
    config: StrategyConfig,
    harness_output: dict[str, Any],
    fitness: FitnessResult,
    iteration_n: int,
    parent_hash: str | None,
) -> tuple[int, list[str]]:
    create_discovery_db(db_path).close()
    writer = ResultsWriter(db_path, vault_path)

    is_m = harness_output.get("is_metrics") or {}
    oos_m = harness_output.get("oos_metrics") or {}
    rejection_reasons = list(harness_output.get("rejection_reasons") or fitness.rejection_reasons)
    parent_iteration_id = find_parent_iteration_id(db_path, parent_hash)

    iteration_data = {
        "strategy_hash": config.config_hash(),
        "config": json.loads(config.model_dump_json()),
        "is_win_rate": is_m.get("win_rate", 0.0),
        "is_avg_rr": is_m.get("avg_rr", 0.0),
        "is_profit_factor": is_m.get("profit_factor", 0.0),
        "is_max_dd": is_m.get("max_drawdown", 0.0),
        "oos_win_rate": oos_m.get("win_rate", 0.0),
        "oos_avg_rr": oos_m.get("avg_rr", 0.0),
        "oos_profit_factor": oos_m.get("profit_factor", 0.0),
        "oos_max_dd": oos_m.get("max_drawdown", 0.0),
        "is_trade_count": is_m.get("trade_count", 0),
        "oos_trade_count": oos_m.get("trade_count", 0),
        "status": harness_output.get("status", "completed"),
        "parent_iteration_id": parent_iteration_id,
        "fitness_passed": bool(fitness.passed),
        "mutation_type": config.mutation_type,
        "parent_hash": parent_hash,
        "is_metrics": is_m,
        "oos_metrics": oos_m,
        "rejection_reasons": rejection_reasons,
    }

    iteration_id = writer.write_iteration(iteration_data)
    writer.upsert_strategy(
        config.config_hash(),
        config.model_dump_json(),
        config.generation,
        config.parent_hash,
        config.mutation_type,
        fitness.score,  # Always store score so mutations can find best attempt
        fitness.score,
    )

    files_written = [
        writer.write_strategy_hypothesis(
            config.config_hash(),
            json.loads(config.model_dump_json()),
            config.generation,
            config.parent_hash,
            config.mutation_type,
        ),
        writer.write_backtest_result(iteration_n, iteration_data),
    ]
    writer.update_brain_index(iteration_n, iteration_data)

    if fitness.passed:
        files_written.append(
            writer.write_finding(
                {
                    "slug": f"winning-strategy-{config.config_hash()[:8]}",
                    "title": f"Strategy {config.config_hash()[:8]} passes fitness criteria",
                    "description": (
                        f"IS WR: {is_m.get('win_rate', 0):.1%}, "
                        f"OOS WR: {oos_m.get('win_rate', 0):.1%}, "
                        f"IS R:R: {is_m.get('avg_rr', 0):.2f}, "
                        f"OOS R:R: {oos_m.get('avg_rr', 0):.2f}"
                    ),
                    "confidence": "high",
                    "pattern": config.model_dump_json(indent=2),
                }
            )
        )

    return iteration_id, files_written


def format_best(best_hash: str | None, best_score: float | None) -> str:
    if not best_hash:
        return "None"
    score_text = f"{best_score:.3f}" if isinstance(best_score, (int, float)) else "n/a"
    return f"{best_hash[:8]} (score: {score_text})"


def decide_next_action(
    iteration_n: int,
    budget: int,
    fitness: FitnessResult,
    current_action: str,
) -> str:
    if iteration_n >= budget:
        return "CHECKPOINT - budget exhausted"
    if fitness.passed:
        return "REPORT - threshold met"
    if current_action == "random" or iteration_n % 5 == 0:
        return "explore random"
    return "mutate best"


def print_summary(
    iteration_n: int,
    config: StrategyConfig,
    harness_output: dict[str, Any],
    fitness: FitnessResult,
    best_hash: str | None,
    best_score: float | None,
    budget: int,
    files_written: list[str],
    next_action: str,
) -> None:
    is_m = harness_output.get("is_metrics") or {}
    oos_m = harness_output.get("oos_metrics") or {}
    reasons = harness_output.get("rejection_reasons") or fitness.rejection_reasons
    reason_text = "; ".join(reasons) if reasons else "All criteria met"

    print(f"=== ITERATION {iteration_n} COMPLETE ===")
    print(f"Strategy: {config.config_hash()}")
    print(
        f"Mutation: {config.mutation_type or 'RANDOM'} from parent {config.parent_hash or 'None'}"
    )
    print(
        f"IS Win Rate: {float(is_m.get('win_rate', 0.0)):.1%} | "
        f"IS R:R: {float(is_m.get('avg_rr', 0.0)):.2f} | "
        f"IS Trades: {int(is_m.get('trade_count', 0) or 0)}"
    )
    print(
        f"OOS Win Rate: {float(oos_m.get('win_rate', 0.0)):.1%} | "
        f"OOS R:R: {float(oos_m.get('avg_rr', 0.0)):.2f} | "
        f"OOS Trades: {int(oos_m.get('trade_count', 0) or 0)}"
    )
    print(
        f"FITNESS: {'PASSED' if fitness.passed else 'FAILED'} "
        f"(score: {fitness.score:.3f})"
    )
    print(f"Reason: {reason_text}")
    print(f"Best So Far: {format_best(best_hash, best_score)}")
    print(f"Iterations Remaining: {max(budget - iteration_n, 0)}")
    print(f"Files Written: {files_written}")
    print(f"=== NEXT ACTION: {next_action} ===")


def print_checkpoint(state: dict[str, Any], budget: int) -> None:
    print(f"=== CHECKPOINT - budget exhausted ({budget} iterations) ===")
    for index, row in enumerate(state.get("best_strategies") or [], start=1):
        strategy_hash, _config_json, best_oos_fitness, times_tested = row
        score_text = (
            f"{best_oos_fitness:.3f}"
            if isinstance(best_oos_fitness, (int, float))
            else "n/a"
        )
        print(
            f"{index}. {strategy_hash[:8]} | score={score_text} | tested={times_tested}"
        )


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    over_budget, state = check_budget(args.db, args.budget)
    if over_budget:
        print_checkpoint(state, args.budget)
        return 0

    action = decide_action(state, args)
    LOGGER.info("Selected action", extra={"action": action})

    config, parent_hash, deduped = get_or_generate_config(args.db, state, action, args)
    if deduped:
        LOGGER.info("Duplicate strategy detected; fell back to unique random config")

    validation = validate(config)
    if validation.valid:
        config_path = serialize_config(config)
        try:
            harness_output = run_harness(config_path, args.data_dir)
        finally:
            Path(config_path).unlink(missing_ok=True)
    else:
        harness_output = build_validation_failure_output(validation)

    fitness = compute_fitness(harness_output)
    if harness_output.get("rejection_reasons") and not fitness.rejection_reasons:
        fitness.rejection_reasons.extend(harness_output["rejection_reasons"])

    iteration_n = state["iteration_count"] + 1
    _iteration_id, files_written = write_results(
        args.db,
        args.vault,
        config,
        harness_output,
        fitness,
        iteration_n,
        parent_hash,
    )

    post_state = load_state(args.db)
    next_action = decide_next_action(iteration_n, args.budget, fitness, action)
    print_summary(
        iteration_n=iteration_n,
        config=config,
        harness_output=harness_output,
        fitness=fitness,
        best_hash=post_state["best_hash"],
        best_score=post_state["best_score"],
        budget=args.budget,
        files_written=files_written,
        next_action=next_action,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
