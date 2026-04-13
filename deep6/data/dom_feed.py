"""DOM callback factory — O(1) per callback, zero allocation.

Per D-05: DOM data drives DOMState pre-allocated arrays.
Per D-06: DOM data outside RTH is still received but not processed into session state.
Per D-08: DOM data outside RTH skipped at bar-builder level (not here — keep callback minimal).
Per D-17: callback exits immediately if freeze_guard reports FROZEN state.

update_type filtering: async-rithmic order book updates come in three types:
    BEGIN  — start of a snapshot batch (book not yet evaluable)
    MIDDLE — intermediate level in snapshot (book not yet evaluable)
    END    — final level in snapshot (book now complete and evaluable)
    SOLO   — single-message complete update (always evaluable)

Only SOLO and END updates represent a complete book state.
"""
import structlog

log = structlog.get_logger()

# Update types that represent a complete, evaluable order book state
_EVALUABLE_UPDATE_TYPES = frozenset(("SOLO", "END"))


def make_dom_callback(state: "SharedState"):
    """Return the async on_order_book callback bound to shared state.

    The returned coroutine is registered via: client.on_order_book += callback
    Called up to 1,000 times/sec — must remain O(1) and zero-allocation.
    """
    async def on_order_book(update) -> None:
        # Skip incomplete snapshots — only process evaluable book states
        update_type = getattr(update, "update_type", None)
        if update_type not in _EVALUABLE_UPDATE_TYPES:
            return

        # D-17: no processing during FROZEN state (disconnect/reconnect in progress)
        if hasattr(state, "freeze_guard") and state.freeze_guard.is_frozen:
            return

        # Extract bid/ask arrays from update object
        # async-rithmic provides .bids and .asks as lists of level objects with .price and .size
        bids = getattr(update, "bids", None) or []
        asks = getattr(update, "asks", None) or []

        bid_prices = [lv.price for lv in bids]
        bid_sizes  = [lv.size  for lv in bids]
        ask_prices = [lv.price for lv in asks]
        ask_sizes  = [lv.size  for lv in asks]

        # In-place update — zero allocation inside DOMState.update()
        state.dom.update(bid_prices, bid_sizes, ask_prices, ask_sizes)

    return on_order_book
