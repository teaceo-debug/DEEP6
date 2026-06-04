"""NQ ATLAS test fixtures."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from nq_atlas.types import (
    BiasDirection, BiasOutput, ChainSnapshot, FlowResult,
    GEXResult, NQLevels, OptionsContract, VannaCharmResult,
)
from nq_atlas.state import AtlasState


def _tomorrow_str() -> str:
    return (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')


@pytest.fixture
def tomorrow_expiry() -> str:
    return _tomorrow_str()


@pytest.fixture
def sample_chain(tomorrow_expiry) -> ChainSnapshot:
    """20-contract QQQ chain with full Greeks."""
    contracts = []
    spot = 520.0
    for i, strike in enumerate([505, 510, 515, 520, 525, 530, 535, 540, 545, 550]):
        contracts.append(OptionsContract(
            symbol="QQQ", strike=float(strike), expiry=tomorrow_expiry,
            call_put="call", gamma=0.005, delta=0.5, iv=0.20,
            oi=1000 + i*100, bid=5.0, ask=5.2, last=5.1, volume=50,
        ))
        contracts.append(OptionsContract(
            symbol="QQQ", strike=float(strike), expiry=tomorrow_expiry,
            call_put="put", gamma=0.005, delta=-0.5, iv=0.20,
            oi=800 + i*80, bid=4.8, ask=5.0, last=4.9, volume=40,
        ))
    return ChainSnapshot(
        underlying="QQQ", spot_price=spot,
        timestamp=datetime.now(timezone.utc), contracts=contracts
    )


@pytest.fixture
def fresh_state() -> AtlasState:
    return AtlasState(refresh_interval_sec=10)


@pytest.fixture
def populated_state(sample_chain) -> AtlasState:
    import time
    state = AtlasState(refresh_interval_sec=10)
    state.chain = sample_chain
    state.spots = {"QQQ": 520.0, "NQ": 21240.0}
    state.last_chain_ts = time.time()
    return state
