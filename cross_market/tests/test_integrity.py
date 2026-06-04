"""Tests for all MBO book integrity hard-gate checks."""
from __future__ import annotations

from cross_market.book.book_integrity import AlertSeverity, BookIntegrityValidator
from cross_market.book.mbo_order_book import MBOOrderBook


def make_book_with_levels() -> MBOOrderBook:
    book = MBOOrderBook()
    book.on_add("B001", 21550.00, 100, "B", 1_000_000, 1)
    book.on_add("A001", 21550.25, 80, "A", 1_000_001, 1)
    return book


def test_sequence_gap_detected() -> None:
    book = make_book_with_levels()
    validator = BookIntegrityValidator()
    validator.validate(book, 100, 1_000.0)
    alerts = validator.validate(book, 102, 1_001.0)
    assert any(alert.check_type == "SEQUENCE_GAP" for alert in alerts)


def test_crossed_book_detected() -> None:
    book = MBOOrderBook()
    book.on_add("B001", 21550.50, 100, "B", 1_000, 1)
    book.on_add("A001", 21550.00, 80, "A", 1_001, 1)
    validator = BookIntegrityValidator()
    alerts = validator.validate(book, 1, 1_000.0)
    assert any(
        alert.severity == AlertSeverity.CRITICAL and alert.check_type == "CROSSED_BOOK"
        for alert in alerts
    )


def test_negative_bid_size_detected() -> None:
    book = make_book_with_levels()
    best_bid_tick = max(book.bids)
    book.bids[best_bid_tick].total_size = -1
    validator = BookIntegrityValidator()
    alerts = validator.validate(book, 1, 1_000.0)
    assert any("bid at" in alert.detail and alert.check_type == "NEGATIVE_SIZE" for alert in alerts)


def test_negative_ask_size_detected() -> None:
    book = make_book_with_levels()
    best_ask_tick = min(book.asks)
    book.asks[best_ask_tick].total_size = -1
    validator = BookIntegrityValidator()
    alerts = validator.validate(book, 1, 1_000.0)
    assert any("ask at" in alert.detail and alert.check_type == "NEGATIVE_SIZE" for alert in alerts)


def test_stale_level_warns() -> None:
    book = make_book_with_levels()
    validator = BookIntegrityValidator()
    best_bid_tick = max(book.bids)
    best_ask_tick = min(book.asks)
    validator.record_update(best_bid_tick, 1_000.0)
    validator.record_update(best_ask_tick, 1_000.0)
    alerts = validator.validate(book, 1, 31_500.0)
    stale = [alert for alert in alerts if alert.check_type == "STALE_LEVEL"]
    assert len(stale) == 2
    assert all(alert.severity == AlertSeverity.WARN for alert in stale)


def test_empty_book_warns() -> None:
    validator = BookIntegrityValidator()
    alerts = validator.validate(MBOOrderBook(), 1, 1_000.0)
    assert any(alert.check_type == "EMPTY_BOOK" for alert in alerts)


def test_valid_book_has_no_error_or_critical_alerts() -> None:
    book = make_book_with_levels()
    validator = BookIntegrityValidator()
    alerts = validator.validate(book, 1, 1_000.0)
    assert not [a for a in alerts if a.severity in (AlertSeverity.ERROR, AlertSeverity.CRITICAL)]


def test_consumers_pause_and_clear_on_critical() -> None:
    book = MBOOrderBook()
    book.on_add("B001", 21550.50, 100, "B", 1_000, 1)
    book.on_add("A001", 21550.00, 80, "A", 1_001, 1)
    validator = BookIntegrityValidator()
    validator.validate(book, 1, 1_000.0)
    assert validator.consumers_paused is True
    validator.clear_pause()
    assert validator.consumers_paused is False
