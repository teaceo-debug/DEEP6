"""CLI evaluator for individual absorption/exhaustion variants.

Runs a lightweight, single-variant audit over 1-minute OHLCV data and writes
summary/results into DuckDB.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from deep6.backtest.fitness import split_sessions
from deep6.backtest.harness import DEFAULT_IS_RATIO
from deep6.engines.exhaustion import reset_cooldowns
from deep6.engines.signal_config import AbsorptionConfig, ExhaustionConfig

DB_PATH = "data/backtests/v8_variant_audit.duckdb"
SUPPORTED_VARIANTS = (
    "ABS_01",
    "ABS_02",
    "ABS_03",
    "ABS_04",
    "EXH_01",
    "EXH_02",
    "EXH_03",
    "EXH_04",
    "EXH_05",
    "EXH_06",
)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS variants (
    name TEXT PRIMARY KEY,
    is_hit_rate DOUBLE,
    oos_hit_rate DOUBLE,
    rr DOUBLE,
    pf DOUBLE,
    n_is INTEGER,
    n_oos INTEGER,
    verdict TEXT CHECK(verdict IN ('KEEP','KILL','INCONCLUSIVE'))
);

CREATE TABLE IF NOT EXISTS signals (
    timestamp TEXT,
    variant TEXT,
    direction TEXT CHECK(direction IN ('LONG','SHORT')),
    price DOUBLE,
    strength DOUBLE,
    forward_return_10b DOUBLE,
    forward_return_20b DOUBLE
);
"""


@dataclass(slots=True)
class RawBar:
    timestamp: datetime
    session_date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(slots=True)
class EvaluatedSignal:
    timestamp: str
    variant: str
    direction: str
    split: str
    price: float
    strength: float
    risk: float
    forward_return_10b: float
    forward_return_20b: float
    hit: bool
    realized_r: float


@dataclass(slots=True)
class VariantMatch:
    direction: str
    price: float
    strength: float


def load_bars(path: str | Path) -> list[RawBar]:
    rows: list[RawBar] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            timestamp = datetime.fromisoformat(str(row["ts_event"]))
            rows.append(
                RawBar(
                    timestamp=timestamp,
                    session_date=timestamp.date().isoformat(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=max(int(float(row["volume"])), 1),
                )
            )
    if not rows:
        raise FileNotFoundError(f"No bars found in {path}")
    return rows


def rolling_atr(bars: list[RawBar], period: int = 20) -> list[float]:
    trs: list[float] = []
    atrs: list[float] = []
    prev_close: float | None = None
    for bar in bars:
        high_low = bar.high - bar.low
        if prev_close is None:
            tr = high_low
        else:
            tr = max(high_low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        trs.append(tr)
        window = trs[-period:]
        atrs.append(sum(window) / max(len(window), 1))
        prev_close = bar.close
    return atrs


def rolling_vol_ema(bars: list[RawBar], alpha: float = 0.05) -> list[float]:
    ema_values: list[float] = []
    ema = float(bars[0].volume)
    for bar in bars:
        ema = ema * (1.0 - alpha) + float(bar.volume) * alpha
        ema_values.append(ema)
    return ema_values


def split_bar_dates(bars: list[RawBar], is_ratio: float = DEFAULT_IS_RATIO) -> tuple[set[str], set[str]]:
    is_dates, oos_dates = split_sessions(sorted({bar.session_date for bar in bars}), is_ratio=is_ratio)
    return set(is_dates), set(oos_dates)


def _range(raw: RawBar) -> float:
    return max(raw.high - raw.low, 0.25)


def _body(raw: RawBar) -> float:
    return abs(raw.close - raw.open)


def _body_bounds(raw: RawBar) -> tuple[float, float]:
    return min(raw.open, raw.close), max(raw.open, raw.close)


def _wick_stats(raw: RawBar) -> tuple[float, float, float, float]:
    body_bot, body_top = _body_bounds(raw)
    bar_range = _range(raw)
    upper = max(raw.high - body_top, 0.0)
    lower = max(body_bot - raw.low, 0.0)
    return upper, lower, upper / bar_range * 100.0, lower / bar_range * 100.0


def _close_position(raw: RawBar) -> float:
    return (raw.close - raw.low) / _range(raw)


def _range_ticks(raw: RawBar) -> int:
    return max(int(round(_range(raw) / 0.25)), 1)


def match_variant(
    raw: RawBar,
    prior: RawBar | None,
    variant: str,
    atr: float,
    vol_ema: float,
    abs_cfg: AbsorptionConfig,
    exh_cfg: ExhaustionConfig,
) -> list[VariantMatch]:
    upper_wick, lower_wick, upper_pct, lower_pct = _wick_stats(raw)
    candle_body = _body(raw)
    body_ratio = candle_body / _range(raw)
    close_pos = _close_position(raw)
    tick_count = _range_ticks(raw)
    high_volume = raw.volume > vol_ema * 1.5
    results: list[VariantMatch] = []

    if variant == "ABS_01":
        delta_proxy = body_ratio * 0.10
        if lower_pct >= abs_cfg.absorb_wick_min and delta_proxy < abs_cfg.absorb_delta_max and close_pos >= 0.55:
            results.append(VariantMatch("LONG", raw.low, min(lower_pct / 60.0, 1.0)))
        if upper_pct >= abs_cfg.absorb_wick_min and delta_proxy < abs_cfg.absorb_delta_max and close_pos <= 0.45:
            results.append(VariantMatch("SHORT", raw.high, min(upper_pct / 60.0, 1.0)))
    elif variant == "ABS_02":
        extreme_pct = abs_cfg.passive_extreme_pct * 100.0
        if lower_pct >= max(extreme_pct, abs_cfg.passive_vol_pct * 100.0 * 0.6) and close_pos > 0.55:
            results.append(VariantMatch("LONG", raw.low, min(lower_pct / 100.0, 1.0)))
        if upper_pct >= max(extreme_pct, abs_cfg.passive_vol_pct * 100.0 * 0.6) and close_pos < 0.45:
            results.append(VariantMatch("SHORT", raw.high, min(upper_pct / 100.0, 1.0)))
    elif variant == "ABS_03":
        if raw.volume > vol_ema * abs_cfg.stop_vol_mult:
            if lower_pct >= 20.0 and close_pos > 0.55:
                results.append(VariantMatch("LONG", raw.low + lower_wick * 0.5, min(raw.volume / max(vol_ema * abs_cfg.stop_vol_mult * 2.0, 1.0), 1.0)))
            if upper_pct >= 20.0 and close_pos < 0.45:
                results.append(VariantMatch("SHORT", raw.high - upper_wick * 0.5, min(raw.volume / max(vol_ema * abs_cfg.stop_vol_mult * 2.0, 1.0), 1.0)))
    elif variant == "ABS_04":
        if atr > 0 and raw.volume > vol_ema * abs_cfg.evr_vol_mult and _range(raw) < atr * abs_cfg.evr_range_cap:
            direction = "LONG" if close_pos <= 0.5 else "SHORT"
            results.append(VariantMatch(direction, (raw.high + raw.low) / 2.0, min(raw.volume / max(vol_ema * abs_cfg.evr_vol_mult * 2.0, 1.0), 1.0)))
    elif variant == "EXH_01":
        if tick_count >= 6 and candle_body >= 0.5 and 0.20 <= close_pos <= 0.80:
            results.append(VariantMatch("LONG" if raw.close >= raw.open else "SHORT", raw.close, 0.6))
    elif variant == "EXH_02":
        threshold = exh_cfg.exhaust_wick_min / 3.0
        if upper_pct >= threshold and close_pos <= 0.40:
            results.append(VariantMatch("SHORT", raw.high, min(upper_pct / 20.0, 1.0)))
        if lower_pct >= threshold and close_pos >= 0.60:
            results.append(VariantMatch("LONG", raw.low, min(lower_pct / 20.0, 1.0)))
    elif variant == "EXH_03":
        if tick_count >= max(exh_cfg.cooldown_bars, 5) and raw.volume < vol_ema * 0.85 and _range(raw) >= max(atr * 0.8, 1.0):
            results.append(VariantMatch("LONG" if raw.close >= raw.open else "SHORT", (raw.high + raw.low) / 2.0, min(tick_count / 14.0, 1.0)))
    elif variant == "EXH_04":
        if high_volume and tick_count <= max(int(round(max(atr, 0.25) / 0.25)), 1):
            direction = "LONG" if close_pos >= 0.5 else "SHORT"
            results.append(VariantMatch(direction, (raw.high + raw.low) / 2.0, min(raw.volume / max(vol_ema * 3.0, 1.0), 1.0)))
    elif variant == "EXH_05":
        if candle_body / _range(raw) >= exh_cfg.delta_gate_min_ratio:
            if raw.close > raw.open and upper_pct > lower_pct and upper_wick >= candle_body:
                results.append(VariantMatch("SHORT", raw.close, min(body_ratio, 1.0)))
            if raw.close < raw.open and lower_pct > upper_pct and lower_wick >= candle_body:
                results.append(VariantMatch("LONG", raw.close, min(body_ratio, 1.0)))
    elif variant == "EXH_06" and prior is not None:
        prior_upper, prior_lower, prior_upper_pct, prior_lower_pct = _wick_stats(prior)
        if prior_upper > 0 and upper_wick < prior_upper * exh_cfg.fade_threshold and close_pos <= 0.45:
            results.append(VariantMatch("SHORT", raw.high, max(0.0, 1.0 - (upper_wick / prior_upper))))
        if prior_lower > 0 and lower_wick < prior_lower * exh_cfg.fade_threshold and close_pos >= 0.55:
            results.append(VariantMatch("LONG", raw.low, max(0.0, 1.0 - (lower_wick / prior_lower))))
        if not results and prior_upper_pct > 0 and upper_pct < prior_upper_pct * exh_cfg.fade_threshold and close_pos <= 0.45:
            results.append(VariantMatch("SHORT", raw.high, max(0.0, 1.0 - (upper_pct / prior_upper_pct))))
        if not results and prior_lower_pct > 0 and lower_pct < prior_lower_pct * exh_cfg.fade_threshold and close_pos >= 0.55:
            results.append(VariantMatch("LONG", raw.low, max(0.0, 1.0 - (lower_pct / prior_lower_pct))))
    return results


def risk_distance(raw: RawBar, price: float, direction: str) -> float:
    if direction == "LONG":
        risk = max(price - raw.low, raw.close - raw.low)
    else:
        risk = max(raw.high - price, raw.high - raw.close)
    return max(round(risk, 6), 0.25)


def forward_r_multiple(bars: list[RawBar], index: int, horizon: int, direction: str, price: float, risk: float) -> float:
    if horizon <= 0 or index >= len(bars) - 1:
        return 0.0
    target_index = min(index + horizon, len(bars) - 1)
    move = bars[target_index].close - price
    if direction == "SHORT":
        move *= -1.0
    return round(move / risk, 6)


def is_hit(bars: list[RawBar], index: int, horizon: int, direction: str, price: float, risk: float) -> bool:
    if horizon <= 0:
        return False
    end = min(index + horizon, len(bars) - 1)
    if end <= index:
        return False
    window = bars[index + 1 : end + 1]
    if direction == "LONG":
        best_move = max(bar.high for bar in window) - price
    else:
        best_move = price - min(bar.low for bar in window)
    return best_move >= risk


def summarize_signals(signals: list[EvaluatedSignal]) -> dict[str, Any]:
    is_signals = [signal for signal in signals if signal.split == "is"]
    oos_signals = [signal for signal in signals if signal.split == "oos"]
    all_returns = [signal.realized_r for signal in signals]
    winners = [value for value in all_returns if value > 0]
    losers = [value for value in all_returns if value <= 0]
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 0.0
    rr = avg_win / avg_loss if avg_loss > 0 else 0.0
    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    pf = gross_profit / gross_loss if gross_loss > 0 else 99.0 if gross_profit > 0 else 0.0
    is_hit_rate = sum(signal.hit for signal in is_signals) / len(is_signals) if is_signals else 0.0
    oos_hit_rate = sum(signal.hit for signal in oos_signals) / len(oos_signals) if oos_signals else 0.0
    n_oos = len(oos_signals)
    if n_oos < 30:
        verdict = "INCONCLUSIVE"
    elif oos_hit_rate >= 0.55 and rr >= 1.5:
        verdict = "KEEP"
    elif oos_hit_rate < 0.50:
        verdict = "KILL"
    else:
        verdict = "INCONCLUSIVE"
    return {
        "is_hit_rate": round(is_hit_rate, 6),
        "oos_hit_rate": round(oos_hit_rate, 6),
        "rr": round(rr, 6),
        "pf": round(min(pf, 99.0), 6),
        "n_is": len(is_signals),
        "n_oos": n_oos,
        "verdict": verdict,
    }


def extract_variant_signals(bars: list[RawBar], variant: str, bars_forward: int, is_dates: set[str]) -> list[EvaluatedSignal]:
    atrs = rolling_atr(bars)
    vol_emas = rolling_vol_ema(bars)
    abs_config = AbsorptionConfig()
    exh_config = ExhaustionConfig()
    prior_raw: RawBar | None = None
    prior_session: str | None = None
    extracted: list[EvaluatedSignal] = []

    for index, raw in enumerate(bars):
        if raw.session_date != prior_session:
            reset_cooldowns()
            prior_raw = None
            prior_session = raw.session_date
        atr = atrs[index]
        vol_ema = vol_emas[index]
        matches = match_variant(raw, prior_raw, variant, atr, vol_ema, abs_config, exh_config)
        prior_raw = raw

        split = "is" if raw.session_date in is_dates else "oos"
        for match in matches:
            risk = risk_distance(raw, match.price, match.direction)
            evaluated = EvaluatedSignal(
                timestamp=raw.timestamp.isoformat(),
                variant=variant,
                direction=match.direction,
                split=split,
                price=round(match.price, 6),
                strength=round(float(match.strength), 6),
                risk=risk,
                forward_return_10b=forward_r_multiple(bars, index, 10, match.direction, match.price, risk),
                forward_return_20b=forward_r_multiple(bars, index, 20, match.direction, match.price, risk),
                hit=is_hit(bars, index, bars_forward, match.direction, match.price, risk),
                realized_r=forward_r_multiple(bars, index, bars_forward, match.direction, match.price, risk),
            )
            extracted.append(evaluated)
    return extracted


def create_db(path: str) -> duckdb.DuckDBPyConnection:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = duckdb.connect(path)
    conn.execute(SCHEMA_SQL)
    return conn


def persist_results(path: str, variant: str, summary: dict[str, Any], signals: list[EvaluatedSignal]) -> None:
    conn = create_db(path)
    try:
        conn.execute("DELETE FROM signals WHERE variant = ?", [variant])
        if signals:
            conn.executemany(
                "INSERT INTO signals (timestamp, variant, direction, price, strength, forward_return_10b, forward_return_20b) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        signal.timestamp,
                        signal.variant,
                        signal.direction,
                        signal.price,
                        signal.strength,
                        signal.forward_return_10b,
                        signal.forward_return_20b,
                    )
                    for signal in signals
                ],
            )
        conn.execute(
            "INSERT OR REPLACE INTO variants (name, is_hit_rate, oos_hit_rate, rr, pf, n_is, n_oos, verdict) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                variant,
                summary["is_hit_rate"],
                summary["oos_hit_rate"],
                summary["rr"],
                summary["pf"],
                summary["n_is"],
                summary["n_oos"],
                summary["verdict"],
            ],
        )
    finally:
        conn.close()


def run_variant_evaluator(data_path: str | Path, variant: str, bars_forward: int, is_ratio: float = DEFAULT_IS_RATIO) -> dict[str, Any]:
    if bars_forward <= 0:
        raise ValueError("--bars-forward must be > 0")
    bars = load_bars(data_path)
    is_dates, _oos_dates = split_bar_dates(bars, is_ratio=is_ratio)
    signals = extract_variant_signals(bars, variant=variant, bars_forward=bars_forward, is_dates=is_dates)
    summary = summarize_signals(signals)
    persist_results(DB_PATH, variant, summary, signals)
    return {
        "variant": variant,
        "bars_forward": bars_forward,
        "data": str(data_path),
        "db_path": DB_PATH,
        **summary,
        "signals_written": len(signals),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DEEP6 isolated variant evaluator")
    parser.add_argument("--data", required=True, help="Path to OHLCV CSV data")
    parser.add_argument("--variant", required=True, choices=SUPPORTED_VARIANTS, help="Signal variant to evaluate")
    parser.add_argument("--bars-forward", required=True, type=int, help="Forward bars horizon for hit-rate evaluation")
    parser.add_argument("--is-ratio", type=float, default=DEFAULT_IS_RATIO, help="In-sample split ratio")
    args = parser.parse_args(argv)

    try:
        result = run_variant_evaluator(args.data, args.variant, args.bars_forward, is_ratio=args.is_ratio)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"Variant evaluator failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
