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
OUT_PATH = OUT_DIR / "round42_execution_simulation_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
TICK_SIZE = 0.25
DOLLARS_PER_TICK = 5.0
ROLLING_LOOKBACK = 20
RTH_START_MINUTE = 9 * 60 + 30
FIRST_HOUR_MINUTES = 60
LUNCH_START_MINUTES = 150
LUNCH_END_MINUTES = 270
BREAKEVEN_COMMISSION_DOLLARS = 1.40

Predicate = Callable[[pd.DataFrame], pd.Series]
DirectionFn = Callable[[pd.DataFrame], int | pd.Series]


@dataclass(frozen=True)
class SetupSpec:
    code: str
    label: str
    dataset_key: str
    observation_unit: str
    direction_label: str
    predicate: Predicate
    direction_fn: DirectionFn


@dataclass(frozen=True)
class FrictionSpec:
    code: str
    label: str
    slippage_ticks: float
    commission_dollars: float


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


def fmt_currency(value: float) -> str:
    if pd.isna(value):
        return "nan"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def fmt_ticks(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:,.2f}t"


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


def render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    lines = [
        " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)),
        "-+-".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))
    return lines


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
        "score_final",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        "bar_delta",
        "bar_volume",
        "fwd_close_5b",
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=cols, dtype=dtypes, low_memory=False)

    numeric_cols = [
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
        events[col] = pd.to_numeric(events[col], errors="coerce")

    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    events = events[events["bar_ts"].notna()].copy()
    events["event_direction_sign"] = direction_to_sign(events["direction"])
    return events.sort_values(["session_date", "bar_ts", "global_index", "signal_id"], kind="stable").reset_index(drop=True)


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
        low_memory=False,
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    return bars.sort_values("ts_event").reset_index(drop=True)


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


def attach_timeframe_context(df: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    out = df.copy()
    for tf, ctx in context.items():
        bucket_col = f"bucket_{tf}m"
        out[bucket_col] = out["bar_ts"].dt.floor(f"{tf}min")
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
        out = out.merge(renamed, on=bucket_col, how="left", validate="many_to_one")

    for col in ["bar_open", "bar_high", "bar_low", "bar_close", "bar_delta", "bar_volume", "fwd_close_5b"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.reset_index(drop=True)


def add_time_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hour"] = out["bar_ts"].dt.hour
    out["minute"] = out["bar_ts"].dt.minute
    out["minutes_since_930"] = (out["hour"] * 60 + out["minute"]) - RTH_START_MINUTE
    out["is_first_hour"] = out["minutes_since_930"].ge(0) & out["minutes_since_930"].lt(FIRST_HOUR_MINUTES)

    lunch_mask = out["minutes_since_930"].ge(LUNCH_START_MINUTES) & out["minutes_since_930"].lt(LUNCH_END_MINUTES)
    out["is_not_lunch"] = out["minutes_since_930"].notna() & (~lunch_mask)

    out["is_first_hour"] = out["is_first_hour"].fillna(False).astype(bool)
    out["is_not_lunch"] = out["is_not_lunch"].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def build_bar_frame(events: pd.DataFrame) -> pd.DataFrame:
    bars = (
        events.drop_duplicates(subset=["global_index"])
        .sort_values(["session_date", "bar_ts", "global_index"], kind="stable")
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
                "fwd_close_5b",
            ],
        ]
        .copy()
        .reset_index(drop=True)
    )
    bars["direction_sign"] = np.sign(bars["bar_delta"].fillna(0.0)).astype(int)
    return bars


def build_signal_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events[events["event_direction_sign"].ne(0)].copy()
    observations = (
        working.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
            max_score_final=("score_final", "max"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def build_absorption_observations(events: pd.DataFrame) -> pd.DataFrame:
    working = events[events["category"].eq("absorption") & events["event_direction_sign"].ne(0)].copy()
    observations = (
        working.groupby(["global_index", "event_direction_sign"], as_index=False, sort=False)
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
            absorption_signal_count=("signal_id", "nunique"),
        )
        .rename(columns={"event_direction_sign": "direction_sign"})
        .sort_values(["session_date", "bar_ts", "global_index", "direction_sign"], kind="stable")
        .reset_index(drop=True)
    )
    return observations


def compute_bar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    by_session = out.groupby("session_date", sort=False)

    out["bar_range"] = out["bar_high"] - out["bar_low"]
    out["body"] = (out["bar_close"] - out["bar_open"]).abs()
    out["is_doji"] = out["bar_range"].gt(0) & out["body"].lt(0.10 * out["bar_range"])

    out["rolling_20_ema_vol"] = by_session["bar_volume"].transform(
        lambda s: s.ewm(span=ROLLING_LOOKBACK, adjust=False, min_periods=ROLLING_LOOKBACK).mean().shift(1)
    )
    out["is_volume_spike_3x"] = out["rolling_20_ema_vol"].gt(0) & out["bar_volume"].gt(3.0 * out["rolling_20_ema_vol"])

    out["cvd"] = by_session["bar_delta"].cumsum()
    out["prior_session_price_high"] = by_session["bar_high"].transform(lambda s: s.cummax().shift(1))
    out["prior_session_price_low"] = by_session["bar_low"].transform(lambda s: s.cummin().shift(1))
    out["prior_cvd_high"] = by_session["cvd"].transform(lambda s: s.cummax().shift(1))
    out["prior_cvd_low"] = by_session["cvd"].transform(lambda s: s.cummin().shift(1))

    out["is_price_new_session_high"] = out["prior_session_price_high"].notna() & out["bar_high"].gt(out["prior_session_price_high"])
    out["is_price_new_session_low"] = out["prior_session_price_low"].notna() & out["bar_low"].lt(out["prior_session_price_low"])

    out["is_bearish_cvd_divergence"] = (
        out["is_price_new_session_high"]
        & out["prior_cvd_high"].notna()
        & out["cvd"].lt(out["prior_cvd_high"])
    )
    out["is_bullish_cvd_divergence"] = (
        out["is_price_new_session_low"]
        & out["prior_cvd_low"].notna()
        & out["cvd"].gt(out["prior_cvd_low"])
    )
    out["divergence_sign"] = np.select(
        [out["is_bullish_cvd_divergence"], out["is_bearish_cvd_divergence"]],
        [1, -1],
        default=0,
    ).astype(int)
    out["is_cvd_divergence"] = out["divergence_sign"].ne(0)

    bool_cols = [
        "is_doji",
        "is_volume_spike_3x",
        "is_bearish_cvd_divergence",
        "is_bullish_cvd_divergence",
        "is_cvd_divergence",
    ]
    for col in bool_cols:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def build_shared_bar_context(bar_frame: pd.DataFrame) -> pd.DataFrame:
    return bar_frame[["bar_ts", "is_first_hour", "is_not_lunch", "is_volume_spike_3x"]].copy()


def merge_shared_bar_context(df: pd.DataFrame, shared_bar_context: pd.DataFrame) -> pd.DataFrame:
    out = df.merge(shared_bar_context, on="bar_ts", how="left", validate="many_to_one")
    for col in ["is_first_hour", "is_not_lunch", "is_volume_spike_3x"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out.reset_index(drop=True)


def normalize_direction(direction: int | pd.Series, df: pd.DataFrame) -> pd.Series:
    if isinstance(direction, pd.Series):
        series = direction.reindex(df.index)
    else:
        series = pd.Series(direction, index=df.index)
    series = pd.to_numeric(series, errors="coerce").fillna(0.0)
    return pd.Series(np.sign(series), index=df.index).astype(int)


def anchor_pos_60m(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    rng_60m = df["range_60m"].replace(0, np.nan)
    anchor = np.where(direction_sign > 0, df["bar_low"], np.where(direction_sign < 0, df["bar_high"], np.nan))
    return pd.Series((anchor - df["low_60m"]) / rng_60m, index=df.index)


def has_core_60m_15m_gate_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    is_60m_extreme = ((direction_sign > 0) & pos_60m.le(0.20)) | ((direction_sign < 0) & pos_60m.ge(0.80))
    is_15m_trend_aligned = direction_sign.ne(0) & direction_sign.eq(df["trend_sign_15m"])
    return is_60m_extreme & is_15m_trend_aligned


def passes_not_all_killers_for(df: pd.DataFrame, direction: int | pd.Series) -> pd.Series:
    direction_sign = normalize_direction(direction, df)
    pos_60m = anchor_pos_60m(df, direction_sign)
    not_middle_60m = ~pos_60m.between(0.40, 0.60, inclusive="both")
    return direction_sign.ne(0) & not_middle_60m & (~df["is_volume_spike_3x"])


def build_setup_specs() -> list[SetupSpec]:
    return [
        SetupSpec(
            code="A",
            label="60m + 15m + NOT killers + first_hour",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="B",
            label="Doji + 60m + 15m + NOT killers",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = sign(bar_delta)",
            predicate=lambda df: df["is_doji"]
            & df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"]),
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="C",
            label="CVD divergence + 60m + 15m",
            dataset_key="bar",
            observation_unit="global_index (unique signal bar)",
            direction_label="trade direction = divergence_sign",
            predicate=lambda df: df["is_cvd_divergence"] & has_core_60m_15m_gate_for(df, df["divergence_sign"]),
            direction_fn=lambda df: df["divergence_sign"],
        ),
        SetupSpec(
            code="D",
            label="absorption + 60m + 15m + NOT lunch",
            dataset_key="absorption",
            observation_unit="global_index + direction (unique absorption signal direction)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & df["is_not_lunch"],
            direction_fn=lambda df: df["direction_sign"],
        ),
        SetupSpec(
            code="E",
            label="score >= 60 + 60m + 15m + first_hour + NOT killers",
            dataset_key="score",
            observation_unit="global_index + direction (unique signal observation)",
            direction_label="trade direction = signal direction",
            predicate=lambda df: df["direction_sign"].ne(0)
            & df["max_score_final"].ge(60)
            & has_core_60m_15m_gate_for(df, df["direction_sign"])
            & passes_not_all_killers_for(df, df["direction_sign"])
            & df["is_first_hour"],
            direction_fn=lambda df: df["direction_sign"],
        ),
    ]


def build_friction_specs() -> list[FrictionSpec]:
    return [
        FrictionSpec(code="0", label="Zero", slippage_ticks=0.0, commission_dollars=0.0),
        FrictionSpec(code="1", label="Light", slippage_ticks=2.0, commission_dollars=1.40),
        FrictionSpec(code="2", label="Medium", slippage_ticks=4.0, commission_dollars=1.40),
        FrictionSpec(code="3", label="Heavy", slippage_ticks=6.0, commission_dollars=2.00),
    ]


def build_analysis_frames() -> dict[str, pd.DataFrame]:
    events = load_events()
    bars_1m = load_ohlcv()
    context = build_timeframe_context(bars_1m)

    bar_frame = build_bar_frame(events)
    bar_frame = attach_timeframe_context(bar_frame, context)
    bar_frame = add_time_flags(bar_frame)
    bar_frame = compute_bar_features(bar_frame)

    shared_bar_context = build_shared_bar_context(bar_frame)

    score_frame = build_signal_observations(events)
    score_frame = attach_timeframe_context(score_frame, context)
    score_frame = merge_shared_bar_context(score_frame, shared_bar_context)

    absorption_frame = build_absorption_observations(events)
    absorption_frame = attach_timeframe_context(absorption_frame, context)
    absorption_frame = merge_shared_bar_context(absorption_frame, shared_bar_context)

    return {
        "bar": bar_frame,
        "score": score_frame,
        "absorption": absorption_frame,
    }


def build_setup_sample(source_df: pd.DataFrame, spec: SetupSpec) -> pd.DataFrame:
    mask = spec.predicate(source_df).fillna(False)
    sample = source_df.loc[mask].copy()

    direction = spec.direction_fn(source_df)
    sample["trade_sign"] = normalize_direction(direction, sample)
    sample = sample.loc[sample["trade_sign"].ne(0)].copy()
    sample = sample.dropna(subset=["bar_close", "fwd_close_5b"]).copy()
    sample["ret_5b_ticks"] = sample["trade_sign"] * ((sample["fwd_close_5b"] - sample["bar_close"]) / TICK_SIZE)
    return sample.reset_index(drop=True)


def adjust_returns(returns: pd.Series, friction: FrictionSpec) -> pd.Series:
    total_cost_ticks = friction.slippage_ticks + (friction.commission_dollars / DOLLARS_PER_TICK)
    return returns - total_cost_ticks


def compute_friction_metrics(sample: pd.DataFrame, friction: FrictionSpec) -> dict[str, object]:
    raw_returns = pd.to_numeric(sample["ret_5b_ticks"], errors="coerce").dropna()
    adjusted = adjust_returns(raw_returns, friction)
    n = int(len(adjusted))

    avg_dollars = float(adjusted.mean() * DOLLARS_PER_TICK) if n else np.nan
    net_dollars = float(adjusted.sum() * DOLLARS_PER_TICK) if n else np.nan

    return {
        "friction": friction,
        "n": n,
        "win_rate": float((adjusted > 0).mean()) if n else np.nan,
        "profit_factor": profit_factor(adjusted) if n else np.nan,
        "avg_dollars": avg_dollars,
        "net_dollars": net_dollars,
        "sharpe": sharpe_ratio(adjusted) if n else np.nan,
    }


def break_even_slippage_ticks(returns: pd.Series, commission_dollars: float = BREAKEVEN_COMMISSION_DOLLARS) -> float:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return np.nan

    commission_ticks = commission_dollars / DOLLARS_PER_TICK
    commission_only_pf = profit_factor(clean - commission_ticks)
    if not np.isfinite(commission_only_pf) and commission_only_pf > 1.0:
        commission_only_pf = float("inf")
    if commission_only_pf <= 1.0:
        return np.nan

    lo = 0.0
    hi = max(1.0, float(clean.max() - commission_ticks + 1.0))
    for _ in range(60):
        mid = (lo + hi) / 2.0
        pf_mid = profit_factor(clean - commission_ticks - mid)
        if pf_mid > 1.0:
            lo = mid
        else:
            hi = mid
    return float(lo)


def analyze_setup(spec: SetupSpec, frames: dict[str, pd.DataFrame], frictions: list[FrictionSpec]) -> dict[str, object]:
    sample = build_setup_sample(frames[spec.dataset_key], spec)
    rows = [compute_friction_metrics(sample, friction) for friction in frictions]
    return {
        "setup": spec,
        "sample_n": int(len(sample)),
        "break_even_slippage_ticks": break_even_slippage_ticks(sample["ret_5b_ticks"]),
        "rows": rows,
    }


def run_analysis() -> list[dict[str, object]]:
    frames = build_analysis_frames()
    frictions = build_friction_specs()
    return [analyze_setup(spec, frames, frictions) for spec in build_setup_specs()]


def render_execution_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Setup", "Friction", "N", "WR", "PF", "Avg $/trade", "Net $", "Sharpe", "Break-even slip*"]
    rows: list[list[str]] = []

    for result in results:
        break_even = result["break_even_slippage_ticks"]
        break_even_text = fmt_ticks(float(break_even)) if not pd.isna(break_even) else "n/a"

        for idx, metrics in enumerate(result["rows"]):
            friction = metrics["friction"]
            rows.append(
                [
                    f"{result['setup'].code}. {result['setup'].label}" if idx == 0 else "",
                    f"{friction.label} ({fmt_ticks(friction.slippage_ticks)} + {fmt_currency(friction.commission_dollars)})",
                    f"{int(metrics['n']):,}",
                    fmt_pct(float(metrics["win_rate"])) if not pd.isna(metrics["win_rate"]) else "nan",
                    fmt_float(float(metrics["profit_factor"])) if not pd.isna(metrics["profit_factor"]) else "nan",
                    fmt_currency(float(metrics["avg_dollars"])) if not pd.isna(metrics["avg_dollars"]) else "nan",
                    fmt_currency(float(metrics["net_dollars"])) if not pd.isna(metrics["net_dollars"]) else "nan",
                    fmt_float(float(metrics["sharpe"])) if not pd.isna(metrics["sharpe"]) else "nan",
                    break_even_text if idx == 0 else "",
                ]
            )

    return render_table(headers, rows)


def render_break_even_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Setup", "Observation unit", "Direction", "Break-even slippage*"]
    rows: list[list[str]] = []

    for result in results:
        spec = result["setup"]
        break_even = result["break_even_slippage_ticks"]
        rows.append(
            [
                f"{spec.code}. {spec.label}",
                spec.observation_unit,
                spec.direction_label,
                fmt_ticks(float(break_even)) if not pd.isna(break_even) else "n/a",
            ]
        )

    return render_table(headers, rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = run_analysis()

    lines = [
        "DEEP6 round42 execution friction simulation",
        "==========================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Forward horizon: 5 bars only.",
        "Adjusted return formula: ret_5b_ticks - slippage_ticks - (commission_dollars / 5.0).",
        "Dollar P&L assumes 1 NQ contract at $5.00 per tick.",
        "Setup definitions match prior round40/round41 execution-style filters and round2/round8/round29/round34 context gates.",
        "Lunch window uses 12:00-13:59 ET (minutes since 09:30 in [150, 270)).",
        "Break-even slippage* holds round-trip commission fixed at $1.40 and solves the max additional slippage where PF stays > 1.0.",
        "If break-even slippage is n/a, PF is already <= 1.0 with commission-only friction.",
        "",
        "Execution table",
        "---------------",
    ]
    lines.extend(render_execution_table(results))
    lines.extend(
        [
            "",
            "Break-even slippage summary",
            "---------------------------",
        ]
    )
    lines.extend(render_break_even_table(results))
    lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
