#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "backtests" / "signal_events.csv"
OUT_DIR = ROOT / "data" / "backtests" / "analysis"
REPORT_MD = OUT_DIR / "absorption_regime_report.md"
REPORT_CSV = OUT_DIR / "absorption_regime_metrics.csv"

TICK_SIZE = 0.25
FORWARD_WINDOWS = (5, 15)


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
    df = pd.read_csv(EVENTS_CSV, dtype=dtypes, low_memory=False)
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
    df["direction"] = (
        df["direction"]
        .replace({"BULLISH": "1", "BEARISH": "-1", "neutral": "0", "NEUTRAL": "0"})
    )
    df["direction"] = pd.to_numeric(df["direction"], errors="coerce").fillna(0).astype("int8")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce")
    df = df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)
    return df


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
    bars["prior_move_30_ticks"] = (
        bars.groupby("session_date", sort=False)["bar_close"]
        .transform(lambda s: (s - s.shift(30)).abs() / TICK_SIZE)
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

    local_ts = bars["bar_ts"].dt.tz_convert("America/New_York")
    bars["minutes_since_midnight"] = local_ts.dt.hour * 60 + local_ts.dt.minute
    bars["session_half"] = np.where(
        bars["minutes_since_midnight"] < (12 * 60 + 30),
        "morning_0930_1230",
        "afternoon_1230_1600",
    )
    bars["price_vs_sma"] = np.where(
        bars["bar_close"] >= bars["sma_50"],
        "above_sma50",
        "below_sma50",
    )
    return bars


def add_regimes(absorption: pd.DataFrame) -> pd.DataFrame:
    absorption = absorption.copy()

    absorption["volatility_regime"] = pd.qcut(
        absorption["atr_20"],
        q=3,
        labels=["low_vol", "mid_vol", "high_vol"],
        duplicates="drop",
    )
    absorption["vwap_position"] = pd.qcut(
        absorption["vwap_dist_ticks"],
        q=3,
        labels=["near_vwap", "mid_vwap", "far_vwap"],
        duplicates="drop",
    )
    absorption["trend_alignment"] = np.where(
        absorption["direction"] * np.where(absorption["bar_close"] >= absorption["sma_50"], 1, -1) > 0,
        "with_trend",
        "against_trend",
    )
    absorption["prior_move_bucket"] = pd.cut(
        absorption["prior_move_30_ticks"],
        bins=[-math.inf, 50, 150, math.inf],
        labels=["small_lt50", "medium_50_150", "large_gt150"],
        right=False,
    )

    delta_side = np.sign(absorption["prior_delta_10"].fillna(0.0)) * absorption["direction"]
    absorption["prior_delta_relation"] = np.select(
        [delta_side < 0, delta_side > 0, delta_side == 0],
        ["opposite_to_signal", "same_as_signal", "flat_zero"],
        default="flat_zero",
    )
    absorption["prior_delta_sign"] = np.select(
        [absorption["prior_delta_10"] > 0, absorption["prior_delta_10"] < 0],
        ["positive", "negative"],
        default="flat_zero",
    )
    return absorption


def regime_stats(df: pd.DataFrame, label_col: str, baseline: dict[str, float], min_n: int = 30) -> pd.DataFrame:
    rows: list[dict[str, float | str | int]] = []
    valid = df.dropna(subset=[label_col, "ret_5b_ticks", "ret_15b_ticks"])
    for label, grp in valid.groupby(label_col, observed=False, sort=False):
        n = len(grp)
        if n < min_n:
            continue
        wr_5 = (grp["ret_5b_ticks"] > 0).mean()
        wr_15 = (grp["ret_15b_ticks"] > 0).mean()
        avg_ret = grp["ret_5b_ticks"].mean()
        rows.append(
            {
                "cut": label_col,
                "bucket": str(label),
                "n": n,
                "wr_5b": wr_5,
                "wr_15b": wr_15,
                "avg_return_5b_ticks": avg_ret,
                "delta_wr_5b_pp": (wr_5 - baseline["wr_5b"]) * 100.0,
                "delta_wr_15b_pp": (wr_15 - baseline["wr_15b"]) * 100.0,
                "delta_avg_return_5b_ticks": avg_ret - baseline["avg_return_5b_ticks"],
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["cut", "avg_return_5b_ticks", "wr_5b"], ascending=[True, False, False])


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def fmt_pp(x: float) -> str:
    return f"{x:+.2f}pp"


def fmt_ticks(x: float) -> str:
    return f"{x:+.2f}t"


def to_markdown_table(df: pd.DataFrame) -> list[str]:
    lines = [
        "| Bucket | N | WR 5b | WR 15b | Avg Ret 5b (ticks) | Δ WR 5b | Δ WR 15b | Δ Avg Ret |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in df.iterrows():
        lines.append(
            "| {bucket} | {n:,} | {wr5} | {wr15} | {avgret} | {dwr5} | {dwr15} | {davg} |".format(
                bucket=row["bucket"],
                n=int(row["n"]),
                wr5=fmt_pct(row["wr_5b"]),
                wr15=fmt_pct(row["wr_15b"]),
                avgret=f"{row['avg_return_5b_ticks']:.2f}",
                dwr5=fmt_pp(row["delta_wr_5b_pp"]),
                dwr15=fmt_pp(row["delta_wr_15b_pp"]),
                davg=fmt_ticks(row["delta_avg_return_5b_ticks"]),
            )
        )
    return lines


def summarize_findings(results: dict[str, pd.DataFrame]) -> list[str]:
    findings: list[str] = []
    for cut, df in results.items():
        if df.empty:
            continue
        best = df.sort_values(["avg_return_5b_ticks", "wr_5b"], ascending=False).iloc[0]
        worst = df.sort_values(["avg_return_5b_ticks", "wr_5b"], ascending=True).iloc[0]
        findings.append(
            f"- **{cut}**: best `{best['bucket']}` ({best['avg_return_5b_ticks']:.2f}t, {best['wr_5b']*100:.2f}% WR5) vs worst `{worst['bucket']}` ({worst['avg_return_5b_ticks']:.2f}t, {worst['wr_5b']*100:.2f}% WR5)."
        )
    return findings


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    events = load_events()
    bars = compute_bar_features(events)
    absorption = events[events["category"] == "absorption"].copy()
    absorption = absorption.merge(
        bars[
            [
                "global_index",
                "atr_20",
                "sma_50",
                "session_half",
                "session_vwap",
                "vwap_dist_ticks",
                "prior_move_30_ticks",
                "prior_delta_10",
                "price_vs_sma",
            ]
        ],
        on="global_index",
        how="left",
    )

    absorption["ret_5b_ticks"] = absorption["direction"] * (
        (absorption["fwd_close_5b"] - absorption["bar_close"]) / TICK_SIZE
    )
    absorption["ret_15b_ticks"] = absorption["direction"] * (
        (absorption["fwd_close_15b"] - absorption["bar_close"]) / TICK_SIZE
    )
    absorption = absorption.dropna(subset=["ret_5b_ticks", "ret_15b_ticks"]).copy()
    absorption = add_regimes(absorption)

    baseline = {
        "n": len(absorption),
        "wr_5b": float((absorption["ret_5b_ticks"] > 0).mean()),
        "wr_15b": float((absorption["ret_15b_ticks"] > 0).mean()),
        "avg_return_5b_ticks": float(absorption["ret_5b_ticks"].mean()),
    }

    cuts = {
        "volatility_regime": regime_stats(absorption, "volatility_regime", baseline),
        "price_vs_sma": regime_stats(absorption, "price_vs_sma", baseline),
        "trend_alignment": regime_stats(absorption, "trend_alignment", baseline),
        "session_half": regime_stats(absorption, "session_half", baseline),
        "vwap_position": regime_stats(absorption, "vwap_position", baseline),
        "prior_move_bucket": regime_stats(absorption, "prior_move_bucket", baseline),
        "prior_delta_relation": regime_stats(absorption, "prior_delta_relation", baseline),
        "prior_delta_sign": regime_stats(absorption, "prior_delta_sign", baseline),
    }

    all_rows = [df for df in cuts.values() if not df.empty]
    if all_rows:
        pd.concat(all_rows, ignore_index=True).to_csv(REPORT_CSV, index=False)

    lines: list[str] = []
    lines.append("# Absorption Regime Analysis")
    lines.append("")
    lines.append(f"Source: `{EVENTS_CSV}`")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- N: {baseline['n']:,}")
    lines.append(f"- WR 5b: {baseline['wr_5b'] * 100:.2f}%")
    lines.append(f"- WR 15b: {baseline['wr_15b'] * 100:.2f}%")
    lines.append(f"- Avg return 5b: {baseline['avg_return_5b_ticks']:.2f} ticks")
    lines.append("")
    lines.append("## Findings")
    lines.extend(summarize_findings(cuts))
    lines.append("")

    section_titles = {
        "volatility_regime": "Volatility regime (ATR20 terciles)",
        "price_vs_sma": "Trend regime proxy (price vs SMA50)",
        "trend_alignment": "Trend alignment (with-trend vs contrarian)",
        "session_half": "Session type",
        "vwap_position": "Volume profile position proxy (VWAP distance terciles)",
        "prior_move_bucket": "Prior move magnitude (30 bars)",
        "prior_delta_relation": "Delta accumulation vs signal direction",
        "prior_delta_sign": "Raw prior delta sign",
    }
    for cut, title in section_titles.items():
        df = cuts[cut]
        lines.append(f"## {title}")
        lines.append("")
        if df.empty:
            lines.append("Insufficient data.")
            lines.append("")
            continue
        lines.extend(to_markdown_table(df))
        lines.append("")

    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    print("ABSORPTION REGIME ANALYSIS")
    print(f"Baseline N={baseline['n']:,} | WR5={baseline['wr_5b']*100:.2f}% | WR15={baseline['wr_15b']*100:.2f}% | Avg5={baseline['avg_return_5b_ticks']:.2f}t")
    for cut, df in cuts.items():
        print(f"\n[{cut}]")
        if df.empty:
            print("  Insufficient data")
            continue
        print(df.to_string(index=False))
    print(f"\nSaved markdown -> {REPORT_MD}")
    print(f"Saved csv      -> {REPORT_CSV}")


if __name__ == "__main__":
    main()
