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
OUT_PATH = OUT_DIR / "top5_validation_report.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (5, 15, 60)
FORWARD_WINDOWS = (5, 10, 15, 30)
TICK_SIZE = 0.25
PRIMARY_WINDOW = 5
WALK_FORWARD_WINDOWS = 6
BETA_PRIOR_ALPHA = 10
BETA_PRIOR_BETA = 10


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


def fmt_ticks(value: float) -> str:
    if pd.isna(value):
        return "nan"
    if np.isinf(value):
        return "inf"
    return f"{value:+,.2f}"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


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


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("F1", "absorption + 60m_extreme + 15m_trend_aligned", lambda df: df["is_60m_extreme"] & df["is_15m_trend_aligned"]),
        ("F2", "absorption + 15m_trend_aligned + delta_opposite", lambda df: df["is_15m_trend_aligned"] & df["is_delta_opposite"]),
        ("F3", "absorption + 60m_extreme + mid_vol", lambda df: df["is_60m_extreme"] & df["is_mid_vol"]),
        ("F4", "absorption + 60m_extreme + delta_opposite", lambda df: df["is_60m_extreme"] & df["is_delta_opposite"]),
        ("F5", "absorption + 60m_extreme", lambda df: df["is_60m_extreme"]),
    ]


def prep_validation_frame() -> pd.DataFrame:
    events = load_events()
    bars_1m = load_ohlcv()
    absorption = build_absorption_observations(events)
    bar_features = compute_bar_features(events)
    context = build_timeframe_context(bars_1m, events)

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
    absorption = add_regime_flags(absorption)
    absorption["session_date_dt"] = pd.to_datetime(absorption["session_date"], errors="coerce")
    absorption["session_month"] = absorption["session_date_dt"].dt.to_period("M")
    absorption["hour_et"] = absorption["bar_ts"].dt.hour
    absorption = absorption.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True)
    return absorption


def month_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b %Y")


def month_short_label(period_value: pd.Period) -> str:
    return period_value.to_timestamp().strftime("%b-%y")


def format_is_label(is_months: list[pd.Period]) -> str:
    if not is_months:
        return "n/a"
    if len(is_months) == 1:
        return month_label(is_months[0])
    first = is_months[0].to_timestamp()
    last = is_months[-1].to_timestamp()
    if first.year == last.year:
        return f"{first.strftime('%b')}-{last.strftime('%b %Y')}"
    return f"{first.strftime('%b %Y')}-{last.strftime('%b %Y')}"


def build_walk_forward_windows(df: pd.DataFrame, window_count: int = WALK_FORWARD_WINDOWS) -> list[dict[str, object]]:
    months = [period for period in sorted(df["session_month"].dropna().unique())]
    if len(months) < 3:
        return []

    oos_indices = np.linspace(2, len(months) - 1, num=min(window_count, len(months) - 2))
    oos_indices = np.round(oos_indices).astype(int)
    oos_indices = np.unique(oos_indices)

    windows: list[dict[str, object]] = []
    for idx, oos_idx in enumerate(oos_indices, start=1):
        is_months = months[oos_idx - 2 : oos_idx]
        oos_month = months[oos_idx]
        windows.append(
            {
                "window_num": idx,
                "is_months": is_months,
                "oos_month": oos_month,
                "label": f"{format_is_label(is_months)} IS → {month_label(oos_month)} OOS",
            }
        )
    return windows


def win_rate(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    return float((returns > 0).mean())


def walk_forward_analysis(df: pd.DataFrame, windows: list[dict[str, object]]) -> dict[str, object]:
    oos_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    weak_windows: list[str] = []

    for window in windows:
        oos_month = window["oos_month"]
        window_df = df.loc[df["session_month"].eq(oos_month)].copy()
        ret = window_df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
        n = int(len(ret))
        wr = win_rate(ret)
        avg_ticks = float(ret.mean()) if n else float("nan")
        rows.append(
            {
                "window_num": int(window["window_num"]),
                "label": str(window["label"]),
                "n": n,
                "wr": wr,
                "avg_ticks": avg_ticks,
            }
        )
        if n and wr < 0.40:
            weak_windows.append(str(window["label"]))
        if n:
            oos_frames.append(window_df)

    oos_df = pd.concat(oos_frames, ignore_index=True) if oos_frames else df.iloc[0:0].copy()
    oos_ret = oos_df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
    oos_n = int(len(oos_ret))
    oos_wr = win_rate(oos_ret)
    oos_avg = float(oos_ret.mean()) if oos_n else float("nan")

    if oos_n == 0:
        status = "FAIL"
        reason = "no out-of-sample trades"
    elif weak_windows:
        status = "FAIL"
        reason = f"{len(weak_windows)} OOS window(s) below 40% WR"
    else:
        status = "PASS"
        reason = "no OOS window below 40% WR"

    return {
        "rows": rows,
        "oos_n": oos_n,
        "oos_wr": oos_wr,
        "oos_avg_ticks": oos_avg,
        "status": status,
        "reason": reason,
    }


def monthly_stability(df: pd.DataFrame) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for month, grp in df.groupby("session_month", sort=True):
        ret = grp[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
        n = int(len(ret))
        wr = win_rate(ret)
        avg_ticks = float(ret.mean()) if n else float("nan")
        rows.append(
            {
                "month": month,
                "label": month_short_label(month),
                "n": n,
                "wr": wr,
                "avg_ticks": avg_ticks,
            }
        )

    active_rows = [row for row in rows if row["n"] > 0]
    good_months = sum(1 for row in active_rows if row["wr"] > 0.50)

    longest_losing_streak = 0
    current_losing_streak = 0
    flagged_bad_months: list[str] = []
    for row in active_rows:
        if row["wr"] < 0.50:
            current_losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, current_losing_streak)
        else:
            current_losing_streak = 0
        if row["n"] >= 3 and row["wr"] < 0.35:
            flagged_bad_months.append(row["label"])

    if not active_rows:
        status = "FAIL"
        reason = "no monthly trades"
    elif flagged_bad_months:
        status = "FAIL"
        reason = f"month(s) below 35% WR with N>=3: {', '.join(flagged_bad_months)}"
    else:
        status = "PASS"
        reason = "no month below 35% WR with N>=3"

    return {
        "rows": rows,
        "active_months": len(active_rows),
        "good_months": good_months,
        "longest_losing_streak": longest_losing_streak,
        "flagged_bad_months": flagged_bad_months,
        "status": status,
        "reason": reason,
    }


def time_of_day_analysis(df: pd.DataFrame) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for hour in range(9, 16):
        grp = df.loc[df["hour_et"].eq(hour)]
        ret = grp[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
        n = int(len(ret))
        wr = win_rate(ret)
        avg_ticks = float(ret.mean()) if n else float("nan")
        rows.append({"hour": hour, "n": n, "wr": wr, "avg_ticks": avg_ticks})

    active = [row for row in rows if row["n"] > 0]
    best = max(active, key=lambda row: (row["avg_ticks"], row["wr"], row["n"])) if active else None
    worst = min(active, key=lambda row: (row["avg_ticks"], row["wr"], -row["n"])) if active else None
    return {"rows": rows, "best": best, "worst": worst}


def streak_analysis(df: pd.DataFrame) -> dict[str, object]:
    ret = df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
    outcomes = (ret > 0).tolist()
    if not outcomes:
        return {
            "max_win_streak": 0,
            "max_loss_streak": 0,
            "avg_win_streak": float("nan"),
            "avg_loss_streak": float("nan"),
        }

    win_streaks: list[int] = []
    loss_streaks: list[int] = []
    current_is_win = outcomes[0]
    current_length = 1

    for outcome in outcomes[1:]:
        if outcome == current_is_win:
            current_length += 1
            continue
        if current_is_win:
            win_streaks.append(current_length)
        else:
            loss_streaks.append(current_length)
        current_is_win = outcome
        current_length = 1

    if current_is_win:
        win_streaks.append(current_length)
    else:
        loss_streaks.append(current_length)

    return {
        "max_win_streak": max(win_streaks) if win_streaks else 0,
        "max_loss_streak": max(loss_streaks) if loss_streaks else 0,
        "avg_win_streak": float(np.mean(win_streaks)) if win_streaks else float("nan"),
        "avg_loss_streak": float(np.mean(loss_streaks)) if loss_streaks else float("nan"),
    }


def drawdown_analysis(df: pd.DataFrame) -> dict[str, object]:
    trade_df = df.dropna(subset=[f"ret_{PRIMARY_WINDOW}b_ticks"]).copy()
    if trade_df.empty:
        return {"max_drawdown_ticks": float("nan"), "max_drawdown_duration_bars": 0}

    trade_df = trade_df.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True)
    equity = trade_df[f"ret_{PRIMARY_WINDOW}b_ticks"].cumsum()
    running_peak = equity.cummax()
    drawdown = running_peak - equity
    max_drawdown_ticks = float(drawdown.max()) if not drawdown.empty else float("nan")

    peak_equity = 0.0
    peak_global_index = int(trade_df.loc[0, "global_index"])
    underwater_start: int | None = None
    max_duration = 0

    cumulative = 0.0
    for row in trade_df[["global_index", f"ret_{PRIMARY_WINDOW}b_ticks"]].itertuples(index=False):
        cumulative += float(getattr(row, f"ret_{PRIMARY_WINDOW}b_ticks"))
        global_index = int(row.global_index)
        if cumulative >= peak_equity:
            if underwater_start is not None:
                max_duration = max(max_duration, global_index - underwater_start)
                underwater_start = None
            peak_equity = cumulative
            peak_global_index = global_index
        elif underwater_start is None:
            underwater_start = peak_global_index

    if underwater_start is not None:
        last_global = int(trade_df["global_index"].iloc[-1])
        max_duration = max(max_duration, last_global - underwater_start)

    return {"max_drawdown_ticks": max_drawdown_ticks, "max_drawdown_duration_bars": int(max_duration)}


def beta_credible_interval(alpha: float, beta_value: float, level: float = 0.95) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    try:
        from scipy.stats import beta as scipy_beta

        low = float(scipy_beta.ppf(tail, alpha, beta_value))
        high = float(scipy_beta.ppf(1.0 - tail, alpha, beta_value))
        return low, high
    except Exception:
        mean = alpha / (alpha + beta_value)
        var = (alpha * beta_value) / (((alpha + beta_value) ** 2) * (alpha + beta_value + 1.0))
        z = 1.959963984540054
        margin = z * math.sqrt(var)
        return max(0.0, mean - margin), min(1.0, mean + margin)


def bayesian_analysis(df: pd.DataFrame) -> dict[str, object]:
    ret = df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
    n = int(len(ret))
    wins = int((ret > 0).sum())
    losses = n - wins
    posterior_alpha = BETA_PRIOR_ALPHA + wins
    posterior_beta = BETA_PRIOR_BETA + losses
    observed_wr = win_rate(ret)
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta) if n or BETA_PRIOR_ALPHA or BETA_PRIOR_BETA else float("nan")
    ci_low, ci_high = beta_credible_interval(posterior_alpha, posterior_beta)
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "observed_wr": observed_wr,
        "posterior_alpha": posterior_alpha,
        "posterior_beta": posterior_beta,
        "posterior_mean": float(posterior_mean),
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def overall_verdict(walk_forward: dict[str, object], monthly: dict[str, object], bayes: dict[str, object]) -> str:
    oos_wr = float(walk_forward["oos_wr"])
    posterior_mean = float(bayes["posterior_mean"])
    has_bad_month = bool(monthly["flagged_bad_months"])
    if not pd.isna(oos_wr) and oos_wr > 0.55 and not has_bad_month and posterior_mean > 0.55:
        return "DEPLOY"
    if not pd.isna(oos_wr) and oos_wr > 0.50 and posterior_mean > 0.50:
        return "PAPER TRADE"
    return "INSUFFICIENT DATA"


def validate_filter(df: pd.DataFrame, filter_code: str, label: str, windows: list[dict[str, object]]) -> dict[str, object]:
    trade_df = df.dropna(subset=[f"ret_{PRIMARY_WINDOW}b_ticks"]).copy()
    primary = trade_df[f"ret_{PRIMARY_WINDOW}b_ticks"]
    walk_forward = walk_forward_analysis(trade_df, windows)
    monthly = monthly_stability(trade_df)
    tod = time_of_day_analysis(trade_df)
    streaks = streak_analysis(trade_df)
    drawdown = drawdown_analysis(trade_df)
    bayes = bayesian_analysis(trade_df)
    return {
        "filter_code": filter_code,
        "label": label,
        "n": int(len(primary)),
        "wr": win_rate(primary),
        "pf": profit_factor(primary) if len(primary) else float("nan"),
        "avg_ticks": float(primary.mean()) if len(primary) else float("nan"),
        "walk_forward": walk_forward,
        "monthly": monthly,
        "time_of_day": tod,
        "streaks": streaks,
        "drawdown": drawdown,
        "bayes": bayes,
        "verdict": overall_verdict(walk_forward, monthly, bayes),
    }


def render_time_of_day_lines(tod: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for row in tod["rows"]:
        lines.append(
            f"  {int(row['hour']):02d}h: N={int(row['n'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    best = tod["best"]
    worst = tod["worst"]
    if best is None:
        lines.append("  Best: n/a")
        lines.append("  Worst: n/a")
    else:
        lines.append(f"  Best: {int(best['hour']):02d}h (N={int(best['n'])}, WR={fmt_pct(float(best['wr']))}, Avg={fmt_ticks(float(best['avg_ticks']))} ticks)")
        lines.append(f"  Worst: {int(worst['hour']):02d}h (N={int(worst['n'])}, WR={fmt_pct(float(worst['wr']))}, Avg={fmt_ticks(float(worst['avg_ticks']))} ticks)")
    return lines


def render_filter_report(result: dict[str, object]) -> list[str]:
    walk_forward = result["walk_forward"]
    monthly = result["monthly"]
    bayes = result["bayes"]
    streaks = result["streaks"]
    drawdown = result["drawdown"]

    lines = [
        f"FILTER {result['filter_code'][1:]}: {result['label']}",
        "-" * (10 + len(result["label"])),
        f"Summary: N={result['n']:,}, WR={fmt_pct(float(result['wr']))}, PF={fmt_float(float(result['pf']))}, Avg={fmt_ticks(float(result['avg_ticks']))} ticks",
        "",
        f"A) Walk-Forward ({len(walk_forward['rows'])} windows):",
    ]
    for row in walk_forward["rows"]:
        lines.append(
            f"  Window {int(row['window_num'])} ({row['label']}): N={int(row['n'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Overall OOS: N={int(walk_forward['oos_n'])}, WR={fmt_pct(float(walk_forward['oos_wr']))}, Avg={fmt_ticks(float(walk_forward['oos_avg_ticks']))} ticks",
            f"  [{walk_forward['status']}]: {walk_forward['reason']}",
            "",
            "B) Monthly Stability:",
        ]
    )
    for row in monthly["rows"]:
        lines.append(
            f"  {row['label']}: N={int(row['n'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Months > 50% WR: {int(monthly['good_months'])}/{int(monthly['active_months'])}",
            f"  Longest losing streak: {int(monthly['longest_losing_streak'])} months",
            f"  [{monthly['status']}]: {monthly['reason']}",
            "",
            "C) Time-of-Day:",
        ]
    )
    lines.extend(render_time_of_day_lines(result["time_of_day"]))
    lines.extend(
        [
            "",
            "D) Streaks:",
            f"  Max consecutive wins: {int(streaks['max_win_streak'])}",
            f"  Max consecutive losses: {int(streaks['max_loss_streak'])}",
            f"  Avg win streak length: {fmt_float(float(streaks['avg_win_streak']))}",
            f"  Avg loss streak length: {fmt_float(float(streaks['avg_loss_streak']))}",
            "",
            "E) Drawdown:",
            f"  Max drawdown: {fmt_ticks(float(drawdown['max_drawdown_ticks']))} ticks",
            f"  Max drawdown duration: {int(drawdown['max_drawdown_duration_bars'])} bars",
            "",
            "F) Bayesian:",
            f"  Prior: Beta({BETA_PRIOR_ALPHA}, {BETA_PRIOR_BETA}), mean=50.0%",
            f"  Posterior: Beta({int(bayes['posterior_alpha'])}, {int(bayes['posterior_beta'])}), mean={fmt_pct(float(bayes['posterior_mean']))}",
            f"  95% Credible Interval: [{fmt_pct(float(bayes['ci_low']))}, {fmt_pct(float(bayes['ci_high']))}]",
            f"  Shrinkage: {fmt_pct(float(bayes['observed_wr']))} → {fmt_pct(float(bayes['posterior_mean']))}",
            "",
            f"OVERALL VERDICT: {result['verdict']}",
            "- DEPLOY: OOS WR > 55%, no month below 35%, Bayesian posterior > 55%",
            "- PAPER TRADE: OOS WR > 50%, Bayesian posterior > 50%",
            "- INSUFFICIENT DATA: otherwise",
            "",
        ]
    )
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    absorption = prep_validation_frame()
    windows = build_walk_forward_windows(absorption)

    results: list[dict[str, object]] = []
    for filter_code, label, predicate in build_filter_specs():
        filtered = absorption.loc[predicate(absorption)].copy()
        results.append(validate_filter(filtered, filter_code, label, windows))

    lines = [
        "TOP 5 COMPOUND FILTER VALIDATION",
        "=================================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique absorption bar grouped by global_index + direction.",
        "Primary P&L: ret_5b_ticks = direction * (fwd_close_5b - bar_close) / 0.25.",
        "Walk-forward windows: six evenly spaced date-based 2-month IS / 1-month OOS splits across the available sample.",
        "",
    ]
    for result in results:
        lines.extend(render_filter_report(result))

    report = "\n".join(lines).rstrip() + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
