#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "round6_gap_opening_range_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
OPENING_RANGE_BARS = 15
INITIAL_BALANCE_BARS = 60
OPENING_DRIVE_BARS = 5
REVERSAL_START_BAR = 30  # 10:00 ET


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
    observations = observations[observations["direction_sign"] != 0].copy()
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["ret_5b_ticks"] = observations["direction_sign"] * (
        (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    )
    return observations.reset_index(drop=True)


def prepare_rth_bars(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    minute_of_day = out["ts_event"].dt.hour * 60 + out["ts_event"].dt.minute
    out = out[(minute_of_day >= RTH_START_MINUTE) & (minute_of_day < RTH_END_MINUTE)].copy()
    out["session_date"] = out["ts_event"].dt.strftime("%Y-%m-%d")
    out["session_bar_count"] = out.groupby("session_date", sort=False)["ts_event"].transform("size")
    out = out[out["session_bar_count"] >= INITIAL_BALANCE_BARS].copy()
    out["bar_index"] = out.groupby("session_date", sort=False).cumcount()
    out["bar_range"] = out["high"] - out["low"]
    out["body"] = (out["close"] - out["open"]).abs()
    out["price_sign"] = np.sign(out["close"] - out["open"]).astype(int)
    return out.reset_index(drop=True)


def build_timeframe_context(bars_1m: pd.DataFrame) -> dict[int, pd.DataFrame]:
    context: dict[int, pd.DataFrame] = {}

    for tf in TIMEFRAMES:
        bucket_col = f"bucket_{tf}m"
        temp = bars_1m[["session_date", "ts_event", "bar_index", "open", "high", "low", "close", "volume"]].copy()
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


def attach_timeframe_context(bars: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    out = bars.copy()

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

    return out


def build_session_summaries(bars: pd.DataFrame) -> pd.DataFrame:
    sessions = (
        bars.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_open=("open", "first"),
            session_high=("high", "max"),
            session_low=("low", "min"),
            session_close=("close", "last"),
            session_bar_count=("ts_event", "size"),
        )
        .reset_index(drop=True)
    )
    sessions["session_range"] = sessions["session_high"] - sessions["session_low"]
    sessions["prior_session_close"] = sessions["session_close"].shift(1)
    sessions["prior_session_high"] = sessions["session_high"].shift(1)
    sessions["prior_session_low"] = sessions["session_low"].shift(1)
    sessions["gap"] = sessions["session_open"] - sessions["prior_session_close"]
    sessions["gap_sign"] = np.sign(sessions["gap"].fillna(0.0)).astype(int)

    opening_range = (
        bars[bars["bar_index"] < OPENING_RANGE_BARS]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            or_open=("open", "first"),
            or_high=("high", "max"),
            or_low=("low", "min"),
            or_close=("close", "last"),
        )
    )
    opening_range["or_range"] = opening_range["or_high"] - opening_range["or_low"]

    initial_balance = (
        bars[bars["bar_index"] < INITIAL_BALANCE_BARS]
        .groupby("session_date", as_index=False, sort=False)
        .agg(
            ib_high=("high", "max"),
            ib_low=("low", "min"),
        )
    )
    initial_balance["ib_range"] = initial_balance["ib_high"] - initial_balance["ib_low"]

    drive_records: list[dict[str, object]] = []
    for session_date, group in bars.groupby("session_date", sort=False):
        first_five = group.head(OPENING_DRIVE_BARS).copy()
        signs = first_five["price_sign"].astype(int).tolist()

        opening_drive_sign = 0
        if len(signs) == OPENING_DRIVE_BARS and all(sign == signs[0] and sign != 0 for sign in signs):
            opening_drive_sign = int(signs[0])

        is_choppy_open = len(signs) == OPENING_DRIVE_BARS and all(
            prev != 0 and curr != 0 and curr == -prev for prev, curr in zip(signs, signs[1:])
        )

        drive_records.append(
            {
                "session_date": session_date,
                "opening_drive_sign": opening_drive_sign,
                "is_choppy_open": bool(is_choppy_open),
            }
        )

    drive = pd.DataFrame(drive_records)

    sessions = sessions.merge(opening_range, on="session_date", how="left", validate="one_to_one")
    sessions = sessions.merge(initial_balance, on="session_date", how="left", validate="one_to_one")
    sessions = sessions.merge(drive, on="session_date", how="left", validate="one_to_one")

    or_q25 = sessions["or_range"].dropna().quantile(0.25)
    or_q75 = sessions["or_range"].dropna().quantile(0.75)
    day_q25 = sessions["session_range"].dropna().quantile(0.25)

    sessions["is_narrow_or"] = sessions["or_range"] < or_q25
    sessions["is_wide_or"] = sessions["or_range"] > or_q75
    sessions["is_narrow_day"] = sessions["session_range"] < day_q25
    sessions["prior_is_narrow_day"] = sessions["is_narrow_day"].shift(1).fillna(False).astype(bool)
    sessions["prev2_is_narrow_day"] = sessions["is_narrow_day"].shift(2).fillna(False).astype(bool)
    sessions["two_prior_narrow_days"] = sessions["prior_is_narrow_day"] & sessions["prev2_is_narrow_day"]
    sessions["is_inside_day_open_range"] = (
        sessions["prior_session_high"].notna()
        & sessions["prior_session_low"].notna()
        & sessions["or_high"].le(sessions["prior_session_high"])
        & sessions["or_low"].ge(sessions["prior_session_low"])
    )
    sessions["gap_not_filled_by_1030"] = (
        ((sessions["gap_sign"] > 0) & sessions["ib_low"].gt(sessions["prior_session_close"]))
        | ((sessions["gap_sign"] < 0) & sessions["ib_high"].lt(sessions["prior_session_close"]))
    )

    return sessions


def compute_intraday_state(bars: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    out = bars.merge(sessions, on="session_date", how="left", validate="many_to_one")
    by_session = out.groupby("session_date", sort=False)

    out["cum_high"] = by_session["high"].cummax()
    out["cum_low"] = by_session["low"].cummin()
    out["price_is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["after_1000"] = out["bar_index"] >= REVERSAL_START_BAR
    out["after_1030"] = out["bar_index"] >= INITIAL_BALANCE_BARS

    out["close_above_or"] = out["close"] > out["or_high"]
    out["close_below_or"] = out["close"] < out["or_low"]
    out["inside_or"] = out["close"].le(out["or_high"]) & out["close"].ge(out["or_low"])

    out["broke_above_or_now"] = out["bar_index"].ge(OPENING_RANGE_BARS) & out["high"].gt(out["or_high"])
    out["broke_below_or_now"] = out["bar_index"].ge(OPENING_RANGE_BARS) & out["low"].lt(out["or_low"])
    out["has_broken_above_or"] = by_session["broke_above_or_now"].cummax()
    out["has_broken_below_or"] = by_session["broke_below_or_now"].cummax()
    out["has_failed_breakout"] = out["has_broken_above_or"] & out["inside_or"] & out["bar_index"].ge(OPENING_RANGE_BARS)
    out["has_failed_breakdown"] = out["has_broken_below_or"] & out["inside_or"] & out["bar_index"].ge(OPENING_RANGE_BARS)

    out["gap_up_session"] = out["gap"] > 0
    out["gap_down_session"] = out["gap"] < 0
    out["gap_filled_up"] = out["gap_up_session"] & out["cum_low"].le(out["prior_session_close"])
    out["gap_filled_down"] = out["gap_down_session"] & out["cum_high"].ge(out["prior_session_close"])
    out["gap_filled"] = out["gap_filled_up"] | out["gap_filled_down"]

    out["is_at_ib_high"] = out["after_1030"] & out["high"].ge(out["ib_high"] - TICK_SIZE)
    out["is_at_ib_low"] = out["after_1030"] & out["low"].le(out["ib_low"] + TICK_SIZE)

    rng_60m = out["range_60m"].replace(0, np.nan)
    out["pos_60m_low"] = (out["low"] - out["low_60m"]) / rng_60m
    out["pos_60m_high"] = (out["high"] - out["low_60m"]) / rng_60m
    out["is_60m_bottom_extreme"] = out["pos_60m_low"].le(0.20)
    out["is_60m_top_extreme"] = out["pos_60m_high"].ge(0.80)

    bool_cols = [
        "price_is_doji",
        "after_1000",
        "after_1030",
        "close_above_or",
        "close_below_or",
        "inside_or",
        "broke_above_or_now",
        "broke_below_or_now",
        "has_broken_above_or",
        "has_broken_below_or",
        "has_failed_breakout",
        "has_failed_breakdown",
        "gap_up_session",
        "gap_down_session",
        "gap_filled_up",
        "gap_filled_down",
        "gap_filled",
        "is_at_ib_high",
        "is_at_ib_low",
        "is_60m_bottom_extreme",
        "is_60m_top_extreme",
        "is_narrow_or",
        "is_wide_or",
        "is_narrow_day",
        "two_prior_narrow_days",
        "is_inside_day_open_range",
        "gap_not_filled_by_1030",
        "is_choppy_open",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)

    return out


def attach_session_context(observations: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    context_cols = [
        "ts_event",
        "bar_index",
        "session_date",
        "prior_session_close",
        "gap",
        "gap_sign",
        "or_high",
        "or_low",
        "or_range",
        "ib_high",
        "ib_low",
        "opening_drive_sign",
        "is_choppy_open",
        "is_narrow_or",
        "is_wide_or",
        "two_prior_narrow_days",
        "is_inside_day_open_range",
        "trend_sign_15m",
        "high_60m",
        "low_60m",
        "range_60m",
        "price_is_doji",
        "after_1000",
        "after_1030",
        "close_above_or",
        "close_below_or",
        "inside_or",
        "has_broken_above_or",
        "has_broken_below_or",
        "has_failed_breakout",
        "has_failed_breakdown",
        "gap_up_session",
        "gap_down_session",
        "gap_filled_up",
        "gap_filled_down",
        "gap_filled",
        "gap_not_filled_by_1030",
        "is_at_ib_high",
        "is_at_ib_low",
        "is_60m_bottom_extreme",
        "is_60m_top_extreme",
    ]
    renamed = bars[context_cols].rename(
        columns={
            "ts_event": "bar_ts",
            "bar_index": "rth_bar_index",
            "session_date": "rth_session_date",
        }
    )
    df = observations.merge(renamed, on="bar_ts", how="left", validate="many_to_one")
    df = df[df["rth_session_date"].notna()].copy()

    df["signal_range"] = df["bar_high"] - df["bar_low"]
    df["signal_body"] = (df["bar_close"] - df["bar_open"]).abs()
    df["signal_is_doji"] = df["signal_range"].gt(0) & df["signal_body"].lt(0.10 * df["signal_range"])
    df["is_15m_trend_aligned"] = df["direction_sign"] == df["trend_sign_15m"]
    df["is_60m_reversal_extreme"] = (
        ((df["direction_sign"] > 0) & df["is_60m_bottom_extreme"])
        | ((df["direction_sign"] < 0) & df["is_60m_top_extreme"])
    )
    df["is_60m_momentum_extreme"] = (
        ((df["direction_sign"] > 0) & df["is_60m_top_extreme"])
        | ((df["direction_sign"] < 0) & df["is_60m_bottom_extreme"])
    )
    df["gap_direction_matches_signal"] = df["direction_sign"] == df["gap_sign"]
    df["gap_fill_direction_matches_signal"] = df["direction_sign"] == -df["gap_sign"]
    df["opening_drive_matches_signal"] = df["opening_drive_sign"].ne(0) & df["direction_sign"].eq(df["opening_drive_sign"])
    df["opening_drive_reversal_signal"] = df["opening_drive_sign"].ne(0) & df["direction_sign"].eq(-df["opening_drive_sign"])

    bool_cols = [
        "signal_is_doji",
        "is_15m_trend_aligned",
        "is_60m_reversal_extreme",
        "is_60m_momentum_extreme",
        "gap_direction_matches_signal",
        "gap_fill_direction_matches_signal",
        "opening_drive_matches_signal",
        "opening_drive_reversal_signal",
        "price_is_doji",
        "after_1000",
        "after_1030",
        "close_above_or",
        "close_below_or",
        "inside_or",
        "has_broken_above_or",
        "has_broken_below_or",
        "has_failed_breakout",
        "has_failed_breakdown",
        "gap_up_session",
        "gap_down_session",
        "gap_filled_up",
        "gap_filled_down",
        "gap_filled",
        "gap_not_filled_by_1030",
        "is_at_ib_high",
        "is_at_ib_low",
        "is_60m_bottom_extreme",
        "is_60m_top_extreme",
        "is_narrow_or",
        "is_wide_or",
        "two_prior_narrow_days",
        "is_inside_day_open_range",
        "is_choppy_open",
    ]
    for col in bool_cols:
        df[col] = df[col].fillna(False).astype(bool)

    return df.reset_index(drop=True)


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict:
    returns = df["ret_5b_ticks"].dropna()
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
        "median_return_5b_ticks": float(returns.median()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        (
            "01",
            "OR breakout above + top 60m extreme",
            lambda df: df["direction_sign"].gt(0)
            & df["has_broken_above_or"]
            & df["close_above_or"]
            & df["is_60m_top_extreme"],
        ),
        (
            "02",
            "OR breakdown below + bottom 60m extreme",
            lambda df: df["direction_sign"].lt(0)
            & df["has_broken_below_or"]
            & df["close_below_or"]
            & df["is_60m_bottom_extreme"],
        ),
        (
            "03",
            "Failed OR breakout trap + top 60m extreme",
            lambda df: df["direction_sign"].lt(0) & df["has_failed_breakout"] & df["is_60m_top_extreme"],
        ),
        (
            "04",
            "Failed OR breakdown trap + bottom 60m extreme",
            lambda df: df["direction_sign"].gt(0) & df["has_failed_breakdown"] & df["is_60m_bottom_extreme"],
        ),
        (
            "05",
            "OR breakout/breakdown + momentum 60m extreme + 15m trend",
            lambda df: (
                (
                    df["direction_sign"].gt(0)
                    & df["has_broken_above_or"]
                    & df["close_above_or"]
                    & df["is_60m_top_extreme"]
                )
                | (
                    df["direction_sign"].lt(0)
                    & df["has_broken_below_or"]
                    & df["close_below_or"]
                    & df["is_60m_bottom_extreme"]
                )
            )
            & df["is_15m_trend_aligned"],
        ),
        (
            "06",
            "Failed OR breakout/breakdown trap + reversal 60m extreme + 15m trend",
            lambda df: (
                (df["direction_sign"].lt(0) & df["has_failed_breakout"] & df["is_60m_top_extreme"])
                | (df["direction_sign"].gt(0) & df["has_failed_breakdown"] & df["is_60m_bottom_extreme"])
            )
            & df["is_15m_trend_aligned"],
        ),
        (
            "07",
            "Gap-up filled + bearish signal + momentum 60m extreme",
            lambda df: df["gap_up_session"]
            & df["gap_filled_up"]
            & df["gap_fill_direction_matches_signal"]
            & df["is_60m_momentum_extreme"],
        ),
        (
            "08",
            "Gap-down filled + bullish signal + momentum 60m extreme",
            lambda df: df["gap_down_session"]
            & df["gap_filled_down"]
            & df["gap_fill_direction_matches_signal"]
            & df["is_60m_momentum_extreme"],
        ),
        (
            "09",
            "Gap not filled by 10:30 + gap-direction continuation + momentum 60m extreme",
            lambda df: df["gap_not_filled_by_1030"]
            & df["after_1030"]
            & df["gap_direction_matches_signal"]
            & df["is_60m_momentum_extreme"],
        ),
        (
            "10",
            "Gap filled + doji + reversal 60m extreme",
            lambda df: df["gap_filled"] & df["signal_is_doji"] & df["gap_direction_matches_signal"] & df["is_60m_reversal_extreme"],
        ),
        (
            "11",
            "Narrow OR (bottom quartile) + momentum 60m extreme",
            lambda df: df["is_narrow_or"] & df["is_60m_momentum_extreme"],
        ),
        (
            "12",
            "Wide OR (top quartile) + momentum 60m extreme",
            lambda df: df["is_wide_or"] & df["is_60m_momentum_extreme"],
        ),
        (
            "13",
            "Narrow OR + momentum 60m extreme + 15m trend",
            lambda df: df["is_narrow_or"] & df["is_60m_momentum_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "14",
            "Wide OR + momentum 60m extreme + 15m trend",
            lambda df: df["is_wide_or"] & df["is_60m_momentum_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "15",
            "Strong opening drive + momentum 60m extreme",
            lambda df: df["opening_drive_matches_signal"] & df["is_60m_momentum_extreme"],
        ),
        (
            "16",
            "Choppy open + reversal 60m extreme",
            lambda df: df["is_choppy_open"] & df["is_60m_reversal_extreme"],
        ),
        (
            "17",
            "Opening drive + reversal signal after 10:00 + reversal 60m extreme",
            lambda df: df["opening_drive_reversal_signal"] & df["after_1000"] & df["is_60m_reversal_extreme"],
        ),
        (
            "18",
            "Initial balance extreme touch + reversal 60m extreme",
            lambda df: (
                (df["direction_sign"].gt(0) & df["is_at_ib_low"] & df["is_60m_bottom_extreme"])
                | (df["direction_sign"].lt(0) & df["is_at_ib_high"] & df["is_60m_top_extreme"])
            ),
        ),
        (
            "19",
            "Two prior narrow-range days + momentum 60m extreme",
            lambda df: df["two_prior_narrow_days"] & df["is_60m_momentum_extreme"],
        ),
        (
            "20",
            "Prior-day inside-range OR + momentum 60m extreme",
            lambda df: df["is_inside_day_open_range"] & df["is_60m_momentum_extreme"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy()))
    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_return_5b_ticks"]) else float(row["avg_return_5b_ticks"]),
            float("-inf") if pd.isna(row["win_rate"]) else float(row["win_rate"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict]) -> list[str]:
    headers = ["Filter", "N", "WR%", "PF", "Avg Ticks", "Med Ticks", "Wilson 95% CI"]
    data_rows: list[list[str]] = []

    for row in rows:
        filter_name = f"{row['code']}. {row['label']}"
        if row["flag"]:
            filter_name = f"{filter_name} [{row['flag']}]"
        data_rows.append(
            [
                filter_name,
                f"{row['n']:,}",
                fmt_pct(row["win_rate"]),
                fmt_float(row["profit_factor"]),
                fmt_float(row["avg_return_5b_ticks"]),
                fmt_float(row["median_return_5b_ticks"]),
                fmt_ci(row["ci_low"], row["ci_high"]),
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
    grouped_observation_count = len(observations)
    rth_bars = prepare_rth_bars(bars_1m)
    context = build_timeframe_context(rth_bars)
    rth_bars = attach_timeframe_context(rth_bars, context)
    sessions = build_session_summaries(rth_bars)
    rth_bars = compute_intraday_state(rth_bars, sessions)
    observations = attach_session_context(observations, rth_bars)

    baseline_all = summarize_filter("00", "All RTH non-zero-delta signal bars", observations)
    baseline_reversal = summarize_filter(
        "00A",
        "All RTH bars at reversal 60m extremes",
        observations[observations["is_60m_reversal_extreme"]].copy(),
    )
    baseline_momentum = summarize_filter(
        "00B",
        "All RTH bars at momentum 60m extremes",
        observations[observations["is_60m_momentum_extreme"]].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 6 gap + opening range analysis",
        "==========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index, restricted to RTH bars with session context.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        "RTH session = 09:30-15:59 America/New_York. 15m/60m bars are session-anchored from the 09:30 open.",
        "Opening range = first 15 one-minute bars (09:30-09:44). Initial balance = first 60 one-minute bars (09:30-10:29).",
        "Strong opening drive uses price-direction signs from the first 5 one-minute bars because nq_1yr_1m.csv has OHLCV but no delta column.",
        "Momentum 60m extreme = bullish bars near the top 20% of the active 60m range / bearish bars near the bottom 20%.",
        "Reversal 60m extreme = bullish bars near the bottom 20% of the active 60m range / bearish bars near the top 20%.",
        "Gap fill = session price crosses prior RTH close. Gap continuation = gap still unfilled through 10:29 and signal bar occurs from 10:30 onward.",
        "Narrow/Wide OR quartiles and narrow-day quartile are computed across the full session sample.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:               {len(events):,}",
        f"Grouped signal-bar observations:     {grouped_observation_count:,}",
        f"RTH 1m bars used:                    {len(rth_bars):,}",
        f"RTH sessions built:                  {len(sessions):,}",
        f"RTH observations with session data:  {len(observations):,}",
        f"15m bars built:                      {len(context[15]):,}",
        f"60m bars built:                      {len(context[60]):,}",
        f"Narrow OR sessions:                  {int(sessions['is_narrow_or'].sum()):,}",
        f"Wide OR sessions:                    {int(sessions['is_wide_or'].sum()):,}",
        f"Gap continuation sessions (10:30):   {int(sessions['gap_not_filled_by_1030'].sum()):,}",
        f"Two prior narrow-day sessions:       {int(sessions['two_prior_narrow_days'].sum()):,}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"All RTH bars:      N={baseline_all['n']:,} | WR={fmt_pct(baseline_all['win_rate'])} | PF={fmt_float(baseline_all['profit_factor'])} | Avg={fmt_float(baseline_all['avg_return_5b_ticks'])}t | Med={fmt_float(baseline_all['median_return_5b_ticks'])}t | CI={fmt_ci(baseline_all['ci_low'], baseline_all['ci_high'])}",
        f"Reversal 60m ext:  N={baseline_reversal['n']:,} | WR={fmt_pct(baseline_reversal['win_rate'])} | PF={fmt_float(baseline_reversal['profit_factor'])} | Avg={fmt_float(baseline_reversal['avg_return_5b_ticks'])}t | Med={fmt_float(baseline_reversal['median_return_5b_ticks'])}t | CI={fmt_ci(baseline_reversal['ci_low'], baseline_reversal['ci_high'])}",
        f"Momentum 60m ext:  N={baseline_momentum['n']:,} | WR={fmt_pct(baseline_momentum['win_rate'])} | PF={fmt_float(baseline_momentum['profit_factor'])} | Avg={fmt_float(baseline_momentum['avg_return_5b_ticks'])}t | Med={fmt_float(baseline_momentum['median_return_5b_ticks'])}t | CI={fmt_ci(baseline_momentum['ci_low'], baseline_momentum['ci_high'])}",
        "",
        "All 20 opening-range / gap filters ranked by 5-bar average return",
        "--------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
