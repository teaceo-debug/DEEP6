"""Auction Theory signals — 5 variants + E9 State Machine.

Auction theory views the market as a continuous two-sided auction.
Price explores until it finds acceptance (volume) or rejection (no volume).
These signals detect when auctions are complete, incomplete, or in transition.

Variants (per AUCT-01..05):
  1. Unfinished Business: non-zero bid at high / ask at low — price will return
  2. Finished Auction:    zero volume on bid at high / ask at low — exhaustion
  3. Poor High/Low:       single-print or low-volume extreme — incomplete auction
  4. Volume Void:         LVN gap within bar — fast-move zone
  5. Market Sweep:        rapid traversal with increasing volume

E9 Auction State Machine (ENG-09):
  States: EXPLORING_UP, EXPLORING_DOWN, BALANCED, BREAKOUT, BREAKDOWN
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from deep6.state.footprint import FootprintBar, tick_to_price


class AuctionType(Enum):
    UNFINISHED_BUSINESS = auto()
    FINISHED_AUCTION = auto()
    POOR_HIGH = auto()
    POOR_LOW = auto()
    VOLUME_VOID = auto()
    MARKET_SWEEP = auto()


class AuctionState(Enum):
    EXPLORING_UP = auto()
    EXPLORING_DOWN = auto()
    BALANCED = auto()
    BREAKOUT = auto()
    BREAKDOWN = auto()


@dataclass
class AuctionSignal:
    auction_type: AuctionType
    direction: int
    price: float
    strength: float
    detail: str


class AuctionEngine:
    """E9: Auction State Machine tracking market auction states."""

    def __init__(self):
        self.state: AuctionState = AuctionState.BALANCED
        self.prev_high: float = 0.0
        self.prev_low: float = float('inf')
        self.balance_count: int = 0

    def reset(self) -> None:
        self.state = AuctionState.BALANCED
        self.prev_high = 0.0
        self.prev_low = float('inf')
        self.balance_count = 0

    def process(self, bar: FootprintBar) -> list[AuctionSignal]:
        signals: list[AuctionSignal] = []

        if not bar.levels or bar.total_vol == 0:
            return signals

        sorted_ticks = sorted(bar.levels.keys())
        if len(sorted_ticks) < 2:
            return signals

        # --- 1. UNFINISHED BUSINESS (AUCT-01) ---
        high_tick = sorted_ticks[-1]
        low_tick = sorted_ticks[0]
        high_level = bar.levels[high_tick]
        low_level = bar.levels[low_tick]

        # Non-zero bid at bar high = unfinished business upward
        if high_level.bid_vol > 0:
            signals.append(AuctionSignal(
                AuctionType.UNFINISHED_BUSINESS, +1,
                tick_to_price(high_tick), 0.6,
                f"UNFINISHED BUSINESS at high {tick_to_price(high_tick):.2f}: "
                f"bid_vol={high_level.bid_vol} — price will return",
            ))

        # Non-zero ask at bar low = unfinished business downward
        if low_level.ask_vol > 0:
            signals.append(AuctionSignal(
                AuctionType.UNFINISHED_BUSINESS, -1,
                tick_to_price(low_tick), 0.6,
                f"UNFINISHED BUSINESS at low {tick_to_price(low_tick):.2f}: "
                f"ask_vol={low_level.ask_vol} — price will return",
            ))

        # --- 2. FINISHED AUCTION (AUCT-02) ---
        if high_level.bid_vol == 0 and high_level.ask_vol > 0:
            signals.append(AuctionSignal(
                AuctionType.FINISHED_AUCTION, -1,
                tick_to_price(high_tick), 0.7,
                f"FINISHED AUCTION at high {tick_to_price(high_tick):.2f}: "
                f"zero bid — buyers exhausted",
            ))

        if low_level.ask_vol == 0 and low_level.bid_vol > 0:
            signals.append(AuctionSignal(
                AuctionType.FINISHED_AUCTION, +1,
                tick_to_price(low_tick), 0.7,
                f"FINISHED AUCTION at low {tick_to_price(low_tick):.2f}: "
                f"zero ask — sellers exhausted",
            ))

        # --- 3. POOR HIGH/LOW (AUCT-03) ---
        avg_vol = bar.total_vol / len(bar.levels) if bar.levels else 1
        high_vol = high_level.ask_vol + high_level.bid_vol
        low_vol = low_level.ask_vol + low_level.bid_vol

        if high_vol < avg_vol * 0.3:
            signals.append(AuctionSignal(
                AuctionType.POOR_HIGH, -1,
                tick_to_price(high_tick), 0.5,
                f"POOR HIGH at {tick_to_price(high_tick):.2f}: "
                f"vol={high_vol} ({high_vol/avg_vol*100:.0f}% avg) — incomplete auction",
            ))

        if low_vol < avg_vol * 0.3:
            signals.append(AuctionSignal(
                AuctionType.POOR_LOW, +1,
                tick_to_price(low_tick), 0.5,
                f"POOR LOW at {tick_to_price(low_tick):.2f}: "
                f"vol={low_vol} ({low_vol/avg_vol*100:.0f}% avg) — incomplete auction",
            ))

        # --- 4. VOLUME VOID (AUCT-04) ---
        max_vol = max(lv.ask_vol + lv.bid_vol for lv in bar.levels.values())
        void_count = 0
        for tick in sorted_ticks:
            level = bar.levels[tick]
            vol = level.ask_vol + level.bid_vol
            if vol < max_vol * 0.05 and vol > 0:
                void_count += 1

        if void_count >= 3:
            direction = +1 if bar.close > bar.open else -1
            signals.append(AuctionSignal(
                AuctionType.VOLUME_VOID, direction,
                (bar.high + bar.low) / 2, min(void_count / 7.0, 1.0),
                f"VOLUME VOID: {void_count} thin levels — fast-move zone",
            ))

        # --- 5. MARKET SWEEP (AUCT-05) ---
        if bar.bar_range > 0 and len(sorted_ticks) >= 10:
            # Check for increasing volume as price moves through levels
            half = len(sorted_ticks) // 2
            if bar.close > bar.open:  # Up sweep
                first_half_vol = sum(
                    bar.levels[t].ask_vol + bar.levels[t].bid_vol
                    for t in sorted_ticks[:half]
                )
                second_half_vol = sum(
                    bar.levels[t].ask_vol + bar.levels[t].bid_vol
                    for t in sorted_ticks[half:]
                )
                if second_half_vol > first_half_vol * 1.5:
                    signals.append(AuctionSignal(
                        AuctionType.MARKET_SWEEP, +1,
                        bar.high, min(second_half_vol / first_half_vol / 3, 1.0),
                        f"MARKET SWEEP UP: upper half vol {second_half_vol/first_half_vol:.1f}x lower",
                    ))
            else:  # Down sweep
                first_half_vol = sum(
                    bar.levels[t].ask_vol + bar.levels[t].bid_vol
                    for t in sorted_ticks[half:]
                )
                second_half_vol = sum(
                    bar.levels[t].ask_vol + bar.levels[t].bid_vol
                    for t in sorted_ticks[:half]
                )
                if second_half_vol > first_half_vol * 1.5:
                    signals.append(AuctionSignal(
                        AuctionType.MARKET_SWEEP, -1,
                        bar.low, min(second_half_vol / first_half_vol / 3, 1.0),
                        f"MARKET SWEEP DOWN: lower half vol {second_half_vol/first_half_vol:.1f}x upper",
                    ))

        # --- Update E9 State Machine ---
        self._update_state(bar)

        return signals

    def _update_state(self, bar: FootprintBar) -> None:
        """Transition the auction state machine."""
        expanding_up = bar.high > self.prev_high
        expanding_down = bar.low < self.prev_low
        range_pct = bar.bar_range / ((self.prev_high - self.prev_low) or 1)

        if expanding_up and not expanding_down:
            self.state = AuctionState.EXPLORING_UP if range_pct < 2 else AuctionState.BREAKOUT
            self.balance_count = 0
        elif expanding_down and not expanding_up:
            self.state = AuctionState.EXPLORING_DOWN if range_pct < 2 else AuctionState.BREAKDOWN
            self.balance_count = 0
        elif not expanding_up and not expanding_down:
            self.balance_count += 1
            if self.balance_count >= 3:
                self.state = AuctionState.BALANCED
        # else: expanding both ways — keep current state

        self.prev_high = max(self.prev_high, bar.high)
        self.prev_low = min(self.prev_low, bar.low)
