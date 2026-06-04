from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QMenuBar, QSplitter, QToolBar, QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

from depth_radar_desktop.constants import (
    APP_NAME, APP_VERSION, SYMBOL,
    WINDOW_WIDTH, WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
)
from depth_radar_desktop.theme import apply_theme, COLORS
from depth_radar_desktop.widgets.status_bar import ConnectionStatusBar


class DepthRadarMainWindow(QMainWindow):
    refresh_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION} — {SYMBOL}")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)

        # Toolbar with refresh button
        self._toolbar = QToolBar("Controls")
        self._toolbar.setMovable(False)
        self._toolbar.setStyleSheet(
            f"QToolBar {{ background: {COLORS['panel']}; border-bottom: 1px solid {COLORS['border']}; spacing: 6px; padding: 4px; }}"
        )
        self._refresh_btn = QPushButton("⟳ Refresh Connection")
        self._refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['border']}; color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; padding: 4px 12px; "
            f"font-family: Consolas; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {COLORS['blue']}; color: #fff; }}"
            f"QPushButton:pressed {{ background: {COLORS['green']}; }}"
        )
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._toolbar.addWidget(self._refresh_btn)
        self.addToolBar(self._toolbar)

        # Tab widget
        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        # Live tab (placeholder — will be replaced by LiveTab in Task 12)
        self._live_placeholder = QWidget()
        live_layout = QVBoxLayout(self._live_placeholder)
        live_label = QLabel("Live panel loading...")
        live_label.setAlignment(Qt.AlignCenter)
        live_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 18px;")
        live_layout.addWidget(live_label)
        self._tabs.addTab(self._live_placeholder, "⚡ Live")

        # Research tab (placeholder — will be replaced in Task 13/14)
        self._research_placeholder = QWidget()
        research_layout = QVBoxLayout(self._research_placeholder)
        research_label = QLabel("Research panel loading...")
        research_label.setAlignment(Qt.AlignCenter)
        research_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 18px;")
        research_layout.addWidget(research_label)
        self._tabs.addTab(self._research_placeholder, "📊 Research")

        # Status bar
        self._status_bar = ConnectionStatusBar(self)
        self.setStatusBar(self._status_bar)

        # Menu bar
        self._setup_menu_bar()

    def _setup_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        view_menu = menu_bar.addMenu("&View")
        live_action = QAction("Switch to &Live", self)
        live_action.setShortcut("Ctrl+1")
        live_action.triggered.connect(lambda: self._tabs.setCurrentIndex(0))
        view_menu.addAction(live_action)

        research_action = QAction("Switch to &Research", self)
        research_action.setShortcut("Ctrl+2")
        research_action.triggered.connect(lambda: self._tabs.setCurrentIndex(1))
        view_menu.addAction(research_action)

    @property
    def status_bar_widget(self) -> ConnectionStatusBar:
        return self._status_bar

    @property
    def tabs(self) -> QTabWidget:
        return self._tabs

    def set_live_widget(self, widget: QWidget) -> None:
        """Replace the live tab placeholder with the actual LiveTab widget."""
        idx = self._tabs.indexOf(self._live_placeholder)
        if idx >= 0:
            self._tabs.removeTab(idx)
            self._live_placeholder.deleteLater()
        self._tabs.insertTab(0, widget, "⚡ Live")
        self._tabs.setCurrentIndex(0)
        self._live_placeholder = widget

    def set_research_widget(self, widget: QWidget) -> None:
        """Replace the research tab placeholder with the actual research widget."""
        idx = self._tabs.indexOf(self._research_placeholder)
        if idx >= 0:
            self._tabs.removeTab(idx)
            self._research_placeholder.deleteLater()
        self._tabs.insertTab(1, widget, "📊 Research")
        self._research_placeholder = widget

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click — emit signal and update UI."""
        self._refresh_btn.setText("⟳ Reconnecting...")
        self._refresh_btn.setEnabled(False)
        self.refresh_requested.emit()

    def set_refresh_complete(self) -> None:
        """Called after refresh completes to restore button state."""
        self._refresh_btn.setText("⟳ Refresh Connection")
        self._refresh_btn.setEnabled(True)
