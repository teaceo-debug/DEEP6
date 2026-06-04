# Flow to Signal

Converting institutional options flow into NQ momentum and reversal signals.

Flow theory (what sweeps are, how dark pool prints work, why OI changes matter) lives in
`options-bias-engine/step3-flow/`. This file is purely about the code: how to take raw
flow data and produce `SignalResult` objects.

For the base signal interface, see `algo-patterns/python-signal-templates.md`.
For data source integration (Massive.com, Unusual Whales), see `data-sources/`.

---

## Flow State Taxonomy

Six flow states, defined in `options-bias-engine/step3-flow/flow-interpretation.md`.
This enum is the shared vocabulary across all flow signals.

```python
# deep6/signals/options/flow/types.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class FlowState(str, Enum):
    AGGRESSIVE_BULLISH = "aggressive_bullish"
    AGGRESSIVE_BEARISH = "aggressive_bearish"
    ACCUMULATION       = "accumulation"        # Stealth bullish
    DISTRIBUTION       = "distribution"        # Stealth bearish
    HEDGING            = "hedging"             # Not directional
    DEAD               = "dead"                # Sub-threshold, no signal


@dataclass
class FlowClassification:
    state: FlowState
    intensity: float          # 0-1: how strong the flow signal is
    confidence: float         # 0-1: how certain the classification is
    dominant_source: str      # "massive", "unusual_whales", "both", "none"
    metadata: dict[str, Any]


@dataclass
class SweepEvent:
    timestamp: float
    direction: int            # +1 bullish, -1 bearish
    premium_usd: float        # Total premium in dollars
    symbol: str               # QQQ, NDX, etc.
    expiry_dte: int           # Days to expiry
    is_opening: bool          # Opening vs closing position


@dataclass
class DarkPoolPrint:
    timestamp: float
    direction: float          # -1.0 to +1.0 (net of all prints in window)
    total_volume: float       # Shares/contracts
    premium_usd: float
    confidence: float         # How clearly directional the prints are
```

---

## FlowStateClassifier

Classifies current flow into one of the six states.

```python
# deep6/signals/options/flow/flow_state.py
from __future__ import annotations

import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.flow.types import FlowState, FlowClassification

# Minimum net premium to consider flow "alive"
_MIN_PREMIUM_5M_USD = 5_000_000    # $5M in 5 minutes
_MIN_PREMIUM_1H_USD = 20_000_000   # $20M in 1 hour

# Sweep imbalance thresholds
_SWEEP_STRONG_RATIO = 3.0    # 3:1 bull:bear sweeps = strong directional
_SWEEP_MILD_RATIO = 1.8      # 1.8:1 = mild directional

# Dark pool direction thresholds
_DARK_STRONG = 0.60
_DARK_MILD = 0.30


class FlowStateClassifier(BaseOptionsSignal):
    """
    Classifies current options flow into one of six states.

    Classification logic (in priority order):
      1. DEAD: net premium below threshold AND no sweeps → no signal
      2. HEDGING: far OTM, long-dated, symmetric put/call → ignore
      3. DISTRIBUTION: dark pool bearish + visible flow bullish (divergence)
      4. ACCUMULATION: dark pool bullish + visible flow quiet/bearish
      5. AGGRESSIVE_BULLISH: call sweeps dominant + premium positive
      6. AGGRESSIVE_BEARISH: put sweeps dominant + premium negative

    The divergence patterns (ACCUMULATION/DISTRIBUTION) are the highest-alpha
    states — smart money hiding behind visible flow noise.
    See options-bias-engine/step4-cross-validation/distribution-accumulation.md.
    """

    signal_name: ClassVar[str] = "flow_state_classifier"
    signal_weight: ClassVar[float] = 0.18
    category: ClassVar[SignalCategory] = SignalCategory.FLOW

    # Signal values per flow state
    _STATE_VALUES: dict[FlowState, float] = {
        FlowState.AGGRESSIVE_BULLISH: 0.75,
        FlowState.AGGRESSIVE_BEARISH: -0.75,
        FlowState.ACCUMULATION:       0.55,   # Stealth bullish — high alpha
        FlowState.DISTRIBUTION:       -0.55,  # Stealth bearish — high alpha
        FlowState.HEDGING:            0.0,
        FlowState.DEAD:               0.0,
    }

    _STATE_CONFIDENCE: dict[FlowState, float] = {
        FlowState.AGGRESSIVE_BULLISH: 0.72,
        FlowState.AGGRESSIVE_BEARISH: 0.72,
        FlowState.ACCUMULATION:       0.78,   # Higher confidence — smart money signal
        FlowState.DISTRIBUTION:       0.78,
        FlowState.HEDGING:            0.20,
        FlowState.DEAD:               0.0,
    }

    def _classify(self, state: OptionsState) -> FlowClassification:
        prem_5m = state.net_premium_5m * 1_000_000   # Convert $M to $
        prem_1h = state.net_premium_1h * 1_000_000
        bull_sweeps = state.sweep_count_bullish
        bear_sweeps = state.sweep_count_bearish
        dark = state.dark_pool_direction

        total_sweeps = bull_sweeps + bear_sweeps

        # DEAD check
        if (abs(prem_5m) < _MIN_PREMIUM_5M_USD and
                abs(prem_1h) < _MIN_PREMIUM_1H_USD and
                total_sweeps < 2):
            return FlowClassification(
                state=FlowState.DEAD,
                intensity=0.0,
                confidence=0.0,
                dominant_source="none",
                metadata={"reason": "below_threshold"},
            )

        # Sweep ratio
        if total_sweeps > 0:
            sweep_ratio = bull_sweeps / max(bear_sweeps, 1)
            sweep_direction = 1 if bull_sweeps > bear_sweeps else -1
        else:
            sweep_ratio = 1.0
            sweep_direction = 0

        # Visible flow direction
        visible_bullish = prem_5m > _MIN_PREMIUM_5M_USD * 0.5 or sweep_direction == 1
        visible_bearish = prem_5m < -_MIN_PREMIUM_5M_USD * 0.5 or sweep_direction == -1

        # DISTRIBUTION: dark pool bearish + visible flow looks bullish
        if dark < -_DARK_MILD and visible_bullish:
            intensity = min(1.0, abs(dark) * 1.5)
            return FlowClassification(
                state=FlowState.DISTRIBUTION,
                intensity=intensity,
                confidence=0.75 if abs(dark) > _DARK_STRONG else 0.60,
                dominant_source="unusual_whales",
                metadata={
                    "dark_direction": dark,
                    "visible_bullish": visible_bullish,
                    "prem_5m_m": state.net_premium_5m,
                },
            )

        # ACCUMULATION: dark pool bullish + visible flow quiet or bearish
        if dark > _DARK_MILD and (not visible_bullish or visible_bearish):
            intensity = min(1.0, dark * 1.5)
            return FlowClassification(
                state=FlowState.ACCUMULATION,
                intensity=intensity,
                confidence=0.75 if dark > _DARK_STRONG else 0.60,
                dominant_source="unusual_whales",
                metadata={
                    "dark_direction": dark,
                    "visible_bearish": visible_bearish,
                    "prem_5m_m": state.net_premium_5m,
                },
            )

        # AGGRESSIVE BULLISH
        if (sweep_ratio >= _SWEEP_MILD_RATIO and sweep_direction == 1 and
                prem_5m > 0):
            intensity = min(1.0, (sweep_ratio - 1.0) / 3.0 + abs(prem_5m) / (50 * _MIN_PREMIUM_5M_USD))
            return FlowClassification(
                state=FlowState.AGGRESSIVE_BULLISH,
                intensity=min(1.0, intensity),
                confidence=0.70 if sweep_ratio >= _SWEEP_STRONG_RATIO else 0.55,
                dominant_source="massive",
                metadata={
                    "sweep_ratio": round(sweep_ratio, 2),
                    "bull_sweeps": bull_sweeps,
                    "bear_sweeps": bear_sweeps,
                    "prem_5m_m": state.net_premium_5m,
                },
            )

        # AGGRESSIVE BEARISH
        if (sweep_ratio <= 1.0 / _SWEEP_MILD_RATIO and sweep_direction == -1 and
                prem_5m < 0):
            bear_ratio = bear_sweeps / max(bull_sweeps, 1)
            intensity = min(1.0, (bear_ratio - 1.0) / 3.0 + abs(prem_5m) / (50 * _MIN_PREMIUM_5M_USD))
            return FlowClassification(
                state=FlowState.AGGRESSIVE_BEARISH,
                intensity=min(1.0, intensity),
                confidence=0.70 if bear_ratio >= _SWEEP_STRONG_RATIO else 0.55,
                dominant_source="massive",
                metadata={
                    "sweep_ratio": round(1.0 / sweep_ratio, 2),
                    "bull_sweeps": bull_sweeps,
                    "bear_sweeps": bear_sweeps,
                    "prem_5m_m": state.net_premium_5m,
                },
            )

        # HEDGING: symmetric or far-OTM flow
        return FlowClassification(
            state=FlowState.HEDGING,
            intensity=0.3,
            confidence=0.25,
            dominant_source="none",
            metadata={"reason": "symmetric_or_hedging"},
        )

    async def compute(self, state: OptionsState) -> SignalResult:
        classification = self._classify(state)

        base_value = self._STATE_VALUES[classification.state]
        base_confidence = self._STATE_CONFIDENCE[classification.state]

        # Scale by intensity
        final_value = base_value * classification.intensity
        final_confidence = base_confidence * (0.7 + 0.3 * classification.intensity)

        # Regime interaction: flow signals are more reliable in negative gamma
        regime = state.regime_label.upper()
        if regime in ("D", "E"):
            final_confidence = min(1.0, final_confidence * 1.15)

        return SignalResult(
            value=round(max(-1.0, min(1.0, final_value)), 4),
            confidence=round(min(1.0, final_confidence), 4),
            metadata={
                "flow_state": classification.state.value,
                "intensity": round(classification.intensity, 3),
                "dominant_source": classification.dominant_source,
                "regime": regime,
                **classification.metadata,
            },
        )
```

---

## SweepMomentumSignal

Detects escalating sweep patterns as momentum confirmation.

```python
# deep6/signals/options/flow/sweep_momentum.py
from __future__ import annotations

import collections
import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.flow.types import SweepEvent

# Escalation: sweeps accelerating in the same direction
_ESCALATION_WINDOW_SEC = 900.0   # 15 minutes
_MIN_SWEEPS_FOR_SIGNAL = 3
_STRONG_ESCALATION_RATE = 2.0    # 2x sweep rate increase = strong


class SweepMomentumSignal(BaseOptionsSignal):
    """
    Detects escalating sweep patterns as momentum confirmation.

    A single sweep is noise. Three sweeps in the same direction in 15 minutes
    is a signal. Three sweeps with increasing premium is a strong signal.

    Escalation rate: (recent sweep rate) / (baseline sweep rate).
    If sweeps are accelerating, momentum is building.

    State: rolling deque of SweepEvent objects.
    The OptionsState only provides aggregate counts — for per-sweep data,
    this signal needs to be fed via the flow event bus (see data-sources/).
    When only aggregate data is available, falls back to count-based scoring.
    """

    signal_name: ClassVar[str] = "sweep_momentum"
    signal_weight: ClassVar[float] = 0.12
    category: ClassVar[SignalCategory] = SignalCategory.FLOW

    def __init__(self) -> None:
        super().__init__()
        self._sweep_history: collections.deque[SweepEvent] = collections.deque()
        self._last_bull_count: int = 0
        self._last_bear_count: int = 0
        self._last_update_time: float = time.time()

    def add_sweep_event(self, event: SweepEvent) -> None:
        """
        Called by the flow event bus when a new sweep is detected.
        This is the preferred path — gives per-sweep granularity.
        """
        self._sweep_history.append(event)
        cutoff = time.time() - _ESCALATION_WINDOW_SEC
        while self._sweep_history and self._sweep_history[0].timestamp < cutoff:
            self._sweep_history.popleft()

    def _compute_from_events(self) -> tuple[float, float, dict]:
        """Use per-sweep event history when available."""
        now = time.time()
        cutoff_15m = now - _ESCALATION_WINDOW_SEC
        cutoff_5m = now - 300.0

        recent_15m = [e for e in self._sweep_history if e.timestamp > cutoff_15m]
        recent_5m = [e for e in self._sweep_history if e.timestamp > cutoff_5m]

        if len(recent_15m) < _MIN_SWEEPS_FOR_SIGNAL:
            return 0.0, 0.0, {"reason": "insufficient_sweeps", "count_15m": len(recent_15m)}

        bull_15m = [e for e in recent_15m if e.direction == 1]
        bear_15m = [e for e in recent_15m if e.direction == -1]
        bull_5m = [e for e in recent_5m if e.direction == 1]
        bear_5m = [e for e in recent_5m if e.direction == -1]

        # Dominant direction
        if len(bull_15m) > len(bear_15m):
            direction = 1
            dominant_15m = bull_15m
            dominant_5m = bull_5m
        elif len(bear_15m) > len(bull_15m):
            direction = -1
            dominant_15m = bear_15m
            dominant_5m = bear_5m
        else:
            return 0.0, 0.30, {"reason": "balanced_sweeps"}

        # Escalation: are sweeps accelerating?
        rate_15m = len(dominant_15m) / 15.0   # sweeps per minute
        rate_5m = len(dominant_5m) / 5.0 if dominant_5m else 0.0
        escalation_rate = rate_5m / max(rate_15m, 0.01)

        # Premium escalation: are individual sweeps getting larger?
        if len(dominant_15m) >= 3:
            premiums = [e.premium_usd for e in sorted(dominant_15m, key=lambda x: x.timestamp)]
            # Simple linear trend: positive = escalating
            n = len(premiums)
            x = list(range(n))
            mean_x = sum(x) / n
            mean_p = sum(premiums) / n
            slope = sum((xi - mean_x) * (pi - mean_p) for xi, pi in zip(x, premiums))
            slope /= max(sum((xi - mean_x) ** 2 for xi in x), 1.0)
            premium_escalating = slope > 0
        else:
            premium_escalating = False

        # Score
        base_score = min(1.0, len(dominant_15m) / 8.0)  # 8 sweeps = max
        if escalation_rate >= _STRONG_ESCALATION_RATE:
            base_score = min(1.0, base_score * 1.4)
        if premium_escalating:
            base_score = min(1.0, base_score * 1.2)

        confidence = 0.55 + min(0.25, len(dominant_15m) * 0.04)
        if escalation_rate >= _STRONG_ESCALATION_RATE:
            confidence = min(0.85, confidence + 0.10)

        return (
            direction * base_score,
            confidence,
            {
                "direction": direction,
                "count_15m": len(dominant_15m),
                "count_5m": len(dominant_5m),
                "escalation_rate": round(escalation_rate, 2),
                "premium_escalating": premium_escalating,
            },
        )

    def _compute_from_counts(self, state: OptionsState) -> tuple[float, float, dict]:
        """
        Fallback when per-sweep events aren't available.
        Uses aggregate counts from OptionsState.
        """
        bull = state.sweep_count_bullish
        bear = state.sweep_count_bearish
        total = bull + bear

        if total < _MIN_SWEEPS_FOR_SIGNAL:
            return 0.0, 0.0, {"reason": "insufficient_sweeps", "total": total}

        if bull > bear:
            direction = 1
            ratio = bull / max(bear, 1)
            dominant = bull
        elif bear > bull:
            direction = -1
            ratio = bear / max(bull, 1)
            dominant = bear
        else:
            return 0.0, 0.25, {"reason": "balanced"}

        score = min(1.0, (ratio - 1.0) / 3.0 + dominant / 10.0)
        confidence = 0.45 + min(0.20, dominant * 0.03)

        return (
            direction * score,
            confidence,
            {"direction": direction, "bull": bull, "bear": bear, "ratio": round(ratio, 2)},
        )

    async def compute(self, state: OptionsState) -> SignalResult:
        if self._sweep_history:
            value, confidence, meta = self._compute_from_events()
        else:
            value, confidence, meta = self._compute_from_counts(state)

        return SignalResult(
            value=round(max(-1.0, min(1.0, value)), 4),
            confidence=round(min(1.0, confidence), 4),
            metadata={**meta, "data_source": "events" if self._sweep_history else "counts"},
        )
```

---

## DarkPoolSupportSignal

Dark pool prints as institutional support/distribution indicator.

```python
# deep6/signals/options/flow/dark_pool.py
from __future__ import annotations

import collections
import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.flow.types import DarkPoolPrint

_HISTORY_WINDOW_SEC = 3600.0   # 1 hour of dark pool history
_MIN_PRINTS_FOR_SIGNAL = 3
_STRONG_DIRECTION_THRESHOLD = 0.50


class DarkPoolSupportSignal(BaseOptionsSignal):
    """
    Translates dark pool print direction into a support/distribution signal.

    Dark pool prints are the highest-conviction flow signal in the system.
    When dark pool is buying while visible flow looks bearish, that's accumulation.
    When dark pool is selling while visible flow looks bullish, that's distribution.

    The divergence between dark and visible flow is the key pattern.
    See options-bias-engine/step4-cross-validation/distribution-accumulation.md.

    State: rolling deque of DarkPoolPrint objects.
    Falls back to OptionsState.dark_pool_direction when no event history.
    """

    signal_name: ClassVar[str] = "dark_pool_support"
    signal_weight: ClassVar[float] = 0.10
    category: ClassVar[SignalCategory] = SignalCategory.FLOW

    def __init__(self) -> None:
        super().__init__()
        self._print_history: collections.deque[DarkPoolPrint] = collections.deque()

    def add_print(self, print_event: DarkPoolPrint) -> None:
        self._print_history.append(print_event)
        cutoff = time.time() - _HISTORY_WINDOW_SEC
        while self._print_history and self._print_history[0].timestamp < cutoff:
            self._print_history.popleft()

    def _compute_from_history(self, state: OptionsState) -> tuple[float, float, dict]:
        now = time.time()
        recent = [p for p in self._print_history if p.timestamp > now - 1800.0]  # 30 min

        if len(recent) < _MIN_PRINTS_FOR_SIGNAL:
            return 0.0, 0.0, {"reason": "insufficient_prints", "count": len(recent)}

        # Volume-weighted direction
        total_volume = sum(p.total_volume for p in recent)
        if total_volume == 0:
            return 0.0, 0.0, {"reason": "zero_volume"}

        weighted_dir = sum(p.direction * p.total_volume for p in recent) / total_volume
        avg_confidence = sum(p.confidence for p in recent) / len(recent)

        # Divergence bonus: dark pool direction vs visible flow
        visible_dir = 1.0 if state.net_premium_5m > 0 else -1.0 if state.net_premium_5m < 0 else 0.0
        divergence = weighted_dir * visible_dir < 0  # opposite signs = divergence

        if divergence:
            # Dark vs visible divergence = higher alpha signal
            confidence = min(0.85, avg_confidence * 1.25)
        else:
            confidence = avg_confidence * 0.85

        value = max(-1.0, min(1.0, weighted_dir * 1.2))

        return (
            value,
            confidence,
            {
                "weighted_direction": round(weighted_dir, 3),
                "print_count": len(recent),
                "divergence_from_visible": divergence,
                "visible_direction": visible_dir,
            },
        )

    async def compute(self, state: OptionsState) -> SignalResult:
        if self._print_history:
            value, confidence, meta = self._compute_from_history(state)
        else:
            # Fallback: use aggregate dark_pool_direction from OptionsState
            dark = state.dark_pool_direction
            if abs(dark) < 0.15:
                return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "weak_dark_signal"})

            value = dark * 0.8
            confidence = 0.45 + abs(dark) * 0.25
            meta = {"source": "aggregate", "dark_direction": dark}

        return SignalResult(
            value=round(max(-1.0, min(1.0, value)), 4),
            confidence=round(min(1.0, confidence), 4),
            metadata=meta,
        )
```

---

## OIChangeSignal

Open interest changes as positioning shift indicator.

```python
# deep6/signals/options/flow/oi_change.py
from __future__ import annotations

import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory


class OIChangeSignal(BaseOptionsSignal):
    """
    Detects significant open interest changes as positioning shifts.

    OI increasing on calls = new bullish positioning (or new hedging).
    OI increasing on puts = new bearish positioning (or new hedging).
    OI decreasing = position closing — less directional signal.

    Context matters: OI change in the direction of the current trend
    is continuation. OI change against the trend is potential reversal.

    This signal requires OI snapshot data from Massive.com.
    The OptionsState carries net_premium as a proxy when OI snapshots
    aren't available — this signal degrades gracefully.

    State: previous OI snapshot for delta computation.
    """

    signal_name: ClassVar[str] = "oi_change"
    signal_weight: ClassVar[float] = 0.08
    category: ClassVar[SignalCategory] = SignalCategory.FLOW

    def __init__(self) -> None:
        super().__init__()
        self._prev_call_oi: float | None = None
        self._prev_put_oi: float | None = None
        self._prev_snapshot_time: float = 0.0

    def update_oi_snapshot(
        self,
        call_oi: float,
        put_oi: float,
        timestamp: float | None = None,
    ) -> None:
        """
        Called when a new OI snapshot arrives from Massive.com.
        Stores previous values for delta computation.
        """
        self._prev_call_oi = call_oi
        self._prev_put_oi = put_oi
        self._prev_snapshot_time = timestamp or time.time()

    async def compute(self, state: OptionsState) -> SignalResult:
        # Without OI snapshot data, fall back to premium flow as proxy
        if self._prev_call_oi is None or self._prev_put_oi is None:
            return self._compute_from_premium_proxy(state)

        # OI snapshot available
        snapshot_age = time.time() - self._prev_snapshot_time
        if snapshot_age > 3600.0:
            return SignalResult(
                value=0.0, confidence=0.0,
                metadata={"reason": "stale_oi_snapshot", "age_sec": snapshot_age}
            )

        call_oi = self._prev_call_oi
        put_oi = self._prev_put_oi
        total_oi = call_oi + put_oi

        if total_oi == 0:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "zero_oi"})

        # PC ratio: < 0.7 = bullish, > 1.3 = bearish
        pc_ratio = put_oi / max(call_oi, 1.0)

        if pc_ratio < 0.5:
            value = 0.60
            confidence = 0.65
            positioning = "strongly_bullish"
        elif pc_ratio < 0.7:
            value = 0.35
            confidence = 0.55
            positioning = "bullish"
        elif pc_ratio < 1.0:
            value = 0.10
            confidence = 0.40
            positioning = "mild_bullish"
        elif pc_ratio < 1.3:
            value = -0.10
            confidence = 0.40
            positioning = "mild_bearish"
        elif pc_ratio < 1.8:
            value = -0.35
            confidence = 0.55
            positioning = "bearish"
        else:
            value = -0.60
            confidence = 0.65
            positioning = "strongly_bearish"

        return SignalResult(
            value=round(value, 4),
            confidence=confidence,
            metadata={
                "pc_ratio": round(pc_ratio, 3),
                "call_oi": call_oi,
                "put_oi": put_oi,
                "positioning": positioning,
                "snapshot_age_sec": round(snapshot_age, 0),
            },
        )

    def _compute_from_premium_proxy(self, state: OptionsState) -> SignalResult:
        """
        Fallback when OI data isn't available.
        Uses net premium flow as a rough positioning proxy.
        """
        prem_1h = state.net_premium_1h

        if abs(prem_1h) < 10.0:  # < $10M in 1h = no signal
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "low_premium_proxy"})

        # Normalize: $100M = max signal
        value = max(-1.0, min(1.0, prem_1h / 100.0))
        confidence = 0.35  # Low confidence — proxy only

        return SignalResult(
            value=round(value, 4),
            confidence=confidence,
            metadata={"source": "premium_proxy", "prem_1h_m": prem_1h},
        )
```

---

## PutCallRatioSignal

PC ratio contextualized by regime and flow state.

```python
# deep6/signals/options/flow/put_call_ratio.py
from __future__ import annotations

from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory


class PutCallRatioSignal(BaseOptionsSignal):
    """
    Interprets put/call ratio in the context of the current regime.

    Raw PC ratio is ambiguous: high puts could mean bearish positioning
    OR protective hedging by longs. Context resolves the ambiguity:

    In positive gamma (A/B/C):
        High PC ratio = hedging by longs = bullish (they're protecting gains)
        Low PC ratio = complacency = mild bearish (no protection = crowded long)

    In negative gamma (D/E):
        High PC ratio = directional bearish bets = bearish
        Low PC ratio = directional bullish bets = bullish

    This inversion is the key insight. The same PC ratio means opposite
    things in different regimes.

    PC ratio is derived from OptionsState sweep counts as a proxy.
    For actual OI-based PC ratio, use OIChangeSignal.
    """

    signal_name: ClassVar[str] = "put_call_ratio"
    signal_weight: ClassVar[float] = 0.07
    category: ClassVar[SignalCategory] = SignalCategory.FLOW

    async def compute(self, state: OptionsState) -> SignalResult:
        bull_sweeps = state.sweep_count_bullish
        bear_sweeps = state.sweep_count_bearish
        total = bull_sweeps + bear_sweeps

        if total < 2:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "insufficient_sweeps"})

        # PC ratio from sweep counts (proxy)
        pc_ratio = bear_sweeps / max(bull_sweeps, 1)
        regime = state.regime_label.upper()
        is_positive_gamma = regime in ("A", "B", "C")

        if is_positive_gamma:
            # Positive gamma: high PC = hedging = bullish context
            if pc_ratio > 1.5:
                value = 0.30    # Hedging = longs protecting = bullish
                confidence = 0.50
                context = "hedging_bullish"
            elif pc_ratio < 0.5:
                value = -0.20   # Complacency = crowded long = mild bearish
                confidence = 0.40
                context = "complacency_bearish"
            else:
                value = 0.0
                confidence = 0.25
                context = "neutral"
        else:
            # Negative gamma: PC ratio is directional
            if pc_ratio > 1.5:
                value = -0.45   # Directional puts = bearish
                confidence = 0.60
                context = "directional_bearish"
            elif pc_ratio < 0.5:
                value = 0.45    # Directional calls = bullish
                confidence = 0.60
                context = "directional_bullish"
            else:
                value = 0.0
                confidence = 0.30
                context = "neutral"

        return SignalResult(
            value=round(value, 4),
            confidence=confidence,
            metadata={
                "pc_ratio": round(pc_ratio, 3),
                "bull_sweeps": bull_sweeps,
                "bear_sweeps": bear_sweeps,
                "regime": regime,
                "is_positive_gamma": is_positive_gamma,
                "context": context,
            },
        )
```

---

## Flow Signal Composition

```python
# deep6/signals/options/flow/composite.py
from __future__ import annotations

from dataclasses import dataclass

from deep6.signals.options.types import OptionsState, SignalResult
from deep6.signals.options.flow.flow_state import FlowStateClassifier
from deep6.signals.options.flow.sweep_momentum import SweepMomentumSignal
from deep6.signals.options.flow.dark_pool import DarkPoolSupportSignal
from deep6.signals.options.flow.oi_change import OIChangeSignal
from deep6.signals.options.flow.put_call_ratio import PutCallRatioSignal


@dataclass
class FlowCategoryResult:
    composite_value: float
    composite_confidence: float
    flow_state_result: SignalResult
    sweep_result: SignalResult
    dark_pool_result: SignalResult
    oi_result: SignalResult
    pc_ratio_result: SignalResult


class FlowCategoryComposite:
    """
    Aggregates the five flow signals into a single category score.

    Weights are regime-conditional:
        Negative gamma (D/E): flow signals weighted higher (trend confirmation)
        Positive gamma (A/B/C): flow signals weighted lower (structure dominates)
        Pre-event (G): all flow signals suppressed

    Dark pool signal gets a bonus weight when divergence is detected
    (dark vs visible flow disagreement = highest alpha scenario).
    """

    _BASE_WEIGHTS = {
        "flow_state":    0.35,
        "sweep":         0.25,
        "dark_pool":     0.20,
        "oi_change":     0.12,
        "pc_ratio":      0.08,
    }

    _NEG_GAMMA_WEIGHTS = {
        "flow_state":    0.30,
        "sweep":         0.30,
        "dark_pool":     0.22,
        "oi_change":     0.10,
        "pc_ratio":      0.08,
    }

    _POS_GAMMA_WEIGHTS = {
        "flow_state":    0.35,
        "sweep":         0.20,
        "dark_pool":     0.25,  # Dark pool more important in range (accumulation/distribution)
        "oi_change":     0.12,
        "pc_ratio":      0.08,
    }

    def __init__(self) -> None:
        self.flow_state_signal = FlowStateClassifier()
        self.sweep_signal = SweepMomentumSignal()
        self.dark_pool_signal = DarkPoolSupportSignal()
        self.oi_signal = OIChangeSignal()
        self.pc_ratio_signal = PutCallRatioSignal()

    async def compute(self, state: OptionsState) -> FlowCategoryResult:
        import asyncio

        flow_r, sweep_r, dark_r, oi_r, pc_r = await asyncio.gather(
            self.flow_state_signal.safe_compute(state),
            self.sweep_signal.safe_compute(state),
            self.dark_pool_signal.safe_compute(state),
            self.oi_signal.safe_compute(state),
            self.pc_ratio_signal.safe_compute(state),
        )

        regime = state.regime_label.upper()
        if regime in ("D", "E"):
            weights = self._NEG_GAMMA_WEIGHTS
        elif regime in ("A", "B", "C"):
            weights = self._POS_GAMMA_WEIGHTS
        else:
            weights = self._BASE_WEIGHTS

        components = [
            (flow_r, weights["flow_state"]),
            (sweep_r, weights["sweep"]),
            (dark_r, weights["dark_pool"]),
            (oi_r, weights["oi_change"]),
            (pc_r, weights["pc_ratio"]),
        ]

        total_weight = sum(w for _, w in components)
        weighted_value = sum(r.weighted_value * w for r, w in components) / total_weight
        weighted_confidence = sum(r.confidence * w for r, w in components) / total_weight

        # Pre-event suppression
        if regime == "G":
            weighted_confidence *= 0.35

        return FlowCategoryResult(
            composite_value=round(max(-1.0, min(1.0, weighted_value)), 4),
            composite_confidence=round(min(1.0, weighted_confidence), 4),
            flow_state_result=flow_r,
            sweep_result=sweep_r,
            dark_pool_result=dark_r,
            oi_result=oi_r,
            pc_ratio_result=pc_r,
        )
```

---

## Integration Notes

Flow signals are the most time-sensitive signals in the options category. FlashAlpha
polls every 30-60 seconds, but sweep events from Massive.com arrive in near real-time
(10-15 second polling). The `SweepMomentumSignal` and `DarkPoolSupportSignal` both
support an event-push interface (`add_sweep_event`, `add_print`) for when the data
pipeline delivers individual events rather than aggregates.

When only aggregate data is available (the OptionsState counts), all signals degrade
gracefully to count-based scoring with reduced confidence. This is the correct behavior
for the initial integration phase before per-event streaming is wired up.

The divergence pattern (dark pool vs visible flow) is the highest-alpha signal in this
category. When `DarkPoolSupportSignal` detects divergence, it boosts its own confidence
by 25%. The `FlowStateClassifier` also detects this pattern and classifies it as
ACCUMULATION or DISTRIBUTION — both signals firing in the same direction on divergence
is a strong conviction indicator.
