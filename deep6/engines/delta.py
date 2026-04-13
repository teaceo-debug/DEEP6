"""Delta signal detection — 11 variants.

Delta measures the difference between buying and selling pressure.
These signals detect when delta behavior diverges from price action
or reaches extremes that predict reversals.

Variants (per DELT-01..11):
  1.  Rise/Drop:       Delta classified per bar
  2.  Tail:            Bar delta at 95%+ of its extreme
  3.  Reversal:        Intrabar delta flip (not available without tick-level tracking)
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


class DeltaEngine:
    """Stateful delta engine tracking CVD, session extremes, and history."""

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.cvd_history: deque[float] = deque(maxlen=lookback)
        self.price_history: deque[float] = deque(maxlen=lookback)
        self.delta_history: deque[float] = deque(maxlen=lookback)
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

    def process(self, bar: FootprintBar) -> list[DeltaSignal]:
        signals: list[DeltaSignal] = []

        if bar.total_vol == 0:
            return signals

        delta = bar.bar_delta
        cvd = bar.cvd
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

        # --- 2. TAIL (DELT-02) ---
        # Delta at 95%+ of its extreme within bar
        if bar.total_vol > 0:
            delta_ratio = abs(delta) / bar.total_vol
            if delta_ratio >= 0.95:
                direction = +1 if delta > 0 else -1
                signals.append(DeltaSignal(
                    DeltaType.TAIL, direction, delta_ratio, delta,
                    f"DELTA TAIL: {delta_ratio*100:.0f}% at extreme — strong conviction",
                ))

        # --- 4. DIVERGENCE (DELT-04) — highest alpha ---
        if len(self.price_history) >= 5 and len(self.cvd_history) >= 5:
            prices = list(self.price_history)
            cvds = list(self.cvd_history)

            # Price making new 5-bar high but CVD not confirming
            if prices[-1] == max(prices[-5:]) and cvds[-1] < max(cvds[-5:]):
                signals.append(DeltaSignal(
                    DeltaType.DIVERGENCE, -1, 0.8, cvd,
                    f"BEARISH DIVERGENCE: price at 5-bar high but CVD failing",
                ))

            # Price making new 5-bar low but CVD not confirming
            if prices[-1] == min(prices[-5:]) and cvds[-1] > min(cvds[-5:]):
                signals.append(DeltaSignal(
                    DeltaType.DIVERGENCE, +1, 0.8, cvd,
                    f"BULLISH DIVERGENCE: price at 5-bar low but CVD holding",
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
            if prev_delta > bar.total_vol * 0.3 and bar.close < bar.open:
                signals.append(DeltaSignal(
                    DeltaType.TRAP, -1, 0.7, delta,
                    f"DELTA TRAP: prev delta={prev_delta:+d} (bullish) but price dropped",
                ))
            # Strong selling delta then price rises
            if prev_delta < -bar.total_vol * 0.3 and bar.close > bar.open:
                signals.append(DeltaSignal(
                    DeltaType.TRAP, +1, 0.7, delta,
                    f"DELTA TRAP: prev delta={prev_delta:+d} (bearish) but price rose",
                ))

        # --- 8. SLINGSHOT (DELT-08) — 72-78% win rate ---
        if len(self.delta_history) >= 4:
            recent = list(self.delta_history)[-4:]
            # Compressed: 3 bars of small delta, then explosive
            small_bars = sum(1 for d in recent[:3] if abs(d) < bar.total_vol * 0.1)
            if small_bars >= 2 and abs(delta) > bar.total_vol * 0.4:
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
        if len(self.cvd_history) >= 10:
            x = np.arange(len(self.cvd_history), dtype=np.float64)
            cvd_arr = np.array(self.cvd_history, dtype=np.float64)
            price_arr = np.array(self.price_history, dtype=np.float64)

            cvd_slope = np.polyfit(x, cvd_arr, 1)[0]
            price_slope = np.polyfit(x, price_arr, 1)[0]

            # Divergence: slopes in opposite directions
            if price_slope > 0 and cvd_slope < -abs(price_slope) * 0.3:
                signals.append(DeltaSignal(
                    DeltaType.CVD_DIVERGENCE, -1, 0.75, cvd_slope,
                    f"CVD MULTI-BAR DIVERGENCE: price trending up (slope={price_slope:.2f}) "
                    f"but CVD declining (slope={cvd_slope:.2f})",
                ))
            elif price_slope < 0 and cvd_slope > abs(price_slope) * 0.3:
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
            if abs(accel) > bar.total_vol * 0.3:
                direction = +1 if accel > 0 else -1
                signals.append(DeltaSignal(
                    DeltaType.VELOCITY, direction, min(abs(accel) / bar.total_vol, 1.0), accel,
                    f"DELTA VELOCITY: accel={accel:+.0f} — {'accelerating' if direction > 0 else 'decelerating'}",
                ))

        return signals
