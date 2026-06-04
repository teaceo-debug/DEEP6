#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EVENTS_CSV = ROOT / "data" / "backtests" / "signal_events.csv"
TELEGRAM_JSON = ROOT / "data" / "telegram_levels" / "raw_nq.json"
OUT_DIR = ROOT / "data" / "backtests" / "analysis"
OUT_JSON = OUT_DIR / "absorption_walkforward_robustness.json"

ET_TZ = "America/New_York"
TICK_SIZE = 0.25
HALF_SPLIT_SEED = 42
PERIODS = [
    ("P1", pd.Timestamp("2025-01-01"), pd.Timestamp("2025-07-01")),
    ("P2", pd.Timestamp("2025-07-01"), pd.Timestamp("2026-01-01")),
    ("P3", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-05-01")),
]
PERIOD_ORDER = [name for name, _, _ in PERIODS]


def _fmt_wr(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value * 100:.1f}%"


def _fmt_ticks(value: float | None) -> str:
    return "n/a" if value is None or pd.isna(value) else f"{value:+.2f}t"


def _serialise(value):
    if isinstance(value, dict):
        return {str(k): _serialise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialise(v) for v in value]
    if isinstance(value, tuple):
        return [_serialise(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if np.isnan(value) or np.isinf(value):
            return None
        return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def compute_stats(df: pd.DataFrame) -> dict:
    returns = df["return_5b_ticks"].dropna().to_numpy(dtype=float)
    n = int(len(returns))
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_ticks": None, "median_ticks": None}
    return {
        "n": n,
        "win_rate": float((returns > 0).mean()),
        "avg_ticks": float(returns.mean()),
        "median_ticks": float(np.median(returns)),
    }


def trimmed_stats(df: pd.DataFrame) -> dict:
    n = len(df)
    k = 0
    if n >= 10:
        k = max(1, int(np.floor(n * 0.05)))
    if k == 0 or (n - 2 * k) <= 0:
        out = compute_stats(df)
        out["trim_each_side"] = 0
        return out
    trimmed = df.sort_values("return_5b_ticks").iloc[k : n - k]
    out = compute_stats(trimmed)
    out["trim_each_side"] = k
    return out


def half_split_stats(df: pd.DataFrame, seed: int = HALF_SPLIT_SEED) -> list[dict]:
    n = len(df)
    if n < 2:
        return []
    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    mid = n // 2
    halves = [df.iloc[order[:mid]], df.iloc[order[mid:]]]
    out = []
    for label, subset in zip(("H1", "H2"), halves, strict=True):
        stats = compute_stats(subset)
        stats["label"] = label
        out.append(stats)
    return out


def flipped_stats(df: pd.DataFrame) -> dict:
    flipped = df.copy()
    flipped["return_5b_ticks"] = -flipped["return_5b_ticks"]
    return compute_stats(flipped)


def assign_period(session_dates: pd.Series) -> pd.Series:
    period = pd.Series(pd.NA, index=session_dates.index, dtype="object")
    for name, start, end in PERIODS:
        mask = (session_dates >= start) & (session_dates < end)
        period.loc[mask] = name
    return period


def add_prior_absorption_counts(df: pd.DataFrame) -> pd.DataFrame:
    # Reset the index after filtering/sorting so positional writes into the
    # counts array cannot use sparse source CSV row labels (for example 9214)
    # against a compact array sized to the filtered absorption rows.
    df = df.sort_values(["session_date", "bar_index"]).reset_index(drop=True).copy()
    counts = np.zeros(len(df), dtype=int)
    for _, grp in df.groupby("session_date", sort=False):
        bars = grp["bar_index"].to_numpy(dtype=int)
        grp_counts = np.zeros(len(grp), dtype=int)
        left = 0
        for i, bar in enumerate(bars):
            while bars[left] < (bar - 30):
                left += 1
            grp_counts[i] = i - left
        counts[grp.index.to_numpy()] = grp_counts
    df["prior_abs_30" ] = counts
    return df


def load_events() -> tuple[pd.DataFrame, dict]:
    usecols = [
        "session_date",
        "bar_ts",
        "bar_index",
        "signal_id",
        "category",
        "direction",
        "strength",
        "score_tier",
        "bar_high",
        "bar_low",
        "bar_close",
        "fwd_close_5b",
    ]
    df = pd.read_csv(EVENTS_CSV, usecols=usecols, low_memory=False)
    df = df[df["category"] == "absorption"].copy()
    df["session_date"] = pd.to_datetime(df["session_date"], errors="coerce")
    df["bar_ts"] = pd.to_datetime(df["bar_ts"], utc=True, errors="coerce")
    df["direction"] = pd.to_numeric(df["direction"], errors="coerce")
    df["bar_close"] = pd.to_numeric(df["bar_close"], errors="coerce")
    df["fwd_close_5b"] = pd.to_numeric(df["fwd_close_5b"], errors="coerce")
    df["bar_high"] = pd.to_numeric(df["bar_high"], errors="coerce")
    df["bar_low"] = pd.to_numeric(df["bar_low"], errors="coerce")
    df["strength"] = pd.to_numeric(df["strength"], errors="coerce")
    df["return_5b_ticks"] = df["direction"] * (df["fwd_close_5b"] - df["bar_close"]) / TICK_SIZE
    df["bar_range"] = df["bar_high"] - df["bar_low"]
    df["bar_ts_et"] = df["bar_ts"].dt.tz_convert(ET_TZ)
    df["time_bucket_30m"] = df["bar_ts_et"].dt.floor("30min").dt.strftime("%H:%M")
    df["period"] = assign_period(df["session_date"])
    df = df.dropna(subset=["session_date", "bar_ts", "direction", "return_5b_ticks", "period", "bar_range"]).copy()
    df = add_prior_absorption_counts(df)

    q1, q2, q3 = df["bar_range"].quantile([0.25, 0.50, 0.75]).tolist()
    df["range_bucket"] = np.select(
        [
            df["bar_range"] <= q1,
            df["bar_range"] <= q2,
            df["bar_range"] <= q3,
        ],
        ["Q1", "Q2", "Q3"],
        default="Q4",
    )
    meta = {
        "rows": int(len(df)),
        "range_cutoffs": {"q1": float(q1), "q2": float(q2), "q3": float(q3)},
    }
    return df, meta


def load_telegram_summary() -> dict:
    messages = json.loads(TELEGRAM_JSON.read_text(encoding="utf-8"))
    pattern = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    rows = []
    for message in messages:
        text = (message.get("text") or "").strip()
        if not pattern.match(text):
            continue
        ts = pd.Timestamp(message["date"])
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        rows.append(ts.tz_convert(ET_TZ))
    if not rows:
        return {"total_nq_absorption_alerts": 0, "period_counts": {name: 0 for name in PERIOD_ORDER}}
    series = pd.Series(rows, name="ts_et")
    dates = pd.to_datetime(series.dt.date.astype(str))
    period_counts = {}
    for name, start, end in PERIODS:
        period_counts[name] = int(((dates >= start) & (dates < end)).sum())
    return {
        "total_nq_absorption_alerts": int(len(series)),
        "period_counts": period_counts,
    }


def evaluate_single(df: pd.DataFrame, label: str, mask: pd.Series) -> dict:
    subset = df[mask].copy()
    period_stats = {}
    period_failures = []
    half_failures = []
    half_stats = {}
    for period in PERIOD_ORDER:
        per = subset[subset["period"] == period]
        stats = compute_stats(per)
        period_stats[period] = stats
        halves = half_split_stats(per)
        half_stats[period] = halves
        if stats["n"] < 5:
            period_failures.append(f"{period}: insufficient N={stats['n']}")
        elif (stats["avg_ticks"] or 0) <= 0 or (stats["win_rate"] or 0) <= 0.50:
            period_failures.append(
                f"{period}: WR={_fmt_wr(stats['win_rate'])}, Avg={_fmt_ticks(stats['avg_ticks'])}"
            )
        for half in halves:
            if half["n"] == 0:
                continue
            if (half["avg_ticks"] or 0) <= 0:
                half_failures.append(f"{period}-{half['label']}: Avg={_fmt_ticks(half['avg_ticks'])}")
    full_stats = compute_stats(subset)
    trimmed = trimmed_stats(subset)
    flipped = flipped_stats(subset)

    fragility = []
    if (trimmed["avg_ticks"] or 0) <= 0:
        fragility.append(
            f"trimmed edge disappeared (WR={_fmt_wr(trimmed['win_rate'])}, Avg={_fmt_ticks(trimmed['avg_ticks'])})"
        )
    if full_stats["avg_ticks"] is not None and flipped["avg_ticks"] is not None and flipped["avg_ticks"] >= full_stats["avg_ticks"]:
        fragility.append("flipped direction was as good or better")
    if half_failures:
        fragility.append("random half-split instability")

    verdict = "PASS"
    reasons = []
    if period_failures:
        verdict = "FAIL"
        reasons.extend(period_failures)
    if fragility:
        verdict = "FAIL"
        reasons.extend(fragility)

    return {
        "label": label,
        "kind": "single",
        "full": full_stats,
        "periods": period_stats,
        "halves": half_stats,
        "trimmed": trimmed,
        "flipped": flipped,
        "verdict": verdict,
        "reasons": reasons,
    }


def evaluate_comparison(df: pd.DataFrame, label: str, target_mask: pd.Series, compare_mask: pd.Series) -> dict:
    target = df[target_mask].copy()
    compare = df[compare_mask].copy()
    period_stats = {}
    period_failures = []
    half_failures = []
    half_stats = {}
    for period in PERIOD_ORDER:
        t_per = target[target["period"] == period]
        c_per = compare[compare["period"] == period]
        t_stats = compute_stats(t_per)
        c_stats = compute_stats(c_per)
        period_stats[period] = {"target": t_stats, "compare": c_stats}
        halves = half_split_stats(t_per)
        half_stats[period] = halves
        if t_stats["n"] < 5:
            period_failures.append(f"{period}: target insufficient N={t_stats['n']}")
        elif c_stats["n"] < 5:
            period_failures.append(f"{period}: comparator insufficient N={c_stats['n']}")
        else:
            t_avg = t_stats["avg_ticks"] or 0
            c_avg = c_stats["avg_ticks"] or 0
            t_wr = t_stats["win_rate"] or 0
            c_wr = c_stats["win_rate"] or 0
            if t_avg <= 0 or t_avg <= c_avg or t_wr <= c_wr:
                period_failures.append(
                    f"{period}: target WR/Avg {_fmt_wr(t_stats['win_rate'])}/{_fmt_ticks(t_stats['avg_ticks'])} vs comparator {_fmt_wr(c_stats['win_rate'])}/{_fmt_ticks(c_stats['avg_ticks'])}"
                )
        for half in halves:
            if half["n"] == 0:
                continue
            if (half["avg_ticks"] or 0) <= 0:
                half_failures.append(f"{period}-{half['label']}: Avg={_fmt_ticks(half['avg_ticks'])}")
    full_stats = {"target": compute_stats(target), "compare": compute_stats(compare)}
    trimmed = trimmed_stats(target)
    flipped = flipped_stats(target)

    fragility = []
    if (trimmed["avg_ticks"] or 0) <= 0:
        fragility.append(
            f"trimmed target edge disappeared (WR={_fmt_wr(trimmed['win_rate'])}, Avg={_fmt_ticks(trimmed['avg_ticks'])})"
        )
    if full_stats["target"]["avg_ticks"] is not None and flipped["avg_ticks"] is not None and flipped["avg_ticks"] >= full_stats["target"]["avg_ticks"]:
        fragility.append("flipped direction was as good or better")
    if half_failures:
        fragility.append("random half-split instability")

    verdict = "PASS"
    reasons = []
    if period_failures:
        verdict = "FAIL"
        reasons.extend(period_failures)
    if fragility:
        verdict = "FAIL"
        reasons.extend(fragility)

    return {
        "label": label,
        "kind": "comparison",
        "full": full_stats,
        "periods": period_stats,
        "halves": half_stats,
        "trimmed": trimmed,
        "flipped": flipped,
        "verdict": verdict,
        "reasons": reasons,
    }


def build_report(df: pd.DataFrame, meta: dict, telegram: dict) -> dict:
    overlap = int(((df["score_tier"] == "TYPE_B") & (df["strength"] >= 0.20)).sum())
    findings = [
        evaluate_single(df, "1. TYPE_B absorption", df["score_tier"] == "TYPE_B"),
        evaluate_single(df, "2. Strength >= 0.20", df["strength"] >= 0.20),
        evaluate_single(df, "3. ABS_04 in 15:30 ET half-hour bucket", (df["signal_id"] == "ABS_04") & (df["time_bucket_30m"] == "15:30")),
        evaluate_comparison(df, "4. Tight bar range (Q1/Q2) vs wide (Q3/Q4)", df["range_bucket"].isin(["Q1", "Q2"]), df["range_bucket"].isin(["Q3", "Q4"])),
        evaluate_comparison(df, "5. Clustering: >=3 prior absorptions in 30 bars", df["prior_abs_30"] >= 3, df["prior_abs_30"] < 3),
    ]
    return {
        "inputs": {
            "events_csv": str(EVENTS_CSV),
            "telegram_json": str(TELEGRAM_JSON),
            "absorption_rows": int(len(df)),
            "range_cutoffs": meta["range_cutoffs"],
            "type_b_strength_overlap": overlap,
            "telegram": telegram,
        },
        "findings": findings,
    }


def print_single(result: dict) -> None:
    full = result["full"]
    print(f"{result['label']}  [{result['verdict']}]")
    print(f"  Full sample: N={full['n']}, WR={_fmt_wr(full['win_rate'])}, Avg={_fmt_ticks(full['avg_ticks'])}, Median={_fmt_ticks(full['median_ticks'])}")
    for period in PERIOD_ORDER:
        stats = result["periods"][period]
        print(f"  {period}: N={stats['n']}, WR={_fmt_wr(stats['win_rate'])}, Avg={_fmt_ticks(stats['avg_ticks'])}")
        halves = result["halves"][period]
        if halves:
            half_text = " | ".join(
                f"{half['label']}: N={half['n']}, WR={_fmt_wr(half['win_rate'])}, Avg={_fmt_ticks(half['avg_ticks'])}"
                for half in halves
            )
            print(f"     halves -> {half_text}")
    trimmed = result["trimmed"]
    print(
        f"  Trimmed ±5%: N={trimmed['n']}, WR={_fmt_wr(trimmed['win_rate'])}, Avg={_fmt_ticks(trimmed['avg_ticks'])}, trim_each_side={trimmed['trim_each_side']}"
    )
    flipped = result["flipped"]
    print(f"  Flipped direction: N={flipped['n']}, WR={_fmt_wr(flipped['win_rate'])}, Avg={_fmt_ticks(flipped['avg_ticks'])}")
    if result["reasons"]:
        for reason in result["reasons"]:
            print(f"  FAIL reason: {reason}")
    print()


def print_comparison(result: dict) -> None:
    full = result["full"]
    t_full = full["target"]
    c_full = full["compare"]
    print(f"{result['label']}  [{result['verdict']}]")
    print(
        f"  Full sample target: N={t_full['n']}, WR={_fmt_wr(t_full['win_rate'])}, Avg={_fmt_ticks(t_full['avg_ticks'])} | comparator: N={c_full['n']}, WR={_fmt_wr(c_full['win_rate'])}, Avg={_fmt_ticks(c_full['avg_ticks'])}"
    )
    for period in PERIOD_ORDER:
        pair = result["periods"][period]
        t_stats = pair["target"]
        c_stats = pair["compare"]
        print(
            f"  {period}: target N={t_stats['n']}, WR={_fmt_wr(t_stats['win_rate'])}, Avg={_fmt_ticks(t_stats['avg_ticks'])} | comparator N={c_stats['n']}, WR={_fmt_wr(c_stats['win_rate'])}, Avg={_fmt_ticks(c_stats['avg_ticks'])}"
        )
        halves = result["halves"][period]
        if halves:
            half_text = " | ".join(
                f"{half['label']}: N={half['n']}, WR={_fmt_wr(half['win_rate'])}, Avg={_fmt_ticks(half['avg_ticks'])}"
                for half in halves
            )
            print(f"     target halves -> {half_text}")
    trimmed = result["trimmed"]
    print(
        f"  Target trimmed ±5%: N={trimmed['n']}, WR={_fmt_wr(trimmed['win_rate'])}, Avg={_fmt_ticks(trimmed['avg_ticks'])}, trim_each_side={trimmed['trim_each_side']}"
    )
    flipped = result["flipped"]
    print(f"  Target flipped direction: N={flipped['n']}, WR={_fmt_wr(flipped['win_rate'])}, Avg={_fmt_ticks(flipped['avg_ticks'])}")
    if result["reasons"]:
        for reason in result["reasons"]:
            print(f"  FAIL reason: {reason}")
    print()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df, meta = load_events()
    telegram = load_telegram_summary()
    report = build_report(df, meta, telegram)
    OUT_JSON.write_text(json.dumps(_serialise(report), indent=2), encoding="utf-8")

    print("ABSORPTION WALK-FORWARD ROBUSTNESS")
    print(f"Events CSV: {EVENTS_CSV}")
    print(f"Telegram JSON: {TELEGRAM_JSON}")
    print(f"Absorption rows analysed: {len(df)}")
    print(
        "Bar-range quartiles (global cutoffs): "
        f"Q1<= {meta['range_cutoffs']['q1']:.2f}, "
        f"Q2<= {meta['range_cutoffs']['q2']:.2f}, "
        f"Q3<= {meta['range_cutoffs']['q3']:.2f}"
    )
    print(
        "Telegram NQ absorption alerts by period: "
        + ", ".join(f"{name}={telegram['period_counts'][name]}" for name in PERIOD_ORDER)
        + f", total={telegram['total_nq_absorption_alerts']}"
    )
    print(f"TYPE_B n strength>=0.20 overlap: {report['inputs']['type_b_strength_overlap']}")
    print()

    for result in report["findings"]:
        if result["kind"] == "single":
            print_single(result)
        else:
            print_comparison(result)

    print(f"Saved JSON summary to: {OUT_JSON}")


if __name__ == "__main__":
    main()
