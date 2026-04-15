"""Phase 14 — feed factory dispatch tests.

Verifies that ``deep6.data.factory.create_feed`` dispatches correctly on
``source``, honours the GLBX key preference (D-01), and raises on missing
credentials. Does NOT exercise live connections.
"""
from __future__ import annotations

import pytest

from deep6.config import Config
from deep6.data.databento_live import DatabentoLiveFeed
from deep6.data.factory import create_feed


def _cfg(**overrides):
    base = dict(
        rithmic_user="",
        rithmic_password="",
        rithmic_system_name="test",
        rithmic_uri="",
        db_path=":memory:",
        databento_api_key="",
        databento_api_key_glbx="",
    )
    base.update(overrides)
    return Config(**base)


def test_factory_returns_databento_feed():
    cfg = _cfg(databento_api_key_glbx="glbx-key")
    feed = create_feed("databento", cfg)
    assert isinstance(feed, DatabentoLiveFeed)
    assert feed.api_key == "glbx-key"


def test_factory_falls_back_to_primary_key():
    cfg = _cfg(databento_api_key="primary-key", databento_api_key_glbx="")
    feed = create_feed("databento", cfg)
    assert feed.api_key == "primary-key"


def test_factory_glbx_key_wins_when_both_set():
    cfg = _cfg(databento_api_key="primary", databento_api_key_glbx="glbx")
    feed = create_feed("databento", cfg)
    assert feed.api_key == "glbx"


def test_factory_raises_when_no_databento_key():
    cfg = _cfg()
    with pytest.raises(RuntimeError, match="DATABENTO_API_KEY"):
        create_feed("databento", cfg)


def test_factory_raises_on_unknown_source():
    cfg = _cfg()
    with pytest.raises(ValueError, match="Unknown data source"):
        create_feed("quantum", cfg)


def test_config_live_key_prefers_glbx():
    cfg = _cfg(databento_api_key="a", databento_api_key_glbx="b")
    assert cfg.databento_live_key() == "b"


def test_config_live_key_falls_back():
    cfg = _cfg(databento_api_key="a", databento_api_key_glbx="")
    assert cfg.databento_live_key() == "a"
