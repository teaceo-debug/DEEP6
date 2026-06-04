from __future__ import annotations

from dataclasses import dataclass

from deep6v2.execution.rithmic_broker import Fill
from deep6v2.scoring.hysteresis import is_midday_blocked
from deep6v2.types.execution import OrderSide, TradeState, TradeTransition
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.signal import Direction, SignalId


@dataclass
class TradeSetupContext:
    entry_bar_index: int
    direction: OrderSide
    tier: SignalTier
    entry_price: float
    stop_price: float
    target_price: float
    age_bars: int = 0


class TradeDecisionMachine:
    def __init__(self, max_setup_age: int = 3, cooldown_bars: int = 2) -> None:
        self._state = TradeState.IDLE
        self._setup: TradeSetupContext | None = None
        self._max_setup_age = max_setup_age
        self._cooldown_bars = cooldown_bars
        self._cooldown_remaining = 0
        self._transitions: list[tuple[TradeState, TradeState, str]] = []

    @property
    def state(self) -> TradeState:
        return self._state

    @property
    def setup(self) -> TradeSetupContext | None:
        return self._setup

    @property
    def cooldown_remaining(self) -> int:
        return self._cooldown_remaining

    @property
    def transitions(self) -> list[tuple[TradeState, TradeState, str]]:
        return list(self._transitions)

    def on_session_open(self) -> None:
        if self._state is TradeState.IDLE:
            self._transition(TradeState.WATCHING, TradeTransition.T1)

    def on_session_close(self) -> None:
        if self._state is TradeState.WATCHING:
            self._transition(TradeState.IDLE, TradeTransition.T10)
            self._setup = None

    def on_score(self, result: ScorerResult, bar_index: int, price: float, atr: float) -> None:
        if self._state is not TradeState.WATCHING:
            return
        if result.tier not in {SignalTier.TYPE_A, SignalTier.TYPE_B}:
            return
        if result.midday_blocked:
            return

        direction = self._resolve_direction(result)
        if direction is None:
            return

        self._setup = self._build_setup(
            bar_index=bar_index,
            direction=direction,
            tier=result.tier,
            entry_price=price,
            atr=atr,
        )
        self._transition(TradeState.ARMED, TradeTransition.T2)

    def on_bar_close(self, bar_index: int) -> None:
        if self._state is TradeState.ARMED and self._setup is not None:
            self._setup.age_bars = max(0, bar_index - self._setup.entry_bar_index)
            reasons = self.check_invalidation(bar_index=bar_index)
            if reasons:
                return
            if bar_index >= self._setup.entry_bar_index + 1:
                self._transition(TradeState.PENDING_ENTRY, TradeTransition.T3)
                return

        if self._state is TradeState.CLOSED and self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            if self._cooldown_remaining == 0:
                self._transition(TradeState.WATCHING, TradeTransition.T7)

    def on_fill(self, fill: Fill) -> None:
        if self._state is TradeState.PENDING_ENTRY:
            self._transition(TradeState.IN_POSITION, TradeTransition.T4)
            return
        if self._state is TradeState.IN_POSITION:
            self._transition(TradeState.IN_POSITION, TradeTransition.T11)

    def on_exit_trigger(self, reason: str) -> None:
        if self._state is not TradeState.IN_POSITION:
            return
        self._transition(TradeState.EXITING, f"{TradeTransition.T5.value}:{reason}")

    def on_position_flat(self) -> None:
        if self._state is not TradeState.EXITING:
            return
        self._transition(TradeState.CLOSED, TradeTransition.T6)
        self._setup = None
        self._cooldown_remaining = self._cooldown_bars

    def check_invalidation(self, **context) -> list[str]:
        if self._setup is None:
            return []

        bar_index = int(context.get("bar_index", self._setup.entry_bar_index + self._setup.age_bars))
        current_price = context.get("current_price")
        kill_switch = str(context.get("kill_switch", "")).upper()
        bars_to_session_close = context.get("bars_to_session_close")
        session_closing_soon = bool(context.get("session_closing_soon", False))
        freeze_guard = bool(context.get("freeze_guard", False))
        spoof_veto = bool(context.get("spoof_veto", False))
        opposing_signal = bool(context.get("opposing_signal", False))
        opposing_tier = context.get("opposing_tier")
        daily_loss_pct = context.get("daily_loss_pct", 0.0)

        reasons: list[str] = []

        if current_price is not None and self._is_beyond_stop(float(current_price)):
            reasons.append("I1")
        if opposing_signal or opposing_tier in {SignalTier.TYPE_A, SignalTier.TYPE_B}:
            reasons.append("I2")
        if kill_switch in {"CAUTION", "STOP"}:
            reasons.append("I3")
        if session_closing_soon or (bars_to_session_close is not None and int(bars_to_session_close) <= 15):
            reasons.append("I4")
        if self._setup.age_bars > self._max_setup_age:
            reasons.append("I5")
        if is_midday_blocked(bar_index):
            reasons.append("I6")
        if freeze_guard:
            reasons.append("I7")
        if self._daily_loss_cap_hit(daily_loss_pct):
            reasons.append("I8")
        if spoof_veto or SignalId.SPOOF_VETO in self._active_signal_ids(context):
            reasons.append("I9")

        if reasons and self._state in {TradeState.ARMED, TradeState.PENDING_ENTRY}:
            self._setup = None
            self._transition(TradeState.WATCHING, TradeTransition.T8 if self._state is TradeState.ARMED else TradeTransition.T9)

        return reasons

    def _build_setup(
        self,
        *,
        bar_index: int,
        direction: OrderSide,
        tier: SignalTier,
        entry_price: float,
        atr: float,
    ) -> TradeSetupContext:
        risk = atr if atr > 0 else max(abs(entry_price) * 0.001, 1.0)
        if direction is OrderSide.BUY:
            stop_price = entry_price - risk
            target_price = entry_price + (2.0 * risk)
        else:
            stop_price = entry_price + risk
            target_price = entry_price - (2.0 * risk)
        return TradeSetupContext(
            entry_bar_index=bar_index,
            direction=direction,
            tier=tier,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

    def _resolve_direction(self, result: ScorerResult) -> OrderSide | None:
        for signal in result.active_signals:
            if signal.direction is Direction.BULLISH:
                return OrderSide.BUY
            if signal.direction is Direction.BEARISH:
                return OrderSide.SELL
        return None

    def _is_beyond_stop(self, current_price: float) -> bool:
        if self._setup is None:
            return False
        if self._setup.direction is OrderSide.BUY:
            return current_price <= self._setup.stop_price
        return current_price >= self._setup.stop_price

    @staticmethod
    def _active_signal_ids(context: dict[str, object]) -> set[SignalId]:
        signal_ids = context.get("signal_ids")
        if signal_ids is None:
            return set()
        return {signal_id for signal_id in signal_ids if isinstance(signal_id, SignalId)}

    @staticmethod
    def _daily_loss_cap_hit(value: object) -> bool:
        if not isinstance(value, (int, float)):
            return False
        numeric = float(value)
        if numeric > 1.0:
            numeric /= 100.0
        return numeric >= 0.80

    def _transition(self, to_state: TradeState, transition: TradeTransition | str) -> None:
        from_state = self._state
        self._state = to_state
        transition_name = transition.value if isinstance(transition, TradeTransition) else transition
        self._transitions.append((from_state, to_state, transition_name))


__all__ = ["TradeDecisionMachine", "TradeSetupContext"]
