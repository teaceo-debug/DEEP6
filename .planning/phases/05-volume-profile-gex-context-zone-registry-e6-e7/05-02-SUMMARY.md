---
phase: 05-volume-profile-gex-context-zone-registry-e6-e7
plan: "02"
subsystem: zone-registry-e6-e7
tags:
  - zone-registry
  - confluence
  - e6-engine
  - e7-stub
  - volume-profile
  - gex-integration
dependency_graph:
  requires:
    - "05-01 (POCConfig, VolumeProfileConfig, GexConfig, updated engines)"
    - "deep6/engines/volume_profile.py (SessionProfile, VolumeZone, ZoneState, ZoneType)"
    - "deep6/engines/poc.py (POCEngine, POCSignal, get_migration)"
    - "deep6/engines/gex.py (GexEngine, GexLevels, GexSignal)"
    - "deep6/engines/signal_config.py (POCConfig, VolumeProfileConfig, GexConfig)"
  provides:
    - "ZoneRegistry — centralized zone store for all types"
    - "ConfluenceResult — cross-type confluence scoring data"
    - "E6VPContextEngine — unified VP+GEX+POC context engine"
    - "VPContextResult — per-bar context struct for Phase 7 scorer"
    - "E7MLQualityEngine — stub quality multiplier (returns 1.0)"
  affects:
    - "Phase 7 confluence scorer (07-01) — consumes VPContextResult"
    - "Phase 10 dashboard — ZoneRegistry.get_all_active() is data source (ZONE-04)"
tech_stack:
  added:
    - "ZoneRegistry (pure Python, no deps beyond volume_profile + gex)"
    - "ConfluenceResult dataclass"
    - "VPContextResult dataclass"
    - "E6VPContextEngine"
    - "E7MLQualityEngine stub"
  patterns:
    - "Merge-on-add: overlapping same-type same-direction zones consolidate"
    - "Peak bucket: merged zone inherits higher-score zone's price range"
    - "Cross-type confluence: VolumeZone + GEX level within N ticks"
    - "Session reset with prior_bins VPRO-07 decay (0.70 weight)"
key_files:
  created:
    - "deep6/engines/zone_registry.py"
    - "deep6/engines/vp_context_engine.py"
  modified: []
decisions:
  - "ZoneRegistry mutation on merge: VolumeZone is not frozen so in-place score/range update is valid"
  - "Peak bucket (ZONE-05): merged zone uses higher-score zone's price range, not union — tighter focus on volume concentration"
  - "E7 stub: returns 1.0 unconditionally; E7 doc explains Phase 9 XGBoost replacement"
  - "on_session_start re-creates SessionProfile with config reference from old instance — preserves config without copying"
metrics:
  duration: "~10 minutes"
  completed: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 05 Plan 02: ZoneRegistry + E6VPContextEngine + E7MLQualityEngine Summary

**One-liner:** ZoneRegistry with merge+confluence (ZONE-01..05) and E6 engine wiring POC+VP+GEX into VPContextResult per bar, E7 stub returning 1.0.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ZoneRegistry — centralized zone store with merge and confluence | `0cdac1b` | `deep6/engines/zone_registry.py` (created) |
| 2 | E6VPContextEngine and E7MLQualityEngine stub | `f7c5d9f` | `deep6/engines/vp_context_engine.py` (created) |

## What Was Built

### ZoneRegistry (`deep6/engines/zone_registry.py`)

Centralized store implementing ZONE-01 through ZONE-05:

- **ZONE-01:** `get_near_price(price, ticks=4)` returns active VolumeZone list within threshold
- **ZONE-02:** `get_confluence(price, ticks=4)` fires when VolumeZone near price AND GEX level near price → `ConfluenceResult(has_confluence=True, score_bonus=6/8)`
- **ZONE-03:** `add_zone()` merges overlapping same-type same-direction zones (score = max + 5, capped at 100)
- **ZONE-04:** `get_all_active(min_score=0.0)` exposes all live zones for downstream dashboard
- **ZONE-05:** Peak bucket — merged zone inherits higher-score zone's price range (tighter than union)
- **GEX storage:** `add_gex_levels(GexLevels)` extracts call wall, put wall, gamma flip, HVL as named price points; `get_gex_level(name)` retrieves by name
- **Session reset:** `clear()` removes all zones and GEX levels; `bulk_load()` for SessionProfile reload

### E6VPContextEngine + E7MLQualityEngine (`deep6/engines/vp_context_engine.py`)

**VPContextResult** dataclass:
- `poc_signals: list[POCSignal]`
- `gex_signal: Optional[GexSignal]`
- `active_zones: list[VolumeZone]`
- `zone_events: list[str]`
- `confluence: Optional[ConfluenceResult]`
- `poc_migration: tuple[int, float]`
- `ml_quality: float = 1.0`

**E6VPContextEngine.process(bar)** — 7-step pipeline:
1. `session_profile.add_bar(bar)` — accumulate volume
2. `detect_zones(bar.close)` → `registry.add_zone()` for each new zone
3. `update_zones(bar, bar_count)` → zone lifecycle events list
4. `poc_engine.process(bar)` → POC signals
5. `gex_engine.get_signal(bar.close)` → GEX regime/direction
6. `registry.get_confluence(bar.close)` → confluence result
7. Return `VPContextResult`

**E6VPContextEngine.fetch_gex(spot_price)** — calls `gex_engine.fetch_and_compute()` and loads levels into registry.

**E6VPContextEngine.on_session_start(prior_bins)** — resets SessionProfile (with VPRO-07 decay at 0.70), clears registry, resets POCEngine.

**E7MLQualityEngine.score()** — always returns `1.0` (ENG-07 stub, Phase 9 replacement noted in docstring).

## Deviations from Plan

### [Rule 3 - Blocking] Worktree missing 05-01 changes

- **Found during:** Pre-execution setup
- **Issue:** Worktree `worktree-agent-a9bc54ce` was at commit `82ef408` (pre-05-01), missing `signal_config.py`, updated `POCEngine(config=)`, updated `SessionProfile(config=, prior_bins=)`, and `get_migration()` on `POCEngine`
- **Fix:** `git merge c50c7bf` — fast-forward merged main branch into worktree (all 05-01 results now present)
- **Files modified:** All 05-01 files brought in via merge
- **Commit:** Merge was fast-forward, no separate commit (pre-existing work)

## Known Stubs

| Stub | File | Line | Reason |
|------|------|------|--------|
| `E7MLQualityEngine.score()` returns `1.0` | `deep6/engines/vp_context_engine.py` | ~136 | ENG-07 by design; Phase 9 replaces with Kalman filter + XGBoost |
| `VPContextResult.ml_quality` always `1.0` | `deep6/engines/vp_context_engine.py` | ~29 | Flows from E7 stub; intentional until Phase 9 |

These stubs do not prevent plan goal: ZoneRegistry and E6 wiring are fully functional. ml_quality=1.0 means no adjustment (neutral), which is the correct behavior until Phase 9.

## Threat Flags

None. No new network endpoints, auth paths, or schema changes. ZoneRegistry is purely in-process. GEX network calls remain in GexEngine (pre-existing surface from 05-01).

## Self-Check: PASSED

- `deep6/engines/zone_registry.py` — FOUND
- `deep6/engines/vp_context_engine.py` — FOUND
- Commit `0cdac1b` — FOUND
- Commit `f7c5d9f` — FOUND
- `python -m pytest tests/ -x -q` — 174 passed
