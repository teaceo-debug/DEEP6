"""Active Walls QTableView — real-time wall detection display."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QLabel, QTableView, QVBoxLayout, QWidget

from depth_radar_desktop.theme import COLORS

COLUMNS = ["Price", "Side", "Size", "Max", "Intent", "State", "Conf%", "Age"]
COLUMN_KEYS = [
    "price",
    "side",
    "size",
    "max_size",
    "intent",
    "state",
    "confidence",
    "age_sec",
]
COLUMN_WIDTHS = [100, 60, 70, 70, 130, 120, 60, 60]

# Pre-built brushes (avoid per-cell allocation)
_BRUSH_GREEN = QBrush(QColor(COLORS["green"]))
_BRUSH_RED = QBrush(QColor(COLORS["red"]))
_BRUSH_AMBER = QBrush(QColor(COLORS["amber"]))
_BG_BID = QBrush(QColor(63, 185, 80, 15))
_BG_ASK = QBrush(QColor(248, 81, 73, 15))

_ALIGN_RIGHT = int(Qt.AlignRight | Qt.AlignVCenter)
_ALIGN_CENTER = int(Qt.AlignCenter | Qt.AlignVCenter)
_ALIGN_LEFT = int(Qt.AlignLeft | Qt.AlignVCenter)

_RIGHT_ALIGNED_KEYS = frozenset({"price", "size", "max_size", "confidence", "age_sec"})


class WallsTableModel(QAbstractTableModel):
    """Model backing the active-walls table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._walls: list[dict[str, Any]] = []

    # --- required overrides ---------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._walls)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(COLUMNS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ) -> str | None:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._walls):
            return None

        wall = self._walls[index.row()]
        key = COLUMN_KEYS[index.column()]
        value = wall.get(key, "")

        if role == Qt.DisplayRole:
            return self._format_value(key, value)
        if role == Qt.ForegroundRole:
            return self._foreground(wall, key, value)
        if role == Qt.BackgroundRole:
            return self._background(wall)
        if role == Qt.TextAlignmentRole:
            return self._alignment(key)
        return None

    # --- public API -----------------------------------------------------------

    def update_walls(self, walls: list[dict[str, Any]]) -> None:
        """Replace wall data wholesale and notify views."""
        self.beginResetModel()
        self._walls = list(walls)
        self.endResetModel()

    # --- private helpers ------------------------------------------------------

    @staticmethod
    def _format_value(key: str, value: Any) -> str:
        if key == "price":
            return f"{float(value):.2f}"
        if key == "side":
            return "ASK" if float(value) >= 0.5 else "BID"
        if key in ("size", "max_size"):
            return str(int(value))
        if key == "confidence":
            return f"{float(value):.0%}"
        if key == "age_sec":
            return f"{float(value):.0f}s"
        return str(value)

    @staticmethod
    def _foreground(wall: dict[str, Any], key: str, value: Any) -> QBrush | None:
        if key == "intent" and str(value) == "SPOOF_LIKE":
            return _BRUSH_AMBER
        if key == "state" and str(value) == "UNDER_ATTACK":
            return _BRUSH_RED
        if key == "side":
            return _BRUSH_GREEN if float(value) < 0.5 else _BRUSH_RED
        return None

    @staticmethod
    def _background(wall: dict[str, Any]) -> QBrush:
        side = float(wall.get("side", 0))
        return _BG_BID if side < 0.5 else _BG_ASK

    @staticmethod
    def _alignment(key: str) -> int:
        if key in _RIGHT_ALIGNED_KEYS:
            return _ALIGN_RIGHT
        if key == "side":
            return _ALIGN_CENTER
        return _ALIGN_LEFT


class WallsTableView(QWidget):
    """Composite widget: QTableView + empty-state overlay for active walls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._model = WallsTableModel(self)

        self._table = QTableView(self)
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)

        for i, width in enumerate(COLUMN_WIDTHS):
            self._table.setColumnWidth(i, width)

        # Empty-state overlay
        self._empty_label = QLabel("No Active Walls", self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 16px;"
        )
        self._empty_label.setVisible(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

        self._empty_label.raise_()

    # --- public API -----------------------------------------------------------

    def update_walls(self, walls: list[dict[str, Any]]) -> None:
        """Push new wall data into the model and toggle empty state."""
        self._model.update_walls(walls)
        self._empty_label.setVisible(len(walls) == 0)

    # --- geometry -------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._empty_label.setGeometry(self.rect())
