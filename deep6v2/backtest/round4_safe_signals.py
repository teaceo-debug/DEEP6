"""Round 4: re-run backtest with ONLY OHLCV-valid signals.

Oracle audit found 26/52 signals produce BROKEN/misleading results on synthetic
OHLCV data. This round filters to the 16 validated signals and re-sweeps with
lower score thresholds (since fewer signals = lower raw scores).
"""

from __future__ import annotations

import itertools
import time
from collections import deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from deep6v2.backtest.ohlcv_synthesizer import synthesize_footprint
from deep6v2.backtest.param_sweep import (
    DEFAULT_CSV,
    ScoredBar,
    SweepParams,
    SweepResult,
    simulate_trades,
)
from deep6v2.scoring.entry_gate import EntryGate
from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.signals.registry import DetectorRegistry
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.scoring import SignalTier
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import (
    Direction,
    SIGNAL_TO_CATEGORY,
    SignalCategory,
    SignalId,
    SignalResult,
)

# ── OHLCV-safe signal set (Oracle audit validated) ───────────────

OHLCV_SAFE_SIGNALS: frozenset[SignalId] = frozenset({
    # Absorption (1/4 valid)
    SignalId.ABS_04,      # Effort vs Result -- HIGH
    # Exhaustion (1/6 valid)
    SignalId.EXH_04,      # Fat Print -- MODERATE
    # Delta (7/11 valid)
    SignalId.DELT_01,     # Rise/Drop -- MODERATE
    SignalId.DELT_03,     # Delta Reversal -- MODERATE
    SignalId.DELT_05,     # CVD Zero Flip -- MODERATE
    SignalId.DELT_06,     # Delta Trap -- MODERATE
    SignalId.DELT_08,     # Slingshot -- MODERATE
    SignalId.DELT_09,     # Session Extreme -- MODERATE
    SignalId.DELT_11,     # Delta Velocity -- MODERATE
    # Auction (2/5 valid)
    SignalId.AUCT_03,     # Poor High/Low -- MODERATE
    SignalId.AUCT_05,     # Market Sweep -- MODERATE
    # Volume Profile (5/6 valid)
    SignalId.VOLP_01,     # Volume Sequencing -- HIGH
    SignalId.VOLP_02,     # Volume Bubble -- HIGH
    SignalId.VOLP_03,     # Volume Surge -- HIGH
    SignalId.VOLP_04,     # POC Momentum -- MODERATE
    SignalId.VOLP_05,     # Delta Velocity Spike -- MODERATE
    # Imbalance: ALL disabled (IMB_01-09 manufactures artifacts)
    # Trapped: not in safe set
    # ENG_*: not in safe set
})

DISABLED_SIGNALS: frozenset[SignalId] = frozenset({
    SignalId.ABS_01, SignalId.ABS_02, SignalId.ABS_03,
    SignalId.EXH_01, SignalId.EXH_02, SignalId.EXH_03, SignalId.EXH_05, SignalId.EXH_06,
    SignalId.IMB_01, SignalId.IMB_02, SignalId.IMB_03, SignalId.IMB_04, SignalId.IMB_05,
    SignalId.IMB_06, SignalId.IMB_07, SignalId.IMB_08, SignalId.IMB_09,
    SignalId.DELT_02, SignalId.DELT_04, SignalId.DELT_07, SignalId.DELT_10,
    SignalId.AUCT_01, SignalId.AUCT_02, SignalId.AUCT_04,
    SignalId.VOLP_06,
})


def filter_safe_signals(signals: list[SignalResult]) -> list[SignalResult]:
    """Keep only OHLCV-validated signals."""
    return [s for s in signals if s.signal_id in OHLCV_SAFE_SIGNALS]


# ── Phase 1: Signal Scan with filtering ──────────────────────────

def scan_signals_safe(csv_path: Path) -> tuple[dict[date, list[ScoredBar]], dict[str, int]]:
    """Run all detectors but filter to safe set before scoring.

    Returns (sessions, stats) where stats tracks signal firing counts.
    """
    registry = DetectorRegistry.create_default()
    scorer = ConfluenceScorer()
    gate = EntryGate()

    df = pd.read_csv(
        csv_path,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
        parse_dates=["ts_event"],
    )
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
    df["ts_et"] = df["ts_event"].dt.tz_convert("America/New_York")
    minutes = df["ts_et"].dt.hour * 60 + df["ts_et"].dt.minute
    df = df.loc[(minutes >= 570) & (minutes < 960)].copy()
    df["session_date"] = df["ts_et"].dt.date

    sessions: dict[date, list[ScoredBar]] = {}
    total_bars = 0
    total_all_signals = 0
    total_safe_signals = 0
    bars_with_all_signals = 0
    bars_with_safe_signals = 0
    signal_id_counts_all: dict[str, int] = {}
    signal_id_counts_safe: dict[str, int] = {}

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

            # Detect ALL signals
            try:
                all_signals = registry.evaluate_bar(bar, ctx)
            except Exception:
                all_signals = []

            # *** ROUND 4 FILTER: keep only OHLCV-safe signals ***
            safe_signals = filter_safe_signals(all_signals)

            # Track stats
            if all_signals:
                bars_with_all_signals += 1
                total_all_signals += len(all_signals)
                for s in all_signals:
                    signal_id_counts_all[s.signal_id.value] = signal_id_counts_all.get(s.signal_id.value, 0) + 1
            if safe_signals:
                bars_with_safe_signals += 1
                total_safe_signals += len(safe_signals)
                for s in safe_signals:
                    signal_id_counts_safe[s.signal_id.value] = signal_id_counts_safe.get(s.signal_id.value, 0) + 1

            # Score using ONLY safe signals
            if safe_signals:
                result = scorer.score(safe_signals, bar.bar_index)
                decision = gate.evaluate(result, bar, ctx)
                cats: set[SignalCategory] = set()
                for s in safe_signals:
                    cat = SIGNAL_TO_CATEGORY.get(s.signal_id)
                    if cat is not None:
                        cats.add(cat)
                bars.append(ScoredBar(
                    bar=bar, score=result.final_score,
                    tier=result.tier.value, direction=decision.direction,
                    eligible=decision.eligible, n_signals=len(safe_signals),
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
                session_profile[price] = (
                    session_profile.get(price, 0)
                    + bar.bid_volumes.get(price, 0)
                    + bar.ask_volumes.get(price, 0)
                )
            if session_profile:
                poc_p = max(session_profile, key=session_profile.get)  # type: ignore[arg-type]
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

    stats = {
        "total_bars": total_bars,
        "bars_with_all_signals": bars_with_all_signals,
        "bars_with_safe_signals": bars_with_safe_signals,
        "total_all_signals": total_all_signals,
        "total_safe_signals": total_safe_signals,
        "avg_all_per_bar": total_all_signals / total_bars if total_bars else 0.0,
        "avg_safe_per_bar": total_safe_signals / total_bars if total_bars else 0.0,
        "avg_all_per_signal_bar": (
            total_all_signals / bars_with_all_signals if bars_with_all_signals else 0.0
        ),
        "avg_safe_per_signal_bar": (
            total_safe_signals / bars_with_safe_signals if bars_with_safe_signals else 0.0
        ),
    }

    return sessions, stats


# ── Phase 2: Sweep (reuses simulate_trades from param_sweep) ─────

def run_sweep(csv_path: Path = DEFAULT_CSV) -> None:
    print("=" * 100)
    print("ROUND 4: OHLCV-SAFE SIGNALS ONLY (16/52 signals)")
    print("=" * 100)

    print("\nPhase 1: Scanning signals (all detectors, filtering to safe set)...")
    t0 = time.time()
    sessions, stats = scan_signals_safe(csv_path)
    scan_time = time.time() - t0
    n_sessions = len(sessions)
    total_bars = sum(len(b) for b in sessions.values())
    print(f"  Scanned {total_bars:,} bars across {n_sessions} sessions in {scan_time:.1f}s")

    # ── Signal firing stats ──────────────────────────────────────
    print(f"\n{'=' * 100}")
    print("SIGNAL FIRING STATS")
    print(f"{'=' * 100}")
    print(f"  Total bars:                {stats['total_bars']:>10,}")
    print(f"  Bars w/ ANY signal (all):  {stats['bars_with_all_signals']:>10,}")
    print(f"  Bars w/ ANY signal (safe): {stats['bars_with_safe_signals']:>10,}")
    print(f"  Total signals fired (all): {stats['total_all_signals']:>10,}")
    print(f"  Total signals fired (safe):{stats['total_safe_signals']:>10,}")
    avg_all = stats['avg_all_per_bar']
    avg_safe = stats['avg_safe_per_bar']
    print(f"  Avg signals/bar (all):     {avg_all:>10.3f}")
    print(f"  Avg signals/bar (safe):    {avg_safe:>10.3f}")
    if avg_all > 0:
        pct = avg_safe / avg_all * 100
        print(f"  Safe/All ratio:            {pct:>9.1f}%")

    # ── Parameter grid (lower thresholds for fewer signals) ──────
    score_mins = [50, 55, 60, 65, 70, 75, 80]
    stop_mults = [1.5, 2.0, 2.5, 3.0, 4.0]
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
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(combos)} done...")

    sweep_time = time.time() - t1
    print(f"  Sweep completed in {sweep_time:.1f}s")

    # ── Results ──────────────────────────────────────────────────
    print_results(results, n_sessions)
    print_round1_comparison(results)


def print_results(results: list[SweepResult], n_sessions: int) -> None:
    viable = [r for r in results if r.trades >= 20]
    if not viable:
        viable = [r for r in results if r.trades >= 5]
    if not viable:
        print("\nNo configurations produced enough trades.")
        return

    by_pnl = sorted(viable, key=lambda r: r.total_pnl, reverse=True)
    by_pf = sorted(viable, key=lambda r: r.profit_factor, reverse=True)
    by_sharpe = sorted(viable, key=lambda r: r.sharpe, reverse=True)

    header = f"{'Config':<40} {'Trades':>6} {'WR%':>6} {'PnL':>10} {'PF':>6} {'Sharpe':>7} {'MaxDD':>10} {'AvgW':>8} {'AvgL':>8}"

    print(f"\n{'=' * 100}")
    print("TOP 10 BY TOTAL P&L (min 20 trades)")
    print(f"{'=' * 100}")
    print(header)
    print("-" * 100)
    for r in by_pnl[:10]:
        _print_row(r)

    print(f"\n{'=' * 100}")
    print("TOP 10 BY PROFIT FACTOR (min 20 trades)")
    print(f"{'=' * 100}")
    print(header)
    print("-" * 100)
    for r in by_pf[:10]:
        _print_row(r)

    print(f"\n{'=' * 100}")
    print("TOP 10 BY SHARPE RATIO (min 20 trades)")
    print(f"{'=' * 100}")
    print(header)
    print("-" * 100)
    for r in by_sharpe[:10]:
        _print_row(r)

    # Best overall
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
        print(f"  ---")
        print(f"  Trades:           {best.trades}")
        print(f"  Win Rate:         {best.win_rate:.1f}%")
        print(f"  Total P&L:        ${best.total_pnl:,.0f}")
        print(f"  Profit Factor:    {best.profit_factor:.2f}")
        print(f"  Sharpe (ann):     {best.sharpe:.2f}")
        print(f"  Max Drawdown:     ${best.max_drawdown:,.0f}")
        print(f"  Avg Win:          ${best.avg_win:,.0f}")
        print(f"  Avg Loss:         ${best.avg_loss:,.0f}")
        print(f"  Sessions active:  {best.sessions_with_trades}/{n_sessions}")
    else:
        print("\nNo profitable configurations found with 20+ trades.")

    # Summary
    profitable_count = len([r for r in viable if r.total_pnl > 0])
    total_viable = len(viable)
    pct = profitable_count / total_viable * 100 if total_viable else 0
    print(f"\n{'=' * 100}")
    print(f"SWEEP SUMMARY: {total_viable} viable configs, {profitable_count} profitable ({pct:.0f}%)")
    print(f"{'=' * 100}")


def print_round1_comparison(results: list[SweepResult]) -> None:
    """Compare Round 4 best to Round 1 best config."""
    # Round 1 best was: sc72 st3.0 rr3.0 cd10 ms1 (from param_sweep.py)
    r1_best_label = "sc72 st3.0 rr3.0 cd10 ms1"

    r4_viable = [r for r in results if r.trades >= 20 and r.profit_factor > 1.0]
    if not r4_viable:
        r4_viable = [r for r in results if r.trades >= 5]
    if not r4_viable:
        print("\nNo Round 4 configs to compare.")
        return

    r4_best = max(r4_viable, key=lambda r: r.sharpe)
    r4p = r4_best.params

    print(f"\n{'=' * 100}")
    print("ROUND 1 vs ROUND 4 COMPARISON")
    print(f"{'=' * 100}")
    print(f"  {'Metric':<25} {'Round 1 (all 52 signals)':>25} {'Round 4 (16 safe signals)':>25}")
    print(f"  {'-' * 75}")
    print(f"  {'Signals available':<25} {'52':>25} {'16':>25}")
    print(f"  {'Config':<25} {r1_best_label:>25} {f'sc{r4p.score_min:.0f} st{r4p.stop_mult:.1f} rr{r4p.rr_ratio:.1f} cd{r4p.cooldown} ms{r4p.min_signals}':>25}")
    print(f"  {'Trades':<25} {'(run Round 1 to compare)':>25} {r4_best.trades:>25}")
    print(f"  {'Win Rate':<25} {'':>25} {f'{r4_best.win_rate:.1f}%':>25}")
    print(f"  {'Total P&L':<25} {'':>25} {f'${r4_best.total_pnl:,.0f}':>25}")
    print(f"  {'Profit Factor':<25} {'':>25} {f'{r4_best.profit_factor:.2f}':>25}")
    print(f"  {'Sharpe (ann)':<25} {'':>25} {f'{r4_best.sharpe:.2f}':>25}")
    print(f"  {'Max Drawdown':<25} {'':>25} {f'${r4_best.max_drawdown:,.0f}':>25}")
    print(f"\n  Note: Run Round 1 (param_sweep.py) and compare side-by-side.")
    print(f"  Key question: Does removing 36 broken signals IMPROVE or DEGRADE results?")
    print(f"  If Round 4 is competitive with fewer signals, the broken signals were noise.")


def _print_row(r: SweepResult) -> None:
    p = r.params
    label = f"sc{p.score_min:.0f} st{p.stop_mult:.1f} rr{p.rr_ratio:.1f} cd{p.cooldown} ms{p.min_signals}"
    print(
        f"{label:<40} {r.trades:>6} {r.win_rate:>5.1f}% "
        f"${r.total_pnl:>9,.0f} {r.profit_factor:>5.2f} {r.sharpe:>7.2f} "
        f"${r.max_drawdown:>9,.0f} ${r.avg_win:>7,.0f} ${r.avg_loss:>7,.0f}"
    )


if __name__ == "__main__":
    run_sweep()
