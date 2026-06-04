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
OUT_PATH = OUT_DIR / "compound_filter_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (5, 15, 60)
FORWARD_WINDOWS = (5, 10, 15, 30)
TICK_SIZE = 0.25
CO_SIGNAL_IDS = ("TRAP_04", "TRAP_05", "EXH_03", "EXH_04", "VOLP_06", "AUCT_03")


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
    """Wilson score interval for binomial proportion."""
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
    bars = bars.sort_values("ts_event").reset_index(drop=True)
    return bars


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
        "fwd_close_1b",
        "fwd_close_2b",
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
        "bar_delta",
        "bar_volume",
        "fwd_close_1b",
        "fwd_close_2b",
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
    df["direction"] = df["direction_sign"].astype("int8")
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    abs_ev = events[events["category"] == "absorption"].copy()
    abs_obs = (
        abs_ev.groupby(["global_index", "direction_sign"], as_index=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            signal_ids=("signal_id", lambda s: ",".join(sorted(set(s)))),
            has_ABS_04=("signal_id", lambda s: "ABS_04" in set(s)),
            absorption_variants=("signal_id", "nunique"),
            strength=("strength", "max"),
            score_final=("score_final", "max"),
            score_tier=("score_tier", "first"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_1b=("fwd_close_1b", "first"),
            fwd_close_2b=("fwd_close_2b", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
        )
    )
    abs_obs["direction"] = np.where(abs_obs["direction_sign"] > 0, "BULLISH", "BEARISH")
    for window in FORWARD_WINDOWS:
        abs_obs[f"ret_{window}b_ticks"] = abs_obs["direction_sign"] * (
            (abs_obs[f"fwd_close_{window}b"] - abs_obs["bar_close"]) / TICK_SIZE
        )
    return abs_obs


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
    bars["price_vs_sma"] = np.where(bars["bar_close"] >= bars["sma_50"], "above_sma50", "below_sma50")
    return bars


def build_timeframe_context(bars_1m: pd.DataFrame, events_all: pd.DataFrame) -> dict[int, pd.DataFrame]:
    delta_1m = (
        events_all[["bar_ts", "bar_delta"]]
        .dropna(subset=["bar_ts"])
        .drop_duplicates(subset=["bar_ts"])
        .sort_values("bar_ts")
        .rename(columns={"bar_ts": "ts_event"})
    )
    delta_1m["bar_delta"] = pd.to_numeric(delta_1m["bar_delta"], errors="coerce").fillna(0.0)

    context: dict[int, pd.DataFrame] = {}
    base = bars_1m.set_index("ts_event")
    delta_base = delta_1m.set_index("ts_event")

    for tf in TIMEFRAMES:
        rule = f"{tf}min"
        tf_bars = (
            base.resample(rule)
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
        tf_delta = delta_base.resample(rule).agg(delta=("bar_delta", "sum")).reset_index()
        tf_bars = tf_bars.merge(tf_delta, on="ts_event", how="left", validate="one_to_one")
        tf_bars["delta"] = tf_bars["delta"].fillna(0.0)
        tf_bars["range"] = tf_bars["high"] - tf_bars["low"]
        tf_bars["trend_sign"] = np.sign(tf_bars["close"] - tf_bars["open"]).astype(int)
        context[tf] = tf_bars

    return context


def attach_context(absorption: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    df = absorption.copy()
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
                "delta": f"delta_{tf}m",
                "range": f"range_{tf}m",
                "trend_sign": f"trend_sign_{tf}m",
            }
        )
        df = df.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def build_co_signal_flags(events: pd.DataFrame) -> pd.DataFrame:
    relevant = events[events["signal_id"].isin(CO_SIGNAL_IDS)].copy()
    if relevant.empty:
        return pd.DataFrame(columns=["global_index", "direction_sign", *[f"has_{signal_id}" for signal_id in CO_SIGNAL_IDS]])

    flags = relevant[["global_index", "direction_sign"]].drop_duplicates().copy()
    for signal_id in CO_SIGNAL_IDS:
        flagged = relevant.loc[
            relevant["signal_id"].eq(signal_id),
            ["global_index", "direction_sign"],
        ].drop_duplicates()
        flagged[f"has_{signal_id}"] = True
        flags = flags.merge(flagged, on=["global_index", "direction_sign"], how="left")
        flags[f"has_{signal_id}"] = flags[f"has_{signal_id}"].fillna(False).astype(bool)
    return flags


def add_regime_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["volatility_regime"] = pd.qcut(
        out["atr_20"],
        q=3,
        labels=["low_vol", "mid_vol", "high_vol"],
        duplicates="drop",
    )
    out["trend_alignment"] = np.where(
        out["direction_sign"] * np.where(out["bar_close"] >= out["sma_50"], 1, -1) > 0,
        "with_trend",
        "against_trend",
    )
    delta_side = np.sign(out["prior_delta_10"].fillna(0.0)) * out["direction_sign"]
    out["prior_delta_relation"] = np.select(
        [delta_side < 0, delta_side > 0, delta_side == 0],
        ["opposite_to_signal", "same_as_signal", "flat_zero"],
        default="flat_zero",
    )
    out["is_mid_vol"] = out["volatility_regime"].eq("mid_vol")
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]
    out["is_delta_opposite"] = out["prior_delta_relation"].eq("opposite_to_signal")

    rng_60m = out["range_60m"].replace(0, np.nan)
    anchor = np.where(out["direction_sign"] > 0, out["bar_low"], out["bar_high"])
    out["pos_60m"] = (anchor - out["low_60m"]) / rng_60m
    out["is_60m_extreme"] = (
        ((out["direction_sign"] > 0) & (out["pos_60m"] <= 0.20))
        | ((out["direction_sign"] < 0) & (out["pos_60m"] >= 0.80))
    )
    return out


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict:
    primary = df["ret_5b_ticks"].dropna()
    n = int(len(primary))
    wins = int((primary > 0).sum())
    ci_low, ci_high, win_rate = wilson_ci(n, wins)
    windows: dict[int, dict[str, float | int]] = {}

    for window in FORWARD_WINDOWS:
        ret = df[f"ret_{window}b_ticks"].dropna()
        windows[window] = {
            "n": int(len(ret)),
            "win_rate": float((ret > 0).mean()) if len(ret) else np.nan,
            "avg_return": float(ret.mean()) if len(ret) else np.nan,
            "median_return": float(ret.median()) if len(ret) else np.nan,
        }

    return {
        "code": code,
        "label": label,
        "n": n,
        "win_rate": win_rate,
        "wins": wins,
        "profit_factor": profit_factor(primary) if n else np.nan,
        "avg_return_5b_ticks": float(primary.mean()) if n else np.nan,
        "median_return_5b_ticks": float(primary.median()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "sharpe": sharpe_ratio(primary) if n else np.nan,
        "flag": status_flag(n, ci_low),
        "windows": windows,
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "absorption + 60m_extreme", lambda df: df["is_60m_extreme"]),
        ("02", "absorption + 15m_trend_aligned", lambda df: df["is_15m_trend_aligned"]),
        ("03", "absorption + mid_vol", lambda df: df["is_mid_vol"]),
        ("04", "absorption + delta_opposite", lambda df: df["is_delta_opposite"]),
        ("05", "absorption + has_TRAP_05", lambda df: df["has_TRAP_05"]),
        ("06", "absorption + has_TRAP_04", lambda df: df["has_TRAP_04"]),
        ("07", "absorption + has_EXH_03", lambda df: df["has_EXH_03"]),
        ("08", "absorption + has_EXH_04", lambda df: df["has_EXH_04"]),
        ("09", "absorption + has_VOLP_06", lambda df: df["has_VOLP_06"]),
        ("10", "absorption + has_AUCT_03", lambda df: df["has_AUCT_03"]),
        ("11", "absorption + 60m_extreme + has_TRAP_05", lambda df: df["is_60m_extreme"] & df["has_TRAP_05"]),
        ("12", "absorption + 60m_extreme + has_EXH_03", lambda df: df["is_60m_extreme"] & df["has_EXH_03"]),
        ("13", "absorption + 60m_extreme + 15m_trend_aligned", lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("14", "absorption + 15m_trend_aligned + has_TRAP_05", lambda df: df["is_15m_trend_aligned"] & df["has_TRAP_05"]),
        ("15", "absorption + mid_vol + has_TRAP_05", lambda df: df["is_mid_vol"] & df["has_TRAP_05"]),
        ("16", "absorption + delta_opposite + has_TRAP_05", lambda df: df["is_delta_opposite"] & df["has_TRAP_05"]),
        ("17", "absorption + 60m_extreme + mid_vol", lambda df: df["is_60m_extreme"] & df["is_mid_vol"]),
        ("18", "absorption + 60m_extreme + delta_opposite", lambda df: df["is_60m_extreme"] & df["is_delta_opposite"]),
        ("19", "absorption + 15m_trend_aligned + delta_opposite", lambda df: df["is_15m_trend_aligned"] & df["is_delta_opposite"]),
        ("20", "absorption + 60m_extreme + mid_vol + has_TRAP_05", lambda df: df["is_60m_extreme"] & df["is_mid_vol"] & df["has_TRAP_05"]),
        ("21", "absorption + 60m_extreme + 15m_trend_aligned + has_TRAP_05", lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["has_TRAP_05"]),
        ("22", "absorption + 15m_trend_aligned + delta_opposite + has_TRAP_05", lambda df: df["is_15m_trend_aligned"] & df["is_delta_opposite"] & df["has_TRAP_05"]),
        ("23", "absorption + 60m_extreme + delta_opposite + has_EXH_03", lambda df: df["is_60m_extreme"] & df["is_delta_opposite"] & df["has_EXH_03"]),
        ("24", "ABS_04 only", lambda df: df["has_ABS_04"]),
        ("25", "ABS_04 + 60m_extreme", lambda df: df["has_ABS_04"] & df["is_60m_extreme"]),
        ("26", "ABS_04 + 15m_trend_aligned", lambda df: df["has_ABS_04"] & df["is_15m_trend_aligned"]),
        ("27", "ABS_04 + has_TRAP_05", lambda df: df["has_ABS_04"] & df["has_TRAP_05"]),
        ("28", "ABS_04 + 60m_extreme + has_TRAP_05", lambda df: df["has_ABS_04"] & df["is_60m_extreme"] & df["has_TRAP_05"]),
        ("29", "ABS_04 + 15m_trend_aligned + has_TRAP_05", lambda df: df["has_ABS_04"] & df["is_15m_trend_aligned"] & df["has_TRAP_05"]),
        ("30", "ABS_04 + 60m_extreme + 15m_trend_aligned", lambda df: df["has_ABS_04"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
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


def render_window_detail(rows: list[dict]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        title = f"{row['code']}. {row['label']}"
        if row["flag"]:
            title = f"{title} [{row['flag']}]"
        lines.append(title)
        lines.append("  " + render_window_parts(row))
    return lines


def render_window_parts(row: dict) -> str:
    parts = []
    for window in FORWARD_WINDOWS:
        stats = row["windows"][window]
        parts.append(
            f"{window}b N={stats['n']:,} WR={fmt_pct(stats['win_rate'])} Avg={fmt_float(stats['avg_return'])} Med={fmt_float(stats['median_return'])}"
        )
    return " | ".join(parts)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    absorption = build_absorption_observations(events)
    bar_features = compute_bar_features(events)
    context = build_timeframe_context(bars_1m, events)
    co_flags = build_co_signal_flags(events)

    absorption = absorption.merge(
        bar_features[
            [
                "global_index",
                "atr_20",
                "sma_50",
                "session_vwap",
                "vwap_dist_ticks",
                "prior_delta_10",
                "price_vs_sma",
            ]
        ],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    absorption = attach_context(absorption, context)
    absorption = absorption.merge(
        co_flags,
        on=["global_index", "direction_sign"],
        how="left",
        validate="many_to_one",
    )
    for signal_id in CO_SIGNAL_IDS:
        col = f"has_{signal_id}"
        absorption[col] = absorption[col].fillna(False).astype(bool)
    absorption = add_regime_flags(absorption)

    baseline = summarize_filter("00", "All absorption", absorption)
    abs04_baseline = summarize_filter("24", "ABS_04 only", absorption[absorption["has_ABS_04"]].copy())
    results = run_filters(absorption)

    lines = [
        "DEEP6 compound absorption filter analysis",
        "========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique absorption bar grouped by global_index + direction.",
        "Co-fire logic: same global_index + same direction as the absorption observation.",
        "ABS_04 filters use grouped absorption observations that include ABS_04 among the same-bar absorption variants.",
        "Primary ranking window: 5 bars. Additional forward windows shown in detail section.",
        "Status flags: VALIDATED = N>=30 and Wilson lower bound >50%; PROMISING = N>=15 and Wilson lower bound >45%; LOW_N = N<15.",
        "",
        f"Absorption observations: {len(absorption):,}",
        f"5m bars built:  {len(context[5]):,}",
        f"15m bars built: {len(context[15]):,}",
        f"60m bars built: {len(context[60]):,}",
        "",
        "Baseline (all absorption, 5-bar window)",
        "--------------------------------------",
        f"N={baseline['n']:,} | WR={fmt_pct(baseline['win_rate'])} | PF={fmt_float(baseline['profit_factor'])} | Avg={fmt_float(baseline['avg_return_5b_ticks'])}t | Med={fmt_float(baseline['median_return_5b_ticks'])}t | CI={fmt_ci(baseline['ci_low'], baseline['ci_high'])} | Sharpe={fmt_float(baseline['sharpe'])}",
        "  " + render_window_parts(baseline),
        f"ABS_04 subset: N={abs04_baseline['n']:,} | WR={fmt_pct(abs04_baseline['win_rate'])} | PF={fmt_float(abs04_baseline['profit_factor'])} | Avg={fmt_float(abs04_baseline['avg_return_5b_ticks'])}t | Med={fmt_float(abs04_baseline['median_return_5b_ticks'])}t | CI={fmt_ci(abs04_baseline['ci_low'], abs04_baseline['ci_high'])} | Sharpe={fmt_float(abs04_baseline['sharpe'])}",
        "  " + render_window_parts(abs04_baseline),
        "",
        "Compound filters ranked by 5-bar average return",
        "-----------------------------------------------",
    ]
    lines.extend(render_table(results))
    lines.extend([
        "",
        "Forward window detail (returns in ticks)",
        "----------------------------------------",
    ])
    lines.extend(render_window_detail(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
