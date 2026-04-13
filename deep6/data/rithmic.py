"""Rithmic connection factory and aggressor verification gate.

Per D-02: async-rithmic 1.5.9 event callback pattern.
Per D-03: aggressor verification gate — CRITICAL. No footprint accumulation until verified.
Per D-17: on_disconnected activates FROZEN state immediately.
Per D-18: Issue #49 workaround — 500ms asyncio.sleep after connect() before subscribing.
Per D-19: all disconnect/reconnect events logged with timestamps.
Per T-01-01: rithmic_password NEVER appears in log output.
Per T-01-02: _aggressor_verified module-level state; single event loop, no concurrent mutation.
"""
import asyncio
import time

import structlog
from async_rithmic import RithmicClient, ReconnectionSettings

from deep6.config import Config

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Aggressor gate state — module-level (single event loop; no thread mutation)
# Per T-01-02: gate cannot be bypassed without explicitly setting _aggressor_verified=True
# ---------------------------------------------------------------------------
_aggressor_sample_count: int = 0
_aggressor_unknown_count: int = 0
_aggressor_verified: bool = False


def reset_aggressor_gate() -> None:
    """Reset gate state — used after reconnection to re-verify."""
    global _aggressor_sample_count, _aggressor_unknown_count, _aggressor_verified
    _aggressor_sample_count = 0
    _aggressor_unknown_count = 0
    _aggressor_verified = False
    log.info("aggressor.gate_reset")


def record_aggressor_sample(aggressor: int) -> None:
    """Called from tick_feed for each LAST_TRADE tick during gate sampling.

    aggressor: 0=TRANSACTIONTYPE_UNSPECIFIED, 1=BUY, 2=SELL
    """
    global _aggressor_sample_count, _aggressor_unknown_count
    _aggressor_sample_count += 1
    if aggressor == 0:  # TRANSACTIONTYPE_UNSPECIFIED
        _aggressor_unknown_count += 1


async def aggressor_verification_gate(config: Config) -> bool:
    """Sample N ticks and confirm TransactionType.BUY/SELL is present.

    Returns True when gate passes (sufficient non-UNSPECIFIED aggressors observed).
    Returns False while still sampling (fewer than aggressor_sample_size ticks seen).
    Returns False and logs ESCALATE error if >aggressor_max_unknown_pct are UNSPECIFIED.

    CRITICAL per D-03: No FootprintBar accumulator code runs until this gate passes.

    TransactionType enum values (from async_rithmic protocol_buffers/last_trade_pb2.py):
        TRANSACTIONTYPE_UNSPECIFIED = 0
        BUY = 1   (ask-side aggressor)
        SELL = 2  (bid-side aggressor)
    """
    global _aggressor_verified

    if _aggressor_verified:
        return True

    if _aggressor_sample_count < config.aggressor_sample_size:
        return False  # still sampling; gate not yet evaluated

    unknown_pct = _aggressor_unknown_count / _aggressor_sample_count
    if unknown_pct > config.aggressor_max_unknown_pct:
        log.error(
            "aggressor.verification_failed",
            sample_count=_aggressor_sample_count,
            unknown_count=_aggressor_unknown_count,
            unknown_pct=f"{unknown_pct:.1%}",
            action=(
                "ESCALATE — footprint accumulation disabled. "
                "Check Rithmic CME aggressor feed. "
                "TransactionType.BUY/SELL is not being reported. "
                "Contact broker to confirm LAST_TRADE aggressor field is enabled."
            ),
        )
        return False

    _aggressor_verified = True
    log.info(
        "aggressor.verified",
        sample_count=_aggressor_sample_count,
        unknown_count=_aggressor_unknown_count,
        unknown_pct=f"{unknown_pct:.1%}",
        message="Aggressor gate PASSED — footprint accumulation enabled.",
    )
    return True


async def connect_rithmic(config: Config) -> RithmicClient:
    """Connect to Rithmic with Issue #49 workaround (sequential plant delay).

    Per D-18: 500ms asyncio.sleep after connect() before any subscriptions —
    prevents ForcedLogout reconnection loop (async-rithmic issue #49).
    Per D-19: connection event logged with timestamp.
    Per T-01-01: password excluded from log output.
    """
    client = RithmicClient(
        user=config.rithmic_user,
        password=config.rithmic_password,
        system_name=config.rithmic_system_name,
        app_name="DEEP6",
        app_version="2.0.0",
        uri=config.rithmic_uri,
        reconnection_settings=ReconnectionSettings(
            max_retries=10,
            base_delay=1.0,
            max_delay=60.0,
            backoff_factor=2.0,
            jitter=True,
        ),
    )

    log.info("rithmic.connecting", **config.safe_log_fields())
    await client.connect()

    # Issue #49 workaround: 500ms delay after connect before subscribing
    # Prevents ForcedLogout reconnection loop bug in async-rithmic
    await asyncio.sleep(0.5)

    log.info(
        "rithmic.connected",
        uri=config.rithmic_uri,
        system=config.rithmic_system_name,
        ts=time.time(),
    )
    return client


def register_callbacks(client: RithmicClient, state: "SharedState") -> None:
    """Attach all event callbacks to the connected client.

    Callbacks are closures bound to shared state — no global state in callbacks.
    Per D-17, D-19: disconnect handler activates FROZEN state and logs timestamp.
    """
    from deep6.data.dom_feed import make_dom_callback
    from deep6.data.tick_feed import make_tick_callback

    client.on_order_book += make_dom_callback(state)
    client.on_tick += make_tick_callback(state)
    client.on_connected += lambda: _on_connected()
    client.on_disconnected += lambda: _on_disconnected(state)

    log.info("rithmic.callbacks_registered")


def _on_connected() -> None:
    """Log reconnection event (D-19)."""
    log.info("rithmic.on_connected", ts=time.time())


def _on_disconnected(state: "SharedState") -> None:
    """Activate FROZEN state immediately on disconnect (D-17, D-19).

    No new bar processing occurs until reconnection + position reconciliation.
    """
    ts = time.time()
    log.warning("rithmic.disconnected", ts=ts)
    if hasattr(state, "freeze_guard"):
        state.freeze_guard.on_disconnect(ts)
