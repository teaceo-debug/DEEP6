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
OUT_PATH = OUT_DIR / "round2_stacked_persistence_time_report.txt"

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
        "bar_delta": "float64",
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
                "bar_high",
                "bar_low",
                "bar_close",
                "bar_delta",
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


def add_regime_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["volatility_regime"] = pd.qcut(
        out["atr_20"],
        q=3,
        labels=["low_vol", "mid_vol", "high_vol"],
        duplicates="drop",
    )
    out["is_mid_vol"] = out["volatility_regime"].eq("mid_vol")

    delta_side = np.sign(out["prior_delta_10"].fillna(0.0)) * out["direction_sign"]
    out["prior_delta_relation"] = np.select(
        [delta_side < 0, delta_side > 0, delta_side == 0],
        ["delta_opposite", "delta_same", "delta_flat"],
        default="delta_flat",
    )
    out["is_delta_opposite"] = out["prior_delta_relation"].eq("delta_opposite")
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

    out["is_first_30min"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(30)
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(60)
    out["is_last_hour"] = out["minutes_since_930"].ge(330) & out["minutes_since_930"].lt(390)
    out["is_hour_10_12"] = out["minutes_since_930"].ge(30) & out["minutes_since_930"].lt(150)

    lunch_mask = out["minutes_since_930"].ge(150) & out["minutes_since_930"].lt(270)
    out["is_not_lunch"] = ~lunch_mask
    out["is_not_monday"] = out["weekday"].ne("Monday")
    out["is_tuesday_thursday"] = out["weekday"].isin(["Tuesday", "Wednesday", "Thursday"])
    return out


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        (
            "01",
            "60m_extreme + 15m_trend_aligned + NOT lunch (12:00-14:00)",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_lunch"],
        ),
        (
            "02",
            "60m_extreme + 15m_trend_aligned + first_hour (09:30-10:30)",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_first_hour"],
        ),
        (
            "03",
            "60m_extreme + 15m_trend_aligned + last_hour (15:00-16:00)",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_last_hour"],
        ),
        (
            "04",
            "60m_extreme + 15m_trend_aligned + NOT first_30min + NOT lunch",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & ~df["is_first_30min"]
            & df["is_not_lunch"],
        ),
        (
            "05",
            "60m_extreme + 15m_trend_aligned + hour 10-12 only",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_hour_10_12"],
        ),
        (
            "06",
            "score_final >= 60 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["max_score_final"].ge(60)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
        ),
        (
            "07",
            "score_final >= 60 + 60m_extreme + 15m_trend_aligned + first_hour",
            lambda df: df["max_score_final"].ge(60)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_first_hour"],
        ),
        (
            "08",
            "score_final >= 70 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["max_score_final"].ge(70)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
        ),
        (
            "09",
            "score_final >= 70 + 60m_extreme + 15m_trend_aligned + last_hour",
            lambda df: df["max_score_final"].ge(70)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_last_hour"],
        ),
        (
            "10",
            "score_final >= 80 + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["max_score_final"].ge(80)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
        ),
        (
            "11",
            "3+ categories + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["category_count"].ge(3)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
        ),
        (
            "12",
            "4+ signals + 60m_extreme + 15m_trend_aligned + NOT lunch",
            lambda df: df["signal_count"].ge(4)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_not_lunch"],
        ),
        (
            "13",
            "3+ categories + 60m_extreme + 15m_trend_aligned + first_hour",
            lambda df: df["category_count"].ge(3)
            & df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_first_hour"],
        ),
        (
            "14",
            "5+ signals + 60m_extreme + 15m_trend_aligned",
            lambda df: df["signal_count"].ge(5) & df["is_60m_extreme"] & df["is_15m_trend_aligned"],
        ),
        (
            "15",
            "60m_extreme + 15m_trend_aligned + Friday",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["weekday"].eq("Friday"),
        ),
        (
            "16",
            "60m_extreme + 15m_trend_aligned + NOT Monday",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_not_monday"],
        ),
        (
            "17",
            "60m_extreme + 15m_trend_aligned + Tuesday-Thursday",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_tuesday_thursday"],
        ),
        (
            "18",
            "60m_extreme + 15m_trend_aligned + delta_opposite + NOT lunch",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["is_delta_opposite"]
            & df["is_not_lunch"],
        ),
        (
            "19",
            "60m_extreme + 15m_trend_aligned + mid_vol + NOT lunch",
            lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"] & df["is_mid_vol"] & df["is_not_lunch"],
        ),
        (
            "20",
            "60m_extreme + 15m_trend_aligned + score_final >= 60 + first_hour + NOT Monday",
            lambda df: df["is_60m_extreme"]
            & df["is_15m_trend_aligned"]
            & df["max_score_final"].ge(60)
            & df["is_first_hour"]
            & df["is_not_monday"],
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
        "sharpe": sharpe_ratio(returns_5b) if n else np.nan,
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
        "Sharpe",
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
                fmt_float(row["sharpe"]),
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
    bar_features = compute_bar_features(events)
    context = build_timeframe_context(bars_1m)

    observations = observations.merge(
        bar_features[["global_index", "atr_20", "prior_delta_10"]],
        on="global_index",
        how="left",
        validate="many_to_one",
    )
    observations = attach_context(observations, context)
    observations = add_regime_flags(observations)
    observations = add_time_flags(observations)
    results = run_filters(observations)

    base_mask = observations["is_60m_extreme"] & observations["is_15m_trend_aligned"]

    lines = [
        "DEEP6 round2 stacked persistence + time filter analysis",
        "=====================================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation.",
        "N uses rows with complete 5b/10b/15b/30b forward closes so persistence compares the same sample across windows.",
        "Base stack = 60m_extreme + 15m_trend_aligned. Score gates use grouped max score_final. Category/signal gates use grouped unique counts.",
        "mid_vol = middle ATR-20 tercile on unique 1-minute event bars. delta_opposite = sign of prior 10-bar session delta opposes signal direction.",
        "Time filters use bar_ts converted to America/New_York. lunch = 12:00-14:00, first_hour = 09:30-10:30, last_hour = 15:00-16:00, hour 10-12 = 10:00-11:59.",
        "Persistence: GROWING if WR_30b > WR_5b; STABLE if WR_30b is within 3 percentage points of WR_5b without growth; DECAYING otherwise.",
        "Sorted by 30b win rate descending.",
        "",
        f"Raw event rows loaded:                 {len(events):,}",
        f"Grouped observations:                  {len(observations):,}",
        f"15m bars built:                        {len(context[15]):,}",
        f"60m bars built:                        {len(context[60]):,}",
        f"15m trend aligned observations:        {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme observations:              {int(observations['is_60m_extreme'].sum()):,}",
        f"Base stack observations:               {int(base_mask.sum()):,}",
        f"Base stack + delta_opposite:           {int((base_mask & observations['is_delta_opposite']).sum()):,}",
        f"Base stack + mid_vol:                  {int((base_mask & observations['is_mid_vol']).sum()):,}",
        "",
        "20 requested stacked filters ranked by 30b win rate",
        "---------------------------------------------------",
    ]
    lines.extend(render_table(results))

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
