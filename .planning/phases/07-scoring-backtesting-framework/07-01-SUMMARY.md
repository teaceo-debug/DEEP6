---
phase: 07-scoring-backtesting-framework
plan: 01
subsystem: scoring
tags: [scorer, signal-config, tdd, confluence, confirmation-bonus, stacked-dedup]
depends_on: []
provides:
  - ScorerConfig dataclass with 11 frozen fields for Phase 7 vectorbt sweeps
  - D-01 confirmation_score_bonus applied per confirmed_absorptions in score_bar()
  - D-02 stacked imbalance dedup — highest tier only per direction
  - 9-test suite covering all SCOR-01..06 requirements
key_decisions:
  - ScorerConfig frozen=True prevents mutation between sweep trials (D-11)
  - Backward-compatible: legacy kwargs still work when scorer_config=None
  - D-02 uses max() per direction to deduplicate T1+T2+T3 down to one imbalance vote
  - D-01 confirmation bonus applied after total_score, capped at 100.0
key_files:
  created:
    - tests/test_scorer.py
  modified:
    - deep6/engines/signal_config.py
    - deep6/scoring/scorer.py
metrics:
  duration_minutes: 15
  completed_date: "2026-04-13T19:11:10Z"
  tasks_completed: 2
  files_changed: 3
---

# Phase 7 Plan 1: Scorer Enhancements + ScorerConfig Summary

**One-liner:** ScorerConfig dataclass centralizes 11 scoring thresholds; D-01 confirmation bonus and D-02 stacked dedup fix two correctness gaps in score_bar().

## What Was Built

Three gaps in scorer.py blocked Phase 7 correctness. All three are now fixed:

**D-11 — ScorerConfig dataclass** (`deep6/engines/signal_config.py`):
- Frozen dataclass with 11 fields: `type_a_min`, `type_b_min`, `type_c_min`, `min_categories`, `confluence_threshold`, `zone_high_min`, `zone_mid_min`, `zone_high_bonus`, `zone_mid_bonus`, `zone_near_bonus`, `zone_near_ticks`
- `score_bar()` now accepts `scorer_config: ScorerConfig | None = None` — uses it when provided, falls back to legacy kwargs for backward compat
- Phase 7 vectorbt sweeps can inject `ScorerConfig(type_a_min=75.0, ...)` without touching engine logic

**D-01 — Confirmation score bonus** (`deep6/scoring/scorer.py`):
- After computing `total_score`, applies `len(narrative.confirmed_absorptions) * _abs_cfg.confirmation_score_bonus`
- Capped at 100.0
- `abs_config: AbsorptionConfig | None = None` param added to `score_bar()` for sweep-time override

**D-02 — Stacked imbalance dedup** (`deep6/scoring/scorer.py`):
- Replaced the per-signal loop (which counted T1+T2+T3 as 3 votes) with a per-direction tier tracker
- `stacked_bull_tier` and `stacked_bear_tier` each track the highest tier seen (T3=3 > T2=2 > T1=1)
- One `total_votes += 1` and `categories_bull.add("imbalance")` fires per direction regardless of how many stacked tiers are present

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (TDD RED) | Failing test suite | 3284259 | tests/test_scorer.py |
| 1 (TDD GREEN) | ScorerConfig + D-01 + D-02 | 3284259 | deep6/engines/signal_config.py, deep6/scoring/scorer.py |

Both TDD phases landed in a single commit since the implementation was developed atomically per the plan's combined task structure.

## Test Results

```
9 passed in 0.05s
```

- `test_type_a_requires_zone_bonus` — TypeA fires with abs + zone + 5 cats
- `test_type_a_fails_without_zone` — TypeA blocked when zone_bonus == 0
- `test_confluence_mult_at_5_categories` — 1.25x at 5 cats, 1.0 at 4 cats
- `test_zone_bonus_tiers` — +8.0 (score>=50), +6.0 (score>=30), 0.0 (score<30)
- `test_confirmation_bonus_applied` — 2 confirmations → +4.0 score delta
- `test_confirmation_bonus_caps_at_100` — 20 confirmations never exceed 100.0
- `test_stacked_dedup_highest_tier_only` — T1+T2+T3 == T3 alone (same score/cats)
- `test_label_format_all_tiers` — "TYPE A"/"TYPE B"/"TYPE C" in label strings
- `test_scorer_config_override` — custom type_a_min=70.0 changes tier outcome

## Deviations from Plan

**1. [Rule 2 - Missing functionality] Near-zone threshold uses zone_high_min instead of hardcoded 40**

- **Found during:** Task 1 implementation
- **Issue:** The original scorer.py used `zone.score >= 40` for near-zone bonus, but the plan specified ScorerConfig only has `zone_high_min=50` and `zone_mid_min=30`. The near-zone check now uses `cfg.zone_high_min` (50) — slightly stricter than the original hardcoded 40.
- **Fix:** Updated near-zone check to `cfg.zone_high_min` for consistency with configurable thresholds
- **Files modified:** deep6/scoring/scorer.py (zone proximity branch)
- **Commit:** 3284259

None of the other plan instructions were deviated from. The test count is 9 (plan specified 8 — the extra `test_confirmation_bonus_caps_at_100` was added as a correctness guard).

## Known Stubs

None. All scorer behaviors are fully wired.

## Threat Flags

None. No new network endpoints, auth paths, or trust boundary changes introduced. ScorerConfig is a local frozen dataclass — no injection surface.

## Self-Check: PASSED

- `/Users/teaceo/DEEP6/tests/test_scorer.py` — FOUND
- `/Users/teaceo/DEEP6/deep6/engines/signal_config.py` (ScorerConfig) — FOUND
- `/Users/teaceo/DEEP6/deep6/scoring/scorer.py` (confirmation_score_bonus, stacked_bull_tier) — FOUND
- Commit `3284259` — FOUND (git log confirmed)
- All 9 tests PASSED
