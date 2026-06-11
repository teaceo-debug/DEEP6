#!/usr/bin/env python3
from __future__ import annotations

import calendar
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round21_walkforward_r16_r20_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
ATR_LOOKBACK = 20
VOL_OF_VOL_WINDOW = 10
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FIRST_HOUR_MINUTES = 60
VALIDATION_MONTHS = pd.period_range("2025-01", "2026-04", freq="M")
BETA_PRIOR_ALPHA = 10
BETA_PRIOR_BETA = 10
SMALL_OVERNIGHT_MOVE_TICKS = 20

FOMC_DATES = [
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-17",
    "2026-01-28",
    "2026-03-18",
]


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
    return f"{value:+,.2f}"


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def win_rate(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    return float((returns > 0).mean())


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def beta_credible_interval(alpha: float, beta_value: float, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    try:
        from scipy.stats import beta as scipy_beta

        low = float(scipy_beta.ppf(tail, alpha, beta_value))
        high = float(scipy_beta.ppf(1.0 - tail, alpha, beta_value))
        return low, high
    except Exception:
        mean = alpha / (alpha + beta_value)
        var = (alpha * beta_value) / (((alpha + beta_value) ** 2) * (alpha + beta_value + 1.0))
        z = 1.959963984540054
        margin = z * math.sqrt(var)
        return max(0.0, mean - margin), min(1.0, mean + margin)


def month_period(value: str) -> pd.Period:
    return pd.Period(value, freq="M")


def month_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b %Y")


def month_short_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b-%y")


def format_is_label(is_months: list[pd.Period]) -> str:
    if len(is_months) == 1:
        return month_label(is_months[0])
    first = is_months[0].to_timestamp()
    last = is_months[-1].to_timestamp()
    if first.year == last.year:
        return f"{first.strftime('%b')}-{last.strftime('%b %Y')}"
    return f"{first.strftime('%b %Y')}-{last.strftime('%b %Y')}"


def third_friday(year: int, month: int) -> pd.Timestamp:
    cal = calendar.monthcalendar(year, month)
    friday = calendar.FRIDAY
    fridays = [week[friday] for week in cal if week[friday] != 0]
    return pd.Timestamp(year=year, month=month, day=fridays[2]).normalize()


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
    for window in FORWARD_WINDOWS:
        observations[f"move_{window}b_ticks"] = (
            observations[f"fwd_close_{window}b"] - observations["bar_close"]
        ) / TICK_SIZE
    return observations


def filter_rth_bars(bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars.reset_index(drop=True)


def build_overnight_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    summary = (
        rth_bars.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("ts_event", "first"),
            rth_open=("open", "first"),
            rth_close=("close", "last"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    summary["prior_rth_close"] = summary["rth_close"].shift(1)
    summary["overnight_move_ticks"] = (summary["rth_open"] - summary["prior_rth_close"]) / TICK_SIZE
    summary["abs_overnight_move_ticks"] = summary["overnight_move_ticks"].abs()
    return summary[
        [
            "session_date",
            "rth_open",
            "prior_rth_close",
            "overnight_move_ticks",
            "abs_overnight_move_ticks",
        ]
    ].copy()


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


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["delta_ratio"] = np.where(out["bar_volume"] > 0, out["bar_delta"].abs() / out["bar_volume"], np.nan)
    out["prior_close"] = by_session["bar_close"].shift(1)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["bar_range_2"] = by_session["bar_range"].shift(2)

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
        lambda s: s.rolling(ATR_LOOKBACK, min_periods=ATR_LOOKBACK).mean()
    )
    out["vol_of_vol"] = by_session["atr20"].transform(
        lambda s: s.rolling(VOL_OF_VOL_WINDOW, min_periods=VOL_OF_VOL_WINDOW).std()
    )
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )

    out["is_very_low_delta_ratio"] = out["delta_ratio"].lt(0.05)
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_three_narrowing_ranges"] = (
        out["bar_range_2"].notna()
        & out["prior_bar_range"].lt(out["bar_range_2"])
        & out["bar_range"].lt(out["prior_bar_range"])
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    bool_cols = [
        "is_very_low_delta_ratio",
        "is_doji",
        "is_three_narrowing_ranges",
        "is_volume_spike_3x",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
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
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def build_trading_calendar(bars_1m: pd.DataFrame) -> pd.DatetimeIndex:
    minute_of_day = bars_1m["ts_event"].dt.hour * 60 + bars_1m["ts_event"].dt.minute
    rth_mask = minute_of_day.ge(RTH_START_MINUTE) & minute_of_day.lt(RTH_END_MINUTE)
    sessions = (
        bars_1m.loc[rth_mask, "ts_event"]
        .dt.tz_localize(None)
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )
    return pd.DatetimeIndex(sessions)


def expand_session_offsets(
    session_dates: pd.DatetimeIndex,
    anchor_dates: list[str],
    offsets: tuple[int, ...],
) -> set[pd.Timestamp]:
    index_by_date = {session_date: idx for idx, session_date in enumerate(session_dates)}
    selected: set[pd.Timestamp] = set()

    for raw_date in anchor_dates:
        anchor = pd.Timestamp(raw_date).normalize()
        anchor_idx = index_by_date.get(anchor)
        if anchor_idx is None:
            continue
        for offset in offsets:
            target_idx = anchor_idx + offset
            if 0 <= target_idx < len(session_dates):
                selected.add(session_dates[target_idx])
    return selected


def build_session_calendar(bars_1m: pd.DataFrame) -> pd.DataFrame:
    session_dates = build_trading_calendar(bars_1m)
    calendar_df = pd.DataFrame({"session_date_ts": session_dates}).sort_values("session_date_ts").reset_index(drop=True)
    calendar_df["year"] = calendar_df["session_date_ts"].dt.year
    calendar_df["month"] = calendar_df["session_date_ts"].dt.month
    calendar_df["month_period"] = calendar_df["session_date_ts"].dt.to_period("M")

    calendar_df["is_summer"] = calendar_df["month"].isin([6, 7, 8])
    calendar_df["is_not_summer"] = ~calendar_df["is_summer"]

    for year, month in calendar_df[["year", "month"]].drop_duplicates().itertuples(index=False):
        _ = third_friday(int(year), int(month))

    fomc_day_dates = expand_session_offsets(session_dates, FOMC_DATES, (0,))

    calendar_df["is_fomc_day"] = calendar_df["session_date_ts"].isin(fomc_day_dates)
    calendar_df["is_not_fomc_day"] = ~calendar_df["is_fomc_day"]
    return calendar_df[
        [
            "session_date_ts",
            "is_summer",
            "is_not_summer",
            "is_fomc_day",
            "is_not_fomc_day",
        ]
    ].copy()


def attach_calendar_flags(observations: pd.DataFrame, calendar_df: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    out["session_date_ts"] = pd.to_datetime(out["session_date"], errors="coerce")
    out = out.merge(calendar_df, on="session_date_ts", how="left", validate="many_to_one")
    bool_cols = [
        "is_summer",
        "is_not_summer",
        "is_fomc_day",
        "is_not_fomc_day",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_session_structure_summary(observations: pd.DataFrame) -> pd.DataFrame:
    working = observations.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    working["bar_pv"] = working["bar_close"] * working["bar_volume"]

    summary = (
        working.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_high=("bar_high", "max"),
            session_low=("bar_low", "min"),
            session_close=("bar_close", "last"),
            session_volume=("bar_volume", "sum"),
            session_pv=("bar_pv", "sum"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )

    summary["session_vwap"] = np.where(
        summary["session_volume"] > 0,
        summary["session_pv"] / summary["session_volume"],
        np.nan,
    )
    summary["prior_session_high"] = summary["session_high"].shift(1)
    summary["prior_session_low"] = summary["session_low"].shift(1)
    summary["session_is_inside_day"] = (
        summary["prior_session_high"].notna()
        & summary["session_high"].lt(summary["prior_session_high"])
        & summary["session_low"].gt(summary["prior_session_low"])
    )
    summary["prior_session_is_inside_day"] = summary["session_is_inside_day"].shift(1)
    return summary[
        [
            "session_date",
            "prior_session_high",
            "prior_session_low",
            "prior_session_is_inside_day",
        ]
    ].copy()


def attach_session_weekly_context(observations: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    running = observations.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    session_date_dt = pd.to_datetime(running["session_date"], errors="coerce")
    iso = session_date_dt.dt.isocalendar()
    running["iso_year"] = iso.year.astype("Int64")
    running["iso_week"] = iso.week.astype("Int64")

    by_session = running.groupby("session_date", sort=False)
    running["developing_session_high"] = by_session["bar_high"].cummax()
    running["developing_session_low"] = by_session["bar_low"].cummin()

    by_week = running.groupby(["iso_year", "iso_week"], sort=False)
    running["prior_weekly_high"] = by_week["bar_high"].transform(lambda s: s.cummax().shift(1))
    running["prior_weekly_low"] = by_week["bar_low"].transform(lambda s: s.cummin().shift(1))
    running["broke_weekly_high"] = running["prior_weekly_high"].notna() & running["bar_high"].gt(running["prior_weekly_high"])
    running["broke_weekly_low"] = running["prior_weekly_low"].notna() & running["bar_low"].lt(running["prior_weekly_low"])

    out = observations.merge(session_summary, on="session_date", how="left", validate="many_to_one")
    out = out.merge(
        running[
            [
                "global_index",
                "developing_session_high",
                "developing_session_low",
                "prior_weekly_high",
                "prior_weekly_low",
                "broke_weekly_high",
                "broke_weekly_low",
            ]
        ],
        on="global_index",
        how="left",
        validate="many_to_one",
    )

    out["is_inside_day"] = (
        out["prior_session_high"].notna()
        & out["developing_session_high"].lt(out["prior_session_high"])
        & out["developing_session_low"].gt(out["prior_session_low"])
    )
    out["is_consecutive_inside_day"] = out["is_inside_day"] & out["prior_session_is_inside_day"].fillna(False)

    bool_cols = [
        "broke_weekly_high",
        "broke_weekly_low",
        "is_inside_day",
        "is_consecutive_inside_day",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def attach_overnight_context(observations: pd.DataFrame, overnight_context: pd.DataFrame) -> pd.DataFrame:
    return observations.merge(overnight_context, on="session_date", how="left", validate="many_to_one")


def coerce_trade_sign(trade_sign: int | pd.Series | np.ndarray, index: pd.Index) -> pd.Series:
    if isinstance(trade_sign, pd.Series):
        series = trade_sign.reindex(index)
    else:
        series = pd.Series(trade_sign, index=index)
    return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)


def anchor_pos_in_range(df: pd.DataFrame, trade_sign: pd.Series, tf: int) -> pd.Series:
    rng = df[f"range_{tf}m"].replace(0, np.nan)
    anchor = np.where(trade_sign > 0, df["bar_low"], np.where(trade_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df[f"low_{tf}m"]) / rng, index=df.index)


def build_trade_sample(source_df: pd.DataFrame, trade_sign: int | pd.Series | np.ndarray) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = coerce_trade_sign(trade_sign, sample.index)
    sample = sample[sample["trade_sign"].ne(0)].copy()

    sample["pos_60m_anchor"] = anchor_pos_in_range(sample, sample["trade_sign"], 60)
    sample["is_60m_extreme"] = (
        ((sample["trade_sign"] > 0) & sample["pos_60m_anchor"].le(0.20))
        | ((sample["trade_sign"] < 0) & sample["pos_60m_anchor"].ge(0.80))
    )
    sample["is_15m_trend_aligned"] = sample["trade_sign"].eq(sample["trend_sign_15m"])
    sample["has_core_60m_15m_gate"] = sample["is_60m_extreme"] & sample["is_15m_trend_aligned"]

    sample["is_killer_1"] = sample["pos_60m_anchor"].between(0.40, 0.60, inclusive="both")
    sample["is_killer_2"] = sample["is_volume_spike_3x"]
    sample["passes_not_all_killers"] = (~sample["is_killer_1"]) & (~sample["is_killer_2"])

    for window in FORWARD_WINDOWS:
        sample[f"trade_ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]

    bool_cols = [
        "is_60m_extreme",
        "is_15m_trend_aligned",
        "has_core_60m_15m_gate",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
    ]
    for col in bool_cols:
        sample[col] = sample[col].fillna(False).astype(bool)
    return sample.reset_index(drop=True)


def build_session_performance_summary(bar_sample: pd.DataFrame) -> pd.DataFrame:
    working = bar_sample.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    working["qualifying_ret_5b_ticks"] = working["trade_ret_5b_ticks"].where(working["has_core_60m_15m_gate"])
    working["qualifying_win_5b"] = np.where(
        working["has_core_60m_15m_gate"],
        working["trade_ret_5b_ticks"].gt(0),
        np.nan,
    )

    summary = (
        working.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_qualifying_count=("has_core_60m_15m_gate", "sum"),
            session_avg_ret_5b_ticks=("qualifying_ret_5b_ticks", "mean"),
            session_wr_5b=("qualifying_win_5b", "mean"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    summary["session_has_qualifying"] = summary["session_qualifying_count"].gt(0)
    summary["session_is_losing"] = summary["session_has_qualifying"] & summary["session_avg_ret_5b_ticks"].le(0)
    summary["prior_session_is_losing"] = summary["session_is_losing"].shift(1)

    qualified = summary.loc[summary["session_has_qualifying"], ["session_date", "session_avg_ret_5b_ticks"]].copy()
    qualified["rolling_5_session_avg_ret_5b_ticks"] = qualified["session_avg_ret_5b_ticks"].shift(1).rolling(5, min_periods=5).mean()
    summary = summary.merge(
        qualified[["session_date", "rolling_5_session_avg_ret_5b_ticks"]],
        on="session_date",
        how="left",
        validate="one_to_one",
    )

    summary["prior_session_is_losing"] = summary["prior_session_is_losing"].fillna(False).astype(bool)
    return summary[
        [
            "session_date",
            "session_has_qualifying",
            "session_is_losing",
            "prior_session_is_losing",
            "rolling_5_session_avg_ret_5b_ticks",
        ]
    ].copy()


def merge_session_performance_context(bar_sample: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    out = bar_sample.merge(session_summary, on="session_date", how="left", validate="many_to_one")
    for col in ["session_has_qualifying", "session_is_losing", "prior_session_is_losing"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_validation_samples() -> tuple[pd.DataFrame, pd.DataFrame, dict[int, pd.DataFrame], int, float, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)

    timeframe_context = build_timeframe_context(bars_1m)
    overnight_context = build_overnight_context(filter_rth_bars(bars_1m))
    calendar_df = build_session_calendar(bars_1m)
    session_structure_summary = build_session_structure_summary(observations)

    observations = attach_timeframe_context(observations, timeframe_context)
    observations = attach_overnight_context(observations, overnight_context)
    observations = compute_bar_features(observations)
    observations = compute_cvd_features(observations)
    observations = add_time_flags(observations)
    observations = attach_calendar_flags(observations, calendar_df)
    observations = attach_session_weekly_context(observations, session_structure_summary)
    observations["session_month"] = observations["session_date_ts"].dt.to_period("M")
    observations = observations[observations["session_month"].isin(VALIDATION_MONTHS)].copy()
    observations = observations.sort_values(["bar_ts", "global_index"], kind="stable").reset_index(drop=True)

    bar_sample = build_trade_sample(observations, observations["direction_sign"])
    stable_vol_threshold = float(bar_sample["vol_of_vol"].dropna().quantile(0.25)) if bar_sample["vol_of_vol"].notna().any() else float("nan")
    bar_sample["is_stable_vol"] = bar_sample["vol_of_vol"].lt(stable_vol_threshold)
    bar_sample["is_small_overnight"] = bar_sample["abs_overnight_move_ticks"].lt(SMALL_OVERNIGHT_MOVE_TICKS)

    session_perf_summary = build_session_performance_summary(bar_sample)
    bar_sample = merge_session_performance_context(bar_sample, session_perf_summary)

    div_source = observations.loc[observations["is_cvd_divergence"]].copy()
    div_sample = build_trade_sample(div_source, div_source["divergence_sign"])
    div_sample["is_stable_vol"] = div_sample["vol_of_vol"].lt(stable_vol_threshold)
    div_sample["is_small_overnight"] = div_sample["abs_overnight_move_ticks"].lt(SMALL_OVERNIGHT_MOVE_TICKS)
    div_sample["matches_weekly_breakout"] = (
        ((div_sample["trade_sign"] > 0) & div_sample["broke_weekly_low"])
        | ((div_sample["trade_sign"] < 0) & div_sample["broke_weekly_high"])
    )

    for df in [bar_sample, div_sample]:
        for col in ["is_stable_vol", "is_small_overnight"]:
            df[col] = df[col].fillna(False).astype(bool)
    div_sample["matches_weekly_breakout"] = div_sample["matches_weekly_breakout"].fillna(False).astype(bool)

    return bar_sample, div_sample, timeframe_context, len(events), stable_vol_threshold, session_perf_summary


def build_walk_forward_windows() -> list[dict[str, object]]:
    raw_specs = [
        (1, ["2025-01", "2025-02"], "2025-03"),
        (2, ["2025-04", "2025-05"], "2025-06"),
        (3, ["2025-06", "2025-07"], "2025-08"),
        (4, ["2025-09", "2025-10"], "2025-11"),
        (5, ["2025-11", "2025-12"], "2026-01"),
        (6, ["2026-02", "2026-03"], "2026-04"),
    ]
    windows: list[dict[str, object]] = []
    for window_num, is_labels, oos_label in raw_specs:
        is_months = [month_period(label) for label in is_labels]
        oos_month = month_period(oos_label)
        windows.append(
            {
                "window_num": window_num,
                "is_months": is_months,
                "oos_month": oos_month,
                "label": f"{format_is_label(is_months)} IS → {month_label(oos_month)} OOS",
            }
        )
    return windows


def sample_stats(df: pd.DataFrame, eval_window: int) -> dict[str, float | int]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    returns = df[ret_col].dropna()
    n = int(len(returns))
    wins = int((returns > 0).sum())
    ci_low, ci_high, wr_hat = wilson_ci(n, wins)
    return {
        "n": n,
        "wins": wins,
        "wr": win_rate(returns),
        "pf": profit_factor(returns) if n else float("nan"),
        "avg_ticks": float(returns.mean()) if n else float("nan"),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "wr_hat": wr_hat,
    }


def walk_forward_analysis(df: pd.DataFrame, windows: list[dict[str, object]], eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    oos_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    weak_windows: list[str] = []

    for window in windows:
        is_months = list(window["is_months"])
        oos_month = window["oos_month"]

        is_df = df.loc[df["session_month"].isin(is_months)].copy()
        oos_df = df.loc[df["session_month"].eq(oos_month)].copy()

        is_ret = is_df[ret_col].dropna()
        oos_ret = oos_df[ret_col].dropna()
        oos_n = int(len(oos_ret))
        oos_wins = int((oos_ret > 0).sum())
        oos_wr = win_rate(oos_ret)
        oos_avg_ticks = float(oos_ret.mean()) if oos_n else float("nan")

        rows.append(
            {
                "window_num": int(window["window_num"]),
                "label": str(window["label"]),
                "is_n": int(len(is_ret)),
                "is_wr": win_rate(is_ret),
                "oos_month": oos_month,
                "oos_n": oos_n,
                "oos_wins": oos_wins,
                "oos_wr": oos_wr,
                "oos_avg_ticks": oos_avg_ticks,
            }
        )
        if oos_n and oos_wr < 0.40:
            weak_windows.append(str(window["label"]))
        if oos_n:
            oos_frames.append(oos_df.loc[oos_df[ret_col].notna()].copy())

    oos_trade_df = pd.concat(oos_frames, ignore_index=True) if oos_frames else df.iloc[0:0].copy()
    oos_ret = oos_trade_df[ret_col].dropna()
    oos_n = int(len(oos_ret))
    oos_wins = int((oos_ret > 0).sum())
    oos_ci_low, oos_ci_high, oos_wr_hat = wilson_ci(oos_n, oos_wins)
    oos_wr = win_rate(oos_ret)
    oos_avg = float(oos_ret.mean()) if oos_n else float("nan")

    if oos_n == 0:
        status = "FAIL"
        reason = "no out-of-sample trades"
    elif weak_windows:
        status = "FAIL"
        reason = f"{len(weak_windows)} OOS window(s) below 40% WR"
    else:
        status = "PASS"
        reason = "no OOS window below 40% WR"

    return {
        "rows": rows,
        "oos_trade_df": oos_trade_df,
        "oos_n": oos_n,
        "oos_wins": oos_wins,
        "oos_wr": oos_wr,
        "oos_avg_ticks": oos_avg,
        "oos_ci_low": oos_ci_low,
        "oos_ci_high": oos_ci_high,
        "oos_wr_hat": oos_wr_hat,
        "weak_windows": weak_windows,
        "status": status,
        "reason": reason,
    }


def longest_losing_trade_streak(df: pd.DataFrame, eval_window: int) -> int:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    returns = df.sort_values(["bar_ts", "global_index"], kind="stable")[ret_col].dropna()
    longest = 0
    current = 0
    for value in returns:
        if value <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def monthly_stability(df: pd.DataFrame, months: list[pd.Period], eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    rows: list[dict[str, object]] = []
    for month in months:
        month_df = df.loc[df["session_month"].eq(month)].copy()
        ret = month_df[ret_col].dropna()
        n = int(len(ret))
        rows.append(
            {
                "month": month,
                "label": month_short_label(month),
                "n": n,
                "wr": win_rate(ret),
                "avg_ticks": float(ret.mean()) if n else float("nan"),
            }
        )

    active_rows = [row for row in rows if row["n"] > 0]
    good_months = sum(1 for row in active_rows if row["wr"] > 0.50)
    flagged_bad_months: list[str] = []
    longest_bad_month_streak = 0
    current_bad_month_streak = 0

    for row in active_rows:
        if row["wr"] < 0.50:
            current_bad_month_streak += 1
            longest_bad_month_streak = max(longest_bad_month_streak, current_bad_month_streak)
        else:
            current_bad_month_streak = 0
        if row["n"] >= 3 and row["wr"] < 0.35:
            flagged_bad_months.append(row["label"])

    if not active_rows:
        status = "FAIL"
        reason = "no monthly OOS trades"
    elif flagged_bad_months:
        status = "FAIL"
        reason = f"month(s) below 35% WR with N>=3: {', '.join(flagged_bad_months)}"
    else:
        status = "PASS"
        reason = "no OOS month below 35% WR with N>=3"

    return {
        "rows": rows,
        "active_months": len(active_rows),
        "good_months": good_months,
        "flagged_bad_months": flagged_bad_months,
        "longest_bad_month_streak": longest_bad_month_streak,
        "longest_losing_trade_streak": longest_losing_trade_streak(df, eval_window),
        "status": status,
        "reason": reason,
    }


def bayesian_analysis(df: pd.DataFrame, eval_window: int) -> dict[str, object]:
    ret_col = f"trade_ret_{eval_window}b_ticks"
    ret = df[ret_col].dropna()
    n = int(len(ret))
    wins = int((ret > 0).sum())
    losses = n - wins
    posterior_alpha = BETA_PRIOR_ALPHA + wins
    posterior_beta = BETA_PRIOR_BETA + losses
    observed_wr = win_rate(ret)
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
    ci_low, ci_high = beta_credible_interval(posterior_alpha, posterior_beta)
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "observed_wr": observed_wr,
        "posterior_alpha": posterior_alpha,
        "posterior_beta": posterior_beta,
        "posterior_mean": float(posterior_mean),
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def overall_verdict(walk_forward: dict[str, object], monthly: dict[str, object], bayes: dict[str, object]) -> str:
    oos_wr = float(walk_forward["oos_wr"])
    posterior_mean = float(bayes["posterior_mean"])
    has_bad_month = bool(monthly["flagged_bad_months"])
    if not pd.isna(oos_wr) and oos_wr > 0.55 and not has_bad_month and posterior_mean > 0.55:
        return "DEPLOY"
    if not pd.isna(oos_wr) and oos_wr > 0.50 and posterior_mean > 0.50:
        return "PAPER TRADE"
    return "INSUFFICIENT"


def sample_label(sample_key: str) -> str:
    labels = {
        "bar": "bar sample / sign(bar_delta)",
        "div": "CVD divergence sample / divergence_sign",
    }
    return labels[sample_key]


def build_filter_specs() -> list[dict[str, object]]:
    return [
        {
            "code": "01",
            "source_round": "R17",
            "label": "Stable vol + 60m + 15m + first_hour",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_stable_vol"] & df["has_core_60m_15m_gate"] & df["is_first_hour"],
            "ref_n": 64,
            "ref_wr": 0.984,
        },
        {
            "code": "02",
            "source_round": "R17",
            "label": "3 bars contracting ranges + 60m + 15m",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_three_narrowing_ranges"] & df["has_core_60m_15m_gate"],
            "ref_n": 1970,
            "ref_wr": 0.869,
        },
        {
            "code": "03",
            "source_round": "R18",
            "label": "Consecutive inside days + 60m + 15m",
            "sample_key": "bar",
            "eval_window": 5,
            "predicate": lambda df: df["is_consecutive_inside_day"] & df["has_core_60m_15m_gate"],
            "ref_avg_ticks": 199.7,
        },
        {
            "code": "04",
            "source_round": "R16",
            "label": "Rolling 5-session avg return > +30 ticks + 60m + 15m + first_hour",
            "sample_key": "bar",
            "eval_window": 5,
            "predicate": lambda df: df["has_core_60m_15m_gate"]
            & df["rolling_5_session_avg_ret_5b_ticks"].gt(30)
            & df["is_first_hour"],
            "ref_n": 2329,
            "ref_avg_ticks": 98.6,
        },
        {
            "code": "05",
            "source_round": "R20",
            "label": "CVD divergence + doji + stable vol + 60m + 15m + NOT killers + first_hour",
            "sample_key": "div",
            "eval_window": 30,
            "predicate": lambda df: df["is_doji"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
            "note": "R20 ultra-stack reconstructed from the supplied brief because round20_ultra_stack.py was not present in scripts/.",
        },
        {
            "code": "06",
            "source_round": "R20",
            "label": "Doji + stable vol + small overnight + 60m + 15m + NOT killers + first_hour",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_doji"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        },
        {
            "code": "07",
            "source_round": "R20",
            "label": "|delta|/vol < 0.05 + stable vol + 60m + 15m + NOT killers + first_hour",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_very_low_delta_ratio"]
            & df["is_stable_vol"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        },
        {
            "code": "08",
            "source_round": "R20",
            "label": "CVD divergence + doji + small overnight + 60m + 15m + NOT killers + first_hour",
            "sample_key": "div",
            "eval_window": 30,
            "predicate": lambda df: df["is_doji"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        },
        {
            "code": "09",
            "source_round": "R20",
            "label": "Doji + NOT FOMC + NOT summer + 60m + 15m + NOT killers + first_hour",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_doji"]
            & df["is_not_fomc_day"]
            & df["is_not_summer"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
        },
        {
            "code": "10",
            "source_round": "R20",
            "label": "3 narrowing ranges + stable vol + small overnight + 60m + 15m + NOT killers",
            "sample_key": "bar",
            "eval_window": 30,
            "predicate": lambda df: df["is_three_narrowing_ranges"]
            & df["is_stable_vol"]
            & df["is_small_overnight"]
            & df["has_core_60m_15m_gate"]
            & df["passes_not_all_killers"],
        },
        {
            "code": "11",
            "source_round": "R18",
            "label": "Weekly breakout + CVD divergence + 60m + 15m + NOT killers",
            "sample_key": "div",
            "eval_window": 5,
            "predicate": lambda df: df["matches_weekly_breakout"] & df["has_core_60m_15m_gate"] & df["passes_not_all_killers"],
            "note": "Weekly breakout is symmetric by divergence direction: bullish divergence requires a fresh weekly low; bearish divergence requires a fresh weekly high.",
        },
        {
            "code": "12",
            "source_round": "R16",
            "label": "Prior losing session + 60m + 15m + NOT killers + first_hour",
            "sample_key": "bar",
            "eval_window": 5,
            "predicate": lambda df: df["has_core_60m_15m_gate"]
            & df["prior_session_is_losing"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
            "ref_n": 23,
        },
    ]


def validate_filter(
    sample_df: pd.DataFrame,
    filter_spec: dict[str, object],
    windows: list[dict[str, object]],
    oos_months: list[pd.Period],
) -> dict[str, object]:
    filtered = sample_df.loc[filter_spec["predicate"](sample_df)].copy()
    eval_window = int(filter_spec["eval_window"])
    stats = sample_stats(filtered, eval_window)
    walk_forward = walk_forward_analysis(filtered, windows, eval_window)
    oos_trade_df = walk_forward["oos_trade_df"]
    monthly = monthly_stability(oos_trade_df, oos_months, eval_window)
    bayes = bayesian_analysis(oos_trade_df, eval_window)

    return {
        "filter_code": str(filter_spec["code"]),
        "source_round": str(filter_spec["source_round"]),
        "label": str(filter_spec["label"]),
        "sample_key": str(filter_spec["sample_key"]),
        "eval_window": eval_window,
        "ref_n": filter_spec.get("ref_n"),
        "ref_wr": filter_spec.get("ref_wr"),
        "ref_avg_ticks": filter_spec.get("ref_avg_ticks"),
        "note": filter_spec.get("note"),
        "n": int(stats["n"]),
        "wr": float(stats["wr"]),
        "pf": float(stats["pf"]),
        "avg_ticks": float(stats["avg_ticks"]),
        "walk_forward": walk_forward,
        "monthly": monthly,
        "bayes": bayes,
        "verdict": overall_verdict(walk_forward, monthly, bayes),
    }


def render_reference_line(result: dict[str, object]) -> str | None:
    parts: list[str] = []
    ref_n = result["ref_n"]
    ref_wr = result["ref_wr"]
    ref_avg_ticks = result["ref_avg_ticks"]

    if ref_n is not None:
        parts.append(f"N={int(ref_n):,}")
    if ref_wr is not None:
        parts.append(f"WR={fmt_pct(float(ref_wr))}")
    if ref_avg_ticks is not None:
        parts.append(f"Avg={fmt_ticks(float(ref_avg_ticks))} ticks")

    if not parts:
        return None
    return f"Discovery reference ({result['source_round']}, {result['eval_window']}b): " + " | ".join(parts)


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Rank", "Round", "Eval", "Filter", "N", "WR%", "OOS N", "OOS WR%", "OOS Wilson 95% CI", "OOS Bayes", "Verdict"]
    data_rows: list[list[str]] = []

    for idx, row in enumerate(results, start=1):
        walk_forward = row["walk_forward"]
        bayes = row["bayes"]
        data_rows.append(
            [
                str(idx),
                str(row["source_round"]),
                f"{int(row['eval_window'])}b",
                f"{row['filter_code']}. {row['label']}",
                f"{int(row['n']):,}",
                fmt_pct(float(row["wr"])),
                f"{int(walk_forward['oos_n']):,}",
                fmt_pct(float(walk_forward["oos_wr"])),
                fmt_ci(float(walk_forward["oos_ci_low"]), float(walk_forward["oos_ci_high"])),
                fmt_pct(float(bayes["posterior_mean"])),
                str(row["verdict"]),
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


def render_baseline_line(label: str, df: pd.DataFrame, eval_window: int) -> str:
    stats = sample_stats(df, eval_window)
    return (
        f"{label}: N={int(stats['n']):,} | WR={fmt_pct(float(stats['wr']))} | PF={fmt_float(float(stats['pf']))} | "
        f"Avg={fmt_ticks(float(stats['avg_ticks']))} ticks | CI={fmt_ci(float(stats['ci_low']), float(stats['ci_high']))}"
    )


def render_filter_report(result: dict[str, object]) -> list[str]:
    walk_forward = result["walk_forward"]
    monthly = result["monthly"]
    bayes = result["bayes"]
    weak_windows = walk_forward["weak_windows"]
    reference_line = render_reference_line(result)

    lines = [
        f"FILTER {result['filter_code']}: {result['label']}",
        "-" * (8 + len(result["filter_code"]) + len(result["label"])),
        f"Source round: {result['source_round']}",
        f"Observation frame: {sample_label(str(result['sample_key']))}",
        f"Evaluation horizon: {int(result['eval_window'])} bars forward",
        f"Discovery sample: N={result['n']:,}, WR={fmt_pct(float(result['wr']))}, PF={fmt_float(float(result['pf']))}, Avg={fmt_ticks(float(result['avg_ticks']))} ticks",
    ]
    if reference_line is not None:
        lines.append(reference_line)
    if result["note"]:
        lines.append(f"Note: {result['note']}")

    lines.extend(
        [
            "",
            f"A) Walk-Forward ({len(walk_forward['rows'])} fixed windows, 2mo IS / 1mo OOS):",
        ]
    )
    for row in walk_forward["rows"]:
        lines.append(
            f"  Window {int(row['window_num'])} ({row['label']}): IS N={int(row['is_n'])}, IS WR={fmt_pct(float(row['is_wr']))} | "
            f"OOS N={int(row['oos_n'])}, Wins={int(row['oos_wins'])}, WR={fmt_pct(float(row['oos_wr']))}, Avg={fmt_ticks(float(row['oos_avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Composite OOS: N={int(walk_forward['oos_n'])}, Wins={int(walk_forward['oos_wins'])}, WR={fmt_pct(float(walk_forward['oos_wr']))}, Avg={fmt_ticks(float(walk_forward['oos_avg_ticks']))} ticks",
            f"  OOS Wilson 95% CI: {fmt_ci(float(walk_forward['oos_ci_low']), float(walk_forward['oos_ci_high']))}",
            f"  Any OOS window < 40% WR: {'YES' if weak_windows else 'NO'}",
            f"  [{walk_forward['status']}]: {walk_forward['reason']}",
            "",
            "B) Monthly Stability (OOS months only):",
        ]
    )
    for row in monthly["rows"]:
        lines.append(
            f"  {row['label']}: N={int(row['n'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Months > 50% WR: {int(monthly['good_months'])}/{int(monthly['active_months'])}",
            f"  Longest bad-month streak (<50% WR): {int(monthly['longest_bad_month_streak'])}",
            f"  Longest losing trade streak (composite OOS): {int(monthly['longest_losing_trade_streak'])}",
            f"  [{monthly['status']}]: {monthly['reason']}",
            "",
            "C) Bayesian (Composite OOS):",
            f"  Prior: Beta({BETA_PRIOR_ALPHA}, {BETA_PRIOR_BETA}), mean=50.0%",
            f"  Posterior: Beta({int(bayes['posterior_alpha'])}, {int(bayes['posterior_beta'])}), mean={fmt_pct(float(bayes['posterior_mean']))}",
            f"  95% Credible Interval: {fmt_ci(float(bayes['ci_low']), float(bayes['ci_high']))}",
            f"  Shrinkage: {fmt_pct(float(bayes['observed_wr']))} → {fmt_pct(float(bayes['posterior_mean']))}",
            "",
            f"OVERALL VERDICT: {result['verdict']}",
            "- DEPLOY: composite OOS WR > 55%, no OOS month below 35% WR (N>=3), posterior > 55%",
            "- PAPER TRADE: composite OOS WR > 50% and posterior > 50%",
            "- INSUFFICIENT: otherwise",
            "",
        ]
    )
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bar_sample, div_sample, timeframe_context, raw_event_count, stable_vol_threshold, session_perf_summary = build_validation_samples()
    windows = build_walk_forward_windows()
    oos_months = [window["oos_month"] for window in windows]

    samples = {
        "bar": bar_sample,
        "div": div_sample,
    }

    results: list[dict[str, object]] = []
    for filter_spec in build_filter_specs():
        sample_df = samples[str(filter_spec["sample_key"])]
        results.append(validate_filter(sample_df, filter_spec, windows, oos_months))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["walk_forward"]["oos_wr"]) else float(row["walk_forward"]["oos_wr"]),
            int(row["walk_forward"]["oos_n"]),
            float("-inf") if pd.isna(row["bayes"]["posterior_mean"]) else float(row["bayes"]["posterior_mean"]),
            float("-inf") if pd.isna(row["wr"]) else float(row["wr"]),
            int(row["n"]),
        ),
        reverse=True,
    )

    lines = [
        "ROUND 21 WALK-FORWARD VALIDATION (R16-R18 + R20 TOP 12)",
        "======================================================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction: sign(bar_delta) for non-divergence filters; divergence_sign for CVD divergence filters.",
        "Core gate: 60m_extreme = trade-direction anchor in bottom 20% / top 20% of the active 60m bar; 15m gate = trade_sign aligned with the active 15m trend.",
        "Stable vol = rolling 10-bar std of ATR20 below the 25th percentile of the validation-period bar sample.",
        "ATR20 uses grouped signal bars inside each session: ATR20 = rolling 20-bar mean of true range.",
        "Small overnight move = |09:30 RTH open - prior RTH close| < 20 ticks (5 points).",
        "Inside day = developing_session_high < prior_session_high AND developing_session_low > prior_session_low.",
        "Consecutive inside days = current developing inside day AND the completed prior session was also an inside day.",
        "Rolling 5-session avg return uses the prior 5 qualifying sessions' 5-bar average returns, where qualifying sessions have at least one core-gated bar-direction trade.",
        "Doji = abs(close-open) < 10% of bar range. |delta|/vol = abs(bar_delta) / bar_volume.",
        "CVD divergence = price makes a new session high/low while cumulative delta fails to confirm; divergence filters trade in divergence_sign direction.",
        "NOT killers = NOT killer_1 (trade anchor in middle 40-60% of the active 60m range) AND NOT killer_2 (bar_volume > 3x prior 20-bar EMA volume).",
        "NOT FOMC uses the exact supplied FOMC session dates. NOT summer = session month not in Jun-Aug.",
        "Round20 source note: round20_ultra_stack.py was not present in scripts/, so R20 filters were rebuilt from the supplied brief plus the existing round12/13/14/16/17/18 primitives.",
        "Walk-forward windows: Jan-Feb→Mar 2025, Apr-May→Jun 2025, Jun-Jul→Aug 2025, Sep-Oct→Nov 2025, Nov-Dec 2025→Jan 2026, Feb-Mar→Apr 2026.",
        "R16/R18 filters are scored on 5b forward returns. R17 and reconstructed R20 stack filters are scored on 30b forward returns.",
        "Monthly stability and Bayesian metrics are computed on the composite OOS trades only.",
        "",
        f"Raw event rows loaded:                      {raw_event_count:,}",
        f"Tradable bar-direction sample:              {len(bar_sample):,}",
        f"Tradable CVD-divergence sample:             {len(div_sample):,}",
        f"15m bars built:                             {len(timeframe_context[15]):,}",
        f"60m bars built:                             {len(timeframe_context[60]):,}",
        f"Stable-vol threshold (q25 vol-of-vol):      {fmt_float(stable_vol_threshold)}",
        f"Stable-vol observations:                    {int(bar_sample['is_stable_vol'].sum()):,}",
        f"Doji observations:                          {int(bar_sample['is_doji'].sum()):,}",
        f"Very-low delta-ratio observations (<0.05):  {int(bar_sample['is_very_low_delta_ratio'].sum()):,}",
        f"3 narrowing-range observations:             {int(bar_sample['is_three_narrowing_ranges'].sum()):,}",
        f"Small-overnight observations:               {int(bar_sample['is_small_overnight'].sum()):,}",
        f"Consecutive inside-day observations:        {int(bar_sample['is_consecutive_inside_day'].sum()):,}",
        f"Core NOT-killer observations:               {int((bar_sample['has_core_60m_15m_gate'] & bar_sample['passes_not_all_killers']).sum()):,}",
        f"Sessions with rolling-5 qualifying context: {int(session_perf_summary['rolling_5_session_avg_ret_5b_ticks'].notna().sum()):,}",
        f"Weekly-breakout divergence observations:    {int(div_sample['matches_weekly_breakout'].sum()):,}",
        "",
        "Baselines",
        "---------",
        render_baseline_line("Bar sample core 5b", bar_sample.loc[bar_sample['has_core_60m_15m_gate']].copy(), 5),
        render_baseline_line("Bar sample core 30b", bar_sample.loc[bar_sample['has_core_60m_15m_gate']].copy(), 30),
        render_baseline_line("Divergence sample core 5b", div_sample.loc[div_sample['has_core_60m_15m_gate']].copy(), 5),
        render_baseline_line("Divergence sample core 30b", div_sample.loc[div_sample['has_core_60m_15m_gate']].copy(), 30),
        "",
        "Summary ranking by composite OOS WR",
        "-----------------------------------",
    ]
    lines.extend(render_summary_table(results))
    lines.append("")

    for result in results:
        lines.extend(render_filter_report(result))

    report = "\n".join(lines).rstrip() + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
