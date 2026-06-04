# Python Signal Templates

Reusable base classes and patterns for options-derived signals in the DEEP6 44-signal engine.

Theory for GEX regimes, walls, and flow states lives in `options-bias-engine/`. This file is
purely about the code interface: how to build a signal, register it, test it, and maintain state.

---

## Core Data Contracts

```python
# deep6/signals/options/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class SignalCategory(str, Enum):
    GEX = "gex"
    FLOW = "flow"
    VOLATILITY = "volatility"
    DOM = "dom"
    MICROSTRUCTURE = "microstructure"


@dataclass(frozen=True)
class SignalResult:
    """
    Canonical output from any signal in the 44-signal engine.

    value:      -1.0 (max bearish) to +1.0 (max bullish). 0.0 = neutral.
    confidence: 0.0 (no confidence) to 1.0 (maximum confidence).
                Multiplied against signal weight during aggregation.
    metadata:   Arbitrary dict for debugging, logging, and downstream context.
                Never used in score computation — only for observability.
    timestamp:  Unix epoch float. Set by the signal, not the engine.
    """
    value: float
    confidence: float
    metadata: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"SignalResult.value must be in [-1, 1], got {self.value}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"SignalResult.confidence must be in [0, 1], got {self.confidence}")

    @property
    def weighted_value(self) -> float:
        """Value scaled by confidence. Used by the aggregator."""
        return self.value * self.confidence


@dataclass
class OptionsState:
    """
    Snapshot of all options-derived data available to signals.

    Populated by the data fusion layer (see data-sources/data-fusion.md).
    Signals receive this as their primary input — they never call APIs directly.
    """
    # FlashAlpha exposure
    gamma_flip: float           # NQ-adjusted gamma flip level
    call_wall: float            # NQ-adjusted call wall
    put_wall: float             # NQ-adjusted put wall
    net_gex: float              # Net GEX in $ billions
    net_dex: float              # Net DEX in $ billions
    net_vex: float              # Net VEX in $ billions
    net_chex: float             # Net CHEX in $ billions
    regime_label: str           # "A" through "G" from FlashAlpha interpretation
    dte_magnet: float | None    # 0DTE magnet strike (NQ-adjusted), None if not 0DTE day

    # Current market
    nq_price: float             # Current NQ futures price
    nq_velocity: float          # Price change per second (rolling 30s)
    iv_rank: float              # IV rank 0-100 from FlashAlpha
    vix: float                  # VIX spot

    # Flow state (from Massive.com / Unusual Whales)
    net_premium_5m: float       # Net options premium flow, last 5 minutes ($M)
    net_premium_1h: float       # Net options premium flow, last 1 hour ($M)
    sweep_count_bullish: int    # Bullish sweeps in last 15 min
    sweep_count_bearish: int    # Bearish sweeps in last 15 min
    dark_pool_direction: float  # -1.0 to +1.0 from dark pool prints

    # Timestamps
    flashalpha_age_sec: float   # Seconds since last FlashAlpha poll
    flow_age_sec: float         # Seconds since last flow poll

    # GEX by strike (optional — only populated when profile analysis is needed)
    gex_by_strike: dict[float, float] = field(default_factory=dict)
```

---

## BaseOptionsSignal

```python
# deep6/signals/options/base.py
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory

logger = logging.getLogger(__name__)


class BaseOptionsSignal(ABC):
    """
    Abstract base for all options-derived signals in the 44-signal engine.

    Subclass this, implement `compute()`, and register via SignalRegistry.

    Threading model:
        All signals run in the asyncio event loop. If your signal needs CPU-heavy
        computation (e.g., SVI fitting, profile shape FFT), offload to a
        ThreadPoolExecutor via asyncio.get_event_loop().run_in_executor().
        Never block the event loop directly.

    State management:
        Signals may maintain inter-tick state as instance attributes.
        The engine calls `compute()` on every options state update (typically
        every 30-60 seconds from FlashAlpha polling). State persists across calls.
        Use `_last_result` to cache the previous result for staleness checks.
    """

    # Class-level constants — override in subclass
    signal_name: ClassVar[str]
    signal_weight: ClassVar[float]   # 0.0 to 1.0, relative weight within category
    category: ClassVar[SignalCategory]
    max_data_age_sec: ClassVar[float] = 120.0  # Reject stale data beyond this

    def __init__(self) -> None:
        self._last_result: SignalResult | None = None
        self._compute_count: int = 0
        self._error_count: int = 0

    @abstractmethod
    async def compute(self, state: OptionsState) -> SignalResult:
        """
        Compute signal value from current options state.

        Must return a SignalResult. Never raise — catch exceptions internally
        and return a neutral result with confidence=0.0 on failure.
        """
        ...

    async def safe_compute(self, state: OptionsState) -> SignalResult:
        """
        Wrapper that handles staleness checks and exception safety.
        The engine calls this, not compute() directly.
        """
        # Reject stale data
        if state.flashalpha_age_sec > self.max_data_age_sec:
            logger.warning(
                "%s: FlashAlpha data is %.0fs old (max %.0fs), returning neutral",
                self.signal_name, state.flashalpha_age_sec, self.max_data_age_sec
            )
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "stale_data"})

        try:
            result = await self.compute(state)
            self._last_result = result
            self._compute_count += 1
            return result
        except Exception as exc:
            self._error_count += 1
            logger.exception("%s: compute() raised %s", self.signal_name, exc)
            # Return last known result at reduced confidence, or neutral
            if self._last_result is not None:
                return SignalResult(
                    value=self._last_result.value,
                    confidence=self._last_result.confidence * 0.5,
                    metadata={"reason": "compute_error", "error": str(exc)},
                )
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "compute_error"})

    @property
    def stats(self) -> dict[str, int]:
        return {"compute_count": self._compute_count, "error_count": self._error_count}
```

---

## Concrete Example: GEXRegimeSignal

```python
# deep6/signals/options/gex_regime.py
from __future__ import annotations

import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory

# Regime value map: how bullish/bearish each regime is by default.
# Regime G (pre-event) returns 0.0 — no directional bias.
# See options-bias-engine/step1-regimes/ for full regime theory.
_REGIME_BASE_VALUE: dict[str, float] = {
    "A": 0.0,    # Positive gamma, between walls — neutral, mean-reverting
    "B": -0.3,   # At call wall — mild bearish (ceiling test)
    "C": 0.5,    # At put wall — bullish (floor, highest win-rate long)
    "D": 0.2,    # Negative gamma above flip — cautious bullish
    "E": -0.6,   # Negative gamma below flip — bearish, trend mode
    "F": 0.0,    # Pin regime — no directional bias
    "G": 0.0,    # Pre-event — suppressed
}

_REGIME_CONFIDENCE: dict[str, float] = {
    "A": 0.7,
    "B": 0.65,
    "C": 0.80,
    "D": 0.55,
    "E": 0.75,
    "F": 0.60,
    "G": 0.20,   # Low confidence — pre-event noise
}


class GEXRegimeSignal(BaseOptionsSignal):
    """
    Translates the current GEX regime (A-G) into a directional signal value.

    Regime duration bonus: a regime that has persisted for 30+ minutes gets
    a confidence boost (established regime vs fresh transition).

    State maintained:
        _regime_entry_time: when the current regime was first detected
        _last_regime: previous regime label (for transition detection)
    """

    signal_name: ClassVar[str] = "gex_regime"
    signal_weight: ClassVar[float] = 0.20
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    def __init__(self) -> None:
        super().__init__()
        self._regime_entry_time: float = time.time()
        self._last_regime: str | None = None

    async def compute(self, state: OptionsState) -> SignalResult:
        regime = state.regime_label.upper()

        # Track regime duration
        if regime != self._last_regime:
            self._regime_entry_time = time.time()
            self._last_regime = regime

        regime_duration_min = (time.time() - self._regime_entry_time) / 60.0

        base_value = _REGIME_BASE_VALUE.get(regime, 0.0)
        base_confidence = _REGIME_CONFIDENCE.get(regime, 0.5)

        # Confidence bonus for established regimes (up to +0.15 after 45 min)
        duration_bonus = min(0.15, regime_duration_min / 300.0)
        # Confidence penalty for very fresh transitions (first 5 min)
        transition_penalty = max(0.0, 0.10 - regime_duration_min / 50.0)

        final_confidence = min(1.0, base_confidence + duration_bonus - transition_penalty)

        # Regime G: suppress everything
        if regime == "G":
            final_confidence = 0.15

        return SignalResult(
            value=base_value,
            confidence=final_confidence,
            metadata={
                "regime": regime,
                "duration_min": round(regime_duration_min, 1),
                "duration_bonus": round(duration_bonus, 3),
                "transition_penalty": round(transition_penalty, 3),
                "gamma_flip": state.gamma_flip,
                "nq_price": state.nq_price,
            },
        )
```

---

## Concrete Example: WallProximitySignal

```python
# deep6/signals/options/wall_proximity.py
from __future__ import annotations

from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory


class WallProximitySignal(BaseOptionsSignal):
    """
    Scores proximity to call/put walls and translates it into a directional signal.

    Logic:
        - Near call wall → bearish signal (resistance, dealers sell into it)
        - Near put wall → bullish signal (support, dealers buy into it)
        - Between walls → neutral
        - Beyond a wall (break) → strong directional signal in break direction

    Proximity threshold: configurable, default 0.3% of NQ price (~6 NQ points at 20,000).
    """

    signal_name: ClassVar[str] = "wall_proximity"
    signal_weight: ClassVar[float] = 0.15
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    def __init__(self, proximity_pct: float = 0.003) -> None:
        super().__init__()
        self.proximity_pct = proximity_pct  # 0.3% default

    async def compute(self, state: OptionsState) -> SignalResult:
        price = state.nq_price
        call_wall = state.call_wall
        put_wall = state.put_wall

        threshold = price * self.proximity_pct

        # Distance to each wall (positive = below wall, negative = above wall)
        dist_to_call = call_wall - price   # positive = price below call wall
        dist_to_put = price - put_wall     # positive = price above put wall

        # Determine which wall is closer
        at_call_wall = 0.0 < dist_to_call <= threshold
        above_call_wall = dist_to_call < 0  # broken through
        at_put_wall = 0.0 < dist_to_put <= threshold
        below_put_wall = dist_to_put < 0    # broken through

        if above_call_wall:
            # Price broke above call wall — strong bullish (wall break)
            penetration = abs(dist_to_call) / threshold
            value = min(1.0, 0.6 + penetration * 0.4)
            confidence = 0.75
            wall_state = "above_call_wall"
        elif at_call_wall:
            # Approaching call wall — bearish (expect rejection)
            proximity_ratio = 1.0 - (dist_to_call / threshold)
            value = -(0.3 + proximity_ratio * 0.4)
            confidence = 0.65 + proximity_ratio * 0.15
            wall_state = "at_call_wall"
        elif below_put_wall:
            # Price broke below put wall — strong bearish
            penetration = abs(dist_to_put) / threshold
            value = -min(1.0, 0.6 + penetration * 0.4)
            confidence = 0.75
            wall_state = "below_put_wall"
        elif at_put_wall:
            # Approaching put wall — bullish (expect support)
            proximity_ratio = 1.0 - (dist_to_put / threshold)
            value = 0.3 + proximity_ratio * 0.4
            confidence = 0.70 + proximity_ratio * 0.15
            wall_state = "at_put_wall"
        else:
            # Between walls — neutral
            # Slight lean based on relative position within the range
            wall_range = call_wall - put_wall
            if wall_range > 0:
                position_in_range = (price - put_wall) / wall_range
                value = (position_in_range - 0.5) * 0.2  # -0.1 to +0.1
            else:
                value = 0.0
            confidence = 0.40
            wall_state = "between_walls"

        return SignalResult(
            value=round(value, 4),
            confidence=round(confidence, 4),
            metadata={
                "wall_state": wall_state,
                "call_wall": call_wall,
                "put_wall": put_wall,
                "dist_to_call": round(dist_to_call, 2),
                "dist_to_put": round(dist_to_put, 2),
                "threshold_pts": round(threshold, 2),
                "regime": state.regime_label,
            },
        )
```

---

## Signal Registration

```python
# deep6/signals/options/registry.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deep6.signals.options.base import BaseOptionsSignal


class OptionsSignalRegistry:
    """
    Central registry for all options-derived signals.

    The 44-signal engine queries this registry to discover which signals
    belong to the options category and what their weights are.

    Usage:
        registry = OptionsSignalRegistry()
        registry.register(GEXRegimeSignal())
        registry.register(WallProximitySignal())

        # Engine calls this on each state update
        results = await registry.compute_all(options_state)
    """

    def __init__(self) -> None:
        self._signals: list[BaseOptionsSignal] = []

    def register(self, signal: BaseOptionsSignal) -> None:
        self._signals.append(signal)

    async def compute_all(
        self, state: OptionsState
    ) -> dict[str, SignalResult]:
        """
        Run all registered signals concurrently.
        Returns dict keyed by signal_name.
        """
        import asyncio
        from deep6.signals.options.types import OptionsState  # noqa: F401

        tasks = {
            sig.signal_name: sig.safe_compute(state)
            for sig in self._signals
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=False)
        return dict(zip(tasks.keys(), results))

    @property
    def total_weight(self) -> float:
        return sum(s.signal_weight for s in self._signals)

    def summary(self) -> list[dict]:
        return [
            {
                "name": s.signal_name,
                "weight": s.signal_weight,
                "category": s.category.value,
                **s.stats,
            }
            for s in self._signals
        ]


# Default registry — import and use this in the engine
def build_default_registry() -> OptionsSignalRegistry:
    from deep6.signals.options.gex_regime import GEXRegimeSignal
    from deep6.signals.options.wall_proximity import WallProximitySignal
    from deep6.signals.options.gex_flip_distance import GEXFlipDistanceSignal
    from deep6.signals.options.flow_state import FlowStateSignal
    from deep6.signals.options.sweep_momentum import SweepMomentumSignal

    registry = OptionsSignalRegistry()
    registry.register(GEXRegimeSignal())
    registry.register(WallProximitySignal())
    registry.register(GEXFlipDistanceSignal())
    registry.register(FlowStateSignal())
    registry.register(SweepMomentumSignal())
    return registry
```

---

## Threading Model

```python
# deep6/signals/options/threading_example.py
"""
Pattern for offloading CPU-heavy signal computation to a thread pool
without blocking the asyncio event loop.

Use this when a signal needs:
  - NumPy/SciPy fitting (e.g., SVI surface fitting)
  - Profile shape analysis (FFT, clustering)
  - Any computation > ~0.5ms

Kronos inference always uses this pattern (see STACK.md).
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import numpy as np

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory

# Module-level executor — shared across all CPU-heavy signals
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="options-signal")


def _compute_profile_shape_sync(gex_by_strike: dict[float, float]) -> dict:
    """
    CPU-bound: runs in thread pool, not event loop.
    Returns serializable dict (no asyncio objects).
    """
    if not gex_by_strike:
        return {"shape": "unknown", "skew": 0.0}

    strikes = np.array(sorted(gex_by_strike.keys()))
    values = np.array([gex_by_strike[k] for k in strikes])

    total = np.sum(np.abs(values))
    if total == 0:
        return {"shape": "flat", "skew": 0.0}

    # Weighted center of mass
    center = np.sum(strikes * np.abs(values)) / total
    # Skew: positive = call-heavy, negative = put-heavy
    skew = float(np.sum(values) / total)

    if abs(skew) < 0.1:
        shape = "symmetric"
    elif skew > 0.3:
        shape = "skewed_call"
    elif skew < -0.3:
        shape = "skewed_put"
    else:
        shape = "mild_skew"

    return {"shape": shape, "skew": round(skew, 4), "center": round(float(center), 2)}


class GEXProfileShapeSignal(BaseOptionsSignal):
    """
    Analyzes the GEX strike profile shape for structural skew.
    CPU-heavy — offloaded to thread pool.
    """

    signal_name: ClassVar[str] = "gex_profile_shape"
    signal_weight: ClassVar[float] = 0.08
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    async def compute(self, state: OptionsState) -> SignalResult:
        if not state.gex_by_strike:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "no_profile_data"})

        loop = asyncio.get_event_loop()
        profile = await loop.run_in_executor(
            _executor,
            _compute_profile_shape_sync,
            state.gex_by_strike,
        )

        shape = profile["shape"]
        skew = profile["skew"]

        # Skewed call profile → bullish structural bias
        # Skewed put profile → bearish structural bias
        value = max(-1.0, min(1.0, skew * 1.5))
        confidence = 0.55 if shape in ("symmetric", "flat") else 0.70

        return SignalResult(
            value=round(value, 4),
            confidence=confidence,
            metadata=profile,
        )
```

---

## State Management Pattern

```python
# deep6/signals/options/stateful_example.py
"""
Pattern for signals that need to track history across ticks.

Examples:
  - Regime duration (how long have we been in regime E?)
  - Sweep escalation rate (are sweeps accelerating?)
  - Wall approach velocity (how fast is price moving toward the call wall?)
"""
from __future__ import annotations

import collections
import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory


class WallApproachVelocitySignal(BaseOptionsSignal):
    """
    Measures how fast price is approaching the nearest wall.

    A fast approach to the call wall is more bearish than a slow drift.
    A fast approach to the put wall is more bullish (strong buying).

    State: rolling deque of (timestamp, price) tuples.
    """

    signal_name: ClassVar[str] = "wall_approach_velocity"
    signal_weight: ClassVar[float] = 0.07
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    def __init__(self, history_sec: float = 120.0) -> None:
        super().__init__()
        self.history_sec = history_sec
        self._price_history: collections.deque[tuple[float, float]] = collections.deque()

    async def compute(self, state: OptionsState) -> SignalResult:
        now = time.time()
        self._price_history.append((now, state.nq_price))

        # Prune old entries
        cutoff = now - self.history_sec
        while self._price_history and self._price_history[0][0] < cutoff:
            self._price_history.popleft()

        if len(self._price_history) < 3:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "insufficient_history"})

        oldest_t, oldest_p = self._price_history[0]
        elapsed = now - oldest_t
        if elapsed < 10.0:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "too_short_window"})

        velocity_pts_per_min = (state.nq_price - oldest_p) / (elapsed / 60.0)

        # Positive velocity = moving up (toward call wall)
        # Negative velocity = moving down (toward put wall)
        call_dist = state.call_wall - state.nq_price
        put_dist = state.nq_price - state.put_wall

        # Normalize velocity by wall distance
        if velocity_pts_per_min > 0 and call_dist > 0:
            # Moving toward call wall — bearish signal
            approach_rate = velocity_pts_per_min / max(call_dist, 1.0)
            value = -min(1.0, approach_rate * 5.0)
            confidence = min(0.80, 0.40 + abs(approach_rate) * 2.0)
        elif velocity_pts_per_min < 0 and put_dist > 0:
            # Moving toward put wall — bullish signal
            approach_rate = abs(velocity_pts_per_min) / max(put_dist, 1.0)
            value = min(1.0, approach_rate * 5.0)
            confidence = min(0.80, 0.40 + abs(approach_rate) * 2.0)
        else:
            value = 0.0
            confidence = 0.30

        return SignalResult(
            value=round(value, 4),
            confidence=round(confidence, 4),
            metadata={
                "velocity_pts_per_min": round(velocity_pts_per_min, 2),
                "history_points": len(self._price_history),
                "window_sec": round(elapsed, 1),
                "call_dist": round(call_dist, 2),
                "put_dist": round(put_dist, 2),
            },
        )
```

---

## Unit Test Template

```python
# tests/signals/options/test_wall_proximity.py
"""
Template for testing options signals.

Key principles:
  - Test boundary conditions (at wall, just inside, just outside)
  - Test stale data rejection
  - Test exception safety (safe_compute never raises)
  - Test state persistence across calls
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from deep6.signals.options.wall_proximity import WallProximitySignal
from deep6.signals.options.types import OptionsState


def make_state(**overrides) -> OptionsState:
    """Factory for test OptionsState with sensible NQ defaults."""
    defaults = dict(
        gamma_flip=20_000.0,
        call_wall=20_200.0,
        put_wall=19_800.0,
        net_gex=2.5,
        net_dex=0.8,
        net_vex=0.3,
        net_chex=0.1,
        regime_label="A",
        dte_magnet=None,
        nq_price=20_050.0,
        nq_velocity=0.5,
        iv_rank=35.0,
        vix=18.5,
        net_premium_5m=12.0,
        net_premium_1h=45.0,
        sweep_count_bullish=3,
        sweep_count_bearish=1,
        dark_pool_direction=0.2,
        flashalpha_age_sec=15.0,
        flow_age_sec=8.0,
        gex_by_strike={},
    )
    defaults.update(overrides)
    return OptionsState(**defaults)


class TestWallProximitySignal:
    def setup_method(self):
        self.signal = WallProximitySignal(proximity_pct=0.003)

    def test_between_walls_neutral(self):
        state = make_state(nq_price=20_050.0, call_wall=20_200.0, put_wall=19_800.0)
        result = asyncio.run(self.signal.compute(state))
        assert -0.15 <= result.value <= 0.15
        assert result.confidence < 0.55

    def test_at_call_wall_bearish(self):
        # Price within 0.3% of call wall (20,200 * 0.003 = 60.6 pts)
        state = make_state(nq_price=20_160.0, call_wall=20_200.0, put_wall=19_800.0)
        result = asyncio.run(self.signal.compute(state))
        assert result.value < -0.2
        assert result.confidence > 0.60

    def test_at_put_wall_bullish(self):
        state = make_state(nq_price=19_840.0, call_wall=20_200.0, put_wall=19_800.0)
        result = asyncio.run(self.signal.compute(state))
        assert result.value > 0.2
        assert result.confidence > 0.60

    def test_above_call_wall_strong_bullish(self):
        state = make_state(nq_price=20_250.0, call_wall=20_200.0, put_wall=19_800.0)
        result = asyncio.run(self.signal.compute(state))
        assert result.value > 0.5

    def test_stale_data_returns_neutral(self):
        state = make_state(flashalpha_age_sec=200.0)  # Beyond 120s max
        result = asyncio.run(self.signal.safe_compute(state))
        assert result.value == 0.0
        assert result.confidence == 0.0
        assert result.metadata["reason"] == "stale_data"

    def test_safe_compute_never_raises(self):
        """safe_compute must not propagate exceptions."""
        state = make_state(nq_price=float("nan"))
        # Should not raise
        result = asyncio.run(self.signal.safe_compute(state))
        assert isinstance(result.value, float)

    def test_signal_result_value_bounds(self):
        """SignalResult rejects out-of-range values."""
        with pytest.raises(ValueError):
            from deep6.signals.options.types import SignalResult
            SignalResult(value=1.5, confidence=0.5, metadata={})
```

---

## Integration Checklist

When adding a new options signal to the 44-signal engine:

1. Subclass `BaseOptionsSignal` in `deep6/signals/options/`
2. Set `signal_name`, `signal_weight`, `category` as class variables
3. Implement `compute(state: OptionsState) -> SignalResult`
4. Register in `build_default_registry()` in `registry.py`
5. Add unit tests in `tests/signals/options/test_<name>.py`
6. Verify total category weight stays within configured bounds (see `composite-scoring.md`)
7. Add signal to the observability dashboard (signal name appears in the 44-signal table)

For composite scoring and how options signals integrate with the other 32 signals, see
`algo-patterns/composite-scoring.md`.
