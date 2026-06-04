"""End-to-end smoke tests for the DEEP6 copilot system."""
from __future__ import annotations

import asyncio
import importlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from deep6.copilot.config import CopilotConfig
from deep6.copilot.overlay_content import OverlayContentRenderer
from deep6.copilot.session import SessionManager
from deep6.copilot.types import DataSourceStatus, TradeCall


@pytest.fixture
def copilot_cfg() -> CopilotConfig:
    """CopilotConfig with test values."""
    return CopilotConfig(
        claude_api_key="test-key",
        narrative_interval_sec=1,
        screenshot_interval_sec=2,
        token_budget_per_hour=10_000,
    )


def _run_copilot(*args: str, timeout: int = 15) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "deep6.copilot", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "ANTHROPIC_API_KEY": "test"},
        cwd=Path(__file__).resolve().parents[2],
    )


class _FakeNarrativeEngine:
    def __init__(self) -> None:
        self._callbacks: list = []

    def on_narrative_complete(self, callback) -> None:
        self._callbacks.append(callback)

    def fire(self, text: str) -> None:
        for callback in self._callbacks:
            callback(text)


class _FakeTradeCallEngine:
    def __init__(self) -> None:
        self._callbacks: list = []

    def on_trade_call(self, callback) -> None:
        self._callbacks.append(callback)

    def fire(self, call: TradeCall) -> None:
        for callback in self._callbacks:
            callback(call)


class _FakeFreshnessTracker:
    def __init__(self, statuses: list[DataSourceStatus] | None = None) -> None:
        self._statuses = statuses or []

    def get_status_all(self) -> list[DataSourceStatus]:
        return list(self._statuses)


class TestDryRunMode:
    def test_help_flag_works(self) -> None:
        """python -m deep6.copilot --help exits 0."""
        result = _run_copilot("--help", timeout=30)

        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert "--test-overlay" in result.stdout
        assert "--config" in result.stdout

    def test_dry_run_flag_is_recognized(self) -> None:
        """python -m deep6.copilot --dry-run exits cleanly."""
        result = _run_copilot("--dry-run")

        assert result.returncode == 0
        assert "Copilot starting..." in result.stdout
        assert "Dry run enabled" in result.stdout

    def test_config_imports_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CopilotConfig loads correctly from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
        monkeypatch.setenv("COPILOT_SCREENSHOT_INTERVAL_SEC", "45")
        monkeypatch.setenv("COPILOT_OVERLAY_SIDE", "left")

        cfg = CopilotConfig.from_env()

        assert cfg.claude_api_key == "sk-ant-test123"
        assert cfg.screenshot_interval_sec == 45
        assert cfg.overlay_side == "left"


class TestSessionManagerLifecycle:
    @pytest.mark.asyncio
    async def test_session_manager_can_be_instantiated(self, copilot_cfg: CopilotConfig, tmp_path: Path) -> None:
        """SessionManager instantiates without error."""
        mgr = SessionManager(copilot_cfg, state_path=tmp_path / ".copilot_state.json")

        assert mgr is not None
        assert mgr.is_started is False

    @pytest.mark.asyncio
    async def test_start_stop_cycle_completes_without_error(self, copilot_cfg: CopilotConfig, tmp_path: Path) -> None:
        """Session manager starts and stops cleanly with mocked components."""
        mgr = SessionManager(copilot_cfg, state_path=tmp_path / ".copilot_state.json")
        mgr._bridge_client.connect = AsyncMock()
        mgr._bridge_client.disconnect = AsyncMock()
        mgr._overlay.start = MagicMock()
        mgr._overlay.stop = MagicMock()

        await mgr.start()

        assert mgr.is_started is True
        assert mgr._overlay.start.called
        assert mgr._bridge_client.connect.await_count == 1

        await mgr.stop()

        assert mgr.is_started is False
        assert mgr._overlay.stop.called
        assert mgr._bridge_client.disconnect.await_count == 1

    @pytest.mark.asyncio
    async def test_run_until_shutdown_exits_gracefully(self, copilot_cfg: CopilotConfig, tmp_path: Path) -> None:
        """run_until_shutdown handles signal-triggered shutdown cleanly."""
        mgr = SessionManager(copilot_cfg, state_path=tmp_path / ".copilot_state.json")
        mgr._bridge_client.connect = AsyncMock()
        mgr._bridge_client.disconnect = AsyncMock()
        mgr._overlay.start = MagicMock()
        mgr._overlay.stop = MagicMock()

        task = asyncio.create_task(mgr.run_until_shutdown())
        await asyncio.sleep(0.05)
        mgr._signal_shutdown()
        await asyncio.wait_for(task, timeout=2)

        assert mgr.is_started is False
        assert mgr._bridge_client.connect.await_count == 1
        assert mgr._bridge_client.disconnect.await_count == 1


class TestOverlayNarrativeUpdates:
    @pytest.mark.asyncio
    async def test_overlay_narrative_updates_and_trade_calls_flow(self) -> None:
        """Overlay renderer forwards narrative, statuses, and trade calls."""
        overlay = MagicMock()
        narrative_engine = _FakeNarrativeEngine()
        trade_engine = _FakeTradeCallEngine()
        freshness = _FakeFreshnessTracker(
            [DataSourceStatus(source_name="bridge_tcp", is_stale=False)]
        )

        renderer = OverlayContentRenderer(
            overlay=overlay,
            narrative_engine=narrative_engine,
            trade_engine=trade_engine,
            freshness_tracker=freshness,
        )

        await renderer.start()
        narrative_engine.fire("Absorption confirmed at support.")
        trade_engine.fire(TradeCall(direction="LONG", entry=18450, stop=18440, target=18470, confidence=82))
        await asyncio.sleep(0.05)
        await renderer.stop()

        overlay.update_narrative.assert_called_once_with("Absorption confirmed at support.")
        overlay.update_source_status.assert_called()
        overlay.update_trade_call.assert_any_call(
            TradeCall(direction="LONG", entry=18450, stop=18440, target=18470, confidence=82)
        )

    @pytest.mark.asyncio
    async def test_long_narrative_is_truncated(self) -> None:
        """Long overlay narratives are trimmed for display."""
        overlay = MagicMock()
        renderer = OverlayContentRenderer(
            overlay=overlay,
            narrative_engine=_FakeNarrativeEngine(),
            trade_engine=_FakeTradeCallEngine(),
            freshness_tracker=_FakeFreshnessTracker(),
        )

        long_text = "A" * 600
        renderer._on_narrative_complete(long_text)

        sent_text = overlay.update_narrative.call_args.args[0]
        assert len(sent_text) <= 303
        assert sent_text.endswith("...")


class TestGracefulDegradation:
    def test_all_copilot_modules_import_without_crash(self) -> None:
        """Copilot modules import cleanly without external services."""
        modules = [
            "deep6.copilot.config",
            "deep6.copilot.types",
            "deep6.copilot.brain",
            "deep6.copilot.budget",
            "deep6.copilot.context",
            "deep6.copilot.freshness",
            "deep6.copilot.narrative",
            "deep6.copilot.overlay",
            "deep6.copilot.overlay_content",
            "deep6.copilot.session",
            "deep6.copilot.trade_calls",
            "deep6.copilot.vision",
            "deep6.copilot.vision_analysis",
            "deep6.copilot.bridge_client",
            "deep6.copilot.adapters.calendar",
            "deep6.copilot.adapters.news",
            "deep6.copilot.adapters.sentiment",
            "deep6.copilot.adapters.options_flow",
            "deep6.copilot.adapters.internals",
        ]

        for mod_name in modules:
            mod = importlib.import_module(mod_name)
            assert mod is not None, f"Failed to import {mod_name}"

    def test_copilot_help_outputs_required_flags(self) -> None:
        """--help shows all required CLI flags."""
        result = _run_copilot("--help", timeout=30)

        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert "--test-overlay" in result.stdout
        assert "--config" in result.stdout
