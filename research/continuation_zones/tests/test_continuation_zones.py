from __future__ import annotations

import pandas as pd

from research.continuation_zones.continuation_zones import (
    ContinuationZoneDetector,
    Zone,
    score_continuation_zone,
)


def _make_frame(rows: list[dict[str, float]], freq: str = "5min") -> pd.DataFrame:
    index = pd.date_range(
        start="2026-01-05 14:30:00+00:00",
        periods=len(rows),
        freq=freq,
        tz="UTC",
        name="ts_event",
    )
    frame = pd.DataFrame(rows, index=index)
    if "volume" not in frame.columns:
        frame["volume"] = 100
    return frame[["open", "high", "low", "close", "volume"]]


def _basic_rbr_frame() -> pd.DataFrame:
    return _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.2, "low": 104.6, "close": 105.0, "volume": 100},
        ]
    )


def _basic_dbd_frame() -> pd.DataFrame:
    return _make_frame(
        [
            {"open": 105.0, "high": 105.2, "low": 100.8, "close": 101.0, "volume": 100},
            {"open": 101.0, "high": 101.5, "low": 100.5, "close": 100.8, "volume": 100},
            {"open": 100.4, "high": 100.4, "low": 99.8, "close": 100.0, "volume": 100},
        ]
    )


def test_score_continuation_zone_all_max() -> None:
    total, components = score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=15000,
        departure_close_extension_to_height_bp=5000,
        base_candle_count=1,
        max_base_body_ratio_bp=3500,
        trend_close_side_ok=True,
        trend_slope_ok=True,
        zone_height_ticks=6,
    )

    assert total == 10
    assert components == {
        "freshness": 2,
        "departure": 2,
        "base_quality": 2,
        "trend_alignment": 2,
        "zone_height": 2,
    }


def test_score_continuation_zone_all_zero() -> None:
    total, components = score_continuation_zone(
        timeframe_min=5,
        touch_count=2,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )

    assert total == 0
    assert components == {
        "freshness": 0,
        "departure": 0,
        "base_quality": 0,
        "trend_alignment": 0,
        "zone_height": 0,
    }


def test_score_freshness_decay() -> None:
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["freshness"] == 2
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=1,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["freshness"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=2,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["freshness"] == 0


def test_score_departure_thresholds() -> None:
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=15000,
        departure_close_extension_to_height_bp=5000,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["departure"] == 2
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=10000,
        departure_close_extension_to_height_bp=1,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["departure"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=9999,
        departure_close_extension_to_height_bp=5000,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["departure"] == 0


def test_score_base_quality_thresholds() -> None:
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=2,
        max_base_body_ratio_bp=3500,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["base_quality"] == 2
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=3,
        max_base_body_ratio_bp=5000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["base_quality"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=5000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["base_quality"] == 0


def test_score_trend_alignment() -> None:
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=True,
        trend_slope_ok=True,
        zone_height_ticks=2,
    )[1]["trend_alignment"] == 2
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=True,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["trend_alignment"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=True,
        zone_height_ticks=2,
    )[1]["trend_alignment"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=2,
    )[1]["trend_alignment"] == 0


def test_score_zone_height_5m() -> None:
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=4,
    )[1]["zone_height"] == 2
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=3,
    )[1]["zone_height"] == 1
    assert score_continuation_zone(
        timeframe_min=5,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=13,
    )[1]["zone_height"] == 0


def test_score_zone_height_15m() -> None:
    assert score_continuation_zone(
        timeframe_min=15,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=6,
    )[1]["zone_height"] == 2
    assert score_continuation_zone(
        timeframe_min=15,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=5,
    )[1]["zone_height"] == 1
    assert score_continuation_zone(
        timeframe_min=15,
        touch_count=0,
        departure_body_to_height_bp=0,
        departure_close_extension_to_height_bp=0,
        base_candle_count=4,
        max_base_body_ratio_bp=6000,
        trend_close_side_ok=False,
        trend_slope_ok=False,
        zone_height_ticks=19,
    )[1]["zone_height"] == 0


def test_detect_rbr_basic() -> None:
    zones = ContinuationZoneDetector().detect(_basic_rbr_frame(), timeframe_min=5)

    assert len(zones) == 1
    zone = zones[0]
    assert zone.kind == "RBR"
    assert zone.top == 104.2
    assert zone.bottom == 103.5


def test_detect_dbd_basic() -> None:
    zones = ContinuationZoneDetector().detect(_basic_dbd_frame(), timeframe_min=5)

    assert len(zones) == 1
    zone = zones[0]
    assert zone.kind == "DBD"
    assert zone.top == 101.5
    assert zone.bottom == 100.8


def test_detect_no_zone_when_base_too_large() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 105.5, "low": 103.5, "close": 105.2, "volume": 100},
            {"open": 105.3, "high": 106.0, "low": 105.2, "close": 105.8, "volume": 100},
        ]
    )

    zones = ContinuationZoneDetector().detect(df, timeframe_min=5)
    assert zones == []


def test_detect_no_zone_when_departure_fails() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.4, "high": 104.9, "low": 104.0, "close": 104.5, "volume": 100},
        ]
    )

    zones = ContinuationZoneDetector().detect(df, timeframe_min=5)
    assert zones == []


def test_invalidation_rbr() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.2, "low": 104.6, "close": 105.0, "volume": 100},
            {"open": 103.4, "high": 103.8, "low": 103.0, "close": 103.3, "volume": 100},
        ]
    )

    zone = ContinuationZoneDetector().detect(df, timeframe_min=5)[0]
    assert zone.is_active is False


def test_touch_count_increments() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.2, "low": 104.6, "close": 105.0, "volume": 100},
            {"open": 105.0, "high": 105.1, "low": 103.7, "close": 104.1, "volume": 100},
        ]
    )

    zone = ContinuationZoneDetector().detect(df, timeframe_min=5)[0]
    assert zone.touch_count == 1
    assert zone.score_freshness == 1


def test_age_expiry() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.2, "low": 104.6, "close": 105.0, "volume": 100},
            {"open": 105.3, "high": 105.7, "low": 104.9, "close": 105.4, "volume": 100},
        ]
    )

    zone = ContinuationZoneDetector(max_zone_age_bars=1).detect(df, timeframe_min=5)[0]
    assert zone.is_active is False


def test_overlap_dedup() -> None:
    df = _make_frame(
        [
            {"open": 100.0, "high": 104.2, "low": 99.8, "close": 104.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.2, "low": 104.6, "close": 105.0, "volume": 100},
            {"open": 105.0, "high": 106.2, "low": 104.8, "close": 106.0, "volume": 100},
            {"open": 104.0, "high": 104.5, "low": 103.5, "close": 104.2, "volume": 100},
            {"open": 104.6, "high": 105.1, "low": 104.6, "close": 104.9, "volume": 100},
        ]
    )

    zones = ContinuationZoneDetector().detect(df, timeframe_min=5)
    assert len(zones) == 1


def test_parity_20_examples() -> None:
    examples = [
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 6}, 10, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 2, "departure_body_to_height_bp": 0, "departure_close_extension_to_height_bp": 0, "base_candle_count": 4, "max_base_body_ratio_bp": 6000, "trend_close_side_ok": False, "trend_slope_ok": False, "zone_height_ticks": 2}, 0, {"freshness": 0, "departure": 0, "base_quality": 0, "trend_alignment": 0, "zone_height": 0}),
        ({"timeframe_min": 5, "touch_count": 1, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 9, {"freshness": 1, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 2, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 8, {"freshness": 0, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 10000, "departure_close_extension_to_height_bp": 1, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 9, {"freshness": 2, "departure": 1, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 9999, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 8, {"freshness": 2, "departure": 0, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 3, "max_base_body_ratio_bp": 5000, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 9, {"freshness": 2, "departure": 2, "base_quality": 1, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 4, "max_base_body_ratio_bp": 5000, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 4}, 8, {"freshness": 2, "departure": 2, "base_quality": 0, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": False, "zone_height_ticks": 4}, 9, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 1, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": False, "trend_slope_ok": False, "zone_height_ticks": 4}, 8, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 0, "zone_height": 2}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 3}, 9, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 1}),
        ({"timeframe_min": 5, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 13}, 8, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 0}),
        ({"timeframe_min": 15, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 6}, 10, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
        ({"timeframe_min": 15, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 5}, 9, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 1}),
        ({"timeframe_min": 15, "touch_count": 0, "departure_body_to_height_bp": 15000, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 1, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 19}, 8, {"freshness": 2, "departure": 2, "base_quality": 2, "trend_alignment": 2, "zone_height": 0}),
        ({"timeframe_min": 15, "touch_count": 1, "departure_body_to_height_bp": 10000, "departure_close_extension_to_height_bp": 1, "base_candle_count": 2, "max_base_body_ratio_bp": 3500, "trend_close_side_ok": True, "trend_slope_ok": False, "zone_height_ticks": 14}, 7, {"freshness": 1, "departure": 1, "base_quality": 2, "trend_alignment": 1, "zone_height": 2}),
        ({"timeframe_min": 15, "touch_count": 2, "departure_body_to_height_bp": 10000, "departure_close_extension_to_height_bp": 100, "base_candle_count": 3, "max_base_body_ratio_bp": 5000, "trend_close_side_ok": False, "trend_slope_ok": True, "zone_height_ticks": 18}, 4, {"freshness": 0, "departure": 1, "base_quality": 1, "trend_alignment": 1, "zone_height": 1}),
        ({"timeframe_min": 15, "touch_count": 0, "departure_body_to_height_bp": 10000, "departure_close_extension_to_height_bp": 0, "base_candle_count": 3, "max_base_body_ratio_bp": 5000, "trend_close_side_ok": False, "trend_slope_ok": False, "zone_height_ticks": 5}, 4, {"freshness": 2, "departure": 0, "base_quality": 1, "trend_alignment": 0, "zone_height": 1}),
        ({"timeframe_min": 5, "touch_count": 1, "departure_body_to_height_bp": 14999, "departure_close_extension_to_height_bp": 5000, "base_candle_count": 2, "max_base_body_ratio_bp": 3501, "trend_close_side_ok": False, "trend_slope_ok": True, "zone_height_ticks": 12}, 5, {"freshness": 1, "departure": 1, "base_quality": 1, "trend_alignment": 1, "zone_height": 1}),
        ({"timeframe_min": 15, "touch_count": 0, "departure_body_to_height_bp": 16000, "departure_close_extension_to_height_bp": 4999, "base_candle_count": 1, "max_base_body_ratio_bp": 3499, "trend_close_side_ok": True, "trend_slope_ok": True, "zone_height_ticks": 14}, 9, {"freshness": 2, "departure": 1, "base_quality": 2, "trend_alignment": 2, "zone_height": 2}),
    ]

    for kwargs, expected_total, expected_components in examples:
        total, components = score_continuation_zone(**kwargs)
        assert total == expected_total
        assert components == expected_components


def test_detect_returns_list_of_zones() -> None:
    zones = ContinuationZoneDetector().detect(_basic_rbr_frame(), timeframe_min=5)

    assert isinstance(zones, list)
    assert all(isinstance(zone, Zone) for zone in zones)


def test_entry_price_rbr() -> None:
    zone = ContinuationZoneDetector().detect(_basic_rbr_frame(), timeframe_min=5)[0]
    assert zone.entry_price == zone.bottom


def test_entry_price_dbd() -> None:
    zone = ContinuationZoneDetector().detect(_basic_dbd_frame(), timeframe_min=5)[0]
    assert zone.entry_price == zone.top
