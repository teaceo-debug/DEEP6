"""Round 2 analysis: time-of-day filters and signal category attribution.

Uses CapturingRegistry to intercept signal metadata from scan_signals()
without duplicating the scan loop.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import NamedTuple
import time as _time

from deep6v2.backtest import param_sweep
from deep6v2.backtest.param_sweep import DEFAULT_CSV, ScoredBar, SweepParams
from deep6v2.types.signal import (
    SIGNAL_TO_CATEGORY,
    Direction,
    SignalCategory,
    SignalId,
    SignalResult,
)

# ---- Best R1 config ----
BEST_PARAMS = SweepParams(
    score_min=72, stop_mult=3.0, rr_ratio=3.0, cooldown=10, min_signals=1,
)

# ---- Hour blocks (bar_index ranges, NOT clock hours) ----
#   bar_index = minutes since 9:30 RTH open
HOUR_BLOCKS: list[tuple[int, int, int]] = [
    (9,  0,   59),
    (10, 60,  119),
    (11, 120, 179),
    (12, 180, 239),
    (13, 240, 299),
    (14, 300, 359),
    (15, 360, 389),
]

# ---- Time windows ----
WINDOWS: list[tuple[str, tuple[tuple[int, int], ...]]] = [
    ("IB only",        ((0, 59),)),
    ("Morning",        ((0, 120),)),
    ("Afternoon",      ((211, 389),)),
    ("Power hour",     ((330, 389),)),
    ("IB + Afternoon", ((0, 59), (211, 389))),
]


# ---- Data types ----

@dataclass(frozen=True, slots=True)
class BarSignalMeta:
    signal_ids: tuple[SignalId, ...]
    categories: frozenset[SignalCategory]


EMPTY_META = BarSignalMeta(signal_ids=(), categories=frozenset())


@dataclass(frozen=True, slots=True)
class TradeMeta:
    session_date: date
    entry_bar_index: int
    setup_bar_index: int
    entry_price: float
    exit_price: float
    direction: Direction
    pnl: float
    exit_reason: str
    score: float
    signal_ids: tuple[SignalId, ...]
    categories: frozenset[SignalCategory]


class StatLine(NamedTuple):
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    profit_factor: float
    sharpe: float
    avg_win: float
    avg_loss: float


# ---- Registry wrapper to capture per-bar categories ----

class CapturingRegistry:
    """Wraps DetectorRegistry to intercept evaluate_bar results."""

    def __init__(self, inner: object, store: dict[tuple[date, int], BarSignalMeta]) -> None:
        self._inner = inner
        self._store = store

    def evaluate_bar(self, bar: object, ctx: object) -> list[SignalResult]:
        signals = self._inner.evaluate_bar(bar, ctx)
        sig_ids = tuple(s.signal_id for s in signals)
        cats = frozenset(
            c for c in (SIGNAL_TO_CATEGORY.get(s.signal_id) for s in signals)
            if c is not None
        )
        self._store[(bar.timestamp.date(), bar.bar_index)] = BarSignalMeta(
            signal_ids=sig_ids, categories=cats,
        )
        return signals

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def scan_sessions_with_metadata(
    csv_path: Path,
) -> tuple[dict[date, list[ScoredBar]], dict[tuple[date, int], BarSignalMeta]]:
    """Run scan_signals with category capture via monkey-patched registry."""
    metadata: dict[tuple[date, int], BarSignalMeta] = {}
    original_descriptor = param_sweep.DetectorRegistry.__dict__["create_default"]
    original_fn = original_descriptor.__func__

    def patched_create_default(cls: object, config: object = None) -> CapturingRegistry:
        inner = original_fn(cls, config)
        return CapturingRegistry(inner=inner, store=metadata)

    param_sweep.DetectorRegistry.create_default = classmethod(patched_create_default)
    try:
        sessions = param_sweep.scan_signals(csv_path)
    finally:
        param_sweep.DetectorRegistry.create_default = original_descriptor
    return sessions, metadata


# ---- Helpers ----

def bar_in_ranges(bar_index: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(lo <= bar_index <= hi for lo, hi in ranges)


def calc_stats(trades: list[TradeMeta]) -> StatLine:
    pnl_list = [t.pnl for t in trades]
    if not pnl_list:
        return StatLine(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p <= 0]
    total = sum(pnl_list)
    mean = total / len(pnl_list)
    std = (
        (sum((p - mean) ** 2 for p in pnl_list) / len(pnl_list)) ** 0.5
        if len(pnl_list) > 1 else 0.0
    )
    pf = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0.0
    sharpe = (mean / std * (252 ** 0.5)) if std > 0 else 0.0

    return StatLine(
        trades=len(pnl_list),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / len(pnl_list) * 100.0,
        total_pnl=total,
        avg_pnl=mean,
        profit_factor=pf,
        sharpe=sharpe,
        avg_win=sum(wins) / len(wins) if wins else 0.0,
        avg_loss=sum(losses) / len(losses) if losses else 0.0,
    )


# ---- Trade simulation with metadata tracking ----

def simulate_trades_with_metadata(
    sessions: dict[date, list[ScoredBar]],
    params: SweepParams,
    metadata: dict[tuple[date, int], BarSignalMeta],
    *,
    allowed_ranges: tuple[tuple[int, int], ...] | None = None,
) -> list[TradeMeta]:
    """Simulate trades tracking entry details and signal categories.

    If allowed_ranges is set, signals are only armed when the signal bar
    falls within one of the (lo, hi) inclusive ranges.
    """
    DPP = 20.0
    trades: list[TradeMeta] = []

    for session_date, bars in sessions.items():
        in_trade = False
        entry_price = 0.0
        entry_dir = Direction.NEUTRAL
        stop_px = 0.0
        target_px = 0.0
        entry_bar_i = 0
        armed = False
        armed_dir = Direction.NEUTRAL
        armed_score = 0.0
        armed_meta = EMPTY_META
        armed_setup_bar = -1
        bars_since_trade = 999

        for i, sb in enumerate(bars):
            bar = sb.bar

            # ---- Exit check ----
            if in_trade:
                exit_px: float | None = None
                reason = ""
                if entry_dir == Direction.BULLISH:
                    if bar.low <= stop_px:
                        exit_px, reason = stop_px, "stop"
                    elif bar.high >= target_px:
                        exit_px, reason = target_px, "target"
                else:
                    if bar.high >= stop_px:
                        exit_px, reason = stop_px, "stop"
                    elif bar.low <= target_px:
                        exit_px, reason = target_px, "target"

                if exit_px is not None:
                    pnl = (exit_px - entry_price) * DPP
                    if entry_dir == Direction.BEARISH:
                        pnl *= -1.0
                    trades.append(TradeMeta(
                        session_date=session_date,
                        entry_bar_index=entry_bar_i,
                        setup_bar_index=armed_setup_bar,
                        entry_price=entry_price,
                        exit_price=exit_px,
                        direction=entry_dir,
                        pnl=pnl,
                        exit_reason=reason,
                        score=armed_score,
                        signal_ids=armed_meta.signal_ids,
                        categories=armed_meta.categories,
                    ))
                    in_trade = False
                    bars_since_trade = 0
                    continue

                if i == len(bars) - 1:
                    pnl = (bar.close - entry_price) * DPP
                    if entry_dir == Direction.BEARISH:
                        pnl *= -1.0
                    trades.append(TradeMeta(
                        session_date=session_date,
                        entry_bar_index=entry_bar_i,
                        setup_bar_index=armed_setup_bar,
                        entry_price=entry_price,
                        exit_price=bar.close,
                        direction=entry_dir,
                        pnl=pnl,
                        exit_reason="session_close",
                        score=armed_score,
                        signal_ids=armed_meta.signal_ids,
                        categories=armed_meta.categories,
                    ))
                    in_trade = False
                continue

            bars_since_trade += 1

            # ---- D-20 confirmation (enter on bar after signal) ----
            if armed:
                armed = False
                entry_ok = (
                    allowed_ranges is None
                    or bar_in_ranges(bar.bar_index, allowed_ranges)
                )
                if not in_trade and bars_since_trade >= params.cooldown and entry_ok:
                    in_trade = True
                    entry_price = bar.open
                    entry_dir = armed_dir
                    entry_bar_i = bar.bar_index

                    recent = bars[max(0, i - 14):i]
                    atr = (
                        sum(b.bar.high - b.bar.low for b in recent) / len(recent)
                        if recent else 5.0
                    )
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

            # ---- Entry criteria ----
            setup_ok = (
                allowed_ranges is None
                or bar_in_ranges(bar.bar_index, allowed_ranges)
            )
            if (
                not in_trade
                and setup_ok
                and sb.score >= params.score_min
                and sb.direction in (Direction.BULLISH, Direction.BEARISH)
                and sb.n_signals >= params.min_signals
                and bars_since_trade >= params.cooldown
            ):
                armed = True
                armed_dir = sb.direction
                armed_score = sb.score
                armed_meta = metadata.get(
                    (session_date, bar.bar_index), EMPTY_META,
                )
                armed_setup_bar = bar.bar_index

    return trades


# ---- Reporting ----

def _header(title: str) -> None:
    print("=" * 100)
    print(title)
    print("=" * 100)


def _fmt_stat_row(
    label: str, s: StatLine, *, label_w: int = 20, show_sharpe: bool = False,
) -> str:
    base = (
        f"{label:<{label_w}} {s.trades:>6} {s.wins:>5} "
        f"{s.win_rate:>6.1f}% ${s.total_pnl:>10,.0f} "
        f"${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f}"
    )
    if show_sharpe:
        base += f" {s.sharpe:>7.2f}"
    return base


# ---- Analysis A: Time-of-Day Performance ----

def analysis_a(
    sessions: dict[date, list[ScoredBar]],
    metadata: dict[tuple[date, int], BarSignalMeta],
) -> None:
    _header("ANALYSIS A: TIME-OF-DAY PERFORMANCE")
    print(
        f"Config: score_min={BEST_PARAMS.score_min}, "
        f"stop={BEST_PARAMS.stop_mult}x, rr={BEST_PARAMS.rr_ratio}, "
        f"cd={BEST_PARAMS.cooldown}, min_sig={BEST_PARAMS.min_signals}"
    )

    # Full unrestricted simulation
    all_trades = simulate_trades_with_metadata(sessions, BEST_PARAMS, metadata)
    base = calc_stats(all_trades)
    print(
        f"\nBaseline (all hours): {base.trades} trades, "
        f"WR {base.win_rate:.1f}%, PnL ${base.total_pnl:,.0f}, "
        f"PF {base.profit_factor:.2f}, Sharpe {base.sharpe:.2f}"
    )

    # ---- Per-hour breakdown (by bar_index blocks) ----
    print("\n--- Per-Hour Breakdown (grouped by bar_index) ---")
    hdr = (
        f"{'Hour':<8} {'Bars':<12} {'Trades':>6} {'Wins':>5} "
        f"{'WR%':>7} {'Total PnL':>12} {'Avg PnL':>10} {'PF':>6}"
    )
    print(hdr)
    print("-" * len(hdr))

    for hour, lo, hi in HOUR_BLOCKS:
        ht = [t for t in all_trades if lo <= t.entry_bar_index <= hi]
        s = calc_stats(ht)
        print(
            f"{hour}:xx    {lo}-{hi:<6} "
            f"{s.trades:>6} {s.wins:>5} {s.win_rate:>6.1f}% "
            f"${s.total_pnl:>10,.0f} ${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f}"
        )

    # ---- Time window configs (re-run sim with restrictions) ----
    print("\n--- Time Window Configs ---")
    whdr = (
        f"{'Window':<20} {'Trades':>6} {'Wins':>5} "
        f"{'WR%':>7} {'Total PnL':>12} {'Avg PnL':>10} {'PF':>6} {'Sharpe':>7}"
    )
    print(whdr)
    print("-" * len(whdr))

    # Baseline row
    print(
        f"{'Full session':<20} {base.trades:>6} {base.wins:>5} "
        f"{base.win_rate:>6.1f}% ${base.total_pnl:>10,.0f} "
        f"${base.avg_pnl:>8,.0f} {base.profit_factor:>5.2f} {base.sharpe:>7.2f}"
    )

    for name, ranges in WINDOWS:
        wt = simulate_trades_with_metadata(
            sessions, BEST_PARAMS, metadata, allowed_ranges=ranges,
        )
        s = calc_stats(wt)
        print(
            f"{name:<20} {s.trades:>6} {s.wins:>5} "
            f"{s.win_rate:>6.1f}% ${s.total_pnl:>10,.0f} "
            f"${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f} {s.sharpe:>7.2f}"
        )


# ---- Analysis B: Signal Category Attribution ----

def _presence_block(
    label: str,
    present: list[TradeMeta],
    absent: list[TradeMeta],
) -> None:
    sp = calc_stats(present)
    sa = calc_stats(absent)
    edge = sp.avg_pnl - sa.avg_pnl if sa.trades > 0 else sp.avg_pnl
    print(f"  {label}")
    print(
        f"    WITH:    {sp.trades:>4} trades  "
        f"WR {sp.win_rate:>5.1f}%  "
        f"PnL ${sp.total_pnl:>9,.0f}  "
        f"Avg ${sp.avg_pnl:>7,.0f}  "
        f"PF {sp.profit_factor:>5.2f}"
    )
    print(
        f"    WITHOUT: {sa.trades:>4} trades  "
        f"WR {sa.win_rate:>5.1f}%  "
        f"PnL ${sa.total_pnl:>9,.0f}  "
        f"Avg ${sa.avg_pnl:>7,.0f}  "
        f"PF {sa.profit_factor:>5.2f}"
    )
    print(f"    EDGE:    ${edge:>7,.0f} avg PnL difference")


def analysis_b(
    sessions: dict[date, list[ScoredBar]],
    metadata: dict[tuple[date, int], BarSignalMeta],
) -> None:
    _header("ANALYSIS B: SIGNAL CATEGORY ATTRIBUTION")

    all_trades = simulate_trades_with_metadata(sessions, BEST_PARAMS, metadata)
    if not all_trades:
        print("No trades to analyze.")
        return

    base = calc_stats(all_trades)
    print(
        f"\nTotal trades: {base.trades}, WR {base.win_rate:.1f}%, "
        f"PnL ${base.total_pnl:,.0f}"
    )

    # ---- Per-category presence vs absence ----
    print("\n--- Category Presence vs Absence ---")
    for cat in [
        SignalCategory.ABSORPTION,
        SignalCategory.EXHAUSTION,
        SignalCategory.IMBALANCE,
        SignalCategory.DELTA,
        SignalCategory.VOLUME_PROFILE,
        SignalCategory.AUCTION,
        SignalCategory.TRAPPED,
    ]:
        _presence_block(
            cat.value.upper(),
            [t for t in all_trades if cat in t.categories],
            [t for t in all_trades if cat not in t.categories],
        )
        print()

    # ---- Category count impact ----
    print("--- Category Count Impact ---")
    count_hdr = (
        f"{'Group':<12} {'Trades':>6} {'Wins':>5} "
        f"{'WR%':>7} {'Total PnL':>12} {'Avg PnL':>10} {'PF':>6}"
    )
    print(count_hdr)
    print("-" * len(count_hdr))

    for label, subset in [
        ("4+ cats", [t for t in all_trades if len(t.categories) >= 4]),
        ("2-3 cats", [t for t in all_trades if 2 <= len(t.categories) <= 3]),
        ("1 cat", [t for t in all_trades if len(t.categories) == 1]),
        ("0 cats", [t for t in all_trades if len(t.categories) == 0]),
    ]:
        s = calc_stats(subset)
        print(
            f"{label:<12} {s.trades:>6} {s.wins:>5} "
            f"{s.win_rate:>6.1f}% ${s.total_pnl:>10,.0f} "
            f"${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f}"
        )

    # ---- Best category combinations ----
    print("\n--- Top 15 Category Combinations (by total PnL, 3+ trades) ---")
    combo_hdr = (
        f"{'Combination':<48} {'Trades':>6} {'WR%':>7} "
        f"{'Total PnL':>12} {'Avg PnL':>10} {'PF':>6}"
    )
    print(combo_hdr)
    print("-" * len(combo_hdr))

    combos: dict[tuple[str, ...], list[TradeMeta]] = defaultdict(list)
    for t in all_trades:
        key = tuple(sorted(c.value for c in t.categories))
        combos[key].append(t)

    ranked = sorted(
        ((k, v) for k, v in combos.items() if len(v) >= 3),
        key=lambda x: sum(t.pnl for t in x[1]),
        reverse=True,
    )

    for combo, ctrades in ranked[:15]:
        s = calc_stats(ctrades)
        combo_str = " + ".join(combo) if combo else "(none)"
        if len(combo_str) > 46:
            combo_str = combo_str[:43] + "..."
        print(
            f"{combo_str:<48} {s.trades:>6} {s.win_rate:>6.1f}% "
            f"${s.total_pnl:>10,.0f} ${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f}"
        )

    # ---- Worst combinations ----
    if len(ranked) > 10:
        print("\n--- Bottom 10 Category Combinations (worst PnL, 3+ trades) ---")
        print(combo_hdr)
        print("-" * len(combo_hdr))

        for combo, ctrades in ranked[-10:]:
            s = calc_stats(ctrades)
            combo_str = " + ".join(combo) if combo else "(none)"
            if len(combo_str) > 46:
                combo_str = combo_str[:43] + "..."
            print(
                f"{combo_str:<48} {s.trades:>6} {s.win_rate:>6.1f}% "
                f"${s.total_pnl:>10,.0f} ${s.avg_pnl:>8,.0f} {s.profit_factor:>5.2f}"
            )


# ---- Main ----

def main(csv_path: Path = DEFAULT_CSV) -> None:
    print("Round 2: Time-of-Day + Category Attribution Analysis")
    print(
        f"Config: score_min={BEST_PARAMS.score_min}, "
        f"stop={BEST_PARAMS.stop_mult}x, rr={BEST_PARAMS.rr_ratio}, "
        f"cd={BEST_PARAMS.cooldown}"
    )
    print()

    t0 = _time.time()
    print("Scanning signals with category capture...")
    sessions, metadata = scan_sessions_with_metadata(csv_path)
    total_bars = sum(len(b) for b in sessions.values())
    scan_t = _time.time() - t0
    print(f"  {total_bars:,} bars across {len(sessions)} sessions in {scan_t:.1f}s")
    print()

    t1 = _time.time()
    analysis_a(sessions, metadata)
    print(f"\n  [Analysis A: {_time.time() - t1:.1f}s]")

    print()
    t2 = _time.time()
    analysis_b(sessions, metadata)
    print(f"\n  [Analysis B: {_time.time() - t2:.1f}s]")

    print(f"\nTotal runtime: {_time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
