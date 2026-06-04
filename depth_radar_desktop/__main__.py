from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime


def _hide_console():
    """Hide the console window on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="depth-radar-desktop")
    parser.add_argument("--dry-run", action="store_true", help="Validate startup without launching the GUI")
    parser.add_argument("--source", default="rithmic", choices=["rithmic", "replay", "none"], help="Data source: rithmic (live), replay (MBO file), none (disconnected)")
    parser.add_argument("--show-console", action="store_true", help="Keep the console window visible (debug mode)")
    return parser


def _create_app_icon():
    """Generate a distinctive Depth Radar icon — cyan radar sweep on dark bg with 'DR' monogram."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QColor, QConicalGradient, QFont, QIcon, QPainter, QPen, QPixmap, QRadialGradient,
    )

    sizes = [16, 32, 48, 64, 128, 256]
    icon = QIcon()
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = size / 2.0
        radius = size / 2.0 - max(1, size // 16)

        # Dark circle background with subtle gradient
        bg_gradient = QRadialGradient(center, center, radius)
        bg_gradient.setColorAt(0.0, QColor("#1a2332"))
        bg_gradient.setColorAt(1.0, QColor("#0d1117"))
        painter.setBrush(bg_gradient)
        painter.setPen(QPen(QColor("#00d4aa"), max(1, size // 32)))
        painter.drawEllipse(QRectF(size / 2 - radius, size / 2 - radius, radius * 2, radius * 2))

        # Radar rings (concentric circles, subtle)
        ring_pen = QPen(QColor(0, 212, 170, 40), max(1, size // 64))
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        for r_frac in [0.3, 0.55, 0.8]:
            r = radius * r_frac
            painter.drawEllipse(QRectF(center - r, center - r, r * 2, r * 2))

        # Radar sweep (conical gradient wedge) — signature cyan/teal
        sweep_pen = QPen(QColor("#00d4aa"), max(2, size // 16))
        painter.setPen(sweep_pen)
        sweep_rect = QRectF(center - radius * 0.85, center - radius * 0.85, radius * 1.7, radius * 1.7)
        painter.drawArc(sweep_rect, 30 * 16, 60 * 16)

        # Second sweep at different angle (gives depth feel)
        sweep_pen2 = QPen(QColor(0, 212, 170, 100), max(1, size // 24))
        painter.setPen(sweep_pen2)
        painter.drawArc(sweep_rect, 200 * 16, 40 * 16)

        # "DR" monogram in center (only for sizes >= 32)
        if size >= 32:
            font_size = max(8, int(size * 0.28))
            font = QFont("Consolas", font_size, QFont.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            text_rect = QRectF(0, size * 0.05, size, size)
            painter.drawText(text_rect, Qt.AlignCenter, "DR")

        # Bright dot at sweep tip (signature element)
        dot_size = max(2, size // 10)
        import math
        tip_angle = math.radians(60)
        tip_x = center + radius * 0.75 * math.cos(tip_angle)
        tip_y = center - radius * 0.75 * math.sin(tip_angle)
        painter.setBrush(QColor("#00ffcc"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(tip_x, tip_y), dot_size / 2, dot_size / 2)

        painter.end()
        icon.addPixmap(pixmap)
    return icon


def main() -> int:
    args = _build_parser().parse_args()

    if args.dry_run:
        print("Depth Radar Desktop v0.1.0 -- Dry-run OK")
        return 0

    if not getattr(args, "show_console", False):
        _hide_console()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - environment dependent
        print("PySide6 is required. Install with: pip install PySide6", file=sys.stderr)
        raise SystemExit(1) from exc

    from depth_radar_desktop.main_window import DepthRadarMainWindow
    from depth_radar_desktop.config import load_config
    from depth_radar_desktop.live.engine_worker import EngineWorker
    from depth_radar_desktop.live.live_tab import LiveTab
    from depth_radar_desktop.research.research_tab import ResearchTab
    from depth_radar_desktop.theme import apply_theme

    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(_create_app_icon())

    # Global exception handler — keeps app alive on unhandled errors
    def _global_exception_handler(exc_type, exc_value, exc_tb):
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(f"[unhandled exception]\n{error_msg}", file=sys.stderr)

    sys.excepthook = _global_exception_handler

    config = load_config()
    config.source = args.source

    window = DepthRadarMainWindow()

    # --- Engine + Live tab (graceful if engine fails) ---
    worker = None
    try:
        worker = EngineWorker(config)
    except Exception as exc:
        print(f"[engine error] Failed to create engine: {exc}", file=sys.stderr)

    if worker is not None:
        live_tab = LiveTab(worker.bridge)
        window.set_live_widget(live_tab)

        worker.bridge.connection_changed.connect(window.status_bar_widget.set_connected)
        worker.bridge.engine_stats.connect(
            lambda stats: window.status_bar_widget.update_stats(
                stats.get("active_walls", 0),
                datetime.now().strftime("%H:%M:%S.")
                + f"{datetime.now().microsecond // 1000:03d}",
            )
        )
        worker.bridge.error_occurred.connect(
            lambda msg: print(f"[engine error] {msg}", file=sys.stderr)
        )

        # --- Refresh button wiring ---
        def _do_refresh():
            window.status_bar_widget.set_connected(False)
            worker.stop()
            try:
                worker._bridge = worker._bridge.__class__(
                    source=config.source,
                    rithmic_user=config.rithmic_user,
                    rithmic_password=config.rithmic_password,
                    rithmic_system_name=config.rithmic_system_name,
                    rithmic_url=config.rithmic_url,
                    rithmic_symbol=config.rithmic_symbol,
                    rithmic_exchange=config.rithmic_exchange,
                    replay_file=config.replay_file or None,
                    min_wall_size=config.min_wall_size,
                    rth_only=config.rth_only,
                    intent_model_path=str(config.intent_model_path),
                    interaction_model_path=str(config.interaction_model_path),
                    output_path=config.nt8_output_path,
                )
                worker.bridge.connection_changed.connect(window.status_bar_widget.set_connected)
                worker.bridge.engine_stats.connect(
                    lambda stats: window.status_bar_widget.update_stats(
                        stats.get("active_walls", 0),
                        datetime.now().strftime("%H:%M:%S.")
                        + f"{datetime.now().microsecond // 1000:03d}",
                    )
                )
                live_tab.set_bridge(worker.bridge)
                worker.start()
            except Exception as exc:
                print(f"[refresh error] {exc}", file=sys.stderr)
            window.set_refresh_complete()

        window.refresh_requested.connect(_do_refresh)
        worker.start()

    # --- Model status (always shown) ---
    window.status_bar_widget.set_model_status(
        intent_loaded=config.intent_model_path.exists(),
        interaction_loaded=config.interaction_model_path.exists(),
    )

    # --- Research tab ---
    research_tab = ResearchTab()
    research_tab.load_data(
        config.training_output_dir,
        config.intent_model_path,
        config.interaction_model_path,
    )
    window.set_research_widget(research_tab)

    window.show()

    try:
        return app.exec()
    finally:
        if worker is not None:
            worker.stop()


if __name__ == "__main__":
    sys.exit(main())
