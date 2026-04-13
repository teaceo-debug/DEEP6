"""FootprintBar accumulator tests — verifies bid/ask per level correctness."""
import pytest
from collections import defaultdict
from deep6.state.footprint import (
    FootprintLevel, FootprintBar, BarHistory,
    price_to_tick, tick_to_price,
)

TICK_SIZE = 0.25


def test_price_to_tick_nq():
    assert price_to_tick(21000.0) == 84000
    assert price_to_tick(21000.25) == 84001
    assert price_to_tick(20999.75) == 83999


def test_tick_to_price():
    assert tick_to_price(84000) == pytest.approx(21000.0)
    assert tick_to_price(84001) == pytest.approx(21000.25)


def test_add_trade_ask_aggressor():
    bar = FootprintBar()
    bar.add_trade(21000.0, 5, aggressor=1)  # BUY = ask_vol
    assert bar.levels[84000].ask_vol == 5
    assert bar.levels[84000].bid_vol == 0


def test_add_trade_bid_aggressor():
    bar = FootprintBar()
    bar.add_trade(21000.0, 3, aggressor=2)  # SELL = bid_vol
    assert bar.levels[84000].bid_vol == 3
    assert bar.levels[84000].ask_vol == 0


def test_add_trade_accumulates():
    bar = FootprintBar()
    bar.add_trade(21000.0, 5, aggressor=1)
    bar.add_trade(21000.0, 3, aggressor=1)
    assert bar.levels[84000].ask_vol == 8


def test_finalize_bar_delta():
    bar = FootprintBar()
    bar.add_trade(21000.0, 10, aggressor=1)  # ask +10
    bar.add_trade(21000.0, 3,  aggressor=2)  # bid +3
    bar.finalize()
    assert bar.bar_delta == 7  # 10 - 3


def test_finalize_poc():
    bar = FootprintBar()
    bar.add_trade(21000.0, 100, aggressor=1)
    bar.add_trade(21000.25, 5, aggressor=2)
    bar.finalize()
    assert bar.poc_price == pytest.approx(21000.0)


def test_finalize_cvd():
    bar = FootprintBar()
    bar.add_trade(21000.0, 10, aggressor=1)
    bar.finalize(prior_cvd=50)
    assert bar.cvd == 60  # 50 + 10


def test_finalize_bar_range():
    bar = FootprintBar()
    bar.add_trade(21000.0, 5, aggressor=1)
    bar.add_trade(21001.0, 5, aggressor=2)
    bar.finalize()
    assert bar.bar_range == pytest.approx(1.0)


def test_empty_bar_finalize():
    bar = FootprintBar()
    bar.finalize()
    assert bar.bar_delta == 0
    assert bar.poc_price == 0.0


def test_bar_history_maxlen():
    from deep6.state.footprint import BarHistory
    h = BarHistory()
    for i in range(205):
        h.appendleft(FootprintBar())
    assert len(h) == 200
