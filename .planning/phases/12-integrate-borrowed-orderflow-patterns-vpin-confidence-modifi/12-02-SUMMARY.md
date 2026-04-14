---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 02
subsystem: orderflow-signals
tags: [delta, intrabar, signal-fix, bit-lock-preserved]
requirements: [OFP-03, OFP-04]
dependency-graph:
  requires:
    - FootprintBar (phase 01)
    - DeltaEngine (phase 03)
    - SignalFlags bits 0-43 (phase 01 — stable)
  provides:
    - FootprintBar.max_delta / min_delta / running_delta (live intrabar extremes)
    - FootprintBar.delta_quality_scalar()
    - DeltaResult dataclass (signals + delta_quality)
    - DeltaEngine.process_with_quality()
    - DELTA_FAMILY_BITS whitelist ({21..32})
  affects:
    - DELT_TAIL (bit 22) detector — now uses TRUE intrabar extreme, not bar-geometry proxy
tech-stack:
  added: []
  patterns:
    - non-breaking-field-extension (dataclass defaults)
    - whitelisted-scalar-consumption (DELTA_FAMILY_BITS)
key-files:
  created:
    - tests/state/test_footprint_intrabar.py
  modified:
    - deep6/state/footprint.py
    - deep6/engines/delta.py
    - tests/test_delta.py
decisions:
  - DELT_TAIL bit 22 rewired in-place — no new bit added (bits 0-43 stable per STATE.md lock)
  - delta_quality_scalar() uses linear interpolation between 0.35 ratio (0.7x) and 0.95 ratio (1.15x)
  - FOOTGUN 3 guard: max_delta==0 falls back to bar_delta (trivial-extreme → 1.0x conservative)
  - process_with_quality() added as non-breaking sibling to process() — existing callers unaffected
  - DELTA_FAMILY_BITS whitelist lives in delta.py; downstream scorer (phase 04) enforces orthogonality to VPIN
metrics:
  duration: "~12 min"
  completed: "2026-04-13"
  tasks: 2
  commits: 4
---

# Phase 12 Plan 02: Intrabar Delta Tracking + DELT_TAIL Fix — Summary

Added live intrabar `max_delta` / `min_delta` / `running_delta` to `FootprintBar.add_trade()` and rewired the existing `DELT_TAIL` signal (bit 22) to use the TRUE intrabar extreme instead of the old bar-geometry proxy (`|delta|/total_vol`). A bar-quality scalar (`delta_quality_scalar()`) is emitted via the new `DeltaResult` for consumption by delta-family signals only — orthogonal to the VPIN multiplier.

## What Shipped

### FootprintBar (deep6/state/footprint.py)

Three new fields, default 0, updated live on every `add_trade()`:

| Field           | Semantics                                                   |
| --------------- | ----------------------------------------------------------- |
| `running_delta` | Live signed sum: `+size` on BUY (aggressor=1), `-size` on SELL (aggressor=2) |
| `max_delta`     | Highest `running_delta` seen during the bar (>= 0)          |
| `min_delta`     | Lowest `running_delta` seen during the bar (<= 0)           |

New method `delta_quality_scalar() -> float` with the contract:

- `ratio = |running_delta| / max(|max_delta|, |min_delta|, 1)`
- `ratio >= 0.95` → `1.15` (closing-at-extreme — strong conviction)
- `ratio <= 0.35` → `0.7` (peaked-and-faded — dissipation)
- linear interpolation between
- empty bar (all zeros) → `1.0` (neutral)

Post-finalize invariant (verified by test): `bar.bar_delta == bar.running_delta`.

### DeltaEngine (deep6/engines/delta.py)

`DELT_TAIL` (bit 22) rewired:

```python
# OLD (bar-geometry proxy)
delta_ratio = abs(delta) / bar.total_vol
if delta_ratio >= cfg.tail_threshold: ...

# NEW (TRUE intrabar extreme)
extreme = bar.max_delta if bar.max_delta > 0 else delta   # FOOTGUN 3 guard
tail_ratio = delta / extreme
if tail_ratio >= cfg.tail_threshold: ...
```

Negative deltas use `bar.min_delta` with symmetric fallback. No `close_pct` or `body_ratio` references remain.

New additions:

- `DeltaResult(signals: list[DeltaSignal], delta_quality: float = 1.0)` dataclass
- `DeltaEngine.process_with_quality(bar) -> DeltaResult` — non-breaking sibling of `process()`
- `DELTA_FAMILY_BITS = frozenset({21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32})` — whitelist for scorer (phase 04)

## Bit Lock Verification

- `grep -nE "bit\s*=\s*4[4-9]" deep6/engines/delta.py` → empty ✓
- `grep -n "close_pct\|body_ratio" deep6/engines/delta.py` → empty ✓
- `DELT_TAIL = 1 << 22` in `deep6/signals/flags.py` → unchanged ✓
- No new `SignalFlags` member added ✓

## Tests

**New file:** `tests/state/test_footprint_intrabar.py` (9 tests)

- monotonic rise: 10 buys × 5 → running=50, max=50, min=0
- reversal: 5 buys + 10 sells → running=-25, max=25, min=-25
- running_delta == bar_delta after finalize (invariant)
- `delta_quality_scalar()` closing-at-max → 1.15
- peaked-and-faded (running=20, max=100) → 0.7
- mixed neutral zone → in (0.7, 1.15)
- empty bar → 1.0
- negative extreme (closing at min) → 1.15
- level accumulation unchanged (regression guard)

**Updated:** `tests/test_delta.py`

- `make_bar()` helper gained `max_delta` / `min_delta` kwargs; defaults mirror closing-at-extreme
- TAIL tests rewritten for ratio-based semantics:
  - `test_tail_signal_closing_at_extreme` (bar_delta == max_delta)
  - `test_tail_not_fired_when_peaked_and_faded` (bar_delta = 0.5 × max_delta)
  - `test_negative_tail_signal_closing_at_min`
  - `test_tail_ratio_trivial_fallback_when_max_delta_zero` (FOOTGUN 3 guard)
- New `test_delta_quality_closing_at_extreme` / `test_delta_quality_peaked_and_faded`
- `test_delta_family_bits_whitelist_contains_only_delta_bits`
- `test_config_tail_threshold_override` updated for new semantics

**Full suite:** `556 passed in 3.26s` (no regressions, including phase 01–09 tests)

## Commits

| Type | Hash      | Message                                                              |
| ---- | --------- | -------------------------------------------------------------------- |
| test | `12a0821` | test(12-02): add failing tests for intrabar delta tracking           |
| feat | `30102a8` | feat(12-02): add intrabar delta tracking to FootprintBar             |
| test | `f06033c` | test(12-02): add failing tests for DELT_TAIL intrabar-extreme rewire |
| feat | `833f164` | feat(12-02): rewire DELT_TAIL to true intrabar extreme + DeltaResult |

## Deviations from Plan

None — plan executed exactly as written. TDD cycle for each task (RED → GREEN), no REFACTOR needed. No deviation rules triggered.

## Key Decisions

1. **No new bit added.** The plan's core constraint (STATE.md bit lock 0-43) was honored. `DELT_TAIL` remained bit 22; its detector was rewired in place.
2. **`process_with_quality()` as non-breaking sibling.** Rather than changing `DeltaEngine.process()` to return `DeltaResult` (breaks all existing callers — 44-signal engine, scorer, backtester), the scalar is delivered via a new method. Downstream consumers in phase 04 (scorer) will opt in explicitly.
3. **FOOTGUN 3 guard is conservative.** When `max_delta == 0` (untracked legacy bar or trivial single-trade case), effective extreme is `bar_delta` → ratio 1.0 → TAIL fires. This preserves signal for deserialized historical bars pre-dating this plan.
4. **DELTA_FAMILY_BITS as module constant.** Lives in `delta.py` (owner of the concept) rather than `flags.py` (pure enum). Phase 04 scorer will import and enforce.

## Known Stubs

None. All new fields are live and consumed; `DeltaResult.delta_quality` populates from the real scalar; whitelist is a frozenset ready for consumption.

## Threat Flags

None. No new network endpoints, auth paths, file access, or trust-boundary schema changes introduced.

## Self-Check: PASSED

Files present:
- `deep6/state/footprint.py` — FOUND
- `deep6/engines/delta.py` — FOUND
- `tests/state/test_footprint_intrabar.py` — FOUND
- `tests/test_delta.py` — FOUND (modified)

Commits present:
- `12a0821` — FOUND
- `30102a8` — FOUND
- `f06033c` — FOUND
- `833f164` — FOUND

Verification greps (from plan):
- `grep -nE "bit\s*=\s*4[4-9]" deep6/engines/delta.py` → empty ✓
- `grep -n "close_pct\|body_ratio" deep6/engines/delta.py` → empty ✓

Test suite:
- `pytest tests/state/test_footprint_intrabar.py tests/test_footprint.py tests/test_bar_builder.py tests/test_delta.py -x` → all pass ✓
- Full `pytest tests/` (excluding unrelated `tests/orderflow/`) → 556 passed ✓
