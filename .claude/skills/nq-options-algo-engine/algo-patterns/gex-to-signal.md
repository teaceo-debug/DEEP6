# GEX to Signal

Converting GEX data from FlashAlpha into tradeable NQ signals.

GEX theory (what gamma exposure is, how dealers hedge, why walls form) lives in
`options-bias-engine/domains/gex-theory.md`. This file is purely about the code:
how to take the raw FlashAlpha response and produce `SignalResult` objects.

For the base signal interface, see `algo-patterns/python-signal-templates.md`.
For FlashAlpha API calls and response parsing, see `data-sources/flashalpha-bridge.md`.

---

## Data Contracts

```python
# deep6/signals/options/gex/types.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RegimeLabel(str, Enum):
    """
    Seven GEX regimes. Full playbooks in options-bias-engine/step1-regimes/.
    """
    A = "A"   # Positive gamma, between walls
    B = "B"   # Positive gamma, at call wall
    C = "C"   # Positive gamma, at put wall
    D = "D"   # Negative gamma, above flip
    E = "E"   # Negative gamma, below flip
    F = "F"   # Pin regime
    G = "G"   # Pre-event


class ProfileShape(str, Enum):
    SYMMETRIC    = "symmetric"
    SKEWED_CALL  = "skewed_call"
    SKEWED_PUT   = "skewed_put"
    BIMODAL      = "bimodal"
    FLAT         = "flat"
    UNKNOWN      = "unknown"


@dataclass
class RegimeState:
    label: RegimeLabel
    duration_sec: float
    stability_score: float   # 0-1: how stable/established this regime is
    previous_label: RegimeLabel | None
    transition_age_sec: float  # seconds since last regime change


@dataclass
class WallProximityResult:
    wall_state: str          # "at_call_wall", "at_put_wall", "between_walls", etc.
    nearest_wall: str        # "call" or "put"
    nearest_wall_price: float
    distance_pts: float      # absolute distance to nearest wall
    proximity_score: float   # 0-1, 1 = at wall
    direction: int           # +1 = bullish (at put wall), -1 = bearish (at call wall), 0 = neutral
```

---

## GEXRegimeClassifier

Classifies the current regime from FlashAlpha exposure data and maintains duration state.

```python
# deep6/signals/options/gex/regime_classifier.py
from __future__ import annotations

import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.gex.types import RegimeLabel, RegimeState

# How much each regime contributes to directional bias.
# Regime G is suppressed — pre-event noise dominates.
# See options-bias-engine/step1-regimes/ for the full playbook per regime.
_REGIME_SIGNAL_VALUE: dict[RegimeLabel, float] = {
    RegimeLabel.A: 0.0,    # Range — no directional lean
    RegimeLabel.B: -0.35,  # At call wall — expect rejection
    RegimeLabel.C: 0.55,   # At put wall — highest win-rate long setup
    RegimeLabel.D: 0.25,   # Negative gamma above flip — cautious bullish
    RegimeLabel.E: -0.65,  # Negative gamma below flip — trend bear
    RegimeLabel.F: 0.0,    # Pin — no directional bias
    RegimeLabel.G: 0.0,    # Pre-event — suppressed
}

_REGIME_BASE_CONFIDENCE: dict[RegimeLabel, float] = {
    RegimeLabel.A: 0.70,
    RegimeLabel.B: 0.65,
    RegimeLabel.C: 0.82,
    RegimeLabel.D: 0.55,
    RegimeLabel.E: 0.75,
    RegimeLabel.F: 0.60,
    RegimeLabel.G: 0.15,
}

# Minimum duration before a regime is considered "established"
_REGIME_ESTABLISHMENT_SEC = 300.0   # 5 minutes
# Maximum confidence bonus from duration
_MAX_DURATION_BONUS = 0.15
# Confidence penalty during the first 5 minutes of a new regime
_TRANSITION_PENALTY_WINDOW_SEC = 300.0
_MAX_TRANSITION_PENALTY = 0.12


class GEXRegimeClassifier(BaseOptionsSignal):
    """
    Translates the FlashAlpha regime label into a directional signal.

    The regime label comes pre-computed from FlashAlpha's exposure_summary endpoint.
    This signal's job is to:
      1. Track how long we've been in the current regime (duration bonus)
      2. Apply a transition penalty for fresh regime changes
      3. Suppress confidence in pre-event (G) and pin (F) regimes
      4. Expose the RegimeState for downstream signals to consume

    State maintained:
        _regime_entry_time: when the current regime was first detected
        _previous_regime: the regime before the current one
        _current_regime_state: full RegimeState, updated on each compute()
    """

    signal_name: ClassVar[str] = "gex_regime_classifier"
    signal_weight: ClassVar[float] = 0.20
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    def __init__(self) -> None:
        super().__init__()
        self._regime_entry_time: float = time.time()
        self._previous_regime: RegimeLabel | None = None
        self._current_regime: RegimeLabel | None = None
        self._current_regime_state: RegimeState | None = None

    @property
    def current_regime_state(self) -> RegimeState | None:
        """Expose for other signals that need regime context."""
        return self._current_regime_state

    async def compute(self, state: OptionsState) -> SignalResult:
        try:
            regime = RegimeLabel(state.regime_label.upper())
        except ValueError:
            return SignalResult(
                value=0.0, confidence=0.0,
                metadata={"reason": "unknown_regime", "raw": state.regime_label}
            )

        now = time.time()

        # Detect regime transition
        if regime != self._current_regime:
            self._previous_regime = self._current_regime
            self._current_regime = regime
            self._regime_entry_time = now

        duration_sec = now - self._regime_entry_time
        transition_age_sec = duration_sec  # same thing from the new regime's perspective

        # Stability score: 0 at transition, 1.0 after establishment window
        stability = min(1.0, duration_sec / _REGIME_ESTABLISHMENT_SEC)

        self._current_regime_state = RegimeState(
            label=regime,
            duration_sec=duration_sec,
            stability_score=stability,
            previous_label=self._previous_regime,
            transition_age_sec=transition_age_sec,
        )

        base_value = _REGIME_SIGNAL_VALUE[regime]
        base_confidence = _REGIME_BASE_CONFIDENCE[regime]

        # Duration bonus: established regimes are more reliable
        duration_bonus = min(_MAX_DURATION_BONUS, stability * _MAX_DURATION_BONUS)

        # Transition penalty: fresh regime changes are noisy
        if transition_age_sec < _TRANSITION_PENALTY_WINDOW_SEC:
            penalty_ratio = 1.0 - (transition_age_sec / _TRANSITION_PENALTY_WINDOW_SEC)
            transition_penalty = _MAX_TRANSITION_PENALTY * penalty_ratio
        else:
            transition_penalty = 0.0

        final_confidence = min(1.0, max(0.0, base_confidence + duration_bonus - transition_penalty))

        return SignalResult(
            value=base_value,
            confidence=final_confidence,
            metadata={
                "regime": regime.value,
                "duration_min": round(duration_sec / 60.0, 1),
                "stability": round(stability, 3),
                "duration_bonus": round(duration_bonus, 3),
                "transition_penalty": round(transition_penalty, 3),
                "previous_regime": self._previous_regime.value if self._previous_regime else None,
                "gamma_flip": state.gamma_flip,
                "nq_price": state.nq_price,
                "net_gex": state.net_gex,
            },
        )
```

---

## GEXWallProximityScorer

Scores proximity to call/put walls and produces a directional signal.

```python
# deep6/signals/options/gex/wall_proximity.py
from __future__ import annotations

from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.gex.types import WallProximityResult


class GEXWallProximityScorer(BaseOptionsSignal):
    """
    Scores proximity to call/put walls.

    Proximity threshold: configurable as a percentage of NQ price.
    Default 0.3% = ~60 NQ points at 20,000.

    Signal logic:
        - At call wall: bearish (dealers sell into it, expect rejection)
        - At put wall: bullish (dealers buy into it, expect support)
        - Above call wall (break): strong bullish (wall break, dealers chase)
        - Below put wall (break): strong bearish
        - Between walls: mild lean based on relative position

    Regime interaction:
        In positive gamma (A/B/C), wall signals are high confidence.
        In negative gamma (D/E), walls are weaker — price can blow through.
        Confidence is scaled down by 30% in negative gamma regimes.
    """

    signal_name: ClassVar[str] = "gex_wall_proximity"
    signal_weight: ClassVar[float] = 0.15
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    def __init__(
        self,
        proximity_pct: float = 0.003,
        neg_gamma_confidence_scale: float = 0.70,
    ) -> None:
        super().__init__()
        self.proximity_pct = proximity_pct
        self.neg_gamma_confidence_scale = neg_gamma_confidence_scale

    def _score_proximity(
        self, price: float, call_wall: float, put_wall: float
    ) -> WallProximityResult:
        threshold = price * self.proximity_pct

        dist_to_call = call_wall - price   # positive = price below call wall
        dist_to_put = price - put_wall     # positive = price above put wall

        above_call = dist_to_call < 0
        at_call = 0.0 < dist_to_call <= threshold
        below_put = dist_to_put < 0
        at_put = 0.0 < dist_to_put <= threshold

        if above_call:
            penetration = abs(dist_to_call) / max(threshold, 1.0)
            proximity_score = min(1.0, penetration)
            return WallProximityResult(
                wall_state="above_call_wall",
                nearest_wall="call",
                nearest_wall_price=call_wall,
                distance_pts=abs(dist_to_call),
                proximity_score=proximity_score,
                direction=1,
            )
        elif at_call:
            proximity_score = 1.0 - (dist_to_call / threshold)
            return WallProximityResult(
                wall_state="at_call_wall",
                nearest_wall="call",
                nearest_wall_price=call_wall,
                distance_pts=dist_to_call,
                proximity_score=proximity_score,
                direction=-1,
            )
        elif below_put:
            penetration = abs(dist_to_put) / max(threshold, 1.0)
            proximity_score = min(1.0, penetration)
            return WallProximityResult(
                wall_state="below_put_wall",
                nearest_wall="put",
                nearest_wall_price=put_wall,
                distance_pts=abs(dist_to_put),
                proximity_score=proximity_score,
                direction=-1,
            )
        elif at_put:
            proximity_score = 1.0 - (dist_to_put / threshold)
            return WallProximityResult(
                wall_state="at_put_wall",
                nearest_wall="put",
                nearest_wall_price=put_wall,
                distance_pts=dist_to_put,
                proximity_score=proximity_score,
                direction=1,
            )
        else:
            # Between walls
            wall_range = call_wall - put_wall
            if wall_range > 0:
                position = (price - put_wall) / wall_range
                # Slight lean: 0.5 = center = neutral, 0.8 = near call = mild bearish
                lean = (position - 0.5) * 0.3
            else:
                lean = 0.0
            nearest = "call" if dist_to_call < dist_to_put else "put"
            nearest_price = call_wall if nearest == "call" else put_wall
            nearest_dist = min(dist_to_call, dist_to_put)
            return WallProximityResult(
                wall_state="between_walls",
                nearest_wall=nearest,
                nearest_wall_price=nearest_price,
                distance_pts=nearest_dist,
                proximity_score=0.0,
                direction=0,
            )

    async def compute(self, state: OptionsState) -> SignalResult:
        if state.call_wall <= 0 or state.put_wall <= 0:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "no_wall_data"})

        prox = self._score_proximity(state.nq_price, state.call_wall, state.put_wall)

        # Compute value and confidence from proximity result
        if prox.wall_state == "above_call_wall":
            value = min(1.0, 0.55 + prox.proximity_score * 0.45)
            confidence = 0.72
        elif prox.wall_state == "at_call_wall":
            value = -(0.30 + prox.proximity_score * 0.45)
            confidence = 0.60 + prox.proximity_score * 0.20
        elif prox.wall_state == "below_put_wall":
            value = -min(1.0, 0.55 + prox.proximity_score * 0.45)
            confidence = 0.72
        elif prox.wall_state == "at_put_wall":
            value = 0.30 + prox.proximity_score * 0.45
            confidence = 0.65 + prox.proximity_score * 0.20
        else:
            # Between walls — use lean
            wall_range = state.call_wall - state.put_wall
            position = (state.nq_price - state.put_wall) / max(wall_range, 1.0)
            value = (position - 0.5) * 0.3
            confidence = 0.35

        # Scale confidence down in negative gamma regimes
        regime = state.regime_label.upper()
        if regime in ("D", "E"):
            confidence *= self.neg_gamma_confidence_scale

        return SignalResult(
            value=round(max(-1.0, min(1.0, value)), 4),
            confidence=round(min(1.0, confidence), 4),
            metadata={
                "wall_state": prox.wall_state,
                "nearest_wall": prox.nearest_wall,
                "nearest_wall_price": prox.nearest_wall_price,
                "distance_pts": round(prox.distance_pts, 2),
                "proximity_score": round(prox.proximity_score, 3),
                "call_wall": state.call_wall,
                "put_wall": state.put_wall,
                "regime": regime,
            },
        )
```

---

## GEXFlipDistanceSignal

Distance to gamma flip as a trend/reversal indicator.

```python
# deep6/signals/options/gex/flip_distance.py
from __future__ import annotations

import collections
import time
from typing import ClassVar

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory


class GEXFlipDistanceSignal(BaseOptionsSignal):
    """
    Measures distance to the gamma flip and estimates crossing probability.

    The gamma flip is the regime boundary. Price crossing it changes the entire
    trading character (positive → negative gamma or vice versa).

    Signal logic:
        - Far above flip in positive gamma: stable, mild bullish lean
        - Close to flip from above: transition risk, reduce confidence
        - Just crossed flip upward: strong bullish (regime D entry)
        - Far below flip in negative gamma: trend bear, high confidence
        - Close to flip from below: potential reversal, reduce confidence

    Crossing probability is estimated from:
        - Distance to flip (closer = higher probability)
        - Price velocity (faster approach = higher probability)
        - Regime duration (established regimes are stickier)

    State: rolling price history for velocity computation.
    """

    signal_name: ClassVar[str] = "gex_flip_distance"
    signal_weight: ClassVar[float] = 0.12
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    # Distance thresholds as % of NQ price
    NEAR_FLIP_PCT = 0.005    # 0.5% = ~100 pts at 20,000
    CLOSE_FLIP_PCT = 0.002   # 0.2% = ~40 pts

    def __init__(self, velocity_window_sec: float = 120.0) -> None:
        super().__init__()
        self._price_history: collections.deque[tuple[float, float]] = collections.deque()
        self.velocity_window_sec = velocity_window_sec

    def _compute_velocity(self, current_price: float) -> float:
        """Points per minute, positive = moving up."""
        now = time.time()
        self._price_history.append((now, current_price))
        cutoff = now - self.velocity_window_sec
        while self._price_history and self._price_history[0][0] < cutoff:
            self._price_history.popleft()

        if len(self._price_history) < 3:
            return 0.0

        oldest_t, oldest_p = self._price_history[0]
        elapsed = now - oldest_t
        if elapsed < 10.0:
            return 0.0

        return (current_price - oldest_p) / (elapsed / 60.0)

    def _crossing_probability(
        self,
        distance_pct: float,
        velocity_pts_per_min: float,
        flip_price: float,
        above_flip: bool,
    ) -> float:
        """
        Rough estimate of probability that price crosses the flip in the next 30 min.
        Not a rigorous model — used for confidence scaling only.
        """
        # Base probability from distance
        if distance_pct > 0.02:
            base_prob = 0.05
        elif distance_pct > 0.01:
            base_prob = 0.15
        elif distance_pct > 0.005:
            base_prob = 0.30
        elif distance_pct > 0.002:
            base_prob = 0.50
        else:
            base_prob = 0.70

        # Velocity adjustment: approaching flip increases probability
        if flip_price > 0 and velocity_pts_per_min != 0:
            approaching = (above_flip and velocity_pts_per_min < 0) or \
                          (not above_flip and velocity_pts_per_min > 0)
            if approaching:
                # Normalize velocity: 50 pts/min = significant
                vel_factor = min(0.25, abs(velocity_pts_per_min) / 200.0)
                base_prob = min(0.95, base_prob + vel_factor)
            else:
                base_prob = max(0.02, base_prob - 0.10)

        return base_prob

    async def compute(self, state: OptionsState) -> SignalResult:
        if state.gamma_flip <= 0:
            return SignalResult(value=0.0, confidence=0.0, metadata={"reason": "no_flip_data"})

        price = state.nq_price
        flip = state.gamma_flip
        velocity = self._compute_velocity(price)

        above_flip = price > flip
        distance_pts = abs(price - flip)
        distance_pct = distance_pts / price

        crossing_prob = self._crossing_probability(distance_pct, velocity, flip, above_flip)

        near_flip = distance_pct < self.NEAR_FLIP_PCT
        very_near_flip = distance_pct < self.CLOSE_FLIP_PCT

        if above_flip:
            # Above flip: positive gamma territory (or just entered D)
            regime = state.regime_label.upper()
            if regime in ("D",):
                # Negative gamma above flip — unstable bullish
                base_value = 0.20
                base_confidence = 0.50
            else:
                # Positive gamma above flip — stable
                base_value = 0.15
                base_confidence = 0.60

            # Near flip: reduce confidence (transition risk)
            if very_near_flip:
                base_confidence *= 0.60
                base_value *= 0.50
            elif near_flip:
                base_confidence *= 0.80
                base_value *= 0.75
        else:
            # Below flip: negative gamma territory
            base_value = -0.40
            base_confidence = 0.65

            if very_near_flip:
                # Potential reversal zone
                base_confidence *= 0.65
                base_value *= 0.60
            elif near_flip:
                base_confidence *= 0.82
                base_value *= 0.80

        # Reduce confidence when crossing is likely (regime transition imminent)
        if crossing_prob > 0.60:
            base_confidence *= (1.0 - (crossing_prob - 0.60) * 0.5)

        return SignalResult(
            value=round(max(-1.0, min(1.0, base_value)), 4),
            confidence=round(min(1.0, max(0.0, base_confidence)), 4),
            metadata={
                "above_flip": above_flip,
                "distance_pts": round(distance_pts, 2),
                "distance_pct": round(distance_pct * 100, 3),
                "crossing_probability": round(crossing_prob, 3),
                "velocity_pts_per_min": round(velocity, 2),
                "near_flip": near_flip,
                "very_near_flip": very_near_flip,
                "gamma_flip": flip,
                "regime": state.regime_label,
            },
        )
```

---

## GEXProfileShapeAnalyzer

Analyzes the full GEX strike profile for structural skew.

```python
# deep6/signals/options/gex/profile_shape.py
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import numpy as np

from deep6.signals.options.base import BaseOptionsSignal
from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.gex.types import ProfileShape

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gex-profile")


def _analyze_profile_sync(
    gex_by_strike: dict[float, float],
    current_price: float,
) -> dict:
    """
    CPU-bound profile analysis. Runs in thread pool.

    Returns:
        shape: ProfileShape value
        skew: -1 (put-heavy) to +1 (call-heavy)
        call_gex_pct: fraction of total |GEX| above current price
        put_gex_pct: fraction of total |GEX| below current price
        peak_call_strike: strike with highest positive GEX above price
        peak_put_strike: strike with highest negative GEX below price
    """
    if not gex_by_strike:
        return {"shape": ProfileShape.UNKNOWN.value, "skew": 0.0}

    strikes = np.array(sorted(gex_by_strike.keys()), dtype=np.float64)
    values = np.array([gex_by_strike[k] for k in strikes], dtype=np.float64)

    total_abs = np.sum(np.abs(values))
    if total_abs < 1e-9:
        return {"shape": ProfileShape.FLAT.value, "skew": 0.0, "call_gex_pct": 0.5, "put_gex_pct": 0.5}

    # Split by current price
    above_mask = strikes > current_price
    below_mask = strikes <= current_price

    call_gex = values[above_mask]
    put_gex = values[below_mask]
    call_strikes = strikes[above_mask]
    put_strikes = strikes[below_mask]

    call_abs = float(np.sum(np.abs(call_gex)))
    put_abs = float(np.sum(np.abs(put_gex)))

    call_pct = call_abs / total_abs
    put_pct = put_abs / total_abs

    # Skew: positive = call-heavy (bullish structure), negative = put-heavy
    skew = float((call_abs - put_abs) / total_abs)

    # Bimodal detection: two distinct peaks
    if len(call_gex) > 3 and len(put_gex) > 3:
        call_std = float(np.std(call_gex))
        put_std = float(np.std(put_gex))
        is_bimodal = call_std > 0.3 * call_abs / len(call_gex) and \
                     put_std > 0.3 * put_abs / len(put_gex)
    else:
        is_bimodal = False

    if is_bimodal:
        shape = ProfileShape.BIMODAL
    elif skew > 0.30:
        shape = ProfileShape.SKEWED_CALL
    elif skew < -0.30:
        shape = ProfileShape.SKEWED_PUT
    else:
        shape = ProfileShape.SYMMETRIC

    # Peak strikes
    peak_call_strike = None
    peak_put_strike = None
    if len(call_gex) > 0:
        peak_call_idx = int(np.argmax(call_gex))
        peak_call_strike = float(call_strikes[peak_call_idx])
    if len(put_gex) > 0:
        peak_put_idx = int(np.argmin(put_gex))  # most negative
        peak_put_strike = float(put_strikes[peak_put_idx])

    return {
        "shape": shape.value,
        "skew": round(skew, 4),
        "call_gex_pct": round(call_pct, 3),
        "put_gex_pct": round(put_pct, 3),
        "peak_call_strike": peak_call_strike,
        "peak_put_strike": peak_put_strike,
        "strike_count": len(strikes),
    }


class GEXProfileShapeAnalyzer(BaseOptionsSignal):
    """
    Analyzes the GEX strike profile shape for structural directional bias.

    A call-heavy profile (more GEX above price) means dealers have more
    gamma to hedge on the upside — creating a structural ceiling.
    A put-heavy profile means more downside hedging pressure.

    Bimodal profiles indicate contested levels — reduce confidence.

    Requires gex_by_strike to be populated in OptionsState.
    If not available, returns neutral with confidence=0.
    """

    signal_name: ClassVar[str] = "gex_profile_shape"
    signal_weight: ClassVar[float] = 0.08
    category: ClassVar[SignalCategory] = SignalCategory.GEX

    async def compute(self, state: OptionsState) -> SignalResult:
        if not state.gex_by_strike:
            return SignalResult(
                value=0.0, confidence=0.0,
                metadata={"reason": "no_profile_data"}
            )

        loop = asyncio.get_event_loop()
        profile = await loop.run_in_executor(
            _executor,
            _analyze_profile_sync,
            state.gex_by_strike,
            state.nq_price,
        )

        shape = profile["shape"]
        skew = profile.get("skew", 0.0)

        # Skewed call = bearish (ceiling), skewed put = bullish (floor support)
        # This is counterintuitive but correct: more call GEX above = more dealer
        # selling pressure on rallies. More put GEX below = more dealer buying on dips.
        value = -skew * 0.6   # invert: call-heavy → bearish signal

        if shape == ProfileShape.BIMODAL.value:
            confidence = 0.40   # contested — low confidence
        elif shape in (ProfileShape.SKEWED_CALL.value, ProfileShape.SKEWED_PUT.value):
            confidence = 0.65
        elif shape == ProfileShape.SYMMETRIC.value:
            confidence = 0.50
        else:
            confidence = 0.25

        return SignalResult(
            value=round(max(-1.0, min(1.0, value)), 4),
            confidence=confidence,
            metadata=profile,
        )
```

---

## Signal Composition

How the four GEX sub-signals combine into the GEX category score.

```python
# deep6/signals/options/gex/composite.py
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.gex.regime_classifier import GEXRegimeClassifier
from deep6.signals.options.gex.wall_proximity import GEXWallProximityScorer
from deep6.signals.options.gex.flip_distance import GEXFlipDistanceSignal
from deep6.signals.options.gex.profile_shape import GEXProfileShapeAnalyzer


@dataclass
class GEXCategoryResult:
    composite_value: float
    composite_confidence: float
    regime_result: SignalResult
    wall_result: SignalResult
    flip_result: SignalResult
    profile_result: SignalResult
    regime_weight_applied: float


class GEXCategoryComposite:
    """
    Aggregates the four GEX signals into a single category score.

    Weights are regime-conditional:
        Positive gamma (A/B/C): wall proximity weighted higher (walls hold)
        Negative gamma (D/E): flip distance weighted higher (trend continuation)
        Pin (F): all signals suppressed, only profile shape matters
        Pre-event (G): all signals at minimum weight

    The composite is consumed by CompositeOptionsScore (see composite-scoring.md).
    """

    # Base weights (sum to 1.0)
    _BASE_WEIGHTS = {
        "regime":  0.35,
        "wall":    0.30,
        "flip":    0.25,
        "profile": 0.10,
    }

    # Regime-conditional weight overrides
    _REGIME_WEIGHTS: dict[str, dict[str, float]] = {
        "A": {"regime": 0.30, "wall": 0.40, "flip": 0.20, "profile": 0.10},
        "B": {"regime": 0.25, "wall": 0.50, "flip": 0.15, "profile": 0.10},
        "C": {"regime": 0.25, "wall": 0.50, "flip": 0.15, "profile": 0.10},
        "D": {"regime": 0.30, "wall": 0.20, "flip": 0.40, "profile": 0.10},
        "E": {"regime": 0.35, "wall": 0.15, "flip": 0.40, "profile": 0.10},
        "F": {"regime": 0.10, "wall": 0.20, "flip": 0.10, "profile": 0.60},
        "G": {"regime": 0.25, "wall": 0.25, "flip": 0.25, "profile": 0.25},
    }

    def __init__(self) -> None:
        self.regime_signal = GEXRegimeClassifier()
        self.wall_signal = GEXWallProximityScorer()
        self.flip_signal = GEXFlipDistanceSignal()
        self.profile_signal = GEXProfileShapeAnalyzer()

    async def compute(self, state: OptionsState) -> GEXCategoryResult:
        import asyncio

        regime_r, wall_r, flip_r, profile_r = await asyncio.gather(
            self.regime_signal.safe_compute(state),
            self.wall_signal.safe_compute(state),
            self.flip_signal.safe_compute(state),
            self.profile_signal.safe_compute(state),
        )

        regime = state.regime_label.upper()
        weights = self._REGIME_WEIGHTS.get(regime, self._BASE_WEIGHTS)

        # Weighted average of confidence-scaled values
        components = [
            (regime_r, weights["regime"]),
            (wall_r,   weights["wall"]),
            (flip_r,   weights["flip"]),
            (profile_r, weights["profile"]),
        ]

        total_weight = sum(w for _, w in components)
        weighted_value = sum(r.weighted_value * w for r, w in components) / total_weight
        weighted_confidence = sum(r.confidence * w for r, w in components) / total_weight

        # Pre-event suppression
        if regime == "G":
            weighted_confidence *= 0.40

        return GEXCategoryResult(
            composite_value=round(max(-1.0, min(1.0, weighted_value)), 4),
            composite_confidence=round(min(1.0, weighted_confidence), 4),
            regime_result=regime_r,
            wall_result=wall_r,
            flip_result=flip_r,
            profile_result=profile_r,
            regime_weight_applied=weights["regime"],
        )
```

---

## Historical Calibration

Tuning thresholds from backtest data.

```python
# deep6/signals/options/gex/calibration.py
"""
Pattern for calibrating GEX signal thresholds from historical data.

Uses Databento MBO historical data + FlashAlpha historical API (Alpha tier).
See data-sources/databento-bridge.md and data-sources/flashalpha-bridge.md.

The calibration loop:
  1. Load historical FlashAlpha snapshots (at=YYYY-MM-DDTHH:mm:ss)
  2. Load corresponding NQ price data from Databento
  3. For each snapshot, compute signal values with candidate thresholds
  4. Evaluate: did the signal correctly predict the next N-bar move?
  5. Optimize thresholds via Optuna (see backtesting/optimization.py)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class GEXThresholds:
    """Tunable thresholds for GEX signals. Calibrate per instrument."""
    wall_proximity_pct: float = 0.003      # 0.3% default
    flip_near_pct: float = 0.005           # 0.5% default
    flip_very_near_pct: float = 0.002      # 0.2% default
    regime_establishment_sec: float = 300.0
    neg_gamma_confidence_scale: float = 0.70


def evaluate_wall_signal_accuracy(
    snapshots: list[dict],          # FlashAlpha snapshots
    prices: list[tuple[float, float]],  # (timestamp, nq_price) pairs
    thresholds: GEXThresholds,
    forward_bars: int = 5,
    bar_size_sec: int = 60,
) -> dict[str, float]:
    """
    Evaluate wall proximity signal accuracy on historical data.

    Returns:
        accuracy: fraction of correct directional predictions
        precision_bull: precision for bullish signals
        precision_bear: precision for bearish signals
        avg_confidence: mean confidence when signal fires
    """
    correct = 0
    total = 0
    bull_correct = bull_total = 0
    bear_correct = bear_total = 0
    confidences = []

    price_arr = np.array([p for _, p in prices])
    time_arr = np.array([t for t, _ in prices])

    for snap in snapshots:
        snap_time = snap["timestamp"]
        call_wall = snap.get("call_wall_nq", 0)
        put_wall = snap.get("put_wall_nq", 0)

        # Find price at snapshot time
        idx = int(np.searchsorted(time_arr, snap_time))
        if idx >= len(price_arr) - forward_bars:
            continue

        current_price = price_arr[idx]
        future_price = price_arr[idx + forward_bars]
        actual_direction = 1 if future_price > current_price else -1

        # Compute signal
        threshold = current_price * thresholds.wall_proximity_pct
        dist_to_call = call_wall - current_price
        dist_to_put = current_price - put_wall

        if 0 < dist_to_call <= threshold:
            predicted = -1  # at call wall → bearish
            confidence = 0.65 + (1.0 - dist_to_call / threshold) * 0.20
        elif 0 < dist_to_put <= threshold:
            predicted = 1   # at put wall → bullish
            confidence = 0.65 + (1.0 - dist_to_put / threshold) * 0.20
        else:
            continue  # signal not active

        total += 1
        confidences.append(confidence)
        if predicted == actual_direction:
            correct += 1
        if predicted == 1:
            bull_total += 1
            if actual_direction == 1:
                bull_correct += 1
        else:
            bear_total += 1
            if actual_direction == -1:
                bear_correct += 1

    return {
        "accuracy": correct / total if total > 0 else 0.0,
        "precision_bull": bull_correct / bull_total if bull_total > 0 else 0.0,
        "precision_bear": bear_correct / bear_total if bear_total > 0 else 0.0,
        "avg_confidence": float(np.mean(confidences)) if confidences else 0.0,
        "sample_count": total,
    }
```

---

## Integration Notes

The four GEX signals register individually in the signal registry AND compose via
`GEXCategoryComposite` for the options category score. Both paths are used:

- **Individual registration**: each signal appears in the 44-signal table with its own
  weight, value, and confidence. Useful for debugging and observability.
- **Category composite**: `GEXCategoryComposite.compute()` is called by
  `CompositeOptionsScore` (see `composite-scoring.md`) to produce the GEX sub-score
  that feeds into the options category weight.

The regime-conditional weighting in `GEXCategoryComposite` is the key insight: in
positive gamma, walls are reliable and should dominate. In negative gamma, the flip
distance matters more because walls can be blown through.
