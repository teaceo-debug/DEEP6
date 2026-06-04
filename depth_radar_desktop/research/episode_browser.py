from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from depth_radar_desktop.theme import COLORS, FONTS

logger = logging.getLogger(__name__)

INTENT_OPTIONS = ["All", "PASSIVE_REAL", "SPOOF_LIKE", "RESERVE_REFRESH", "MIGRATORY"]
OUTCOME_OPTIONS = ["All", "BOUNCE", "BREAK", "CHURN"]

_AMBER = QColor(COLORS["amber"])
_GREEN = QColor(COLORS["green"])
_RED = QColor(COLORS["red"])


class EpisodeTableModel(QAbstractTableModel):
    """Model for the episode list table."""

    DISPLAY_COLUMNS = [
        ("Session", "session_date"),
        ("Side", "side"),
        ("Price", "price"),
        ("Intent", "intent_label"),
        ("State", "final_state"),
        ("Reason", "retirement_reason"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._df = pd.DataFrame()
        self._filtered_df = pd.DataFrame()
        self._intent_filter = "All"

    def set_data(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df.copy()
        self._apply_filter()
        self.endResetModel()

    def set_intent_filter(self, intent: str) -> None:
        self.beginResetModel()
        self._intent_filter = intent
        self._apply_filter()
        self.endResetModel()

    def _apply_filter(self) -> None:
        df = self._df
        if self._intent_filter != "All" and "intent_label" in df.columns:
            mask = df["intent_label"].astype(str).str.upper() == self._intent_filter.upper()
            df = df[mask]
        self._filtered_df = df.reset_index(drop=True)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._filtered_df)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.DISPLAY_COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole
    ) -> str | None:
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.DISPLAY_COLUMNS[section][0]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._filtered_df):
            return None

        col_key = self.DISPLAY_COLUMNS[index.column()][1]
        value = self._filtered_df.iloc[index.row()].get(col_key, "")

        if role == Qt.DisplayRole:
            if col_key == "price":
                try:
                    return f"{float(value):.2f}"
                except (ValueError, TypeError):
                    return str(value)
            return str(value) if pd.notna(value) else ""

        if role == Qt.ForegroundRole:
            text = str(value)
            if col_key == "intent_label" and text == "SPOOF_LIKE":
                return QBrush(_AMBER)
            if col_key == "side":
                return QBrush(_GREEN if text == "bid" else _RED)

        return None

    def get_episode_row(self, row: int) -> dict:
        if 0 <= row < len(self._filtered_df):
            return self._filtered_df.iloc[row].to_dict()
        return {}


class EpisodeBrowser(QWidget):
    """Master-detail episode browser with filtering."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._episodes_df = pd.DataFrame()
        self._snapshots_df = pd.DataFrame()
        self._touches_df = pd.DataFrame()

        # --- filter bar ---
        filter_bar = QFrame(self)
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(4, 4, 4, 4)

        filter_layout.addWidget(QLabel("Intent:"))
        self._intent_combo = QComboBox()
        self._intent_combo.addItems(INTENT_OPTIONS)
        self._intent_combo.currentTextChanged.connect(self._on_intent_filter_changed)
        filter_layout.addWidget(self._intent_combo)

        self._count_label = QLabel("0 episodes")
        self._count_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_layout.addStretch()
        filter_layout.addWidget(self._count_label)

        # --- episode table (left) ---
        self._model = EpisodeTableModel(self)
        self._table = QTableView(self)
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.selectionModel().currentRowChanged.connect(self._on_row_selected)

        # --- detail view (right) ---
        self._detail = QTextEdit(self)
        self._detail.setReadOnly(True)
        self._detail.setStyleSheet(
            f"font-family: {FONTS['monospace']}; font-size: 12px; "
            f"background-color: {COLORS['background']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border']};"
        )
        self._detail.setPlaceholderText("Select an episode to view details")

        # --- empty state ---
        self._empty_label = QLabel("No training data found.\nRun training first.", self)
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 16px;"
        )
        self._empty_label.setVisible(True)

        # --- splitter ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._table)
        splitter.addWidget(self._detail)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setVisible(False)
        self._splitter = splitter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(filter_bar)
        layout.addWidget(splitter)
        layout.addWidget(self._empty_label)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------

    def load_data(self, directory: Path) -> None:
        """Load episodes, snapshots, and touches from parquet files."""
        directory = Path(directory)
        episodes_path = directory / "episodes.parquet"
        snapshots_path = directory / "snapshots.parquet"
        touches_path = directory / "touches.parquet"

        if not episodes_path.exists():
            logger.warning("episode_browser.no_data dir=%s", directory)
            self._empty_label.setVisible(True)
            self._splitter.setVisible(False)
            return

        try:
            self._episodes_df = pd.read_parquet(episodes_path)
            if snapshots_path.exists():
                self._snapshots_df = pd.read_parquet(snapshots_path)
            if touches_path.exists():
                self._touches_df = pd.read_parquet(touches_path)

            self._model.set_data(self._episodes_df)
            self._count_label.setText(f"{len(self._episodes_df)} episodes")
            self._empty_label.setVisible(False)
            self._splitter.setVisible(True)
            logger.info(
                "episode_browser.loaded episodes=%d snapshots=%d touches=%d",
                len(self._episodes_df),
                len(self._snapshots_df),
                len(self._touches_df),
            )
        except Exception as exc:
            logger.error("episode_browser.load_failed error=%s", exc)
            self._empty_label.setText(f"Error loading data: {exc}")
            self._empty_label.setVisible(True)
            self._splitter.setVisible(False)

    # ------------------------------------------------------------------
    # slots
    # ------------------------------------------------------------------

    def _on_intent_filter_changed(self, intent: str) -> None:
        self._model.set_intent_filter(intent)
        self._count_label.setText(f"{self._model.rowCount()} episodes")

    def _on_row_selected(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            self._detail.clear()
            return
        episode = self._model.get_episode_row(current.row())
        self._show_detail(episode)

    # ------------------------------------------------------------------
    # detail rendering
    # ------------------------------------------------------------------

    def _show_detail(self, episode: dict) -> None:
        ep_id = str(episode.get("episode_id", ""))
        duration = episode.get("duration_sec", 0)
        try:
            dur_str = f"{float(duration):.1f}s"
        except (ValueError, TypeError):
            dur_str = str(duration)

        lines = [
            f"Episode: {ep_id}",
            f"Session: {episode.get('session_date', '')}",
            f"Side: {episode.get('side', '')}  Price: {episode.get('price', '')}",
            f"Intent: {episode.get('intent_label', '')}",
            f"Final State: {episode.get('final_state', '')}",
            f"Retirement: {episode.get('retirement_reason', '')}",
            f"Duration: {dur_str}  Max Wall: {episode.get('max_wall_size', '')}",
            f"Snapshots: {episode.get('snapshot_count', 0)}  "
            f"Touches: {episode.get('touch_count', 0)}",
            "",
        ]

        # snapshot detail
        if not self._snapshots_df.empty and "episode_id" in self._snapshots_df.columns:
            snaps = self._snapshots_df[self._snapshots_df["episode_id"] == ep_id]
            lines.append(f"--- Snapshots ({len(snaps)}) ---")
            for _, snap in snaps.head(20).iterrows():
                ts = str(snap.get("timestamp", ""))[:19]
                state = snap.get("state", "")
                wall_size = snap.get("wall_size", "")
                mid = snap.get("mid_price", "")
                lines.append(f"  {ts}  state={state}  size={wall_size}  mid={mid}")
            if len(snaps) > 20:
                lines.append(f"  ... ({len(snaps) - 20} more)")
            lines.append("")

        # touch detail
        if not self._touches_df.empty and "episode_id" in self._touches_df.columns:
            touches = self._touches_df[self._touches_df["episode_id"] == ep_id]
            lines.append(f"--- Touches ({len(touches)}) ---")
            for _, touch in touches.iterrows():
                ts = str(touch.get("timestamp", ""))[:19]
                outcome = touch.get("outcome", "pending")
                mid = touch.get("mid_price", "")
                lines.append(f"  {ts}  outcome={outcome}  mid={mid}")
            lines.append("")

        self._detail.setPlainText("\n".join(lines))
