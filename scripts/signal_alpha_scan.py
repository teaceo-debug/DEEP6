#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENTS = ROOT / "data/backtests/signal_events.csv"
DEFAULT_OUTDIR = ROOT / "data/backtests/analysis"
WINDOWS = [1, 5, 10, 15, 30]
TICK_SIZE = 0.25
PRIMARY_WINDOW = 5
MIN_TOP_N = 30


def load_events(csv_path: Path) -> pd.DataFrame:
    usecols = [
        "session_date",
        "bar_ts",
        "bar_index",
        "global_index",
        "signal_id",
        "category",
        "direction",
        "score_tier",
        "bar_close",
        *(f"fwd_close_{w}b" for w in WINDOWS),
    ]
    df = pd.read_csv(csv_path, usecols=usecols, low_memory=False)
    df["direction"] = pd.to_numeric(df["direction"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    for w in WINDOWS:
        df[f"fwd_close_{w}b"] = pd.to_numeric(df[f"fwd_close_{w}b"], errors="coerce")
        df[f"ret_{w}b"] = (df[f"fwd_close_{w}b"] - df["bar_close"]) * df["direction"] / TICK_SIZE
    ts_et = pd.to_datetime(df["bar_ts"], errors="coerce", utc=True).dt.tz_convert("America/New_York")
    df["hour_et"] = ts_et.dt.hour
    return df


def stats_frame(df: pd.DataFrame, group_cols: list[str], prefix: str = "") -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for w in WINDOWS:
        col = f"ret_{w}b"
        grouped = df.groupby(group_cols, dropna=False)[col]
        stat = grouped.agg(
            n="count",
            win_rate=lambda s: float((s > 0).mean()),
            avg_return="mean",
            std="std",
        ).reset_index()
        stat["sharpe"] = np.where(
            stat["std"].fillna(0) > 0,
            stat["avg_return"] / stat["std"],
            np.nan,
        )
        stat = stat.drop(columns=["std"])
        renamed = {
            "n": f"{prefix}n_{w}b",
            "win_rate": f"{prefix}wr_{w}b",
            "avg_return": f"{prefix}avg_{w}b",
            "sharpe": f"{prefix}sharpe_{w}b",
        }
        stat = stat.rename(columns=renamed)
        pieces.append(stat)

    out = pieces[0]
    for piece in pieces[1:]:
        out = out.merge(piece, on=group_cols, how="outer")
    return out


def leaderboard_table(signal_stats: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "signal_id",
        "category",
        *(f"n_{w}b" for w in WINDOWS),
        *(f"wr_{w}b" for w in WINDOWS),
        *(f"avg_{w}b" for w in WINDOWS),
        *(f"sharpe_{w}b" for w in WINDOWS),
    ]
    board = signal_stats[cols].copy()
    board = board.sort_values([f"avg_{PRIMARY_WINDOW}b", f"sharpe_{PRIMARY_WINDOW}b"], ascending=[False, False])
    board.insert(2, "primary_window", PRIMARY_WINDOW)
    return board


def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for category, grp in df.groupby("category", dropna=False):
        row: dict[str, object] = {
            "category": category,
            "signals": grp["signal_id"].nunique(),
        }
        for w in WINDOWS:
            col = f"ret_{w}b"
            vals = grp[col].dropna()
            wr = float((vals > 0).mean()) if len(vals) else np.nan
            std = float(vals.std(ddof=1)) if len(vals) > 1 else np.nan
            sharpe = float(vals.mean() / std) if len(vals) > 1 and std and not np.isnan(std) else np.nan
            row.update(
                {
                    f"n_{w}b": int(vals.count()),
                    f"wr_{w}b": wr,
                    f"avg_{w}b": float(vals.mean()) if len(vals) else np.nan,
                    f"sharpe_{w}b": sharpe,
                }
            )
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values([f"avg_{PRIMARY_WINDOW}b", f"sharpe_{PRIMARY_WINDOW}b"], ascending=[False, False])


def signal_tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    return stats_frame(df, ["signal_id", "category", "score_tier"])


def overall_tier_summary(df: pd.DataFrame) -> pd.DataFrame:
    out = stats_frame(df, ["score_tier"])
    return out.sort_values([f"avg_{PRIMARY_WINDOW}b", f"sharpe_{PRIMARY_WINDOW}b"], ascending=[False, False])


def top_signal_ids(leaderboard: pd.DataFrame, min_n: int, top_n: int) -> list[str]:
    eligible = leaderboard[leaderboard[f"n_{PRIMARY_WINDOW}b"] >= min_n]
    if len(eligible) < top_n:
        eligible = leaderboard
    return eligible.head(top_n)["signal_id"].tolist()


def time_of_day_for_signals(df: pd.DataFrame, signal_ids: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    subset = df[df["signal_id"].isin(signal_ids)].copy()
    rows = []
    summary_rows = []
    for signal_id, grp in subset.groupby("signal_id"):
        for hour, hour_grp in grp.groupby("hour_et"):
            vals = hour_grp[f"ret_{PRIMARY_WINDOW}b"].dropna()
            if not len(vals):
                continue
            rows.append(
                {
                    "signal_id": signal_id,
                    "hour_et": int(hour),
                    "n": int(vals.count()),
                    "wr_5b": float((vals > 0).mean()),
                    "avg_5b": float(vals.mean()),
                    "sharpe_5b": float(vals.mean() / vals.std(ddof=1)) if len(vals) > 1 and vals.std(ddof=1) > 0 else np.nan,
                }
            )
        ranked = pd.DataFrame([r for r in rows if r["signal_id"] == signal_id]).sort_values(
            ["avg_5b", "n"], ascending=[False, False]
        )
        top_hours = ranked.head(3)
        summary_rows.append(
            {
                "signal_id": signal_id,
                "best_hours_et": ", ".join(f"{int(h):02d}" for h in top_hours["hour_et"].tolist()),
                "best_hours_avg_5b": ", ".join(f"{v:.2f}" for v in top_hours["avg_5b"].tolist()),
                "hours_with_n_ge_10": int((ranked["n"] >= 10).sum()),
            }
        )
    detail = pd.DataFrame(rows).sort_values(["signal_id", "avg_5b", "n"], ascending=[True, False, False])
    summary = pd.DataFrame(summary_rows).sort_values("signal_id")
    return detail, summary


def absorption_interactions(df: pd.DataFrame, signal_ids: list[str]) -> pd.DataFrame:
    absorption_bars = set(df.loc[df["category"] == "absorption", "global_index"].dropna().astype(int).tolist())
    rows = []
    for signal_id in signal_ids:
        grp = df[df["signal_id"] == signal_id].copy()
        grp["global_index"] = pd.to_numeric(grp["global_index"], errors="coerce")
        grp = grp.dropna(subset=["global_index", f"ret_{PRIMARY_WINDOW}b"])
        grp["global_index"] = grp["global_index"].astype(int)
        same = grp["global_index"].isin(absorption_bars)
        adjacent = grp["global_index"].map(lambda x: (x - 1 in absorption_bars) or (x + 1 in absorption_bars))
        either = same | adjacent
        baseline = ~either
        for label, mask in {
            "same_bar": same,
            "adjacent_bar": adjacent,
            "same_or_adjacent": either,
            "no_absorption_nearby": baseline,
        }.items():
            vals = grp.loc[mask, f"ret_{PRIMARY_WINDOW}b"].dropna()
            if not len(vals):
                continue
            rows.append(
                {
                    "signal_id": signal_id,
                    "interaction": label,
                    "n": int(vals.count()),
                    "wr_5b": float((vals > 0).mean()),
                    "avg_5b": float(vals.mean()),
                    "sharpe_5b": float(vals.mean() / vals.std(ddof=1)) if len(vals) > 1 and vals.std(ddof=1) > 0 else np.nan,
                }
            )
    return pd.DataFrame(rows).sort_values(["signal_id", "interaction"])


def signal_of_signals(df: pd.DataFrame) -> pd.DataFrame:
    bar_cols = [
        "session_date",
        "global_index",
        "bar_close",
        *(f"fwd_close_{w}b" for w in WINDOWS),
    ]
    bars = df[bar_cols].drop_duplicates(subset=["session_date", "global_index"]).copy()

    bar_keys = ["session_date", "global_index"]
    type_a = df[df["score_tier"] == "TYPE_A"].copy()
    type_a_counts = type_a.groupby(bar_keys).agg(
        type_a_signal_count=("signal_id", "count"),
        type_a_category_count=("category", "nunique"),
        type_a_direction_sum=("direction", "sum"),
    ).reset_index()
    type_a_counts["has_type_a"] = True

    absorption_any = (
        df[df["category"] == "absorption"][bar_keys]
        .drop_duplicates()
        .assign(has_absorption_any=True)
    )
    absorption_type_a = (
        type_a[type_a["category"] == "absorption"][bar_keys]
        .drop_duplicates()
        .assign(has_absorption_type_a=True)
    )

    bars = bars.merge(type_a_counts, on=bar_keys, how="left")
    bars = bars.merge(absorption_any, on=bar_keys, how="left")
    bars = bars.merge(absorption_type_a, on=bar_keys, how="left")
    bars["has_type_a"] = bars["has_type_a"].fillna(False)
    bars["type_a_signal_count"] = bars["type_a_signal_count"].fillna(0).astype(int)
    bars["type_a_category_count"] = bars["type_a_category_count"].fillna(0).astype(int)
    bars["type_a_direction_sum"] = pd.to_numeric(bars["type_a_direction_sum"], errors="coerce").fillna(0.0)
    bars["has_absorption_any"] = bars["has_absorption_any"].fillna(False)
    bars["has_absorption_type_a"] = bars["has_absorption_type_a"].fillna(False)
    bars["scenario_direction"] = np.sign(bars["type_a_direction_sum"])

    signal_scenarios = {
        "type_a_any": bars["has_type_a"] & (bars["scenario_direction"] != 0),
        "type_a_2plus_categories": (bars["type_a_category_count"] >= 2) & (bars["scenario_direction"] != 0),
        "type_a_plus_absorption_any": bars["has_type_a"] & bars["has_absorption_any"] & (bars["scenario_direction"] != 0),
        "type_a_plus_absorption_type_a": bars["has_type_a"] & bars["has_absorption_type_a"] & (bars["scenario_direction"] != 0),
    }

    rows = []
    for scenario, mask in signal_scenarios.items():
        subset = bars.loc[mask]
        row: dict[str, object] = {
            "scenario": scenario,
            "bars": int(len(subset)),
        }
        for w in WINDOWS:
            ret = (subset[f"fwd_close_{w}b"] - subset["bar_close"]) * subset["scenario_direction"] / TICK_SIZE
            ret = ret.dropna()
            row[f"n_{w}b"] = int(ret.count())
            row[f"wr_{w}b"] = float((ret > 0).mean()) if len(ret) else np.nan
            row[f"avg_{w}b"] = float(ret.mean()) if len(ret) else np.nan
            row[f"sharpe_{w}b"] = float(ret.mean() / ret.std(ddof=1)) if len(ret) > 1 and ret.std(ddof=1) > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def top10_full_stats(leaderboard: pd.DataFrame, tier_stats: pd.DataFrame, top_ids: list[str]) -> pd.DataFrame:
    base = leaderboard[leaderboard["signal_id"].isin(top_ids)].copy()
    tier_5b = tier_stats[["signal_id", "score_tier", f"n_{PRIMARY_WINDOW}b", f"wr_{PRIMARY_WINDOW}b", f"avg_{PRIMARY_WINDOW}b", f"sharpe_{PRIMARY_WINDOW}b"]].copy()
    tier_5b = tier_5b.rename(
        columns={
            f"n_{PRIMARY_WINDOW}b": "tier_n_5b",
            f"wr_{PRIMARY_WINDOW}b": "tier_wr_5b",
            f"avg_{PRIMARY_WINDOW}b": "tier_avg_5b",
            f"sharpe_{PRIMARY_WINDOW}b": "tier_sharpe_5b",
        }
    )
    pivot = tier_5b.pivot_table(
        index="signal_id",
        columns="score_tier",
        values=["tier_n_5b", "tier_wr_5b", "tier_avg_5b", "tier_sharpe_5b"],
        aggfunc="first",
    )
    pivot.columns = [f"{metric}_{tier}" for metric, tier in pivot.columns]
    pivot = pivot.reset_index()
    return base.merge(pivot, on="signal_id", how="left").sort_values([f"avg_{PRIMARY_WINDOW}b"], ascending=False)


def format_pct(v: float) -> str:
    return "nan" if pd.isna(v) else f"{v * 100:.1f}%"


def format_num(v: float) -> str:
    return "nan" if pd.isna(v) else f"{v:.2f}"


def render_summary(
    leaderboard: pd.DataFrame,
    categories: pd.DataFrame,
    overall_tiers: pd.DataFrame,
    top10: pd.DataFrame,
    tod_summary: pd.DataFrame,
    absorption_df: pd.DataFrame,
    signal_of_signals_df: pd.DataFrame,
) -> str:
    lines: list[str] = []
    add = lines.append
    add("DEEP6 signal alpha scan")
    add(f"Primary ranking window: {PRIMARY_WINDOW} bars")
    add("")
    add("Top 15 signals by 5-bar expectancy")
    add("signal_id | category | N | WR | avg_5b | sharpe_5b")
    add("---|---:|---:|---:|---:|---:")
    for _, row in leaderboard.head(15).iterrows():
        add(
            f"{row['signal_id']} | {row['category']} | {int(row['n_5b'])} | {format_pct(row['wr_5b'])} | {format_num(row['avg_5b'])} | {format_num(row['sharpe_5b'])}"
        )

    add("")
    add("Category leaderboard by 5-bar expectancy")
    add("category | signals | N | WR | avg_5b | sharpe_5b")
    add("---|---:|---:|---:|---:|---:")
    for _, row in categories.iterrows():
        add(
            f"{row['category']} | {int(row['signals'])} | {int(row['n_5b'])} | {format_pct(row['wr_5b'])} | {format_num(row['avg_5b'])} | {format_num(row['sharpe_5b'])}"
        )

    add("")
    add("Overall score-tier edge by 5-bar expectancy")
    add("score_tier | N | WR | avg_5b | sharpe_5b")
    add("---|---:|---:|---:|---:")
    for _, row in overall_tiers.iterrows():
        add(
            f"{row['score_tier']} | {int(row['n_5b'])} | {format_pct(row['wr_5b'])} | {format_num(row['avg_5b'])} | {format_num(row['sharpe_5b'])}"
        )

    add("")
    add(f"Top 10 deep-dive signals (N >= {MIN_TOP_N} on 5b if available)")
    add("signal_id | category | N | WR | avg_1b | avg_5b | avg_10b | avg_15b | avg_30b | TYPE_A avg_5b | TYPE_B avg_5b | TYPE_C avg_5b | best ET hours")
    add("---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---")
    tod_map = tod_summary.set_index("signal_id").to_dict("index") if not tod_summary.empty else {}
    for _, row in top10.iterrows():
        tod = tod_map.get(row["signal_id"], {})
        add(
            f"{row['signal_id']} | {row['category']} | {int(row['n_5b'])} | {format_pct(row['wr_5b'])} | {format_num(row['avg_1b'])} | {format_num(row['avg_5b'])} | {format_num(row['avg_10b'])} | {format_num(row['avg_15b'])} | {format_num(row['avg_30b'])} | {format_num(row.get('tier_avg_5b_TYPE_A', np.nan))} | {format_num(row.get('tier_avg_5b_TYPE_B', np.nan))} | {format_num(row.get('tier_avg_5b_TYPE_C', np.nan))} | {tod.get('best_hours_et', '')}"
        )

    if not absorption_df.empty:
        add("")
        add("Top 10 absorption interaction (5b)")
        add("signal_id | interaction | N | WR | avg_5b | sharpe_5b")
        add("---|---|---:|---:|---:|---:")
        for _, row in absorption_df.iterrows():
            add(
                f"{row['signal_id']} | {row['interaction']} | {int(row['n'])} | {format_pct(row['wr_5b'])} | {format_num(row['avg_5b'])} | {format_num(row['sharpe_5b'])}"
            )

    add("")
    add("Signal-of-signals scenarios")
    add("scenario | bars | avg_1b | avg_5b | avg_10b | avg_15b | avg_30b")
    add("---|---:|---:|---:|---:|---:|---:")
    for _, row in signal_of_signals_df.iterrows():
        add(
            f"{row['scenario']} | {int(row['bars'])} | {format_num(row['avg_1b'])} | {format_num(row['avg_5b'])} | {format_num(row['avg_10b'])} | {format_num(row['avg_15b'])} | {format_num(row['avg_30b'])}"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Comprehensive alpha scan across all DEEP6 signal IDs.")
    parser.add_argument("--input", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR / "alpha_scan")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-top-n", type=int, default=MIN_TOP_N)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    df = load_events(args.input)

    signal_stats = stats_frame(df, ["signal_id", "category"])
    leaderboard = leaderboard_table(signal_stats)
    tiers = signal_tier_summary(df)
    categories = category_summary(df)
    overall_tiers = overall_tier_summary(df)
    top_ids = top_signal_ids(leaderboard, args.min_top_n, args.top_n)
    top10 = top10_full_stats(leaderboard, tiers, top_ids)
    tod_detail, tod_summary = time_of_day_for_signals(df, top_ids)
    absorption_df = absorption_interactions(df, top_ids)
    signal_of_signals_df = signal_of_signals(df)

    leaderboard.to_csv(args.outdir / "signal_leaderboard_by_5b_expectancy.csv", index=False)
    tiers.to_csv(args.outdir / "signal_score_tier_stats.csv", index=False)
    overall_tiers.to_csv(args.outdir / "overall_score_tier_summary.csv", index=False)
    categories.to_csv(args.outdir / "category_summary.csv", index=False)
    top10.to_csv(args.outdir / "top10_signal_deep_dive.csv", index=False)
    tod_detail.to_csv(args.outdir / "top10_time_of_day_detail.csv", index=False)
    tod_summary.to_csv(args.outdir / "top10_time_of_day_summary.csv", index=False)
    absorption_df.to_csv(args.outdir / "top10_absorption_interactions.csv", index=False)
    signal_of_signals_df.to_csv(args.outdir / "signal_of_signals.csv", index=False)

    summary_text = render_summary(leaderboard, categories, overall_tiers, top10, tod_summary, absorption_df, signal_of_signals_df)
    (args.outdir / "alpha_scan_summary.md").write_text(summary_text, encoding="utf-8")
    metadata = {
        "input": str(args.input),
        "rows": int(len(df)),
        "signals": int(df["signal_id"].nunique()),
        "categories": int(df["category"].nunique()),
        "top_signal_ids": top_ids,
        "primary_window": PRIMARY_WINDOW,
    }
    (args.outdir / "alpha_scan_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(summary_text)


if __name__ == "__main__":
    main()
