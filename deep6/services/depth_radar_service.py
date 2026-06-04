"""Depth Radar ML Classification Service.

Async TCP client that connects to NT8's DepthRadarBridge on port 9201,
receives wall snapshots via NDJSON, runs LightGBM inference through
WallFeatureExtractor + WallClassifier, and sends classifications back.

Exposes a FastAPI health endpoint on port 9202.

When the model file is missing or fails to load, the service runs in
passthrough mode -- returning UNKNOWN with confidence 0.0 for all walls.

Usage:
    python -m deep6.services.depth_radar_service --model path/to/model.joblib
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import time
from typing import Any

import uvicorn
from fastapi import FastAPI

from deep6.ml.depth_radar.classifier import WallClassifier
from deep6.ml.depth_radar.wall_features import WallFeatureExtractor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reconnection constants (matches bridge_client.py pattern)
# ---------------------------------------------------------------------------
_BACKOFF_BASE = 1.0
_BACKOFF_MAX = 30.0
_BACKOFF_FACTOR = 2.0
_JITTER = 0.3


def _backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: 1s -> 2s -> 4s -> ... -> 30s max."""
    delay = min(_BACKOFF_BASE * (_BACKOFF_FACTOR ** attempt), _BACKOFF_MAX)
    jitter = delay * _JITTER * (2.0 * random.random() - 1.0)
    return max(0.1, delay + jitter)


# ---------------------------------------------------------------------------
# DepthRadarService
# ---------------------------------------------------------------------------
class DepthRadarService:
    """Async service: TCP client for wall classification + FastAPI health.

    Parameters
    ----------
    model_path:
        Path to the joblib-serialized WallClassifier model.
    bridge_port:
        TCP port of the NT8 DepthRadarBridge (default 9201).
    health_port:
        HTTP port for the FastAPI health/metrics endpoints (default 9202).
    bridge_host:
        Hostname for the NT8 bridge connection (default localhost).
    """

    def __init__(
        self,
        model_path: str,
        bridge_port: int = 9201,
        health_port: int = 9202,
        bridge_host: str = "127.0.0.1",
    ) -> None:
        self._model_path = model_path
        self._bridge_host = bridge_host
        self._bridge_port = bridge_port
        self._health_port = health_port

        # ML components
        self._classifier: WallClassifier | None = None
        self._extractor = WallFeatureExtractor(normalize=True)
        self._model_loaded = False

        # Connection state
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._stop = False

        # Metrics
        self._walls_classified = 0
        self._last_classification_ms = 0.0
        self._classification_distribution: dict[str, int] = {}
        self._inference_times: list[float] = []
        self._start_time = 0.0

        # FastAPI app
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Attempt to load the classifier model. Enter passthrough on failure."""
        try:
            self._classifier = WallClassifier(model_path=self._model_path)
            self._model_loaded = True
            logger.info(
                "depth_radar.model_loaded path=%s mode=%s classes=%s",
                self._model_path,
                self._classifier.mode,
                ",".join(self._classifier.class_names),
            )
        except FileNotFoundError:
            self._classifier = None
            self._model_loaded = False
            logger.warning(
                "depth_radar.model_not_found path=%s mode=passthrough",
                self._model_path,
            )
        except Exception as exc:
            self._classifier = None
            self._model_loaded = False
            logger.error(
                "depth_radar.model_load_failed path=%s error=%s mode=passthrough",
                self._model_path, exc,
            )

    # ------------------------------------------------------------------
    # FastAPI health/metrics
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        """Construct the FastAPI app with /health and /metrics endpoints."""
        app = FastAPI(title="Depth Radar Service", docs_url=None, redoc_url=None)

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "model_loaded": self._model_loaded,
                "last_classification_ms": round(self._last_classification_ms, 2),
                "walls_classified": self._walls_classified,
                "connected": self._connected,
            }

        @app.get("/metrics")
        async def metrics() -> dict[str, Any]:
            avg_ms = 0.0
            if self._inference_times:
                avg_ms = sum(self._inference_times) / len(self._inference_times)
            uptime = time.monotonic() - self._start_time if self._start_time else 0.0
            return {
                "classification_distribution": dict(self._classification_distribution),
                "avg_inference_ms": round(avg_ms, 2),
                "uptime_sec": round(uptime, 1),
            }

        return app

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the TCP client and health server concurrently."""
        self._start_time = time.monotonic()
        self._stop = False
        self._load_model()

        logger.info(
            "depth_radar.starting bridge=%s:%d health_port=%d model_loaded=%s",
            self._bridge_host, self._bridge_port, self._health_port,
            self._model_loaded,
        )

        tcp_task = asyncio.create_task(
            self._tcp_connection_loop(), name="depth_radar_tcp",
        )
        health_task = asyncio.create_task(
            self._run_health_server(), name="depth_radar_health",
        )

        try:
            await asyncio.gather(tcp_task, health_task)
        except asyncio.CancelledError:
            pass
        finally:
            self._stop = True
            for task in (tcp_task, health_task):
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            await self._close_tcp()
            logger.info("depth_radar.stopped")

    async def _run_health_server(self) -> None:
        """Run uvicorn inside the existing event loop."""
        config = uvicorn.Config(
            app=self._app,
            host="0.0.0.0",
            port=self._health_port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        await server.serve()

    # ------------------------------------------------------------------
    # TCP connection loop (DepthRadarBridge NDJSON on port 9201)
    # ------------------------------------------------------------------

    async def _tcp_connection_loop(self) -> None:
        """Outer loop: connect -> read -> reconnect on failure."""
        attempt = 0
        while not self._stop:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self._bridge_host, self._bridge_port,
                    ),
                    timeout=5.0,
                )
                self._connected = True
                attempt = 0
                logger.info(
                    "depth_radar.tcp_connected host=%s port=%d",
                    self._bridge_host, self._bridge_port,
                )
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except (ConnectionRefusedError, asyncio.TimeoutError, OSError) as exc:
                logger.debug(
                    "depth_radar.tcp_unavailable attempt=%d error=%s",
                    attempt, exc,
                )
            except Exception as exc:
                logger.warning(
                    "depth_radar.tcp_error attempt=%d error=%s",
                    attempt, exc,
                )
            finally:
                self._connected = False
                await self._close_tcp()

            if not self._stop:
                delay = _backoff_delay(attempt)
                attempt = min(attempt + 1, 10)
                logger.debug("depth_radar.tcp_reconnect_in %.1fs", delay)
                await asyncio.sleep(delay)

    async def _read_loop(self) -> None:
        """Read NDJSON lines from the bridge until EOF or error."""
        assert self._reader is not None
        while not self._stop:
            line = await self._reader.readline()
            if not line:
                logger.info("depth_radar.tcp_eof")
                return
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            await self._dispatch(data)

    async def _dispatch(self, data: dict[str, Any]) -> None:
        """Route an NDJSON message by its 'type' field."""
        msg_type = data.get("type", "")

        if msg_type == "wall_snapshot":
            await self._handle_wall_snapshot(data)
        elif msg_type == "heartbeat":
            await self._handle_heartbeat(data)
        else:
            logger.debug("depth_radar.unknown_message type=%s", msg_type)

    # ------------------------------------------------------------------
    # Wall snapshot processing
    # ------------------------------------------------------------------

    async def _handle_wall_snapshot(self, data: dict[str, Any]) -> None:
        """Extract features, classify, and send result back to NT8."""
        price = float(data.get("price", 0.0))
        side = str(data.get("side", "bid"))
        best_bid = float(data.get("best_bid", price))
        best_ask = float(data.get("best_ask", price))

        wall_data = {
            "time_in_book": float(data.get("time_in_book", 0.0)),
            "modification_count": float(data.get("modification_count", 0)),
            "cancellation_count": float(data.get("cancellation_count", 0)),
            "original_size": float(data.get("original_size", 0)),
            "max_size": float(data.get("max_size", 0)),
            "current_size": float(data.get("current_size", 0)),
            "refill_count": float(data.get("refill_count", 0)),
            "price_crossed": bool(data.get("price_crossed", False)),
            "side": 1 if side.lower() == "ask" else 0,
            "wall_price": price,
        }

        mid_price = (best_bid + best_ask) / 2.0
        avg_wall_size = float(data.get("max_size", 1.0))
        avg_wall_size = max(1.0, avg_wall_size)

        market_context = {
            "mid_price": mid_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": best_ask - best_bid,
            "avg_wall_size": avg_wall_size,
            "bid_volumes": [],
            "ask_volumes": [],
        }

        if not self._model_loaded or self._classifier is None:
            # Passthrough mode
            await self._send_classification(price, side, "UNKNOWN", 0.0)
            self._walls_classified += 1
            self._classification_distribution["UNKNOWN"] = (
                self._classification_distribution.get("UNKNOWN", 0) + 1
            )
            return

        try:
            features = self._extractor.extract(wall_data, market_context)

            loop = asyncio.get_event_loop()
            t0 = time.monotonic()
            label, confidence = await loop.run_in_executor(
                None, self._classifier.classify, features,
            )
            label = self._normalize_label_for_service(label)
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            self._walls_classified += 1
            self._last_classification_ms = elapsed_ms
            self._inference_times.append(elapsed_ms)
            # Keep last 1000 inference times for avg calculation
            if len(self._inference_times) > 1000:
                self._inference_times = self._inference_times[-1000:]

            self._classification_distribution[label] = (
                self._classification_distribution.get(label, 0) + 1
            )

            await self._send_classification(price, side, label, confidence)

            logger.debug(
                "depth_radar.classified price=%.2f side=%s label=%s conf=%.3f ms=%.1f",
                price, side, label, confidence, elapsed_ms,
            )
        except Exception as exc:
            logger.error(
                "depth_radar.classification_error price=%.2f error=%s",
                price, exc,
            )
            await self._send_classification(price, side, "UNKNOWN", 0.0)

    def _normalize_label_for_service(self, label: str) -> str:
        """Map classifier output to NT8-facing lifecycle labels."""
        classifier = self._classifier
        if classifier is None:
            return label
        if classifier.mode == "multiclass":
            return label
        if label == "NOT_SPOOF":
            return "GENUINE"
        return label

    async def _send_classification(
        self, price: float, side: str, label: str, confidence: float,
    ) -> None:
        """Send a classification result back to NT8 as NDJSON."""
        if self._writer is None:
            return
        msg = {
            "type": "wall_classification",
            "price": price,
            "side": side,
            "classification": label,
            "confidence": round(confidence, 4),
        }
        try:
            line = json.dumps(msg) + "\n"
            self._writer.write(line.encode("utf-8"))
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("depth_radar.send_failed error=%s", exc)

    # ------------------------------------------------------------------
    # Heartbeat handling
    # ------------------------------------------------------------------

    async def _handle_heartbeat(self, data: dict[str, Any]) -> None:
        """Echo heartbeat back as heartbeat_ack."""
        if self._writer is None:
            return
        ack = {
            "type": "heartbeat_ack",
            "timestamp": data.get("timestamp", 0),
        }
        try:
            line = json.dumps(ack) + "\n"
            self._writer.write(line.encode("utf-8"))
            await self._writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            logger.warning("depth_radar.heartbeat_ack_failed error=%s", exc)

    # ------------------------------------------------------------------
    # Connection cleanup
    # ------------------------------------------------------------------

    async def _close_tcp(self) -> None:
        """Close the TCP connection if open."""
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main(model_path: str, bridge_port: int, health_port: int) -> None:
    """Create and start the DepthRadarService."""
    service = DepthRadarService(model_path, bridge_port, health_port)
    await service.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Depth Radar ML Classification Service",
    )
    parser.add_argument(
        "--model",
        default="deep6/models/depth_radar_classifier.joblib",
        help="Model path",
    )
    parser.add_argument(
        "--port", type=int, default=9201, help="NT8 bridge port",
    )
    parser.add_argument(
        "--health-port", type=int, default=9202, help="Health endpoint port",
    )
    args = parser.parse_args()
    asyncio.run(main(args.model, args.port, args.health_port))
