from __future__ import annotations
import pytest
import time

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication
from depth_radar_desktop.engine_bridge import EngineBridge


@pytest.fixture(scope="module")
def qapp():
    """Create a QCoreApplication for the test module."""
    import sys
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def test_bridge_init(qapp):
    bridge = EngineBridge(source="none")
    assert bridge.source == "none"
    assert bridge.is_running is False


def test_bridge_invalid_source(qapp):
    with pytest.raises(ValueError, match="Unsupported source"):
        EngineBridge(source="invalid")


def test_bridge_start_stop(qapp):
    bridge = EngineBridge(source="none")
    bridge.start()
    assert bridge.is_running is True
    time.sleep(0.5)
    bridge.stop()
    assert bridge.is_running is False


def test_bridge_double_start(qapp):
    bridge = EngineBridge(source="none")
    bridge.start()
    bridge.start()  # should not crash
    bridge.stop()


def test_bridge_stop_without_start(qapp):
    bridge = EngineBridge(source="none")
    bridge.stop()  # should not crash


def test_bridge_connection_signal(qapp):
    bridge = EngineBridge(source="none")
    received = []
    bridge.connection_changed.connect(lambda c: received.append(c))
    bridge.start()
    time.sleep(0.5)
    bridge.stop()
    assert False in received
