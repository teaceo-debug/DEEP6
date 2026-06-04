"""Backtest five final composite NQ absorption strategies.

Data inputs:
- data/backtests/signal_events.csv
- data/telegram_levels/raw_nq.json
- data/backtests/nq_1yr_1m.csv

Core assumptions:
- Entry is next bar open after the qualifying absorption signal bar.
- One open position at a time per strategy (no pyramiding / overlapping trades).
- Fixed-stop/target strategies use conservative same-bar resolution: stop first when
  both stop and target are touched within the same 1-minute bar.
- Strategy 2 uses an initial 20-tick stop because the prompt defines only the
  trailing mechanics and 20 ticks is the trail distance.
- Telegram confirmation compares alert price to the absorption bar extreme:
  bullish absorption uses signal-bar low, bearish absorption uses signal-bar high.
- P&L is reported in gross ticks / dollars (no commissions or slippage deducted).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SIGNALS_PATH = ROOT / "data" / "backtests" / "signal_events.csv"
TELEGRAM_PATH = ROOT / "data" / "telegram_levels" / "raw_nq.json"
BARS_PATH = ROOT / "data" / "backtests" / "nq_1yr_1m.csv"
OUTPUT_JSON = ROOT / "data" / "backtests" / "final_composite_strategy_results.json"
OUTPUT_TRADES = ROOT / "data" / "backtests" / "final_composite_strategy_trades.csv"

ET = "America/New_York"
TICK_SIZE = 0.25
TICK_VALUE = 5.0
TELEGRAM_WINDOW = pd.Timedelta(minutes=30)
TELEGRAM_PRICE_WINDOW = 20 * TICK_SIZE
BAR_RANGE_LIMIT_TICKS = 80


@dataclass
class Trade:
    strategy: str
    signal_ts: str
    entry_ts: str
    exit_ts: str
    signal_bar_idx: int
    entry_bar_idx: int
    exit_bar_idx: int
    direction: int
    entry_price: float
    exit_price: float
    pnl_ticks: float
    pnl_dollars: float
    bars_held: int
    exit_reason: str
    abs_strength: float
    score_tier: str
    score_final: float


def tier_rank(tier: str) -> int:
    return {"QUIET": 0, "TYPE_C": 1, "TYPE_B": 2, "TYPE_A": 3}.get(str(tier), -1)


def direction_label(direction: int) -> str:
    return "LONG" if direction > 0 else "SHORT"


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    if pd.isna(value):
        return None
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def load_bars() -> pd.DataFrame:
    bars = pd.read_csv(BARS_PATH, parse_dates=["ts_event"])
    bars = bars.rename(columns={"ts_event": "timestamp_utc"}).copy()
    bars["timestamp_utc"] = pd.to_datetime(bars["timestamp_utc"], utc=True)
    bars = bars.sort_values("timestamp_utc").reset_index(drop=True)
    bars["bar_idx"] = np.arange(len(bars), dtype=int)
    bars["timestamp_et"] = bars["timestamp_utc"].dt.tz_convert(ET)
    bars["date_et"] = bars["timestamp_et"].dt.date.astype(str)
    bars["month_et"] = bars["timestamp_et"].dt.strftime("%Y-%m")
    bars["time_hm"] = bars["timestamp_et"].dt.strftime("%H:%M")
    return bars


def load_signals() -> pd.DataFrame:
    usecols = [
        "bar_ts",
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
    ]
    signals = pd.read_csv(SIGNALS_PATH, usecols=usecols)
    signals["bar_ts"] = pd.to_datetime(signals["bar_ts"], utc=True)
    signals["direction"] = pd.to_numeric(signals["direction"], errors="coerce").fillna(0).astype(int)
    signals["strength"] = pd.to_numeric(signals["strength"], errors="coerce")
    signals["score_final"] = pd.to_numeric(signals["score_final"], errors="coerce")
    signals = signals.sort_values(["bar_ts", "category", "strength"], ascending=[True, True, False]).reset_index(drop=True)
    return signals


def load_telegram_absorptions() -> pd.DataFrame:
    messages = json.loads(TELEGRAM_PATH.read_text(encoding="utf-8"))
    pattern = re.compile(r"^NQ absorption at:\s*([\d.]+)$")
    rows: list[dict[str, Any]] = []
    for message in messages:
        raw = (message.get("text") or "").strip()
        match = pattern.match(raw)
        if not match:
            continue
        rows.append(
            {
                "timestamp_utc": pd.Timestamp(message["date"]).tz_convert("UTC")
                if pd.Timestamp(message["date"]).tzinfo is not None
                else pd.Timestamp(message["date"]).tz_localize("UTC"),
                "price": float(match.group(1)),
            }
        )
    alerts = pd.DataFrame(rows)
    if alerts.empty:
        return alerts
    alerts = alerts.drop_duplicates(["timestamp_utc", "price"]).sort_values("timestamp_utc").reset_index(drop=True)
    return alerts


def build_bar_feature_frame(bars: pd.DataFrame, signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    presence = (
        signals.assign(pos=signals["direction"].eq(1), neg=signals["direction"].eq(-1))
        .groupby(["bar_ts", "category"])[["pos", "neg"]]
        .max()
        .unstack("category", fill_value=False)
    )
    presence.columns = [f"{cat}_{side}" for side, cat in presence.columns]
    presence = presence.reset_index().rename(columns={"bar_ts": "timestamp_utc"})

    bars_full = bars.merge(presence, on="timestamp_utc", how="left")
    bool_cols = [c for c in bars_full.columns if c.endswith("_pos") or c.endswith("_neg")]
    for col in bool_cols:
        bars_full[col] = bars_full[col].where(bars_full[col].notna(), False).astype(bool)

    for cat in ("exhaustion", "trapped"):
        for suffix in ("pos", "neg"):
            base = f"{cat}_{suffix}"
            recent = f"{cat}_recent_{suffix}"
            bars_full[recent] = bars_full[base].astype(int).rolling(window=6, min_periods=1).max().astype(bool)

    abs_rows = signals.loc[signals["category"].eq("absorption")].copy()
    abs_rows["tier_value"] = abs_rows["score_tier"].map(tier_rank)
    abs_rows = abs_rows.sort_values(
        ["bar_ts", "tier_value", "strength", "score_final", "signal_id"],
        ascending=[True, False, False, False, True],
    )
    abs_rows = abs_rows.drop_duplicates("bar_ts", keep="first")
    abs_rows = abs_rows.rename(
        columns={
            "bar_ts": "timestamp_utc",
            "direction": "abs_direction",
            "strength": "abs_strength",
            "score_tier": "abs_score_tier",
            "score_final": "abs_score_final",
            "signal_id": "abs_signal_id",
        }
    )

    abs_events = abs_rows.merge(
        bars_full[
            [
                "timestamp_utc",
                "bar_idx",
                "timestamp_et",
                "date_et",
                "month_et",
                "time_hm",
                "exhaustion_pos",
                "exhaustion_neg",
                "trapped_pos",
                "trapped_neg",
                "delta_pos",
                "delta_neg",
                "exhaustion_recent_pos",
                "exhaustion_recent_neg",
                "trapped_recent_pos",
                "trapped_recent_neg",
            ]
        ],
        on="timestamp_utc",
        how="inner",
    )

    abs_events["bar_range_ticks"] = (abs_events["bar_high"] - abs_events["bar_low"]) / TICK_SIZE
    abs_events["tier_value"] = abs_events["abs_score_tier"].map(tier_rank)
    return bars_full, abs_events.sort_values("bar_idx").reset_index(drop=True)


def add_telegram_filter(abs_events: pd.DataFrame, alerts: pd.DataFrame) -> pd.DataFrame:
    abs_events = abs_events.copy()
    if alerts.empty:
        abs_events["telegram_confirmed"] = False
        return abs_events

    alert_times = alerts["timestamp_utc"].astype("int64").to_numpy()
    alert_prices = alerts["price"].to_numpy(dtype=float)
    window_ns = int(TELEGRAM_WINDOW.value)

    confirmed: list[bool] = []
    for row in abs_events.itertuples(index=False):
        signal_ns = int(row.timestamp_utc.value)
        start_ns = signal_ns - window_ns
        lo = int(np.searchsorted(alert_times, start_ns, side="left"))
        hi = int(np.searchsorted(alert_times, signal_ns, side="right"))
        if lo >= hi:
            confirmed.append(False)
            continue
        reference_price = row.bar_low if row.abs_direction > 0 else row.bar_high
        price_slice = alert_prices[lo:hi]
        confirmed.append(bool(np.any(np.abs(price_slice - reference_price) <= TELEGRAM_PRICE_WINDOW)))

    abs_events["telegram_confirmed"] = confirmed
    return abs_events


def qualifies_same_direction(row: pd.Series, category: str) -> bool:
    if row["abs_direction"] > 0:
        return bool(row[f"{category}_pos"] and not row[f"{category}_neg"])
    return bool(row[f"{category}_neg"] and not row[f"{category}_pos"])


def qualifies_recent_same_direction(row: pd.Series) -> bool:
    if row["abs_direction"] > 0:
        return bool(row["exhaustion_recent_pos"] or row["trapped_recent_pos"])
    return bool(row["exhaustion_recent_neg"] or row["trapped_recent_neg"])


def strategy_filters(abs_events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    events = abs_events.copy()
    events["is_lunch_block"] = events["time_hm"].ge("13:00") & events["time_hm"].lt("13:30")
    events["same_bar_confirm_categories"] = events.apply(
        lambda row: sum(qualifies_same_direction(row, cat) for cat in ("exhaustion", "trapped", "delta")),
        axis=1,
    )
    events["recent_exh_or_trap_same_dir"] = events.apply(qualifies_recent_same_direction, axis=1)

    filters = {
        "Strategy 1: Pure Absorption": events.loc[
            events["abs_score_tier"].ne("QUIET") & events["abs_strength"].ge(0.02)
        ].copy(),
        "Strategy 2: High-Quality Absorption": events.loc[
            events["tier_value"].ge(tier_rank("TYPE_B")) | events["abs_strength"].ge(0.20)
        ].copy(),
        "Strategy 3: Telegram-Confirmed Absorption": events.loc[
            events["telegram_confirmed"]
        ].copy(),
        "Strategy 4: Multi-Signal Confluence": events.loc[
            events["same_bar_confirm_categories"].ge(2)
        ].copy(),
        "Strategy 5: Kitchen Sink": events.loc[
            events["abs_score_tier"].isin(["TYPE_A", "TYPE_B", "TYPE_C"])
            & events["abs_strength"].ge(0.05)
            & events["bar_range_ticks"].lt(BAR_RANGE_LIMIT_TICKS)
            & ~events["is_lunch_block"]
            & events["recent_exh_or_trap_same_dir"]
        ].copy(),
    }
    return filters


def pnl_ticks(direction: int, entry_price: float, exit_price: float) -> float:
    return direction * (exit_price - entry_price) / TICK_SIZE


def make_trade(
    strategy: str,
    row: pd.Series,
    entry_bar: pd.Series,
    exit_bar: pd.Series,
    exit_price: float,
    exit_reason: str,
) -> Trade:
    ticks = pnl_ticks(int(row["abs_direction"]), float(entry_bar["open"]), float(exit_price))
    return Trade(
        strategy=strategy,
        signal_ts=str(row["timestamp_utc"]),
        entry_ts=str(entry_bar["timestamp_utc"]),
        exit_ts=str(exit_bar["timestamp_utc"]),
        signal_bar_idx=int(row["bar_idx"]),
        entry_bar_idx=int(entry_bar["bar_idx"]),
        exit_bar_idx=int(exit_bar["bar_idx"]),
        direction=int(row["abs_direction"]),
        entry_price=float(entry_bar["open"]),
        exit_price=float(exit_price),
        pnl_ticks=float(ticks),
        pnl_dollars=float(ticks * TICK_VALUE),
        bars_held=int(exit_bar["bar_idx"] - entry_bar["bar_idx"] + 1),
        exit_reason=exit_reason,
        abs_strength=float(row["abs_strength"]),
        score_tier=str(row["abs_score_tier"]),
        score_final=float(row["abs_score_final"]),
    )


def simulate_fixed_exit(
    bars: pd.DataFrame,
    row: pd.Series,
    strategy: str,
    stop_ticks: int,
    target_ticks: int,
    max_hold_bars: int | None = None,
) -> Trade | None:
    signal_bar_idx = int(row["bar_idx"])
    entry_idx = signal_bar_idx + 1
    if entry_idx >= len(bars):
        return None

    entry_bar = bars.iloc[entry_idx]
    direction = int(row["abs_direction"])
    entry_price = float(entry_bar["open"])
    stop_price = entry_price - direction * stop_ticks * TICK_SIZE
    target_price = entry_price + direction * target_ticks * TICK_SIZE
    last_idx = len(bars) - 1 if max_hold_bars is None else min(len(bars) - 1, entry_idx + max_hold_bars - 1)

    for j in range(entry_idx, last_idx + 1):
        bar = bars.iloc[j]
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])

        if direction > 0:
            if j > entry_idx and open_price <= stop_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "STOP_GAP")
            if j > entry_idx and open_price >= target_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "TARGET_GAP")
            if low <= stop_price and high >= target_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP_FIRST_SAME_BAR")
            if low <= stop_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP")
            if high >= target_price:
                return make_trade(strategy, row, entry_bar, bar, target_price, "TARGET")
        else:
            if j > entry_idx and open_price >= stop_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "STOP_GAP")
            if j > entry_idx and open_price <= target_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "TARGET_GAP")
            if high >= stop_price and low <= target_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP_FIRST_SAME_BAR")
            if high >= stop_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP")
            if low <= target_price:
                return make_trade(strategy, row, entry_bar, bar, target_price, "TARGET")

    exit_bar = bars.iloc[last_idx]
    return make_trade(strategy, row, entry_bar, exit_bar, float(exit_bar["close"]), "TIME")


def simulate_trailing_exit(
    bars: pd.DataFrame,
    row: pd.Series,
    strategy: str,
    initial_stop_ticks: int = 20,
    activation_ticks: int = 15,
    trail_ticks: int = 20,
    max_hold_bars: int = 30,
) -> Trade | None:
    signal_bar_idx = int(row["bar_idx"])
    entry_idx = signal_bar_idx + 1
    if entry_idx >= len(bars):
        return None

    entry_bar = bars.iloc[entry_idx]
    direction = int(row["abs_direction"])
    entry_price = float(entry_bar["open"])
    stop_price = entry_price - direction * initial_stop_ticks * TICK_SIZE
    trigger_price = entry_price + direction * activation_ticks * TICK_SIZE
    last_idx = min(len(bars) - 1, entry_idx + max_hold_bars - 1)
    activated = False
    best_price = entry_price

    for j in range(entry_idx, last_idx + 1):
        bar = bars.iloc[j]
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])

        if direction > 0:
            if j > entry_idx and open_price <= stop_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "STOP_GAP")
            if low <= stop_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP")
            if high > best_price:
                best_price = high
            if best_price >= trigger_price:
                activated = True
                stop_price = max(stop_price, entry_price, best_price - trail_ticks * TICK_SIZE)
                if low <= stop_price:
                    return make_trade(strategy, row, entry_bar, bar, stop_price, "TRAIL_STOP")
        else:
            if j > entry_idx and open_price >= stop_price:
                return make_trade(strategy, row, entry_bar, bar, open_price, "STOP_GAP")
            if high >= stop_price:
                return make_trade(strategy, row, entry_bar, bar, stop_price, "STOP")
            if low < best_price:
                best_price = low
            if best_price <= trigger_price:
                activated = True
                stop_price = min(stop_price, entry_price, best_price + trail_ticks * TICK_SIZE)
                if high >= stop_price:
                    return make_trade(strategy, row, entry_bar, bar, stop_price, "TRAIL_STOP")

    exit_bar = bars.iloc[last_idx]
    reason = "TIME_TRAIL_ACTIVE" if activated else "TIME"
    return make_trade(strategy, row, entry_bar, exit_bar, float(exit_bar["close"]), reason)


def run_strategy(
    bars: pd.DataFrame,
    candidates: pd.DataFrame,
    strategy: str,
    simulator: Callable[[pd.DataFrame, pd.Series, str], Trade | None],
) -> list[Trade]:
    trades: list[Trade] = []
    last_exit_bar_idx = -1
    for _, row in candidates.sort_values("bar_idx").iterrows():
        if int(row["bar_idx"]) <= last_exit_bar_idx:
            continue
        trade = simulator(bars, row, strategy)
        if trade is None:
            continue
        trades.append(trade)
        last_exit_bar_idx = trade.exit_bar_idx
    return trades


def max_consecutive_losses(pnls: np.ndarray) -> int:
    streak = 0
    worst = 0
    for pnl in pnls:
        if pnl < 0:
            streak += 1
            worst = max(worst, streak)
        else:
            streak = 0
    return worst


def max_drawdown_ticks(pnls: np.ndarray) -> float:
    if len(pnls) == 0:
        return 0.0
    equity = np.cumsum(pnls)
    running_peak = np.maximum.accumulate(equity)
    drawdown = running_peak - equity
    return float(drawdown.max())


def sharpe_ratio_daily(trades_df: pd.DataFrame) -> float | None:
    if trades_df.empty:
        return None
    daily = trades_df.groupby("exit_date")["pnl_ticks"].sum().sort_index()
    all_days = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(all_days, fill_value=0.0)
    std = float(daily.std(ddof=1))
    if std == 0.0 or math.isnan(std):
        return None
    return float((daily.mean() / std) * math.sqrt(252.0))


def describe_equity_curve(trades_df: pd.DataFrame, metrics: dict[str, Any]) -> str:
    if trades_df.empty:
        return "No trades."
    pnls = trades_df["pnl_ticks"].to_numpy(dtype=float)
    total = float(pnls.sum())
    wins = pnls[pnls > 0]
    positive_month_ratio = float((trades_df.groupby("exit_month")["pnl_ticks"].sum() > 0).mean()) if not trades_df.empty else 0.0
    max_dd = float(metrics["max_drawdown_ticks"] or 0.0)
    top_win_share = float(np.sort(wins)[-5:].sum() / wins.sum()) if len(wins) and wins.sum() > 0 else 0.0

    if total <= 0:
        return "Deteriorating / sideways; gains do not sustain against losses."
    if top_win_share >= 0.45:
        return "Profits are concentrated in a small cluster of outsized winners."
    if max_dd <= max(total * 0.35, 1.0) and positive_month_ratio >= 0.60:
        return "Growing steadily with controlled drawdowns across most months."
    if positive_month_ratio >= 0.50:
        return "Choppy but upward-sloping; progress comes with notable pullbacks."
    return "Uneven and regime-dependent; profitability is fragile across months."


def summarize_strategy(strategy: str, trades: list[Trade]) -> dict[str, Any]:
    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    if trades_df.empty:
        return {
            "strategy": strategy,
            "total_trades": 0,
            "win_rate": None,
            "avg_win_ticks": None,
            "avg_loss_ticks": None,
            "profit_factor": None,
            "expectancy_ticks": None,
            "expectancy_dollars": None,
            "max_consecutive_losses": 0,
            "max_drawdown_ticks": 0.0,
            "sharpe_daily": None,
            "total_ticks": 0.0,
            "total_dollars": 0.0,
            "monthly_breakdown_ticks": {},
            "equity_curve_description": "No trades.",
            "trades": trades_df,
        }

    trades_df["exit_ts"] = pd.to_datetime(trades_df["exit_ts"], utc=True)
    trades_df["exit_date"] = trades_df["exit_ts"].dt.date
    trades_df["exit_month"] = trades_df["exit_ts"].dt.tz_convert(ET).dt.strftime("%Y-%m")

    pnls = trades_df["pnl_ticks"].to_numpy(dtype=float)
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(np.abs(losses.sum())) if len(losses) else 0.0
    metrics = {
        "strategy": strategy,
        "total_trades": int(len(trades_df)),
        "win_rate": float((pnls > 0).mean() * 100.0),
        "avg_win_ticks": float(wins.mean()) if len(wins) else None,
        "avg_loss_ticks": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else None),
        "expectancy_ticks": float(pnls.mean()),
        "expectancy_dollars": float(pnls.mean() * TICK_VALUE),
        "max_consecutive_losses": max_consecutive_losses(pnls),
        "max_drawdown_ticks": max_drawdown_ticks(pnls),
        "sharpe_daily": sharpe_ratio_daily(trades_df),
        "total_ticks": float(pnls.sum()),
        "total_dollars": float(pnls.sum() * TICK_VALUE),
        "monthly_breakdown_ticks": trades_df.groupby("exit_month")["pnl_ticks"].sum().round(2).to_dict(),
    }
    metrics["equity_curve_description"] = describe_equity_curve(trades_df, metrics)
    metrics["trades"] = trades_df
    return metrics


def rank_strategies(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scored = []
    for result in results:
        sharpe = result["sharpe_daily"] if result["sharpe_daily"] is not None else -999.0
        pf = result["profit_factor"] if result["profit_factor"] is not None and math.isfinite(result["profit_factor"]) else 999.0
        score = (
            result["expectancy_ticks"] or -999.0,
            sharpe,
            pf,
            -(result["max_drawdown_ticks"] or 0.0),
            result["total_trades"],
        )
        scored.append((score, result))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored]


def print_summary_table(results: list[dict[str, Any]]) -> None:
    summary = pd.DataFrame(
        [
            {
                "Strategy": r["strategy"],
                "Trades": r["total_trades"],
                "Win%": None if r["win_rate"] is None else round(r["win_rate"], 2),
                "AvgWinT": None if r["avg_win_ticks"] is None else round(r["avg_win_ticks"], 2),
                "AvgLossT": None if r["avg_loss_ticks"] is None else round(r["avg_loss_ticks"], 2),
                "PF": None if r["profit_factor"] is None else round(r["profit_factor"], 3),
                "ExpT": None if r["expectancy_ticks"] is None else round(r["expectancy_ticks"], 2),
                "Exp$": None if r["expectancy_dollars"] is None else round(r["expectancy_dollars"], 2),
                "MaxCLoss": r["max_consecutive_losses"],
                "MaxDDT": round(r["max_drawdown_ticks"], 2),
                "SharpeD": None if r["sharpe_daily"] is None else round(r["sharpe_daily"], 3),
                "TotalT": round(r["total_ticks"], 2),
                "Total$": round(r["total_dollars"], 2),
            }
            for r in results
        ]
    )
    print("\nFINAL COMPOSITE STRATEGY COMPARISON")
    print(summary.to_string(index=False))


def main() -> None:
    bars = load_bars()
    signals = load_signals()
    alerts = load_telegram_absorptions()
    bars_full, abs_events = build_bar_feature_frame(bars, signals)
    abs_events = add_telegram_filter(abs_events, alerts)
    strategy_candidates = strategy_filters(abs_events)

    simulators: dict[str, Callable[[pd.DataFrame, pd.Series, str], Trade | None]] = {
        "Strategy 1: Pure Absorption": lambda b, row, name: simulate_fixed_exit(b, row, name, stop_ticks=20, target_ticks=30, max_hold_bars=5),
        "Strategy 2: High-Quality Absorption": lambda b, row, name: simulate_trailing_exit(b, row, name, initial_stop_ticks=20, activation_ticks=15, trail_ticks=20, max_hold_bars=30),
        "Strategy 3: Telegram-Confirmed Absorption": lambda b, row, name: simulate_fixed_exit(b, row, name, stop_ticks=30, target_ticks=50, max_hold_bars=None),
        "Strategy 4: Multi-Signal Confluence": lambda b, row, name: simulate_fixed_exit(b, row, name, stop_ticks=20, target_ticks=40, max_hold_bars=None),
        "Strategy 5: Kitchen Sink": lambda b, row, name: simulate_fixed_exit(b, row, name, stop_ticks=15, target_ticks=30, max_hold_bars=15),
    }

    results: list[dict[str, Any]] = []
    all_trades: list[pd.DataFrame] = []
    for strategy, candidates in strategy_candidates.items():
        trades = run_strategy(bars_full, candidates, strategy, simulators[strategy])
        result = summarize_strategy(strategy, trades)
        results.append(result)
        if not result["trades"].empty:
            all_trades.append(result["trades"])

    ranked = rank_strategies(results)
    print_summary_table(ranked)

    print("\nRANKING")
    for i, result in enumerate(ranked, start=1):
        print(
            f"{i}. {result['strategy']} | trades={result['total_trades']} | "
            f"exp={None if result['expectancy_ticks'] is None else round(result['expectancy_ticks'], 2)}t | "
            f"pf={None if result['profit_factor'] is None else round(result['profit_factor'], 3)} | "
            f"sharpe={None if result['sharpe_daily'] is None else round(result['sharpe_daily'], 3)}"
        )
        print(f"   Monthly ticks: {result['monthly_breakdown_ticks']}")
        print(f"   Equity: {result['equity_curve_description']}")

    export_payload = {
        "assumptions": {
            "entry": "next_bar_open",
            "positioning": "one_position_at_a_time",
            "same_bar_resolution": "conservative_stop_first",
            "strategy_2_initial_stop_ticks": 20,
            "telegram_reference_price": "signal_low_for_long_signal_high_for_short",
            "cost_model": "gross_no_commission_no_slippage",
        },
        "dataset_summary": {
            "bars": int(len(bars)),
            "signals": int(len(signals)),
            "absorption_events": int(len(abs_events)),
            "telegram_absorption_alerts": int(len(alerts)),
        },
        "ranking": [result["strategy"] for result in ranked],
        "results": [
            {k: v for k, v in result.items() if k != "trades"}
            for result in ranked
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(export_payload, indent=2, default=_json_default), encoding="utf-8")

    if all_trades:
        pd.concat(all_trades, ignore_index=True).to_csv(OUTPUT_TRADES, index=False)

    print(f"\nSaved JSON report: {OUTPUT_JSON}")
    print(f"Saved trade log:   {OUTPUT_TRADES}")


if __name__ == "__main__":
    main()
