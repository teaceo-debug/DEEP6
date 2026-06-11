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
OUT_PATH = OUT_DIR / "round22_inverse_signals_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FOMC_DATES = {
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-10",
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-09",
}


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


def fmt_count(value: int) -> str:
    return f"{value:,}"


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


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


def status_flag(n: int, ci_low: float, avg_return_5b_ticks: float) -> str:
    if n < 15:
        return "LOW_N"
    if pd.isna(avg_return_5b_ticks) or avg_return_5b_ticks <= 0:
        return ""
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
    df = df[df["event_direction_sign"] != 0].copy()
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_bar_frame(events: pd.DataFrame) -> pd.DataFrame:
    bars = (
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
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    bars["signal_bar_seq"] = bars.groupby("session_date", sort=False).cumcount().astype("int32")
    return bars


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            signal_ids=("signal_id", lambda s: tuple(sorted({str(v) for v in s.dropna()}))),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["ret_5b_ticks"] = observations["direction_sign"] * (
        (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    )
    observations["anti_ret_5b_ticks"] = -observations["ret_5b_ticks"]
    return observations


def compute_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_sign"] = np.sign(out["bar_delta"].fillna(0.0)).astype(int)
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_sign"] = np.sign(out["price_change"].fillna(0.0)).astype(int)
    out["prev_close"] = by_session["bar_close"].shift(1)

    true_range_parts = pd.concat(
        [
            out["bar_high"] - out["bar_low"],
            (out["bar_high"] - out["prev_close"]).abs(),
            (out["bar_low"] - out["prev_close"]).abs(),
        ],
        axis=1,
    )
    out["true_range"] = true_range_parts.max(axis=1)

    out["prior_bar_volume"] = by_session["bar_volume"].shift(1)
    out["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    out["prior_delta_sign"] = by_session["delta_sign"].shift(1)
    out["next_delta_sign"] = by_session["delta_sign"].shift(-1)
    out["next2_delta_sign"] = by_session["delta_sign"].shift(-2)
    out["next_price_sign"] = by_session["price_sign"].shift(-1)
    out["next_bar_close"] = by_session["bar_close"].shift(-1)
    out["next_fwd_close_5b"] = by_session["fwd_close_5b"].shift(-1)
    out["next_global_index"] = by_session["global_index"].shift(-1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["prior_rolling_20_ema_vol"] = out.groupby("session_date", sort=False)["rolling_20_ema_vol"].shift(1)
    out["abs_delta_q90"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.90)
    )
    out["atr_20"] = by_session["true_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).mean()
    )

    out["session_cvd"] = by_session["bar_delta"].cumsum()
    out["session_cvd_sign"] = np.sign(out["session_cvd"].fillna(0.0)).astype(int)

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["next_is_doji"] = out.groupby("session_date", sort=False)["is_doji"].shift(-1)

    out["volume_context_valid"] = out["rolling_20_ema_vol"].gt(0)
    out["prior_volume_context_valid"] = out["prior_rolling_20_ema_vol"].gt(0)
    out["prior_is_volume_spike_2x"] = out["prior_volume_context_valid"] & out["prior_bar_volume"].gt(
        2.0 * out["prior_rolling_20_ema_vol"]
    )
    return out


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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])
    out["is_15m_trend_opposite"] = out["direction_sign"].eq(-out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(
        out["direction_sign"] > 0,
        out["bar_low"],
        np.where(out["direction_sign"] < 0, out["bar_high"], np.nan),
    )
    out["anchor_pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["close_pos_60m"] = (out["bar_close"] - out["low_60m"]) / rng_60m
    out["directional_close_pos_60m"] = np.where(
        out["direction_sign"] > 0,
        out["close_pos_60m"],
        1.0 - out["close_pos_60m"],
    )
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["anchor_pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["anchor_pos_60m"].ge(0.80))
    )
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]
    out["is_directional_30_40_60m"] = out["directional_close_pos_60m"].between(0.30, 0.40, inclusive="both")
    out["is_mid_40_60_60m"] = out["close_pos_60m"].between(0.40, 0.60, inclusive="both")
    out["is_cvd_confirming"] = out["session_cvd_sign"].eq(out["direction_sign"]) & out["delta_sign"].eq(
        out["direction_sign"]
    )

    bool_cols = [
        "is_15m_trend_aligned",
        "is_15m_trend_opposite",
        "is_60m_extreme",
        "has_core_60m_15m_gate",
        "is_directional_30_40_60m",
        "is_mid_40_60_60m",
        "is_cvd_confirming",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_lunch"] = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_last_30m"] = out["minutes_since_930"].ge(360) & out["minutes_since_930"].lt(390)
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)
    out["is_afternoon"] = out["minutes_since_930"].ge(270) & out["minutes_since_930"].lt(390)
    out["is_fomc_day"] = out["session_date"].isin(FOMC_DATES)

    for col in ["is_lunch", "is_last_30m", "is_first_hour", "is_afternoon", "is_fomc_day"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_analysis_frame(events: pd.DataFrame, bars_1m: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    bars = build_bar_frame(events)
    bar_features = compute_bar_features(bars)
    observations = build_signal_observations(events)
    context = build_timeframe_context(bars_1m)

    feature_cols = [
        "global_index",
        "signal_bar_seq",
        "bar_delta",
        "bar_volume",
        "bar_range",
        "body",
        "abs_delta",
        "delta_sign",
        "price_sign",
        "true_range",
        "prior_bar_volume",
        "prior_bar_delta",
        "prior_delta_sign",
        "next_delta_sign",
        "next2_delta_sign",
        "next_price_sign",
        "next_bar_close",
        "next_fwd_close_5b",
        "next_global_index",
        "rolling_20_ema_vol",
        "prior_rolling_20_ema_vol",
        "abs_delta_q90",
        "atr_20",
        "session_cvd",
        "session_cvd_sign",
        "is_doji",
        "next_is_doji",
        "volume_context_valid",
        "prior_volume_context_valid",
        "prior_is_volume_spike_2x",
    ]
    observations = observations.merge(
        bar_features[feature_cols],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_context(observations, context)
    observations = add_context_flags(observations)
    observations = add_time_flags(observations)

    atr_threshold = float(observations["atr_20"].dropna().quantile(2.0 / 3.0)) if observations["atr_20"].notna().any() else float("nan")
    observations["is_high_atr_tercile"] = False if pd.isna(atr_threshold) else observations["atr_20"].ge(atr_threshold)
    observations["is_high_atr_tercile"] = observations["is_high_atr_tercile"].fillna(False).astype(bool)
    observations["signal_id_set"] = observations["signal_ids"].map(frozenset)
    return observations.reset_index(drop=True), atr_threshold


def add_base_history(base: pd.DataFrame) -> pd.DataFrame:
    out = base.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True).copy()
    out["has_ret_5b"] = out["ret_5b_ticks"].notna()
    out["is_win"] = out["has_ret_5b"] & out["ret_5b_ticks"].gt(0)
    out["is_loss"] = out["has_ret_5b"] & out["ret_5b_ticks"].le(0)

    prior_win_streak: list[int] = []
    prior_loss_streak: list[int] = []
    current_win_streak = 0
    current_loss_streak = 0

    for is_win, is_loss in zip(out["is_win"], out["is_loss"]):
        prior_win_streak.append(current_win_streak)
        prior_loss_streak.append(current_loss_streak)
        if bool(is_win):
            current_win_streak += 1
            current_loss_streak = 0
        elif bool(is_loss):
            current_loss_streak += 1
            current_win_streak = 0
        else:
            current_win_streak = 0
            current_loss_streak = 0

    out["prior_win_streak"] = np.array(prior_win_streak, dtype="int32")
    out["prior_loss_streak"] = np.array(prior_loss_streak, dtype="int32")
    return out


def summarize_filter(code: str, label: str, returns: pd.Series) -> dict[str, object]:
    clean_returns = pd.to_numeric(returns, errors="coerce").dropna()
    n = int(len(clean_returns))
    wins = int((clean_returns > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    avg_return_5b_ticks = float(clean_returns.mean()) if n else np.nan
    return {
        "code": code,
        "label": label,
        "n": n,
        "win_rate": win_rate,
        "profit_factor": profit_factor(clean_returns) if n else np.nan,
        "avg_return_5b_ticks": avg_return_5b_ticks,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low, avg_return_5b_ticks),
    }


def filter_15_same_signal_retry(base: pd.DataFrame) -> pd.Series:
    hits = pd.Series(False, index=base.index)
    for _, group in base.groupby("session_date", sort=False):
        rows = list(group.itertuples())
        for row in rows:
            matched = False
            for prior in rows:
                if prior.Index >= row.Index:
                    break
                gap = int(row.signal_bar_seq) - int(prior.signal_bar_seq)
                if gap <= 0 or gap > 5:
                    continue
                if not bool(prior.is_loss):
                    continue
                if int(prior.direction_sign) != int(row.direction_sign):
                    continue
                if prior.signal_id_set.intersection(row.signal_id_set):
                    matched = True
                    break
            hits.loc[row.Index] = matched
    return hits


def filter_16_opposite_after_loss(base: pd.DataFrame) -> pd.Series:
    hits = pd.Series(False, index=base.index)
    for _, group in base.groupby("session_date", sort=False):
        rows = list(group.itertuples())
        for row in rows:
            matched = False
            for prior in rows:
                if prior.Index >= row.Index:
                    break
                gap = int(row.signal_bar_seq) - int(prior.signal_bar_seq)
                if gap <= 0 or gap > 3:
                    continue
                if bool(prior.is_loss) and int(prior.direction_sign) == -int(row.direction_sign):
                    matched = True
                    break
            hits.loc[row.Index] = matched
    return hits


def build_filter_18_trades(base: pd.DataFrame) -> pd.Series:
    direction = base["next_price_sign"].fillna(0).astype(int)
    direction = direction.where(direction.ne(0), base["next_delta_sign"].fillna(0).astype(int))
    returns = direction * ((base["next_fwd_close_5b"] - base["next_bar_close"]) / TICK_SIZE)
    mask = base["is_loss"] & base["next_is_doji"].fillna(False).astype(bool) & direction.ne(0)
    return returns[mask]


def build_filter_19_trades(base: pd.DataFrame, analysis: pd.DataFrame) -> pd.Series:
    ordered_sessions = (
        analysis.groupby("session_date", as_index=False, sort=False)
        .agg(session_start_ts=("bar_ts", "min"))
        .sort_values("session_start_ts", kind="stable")
        ["session_date"]
        .tolist()
    )
    next_session_map = {
        ordered_sessions[idx]: ordered_sessions[idx + 1]
        for idx in range(len(ordered_sessions) - 1)
    }

    last_30m_losing_sessions = set(base.loc[base["is_last_30m"] & base["is_loss"], "session_date"].tolist())
    trade_indices: list[int] = []

    for session_date in ordered_sessions:
        if session_date not in last_30m_losing_sessions:
            continue
        next_session = next_session_map.get(session_date)
        if next_session is None:
            continue
        target = base.loc[(base["session_date"] == next_session) & base["is_first_hour"]].sort_values(
            ["bar_ts", "global_index", "direction_sign"],
            kind="stable",
        )
        if not target.empty:
            trade_indices.append(int(target.index[0]))

    if not trade_indices:
        return pd.Series(dtype="float64")
    return base.loc[sorted(set(trade_indices)), "ret_5b_ticks"]


def build_filter_20_trades(base: pd.DataFrame) -> pd.Series:
    trade_indices: list[int] = []
    for _, group in base.groupby("session_date", sort=False):
        morning_losers = group.loc[group["is_first_hour"] & group["is_loss"]]
        if morning_losers.empty:
            continue

        target_directions = {-int(direction) for direction in morning_losers["direction_sign"].unique().tolist()}
        afternoon = group.loc[group["is_afternoon"]].sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable")
        for direction in target_directions:
            match = afternoon.loc[afternoon["direction_sign"].eq(direction)]
            if not match.empty:
                trade_indices.append(int(match.index[0]))

    if not trade_indices:
        return pd.Series(dtype="float64")
    return base.loc[sorted(set(trade_indices)), "ret_5b_ticks"]


def evaluate_filters(analysis: pd.DataFrame) -> list[dict[str, object]]:
    base = add_base_history(analysis.loc[analysis["has_core_60m_15m_gate"]].copy())
    results = [
        summarize_filter(
            "01",
            "A1 BASE: prior win streak >= 3 before 60m+15m signal",
            base.loc[base["prior_win_streak"].ge(3), "ret_5b_ticks"],
        ),
        summarize_filter(
            "02",
            "A2 BASE: prior bar volume spike > 2x EMA before 60m+15m signal",
            base.loc[base["prior_is_volume_spike_2x"], "ret_5b_ticks"],
        ),
        summarize_filter(
            "03",
            "A3 BASE: current abs delta > rolling 90th percentile on 60m+15m signal",
            base.loc[
                base["abs_delta_q90"].notna() & base["delta_sign"].eq(base["direction_sign"]) & base["abs_delta"].gt(base["abs_delta_q90"]),
                "ret_5b_ticks",
            ],
        ),
        summarize_filter(
            "04",
            "A4 BASE: directional close sits 30-40% into 60m range on 60m+15m signal",
            base.loc[base["is_directional_30_40_60m"], "ret_5b_ticks"],
        ),
        summarize_filter(
            "05",
            "A5 BASE: FOMC day 60m+15m signal",
            base.loc[base["is_fomc_day"], "ret_5b_ticks"],
        ),
        summarize_filter(
            "06",
            "B6 ANTI: next signal-bar delta flips opposite 60m+15m signal",
            base.loc[base["next_delta_sign"].eq(-base["direction_sign"]), "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "07",
            "B7 ANTI: next two signal-bar deltas both flip opposite 60m+15m signal",
            base.loc[
                base["next_delta_sign"].eq(-base["direction_sign"]) & base["next2_delta_sign"].eq(-base["direction_sign"]),
                "anti_ret_5b_ticks",
            ],
        ),
        summarize_filter(
            "08",
            "B8 ANTI: lunch-hour (12:00-14:00) 60m+15m signal",
            base.loc[base["is_lunch"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "09",
            "B9 ANTI: current volume > 3x EMA on 60m+15m signal",
            base.loc[base["volume_context_valid"] & base["bar_volume"].gt(3.0 * base["rolling_20_ema_vol"]), "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "10",
            "B10 ANTI: close sits in middle 40-60% of 60m range on 60m+15m signal",
            base.loc[base["is_mid_40_60_60m"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "11",
            "C11 ANTI: 60m extreme + 15m trend opposite to signal direction",
            analysis.loc[analysis["is_60m_extreme"] & analysis["is_15m_trend_opposite"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "12",
            "C12 ANTI: 60m extreme + no 15m trend alignment",
            analysis.loc[analysis["is_60m_extreme"] & ~analysis["is_15m_trend_aligned"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "13",
            "C13 ANTI: 60m+15m signal + high ATR top tercile",
            base.loc[base["is_high_atr_tercile"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "14",
            "C14 ANTI: 60m extreme + CVD confirms signal direction",
            analysis.loc[analysis["is_60m_extreme"] & analysis["is_cvd_confirming"], "anti_ret_5b_ticks"],
        ),
        summarize_filter(
            "15",
            "D15 BASE: losing signal repeats with overlapping signal_id set within 5 bars",
            base.loc[filter_15_same_signal_retry(base), "ret_5b_ticks"],
        ),
        summarize_filter(
            "16",
            "D16 BASE: losing signal followed by opposite 60m+15m signal within 3 bars",
            base.loc[filter_16_opposite_after_loss(base), "ret_5b_ticks"],
        ),
        summarize_filter(
            "17",
            "D17 BASE: next 60m+15m signal after prior loss streak >= 2",
            base.loc[base["prior_loss_streak"].ge(2), "ret_5b_ticks"],
        ),
        summarize_filter(
            "18",
            "D18 BAR: losing 60m+15m signal then next signal bar is doji, trade doji direction",
            build_filter_18_trades(base),
        ),
        summarize_filter(
            "19",
            "E19 BASE: next-session first-hour signal after prior-session last-30m loser",
            build_filter_19_trades(base, analysis),
        ),
        summarize_filter(
            "20",
            "E20 BASE: first afternoon reversal signal after first-hour loser",
            build_filter_20_trades(base),
        ),
    ]

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
                fmt_count(int(row["n"])),
                fmt_pct(float(row["win_rate"])),
                fmt_float(float(row["profit_factor"])),
                fmt_ticks(float(row["avg_return_5b_ticks"])),
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
    analysis, atr_threshold = build_analysis_frame(events, bars_1m)
    base = add_base_history(analysis.loc[analysis["has_core_60m_15m_gate"]].copy())
    results = evaluate_filters(analysis)

    base_returns = base["ret_5b_ticks"].dropna()
    base_n = int(len(base_returns))
    base_wins = int((base_returns > 0).sum())
    base_ci_low, base_ci_high, base_wr = wilson_ci(base_n, base_wins)

    lines = [
        "DEEP6 Round 22 inverse signals analysis",
        "=====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal observation grouped by global_index + direction_sign.",
        "Base 60m+15m gate: is_60m_extreme & is_15m_trend_aligned.",
        "Signal-bar sequencing follows signal_events bars, matching earlier round2/round7 pattern work.",
        "Filters 01-05 keep original direction to isolate loss-prone base subsets.",
        "Filters 06-14 flip direction_sign on the same observation (ANTI logic).",
        "Filters 15-20 trade linked later observations/bars in the direction described by the pattern.",
        "Within-X-bar recurrence filters stay inside the same session. Streak filters use chronological base observations.",
        "C14 CVD confirmation uses session cumulative delta on signal-event bars aligned with the signal direction.",
        "Filter rows are sorted by Avg Ticks descending.",
        "",
        f"Raw event rows loaded:           {len(events):,}",
        f"Signal observations:             {len(analysis):,}",
        f"Base 60m+15m observations:       {len(base):,}",
        f"Base WR 5b:                      {fmt_pct(base_wr)}",
        f"Base PF:                         {fmt_float(profit_factor(base_returns) if base_n else np.nan)}",
        f"Base Avg Ticks:                  {fmt_ticks(float(base_returns.mean()) if base_n else np.nan)}",
        f"Base Wilson 95% CI:              {fmt_ci(base_ci_low, base_ci_high)}",
        f"ATR top-tercile threshold:       {fmt_float(atr_threshold)}",
        "",
        "20 inverse / failure filters",
        "----------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
