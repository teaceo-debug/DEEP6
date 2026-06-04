from __future__ import annotations

from scripts.massive_gex_map_service import StrikeExposure, choose_levels


def sx(strike: float, net_gex: float) -> StrikeExposure:
    item = StrikeExposure(strike=strike)
    item.net_gex = net_gex
    item.abs_gex = abs(net_gex)
    item.contract_count = 1
    return item


def test_choose_levels_v3_near_cap_does_not_force_far_pinned_walls() -> None:
    by = {
        635.0: sx(635.0, -13_000_000_000.0),
        672.0: sx(672.0, 63_000_000_000.0),
        675.0: sx(675.0, 148_000_000_000.0),
        680.0: sx(680.0, 88_000_000_000.0),
        714.0: sx(714.0, -1_000_000.0),
    }
    levels, selection = choose_levels(
        by,
        underlying="QQQ",
        futures_root="NQ",
        source_spot=673.84,
        futures_spot=27827.25,
        window_pct=0.07,
        max_above_pct=None,
        max_below_pct=None,
        max_levels=9,
        max_futures_distance_points=350,
    )

    prices = {level["key"]: level["price"] for level in levels}
    assert selection["algorithm"] == "original_v1_oi_gex_selective_near_price"
    assert selection["near_candidate_strikes"] == 3
    assert "put_wall" not in prices  # 635 QQQ maps ~1600 NQ points away; V3 should not force it.
    assert "gamma_flip" not in prices  # 714 QQQ maps ~1650 NQ points away; V3 should not force it.
    assert prices["call_wall"] == 27875.15
    assert len([level for level in levels if level["price"] == 27875.15]) == 1


def test_choose_levels_v3_outputs_no_levels_when_no_near_magnet_exists() -> None:
    by = {
        600.0: sx(600.0, -25_000_000_000.0),
        750.0: sx(750.0, 25_000_000_000.0),
    }
    levels, selection = choose_levels(
        by,
        underlying="QQQ",
        futures_root="NQ",
        source_spot=673.84,
        futures_spot=27827.25,
        window_pct=0.20,
        max_above_pct=None,
        max_below_pct=None,
        max_levels=9,
        max_futures_distance_points=100,
    )

    assert levels == []
    assert selection["candidate_strikes"] == 2
    assert selection["near_candidate_strikes"] == 0
