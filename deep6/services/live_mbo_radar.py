"""Live MBO radar service: source feed -> MBOWallEngine -> wall snapshots."""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import signal
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

try:
    import databento as db
except ImportError:  # pragma: no cover - runtime dependency guard
    db = None  # type: ignore[assignment]

from deep6.data.databento_live import (
    _ACTION_ADD,
    _ACTION_CANCEL,
    _ACTION_MODIFY,
    _SIDE_ASK,
    _SIDE_BID,
)
from deep6.ml.depth_radar.causal_classifier import (
    CausalClassifier,
    DEFAULT_INTENT_MODEL,
    DEFAULT_INTERACTION_MODEL,
)
from deep6.ml.depth_radar.mbo_wall_engine import MBOWallEngine


logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_PATH = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "depth_radar_walls.json"
DEFAULT_DATABENTO_DATASET = "GLBX.MDP3"
DEFAULT_DATABENTO_SCHEMA = "mbo"
DEFAULT_DATABENTO_SYMBOL = "NQ.c.0"
DEFAULT_RITHMIC_SYMBOL = "NQM6"
DEFAULT_RITHMIC_EXCHANGE = "CME"
DEFAULT_HEALTH_PORT = 9203
DEFAULT_SNAPSHOT_INTERVAL_SEC = 2.0
DEFAULT_MIN_WALL = 50
_QUEUE_MAXSIZE = 100_000

WallCallback = Callable[[list[dict[str, Any]]], Any]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(ts: datetime | pd.Timestamp) -> str:
    if isinstance(ts, pd.Timestamp):
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.tz_convert("UTC").isoformat().replace("+00:00", "Z")
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    try:
        tmp.replace(path)
    except PermissionError:
        # Windows: target file may be locked by NT8 reader — fall back to direct write
        path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _decode_char(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode("ascii", errors="replace")
    if isinstance(value, int):
        return chr(value)
    return str(value)


def _normalize_side(value: Any) -> str:
    s = str(value).strip().lower()
    if s in ("ask", "a", "1", "1.0"):
        return "ask"
    return "bid"


def _legacy_classification(intent: str) -> str:
    return {
        "PASSIVE_REAL": "GENUINE",
        "MIGRATORY": "GENUINE",
        "SPOOF_LIKE": "SPOOF",
        "RESERVE_REFRESH": "ICEBERG",
    }.get(intent, "GENUINE")


class LiveMBORadar:
    """Async service: MBO events -> MBOWallEngine -> classified walls."""

    def __init__(
        self,
        source: str = "databento",
        output_path: Path | None = None,
        health_port: int = DEFAULT_HEALTH_PORT,
        snapshot_interval_sec: float = DEFAULT_SNAPSHOT_INTERVAL_SEC,
        min_wall_size: int = DEFAULT_MIN_WALL,
        on_walls_updated: WallCallback | None = None,
        databento_api_key: str | None = None,
        databento_symbol: str = DEFAULT_DATABENTO_SYMBOL,
        rithmic_user: str | None = None,
        rithmic_password: str | None = None,
        rithmic_system_name: str | None = None,
        rithmic_url: str | None = None,
        rithmic_symbol: str = DEFAULT_RITHMIC_SYMBOL,
        rithmic_exchange: str = DEFAULT_RITHMIC_EXCHANGE,
        replay_file: str | None = None,
        intent_model_path: str | None = DEFAULT_INTENT_MODEL,
        interaction_model_path: str | None = DEFAULT_INTERACTION_MODEL,
        rth_only: bool = True,
    ) -> None:
        self.source = str(source).strip().lower()
        self.output_path = output_path or DEFAULT_OUTPUT_PATH
        self.health_port = int(health_port)
        self.snapshot_interval_sec = max(0.25, float(snapshot_interval_sec))
        self.min_wall_size = int(min_wall_size)
        self.on_walls_updated = on_walls_updated

        self.databento_api_key = (databento_api_key or "").strip() or None
        self.databento_symbol = databento_symbol
        self.rithmic_user = (rithmic_user or "").strip() or None
        self.rithmic_password = (rithmic_password or "").strip() or None
        self.rithmic_system_name = (rithmic_system_name or "").strip() or None
        self.rithmic_url = (rithmic_url or "").strip() or None
        self.rithmic_symbol = rithmic_symbol
        self.rithmic_exchange = rithmic_exchange
        self.replay_file = replay_file

        self.rth_only = bool(rth_only)
        self._engine = MBOWallEngine(
            min_wall_size=self.min_wall_size,
            snapshot_interval_sec=max(1, int(round(self.snapshot_interval_sec))),
            rth_only=self.rth_only,
        )
        self._classifier = CausalClassifier(
            intent_model_path=intent_model_path,
            interaction_model_path=interaction_model_path,
        )
        self._app = self._build_app()
        self._health_server: uvicorn.Server | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._stop_event = asyncio.Event()
        self._running = False
        self._connected = False
        self._finalized = False
        self._last_update_ts: pd.Timestamp | None = None
        self._completed_episode_count = 0
        self._latest_feature_walls: list[dict[str, Any]] = []
        self._latest_output_walls: list[dict[str, Any]] = []
        self._latest_payload: dict[str, Any] = {}
        self._last_mid_price = 0.0

        self._databento_client: Any = None
        self._databento_queue: asyncio.Queue[Any] | None = None
        self._databento_loop: asyncio.AbstractEventLoop | None = None

        self._rithmic_client: Any = None
        self._rithmic_levels: dict[str, dict[float, int]] = {"bid": {}, "ask": {}}

    async def start(self) -> None:
        """Start the radar (source + wall engine + output loop + health API)."""
        if self._running:
            return
        self._validate_source_config()
        self._running = True
        self._stop_event = asyncio.Event()
        self._finalized = False
        self._tasks = [
            asyncio.create_task(self._run_source(), name=f"live_mbo_radar_source_{self.source}"),
            asyncio.create_task(self._output_loop(), name="live_mbo_radar_output"),
            asyncio.create_task(self._run_health_server(), name="live_mbo_radar_health"),
        ]
        logger.info(
            "live_mbo_radar.starting source=%s health_port=%d output=%s",
            self.source,
            self.health_port,
            self.output_path,
        )
        first_error: BaseException | None = None
        try:
            done, _ = await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.cancelled():
                    continue
                exc = task.exception()
                if exc is not None:
                    first_error = exc
                    break
        finally:
            await self.stop()
        if first_error is not None:
            raise first_error

    async def stop(self) -> None:
        """Graceful shutdown."""
        if not self._running and self._stop_event.is_set():
            return
        self._stop_event.set()
        self._connected = False

        if not self._finalized and self._engine.last_timestamp is not None:
            flushed = self._engine.flush_all()
            self._completed_episode_count += len(flushed)
            if flushed:
                logger.info("live_mbo_radar.completed_episodes count=%d reason=shutdown", len(flushed))
            self._finalized = True

        await self._emit_snapshot(force=True)

        if self._health_server is not None:
            self._health_server.should_exit = True

        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is current or task.done():
                continue
            task.cancel()
        for task in list(self._tasks):
            if task is current:
                continue
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        self._running = False
        logger.info("live_mbo_radar.stopped source=%s", self.source)

    def _validate_source_config(self) -> None:
        if self.source not in {"databento", "rithmic", "replay"}:
            raise ValueError(f"Unsupported source: {self.source}")
        if self.source == "databento" and not self.databento_api_key:
            raise RuntimeError("DATABENTO_API_KEY is required for source=databento")
        if self.source == "replay" and not self.replay_file:
            raise RuntimeError("--replay-file is required for source=replay")
        if self.source == "rithmic":
            missing = [
                name
                for name, value in (
                    ("RITHMIC_USER", self.rithmic_user),
                    ("RITHMIC_PASSWORD", self.rithmic_password),
                    ("RITHMIC_SYSTEM_NAME", self.rithmic_system_name),
                    ("RITHMIC_URL/RITHMIC_URI", self.rithmic_url),
                )
                if not value
            ]
            if missing:
                raise RuntimeError(f"Missing Rithmic config for source=rithmic: {', '.join(missing)}")

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="Live MBO Radar", docs_url=None, redoc_url=None)

        @app.get("/health")
        async def health() -> dict[str, Any]:
            return {
                "status": "ok",
                "source": self.source,
                "active_walls": len(self._latest_output_walls),
                "completed_episodes": self._completed_episode_count,
                "last_update_ts": iso_z(self._last_update_ts) if self._last_update_ts is not None else None,
                "connected": self._connected,
                "intent_model_loaded": self._classifier.intent_model_loaded,
                "interaction_model_loaded": self._classifier.interaction_model_loaded,
            }

        @app.get("/walls")
        async def walls() -> dict[str, Any]:
            return {
                "timestamp": self._latest_payload.get("timestamp"),
                "source": self.source,
                "symbol": self._symbol_for_output(),
                "mid_price": self._latest_payload.get("mid_price", 0.0),
                "wall_count": len(self._latest_feature_walls),
                "walls": self._latest_feature_walls,
            }

        return app

    async def _run_health_server(self) -> None:
        config = uvicorn.Config(
            app=self._app,
            host="0.0.0.0",
            port=self.health_port,
            log_level="warning",
            access_log=False,
        )
        self._health_server = uvicorn.Server(config)
        await self._health_server.serve()

    async def _run_source(self) -> None:
        if self.source == "databento":
            await self._run_databento_source()
            return
        if self.source == "rithmic":
            await self._run_rithmic_source()
            return
        await self._run_replay_source()

    async def _run_databento_source(self) -> None:
        if db is None:
            raise RuntimeError("databento is not installed")
        self._databento_loop = asyncio.get_running_loop()
        self._databento_queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._databento_client = db.Live(key=self.databento_api_key)
        self._databento_client.subscribe(
            dataset=DEFAULT_DATABENTO_DATASET,
            schema=DEFAULT_DATABENTO_SCHEMA,
            symbols=[self.databento_symbol],
            stype_in="continuous",
        )
        self._databento_client.add_callback(record_callback=self._on_databento_record)
        add_dc = getattr(self._databento_client, "add_disconnect_callback", None)
        if callable(add_dc):
            add_dc(self._on_databento_disconnect)
        add_rc = getattr(self._databento_client, "add_reconnect_callback", None)
        if callable(add_rc):
            add_rc(self._on_databento_reconnect)
        self._databento_client.start()
        self._connected = True
        logger.info("live_mbo_radar.databento_subscribed symbol=%s", self.databento_symbol)
        try:
            while not self._stop_event.is_set():
                try:
                    assert self._databento_queue is not None
                    record = await asyncio.wait_for(self._databento_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                self._process_mbo_record(record)
        finally:
            client = self._databento_client
            self._databento_client = None
            self._connected = False
            if client is not None:
                stop = getattr(client, "stop", None)
                if callable(stop):
                    try:
                        stop()
                    except Exception:  # noqa: BLE001
                        logger.exception("live_mbo_radar.databento_stop_failed")

    def _on_databento_record(self, record: Any) -> None:
        if self._databento_loop is None or self._databento_queue is None:
            return
        try:
            self._databento_loop.call_soon_threadsafe(self._databento_queue.put_nowait, record)
        except asyncio.QueueFull:
            logger.warning("live_mbo_radar.databento_queue_full")
        except RuntimeError:
            pass

    def _on_databento_disconnect(self, *_: Any, **__: Any) -> None:
        if self._databento_loop is None:
            return
        self._databento_loop.call_soon_threadsafe(self._set_connected, False)

    def _on_databento_reconnect(self, *_: Any, **__: Any) -> None:
        if self._databento_loop is None:
            return
        self._databento_loop.call_soon_threadsafe(self._set_connected, True)

    async def _run_rithmic_source(self) -> None:
        from async_rithmic import DataType, ReconnectionSettings, RithmicClient

        client = RithmicClient(
            user=self.rithmic_user,
            password=self.rithmic_password,
            system_name=self.rithmic_system_name,
            app_name="live_mbo_radar",
            app_version="1.0.0",
            url=self.rithmic_url,
            reconnection_settings=ReconnectionSettings(
                max_retries=20,
                backoff_type="exponential",
                interval=1.0,
                max_delay=60.0,
                jitter_range=(0.5, 1.5),
            ),
        )
        self._rithmic_client = client
        client.on_order_book += self._on_rithmic_order_book
        client.on_connected += lambda _plant_type: self._set_connected(True)
        client.on_disconnected += lambda _plant_type: self._set_connected(False)
        try:
            await client.connect()
            await asyncio.sleep(0.5)
            await client.subscribe_to_market_data(self.rithmic_symbol, self.rithmic_exchange, DataType.ORDER_BOOK)
            self._connected = True
            logger.info(
                "live_mbo_radar.rithmic_subscribed symbol=%s exchange=%s",
                self.rithmic_symbol,
                self.rithmic_exchange,
            )
            while not self._stop_event.is_set():
                await asyncio.sleep(0.25)
        finally:
            self._connected = False
            self._rithmic_client = None
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                logger.exception("live_mbo_radar.rithmic_disconnect_failed")

    def _on_rithmic_order_book(self, update: Any) -> None:
        timestamp = pd.Timestamp.now(tz="UTC")
        bid_update = self._extract_levels(getattr(update, "bid_price", []), getattr(update, "bid_size", []))
        ask_update = self._extract_levels(getattr(update, "ask_price", []), getattr(update, "ask_size", []))
        is_snapshot = getattr(update, "update_type", 0) == 3
        self._apply_rithmic_side_update("bid", _SIDE_BID, bid_update, timestamp, is_snapshot)
        self._apply_rithmic_side_update("ask", _SIDE_ASK, ask_update, timestamp, is_snapshot)
        self._refresh_mid_from_rithmic_book()

    def _extract_levels(self, prices: Any, sizes: Any) -> dict[float, int]:
        levels: dict[float, int] = {}
        for raw_price, raw_size in zip(prices, sizes, strict=False):
            price = self._normalize_price(float(raw_price))
            size = int(raw_size or 0)
            if size > 0:
                levels[price] = size
            elif price > 0:
                levels[price] = 0
        return levels

    def _apply_rithmic_side_update(
        self,
        side_name: str,
        side_code: str,
        updates: dict[float, int],
        timestamp: pd.Timestamp,
        is_snapshot: bool,
    ) -> None:
        previous = dict(self._rithmic_levels[side_name])
        if is_snapshot:
            merged = {price: size for price, size in updates.items() if size > 0}
        else:
            merged = dict(previous)
            for price, size in updates.items():
                if size > 0:
                    merged[price] = size
                else:
                    merged.pop(price, None)

        removed_prices = set(previous) - set(merged) if is_snapshot else {price for price, size in updates.items() if size <= 0 and price in previous}
        for price in sorted(removed_prices):
            self._engine.process_event(
                action=_ACTION_CANCEL,
                side=side_code,
                order_id=self._synthetic_order_id(side_name, price),
                price=price,
                size=0,
                timestamp=timestamp,
            )

        candidate_prices = set(updates) if not is_snapshot else set(merged)
        for price in sorted(candidate_prices):
            new_size = merged.get(price, 0)
            if new_size <= 0:
                continue
            old_size = previous.get(price)
            if old_size is None:
                action = _ACTION_ADD
            elif old_size != new_size:
                action = _ACTION_MODIFY
            else:
                continue
            self._engine.process_event(
                action=action,
                side=side_code,
                order_id=self._synthetic_order_id(side_name, price),
                price=price,
                size=new_size,
                timestamp=timestamp,
            )

        self._rithmic_levels[side_name] = merged
        self._last_update_ts = timestamp
        self._refresh_mid_from_engine()

    def _refresh_mid_from_rithmic_book(self) -> None:
        if self._rithmic_levels["bid"] and self._rithmic_levels["ask"]:
            best_bid = max(self._rithmic_levels["bid"])
            best_ask = min(self._rithmic_levels["ask"])
            self._last_mid_price = (best_bid + best_ask) / 2.0

    async def _run_replay_source(self) -> None:
        if db is None:
            raise RuntimeError("databento is not installed")
        replay_path = Path(self.replay_file or "").expanduser().resolve()
        if not replay_path.exists():
            raise FileNotFoundError(f"Replay file not found: {replay_path}")
        self._connected = True
        logger.info("live_mbo_radar.replay_start file=%s", replay_path)
        store = db.DBNStore.from_file(str(replay_path))
        try:
            for index, record in enumerate(store, start=1):
                if self._stop_event.is_set():
                    break
                self._process_mbo_record(record)
                if index % 5_000 == 0:
                    await asyncio.sleep(0)
        finally:
            self._connected = False
            logger.info("live_mbo_radar.replay_complete file=%s", replay_path)

    def _process_mbo_record(self, record: Any) -> None:
        action = _decode_char(getattr(record, "action", None))
        if action is None:
            return
        self._engine.process_event(
            action=action,
            side=_decode_char(getattr(record, "side", "N")) or "N",
            order_id=int(getattr(record, "order_id", 0) or 0),
            price=self._price_from_record(record),
            size=int(getattr(record, "size", 0) or 0),
            timestamp=self._timestamp_from_record(record),
        )
        self._last_update_ts = self._timestamp_from_record(record)
        self._refresh_mid_from_engine()

    def _timestamp_from_record(self, record: Any) -> pd.Timestamp:
        ts_ns = int(getattr(record, "ts_event", 0) or 0)
        if ts_ns <= 0:
            raise RuntimeError("Encountered MBO record without a valid ts_event timestamp")
        return pd.to_datetime(ts_ns, unit="ns", utc=True)

    def _price_from_record(self, record: Any) -> float:
        raw_price = getattr(record, "price", 0) or 0
        if isinstance(raw_price, int):
            price = raw_price / 1e9
        else:
            price = float(raw_price)
            if price > 1_000_000:
                price /= 1e9
        return self._normalize_price(price)

    def _normalize_price(self, price: float) -> float:
        ticks = round(float(price) / self._engine.tick_size)
        return round(ticks * self._engine.tick_size, 10)

    def _refresh_mid_from_engine(self) -> None:
        dom = getattr(self._engine, "_dom", None)
        if dom is None:
            return
        best_bid, _ = dom.best_bid()
        best_ask, _ = dom.best_ask()
        if best_bid > 0 and best_ask > 0:
            self._last_mid_price = (best_bid + best_ask) / 2.0

    async def _output_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._emit_snapshot()
            except Exception:  # noqa: BLE001
                logger.exception("live_mbo_radar.snapshot_failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.snapshot_interval_sec)
            except asyncio.TimeoutError:
                continue

    async def _emit_snapshot(self, force: bool = False) -> None:
        if not force and self._last_update_ts is None and self.source != "replay":
            return
        drained = self._engine.get_completed_episodes()
        if drained:
            self._completed_episode_count += len(drained)
            logger.info("live_mbo_radar.completed_episodes count=%d", len(drained))

        raw_walls = self._engine.get_active_walls()
        feature_walls = [self._enrich_wall_features(wall) for wall in raw_walls]
        output_walls = [self._to_output_wall(wall) for wall in feature_walls]
        payload = {
            "timestamp": iso_z(self._last_update_ts or utc_now()),
            "symbol": self._symbol_for_output(),
            "mid_price": round(self._last_mid_price, 2) if self._last_mid_price > 0 else 0.0,
            "wall_count": len(output_walls),
            "walls": output_walls,
        }

        self._latest_feature_walls = feature_walls
        self._latest_output_walls = output_walls
        self._latest_payload = payload

        if self.output_path is not None:
            write_payload(self.output_path, payload)
        if self.on_walls_updated is not None:
            result = self.on_walls_updated(output_walls)
            if inspect.isawaitable(result):
                await result

    def _enrich_wall_features(self, wall: dict[str, Any]) -> dict[str, Any]:
        enriched = self._classifier.classify_wall(wall)
        enriched["classification"] = _legacy_classification(enriched.get("intent", "PASSIVE_REAL"))
        enriched["confidence"] = round(float(enriched.get("confidence", 0.0) or 0.0), 4)
        enriched["duration_sec"] = round(float(enriched.get("age_sec", 0.0)), 1)
        return enriched

    def _to_output_wall(self, wall: dict[str, Any]) -> dict[str, Any]:
        return {
            "price": round(float(wall.get("price", 0.0)), 8),
            "side": _normalize_side(wall.get("side", "bid")),
            "size": int(wall.get("size", 0) or 0),
            "max_size": int(wall.get("max_size", 0) or 0),
            "classification": str(wall.get("classification", "GENUINE")),
            "confidence": round(float(wall.get("confidence", 0.0) or 0.0), 4),
            "duration_sec": round(float(wall.get("duration_sec", 0.0) or 0.0), 1),
            "refill_count": int(float(wall.get("refills_so_far", 0.0) or 0.0)),
            "state": str(wall.get("state", "FRESH")),
            "intent": str(wall.get("intent", "PASSIVE_REAL")),
        }

    def _symbol_for_output(self) -> str:
        if self.source == "rithmic":
            return self.rithmic_symbol
        return self.databento_symbol

    def _synthetic_order_id(self, side_name: str, price: float) -> int:
        encoded_price = int(round(price / self._engine.tick_size))
        side_prefix = 1 if side_name == "bid" else 2
        return side_prefix * 1_000_000_000 + encoded_price

    def _set_connected(self, connected: bool) -> None:
        self._connected = connected


def _load_env() -> None:
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, "").strip()
    if value:
        return value
    return default


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live MBO radar service")
    parser.add_argument("--source", choices=["databento", "rithmic", "replay"], default="databento")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--replay-file", default=None)
    parser.add_argument("--health-port", type=int, default=DEFAULT_HEALTH_PORT)
    parser.add_argument("--min-wall", type=int, default=DEFAULT_MIN_WALL)
    parser.add_argument("--snapshot-interval-sec", type=float, default=DEFAULT_SNAPSHOT_INTERVAL_SEC)
    parser.add_argument("--databento-symbol", default=DEFAULT_DATABENTO_SYMBOL)
    parser.add_argument("--rithmic-symbol", default=DEFAULT_RITHMIC_SYMBOL)
    parser.add_argument("--rithmic-exchange", default=DEFAULT_RITHMIC_EXCHANGE)
    parser.add_argument("--intent-model", default=DEFAULT_INTENT_MODEL)
    parser.add_argument("--interaction-model", default=DEFAULT_INTERACTION_MODEL)
    parser.add_argument("--all-hours", action="store_true", help="Process outside RTH (globex/overnight)")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


async def async_main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _load_env()

    service = LiveMBORadar(
        source=args.source,
        output_path=args.output,
        health_port=args.health_port,
        snapshot_interval_sec=args.snapshot_interval_sec,
        min_wall_size=args.min_wall,
        databento_api_key=_env("DATABENTO_API_KEY"),
        databento_symbol=args.databento_symbol,
        rithmic_user=_env("RITHMIC_USER"),
        rithmic_password=_env("RITHMIC_PASSWORD"),
        rithmic_system_name=_env("RITHMIC_SYSTEM_NAME"),
        rithmic_url=_env("RITHMIC_URL", _env("RITHMIC_URI")),
        rithmic_symbol=args.rithmic_symbol,
        rithmic_exchange=args.rithmic_exchange,
        replay_file=args.replay_file,
        intent_model_path=args.intent_model,
        interaction_model_path=args.interaction_model,
        rth_only=not getattr(args, "all_hours", False),
    )

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(service.stop()))
        except NotImplementedError:
            pass

    try:
        await service.start()
    except KeyboardInterrupt:
        logger.info("live_mbo_radar.keyboard_interrupt")
    return 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["LiveMBORadar"]
