from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
TELEGRAM_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
SIGNALS_PATH = ROOT / "data" / "backtests" / "signal_events.csv"
BARS_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
TICK_SIZE = 0.25
N_GRID = [5, 10, 15, 30]
X_GRID = [10, 20, 40]
S_GRID = [0.01, 0.05, 0.10, 0.20]
HORIZONS = [5, 10, 15, 30]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest Telegram MAD absorption alerts combined with DEEP6 absorption signals.",
    )
    parser.add_argument("--telegram-path", type=Path, default=TELEGRAM_PATH)
    parser.add_argument("--signals-path", type=Path, default=SIGNALS_PATH)
    parser.add_argument("--bars-path", type=Path, default=BARS_PATH)
    parser.add_argument("--min-trades", type=int, default=10, help="Minimum trades required when ranking parameter sets.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional directory for CSV exports.")
    return parser.parse_args()


def _format_float(value: Any, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "-"
    value = float(value)
    if np.isinf(value):
        return "inf"
    return f"{value:.{digits}f}"


def _print_table(title: str, df: pd.DataFrame, digits: int = 2) -> None:
    print(f"\n{title}")
    if df.empty:
        print("(no rows)")
        return
    display = df.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: _format_float(value, digits))
    print(display.to_string(index=False))


def _trade_stats(returns_ticks: np.ndarray) -> dict[str, float | int | None]:
    finite = returns_ticks[np.isfinite(returns_ticks)]
    if len(finite) == 0:
        return {
            "trades": 0,
            "win_rate": None,
            "avg_return_ticks": None,
            "profit_factor": None,
        }

    wins = finite[finite > 0]
    losses = finite[finite < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else None
    else:
        profit_factor = gross_profit / gross_loss

    return {
        "trades": int(len(finite)),
        "win_rate": float((finite > 0).mean() * 100.0),
        "avg_return_ticks": float(finite.mean()),
        "profit_factor": profit_factor,
    }


def load_bars(path: Path) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, dict[pd.Timestamp, int]]:
    bars = pd.read_csv(path, usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"])
    bars["timestamp_utc"] = pd.to_datetime(bars["ts_event"], utc=True)
    bars = bars.sort_values("timestamp_utc").reset_index(drop=True)
    bars["bar_index"] = np.arange(len(bars), dtype=int)
    closes = bars["close"].to_numpy(dtype=float)
    timestamps_ns = bars["timestamp_utc"].astype("int64").to_numpy()
    timestamp_to_index = dict(zip(bars["timestamp_utc"], bars["bar_index"], strict=False))
    return bars, closes, timestamps_ns, timestamp_to_index


def load_telegram_alerts(path: Path, bar_timestamps_ns: np.ndarray, closes: np.ndarray, max_horizon: int) -> pd.DataFrame:
    pattern = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    messages = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for message in messages:
        raw_text = (message.get("text") or "").strip()
        match = pattern.match(raw_text)
        if not match:
            continue
        timestamp_utc = pd.Timestamp(message["date"])
        timestamp_utc = timestamp_utc.tz_localize("UTC") if timestamp_utc.tzinfo is None else timestamp_utc.tz_convert("UTC")
        rows.append(
            {
                "message_id": int(message["message_id"]),
                "timestamp_utc": timestamp_utc,
                "alert_price": float(match.group(1)),
            }
        )

    alerts = pd.DataFrame(rows).sort_values("timestamp_utc").reset_index(drop=True)
    alerts["bar_index"] = np.searchsorted(
        bar_timestamps_ns,
        alerts["timestamp_utc"].astype("int64").to_numpy(),
        side="right",
    ) - 1
    alerts["entry_index"] = alerts["bar_index"] + 1

    valid = (alerts["bar_index"] >= 0) & (alerts["entry_index"] + max_horizon < len(closes))
    alerts = alerts[valid].copy().reset_index(drop=True)
    anchor_close = closes[alerts["bar_index"].to_numpy(dtype=int)]
    alerts["anchor_close"] = anchor_close
    alerts["baseline_direction"] = np.where(
        anchor_close > alerts["alert_price"],
        1,
        np.where(anchor_close < alerts["alert_price"], -1, 0),
    )
    return alerts


def load_absorption_signals(path: Path, timestamp_to_index: dict[pd.Timestamp, int], max_horizon: int, bar_count: int) -> pd.DataFrame:
    signals = pd.read_csv(
        path,
        usecols=["bar_ts", "signal_id", "category", "direction", "strength", "score_final", "score_tier", "bar_close"],
    )
    signals = signals[signals["category"] == "absorption"].copy()
    signals["bar_ts_utc"] = pd.to_datetime(signals["bar_ts"], utc=True)
    signals["bar_index"] = signals["bar_ts_utc"].map(timestamp_to_index)
    signals = signals[signals["bar_index"].notna()].copy()
    signals["bar_index"] = signals["bar_index"].astype(int)
    signals["direction"] = signals["direction"].astype(int)
    signals["strength"] = signals["strength"].astype(float)
    signals["bar_close"] = signals["bar_close"].astype(float)
    valid = signals["bar_index"] + max_horizon < bar_count
    signals = signals[valid].sort_values("bar_ts_utc").reset_index(drop=True)
    return signals


def evaluate_telegram_baseline(alerts: pd.DataFrame, closes: np.ndarray) -> pd.DataFrame:
    usable = alerts[alerts["baseline_direction"] != 0].copy()
    entry_idx = usable["entry_index"].to_numpy(dtype=int)
    direction = usable["baseline_direction"].to_numpy(dtype=int)

    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        returns = direction * (closes[entry_idx + horizon] - closes[entry_idx]) / TICK_SIZE
        stats = _trade_stats(returns)
        rows.append(
            {
                "model": "telegram_alone",
                "strength_threshold": "n/a",
                "horizon_bars": horizon,
                **stats,
            }
        )
    return pd.DataFrame(rows)


def evaluate_deep6_baseline(signals: pd.DataFrame, closes: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    thresholds = [0.0, *S_GRID]
    for threshold in thresholds:
        subset = signals[signals["strength"] >= threshold].copy()
        entry_idx = subset["bar_index"].to_numpy(dtype=int)
        direction = subset["direction"].to_numpy(dtype=int)
        for horizon in HORIZONS:
            returns = direction * (closes[entry_idx + horizon] - closes[entry_idx]) / TICK_SIZE
            stats = _trade_stats(returns)
            rows.append(
                {
                    "model": "deep6_alone",
                    "strength_threshold": threshold,
                    "horizon_bars": horizon,
                    **stats,
                }
            )
    return pd.DataFrame(rows)


def evaluate_random_baseline(closes: np.ndarray) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        raw = (closes[horizon:] - closes[:-horizon]) / TICK_SIZE
        returns = np.concatenate([raw, -raw])
        stats = _trade_stats(returns)
        rows.append(
            {
                "model": "random_entry_random_direction",
                "strength_threshold": "n/a",
                "horizon_bars": horizon,
                **stats,
            }
        )
    return pd.DataFrame(rows)


def evaluate_combined_models(alerts: pd.DataFrame, signals: pd.DataFrame, closes: np.ndarray) -> pd.DataFrame:
    alert_bar_idx = alerts["bar_index"].to_numpy(dtype=int)
    alert_entry_idx = alerts["entry_index"].to_numpy(dtype=int)
    alert_prices = alerts["alert_price"].to_numpy(dtype=float)
    alert_times = alerts["timestamp_utc"].to_numpy()

    signal_bar_idx = signals["bar_index"].to_numpy(dtype=int)
    signal_times = signals["bar_ts_utc"].to_numpy()
    signal_close = signals["bar_close"].to_numpy(dtype=float)
    signal_direction = signals["direction"].to_numpy(dtype=int)
    signal_strength = signals["strength"].to_numpy(dtype=float)

    rows: list[dict[str, Any]] = []
    max_horizon = max(HORIZONS)

    for sequence in ("telegram_first", "deep6_first"):
        for n_bars in N_GRID:
            for x_ticks in X_GRID:
                for strength_threshold in S_GRID:
                    eligible = signal_strength >= strength_threshold
                    matched_returns: dict[int, list[float]] = {horizon: [] for horizon in HORIZONS}
                    lags: list[int] = []
                    price_diffs: list[float] = []
                    matched_alert_times: list[pd.Timestamp] = []
                    matched_signal_times: list[pd.Timestamp] = []

                    for idx, bar_close, direction, strength, sig_ts in zip(
                        signal_bar_idx[eligible],
                        signal_close[eligible],
                        signal_direction[eligible],
                        signal_strength[eligible],
                        signal_times[eligible],
                        strict=False,
                    ):
                        price_distance_ticks = np.abs(alert_prices - bar_close) / TICK_SIZE
                        if sequence == "telegram_first":
                            candidate_mask = (alert_bar_idx < idx) & (alert_bar_idx >= idx - n_bars) & (price_distance_ticks <= x_ticks)
                        else:
                            candidate_mask = (alert_bar_idx > idx) & (alert_bar_idx <= idx + n_bars) & (price_distance_ticks <= x_ticks)

                        candidate_idx = np.flatnonzero(candidate_mask)
                        if len(candidate_idx) == 0:
                            continue

                        if sequence == "telegram_first":
                            lags_for_candidates = idx - alert_bar_idx[candidate_idx]
                            entry_index = idx
                        else:
                            lags_for_candidates = alert_bar_idx[candidate_idx] - idx
                            earliest_entry_candidates = alert_entry_idx[candidate_idx]
                            valid_entry = earliest_entry_candidates + max_horizon < len(closes)
                            candidate_idx = candidate_idx[valid_entry]
                            lags_for_candidates = lags_for_candidates[valid_entry]
                            if len(candidate_idx) == 0:
                                continue
                            entry_index = int(alert_entry_idx[candidate_idx[0]])

                        distance_for_candidates = price_distance_ticks[candidate_idx]
                        best_local_pos = np.lexsort((distance_for_candidates, lags_for_candidates))[0]
                        best_alert_idx = int(candidate_idx[best_local_pos])
                        if sequence == "deep6_first":
                            entry_index = int(alert_entry_idx[best_alert_idx])

                        lags.append(int(lags_for_candidates[best_local_pos]))
                        price_diffs.append(float(distance_for_candidates[best_local_pos]))
                        matched_alert_times.append(pd.Timestamp(alert_times[best_alert_idx]))
                        matched_signal_times.append(pd.Timestamp(sig_ts))

                        for horizon in HORIZONS:
                            trade_return = direction * (closes[entry_index + horizon] - closes[entry_index]) / TICK_SIZE
                            matched_returns[horizon].append(float(trade_return))

                    row: dict[str, Any] = {
                        "sequence": sequence,
                        "n_bars": n_bars,
                        "x_ticks": x_ticks,
                        "strength_threshold": strength_threshold,
                        "trades": len(lags),
                        "avg_bar_lag": float(np.mean(lags)) if lags else None,
                        "avg_price_diff_ticks": float(np.mean(price_diffs)) if price_diffs else None,
                        "matched_alert_start": min(matched_alert_times).isoformat() if matched_alert_times else None,
                        "matched_alert_end": max(matched_alert_times).isoformat() if matched_alert_times else None,
                        "matched_signal_start": min(matched_signal_times).isoformat() if matched_signal_times else None,
                        "matched_signal_end": max(matched_signal_times).isoformat() if matched_signal_times else None,
                    }

                    avg_returns_for_score: list[float] = []
                    for horizon in HORIZONS:
                        stats = _trade_stats(np.asarray(matched_returns[horizon], dtype=float))
                        row[f"wr_{horizon}b"] = stats["win_rate"]
                        row[f"avg_{horizon}b_ticks"] = stats["avg_return_ticks"]
                        row[f"pf_{horizon}b"] = stats["profit_factor"]
                        if stats["avg_return_ticks"] is not None:
                            avg_returns_for_score.append(float(stats["avg_return_ticks"]))

                    row["avg_return_mean_ticks"] = float(np.mean(avg_returns_for_score)) if avg_returns_for_score else None
                    row["positive_horizons"] = int(sum(value > 0 for value in avg_returns_for_score)) if avg_returns_for_score else 0
                    rows.append(row)

    return pd.DataFrame(rows)


def build_best_of_table(results: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sequence in ("telegram_first", "deep6_first"):
        for horizon in HORIZONS:
            filtered = results[(results["sequence"] == sequence) & (results["trades"] >= min_trades)].copy()
            if filtered.empty:
                filtered = results[results["sequence"] == sequence].copy()
            if filtered.empty:
                continue
            best = filtered.sort_values(
                [f"avg_{horizon}b_ticks", "trades", f"pf_{horizon}b"],
                ascending=[False, False, False],
            ).iloc[0]
            rows.append(
                {
                    "sequence": sequence,
                    "horizon_bars": horizon,
                    "n_bars": int(best["n_bars"]),
                    "x_ticks": int(best["x_ticks"]),
                    "strength_threshold": float(best["strength_threshold"]),
                    "trades": int(best["trades"]),
                    "win_rate": best[f"wr_{horizon}b"],
                    "avg_return_ticks": best[f"avg_{horizon}b_ticks"],
                    "profit_factor": best[f"pf_{horizon}b"],
                }
            )
    return pd.DataFrame(rows)


def build_overall_best_table(results: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for sequence in ("telegram_first", "deep6_first"):
        filtered = results[(results["sequence"] == sequence) & (results["trades"] >= min_trades)].copy()
        if filtered.empty:
            filtered = results[results["sequence"] == sequence].copy()
        if filtered.empty:
            continue
        best = filtered.sort_values(
            ["avg_return_mean_ticks", "positive_horizons", "trades"],
            ascending=[False, False, False],
        ).iloc[0]
        rows.append(
            {
                "sequence": sequence,
                "n_bars": int(best["n_bars"]),
                "x_ticks": int(best["x_ticks"]),
                "strength_threshold": float(best["strength_threshold"]),
                "trades": int(best["trades"]),
                "positive_horizons": int(best["positive_horizons"]),
                "avg_return_mean_ticks": best["avg_return_mean_ticks"],
                "avg_5b_ticks": best["avg_5b_ticks"],
                "avg_10b_ticks": best["avg_10b_ticks"],
                "avg_15b_ticks": best["avg_15b_ticks"],
                "avg_30b_ticks": best["avg_30b_ticks"],
            }
        )
    return pd.DataFrame(rows)


def build_selected_model_comparison(
    overall_best: pd.DataFrame,
    telegram_baseline: pd.DataFrame,
    deep6_baseline: pd.DataFrame,
    random_baseline: pd.DataFrame,
    combined_results: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    telegram_lookup = telegram_baseline.set_index("horizon_bars")
    random_lookup = random_baseline.set_index("horizon_bars")
    deep6_lookup = deep6_baseline.set_index(["strength_threshold", "horizon_bars"])

    for best_row in overall_best.itertuples(index=False):
        combo = combined_results[
            (combined_results["sequence"] == best_row.sequence)
            & (combined_results["n_bars"] == best_row.n_bars)
            & (combined_results["x_ticks"] == best_row.x_ticks)
            & (combined_results["strength_threshold"] == best_row.strength_threshold)
        ].iloc[0]

        for horizon in HORIZONS:
            rows.append(
                {
                    "selected_model": best_row.sequence,
                    "comparison_model": "combined",
                    "strength_threshold": best_row.strength_threshold,
                    "horizon_bars": horizon,
                    "trades": int(combo["trades"]),
                    "win_rate": combo[f"wr_{horizon}b"],
                    "avg_return_ticks": combo[f"avg_{horizon}b_ticks"],
                    "profit_factor": combo[f"pf_{horizon}b"],
                }
            )
            rows.append(
                {
                    "selected_model": best_row.sequence,
                    "comparison_model": "telegram_alone",
                    "strength_threshold": "n/a",
                    "horizon_bars": horizon,
                    "trades": int(telegram_lookup.loc[horizon, "trades"]),
                    "win_rate": telegram_lookup.loc[horizon, "win_rate"],
                    "avg_return_ticks": telegram_lookup.loc[horizon, "avg_return_ticks"],
                    "profit_factor": telegram_lookup.loc[horizon, "profit_factor"],
                }
            )
            rows.append(
                {
                    "selected_model": best_row.sequence,
                    "comparison_model": f"deep6_alone_s>={best_row.strength_threshold:.2f}",
                    "strength_threshold": best_row.strength_threshold,
                    "horizon_bars": horizon,
                    "trades": int(deep6_lookup.loc[(best_row.strength_threshold, horizon), "trades"]),
                    "win_rate": deep6_lookup.loc[(best_row.strength_threshold, horizon), "win_rate"],
                    "avg_return_ticks": deep6_lookup.loc[(best_row.strength_threshold, horizon), "avg_return_ticks"],
                    "profit_factor": deep6_lookup.loc[(best_row.strength_threshold, horizon), "profit_factor"],
                }
            )
            rows.append(
                {
                    "selected_model": best_row.sequence,
                    "comparison_model": "random_entry",
                    "strength_threshold": "n/a",
                    "horizon_bars": horizon,
                    "trades": int(random_lookup.loc[horizon, "trades"]),
                    "win_rate": random_lookup.loc[horizon, "win_rate"],
                    "avg_return_ticks": random_lookup.loc[horizon, "avg_return_ticks"],
                    "profit_factor": random_lookup.loc[horizon, "profit_factor"],
                }
            )

    return pd.DataFrame(rows)


def export_tables(output_dir: Path, **tables: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(output_dir / f"{name}.csv", index=False)


def main() -> None:
    args = parse_args()
    max_horizon = max(HORIZONS)

    bars, closes, bar_timestamps_ns, timestamp_to_index = load_bars(args.bars_path)
    alerts = load_telegram_alerts(args.telegram_path, bar_timestamps_ns, closes, max_horizon)
    signals = load_absorption_signals(args.signals_path, timestamp_to_index, max_horizon, len(bars))

    telegram_baseline = evaluate_telegram_baseline(alerts, closes)
    deep6_baseline = evaluate_deep6_baseline(signals, closes)
    random_baseline = evaluate_random_baseline(closes)
    combined_results = evaluate_combined_models(alerts, signals, closes)
    best_by_horizon = build_best_of_table(combined_results, args.min_trades)
    overall_best = build_overall_best_table(combined_results, args.min_trades)
    selected_comparison = build_selected_model_comparison(
        overall_best,
        telegram_baseline,
        deep6_baseline,
        random_baseline,
        combined_results,
    )

    coverage = pd.DataFrame(
        [
            {
                "bars": int(len(bars)),
                "telegram_alerts_raw": int(len(json.loads(args.telegram_path.read_text(encoding='utf-8')))),
                "telegram_absorption_alerts": int(len(alerts)),
                "telegram_directional_baseline_trades": int((alerts["baseline_direction"] != 0).sum()),
                "deep6_absorption_signals": int(len(signals)),
                "signal_date_start": signals["bar_ts_utc"].min().isoformat(),
                "signal_date_end": signals["bar_ts_utc"].max().isoformat(),
            }
        ]
    )

    _print_table("DATA COVERAGE", coverage)
    _print_table("TELEGRAM ALONE BASELINE", telegram_baseline)
    _print_table("DEEP6 ALONE BASELINE", deep6_baseline)
    _print_table("RANDOM ENTRY BASELINE", random_baseline)
    _print_table(f"BEST PARAMETER SET PER HORIZON (min_trades={args.min_trades})", best_by_horizon)
    _print_table(f"OVERALL BEST COMBINED CONFIG PER SEQUENCE (min_trades={args.min_trades})", overall_best)
    _print_table("SELECTED MODEL VS BASELINES", selected_comparison)

    if args.output_dir is not None:
        export_tables(
            args.output_dir,
            coverage=coverage,
            telegram_baseline=telegram_baseline,
            deep6_baseline=deep6_baseline,
            random_baseline=random_baseline,
            combined_grid=combined_results,
            best_by_horizon=best_by_horizon,
            overall_best=overall_best,
            selected_comparison=selected_comparison,
        )
        print(f"\nSaved CSV outputs to: {args.output_dir}")


if __name__ == "__main__":
    main()
