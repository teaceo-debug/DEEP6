"""Volume pattern signal engine — VOLP-01..06.

Detects six volume structure anomalies that indicate institutional activity,
accumulation/distribution, or impending directional moves.

Requirements addressed:
  VOLP-01: Volume sequencing — 3+ consecutive bars with escalating volume
  VOLP-02: Volume bubble — single price level with outsized volume concentration
  VOLP-03: Volume surge — bar volume > 3× vol_ema
  VOLP-04: POC momentum wave — POC has migrated directionally for N consecutive bars
  VOLP-05: Delta velocity spike — rapid change in bar delta between consecutive bars
  VOLP-06: Big delta per level — one price level with dominant net_delta

Architecture:
  - No global state — all inputs passed as arguments to process()
  - bar_history: caller-maintained list/deque, passed as list; oldest first
  - poc_history: caller-maintained list of prior bar POC prices; read-only
  - Returns [] immediately for zero-volume bars or empty levels (T-04-02)
  - All divisions guarded by total_vol > 0 (T-04-03)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from deep6.engines.signal_config import VolPatternConfig
from deep6.state.footprint import FootprintBar, tick_to_price


class VolPatternType(Enum):
    """Volume pattern signal variants (VOLP-01..06)."""
    SEQUENCING = auto()           # VOLP-01
    BUBBLE = auto()               # VOLP-02
    SURGE = auto()                # VOLP-03
    POC_MOMENTUM_WAVE = auto()    # VOLP-04
    DELTA_VELOCITY_SPIKE = auto() # VOLP-05
    BIG_DELTA_PER_LEVEL = auto()  # VOLP-06


@dataclass
class VolPatternSignal:
    """A single volume pattern signal.

    Matches the ImbalanceSignal pattern for consistency across the signal layer.
    """
    pattern_type: VolPatternType
    direction: int      # +1 = bullish pattern, -1 = bearish, 0 = ambiguous
    price: float        # Reference price for the pattern
    strength: float     # 0.0–1.0 quality score
    detail: str         # Human-readable description


class VolPatternEngine:
    """Detect 6 volume pattern signal variants from FootprintBar data.

    All state is caller-provided — engine is stateless and re-entrant.

    Usage::

        engine = VolPatternEngine()
        signals = engine.process(bar, bar_history=list(history_deque),
                                 vol_ema=200.0, poc_history=poc_list)
    """

    def __init__(self, config: VolPatternConfig = VolPatternConfig()) -> None:
        self.config = config

    def process(
        self,
        bar: FootprintBar,
        bar_history: list[FootprintBar],
        vol_ema: float,
        poc_history: list[float],
    ) -> list[VolPatternSignal]:
        """Detect all volume pattern variants in *bar*.

        Args:
            bar:         Current completed FootprintBar.
            bar_history: Recent prior bars (oldest first). Caller maintains this
                         list from a deque — engine reads only, never mutates.
            vol_ema:     Exponential moving average of volume (caller-maintained).
            poc_history: Rolling list of prior bar POC prices — oldest first.
                         Engine reads only, never mutates.

        Returns:
            List of VolPatternSignal objects; empty list if bar.total_vol == 0 or
            bar.levels is empty (T-04-02).
        """
        # T-04-02: guard for empty / zero-volume bars
        if bar.total_vol == 0 or not bar.levels:
            return []

        signals: list[VolPatternSignal] = []

        sig = self._detect_sequencing(bar, bar_history)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_bubble(bar)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_surge(bar, vol_ema)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_poc_wave(bar, poc_history)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_delta_velocity(bar, bar_history, vol_ema)
        if sig is not None:
            signals.append(sig)

        sig = self._detect_big_delta_per_level(bar)
        if sig is not None:
            signals.append(sig)

        return signals

    # ------------------------------------------------------------------
    # Private: VOLP-01 — Volume sequencing
    # ------------------------------------------------------------------

    def _detect_sequencing(
        self,
        bar: FootprintBar,
        bar_history: list[FootprintBar],
    ) -> VolPatternSignal | None:
        """VOLP-01: 3+ consecutive bars where each vol >= prior × step_ratio.

        Combines current bar with bar_history to check the sequence ending at bar.
        Direction = sign of sum of bar_delta across the qualifying sequence.
        """
        cfg = self.config
        min_bars = cfg.vol_seq_min_bars
        step = cfg.vol_seq_step_ratio

        # Build sequence ending at current bar (most recent last)
        all_bars = list(bar_history) + [bar]
        if len(all_bars) < min_bars:
            return None

        # Walk backwards from current bar to find the longest qualifying run
        run_bars: list[FootprintBar] = [bar]
        for i in range(len(bar_history) - 1, -1, -1):
            prev = bar_history[i]
            latest = run_bars[0]
            # Each bar's vol must be >= prior * step_ratio, so:
            # run_bars[0] (newer) must be >= bar_history[i] (older) * step
            if prev.total_vol > 0 and latest.total_vol >= prev.total_vol * step:
                run_bars.insert(0, prev)
            else:
                break

        if len(run_bars) < min_bars:
            return None

        total_delta = sum(b.bar_delta for b in run_bars)
        direction = 1 if total_delta > 0 else (-1 if total_delta < 0 else 0)
        # Strength: how many bars above minimum (capped at 2× min)
        strength = min((len(run_bars) - min_bars + 1) / (min_bars + 1), 1.0)

        return VolPatternSignal(
            pattern_type=VolPatternType.SEQUENCING,
            direction=direction,
            price=bar.close,
            strength=strength,
            detail=(
                f"VOL SEQUENCING: {len(run_bars)} bars escalating "
                f"(each >= {step:.0%} of prior); net delta {total_delta:+d}"
            ),
        )

    # ------------------------------------------------------------------
    # Private: VOLP-02 — Volume bubble
    # ------------------------------------------------------------------

    def _detect_bubble(self, bar: FootprintBar) -> VolPatternSignal | None:
        """VOLP-02: Single price level vol > bar_avg_level_vol × bubble_mult.

        bar_avg_level_vol = bar.total_vol / len(bar.levels).
        Fires one signal per bar at the highest-volume bubble level.
        T-04-03: bar.total_vol > 0 already guaranteed by process() guard.
        """
        cfg = self.config
        n_levels = len(bar.levels)
        if n_levels == 0:
            return None

        avg_level_vol = bar.total_vol / n_levels
        threshold = avg_level_vol * cfg.bubble_mult

        best_tick: int | None = None
        best_vol: float = 0.0

        for tick, level in bar.levels.items():
            level_vol = level.bid_vol + level.ask_vol
            if level_vol > threshold and level_vol > best_vol:
                best_vol = level_vol
                best_tick = tick

        if best_tick is None:
            return None

        bubble_price = tick_to_price(best_tick)
        strength = min((best_vol / threshold - 1.0) / 3.0, 1.0)
        # Direction: ask dominance = bullish bubble, bid dominance = bearish
        level = bar.levels[best_tick]
        net = level.ask_vol - level.bid_vol
        direction = 1 if net > 0 else (-1 if net < 0 else 0)

        return VolPatternSignal(
            pattern_type=VolPatternType.BUBBLE,
            direction=direction,
            price=bubble_price,
            strength=strength,
            detail=(
                f"VOL BUBBLE at {bubble_price:.2f}: {int(best_vol)} contracts "
                f"({best_vol/avg_level_vol:.1f}× avg level vol)"
            ),
        )

    # ------------------------------------------------------------------
    # Private: VOLP-03 — Volume surge
    # ------------------------------------------------------------------

    def _detect_surge(
        self, bar: FootprintBar, vol_ema: float
    ) -> VolPatternSignal | None:
        """VOLP-03: bar.total_vol > vol_ema × surge_mult.

        Direction: sign of bar_delta if |delta/vol| > surge_delta_min_ratio, else 0.
        T-04-03: bar.total_vol > 0 guaranteed by process() guard.
        """
        cfg = self.config
        if vol_ema <= 0:
            return None

        threshold = vol_ema * cfg.surge_mult
        if bar.total_vol <= threshold:
            return None

        delta_ratio = abs(bar.bar_delta) / bar.total_vol
        if delta_ratio > cfg.surge_delta_min_ratio:
            direction = 1 if bar.bar_delta > 0 else -1
        else:
            direction = 0

        strength = min((bar.total_vol / threshold - 1.0) / 2.0, 1.0)

        return VolPatternSignal(
            pattern_type=VolPatternType.SURGE,
            direction=direction,
            price=bar.close,
            strength=strength,
            detail=(
                f"VOL SURGE: {bar.total_vol} contracts ({bar.total_vol/vol_ema:.1f}×ema); "
                f"delta {bar.bar_delta:+d} ({delta_ratio:.1%})"
            ),
        )

    # ------------------------------------------------------------------
    # Private: VOLP-04 — POC momentum wave
    # ------------------------------------------------------------------

    def _detect_poc_wave(
        self,
        bar: FootprintBar,
        poc_history: list[float],
    ) -> VolPatternSignal | None:
        """VOLP-04: POC has migrated directionally for poc_wave_bars consecutive bars.

        poc_history contains prior bar POC prices (oldest first).
        Checks that all prices in the last (poc_wave_bars) entries of poc_history
        are monotonically increasing or decreasing.
        Direction = sign of (last - first) in the qualifying window.
        """
        cfg = self.config
        n = cfg.poc_wave_bars

        if len(poc_history) < n:
            return None

        # Use the last n entries of poc_history as the window
        window = poc_history[-n:]
        # Check monotonic (all diffs same sign)
        diffs = [window[i + 1] - window[i] for i in range(len(window) - 1)]
        if all(d > 0 for d in diffs):
            direction = 1
        elif all(d < 0 for d in diffs):
            direction = -1
        else:
            return None  # Not monotonic — choppy POC

        displacement = abs(window[-1] - window[0])
        strength = min(displacement / 10.0, 1.0)  # 10 points = full strength

        return VolPatternSignal(
            pattern_type=VolPatternType.POC_MOMENTUM_WAVE,
            direction=direction,
            price=window[-1],
            strength=strength,
            detail=(
                f"POC WAVE: POC migrated {direction:+d} for {n} bars "
                f"({window[0]:.2f} → {window[-1]:.2f})"
            ),
        )

    # ------------------------------------------------------------------
    # Private: VOLP-05 — Delta velocity spike
    # ------------------------------------------------------------------

    def _detect_delta_velocity(
        self,
        bar: FootprintBar,
        bar_history: list[FootprintBar],
        vol_ema: float,
    ) -> VolPatternSignal | None:
        """VOLP-05: Rapid change in bar delta between current and prior bar.

        velocity = bar.bar_delta - prior_bar.bar_delta
        Fires if |velocity| > vol_ema × delta_velocity_mult.
        Direction = sign of velocity.
        """
        cfg = self.config
        if not bar_history or vol_ema <= 0:
            return None

        prior_bar = bar_history[-1]
        velocity = bar.bar_delta - prior_bar.bar_delta
        threshold = vol_ema * cfg.delta_velocity_mult

        if abs(velocity) <= threshold:
            return None

        direction = 1 if velocity > 0 else -1
        strength = min(abs(velocity) / (threshold * 3.0), 1.0)

        return VolPatternSignal(
            pattern_type=VolPatternType.DELTA_VELOCITY_SPIKE,
            direction=direction,
            price=bar.close,
            strength=strength,
            detail=(
                f"DELTA VELOCITY SPIKE: velocity {velocity:+d} "
                f"(prior delta {prior_bar.bar_delta:+d} → current {bar.bar_delta:+d}); "
                f"threshold {threshold:.0f}"
            ),
        )

    # ------------------------------------------------------------------
    # Private: VOLP-06 — Big delta per level
    # ------------------------------------------------------------------

    def _detect_big_delta_per_level(
        self, bar: FootprintBar
    ) -> VolPatternSignal | None:
        """VOLP-06: Single price level with dominant net_delta.

        Iterates bar.levels to find the level with highest |net_delta|
        (net_delta = ask_vol - bid_vol). Fires if that level's |net_delta|
        exceeds big_delta_level_threshold.
        Direction = sign of net_delta at that level.
        """
        cfg = self.config
        threshold = cfg.big_delta_level_threshold

        best_tick: int | None = None
        best_abs_delta: int = 0
        best_net_delta: int = 0

        for tick, level in bar.levels.items():
            net_delta = level.ask_vol - level.bid_vol
            abs_delta = abs(net_delta)
            if abs_delta > best_abs_delta:
                best_abs_delta = abs_delta
                best_net_delta = net_delta
                best_tick = tick

        if best_tick is None or best_abs_delta < threshold:
            return None

        direction = 1 if best_net_delta > 0 else -1
        level_price = tick_to_price(best_tick)
        strength = min((best_abs_delta - threshold) / (threshold * 2.0), 1.0)

        return VolPatternSignal(
            pattern_type=VolPatternType.BIG_DELTA_PER_LEVEL,
            direction=direction,
            price=level_price,
            strength=strength,
            detail=(
                f"BIG DELTA/LEVEL at {level_price:.2f}: net_delta {best_net_delta:+d} "
                f"(threshold {threshold})"
            ),
        )
