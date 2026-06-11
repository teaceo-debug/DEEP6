from __future__ import annotations

from pathlib import Path

from deep6.ml.depth_radar.wall_ranker import SourceQuality, WallRanker
from deep6.services.live_mbo_radar import LiveMBORadar


def test_wall_ranker_scores_spoof_like_pull_with_evidence() -> None:
    ranker = WallRanker(source_quality=SourceQuality.TRUE_MBO)

    ranked = ranker.rank(
        {
            "intent": "SPOOF_LIKE",
            "classification": "SPOOF",
            "state": "PULLED",
            "size": 40,
            "max_size": 320,
            "duration_sec": 0.18,
            "in_touch_band": True,
            "pull_approach_flag": 1.0,
            "cancel_reappear_count": 3,
            "filled_volume": 0,
            "absorbed_volume": 0,
            "refills_so_far": 0,
            "distance_from_mid_ticks": 6,
        }
    )

    assert ranked["scores"]["spoof"] >= 75
    assert ranked["scores"]["quality"] < ranked["scores"]["spoof"]
    assert "pulled_on_approach" in ranked["evidence"]
    assert ranked["source_quality"] == "TRUE_MBO"
    assert ranked["confidence_multiplier"] == 1.0


def test_wall_ranker_scores_iceberg_refresh_as_high_quality() -> None:
    ranker = WallRanker(source_quality=SourceQuality.TRUE_MBO)

    ranked = ranker.rank(
        {
            "intent": "RESERVE_REFRESH",
            "classification": "ICEBERG",
            "state": "DEFENDING",
            "size": 180,
            "max_size": 220,
            "duration_sec": 4.5,
            "in_touch_band": True,
            "refills_so_far": 7,
            "filled_volume": 640,
            "absorbed_volume": 640,
            "pull_approach_flag": 0.0,
            "distance_from_mid_ticks": 2,
        }
    )

    assert ranked["scores"]["iceberg"] >= 70
    assert ranked["scores"]["quality"] >= 70
    assert "reloaded_after_hits" in ranked["evidence"]
    assert "meaningful_fill_interaction" in ranked["evidence"]


def test_rithmic_payload_marks_l2_approx_and_preserves_rich_wall_fields(tmp_path: Path) -> None:
    radar = LiveMBORadar(source="rithmic", output_path=tmp_path / "walls.json")
    radar._last_mid_price = 20000.0

    wall = radar._to_output_wall(
        {
            "episode_id": "ep-1",
            "price": 20001.5,
            "side": "ask",
            "size": 40,
            "max_size": 320,
            "classification": "SPOOF",
            "confidence": 0.86,
            "duration_sec": 0.2,
            "refills_so_far": 0,
            "state": "PULLED",
            "intent": "SPOOF_LIKE",
            "in_touch_band": True,
            "pull_approach_flag": 1.0,
            "cancel_reappear_count": 3,
            "filled_volume": 0,
            "absorbed_volume": 0,
            "delta_2s": -120,
            "delta_10s": -420,
            "approach_speed": 3.5,
            "attack_intensity": 0.8,
            "distance_from_mid_ticks": 6,
        }
    )

    assert wall["episode_id"] == "ep-1"
    assert wall["source_quality"] == "L2_APPROX"
    assert wall["scores"]["spoof"] >= 70
    assert wall["in_touch_band"] is True
    assert wall["delta_2s"] == -120
    assert wall["evidence"]


def test_payload_v2_includes_schema_market_state_source_quality_and_gray_fusion_stub(tmp_path: Path) -> None:
    radar = LiveMBORadar(source="rithmic", output_path=tmp_path / "walls.json")
    radar._last_mid_price = 20000.0

    payload = radar._build_payload(
        timestamp="2026-06-05T14:00:00Z",
        output_walls=[
            {
                "episode_id": "ep-1",
                "price": 20001.5,
                "side": "ask",
                "size": 40,
                "max_size": 320,
                "classification": "SPOOF",
                "confidence": 0.86,
                "duration_sec": 0.2,
                "refill_count": 0,
                "state": "PULLED",
                "intent": "SPOOF_LIKE",
                "source_quality": "L2_APPROX",
                "scores": {"spoof": 86, "quality": 25},
                "evidence": ["pulled_on_approach"],
            }
        ],
    )

    assert payload["schema"] == "DEEP6_DEPTH_RADAR_V2"
    assert payload["version"]
    assert payload["source"] == "rithmic"
    assert payload["source_quality"] == "L2_APPROX"
    assert payload["data_quality"]["order_id_available"] is False
    assert payload["market_state"]["mid_price"] == 20000.0
    assert payload["gray_fusion"]["active_marker"] is False
    assert payload["walls"][0]["episode_id"] == "ep-1"
