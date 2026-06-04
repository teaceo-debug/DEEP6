from __future__ import annotations

from deep6v2.config.execution import ExecutionConfig
from deep6v2.types.execution import OrderSide


class RiskManager:
    def __init__(self, config: ExecutionConfig | None = None) -> None:
        self._config = config or ExecutionConfig()
        self._daily_pnl: float = 0.0
        self._trades_today: int = 0

    def pre_trade_check(self, setup: object) -> tuple[bool, list[str]]:
        """Returns (allowed, reasons). Check all risk gates."""
        del setup

        reasons: list[str] = []
        if self._trades_today >= self._config.max_trades_per_session:
            reasons.append("max_trades_per_session")
        if abs(self._daily_pnl) >= self._config.daily_loss_cap_dollars:
            reasons.append("daily_loss_cap_breached")
        return (len(reasons) == 0, reasons)

    def calculate_position_size(self, stop_distance: float, atr: float, tier_weight: float = 1.0) -> int:
        """Size = floor(risk_budget / stop_distance), capped at max_contracts."""
        del atr

        if stop_distance <= 0 or tier_weight <= 0:
            return 0
        risk_budget = self._config.daily_loss_cap_dollars * 0.1 * tier_weight
        raw_size = risk_budget / (stop_distance * 20.0)
        return min(int(raw_size), self._config.max_contracts)

    def calculate_stop(self, entry_price: float, direction: OrderSide, atr: float) -> float:
        """Stop = max(structural_stop + 2 ticks, 2 × ATR), capped at 1.5% of account."""
        min_stop = 2.0 * atr
        stop_ticks = max(min_stop, 5.0)
        return entry_price - stop_ticks if direction is OrderSide.BUY else entry_price + stop_ticks

    def record_trade_result(self, pnl: float) -> None:
        self._daily_pnl += pnl
        self._trades_today += 1

    def reset_daily(self) -> None:
        self._daily_pnl = 0.0
        self._trades_today = 0

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def is_at_loss_cap_warning(self) -> bool:
        """True if at ≥80% of daily loss cap."""
        return abs(self._daily_pnl) >= self._config.daily_loss_cap_dollars * 0.8


__all__ = ["RiskManager"]
