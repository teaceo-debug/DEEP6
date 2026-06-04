from __future__ import annotations
import pytest

# Only run if PySide6 is available
PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from depth_radar_desktop.live.walls_table import WallsTableModel, COLUMNS, COLUMN_KEYS


@pytest.fixture
def model():
    return WallsTableModel()


def test_model_empty(model):
    assert model.rowCount() == 0
    assert model.columnCount() == len(COLUMNS)


def test_model_headers(model):
    for i, name in enumerate(COLUMNS):
        assert model.headerData(i, Qt.Horizontal) == name


def test_model_update_walls(model, mock_walls):
    model.update_walls(mock_walls)
    assert model.rowCount() == 3


def test_model_price_format(model, mock_walls):
    model.update_walls(mock_walls)
    idx = model.index(0, 0)  # Price column
    value = model.data(idx, Qt.DisplayRole)
    assert "." in str(value)  # Should be formatted as float


def test_model_side_display(model, mock_walls):
    model.update_walls(mock_walls)
    idx = model.index(0, 1)  # Side column
    value = model.data(idx, Qt.DisplayRole)
    assert value in ("BID", "ASK")


def test_model_intent_display(model, mock_walls):
    model.update_walls(mock_walls)
    idx = model.index(0, 4)  # Intent column
    value = model.data(idx, Qt.DisplayRole)
    assert value in ("PASSIVE_REAL", "SPOOF_LIKE", "RESERVE_REFRESH", "MIGRATORY")


def test_model_confidence_format(model, mock_walls):
    model.update_walls(mock_walls)
    idx = model.index(0, 6)  # Confidence column
    value = model.data(idx, Qt.DisplayRole)
    assert "%" in str(value)


def test_model_foreground_spoof(model, mock_walls):
    model.update_walls(mock_walls)
    # mock_walls[1] has intent="SPOOF_LIKE"
    idx = model.index(1, 4)  # Intent column for spoof wall
    brush = model.data(idx, Qt.ForegroundRole)
    assert brush is not None  # Should have amber foreground


def test_model_empty_walls(model):
    model.update_walls([])
    assert model.rowCount() == 0
