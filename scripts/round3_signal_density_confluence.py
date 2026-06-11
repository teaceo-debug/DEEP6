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
OUT_PATH = OUT_DIR / "round3_signal_density_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 15, 30)
TICK_SIZE = 0.25


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
        "direction": "string",
        "score_tier": "string",
        "bar_index": "int32",
        "global_index": "int32",
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
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)
    numeric_cols = [
        "strength",
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    for window in FORWARD_WINDOWS:
        observations[f"ret_{window}b_ticks"] = observations["direction_sign"] * (
            (observations[f"fwd_close_{window}b"] - observations["bar_close"]) / TICK_SIZE
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

    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def add_stack_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & (out["pos_60m"] <= 0.20))
        | ((out["direction_sign"] < 0) & (out["pos_60m"] >= 0.80))
    )
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


def build_filter_specs() -> list[tuple[str, str, object]]:
    def base_mask(df: pd.DataFrame) -> pd.Series:
        return df["is_60m_extreme"] & df["is_15m_trend_aligned"]

    return [
        ("01", "2+ categories + 60m_extreme + 15m_trend_aligned", lambda df: df["category_count"].ge(2) & base_mask(df)),
        ("02", "3+ categories + 60m_extreme + 15m_trend_aligned", lambda df: df["category_count"].ge(3) & base_mask(df)),
        ("03", "4+ categories + 60m_extreme + 15m_trend_aligned", lambda df: df["category_count"].ge(4) & base_mask(df)),
        ("04", "5+ categories + 60m_extreme + 15m_trend_aligned", lambda df: df["category_count"].ge(5) & base_mask(df)),
        ("05", "3+ signals + 60m_extreme + 15m_trend_aligned", lambda df: df["signal_count"].ge(3) & base_mask(df)),
        ("06", "5+ signals + 60m_extreme + 15m_trend_aligned", lambda df: df["signal_count"].ge(5) & base_mask(df)),
        ("07", "7+ signals + 60m_extreme + 15m_trend_aligned", lambda df: df["signal_count"].ge(7) & base_mask(df)),
        ("08", "10+ signals + 60m_extreme + 15m_trend_aligned", lambda df: df["signal_count"].ge(10) & base_mask(df)),
        ("09", "score >= 50 + 60m_extreme + 15m_trend_aligned", lambda df: df["max_score_final"].ge(50) & base_mask(df)),
        ("10", "score >= 60 + 60m_extreme + 15m_trend_aligned", lambda df: df["max_score_final"].ge(60) & base_mask(df)),
        ("11", "score >= 70 + 60m_extreme + 15m_trend_aligned", lambda df: df["max_score_final"].ge(70) & base_mask(df)),
        ("12", "score >= 80 + 60m_extreme + 15m_trend_aligned", lambda df: df["max_score_final"].ge(80) & base_mask(df)),
        ("13", "score >= 90 + 60m_extreme + 15m_trend_aligned", lambda df: df["max_score_final"].ge(90) & base_mask(df)),
        (
            "14",
            "3+ categories + 60m_extreme + 15m_trend_aligned + first_hour",
            lambda df: df["category_count"].ge(3) & base_mask(df) & df["is_first_hour"],
        ),
        (
            "15",
            "score >= 60 + 60m_extreme + 15m_trend_aligned + first_hour",
            lambda df: df["max_score_final"].ge(60) & base_mask(df) & df["is_first_hour"],
        ),
        (
            "16",
            "5+ signals + 60m_extreme + 15m_trend_aligned + first_hour",
            lambda df: df["signal_count"].ge(5) & base_mask(df) & df["is_first_hour"],
        ),
        (
            "17",
            "3+ categories + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["category_count"].ge(3) & base_mask(df) & df["is_not_lunch"],
        ),
        (
            "18",
            "score >= 60 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["max_score_final"].ge(60) & base_mask(df) & df["is_not_lunch"],
        ),
        (
            "19",
            "score >= 70 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["max_score_final"].ge(70) & base_mask(df) & df["is_not_lunch"],
        ),
        (
            "20",
            "5+ signals + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["signal_count"].ge(5) & base_mask(df) & df["is_not_lunch"],
        ),
    ]


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict:
    required_cols = [f"ret_{window}b_ticks" for window in FORWARD_WINDOWS]
    sample = df.dropna(subset=required_cols).copy()
    n = int(len(sample))
    win_rates: dict[int, float] = {window: np.nan for window in FORWARD_WINDOWS}

    for window in FORWARD_WINDOWS:
        returns = sample[f"ret_{window}b_ticks"]
        wins = int((returns > 0).sum())
        win_rates[window] = (wins / n) if n else np.nan

    returns_5b = sample["ret_5b_ticks"]
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b if n else np.nan,
        "wr_10b": win_rates[10],
        "wr_15b": win_rates[15],
        "wr_30b": win_rates[30],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b if n else np.nan, win_rates[30]),
    }


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy()))
    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["wr_30b"]) else float(row["wr_30b"]),
            float("-inf") if pd.isna(row["wr_15b"]) else float(row["wr_15b"]),
            float("-inf") if pd.isna(row["wr_10b"]) else float(row["wr_10b"]),
            float("-inf") if pd.isna(row["wr_5b"]) else float(row["wr_5b"]),
            int(row["n"]),
        ),
        reverse=True,
    )
    return results


def render_table(rows: list[dict]) -> list[str]:
    headers = [
        "Filter",
        "N",
        "WR 5b",
        "WR 10b",
        "WR 15b",
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
                f"{row['code']}. {row['label']}",
                f"{row['n']:,}",
                fmt_pct(row["wr_5b"]),
                fmt_pct(row["wr_10b"]),
                fmt_pct(row["wr_15b"]),
                fmt_pct(row["wr_30b"]),
                fmt_float(row["pf_5b"]),
                fmt_float(row["avg_ticks_5b"]),
                fmt_ci(row["ci_low"], row["ci_high"]),
                row["persistence"],
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
    observations = add_stack_flags(observations)
    observations = add_time_flags(observations)
    results = run_filters(observations)

    base_mask = observations["is_60m_extreme"] & observations["is_15m_trend_aligned"]

    lines = [
        "DEEP6 round3 signal density + confluence threshold analysis",
        "========================================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation.",
        "N uses rows with complete 5b/10b/15b/30b forward closes so persistence compares the same sample across windows.",
        "category_count = grouped unique category count; signal_count = grouped unique signal_id count; score = grouped max score_final.",
        "Base stack = 60m_extreme + 15m_trend_aligned.",
        "15m_trend_aligned = signal direction matches 15m bar sign; 60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "Time filters use America/New_York. first_hour = 09:30-10:30. lunch = 12:00-14:00, so NOT lunch excludes that window.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "Sorted by 30b win rate descending.",
        "",
        f"Raw event rows loaded:          {len(events):,}",
        f"Grouped observations:           {len(observations):,}",
        f"15m bars built:                 {len(context[15]):,}",
        f"60m bars built:                 {len(context[60]):,}",
        f"15m trend aligned observations: {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme observations:       {int(observations['is_60m_extreme'].sum()):,}",
        f"Base stack observations:        {int(base_mask.sum()):,}",
        "",
        "20 requested density / confluence filters ranked by 30b win rate",
        "--------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
