#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round8_delta_cvd_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
SLOPE_WINDOW = 10
SHORT_SLOPE_WINDOW = 5
ACCUM_WINDOW = 20
EXHAUSTION_WINDOW = 10

FilterSpec = tuple[str, str, Callable[[pd.DataFrame], pd.Series], str]


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


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def status_flag(n: int, ci_low: float) -> str:
    if n < 15:
        return "LOW_N"
    if n >= 30 and ci_low > 0.50:
        return "VALIDATED"
    if n >= 15 and ci_low > 0.45:
        return "PROMISING"
    return ""


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    return bars.sort_values("ts_event").reset_index(drop=True)


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
        "fwd_close_5b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_5b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
            fwd_close_5b=("fwd_close_5b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
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


def attach_context(observations: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
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

    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["abs_delta"] = bars["bar_delta"].abs()
    bars["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    bars["prior_bar_range"] = by_session["bar_range"].shift(1)
    bars["bar_range_2"] = by_session["bar_range"].shift(2)
    bars["abs_delta_1"] = by_session["abs_delta"].shift(1)
    bars["abs_delta_2"] = by_session["abs_delta"].shift(2)
    bars["abs_delta_3"] = by_session["abs_delta"].shift(3)
    bars["abs_delta_4"] = by_session["abs_delta"].shift(4)
    bars["prior_abs_delta_avg_5"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=5).mean()
    )

    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    bars["is_three_narrowing_ranges"] = (
        bars["bar_range_2"].notna()
        & bars["prior_bar_range"].lt(bars["bar_range_2"])
        & bars["bar_range"].lt(bars["prior_bar_range"])
    )
    bars["is_five_increasing_abs_delta"] = (
        bars["abs_delta_4"].notna()
        & bars["abs_delta"].gt(bars["abs_delta_1"])
        & bars["abs_delta_1"].gt(bars["abs_delta_2"])
        & bars["abs_delta_2"].gt(bars["abs_delta_3"])
        & bars["abs_delta_3"].gt(bars["abs_delta_4"])
    )
    bars["delta_reverses_this_bar"] = (
        bars["direction_sign"].ne(0)
        & bars["prior_bar_delta"].notna()
        & pd.Series(np.sign(bars["prior_bar_delta"]), index=bars.index).ne(0)
        & pd.Series(np.sign(bars["bar_delta"]), index=bars.index).ne(
            pd.Series(np.sign(bars["prior_bar_delta"]), index=bars.index)
        )
    )
    return bars


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned_delta"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    out["bullish_pos_60m"] = (out["bar_low"] - out["low_60m"]) / rng_60m
    out["bearish_pos_60m"] = (out["bar_high"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme_bullish"] = out["bullish_pos_60m"] <= 0.20
    out["is_60m_extreme_bearish"] = out["bearish_pos_60m"] >= 0.80
    out["is_60m_extreme_delta"] = (
        ((out["direction_sign"] > 0) & out["is_60m_extreme_bullish"])
        | ((out["direction_sign"] < 0) & out["is_60m_extreme_bearish"])
    )
    return out


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

    out["cvd_slope_10"] = by_session["cvd"].transform(lambda s: (s - s.shift(SLOPE_WINDOW)) / SLOPE_WINDOW)
    out["cvd_slope_5"] = by_session["cvd"].transform(
        lambda s: (s - s.shift(SHORT_SLOPE_WINDOW)) / SHORT_SLOPE_WINDOW
    )
    out["prior_cvd_slope_5"] = by_session["cvd"].transform(
        lambda s: (s.shift(SHORT_SLOPE_WINDOW) - s.shift(SHORT_SLOPE_WINDOW * 2)) / SHORT_SLOPE_WINDOW
    )

    out["running_cvd_high"] = by_session["cvd"].cummax()
    out["running_cvd_low"] = by_session["cvd"].cummin()
    out["running_cvd_range"] = out["running_cvd_high"] - out["running_cvd_low"]
    out["cvd_pos_in_range"] = (out["cvd"] - out["running_cvd_low"]) / out["running_cvd_range"].replace(0, np.nan)

    out["prior_cvd"] = by_session["cvd"].shift(1)
    out["cvd_crossed_zero"] = (
        out["prior_cvd"].notna()
        & (((out["prior_cvd"] < 0) & (out["cvd"] > 0)) | ((out["prior_cvd"] > 0) & (out["cvd"] < 0)))
    )

    out["prior_delta_sum_20"] = by_session["bar_delta"].transform(
        lambda s: s.shift(1).rolling(ACCUM_WINDOW, min_periods=ACCUM_WINDOW).sum()
    )
    out["prior_delta_sum_10"] = by_session["bar_delta"].transform(
        lambda s: s.shift(1).rolling(EXHAUSTION_WINDOW, min_periods=EXHAUSTION_WINDOW).sum()
    )
    out["aligned_delta_sum_20"] = out["direction_sign"] * out["prior_delta_sum_20"]
    out["aligned_delta_sum_10"] = out["direction_sign"] * out["prior_delta_sum_10"]

    return out


def compute_thresholds(df: pd.DataFrame) -> dict[str, float]:
    slope_10 = df["cvd_slope_10"].dropna()
    abs_slope_10 = slope_10.abs()
    abs_delta_sum_20 = df["prior_delta_sum_20"].abs().dropna()

    return {
        "strong_positive_slope": float(slope_10.quantile(0.75)) if not slope_10.empty else float("nan"),
        "strong_negative_slope": float(slope_10.quantile(0.25)) if not slope_10.empty else float("nan"),
        "flat_abs_slope": float(abs_slope_10.quantile(0.25)) if not abs_slope_10.empty else float("nan"),
        "heavy_accum_abs_sum_20": float(abs_delta_sum_20.quantile(0.75)) if not abs_delta_sum_20.empty else float("nan"),
    }


def summarize_filter(code: str, label: str, df: pd.DataFrame, trade_sign_col: str) -> dict[str, object]:
    trade_sign = pd.to_numeric(df[trade_sign_col], errors="coerce")
    returns = (trade_sign * df["move_5b_ticks"]).where(trade_sign.ne(0)).dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "code": code,
        "label": label,
        "n": n,
        "win_rate": win_rate,
        "wins": wins,
        "profit_factor": profit_factor(returns) if n else np.nan,
        "avg_return_5b_ticks": float(returns.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs(thresholds: dict[str, float]) -> list[FilterSpec]:
    strong_positive = thresholds["strong_positive_slope"]
    strong_negative = thresholds["strong_negative_slope"]
    flat_abs_slope = thresholds["flat_abs_slope"]
    heavy_accum_abs_sum_20 = thresholds["heavy_accum_abs_sum_20"]

    return [
        (
            "01",
            "Price new session high but CVD below prior session CVD high + 60m_extreme",
            lambda df: df["is_bearish_cvd_divergence"] & df["is_60m_extreme_divergence"],
            "divergence_sign",
        ),
        (
            "02",
            "Price new session low but CVD above prior session CVD low + 60m_extreme",
            lambda df: df["is_bullish_cvd_divergence"] & df["is_60m_extreme_divergence"],
            "divergence_sign",
        ),
        (
            "03",
            "CVD divergence + 60m_extreme + 15m_trend",
            lambda df: df["is_cvd_divergence"]
            & df["is_60m_extreme_divergence"]
            & df["is_15m_trend_aligned_divergence"],
            "divergence_sign",
        ),
        (
            "04",
            "CVD divergence + doji + 60m_extreme",
            lambda df: df["is_cvd_divergence"] & df["is_doji"] & df["is_60m_extreme_divergence"],
            "divergence_sign",
        ),
        (
            "05",
            "CVD divergence + 3 narrowing ranges + 60m_extreme",
            lambda df: df["is_cvd_divergence"]
            & df["is_three_narrowing_ranges"]
            & df["is_60m_extreme_divergence"],
            "divergence_sign",
        ),
        (
            "06",
            "Strongly positive 10-bar CVD slope + bearish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].lt(0)
            & df["is_60m_extreme_delta"]
            & df["cvd_slope_10"].ge(strong_positive),
            "direction_sign",
        ),
        (
            "07",
            "Strongly negative 10-bar CVD slope + bullish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].gt(0)
            & df["is_60m_extreme_delta"]
            & df["cvd_slope_10"].le(strong_negative),
            "direction_sign",
        ),
        (
            "08",
            "Flat CVD slope (bottom 25% abs) + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["cvd_slope_10"].abs().lt(flat_abs_slope),
            "direction_sign",
        ),
        (
            "09",
            "Accelerating 5-bar CVD slope magnitude + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["prior_cvd_slope_5"].notna()
            & df["cvd_slope_5"].abs().gt(df["prior_cvd_slope_5"].abs()),
            "direction_sign",
        ),
        (
            "10",
            "Decelerating 5-bar CVD slope magnitude + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["prior_cvd_slope_5"].notna()
            & df["cvd_slope_5"].abs().lt(df["prior_cvd_slope_5"].abs()),
            "direction_sign",
        ),
        (
            "11",
            "CVD in top 10% of session range + bearish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].lt(0)
            & df["is_60m_extreme_delta"]
            & df["cvd_pos_in_range"].ge(0.90),
            "direction_sign",
        ),
        (
            "12",
            "CVD in bottom 10% of session range + bullish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].gt(0)
            & df["is_60m_extreme_delta"]
            & df["cvd_pos_in_range"].le(0.10),
            "direction_sign",
        ),
        (
            "13",
            "CVD > 0 + bullish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].gt(0) & df["is_60m_extreme_delta"] & df["cvd"].gt(0),
            "direction_sign",
        ),
        (
            "14",
            "CVD < 0 + bearish bar_delta + 60m_extreme",
            lambda df: df["direction_sign"].lt(0) & df["is_60m_extreme_delta"] & df["cvd"].lt(0),
            "direction_sign",
        ),
        (
            "15",
            "CVD crossed zero this bar + 60m_extreme",
            lambda df: df["direction_sign"].ne(0) & df["is_60m_extreme_delta"] & df["cvd_crossed_zero"],
            "direction_sign",
        ),
        (
            "16",
            "Aligned prior-20 delta sum above 75th percentile + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["aligned_delta_sum_20"].gt(heavy_accum_abs_sum_20),
            "direction_sign",
        ),
        (
            "17",
            "Prior-20 delta sum opposes bar_delta sign + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["aligned_delta_sum_20"].lt(0),
            "direction_sign",
        ),
        (
            "18",
            "5 consecutive bars of increasing |delta| + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["is_five_increasing_abs_delta"],
            "direction_sign",
        ),
        (
            "19",
            "Current |delta| > 3x prior 5-bar avg |delta| + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["prior_abs_delta_avg_5"].gt(0)
            & df["abs_delta"].gt(3.0 * df["prior_abs_delta_avg_5"]),
            "direction_sign",
        ),
        (
            "20",
            "10-bar delta sum opposes bar_delta sign and delta reverses + 60m_extreme",
            lambda df: df["direction_sign"].ne(0)
            & df["is_60m_extreme_delta"]
            & df["aligned_delta_sum_10"].lt(0)
            & df["delta_reverses_this_bar"],
            "direction_sign",
        ),
    ]


def run_filters(df: pd.DataFrame, thresholds: dict[str, float]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, label, predicate, trade_sign_col in build_filter_specs(thresholds):
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy(), trade_sign_col))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_return_5b_ticks"]) else float(row["avg_return_5b_ticks"]),
            float("-inf") if pd.isna(row["win_rate"]) else float(row["win_rate"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI", "Flag"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(float(row["win_rate"])),
                fmt_float(float(row["profit_factor"])),
                fmt_float(float(row["avg_return_5b_ticks"])),
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                str(row["flag"]),
            ]
        )

    widths = [len(header) for header in headers]
    for data_row in data_rows:
        for idx, cell in enumerate(data_row):
            widths[idx] = max(widths[idx], len(cell))

    def pad(cells: list[str]) -> str:
        return " | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(cells))

    lines = [pad(headers), "-+-".join("-" * width for width in widths)]
    for data_row in data_rows:
        lines.append(pad(data_row))
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)
    observations = compute_cvd_features(observations)
    thresholds = compute_thresholds(observations)

    baseline_all = summarize_filter(
        "00",
        "All non-zero-delta signal bars",
        observations[observations["direction_sign"] != 0].copy(),
        "direction_sign",
    )
    baseline_60m = summarize_filter(
        "00A",
        "All non-zero-delta bars at 60m extreme",
        observations[observations["is_60m_extreme_delta"]].copy(),
        "direction_sign",
    )
    baseline_div = summarize_filter(
        "00B",
        "All CVD divergence bars at 60m extreme",
        observations[observations["is_cvd_divergence"] & observations["is_60m_extreme_divergence"]].copy(),
        "divergence_sign",
    )
    results = run_filters(observations, thresholds)

    lines = [
        "DEEP6 round 8 delta/CVD pattern analysis",
        "=========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "CVD resets each session and is built from grouped bar_delta values.",
        "Divergence direction: price new session high + lower CVD than prior session CVD high = short; price new session low + higher CVD than prior session CVD low = long.",
        "Other trade direction: sign(bar_delta).",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20% of 60m range.",
        "15m_trend alignment uses the active trade direction for that filter.",
        f"10-bar CVD slope = simple difference over {SLOPE_WINDOW} bars divided by {SLOPE_WINDOW}.",
        "Accelerating/decelerating CVD uses the absolute 5-bar slope versus the immediately prior 5-bar slope window.",
        f"Heavy accumulation uses |prior {ACCUM_WINDOW}-bar delta sum| above the 75th percentile, aligned with current bar_delta sign.",
        "CVD extreme position uses the running session CVD range so far; top/bottom bands are the top/bottom 10%.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:              {len(events):,}",
        f"Grouped observations:               {len(observations):,}",
        f"Non-zero-delta observations:        {int(observations['direction_sign'].ne(0).sum()):,}",
        f"Bearish divergence observations:    {int(observations['is_bearish_cvd_divergence'].sum()):,}",
        f"Bullish divergence observations:    {int(observations['is_bullish_cvd_divergence'].sum()):,}",
        f"60m extreme (bar_delta direction):  {int(observations['is_60m_extreme_delta'].sum()):,}",
        f"60m extreme (divergence direction): {int(observations['is_60m_extreme_divergence'].sum()):,}",
        f"15m bars built:                     {len(context[15]):,}",
        f"60m bars built:                     {len(context[60]):,}",
        "",
        "Thresholds used",
        "---------------",
        f"Strong positive CVD slope (75th pct): {fmt_float(thresholds['strong_positive_slope'])}",
        f"Strong negative CVD slope (25th pct): {fmt_float(thresholds['strong_negative_slope'])}",
        f"Flat |CVD slope| cutoff (25th pct):   {fmt_float(thresholds['flat_abs_slope'])}",
        f"Heavy |20-bar delta sum| cutoff:      {fmt_float(thresholds['heavy_accum_abs_sum_20'])}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"All non-zero-delta bars: N={baseline_all['n']:,} | WR={fmt_pct(float(baseline_all['win_rate']))} | PF={fmt_float(float(baseline_all['profit_factor']))} | Avg={fmt_float(float(baseline_all['avg_return_5b_ticks']))}t | CI={fmt_ci(float(baseline_all['ci_low']), float(baseline_all['ci_high']))}",
        f"60m extreme bars:       N={baseline_60m['n']:,} | WR={fmt_pct(float(baseline_60m['win_rate']))} | PF={fmt_float(float(baseline_60m['profit_factor']))} | Avg={fmt_float(float(baseline_60m['avg_return_5b_ticks']))}t | CI={fmt_ci(float(baseline_60m['ci_low']), float(baseline_60m['ci_high']))}",
        f"Divergence + 60m:       N={baseline_div['n']:,} | WR={fmt_pct(float(baseline_div['win_rate']))} | PF={fmt_float(float(baseline_div['profit_factor']))} | Avg={fmt_float(float(baseline_div['avg_return_5b_ticks']))}t | CI={fmt_ci(float(baseline_div['ci_low']), float(baseline_div['ci_high']))}",
        "",
        "All round 8 filters ranked by 5-bar average return",
        "-----------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
