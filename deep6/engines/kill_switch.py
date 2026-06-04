"""KillSwitch — GO/CAUTION/STOP entry permission system for bias v3.

Evaluates market conditions (time, VIX, domain availability, event calendar)
to determine whether trade entry is permitted.

Rules evaluated in priority order (first match wins):
1. STOP:    lunch window (default 12:00-13:00 CT)
2. STOP:    past cutoff (default after 15:00 CT)
3. STOP:    VIX >= vix_crisis_threshold (default 35.0)
4. CAUTION: VIX >= vix_elevated_threshold (default 25.0)
5. CAUTION: VIX unavailable (None → treat as elevated for safety)
6. STOP:    fewer than min_domains_for_go domains available
7. STOP:    event_day flag set and event_day_mode == "STOP"
8. GO:      all clear
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from deep6.engines.signal_config import KillSwitchConfig

CT = ZoneInfo("America/Chicago")


class KillSwitch:
    """Evaluates whether market conditions permit trade entry.

    Outputs GO / CAUTION / STOP with a human-readable reason.
    """

    def __init__(self, config: Optional[KillSwitchConfig] = None) -> None:
        self._config = config or KillSwitchConfig()
        self._event_day: bool = False

    def evaluate(
        self,
        bias_score: int,
        vix: Optional[float],
        domains_available: int,
        now: Optional[datetime] = None,
    ) -> tuple[str, str]:
        """Return (mode, reason) where mode is 'GO' | 'CAUTION' | 'STOP'.

        ``now`` defaults to current CT time if None.
        """
        cfg = self._config

        if now is None:
            now = datetime.now(CT)
        else:
            now = now.astimezone(CT)

        ct_hour = now.hour

        # 1. Lunch window → STOP
        if cfg.lunch_start_hour <= ct_hour < cfg.lunch_end_hour:
            return ("STOP", "Lunch window")

        # 2. Past cutoff → STOP
        if ct_hour >= cfg.cutoff_hour:
            return ("STOP", "After cutoff")

        # 3. VIX crisis → STOP
        if vix is not None and vix >= cfg.vix_crisis_threshold:
            return ("STOP", f"VIX crisis ({vix:.1f})")

        # 4. VIX elevated → CAUTION
        if vix is not None and vix >= cfg.vix_elevated_threshold:
            return ("CAUTION", f"VIX elevated ({vix:.1f})")

        # 5. VIX unavailable → CAUTION (safety fallback)
        if vix is None:
            return ("CAUTION", "VIX unavailable")

        # 6. Insufficient domains → STOP
        if domains_available < cfg.min_domains_for_go:
            return ("STOP", f"Insufficient domains ({domains_available}/{cfg.min_domains_for_go})")

        # 7. Event day → STOP (when configured)
        if self._event_day and cfg.event_day_mode == "STOP":
            return ("STOP", "Event day")

        # 8. All clear → GO
        return ("GO", "All clear")

    def set_event_day(self, is_event_day: bool) -> None:
        """Called by external calendar adapter when a major macro event is scheduled."""
        self._event_day = is_event_day
