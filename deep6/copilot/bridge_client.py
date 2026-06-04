"""CopilotBridgeClient — read-only consumer of DEEP6 live infrastructure.

Connects to two data sources:
  1. DataBridge TCP (127.0.0.1:9200) — NDJSON stream of trade/depth/bar/internals
  2. FastAPI WebSocket (ws://127.0.0.1:8765/ws/live) — signal/score/status/bias

All data is consumed passively.  When a source is unavailable, getters return
None gracefully.  Both connections auto-reconnect with exponential backoff
(1 s -> 60 s, jittered).

Usage:
    client = CopilotBridgeClient(config)
    await client.connect()
    score = client.get_latest_score()
    await client.disconnect()
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Callable

try:
    import websockets  # type: ignore[import-untyped]
except ImportError:
    websockets = None  # type: ignore[assignment]

from deep6.copilot.config import CopilotConfig
from deep6.copilot.types import GEXSummary, KronosBias, SignalSummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reconnection constants
# ---------------------------------------------------------------------------
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 60.0
_BACKOFF_FACTOR = 2.0
_JITTER = 0.3  # +/-30% of computed delay
_MAX_SIGNAL_HISTORY = 50


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 1 s -> 60 s."""
    delay = min(_BACKOFF_BASE * (_BACKOFF_FACTOR ** attempt), _BACKOFF_MAX)
    jitter = delay * _JITTER * (2.0 * random.random() - 1.0)
    return max(0.1, delay + jitter)


# ---------------------------------------------------------------------------
# Lightweight score snapshot (avoids importing scorer engine internals)
# ---------------------------------------------------------------------------

class ScoreSnapshot:
    """Read-only mirror of LiveScoreMessage fields."""

    __slots__ = (
        "total_score", "tier", "direction", "categories_firing",
        "category_scores", "kronos_bias", "kronos_direction", "gex_regime",
    )

    def __init__(self, data: dict[str, Any]) -> None:
        self.total_score: float = float(data.get("total_score", 0.0))
        self.tier: str = str(data.get("tier", "QUIET"))
        self.direction: int = int(data.get("direction", 0))
        self.categories_firing: list[str] = list(data.get("categories_firing", []))
        self.category_scores: dict[str, float] = dict(data.get("category_scores", {}))
        self.kronos_bias: float = float(data.get("kronos_bias", 0.0))
        self.kronos_direction: str = str(data.get("kronos_direction", "NEUTRAL"))
        self.gex_regime: str = str(data.get("gex_regime", "NEUTRAL"))

    def __repr__(self) -> str:
        return (
            f"ScoreSnapshot(score={self.total_score:.1f}, tier={self.tier}, "
            f"dir={self.direction})"
        )


# ---------------------------------------------------------------------------
# CopilotBridgeClient
# ---------------------------------------------------------------------------

class CopilotBridgeClient:
    """Async read-only client for DEEP6 DataBridge TCP and FastAPI WebSocket.

    Parameters
    ----------
    config:
        CopilotConfig with ``data_bridge_host/port`` and ``api_host/port``.
    """

    def __init__(self, config: CopilotConfig) -> None:
        self._config = config

        # Connection state
        self._tcp_reader: asyncio.StreamReader | None = None
        self._tcp_writer: asyncio.StreamWriter | None = None
        self._tcp_connected = False
        self._ws_connected = False

        # Latest data snapshots (single-threaded asyncio — no lock needed)
        self._latest_score: ScoreSnapshot | None = None
        self._latest_signals: list[dict[str, Any]] = []
        self._latest_gex: dict[str, Any] | None = None
        self._latest_kronos: dict[str, Any] | None = None
        self._latest_bar: dict[str, Any] | None = None
        self._latest_status: dict[str, Any] | None = None

        # Callbacks
        self._signal_callbacks: list[Callable] = []
        self._score_callbacks: list[Callable] = []
        self._bar_callbacks: list[Callable] = []

        # Background tasks
        self._tcp_task: asyncio.Task | None = None
        self._ws_task: asyncio.Task | None = None
        self._stop = False

        # Stats
        self.tcp_messages_received: int = 0
        self.ws_messages_received: int = 0

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start background reader loops for both TCP and WebSocket."""
        self._stop = False
        self._tcp_task = asyncio.create_task(
            self._tcp_connection_loop(), name="bridge_tcp",
        )
        self._ws_task = asyncio.create_task(
            self._ws_connection_loop(), name="bridge_ws",
        )
        logger.info(
            "bridge.started tcp=%s:%d ws=%s:%d",
            self._config.data_bridge_host, self._config.data_bridge_port,
            self._config.api_host, self._config.api_port,
        )

    async def disconnect(self) -> None:
        """Cleanly shut down both connections."""
        self._stop = True
        for task in (self._tcp_task, self._ws_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        await self._close_tcp()
        self._ws_connected = False
        logger.info("bridge.stopped")

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_signal(self, callback: Callable) -> None:
        """Register a callback for signal events."""
        self._signal_callbacks.append(callback)

    def on_score(self, callback: Callable) -> None:
        """Register a callback for confluence score updates."""
        self._score_callbacks.append(callback)

    def on_bar(self, callback: Callable) -> None:
        """Register a callback for bar close events."""
        self._bar_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Public getters (return None when data not yet received)
    # ------------------------------------------------------------------

    def get_latest_score(self) -> ScoreSnapshot | None:
        """Last known confluence score, or None."""
        return self._latest_score

    def get_latest_signals(self) -> list[SignalSummary]:
        """Active signals mapped to SignalSummary."""
        out: list[SignalSummary] = []
        for s in self._latest_signals:
            raw_dir = s.get("direction", 0)
            if isinstance(raw_dir, (int, float)):
                direction = "bullish" if raw_dir > 0 else (
                    "bearish" if raw_dir < 0 else "neutral"
                )
            else:
                direction = str(raw_dir)
            out.append(SignalSummary(
                name=str(s.get("tier", s.get("name", ""))),
                direction=direction,
                strength=float(s.get("total_score", s.get("strength", 0))),
                category=", ".join(s.get("categories_firing", [])),
                timestamp=float(s.get("ts", 0.0)),
            ))
        return out

    def get_latest_gex(self) -> GEXSummary | None:
        """Last known GEX regime summary, or None."""
        g = self._latest_gex
        if g is None:
            return None
        return GEXSummary(
            call_wall=float(g.get("call_wall", 0)),
            put_wall=float(g.get("put_wall", 0)),
            gamma_flip=float(g.get("gamma_flip", 0)),
            hvl=float(g.get("hvl", 0)),
            regime=str(g.get("regime", "unknown")),
        )

    def get_latest_kronos(self) -> KronosBias | None:
        """Last known Kronos E10 bias, or None."""
        k = self._latest_kronos
        if k is None:
            return None
        raw = k.get("kronos_direction", "NEUTRAL")
        direction = (
            "bullish" if raw == "LONG"
            else "bearish" if raw == "SHORT"
            else "neutral"
        )
        return KronosBias(
            direction=direction,
            confidence=float(k.get("kronos_bias", 0)) / 100.0,
        )

    def get_latest_bar(self) -> dict[str, Any] | None:
        """Last received bar data, or None."""
        return self._latest_bar

    def get_latest_status(self) -> dict[str, Any] | None:
        """Last received status message, or None."""
        return self._latest_status

    @property
    def is_tcp_connected(self) -> bool:
        return self._tcp_connected

    @property
    def is_ws_connected(self) -> bool:
        return self._ws_connected

    # ------------------------------------------------------------------
    # TCP connection loop (DataBridge NDJSON on port 9200)
    # ------------------------------------------------------------------

    async def _tcp_connection_loop(self) -> None:
        """Outer loop: connect -> read -> reconnect on failure."""
        attempt = 0
        while not self._stop:
            try:
                self._tcp_reader, self._tcp_writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self._config.data_bridge_host,
                        self._config.data_bridge_port,
                    ),
                    timeout=5.0,
                )
                self._tcp_connected = True
                attempt = 0
                logger.info(
                    "bridge.tcp_connected host=%s port=%d",
                    self._config.data_bridge_host,
                    self._config.data_bridge_port,
                )
                await self._read_tcp_loop()
            except asyncio.CancelledError:
                raise
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as exc:
                logger.debug("bridge.tcp_unavailable attempt=%d error=%s", attempt, exc)
            except Exception as exc:
                logger.warning("bridge.tcp_error attempt=%d error=%s", attempt, exc)
            finally:
                self._tcp_connected = False
                await self._close_tcp()

            if not self._stop:
                delay = _backoff_delay(attempt)
                attempt = min(attempt + 1, 10)
                logger.debug("bridge.tcp_reconnect_in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _read_tcp_loop(self) -> None:
        """Read NDJSON lines from DataBridge TCP stream until EOF or error."""
        assert self._tcp_reader is not None
        while not self._stop:
            line = await self._tcp_reader.readline()
            if not line:
                logger.info("bridge.tcp_eof")
                return
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self.tcp_messages_received += 1
            await self._dispatch_tcp(data)

    async def _dispatch_tcp(self, data: dict[str, Any]) -> None:
        """Route an NDJSON message by its 'type' field."""
        msg_type = data.get("type", "")

        if msg_type == "bar":
            self._latest_bar = data
            await self._fire_callbacks(self._bar_callbacks, data)

        elif msg_type == "trade":
            # Store latest tape print for context
            self._latest_bar_trade = data

        elif msg_type == "depth":
            # DOM depth snapshot — not stored long-term
            pass

        elif msg_type == "internals":
            # Market internals (TICK, ADD, VOLD)
            self._latest_status = self._latest_status or {}
            self._latest_status["internals"] = data

    async def _close_tcp(self) -> None:
        """Close the TCP connection if open."""
        writer = self._tcp_writer
        self._tcp_writer = None
        self._tcp_reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _reconnect_tcp(self, max_attempts: int = 10) -> None:
        """Exponential backoff reconnect for TCP (called by connection loop)."""
        for attempt in range(max_attempts):
            if self._stop:
                return
            delay = _backoff_delay(attempt)
            logger.debug("bridge.tcp_reconnect attempt=%d delay=%.1fs", attempt, delay)
            await asyncio.sleep(delay)
            try:
                self._tcp_reader, self._tcp_writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self._config.data_bridge_host,
                        self._config.data_bridge_port,
                    ),
                    timeout=5.0,
                )
                self._tcp_connected = True
                logger.info("bridge.tcp_reconnected attempt=%d", attempt)
                return
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                continue
        logger.warning("bridge.tcp_reconnect_exhausted max_attempts=%d", max_attempts)

    # ------------------------------------------------------------------
    # WebSocket connection loop (FastAPI ws://host:port/ws/live)
    # ------------------------------------------------------------------

    async def _ws_connection_loop(self) -> None:
        """Outer loop: connect -> read -> reconnect on failure."""
        if websockets is None:
            logger.warning("bridge.ws_unavailable reason=websockets_not_installed")
            return

        ws_url = f"ws://{self._config.api_host}:{self._config.api_port}/ws/live"
        attempt = 0
        while not self._stop:
            try:
                async with websockets.connect(
                    ws_url, ping_interval=20, ping_timeout=10,
                ) as ws:
                    self._ws_connected = True
                    attempt = 0
                    logger.info("bridge.ws_connected url=%s", ws_url)
                    await self._read_ws_loop(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("bridge.ws_unavailable attempt=%d error=%s", attempt, exc)
            finally:
                self._ws_connected = False

            if not self._stop:
                delay = _backoff_delay(attempt)
                attempt = min(attempt + 1, 10)
                logger.debug("bridge.ws_reconnect_in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _read_ws_loop(self, ws: Any) -> None:
        """Receive JSON messages from the WebSocket and dispatch."""
        async for raw_msg in ws:
            if self._stop:
                break
            try:
                data = json.loads(raw_msg)
            except (json.JSONDecodeError, TypeError):
                continue
            self.ws_messages_received += 1
            await self._dispatch_ws(data)

    async def _dispatch_ws(self, data: dict[str, Any]) -> None:
        """Route a WebSocket message by its 'type' field."""
        msg_type = data.get("type", "")

        if msg_type == "score":
            snapshot = ScoreSnapshot(data)
            self._latest_score = snapshot
            # Extract GEX regime from score messages
            if snapshot.gex_regime and snapshot.gex_regime != "NEUTRAL":
                if self._latest_gex is None:
                    self._latest_gex = {}
                self._latest_gex["regime"] = snapshot.gex_regime
            # Extract Kronos from score messages
            if snapshot.kronos_direction != "NEUTRAL" or snapshot.kronos_bias != 0.0:
                self._latest_kronos = {
                    "kronos_bias": snapshot.kronos_bias,
                    "kronos_direction": snapshot.kronos_direction,
                }
            await self._fire_callbacks(self._score_callbacks, snapshot)

        elif msg_type == "signal":
            event = data.get("event", {})
            self._latest_signals.append(event)
            if len(self._latest_signals) > _MAX_SIGNAL_HISTORY:
                self._latest_signals = self._latest_signals[-_MAX_SIGNAL_HISTORY:]
            # Extract GEX/Kronos from signal events
            gex_regime = event.get("gex_regime")
            if gex_regime and gex_regime != "NEUTRAL":
                if self._latest_gex is None:
                    self._latest_gex = {}
                self._latest_gex["regime"] = gex_regime
            kronos_bias = event.get("kronos_bias")
            if kronos_bias is not None and kronos_bias != 0:
                self._latest_kronos = {
                    "kronos_bias": kronos_bias,
                    "kronos_direction": event.get("kronos_direction", "NEUTRAL"),
                }
            await self._fire_callbacks(self._signal_callbacks, data)

        elif msg_type == "bar":
            self._latest_bar = data
            await self._fire_callbacks(self._bar_callbacks, data)

        elif msg_type == "status":
            self._latest_status = data

        elif msg_type == "tape":
            # Store latest tape print
            pass

        elif msg_type == "bias":
            # Update Kronos from bias messages
            direction = data.get("direction", "NEUTRAL")
            confidence = data.get("confidence", 0.0)
            if direction and direction != "NEUTRAL":
                self._latest_kronos = {
                    "kronos_bias": confidence * 100.0,
                    "kronos_direction": (
                        "LONG" if direction == "BULLISH"
                        else "SHORT" if direction == "BEARISH"
                        else "NEUTRAL"
                    ),
                }

    async def _reconnect_ws(self, max_attempts: int = 10) -> None:
        """Exponential backoff reconnect for WebSocket (called by connection loop)."""
        for attempt in range(max_attempts):
            if self._stop:
                return
            delay = _backoff_delay(attempt)
            logger.debug("bridge.ws_reconnect attempt=%d delay=%.1fs", attempt, delay)
            await asyncio.sleep(delay)
            try:
                ws_url = f"ws://{self._config.api_host}:{self._config.api_port}/ws/live"
                ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=10)
                self._ws_connected = True
                logger.info("bridge.ws_reconnected attempt=%d", attempt)
                await self._read_ws_loop(ws)
                return
            except Exception:
                continue
        logger.warning("bridge.ws_reconnect_exhausted max_attempts=%d", max_attempts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fire_callbacks(self, cbs: list[Callable], data: Any) -> None:
        """Fire all registered callbacks, tolerating both sync and async."""
        for cb in cbs:
            try:
                result = cb(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("bridge.callback_error error=%s", exc)
