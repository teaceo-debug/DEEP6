"""Parameter sweep: run signals once, then sweep trade params against cached scores."""

from __future__ import annotations

import itertools
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from deep6v2.backtest.ohlcv_synthesizer import synthesize_footprint
from deep6v2.scoring.entry_gate import EntryGate
from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.signals.registry import DetectorRegistry
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.scoring import SignalTier
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalResult

DEFAULT_CSV = Path("data/backtests/nq_1yr_1m.csv")


@dataclass(slots=True)
class ScoredBar:
    bar: FootprintBar
    score: float
    tier: str
    direction: Direction
    eligible: bool
    n_signals: int
    n_categories: int


@dataclass(slots=True)
class SweepParams:
    score_min: float
    stop_mult: float
    rr_ratio: float
    cooldown: int
    min_signals: int

    def label(self) -> str:
        return f"sc{self.score_min:.0f}_st{self.stop_mult:.1f}_rr{self.rr_ratio:.1f}_cd{self.cooldown}_ms{self.min_signals}"


@dataclass(slots=True)
class SweepResult:
    params: SweepParams
    trades: int
    wins: int
    losses: int
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    win_rate: float
    sharpe: float
    sessions_with_trades: int


# ── Phase 1: Signal Scan (run once) ──────────────────────────────

def scan_signals(csv_path: Path) -> dict[date, list[ScoredBar]]:
    """Run all 52 detectors + scorer on every RTH bar. Cache results per session."""
    registry = DetectorRegistry.create_default()
    scorer = ConfluenceScorer()
    gate = EntryGate()

    df = pd.read_csv(csv_path, usecols=["ts_event", "open", "high", "low", "close", "volume"], parse_dates=["ts_event"])
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")
    minutes = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    df = df.loc[(minutes >= 570) & (minutes < 960)].copy()
    df["session_date"] = df["ts_et"].dt.date

    sessions: dict[date, list[ScoredBar]] = {}
    total_bars = 0

    for session_date, sdf in df.groupby("session_date", sort=True):
        ctx = SessionContext(
            atr=0.0, cvd=0.0, vah=0.0, val=0.0, poc=0.0,
            session_type=SessionType.RTH, session_open_bar_index=0,
        )
        cvd_accum = 0.0
        true_ranges: deque[float] = deque(maxlen=14)
        prev_close: float | None = None
        session_profile: dict[float, int] = {}
        bars: list[ScoredBar] = []

        for bar_index, row in enumerate(sdf.itertuples(index=False)):
            bar = synthesize_footprint(
                ts=row.ts_et.to_pydatetime(),
                open_=row.open, high=row.high, low=row.low, close=row.close,
                volume=int(row.volume), bar_index=bar_index, cvd_accum=cvd_accum,
            )
            cvd_accum = bar.cvd
            total_bars += 1

            # Update context
            if bar_index == 0:
                ctx.vah, ctx.val, ctx.poc = bar.vah, bar.val, bar.poc_price
            ctx.current_bar = bar
            ctx.cvd = bar.cvd

            if prev_close is None:
                tr = bar.high - bar.low
            else:
                tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            true_ranges.append(tr)
            ctx.atr = sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

            # Detect + score
            try:
                signals = registry.evaluate_bar(bar, ctx)
            except Exception:
                signals = []

            if signals:
                result = scorer.score(signals, bar.bar_index)
                decision = gate.evaluate(result, bar, ctx)
                cats = set()
                from deep6v2.types.signal import SIGNAL_TO_CATEGORY
                for s in signals:
                    cat = SIGNAL_TO_CATEGORY.get(s.signal_id)
                    if cat is not None:
                        cats.add(cat)
                bars.append(ScoredBar(
                    bar=bar, score=result.final_score,
                    tier=result.tier.value, direction=decision.direction,
                    eligible=decision.eligible, n_signals=len(signals),
                    n_categories=len(cats),
                ))
            else:
                bars.append(ScoredBar(
                    bar=bar, score=0.0, tier="QUIET",
                    direction=Direction.NEUTRAL, eligible=False,
                    n_signals=0, n_categories=0,
                ))

            # Update histories
            ctx.bar_history.append(bar)
            ctx.price_history.append(bar.close)
            ctx.cvd_history.append(bar.cvd)
            ctx.delta_history.append(bar.delta)
            ctx.poc_history.append(bar.poc_price)
            ctx.vol_history.append(bar.total_volume)

            # Update session profile for VA
            for price in set(bar.bid_volumes) | set(bar.ask_volumes):
                session_profile[price] = session_profile.get(price, 0) + bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)
            if session_profile:
                poc_p = max(session_profile, key=session_profile.get)
                ctx.poc = poc_p
                target = sum(session_profile.values()) * 0.70
                levels_sorted = sorted(session_profile)
                included = {poc_p}
                running_va = session_profile[poc_p]
                center = levels_sorted.index(poc_p)
                left, right = center - 1, center + 1
                while running_va < target and (left >= 0 or right < len(levels_sorted)):
                    lv = session_profile[levels_sorted[left]] if left >= 0 else -1
                    rv = session_profile[levels_sorted[right]] if right < len(levels_sorted) else -1
                    if rv > lv:
                        included.add(levels_sorted[right])
                        running_va += rv
                        right += 1
                    else:
                        included.add(levels_sorted[left])
                        running_va += lv
                        left -= 1
                ctx.vah, ctx.val = max(included), min(included)

            prev_close = bar.close

        sessions[session_date] = bars

    return sessions


# ── Phase 2: Fast Trade Simulation ───────────────────────────────

def simulate_trades(sessions: dict[date, list[ScoredBar]], params: SweepParams) -> SweepResult:
    """Simulate trades using cached scored bars. Fast — no signal computation."""
    all_pnl: list[float] = []
    sessions_active = 0
    DPP = 20.0  # dollars per point

    for session_date, bars in sessions.items():
        in_trade = False
        entry_price = 0.0
        entry_dir = Direction.NEUTRAL
        stop_px = 0.0
        target_px = 0.0
        entry_bar = 0
        armed = False
        armed_dir = Direction.NEUTRAL
        armed_score = 0.0
        armed_signals = 0
        armed_cats = 0
        bars_since_trade = 999  # allow immediate first trade
        session_traded = False

        for i, sb in enumerate(bars):
            bar = sb.bar

            # Check exit
            if in_trade:
                if entry_dir == Direction.BULLISH:
                    if bar.low <= stop_px:
                        all_pnl.append((stop_px - entry_price) * DPP)
                        in_trade = False
                        bars_since_trade = 0
                    elif bar.high >= target_px:
                        all_pnl.append((target_px - entry_price) * DPP)
                        in_trade = False
                        bars_since_trade = 0
                else:
                    if bar.high >= stop_px:
                        all_pnl.append((entry_price - stop_px) * DPP)
                        in_trade = False
                        bars_since_trade = 0
                    elif bar.low <= target_px:
                        all_pnl.append((entry_price - target_px) * DPP)
                        in_trade = False
                        bars_since_trade = 0

                if in_trade and i == len(bars) - 1:
                    # Force close
                    if entry_dir == Direction.BULLISH:
                        all_pnl.append((bar.close - entry_price) * DPP)
                    else:
                        all_pnl.append((entry_price - bar.close) * DPP)
                    in_trade = False
                continue

            bars_since_trade += 1

            # D-20 confirmation
            if armed:
                armed = False
                if not in_trade and bars_since_trade >= params.cooldown:
                    in_trade = True
                    session_traded = True
                    entry_price = bar.open
                    entry_dir = armed_dir
                    entry_bar = i

                    # Compute ATR from recent bars
                    recent = bars[max(0, i - 14):i]
                    if recent:
                        atr = sum(b.bar.high - b.bar.low for b in recent) / len(recent)
                    else:
                        atr = 5.0
                    atr = max(atr, 0.5)

                    stop_dist = max(5.0, params.stop_mult * atr)
                    target_dist = stop_dist * params.rr_ratio

                    if entry_dir == Direction.BULLISH:
                        stop_px = entry_price - stop_dist
                        target_px = entry_price + target_dist
                    else:
                        stop_px = entry_price + stop_dist
                        target_px = entry_price - target_dist
                continue

            # Check entry criteria
            if (
                not in_trade
                and sb.score >= params.score_min
                and sb.direction in (Direction.BULLISH, Direction.BEARISH)
                and sb.n_signals >= params.min_signals
                and bars_since_trade >= params.cooldown
            ):
                armed = True
                armed_dir = sb.direction

        if session_traded:
            sessions_active += 1

    # Compute stats
    if not all_pnl:
        return SweepResult(
            params=params, trades=0, wins=0, losses=0,
            total_pnl=0.0, avg_win=0.0, avg_loss=0.0,
            profit_factor=0.0, max_drawdown=0.0, win_rate=0.0,
            sharpe=0.0, sessions_with_trades=0,
        )

    wins_pnl = [p for p in all_pnl if p > 0]
    losses_pnl = [p for p in all_pnl if p <= 0]
    total = sum(all_pnl)
    peak = 0.0
    dd = 0.0
    running = 0.0
    for p in all_pnl:
        running += p
        peak = max(peak, running)
        dd = min(dd, running - peak)

    mean = total / len(all_pnl)
    std = (sum((p - mean) ** 2 for p in all_pnl) / len(all_pnl)) ** 0.5 if len(all_pnl) > 1 else 0.0

    return SweepResult(
        params=params,
        trades=len(all_pnl),
        wins=len(wins_pnl),
        losses=len(losses_pnl),
        total_pnl=total,
        avg_win=sum(wins_pnl) / len(wins_pnl) if wins_pnl else 0.0,
        avg_loss=sum(losses_pnl) / len(losses_pnl) if losses_pnl else 0.0,
        profit_factor=abs(sum(wins_pnl) / sum(losses_pnl)) if losses_pnl and sum(losses_pnl) != 0 else 0.0,
        max_drawdown=dd,
        win_rate=len(wins_pnl) / len(all_pnl) * 100,
        sharpe=(mean / std * (252 ** 0.5)) if std > 0 else 0.0,
        sessions_with_trades=sessions_active,
    )


# ── Phase 3: Sweep ───────────────────────────────────────────────

def run_sweep(csv_path: Path = DEFAULT_CSV) -> list[SweepResult]:
    print("Phase 1: Scanning signals across all sessions...")
    t0 = time.time()
    sessions = scan_signals(csv_path)
    scan_time = time.time() - t0
    total_bars = sum(len(b) for b in sessions.values())
    print(f"  Scanned {total_bars:,} bars across {len(sessions)} sessions in {scan_time:.1f}s")

    # Parameter grid
    score_mins = [72, 78, 82, 86, 90, 94]
    stop_mults = [1.5, 2.0, 2.5, 3.0]
    rr_ratios = [1.5, 2.0, 2.5, 3.0]
    cooldowns = [0, 5, 10, 20]
    min_signals_list = [1, 2, 3]

    combos = list(itertools.product(score_mins, stop_mults, rr_ratios, cooldowns, min_signals_list))
    print(f"\nPhase 2: Sweeping {len(combos)} parameter combinations...")
    t1 = time.time()

    results: list[SweepResult] = []
    for i, (sc, st, rr, cd, ms) in enumerate(combos):
        params = SweepParams(score_min=sc, stop_mult=st, rr_ratio=rr, cooldown=cd, min_signals=ms)
        result = simulate_trades(sessions, params)
        results.append(result)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(combos)} done...")

    sweep_time = time.time() - t1
    print(f"  Sweep completed in {sweep_time:.1f}s")

    return results


def print_results(results: list[SweepResult]) -> None:
    # Filter to configs with at least 20 trades
    viable = [r for r in results if r.trades >= 20]
    if not viable:
        viable = [r for r in results if r.trades >= 5]
    if not viable:
        print("\nNo configurations produced enough trades.")
        return

    # Sort by total P&L
    by_pnl = sorted(viable, key=lambda r: r.total_pnl, reverse=True)

    # Sort by profit factor
    by_pf = sorted(viable, key=lambda r: r.profit_factor, reverse=True)

    # Sort by Sharpe
    by_sharpe = sorted(viable, key=lambda r: r.sharpe, reverse=True)

    print(f"\n{'=' * 100}")
    print("TOP 10 BY TOTAL P&L (min 20 trades)")
    print(f"{'=' * 100}")
    print(f"{'Config':<35} {'Trades':>6} {'WR%':>6} {'PnL':>10} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10} {'AvgW':>8} {'AvgL':>8}")
    print("-" * 100)
    for r in by_pnl[:10]:
        p = r.params
        label = f"sc{p.score_min:.0f} st{p.stop_mult:.1f} rr{p.rr_ratio:.1f} cd{p.cooldown} ms{p.min_signals}"
        print(f"{label:<35} {r.trades:>6} {r.win_rate:>5.1f}% ${r.total_pnl:>9,.0f} {r.profit_factor:>5.2f} {r.sharpe:>7.2f} ${r.max_drawdown:>9,.0f} ${r.avg_win:>7,.0f} ${r.avg_loss:>7,.0f}")

    print(f"\n{'=' * 100}")
    print("TOP 10 BY PROFIT FACTOR (min 20 trades)")
    print(f"{'=' * 100}")
    print(f"{'Config':<35} {'Trades':>6} {'WR%':>6} {'PnL':>10} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10}")
    print("-" * 100)
    for r in by_pf[:10]:
        p = r.params
        label = f"sc{p.score_min:.0f} st{p.stop_mult:.1f} rr{p.rr_ratio:.1f} cd{p.cooldown} ms{p.min_signals}"
        print(f"{label:<35} {r.trades:>6} {r.win_rate:>5.1f}% ${r.total_pnl:>9,.0f} {r.profit_factor:>5.2f} {r.sharpe:>7.2f} ${r.max_drawdown:>9,.0f}")

    print(f"\n{'=' * 100}")
    print("TOP 10 BY SHARPE RATIO (min 20 trades)")
    print(f"{'=' * 100}")
    print(f"{'Config':<35} {'Trades':>6} {'WR%':>6} {'PnL':>10} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10}")
    print("-" * 100)
    for r in by_sharpe[:10]:
        p = r.params
        label = f"sc{p.score_min:.0f} st{p.stop_mult:.1f} rr{p.rr_ratio:.1f} cd{p.cooldown} ms{p.min_signals}"
        print(f"{label:<35} {r.trades:>6} {r.win_rate:>5.1f}% ${r.total_pnl:>9,.0f} {r.profit_factor:>5.2f} {r.sharpe:>7.2f} ${r.max_drawdown:>9,.0f}")

    # Best overall (highest Sharpe with PF > 1.0)
    profitable = [r for r in viable if r.profit_factor > 1.0 and r.trades >= 20]
    if profitable:
        best = max(profitable, key=lambda r: r.sharpe)
        p = best.params
        print(f"\n{'=' * 100}")
        print("BEST OVERALL (Profitable + Best Sharpe + min 20 trades)")
        print(f"{'=' * 100}")
        print(f"  Score threshold:  {p.score_min}")
        print(f"  Stop multiplier:  {p.stop_mult}x ATR")
        print(f"  Reward:Risk:      {p.rr_ratio}:1")
        print(f"  Cooldown:         {p.cooldown} bars")
        print(f"  Min signals:      {p.min_signals}")
        print(f"  ─────────────────────────")
        print(f"  Trades:           {best.trades}")
        print(f"  Win Rate:         {best.win_rate:.1f}%")
        print(f"  Total P&L:        ${best.total_pnl:,.0f}")
        print(f"  Profit Factor:    {best.profit_factor:.2f}")
        print(f"  Sharpe (ann):     {best.sharpe:.2f}")
        print(f"  Max Drawdown:     ${best.max_drawdown:,.0f}")
        print(f"  Avg Win:          ${best.avg_win:,.0f}")
        print(f"  Avg Loss:         ${best.avg_loss:,.0f}")
        print(f"  Sessions active:  {best.sessions_with_trades}/{len(next(iter({})) if not True else 328)}")
    else:
        print("\nNo profitable configurations found with 20+ trades.")

    # Summary stats
    profitable_count = len([r for r in viable if r.total_pnl > 0])
    print(f"\n{'=' * 100}")
    print(f"SWEEP SUMMARY: {len(viable)} viable configs, {profitable_count} profitable ({profitable_count / len(viable) * 100:.0f}%)")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    results = run_sweep()
    print_results(results)
