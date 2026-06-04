#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "backtests" / "signal_events.csv"
OUT_DIR = ROOT / "data" / "backtests" / "analysis"
REPORT_MD = OUT_DIR / "reversal_family_report.md"
SUMMARY_CSV = OUT_DIR / "reversal_family_summary.csv"
COMBO_CSV = OUT_DIR / "reversal_family_combo_rankings.csv"

WINDOWS = (5, 10, 15, 30)
PRIMARY_WINDOW = 10
MIN_COMBO_N = 10
FAMILIES = ("absorption", "exhaustion", "trapped")


@dataclass(frozen=True)
class SequenceSpec:
    name: str
    first_family: str
    second_family: str
    max_gap: int


def load_events() -> pd.DataFrame:
    usecols = [
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
        "bar_close",
        "fwd_close_5b",
        "fwd_close_10b",
        "fwd_close_15b",
        "fwd_close_30b",
    ]
    dtypes = {
        "session_date": "string",
        "signal_id": "string",
        "category": "string",
        "direction": "string",
        "score_tier": "string",
        "bar_index": "int32",
        "global_index": "int32",
        "strength": "float64",
        "score_final": "float64",
        "bar_close": "float64",
        "fwd_close_5b": "float64",
        "fwd_close_10b": "float64",
        "fwd_close_15b": "float64",
        "fwd_close_30b": "float64",
    }
    df = pd.read_csv(EVENTS_CSV, usecols=usecols, dtype=dtypes, low_memory=False)
    df = df[df["category"].isin(FAMILIES)].copy()
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce")
    df["direction"] = pd.to_numeric(df["direction"], errors="coerce")
    df = df[df["direction"].isin([-1, 1])].copy()
    df["direction"] = df["direction"].astype("int8")
    for w in WINDOWS:
        df[f"ret_{w}b"] = df["direction"] * (df[f"fwd_close_{w}b"] - df["bar_close"])
    return df.sort_values(["global_index", "signal_id"], kind="stable").reset_index(drop=True)


def sharpe(series: pd.Series) -> float:
    std = float(series.std(ddof=1))
    if std == 0.0 or np.isnan(std):
        return 0.0
    return float(series.mean() / std)


def metric_row(df: pd.DataFrame, label: str, cohort: str, extra: dict | None = None) -> dict:
    row: dict[str, object] = {
        "label": label,
        "cohort": cohort,
        "n": int(len(df)),
    }
    for w in WINDOWS:
        ret = df[f"ret_{w}b"].dropna()
        row[f"wr_{w}b"] = float((ret > 0).mean()) if len(ret) else np.nan
        row[f"avg_{w}b"] = float(ret.mean()) if len(ret) else np.nan
        row[f"median_{w}b"] = float(ret.median()) if len(ret) else np.nan
        row[f"sharpe_{w}b"] = sharpe(ret) if len(ret) else np.nan
    if extra:
        row.update(extra)
    return row


def summarize_groups(df: pd.DataFrame, by: list[str], cohort: str) -> pd.DataFrame:
    rows: list[dict] = []
    for key, grp in df.groupby(by, dropna=False, observed=False, sort=True):
        key_tuple = key if isinstance(key, tuple) else (key,)
        extra = {col: val for col, val in zip(by, key_tuple)}
        label = " | ".join(f"{col}={val}" for col, val in extra.items())
        rows.append(metric_row(grp, label=label, cohort=cohort, extra=extra))
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("avg_10b", ascending=False, na_position="last")


def build_family_bar_events(df: pd.DataFrame) -> pd.DataFrame:
    agg = {
        "session_date": "first",
        "bar_ts": "first",
        "bar_index": "first",
        "score_tier": lambda s: ",".join(sorted(s.dropna().unique())),
        "signal_id": lambda s: ",".join(sorted(s.dropna().unique())),
    }
    for w in WINDOWS:
        agg[f"ret_{w}b"] = "mean"
    out = (
        df.groupby(["category", "global_index", "direction"], observed=False, sort=True)
        .agg(agg)
        .reset_index()
        .rename(columns={"category": "family", "signal_id": "signal_ids", "score_tier": "score_tiers"})
    )
    return out


def merge_prior_signal(
    events: pd.DataFrame,
    lead_family: str,
    follow_family: str,
    max_gap: int,
    include_same_bar: bool = False,
) -> pd.DataFrame:
    matched: list[pd.DataFrame] = []
    allow_exact = include_same_bar
    for direction in (-1, 1):
        lead = events[(events["family"] == lead_family) & (events["direction"] == direction)].copy()
        follow = events[(events["family"] == follow_family) & (events["direction"] == direction)].copy()
        if lead.empty or follow.empty:
            continue
        lead = lead.sort_values("global_index").rename(
            columns={
                "global_index": "lead_global_index",
                "bar_index": "lead_bar_index",
                "bar_ts": "lead_bar_ts",
                "signal_ids": "lead_signal_ids",
                "score_tiers": "lead_score_tiers",
            }
        )
        follow = follow.sort_values("global_index").rename(
            columns={
                "global_index": "confirm_global_index",
                "bar_index": "confirm_bar_index",
                "bar_ts": "confirm_bar_ts",
                "signal_ids": "confirm_signal_ids",
                "score_tiers": "confirm_score_tiers",
            }
        )
        merged = pd.merge_asof(
            follow,
            lead[[
                "lead_global_index",
                "lead_bar_index",
                "lead_bar_ts",
                "lead_signal_ids",
                "lead_score_tiers",
            ]],
            left_on="confirm_global_index",
            right_on="lead_global_index",
            direction="backward",
            allow_exact_matches=allow_exact,
        )
        merged["gap_bars"] = merged["confirm_global_index"] - merged["lead_global_index"]
        merged = merged[merged["gap_bars"].between(0 if include_same_bar else 1, max_gap)].copy()
        if not merged.empty:
            merged["lead_family"] = lead_family
            merged["confirm_family"] = follow_family
            matched.append(merged)
    if not matched:
        return pd.DataFrame()
    return pd.concat(matched, ignore_index=True)


def exact_gap_summary(seq_df: pd.DataFrame, name: str) -> pd.DataFrame:
    rows: list[dict] = []
    for gap, grp in seq_df.groupby("gap_bars", observed=False, sort=True):
        rows.append(metric_row(grp, label=f"{name} gap={int(gap)}", cohort="sequence_gap", extra={"combo_name": name, "gap_bars": int(gap)}))
    out = pd.DataFrame(rows)
    return out.sort_values("avg_10b", ascending=False, na_position="last")


def same_bar_family_combo(events: pd.DataFrame, family_a: str, family_b: str) -> pd.DataFrame:
    left = events[events["family"] == family_a][["global_index", "direction"] + [f"ret_{w}b" for w in WINDOWS]].copy()
    right = events[events["family"] == family_b][["global_index", "direction"]].copy()
    combo = left.merge(right, on=["global_index", "direction"], how="inner")
    combo = combo.drop_duplicates(subset=["global_index", "direction"])
    return combo


def rank_raw_signal_combos(df: pd.DataFrame) -> pd.DataFrame:
    combo_rows: list[dict] = []
    combo_source = df[df["category"].isin(FAMILIES)].copy()
    grouped = combo_source.groupby(["global_index", "direction"], observed=False, sort=True)
    for (global_index, direction), grp in grouped:
        signal_ids = sorted(grp["signal_id"].dropna().unique().tolist())
        if len(signal_ids) < 2:
            continue
        payload = {
            f"ret_{w}b": float(grp[f"ret_{w}b"].mean()) for w in WINDOWS
        }
        for size in (2, 3):
            if len(signal_ids) < size:
                continue
            for combo in combinations(signal_ids, size):
                combo_rows.append(
                    {
                        "combo_type": f"same_bar_signal_{size}",
                        "combo_name": " + ".join(combo),
                        "n_signals": size,
                        "global_index": int(global_index),
                        "direction": int(direction),
                        **payload,
                    }
                )
    if not combo_rows:
        return pd.DataFrame()
    combos = pd.DataFrame(combo_rows)
    rows: list[dict] = []
    for (combo_type, combo_name, n_signals), grp in combos.groupby(["combo_type", "combo_name", "n_signals"], observed=False, sort=True):
        summary = metric_row(
            grp,
            label=str(combo_name),
            cohort="combo_ranking",
            extra={"combo_type": combo_type, "combo_name": combo_name, "n_signals": int(n_signals)},
        )
        rows.append(summary)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["avg_10b", "n"], ascending=[False, False], na_position="last")


def fmt_num(value: object, pct: bool = False) -> str:
    if value is None:
        return "-"
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return "-"
    if pct:
        return f"{float(value) * 100:.2f}%"
    return f"{float(value):.4f}"


def markdown_table(df: pd.DataFrame, cols: list[str], pct_cols: set[str] | None = None, limit: int | None = None) -> list[str]:
    pct_cols = pct_cols or set()
    use = df.head(limit) if limit else df
    headers = [str(c) for c in cols]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in use.iterrows():
        vals = []
        for col in cols:
            value = row[col]
            if col == "n":
                vals.append(f"{int(value):,}")
            elif col in pct_cols:
                vals.append(fmt_num(value, pct=True))
            elif isinstance(value, (float, np.floating)):
                vals.append(fmt_num(value))
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_events()
    family_events = build_family_bar_events(df)

    summary_frames: list[pd.DataFrame] = []

    raw_family = summarize_groups(df[df["category"].isin(["absorption", "exhaustion"])], ["category"], "raw_family")
    raw_signal = summarize_groups(df[df["category"].isin(["absorption", "exhaustion"])], ["category", "signal_id"], "raw_signal")
    raw_tier = summarize_groups(df[df["category"].isin(["absorption", "exhaustion"])], ["category", "score_tier"], "raw_score_tier")
    exh_type_ab = summarize_groups(df[(df["category"] == "exhaustion") & (df["score_tier"].isin(["TYPE_A", "TYPE_B"]))], ["score_tier"], "exhaustion_type_ab")
    family_event_perf = summarize_groups(family_events[family_events["family"].isin(["absorption", "exhaustion"])].rename(columns={"family": "category"}), ["category"], "family_event_baseline")

    summary_frames.extend([raw_family, raw_signal, raw_tier, exh_type_ab, family_event_perf])

    seq_specs = [
        SequenceSpec("exhaustion_then_absorption_5", "exhaustion", "absorption", 5),
        SequenceSpec("exhaustion_then_absorption_10", "exhaustion", "absorption", 10),
        SequenceSpec("exhaustion_then_absorption_30", "exhaustion", "absorption", 30),
        SequenceSpec("absorption_then_exhaustion_5", "absorption", "exhaustion", 5),
        SequenceSpec("absorption_then_exhaustion_10", "absorption", "exhaustion", 10),
        SequenceSpec("absorption_then_exhaustion_30", "absorption", "exhaustion", 30),
    ]
    sequence_frames: list[pd.DataFrame] = []
    exact_gap_frames: list[pd.DataFrame] = []
    for spec in seq_specs:
        seq = merge_prior_signal(family_events, spec.first_family, spec.second_family, spec.max_gap)
        if seq.empty:
            continue
        sequence_frames.append(
            pd.DataFrame([
                metric_row(
                    seq,
                    label=spec.name,
                    cohort="sequence_window",
                    extra={
                        "combo_name": spec.name,
                        "combo_type": "sequence",
                        "n_signals": 2,
                        "first_family": spec.first_family,
                        "second_family": spec.second_family,
                        "max_gap": spec.max_gap,
                        "best_exact_gap": int(seq.groupby("gap_bars")["ret_10b"].mean().idxmax()),
                    },
                )
            ])
        )
        exact_gap_frames.append(exact_gap_summary(seq, spec.name))

    simultaneous = same_bar_family_combo(family_events, "absorption", "exhaustion")
    simultaneous_summary = pd.DataFrame([
        metric_row(
            simultaneous,
            label="absorption_and_exhaustion_same_bar",
            cohort="same_bar_family",
            extra={"combo_name": "absorption_and_exhaustion_same_bar", "combo_type": "same_bar_family", "n_signals": 2},
        )
    ]) if not simultaneous.empty else pd.DataFrame()

    absorption_with_prior_exh = merge_prior_signal(family_events, "exhaustion", "absorption", 10)
    absorption_filter_summary = pd.DataFrame()
    if not absorption_with_prior_exh.empty:
        baseline_abs = family_events[family_events["family"] == "absorption"].copy()
        absorption_filter_summary = pd.concat(
            [
                pd.DataFrame([
                    metric_row(baseline_abs, label="absorption_all_family_events", cohort="absorption_filter", extra={"filter": "baseline"})
                ]),
                pd.DataFrame([
                    metric_row(absorption_with_prior_exh, label="absorption_with_prior_exhaustion_10b", cohort="absorption_filter", extra={"filter": "prior_exhaustion_10b"})
                ]),
            ],
            ignore_index=True,
        )

    trapped_same_bar = same_bar_family_combo(family_events, "trapped", "absorption")
    trapped_prior3 = merge_prior_signal(family_events, "trapped", "absorption", 3, include_same_bar=True)
    trapped_summary_parts: list[pd.DataFrame] = []
    if not trapped_same_bar.empty:
        trapped_summary_parts.append(
            pd.DataFrame([
                metric_row(trapped_same_bar, label="trapped_and_absorption_same_bar", cohort="trapped_confirmation", extra={"combo_name": "trapped_and_absorption_same_bar", "combo_type": "same_bar_family", "n_signals": 2})
            ])
        )
    if not trapped_prior3.empty:
        trapped_summary_parts.append(
            pd.DataFrame([
                metric_row(trapped_prior3, label="trapped_then_absorption_within_3b", cohort="trapped_confirmation", extra={"combo_name": "trapped_then_absorption_within_3b", "combo_type": "sequence", "n_signals": 2})
            ])
        )
    trapped_summary = pd.concat(trapped_summary_parts, ignore_index=True) if trapped_summary_parts else pd.DataFrame()

    raw_combo_rank = rank_raw_signal_combos(df)

    combo_rank_frames = [frame for frame in sequence_frames + [simultaneous_summary, trapped_summary, raw_combo_rank] if not frame.empty]
    combo_rankings = pd.concat(combo_rank_frames, ignore_index=True) if combo_rank_frames else pd.DataFrame()
    if not combo_rankings.empty:
        combo_rankings = combo_rankings.sort_values(["avg_10b", "n"], ascending=[False, False], na_position="last")
        combo_rankings.to_csv(COMBO_CSV, index=False)

    if exact_gap_frames:
        exact_gap_df = pd.concat(exact_gap_frames, ignore_index=True)
        summary_frames.append(exact_gap_df)
    for frame in [simultaneous_summary, absorption_filter_summary, trapped_summary]:
        if not frame.empty:
            summary_frames.append(frame)
    if not raw_combo_rank.empty:
        summary_frames.append(raw_combo_rank)

    summary = pd.concat([frame for frame in summary_frames if not frame.empty], ignore_index=True)
    summary.to_csv(SUMMARY_CSV, index=False)

    stable_combo_rank = combo_rankings[combo_rankings["n"] >= MIN_COMBO_N].copy() if not combo_rankings.empty else pd.DataFrame()
    best_combo = stable_combo_rank.iloc[0] if not stable_combo_rank.empty else (combo_rankings.iloc[0] if not combo_rankings.empty else None)

    report: list[str] = []
    report.append("# Reversal Family Head-to-Head")
    report.append("")
    report.append(f"Source: `{EVENTS_CSV}`")
    report.append("")
    report.append(f"Primary ranking horizon: **{PRIMARY_WINDOW} bars** (all tables also include 5/15/30b metrics).")
    report.append("")
    if best_combo is not None:
        report.append("## Best stable combination")
        report.append("")
        report.append(
            f"- **{best_combo.get('combo_name', best_combo['label'])}** | N={int(best_combo['n']):,} | "
            f"WR10={fmt_num(best_combo['wr_10b'], pct=True)} | Avg10={fmt_num(best_combo['avg_10b'])} | Sharpe10={fmt_num(best_combo['sharpe_10b'])}"
        )
        report.append("")

    report.append("## 1) Absorption vs Exhaustion — raw performance")
    report.append("")
    report.extend(markdown_table(
        raw_family,
        ["category", "n", "wr_5b", "avg_5b", "median_5b", "sharpe_5b", "wr_10b", "avg_10b", "median_10b", "sharpe_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b"],
        pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
    ))
    report.append("")
    report.append("### By signal_id")
    report.append("")
    report.extend(markdown_table(
        raw_signal,
        ["category", "signal_id", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
        pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
    ))
    report.append("")
    report.append("### By score_tier")
    report.append("")
    report.extend(markdown_table(
        raw_tier,
        ["category", "score_tier", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b"],
        pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
    ))
    report.append("")

    report.append("## 2) Why does exhaustion have 152K signals?")
    report.append("")
    report.append("### Exhaustion TYPE_A/B only")
    report.append("")
    if not exh_type_ab.empty:
        report.extend(markdown_table(
            exh_type_ab,
            ["score_tier", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
        ))
    else:
        report.append("No TYPE_A/B exhaustion rows found.")
    report.append("")
    report.append("### Per-family event expectancy (deduped to one family-direction event per bar)")
    report.append("")
    report.extend(markdown_table(
        family_event_perf,
        ["category", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
        pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
    ))
    report.append("")

    report.append("## 3) Absorption + Exhaustion sequence")
    report.append("")
    sequence_summary = pd.concat(sequence_frames, ignore_index=True) if sequence_frames else pd.DataFrame()
    if not sequence_summary.empty:
        report.extend(markdown_table(
            sequence_summary.sort_values(["avg_10b", "n"], ascending=[False, False]),
            ["combo_name", "n", "first_family", "second_family", "max_gap", "best_exact_gap", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
        ))
        report.append("")
        if exact_gap_frames:
            best_gap_table = pd.concat(exact_gap_frames, ignore_index=True)
            report.append("### Exact-gap ranking")
            report.append("")
            report.extend(markdown_table(
                best_gap_table.sort_values(["avg_10b", "n"], ascending=[False, False]),
                ["combo_name", "gap_bars", "n", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b"],
                pct_cols={"wr_10b", "wr_15b", "wr_30b"},
                limit=20,
            ))
    else:
        report.append("No valid sequences found.")
    report.append("")

    report.append("## 4) Double confirmation: absorption + exhaustion same bar")
    report.append("")
    if not simultaneous_summary.empty:
        report.extend(markdown_table(
            simultaneous_summary,
            ["label", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
        ))
    else:
        report.append("No same-bar absorption+exhaustion confirmations found.")
    report.append("")

    report.append("## 5) Exhaustion as a filter for absorption")
    report.append("")
    if not absorption_filter_summary.empty:
        report.extend(markdown_table(
            absorption_filter_summary,
            ["label", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
        ))
    else:
        report.append("No absorption events had prior exhaustion within 10 bars.")
    report.append("")

    report.append("## 6) Trapped signals as confirmation")
    report.append("")
    if not trapped_summary.empty:
        report.extend(markdown_table(
            trapped_summary,
            ["label", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
        ))
    else:
        report.append("No trapped+absorption confirmations found.")
    report.append("")

    report.append("## 7) Ranked 2-signal / 3-signal combinations")
    report.append("")
    if not combo_rankings.empty:
        report.extend(markdown_table(
            combo_rankings,
            ["combo_type", "combo_name", "n_signals", "n", "wr_5b", "avg_5b", "wr_10b", "avg_10b", "wr_15b", "avg_15b", "wr_30b", "avg_30b", "sharpe_10b"],
            pct_cols={"wr_5b", "wr_10b", "wr_15b", "wr_30b"},
            limit=40,
        ))
        report.append("")
        report.append(f"Full ranking CSV: `{COMBO_CSV}`")
    else:
        report.append("No combinations ranked.")
    report.append("")

    REPORT_MD.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote report: {REPORT_MD}")
    print(f"Wrote summary csv: {SUMMARY_CSV}")
    if not combo_rankings.empty:
        print(f"Wrote combo ranking csv: {COMBO_CSV}")


if __name__ == "__main__":
    main()
