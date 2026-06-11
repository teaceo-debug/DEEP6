#!/usr/bin/env python3
from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round35_session_structure_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 30)
TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
INITIAL_BALANCE_BARS = 60
AVG_SESSION_RANGE_LOOKBACK = 20
RANGE_LOOKBACK_BARS = 10
RECENT_EXTENSION_BARS = 5
ROLLING_VOLUME_LOOKBACK = 20
DELTA_QUANTILE_MIN_PERIODS = 10
VALUE_AREA_PCT = 0.70
POST_IB_FIRST_HOUR_END = INITIAL_BALANCE_BARS + 60

FilterSpec = tuple[
    str,
    str,
    str,
    Callable[[pd.DataFrame], pd.Series],
    Callable[[pd.DataFrame], int | pd.Series],
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


def price_to_tick(price: float) -> int:
    return int(round(float(price) / TICK_SIZE))


def tick_to_price(tick: int) -> float:
    return tick * TICK_SIZE


def compute_value_area(profile: dict[int, float], poc_tick: int, pct: float = VALUE_AREA_PCT) -> tuple[float, float]:
    total_volume = sum(profile.values())
    target = total_volume * pct
    ordered = sorted(profile)
    center_idx = ordered.index(poc_tick)
    included = {poc_tick}
    running = profile[poc_tick]
    left = center_idx - 1
    right = center_idx + 1

    while running < target and (left >= 0 or right < len(ordered)):
        left_tick = ordered[left] if left >= 0 else None
        right_tick = ordered[right] if right < len(ordered) else None
        left_volume = profile[left_tick] if left_tick is not None else -1.0
        right_volume = profile[right_tick] if right_tick is not None else -1.0

        if right_volume > left_volume:
            included.add(right_tick)
            running += right_volume
            right += 1
        else:
            included.add(left_tick)
            running += left_volume
            left -= 1

    return tick_to_price(min(included)), tick_to_price(max(included))


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
    return observations


def prepare_rth_bars(bars_1m: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    bars = bars_1m.copy()
    minute_of_day = bars["ts_event"].dt.hour * 60 + bars["ts_event"].dt.minute
    bars = bars.loc[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    bars["session_date"] = bars["ts_event"].dt.strftime("%Y-%m-%d")
    bars["session_bar_count"] = bars.groupby("session_date", sort=False)["ts_event"].transform("size")
    bars = bars.loc[bars["session_bar_count"] >= INITIAL_BALANCE_BARS].copy()
    bars["bar_index"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")

    delta_proxy = observations[["bar_ts", "bar_delta"]].drop_duplicates(subset=["bar_ts"], keep="first").rename(
        columns={"bar_ts": "ts_event", "bar_delta": "delta_proxy"}
    )
    bars = bars.merge(delta_proxy, on="ts_event", how="left", validate="one_to_one")
    bars["has_observed_delta"] = bars["delta_proxy"].notna()
    bars["delta_proxy"] = pd.to_numeric(bars["delta_proxy"], errors="coerce").fillna(0.0)
    return bars.reset_index(drop=True)


def build_session_summary(rth_bars: pd.DataFrame) -> pd.DataFrame:
    sessions = (
        rth_bars.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("ts_event", "first"),
            session_open=("open", "first"),
            session_high=("high", "max"),
            session_low=("low", "min"),
            session_close=("close", "last"),
            session_volume=("volume", "sum"),
            session_bar_count=("ts_event", "size"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    sessions["session_range"] = sessions["session_high"] - sessions["session_low"]
    sessions["avg_prior_20_session_range"] = (
        sessions["session_range"]
        .shift(1)
        .rolling(AVG_SESSION_RANGE_LOOKBACK, min_periods=AVG_SESSION_RANGE_LOOKBACK)
        .mean()
    )

    initial_balance = (
        rth_bars.loc[rth_bars["bar_index"] < INITIAL_BALANCE_BARS]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            ib_high=("high", "max"),
            ib_low=("low", "min"),
        )
    )
    initial_balance["ib_range"] = initial_balance["ib_high"] - initial_balance["ib_low"]
    return sessions.merge(initial_balance, on="session_date", how="left", validate="one_to_one")


def build_timeframe_context(rth_bars: pd.DataFrame) -> dict[int, pd.DataFrame]:
    context: dict[int, pd.DataFrame] = {}

    for tf in TIMEFRAMES:
        bucket_col = f"bucket_{tf}m"
        temp = rth_bars[["session_date", "ts_event", "bar_index", "open", "high", "low", "close", "volume"]].copy()
        temp[bucket_col] = temp["bar_index"] // tf
        tf_bars = (
            temp.groupby(["session_date", bucket_col], as_index=False, sort=False)
            .agg(
                ts_event=("ts_event", "first"),
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .sort_values(["session_date", bucket_col], kind="stable")
            .reset_index(drop=True)
        )
        tf_bars["range"] = tf_bars["high"] - tf_bars["low"]
        tf_bars["trend_sign"] = np.sign(tf_bars["close"] - tf_bars["open"]).astype(int)
        context[tf] = tf_bars

    return context


def attach_timeframe_context(rth_bars: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    out = rth_bars.copy()

    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        out[bucket_col] = out["bar_index"] // tf
        renamed = ctx.rename(
            columns={
                "ts_event": f"ts_{tf}m",
                "open": f"open_{tf}m",
                "high": f"high_{tf}m",
                "low": f"low_{tf}m",
                "close": f"close_{tf}m",
                "volume": f"volume_{tf}m",
                "range": f"range_{tf}m",
                "trend_sign": f"trend_sign_{tf}m",
            }
        )
        out = out.merge(renamed, on=["session_date", bucket_col], how="left", validate="many_to_one")

    return out.reset_index(drop=True)


def build_developing_profile_context(rth_bars: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for session_date, session in rth_bars.groupby("session_date", sort=False):
        profile: dict[int, float] = defaultdict(float)
        total_volume = 0.0
        vwap_num = 0.0

        for row in session.itertuples(index=False):
            volume = float(row.volume)
            if volume > 0:
                total_volume += volume
                typical_price = (float(row.high) + float(row.low) + float(row.close)) / 3.0
                vwap_num += typical_price * volume

                lo_tick = price_to_tick(float(row.low))
                hi_tick = price_to_tick(float(row.high))
                tick_count = max(1, hi_tick - lo_tick + 1)
                volume_per_tick = volume / tick_count
                for tick in range(lo_tick, hi_tick + 1):
                    profile[tick] += volume_per_tick

            session_poc = np.nan
            session_val = np.nan
            session_vah = np.nan
            session_vwap = np.nan
            in_value_area = False

            if profile and total_volume > 0:
                session_vwap = vwap_num / total_volume
                max_volume = max(profile.values())
                poc_candidates = [tick for tick, tick_volume in profile.items() if tick_volume == max_volume]
                poc_tick = min(poc_candidates, key=lambda tick: (abs(tick_to_price(tick) - session_vwap), tick))
                session_val, session_vah = compute_value_area(profile, poc_tick)
                session_poc = tick_to_price(poc_tick)
                in_value_area = bool(session_val <= float(row.close) <= session_vah)

            rows.append(
                {
                    "ts_event": row.ts_event,
                    "session_date": session_date,
                    "session_poc": session_poc,
                    "session_val": session_val,
                    "session_vah": session_vah,
                    "session_vwap": session_vwap,
                    "in_value_area": in_value_area,
                }
            )

    profile_context = pd.DataFrame(rows).sort_values(["session_date", "ts_event"], kind="stable").reset_index(drop=True)
    by_session = profile_context.groupby("session_date", sort=False)
    profile_context["prior_session_poc"] = by_session["session_poc"].shift(1)
    profile_context["poc_migration_sign"] = np.sign(
        (profile_context["session_poc"] - profile_context["prior_session_poc"]).fillna(0.0)
    ).astype(int)
    profile_context["poc_migrating_up"] = profile_context["prior_session_poc"].notna() & profile_context["poc_migration_sign"].gt(0)
    profile_context["poc_migrating_down"] = profile_context["prior_session_poc"].notna() & profile_context["poc_migration_sign"].lt(0)
    profile_context["poc_migrating_flat"] = profile_context["prior_session_poc"].notna() & profile_context["poc_migration_sign"].eq(0)
    return profile_context


def compute_intraday_state(rth_bars: pd.DataFrame, sessions: pd.DataFrame, profile_context: pd.DataFrame) -> pd.DataFrame:
    out = rth_bars.merge(sessions, on="session_date", how="left", validate="many_to_one")
    out = out.merge(profile_context, on=["session_date", "ts_event"], how="left", validate="one_to_one")
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["high"] - out["low"]
    out["running_high"] = by_session["high"].cummax()
    out["running_low"] = by_session["low"].cummin()
    out["session_range_so_far"] = out["running_high"] - out["running_low"]
    out["session_range_10b_ago"] = by_session["session_range_so_far"].shift(RANGE_LOOKBACK_BARS)
    out["session_midpoint"] = (out["running_high"] + out["running_low"]) / 2.0
    out["prior_session_midpoint"] = by_session["session_midpoint"].shift(1)
    out["prev_close"] = by_session["close"].shift(1)
    out["bars_seen"] = by_session.cumcount() + 1

    out["after_ib"] = out["bar_index"] >= INITIAL_BALANCE_BARS
    out["is_first_hour"] = out["bar_index"].lt(INITIAL_BALANCE_BARS)
    out["is_first_hour_post_ib"] = out["bar_index"].ge(INITIAL_BALANCE_BARS) & out["bar_index"].lt(POST_IB_FIRST_HOUR_END)

    out["close_above_ib"] = out["after_ib"] & out["close"].gt(out["ib_high"])
    out["close_below_ib"] = out["after_ib"] & out["close"].lt(out["ib_low"])
    out["inside_ib"] = out["after_ib"] & out["close"].le(out["ib_high"]) & out["close"].ge(out["ib_low"])

    out["ib_extension_up_now"] = out["after_ib"] & out["high"].gt(out["ib_high"])
    out["ib_extension_down_now"] = out["after_ib"] & out["low"].lt(out["ib_low"])
    out["has_ib_extension_up"] = by_session["ib_extension_up_now"].cummax()
    out["has_ib_extension_down"] = by_session["ib_extension_down_now"].cummax()
    out["has_any_ib_extension"] = out["has_ib_extension_up"] | out["has_ib_extension_down"]

    out["first_ib_extension_up_bar"] = by_session["bar_index"].transform(
        lambda s: s.where(out.loc[s.index, "ib_extension_up_now"]).min()
    )
    out["first_ib_extension_down_bar"] = by_session["bar_index"].transform(
        lambda s: s.where(out.loc[s.index, "ib_extension_down_now"]).min()
    )
    out["bars_since_first_ib_extension_up"] = out["bar_index"] - out["first_ib_extension_up_bar"]
    out["bars_since_first_ib_extension_down"] = out["bar_index"] - out["first_ib_extension_down_bar"]
    out["ib_extension_up_last_5"] = out["first_ib_extension_up_bar"].notna() & out["bars_since_first_ib_extension_up"].between(
        0, RECENT_EXTENSION_BARS - 1
    )
    out["ib_extension_down_last_5"] = out["first_ib_extension_down_bar"].notna() & out[
        "bars_since_first_ib_extension_down"
    ].between(0, RECENT_EXTENSION_BARS - 1)
    out["ib_extension_last_5"] = out["ib_extension_up_last_5"] | out["ib_extension_down_last_5"]
    out["no_ib_extension_yet"] = out["after_ib"] & (~out["has_any_ib_extension"])

    out["range_lt_half_avg"] = out["avg_prior_20_session_range"].notna() & out["session_range_so_far"].lt(
        0.50 * out["avg_prior_20_session_range"]
    )
    out["range_gt_150_avg"] = out["avg_prior_20_session_range"].notna() & out["session_range_so_far"].gt(
        1.50 * out["avg_prior_20_session_range"]
    )
    out["range_expanding_10b"] = out["session_range_10b_ago"].notna() & out["session_range_so_far"].gt(out["session_range_10b_ago"])
    out["range_stable_10b"] = out["session_range_10b_ago"].gt(0) & (
        (out["session_range_so_far"] - out["session_range_10b_ago"]).abs() <= 0.10 * out["session_range_10b_ago"]
    )
    out["in_middle_third_of_range"] = out["session_range_so_far"].gt(0) & out["close"].between(
        out["running_low"] + out["session_range_so_far"] / 3.0,
        out["running_low"] + 2.0 * out["session_range_so_far"] / 3.0,
        inclusive="both",
    )

    out["close_in_upper_half"] = out["close"].ge(out["session_midpoint"])
    out["close_in_lower_half"] = out["close"].lt(out["session_midpoint"])
    out["upper_half_count"] = by_session["close_in_upper_half"].cumsum()
    out["lower_half_count"] = by_session["close_in_lower_half"].cumsum()
    out["upper_half_share"] = out["upper_half_count"] / out["bars_seen"]
    out["lower_half_share"] = out["lower_half_count"] / out["bars_seen"]
    out["crossed_upper_to_lower_half"] = (
        out["prev_close"].notna()
        & out["prior_session_midpoint"].notna()
        & out["prev_close"].ge(out["prior_session_midpoint"])
        & out["close"].lt(out["session_midpoint"])
    )

    out["session_cum_delta"] = by_session["delta_proxy"].cumsum()
    out["abs_session_cum_delta"] = out["session_cum_delta"].abs()
    out["session_abs_cum_delta_q25"] = by_session["session_cum_delta"].transform(
        lambda s: s.abs().expanding(min_periods=DELTA_QUANTILE_MIN_PERIODS).quantile(0.25)
    )
    out["session_abs_cum_delta_q75"] = by_session["session_cum_delta"].transform(
        lambda s: s.abs().expanding(min_periods=DELTA_QUANTILE_MIN_PERIODS).quantile(0.75)
    )
    out["session_delta_near_zero"] = out["session_abs_cum_delta_q25"].notna() & out["abs_session_cum_delta"].lt(
        out["session_abs_cum_delta_q25"]
    )
    out["session_delta_extreme"] = out["session_abs_cum_delta_q75"].notna() & out["abs_session_cum_delta"].gt(
        out["session_abs_cum_delta_q75"]
    )

    out["rolling_20_ema_vol"] = by_session["volume"].transform(
        lambda s: s.ewm(span=ROLLING_VOLUME_LOOKBACK, adjust=False, min_periods=ROLLING_VOLUME_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["volume"].gt(3.0 * out["rolling_20_ema_vol"])

    bool_cols = [
        "has_observed_delta",
        "in_value_area",
        "poc_migrating_up",
        "poc_migrating_down",
        "poc_migrating_flat",
        "after_ib",
        "is_first_hour",
        "is_first_hour_post_ib",
        "close_above_ib",
        "close_below_ib",
        "inside_ib",
        "ib_extension_up_now",
        "ib_extension_down_now",
        "has_ib_extension_up",
        "has_ib_extension_down",
        "has_any_ib_extension",
        "ib_extension_up_last_5",
        "ib_extension_down_last_5",
        "ib_extension_last_5",
        "no_ib_extension_yet",
        "range_lt_half_avg",
        "range_gt_150_avg",
        "range_expanding_10b",
        "range_stable_10b",
        "in_middle_third_of_range",
        "close_in_upper_half",
        "close_in_lower_half",
        "crossed_upper_to_lower_half",
        "session_delta_near_zero",
        "session_delta_extreme",
        "is_volume_spike_3x",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)

    return out.reset_index(drop=True)


def merge_rth_context(observations: pd.DataFrame, rth_context: pd.DataFrame) -> pd.DataFrame:
    context_cols = [
        "ts_event",
        "session_date",
        "bar_index",
        "has_observed_delta",
        "delta_proxy",
        "ib_high",
        "ib_low",
        "ib_range",
        "avg_prior_20_session_range",
        "open_15m",
        "high_15m",
        "low_15m",
        "close_15m",
        "volume_15m",
        "range_15m",
        "trend_sign_15m",
        "open_60m",
        "high_60m",
        "low_60m",
        "close_60m",
        "volume_60m",
        "range_60m",
        "trend_sign_60m",
        "session_poc",
        "session_val",
        "session_vah",
        "session_vwap",
        "in_value_area",
        "poc_migration_sign",
        "poc_migrating_up",
        "poc_migrating_down",
        "poc_migrating_flat",
        "after_ib",
        "is_first_hour",
        "is_first_hour_post_ib",
        "close_above_ib",
        "close_below_ib",
        "inside_ib",
        "has_ib_extension_up",
        "has_ib_extension_down",
        "has_any_ib_extension",
        "ib_extension_last_5",
        "no_ib_extension_yet",
        "session_range_so_far",
        "session_range_10b_ago",
        "range_lt_half_avg",
        "range_gt_150_avg",
        "range_expanding_10b",
        "range_stable_10b",
        "in_middle_third_of_range",
        "session_midpoint",
        "upper_half_share",
        "lower_half_share",
        "crossed_upper_to_lower_half",
        "session_cum_delta",
        "abs_session_cum_delta",
        "session_abs_cum_delta_q25",
        "session_abs_cum_delta_q75",
        "session_delta_near_zero",
        "session_delta_extreme",
        "rolling_20_ema_vol",
        "is_volume_spike_3x",
    ]
    renamed = rth_context[context_cols].rename(
        columns={
            "ts_event": "bar_ts",
            "session_date": "rth_session_date",
            "bar_index": "rth_bar_index",
        }
    )
    out = observations.merge(renamed, on="bar_ts", how="left", validate="many_to_one")
    out = out.loc[out["rth_session_date"].notna()].copy()

    numeric_cols = [
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "delta_proxy",
        "ib_high",
        "ib_low",
        "ib_range",
        "avg_prior_20_session_range",
        "open_15m",
        "high_15m",
        "low_15m",
        "close_15m",
        "volume_15m",
        "range_15m",
        "open_60m",
        "high_60m",
        "low_60m",
        "close_60m",
        "volume_60m",
        "range_60m",
        "session_poc",
        "session_val",
        "session_vah",
        "session_vwap",
        "poc_migration_sign",
        "session_range_so_far",
        "session_range_10b_ago",
        "session_midpoint",
        "upper_half_share",
        "lower_half_share",
        "session_cum_delta",
        "abs_session_cum_delta",
        "session_abs_cum_delta_q25",
        "session_abs_cum_delta_q75",
        "rolling_20_ema_vol",
    ]
    for col in numeric_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    trend_cols = ["direction_sign", "trend_sign_15m", "trend_sign_60m"]
    for col in trend_cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0).astype(int)

    bool_cols = [
        "has_observed_delta",
        "in_value_area",
        "poc_migrating_up",
        "poc_migrating_down",
        "poc_migrating_flat",
        "after_ib",
        "is_first_hour",
        "is_first_hour_post_ib",
        "close_above_ib",
        "close_below_ib",
        "inside_ib",
        "has_ib_extension_up",
        "has_ib_extension_down",
        "has_any_ib_extension",
        "ib_extension_last_5",
        "no_ib_extension_yet",
        "range_lt_half_avg",
        "range_gt_150_avg",
        "range_expanding_10b",
        "range_stable_10b",
        "in_middle_third_of_range",
        "crossed_upper_to_lower_half",
        "session_delta_near_zero",
        "session_delta_extreme",
        "is_volume_spike_3x",
    ]
    for col in bool_cols:
        if col in out.columns:
            out[col] = out[col].fillna(False).astype(bool)

    return out.reset_index(drop=True)


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return np.sign(series).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    range_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / range_60m, index=df.index)


def is_60m_extreme_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    return ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    return is_60m_extreme_for(df, direction) & is_15m_trend_aligned_for(df, direction)


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_trade_sample(source_df: pd.DataFrame, direction: int | pd.Series) -> pd.DataFrame:
    sample = source_df.copy()
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    for window in FORWARD_WINDOWS:
        sample[f"ret_{window}b_ticks"] = sample["trade_sign"] * sample[f"move_{window}b_ticks"]
    return sample.reset_index(drop=True)


def summarize_filter(code: str, group: str, label: str, sample: pd.DataFrame) -> dict[str, object]:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    clean = sample.dropna(subset=required_cols).copy()
    n = int(len(clean))
    win_rates: dict[int, float] = {}

    for window in FORWARD_WINDOWS:
        returns = clean[f"ret_{window}b_ticks"]
        win_rates[window] = float((returns > 0).mean()) if n else np.nan

    returns_5b = clean["ret_5b_ticks"]
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


def build_filter_specs() -> list[FilterSpec]:
    return [
        (
            "01",
            "A",
            "Price above IB high + bearish signal + 60m + 15m",
            lambda df: df["close_above_ib"] & df["has_ib_extension_up"] & df["direction_sign"].lt(0) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "02",
            "A",
            "Price below IB low + bullish signal + 60m + 15m",
            lambda df: df["close_below_ib"]
            & df["has_ib_extension_down"]
            & df["direction_sign"].gt(0)
            & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "03",
            "A",
            "Price within IB range + 60m + 15m",
            lambda df: df["inside_ib"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "04",
            "A",
            "IB extension happened in last 5 bars + 60m + 15m",
            lambda df: df["ib_extension_last_5"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "05",
            "A",
            "No IB extension yet today + 60m + 15m",
            lambda df: df["no_ib_extension_yet"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "06",
            "B",
            "Developing range < 50% avg session range + 60m + 15m",
            lambda df: df["range_lt_half_avg"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "07",
            "B",
            "Developing range > 150% avg session range + 60m + 15m",
            lambda df: df["range_gt_150_avg"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "08",
            "B",
            "Developing range expanding vs 10 bars ago + 60m + 15m",
            lambda df: df["range_expanding_10b"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "09",
            "B",
            "Developing range stable vs 10 bars ago + 60m + 15m",
            lambda df: df["range_stable_10b"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "10",
            "B",
            "Price in middle third of developing range + 60m + 15m",
            lambda df: df["in_middle_third_of_range"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "11",
            "C",
            "Session cumulative delta positive + bullish signal + 60m + 15m",
            lambda df: df["session_cum_delta"].gt(0) & df["direction_sign"].gt(0) & has_core_60m_15m_gate_for(df, 1),
            lambda df: 1,
        ),
        (
            "12",
            "C",
            "Session cumulative delta negative + bearish signal + 60m + 15m",
            lambda df: df["session_cum_delta"].lt(0) & df["direction_sign"].lt(0) & has_core_60m_15m_gate_for(df, -1),
            lambda df: -1,
        ),
        (
            "13",
            "C",
            "Session delta opposing signal direction + 60m + 15m",
            lambda df: df["session_cum_delta"].ne(0)
            & df["direction_sign"].ne(0)
            & df["session_cum_delta"].mul(df["direction_sign"]).lt(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "14",
            "C",
            "Session delta near zero (|cum_delta| < session q25) + 60m + 15m",
            lambda df: df["session_delta_near_zero"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "15",
            "C",
            "Session delta extreme (|cum_delta| > session q75) + 60m + 15m",
            lambda df: df["session_delta_extreme"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "16",
            "D",
            "Price spent >70% of bars in upper half of range + 60m + 15m",
            lambda df: df["upper_half_share"].gt(0.70) & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "17",
            "D",
            "Price spent >70% of bars in lower half of range + 60m + 15m",
            lambda df: df["lower_half_share"].gt(0.70) & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "18",
            "D",
            "Price recently crossed from upper to lower half + 60m + 15m",
            lambda df: df["crossed_upper_to_lower_half"] & has_core_60m_15m_gate_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "19",
            "E",
            "Within IB + session delta opposing + 60m + 15m + NOT killers",
            lambda df: df["inside_ib"]
            & df["session_cum_delta"].ne(0)
            & df["direction_sign"].ne(0)
            & df["session_cum_delta"].mul(df["direction_sign"]).lt(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"]),
            lambda df: df["direction_sign"],
        ),
        (
            "20",
            "E",
            "IB extension + developing range >150% avg + 60m + 15m + NOT killers + first_hour",
            lambda df: df["has_any_ib_extension"]
            & df["range_gt_150_avg"]
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour_post_ib"],
            lambda df: df["direction_sign"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for code, group, label, predicate, direction_fn in build_filter_specs():
        mask = predicate(df).fillna(False)
        filtered = df.loc[mask].copy()
        direction = direction_fn(df)
        if isinstance(direction, pd.Series):
            direction = direction.loc[mask]
        sample = build_trade_sample(filtered, direction)
        results.append(summarize_filter(code, group, label, sample))

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
    rth_bars = prepare_rth_bars(bars_1m, observations)
    sessions = build_session_summary(rth_bars)
    timeframe_context = build_timeframe_context(rth_bars)
    rth_bars = attach_timeframe_context(rth_bars, timeframe_context)
    profile_context = build_developing_profile_context(rth_bars)
    rth_bars = compute_intraday_state(rth_bars, sessions, profile_context)
    observations = merge_rth_context(observations, rth_bars)

    observations["has_core_60m_15m_gate"] = has_core_60m_15m_gate_for(observations, observations["direction_sign"])
    observations["passes_not_all_killers"] = passes_not_all_killers_for(observations, observations["direction_sign"])
    observations["has_core_60m_15m_gate"] = observations["has_core_60m_15m_gate"].fillna(False).astype(bool)
    observations["passes_not_all_killers"] = observations["passes_not_all_killers"].fillna(False).astype(bool)

    all_signal_bars = build_trade_sample(observations, observations["direction_sign"])
    core_signal_bars = all_signal_bars.loc[all_signal_bars["has_core_60m_15m_gate"]].copy()
    core_not_killers = core_signal_bars.loc[core_signal_bars["passes_not_all_killers"]].copy()
    core_not_killers_post_ib_first_hour = core_signal_bars.loc[
        core_signal_bars["passes_not_all_killers"] & core_signal_bars["is_first_hour_post_ib"]
    ].copy()

    baseline_all = summarize_filter("00", "BASE", "All non-zero-delta signal bars", all_signal_bars)
    baseline_core = summarize_filter("00A", "BASE", "60m + 15m core sample", core_signal_bars)
    baseline_core_not_killers = summarize_filter(
        "00B",
        "BASE",
        "60m + 15m + NOT killers",
        core_not_killers,
    )
    baseline_core_not_killers_post_ib_first_hour = summarize_filter(
        "00C",
        "BASE",
        "60m + 15m + NOT killers + first hour after IB",
        core_not_killers_post_ib_first_hour,
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round35 session structure analysis",
        "=======================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Bullish / bearish trade direction = sign(bar_delta) unless the filter explicitly fixes the direction.",
        "60m + 15m = trade-direction 60m extreme (bull anchor in bottom 20%, bear anchor in top 20%) plus 15m open-close trend alignment.",
        "IB = first 60 RTH one-minute bars (09:30-10:29 ET). IB extension = first post-10:30 break of IB high/low using bar high/low.",
        "Developing range = running session high - running session low. Average session range = mean of the prior 20 full RTH session ranges.",
        "Range stable vs 10 bars ago = absolute change <= 10% of the developing range from 10 bars earlier.",
        "Session delta features use the bar_delta column from signal_events.csv merged onto the full RTH 1m timeline; bars without a signal row are zero-filled because nq_1yr_1m.csv has OHLCV only.",
        "Developing value area / POC use a running session volume profile that evenly distributes each 1m bar's volume across its high-low ticks.",
        "POC migration is reported versus the immediately prior 1m bar. In-value-area uses the developing session VAL/VAH at that bar.",
        "Filter 20 interprets first_hour as the first hour after the IB is complete (10:30-11:29 ET); otherwise the IB-extension condition would be impossible.",
        "PF, Avg Ticks, and Wilson CI are reported on the 5-bar horizon; WR columns show 5b / 10b / 30b. Rows are sorted by 30b WR.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "",
        f"Raw event rows loaded:                        {len(events):,}",
        f"Grouped signal bars:                          {len(observations):,}",
        f"Tradable non-zero-delta bars:                 {len(all_signal_bars):,}",
        f"RTH 1m bars used:                             {len(rth_bars):,}",
        f"RTH bars with observed delta proxy:           {int(rth_bars['has_observed_delta'].sum()):,}",
        f"RTH sessions built:                           {len(sessions):,}",
        f"Sessions with prior 20-session avg range:     {int(sessions['avg_prior_20_session_range'].notna().sum()):,}",
        f"15m bars built:                               {len(timeframe_context[15]):,}",
        f"60m bars built:                               {len(timeframe_context[60]):,}",
        f"60m + 15m core bars:                          {len(core_signal_bars):,}",
        f"60m + 15m + NOT killers bars:                 {len(core_not_killers):,}",
        f"60m + 15m + NOT killers + 1st hr after IB:    {len(core_not_killers_post_ib_first_hour):,}",
        f"Signal bars inside developing value area:     {int(all_signal_bars['in_value_area'].sum()):,}",
        f"Signal bars with POC migrating up:            {int(all_signal_bars['poc_migrating_up'].sum()):,}",
        f"Signal bars with POC migrating down:          {int(all_signal_bars['poc_migrating_down'].sum()):,}",
        f"Signal bars with POC migrating flat:          {int(all_signal_bars['poc_migrating_flat'].sum()):,}",
        f"Signal bars above IB after 10:30:             {int(all_signal_bars['close_above_ib'].sum()):,}",
        f"Signal bars below IB after 10:30:             {int(all_signal_bars['close_below_ib'].sum()):,}",
        f"Signal bars within IB after 10:30:            {int(all_signal_bars['inside_ib'].sum()):,}",
        f"Signal bars with fresh IB extension (<=5b):   {int(all_signal_bars['ib_extension_last_5'].sum()):,}",
        f"Signal bars with no IB extension yet:         {int(all_signal_bars['no_ib_extension_yet'].sum()):,}",
        f"Signal bars in tight developing range days:   {int(all_signal_bars['range_lt_half_avg'].sum()):,}",
        f"Signal bars in wide developing range days:    {int(all_signal_bars['range_gt_150_avg'].sum()):,}",
        f"Signal bars with near-zero session delta:     {int(all_signal_bars['session_delta_near_zero'].sum()):,}",
        f"Signal bars with extreme session delta:       {int(all_signal_bars['session_delta_extreme'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All non-zero-delta bars:                {render_summary_line(baseline_all)}",
        f"60m + 15m core:                         {render_summary_line(baseline_core)}",
        f"60m + 15m + NOT killers:                {render_summary_line(baseline_core_not_killers)}",
        f"60m + 15m + NOT killers + 1st hr postIB:{render_summary_line(baseline_core_not_killers_post_ib_first_hour)}",
        "",
        "20 requested session-structure filters sorted by 30b WR",
        "-----------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
