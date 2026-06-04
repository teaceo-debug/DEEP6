from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSplitter, QVBoxLayout, QWidget

from depth_radar_desktop.config import PROJECT_ROOT
from depth_radar_desktop.research.episode_browser import EpisodeBrowser
from depth_radar_desktop.research.model_dashboard import ModelDashboard


class ResearchTab(QWidget):
    """Research tab assembling episode browser and model dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._episode_browser = EpisodeBrowser(self)
        self._model_dashboard = ModelDashboard(self)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._episode_browser)
        splitter.addWidget(self._model_dashboard)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def load_data(
        self,
        training_dir: Path,
        intent_model_path: Path,
        interaction_model_path: Path,
    ) -> None:
        """Load episode data and model metrics with graceful fallback."""
        dirs_to_try = [
            training_dir / "depth_radar_v4_3day",
            training_dir / "depth_radar_v4",
            training_dir,
            PROJECT_ROOT / "data" / "depth_radar_v4",
            PROJECT_ROOT / "data" / "depth_radar_v4_full",
        ]

        for directory in dirs_to_try:
            if directory.exists() and (directory / "episodes.parquet").exists():
                self._episode_browser.load_data(directory)
                break

        if intent_model_path.exists():
            self._model_dashboard.load_model_metrics(intent_model_path)
        elif interaction_model_path.exists():
            self._model_dashboard.load_model_metrics(interaction_model_path)
