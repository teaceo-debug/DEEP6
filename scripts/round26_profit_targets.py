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
OUT_PATH = OUT_DIR / "round26_profit_targets_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
REPORT_WINDOWS = (1, 2, 5, 10, 15, 30)
PATH_WINDOWS = tuple(range(1, 31))
FIXED_TARGET_TICKS = (20.0, 40.0, 60.0)
ATR_TARGET_MULTIPLIERS = (0.5, 1.0, 1.5)
STOP_TARGET_SPECS = ((20.0, 40.0), (30.0, 60.0), (20.0, 60.0))

ATR_LOOKBACK = 20
FIRST_HOUR_MINUTES = 60
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
TICK_SIZE = 0.25

Predicate = Callable[[pd.DataFrame], pd.Series]
DirectionFn = Callable[[pd.DataFrame], int | pd.Series]


@dataclass(frozen=True)
class SetupSpec:
    code: str
    label: str
    direction_label: str
    predicate: Predicate
    direction_fn: DirectionFn


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


def sharpe_ratio(returns: pd.Series) -> float:
    if len(returns) <= 1:
        return 0.0
    std = float(returns.std(ddof=1))
    return float(returns.mean() / std) if std > 0 else 0.0


def render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    lines = [
        " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)),
        "-+-".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))
    return lines


def load_events() -> pd.DataFrame:
    dtypes = {
        "session_date": "string",
        "signal_id": "string",
        "category": "string",
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
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df = df[df["bar_ts"].notna()].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
    prev_close = by_session["close"].shift(1)
    true_range_parts = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    bars["true_range"] = true_range_parts.max(axis=1)
    bars["atr20"] = by_session["true_range"].transform(
        lambda s: s.rolling(ATR_LOOKBACK, min_periods=ATR_LOOKBACK).mean()
    )

    for window in PATH_WINDOWS:
        bars[f"fwd_close_{window}b"] = by_session["close"].shift(-window)

    return bars.reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby("global_index", as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    return observations


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
    merge_cols = ["ts_event", "session_date", "bar_index", "atr20"] + [f"fwd_close_{window}b" for window in PATH_WINDOWS]
    context = rth_bars[merge_cols].rename(
        columns={
            "ts_event": "bar_ts",
            "session_date": "rth_session_date",
            "bar_index": "rth_bar_index",
        }
    )
    out = observations.merge(context, on="bar_ts", how="left", validate="many_to_one")
    return out.reset_index(drop=True)


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["bar_delta"].abs() / out["bar_volume"], np.nan)
    out["is_very_low_delta_ratio"] = out["delta_ratio"].lt(0.05)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=20, adjust=False, min_periods=20).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["price_color_sign"] = np.sign(out["bar_close"] - out["bar_open"]).astype(int)
    out["price_color_sign_1"] = by_session["price_color_sign"].shift(1)
    out["price_color_sign_2"] = by_session["price_color_sign"].shift(2)
    out["is_doji_1"] = by_session["is_doji"].shift(1)
    out["open_2"] = by_session["bar_open"].shift(2)
    out["close_2"] = by_session["bar_close"].shift(2)
    out["body_mid_2"] = (out["open_2"] + out["close_2"]) / 2.0

    out["is_morning_star"] = (
        out["price_color_sign"].eq(1)
        & out["is_doji_1"].fillna(False)
        & out["price_color_sign_2"].eq(-1)
        & out["bar_close"].gt(out["body_mid_2"])
    )
    out["is_evening_star"] = (
        out["price_color_sign"].eq(-1)
        & out["is_doji_1"].fillna(False)
        & out["price_color_sign_2"].eq(1)
        & out["bar_close"].lt(out["body_mid_2"])
    )
    out["star_direction_sign"] = np.select(
        [out["is_morning_star"], out["is_evening_star"]],
        [1, -1],
        default=0,
    ).astype(int)

    bool_cols = [
        "is_doji",
        "is_very_low_delta_ratio",
        "is_volume_spike_3x",
        "is_morning_star",
        "is_evening_star",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
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

    bool_cols = ["is_bullish_cvd_divergence", "is_bearish_cvd_divergence", "is_cvd_divergence"]
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
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="B",
            label="Doji + 60m + 15m + NOT killers + first_hour",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_doji"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="C",
            label="CVD divergence + 60m + 15m",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="D",
            label="Morning/evening star + 60m + 15m + NOT killers + first_hour",
            direction_label="trade direction = star_direction_sign",
            predicate=lambda df: df["star_direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["star_direction_sign"])
            & passes_not_all_killers_for(df, df["star_direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["star_direction_sign"],
        ),
        SetupSpec(
            code="E",
            label="|delta|/vol < 0.05 + 60m + 15m + NOT killers",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_very_low_delta_ratio"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
    ]


def build_setup_sample(df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(df).fillna(False)
    sample = df.loc[mask].copy()

    direction = spec.direction_fn(df)
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()

    for window in REPORT_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * ((sample[f"fwd_close_{window}b"] - sample["bar_close"]) / TICK_SIZE)
    sample["atr20_ticks"] = sample["atr20"] / TICK_SIZE
    return sample.reset_index(drop=True)


def summarize_time_window(sample: pd.DataFrame, window: int) -> dict[str, object]:
    returns = sample[f"ret_{window}b_ticks"].dropna()
    n = int(len(returns))
    return {
        "window": window,
        "n": n,
        "win_rate": float((returns > 0).mean()) if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "sharpe": sharpe_ratio(returns) if n else np.nan,
    }


def coerce_target_series(target_ticks: float | pd.Series, sample: pd.DataFrame) -> pd.Series:
    if isinstance(target_ticks, pd.Series):
        series = target_ticks.reindex(sample.index)
    else:
        series = pd.Series(target_ticks, index=sample.index)
    return pd.to_numeric(series, errors="coerce")


def path_return_matrix(sample: pd.DataFrame) -> np.ndarray:
    path_cols = [f"fwd_close_{window}b" for window in PATH_WINDOWS]
    path_prices = sample[path_cols].to_numpy(dtype=float)
    entry = sample["bar_close"].to_numpy(dtype=float)[:, None]
    trade_sign = sample["trade_sign"].to_numpy(dtype=float)[:, None]
    return trade_sign * ((path_prices - entry) / TICK_SIZE)


def summarize_target_exit(sample: pd.DataFrame, label: str, target_ticks: float | pd.Series) -> dict[str, object]:
    targets = coerce_target_series(target_ticks, sample)
    valid_mask = sample["fwd_close_30b"].notna() & targets.notna() & targets.gt(0)
    clean = sample.loc[valid_mask].copy()
    clean_targets = targets.loc[valid_mask].to_numpy(dtype=float)

    if clean.empty:
        return {
            "label": label,
            "n": 0,
            "hit_rate": np.nan,
            "profit_factor": np.nan,
            "avg_ticks": np.nan,
            "sharpe": np.nan,
            "avg_exit_bar": np.nan,
        }

    returns_matrix = path_return_matrix(clean)
    realized = returns_matrix[:, -1].copy()
    hits = np.zeros(len(clean), dtype=bool)
    exit_bars = np.full(len(clean), PATH_WINDOWS[-1], dtype=int)

    for row_idx in range(len(clean)):
        target = clean_targets[row_idx]
        for path_idx, ret_ticks in enumerate(returns_matrix[row_idx], start=1):
            if ret_ticks >= target:
                realized[row_idx] = target
                hits[row_idx] = True
                exit_bars[row_idx] = path_idx
                break

    realized_series = pd.Series(realized)
    return {
        "label": label,
        "n": int(len(clean)),
        "hit_rate": float(hits.mean()),
        "profit_factor": profit_factor(realized_series),
        "avg_ticks": float(realized_series.mean()),
        "sharpe": sharpe_ratio(realized_series),
        "avg_exit_bar": float(exit_bars.mean()),
    }


def summarize_stop_target(sample: pd.DataFrame, stop_ticks: float, target_ticks: float) -> dict[str, object]:
    valid_mask = sample["fwd_close_30b"].notna()
    clean = sample.loc[valid_mask].copy()

    if clean.empty:
        return {
            "label": f"-{int(stop_ticks)} / +{int(target_ticks)}",
            "n": 0,
            "win_rate": np.nan,
            "avg_ticks": np.nan,
            "profit_factor": np.nan,
            "timeouts": 0,
        }

    returns_matrix = path_return_matrix(clean)
    realized = returns_matrix[:, -1].copy()
    target_hits = np.zeros(len(clean), dtype=bool)
    stop_hits = np.zeros(len(clean), dtype=bool)

    for row_idx in range(len(clean)):
        for ret_ticks in returns_matrix[row_idx]:
            if ret_ticks >= target_ticks:
                realized[row_idx] = target_ticks
                target_hits[row_idx] = True
                break
            if ret_ticks <= -stop_ticks:
                realized[row_idx] = -stop_ticks
                stop_hits[row_idx] = True
                break

    realized_series = pd.Series(realized)
    return {
        "label": f"-{int(stop_ticks)} / +{int(target_ticks)}",
        "n": int(len(clean)),
        "win_rate": float(target_hits.mean()),
        "avg_ticks": float(realized_series.mean()),
        "profit_factor": profit_factor(realized_series),
        "timeouts": int((~target_hits & ~stop_hits).sum()),
    }


def pick_best(rows: list[dict[str, object]], key: str) -> dict[str, object] | None:
    valid = [row for row in rows if not pd.isna(row[key])]
    if not valid:
        return None
    return max(valid, key=lambda row: (float(row[key]), float(row.get("profit_factor", -np.inf)), float(row.get("avg_ticks", -np.inf))))


def pick_default_time_exit(rows: list[dict[str, object]]) -> dict[str, object] | None:
    valid = [row for row in rows if not pd.isna(row["sharpe"])]
    if not valid:
        return None
    return max(
        valid,
        key=lambda row: (
            float(row["sharpe"]),
            float(row["profit_factor"]),
            float(row["avg_ticks"]),
            -int(row["window"]),
        ),
    )


def render_time_exit_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Window", "N", "WR", "PF", "Avg", "Sharpe"]
    table_rows = [
        [
            f"{int(row['window'])}b",
            f"{int(row['n']):,}",
            fmt_pct(float(row["win_rate"])),
            fmt_float(float(row["profit_factor"])),
            fmt_ticks(float(row["avg_ticks"])),
            fmt_float(float(row["sharpe"])),
        ]
        for row in rows
    ]
    return render_table(headers, table_rows)


def render_target_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Target", "N", "Hit", "PF", "Avg", "Sharpe", "Avg Exit"]
    table_rows = [
        [
            str(row["label"]),
            f"{int(row['n']):,}",
            fmt_pct(float(row["hit_rate"])),
            fmt_float(float(row["profit_factor"])),
            fmt_ticks(float(row["avg_ticks"])),
            fmt_float(float(row["sharpe"])),
            "nan" if pd.isna(row["avg_exit_bar"]) else f"{float(row['avg_exit_bar']):.1f}b",
        ]
        for row in rows
    ]
    return render_table(headers, table_rows)


def render_bracket_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Stop/Target", "N", "WR", "Avg P&L", "PF", "Timeouts"]
    table_rows = [
        [
            str(row["label"]),
            f"{int(row['n']):,}",
            fmt_pct(float(row["win_rate"])),
            fmt_ticks(float(row["avg_ticks"])),
            fmt_float(float(row["profit_factor"])),
            f"{int(row['timeouts']):,}",
        ]
        for row in rows
    ]
    return render_table(headers, table_rows)


def analyze_setup(sample: pd.DataFrame) -> dict[str, object]:
    time_rows = [summarize_time_window(sample, window) for window in REPORT_WINDOWS]
    fixed_rows = [summarize_target_exit(sample, f"+{int(target_ticks)}t", target_ticks) for target_ticks in FIXED_TARGET_TICKS]
    atr_rows = [
        summarize_target_exit(sample, f"{multiplier:.1f}x ATR20", sample["atr20_ticks"] * multiplier)
        for multiplier in ATR_TARGET_MULTIPLIERS
    ]
    bracket_rows = [summarize_stop_target(sample, stop_ticks, target_ticks) for stop_ticks, target_ticks in STOP_TARGET_SPECS]

    return {
        "sample_n": int(len(sample)),
        "time_rows": time_rows,
        "fixed_rows": fixed_rows,
        "atr_rows": atr_rows,
        "bracket_rows": bracket_rows,
        "pf_leader": pick_best(time_rows, "profit_factor"),
        "sharpe_leader": pick_best(time_rows, "sharpe"),
        "avg_leader": pick_best(time_rows, "avg_ticks"),
        "default_time_exit": pick_default_time_exit(time_rows),
        "fixed_leader": pick_best(fixed_rows, "sharpe"),
        "atr_leader": pick_best(atr_rows, "sharpe"),
        "bracket_leader": pick_best(bracket_rows, "profit_factor"),
    }


def build_analysis_frame() -> pd.DataFrame:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(bars_1m)

    observations = build_observations(events)
    observations = attach_timeframe_context(observations, context)
    observations = attach_rth_context(observations, rth_bars)
    observations = add_time_flags(observations)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    return observations


def build_report(analysis_frame: pd.DataFrame, results: list[tuple[SetupSpec, dict[str, object]]]) -> str:
    lines = [
        "ROUND 26 PROFIT TARGET ANALYSIS",
        "===============================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "",
        "Methodology:",
        "- Observation unit is one unique signal bar grouped by global_index.",
        "- 15m/60m context comes from nq_1yr_1m.csv resamples.",
        "- Forward paths use same-session RTH 1m closes only; no overnight carry is allowed.",
        "- Time exits score the requested 1/2/5/10/15/30 bar windows.",
        "- Fixed-target sweeps use +20t / +40t / +60t targets with a 30-bar timeout and no hard stop.",
        "- ATR-target sweeps use 0.5x / 1.0x / 1.5x ATR20 targets with a 30-bar timeout and no hard stop.",
        "- Bracket sims use close-only path checks: first close to cross stop/target wins; otherwise trade exits at the 30-bar close.",
        "- NOT killers = direction-aware 60m anchor not in the 40%-60% middle band AND bar_volume not > 3x prior 20-bar EMA.",
        "- CVD divergence follows the round9 session-extreme vs prior-CVD-extreme logic.",
        "- Morning/evening star follows the round23 3-candle definition.",
        "- Setup D uses the first-hour star variant because the brief's cited sample size (~88) matches that round23 winner.",
        "",
        f"Unique signal bars loaded: {len(analysis_frame):,}",
        f"First-hour bars:           {int(analysis_frame['is_first_hour'].sum()):,}",
        f"Doji bars:                 {int(analysis_frame['is_doji'].sum()):,}",
        f"CVD divergence bars:       {int(analysis_frame['is_cvd_divergence'].sum()):,}",
        f"Morning/evening stars:     {int(analysis_frame['star_direction_sign'].ne(0).sum()):,}",
        f"|delta|/vol < 0.05 bars:   {int(analysis_frame['is_very_low_delta_ratio'].sum()):,}",
        "",
    ]

    for spec, result in results:
        lines.extend(
            [
                f"SETUP {spec.code}: {spec.label}",
                "-" * (9 + len(spec.code) + len(spec.label)),
                f"Trade direction: {spec.direction_label}",
                f"Raw sample size before window-specific drops: {int(result['sample_n']):,}",
                "",
                "Time-based exits:",
            ]
        )
        lines.extend(render_time_exit_table(result["time_rows"]))
        lines.extend(["", "Time-window leaders:"])

        pf_leader = result["pf_leader"]
        sharpe_leader = result["sharpe_leader"]
        avg_leader = result["avg_leader"]
        default_time_exit = result["default_time_exit"]

        lines.append(
            "- PF max: "
            + (
                f"{int(pf_leader['window'])}b (PF {fmt_float(float(pf_leader['profit_factor']))}, Avg {fmt_ticks(float(pf_leader['avg_ticks']))})."
                if pf_leader is not None
                else "n/a."
            )
        )
        lines.append(
            "- Sharpe max: "
            + (
                f"{int(sharpe_leader['window'])}b (Sharpe {fmt_float(float(sharpe_leader['sharpe']))}, Avg {fmt_ticks(float(sharpe_leader['avg_ticks']))})."
                if sharpe_leader is not None
                else "n/a."
            )
        )
        lines.append(
            "- Avg-ticks max: "
            + (
                f"{int(avg_leader['window'])}b (Avg {fmt_ticks(float(avg_leader['avg_ticks']))}, PF {fmt_float(float(avg_leader['profit_factor']))})."
                if avg_leader is not None
                else "n/a."
            )
        )

        lines.extend(["", "Fixed tick target sweeps:"])
        lines.extend(render_target_table(result["fixed_rows"]))

        lines.extend(["", "ATR-scaled target sweeps:"])
        lines.extend(render_target_table(result["atr_rows"]))

        lines.extend(["", "Stop/target simulations:"])
        lines.extend(render_bracket_table(result["bracket_rows"]))

        fixed_leader = result["fixed_leader"]
        atr_leader = result["atr_leader"]
        bracket_leader = result["bracket_leader"]

        recommendation_parts: list[str] = []
        if default_time_exit is not None:
            recommendation_parts.append(
                f"Default to {int(default_time_exit['window'])}b time exit (Sharpe {fmt_float(float(default_time_exit['sharpe']))}, PF {fmt_float(float(default_time_exit['profit_factor']))}, Avg {fmt_ticks(float(default_time_exit['avg_ticks']))})"
            )
        if fixed_leader is not None:
            recommendation_parts.append(
                f"best fixed target = {fixed_leader['label']} (Hit {fmt_pct(float(fixed_leader['hit_rate']))}, Avg {fmt_ticks(float(fixed_leader['avg_ticks']))})"
            )
        if atr_leader is not None:
            recommendation_parts.append(
                f"best ATR target = {atr_leader['label']} (Hit {fmt_pct(float(atr_leader['hit_rate']))}, Avg {fmt_ticks(float(atr_leader['avg_ticks']))})"
            )
        if bracket_leader is not None:
            recommendation_parts.append(
                f"best bracket = {bracket_leader['label']} (WR {fmt_pct(float(bracket_leader['win_rate']))}, Avg {fmt_ticks(float(bracket_leader['avg_ticks']))}, PF {fmt_float(float(bracket_leader['profit_factor']))})"
            )

        lines.extend(["", "Recommendation:"])
        lines.append("- " + "; ".join(recommendation_parts) + ".")
        lines.extend(["", ""])

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    analysis_frame = build_analysis_frame()
    results: list[tuple[SetupSpec, dict[str, object]]] = []
    for spec in build_setup_specs():
        sample = build_setup_sample(analysis_frame, spec)
        results.append((spec, analyze_setup(sample)))

    report = build_report(analysis_frame, results)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
