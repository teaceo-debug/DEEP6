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
OUT_PATH = OUT_DIR / "round1_regime_gated_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOW = 5
TICK_SIZE = 0.25
TARGET_SIGNAL_IDS = ("DELT_04", "TRAP_04", "IMB_03")


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
    df["direction_sign"] = direction_to_sign(df["direction"])
    df = df[df["direction_sign"] != 0].copy()
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_observations(events: pd.DataFrame) -> pd.DataFrame:
    for signal_id in TARGET_SIGNAL_IDS:
        events[f"is_{signal_id}"] = events["signal_id"].eq(signal_id)

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
            has_DELT_04=("is_DELT_04", "max"),
            has_TRAP_04=("is_TRAP_04", "max"),
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


def compute_bar_features(events: pd.DataFrame) -> pd.DataFrame:
    bars = (
        events.drop_duplicates(subset=["global_index"])
        .sort_values("global_index", kind="stable")
        .loc[
            :,
            [
                "global_index",
                "session_date",
                "bar_ts",
                "bar_index",
                "bar_open",
                "bar_high",
                "bar_low",
                "bar_close",
                "bar_delta",
                "bar_volume",
            ],
        ]
        .copy()
    )

    bars["prev_close"] = bars["bar_close"].shift(1)
    same_session = bars["session_date"].eq(bars["session_date"].shift(1))
    bars.loc[~same_session, "prev_close"] = np.nan

    tr_components = pd.concat(
        [
            bars["bar_high"] - bars["bar_low"],
            (bars["bar_high"] - bars["prev_close"]).abs(),
            (bars["bar_low"] - bars["prev_close"]).abs(),
        ],
        axis=1,
    )
    bars["tr"] = tr_components.max(axis=1)
    bars["atr_20"] = (
        bars.groupby("session_date", sort=False)["tr"]
        .transform(lambda s: s.rolling(20, min_periods=20).mean())
    )
    bars["sma_50"] = (
        bars.groupby("session_date", sort=False)["bar_close"]
        .transform(lambda s: s.rolling(50, min_periods=50).mean())
    )
    bars["prior_delta_10"] = (
        bars.groupby("session_date", sort=False)["bar_delta"]
        .transform(lambda s: s.shift(1).rolling(10, min_periods=10).sum())
    )
    bars["cum_pv"] = (
        (bars["bar_close"] * bars["bar_volume"])
        .groupby(bars["session_date"], sort=False)
        .cumsum()
    )
    bars["cum_vol"] = bars.groupby("session_date", sort=False)["bar_volume"].cumsum()
    bars["session_vwap"] = np.where(bars["cum_vol"] > 0, bars["cum_pv"] / bars["cum_vol"], np.nan)
    bars["vwap_dist_ticks"] = (bars["bar_close"] - bars["session_vwap"]).abs() / TICK_SIZE
    bars["volatility_regime"] = pd.qcut(
        bars["atr_20"],
        q=3,
        labels=["low_vol", "mid_vol", "high_vol"],
        duplicates="drop",
    )
    bars["vwap_position"] = pd.qcut(
        bars["vwap_dist_ticks"],
        q=3,
        labels=["near_vwap", "mid_vwap", "far_vwap"],
        duplicates="drop",
    )
    bars["price_vs_sma"] = np.where(bars["bar_close"] >= bars["sma_50"], "above_sma50", "below_sma50")
    return bars


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


def add_observation_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    delta_side = np.sign(out["prior_delta_10"].fillna(0.0)) * out["direction_sign"]
    out["prior_delta_relation"] = np.select(
        [delta_side < 0, delta_side > 0, delta_side == 0],
        ["delta_opposite", "delta_same", "delta_flat"],
        default="delta_flat",
    )
    out["is_delta_opposite"] = out["prior_delta_relation"].eq("delta_opposite")
    out["is_delta_same"] = out["prior_delta_relation"].eq("delta_same")
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
        "median_return_5b_ticks": float(returns.median()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "sharpe": sharpe_ratio(returns) if n else np.nan,
        "flag": status_flag(n, ci_low),
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "ALL signals + low_vol + 60m_extreme", lambda df: df["volatility_regime"].eq("low_vol") & df["is_60m_extreme"]),
        ("02", "ALL signals + mid_vol + 60m_extreme", lambda df: df["volatility_regime"].eq("mid_vol") & df["is_60m_extreme"]),
        ("03", "ALL signals + high_vol + 60m_extreme", lambda df: df["volatility_regime"].eq("high_vol") & df["is_60m_extreme"]),
        ("04", "DELT_04 + low_vol + 60m_extreme", lambda df: df["has_DELT_04"] & df["volatility_regime"].eq("low_vol") & df["is_60m_extreme"]),
        ("05", "DELT_04 + mid_vol + 60m_extreme", lambda df: df["has_DELT_04"] & df["volatility_regime"].eq("mid_vol") & df["is_60m_extreme"]),
        ("06", "TRAP_04 + mid_vol + 60m_extreme", lambda df: df["has_TRAP_04"] & df["volatility_regime"].eq("mid_vol") & df["is_60m_extreme"]),
        ("07", "IMB_03 + mid_vol + 60m_extreme", lambda df: df["has_IMB_03"] & df["volatility_regime"].eq("mid_vol") & df["is_60m_extreme"]),
        ("08", "ALL signals + above_sma50 + 60m_extreme", lambda df: df["price_vs_sma"].eq("above_sma50") & df["is_60m_extreme"]),
        ("09", "ALL signals + below_sma50 + 60m_extreme", lambda df: df["price_vs_sma"].eq("below_sma50") & df["is_60m_extreme"]),
        ("10", "DELT_04 + above_sma50 + 15m_trend_aligned", lambda df: df["has_DELT_04"] & df["price_vs_sma"].eq("above_sma50") & df["is_15m_trend_aligned"]),
        ("11", "DELT_04 + below_sma50 + 15m_trend_aligned", lambda df: df["has_DELT_04"] & df["price_vs_sma"].eq("below_sma50") & df["is_15m_trend_aligned"]),
        ("12", "ALL signals + near_vwap + 60m_extreme", lambda df: df["vwap_position"].eq("near_vwap") & df["is_60m_extreme"]),
        ("13", "ALL signals + mid_vwap + 60m_extreme", lambda df: df["vwap_position"].eq("mid_vwap") & df["is_60m_extreme"]),
        ("14", "ALL signals + far_vwap + 60m_extreme", lambda df: df["vwap_position"].eq("far_vwap") & df["is_60m_extreme"]),
        ("15", "ALL signals + delta_opposite + 60m_extreme", lambda df: df["is_delta_opposite"] & df["is_60m_extreme"]),
        ("16", "ALL signals + delta_same + 60m_extreme", lambda df: df["is_delta_same"] & df["is_60m_extreme"]),
        ("17", "DELT_04 + delta_opposite + 15m_trend_aligned", lambda df: df["has_DELT_04"] & df["is_delta_opposite"] & df["is_15m_trend_aligned"]),
        ("18", "TRAP_04 + delta_opposite + 60m_extreme", lambda df: df["has_TRAP_04"] & df["is_delta_opposite"] & df["is_60m_extreme"]),
        ("19", "5+ unique signals same bar + 60m_extreme", lambda df: (df["signal_count"] >= 5) & df["is_60m_extreme"]),
        ("20", "6+ unique signals same bar + 60m_extreme", lambda df: (df["signal_count"] >= 6) & df["is_60m_extreme"]),
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
                fmt_pct(float(row["win_rate"])),
                fmt_float(float(row["profit_factor"])),
                fmt_float(float(row["avg_return_5b_ticks"])),
                fmt_float(float(row["median_return_5b_ticks"])),
                fmt_ci(float(row["ci_low"]), float(row["ci_high"])),
                fmt_float(float(row["sharpe"])),
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
    bar_features = compute_bar_features(events)
    context = build_timeframe_context(bars_1m)

    observations = observations.merge(
        bar_features[
            [
                "global_index",
                "atr_20",
                "sma_50",
                "session_vwap",
                "vwap_dist_ticks",
                "prior_delta_10",
                "volatility_regime",
                "vwap_position",
                "price_vs_sma",
            ]
        ],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_context(observations, context)
    observations = add_observation_flags(observations)

    baseline = summarize_filter("00", "All same-bar same-direction observations", observations)
    results = run_filters(observations)

    lines = [
        "DEEP6 round1 regime-gated signal analysis",
        "=========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation.",
        "Bar features (ATR20, SMA50, VWAP, prior_delta_10) are computed on deduplicated bars by global_index.",
        "60m_extreme and 15m_trend_aligned follow the cross-category combo pattern.",
        "Volatility and VWAP buckets use pd.qcut(q=3) on valid deduplicated-bar features.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Raw event rows loaded: {len(events):,}",
        f"Grouped observations:  {len(observations):,}",
        f"15m bars built:       {len(context[15]):,}",
        f"60m bars built:       {len(context[60]):,}",
        f"60m extreme:          {int(observations['is_60m_extreme'].sum()):,}",
        f"15m trend aligned:    {int(observations['is_15m_trend_aligned'].sum()):,}",
        "",
        f"Baseline ({FORWARD_WINDOW}-bar window)",
        "-----------------------",
        f"N={baseline['n']:,} | WR={fmt_pct(float(baseline['win_rate']))} | PF={fmt_float(float(baseline['profit_factor']))} | Avg={fmt_float(float(baseline['avg_return_5b_ticks']))}t | Med={fmt_float(float(baseline['median_return_5b_ticks']))}t | CI={fmt_ci(float(baseline['ci_low']), float(baseline['ci_high']))} | Sharpe={fmt_float(float(baseline['sharpe']))}",
        "",
        "All 20 regime-gated filters ranked by 5-bar average return",
        "--------------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
