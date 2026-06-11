#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round40_drawdown_mae_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
PATH_WINDOWS = tuple(range(1, 31))
STOP_LEVELS = (10, 20, 30, 40, 50)
OPTIMAL_STOP_LEVELS = tuple(range(5, 81, 5))

TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
LUNCH_START_MINUTES = 150
LUNCH_END_MINUTES = 270

Predicate = Callable[[pd.DataFrame], pd.Series]
DirectionFn = Callable[[pd.DataFrame], int | pd.Series]


@dataclass(frozen=True)
class SetupSpec:
    code: str
    label: str
    dataset_key: str
    direction_label: str
    predicate: Predicate
    direction_fn: DirectionFn


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


def fmt_float(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:,.2f}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value * 100:.1f}%"


def fmt_ticks(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:+,.2f}t"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def load_events() -> pd.DataFrame:
    dtypes = {
        "session_date": "string",
        "signal_id": "string",
        "category": "string",
        "direction": "string",
        "bar_index": "int32",
        "global_index": "int32",
        "bar_delta": "float64",
        "bar_volume": "float64",
    }
    cols = [
        "session_date",
        "bar_ts",
        "bar_index",
        "global_index",
        "signal_id",
        "category",
        "direction",
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)

    numeric_cols = [
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
    ]
    for col in numeric_cols:
        events[col] = pd.to_numeric(events[col], errors="coerce")

    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    events = events[events["bar_ts"].notna()].copy()
    events["event_direction_sign"] = direction_to_sign(events["direction"])
    return events.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    return bars.sort_values("ts_event").reset_index(drop=True)


def prepare_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()

    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")

    by_session = bars.groupby("session_date", sort=False)
    for window in PATH_WINDOWS:
        bars[f"fwd_close_{window}b"] = by_session["close"].shift(-window)

    return bars.reset_index(drop=True)


def build_timeframe_context(bars_1m: pd.DataFrame) -> dict[int, pd.DataFrame]:
    context: dict[int, pd.DataFrame] = {}
    base = bars_1m.set_index("ts_event")

    for tf in TIMEFRAMES:
        tf_bars = (
            base.resample(f"{tf}min")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna()
            .reset_index()
        )
        tf_bars["range"] = tf_bars["high"] - tf_bars["low"]
        tf_bars["trend_sign"] = np.sign(tf_bars["close"] - tf_bars["open"]).astype(int)
        context[tf] = tf_bars

    return context


def build_bar_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby("global_index", as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            global_index=("global_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    return observations


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    absorption = events.loc[events["category"].eq("absorption") & events["event_direction_sign"].ne(0)].copy()
    observations = (
        absorption.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            global_index=("global_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            signal_count=("signal_id", "nunique"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_score_observations(events: pd.DataFrame) -> pd.DataFrame:
    scored = events.loc[events["event_direction_sign"].ne(0)].copy()
    observations = (
        scored.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            global_index=("global_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def attach_timeframe_context(observations: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    df = observations.copy()
    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        df[bucket_col] = df["bar_ts"].dt.floor(f"{tf}min")
        renamed = ctx.rename(
            columns={
                "ts_event": bucket_col,
                "open": f"open_{tf}m",
                "high": f"high_{tf}m",
                "low": f"low_{tf}m",
                "close": f"close_{tf}m",
                "volume": f"volume_{tf}m",
                "range": f"range_{tf}m",
                "trend_sign": f"trend_sign_{tf}m",
            }
        )
        df = df.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def attach_rth_context(observations: pd.DataFrame, rth_bars: pd.DataFrame) -> pd.DataFrame:
    merge_cols = ["ts_event"] + [f"fwd_close_{window}b" for window in PATH_WINDOWS]
    context = rth_bars[merge_cols].rename(columns={"ts_event": "bar_ts"})
    return observations.merge(context, on="bar_ts", how="left", validate="many_to_one").reset_index(drop=True)


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_not_lunch"] = ~(
        out["minutes_since_930"].ge(LUNCH_START_MINUTES) & out["minutes_since_930"].lt(LUNCH_END_MINUTES)
    )
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    out["is_not_lunch"] = out["is_not_lunch"].fillna(False).astype(bool)
    return out


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["is_doji"] = out["is_doji"].fillna(False).astype(bool)
    out["is_volume_spike_3x"] = out["is_volume_spike_3x"].fillna(False).astype(bool)
    return out


def compute_cvd_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["cvd"] = by_session["bar_delta"].cumsum()
    by_session = out.groupby("session_date", sort=False)

    out["prior_session_price_high"] = by_session["bar_high"].transform(lambda s: s.cummax().shift(1))
    out["prior_session_price_low"] = by_session["bar_low"].transform(lambda s: s.cummin().shift(1))
    out["prior_cvd_high"] = by_session["cvd"].transform(lambda s: s.cummax().shift(1))
    out["prior_cvd_low"] = by_session["cvd"].transform(lambda s: s.cummin().shift(1))

    out["is_price_new_session_high"] = out["prior_session_price_high"].notna() & out["bar_high"].gt(out["prior_session_price_high"])
    out["is_price_new_session_low"] = out["prior_session_price_low"].notna() & out["bar_low"].lt(out["prior_session_price_low"])

    out["is_bearish_cvd_divergence"] = (
        out["is_price_new_session_high"]
        & out["prior_cvd_high"].notna()
        & out["cvd"].lt(out["prior_cvd_high"])
    )
    out["is_bullish_cvd_divergence"] = (
        out["is_price_new_session_low"]
        & out["prior_cvd_low"].notna()
        & out["cvd"].gt(out["prior_cvd_low"])
    )
    out["divergence_sign"] = np.select(
        [out["is_bullish_cvd_divergence"], out["is_bearish_cvd_divergence"]],
        [1, -1],
        default=0,
    ).astype(int)
    out["is_cvd_divergence"] = out["divergence_sign"].ne(0)

    bool_cols = ["is_bearish_cvd_divergence", "is_bullish_cvd_divergence", "is_cvd_divergence"]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return pd.Series(np.sign(series), index=df.index).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    is_60m_extreme = ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))
    is_15m_trend_aligned = direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])
    return is_60m_extreme & is_15m_trend_aligned


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_setup_specs() -> list[SetupSpec]:
    return [
        SetupSpec(
            code="A",
            label="60m + 15m + NOT killers + first_hour",
            dataset_key="bar",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="B",
            label="Doji + 60m + 15m + NOT killers",
            dataset_key="bar",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_doji"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="C",
            label="CVD divergence + 60m + 15m",
            dataset_key="bar",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="D",
            label="absorption + 60m + 15m + NOT lunch",
            dataset_key="absorption",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & df["is_not_lunch"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="E",
            label="score >= 60 + 60m + 15m + first_hour + NOT killers",
            dataset_key="score",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & df["max_score_final"].ge(60)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
    ]


def build_setup_sample(source_df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(source_df).fillna(False)
    sample = source_df.loc[mask].copy()
    sample["trade_sign"] = normalize_direction(spec.direction_fn(source_df), sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()

    path_cols = [f"fwd_close_{window}b" for window in PATH_WINDOWS]
    sample = sample.dropna(subset=path_cols).copy()
    return sample.reset_index(drop=True)


def path_return_matrix(sample: pd.DataFrame) -> np.ndarray:
    path_cols = [f"fwd_close_{window}b" for window in PATH_WINDOWS]
    path_prices = sample[path_cols].to_numpy(dtype=float)
    entry = sample["bar_close"].to_numpy(dtype=float)[:, None]
    trade_sign = sample["trade_sign"].to_numpy(dtype=float)[:, None]
    return trade_sign * ((path_prices - entry) / TICK_SIZE)


def longest_underwater_run(drawdown: np.ndarray) -> int:
    longest = 0
    current = 0
    for value in drawdown:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def average_drawdown_depth(drawdown: np.ndarray) -> float:
    episode_depths: list[float] = []
    current_depth = 0.0
    in_drawdown = False

    for value in drawdown:
        if value < 0:
            current_depth = min(current_depth, float(value))
            in_drawdown = True
            continue

        if in_drawdown:
            episode_depths.append(current_depth)
            current_depth = 0.0
            in_drawdown = False

    if in_drawdown:
        episode_depths.append(current_depth)

    if not episode_depths:
        return 0.0
    return float(np.mean(episode_depths))


def simulate_stop(path_returns: np.ndarray, stop_ticks: float) -> np.ndarray:
    mae = path_returns.min(axis=1)
    final_returns = path_returns[:, -1]
    return np.where(mae <= -stop_ticks, -stop_ticks, final_returns)


def build_stop_rows(path_returns: np.ndarray, final_returns: np.ndarray, mae: np.ndarray) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    winner_mask = final_returns > 0

    for stop_ticks in STOP_LEVELS:
        winner_stop_out = np.nan
        if winner_mask.any():
            winner_stop_out = float((mae[winner_mask] <= -stop_ticks).mean())

        realized = simulate_stop(path_returns, float(stop_ticks))
        realized_series = pd.Series(realized)
        win_mask = realized > 0
        avg_win = float(realized[win_mask].mean()) if win_mask.any() else 0.0
        avg_loss = float(-realized[~win_mask].mean()) if (~win_mask).any() else 0.0
        win_rate = float(win_mask.mean()) if len(realized) else np.nan
        expectancy = float(realized.mean()) if len(realized) else np.nan

        rows.append(
            {
                "stop_ticks": float(stop_ticks),
                "winner_stop_out": winner_stop_out,
                "win_rate": win_rate,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "expectancy": expectancy,
                "profit_factor": profit_factor(realized_series),
            }
        )

    return rows


def find_optimal_stop(path_returns: np.ndarray) -> dict[str, float]:
    best_row: dict[str, float] | None = None

    for stop_ticks in OPTIMAL_STOP_LEVELS:
        realized = simulate_stop(path_returns, float(stop_ticks))
        win_mask = realized > 0
        avg_win = float(realized[win_mask].mean()) if win_mask.any() else 0.0
        avg_loss = float(-realized[~win_mask].mean()) if (~win_mask).any() else 0.0
        win_rate = float(win_mask.mean()) if len(realized) else np.nan
        expectancy = float(realized.mean()) if len(realized) else np.nan

        row = {
            "stop_ticks": float(stop_ticks),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
        }

        if best_row is None:
            best_row = row
            continue

        best_key = (float(best_row["expectancy"]), float(best_row["win_rate"]), -float(best_row["stop_ticks"]))
        row_key = (float(row["expectancy"]), float(row["win_rate"]), -float(row["stop_ticks"]))
        if row_key > best_key:
            best_row = row

    if best_row is None:
        return {
            "stop_ticks": np.nan,
            "win_rate": np.nan,
            "avg_win": np.nan,
            "avg_loss": np.nan,
            "expectancy": np.nan,
        }
    return best_row


def analyze_setup(sample: pd.DataFrame) -> dict[str, object]:
    if sample.empty:
        return {
            "n": 0,
            "win_rate": np.nan,
            "profit_factor": np.nan,
            "mae_median": np.nan,
            "mae_mean": np.nan,
            "mae_worst": np.nan,
            "mfe_median": np.nan,
            "mfe_mean": np.nan,
            "mfe_best": np.nan,
            "max_drawdown": np.nan,
            "longest_drawdown": np.nan,
            "avg_drawdown_depth": np.nan,
            "stop_rows": [],
            "optimal_stop": {"stop_ticks": np.nan, "expectancy": np.nan},
        }

    path_returns = path_return_matrix(sample)
    final_returns = path_returns[:, -1]
    mae = path_returns.min(axis=1)
    mfe = path_returns.max(axis=1)

    equity = np.cumsum(final_returns)
    running_peak = np.maximum.accumulate(np.concatenate(([0.0], equity)))
    drawdown = equity - running_peak[1:]

    return {
        "n": int(len(sample)),
        "win_rate": float((final_returns > 0).mean()),
        "profit_factor": profit_factor(pd.Series(final_returns)),
        "mae_median": float(np.median(mae)),
        "mae_mean": float(np.mean(mae)),
        "mae_worst": float(np.min(mae)),
        "mfe_median": float(np.median(mfe)),
        "mfe_mean": float(np.mean(mfe)),
        "mfe_best": float(np.max(mfe)),
        "max_drawdown": float(np.min(drawdown)) if len(drawdown) else 0.0,
        "longest_drawdown": longest_underwater_run(drawdown),
        "avg_drawdown_depth": average_drawdown_depth(drawdown),
        "stop_rows": build_stop_rows(path_returns, final_returns, mae),
        "optimal_stop": find_optimal_stop(path_returns),
    }


def render_setup_section(spec: SetupSpec, result: dict[str, object]) -> list[str]:
    stop_map = {int(row["stop_ticks"]): row for row in result["stop_rows"]}
    optimal_stop = result["optimal_stop"]
    optimal_stop_label = "nan"
    if not pd.isna(optimal_stop["stop_ticks"]):
        optimal_stop_label = f"-{int(optimal_stop['stop_ticks'])}t"

    return [
        f"Setup {spec.code}: {spec.label}",
        f"  N={int(result['n']):,}, WR={fmt_pct(float(result['win_rate']))}, PF={fmt_float(float(result['profit_factor']))}",
        f"  MAE: median={fmt_ticks(float(result['mae_median']))}, mean={fmt_ticks(float(result['mae_mean']))}, worst={fmt_ticks(float(result['mae_worst']))}",
        f"  MFE: median={fmt_ticks(float(result['mfe_median']))}, mean={fmt_ticks(float(result['mfe_mean']))}, best={fmt_ticks(float(result['mfe_best']))}",
        "  Winners stopped out: "
        + ", ".join(
            f"-{stop}t={fmt_pct(float(stop_map[stop]['winner_stop_out']))}" for stop in STOP_LEVELS if stop in stop_map
        ),
        f"  Optimal stop: {optimal_stop_label} (expectancy {fmt_ticks(float(optimal_stop['expectancy']))}/trade)",
        f"  Drawdown: max={fmt_ticks(float(result['max_drawdown']))}, duration={int(result['longest_drawdown']) if not pd.isna(result['longest_drawdown']) else 0} bars, avg depth={fmt_ticks(float(result['avg_drawdown_depth']))}",
        "",
    ]


def build_analysis_frames() -> dict[str, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(bars_1m)

    bar_frame = build_bar_observations(events)
    bar_frame = attach_timeframe_context(bar_frame, context)
    bar_frame = attach_rth_context(bar_frame, rth_bars)
    bar_frame = add_time_flags(bar_frame)
    bar_frame = compute_bar_features(bar_frame)
    bar_frame = compute_cvd_features(bar_frame)

    absorption_frame = build_absorption_observations(events)
    absorption_frame = attach_timeframe_context(absorption_frame, context)
    absorption_frame = attach_rth_context(absorption_frame, rth_bars)
    absorption_frame = add_time_flags(absorption_frame)
    absorption_frame = compute_bar_features(absorption_frame)

    score_frame = build_score_observations(events)
    score_frame = attach_timeframe_context(score_frame, context)
    score_frame = attach_rth_context(score_frame, rth_bars)
    score_frame = add_time_flags(score_frame)
    score_frame = compute_bar_features(score_frame)

    return {
        "bar": bar_frame,
        "absorption": absorption_frame,
        "score": score_frame,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    datasets = build_analysis_frames()
    specs = build_setup_specs()

    lines = [
        "DEEP6 round40 drawdown + MAE analysis",
        "====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Trade exit assumption: 30-bar time exit using fwd_close_1b through fwd_close_30b on close-to-close checkpoints.",
        "N only counts setups with a complete 30-bar forward path available inside the same RTH session.",
        "MAE/MFE use signed returns in ticks, so negative MAE is adverse and positive MFE is favorable for both longs and shorts.",
        "Stop analysis asks what share of eventual 30-bar winners would have hit each stop first under the same checkpoint approximation.",
        "Drawdown stats use cumulative 30-bar final returns ordered by setup observation timestamp.",
        "",
    ]

    for spec in specs:
        sample = build_setup_sample(datasets[spec.dataset_key], spec)
        result = analyze_setup(sample)
        lines.extend(render_setup_section(spec, result))

    report = "\n".join(lines).rstrip() + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
