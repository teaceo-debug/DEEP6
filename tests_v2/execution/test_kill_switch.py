from __future__ import annotations

import pytest

from deep6v2.execution.kill_switch import KillSwitch, KillSwitchState


@pytest.fixture
def ks() -> KillSwitch:
    return KillSwitch(max_consecutive_losses=3, volatility_threshold=2.0)


class TestKillSwitchStateTransitions:
    def test_initial_state_is_go(self, ks: KillSwitch) -> None:
        assert ks.state == KillSwitchState.GO
        assert ks.allows_new_trades is True

    def test_three_losses_trigger_caution(self, ks: KillSwitch) -> None:
        ks.on_trade_result(-100.0)
        assert ks.state == KillSwitchState.GO
        ks.on_trade_result(-100.0)
        assert ks.state == KillSwitchState.GO
        result = ks.on_trade_result(-100.0)
        assert result == KillSwitchState.CAUTION
        assert ks.state == KillSwitchState.CAUTION

    def test_win_after_caution_resets_to_go(self, ks: KillSwitch) -> None:
        # 3 losses -> CAUTION
        for _ in range(3):
            ks.on_trade_result(-100.0)
        assert ks.state == KillSwitchState.CAUTION

        # Win resets to GO
        result = ks.on_trade_result(50.0)
        assert result == KillSwitchState.GO
        assert ks.allows_new_trades is True

    def test_win_resets_consecutive_counter(self, ks: KillSwitch) -> None:
        ks.on_trade_result(-100.0)
        ks.on_trade_result(-100.0)
        ks.on_trade_result(50.0)  # resets counter
        ks.on_trade_result(-100.0)
        ks.on_trade_result(-100.0)
        assert ks.state == KillSwitchState.GO  # only 2 consecutive losses


class TestKillSwitchDailyLoss:
    def test_daily_loss_breach_triggers_stop(self, ks: KillSwitch) -> None:
        result = ks.on_daily_loss_breach()
        assert result == KillSwitchState.STOP
        assert ks.state == KillSwitchState.STOP

    def test_stop_blocks_trades(self, ks: KillSwitch) -> None:
        ks.on_daily_loss_breach()
        assert ks.allows_new_trades is False


class TestKillSwitchVolatility:
    def test_volatility_spike_triggers_caution(self, ks: KillSwitch) -> None:
        result = ks.on_volatility_spike(current_atr=30.0, baseline_atr=10.0)
        assert result == KillSwitchState.CAUTION

    def test_no_caution_below_threshold(self, ks: KillSwitch) -> None:
        ks.on_volatility_spike(current_atr=15.0, baseline_atr=10.0)
        assert ks.state == KillSwitchState.GO

    def test_zero_baseline_does_not_trigger(self, ks: KillSwitch) -> None:
        ks.on_volatility_spike(current_atr=100.0, baseline_atr=0.0)
        assert ks.state == KillSwitchState.GO


class TestKillSwitchManualAndReset:
    def test_manual_stop(self, ks: KillSwitch) -> None:
        result = ks.manual_stop()
        assert result == KillSwitchState.STOP
        assert ks.allows_new_trades is False

    def test_reset_clears_state(self, ks: KillSwitch) -> None:
        for _ in range(3):
            ks.on_trade_result(-100.0)
        assert ks.state == KillSwitchState.CAUTION

        ks.reset()
        assert ks.state == KillSwitchState.GO
        assert ks.allows_new_trades is True

    def test_reset_clears_consecutive_counter(self, ks: KillSwitch) -> None:
        ks.on_trade_result(-100.0)
        ks.on_trade_result(-100.0)
        ks.reset()
        ks.on_trade_result(-100.0)
        # Only 1 loss after reset, should still be GO
        assert ks.state == KillSwitchState.GO
