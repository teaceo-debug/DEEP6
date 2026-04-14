"""VPINEngine — Volume-Synchronized Probability of Informed Trading.

Reference: Easley, López de Prado, O'Hara (2011) "The Volume Clock: Insights
into the High Frequency Paradigm." Review of Financial Studies.

DEEP6 adaptation
----------------
This implementation uses DEEP6's exact aggressor split (DATA-02 verified) rather
than Bulk Volume Classification (BVC / normal-CDF), because DEEP6 already knows
which side hit the trade per tick. BVC is a workaround for systems lacking
aggressor data and is strictly less accurate than exact split — it is therefore
FORBIDDEN in this module (enforced by tests/orderflow/test_vpin.py
::test_no_bvc_path).

Integration pattern
-------------------
* One VPINEngine instance per timeframe (currently 1m only) lives on SharedState
* SharedState.on_bar_close calls engine.update_from_bar(bar) BEFORE scoring
* scorer.score_bar receives vpin_modifier=engine.get_confidence_modifier()
* The modifier is applied ONLY to the final fused score, AFTER the IB multiplier,
  BEFORE clip. It never stacks with IB on per-signal scores (footgun; see
  12-01-PLAN.md FOOTGUN 1).

Semantics
---------
* Volume clock: one bucket = 1000 contracts (configurable)
* Window: 50 buckets (Easley standard)
* VPIN = mean( |buy - sell| / bucket_volume ) over the last N completed buckets
* Modifier curve (continuous, linear interp over percentile of VPIN in history):
    percentile 0.0 -> 1.20x  (clean tape, expand sizing)
    percentile 0.5 -> 1.00x  (neutral)
    percentile 1.0 -> 0.20x  (toxic tape, compress sizing)
* Warmup: if fewer than `warmup_buckets` buckets completed, return neutral 1.0
  (avoids the reference impl's NaN-saturation path).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Tuple

import structlog

log = structlog.get_logger(__name__)


class FlowRegime(str, Enum):
    """Qualitative flow-toxicity regime derived from current VPIN percentile."""
    CLEAN = "CLEAN"           # percentile < 0.3
    NORMAL = "NORMAL"         # 0.3 <= percentile < 0.7
    ELEVATED = "ELEVATED"     # 0.7 <= percentile < 0.9
    TOXIC = "TOXIC"           # percentile >= 0.9


# Modifier curve keypoints (percentile -> multiplier)
# Linear interp between them; neutral at 0.5.
_MODIFIER_MIN = 0.20
_MODIFIER_MAX = 1.20
_MODIFIER_MID = 1.00


class VPINEngine:
    """Compute a continuous confidence multiplier in [0.2, 1.2] from VPIN.

    All methods are synchronous and O(1) per call (with a one-time O(H) sort
    inside get_percentile when history has been repopulated). Safe to call
    directly from the single-event-loop on_bar_close path — no I/O, no locks.
    """

    def __init__(
        self,
        bucket_volume: int = 1000,
        num_buckets: int = 50,
        history_size: int = 2000,
        warmup_buckets: int = 10,
    ) -> None:
        if bucket_volume <= 0:
            raise ValueError("bucket_volume must be positive")
        if num_buckets <= 0:
            raise ValueError("num_buckets must be positive")
        if warmup_buckets < 0:
            raise ValueError("warmup_buckets must be >= 0")

        self.bucket_volume = int(bucket_volume)
        self.num_buckets = int(num_buckets)
        self.history_size = int(history_size)
        self.warmup_buckets = int(warmup_buckets)

        # Mutable state — accumulator for the in-progress bucket
        self._bucket_buy_accum: float = 0.0
        self._bucket_sell_accum: float = 0.0
        self._bucket_vol_accum: float = 0.0

        # Rolling window of the last `num_buckets` completed (buy, sell) pairs
        self.completed_buckets: Deque[Tuple[float, float]] = deque(maxlen=num_buckets)

        # Long history of VPIN values for percentile ranking
        self._vpin_history: Deque[float] = deque(maxlen=history_size)

        # Running counter — counts TOTAL buckets completed since engine start,
        # not just the rolling window size.
        self.buckets_completed: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_from_bar(self, bar) -> None:
        """Fold one FootprintBar into the volume clock.

        Uses the exact aggressor split from bar.levels:
            buy  = sum(level.ask_vol)   [aggressor=BUY hit the ask]
            sell = sum(level.bid_vol)   [aggressor=SELL hit the bid]
        which exactly matches DEEP6's DATA-02 contract.

        A single large-volume bar may complete multiple buckets; volume is
        spilled proportionally, preserving the bar's buy/sell ratio for each
        spill segment.
        """
        total_vol = int(getattr(bar, "total_vol", 0))
        if total_vol <= 0:
            # Malformed / empty bar — no-op (threat T-12-01-01 mitigation)
            return

        buy_vol = 0.0
        sell_vol = 0.0
        levels = getattr(bar, "levels", None)
        if levels:
            for lv in levels.values():
                buy_vol += float(getattr(lv, "ask_vol", 0))
                sell_vol += float(getattr(lv, "bid_vol", 0))

        bar_volume = buy_vol + sell_vol
        if bar_volume <= 0.0:
            return

        # Proportional spill: split the bar's volume across as many buckets as
        # needed to preserve buy/sell ratio per segment.
        buy_ratio = buy_vol / bar_volume
        sell_ratio = sell_vol / bar_volume

        remaining = bar_volume
        while remaining > 0.0:
            space = self.bucket_volume - self._bucket_vol_accum
            if remaining >= space:
                # Fill the rest of the current bucket at the bar's buy/sell ratio
                self._bucket_buy_accum += space * buy_ratio
                self._bucket_sell_accum += space * sell_ratio
                self._bucket_vol_accum += space
                remaining -= space
                self._complete_bucket()
            else:
                self._bucket_buy_accum += remaining * buy_ratio
                self._bucket_sell_accum += remaining * sell_ratio
                self._bucket_vol_accum += remaining
                remaining = 0.0

    def get_vpin(self) -> float:
        """Rolling-window VPIN in [0, 1].

        VPIN = mean( |buy - sell| / bucket_volume ) across completed buckets.
        """
        if not self.completed_buckets:
            return 0.0
        total = 0.0
        for buy, sell in self.completed_buckets:
            total += abs(buy - sell) / self.bucket_volume
        return total / len(self.completed_buckets)

    def get_percentile(self) -> float:
        """Percentile rank of current VPIN within the long history deque, in [0,1].

        Returns 0.5 if history has fewer than `warmup_buckets` samples (caller
        should typically short-circuit on warmup anyway).
        """
        if len(self._vpin_history) < max(self.warmup_buckets, 2):
            return 0.5
        current = self.get_vpin()
        count_below = sum(1 for v in self._vpin_history if v < current)
        return count_below / len(self._vpin_history)

    def get_confidence_modifier(self) -> float:
        """Confidence multiplier with floor at 0.65 (TIER-1 FIX 5).

        Returns neutral 1.0 during warmup (< warmup_buckets completed).
        Uses FlowRegime-based quantization rather than linear interp:
            CLEAN / NORMAL  -> 1.0
            ELEVATED        -> 0.85
            TOXIC           -> 0.65 (floor, was 0.20)
        The previous 0.20-0.40 range over-dampened tradeable signals during
        toxic flow when the signal itself was correct.
        """
        if self.buckets_completed < self.warmup_buckets:
            return _MODIFIER_MID

        regime = self.get_flow_regime()
        if regime == FlowRegime.TOXIC:
            return 0.65  # floor, was 0.20
        if regime == FlowRegime.ELEVATED:
            return 0.85  # was 0.6-0.8
        return 1.0

    def should_block_type_a(
        self, raw_vpin_gate: float = 0.40, pct_gate: float = 0.95
    ) -> bool:
        """TIER-1 FIX 5: Absolute VPIN gate for TYPE_A blocking.

        Binary block when BOTH conditions hold:
            - raw VPIN > raw_vpin_gate (default 0.40)
            - percentile > pct_gate (default 0.95)
        When true, TYPE_A signals should be suppressed entirely — extreme
        flow toxicity is not salvageable by sizing reduction alone.
        """
        if self.buckets_completed < self.warmup_buckets:
            return False
        return self.get_vpin() > raw_vpin_gate and self.get_percentile() > pct_gate

    def get_flow_regime(self) -> FlowRegime:
        """Qualitative regime label derived from current VPIN percentile."""
        if self.buckets_completed < self.warmup_buckets:
            return FlowRegime.NORMAL
        pct = self.get_percentile()
        if pct < 0.3:
            return FlowRegime.CLEAN
        if pct < 0.7:
            return FlowRegime.NORMAL
        if pct < 0.9:
            return FlowRegime.ELEVATED
        return FlowRegime.TOXIC

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _complete_bucket(self) -> None:
        """Finalize the in-progress bucket and roll forward."""
        buy = self._bucket_buy_accum
        sell = self._bucket_sell_accum
        self.completed_buckets.append((buy, sell))
        self.buckets_completed += 1

        # Append VPIN snapshot to long history
        vpin_now = self.get_vpin()
        self._vpin_history.append(vpin_now)

        log.debug(
            "vpin.bucket_complete",
            buckets_completed=self.buckets_completed,
            buy=round(buy, 2),
            sell=round(sell, 2),
            vpin=round(vpin_now, 4),
        )

        # Reset accumulator
        self._bucket_buy_accum = 0.0
        self._bucket_sell_accum = 0.0
        self._bucket_vol_accum = 0.0
