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
OUT_PATH = OUT_DIR / "round4_final_walkforward_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
BETA_PRIOR_ALPHA = 10
BETA_PRIOR_BETA = 10
VALIDATION_MONTHS = pd.period_range("2025-01", "2026-04", freq="M")


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
        "direction": "string",
        "score_tier": "string",
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
        "strength",
        "score_final",
        "score_tier",
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
        "strength",
        "score_final",
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
    df["event_direction_sign"] = direction_to_sign(df["direction"])
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


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
            fwd_close_5b=("fwd_close_5b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .sort_values("global_index", kind="stable")
        .reset_index(drop=True)
    )
    observations["direction_sign"] = np.sign(observations["bar_delta"].fillna(0.0)).astype(int)
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    return observations


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["is_DELT_04"] = working["signal_id"].eq("DELT_04")
    working["is_TRAP_04"] = working["signal_id"].eq("TRAP_04")

    observations = (
        working.loc[working["event_direction_sign"].ne(0)]
        .groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
            max_score_final=("score_final", "max"),
            has_DELT_04=("is_DELT_04", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
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

    df["bar_open"] = pd.to_numeric(df["bar_open"], errors="coerce")
    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["body_high"] = np.maximum(bars["bar_open"], bars["bar_close"])
    bars["body_low"] = np.minimum(bars["bar_open"], bars["bar_close"])
    bars["upper_wick"] = bars["bar_high"] - bars["body_high"]
    bars["lower_wick"] = bars["body_low"] - bars["bar_low"]
    bars["prior_bar_range"] = by_session["bar_range"].shift(1)
    bars["bar_range_2"] = by_session["bar_range"].shift(2)
    bars["prior_body_high"] = by_session["body_high"].shift(1)
    bars["prior_body_low"] = by_session["body_low"].shift(1)

    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    bars["is_three_narrowing_ranges"] = (
        bars["bar_range_2"].notna()
        & bars["prior_bar_range"].lt(bars["bar_range_2"])
        & bars["bar_range"].lt(bars["prior_bar_range"])
    )

    bars["is_hammer"] = (
        bars["body"].gt(0)
        & bars["lower_wick"].gt(2.0 * bars["body"])
        & bars["upper_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].gt(bars["bar_open"])
    )
    bars["is_shooting_star"] = (
        bars["body"].gt(0)
        & bars["upper_wick"].gt(2.0 * bars["body"])
        & bars["lower_wick"].lt(0.5 * bars["body"])
        & bars["bar_close"].lt(bars["bar_open"])
    )
    bars["hammer_direction_sign"] = np.where(bars["is_hammer"], 1, 0)
    bars["shooting_star_direction_sign"] = np.where(bars["is_shooting_star"], -1, 0)

    bars["is_engulfing"] = (
        bars["prior_body_high"].notna()
        & bars["body_high"].gt(bars["prior_body_high"])
        & bars["body_low"].lt(bars["prior_body_low"])
    )
    bars["is_bullish_engulf"] = bars["is_engulfing"] & bars["bar_close"].gt(bars["bar_open"])
    bars["is_bearish_engulf"] = bars["is_engulfing"] & bars["bar_close"].lt(bars["bar_open"])
    bars["engulf_direction_sign"] = np.select(
        [bars["is_bullish_engulf"], bars["is_bearish_engulf"]],
        [1, -1],
        default=0,
    )
    return bars


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return np.sign(series).astype(int)


def is_60m_extreme_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return ((direction_sign > 0) & df["is_60m_extreme_bullish"]) | (
        (direction_sign < 0) & df["is_60m_extreme_bearish"]
    )


def is_15m_trend_aligned_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    return direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    rng_60m = out["range_60m"].replace(0, np.nan)
    out["pos_60m_low"] = (out["bar_low"] - out["low_60m"]) / rng_60m
    out["pos_60m_high"] = (out["bar_high"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme_bullish"] = out["pos_60m_low"].le(0.20)
    out["is_60m_extreme_bearish"] = out["pos_60m_high"].ge(0.80)
    out["is_60m_extreme"] = is_60m_extreme_for(out, out["direction_sign"])
    out["is_15m_trend_aligned"] = is_15m_trend_aligned_for(out, out["direction_sign"])
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] - 9) * 60 + out["minute"] - 30
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)
    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask
    return out


def prep_validation_frames() -> tuple[dict[str, pd.DataFrame], dict[int, pd.DataFrame], int]:
    events = load_events()
    bars_1m = load_ohlcv()
    context = build_timeframe_context(bars_1m)

    frames = {
        "bar": build_bar_observations(events),
        "signal": build_signal_observations(events),
    }

    processed_frames: dict[str, pd.DataFrame] = {}
    for frame_name, frame in frames.items():
        frame = attach_context(frame, context)
        if frame_name == "bar":
            frame = compute_bar_features(frame)
        frame = add_context_flags(frame)
        frame = add_time_flags(frame)
        frame["session_date_dt"] = pd.to_datetime(frame["session_date"], errors="coerce")
        frame["session_month"] = frame["session_date_dt"].dt.to_period("M")
        frame = frame[frame["session_month"].isin(VALIDATION_MONTHS)].copy()
        frame = frame.sort_values(["bar_ts", "global_index"], kind="stable").reset_index(drop=True)
        processed_frames[frame_name] = frame

    return processed_frames, context, len(events)


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


def prepare_trade_sample(df: pd.DataFrame, direction: int | pd.Series) -> pd.DataFrame:
    direction_sign = normalize_direction(direction, df)
    sample = df.loc[direction_sign.ne(0)].copy()
    sample["trade_direction_sign"] = direction_sign.loc[sample.index]
    sample["trade_ret_5b_ticks"] = sample["trade_direction_sign"] * sample["move_5b_ticks"]
    return sample.dropna(subset=["trade_ret_5b_ticks"]).copy()


def walk_forward_analysis(df: pd.DataFrame, windows: list[dict[str, object]]) -> dict[str, object]:
    oos_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    weak_windows: list[str] = []

    for window in windows:
        is_months = list(window["is_months"])
        oos_month = window["oos_month"]

        is_df = df.loc[df["session_month"].isin(is_months)].copy()
        oos_df = df.loc[df["session_month"].eq(oos_month)].copy()

        is_ret = is_df["trade_ret_5b_ticks"].dropna()
        oos_ret = oos_df["trade_ret_5b_ticks"].dropna()
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
            oos_frames.append(oos_df)

    oos_trade_df = pd.concat(oos_frames, ignore_index=True) if oos_frames else df.iloc[0:0].copy()
    oos_ret = oos_trade_df["trade_ret_5b_ticks"].dropna()
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


def monthly_stability(df: pd.DataFrame, months: list[pd.Period]) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for month in months:
        month_df = df.loc[df["session_month"].eq(month)].copy()
        ret = month_df["trade_ret_5b_ticks"].dropna()
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
    longest_losing_streak = 0
    current_losing_streak = 0

    for row in active_rows:
        if row["wr"] < 0.50:
            current_losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, current_losing_streak)
        else:
            current_losing_streak = 0
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
        "longest_losing_streak": longest_losing_streak,
        "flagged_bad_months": flagged_bad_months,
        "status": status,
        "reason": reason,
    }


def bayesian_analysis(df: pd.DataFrame) -> dict[str, object]:
    ret = df["trade_ret_5b_ticks"].dropna()
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


def frame_label(frame_name: str) -> str:
    labels = {
        "bar": "bar/global_index",
        "signal": "signal/global_index+direction",
    }
    return labels[frame_name]


def build_filter_specs() -> list[dict[str, object]]:
    return [
        {
            "code": "01",
            "label": "Hammer + 60m_extreme + 15m_trend_aligned",
            "source_frame": "bar",
            "predicate": lambda df: df["is_hammer"] & is_60m_extreme_for(df, 1) & is_15m_trend_aligned_for(df, 1),
            "direction": lambda df: 1,
            "ref_n": 177,
            "ref_wr": 0.785,
        },
        {
            "code": "02",
            "label": "Shooting star + 60m_extreme + 15m_trend_aligned",
            "source_frame": "bar",
            "predicate": lambda df: df["is_shooting_star"] & is_60m_extreme_for(df, -1) & is_15m_trend_aligned_for(df, -1),
            "direction": lambda df: -1,
            "ref_n": 150,
            "ref_wr": 0.787,
        },
        {
            "code": "03",
            "label": "Engulfing + 60m_extreme + 15m_trend_aligned",
            "source_frame": "bar",
            "predicate": lambda df: df["engulf_direction_sign"].ne(0)
            & is_60m_extreme_for(df, df["engulf_direction_sign"])
            & is_15m_trend_aligned_for(df, df["engulf_direction_sign"]),
            "direction": lambda df: df["engulf_direction_sign"],
            "ref_n": 1_756,
            "ref_wr": 0.767,
        },
        {
            "code": "04",
            "label": "score >= 60 + 60m_extreme + 15m_trend_aligned + first_hour",
            "source_frame": "signal",
            "predicate": lambda df: df["max_score_final"].ge(60)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_first_hour"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 3_362,
            "ref_wr": 0.835,
        },
        {
            "code": "05",
            "label": "score >= 60 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            "source_frame": "signal",
            "predicate": lambda df: df["max_score_final"].ge(60)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 4_749,
            "ref_wr": 0.831,
        },
        {
            "code": "06",
            "label": "score >= 70 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            "source_frame": "signal",
            "predicate": lambda df: df["max_score_final"].ge(70)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 1_107,
            "ref_wr": 0.832,
        },
        {
            "code": "07",
            "label": "5+ categories + 60m_extreme + 15m_trend_aligned",
            "source_frame": "signal",
            "predicate": lambda df: df["category_count"].ge(5) & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 1_159,
            "ref_wr": 0.821,
        },
        {
            "code": "08",
            "label": "60m_extreme + 15m_trend_aligned + first_hour (all signals)",
            "source_frame": "signal",
            "predicate": lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_first_hour"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 4_235,
            "ref_wr": 0.831,
        },
        {
            "code": "09",
            "label": "DELT_04 + TRAP_04 + 15m_trend_aligned",
            "source_frame": "signal",
            "predicate": lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & df["is_15m_trend_aligned"],
            "direction": lambda df: df["direction_sign"],
            "ref_n": 286,
            "ref_wr": 0.738,
            "note": "Previously walk-forward tested; included here for comparison.",
        },
        {
            "code": "10",
            "label": "Doji + 60m_extreme + 15m_trend_aligned + NOT lunch",
            "source_frame": "bar",
            "predicate": lambda df: df["is_doji"]
            & is_60m_extreme_for(df, df["direction_sign"])
            & is_15m_trend_aligned_for(df, df["direction_sign"])
            & df["is_not_lunch"],
            "direction": lambda df: df["direction_sign"],
        },
        {
            "code": "11",
            "label": "Doji + 60m_extreme + 15m_trend_aligned + first_hour",
            "source_frame": "bar",
            "predicate": lambda df: df["is_doji"]
            & is_60m_extreme_for(df, df["direction_sign"])
            & is_15m_trend_aligned_for(df, df["direction_sign"])
            & df["is_first_hour"],
            "direction": lambda df: df["direction_sign"],
        },
        {
            "code": "12",
            "label": "3 narrowing ranges + 60m_extreme + 15m_trend_aligned",
            "source_frame": "bar",
            "predicate": lambda df: df["is_three_narrowing_ranges"]
            & is_60m_extreme_for(df, df["direction_sign"])
            & is_15m_trend_aligned_for(df, df["direction_sign"]),
            "direction": lambda df: df["direction_sign"],
        },
    ]


def validate_filter(
    source_df: pd.DataFrame,
    filter_spec: dict[str, object],
    windows: list[dict[str, object]],
    oos_months: list[pd.Period],
) -> dict[str, object]:
    predicate = filter_spec["predicate"]
    direction_fn = filter_spec["direction"]
    filtered = source_df.loc[predicate(source_df)].copy()
    trade_df = prepare_trade_sample(filtered, direction_fn(filtered))
    returns = trade_df["trade_ret_5b_ticks"]
    walk_forward = walk_forward_analysis(trade_df, windows)
    oos_trade_df = walk_forward["oos_trade_df"]
    monthly = monthly_stability(oos_trade_df, oos_months)
    bayes = bayesian_analysis(oos_trade_df)

    return {
        "filter_code": str(filter_spec["code"]),
        "label": str(filter_spec["label"]),
        "source_frame": str(filter_spec["source_frame"]),
        "ref_n": filter_spec.get("ref_n"),
        "ref_wr": filter_spec.get("ref_wr"),
        "note": filter_spec.get("note"),
        "n": int(len(returns)),
        "wr": win_rate(returns),
        "pf": profit_factor(returns) if len(returns) else float("nan"),
        "avg_ticks": float(returns.mean()) if len(returns) else float("nan"),
        "walk_forward": walk_forward,
        "monthly": monthly,
        "bayes": bayes,
        "verdict": overall_verdict(walk_forward, monthly, bayes),
    }


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Rank", "Frame", "Filter", "N", "WR%", "OOS N", "OOS WR%", "OOS Wilson 95% CI", "OOS Bayes", "Verdict"]
    data_rows: list[list[str]] = []

    for idx, row in enumerate(results, start=1):
        walk_forward = row["walk_forward"]
        bayes = row["bayes"]
        data_rows.append(
            [
                str(idx),
                frame_label(str(row["source_frame"])),
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


def render_reference_line(result: dict[str, object]) -> str | None:
    ref_n = result["ref_n"]
    ref_wr = result["ref_wr"]
    if ref_n is None or ref_wr is None:
        return None
    n_delta = int(result["n"]) - int(ref_n)
    wr_delta_pp = (float(result["wr"]) - float(ref_wr)) * 100.0
    return (
        f"Discovery reference: N={int(ref_n):,}, WR={fmt_pct(float(ref_wr))} | "
        f"current delta: N {n_delta:+d}, WR {wr_delta_pp:+.1f}pp"
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
        f"Observation frame: {frame_label(str(result['source_frame']))}",
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
            f"  Window {int(row['window_num'])} ({row['label']}): IS N={int(row['is_n'])}, IS WR={fmt_pct(float(row['is_wr']))} | OOS N={int(row['oos_n'])}, Wins={int(row['oos_wins'])}, WR={fmt_pct(float(row['oos_wr']))}, Avg={fmt_ticks(float(row['oos_avg_ticks']))} ticks"
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
            f"  Longest losing streak (<50% WR months): {int(monthly['longest_losing_streak'])}",
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

    frames, context, raw_event_count = prep_validation_frames()
    windows = build_walk_forward_windows()
    oos_months = [window["oos_month"] for window in windows]
    bar_observations = frames["bar"]
    signal_observations = frames["signal"]

    results: list[dict[str, object]] = []
    for filter_spec in build_filter_specs():
        source_df = frames[str(filter_spec["source_frame"])]
        results.append(validate_filter(source_df, filter_spec, windows, oos_months))

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
        "ROUND 4 FINAL WALK-FORWARD VALIDATION",
        "====================================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Bar-pattern filters use unique bars deduplicated by global_index.",
        "Signal-stack filters use same-bar, same-direction grouped signal observations.",
        "Hammer / shooting star / engulfing definitions match round3_multi_bar_sequences.py.",
        "Doji = body / range < 10%, direction from sign(bar_delta).",
        "3 narrowing ranges = current range < prior range < 2-bars-back range within session, direction from sign(bar_delta).",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m_trend_aligned = trade direction matches sign(15m close - 15m open).",
        "Time filters use America/New_York. first_hour = 09:30-10:30 ET. lunch exclusion = 12:00-14:00 ET.",
        "Walk-forward windows: Jan-Feb→Mar 2025, Apr-May→Jun 2025, Jun-Jul→Aug 2025, Sep-Oct→Nov 2025, Nov-Dec 2025→Jan 2026, Feb-Mar→Apr 2026.",
        "Monthly stability and Bayesian metrics are computed on the composite OOS trades only.",
        "",
        f"Raw event rows loaded:             {raw_event_count:,}",
        f"Bar observations:                  {len(bar_observations):,}",
        f"Signal observations:               {len(signal_observations):,}",
        f"15m bars built:                    {len(context[15]):,}",
        f"60m bars built:                    {len(context[60]):,}",
        f"Hammer bars:                       {int(bar_observations['is_hammer'].sum()):,}",
        f"Shooting star bars:                {int(bar_observations['is_shooting_star'].sum()):,}",
        f"Engulfing bars:                    {int(bar_observations['engulf_direction_sign'].ne(0).sum()):,}",
        f"Doji bars:                         {int(bar_observations['is_doji'].sum()):,}",
        f"3 narrowing range bars:            {int(bar_observations['is_three_narrowing_ranges'].sum()):,}",
        f"Signal obs with 5+ categories:     {int(signal_observations['category_count'].ge(5).sum()):,}",
        f"Signal obs with score >= 60:       {int(signal_observations['max_score_final'].ge(60).sum()):,}",
        f"Signal obs with score >= 70:       {int(signal_observations['max_score_final'].ge(70).sum()):,}",
        f"Signal obs with DELT_04 + TRAP_04: {int((signal_observations['has_DELT_04'] & signal_observations['has_TRAP_04']).sum()):,}",
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
