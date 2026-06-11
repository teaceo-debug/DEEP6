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
OUT_PATH = OUT_DIR / "round6_multi_session_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
LARGE_GAP_TICKS = 50
SMALL_GAP_TICKS = 10
NEAR_PRIOR_VWAP_TICKS = 20
FAR_PRIOR_CLOSE_TICKS = 100


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
    df["direction_sign"] = np.sign(df["bar_delta"].fillna(0.0)).astype(int)
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_unique_bars(events: pd.DataFrame) -> pd.DataFrame:
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
    bars["direction_sign"] = np.sign(bars["bar_delta"].fillna(0.0)).astype(int)
    bars["ret_5b_ticks"] = bars["direction_sign"] * ((bars["fwd_close_5b"] - bars["bar_close"]) / TICK_SIZE)
    return bars


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    observations = (
        events.loc[events["direction_sign"].ne(0)]
        .groupby(["global_index", "direction_sign"], as_index=False, sort=False)
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
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    observations["direction"] = np.where(observations["direction_sign"] > 0, "BULLISH", "BEARISH")
    observations["ret_5b_ticks"] = observations["direction_sign"] * (
        (observations["fwd_close_5b"] - observations["bar_close"]) / TICK_SIZE
    )
    return observations


def build_session_summary(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    working = bars.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    working["bar_pv"] = working["bar_close"] * working["bar_volume"]

    summary = (
        working.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_open=("bar_open", "first"),
            session_high=("bar_high", "max"),
            session_low=("bar_low", "min"),
            session_close=("bar_close", "last"),
            session_delta=("bar_delta", "sum"),
            session_volume=("bar_volume", "sum"),
            session_pv=("bar_pv", "sum"),
            session_bar_count=("global_index", "count"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    summary["session_range"] = summary["session_high"] - summary["session_low"]
    summary["session_vwap"] = np.where(
        summary["session_volume"] > 0,
        summary["session_pv"] / summary["session_volume"],
        np.nan,
    )
    summary["session_day_sign"] = np.sign(summary["session_close"] - summary["session_open"]).astype(int)
    summary["session_close_vs_open"] = np.select(
        [summary["session_day_sign"] > 0, summary["session_day_sign"] < 0],
        ["bullish", "bearish"],
        default="flat",
    )

    shift_cols = [
        "session_open",
        "session_high",
        "session_low",
        "session_close",
        "session_range",
        "session_delta",
        "session_volume",
        "session_vwap",
        "session_day_sign",
        "session_close_vs_open",
        "session_bar_count",
    ]
    for col in shift_cols:
        summary[f"prior_{col}"] = summary[col].shift(1)

    thresholds = {
        "range_q25": float(summary["session_range"].quantile(0.25)),
        "range_q75": float(summary["session_range"].quantile(0.75)),
        "delta_q25": float(summary["session_delta"].quantile(0.25)),
        "delta_q75": float(summary["session_delta"].quantile(0.75)),
    }
    return summary, thresholds


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
    return df


def attach_session_context(
    observations: pd.DataFrame,
    bars: pd.DataFrame,
    session_summary: pd.DataFrame,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    running = bars.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    by_session = running.groupby("session_date", sort=False)
    running["developing_session_high"] = by_session["bar_high"].cummax()
    running["developing_session_low"] = by_session["bar_low"].cummin()
    running["developing_session_range"] = running["developing_session_high"] - running["developing_session_low"]
    running["developing_session_pos"] = np.where(
        running["developing_session_range"] > 0,
        (running["bar_close"] - running["developing_session_low"]) / running["developing_session_range"],
        np.nan,
    )

    session_cols = [
        "session_date",
        "session_open",
        "session_high",
        "session_low",
        "session_close",
        "session_range",
        "session_delta",
        "session_volume",
        "session_vwap",
        "session_close_vs_open",
        "prior_session_open",
        "prior_session_high",
        "prior_session_low",
        "prior_session_close",
        "prior_session_range",
        "prior_session_delta",
        "prior_session_volume",
        "prior_session_vwap",
        "prior_session_day_sign",
        "prior_session_close_vs_open",
        "prior_session_bar_count",
    ]
    running_cols = [
        "global_index",
        "developing_session_high",
        "developing_session_low",
        "developing_session_range",
        "developing_session_pos",
    ]

    df = observations.merge(session_summary[session_cols], on="session_date", how="left", validate="many_to_one")
    df = df.merge(running[running_cols], on="global_index", how="left", validate="many_to_one")

    df["gap_from_prior_close_ticks"] = (df["session_open"] - df["prior_session_close"]).abs() / TICK_SIZE
    df["is_gap_up"] = df["session_open"] > df["prior_session_high"]
    df["is_gap_down"] = df["session_open"] < df["prior_session_low"]
    df["is_large_gap"] = df["gap_from_prior_close_ticks"] > LARGE_GAP_TICKS
    df["is_small_gap"] = df["gap_from_prior_close_ticks"] < SMALL_GAP_TICKS

    df["prior_session_is_wide_range"] = df["prior_session_range"] >= thresholds["range_q75"]
    df["prior_session_is_narrow_range"] = df["prior_session_range"] <= thresholds["range_q25"]
    df["prior_session_large_positive_delta"] = df["prior_session_delta"] >= thresholds["delta_q75"]
    df["prior_session_large_negative_delta"] = df["prior_session_delta"] <= thresholds["delta_q25"]

    df["prior_session_delta_sign"] = np.sign(df["prior_session_delta"].fillna(0.0)).astype(int)
    delta_relation = df["prior_session_delta_sign"] * df["direction_sign"]
    df["prior_delta_opposes_signal"] = delta_relation < 0
    df["prior_delta_matches_signal"] = delta_relation > 0

    df["is_first_20pct_developing_range"] = df["developing_session_pos"] <= 0.20
    df["is_last_20pct_developing_range"] = df["developing_session_pos"] >= 0.80

    df["dist_prior_session_vwap_ticks"] = (df["bar_close"] - df["prior_session_vwap"]).abs() / TICK_SIZE
    df["dist_prior_session_close_ticks"] = (df["bar_close"] - df["prior_session_close"]).abs() / TICK_SIZE
    df["is_near_prior_session_vwap"] = df["dist_prior_session_vwap_ticks"] < NEAR_PRIOR_VWAP_TICKS
    df["is_far_from_prior_session_close"] = df["dist_prior_session_close_ticks"] > FAR_PRIOR_CLOSE_TICKS
    return df


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
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


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict[str, object]:
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
        "ci_low": ci_low,
        "ci_high": ci_high,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "Gap up above prior high + 60m_extreme", lambda df: df["is_gap_up"] & df["is_60m_extreme"]),
        ("02", "Gap down below prior low + 60m_extreme", lambda df: df["is_gap_down"] & df["is_60m_extreme"]),
        ("03", "Large gap (>50 ticks from prior close) + 60m_extreme", lambda df: df["is_large_gap"] & df["is_60m_extreme"]),
        ("04", "Small/no gap (<10 ticks from prior close) + 60m_extreme", lambda df: df["is_small_gap"] & df["is_60m_extreme"]),
        (
            "05",
            "Gap up above prior high + 60m_extreme + 15m trend aligned",
            lambda df: df["is_gap_up"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "06",
            "Gap down below prior low + 60m_extreme + 15m trend aligned",
            lambda df: df["is_gap_down"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "07",
            "Prior session wide range (top quartile) + 60m_extreme",
            lambda df: df["prior_session_is_wide_range"] & df["is_60m_extreme"],
        ),
        (
            "08",
            "Prior session narrow range (bottom quartile) + 60m_extreme",
            lambda df: df["prior_session_is_narrow_range"] & df["is_60m_extreme"],
        ),
        (
            "09",
            "Prior session bullish + bearish signal today + 60m_extreme",
            lambda df: (df["prior_session_day_sign"] > 0) & (df["direction_sign"] < 0) & df["is_60m_extreme"],
        ),
        (
            "10",
            "Prior session bearish + bullish signal today + 60m_extreme",
            lambda df: (df["prior_session_day_sign"] < 0) & (df["direction_sign"] > 0) & df["is_60m_extreme"],
        ),
        (
            "11",
            "Prior session wide range (top quartile) + 60m_extreme + 15m trend aligned",
            lambda df: df["prior_session_is_wide_range"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "12",
            "Prior session narrow range (bottom quartile) + 60m_extreme + 15m trend aligned",
            lambda df: df["prior_session_is_narrow_range"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "13",
            "Prior session large positive delta + 60m_extreme",
            lambda df: df["prior_session_large_positive_delta"] & df["is_60m_extreme"],
        ),
        (
            "14",
            "Prior session large negative delta + 60m_extreme",
            lambda df: df["prior_session_large_negative_delta"] & df["is_60m_extreme"],
        ),
        (
            "15",
            "Prior delta opposes today's signal direction + 60m_extreme",
            lambda df: df["prior_delta_opposes_signal"] & df["is_60m_extreme"],
        ),
        (
            "16",
            "Prior delta matches today's signal direction + 60m_extreme",
            lambda df: df["prior_delta_matches_signal"] & df["is_60m_extreme"],
        ),
        (
            "17",
            "Signal close in first 20% of today's developing range + 60m_extreme",
            lambda df: df["is_first_20pct_developing_range"] & df["is_60m_extreme"],
        ),
        (
            "18",
            "Signal close in last 20% of today's developing range + 60m_extreme",
            lambda df: df["is_last_20pct_developing_range"] & df["is_60m_extreme"],
        ),
        (
            "19",
            "Signal close within 20 ticks of prior session VWAP + 60m_extreme",
            lambda df: df["is_near_prior_session_vwap"] & df["is_60m_extreme"],
        ),
        (
            "20",
            "Signal close >100 ticks from prior session close + 60m_extreme",
            lambda df: df["is_far_from_prior_session_close"] & df["is_60m_extreme"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
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


def render_table(rows: list[dict[str, object]]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "PF", "Avg Ticks", "Wilson 95% CI"]
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
                fmt_ticks(row["avg_return_5b_ticks"]),
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
    unique_bars = build_unique_bars(events)
    observations = build_observations(events)
    session_summary, thresholds = build_session_summary(unique_bars)
    context = build_timeframe_context(bars_1m)

    observations = attach_timeframe_context(observations, context)
    observations = attach_session_context(observations, unique_bars, session_summary, thresholds)
    observations = add_context_flags(observations)

    baseline_all = summarize_filter("00", "All non-zero-delta grouped signal bars", observations)
    baseline_prior = summarize_filter(
        "00A",
        "All bars with prior-session context",
        observations[observations["prior_session_close"].notna()].copy(),
    )
    baseline_60m = summarize_filter(
        "00B",
        "All bars at 60m extreme",
        observations[observations["is_60m_extreme"]].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round 6 multi-session analysis",
        "====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: grouped signal bar by (global_index, direction_sign from bar_delta).",
        "Session summary source: unique signal bars deduplicated by global_index before daily aggregation.",
        "Forward P&L window: 5 bars, signed by bar_delta direction.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m trend aligned = bar_delta sign matches the 15m open-close sign.",
        "Developing range location uses bar_close within the running session low/high from signal bars.",
        "Near prior VWAP uses prior session VWAP from close*volume / volume on unique signal bars.",
        "Wide/narrow prior session = top/bottom quartile of session range across all sessions.",
        "Large positive/negative prior delta = top/bottom quartile of session delta across all sessions.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:            {len(events):,}",
        f"Unique bars loaded:               {len(unique_bars):,}",
        f"Grouped observations:             {len(observations):,}",
        f"Sessions summarized:              {len(session_summary):,}",
        f"Observations with prior session:  {int(observations['prior_session_close'].notna().sum()):,}",
        f"15m bars built:                   {len(context[15]):,}",
        f"60m bars built:                   {len(context[60]):,}",
        f"60m extreme observations:         {int(observations['is_60m_extreme'].sum()):,}",
        f"15m trend aligned observations:   {int(observations['is_15m_trend_aligned'].sum()):,}",
        "",
        "Cross-session thresholds",
        "------------------------",
        f"Wide range q75:        {fmt_float(thresholds['range_q75'])}",
        f"Narrow range q25:      {fmt_float(thresholds['range_q25'])}",
        f"Large positive delta:  {fmt_float(thresholds['delta_q75'])}",
        f"Large negative delta:  {fmt_float(thresholds['delta_q25'])}",
        "",
        f"Baselines ({FORWARD_WINDOW}-bar window)",
        "--------------------------",
        f"All bars:               N={baseline_all['n']:,} | WR={fmt_pct(baseline_all['win_rate'])} | PF={fmt_float(baseline_all['profit_factor'])} | Avg={fmt_ticks(baseline_all['avg_return_5b_ticks'])} | CI={fmt_ci(baseline_all['ci_low'], baseline_all['ci_high'])}",
        f"Prior-session ready:    N={baseline_prior['n']:,} | WR={fmt_pct(baseline_prior['win_rate'])} | PF={fmt_float(baseline_prior['profit_factor'])} | Avg={fmt_ticks(baseline_prior['avg_return_5b_ticks'])} | CI={fmt_ci(baseline_prior['ci_low'], baseline_prior['ci_high'])}",
        f"60m extreme:            N={baseline_60m['n']:,} | WR={fmt_pct(baseline_60m['win_rate'])} | PF={fmt_float(baseline_60m['profit_factor'])} | Avg={fmt_ticks(baseline_60m['avg_return_5b_ticks'])} | CI={fmt_ci(baseline_60m['ci_low'], baseline_60m['ci_high'])}",
        "",
        "All 20 cross-session filters ranked by 5-bar average return",
        "----------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
