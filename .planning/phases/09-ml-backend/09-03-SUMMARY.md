---
phase: 09-ml-backend
plan: "03"
subsystem: ml-backend
tags: [deploy-gate, weight-loader, optuna-sweep, atomic-write, rollback]
dependency_graph:
  requires: [09-01, 09-02]
  provides: [deploy-gate, sweep-api, atomic-weight-deployment]
  affects: [scorer, paper-trader]
tech_stack:
  added: []
  patterns:
    - atomic-rename (os.replace on POSIX/macOS for zero partial-write window)
    - tdd (RED commit then GREEN commit for WeightLoader)
    - async-job-pattern (asyncio.create_task + in-memory job store)
key_files:
  created:
    - deep6/ml/deploy_gate.py
    - deep6/ml/weight_loader.py
    - deep6/api/routes/sweep.py
    - tests/test_deploy_gate.py
  modified:
    - deep6/api/routes/weights.py
    - deep6/api/app.py
decisions:
  - "DeployGate fail-fast order: token → WFE → OOS count → weight cap"
  - "Weight cap override via override_weight_cap=True in DeployRequest (explicit opt-in)"
  - "GET /ml/deploy-token returns hint only; DEPLOY_SECRET remains server-side"
  - "Sweep dry-run: uses _make_synthetic_bars(200) when DATABENTO_API_KEY absent"
  - "T-09-12: 409 Conflict if sweep already running (single-job concurrency limit)"
metrics:
  duration_minutes: 18
  completed_date: "2026-04-13"
  tasks_completed: 2
  tasks_total: 3
  files_created: 4
  files_modified: 2
---

# Phase 9 Plan 03: Sweep API + Deploy Gate + Atomic Weight Swap Summary

Wires the Optuna sweep endpoint, full 3-part deployment gate, atomic weight file writes, and 7-day rollback. Plans 01+02 provided storage and models; this plan closes the loop so operators can trigger Bayesian sweeps via API and deploy weights only after explicit gate-passing.

## What Was Built

### 1. DeployGate (`deep6/ml/deploy_gate.py`)

3-part gate enforced in fail-fast order:

| Gate | Check | Failure Reason |
|------|-------|----------------|
| 1 — Token | `confirmation_token == DEPLOY_SECRET` | "Invalid confirmation token" |
| 2 — WFE | `candidate.wfe >= 0.70` | "WFE {value} < 0.70" |
| 3 — OOS count | `sum(oos_counts.values()) >= 200` | "Insufficient OOS trades: N < 200" |
| 4 — Weight cap | no signal > 3x baseline | "Weight cap exceeded for: [signals]" |

`DeployDecision` dataclass carries: `allowed`, `reason`, `wfe`, `oos_counts`, `weight_cap_violations`, `before_after` comparison dict.

`generate_token()` → `secrets.token_hex(16)` (32-char hex). Stored as `_pending_token`; `GET /ml/deploy-token` informs the operator that DEPLOY_SECRET is the expected value.

### 2. Sweep API (`deep6/api/routes/sweep.py`)

- `POST /ml/sweep` — triggers Optuna sweep as `asyncio.create_task`; returns `{job_id, status}` immediately (non-blocking)
- `GET /ml/sweep/{job_id}` — polls job status; returns `{status, best_params, best_pnl}` on completion
- T-09-12: Returns 409 if a sweep is already running
- Dry-run: if `DATABENTO_API_KEY` not set, uses `_make_synthetic_bars(200)` — sweep works in dev without Databento
- `GET /ml/deploy-token` — operator readiness check

### 3. WeightLoader (`deep6/ml/weight_loader.py`)

Atomic write pattern (T-09-09):
1. Copy existing weights.json → weights_prev.json (backup for rollback)
2. Write new content to weights.json.tmp
3. `os.replace(tmp, weights.json)` — atomic rename on POSIX/macOS; no partial-write window

`rollback()`: restores backup if within 7-day TTL (`backup_ttl_days=7`). Returns `False` if no backup or backup expired.

`backup_age_days()`: mtime-based age in fractional days.

### 4. Full Deploy Endpoint (`deep6/api/routes/weights.py`)

Replaces Plan 01 501-stub with full implementation:

- `POST /weights/deploy` — accepts `DeployRequest(candidate_weights, confirmation_token, override_weight_cap)`
- Loads `DEPLOY_SECRET` from env for token comparison
- Loads OOS counts from `app.state.event_store.count_oos_trades_per_signal()`
- Evaluates `DeployGate.evaluate()` → 422 on failure with reason
- On pass: `WeightLoader.write_atomic(candidate)` + T-09-11 structlog audit
- `GET /weights/rollback` — restore previous within TTL
- `GET /weights/current` — extended response: `{current, previous, backup_age_days}`

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `DEPLOY_SECRET` | (required) | Operator confirmation token for deploy gate |
| `WEIGHTS_PATH` | `./deep6_weights.json` | Active weights file path |
| `WEIGHTS_BACKUP_PATH` | `./deep6_weights_prev.json` | Backup/rollback file path |
| `DB_PATH` | `./deep6_ml.db` | EventStore SQLite path |

## Confirmation Token Flow

1. Operator retrieves `GET /ml/deploy-token` → sees DEPLOY_SECRET is the expected value
2. Operator copies their DEPLOY_SECRET value
3. Operator submits `POST /weights/deploy` with `confirmation_token: <DEPLOY_SECRET>`
4. Server evaluates all 4 gates; deploys atomically on pass

## TDD Evidence

- RED commit: `60d1aee` — 9 failing WeightLoader tests committed before implementation
- GREEN commit: `86761ce` — all 18 tests pass (9 DeployGate + 9 WeightLoader)

## Checkpoint Status

Task 3 (`checkpoint:human-verify`) reached. Operator must verify the running API (6 steps in plan) before confirming deploy pipeline is correct.

## Deviations from Plan

**1. [Rule 2 - Missing Feature] Added GET /ml/deploy-token endpoint**
- Found during: Task 1
- Issue: Plan specified `generate_token()` to show operator the token, but provided no API surface to retrieve it
- Fix: Added `GET /ml/deploy-token` endpoint that informs operator DEPLOY_SECRET is the expected value
- Files modified: `deep6/api/routes/sweep.py`

**2. [Rule 2 - Missing Auth Surface] Added WEIGHTS_BACKUP_PATH env var**
- Found during: Task 2
- Issue: WeightLoader hard-coded backup path; ops environments may need different paths
- Fix: Added `WEIGHTS_BACKUP_PATH` env var alongside existing `WEIGHTS_PATH`
- Files modified: `deep6/api/routes/weights.py`

## Threat Flags

None — all threat model items (T-09-09 through T-09-12) implemented as specified:
- T-09-09: os.replace atomic write ✓
- T-09-10: UUID4 job IDs (accepted) ✓
- T-09-11: structlog audit on deploy ✓
- T-09-12: 409 on concurrent sweeps ✓

## Self-Check: PASSED

- `deep6/ml/deploy_gate.py` — exists ✓
- `deep6/ml/weight_loader.py` — exists ✓
- `deep6/api/routes/sweep.py` — exists ✓
- `tests/test_deploy_gate.py` — exists, 18/18 pass ✓
- Commit `f0fd3fa` — Task 1 ✓
- Commit `60d1aee` — RED tests ✓
- Commit `86761ce` — Task 2 GREEN ✓
