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
OUT_PATH = OUT_DIR / "round2_novel_bar_patterns_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
ROLLING_LOOKBACK = 20


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


def compute_bar_features(observations: pd.DataFrame) -> pd.DataFrame:
    bars = observations.copy()
    by_session = bars.groupby("session_date", sort=False)

    bars["bar_range"] = bars["bar_high"] - bars["bar_low"]
    bars["body"] = (bars["bar_close"] - bars["bar_open"]).abs()
    bars["upper_wick"] = bars["bar_high"] - np.maximum(bars["bar_open"], bars["bar_close"])
    bars["lower_wick"] = np.minimum(bars["bar_open"], bars["bar_close"]) - bars["bar_low"]
    bars["delta_ratio"] = np.where(bars["bar_volume"] > 0, bars["bar_delta"] / bars["bar_volume"], np.nan)
    bars["abs_delta"] = bars["bar_delta"].abs()
    bars["price_change"] = bars["bar_close"] - bars["bar_open"]
    bars["price_sign"] = np.sign(bars["price_change"]).astype(int)

    bars["prior_bar_delta"] = by_session["bar_delta"].shift(1)
    bars["prior_abs_delta"] = by_session["abs_delta"].shift(1)
    bars["prior_high"] = by_session["bar_high"].shift(1)
    bars["prior_low"] = by_session["bar_low"].shift(1)
    bars["prior_bar_range"] = by_session["bar_range"].shift(1)
    bars["prior_price_sign"] = by_session["price_sign"].shift(1)
    bars["prior_direction_sign"] = by_session["direction_sign"].shift(1)
    bars["bar_range_2"] = by_session["bar_range"].shift(2)

    bars["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    bars["abs_delta_q90"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.90)
    )
    bars["abs_delta_q75"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    bars["abs_delta_q25"] = by_session["abs_delta"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )
    bars["range_q75"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.75)
    )
    bars["range_q25"] = by_session["bar_range"].transform(
        lambda s: s.shift(1).rolling(ROLLING_LOOKBACK, min_periods=ROLLING_LOOKBACK).quantile(0.25)
    )

    rejection_wick = np.where(bars["direction_sign"] > 0, bars["lower_wick"], bars["upper_wick"])
    opposite_wick = np.where(bars["direction_sign"] > 0, bars["upper_wick"], bars["lower_wick"])
    bars["rejection_wick"] = rejection_wick
    bars["opposite_wick"] = opposite_wick

    bars["is_large_abs_delta"] = bars["abs_delta"] > bars["abs_delta_q90"]
    bars["is_delta_reversal"] = (
        bars["prior_bar_delta"].notna()
        & bars["prior_bar_delta"].ne(0)
        & np.sign(bars["bar_delta"]).ne(np.sign(bars["prior_bar_delta"]))
    )
    bars["is_narrow_range"] = bars["bar_range"] < bars["range_q25"]
    bars["is_wide_range"] = bars["bar_range"] > bars["range_q75"]
    bars["is_high_delta"] = bars["abs_delta"] > bars["abs_delta_q75"]
    bars["is_low_delta"] = bars["abs_delta"] < bars["abs_delta_q25"]
    bars["is_delta_acceleration"] = (
        bars["prior_abs_delta"].gt(0)
        & bars["abs_delta"].gt(2.0 * bars["prior_abs_delta"])
    )

    bars["is_volume_spike"] = (
        bars["rolling_20_ema_vol"].gt(0)
        & bars["bar_volume"].gt(2.0 * bars["rolling_20_ema_vol"])
    )
    bars["is_volume_exhaustion"] = (
        bars["rolling_20_ema_vol"].gt(0)
        & bars["bar_volume"].lt(0.5 * bars["rolling_20_ema_vol"])
    )
    bars["is_inside_bar"] = bars["bar_high"].lt(bars["prior_high"]) & bars["bar_low"].gt(bars["prior_low"])
    bars["is_outside_bar"] = bars["bar_high"].gt(bars["prior_high"]) & bars["bar_low"].lt(bars["prior_low"])
    bars["is_pin_bar"] = (
        bars["bar_range"].gt(0)
        & pd.Series(rejection_wick, index=bars.index).gt(2.0 * bars["body"])
        & pd.Series(rejection_wick, index=bars.index).gt(pd.Series(opposite_wick, index=bars.index))
    )
    bars["is_doji"] = bars["bar_range"].gt(0) & bars["body"].lt(0.10 * bars["bar_range"])
    bars["is_three_narrowing_ranges"] = (
        bars["bar_range_2"].notna()
        & bars["prior_bar_range"].lt(bars["bar_range_2"])
        & bars["bar_range"].lt(bars["prior_bar_range"])
    )

    bars["is_price_delta_divergence"] = (
        bars["price_sign"].ne(0)
        & bars["direction_sign"].ne(0)
        & bars["price_sign"].eq(-bars["direction_sign"])
    )
    bars["is_delta_divergence_2bar"] = (
        bars["is_price_delta_divergence"]
        & bars["prior_price_sign"].notna()
        & bars["prior_direction_sign"].notna()
        & pd.Series(bars["prior_price_sign"], index=bars.index).ne(0)
        & pd.Series(bars["prior_direction_sign"], index=bars.index).ne(0)
        & pd.Series(bars["prior_price_sign"], index=bars.index).eq(-pd.Series(bars["prior_direction_sign"], index=bars.index))
    )
    return bars


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
        ("01", "Large abs delta (rolling q90) + 60m_extreme", lambda df: df["is_large_abs_delta"] & df["is_60m_extreme"]),
        ("02", "Delta reversal + 60m_extreme", lambda df: df["is_delta_reversal"] & df["is_60m_extreme"]),
        (
            "03",
            "Narrow range (q25) + high delta (q75) + 60m_extreme",
            lambda df: df["is_narrow_range"] & df["is_high_delta"] & df["is_60m_extreme"],
        ),
        (
            "04",
            "Wide range (q75) + low delta (q25) + 60m_extreme",
            lambda df: df["is_wide_range"] & df["is_low_delta"] & df["is_60m_extreme"],
        ),
        ("05", "Delta acceleration (>2x prior) + 60m_extreme", lambda df: df["is_delta_acceleration"] & df["is_60m_extreme"]),
        ("06", "Volume spike (>2x prior 20 EMA) + 60m_extreme", lambda df: df["is_volume_spike"] & df["is_60m_extreme"]),
        (
            "07",
            "Volume exhaustion (<0.5x prior 20 EMA) + 60m_extreme",
            lambda df: df["is_volume_exhaustion"] & df["is_60m_extreme"],
        ),
        (
            "08",
            "Volume spike + narrow range + 60m_extreme",
            lambda df: df["is_volume_spike"] & df["is_narrow_range"] & df["is_60m_extreme"],
        ),
        (
            "09",
            "Volume spike + delta reversal + 60m_extreme",
            lambda df: df["is_volume_spike"] & df["is_delta_reversal"] & df["is_60m_extreme"],
        ),
        ("10", "Inside bar + 60m_extreme", lambda df: df["is_inside_bar"] & df["is_60m_extreme"]),
        ("11", "Outside bar + 60m_extreme", lambda df: df["is_outside_bar"] & df["is_60m_extreme"]),
        ("12", "Pin bar + 60m_extreme", lambda df: df["is_pin_bar"] & df["is_60m_extreme"]),
        ("13", "Doji + 60m_extreme + 15m_trend", lambda df: df["is_doji"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        (
            "14",
            "3 consecutive narrowing ranges + 60m_extreme",
            lambda df: df["is_three_narrowing_ranges"] & df["is_60m_extreme"],
        ),
        (
            "15",
            "2-bar price/delta divergence + 60m_extreme",
            lambda df: df["is_delta_divergence_2bar"] & df["is_60m_extreme"],
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
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = compute_bar_features(observations)
    observations = add_context_flags(observations)

    baseline_all = summarize_filter("00", "All non-zero-delta signal bars", observations)
    baseline_60m = summarize_filter("00A", "All non-zero-delta bars at 60m extreme", observations[observations["is_60m_extreme"]].copy())
    results = run_filters(observations)

    lines = [
        "DEEP6 round 2 novel bar-pattern analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique signal bar grouped by global_index.",
        "Trade direction for P&L: sign(bar_delta). Zero-delta bars are skipped.",
        f"Rolling thresholds use the prior {ROLLING_LOOKBACK} bars within each session.",
        "60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "15m_trend = bar_delta sign matches 15m open-close sign.",
        "Pin bar = rejection wick aligned with delta sign is >2x body and larger than the opposite wick.",
        "2-bar price/delta divergence = current and prior bars both closed opposite their delta sign.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded:    {len(events):,}",
        f"Grouped observations:     {len(observations):,}",
        f"15m bars built:           {len(context[15]):,}",
        f"60m bars built:           {len(context[60]):,}",
        f"60m extreme observations: {int(observations['is_60m_extreme'].sum()):,}",
        f"15m trend aligned:        {int(observations['is_15m_trend_aligned'].sum()):,}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"All bars: N={baseline_all['n']:,} | WR={fmt_pct(baseline_all['win_rate'])} | PF={fmt_float(baseline_all['profit_factor'])} | Avg={fmt_float(baseline_all['avg_return_5b_ticks'])}t | Med={fmt_float(baseline_all['median_return_5b_ticks'])}t | CI={fmt_ci(baseline_all['ci_low'], baseline_all['ci_high'])}",
        f"60m extreme: N={baseline_60m['n']:,} | WR={fmt_pct(baseline_60m['win_rate'])} | PF={fmt_float(baseline_60m['profit_factor'])} | Avg={fmt_float(baseline_60m['avg_return_5b_ticks'])}t | Med={fmt_float(baseline_60m['median_return_5b_ticks'])}t | CI={fmt_ci(baseline_60m['ci_low'], baseline_60m['ci_high'])}",
        "",
        "All 15 novel filters ranked by 5-bar average return",
        "-----------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
