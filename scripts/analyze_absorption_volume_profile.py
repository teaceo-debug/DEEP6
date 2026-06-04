#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BARS_CSV = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
EVENTS_CSV = ROOT / "data" / "backtests" / "signal_events.csv"
OUT_DIR = ROOT / "data" / "backtests" / "analysis"

TICK_SIZE = 0.25
RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
FORWARD_WINDOWS = (1, 2, 5, 10, 15, 30)


def price_to_tick(price: float) -> int:
    return int(round(float(price) / TICK_SIZE))


def tick_to_price(tick: int) -> float:
    return tick * TICK_SIZE


def ticks_distance(a: pd.Series, b: pd.Series) -> pd.Series:
    return ((a - b).abs() / TICK_SIZE).round(2)


def load_bars() -> pd.DataFrame:
    bars = pd.read_csv(
        BARS_CSV,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
    )
    bars["ts_event"] = pd.to_datetime(bars["ts_event"], utc=True)
    bars["ts_et"] = bars["ts_event"].dt.tz_convert("America/New_York")
    minute = bars["ts_et"].dt.hour * 60 + bars["ts_et"].dt.minute
    bars = bars.loc[(minute >= RTH_START_MINUTE) & (minute < RTH_END_MINUTE)].copy()
    bars["session_date"] = pd.to_datetime(bars["ts_et"].dt.date)
    return bars.sort_values("ts_event").reset_index(drop=True)


def compute_value_area(profile: dict[int, float], poc_tick: int, pct: float = 0.70) -> tuple[float, float]:
    total_vol = sum(profile.values())
    target = total_vol * pct
    ordered = sorted(profile)
    center_idx = ordered.index(poc_tick)
    included = {poc_tick}
    running = profile[poc_tick]
    left = center_idx - 1
    right = center_idx + 1

    while running < target and (left >= 0 or right < len(ordered)):
        left_tick = ordered[left] if left >= 0 else None
        right_tick = ordered[right] if right < len(ordered) else None
        left_vol = profile[left_tick] if left_tick is not None else -1.0
        right_vol = profile[right_tick] if right_tick is not None else -1.0

        if right_vol > left_vol:
            included.add(right_tick)
            running += right_vol
            right += 1
        else:
            included.add(left_tick)
            running += left_vol
            left -= 1

    return tick_to_price(min(included)), tick_to_price(max(included))


def compute_lvns(profile: dict[int, float], strength: int = 2) -> list[float]:
    ordered_ticks = sorted(profile)
    if len(ordered_ticks) < strength * 2 + 1:
        return []

    lvns: list[float] = []
    vols = [profile[tick] for tick in ordered_ticks]
    for idx in range(strength, len(ordered_ticks) - strength):
        center = vols[idx]
        if center <= 0:
            continue
        neighborhood = vols[idx - strength : idx + strength + 1]
        if center < min(neighborhood[:strength] + neighborhood[strength + 1 :]):
            lvns.append(tick_to_price(ordered_ticks[idx]))
    return lvns


def build_session_profiles(bars: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    for session_date, session in bars.groupby("session_date", sort=True):
        profile: dict[int, float] = defaultdict(float)
        total_volume = 0.0
        vwap_num = 0.0

        for row in session.itertuples(index=False):
            volume = float(row.volume)
            if volume <= 0:
                continue

            total_volume += volume
            typical_price = (float(row.high) + float(row.low) + float(row.close)) / 3.0
            vwap_num += typical_price * volume

            lo_tick = price_to_tick(float(row.low))
            hi_tick = price_to_tick(float(row.high))
            tick_count = max(1, hi_tick - lo_tick + 1)
            vol_per_tick = volume / tick_count
            for tick in range(lo_tick, hi_tick + 1):
                profile[tick] += vol_per_tick

        if not profile or total_volume <= 0:
            continue

        session_vwap = vwap_num / total_volume
        max_vol = max(profile.values())
        poc_candidates = [tick for tick, vol in profile.items() if vol == max_vol]
        poc_tick = min(poc_candidates, key=lambda tick: (abs(tick_to_price(tick) - session_vwap), tick))
        val, vah = compute_value_area(profile, poc_tick)
        lvns = compute_lvns(profile)

        rows.append(
            {
                "session_date": session_date,
                "poc": tick_to_price(poc_tick),
                "val": val,
                "vah": vah,
                "vwap": round(session_vwap / TICK_SIZE) * TICK_SIZE,
                "session_low": float(session["low"].min()),
                "session_high": float(session["high"].max()),
                "lvn_count": len(lvns),
                "lvn_prices": "|".join(f"{price:.2f}" for price in lvns),
            }
        )

    prof = pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)
    for level in ("poc", "val", "vah", "vwap", "lvn_prices"):
        prof[f"prior_{level}"] = prof[level].shift(1)
    return prof


def parse_direction(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .map({"1": 1, "-1": -1, "BULLISH": 1, "BEARISH": -1})
        .fillna(0)
        .astype(int)
    )


def load_absorption_events() -> pd.DataFrame:
    usecols = [
        "session_date",
        "bar_ts",
        "signal_id",
        "category",
        "direction",
        "strength",
        "score_tier",
        "bar_open",
        "bar_high",
        "bar_low",
        "bar_close",
        *[f"fwd_close_{w}b" for w in FORWARD_WINDOWS],
    ]
    events = pd.read_csv(EVENTS_CSV, usecols=usecols, low_memory=False)
    events = events.loc[events["category"] == "absorption"].copy()
    events["session_date"] = pd.to_datetime(events["session_date"])
    events["bar_ts"] = pd.to_datetime(events["bar_ts"], utc=True, errors="coerce")
    events["direction_num"] = parse_direction(events["direction"])
    events = events.loc[events["direction_num"] != 0].copy()
    events["signal_price"] = np.where(
        events["direction_num"] > 0,
        events["bar_low"].astype(float),
        events["bar_high"].astype(float),
    )

    for w in FORWARD_WINDOWS:
        move_points = events["direction_num"] * (events[f"fwd_close_{w}b"].astype(float) - events["bar_close"].astype(float))
        events[f"signed_ticks_{w}b"] = move_points / TICK_SIZE
        events[f"win_{w}b"] = move_points > 0

    return events.reset_index(drop=True)


def nearest_lvn_distance(signal_price: float, lvn_prices: str | float | None) -> float:
    if not isinstance(lvn_prices, str) or not lvn_prices:
        return np.nan
    levels = [float(item) for item in lvn_prices.split("|") if item]
    if not levels:
        return np.nan
    return min(abs(signal_price - level) / TICK_SIZE for level in levels)


def add_profile_features(events: pd.DataFrame, profiles: pd.DataFrame, level_ticks: int, prior_level_ticks: int) -> pd.DataFrame:
    merged = events.merge(profiles, on="session_date", how="left", validate="many_to_one")

    for level in ("poc", "vah", "val", "vwap"):
        merged[f"dist_{level}_ticks"] = ticks_distance(merged["signal_price"], merged[level])

    merged["dist_current_value_edge_ticks"] = np.where(
        merged["direction_num"] > 0,
        merged["dist_val_ticks"],
        merged["dist_vah_ticks"],
    )
    merged["dist_prior_value_edge_ticks"] = np.where(
        merged["direction_num"] > 0,
        ticks_distance(merged["signal_price"], merged["prior_val"]),
        ticks_distance(merged["signal_price"], merged["prior_vah"]),
    )
    merged["dist_nearest_lvn_ticks"] = merged.apply(
        lambda row: nearest_lvn_distance(row["signal_price"], row["lvn_prices"]),
        axis=1,
    )
    merged["dist_prior_nearest_lvn_ticks"] = merged.apply(
        lambda row: nearest_lvn_distance(row["signal_price"], row["prior_lvn_prices"]),
        axis=1,
    )

    merged["at_poc"] = merged["dist_poc_ticks"] <= level_ticks
    merged["away_from_poc"] = merged["dist_poc_ticks"] > level_ticks
    merged["at_vwap"] = merged["dist_vwap_ticks"] <= level_ticks
    merged["near_lvn"] = merged["dist_nearest_lvn_ticks"] <= level_ticks
    merged["near_prior_lvn"] = merged["dist_prior_nearest_lvn_ticks"] <= prior_level_ticks

    merged["at_value_edge"] = (
        ((merged["direction_num"] > 0) & (merged["dist_val_ticks"] <= level_ticks))
        | ((merged["direction_num"] < 0) & (merged["dist_vah_ticks"] <= level_ticks))
    )
    merged["beyond_value_area"] = (
        ((merged["direction_num"] > 0) & (merged["signal_price"] < merged["val"]))
        | ((merged["direction_num"] < 0) & (merged["signal_price"] > merged["vah"]))
    )
    merged["combined_value_edge_type_bc"] = merged["at_value_edge"] & merged["score_tier"].isin(["TYPE_B", "TYPE_C"])

    merged["near_prior_poc"] = ticks_distance(merged["signal_price"], merged["prior_poc"]) <= prior_level_ticks
    merged["near_prior_value_edge"] = merged["dist_prior_value_edge_ticks"] <= prior_level_ticks
    merged["near_any_prior_major_level"] = merged[["near_prior_poc", "near_prior_value_edge"]].any(axis=1)
    merged["near_prior_vwap"] = ticks_distance(merged["signal_price"], merged["prior_vwap"]) <= prior_level_ticks

    return merged


def summarize(label: str, frame: pd.DataFrame, window: int) -> dict[str, object]:
    n = len(frame)
    if n == 0:
        return {"label": label, "n": 0, "wr": np.nan, "avg_ticks": np.nan, "median_ticks": np.nan}
    ticks = frame[f"signed_ticks_{window}b"].dropna()
    if ticks.empty:
        return {"label": label, "n": n, "wr": np.nan, "avg_ticks": np.nan, "median_ticks": np.nan}
    return {
        "label": label,
        "n": int(n),
        "wr": float((ticks > 0).mean()),
        "avg_ticks": float(ticks.mean()),
        "median_ticks": float(ticks.median()),
    }


def comparison_rows(events: pd.DataFrame, window: int, level_ticks: int, prior_level_ticks: int) -> list[dict[str, object]]:
    rows = [summarize("All absorption", events, window)]
    rows.extend(
        [
            summarize(f"At POC (≤{level_ticks}t)", events.loc[events["at_poc"]], window),
            summarize(f"Away from POC (>{level_ticks}t)", events.loc[events["away_from_poc"]], window),
            summarize(f"At VAH/VAL edge (≤{level_ticks}t)", events.loc[events["at_value_edge"]], window),
            summarize("Beyond value area", events.loc[events["beyond_value_area"]], window),
            summarize(f"At VWAP (≤{level_ticks}t)", events.loc[events["at_vwap"]], window),
            summarize(f"Near LVN (≤{level_ticks}t)", events.loc[events["near_lvn"]], window),
            summarize("VAH/VAL + TYPE_B/C", events.loc[events["combined_value_edge_type_bc"]], window),
            summarize(f"Near prior POC (≤{prior_level_ticks}t)", events.loc[events["near_prior_poc"]], window),
            summarize(f"Near prior VAH/VAL (≤{prior_level_ticks}t)", events.loc[events["near_prior_value_edge"]], window),
            summarize(f"Near any prior major level (≤{prior_level_ticks}t)", events.loc[events["near_any_prior_major_level"]], window),
            summarize(f"Near prior VWAP (≤{prior_level_ticks}t)", events.loc[events["near_prior_vwap"]], window),
            summarize(f"Near prior LVN (≤{prior_level_ticks}t)", events.loc[events["near_prior_lvn"]], window),
        ]
    )
    return rows


def format_summary(rows: list[dict[str, object]]) -> list[str]:
    lines = []
    header = f"{'Bucket':<34} {'N':>8} {'WR%':>8} {'AvgTicks':>10} {'Median':>10}"
    lines.append(header)
    lines.append("-" * len(header))
    for row in rows:
        if row["n"] == 0:
            lines.append(f"{row['label']:<34} {0:>8} {'-':>8} {'-':>10} {'-':>10}")
            continue
        lines.append(
            f"{row['label']:<34} {int(row['n']):>8,} {float(row['wr']) * 100:>7.2f}%"
            f" {float(row['avg_ticks']):>10.2f} {float(row['median_ticks']):>10.2f}"
        )
    return lines


def write_report(events: pd.DataFrame, rows: list[dict[str, object]], window: int, level_ticks: int, prior_level_ticks: int) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "absorption_volume_profile_report.txt"

    lines: list[str] = []
    lines.append("ABSORPTION @ VOLUME PROFILE LEVELS")
    lines.append("=" * 72)
    lines.append(f"Primary window: {window} bars")
    lines.append(f"Current-session threshold: {level_ticks} ticks | Prior-day threshold: {prior_level_ticks} ticks")
    lines.append("Signal price proxy: bullish=bar low, bearish=bar high")
    lines.append("Session profile method: 1m OHLCV volume distributed evenly across touched 0.25-tick levels")
    lines.append("Current-session profile levels are end-of-session retrospective levels.")
    lines.append("")
    lines.append(f"Absorption events analyzed: {len(events):,}")
    lines.append(f"Sessions with profiles: {events['session_date'].nunique():,}")
    lines.append("")
    lines.extend(format_summary(rows))
    lines.append("")

    signal_rows = []
    for signal_id, grp in events.groupby("signal_id"):
        signal_rows.append(summarize(str(signal_id), grp, window))
    lines.append("Per absorption signal")
    lines.append("-" * 72)
    lines.extend(format_summary(sorted(signal_rows, key=lambda row: row["label"])))
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Test absorption performance near session volume profile levels.")
    parser.add_argument("--window", type=int, default=5, choices=FORWARD_WINDOWS)
    parser.add_argument("--level-ticks", type=int, default=10)
    parser.add_argument("--prior-level-ticks", type=int, default=20)
    args = parser.parse_args()

    print("Loading bars...", flush=True)
    bars = load_bars()
    print(f"  {len(bars):,} RTH bars across {bars['session_date'].nunique():,} sessions", flush=True)

    print("Building session profiles...", flush=True)
    profiles = build_session_profiles(bars)
    print(f"  {len(profiles):,} session profiles built", flush=True)

    print("Loading absorption events...", flush=True)
    events = load_absorption_events()
    print(f"  {len(events):,} absorption events loaded", flush=True)

    print("Joining events to profiles and computing tests...", flush=True)
    enriched = add_profile_features(events, profiles, args.level_ticks, args.prior_level_ticks)
    rows = comparison_rows(enriched, args.window, args.level_ticks, args.prior_level_ticks)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    enriched_path = OUT_DIR / "absorption_volume_profile_events.csv"
    report_path = write_report(enriched, rows, args.window, args.level_ticks, args.prior_level_ticks)
    enriched.to_csv(enriched_path, index=False)

    print("\n" + "\n".join(format_summary(rows)), flush=True)
    print(f"\nSaved report -> {report_path}", flush=True)
    print(f"Saved enriched events -> {enriched_path}", flush=True)


if __name__ == "__main__":
    main()
