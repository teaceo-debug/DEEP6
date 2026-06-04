from __future__ import annotations

import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from depth_radar_desktop.constants import MARKETS_CLOSED_TIMEOUT_SEC, UPDATE_INTERVAL_MS
from depth_radar_desktop.engine_bridge import EngineBridge
from depth_radar_desktop.live.alerts_panel import AlertsPanel
from depth_radar_desktop.live.feature_gauges import FeatureGaugesPanel
from depth_radar_desktop.live.walls_table import WallsTableView


class LiveTab(QWidget):
    """Assembles all live panel widgets and connects to EngineBridge signals."""

    def __init__(self, bridge: EngineBridge, parent=None):
        super().__init__(parent)
        self._bridge = bridge
        self._last_wall_update_time = 0.0
        self._mid_price = 0.0

        self._walls_table = WallsTableView(self)
        self._gauges = FeatureGaugesPanel(self)
        self._alerts = AlertsPanel(self)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self._gauges)
        right_splitter.addWidget(self._alerts)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 2)

        main_splitter = QSplitter(Qt.Horizontal, self)
        main_splitter.addWidget(self._walls_table)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 7)
        main_splitter.setStretchFactor(1, 3)

        self._markets_closed_label = QLabel("Markets Closed", self)
        self._markets_closed_label.setAlignment(Qt.AlignCenter)
        self._markets_closed_label.setStyleSheet(
            "color: #8b949e; font-size: 24px; background-color: rgba(13, 17, 23, 180); border-radius: 8px;"
        )
        self._markets_closed_label.setVisible(False)
        self._markets_closed_label.raise_()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(main_splitter)

        self._bridge.walls_updated.connect(self._on_walls_updated)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(UPDATE_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start()

    def set_bridge(self, bridge: EngineBridge) -> None:
        """Reconnect to a new EngineBridge after refresh."""
        try:
            self._bridge.walls_updated.disconnect(self._on_walls_updated)
        except RuntimeError:
            pass
        self._bridge = bridge
        self._bridge.walls_updated.connect(self._on_walls_updated)

    def _on_walls_updated(self, walls: list[dict]) -> None:
        self._last_wall_update_time = time.monotonic()

        if walls:
            prices = [float(wall.get("price", 0.0)) for wall in walls]
            if prices:
                self._mid_price = sum(prices) / len(prices)

        self._walls_table.update_walls(walls)
        self._gauges.update_gauges(walls, self._mid_price)
        self._alerts.update_from_walls(walls, self._mid_price)
        self._markets_closed_label.setVisible(False)

    def _on_refresh_tick(self) -> None:
        if self._last_wall_update_time <= 0:
            return

        elapsed = time.monotonic() - self._last_wall_update_time
        if elapsed > MARKETS_CLOSED_TIMEOUT_SEC:
            self._markets_closed_label.setVisible(True)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._markets_closed_label.setGeometry(self.rect())
