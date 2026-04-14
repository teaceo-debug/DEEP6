---
phase: 10-analytics-dashboard
plan: "01"
subsystem: api
tags: [websocket, backtest, real-time, fastapi]
dependency_graph:
  requires: []
  provides: [ws-endpoint, backtest-job-api, ws-broadcast]
  affects: [deep6/api/routes/events.py, deep6/api/app.py]
tech_stack:
  added: []
  patterns: [ConnectionManager-singleton, async-job-store, executor-offload, broadcast-hook]
key_files:
  created:
    - deep6/api/routes/ws.py
    - deep6/api/routes/backtest.py
    - tests/api/test_ws.py
    - tests/api/test_backtest.py
    - tests/api/__init__.py
  modified:
    - deep6/api/routes/events.py
    - deep6/api/app.py
decisions:
  - "WS_TOKEN defaults to 'deep6-dev' so local dev works without .env setup"
  - "Broadcast in events router is synchronous await — no fire-and-forget; ensures delivery before returning 200"
  - "Dry-run backtest uses _make_synthetic_bars(100) from sweep_thresholds when DATABENTO_API_KEY absent"
  - "ws_manager imported directly into events.py — no circular import risk since ws.py has no app-level imports"
metrics:
  duration: "~20 minutes"
  completed: "2026-04-14"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 2
  tests_added: 20
---

# Phase 10 Plan 01: WebSocket + Backtest API Summary

**One-liner:** Native WebSocket /ws with bearer-token auth + async backtest job API (/backtest/run, /backtest/results) wired into existing FastAPI backend with broadcast on every signal/trade insert.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | WebSocket ConnectionManager + /ws endpoint | 847314d | deep6/api/routes/ws.py, tests/api/test_ws.py |
| 2 | /backtest/run + /backtest/results + broadcast wiring | f4c1f86 | deep6/api/routes/backtest.py, events.py, app.py, tests/api/test_backtest.py |

## What Was Built

### deep6/api/routes/ws.py
- `ConnectionManager` class: `connect()`, `disconnect()`, `broadcast()` with dead-socket silent cleanup (T-10-04)
- Module-level singleton `ws_manager` imported by events.py
- `/ws` WebSocket endpoint: reads token from `?token=` query param or `Authorization: Bearer` header, compares to `WS_TOKEN` env var (default `"deep6-dev"`), closes with code 1008 on mismatch (T-10-01)
- Ping/pong keepalive protocol

### deep6/api/routes/backtest.py
- `BacktestRequest` Pydantic model with defaults
- `POST /backtest/run`: 202 response with job_id, 409 if already running (T-10-02), async task via `asyncio.create_task`
- `GET /backtest/results/{job_id}`: 404 on unknown, full job dict on known
- Background `_execute_backtest`: dry-run (synthetic bars) when no `DATABENTO_API_KEY`, else Databento fetch; both paths run in executor; stores `rows`, `summary`, `total_bars` on complete

### deep6/api/routes/events.py (modified)
- Added `from deep6.api.routes.ws import ws_manager`
- `POST /events/signal`: broadcasts `{"type": "signal", ...ev fields}` after DB insert (D-22)
- `POST /events/trade`: broadcasts `{"type": "trade", ...ev fields}` after DB insert (D-22)

### deep6/api/app.py (modified)
- Imports and mounts `ws_router_module.router` and `backtest_router_module.router`

## Test Coverage

20 tests across 2 files:
- `tests/api/test_ws.py`: ConnectionManager unit tests (broadcast, disconnect, dead-socket cleanup) + /ws endpoint auth integration tests
- `tests/api/test_backtest.py`: POST /backtest/run (202, 422, 409, defaults), GET /backtest/results (404, running, complete), router registration assertions, broadcast wiring verification

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] ws_router mounted in app.py during Task 1**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** Test 3 and 4 for Task 1 reference `deep6.api.app:app` to test the /ws endpoint — but the router was not yet mounted (that mount was listed under Task 2's files). Tests could not pass without the mount.
- **Fix:** Added ws_router import and mount to app.py during Task 1 commit so the Task 1 test file could fully pass.
- **Files modified:** deep6/api/app.py
- **Commit:** 847314d

## Known Stubs

None — all endpoints return real data or proper job state. Dry-run synthetic bars are clearly gated on absent `DATABENTO_API_KEY` and are a documented feature, not a stub.

## Threat Flags

No new security surface beyond what the plan's threat model covers (T-10-01 through T-10-04).

## Self-Check: PASSED

- deep6/api/routes/ws.py: FOUND
- deep6/api/routes/backtest.py: FOUND
- tests/api/test_ws.py: FOUND
- tests/api/test_backtest.py: FOUND
- Commit 847314d: FOUND
- Commit f4c1f86: FOUND
- /ws in app routes: CONFIRMED
- /backtest/run in app routes: CONFIRMED
- 20 tests passing: CONFIRMED
