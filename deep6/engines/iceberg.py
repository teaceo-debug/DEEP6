"""E4 IcebergEngine — ENG-04. Native and synthetic iceberg detection.

Detects two variants of iceberg order activity:
  - NATIVE: trade fill size > displayed DOM depth at that price × native_ratio (D-08)
  - SYNTHETIC: same price level refills to >= peak_size * refill_ratio within
               refill_window_ms of being depleted (D-09)

Conviction bonus: +3 when iceberg fires at a registered absorption zone (D-10).

Usage:
    engine = IcebergEngine()

    # On each trade callback (from async-rithmic LAST_TRADE):
    signal = engine.check_trade(price, size, aggressor_side, dom_snapshot, timestamp)

    # On each periodic DOM snapshot (100ms timer):
    engine.update_dom(bid_prices, bid_sizes, ask_prices, ask_sizes, timestamp)

    # When absorption engine registers a zone:
    engine.mark_absorption_zone(price, radius_ticks=4)

    # Session boundary:
    engine.reset()

Per D-13: Returns None when dom_snapshot is None or trade data is insufficient.
All price-level dict lookups use round(price / 0.25) * 0.25 for consistent keys.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from deep6.engines.signal_config import IcebergConfig
from deep6.state.dom import LEVELS

# Tick size for NQ futures
_NQ_TICK = 0.25


def _round_price(price: float) -> float:
    """Round price to nearest NQ tick (0.25) for consistent dict keys."""
    return round(price / _NQ_TICK) * _NQ_TICK


class IcebergType(Enum):
    """Iceberg order signal variants (ENG-04)."""
    NATIVE = auto()      # Trade fill > DOM displayed size at that level * ratio
    SYNTHETIC = auto()   # Level refills rapidly after depletion (N times within window)


@dataclass
class IcebergSignal:
    """A single iceberg detection signal.

    Fields:
        iceberg_type:      NATIVE or SYNTHETIC.
        price:             Price level where iceberg was detected.
        size:              Trade size (native) or refill size (synthetic).
        refill_count:      Number of refills detected (0 for NATIVE).
        at_absorption_zone: True if price is within a registered absorption zone.
        conviction_bonus:  +3 if at absorption zone (D-10), else 0.
        direction:         +1 = bid-side iceberg (buying), -1 = ask-side (selling), 0 = unknown.
        detail:            Diagnostic string.
    """
    iceberg_type: IcebergType
    price: float
    size: float
    refill_count: int
    at_absorption_zone: bool
    conviction_bonus: int
    direction: int
    detail: str


class IcebergEngine:
    """E4 Iceberg detection engine — native fills and synthetic refills (ENG-04).

    State is per-instance. Engine is NOT stateless (tracks DOM history per level).
    Call reset() at session boundaries.

    Thread safety: Designed for asyncio single-threaded use.
    """

    def __init__(self, config: IcebergConfig | None = None) -> None:
        self.config = config if config is not None else IcebergConfig()

        # Per-level depletion timestamp deques (D-09: bounded)
        self._level_depletions: dict[float, deque] = {}
        # Last observed size per price level
        self._level_prior_sizes: dict[float, float] = {}
        # Pre-depletion peak size (key decision: required for refill comparison)
        self._level_peak_sizes: dict[float, float] = {}
        # Refill count per level
        self._refill_counts: dict[float, int] = {}
        # Absorption zones: set of rounded prices within marked zones
        self._absorption_zone_prices: set[float] = set()

    # ------------------------------------------------------------------
    # Public: NATIVE iceberg detection
    # ------------------------------------------------------------------

    def check_trade(
        self,
        price: float,
        size: float,
        aggressor_side: int,
        dom_snapshot: tuple | None,
        timestamp: float | None = None,
    ) -> Optional[IcebergSignal]:
        """Check if a trade constitutes a native iceberg (fill > DOM depth at price).

        Args:
            price:          Trade execution price.
            size:           Trade size (contracts).
            aggressor_side: +1 = buy aggressor (hitting ask), -1 = sell aggressor (hitting bid).
                            0 = unknown.
            dom_snapshot:   (bid_prices, bid_sizes, ask_prices, ask_sizes) from DOMState.
                            If None — returns None (D-13).
            timestamp:      time.monotonic() at trade time; defaults to now.

        Returns:
            IcebergSignal if NATIVE iceberg detected, else None.
        """
        if dom_snapshot is None:
            return None

        if timestamp is None:
            timestamp = time.monotonic()

        cfg = self.config
        rounded_price = _round_price(price)

        # Find DOM size at this price level based on aggressor side
        dom_size = self._get_dom_size_at_price(rounded_price, aggressor_side, dom_snapshot)

        if dom_size is None or dom_size < cfg.iceberg_min_size:
            return None

        # D-08: Native iceberg = trade fill > displayed DOM depth * native_ratio
        if size <= dom_size * cfg.native_ratio:
            return None

        at_zone = self.is_at_absorption_zone(rounded_price)
        conviction_bonus = cfg.conviction_bonus_at_zone if at_zone else 0

        # Direction: buy aggressor = iceberg buying (absorbs asks), direction +1
        direction = aggressor_side if aggressor_side in (1, -1) else 0

        return IcebergSignal(
            iceberg_type=IcebergType.NATIVE,
            price=rounded_price,
            size=size,
            refill_count=0,
            at_absorption_zone=at_zone,
            conviction_bonus=conviction_bonus,
            direction=direction,
            detail=(
                f"NATIVE ICEBERG at {rounded_price:.2f}: trade {size:.0f} > "
                f"dom {dom_size:.0f} * {cfg.native_ratio} = {dom_size * cfg.native_ratio:.0f}"
            ),
        )

    # ------------------------------------------------------------------
    # Public: SYNTHETIC iceberg detection (DOM update path)
    # ------------------------------------------------------------------

    def update_dom(
        self,
        bid_prices: list[float],
        bid_sizes: list[float],
        ask_prices: list[float],
        ask_sizes: list[float],
        timestamp: float | None = None,
    ) -> list[IcebergSignal]:
        """Process a DOM snapshot update to detect synthetic iceberg refills.

        Called from the 100ms periodic timer task (NOT from the 1000/sec callback path).
        Compares current level sizes to prior sizes to detect depletion/refill cycles.

        Args:
            bid_prices: List of LEVELS bid prices.
            bid_sizes:  List of LEVELS bid sizes.
            ask_prices: List of LEVELS ask prices.
            ask_sizes:  List of LEVELS ask sizes.
            timestamp:  time.monotonic() at snapshot time; defaults to now.

        Returns:
            List of IcebergSignal (SYNTHETIC type) for each level that triggered.
        """
        if timestamp is None:
            timestamp = time.monotonic()

        cfg = self.config
        signals: list[IcebergSignal] = []
        refill_window_s = cfg.refill_window_ms / 1000.0

        # Process bid and ask sides
        for prices, sizes, side in [
            (bid_prices, bid_sizes, -1),   # bid side = sell pressure (selling iceberg)
            (ask_prices, ask_sizes, +1),   # ask side = buy pressure (buying iceberg)
        ]:
            for i in range(min(len(prices), LEVELS)):
                price = prices[i]
                size = sizes[i]
                if price == 0.0:
                    continue

                rounded_price = _round_price(price)
                prior_size = self._level_prior_sizes.get(rounded_price, size)
                peak_size = self._level_peak_sizes.get(rounded_price, prior_size)

                # Depletion detection: level drops to < depletion_threshold * peak_size
                depletion_threshold = cfg.depletion_threshold * peak_size
                if (prior_size >= cfg.iceberg_min_size and
                        size < depletion_threshold and
                        size < prior_size):
                    # Record depletion event: save peak before updating prior
                    self._level_peak_sizes[rounded_price] = prior_size
                    if rounded_price not in self._level_depletions:
                        self._level_depletions[rounded_price] = deque()
                    self._level_depletions[rounded_price].append(timestamp)

                # Refill detection: level refills to >= refill_ratio * peak_size
                if rounded_price in self._level_depletions:
                    depletions = self._level_depletions[rounded_price]
                    peak = self._level_peak_sizes.get(rounded_price, 0.0)

                    # Prune expired depletion timestamps
                    while depletions and (timestamp - depletions[0]) > refill_window_s:
                        depletions.popleft()

                    if (depletions and
                            peak >= cfg.iceberg_min_size and
                            size >= peak * cfg.refill_ratio):
                        # Refill confirmed — count it
                        self._refill_counts[rounded_price] = (
                            self._refill_counts.get(rounded_price, 0) + 1
                        )
                        refill_count = self._refill_counts[rounded_price]

                        # Clear depletions to avoid double-counting
                        depletions.clear()

                        # Only fire signal after minimum refills
                        if refill_count >= cfg.synthetic_min_refills:
                            at_zone = self.is_at_absorption_zone(rounded_price)
                            conviction_bonus = cfg.conviction_bonus_at_zone if at_zone else 0

                            signals.append(IcebergSignal(
                                iceberg_type=IcebergType.SYNTHETIC,
                                price=rounded_price,
                                size=size,
                                refill_count=refill_count,
                                at_absorption_zone=at_zone,
                                conviction_bonus=conviction_bonus,
                                direction=side,
                                detail=(
                                    f"SYNTHETIC ICEBERG at {rounded_price:.2f}: "
                                    f"{refill_count} refills within {cfg.refill_window_ms:.0f}ms; "
                                    f"peak={peak:.0f}, refill={size:.0f}"
                                ),
                            ))

                # Update prior size
                self._level_prior_sizes[rounded_price] = size

        return signals

    # ------------------------------------------------------------------
    # Public: Absorption zone management
    # ------------------------------------------------------------------

    def mark_absorption_zone(
        self, price: float, radius_ticks: int = 4
    ) -> None:
        """Mark price ± radius_ticks as an absorption zone for conviction bonus (D-10).

        Args:
            price:        Center price of the absorption zone.
            radius_ticks: Number of ticks above/below price to include.
        """
        rounded = _round_price(price)
        for i in range(-radius_ticks, radius_ticks + 1):
            zone_price = _round_price(rounded + i * _NQ_TICK)
            self._absorption_zone_prices.add(zone_price)

    def is_at_absorption_zone(self, price: float) -> bool:
        """Check if price is within a registered absorption zone.

        Args:
            price: Price to check (will be rounded to nearest tick).

        Returns:
            True if price is in an absorption zone, False otherwise.
        """
        return _round_price(price) in self._absorption_zone_prices

    # ------------------------------------------------------------------
    # Public: Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all internal state for session start or test teardown."""
        self._level_depletions.clear()
        self._level_prior_sizes.clear()
        self._level_peak_sizes.clear()
        self._refill_counts.clear()
        self._absorption_zone_prices.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_dom_size_at_price(
        self,
        rounded_price: float,
        aggressor_side: int,
        dom_snapshot: tuple,
    ) -> Optional[float]:
        """Find the displayed DOM size at a given price on the relevant side.

        For buy aggressor (hitting asks): look in ask_prices/ask_sizes.
        For sell aggressor (hitting bids): look in bid_prices/bid_sizes.
        """
        bid_prices, bid_sizes, ask_prices, ask_sizes = dom_snapshot

        if aggressor_side >= 0:
            # Buy aggressor — check ask side
            prices, sizes = ask_prices, ask_sizes
        else:
            # Sell aggressor — check bid side
            prices, sizes = bid_prices, bid_sizes

        for i in range(min(len(prices), LEVELS)):
            if abs(prices[i] - rounded_price) < _NQ_TICK / 2:
                return float(sizes[i])

        return None
