from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from deep6v2.config.scoring import ScoringConfig
from deep6v2.scoring.exhaustion_context import (
    ExhaustionContextFilter,
    ExhaustionContextResult,
)
from deep6v2.types.bar import FootprintBar
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import (
    Direction,
    SIGNAL_TO_CATEGORY,
    SignalCategory,
    SignalId,
    SignalResult,
)

_TRAP_IDS: frozenset[SignalId] = frozenset(
    {SignalId.TRAP_01, SignalId.TRAP_02, SignalId.TRAP_03, SignalId.TRAP_04, SignalId.TRAP_05}
)

_ABSORPTION_IDS: frozenset[SignalId] = frozenset(
    {SignalId.ABS_01, SignalId.ABS_02, SignalId.ABS_03, SignalId.ABS_04}
)

_EXHAUSTION_IDS: frozenset[SignalId] = frozenset(
    {SignalId.EXH_01, SignalId.EXH_02, SignalId.EXH_03, SignalId.EXH_04, SignalId.EXH_05, SignalId.EXH_06}
)

_CORE_IDS: frozenset[SignalId] = _ABSORPTION_IDS | _EXHAUSTION_IDS | frozenset({SignalId.IMB_03})

_CHASE_DELTA_THRESHOLD = 50


class EntryDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    eligible: bool
    tier: SignalTier
    veto_reasons: list[str]
    confluence_type: str  # "STACKED", "VA_EXTREME", "NONE"
    direction: Direction
    exhaustion_context: ExhaustionContextResult | None = None


class EntryGate:
    def __init__(self, config: ScoringConfig | None = None) -> None:
        self._config = config or ScoringConfig()
        self._exhaustion_filter = ExhaustionContextFilter()

    def evaluate(
        self,
        scorer_result: ScorerResult,
        bar: FootprintBar,
        ctx: SessionContext,
        *,
        recent_trap_signals: list[SignalResult] | None = None,
    ) -> EntryDecision:
        signals = scorer_result.active_signals
        tier = scorer_result.tier
        direction = self._determine_direction(signals)

        veto_reasons = self._check_vetoes(signals, bar, direction)
        confluence_type = self._check_confluence(signals, bar, ctx, direction)

        # Exhaustion context: validate absorption signals against prior delta flow
        exhaustion_ctx = self._exhaustion_filter.evaluate(
            signals, ctx, recent_trap_signals=recent_trap_signals
        )

        has_vetoes = len(veto_reasons) > 0

        if tier is SignalTier.TYPE_A:
            has_abs_or_exh = any(
                s.signal_id in _ABSORPTION_IDS or s.signal_id in _EXHAUSTION_IDS for s in signals
            )
            agreeing = self._agreeing_categories(signals, direction)
            eligible = not has_vetoes and has_abs_or_exh and agreeing >= 5
        elif tier is SignalTier.TYPE_B:
            has_core = any(s.signal_id in _CORE_IDS for s in signals)
            eligible = not has_vetoes and has_core
        else:
            eligible = False

        # Apply exhaustion context filter to absorption-driven entries
        has_absorption = any(s.signal_id in _ABSORPTION_IDS for s in signals)
        if eligible and has_absorption and exhaustion_ctx is not None:
            if not exhaustion_ctx.has_context and not exhaustion_ctx.killer_combo:
                # Absorption without exhaustion context = no edge (research: -3.2 ticks avg)
                eligible = False
                veto_reasons.append(
                    f"exhaustion_context_absent: prior_delta_sum={exhaustion_ctx.prior_delta_sum} "
                    f"does not oppose {direction.name}"
                )

        # Killer combo override: ABS_04 + TRAP_05 bypasses normal tier requirements
        if not eligible and exhaustion_ctx is not None and exhaustion_ctx.killer_combo:
            if tier is not SignalTier.QUIET and not has_vetoes:
                eligible = True
                veto_reasons = [r for r in veto_reasons if "exhaustion_context" not in r]

        return EntryDecision(
            eligible=eligible,
            tier=tier,
            veto_reasons=veto_reasons,
            confluence_type=confluence_type,
            direction=direction,
            exhaustion_context=exhaustion_ctx,
        )

    @staticmethod
    def _determine_direction(signals: list[SignalResult]) -> Direction:
        bullish = sum(1 for s in signals if s.direction is Direction.BULLISH)
        bearish = sum(1 for s in signals if s.direction is Direction.BEARISH)
        if bullish > bearish:
            return Direction.BULLISH
        if bearish > bullish:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _check_vetoes(
        signals: list[SignalResult],
        bar: FootprintBar,
        direction: Direction,
    ) -> list[str]:
        reasons: list[str] = []

        trap_count = sum(1 for s in signals if s.signal_id in _TRAP_IDS)
        if trap_count >= 3:
            reasons.append(f"trap_veto: {trap_count} TRAP signals")

        if direction is Direction.BULLISH and bar.delta > _CHASE_DELTA_THRESHOLD:
            reasons.append(f"chase_veto: delta {bar.delta} chasing bullish")
        elif direction is Direction.BEARISH and bar.delta < -_CHASE_DELTA_THRESHOLD:
            reasons.append(f"chase_veto: delta {bar.delta} chasing bearish")

        if any(s.signal_id is SignalId.SPOOF_VETO for s in signals):
            reasons.append("spoof_veto: SPOOF_VETO flag present")

        if any(s.signal_id is SignalId.PIN_REGIME for s in signals):
            reasons.append("pin_veto: PIN_REGIME flag present")

        return reasons

    @staticmethod
    def _check_confluence(
        signals: list[SignalResult],
        bar: FootprintBar,
        ctx: SessionContext,
        direction: Direction,
    ) -> str:
        has_abs = any(s.signal_id in _ABSORPTION_IDS and s.direction is direction for s in signals)
        has_exh = any(s.signal_id in _EXHAUSTION_IDS and s.direction is direction for s in signals)
        if has_abs and has_exh:
            return "STACKED"

        has_strong = any(s.strength >= 0.75 for s in signals)
        near_va = abs(bar.close - ctx.vah) <= 0.5 or abs(bar.close - ctx.val) <= 0.5
        if has_strong and near_va:
            return "VA_EXTREME"

        return "NONE"

    @staticmethod
    def _agreeing_categories(signals: list[SignalResult], direction: Direction) -> int:
        categories: set[SignalCategory] = set()
        for s in signals:
            if s.direction is direction:
                cat = SIGNAL_TO_CATEGORY.get(s.signal_id)
                if cat is not None:
                    categories.add(cat)
        return len(categories)


__all__ = ["EntryDecision", "EntryGate"]
