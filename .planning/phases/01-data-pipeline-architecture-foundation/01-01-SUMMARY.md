---
phase: 01-data-pipeline-architecture-foundation
plan: 01
subsystem: data-pipeline
tags: [rithmic, asyncio, uvloop, dom-state, aggressor-gate, signal-flags, package-structure]
dependency_graph:
  requires: []
  provides:
    - deep6 Python package (importable, all subpackages)
    - DOMState pre-allocated zero-allocation DOM callback pattern
    - RithmicClient connection factory with aggressor verification gate
    - SignalFlags 44-bit IntFlag bitmask
  affects:
    - All future plans (deep6/ package is the shared foundation)
    - Plan 01-02 (FootprintBar accumulator imports from deep6.state)
    - Plan 01-03 (SessionManager imports from deep6.config, deep6.state)
    - Plan 01-04 (main asyncio loop imports all of the above)
tech_stack:
  added:
    - async-rithmic==1.5.9 (Rithmic L2 DOM + tick via WebSocket/protobuf)
    - uvloop==0.22.1 (asyncio event loop replacement)
    - aiosqlite==0.22.1 (async SQLite for session persistence)
    - numpy>=2.0 (DOM arrays, bar-close vectorized computation)
    - structlog>=25.0 (structured logging with JSON output)
    - pytest>=8.0 + pytest-asyncio>=1.2.0 (test framework)
  patterns:
    - asyncio.Runner(loop_factory=uvloop.new_event_loop) — Python 3.12 uvloop entry point
    - array.array 'd' pre-allocated arrays — zero-allocation DOM callback pattern
    - IntFlag bitmask — 44 bits, stable positions, O(popcount) scoring
    - Aggressor gate — module-level state, single event loop, no concurrent mutation
key_files:
  created:
    - pyproject.toml
    - .env.example
    - deep6/__init__.py
    - deep6/__main__.py
    - deep6/config.py
    - deep6/data/__init__.py
    - deep6/data/rithmic.py
    - deep6/data/dom_feed.py
    - deep6/data/tick_feed.py
    - deep6/engines/__init__.py
    - deep6/signals/__init__.py
    - deep6/signals/flags.py
    - deep6/scoring/__init__.py
    - deep6/execution/__init__.py
    - deep6/ml/__init__.py
    - deep6/api/__init__.py
    - deep6/state/__init__.py
    - deep6/state/dom.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_signal_flags.py
  modified:
    - .gitignore (added .env, Python, SQLite, .venv exclusions)
decisions:
  - "pyproject.toml build-backend corrected to setuptools.build_meta (legacy backend unavailable in venv pip)"
  - "DOMState uses array.array 'd' (not numpy) for hot-path simplicity; numpy reserved for bar-close vectorized ops"
  - "Aggressor gate is module-level state (not class instance) — safe because single event loop guarantees no concurrent mutation (T-01-02)"
  - "Config.safe_log_fields() helper prevents password leakage at all log call sites (T-01-01)"
  - "dom_feed.py clips incoming levels at LEVELS=40 but retains prior values for levels not covered by update"
metrics:
  duration_minutes: 5
  completed_date: "2026-04-13"
  tasks_completed: 3
  files_created: 21
  files_modified: 1
---

# Phase 1 Plan 1: Package Structure, DOMState, Aggressor Gate, SignalFlags Summary

**One-liner:** Deep6 Python package bootstrapped with uvloop asyncio entry point, pre-allocated array.array DOM state, 50-tick CME aggressor verification gate, and 44-bit SignalFlags IntFlag bitmask.

## What Was Built

### Task 1: Python Package Structure + pyproject.toml
- Full `deep6/` package with 8 subpackages: `data`, `engines`, `signals`, `scoring`, `execution`, `ml`, `api`, `state`
- `pyproject.toml` with all pinned dependencies — `async-rithmic==1.5.9` confirmed install
- `deep6/__main__.py` using `asyncio.Runner(loop_factory=uvloop.new_event_loop)` — the Python 3.12 uvloop pattern (not deprecated `uvloop.install()`)
- `deep6/config.py` — frozen `Config` dataclass with `from_env()` and `safe_log_fields()` to prevent password logging
- `tests/conftest.py` — `config` and `fake_tick_factory` fixtures ready for all future test plans

### Task 2: DOMState, RithmicClient, Callbacks
- `deep6/state/dom.py` — `DOMState` with `array.array('d', [0.0] * 40)` pre-allocated for 40 bid + 40 ask levels; `update()` assigns in-place only (no append, no realloc)
- `deep6/data/rithmic.py` — `connect_rithmic()` with Issue #49 workaround (`asyncio.sleep(0.5)` after `connect()`); `aggressor_verification_gate()` samples 50 ticks, logs ESCALATE if >10% UNSPECIFIED
- `deep6/data/dom_feed.py` — `make_dom_callback()` filtering to SOLO/END update types only; exits on FROZEN state
- `deep6/data/tick_feed.py` — `make_tick_callback()` recording aggressor samples and forwarding to bar builders only after gate passes and aggressor != 0

### Task 3: SignalFlags IntFlag (TDD)
- RED: `tests/test_signal_flags.py` with 5 failing tests committed before implementation
- GREEN: `deep6/signals/flags.py` — 44 signals across 7 groups (ABS=4, EXH=8, IMB=9, DELT=11, AUCT=5, TRAP=5, VOLP=2), bits 0-43, all distinct powers of 2
- All 5 tests pass: `NONE==0`, powers-of-2, OR popcount, int64 fit, exact count of 44

## Installation Notes

**async-rithmic 1.5.9 install command that worked:**
```bash
pip install -e ".[dev]"
```
This installs async-rithmic==1.5.9 as declared in pyproject.toml. The version resolved correctly from PyPI.

**Confirmed aggressor field structure:**
```
TransactionType enum (async_rithmic/protocol_buffers/last_trade_pb2.py):
  TRANSACTIONTYPE_UNSPECIFIED = 0
  BUY = 1   # ask-side aggressor (buyer lifts the offer)
  SELL = 2  # bid-side aggressor (seller hits the bid)
```
Field name in callback dict: `"aggressor"` (protobuf field name preserved via `MessageToDict(preserving_proto_field_name=True)`).

**DOMState array.array typecode confirmed:**
`'d'` (C double, 8 bytes) — correct for NQ prices (e.g. 21000.25) and sizes (integers stored as doubles).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] setuptools.backends.legacy not available in venv pip**
- **Found during:** Task 1, first `pip install -e ".[dev]"` attempt
- **Issue:** `pyproject.toml` initially specified `build-backend = "setuptools.backends.legacy:build"` which requires setuptools >= 69.0 with the new backends subpackage — not available in the venv's pip version
- **Fix:** Changed to `build-backend = "setuptools.build_meta"` (the standard, universally supported backend)
- **Files modified:** `pyproject.toml`
- **Impact:** Zero functional impact — `setuptools.build_meta` is the correct standard backend

## Known Stubs

The following subpackages are intentional empty stubs created for package structure only. They will be filled in future plans:
- `deep6/engines/__init__.py` — Phase 2 (signal engines)
- `deep6/scoring/__init__.py` — Phase 2 (confidence scoring)
- `deep6/execution/__init__.py` — Phase 4 (order execution, FROZEN state machine)
- `deep6/ml/__init__.py` — Phase 6 (Kronos E10 integration)
- `deep6/api/__init__.py` — Phase 7 (FastAPI endpoints)

These stubs are intentional infrastructure placeholders, not data-flow stubs. No UI data is flowing through empty values.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced beyond what the plan's threat model covers.

## Self-Check: PASSED

Files exist:
- `pyproject.toml` ✓
- `deep6/__main__.py` ✓
- `deep6/config.py` ✓
- `deep6/state/dom.py` ✓
- `deep6/data/rithmic.py` ✓
- `deep6/data/dom_feed.py` ✓
- `deep6/data/tick_feed.py` ✓
- `deep6/signals/flags.py` ✓
- `tests/test_signal_flags.py` ✓

Commits:
- `7ca1242` chore(01-01): bootstrap deep6 Python package structure
- `f582fa0` feat(01-01): implement DOMState, rithmic connection, and aggressor gate
- `9c5a822` test(01-01): add failing tests for SignalFlags 44-bit IntFlag (RED)
- `93f4b65` feat(01-01): implement SignalFlags 44-bit IntFlag (GREEN)

All 5 SignalFlags tests pass. All imports succeed. Full verification suite: 10/10 checks OK.
