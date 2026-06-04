from __future__ import annotations

from deep6v2.signals.dom.compat.feature_flags import (
    DOM_INTELLIGENCE_ENABLED_ENV_VAR,
    force_disable_dom_intelligence,
    force_enable_dom_intelligence,
    is_dom_intelligence_enabled,
)
from deep6v2.signals.registry import DetectorRegistry


def test_enabled_by_default_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, raising=False)

    assert is_dom_intelligence_enabled() is True


def test_force_disable_then_enable_roundtrip(monkeypatch) -> None:
    monkeypatch.delenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, raising=False)

    force_disable_dom_intelligence()
    assert is_dom_intelligence_enabled() is False

    force_enable_dom_intelligence()
    assert is_dom_intelligence_enabled() is True


def test_env_var_false_like_values_disable_case_insensitive(monkeypatch) -> None:
    for value in ("False", "FALSE", "0", "no"):
        monkeypatch.setenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, value)
        assert is_dom_intelligence_enabled() is False


def test_env_var_true_enables(monkeypatch) -> None:
    monkeypatch.setenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, "true")

    assert is_dom_intelligence_enabled() is True


def test_disabled_flag_does_not_break_registry_construction(monkeypatch) -> None:
    monkeypatch.setenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, "false")

    registry = DetectorRegistry.create_default()

    assert is_dom_intelligence_enabled() is False
    assert isinstance(registry, DetectorRegistry)
    assert len(registry._detectors) > 0


def test_env_restores_after_context(monkeypatch) -> None:
    monkeypatch.delenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, raising=False)

    force_disable_dom_intelligence()
    assert is_dom_intelligence_enabled() is False

    monkeypatch.delenv(DOM_INTELLIGENCE_ENABLED_ENV_VAR, raising=False)
    assert is_dom_intelligence_enabled() is True
