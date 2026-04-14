"""Synthetic day-type session fixtures for Phase 15-05 integration tests.

Phase 15-05 T-15-05-01 — D-36 fallback path.

Produces 5 deterministic day-type sessions (Normal, Trend, Double
Distribution, Neutral, Non-Trend) each ≈390 FootprintBars (one RTH
session at 1-minute bar cadence). Each yields tuples of
``(bar, narrative_result, gex_signal)`` — narrative_result and
gex_signal are shaped to exercise the Phase-15 confluence pipeline.

Determinism: ``numpy.random.default_rng(seed)`` seeded from the
day-type string hash (stable across Python invocations via
``hashlib.md5``). Same seed → byte-identical bar sequences.

Day-type signatures (per auction_theory.md §Day-type classification):
  * Normal:           auction inside initial balance, closes near POC
  * Trend:            one-directional auction, extends IB early, closes at extreme
  * Double Distribution: two distinct value areas with migration
  * Neutral:          range extends both sides of IB, closes near open
  * Non-Trend:        sub-1.5×IB range, no extension

Narrative seeding (per day-type profile):
  * Trend day: MOMENTUM at bar 30, absorption at bar 100
  * Double distribution: rejection at bar 120, acceptance at bar 240
  * Neutral: rejection + absorption at both extremes
  * Normal / Non-Trend: sparse narrative hits
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterator, Sequence

import numpy as np

from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.exhaustion import ExhaustionSignal, ExhaustionType
from deep6.engines.gex import GexLevels, GexRegime, GexSignal
from deep6.engines.narrative import (
    AbsorptionConfirmation,
    NarrativeResult,
    NarrativeType,
)
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick


RTH_BAR_COUNT = 390  # one session at 1m cadence
DEFAULT_TICK_SIZE = 0.25
NQ_BASE_PRICE = 18500.0


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def _seed_from_day_type(day_type: str) -> int:
    """Stable integer seed derived from day-type string.

    Uses md5 so the seed is reproducible across Python sessions (Python's
    built-in hash() randomises between interpreter runs).
    """
    return int(hashlib.md5(day_type.encode()).hexdigest()[:8], 16)


def _make_rng(day_type: str) -> np.random.Generator:
    return np.random.default_rng(_seed_from_day_type(day_type))


# ---------------------------------------------------------------------------
# Bar construction helpers
# ---------------------------------------------------------------------------


def _build_bar(
    *, timestamp: float, open_p: float, high: float, low: float, close: float,
    total_vol: int, bar_delta: int, tick_size: float = DEFAULT_TICK_SIZE,
) -> FootprintBar:
    """Assemble a finalized FootprintBar with minimal footprint-level data.

    For integration tests we don't need every tick — just the
    bar-close fields (open/high/low/close/total_vol/bar_delta/poc_price).
    One synthetic footprint-level is placed at close price to keep
    ``levels`` non-empty.
    """
    bar = FootprintBar(
        timestamp=timestamp,
        open=open_p,
        high=high,
        low=low,
        close=close,
        total_vol=total_vol,
        bar_delta=bar_delta,
        cvd=0,
        poc_price=close,
        bar_range=max(high - low, tick_size),
    )
    # Single footprint level at close price with ~balanced aggression
    tick = price_to_tick(close)
    ask = max(1, int(total_vol // 2) + (bar_delta // 2 if bar_delta > 0 else 0))
    bid = max(1, total_vol - ask)
    bar.levels[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
    return bar


def _quiet_narrative(bar: FootprintBar) -> NarrativeResult:
    return NarrativeResult(
        bar_type=NarrativeType.QUIET,
        direction=0,
        label="",
        strength=0.0,
        price=bar.close,
        absorption=[],
        exhaustion=[],
        imbalances=[],
        all_signals_count=0,
    )


def _absorption_narrative(
    bar: FootprintBar, *, direction: int, strength: float = 0.65,
    bar_index: int = 0,
) -> NarrativeResult:
    sig = AbsorptionSignal(
        bar_type=AbsorptionType.CLASSIC,
        direction=direction,
        price=bar.close,
        wick="lower" if direction > 0 else "upper",
        strength=strength,
        wick_pct=0.6,
        delta_ratio=0.35,
        detail=f"synthetic absorption dir={direction}",
    )
    return NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=direction,
        label=f"ABSORB_{'UP' if direction>0 else 'DN'}",
        strength=strength,
        price=bar.close,
        absorption=[sig],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
    )


def _exhaustion_narrative(
    bar: FootprintBar, *, direction: int, strength: float = 0.55,
) -> NarrativeResult:
    sig = ExhaustionSignal(
        bar_type=ExhaustionType.EXHAUSTION_PRINT,
        direction=direction,
        price=bar.close,
        strength=strength,
        detail="synthetic exhaustion",
    )
    return NarrativeResult(
        bar_type=NarrativeType.EXHAUSTION,
        direction=direction,
        label=f"EXHAUST_{'UP' if direction>0 else 'DN'}",
        strength=strength,
        price=bar.close,
        absorption=[],
        exhaustion=[sig],
        imbalances=[],
        all_signals_count=1,
    )


def _momentum_narrative(bar: FootprintBar, *, direction: int) -> NarrativeResult:
    return NarrativeResult(
        bar_type=NarrativeType.MOMENTUM,
        direction=direction,
        label="MOMENTUM",
        strength=0.55,
        price=bar.close,
        absorption=[],
        exhaustion=[],
        imbalances=[],
        all_signals_count=0,
    )


def _rejection_narrative(bar: FootprintBar, *, direction: int) -> NarrativeResult:
    return NarrativeResult(
        bar_type=NarrativeType.REJECTION,
        direction=direction,
        label="REJECTION",
        strength=0.45,
        price=bar.close,
        absorption=[],
        exhaustion=[],
        imbalances=[],
        all_signals_count=0,
    )


# ---------------------------------------------------------------------------
# GEX signal helper
# ---------------------------------------------------------------------------


def _build_gex_signal(
    *, spot: float, regime: GexRegime = GexRegime.NEUTRAL,
    call_wall_offset: float = 25.0, put_wall_offset: float = -25.0,
    gamma_flip_offset: float = -5.0,
) -> GexSignal:
    call_wall = spot + call_wall_offset
    put_wall = spot + put_wall_offset
    gamma_flip = spot + gamma_flip_offset
    direction = +1 if regime == GexRegime.POSITIVE_DAMPENING else (
        -1 if regime == GexRegime.NEGATIVE_AMPLIFYING else 0
    )
    return GexSignal(
        regime=regime,
        direction=direction,
        call_wall=call_wall,
        put_wall=put_wall,
        gamma_flip=gamma_flip,
        near_call_wall=False,
        near_put_wall=False,
        strength=0.5,
        detail=f"synthetic {regime.name}",
    )


# ---------------------------------------------------------------------------
# Day-type session builders
# ---------------------------------------------------------------------------


SessionTuple = tuple[FootprintBar, NarrativeResult, GexSignal]


def build_normal_day(
    bar_count: int = RTH_BAR_COUNT,
    base_price: float = NQ_BASE_PRICE,
) -> list[SessionTuple]:
    """Normal day: auction inside initial balance, closes near POC.

    IB (first 60 bars) sets the range; remainder oscillates inside.
    """
    rng = _make_rng("normal")
    bars: list[SessionTuple] = []
    ib_range = 20.0
    ib_high = base_price + ib_range / 2
    ib_low = base_price - ib_range / 2
    price = base_price
    base_ts = 1_700_000_000.0
    for i in range(bar_count):
        if i < 60:
            # IB: drift randomly within a growing band around base_price
            price += rng.normal(0.0, 1.5)
            price = float(np.clip(price, ib_low, ib_high))
        else:
            # post-IB: mean-revert toward POC ≈ base_price
            pull = (base_price - price) * 0.05
            price += pull + rng.normal(0.0, 1.0)
            price = float(np.clip(price, ib_low - 1.0, ib_high + 1.0))
        high = price + abs(rng.normal(0, 0.75))
        low = price - abs(rng.normal(0, 0.75))
        open_p = price - rng.normal(0, 0.5)
        close = price
        vol = int(rng.integers(500, 1500))
        delta = int(rng.integers(-150, 150))
        bar = _build_bar(
            timestamp=base_ts + i * 60.0,
            open_p=round(open_p, 2), high=round(high, 2),
            low=round(low, 2), close=round(close, 2),
            total_vol=vol, bar_delta=delta,
        )
        narr = _quiet_narrative(bar)
        # Occasional light absorption near IB extremes
        if i in (20, 45) and 0 < bar.bar_range > 0:
            narr = _absorption_narrative(bar, direction=+1, strength=0.5, bar_index=i)
        gex = _build_gex_signal(spot=bar.close)
        bars.append((bar, narr, gex))
    return bars


def build_trend_day(
    bar_count: int = RTH_BAR_COUNT,
    base_price: float = NQ_BASE_PRICE,
) -> list[SessionTuple]:
    """Trend day: one-directional auction, extends IB early, closes at extreme.

    Seeds MOMENTUM narrative at bar 30, absorption at bar 100.
    """
    rng = _make_rng("trend")
    bars: list[SessionTuple] = []
    price = base_price
    base_ts = 1_700_000_000.0
    trend_per_bar = 0.25  # +60 points over 240 bars
    for i in range(bar_count):
        price += trend_per_bar + rng.normal(0.0, 1.0)
        high = price + abs(rng.normal(0, 0.75))
        low = price - abs(rng.normal(0, 0.5))
        open_p = price - trend_per_bar * 0.5
        close = price
        vol = int(rng.integers(800, 2500))
        # Positive delta skew for bull trend
        delta = int(rng.integers(-50, 400))
        bar = _build_bar(
            timestamp=base_ts + i * 60.0,
            open_p=round(open_p, 2), high=round(high, 2),
            low=round(low, 2), close=round(close, 2),
            total_vol=vol, bar_delta=delta,
        )
        narr = _quiet_narrative(bar)
        if i == 30:
            narr = _momentum_narrative(bar, direction=+1)
        elif i == 100:
            narr = _absorption_narrative(bar, direction=+1, strength=0.75, bar_index=i)
        gex = _build_gex_signal(
            spot=bar.close,
            regime=(
                GexRegime.NEGATIVE_AMPLIFYING
                if bar.close > base_price + 20.0
                else GexRegime.NEUTRAL
            ),
        )
        bars.append((bar, narr, gex))
    return bars


def build_double_distribution_day(
    bar_count: int = RTH_BAR_COUNT,
    base_price: float = NQ_BASE_PRICE,
) -> list[SessionTuple]:
    """Double Distribution: two distinct value areas with migration at mid-session.

    Seeds rejection at bar 120 (leaving distribution 1), acceptance at
    bar 240 (into distribution 2).
    """
    rng = _make_rng("double_distribution")
    bars: list[SessionTuple] = []
    base_ts = 1_700_000_000.0
    dist1_center = base_price - 15.0
    dist2_center = base_price + 15.0
    price = dist1_center
    for i in range(bar_count):
        if i < 180:
            target = dist1_center
        elif i < 200:
            # Migration bars — walk quickly
            target = dist1_center + (dist2_center - dist1_center) * ((i - 180) / 20)
        else:
            target = dist2_center
        price += (target - price) * 0.20 + rng.normal(0.0, 1.0)
        high = price + abs(rng.normal(0, 0.75))
        low = price - abs(rng.normal(0, 0.75))
        open_p = price - rng.normal(0, 0.5)
        close = price
        vol = int(rng.integers(600, 1800))
        delta = int(rng.integers(-200, 250))
        bar = _build_bar(
            timestamp=base_ts + i * 60.0,
            open_p=round(open_p, 2), high=round(high, 2),
            low=round(low, 2), close=round(close, 2),
            total_vol=vol, bar_delta=delta,
        )
        narr = _quiet_narrative(bar)
        if i == 120:
            narr = _rejection_narrative(bar, direction=+1)
        elif i == 240:
            narr = _absorption_narrative(bar, direction=+1, strength=0.6, bar_index=i)
        gex = _build_gex_signal(spot=bar.close)
        bars.append((bar, narr, gex))
    return bars


def build_neutral_day(
    bar_count: int = RTH_BAR_COUNT,
    base_price: float = NQ_BASE_PRICE,
) -> list[SessionTuple]:
    """Neutral: range extends both sides of IB, closes near open.

    Seeds rejection + absorption at both extremes (bars 80, 200, 300).
    """
    rng = _make_rng("neutral")
    bars: list[SessionTuple] = []
    base_ts = 1_700_000_000.0
    ib_high = base_price + 15.0
    ib_low = base_price - 15.0
    price = base_price
    for i in range(bar_count):
        # Alternating excursion: go high, come back, go low, come back, close near base
        if i < 80:
            target = base_price
        elif i < 160:
            target = ib_high + 3.0
        elif i < 240:
            target = base_price
        elif i < 320:
            target = ib_low - 3.0
        else:
            target = base_price
        price += (target - price) * 0.12 + rng.normal(0.0, 1.2)
        high = price + abs(rng.normal(0, 0.9))
        low = price - abs(rng.normal(0, 0.9))
        open_p = price - rng.normal(0, 0.6)
        close = price
        vol = int(rng.integers(700, 2000))
        delta = int(rng.integers(-250, 250))
        bar = _build_bar(
            timestamp=base_ts + i * 60.0,
            open_p=round(open_p, 2), high=round(high, 2),
            low=round(low, 2), close=round(close, 2),
            total_vol=vol, bar_delta=delta,
        )
        narr = _quiet_narrative(bar)
        if i == 160:
            narr = _exhaustion_narrative(bar, direction=-1, strength=0.65)
        elif i == 200:
            narr = _absorption_narrative(bar, direction=-1, strength=0.65, bar_index=i)
        elif i == 320:
            narr = _absorption_narrative(bar, direction=+1, strength=0.65, bar_index=i)
        gex = _build_gex_signal(spot=bar.close)
        bars.append((bar, narr, gex))
    return bars


def build_non_trend_day(
    bar_count: int = RTH_BAR_COUNT,
    base_price: float = NQ_BASE_PRICE,
) -> list[SessionTuple]:
    """Non-Trend: sub-1.5×IB range, no extension. Lowest-activity day type."""
    rng = _make_rng("non_trend")
    bars: list[SessionTuple] = []
    base_ts = 1_700_000_000.0
    # Very tight range ±5 points
    for i in range(bar_count):
        price = base_price + rng.normal(0.0, 2.0)
        high = price + abs(rng.normal(0, 0.4))
        low = price - abs(rng.normal(0, 0.4))
        open_p = price - rng.normal(0, 0.3)
        close = price
        vol = int(rng.integers(200, 700))
        delta = int(rng.integers(-80, 80))
        bar = _build_bar(
            timestamp=base_ts + i * 60.0,
            open_p=round(open_p, 2), high=round(high, 2),
            low=round(low, 2), close=round(close, 2),
            total_vol=vol, bar_delta=delta,
        )
        narr = _quiet_narrative(bar)
        gex = _build_gex_signal(spot=bar.close)
        bars.append((bar, narr, gex))
    return bars


DAY_TYPE_BUILDERS: dict[str, callable] = {
    "normal": build_normal_day,
    "trend": build_trend_day,
    "double_distribution": build_double_distribution_day,
    "neutral": build_neutral_day,
    "non_trend": build_non_trend_day,
}


def build_session(day_type: str, **kwargs) -> list[SessionTuple]:
    """Dispatch to the appropriate day-type builder.

    Raises KeyError on unknown day_type.
    """
    return DAY_TYPE_BUILDERS[day_type](**kwargs)


__all__ = [
    "RTH_BAR_COUNT",
    "DEFAULT_TICK_SIZE",
    "SessionTuple",
    "build_normal_day",
    "build_trend_day",
    "build_double_distribution_day",
    "build_neutral_day",
    "build_non_trend_day",
    "build_session",
    "DAY_TYPE_BUILDERS",
]
