from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import signal
import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

LOGGER = logging.getLogger("depth_radar_live")
DEFAULT_SYMBOL = "NQM6"
DEFAULT_EXCHANGE = "CME"
DEFAULT_MIN_WALL = 50
DEFAULT_INTERVAL = 5.0
DEFAULT_PRUNE_SEC = 300.0
MODEL_PATH = Path("deep6/models/depth_radar_classifier_4class.joblib")
OUTPUT_PATH = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "DEEP6" / "depth_radar_walls.json"


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(ts: datetime) -> str:
    return ts.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def _ensure_depth_radar_importable() -> None:
    try:
        importlib.import_module("deep6.ml")
        return
    except ImportError:
        pass

    for mod_name in (
        "deep6.ml.lgbm_trainer",
        "deep6.ml.feature_builder",
        "deep6.ml.hmm_regime",
    ):
        if mod_name in sys.modules:
            continue
        stub = types.ModuleType(mod_name)
        stub.__package__ = "deep6.ml"
        if mod_name == "deep6.ml.feature_builder":
            stub.FEATURE_NAMES = []  # type: ignore[attr-defined]
            stub.build_feature_matrix = None  # type: ignore[attr-defined]
        elif mod_name == "deep6.ml.lgbm_trainer":
            stub.LGBMTrainer = None  # type: ignore[attr-defined]
            stub.WeightFile = None  # type: ignore[attr-defined]
        elif mod_name == "deep6.ml.hmm_regime":
            stub.HMMRegimeDetector = None  # type: ignore[attr-defined]
            stub.RegimeState = None  # type: ignore[attr-defined]
        sys.modules[mod_name] = stub

    sys.modules.pop("deep6.ml", None)
    importlib.import_module("deep6.ml")


def try_load_classifier(model_path: Path):
    try:
        _ensure_depth_radar_importable()
        from deep6.ml.depth_radar.classifier import WallClassifier
        from deep6.ml.depth_radar.wall_features import WallFeatureExtractor

        clf = WallClassifier(model_path=str(model_path))
        extractor = WallFeatureExtractor(normalize=True)
        LOGGER.info("Loaded depth radar model: %s (mode=%s)", model_path, clf.mode)
        return clf, extractor
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Depth radar model unavailable, using rule-based classification: %s", exc)
        return None, None


def try_load_interaction_model(model_path: Path | str):
    try:
        import joblib
        path = Path(model_path)
        if not path.exists():
            LOGGER.info("No wall interaction model at %s — predictions disabled", path)
            return None
        payload = joblib.load(str(path))
        LOGGER.info("Loaded wall interaction model: %s (%d features, classes=%s)",
                     path, len(payload["feature_names"]), payload["class_names"])
        return payload
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Wall interaction model unavailable: %s", exc)
        return None


@dataclass
class WallState:
    side: str
    price: float
    first_seen: datetime
    last_update: datetime
    current_size: int
    max_size: int
    original_size: int
    modification_count: int = 0
    cancellation_events: int = 0
    refill_count: int = 0
    price_crossed: bool = False
    last_nonzero_size: int = 0

    @property
    def duration_sec(self) -> float:
        return max(0.0, (utc_now() - self.first_seen).total_seconds())

    def to_feature_wall(self) -> dict[str, Any]:
        return {
            "time_in_book": self.duration_sec,
            "modification_count": self.modification_count,
            "cancellation_count": self.cancellation_events,
            "original_size": self.original_size,
            "max_size": self.max_size,
            "current_size": self.current_size,
            "refill_count": self.refill_count,
            "price_crossed": self.price_crossed,
            "side": 1 if self.side == "ask" else 0,
            "wall_price": self.price,
            "first_seen_time": self.first_seen.timestamp(),
        }


@dataclass
class DepthRadarLiveService:
    user: str
    password: str
    system_name: str
    url: str
    symbol: str
    exchange: str
    min_wall: int
    interval_sec: float
    output_path: Path
    model_path: Path
    tick_size: float = 0.25
    prune_sec: float = DEFAULT_PRUNE_SEC
    app_name: str = "depth_radar_live"
    _walls: dict[str, dict[float, WallState]] = field(default_factory=lambda: {"bid": {}, "ask": {}})
    _bid_sizes: list[int] = field(default_factory=list)
    _ask_sizes: list[int] = field(default_factory=list)
    _best_bid: float = 0.0
    _best_ask: float = 0.0
    _mid_price: float = 0.0
    _running: bool = field(default=False, init=False)
    _connection_status: str = field(default="disconnected", init=False)

    interaction_model_path: Path = Path("deep6/models/wall_interaction_predictor.joblib")
    _interaction_model: Any = field(default=None, init=False)
    _mid_history: list = field(default_factory=list, init=False)  # (timestamp, mid) for momentum
    _cumulative_delta: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._classifier, self._extractor = try_load_classifier(self.model_path)
        self._interaction_model = try_load_interaction_model(self.interaction_model_path)

    def stop(self) -> None:
        self._running = False

    def _update_side(self, side: str, prices: list[float], sizes: list[int], now: datetime, is_snapshot: bool = False) -> None:
        side_walls = self._walls[side]
        seen_prices: set[float] = set()

        for price, raw_size in zip(prices, sizes):
            price = round(float(price), 8)
            size = int(raw_size)
            seen_prices.add(price)

            st = side_walls.get(price)
            if st is None:
                st = WallState(
                    side=side,
                    price=price,
                    first_seen=now,
                    last_update=now,
                    current_size=size,
                    max_size=size,
                    original_size=size,
                    last_nonzero_size=size,
                )
                side_walls[price] = st
            else:
                prior_size = st.current_size
                if prior_size > 0 and size == 0:
                    st.cancellation_events += 1
                if prior_size == 0 and size > 0:
                    st.cancellation_events += 1
                if prior_size > 0 and size > 0 and size != prior_size:
                    st.modification_count += 1
                if st.max_size > 0 and prior_size < st.max_size * 0.5 and size >= st.max_size * 0.5:
                    st.refill_count += 1
                st.current_size = size
                st.last_update = now
                if size > st.max_size:
                    st.max_size = size

            if size > 0:
                st.last_nonzero_size = size

        # Only zero out unseen levels on full snapshot — SOLO updates are single-level
        if is_snapshot:
            for price, st in list(side_walls.items()):
                if price in seen_prices:
                    continue
                if st.current_size != 0:
                    st.current_size = 0
                    st.cancellation_events += 1
                    st.last_update = now

    def _update_mid_price(self) -> None:
        if self._best_bid > 0 and self._best_ask > 0:
            self._mid_price = (self._best_bid + self._best_ask) / 2.0
        elif self._best_bid > 0:
            self._mid_price = self._best_bid
        elif self._best_ask > 0:
            self._mid_price = self._best_ask

    def _mark_price_crosses(self) -> None:
        if self._mid_price <= 0:
            return
        for price, st in self._walls["bid"].items():
            if not st.price_crossed and self._mid_price < price:
                st.price_crossed = True
        for price, st in self._walls["ask"].items():
            if not st.price_crossed and self._mid_price > price:
                st.price_crossed = True

    def _prune(self, now: datetime) -> None:
        cutoff = now.timestamp() - self.prune_sec
        for side in ("bid", "ask"):
            side_walls = self._walls[side]
            for price in [p for p, st in side_walls.items() if st.last_update.timestamp() < cutoff]:
                del side_walls[price]

    def _avg_wall_size(self) -> float:
        sizes = [st.max_size for side in self._walls.values() for st in side.values() if st.max_size >= self.min_wall]
        return float(sum(sizes) / len(sizes)) if sizes else 1.0

    def _market_context(self) -> dict[str, Any]:
        best_bid = self._best_bid
        best_ask = self._best_ask
        spread = best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0.0
        return {
            "mid_price": self._mid_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "avg_wall_size": self._avg_wall_size(),
            "bid_volumes": self._bid_sizes[:10],
            "ask_volumes": self._ask_sizes[:10],
        }

    def _predict_interaction(self, wall: WallState) -> tuple[str, float] | None:
        """Predict bounce/break/hold if price is near this wall."""
        if self._interaction_model is None or self._mid_price <= 0:
            return None
        dist = abs(self._mid_price - wall.price) / self.tick_size
        if dist > 12:  # only predict within 3 points
            return None
        # Check approach direction
        if wall.side == "bid" and self._mid_price <= wall.price:
            return None  # wrong side
        if wall.side == "ask" and self._mid_price >= wall.price:
            return None

        # Compute momentum
        momentum = 0.0
        approach_speed = 0.0
        if len(self._mid_history) >= 2:
            dt = (self._mid_history[-1][0] - self._mid_history[0][0]).total_seconds()
            if dt > 0:
                pc = (self._mid_history[-1][1] - self._mid_history[0][1]) / self.tick_size
                momentum = pc
                approach_speed = abs(pc) / dt

        bid_vol = sum(self._bid_sizes[:10]) if self._bid_sizes else 0
        ask_vol = sum(self._ask_sizes[:10]) if self._ask_sizes else 0
        imbalance = (bid_vol - ask_vol) / max(1, bid_vol + ask_vol)
        spread = (self._best_ask - self._best_bid) / self.tick_size if self._best_ask > self._best_bid else 0

        model = self._interaction_model
        feat_names = model["feature_names"]
        class_names = model["class_names"]
        import numpy as np

        feat_map = {
            "wall_size": wall.current_size,
            "wall_max_size": wall.max_size,
            "wall_duration_sec": wall.duration_sec,
            "wall_refill_count": wall.refill_count,
            "wall_modification_count": wall.modification_count,
            "wall_cancellation_events": wall.cancellation_events,
            "approach_speed": approach_speed,
            "book_imbalance": imbalance,
            "distance_from_wall": dist,
            "spread": spread,
            "hour_of_day": utc_now().hour,
            "cumulative_delta": self._cumulative_delta,
            "price_momentum_10s": momentum,
        }
        features = np.array([[feat_map.get(f, 0) for f in feat_names]], dtype=np.float64)
        probs = model["model"].predict(features)[0]
        pred_idx = int(np.argmax(probs))
        pred_label = class_names[pred_idx]
        pred_conf = float(probs[pred_idx])
        return pred_label, pred_conf

    def _rule_classify(self, wall: WallState) -> tuple[str, float]:
        if wall.cancellation_events >= 2 and wall.duration_sec < 2.0 and wall.max_size > 200:
            return "SPOOF", 0.9
        if wall.refill_count >= 2:
            return "ICEBERG", min(1.0, 0.6 + 0.1 * wall.refill_count)
        if wall.price_crossed:
            return "STALE", 0.8
        return "GENUINE", 0.75

    def _classify(self, wall: WallState, market_context: dict[str, Any]) -> tuple[str, float]:
        if self._classifier is None or self._extractor is None:
            return self._rule_classify(wall)

        try:
            features = self._extractor.extract(wall.to_feature_wall(), market_context)
            label, confidence = self._classifier.classify(features)
            if label == "NOT_SPOOF":
                label = "GENUINE"
            if label not in {"GENUINE", "SPOOF", "ICEBERG", "STALE"}:
                return self._rule_classify(wall)
            return label, float(confidence)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("ML classification failed at %s %s %.2f: %s", self.symbol, wall.side, wall.price, exc)
            return self._rule_classify(wall)

    def _build_payload(self) -> dict[str, Any]:
        now = utc_now()
        self._mark_price_crosses()
        self._prune(now)
        market_context = self._market_context()
        walls: list[dict[str, Any]] = []

        for side in ("bid", "ask"):
            for price, st in sorted(self._walls[side].items(), key=lambda item: item[0]):
                if st.max_size < self.min_wall or st.current_size <= 0:
                    continue
                classification, confidence = self._classify(st, market_context)
                # Map classification to V4 intent taxonomy
                _INTENT_MAP = {
                    "SPOOF": "SPOOF_LIKE",
                    "ICEBERG": "RESERVE_REFRESH",
                    "STALE": "PASSIVE_REAL",
                    "GENUINE": "PASSIVE_REAL",
                }
                intent = _INTENT_MAP.get(classification, "PASSIVE_REAL")

                # Infer wall state from lifecycle signals
                age = st.duration_sec
                if st.price_crossed:
                    state = "STALE"
                elif age < 15.0 and st.modification_count == 0:
                    state = "FRESH"
                elif st.refill_count >= 2 and st.current_size > 0:
                    state = "DEFENDING"
                elif st.current_size < st.max_size * 0.25 and st.max_size > 0:
                    state = "EXHAUSTED"
                else:
                    state = "ESTABLISHED"

                wall_entry = {
                    "price": round(price, 8),
                    "side": side,
                    "size": int(st.current_size),
                    "max_size": int(st.max_size),
                    "classification": classification,
                    "intent": intent,
                    "state": state,
                    "confidence": round(max(0.0, min(1.0, confidence)), 4),
                    "duration_sec": round(st.duration_sec, 1),
                    "refill_count": int(st.refill_count),
                }
                # Add interaction prediction if price is near this wall
                interaction = self._predict_interaction(st)
                if interaction is not None:
                    wall_entry["interaction"] = interaction[0]  # BOUNCE/BREAK/HOLD
                    wall_entry["interaction_confidence"] = round(interaction[1], 4)
                walls.append(wall_entry)

        return {
            "timestamp": iso_z(now),
            "symbol": self.symbol,
            "mid_price": round(self._mid_price, 2) if self._mid_price > 0 else 0.0,
            "wall_count": len(walls),
            "walls": walls,
        }

    def _on_order_book(self, update: Any) -> None:
        now = utc_now()
        bid_prices = [float(p) for p in getattr(update, "bid_price", [])]
        bid_sizes = [int(s) for s in getattr(update, "bid_size", [])]
        ask_prices = [float(p) for p in getattr(update, "ask_price", [])]
        ask_sizes = [int(s) for s in getattr(update, "ask_size", [])]

        self._bid_sizes = bid_sizes
        self._ask_sizes = ask_sizes
        self._best_bid = max(bid_prices) if bid_prices else 0.0
        self._best_ask = min(ask_prices) if ask_prices else 0.0
        self._update_mid_price()
        # Track mid history for momentum (last 10 seconds)
        if self._mid_price > 0:
            self._mid_history.append((now, self._mid_price))
            cutoff = now - __import__("datetime").timedelta(seconds=10)
            while self._mid_history and self._mid_history[0][0] < cutoff:
                self._mid_history.pop(0)
        # update_type 3 = SNAPSHOT_IMAGE — contains all levels; others are incremental
        is_snapshot = getattr(update, "update_type", 0) == 3
        self._update_side("bid", bid_prices, bid_sizes, now, is_snapshot=is_snapshot)
        self._update_side("ask", ask_prices, ask_sizes, now, is_snapshot=is_snapshot)

    async def _write_loop(self) -> None:
        while self._running:
            try:
                payload = self._build_payload()
                write_payload(self.output_path, payload)
                LOGGER.info(
                    "Wrote %s walls to %s (mid=%.2f)",
                    payload["wall_count"],
                    self.output_path,
                    payload["mid_price"],
                )
            except Exception:  # noqa: BLE001
                LOGGER.exception("Failed to write depth radar payload")
            await asyncio.sleep(self.interval_sec)

    async def run(self) -> int:
        from async_rithmic import DataType, ReconnectionSettings, RithmicClient

        self._running = True
        client = RithmicClient(
            user=self.user,
            password=self.password,
            system_name=self.system_name,
            app_name=self.app_name,
            app_version="1.0.0",
            url=self.url,
            reconnection_settings=ReconnectionSettings(
                max_retries=20,
                backoff_type="exponential",
                interval=1.0,
                max_delay=60.0,
                jitter_range=(0.5, 1.5),
            ),
        )

        client.on_order_book += self._on_order_book
        client.on_connected += lambda _plant_type: LOGGER.info("Rithmic connected")
        client.on_disconnected += lambda _plant_type: LOGGER.warning("Rithmic disconnected")

        try:
            LOGGER.info(
                "Connecting to Rithmic: system=%s, url=%s, symbol=%s/%s",
                self.system_name,
                self.url,
                self.symbol,
                self.exchange,
            )
            await client.connect()
            await asyncio.sleep(0.5)
            await client.subscribe_to_market_data(self.symbol, self.exchange, DataType.ORDER_BOOK)
            self._connection_status = "streaming"
            LOGGER.info("Subscribed to %s/%s order book", self.symbol, self.exchange)

            write_task = asyncio.create_task(self._write_loop())
            while self._running:
                await asyncio.sleep(0.25)

            write_task.cancel()
            try:
                await write_task
            except asyncio.CancelledError:
                pass
        except KeyboardInterrupt:
            LOGGER.info("Keyboard interrupt")
        except Exception:  # noqa: BLE001
            LOGGER.exception("Fatal error in depth radar live service")
            return 1
        finally:
            self._connection_status = "disconnected"
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                LOGGER.exception("Error during disconnect")

        return 0


def load_env(project_root: Path) -> None:
    env_path = project_root / ".env"
    load_dotenv(env_path, override=False)


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rithmic live Depth Radar JSON bridge")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL)
    parser.add_argument("--exchange", default=DEFAULT_EXCHANGE)
    parser.add_argument("--min-wall", type=int, default=DEFAULT_MIN_WALL)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    project_root = Path(__file__).resolve().parent.parent
    load_env(project_root)
    output_path = args.output if args.output.is_absolute() else (project_root / args.output)
    model_path = args.model if args.model.is_absolute() else (project_root / args.model)

    service = DepthRadarLiveService(
        user=require_env("RITHMIC_USER"),
        password=require_env("RITHMIC_PASSWORD"),
        system_name=require_env("RITHMIC_SYSTEM_NAME"),
        url=require_env("RITHMIC_URI"),
        symbol=args.symbol,
        exchange=args.exchange,
        min_wall=args.min_wall,
        interval_sec=max(1.0, args.interval),
        output_path=output_path,
        model_path=model_path,
    )

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, service.stop)
            except NotImplementedError:
                pass

    return await service.run()


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
