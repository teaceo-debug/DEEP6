"""Market Internals adapter — receives ^TICK, ^ADD, ^VOLD from DataBridge.

Connects to the DEEP6 DataBridge TCP server (default 127.0.0.1:9200) and
parses NDJSON lines with type=="internals". Provides real-time MarketInternals
snapshots with auto-reconnect and interpretation helpers.

Usage::

    adapter = MarketInternalsAdapter()
    await adapter.connect("127.0.0.1", 9200)

    # Poll latest snapshot
    snapshot = adapter.get_current()

    # Or register a callback
    adapter.on_update(lambda mi: print(mi.advance_decline))

    # Interpretation
    bias = interpret_tick(snapshot.upticks - snapshot.downticks)

    await adapter.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from deep6.copilot.types import MarketInternals

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interpretation thresholds
# ---------------------------------------------------------------------------
TICK_BULLISH: int = 500
TICK_BEARISH: int = -500
TICK_EXTREME_BULLISH: int = 800
TICK_EXTREME_BEARISH: int = -800
ADD_BULLISH: float = 1000.0
ADD_BEARISH: float = -1000.0

_BACKOFF_INITIAL: float = 1.0
_BACKOFF_MAX: float = 30.0
_BACKOFF_FACTOR: float = 2.0


def interpret_tick(tick: float) -> str:
    """Classify NYSE TICK reading into a bias label.

    Returns one of: extreme_bullish, bullish, neutral, bearish, extreme_bearish.
    Thresholds: +/-500 = directional, +/-800 = extreme.
    """
    if tick >= TICK_EXTREME_BULLISH:
        return "extreme_bullish"
    if tick >= TICK_BULLISH:
        return "bullish"
    if tick <= TICK_EXTREME_BEARISH:
        return "extreme_bearish"
    if tick <= TICK_BEARISH:
        return "bearish"
    return "neutral"


def interpret_add(add: float) -> str:
    """Classify NYSE Advance/Decline reading."""
    if add >= ADD_BULLISH:
        return "bullish"
    if add <= ADD_BEARISH:
        return "bearish"
    return "neutral"


def interpret_vold(vold: float) -> str:
    """Classify NYSE Up/Down Volume ratio.

    vold > 2.0 = strong bullish volume, vold < 0.5 = strong bearish volume.
    """
    if vold >= 2.0:
        return "strong_bullish"
    if vold >= 1.2:
        return "bullish"
    if vold <= 0.5:
        return "strong_bearish"
    if vold <= 0.8:
        return "bearish"
    return "neutral"


class MarketInternalsAdapter:
    """Async TCP client for DataBridge market internals stream.

    Connects to the DEEP6 DataBridge and filters for ``type=="internals"``
    messages containing ^TICK, ^ADD, and ^VOLD data. Automatically reconnects
    with exponential backoff on disconnect.
    """

    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._current: MarketInternals | None = None
        self._raw: dict[str, float] = {"tick": 0.0, "add": 0.0, "vold": 0.0}
        self._callbacks: list[Callable[[MarketInternals], Any]] = []
        self._connected: bool = False
        self._task: asyncio.Task[None] | None = None
        self._stop: bool = False
        self._host: str = "127.0.0.1"
        self._port: int = 9200

    # -- public properties --------------------------------------------------

    @property
    def connected(self) -> bool:
        """True when the TCP connection is active."""
        return self._connected

    @property
    def raw(self) -> dict[str, float]:
        """Raw tick/add/vold values from the last update."""
        return dict(self._raw)

    # -- lifecycle -----------------------------------------------------------

    async def connect(self, host: str = "127.0.0.1", port: int = 9200) -> None:
        """Connect to DataBridge and start reading internals messages.

        Launches a background task that auto-reconnects on disconnect.
        """
        self._host = host
        self._port = port
        self._stop = False
        self._task = asyncio.create_task(self._run_loop())

    async def disconnect(self) -> None:
        """Disconnect and stop the read loop."""
        self._stop = True
        self._close_writer()
        self._connected = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # -- data access ---------------------------------------------------------

    def get_current(self) -> MarketInternals | None:
        """Return the latest internals snapshot, or None if not connected."""
        return self._current

    def on_update(self, callback: Callable[[MarketInternals], Any]) -> None:
        """Register a callback invoked on every internals update.

        Callback receives a ``MarketInternals`` dataclass instance.
        """
        self._callbacks.append(callback)

    # -- internal ------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Main loop: connect, read, reconnect with exponential backoff."""
        backoff = _BACKOFF_INITIAL

        while not self._stop:
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self._host, self._port
                )
                self._connected = True
                backoff = _BACKOFF_INITIAL
                log.info(
                    "internals.connected host=%s port=%d",
                    self._host,
                    self._port,
                )

                await self._read_stream()

            except ConnectionRefusedError:
                log.debug(
                    "internals.connection_refused host=%s port=%d",
                    self._host,
                    self._port,
                )
            except OSError as exc:
                log.warning("internals.connection_error error=%s", exc)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("internals.unexpected_error error=%s", exc)
            finally:
                self._connected = False
                self._close_writer()

            if self._stop:
                break

            log.debug("internals.reconnecting backoff=%.1fs", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * _BACKOFF_FACTOR, _BACKOFF_MAX)

    async def _read_stream(self) -> None:
        """Read NDJSON lines and dispatch internals messages."""
        assert self._reader is not None
        while not self._stop:
            line = await self._reader.readline()
            if not line:
                break  # EOF — server disconnected

            try:
                msg = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            if msg.get("type") != "internals":
                continue

            ts_ms = msg.get("ts_ms", 0)
            tick_val = float(msg.get("tick", 0.0))
            add_val = float(msg.get("add", 0.0))
            vold_val = float(msg.get("vold", 0.0))

            self._raw["tick"] = tick_val
            self._raw["add"] = add_val
            self._raw["vold"] = vold_val

            snapshot = MarketInternals(
                tick_value=tick_val,
                tick_direction=interpret_tick(tick_val),
                add_value=add_val,
                add_direction=interpret_add(add_val),
                vold_value=vold_val,
                vold_ratio=vold_val,
                timestamp=ts_ms / 1000.0,
            )
            self._current = snapshot

            for cb in self._callbacks:
                try:
                    cb(snapshot)
                except Exception as exc:
                    log.warning("internals.callback_error error=%s", exc)

    def _close_writer(self) -> None:
        """Safely close the TCP writer."""
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass
        self._writer = None
        self._reader = None
