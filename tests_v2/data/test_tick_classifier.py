from __future__ import annotations

from datetime import UTC, datetime

from deep6v2.data.tick_classifier import AggressorSide, ClassifiedTick, TickClassifier
from deep6v2.state.dom import DOMState


def _make_dom(best_bid: float | None = None, best_ask: float | None = None) -> DOMState:
    """Create a DOMState with optional BBO pre-set."""
    dom = DOMState(base_price=21000.0, num_levels=4000)
    if best_bid is not None:
        dom.update_level("bid", best_bid, 10)
    if best_ask is not None:
        dom.update_level("ask", best_ask, 10)
    return dom


NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)


class TestBuyAggressor:
    def test_buy_at_best_ask(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.25, size=5, timestamp=NOW)
        assert tick.aggressor == AggressorSide.BUY

    def test_buy_above_ask(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.50, size=3, timestamp=NOW)
        assert tick.aggressor == AggressorSide.BUY


class TestSellAggressor:
    def test_sell_at_best_bid(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.00, size=7, timestamp=NOW)
        assert tick.aggressor == AggressorSide.SELL

    def test_sell_below_bid(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21449.75, size=2, timestamp=NOW)
        assert tick.aggressor == AggressorSide.SELL


class TestUnspecified:
    def test_unspecified_inside_spread(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.125, size=1, timestamp=NOW)
        assert tick.aggressor == AggressorSide.UNSPECIFIED

    def test_unspecified_no_bbo(self):
        dom = DOMState(base_price=21000.0, num_levels=4000)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.00, size=1, timestamp=NOW)
        assert tick.aggressor == AggressorSide.UNSPECIFIED

    def test_unspecified_no_bid(self):
        dom = _make_dom(best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.25, size=1, timestamp=NOW)
        assert tick.aggressor == AggressorSide.UNSPECIFIED

    def test_unspecified_no_ask(self):
        dom = _make_dom(best_bid=21450.00)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.00, size=1, timestamp=NOW)
        assert tick.aggressor == AggressorSide.UNSPECIFIED


class TestClassifiedTickFields:
    def test_classified_tick_fields(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.25, size=5, timestamp=NOW)
        assert tick.price == 21450.25
        assert tick.size == 5
        assert tick.timestamp == NOW
        assert tick.aggressor == AggressorSide.BUY


class TestHelperMethods:
    def test_unspecified_not_directional(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.125, size=1, timestamp=NOW)
        assert not tc.is_buy_aggressor(tick)
        assert not tc.is_sell_aggressor(tick)
        assert tc.is_unspecified(tick)

    def test_buy_helpers(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.25, size=1, timestamp=NOW)
        assert tc.is_buy_aggressor(tick)
        assert not tc.is_sell_aggressor(tick)
        assert not tc.is_unspecified(tick)

    def test_sell_helpers(self):
        dom = _make_dom(best_bid=21450.00, best_ask=21450.25)
        tc = TickClassifier(dom)
        tick = tc.classify(price=21450.00, size=1, timestamp=NOW)
        assert not tc.is_buy_aggressor(tick)
        assert tc.is_sell_aggressor(tick)
        assert not tc.is_unspecified(tick)
