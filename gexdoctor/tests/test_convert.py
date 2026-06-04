from __future__ import annotations

import pytest

from gexdoctor.monitor.convert import (
    compute_nq_ndx_basis,
    compute_nq_qqq_factor,
    ndx_to_nq,
    normalize_level,
    qqq_to_nq,
)


def test_compute_nq_qqq_factor_basic() -> None:
    assert compute_nq_qqq_factor(21800, 480) == pytest.approx(45.4166666667)


def test_compute_nq_qqq_factor_zero_raises() -> None:
    with pytest.raises(ValueError, match="qqq_spot must be non-zero"):
        compute_nq_qqq_factor(21800, 0)


def test_qqq_to_nq_accuracy() -> None:
    factor = compute_nq_qqq_factor(21800, 480)
    assert qqq_to_nq(480.50, factor) == pytest.approx(21822.71, abs=0.02)


def test_compute_nq_ndx_basis() -> None:
    assert compute_nq_ndx_basis(21800, 21750) == pytest.approx(50)


def test_ndx_to_nq_accuracy() -> None:
    assert ndx_to_nq(21500, 50) == pytest.approx(21550)


def test_normalize_nq_passthrough() -> None:
    assert normalize_level(123.45, "NQ", 21800) == pytest.approx(123.45)


def test_normalize_qqq_conversion() -> None:
    assert normalize_level(480.50, "QQQ", 21800, qqq_spot=480) == pytest.approx(21822.71, abs=0.02)


def test_normalize_ndx_conversion() -> None:
    assert normalize_level(21500, "NDX", 21800, ndx_spot=21750) == pytest.approx(21550)


def test_normalize_spx_rejects() -> None:
    with pytest.raises(ValueError, match="SPX levels cannot be converted"):
        normalize_level(5000, "SPX", 21800)


def test_normalize_qqq_missing_spot_raises() -> None:
    with pytest.raises(ValueError, match="qqq_spot required"):
        normalize_level(480.50, "QQQ", 21800)


def test_normalize_ndx_missing_spot_raises() -> None:
    with pytest.raises(ValueError, match="ndx_spot required"):
        normalize_level(21500, "NDX", 21800)


def test_normalize_unknown_symbol_raises() -> None:
    with pytest.raises(ValueError, match="Unknown symbol"):
        normalize_level(1.0, "EUR", 21800)  # type: ignore[arg-type]
