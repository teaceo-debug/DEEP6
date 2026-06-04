from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor

from depth_radar_desktop.constants import MAX_ALERTS, TICK_SIZE
from depth_radar_desktop.theme import COLORS


class AlertEntry(QFrame):
    """Single alert row with flash animation."""

    def __init__(
        self,
        timestamp: str,
        price: float,
        side: str,
        outcome: str,
        distance: float,
        parent=None,
    ):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background-color: transparent; padding: 4px 8px;")

        # Color by outcome
        outcome_colors = {
            "BOUNCE": COLORS["green"],
            "BREAK": COLORS["red"],
            "CHURN": COLORS["text_secondary"],
        }
        color = outcome_colors.get(outcome, COLORS["text_secondary"])
        side_text = (
            "ASK"
            if side == "ask"
            or (isinstance(side, (int, float)) and float(side) >= 0.5)
            else "BID"
        )

        label = QLabel(
            f'<span style="color:{COLORS["text_secondary"]}">{timestamp}</span> '
            f'<span style="color:{color}">●</span> '
            f'<span style="color:{COLORS["text_primary"]}">{price:.2f}</span> '
            f'<span style="color:{COLORS["green"] if side_text == "BID" else COLORS["red"]}">{side_text}</span> '
            f'<span style="color:{color}">{outcome}</span> '
            f'<span style="color:{COLORS["text_secondary"]}">({distance:.1f}t)</span>',
            self,
        )
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px; background: transparent;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)


class AlertsPanel(QWidget):
    """Scrollable log of recent touch events."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: deque[AlertEntry] = deque(maxlen=MAX_ALERTS)
        self._seen_touches: set[str] = set()

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("border: none; background: transparent;")

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(2)
        self._container_layout.addStretch()
        self._scroll.setWidget(self._container)

        # Title
        title = QLabel("Touch Alerts")
        title.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 11px; "
            f"font-weight: bold; padding: 4px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self._scroll)

    def add_alert(
        self,
        wall: dict,
        mid_price: float,
        predicted_outcome: str = "CHURN",
    ) -> None:
        price = float(wall.get("price", 0))
        side = wall.get("side", 0)
        distance = abs(price - mid_price) / TICK_SIZE if mid_price > 0 else 0
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

        entry = AlertEntry(
            timestamp, price, side, predicted_outcome, distance, self._container
        )

        # Remove oldest if at capacity
        if len(self._entries) >= MAX_ALERTS:
            old = self._entries.popleft()
            self._container_layout.removeWidget(old)
            old.deleteLater()

        # Insert before the stretch
        self._container_layout.insertWidget(
            self._container_layout.count() - 1, entry
        )
        self._entries.append(entry)

        # Auto-scroll to bottom
        scrollbar = self._scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def update_from_walls(self, walls: list[dict], mid_price: float) -> None:
        """Detect walls newly entering touch band and fire alerts."""
        current_in_band: set[str] = set()
        for wall in walls:
            ep_id = str(wall.get("episode_id", ""))
            in_band = bool(wall.get("in_touch_band", False))
            if in_band:
                current_in_band.add(ep_id)
                if ep_id not in self._seen_touches:
                    outcome = str(
                        wall.get(
                            "interaction_prediction",
                            wall.get("predicted_outcome", "CHURN"),
                        )
                    )
                    self.add_alert(wall, mid_price, outcome)
        self._seen_touches = current_in_band
