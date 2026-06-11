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
OUT_PATH = OUT_DIR / "round44_seasonal_vix_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
EARNINGS_MONTHS = {1, 4, 7, 10}
DECEMBER_LAST_2_WEEKS_START_DAY = 18
JANUARY_FIRST_2_WEEKS_END_DAY = 14

FilterSpec = tuple[str, str, str, Callable[[pd.DataFrame], pd.Series]]


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


def classify_persistence(win_rate_5b: float, win_rate_30b: float) -> str:
    if pd.isna(win_rate_5b) or pd.isna(win_rate_30b):
        return "NO_DATA"
    delta = win_rate_30b - win_rate_5b
    if delta > 0:
        return "GROWING"
    if abs(delta) < 0.03:
        return "STABLE"
    return "DECAYING"


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
        "fwd_close_10b",
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
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
        )
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["direction"] = np.select(
        [observations["direction_sign"] > 0, observations["direction_sign"] < 0],
        ["BULLISH", "BEARISH"],
        default="FLAT",
    )
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (
            observations[f"fwd_close_{window}b"] - observations["bar_close"]
        ) / TICK_SIZE
    observations["session_date_ts"] = pd.to_datetime(observations["session_date"], errors="coerce").dt.normalize()
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

    df["bar_open"] = pd.to_numeric(df["bar_open"], errors="coerce")
    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["prior_close"] = by_session["bar_close"].shift(1)

    true_range_parts = pd.concat(
        [
            out["bar_high"] - out["bar_low"],
            (out["bar_high"] - out["prior_close"]).abs(),
            (out["bar_low"] - out["prior_close"]).abs(),
        ],
        axis=1,
    )
    out["true_range"] = true_range_parts.max(axis=1)
    out["atr20"] = by_session["true_range"].transform(
        lambda s: s.rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).mean()
    )
    out["atr20_1"] = by_session["atr20"].shift(1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    return out


def add_seasonal_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["month"] = out["session_date_ts"].dt.month
    out["day_of_month"] = out["session_date_ts"].dt.day
    out["quarter"] = ((out["month"] - 1) // 3 + 1).astype("Int64")
    out["month_of_quarter"] = ((out["month"] - 1) % 3 + 1).astype("Int64")

    out["is_earnings_month"] = out["month"].isin(EARNINGS_MONTHS)
    out["is_non_earnings_month"] = ~out["is_earnings_month"]
    out["is_last_2_weeks_of_december"] = out["month"].eq(12) & out["day_of_month"].ge(DECEMBER_LAST_2_WEEKS_START_DAY)
    out["is_first_2_weeks_of_january"] = out["month"].eq(1) & out["day_of_month"].le(JANUARY_FIRST_2_WEEKS_END_DAY)
    out["is_september"] = out["month"].eq(9)
    out["is_march"] = out["month"].eq(3)
    out["is_november"] = out["month"].eq(11)
    return out


def coerce_trade_sign(trade_sign: int | pd.Series | np.ndarray, index: pd.Index) -> pd.Series:
    if isinstance(trade_sign, pd.Series):
        series = trade_sign.reindex(index)
    else:
        series = pd.Series(trade_sign, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def anchor_pos_60m(df: pd.DataFrame, trade_sign: pd.Series) -> pd.Series:
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(trade_sign > 0, df["bar_low"], np.where(trade_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def build_trade_sample(source_df: pd.DataFrame, trade_sign: int | pd.Series | np.ndarray) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = coerce_trade_sign(trade_sign, sample.index)
    sample = sample[sample["trade_sign"].ne(0)].copy()

    sample["pos_in_60m"] = anchor_pos_60m(sample, sample["trade_sign"])
    sample["is_60m_extreme"] = (
        ((sample["trade_sign"] > 0) & sample["pos_in_60m"].le(0.20))
        | ((sample["trade_sign"] < 0) & sample["pos_in_60m"].ge(0.80))
    )
    sample["is_15m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_15m"])
    sample["has_core_60m_15m_gate"] = sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]

    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    sample["is_killer_1"] = sample["pos_in_60m"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])
    return sample.reset_index(drop=True)


def compute_thresholds(sample: pd.DataFrame) -> dict[str, float]:
    atr_sample = sample.loc[sample["has_core_60m_15m_gate"], "atr20"].dropna()
    if atr_sample.empty:
        return {"atr20_q25": float("nan"), "atr20_q50": float("nan"), "atr20_q75": float("nan")}
    return {
        "atr20_q25": float(atr_sample.quantile(0.25)),
        "atr20_q50": float(atr_sample.quantile(0.50)),
        "atr20_q75": float(atr_sample.quantile(0.75)),
    }


def add_atr_regime_flags(sample: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = sample.copy()
    q25 = thresholds["atr20_q25"]
    q50 = thresholds["atr20_q50"]
    q75 = thresholds["atr20_q75"]

    out["is_atr_bottom_quartile"] = out["atr20"].lt(q25)
    out["is_atr_q25_to_q50"] = out["atr20"].ge(q25) & out["atr20"].lt(q50)
    out["is_atr_q50_to_q75"] = out["atr20"].ge(q50) & out["atr20"].lt(q75)
    out["is_atr_top_quartile"] = out["atr20"].ge(q75)
    out["atr20_crossed_above_q50"] = (
        out["atr20"].gt(q50)
        & out["atr20_1"].notna()
        & out["atr20_1"].le(q50)
    )
    return out


def summarize_filter(code: str, group: str, label: str, df: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    sample = df.dropna(subset=required_cols).copy()
    n = int(len(sample))
    win_rates: dict[int, float] = {}

    for window in FORWARD_WINDOWS:
        returns = sample[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = sample["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b,
        "wr_10b": win_rates[10],
        "wr_30b": win_rates[30],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b, win_rates[30]),
    }


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | WR10={fmt_pct(float(row['wr_10b']))} | "
        f"WR30={fmt_pct(float(row['wr_30b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))} | "
        f"Persistence={row['persistence']}"
    )


def choose_best_quarter(sample: pd.DataFrame) -> tuple[int, dict[int, dict[str, object]]]:
    quarter_summaries: dict[int, dict[str, object]] = {}
    for quarter in (1, 2, 3, 4):
        filtered = sample.loc[
            sample["has_core_60m_15m_gate"] & sample["is_first_hour"] & sample["quarter"].eq(quarter)
        ].copy()
        quarter_summaries[quarter] = summarize_filter(
            f"Q{quarter}",
            "A",
            f"Q{quarter} + 60m + 15m + first_hour",
            filtered,
        )

    best_quarter = max(
        quarter_summaries,
        key=lambda quarter: (
            float("-inf") if pd.isna(quarter_summaries[quarter]["wr_30b"]) else float(quarter_summaries[quarter]["wr_30b"]),
            float("-inf") if pd.isna(quarter_summaries[quarter]["wr_10b"]) else float(quarter_summaries[quarter]["wr_10b"]),
            float("-inf") if pd.isna(quarter_summaries[quarter]["wr_5b"]) else float(quarter_summaries[quarter]["wr_5b"]),
            int(quarter_summaries[quarter]["n"]),
        ),
    )
    return best_quarter, quarter_summaries


def build_filter_specs(thresholds: dict[str, float], best_quarter: int) -> list[FilterSpec]:
    return [
        (
            "01",
            "A",
            "Q1 (Jan-Mar) + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["quarter"].eq(1),
        ),
        (
            "02",
            "A",
            "Q2 (Apr-Jun) + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["quarter"].eq(2),
        ),
        (
            "03",
            "A",
            "Q3 (Jul-Sep) + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["quarter"].eq(3),
        ),
        (
            "04",
            "A",
            "Q4 (Oct-Dec) + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["is_first_hour"] & df["quarter"].eq(4),
        ),
        (
            "05",
            "A",
            f"Best quarter (Q{best_quarter}) + NOT killers + 60m + 15m + first_hour",
            lambda df, quarter=best_quarter: df["has_core_60m_15m_gate"]
            & df["is_first_hour"]
            & df["passes_not_all_killers"]
            & df["quarter"].eq(quarter),
        ),
        (
            "06",
            "B",
            "First month of quarter + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["month_of_quarter"].eq(1),
        ),
        (
            "07",
            "B",
            "Second month of quarter + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["month_of_quarter"].eq(2),
        ),
        (
            "08",
            "B",
            "Third month of quarter + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["month_of_quarter"].eq(3),
        ),
        (
            "09",
            "B",
            "Earnings month (Jan/Apr/Jul/Oct) + 60m + 15m + NOT killers + first_hour",
            lambda df: df["has_core_60m_15m_gate"]
            & df["is_first_hour"]
            & df["passes_not_all_killers"]
            & df["is_earnings_month"],
        ),
        (
            "10",
            "B",
            "Non-earnings month + 60m + 15m + NOT killers + first_hour",
            lambda df: df["has_core_60m_15m_gate"]
            & df["is_first_hour"]
            & df["passes_not_all_killers"]
            & df["is_non_earnings_month"],
        ),
        (
            "11",
            "C",
            "ATR20 in bottom quartile + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_atr_bottom_quartile"],
        ),
        (
            "12",
            "C",
            "ATR20 in 25-50th percentile + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_atr_q25_to_q50"],
        ),
        (
            "13",
            "C",
            "ATR20 in 50-75th percentile + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_atr_q50_to_q75"],
        ),
        (
            "14",
            "C",
            "ATR20 in top quartile + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_atr_top_quartile"],
        ),
        (
            "15",
            "C",
            "ATR20 crossed above 50th percentile + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["atr20_crossed_above_q50"],
        ),
        (
            "16",
            "D",
            "Last 2 weeks of December + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_last_2_weeks_of_december"],
        ),
        (
            "17",
            "D",
            "First 2 weeks of January + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_first_2_weeks_of_january"],
        ),
        (
            "18",
            "D",
            "September + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_september"],
        ),
        (
            "19",
            "D",
            "March + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_march"],
        ),
        (
            "20",
            "D",
            "November + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["is_november"],
        ),
    ]


def run_filters(sample: pd.DataFrame, thresholds: dict[str, float], best_quarter: int) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate in build_filter_specs(thresholds, best_quarter):
        filtered = sample.loc[predicate(sample)].copy()
        results.append(summarize_filter(code, group, label, filtered))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
            float("-inf") if pd.isna(row["wr_10b"]) else float(row["wr_10b"]),
            float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = [
        "Filter",
        "N",
        "WR 5b",
        "WR 10b",
        "WR 30b",
        "PF 5b",
        "Avg Ticks 5b",
        "Wilson 95% CI (5b)",
        "Persistence",
    ]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. [{row['group']}] {row['label']}",
                f"{int(row['n']):,}",
                fmt_pct(float(row["wr_5b"])),
                fmt_pct(float(row["wr_10b"])),
                fmt_pct(float(row["wr_30b"])),
                fmt_float(float(row["pf_5b"])),
                fmt_float(float(row["avg_ticks_5b"])),
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                str(row["persistence"]),
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
    timeframe_context = build_timeframe_context(bars_1m)
    observations = attach_timeframe_context(observations, timeframe_context)
    observations = compute_bar_features(observations)
    observations = add_time_flags(observations)
    observations = add_seasonal_flags(observations)

    sample = build_trade_sample(observations, observations["direction_sign"])
    thresholds = compute_thresholds(sample)
    sample = add_atr_regime_flags(sample, thresholds)

    best_quarter, quarter_summaries = choose_best_quarter(sample)
    results = run_filters(sample, thresholds, best_quarter)

    base_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", sample)
    base_core = summarize_filter(
        "00A",
        "BASE",
        "60m + 15m core gate",
        sample.loc[sample["has_core_60m_15m_gate"]].copy(),
    )
    base_core_first_hour = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + first_hour",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["is_first_hour"]].copy(),
    )
    base_core_not_killers = summarize_filter(
        "00C",
        "BASE",
        "60m + 15m + NOT killers",
        sample.loc[sample["has_core_60m_15m_gate"] & sample["passes_not_all_killers"]].copy(),
    )

    lines = [
        "DEEP6 round44 seasonal + VIX-proxy analysis",
        "============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        "Seasonal parsing comes from session_date -> month, quarter, month-of-quarter, and day-of-month.",
        "60m gate = bullish bar_low in bottom 20% of active 60m range / bearish bar_high in top 20% of active 60m range.",
        "15m gate = trade direction matches 15m open-close trend sign.",
        "first_hour = 09:30-10:29 ET.",
        "KILLER_1 = trade-direction anchor sits in the middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA volume.",
        "NOT killers = NOT killer_1 AND NOT killer_2.",
        "ATR20 is a rolling 20-bar mean of true range built from deduped signal-event bars within each session.",
        "ATR quartile thresholds use valid ATR20 rows inside the 60m + 15m core sample.",
        "Filter 15 = ATR20 crossed from <= median ATR threshold to > median ATR threshold on the current bar.",
        f"Last 2 weeks of December = Dec {DECEMBER_LAST_2_WEEKS_START_DAY:02d}-31. First 2 weeks of January = Jan 01-{JANUARY_FIRST_2_WEEKS_END_DAY:02d}.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "Final ranking is sorted by WR 30b descending, then WR 10b, WR 5b, N.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped signal bars:                   {len(observations):,}",
        f"Non-zero-delta trade sample:           {len(sample):,}",
        f"15m bars built:                        {len(timeframe_context[15]):,}",
        f"60m bars built:                        {len(timeframe_context[60]):,}",
        f"Core 60m + 15m bars:                   {int(sample['has_core_60m_15m_gate'].sum()):,}",
        f"Core 60m + 15m + first_hour bars:      {int((sample['has_core_60m_15m_gate'] & sample['is_first_hour']).sum()):,}",
        f"Core earnings-month bars:              {int((sample['has_core_60m_15m_gate'] & sample['is_earnings_month']).sum()):,}",
        f"Core non-earnings-month bars:          {int((sample['has_core_60m_15m_gate'] & sample['is_non_earnings_month']).sum()):,}",
        f"Best quarter from filters 1-4:         Q{best_quarter}",
        f"ATR20 25th percentile (core sample):   {fmt_float(thresholds['atr20_q25'])}",
        f"ATR20 50th percentile (core sample):   {fmt_float(thresholds['atr20_q50'])}",
        f"ATR20 75th percentile (core sample):   {fmt_float(thresholds['atr20_q75'])}",
        f"Core ATR20 bottom-quartile bars:       {int((sample['has_core_60m_15m_gate'] & sample['is_atr_bottom_quartile']).sum()):,}",
        f"Core ATR20 25-50th percentile bars:    {int((sample['has_core_60m_15m_gate'] & sample['is_atr_q25_to_q50']).sum()):,}",
        f"Core ATR20 50-75th percentile bars:    {int((sample['has_core_60m_15m_gate'] & sample['is_atr_q50_to_q75']).sum()):,}",
        f"Core ATR20 top-quartile bars:          {int((sample['has_core_60m_15m_gate'] & sample['is_atr_top_quartile']).sum()):,}",
        f"Core ATR20 cross-above-median bars:    {int((sample['has_core_60m_15m_gate'] & sample['atr20_crossed_above_q50']).sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:     {render_summary_line(base_all)}",
        f"60m + 15m core gate:        {render_summary_line(base_core)}",
        f"60m + 15m + first_hour:     {render_summary_line(base_core_first_hour)}",
        f"60m + 15m + NOT killers:    {render_summary_line(base_core_not_killers)}",
        "",
        "Quarter checkpoints used to choose filter 5",
        "-------------------------------------------",
        f"Q1: {render_summary_line(quarter_summaries[1])}",
        f"Q2: {render_summary_line(quarter_summaries[2])}",
        f"Q3: {render_summary_line(quarter_summaries[3])}",
        f"Q4: {render_summary_line(quarter_summaries[4])}",
        "",
        "20 seasonal / earnings-cycle / VIX-proxy filters ranked by 30b win rate",
        "--------------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
