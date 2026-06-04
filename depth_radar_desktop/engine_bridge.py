from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

_VALID_SOURCES = {"rithmic", "replay", "none"}


class EngineBridge(QObject):
    walls_updated = Signal(list)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)
    engine_stats = Signal(dict)

    def __init__(
        self,
        source: str = "rithmic",
        rithmic_user: str = "",
        rithmic_password: str = "",
        rithmic_system_name: str = "",
        rithmic_url: str = "",
        rithmic_symbol: str = "NQM6",
        rithmic_exchange: str = "CME",
        replay_file: str | None = None,
        min_wall_size: int = 50,
        rth_only: bool = True,
        intent_model_path: str | None = None,
        interaction_model_path: str | None = None,
        output_path: str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)

        normalized_source = str(source).strip().lower()
        if normalized_source not in _VALID_SOURCES:
            raise ValueError(f"Unsupported source: {source!r}")

        self._source = normalized_source
        self.rithmic_user = rithmic_user
        self.rithmic_password = rithmic_password
        self.rithmic_system_name = rithmic_system_name
        self.rithmic_url = rithmic_url
        self.rithmic_symbol = rithmic_symbol
        self.rithmic_exchange = rithmic_exchange
        self.replay_file = replay_file
        self.min_wall_size = int(min_wall_size)
        self.rth_only = bool(rth_only)
        self.intent_model_path = intent_model_path
        self.interaction_model_path = interaction_model_path
        self.output_path = output_path

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._thread_lock = threading.Lock()
        self._last_connection_state: bool | None = None
        self._last_stats: dict[str, int] | None = None

    def start(self) -> None:
        """Start the engine thread. Non-blocking."""
        with self._thread_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event = threading.Event()
            self._last_connection_state = None
            self._last_stats = None
            if self.source == "none":
                self._emit_stats(active_walls=0, completed_episodes=0)
                self._emit_connection_state(False)
            self._thread = threading.Thread(target=self._run_thread, daemon=True, name="engine-bridge")
            self._thread.start()

    def stop(self) -> None:
        """Stop the engine thread. Blocks until thread exits (max 10s)."""
        thread: threading.Thread | None
        with self._thread_lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()

        thread.join(timeout=10.0)
        if thread.is_alive():
            logger.error("engine_bridge.stop_timeout")
            self.error_occurred.emit("Engine thread did not stop within 10 seconds")
            return

        with self._thread_lock:
            if self._thread is thread:
                self._thread = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def source(self) -> str:
        return self._source

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._engine_loop())
        except Exception as exc:  # noqa: BLE001
            logger.exception("engine_bridge.thread_error")
            self.error_occurred.emit(str(exc))
            self._emit_connection_state(False)
        finally:
            with self._thread_lock:
                current = threading.current_thread()
                if self._thread is current:
                    self._thread = None

    async def _engine_loop(self) -> None:
        if self.source == "none":
            await self._run_none_loop()
            return

        radar = None
        monitor_task: asyncio.Task[None] | None = None
        radar_task: asyncio.Task[None] | None = None
        stop_task: asyncio.Task[None] | None = None

        try:
            radar = self._build_radar()
            radar_task = asyncio.create_task(radar.start(), name="engine_bridge_radar")
            monitor_task = asyncio.create_task(self._monitor_radar(radar), name="engine_bridge_monitor")
            stop_task = asyncio.create_task(self._wait_for_stop(), name="engine_bridge_stop_wait")

            done, pending = await asyncio.wait(
                {radar_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

            if radar_task in done:
                await radar_task
            if stop_task in done:
                await stop_task
        except RuntimeError as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("engine_bridge.engine_error")
            self.error_occurred.emit(str(exc))
        finally:
            if monitor_task is not None:
                monitor_task.cancel()
                await asyncio.gather(monitor_task, return_exceptions=True)
            if radar_task is not None and not radar_task.done():
                radar_task.cancel()
                await asyncio.gather(radar_task, return_exceptions=True)
            if radar is not None:
                try:
                    await radar.stop()
                except Exception:  # noqa: BLE001
                    logger.exception("engine_bridge.stop_failed")
            self._emit_stats(active_walls=0, completed_episodes=0)
            self._emit_connection_state(False)

    async def _run_none_loop(self) -> None:
        self._emit_stats(active_walls=0, completed_episodes=0)
        self._emit_connection_state(False)
        while not self._stop_event.is_set():
            await asyncio.sleep(0.5)

    def _build_radar(self) -> Any:
        from deep6.services.live_mbo_radar import LiveMBORadar

        kwargs: dict[str, Any] = dict(
            source=self.source,
            on_walls_updated=self._on_walls_callback,
            min_wall_size=self.min_wall_size,
            rth_only=self.rth_only,
            rithmic_user=self.rithmic_user,
            rithmic_password=self.rithmic_password,
            rithmic_system_name=self.rithmic_system_name,
            rithmic_url=self.rithmic_url,
            rithmic_symbol=self.rithmic_symbol,
            rithmic_exchange=self.rithmic_exchange,
            replay_file=self.replay_file,
            intent_model_path=self.intent_model_path,
            interaction_model_path=self.interaction_model_path,
        )
        if self.output_path:
            kwargs["output_path"] = Path(self.output_path)
        return LiveMBORadar(**kwargs)

    async def _monitor_radar(self, radar: Any) -> None:
        while not self._stop_event.is_set():
            self._emit_connection_state(bool(getattr(radar, "_connected", False)))
            self._emit_stats(
                active_walls=len(list(getattr(radar, "_latest_output_walls", []))),
                completed_episodes=int(getattr(radar, "_completed_episode_count", 0)),
            )
            await asyncio.sleep(0.25)

        self._emit_connection_state(bool(getattr(radar, "_connected", False)))
        self._emit_stats(
            active_walls=len(list(getattr(radar, "_latest_output_walls", []))),
            completed_episodes=int(getattr(radar, "_completed_episode_count", 0)),
        )

    async def _wait_for_stop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(0.1)

    def _on_walls_callback(self, walls: list[dict[str, Any]]) -> None:
        wall_copies = [dict(wall) for wall in walls]
        self.walls_updated.emit(wall_copies)
        self._emit_stats(active_walls=len(wall_copies), completed_episodes=self._last_completed_episodes())

    def _last_completed_episodes(self) -> int:
        if self._last_stats is None:
            return 0
        return int(self._last_stats.get("completed_episodes", 0))

    def _emit_connection_state(self, connected: bool) -> None:
        if self._last_connection_state is connected:
            return
        self._last_connection_state = connected
        self.connection_changed.emit(connected)

    def _emit_stats(self, active_walls: int, completed_episodes: int) -> None:
        payload = {
            "active_walls": int(active_walls),
            "completed_episodes": int(completed_episodes),
        }
        if self._last_stats == payload:
            return
        self._last_stats = dict(payload)
        self.engine_stats.emit(dict(payload))
