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
OUT_PATH = OUT_DIR / "round11_chain_triple_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
ATR_WINDOW = 20
SMA_WINDOW = 50
DELTA_LOOKBACK = 10
CONTRARIAN_LOOKBACK = 10
SEQUENCE_DIRECTIONS = (-1, 1)


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
    df["direction_sign"] = np.sign(df["bar_delta"].fillna(0.0)).astype(int)
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["is_absorption"] = working["category"].eq("absorption")
    working["is_TRAP_04"] = working["signal_id"].eq("TRAP_04")
    working["is_TRAP_05"] = working["signal_id"].eq("TRAP_05")
    working["is_EXH_03"] = working["signal_id"].eq("EXH_03")
    working["is_DELT_04"] = working["signal_id"].eq("DELT_04")
    working["is_TYPE_B"] = working["score_tier"].eq("TYPE_B")

    observations = (
        working.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
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
            max_strength=("strength", "max"),
            score_final_bar=("score_final", "max"),
            has_absorption=("is_absorption", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
            has_TRAP_05=("is_TRAP_05", "max"),
            has_EXH_03=("is_EXH_03", "max"),
            has_DELT_04=("is_DELT_04", "max"),
            has_TYPE_B=("is_TYPE_B", "max"),
        )
        .sort_values(["session_date", "global_index"], kind="stable")
        .reset_index(drop=True)
    )
    observations["move_5b_ticks"] = (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    observations["ret_5b_ticks"] = np.where(
        observations["direction_sign"].ne(0),
        observations["direction_sign"] * observations["move_5b_ticks"],
        np.nan,
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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def classify_volatility_regime(series: pd.Series) -> pd.Series:
    try:
        return pd.qcut(series, q=3, labels=["low_vol", "mid_vol", "high_vol"], duplicates="drop")
    except ValueError:
        valid = series.dropna()
        if valid.empty:
            return pd.Series(pd.NA, index=series.index, dtype="string")
        low_cut = float(valid.quantile(1 / 3))
        high_cut = float(valid.quantile(2 / 3))
        out = pd.Series(index=series.index, dtype="object")
        out.loc[series.lt(low_cut)] = "low_vol"
        out.loc[series.ge(low_cut) & series.le(high_cut)] = "mid_vol"
        out.loc[series.gt(high_cut)] = "high_vol"
        return out.astype("string")


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["body_high"] = np.maximum(out["bar_open"], out["bar_close"])
    out["body_low"] = np.minimum(out["bar_open"], out["bar_close"])
    out["prior_body_high"] = by_session["body_high"].shift(1)
    out["prior_body_low"] = by_session["body_low"].shift(1)
    out["prior_close"] = by_session["bar_close"].shift(1)

    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])
    out["is_engulfing"] = (
        out["prior_body_high"].notna()
        & out["body_high"].gt(out["prior_body_high"])
        & out["body_low"].lt(out["prior_body_low"])
    )

    tr_components = pd.concat(
        [
            out["bar_high"] - out["bar_low"],
            (out["bar_high"] - out["prior_close"]).abs(),
            (out["bar_low"] - out["prior_close"]).abs(),
        ],
        axis=1,
    )
    out["tr"] = tr_components.max(axis=1)
    by_session = out.groupby("session_date", sort=False)
    out["atr_20"] = by_session["tr"].transform(lambda s: s.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean())
    out["prior_atr_20"] = by_session["atr_20"].shift(1)

    out["volatility_regime"] = classify_volatility_regime(out["atr_20"])
    out["is_mid_vol"] = out["volatility_regime"].eq("mid_vol")

    out["prior_delta_10"] = by_session["bar_delta"].transform(
        lambda s: s.shift(1).rolling(DELTA_LOOKBACK, min_periods=DELTA_LOOKBACK).sum()
    )
    delta_side = np.sign(out["prior_delta_10"].fillna(0.0)) * out["direction_sign"]
    out["is_delta_opposite"] = delta_side.lt(0)

    out["cvd"] = by_session["bar_delta"].cumsum()
    by_session = out.groupby("session_date", sort=False)
    out["prior_cvd"] = by_session["cvd"].shift(1)
    out["cvd_crossed_zero"] = out["prior_cvd"].notna() & (
        ((out["prior_cvd"] < 0) & (out["cvd"] > 0)) | ((out["prior_cvd"] > 0) & (out["cvd"] < 0))
    )

    out["sma50"] = by_session["bar_close"].transform(lambda s: s.rolling(SMA_WINDOW, min_periods=SMA_WINDOW).mean())
    out["sma50_diff"] = out["bar_close"] - out["sma50"]
    by_session = out.groupby("session_date", sort=False)
    out["prior_sma50_diff"] = by_session["sma50_diff"].shift(1)
    out["price_crossed_sma50"] = out["prior_sma50_diff"].notna() & (
        ((out["prior_sma50_diff"] < 0) & (out["sma50_diff"] >= 0))
        | ((out["prior_sma50_diff"] > 0) & (out["sma50_diff"] <= 0))
    )

    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] - 9) * 60 + out["minute"] - 30
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)

    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask

    out["is_bullish_dir"] = out["direction_sign"].eq(1)
    out["is_bearish_dir"] = out["direction_sign"].eq(-1)
    by_session = out.groupby("session_date", sort=False)
    out["prior_bullish_count_10"] = by_session["is_bullish_dir"].transform(
        lambda s: s.shift(1).rolling(CONTRARIAN_LOOKBACK, min_periods=CONTRARIAN_LOOKBACK).sum()
    )
    out["prior_bearish_count_10"] = by_session["is_bearish_dir"].transform(
        lambda s: s.shift(1).rolling(CONTRARIAN_LOOKBACK, min_periods=CONTRARIAN_LOOKBACK).sum()
    )
    out["is_contrarian_reversal"] = (
        (out["direction_sign"].eq(-1) & out["prior_bullish_count_10"].ge(7))
        | (out["direction_sign"].eq(1) & out["prior_bearish_count_10"].ge(7))
    )

    return out


def compute_thresholds(df: pd.DataFrame) -> dict[str, float]:
    atr_20 = df["atr_20"].dropna()
    return {
        "atr_50pct": float(atr_20.quantile(0.50)) if not atr_20.empty else float("nan"),
    }


def add_context_flags(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_60m"].ge(0.80))
    )

    atr_50pct = thresholds["atr_50pct"]
    out["atr_crossed_above_50pct"] = (
        out["prior_atr_20"].notna() & out["prior_atr_20"].lt(atr_50pct) & out["atr_20"].ge(atr_50pct)
    )
    out["atr_crossed_below_50pct"] = (
        out["prior_atr_20"].notna() & out["prior_atr_20"].gt(atr_50pct) & out["atr_20"].le(atr_50pct)
    )
    return out


def build_condition_cache(df: pd.DataFrame) -> dict[tuple[str, int], np.ndarray]:
    cache: dict[tuple[str, int], np.ndarray] = {}
    for direction in SEQUENCE_DIRECTIONS:
        dir_mask = df["direction_sign"].eq(direction)
        cache[("signal_EXH_03", direction)] = (df["has_EXH_03"] & dir_mask).to_numpy(dtype=bool)
        cache[("signal_DELT_04", direction)] = (df["has_DELT_04"] & dir_mask).to_numpy(dtype=bool)
        cache[("signal_TRAP_04", direction)] = (df["has_TRAP_04"] & dir_mask).to_numpy(dtype=bool)
        cache[("signal_TRAP_05", direction)] = (df["has_TRAP_05"] & dir_mask).to_numpy(dtype=bool)
        cache[("category_absorption", direction)] = (df["has_absorption"] & dir_mask).to_numpy(dtype=bool)
        cache[("doji", direction)] = (df["is_doji"] & dir_mask).to_numpy(dtype=bool)
        cache[("engulfing", direction)] = (df["is_engulfing"] & dir_mask).to_numpy(dtype=bool)
        cache[("category_ge_2", direction)] = (df["category_count"].ge(2) & dir_mask).to_numpy(dtype=bool)
        cache[("category_ge_3", direction)] = (df["category_count"].ge(3) & dir_mask).to_numpy(dtype=bool)
        cache[("category_ge_4", direction)] = (df["category_count"].ge(4) & dir_mask).to_numpy(dtype=bool)
        cache[("score_lt_50", direction)] = (df["score_final_bar"].lt(50) & dir_mask).to_numpy(dtype=bool)
        cache[("score_ge_60", direction)] = (df["score_final_bar"].ge(60) & dir_mask).to_numpy(dtype=bool)
        cache[("score_ge_70", direction)] = (df["score_final_bar"].ge(70) & dir_mask).to_numpy(dtype=bool)
        cache[("type_b_bar", direction)] = (df["has_TYPE_B"] & dir_mask).to_numpy(dtype=bool)
    return cache


def summarize_returns(code: str, group: str, label: str, returns: list[float] | pd.Series) -> dict[str, object]:
    series = pd.Series(returns, dtype="float64").dropna()
    n = int(len(series))
    wins = int((series > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    return {
        "code": code,
        "group": group,
        "label": label,
        "n": n,
        "wr_5b": win_rate,
        "pf_5b": profit_factor(series) if n else np.nan,
        "avg_ticks_5b": float(series.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def summarize_mask(code: str, group: str, label: str, df: pd.DataFrame) -> dict[str, object]:
    return summarize_returns(code, group, label, df["ret_5b_ticks"])


def collect_three_step_sequence_returns(
    session_positions: list[np.ndarray],
    cache: dict[tuple[str, int], np.ndarray],
    returns_5b: np.ndarray,
    gate: np.ndarray,
    first_name: str,
    second_name: str,
    third_name: str,
    total_lookahead: int,
) -> list[float]:
    matched_returns: list[float] = []

    for positions in session_positions:
        session_len = len(positions)
        for start_offset, start_idx in enumerate(positions):
            found_match = False
            for direction in SEQUENCE_DIRECTIONS:
                if not cache[(first_name, direction)][start_idx]:
                    continue

                max_second_step = min(total_lookahead - 1, session_len - start_offset - 2)
                for second_step in range(1, max_second_step + 1):
                    second_idx = positions[start_offset + second_step]
                    if not cache[(second_name, direction)][second_idx]:
                        continue

                    max_third_step = min(total_lookahead - second_step, session_len - start_offset - second_step - 1)
                    for third_step in range(1, max_third_step + 1):
                        third_idx = positions[start_offset + second_step + third_step]
                        if not cache[(third_name, direction)][third_idx]:
                            continue
                        if not gate[third_idx]:
                            continue

                        ret_5b = returns_5b[third_idx]
                        if not np.isnan(ret_5b):
                            matched_returns.append(float(ret_5b))
                        found_match = True
                        break

                    if found_match:
                        break

                if found_match:
                    break

    return matched_returns


def collect_two_step_sequence_returns(
    session_positions: list[np.ndarray],
    cache: dict[tuple[str, int], np.ndarray],
    returns_5b: np.ndarray,
    gate: np.ndarray,
    first_name: str,
    second_name: str,
    total_lookahead: int,
) -> list[float]:
    matched_returns: list[float] = []

    for positions in session_positions:
        session_len = len(positions)
        for start_offset, start_idx in enumerate(positions):
            found_match = False
            for direction in SEQUENCE_DIRECTIONS:
                if not cache[(first_name, direction)][start_idx]:
                    continue

                max_step = min(total_lookahead, session_len - start_offset - 1)
                for step in range(1, max_step + 1):
                    end_idx = positions[start_offset + step]
                    if not cache[(second_name, direction)][end_idx]:
                        continue
                    if not gate[end_idx]:
                        continue

                    ret_5b = returns_5b[end_idx]
                    if not np.isnan(ret_5b):
                        matched_returns.append(float(ret_5b))
                    found_match = True
                    break

                if found_match:
                    break

    return matched_returns


def collect_gap_absorption_returns(
    session_positions: list[np.ndarray],
    cache: dict[tuple[str, int], np.ndarray],
    returns_5b: np.ndarray,
    gate: np.ndarray,
) -> list[float]:
    matched_returns: list[float] = []

    for positions in session_positions:
        session_len = len(positions)
        for start_offset, start_idx in enumerate(positions):
            if start_offset + 4 >= session_len:
                continue

            for direction in SEQUENCE_DIRECTIONS:
                if not cache[("category_absorption", direction)][start_idx]:
                    continue

                gap_ok = True
                for gap_step in range(1, 4):
                    gap_idx = positions[start_offset + gap_step]
                    if cache[("category_absorption", direction)][gap_idx]:
                        gap_ok = False
                        break
                if not gap_ok:
                    continue

                end_idx = positions[start_offset + 4]
                if not cache[("category_absorption", direction)][end_idx]:
                    continue
                if not gate[end_idx]:
                    continue

                ret_5b = returns_5b[end_idx]
                if not np.isnan(ret_5b):
                    matched_returns.append(float(ret_5b))
                break

    return matched_returns


def collect_increasing_score_returns(
    df: pd.DataFrame,
    session_positions: list[np.ndarray],
    returns_5b: np.ndarray,
    gate: np.ndarray,
) -> list[float]:
    matched_returns: list[float] = []
    scores = df["score_final_bar"].to_numpy(dtype=float)
    directions = df["direction_sign"].to_numpy(dtype=int)

    for positions in session_positions:
        session_len = len(positions)
        for start_offset in range(session_len - 2):
            idx0 = positions[start_offset]
            idx1 = positions[start_offset + 1]
            idx2 = positions[start_offset + 2]

            if directions[idx0] == 0:
                continue
            if not (directions[idx0] == directions[idx1] == directions[idx2]):
                continue
            if not (scores[idx0] < scores[idx1] < scores[idx2]):
                continue
            if not gate[idx2]:
                continue

            ret_5b = returns_5b[idx2]
            if not np.isnan(ret_5b):
                matched_returns.append(float(ret_5b))

    return matched_returns


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    cache = build_condition_cache(df)
    session_positions = [group.index.to_numpy() for _, group in df.groupby("session_date", sort=False)]
    returns_5b = df["ret_5b_ticks"].to_numpy(dtype=float)
    gate_60m = (df["direction_sign"].ne(0) & df["is_60m_extreme"]).to_numpy(dtype=bool)

    results = [
        summarize_returns(
            "01",
            "A",
            "EXH_03 -> absorption -> TRAP_05 within 5 bars + 60m_extreme",
            collect_three_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "signal_EXH_03",
                "category_absorption",
                "signal_TRAP_05",
                5,
            ),
        ),
        summarize_returns(
            "02",
            "A",
            "DELT_04 -> doji -> engulfing within 5 bars + 60m_extreme",
            collect_three_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "signal_DELT_04",
                "doji",
                "engulfing",
                5,
            ),
        ),
        summarize_returns(
            "03",
            "A",
            "TRAP_04 -> doji -> absorption within 5 bars + 60m_extreme",
            collect_three_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "signal_TRAP_04",
                "doji",
                "category_absorption",
                5,
            ),
        ),
        summarize_returns(
            "04",
            "A",
            "2+ categories -> 3+ categories -> 4+ categories within 3 bars + 60m_extreme",
            collect_three_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "category_ge_2",
                "category_ge_3",
                "category_ge_4",
                3,
            ),
        ),
        summarize_returns(
            "05",
            "A",
            "score < 50 -> score >= 60 -> score >= 70 within 5 bars + 60m_extreme",
            collect_three_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "score_lt_50",
                "score_ge_60",
                "score_ge_70",
                5,
            ),
        ),
        summarize_mask(
            "06",
            "B",
            "strength >= 0.7 + mid_vol + first_hour + 60m_extreme + 15m_trend",
            df[
                df["direction_sign"].ne(0)
                & df["max_strength"].ge(0.7)
                & df["is_mid_vol"]
                & df["is_first_hour"]
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
            ].copy(),
        ),
        summarize_mask(
            "07",
            "B",
            "strength >= 0.7 + mid_vol + NOT lunch + 60m_extreme + 15m_trend",
            df[
                df["direction_sign"].ne(0)
                & df["max_strength"].ge(0.7)
                & df["is_mid_vol"]
                & df["is_not_lunch"]
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
            ].copy(),
        ),
        summarize_mask(
            "08",
            "B",
            "score >= 70 + delta_opposite + first_hour + 60m_extreme + 15m_trend",
            df[
                df["direction_sign"].ne(0)
                & df["score_final_bar"].ge(70)
                & df["is_delta_opposite"]
                & df["is_first_hour"]
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
            ].copy(),
        ),
        summarize_mask(
            "09",
            "B",
            "score >= 70 + delta_opposite + NOT lunch + 60m_extreme + 15m_trend",
            df[
                df["direction_sign"].ne(0)
                & df["score_final_bar"].ge(70)
                & df["is_delta_opposite"]
                & df["is_not_lunch"]
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
            ].copy(),
        ),
        summarize_mask(
            "10",
            "B",
            "score >= 60 + mid_vol + delta_opposite + 60m_extreme + 15m_trend",
            df[
                df["direction_sign"].ne(0)
                & df["score_final_bar"].ge(60)
                & df["is_mid_vol"]
                & df["is_delta_opposite"]
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
            ].copy(),
        ),
        summarize_returns(
            "11",
            "C",
            "absorption -> 3-bar gap with no absorption -> absorption + 60m_extreme",
            collect_gap_absorption_returns(session_positions, cache, returns_5b, gate_60m),
        ),
        summarize_returns(
            "12",
            "C",
            "TRAP_04 on 2 bars within 5 bars + 60m_extreme",
            collect_two_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "signal_TRAP_04",
                "signal_TRAP_04",
                5,
            ),
        ),
        summarize_mask(
            "13",
            "C",
            "3+ different signal_ids on same bar + 60m_extreme + 15m_trend + first_hour",
            df[
                df["direction_sign"].ne(0)
                & df["signal_count"].ge(3)
                & df["is_60m_extreme"]
                & df["is_15m_trend_aligned"]
                & df["is_first_hour"]
            ].copy(),
        ),
        summarize_returns(
            "14",
            "C",
            "TYPE_B -> TYPE_B within 3 bars + 60m_extreme",
            collect_two_step_sequence_returns(
                session_positions,
                cache,
                returns_5b,
                gate_60m,
                "type_b_bar",
                "type_b_bar",
                3,
            ),
        ),
        summarize_returns(
            "15",
            "C",
            "score_final increasing over 3 consecutive bars + 60m_extreme",
            collect_increasing_score_returns(df, session_positions, returns_5b, gate_60m),
        ),
        summarize_mask(
            "16",
            "D",
            "ATR crossed above 50th percentile this bar + 60m_extreme",
            df[df["direction_sign"].ne(0) & df["atr_crossed_above_50pct"] & df["is_60m_extreme"]].copy(),
        ),
        summarize_mask(
            "17",
            "D",
            "ATR crossed below 50th percentile this bar + 60m_extreme",
            df[df["direction_sign"].ne(0) & df["atr_crossed_below_50pct"] & df["is_60m_extreme"]].copy(),
        ),
        summarize_mask(
            "18",
            "D",
            "Session delta flipped sign (CVD crossed zero) + 60m_extreme + 15m_trend",
            df[df["direction_sign"].ne(0) & df["cvd_crossed_zero"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]].copy(),
        ),
        summarize_mask(
            "19",
            "D",
            "Price crossed SMA50 this bar + 60m_extreme",
            df[df["direction_sign"].ne(0) & df["price_crossed_sma50"] & df["is_60m_extreme"]].copy(),
        ),
        summarize_mask(
            "20",
            "D",
            "Prior 10 bars: 7+ same-direction, then current bar opposite + 60m_extreme",
            df[df["direction_sign"].ne(0) & df["is_contrarian_reversal"] & df["is_60m_extreme"]].copy(),
        ),
    ]

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["avg_ticks_5b"]) else float(row["avg_ticks_5b"]),
            float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
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
                f"{row['code']}. [{row['group']}] {row['label']}",
                f"{row['n']:,}",
                fmt_pct(float(row["wr_5b"])),
                fmt_float(float(row["pf_5b"])),
                fmt_float(float(row["avg_ticks_5b"])),
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


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR5={fmt_pct(float(row['wr_5b']))} | PF5={fmt_float(float(row['pf_5b']))} | "
        f"Avg5={fmt_float(float(row['avg_ticks_5b']))}t | CI5={fmt_ci(float(row['ci_low']), float(row['ci_high']))}"
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = compute_bar_features(observations)
    thresholds = compute_thresholds(observations)
    observations = add_context_flags(observations, thresholds)

    non_zero = observations[observations["direction_sign"].ne(0)].copy()
    baseline_all = summarize_returns("00", "BASE", "All non-zero-delta grouped bars", non_zero["ret_5b_ticks"])
    baseline_60m = summarize_returns(
        "00A",
        "BASE",
        "All non-zero-delta grouped bars at 60m_extreme",
        non_zero.loc[non_zero["is_60m_extreme"], "ret_5b_ticks"],
    )
    baseline_60m_15m = summarize_returns(
        "00B",
        "BASE",
        "All non-zero-delta grouped bars at 60m_extreme + 15m_trend",
        non_zero.loc[non_zero["is_60m_extreme"] & non_zero["is_15m_trend_aligned"], "ret_5b_ticks"],
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 11 chain/triple-interaction analysis",
        "===============================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: signal_events rows grouped by (global_index, sign(bar_delta)).",
        "Trade direction for P&L = sign(bar_delta) on the final/matched bar for every filter.",
        "60m_extreme = bullish grouped-bar low in bottom 20% of active 60m range / bearish grouped-bar high in top 20%.",
        "15m_trend = grouped bar_delta sign matches the active 15m open-close sign.",
        f"mid_vol = middle ATR_{ATR_WINDOW} tercile on the grouped observation stream.",
        f"delta_opposite = sign(prior {DELTA_LOOKBACK}-bar grouped delta sum) opposes current bar_delta sign.",
        "first_hour = 09:30-10:29 ET; lunch excluded = 12:00-13:59 ET.",
        "Doji = body/range < 0.10 on the grouped observation stream.",
        "Engulfing = current grouped-bar body fully engulfs the prior grouped-bar body.",
        f"ATR regime transitions use ATR_{ATR_WINDOW} crossing the full-sample 50th percentile threshold.",
        f"SMA trend transition uses grouped-bar close crossing session SMA{SMA_WINDOW}.",
        f"Contrarian filter = prior {CONTRARIAN_LOOKBACK} grouped bars contain >=7 bars in one direction, then current grouped bar flips opposite.",
        "Filter 11 uses an exact 3-bar no-absorption gap before the second absorption bar.",
        "Filter 15 requires strictly increasing grouped-bar score_final over three consecutive grouped bars with the same non-zero bar_delta sign.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "Final ranking is sorted by 5-bar average ticks descending.",
        "",
        f"Raw event rows loaded:                  {len(events):,}",
        f"Grouped observations:                   {len(observations):,}",
        f"Non-zero grouped observations:          {len(non_zero):,}",
        f"15m bars built:                         {len(context[15]):,}",
        f"60m bars built:                         {len(context[60]):,}",
        f"60m extreme grouped observations:       {int(observations['is_60m_extreme'].sum()):,}",
        f"60m + 15m aligned observations:         {int((observations['is_60m_extreme'] & observations['is_15m_trend_aligned']).sum()):,}",
        f"mid_vol grouped observations:           {int(observations['is_mid_vol'].sum()):,}",
        f"delta_opposite grouped observations:    {int(observations['is_delta_opposite'].sum()):,}",
        f"ATR 50th percentile threshold:          {fmt_float(thresholds['atr_50pct'])}",
        "",
        "Baselines",
        "---------",
        f"All non-zero grouped bars:      {render_summary_line(baseline_all)}",
        f"60m_extreme grouped bars:       {render_summary_line(baseline_60m)}",
        f"60m_extreme + 15m_trend bars:   {render_summary_line(baseline_60m_15m)}",
        "",
        "20 requested chain / triple-interaction filters",
        "---------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
