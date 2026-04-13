"""Tests for walk_forward.py — fold splitting, purge logic, WFE gate.

No Databento required — uses lightweight bar stubs (integer lists).
split_folds() only needs len(bars) and slicing, so any list works.

TEST-05: purged walk-forward splits prevent leakage.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.walk_forward import split_folds, compute_wfe, wfe_gate


def fake_bars(n: int) -> list:
    """Return n minimal bar-like objects sufficient for split_folds.

    split_folds only needs len(bars) and slicing — integers suffice.
    Using range(n) means bar values equal their index, making purge
    gap assertions directly verifiable via arithmetic on bar values.
    """
    return list(range(n))


# ---------------------------------------------------------------------------
# Fold count tests
# ---------------------------------------------------------------------------

def test_split_folds_count():
    """100-bar list with n_folds=3 should return 3 fold tuples."""
    bars = fake_bars(100)
    folds = split_folds(bars, n_folds=3, oos_frac=0.20, purge_bars=5)
    assert len(folds) == 3, f"Expected 3 folds, got {len(folds)}"


# ---------------------------------------------------------------------------
# Purge gap tests (D-10, TEST-05)
# ---------------------------------------------------------------------------

def test_purge_gap():
    """IS end index must be at least purge_bars before OOS start index.

    With integer bars = range(200): train[-1] is the last IS integer value
    (equals the last IS index), oos[0] is the first OOS integer value
    (equals the OOS start index). The purge gap = oos[0] - train[-1] - 1.

    Invariant: train[-1] + purge_bars < oos[0]
    """
    bars = fake_bars(200)
    purge = 10
    folds = split_folds(bars, n_folds=3, oos_frac=0.20, purge_bars=purge)
    assert len(folds) > 0, "Expected at least 1 fold for 200 bars"
    for train, oos in folds:
        # train[-1] is last IS bar index value, oos[0] is first OOS bar index value
        # Gap must strictly exceed purge_bars
        assert train[-1] + purge < oos[0], (
            f"Purge gap violated: IS ends at {train[-1]}, "
            f"OOS starts at {oos[0]}, purge={purge}"
        )


# ---------------------------------------------------------------------------
# OOS non-overlap tests
# ---------------------------------------------------------------------------

def test_oos_non_overlapping():
    """Fold OOS windows must not overlap each other."""
    bars = fake_bars(200)
    folds = split_folds(bars, n_folds=3, oos_frac=0.20, purge_bars=5)
    assert len(folds) > 1, "Need at least 2 folds to test non-overlap"
    oos_ranges = [(oos[0], oos[-1]) for _, oos in folds]
    for i in range(len(oos_ranges) - 1):
        end_i = oos_ranges[i][1]
        start_j = oos_ranges[i + 1][0]
        assert end_i < start_j, (
            f"OOS overlap: fold {i + 1} ends {end_i}, fold {i + 2} starts {start_j}"
        )


# ---------------------------------------------------------------------------
# WFE computation tests
# ---------------------------------------------------------------------------

def test_compute_wfe_normal():
    """WFE = mean(OOS) / mean(IS) for positive IS P&L."""
    is_pnls = [100.0, 80.0, 90.0]
    oos_pnls = [75.0, 60.0, 70.0]
    wfe = compute_wfe(is_pnls, oos_pnls)
    expected = (75 + 60 + 70) / 3 / ((100 + 80 + 90) / 3)  # ~0.7963
    assert abs(wfe - expected) < 0.001, f"WFE={wfe:.4f}, expected ~{expected:.4f}"


def test_compute_wfe_zero_is():
    """WFE should be 0.0 when IS mean is <= 0 (no division by negative)."""
    wfe = compute_wfe([-10.0, -20.0], [5.0, 5.0])
    assert wfe == 0.0, f"WFE should be 0 when IS mean <= 0, got {wfe}"


def test_compute_wfe_zero_is_exact_zero():
    """WFE should be 0.0 when IS mean is exactly 0.0."""
    wfe = compute_wfe([0.0, 0.0], [10.0, 10.0])
    assert wfe == 0.0, f"WFE should be 0 when IS mean == 0, got {wfe}"


# ---------------------------------------------------------------------------
# WFE gate tests
# ---------------------------------------------------------------------------

def test_wfe_gate_pass():
    """Gate must pass when WFE meets or exceeds threshold."""
    assert wfe_gate(0.70, 0.70) is True, "WFE == threshold should pass"
    assert wfe_gate(0.80, 0.70) is True, "WFE > threshold should pass"
    assert wfe_gate(1.50, 0.70) is True, "WFE >> threshold should pass"


def test_wfe_gate_fail():
    """Gate must fail when WFE is below threshold."""
    assert wfe_gate(0.69, 0.70) is False, "WFE just below threshold should fail"
    assert wfe_gate(0.0, 0.70) is False, "WFE == 0.0 should fail"
    assert wfe_gate(-0.5, 0.70) is False, "Negative WFE should fail"


# ---------------------------------------------------------------------------
# Insufficient data tests
# ---------------------------------------------------------------------------

def test_fold_min_oos_size_insufficient():
    """15-bar input cannot produce meaningful folds — should return empty list.

    With n=15, oos_size=3 (20%), n_folds=5: oos_start becomes negative for
    most folds, or train_end is too small, or oos is < 20 bars minimum.
    """
    bars = fake_bars(15)
    folds = split_folds(bars, n_folds=5, oos_frac=0.20, purge_bars=10)
    assert len(folds) == 0, f"Expected 0 folds for 15-bar list, got {len(folds)}"
