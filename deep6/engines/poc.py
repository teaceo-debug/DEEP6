"""POC / Value Area signals — 8 variants.

POC (Point of Control) is the price with highest volume in a bar or session.
Value Area contains ~70% of volume. These signals detect when POC behavior
and value area dynamics predict directional bias.

Variants (per POC-01..08):
  1. Above/Below POC:  Bar close relative to session POC
  2. Extreme POC:      POC at bar high or low (P/B reversal profile)
  3. Continuous POC:   Same POC defended 3+ bars
  4. POC Gap:          POC jumped N+ ticks from prior bar
  5. POC Delta:        Net delta at the POC level specifically
  6. Engulfing VA:     Current VA contains prior VA entirely
  7. VA Gap:           No overlap between current and prior VA
  8. Bullish/Bearish:  POC position relative to open/close
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto

from deep6.engines.signal_config import POCConfig
from deep6.state.footprint import FootprintBar, price_to_tick, tick_to_price


class POCType(Enum):
    ABOVE_POC = auto()
    BELOW_POC = auto()
    EXTREME_POC_HIGH = auto()
    EXTREME_POC_LOW = auto()
    CONTINUOUS_POC = auto()
    POC_GAP = auto()
    POC_DELTA = auto()
    ENGULFING_VA = auto()
    VA_GAP = auto()
    BULLISH_POC = auto()
    BEARISH_POC = auto()


@dataclass
class POCSignal:
    poc_type: POCType
    direction: int
    price: float
    strength: float
    detail: str


class POCEngine:
    """Stateful POC/VA engine tracking session POC migration and value areas."""

    def __init__(
        self,
        config: POCConfig | None = None,
        va_pct: float | None = None,
        poc_gap_ticks: int | None = None,
    ):
        if config is None:
            # Support legacy kwargs for backward compat
            kwargs: dict = {}
            if va_pct is not None:
                kwargs['va_pct'] = va_pct
            if poc_gap_ticks is not None:
                kwargs['poc_gap_ticks'] = poc_gap_ticks
            config = POCConfig(**kwargs)
        self.config = config
        self.va_pct = config.va_pct          # keep attribute for any direct references
        self.poc_gap_ticks = config.poc_gap_ticks
        self.session_poc: float = 0.0
        self.prev_poc: float = 0.0
        self.poc_streak: int = 0
        self.prev_vah: float = 0.0
        self.prev_val: float = 0.0
        self.poc_history: deque[float] = deque(maxlen=50)
        self.poc_migration_history: deque[float] = deque(maxlen=self.config.migration_window)

    def reset(self) -> None:
        self.session_poc = 0.0
        self.prev_poc = 0.0
        self.poc_streak = 0
        self.prev_vah = 0.0
        self.prev_val = 0.0
        self.poc_history.clear()

    def process(self, bar: FootprintBar) -> list[POCSignal]:
        signals: list[POCSignal] = []

        if not bar.levels or bar.total_vol == 0:
            return signals

        poc = bar.poc_price
        self.poc_history.append(poc)

        # Compute bar's value area
        vah, val = self._compute_va(bar)

        # --- 1. ABOVE/BELOW POC (POC-01) ---
        if self.session_poc > 0:
            if bar.close > self.session_poc:
                signals.append(POCSignal(
                    POCType.ABOVE_POC, +1, self.session_poc, 0.4,
                    f"CLOSE ABOVE SESSION POC {self.session_poc:.2f} — bullish bias",
                ))
            elif bar.close < self.session_poc:
                signals.append(POCSignal(
                    POCType.BELOW_POC, -1, self.session_poc, 0.4,
                    f"CLOSE BELOW SESSION POC {self.session_poc:.2f} — bearish bias",
                ))

        # --- 2. EXTREME POC (POC-02) — P/B reversal profile ---
        body_top = max(bar.open, bar.close)
        body_bot = min(bar.open, bar.close)

        if poc >= body_top and poc >= bar.high - bar.bar_range * self.config.extreme_top_pct:
            # POC at top = P-shaped profile (bearish reversal)
            signals.append(POCSignal(
                POCType.EXTREME_POC_HIGH, -1, poc, 0.7,
                f"EXTREME POC at HIGH {poc:.2f} — P-profile bearish reversal",
            ))
        elif poc <= body_bot and poc <= bar.low + bar.bar_range * self.config.extreme_bot_pct:
            # POC at bottom = B-shaped profile (bullish reversal)
            signals.append(POCSignal(
                POCType.EXTREME_POC_LOW, +1, poc, 0.7,
                f"EXTREME POC at LOW {poc:.2f} — B-profile bullish reversal",
            ))

        # --- 3. CONTINUOUS POC (POC-03) ---
        if self.prev_poc > 0:
            if abs(poc - self.prev_poc) <= bar.bar_range * 0.2 or \
               abs(price_to_tick(poc) - price_to_tick(self.prev_poc)) <= 2:
                self.poc_streak += 1
            else:
                self.poc_streak = 1

            if self.poc_streak >= self.config.continuous_streak_min:
                signals.append(POCSignal(
                    POCType.CONTINUOUS_POC, 0, poc, min(self.poc_streak / 5.0, 1.0),
                    f"CONTINUOUS POC x{self.poc_streak} at {poc:.2f} — strong acceptance",
                ))

        # --- 4. POC GAP (POC-04) ---
        if self.prev_poc > 0:
            gap_ticks = abs(price_to_tick(poc) - price_to_tick(self.prev_poc))
            if gap_ticks >= self.poc_gap_ticks:
                direction = +1 if poc > self.prev_poc else -1
                signals.append(POCSignal(
                    POCType.POC_GAP, direction, poc, min(gap_ticks / 16.0, 1.0),
                    f"POC GAP: {gap_ticks} ticks ({self.prev_poc:.2f} → {poc:.2f})",
                ))

        # --- 5. POC DELTA (POC-05) ---
        poc_tick = price_to_tick(poc)
        if poc_tick in bar.levels:
            level = bar.levels[poc_tick]
            poc_delta = level.ask_vol - level.bid_vol
            direction = +1 if poc_delta > 0 else -1 if poc_delta < 0 else 0
            poc_vol = level.ask_vol + level.bid_vol
            if poc_vol > 0:
                signals.append(POCSignal(
                    POCType.POC_DELTA, direction, poc,
                    min(abs(poc_delta) / poc_vol, 1.0),
                    f"POC DELTA at {poc:.2f}: {poc_delta:+d} "
                    f"({'buyers' if poc_delta > 0 else 'sellers'} dominant at fair value)",
                ))

        # --- 6. ENGULFING VA (POC-06) ---
        if self.prev_vah > 0 and self.prev_val > 0:
            if vah >= self.prev_vah and val <= self.prev_val:
                signals.append(POCSignal(
                    POCType.ENGULFING_VA, 0, (vah + val) / 2, 0.6,
                    f"ENGULFING VA: {val:.2f}-{vah:.2f} contains prior {self.prev_val:.2f}-{self.prev_vah:.2f}",
                ))

        # --- 7. VA GAP (POC-07) ---
        if self.prev_vah > 0 and self.prev_val > 0:
            if val > self.prev_vah:
                signals.append(POCSignal(
                    POCType.VA_GAP, +1, (val + self.prev_vah) / 2, 0.7,
                    f"VA GAP UP: current VAL {val:.2f} above prior VAH {self.prev_vah:.2f}",
                ))
            elif vah < self.prev_val:
                signals.append(POCSignal(
                    POCType.VA_GAP, -1, (vah + self.prev_val) / 2, 0.7,
                    f"VA GAP DOWN: current VAH {vah:.2f} below prior VAL {self.prev_val:.2f}",
                ))

        # --- 8. BULLISH/BEARISH POC (POC-08) ---
        if bar.bar_range > 0:
            poc_position = (poc - bar.low) / bar.bar_range
            if poc_position < self.config.bullish_poc_position_max and bar.close > bar.open:
                signals.append(POCSignal(
                    POCType.BULLISH_POC, +1, poc, 0.6,
                    f"BULLISH POC: POC at {poc_position*100:.0f}% (low) in green bar — B-profile",
                ))
            elif poc_position > self.config.bearish_poc_position_min and bar.close < bar.open:
                signals.append(POCSignal(
                    POCType.BEARISH_POC, -1, poc, 0.6,
                    f"BEARISH POC: POC at {poc_position*100:.0f}% (high) in red bar — P-profile",
                ))

        # Update state for next bar
        self.prev_poc = poc
        self.poc_migration_history.append(poc)
        self.prev_vah = vah
        self.prev_val = val
        self.session_poc = self._compute_session_poc()

        return signals

    def get_migration(self) -> tuple[int, float]:
        """Return (direction, velocity) of session POC migration.

        direction: +1 (rising), -1 (falling), 0 (flat)
        velocity: absolute ticks/bar over migration_window
        VPRO-08: POC migration direction and velocity.
        """
        hist = list(self.poc_migration_history)
        if len(hist) < 2:
            return (0, 0.0)
        ticks = [price_to_tick(p) for p in hist]
        # Average tick change per bar
        velocity = (ticks[-1] - ticks[0]) / (len(ticks) - 1)
        direction = +1 if velocity > 0.5 else -1 if velocity < -0.5 else 0
        return (direction, abs(velocity))

    def _compute_va(self, bar: FootprintBar) -> tuple[float, float]:
        """Compute Value Area High and Low for the bar (70% of volume)."""
        if not bar.levels:
            return 0.0, 0.0

        sorted_levels = sorted(
            bar.levels.items(),
            key=lambda x: x[1].ask_vol + x[1].bid_vol,
            reverse=True,
        )

        target_vol = bar.total_vol * self.va_pct
        accumulated = 0
        ticks_in_va: list[int] = []

        for tick, level in sorted_levels:
            accumulated += level.ask_vol + level.bid_vol
            ticks_in_va.append(tick)
            if accumulated >= target_vol:
                break

        if not ticks_in_va:
            return bar.high, bar.low

        vah = tick_to_price(max(ticks_in_va)) + 0.25  # top of highest tick
        val = tick_to_price(min(ticks_in_va))
        return vah, val

    def _compute_session_poc(self) -> float:
        """Simple session POC: most frequent POC price in history."""
        if not self.poc_history:
            return 0.0
        from collections import Counter
        counts = Counter(self.poc_history)
        return counts.most_common(1)[0][0]
