"""Unified Level primitive for Phase 15 LevelBus.

A single ``Level`` dataclass represents all 17 ``LevelKind`` variants —
volume-profile origins (LVN/HVN/VPOC/VAH/VAL), narrative-zone origins
(ABSORB/EXHAUST/MOMENTUM/REJECTION/FLIPPED/CONFIRMED_ABSORB), and GEX-derived
point levels (CALL_WALL/PUT_WALL/GAMMA_FLIP/ZERO_GAMMA/HVL/LARGEST_GAMMA).

Design references:
  D-01: ``@dataclass(slots=True)`` ``Level`` with unified geometry
        (point levels set ``price_top == price_bot``; zones use full range),
        score (0–100), lifecycle state, sparse ``meta`` dict.
  D-02: ``LevelKind`` enum with exactly 17 members.
  D-03: ``LevelState`` FSM matches ``deep6.engines.volume_profile.ZoneState``
        member names verbatim — CREATED, DEFENDED, BROKEN, FLIPPED, INVALIDATED.
  D-04: ``origin_ts`` (Unix wall time) alongside ``origin_bar`` (index).
        Bar indices reset at session boundaries in backtest; ``origin_ts``
        survives reset for cross-session persistence + logging.
  D-05: ``meta`` is a sparse ``dict`` — no typed subclass. Known keys include
        ``vol_ratio``, ``wick_pct``, ``delta_ratio``, ``absorb_type``,
        ``gex_net``, ``confirmation_window_ends_bar``, ``confirmed``,
        ``confluence``, ``va_confirmed``, ``acceleration_candidate``.

C5 rationale (``uid: int``):
  ConfluenceRules (Plan 15-03) returns ``score_mutations: dict[int, float]``
  keyed by ``Level.uid`` rather than ``id(level)``. ``id()`` is not stable
  across copies / pickles / dataclasses.replace(), and Python can reuse
  memory addresses after GC. A per-instance ``uid: int = uuid4().int``
  gives downstream consumers a stable mutation key for as long as the same
  Level object is retained in LevelBus. Merging into an existing Level
  preserves the *existing* uid (see LevelBus.add_level); callers who want
  to track a Level across a ``dataclasses.replace()`` must explicitly copy
  the uid into the new instance.

``slots=True`` is compatible with ``default_factory`` on dataclass fields
(Python 3.10+).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto


class LevelKind(Enum):
    """17 level variants per D-02."""

    # Volume-profile origins
    LVN = auto()
    HVN = auto()
    VPOC = auto()
    VAH = auto()
    VAL = auto()
    # Narrative-zone origins
    ABSORB = auto()
    EXHAUST = auto()
    MOMENTUM = auto()
    REJECTION = auto()
    FLIPPED = auto()
    CONFIRMED_ABSORB = auto()
    # GEX-derived point levels
    CALL_WALL = auto()
    PUT_WALL = auto()
    GAMMA_FLIP = auto()
    ZERO_GAMMA = auto()  # naming alias for GAMMA_FLIP (D-29); distinct LevelKind so downstream rules can address it separately
    HVL = auto()
    LARGEST_GAMMA = auto()


class LevelState(Enum):
    """Lifecycle states.

    D-03 binds these names to ``deep6.engines.volume_profile.ZoneState``
    verbatim. Do not rename without also updating ZoneState.
    """

    CREATED = auto()
    DEFENDED = auto()
    BROKEN = auto()
    FLIPPED = auto()
    INVALIDATED = auto()


def _new_uid() -> int:
    """Per-instance stable integer id (uuid4).int).

    Extracted into a module-level function so tests can monkeypatch if
    needed; avoids lambda-in-default-factory repr noise in debugging.
    """
    return uuid.uuid4().int


@dataclass(slots=True)
class Level:
    """Unified level object — every producer writes this, every consumer reads it.

    Geometry:
      - Point levels (GEX walls, gamma flip, HVL, largest gamma) set
        ``price_top == price_bot``.
      - Zone levels set ``price_top > price_bot``. Minimum width is 1 tick;
        LevelFactory enforces this via ``tick_size``.

    Containment check is uniform:  ``price_bot <= p <= price_top``.

    Invariant (T-15-01-01, threat T-15-01-01):
      ``price_top >= price_bot``. ``__post_init__`` raises ``ValueError`` if
      violated. Tests enforce this.

    Identity:
      ``uid`` is a stable integer assigned once at construction. Use it as
      the mutation key for ConfluenceRules.score_mutations (C5). Do not use
      ``id(level)`` — that is address-based and not stable across copies.
    """

    price_top: float
    price_bot: float
    kind: LevelKind
    origin_ts: float
    origin_bar: int
    last_act_bar: int
    score: float
    touches: int
    direction: int  # +1 support, -1 resistance, 0 neutral (MOMENTUM / GEX lines)
    inverted: bool
    state: LevelState
    meta: dict = field(default_factory=dict)
    uid: int = field(default_factory=_new_uid)

    def __post_init__(self) -> None:
        if self.price_top < self.price_bot:
            raise ValueError(
                f"Level geometry invariant violated: price_top={self.price_top} "
                f"< price_bot={self.price_bot} (kind={self.kind.name})"
            )

    @property
    def confidence(self) -> float:
        """Derived: ``score / 100.0``.

        Cheap derived view rather than a stored field — avoids two sources of
        truth when ConfluenceRules mutates ``score``.
        """
        return self.score / 100.0

    def contains(self, price: float) -> bool:
        """``True`` if ``price`` falls within ``[price_bot, price_top]``."""
        return self.price_bot <= price <= self.price_top

    def midpoint(self) -> float:
        return (self.price_top + self.price_bot) / 2.0
