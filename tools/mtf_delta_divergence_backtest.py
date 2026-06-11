from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DATA_PATH = Path(r"/mnt/c/Users/Tea/DEEP6/data/backtests/signal_events.csv")
REPORT_PATH = Path(r"/mnt/c/Users/Tea/DEEP6/reports/mtf_delta_divergence_backtest_report.json")

TICK_SIZE = 0.25
PIVOT_LOOKBACK = 20
MIN_BARS = 20
MIN_PRICE_BREAK_TICKS = 4
MIN_DELTA_IMPROVEMENT = 250
CLOSE_CONFIRMATION_RATIO = 0.50
MIN_ALIGNED_TIMEFRAMES = 3
STOP_LOSS_TICKS = 24
PROFIT_TARGET_TICKS = 40
MAX_BARS_IN_TRADE = 24
MIN_BARS_BETWEEN_ENTRIES = 3


@dataclass
class Bar:
    ts: datetime
    session_date: str
    bar_index: int
    open: float
    high: float
    low: float
    close: float
    delta: int


@dataclass
class AggBar:
    key: str
    open: float
    high: float
    low: float
    close: float
    delta: int


class Bias:
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1


class Engine:
    def __init__(self) -> None:
        self.bars: List[AggBar] = []
        self.current_bias = Bias.NEUTRAL

    def add_bar(self, bar: AggBar) -> int:
        self.bars.append(bar)
        self.current_bias = self.evaluate_latest()
        return self.current_bias

    def evaluate_latest(self) -> int:
        if len(self.bars) < max(2, MIN_BARS):
            return Bias.NEUTRAL

        current = self.bars[-1]
        lookback = min(PIVOT_LOOKBACK, len(self.bars) - 1)
        start = (len(self.bars) - 1) - lookback
        price_break_distance = MIN_PRICE_BREAK_TICKS * TICK_SIZE

        prior_low_index = start
        prior_high_index = start
        for i in range(start + 1, len(self.bars) - 1):
            if self.bars[i].low < self.bars[prior_low_index].low:
                prior_low_index = i
            if self.bars[i].high > self.bars[prior_high_index].high:
                prior_high_index = i

        prior_low = self.bars[prior_low_index]
        prior_high = self.bars[prior_high_index]

        bullish = (
            current.low <= prior_low.low - price_break_distance
            and current.delta >= prior_low.delta + MIN_DELTA_IMPROVEMENT
            and self._bullish_close(current)
        )
        bearish = (
            current.high >= prior_high.high + price_break_distance
            and current.delta <= prior_high.delta - MIN_DELTA_IMPROVEMENT
            and self._bearish_close(current)
        )

        if bullish == bearish:
            return Bias.NEUTRAL
        return Bias.BULLISH if bullish else Bias.BEARISH

    @staticmethod
    def to_composite(biases: Iterable[int], min_agreement: int) -> int:
        bulls = sum(1 for b in biases if b == Bias.BULLISH)
        bears = sum(1 for b in biases if b == Bias.BEARISH)
        if bulls >= min_agreement and bulls > bears:
            return Bias.BULLISH
        if bears >= min_agreement and bears > bulls:
            return Bias.BEARISH
        return Bias.NEUTRAL

    @staticmethod
    def _bullish_close(bar: AggBar) -> bool:
        rng = max(bar.high - bar.low, TICK_SIZE)
        threshold = bar.low + (rng * CLOSE_CONFIRMATION_RATIO)
        return bar.close >= threshold

    @staticmethod
    def _bearish_close(bar: AggBar) -> bool:
        rng = max(bar.high - bar.low, TICK_SIZE)
        threshold = bar.high - (rng * CLOSE_CONFIRMATION_RATIO)
        return bar.close <= threshold


def load_unique_minute_bars(path: Path) -> List[Bar]:
    bars: List[Bar] = []
    seen = set()
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            global_index = int(row["global_index"])
            if global_index in seen:
                continue
            seen.add(global_index)
            bars.append(
                Bar(
                    ts=datetime.fromisoformat(row["bar_ts"]),
                    session_date=row["session_date"],
                    bar_index=int(row["bar_index"]),
                    open=float(row["bar_open"]),
                    high=float(row["bar_high"]),
                    low=float(row["bar_low"]),
                    close=float(row["bar_close"]),
                    delta=int(float(row["bar_delta"])),
                )
            )
    return bars


def hour_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:00:00%z")


def four_hour_key(ts: datetime) -> str:
    bucket_hour = (ts.hour // 4) * 4
    return ts.replace(hour=bucket_hour, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00:00%z")


def daily_key(bar: Bar) -> str:
    return bar.session_date


def update_bucket(state: Dict[str, Optional[AggBar]], key: str, bar: Bar) -> Tuple[Optional[AggBar], Optional[AggBar]]:
    current = state.get("current")
    completed = None
    if current is None:
        state["current"] = AggBar(key=key, open=bar.open, high=bar.high, low=bar.low, close=bar.close, delta=bar.delta)
        return None, state["current"]
    if current.key != key:
        completed = current
        state["current"] = AggBar(key=key, open=bar.open, high=bar.high, low=bar.low, close=bar.close, delta=bar.delta)
        return completed, state["current"]

    current.high = max(current.high, bar.high)
    current.low = min(current.low, bar.low)
    current.close = bar.close
    current.delta += bar.delta
    return None, current


def run_backtest(bars: List[Bar], min_aligned_timeframes: int = MIN_ALIGNED_TIMEFRAMES) -> dict:
    hour_engine = Engine()
    four_hour_engine = Engine()
    daily_engine = Engine()

    hour_state: Dict[str, Optional[AggBar]] = {"current": None}
    four_hour_state: Dict[str, Optional[AggBar]] = {"current": None}
    daily_state: Dict[str, Optional[AggBar]] = {"current": None}

    hour_bias = Bias.NEUTRAL
    four_hour_bias = Bias.NEUTRAL
    daily_bias = Bias.NEUTRAL
    last_composite = Bias.NEUTRAL

    position = 0
    entry_price = 0.0
    entry_bar = -10_000
    entry_reason = ""
    trades = []
    composite_counts = defaultdict(int)

    stop_distance = STOP_LOSS_TICKS * TICK_SIZE
    target_distance = PROFIT_TARGET_TICKS * TICK_SIZE

    for i, bar in enumerate(bars):
        completed, _ = update_bucket(hour_state, hour_key(bar.ts), bar)
        if completed is not None:
            hour_bias = hour_engine.add_bar(completed)

        completed, _ = update_bucket(four_hour_state, four_hour_key(bar.ts), bar)
        if completed is not None:
            four_hour_bias = four_hour_engine.add_bar(completed)

        completed, _ = update_bucket(daily_state, daily_key(bar), bar)
        if completed is not None:
            daily_bias = daily_engine.add_bar(completed)

        composite = Engine.to_composite([hour_bias, four_hour_bias, daily_bias], min_aligned_timeframes)
        composite_counts[str(composite)] += 1

        if position != 0:
            exit_price = None
            exit_reason = None
            if position > 0:
                if bar.low <= entry_price - stop_distance:
                    exit_price = entry_price - stop_distance
                    exit_reason = "StopLoss"
                elif bar.high >= entry_price + target_distance:
                    exit_price = entry_price + target_distance
                    exit_reason = "ProfitTarget"
                elif i - entry_bar >= MAX_BARS_IN_TRADE:
                    exit_price = bar.close
                    exit_reason = "TimedExit"
                elif composite == Bias.BEARISH:
                    exit_price = bar.close
                    exit_reason = "FlipExit"
            else:
                if bar.high >= entry_price + stop_distance:
                    exit_price = entry_price + stop_distance
                    exit_reason = "StopLoss"
                elif bar.low <= entry_price - target_distance:
                    exit_price = entry_price - target_distance
                    exit_reason = "ProfitTarget"
                elif i - entry_bar >= MAX_BARS_IN_TRADE:
                    exit_price = bar.close
                    exit_reason = "TimedExit"
                elif composite == Bias.BULLISH:
                    exit_price = bar.close
                    exit_reason = "FlipExit"

            if exit_price is not None:
                pnl_points = (exit_price - entry_price) * position
                trades.append(
                    {
                        "entry_ts": bars[entry_bar].ts.isoformat(),
                        "exit_ts": bar.ts.isoformat(),
                        "side": "long" if position > 0 else "short",
                        "entry": entry_price,
                        "exit": exit_price,
                        "pnl_points": pnl_points,
                        "pnl_ticks": pnl_points / TICK_SIZE,
                        "entry_reason": entry_reason,
                        "exit_reason": exit_reason,
                        "bars_held": i - entry_bar,
                    }
                )
                position = 0
                entry_price = 0.0
                entry_reason = ""

        if position == 0:
            if i - entry_bar < MIN_BARS_BETWEEN_ENTRIES:
                last_composite = composite
                continue
            if composite == Bias.NEUTRAL or composite == last_composite:
                last_composite = composite
                continue
            position = 1 if composite == Bias.BULLISH else -1
            entry_price = bar.close
            entry_bar = i
            entry_reason = "MtfDeltaBull" if position > 0 else "MtfDeltaBear"

        last_composite = composite

    if position != 0:
        bar = bars[-1]
        pnl_points = (bar.close - entry_price) * position
        trades.append(
            {
                "entry_ts": bars[entry_bar].ts.isoformat(),
                "exit_ts": bar.ts.isoformat(),
                "side": "long" if position > 0 else "short",
                "entry": entry_price,
                "exit": bar.close,
                "pnl_points": pnl_points,
                "pnl_ticks": pnl_points / TICK_SIZE,
                "entry_reason": entry_reason,
                "exit_reason": "EndOfData",
                "bars_held": len(bars) - 1 - entry_bar,
            }
        )

    gross_points = sum(t["pnl_points"] for t in trades)
    wins = [t for t in trades if t["pnl_points"] > 0]
    losses = [t for t in trades if t["pnl_points"] < 0]
    long_trades = [t for t in trades if t["side"] == "long"]
    short_trades = [t for t in trades if t["side"] == "short"]

    return {
        "config": {
            "tick_size": TICK_SIZE,
            "pivot_lookback": PIVOT_LOOKBACK,
            "min_bars": MIN_BARS,
            "min_price_break_ticks": MIN_PRICE_BREAK_TICKS,
            "min_delta_improvement": MIN_DELTA_IMPROVEMENT,
            "close_confirmation_ratio": CLOSE_CONFIRMATION_RATIO,
            "min_aligned_timeframes": min_aligned_timeframes,
            "stop_loss_ticks": STOP_LOSS_TICKS,
            "profit_target_ticks": PROFIT_TARGET_TICKS,
            "max_bars_in_trade": MAX_BARS_IN_TRADE,
            "min_bars_between_entries": MIN_BARS_BETWEEN_ENTRIES,
        },
        "dataset": {
            "path": str(DATA_PATH),
            "bars": len(bars),
            "first_ts": bars[0].ts.isoformat() if bars else None,
            "last_ts": bars[-1].ts.isoformat() if bars else None,
            "sessions": len({b.session_date for b in bars}),
        },
        "signals": {
            "composite_bullish_bars": composite_counts[str(Bias.BULLISH)],
            "composite_bearish_bars": composite_counts[str(Bias.BEARISH)],
            "composite_neutral_bars": composite_counts[str(Bias.NEUTRAL)],
            "hour_bias_events": len(hour_engine.bars),
            "four_hour_bias_events": len(four_hour_engine.bars),
            "daily_bias_events": len(daily_engine.bars),
        },
        "performance": {
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round((len(wins) / len(trades) * 100.0), 2) if trades else 0.0,
            "gross_points": round(gross_points, 2),
            "gross_ticks": round(gross_points / TICK_SIZE, 2),
            "avg_trade_points": round(gross_points / len(trades), 4) if trades else 0.0,
            "avg_win_points": round(sum(t["pnl_points"] for t in wins) / len(wins), 4) if wins else 0.0,
            "avg_loss_points": round(sum(t["pnl_points"] for t in losses) / len(losses), 4) if losses else 0.0,
            "profit_factor": round(
                abs(sum(t["pnl_points"] for t in wins) / sum(t["pnl_points"] for t in losses)), 4
            ) if wins and losses else None,
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
        },
        "sample_trades": trades[:10],
    }


def main() -> None:
    bars = load_unique_minute_bars(DATA_PATH)
    scenario_results = {
        "min_aligned_1": run_backtest(bars, 1),
        "min_aligned_2": run_backtest(bars, 2),
        "min_aligned_3": run_backtest(bars, 3),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(scenario_results, indent=2))
    print(json.dumps(scenario_results, indent=2))


if __name__ == "__main__":
    main()
