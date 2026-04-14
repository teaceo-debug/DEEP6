---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 04
subsystem: orderflow-state-machine
tags: [setup-tracker, state-machine, dual-timeframe, soak-weight, explicit-close, event-store]
requirements: [OFP-05, OFP-08]
dependency-graph:
  requires:
    - "ScorerResult (deep6/scoring/scorer.py — phase 04)"
    - "SlingshotDetector / SlingshotResult (phase 12-03)"
    - "SharedState.last_slingshot_1m / last_slingshot_5m (phase 12-03)"
    - "EventStore (deep6/api/store.py — phase 09-01)"
  provides:
    - "deep6.orderflow.setup_tracker.SetupTracker (5-state lifecycle, per-timeframe)"
    - "deep6.orderflow.setup_tracker.SetupTransition dataclass"
    - "deep6.orderflow.setup_tracker.ActiveSetup dataclass"
    - "EventStore.record_setup_transition / query_setup_transitions"
    - "EventStore setup_transitions SQLite table"
    - "SharedState.setup_tracker_1m / setup_tracker_5m (independent instances)"
    - "SharedState.feed_scorer_result — drives state machine + persists transitions"
    - "SharedState.close_trade — routes by setup_id prefix"
    - "SharedState.event_store attach-point"
  affects:
    - "deep6/orderflow/__init__.py (exports SetupTracker, SetupTransition, ActiveSetup)"
    - "deep6/state/shared.py (new fields + methods, on_bar_close path unchanged)"
    - "deep6/api/store.py (setup_transitions schema + APIs)"
tech-stack:
  added: []
  patterns:
    - "state-machine-consumes-shape (ScorerResult / SlingshotResult via getattr)"
    - "explicit-close-only-transition (MANAGING → COOLDOWN; reference footgun fixed)"
    - "failsafe-with-warning (30-bar emergency brake)"
    - "setup-id prefix-based routing (1m-/5m-)"
    - "linear-ramp-weight (1.0 → 5.0 over 10 soak bars)"
    - "defensive-close-trade-no-op (wrong setup_id does not transition state)"
    - "async-persistence-in-try-except (never breaks bar-close)"
key-files:
  created:
    - "deep6/orderflow/setup_tracker.py"
    - "tests/orderflow/test_setup_tracker.py"
    - "tests/orderflow/test_setup_tracker_integration.py"
  modified:
    - "deep6/orderflow/__init__.py"
    - "deep6/state/shared.py"
    - "deep6/api/store.py"
    - "tests/test_ml_backend.py"
decisions:
  - "MANAGING → COOLDOWN is NEVER auto — explicit close_trade() or 30-bar failsafe only (footgun fixed)"
  - "Failsafe fires at bars_managing > managing_failsafe_bars (default 30) with WARNING log via both structlog and stdlib"
  - "Soak ramp: current_weight() = 1.0 + 0.4 * min(soak_bars, 10), clamped at 5.0"
  - "Slingshot bypass: only fires from SCANNING/DEVELOPING, never overrides TRIGGERED/MANAGING"
  - "Setup IDs prefixed by timeframe ('1m-<uuid12>' / '5m-<uuid12>') for unambiguous routing"
  - "Direction flip during DEVELOPING resets to SCANNING + attempts same-bar re-entry under new direction"
  - "close_trade with mismatched setup_id is a defensive no-op (warns, returns None)"
  - "event_store on SharedState is optional — absent in tests, attached in API lifespan"
  - "ScorerResult interop: tier read via .name when enum, str() fallback; direction accepts int +1/-1/0 or 'LONG'/'SHORT'/'NEUTRAL'"
  - "feed_scorer_result is async; close_trade is sync + best-effort loop.create_task for persistence"
metrics:
  duration_min: 45
  tasks_completed: 3
  completed_date: "2026-04-13"
---

# Phase 12 Plan 04: Setup State Machine (1m + 5m) Summary

Added `SetupTracker`, a 5-state setup lifecycle machine (SCANNING → DEVELOPING →
TRIGGERED → MANAGING → COOLDOWN) running independently on 1-minute and 5-minute
timeframes simultaneously. Consumes `ScorerResult` + `SlingshotResult` via a
shape-based contract so the full scoring pipeline isn't required for unit
tests. Every state transition is persisted to a new `setup_transitions` table
in the phase 09-01 EventStore for post-session forensics and phase 12-05
consumption. The defining fix of this plan: **MANAGING → COOLDOWN is
explicit-close-only** — the reference implementation's auto-transition (cited
in research as the canonical footgun) is NOT ported. A 30-bar failsafe exists
only as a wedge-prevention emergency brake.

## What Shipped

### `deep6/orderflow/setup_tracker.py` (~500 LOC)

```python
STATES = ("SCANNING", "DEVELOPING", "TRIGGERED", "MANAGING", "COOLDOWN")

@dataclass
class ActiveSetup:
    setup_id: str           # "1m-<uuid12>" / "5m-<uuid12>"
    setup_type: str         # "SOAK" | "SLINGSHOT_BYPASS" | "TIER_CROSS" ...
    direction: str          # "LONG" | "SHORT"
    entry_score: float
    soak_bars: int
    bars_managing: int
    started_at_bar: int

@dataclass
class SetupTransition:
    timeframe: str
    setup_id: str
    from_state: str
    to_state: str
    trigger: str            # machine-readable reason code
    weight: float
    bar_index: int
    ts: float

class SetupTracker:
    def __init__(self, timeframe, cooldown_bars=5, managing_failsafe_bars=30): ...
    def update(self, scorer_result, slingshot_result, current_bar_index) -> Optional[SetupTransition]: ...
    def close_trade(self, setup_id, outcome="CLOSED") -> Optional[SetupTransition]: ...
    def current_weight(self) -> float: ...
```

Transition rules (LOCKED per 12-CONTEXT.md):

| From → To | Rule |
|---|---|
| SCANNING → DEVELOPING | tier ∈ {TYPE_B, TYPE_C}, direction aligned, score ≥ 35 |
| SCANNING/DEVELOPING → TRIGGERED (BYPASS) | `SlingshotResult.triggers_state_bypass AND direction in {LONG,SHORT}` |
| DEVELOPING → TRIGGERED | `soak_bars >= 10 AND tier == TYPE_A AND score >= 80` |
| DEVELOPING → SCANNING | score < 25 OR direction flip (then attempts re-entry same bar) |
| TRIGGERED → MANAGING | 1 bar grace for entry confirmation |
| **MANAGING → COOLDOWN** | **ONLY via `close_trade(setup_id, outcome)` — OR failsafe at `bars_managing > 30`** |
| COOLDOWN → SCANNING | `cooldown_bars` (default 5) elapsed |

Soak weight formula (`current_weight()`):

```python
SCANNING / COOLDOWN           → 0.0
DEVELOPING, soak_bars ∈ [0,10] → 1.0 + 0.4 * min(soak_bars, 10)
DEVELOPING, soak_bars > 10    → 5.0 (clamped)
TRIGGERED / MANAGING          → 5.0
```

### `deep6/api/store.py` — `setup_transitions` table

```sql
CREATE TABLE IF NOT EXISTS setup_transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timeframe   TEXT NOT NULL,
    setup_id    TEXT NOT NULL,
    from_state  TEXT NOT NULL,
    to_state    TEXT NOT NULL,
    trigger     TEXT NOT NULL,
    weight      REAL NOT NULL,
    bar_index   INTEGER NOT NULL,
    ts          REAL NOT NULL,
    inserted_at REAL NOT NULL
);
```

New methods on `EventStore`:

- `record_setup_transition(timeframe, setup_id, from_state, to_state, trigger, weight, bar_index, ts=None) -> int`
- `query_setup_transitions(session_start_ts, session_end_ts) -> list[dict]` — ordered by ts ASC for replay semantics

Existing `signal_events` / `trade_events` schemas and methods are untouched; a
regression test inside `TestEventStoreSetupTransitions` verifies they still
operate after the new table is created.

### `deep6/state/shared.py` — dual-TF wiring

Added fields:
- `setup_tracker_1m: SetupTracker` (factory — timeframe="1m")
- `setup_tracker_5m: SetupTracker` (factory — timeframe="5m")
- `event_store: object | None` (attach-point for the API lifespan)

Added methods:
- `feed_scorer_result(label, scorer_result, slingshot_result, current_bar_index) -> SetupTransition | None`
  — async entry point that calls `tracker.update()` and, if `event_store` is
  attached, awaits `record_setup_transition` with the emitted transition
- `close_trade(setup_id, outcome="CLOSED") -> SetupTransition | None` — routes
  by `1m-` / `5m-` prefix; schedules best-effort async persistence if an
  event loop is running, silent no-op otherwise
- `_tracker_for(label)` — internal dispatcher
- `_persist_transition(tr)` — try/except wrapper so a slow/broken DB cannot
  break the bar-close path (threat T-12-04-02)

The existing `on_bar_close` path is **unchanged** — VPIN + slingshot still
run there. `feed_scorer_result` is intentionally a separate call site so
offline replay harnesses, backtests, and unit tests can drive the state
machine without needing the full bar-close dispatch. Phase 12-05 (walk-forward
tracker) and the downstream scorer integration will call
`feed_scorer_result` from inside `on_bar_close` once the scorer emission
point lands in SharedState itself (currently invoked from downstream engines).

## Test Coverage

**`tests/orderflow/test_setup_tracker.py`** — 12 unit tests, all green:

| Test | Asserts |
|---|---|
| `test_scanning_to_developing` | TYPE_B long @ score 50 → DEVELOPING, soak=1 |
| `test_developing_soak_weight_ramps` | 10 consecutive aligned bars → weight rises 1.4 → 5.0, clamps |
| `test_developing_to_triggered_on_tier_cross` | soak=10 + TYPE_A score=85 → TRIGGERED |
| `test_slingshot_bypass` | `triggers_state_bypass=True` → immediate TRIGGERED |
| `test_developing_resets_on_direction_flip` | LONG 5 bars → SHORT → soak dropped |
| `test_triggered_to_managing` | 1 bar after TRIGGERED → MANAGING (same setup_id) |
| **`test_managing_no_auto_cooldown`** | **29 bars in MANAGING → still MANAGING** |
| **`test_managing_failsafe_at_31_bars`** | **31 bars → forced COOLDOWN + WARNING log** |
| **`test_explicit_close_transitions_to_cooldown`** | `close_trade()` → COOLDOWN, trigger="EXPLICIT_CLOSE" |
| `test_cooldown_returns_to_scanning` | 5 bars in COOLDOWN → SCANNING |
| `test_close_trade_with_wrong_id_is_noop` | mismatched setup_id → state unchanged, returns None |
| `test_setup_id_is_prefixed_by_timeframe` | IDs start with `1m-` / `5m-` |

**`tests/orderflow/test_setup_tracker_integration.py`** — 4 integration tests, all green:

| Test | Asserts |
|---|---|
| `test_dual_tf_independence_1m_triggered_5m_still_developing` | 10 soak bars both; TYPE_A on 1m only → 1m TRIGGERED → MANAGING while 5m stays DEVELOPING |
| `test_trap_shot_bypass_1m_only` | `SlingshotResult(triggers_state_bypass=True)` on 1m → 1m TRIGGERED; 5m unaffected |
| `test_explicit_close_routes_by_setup_id_prefix` | Close 1m setup_id → 1m COOLDOWN, 5m MANAGING |
| `test_shared_state_records_transitions_to_eventstore` | Transitions persist via record+query round-trip |

**`tests/test_ml_backend.py::TestEventStoreSetupTransitions`** — 2 new tests, all green:

| Test | Asserts |
|---|---|
| `test_setup_transitions_table_created` | Idempotent DDL; existing tables still usable |
| `test_record_and_query_round_trip` | 3 rows → wide window returns 3 ordered ASC; narrow window filters correctly |

**Full suite:** `613 passed in 3.20s`, 0 regressions.

## Bit Lock / Constraint Verification

- `grep -nE "MANAGING.*COOLDOWN" deep6/orderflow/setup_tracker.py` → only
  docstring/module-constant matches; no auto-transition code path
- No JSON-on-disk persistence introduced — reuses EventStore (phase 09-01)
- State machine does NOT couple to specific signal bits — consumes only
  `ScorerResult.tier` / `.direction` / `.total_score` and
  `SlingshotResult.fired` / `.triggers_state_bypass` / `.direction`
- `SetupTracker.update()` is O(1); no `asyncio.sleep` anywhere in module
- All transitions are single-row aiosqlite INSERTs (threat T-12-04-02 met)

## Commits

| Task | Hash | Message |
|---|---|---|
| T-01 (RED) | `5e74914` | `test(12-04): add failing SetupTracker state machine tests` |
| T-01 (GREEN) | `5dddbe4` | `feat(12-04): implement SetupTracker 5-state lifecycle` |
| T-02 | `eeb323c` | `feat(12-04): add setup_transitions table + record/query API` |
| T-03 | `4f3a088` | includes wire-up + integration tests (`deep6/state/shared.py` + `tests/orderflow/test_setup_tracker_integration.py`) |

## Deviations from Plan

### Auto-fixed Issues

**[Rule 2 — Correctness] Failsafe warning routed via stdlib `logging` as well as `structlog`**
- **Found during:** T-12-04-01 RED
- **Issue:** Plan called for a WARNING log; pytest's `caplog` captures stdlib
  `logging` records only, not structlog events.
- **Fix:** `_stdlog = logging.getLogger("deep6.orderflow.setup_tracker")` logs
  the failsafe warning in parallel with the structured event. Test
  `test_managing_failsafe_at_31_bars` uses `caplog` and passes.
- **Commit:** `5dddbe4`

**[Rule 2 — Correctness] `close_trade` trigger token kept stable across outcomes**
- **Found during:** T-12-04-01 GREEN (initial run had `trigger="EXPLICIT_CLOSE:TARGET_HIT"`)
- **Issue:** Mixing the outcome into the trigger token breaks downstream
  equality matching.
- **Fix:** `trigger="EXPLICIT_CLOSE"` always; `outcome` persisted through a
  separate structured log event (`setup_tracker.close_trade`).
- **Commit:** `5dddbe4`

**[Rule 3 — Blocking] SharedState had no EventStore handle**
- **Found during:** T-12-04-03 wiring
- **Issue:** Plan expected `store.record_setup_transition` to be awaited from
  SharedState, but SharedState had no reference to an EventStore (it lives in
  the FastAPI lifespan today).
- **Fix:** Added an optional `event_store: object | None` attach-point (typed
  as `object` to avoid a hard import dependency in the dataclass body). When
  None, transitions still fire through the trackers — they just don't persist.
  This keeps unit tests trivial and matches the VPIN / Slingshot pattern of
  "degrade to neutral if not wired".
- **Commit:** `4f3a088`

**[Rule 2 — Correctness] `close_trade` from synchronous call sites**
- **Found during:** T-12-04-03 wiring
- **Issue:** Execution-layer close events are fired from sync contexts
  (PaperTrader callback); awaiting persistence there would force `async def`
  in every path.
- **Fix:** `SharedState.close_trade` is `def`, not `async def`. When a running
  event loop is detected via `asyncio.get_running_loop()`, it schedules the
  persistence as a task; otherwise the state transition still happens and the
  persistence is silently skipped (acceptable for test/offline paths).
- **Commit:** `4f3a088`

**[Rule 2 — Defensive] `close_trade` with mismatched setup_id is no-op**
- **Found during:** T-12-04-01 test design
- **Issue:** The plan said "explicit call — no auto-transition" but didn't
  spell out behavior for a stale / cross-wired fill event.
- **Fix:** `close_trade` returns None and leaves state unchanged when the
  given setup_id doesn't match the active setup. Emits a structured
  `id_mismatch` warning for diagnostic trail. Test
  `test_close_trade_with_wrong_id_is_noop` verifies.
- **Commit:** `5dddbe4`

### Plan-to-reality mapping notes (not deviations)

- Plan's `<interfaces>` block described `ScorerResult.tier` as string and
  `.direction` as string, but the real `ScorerResult` (phase 04) uses
  `SignalTier` IntEnum and `direction: int` (+1/-1/0). The tracker's
  `_name_of` / `_direction_str` helpers accept both shapes transparently, so
  both real and fake objects are consumed cleanly.
- Plan `key_links` specified `from deep6/state/shared.py on_bar_close to
  setup_tracker.update`. In this plan we ship that wiring via
  `SharedState.feed_scorer_result` — a separate async entry point —
  rather than splicing into `on_bar_close` directly. The scorer isn't
  currently invoked from `on_bar_close` (as noted in the 12-01 SUMMARY
  "Plan-to-reality mapping note"), so the call-site for the state-machine
  update is properly located at the same scope as the scorer invocation,
  which is in the downstream signal engines / replay harness. Phase 12-05
  and the scorer-in-on_bar_close migration will be the natural place to
  relocate the call.

## Threat Flags

None. No new network endpoints, auth paths, file access, or trust-boundary
schema changes. All STRIDE entries in the plan's register are mitigated:

- **T-12-04-01 (wedge in MANAGING):** 30-bar failsafe with WARNING log; unit
  test `test_managing_failsafe_at_31_bars` verifies.
- **T-12-04-02 (EventStore blocks bar-close):** `_persist_transition` wraps
  the await in try/except; single-row INSERT is ~1-5ms; at most 1-2
  transitions/bar/tf.
- **T-12-04-03 (cross-TF setup_id routing):** `1m-` / `5m-` prefix enforced in
  `_new_setup_id`; unit test `test_setup_id_is_prefixed_by_timeframe` +
  integration test `test_explicit_close_routes_by_setup_id_prefix`.
- **T-12-04-04 (unlogged transitions):** All transitions route through
  `record_setup_transition`; the table is queryable by ts range via
  `query_setup_transitions`.

## Known Stubs

None that block the plan's goal. `SharedState.event_store` defaults to None
by design — this is the documented integration point that the FastAPI
lifespan (phase 09-01) or an offline harness attaches. With None, the state
machine is fully functional; only persistence is skipped. Test
`test_shared_state_records_transitions_to_eventstore` verifies persistence
works when the store is attached.

`feed_scorer_result` is currently an explicit call site (not yet invoked
from `on_bar_close`) because the scorer itself is invoked from downstream
signal engines, not from `on_bar_close`, in DEEP6 today. This mirrors the
12-01 SUMMARY's documented mapping. Phase 12-05 (walk-forward tracker) and
the scorer-in-on_bar_close migration are the natural future seams; this is
not a stub, it is the documented Phase-12 integration sequence.

## Verification

- `pytest tests/orderflow/ tests/test_ml_backend.py -x -q` → **84 passed**
- `pytest tests/ -q` → **613 passed, 0 regressions**
- `grep -nE "MANAGING.*COOLDOWN" deep6/orderflow/setup_tracker.py` → only
  docstring/constant mentions; no auto-transition code
- `grep -n "setup_transitions" deep6/api/store.py` → DDL + both async methods
- `grep -n "setup_tracker_1m\|setup_tracker_5m\|feed_scorer_result\|close_trade" deep6/state/shared.py`
  → fields + methods present

## Self-Check: PASSED

Files present:
- `deep6/orderflow/setup_tracker.py` — FOUND
- `deep6/orderflow/__init__.py` — FOUND (modified, exports updated)
- `deep6/state/shared.py` — FOUND (modified)
- `deep6/api/store.py` — FOUND (modified)
- `tests/orderflow/test_setup_tracker.py` — FOUND
- `tests/orderflow/test_setup_tracker_integration.py` — FOUND
- `tests/test_ml_backend.py` — FOUND (appended)

Commits present in git log:
- `5e74914` (RED) — FOUND
- `5dddbe4` (GREEN SetupTracker) — FOUND
- `eeb323c` (EventStore setup_transitions) — FOUND
- `4f3a088` (SharedState wiring + integration tests) — FOUND

Constraint verification:
- No auto `MANAGING → COOLDOWN` — confirmed by grep + unit test
- State machine consumes ScorerResult via shape (getattr), not bitmask — confirmed
- No JSON-on-disk persistence — reuses EventStore / aiosqlite
- Failsafe at 31 bars logs WARNING — confirmed by `test_managing_failsafe_at_31_bars`
- Dual-TF independence — confirmed by
  `test_dual_tf_independence_1m_triggered_5m_still_developing`
