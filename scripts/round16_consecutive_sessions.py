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
OUT_PATH = OUT_DIR / "round16_consecutive_sessions_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60


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


def render_summary_line(row: dict[str, object]) -> str:
    return (
        f"N={int(row['n']):,} | WR={fmt_pct(float(row['win_rate']))} | PF={fmt_float(float(row['profit_factor']))} | "
        f"Avg={fmt_ticks(float(row['avg_return_5b_ticks']))} | CI={fmt_ci(float(row['ci_low']), float(row['ci_high']))}"
    )


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
    return df.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


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

    for col in ["bar_open", "bar_high", "bar_low", "bar_close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.reset_index(drop=True)


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    out = observations.copy()
    by_session = out.groupby("session_date", sort=False)
    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    return out


def add_context_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["is_15m_trend_aligned"] = out["direction_sign"].eq(out["trend_sign_15m"])

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], np.where(out["direction_sign"] < 0, out["bar_high"], np.nan))
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & out["pos_60m"].le(0.20))
        | ((out["direction_sign"] < 0) & out["pos_60m"].ge(0.80))
    )
    out["has_core_60m_15m_gate"] = out["is_60m_extreme"] & out["is_15m_trend_aligned"]

    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])
    out["is_killer_1"] = out["pos_60m"].between(0.40, 0.60, inclusive="both")
    out["is_killer_2"] = out["is_volume_spike_3x"]
    out["passes_not_all_killers"] = (~out["is_killer_1"]) & (~out["is_killer_2"])

    bool_cols = [
        "is_15m_trend_aligned",
        "is_60m_extreme",
        "has_core_60m_15m_gate",
        "is_volume_spike_3x",
        "is_killer_1",
        "is_killer_2",
        "passes_not_all_killers",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)
    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    return out


def add_session_rollups(summary: pd.DataFrame) -> pd.DataFrame:
    out = summary.sort_values("session_start_ts", kind="stable").reset_index(drop=True).copy()
    out["session_weekday"] = out["session_start_ts"].dt.dayofweek
    out["session_weekday_name"] = out["session_start_ts"].dt.day_name()
    out["session_has_qualifying"] = out["session_qualifying_count"].gt(0)
    out["session_is_winning"] = out["session_has_qualifying"] & out["session_avg_ret_5b_ticks"].gt(0)
    out["session_is_losing"] = out["session_has_qualifying"] & out["session_avg_ret_5b_ticks"].le(0)

    ending_win_streak: list[int] = []
    ending_loss_streak: list[int] = []
    current_win_streak = 0
    current_loss_streak = 0

    for is_winning, is_losing in zip(out["session_is_winning"], out["session_is_losing"]):
        if bool(is_winning):
            current_win_streak += 1
            current_loss_streak = 0
        elif bool(is_losing):
            current_loss_streak += 1
            current_win_streak = 0
        else:
            current_win_streak = 0
            current_loss_streak = 0
        ending_win_streak.append(current_win_streak)
        ending_loss_streak.append(current_loss_streak)

    out["ending_win_streak"] = np.array(ending_win_streak, dtype="int32")
    out["ending_loss_streak"] = np.array(ending_loss_streak, dtype="int32")

    out["prior_session_date"] = out["session_date"].shift(1)
    out["prior_session_weekday"] = out["session_weekday"].shift(1)
    out["prior_session_weekday_name"] = out["session_weekday_name"].shift(1)
    out["prior_session_qualifying_count"] = out["session_qualifying_count"].shift(1)
    out["prior_session_avg_ret_5b_ticks"] = out["session_avg_ret_5b_ticks"].shift(1)
    out["prior_session_wr_5b"] = out["session_wr_5b"].shift(1)
    out["prior_session_has_qualifying"] = out["session_has_qualifying"].shift(1)
    out["prior_session_is_winning"] = out["session_is_winning"].shift(1)
    out["prior_session_is_losing"] = out["session_is_losing"].shift(1)
    out["prior_win_streak"] = out["ending_win_streak"].shift(1).fillna(0).astype("int32")
    out["prior_loss_streak"] = out["ending_loss_streak"].shift(1).fillna(0).astype("int32")

    win_values = pd.Series(
        np.where(out["session_has_qualifying"], out["session_is_winning"].astype(float), np.nan),
        index=out.index,
    )
    out["rolling_5_session_wr"] = win_values.shift(1).rolling(5, min_periods=5).mean()
    out["rolling_5_session_avg_ret_5b_ticks"] = out["session_avg_ret_5b_ticks"].shift(1).rolling(5, min_periods=5).mean()

    out["is_first_half_week"] = out["session_weekday"].isin([0, 1, 2])
    out["is_second_half_week"] = out["session_weekday"].isin([3, 4])
    out["is_monday_after_losing_friday"] = (
        out["session_weekday"].eq(0) & out["prior_session_weekday"].eq(4) & out["prior_session_is_losing"]
    )
    out["is_friday_after_winning_thursday"] = (
        out["session_weekday"].eq(4) & out["prior_session_weekday"].eq(3) & out["prior_session_is_winning"]
    )

    bool_cols = [
        "session_has_qualifying",
        "session_is_winning",
        "session_is_losing",
        "prior_session_has_qualifying",
        "prior_session_is_winning",
        "prior_session_is_losing",
        "is_first_half_week",
        "is_second_half_week",
        "is_monday_after_losing_friday",
        "is_friday_after_winning_thursday",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def build_session_summary(observations: pd.DataFrame) -> pd.DataFrame:
    working = observations.sort_values(["session_date", "bar_ts", "global_index"], kind="stable").copy()
    working["qualifying_ret_5b_ticks"] = working["ret_5b_ticks"].where(working["has_core_60m_15m_gate"])
    working["qualifying_win_5b"] = np.where(
        working["has_core_60m_15m_gate"],
        working["ret_5b_ticks"].gt(0),
        np.nan,
    )

    summary = (
        working.groupby("session_date", as_index=False, sort=False)
        .agg(
            session_start_ts=("bar_ts", "first"),
            session_observation_count=("global_index", "count"),
            session_qualifying_count=("has_core_60m_15m_gate", "sum"),
            session_avg_ret_5b_ticks=("qualifying_ret_5b_ticks", "mean"),
            session_wr_5b=("qualifying_win_5b", "mean"),
        )
        .sort_values("session_start_ts", kind="stable")
        .reset_index(drop=True)
    )
    return add_session_rollups(summary)


def merge_session_context(observations: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    return observations.merge(session_summary, on="session_date", how="left", validate="many_to_one")


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
        ("01", "Prior session winning + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_is_winning"]),
        ("02", "Prior session losing + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_is_losing"]),
        ("03", "2 consecutive winning sessions + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_win_streak"].ge(2)),
        ("04", "2 consecutive losing sessions + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_loss_streak"].ge(2)),
        ("05", "3+ consecutive winning sessions + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_win_streak"].ge(3)),
        ("06", "3+ consecutive losing sessions + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_loss_streak"].ge(3)),
        ("07", "Prior session avg return > +50 ticks + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_avg_ret_5b_ticks"].gt(50)),
        ("08", "Prior session avg return < -50 ticks + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_avg_ret_5b_ticks"].lt(-50)),
        (
            "09",
            "Prior session avg return between -10 and +10 ticks + 60m + 15m",
            lambda df: df["has_core_60m_15m_gate"] & df["prior_session_avg_ret_5b_ticks"].between(-10, 10, inclusive="both"),
        ),
        ("10", "Prior session > 20 qualifying signals + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_qualifying_count"].gt(20)),
        ("11", "Prior session < 5 qualifying signals + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["prior_session_qualifying_count"].lt(5)),
        ("12", "Monday after losing Friday + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["is_monday_after_losing_friday"]),
        ("13", "Friday after winning Thursday + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["is_friday_after_winning_thursday"]),
        ("14", "First half of week (Mon-Wed) + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["is_first_half_week"]),
        ("15", "Second half of week (Thu-Fri) + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["is_second_half_week"]),
        ("16", "Rolling 5-session WR > 60% + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["rolling_5_session_wr"].gt(0.60)),
        ("17", "Rolling 5-session WR < 40% + 60m + 15m", lambda df: df["has_core_60m_15m_gate"] & df["rolling_5_session_wr"].lt(0.40)),
        (
            "18",
            "Rolling 5-session avg return > +30 ticks + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["rolling_5_session_avg_ret_5b_ticks"].gt(30) & df["is_first_hour"],
        ),
        (
            "19",
            "Rolling 5-session avg return < -30 ticks + 60m + 15m + first_hour",
            lambda df: df["has_core_60m_15m_gate"] & df["rolling_5_session_avg_ret_5b_ticks"].lt(-30) & df["is_first_hour"],
        ),
        (
            "20",
            "Prior losing session + 60m + 15m + NOT killers + first_hour",
            lambda df: df["has_core_60m_15m_gate"]
            & df["prior_session_is_losing"]
            & df["passes_not_all_killers"]
            & df["is_first_hour"],
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
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)

    observations = attach_timeframe_context(observations, context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)
    observations = add_time_flags(observations)

    session_summary = build_session_summary(observations)
    observations = merge_session_context(observations, session_summary)

    baseline_all = summarize_filter("00", "All grouped non-zero-delta observations", observations)
    baseline_core = summarize_filter(
        "00A",
        "60m + 15m core observations",
        observations[observations["has_core_60m_15m_gate"]].copy(),
    )
    baseline_core_first_hour = summarize_filter(
        "00B",
        "60m + 15m + first_hour",
        observations[observations["has_core_60m_15m_gate"] & observations["is_first_hour"]].copy(),
    )
    baseline_core_not_killers = summarize_filter(
        "00C",
        "60m + 15m + NOT killers",
        observations[observations["has_core_60m_15m_gate"] & observations["passes_not_all_killers"]].copy(),
    )

    results = run_filters(observations)

    lines = [
        "DEEP6 round 16 consecutive-session analysis",
        "==========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: grouped signal bar by (global_index, direction_sign from bar_delta).",
        "Core gate = is_60m_extreme AND is_15m_trend_aligned.",
        "Per-session summary uses only core-gated observations: qualifying count plus avg ret_5b_ticks.",
        "Winning session = avg ret_5b_ticks > 0. Losing session = avg ret_5b_ticks <= 0. Sessions with zero qualifying bars stay unclassified.",
        "KILLER_1 = trade-direction anchor in middle 40-60% of the active 60m range. KILLER_2 = bar_volume > 3x prior 20-bar EMA.",
        "Rolling 5-session metrics use the prior five sessions and require five prior sessions with qualifying core observations.",
        "first_hour = 09:30-10:29 ET.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped observations:                  {len(observations):,}",
        f"Sessions summarized:                   {len(session_summary):,}",
        f"15m bars built:                        {len(context[15]):,}",
        f"60m bars built:                        {len(context[60]):,}",
        f"Core 60m+15m observations:            {int(observations['has_core_60m_15m_gate'].sum()):,}",
        f"Core first-hour observations:         {int((observations['has_core_60m_15m_gate'] & observations['is_first_hour']).sum()):,}",
        f"Core NOT-killer observations:         {int((observations['has_core_60m_15m_gate'] & observations['passes_not_all_killers']).sum()):,}",
        f"Sessions with qualifying core bars:   {int(session_summary['session_has_qualifying'].sum()):,}",
        f"Winning sessions:                     {int(session_summary['session_is_winning'].sum()):,}",
        f"Losing sessions:                      {int(session_summary['session_is_losing'].sum()):,}",
        f"Sessions with zero core bars:         {int((~session_summary['session_has_qualifying']).sum()):,}",
        f"Longest winning streak:               {int(session_summary['ending_win_streak'].max()):,}",
        f"Longest losing streak:                {int(session_summary['ending_loss_streak'].max()):,}",
        f"Sessions with rolling-5 context:      {int(session_summary['rolling_5_session_wr'].notna().sum()):,}",
        "",
        f"Baselines ({FORWARD_WINDOW}-bar window)",
        "--------------------------",
        f"All grouped bars:          {render_summary_line(baseline_all)}",
        f"60m + 15m core:           {render_summary_line(baseline_core)}",
        f"60m + 15m + first_hour:  {render_summary_line(baseline_core_first_hour)}",
        f"60m + 15m + NOT killers: {render_summary_line(baseline_core_not_killers)}",
        "",
        "All 20 consecutive-session filters ranked by 5-bar average return",
        "--------------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
