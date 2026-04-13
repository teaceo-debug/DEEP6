---
phase: 02-absorption-exhaustion-core
plan: 01
subsystem: signal-engines
tags: [config-extraction, exhaustion, delta-gate, refactor, backward-compat]
dependency_graph:
  requires: []
  provides: [signal_config.AbsorptionConfig, signal_config.ExhaustionConfig, exhaustion._delta_trajectory_gate]
  affects: [deep6/engines/absorption.py, deep6/engines/exhaustion.py, deep6/engines/narrative.py, scripts/backtest_signals.py]
tech_stack:
  added: []
  patterns: [frozen-dataclass-config, optional-config-param-with-default, universal-gate-pattern]
key_files:
  created:
    - deep6/engines/signal_config.py
  modified:
    - deep6/engines/absorption.py
    - deep6/engines/exhaustion.py
    - deep6/engines/narrative.py
    - scripts/backtest_signals.py
decisions:
  - "Config as frozen dataclass (not dict) — hashable, immutable, IDE-navigable, Phase 7 sweep-ready"
  - "vol_ema and atr kept as runtime params in detect_absorption/detect_exhaustion — not tunable thresholds"
  - "Zero print exempt from delta gate — structural gap signal exists regardless of delta direction"
  - "Fading momentum keeps internal 0.15 threshold alongside gate — pronounce divergence requirement"
  - "config=None default preserves full backward compat — all existing callers unchanged"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 1
  files_modified: 4
---

# Phase 02 Plan 01: Config Extraction + Universal Delta Gate Summary

**One-liner:** Extracted all 14 absorption/exhaustion thresholds into frozen config dataclasses and implemented universal delta trajectory divergence gate filtering exhaustion variants 2-6.

## What Was Built

### signal_config.py (new)
Two `@dataclass(frozen=True)` classes ready for Phase 7 vectorbt parameter sweeps:

- `AbsorptionConfig` — 7 fields: absorb_wick_min, absorb_delta_max, passive_extreme_pct, passive_vol_pct, stop_vol_mult, evr_vol_mult, evr_range_cap
- `ExhaustionConfig` — 7 fields: thin_pct, fat_mult, exhaust_wick_min, fade_threshold, cooldown_bars, delta_gate_min_ratio, delta_gate_enabled

All defaults match the original function kwargs exactly (D-01: no hand-tuning until Phase 7).

### absorption.py (refactored)
`detect_absorption(bar, atr, vol_ema, config=None)` — `config` param added. All 7 threshold references replaced with `cfg.field_name`. `atr` and `vol_ema` remain as runtime params (not tunable). Full backward compatibility preserved.

### exhaustion.py (refactored + gate added)
`detect_exhaustion(bar, prior_bar, bar_index, atr, config=None)` — `config` param added. All 5 threshold references replaced with `cfg.field_name`. `cooldown_bars` moved from kwarg to `cfg.cooldown_bars`.

New `_delta_trajectory_gate(bar, config) -> bool`:
- Returns True (pass) when gate disabled, delta too small (< 0.10), or delta diverges from price direction
- Returns False (block) when bullish bar has positive delta or bearish bar has negative delta — aggressor not fading
- Applied between zero print detection and variants 2-6
- O(1) cost per bar (T-02-03 mitigated)

### narrative.py (wired)
`classify_bar()` gains `abs_config` and `exh_config` optional params. Both flow to their respective detectors. Cascade priority verified: ABSORPTION(1) < EXHAUSTION(2) < MOMENTUM(3) < REJECTION(4) < QUIET(5).

### scripts/backtest_signals.py (updated)
Imports AbsorptionConfig/ExhaustionConfig. Creates default instances at top of `run_backtest()`. Passes both to `classify_bar()`.

## Decisions Made

1. **Frozen dataclass over dict** — `@dataclass(frozen=True)` gives immutability (T-02-01), hashability for caching, IDE navigation, and type safety. Phase 7 sweep can create custom instances without mutation risk.

2. **vol_ema and atr stay as runtime params** — These are computed live from market data, not tunable thresholds. They belong in the function signature, not in config.

3. **Zero print exempt from delta gate** — Zero prints are structural gaps (missing volume at a price level). They exist regardless of whether delta is fading — the gap fact is independent of aggressor state.

4. **Fading momentum retains internal 0.15 threshold** — The universal gate confirms basic delta divergence (>10% ratio). Fading momentum is a stronger signal requiring pronounced divergence (>15%). The two checks are complementary, not redundant.

5. **config=None default** — All existing callers (narrative.py, scorer.py, backtest_signals.py) continue working without modification. Zero breaking changes.

## Verification Results

All plan-specified automated checks passed:
- `AbsorptionConfig()` defaults: absorb_wick_min=30.0, absorb_delta_max=0.12, etc.
- `ExhaustionConfig()` defaults: cooldown_bars=5, delta_gate_enabled=True, delta_gate_min_ratio=0.10
- Bullish bar + positive delta: gate returns False (blocked)
- Bullish bar + negative delta: gate returns True (allowed)
- Gate disabled: always returns True
- `classify_bar()` with explicit configs returns QUIET for empty bar
- `classify_bar()` with no config returns QUIET (backward compat)
- NarrativeType values: ABSORPTION=1, EXHAUSTION=2, MOMENTUM=3, REJECTION=4, QUIET=5
- All scorer.py imports still resolve

## Commits

| Hash | Description |
|------|-------------|
| fc0ce6e | feat(02-01): extract thresholds into signal_config.py + universal delta gate (EXH-07) |
| f6a6f4b | feat(02-01): wire AbsorptionConfig/ExhaustionConfig into classify_bar and backtest pipeline |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None in files created/modified by this plan. Note: `FADING_MOMENTUM` (EXH-05) has an existing "stub" comment indicating it will be enhanced when E8 CVD linear regression slope is available (Phase 3). This stub predates this plan and is intentional — tracked in the phase 02 plan for exhaustion variants.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

Files confirmed present:
- deep6/engines/signal_config.py: FOUND
- deep6/engines/absorption.py: modified (FOUND)
- deep6/engines/exhaustion.py: modified (FOUND)
- deep6/engines/narrative.py: modified (FOUND)
- scripts/backtest_signals.py: modified (FOUND)

Commits confirmed:
- fc0ce6e: FOUND
- f6a6f4b: FOUND
