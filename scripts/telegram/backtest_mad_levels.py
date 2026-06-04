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
CSV_PRICE_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
PARQUET_PRICE_PATH = ROOT / "data" / "ohlcv" / "NQ_1m_continuous.parquet"
OUTPUT_JSON_PATH = ROOT / "data" / "telegram_levels" / "backtest_results.json"
OUTPUT_TRADES_PATH = ROOT / "data" / "telegram_levels" / "trades.csv"

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
TICK_SIZE = 0.25
APPROACH_TICKS = 5
REVERSAL_TARGET_TICKS = 10
SESSION_MOVE_TICKS = 10
BASELINE_SUCCESS_TICKS = 10
BASELINE_EXIT_BARS = 10
FORWARD_BARS = [1, 2, 5, 10, 15, 30, 60]
REVERSAL_TICK_GRID = [5, 10, 15, 20, 30, 40]
REVERSAL_BAR_GRID = [5, 10, 15, 30, 60]
ENTRY_DELAY_GRID = [0, 1, 2, 3]
STOP_LOSS_GRID = [10, 15, 20, 30, 40]
TAKE_PROFIT_GRID = [10, 15, 20, 30, 40, 60]
MAX_HOLD_BARS = 60
SESSION_APPROACH_COOLDOWN_BARS = 10


@dataclass
class TradeMetrics:
    direction: int
    entry_index: int
    entry_timestamp: pd.Timestamp
    entry_price: float
    exit_index: int
    exit_timestamp: pd.Timestamp
    exit_price: float
    pnl_ticks: float
    mfe_ticks: float
    mae_ticks: float
    outcome: str
    bars_held: int


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_ticks(points: float) -> float:
    return round(points / TICK_SIZE, 2)


def _serialize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, tuple):
        return [_serialize(v) for v in value]
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


def parse_telegram_messages(path: Path) -> pd.DataFrame:
    messages = json.loads(path.read_text(encoding="utf-8"))
    nq_absorption_re = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    es_absorption_re = re.compile(r"^ES absorption at:\s*([\d.]+)$")
    intraday_re = re.compile(r"^NQ Intraday level detected:\s*([\d.]+)$")
    session_header = "NQ Asian and London sessions' intraday swing H/L:"

    parsed: list[dict[str, Any]] = []
    skipped_samples: list[dict[str, Any]] = []

    for message in messages:
        raw_text = (message.get("text") or "").strip()
        if not raw_text:
            continue

        timestamp_utc = pd.Timestamp(message["date"])
        if timestamp_utc.tzinfo is None:
            timestamp_utc = timestamp_utc.tz_localize(UTC)
        else:
            timestamp_utc = timestamp_utc.tz_convert(UTC)

        if match := nq_absorption_re.match(raw_text):
            parsed.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "price": float(match.group(1)),
                    "alert_type": "absorption",
                    "symbol": "NQ",
                    "raw_text": raw_text,
                }
            )
            continue

        if match := es_absorption_re.match(raw_text):
            parsed.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "price": float(match.group(1)),
                    "alert_type": "absorption",
                    "symbol": "ES",
                    "raw_text": raw_text,
                }
            )
            continue

        if match := intraday_re.match(raw_text):
            parsed.append(
                {
                    "timestamp_utc": timestamp_utc,
                    "price": float(match.group(1)),
                    "alert_type": "intraday_level",
                    "symbol": "NQ",
                    "raw_text": raw_text,
                }
            )
            continue

        if raw_text.startswith(session_header):
            body = raw_text[len(session_header) :].replace("|", "\n")
            levels = re.findall(r"\d+(?:\.\d+)?", body)
            for level in levels:
                parsed.append(
                    {
                        "timestamp_utc": timestamp_utc,
                        "price": float(level),
                        "alert_type": "session_level",
                        "symbol": "NQ",
                        "raw_text": raw_text,
                    }
                )
            continue

        if len(skipped_samples) < 20:
            skipped_samples.append({"timestamp_utc": timestamp_utc.isoformat(), "raw_text": raw_text})

    df = pd.DataFrame(parsed).sort_values(["timestamp_utc", "alert_type", "symbol", "price"]).reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_utc"].dt.tz_convert(ET)
    df["trade_date_et"] = df["timestamp_et"].dt.date.astype(str)
    df.attrs["message_count"] = len(messages)
    df.attrs["skipped_samples"] = skipped_samples
    return df


def load_price_data() -> tuple[pd.DataFrame, dict[str, Any]]:
    attempted_sources: list[dict[str, Any]] = []
    chosen_df: pd.DataFrame | None = None
    chosen_meta: dict[str, Any] | None = None

    if PARQUET_PRICE_PATH.exists():
        try:
            parquet_df = pd.read_parquet(PARQUET_PRICE_PATH)
            parquet_meta = {
                "source": str(PARQUET_PRICE_PATH),
                "rows": int(len(parquet_df)),
                "columns": list(parquet_df.columns),
            }
            attempted_sources.append({**parquet_meta, "status": "loaded"})
            if "timestamp" in parquet_df.columns:
                parquet_df = parquet_df.rename(columns={"timestamp": "ts_event"})
            if "ts_event" in parquet_df.columns:
                chosen_df = parquet_df.copy()
                chosen_meta = parquet_meta
        except Exception as exc:  # noqa: BLE001
            attempted_sources.append(
                {
                    "source": str(PARQUET_PRICE_PATH),
                    "status": "failed",
                    "error": str(exc),
                }
            )

    csv_df = pd.read_csv(CSV_PRICE_PATH, parse_dates=["ts_event"])
    csv_meta = {
        "source": str(CSV_PRICE_PATH),
        "rows": int(len(csv_df)),
        "columns": list(csv_df.columns),
    }
    attempted_sources.append({**csv_meta, "status": "loaded"})

    if chosen_df is None or len(csv_df) >= len(chosen_df):
        chosen_df = csv_df.copy()
        chosen_meta = csv_meta

    assert chosen_df is not None
    assert chosen_meta is not None

    df = chosen_df.rename(columns={"ts_event": "timestamp_utc"}).copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    needed = ["timestamp_utc", "open", "high", "low", "close", "volume"]
    missing = [column for column in needed if column not in df.columns]
    if missing:
        raise ValueError(f"Price file missing required columns: {missing}")

    df = df[needed + [c for c in df.columns if c not in needed]].sort_values("timestamp_utc").reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_utc"].dt.tz_convert(ET)
    df["trade_date_et"] = df["timestamp_et"].dt.date.astype(str)
    minutes = df["timestamp_et"].dt.hour * 60 + df["timestamp_et"].dt.minute
    df["is_rth"] = (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)
    df["is_rth_core"] = (minutes >= 9 * 60 + 45) & (minutes < 15 * 60 + 45)
    df["day_of_week"] = df["timestamp_et"].dt.day_name()
    df["time_bucket_30m"] = df["timestamp_et"].dt.floor("30min").dt.strftime("%H:%M")
    return df, {
        "chosen_source": chosen_meta,
        "attempted_sources": attempted_sources,
        "min_timestamp_utc": df["timestamp_utc"].min(),
        "max_timestamp_utc": df["timestamp_utc"].max(),
    }


def _trade_stats_from_pnls(pnls: list[float]) -> dict[str, Any]:
    if not pnls:
        return {
            "trades": 0,
            "win_rate": None,
            "avg_profit_ticks": None,
            "avg_loss_ticks": None,
            "profit_factor": None,
            "expectancy_ticks": None,
            "total_ticks": 0.0,
        }

    pnl_array = np.array(pnls, dtype=float)
    wins = pnl_array[pnl_array > 0]
    losses = pnl_array[pnl_array < 0]
    gross_profit = float(wins.sum())
    gross_loss = float(np.abs(losses.sum()))
    return {
        "trades": int(len(pnl_array)),
        "win_rate": float((pnl_array > 0).mean() * 100.0),
        "avg_profit_ticks": float(wins.mean()) if len(wins) else None,
        "avg_loss_ticks": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else None),
        "expectancy_ticks": float(pnl_array.mean()),
        "total_ticks": float(pnl_array.sum()),
    }


def _simulate_target_stop(
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    future_closes: np.ndarray,
    future_timestamps: np.ndarray,
    entry_price: float,
    direction: int,
    take_profit_ticks: int,
    stop_loss_ticks: int,
) -> TradeMetrics:
    tp_points = take_profit_ticks * TICK_SIZE
    sl_points = stop_loss_ticks * TICK_SIZE
    exit_price = float(future_closes[-1])
    exit_index_offset = len(future_closes) - 1
    outcome = "time_exit"

    favorable_target = entry_price + direction * tp_points
    adverse_stop = entry_price - direction * sl_points

    for idx in range(len(future_closes)):
        high = float(future_highs[idx])
        low = float(future_lows[idx])
        tp_hit = high >= favorable_target if direction == 1 else low <= favorable_target
        sl_hit = low <= adverse_stop if direction == 1 else high >= adverse_stop
        if tp_hit and sl_hit:
            exit_price = adverse_stop
            exit_index_offset = idx
            outcome = "stop_and_target_same_bar_stop_assumed"
            break
        if sl_hit:
            exit_price = adverse_stop
            exit_index_offset = idx
            outcome = "stop_loss"
            break
        if tp_hit:
            exit_price = favorable_target
            exit_index_offset = idx
            outcome = "take_profit"
            break

    favorable_moves = direction * (future_highs - entry_price) if direction == 1 else direction * (future_lows - entry_price)
    adverse_moves = direction * (future_lows - entry_price) if direction == 1 else direction * (future_highs - entry_price)
    mfe_ticks = _round_ticks(float(np.max(favorable_moves)))
    mae_ticks = _round_ticks(float(np.min(adverse_moves)))
    pnl_ticks = _round_ticks(direction * (exit_price - entry_price))

    return TradeMetrics(
        direction=direction,
        entry_index=-1,
        entry_timestamp=pd.Timestamp(future_timestamps[0]),
        entry_price=float(entry_price),
        exit_index=exit_index_offset,
        exit_timestamp=pd.Timestamp(future_timestamps[exit_index_offset]),
        exit_price=float(exit_price),
        pnl_ticks=pnl_ticks,
        mfe_ticks=mfe_ticks,
        mae_ticks=mae_ticks,
        outcome=outcome,
        bars_held=int(exit_index_offset + 1),
    )


def build_absorption_events(levels: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
    alerts = levels[(levels["alert_type"] == "absorption") & (levels["symbol"] == "NQ")].copy()
    bars = price_df.reset_index().rename(columns={"index": "bar_index"})

    alert_idx = pd.merge_asof(
        alerts.sort_values("timestamp_utc"),
        bars[["timestamp_utc", "bar_index", "close", "trade_date_et", "is_rth_core", "timestamp_et", "day_of_week", "time_bucket_30m"]].sort_values("timestamp_utc"),
        on="timestamp_utc",
        direction="forward",
        tolerance=pd.Timedelta("7D"),
    )

    alert_idx = alert_idx.rename(
        columns={
            "bar_index": "entry_bar_index",
            "close": "entry_bar_close",
            "trade_date_et_y": "entry_trade_date_et",
            "is_rth_core": "entry_is_rth_core",
            "timestamp_et_y": "entry_timestamp_et",
            "day_of_week": "entry_day_of_week",
            "time_bucket_30m": "entry_time_bucket_30m",
        }
    )
    if "trade_date_et_x" in alert_idx.columns:
        alert_idx = alert_idx.rename(columns={"trade_date_et_x": "alert_trade_date_et"})
    else:
        alert_idx["alert_trade_date_et"] = alert_idx["trade_date_et"]

    entry_indices = alert_idx["entry_bar_index"].to_numpy(dtype="float64")
    closes = price_df["close"].to_numpy(dtype=float)
    highs = price_df["high"].to_numpy(dtype=float)
    lows = price_df["low"].to_numpy(dtype=float)
    for horizon in FORWARD_BARS:
        returns: list[float | None] = []
        mfe_values: list[float | None] = []
        mae_values: list[float | None] = []
        for entry_idx in entry_indices:
            if np.isnan(entry_idx):
                returns.append(None)
                mfe_values.append(None)
                mae_values.append(None)
                continue

            idx = int(entry_idx)
            if idx == 0 or idx + horizon >= len(price_df):
                returns.append(None)
                mfe_values.append(None)
                mae_values.append(None)
                continue

            entry_price = closes[idx]
            alert_price = float(alert_idx.iloc[len(returns)]["price"])
            prev_close = closes[idx - 1]
            if prev_close == alert_price:
                returns.append(None)
                mfe_values.append(None)
                mae_values.append(None)
                continue

            direction = 1 if prev_close > alert_price else -1
            window_slice = slice(idx, idx + horizon + 1)
            future_highs = highs[window_slice]
            future_lows = lows[window_slice]
            exit_price = closes[idx + horizon]
            directional_return = direction * (exit_price - entry_price)
            favorable = (future_highs - entry_price) if direction == 1 else (entry_price - future_lows)
            adverse = (future_lows - entry_price) if direction == 1 else (entry_price - future_highs)
            returns.append(_round_ticks(float(directional_return)))
            mfe_values.append(_round_ticks(float(np.max(favorable))))
            mae_values.append(_round_ticks(float(np.min(adverse))))

        alert_idx[f"return_{horizon}b_ticks"] = returns
        alert_idx[f"mfe_{horizon}b_ticks"] = mfe_values
        alert_idx[f"mae_{horizon}b_ticks"] = mae_values

    directions: list[str | None] = []
    prior_30m_counts: list[int | None] = []
    for row in alert_idx.itertuples(index=False):
        if pd.isna(row.entry_bar_index) or int(row.entry_bar_index) == 0:
            directions.append(None)
            prior_30m_counts.append(None)
            continue
        idx = int(row.entry_bar_index)
        prev_close = closes[idx - 1]
        if prev_close == row.price:
            directions.append(None)
        else:
            directions.append("long_reversal" if prev_close > row.price else "short_reversal")
        start_ts = row.timestamp_utc - pd.Timedelta(minutes=30)
        same_day = alerts[(alerts["trade_date_et"] == row.alert_trade_date_et) & (alerts["timestamp_utc"] < row.timestamp_utc) & (alerts["timestamp_utc"] >= start_ts)]
        prior_30m_counts.append(int(len(same_day)))

    alert_idx["direction_label"] = directions
    alert_idx["prior_30m_absorptions"] = prior_30m_counts
    alert_idx["in_price_range"] = alert_idx["entry_bar_index"].notna()
    entry_is_rth_core = alert_idx["entry_is_rth_core"].astype("boolean").fillna(False)
    alert_idx["usable_trade"] = alert_idx["in_price_range"] & entry_is_rth_core & alert_idx["direction_label"].notna()
    return alert_idx


def summarize_reversal_matrix(absorption_events: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    usable = absorption_events[absorption_events["usable_trade"]].copy()
    matrix: dict[str, dict[str, Any]] = {}
    best: dict[str, Any] | None = None

    for bars_forward in REVERSAL_BAR_GRID:
        pnls = usable[f"return_{bars_forward}b_ticks"].dropna().astype(float)
        stats = _trade_stats_from_pnls(pnls.tolist())
        matrix[str(bars_forward)] = {"close_exit_stats": stats, "success_by_ticks": {}}
        for target_ticks in REVERSAL_TICK_GRID:
            subset = usable[[f"mfe_{bars_forward}b_ticks", f"return_{bars_forward}b_ticks"]].dropna()
            if subset.empty:
                metric = {
                    "trades": 0,
                    "success_rate": None,
                    "avg_exit_ticks": None,
                    "profit_factor": None,
                    "expectancy_ticks": None,
                }
            else:
                success = subset[f"mfe_{bars_forward}b_ticks"] >= target_ticks
                exit_pnls = subset[f"return_{bars_forward}b_ticks"].astype(float)
                pf_stats = _trade_stats_from_pnls(exit_pnls.tolist())
                metric = {
                    "trades": int(len(subset)),
                    "success_rate": float(success.mean() * 100.0),
                    "avg_exit_ticks": float(exit_pnls.mean()),
                    "profit_factor": pf_stats["profit_factor"],
                    "expectancy_ticks": pf_stats["expectancy_ticks"],
                }
            matrix[str(bars_forward)]["success_by_ticks"][str(target_ticks)] = metric

        baseline = matrix[str(bars_forward)]["success_by_ticks"][str(BASELINE_SUCCESS_TICKS)]
        candidate = {
            "bars_forward": bars_forward,
            "success_rate": baseline["success_rate"],
            "profit_factor": baseline["profit_factor"],
            "expectancy_ticks": baseline["expectancy_ticks"],
            "trades": baseline["trades"],
        }
        if best is None or ((candidate["expectancy_ticks"] or -10**9) > (best["expectancy_ticks"] or -10**9)):
            best = candidate

    assert best is not None
    return matrix, best


def run_session_level_backtest(levels: pd.DataFrame, price_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    session_levels = levels[(levels["alert_type"] == "session_level") & (levels["symbol"] == "NQ")].copy()
    if session_levels.empty:
        return pd.DataFrame(), {"approaches": 0}

    grouped_levels = session_levels.groupby("trade_date_et")["price"].apply(lambda s: sorted({float(x) for x in s})).to_dict()
    grouped_level_times = session_levels.groupby("trade_date_et")["timestamp_utc"].min().to_dict()
    bars = price_df[price_df["is_rth_core"]].copy()

    records: list[dict[str, Any]] = []
    threshold = APPROACH_TICKS * TICK_SIZE
    target_points = SESSION_MOVE_TICKS * TICK_SIZE

    for trade_date, day_bars in bars.groupby("trade_date_et"):
        level_prices = grouped_levels.get(trade_date)
        if not level_prices:
            continue

        day_bars = day_bars.reset_index().rename(columns={"index": "bar_index"})
        highs = day_bars["high"].to_numpy(dtype=float)
        lows = day_bars["low"].to_numpy(dtype=float)
        closes = day_bars["close"].to_numpy(dtype=float)
        timestamps = day_bars["timestamp_utc"].to_numpy()
        buckets = day_bars["time_bucket_30m"].to_numpy()
        days = day_bars["day_of_week"].to_numpy()

        for level_price in level_prices:
            last_approach_idx = -10**9
            for i in range(1, len(day_bars) - 1):
                if i - last_approach_idx <= SESSION_APPROACH_COOLDOWN_BARS:
                    continue

                within = lows[i] <= level_price + threshold and highs[i] >= level_price - threshold
                previous_far = not (lows[i - 1] <= level_price + threshold and highs[i - 1] >= level_price - threshold)
                if not within or not previous_far:
                    continue

                prev_close = closes[i - 1]
                if prev_close == level_price:
                    continue
                direction = 1 if prev_close > level_price else -1
                entry_index = i
                exit_index = min(i + 30, len(day_bars) - 1)
                future_highs = highs[entry_index : exit_index + 1]
                future_lows = lows[entry_index : exit_index + 1]
                future_closes = closes[entry_index : exit_index + 1]
                future_ts = timestamps[entry_index : exit_index + 1]
                trade = _simulate_target_stop(
                    future_highs=future_highs,
                    future_lows=future_lows,
                    future_closes=future_closes,
                    future_timestamps=future_ts,
                    entry_price=closes[entry_index],
                    direction=direction,
                    take_profit_ticks=SESSION_MOVE_TICKS,
                    stop_loss_ticks=SESSION_MOVE_TICKS,
                )
                move_target = level_price + direction * target_points
                break_target = level_price - direction * target_points
                first_hit = "none"
                for j in range(entry_index, exit_index + 1):
                    high = highs[j]
                    low = lows[j]
                    bounce_hit = high >= move_target if direction == 1 else low <= move_target
                    break_hit = low <= break_target if direction == 1 else high >= break_target
                    if bounce_hit and break_hit:
                        first_hit = "break_same_bar_assumed"
                        break
                    if break_hit:
                        first_hit = "break"
                        break
                    if bounce_hit:
                        first_hit = "bounce"
                        break

                favorable = (np.max(future_highs) - closes[entry_index]) if direction == 1 else (closes[entry_index] - np.min(future_lows))
                adverse = (np.min(future_lows) - closes[entry_index]) if direction == 1 else (closes[entry_index] - np.max(future_highs))
                records.append(
                    {
                        "hypothesis": "session_level_sr",
                        "trade_date_et": trade_date,
                        "level_timestamp_utc": grouped_level_times[trade_date],
                        "level_price": level_price,
                        "approach_bar_index": int(day_bars.loc[entry_index, "bar_index"]),
                        "approach_timestamp_utc": pd.Timestamp(timestamps[entry_index]),
                        "entry_price": float(closes[entry_index]),
                        "direction": "support_bounce_long" if direction == 1 else "resistance_bounce_short",
                        "time_bucket_30m": buckets[entry_index],
                        "day_of_week": days[entry_index],
                        "first_hit": first_hit,
                        "bounce_size_ticks": _round_ticks(float(favorable)),
                        "break_size_ticks": _round_ticks(abs(float(adverse))),
                        "trade_pnl_ticks": trade.pnl_ticks,
                        "trade_outcome": trade.outcome,
                    }
                )
                last_approach_idx = i

    approaches = pd.DataFrame(records)
    if approaches.empty:
        return approaches, {"approaches": 0}

    bounce_mask = approaches["first_hit"].eq("bounce")
    break_mask = approaches["first_hit"].isin(["break", "break_same_bar_assumed"])
    summary = {
        "approaches": int(len(approaches)),
        "bounce_rate": float(bounce_mask.mean() * 100.0),
        "break_rate": float(break_mask.mean() * 100.0),
        "avg_bounce_ticks": float(approaches.loc[bounce_mask, "bounce_size_ticks"].mean()) if bounce_mask.any() else None,
        "avg_break_ticks": float(approaches.loc[break_mask, "break_size_ticks"].mean()) if break_mask.any() else None,
        "days_tested": int(approaches["trade_date_et"].nunique()),
    }
    return approaches, summary


def add_session_proximity(absorption_events: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    session_levels = levels[(levels["alert_type"] == "session_level") & (levels["symbol"] == "NQ")].copy()
    grouped = session_levels.groupby("trade_date_et")["price"].apply(list).to_dict()
    nearest_ticks: list[float | None] = []
    near_flags: list[bool | None] = []
    for row in absorption_events.itertuples(index=False):
        prices = grouped.get(row.alert_trade_date_et if hasattr(row, "alert_trade_date_et") else row.trade_date_et)
        if not prices:
            nearest_ticks.append(None)
            near_flags.append(None)
            continue
        distance_points = min(abs(float(row.price) - float(level_price)) for level_price in prices)
        distance_ticks = _round_ticks(distance_points)
        nearest_ticks.append(distance_ticks)
        near_flags.append(distance_ticks <= 10)
    out = absorption_events.copy()
    out["nearest_session_level_distance_ticks"] = nearest_ticks
    out["near_session_level_10t"] = near_flags
    return out


def add_es_confluence(absorption_events: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    es_alerts = levels[(levels["alert_type"] == "absorption") & (levels["symbol"] == "ES")].copy()
    out = absorption_events.copy()
    flags: list[bool] = []
    lead_minutes: list[float | None] = []
    for row in out.itertuples(index=False):
        same_day = es_alerts[es_alerts["trade_date_et"] == row.alert_trade_date_et]
        if same_day.empty:
            flags.append(False)
            lead_minutes.append(None)
            continue
        deltas = (same_day["timestamp_utc"] - row.timestamp_utc).abs() / pd.Timedelta(minutes=1)
        min_delta = float(deltas.min()) if len(deltas) else math.inf
        flags.append(min_delta <= 30)
        lead_minutes.append(min_delta if math.isfinite(min_delta) else None)
    out["es_confluence_30m"] = flags
    out["nearest_es_absorption_minutes"] = lead_minutes
    return out


def summarize_bucket_performance(
    df: pd.DataFrame,
    column: str,
    pnl_column: str,
    title_filter: set[str] | None = None,
    success_column: str | None = None,
) -> list[dict[str, Any]]:
    subset = df[df["usable_trade"]].copy()
    if title_filter is not None:
        subset = subset[subset[column].isin(title_filter)]
    rows: list[dict[str, Any]] = []
    for key, group in subset.groupby(column):
        pnls = group[pnl_column].dropna().astype(float).tolist()
        stats = _trade_stats_from_pnls(pnls)
        if success_column is not None and success_column in group.columns:
            success = group[success_column].dropna().astype(bool)
            stats["win_rate"] = float(success.mean() * 100.0) if len(success) else None
        rows.append({column: key, **stats})
    rows.sort(key=lambda item: ((item["expectancy_ticks"] if item["expectancy_ticks"] is not None else -10**9), item["trades"]), reverse=True)
    return rows


def run_parameter_sweep(absorption_events: pd.DataFrame, price_df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    usable = absorption_events[absorption_events["usable_trade"]].copy()
    closes = price_df["close"].to_numpy(dtype=float)
    highs = price_df["high"].to_numpy(dtype=float)
    lows = price_df["low"].to_numpy(dtype=float)
    timestamps = price_df["timestamp_utc"].to_numpy()

    ranking: list[dict[str, Any]] = []
    trade_records: list[dict[str, Any]] = []
    for entry_delay in ENTRY_DELAY_GRID:
        for stop_loss in STOP_LOSS_GRID:
            for take_profit in TAKE_PROFIT_GRID:
                pnls: list[float] = []
                trades = 0
                for row in usable.itertuples(index=False):
                    base_idx = int(row.entry_bar_index)
                    entry_idx = base_idx + entry_delay
                    if entry_idx <= 0 or entry_idx + MAX_HOLD_BARS >= len(price_df):
                        continue
                    direction = 1 if row.direction_label == "long_reversal" else -1
                    future_slice = slice(entry_idx, entry_idx + MAX_HOLD_BARS + 1)
                    trade = _simulate_target_stop(
                        future_highs=highs[future_slice],
                        future_lows=lows[future_slice],
                        future_closes=closes[future_slice],
                        future_timestamps=timestamps[future_slice],
                        entry_price=float(closes[entry_idx]),
                        direction=direction,
                        take_profit_ticks=take_profit,
                        stop_loss_ticks=stop_loss,
                    )
                    pnls.append(trade.pnl_ticks)
                    trades += 1

                stats = _trade_stats_from_pnls(pnls)
                row_data = {
                    "entry_delay_bars": entry_delay,
                    "stop_loss_ticks": stop_loss,
                    "take_profit_ticks": take_profit,
                    **stats,
                }
                ranking.append(row_data)

    ranking.sort(
        key=lambda item: (
            item["profit_factor"] if item["profit_factor"] not in (None, float("inf")) else (999999.0 if item["profit_factor"] == float("inf") else -999999.0),
            item["expectancy_ticks"] if item["expectancy_ticks"] is not None else -10**9,
            item["trades"],
        ),
        reverse=True,
    )

    top10 = ranking[:10]
    best = top10[0] if top10 else None
    if best is not None:
        entry_delay = int(best["entry_delay_bars"])
        stop_loss = int(best["stop_loss_ticks"])
        take_profit = int(best["take_profit_ticks"])
        for row in usable.itertuples(index=False):
            base_idx = int(row.entry_bar_index)
            entry_idx = base_idx + entry_delay
            if entry_idx <= 0 or entry_idx + MAX_HOLD_BARS >= len(price_df):
                continue
            direction = 1 if row.direction_label == "long_reversal" else -1
            future_slice = slice(entry_idx, entry_idx + MAX_HOLD_BARS + 1)
            trade = _simulate_target_stop(
                future_highs=highs[future_slice],
                future_lows=lows[future_slice],
                future_closes=closes[future_slice],
                future_timestamps=timestamps[future_slice],
                entry_price=float(closes[entry_idx]),
                direction=direction,
                take_profit_ticks=take_profit,
                stop_loss_ticks=stop_loss,
            )
            trade_records.append(
                {
                    "hypothesis": "absorption_param_sweep_best",
                    "alert_timestamp_utc": row.timestamp_utc,
                    "alert_price": row.price,
                    "entry_delay_bars": entry_delay,
                    "stop_loss_ticks": stop_loss,
                    "take_profit_ticks": take_profit,
                    "entry_timestamp_utc": pd.Timestamp(timestamps[entry_idx]),
                    "entry_price": float(closes[entry_idx]),
                    "exit_timestamp_utc": trade.exit_timestamp,
                    "exit_price": trade.exit_price,
                    "direction": row.direction_label,
                    "pnl_ticks": trade.pnl_ticks,
                    "mfe_ticks": trade.mfe_ticks,
                    "mae_ticks": trade.mae_ticks,
                    "outcome": trade.outcome,
                    "bars_held": trade.bars_held,
                }
            )
    return top10, trade_records


def build_baseline_trade_log(absorption_events: pd.DataFrame, session_approaches: pd.DataFrame) -> pd.DataFrame:
    usable = absorption_events[absorption_events["usable_trade"]].copy()
    usable["baseline_success"] = usable[f"mfe_{BASELINE_EXIT_BARS}b_ticks"] >= BASELINE_SUCCESS_TICKS
    baseline = usable[
        [
            "timestamp_utc",
            "price",
            "entry_bar_index",
            "entry_bar_close",
            "direction_label",
            "entry_trade_date_et",
            "entry_day_of_week",
            "entry_time_bucket_30m",
            f"return_{BASELINE_EXIT_BARS}b_ticks",
            f"mfe_{BASELINE_EXIT_BARS}b_ticks",
            f"mae_{BASELINE_EXIT_BARS}b_ticks",
            "baseline_success",
            "prior_30m_absorptions",
            "near_session_level_10t",
            "nearest_session_level_distance_ticks",
            "es_confluence_30m",
            "nearest_es_absorption_minutes",
        ]
    ].copy()
    baseline = baseline.rename(
        columns={
            "timestamp_utc": "alert_timestamp_utc",
            "price": "alert_price",
            "entry_bar_close": "entry_price",
            "entry_trade_date_et": "trade_date_et",
            "entry_day_of_week": "day_of_week",
            "entry_time_bucket_30m": "time_bucket_30m",
            f"return_{BASELINE_EXIT_BARS}b_ticks": "trade_pnl_ticks",
            f"mfe_{BASELINE_EXIT_BARS}b_ticks": "mfe_ticks",
            f"mae_{BASELINE_EXIT_BARS}b_ticks": "mae_ticks",
            "baseline_success": "success_flag",
        }
    )
    baseline.insert(0, "hypothesis", "absorption_baseline")
    if not session_approaches.empty:
        session_csv = session_approaches.copy()
        session_csv = session_csv.rename(columns={"level_price": "alert_price", "approach_timestamp_utc": "alert_timestamp_utc", "entry_price": "entry_price", "trade_pnl_ticks": "trade_pnl_ticks"})
        for col in baseline.columns:
            if col not in session_csv.columns:
                session_csv[col] = None
        session_csv = session_csv[baseline.columns]
        combined = pd.DataFrame(baseline.to_dict("records") + session_csv.to_dict("records"), columns=baseline.columns)
        return combined
    return baseline


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def format_num(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if value == float("inf"):
        return "inf"
    return f"{value:.{digits}f}"


def print_report(results: dict[str, Any]) -> None:
    hypothesis1 = results["hypothesis_1"]
    hypothesis2 = results["hypothesis_2"]
    hypothesis3 = results["hypothesis_3"]
    price = results["price_data"]
    counts = results["counts"]
    print("=" * 40)
    print("MAD LEVELS BACKTEST RESULTS")
    print("=" * 40)
    print(f"Data: {counts['nq_absorption_alerts']} NQ absorptions, {counts['session_level_messages']} session-level messages, {counts['session_level_prices']} session prices")
    print(f"Period: {results['period']['messages_start']} to {results['period']['messages_end']}")
    print(f"Price data: {price['start']} to {price['end']} | source={price['source']}")
    print(f"Overlap with price data: {results['overlap']['trading_days']} trading days")
    print()
    print("HYPOTHESIS 1: Absorption -> Reversal")
    print(f"  Baseline: {BASELINE_SUCCESS_TICKS} ticks target lens, {BASELINE_EXIT_BARS}-bar exit")
    print(f"  Trades: {hypothesis1['baseline_stats']['trades']} | Win Rate: {format_pct(hypothesis1['baseline_stats']['win_rate'])}")
    print(f"  Avg Win: {format_num(hypothesis1['baseline_stats']['avg_profit_ticks'],1)} ticks | Avg Loss: {format_num(hypothesis1['baseline_stats']['avg_loss_ticks'],1)} ticks")
    print(f"  Profit Factor: {format_num(hypothesis1['baseline_stats']['profit_factor'])}")
    print(f"  Expectancy: {format_num(hypothesis1['baseline_stats']['expectancy_ticks'])} ticks/trade")
    print(f"  Best timeframe: {hypothesis1['best_timeframe']['bars_forward']} bars forward")
    print()
    print("  BY TIME OF DAY (best 3):")
    for row in hypothesis1['time_of_day'][:3]:
        print(f"    {row['entry_time_bucket_30m']}: WR={format_pct(row['win_rate'])}, Exp={format_num(row['expectancy_ticks'])}, N={row['trades']}")
    print()
    print("  OPTIMAL PARAMETERS:")
    best_params = hypothesis1['parameter_sweep_top10'][0] if hypothesis1['parameter_sweep_top10'] else None
    if best_params:
        print(f"    Entry delay: {best_params['entry_delay_bars']} bars | SL: {best_params['stop_loss_ticks']} ticks | TP: {best_params['take_profit_ticks']} ticks")
        print(f"    PF: {format_num(best_params['profit_factor'])} | Expectancy: {format_num(best_params['expectancy_ticks'])} | Trades: {best_params['trades']}")
    else:
        print("    No sweep result available")
    print()
    print("HYPOTHESIS 2: Session Levels as S/R")
    print(f"  Approaches: {hypothesis2['summary']['approaches']}")
    print(f"  Bounce Rate: {format_pct(hypothesis2['summary'].get('bounce_rate'))}")
    print(f"  Break Rate: {format_pct(hypothesis2['summary'].get('break_rate'))}")
    print(f"  Avg Bounce: {format_num(hypothesis2['summary'].get('avg_bounce_ticks'))} ticks | Avg Break: {format_num(hypothesis2['summary'].get('avg_break_ticks'))} ticks")
    print()
    print("HYPOTHESIS 3: ES+NQ Confluence")
    print(f"  NQ-only WR: {format_pct(hypothesis3['nq_only']['win_rate'])} ({hypothesis3['nq_only']['trades']} trades)")
    print(f"  ES+NQ WR: {format_pct(hypothesis3['with_es']['win_rate'])} ({hypothesis3['with_es']['trades']} trades)")
    print(f"  Improvement: {format_num(hypothesis3['improvement_win_rate_pct_points'], 1)} pct points")
    print()
    print("ACTIONABLE SETTINGS:")
    if best_params:
        best_absorption = f"{hypothesis1['best_timeframe']['bars_forward']} bars baseline; sweep delay={best_params['entry_delay_bars']}, SL={best_params['stop_loss_ticks']}, TP={best_params['take_profit_ticks']}"
    else:
        best_absorption = f"{hypothesis1['best_timeframe']['bars_forward']} bars baseline"
    print(f"  - Best absorption signal: {best_absorption}")
    print(f"  - Best session level usage: bounce rate {format_pct(hypothesis2['summary'].get('bounce_rate'))} using first touch within {APPROACH_TICKS} ticks")
    improvement = hypothesis3['improvement_win_rate_pct_points']
    es_value = "yes" if improvement is not None and improvement > 0 else "no"
    print(f"  - ES confirmation value: {es_value}, improvement {format_num(improvement, 1)} pct points")
    print("=" * 40)


def main() -> None:
    levels = parse_telegram_messages(RAW_MESSAGES_PATH)
    price_df, price_meta = load_price_data()

    absorption_events = build_absorption_events(levels, price_df)
    absorption_events = add_session_proximity(absorption_events, levels)
    absorption_events = add_es_confluence(absorption_events, levels)

    session_approaches, session_summary = run_session_level_backtest(levels, price_df)
    reversal_matrix, best_timeframe = summarize_reversal_matrix(absorption_events)

    baseline_usable = absorption_events[absorption_events["usable_trade"]].copy()
    baseline_usable["baseline_success"] = baseline_usable[f"mfe_{BASELINE_EXIT_BARS}b_ticks"] >= BASELINE_SUCCESS_TICKS
    baseline_pnls = baseline_usable[f"return_{BASELINE_EXIT_BARS}b_ticks"].dropna().astype(float).tolist()
    baseline_stats = _trade_stats_from_pnls(baseline_pnls)
    baseline_stats["win_rate"] = float(baseline_usable["baseline_success"].dropna().astype(bool).mean() * 100.0) if len(baseline_usable) else None

    time_filter = {"10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"}
    time_of_day = summarize_bucket_performance(baseline_usable, "entry_time_bucket_30m", f"return_{BASELINE_EXIT_BARS}b_ticks", time_filter, success_column="baseline_success")
    day_of_week = summarize_bucket_performance(baseline_usable, "entry_day_of_week", f"return_{BASELINE_EXIT_BARS}b_ticks", success_column="baseline_success")

    freq_bucket_series = pd.cut(
        baseline_usable["prior_30m_absorptions"],
        bins=[-1, 0, 2, 4, 1000],
        labels=["0", "1-2", "3-4", "5+"],
    )
    freq_df = baseline_usable.copy()
    freq_df["frequency_bucket"] = freq_bucket_series.astype(str)
    absorption_frequency = summarize_bucket_performance(freq_df, "frequency_bucket", f"return_{BASELINE_EXIT_BARS}b_ticks", success_column="baseline_success")

    distance_df = baseline_usable.copy()
    distance_df["session_proximity_bucket"] = np.where(distance_df["near_session_level_10t"].astype("boolean").fillna(False), "near_10t", "far_gt_10t")
    session_proximity = summarize_bucket_performance(distance_df, "session_proximity_bucket", f"return_{BASELINE_EXIT_BARS}b_ticks", success_column="baseline_success")

    parameter_sweep_top10, best_sweep_trade_records = run_parameter_sweep(absorption_events, price_df)

    confluence_df = baseline_usable[baseline_usable[f"return_{BASELINE_EXIT_BARS}b_ticks"].notna()].copy()
    nq_only_df = confluence_df[~confluence_df["es_confluence_30m"].astype("boolean").fillna(False)]
    with_es_df = confluence_df[confluence_df["es_confluence_30m"].astype("boolean").fillna(False)]
    nq_only_stats = _trade_stats_from_pnls(nq_only_df[f"return_{BASELINE_EXIT_BARS}b_ticks"].astype(float).tolist())
    with_es_stats = _trade_stats_from_pnls(with_es_df[f"return_{BASELINE_EXIT_BARS}b_ticks"].astype(float).tolist())
    nq_only_stats["win_rate"] = float(nq_only_df["baseline_success"].dropna().astype(bool).mean() * 100.0) if len(nq_only_df) else None
    with_es_stats["win_rate"] = float(with_es_df["baseline_success"].dropna().astype(bool).mean() * 100.0) if len(with_es_df) else None
    improvement = None
    if nq_only_stats["win_rate"] is not None and with_es_stats["win_rate"] is not None:
        improvement = float(with_es_stats["win_rate"] - nq_only_stats["win_rate"])

    trade_log = build_baseline_trade_log(absorption_events, session_approaches)
    if best_sweep_trade_records:
        trade_log = pd.concat([trade_log, pd.DataFrame(best_sweep_trade_records)], ignore_index=True, sort=False)
    trade_log = trade_log.sort_values([col for col in ["alert_timestamp_utc", "hypothesis"] if col in trade_log.columns]).reset_index(drop=True)
    OUTPUT_TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    trade_log.to_csv(OUTPUT_TRADES_PATH, index=False)

    overlap_mask = (levels["timestamp_utc"] >= price_df["timestamp_utc"].min()) & (levels["timestamp_utc"] <= price_df["timestamp_utc"].max())
    overlap_days = price_df.loc[
        (price_df["timestamp_utc"] >= levels.loc[overlap_mask, "timestamp_utc"].min())
        & (price_df["timestamp_utc"] <= levels.loc[overlap_mask, "timestamp_utc"].max()),
        "trade_date_et",
    ].nunique()

    results = {
        "counts": {
            "raw_messages": int(levels.attrs.get("message_count", 0)),
            "nq_absorption_alerts": int(((levels["alert_type"] == "absorption") & (levels["symbol"] == "NQ")).sum()),
            "es_absorption_alerts": int(((levels["alert_type"] == "absorption") & (levels["symbol"] == "ES")).sum()),
            "session_level_messages": int(levels.loc[levels["alert_type"] == "session_level", ["timestamp_utc", "raw_text"]].drop_duplicates().shape[0]),
            "session_level_prices": int((levels["alert_type"] == "session_level").sum()),
            "intraday_levels": int((levels["alert_type"] == "intraday_level").sum()),
            "skipped_samples": levels.attrs.get("skipped_samples", []),
        },
        "period": {
            "messages_start": levels["timestamp_utc"].min(),
            "messages_end": levels["timestamp_utc"].max(),
        },
        "price_data": {
            "source": price_meta["chosen_source"]["source"],
            "rows": price_meta["chosen_source"]["rows"],
            "columns": price_meta["chosen_source"]["columns"],
            "start": price_df["timestamp_utc"].min(),
            "end": price_df["timestamp_utc"].max(),
            "attempted_sources": price_meta["attempted_sources"],
            "timezone_assessment": "Input bars are timezone-aware UTC timestamps; RTH filtering converts to America/New_York via zoneinfo.",
        },
        "overlap": {
            "alerts_in_price_range": int(overlap_mask.sum()),
            "trading_days": int(overlap_days),
        },
        "hypothesis_1": {
            "baseline_success_ticks": BASELINE_SUCCESS_TICKS,
            "baseline_exit_bars": BASELINE_EXIT_BARS,
            "baseline_stats": baseline_stats,
            "reversal_matrix": reversal_matrix,
            "best_timeframe": best_timeframe,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "absorption_frequency": absorption_frequency,
            "session_proximity": session_proximity,
            "parameter_sweep_top10": parameter_sweep_top10,
        },
        "hypothesis_2": {
            "summary": session_summary,
        },
        "hypothesis_3": {
            "nq_only": nq_only_stats,
            "with_es": with_es_stats,
            "improvement_win_rate_pct_points": improvement,
        },
        "notes": [
            "All timestamps are normalized to UTC internally and filtered for core RTH using America/New_York.",
            "Entry uses the first 1-minute bar whose timestamp is >= alert timestamp to avoid look-ahead bias.",
            "If stop loss and take profit are both hit inside one minute bar, stop loss is assumed first for conservatism.",
            "The parquet path was inspected first; if unreadable or not a real parquet file, the CSV source is used.",
        ],
    }

    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(_serialize(results), indent=2), encoding="utf-8")
    print_report(_serialize(results))


if __name__ == "__main__":
    main()
