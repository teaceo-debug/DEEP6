from __future__ import annotations

COLORS: dict[str, str] = {
    "background": "#0d1117",
    "panel": "#161b22",
    "border": "#30363d",
    "text_primary": "#e6edf3",
    "text_secondary": "#8b949e",
    "green": "#3fb950",
    "red": "#f85149",
    "amber": "#d29922",
    "blue": "#58a6ff",
}

FONTS: dict[str, str] = {
    "monospace": "Consolas, Menlo, 'Courier New', monospace",
    "sans_serif": "'Segoe UI', 'SF Pro Display', system-ui, sans-serif",
}

STYLESHEET: str = f"""
QMainWindow {{
    background-color: {COLORS['background']};
    color: {COLORS['text_primary']};
    font-family: {FONTS['sans_serif']};
}}

QTabWidget::pane {{
    border: none;
    background-color: {COLORS['background']};
}}

QTabBar::tab {{
    background: {COLORS['panel']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
    border-bottom: none;
    padding: 8px 14px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    color: {COLORS['text_primary']};
    border-bottom: 2px solid {COLORS['blue']};
}}

QTableView {{
    background-color: {COLORS['background']};
    alternate-background-color: {COLORS['panel']};
    color: {COLORS['text_primary']};
    gridline-color: {COLORS['border']};
    selection-background-color: {COLORS['blue']};
    selection-color: {COLORS['text_primary']};
    font-family: {FONTS['monospace']};
}}

QHeaderView::section {{
    background-color: {COLORS['panel']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    padding: 6px 8px;
    font-weight: 600;
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background: {COLORS['background']};
    border: none;
    width: 10px;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    border: none;
}}

QLabel {{
    color: {COLORS['text_primary']};
    background: transparent;
}}

QPushButton {{
    background-color: {COLORS['panel']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 6px 12px;
}}

QPushButton:hover {{
    border-color: {COLORS['blue']};
}}

QPushButton:pressed {{
    background-color: {COLORS['border']};
}}

QStatusBar {{
    background-color: {COLORS['panel']};
    color: {COLORS['text_secondary']};
    border-top: 1px solid {COLORS['border']};
}}

QMenuBar {{
    background-color: {COLORS['background']};
    color: {COLORS['text_primary']};
}}

QMenuBar::item:selected {{
    background: {COLORS['panel']};
}}

QMenu {{
    background-color: {COLORS['panel']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
}}

QMenu::item:selected {{
    background-color: {COLORS['blue']};
}}
""".strip()


def apply_theme(app) -> None:
    app.setStyleSheet(STYLESHEET)
