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
OUT_PATH = OUT_DIR / "round7_signal_negation_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
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


@dataclass(frozen=True)
class FilterSpec:
    code: str
    label: str
    valid: Callable[[pd.DataFrame], pd.Series]
    condition: Callable[[pd.DataFrame], pd.Series]


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


def fmt_count(value: int) -> str:
    return f"{value:,}"


def fmt_pct(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value * 100:.1f}%"


def fmt_pp(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value * 100:+.1f}pp"


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
    df = df[df["event_direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_bar_frame(events: pd.DataFrame) -> pd.DataFrame:
    working = events.copy()
    working["is_TYPE_A"] = working["score_tier"].eq("TYPE_A")

    bars = (
        working.groupby("global_index", as_index=False, sort=False)
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
            bar_signal_count=("signal_id", "nunique"),
            bar_category_count=("category", "nunique"),
            bar_has_TYPE_A=("is_TYPE_A", "max"),
            bar_max_score_final=("score_final", "max"),
        )
        .sort_values("global_index", kind="stable")
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
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["ret_5b_ticks"] = observations["direction_sign"] * (
        (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    )
    return observations


def compute_bar_features(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["abs_delta"] = out["bar_delta"].abs()
    out["delta_sign"] = np.sign(out["bar_delta"].fillna(0.0)).astype(int)
    out["price_change"] = out["bar_close"] - out["bar_open"]
    out["price_sign"] = np.sign(out["price_change"].fillna(0.0)).astype(int)

    out["prior_bar_volume"] = by_session["bar_volume"].shift(1)
    out["prior2_bar_volume"] = by_session["bar_volume"].shift(2)
    out["prior_bar_range"] = by_session["bar_range"].shift(1)
    out["prior_delta_sign"] = by_session["delta_sign"].shift(1)
    out["prior2_delta_sign"] = by_session["delta_sign"].shift(2)
    out["prior3_delta_sign"] = by_session["delta_sign"].shift(3)
    out["prior_price_sign"] = by_session["price_sign"].shift(1)
    out["next_delta_sign"] = by_session["delta_sign"].shift(-1)

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["abs_delta_q90"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.90)
    )
    out["range_q75"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    out["prior_range_q75"] = by_session["range_q75"].shift(1)
    out["prior_5bar_cum_delta"] = by_session["bar_delta"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=5).sum()
    )

    out["volume_context_valid"] = out["rolling_20_ema_vol"].gt(0)
    out["is_volume_spike_3x"] = out["volume_context_valid"] & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["prior1_is_volume_spike_3x"] = by_session["is_volume_spike_3x"].shift(1)
    out["prior2_is_volume_spike_3x"] = by_session["is_volume_spike_3x"].shift(2)
    out["prior3_is_volume_spike_3x"] = by_session["is_volume_spike_3x"].shift(3)
    out["prior1_volume_context_valid"] = by_session["volume_context_valid"].shift(1)
    out["prior2_volume_context_valid"] = by_session["volume_context_valid"].shift(2)
    out["prior3_volume_context_valid"] = by_session["volume_context_valid"].shift(3)
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


def build_session_reference(bars_1m: pd.DataFrame) -> pd.DataFrame:
    session_open = bars_1m.loc[
        bars_1m["ts_event"].dt.hour.eq(9) & bars_1m["ts_event"].dt.minute.eq(30),
        ["ts_event", "open"],
    ].copy()
    session_open["session_date"] = session_open["ts_event"].dt.strftime("%Y-%m-%d")
    return session_open.rename(columns={"open": "session_open_price"})[["session_date", "session_open_price"]]


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


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["anchor_pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["close_pos_60m"] = (out["bar_close"] - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["anchor_pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["anchor_pos_60m"].ge(0.80))
    )
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] - 9) * 60 + out["minute"] - 30
    out["is_lunch"] = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_last_15m"] = out["minutes_since_930"].ge(375) & out["minutes_since_930"].lt(390)
    out["is_first_5m"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(5)
    out["is_fomc_day"] = out["session_date"].isin(FOMC_DATES)
    return out


def add_signal_conflict_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["has_opposite_direction_same_bar"] = out.groupby("global_index")["direction_sign"].transform("nunique").gt(1)

    session_maps: dict[str, dict[int, dict[int, set[str]]]] = {}
    for row in out[["session_date", "signal_bar_seq", "direction_sign", "signal_ids"]].itertuples(index=False):
        session_map = session_maps.setdefault(str(row.session_date), {})
        seq_map = session_map.setdefault(int(row.signal_bar_seq), {})
        seq_map[int(row.direction_sign)] = set(row.signal_ids)

    flags: list[bool] = []
    for row in out[["session_date", "signal_bar_seq", "direction_sign", "signal_ids"]].itertuples(index=False):
        session_map = session_maps.get(str(row.session_date), {})
        current_ids = set(row.signal_ids)
        opposite_direction = -int(row.direction_sign)
        found_match = False
        for lag in (1, 2, 3):
            prior_ids = session_map.get(int(row.signal_bar_seq) - lag, {}).get(opposite_direction)
            if prior_ids and current_ids.intersection(prior_ids):
                found_match = True
                break
        flags.append(found_match)

    out["has_same_signal_opposite_within_3"] = flags
    return out


def build_analysis_frame(events: pd.DataFrame, bars_1m: pd.DataFrame) -> pd.DataFrame:
    bars = build_bar_frame(events)
    bar_features = compute_bar_features(bars)
    observations = build_signal_observations(events)
    context = build_timeframe_context(bars_1m)
    session_ref = build_session_reference(bars_1m)

    feature_cols = [
        "global_index",
        "signal_bar_seq",
        "bar_delta",
        "bar_volume",
        "bar_signal_count",
        "bar_category_count",
        "bar_has_TYPE_A",
        "bar_max_score_final",
        "bar_range",
        "abs_delta",
        "delta_sign",
        "price_sign",
        "prior_bar_volume",
        "prior2_bar_volume",
        "prior_bar_range",
        "prior_delta_sign",
        "prior2_delta_sign",
        "prior3_delta_sign",
        "prior_price_sign",
        "next_delta_sign",
        "rolling_20_ema_vol",
        "abs_delta_q90",
        "range_q75",
        "prior_range_q75",
        "prior_5bar_cum_delta",
        "volume_context_valid",
        "is_volume_spike_3x",
        "prior1_is_volume_spike_3x",
        "prior2_is_volume_spike_3x",
        "prior3_is_volume_spike_3x",
        "prior1_volume_context_valid",
        "prior2_volume_context_valid",
        "prior3_volume_context_valid",
    ]
    observations = observations.merge(
        bar_features[feature_cols],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_context(observations, context)
    observations = observations.merge(session_ref, on="session_date", how="left", validate="many_to_one")
    observations = add_context_flags(observations)
    observations = add_time_flags(observations)
    observations = add_signal_conflict_flags(observations)

    observations["directional_move_from_open_ticks"] = observations["direction_sign"] * (
        (observations["bar_close"] - observations["session_open_price"]) / TICK_SIZE
    )
    return observations


def summarize_sample(df: pd.DataFrame) -> dict[str, float | int]:
    returns = df["ret_5b_ticks"].dropna()
    n = int(len(returns))
    wr = float((returns > 0).mean()) if n else float("nan")
    return {"n": n, "wr": wr}


def build_filter_specs() -> list[FilterSpec]:
    return [
        FilterSpec(
            "01",
            "volume spike > 3x EMA",
            valid=lambda df: df["volume_context_valid"],
            condition=lambda df: df["bar_volume"].gt(3.0 * df["rolling_20_ema_vol"]),
        ),
        FilterSpec(
            "02",
            "volume < 0.3x EMA",
            valid=lambda df: df["volume_context_valid"],
            condition=lambda df: df["bar_volume"].lt(0.3 * df["rolling_20_ema_vol"]),
        ),
        FilterSpec(
            "03",
            "declining volume over 3 signal bars",
            valid=lambda df: df["prior_bar_volume"].notna() & df["prior2_bar_volume"].notna(),
            condition=lambda df: df["prior2_bar_volume"].gt(df["prior_bar_volume"]) & df["prior_bar_volume"].gt(df["bar_volume"]),
        ),
        FilterSpec(
            "04",
            "volume spike on opposite-direction bar in prior 3 signal bars",
            valid=lambda df: df["prior1_volume_context_valid"].fillna(False)
            & df["prior2_volume_context_valid"].fillna(False)
            & df["prior3_volume_context_valid"].fillna(False),
            condition=lambda df: (
                df["prior1_is_volume_spike_3x"].fillna(False) & df["prior_delta_sign"].eq(-df["direction_sign"])
            )
            | (
                df["prior2_is_volume_spike_3x"].fillna(False) & df["prior2_delta_sign"].eq(-df["direction_sign"])
            )
            | (
                df["prior3_is_volume_spike_3x"].fillna(False) & df["prior3_delta_sign"].eq(-df["direction_sign"])
            ),
        ),
        FilterSpec(
            "05",
            "bar_delta same direction and > 90th percentile",
            valid=lambda df: df["abs_delta_q90"].notna(),
            condition=lambda df: df["delta_sign"].eq(df["direction_sign"]) & df["abs_delta"].gt(df["abs_delta_q90"]),
        ),
        FilterSpec(
            "06",
            "prior 5-bar cumulative delta same as signal",
            valid=lambda df: df["prior_5bar_cum_delta"].notna(),
            condition=lambda df: pd.Series(
                np.sign(df["prior_5bar_cum_delta"]),
                index=df.index,
            ).fillna(0).astype(int).eq(df["direction_sign"]),
        ),
        FilterSpec(
            "07",
            "next-bar delta flips opposite signal",
            valid=lambda df: df["next_delta_sign"].notna(),
            condition=lambda df: df["next_delta_sign"].eq(-df["direction_sign"]),
        ),
        FilterSpec(
            "08",
            "3 consecutive same-delta bars before signal",
            valid=lambda df: df["prior_delta_sign"].notna() & df["prior2_delta_sign"].notna() & df["prior3_delta_sign"].notna(),
            condition=lambda df: df["prior_delta_sign"].eq(df["direction_sign"])
            & df["prior2_delta_sign"].eq(df["direction_sign"])
            & df["prior3_delta_sign"].eq(df["direction_sign"]),
        ),
        FilterSpec(
            "09",
            "wide range bar > 75th percentile",
            valid=lambda df: df["range_q75"].notna(),
            condition=lambda df: df["bar_range"].gt(df["range_q75"]),
        ),
        FilterSpec(
            "10",
            "price already moved > 50 ticks from session open in signal direction",
            valid=lambda df: df["session_open_price"].notna(),
            condition=lambda df: df["directional_move_from_open_ticks"].gt(50.0),
        ),
        FilterSpec(
            "11",
            "signal closes in middle 40-60% of 60m range",
            valid=lambda df: df["close_pos_60m"].notna(),
            condition=lambda df: df["close_pos_60m"].between(0.40, 0.60, inclusive="both"),
        ),
        FilterSpec(
            "12",
            "prior bar was strong momentum bar",
            valid=lambda df: df["prior_bar_range"].notna()
            & df["prior_range_q75"].notna()
            & df["prior_delta_sign"].notna()
            & df["prior_price_sign"].notna(),
            condition=lambda df: df["prior_bar_range"].gt(df["prior_range_q75"])
            & df["prior_delta_sign"].eq(df["direction_sign"])
            & df["prior_price_sign"].eq(df["direction_sign"]),
        ),
        FilterSpec(
            "13",
            "lunch hour (12:00-14:00)",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["is_lunch"],
        ),
        FilterSpec(
            "14",
            "last 15 minutes (15:45-16:00)",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["is_last_15m"],
        ),
        FilterSpec(
            "15",
            "first 5 minutes (09:30-09:35)",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["is_first_5m"],
        ),
        FilterSpec(
            "16",
            "FOMC day",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["is_fomc_day"],
        ),
        FilterSpec(
            "17",
            "opposite-direction signal also fired on same bar",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["has_opposite_direction_same_bar"],
        ),
        FilterSpec(
            "18",
            "same signal_id fired opposite direction within prior 3 signal bars",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["has_same_signal_opposite_within_3"],
        ),
        FilterSpec(
            "19",
            "TYPE_A signal present on same bar",
            valid=lambda df: pd.Series(True, index=df.index),
            condition=lambda df: df["bar_has_TYPE_A"],
        ),
        FilterSpec(
            "20",
            "score_final < 40 on same bar",
            valid=lambda df: df["bar_max_score_final"].notna(),
            condition=lambda df: df["bar_max_score_final"].lt(40.0),
        ),
    ]


def evaluate_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    base_mask = df["is_60m_extreme"] & df["is_15m_trend_aligned"]
    results: list[dict[str, object]] = []

    for spec in build_filter_specs():
        valid_mask = base_mask & spec.valid(df).fillna(False).astype(bool)
        condition_mask = spec.condition(df).fillna(False).astype(bool)

        with_sample = summarize_sample(df[valid_mask & condition_mask].copy())
        without_sample = summarize_sample(df[valid_mask & ~condition_mask].copy())
        delta_wr = float(with_sample["wr"] - without_sample["wr"]) if not pd.isna(with_sample["wr"]) and not pd.isna(without_sample["wr"]) else float("nan")

        results.append(
            {
                "code": spec.code,
                "label": spec.label,
                "eligible_n": int(valid_mask.sum()),
                "with_n": int(with_sample["n"]),
                "with_wr": float(with_sample["wr"]),
                "without_n": int(without_sample["n"]),
                "without_wr": float(without_sample["wr"]),
                "delta_wr": delta_wr,
                "verdict": "KILLER" if not pd.isna(delta_wr) and delta_wr < -0.05 else "",
            }
        )

    return results


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Filter", "N with", "WR with", "N without", "WR without", "Delta WR", "Verdict"]
    data_rows: list[list[str]] = []

    for row in rows:
        data_rows.append(
            [
                f"{row['code']}. {row['label']}",
                fmt_count(int(row["with_n"])),
                fmt_pct(float(row["with_wr"])),
                fmt_count(int(row["without_n"])),
                fmt_pct(float(row["without_wr"])),
                fmt_pp(float(row["delta_wr"])),
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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    analysis = build_analysis_frame(events, bars_1m)

    base_mask = analysis["is_60m_extreme"] & analysis["is_15m_trend_aligned"]
    base_sample = summarize_sample(analysis[base_mask].copy())
    results = evaluate_filters(analysis)
    killers = [f"{row['code']}. {row['label']}" for row in results if row["verdict"] == "KILLER"]

    lines = [
        "DEEP6 Round 7 signal negation analysis",
        "====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal observation grouped by global_index + direction_sign.",
        "Base mask: is_60m_extreme & is_15m_trend_aligned.",
        "WITH vs WITHOUT partitions are computed only on base rows where each anti-pattern can actually be evaluated.",
        "Delta WR = WR(with condition) - WR(without condition). KILLER = delta worse than -5 percentage points.",
        "Prior-bar sequence features follow the round2_novel_bar_patterns.py signal-bar pattern.",
        "FOMC dates copied from analyze_absorption_calendar.py.",
        "",
        f"Raw event rows loaded:      {len(events):,}",
        f"Signal observations:        {len(analysis):,}",
        f"Base observations:          {int(base_mask.sum()):,}",
        f"Base anchor WR:             {fmt_pct(float(base_sample['wr']))}",
        "",
        "20 anti-pattern filters",
        "-----------------------",
    ]
    lines.extend(render_table(results))
    lines.extend(
        [
            "",
            f"KILLER count: {len(killers)}",
            "KILLER filters:" if killers else "KILLER filters: none",
        ]
    )
    if killers:
        lines.extend(f"- {item}" for item in killers)

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
