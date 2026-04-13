---
phase: 09-ml-backend
plan: "01"
subsystem: api
tags: [fastapi, aiosqlite, sqlite, event-store, pydantic-v2, ml-backend]
dependency_graph:
  requires: []
  provides: [deep6.api.app, deep6.api.store.EventStore, deep6.api.schemas, deep6.api.routes.events, deep6.api.routes.weights]
  affects: [deep6.scoring.scorer, deep6.execution.paper_trader]
tech_stack:
  added: [fastapi==0.135.3, uvicorn==0.44.0]
  patterns: [lifespan-context-manager, per-operation-aiosqlite, pydantic-v2-models, fastapi-app-state]
key_files:
  created:
    - deep6/api/app.py
    - deep6/api/schemas.py
    - deep6/api/store.py
    - deep6/api/routes/events.py
    - deep6/api/routes/weights.py
    - deep6/api/routes/__init__.py
  modified:
    - deep6/api/__init__.py
decisions:
  - "Used _BorrowedConnection wrapper to support :memory: DBs in tests while keeping per-operation pattern for file DBs"
  - "POST /weights/deploy already enforces DEPLOY_SECRET env var auth gate (T-09-04) even as a 501 stub"
metrics:
  duration_minutes: 25
  completed_date: "2026-04-13"
  tasks_completed: 2
  tasks_total: 2
  files_created: 7
  files_modified: 0
---

# Phase 9 Plan 01: FastAPI Foundation + EventStore Summary

**One-liner:** FastAPI app factory with aiosqlite EventStore — signal_events + trade_events ingestion pipeline for ML backend.

## What Was Built

### Files Created

| File | Key Exports | Purpose |
|------|-------------|---------|
| `deep6/api/app.py` | `create_app`, `app` | FastAPI factory with lifespan; mounts routers; GET /health |
| `deep6/api/schemas.py` | `SignalEventIn`, `TradeEventIn`, `WeightFileOut` | Pydantic v2 models matching ScorerResult and PositionEvent shapes |
| `deep6/api/store.py` | `EventStore` | aiosqlite CRUD for signal_events and trade_events |
| `deep6/api/routes/events.py` | `router` | POST /events/signal + POST /events/trade |
| `deep6/api/routes/weights.py` | `router` | GET /weights/current + POST /weights/deploy (stub) |
| `deep6/api/__init__.py` | `app`, `create_app` | Package exports |

### Database Schema

**signal_events table:**
```sql
CREATE TABLE IF NOT EXISTS signal_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               REAL NOT NULL,           -- bar close epoch timestamp
    bar_index        INTEGER NOT NULL,         -- 0 = 9:30 RTH open
    total_score      REAL NOT NULL,            -- 0-100
    tier             TEXT NOT NULL,            -- TYPE_A/B/C/QUIET
    direction        INTEGER NOT NULL,         -- +1 bull, -1 bear, 0 neutral
    engine_agreement REAL NOT NULL,            -- 0-1
    category_count   INTEGER NOT NULL,
    categories       TEXT NOT NULL,            -- JSON array string
    gex_regime       TEXT NOT NULL DEFAULT 'NEUTRAL',
    kronos_bias      REAL NOT NULL DEFAULT 0.0,
    inserted_at      REAL NOT NULL
)
```

**trade_events table:**
```sql
CREATE TABLE IF NOT EXISTS trade_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    position_id  TEXT NOT NULL,
    event_type   TEXT NOT NULL,      -- STOP_HIT, TARGET_HIT, TIMEOUT_EXIT, MANUAL_EXIT
    side         TEXT NOT NULL,      -- LONG or SHORT
    entry_price  REAL NOT NULL,
    exit_price   REAL NOT NULL,
    pnl          REAL NOT NULL,
    bars_held    INTEGER NOT NULL,
    signal_tier  TEXT NOT NULL,
    signal_score REAL NOT NULL DEFAULT 0.0,
    inserted_at  REAL NOT NULL
)
```

### API Endpoints

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | /health | 200 | Liveness probe — returns `{status, ts}` |
| POST | /events/signal | 200 | Persist ScorerResult-shaped event |
| POST | /events/trade | 200 | Persist PositionEvent-shaped trade |
| GET | /weights/current | 200 | Returns deployed weights or defaults (all 1.0) |
| POST | /weights/deploy | 501 | Stub — full implementation in Plan 03 |

### How to Start the API

```bash
# Standalone
uvicorn deep6.api.app:app --port 8000

# Same-loop integration (from trading engine)
import asyncio, uvicorn
from deep6.api.app import app
asyncio.create_task(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000)).serve())
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_PATH` | `./deep6_ml.db` | SQLite database path |
| `WEIGHTS_PATH` | `./deep6_weights.json` | Weight file location |
| `DEPLOY_SECRET` | (unset) | If set, POST /weights/deploy requires matching `X-Deploy-Secret` header |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `63b4bb7` | FastAPI app factory + Pydantic schemas |
| Task 2 | `3460247` | EventStore + event ingestion routes |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed :memory: SQLite incompatibility with per-operation connections**
- **Found during:** Task 2 verification
- **Issue:** Per-operation `aiosqlite.connect(":memory:")` opens a fresh empty DB each time — tables created in `initialize()` were invisible to subsequent operations. SQLite shared-cache URI mode doesn't work across aiosqlite threads.
- **Fix:** Added `_BorrowedConnection` wrapper class. `EventStore` detects `":memory:"` at init, opens one persistent `aiosqlite.Connection` in `initialize()`, and routes all subsequent ops through it via `_BorrowedConnection` (a no-op `__aexit__` that skips `close()`). File-path DBs continue using the per-operation pattern unchanged.
- **Files modified:** `deep6/api/store.py`
- **Commit:** `3460247`

**2. [Rule 2 - Security] Added DEPLOY_SECRET auth gate to POST /weights/deploy stub**
- **Found during:** Task 2 implementation — T-09-04 in threat model
- **Issue:** T-09-04 requires that if `DEPLOY_SECRET` env var is set, POST /weights/deploy returns 401 without the matching header. The plan's stub description didn't include this but the threat register marks it `mitigate`.
- **Fix:** Added `X-Deploy-Secret` header check to the 501 stub so the security surface is correct before Plan 03 implementation.
- **Files modified:** `deep6/api/routes/weights.py`
- **Commit:** `3460247`

**3. [Rule 3 - Blocking] Installed fastapi + uvicorn (not in environment)**
- **Found during:** Task 1 pre-flight
- **Issue:** `fastapi` and `uvicorn` were not installed in the venv.
- **Fix:** `pip install "fastapi>=0.115.0" "uvicorn>=0.34.0"` — fastapi 0.135.3 + uvicorn 0.44.0 installed.
- **Commit:** No separate commit — prerequisite for Task 1.

**4. [Rule 3 - Blocking] Reinstalled editable package from worktree**
- **Found during:** Task 1 verification
- **Issue:** The editable install's MAPPING pointed to `/Users/teaceo/DEEP6/deep6` (main repo) while files were created in the worktree at `/Users/teaceo/DEEP6/.claude/worktrees/agent-a6fc66d7/deep6`. Imports failed from `cd /Users/teaceo/DEEP6` because CWD shadowed the editable install.
- **Fix:** Ran `pip install -e .` from the worktree directory, updating the finder MAPPING to point to the worktree. All subsequent Python invocations run from the worktree directory.
- **Commit:** No separate commit — environment fix.

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| POST /weights/deploy → 501 | `deep6/api/routes/weights.py` | Intentional — Plan 03 implements WFE gate + atomic weight swap (D-19, D-20) |

## Threat Flags

None — all new surface is internal HTTP endpoints (not externally exposed). T-09-01 (confirmation token) is deferred to Plan 03 as designed. T-09-04 (DEPLOY_SECRET) is pre-wired in the stub.

## Self-Check: PASSED

Files verified:
- `deep6/api/app.py` — FOUND
- `deep6/api/schemas.py` — FOUND
- `deep6/api/store.py` — FOUND
- `deep6/api/routes/events.py` — FOUND
- `deep6/api/routes/weights.py` — FOUND

Commits verified:
- `63b4bb7` — FOUND (feat(09-01): FastAPI app factory + Pydantic schemas)
- `3460247` — FOUND (feat(09-01): EventStore + event ingestion routes)
