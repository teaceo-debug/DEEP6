#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data/backtests/signal_events.csv"
OHLCV_CSV = ROOT / "data/backtests/nq_1yr_1m.csv"
OUT_DIR = ROOT / "data/backtests/analysis"
OUT_PATH = OUT_DIR / "absorption_multitimeframe_report.txt"

TIMEFRAMES = (5, 15, 30, 60)
PRIMARY_WINDOW = 5
COMMISSION = 0.70
DPP = 20.0
EASTERN = "America/New_York"


def direction_to_sign(series: pd.Series) -> pd.Series:
    return series.map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1, 1: 1, -1: -1}).fillna(0).astype(int)


def fmt_pct(value: float) -> str:
    return f"{value * 100:,.1f}%"


def fmt_float(value: float) -> str:
    if pd.isna(value):
        return "nan"
    return f"{value:,.2f}"


def profit_factor(pnls: pd.Series) -> float:
    wins = pnls[pnls > 0].sum()
    losses = -pnls[pnls <= 0].sum()
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def summarize(label: str, df: pd.DataFrame) -> dict:
    pnls = df[f"pnl_{PRIMARY_WINDOW}b"].dropna()
    n = len(pnls)
    wins = (pnls > 0).sum()
    return {
        "label": label,
        "n": n,
        "win_rate": wins / n if n else np.nan,
        "profit_factor": profit_factor(pnls) if n else np.nan,
        "avg_pnl": pnls.mean() if n else np.nan,
        "median_pnl": pnls.median() if n else np.nan,
        "net_pnl": pnls.sum() if n else np.nan,
        "avg_move_pts": df["move_5b_pts"].mean() if n else np.nan,
    }


def render_stats(stats: dict) -> str:
    return (
        f"{stats['label']}: N={stats['n']:,} | WR={fmt_pct(stats['win_rate'])} | "
        f"PF={fmt_float(stats['profit_factor'])} | Avg$={fmt_float(stats['avg_pnl'])} | "
        f"Med$={fmt_float(stats['median_pnl'])} | Net$={fmt_float(stats['net_pnl'])} | "
        f"AvgMove={fmt_float(stats['avg_move_pts'])} pts"
    )


def load_ohlcv() -> pd.DataFrame:
    bars = pd.read_csv(
        OHLCV_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True).dt.tz_convert(EASTERN)
    bars = bars.sort_values("ts_event").reset_index(drop=True)
    return bars


def load_events() -> tuple[pd.DataFrame, pd.DataFrame]:
    ev = pd.read_csv(EVENTS_CSV, low_memory=False)
    ev["bar_ts"] = pd.to_datetime(ev["bar_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    ev["direction_sign"] = direction_to_sign(ev["direction"])
    ev = ev[ev["direction_sign"] != 0].copy()

    fc = pd.to_numeric(ev[f"fwd_close_{PRIMARY_WINDOW}b"], errors="coerce")
    price_move = fc - pd.to_numeric(ev["bar_close"], errors="coerce")
    ev[f"pnl_{PRIMARY_WINDOW}b"] = ev["direction_sign"] * price_move * DPP - COMMISSION
    ev["move_5b_pts"] = ev["direction_sign"] * price_move

    abs_ev = ev[ev["category"] == "absorption"].copy()
    abs_obs = (
        abs_ev.groupby(["bar_ts", "direction_sign"], as_index=False)
        .agg(
            session_date=("session_date", "first"),
            signal_ids=("signal_id", lambda s: ",".join(sorted(set(s)))),
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
            fwd_close_5b=(f"fwd_close_{PRIMARY_WINDOW}b", "first"),
            pnl_5b=(f"pnl_{PRIMARY_WINDOW}b", "first"),
            move_5b_pts=("move_5b_pts", "first"),
        )
    )
    abs_obs["direction"] = np.where(abs_obs["direction_sign"] > 0, "BULLISH", "BEARISH")
    return ev, abs_obs


def build_timeframe_context(bars_1m: pd.DataFrame, events_all: pd.DataFrame) -> tuple[dict[int, pd.DataFrame], pd.DataFrame]:
    delta_1m = (
        events_all[["bar_ts", "bar_delta"]]
        .dropna(subset=["bar_ts"])
        .drop_duplicates(subset=["bar_ts"])
        .sort_values("bar_ts")
        .rename(columns={"bar_ts": "ts_event"})
    )
    delta_1m["bar_delta"] = pd.to_numeric(delta_1m["bar_delta"], errors="coerce").fillna(0.0)

    context: dict[int, pd.DataFrame] = {}
    bars_built = []
    base = bars_1m.set_index("ts_event")
    delta_base = delta_1m.set_index("ts_event")

    for tf in TIMEFRAMES:
        rule = f"{tf}min"
        tf_bars = (
            base.resample(rule)
            .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
            .dropna()
            .reset_index()
        )
        tf_delta = delta_base.resample(rule).agg(delta=("bar_delta", "sum")).reset_index()
        tf_bars = tf_bars.merge(tf_delta, on="ts_event", how="left")
        tf_bars["delta"] = tf_bars["delta"].fillna(0.0)
        tf_bars["range"] = tf_bars["high"] - tf_bars["low"]
        tf_bars["trend_sign"] = np.sign(tf_bars["close"] - tf_bars["open"]).astype(int)
        context[tf] = tf_bars
        bars_built.append(tf_bars.assign(tf=tf)[["ts_event", "tf", "open", "high", "low", "close", "volume", "delta", "range"]])

    built = pd.concat(bars_built, ignore_index=True)
    return context, built


def attach_context(abs_obs: pd.DataFrame, context: dict[int, pd.DataFrame]) -> pd.DataFrame:
    df = abs_obs.copy()
    for tf, ctx in context.items():
        bucket = df["bar_ts"].dt.floor(f"{tf}min")
        df[f"bucket_{tf}m"] = bucket
        renamed = ctx.rename(
            columns={
                "ts_event": f"bucket_{tf}m",
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
        df = df.merge(renamed, on=f"bucket_{tf}m", how="left")

    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    return df


def analyze_high_delta_5m(df: pd.DataFrame, ctx_5m: pd.DataFrame) -> tuple[list[str], bool]:
    pos_q75 = ctx_5m.loc[ctx_5m["delta"] > 0, "delta"].quantile(0.75)
    neg_q25 = ctx_5m.loc[ctx_5m["delta"] < 0, "delta"].quantile(0.25)
    same_pressure = ((df["direction_sign"] > 0) & (df["delta_5m"] >= pos_q75)) | ((df["direction_sign"] < 0) & (df["delta_5m"] <= neg_q25))

    hi = summarize("Aligned high-delta 5m", df[same_pressure])
    other = summarize("Everything else", df[~same_pressure])
    ok = hi["n"] >= 30 and other["n"] >= 30
    lines = [
        "1) 1-min absorption inside a high-delta 5-min bar",
        f"Thresholds: bullish delta >= {fmt_float(pos_q75)}, bearish delta <= {fmt_float(neg_q25)}",
        render_stats(hi),
        render_stats(other),
    ]
    return lines, ok


def analyze_multi_absorption_5m(df: pd.DataFrame) -> tuple[list[str], bool]:
    same_dir_minutes = df.groupby(["bucket_5m", "direction_sign"])["bar_ts"].transform("nunique")
    multi = same_dir_minutes >= 2
    a = summarize("2+ absorption minutes in same 5m + direction", df[multi])
    b = summarize("Single absorption minute in same 5m + direction", df[~multi])
    ok = a["n"] >= 30 and b["n"] >= 30
    lines = [
        "2) Multiple 1-min absorptions inside one 5-min bar",
        "Count uses unique 1-min absorption timestamps within the same 5m bucket and direction.",
        render_stats(a),
        render_stats(b),
    ]
    return lines, ok


def analyze_range_context_5m(df: pd.DataFrame, ctx_5m: pd.DataFrame) -> tuple[list[str], bool]:
    low_q25 = ctx_5m["range"].quantile(0.25)
    high_q75 = ctx_5m["range"].quantile(0.75)
    tight = df["range_5m"] <= low_q25
    wide = df["range_5m"] >= high_q75

    a = summarize("Tight 5m range (bottom quartile)", df[tight])
    b = summarize("Wide 5m range (top quartile)", df[wide])
    ok = a["n"] >= 30 and b["n"] >= 30
    lines = [
        "3) 5-min bar range context",
        f"Thresholds: tight <= {fmt_float(low_q25)} pts, wide >= {fmt_float(high_q75)} pts",
        render_stats(a),
        render_stats(b),
    ]
    return lines, ok


def analyze_15m_trend_alignment(df: pd.DataFrame) -> tuple[list[str], bool]:
    aligned = df["direction_sign"] == df["trend_sign_15m"]
    disagree = df["direction_sign"] == -df["trend_sign_15m"]
    flat = df["trend_sign_15m"] == 0

    a = summarize("15m trend aligned", df[aligned])
    b = summarize("15m trend disagrees", df[disagree])
    c = summarize("15m trend flat/doji", df[flat])
    ok = a["n"] >= 30 and b["n"] >= 30
    lines = [
        "4) 15-min trend alignment",
        "Trend sign = sign(15m close - 15m open).",
        render_stats(a),
        render_stats(b),
        render_stats(c),
    ]
    return lines, ok


def analyze_60m_structure(df: pd.DataFrame) -> tuple[list[str], bool]:
    rng = df["range_60m"].replace(0, np.nan)
    anchor = np.where(df["direction_sign"] > 0, df["bar_low"], df["bar_high"])
    pos = (anchor - df["low_60m"]) / rng
    extreme = ((df["direction_sign"] > 0) & (pos <= 0.20)) | ((df["direction_sign"] < 0) & (pos >= 0.80))
    middle = pos.between(0.40, 0.60, inclusive="both")
    opposite = (~extreme) & (~middle) & pos.notna()

    a = summarize("Near favorable 60m extreme", df[extreme])
    b = summarize("Near 60m middle", df[middle])
    c = summarize("Neither extreme nor middle", df[opposite])
    ok = a["n"] >= 30 and b["n"] >= 30
    lines = [
        "5) 60-min structure positioning",
        "Bullish uses the 1m bar low inside the 60m range; bearish uses the 1m bar high.",
        render_stats(a),
        render_stats(b),
        render_stats(c),
    ]
    return lines, ok


def build_conclusions(results: list[tuple[str, dict, dict, bool]]) -> list[str]:
    lines = ["Conclusions (only treat N>=30 comparisons as actionable):"]
    for title, left, right, ok in results:
        if not ok:
            lines.append(f"- {title}: insufficient sample for one side; no hard conclusion.")
            continue
        delta = left["avg_pnl"] - right["avg_pnl"]
        better = left["label"] if delta > 0 else right["label"]
        lines.append(
            f"- {title}: {better} performed better by ${abs(delta):.2f} avg P&L per signal "
            f"(PF {fmt_float(left['profit_factor'])} vs {fmt_float(right['profit_factor'])})."
        )
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_events, abs_obs = load_events()
    bars_1m = load_ohlcv()
    context, built_bars = build_timeframe_context(bars_1m, all_events)
    df = attach_context(abs_obs, context)

    baseline = summarize("All absorption observations", df)

    sec1, ok1 = analyze_high_delta_5m(df, context[5])
    sec2, ok2 = analyze_multi_absorption_5m(df)
    sec3, ok3 = analyze_range_context_5m(df, context[5])
    sec4, ok4 = analyze_15m_trend_alignment(df)
    sec5, ok5 = analyze_60m_structure(df)

    same_pressure = ((df["direction_sign"] > 0) & (df["delta_5m"] >= context[5].loc[context[5]["delta"] > 0, "delta"].quantile(0.75))) | ((df["direction_sign"] < 0) & (df["delta_5m"] <= context[5].loc[context[5]["delta"] < 0, "delta"].quantile(0.25)))
    multi = df.groupby(["bucket_5m", "direction_sign"])["bar_ts"].transform("nunique") >= 2
    tight = df["range_5m"] <= context[5]["range"].quantile(0.25)
    wide = df["range_5m"] >= context[5]["range"].quantile(0.75)
    aligned = df["direction_sign"] == df["trend_sign_15m"]
    disagree = df["direction_sign"] == -df["trend_sign_15m"]
    rng = df["range_60m"].replace(0, np.nan)
    anchor = np.where(df["direction_sign"] > 0, df["bar_low"], df["bar_high"])
    pos = (anchor - df["low_60m"]) / rng
    extreme = ((df["direction_sign"] > 0) & (pos <= 0.20)) | ((df["direction_sign"] < 0) & (pos >= 0.80))
    middle = pos.between(0.40, 0.60, inclusive="both")

    conclusions = build_conclusions([
        ("High-delta 5m context", summarize("Aligned high-delta 5m", df[same_pressure]), summarize("Everything else", df[~same_pressure]), ok1),
        ("Multiple absorptions in 5m", summarize("2+ absorption minutes in same 5m + direction", df[multi]), summarize("Single absorption minute in same 5m + direction", df[~multi]), ok2),
        ("5m range regime", summarize("Tight 5m range (bottom quartile)", df[tight]), summarize("Wide 5m range (top quartile)", df[wide]), ok3),
        ("15m trend alignment", summarize("15m trend aligned", df[aligned]), summarize("15m trend disagrees", df[disagree]), ok4),
        ("60m location", summarize("Near favorable 60m extreme", df[extreme]), summarize("Near 60m middle", df[middle]), ok5),
    ])

    lines = [
        "DEEP6 absorption multi-timeframe study",
        "====================================",
        f"Source events: {EVENTS_CSV}",
        f"Source bars:   {OHLCV_CSV}",
        f"Primary metric: {PRIMARY_WINDOW}-bar forward P&L from absorption observation (1 unique 1m timestamp + direction)",
        "",
        f"Absorption observations: {len(df):,}",
        render_stats(baseline),
        "",
        "Higher-timeframe bars built from 1m OHLCV:",
    ]

    for tf in TIMEFRAMES:
        lines.append(f"- {tf}m bars: {len(context[tf]):,}")

    lines.extend([
        "",
        f"All aggregated TF rows retained for audit: {len(built_bars):,}",
        "",
    ])
    lines.extend(sec1)
    lines.append("")
    lines.extend(sec2)
    lines.append("")
    lines.extend(sec3)
    lines.append("")
    lines.extend(sec4)
    lines.append("")
    lines.extend(sec5)
    lines.append("")
    lines.extend(conclusions)

    report = "\n".join(lines)
    OUT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved report -> {OUT_PATH}")


if __name__ == "__main__":
    main()
