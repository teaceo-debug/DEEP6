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
OUT_PATH = OUT_DIR / "round9_exit_timing_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (1, 2, 5, 10, 15, 30)
OPENING_RANGE_BARS = 15
FIRST_HOUR_BARS = 60
LAST_HOUR_START_BAR = 330
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
TICK_SIZE = 0.25

Predicate = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class SetupSpec:
    label: str
    frame: str
    sign_col: str
    predicate: Predicate
    observation_unit: str


@dataclass(frozen=True)
class SectionSpec:
    label: str
    description: str
    entry_predicate: Predicate
    exit_cap: str


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


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    bars = bars.sort_values("ts_event").reset_index(drop=True)
    return bars


def prepare_rth_bars(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    minute_of_day = out["ts_event"].dt.hour * 60 + out["ts_event"].dt.minute
    out = out[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    out["session_date"] = out["ts_event"].dt.strftime("%Y-%m-%d")
    out["bar_index"] = out.groupby("session_date", sort=False).cumcount().astype("int32")
    out["session_bar_count"] = out.groupby("session_date", sort=False)["ts_event"].transform("size")
    return out.reset_index(drop=True)


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
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_1b",
        "fwd_close_2b",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_1b",
        "fwd_close_2b",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["bar_ts"].notna()].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_session_info(bars_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        bars_1m.groupby("session_date", as_index=False, sort=False)
        .agg(session_size=("bar_index", lambda s: int(s.max()) + 1))
        .reset_index(drop=True)
    )


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events[events["direction_sign"] != 0]
        .groupby(["global_index", "direction_sign"], as_index=False, sort=False)
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
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_bar_observations(events: pd.DataFrame) -> pd.DataFrame:
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
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    return observations


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    absorption = events[(events["category"] == "absorption") & (events["direction_sign"] != 0)].copy()
    observations = (
        absorption.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
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
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
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


def attach_context(df: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()
    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        out[bucket_col] = out["bar_ts"].dt.floor(f"{tf}min")
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
        out = out.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    out["bar_high"] = pd.to_numeric(out["bar_high"], errors="coerce")
    out["bar_low"] = pd.to_numeric(out["bar_low"], errors="coerce")
    out["bar_close"] = pd.to_numeric(out["bar_close"], errors="coerce")
    return out


def add_session_info(df: pd.DataFrame, session_info: pd.DataFrame) -> pd.DataFrame:
    return df.merge(session_info, on="session_date", how="left", validate="many_to_one")


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] - 9) * 60 + out["minute"] - 30
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_BARS)
    out["is_last_hour"] = out["minutes_since_930"].ge(LAST_HOUR_START_BAR) & out["minutes_since_930"].lt(390)
    return out


def add_regime_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["bullish_pos_60m"] = (out["bar_low"] - out["low_60m"]) / rng_60m
    out["bearish_pos_60m"] = (out["bar_high"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme_bullish"] = out["bullish_pos_60m"] <= 0.20
    out["is_60m_extreme_bearish"] = out["bearish_pos_60m"] >= 0.80
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["is_60m_extreme_bullish"])
        | ((out["direction_sign"] < 0) & out["is_60m_extreme_bearish"])
    )
    return out


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    return bars


def compute_cvd_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["cvd"] = by_session["bar_delta"].cumsum()
    by_session = out.groupby("session_date", sort=False)

    out["prior_session_price_high"] = by_session["bar_high"].transform(lambda s: s.cummax().shift(1))
    out["prior_session_price_low"] = by_session["bar_low"].transform(lambda s: s.cummin().shift(1))
    out["prior_cvd_high"] = by_session["cvd"].transform(lambda s: s.cummax().shift(1))
    out["prior_cvd_low"] = by_session["cvd"].transform(lambda s: s.cummin().shift(1))

    out["is_price_new_session_high"] = out["prior_session_price_high"].notna() & out["bar_high"].gt(
        out["prior_session_price_high"]
    )
    out["is_price_new_session_low"] = out["prior_session_price_low"].notna() & out["bar_low"].lt(
        out["prior_session_price_low"]
    )

    out["is_bearish_cvd_divergence"] = (
        out["is_price_new_session_high"] & out["prior_cvd_high"].notna() & out["cvd"].lt(out["prior_cvd_high"])
    )
    out["is_bullish_cvd_divergence"] = (
        out["is_price_new_session_low"] & out["prior_cvd_low"].notna() & out["cvd"].gt(out["prior_cvd_low"])
    )
    out["divergence_sign"] = np.select(
        [out["is_bullish_cvd_divergence"], out["is_bearish_cvd_divergence"]],
        [1, -1],
        default=0,
    ).astype(int)
    out["is_cvd_divergence"] = out["divergence_sign"].ne(0)
    out["is_60m_extreme_divergence"] = (
        ((out["divergence_sign"] > 0) & out["is_60m_extreme_bullish"])
        | ((out["divergence_sign"] < 0) & out["is_60m_extreme_bearish"])
    )
    out["is_15m_trend_aligned_divergence"] = out["divergence_sign"] == out["trend_sign_15m"]
    return out


def build_or_state(bars_1m: pd.DataFrame) -> pd.DataFrame:
    opening_range = (
        bars_1m[bars_1m["bar_index"] < OPENING_RANGE_BARS]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            or_high=("high", "max"),
            or_low=("low", "min"),
        )
    )

    out = bars_1m.merge(opening_range, on="session_date", how="left", validate="many_to_one")
    by_session = out.groupby("session_date", sort=False)

    out["inside_or"] = out["close"].le(out["or_high"]) & out["close"].ge(out["or_low"])
    out["broke_above_or_now"] = out["bar_index"].ge(OPENING_RANGE_BARS) & out["high"].gt(out["or_high"])
    out["broke_below_or_now"] = out["bar_index"].ge(OPENING_RANGE_BARS) & out["low"].lt(out["or_low"])
    out["has_broken_above_or"] = by_session["broke_above_or_now"].cummax()
    out["has_broken_below_or"] = by_session["broke_below_or_now"].cummax()
    out["has_failed_breakout"] = out["has_broken_above_or"] & out["inside_or"] & out["bar_index"].ge(OPENING_RANGE_BARS)
    out["has_failed_breakdown"] = out["has_broken_below_or"] & out["inside_or"] & out["bar_index"].ge(OPENING_RANGE_BARS)

    cols = ["ts_event", "has_failed_breakout", "has_failed_breakdown"]
    renamed = out[cols].rename(columns={"ts_event": "bar_ts"})
    for col in ["has_failed_breakout", "has_failed_breakdown"]:
        renamed[col] = renamed[col].fillna(False).astype(bool)
    return renamed


def attach_or_state(df: pd.DataFrame, or_state: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(or_state, on="bar_ts", how="left", validate="many_to_one")
    out["has_failed_breakout"] = out["has_failed_breakout"].fillna(False).astype(bool)
    out["has_failed_breakdown"] = out["has_failed_breakdown"].fillna(False).astype(bool)
    return out


def prepare_frames() -> dict[str, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    rth_bars = prepare_rth_bars(bars_1m)
    session_info = build_session_info(rth_bars)
    context = build_timeframe_context(bars_1m)
    or_state = build_or_state(rth_bars)

    signal = build_signal_observations(events)
    signal = add_session_info(signal, session_info)
    signal = attach_context(signal, context)
    signal = add_regime_flags(signal)
    signal = add_time_flags(signal)
    signal = attach_or_state(signal, or_state)

    bars = build_bar_observations(events)
    bars = add_session_info(bars, session_info)
    bars = attach_context(bars, context)
    bars = add_regime_flags(bars)
    bars = compute_bar_features(bars)
    bars = compute_cvd_features(bars)
    bars = add_time_flags(bars)

    absorption = build_absorption_observations(events)
    absorption = add_session_info(absorption, session_info)
    absorption = attach_context(absorption, context)
    absorption = add_regime_flags(absorption)
    absorption = add_time_flags(absorption)

    return {
        "signal": signal,
        "bar": bars,
        "absorption": absorption,
    }


def build_setup_specs() -> list[SetupSpec]:
    return [
        SetupSpec(
            label="60m_extreme + 15m_trend",
            frame="signal",
            sign_col="direction_sign",
            predicate=lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"],
            observation_unit="signal/global_index+direction",
        ),
        SetupSpec(
            label="Doji + 60m_extreme + 15m_trend",
            frame="bar",
            sign_col="direction_sign",
            predicate=lambda df: df["direction_sign"].ne(0)
            & df["is_doji"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"],
            observation_unit="bar/global_index",
        ),
        SetupSpec(
            label="CVD divergence + 60m_extreme + 15m_trend",
            frame="bar",
            sign_col="divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"]
            & df["is_60m_extreme_divergence"]
            & df["is_15m_trend_aligned_divergence"],
            observation_unit="bar/global_index",
        ),
        SetupSpec(
            label="Failed OR breakout + 60m_extreme + 15m_trend",
            frame="signal",
            sign_col="direction_sign",
            predicate=lambda df: (
                (df["direction_sign"].lt(0) & df["has_failed_breakout"])
                | (df["direction_sign"].gt(0) & df["has_failed_breakdown"])
            )
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"],
            observation_unit="signal/global_index+direction",
        ),
        SetupSpec(
            label="Absorption + 60m_extreme + 15m_trend",
            frame="absorption",
            sign_col="direction_sign",
            predicate=lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"],
            observation_unit="absorption/global_index+direction",
        ),
    ]


def build_section_specs() -> list[SectionSpec]:
    return [
        SectionSpec(
            label="All entries",
            description="Entry can happen anywhere in RTH; exits must stay inside the same RTH session.",
            entry_predicate=lambda df: pd.Series(True, index=df.index),
            exit_cap="session",
        ),
        SectionSpec(
            label="First-hour entries",
            description="Entry must occur in 09:30-10:29 ET and exit must complete by 10:30 ET.",
            entry_predicate=lambda df: df["is_first_hour"],
            exit_cap="first_hour",
        ),
        SectionSpec(
            label="Last-hour entries",
            description="Entry must occur in 15:00-15:59 ET and exit must complete by the session close.",
            entry_predicate=lambda df: df["is_last_hour"],
            exit_cap="session",
        ),
    ]


def exit_cap_series(df: pd.DataFrame, cap_name: str) -> pd.Series:
    session_cap = pd.to_numeric(df["session_size"], errors="coerce")
    if cap_name == "session":
        return session_cap
    if cap_name == "first_hour":
        return pd.Series(np.minimum(session_cap.to_numpy(dtype=float), FIRST_HOUR_BARS), index=df.index)
    raise ValueError(f"Unknown exit cap: {cap_name}")


def compute_window_metrics(df: pd.DataFrame, sign_col: str, window: int, cap_name: str) -> dict[str, float | int]:
    sign = pd.to_numeric(df[sign_col], errors="coerce")
    bar_close = pd.to_numeric(df["bar_close"], errors="coerce")
    fwd_close = pd.to_numeric(df[f"fwd_close_{window}b"], errors="coerce")
    bar_index = pd.to_numeric(df["bar_index"], errors="coerce")
    exit_cap = exit_cap_series(df, cap_name)

    valid = (
        sign.notna()
        & sign.ne(0)
        & bar_close.notna()
        & fwd_close.notna()
        & bar_index.notna()
        & exit_cap.notna()
        & bar_index.add(window).lt(exit_cap)
    )

    returns = sign[valid] * ((fwd_close[valid] - bar_close[valid]) / TICK_SIZE)
    n = int(len(returns))
    return {
        "window": window,
        "n": n,
        "win_rate": float((returns > 0).mean()) if n else np.nan,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_ticks": float(returns.mean()) if n else np.nan,
        "sharpe": sharpe_ratio(returns) if n else np.nan,
    }


def choose_optimal(metrics: dict[int, dict[str, float | int]]) -> tuple[int | None, float]:
    candidates = [row for row in metrics.values() if int(row["n"]) > 0]
    if not candidates:
        return None, float("nan")
    best = max(
        candidates,
        key=lambda row: (
            float(row["sharpe"]),
            float(row["avg_ticks"]),
            float(row["win_rate"]),
            -int(row["window"]),
        ),
    )
    return int(best["window"]), float(best["sharpe"])


def summarize_setup(df: pd.DataFrame, setup: SetupSpec, section: SectionSpec) -> dict[str, object]:
    setup_mask = setup.predicate(df)
    entry_mask = section.entry_predicate(df)
    sample = df.loc[setup_mask & entry_mask].copy()

    metrics = {
        window: compute_window_metrics(sample, setup.sign_col, window, section.exit_cap)
        for window in FORWARD_WINDOWS
    }
    optimal_window, optimal_sharpe = choose_optimal(metrics)

    return {
        "setup": setup,
        "sample_size": int(len(sample)),
        "metrics": metrics,
        "optimal_window": optimal_window,
        "optimal_sharpe": optimal_sharpe,
    }


def run_analysis(frames: dict[str, pd.DataFrame]) -> dict[str, list[dict[str, object]]]:
    results: dict[str, list[dict[str, object]]] = {}
    setups = build_setup_specs()
    sections = build_section_specs()

    for section in sections:
        section_results: list[dict[str, object]] = []
        for setup in setups:
            section_results.append(summarize_setup(frames[setup.frame], setup, section))
        results[section.label] = section_results
    return results


def metric_cell(metrics: dict[str, float | int]) -> str:
    if int(metrics["n"]) == 0:
        return "n/a"
    return f"{fmt_pct(float(metrics['win_rate']))}/{fmt_ticks(float(metrics['avg_ticks']))}"


def render_section_summary(rows: list[dict[str, object]]) -> list[str]:
    headers = [
        "Setup",
        "1b WR/Avg",
        "2b WR/Avg",
        "5b WR/Avg",
        "10b WR/Avg",
        "15b WR/Avg",
        "30b WR/Avg",
        "Optimal Exit",
        "Sharpe at Optimal",
    ]
    table_rows: list[list[str]] = []

    for row in rows:
        metrics = row["metrics"]
        optimal_window = row["optimal_window"]
        optimal_text = f"{optimal_window}b" if optimal_window is not None else "n/a"
        table_rows.append(
            [
                row["setup"].label,
                metric_cell(metrics[1]),
                metric_cell(metrics[2]),
                metric_cell(metrics[5]),
                metric_cell(metrics[10]),
                metric_cell(metrics[15]),
                metric_cell(metrics[30]),
                optimal_text,
                fmt_float(float(row["optimal_sharpe"])),
            ]
        )
    return render_table(headers, table_rows)


def render_section_detail(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Setup", "Window", "N", "WR", "PF", "Avg Ticks", "Sharpe"]
    table_rows: list[list[str]] = []

    for row in rows:
        for window in FORWARD_WINDOWS:
            metrics = row["metrics"][window]
            table_rows.append(
                [
                    row["setup"].label,
                    f"{window}b",
                    f"{int(metrics['n']):,}",
                    fmt_pct(float(metrics["win_rate"])),
                    fmt_float(float(metrics["profit_factor"])),
                    fmt_ticks(float(metrics["avg_ticks"])),
                    fmt_float(float(metrics["sharpe"])),
                ]
            )
    return render_table(headers, table_rows)


def render_recommendations(section_label: str, rows: list[dict[str, object]]) -> list[str]:
    lines = [section_label + ":"]
    for row in rows:
        optimal_window = row["optimal_window"]
        if optimal_window is None:
            lines.append(f"- {row['setup'].label}: no valid exit sample.")
            continue

        metrics = row["metrics"][optimal_window]
        lines.append(
            f"- {row['setup'].label}: hold until {optimal_window} bars "
            f"(Sharpe {fmt_float(float(metrics['sharpe']))}, Avg {fmt_ticks(float(metrics['avg_ticks']))}, N={int(metrics['n']):,})."
        )
    return lines


def build_report(results: dict[str, list[dict[str, object]]]) -> str:
    lines = [
        "ROUND 9 EXIT TIMING ANALYSIS",
        "============================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "",
        "Methodology:",
        "- Base setup uses all signal observations grouped by global_index + direction.",
        "- Doji and CVD divergence use bar observations grouped by global_index.",
        "- Absorption uses absorption-only observations grouped by global_index + direction.",
        "- Failed OR breakout uses the round 6 trap logic: prior OR break, close back inside OR, direction flipped against the failed move.",
        "- CVD divergence uses session CVD = cumsum(bar_delta) and compares price session extremes vs prior running CVD extremes.",
        "- Every exit window is capped to stay inside the same RTH session; no overnight carry is allowed.",
        "",
    ]

    sections = build_section_specs()
    for section in sections:
        section_rows = results[section.label]
        lines.extend(
            [
                section.label.upper(),
                "-" * len(section.label),
                section.description,
                "",
                "Overview:",
            ]
        )
        lines.extend(render_section_summary(section_rows))
        lines.extend(
            [
                "",
                "Detailed metrics:",
            ]
        )
        lines.extend(render_section_detail(section_rows))
        lines.extend(["", "Observation units:"])
        for row in section_rows:
            lines.append(f"- {row['setup'].label}: {row['setup'].observation_unit}")
        lines.extend(["", ""])

    lines.append("RECOMMENDATION SECTION")
    lines.append("----------------------")
    lines.append("For each setup, hold until the bar count below for maximum risk-adjusted return:")
    lines.append("")
    for section in sections:
        lines.extend(render_recommendations(section.label, results[section.label]))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    frames = prepare_frames()
    results = run_analysis(frames)
    report = build_report(results)

    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
