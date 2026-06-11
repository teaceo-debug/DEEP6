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
OUT_PATH = OUT_DIR / "round1_time_day_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
TARGET_SIGNAL_IDS = ("DELT_04", "AUCT_03", "VOLP_06", "TRAP_04", "EXH_03", "IMB_03")


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


def sharpe_ratio(returns: pd.Series) -> float:
    if len(returns) <= 1:
        return 0.0
    std = float(returns.std(ddof=1))
    return float(returns.mean() / std) if std > 0 else 0.0


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
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    for signal_id in TARGET_SIGNAL_IDS:
        events[f"is_{signal_id}"] = events["signal_id"].eq(signal_id)
    events["is_absorption"] = events["category"].eq("absorption")
    events["is_TYPE_A"] = events["score_tier"].eq("TYPE_A")
    events["is_TYPE_B"] = events["score_tier"].eq("TYPE_B")
    events["is_score_ge_80"] = events["score_final"].ge(80)

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
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            has_absorption=("is_absorption", "max"),
            has_TYPE_A=("is_TYPE_A", "max"),
            has_TYPE_B=("is_TYPE_B", "max"),
            has_score_ge_80=("is_score_ge_80", "max"),
            has_DELT_04=("is_DELT_04", "max"),
            has_AUCT_03=("is_AUCT_03", "max"),
            has_VOLP_06=("is_VOLP_06", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
            has_EXH_03=("is_EXH_03", "max"),
            has_IMB_03=("is_IMB_03", "max"),
        )
        .sort_values(["global_index", "direction_sign"], kind="stable")
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


def add_regime_flags(df: pd.DataFrame) -> pd.DataFrame:
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
    out["weekday"] = out["bar_ts"].dt.day_name()
    out["minutes_since_930"] = (out["hour"] - 9) * 60 + out["minute"] - 30

    out["is_hour_09_10"] = out["hour"].eq(9)
    out["is_hour_10_12"] = out["hour"].isin([10, 11])
    out["is_hour_12_14"] = out["hour"].isin([12, 13])
    out["is_hour_14_16"] = out["hour"].isin([14, 15])
    out["is_hour_15_only"] = out["hour"].eq(15)
    out["is_not_hour_12_14"] = ~out["is_hour_12_14"]

    out["is_first_30min"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(30)
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)
    out["is_last_hour"] = out["minutes_since_930"].ge(330) & out["minutes_since_930"].lt(390)
    out["is_mid_session"] = out["minutes_since_930"].ge(60) & out["minutes_since_930"].lt(330)
    out["is_not_first_30min"] = ~out["is_first_30min"]

    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(240)
    out["is_not_lunch"] = ~lunch_mask
    out["is_not_monday"] = out["weekday"].ne("Monday")
    return out


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
        "sharpe": sharpe_ratio(returns) if n else np.nan,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "ALL + 60m_extreme + hour 09-10 (open range)", lambda df: df["is_60m_extreme"] & df["is_hour_09_10"]),
        ("02", "ALL + 60m_extreme + hour 10-12 (mid-morning)", lambda df: df["is_60m_extreme"] & df["is_hour_10_12"]),
        ("03", "ALL + 60m_extreme + hour 12-14 (lunch/afternoon)", lambda df: df["is_60m_extreme"] & df["is_hour_12_14"]),
        ("04", "ALL + 60m_extreme + hour 14-16 (close range)", lambda df: df["is_60m_extreme"] & df["is_hour_14_16"]),
        ("05", "ALL + 60m_extreme + hour 15 only (power hour)", lambda df: df["is_60m_extreme"] & df["is_hour_15_only"]),
        (
            "06",
            "absorption + 60m_extreme + 15m_trend + hour 10-12",
            lambda df: df["has_absorption"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_hour_10_12"],
        ),
        (
            "07",
            "absorption + 60m_extreme + 15m_trend + hour 14-16",
            lambda df: df["has_absorption"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_hour_14_16"],
        ),
        (
            "08",
            "absorption + 60m_extreme + 15m_trend + NOT hour 12-14",
            lambda df: df["has_absorption"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_hour_12_14"],
        ),
        (
            "09",
            "DELT_04 + TRAP_04 + 15m_trend + hour 14-16",
            lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & df["is_15m_trend_aligned"] & df["is_hour_14_16"],
        ),
        (
            "10",
            "DELT_04 + TRAP_04 + 15m_trend + hour 10-12",
            lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & df["is_15m_trend_aligned"] & df["is_hour_10_12"],
        ),
        (
            "11",
            "score >= 80 + 60m_extreme + hour 14-16",
            lambda df: df["has_score_ge_80"] & df["is_60m_extreme"] & df["is_hour_14_16"],
        ),
        (
            "12",
            "score >= 80 + 60m_extreme + hour 10-12",
            lambda df: df["has_score_ge_80"] & df["is_60m_extreme"] & df["is_hour_10_12"],
        ),
        ("13", "ALL + 60m_extreme + Monday", lambda df: df["is_60m_extreme"] & df["weekday"].eq("Monday")),
        ("14", "ALL + 60m_extreme + Tuesday", lambda df: df["is_60m_extreme"] & df["weekday"].eq("Tuesday")),
        ("15", "ALL + 60m_extreme + Wednesday", lambda df: df["is_60m_extreme"] & df["weekday"].eq("Wednesday")),
        ("16", "ALL + 60m_extreme + Thursday", lambda df: df["is_60m_extreme"] & df["weekday"].eq("Thursday")),
        ("17", "ALL + 60m_extreme + Friday", lambda df: df["is_60m_extreme"] & df["weekday"].eq("Friday")),
        ("18", "ALL + 60m_extreme + first_30min (09:30-10:00)", lambda df: df["is_60m_extreme"] & df["is_first_30min"]),
        ("19", "ALL + 60m_extreme + first_hour (09:30-10:30)", lambda df: df["is_60m_extreme"] & df["is_first_hour"]),
        ("20", "ALL + 60m_extreme + last_hour (15:00-16:00)", lambda df: df["is_60m_extreme"] & df["is_last_hour"]),
        ("21", "ALL + 60m_extreme + mid_session (10:30-15:00)", lambda df: df["is_60m_extreme"] & df["is_mid_session"]),
        (
            "22",
            "absorption + 60m_extreme + 15m_trend + last_hour + NOT_Monday",
            lambda df: df["has_absorption"]
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_last_hour"]
            & df["is_not_monday"],
        ),
        (
            "23",
            "DELT_04 + TRAP_04 + 15m_trend + NOT_lunch (exclude 12:00-13:30)",
            lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & df["is_15m_trend_aligned"] & df["is_not_lunch"],
        ),
        (
            "24",
            "3+ categories + 60m_extreme + last_hour",
            lambda df: df["category_count"].ge(3) & df["is_60m_extreme"] & df["is_last_hour"],
        ),
        (
            "25",
            "TYPE_B + 60m_extreme + NOT_first_30min",
            lambda df: df["has_TYPE_B"] & df["is_60m_extreme"] & df["is_not_first_30min"],
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
    headers = ["Filter", "N", "WR%", "PF", "Avg Ticks", "Med Ticks", "Wilson 95% CI", "Sharpe"]
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
                fmt_float(row["sharpe"]),
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
    observations = add_regime_flags(observations)
    observations = add_time_flags(observations)

    baseline = summarize_filter("00", "All same-bar same-direction observations", observations)
    extreme_baseline = summarize_filter("00x", "All 60m_extreme observations", observations[observations["is_60m_extreme"]].copy())
    results = run_filters(observations)

    lines = [
        "DEEP6 round1 time-of-day and day-of-week filter analysis",
        "======================================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation.",
        "Regime filters match analyze_cross_category_combos.py: 15m_trend_aligned = signal direction matches 15m bar sign; 60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "Time filters use bar_ts converted to America/New_York. Hour buckets are local-clock windows: 09-10=09:xx, 10-12=10:xx-11:xx, 12-14=12:xx-13:xx, 14-16=14:xx-15:xx.",
        "Session windows use minutes_since_930 = (hour - 9) * 60 + minute - 30.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded: {len(events):,}",
        f"Grouped observations:  {len(observations):,}",
        f"15m bars built:       {len(context[15]):,}",
        f"60m bars built:       {len(context[60]):,}",
        f"15m trend aligned:    {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme:          {int(observations['is_60m_extreme'].sum()):,}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"All observations: N={baseline['n']:,} | WR={fmt_pct(baseline['win_rate'])} | PF={fmt_float(baseline['profit_factor'])} | Avg={fmt_float(baseline['avg_return_5b_ticks'])}t | Med={fmt_float(baseline['median_return_5b_ticks'])}t | CI={fmt_ci(baseline['ci_low'], baseline['ci_high'])} | Sharpe={fmt_float(baseline['sharpe'])}",
        f"60m_extreme only: N={extreme_baseline['n']:,} | WR={fmt_pct(extreme_baseline['win_rate'])} | PF={fmt_float(extreme_baseline['profit_factor'])} | Avg={fmt_float(extreme_baseline['avg_return_5b_ticks'])}t | Med={fmt_float(extreme_baseline['median_return_5b_ticks'])}t | CI={fmt_ci(extreme_baseline['ci_low'], extreme_baseline['ci_high'])} | Sharpe={fmt_float(extreme_baseline['sharpe'])}",
        "",
        f"All 25 filters ranked by {FORWARD_WINDOW}-bar average return",
        "---------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
