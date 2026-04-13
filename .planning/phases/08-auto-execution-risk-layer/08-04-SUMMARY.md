---
phase: 08-auto-execution-risk-layer
plan: "04"
subsystem: execution
tags: [paper-trading, risk-management, slippage, gate, sqlite]
dependency_graph:
  requires:
    - "08-01"  # ExecutionConfig, ExecutionEngine, FreezeGuard
    - "08-02"  # PositionManager (implemented as Rule 3 deviation)
    - "08-03"  # RiskManager (implemented as Rule 3 deviation)
  provides:
    - PaperTrader
    - LiveGate
    - PaperStats
  affects:
    - "08-05"  # Future LiveTrader (same interface, different fill mechanics)
    - "09"     # ML backend consumes PositionEvents
    - "10"     # Dashboard consumes PositionEvents
tech_stack:
  added:
    - sqlite3 (stdlib) — LiveGate 30-day persistence
    - random (stdlib) — slippage simulation
  patterns:
    - TDD red-green cycle per task
    - SQLite idempotent INSERT OR IGNORE for gate tracking
    - dataclasses.replace() for immutable decision mutation
    - structlog for full audit trail on every bar decision
key_files:
  created:
    - deep6/execution/paper_trader.py
    - deep6/execution/position_manager.py
    - deep6/execution/risk_manager.py
    - tests/execution/test_paper_trader.py
    - tests/execution/test_position_manager.py
    - tests/execution/test_risk_manager.py
    - tests/execution/test_risk_integration.py
  modified:
    - deep6/execution/__init__.py
decisions:
  - "SQLite INSERT OR IGNORE makes LiveGate.record_trading_day() safely idempotent — safe to call on every bar close"
  - "structlog key renamed event_type (not event) to avoid conflict with structlog reserved 'event' positional arg"
  - "dataclasses.replace() used to apply simulated fill price to ExecutionDecision without mutating frozen fields"
  - "PositionManager and RiskManager implemented inline (Rule 3 deviation) since 08-02 and 08-03 were unexecuted"
metrics:
  duration_seconds: 349
  completed_date: "2026-04-13"
  tasks_completed: 2
  files_created: 7
  files_modified: 1
  tests_added: 66
---

# Phase 8 Plan 04: PaperTrader — 30-Day Gate + Pipeline Orchestration Summary

**One-liner:** PaperTrader wires ExecutionEngine → RiskManager → PositionManager with SQLite-backed 30-day gate and 1+random-tick adverse slippage model.

## What Was Built

### LiveGate
SQLite-backed persistence layer for the 30-day paper trading gate (D-18, D-20). Uses `INSERT OR IGNORE` so `record_trading_day()` is idempotent and safe to call on every bar. `is_gate_open()` returns True only when ≥30 distinct trading days are recorded — no force flag, no environment override.

### PaperStats
Dataclass tracking `total_trades`, `wins`, `losses`, `total_pnl`, `max_drawdown`, `peak_pnl`. `win_rate` computed property. `to_dict()` returns JSON-primitive dict for Phase 9/10 consumption.

### PaperTrader
Top-level orchestrator. `complete_bar()` implements the full pipeline:
1. Record trading day in LiveGate
2. `engine.evaluate()` → ExecutionDecision
3. If `ENTER`: `risk.can_enter()` → GateResult; if allowed: `_simulate_fill()` → `positions.open_position()`
4. `positions.on_bar()` → list[PositionEvent]; for each close event: `risk.record_trade()` + `stats.record_trade()`
5. Full structlog audit trail on every decision

### Slippage Model (D-19)
`_simulate_fill()`: `slippage = fixed_ticks * tick_size + random(0, random_max) * tick_size`. LONG fills at `entry + slippage` (adverse), SHORT fills at `entry - slippage` (adverse). Default: 1 fixed tick + 0-1 random tick.

### Dependency Auto-Implementation (Rule 3)
Plans 08-02 (PositionManager) and 08-03 (RiskManager) were not yet executed. Both were implemented inline as a blocking-issue fix to allow 08-04 to proceed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] PositionManager and RiskManager not yet implemented**
- **Found during:** Task 1 setup — `deep6/execution/position_manager.py` and `risk_manager.py` did not exist
- **Fix:** Implemented both files from their respective plan specs (08-02, 08-03) with full test suites
- **Files created:** `deep6/execution/position_manager.py`, `deep6/execution/risk_manager.py`, `tests/execution/test_position_manager.py`, `tests/execution/test_risk_manager.py`, `tests/execution/test_risk_integration.py`
- **Commit:** a5d90d4

**2. [Rule 1 - Bug] structlog `event` reserved keyword collision**
- **Found during:** Task 2 GREEN phase — `log.info("paper_trader.trade_closed", event=...)` raised TypeError
- **Fix:** Renamed kwarg to `event_type=ev.event_type.value`
- **Files modified:** `deep6/execution/paper_trader.py`

## Tests

| File | Tests | Status |
|------|-------|--------|
| test_paper_trader.py | 19 | PASS |
| test_position_manager.py | 14 | PASS |
| test_risk_manager.py | 13 | PASS |
| test_risk_integration.py | 3 | PASS |
| test_execution_config.py | (existing) | PASS |
| test_execution_engine.py | (existing) | PASS |
| **Total** | **66** | **PASS** |

## Known Stubs

None — all data paths wired. LiveGate reads from real SQLite; PaperStats accumulates from real PositionEvents.

## Threat Surface Scan

No new network endpoints or auth paths introduced. LiveGate writes to a local SQLite file (path passed by caller). Threats T-08-14 through T-08-18 from the plan's threat model are all mitigated:

| Threat ID | Status |
|-----------|--------|
| T-08-14: LiveGate 30-day bypass | Mitigated — no force flag exists in code |
| T-08-15: paper_days table manual edit | Accepted — single-user local system |
| T-08-16: Simulated fill spoofing | Mitigated — all fills logged with `paper_trader.enter` key |
| T-08-17: on_event callback DoS | Mitigated — `_route_event` wraps in try/except |
| T-08-18: PaperStats.to_dict in logs | Accepted — local only |

## Self-Check: PASSED

All created files found on disk. All commits present in git history.

| Check | Result |
|-------|--------|
| deep6/execution/paper_trader.py | FOUND |
| deep6/execution/position_manager.py | FOUND |
| deep6/execution/risk_manager.py | FOUND |
| tests/execution/test_paper_trader.py | FOUND |
| commit a5d90d4 (08-02/03 deps) | FOUND |
| commit 290816a (failing tests) | FOUND |
| commit 3f779ad (implementation) | FOUND |
| 66 tests pass | PASS |
