from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_MESSAGES_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
PRICE_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "backtests" / "analysis" / "telegram_absorption_context.json"
OUTPUT_MD_PATH = ROOT / "data" / "backtests" / "analysis" / "telegram_absorption_context.md"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK_SIZE = 0.25
APPROACH_LOOKBACKS = [5, 10, 30]
FORWARD_HORIZONS = [5, 10, 15, 30, 60]
ROUND_TOL = 1e-9
REPEAT_LEVEL_TOL_POINTS = 0.50
SESSION_CONFLUENCE_TICKS = 20
GAP_EDGE_TICKS = 20
MEANINGFUL_GAP_TICKS = 20


def parse_messages(path: Path) -> pd.DataFrame:
    messages = json.loads(path.read_text(encoding="utf-8"))
    absorption_re = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    session_header = "NQ Asian and London sessions' intraday swing H/L:"

    rows: list[dict[str, Any]] = []
    for message in messages:
        text = (message.get("text") or "").strip()
        if not text:
            continue

        timestamp_utc = pd.Timestamp(message["date"])
        timestamp_utc = timestamp_utc.tz_localize(UTC) if timestamp_utc.tzinfo is None else timestamp_utc.tz_convert(UTC)

        absorption_match = absorption_re.match(text)
        if absorption_match:
            rows.append(
                {
                    "message_id": int(message["message_id"]),
                    "timestamp_utc": timestamp_utc,
                    "timestamp_et": timestamp_utc.tz_convert(ET),
                    "alert_type": "absorption",
                    "price": float(absorption_match.group(1)),
                    "raw_text": text,
                }
            )
            continue

        if text.startswith(session_header):
            levels = re.findall(r"\d+(?:\.\d+)?", text[len(session_header) :].replace("|", "\n"))
            for level in levels:
                rows.append(
                    {
                        "message_id": int(message["message_id"]),
                        "timestamp_utc": timestamp_utc,
                        "timestamp_et": timestamp_utc.tz_convert(ET),
                        "alert_type": "session_level",
                        "price": float(level),
                        "raw_text": text,
                    }
                )

    df = pd.DataFrame(rows).sort_values(["timestamp_utc", "message_id", "alert_type", "price"]).reset_index(drop=True)
    df["trade_date_et"] = df["timestamp_et"].dt.date.astype(str)
    return df


def load_price_data(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path, parse_dates=["ts_event"])
    bars = bars.rename(columns={"ts_event": "timestamp_utc"}).copy()
    bars["timestamp_utc"] = pd.to_datetime(bars["timestamp_utc"], utc=True)
    bars = bars.sort_values("timestamp_utc").reset_index(drop=True)
    bars["bar_index"] = np.arange(len(bars), dtype=int)
    bars["timestamp_et"] = bars["timestamp_utc"].dt.tz_convert(ET)
    bars["trade_date_et"] = bars["timestamp_et"].dt.date.astype(str)
    minutes = bars["timestamp_et"].dt.hour * 60 + bars["timestamp_et"].dt.minute
    bars["is_rth"] = (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)
    return bars


def align_absorptions(levels: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    raw_absorptions = levels[levels["alert_type"] == "absorption"].copy()
    absorptions = raw_absorptions[
        (raw_absorptions["timestamp_utc"] >= bars["timestamp_utc"].min())
        & (raw_absorptions["timestamp_utc"] <= bars["timestamp_utc"].max())
    ].copy()
    aligned = pd.merge_asof(
        absorptions.sort_values("timestamp_utc"),
        bars[["timestamp_utc", "bar_index", "timestamp_et", "trade_date_et", "open", "high", "low", "close", "is_rth"]].sort_values("timestamp_utc"),
        on="timestamp_utc",
        direction="forward",
        tolerance=pd.Timedelta("7D"),
    )
    aligned = aligned.rename(
        columns={
            "timestamp_et_y": "bar_timestamp_et",
            "timestamp_et_x": "alert_timestamp_et",
            "trade_date_et_y": "bar_trade_date_et",
            "trade_date_et_x": "alert_trade_date_et",
            "open": "bar_open",
            "high": "bar_high",
            "low": "bar_low",
            "close": "bar_close",
        }
    )
    aligned["in_price_range"] = aligned["bar_index"].notna()
    aligned.attrs["raw_absorption_alerts_total"] = int(len(raw_absorptions))
    aligned.attrs["absorption_alerts_in_bar_range"] = int(len(absorptions))
    return aligned


def assign_level_clusters(prices: pd.Series, tolerance_points: float) -> dict[float, int]:
    unique_prices = sorted({float(price) for price in prices.dropna().tolist()})
    if not unique_prices:
        return {}

    cluster_map: dict[float, int] = {}
    cluster_id = 0
    cluster_start = unique_prices[0]
    cluster_map[unique_prices[0]] = cluster_id
    for price in unique_prices[1:]:
        if price - cluster_start <= tolerance_points + ROUND_TOL:
            cluster_map[price] = cluster_id
        else:
            cluster_id += 1
            cluster_start = price
            cluster_map[price] = cluster_id
    return cluster_map


def build_analysis_frame(levels: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    events = align_absorptions(levels, bars)
    raw_absorption_alerts_total = int(events.attrs.get("raw_absorption_alerts_total", len(events)))
    absorption_alerts_in_bar_range = int(events.attrs.get("absorption_alerts_in_bar_range", len(events)))
    events = events[events["in_price_range"]].copy().reset_index(drop=True)
    events.attrs["raw_absorption_alerts_total"] = raw_absorption_alerts_total
    events.attrs["absorption_alerts_in_bar_range"] = absorption_alerts_in_bar_range

    closes = bars["close"].to_numpy(dtype=float)
    timestamps = bars["timestamp_utc"].to_numpy()

    bar_indices = events["bar_index"].to_numpy(dtype=int)
    events["entry_price"] = closes[bar_indices]
    events["bar_timestamp_utc"] = pd.to_datetime(timestamps[bar_indices], utc=True)

    for lookback in APPROACH_LOOKBACKS:
        values = np.full(len(events), np.nan, dtype=float)
        valid = bar_indices >= lookback
        values[valid] = (closes[bar_indices[valid]] - closes[bar_indices[valid] - lookback]) / TICK_SIZE
        events[f"approach_{lookback}b_ticks"] = values
        events[f"approach_{lookback}b_side"] = np.where(values > 0, "approaching_from_below", np.where(values < 0, "approaching_from_above", None))
        fade_dir = np.where(values > 0, -1.0, np.where(values < 0, 1.0, np.nan))
        events[f"fade_direction_{lookback}b"] = fade_dir
        for horizon in FORWARD_HORIZONS:
            fwd = np.full(len(events), np.nan, dtype=float)
            valid_h = valid & ((bar_indices + horizon) < len(closes)) & ~np.isnan(fade_dir)
            fwd[valid_h] = fade_dir[valid_h] * (closes[bar_indices[valid_h] + horizon] - closes[bar_indices[valid_h]]) / TICK_SIZE
            events[f"fade_return_{lookback}b_to_{horizon}b_ticks"] = fwd

    mod_100 = np.mod(events["price"].to_numpy(dtype=float), 100.0)
    round_100 = np.isclose(mod_100, 0.0, atol=ROUND_TOL)
    round_50 = np.isclose(mod_100, 50.0, atol=ROUND_TOL)
    events["round_bucket"] = np.where(round_100, "round_100", np.where(round_50, "round_50", "non_round"))
    events["is_any_round"] = round_100 | round_50

    cluster_map = assign_level_clusters(events["price"], REPEAT_LEVEL_TOL_POINTS)
    events["level_cluster"] = events["price"].map(cluster_map).astype(int)

    session_occurrence = (
        events[["level_cluster", "bar_trade_date_et"]]
        .drop_duplicates()
        .sort_values(["level_cluster", "bar_trade_date_et"])
        .assign(session_touch_ordinal=lambda df: df.groupby("level_cluster").cumcount() + 1)
    )
    events = events.merge(session_occurrence, on=["level_cluster", "bar_trade_date_et"], how="left")
    events["repeat_level_bucket"] = np.where(
        events["session_touch_ordinal"] == 1,
        "first_session_touch",
        np.where(events["session_touch_ordinal"] == 2, "second_session_touch", "third_plus_session_touch"),
    )

    events = events.sort_values("timestamp_utc").reset_index(drop=True)
    prior_any_times: list[float | None] = []
    prior_same_times: list[float | None] = []
    prior_same_counts: list[int] = []
    timestamps_ns = events["timestamp_utc"].astype("int64").to_numpy()
    clusters = events["level_cluster"].to_numpy(dtype=int)
    for i in range(len(events)):
        if i == 0:
            prior_any_times.append(None)
            prior_same_times.append(None)
            prior_same_counts.append(0)
            continue
        delta_any = (timestamps_ns[i] - timestamps_ns[i - 1]) / 60_000_000_000
        prior_any_times.append(float(delta_any))

        same_cluster_mask = clusters[:i] == clusters[i]
        if not same_cluster_mask.any():
            prior_same_times.append(None)
            prior_same_counts.append(0)
            continue
        same_idx = np.flatnonzero(same_cluster_mask)
        last_same_idx = int(same_idx[-1])
        delta_same = (timestamps_ns[i] - timestamps_ns[last_same_idx]) / 60_000_000_000
        prior_same_times.append(float(delta_same))
        window_start_ns = timestamps_ns[i] - int(pd.Timedelta(minutes=30).value)
        prior_same_in_window = int(np.sum(same_cluster_mask & (timestamps_ns[:i] >= window_start_ns)))
        prior_same_counts.append(prior_same_in_window)

    events["minutes_since_prior_absorption"] = prior_any_times
    events["minutes_since_prior_same_level"] = prior_same_times
    events["prior_same_level_count_30m"] = prior_same_counts
    events["rapid_absorption_30m"] = events["minutes_since_prior_absorption"].le(30)
    events["same_level_sequence_30m_bucket"] = np.where(
        events["prior_same_level_count_30m"] == 0,
        "first_same_level_30m",
        np.where(events["prior_same_level_count_30m"] == 1, "second_same_level_30m", "third_plus_same_level_30m"),
    )

    premarket_levels = levels[(levels["alert_type"] == "session_level") & (levels["timestamp_et"].dt.hour * 60 + levels["timestamp_et"].dt.minute < 9 * 60 + 30)].copy()
    premarket_by_day = premarket_levels.groupby("trade_date_et")["price"].apply(list).to_dict()
    near_session_flags: list[bool] = []
    near_session_distances: list[float | None] = []
    for row in events.itertuples(index=False):
        day_levels = premarket_by_day.get(row.bar_trade_date_et, [])
        if not day_levels:
            near_session_flags.append(False)
            near_session_distances.append(None)
            continue
        distances = [abs(float(row.price) - float(level)) / TICK_SIZE for level in day_levels]
        nearest = min(distances)
        near_session_flags.append(nearest <= SESSION_CONFLUENCE_TICKS)
        near_session_distances.append(float(nearest))
    events["near_premarket_session_level_20t"] = near_session_flags
    events["nearest_premarket_session_level_ticks"] = near_session_distances

    rth = bars[bars["is_rth"]].copy()
    first_rth = rth.groupby("trade_date_et").first().reset_index()[["trade_date_et", "open"]].rename(columns={"open": "rth_open"})
    last_rth = rth.groupby("trade_date_et").last().reset_index()[["trade_date_et", "close"]].rename(columns={"close": "rth_close"})
    prior_close_map = dict(zip(last_rth["trade_date_et"].shift(1), last_rth["rth_close"].shift(1)))
    gap_rows: list[dict[str, Any]] = []
    for row in first_rth.itertuples(index=False):
        prior_close = prior_close_map.get(row.trade_date_et)
        if prior_close is None or (isinstance(prior_close, float) and math.isnan(prior_close)):
            continue
        gap_rows.append(
            {
                "bar_trade_date_et": row.trade_date_et,
                "rth_open": float(row.rth_open),
                "prior_rth_close": float(prior_close),
                "gap_ticks": float((row.rth_open - prior_close) / TICK_SIZE),
            }
        )
    gap_df = pd.DataFrame(gap_rows, columns=["bar_trade_date_et", "rth_open", "prior_rth_close", "gap_ticks"])
    events = events.merge(gap_df, on="bar_trade_date_et", how="left")
    edge_distances = np.nanmin(
        np.vstack(
            [
                np.abs(events["price"].to_numpy(dtype=float) - events["rth_open"].to_numpy(dtype=float)) / TICK_SIZE,
                np.abs(events["price"].to_numpy(dtype=float) - events["prior_rth_close"].to_numpy(dtype=float)) / TICK_SIZE,
            ]
        ),
        axis=0,
    )
    edge_distances = np.where(np.isfinite(edge_distances), edge_distances, np.nan)
    events["nearest_gap_edge_ticks"] = edge_distances
    events["meaningful_gap_day"] = events["gap_ticks"].abs() >= MEANINGFUL_GAP_TICKS
    events["near_gap_edge_20t"] = events["nearest_gap_edge_ticks"] <= GAP_EDGE_TICKS
    return events


def cohort_stats(df: pd.DataFrame, return_col: str) -> dict[str, Any]:
    series = pd.to_numeric(df[return_col], errors="coerce").dropna()
    n = int(series.shape[0])
    if n == 0:
        return {"n": 0, "win_rate": None, "avg_return_ticks": None, "median_return_ticks": None}
    return {
        "n": n,
        "win_rate": float((series > 0).mean() * 100.0),
        "avg_return_ticks": float(series.mean()),
        "median_return_ticks": float(series.median()),
    }


def summarize_by_horizon(df: pd.DataFrame, prefix_lookback: int) -> dict[str, Any]:
    return {
        str(h): cohort_stats(df, f"fade_return_{prefix_lookback}b_to_{h}b_ticks")
        for h in FORWARD_HORIZONS
    }


def run_analyses(events: pd.DataFrame) -> dict[str, Any]:
    results: dict[str, Any] = {
        "dataset": {
            "raw_absorption_alerts": int(events.attrs.get("raw_absorption_alerts_total", len(events))),
            "absorption_alerts_in_bar_time_range": int(events.attrs.get("absorption_alerts_in_bar_range", len(events))),
            "overlapping_absorption_alerts": int(len(events)),
            "date_start": str(events["timestamp_utc"].min()),
            "date_end": str(events["timestamp_utc"].max()),
            "rth_absorptions": int(events["is_rth"].sum()),
        }
    }

    analysis_1: dict[str, Any] = {}
    for lookback in APPROACH_LOOKBACKS:
        valid = events[pd.to_numeric(events[f"approach_{lookback}b_ticks"], errors="coerce").notna()].copy()
        valid = valid[valid[f"approach_{lookback}b_ticks"] != 0].copy()
        group_summary: dict[str, Any] = {}
        for side, group in valid.groupby(f"approach_{lookback}b_side"):
            group_summary[str(side)] = {
                "n": int(len(group)),
                "avg_approach_ticks": float(group[f"approach_{lookback}b_ticks"].mean()),
                "post_fade_stats": summarize_by_horizon(group, lookback),
            }
        analysis_1[str(lookback)] = group_summary
    results["analysis_1_pre_absorption_price_action"] = analysis_1

    analysis_2: dict[str, Any] = {}
    base = events[pd.to_numeric(events["approach_10b_ticks"], errors="coerce").notna()].copy()
    base = base[base["approach_10b_ticks"] != 0].copy()
    analysis_2["all_absorptions"] = summarize_by_horizon(base, 10)
    analysis_2["by_approach_direction"] = {
        side: summarize_by_horizon(group, 10)
        for side, group in base.groupby("approach_10b_side")
    }
    results["analysis_2_post_absorption_directional_accuracy"] = analysis_2

    analysis_3: dict[str, Any] = {}
    for bucket, group in base.groupby("round_bucket"):
        analysis_3[str(bucket)] = summarize_by_horizon(group, 10)
    analysis_3["any_round_50_or_100"] = summarize_by_horizon(base[base["is_any_round"]], 10)
    analysis_3["non_round"] = summarize_by_horizon(base[~base["is_any_round"]], 10)
    results["analysis_3_round_number_effect"] = analysis_3

    analysis_4: dict[str, Any] = {}
    for bucket, group in base.groupby("repeat_level_bucket"):
        analysis_4[str(bucket)] = summarize_by_horizon(group, 10)
    results["analysis_4_repeat_levels"] = analysis_4

    analysis_5: dict[str, Any] = {
        "rapid_vs_not": {
            "rapid_30m": summarize_by_horizon(base[base["rapid_absorption_30m"]], 10),
            "not_rapid_30m": summarize_by_horizon(base[~base["rapid_absorption_30m"].fillna(False)], 10),
        },
        "same_level_second_confirmation": {},
    }
    for bucket, group in base.groupby("same_level_sequence_30m_bucket"):
        analysis_5["same_level_second_confirmation"][str(bucket)] = summarize_by_horizon(group, 10)
    results["analysis_5_time_between_absorptions"] = analysis_5

    rth_base = base[base["is_rth"]].copy()
    analysis_6 = {
        "near_premarket_session_level_20t": summarize_by_horizon(rth_base[rth_base["near_premarket_session_level_20t"]], 10),
        "not_near_premarket_session_level_20t": summarize_by_horizon(rth_base[~rth_base["near_premarket_session_level_20t"]], 10),
    }
    results["analysis_6_session_level_interaction"] = analysis_6

    gap_base = rth_base[rth_base["meaningful_gap_day"]].copy()
    analysis_7 = {
        "near_gap_edge_20t": summarize_by_horizon(gap_base[gap_base["near_gap_edge_20t"]], 10),
        "far_from_gap_edge": summarize_by_horizon(gap_base[~gap_base["near_gap_edge_20t"].fillna(False)], 10),
    }
    results["analysis_7_gap_edge_interaction"] = analysis_7

    return results


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "na"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    return f"{float(value):.{digits}f}"


def render_markdown(results: dict[str, Any]) -> str:
    lines = [
        "# Telegram NQ Absorption Context Analysis",
        "",
        f"- Overlapping absorption alerts: {results['dataset']['overlapping_absorption_alerts']}",
        f"- RTH absorptions: {results['dataset']['rth_absorptions']}",
        f"- Date range: {results['dataset']['date_start']} → {results['dataset']['date_end']}",
        "",
    ]

    for analysis_name, payload in results.items():
        if analysis_name == "dataset":
            continue
        lines.append(f"## {analysis_name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    levels = parse_messages(RAW_MESSAGES_PATH)
    bars = load_price_data(PRICE_PATH)
    events = build_analysis_frame(levels, bars)
    results = run_analyses(events)

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    OUTPUT_MD_PATH.write_text(render_markdown(results), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
