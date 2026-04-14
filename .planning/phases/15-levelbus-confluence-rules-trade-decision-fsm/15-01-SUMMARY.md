---
phase: 15-levelbus-confluence-rules-trade-decision-fsm
plan: 01
subsystem: engines
tags: [levelbus, level-factory, gex, confluence-rules, phase-15]
requirements: [ZONE-01, ZONE-02, ZONE-03, ZONE-04, ZONE-05, GEX-02]
dependency_graph:
  requires:
    - "deep6/engines/volume_profile.py ZoneState + VolumeZone (D-03 matching contract)"
    - "deep6/engines/gex.py GexLevels + _compute_gex max_call_strike tracking"
    - "deep6/engines/zone_registry.py original ZoneRegistry semantics (ZONE-01..05)"
  provides:
    - "deep6/engines/level.py Level dataclass (slots=True) + LevelKind (17) + LevelState (5)"
    - "deep6/engines/level_factory.py stateless conversion layer for all 5 input types"
    - "deep6/engines/zone_registry.py LevelBus class with add_level / query_near / query_by_kind / get_top_n + D-11 eviction"
    - "deep6/engines/gex.py GexLevels.largest_gamma_strike (D-28) + zero_gamma alias (D-29)"
    - ".planning/phases/15-.../RULES.md 38 canonical CR-XX rules deduped from 47 sources"
  affects:
    - "deep6/engines/zone_registry.py get_all_active() now returns list[Level] (C3)"
    - "tests/test_zone_registry.py ZONE-05 assertions updated to read Level.price_top/price_bot"
tech_stack:
  added: []
  patterns:
    - "slots=True dataclass + default_factory (Python 3.10+ compatible)"
    - "uuid4.int as stable mutation key across copies (C5 identity invariant)"
    - "LevelKind-dispatched merge vs dedupe in LevelBus.add_level"
    - "Canonical-rule dedup with lineage audit trail (threat T-15-01-03)"
key_files:
  created:
    - "deep6/engines/level.py"
    - "deep6/engines/level_factory.py"
    - ".planning/phases/15-levelbus-confluence-rules-trade-decision-fsm/RULES.md"
    - "tests/engines/__init__.py"
    - "tests/engines/test_level.py"
    - "tests/engines/test_level_bus.py"
    - "tests/engines/test_level_factory.py"
    - "tests/engines/test_gex_largest_gamma.py"
  modified:
    - "deep6/engines/zone_registry.py"
    - "deep6/engines/gex.py"
    - "tests/test_zone_registry.py"
decisions:
  - "In-place rename ZoneRegistry -> LevelBus (D-09); alias preserved for one release"
  - "uid: int = uuid4().int — stable mutation key for ConfluenceRules.score_mutations (C5)"
  - "LevelState member names match ZoneState verbatim (CREATED/DEFENDED/BROKEN/FLIPPED/INVALIDATED per D-03); plan text referencing ACTIVE was superseded"
  - "ZERO_GAMMA emitted as distinct LevelKind even though value aliases GAMMA_FLIP (D-29 — lets downstream rules address them separately)"
  - "LARGEST_GAMMA == call_wall strike by construction (both are raw call gamma*OI peak pre-netting); hvl is the |net GEX| peak and therefore differs"
  - "RULES.md deduplicated 47 source rules to 38 canonical CR-IDs with full lineage audit table"
  - "get_all_active() returns list[Level] (C3/C5); consumers migrate field names in Plan 15-03"
metrics:
  duration_min: 45
  tasks_completed: 3
  completed_date: "2026-04-14"
---

# Phase 15 Plan 01: LevelBus Foundation + Canonical Rules Summary

Unified Level primitive, LevelBus upgrade of ZoneRegistry, stateless
LevelFactory, deduplicated 38-rule canonical catalog (RULES.md), and GEX
extensions — the foundation every subsequent Plan 15-02/03/04/05 builds on.

## What Shipped

- **`deep6/engines/level.py`** — `@dataclass(slots=True) class Level` with
  unified geometry (point levels set `price_top == price_bot`, zones use
  `price_top > price_bot`), 17-member `LevelKind` enum, 5-member
  `LevelState` FSM matching `ZoneState` verbatim, and `uid: int =
  uuid4().int` for stable mutation keying. Invariant check in
  `__post_init__` (threat T-15-01-01). `confidence` is a derived property,
  not a stored field, removing dual-source-of-truth risk when rules mutate
  score.
- **`deep6/engines/level_factory.py`** — stateless conversion functions:
  `from_volume_zone`, `from_narrative`, `from_absorption`,
  `from_exhaustion`, `from_momentum`, `from_rejection`, `from_gex`.
  D-07 wick geometry honored for ABSORB/EXHAUST (UW: `top=bar.high,
  bot=body_top`; LW: `top=body_bot, bot=bar.low`; 1-tick minimum width
  from caller-provided `tick_size`). `from_gex` emits up to six point
  Levels per snapshot (call wall, put wall, gamma flip, HVL, largest
  gamma, zero gamma).
- **`deep6/engines/zone_registry.py`** — in-place rename
  `ZoneRegistry` → `LevelBus` (D-09), `ZoneRegistry = LevelBus` alias
  preserved for one release. Unified `_levels: list[Level]` replaces
  dual `_zones` / `_gex` storage. New queries: `add_level`,
  `query_near`, `query_by_kind`, `get_top_n(n=6)`. `max_levels = 80` cap
  with eviction that prefers CREATED over DEFENDED/FLIPPED when scores
  are comparable (D-11). Legacy `add_zone` / `add_gex_levels` /
  `get_near_price` / `get_all_active` / `get_confluence` wrappers retained
  and delegate to LevelFactory + add_level.
- **`deep6/engines/gex.py`** — `GexLevels.largest_gamma_strike: float =
  0.0` (D-28), populated by `_compute_gex` from the already-tracked
  `max_call_strike` (raw call γ × OI peak, pre-netting). `zero_gamma`
  `@property` aliases `gamma_flip` (D-29).
- **`.planning/phases/15-.../RULES.md`** — 38 canonical CR-IDs derived
  from four research streams (DEEP6_INT §8 + industry §12 +
  microstructure §12 + auction_theory §15 = 47 raw). Dedup lineage table
  documents every merge (e.g., `DEEP6-03 ↔ IND-06` collapse to `CR-03`).
  Tier column tags each rule `EASY` / `MEDIUM` / `CALIBRATION-GATED`
  (D-16 — gated rules default OFF in `ConfluenceRulesConfig`).

## Identity Guarantee (C5)

`Level.uid` is assigned once at construction and preserved through
overlap-merge in `LevelBus.add_level`. ConfluenceRules (Plan 15-03) keys
its `score_mutations: dict[int, float]` by `level.uid`, not
`id(level)` — `id()` is not stable across copies / pickles /
`dataclasses.replace`, and Python can reuse addresses after GC. Callers
who mutate via the return table must snapshot uids BEFORE calling
`evaluate()`; merges during the same bar leave uids valid.

## Test Coverage

| File | Tests | Covers |
|------|-------|--------|
| `tests/engines/test_level.py` | 13 | slots enforcement, geometry invariant, point vs zone containment, 17-kind count, LevelState-vs-ZoneState equality, origin_ts + origin_bar, meta dict, confidence derivation, uid uniqueness, `replace()` uid preservation |
| `tests/engines/test_level_bus.py` | 19 | add zone merge (score+5, touches sum, peak bucket), different-dir/kind isolation, point dedup by (kind, price), query_near for zones+points, query_by_kind INVALIDATED filter, get_top_n desc, 80-cap eviction, DEFENDED preservation, `ZoneRegistry` alias, `add_zone`/`add_gex_levels` wrappers, C5 uid stability through merge and point replace, get_confluence smoke, clear/bulk_load |
| `tests/engines/test_level_factory.py` | 13 | VolumeZone round-trip (LVN/HVN), absorption UW/LW geometry, min-tick width on degenerate bars, exhaustion wick + direction-inferred fallback, momentum/rejection body geometry, GEX emission of 5 populated fields + skipping zeros + `gex_source` meta |
| `tests/engines/test_gex_largest_gamma.py` | 8 | `zero_gamma` alias, `_compute_gex` raw-call-peak population, differentiation from `hvl` when puts dominate at different strike, factory LARGEST_GAMMA + ZERO_GAMMA emission, default-values regression |

**Totals:** 53 new tests, all passing. Full engines-suite regression
(`tests/engines/` + `test_zone_registry.py` + `test_gex.py` +
`test_vp_context_engine.py` + `test_scorer.py`) = 93 passing.
Broader suite (all non-live, non-backtest, non-API tests) = 551 passing.

## Deviations from Plan

### Auto-fixed during execution

1. **[Rule 1 - Interpretation] LevelState member names — CREATED vs ACTIVE.**
   Plan 15-01 body text listed `LevelState: ACTIVE, DEFENDED, BROKEN, FLIPPED,
   INVALIDATED`. But D-03 requires LevelState to **match ZoneState verbatim**,
   and the dedicated test `test_level_state_matches_zone_state` asserts the
   same. Existing `deep6/engines/volume_profile.py:ZoneState` uses
   `CREATED, DEFENDED, BROKEN, FLIPPED, INVALIDATED`. I followed D-03
   (authoritative) + the test requirement and used `CREATED` rather than
   `ACTIVE`. Plan 15-02/03/04/05 will see `LevelState.CREATED` when reading
   freshly-created zones.

2. **[Rule 2 - Missing critical functionality] Legacy `test_zone_registry.py`
   ZONE-05 assertions updated.** Two legacy tests read
   `active[0].top_price` / `.bot_price` — VolumeZone field names. Per
   plan D-09/C3, `get_all_active()` now returns `list[Level]`; I updated
   the two assertions to `.price_top` / `.price_bot` (Level field names).
   The semantic invariant (peak-bucket keeps stronger range) is
   unchanged; only the reader-side attribute names moved.

3. **[Rule 3 - Blocking] `zero_gamma` property added with T-15-01-02, not
   deferred to T-15-01-03.** Tests in `test_level_factory.py` and
   `test_level_bus.py` asserted that `LevelFactory.from_gex` emits a
   `ZERO_GAMMA` point-Level, which requires `GexLevels.zero_gamma` to
   exist. Adding the property one task earlier (in the same commit as
   the factory) unblocked T-15-01-02 without changing the plan's
   structure — T-15-01-03 still adds `largest_gamma_strike` + engine
   population + dedicated `test_gex_largest_gamma.py`.

No Rule-4 architectural deviations. No auth gates encountered.

## Authentication Gates

None.

## Known Stubs

None — every surface added here has a concrete implementation and test
coverage.

## Threat Flags

None — no new network endpoints, auth paths, file-access patterns, or
trust-boundary schemas. The `add_level` API is in-process; input is
`Level` objects constructed by trusted factories; invariants enforced
in `Level.__post_init__`.

## Performance Budget

- `LevelBus.add_level`: O(n) over active Levels for zone-overlap search;
  n ≤ 80 (D-11). Measured with synthetic loads ≤ 10 µs/call on M2.
- `query_near` / `query_by_kind` / `get_top_n`: O(n). `get_top_n` sorts
  ≤ 80 items each call — acceptable for bar-close cadence.
- `LevelFactory.from_*`: all O(1) except `from_narrative` which is O(k)
  in signal count — `k` ≤ 10 typical.
- `from_gex`: O(1) (fixed 6-field iteration).

All well within the <1ms-per-bar-close budget (D-34).

## Handoff to Wave 2 (Plan 15-02)

Plan 15-02 (narrative-Level persistence + cross-session decay) consumes:

- `deep6.engines.level.Level` / `LevelKind` / `LevelState` — stable APIs.
- `deep6.engines.level_factory.from_narrative(result, *, strength_threshold=0.4,
   bar_index, tick_size, bar=None)` — single-source-of-truth signature.
- `deep6.engines.zone_registry.LevelBus.add_level(level)` — primary entry
  point. Overlap merges preserve `Level.uid` (C5).
- `LevelBus.get_all_active()` returns `list[Level]` — 15-02 should read
  `level.price_top`, `level.price_bot`, `level.score`, `level.state`,
  not VolumeZone field names.

Plan 15-03 additionally consumes:
- `ConfluenceRules.score_mutations: dict[int, float]` keyed by
  `Level.uid`. Mutation callers must snapshot `uids = [lv.uid for lv in
  bus.get_all_active()]` BEFORE calling `evaluate()` so the mutation
  table remains meaningful even if a merge happens mid-bar.
- `RULES.md` canonical CR-01..CR-38 with tier and lineage for the
  rule-switch dispatcher.

## Self-Check: PASSED

- Created files exist: `deep6/engines/level.py` ✓,
  `deep6/engines/level_factory.py` ✓, `RULES.md` ✓,
  `tests/engines/{test_level, test_level_bus, test_level_factory, test_gex_largest_gamma}.py` ✓.
- Modified files exist: `deep6/engines/zone_registry.py` ✓,
  `deep6/engines/gex.py` ✓.
- Commits exist on main:
  - `4202cee` feat(15-01): Level dataclass + LevelKind/LevelState + RULES.md ✓
  - `3a43380` feat(15-01): upgrade ZoneRegistry -> LevelBus + add LevelFactory ✓
  - `e6ce0e8` feat(15-01): populate GexLevels.largest_gamma_strike in _compute_gex ✓
- Automated verification: 53/53 plan tests green; 551/551 broader-suite tests green; RULES.md has 38 CR rows (in [35,40] band); `ZoneRegistry = LevelBus` alias present; `largest_gamma_strike` populated in `_compute_gex`.
