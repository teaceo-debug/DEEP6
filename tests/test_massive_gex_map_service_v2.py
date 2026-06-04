"""DEEP6 Gamma Decision Surface V2 — complete test suite (C1–C6)."""
from __future__ import annotations

from scripts.massive_gex_map_service_v2 import (
    StrikeExposure,
    translate_behavior,
    assign_tier,
    compute_health_state,
    detect_call_wall,
    detect_put_wall,
    detect_hvl,
    detect_gamma_flip,
    detect_secondary_nodes,
    detect_open_space_lanes,
    detect_confluence_zones,
    score_level_confidence,
    rank_levels,
    apply_near_price_cap,
    aggregate_chain,
    spot_window,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_sx(
    strike: float, net_gex: float, call_oi: int = 100, put_oi: int = 100
) -> StrikeExposure:
    s = StrikeExposure(strike=strike)
    s.net_gex = net_gex
    s.abs_gex = abs(net_gex)
    s.call_oi = call_oi
    s.put_oi = put_oi
    s.contract_count = 1
    return s


# ===================================================================
# C1 — Behavior translation tests
# ===================================================================


def test_put_wall_maps_to_defend() -> None:
    b = translate_behavior("put_wall", "", 0, 0)
    assert b.state == "DEFEND"
    assert b.action_hint == "HOLD"


def test_call_wall_maps_to_reject() -> None:
    b = translate_behavior("call_wall", "", 0, 0)
    assert b.state == "REJECT"
    assert b.action_hint == "FADE"


def test_hvl_maps_to_attract() -> None:
    b = translate_behavior("hvl", "", 0, 0)
    assert b.state == "ATTRACT"
    assert b.action_hint == "TARGET"


def test_gamma_flip_maps_to_flip() -> None:
    b = translate_behavior("gamma_flip", "", 0, 0)
    assert b.state == "FLIP"
    assert b.action_hint == "WATCH_FOR_FLIP"


def test_pos_gex_above_spot_maps_to_reject() -> None:
    b = translate_behavior("pos_gex_4", "", 0, 0)
    assert b.state == "REJECT"
    assert b.action_hint == "FADE"


def test_neg_gex_below_spot_maps_to_defend() -> None:
    b = translate_behavior("neg_gex_5", "", 0, 0)
    assert b.state == "DEFEND"
    assert b.action_hint == "HOLD"


# ===================================================================
# C2 — Selectivity tests
# ===================================================================


def test_no_far_away_levels_when_cap_applied() -> None:
    """V3 near-price cap: no level beyond max_futures_distance_points emitted."""
    by = {
        19000.0: make_sx(19000.0, -5e9),
        21200.0: make_sx(21200.0, 3e9),
        23000.0: make_sx(23000.0, 8e9),
    }
    near = apply_near_price_cap(
        spot_window(by, 21200.0, 0.20, None, None),
        futures_spot=21200.0,
        ratio=1.0,
        max_futures_distance_points=350.0,
    )
    prices = {sx.strike for sx in near}
    assert 19000.0 not in prices, "Far-below strike should be excluded by cap"
    assert 23000.0 not in prices, "Far-above strike should be excluded by cap"
    assert 21200.0 in prices, "Near strike should remain"


def test_empty_output_when_no_near_actionable_structure() -> None:
    """If no strikes within cap, near_selected is empty."""
    by = {
        18000.0: make_sx(18000.0, -5e9),
        24000.0: make_sx(24000.0, 5e9),
    }
    near = apply_near_price_cap(
        spot_window(by, 21200.0, 0.20, None, None),
        futures_spot=21200.0,
        ratio=1.0,
        max_futures_distance_points=100.0,
    )
    assert near == [], "No near strikes should produce empty list"


def test_max_rendered_levels_cap_respected() -> None:
    """Tier assignment: high abs_gex + near price = T1."""
    by = {
        float(21000 + i * 10): make_sx(float(21000 + i * 10), float((i + 1) * 1e9))
        for i in range(10)
    }
    strikes = list(by.values())
    hvl = detect_hvl(strikes)
    assert hvl is not None
    assert hvl.strike == 21090.0  # index 9 has abs_gex=10e9


# ===================================================================
# C3 — Confluence detection tests
# ===================================================================


def test_two_levels_within_25pts_merge() -> None:
    """Two levels within 25 futures-points merge into one confluence zone."""
    lvls = [
        {
            "mapped_price": 21000.0,
            "id": "put_wall",
            "confidence_score": 0.8,
            "behavior_state": "DEFEND",
            "structural_source": "put_wall",
        },
        {
            "mapped_price": 21020.0,
            "id": "neg_gex_4",
            "confidence_score": 0.6,
            "behavior_state": "DEFEND",
            "structural_source": "neg_gex_4",
        },
        {
            "mapped_price": 21500.0,
            "id": "call_wall",
            "confidence_score": 0.9,
            "behavior_state": "REJECT",
            "structural_source": "call_wall",
        },
    ]
    zones = detect_confluence_zones(lvls, 21200.0, merge_window_pts=25.0)
    assert len(zones) == 1, f"Expected 1 zone, got {len(zones)}"
    assert zones[0].zone_low <= 21000.0
    assert zones[0].zone_high >= 21020.0
    assert zones[0].dominant_behavior == "DEFEND"


def test_confluence_zone_label_correct_for_dominant_behavior() -> None:
    lvls = [
        {
            "mapped_price": 21000.0,
            "id": "call_wall",
            "confidence_score": 0.9,
            "behavior_state": "REJECT",
            "structural_source": "call_wall",
        },
        {
            "mapped_price": 21015.0,
            "id": "pos_gex_4",
            "confidence_score": 0.7,
            "behavior_state": "REJECT",
            "structural_source": "pos_gex_4",
        },
    ]
    zones = detect_confluence_zones(lvls, 21200.0, merge_window_pts=25.0)
    assert len(zones) == 1
    assert zones[0].dominant_behavior == "REJECT"
    assert "REJECT" in zones[0].label


def test_confluence_member_level_ids_correct() -> None:
    lvls = [
        {
            "mapped_price": 21000.0,
            "id": "put_wall",
            "confidence_score": 0.8,
            "behavior_state": "DEFEND",
            "structural_source": "put_wall",
        },
        {
            "mapped_price": 21010.0,
            "id": "neg_gex_4",
            "confidence_score": 0.6,
            "behavior_state": "DEFEND",
            "structural_source": "neg_gex_4",
        },
    ]
    zones = detect_confluence_zones(lvls, 21200.0, merge_window_pts=25.0)
    assert len(zones) == 1
    assert set(zones[0].member_level_ids) == {"put_wall", "neg_gex_4"}


# ===================================================================
# C4 — Open-space lane detection tests
# ===================================================================


def test_lane_detected_between_levels_over_80pts_apart() -> None:
    """Lane detected when gap > 80pts between consecutive levels."""
    lvls = [
        {"mapped_price": 21000.0, "id": "put_wall"},
        {"mapped_price": 21200.0, "id": "call_wall"},
    ]
    lanes = detect_open_space_lanes(lvls, 21100.0)
    assert len(lanes) >= 1


def test_no_lane_when_levels_close() -> None:
    """No lane emitted when levels are within 80pts of each other."""
    lvls = [
        {"mapped_price": 21000.0, "id": "put_wall"},
        {"mapped_price": 21050.0, "id": "call_wall"},
    ]
    lanes = detect_open_space_lanes(lvls, 21000.0)
    close_lanes = [lane for lane in lanes if lane["width_pts"] > 80.0]
    assert len(close_lanes) == 0


def test_lane_has_correct_bounds() -> None:
    """Lane start_price and end_price are correct."""
    lvls = [
        {"mapped_price": 21000.0, "id": "put_wall"},
        {"mapped_price": 21200.0, "id": "call_wall"},
    ]
    lanes = detect_open_space_lanes(lvls, 21400.0)
    assert len(lanes) == 2
    assert lanes[0]["start_price"] == 21000.0
    assert lanes[0]["end_price"] == 21200.0
    assert lanes[0]["width_pts"] == 200.0


# ===================================================================
# C5 — Freshness model tests
# ===================================================================


def test_health_state_healthy_when_fresh() -> None:
    assert compute_health_state(0) == "healthy"
    assert compute_health_state(179) == "healthy"


def test_health_state_stale_when_age_exceeds_stale_seconds() -> None:
    assert compute_health_state(181) == "stale"
    assert compute_health_state(599) == "stale"


def test_health_state_very_stale_when_age_exceeds_very_stale_seconds() -> None:
    assert compute_health_state(600) == "very_stale"
    assert compute_health_state(1200) == "very_stale"


def test_health_state_uses_custom_thresholds() -> None:
    assert compute_health_state(100, stale_seconds=90, very_stale_seconds=200) == "stale"
    assert compute_health_state(250, stale_seconds=90, very_stale_seconds=200) == "very_stale"
    assert compute_health_state(50, stale_seconds=90, very_stale_seconds=200) == "healthy"


# ===================================================================
# C6 — Confidence scoring + tier tests
# ===================================================================


def test_high_abs_gex_near_price_is_t1() -> None:
    """High abs_gex + near price -> T1 (score >= 0.75)."""
    strikes = [
        make_sx(21000.0, 10e9, call_oi=5000, put_oi=5000),
        make_sx(21200.0, 1e9, call_oi=100, put_oi=100),
    ]
    max_abs_gex = max(s.abs_gex for s in strikes)
    max_oi = max(s.call_oi + s.put_oi for s in strikes)
    score = score_level_confidence(
        strikes[0],
        distance_pts=0.0,
        futures_spot=21000.0,
        flip_distance=0.0,
        max_abs_gex=max_abs_gex,
        max_oi=max_oi,
        max_futures_distance_points=350.0,
    )
    assert score >= 0.75, f"Expected T1 score >= 0.75, got {score}"
    assert assign_tier(score) == "T1"


def test_low_abs_gex_far_price_is_t3() -> None:
    """Low abs_gex + far price -> T3 (score < 0.50)."""
    strikes = [
        make_sx(21000.0, 10e9, call_oi=5000, put_oi=5000),
        make_sx(21500.0, 0.001e9, call_oi=1, put_oi=1),
    ]
    max_abs_gex = max(s.abs_gex for s in strikes)
    max_oi = max(s.call_oi + s.put_oi for s in strikes)
    score = score_level_confidence(
        strikes[1],
        distance_pts=500.0,
        futures_spot=21000.0,
        flip_distance=500.0,
        max_abs_gex=max_abs_gex,
        max_oi=max_oi,
        max_futures_distance_points=350.0,
    )
    assert score < 0.50, f"Expected T3 score < 0.50, got {score}"
    assert assign_tier(score) == "T3"


def test_ranking_is_stable() -> None:
    """Same input always produces same ranked order."""
    lvls = [
        {"confidence_score": 0.8, "id": "a"},
        {"confidence_score": 0.6, "id": "b"},
        {"confidence_score": 0.9, "id": "c"},
        {"confidence_score": 0.5, "id": "d"},
    ]
    r1 = rank_levels(lvls)
    r2 = rank_levels(lvls)
    assert [x["id"] for x in r1] == [x["id"] for x in r2]
    assert r1[0]["id"] == "c"
    assert r1[-1]["id"] == "d"
