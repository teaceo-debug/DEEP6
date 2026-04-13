"""E2 TrespassEngine — ENG-02. Multi-level weighted DOM queue imbalance.

Computes a weighted bid/ask pressure ratio from DOMState snapshots.
Weight decay: weight[i] = 1/(i+1) — closer-to-best levels matter more.
Pre-computes weight array once at init (D-03: no allocations in hot path).

Usage:
    engine = TrespassEngine()  # or TrespassEngine(TrespassConfig(trespass_depth=5))
    snapshot = dom_state.snapshot()  # call once per bar close
    result = engine.process(snapshot)

Per D-13: Returns neutral (imbalance_ratio=1.0, direction=0) when DOM is unavailable.
Per D-03: process() executes in < 0.1ms — no string formatting unless debug=True.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from deep6.engines.signal_config import TrespassConfig
from deep6.state.dom import LEVELS

# Type alias: (bid_prices, bid_sizes, ask_prices, ask_sizes) — all lists of length LEVELS=40.
# Returned by DOMState.snapshot().
DOMSnapshot = tuple  # tuple[list[float], list[float], list[float], list[float]]


@dataclass
class TrespassResult:
    """Result from TrespassEngine.process().

    Fields:
        imbalance_ratio: weighted_bid / weighted_ask (1.0 = neutral).
        direction: +1 bull, -1 bear, 0 neutral.
        probability: float in [0, 1] approximating directional probability.
        depth_gradient: (bid[0] - bid[depth-1]) / depth — book thinning measure.
        detail: diagnostic string (empty in hot path; set when DOM unavailable).
    """
    imbalance_ratio: float
    direction: int
    probability: float
    depth_gradient: float
    detail: str


# Pre-built neutral results (avoid allocation on every None call — Rule 2: correctness).
_NEUTRAL_UNAVAILABLE = TrespassResult(
    imbalance_ratio=1.0,
    direction=0,
    probability=0.5,
    depth_gradient=0.0,
    detail="DOM_UNAVAILABLE",
)
_NEUTRAL_EMPTY = TrespassResult(
    imbalance_ratio=1.0,
    direction=0,
    probability=0.5,
    depth_gradient=0.0,
    detail="DOM_EMPTY",
)


class TrespassEngine:
    """E2 DOM queue imbalance engine (ENG-02).

    Instantiated once at startup, reused for every bar close.
    Weight array is pre-computed at init — no allocations in process().
    """

    def __init__(self, config: TrespassConfig | None = None) -> None:
        self.config = config if config is not None else TrespassConfig()
        # Pre-compute weight array: weights[i] = 1.0/(i+1) for i in range(LEVELS).
        # Computed once — never reallocated (D-03).
        self._weights: list[float] = [1.0 / (i + 1) for i in range(LEVELS)]

    def process(self, dom_snapshot: DOMSnapshot | None) -> TrespassResult:
        """Compute weighted DOM queue imbalance from a DOMState snapshot.

        Args:
            dom_snapshot: tuple (bid_prices, bid_sizes, ask_prices, ask_sizes)
                          from DOMState.snapshot(), or None if DOM unavailable.

        Returns:
            TrespassResult with imbalance_ratio, direction, probability,
            depth_gradient, detail. Never raises.

        Performance: < 0.1ms. No allocations beyond the result dataclass.
        """
        # T-04-04: Guard — DOM unavailable
        if dom_snapshot is None:
            return _NEUTRAL_UNAVAILABLE

        bid_prices, bid_sizes, ask_prices, ask_sizes = dom_snapshot
        depth = self.config.trespass_depth

        # T-04-04: Guard — all-zero DOM (not yet populated)
        if not any(bid_sizes[:depth]) and not any(ask_sizes[:depth]):
            return _NEUTRAL_EMPTY

        weights = self._weights

        # Weighted sums over top `depth` levels only (D-01).
        weighted_bid = 0.0
        weighted_ask = 0.0
        for i in range(depth):
            w = weights[i]
            weighted_bid += bid_sizes[i] * w
            weighted_ask += ask_sizes[i] * w

        # T-04-04: Guard div-by-zero when ask side is empty
        if weighted_ask == 0.0:
            imbalance_ratio = 0.0
            direction = -1 if weighted_bid == 0.0 else 0
            probability = 0.0
            depth_gradient = 0.0
        else:
            imbalance_ratio = weighted_bid / weighted_ask

            # Direction: D-02 heuristic thresholds
            bull_thresh = self.config.bull_ratio_threshold
            bear_thresh = self.config.bear_ratio_threshold
            if imbalance_ratio > bull_thresh:
                direction = 1
            elif imbalance_ratio < bear_thresh:
                direction = -1
            else:
                direction = 0

            # Probability: logistic approximation — min(max((ratio-1)*0.5+0.5, 0), 1)
            probability = min(max((imbalance_ratio - 1.0) * 0.5 + 0.5, 0.0), 1.0)

            # depth_gradient: (bid[0] - bid[depth-1]) / depth — measures book thinning
            depth_gradient = (bid_sizes[0] - bid_sizes[depth - 1]) / depth

        return TrespassResult(
            imbalance_ratio=imbalance_ratio,
            direction=direction,
            probability=probability,
            depth_gradient=depth_gradient,
            detail="",
        )
