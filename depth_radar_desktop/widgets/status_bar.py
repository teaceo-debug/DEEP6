from __future__ import annotations

from PySide6.QtWidgets import QStatusBar, QLabel
from PySide6.QtCore import Qt

from depth_radar_desktop.theme import COLORS


class ConnectionStatusBar(QStatusBar):
    """Status bar showing connection, model, wall count, and timestamp."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeGripEnabled(False)

        self._connection_label = QLabel()
        self._model_label = QLabel()
        self._wall_count_label = QLabel()
        self._timestamp_label = QLabel()

        # Style all labels
        label_style = (
            "font-family: Consolas, monospace; font-size: 11px; padding: 0 8px;"
        )
        for label in [
            self._connection_label,
            self._model_label,
            self._wall_count_label,
            self._timestamp_label,
        ]:
            label.setStyleSheet(label_style)

        self.addWidget(self._connection_label)
        self.addWidget(self._model_label)
        self.addPermanentWidget(self._wall_count_label)
        self.addPermanentWidget(self._timestamp_label)

        # Set defaults
        self.set_connected(False)
        self.set_model_status(False, False)
        self.update_stats(0, "\u2014")

    def set_connected(self, connected: bool) -> None:
        if connected:
            self._connection_label.setText(
                f'<span style="color:{COLORS["green"]}">● Connected</span>'
            )
        else:
            self._connection_label.setText(
                f'<span style="color:{COLORS["red"]}">● Disconnected</span>'
            )
        self._connection_label.setTextFormat(Qt.RichText)

    def set_model_status(
        self, intent_loaded: bool, interaction_loaded: bool
    ) -> None:
        i_icon = (
            f'<span style="color:{COLORS["green"]}">✓</span>'
            if intent_loaded
            else f'<span style="color:{COLORS["red"]}">✗</span>'
        )
        x_icon = (
            f'<span style="color:{COLORS["green"]}">✓</span>'
            if interaction_loaded
            else f'<span style="color:{COLORS["red"]}">✗</span>'
        )
        self._model_label.setText(
            f"Models: {i_icon} Intent {x_icon} Interaction"
        )
        self._model_label.setTextFormat(Qt.RichText)

    def update_stats(self, wall_count: int, timestamp: str) -> None:
        self._wall_count_label.setText(f"Walls: {wall_count} active")
        self._timestamp_label.setText(f"Last: {timestamp}")
