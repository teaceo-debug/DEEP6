---
phase: 01-data-pipeline-architecture-foundation
plan: 03
subsystem: state-management
tags: [sqlite, aiosqlite, session-persistence, freeze-guard, gc-control, shared-state]

dependency_graph:
  requires:
    - "01-01: Config, DOMState, aggressor gate"
    - "01-02: FootprintBar, BarBuilder, SessionContext, ATRTracker"
  provides:
    - "SessionPersistence: async SQLite key-value store for session state"
    - "FreezeGuard: CONNECTED/FROZEN/RECONNECTING state machine"
    - "SessionManager: GC control at RTH boundaries"
    - "SharedState: unified container for all callback-accessible state"
  affects:
    - "01-04: __main__.py uses SharedState.build() as assembly point"
    - "All future plans: callbacks receive SharedState as their only context"

tech_stack:
  added:
    - aiosqlite==0.22.1 (async SQLite driver — already installed)
    - zoneinfo (stdlib — Python 3.12 DST-correct timezone handling)
  patterns:
    - "INSERT OR REPLACE upsert for idempotent session state writes"
    - "asyncio event loop single-threaded — no locks needed on SharedState"
    - "gc.disable()/gc.enable() at RTH session boundaries (not global)"

key_files:
  created:
    - deep6/state/persistence.py
    - deep6/state/connection.py
    - deep6/state/shared.py
    - tests/test_session.py
  modified: []

decisions:
  - "aiosqlite opens a new connection per operation (not a connection pool) — safe for single event loop; no concurrent writes"
  - "FreezeGuard._state is private string; only on_disconnect/on_reconnect mutate it (T-03-01)"
  - "SessionManager uses 1-second poll to detect RTH boundaries — negligible CPU vs 1,000/sec DOM callbacks"
  - "SharedState.persistence field initialized to None in dataclass default, set in build() classmethod — avoids module-level SQLite connection"
  - "on_bar_close is a method on SharedState (not a standalone callback) to avoid circular import between shared.py and signal engine modules"

metrics:
  duration: "~25 minutes"
  completed_date: "2026-04-13"
  tasks_completed: 2
  files_created: 4
  tests_added: 6
---

# Phase 1 Plan 03: Session Persistence, FreezeGuard, and SharedState Summary

**One-liner:** aiosqlite SQLite key-value session persistence + CONNECTED/FROZEN/RECONNECTING state machine + GC-controlled RTH session lifecycle wired into unified SharedState container.

## What Was Built

### Task 1: SessionPersistence (TDD GREEN)

`deep6/state/persistence.py` implements async SQLite key-value storage for session state.

Key implementation details:
- Schema: `session_state(session_id TEXT, key TEXT, value TEXT, updated_at REAL)` with `PRIMARY KEY (session_id, key)`
- `write()` uses `INSERT OR REPLACE` — upsert semantics, last write wins
- `write_many()` uses `executemany` in a single transaction — efficient for writing full SessionContext at session close
- `read_all(session_id)` returns `{}` for unknown session_id — never raises, callers use `SessionContext.from_dict` with safe defaults
- In-memory SQLite (`":memory:"`) confirmed working with aiosqlite for test isolation
- `persist_session_context()` and `restore_session_context()` convenience wrappers for SessionManager use

All 6 tests pass:
- Empty read returns `{}`
- Write + read round-trips correctly
- Multiple writes to same key keeps latest (INSERT OR REPLACE)
- Multiple keys per session stored independently
- Session isolation — different session_ids don't interfere
- Full `SessionContext.to_dict() -> SQLite -> from_dict()` round-trip

### Task 2: FreezeGuard, SessionManager, and SharedState

`deep6/state/connection.py` implements the FROZEN state machine and GC-controlled session lifecycle.

**FreezeGuard state transitions:**
```
CONNECTED → FROZEN (on_disconnect)
FROZEN → RECONNECTING (on_reconnect start)
RECONNECTING → CONNECTED (on_reconnect end)
```
- `is_frozen` returns True in both FROZEN and RECONNECTING states — no partial processing
- `on_disconnect()` is synchronous — can be called from non-async `_on_disconnected` handler
- `on_reconnect()` is async — contains `await asyncio.sleep(0.5)` (Issue #49 workaround)
- All transitions logged with structlog timestamps for audit trail (D-19)

**SessionManager GC control:**
- `gc.collect()` then `gc.disable()` at RTH open (9:30 ET) — clean sweep before disabling
- `gc.enable()` then `gc.collect()` at RTH close (16:00 ET) — GC stays disabled only during 6.5hr RTH window
- Mid-session restart handled: `restore_session_context()` called at session open; if SQLite has prior state for today's session_id, CVD/VWAP/IB are restored before bar processing resumes (D-07)

`deep6/state/shared.py` implements SharedState:
- `SharedState.build(config)` is the single entry point — creates `SessionPersistence(config.db_path)` and returns assembled state
- `atr_trackers` dict pre-populated with `ATRTracker(period=20)` for "1m" and "5m"
- `bar_builders` list starts empty — populated by `__main__.py` after BarBuilder construction
- `on_bar_close(label, bar)` is async method — Phase 1 logs only; `_on_bar_close_fn` hook for Phase 2+
- `session_manager()` returns a bound `SessionManager` for use in `asyncio.gather()`

## No Circular Import Issues

The potential circular import between `shared.py` → `connection.py` → (forward ref to SharedState) was handled by:
1. Using `from __future__ import annotations` in connection.py
2. String forward references in type hints: `"SharedState"` in SessionManager.__init__
3. Late imports inside methods where needed (e.g., `restore_session_context` imports `SessionContext` inline to break `session.py` → `persistence.py` circular dependency)

## Integration Points Verified

`dom_feed.py` and `tick_feed.py` (Plan 01) already check `state.freeze_guard.is_frozen` — no modifications needed. `rithmic.py` (Plan 01) already calls `state.freeze_guard.on_disconnect(ts)` in `_on_disconnected()`. All integration points from Plan 01 are compatible with Plan 03's implementation.

## Deviations from Plan

### Auto-fixed Issues

**[Rule 3 - Blocking Issue] Plan 01-02 Task 2 files missing — created as prerequisite**

- **Found during:** Pre-execution check before Task 1
- **Issue:** Plan 01-03 depends on `session.py`, `bar_builder.py`, `atr.py` from Plan 01-02 Task 2, but these files were not committed (only `footprint.py` from Task 1 was committed in `f863ba0`)
- **Fix:** Created all three missing Plan 01-02 Task 2 files (`session.py`, `atr.py`, `bar_builder.py`, `test_bar_builder.py`) with all 20 tests passing before beginning Plan 01-03 tasks
- **Commit:** `f95093a feat(01-02): implement dual-TF BarBuilder, SessionContext, and ATRTracker`

## Known Stubs

None — all Plan 03 functionality is fully wired:
- `SessionPersistence.write/read_all` — fully functional aiosqlite SQLite operations
- `FreezeGuard.on_reconnect()` — async reconnect with 500ms delay; position reconciliation marked as `TODO Phase 8` (intentional, documented in threat model as acceptable for Phase 1)
- `SharedState.on_bar_close()` — Phase 1 logs bar close; `_on_bar_close_fn` hook is `None` by default (intentional stub, Plan 01-04/Phase 2 attaches signal engines)

The `on_bar_close` stub does not prevent Plan 03's goal — SharedState is complete and all Plan 03 requirements (DATA-07, DATA-08, DATA-09, ARCH-02) are satisfied.

## Threat Flags

No new security-relevant surface beyond what the plan's threat model documented.
- SQLite file at `config.db_path` — local file, no network exposure (T-03-03: accepted)
- `gc.disable()` during RTH — SessionManager always re-enables at close; no permanent GC disable risk (T-03-02: accepted)

## Self-Check: PASSED

All files confirmed present on disk:
- deep6/state/persistence.py: FOUND
- deep6/state/connection.py: FOUND
- deep6/state/shared.py: FOUND
- tests/test_session.py: FOUND

All commits confirmed in git log:
- deb0321 (Task 1: SessionPersistence): FOUND
- 7a21c7f (Task 2: FreezeGuard + SharedState): FOUND
