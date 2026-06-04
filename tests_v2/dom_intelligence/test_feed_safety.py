from __future__ import annotations

import pytest

from deep6v2.signals.dom.adapters.live_adapter import FeedStaleError, LiveDOMAdapter
from deep6v2.signals.dom.feed_safety import FeedState, FeedStateManager
from deep6v2.state.dom import DOMState
from deep6v2.types.dom import DOMUpdate
from deep6v2.types.execution import OrderSide


@pytest.fixture()
def dom_state() -> DOMState:
    return DOMState(base_price=20_000.0, num_levels=4000)


@pytest.fixture()
def adapter(dom_state: DOMState) -> LiveDOMAdapter:
    return LiveDOMAdapter(dom_state)


@pytest.fixture()
def manager(adapter: LiveDOMAdapter) -> FeedStateManager:
    return FeedStateManager(adapter)


def _bid_update(price: float = 20_010.0, volume: int = 100) -> DOMUpdate:
    return DOMUpdate(side=OrderSide.BUY, level=0, price=price, volume=volume)


def _ask_update(price: float = 20_010.25, volume: int = 120) -> DOMUpdate:
    return DOMUpdate(side=OrderSide.SELL, level=0, price=price, volume=volume)


def test_initial_state_is_connected(manager: FeedStateManager) -> None:
    assert manager.state is FeedState.CONNECTED
    assert manager.is_safe_for_detection() is True
    assert manager.transition_history() == []


def test_disconnect_transitions_to_disconnected_and_marks_adapter_stale(manager: FeedStateManager, adapter: LiveDOMAdapter) -> None:
    transition = manager.on_disconnect("network drop")

    assert transition.from_state is FeedState.CONNECTED
    assert transition.to_state is FeedState.DISCONNECTED
    assert adapter.is_stale() is True
    assert manager.state is FeedState.DISCONNECTED


def test_reconnect_transitions_to_connected_and_clears_adapter_stale(manager: FeedStateManager, adapter: LiveDOMAdapter) -> None:
    manager.on_disconnect("network drop")

    transition = manager.on_reconnect()

    assert transition.to_state is FeedState.CONNECTED
    assert adapter.is_stale() is False
    assert manager.state is FeedState.CONNECTED


def test_stale_detected_transitions_to_stale(manager: FeedStateManager, adapter: LiveDOMAdapter) -> None:
    transition = manager.on_stale_detected("slow feed")

    assert transition.to_state is FeedState.STALE
    assert adapter.is_stale() is True
    assert manager.state is FeedState.STALE


@pytest.mark.parametrize("action", ["disconnect", "stale"])
def test_is_safe_for_detection_is_false_in_stale_and_disconnected_states(
    manager: FeedStateManager,
    action: str,
) -> None:
    if action == "disconnect":
        manager.on_disconnect("link loss")
    else:
        manager.on_stale_detected("lag")

    assert manager.is_safe_for_detection() is False


def test_session_rollover_resets_adapter_state_without_leaking_prior_session_data(
    manager: FeedStateManager,
    adapter: LiveDOMAdapter,
) -> None:
    adapter.set_session("session-a")
    adapter.on_dom_update(_bid_update())
    adapter.on_dom_update(_ask_update())
    manager.on_stale_detected("pre-rollover stale")

    transition = manager.on_session_rollover("session-b")

    assert transition.to_state is FeedState.CONNECTED
    assert adapter.session_id == "session-b"
    assert adapter.version == 0
    assert adapter.is_stale() is False
    assert adapter._dom_state.get_best_bid() is None
    assert adapter._dom_state.get_best_ask() is None
    assert manager.state is FeedState.CONNECTED


def test_transition_history_records_all_transitions_in_order(manager: FeedStateManager) -> None:
    manager.on_disconnect("drop")
    manager.on_reconnect()
    manager.on_stale_detected("lag")
    manager.on_reconnect()

    assert [transition.to_state for transition in manager.transition_history()] == [
        FeedState.DISCONNECTED,
        FeedState.RECONNECTING,
        FeedState.CONNECTED,
        FeedState.STALE,
        FeedState.RECONNECTING,
        FeedState.CONNECTED,
    ]


def test_disconnect_reconnect_stale_reconnect_chain_produces_correct_state_sequence(
    manager: FeedStateManager,
    adapter: LiveDOMAdapter,
) -> None:
    states = [manager.state]

    manager.on_disconnect("drop")
    states.append(manager.state)

    manager.on_reconnect()
    states.append(manager.state)

    manager.on_stale_detected("slow feed")
    states.append(manager.state)

    manager.on_reconnect()
    states.append(manager.state)

    assert states == [
        FeedState.CONNECTED,
        FeedState.DISCONNECTED,
        FeedState.CONNECTED,
        FeedState.STALE,
        FeedState.CONNECTED,
    ]
    assert adapter.is_stale() is False


def test_no_stale_state_leaks_through_after_disconnect_and_reconnect(
    manager: FeedStateManager,
    adapter: LiveDOMAdapter,
) -> None:
    adapter.mark_stale()
    manager.on_disconnect("drop")
    manager.on_reconnect()

    snap = adapter.on_dom_update(_bid_update(volume=77))

    assert adapter.is_stale() is False
    assert manager.is_safe_for_detection() is True
    assert snap.bids[0].volume == 77
    with pytest.raises(FeedStaleError):
        # Re-mark stale and confirm the guard still works after recovery.
        adapter.mark_stale()
        adapter.on_dom_update(_bid_update(volume=88))
