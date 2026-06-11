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
OUT_PATH = OUT_DIR / "round2_absorption_deep_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
FORWARD_WINDOWS = (5, 10, 15, 30)
TICK_SIZE = 0.25
CO_SIGNAL_IDS = ("TRAP_04", "TRAP_05", "EXH_03", "DELT_04")


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
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
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


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    abs_ev = events[events["category"] == "absorption"].copy()
    observations = (
        abs_ev.groupby(["global_index", "direction_sign"], as_index=False, sort=False)
        .agg(
            session_date=("session_date", "first"),
            bar_ts=("bar_ts", "first"),
            bar_index=("bar_index", "first"),
            signal_ids=("signal_id", lambda s: ",".join(sorted(set(s)))),
            has_ABS_04=("signal_id", lambda s: "ABS_04" in set(s)),
            absorption_variants=("signal_id", "nunique"),
            strength=("strength", "max"),
            score_final=("score_final", "max"),
            bar_open=("bar_open", "first"),
            bar_high=("bar_high", "first"),
            bar_low=("bar_low", "first"),
            bar_close=("bar_close", "first"),
            bar_delta=("bar_delta", "first"),
            bar_volume=("bar_volume", "first"),
            fwd_close_5b=("fwd_close_5b", "first"),
            fwd_close_10b=("fwd_close_10b", "first"),
            fwd_close_15b=("fwd_close_15b", "first"),
            fwd_close_30b=("fwd_close_30b", "first"),
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
    bars["prior_delta_10"] = (
        bars.groupby("session_date", sort=False)["bar_delta"]
        .transform(lambda s: s.shift(1).rolling(10, min_periods=10).sum())
    )
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
    delta_side = np.sign(out["prior_delta_10"].fillna(0.0)) * out["direction_sign"]
    out["prior_delta_relation"] = np.select(
        [delta_side < 0, delta_side > 0, delta_side == 0],
        ["opposite_to_signal", "same_as_signal", "flat_zero"],
        default="flat_zero",
    )
    out["is_mid_vol"] = out["volatility_regime"].eq("mid_vol")
    out["is_15m_trend_aligned"] = out["direction_sign"] == out["trend_sign_15m"]
    out["is_delta_opposite"] = out["prior_delta_relation"].eq("opposite_to_signal")
    out["is_score_ge_60"] = out["score_final"].ge(60)

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

    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)
    out["is_last_hour"] = out["minutes_since_930"].ge(330) & out["minutes_since_930"].lt(390)
    out["is_not_monday"] = out["weekday"].ne("Monday")
    return out


def summarize_filter(code: str, label: str, df: pd.DataFrame) -> dict:
    windows: dict[int, dict[str, float | int]] = {}

    for window in FORWARD_WINDOWS:
        returns = df[f"ret_{window}b_ticks"].dropna()
        wins = int((returns > 0).sum())
        window_n = int(len(returns))
        windows[window] = {
            "n": window_n,
            "win_rate": (wins / window_n) if window_n else np.nan,
            "avg_return": float(returns.mean()) if window_n else np.nan,
        }

    returns_5b = df["ret_5b_ticks"].dropna()
    n = int(len(returns_5b))
    wins_5b = int((returns_5b > 0).sum())
    ci_low, ci_high, win_rate_5b = wilson_ci(n, wins_5b)

    return {
        "code": code,
        "label": label,
        "n": n,
        "wr_5b": win_rate_5b,
        "wr_10b": windows[10]["win_rate"],
        "wr_15b": windows[15]["win_rate"],
        "wr_30b": windows[30]["win_rate"],
        "pf_5b": profit_factor(returns_5b) if n else np.nan,
        "avg_ticks_5b": float(returns_5b.mean()) if n else np.nan,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "persistence": classify_persistence(win_rate_5b, windows[30]["win_rate"]),
        "windows": windows,
    }


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        (
            "01",
            "absorption + 60m_extreme + 15m_trend + NOT lunch (12:00-14:00)",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_lunch"],
        ),
        (
            "02",
            "absorption + 60m_extreme + 15m_trend + last_hour (15:00-16:00)",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_last_hour"],
        ),
        (
            "03",
            "absorption + 60m_extreme + 15m_trend + first_hour",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_first_hour"],
        ),
        (
            "04",
            "absorption + 60m_extreme + 15m_trend + NOT Monday",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_monday"],
        ),
        (
            "05",
            "absorption + 60m_extreme + 15m_trend + has_TRAP_05 + NOT lunch",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["has_TRAP_05"]
            & df["is_not_lunch"],
        ),
        (
            "06",
            "absorption + 60m_extreme + 15m_trend + has_EXH_03 + NOT lunch",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["has_EXH_03"]
            & df["is_not_lunch"],
        ),
        (
            "07",
            "absorption + 60m_extreme + has_TRAP_04 + NOT lunch",
            lambda df: df["is_60m_extreme"] & df["has_TRAP_04"] & df["is_not_lunch"],
        ),
        (
            "08",
            "absorption + 60m_extreme + 15m_trend + has_DELT_04",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["has_DELT_04"],
        ),
        (
            "09",
            "absorption + 60m_extreme + 15m_trend + delta_opposite",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_delta_opposite"],
        ),
        (
            "10",
            "absorption + 60m_extreme + 15m_trend + mid_vol",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_mid_vol"],
        ),
        (
            "11",
            "absorption + 60m_extreme + 15m_trend + delta_opposite + NOT lunch",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_delta_opposite"]
            & df["is_not_lunch"],
        ),
        (
            "12",
            "absorption + 60m_extreme + 15m_trend + score >= 60",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_score_ge_60"],
        ),
        (
            "13",
            "ABS_04 + 60m_extreme + 15m_trend + NOT lunch",
            lambda df: df["has_ABS_04"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_lunch"],
        ),
        (
            "14",
            "ABS_04 + 60m_extreme + 15m_trend + last_hour",
            lambda df: df["has_ABS_04"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_last_hour"],
        ),
        (
            "15",
            "ABS_04 + 60m_extreme + 15m_trend + has_TRAP_05",
            lambda df: df["has_ABS_04"] & df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["has_TRAP_05"],
        ),
    ]


def run_filters(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    for code, label, predicate in build_filter_specs():
        mask = predicate(df)
        results.append(summarize_filter(code, label, df[mask].copy()))
    return results


def render_table(rows: list[dict]) -> list[str]:
    headers = ["Filter", "N", "WR 5b", "WR 10b", "WR 15b", "WR 30b", "PF 5b", "Avg Ticks 5b", "Wilson 95% CI (5b)", "Persistence"]
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


def render_window_parts(row: dict) -> str:
    parts = []
    for window in FORWARD_WINDOWS:
        stats = row["windows"][window]
        parts.append(f"{window}b N={stats['n']:,} WR={fmt_pct(stats['win_rate'])} Avg={fmt_float(stats['avg_return'])}")
    return " | ".join(parts)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_absorption_observations(events)
    bar_features = compute_bar_features(events)
    context = build_timeframe_context(bars_1m)
    co_flags = build_co_signal_flags(events)

    observations = observations.merge(
        bar_features[["global_index", "atr_20", "prior_delta_10"]],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_context(observations, context)
    observations = observations.merge(
        co_flags,
        on=["global_index", "direction_sign"],
        how="left",
        validate="many_to_one",
    )
    for signal_id in CO_SIGNAL_IDS:
        col = f"has_{signal_id}"
        observations[col] = observations[col].fillna(False).astype(bool)
    observations = add_regime_flags(observations)
    observations = add_time_flags(observations)

    baseline = summarize_filter("00", "All absorption observations", observations)
    core_stack = summarize_filter(
        "00x",
        "absorption + 60m_extreme + 15m_trend",
        observations[observations["is_60m_extreme"] & observations["is_15m_trend_aligned"]].copy(),
    )
    abs04_core = summarize_filter(
        "00y",
        "ABS_04 + 60m_extreme + 15m_trend",
        observations[
            observations["has_ABS_04"] & observations["is_60m_extreme"] & observations["is_15m_trend_aligned"]
        ].copy(),
    )
    results = run_filters(observations)

    lines = [
        "DEEP6 round2 absorption deep filter analysis",
        "===========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique absorption observation grouped by global_index + direction_sign using only rows where category == 'absorption'.",
        "Co-fire logic: same global_index + same direction pulled from ALL events, then merged back onto the grouped absorption observation.",
        "Time filters use America/New_York and minutes_since_930 from round1_time_day_filters.py.",
        "N / PF / Avg Ticks / Wilson CI use the 5-bar sample. 10b/15b/30b WRs use the available sample for each horizon; the baseline detail lines show per-window N.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "PF and Avg Ticks columns are for the 5-bar window.",
        "Requested filters are shown in the exact order requested.",
        "",
        f"Raw event rows loaded:        {len(events):,}",
        f"Absorption observations:      {len(observations):,}",
        f"15m bars built:               {len(context[15]):,}",
        f"60m bars built:               {len(context[60]):,}",
        f"60m_extreme + 15m_trend obs:  {int((observations['is_60m_extreme'] & observations['is_15m_trend_aligned']).sum()):,}",
        f"ABS_04 observations:          {int(observations['has_ABS_04'].sum()):,}",
        "",
        "Baselines",
        "---------",
        f"All absorption: N={baseline['n']:,} | WR5={fmt_pct(baseline['wr_5b'])} | PF5={fmt_float(baseline['pf_5b'])} | Avg5={fmt_float(baseline['avg_ticks_5b'])}t | CI5={fmt_ci(baseline['ci_low'], baseline['ci_high'])} | Persistence={baseline['persistence']}",
        "  " + render_window_parts(baseline),
        f"Core stack: N={core_stack['n']:,} | WR5={fmt_pct(core_stack['wr_5b'])} | PF5={fmt_float(core_stack['pf_5b'])} | Avg5={fmt_float(core_stack['avg_ticks_5b'])}t | CI5={fmt_ci(core_stack['ci_low'], core_stack['ci_high'])} | Persistence={core_stack['persistence']}",
        "  " + render_window_parts(core_stack),
        f"ABS_04 core: N={abs04_core['n']:,} | WR5={fmt_pct(abs04_core['wr_5b'])} | PF5={fmt_float(abs04_core['pf_5b'])} | Avg5={fmt_float(abs04_core['avg_ticks_5b'])}t | CI5={fmt_ci(abs04_core['ci_low'], abs04_core['ci_high'])} | Persistence={abs04_core['persistence']}",
        "  " + render_window_parts(abs04_core),
        "",
        "15 requested deep filters",
        "-------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
