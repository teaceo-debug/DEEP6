# Composite Scoring

How options-derived signals integrate into the DEEP6 44-signal composite confidence score.

This file covers the aggregation math, regime-conditional weighting, conviction matrix
integration, and time-of-day adjustments. For individual signal implementations, see
`gex-to-signal.md` and `flow-to-signal.md`. For the conviction matrix theory, see
`options-bias-engine/step4-cross-validation/conviction-matrix.md`.

---

## Signal Inventory

The 44-signal engine has signals across multiple categories. Options-derived signals
occupy approximately 8-12 slots depending on which sub-signals are active.

```
44-SIGNAL ENGINE
├── Microstructure (footprint) signals: ~20 signals
│   ├── Absorption detection
│   ├── Exhaustion detection
│   ├── Delta imbalance
│   ├── Stacked imbalances
│   └── ... (see main signal engine docs)
│
├── Options signals: 8-12 signals (this file)
│   ├── GEX category (4 signals)
│   │   ├── gex_regime_classifier       weight: 0.20
│   │   ├── gex_wall_proximity          weight: 0.15
│   │   ├── gex_flip_distance           weight: 0.12
│   │   └── gex_profile_shape           weight: 0.08
│   │
│   ├── Flow category (5 signals)
│   │   ├── flow_state_classifier       weight: 0.18
│   │   ├── sweep_momentum              weight: 0.12
│   │   ├── dark_pool_support           weight: 0.10
│   │   ├── oi_change                   weight: 0.08
│   │   └── put_call_ratio              weight: 0.07
│   │
│   └── Volatility category (3 signals, optional)
│       ├── vrp_regime                  weight: 0.10
│       ├── iv_rank                     weight: 0.06
│       └── skew_signal                 weight: 0.05
│
├── Kronos E10 bias: 1 signal
│   └── kronos_directional_bias         weight: configurable
│
└── DOM/order book signals: ~12 signals
    └── (Rithmic MBO signals — separate module)
```

---

## Category Weight Architecture

```python
# deep6/signals/options/composite_scoring.py
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from deep6.signals.options.types import OptionsState, SignalResult, SignalCategory
from deep6.signals.options.gex.composite import GEXCategoryComposite, GEXCategoryResult
from deep6.signals.options.flow.composite import FlowCategoryComposite, FlowCategoryResult


@dataclass
class OptionsScoreBreakdown:
    """
    Full breakdown of the options category score.
    Consumed by the main 44-signal aggregator.
    """
    # Final outputs
    composite_value: float          # -1.0 to +1.0
    composite_confidence: float     # 0.0 to 1.0
    category_weight: float          # Applied weight in the 44-signal engine

    # Sub-category scores
    gex_value: float
    gex_confidence: float
    flow_value: float
    flow_confidence: float
    volatility_value: float
    volatility_confidence: float

    # Conviction matrix
    rivers_agreeing: int            # 0-5
    conviction_multiplier: float    # Applied to category_weight

    # Regime context
    regime: str
    regime_weight_applied: float    # How much regime influenced weighting

    # Time-of-day context
    tod_multiplier: float           # 0DTE intensification factor
    session_phase: str              # "open", "midday", "power_hour", "close"

    # Metadata
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_weight(self) -> float:
        """Actual weight applied in the 44-signal engine after all adjustments."""
        return self.category_weight * self.conviction_multiplier * self.tod_multiplier
```

---

## CompositeOptionsScore

The main class that aggregates all options signals into a single score.

```python
# deep6/signals/options/composite_scoring.py (continued)

# Default category weight within the 44-signal engine
# Configurable — tune based on backtest results
DEFAULT_OPTIONS_CATEGORY_WEIGHT = 0.30

# Sub-category weights within the options category (sum to 1.0)
_SUBCATEGORY_BASE_WEIGHTS = {
    "gex":        0.45,
    "flow":       0.40,
    "volatility": 0.15,
}

# Regime-conditional sub-category weights
_SUBCATEGORY_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "A": {"gex": 0.50, "flow": 0.35, "volatility": 0.15},  # Range: structure dominates
    "B": {"gex": 0.55, "flow": 0.30, "volatility": 0.15},  # At call wall: GEX critical
    "C": {"gex": 0.55, "flow": 0.30, "volatility": 0.15},  # At put wall: GEX critical
    "D": {"gex": 0.35, "flow": 0.50, "volatility": 0.15},  # Neg gamma: flow leads
    "E": {"gex": 0.30, "flow": 0.55, "volatility": 0.15},  # Trend bear: flow leads
    "F": {"gex": 0.40, "flow": 0.35, "volatility": 0.25},  # Pin: vol structure matters
    "G": {"gex": 0.33, "flow": 0.33, "volatility": 0.34},  # Pre-event: balanced, suppressed
}

# Conviction matrix multipliers (from options-bias-engine/step4-cross-validation)
_CONVICTION_MULTIPLIERS = {
    5: 1.00,   # All rivers agree → full weight
    4: 0.80,   # One divergence → 80%
    3: 0.50,   # Significant divergence → 50%
    2: 0.20,   # Conflict → heavily suppressed
    1: 0.05,   # Almost no agreement → near-zero
    0: 0.0,    # No agreement → suppressed
}


class CompositeOptionsScore:
    """
    Aggregates GEX, flow, and volatility signals into the options category score.

    This is the single entry point for the 44-signal engine to get the options
    category contribution. It handles:
      - Sub-category aggregation (GEX + flow + volatility)
      - Regime-conditional weighting
      - Conviction matrix integration
      - Time-of-day adjustments
      - Pre-event suppression

    Usage:
        scorer = CompositeOptionsScore()
        breakdown = await scorer.compute(options_state)
        # breakdown.composite_value feeds into the 44-signal aggregator
        # breakdown.effective_weight is the weight to apply
    """

    def __init__(
        self,
        category_weight: float = DEFAULT_OPTIONS_CATEGORY_WEIGHT,
    ) -> None:
        self.category_weight = category_weight
        self.gex_composite = GEXCategoryComposite()
        self.flow_composite = FlowCategoryComposite()
        # Volatility composite: optional, see volatility-to-signal.md
        self._volatility_available = False

    async def compute(self, state: OptionsState) -> OptionsScoreBreakdown:
        # Run GEX and flow composites concurrently
        gex_result, flow_result = await asyncio.gather(
            self.gex_composite.compute(state),
            self.flow_composite.compute(state),
        )

        regime = state.regime_label.upper()
        weights = _SUBCATEGORY_REGIME_WEIGHTS.get(regime, _SUBCATEGORY_BASE_WEIGHTS)

        # Volatility sub-score (placeholder — 0 when not available)
        vol_value = 0.0
        vol_confidence = 0.0

        # Weighted aggregation
        gex_w = weights["gex"]
        flow_w = weights["flow"]
        vol_w = weights["volatility"]

        # Confidence-weighted values
        gex_contrib = gex_result.composite_value * gex_result.composite_confidence * gex_w
        flow_contrib = flow_result.composite_value * flow_result.composite_confidence * flow_w
        vol_contrib = vol_value * vol_confidence * vol_w

        total_conf_weight = (
            gex_result.composite_confidence * gex_w +
            flow_result.composite_confidence * flow_w +
            vol_confidence * vol_w
        )

        if total_conf_weight > 0:
            composite_value = (gex_contrib + flow_contrib + vol_contrib) / total_conf_weight
            composite_confidence = total_conf_weight / (gex_w + flow_w + vol_w)
        else:
            composite_value = 0.0
            composite_confidence = 0.0

        # Conviction matrix
        rivers_agreeing = self._count_agreeing_rivers(state, gex_result, flow_result)
        conviction_multiplier = _CONVICTION_MULTIPLIERS.get(rivers_agreeing, 0.0)

        # Time-of-day adjustment
        tod_multiplier, session_phase = self._time_of_day_multiplier()

        # Pre-event suppression (regime G)
        if regime == "G":
            composite_confidence *= 0.40
            conviction_multiplier = min(conviction_multiplier, 0.50)

        return OptionsScoreBreakdown(
            composite_value=round(max(-1.0, min(1.0, composite_value)), 4),
            composite_confidence=round(min(1.0, composite_confidence), 4),
            category_weight=self.category_weight,
            gex_value=gex_result.composite_value,
            gex_confidence=gex_result.composite_confidence,
            flow_value=flow_result.composite_value,
            flow_confidence=flow_result.composite_confidence,
            volatility_value=vol_value,
            volatility_confidence=vol_confidence,
            rivers_agreeing=rivers_agreeing,
            conviction_multiplier=conviction_multiplier,
            regime=regime,
            regime_weight_applied=gex_w,
            tod_multiplier=tod_multiplier,
            session_phase=session_phase,
            metadata={
                "gex_regime": gex_result.regime_result.metadata.get("regime"),
                "flow_state": flow_result.flow_state_result.metadata.get("flow_state"),
                "subcategory_weights": weights,
            },
        )

    def _count_agreeing_rivers(
        self,
        state: OptionsState,
        gex_result: GEXCategoryResult,
        flow_result: FlowCategoryResult,
    ) -> int:
        """
        Count how many of the five data rivers agree on direction.

        Rivers:
          1. FlashAlpha structure (GEX regime + walls)
          2. Massive.com flow (sweeps + premium)
          3. Unusual Whales dark pool
          4. Rithmic MBO order book (DOM confirmation)
          5. Volatility structure (VRP + IV rank)

        Agreement threshold: |value| > 0.15 and same sign.
        """
        agreeing = 0
        direction_votes = []

        # River 1: FlashAlpha structure
        if gex_result.composite_confidence > 0.30:
            direction_votes.append(gex_result.composite_value)

        # River 2: Massive.com flow (sweep + premium)
        sweep_val = flow_result.sweep_result.value
        if flow_result.sweep_result.confidence > 0.30:
            direction_votes.append(sweep_val)

        # River 3: Dark pool (Unusual Whales)
        dark_val = flow_result.dark_pool_result.value
        if flow_result.dark_pool_result.confidence > 0.30:
            direction_votes.append(dark_val)

        # River 4: DOM (Rithmic MBO) — placeholder
        # In production, this comes from the DOM signal module
        # For now, use net_premium as a rough proxy
        if abs(state.net_premium_5m) > 5.0:
            direction_votes.append(1.0 if state.net_premium_5m > 0 else -1.0)

        # River 5: Volatility structure — placeholder
        # In production, this comes from the volatility signal module
        # VIX direction as rough proxy
        if state.vix > 0:
            # High VIX = bearish pressure, low VIX = bullish
            vix_signal = -0.5 if state.vix > 25 else 0.3 if state.vix < 15 else 0.0
            if abs(vix_signal) > 0.15:
                direction_votes.append(vix_signal)

        if not direction_votes:
            return 0

        # Count votes that agree with the majority direction
        majority_sign = 1 if sum(direction_votes) > 0 else -1
        agreeing = sum(
            1 for v in direction_votes
            if abs(v) > 0.15 and (v > 0) == (majority_sign > 0)
        )

        return min(5, agreeing)

    def _time_of_day_multiplier(self) -> tuple[float, str]:
        """
        Adjust options signal weight based on time of day (ET).

        0DTE options dominate after 2 PM ET — gamma and charm effects intensify.
        Opening hour (9:30-10:30) has high noise — reduce weight slightly.
        """
        import datetime
        import zoneinfo

        now_et = datetime.datetime.now(tz=zoneinfo.ZoneInfo("America/New_York"))
        hour = now_et.hour
        minute = now_et.minute
        time_decimal = hour + minute / 60.0

        if time_decimal < 9.5:
            # Pre-market
            return 0.70, "pre_market"
        elif time_decimal < 10.5:
            # Opening hour: high noise
            return 0.85, "open"
        elif time_decimal < 14.0:
            # Midday: normal
            return 1.00, "midday"
        elif time_decimal < 15.0:
            # Power hour: 0DTE intensifies
            return 1.15, "power_hour"
        elif time_decimal < 16.0:
            # Last hour: 0DTE charm/gamma at maximum
            return 1.25, "close"
        else:
            # After close
            return 0.50, "after_close"
```

---

## Integration with the 44-Signal Engine

```python
# deep6/signals/engine/signal_aggregator.py
"""
Pattern for how the 44-signal engine consumes the options category score.

The engine maintains a list of all signal categories. Each category produces
a (value, confidence, weight) tuple. The engine computes a weighted average.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from deep6.signals.options.composite_scoring import CompositeOptionsScore, OptionsScoreBreakdown
from deep6.signals.options.types import OptionsState


@dataclass
class CategoryContribution:
    """Single category's contribution to the 44-signal composite."""
    category_name: str
    value: float           # -1.0 to +1.0
    confidence: float      # 0.0 to 1.0
    effective_weight: float  # After all multipliers applied
    raw_weight: float      # Base weight before multipliers


class SignalCategory44(Protocol):
    """Protocol that all signal categories must implement."""
    async def get_contribution(self) -> CategoryContribution: ...


class FortyFourSignalAggregator:
    """
    Aggregates all signal categories into the final composite score.

    The options category is one of several. The final score is a
    confidence-weighted average of all category contributions.
    """

    def __init__(self) -> None:
        self.options_scorer = CompositeOptionsScore(category_weight=0.30)
        # Other categories registered here (microstructure, Kronos, DOM, etc.)
        self._other_categories: list = []

    async def compute_options_contribution(
        self, options_state: OptionsState
    ) -> CategoryContribution:
        breakdown = await self.options_scorer.compute(options_state)

        return CategoryContribution(
            category_name="options",
            value=breakdown.composite_value,
            confidence=breakdown.composite_confidence,
            effective_weight=breakdown.effective_weight,
            raw_weight=breakdown.category_weight,
        )

    def aggregate(self, contributions: list[CategoryContribution]) -> dict:
        """
        Weighted average of all category contributions.

        Uses confidence-scaled values: each category's contribution is
        value * confidence * effective_weight.
        """
        total_weight = sum(c.effective_weight for c in contributions)
        if total_weight == 0:
            return {"composite_score": 0.0, "composite_confidence": 0.0}

        weighted_value = sum(
            c.value * c.confidence * c.effective_weight
            for c in contributions
        ) / total_weight

        weighted_confidence = sum(
            c.confidence * c.effective_weight
            for c in contributions
        ) / total_weight

        # Normalize to -100 to +100 for the bias score output
        bias_score = weighted_value * 100.0

        return {
            "composite_score": round(bias_score, 2),
            "composite_confidence": round(weighted_confidence, 4),
            "category_breakdown": {
                c.category_name: {
                    "value": c.value,
                    "confidence": c.confidence,
                    "effective_weight": c.effective_weight,
                }
                for c in contributions
            },
        }
```

---

## Conviction Matrix Integration

```python
# deep6/signals/options/conviction.py
"""
Conviction matrix: how many rivers agree determines the weight multiplier.

Theory: options-bias-engine/step4-cross-validation/conviction-matrix.md

This module provides the conviction assessment as a standalone utility
so it can be used by both the options scorer and the main engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConvictionLevel(str, Enum):
    MAXIMUM  = "maximum"   # 5/5 rivers agree
    HIGH     = "high"      # 4/5
    MODERATE = "moderate"  # 3/5
    LOW      = "low"       # 2/5
    MINIMAL  = "minimal"   # 1/5
    NONE     = "none"      # 0/5


@dataclass
class ConvictionAssessment:
    level: ConvictionLevel
    rivers_agreeing: int
    multiplier: float
    recommended_size: str   # "full", "standard", "half", "quarter", "none"
    reasoning: str


_CONVICTION_TABLE: dict[int, tuple[ConvictionLevel, float, str, str]] = {
    5: (ConvictionLevel.MAXIMUM,  1.00, "full",     "All 5 rivers agree — maximum conviction"),
    4: (ConvictionLevel.HIGH,     0.80, "standard", "4/5 rivers agree — high conviction"),
    3: (ConvictionLevel.MODERATE, 0.50, "half",     "3/5 rivers agree — moderate, half size or wait"),
    2: (ConvictionLevel.LOW,      0.20, "quarter",  "2/5 rivers agree — significant conflict, avoid"),
    1: (ConvictionLevel.MINIMAL,  0.05, "none",     "1/5 rivers agree — no trade"),
    0: (ConvictionLevel.NONE,     0.00, "none",     "No agreement — no trade"),
}


def assess_conviction(rivers_agreeing: int) -> ConvictionAssessment:
    rivers_agreeing = max(0, min(5, rivers_agreeing))
    level, multiplier, size, reasoning = _CONVICTION_TABLE[rivers_agreeing]
    return ConvictionAssessment(
        level=level,
        rivers_agreeing=rivers_agreeing,
        multiplier=multiplier,
        recommended_size=size,
        reasoning=reasoning,
    )


def apply_conviction_to_weight(
    base_weight: float,
    rivers_agreeing: int,
    min_weight: float = 0.0,
) -> float:
    """
    Apply conviction multiplier to a base weight.
    Never goes below min_weight (default 0.0).
    """
    assessment = assess_conviction(rivers_agreeing)
    return max(min_weight, base_weight * assessment.multiplier)
```

---

## Regime-Conditional Weighting Reference

```python
# deep6/signals/options/regime_weights.py
"""
Complete reference for how regime affects signal weights throughout the system.

This is the single source of truth for regime-conditional weighting.
Import from here rather than hardcoding regime logic in individual signals.
"""
from __future__ import annotations

from typing import TypedDict


class RegimeWeightConfig(TypedDict):
    # Options category weight in the 44-signal engine
    options_category_weight: float
    # Within options: GEX vs flow vs volatility
    gex_subcategory_weight: float
    flow_subcategory_weight: float
    volatility_subcategory_weight: float
    # Within GEX: which sub-signals matter most
    gex_regime_weight: float
    gex_wall_weight: float
    gex_flip_weight: float
    gex_profile_weight: float
    # Within flow: which sub-signals matter most
    flow_state_weight: float
    sweep_weight: float
    dark_pool_weight: float
    oi_weight: float
    pc_ratio_weight: float
    # Pre-event suppression factor
    pre_event_suppression: float


REGIME_WEIGHT_CONFIGS: dict[str, RegimeWeightConfig] = {
    "A": {  # Positive gamma, between walls — range mode
        "options_category_weight": 0.32,
        "gex_subcategory_weight": 0.50,
        "flow_subcategory_weight": 0.35,
        "volatility_subcategory_weight": 0.15,
        "gex_regime_weight": 0.30,
        "gex_wall_weight": 0.40,
        "gex_flip_weight": 0.20,
        "gex_profile_weight": 0.10,
        "flow_state_weight": 0.35,
        "sweep_weight": 0.20,
        "dark_pool_weight": 0.25,
        "oi_weight": 0.12,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "B": {  # At call wall — ceiling test
        "options_category_weight": 0.35,
        "gex_subcategory_weight": 0.55,
        "flow_subcategory_weight": 0.30,
        "volatility_subcategory_weight": 0.15,
        "gex_regime_weight": 0.25,
        "gex_wall_weight": 0.50,
        "gex_flip_weight": 0.15,
        "gex_profile_weight": 0.10,
        "flow_state_weight": 0.35,
        "sweep_weight": 0.25,
        "dark_pool_weight": 0.22,
        "oi_weight": 0.10,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "C": {  # At put wall — highest win-rate long
        "options_category_weight": 0.38,
        "gex_subcategory_weight": 0.55,
        "flow_subcategory_weight": 0.30,
        "volatility_subcategory_weight": 0.15,
        "gex_regime_weight": 0.25,
        "gex_wall_weight": 0.50,
        "gex_flip_weight": 0.15,
        "gex_profile_weight": 0.10,
        "flow_state_weight": 0.35,
        "sweep_weight": 0.25,
        "dark_pool_weight": 0.22,
        "oi_weight": 0.10,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "D": {  # Negative gamma above flip — unstable bullish
        "options_category_weight": 0.28,
        "gex_subcategory_weight": 0.35,
        "flow_subcategory_weight": 0.50,
        "volatility_subcategory_weight": 0.15,
        "gex_regime_weight": 0.30,
        "gex_wall_weight": 0.20,
        "gex_flip_weight": 0.40,
        "gex_profile_weight": 0.10,
        "flow_state_weight": 0.30,
        "sweep_weight": 0.30,
        "dark_pool_weight": 0.22,
        "oi_weight": 0.10,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "E": {  # Negative gamma below flip — trend bear
        "options_category_weight": 0.28,
        "gex_subcategory_weight": 0.30,
        "flow_subcategory_weight": 0.55,
        "volatility_subcategory_weight": 0.15,
        "gex_regime_weight": 0.35,
        "gex_wall_weight": 0.15,
        "gex_flip_weight": 0.40,
        "gex_profile_weight": 0.10,
        "flow_state_weight": 0.30,
        "sweep_weight": 0.30,
        "dark_pool_weight": 0.22,
        "oi_weight": 0.10,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "F": {  # Pin regime
        "options_category_weight": 0.30,
        "gex_subcategory_weight": 0.40,
        "flow_subcategory_weight": 0.35,
        "volatility_subcategory_weight": 0.25,
        "gex_regime_weight": 0.10,
        "gex_wall_weight": 0.20,
        "gex_flip_weight": 0.10,
        "gex_profile_weight": 0.60,
        "flow_state_weight": 0.35,
        "sweep_weight": 0.20,
        "dark_pool_weight": 0.22,
        "oi_weight": 0.15,
        "pc_ratio_weight": 0.08,
        "pre_event_suppression": 1.0,
    },
    "G": {  # Pre-event — suppressed
        "options_category_weight": 0.15,   # Halved
        "gex_subcategory_weight": 0.33,
        "flow_subcategory_weight": 0.33,
        "volatility_subcategory_weight": 0.34,
        "gex_regime_weight": 0.25,
        "gex_wall_weight": 0.25,
        "gex_flip_weight": 0.25,
        "gex_profile_weight": 0.25,
        "flow_state_weight": 0.25,
        "sweep_weight": 0.25,
        "dark_pool_weight": 0.25,
        "oi_weight": 0.13,
        "pc_ratio_weight": 0.12,
        "pre_event_suppression": 0.40,
    },
}


def get_regime_config(regime: str) -> RegimeWeightConfig:
    return REGIME_WEIGHT_CONFIGS.get(regime.upper(), REGIME_WEIGHT_CONFIGS["A"])
```

---

## Score Output Format

```python
# deep6/signals/options/output.py
"""
Final score output format compatible with the main signal engine and
the FastAPI dashboard endpoint.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any

from deep6.signals.options.composite_scoring import OptionsScoreBreakdown
from deep6.signals.options.conviction import assess_conviction, ConvictionAssessment


@dataclass
class OptionsSignalOutput:
    """
    The complete options signal output.
    Serialized to JSON for the FastAPI /signals/options endpoint.
    Consumed by the 44-signal engine as a CategoryContribution.
    """
    # Core outputs
    bias_score: float           # -100 to +100 (composite_value * 100)
    confidence: float           # 0.0 to 1.0
    direction: str              # "bullish", "bearish", "neutral"
    conviction: ConvictionAssessment

    # Category breakdown
    gex_score: float            # -100 to +100
    gex_confidence: float
    flow_score: float           # -100 to +100
    flow_confidence: float

    # Context
    regime: str
    session_phase: str
    effective_weight: float

    # Metadata
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_breakdown(cls, breakdown: OptionsScoreBreakdown) -> "OptionsSignalOutput":
        score = breakdown.composite_value * 100.0
        conviction = assess_conviction(breakdown.rivers_agreeing)

        if score > 10:
            direction = "bullish"
        elif score < -10:
            direction = "bearish"
        else:
            direction = "neutral"

        return cls(
            bias_score=round(score, 2),
            confidence=breakdown.composite_confidence,
            direction=direction,
            conviction=conviction,
            gex_score=round(breakdown.gex_value * 100.0, 2),
            gex_confidence=breakdown.gex_confidence,
            flow_score=round(breakdown.flow_value * 100.0, 2),
            flow_confidence=breakdown.flow_confidence,
            regime=breakdown.regime,
            session_phase=breakdown.session_phase,
            effective_weight=breakdown.effective_weight,
            metadata=breakdown.metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["conviction"] = {
            "level": self.conviction.level.value,
            "rivers_agreeing": self.conviction.rivers_agreeing,
            "multiplier": self.conviction.multiplier,
            "recommended_size": self.conviction.recommended_size,
            "reasoning": self.conviction.reasoning,
        }
        return d
```

---

## FastAPI Endpoint Pattern

```python
# deep6/api/routes/signals.py
"""
FastAPI endpoint that exposes the options signal output.
Consumed by the Next.js dashboard via SSE.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from deep6.signals.options.composite_scoring import CompositeOptionsScore
from deep6.signals.options.output import OptionsSignalOutput
from deep6.state import get_current_options_state   # Application state singleton

router = APIRouter(prefix="/signals", tags=["signals"])
_scorer = CompositeOptionsScore()


@router.get("/options/latest")
async def get_options_signal() -> dict:
    """Single snapshot of the current options signal."""
    state = get_current_options_state()
    breakdown = await _scorer.compute(state)
    output = OptionsSignalOutput.from_breakdown(breakdown)
    return output.to_dict()


@router.get("/options/stream")
async def stream_options_signal() -> StreamingResponse:
    """
    SSE stream of options signal updates.
    Pushes a new event whenever the options state changes.
    """
    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            state = get_current_options_state()
            breakdown = await _scorer.compute(state)
            output = OptionsSignalOutput.from_breakdown(breakdown)
            data = output.to_dict()

            import json
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(30.0)   # Match FlashAlpha poll interval

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

---

## Calibration and Tuning

```python
# deep6/signals/options/calibration.py
"""
Utilities for calibrating composite score weights from backtest data.

The default weights in this file are starting points. After running
the Databento historical replay (see hermes-backtest-discovery skill),
use Optuna to find optimal weights per regime.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class WeightSearchSpace:
    """Optuna search space for composite score weight optimization."""
    options_category_min: float = 0.15
    options_category_max: float = 0.45
    gex_subcategory_min: float = 0.25
    gex_subcategory_max: float = 0.65
    flow_subcategory_min: float = 0.20
    flow_subcategory_max: float = 0.60


def build_optuna_objective(
    historical_snapshots: list[dict],
    forward_return_fn: Callable[[float, int], float],
    regime_filter: str | None = None,
) -> Callable:
    """
    Build an Optuna objective function for weight optimization.

    historical_snapshots: list of {timestamp, options_state, nq_price}
    forward_return_fn: given (timestamp, bars_forward) → NQ return
    regime_filter: if set, only optimize for this regime (e.g., "E")
    """
    def objective(trial) -> float:
        import optuna

        cat_weight = trial.suggest_float("options_category_weight", 0.15, 0.45)
        gex_weight = trial.suggest_float("gex_subcategory_weight", 0.25, 0.65)
        flow_weight = 1.0 - gex_weight - 0.15  # volatility fixed at 0.15

        if flow_weight < 0.20:
            raise optuna.exceptions.TrialPruned()

        # Evaluate on historical data
        total_pnl = 0.0
        count = 0

        for snap in historical_snapshots:
            if regime_filter and snap.get("regime") != regime_filter:
                continue

            # Simplified: use composite value as trade direction
            # In production, apply full signal pipeline
            signal_value = snap.get("composite_value", 0.0)
            if abs(signal_value) < 0.20:
                continue  # No trade

            direction = 1 if signal_value > 0 else -1
            forward_return = forward_return_fn(snap["timestamp"], 5)
            pnl = direction * forward_return
            total_pnl += pnl
            count += 1

        return total_pnl / max(count, 1)

    return objective
```

---

## Integration Checklist

When wiring the options composite score into the 44-signal engine:

1. Instantiate `CompositeOptionsScore` once at startup (not per-tick)
2. Call `compute(options_state)` on each FlashAlpha poll (every 30-60 sec)
3. Pass `breakdown.composite_value` and `breakdown.effective_weight` to the aggregator
4. Log `breakdown.rivers_agreeing` and `breakdown.conviction_multiplier` for observability
5. Expose `OptionsSignalOutput.to_dict()` via the FastAPI `/signals/options/latest` endpoint
6. Subscribe the Next.js dashboard to `/signals/options/stream` for live updates
7. After 2 weeks of live data, run Optuna calibration on the weight search space
8. Regime G (pre-event): verify the 40% suppression fires correctly before FOMC/CPI events
9. Time-of-day multiplier: verify the 1.25x power-hour boost activates after 3 PM ET
10. Conviction matrix: log all 5-river agreement events — these are the highest-alpha setups
