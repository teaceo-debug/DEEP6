from __future__ import annotations

import time
from collections import deque
from datetime import date
from pathlib import Path

import pandas as pd

from deep6v2.backtest.ohlcv_synthesizer import synthesize_footprint
from deep6v2.backtest.trade_simulator import TradeSimulator
from deep6v2.scoring.entry_gate import EntryDecision, EntryGate
from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.signals.registry import DetectorRegistry
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.scoring import ScorerResult
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalResult

DEFAULT_CSV_PATH = Path("data/backtests/nq_1yr_1m.csv")


class ReplayEngine:
    def __init__(self) -> None:
        self.registry = DetectorRegistry.create_default()
        self.scorer = ConfluenceScorer()
        self.entry_gate = EntryGate()
        self.results: list[dict[str, object]] = []

    def run(self, csv_path: str | Path) -> list[dict[str, object]]:
        df = pd.read_csv(
            csv_path,
            usecols=["ts_event", "open", "high", "low", "close", "volume"],
            parse_dates=["ts_event"],
        )
        df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
        df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")

        minutes = (df["ts_et"].dt.hour * 60) + df["ts_et"].dt.minute
        df = df.loc[(minutes >= 570) & (minutes < 960)].copy()
        df["session_date"] = df["ts_et"].dt.date

        trades: list[dict[str, object]] = []
        self.results.clear()
        for session_date, session_df in df.groupby("session_date", sort=True):
            trades.extend(self._run_session(session_date, session_df))
        return trades

    def _run_session(self, session_date: date, session_df: pd.DataFrame) -> list[dict[str, object]]:
        ctx = SessionContext(
            atr=0.0,
            cvd=0.0,
            vah=0.0,
            val=0.0,
            poc=0.0,
            session_type=SessionType.RTH,
            session_open_bar_index=0,
        )
        simulator = TradeSimulator(dollars_per_point=20.0)
        trades: list[dict[str, object]] = []
        armed_decision: tuple[list[SignalResult], ScorerResult, EntryDecision] | None = None
        cvd_accum = 0.0
        true_ranges: deque[float] = deque(maxlen=14)
        previous_close: float | None = None
        session_profile: dict[float, int] = {}
        first_bar = True
        last_bar: FootprintBar | None = None

        for bar_index, row in enumerate(session_df.itertuples(index=False)):
            bar = synthesize_footprint(
                ts=row.ts_et.to_pydatetime(),
                open_=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=int(row.volume),
                bar_index=bar_index,
                cvd_accum=cvd_accum,
            )
            last_bar = bar
            cvd_accum = bar.cvd

            if first_bar:
                ctx.vah = bar.vah
                ctx.val = bar.val
                ctx.poc = bar.poc_price
                first_bar = False

            ctx.current_bar = bar
            ctx.cvd = bar.cvd

            if previous_close is None:
                true_range = bar.high - bar.low
            else:
                true_range = max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
            true_ranges.append(true_range)
            ctx.atr = (sum(true_ranges) / len(true_ranges)) if true_ranges else 0.0

            closed_trade = simulator.on_bar(bar)
            if closed_trade is not None:
                trades.append(closed_trade.as_dict())
                self.results.append({"bar": bar, "signals": [], "score": None, "decision": None, "trade": closed_trade.as_dict()})
                self._append_history(ctx, bar)
                self._update_profile(session_profile, ctx, bar)
                previous_close = bar.close
                armed_decision = None
                continue

            if armed_decision is not None:
                _, _, decision = armed_decision
                if decision.eligible and decision.direction in (Direction.BULLISH, Direction.BEARISH):
                    stop_distance = max(5.0, 2.0 * max(ctx.atr, 0.25))
                    target_distance = stop_distance * 2.0
                    if decision.direction is Direction.BULLISH:
                        stop_price = bar.open - stop_distance
                        target_price = bar.open + target_distance
                    else:
                        stop_price = bar.open + stop_distance
                        target_price = bar.open - target_distance

                    simulator.enter(
                        session_date=session_date,
                        entry_price=bar.open,
                        direction=decision.direction,
                        entry_time=bar.timestamp,
                        entry_bar_index=bar.bar_index,
                        stop_price=stop_price,
                        target_price=target_price,
                    )
                armed_decision = None

            try:
                signals = self.registry.evaluate_bar(bar, ctx)
            except Exception:
                signals = []

            score: ScorerResult | None = None
            decision: EntryDecision | None = None
            if signals:
                score = self.scorer.score(signals, bar.bar_index)
                decision = self.entry_gate.evaluate(score, bar, ctx)
                if decision.eligible and not simulator.in_position:
                    armed_decision = (signals, score, decision)

            self.results.append({"bar": bar, "signals": signals, "score": score, "decision": decision, "trade": None})
            self._append_history(ctx, bar)
            self._update_profile(session_profile, ctx, bar)
            previous_close = bar.close

        if last_bar is not None:
            forced = simulator.force_close(last_bar.close, last_bar.timestamp, last_bar.bar_index)
            if forced is not None:
                trades.append(forced.as_dict())
                self.results.append({"bar": last_bar, "signals": [], "score": None, "decision": None, "trade": forced.as_dict()})

        return trades

    @staticmethod
    def _append_history(ctx: SessionContext, bar: FootprintBar) -> None:
        ctx.bar_history.append(bar)
        ctx.price_history.append(bar.close)
        ctx.cvd_history.append(bar.cvd)
        ctx.delta_history.append(bar.delta)
        ctx.poc_history.append(bar.poc_price)
        ctx.vol_history.append(bar.total_volume)

    @staticmethod
    def _update_profile(session_profile: dict[float, int], ctx: SessionContext, bar: FootprintBar) -> None:
        for price in set(bar.bid_volumes) | set(bar.ask_volumes):
            session_profile[price] = session_profile.get(price, 0) + bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)
        if not session_profile:
            return

        poc_price = max(session_profile, key=session_profile.get)
        target = sum(session_profile.values()) * 0.70
        levels = sorted(session_profile)
        included = {poc_price}
        running = session_profile[poc_price]
        center = levels.index(poc_price)
        left = center - 1
        right = center + 1
        while running < target and (left >= 0 or right < len(levels)):
            left_volume = session_profile[levels[left]] if left >= 0 else -1
            right_volume = session_profile[levels[right]] if right < len(levels) else -1
            if right_volume > left_volume:
                included.add(levels[right])
                running += right_volume
                right += 1
            else:
                included.add(levels[left])
                running += left_volume
                left -= 1

        ctx.poc = poc_price
        ctx.vah = max(included)
        ctx.val = min(included)


def summarize_trades(trades: list[dict[str, object]], elapsed: float) -> str:
    if not trades:
        return "Running DEEP6 v2 backtest on 1yr NQ data...\nNo trades generated."

    tdf = pd.DataFrame(trades)
    total_pnl = float(tdf["pnl"].sum())
    wins = int((tdf["pnl"] > 0).sum())
    losses = int((tdf["pnl"] <= 0).sum())
    win_rate = (wins / len(tdf) * 100.0) if len(tdf) else 0.0
    avg_win = float(tdf.loc[tdf["pnl"] > 0, "pnl"].mean()) if wins else 0.0
    avg_loss = float(tdf.loc[tdf["pnl"] <= 0, "pnl"].mean()) if losses else 0.0
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in tdf["pnl"]:
        running += float(pnl)
        peak = max(peak, running)
        max_dd = min(max_dd, running - peak)

    pnl_std = float(tdf["pnl"].std()) if len(tdf) > 1 else 0.0
    pnl_mean = float(tdf["pnl"].mean()) if len(tdf) else 0.0
    sharpe = (pnl_mean / pnl_std * (252 ** 0.5)) if pnl_std > 0 else 0.0
    losing_sum = float(tdf.loc[tdf["pnl"] <= 0, "pnl"].sum()) if losses else 0.0
    winning_sum = float(tdf.loc[tdf["pnl"] > 0, "pnl"].sum()) if wins else 0.0
    profit_factor = abs(winning_sum / losing_sum) if losing_sum != 0 else float("inf")

    tdf["month"] = pd.to_datetime(tdf["date"]).dt.to_period("M")
    sections = [
        "Running DEEP6 v2 backtest on 1yr NQ data...",
        "",
        f"{'=' * 60}",
        "DEEP6 v2 BACKTEST RESULTS — NQ 1-Minute",
        f"{'=' * 60}",
        "Period:          2025-01-01 to 2026-04-24",
        f"RTH Sessions:    {tdf['date'].nunique()}",
        f"Runtime:         {elapsed:.1f}s",
        f"{'=' * 60}",
        f"Total Trades:    {len(tdf)}",
        f"Wins:            {wins} ({win_rate:.1f}%)",
        f"Losses:          {losses}",
        f"{'=' * 60}",
        f"Total P&L:       ${total_pnl:,.0f}",
        f"Avg Win:         ${avg_win:,.0f}",
        f"Avg Loss:        ${avg_loss:,.0f}",
        f"Profit Factor:   {profit_factor:.2f}",
        f"Sharpe (ann):    {sharpe:.2f}",
        f"Max Drawdown:    ${max_dd:,.0f}",
        f"{'=' * 60}",
        "",
        "By Exit Reason:",
        tdf.groupby("exit_reason")["pnl"].agg(["count", "sum", "mean"]).to_string(),
        "",
        "By Side:",
        tdf.groupby("side")["pnl"].agg(["count", "sum", "mean"]).to_string(),
        "",
        "Monthly P&L:",
        tdf.groupby("month")["pnl"].agg(["count", "sum"]).to_string(),
    ]
    return "\n".join(sections)


if __name__ == "__main__":
    engine = ReplayEngine()
    started = time.time()
    trades = engine.run(DEFAULT_CSV_PATH)
    print(summarize_trades(trades, time.time() - started))


__all__ = ["DEFAULT_CSV_PATH", "ReplayEngine", "summarize_trades"]
