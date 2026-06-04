from __future__ import annotations

import logging

from depth_radar_desktop.config import DepthRadarConfig, load_config
from depth_radar_desktop.engine_bridge import EngineBridge

logger = logging.getLogger(__name__)


class EngineWorker:
    """Configures and manages the EngineBridge from app config."""

    def __init__(self, config: DepthRadarConfig | None = None, parent=None) -> None:
        self._config = config or load_config()
        self._bridge = EngineBridge(
            source=self._config.source,
            rithmic_user=self._config.rithmic_user,
            rithmic_password=self._config.rithmic_password,
            rithmic_system_name=self._config.rithmic_system_name,
            rithmic_url=self._config.rithmic_url,
            rithmic_symbol=self._config.rithmic_symbol,
            rithmic_exchange=self._config.rithmic_exchange,
            replay_file=self._config.replay_file or None,
            min_wall_size=self._config.min_wall_size,
            rth_only=self._config.rth_only,
            intent_model_path=str(self._config.intent_model_path),
            interaction_model_path=str(self._config.interaction_model_path),
            output_path=self._config.nt8_output_path,
            parent=parent,
        )

    @property
    def bridge(self) -> EngineBridge:
        return self._bridge

    @property
    def config(self) -> DepthRadarConfig:
        return self._config

    def start(self) -> None:
        logger.info("engine_worker.starting source=%s", self._config.source)
        self._bridge.start()

    def stop(self) -> None:
        logger.info("engine_worker.stopping")
        self._bridge.stop()
