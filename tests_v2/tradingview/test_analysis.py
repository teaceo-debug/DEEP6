"""Tests for VisualAnalysis — screenshot capture on high-tier signals."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

from deep6v2.tradingview.analysis import VisualAnalysis
from deep6v2.tradingview.client import TradingViewClient
from deep6v2.types.scoring import ScorerResult, SignalTier


def _make_scorer_result(tier: SignalTier) -> ScorerResult:
    """Factory for minimal ScorerResult with the given tier."""
    return ScorerResult(
        tier=tier,
        raw_score=85.0,
        final_score=82.0,
        category_scores={"absorption": 0.9},
        category_count=3,
        confluence_mult=1.1,
        zone_bonus=2.0,
        gex_mult=1.0,
        agreement_mult=1.0,
        ib_mult=1.0,
        vpin_mult=1.0,
        midday_blocked=False,
        active_signals=[],
        veto_reasons=[],
        e10_agreement=None,
        e10_caution=False,
    )


class TestVisualAnalysisDisconnected:
    """All capture methods return None/empty when TV not connected."""

    def setup_method(self) -> None:
        self.va = VisualAnalysis()

    def test_on_score_type_a_returns_none_disconnected(self) -> None:
        result = _make_scorer_result(SignalTier.TYPE_A)
        assert self.va.on_score(result) is None

    def test_on_score_type_b_returns_none_disconnected(self) -> None:
        result = _make_scorer_result(SignalTier.TYPE_B)
        assert self.va.on_score(result) is None

    def test_on_score_type_c_returns_none(self) -> None:
        result = _make_scorer_result(SignalTier.TYPE_C)
        assert self.va.on_score(result) is None

    def test_on_score_quiet_returns_none(self) -> None:
        result = _make_scorer_result(SignalTier.QUIET)
        assert self.va.on_score(result) is None

    def test_generate_trade_report_returns_empty(self) -> None:
        assert self.va.generate_trade_report("session_001") == []


class TestVisualAnalysisConnected:
    """Verify screenshot capture when client is connected."""

    def setup_method(self) -> None:
        self.client = TradingViewClient()
        self.client._connected = True
        self.va = VisualAnalysis(client=self.client)

    def test_on_score_type_a_captures(self) -> None:
        with patch.object(self.client, "capture_screenshot", return_value="/tmp/signal_TYPE_A.png"):
            result = _make_scorer_result(SignalTier.TYPE_A)
            path = self.va.on_score(result)
            assert path == "/tmp/signal_TYPE_A.png"
            self.client.capture_screenshot.assert_called_once_with("signal_TYPE_A")

    def test_on_score_type_b_captures(self) -> None:
        with patch.object(self.client, "capture_screenshot", return_value="/tmp/signal_TYPE_B.png"):
            result = _make_scorer_result(SignalTier.TYPE_B)
            path = self.va.on_score(result)
            assert path == "/tmp/signal_TYPE_B.png"

    def test_on_score_type_c_skips(self) -> None:
        result = _make_scorer_result(SignalTier.TYPE_C)
        assert self.va.on_score(result) is None

    def test_on_score_quiet_skips(self) -> None:
        result = _make_scorer_result(SignalTier.QUIET)
        assert self.va.on_score(result) is None

    def test_generate_trade_report_captures_all_timeframes(self) -> None:
        with patch.object(
            self.client,
            "capture_screenshot",
            side_effect=[
                "/tmp/report_s1_1m.png",
                "/tmp/report_s1_5m.png",
                "/tmp/report_s1_15m.png",
                "/tmp/report_s1_60m.png",
            ],
        ):
            screenshots = self.va.generate_trade_report("s1")
            assert len(screenshots) == 4
            assert "/tmp/report_s1_1m.png" in screenshots

    def test_generate_trade_report_partial_failure(self) -> None:
        with patch.object(
            self.client,
            "capture_screenshot",
            side_effect=["/tmp/report_s1_1m.png", None, "/tmp/report_s1_15m.png", None],
        ):
            screenshots = self.va.generate_trade_report("s1")
            assert len(screenshots) == 2

    def test_on_score_returns_none_when_disconnected_mid_call(self) -> None:
        """Tier matches but client reports not connected."""
        with patch.object(
            type(self.client), "is_connected", new_callable=PropertyMock, return_value=False
        ):
            result = _make_scorer_result(SignalTier.TYPE_A)
            assert self.va.on_score(result) is None

    def test_default_client_created_when_none_passed(self) -> None:
        va = VisualAnalysis()
        assert va._client is not None
        assert va._client.is_connected is False
