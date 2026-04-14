"""Tests for Level / LevelKind / LevelState (Plan 15-01, T-15-01-01).

Covers D-01..D-05 and the C5 uid-stability rationale.
"""
from __future__ import annotations

import dataclasses
import time

import pytest

from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.volume_profile import ZoneState


def _make_point(kind: LevelKind = LevelKind.CALL_WALL, price: float = 21000.0) -> Level:
    return Level(
        price_top=price,
        price_bot=price,
        kind=kind,
        origin_ts=time.time(),
        origin_bar=1,
        last_act_bar=1,
        score=50.0,
        touches=0,
        direction=0,
        inverted=False,
        state=LevelState.CREATED,
    )


def _make_zone(
    kind: LevelKind = LevelKind.LVN,
    top: float = 21010.0,
    bot: float = 21000.0,
) -> Level:
    return Level(
        price_top=top,
        price_bot=bot,
        kind=kind,
        origin_ts=time.time(),
        origin_bar=1,
        last_act_bar=1,
        score=50.0,
        touches=0,
        direction=+1,
        inverted=False,
        state=LevelState.CREATED,
    )


# ---------------------------------------------------------------------------
# D-01: slots + invariants
# ---------------------------------------------------------------------------

def test_level_slots_defined() -> None:
    """Level must use __slots__ (slots=True)."""
    assert hasattr(Level, "__slots__"), "Level must have __slots__ (slots=True)"
    # All documented fields + uid present
    slot_names = set(Level.__slots__)
    expected = {
        "price_top", "price_bot", "kind", "origin_ts", "origin_bar",
        "last_act_bar", "score", "touches", "direction", "inverted",
        "state", "meta", "uid",
    }
    assert expected.issubset(slot_names), f"missing slots: {expected - slot_names}"


def test_level_slots_reject_unknown_attribute() -> None:
    """Assigning an unknown attribute must raise AttributeError (slots enforcement)."""
    level = _make_point()
    with pytest.raises(AttributeError):
        level.not_a_field = 1  # type: ignore[attr-defined]


def test_level_geometry_invariant_rejects_inverted() -> None:
    """price_top < price_bot must raise ValueError (threat T-15-01-01)."""
    with pytest.raises(ValueError, match="invariant"):
        Level(
            price_top=100.0,
            price_bot=200.0,
            kind=LevelKind.LVN,
            origin_ts=0.0,
            origin_bar=0,
            last_act_bar=0,
            score=0.0,
            touches=0,
            direction=0,
            inverted=False,
            state=LevelState.CREATED,
        )


# ---------------------------------------------------------------------------
# D-01: point-level vs zone-level geometry
# ---------------------------------------------------------------------------

def test_point_level_geometry() -> None:
    """GEX kinds set price_top == price_bot; contains() works for single price."""
    level = _make_point(LevelKind.CALL_WALL, 21000.0)
    assert level.price_top == level.price_bot == 21000.0
    assert level.contains(21000.0)
    assert not level.contains(21000.25)
    assert not level.contains(20999.75)


def test_zone_level_geometry() -> None:
    """Zone kinds have price_top > price_bot; contains() is inclusive on both ends."""
    level = _make_zone(LevelKind.ABSORB, top=21010.0, bot=21000.0)
    assert level.price_top > level.price_bot
    assert level.contains(21000.0)
    assert level.contains(21010.0)
    assert level.contains(21005.0)
    assert not level.contains(21010.25)
    assert not level.contains(20999.75)


# ---------------------------------------------------------------------------
# D-02: LevelKind count
# ---------------------------------------------------------------------------

def test_level_kind_count() -> None:
    """LevelKind must have exactly 17 members per D-02."""
    expected_names = {
        "LVN", "HVN", "VPOC", "VAH", "VAL",
        "ABSORB", "EXHAUST", "MOMENTUM", "REJECTION",
        "FLIPPED", "CONFIRMED_ABSORB",
        "CALL_WALL", "PUT_WALL", "GAMMA_FLIP", "ZERO_GAMMA", "HVL", "LARGEST_GAMMA",
    }
    actual = {m.name for m in LevelKind}
    assert len(LevelKind) == 17, f"Expected 17 LevelKinds, got {len(LevelKind)}: {actual}"
    assert actual == expected_names


# ---------------------------------------------------------------------------
# D-03: LevelState matches ZoneState verbatim
# ---------------------------------------------------------------------------

def test_level_state_matches_zone_state() -> None:
    """Every ZoneState member name must exist as a LevelState member (D-03)."""
    zone_names = {m.name for m in ZoneState}
    level_state_names = {m.name for m in LevelState}
    assert zone_names == level_state_names, (
        f"LevelState must match ZoneState verbatim. "
        f"zone_only={zone_names - level_state_names} "
        f"level_only={level_state_names - zone_names}"
    )


# ---------------------------------------------------------------------------
# D-04: origin_ts + origin_bar both preserved
# ---------------------------------------------------------------------------

def test_origin_ts_and_origin_bar_both_set() -> None:
    """Both origin_ts (wall time) and origin_bar (index) must persist."""
    t = 1_700_000_000.5
    b = 42
    level = Level(
        price_top=21000.0, price_bot=21000.0, kind=LevelKind.GAMMA_FLIP,
        origin_ts=t, origin_bar=b, last_act_bar=b,
        score=0.0, touches=0, direction=0, inverted=False,
        state=LevelState.CREATED,
    )
    assert level.origin_ts == t
    assert level.origin_bar == b


# ---------------------------------------------------------------------------
# D-05: meta sparse dict
# ---------------------------------------------------------------------------

def test_meta_defaults_to_empty_dict_and_accepts_arbitrary_keys() -> None:
    level = _make_point()
    assert level.meta == {}
    level.meta["vol_ratio"] = 2.3
    level.meta["custom_key"] = "anything"
    assert level.meta["vol_ratio"] == 2.3
    assert level.meta["custom_key"] == "anything"


def test_meta_default_factory_independent_instances() -> None:
    """default_factory=dict must not share state across instances (common bug)."""
    a = _make_point()
    b = _make_point()
    a.meta["x"] = 1
    assert "x" not in b.meta


# ---------------------------------------------------------------------------
# confidence derived view
# ---------------------------------------------------------------------------

def test_confidence_is_derived_from_score() -> None:
    level = _make_zone()
    level.score = 75.0
    assert level.confidence == 0.75
    level.score = 0.0
    assert level.confidence == 0.0
    level.score = 100.0
    assert level.confidence == 1.0


# ---------------------------------------------------------------------------
# C5: uid stability / uniqueness
# ---------------------------------------------------------------------------

def test_level_uid_unique_across_instances() -> None:
    """100 Level instances must produce 100 distinct uids."""
    levels = [_make_zone() for _ in range(100)]
    uids = {lv.uid for lv in levels}
    assert len(uids) == 100, f"uid collisions: {100 - len(uids)}"


def test_dataclass_replace_preserves_uid_by_default() -> None:
    """``dataclasses.replace`` copies existing field values — including ``uid``.

    This is the stdlib behavior: ``default_factory`` is only invoked when a
    field has no value. Since the source Level already has a ``uid``,
    replace() reuses it. This is SAFER for downstream mutation keying
    (ConfluenceRules.score_mutations, C5) — callers don't accidentally
    orphan their mutation keys after a minor field update.

    To force a fresh uid on replace(), pass ``uid=_new_uid()`` explicitly
    or construct a new Level().
    """
    from deep6.engines.level import _new_uid

    lv = _make_zone()
    original_uid = lv.uid
    copy = dataclasses.replace(lv, score=99.0)
    assert copy.uid == original_uid, "replace() preserves uid — stable mutation keys"
    assert copy.score == 99.0

    # Explicit fresh uid path:
    forked = dataclasses.replace(lv, uid=_new_uid())
    assert forked.uid != original_uid
