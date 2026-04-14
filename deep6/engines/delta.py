"""Delta signal detection — 11 variants.

Delta measures the difference between buying and selling pressure.
These signals detect when delta behavior diverges from price action
or reaches extremes that predict reversals.

Variants (per DELT-01..11):
  1.  Rise/Drop:       Delta classified per bar
  2.  Tail:            Bar delta at 95%+ of its extreme
  3.  Reversal:        Bar-level delta/direction mismatch (approximation — no tick-level intrabar)
  4.  Divergence:      Price new high/low but delta fails to confirm (highest alpha)
  5.  Flip:            Sign change in cumulative delta
  6.  Trap:            Aggressive delta + price reversal
  7.  Sweep:           Rapid delta across multiple levels
  8.  Slingshot:       Compressed then explosive delta (72-78% win rate)
  9.  At Min/Max:      Delta at session extreme
  10. CVD Multi-Bar:   Linear regression divergence over N bars
  11. Velocity:        Rate of change of CVD
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from deep6.engines.signal_config import DeltaConfig
from deep6.state.footprint import FootprintBar


class DeltaType(Enum):
    RISE = auto()
    DROP = auto()
    TAIL = auto()
    REVERSAL = auto()
    DIVERGENCE = auto()
    FLIP = auto()
    TRAP = auto()
    SWEEP = auto()
    SLINGSHOT = auto()
    AT_MIN = auto()
    AT_MAX = auto()
    CVD_DIVERGENCE = auto()
    VELOCITY = auto()


@dataclass
class DeltaSignal:
    delta_type: DeltaType
    direction: int
    strength: float
    value: float        # the delta or CVD value
    detail: str


@dataclass
class DeltaResult:
    """Bundled engine output: the emitted signals plus the bar-quality scalar.

    delta_quality is orthogonal to VPIN — applies to delta-family signals ONLY
    (bits 21-32). Consumers MUST check DELTA_FAMILY_BITS before multiplying.
    Added in Plan 12-02 alongside the DELT_TAIL intrabar-extreme fix.
    """
    signals: list["DeltaSignal"]
    delta_quality: float = 1.0


# Whitelist of SignalFlags bit positions that may consume delta_quality.
# Covers DELT-01..DELT-11 (bits 21-31) + CVD VELOCITY (bit 32 reserved in plan).
# DO NOT extend to absorption/exhaustion/imbalance — those have their own quality
# domain. Stacking delta_quality across unrelated signals is a P0 bug.
DELTA_FAMILY_BITS: frozenset[int] = frozenset({21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32})


class DeltaEngine:
    """Stateful delta engine tracking CVD, session extremes, and history."""

    def __init__(self, config: DeltaConfig = DeltaConfig()):
        self.config = config
        self.cvd_history: deque[float] = deque(maxlen=config.lookback)
        self.price_history: deque[float] = deque(maxlen=config.lookback)
        self.delta_history: deque[float] = deque(maxlen=config.lookback)
        self.session_cvd_min: float = 0.0
        self.session_cvd_max: float = 0.0
        self.bar_count: int = 0

    def reset(self) -> None:
        self.cvd_history.clear()
        self.price_history.clear()
        self.delta_history.clear()
        self.session_cvd_min = 0.0
        self.session_cvd_max = 0.0
        self.bar_count = 0

    def process_with_quality(self, bar: FootprintBar) -> DeltaResult:
        """Process bar and return DeltaResult with delta_quality scalar.

        Plan 12-02: non-breaking alternative to process() for consumers that need
        the intrabar delta-quality scalar (1.15 closing-at-extreme / 0.7 faded / linear).
        The scalar applies ONLY to delta-family bits (see DELTA_FAMILY_BITS).

        Existing process() callers are unchanged — they receive just the signal list.
        """
        signals = self.process(bar)
        return DeltaResult(signals=signals, delta_quality=bar.delta_quality_scalar())

    def process(self, bar: FootprintBar) -> list[DeltaSignal]:
        signals: list[DeltaSignal] = []

        if bar.total_vol == 0:
            return signals

        delta = bar.bar_delta
        cvd = bar.cvd
        cfg = self.config
        self.bar_count += 1

        # Update histories
        self.delta_history.append(delta)
        self.cvd_history.append(cvd)
        self.price_history.append(bar.close)

        # Update session extremes
        self.session_cvd_min = min(self.session_cvd_min, cvd)
        self.session_cvd_max = max(self.session_cvd_max, cvd)

        # --- 1. RISE/DROP (DELT-01) ---
        if delta > 0:
            signals.append(DeltaSignal(
                DeltaType.RISE, +1, min(delta / bar.total_vol, 1.0), delta,
                f"DELTA RISE: {delta:+d} ({delta/bar.total_vol*100:.0f}% of vol)",
            ))
        elif delta < 0:
            signals.append(DeltaSignal(
                DeltaType.DROP, -1, min(abs(delta) / bar.total_vol, 1.0), delta,
                f"DELTA DROP: {delta:+d} ({abs(delta)/bar.total_vol*100:.0f}% of vol)",
            ))

        # --- 2. TAIL (DELT-02) — Plan 12-02: TRUE intrabar extreme (no more bar-geometry proxy) ---
        # Fires iff bar closes within tail_threshold (default 0.95) of its intrabar max_delta
        # (positive) or min_delta (negative). Consumes FootprintBar.max_delta / min_delta
        # which are now updated live by add_trade() (Plan 12-02 Task 1).
        #
        # FOOTGUN 3 guard: if the matching extreme is 0 (e.g., uninstrumented legacy bar or
        # trivial case where first-ever trade sets the extreme), treat it as equal to
        # bar_delta — conservative closing-at-trivial-extreme ratio of 1.0.
        if delta > 0:
            extreme = bar.max_delta if bar.max_delta > 0 else delta
            tail_ratio = delta / extreme if extreme > 0 else 0.0
            if tail_ratio >= cfg.tail_threshold:
                signals.append(DeltaSignal(
                    DeltaType.TAIL, +1, tail_ratio, delta,
                    f"DELTA TAIL: closed at {tail_ratio*100:.0f}% of intrabar max "
                    f"({delta:+d}/{extreme:+d}) — strong conviction",
                ))
        elif delta < 0:
            extreme = bar.min_delta if bar.min_delta < 0 else delta
            tail_ratio = delta / extreme if extreme < 0 else 0.0
            if tail_ratio >= cfg.tail_threshold:
                signals.append(DeltaSignal(
                    DeltaType.TAIL, -1, tail_ratio, delta,
                    f"DELTA TAIL: closed at {tail_ratio*100:.0f}% of intrabar min "
                    f"({delta:+d}/{extreme:+d}) — strong conviction",
                ))

        # --- 3. REVERSAL (DELT-03) — bar-level approximation ---
        # Delta sign contradicts bar direction: close > open but delta < 0 (bearish hidden reversal)
        # or close < open but delta > 0 (bullish hidden reversal).
        # Requires min delta ratio to avoid noise on flat bars.
        if bar.total_vol > 0:
            delta_ratio_abs = abs(delta) / bar.total_vol
            if delta_ratio_abs >= cfg.reversal_min_delta_ratio:
                bar_bullish = bar.close > bar.open
                bar_bearish = bar.close < bar.open
                if bar_bullish and delta < 0:
                    signals.append(DeltaSignal(
                        DeltaType.REVERSAL, -1,
                        min(delta_ratio_abs, 1.0), delta,
                        f"DELTA REVERSAL (bearish hidden): bar closed UP but delta={delta:+d} (selling dominated)",
                    ))
                elif bar_bearish and delta > 0:
                    signals.append(DeltaSignal(
                        DeltaType.REVERSAL, +1,
                        min(delta_ratio_abs, 1.0), delta,
                        f"DELTA REVERSAL (bullish hidden): bar closed DOWN but delta={delta:+d} (buying dominated)",
                    ))

        # --- 4. DIVERGENCE (DELT-04) — highest alpha ---
        div_lb = cfg.divergence_lookback
        if len(self.price_history) >= div_lb and len(self.cvd_history) >= div_lb:
            prices = list(self.price_history)
            cvds = list(self.cvd_history)

            # Price making new N-bar high but CVD not confirming
            if prices[-1] == max(prices[-div_lb:]) and cvds[-1] < max(cvds[-div_lb:]):
                signals.append(DeltaSignal(
                    DeltaType.DIVERGENCE, -1, 0.8, cvd,
                    f"BEARISH DIVERGENCE: price at {div_lb}-bar high but CVD failing",
                ))

            # Price making new N-bar low but CVD not confirming
            if prices[-1] == min(prices[-div_lb:]) and cvds[-1] > min(cvds[-div_lb:]):
                signals.append(DeltaSignal(
                    DeltaType.DIVERGENCE, +1, 0.8, cvd,
                    f"BULLISH DIVERGENCE: price at {div_lb}-bar low but CVD holding",
                ))

        # --- 5. FLIP (DELT-05) ---
        if len(self.cvd_history) >= 2:
            prev_cvd = self.cvd_history[-2]
            if prev_cvd >= 0 and cvd < 0:
                signals.append(DeltaSignal(
                    DeltaType.FLIP, -1, 0.6, cvd,
                    f"CVD FLIP: crossed below zero ({prev_cvd:+.0f} → {cvd:+.0f})",
                ))
            elif prev_cvd <= 0 and cvd > 0:
                signals.append(DeltaSignal(
                    DeltaType.FLIP, +1, 0.6, cvd,
                    f"CVD FLIP: crossed above zero ({prev_cvd:+.0f} → {cvd:+.0f})",
                ))

        # --- 6. TRAP (DELT-06) ---
        if len(self.delta_history) >= 2:
            prev_delta = self.delta_history[-2]
            # Strong buying delta then price drops
            if prev_delta > bar.total_vol * cfg.trap_delta_ratio and bar.close < bar.open:
                signals.append(DeltaSignal(
                    DeltaType.TRAP, -1, 0.7, delta,
                    f"DELTA TRAP: prev delta={prev_delta:+d} (bullish) but price dropped",
                ))
            # Strong selling delta then price rises
            if prev_delta < -bar.total_vol * cfg.trap_delta_ratio and bar.close > bar.open:
                signals.append(DeltaSignal(
                    DeltaType.TRAP, +1, 0.7, delta,
                    f"DELTA TRAP: prev delta={prev_delta:+d} (bearish) but price rose",
                ))

        # --- 7. SWEEP (DELT-07) ---
        # Bar spans >= sweep_min_levels price levels AND second-half volume exceeds
        # first-half volume by sweep_vol_increase_ratio (indicates acceleration = sweep).
        if bar.levels and len(bar.levels) >= cfg.sweep_min_levels:
            sorted_ticks = sorted(bar.levels.keys())
            n_levels = len(sorted_ticks)
            mid = n_levels // 2
            first_half_vol = sum(
                bar.levels[t].bid_vol + bar.levels[t].ask_vol
                for t in sorted_ticks[:mid]
            )
            second_half_vol = sum(
                bar.levels[t].bid_vol + bar.levels[t].ask_vol
                for t in sorted_ticks[mid:]
            )
            if first_half_vol > 0 and second_half_vol >= first_half_vol * cfg.sweep_vol_increase_ratio:
                direction = +1 if delta >= 0 else -1
                signals.append(DeltaSignal(
                    DeltaType.SWEEP, direction, 0.8, delta,
                    f"DELTA SWEEP: {n_levels} levels, vol accelerated "
                    f"({first_half_vol} → {second_half_vol}, "
                    f"{second_half_vol/first_half_vol:.1f}x increase)",
                ))

        # --- 8. SLINGSHOT (DELT-08) — 72-78% win rate ---
        if len(self.delta_history) >= 4:
            recent = list(self.delta_history)[-4:]
            # Compressed: slingshot_quiet_bars out of 3 prior bars have small delta,
            # then current bar explodes
            small_bars = sum(
                1 for d in recent[:3] if abs(d) < bar.total_vol * cfg.slingshot_quiet_ratio
            )
            if (
                small_bars >= cfg.slingshot_quiet_bars
                and abs(delta) > bar.total_vol * cfg.slingshot_explosive_ratio
            ):
                direction = +1 if delta > 0 else -1
                signals.append(DeltaSignal(
                    DeltaType.SLINGSHOT, direction, 0.85, delta,
                    f"DELTA SLINGSHOT: compressed then explosive delta={delta:+d} (72-78% win rate)",
                ))

        # --- 9. AT MIN/MAX (DELT-09) ---
        cvd_range = self.session_cvd_max - self.session_cvd_min
        if cvd_range > 0:
            if cvd >= self.session_cvd_max:
                signals.append(DeltaSignal(
                    DeltaType.AT_MAX, +1, 0.5, cvd,
                    f"CVD AT SESSION MAX: {cvd:+.0f}",
                ))
            if cvd <= self.session_cvd_min:
                signals.append(DeltaSignal(
                    DeltaType.AT_MIN, -1, 0.5, cvd,
                    f"CVD AT SESSION MIN: {cvd:+.0f}",
                ))

        # --- 10. CVD MULTI-BAR DIVERGENCE (DELT-10) ---
        if len(self.cvd_history) >= cfg.cvd_divergence_min_bars:
            x = np.arange(len(self.cvd_history), dtype=np.float64)
            cvd_arr = np.array(self.cvd_history, dtype=np.float64)
            price_arr = np.array(self.price_history, dtype=np.float64)

            cvd_slope = np.polyfit(x, cvd_arr, 1)[0]
            price_slope = np.polyfit(x, price_arr, 1)[0]

            # Divergence: slopes in opposite directions
            if price_slope > 0 and cvd_slope < -abs(price_slope) * cfg.cvd_slope_divergence_factor:
                signals.append(DeltaSignal(
                    DeltaType.CVD_DIVERGENCE, -1, 0.75, cvd_slope,
                    f"CVD MULTI-BAR DIVERGENCE: price trending up (slope={price_slope:.2f}) "
                    f"but CVD declining (slope={cvd_slope:.2f})",
                ))
            elif price_slope < 0 and cvd_slope > abs(price_slope) * cfg.cvd_slope_divergence_factor:
                signals.append(DeltaSignal(
                    DeltaType.CVD_DIVERGENCE, +1, 0.75, cvd_slope,
                    f"CVD MULTI-BAR DIVERGENCE: price trending down (slope={price_slope:.2f}) "
                    f"but CVD rising (slope={cvd_slope:.2f})",
                ))

        # --- 11. VELOCITY (DELT-11) ---
        if len(self.cvd_history) >= 3:
            cvd_vals = list(self.cvd_history)
            velocity = cvd_vals[-1] - cvd_vals[-2]
            accel = velocity - (cvd_vals[-2] - cvd_vals[-3])
            if abs(accel) > bar.total_vol * cfg.velocity_accel_ratio:
                direction = +1 if accel > 0 else -1
                signals.append(DeltaSignal(
                    DeltaType.VELOCITY, direction, min(abs(accel) / bar.total_vol, 1.0), accel,
                    f"DELTA VELOCITY: accel={accel:+.0f} — {'accelerating' if direction > 0 else 'decelerating'}",
                ))

        return signals
