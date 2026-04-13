"""Trapped trader signal engine — TRAP-02..05.

Detects four variants of price traps where participants are caught on the wrong
side of the market after committing capital.

Requirements addressed:
  TRAP-02: Delta trap — prior strong directional delta reverses on current bar
  TRAP-03: False breakout trap — bar breaks prior extreme then closes back inside
  TRAP-04: High volume rejection trap — high-vol bar with dominant wick rejection
  TRAP-05: CVD trap — cumulative volume delta trend reverses direction

NOTE: TRAP-01 (inverse imbalance trap / INVERSE_TRAP) is already implemented in
deep6/engines/imbalance.py as ImbalanceType.INVERSE_TRAP. It fires via
detect_imbalances() for IMB-05. Do NOT duplicate it here.

Architecture:
  - No global state — all inputs passed as arguments to process()
  - Caller maintains history (cvd_history, vol_ema); engine reads only
  - Returns [] immediately for zero-volume bars (T-04-02)
  - All divisions guarded by total_vol > 0 check (T-04-03)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from deep6.engines.signal_config import TrapConfig
from deep6.state.footprint import FootprintBar


class TrapType(Enum):
    """Trapped trader signal variants (TRAP-02..05)."""
    DELTA_TRAP = auto()                 # TRAP-02
    FALSE_BREAKOUT_TRAP = auto()        # TRAP-03
    HIGH_VOL_REJECTION_TRAP = auto()    # TRAP-04
    CVD_TRAP = auto()                   # TRAP-05


@dataclass
class TrapSignal:
    """A single trapped trader signal.

    Matches the ImbalanceSignal pattern for scorer integration (Phase 7).
    """
    trap_type: TrapType
    direction: int       # +1 = bull trap (shorts trapped), -1 = bear trap (longs trapped)
    price: float         # Reference price (usually bar.close or bar.high/low)
    strength: float      # 0.0–1.0 quality score
    detail: str          # Human-readable description


class TrapEngine:
    """Detect 4 trapped trader signal variants from FootprintBar data.

    All state is passed in — engine is stateless. This allows the same engine
    instance to be reused across bars or in backtests without side effects.

    Usage::

        engine = TrapEngine()
        signals = engine.process(bar, prior_bar, vol_ema=200.0, cvd_history=cvd_list)
    """

    def __init__(self, config: TrapConfig = TrapConfig()) -> None:
        self.config = config

    def process(
        self,
        bar: FootprintBar,
        prior_bar: FootprintBar | None,
        vol_ema: float,
        cvd_history: list[int],
    ) -> list[TrapSignal]:
        """Detect all trap variants in *bar*.

        Args:
            bar:         Current completed FootprintBar.
            prior_bar:   Previous FootprintBar, or None if first bar.
            vol_ema:     Exponential moving average of volume (caller-maintained).
            cvd_history: Rolling list of bar CVD values — oldest first, read-only.
                         Engine never mutates this list (T-04-01).

        Returns:
            List of TrapSignal objects; empty list if bar.total_vol == 0 or
            no conditions met.
        """
        # T-04-02: guard for empty / zero-volume bars
        if bar.total_vol == 0:
            return []

        signals: list[TrapSignal] = []

        sig = self._detect_delta_trap(bar, prior_bar)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_false_breakout(bar, prior_bar, vol_ema)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_high_vol_rejection(bar, vol_ema)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_cvd_trap(bar, cvd_history)
        if sig is not None:
            signals.append(sig)

        return signals

    # ------------------------------------------------------------------
    # Private: TRAP-02 — Delta trap
    # ------------------------------------------------------------------

    def _detect_delta_trap(
        self,
        bar: FootprintBar,
        prior_bar: FootprintBar | None,
    ) -> TrapSignal | None:
        """TRAP-02: Prior bar had strong directional delta; current bar reverses.

        Condition:
          1. prior_bar |delta|/total_vol >= trap_delta_ratio
          2. Price reversal: current bar closes opposite direction to prior delta
          3. Delta reversal: current bar_delta also reverses (confirms)
        """
        if prior_bar is None or prior_bar.total_vol == 0:
            return None

        cfg = self.config
        prior_ratio = abs(prior_bar.bar_delta) / prior_bar.total_vol
        if prior_ratio < cfg.trap_delta_ratio:
            return None

        prior_bull = prior_bar.bar_delta > 0  # prior bar was net-buying
        current_delta_reversed = (
            (prior_bull and bar.bar_delta < 0) or
            (not prior_bull and bar.bar_delta > 0)
        )
        price_reversed = (
            (prior_bull and bar.close < bar.open) or
            (not prior_bull and bar.close > bar.open)
        )

        if not (current_delta_reversed and price_reversed):
            return None

        direction = 1 if bar.bar_delta > 0 else -1
        # Strength: how much the prior bar's delta ratio exceeded threshold
        strength = min(prior_ratio / (cfg.trap_delta_ratio * 2.0), 1.0)

        return TrapSignal(
            trap_type=TrapType.DELTA_TRAP,
            direction=direction,
            price=bar.close,
            strength=strength,
            detail=(
                f"DELTA TRAP: prior delta ratio {prior_ratio:.2f} reversed; "
                f"current delta {bar.bar_delta:+d}"
            ),
        )

    # ------------------------------------------------------------------
    # Private: TRAP-03 — False breakout trap
    # ------------------------------------------------------------------

    def _detect_false_breakout(
        self,
        bar: FootprintBar,
        prior_bar: FootprintBar | None,
        vol_ema: float,
    ) -> TrapSignal | None:
        """TRAP-03: Bar breaks prior extreme then closes back inside.

        Bear trap (longs trapped):
          bar.high > prior_bar.high AND bar.close < prior_bar.high
          AND bar.total_vol > vol_ema * false_breakout_vol_mult

        Bull trap (shorts trapped):
          bar.low < prior_bar.low AND bar.close > prior_bar.low
          AND bar.total_vol > vol_ema * false_breakout_vol_mult
        """
        if prior_bar is None:
            return None

        cfg = self.config
        vol_threshold = vol_ema * cfg.false_breakout_vol_mult
        if bar.total_vol <= vol_threshold:
            return None

        # Bear false breakout: broke above prior high, closed back below it
        if bar.high > prior_bar.high and bar.close < prior_bar.high:
            # Volume normalised strength
            strength = min((bar.total_vol / vol_threshold - 1.0) / 2.0, 1.0)
            return TrapSignal(
                trap_type=TrapType.FALSE_BREAKOUT_TRAP,
                direction=-1,   # longs trapped
                price=bar.high,
                strength=strength,
                detail=(
                    f"FALSE BREAKOUT TRAP (bear): high {bar.high:.2f} > prior {prior_bar.high:.2f}, "
                    f"closed {bar.close:.2f} < prior high; vol {bar.total_vol} ({bar.total_vol/vol_ema:.1f}×ema)"
                ),
            )

        # Bull false breakout: broke below prior low, closed back above it
        if bar.low < prior_bar.low and bar.close > prior_bar.low:
            strength = min((bar.total_vol / vol_threshold - 1.0) / 2.0, 1.0)
            return TrapSignal(
                trap_type=TrapType.FALSE_BREAKOUT_TRAP,
                direction=+1,   # shorts trapped
                price=bar.low,
                strength=strength,
                detail=(
                    f"FALSE BREAKOUT TRAP (bull): low {bar.low:.2f} < prior {prior_bar.low:.2f}, "
                    f"closed {bar.close:.2f} > prior low; vol {bar.total_vol} ({bar.total_vol/vol_ema:.1f}×ema)"
                ),
            )

        return None

    # ------------------------------------------------------------------
    # Private: TRAP-04 — High volume rejection trap
    # ------------------------------------------------------------------

    def _detect_high_vol_rejection(
        self,
        bar: FootprintBar,
        vol_ema: float,
    ) -> TrapSignal | None:
        """TRAP-04: High volume bar with dominant wick rejection.

        Condition:
          bar.total_vol > vol_ema * hvr_vol_mult
          AND bar.bar_range > 0
          AND upper or lower wick volume fraction > hvr_wick_min

        Wick volume is computed from bar.levels: levels in the top or bottom
        quarter of the range contribute to the respective wick fraction.
        Direction: -1 if upper wick dominates (price rejected from highs),
                   +1 if lower wick dominates (price rejected from lows).
        """
        cfg = self.config
        if bar.total_vol <= vol_ema * cfg.hvr_vol_mult:
            return None
        if bar.bar_range <= 0:
            return None

        # Compute wick volumes from levels dict (T-04-03: guard total_vol > 0 above)
        upper_wick_vol = 0
        lower_wick_vol = 0

        if bar.levels:
            range_quarter = bar.bar_range / 4.0
            upper_zone_price = bar.high - range_quarter
            lower_zone_price = bar.low + range_quarter

            from deep6.state.footprint import tick_to_price
            for tick, level in bar.levels.items():
                price = tick_to_price(tick)
                level_vol = level.bid_vol + level.ask_vol
                if price >= upper_zone_price:
                    upper_wick_vol += level_vol
                if price <= lower_zone_price:
                    lower_wick_vol += level_vol

        upper_frac = upper_wick_vol / bar.total_vol
        lower_frac = lower_wick_vol / bar.total_vol

        dominant_upper = upper_frac > lower_frac and upper_frac >= cfg.hvr_wick_min
        dominant_lower = lower_frac >= upper_frac and lower_frac >= cfg.hvr_wick_min

        if not (dominant_upper or dominant_lower):
            return None

        direction = -1 if dominant_upper else +1
        wick_frac = upper_frac if dominant_upper else lower_frac
        strength = min(wick_frac / (cfg.hvr_wick_min * 2.0), 1.0)
        wick_label = "upper" if dominant_upper else "lower"

        return TrapSignal(
            trap_type=TrapType.HIGH_VOL_REJECTION_TRAP,
            direction=direction,
            price=bar.high if dominant_upper else bar.low,
            strength=strength,
            detail=(
                f"HVR TRAP: vol {bar.total_vol} ({bar.total_vol/vol_ema:.1f}×ema), "
                f"{wick_label} wick frac {wick_frac:.1%}"
            ),
        )

    # ------------------------------------------------------------------
    # Private: TRAP-05 — CVD trap
    # ------------------------------------------------------------------

    def _detect_cvd_trap(
        self,
        bar: FootprintBar,
        cvd_history: list[int],
    ) -> TrapSignal | None:
        """TRAP-05: CVD trend (measured by linear slope) reverses direction.

        Uses numpy polyfit over the last cvd_trap_lookback values to measure
        prior trend slope. If |slope| > cvd_trap_min_slope AND the current bar's
        delta sign opposes the prior slope sign, fire the trap.

        T-04-01: cvd_history is never mutated — numpy slices create copies.
        """
        cfg = self.config
        lookback = cfg.cvd_trap_lookback

        if len(cvd_history) < lookback:
            return None

        # Slice creates a copy — does not mutate caller's list (T-04-01)
        window = cvd_history[-lookback:]
        x = np.arange(len(window), dtype=float)
        coeffs = np.polyfit(x, window, 1)
        slope = float(coeffs[0])

        if abs(slope) < cfg.cvd_trap_min_slope:
            return None  # CVD is too flat — not a meaningful trend

        # Trend reversal: current bar's delta opposes the prior CVD slope
        prior_trend_bull = slope > 0
        current_delta_bull = bar.bar_delta > 0

        # Trap fires when current delta direction opposes prior CVD trend
        reversal = (prior_trend_bull and not current_delta_bull) or \
                   (not prior_trend_bull and current_delta_bull)

        if not reversal:
            return None

        direction = 1 if current_delta_bull else -1
        strength = min(abs(slope) / (cfg.cvd_trap_min_slope * 10.0), 1.0)

        return TrapSignal(
            trap_type=TrapType.CVD_TRAP,
            direction=direction,
            price=bar.close,
            strength=strength,
            detail=(
                f"CVD TRAP: prior slope {slope:+.2f} (lookback={lookback}), "
                f"current delta {bar.bar_delta:+d} reverses trend"
            ),
        )
