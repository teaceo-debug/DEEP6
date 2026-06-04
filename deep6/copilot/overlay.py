"""Transparent click-through overlay docked to NinjaTrader 8.

Renders AI narrative, trade calls, event countdowns, and data source
status in a sidebar panel that passes all clicks through to NT8 below.

Uses ``transparent-overlay`` (v2.7.2+) for hardware-accelerated layered
window rendering and ``win32gui`` for NT8 window tracking.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

try:
    import transparent_overlay as _tov_mod  # type: ignore[import-untyped]
except ImportError:
    _tov_mod = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from transparent_overlay import Overlay

from .config import CopilotConfig
from .types import CalendarEvent, DataSourceStatus, TradeCall

logger = logging.getLogger(__name__)

# ── Color palette ────────────────────────────────────────────────────────
# RGBA tuples — transparent-overlay uses (R, G, B, A)
_BG = (20, 20, 30, 220)
_BG_SECTION = (30, 30, 45, 200)
_BG_HEADER = (15, 15, 25, 240)
_BG_TRADE = (25, 35, 25, 230)
_BG_TRADE_SHORT = (40, 20, 20, 230)
_TEXT = (240, 240, 240, 255)
_TEXT_DIM = (160, 160, 180, 200)
_TEXT_LABEL = (130, 140, 170, 220)
_GREEN = (0, 200, 80, 255)
_RED = (220, 50, 50, 255)
_AMBER = (255, 160, 0, 255)
_CYAN = (80, 200, 240, 255)
_ACCENT = (100, 120, 200, 255)
_SEPARATOR = (60, 60, 90, 120)
_STATUS_OK = (0, 200, 80, 255)
_STATUS_ERR = (220, 50, 50, 255)
_STATUS_WARN = (255, 160, 0, 255)

# ── Layout constants ─────────────────────────────────────────────────────
_HEADER_H = 62
_TRADE_H = 100
_EVENT_ROW_H = 26
_SOURCE_ROW_H = 18
_SOURCE_SECTION_H = 44
_PAD = 10
_PAD_INNER = 6
_FONT_TITLE = 16
_FONT_BODY = 13
_FONT_SMALL = 11
_FONT_TINY = 10
_MAX_NARRATIVES = 5
_RENDER_FPS = 30


def _find_nt8_window() -> tuple[int, int, int, int] | None:
    """Locate NinjaTrader 8 main window via win32gui.

    Returns ``(x, y, width, height)`` or *None* if not found.
    Uses ``EnumWindows`` with partial title match because the NT8
    window title varies by active chart (e.g. "NinjaTrader - Chart ...").
    """
    try:
        import win32gui  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("win32gui not available — cannot locate NT8 window")
        return None

    result: list[tuple[int, int, int, int]] = []

    def _enum_cb(hwnd: int, _extra: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title: str = win32gui.GetWindowText(hwnd)
        if "NinjaTrader" in title:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w = right - left
            h = bottom - top
            if w > 200 and h > 200:
                result.append((left, top, w, h))
                return False  # stop enumeration
        return True

    win32gui.EnumWindows(_enum_cb, None)
    return result[0] if result else None


class CopilotOverlay:
    """Transparent sidebar overlay docked to NinjaTrader 8.

    The overlay renders four sections (top to bottom):
    1. **Header** — clock, connection dot, bias direction + confidence
    2. **Trade call** — active trade recommendation (hidden when idle)
    3. **Narrative** — scrolling AI commentary (last N updates)
    4. **Footer** — event countdowns + data source health

    All public ``update_*`` methods are thread-safe.  The overlay never
    steals focus from NT8 — ``transparent-overlay`` creates the window
    with ``WS_EX_TRANSPARENT | WS_EX_NOACTIVATE`` by default.

    Parameters
    ----------
    config:
        ``CopilotConfig`` instance controlling side, width, and other prefs.
    """

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self, config: CopilotConfig) -> None:
        self._config = config
        self._width = config.overlay_width
        self._side = config.overlay_side  # "left" or "right"

        # Thread-safe state (guarded by _lock)
        self._lock = threading.Lock()
        self._narrative_lines: deque[str] = deque(maxlen=_MAX_NARRATIVES)
        self._trade_call: TradeCall | None = None
        self._countdowns: list[CalendarEvent] = []
        self._source_statuses: list[DataSourceStatus] = []
        self._bias_direction: str = ""
        self._bias_confidence: float = 0.0
        self._connected: bool = False

        # NT8 window tracking
        self._nt8_rect: tuple[int, int, int, int] | None = None

        # Overlay lifecycle
        self._overlay: Overlay | None = None
        self._render_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Public lifecycle ─────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the overlay rendering thread (non-blocking)."""
        if self._render_thread is not None and self._render_thread.is_alive():
            logger.warning("Overlay already running")
            return

        self._stop_event.clear()
        self._render_thread = threading.Thread(
            target=self._render_loop,
            name="copilot-overlay",
            daemon=True,
        )
        self._render_thread.start()
        logger.info("CopilotOverlay started")

    def stop(self) -> None:
        """Gracefully shut down the overlay."""
        self._stop_event.set()
        if self._render_thread is not None:
            self._render_thread.join(timeout=3.0)
            self._render_thread = None
        if self._overlay is not None:
            try:
                self._overlay.stop_layer()
            except Exception:
                pass
            self._overlay = None
        logger.info("CopilotOverlay stopped")

    # ── Thread-safe update methods ───────────────────────────────────────

    def update_narrative(self, text: str) -> None:
        """Append a narrative line (thread-safe)."""
        with self._lock:
            self._narrative_lines.append(text)

    def update_trade_call(self, call: TradeCall | None) -> None:
        """Set or clear the active trade call (thread-safe)."""
        with self._lock:
            self._trade_call = call

    def update_countdowns(self, events: list[CalendarEvent]) -> None:
        """Replace the countdown events list (thread-safe)."""
        with self._lock:
            self._countdowns = list(events)

    def update_source_status(self, statuses: list[DataSourceStatus]) -> None:
        """Replace data-source health statuses (thread-safe)."""
        with self._lock:
            self._source_statuses = list(statuses)

    def update_bias(self, direction: str, confidence: float) -> None:
        """Set directional bias displayed in the header (thread-safe)."""
        with self._lock:
            self._bias_direction = direction
            self._bias_confidence = confidence

    def set_connected(self, connected: bool) -> None:
        """Toggle the header connection indicator (thread-safe)."""
        with self._lock:
            self._connected = connected

    # ── Internals ────────────────────────────────────────────────────────

    def _compute_overlay_rect(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) for the overlay window.

        Docks to the right (or left) edge of the NT8 window.  If NT8 is
        not found, falls back to right edge of the primary monitor.
        """
        nt8 = _find_nt8_window()
        self._nt8_rect = nt8
        w = self._width

        if nt8 is not None:
            nx, ny, nw, nh = nt8
            if self._side == "left":
                return (nx, ny, w, nh)
            return (nx + nw - w, ny, w, nh)

        # Fallback — right edge of primary monitor
        try:
            import win32api  # type: ignore[import-untyped]

            sw = win32api.GetSystemMetrics(0)
            sh = win32api.GetSystemMetrics(1)
        except ImportError:
            sw, sh = 1920, 1080
        return (sw - w, 0, w, sh)

    def _reposition(self) -> bool:
        """Check if NT8 moved and reposition the overlay.

        Returns *True* if the overlay was repositioned (requires restart).
        """
        prev = self._nt8_rect
        new_rect = self._compute_overlay_rect()
        if prev is None or self._nt8_rect != prev:
            return True
        ox, oy, ow, oh = new_rect
        if self._overlay is not None:
            # transparent-overlay does not support live repositioning;
            # we signal the render loop to tear down and recreate.
            return True
        return False

    def _create_overlay(self) -> "Overlay":
        """Instantiate and start a ``transparent_overlay.Overlay``."""
        if _tov_mod is None:
            raise ImportError("transparent-overlay is not installed")

        from transparent_overlay import Overlay as _Overlay

        ox, oy, ow, oh = self._compute_overlay_rect()
        ov = _Overlay(x=ox, y=oy, width=ow, height=oh)
        ov.sprite_ttl_seconds = 60.0
        ov.enable_auto_ttl_cleanup = True
        ov.start_layer()
        return ov

    # ── Render loop ──────────────────────────────────────────────────────

    def _render_loop(self) -> None:
        """Main render loop — runs on the daemon thread at ~30 fps."""
        if _tov_mod is None:
            logger.warning(
                "overlay.tov_unavailable reason=transparent_overlay_not_installed"
            )
            self._run_fallback_loop()
            return

        interval = 1.0 / _RENDER_FPS
        reposition_check_interval = 2.0
        last_reposition_check = 0.0

        try:
            self._overlay = self._create_overlay()
        except Exception:
            logger.exception("Failed to create overlay")
            return

        while not self._stop_event.is_set():
            frame_start = time.monotonic()

            # Periodic NT8 reposition check
            if frame_start - last_reposition_check > reposition_check_interval:
                last_reposition_check = frame_start
                if self._reposition():
                    try:
                        self._overlay.stop_layer()
                    except Exception:
                        pass
                    try:
                        self._overlay = self._create_overlay()
                    except Exception:
                        logger.exception("Failed to recreate overlay")
                        break

            # Snapshot state under lock
            with self._lock:
                narratives = list(self._narrative_lines)
                trade = self._trade_call
                countdowns = list(self._countdowns)
                sources = list(self._source_statuses)
                bias_dir = self._bias_direction
                bias_conf = self._bias_confidence
                connected = self._connected

            # Draw frame
            ov = self._overlay
            if ov is None:
                break

            try:
                ov.frame_clear()
                self._draw_frame(
                    ov, narratives, trade, countdowns, sources,
                    bias_dir, bias_conf, connected,
                )
                ov.signal_render()
            except Exception:
                logger.exception("Render error")

            # FPS throttle
            elapsed = time.monotonic() - frame_start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Cleanup
        if self._overlay is not None:
            try:
                self._overlay.stop_layer()
            except Exception:
                pass
            self._overlay = None

    def _run_fallback_loop(self) -> None:
        """Fallback: log updates when transparent-overlay is unavailable."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=1.0)
            with self._lock:
                n = len(self._narrative_lines)
            if n:
                logger.debug("overlay.fallback_update narrative_count=%d", n)

    # ── Drawing helpers ──────────────────────────────────────────────────

    def _draw_frame(
        self,
        ov: "Overlay",
        narratives: list[str],
        trade: TradeCall | None,
        countdowns: list[CalendarEvent],
        sources: list[DataSourceStatus],
        bias_dir: str,
        bias_conf: float,
        connected: bool,
    ) -> None:
        """Composite all sections into a single frame."""
        w = self._width
        _, _, _, h = self._compute_overlay_rect()

        # Full background
        ov.draw_rect(0, 0, w, h, _BG)

        cursor_y = 0

        # Section 1: Header
        cursor_y = self._draw_header(ov, w, cursor_y, bias_dir, bias_conf, connected)

        # Separator
        cursor_y = self._draw_separator(ov, w, cursor_y)

        # Section 2: Trade call (conditional)
        if trade is not None and trade.direction:
            cursor_y = self._draw_trade_call(ov, w, cursor_y, trade)
            cursor_y = self._draw_separator(ov, w, cursor_y)

        # Section 3: Narrative (fills remaining space minus footer)
        footer_h = self._estimate_footer_height(countdowns, sources)
        narrative_h = max(80, h - cursor_y - footer_h - 4)
        cursor_y = self._draw_narrative(ov, w, cursor_y, narrative_h, narratives)

        # Separator
        cursor_y = self._draw_separator(ov, w, cursor_y)

        # Section 4: Countdowns
        if countdowns:
            cursor_y = self._draw_countdowns(ov, w, cursor_y, countdowns)

        # Section 5: Source status
        if sources:
            self._draw_source_status(ov, w, cursor_y, sources)

    # ── Section renderers ────────────────────────────────────────────────

    def _draw_header(
        self,
        ov: "Overlay",
        w: int,
        y: int,
        bias_dir: str,
        bias_conf: float,
        connected: bool,
    ) -> int:
        """Header: title + clock + connection dot + bias."""
        ov.draw_rect(0, y, w, _HEADER_H, _BG_HEADER)

        now_str = datetime.now(tz=timezone.utc).strftime("%H:%M:%S")
        title = f"AI COPILOT | {now_str}"
        ov.draw_text(_PAD, y + _PAD, title, color=_TEXT, font_size=_FONT_TITLE)

        # Connection status dot (small filled circle)
        dot_color = _STATUS_OK if connected else _STATUS_ERR
        dot_x = w - _PAD - 10
        dot_y = y + _PAD + 4
        ov.draw_circle(dot_x, dot_y, 5, dot_color)

        # Bias line
        if bias_dir:
            bias_color = _GREEN if bias_dir.upper() == "BULLISH" else _RED
            bias_text = f"Bias: {bias_dir.upper()} {bias_conf:.0f}%"
            ov.draw_text(
                _PAD, y + _PAD + 24, bias_text,
                color=bias_color, font_size=_FONT_BODY,
            )
        else:
            ov.draw_text(
                _PAD, y + _PAD + 24,
                "Waiting for NinjaTrader...",
                color=_TEXT_DIM, font_size=_FONT_BODY,
            )

        return y + _HEADER_H

    def _draw_trade_call(
        self,
        ov: "Overlay",
        w: int,
        y: int,
        trade: TradeCall,
    ) -> int:
        """Trade call section — direction, levels, confidence."""
        bg = _BG_TRADE if trade.direction.upper() == "LONG" else _BG_TRADE_SHORT
        ov.draw_rect(0, y, w, _TRADE_H, bg)

        dir_color = _GREEN if trade.direction.upper() == "LONG" else _RED

        # Row 1: Title
        ov.draw_rect(_PAD, y + _PAD_INNER, 4, 14, dir_color)
        ov.draw_text(
            _PAD + 10, y + _PAD_INNER, "TRADE CALL",
            color=dir_color, font_size=_FONT_BODY,
        )

        # Row 2: Direction + entry
        entry_text = f"{trade.direction.upper()} @ {trade.entry:,.0f}"
        ov.draw_text(
            _PAD, y + _PAD_INNER + 22, entry_text,
            color=_TEXT, font_size=_FONT_BODY,
        )

        # Row 3: Stop / target
        levels_text = f"Stop: {trade.stop:,.0f}  |  Target: {trade.target:,.0f}"
        ov.draw_text(
            _PAD, y + _PAD_INNER + 40, levels_text,
            color=_TEXT_DIM, font_size=_FONT_SMALL,
        )

        # Row 4: Confidence + MAD levels
        mad_str = ""
        if trade.mad_levels:
            mad_str = f" | {trade.mad_levels[0].label}" if trade.mad_levels[0].label else ""
        conf_text = f"Confidence: {trade.confidence:.0f}%{mad_str}"
        ov.draw_text(
            _PAD, y + _PAD_INNER + 58, conf_text,
            color=_CYAN, font_size=_FONT_SMALL,
        )

        # Row 5: Rationale (truncated)
        if trade.rationale:
            rat = trade.rationale[:60] + ("..." if len(trade.rationale) > 60 else "")
            ov.draw_text(
                _PAD, y + _PAD_INNER + 76, rat,
                color=_TEXT_DIM, font_size=_FONT_TINY,
            )

        return y + _TRADE_H

    def _draw_narrative(
        self,
        ov: "Overlay",
        w: int,
        y: int,
        max_h: int,
        narratives: list[str],
    ) -> int:
        """Scrolling narrative section — last N commentary lines."""
        ov.draw_rect(0, y, w, max_h, _BG_SECTION)

        # Section label
        ov.draw_text(
            _PAD, y + _PAD_INNER, "NARRATIVE",
            color=_TEXT_LABEL, font_size=_FONT_TINY,
        )

        if not narratives:
            ov.draw_text(
                _PAD, y + _PAD_INNER + 18,
                "No narrative updates yet...",
                color=_TEXT_DIM, font_size=_FONT_SMALL,
            )
            return y + max_h

        text_y = y + _PAD_INNER + 18
        avail_w = w - 2 * _PAD
        line_height = 16

        for entry in narratives:
            if text_y + line_height > y + max_h - _PAD_INNER:
                break
            # Wrap long lines manually
            lines = self._wrap_text(entry, approx_char_width=7, max_width=avail_w)
            for line in lines:
                if text_y + line_height > y + max_h - _PAD_INNER:
                    break
                ov.draw_text(
                    _PAD, text_y, line,
                    color=_TEXT, font_size=_FONT_SMALL,
                )
                text_y += line_height

            # Small gap between entries
            text_y += 4

        return y + max_h

    def _draw_countdowns(
        self,
        ov: "Overlay",
        w: int,
        y: int,
        countdowns: list[CalendarEvent],
    ) -> int:
        """Event countdown rows — name + time remaining."""
        # Only show events within ~2 hours
        now_ts = time.time()
        upcoming: list[CalendarEvent] = []
        for evt in countdowns:
            try:
                evt_ts = self._parse_event_time(evt.time)
                if evt_ts is not None and 0 < (evt_ts - now_ts) < 7200:
                    upcoming.append(evt)
            except Exception:
                continue

        if not upcoming:
            return y

        for evt in upcoming[:3]:
            evt_ts = self._parse_event_time(evt.time)
            if evt_ts is None:
                continue
            mins_left = int((evt_ts - now_ts) / 60)

            impact_color = _RED if evt.impact == "high" else _AMBER if evt.impact == "medium" else _TEXT_DIM

            # Impact indicator rectangle
            ov.draw_rect(_PAD, y + 6, 4, 14, impact_color)

            row_text = f"{evt.name}  {mins_left} min"
            ov.draw_text(
                _PAD + 10, y + _PAD_INNER, row_text,
                color=_TEXT, font_size=_FONT_SMALL,
            )
            y += _EVENT_ROW_H

        return y

    def _draw_source_status(
        self,
        ov: "Overlay",
        w: int,
        y: int,
        sources: list[DataSourceStatus],
    ) -> None:
        """Data source health bar — count + stale warnings."""
        ov.draw_rect(0, y, w, _SOURCE_SECTION_H, _BG_SECTION)

        ok_count = sum(1 for s in sources if not s.is_stale and s.error is None)
        total = len(sources)

        summary_color = _GREEN if ok_count == total else _AMBER
        summary = f"Sources: {ok_count}/{total}"
        ov.draw_text(
            _PAD, y + _PAD_INNER, summary,
            color=summary_color, font_size=_FONT_SMALL,
        )

        # Status dot
        dot_color = _STATUS_OK if ok_count == total else _STATUS_WARN
        ov.draw_circle(_PAD + 110, y + _PAD_INNER + 5, 4, dot_color)

        # Show first stale/error source as warning
        stale = [s for s in sources if s.is_stale or s.error is not None]
        if stale:
            warn_src = stale[0]
            reason = warn_src.error if warn_src.error else "stale"
            warn_text = f"{warn_src.source_name}: {reason}"
            ov.draw_text(
                _PAD, y + _PAD_INNER + 18, warn_text,
                color=_STATUS_WARN, font_size=_FONT_TINY,
            )

    def _draw_separator(self, ov: "Overlay", w: int, y: int) -> int:
        """Thin horizontal separator line."""
        ov.draw_line(_PAD, y, w - _PAD, y, _SEPARATOR, thickness=1)
        return y + 2

    # ── Utilities ────────────────────────────────────────────────────────

    @staticmethod
    def _wrap_text(text: str, approx_char_width: int, max_width: int) -> list[str]:
        """Rough word-wrap for overlay text rendering."""
        max_chars = max(10, max_width // approx_char_width)
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}" if current else word

        if current:
            lines.append(current)

        return lines or [""]

    @staticmethod
    def _parse_event_time(time_str: str) -> float | None:
        """Best-effort parse of a CalendarEvent.time string to epoch."""
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%H:%M:%S", "%H:%M"):
            try:
                dt = datetime.strptime(time_str, fmt)
                # For time-only formats, assume today
                if dt.year == 1900:
                    now = datetime.now(tz=timezone.utc)
                    dt = dt.replace(year=now.year, month=now.month, day=now.day)
                return dt.timestamp()
            except ValueError:
                continue
        return None

    def _estimate_footer_height(
        self,
        countdowns: list[CalendarEvent],
        sources: list[DataSourceStatus],
    ) -> int:
        """Estimate pixel height needed for countdown + source sections."""
        h = 0
        # Countdowns: up to 3 visible rows
        if countdowns:
            visible = min(len(countdowns), 3)
            h += visible * _EVENT_ROW_H
        # Sources always take fixed height when present
        if sources:
            h += _SOURCE_SECTION_H
        return h + 4  # separator padding
