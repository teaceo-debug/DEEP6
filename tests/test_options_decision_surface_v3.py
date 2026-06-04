from __future__ import annotations

from scripts.options_decision_surface_v3 import (
    assign_tier,
    behavior_for_source,
    classify_regime,
    determine_flow_confirmation_state,
    score_level_confidence,
    selected_because,
)


def test_behavior_for_put_wall() -> None:
    state, hint = behavior_for_source("put_wall")
    assert state == "DEFEND"
    assert hint == "HOLD"


def test_behavior_for_call_wall() -> None:
    state, hint = behavior_for_source("call_wall")
    assert state == "REJECT"
    assert hint == "FADE"


def test_behavior_for_zero_dte_magnet() -> None:
    state, hint = behavior_for_source("zero_dte_magnet")
    assert state == "ATTRACT"
    assert hint == "TARGET"


def test_classify_regime_pinned_wins() -> None:
    summary = {"regime": "positive", "exposures": {"net_gex": 2_000_000_000, "net_dex": 0, "net_vex": 0, "net_chex": 0}}
    zte = {"pin_risk": {"pin_score": 81}, "regime": {"label": "pin-heavy"}}
    result = classify_regime(summary, zte)
    assert result["regime_state"] == "PINNED"


def test_classify_regime_negative_gamma() -> None:
    summary = {"regime": "negative", "exposures": {"net_gex": -500_000_000, "net_dex": 0, "net_vex": 0, "net_chex": 0}}
    zte = {"pin_risk": {"pin_score": 10}, "regime": {"label": "regular"}}
    result = classify_regime(summary, zte)
    assert result["regime_state"] == "NEGATIVE_GAMMA_EXPANSION"


def test_classify_regime_charm_dominated_near_close() -> None:
    summary = {"regime": "neutral", "exposures": {"net_gex": 0, "net_dex": 0, "net_vex": 10, "net_chex": 100}}
    zte = {"pin_risk": {"pin_score": 20}, "regime": {"label": "regular"}, "time_to_close_hours": 1.5}
    result = classify_regime(summary, zte)
    assert result["regime_state"] == "CHARM_DOMINATED"


def test_flow_confirmation_defend_confirmed() -> None:
    flow = {"net_direction": 1, "z_score": 0.8}
    state = determine_flow_confirmation_state("DEFEND", -18, flow)
    assert state == "FLOW_CONFIRMED"


def test_flow_confirmation_reject_contradicted() -> None:
    flow = {"net_direction": 1, "z_score": 1.2}
    state = determine_flow_confirmation_state("REJECT", 30, flow)
    assert state == "FLOW_CONTRADICTED"


def test_flow_confirmation_flip_accelerating() -> None:
    flow = {"net_direction": -1, "z_score": 1.4}
    state = determine_flow_confirmation_state("FLIP", 5, flow)
    assert state == "FLOW_ACCELERATING"


def test_flow_confirmation_far_level_structure_only() -> None:
    flow = {"net_direction": -1, "z_score": 2.0}
    state = determine_flow_confirmation_state("REJECT", 250, flow)
    assert state == "STRUCTURE_ONLY"


def test_score_level_confidence_rewards_pinned_near_level() -> None:
    score = score_level_confidence(
        abs_gex=10.0,
        max_abs_gex=10.0,
        distance_points=8.0,
        max_distance_points=350.0,
        flow_strength=1.0,
        is_pinned=True,
        regime_state="NEGATIVE_GAMMA_EXPANSION",
    )
    assert score > 0.75
    assert assign_tier(score) == "T1"


def test_score_level_confidence_penalizes_far_unpinned_level() -> None:
    score = score_level_confidence(
        abs_gex=1.0,
        max_abs_gex=10.0,
        distance_points=300.0,
        max_distance_points=350.0,
        flow_strength=0.0,
        is_pinned=False,
        regime_state="POSITIVE_GAMMA_RANGE",
    )
    assert score < 0.52
    assert assign_tier(score) == "T3"


def test_selected_because_is_specific() -> None:
    assert "support" in selected_because("put_wall").lower() or "defend" in selected_because("put_wall").lower()
