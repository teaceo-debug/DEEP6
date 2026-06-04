"""Exhaustion Context Filter — validates absorption signals against prior delta flow.

Research finding (15 rounds, N=901 absorption bars):
- Prior 10-bar delta OPPOSING absorption direction = exhaustion reversal context
- Without context: WR=46.3%, Avg=-3.2 ticks (negative expectancy)
- With context: WR=50.2%, Avg=+24.3 ticks (positive expectancy, N=321)
- ABS_04 + prior TRAP_05: N=11, WR=55%, Avg=+563 ticks (killer combo)

The filter:
1. Compute sum of delta over prior N bars (default 10)
2. Check if delta sum OPPOSES the absorption signal direction
3. Flag ABS_04 + TRAP_05 co-occurrence as high-priority
"""

from __future__ import annotations

from dataclasses import dataclass

from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalId, SignalResult


_ABSORPTION_IDS: frozenset[SignalId] = frozenset(
    {SignalId.ABS_01, SignalId.ABS_02, SignalId.ABS_03, SignalId.ABS_04}
)

_DEFAULT_LOOKBACK = 10


@dataclass(frozen=True)
class ExhaustionContextResult:
    """Result of exhaustion context evaluation."""

    has_context: bool
    prior_delta_sum: int
    signal_direction: Direction
    lookback_bars: int
    killer_combo: bool  # ABS_04 + prior TRAP_05
    detail: str


_MIN_BARS_FOR_CONTEXT = 5


class ExhaustionContextFilter:
    """Validates absorption signals against prior delta exhaustion context.

    The core insight: absorption is only a reversal signal when the prior flow
    has EXHAUSTED in the opposite direction. Without exhaustion context,
    absorption bars are noise.
    """

    def __init__(
        self, lookback: int = _DEFAULT_LOOKBACK, min_bars: int = _MIN_BARS_FOR_CONTEXT
    ) -> None:
        self._lookback = lookback
        self._min_bars = min_bars

    def evaluate(
        self,
        signals: list[SignalResult],
        ctx: SessionContext,
        *,
        recent_trap_signals: list[SignalResult] | None = None,
    ) -> ExhaustionContextResult | None:
        """Evaluate exhaustion context for absorption signals in this bar.

        Args:
            signals: All signals fired on the current bar.
            ctx: Session context with delta_history populated.
            recent_trap_signals: Trap signals from prior bars (within lookback window).

        Returns:
            ExhaustionContextResult if absorption signals are present, None otherwise.
        """
        abs_signals = [s for s in signals if s.signal_id in _ABSORPTION_IDS]
        if not abs_signals:
            return None

        # Skip filter when insufficient history (don't block early-session trades)
        if not self.has_sufficient_history(ctx):
            return None

        # Use the absorption signal's direction as the trade direction
        abs_direction = self._consensus_direction(abs_signals)
        if abs_direction is Direction.NEUTRAL:
            return None

        # Compute prior N-bar delta sum
        prior_delta_sum = self._prior_delta_sum(ctx)

        # Exhaustion context: prior delta sum OPPOSES absorption direction
        # Bullish absorption = prior sellers exhausted (negative delta sum)
        # Bearish absorption = prior buyers exhausted (positive delta sum)
        has_context = self._delta_opposes_direction(prior_delta_sum, abs_direction)

        # Check killer combo: ABS_04 present + TRAP_05 in recent history
        killer_combo = self._check_killer_combo(abs_signals, recent_trap_signals)

        detail = self._build_detail(
            has_context, prior_delta_sum, abs_direction, killer_combo
        )

        return ExhaustionContextResult(
            has_context=has_context,
            prior_delta_sum=prior_delta_sum,
            signal_direction=abs_direction,
            lookback_bars=min(self._lookback, len(ctx.delta_history)),
            killer_combo=killer_combo,
            detail=detail,
        )

    def has_sufficient_history(self, ctx: SessionContext) -> bool:
        """True if we have enough bars to evaluate exhaustion context."""
        return len(ctx.delta_history) >= self._min_bars

    def _prior_delta_sum(self, ctx: SessionContext) -> int:
        """Sum of delta over prior N bars (excludes current bar)."""
        if not ctx.delta_history:
            return 0
        history = list(ctx.delta_history)
        # delta_history contains prior bars (current bar not yet appended)
        window = history[-self._lookback:]
        return sum(window)

    @staticmethod
    def _delta_opposes_direction(delta_sum: int, direction: Direction) -> bool:
        """True if prior delta sum opposes the absorption direction.

        Bullish absorption requires prior negative delta (sellers exhausted).
        Bearish absorption requires prior positive delta (buyers exhausted).
        """
        if direction is Direction.BULLISH:
            return delta_sum < 0
        if direction is Direction.BEARISH:
            return delta_sum > 0
        return False

    @staticmethod
    def _consensus_direction(signals: list[SignalResult]) -> Direction:
        """Determine consensus direction from absorption signals."""
        bullish = sum(1 for s in signals if s.direction is Direction.BULLISH)
        bearish = sum(1 for s in signals if s.direction is Direction.BEARISH)
        if bullish > bearish:
            return Direction.BULLISH
        if bearish > bullish:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _check_killer_combo(
        abs_signals: list[SignalResult],
        recent_trap_signals: list[SignalResult] | None,
    ) -> bool:
        """Check ABS_04 + prior TRAP_05 co-occurrence.

        Research: N=11, WR=55%, Avg=+563 ticks ($2,815/trade).
        """
        has_abs04 = any(s.signal_id is SignalId.ABS_04 for s in abs_signals)
        if not has_abs04 or not recent_trap_signals:
            return False
        return any(s.signal_id is SignalId.TRAP_05 for s in recent_trap_signals)

    @staticmethod
    def _build_detail(
        has_context: bool,
        delta_sum: int,
        direction: Direction,
        killer_combo: bool,
    ) -> str:
        ctx_str = "CONFIRMED" if has_context else "ABSENT"
        combo_str = " [KILLER_COMBO: ABS04+TRAP05]" if killer_combo else ""
        return (
            f"Exhaustion context {ctx_str}: "
            f"prior_delta_sum={delta_sum}, "
            f"abs_direction={direction.name}"
            f"{combo_str}"
        )


__all__ = ["ExhaustionContextFilter", "ExhaustionContextResult"]
