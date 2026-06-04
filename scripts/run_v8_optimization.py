"""Run the V8 optimization loop with simple walk-forward validation.

This is a thin V8-specific optimizer because the generic discovery loop operates
on StrategyConfig objects, while V8 optimization is a flat parameter search over
signal toggles and rendering/bias thresholds.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deep6.backtest.fitness import Metrics, evaluate_fitness
from deep6.backtest.v8_config import (
    V8_CONVERGENCE,
    V8_PARAM_BOUNDS,
    clamp_v8_params,
    load_v8_parent0,
)
from deep6.backtest.variant_evaluator import (
    RawBar,
    forward_r_multiple,
    load_bars,
    match_variant,
    risk_distance,
    rolling_atr,
    rolling_vol_ema,
)
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig

DEFAULT_DATA = Path("data/backtests/nq_1yr_1m.csv")
DEFAULT_DB = Path("data/backtests/v8_optimization.duckdb")
DEFAULT_PARAMS_JSON = Path("data/backtests/v8_optimal_params.json")
DEFAULT_REPORT = Path("data/backtests/v8_optimization_report.md")
DEFAULT_BARS_FORWARD = 10
PLATEAU_EPSILON = 1e-9
VARIANT_TO_TOGGLE = {
    "ABS_01": "ShowClassicAbsorption",
    "ABS_02": "ShowPassiveAbsorption",
    "ABS_03": "ShowStoppingVolume",
    "ABS_04": "ShowEffortVsResult",
    "EXH_01": "ShowZeroPrint",
    "EXH_02": "ShowExhaustionPrint",
    "EXH_03": "ShowThinPrint",
    "EXH_04": "ShowFatPrint",
    "EXH_05": "ShowFadingMomentum",
    "EXH_06": "ShowBidAskFade",
}
VARIANTS = tuple(VARIANT_TO_TOGGLE)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS iterations (
    id INTEGER PRIMARY KEY,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    action TEXT NOT NULL,
    parent_iteration_id INTEGER,
    params_hash TEXT NOT NULL,
    params_json TEXT NOT NULL,
    is_win_rate DOUBLE,
    is_avg_rr DOUBLE,
    is_profit_factor DOUBLE,
    is_max_dd DOUBLE,
    is_total_pnl DOUBLE,
    is_trade_count INTEGER,
    oos_win_rate DOUBLE,
    oos_avg_rr DOUBLE,
    oos_profit_factor DOUBLE,
    oos_max_dd DOUBLE,
    oos_total_pnl DOUBLE,
    oos_trade_count INTEGER,
    oos_fitness DOUBLE,
    fitness_passed BOOLEAN,
    plateau_count INTEGER,
    note TEXT
);

CREATE TABLE IF NOT EXISTS walk_forward (
    rank INTEGER,
    iteration_id INTEGER,
    params_hash TEXT,
    params_json TEXT,
    validate_fitness DOUBLE,
    test_win_rate DOUBLE,
    test_avg_rr DOUBLE,
    test_profit_factor DOUBLE,
    test_max_dd DOUBLE,
    test_total_pnl DOUBLE,
    test_trade_count INTEGER,
    test_fitness DOUBLE
);
"""


@dataclass(slots=True)
class MatchEvent:
    variant: str
    direction: str
    strength: float
    realized_r: float


@dataclass(slots=True)
class BarSignals:
    session_date: str
    events: list[MatchEvent]


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    filtered = {name: params[name] for name in V8_PARAM_BOUNDS if name in params}
    normalized = clamp_v8_params(filtered)
    for name in V8_PARAM_BOUNDS:
        if name.startswith("Show"):
            normalized[name] = int(bool(normalized[name]))
        elif name in {"MinArrowConfluence", "MaxSignalsPerSession", "BiasLookback"}:
            normalized[name] = int(normalized[name])
        else:
            normalized[name] = round(float(normalized[name]), 6)
    return normalized


def params_hash(params: dict[str, Any]) -> str:
    return json.dumps(normalize_params(params), sort_keys=True, separators=(",", ":"))


def ensure_db(db_path: Path) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    conn.execute(SCHEMA_SQL)
    return conn


def compute_metrics_from_returns(values: list[float]) -> Metrics:
    if not values:
        return Metrics()
    winners = [value for value in values if value > 0]
    losers = [value for value in values if value <= 0]
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 0.0
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        running += value
        peak = max(peak, running)
        max_dd = max(max_dd, peak - running)
    return Metrics(
        win_rate=len(winners) / len(values),
        avg_rr=(avg_win / avg_loss) if avg_loss > 0 else (99.0 if avg_win > 0 else 0.0),
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0),
        max_drawdown_dollars=max_dd,
        total_pnl=sum(values),
        trade_count=len(values),
    )


def score_period(metrics: Metrics) -> float:
    dd_pct = min(metrics.max_drawdown_dollars / max(abs(metrics.total_pnl), 1.0), 1.0)
    return round(
        metrics.win_rate * 0.30
        + min(metrics.avg_rr / 5.0, 1.0) * 0.30
        + min(metrics.profit_factor / 10.0, 1.0) * 0.20
        + (1.0 - dd_pct) * 0.20,
        4,
    )


def precompute_signals(bars: list[RawBar], bars_forward: int) -> list[BarSignals]:
    atrs = rolling_atr(bars)
    vol_emas = rolling_vol_ema(bars)
    abs_cfg = AbsorptionConfig()
    exh_cfg = ExhaustionConfig()
    precomputed: list[BarSignals] = []
    prior_raw: RawBar | None = None
    prior_session: str | None = None

    for index, raw in enumerate(bars):
        if raw.session_date != prior_session:
            prior_raw = None
            prior_session = raw.session_date
        atr = atrs[index]
        vol_ema = vol_emas[index]
        events: list[MatchEvent] = []
        for variant in VARIANTS:
            matches = match_variant(raw, prior_raw, variant, atr, vol_ema, abs_cfg, exh_cfg)
            for match in matches:
                risk = risk_distance(raw, match.price, match.direction)
                realized_r = forward_r_multiple(bars, index, bars_forward, match.direction, match.price, risk)
                events.append(
                    MatchEvent(
                        variant=variant,
                        direction=match.direction,
                        strength=round(float(match.strength), 6),
                        realized_r=round(float(realized_r), 6),
                    )
                )
        precomputed.append(BarSignals(session_date=raw.session_date, events=events))
        prior_raw = raw
    return precomputed


def evaluate_candidate(
    signals: list[BarSignals],
    params: dict[str, Any],
    train_end: int,
    validate_end: int,
) -> dict[str, Any]:
    params = normalize_params(params)
    lookback = max(int(params["BiasLookback"]), 1)
    min_confluence = max(int(params["MinArrowConfluence"]), 1)
    max_signals = int(params["MaxSignalsPerSession"])
    min_exh_strength = float(params["MinExhaustionStrength"])
    long_threshold = float(params["BiasLongThreshold"])
    short_threshold = float(params["BiasShortThreshold"])

    train_returns: list[float] = []
    validate_returns: list[float] = []
    session_emissions = 0
    current_session: str | None = None
    recent_scores: deque[float] = deque(maxlen=lookback)

    for index, row in enumerate(signals):
        if row.session_date != current_session:
            current_session = row.session_date
            session_emissions = 0
            recent_scores.clear()

        filtered: list[MatchEvent] = []
        for event in row.events:
            toggle = VARIANT_TO_TOGGLE[event.variant]
            if not params.get(toggle):
                continue
            if event.variant.startswith("EXH") and event.strength < min_exh_strength:
                continue
            filtered.append(event)

        if not filtered:
            continue

        long_events = [event for event in filtered if event.direction == "LONG"]
        short_events = [event for event in filtered if event.direction == "SHORT"]
        long_strength = sum(event.strength for event in long_events)
        short_strength = sum(event.strength for event in short_events)
        bar_score = (long_strength - short_strength) / max(len(filtered), 1)
        recent_scores.append(bar_score)
        bias_score = sum(recent_scores) / len(recent_scores)

        if bias_score >= long_threshold:
            bias_state = "LONG"
        elif bias_score <= short_threshold:
            bias_state = "SHORT"
        else:
            bias_state = "NEUTRAL"

        if len(long_events) > len(short_events):
            dominant = long_events
            dominant_side = "LONG"
        elif len(short_events) > len(long_events):
            dominant = short_events
            dominant_side = "SHORT"
        elif long_strength > short_strength:
            dominant = long_events
            dominant_side = "LONG"
        elif short_strength > long_strength:
            dominant = short_events
            dominant_side = "SHORT"
        else:
            dominant = []
            dominant_side = "NEUTRAL"

        if not dominant or dominant_side != bias_state:
            continue
        if len(dominant) < min_confluence:
            continue
        if max_signals > 0 and session_emissions >= max_signals:
            continue

        session_emissions += 1
        realized_r = sum(event.realized_r for event in dominant) / len(dominant)
        if index < train_end:
            train_returns.append(realized_r)
        elif index < validate_end:
            validate_returns.append(realized_r)

    is_metrics = compute_metrics_from_returns(train_returns)
    oos_metrics = compute_metrics_from_returns(validate_returns)
    fitness = evaluate_fitness(is_metrics, oos_metrics)
    return {
        "params": params,
        "is_metrics": is_metrics,
        "oos_metrics": oos_metrics,
        "fitness": fitness,
    }


def evaluate_test_period(
    signals: list[BarSignals],
    params: dict[str, Any],
    validate_end: int,
) -> Metrics:
    params = normalize_params(params)
    lookback = max(int(params["BiasLookback"]), 1)
    min_confluence = max(int(params["MinArrowConfluence"]), 1)
    max_signals = int(params["MaxSignalsPerSession"])
    min_exh_strength = float(params["MinExhaustionStrength"])
    long_threshold = float(params["BiasLongThreshold"])
    short_threshold = float(params["BiasShortThreshold"])

    test_returns: list[float] = []
    session_emissions = 0
    current_session: str | None = None
    recent_scores: deque[float] = deque(maxlen=lookback)

    for index, row in enumerate(signals):
        if row.session_date != current_session:
            current_session = row.session_date
            session_emissions = 0
            recent_scores.clear()

        filtered: list[MatchEvent] = []
        for event in row.events:
            toggle = VARIANT_TO_TOGGLE[event.variant]
            if not params.get(toggle):
                continue
            if event.variant.startswith("EXH") and event.strength < min_exh_strength:
                continue
            filtered.append(event)

        if not filtered:
            continue
        long_events = [event for event in filtered if event.direction == "LONG"]
        short_events = [event for event in filtered if event.direction == "SHORT"]
        long_strength = sum(event.strength for event in long_events)
        short_strength = sum(event.strength for event in short_events)
        bar_score = (long_strength - short_strength) / max(len(filtered), 1)
        recent_scores.append(bar_score)
        bias_score = sum(recent_scores) / len(recent_scores)
        if bias_score >= long_threshold:
            bias_state = "LONG"
        elif bias_score <= short_threshold:
            bias_state = "SHORT"
        else:
            bias_state = "NEUTRAL"

        if len(long_events) > len(short_events):
            dominant = long_events
            dominant_side = "LONG"
        elif len(short_events) > len(long_events):
            dominant = short_events
            dominant_side = "SHORT"
        elif long_strength > short_strength:
            dominant = long_events
            dominant_side = "LONG"
        elif short_strength > long_strength:
            dominant = short_events
            dominant_side = "SHORT"
        else:
            dominant = []
            dominant_side = "NEUTRAL"

        if index < validate_end or not dominant or dominant_side != bias_state:
            continue
        if len(dominant) < min_confluence:
            continue
        if max_signals > 0 and session_emissions >= max_signals:
            continue

        session_emissions += 1
        test_returns.append(sum(event.realized_r for event in dominant) / len(dominant))

    return compute_metrics_from_returns(test_returns)


def mutate_params(parent: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    child = dict(parent)
    mutated_any = False
    for name, (min_value, max_value) in V8_PARAM_BOUNDS.items():
        if name.startswith("Show"):
            if rng.random() < 0.18:
                child[name] = 0 if int(bool(child[name])) else 1
                mutated_any = True
            continue
        if rng.random() >= 0.38:
            continue
        span = max_value - min_value
        current = float(child[name])
        if name in {"MinArrowConfluence", "MaxSignalsPerSession", "BiasLookback"}:
            step = max(1, int(round(span * 0.15)))
            current = int(round(current)) + rng.randint(-step, step)
            child[name] = current
        else:
            child[name] = current + rng.uniform(-0.18 * span, 0.18 * span)
        mutated_any = True
    if not mutated_any:
        fallback = rng.choice(list(V8_PARAM_BOUNDS))
        if fallback.startswith("Show"):
            child[fallback] = 0 if int(bool(child[fallback])) else 1
        elif fallback in {"MinArrowConfluence", "MaxSignalsPerSession", "BiasLookback"}:
            child[fallback] = int(round(float(child[fallback]))) + rng.choice([-1, 1])
        else:
            lo, hi = V8_PARAM_BOUNDS[fallback]
            child[fallback] = float(child[fallback]) + rng.uniform(-0.1 * (hi - lo), 0.1 * (hi - lo))
    return normalize_params(child)


def random_params(rng: random.Random) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name, (min_value, max_value) in V8_PARAM_BOUNDS.items():
        if name.startswith("Show"):
            payload[name] = rng.choice([0, 1])
        elif name in {"MinArrowConfluence", "MaxSignalsPerSession", "BiasLookback"}:
            payload[name] = rng.randint(int(min_value), int(max_value))
        else:
            payload[name] = rng.uniform(min_value, max_value)
    return normalize_params(payload)


def insert_iteration(
    conn: duckdb.DuckDBPyConnection,
    iteration_id: int,
    action: str,
    parent_iteration_id: int | None,
    evaluation: dict[str, Any],
    plateau_count: int,
    note: str,
) -> None:
    params = normalize_params(evaluation["params"])
    fitness = evaluation["fitness"]
    is_metrics: Metrics = evaluation["is_metrics"]
    oos_metrics: Metrics = evaluation["oos_metrics"]
    conn.execute(
        """
        INSERT INTO iterations (
            id, timestamp, status, action, parent_iteration_id, params_hash, params_json,
            is_win_rate, is_avg_rr, is_profit_factor, is_max_dd, is_total_pnl, is_trade_count,
            oos_win_rate, oos_avg_rr, oos_profit_factor, oos_max_dd, oos_total_pnl, oos_trade_count,
            oos_fitness, fitness_passed, plateau_count, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            iteration_id,
            datetime.now(timezone.utc).isoformat(),
            "completed",
            action,
            parent_iteration_id,
            params_hash(params),
            json.dumps(params, sort_keys=True),
            is_metrics.win_rate,
            is_metrics.avg_rr,
            min(is_metrics.profit_factor, 99.0),
            is_metrics.max_drawdown_dollars,
            is_metrics.total_pnl,
            is_metrics.trade_count,
            oos_metrics.win_rate,
            oos_metrics.avg_rr,
            min(oos_metrics.profit_factor, 99.0),
            oos_metrics.max_drawdown_dollars,
            oos_metrics.total_pnl,
            oos_metrics.trade_count,
            fitness.score,
            bool(fitness.passed),
            plateau_count,
            note,
        ],
    )


def top_iterations(conn: duckdb.DuckDBPyConnection, limit: int = 3) -> list[tuple[Any, ...]]:
    return conn.execute(
        """
        SELECT id, params_hash, params_json, oos_fitness, oos_win_rate, oos_avg_rr,
               oos_trade_count, oos_total_pnl
        FROM iterations
        WHERE status = 'completed'
        ORDER BY oos_fitness DESC, oos_total_pnl DESC, id ASC
        LIMIT ?
        """,
        [limit],
    ).fetchall()


def write_optimal_params(path: Path, winner: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(winner, indent=2, sort_keys=False), encoding="utf-8")


def write_report(
    path: Path,
    iteration_count: int,
    stop_reason: str,
    best_validation_fitness: float,
    top3_rows: list[tuple[Any, ...]],
    walk_forward_rows: list[dict[str, Any]],
    winner: dict[str, Any],
) -> None:
    lines = [
        "# V8 Optimization Report",
        "",
        f"- Iterations completed: **{iteration_count}**",
        f"- Stop reason: **{stop_reason}**",
        f"- Best validation OOS fitness: **{best_validation_fitness:.4f}**",
        f"- Winning config test fitness: **{winner['walk_forward']['test_fitness']:.4f}**",
        f"- Target OOS >= 0.55: **{'met' if winner['validation']['oos_fitness'] >= 0.55 else 'not met; best available saved'}**",
        "",
        "## Top-3 validation configs",
        "",
        "| Rank | Iteration | OOS fitness | OOS win rate | OOS avg R:R | OOS trades | OOS total pnl |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(top3_rows, start=1):
        iteration_id, _hash_value, _params_json, oos_fitness, oos_win_rate, oos_avg_rr, oos_trade_count, oos_total_pnl = row
        lines.append(
            f"| {rank} | {iteration_id} | {float(oos_fitness):.4f} | {float(oos_win_rate):.4f} | {float(oos_avg_rr):.4f} | {int(oos_trade_count)} | {float(oos_total_pnl):.4f} |"
        )
    lines.extend(
        [
            "",
            "## Walk-forward test results (final 20%)",
            "",
            "| Rank | Iteration | Validation fitness | Test fitness | Test win rate | Test avg R:R | Test trades | Test total pnl |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in walk_forward_rows:
        lines.append(
            f"| {row['rank']} | {row['iteration_id']} | {row['validate_fitness']:.4f} | {row['test_fitness']:.4f} | {row['test_win_rate']:.4f} | {row['test_avg_rr']:.4f} | {row['test_trade_count']} | {row['test_total_pnl']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Winner",
            "",
            f"- Iteration: **{winner['iteration_id']}**",
            f"- Validation OOS fitness: **{winner['validation']['oos_fitness']:.4f}**",
            f"- Test fitness: **{winner['walk_forward']['test_fitness']:.4f}**",
            f"- Test total pnl: **{winner['walk_forward']['test_total_pnl']:.4f}**",
            "",
            "```json",
            json.dumps(winner['params'], indent=2, sort_keys=True),
            "```",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_optimizer(
    data_path: Path,
    db_path: Path,
    output_params_path: Path,
    report_path: Path,
    *,
    max_iterations: int,
    patience: int,
    max_hours: float,
    bars_forward: int,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed)
    bars = load_bars(data_path)
    signals = precompute_signals(bars, bars_forward)
    total_bars = len(signals)
    train_end = max(1, int(total_bars * 0.60))
    validate_end = max(train_end + 1, int(total_bars * 0.80))

    conn = ensure_db(db_path)
    conn.execute("DELETE FROM iterations")
    conn.execute("DELETE FROM walk_forward")
    start = time.monotonic()

    best_score = -math.inf
    plateau_count = 0
    seen_hashes: set[str] = set()
    best_params = normalize_params(load_v8_parent0())
    best_parent_id: int | None = None

    for iteration_id in range(1, max_iterations + 1):
        elapsed_hours = (time.monotonic() - start) / 3600.0
        if iteration_id == 1:
            candidate = best_params
            action = "baseline"
            parent_iteration_id = None
        else:
            if iteration_id % 5 == 0:
                candidate = random_params(rng)
                action = "random"
                parent_iteration_id = None
            else:
                candidate = mutate_params(best_params, rng)
                action = "mutate"
                parent_iteration_id = best_parent_id
            while params_hash(candidate) in seen_hashes:
                candidate = random_params(rng) if action == "random" else mutate_params(best_params, rng)

        evaluation = evaluate_candidate(signals, candidate, train_end, validate_end)
        score = evaluation["fitness"].score
        note = "best" if score > best_score + PLATEAU_EPSILON else "plateau"
        if score > best_score + PLATEAU_EPSILON:
            best_score = score
            best_params = normalize_params(candidate)
            best_parent_id = iteration_id
            plateau_count = 0
        else:
            plateau_count += 1

        insert_iteration(conn, iteration_id, action, parent_iteration_id, evaluation, plateau_count, note)
        seen_hashes.add(params_hash(candidate))

        if iteration_id >= 100 and plateau_count > patience:
            stop_reason = f"plateau>{patience} after minimum iteration gate"
            break
        if elapsed_hours >= max_hours:
            stop_reason = f"time_limit>{max_hours}h"
            break
    else:
        stop_reason = f"max_iterations={max_iterations}"

    rows = top_iterations(conn, limit=3)
    walk_forward_rows: list[dict[str, Any]] = []
    best_walkforward: dict[str, Any] | None = None
    for rank, row in enumerate(rows, start=1):
        iteration_id, hash_value, row_params_json, validate_fitness, *_rest = row
        config = json.loads(row_params_json)
        test_metrics = evaluate_test_period(signals, config, validate_end)
        test_fitness = score_period(test_metrics)
        record = {
            "rank": rank,
            "iteration_id": int(iteration_id),
            "params_hash": hash_value,
            "params": config,
            "validate_fitness": float(validate_fitness),
            "test_win_rate": float(test_metrics.win_rate),
            "test_avg_rr": float(test_metrics.avg_rr),
            "test_profit_factor": float(min(test_metrics.profit_factor, 99.0)),
            "test_max_dd": float(test_metrics.max_drawdown_dollars),
            "test_total_pnl": float(test_metrics.total_pnl),
            "test_trade_count": int(test_metrics.trade_count),
            "test_fitness": float(test_fitness),
        }
        walk_forward_rows.append(record)
        conn.execute(
            """
            INSERT INTO walk_forward (
                rank, iteration_id, params_hash, params_json, validate_fitness,
                test_win_rate, test_avg_rr, test_profit_factor, test_max_dd,
                test_total_pnl, test_trade_count, test_fitness
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                rank,
                int(iteration_id),
                hash_value,
                json.dumps(config, sort_keys=True),
                float(validate_fitness),
                record["test_win_rate"],
                record["test_avg_rr"],
                record["test_profit_factor"],
                record["test_max_dd"],
                record["test_total_pnl"],
                record["test_trade_count"],
                record["test_fitness"],
            ],
        )
        if best_walkforward is None or record["test_fitness"] > best_walkforward["walk_forward"]["test_fitness"]:
            best_walkforward = {
                "iteration_id": int(iteration_id),
                "params_hash": hash_value,
                "params": config,
                "validation": {
                    "oos_fitness": float(validate_fitness),
                },
                "walk_forward": {
                    "test_win_rate": record["test_win_rate"],
                    "test_avg_rr": record["test_avg_rr"],
                    "test_profit_factor": record["test_profit_factor"],
                    "test_max_dd": record["test_max_dd"],
                    "test_total_pnl": record["test_total_pnl"],
                    "test_trade_count": record["test_trade_count"],
                    "test_fitness": record["test_fitness"],
                },
            }

    if best_walkforward is None:
        raise RuntimeError("No completed iterations were available for walk-forward selection")

    write_optimal_params(output_params_path, best_walkforward)
    write_report(
        report_path,
        iteration_count=int(conn.execute("SELECT COUNT(*) FROM iterations WHERE status='completed'").fetchone()[0]),
        stop_reason=stop_reason,
        best_validation_fitness=float(best_score),
        top3_rows=rows,
        walk_forward_rows=walk_forward_rows,
        winner=best_walkforward,
    )
    conn.close()
    return {
        "db_path": str(db_path),
        "params_path": str(output_params_path),
        "report_path": str(report_path),
        "stop_reason": stop_reason,
        "winner": best_walkforward,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the DEEP6 V8 optimization loop")
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--output-params", default=str(DEFAULT_PARAMS_JSON))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--bars-forward", type=int, default=DEFAULT_BARS_FORWARD)
    parser.add_argument("--max-iterations", type=int, default=int(V8_CONVERGENCE["max_iterations"]))
    parser.add_argument("--convergence-patience", type=int, default=int(V8_CONVERGENCE["patience"]))
    parser.add_argument("--max-hours", type=float, default=float(V8_CONVERGENCE["max_hours"]))
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_optimizer(
        Path(args.data),
        Path(args.db),
        Path(args.output_params),
        Path(args.report),
        max_iterations=min(int(args.max_iterations), 200),
        patience=int(args.convergence_patience),
        max_hours=float(args.max_hours),
        bars_forward=int(args.bars_forward),
        seed=int(args.seed),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
