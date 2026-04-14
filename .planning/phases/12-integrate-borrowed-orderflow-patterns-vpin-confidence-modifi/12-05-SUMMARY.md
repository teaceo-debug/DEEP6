---
phase: 12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi
plan: 05
subsystem: orderflow-walk-forward
tags: [walk-forward, per-regime, per-category, auto-disable, recovery, event-store, feedback-loop]
requirements: [OFP-06]
dependency-graph:
  requires:
    - "EventStore (deep6/api/store.py — phase 09-01)"
    - "WeightFile + regime_adjustments slot (phase 09-02 lgbm_trainer.py)"
    - "HMMRegimeDetector regime labels (phase 09-02)"
    - "SetupTracker + feed_scorer_result (phase 12-04)"
    - "SharedState on_bar_close dispatch (phase 01)"
  provides:
    - "deep6.orderflow.walk_forward_live.WalkForwardTracker — per-category x per-regime"
    - "deep6.orderflow.walk_forward_live.PendingOutcome / ResolvedOutcome dataclasses"
    - "EventStore.record_walk_forward_outcome / query_walk_forward_outcomes"
    - "EventStore walk_forward_outcomes SQLite table"
    - "SharedState.walk_forward — optional attached tracker"
    - "SharedState.attach_event_store — wires EventStore + instantiates tracker"
    - "SharedState.bars_until_rth_close_provider / current_regime_provider hooks"
    - "deep6.ml.weight_loader.apply_walk_forward_overrides feedback merge"
  affects:
    - "deep6/state/shared.py (on_bar_close now drives walk-forward price updates on 1m)"
    - "deep6/state/shared.py (feed_scorer_result now records per-voting-category outcomes)"
    - "deep6/orderflow/__init__.py (exports WalkForwardTracker, dataclasses)"
tech-stack:
  added: []
  patterns:
    - "bounded-deque pending outcomes (maxlen=1000, oldest-drop)"
    - "per-cell rolling pnl cache for O(1) Sharpe recomputation"
    - "immutable WeightFile snapshot via apply_walk_forward_overrides (no mid-bar flip)"
    - "shape-based ScorerResult consumption (tier enum OR str; direction int OR str)"
    - "provider-hook indirection for bars_until_rth_close and current_regime"
key-files:
  created:
    - "deep6/orderflow/walk_forward_live.py"
    - "tests/orderflow/test_walk_forward_live.py"
    - "tests/integration/__init__.py"
    - "tests/integration/test_phase12_end_to_end.py"
  modified:
    - "deep6/api/store.py"
    - "deep6/orderflow/__init__.py"
    - "deep6/state/shared.py"
    - "deep6/ml/weight_loader.py"
decisions:
  - "Outcome labels: CORRECT / INCORRECT / NEUTRAL / EXPIRED; EXPIRED excluded from Sharpe (FOOTGUN 1)"
  - "Per-category granularity (8 groups); per-signal (44 bits) deferred per CONTEXT decision"
  - "Sharpe window 200 non-EXPIRED samples; disable threshold 0.0; recovery threshold 0.3 over 50 samples"
  - "Cross-session pending carry-over resolves as EXPIRED (defensive: avoids overnight-gap PnL)"
  - "Persistence LOCKED to EventStore walk_forward_outcomes — zero JSON-on-disk sink (FOOTGUN 2)"
  - "apply_walk_forward_overrides returns NEW WeightFile — immutable snapshot for bar-close scoring (FOOTGUN 3)"
  - "Multiplicative composition of tracker overrides with any pre-existing regime_adjustments"
  - "Under-sampled cells (< sharpe_window resolutions) return None; never auto-disabled (FOOTGUN 5)"
  - "Attribution at entry regime — HMM state at entry, not at resolution (FOOTGUN 6)"
  - "Bounded pending deque capped at max_pending=1000; oldest-drop silently (T-12-05-01 mitigation)"
  - "feed_scorer_result now records per-voting-category walk-forward signals (1m only, matching VPIN timeframe lock)"
metrics:
  duration_min: 35
  tasks_completed: 3
  completed_date: "2026-04-13"
---

# Phase 12 Plan 05: Per-Regime Walk-Forward Tracker Summary

Added `WalkForwardTracker` — a closed-loop per-category × per-regime
outcome-resolution and auto-disable controller. Every voting category on a
scored bar is recorded against the live price stream; outcomes resolve at the
5/10/20-bar horizons with labels `CORRECT` / `INCORRECT` / `NEUTRAL` /
`EXPIRED`. EXPIRED flags signals whose horizon would span RTH close — they
persist for forensics but are excluded from rolling Sharpe statistics (the
key session-boundary mis-attribution footgun). Per-cell rolling Sharpe over a
200-signal window drives auto-disable (`Sharpe < 0.0`) and auto-recovery
(`Sharpe > 0.3` over the next 50 non-EXPIRED resolutions). Disabled cells
feed back into the LightGBM meta-learner via `WeightFile.regime_adjustments`
through `weight_loader.apply_walk_forward_overrides` — which returns a NEW
`WeightFile` to prevent mid-bar weight flips. Persistence is LOCKED to the
phase 09-01 `EventStore` via a new `walk_forward_outcomes` table; no JSON
on-disk sink exists in the module.

This is the final plan of phase 12 and closes the feedback loop between
scorer → setup tracker → walk-forward evaluator → fusion weights.

## What Shipped

### `deep6/orderflow/walk_forward_live.py` (~350 LOC)

```python
@dataclass
class PendingOutcome:
    category: str
    regime: str
    direction: str
    entry_price: float
    entry_bar_index: int
    session_id: str
    signal_event_id: Optional[int]
    horizon: int
    will_expire: bool = False

@dataclass
class ResolvedOutcome:
    category: str
    regime: str
    direction: str
    entry_price: float
    entry_bar_index: int
    session_id: str
    horizon: int
    outcome_label: str       # CORRECT / INCORRECT / NEUTRAL / EXPIRED
    pnl_ticks: float
    resolved_at_bar_index: int
    resolved_at_ts: float
    signal_event_id: Optional[int] = None

class WalkForwardTracker:
    def __init__(
        self,
        store,
        horizons=(5, 10, 20),
        sharpe_window=200,
        disable_sharpe_threshold=0.0,
        recovery_sharpe_threshold=0.3,
        recovery_window=50,
        neutral_threshold_ticks=0.5,
        max_pending=1000,
        session_close_buffer_bars=20,
    ): ...
    async def record_signal(...): ...
    async def update_price(...) -> list[ResolvedOutcome]: ...
    def get_weights_override(self) -> dict[str, dict[str, float]]: ...
    def is_disabled(self, category: str, regime: str) -> bool: ...
```

Resolution rules (LOCKED):

| Condition | Label |
|---|---|
| `bars_until_rth_close < horizon` at record time | `EXPIRED` |
| cross-session carry-over (session_id mismatch at horizon) | `EXPIRED` |
| `|pnl_ticks| < neutral_threshold_ticks` (default 0.5) | `NEUTRAL` |
| `pnl_ticks > 0` | `CORRECT` |
| `pnl_ticks < 0` | `INCORRECT` |

Sharpe formula: `mean(pnl) / (std(pnl) + 1e-9)` over a rolling deque of the
last `sharpe_window` non-EXPIRED resolutions per `(regime, category)` cell.

### `deep6/api/store.py` — `walk_forward_outcomes` table

```sql
CREATE TABLE IF NOT EXISTS walk_forward_outcomes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_event_id INTEGER,
    category        TEXT NOT NULL,
    regime          TEXT NOT NULL,
    direction       TEXT NOT NULL,
    entry_price     REAL NOT NULL,
    entry_bar_index INTEGER NOT NULL,
    session_id      TEXT NOT NULL,
    horizon         INTEGER NOT NULL,
    outcome_label   TEXT NOT NULL,
    pnl_ticks       REAL NOT NULL,
    resolved_at_ts  REAL NOT NULL,
    inserted_at     REAL NOT NULL
)
```

New async methods:
- `record_walk_forward_outcome(...)` — append one row, returns autoincrement id
- `query_walk_forward_outcomes(category=None, regime=None, limit=500)` — newest-first

Existing `signal_events` / `trade_events` / `setup_transitions` schemas and
methods are untouched.

### `deep6/ml/weight_loader.py`

```python
def apply_walk_forward_overrides(weight_file: WeightFile, tracker) -> WeightFile:
    """Returns a NEW WeightFile (immutable snapshot) with the tracker's
    disable mask merged multiplicatively into regime_adjustments."""
```

Never mutates the input. Returns the input unchanged if `tracker is None` or
the override map is empty (no-ops are identity to make snapshot-per-bar cheap).

### `deep6/state/shared.py` — wire-up

- `walk_forward: WalkForwardTracker | None` — lazy, populated via `attach_event_store`
- `attach_event_store(store)` — attaches EventStore + instantiates tracker
- `bars_until_rth_close_provider` / `current_regime_provider` — nullable callables
- `on_bar_close` on `label == "1m"` now awaits `walk_forward.update_price(...)`
  inside a try/except (never breaks the bar-close path)
- `feed_scorer_result` on `label == "1m"` now also drives per-voting-category
  `walk_forward.record_signal` when tier != QUIET/NONE and categories_firing
  is non-empty; direction string decoded from either `int` (+1/-1/0) or `str`

## Test Coverage

**`tests/orderflow/test_walk_forward_live.py`** — 10 unit tests, all green:

| Test | Asserts |
|---|---|
| `test_import_surface` | `WalkForwardTracker`, `PendingOutcome`, `ResolvedOutcome` exported |
| `test_record_signal_appended_to_pending` | 3 pending entries per record_signal (one per horizon) |
| `test_5bar_resolution_correct` | LONG + 5 upticks → horizon=5 CORRECT, pnl > 0 |
| `test_5bar_resolution_incorrect` | LONG + 5 downticks → INCORRECT |
| `test_neutral_resolution` | unchanged price → NEUTRAL |
| **`test_expired_at_session_boundary`** | **LONG w/ bars_until_close=15 → horizon=20 EXPIRED** |
| `test_rolling_sharpe_per_category_regime` | 200 samples → real Sharpe; under-sampled → None |
| `test_auto_disable_below_threshold` | bad-Sharpe cell → `get_weights_override` returns 0.0 |
| `test_auto_recovery_above_threshold` | disabled cell + 25 winning outcomes → re-enabled |
| `test_bounded_pending` | `max_pending=10` caps growth (T-12-05-01 mitigation) |

**`tests/integration/test_phase12_end_to_end.py`** — 5 integration tests, all green:

| Test | Asserts |
|---|---|
| `test_walk_forward_records_outcomes_end_to_end` | SharedState + scorer feed → rows in walk_forward_outcomes |
| `test_expired_at_session_boundary_end_to_end` | bars_until_close=7 → horizon 10/20 EXPIRED, horizon 5 CORRECT |
| `test_auto_disable_and_recovery_end_to_end` | losing → disabled → override[regime][cat]=0.0 → winning → recovered |
| `test_setup_transitions_recorded_on_end_to_end` | feed_scorer_result still writes setup_transitions alongside walk-forward |
| `test_apply_walk_forward_overrides_none_tracker_is_noop` | defensive identity on None tracker |

**Full suite:** `628 passed in 3.41s`, 0 regressions.

## Verification

- `pytest tests/orderflow/ tests/integration/ tests/test_ml_backend.py tests/test_scorer.py -q` → 108 passed
- `pytest tests/ -q` → 628 passed, 0 regressions
- `grep -n "json\|open(" deep6/orderflow/walk_forward_live.py` → **empty** (no JSON sink, FOOTGUN 2 mitigated)
- `grep -n "walk_forward_outcomes" deep6/api/store.py` → schema + both async methods present
- `grep -n "apply_walk_forward_overrides" deep6/ml/weight_loader.py` → function present
- Manual: `EXPIRED` labels returned for signals within the horizon of session close (test verified)
- Manual: disable/recovery lifecycle verified via `is_disabled()` round-trip in integration test

## Commits

| Task | Hash | Message |
|---|---|---|
| T-12-05-01 (RED + EventStore) | `1181c18` | `test(12-05): add walk_forward_outcomes table + failing WalkForwardTracker tests` |
| T-12-05-02 (GREEN tracker) | `b635ed7` | `feat(12-05): implement WalkForwardTracker with auto-disable/recovery` |
| T-12-05-03 (INTEGRATE) | `08113ad` | `feat(12-05): wire WalkForwardTracker into SharedState + weight_loader feedback` |

## Deviations from Plan

### Auto-fixed Issues

**[Rule 2 — Correctness] Cross-session carry-over treated as EXPIRED**
- **Found during:** T-12-05-02 implementation
- **Issue:** Plan only explicitly called out `bars_until_rth_close < horizon` at
  record time as EXPIRED, but a pending entry could survive across a session
  boundary if `update_price` is driven with a new `session_id` before the
  horizon resolves. Resolving that against the new session's opening price
  re-creates the overnight-gap mis-attribution FOOTGUN 1 tries to prevent.
- **Fix:** When a pending's `session_id` no longer matches `update_price`'s
  `session_id`, it is resolved as EXPIRED with `pnl=0`. Same spirit as
  CONTEXT.md FOOTGUN 1.
- **Files modified:** `deep6/orderflow/walk_forward_live.py`
- **Commit:** `b635ed7`

**[Rule 2 — Correctness] `apply_walk_forward_overrides` returns NEW WeightFile**
- **Found during:** T-12-05-03 weight_loader design
- **Issue:** Plan's mutation-by-default would let a mid-bar tracker state
  change (disable/recover) visibly affect the WeightFile a second scorer
  invocation in the same bar reads — FOOTGUN 3 (mid-bar weight flip).
- **Fix:** Function constructs and returns a fresh WeightFile instance so
  callers can take an immutable snapshot at bar-close. Original WeightFile
  is never mutated.
- **Files modified:** `deep6/ml/weight_loader.py`
- **Commit:** `08113ad`

**[Rule 3 — Blocking] SharedState lacked an attach point for EventStore + tracker**
- **Found during:** T-12-05-03 wiring
- **Issue:** Plan called for `SharedState.build()` to instantiate the tracker,
  but `build()` does not have access to the EventStore (it lives in the
  FastAPI lifespan; phase 12-04 used a field attach-point for the same
  reason). Instantiating in `build()` would break the test harness.
- **Fix:** Added `attach_event_store(store)` method that sets both the
  event_store field and lazily constructs the WalkForwardTracker. Matches
  the phase 12-04 attach-point idiom and keeps unit tests trivial.
- **Files modified:** `deep6/state/shared.py`
- **Commit:** `08113ad`

**[Rule 2 — Safety] All walk-forward wiring in SharedState wrapped in try/except**
- **Found during:** T-12-05-03 implementation
- **Issue:** Plan didn't mandate this, but VPIN (12-01), Slingshot (12-03),
  and SetupTracker (12-04) wiring all established the pattern — the bar-close
  path must never be broken by a downstream consumer. Rule 2 applies.
- **Fix:** Both `on_bar_close`'s `update_price` call and `feed_scorer_result`'s
  `record_signal` loop are wrapped; failures log and continue.
- **Files modified:** `deep6/state/shared.py`
- **Commit:** `08113ad`

### Plan-to-reality mapping notes (not deviations)

- Plan said "SharedState.build() instantiates WalkForwardTracker(store=self._event_store, ...)".
  In DEEP6 today, `build()` takes only `Config` (no store). We added
  `attach_event_store(store)` as the deterministic entry point — matches the
  phase 12-04 event_store attach pattern. `build()` still leaves `walk_forward=None`
  for unit tests.
- Plan said "In on_bar_close 1m: after scorer_result emitted, if tier != NONE ... for each voting category await tracker.record_signal". In DEEP6 the scorer is not invoked from on_bar_close (see phase 12-01 / 12-04 mapping notes). Therefore the per-category `record_signal` loop lives inside `feed_scorer_result` — the same entry point the setup tracker uses — which is called by downstream signal engines. `on_bar_close` still advances the price stream via `update_price`, which is where horizon resolution happens.

## Threat Flags

None. No new network endpoints, auth paths, file access, or trust-boundary
schema changes. STRIDE register mitigations:

- **T-12-05-01 (pending unbounded growth):** `deque(maxlen=max_pending)` + test `test_bounded_pending`
- **T-12-05-02 (external state file corruption):** No external file load path — tracker state is rebuilt from in-memory caches and EventStore only
- **T-12-05-03 (mid-bar weight flip):** `apply_walk_forward_overrides` returns a NEW WeightFile — immutable bar-close snapshot (commit `08113ad`)
- **T-12-05-04 (outcome lost on crash before DB write):** Each `record_walk_forward_outcome` awaits the INSERT; aiosqlite WAL from phase 01
- **T-12-05-05 (Sharpe leaked in logs):** accepted — non-sensitive internal metric

## Known Stubs

None. All surfaces are functional:
- Outcomes persist to real EventStore table (integration test verified)
- Override map populates `regime_adjustments` multiplicatively (integration test verified)
- `bars_until_rth_close_provider` / `current_regime_provider` default to `None`;
  these are the documented integration points for `__main__.py` to wire up
  from `SessionManager` and `HMMRegimeDetector`. A `None` provider is not a
  stub — it produces correct-but-conservative behavior (never expires, UNKNOWN regime).

## Self-Check: PASSED

Files present:
- `deep6/orderflow/walk_forward_live.py` — FOUND
- `deep6/orderflow/__init__.py` — FOUND (modified)
- `deep6/api/store.py` — FOUND (modified, `walk_forward_outcomes` DDL + methods)
- `deep6/state/shared.py` — FOUND (modified, tracker wired)
- `deep6/ml/weight_loader.py` — FOUND (modified, `apply_walk_forward_overrides`)
- `tests/orderflow/test_walk_forward_live.py` — FOUND (10 passing tests)
- `tests/integration/__init__.py` — FOUND
- `tests/integration/test_phase12_end_to_end.py` — FOUND (5 passing tests)

Commits present in git log:
- `1181c18` — FOUND
- `b635ed7` — FOUND
- `08113ad` — FOUND

Test suite:
- `pytest tests/orderflow/test_walk_forward_live.py -q` → 10 passed ✓
- `pytest tests/integration/ -q` → 5 passed ✓
- `pytest tests/ -q` → 628 passed ✓, 0 regressions

Constraint verification:
- No JSON-on-disk sink: `grep -n "json\|open(" deep6/orderflow/walk_forward_live.py` → empty ✓
- Per-category (not per-signal): categories are the 8 WeightFile groups (absorption/exhaustion/trapped/delta/imbalance/volume_profile/auction/poc) ✓
- EXPIRED at session boundary: `test_expired_at_session_boundary` + integration test ✓
- Auto-disable + recovery: unit test `test_auto_disable_below_threshold` + `test_auto_recovery_above_threshold` + integration test ✓
- WeightFile.regime_adjustments feedback: `apply_walk_forward_overrides` returns merged WeightFile ✓
