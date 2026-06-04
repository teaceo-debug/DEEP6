"""Tests for TradingViewClient — all tests verify graceful degradation."""

from __future__ import annotations

from deep6v2.tradingview.client import ChartState, TradingViewClient


class TestChartState:
    def test_dataclass_fields(self) -> None:
        cs = ChartState(symbol="NQ1!", timeframe="5", indicators=["RSI", "VWAP"])
        assert cs.symbol == "NQ1!"
        assert cs.timeframe == "5"
        assert cs.indicators == ["RSI", "VWAP"]


class TestTradingViewClientDisconnected:
    """All methods must degrade gracefully when TV is not running."""

    def setup_method(self) -> None:
        self.client = TradingViewClient()

    def test_initial_state_disconnected(self) -> None:
        assert self.client.is_connected is False

    def test_connect_returns_false(self) -> None:
        result = self.client.connect()
        assert result is False
        assert self.client.is_connected is False

    def test_get_chart_state_returns_none(self) -> None:
        assert self.client.get_chart_state() is None

    def test_get_ohlcv_returns_none(self) -> None:
        assert self.client.get_ohlcv() is None
        assert self.client.get_ohlcv(count=50) is None

    def test_get_study_values_returns_none(self) -> None:
        assert self.client.get_study_values() is None

    def test_capture_screenshot_returns_none(self) -> None:
        assert self.client.capture_screenshot() is None
        assert self.client.capture_screenshot(filename="test") is None

    def test_inject_pine_script_returns_false(self) -> None:
        assert self.client.inject_pine_script("indicator('test')") is False


class TestTradingViewClientConnected:
    """Verify methods route through when connected (via mock)."""

    def setup_method(self) -> None:
        self.client = TradingViewClient()
        # Force connected state for branch coverage
        self.client._connected = True

    def test_is_connected_true(self) -> None:
        assert self.client.is_connected is True

    def test_get_chart_state_stub_returns_none(self) -> None:
        # Stub implementation returns None even when connected
        assert self.client.get_chart_state() is None

    def test_get_ohlcv_stub_returns_none(self) -> None:
        assert self.client.get_ohlcv() is None

    def test_get_study_values_stub_returns_none(self) -> None:
        assert self.client.get_study_values() is None

    def test_capture_screenshot_stub_returns_none(self) -> None:
        assert self.client.capture_screenshot() is None

    def test_inject_pine_script_stub_returns_false(self) -> None:
        assert self.client.inject_pine_script("test") is False
