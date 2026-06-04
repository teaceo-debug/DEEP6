from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_MESSAGES_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
PRICE_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
OUTPUT_JSON_PATH = ROOT / "data" / "telegram_levels" / "active_levels_summary.json"
OUTPUT_TOUCHES_PATH = ROOT / "data" / "telegram_levels" / "active_levels_touches.csv"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK_SIZE = 0.25
TOUCH_TICKS = 5
REACTION_TICKS = 10
CLUSTER_TICKS = 10
TOUCH_DISTANCE = TOUCH_TICKS * TICK_SIZE
REACTION_DISTANCE = REACTION_TICKS * TICK_SIZE
CLUSTER_DISTANCE = CLUSTER_TICKS * TICK_SIZE
SESSION_OPEN_HOUR = 9
SESSION_OPEN_MINUTE = 30
SESSION_CLOSE_HOUR = 16
MIN_SAMPLE = 30

LEVEL_TYPE_LABELS = {
    "absorption": "Absorption",
    "intraday_level": "Intraday",
    "session_level": "Session",
}


@dataclass(frozen=True)
class TouchOutcome:
    outcome: str
    resolve_index: int | None
    resolve_timestamp: pd.Timestamp | None
    bars_to_resolution: int | None


def parse_messages(path: Path) -> pd.DataFrame:
    messages = json.loads(path.read_text(encoding="utf-8"))
    absorption_re = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    intraday_re = re.compile(r"^NQ Intraday level detected:\s*([\d.]+)$")
    session_header = "NQ Asian and London sessions' intraday swing H/L:"

    records: list[dict[str, Any]] = []
    for message in messages:
        raw_text = (message.get("text") or "").strip()
        if not raw_text:
            continue

        timestamp_utc = pd.Timestamp(message["date"])
        if timestamp_utc.tzinfo is None:
            timestamp_utc = timestamp_utc.tz_localize(UTC)
        else:
            timestamp_utc = timestamp_utc.tz_convert(UTC)

        if match := absorption_re.match(raw_text):
            records.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "price": float(match.group(1)),
                    "level_type": "absorption",
                    "message_id": message.get("message_id"),
                    "raw_text": raw_text,
                }
            )
            continue

        if match := intraday_re.match(raw_text):
            records.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "price": float(match.group(1)),
                    "level_type": "intraday_level",
                    "message_id": message.get("message_id"),
                    "raw_text": raw_text,
                }
            )
            continue

        if raw_text.startswith(session_header):
            body = raw_text[len(session_header) :].replace("|", "\n")
            levels = re.findall(r"\d+(?:\.\d+)?", body)
            for level in levels:
                records.append(
                    {
                        "timestamp_utc": timestamp_utc,
                        "price": float(level),
                        "level_type": "session_level",
                        "message_id": message.get("message_id"),
                        "raw_text": raw_text,
                    }
                )

    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("No NQ telegram levels parsed")

    df = df.sort_values(["timestamp_utc", "level_type", "price", "message_id"]).reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_utc"].dt.tz_convert(ET)
    df["trade_date_et"] = df["timestamp_et"].dt.date.astype(str)
    return df


def load_prices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["ts_event"])
    df = df.rename(columns={"ts_event": "timestamp_utc"}).copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    needed = ["timestamp_utc", "open", "high", "low", "close", "volume"]
    missing = [column for column in needed if column not in df.columns]
    if missing:
        raise ValueError(f"Price file missing required columns: {missing}")

    df = df[needed + [c for c in df.columns if c not in needed]].sort_values("timestamp_utc").reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_utc"].dt.tz_convert(ET)
    df["trade_date_et"] = df["timestamp_et"].dt.date.astype(str)
    minutes = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    open_minutes = SESSION_OPEN_HOUR * 60 + SESSION_OPEN_MINUTE
    close_minutes = SESSION_CLOSE_HOUR * 60
    df["is_rth"] = (minutes >= open_minutes) & (minutes < close_minutes)
    return df


def build_session_windows(price_df: pd.DataFrame) -> pd.DataFrame:
    rth_dates = price_df.loc[price_df["is_rth"], "trade_date_et"].drop_duplicates().tolist()
    rows: list[dict[str, Any]] = []
    for trade_date in rth_dates:
        open_et = pd.Timestamp(f"{trade_date} {SESSION_OPEN_HOUR:02d}:{SESSION_OPEN_MINUTE:02d}:00", tz=ET)
        close_et = pd.Timestamp(f"{trade_date} {SESSION_CLOSE_HOUR:02d}:00:00", tz=ET)
        rows.append(
            {
                "trade_date_et": trade_date,
                "session_open_utc": open_et.tz_convert(UTC),
                "session_close_utc": close_et.tz_convert(UTC),
            }
        )
    return pd.DataFrame(rows)


def _resolve_approach_side(session_bars: pd.DataFrame, touch_idx: int, price: float) -> str | None:
    for candidate in range(touch_idx - 1, -1, -1):
        close_price = float(session_bars.iloc[candidate]["close"])
        if close_price > price + TOUCH_DISTANCE:
            return "from_above"
        if close_price < price - TOUCH_DISTANCE:
            return "from_below"
    open_price = float(session_bars.iloc[touch_idx]["open"])
    if open_price > price:
        return "from_above"
    if open_price < price:
        return "from_below"
    return None


def _resolve_touch_outcome(session_bars: pd.DataFrame, touch_idx: int, price: float, side: str) -> TouchOutcome:
    for future_idx in range(touch_idx + 1, len(session_bars)):
        bar = session_bars.iloc[future_idx]
        if side == "from_above":
            bounce_hit = float(bar["high"]) >= price + REACTION_DISTANCE
            break_hit = float(bar["low"]) <= price - REACTION_DISTANCE
        else:
            bounce_hit = float(bar["low"]) <= price - REACTION_DISTANCE
            break_hit = float(bar["high"]) >= price + REACTION_DISTANCE

        if bounce_hit and break_hit:
            close_price = float(bar["close"])
            outcome = "bounce" if ((side == "from_above" and close_price >= price) or (side == "from_below" and close_price <= price)) else "break"
            return TouchOutcome(
                outcome=outcome,
                resolve_index=future_idx,
                resolve_timestamp=bar["timestamp_utc"],
                bars_to_resolution=future_idx - touch_idx,
            )
        if bounce_hit:
            return TouchOutcome(
                outcome="bounce",
                resolve_index=future_idx,
                resolve_timestamp=bar["timestamp_utc"],
                bars_to_resolution=future_idx - touch_idx,
            )
        if break_hit:
            return TouchOutcome(
                outcome="break",
                resolve_index=future_idx,
                resolve_timestamp=bar["timestamp_utc"],
                bars_to_resolution=future_idx - touch_idx,
            )

    return TouchOutcome(outcome="unresolved", resolve_index=None, resolve_timestamp=None, bars_to_resolution=None)


def _bucket_test_number(test_number: int) -> str:
    if test_number <= 1:
        return "1"
    if test_number == 2:
        return "2"
    return "3+"


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100, 2)


def _round_price(price: float) -> float:
    return round(price / TICK_SIZE) * TICK_SIZE


def build_active_level_touches(levels_df: pd.DataFrame, price_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sessions = build_session_windows(price_df)
    touch_rows: list[dict[str, Any]] = []
    active_level_rows: list[dict[str, Any]] = []

    for session in sessions.itertuples(index=False):
        active_mask = (levels_df["timestamp_utc"] >= session.session_open_utc - pd.Timedelta(hours=24)) & (
            levels_df["timestamp_utc"] < session.session_open_utc
        )
        active_raw = levels_df.loc[active_mask].copy()
        if active_raw.empty:
            continue

        active = (
            active_raw.groupby(["price", "level_type"], as_index=False)
            .agg(
                first_seen_utc=("timestamp_utc", "min"),
                last_seen_utc=("timestamp_utc", "max"),
                message_count=("message_id", "count"),
            )
            .sort_values(["price", "level_type"])
            .reset_index(drop=True)
        )

        price_array = active["price"].to_numpy(dtype=float)
        type_array = active["level_type"].tolist()
        session_bars = price_df.loc[
            (price_df["timestamp_utc"] >= session.session_open_utc) & (price_df["timestamp_utc"] < session.session_close_utc)
        ].reset_index(drop=True)
        if session_bars.empty:
            continue

        for idx, row in active.iterrows():
            cluster_mask = np.abs(price_array - float(row["price"])) <= CLUSTER_DISTANCE
            cluster_types = sorted(set(np.array(type_array, dtype=object)[cluster_mask].tolist()))
            has_absorption_cluster = "absorption" in cluster_types
            combo_key = "+".join(cluster_types)
            active_level_rows.append(
                {
                    "trade_date_et": session.trade_date_et,
                    "price": float(row["price"]),
                    "level_type": row["level_type"],
                    "message_count": int(row["message_count"]),
                    "cluster_type_count": len(cluster_types),
                    "cluster_types": combo_key,
                    "cluster_level_count": int(cluster_mask.sum()),
                    "has_absorption_cluster": has_absorption_cluster,
                }
            )

            in_touch_zone = (
                (session_bars["low"] <= float(row["price"]) + TOUCH_DISTANCE)
                & (session_bars["high"] >= float(row["price"]) - TOUCH_DISTANCE)
            ).to_numpy()
            touch_indices = np.flatnonzero(in_touch_zone & np.r_[True, ~in_touch_zone[:-1]])
            prior_bounced = False
            for touch_order, touch_idx in enumerate(touch_indices, start=1):
                side = _resolve_approach_side(session_bars, int(touch_idx), float(row["price"]))
                if side is None:
                    continue
                outcome = _resolve_touch_outcome(session_bars, int(touch_idx), float(row["price"]), side)
                touch_rows.append(
                    {
                        "trade_date_et": session.trade_date_et,
                        "level_price": float(row["price"]),
                        "level_type": row["level_type"],
                        "touch_index_in_session": touch_order,
                        "touch_timestamp_utc": session_bars.iloc[int(touch_idx)]["timestamp_utc"],
                        "touch_timestamp_et": session_bars.iloc[int(touch_idx)]["timestamp_et"],
                        "approach_side": side,
                        "outcome": outcome.outcome,
                        "resolve_timestamp_utc": outcome.resolve_timestamp,
                        "bars_to_resolution": outcome.bars_to_resolution,
                        "message_count": int(row["message_count"]),
                        "cluster_type_count": len(cluster_types),
                        "cluster_types": combo_key,
                        "cluster_level_count": int(cluster_mask.sum()),
                        "has_absorption_cluster": has_absorption_cluster,
                        "second_touch_after_bounce": prior_bounced and touch_order == 2,
                        "test_number_bucket": _bucket_test_number(touch_order),
                    }
                )
                prior_bounced = outcome.outcome == "bounce"

    return pd.DataFrame(active_level_rows), pd.DataFrame(touch_rows)


def summarize_type_counts(levels_df: pd.DataFrame) -> dict[str, Any]:
    messages_by_type = levels_df.groupby("level_type").size().to_dict()
    unique_messages = levels_df.groupby(["level_type", "message_id"]).ngroups
    session_message_count = levels_df.loc[levels_df["level_type"] == "session_level", "message_id"].nunique()
    coverage_by_type = (
        levels_df.groupby("level_type")
        .agg(first_timestamp_utc=("timestamp_utc", "min"), last_timestamp_utc=("timestamp_utc", "max"), rows=("price", "size"))
        .reset_index()
        .to_dict("records")
    )
    return {
        "parsed_rows": int(len(levels_df)),
        "alerts_by_type": {k: int(v) for k, v in messages_by_type.items()},
        "session_messages": int(session_message_count),
        "unique_type_message_pairs": int(unique_messages),
        "coverage_by_type": coverage_by_type,
    }


def summarize_touch_subset(df: pd.DataFrame, group_col: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, subset in df.groupby(group_col):
        resolved = subset[subset["outcome"].isin(["bounce", "break"])]
        n = int(len(resolved))
        if n < MIN_SAMPLE:
            continue
        bounce_n = int((resolved["outcome"] == "bounce").sum())
        rows.append(
            {
                group_col: key,
                "n": n,
                "bounce_n": bounce_n,
                "break_n": int((resolved["outcome"] == "break").sum()),
                "bounce_rate": _pct(_safe_rate(bounce_n, n)),
            }
        )
    return sorted(rows, key=lambda row: (-row["bounce_rate"], -row["n"]))


def summarize_touch_subset_with_expected(df: pd.DataFrame, group_col: str, expected_keys: list[Any]) -> list[dict[str, Any]]:
    rows_by_key = {row[group_col]: row for row in summarize_touch_subset(df, group_col)}
    ordered: list[dict[str, Any]] = []
    for key in expected_keys:
        ordered.append(
            rows_by_key.get(
                key,
                {
                    group_col: key,
                    "n": 0,
                    "bounce_n": 0,
                    "break_n": 0,
                    "bounce_rate": None,
                },
            )
        )
    return ordered


def build_strength_table(touches_df: pd.DataFrame) -> pd.DataFrame:
    resolved = touches_df[touches_df["outcome"].isin(["bounce", "break"])].copy()
    if resolved.empty:
        return resolved

    baseline = float((resolved["outcome"] == "bounce").mean())
    type_count_uplift = (
        resolved.groupby("cluster_type_count")["outcome"].apply(lambda s: (s == "bounce").mean() - baseline).to_dict()
    )
    absorption_uplift = (
        resolved.groupby("has_absorption_cluster")["outcome"].apply(lambda s: (s == "bounce").mean() - baseline).to_dict()
    )
    test_uplift = (
        resolved.groupby("test_number_bucket")["outcome"].apply(lambda s: (s == "bounce").mean() - baseline).to_dict()
    )

    resolved["strength_score"] = resolved.apply(
        lambda row: max(
            0.0,
            min(
                100.0,
                50.0
                + 100.0 * type_count_uplift.get(row["cluster_type_count"], 0.0)
                + 100.0 * absorption_uplift.get(row["has_absorption_cluster"], 0.0)
                + 100.0 * test_uplift.get(row["test_number_bucket"], 0.0),
            ),
        ),
        axis=1,
    )
    return resolved


def build_summary(levels_df: pd.DataFrame, active_levels_df: pd.DataFrame, touches_df: pd.DataFrame, strength_df: pd.DataFrame) -> dict[str, Any]:
    resolved = touches_df[touches_df["outcome"].isin(["bounce", "break"])].copy()
    first_touch = resolved[resolved["touch_index_in_session"] == 1]
    clustered = resolved[resolved["cluster_type_count"] >= 2]
    second_touch_after_bounce = resolved[resolved["second_touch_after_bounce"]]

    combo_rows: list[dict[str, Any]] = []
    if not resolved.empty:
        combo_summary = (
            resolved.groupby(["cluster_types", "cluster_type_count", "has_absorption_cluster", "test_number_bucket"])
            .agg(n=("outcome", "size"), bounce_n=("outcome", lambda s: int((s == "bounce").sum())))
            .reset_index()
        )
        combo_summary = combo_summary[combo_summary["n"] >= MIN_SAMPLE].copy()
        combo_summary["bounce_rate"] = (combo_summary["bounce_n"] / combo_summary["n"] * 100).round(2)
        combo_rows = combo_summary.sort_values(["bounce_rate", "n"], ascending=[False, False]).to_dict("records")

    top_strength_rows: list[dict[str, Any]] = []
    if not strength_df.empty:
        quantile_buckets = pd.qcut(
            strength_df["strength_score"],
            q=min(5, strength_df["strength_score"].nunique()),
            duplicates="drop",
        )
        score_summary = (
            strength_df.assign(score_bucket=quantile_buckets.astype(str))
            .groupby("score_bucket", observed=False)
            .agg(n=("outcome", "size"), bounce_n=("outcome", lambda s: int((s == "bounce").sum())))
            .reset_index()
        )
        score_summary = score_summary[score_summary["n"] >= MIN_SAMPLE].copy()
        score_summary["bounce_rate"] = (score_summary["bounce_n"] / score_summary["n"] * 100).round(2)
        top_strength_rows = score_summary.sort_values("score_bucket").to_dict("records")

    return {
        "data_summary": summarize_type_counts(levels_df),
        "active_level_days": int(active_levels_df["trade_date_et"].nunique()) if not active_levels_df.empty else 0,
        "active_level_rows": int(len(active_levels_df)),
        "touch_rows": int(len(touches_df)),
        "resolved_touch_rows": int(len(resolved)),
        "unresolved_touch_rows": int((touches_df["outcome"] == "unresolved").sum()) if not touches_df.empty else 0,
        "type_reactivity": summarize_touch_subset_with_expected(
            resolved,
            "level_type",
            ["absorption", "intraday_level", "session_level"],
        ),
        "cluster_reactivity": summarize_touch_subset(resolved, "cluster_type_count"),
        "touch_number_reactivity": summarize_touch_subset(resolved, "test_number_bucket"),
        "first_touch_reactivity": summarize_touch_subset_with_expected(
            first_touch,
            "level_type",
            ["absorption", "intraday_level", "session_level"],
        ),
        "clustered_vs_nonclustered": [
            {
                "group": "clustered_2plus_types",
                "n": int(len(clustered)),
                "bounce_rate": _pct(_safe_rate(int((clustered["outcome"] == "bounce").sum()), int(len(clustered)))),
            },
            {
                "group": "single_type",
                "n": int(len(resolved[resolved["cluster_type_count"] == 1])),
                "bounce_rate": _pct(
                    _safe_rate(
                        int((resolved.loc[resolved["cluster_type_count"] == 1, "outcome"] == "bounce").sum()),
                        int((resolved["cluster_type_count"] == 1).sum()),
                    )
                ),
            },
        ],
        "second_touch_after_bounce": {
            "n": int(len(second_touch_after_bounce)),
            "bounce_rate": _pct(
                _safe_rate(
                    int((second_touch_after_bounce["outcome"] == "bounce").sum()),
                    int(len(second_touch_after_bounce)),
                )
            ),
            "by_type": summarize_touch_subset(second_touch_after_bounce, "level_type"),
        },
        "best_combinations_n_ge_30": combo_rows[:15],
        "strength_score_buckets": top_strength_rows,
    }


def serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    if isinstance(value, tuple):
        return [serialize(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        val = float(value)
        return None if math.isnan(val) or math.isinf(val) else val
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if pd.isna(value):
        return None
    return value


def main() -> None:
    levels_df = parse_messages(RAW_MESSAGES_PATH)
    price_df = load_prices(PRICE_PATH)
    active_levels_df, touches_df = build_active_level_touches(levels_df, price_df)
    if touches_df.empty:
        raise ValueError("No active-level touches found")

    touches_df["level_type_label"] = touches_df["level_type"].map(LEVEL_TYPE_LABELS)
    touches_df["rounded_level_price"] = touches_df["level_price"].map(_round_price)
    strength_df = build_strength_table(touches_df)
    summary = build_summary(levels_df, active_levels_df, touches_df, strength_df)

    export_touches = touches_df.copy()
    if not strength_df.empty:
        export_touches = export_touches.merge(
            strength_df[
                [
                    "trade_date_et",
                    "level_price",
                    "level_type",
                    "touch_timestamp_utc",
                    "strength_score",
                ]
            ],
            on=["trade_date_et", "level_price", "level_type", "touch_timestamp_utc"],
            how="left",
        )

    OUTPUT_JSON_PATH.write_text(json.dumps(serialize(summary), indent=2), encoding="utf-8")
    export_touches.to_csv(OUTPUT_TOUCHES_PATH, index=False)

    print(json.dumps(serialize(summary), indent=2))
    print(f"\nWrote {OUTPUT_JSON_PATH}")
    print(f"Wrote {OUTPUT_TOUCHES_PATH}")


if __name__ == "__main__":
    main()
