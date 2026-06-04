"""Tests for institutional computation engines."""
from __future__ import annotations

from gex_terminal.engine.dp_levels import DarkPoolLevelEngine
from gex_terminal.engine.signal_grid import SignalGridEngine
from gex_terminal.engine.swing_equilibrium import SwingEquilibriumEngine


def test_signal_grid_counts_buy_and_sell_confluence() -> None:
    engine = SignalGridEngine()

    grid = engine.compute(
        inst_flow_direction="BUY LEAN",
        market_tide_direction="bullish",
        floor_flow_direction="sell",
        sweep_flow_direction="ACCUMULATION",
        block_flow_direction="distribution",
        oi_change_direction="hold",
    )

    assert grid.total_signals == 10
    assert grid.confluence_buy == 3
    assert grid.confluence_sell == 2
    assert [row.state for row in grid.rows[:3]] == ["BUY", "SELL", "NEUTRAL"]
    assert grid.rows[8].state == "HOLD"


def test_dark_pool_levels_cluster_and_classify_support_resistance() -> None:
    engine = DarkPoolLevelEngine()

    levels = engine.compute_levels(
        [
            {"price": 450.5, "premium": 5_000_000, "size": 100_000},
            {"price": 450.3, "premium": 3_000_000, "size": 80_000},
            {"price": 460.0, "premium": 9_000_000, "size": 120_000},
        ],
        current_price_nq=21_000.0,
        nq_qqq_ratio=41.0,
    )

    assert len(levels) == 2
    assert levels[0].total_premium == 9_000_000
    assert levels[0].level_type == "SUPPORT"
    assert levels[1].print_count == 2
    assert levels[1].volume == 180_000
    assert levels[1].multiplier < levels[0].multiplier


def test_swing_equilibrium_blends_components_and_builds_history() -> None:
    engine = SwingEquilibriumEngine()

    first = engine.compute(
        [21380.0, 21450.0],
        [5_000_000, 3_000_000],
        gamma_flip_nq=21380.0,
        hvl_nq=21425.0,
    )
    second = engine.compute(
        [21400.0],
        [4_000_000],
        gamma_flip_nq=21390.0,
        hvl_nq=21410.0,
    )

    assert first.confidence == 1.0
    assert 21_300 < first.price_nq < 21_500
    assert second.confidence == 1.0
    assert second.price_nq != 0.0


def test_swing_equilibrium_returns_zero_without_components() -> None:
    engine = SwingEquilibriumEngine()

    equilibrium = engine.compute([], [], gamma_flip_nq=None, hvl_nq=None)

    assert equilibrium.price_nq == 0.0
    assert equilibrium.confidence == 0.0
