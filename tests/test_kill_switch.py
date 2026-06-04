"""Tests for KillSwitch — GO/CAUTION/STOP entry permission system."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from deep6.engines.kill_switch import CT, KillSwitch
from deep6.engines.signal_config import KillSwitchConfig

CT_TZ = ZoneInfo("America/Chicago")


def _ct(hour: int, minute: int = 0) -> datetime:
    """Helper: build a CT datetime for testing."""
    return datetime(2026, 5, 12, hour, minute, tzinfo=CT_TZ)


@pytest.fixture
def ks() -> KillSwitch:
    return KillSwitch()


# --- 1. Lunch window STOP ---

class TestLunchWindow:
    def test_stop_during_lunch_start(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(12, 0))
        assert mode == "STOP"
        assert "Lunch" in reason

    def test_stop_during_lunch_mid(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(12, 30))
        assert mode == "STOP"

    def test_not_lunch_at_boundary(self, ks: KillSwitch) -> None:
        """13:00 CT is NOT lunch (end is exclusive)."""
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(13, 0))
        assert mode != "STOP" or "Lunch" not in _


# --- 2. Cutoff STOP ---

class TestCutoff:
    def test_stop_after_cutoff(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(15, 0))
        assert mode == "STOP"
        assert "cutoff" in reason.lower()

    def test_stop_late_evening(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(16, 30))
        assert mode == "STOP"


# --- 3. VIX crisis STOP ---

class TestVIXCrisis:
    def test_stop_vix_crisis(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=35.0, domains_available=3, now=_ct(10, 0))
        assert mode == "STOP"
        assert "VIX crisis" in reason
        assert "35.0" in reason

    def test_stop_vix_way_above_crisis(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=80.0, domains_available=3, now=_ct(10, 0))
        assert mode == "STOP"


# --- 4. VIX elevated CAUTION ---

class TestVIXElevated:
    def test_caution_vix_elevated(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=25.0, domains_available=3, now=_ct(10, 0))
        assert mode == "CAUTION"
        assert "VIX elevated" in reason
        assert "25.0" in reason

    def test_caution_vix_between_thresholds(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=30.0, domains_available=3, now=_ct(10, 0))
        assert mode == "CAUTION"


# --- 5. VIX unavailable CAUTION ---

class TestVIXUnavailable:
    def test_caution_vix_none(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=None, domains_available=3, now=_ct(10, 0))
        assert mode == "CAUTION"
        assert "unavailable" in reason.lower()


# --- 6. Insufficient domains STOP ---

class TestInsufficientDomains:
    def test_stop_zero_domains(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=0, now=_ct(10, 0))
        assert mode == "STOP"
        assert "Insufficient domains" in reason
        assert "0/2" in reason

    def test_stop_one_domain(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=1, now=_ct(10, 0))
        assert mode == "STOP"

    def test_go_at_min_domains(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=2, now=_ct(10, 0))
        assert mode == "GO"


# --- 7. Event day STOP ---

class TestEventDay:
    def test_stop_on_event_day(self, ks: KillSwitch) -> None:
        ks.set_event_day(True)
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(10, 0))
        assert mode == "STOP"
        assert "Event day" in reason

    def test_no_stop_when_event_day_false(self, ks: KillSwitch) -> None:
        ks.set_event_day(False)
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(10, 0))
        assert mode == "GO"

    def test_event_day_caution_mode(self) -> None:
        """When event_day_mode is not STOP, event day doesn't trigger STOP."""
        cfg = KillSwitchConfig(event_day_mode="CAUTION")
        ks = KillSwitch(config=cfg)
        ks.set_event_day(True)
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(10, 0))
        assert mode == "GO"  # event_day_mode != "STOP" → falls through to GO


# --- 8. GO all clear ---

class TestGO:
    def test_go_all_clear(self, ks: KillSwitch) -> None:
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(10, 0))
        assert mode == "GO"
        assert reason == "All clear"

    def test_go_early_morning(self, ks: KillSwitch) -> None:
        mode, _ = ks.evaluate(bias_score=0, vix=15.0, domains_available=4, now=_ct(8, 30))
        assert mode == "GO"


# --- Priority order tests ---

class TestPriorityOrder:
    def test_lunch_beats_vix_crisis(self, ks: KillSwitch) -> None:
        """Lunch window has higher priority than VIX crisis."""
        mode, reason = ks.evaluate(bias_score=5, vix=50.0, domains_available=3, now=_ct(12, 30))
        assert mode == "STOP"
        assert "Lunch" in reason

    def test_cutoff_beats_vix_crisis(self, ks: KillSwitch) -> None:
        """Cutoff has higher priority than VIX crisis."""
        mode, reason = ks.evaluate(bias_score=5, vix=50.0, domains_available=3, now=_ct(15, 30))
        assert mode == "STOP"
        assert "cutoff" in reason.lower()

    def test_vix_crisis_beats_insufficient_domains(self, ks: KillSwitch) -> None:
        """VIX crisis has higher priority than insufficient domains."""
        mode, reason = ks.evaluate(bias_score=5, vix=40.0, domains_available=0, now=_ct(10, 0))
        assert mode == "STOP"
        assert "VIX crisis" in reason

    def test_insufficient_domains_beats_event_day(self, ks: KillSwitch) -> None:
        """Insufficient domains has higher priority than event day."""
        ks.set_event_day(True)
        mode, reason = ks.evaluate(bias_score=5, vix=18.0, domains_available=0, now=_ct(10, 0))
        assert mode == "STOP"
        assert "Insufficient domains" in reason


# --- Custom config tests ---

class TestCustomConfig:
    def test_custom_lunch_window(self) -> None:
        cfg = KillSwitchConfig(lunch_start_hour=11, lunch_end_hour=14)
        ks = KillSwitch(config=cfg)
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(11, 0))
        assert mode == "STOP"

    def test_custom_vix_thresholds(self) -> None:
        cfg = KillSwitchConfig(vix_crisis_threshold=30.0, vix_elevated_threshold=20.0)
        ks = KillSwitch(config=cfg)
        mode, _ = ks.evaluate(bias_score=5, vix=25.0, domains_available=3, now=_ct(10, 0))
        assert mode == "CAUTION"

    def test_custom_min_domains(self) -> None:
        cfg = KillSwitchConfig(min_domains_for_go=4)
        ks = KillSwitch(config=cfg)
        mode, _ = ks.evaluate(bias_score=5, vix=18.0, domains_available=3, now=_ct(10, 0))
        assert mode == "STOP"
