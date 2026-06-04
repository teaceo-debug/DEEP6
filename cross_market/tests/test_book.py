from __future__ import annotations

from cross_market.book.book_reconstructor import BookReconstructor
from cross_market.book.mbo_order_book import MBOOrderBook
from cross_market.book.mbp_order_book import MBPOrderBook
from cross_market.book.order_lifecycle_tracker import LifecycleRecord, OrderLifecycleTracker
from cross_market.types.mbo_event import MBOAction, MBOEvent, MBOSide


def evt(
    action: MBOAction,
    *,
    side: MBOSide = MBOSide.BID,
    price: float = 100.0,
    size: int = 1,
    order_id: str = "o1",
    ts: int = 1,
    seq: int = 1,
    priority: int | None = 0,
) -> MBOEvent:
    return MBOEvent(
        action=action,
        side=side,
        price=price,
        size=size,
        order_id=order_id,
        timestamp_exchange_ns=ts,
        sequence_id=seq,
        priority=priority,
    )


def seeded_book() -> MBOOrderBook:
    book = MBOOrderBook()
    book.on_add("b1", 100.0, 10, "B", 1, 0)
    book.on_add("b2", 99.75, 8, "B", 2, 0)
    book.on_add("a1", 100.25, 12, "A", 3, 0)
    book.on_add("a2", 100.50, 7, "A", 4, 0)
    return book


def assert_book_is_sane(book: MBOOrderBook) -> None:
    for level_map in (book.bids, book.asks):
        for level in level_map.values():
            assert level.total_size >= 0
            assert level.order_count >= 0
    bb = book.best_bid()
    ba = book.best_ask()
    if bb is not None and ba is not None:
        assert bb < ba


def test_add_creates_order_and_level_state() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 7)
    assert book.best_bid() == 100.0
    assert book.bids[400].total_size == 5
    assert book.orders["o1"].priority == 7


def test_cancel_removes_order_and_level() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    removed = book.on_cancel("o1", 2)
    assert removed is not None
    assert book.best_bid() is None
    assert "o1" not in book.orders


def test_modify_updates_live_size_and_level_total() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    book.on_modify("o1", 9, 2)
    assert book.orders["o1"].size == 9
    assert book.bids[400].total_size == 9


def test_modify_zero_size_behaves_like_cancel() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    book.on_modify("o1", 0, 2)
    assert book.best_bid() is None
    assert "o1" not in book.orders


def test_trade_partially_reduces_order_and_level_size() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 10, "B", 1, 0)
    book.on_trade("o1", 4, 2)
    assert book.orders["o1"].size == 6
    assert book.bids[400].total_size == 6


def test_trade_fully_removes_order_from_book() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 10, "B", 1, 0)
    book.on_trade("o1", 10, 2)
    assert "o1" not in book.orders
    assert book.best_bid() is None


def test_best_bid_best_ask_mid_and_microprice() -> None:
    book = seeded_book()
    assert book.best_bid() == 100.0
    assert book.best_ask() == 100.25
    assert book.mid() == 100.125
    expected_micro = ((100.25 * 10) + (100.0 * 12)) / 22
    assert book.microprice() == expected_micro


def test_get_depth_returns_sorted_levels() -> None:
    book = seeded_book()
    bids, asks = book.get_depth(2)
    assert bids == [(100.0, 10, 1), (99.75, 8, 1)]
    assert asks == [(100.25, 12, 1), (100.5, 7, 1)]


def test_duplicate_order_id_replaces_old_state_without_leak() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    book.on_add("o1", 99.75, 8, "B", 2, 0)
    assert 400 not in book.bids
    assert book.bids[399].total_size == 8


def test_invalid_negative_modify_raises() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    try:
        book.on_modify("o1", -1, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_invalid_fill_size_raises() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    try:
        book.on_trade("o1", 0, 2)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_cancel_missing_order_returns_none() -> None:
    assert MBOOrderBook().on_cancel("missing", 1) is None


def test_lifecycle_tracker_records_add_modify_trade_cancel() -> None:
    tracker = OrderLifecycleTracker()
    tracker.on_add("o1", 100.0, 10, "B", 1)
    tracker.on_modify("o1", 12)
    tracker.on_trade("o1", 4, 2)
    record = tracker.on_cancel("o1", 3)
    assert record is not None
    assert record.modify_count == 1
    assert record.total_filled == 4
    assert record.cancel_time_ns == 3
    assert record.trade_time_ns == 2


def test_lifecycle_record_properties() -> None:
    record = LifecycleRecord("o1", 100.0, 10, "B", 1, cancel_time_ns=1_000_001, fills=[2, 3])
    assert record.life_ms == 1.0
    assert record.fill_ratio == 0.5
    assert record.was_filled is True
    assert record.total_filled == 5


def test_get_cancelled_unfilled_filters_correctly() -> None:
    tracker = OrderLifecycleTracker()
    tracker.on_add("small", 100.0, 2, "B", 1)
    tracker.on_cancel("small", 2)
    tracker.on_add("filled", 100.0, 10, "B", 3)
    tracker.on_trade("filled", 3, 4)
    tracker.on_cancel("filled", 5)
    tracker.on_add("spoof", 100.0, 20, "B", 6)
    tracker.on_cancel("spoof", 7)
    results = tracker.get_cancelled_unfilled(min_size=10)
    assert [record.order_id for record in results] == ["spoof"]


def test_reconstructor_processes_basic_lifecycle() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="o1", price=100.0, size=10, seq=1))
    recon.process(evt(MBOAction.MODIFY, order_id="o1", price=100.0, size=8, seq=2))
    recon.process(evt(MBOAction.TRADE, order_id="o1", price=100.0, size=3, seq=3))
    recon.process(evt(MBOAction.CANCEL, order_id="o1", price=100.0, size=0, seq=4))
    assert recon._last_sequence == 4
    assert recon.tracker.get("o1").total_filled == 3
    assert recon.best_bid is None


def test_reconstructor_clear_resets_book_only() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="o1", seq=1))
    recon.process(evt(MBOAction.CLEAR, side=MBOSide.UNKNOWN, size=0, order_id="", seq=2))
    assert recon.best_bid is None
    assert recon.tracker.get("o1") is not None


def test_fill_action_routes_like_trade() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="o1", size=6, seq=1))
    recon.process(evt(MBOAction.FILL, order_id="o1", size=6, seq=2))
    assert recon.tracker.get("o1").total_filled == 6
    assert recon.book.best_bid() is None


def test_mbp_order_book_derives_aggregated_depth() -> None:
    book = seeded_book()
    mbp = MBPOrderBook(book, n_levels=1)
    assert mbp.bids[0].price == 100.0
    assert mbp.bids[0].size == 10
    assert mbp.asks[0].price == 100.25
    assert mbp.spread_ticks == 1.0


def test_spoof_scenario_cancelled_unfilled_within_five_seconds() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="spoof", size=50, ts=1, seq=1))
    recon.process(evt(MBOAction.CANCEL, order_id="spoof", size=0, ts=4_000_000_000, seq=2))
    record = recon.tracker.get_cancelled_unfilled(min_size=10)[0]
    assert record.order_id == "spoof"
    assert record.life_ms == 3999.999999


def test_iceberg_style_refresh_sequence_keeps_book_consistent() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="ice1", price=100.0, size=10, seq=1))
    recon.process(evt(MBOAction.TRADE, order_id="ice1", price=100.0, size=10, seq=2))
    recon.process(evt(MBOAction.ADD, order_id="ice2", price=100.0, size=10, seq=3))
    recon.process(evt(MBOAction.TRADE, order_id="ice2", price=100.0, size=4, seq=4))
    recon.process(evt(MBOAction.ADD, order_id="ice3", price=100.0, size=6, seq=5))
    assert recon.book.bids[400].total_size == 12
    assert_book_is_sane(recon.book)


def test_absorption_style_bid_holds_after_large_trade_volume() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="rest1", price=100.0, size=20, seq=1))
    recon.process(evt(MBOAction.ADD, order_id="rest2", price=100.0, size=15, seq=2))
    recon.process(evt(MBOAction.ADD, side=MBOSide.ASK, order_id="ask1", price=100.25, size=10, seq=3))
    recon.process(evt(MBOAction.TRADE, order_id="rest1", price=100.0, size=18, seq=4))
    recon.process(evt(MBOAction.ADD, order_id="refresh", price=100.0, size=25, seq=5))
    assert recon.best_bid == 100.0
    assert recon.book.bids[400].total_size == 42
    assert_book_is_sane(recon.book)


def test_book_integrity_after_mixed_sequence() -> None:
    recon = BookReconstructor()
    events = [
        evt(MBOAction.ADD, order_id="b1", price=100.0, size=10, seq=1),
        evt(MBOAction.ADD, order_id="b2", price=99.75, size=6, seq=2),
        evt(MBOAction.ADD, side=MBOSide.ASK, order_id="a1", price=100.25, size=9, seq=3),
        evt(MBOAction.MODIFY, order_id="b1", price=100.0, size=12, seq=4),
        evt(MBOAction.TRADE, order_id="a1", side=MBOSide.ASK, price=100.25, size=4, seq=5),
        evt(MBOAction.CANCEL, order_id="b2", price=99.75, size=0, seq=6),
    ]
    for event in events:
        recon.process(event)
    assert recon.book.bids[400].total_size == 12
    assert recon.book.asks[401].total_size == 5
    assert_book_is_sane(recon.book)


def test_trade_overfill_is_clamped_not_negative() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    book.on_trade("o1", 9, 2)
    assert book.best_bid() is None
    assert_book_is_sane(book)


def test_microprice_none_when_one_side_missing() -> None:
    book = MBOOrderBook()
    book.on_add("o1", 100.0, 5, "B", 1, 0)
    assert book.microprice() is None


def test_tracker_get_returns_none_for_unknown_order() -> None:
    assert OrderLifecycleTracker().get("missing") is None


def test_best_bid_less_than_best_ask_across_sequence() -> None:
    recon = BookReconstructor()
    recon.process(evt(MBOAction.ADD, order_id="b1", price=100.0, size=10, seq=1))
    recon.process(evt(MBOAction.ADD, side=MBOSide.ASK, order_id="a1", price=100.25, size=10, seq=2))
    recon.process(evt(MBOAction.ADD, order_id="b2", price=99.75, size=5, seq=3))
    recon.process(evt(MBOAction.TRADE, side=MBOSide.ASK, order_id="a1", price=100.25, size=4, seq=4))
    assert_book_is_sane(recon.book)
