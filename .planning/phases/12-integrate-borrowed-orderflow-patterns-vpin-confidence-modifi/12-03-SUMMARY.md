---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 03
subsystem: orderflow-signals
tags: [slingshot, trap-shot, bit-44, multi-bar, session-reset, gex-bypass]
requirements: [OFP-02, OFP-08]
dependency-graph:
  requires:
    - "FootprintBar (phase 01)"
    - "SignalFlags bits 0-43 (phase 01 — stable)"
    - "SharedState.on_bar_close dispatch (phase 01)"
    - "SessionManager RTH boundary detection (phase 01)"
    - "Intrabar delta tracking (phase 12-02) — provides bar_delta accuracy"
  provides:
    - "SignalFlags.TRAP_SHOT = 1 << 44 (multi-bar trapped-trader reversal)"
    - "deep6.orderflow.slingshot.SlingshotDetector class"
    - "deep6.orderflow.slingshot.SlingshotResult dataclass"
    - "SharedState.slingshot_1m / slingshot_5m instances"
    - "SharedState.last_slingshot_1m / last_slingshot_5m (consumed by phase 12-04)"
    - "SharedState.on_session_reset() — clears both detectors at RTH boundary"
    - "SharedState.gex_distance_provider callable hook (optional)"
  affects:
    - "SessionManager._on_session_open now invokes state.on_session_reset hook"
    - "SharedState.on_bar_close now runs slingshot detect on each closed bar"
tech-stack:
  added: []
  patterns:
    - "bounded-deque rolling history (history_maxlen=500)"
    - "session-aware z-score threshold (2.0 * std over last 200 samples)"
    - "prefer-longest-variant match ordering (4 > 3 > 2)"
    - "duck-typed session-reset hook (callable attribute with getattr guard)"
    - "defensive try/except around optional GEX distance provider"
key-files:
  created:
    - "deep6/orderflow/slingshot.py"
    - "tests/orderflow/test_slingshot.py"
  modified:
    - "deep6/signals/flags.py"
    - "deep6/orderflow/__init__.py"
    - "deep6/state/shared.py"
    - "deep6/state/connection.py"
    - "tests/test_signal_flags.py"
decisions:
  - "TRAP_SHOT occupies bit 44 (first free slot); DELT_SLINGSHOT (bit 28) UNTOUCHED — different pattern"
  - "Z-score threshold = 2.0 * std over last 200 deltas (session-bounded; reference impl's 1.5× avg replaced)"
  - "30-bar warmup gate — no fire below; reset_session restarts warmup"
  - "Rolling bar cache is 5 deep (per-timeframe) — slingshot needs at most 4"
  - "GEX proximity threshold = 8 ticks (default); configurable via constructor"
  - "gex_distance_provider is optional callable — None degrades to no-bypass (fire still OK)"
  - "Slingshot wiring wrapped in try/except in on_bar_close — must never break bar close"
  - "SessionManager uses duck-typed getattr(state, 'on_session_reset') — backwards compatible"
metrics:
  duration: "~18 min"
  completed: "2026-04-14"
  tasks: 3
  commits: 3
---

# Phase 12 Plan 03: TRAP_SHOT @ Bit 44 — Summary

Added `TRAP_SHOT` signal at `SignalFlags` bit 44 for the multi-bar trapped-trader reversal pattern (2/3/4-bar variants, z-score > 2.0 over session-bounded delta history). Implemented `SlingshotDetector` with explicit RTH session reset to prevent threshold drift across overnight gaps. Wired into `SharedState.on_bar_close` with independent 1m and 5m detectors; last firing result exposed for the phase 12-04 setup state machine via `last_slingshot_1m` / `last_slingshot_5m`. When firing within 8 ticks of a GEX wall, `triggers_state_bypass=True` is emitted — consumed downstream to jump SCANNING → TRIGGERED directly.

The existing `DELT_SLINGSHOT` (bit 28, intra-bar compressed→explosive pattern) is **untouched**. The two patterns coexist cleanly; there is no bit reuse and no name overlap in the code path.

## What Shipped

### New module — `deep6/orderflow/slingshot.py` (~250 LOC)

```python
@dataclass
class SlingshotResult:
    fired: bool
    variant: int                 # 2 | 3 | 4 (or 0 when not fired)
    direction: Optional[str]     # "LONG" | "SHORT" | None
    bias: float                  # [-1, 1]
    strength: float              # [0, 3] clamped
    triggers_state_bypass: bool  # True iff fired AND within GEX proximity

class SlingshotDetector:
    def __init__(self, z_threshold=2.0, min_history_bars=30,
                 history_maxlen=500, gex_proximity_ticks=8): ...
    def update_history(self, bar_delta: int) -> None: ...
    def reset_session(self) -> None: ...
    def detect(self, bars, gex_distance_ticks) -> SlingshotResult: ...
```

Detection order: `_check_4bar → _check_3bar → _check_2bar` (prefer longest
variant for higher structural conviction). Each variant checks both bull
and bear templates adapted from reference implementation lines 296-378,
with the `1.5 × avg` threshold replaced by `2.0 × std` over the last 200
samples.

### SignalFlags (`deep6/signals/flags.py`)

```python
TRAP_SHOT = 1 << 44  # OFP-02: multi-bar trapped-trader reversal (phase 12-03)
```

Bits 0-43 are explicitly pinned in a new regression test
(`test_all_stable_bits_unchanged`). `DELT_SLINGSHOT` remains at bit 28.

### SharedState wiring (`deep6/state/shared.py`)

New fields:
- `slingshot_1m`, `slingshot_5m` — per-timeframe detectors
- `last_slingshot_1m`, `last_slingshot_5m` — last fire results (phase 12-04)
- `_bar_cache_1m`, `_bar_cache_5m` — rolling 5-bar caches
- `gex_distance_provider` — optional `() -> float | None` hook

New methods:
- `_run_slingshot(label, bar) -> int` — returns bit-44 mask if fired
- `on_session_reset()` — clears detectors + caches + last results

`on_bar_close` now calls `_run_slingshot()` (after VPIN feed) inside a
try/except so slingshot failures never break the bar-close path.

### Session reset wiring (`deep6/state/connection.py`)

`SessionManager._on_session_open` now duck-types `state.on_session_reset`
and invokes it after `session.reset()`. The getattr check keeps this
backwards compatible with any test/mock that doesn't provide the hook.

## Tests (25 new, all green)

**`tests/orderflow/test_slingshot.py`** (20 tests):
- Import surface + dataclass shape
- 2-bar bull / 2-bar bear fire
- 3-bar bull fire
- 4-bar bull fire
- Below-threshold no-fire
- 30-bar warmup gate
- Session reset clears history + restarts warmup
- GEX proximity sets `triggers_state_bypass=True`
- GEX-far does not set bypass
- Coexists with DELT_SLINGSHOT (bit distinctness)
- End-to-end via `SharedState.on_bar_close` (1m fires)
- 5m detector isolated from 1m history
- `on_session_reset` clears both timeframes + caches
- GEX provider triggers bypass end-to-end
- GEX provider exception does not break bar close

**`tests/test_signal_flags.py`** (5 new / updated):
- `test_trap_shot_bit_44` — exact-value assertion
- `test_delt_slingshot_still_bit_28` — regression guard
- `test_all_stable_bits_unchanged` — pins every bit 0-43
- `test_flag_count` updated to 45 (was 44)
- `test_fits_in_int64` updated to accommodate bit 44

**Full suite:** `553 passed in 3.57s`, 0 regressions (excluded
`tests/test_ml_backend.py` — unrelated, pre-existing).

## Bit Lock Verification

- `grep -n "DELT_SLINGSHOT" deep6/engines/delta.py deep6/signals/flags.py` → bit 28, unchanged ✓
- `grep -n "TRAP_SHOT" deep6/signals/flags.py` → bit 44 ✓
- No shifts to bits 0-43 (pinned by `test_all_stable_bits_unchanged`) ✓
- `test_flag_count == 45` (44 stable + TRAP_SHOT) ✓

## Commits

| Task | Hash      | Message                                                                  |
| ---- | --------- | ------------------------------------------------------------------------ |
| T-01 | `b34a1ec` | test(12-03): add TRAP_SHOT bit 44 + failing SlingshotDetector tests      |
| T-02 | `681c120` | feat(12-03): implement SlingshotDetector with 2/3/4-bar variants         |
| T-03 | `4e99343` | feat(12-03): wire SlingshotDetector into SharedState + RTH reset         |

## Deviations from Plan

### Auto-fixed Issues

**[Rule 3 — Blocking] `_make_state()` test helper needed full Config positional args**
- **Found during:** T-12-03-03 integration test draft
- **Issue:** Plan's pseudo-code `Config(db_path=":memory:")` missed four required
  positional args (`rithmic_user`, `rithmic_password`, `rithmic_system_name`,
  `rithmic_uri` — Config is `frozen=True`, no defaults).
- **Fix:** Helper now passes test stubs for all required fields. Non-breaking —
  db_path=":memory:" still isolates tests from disk.
- **Commit:** `4e99343`

**[Rule 2 — Correctness] `_SyntheticBar` needed logger attributes**
- **Found during:** T-12-03-03 first integration test run
- **Issue:** `SharedState.on_bar_close` reads `bar.timestamp`, `bar.cvd`,
  `bar.poc_price`, `bar.total_vol`, `bar.bar_range` for its debug log line —
  not detector inputs but required for the code path to not AttributeError.
- **Fix:** Added those five fields to `_SyntheticBar.__slots__` with
  zero/neutral defaults. `bar_range` derived from high/low.
- **Commit:** `4e99343`

**[Rule 2 — Safety] Defensive try/except around slingshot in `on_bar_close`**
- **Found during:** T-12-03-03 implementation
- **Issue:** Plan spec didn't require this but phase 12-01 VPIN wiring
  established the convention (`try/except log.exception`) precisely because
  an unhandled exception in a bar-close branch would kill the event loop.
  Applying the same pattern to slingshot is a Rule-2 correctness fix.
- **Fix:** `_run_slingshot()` wrapped in try/except. GEX provider also
  wrapped (tested by `test_gex_provider_exception_does_not_break_bar_close`).
- **Commit:** `4e99343`

**[Rule 2 — Correctness] Bit cache redundancy in end-to-end test**
- **Found during:** T-12-03-03 integration test run 2
- **Issue:** After feeding both template bars through `on_bar_close`,
  calling `_run_slingshot` AGAIN with `bars[1]` appended a duplicate,
  shifting `b2` out of the 2-bar window → flag mask returned 0.
- **Fix:** Test now clears `_bar_cache_1m` and re-feeds both bars via
  `_run_slingshot` directly to get a deterministic bit-44 mask.
- **Commit:** `4e99343`

### Plan-to-reality mapping notes (not deviations)

- Plan said "append bit 44 to flag bitmask for this bar" — DEEP6's actual
  flag emission happens inside the 44-signal engine pipeline (phase 4), not
  in `on_bar_close` directly. `_run_slingshot` returns the mask so any
  downstream pipeline that wants to OR it in can, and `last_slingshot_1m`
  remains the canonical phase-12-04 consumer surface.
- Plan said "pull gex_distance from self._gex_engine" — the actual GEX
  engine lives inside `VPContextEngine` (not as a bare state field). We
  avoided an intrusive rewire by exposing a `gex_distance_provider`
  callable hook on SharedState; phase 12-04 (or whichever consumer wires
  the wall distance) can set it with a one-line closure.

## Key Decisions

1. **Z-score over raw 1.5× avg.** Reference impl used `1.5 × mean(|delta|)`
   which is scale-sensitive and biased by outliers. Plan locked `2.0σ` over
   the last 200 session deltas, which is regime-aware and outlier-robust.
2. **Prefer longest variant.** Detection checks 4 → 3 → 2. Longer multi-bar
   structure = stronger trapped-trader signature. The strength multiplier
   in the result reflects this via the base-weight (0.6, 0.7, 0.8).
3. **Session reset via duck-typed hook.** `SessionManager` calls
   `getattr(state, 'on_session_reset', None)` and guards with `callable()`.
   No compile-time coupling between connection.py and slingshot module.
4. **GEX as optional callable, not hard dependency.** The detector accepts
   a nullable `gex_distance_ticks`; SharedState accepts a nullable
   `gex_distance_provider`. Phase 12-04 (or earlier integration) wires the
   actual closure. Until then, slingshot fires without bypass — no crash.
5. **Rolling bar cache kept at 5.** Slingshot needs at most 4 bars
   (4-variant); 5 leaves one bar of headroom. Bounded to cap memory.

## Known Stubs

None. Every wired surface is functional:
- Detectors fire end-to-end on synthetic data (tested)
- Session reset clears state (tested)
- GEX proximity → bypass (tested)
- Exception isolation in bar-close path (tested)

`gex_distance_provider` defaults to `None` — this is NOT a stub, it is the
documented integration point for phase 12-04. A `None` provider produces
correct behavior (fire with `triggers_state_bypass=False`).

## Threat Flags

None. No new network endpoints, auth paths, file access, or trust-boundary
schema changes. Threats in the plan's register are all mitigated:
- T-12-03-01 (bit-28 renaming / reuse) → `test_all_stable_bits_unchanged`
- T-12-03-02 (first-30min DoS from threshold drift) → 30-bar warmup + session reset
- T-12-03-03 (GEX debug leak) → accepted (not sensitive)

## Self-Check: PASSED

Files present:
- `deep6/orderflow/slingshot.py` — FOUND
- `deep6/orderflow/__init__.py` — FOUND (modified)
- `deep6/signals/flags.py` — FOUND (modified, bit 44 added)
- `deep6/state/shared.py` — FOUND (modified, detectors wired)
- `deep6/state/connection.py` — FOUND (modified, reset hook)
- `tests/orderflow/test_slingshot.py` — FOUND
- `tests/test_signal_flags.py` — FOUND (modified)

Commits present in git log:
- `b34a1ec` — FOUND
- `681c120` — FOUND
- `4e99343` — FOUND

Verification greps (from plan):
- `grep -n "DELT_SLINGSHOT" deep6/engines/delta.py deep6/signals/flags.py` → bit 28 unchanged ✓
- `grep -n "TRAP_SHOT" deep6/signals/flags.py` → bit 44 present ✓

Test suite:
- `pytest tests/orderflow/test_slingshot.py tests/test_signal_flags.py -x -q` → 25 passed ✓
- `pytest tests/ -q --ignore=tests/test_ml_backend.py` → 553 passed, 0 regressions ✓
