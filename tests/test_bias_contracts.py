from __future__ import annotations

import time
from dataclasses import asdict

from deep6.engines.bias_contracts import (
    BiasComponentState,
    BiasMode,
    BiasState,
    DomainScore,
    MarketBiasSnapshot,
)
from deep6.engines.signal_config import (
    BiasHysteresisConfig,
    IntermarketConfig,
    KillSwitchConfig,
    KronosDomainConfig,
)


def test_bias_state_values() -> None:
    assert [state.value for state in BiasState] == [-2, -1, 0, 1, 2]


def test_contract_instantiation() -> None:
    domain = DomainScore(
        domain="flow",
        score=1,
        max_range=2,
        available=True,
        stale=False,
        detail={"delta": 12},
        updated_at=time.time(),
    )
    component = BiasComponentState(
        ict_score=1,
        macro_score=0,
        flow_score=1,
        kronos_score=0,
        gex_score=0,
        total_score=2,
        confidence=0.75,
        setup_quality=4,
        bias_state=BiasState.LEAN_BULL,
        mode=BiasMode.GO.value,
        reason="aligned",
    )
    snapshot = MarketBiasSnapshot(
        symbol="NQ",
        asof_ts=time.time(),
        bias_label="LEAN BULL",
        bias_state=BiasState.LEAN_BULL,
        bias_score=2,
        confidence=0.75,
        setup_quality=4,
        mode=BiasMode.GO.value,
        mode_reason="domains aligned",
        session_label="MID-AM",
        xamd_phase="BETWEEN",
        intermarket_alignment=0.25,
        kronos_confidence=0.6,
        nearest_support=16000.0,
        nearest_resistance=16100.0,
        domain_detail={"flow": asdict(domain)},
        meta={"component": asdict(component)},
    )

    assert snapshot.symbol == "NQ"
    assert snapshot.bias_state is BiasState.LEAN_BULL
    assert snapshot.mode == BiasMode.GO.value


def test_bias_hysteresis_defaults() -> None:
    cfg = BiasHysteresisConfig()
    assert cfg.enter_strong_threshold == 7
    assert cfg.degrade_strong_threshold == 4
    assert cfg.enter_lean_threshold == 3
    assert cfg.degrade_lean_threshold == 1
    assert cfg.emergency_delta == 10


def test_append_only_config_defaults() -> None:
    assert KillSwitchConfig().event_day_mode == "STOP"
    assert IntermarketConfig().staleness_sec == 300
    assert IntermarketConfig().symbols == ("ZN", "DXY", "VIX", "RTY", "TICK", "VOLD", "AD")
    assert KronosDomainConfig().max_range == 3
