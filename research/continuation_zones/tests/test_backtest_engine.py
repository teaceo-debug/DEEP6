from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import pytest

from research.continuation_zones.backtest_engine import BacktestConfig, BacktestEngine
from research.continuation_zones.continuation_zones import Zone


def _make_frame(rows: list[dict[str, float]], freq: str, start: str) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(rows), freq=freq, tz="UTC", name="ts_event")
    frame = pd.DataFrame(rows, index=index)
    if "volume" not in frame.columns:
        frame["volume"] = 100
    return frame[["open", "high", "low", "close", "volume"]]


def _make_5m_frame(rows: list[dict[str, float]], start: str = "2026-01-05 14:30:00+00:00") -> pd.DataFrame:
    return _make_frame(rows, "5min", start)


def _make_15m_frame(rows: list[dict[str, float]], start: str = "2026-01-05 14:30:00+00:00") -> pd.DataFrame:
    return _make_frame(rows, "15min", start)


def _make_zone(
    *,
    kind: str,
    timeframe_min: int,
    created_bar_idx: int = 1,
    top: float,
    bottom: float,
    score: int = 10,
) -> Zone:
    return Zone(
        kind=kind,
        timeframe_min=timeframe_min,
        top=top,
        bottom=bottom,
        entry_price=bottom if kind == "RBR" else top,
        created_bar_idx=created_bar_idx,
        created_at=pd.Timestamp("2026-01-05 14:35:00+00:00"),
        score=score,
        score_freshness=2,
        score_departure=2,
        score_base=2,
        score_trend=2,
        score_height=2,
        departure_body_bp=15000,
        departure_ext_bp=5000,
        base_body_bp=3000,
        zone_height_ticks=int(round((top - bottom) / 0.25)),
        trend_close_ok=True,
        trend_slope_ok=True,
    )


def _patch_detect(monkeypatch: pytest.MonkeyPatch, zones_5m: list[Zone], zones_15m: list[Zone] | None = None) -> None:
    zones_15m = zones_15m or []

    def fake_detect(self, df: pd.DataFrame, timeframe_min: int) -> list[Zone]:
        return zones_5m if timeframe_min == 5 else zones_15m

    monkeypatch.setattr("research.continuation_zones.backtest_engine.ContinuationZoneDetector.detect", fake_detect)


def test_rbr_target_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.25, "low": 101.25, "close": 101.75},
            {"open": 101.75, "high": 105.75, "low": 101.5, "close": 105.5},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "target"
    assert trade.direction == "long"
    assert trade.pnl_ticks > 0


def test_rbr_stop_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.25, "low": 101.25, "close": 101.75},
            {"open": 101.75, "high": 101.9, "low": 98.5, "close": 99.0},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "stop"
    assert trade.direction == "long"
    assert trade.pnl_ticks < 0


def test_dbd_target_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="DBD", timeframe_min=5, top=103.00, bottom=102.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 104.5, "high": 105.0, "low": 104.0, "close": 104.25},
            {"open": 104.25, "high": 104.5, "low": 103.75, "close": 104.0},
            {"open": 104.0, "high": 103.5, "low": 101.5, "close": 102.0},
            {"open": 102.0, "high": 103.25, "low": 101.75, "close": 102.8},
            {"open": 102.8, "high": 103.1, "low": 98.5, "close": 99.0},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "target"
    assert trade.direction == "short"
    assert trade.pnl_ticks > 0


def test_breakeven_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.25, "low": 101.4, "close": 101.9},
            {"open": 101.9, "high": 103.1, "low": 101.75, "close": 102.5},
            {"open": 102.5, "high": 102.75, "low": 101.5, "close": 101.75},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "stop"
    assert trade.exit_price == trade.entry_price
    assert trade.mfe_ticks >= 6


def test_no_data_leakage(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 101.25, "close": 102.0},
            {"open": 102.0, "high": 102.2, "low": 101.4, "close": 101.8},
            {"open": 101.8, "high": 105.75, "low": 101.5, "close": 105.5},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    assert trades[0].entry_time == df_5m.index[3]


def test_one_position_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    higher_score = _make_zone(kind="DBD", timeframe_min=15, created_bar_idx=0, top=103.00, bottom=102.50, score=10)
    lower_score = _make_zone(kind="DBD", timeframe_min=5, top=102.75, bottom=102.25, score=8)
    _patch_detect(monkeypatch, [lower_score], [higher_score])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 101.5, "low": 100.25, "close": 101.0},
            {"open": 101.0, "high": 103.1, "low": 100.8, "close": 102.7},
            {"open": 102.7, "high": 102.9, "low": 101.8, "close": 102.2},
            {"open": 102.2, "high": 102.4, "low": 101.7, "close": 102.0},
        ]
    )
    df_15m = _make_15m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.2, "low": 101.2, "close": 101.8},
        ],
        start="2026-01-05 14:00:00+00:00",
    )

    trades = BacktestEngine(BacktestConfig(stop_ticks=20, target_ticks=40, rth_only=False)).run(df_5m, df_15m)

    assert len(trades) == 1
    assert trades[0].zone_timeframe == 15


def test_slippage_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.25, "low": 101.25, "close": 101.75},
            {"open": 101.75, "high": 105.75, "low": 101.5, "close": 105.5},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trade = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)[0]

    assert trade.pnl_ticks == pytest.approx(14.0)
    assert trade.pnl_dollars == pytest.approx(66.0)


def test_session_end_close(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.2, "low": 101.4, "close": 101.8},
            {"open": 101.8, "high": 102.25, "low": 101.5, "close": 101.75},
        ],
        start="2026-01-05 20:35:00+00:00",
    )
    df_15m = _make_15m_frame(
        [{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4,
        start="2026-01-05 19:45:00+00:00",
    )

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert len(trades) == 1
    assert trades[0].exit_reason == "session_end"
    assert trades[0].exit_time == df_5m.index[-1]


def test_empty_result_no_zones(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_detect(monkeypatch, [])
    df_5m = _make_5m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 5)
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trades = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)

    assert trades == []


def test_trade_fields_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    zone = _make_zone(kind="RBR", timeframe_min=5, top=102.00, bottom=101.50)
    _patch_detect(monkeypatch, [zone])
    df_5m = _make_5m_frame(
        [
            {"open": 100.0, "high": 100.5, "low": 99.75, "close": 100.25},
            {"open": 100.25, "high": 100.75, "low": 100.0, "close": 100.5},
            {"open": 100.5, "high": 102.5, "low": 100.5, "close": 102.0},
            {"open": 102.0, "high": 102.25, "low": 101.25, "close": 101.75},
            {"open": 101.75, "high": 105.75, "low": 101.5, "close": 105.5},
        ]
    )
    df_15m = _make_15m_frame([{"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5}] * 4)

    trade = BacktestEngine(BacktestConfig()).run(df_5m, df_15m)[0]

    for key, value in asdict(trade).items():
        assert value is not None, key
