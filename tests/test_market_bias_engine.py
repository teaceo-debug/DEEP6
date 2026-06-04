from __future__ import annotations

import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from deep6.bias_engine.models import JudasStatus, PO3BiasState, PO3Phase
from deep6.engines.bias_contracts import BiasMode, BiasState
from deep6.engines.intermarket_registry import IntermarketRegistry
from deep6.engines.kronos_bias import KronosBias
from deep6.engines.market_bias_engine import BIAS_LABELS, MarketBiasEngine
from deep6.engines.ohlcv_accumulator import OHLCVBar

ET = ZoneInfo("America/New_York")


def _et(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 12, hour, minute, tzinfo=ET)


def _bar(symbol: str, open_: float, close: float, volume: float = 100.0) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        open=open_,
        high=max(open_, close),
        low=min(open_, close),
        close=close,
        volume=volume,
        bar_start_ts=1_000.0,
        bar_end_ts=1_060.0,
        tick_count=10,
    )


def _registry() -> IntermarketRegistry:
    registry = IntermarketRegistry(staleness_sec=300)
    now = time.time()
    for symbol in ("ZN", "DXY", "VIX"):
        registry.update(symbol, value=1.0, ts=now)
    return registry


def _po3_bull() -> PO3BiasState:
    return PO3BiasState(
        above_midnight_open=True,
        above_weekly_open=True,
        in_discount=True,
        judas_status=JudasStatus.BULL_CONFIRMED,
        phase=PO3Phase.DISTRIBUTION,
        pd_high=20_200.0,
        pd_low=20_050.0,
        asia_high=20_150.0,
        asia_low=20_000.0,
        timestamp=datetime.now(tz=timezone.utc),
    )


def _kronos_bull(confidence: float = 85.0) -> KronosBias:
    return KronosBias(
        direction=1,
        confidence=confidence,
        predicted_close=20_220.0,
        current_close=20_100.0,
        samples=20,
        inference_time_ms=20.0,
        bars_since_inference=0,
        detail="bull",
    )


def test_cold_start_returns_neutral_and_caution() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias()

    assert snapshot.bias_state is BiasState.NEUTRAL
    assert snapshot.bias_label == "NEUTRAL"
    assert snapshot.mode == BiasMode.CAUTION.value
    assert snapshot.mode_reason == "Cold start"
    assert snapshot.bias_score == 0


def test_full_bullish_pipeline_returns_strong_bull_and_go() -> None:
    engine = MarketBiasEngine()
    bars = {
        "ZN": _bar("ZN", 110.0, 111.0, volume=1500.0),
        "DXY": _bar("DXY", 105.0, 104.0, volume=1500.0),
        "VIX": _bar("VIX", 19.5, 19.0, volume=1500.0),
    }

    snapshot = engine.compute_bias(
        po3_state=_po3_bull(),
        intermarket_bars=bars,
        intermarket_registry=_registry(),
        tick_value=1_200,
        cvd_slope=75.0,
        price=20_052.0,
        vwap=20_040.0,
        kronos_bias=_kronos_bull(),
        kronos_ts=time.time(),
        now_et=_et(10, 0),
        vix_level=18.0,
    )

    assert snapshot.bias_state is BiasState.STRONG_BULL
    assert snapshot.bias_label == "STRONG BULL"
    assert snapshot.mode == BiasMode.GO.value
    assert snapshot.mode_reason == "All clear"
    # 5 domains: ICT(4) + Macro(3) + Flow(2) + Kronos(3) + GEX(0, unavailable) = 12
    # GEX unavailable (no snapshot) but other 4 domains contribute max scores
    assert snapshot.bias_score == 12


def test_event_day_forces_stop_mode() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias(
        po3_state=_po3_bull(),
        intermarket_bars={"ZN": _bar("ZN", 110.0, 111.0), "DXY": _bar("DXY", 105.0, 104.0), "VIX": _bar("VIX", 19.5, 19.0)},
        intermarket_registry=_registry(),
        tick_value=1_000,
        cvd_slope=70.0,
        price=20_060.0,
        vwap=20_040.0,
        kronos_bias=_kronos_bull(),
        kronos_ts=time.time(),
        now_et=_et(10, 15),
        vix_level=18.0,
        event_day=True,
    )

    assert snapshot.bias_state is BiasState.STRONG_BULL
    assert snapshot.mode == BiasMode.STOP.value
    assert snapshot.mode_reason == "Event day"


def test_bias_label_strings_cover_all_states() -> None:
    expected = {
        BiasState.STRONG_BEAR: "STRONG BEAR",
        BiasState.LEAN_BEAR: "LEAN BEAR",
        BiasState.NEUTRAL: "NEUTRAL",
        BiasState.LEAN_BULL: "LEAN BULL",
        BiasState.STRONG_BULL: "STRONG BULL",
    }

    assert BIAS_LABELS == expected


def test_session_label_a_plus_open() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias(now_et=_et(9, 45))

    assert snapshot.session_label == "A+ OPEN"


def test_session_label_lunch() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias(now_et=_et(12, 15))

    assert snapshot.session_label == "LUNCH"


def test_xamd_phase_uses_po3_phase_value() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias(po3_state=_po3_bull())

    assert snapshot.xamd_phase == "DISTRIBUTION"


def test_kronos_confidence_is_normalized_to_zero_one() -> None:
    engine = MarketBiasEngine()

    snapshot = engine.compute_bias(kronos_bias=_kronos_bull(confidence=72.0), kronos_ts=time.time())

    assert snapshot.kronos_confidence == 0.72


def test_hysteresis_stabilizes_follow_up_score() -> None:
    engine = MarketBiasEngine()
    bars = {
        "ZN": _bar("ZN", 110.0, 111.0),
        "DXY": _bar("DXY", 104.0, 105.0),
        "VIX": _bar("VIX", 22.0, 22.0),
    }
    registry = _registry()
    first = engine.compute_bias(
        po3_state=_po3_bull(),
        intermarket_bars=bars,
        intermarket_registry=registry,
        tick_value=None,
        cvd_slope=None,
        price=20_050.0,
        vwap=20_050.0,
        kronos_bias=None,
        now_et=_et(10, 0),
        vix_level=18.0,
    )
    second = engine.compute_bias(
        po3_state=_po3_bull(),
        intermarket_bars={"ZN": _bar("ZN", 111.0, 110.0), "DXY": _bar("DXY", 105.0, 105.0), "VIX": _bar("VIX", 22.0, 22.0)},
        intermarket_registry=registry,
        tick_value=None,
        cvd_slope=None,
        price=20_050.0,
        vwap=20_050.0,
        kronos_bias=None,
        now_et=_et(10, 5),
        vix_level=18.0,
    )

    assert first.bias_score == 4
    assert first.bias_state is BiasState.LEAN_BULL
    assert second.bias_score == 3
    assert second.bias_state is BiasState.LEAN_BULL
