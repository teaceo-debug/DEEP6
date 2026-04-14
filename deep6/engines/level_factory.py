"""Stateless factory for converting producer artifacts into ``Level`` instances.

Every producer (VolumeProfile, narrative engine, absorption/exhaustion, GEX
engine) feeds into the LevelBus through this single conversion layer.
No state, no side effects — all functions are pure.

Design references (see `.planning/phases/15-levelbus-.../15-CONTEXT.md`):
  D-07: ABSORB zone geometry = full wick (bar.high..body_top for UW;
        body_bot..bar.low for LW). Minimum width = 1 tick.
  D-12: Factory module with functions from_volume_zone / from_narrative /
        from_absorption / from_exhaustion / from_momentum / from_rejection /
        from_gex. All stateless, callable from any engine.
  D-28/D-29: from_gex emits up to 6 point-Levels, including
        LARGEST_GAMMA and ZERO_GAMMA (ZERO_GAMMA is kind-distinct from
        GAMMA_FLIP even though they share the same price — downstream rules
        can address them separately).
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Iterable

from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType

if TYPE_CHECKING:
    from deep6.engines.absorption import AbsorptionSignal
    from deep6.engines.exhaustion import ExhaustionSignal
    from deep6.engines.gex import GexLevels
    from deep6.engines.narrative import NarrativeResult
    from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_zone_state(state: ZoneState) -> LevelState:
    """Map ZoneState → LevelState by name (D-03 guarantees 1:1)."""
    return LevelState[state.name]


def _enforce_min_width(top: float, bot: float, tick_size: float) -> tuple[float, float]:
    """Ensure zone width ≥ 1 tick (D-07). Degenerate bars widen around midpoint."""
    if top - bot >= tick_size:
        return top, bot
    mid = (top + bot) / 2.0
    half = tick_size / 2.0
    return mid + half, mid - half


def _body(bar: "FootprintBar") -> tuple[float, float]:
    """Return (body_top, body_bot) for a footprint bar."""
    return max(bar.open, bar.close), min(bar.open, bar.close)


# ---------------------------------------------------------------------------
# VolumeZone → Level (D-12)
# ---------------------------------------------------------------------------

def from_volume_zone(zone: VolumeZone, *, origin_ts: float | None = None) -> Level:
    """Convert VolumeZone (LVN/HVN) → Level preserving all score/touches/state."""
    kind = LevelKind.LVN if zone.zone_type == ZoneType.LVN else LevelKind.HVN
    meta: dict = {"vol_ratio": zone.volume_ratio} if zone.volume_ratio else {}
    return Level(
        price_top=zone.top_price,
        price_bot=zone.bot_price,
        kind=kind,
        origin_ts=origin_ts if origin_ts is not None else time.time(),
        origin_bar=zone.origin_bar,
        last_act_bar=zone.last_touch_bar,
        score=zone.score,
        touches=zone.touches,
        direction=zone.direction,
        inverted=zone.inverted,
        state=_map_zone_state(zone.state),
        meta=meta,
    )


# ---------------------------------------------------------------------------
# NarrativeResult → List[Level] (D-06, D-12)
# ---------------------------------------------------------------------------

def from_narrative(
    result: "NarrativeResult",
    *,
    strength_threshold: float = 0.4,
    bar_index: int,
    tick_size: float,
    bar: "FootprintBar | None" = None,
) -> list[Level]:
    """Convert a NarrativeResult into zero-or-more Levels.

    Single-source-of-truth signature consumed by Plan 15-02.

    Args:
        result: NarrativeResult from classify_bar()
        strength_threshold: minimum signal strength for persistence (D-06 default 0.4)
        bar_index: current bar index — written to origin_bar + last_act_bar
        tick_size: instrument tick size for minimum-width enforcement
        bar: the FootprintBar the signals came from. Optional: if omitted,
             zones are built using the signal's ``price`` field as a
             single-tick point-band. Providing ``bar`` enables proper wick
             geometry (D-07) and should be done by callers that have it.

    Emission policy:
        - Absorption signals → ABSORB Levels (wick geometry via ``from_absorption``
          when ``bar`` provided, else 1-tick band around signal.price).
        - Exhaustion signals → EXHAUST Levels (same policy).
        - MOMENTUM narrative → one MOMENTUM Level (body geometry); requires ``bar``.
        - REJECTION narrative → one REJECTION Level (body geometry); requires ``bar``.
    """
    from deep6.engines.narrative import NarrativeType

    levels: list[Level] = []

    # Absorption
    for sig in result.absorption:
        if sig.strength < strength_threshold:
            continue
        if bar is not None:
            levels.append(from_absorption(sig, bar, bar_index=bar_index, tick_size=tick_size))
        else:
            levels.append(_point_zone(
                kind=LevelKind.ABSORB,
                price=sig.price,
                direction=sig.direction,
                strength=sig.strength,
                bar_index=bar_index,
                tick_size=tick_size,
                meta={"wick": sig.wick, "wick_pct": sig.wick_pct, "delta_ratio": sig.delta_ratio, "absorb_type": sig.bar_type.name},
            ))

    # Exhaustion
    for sig in result.exhaustion:
        if sig.strength < strength_threshold:
            continue
        if bar is not None:
            levels.append(from_exhaustion(sig, bar, bar_index=bar_index, tick_size=tick_size))
        else:
            levels.append(_point_zone(
                kind=LevelKind.EXHAUST,
                price=sig.price,
                direction=sig.direction,
                strength=sig.strength,
                bar_index=bar_index,
                tick_size=tick_size,
                meta={},
            ))

    # MOMENTUM / REJECTION come from the bar_type classification, not a discrete
    # signal object. Emit them only when we have a bar to derive geometry from
    # and the strength threshold is met.
    if bar is not None and result.strength >= strength_threshold:
        if result.bar_type == NarrativeType.MOMENTUM:
            levels.append(from_momentum(result, bar, bar_index=bar_index, tick_size=tick_size))
        elif result.bar_type == NarrativeType.REJECTION:
            levels.append(from_rejection(result, bar, bar_index=bar_index, tick_size=tick_size))

    return levels


def _point_zone(
    *,
    kind: LevelKind,
    price: float,
    direction: int,
    strength: float,
    bar_index: int,
    tick_size: float,
    meta: dict,
) -> Level:
    """Build a 1-tick-wide zone around ``price`` for callers without a bar."""
    top, bot = _enforce_min_width(price, price, tick_size)
    return Level(
        price_top=top,
        price_bot=bot,
        kind=kind,
        origin_ts=time.time(),
        origin_bar=bar_index,
        last_act_bar=bar_index,
        score=min(max(strength, 0.0), 1.0) * 100.0,
        touches=0,
        direction=direction,
        inverted=False,
        state=LevelState.CREATED,
        meta=dict(meta),
    )


# ---------------------------------------------------------------------------
# AbsorptionSignal → Level (D-07, D-12)
# ---------------------------------------------------------------------------

def from_absorption(
    signal: "AbsorptionSignal",
    bar: "FootprintBar",
    *,
    bar_index: int,
    tick_size: float,
) -> Level:
    """Build an ABSORB Level with full-wick geometry (D-07).

    UW absorption (``signal.wick == "upper"``): ``top = bar.high, bot = body_top``.
    LW absorption (``signal.wick == "lower"``): ``top = body_bot, bot = bar.low``.
    Minimum width = 1 tick.
    """
    body_top, body_bot = _body(bar)
    if signal.wick == "upper":
        top, bot = bar.high, body_top
    else:
        top, bot = body_bot, bar.low
    top, bot = _enforce_min_width(top, bot, tick_size)

    return Level(
        price_top=top,
        price_bot=bot,
        kind=LevelKind.ABSORB,
        origin_ts=time.time(),
        origin_bar=bar_index,
        last_act_bar=bar_index,
        score=min(max(signal.strength, 0.0), 1.0) * 100.0,
        touches=0,
        direction=signal.direction,
        inverted=False,
        state=LevelState.CREATED,
        meta={
            "wick": signal.wick,
            "wick_pct": signal.wick_pct,
            "delta_ratio": signal.delta_ratio,
            "absorb_type": signal.bar_type.name,
        },
    )


# ---------------------------------------------------------------------------
# ExhaustionSignal → Level (D-07 wick geometry)
# ---------------------------------------------------------------------------

def from_exhaustion(
    signal: "ExhaustionSignal",
    bar: "FootprintBar",
    *,
    bar_index: int,
    tick_size: float,
) -> Level:
    """Build an EXHAUST Level. Same wick-based geometry as absorption."""
    body_top, body_bot = _body(bar)
    wick = getattr(signal, "wick", None)
    if wick == "upper":
        top, bot = bar.high, body_top
    elif wick == "lower":
        top, bot = body_bot, bar.low
    else:
        # If exhaustion signal lacks a wick hint, use the bar's wick on the
        # direction-facing side. direction=-1 (bearish) → upper wick; +1 → lower.
        if signal.direction < 0:
            top, bot = bar.high, body_top
        else:
            top, bot = body_bot, bar.low
    top, bot = _enforce_min_width(top, bot, tick_size)

    return Level(
        price_top=top,
        price_bot=bot,
        kind=LevelKind.EXHAUST,
        origin_ts=time.time(),
        origin_bar=bar_index,
        last_act_bar=bar_index,
        score=min(max(signal.strength, 0.0), 1.0) * 100.0,
        touches=0,
        direction=signal.direction,
        inverted=False,
        state=LevelState.CREATED,
        meta={"wick": wick} if wick else {},
    )


# ---------------------------------------------------------------------------
# MOMENTUM / REJECTION — body geometry
# ---------------------------------------------------------------------------

def _from_body(
    result: "NarrativeResult",
    bar: "FootprintBar",
    kind: LevelKind,
    *,
    bar_index: int,
    tick_size: float,
) -> Level:
    body_top, body_bot = _body(bar)
    top, bot = _enforce_min_width(body_top, body_bot, tick_size)
    return Level(
        price_top=top,
        price_bot=bot,
        kind=kind,
        origin_ts=time.time(),
        origin_bar=bar_index,
        last_act_bar=bar_index,
        score=min(max(result.strength, 0.0), 1.0) * 100.0,
        touches=0,
        direction=result.direction,
        inverted=False,
        state=LevelState.CREATED,
        meta={"narrative_label": result.label},
    )


def from_momentum(
    result: "NarrativeResult",
    bar: "FootprintBar",
    *,
    bar_index: int,
    tick_size: float,
) -> Level:
    """MOMENTUM zone = candle body."""
    return _from_body(result, bar, LevelKind.MOMENTUM, bar_index=bar_index, tick_size=tick_size)


def from_rejection(
    result: "NarrativeResult",
    bar: "FootprintBar",
    *,
    bar_index: int,
    tick_size: float,
) -> Level:
    """REJECTION zone = candle body."""
    return _from_body(result, bar, LevelKind.REJECTION, bar_index=bar_index, tick_size=tick_size)


# ---------------------------------------------------------------------------
# GexLevels → List[Level] (D-28 / D-29)
# ---------------------------------------------------------------------------

_GEX_FIELD_TO_KIND: tuple[tuple[str, LevelKind], ...] = (
    ("call_wall", LevelKind.CALL_WALL),
    ("put_wall", LevelKind.PUT_WALL),
    ("gamma_flip", LevelKind.GAMMA_FLIP),
    ("hvl", LevelKind.HVL),
    ("largest_gamma_strike", LevelKind.LARGEST_GAMMA),
    # zero_gamma is a @property aliasing gamma_flip (D-29); still emit as
    # distinct LevelKind so downstream rules can address it separately.
    ("zero_gamma", LevelKind.ZERO_GAMMA),
)


def from_gex(levels: "GexLevels", *, origin_ts: float | None = None) -> list[Level]:
    """Emit up to 6 point-Levels from a GexLevels snapshot.

    A field contributes a Level only when its price > 0. ``zero_gamma`` is
    read via attribute access (property) so absent attributes raise cleanly
    during tests rather than silently producing nonsense.
    """
    ts = origin_ts if origin_ts is not None else getattr(levels, "timestamp", None) or time.time()
    out: list[Level] = []
    for field_name, kind in _GEX_FIELD_TO_KIND:
        price = getattr(levels, field_name, 0.0) or 0.0
        if price <= 0:
            continue
        out.append(Level(
            price_top=price,
            price_bot=price,
            kind=kind,
            origin_ts=ts,
            origin_bar=0,
            last_act_bar=0,
            score=0.0,  # GEX lines carry proximity-weighted score; initial 0 → LevelBus scorer handles
            touches=0,
            direction=0,
            inverted=False,
            state=LevelState.CREATED,
            meta={"gex_source": field_name},
        ))
    return out


__all__ = [
    "from_volume_zone",
    "from_narrative",
    "from_absorption",
    "from_exhaustion",
    "from_momentum",
    "from_rejection",
    "from_gex",
]
