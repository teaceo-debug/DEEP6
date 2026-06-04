"""Screenshot capture pipeline for NinjaTrader 8 chart window."""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Callable

try:
    import mss
except ImportError:  # pragma: no cover - optional dependency in this env
    mss = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional dependency in this env
    Image = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ScreenCapture:
    def __init__(self, config):
        self._config = config
        self._sct = mss.mss() if mss is not None else None
        self._task: asyncio.Task | None = None
        self._last_capture: bytes | None = None

    def find_nt8_window(self) -> tuple[int, int, int, int] | None:
        """Find NinjaTrader 8 window by title. Returns (left, top, width, height) or None."""
        import sys

        if sys.platform != "win32":
            logger.warning("ScreenCapture.find_nt8_window: Windows only (not running on win32)")
            return None

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        result = []

        def callback(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                # NT8 chart windows: "Chart - NQ 06-26", "Chart - MNQ 06-26"
                # NT8 main window:   "Control Center", "NinjaTrader"
                is_nt8 = (
                    "NinjaTrader" in title
                    or title.startswith("Chart - ")
                    or "Control Center" in title
                )
                if is_nt8 and user32.IsWindowVisible(hwnd):
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    # Prefer chart windows (wider than 400px, taller than 300px)
                    if w > 100 and h > 100:
                        result.append((rect.left, rect.top, w, h, title))
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(callback), 0)

        if not result:
            logger.warning("NinjaTrader 8 window not found")
            return None
        # Prefer chart windows, then the largest by area
        chart_windows = [r for r in result if r[4].startswith("Chart -")]
        candidates = chart_windows or result
        # Sort: NQ futures charts first (not MNQ), then by area descending
        def _sort_key(r):
            title = r[4]
            is_nq = "NQ" in title and "MNQ" not in title
            area = r[2] * r[3]
            return (0 if is_nq else 1, -area)
        best = sorted(candidates, key=_sort_key)[0]
        logger.info("NT8 window found: %s (%dx%d at %d,%d)", best[4], best[2], best[3], best[0], best[1])
        return (best[0], best[1], best[2], best[3])

    def capture(self) -> bytes | None:
        """Capture NT8 window as PNG bytes."""
        bounds = self.find_nt8_window()
        if bounds is None:
            return self._last_capture

        left, top, width, height = bounds
        if width <= 0 or height <= 0:
            logger.warning("NT8 window minimized, skipping capture")
            return self._last_capture

        if self._sct is None or Image is None:
            logger.warning("Screenshot dependencies unavailable, returning cached capture")
            return self._last_capture

        monitor = {"left": left, "top": top, "width": width, "height": height}
        raw = self._sct.grab(monitor)

        img = Image.frombytes("RGB", (raw.width, raw.height), raw.rgb)
        if img.width > 1920:
            ratio = 1920 / img.width
            img = img.resize((1920, int(img.height * ratio)), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        self._last_capture = buf.getvalue()
        return self._last_capture

    def capture_as_base64(self) -> str | None:
        """Capture NT8 window as base64-encoded PNG string."""
        data = self.capture()
        if data is None:
            return None
        return base64.b64encode(data).decode("ascii")

    async def start_periodic(self, interval_sec: int, callback: Callable) -> None:
        """Start periodic capture loop."""

        async def _loop():
            while True:
                try:
                    data = self.capture()
                    if data is not None:
                        await callback(data)
                except Exception:
                    logger.exception("Screenshot capture error")
                await asyncio.sleep(interval_sec)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._sct is not None:
            self._sct.close()
