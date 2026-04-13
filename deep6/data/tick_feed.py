"""Tick callback factory — LAST_TRADE drives the aggressor gate and footprint accumulator.

Per D-02: on_tick callback receives LAST_TRADE events from async-rithmic.
Per D-03: CRITICAL — aggressor gate must pass before forwarding to bar builders.
          Accumulator code never runs until TransactionType.BUY/SELL is confirmed.
Per D-17: callback exits immediately if freeze_guard reports FROZEN state.

Tick data structure (from async-rithmic LAST_TRADE callback):
    tick.data_type  — DataType enum value
    tick.last_trade — LastTrade object with fields:
        .price     (float) — trade price
        .size      (int)   — trade quantity
        .aggressor (int)   — TransactionType: 0=UNSPECIFIED, 1=BUY, 2=SELL
"""
import structlog
from async_rithmic import DataType

from deep6.data.rithmic import record_aggressor_sample, aggressor_verification_gate

log = structlog.get_logger()


def make_tick_callback(state: "SharedState"):
    """Return the async on_tick callback bound to shared state.

    The returned coroutine is registered via: client.on_tick += callback

    Only LAST_TRADE events are processed. BBO and other tick types are ignored.
    Bar builders attached in Plan 02 via state.bar_builders list.
    """
    async def on_tick(tick) -> None:
        # D-17: no processing during FROZEN state (disconnect/reconnect in progress)
        if hasattr(state, "freeze_guard") and state.freeze_guard.is_frozen:
            return

        if not hasattr(tick, "data_type"):
            return

        if tick.data_type != DataType.LAST_TRADE:
            return

        lt = getattr(tick, "last_trade", None)
        if lt is None:
            return

        price     = getattr(lt, "price",     None)
        size      = getattr(lt, "size",      None)
        aggressor = getattr(lt, "aggressor", 0)

        if price is None or size is None:
            return

        # Record sample for aggressor gate evaluation (D-03)
        record_aggressor_sample(aggressor)

        # Only accumulate to footprint once gate is verified AND aggressor is known (D-03)
        gate_passed = await aggressor_verification_gate(state.config)
        if not gate_passed:
            return

        if aggressor == 0:  # TRANSACTIONTYPE_UNSPECIFIED — skip even after gate passes
            return

        # Forward to bar builders — assembled in Plan 02
        bar_builders = getattr(state, "bar_builders", [])
        for builder in bar_builders:
            builder.on_trade(price, size, aggressor)

    return on_tick
