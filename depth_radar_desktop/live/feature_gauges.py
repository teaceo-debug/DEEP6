"""Feature gauge meters for real-time wall monitoring.

Four diagnostic arc gauges: Absorption, Delta, Approach, Walls Near.
Pure QPainter rendering — no external charting libraries.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QWidget

from depth_radar_desktop.constants import TICK_SIZE
from depth_radar_desktop.theme import COLORS

# ---------------------------------------------------------------------------
# Arc geometry
# ---------------------------------------------------------------------------
_ARC_STROKE_PX = 8
_ARC_START_DEG = 180  # left of semicircle
_ARC_SPAN_DEG = 180  # full semicircle


class GaugeWidget(QWidget):
    """Single arc-style gauge meter."""

    def __init__(
        self,
        label: str,
        min_val: float = 0.0,
        max_val: float = 1.0,
        thresholds: tuple[float, float] = (0.3, 0.6),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._value = 0.0
        self._min = min_val
        self._max = max_val
        self._low_threshold, self._high_threshold = thresholds
        self.setMinimumSize(120, 100)
        self.setMaximumHeight(140)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: float) -> None:
        """Clamp *value* to [min, max] and repaint."""
        self._value = max(self._min, min(value, self._max))
        self.update()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # The arc lives in the upper half; text in the lower half.
        arc_rect = QRectF(10, 10, w - 20, (h - 40) * 2)

        # --- background arc ---
        bg_pen = QPen(
            QColor(COLORS["border"]),
            _ARC_STROKE_PX,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(bg_pen)
        painter.drawArc(arc_rect, 0 * 16, _ARC_SPAN_DEG * 16)

        # --- value arc (sweeps clockwise from left) ---
        range_span = max(self._max - self._min, 1e-9)
        normalized = (self._value - self._min) / range_span
        sweep = int(normalized * _ARC_SPAN_DEG * 16)

        fill_pen = QPen(
            QColor(self._threshold_color(normalized)),
            _ARC_STROKE_PX,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
        painter.setPen(fill_pen)
        painter.drawArc(arc_rect, _ARC_START_DEG * 16, -sweep)

        # --- value text ---
        painter.setPen(QColor(COLORS["text_primary"]))
        value_font = QFont("Consolas", 14)
        value_font.setBold(True)
        painter.setFont(value_font)

        value_text = (
            f"{self._value:.1f}" if self._max > 10 else f"{self._value:.2f}"
        )
        painter.drawText(
            QRectF(0, h / 2 - 15, w, 25),
            Qt.AlignmentFlag.AlignCenter,
            value_text,
        )

        # --- label text ---
        label_font = QFont("Segoe UI", 9)
        label_font.setBold(False)
        painter.setFont(label_font)
        painter.setPen(QColor(COLORS["text_secondary"]))
        painter.drawText(
            QRectF(0, h - 25, w, 20),
            Qt.AlignmentFlag.AlignCenter,
            self._label,
        )

        painter.end()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _threshold_color(self, normalized: float) -> str:
        """Return a theme color string based on where *normalized* sits."""
        range_span = max(self._max - self._min, 1e-9)
        low_norm = (self._low_threshold - self._min) / range_span
        high_norm = (self._high_threshold - self._min) / range_span
        if normalized < low_norm:
            return COLORS["green"]
        if normalized < high_norm:
            return COLORS["amber"]
        return COLORS["red"]


# ---------------------------------------------------------------------------
# Panel containing all four gauges
# ---------------------------------------------------------------------------


class FeatureGaugesPanel(QWidget):
    """Horizontal row of four diagnostic gauges."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._absorption = GaugeWidget("Absorption", 0.0, 1.0, (0.3, 0.6))
        self._delta = GaugeWidget("Delta", 0.0, 200.0, (50.0, 100.0))
        self._approach = GaugeWidget("Approach", 0.0, 5.0, (1.0, 2.0))
        self._walls_near = GaugeWidget("Walls Near", 0.0, 10.0, (2.0, 5.0))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        for gauge in self._all_gauges():
            layout.addWidget(gauge)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_gauges(self, walls: list[dict], mid_price: float = 0.0) -> None:
        """Recompute gauge values from *walls*; zero out on empty list."""
        if not walls:
            for gauge in self._all_gauges():
                gauge.set_value(0.0)
            return

        # Absorption: average absorption_ratio
        ratios = [float(w.get("absorption_ratio", 0)) for w in walls]
        self._absorption.set_value(sum(ratios) / len(ratios) if ratios else 0)

        # Delta: average |delta_2s|
        deltas = [abs(float(w.get("delta_2s", 0))) for w in walls]
        self._delta.set_value(sum(deltas) / len(deltas) if deltas else 0)

        # Approach: max approach_speed
        speeds = [float(w.get("approach_speed", 0)) for w in walls]
        self._approach.set_value(max(speeds) if speeds else 0)

        # Walls Near: count within 20 ticks of mid_price
        near_count = (
            sum(
                1
                for w in walls
                if abs(float(w.get("price", 0)) - mid_price) <= 20 * TICK_SIZE
            )
            if mid_price > 0
            else 0
        )
        self._walls_near.set_value(float(near_count))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _all_gauges(self) -> list[GaugeWidget]:
        return [self._absorption, self._delta, self._approach, self._walls_near]
