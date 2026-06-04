"""GEX/Options domain adapter — translates NQ Atlas GEX state into DomainScore -3..+3.

Consumes pre-computed GEX data from either:
  1. Direct injection (GEXSnapshot dataclass) — preferred in-process path
  2. NQ Atlas HTTP endpoint (http://localhost:8766/gex) — out-of-process fallback

Scoring components (each +/-1, total +/-3):
  1. GEX regime: positive gamma = dampener (bearish lean), negative = amplifier (bullish lean)
     - Actually: positive gamma is range-bound (no directional score),
       negative gamma amplifies the *existing* directional signal.
     - Regime contributes directional context, not direction itself.
  2. Dealer delta (DEX proxy): net_gex sign + call/put wall asymmetry
     - Price closer to call wall = resistance = bearish (-1)
     - Price closer to put wall = support = bullish (+1)
     - Equidistant = neutral (0)
  3. GEX flip proximity: price vs gamma flip level
     - Above flip with positive GEX = bullish (+1)
     - Below flip with negative GEX = bearish (-1)
     - Crossing flip = regime transition signal

Stale: data older than STALE_SECONDS (120s) → stale=True.
Cold start (None input) → available=False, score=0.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from deep6.engines.bias_contracts import DomainScore
from deep6.engines.signal_config import GEXOptionsDomainConfig


@dataclass(slots=True)
class GEXSnapshot:
    """Pre-computed GEX state for domain scoring.

    Populated from NQ Atlas /gex endpoint or from direct FlashAlpha client.
    All prices are in NQ points (not QQQ).
    """
    spot: float                 # Current NQ price (or QQQ if nq_levels unavailable)
    flip_level: float           # Gamma flip / zero-gamma price
    call_wall: float            # Highest call-gamma strike (resistance)
    put_wall: float             # Highest put-gamma strike (support)
    net_gex: float              # Net gamma exposure (positive = range-bound)
    regime_sign: int            # +1 positive, -1 negative, 0 neutral
    flow_direction: int = 0     # Net options flow direction: +1 bull, -1 bear, 0 neutral
    updated_at: float = 0.0     # Unix timestamp


class GEXOptionsDomain:
    """Scores directional bias from dealer gamma positioning.

    Three components, each +/-1 (total range -3..+3):
      1. Wall proximity — where is price relative to call/put walls?
      2. Flip relationship — price above or below gamma flip?
      3. Flow direction — net options premium direction (if available)
    """

    MAX_RANGE = 3
    DOMAIN = "gex"

    def __init__(self, config: Optional[GEXOptionsDomainConfig] = None) -> None:
        self._config = config or GEXOptionsDomainConfig()

    def compute(
        self,
        snapshot: Optional[GEXSnapshot],
        nq_price: Optional[float] = None,
    ) -> DomainScore:
        """Translate GEX state into a v3 DomainScore.

        Args:
            snapshot: GEX data from NQ Atlas or direct client. None = cold start.
            nq_price: Override NQ price if snapshot.spot is QQQ-based.
        """
        now = time.time()

        if snapshot is None:
            return DomainScore(
                domain=self.DOMAIN,
                score=0,
                max_range=0,
                available=False,
                stale=False,
                detail={"reason": "gex_unavailable"},
                updated_at=now,
            )

        stale = False
        if snapshot.updated_at > 0:
            stale = (now - snapshot.updated_at) > self._config.stale_threshold_sec

        price = nq_price if nq_price and nq_price > 0 else snapshot.spot
        if price <= 0:
            return DomainScore(
                domain=self.DOMAIN,
                score=0,
                max_range=0,
                available=False,
                stale=stale,
                detail={"reason": "no_price"},
                updated_at=now,
            )

        # Component 1: Wall proximity (-1 / 0 / +1)
        wall_score = self._wall_proximity_score(
            price, snapshot.call_wall, snapshot.put_wall
        )

        # Component 2: Flip relationship (-1 / 0 / +1)
        flip_score = self._flip_score(price, snapshot.flip_level, snapshot.regime_sign)

        # Component 3: Flow direction (-1 / 0 / +1)
        flow_score = self._flow_score(snapshot.flow_direction)

        total = max(-self.MAX_RANGE, min(self.MAX_RANGE, wall_score + flip_score + flow_score))

        return DomainScore(
            domain=self.DOMAIN,
            score=total,
            max_range=self.MAX_RANGE,
            available=True,
            stale=stale,
            detail={
                "wall_component": wall_score,
                "flip_component": flip_score,
                "flow_component": flow_score,
                "spot": round(price, 2),
                "flip_level": round(snapshot.flip_level, 2),
                "call_wall": round(snapshot.call_wall, 2),
                "put_wall": round(snapshot.put_wall, 2),
                "net_gex": snapshot.net_gex,
                "regime_sign": snapshot.regime_sign,
                "flow_direction": snapshot.flow_direction,
            },
            updated_at=snapshot.updated_at if snapshot.updated_at > 0 else now,
        )

    def _wall_proximity_score(
        self, price: float, call_wall: float, put_wall: float
    ) -> int:
        """Score based on where price sits relative to call/put walls.

        Near call wall = resistance = bearish (-1)
        Near put wall = support = bullish (+1)
        Middle = neutral (0)
        """
        if call_wall <= 0 or put_wall <= 0 or call_wall <= put_wall:
            return 0

        wall_range = call_wall - put_wall
        if wall_range <= 0:
            return 0

        # Normalized position: 0.0 = at put wall, 1.0 = at call wall
        position = (price - put_wall) / wall_range
        position = max(0.0, min(1.0, position))

        threshold = self._config.wall_proximity_threshold
        if position >= (1.0 - threshold):
            return -1  # Near call wall = bearish resistance
        if position <= threshold:
            return 1   # Near put wall = bullish support
        return 0       # Middle ground

    def _flip_score(self, price: float, flip_level: float, regime_sign: int) -> int:
        """Score based on price relationship to gamma flip level.

        Above flip in positive gamma = bullish (dealers support rallies)
        Below flip in negative gamma = bearish (dealers amplify selling)
        """
        if flip_level <= 0:
            return 0

        above_flip = price > flip_level

        if regime_sign > 0:
            # Positive gamma: price above flip = range-bound bullish support
            return 1 if above_flip else -1
        elif regime_sign < 0:
            # Negative gamma: price below flip = amplified bearish
            return -1 if not above_flip else 1
        else:
            # Neutral regime: flip level still matters as a reference
            return 1 if above_flip else -1

    def _flow_score(self, flow_direction: int) -> int:
        """Direct pass-through of net options flow direction."""
        if flow_direction > 0:
            return 1
        elif flow_direction < 0:
            return -1
        return 0


__all__ = ["GEXOptionsDomain", "GEXSnapshot"]
