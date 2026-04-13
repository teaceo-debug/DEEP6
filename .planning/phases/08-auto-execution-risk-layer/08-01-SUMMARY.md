---
phase: 08-auto-execution-risk-layer
plan: "01"
subsystem: execution
tags: [execution, risk, freeze-guard, bracket-orders, paper-trading]
dependency_graph:
  requires:
    - deep6/scoring/scorer.py (ScorerResult, SignalTier)
    - deep6/engines/gex.py (GexSignal, GexRegime)
    - deep6/state/connection.py (FreezeGuard)
  provides:
    - deep6/execution/config.py (ExecutionConfig, ExecutionDecision, OrderSide)
    - deep6/execution/engine.py (ExecutionEngine.evaluate)
    - deep6/state/connection.py (sync_position_state, FreezeGuard.last_known_position)
  affects:
    - Plans 02, 03, 04 (PositionManager, RiskManager, PaperTrader all import ExecutionEngine)
tech_stack:
  added: []
  patterns:
    - frozen dataclass for immutable config (T-08-01 mitigation)
    - gate-chain evaluate() returning dataclass decision (no side effects)
    - async position reconciliation before unfreeze (D-15, T-08-02)
key_files:
  created:
    - deep6/execution/config.py
    - deep6/execution/engine.py
    - tests/execution/test_execution_config.py
    - tests/execution/test_execution_engine.py
    - tests/state/test_connection_reconcile.py
  modified:
    - deep6/execution/__init__.py
    - deep6/state/connection.py
decisions:
  - "ExecutionDecision is a plain dataclass (not frozen) so callers can annotate/enrich it"
  - "sync_position_state is a module-level async function (not a method) for testability"
  - "zone_target uses max/min logic: LONG takes further of zone vs rr_target, SHORT takes closer"
metrics:
  duration: "3 minutes"
  completed: "2026-04-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 5
  files_modified: 2
  tests_added: 21
---

# Phase 8 Plan 01: ExecutionConfig + ExecutionEngine + FreezeGuard Reconciliation Summary

**One-liner:** Frozen ExecutionConfig (D-01..D-22 thresholds) + gate-chain ExecutionEngine.evaluate() for bracket order parameters + FreezeGuard async position reconciliation via Rithmic ORDER_PLANT.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | ExecutionConfig + ExecutionDecision dataclasses | b2237db | deep6/execution/config.py, deep6/execution/__init__.py |
| 2 | ExecutionEngine gate checks and bracket computation | cce778b | deep6/execution/engine.py |
| 3 | FreezeGuard position reconciliation | 8c49b2d | deep6/state/connection.py |

## What Was Built

### ExecutionConfig (`deep6/execution/config.py`)
Frozen dataclass covering all D-01..D-22 thresholds with correct defaults:
- `stop_buffer_ticks=2`, `max_stop_atr_mult=2.0` (D-04/D-05)
- `target_rr_min=1.5` (D-08), `max_hold_bars=10` (D-09)
- `entry_delay_seconds=3.0`, `entry_prob_threshold=0.55` (D-03)
- `daily_loss_limit=500.0`, `consecutive_loss_limit=3`, `pause_minutes=30.0` (D-10/D-11)
- `paper_trading_days=30`, `paper_slippage_fixed_ticks=1` (D-18/D-19)
- `OrderSide.LONG/SHORT` enum, `ExecutionDecision` with action/side/prices/ticks fields

### ExecutionEngine (`deep6/execution/engine.py`)
Gate-chain `evaluate()` method returning `ExecutionDecision`:
1. D-14: `freeze_guard.is_frozen` → `FROZEN` (first gate, no bypass)
2. Tier filter: `QUIET`/`TYPE_C` → `SKIP`
3. Direction filter: neutral → `SKIP`
4. D-04: Compute `stop_price` = zone boundary + buffer (ticks + 0.50 pts structural)
5. D-05: `stop_distance > 2×ATR` → `SKIP`
6. D-07/D-08: `target_price` = zone_target or 1.5× risk distance
7. D-02: `TYPE_B` → `WAIT_CONFIRM`; `TYPE_A` → `ENTER`

### FreezeGuard reconciliation (`deep6/state/connection.py`)
- Added `sync_position_state(client, config)` — queries `client.get_positions(exchange)`, finds NQ net_quantity, returns `{"rithmic_position": int, "reconciled": bool}`
- `on_reconnect()` now calls `sync_position_state()` before setting `CONNECTED`; stays `FROZEN` if reconciliation fails (T-08-02)
- Added `_last_known_position: int = 0` field and `last_known_position` property

## Tests

21 tests across 3 files — all pass:
- `tests/execution/test_execution_config.py` (6 tests): defaults, frozen mutation guard, decision fields, enum values, module exports
- `tests/execution/test_execution_engine.py` (8 tests): frozen guard, QUIET/TYPE_C skip, TYPE_B wait-confirm, TYPE_A SHORT/LONG brackets, stop-too-wide skip, neutral direction skip
- `tests/state/test_connection_reconcile.py` (7 tests): reconcile success (flat/short), reconcile failure stays frozen, disconnect → frozen, default position, sync_position_state success/failure

## Deviations from Plan

None — plan executed exactly as written.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. `sync_position_state` queries existing Rithmic ORDER_PLANT — already within the trust boundary defined in the plan's threat model.

## Self-Check: PASSED

Files exist:
- deep6/execution/config.py: FOUND
- deep6/execution/engine.py: FOUND
- deep6/execution/__init__.py: FOUND
- deep6/state/connection.py: FOUND (modified)
- tests/execution/test_execution_config.py: FOUND
- tests/execution/test_execution_engine.py: FOUND
- tests/state/test_connection_reconcile.py: FOUND

Commits exist: b2237db, cce778b, 8c49b2d — verified via `git log`

All 21 tests pass: confirmed via `python -m pytest tests/execution/ tests/state/test_connection_reconcile.py`
