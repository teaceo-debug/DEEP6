from __future__ import annotations

from deep6v2.config.execution import ExecutionConfig
from deep6v2.execution.risk_manager import RiskManager


def test_max_trades_per_session_blocks_new_trades() -> None:
    manager = RiskManager(ExecutionConfig(max_trades_per_session=10))

    for _ in range(10):
        manager.record_trade_result(25.0)

    allowed, reasons = manager.pre_trade_check(setup=None)

    assert allowed is False
    assert reasons == ["max_trades_per_session"]


def test_daily_loss_cap_halts_trading_after_three_losses_over_500() -> None:
    manager = RiskManager(ExecutionConfig(daily_loss_cap_dollars=500.0))

    for loss in (-200.0, -175.0, -150.0):
        manager.record_trade_result(loss)

    allowed, reasons = manager.pre_trade_check(setup=None)

    assert manager.daily_pnl == -525.0
    assert allowed is False
    assert reasons == ["daily_loss_cap_breached"]


def test_position_size_calculation_with_stop_distance() -> None:
    manager = RiskManager(ExecutionConfig(max_contracts=2, daily_loss_cap_dollars=500.0))

    size = manager.calculate_position_size(stop_distance=1.0, atr=3.0)

    assert size == 2


def test_loss_cap_warning_at_eighty_percent() -> None:
    manager = RiskManager(ExecutionConfig(daily_loss_cap_dollars=500.0))

    manager.record_trade_result(-400.0)

    assert manager.is_at_loss_cap_warning is True
