"""Registry for macro/flow intermarket instruments.

Tracks availability and staleness for the v3 bias engine without connecting
to any broker/feed. RTH-only symbols are treated as expected stale outside
their session window so downstream checks can distinguish data loss from
normal market closure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Optional
import time
from zoneinfo import ZoneInfo


EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class IntermarketConfig:
    """Configuration for intermarket registry staleness."""

    staleness_sec: int = 300


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    rithmic_symbol: str
    exchange: str
    is_rth_only: bool
    bar_interval_sec: int
    description: str


@dataclass
class InstrumentState:
    spec: InstrumentSpec
    last_update_ts: Optional[float] = None
    last_value: Optional[float] = None
    is_connected: bool = False


def _to_ts(value: float | None = None) -> float:
    return time.time() if value is None else float(value)


def _now_et(now: float | None = None) -> datetime:
    return datetime.fromtimestamp(_to_ts(now), tz=EASTERN)


def _is_rth(now: float | None = None) -> bool:
    et = _now_et(now)
    current = et.time()
    return dt_time(9, 30) <= current < dt_time(16, 0)


class IntermarketRegistry:
    def __init__(self, staleness_sec: int = 300, config: IntermarketConfig | None = None):
        self._config = config or IntermarketConfig(staleness_sec=staleness_sec)
        self._states: dict[str, InstrumentState] = {
            "ZN": InstrumentState(
                spec=InstrumentSpec(
                    symbol="ZN",
                    rithmic_symbol="ZN_FUT",
                    exchange="CME",
                    is_rth_only=False,
                    bar_interval_sec=60,
                    description="10Y Treasury Note futures",
                )
            ),
            "DXY": InstrumentState(
                spec=InstrumentSpec(
                    symbol="DXY",
                    rithmic_symbol="DXY",
                    exchange="ICE",
                    is_rth_only=False,
                    bar_interval_sec=60,
                    description="US Dollar Index proxy",
                )
            ),
            "VIX": InstrumentState(
                spec=InstrumentSpec(
                    symbol="VIX",
                    rithmic_symbol="VIX",
                    exchange="CBOE",
                    is_rth_only=True,
                    bar_interval_sec=60,
                    description="Volatility index",
                )
            ),
            "RTY": InstrumentState(
                spec=InstrumentSpec(
                    symbol="RTY",
                    rithmic_symbol="RTY_FUT",
                    exchange="CME",
                    is_rth_only=False,
                    bar_interval_sec=60,
                    description="Russell 2000 futures",
                )
            ),
            "TICK": InstrumentState(
                spec=InstrumentSpec(
                    symbol="TICK",
                    rithmic_symbol="TICK",
                    exchange="NYSE",
                    is_rth_only=True,
                    bar_interval_sec=60,
                    description="NYSE TICK breadth",
                )
            ),
            "VOLD": InstrumentState(
                spec=InstrumentSpec(
                    symbol="VOLD",
                    rithmic_symbol="VOLD",
                    exchange="NYSE",
                    is_rth_only=True,
                    bar_interval_sec=60,
                    description="NYSE volume breadth",
                )
            ),
            "AD": InstrumentState(
                spec=InstrumentSpec(
                    symbol="AD",
                    rithmic_symbol="AD",
                    exchange="NYSE",
                    is_rth_only=True,
                    bar_interval_sec=60,
                    description="NYSE advance/decline breadth",
                )
            ),
        }

    @property
    def staleness_sec(self) -> int:
        return self._config.staleness_sec

    def get_state(self, symbol: str) -> Optional[InstrumentState]:
        return self._states.get(symbol)

    def update(self, symbol: str, value: float, ts: float | None = None) -> None:
        state = self._require_state(symbol)
        state.last_update_ts = _to_ts(ts)
        state.last_value = float(value)
        state.is_connected = True

    def is_expected_stale(self, symbol: str, now: float | None = None) -> bool:
        state = self._require_state(symbol)
        return state.spec.is_rth_only and not _is_rth(now)

    def is_stale(self, symbol: str, now: float | None = None) -> bool:
        state = self._require_state(symbol)
        if state.last_update_ts is None:
            return True
        age = _to_ts(now) - state.last_update_ts
        return age > self.staleness_sec

    def get_available_symbols(self, now: float | None = None) -> list[str]:
        now = _to_ts(now)
        return [
            symbol
            for symbol in self._states
            if not self.is_stale(symbol, now=now)
        ]

    def _require_state(self, symbol: str) -> InstrumentState:
        state = self._states.get(symbol)
        if state is None:
            raise KeyError(f"Unknown intermarket symbol: {symbol}")
        return state
