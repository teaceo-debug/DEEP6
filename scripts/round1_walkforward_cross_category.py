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
OUT_PATH = OUT_DIR / "round1_walkforward_cross_category.txt"

EASTERN = "America/New_York"
TIMEFRAMES = (15, 60)
PRIMARY_WINDOW = 5
WALK_FORWARD_WINDOWS = 6
TICK_SIZE = 0.25
BETA_PRIOR_ALPHA = 10
BETA_PRIOR_BETA = 10
TARGET_SIGNAL_IDS = ("DELT_04", "TRAP_04", "EXH_03", "IMB_03")


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


def fmt_ci(low: float, high: float) -> str:
    return f"[{low * 100:.1f}%, {high * 100:.1f}%]"


def profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0].sum()
    losses = -returns[returns <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def win_rate(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    return float((returns > 0).mean())


def wilson_ci(n: int, k: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin), p_hat


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
    events["is_TYPE_A"] = events["score_tier"].eq("TYPE_A")
    events["is_TYPE_B"] = events["score_tier"].eq("TYPE_B")

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
            signal_set=("signal_id", lambda s: ",".join(sorted(set(s.dropna())))),
            category_set=("category", lambda s: ",".join(sorted(set(s.dropna())))),
            signal_count=("signal_id", "nunique"),
            category_count=("category", "nunique"),
            max_score_final=("score_final", "max"),
            has_TYPE_A=("is_TYPE_A", "max"),
            has_TYPE_B=("is_TYPE_B", "max"),
            has_DELT_04=("is_DELT_04", "max"),
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
    observations["has_score_ge_80"] = observations["max_score_final"].ge(80)
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


def prep_validation_frame() -> tuple[pd.DataFrame, dict[int, pd.DataFrame], int]:
    events = load_events()
    bars_1m = load_ohlcv()
    observations = build_observations(events)
    context = build_timeframe_context(bars_1m)
    observations = attach_context(observations, context)
    observations = add_regime_flags(observations)
    observations["session_date_dt"] = pd.to_datetime(observations["session_date"], errors="coerce")
    observations["session_month"] = observations["session_date_dt"].dt.to_period("M")
    observations = observations.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable").reset_index(drop=True)
    return observations, context, len(events)


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


def walk_forward_analysis(df: pd.DataFrame, windows: list[dict[str, object]]) -> dict[str, object]:
    oos_frames: list[pd.DataFrame] = []
    rows: list[dict[str, object]] = []
    weak_windows: list[str] = []

    for window in windows:
        oos_month = window["oos_month"]
        window_df = df.loc[df["session_month"].eq(oos_month)].copy()
        ret = window_df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
        n = int(len(ret))
        wins = int((ret > 0).sum())
        wr = win_rate(ret)
        avg_ticks = float(ret.mean()) if n else float("nan")
        rows.append(
            {
                "window_num": int(window["window_num"]),
                "label": str(window["label"]),
                "n": n,
                "wins": wins,
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
    oos_wins = int((oos_ret > 0).sum())
    oos_ci_low, oos_ci_high, oos_wr_hat = wilson_ci(oos_n, oos_wins)
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
        "oos_wins": oos_wins,
        "oos_wr": oos_wr,
        "oos_avg_ticks": oos_avg,
        "oos_ci_low": oos_ci_low,
        "oos_ci_high": oos_ci_high,
        "oos_wr_hat": oos_wr_hat,
        "weak_windows": weak_windows,
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


def streak_analysis(df: pd.DataFrame) -> dict[str, int]:
    trade_df = df.dropna(subset=[f"ret_{PRIMARY_WINDOW}b_ticks"]).copy()
    if trade_df.empty:
        return {"max_win_streak": 0, "max_loss_streak": 0}

    trade_df = trade_df.sort_values(["bar_ts", "global_index", "direction_sign"], kind="stable")
    outcomes = (trade_df[f"ret_{PRIMARY_WINDOW}b_ticks"] > 0).tolist()

    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0

    for outcome in outcomes:
        if outcome:
            current_win_streak += 1
            current_loss_streak = 0
        else:
            current_loss_streak += 1
            current_win_streak = 0
        max_win_streak = max(max_win_streak, current_win_streak)
        max_loss_streak = max(max_loss_streak, current_loss_streak)

    return {"max_win_streak": max_win_streak, "max_loss_streak": max_loss_streak}


def bayesian_analysis(df: pd.DataFrame) -> dict[str, object]:
    ret = df[f"ret_{PRIMARY_WINDOW}b_ticks"].dropna()
    n = int(len(ret))
    wins = int((ret > 0).sum())
    losses = n - wins
    posterior_alpha = BETA_PRIOR_ALPHA + wins
    posterior_beta = BETA_PRIOR_BETA + losses
    observed_wr = win_rate(ret)
    posterior_mean = posterior_alpha / (posterior_alpha + posterior_beta)
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


def build_filter_specs() -> list[tuple[str, str, object]]:
    return [
        ("01", "DELT_04 + TRAP_04 + 15m_trend_aligned", lambda df: df["has_DELT_04"] & df["has_TRAP_04"] & df["is_15m_trend_aligned"]),
        ("02", "score_final >= 80 + 60m_extreme", lambda df: df["max_score_final"].ge(80) & df["is_60m_extreme"]),
        ("03", "DELT_04 + EXH_03 + 60m_extreme", lambda df: df["has_DELT_04"] & df["has_EXH_03"] & df["is_60m_extreme"]),
        ("04", "TYPE_B + 60m_extreme", lambda df: df["has_TYPE_B"] & df["is_60m_extreme"]),
        ("05", "TYPE_A + 60m_extreme", lambda df: df["has_TYPE_A"] & df["is_60m_extreme"]),
        ("06", "3+ categories + 60m_extreme", lambda df: df["category_count"].ge(3) & df["is_60m_extreme"]),
        ("07", "IMB_03 + 60m_extreme", lambda df: df["has_IMB_03"] & df["is_60m_extreme"]),
        ("08", "DELT_04 + 60m_extreme", lambda df: df["has_DELT_04"] & df["is_60m_extreme"]),
    ]


def validate_filter(df: pd.DataFrame, filter_code: str, label: str, windows: list[dict[str, object]]) -> dict[str, object]:
    trade_df = df.dropna(subset=[f"ret_{PRIMARY_WINDOW}b_ticks"]).copy()
    primary = trade_df[f"ret_{PRIMARY_WINDOW}b_ticks"]
    walk_forward = walk_forward_analysis(trade_df, windows)
    monthly = monthly_stability(trade_df)
    streaks = streak_analysis(trade_df)
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
        "streaks": streaks,
        "bayes": bayes,
        "verdict": overall_verdict(walk_forward, monthly, bayes),
    }


def render_summary_table(results: list[dict[str, object]]) -> list[str]:
    headers = ["Rank", "Filter", "N", "WR%", "OOS WR%", "OOS Wilson 95% CI", "Bayes Mean", "Verdict"]
    data_rows: list[list[str]] = []

    for idx, row in enumerate(results, start=1):
        walk_forward = row["walk_forward"]
        bayes = row["bayes"]
        data_rows.append(
            [
                str(idx),
                f"{row['filter_code']}. {row['label']}",
                f"{int(row['n']):,}",
                fmt_pct(float(row["wr"])),
                fmt_pct(float(walk_forward["oos_wr"])),
                fmt_ci(float(walk_forward["oos_ci_low"]), float(walk_forward["oos_ci_high"])),
                fmt_pct(float(bayes["posterior_mean"])),
                str(row["verdict"]),
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


def render_filter_report(result: dict[str, object]) -> list[str]:
    walk_forward = result["walk_forward"]
    monthly = result["monthly"]
    bayes = result["bayes"]
    streaks = result["streaks"]
    weak_windows = walk_forward["weak_windows"]

    lines = [
        f"FILTER {result['filter_code']}: {result['label']}",
        "-" * (8 + len(result["filter_code"]) + len(result["label"])),
        f"Summary: N={result['n']:,}, WR={fmt_pct(float(result['wr']))}, PF={fmt_float(float(result['pf']))}, Avg={fmt_ticks(float(result['avg_ticks']))} ticks",
        "",
        f"A) Walk-Forward ({len(walk_forward['rows'])} windows, 2mo IS / 1mo OOS):",
    ]
    for row in walk_forward["rows"]:
        lines.append(
            f"  Window {int(row['window_num'])} ({row['label']}): N={int(row['n'])}, Wins={int(row['wins'])}, WR={fmt_pct(float(row['wr']))}, Avg={fmt_ticks(float(row['avg_ticks']))} ticks"
        )
    lines.extend(
        [
            f"  Overall OOS: N={int(walk_forward['oos_n'])}, Wins={int(walk_forward['oos_wins'])}, WR={fmt_pct(float(walk_forward['oos_wr']))}, Avg={fmt_ticks(float(walk_forward['oos_avg_ticks']))} ticks",
            f"  OOS Wilson 95% CI: {fmt_ci(float(walk_forward['oos_ci_low']), float(walk_forward['oos_ci_high']))}",
            f"  Any window < 40% WR: {'YES' if weak_windows else 'NO'}",
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
            "C) Trade Streaks:",
            f"  Max consecutive wins: {int(streaks['max_win_streak'])}",
            f"  Max consecutive losses: {int(streaks['max_loss_streak'])}",
            "",
            "D) Bayesian:",
            f"  Prior: Beta({BETA_PRIOR_ALPHA}, {BETA_PRIOR_BETA}), mean=50.0%",
            f"  Posterior: Beta({int(bayes['posterior_alpha'])}, {int(bayes['posterior_beta'])}), mean={fmt_pct(float(bayes['posterior_mean']))}",
            f"  95% Credible Interval: {fmt_ci(float(bayes['ci_low']), float(bayes['ci_high']))}",
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

    observations, context, raw_event_count = prep_validation_frame()
    windows = build_walk_forward_windows(observations)

    results: list[dict[str, object]] = []
    for filter_code, label, predicate in build_filter_specs():
        filtered = observations.loc[predicate(observations)].copy()
        results.append(validate_filter(filtered, filter_code, label, windows))

    results.sort(
        key=lambda row: (
            float("-inf") if pd.isna(row["walk_forward"]["oos_wr"]) else float(row["walk_forward"]["oos_wr"]),
            int(row["walk_forward"]["oos_n"]),
            float("-inf") if pd.isna(row["wr"]) else float(row["wr"]),
            int(row["n"]),
        ),
        reverse=True,
    )

    lines = [
        "ROUND 1 CROSS-CATEGORY WALK-FORWARD VALIDATION",
        "===============================================",
        "",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        "Observation unit: unique same-bar, same-direction grouped signal observation by global_index + direction.",
        "Primary P&L: ret_5b_ticks = direction * (fwd_close_5b - bar_close) / 0.25.",
        "Regime filters: 15m_trend_aligned = signal direction matches 15m bar sign; 60m_extreme = bullish bar_low in bottom 20% of 60m range / bearish bar_high in top 20%.",
        "Walk-forward windows: six evenly spaced 2-month IS / 1-month OOS splits across available months.",
        "Verdict rules reused from validate_top5_filters.py.",
        "",
        f"Raw event rows loaded: {raw_event_count:,}",
        f"Grouped observations:  {len(observations):,}",
        f"15m bars built:       {len(context[15]):,}",
        f"60m bars built:       {len(context[60]):,}",
        f"15m trend aligned:    {int(observations['is_15m_trend_aligned'].sum()):,}",
        f"60m extreme:          {int(observations['is_60m_extreme'].sum()):,}",
        "",
        "Summary ranking by composite OOS WR",
        "-----------------------------------",
    ]
    lines.extend(render_summary_table(results))
    lines.append("")

    for result in results:
        lines.extend(render_filter_report(result))

    report = "\n".join(lines).rstrip() + "\n"
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
