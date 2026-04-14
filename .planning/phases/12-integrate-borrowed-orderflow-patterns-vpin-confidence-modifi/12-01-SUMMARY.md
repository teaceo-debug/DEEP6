---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 01
subsystem: orderflow
tags: [vpin, orderflow, scoring, flow-toxicity]
requirements: [OFP-01, OFP-07]
dependency_graph:
  requires:
    - "deep6/state/footprint.py FootprintBar (ask_vol / bid_vol — DATA-02)"
    - "deep6/scoring/scorer.py score_bar() — two-layer scorer"
    - "deep6/state/shared.py SharedState.on_bar_close dispatch"
  provides:
    - "deep6/orderflow/vpin.py VPINEngine — flow-toxicity confidence modifier"
    - "scorer vpin_modifier kwarg — final-stage multiplier on fused total_score"
    - "SharedState.vpin field — one engine instance per session (1m)"
  affects:
    - "deep6/scoring/scorer.py (multiplier pipeline extended)"
    - "deep6/state/shared.py (on_bar_close now feeds VPIN on 1m bars)"
tech_stack:
  added: []
  patterns:
    - "Volume-clock bucketing with proportional buy/sell spill"
    - "Rolling percentile over history deque for continuous modifier curve"
key_files:
  created:
    - "deep6/orderflow/__init__.py"
    - "deep6/orderflow/vpin.py"
    - "tests/orderflow/__init__.py"
    - "tests/orderflow/test_vpin.py"
    - "tests/scoring/__init__.py"
    - "tests/scoring/test_scorer_with_vpin.py"
  modified:
    - "deep6/scoring/scorer.py"
    - "deep6/state/shared.py"
decisions:
  - "VPIN applies to FUSED total_score only — never to per-signal raw scores"
  - "IB and VPIN are SEPARATE multiplier line items — never fused (FOOTGUN 1)"
  - "Exact ask_vol/bid_vol aggressor split replaces BVC/normal-CDF from reference impl"
  - "Warmup <10 buckets returns neutral 1.0 (avoids reference NaN saturation)"
  - "Continuous modifier curve: pct 0.0 -> 1.2x, 0.5 -> 1.0x, 1.0 -> 0.2x"
  - "1m timeframe only; 5m VPIN deferred to future phase"
metrics:
  duration_min: 12
  tasks_completed: 3
  completed_date: "2026-04-14"
---

# Phase 12 Plan 01: VPIN Confidence Modifier Summary

Add VPIN (Volume-Synchronized Probability of Informed Trading) as a continuous
0.2x–1.2x flow-toxicity modifier on the final fused LightGBM/scorer confidence,
using DEEP6's exact aggressor split instead of the reference impl's BVC.

## What Shipped

- **`deep6/orderflow/vpin.py`** — `VPINEngine` with `update_from_bar(bar)`,
  `get_vpin()`, `get_percentile()`, `get_confidence_modifier()`,
  `get_flow_regime()`. 1000-contract volume clock, 50-bucket window,
  2000-sample history, 10-bucket warmup. No `math.erf`, no BVC branch
  (enforced by `test_no_bvc_path`).
- **`deep6/scoring/scorer.py`** — new `vpin_modifier: float = 1.0` kwarg on
  `score_bar()`. Applied as the final stage on the fused `total_score`, after
  `ib_mult`, followed by `max(0.0, min(100.0, total_score))`. Module docstring
  now documents the locked multiplier order.
- **`deep6/state/shared.py`** — `SharedState` owns one `VPINEngine` instance;
  `on_bar_close` feeds it on 1m bars, inside a try/except so VPIN cannot break
  the bar-close path.
- **Tests:** 7 unit tests for `VPINEngine` + 7 integration tests for scorer wiring.

## Multiplier Pipeline (locked)

```
base_score
  * confluence_mult            # category count
  + zone_bonus                 # volume profile
  + gex_near_wall_bonus        # GEX
  * agreement                  # engine agreement ratio
  * ib_mult                    # Initial Balance (1.15 in first 60 bars)
--------------------------------  per-signal / fused composition ends here
  * vpin_modifier              # phase 12-01 — fused-only, separate line item
clip(0, 100)
```

Guarantees:
- `ib_mult` and `vpin_modifier` are NEVER multiplied together (source test).
- `vpin_modifier` never touches per-signal raw scores — only fused total.
- Clip applies AFTER VPIN, so a clean-tape 1.2x that overflows still caps at 100.

## Test Coverage

| Test | Asserts |
|---|---|
| `test_warmup_returns_neutral` | <10 buckets → modifier == 1.0 |
| `test_exact_aggressor_split` | ask=800/bid=200 → bucket buy=800 sell=200 (no BVC) |
| `test_bucket_completion_at_1000` | 2×500-volume bars close exactly 1 bucket |
| `test_percentile_grows_with_imbalance` | imbalanced run pushes percentile > 0.8 |
| `test_confidence_modifier_bounded` | 200 random bars: modifier always in [0.2, 1.2] |
| `test_no_bvc_path` | module source has no `math.erf` / `erf(` |
| `test_zero_volume_bar_is_safe` | empty bar is a no-op (T-12-01-01 mitigation) |
| `test_default_modifier_preserves_existing_behavior` | default 1.0 == absent kwarg |
| `test_vpin_reduces_fused_score_when_toxic` | modifier 0.2 → proportional reduction |
| `test_vpin_expands_fused_score_when_clean_but_clips_at_100` | 1.2 grows score, caps 100 |
| `test_clip_bounds_score_to_zero_hundred` | 0 ≤ total_score ≤ 100 for all modifiers |
| `test_toxic_vpin_can_demote_tier_but_never_changes_direction` | direction invariant |
| `test_ib_and_vpin_are_separate_line_items` | source inspection: no `ib_mult * vpin_modifier` |
| `test_final_stage_ordering_vpin_after_ib_before_clip` | source order: ib → vpin → clip |

Results: **14 new tests pass; 513 total tests pass; 0 regressions.**

## Commits

| Task | Commit | Message |
|---|---|---|
| T-12-01-01 (RED) | `adb9834` | test(12-01): add failing VPINEngine tests |
| T-12-01-02 (GREEN) | `e1a8abf` | feat(12-01): implement VPINEngine with exact aggressor split |
| T-12-01-03 (INTEGRATE) | `7da0f05` | feat(12-01): wire VPIN as final-stage confidence modifier |

## Deviations from Plan

### Auto-fixed Issues

**[Rule 2 — Safety] Defensive try/except around VPIN feed in `on_bar_close`**
- **Found during:** T-12-01-03 integration
- **Issue:** Plan called for direct `self.vpin.update_from_bar(bar)` — an unhandled
  exception in VPIN (e.g., malformed bar in future regressions) would kill the
  bar-close coroutine and silently stop the event loop.
- **Fix:** Wrap in `try/except Exception: log.exception(...)`. VPIN failures
  degrade to neutral multiplier on subsequent bars rather than taking down the
  trading path.
- **Files modified:** `deep6/state/shared.py`
- **Commit:** `7da0f05`

**[Rule 2 — Correctness] Added `test_zero_volume_bar_is_safe`**
- **Found during:** T-12-01-01 test design
- **Issue:** Threat model T-12-01-01 calls for a zero-volume-bar DoS mitigation
  and unit test; the plan's task 1 listed six tests but the DoS test wasn't
  enumerated explicitly.
- **Fix:** Added the test plus an early-return path in `update_from_bar`.
- **Files modified:** `tests/orderflow/test_vpin.py`, `deep6/orderflow/vpin.py`
- **Commit:** `adb9834` / `e1a8abf`

**[Rule 3 — Blocking] `tests/scoring/` directory didn't exist**
- **Found during:** T-12-01-03
- **Issue:** Plan wrote tests to `tests/scoring/test_scorer_with_vpin.py` but
  the package dir did not exist (existing scorer tests live at `tests/test_scorer.py`).
- **Fix:** Created `tests/scoring/__init__.py`.
- **Commit:** `7da0f05`

### Plan-to-reality mapping note (not a deviation)

The plan prose in task 3 said *"SharedState.on_bar_close for 1m bar: calls
vpin.update_from_bar(bar) BEFORE scorer.score_bar(...)"*. In DEEP6 today the
scorer is invoked from scripts / downstream engines, not inside
`SharedState.on_bar_close`. The implementation honors the plan's ARTIFACT
requirement (`key_links.from.on_bar_close → vpin.update_from_bar`) by feeding
VPIN inside `on_bar_close`; downstream scorer callers pick up the modifier via
`state.vpin.get_confidence_modifier()` and pass it as the new `vpin_modifier`
kwarg. No callers were changed in this plan — each signal-engine integration
will adopt the kwarg explicitly in its own phase (preserving the default-1.0
backward-compat).

## Verification

- `pytest tests/orderflow/ tests/scoring/ tests/test_scorer.py -x -q` → **23 passed**
- `pytest tests/ -q --ignore=tests/test_ml_backend.py` → **513 passed, 0 regressions**
- `grep -n "math.erf" deep6/orderflow/vpin.py` → **no matches**
- `grep -n "vpin_modifier" deep6/scoring/scorer.py` → **3 matches** (docstring,
  kwarg, single application site)

## Known Stubs

None — all wiring is functional. Downstream signal-engine invocations still
use `vpin_modifier=1.0` (the default) until each engine is updated to read
`state.vpin.get_confidence_modifier()`; this is intentional and documented
(see "Plan-to-reality mapping note" above). No UI / data stubs introduced.

## Self-Check: PASSED

- [x] `deep6/orderflow/vpin.py` exists (confirmed via test import)
- [x] `deep6/orderflow/__init__.py` exists
- [x] `tests/orderflow/test_vpin.py` exists — 7 passing tests
- [x] `tests/scoring/test_scorer_with_vpin.py` exists — 7 passing tests
- [x] Commit `adb9834` present in git log
- [x] Commit `e1a8abf` present in git log
- [x] Commit `7da0f05` present in git log
- [x] `scorer.py` contains `vpin_modifier` kwarg and `total_score *= vpin_modifier` application
- [x] `shared.py` imports `VPINEngine` and feeds it in `on_bar_close` on 1m bars
