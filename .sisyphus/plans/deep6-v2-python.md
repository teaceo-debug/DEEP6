# DEEP6 v2.0 — Python Edition (Clean Room Rebuild)

## TL;DR

> **Quick Summary**: Clean room rebuild of DEEP6 as a Python-native live runtime for NQ futures auto-trading. Eliminates NinjaTrader dependency by connecting directly to Rithmic via async-rithmic for L2 DOM data (40+ levels, 1,000 callbacks/sec) and order execution on AMP Futures. Uses existing Python engine (Phases 1-15) and NT8 C# (Phases 16-19) as reference implementations only — new architecture, new file structure, TDD throughout.
> 
> **Deliverables**:
> - Complete Python trading engine with 52 signal detectors (8 categories), two-layer confluence scorer, and 7-state execution FSM
> - Direct Rithmic order execution via async-rithmic on AMP Futures
> - Kronos-small E10 directional bias integration
> - FastAPI + Next.js operator dashboard (MVP: signal feed, P&L, connection status)
> - TradingView MCP integration for Claude-in-the-loop visual analysis
> - Production hardening: unified startup, observability, paper-to-live promotion gates
> 
> **Estimated Effort**: XL (40+ tasks across 10 waves)
> **Parallel Execution**: YES — 10 waves, up to 8 concurrent agents in Wave 3
> **Critical Path**: Foundation → Data Pipeline → Signals → Scoring → Execution

---

## Context

### Original Request
Build the complete DEEP6 v2.0 Python Edition system as a clean room rebuild, using the existing Python reference engine and NT8 C# implementation as reference only. Maximize parallel agent execution.

### Interview Summary
**Key Discussions**:
- **Broker**: AMP Futures selected (confirmed Rithmic API/plugin support). Replaces Apex which blocked API access.
- **Build Strategy**: CLEAN ROOM REBUILD — new architecture, new file structure. Not incremental hardening.
- **NT8 Relationship**: DUAL RUNTIME — NT8 stays for live execution while Python v2 is built in parallel.
- **Test Strategy**: TDD (RED-GREEN-REFACTOR) for all new code.
- **Core Thesis**: Absorption and exhaustion are the highest-alpha reversal signals in order flow.

**Research Findings**:
- Python reference engine: 162 files, 1,436 tests across 113 test files, Phases 1-15 complete
- NT8 C# path: 164 files, 62 test files, Phase 18/19 (nearly complete)
- R3-optimized weights (source: `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs:59-66`): Absorption 20.0, Exhaustion 15.7, Imbalance 25.0, Delta 14.3, Volume Profile 20.2, Auction 12.6, Trapped 0.0, POC 0.0
- Trapped and POC categories have ZERO alpha — build disabled-by-default
- **Signal inventory**: 52 detector implementations across 8 scorer categories: Absorption (4: ABS-01..04), Exhaustion (6: EXH-01..06), Imbalance (9: IMB-01..09), Delta (11: DELT-01..11), Auction (5: AUCT-01..05), Trapped (5: TRAP-01..05), Volume Patterns (6: VOLP-01..06, scorer category: `volume_profile`), Engine/Context (6: ENG-02..07, scorer category: `poc` for ENG-06 context, others contribute to parent category)
- Midday block (10:30-13:00 ET, bars 60-210 from 9:30 open) accumulated -$1,622 loss
- IB multiplier (bars 0-59): 1.15x boost
- Multiplier chain order LOCKED: base → confluence_mult → zone_bonus → GEX → agreement → IB_mult → VPIN → clip(0,100)

### Metis Review
**Identified Gaps** (all addressed in plan):
- **R1**: Wave 3 parallelism requires frozen type contracts from Wave 1 — added hard gate
- **R2**: "Clean room" vs "port" ambiguity — clarified: implement from algorithm description, test against JSON fixtures
- **R3**: Kronos inference blocking event loop — mandated ThreadPoolExecutor + janus queue
- **R4**: Dashboard scope explosion — scoped Wave 7 to MVP (signal feed, P&L, connection status)
- **R5**: async-rithmic ORDER_PLANT untested — added mandatory research spike in Wave 5
- **R6**: Event store schema undefined — defined DuckDB for events, SQLite for transactional state
- **R7**: Session edge cases (CME halts, contract rollover, DST, half-days) — added to Wave 2 acceptance criteria
- **Cross-detector wiring**: AbsorptionDetector → IcebergDetector interface defined in Wave 1 types
- **GEX integration**: Stub interface in Wave 1, real implementation in Wave 9
- **VPIN integration**: Stub as 1.0 multiplier in Wave 4, real implementation in Wave 9
- **Config management**: Pydantic v2 Settings standardized across all subsystems
- **Logging**: structlog with JSON output from Wave 1

---

## Work Objectives

### Core Objective
Build a production-grade Python-native NQ futures auto-trading system that connects directly to Rithmic via async-rithmic, processes 1,000+ DOM callbacks/sec, evaluates 52 market microstructure signals (8 scorer categories) per bar, and executes trades through a battle-tested confidence scoring and risk management pipeline.

### Concrete Deliverables
- `deep6v2/` Python package with all subsystems
- 52 signal detectors (8 scorer categories) passing against reference JSON fixtures
- Two-layer confluence scorer with R3-optimized weights
- 7-state Trade Decision Machine FSM
- async-rithmic connection manager with FreezeGuard
- Kronos-small E10 bias engine with async inference
- FastAPI SSE/WebSocket backend + Next.js dashboard MVP
- TradingView MCP integration
- Unified `python -m deep6v2` startup command
- pytest suite with >90% coverage on signal logic
- `SIGNAL_TO_CATEGORY` mapping dict connecting 52 signals to 8 scorer categories

### Definition of Done
- [ ] `pytest tests_v2/ --tb=short` passes with 0 failures
- [ ] DOM callback benchmark: 1,000 `update_level()` calls processed in <1ms (matching Task 8 target)
- [ ] Bar close → signal evaluation → score: <100ms p99
- [ ] All 52 signal detectors pass against reference fixtures (±0.01 tolerance)
- [ ] Scorer produces correct tier/score for 5 scoring scenario fixtures (±1 point)
- [ ] Rithmic test environment connection + subscription verified
- [ ] async-rithmic ORDER_PLANT order submission tested on test environment
- [ ] Dashboard MVP: signal feed, P&L tracker, connection status functional
- [ ] FSM reachability test: all 7 states, 11 transitions reachable
- [ ] End-to-end pipeline test: 5 synthetic sessions → at least 1 produces IN_POSITION entry

### Must Have
- Pre-allocated DOM arrays (zero-allocation hot path at 1,000 callbacks/sec)
- Aggressor verification gate as first safety checkpoint (no footprint accumulation until BUY/SELL confirmed)
- FreezeGuard state machine (CONNECTED → FROZEN → RECONNECTING → CONNECTED) with position reconciliation
- Clock abstraction (WallClock for live, EventClock for replay) — every time reference through `clock.now()`
- GC disabled during RTH (9:30 ET open → 16:00 ET close)
- Exception isolation per detector — one crash cannot abort bar evaluation loop
- Midday block (10:30-13:00 ET, bars 60-210 since 9:30 RTH open) enforced as QUIET tier
- IB multiplier (1.15x for bars 0-59 during initial balance)
- Multiplier chain order exactly: base → confluence_mult → zone_bonus → GEX → agreement → IB_mult → VPIN → clip(0,100)
- Confirmation-bar delay (D-20): entry triggers fire on NEXT bar's close
- SharedState container owned by single asyncio event loop — no locks needed
- structlog with JSON output and per-bar correlation IDs

### Must NOT Have (Guardrails)
- **No R3 weight changes** without re-running attribution analysis
- **No Kronos synchronous inference** in the asyncio event loop — must use ThreadPoolExecutor + janus queue
- **No footprint chart rendering** in Wave 7 MVP dashboard — signal/score displays and P&L only
- **No GC during RTH** — `gc.disable()` at session open, `gc.enable()` at session close
- **No lock-based concurrency** — single event loop owns all state
- **No copy-paste from reference implementations** — implement from algorithm descriptions, verify against fixtures
- **No multi-instrument support** — NQ only
- **No mobile app, social features, options execution**
- **No over-engineering** — every feature must answer "Does this improve high-quality NQ trade identification?"
- **No Trapped/POC signals at full priority** — 0.0 weight in R3, build disabled-by-default only
- **No ML pipelines beyond Kronos E10** — LGBM, HMM deferred post-v2
- **No Copilot subsystem** — deferred post-v2
- **No custom Lightweight Charts footprint plugin** in MVP — defer to post-MVP

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: YES (existing pytest infra with 1,436 tests as reference)
- **Automated tests**: TDD (RED-GREEN-REFACTOR for all new code)
- **Framework**: pytest + pytest-asyncio + pytest-benchmark
- **Each task follows**: RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Signal Logic**: Use pytest with JSON fixture comparison — assert SignalId, Direction, Strength within ±0.01
- **Data Pipeline**: Use pytest-asyncio with synthetic Rithmic callbacks — assert DOM state, bar boundaries, RTH gating
- **Execution Logic**: Use pytest with synthetic scoring scenarios — assert FSM transitions, risk gates, order generation
- **API/Backend**: Use Bash (curl/httpx) — assert SSE streams, WebSocket messages, REST responses
- **Performance**: Use pytest-benchmark — assert DOM callback throughput, signal evaluation latency

---

## Execution Strategy

### Parallel Execution Waves

> Maximize throughput by grouping independent tasks into parallel waves.
> Each wave completes before the next begins (hard gates at wave boundaries).
> Target: 5-8 tasks per wave. Signal wave (Wave 3) runs 8 parallel agents.

```
Wave 1 (Foundation — types, config, test infra, clock):
├── Task 1: Project scaffolding + package structure [quick]
├── Task 2: Core type definitions — frozen API contracts [deep]
├── Task 3: Configuration system — Pydantic v2 Settings [quick]
├── Task 4: Test infrastructure + fixture loading [quick]
├── Task 5: Clock abstraction — WallClock + EventClock [quick]
├── Task 6: Logging foundation — structlog + JSON [quick]
└── GATE: All types frozen. pytest --co runs clean.

Wave 2 (Data Pipeline — Rithmic, DOM, bars, sessions):
├── Task 7: async-rithmic connection manager + FreezeGuard [deep]
├── Task 8: DOM state management — pre-allocated arrays [deep]
├── Task 9: Aggressor verification + tick classification [unspecified-high]
├── Task 10: Bar builder (1m, 5m) + session management [deep]
├── Task 11: Rithmic test environment connection test [quick]
├── Task 12: Event store schema — DuckDB + SQLite persistence [unspecified-high]
└── GATE: BarBuilder produces correct FootprintBar from synthetic ticks.

Wave 3 (Signal Engines — 8 PARALLEL agents, one per category):
├── Task 13: Absorption detectors ABS-01..04 [deep]
├── Task 14: Exhaustion detectors EXH-01..06 [deep]
├── Task 15: Imbalance detectors IMB-01..09 [deep]
├── Task 16: Delta detectors DELT-01..11 [deep]
├── Task 17: Auction theory detectors AUCT-01..05 [deep]
├── Task 18: Trapped traders TRAP-01..05 (disabled-by-default) [unspecified-high]
├── Task 19: Volume pattern detectors VOLP-01..06 [deep]
├── Task 20: Engine/context detectors ENG-02..07 + DetectorRegistry [deep]
└── GATE: All 52 signals pass against JSON fixtures.

Wave 4 (Scoring & Confluence — depends on Wave 3):
├── Task 21: Two-layer confluence scorer + R3 weights [deep]
├── Task 22: Entry gate logic (Type A/B/C) + veto conditions [unspecified-high]
├── Task 23: Hysteresis FSM + midday block + IB multiplier [deep]
└── GATE: Scorer produces correct tier/score for 5 scoring fixtures.

Wave 5 (Execution — depends on Wave 4):
├── Task 24: Research spike — async-rithmic ORDER_PLANT test [deep]
├── Task 25: Trade Decision Machine — 7-state FSM [deep]
├── Task 26: Risk manager + position manager [deep]
├── Task 27: Paper trader + promotion gate + kill switch [unspecified-high]
└── GATE: FSM reachability test passes. End-to-end pipeline drives 5 sessions.

Wave 6 (Kronos — parallel with Wave 5, depends on Wave 2):
├── Task 28: Kronos model loading + tokenizer [unspecified-high]
├── Task 29: OHLCV accumulator + async inference pipeline [deep]
├── Task 30: E10 bias signal integration with scorer [unspecified-high]
└── No hard gate — integrates with Wave 4 scorer when ready.

Wave 7 (Dashboard MVP — parallel with Waves 5-6, depends on Wave 4):
├── Task 31: FastAPI backend — SSE + WebSocket endpoints [unspecified-high]
├── Task 32: Next.js shell + signal feed display [visual-engineering]
├── Task 33: P&L tracker + connection status panel [visual-engineering]
├── Task 34: Session replay endpoint [unspecified-high]
└── No hard gate — independent UI milestone.

Wave 8 (TradingView MCP — parallel with Waves 5-7, depends on Wave 2):
├── Task 35: TradingView MCP connection + chart state reading [quick]
├── Task 36: Visual analysis integration [unspecified-high]
└── No hard gate — independent integration milestone.

Wave 9 (Operational Hardening — depends on Waves 1-5):
├── Task 37: Unified startup — python -m deep6v2 [unspecified-high]
├── Task 38: GEX integration — massive.com API [unspecified-high]
├── Task 39: VPIN module + scorer integration [unspecified-high]
├── Task 40: Observability + alerting + GC management [unspecified-high]
├── Task 41: Session edge cases — CME halts, contract rollover, DST, half-days [deep]
└── GATE: Unified startup runs clean. GEX and VPIN integrated. RE-VERIFY: run full pytest tests_v2/ to confirm core signal/scorer/FSM tests still pass after integration.

Wave FINAL (Verification — after ALL tasks):
├── F1: Plan compliance audit [oracle]
├── F2: Code quality review [unspecified-high]
├── F3: Agent-executed integration QA [unspecified-high]
├── F4: Scope fidelity check [deep]
└── → Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1-6 | — | 7-12 | 1 |
| 7 | 2, 3, 5, 6 | 11, 13-20, 28, 35 | 2 |
| 8 | 2, 5 | 9, 10, 13-20 | 2 |
| 9 | 2, 8 | 10 | 2 |
| 10 | 2, 5, 8, 9 | 13-20 | 2 |
| 11 | 7 | 24 | 2 |
| 12 | 2, 3 | 25, 34 | 2 |
| 13-20 | 2, 8, 10 | 21-23 | 3 |
| 21-23 | 13-20 | 24-27, 30 | 4 |
| 24 | 7, 11 | 25-27 | 5 |
| 25 | 2, 12, 21-23 | 26, 27 | 5 |
| 26 | 25 | 27 | 5 |
| 27 | 25, 26 | 37 | 5 |
| 28-29 | 2, 10 | 30 | 6 |
| 30 | 21, 29 | 37 | 6 |
| 31 | 2, 21 | 32, 33 | 7 |
| 32-33 | 31 | — | 7 |
| 34 | 12, 31 | — | 7 |
| 35-36 | 7 | — | 8 |
| 37-41 | 1-27 | F1-F4 | 9 |
| F1-F4 | ALL | — | FINAL |

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|------------|
| 1 | 6 | T1 → `quick`, T2 → `deep`, T3-T6 → `quick` |
| 2 | 6 | T7 → `deep`, T8 → `deep`, T9 → `unspecified-high`, T10 → `deep`, T11 → `quick`, T12 → `unspecified-high` |
| 3 | 8 | T13-T17, T19-T20 → `deep`, T18 → `unspecified-high` |
| 4 | 3 | T21 → `deep`, T22 → `unspecified-high`, T23 → `deep` |
| 5 | 4 | T24-T26 → `deep`, T27 → `unspecified-high` |
| 6 | 3 | T28 → `unspecified-high`, T29 → `deep`, T30 → `unspecified-high` |
| 7 | 4 | T31 → `unspecified-high`, T32-T33 → `visual-engineering`, T34 → `unspecified-high` |
| 8 | 2 | T35 → `quick`, T36 → `unspecified-high` |
| 9 | 5 | T37-T40 → `unspecified-high`, T41 → `deep` |
| FINAL | 4 | F1 → `oracle`, F2-F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

### Wave 1: Foundation

- [x] 1. Project Scaffolding + Package Structure

  **What to do**:
  - Create `deep6v2/` package with `__init__.py`, `__main__.py`, `py.typed`
  - Create subdirectory structure: `data/`, `state/`, `signals/`, `scoring/`, `execution/`, `kronos/`, `api/`, `tradingview/`, `types/`, `config/`
  - Create `pyproject.toml` with Python 3.12+ requirement, dependencies: async-rithmic==1.5.9, pydantic>=2.0, structlog, aiosqlite, duckdb, janus, numpy, uvicorn, fastapi, httpx
  - Create `pytest.ini` or `pyproject.toml [tool.pytest]` section with asyncio_mode=auto, testpaths=["tests_v2"]
  - Create `tests_v2/` directory with `conftest.py` containing shared fixtures
  - Create `Makefile` targets: `test`, `lint`, `typecheck`, `run`, `run-dry`
  - Write RED test: `tests_v2/test_package.py` — verify `import deep6v2` works and version string exists
  - Make test GREEN: implement `deep6v2/__init__.py` with `__version__`

  **Must NOT do**:
  - Do not copy any files from existing `deep6/` package
  - Do not install NinjaTrader-related dependencies
  - Do not add dependencies not in the technology stack

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — must complete FIRST within Wave 1
  - **Parallel Group**: Wave 1 lead (Tasks 2-6 start after Task 1 completes)
  - **Blocks**: Tasks 2-6 (they need package structure), Tasks 7-12
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `deep6/__init__.py` — Existing package init pattern (version string)
  - `deep6/__main__.py:1-20` — Existing main entry point structure
  - `pyproject.toml` — Existing dependency list (reference for versions)

  **External References**:
  - async-rithmic PyPI: https://pypi.org/project/async-rithmic/ (v1.5.9)
  - Pydantic v2 docs: https://docs.pydantic.dev/latest/

  **WHY Each Reference Matters**:
  - `pyproject.toml` — Copy exact dependency versions to ensure compatibility
  - `deep6/__main__.py` — Understand the startup pattern but implement fresh

  **Acceptance Criteria**:

  - [ ] `import deep6v2` succeeds and `deep6v2.__version__` returns a string
  - [ ] `pytest tests_v2/ --co` collects at least 1 test with 0 errors
  - [ ] All subdirectories exist with `__init__.py` files
  - [ ] `pip install -e .` succeeds from `pyproject.toml`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Package imports correctly
    Tool: Bash (python)
    Preconditions: pip install -e . completed
    Steps:
      1. Run: python -c "import deep6v2; print(deep6v2.__version__)"
      2. Assert output is a non-empty version string (e.g., "2.0.0-dev")
    Expected Result: Version string printed, exit code 0
    Failure Indicators: ImportError, ModuleNotFoundError, empty string
    Evidence: .sisyphus/evidence/task-1-import.txt

  Scenario: Test collection works
    Tool: Bash (pytest)
    Preconditions: Package installed
    Steps:
      1. Run: pytest tests_v2/ --co -q
      2. Assert output shows "N tests collected" where N >= 1
      3. Assert exit code 0 (no collection errors)
    Expected Result: At least 1 test collected with 0 errors
    Failure Indicators: "ERROR" in output, exit code != 0
    Evidence: .sisyphus/evidence/task-1-collection.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `deep6v2/`, `tests_v2/`, `pyproject.toml`
  - Pre-commit: `pytest tests_v2/ --co`

---

- [x] 2. Core Type Definitions — Frozen API Contracts

  **What to do**:
  - Create `deep6v2/types/` module with all shared types as frozen Pydantic v2 models and enums
  - `deep6v2/types/bar.py`: `FootprintBar` — OHLC, delta, total_volume, bid_volumes (dict[float, int]), ask_volumes (dict[float, int]), poc_price, poc_volume, vah, val, cvd, bar_index, timestamp, session_type (RTH/ETH)
  - `deep6v2/types/signal.py`: `SignalId` enum (52 entries: ABS_01..ABS_04, EXH_01..EXH_06, IMB_01..IMB_09, DELT_01..DELT_11, AUCT_01..AUCT_05, TRAP_01..TRAP_05, VOLP_01..VOLP_06, ENG_02..ENG_07 + 3 meta-flags: PIN_REGIME, REGIME_CHANGE, SPOOF_VETO), `SignalCategory` enum (8 scorer categories: absorption, exhaustion, imbalance, delta, volume_profile, auction, trapped, poc), `SIGNAL_TO_CATEGORY` mapping dict with EXPLICIT per-signal mapping:
    - ABS_01..ABS_04 → `absorption`
    - EXH_01..EXH_06 → `exhaustion`
    - IMB_01..IMB_09 → `imbalance`
    - DELT_01..DELT_11 → `delta`
    - AUCT_01..AUCT_05 → `auction`
    - TRAP_01..TRAP_05 → `trapped`
    - VOLP_01..VOLP_06 → `volume_profile`
    - ENG_02 (Trespass) → NOT SCORED (produces meta-context, does not participate in category voting; its output feeds risk manager depth_imbalance)
    - ENG_03 (CounterSpoof) → NOT SCORED (produces SPOOF_VETO meta-flag only; veto gate, not category vote)
    - ENG_04 (Iceberg) → `absorption` (iceberg detection is a form of hidden absorption)
    - ENG_05 (MicroProb) → NOT SCORED (produces posterior probability for informational use)
    - ENG_06 (VPContext) → `poc` (POC/VWAP/VA zone context scoring)
    - ENG_07 (SignalConfig) → NOT SCORED (regime classifier, emits REGIME_CHANGE meta-flag)
    - Signals marked NOT SCORED: produce SignalResult but their category is `None` in the mapping. Scorer skips them for category voting. They still appear in `active_signals` and may set meta-flags that trigger veto gates.
  - `Direction` enum (BULLISH=+1, BEARISH=-1, NEUTRAL=0), `SignalResult` (signal_id, direction, strength: float 0-1, detail: str, price: float, flag_bit: int)
  - `deep6v2/types/signal.py`: `SignalFlagBits` — 64-bit ulong bit assignments. NOTE: The C# `SignalFlagBits.cs` uses assignments through bit 57 with reserved gaps (not contiguous 0-54). The Python implementation must match the EXACT C# bit positions (read `SignalFlagBits.cs:163-208` for the canonical layout). Do NOT assume contiguous 0-N assignment — copy the C# bit positions verbatim.
  - `deep6v2/types/scoring.py`: `SignalTier` enum (TYPE_A, TYPE_B, TYPE_C, QUIET), `ScorerResult` (tier, raw_score, final_score, category_scores: dict[str, float], category_count: int, confluence_mult: float, zone_bonus: float, gex_mult: float, agreement_mult: float, ib_mult: float, vpin_mult: float, midday_blocked: bool, active_signals: list[SignalResult], veto_reasons: list[str], e10_agreement: bool | None, e10_caution: bool)
  - `deep6v2/types/dom.py`: `DOMLevel` (price, size, order_count), `DOMSnapshot` (bids: list[DOMLevel], asks: list[DOMLevel], best_bid, best_ask, timestamp), `DOMUpdate` (side, price, size, action)
  - `deep6v2/types/execution.py`: `TradeState` enum (IDLE, WATCHING, ARMED, PENDING_ENTRY, IN_POSITION, EXITING, CLOSED), `TradeTransition` enum (T1..T11), `OrderSide` enum (BUY, SELL), `OrderType` enum (MARKET, LIMIT, STOP), `TradeSetup` (entry_price, stop_price, target_price, side, size, scorer_result, timestamp)
  - `deep6v2/types/session.py`: `SessionType` enum (RTH, ETH), `SessionContext` — shared state container: atr, cvd, vah, val, poc, current_bar, bar_history (maxlen=50), price_history, cvd_history, delta_history, poc_history, vol_history, imbalance_history (all maxlen=50), session_type, session_open_bar_index, e10_direction (Direction | None = None), e10_strength (float = 0.0), e10_stale (bool = True) — E10 fields set by Kronos pipeline (Wave 6), defaulting to None/stale until Kronos is active
  - `deep6v2/types/interfaces.py`: `ISignalDetector` protocol (on_bar(FootprintBar, SessionContext) → list[SignalResult]), `IDepthConsumingDetector` protocol (on_depth(DOMSnapshot)), `IAbsorptionZoneReceiver` protocol (mark_absorption_zone(price, direction, strength))
  - Write RED tests for all types: construction, serialization, immutability, enum coverage
  - Make tests GREEN

  **Must NOT do**:
  - Do not make types mutable (use frozen=True for Pydantic models where appropriate)
  - Do not add methods to type classes — these are pure data containers
  - Do not add any optional fields without explicit defaults
  - Do not deviate from the 52-signal taxonomy: ABS(4) + EXH(6) + IMB(9) + DELT(11) + AUCT(5) + TRAP(5) + VOLP(6) + ENG(6) = 52 signals + 3 meta-flags (PIN_REGIME, REGIME_CHANGE, SPOOF_VETO) = 55 `SignalId` enum entries. `SignalFlagBits` maps these 55 entries to unique bit positions (0-54). Any reserved/extension bits in the C# `SignalFlagBits.cs` beyond these 55 should be included as reserved constants in `SignalFlagBits` but NOT as `SignalId` enum entries.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3-6)
  - **Blocks**: ALL subsequent tasks (Wave 2, 3, 4, 5, 6, 7, 8, 9) — this is the API contract
  - **Blocked By**: Task 1 (needs package structure)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs` — Canonical 64-bit signal bit assignments (MUST MATCH)
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs` — SignalResult shape
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs` — FootprintBar shape
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` — SessionContext rolling histories and fields
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/ISignalDetector.cs` — Detector interface contract
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/SignalTier.cs` — Tier thresholds (A≥80, B≥72, C≥50)
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerResult.cs` — ScorerResult shape
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/TradeSetupState.cs` — Trade setup lifecycle

  **API/Type References**:
  - `deep6/state/footprint.py` — Python reference FootprintBar implementation
  - `deep6/signals/flags.py` — Python reference signal flag definitions
  - `deep6/scoring/scorer.py` — Python reference ScorerResult shape

  **External References**:
  - Pydantic v2 frozen models: https://docs.pydantic.dev/latest/concepts/models/#frozen-models

  **WHY Each Reference Matters**:
  - `SignalFlagBits.cs` — Bit assignments must be identical for cross-system parity testing
  - `SessionContext.cs` — Rolling history maxlen=50 is battle-tested; don't change
  - `ISignalDetector.cs` — Interface contract determines Wave 3 parallelism; must be finalized here
  - `SignalTier.cs` — Tier thresholds (80/72/50) are R3-optimized; must match exactly

  **Acceptance Criteria**:

  - [ ] All 52 signal IDs present in SignalId enum (+ 3 meta-flags = 55 total entries)
  - [ ] SIGNAL_TO_CATEGORY mapping covers all 52 signal IDs → 8 scorer categories or None (ENG_02, ENG_03, ENG_05, ENG_07 map to None = not scored)
  - [ ] 8 categories present in SignalCategory enum
  - [ ] SignalFlagBits matches C# reference bit positions verbatim (NOT contiguous 0-54; matches `SignalFlagBits.cs:163-208` exact layout with gaps and reserved bits)
  - [ ] FootprintBar, SignalResult, ScorerResult constructable with valid data
  - [ ] SessionContext holds 6 rolling histories with maxlen=50
  - [ ] ISignalDetector and IDepthConsumingDetector protocols defined
  - [ ] IAbsorptionZoneReceiver protocol defined (cross-detector wiring)
  - [ ] All types JSON-serializable via Pydantic
  - [ ] Type tests pass: `pytest tests_v2/types/`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: All 52 signal IDs present (+ 3 meta-flags)
    Tool: Bash (python)
    Preconditions: Package installed
    Steps:
      1. Run: python -c "from deep6v2.types.signal import SignalId; print(len(SignalId))"
      2. Assert output is "55" (52 signal IDs + 3 meta-flags: PIN_REGIME, REGIME_CHANGE, SPOOF_VETO)
    Expected Result: Exactly 55 SignalId entries (52 signals + 3 meta-flags)
    Failure Indicators: Count mismatch, missing signal IDs
    Evidence: .sisyphus/evidence/task-2-signal-count.txt

  Scenario: FootprintBar serialization round-trip
    Tool: Bash (python)
    Preconditions: Package installed
    Steps:
      1. Create FootprintBar with: open=21450.0, high=21475.25, low=21425.0, close=21462.50, delta=150, total_volume=5000, poc_price=21450.0
      2. Serialize to JSON via .model_dump_json()
      3. Deserialize back via FootprintBar.model_validate_json()
      4. Assert all fields match original
    Expected Result: Round-trip produces identical object
    Failure Indicators: Serialization error, field mismatch
    Evidence: .sisyphus/evidence/task-2-roundtrip.txt

  Scenario: SignalFlagBits parity with C# reference
    Tool: Bash (python)
    Preconditions: Package installed
    Steps:
      1. Import SignalFlagBits
      2. Verify ABS_01 = 1 << 0, ABS_02 = 1 << 1, etc.
      3. Verify no bit collisions (all values unique)
      4. Verify total bit count matches C# reference
    Expected Result: All bit assignments match C# SignalFlagBits.cs
    Failure Indicators: Bit collision, wrong assignment
    Evidence: .sisyphus/evidence/task-2-flagbits.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `deep6v2/types/`
  - Pre-commit: `pytest tests_v2/types/`

---

- [x] 3. Configuration System — Pydantic v2 Settings

  **What to do**:
  - Create `deep6v2/config/` module with hierarchical Pydantic v2 Settings models
  - `deep6v2/config/rithmic.py`: `RithmicConfig` — uri, username, password, system_name, app_name, gateway (default: test env wss://rituz00100.rithmic.com), reconnect_attempts, reconnect_backoff_base
  - `deep6v2/config/signals.py`: `SignalConfig` — per-category thresholds matching `ninjatrader/Custom/AddOns/DEEP6/Detectors/` defaults (imbalance_ratio=3.0, absorption_wick_pct=0.3, exhaustion_zero_threshold=0, etc.)
  - `deep6v2/config/scoring.py`: `ScoringConfig` — R3 category weights (absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3, volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0), confluence_multiplier=1.25, ib_multiplier=1.15, midday_block_start_bar=60, midday_block_end_bar=210 (10:30-13:00 ET as bar indices from 9:30 open), type_a_threshold=80, type_b_threshold=72, type_c_threshold=50
  - `deep6v2/config/execution.py`: `ExecutionConfig` — max_contracts=2, max_trades_per_session=10, daily_loss_cap_dollars=500, rtth_start="09:30", rth_end="16:00", confirmation_delay_bars=1, dry_run=True (default)
  - `deep6v2/config/app.py`: `AppConfig` — composes all sub-configs, loads from `.env` file and environment variables, `AppConfig.from_env()` factory
  - `deep6v2/config/kronos.py`: `KronosConfig` — model_name="NeoQuasar/Kronos-small", context_length=512, inference_timeout_ms=2000, use_gpu=False, thread_pool_size=1
  - Write RED tests: config loads from env vars, defaults are correct, validation catches invalid values
  - Make tests GREEN

  **Must NOT do**:
  - Do not change R3 category weights from the values above
  - Do not make dry_run default to False — safety first
  - Do not hardcode AMP Futures credentials — use env vars only

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-2, 4-6)
  - **Blocks**: Tasks 7-12 (need config models)
  - **Blocked By**: Task 1 (needs package structure)

  **References**:

  **Pattern References**:
  - `deep6/config.py` — Existing Python config pattern (Config.from_env())
  - `deep6/engines/signal_config.py` — Existing signal threshold defaults
  - `ninjatrader/backtests/results/round3/FINAL-CONFIG.json` — R3 entry/exit parameters (stop_ticks, target_ticks, breakeven, scale_out, blackout window)

  **External References**:
  - Pydantic Settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/

  **WHY Each Reference Matters**:
  - `ConfluenceScorer.cs:59-66` — R3 category weights are the canonical optimized values; must copy exactly (absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3, volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0)
  - `FINAL-CONFIG.json` — R3 entry/exit parameters (stop_ticks=20, target_ticks=40, entry_threshold=40)
  - `signal_config.py` — Signal thresholds (imbalance_ratio, absorption_wick_pct) are calibrated values

  **Acceptance Criteria**:

  - [ ] `AppConfig.from_env()` loads successfully with only `.env` file present
  - [ ] All R3 category weights match `ConfluenceScorer.cs:59-66` values exactly (absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3, volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0)
  - [ ] `dry_run` defaults to `True`
  - [ ] Invalid config values (negative thresholds, empty URI) raise ValidationError
  - [ ] Config tests pass: `pytest tests_v2/config/`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Config loads with defaults
    Tool: Bash (python)
    Preconditions: No environment variables set for deep6v2
    Steps:
      1. Run: python -c "from deep6v2.config.app import AppConfig; c = AppConfig(); print(c.scoring.absorption_weight, c.execution.dry_run)"
      2. Assert output: "20.0 True"
    Expected Result: R3 absorption weight = 20.0, dry_run = True
    Failure Indicators: Wrong default, ValidationError
    Evidence: .sisyphus/evidence/task-3-defaults.txt

  Scenario: Invalid config rejected
    Tool: Bash (python)
    Preconditions: Package installed
    Steps:
      1. Run: python -c "from deep6v2.config.scoring import ScoringConfig; ScoringConfig(type_a_threshold=-1)"
      2. Assert raises ValidationError
    Expected Result: ValidationError raised for negative threshold
    Failure Indicators: Config created with invalid value
    Evidence: .sisyphus/evidence/task-3-validation.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `deep6v2/config/`
  - Pre-commit: `pytest tests_v2/config/`

---

- [x] 4. Test Infrastructure + Fixture Loading

  **What to do**:
  - Create `tests_v2/conftest.py` with shared pytest fixtures
  - Create `tests_v2/fixtures/` directory and ADAPT (not blindly copy) test fixtures from `ninjatrader/tests/fixtures/`
  - **Adaptation rules** (NT8 fixtures use old conventions that must be translated):
    - Signal IDs: translate NT8 format (`IMB-03-T3`, `POC-02`) → new `SignalId` enum format (`IMB_03`, mapped through `SIGNAL_TO_CATEGORY`)
    - Bar indices: translate old midday block values (240-330) → corrected values (60-210, minutes since 9:30 RTH open)
    - POC signals: map old `POC-*` signal IDs to `ENG_06` (VPContext detector handles POC/VA context)
    - Scorer categories: ensure fixture category names match scorer's 8 categories (e.g., `volume_profile` not `vol_patterns`)
  - **Source of truth**: The v2 type system (Task 2) is authoritative. Fixtures must conform to it, not the other way around. NT8 fixtures provide the TEST DATA (FootprintBar values, volumes, prices) but signal IDs and bar indices must be translated to v2 conventions.
  - Fixtures needed: **at least 1 per individual signal variant** (e.g., ABS_01.json, ABS_02.json, ..., ENG_07.json — 52 signal fixture files minimum), each containing a FootprintBar JSON + SessionContext JSON + expected SignalResult JSON with signal_id, direction, strength (using v2 SignalId enum values). Additionally, 1 composite fixture per category (8 total) containing a bar that triggers multiple signals in that category simultaneously.
  - Create 5 scoring scenario fixtures: `quiet-zero-signals.json`, `midday-block.json` (bar_index=120, in 60-210 range), `type-c-suppressed.json`, `type-b-no-zone.json`, `type-a-all-categories.json` — all using v2 bar indices and SignalId format
  - Create `tests_v2/fixtures/loader.py` — utility to load fixture JSON into Pydantic types
  - Create `tests_v2/conftest.py` fixtures: `sample_footprint_bar()`, `sample_session_context()`, `sample_dom_snapshot()`, `synthetic_session()` (generates 390 bars of RTH data)
  - Write RED test: fixture loading works, all fixture files parseable
  - Make tests GREEN

  **Must NOT do**:
  - Do not invent fixture data from scratch — adapt from these sources (in priority order):
    1. `ninjatrader/tests/fixtures/` — primary source for price/volume test data (translate signal IDs and bar indices to v2 conventions)
    2. `ninjatrader/tests/Detectors/*.cs` — test files contain inline test data (extract input values and expected outputs)
    3. `ninjatrader/docs/SIGNALS.md` — algorithm descriptions with example thresholds (construct fixtures from documented examples)
    4. `deep6/engines/*.py` — Python reference test data in existing `tests/` directory
  - For signals without existing fixture data (e.g., ENG-07 regime change), construct minimal fixtures from the algorithm description with realistic NQ values
  - Do not use random data in fixtures — use deterministic, reproducible values

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Creating 52+ individual signal fixtures by adapting from NT8 test data requires understanding each signal's algorithm and expected outputs
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2-3, 5-6, after Task 1)
  - **Blocks**: Tasks 13-20 (signal detectors need fixtures)
  - **Blocked By**: Task 2 (needs type definitions for deserialization)

  **References**:

  **Pattern References**:
  - `ninjatrader/tests/fixtures/` — NT8 JSON test fixtures (source for price/volume TEST DATA; signal IDs and bar indices must be adapted to v2 conventions)
  - `tests/conftest.py` — Existing Python test fixture patterns
  - `tests/test_data_factory.py` — Synthetic data generation patterns

  **WHY Each Reference Matters**:
  - `ninjatrader/tests/fixtures/` — Provide verified price/volume test data from R3 optimization. Signal IDs and bar indices must be adapted to v2 `SignalId` enum and corrected midday block (60-210). The v2 type system is authoritative.
  - `tests/conftest.py` — Shows the session simulation patterns already proven

  **Acceptance Criteria**:

  - [ ] At least 52 signal fixture files (1 per signal variant: ABS_01.json through ENG_07.json) + 8 composite category fixtures in `tests_v2/fixtures/signals/`
  - [ ] 5 scoring scenario fixtures in `tests_v2/fixtures/scoring/`
  - [ ] Fixture loader successfully deserializes all fixtures into Pydantic types
  - [ ] `conftest.py` provides `sample_footprint_bar`, `sample_session_context`, `sample_dom_snapshot` fixtures
  - [ ] `pytest tests_v2/ --co` collects fixture tests

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Fixture loading works
    Tool: Bash (pytest)
    Preconditions: Fixtures ported from NT8
    Steps:
      1. Run: pytest tests_v2/test_fixtures.py -v
      2. Assert all fixture load tests pass
      3. Assert each fixture produces valid Pydantic type instances
    Expected Result: All fixture files load and validate
    Failure Indicators: JSON parse error, Pydantic validation error, missing fixture file
    Evidence: .sisyphus/evidence/task-4-fixtures.txt

  Scenario: Scoring scenario fixtures complete
    Tool: Bash (python)
    Preconditions: Scoring fixtures created
    Steps:
      1. Run: python -c "import json, pathlib; files = list(pathlib.Path('tests_v2/fixtures/scoring').glob('*.json')); print(len(files), [f.stem for f in files])"
      2. Assert 5 files present with expected names
    Expected Result: 5 scoring scenario fixture files
    Failure Indicators: Missing files, wrong names
    Evidence: .sisyphus/evidence/task-4-scoring-fixtures.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `tests_v2/`
  - Pre-commit: `pytest tests_v2/ --co`

---

- [x] 5. Clock Abstraction — WallClock + EventClock

  **What to do**:
  - Create `deep6v2/clock.py` with abstract `Clock` protocol and two implementations
  - `Clock` protocol: `now() → datetime`, `sleep(seconds) → Awaitable`, `is_rth(dt) → bool`, `session_bar_index(dt) → int`
  - `WallClock`: Uses real `datetime.now(tz=ZoneInfo("America/New_York"))` for live trading
  - `EventClock`: Tracks time via injected events for replay. `advance(dt)` sets the current time.
  - RTH detection: 9:30 ET to 16:00 ET, Monday-Friday, excluding US market holidays
  - Bar index calculation: (minutes since 9:30 ET open), used for midday block (60-210 = 10:30-13:00 ET) and IB multiplier (0-59)
  - Write RED tests: WallClock returns current time, EventClock advances correctly, RTH detection at boundaries (9:29:59 = ETH, 9:30:00 = RTH, 16:00:01 = ETH), bar index at 10:30 = 60
  - Make tests GREEN

  **Must NOT do**:
  - Do not use `time.time()` anywhere — all time through Clock protocol
  - Do not hardcode timezone — use ZoneInfo("America/New_York")

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-4, 6)
  - **Blocks**: Tasks 7, 8, 10 (connection manager, DOM, bar builder need clock)
  - **Blocked By**: Task 1 (needs package structure)

  **References**:

  **Pattern References**:
  - `deep6/backtest/clock.py` — Existing WallClock + EventClock implementations
  - `deep6/state/session.py` — RTH/ETH detection and session boundary logic

  **WHY Each Reference Matters**:
  - `clock.py` — Proven clock abstraction; same interface, clean room implementation
  - `session.py` — RTH boundary logic handles DST correctly via zoneinfo

  **Acceptance Criteria**:

  - [ ] WallClock.now() returns timezone-aware datetime in America/New_York
  - [ ] EventClock.advance(dt) correctly updates internal time
  - [ ] is_rth() returns True at exactly 9:30:00 ET, False at 9:29:59 ET and 16:00:01 ET
  - [ ] session_bar_index() returns 0 at 9:30, 59 at 10:29, 60 at 10:30, 240 at 13:30
  - [ ] Clock tests pass: `pytest tests_v2/test_clock.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: RTH boundary detection
    Tool: Bash (pytest)
    Preconditions: Package installed
    Steps:
      1. Run: pytest tests_v2/test_clock.py::test_rth_boundaries -v
      2. Assert: 9:29:59 ET → False (ETH), 9:30:00 ET → True (RTH), 16:00:00 ET → True, 16:00:01 ET → False
    Expected Result: All boundary conditions correct
    Failure Indicators: Wrong RTH classification at boundaries
    Evidence: .sisyphus/evidence/task-5-rth.txt

  Scenario: Bar index calculation
    Tool: Bash (pytest)
    Preconditions: Package installed
    Steps:
      1. Run: pytest tests_v2/test_clock.py::test_bar_index -v
      2. Assert: 9:30 → 0, 10:29 → 59, 10:30 → 60, 13:30 → 240, 15:59 → 389
    Expected Result: Bar indices match minute offset from 9:30
    Failure Indicators: Wrong index calculation
    Evidence: .sisyphus/evidence/task-5-barindex.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `deep6v2/clock.py`
  - Pre-commit: `pytest tests_v2/test_clock.py`

---

- [x] 6. Logging Foundation — structlog + JSON

  **What to do**:
  - Create `deep6v2/logging.py` with structlog configuration
  - Configure structlog processors: add_log_level, TimeStamper(fmt="iso"), JSONRenderer for production, ConsoleRenderer for development
  - Add context binding: `bar_index`, `session_id`, `signal_category` as common bound vars
  - Create `configure_logging(dev_mode: bool = False)` function called at startup
  - Create per-module logger factory: `get_logger(module_name: str) → structlog.BoundLogger`
  - Write RED test: logger outputs JSON with expected fields
  - Make test GREEN

  **Must NOT do**:
  - Do not use stdlib `logging` directly — all logging through structlog
  - Do not use print() for any diagnostic output

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1-5)
  - **Blocks**: All subsequent tasks (they use structured logging)
  - **Blocked By**: Task 1 (needs package structure)

  **References**:

  **Pattern References**:
  - `deep6/engines/live_pipeline.py:1-30` — Existing structlog usage pattern

  **External References**:
  - structlog docs: https://www.structlog.org/en/stable/

  **WHY Each Reference Matters**:
  - `live_pipeline.py` — Shows the existing structlog pattern; clean room should match log field conventions

  **Acceptance Criteria**:

  - [ ] `configure_logging(dev_mode=True)` produces human-readable console output
  - [ ] `configure_logging(dev_mode=False)` produces JSON output with timestamp, level, event, module
  - [ ] `get_logger("signals.absorption")` returns a bound logger with module context
  - [ ] Logging tests pass: `pytest tests_v2/test_logging.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: JSON logging output
    Tool: Bash (python)
    Preconditions: Package installed
    Steps:
      1. Run: python -c "from deep6v2.logging import configure_logging, get_logger; configure_logging(dev_mode=False); log = get_logger('test'); log.info('test_event', bar_index=42)"
      2. Capture stderr output
      3. Assert JSON contains: "event": "test_event", "bar_index": 42, "module": "test"
    Expected Result: Valid JSON log line with expected fields
    Failure Indicators: Non-JSON output, missing fields
    Evidence: .sisyphus/evidence/task-6-json-log.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(foundation): scaffold deep6v2 package with types, config, clock, logging`
  - Files: `deep6v2/logging.py`
  - Pre-commit: `pytest tests_v2/test_logging.py`

---

### Wave 2: Data Pipeline

- [x] 7. async-rithmic Connection Manager + FreezeGuard

  **What to do**:
  - Create `deep6v2/data/rithmic_client.py` — async-rithmic connection lifecycle manager
  - Implement connection states: DISCONNECTED → CONNECTING → CONNECTED → FROZEN → RECONNECTING
  - FreezeGuard state machine: detect connection loss → freeze all DOM/bar processing → reconnect with exponential backoff + jitter → reconcile position state → unfreeze only after reconciliation passes
  - Subscribe to NQ L2 DOM (MarketDepthService) and trades (TickerPlantService) via async-rithmic
  - Callback routing: DOM updates → DOMState (Task 8), trade ticks → BarBuilder (Task 10)
  - Reconnection with configurable backoff (ReconnectionSettings from async-rithmic)
  - Graceful shutdown: unsubscribe, close WebSocket, clean state
  - Write RED tests: connection state transitions, freeze on disconnect, reject DOM callbacks when frozen, unfreeze only after reconciliation
  - Make tests GREEN (using mock Rithmic connection)

  **Must NOT do**:
  - Do not process any DOM or trade data while in FROZEN state
  - Do not unfreeze without position reconciliation
  - Do not use synchronous I/O — all async

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8-12)
  - **Blocks**: Tasks 11, 13-20, 28, 35
  - **Blocked By**: Tasks 2, 3, 5, 6 (types, config, clock, logging)

  **References**:

  **Pattern References**:
  - `deep6/state/connection.py` — Existing FreezeGuard + SessionManager lifecycle (proven pattern)
  - `deep6/data/rithmic.py` — Existing async-rithmic connection and DOM subscription pattern

  **External References**:
  - async-rithmic docs: https://github.com/rundef/async_rithmic — RithmicClient, MarketDepthService, TickerPlantService
  - async-rithmic ReconnectionSettings: exponential backoff with jitter

  **WHY Each Reference Matters**:
  - `connection.py` — FreezeGuard pattern handles the critical edge case of reconnection during position; position reconciliation before unfreeze is non-negotiable
  - `rithmic_client.py` — Shows the async-rithmic API usage for DOM + trade subscriptions

  **Acceptance Criteria**:

  - [ ] Connection manager transitions through DISCONNECTED → CONNECTING → CONNECTED
  - [ ] FreezeGuard triggers on connection loss, blocks all callbacks
  - [ ] Reconnection uses exponential backoff with jitter
  - [ ] Position reconciliation required before unfreeze
  - [ ] Graceful shutdown unsubscribes and closes cleanly
  - [ ] Tests pass: `pytest tests_v2/data/test_rithmic_client.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: FreezeGuard blocks callbacks when frozen
    Tool: Bash (pytest)
    Preconditions: Mock Rithmic connection
    Steps:
      1. Create connection manager, connect (mock)
      2. Simulate disconnect → assert state = FROZEN
      3. Send DOM update → assert it is rejected/queued
      4. Simulate reconnect → assert state still FROZEN (no reconciliation yet)
      5. Call reconcile_position() → assert state = CONNECTED
      6. Send DOM update → assert it is processed
    Expected Result: No data processed during FROZEN state
    Failure Indicators: DOM updates processed while frozen, unfreeze without reconciliation
    Evidence: .sisyphus/evidence/task-7-freezeguard.txt

  Scenario: Reconnection with backoff
    Tool: Bash (pytest)
    Preconditions: Mock Rithmic connection
    Steps:
      1. Simulate disconnect
      2. Simulate 3 failed reconnection attempts
      3. Assert backoff delays increase (e.g., 1s, 2s, 4s)
      4. Simulate successful reconnection on 4th attempt
      5. Assert state = FROZEN (awaiting reconciliation)
    Expected Result: Exponential backoff applied, state correct after reconnect
    Failure Indicators: No backoff, immediate reconnect flood
    Evidence: .sisyphus/evidence/task-7-reconnect.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `deep6v2/data/rithmic_client.py`
  - Pre-commit: `pytest tests_v2/data/test_rithmic_client.py`

---

- [x] 8. DOM State Management — Pre-allocated Arrays

  **What to do**:
  - Create `deep6v2/state/dom.py` — zero-allocation DOM state for 1,000+ callbacks/sec
  - Pre-allocate bid and ask arrays: `array.array('d')` for 40 levels each (covering NQ price range)
  - Price-to-index mapping: `index = int((price - base_price) / tick_size)` where tick_size = 0.25 for NQ
  - `update_level(side, price, size)` — O(1) array index update, no dict lookup
  - `get_best_bid()`, `get_best_ask()` — scan from top/bottom of pre-allocated array
  - `snapshot()` — create DOMSnapshot from current state (for depth-consuming detectors)
  - `reset()` — zero all arrays (on session reset or contract change)
  - `depth_imbalance(levels=5)` — ratio of bid/ask size at top N levels
  - Write RED tests: update_level O(1), snapshot matches expected DOMSnapshot, depth_imbalance calculation, 1000-update benchmark < 1ms
  - Make tests GREEN

  **Must NOT do**:
  - Do not use dict for price→size mapping in the hot path
  - Do not allocate memory per callback — pre-allocate all arrays at init
  - Do not use locks — single event loop owns this state

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9-12)
  - **Blocks**: Tasks 9, 10, 13-20 (signals need DOM state)
  - **Blocked By**: Tasks 2, 5 (types, clock)

  **References**:

  **Pattern References**:
  - `deep6/state/dom.py` — Existing pre-allocated array DOM implementation (proven at 1,000 cb/sec)

  **WHY Each Reference Matters**:
  - `dom.py` — The `array.array('d')` approach is battle-tested; `numpy` alternative was considered but `array.array` has lower overhead for single-element updates

  **Acceptance Criteria**:

  - [ ] Pre-allocated arrays for 40 bid + 40 ask levels
  - [ ] `update_level()` is O(1) array index operation
  - [ ] `snapshot()` produces valid DOMSnapshot with correct best_bid/best_ask
  - [ ] `depth_imbalance(5)` returns correct bid/ask ratio for top 5 levels
  - [ ] Benchmark: 1,000 `update_level()` calls < 1ms wall clock
  - [ ] Tests pass: `pytest tests_v2/state/test_dom.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: DOM update performance
    Tool: Bash (pytest)
    Preconditions: Package installed
    Steps:
      1. Run: pytest tests_v2/state/test_dom.py::test_update_benchmark --benchmark-only
      2. Assert: 1,000 update_level() calls complete in < 1ms
    Expected Result: Sub-millisecond for 1,000 updates
    Failure Indicators: Benchmark exceeds 1ms
    Evidence: .sisyphus/evidence/task-8-benchmark.txt

  Scenario: Snapshot accuracy
    Tool: Bash (pytest)
    Preconditions: DOM populated with known levels
    Steps:
      1. Set bid levels: 21450.00=100, 21449.75=50, 21449.50=200
      2. Set ask levels: 21450.25=80, 21450.50=120
      3. Call snapshot()
      4. Assert best_bid=21450.00, best_ask=21450.25
      5. Assert depth_imbalance(3) = (100+50+200) / (80+120+0) = 1.75
    Expected Result: Snapshot matches manually calculated values
    Failure Indicators: Wrong best_bid/best_ask, wrong imbalance ratio
    Evidence: .sisyphus/evidence/task-8-snapshot.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `deep6v2/state/dom.py`
  - Pre-commit: `pytest tests_v2/state/test_dom.py`

---

- [x] 9. Aggressor Verification + Tick Classification

  **What to do**:
  - Create `deep6v2/data/tick_classifier.py` — aggressor classification from raw Rithmic ticks
  - Aggressor logic: compare last trade price vs best bid/ask at time of trade
    - `price >= best_ask` → BUY aggressor (buyer lifting the offer)
    - `price <= best_bid` → SELL aggressor (seller hitting the bid)
    - `best_bid < price < best_ask` → UNSPECIFIED (inside spread)
  - Aggressor verification gate (D-03): UNSPECIFIED ticks are counted for total volume but NOT classified as buy/sell in footprint bar
  - `ClassifiedTick` type: price, size, timestamp, aggressor (BUY/SELL/UNSPECIFIED)
  - Feed verified ticks to BarBuilder (Task 10)
  - Write RED tests: BUY/SELL/UNSPECIFIED classification at various price vs BBO positions, gate rejects UNSPECIFIED for directional counting
  - Make tests GREEN

  **Must NOT do**:
  - Do not classify UNSPECIFIED ticks as either BUY or SELL — this is the first safety checkpoint
  - Do not accumulate UNSPECIFIED in bid_volumes or ask_volumes

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-8, 10-12)
  - **Blocks**: Task 10 (bar builder needs classified ticks)
  - **Blocked By**: Tasks 2, 8 (types, DOM state for BBO reference)

  **References**:

  **Pattern References**:
  - `deep6/data/rithmic.py` — Existing tick classification logic (search for aggressor/classify)
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs:OnMarketData()` — NT8 aggressor classification via MarketDataType

  **WHY Each Reference Matters**:
  - Both references implement the same D-03 gate; C# uses NT8's MarketDataType enum, Python uses price vs BBO comparison. The Python approach works with raw Rithmic ticks.

  **Acceptance Criteria**:

  - [ ] BUY classification when price >= best_ask
  - [ ] SELL classification when price <= best_bid
  - [ ] UNSPECIFIED when price is inside spread
  - [ ] UNSPECIFIED ticks contribute to total_volume but NOT to bid_volumes/ask_volumes
  - [ ] Tests pass: `pytest tests_v2/data/test_tick_classifier.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Aggressor classification at boundary
    Tool: Bash (pytest)
    Preconditions: best_bid=21450.00, best_ask=21450.25
    Steps:
      1. Trade at 21450.25 → assert BUY
      2. Trade at 21450.00 → assert SELL
      3. Trade at 21450.125 → assert UNSPECIFIED
      4. Trade at 21450.50 → assert BUY (above ask)
      5. Trade at 21449.75 → assert SELL (below bid)
    Expected Result: All classifications correct at boundary conditions
    Failure Indicators: Wrong classification
    Evidence: .sisyphus/evidence/task-9-classify.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `deep6v2/data/tick_classifier.py`
  - Pre-commit: `pytest tests_v2/data/test_tick_classifier.py`

---

- [x] 10. Bar Builder (1m, 5m) + Session Management

  **What to do**:
  - Create `deep6v2/data/bar_builder.py` — dual-timeframe bar accumulator
  - Accumulates ClassifiedTick events into FootprintBar objects
  - 1-minute primary bars: boundary at minute marks (9:30:00, 9:31:00, ...)
  - 5-minute secondary bars: aggregated from 5 consecutive 1-minute bars
  - On bar close: finalize FootprintBar (compute POC, VAH, VAL, delta, CVD, total_volume)
  - POC: price level with highest total volume (bid + ask)
  - Value Area: 70% of volume centered on POC (ascending from POC outward)
  - Delta: sum of (ask_volume - bid_volume) across all levels
  - CVD: cumulative delta across session
  - RTH gating: only build bars during RTH (9:30-16:00 ET). ETH ticks: accumulate for pre-market context but don't feed to signals.
  - Session reset: clear all accumulators, reset CVD, reset bar_index at RTH open (9:30 ET)
  - Update SessionContext rolling histories (price, cvd, delta, poc, vol, imbalance — all maxlen=50) on each bar close
  - Emit `on_bar_close(FootprintBar, SessionContext)` callback to DetectorRegistry
  - Write RED tests: bar boundaries align to minute marks, POC/VAH/VAL calculation, delta/CVD accumulation, RTH gating, session reset
  - Make tests GREEN

  **Must NOT do**:
  - Do not process pre-9:30 or post-16:00 ticks for signal evaluation
  - Do not reset CVD mid-session — only at RTH open
  - Do not use wall clock for bar boundaries — use Clock abstraction

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-9, 11-12)
  - **Blocks**: Tasks 13-20 (signals need FootprintBar), Tasks 28-29 (Kronos needs OHLCV)
  - **Blocked By**: Tasks 2, 5, 8, 9 (types, clock, DOM state, tick classifier)

  **References**:

  **Pattern References**:
  - `deep6/data/bar_builder.py` — Existing dual-timeframe bar builder with session management
  - `deep6/state/footprint.py` — FootprintBar finalization (POC, VAH, VAL calculation)
  - `deep6/state/session.py` — Session lifecycle (open, close, reset, RTH detection)

  **WHY Each Reference Matters**:
  - `bar_builder.py` — The dual-timeframe approach (1m primary, 5m secondary) is proven
  - `footprint.py` — Value Area calculation (70% of volume centered on POC) is calibrated

  **Acceptance Criteria**:

  - [ ] 1-minute bars close at minute boundaries (9:30:59 → close bar, 9:31:00 → new bar)
  - [ ] 5-minute bars aggregate 5 consecutive 1-minute bars
  - [ ] POC = price level with highest total volume
  - [ ] Value Area contains ≥70% of total volume, centered on POC
  - [ ] Delta = Σ(ask_vol - bid_vol) per bar
  - [ ] CVD accumulates across session, resets at RTH open
  - [ ] RTH gating: pre-9:30 and post-16:00 ticks rejected from signal pipeline
  - [ ] SessionContext updated with rolling histories (maxlen=50) on each bar close
  - [ ] Tests pass: `pytest tests_v2/data/test_bar_builder.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Bar boundary alignment
    Tool: Bash (pytest)
    Preconditions: EventClock, synthetic ticks
    Steps:
      1. Feed ticks at 9:30:00, 9:30:30, 9:30:59 (all bar 0)
      2. Feed tick at 9:31:00 (triggers bar 0 close, starts bar 1)
      3. Assert bar 0 contains 3 ticks, bar 1 starts empty then gets 1 tick
      4. Assert bar 0 OHLC matches expected values
    Expected Result: Bar boundaries at exact minute marks
    Failure Indicators: Tick assigned to wrong bar, off-by-one boundary
    Evidence: .sisyphus/evidence/task-10-boundary.txt

  Scenario: POC and Value Area calculation
    Tool: Bash (pytest)
    Preconditions: Synthetic footprint bar with known volume distribution
    Steps:
      1. Create bar with volumes: 21450.00=500, 21450.25=300, 21450.50=100, 21449.75=200
      2. Finalize bar
      3. Assert POC = 21450.00 (highest volume)
      4. Assert VAH and VAL contain ≥70% of total volume (1100 total, VA ≥ 770)
    Expected Result: POC correct, Value Area ≥70% volume
    Failure Indicators: Wrong POC, VA < 70%
    Evidence: .sisyphus/evidence/task-10-poc-va.txt

  Scenario: RTH gating rejects pre-market ticks
    Tool: Bash (pytest)
    Preconditions: EventClock set to 9:00 ET (pre-market)
    Steps:
      1. Feed 10 ticks at 9:00-9:29 ET
      2. Assert no bar created for signal pipeline
      3. Advance clock to 9:30:00 ET
      4. Feed tick at 9:30:00 → assert bar 0 starts
    Expected Result: Pre-market ticks rejected, first bar at 9:30
    Failure Indicators: Bar created before 9:30
    Evidence: .sisyphus/evidence/task-10-rth-gate.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `deep6v2/data/bar_builder.py`
  - Pre-commit: `pytest tests_v2/data/test_bar_builder.py`

---

- [x] 11. Rithmic Test Environment Connection Test

  **What to do**:
  - Create `tests_v2/integration/test_rithmic_connection.py` — live integration test against Rithmic test environment
  - Connect to `wss://rituz00100.rithmic.com` (free test environment) using async-rithmic
  - Subscribe to NQ front-month contract
  - Receive at least 1 DOM depth update and 1 trade tick
  - Verify DOM update has ≥5 bid levels and ≥5 ask levels
  - Verify trade tick has price > 0 and size > 0
  - Timeout: 30 seconds
  - Mark test with `@pytest.mark.integration` (skip in CI, run manually)
  - Document AMP Futures-specific setup steps (account, API mode confirmation, gateway URL) in test docstring

  **Must NOT do**:
  - Do not run this test in CI — it requires network access to Rithmic
  - Do not hardcode credentials — load from env vars (RITHMIC_USER, RITHMIC_PASSWORD, RITHMIC_SYSTEM_NAME)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-10, 12)
  - **Blocks**: Task 24 (ORDER_PLANT research spike needs connection verified)
  - **Blocked By**: Task 7 (connection manager)

  **References**:

  **Pattern References**:
  - `deep6/data/rithmic.py` — Existing Rithmic connection code
  - `tests/test_databento_live.py` — Integration test pattern with @pytest.mark.integration

  **External References**:
  - async-rithmic examples: https://github.com/rundef/async_rithmic/tree/main/examples

  **WHY Each Reference Matters**:
  - `rithmic.py` — Shows the async-rithmic API calls for subscribing to NQ DOM and trades
  - Integration test pattern — `@pytest.mark.integration` marker pattern for optional network tests

  **Acceptance Criteria**:

  - [ ] Connects to Rithmic test environment within 30 seconds
  - [ ] Receives at least 1 DOM update with ≥5 bid and ≥5 ask levels
  - [ ] Receives at least 1 trade tick with price > 0 and size > 0
  - [ ] Test marked with `@pytest.mark.integration`
  - [ ] Credentials loaded from environment variables, not hardcoded

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Rithmic test environment connection
    Tool: Bash (pytest)
    Preconditions: RITHMIC_USER, RITHMIC_PASSWORD, RITHMIC_SYSTEM_NAME env vars set
    Steps:
      1. Run: pytest tests_v2/integration/test_rithmic_connection.py -v -m integration --timeout=60
      2. Assert connection established
      3. Assert DOM data received
      4. Assert trade data received
    Expected Result: Connection, DOM subscription, and trade subscription all succeed
    Failure Indicators: Timeout, connection refused, no data received
    Evidence: .sisyphus/evidence/task-11-rithmic.txt

  Scenario: Graceful handling when credentials missing
    Tool: Bash (pytest)
    Preconditions: No RITHMIC_* env vars set
    Steps:
      1. Run: pytest tests_v2/integration/test_rithmic_connection.py -v -m integration
      2. Assert test is SKIPPED (not FAILED) with clear message
    Expected Result: Test skips with "Rithmic credentials not configured" message
    Failure Indicators: Test fails with cryptic error instead of skip
    Evidence: .sisyphus/evidence/task-11-skip.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `tests_v2/integration/test_rithmic_connection.py`
  - Pre-commit: `pytest tests_v2/ -m "not integration"`

---

- [x] 12. Event Store Schema — DuckDB + SQLite Persistence

  **What to do**:
  - Create `deep6v2/state/persistence.py` — dual-database persistence layer
  - **DuckDB** (append-only analytics): bar events, signal events, FSM transitions, execution events, scoring snapshots. Schema tables: `bars`, `signals`, `fsm_events`, `executions`, `scores`
  - **SQLite** (transactional state): session context snapshots, paper trading gate state, auction levels, configuration snapshots. Schema tables: `sessions`, `paper_gate`, `auction_levels`, `config_snapshots`
  - `EventWriter` class: async writes to DuckDB (batch insert every N events or T seconds)
  - `StateStore` class: sync writes to SQLite (immediate consistency for state)
  - `bars` table: timestamp, bar_index, open, high, low, close, delta, total_volume, poc_price, vah, val, cvd, session_id
  - `signals` table: timestamp, bar_index, signal_id, direction, strength, detail, price, session_id
  - `scores` table: timestamp, bar_index, tier, raw_score, final_score, category_scores_json, active_signal_ids, session_id
  - Write RED tests: insert/query round-trip for each table, batch insert performance
  - Make tests GREEN

  **Must NOT do**:
  - Do not use DuckDB for transactional state (key-value persistence) — use SQLite
  - Do not use SQLite for append-only analytics — use DuckDB
  - Do not block the event loop on DuckDB writes — use batched async inserts

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7-11)
  - **Blocks**: Tasks 25, 34 (execution FSM and replay need persistence)
  - **Blocked By**: Tasks 2, 3 (types, config)

  **References**:

  **Pattern References**:
  - `deep6/state/persistence.py` — Existing SQLite persistence (aiosqlite pattern)
  - `deep6/state/eventstore_schema.py` — Existing event store schema definition
  - `deep6/backtest/result_store.py` — DuckDB usage for backtest results

  **WHY Each Reference Matters**:
  - `persistence.py` — Shows aiosqlite pattern for async state persistence
  - `eventstore_schema.py` — Schema design for bar/signal/execution events
  - `result_store.py` — DuckDB batch insert pattern for analytics data

  **Acceptance Criteria**:

  - [ ] DuckDB `bars` table: insert FootprintBar → query back → all fields match
  - [ ] DuckDB `signals` table: insert SignalResult → query back → all fields match
  - [ ] SQLite `sessions` table: insert/update/query session state
  - [ ] Batch insert: 1000 bar events inserted in < 100ms
  - [ ] Tests pass: `pytest tests_v2/state/test_persistence.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: DuckDB bar event round-trip
    Tool: Bash (pytest)
    Preconditions: Temporary DuckDB file
    Steps:
      1. Insert FootprintBar with known values (open=21450.0, close=21462.50, delta=150)
      2. Query bars table for that bar_index
      3. Assert all fields match
    Expected Result: Round-trip preserves all fields exactly
    Failure Indicators: Missing fields, type conversion errors
    Evidence: .sisyphus/evidence/task-12-duckdb.txt

  Scenario: SQLite session state persistence
    Tool: Bash (pytest)
    Preconditions: Temporary SQLite file
    Steps:
      1. Create session with id="2026-05-13-RTH"
      2. Update session state (bar_count=42, cvd=150.0)
      3. Restart StateStore from same file
      4. Query session → assert state matches
    Expected Result: Session state survives restart
    Failure Indicators: State lost on restart, wrong values
    Evidence: .sisyphus/evidence/task-12-sqlite.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(data): async-rithmic connection, DOM state, bar builder, persistence`
  - Files: `deep6v2/state/persistence.py`
  - Pre-commit: `pytest tests_v2/state/test_persistence.py`

---

### Wave 3: Signal Engines (8 PARALLEL agents)

> ALL 8 tasks in this wave run simultaneously. Each agent implements one signal category
> using the frozen type contracts from Wave 1 and the FootprintBar/SessionContext from Wave 2.
> Implement from algorithm description in references — do NOT copy-paste from reference code.
> Test against JSON fixtures for correctness (±0.01 strength tolerance).

- [x] 13. Absorption Detectors — ABS-01..ABS-04

  **What to do**:
  - Create `deep6v2/signals/absorption.py` implementing ISignalDetector
  - ABS-01 Classic: wick_volume > (total_volume × absorption_wick_pct) AND |delta| < (total_volume × delta_neutrality_threshold). Strength = wick_volume / total_volume.
  - ABS-02 Passive: volume_at_extreme > vol_ema × passive_mult AND price holds (close ≠ extreme). Strength = volume_at_extreme / vol_ema.
  - ABS-03 Stopping Volume: POC in wick zone AND total_volume > vol_ema × stopping_mult AND atr_scaled_threshold. Strength = poc_volume / total_volume.
  - ABS-04 Effort vs Result: total_volume > vol_ema × effort_mult AND range < atr × effort_range_pct. Strength = volume / range ratio normalized.
  - Direction convention (LOCKED — do not deviate, matches `AbsorptionDetector.cs` and `SIGNALS.md`): absorption at HIGH wick (aggressive buyers absorbed by passive sellers at the high → upward move rejected) → signal direction = BEARISH. Absorption at LOW wick (aggressive sellers absorbed by passive buyers at the low → downward move rejected) → signal direction = BULLISH.
  - Implement IAbsorptionZoneReceiver.mark_absorption_zone() — notify any registered receivers (for ENG-04 Iceberg cross-wiring)
  - Write RED tests using absorption fixture from `tests_v2/fixtures/signals/absorption.json`
  - Make tests GREEN

  **Must NOT do**:
  - Do not modify FootprintBar or SessionContext types — they are frozen
  - Do not access DOM state — absorption is bar-only (no IDepthConsumingDetector)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 14-20
  - **Parallel Group**: Wave 3 (all 8 run simultaneously)
  - **Blocks**: Task 20 (cross-detector wiring in DetectorRegistry), Task 21 (scorer needs signals)
  - **Blocked By**: Tasks 2, 4, 10 (types, fixtures, bar builder)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — C# reference implementation (algorithm logic)
  - `deep6/engines/absorption.py` — Python reference implementation
  - `ninjatrader/docs/SIGNALS.md` — Signal specification with thresholds

  **WHY Each Reference Matters**:
  - `AbsorptionDetector.cs` — R3-optimized algorithm with VA extreme bonus; this is the canonical logic
  - `absorption.py` — Python reference; compare algorithm descriptions between C# and Python

  **Acceptance Criteria**:

  - [ ] ABS-01 through ABS-04 all implemented
  - [ ] Each returns SignalResult with correct signal_id, direction, strength (0-1)
  - [ ] IAbsorptionZoneReceiver notification emitted on absorption detection
  - [ ] All absorption fixture tests pass (±0.01 strength tolerance)
  - [ ] Tests pass: `pytest tests_v2/signals/test_absorption.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: ABS-01 Classic absorption detection
    Tool: Bash (pytest)
    Preconditions: Absorption fixture loaded
    Steps:
      1. Create FootprintBar with high wick volume at BAR LOW (low_wick_vol=400, total=1000, delta=50, sellers absorbed at low)
      2. Run AbsorptionDetector.on_bar()
      3. Assert SignalResult with signal_id=ABS_01, direction=BULLISH (low wick absorption = bullish reversal), strength≈0.4
    Expected Result: ABS-01 fires with correct direction and strength
    Failure Indicators: No signal, wrong direction, strength outside ±0.01
    Evidence: .sisyphus/evidence/task-13-abs01.txt

  Scenario: Absorption zone notification fires
    Tool: Bash (pytest)
    Preconditions: Mock IAbsorptionZoneReceiver registered
    Steps:
      1. Trigger ABS-01 detection
      2. Assert mock.mark_absorption_zone() was called with correct price and direction
    Expected Result: Cross-detector notification delivered
    Failure Indicators: Notification not fired, wrong parameters
    Evidence: .sisyphus/evidence/task-13-zone-notify.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(signals): 52 signal detectors across 8 categories with fixture parity`
  - Files: `deep6v2/signals/absorption.py`
  - Pre-commit: `pytest tests_v2/signals/test_absorption.py`

---

- [ ] 14. Exhaustion Detectors — EXH-01..EXH-06

  **What to do**:
  - Create `deep6v2/signals/exhaustion.py` implementing ISignalDetector
  - EXH-01 Zero Print: price level in bar range with 0 volume on both bid+ask sides. Direction from position in bar (top = bearish exhaustion = BEARISH, bottom = bullish exhaustion = BULLISH). Strength = 1.0 (binary).
  - EXH-02 Exhaustion Print: single-side volume at extreme > threshold × avg_row_vol. Strength = extreme_vol / avg_row_vol, capped at 1.0.
  - EXH-03 Thin Print: volume at level < 5% of max_row_vol. Strength = 1.0 - (level_vol / max_row_vol).
  - EXH-04 Fat Print: volume at level > fat_mult × avg_row_vol AND delta at level is neutral. Strength = level_vol / (fat_mult × avg_row_vol).
  - EXH-05 Fading Momentum: delta trajectory over last 3 bars diverges from price trajectory. Use linear regression slope. Strength = abs(divergence_angle) normalized.
  - EXH-06 Bid/Ask Fade: ask_vol at high < 60% of prior bar's ask_vol at high (or bid_vol at low). Strength = 1.0 - (current_vol / prior_vol).
  - Delta gate: suppress EXH signals when |barDelta| > delta_gate_threshold (bar is too one-sided for exhaustion)
  - Write RED tests using exhaustion fixture from `tests_v2/fixtures/signals/exhaustion.json`
  - Make tests GREEN

  **Must NOT do**:
  - Do not fire EXH signals when delta gate triggers (|barDelta| too high)
  - Do not modify any shared types

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13, 15-20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer)
  - **Blocked By**: Tasks 2, 4, 10 (types, fixtures, bar builder)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs` — C# reference (R3 algorithm)
  - `deep6/engines/exhaustion.py` — Python reference
  - `ninjatrader/docs/SIGNALS.md` — Signal specification

  **Acceptance Criteria**:

  - [ ] EXH-01 through EXH-06 all implemented
  - [ ] Delta gate suppresses signals when |barDelta| exceeds threshold
  - [ ] All exhaustion fixture tests pass (±0.01 strength tolerance)
  - [ ] Tests pass: `pytest tests_v2/signals/test_exhaustion.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: EXH-01 Zero Print detection
    Tool: Bash (pytest)
    Steps:
      1. Create FootprintBar with a price level at 21460.00 having 0 bid + 0 ask volume
      2. Level is at top of bar range (near high)
      3. Run ExhaustionDetector.on_bar()
      4. Assert SignalResult with signal_id=EXH_01, direction=BEARISH, strength=1.0
    Expected Result: Zero print at top → BEARISH exhaustion
    Failure Indicators: No signal, wrong direction
    Evidence: .sisyphus/evidence/task-14-exh01.txt

  Scenario: Delta gate suppresses exhaustion
    Tool: Bash (pytest)
    Steps:
      1. Create FootprintBar with zero print BUT |delta|=500 (highly one-sided)
      2. Run ExhaustionDetector.on_bar()
      3. Assert no EXH signals returned (delta gate blocks)
    Expected Result: No signal due to delta gate
    Failure Indicators: Signal fires despite high delta
    Evidence: .sisyphus/evidence/task-14-delta-gate.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(signals): 52 signal detectors across 8 categories with fixture parity`
  - Files: `deep6v2/signals/exhaustion.py`

---

- [ ] 15. Imbalance Detectors — IMB-01..IMB-09

  **What to do**:
  - Create `deep6v2/signals/imbalance.py` implementing ISignalDetector
  - IMB-01 Single: ask_vol / bid_vol >= imbalance_ratio (3.0) at any price level, or vice versa. Strength = ratio / max_ratio, capped at 1.0.
  - IMB-02 Multiple: 3+ imbalances at same price level across consecutive bars. Strength scales with count.
  - IMB-03 Stacked: T1=3, T2=5, T3=7 consecutive levels all showing imbalance. This is the highest-alpha signal (weight=25.0). Strength = tier_level / 3.
  - IMB-04 Reverse: both buy_imbalance AND sell_imbalance at same price (contested level). Strength = min(buy_ratio, sell_ratio) / imbalance_ratio.
  - IMB-05 Inverse: buy imbalance in a red (down) bar or sell imbalance in green (up) bar. Counter-trend signal. Strength = ratio / imbalance_ratio.
  - IMB-06 Oversized: ratio >= 10:1 (extreme). Strength = ratio / 10, capped at 1.0.
  - IMB-07 Consecutive: same level shows imbalance in 2+ consecutive bars. Strength = consecutive_count / 5.
  - IMB-08 Diagonal: ask[price] vs bid[price - tick_size] comparison (diagonal imbalance). Strength similar to IMB-01.
  - IMB-09 Reversal: imbalance pattern reverses direction between consecutive bars. Strength = 0.8 (fixed).
  - Record imbalance levels in SessionContext.imbalance_history for consecutive/multiple detection
  - Write RED tests using imbalance fixture
  - Make tests GREEN

  **Must NOT do**:
  - Do not change imbalance_ratio default from 3.0 without config override

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-14, 16-20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer)
  - **Blocked By**: Tasks 2, 4, 10

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs` — C# reference (9 variants)
  - `deep6/engines/imbalance.py` — Python reference
  - `ninjatrader/docs/SIGNALS.md` — IMB-01 through IMB-09 specifications

  **Acceptance Criteria**:

  - [ ] IMB-01 through IMB-09 all implemented
  - [ ] IMB-03 Stacked detects T1/T2/T3 tiers correctly (3/5/7 levels)
  - [ ] SessionContext.imbalance_history updated for multi-bar patterns
  - [ ] All imbalance fixture tests pass
  - [ ] Tests pass: `pytest tests_v2/signals/test_imbalance.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: IMB-03 Stacked T2 detection
    Tool: Bash (pytest)
    Steps:
      1. Create FootprintBar with 5 consecutive levels each showing 4:1 ask:bid ratio
      2. Run ImbalanceDetector.on_bar()
      3. Assert SignalResult with signal_id=IMB_03, strength≈0.67 (T2=5/3 tiers, normalized)
    Expected Result: Stacked T2 (5 consecutive levels) detected
    Failure Indicators: Wrong tier, wrong strength
    Evidence: .sisyphus/evidence/task-15-imb03.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/imbalance.py`

---

- [ ] 16. Delta Detectors — DELT-01..DELT-11

  **What to do**:
  - Create `deep6v2/signals/delta.py` implementing ISignalDetector
  - DELT-01 Rise/Drop: bar delta > delta_threshold (significant delta). Direction matches delta sign. Strength = |delta| / vol_ema.
  - DELT-02 Tail: delta concentrated in wick zone (last N% of bar range). Strength = wick_delta / bar_delta.
  - DELT-03 Reversal: delta flips sign between consecutive bars AND price continues same direction. Strength based on flip magnitude.
  - DELT-04 Divergence: price trending up but delta trending down over last N bars (or vice versa). Uses SessionContext.delta_history and price_history. Strength = divergence_magnitude.
  - DELT-05 CVD Flip: CVD crosses zero line. Direction = new CVD sign. Strength = 1.0 (binary event).
  - DELT-06 Trap: large delta bar followed by price reversal (trapped momentum). Strength = prior_delta magnitude.
  - DELT-07 Sweep: delta spikes then immediately mean-reverts within same bar. Strength = spike_magnitude / mean.
  - DELT-08 Slingshot: delta compressed (small) then explodes on next bar. Strength = explosion_ratio.
  - DELT-09 Session Min/Max: delta reaches session extreme (min or max CVD). Binary detection. Strength = 1.0.
  - DELT-10 CVD Polyfit Divergence: linear regression (polyfit degree=1) of CVD vs price over last 10 bars. Strength = abs(slope_divergence).
  - DELT-11 Velocity: rate of delta change (delta[t] - delta[t-1]) exceeds threshold. Strength = |velocity| / threshold.
  - Use SessionContext rolling histories for multi-bar patterns (cvd_history, delta_history, price_history)
  - Write RED tests using delta fixture
  - Make tests GREEN

  **Must NOT do**:
  - Do not import numpy for polyfit — use simple least squares from `deep6v2/utils/math.py` (create a minimal helper)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-15, 17-20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer)
  - **Blocked By**: Tasks 2, 4, 10

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs` — C# reference (11 variants)
  - `deep6/engines/delta.py` — Python reference
  - `ninjatrader/Custom/AddOns/DEEP6/Math/LeastSquares.cs` — Polyfit implementation for DELT-10

  **Acceptance Criteria**:

  - [ ] DELT-01 through DELT-11 all implemented
  - [ ] DELT-10 uses least-squares polyfit for CVD divergence
  - [ ] Multi-bar patterns use SessionContext rolling histories
  - [ ] All delta fixture tests pass
  - [ ] Tests pass: `pytest tests_v2/signals/test_delta.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: DELT-04 CVD-Price divergence
    Tool: Bash (pytest)
    Steps:
      1. Create SessionContext with 10-bar history: prices trending UP, CVD trending DOWN
      2. Run DeltaDetector.on_bar()
      3. Assert SignalResult with signal_id=DELT_04, direction=BEARISH (price up but delta down = bearish divergence)
    Expected Result: Divergence detected with correct direction
    Failure Indicators: No signal, wrong direction
    Evidence: .sisyphus/evidence/task-16-delt04.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/delta.py`

- [ ] 17. Auction Theory Detectors — AUCT-01..AUCT-05

  **What to do**:
  - Create `deep6v2/signals/auction.py` implementing ISignalDetector
  - AUCT-01 Unfinished Auction: bar high/low has single-print (only 1 trade at extreme). Market didn't fully auction at that level. Direction = BULLISH if unfinished at HIGH (price expected to revisit upward), BEARISH if unfinished at LOW (price expected to revisit downward). Strength = 0.8 (high confidence pattern).
  - AUCT-02 Finished Auction: bar extreme shows declining volume profile (volume decreases toward extreme). Auction is complete. Direction = reversal from extreme. Strength based on volume decay rate.
  - AUCT-03 Poor High/Low: extreme price level has volume > 2× average row volume (excess activity at extreme = rejection). Direction = reversal from poor extreme. Strength = extreme_vol / avg_row_vol.
  - AUCT-04 Volume Void: gap in volume profile (2+ consecutive levels with <5% of max volume). Market moved through without trading. Direction = toward void (unresolved area). Strength = void_width / bar_range.
  - AUCT-05 Market Sweep: rapid price movement covering >N ticks in <M seconds with declining volume (sweep through stops). Direction = reversal after sweep. Strength = sweep_distance / atr.
  - Write RED tests using auction fixture
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-16, 18-20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer)
  - **Blocked By**: Tasks 2, 4, 10

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/AuctionDetector.cs` — C# reference
  - `deep6/engines/auction.py` — Python reference

  **Acceptance Criteria**:

  - [ ] AUCT-01 through AUCT-05 all implemented
  - [ ] All auction fixture tests pass
  - [ ] Tests pass: `pytest tests_v2/signals/test_auction.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: AUCT-01 Unfinished Auction at bar high
    Tool: Bash (pytest)
    Steps:
      1. Create FootprintBar where high price level has only 1 trade (single-print)
      2. Run AuctionDetector.on_bar()
      3. Assert SignalResult with signal_id=AUCT_01, direction=BULLISH (unfinished above → revisit expected)
    Expected Result: Unfinished auction detected at high
    Failure Indicators: No signal, wrong direction
    Evidence: .sisyphus/evidence/task-17-auct01.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/auction.py`

---

- [ ] 18. Trapped Traders — TRAP-01..TRAP-05 (Disabled by Default)

  **What to do**:
  - Create `deep6v2/signals/trap.py` implementing ISignalDetector
  - TRAP-01 Inverse Imbalance Trap: buy imbalance at high followed by price drop (buyers trapped). Direction = BEARISH. Strength = imbalance_ratio × price_reversal.
  - TRAP-02 Delta Trap: large positive delta bar followed by lower close (buyers committed, market reversed). Direction opposite to trapped side. Strength = delta_magnitude.
  - TRAP-03 False Breakout: price breaks prior bar high/low then reverses back inside range. Direction = reversal from breakout. Strength = breakout_distance / atr.
  - TRAP-04 High Volume Rejection: high volume bar at extreme followed by reversal (trapped in high-vol). Direction = reversal. Strength = rejection_vol / avg_vol.
  - TRAP-05 CVD Trap: CVD trending one direction while price reverses (trend followers trapped). Direction matches price reversal. Strength = cvd_trend_strength.
  - **ALL TRAP signals disabled by default** (R3 weight = 0.0). Implement with `enabled: bool = False` config flag.
  - Write RED tests using trap fixture — tests verify logic correctness even though signals are disabled
  - Make tests GREEN

  **Must NOT do**:
  - Do not enable TRAP signals by default — R3 optimization showed 0.0 alpha
  - Do not skip implementation — build correctly but default to disabled

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-17, 19-20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer — as disabled category)
  - **Blocked By**: Tasks 2, 4, 10

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs` — C# reference
  - `deep6/engines/trap.py` — Python reference

  **Acceptance Criteria**:

  - [ ] TRAP-01 through TRAP-05 all implemented
  - [ ] All disabled by default (config flag)
  - [ ] When enabled, fixture tests pass correctly
  - [ ] When disabled, on_bar() returns empty list
  - [ ] Tests pass: `pytest tests_v2/signals/test_trap.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: TRAP signals disabled by default
    Tool: Bash (pytest)
    Steps:
      1. Create TrapDetector with default config
      2. Feed bar that would trigger TRAP-01
      3. Assert empty result list (disabled)
      4. Create TrapDetector with enabled=True
      5. Feed same bar → assert TRAP-01 fires
    Expected Result: Disabled by default, works when enabled
    Evidence: .sisyphus/evidence/task-18-disabled.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/trap.py`

---

- [ ] 19. Volume Pattern Detectors — VOLP-01..VOLP-06

  **What to do**:
  - Create `deep6v2/signals/vol_patterns.py` implementing ISignalDetector
  - VOLP-01 Sequencing: volume increases over 3+ consecutive bars in same direction. Strength = volume_growth_rate.
  - VOLP-02 Bubble: volume spikes >3× rolling average then immediately drops. Strength = spike_magnitude / avg.
  - VOLP-03 Surge: volume > surge_mult × vol_ema on current bar. Strength = vol / (surge_mult × vol_ema).
  - VOLP-04 POC Momentum Wave: POC moves in same direction for 3+ consecutive bars. Strength = poc_displacement / atr.
  - VOLP-05 Delta Velocity Spike: rate of delta change exceeds 2× prior bar's rate. Strength = velocity_ratio.
  - VOLP-06 Big Delta Per Level: single price level has delta > big_delta_threshold. Strength = level_delta / big_delta_threshold.
  - Use SessionContext.vol_history and poc_history for multi-bar patterns
  - Write RED tests using vol_patterns fixture
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-18, 20
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer)
  - **Blocked By**: Tasks 2, 4, 10

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs` — C# reference
  - `deep6/engines/vol_patterns.py` — Python reference

  **Acceptance Criteria**:

  - [ ] VOLP-01 through VOLP-06 all implemented
  - [ ] Multi-bar patterns use SessionContext rolling histories
  - [ ] All vol_patterns fixture tests pass
  - [ ] Tests pass: `pytest tests_v2/signals/test_vol_patterns.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: VOLP-03 Volume Surge detection
    Tool: Bash (pytest)
    Steps:
      1. Create FootprintBar with total_volume=10000, vol_ema=2000 (5× average)
      2. Run VolPatternDetector.on_bar()
      3. Assert VOLP_03 fires with strength > 0.5
    Expected Result: Surge detected when volume significantly exceeds EMA
    Evidence: .sisyphus/evidence/task-19-volp03.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/vol_patterns.py`

---

- [ ] 20. Engine/Context Detectors — ENG-02..ENG-07 + DetectorRegistry

  **What to do**:
  - Create `deep6v2/signals/engines/` subpackage with advanced microstructure detectors
  - `trespass.py` ENG-02: DOM queue imbalance using logistic regression on bid/ask depth ratio. Implements IDepthConsumingDetector — receives DOMSnapshot on every depth update. Strength = logistic(depth_imbalance).
  - `counter_spoof.py` ENG-03: Wasserstein-1 distance between consecutive DOM snapshots + cancel rate detection. If cancel_rate > threshold AND wasserstein_distance > threshold → spoof detected. Returns SPOOF_VETO meta-flag to suppress entry. Implements IDepthConsumingDetector.
  - `iceberg.py` ENG-04: native fill volume > displayed DOM size AND synthetic refill within 250ms. Implements IDepthConsumingDetector AND IAbsorptionZoneReceiver (receives absorption zone notifications from Task 13). Strength = hidden_volume / displayed_volume.
  - `micro_prob.py` ENG-05: Naïve Bayes micro-probability estimator combining recent signal history. Calculates P(reversal | recent_signals) using independent signal priors. Strength = posterior probability.
  - `vp_context.py` ENG-06: POC/VWAP/IB/GEX/ZoneRegistry context engine. Provides zone_bonus scoring input. Manages LVN lifecycle FSM: Created → Defended → Broken → Flipped → Invalidated. Checks price proximity to VAH/VAL, POC, VWAP, GEX levels.
  - `signal_config_scaffold.py` ENG-07: Market regime classifier + dynamic threshold adjuster. Produces a SignalResult with direction=NEUTRAL when regime changes (trending→ranging or vice versa), emitting REGIME_CHANGE meta-flag. Also adjusts other detectors' thresholds based on current regime (trending/ranging/volatile). Unlike other detectors, ENG-07's primary purpose is regime classification and threshold management, with signal emission being secondary. Its fixture should test regime change detection, not trade-actionable signals.
  - Create `deep6v2/signals/registry.py` — DetectorRegistry: sequential list of all ISignalDetector instances. `evaluate_bar(bar, ctx) → list[SignalResult]` iterates all detectors with try/except isolation per detector. Wires AbsorptionDetector → IcebergDetector via IAbsorptionZoneReceiver.
  - Write RED tests for each engine detector + registry integration test
  - Make tests GREEN

  **Must NOT do**:
  - Do not let one detector crash abort the entire evaluation loop — wrap each in try/except
  - Do not import GEX data directly — use stub interface (real GEX in Wave 9)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 13-19
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 21 (scorer needs registry), ALL subsequent waves
  - **Blocked By**: Tasks 2, 4, 8, 10 (types, fixtures, DOM state, bar builder)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/` — All C# engine detector implementations
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs` — Registry sequential evaluation pattern
  - `deep6/engines/counter_spoof.py` — Wasserstein-1 DOM distance calculation
  - `deep6/engines/iceberg.py` — Iceberg detection with refill timing
  - `deep6/engines/trespass.py` — DOM queue imbalance logistic
  - `deep6/engines/vp_context_engine.py` — VP context engine with zone lifecycle
  - `deep6/engines/zone_registry.py` — LVN zone lifecycle FSM (5-state)

  **WHY Each Reference Matters**:
  - `DetectorRegistry.cs` — Exception isolation per detector is the critical safety pattern
  - `counter_spoof.py` — Wasserstein-1 distance formula is mathematically specific
  - `zone_registry.py` — LVN lifecycle FSM has 5 states and specific transition rules

  **Acceptance Criteria**:

  - [ ] ENG-02 through ENG-07 all implemented
  - [ ] IDepthConsumingDetector interface implemented for ENG-02, ENG-03, ENG-04
  - [ ] IAbsorptionZoneReceiver wiring from Task 13 → ENG-04 functional
  - [ ] SPOOF_VETO meta-flag set by ENG-03 when spoof detected
  - [ ] LVN zone lifecycle FSM: Created → Defended → Broken → Flipped → Invalidated
  - [ ] DetectorRegistry evaluates all detectors with exception isolation
  - [ ] One detector throwing exception does not prevent others from running
  - [ ] Tests pass: `pytest tests_v2/signals/test_engines.py tests_v2/signals/test_registry.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Exception isolation in DetectorRegistry
    Tool: Bash (pytest)
    Steps:
      1. Create registry with 3 detectors: [working, broken(raises), working]
      2. Call evaluate_bar()
      3. Assert 2 results returned (from working detectors)
      4. Assert broken detector's exception was logged but didn't crash
    Expected Result: 2 results, 1 logged error, no crash
    Evidence: .sisyphus/evidence/task-20-isolation.txt

  Scenario: Cross-detector wiring (Absorption → Iceberg)
    Tool: Bash (pytest)
    Steps:
      1. Create registry with AbsorptionDetector and IcebergDetector wired via IAbsorptionZoneReceiver
      2. Feed bar that triggers ABS-01 (absorption at 21450.00)
      3. Assert IcebergDetector received mark_absorption_zone(21450.00, BULLISH, 0.4)
    Expected Result: Absorption zone notification reaches Iceberg detector
    Evidence: .sisyphus/evidence/task-20-wiring.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `deep6v2/signals/engines/`, `deep6v2/signals/registry.py`

---

### Wave 4: Scoring & Confluence

- [ ] 21. Two-Layer Confluence Scorer + R3 Weights

  **What to do**:
  - Create `deep6v2/scoring/scorer.py` — two-layer confluence scoring engine
  - **Layer 1 — Engine-Level Agreement**: For each signal category that fired, compute weighted score using R3 weights: absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3, volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0
  - **Layer 2 — Category-Level Confluence**: Count how many distinct categories fired. If 5+ categories agree on direction → apply confluence_multiplier (1.25×)
  - **Multiplier chain** (LOCKED ORDER, MUST MATCH EXACTLY): base_score → confluence_mult → zone_bonus → gex_mult → agreement_mult → ib_mult → vpin_mult → clip(0, 100)
  - Zone bonus: +6 to +8 when signals align with LVN/HVN/GEX zones (stub: zone_bonus = 0 until Wave 9 GEX integration)
  - GEX multiplier: stub as 1.0 until Wave 9
  - VPIN multiplier: stub as 1.0 until Wave 9
  - IB multiplier: 1.15× for bars 0-59 (initial balance period)
  - Midday block: bars 60-210 (10:30-13:00 ET, bar index = minutes since 9:30 RTH open) → force tier to QUIET regardless of score
  - **Tier classification**: TYPE_A ≥ 80, TYPE_B ≥ 72, TYPE_C ≥ 50, QUIET < 50
  - Type A veto gates: ≥3 trap signals veto Type A, |barDelta| > 50 same-direction = chase veto
  - Return ScorerResult with full breakdown
  - Write RED tests using 5 scoring scenario fixtures
  - Make tests GREEN

  **Must NOT do**:
  - Do not change R3 category weights
  - Do not change multiplier chain order
  - Do not change tier thresholds (80/72/50)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 22, 23
  - **Parallel Group**: Wave 4
  - **Blocks**: Tasks 25, 30, 31 (execution, Kronos integration, dashboard)
  - **Blocked By**: Tasks 13-20 (all signal detectors)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs` — C# reference (canonical scoring logic)
  - `deep6/scoring/scorer.py` — Python reference
  - `ninjatrader/backtests/results/round3/FINAL-CONFIG.json` — R3 entry/exit parameters (stop_ticks, target_ticks, breakeven)
  - `deep6/engines/confluence_rules.py` — Multiplier chain implementation

  **WHY Each Reference Matters**:
  - `ConfluenceScorer.cs:59-66` — R3-optimized category weights are declared as constants here (W_ABSORPTION=20.0, etc.); this is the canonical source
  - `ConfluenceScorer.cs:577-591` — CategoryWeight() lookup maps category string → weight; shows which categories map to which weights
  - `confluence_rules.py` — Multiplier chain order is LOCKED from Phase 12-01

  **Acceptance Criteria**:

  - [ ] R3 category weights match `ConfluenceScorer.cs:59-66` exactly (absorption=20.0, exhaustion=15.7, imbalance=25.0, delta=14.3, volume_profile=20.2, auction=12.6, trapped=0.0, poc=0.0)
  - [ ] Multiplier chain order matches: base → confluence → zone → gex → agreement → ib → vpin → clip
  - [ ] IB multiplier 1.15× applied for bars 0-59
  - [ ] Midday block (bars 60-210, i.e. 10:30-13:00 ET) forces QUIET tier
  - [ ] Type A veto gates active (≥3 traps, chase delta)
  - [ ] All 5 scoring scenario fixtures pass (±1 point tolerance)
  - [ ] Tests pass: `pytest tests_v2/scoring/test_scorer.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Type A score with full confluence
    Tool: Bash (pytest)
    Steps:
      1. Load type-a-all-categories.json fixture
      2. Run ConfluenceScorer.score()
      3. Assert tier=TYPE_A, final_score≥80
      4. Assert category_count≥5, confluence_mult=1.25
    Expected Result: Type A tier with confluence multiplier
    Evidence: .sisyphus/evidence/task-21-type-a.txt

  Scenario: Midday block enforcement
    Tool: Bash (pytest)
    Steps:
      1. Load midday-block.json fixture (bar_index=120 (11:30 ET, mid-block), strong signals)
      2. Run scorer
      3. Assert tier=QUIET regardless of raw score
    Expected Result: QUIET tier during midday block
    Evidence: .sisyphus/evidence/task-21-midday.txt

  Scenario: Multiplier chain order verification
    Tool: Bash (pytest)
    Steps:
      1. Create scorer with known multipliers (zone=6, gex=1.1, agreement=1.25, ib=1.15, vpin=1.05)
      2. Inject logging/tracing into each multiplier step
      3. Assert order matches: base → confluence → zone → gex → agreement → ib → vpin → clip
    Expected Result: Multiplier chain applied in exact LOCKED order
    Evidence: .sisyphus/evidence/task-21-chain.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Message: `feat(scoring): two-layer confluence scorer with R3 weights, entry gates, hysteresis`
  - Files: `deep6v2/scoring/scorer.py`

---

- [ ] 22. Entry Gate Logic (Type A/B/C) + Veto Conditions

  **What to do**:
  - Create `deep6v2/scoring/entry_gate.py` — entry gate logic determining trade eligibility
  - Type A requirements: score ≥ 80 AND absorption/exhaustion present AND zone confluence AND 5+ categories agree
  - Type B requirements: score ≥ 72 AND at least 1 core signal (absorption, exhaustion, or stacked imbalance)
  - Type C requirements: score ≥ 50 (monitoring only, no entry)
  - QUIET: score < 50 (no action)
  - Veto conditions (any blocks entry): ≥3 TRAP signals in same bar, |barDelta| > 50 same direction as entry (chase), SPOOF_VETO meta-flag active, PIN_REGIME meta-flag active
  - Confluence gates: STACKED (ABS + EXH same direction), VA_EXTREME (signal ≥0.75 strength within 2 ticks of VAH/VAL), WALL_ANCHORED (within 3 ticks of GEX liquidity wall — stub until Wave 9)
  - Return `EntryDecision` (eligible: bool, tier, veto_reasons: list[str], confluence_type: str)
  - Write RED tests for each tier and veto condition
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 21, 23
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 25 (trade decision machine)
  - **Blocked By**: Tasks 13-20 (signal types needed)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerEntryGate.cs` — C# entry gate logic
  - `deep6/execution/trade_decision_machine.py` — Python TDM with T1-T3 gates

  **Acceptance Criteria**:

  - [ ] Type A/B/C/QUIET classification correct for all fixture scenarios
  - [ ] All veto conditions block entry when triggered
  - [ ] Confluence gates (STACKED, VA_EXTREME) functional
  - [ ] Tests pass: `pytest tests_v2/scoring/test_entry_gate.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Chase veto blocks Type A
    Tool: Bash (pytest)
    Steps:
      1. Score=85 (Type A eligible) BUT barDelta=+60 same direction as entry
      2. Run entry gate
      3. Assert eligible=False, veto_reasons contains "chase_delta"
    Expected Result: Entry blocked despite high score
    Evidence: .sisyphus/evidence/task-22-chase-veto.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Files: `deep6v2/scoring/entry_gate.py`

---

- [ ] 23. Hysteresis FSM + Midday Block + IB Multiplier

  **What to do**:
  - Create `deep6v2/scoring/hysteresis.py` — bias stability state machine
  - Hysteresis states: BULLISH_CONFIRMED, BEARISH_CONFIRMED, NEUTRAL, TRANSITIONING
  - Transition rules: requires N consecutive bars of agreement before switching (prevents whipsaw)
  - Confirmation threshold: 3 consecutive bars with same directional consensus
  - Decay: if no confirmation within 5 bars, revert to NEUTRAL
  - Midday block enforcer: `is_midday_blocked(bar_index) → bool` — True for bars 60-210 (10:30-13:00 ET)
  - IB period detector: `is_initial_balance(bar_index) → bool` — True for bars 0-59
  - IB multiplier: applies 1.15× to score during IB period
  - Integration: scorer calls hysteresis after scoring to potentially suppress flip-flop trades
  - Write RED tests: state transitions, consecutive bar requirement, midday block boundaries, IB boundaries
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 21, 22
  - **Parallel Group**: Wave 4
  - **Blocks**: Task 25 (trade decision machine)
  - **Blocked By**: Tasks 2, 5 (types, clock for bar index)

  **References**:

  **Pattern References**:
  - `deep6/engines/bias_hysteresis.py` — Python hysteresis FSM implementation
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6BiasV3.cs` — NT8 bias engine with hysteresis

  **Acceptance Criteria**:

  - [ ] Hysteresis requires 3 consecutive bars before state transition
  - [ ] Reverts to NEUTRAL after 5 bars without confirmation
  - [ ] Midday block: is_midday_blocked(60)=True (10:30 ET), is_midday_blocked(59)=False (10:29 ET), is_midday_blocked(210)=True (13:00 ET), is_midday_blocked(211)=False (13:01 ET)
  - [ ] IB period: is_initial_balance(0)=True, is_initial_balance(59)=True, is_initial_balance(60)=False
  - [ ] Tests pass: `pytest tests_v2/scoring/test_hysteresis.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Hysteresis prevents whipsaw
    Tool: Bash (pytest)
    Steps:
      1. Feed 2 bullish bars → assert state=TRANSITIONING (not yet confirmed)
      2. Feed 1 bearish bar → assert state=NEUTRAL (reset)
      3. Feed 3 bullish bars → assert state=BULLISH_CONFIRMED
    Expected Result: Requires 3 consecutive bars for confirmation
    Evidence: .sisyphus/evidence/task-23-hysteresis.txt
  ```

  **Commit**: YES (groups with Wave 4)
  - Files: `deep6v2/scoring/hysteresis.py`

---

### Wave 5: Execution

- [ ] 24. Research Spike — async-rithmic ORDER_PLANT Test

  **What to do**:
  - Create `tests_v2/integration/test_rithmic_orders.py` — research spike for order execution
  - Connect to Rithmic TEST environment (wss://rituz00100.rithmic.com)
  - Test order lifecycle: submit market order → receive fill → query position → close position
  - Test limit order: submit → verify in order book → cancel → verify canceled
  - Test stop order: submit → verify pending → cancel
  - Document async-rithmic ORDER_PLANT API: method signatures, callback events, error codes
  - Document any AMP Futures-specific requirements or differences from test environment
  - Create `deep6v2/execution/rithmic_broker.py` — broker interface abstraction based on findings
  - `IBroker` protocol: submit_order, cancel_order, query_position, get_fills, on_fill_callback
  - `RithmicBroker` implementation using async-rithmic ORDER_PLANT
  - `MockBroker` for testing (returns simulated fills)
  - Write RED tests for broker interface
  - Make tests GREEN (with MockBroker for unit tests, RithmicBroker for integration test)

  **Must NOT do**:
  - Do not submit orders to any live/funded account — test environment ONLY
  - Do not skip this research spike — untested order execution is the highest-risk item

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — must complete before Tasks 25-27
  - **Parallel Group**: Sequential (Wave 5 lead)
  - **Blocks**: Tasks 25, 26, 27 (all execution tasks need broker interface)
  - **Blocked By**: Tasks 7, 11 (connection manager, Rithmic connection verified)

  **References**:

  **Pattern References**:
  - `deep6/execution/engine.py` — Existing execution engine (paper trading logic)
  - `deep6/execution/paper_trader.py` — Paper trading with simulated fills

  **External References**:
  - async-rithmic ORDER_PLANT: https://github.com/rundef/async_rithmic — order submission API
  - async-rithmic examples: order management examples

  **Acceptance Criteria**:

  - [ ] Market order submitted and fill received on test environment
  - [ ] Limit order submitted, verified pending, canceled successfully
  - [ ] Position query returns correct state after fill
  - [ ] IBroker protocol defined with submit_order, cancel_order, query_position
  - [ ] RithmicBroker and MockBroker both implement IBroker
  - [ ] API documentation captured in docstrings
  - [ ] Tests pass: `pytest tests_v2/execution/test_broker.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Mock broker order lifecycle
    Tool: Bash (pytest)
    Steps:
      1. Create MockBroker
      2. Submit market BUY order for NQ at 21450.00, size=1
      3. Assert fill callback received with price=21450.00, size=1
      4. Query position → assert long 1 contract
      5. Submit market SELL order, size=1
      6. Query position → assert flat (0 contracts)
    Expected Result: Full order lifecycle with MockBroker
    Evidence: .sisyphus/evidence/task-24-mock-broker.txt

  Scenario: Rithmic test environment order (integration)
    Tool: Bash (pytest)
    Preconditions: RITHMIC credentials set, test environment accessible
    Steps:
      1. Connect to test environment
      2. Submit market order for NQ (test account)
      3. Wait for fill callback (timeout 10s)
      4. Assert fill received with valid price and size
      5. Query position to verify
    Expected Result: Order submitted and filled on test environment
    Evidence: .sisyphus/evidence/task-24-rithmic-order.txt
  ```

  **Commit**: YES (groups with Wave 5)
  - Message: `feat(execution): trade decision FSM, risk manager, paper trader, kill switch`
  - Files: `deep6v2/execution/rithmic_broker.py`

---

- [ ] 25. Trade Decision Machine — 7-State FSM

  **What to do**:
  - Create `deep6v2/execution/fsm.py` — 7-state finite state machine for trade lifecycle
  - States: IDLE, WATCHING, ARMED, PENDING_ENTRY, IN_POSITION, EXITING, CLOSED
  - Transitions (11 defined):
    - T1: IDLE → WATCHING (session opens, RTH begins)
    - T2: WATCHING → ARMED (Type A or B score detected)
    - T3: ARMED → PENDING_ENTRY (confirmation bar validates — D-20 delay)
    - T4: PENDING_ENTRY → IN_POSITION (order filled)
    - T5: IN_POSITION → EXITING (target hit, stop hit, or manual exit)
    - T6: EXITING → CLOSED (all orders canceled, position flat)
    - T7: CLOSED → WATCHING (cooldown period elapsed)
    - T8: ARMED → WATCHING (setup expires or invalidates)
    - T9: PENDING_ENTRY → WATCHING (order rejected or timeout)
    - T10: WATCHING → IDLE (session closes, RTH ends)
    - T11: IN_POSITION → IN_POSITION (partial fill, scale adjustment)
  - Invalidation conditions (all 9 defined):
    - I1: Price moves beyond calculated stop level before entry is filled
    - I2: Opposing Type A/B signal fires in same bar (directional conflict)
    - I3: Kill switch escalates to CAUTION or STOP
    - I4: Session boundary reached (RTH close approaching within 15 bars)
    - I5: Setup age exceeds max_hold_bars (setup expired)
    - I6: Midday block entered while ARMED (bars 60-210)
    - I7: FreezeGuard triggers (connection lost)
    - I8: Daily loss cap at ≥80% (approaching limit)
    - I9: SPOOF_VETO meta-flag active (market microstructure unsafe)
  - Confirmation-bar delay (D-20): entry triggers fire on NEXT bar's close after signal
  - Persist all transitions to EventStore (Task 12)
  - Emit state change events for dashboard consumption
  - Write RED tests: all 7 states reachable, all 11 transitions valid, invalidation conditions, D-20 delay
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential after Task 24
  - **Blocks**: Tasks 26, 27
  - **Blocked By**: Tasks 2, 12, 21-23, 24

  **References**:

  **Pattern References**:
  - `deep6/execution/trade_decision_machine.py` — Python reference FSM (7 states, 11 transitions)
  - `deep6/execution/trade_state.py` — TradeState enum and transition logic

  **Acceptance Criteria**:

  - [ ] All 7 states defined and reachable
  - [ ] All 11 transitions implemented with correct guards
  - [ ] D-20 confirmation delay enforced (entry on NEXT bar after signal)
  - [ ] All 9 invalidation conditions functional
  - [ ] FSM transitions persisted to EventStore
  - [ ] FSM reachability test passes (all states and transitions exercised)
  - [ ] Tests pass: `pytest tests_v2/execution/test_fsm.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: FSM reachability — all states and transitions
    Tool: Bash (pytest)
    Steps:
      1. Run FSM reachability test that drives through all 7 states
      2. Assert each state visited at least once
      3. Assert each of 11 transitions exercised at least once
    Expected Result: 7/7 states, 11/11 transitions reachable
    Evidence: .sisyphus/evidence/task-25-reachability.txt

  Scenario: D-20 confirmation delay
    Tool: Bash (pytest)
    Steps:
      1. FSM in WATCHING state
      2. Type A score fires on bar N
      3. Assert state → ARMED (not PENDING_ENTRY immediately)
      4. Bar N+1 closes with confirmation
      5. Assert state → PENDING_ENTRY
    Expected Result: Entry delayed by 1 bar (D-20)
    Evidence: .sisyphus/evidence/task-25-d20.txt
  ```

  **Commit**: YES (groups with Wave 5)
  - Files: `deep6v2/execution/fsm.py`

---

- [ ] 26. Risk Manager + Position Manager

  **What to do**:
  - Create `deep6v2/execution/risk_manager.py` — pre-trade and in-trade risk controls
  - Pre-trade checks: max_contracts_per_trade, max_trades_per_session, daily_loss_cap, RTH_only, midday_block
  - Position sizing: `floor(risk_budget / stop_distance × conviction × regime × recency × 0.25)` where conviction = scorer tier weight, regime = market regime adjustment, recency = time decay
  - Stop calculation: `max(structural_stop + 2_ticks, 2.0 × ATR(14))`, capped at 1.5% of account
  - In-trade management: trailing stop logic, partial exit at targets, time-based exit (max hold bars)
  - Create `deep6v2/execution/position_manager.py` — position tracking
  - Track open positions, fills, P&L, exposure
  - Reconciliation: compare local state vs broker position query (from IBroker)
  - Position flattening: market order to close all at session end or risk breach
  - Write RED tests for each risk check, position sizing formula, stop calculation
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential after Task 25
  - **Blocks**: Task 27
  - **Blocked By**: Tasks 24, 25

  **References**:

  **Pattern References**:
  - `deep6/execution/risk_manager.py` — Python risk manager reference
  - `deep6/execution/position_manager.py` — Python position manager reference
  - `deep6/execution/config.py` — Execution config (max contracts, daily caps)

  **Acceptance Criteria**:

  - [ ] Max contracts/trade enforced
  - [ ] Max trades/session enforced
  - [ ] Daily loss cap halts trading when breached
  - [ ] Position sizing formula matches specification
  - [ ] Stop calculation: max(structural+2t, 2×ATR), capped at 1.5% account
  - [ ] Position reconciliation detects local vs broker mismatch
  - [ ] Tests pass: `pytest tests_v2/execution/test_risk_manager.py tests_v2/execution/test_position_manager.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Daily loss cap halts trading
    Tool: Bash (pytest)
    Steps:
      1. Set daily_loss_cap=500
      2. Simulate 3 losing trades totaling -$520
      3. Attempt new trade entry
      4. Assert risk_manager.pre_trade_check() returns False with reason="daily_loss_cap_breached"
    Expected Result: Trading halted after daily loss cap exceeded
    Evidence: .sisyphus/evidence/task-26-daily-cap.txt
  ```

  **Commit**: YES (groups with Wave 5)
  - Files: `deep6v2/execution/risk_manager.py`, `deep6v2/execution/position_manager.py`

---

- [ ] 27. Paper Trader + Promotion Gate + Kill Switch

  **What to do**:
  - Create `deep6v2/execution/paper_trader.py` — simulated execution for paper trading
  - Uses MockBroker (from Task 24) with realistic fill simulation (slippage model)
  - Tracks all paper trades, P&L, win rate, max drawdown
  - Create `deep6v2/execution/promotion_gate.py` — paper-to-live promotion criteria
  - Promotion requirements (all must be met):
    - 30 consecutive RTH sessions without crashes or unhandled exceptions
    - All risk gates fire at least once (daily_loss_cap, max_trades, max_contracts, kill_switch, midday_block)
    - Cumulative P&L > $0 over the 30 sessions
    - Max drawdown < $2,000 (configurable via PromotionConfig)
    - Win rate > 40% (minimum viability)
    - No FreezeGuard FROZEN states lasting > 5 minutes during RTH
    - Median fill slippage < 2 ticks (0.50 NQ points)
  - Create `deep6v2/execution/kill_switch.py` — emergency stop
  - Kill switch states: GO (normal), CAUTION (elevated risk), STOP (all trading halted)
  - Triggers: consecutive losses, volatility spike, connection issues, manual override
  - STOP flattens all positions immediately and prevents new entries
  - Write RED tests for paper trading lifecycle, promotion criteria, kill switch triggers
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — sequential after Tasks 25, 26
  - **Blocks**: Task 37 (unified startup)
  - **Blocked By**: Tasks 25, 26

  **References**:

  **Pattern References**:
  - `deep6/execution/paper_trader.py` — Python paper trader reference
  - `deep6/engines/kill_switch.py` — Kill switch implementation (GO/CAUTION/STOP)

  **Acceptance Criteria**:

  - [ ] Paper trader simulates fills with configurable slippage
  - [ ] Trade history, P&L, win rate tracked
  - [ ] Promotion gate checks 30-session requirement
  - [ ] Kill switch transitions: GO → CAUTION → STOP
  - [ ] STOP state flattens positions and blocks new entries
  - [ ] Tests pass: `pytest tests_v2/execution/test_paper_trader.py tests_v2/execution/test_kill_switch.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Kill switch escalation
    Tool: Bash (pytest)
    Steps:
      1. Kill switch starts in GO state
      2. Simulate 3 consecutive losses → assert CAUTION
      3. Simulate daily loss cap breach → assert STOP
      4. Assert no new orders accepted in STOP state
      5. Assert position flattening triggered
    Expected Result: Kill switch escalates correctly
    Evidence: .sisyphus/evidence/task-27-killswitch.txt
  ```

  **Commit**: YES (groups with Wave 5)
  - Files: `deep6v2/execution/paper_trader.py`, `deep6v2/execution/promotion_gate.py`, `deep6v2/execution/kill_switch.py`

---

### Wave 6: Kronos Integration

- [ ] 28. Kronos Model Loading + Tokenizer

  **What to do**:
  - Create `deep6v2/kronos/model.py` — Kronos-small model loading and tokenizer setup
  - Load from HuggingFace Hub: `NeoQuasar/Kronos-small` (24.7M params, cached locally)
  - Initialize KronosTokenizer for OHLCV → hierarchical discrete tokens
  - Device selection: CUDA GPU if available, MPS (Apple Silicon) if available, CPU fallback
  - Model warm-up: run dummy inference at startup to ensure model loaded and ready
  - Memory management: load model once, keep in memory for duration of session
  - Write RED tests: model loads successfully, tokenizer converts OHLCV DataFrame, device auto-detection
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — parallel with Wave 5 (depends only on Wave 2)
  - **Parallel Group**: Wave 6 (with Tasks 29, 30)
  - **Blocks**: Task 29 (inference pipeline needs model)
  - **Blocked By**: Tasks 2, 10 (types, bar builder for OHLCV data)

  **References**:

  **Pattern References**:
  - `deep6/engines/kronos_domain.py` — Existing Kronos domain model loading
  - `deep6/engines/kronos_worker.py` — Kronos worker pattern

  **External References**:
  - Kronos GitHub: https://github.com/shiyu-coder/Kronos
  - Kronos HuggingFace: https://huggingface.co/NeoQuasar/Kronos-small

  **Acceptance Criteria**:

  - [ ] Model loads from HuggingFace Hub (or local cache)
  - [ ] Tokenizer converts OHLCV DataFrame to tokens
  - [ ] Device auto-detection (CUDA → MPS → CPU)
  - [ ] Warm-up inference completes without error
  - [ ] Tests pass: `pytest tests_v2/kronos/test_model.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Model loading and warm-up
    Tool: Bash (pytest)
    Steps:
      1. Run: pytest tests_v2/kronos/test_model.py::test_model_loads -v
      2. Assert model loaded (24.7M params)
      3. Assert warm-up inference produces output shape matching input context
    Expected Result: Model loaded and inference functional
    Evidence: .sisyphus/evidence/task-28-model.txt
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(kronos): E10 bias engine with async inference pipeline`
  - Files: `deep6v2/kronos/model.py`

---

- [ ] 29. OHLCV Accumulator + Async Inference Pipeline

  **What to do**:
  - Create `deep6v2/kronos/pipeline.py` — async inference pipeline
  - OHLCV accumulator: collect 512 most recent 1-minute bars into DataFrame (columns: open, high, low, close, volume)
  - Thread-safe inference: `ThreadPoolExecutor(max_workers=1)` runs Kronos inference (sync PyTorch)
  - Results delivery: `janus.Queue` bridges sync thread → async event loop
  - Stale-tolerance: if inference is still running when next bar closes, use last prediction (don't block)
  - Inference frequency: every N bars (configurable, default=5 — predict every 5 minutes)
  - E10 signal: predicted close vs current close → BULLISH if predicted > current, BEARISH if predicted < current
  - E10 strength: magnitude of price difference normalized by ATR
  - Create async consumer that reads from janus queue and updates SessionContext with E10 bias
  - Write RED tests: OHLCV accumulation, thread-safe inference, stale prediction handling, janus queue delivery
  - Make tests GREEN (with mock model that returns predetermined predictions)

  **Must NOT do**:
  - Do not run Kronos inference on the asyncio event loop thread — must use ThreadPoolExecutor
  - Do not block on inference result — use stale prediction if current is not ready

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 28, 30
  - **Parallel Group**: Wave 6
  - **Blocks**: Task 30 (E10 integration with scorer)
  - **Blocked By**: Tasks 2, 10, 28 (types, bar builder, model)

  **References**:

  **Pattern References**:
  - `deep6/engines/kronos_worker.py` — Existing Kronos worker with ThreadPoolExecutor
  - `deep6/engines/ohlcv_accumulator.py` — OHLCV accumulation pattern

  **External References**:
  - janus docs: https://github.com/aio-libs/janus — thread-safe asyncio queue

  **Acceptance Criteria**:

  - [ ] OHLCV accumulator maintains 512 most recent 1-minute bars
  - [ ] Inference runs in ThreadPoolExecutor (not blocking event loop)
  - [ ] Results delivered via janus queue to async consumer
  - [ ] Stale prediction used when inference is still running
  - [ ] E10 direction and strength computed from predicted vs current close
  - [ ] Tests pass: `pytest tests_v2/kronos/test_pipeline.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Stale prediction tolerance
    Tool: Bash (pytest)
    Steps:
      1. Start inference with mock model that takes 500ms
      2. Before inference completes, request E10 signal
      3. Assert stale prediction from previous inference is returned
      4. Wait for current inference to complete
      5. Assert next request returns fresh prediction
    Expected Result: Never blocks, uses stale prediction when needed
    Evidence: .sisyphus/evidence/task-29-stale.txt
  ```

  **Commit**: YES (groups with Wave 6)
  - Files: `deep6v2/kronos/pipeline.py`

---

- [ ] 30. E10 Bias Signal Integration with Scorer

  **What to do**:
  - Create `deep6v2/kronos/e10_signal.py` — E10 bias as a scoring modifier
  - E10 is NOT a signal detector (not in the 52-signal taxonomy or SignalId enum) — it's a directional bias overlay that operates as a post-scoring advisory layer
  - Integration point: after scorer computes raw_score, E10 bias is consulted
  - E10 is PURELY ADVISORY — it does NOT modify `final_score`
  - If E10 agrees with signal direction → set `e10_agreement: bool = True` on ScorerResult (logged for analysis and dashboard display)
  - If E10 disagrees → set `e10_agreement: bool = False` and `e10_caution: bool = True` on ScorerResult (logged, no score change)
  - If E10 is neutral or stale → set `e10_agreement: None` on ScorerResult (graceful degradation)
  - E10 output is informational only — the scorer's `final_score` is unchanged by E10
  - Write RED tests: E10 agreement boost, disagreement caution, stale graceful degradation
  - Make tests GREEN

  **Must NOT do**:
  - Do not add E10 to the multiplier chain — it is PURELY ADVISORY, sets flags on ScorerResult only
  - Do not modify `final_score` based on E10 — no additive boost, no multiplicative factor
  - Do not make E10 a required dependency — scorer must work without Kronos

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 28, 29
  - **Parallel Group**: Wave 6
  - **Blocks**: Task 37 (unified startup)
  - **Blocked By**: Tasks 21, 29 (scorer, inference pipeline)

  **References**:

  **Pattern References**:
  - `deep6/engines/kronos_bias.py` — Existing Kronos bias integration

  **Acceptance Criteria**:

  - [ ] E10 agreement sets `e10_agreement=True` on ScorerResult (advisory only, no score change)
  - [ ] E10 disagreement sets `e10_caution=True` on ScorerResult (logged, no score penalty)
  - [ ] `final_score` is identical with and without E10 (E10 is purely advisory)
  - [ ] Scorer works correctly without Kronos (`e10_agreement=None`, graceful degradation)
  - [ ] Tests pass: `pytest tests_v2/kronos/test_e10_signal.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Scorer works without Kronos
    Tool: Bash (pytest)
    Steps:
      1. Create scorer with Kronos disabled (no model loaded)
      2. Run scoring on Type A fixture
      3. Assert score calculated correctly without E10 modification
    Expected Result: Graceful degradation when Kronos unavailable
    Evidence: .sisyphus/evidence/task-30-no-kronos.txt
  ```

  **Commit**: YES (groups with Wave 6)
  - Files: `deep6v2/kronos/e10_signal.py`

---

### Wave 7: Dashboard MVP

- [ ] 31. FastAPI Backend — SSE + WebSocket Endpoints

  **What to do**:
  - Create `deep6v2/api/app.py` — FastAPI application with SSE and WebSocket endpoints
  - `GET /health` — connection status, system state, uptime
  - `GET /signals/stream` — SSE stream of signal events (SignalResult JSON per event)
  - `GET /scores/stream` — SSE stream of scoring events (ScorerResult JSON per event)
  - `WS /bars` — WebSocket for real-time FootprintBar data (high-frequency)
  - `GET /position` — current position, P&L, trade history
  - `GET /config` — current configuration (read-only)
  - `POST /kill-switch` — manual kill switch activation (requires auth token)
  - Use FastAPI's StreamingResponse for SSE, WebSocket for high-frequency bar data
  - CORS configuration for Next.js dashboard
  - Write RED tests using httpx async test client
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — parallel with Waves 5-6
  - **Parallel Group**: Wave 7 (with Tasks 32-34)
  - **Blocks**: Tasks 32, 33, 34
  - **Blocked By**: Tasks 2, 21 (types, scorer for event shapes)

  **References**:

  **Pattern References**:
  - `deep6/api/` — Existing FastAPI routes
  - `tests/api/test_ws.py` — WebSocket test patterns

  **Acceptance Criteria**:

  - [ ] `/health` returns JSON with status, rithmic connection state, uptime
  - [ ] `/signals/stream` produces SSE events with valid SignalResult JSON
  - [ ] `/bars` WebSocket sends FootprintBar JSON on bar close
  - [ ] `/position` returns current position and P&L
  - [ ] Tests pass: `pytest tests_v2/api/test_endpoints.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Health endpoint
    Tool: Bash (curl)
    Steps:
      1. Start FastAPI server in test mode
      2. Run: curl http://localhost:8000/health
      3. Assert JSON response with status="ok"
    Expected Result: Health check passes
    Evidence: .sisyphus/evidence/task-31-health.txt
  ```

  **Commit**: YES (groups with Wave 7)
  - Message: `feat(dashboard): FastAPI SSE/WS backend + Next.js MVP (signals, P&L, status)`
  - Files: `deep6v2/api/`

---

- [ ] 32. Next.js Shell + Signal Feed Display

  **What to do**:
  - Create `dashboard-v2/` Next.js 15 App Router application
  - Layout: dark theme, sidebar navigation, main content area
  - Signal feed page: real-time SSE consumer showing latest signals with: timestamp, signal_id, direction (color-coded), strength (bar), detail text
  - Auto-scroll with pause on hover
  - Connection status indicator (green/yellow/red)
  - Use shadcn/ui components for consistent styling
  - Write component tests

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 33, 34
  - **Parallel Group**: Wave 7
  - **Blocks**: None
  - **Blocked By**: Task 31 (FastAPI backend for SSE)

  **References**:

  **Pattern References**:
  - `dashboard/` — Existing Next.js dashboard (reference for layout patterns)

  **Acceptance Criteria**:

  - [ ] Next.js app starts with `npm run dev`
  - [ ] Signal feed displays real-time signals via SSE
  - [ ] Dark theme applied consistently
  - [ ] Connection status indicator functional

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Dashboard loads and shows signal feed
    Tool: Playwright
    Steps:
      1. Navigate to http://localhost:3000
      2. Assert page title contains "DEEP6"
      3. Assert signal feed component visible (selector: [data-testid="signal-feed"])
      4. Assert connection indicator visible
    Expected Result: Dashboard loads with signal feed
    Evidence: .sisyphus/evidence/task-32-dashboard.png
  ```

  **Commit**: YES (groups with Wave 7)
  - Files: `dashboard-v2/`

---

- [ ] 33. P&L Tracker + Connection Status Panel

  **What to do**:
  - Create P&L tracker component in dashboard: daily P&L, trade count, win rate, max drawdown
  - Create connection status panel: Rithmic connection state, last DOM update timestamp, bar count
  - Create kill switch button (requires confirmation dialog)
  - Use Tremor components for KPI cards and metrics display
  - Fetch data from FastAPI `/position` and `/health` endpoints

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 32, 34
  - **Parallel Group**: Wave 7
  - **Blocked By**: Task 31

  **Acceptance Criteria**:

  - [ ] P&L tracker shows daily P&L, trade count, win rate
  - [ ] Connection status shows Rithmic state and last update time
  - [ ] Kill switch button with confirmation dialog

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: P&L tracker displays metrics
    Tool: Playwright
    Steps:
      1. Navigate to http://localhost:3000
      2. Assert P&L card visible (selector: [data-testid="pnl-tracker"])
      3. Assert trade count visible
    Expected Result: P&L metrics displayed
    Evidence: .sisyphus/evidence/task-33-pnl.png
  ```

  **Commit**: YES (groups with Wave 7)
  - Files: `dashboard-v2/`

---

- [ ] 34. Session Replay Endpoint

  **What to do**:
  - Create `deep6v2/api/replay.py` — session replay API endpoint
  - `GET /replay/sessions` — list available sessions from DuckDB
  - `GET /replay/{session_id}/bars` — return all bars for a session
  - `GET /replay/{session_id}/signals` — return all signals for a session
  - `GET /replay/{session_id}/scores` — return all scores for a session
  - `GET /replay/{session_id}/trades` — return all trade events for a session
  - Query DuckDB event store (Task 12) for historical data
  - Pagination support for large sessions (390 bars per RTH session)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 31-33
  - **Parallel Group**: Wave 7
  - **Blocked By**: Tasks 12, 31 (persistence, FastAPI)

  **Acceptance Criteria**:

  - [ ] Session list endpoint returns available sessions
  - [ ] Bar, signal, score, trade endpoints return correct data for session
  - [ ] Pagination works for large sessions
  - [ ] Tests pass: `pytest tests_v2/api/test_replay.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Replay session data retrieval
    Tool: Bash (curl)
    Steps:
      1. Insert test session data into DuckDB (5 bars, 3 signals, 1 score)
      2. GET /replay/sessions → assert test session listed
      3. GET /replay/{id}/bars → assert 5 bars returned
      4. GET /replay/{id}/signals → assert 3 signals returned
    Expected Result: All session data retrievable
    Evidence: .sisyphus/evidence/task-34-replay.txt
  ```

  **Commit**: YES (groups with Wave 7)
  - Files: `deep6v2/api/replay.py`

---

### Wave 8: TradingView MCP Integration

- [ ] 35. TradingView MCP Connection + Chart State Reading

  **What to do**:
  - Create `deep6v2/tradingview/client.py` — TradingView MCP client wrapper
  - Use existing tradingview-mcp server (already installed, see CLAUDE.md)
  - `get_chart_state()` — current symbol, timeframe, indicators
  - `get_ohlcv(count)` — retrieve bar data from TradingView chart
  - `get_study_values()` — read indicator values (RSI, MACD, EMA, etc.)
  - `get_pine_levels()` — read levels drawn by Pine Script indicators
  - `capture_screenshot()` — save chart screenshot for analysis
  - Error handling: graceful degradation if TradingView Desktop not running
  - Write RED tests with mock MCP responses
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — parallel with Waves 5-7
  - **Parallel Group**: Wave 8 (with Task 36)
  - **Blocks**: Task 36
  - **Blocked By**: Task 7 (connection patterns)

  **Acceptance Criteria**:

  - [ ] Chart state retrieval works when TradingView is running
  - [ ] Graceful degradation when TradingView is not running
  - [ ] Screenshot capture saves to configured directory
  - [ ] Tests pass: `pytest tests_v2/tradingview/test_client.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Graceful degradation without TradingView
    Tool: Bash (pytest)
    Steps:
      1. Create client with TradingView NOT running
      2. Call get_chart_state()
      3. Assert returns None (not exception)
      4. Assert warning logged
    Expected Result: No crash when TradingView unavailable
    Evidence: .sisyphus/evidence/task-35-graceful.txt
  ```

  **Commit**: YES (groups with Wave 8)
  - Message: `feat(tradingview): MCP integration for chart state + visual analysis`
  - Files: `deep6v2/tradingview/client.py`

---

- [ ] 36. Visual Analysis Integration

  **What to do**:
  - Create `deep6v2/tradingview/analysis.py` — visual analysis integration
  - On significant signal (Type A or B): capture chart screenshot, annotate with signal details
  - `annotate_chart(signal_result, scorer_result)` — draw levels/markers on TradingView chart
  - `inject_pine_script(source)` — push custom Pine Script for level visualization
  - `generate_trade_report(session_id)` — capture multi-timeframe screenshots for trade review
  - Integration with dashboard: link trade entries to chart screenshots
  - Write RED tests with mock TradingView
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Task 35
  - **Parallel Group**: Wave 8
  - **Blocked By**: Task 35

  **Acceptance Criteria**:

  - [ ] Screenshot captured on Type A/B signal
  - [ ] Pine Script injection functional
  - [ ] Trade report generates multi-timeframe screenshots
  - [ ] Tests pass: `pytest tests_v2/tradingview/test_analysis.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Screenshot on Type A signal
    Tool: Bash (pytest)
    Steps:
      1. Mock TradingView MCP
      2. Simulate Type A signal
      3. Assert capture_screenshot() called
      4. Assert screenshot file saved to evidence directory
    Expected Result: Screenshot captured automatically on high-confidence signal
    Evidence: .sisyphus/evidence/task-36-screenshot.txt
  ```

  **Commit**: YES (groups with Wave 8)
  - Files: `deep6v2/tradingview/analysis.py`

---

### Wave 9: Operational Hardening

- [ ] 37. Unified Startup — python -m deep6v2

  **What to do**:
  - Create `deep6v2/__main__.py` — single entry point for the entire system
  - Startup sequence: load config → configure logging → initialize clock → connect Rithmic → start DOM/bar pipeline → load signal detectors → start scorer → start FSM → start Kronos (optional) → start FastAPI → start TradingView MCP (optional)
  - Shutdown sequence: reverse order — stop MCP → stop API → stop Kronos → stop FSM → flatten positions → disconnect Rithmic → save state
  - CLI arguments: `--dry-run` (default), `--live`, `--paper`, `--replay <session_id>`, `--dev` (console logging)
  - GC management: `gc.disable()` at RTH open (9:30 ET), `gc.enable()` at RTH close (16:00 ET)
  - Signal handlers: SIGINT/SIGTERM → graceful shutdown
  - Health monitoring: periodic self-check (DOM freshness, bar count, Rithmic heartbeat)
  - Write RED tests for startup/shutdown sequence
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 38-41
  - **Parallel Group**: Wave 9
  - **Blocks**: F1-F4 (verification)
  - **Blocked By**: Tasks 1-27 (all core tasks)

  **References**:

  **Pattern References**:
  - `deep6/__main__.py` — Existing startup pattern (237 lines)

  **Acceptance Criteria**:

  - [ ] `python -m deep6v2 --dry-run` starts and shuts down cleanly
  - [ ] GC disabled during RTH, re-enabled at close
  - [ ] SIGINT triggers graceful shutdown
  - [ ] All subsystems started in correct order
  - [ ] Tests pass: `pytest tests_v2/test_startup.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Dry run startup and shutdown
    Tool: Bash (PowerShell)
    Steps:
      1. Run: Start-Process python -ArgumentList "-m","deep6v2","--dry-run","--dev" -PassThru | ForEach-Object { Start-Sleep 10; Stop-Process $_ }
      2. Or alternatively: python -m deep6v2 --dry-run --dev --max-bars 5 (if max-bars flag implemented for auto-exit)
      3. Assert "System started" in output
      4. Assert "Shutting down" in output
    Expected Result: Clean startup and shutdown cycle
    Evidence: .sisyphus/evidence/task-37-startup.txt
  ```

  **Commit**: YES (groups with Wave 9)
  - Message: `feat(ops): unified startup, GEX, VPIN, observability, session edge cases`
  - Files: `deep6v2/__main__.py`

---

- [ ] 38. GEX Integration — massive.com API

  **What to do**:
  - Create `deep6v2/data/gex_client.py` — massive.com GEX data fetcher (NOTE: CLAUDE.md references "FlashAlpha API" but this is STALE — massive.com is the confirmed live provider per Phase 16 NT8 implementation and .planning/PROJECT.md line 58)
  - Fetch call wall, put wall, gamma flip, HVL via massive.com REST API (MASSIVE_API_KEY env var, base URL from existing `ninjatrader/Custom/Indicators/DEEP6/DEEP6MassiveGexMap.cs`)
  - NQ via QQQ/NDX proxy mapping
  - Background timer: fetch every 5 minutes, exponential backoff on failure
  - Feed GEX levels into VP context engine (ENG-06) for zone_bonus calculation
  - Feed GEX levels into risk manager for wall conflict gate
  - Integrate with scorer: populate gex_mult in multiplier chain (replace 1.0 stub)
  - Write RED tests with mock API responses
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 37, 39-41
  - **Parallel Group**: Wave 9
  - **Blocked By**: Tasks 20, 21 (ENG-06, scorer)

  **References**:

  **Pattern References**:
  - `deep6/engines/gex.py` — Existing GEX client implementation
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevelsV3.cs` — NT8 GEX integration

  **Acceptance Criteria**:

  - [ ] GEX data fetched from massive.com API
  - [ ] Call wall, put wall, gamma flip, HVL levels parsed
  - [ ] Zone bonus calculated from GEX proximity
  - [ ] Scorer gex_mult populated (replacing 1.0 stub)
  - [ ] Tests pass: `pytest tests_v2/data/test_gex_client.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: GEX levels affect zone bonus
    Tool: Bash (pytest)
    Steps:
      1. Mock GEX API returning call_wall=21500, put_wall=21400
      2. Signal at 21498 (2 points from call wall)
      3. Run scorer with GEX context
      4. Assert zone_bonus > 0 (signal near wall)
    Expected Result: Zone bonus applied for wall proximity
    Evidence: .sisyphus/evidence/task-38-gex-bonus.txt
  ```

  **Commit**: YES (groups with Wave 9)
  - Files: `deep6v2/data/gex_client.py`

---

- [ ] 39. VPIN Module + Scorer Integration

  **What to do**:
  - Create `deep6v2/orderflow/vpin.py` — Volume-Synchronized Probability of Informed Trading
  - VPIN calculation: rolling window of volume buckets, classifying buy/sell volume, computing probability
  - Integration: VPIN is the FINAL multiplier in the scoring chain (vpin_mult)
  - When VPIN is high (informed trading likely): boost score (multiplier > 1.0)
  - When VPIN is low: neutral (multiplier = 1.0)
  - Replace 1.0 stub in scorer with actual VPIN multiplier
  - Write RED tests for VPIN calculation, scorer integration
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 37-38, 40-41
  - **Parallel Group**: Wave 9
  - **Blocked By**: Tasks 10, 21 (bar builder, scorer)

  **References**:

  **Pattern References**:
  - `deep6/orderflow/vpin.py` — Existing VPIN implementation

  **Acceptance Criteria**:

  - [ ] VPIN calculated from volume buckets
  - [ ] Scorer vpin_mult populated (replacing 1.0 stub)
  - [ ] High VPIN boosts score, low VPIN neutral
  - [ ] Tests pass: `pytest tests_v2/orderflow/test_vpin.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: VPIN integration in scorer chain
    Tool: Bash (pytest)
    Steps:
      1. Calculate VPIN = 0.8 (high informed trading)
      2. Run scorer with VPIN context
      3. Assert vpin_mult > 1.0 in ScorerResult
      4. Assert final_score > raw_score (VPIN boosted)
    Expected Result: VPIN multiplier applied as final step in chain
    Evidence: .sisyphus/evidence/task-39-vpin.txt
  ```

  **Commit**: YES (groups with Wave 9)
  - Files: `deep6v2/orderflow/vpin.py`

---

- [ ] 40. Observability + Alerting + GC Management

  **What to do**:
  - Create `deep6v2/ops/observability.py` — metrics and health monitoring
  - Metrics: bar_processing_latency_ms, signal_evaluation_latency_ms, dom_callbacks_per_second, active_position_count, daily_pnl, connection_uptime_seconds
  - Health checks: DOM freshness (<5s since last update), bar regularity (no gaps >2 min during RTH), Rithmic heartbeat, Kronos model loaded
  - Alert triggers: DOM stale >10s, bar gap >5 min, daily loss cap at 80%, kill switch state change
  - GC management: `gc.disable()` at RTH open, `gc.enable()` at RTH close, log GC stats
  - Expose metrics via `/metrics` endpoint (Prometheus format optional, JSON minimum)
  - Write RED tests for health checks, alert triggers
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 37-39, 41
  - **Parallel Group**: Wave 9
  - **Blocked By**: Tasks 6, 31 (logging, FastAPI)

  **Acceptance Criteria**:

  - [ ] Health checks detect stale DOM, bar gaps, connection loss
  - [ ] Alert triggers fire at correct thresholds
  - [ ] GC disabled during RTH, enabled outside
  - [ ] Metrics endpoint returns JSON with all tracked metrics
  - [ ] Tests pass: `pytest tests_v2/ops/test_observability.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: Stale DOM alert
    Tool: Bash (pytest)
    Steps:
      1. Set last DOM update to 15 seconds ago
      2. Run health check
      3. Assert alert fired with reason="dom_stale"
    Expected Result: Alert triggers when DOM exceeds staleness threshold
    Evidence: .sisyphus/evidence/task-40-stale-alert.txt
  ```

  **Commit**: YES (groups with Wave 9)
  - Files: `deep6v2/ops/observability.py`

---

- [ ] 41. Session Edge Cases — CME Halts, Contract Rollover, DST, Half-Days

  **What to do**:
  - Create `deep6v2/data/session_edge_cases.py` — edge case handlers
  - **CME circuit breakers**: detect halt condition (no ticks for >30s during active session) → trigger FreezeGuard FROZEN state (reuse existing state, not a new PAUSE state) → flatten positions → wait for resume → standard reconciliation before unfreezing
  - **Contract rollover**: NQ quarterly roll detection (March, June, September, December). Auto-switch subscription to new front-month. Alert operator on roll day.
  - **DST transitions**: session boundaries shift when US clocks change. Use ZoneInfo("America/New_York") — handles automatically. Test at DST transition dates.
  - **Half-day sessions**: early close (1:00 PM ET) before major holidays. Configurable holiday calendar. Adjust midday block and session end time.
  - **Weekend/holiday guard**: no trading on weekends or market holidays
  - Write RED tests for each edge case
  - Make tests GREEN

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — with Tasks 37-40
  - **Parallel Group**: Wave 9
  - **Blocked By**: Tasks 5, 7, 10 (clock, connection manager, bar builder)

  **Acceptance Criteria**:

  - [ ] CME halt detection triggers FreezeGuard
  - [ ] Contract rollover auto-detects and alerts
  - [ ] DST transitions handled correctly (no session boundary errors)
  - [ ] Half-day sessions adjust midday block and session end
  - [ ] Weekend/holiday guard prevents trading
  - [ ] Tests pass: `pytest tests_v2/data/test_session_edge_cases.py`

  **QA Scenarios (MANDATORY)**:

  ```
  Scenario: CME halt detection
    Tool: Bash (pytest)
    Steps:
      1. Simulate active RTH session with regular ticks
      2. Stop all ticks for 35 seconds
      3. Assert halt_detected() returns True
      4. Assert FreezeGuard triggered
      5. Resume ticks → assert recovery after reconciliation
    Expected Result: Halt detected, positions flattened, recovery works
    Evidence: .sisyphus/evidence/task-41-halt.txt

  Scenario: DST boundary handling
    Tool: Bash (pytest)
    Steps:
      1. Set EventClock to March DST transition day (2nd Sunday)
      2. Assert is_rth() at 9:30 AM ET (new time) = True
      3. Assert session_bar_index(9:30) = 0
      4. Verify no off-by-one errors around transition
    Expected Result: Correct RTH detection through DST change
    Evidence: .sisyphus/evidence/task-41-dst.txt
  ```

  **Commit**: YES (groups with Wave 9)
  - Files: `deep6v2/data/session_edge_cases.py`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

  **QA Scenarios**:
  ```
  Scenario: Must Have — pre-allocated DOM arrays
    Tool: Grep tool + Bash (python)
    Steps:
      1. Use Grep tool: pattern="array\.array", path="deep6v2/state/", include="*.py" → assert matches found
      2. Run: python -c "from deep6v2.state.dom import DOMState; d = DOMState(); print(type(d._bids))"
      3. Assert output contains "array.array"
    Expected Result: Pre-allocated arrays confirmed
    Evidence: .sisyphus/evidence/f1-dom-arrays.txt

  Scenario: Must NOT Have — no GC during RTH
    Tool: Grep tool
    Steps:
      1. Grep pattern="gc\.disable", path="deep6v2/" → assert matches found in __main__.py or ops/
      2. Grep pattern="gc\.enable", path="deep6v2/" → assert matches found
      3. Grep pattern="gc\.collect\(\)", path="deep6v2/signals/" + path="deep6v2/scoring/" → assert 0 matches in hot path
    Expected Result: GC management present, no manual gc.collect() in hot path
    Evidence: .sisyphus/evidence/f1-gc-management.txt

  Scenario: Must NOT Have — no lock-based concurrency
    Tool: Grep tool
    Steps:
      1. Grep pattern="threading\.Lock|asyncio\.Lock|multiprocessing\.Lock", path="deep6v2/" → assert 0 matches
    Expected Result: No locks in codebase
    Evidence: .sisyphus/evidence/f1-no-locks.txt

  Scenario: Evidence files exist
    Tool: Glob tool
    Steps:
      1. Glob pattern=".sisyphus/evidence/task-*" → count matches → assert ≥ 41
    Expected Result: Evidence files for all implementation tasks
    Evidence: .sisyphus/evidence/f1-evidence-count.txt
  ```

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m pytest deep6v2/ --tb=short` + type check + lint. Review all changed files for: `type: ignore`, bare `except:`, `print()` in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify structlog used consistently, not `logging` stdlib.
  Output: `Tests [PASS/FAIL] | Types [PASS/FAIL] | Lint [N clean/N issues] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run: pytest tests_v2/ --tb=short -q (NOT deep6v2/ — tests live under tests_v2/)
      2. Assert exit code 0
      3. Assert "passed" in output, "0 failed" or no "failed"
    Expected Result: All tests green
    Evidence: .sisyphus/evidence/f2-pytest.txt

  Scenario: No forbidden patterns
    Tool: Grep tool
    Steps:
      1. Grep pattern="type: ignore", path="deep6v2/", include="*.py", output_mode="count" → assert total < 5
      2. Grep pattern="^[^#]*print\(", path="deep6v2/", include="*.py" → filter out test files → assert 0 in prod code
      3. Grep pattern="import logging", path="deep6v2/", include="*.py" → assert 0 matches (must use structlog)
      4. Grep pattern="# TODO|# HACK|# FIXME", path="deep6v2/" → report count
    Expected Result: Minimal type:ignore, no print() in prod, structlog only
    Evidence: .sisyphus/evidence/f2-patterns.txt

  Scenario: DOM benchmark passes
    Tool: Bash (pytest)
    Steps:
      1. Run: pytest tests_v2/state/test_dom.py::test_update_benchmark --benchmark-only
      2. Assert 1000 updates < 1ms in benchmark output
    Expected Result: Sub-millisecond DOM performance
    Evidence: .sisyphus/evidence/f2-benchmark.txt
  ```

- [ ] F3. **Agent-Executed Integration QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (signals → scorer → FSM → risk manager → order generation). Test edge cases: empty DOM, zero-volume bars, session boundaries. Save to `.sisyphus/evidence/final-qa/`. NOTE: "Manual" means agent-driven (not automated unit tests), NOT human-driven. Zero human intervention — the agent executes all scenarios.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: End-to-end pipeline integration
    Tool: Bash (pytest)
    Steps:
      1. Run: pytest tests_v2/integration/test_end_to_end.py -v
      2. Assert 5 synthetic sessions processed
      3. Assert at least 1 session produces IN_POSITION state
      4. Assert all signals evaluated, scorer computed, FSM transitioned
    Expected Result: Full pipeline drives from ticks to trade decisions
    Evidence: .sisyphus/evidence/f3-e2e.txt

  Scenario: Empty DOM edge case
    Tool: Bash (pytest)
    Steps:
      1. Create DOMState with all-zero arrays
      2. Feed to BarBuilder → create bar → run DetectorRegistry
      3. Assert no crash, signals return empty or QUIET
    Expected Result: Graceful handling of empty DOM
    Evidence: .sisyphus/evidence/f3-empty-dom.txt

  Scenario: Session boundary handling
    Tool: Bash (pytest)
    Steps:
      1. Feed ticks crossing RTH open (9:29:59 → 9:30:01)
      2. Assert bar builder starts accumulating at exactly 9:30:00
      3. Feed ticks crossing RTH close (15:59:59 → 16:00:01)
      4. Assert bar builder stops and session resets
    Expected Result: Clean session boundaries
    Evidence: .sisyphus/evidence/f3-session-boundary.txt
  ```

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination: Task N touching Task M's files. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: No scope creep — package structure matches plan
    Tool: Glob tool
    Steps:
      1. Glob pattern="deep6v2/**/*.py" → list all Python files
      2. Compare against plan's expected file list (derived from all task "Files:" entries)
      3. Assert no unexpected files beyond plan scope
    Expected Result: File inventory matches plan exactly
    Evidence: .sisyphus/evidence/f4-file-inventory.txt

  Scenario: Must NOT do compliance
    Tool: Grep tool
    Steps:
      1. Grep pattern="import torch", path="deep6v2/signals/" → assert 0 (Kronos only in deep6v2/kronos/)
      2. Grep pattern="multiprocessing", path="deep6v2/" → assert 0 (single event loop, no multiprocessing)
      3. Grep pattern="lightweight.charts|plotly", path="deep6v2/" → assert 0 (no chart rendering in Python backend)
    Expected Result: All "Must NOT do" rules respected
    Evidence: .sisyphus/evidence/f4-must-not.txt

  Scenario: Cross-task contamination check
    Tool: Bash (git)
    Steps:
      1. For each wave commit, run: git diff --name-only HEAD~1
      2. Verify Wave 3 commits only touch deep6v2/signals/ and tests_v2/signals/
      3. Verify Wave 4 commits only touch deep6v2/scoring/ and tests_v2/scoring/
      4. Flag any file touched by multiple waves unexpectedly
    Expected Result: Clean wave boundaries, no contamination
    Evidence: .sisyphus/evidence/f4-contamination.txt
  ```

---

## Commit Strategy

| Wave | Commit | Message | Pre-commit |
|------|--------|---------|-----------|
| 1 | After all 6 tasks | `feat(foundation): scaffold deep6v2 package with types, config, clock, logging` | `pytest tests_v2/ --co` |
| 2 | After all 6 tasks | `feat(data): async-rithmic connection, DOM state, bar builder, persistence` | `pytest tests_v2/data/ tests_v2/state/` |
| 3 | After all 8 tasks | `feat(signals): 52 signal detectors across 8 categories with fixture parity` | `pytest tests_v2/signals/` |
| 4 | After all 3 tasks | `feat(scoring): two-layer confluence scorer with R3 weights, entry gates, hysteresis` | `pytest tests_v2/scoring/` |
| 5 | After all 4 tasks | `feat(execution): trade decision FSM, risk manager, paper trader, kill switch` | `pytest tests_v2/execution/` |
| 6 | After all 3 tasks | `feat(kronos): E10 bias engine with async inference pipeline` | `pytest tests_v2/kronos/` |
| 7 | After all 4 tasks | `feat(dashboard): FastAPI SSE/WS backend + Next.js MVP (signals, P&L, status)` | `pytest tests_v2/api/` |
| 8 | After all 2 tasks | `feat(tradingview): MCP integration for chart state + visual analysis` | `pytest tests_v2/tradingview/` |
| 9 | After all 5 tasks | `feat(ops): unified startup, GEX, VPIN, observability, session edge cases` | `pytest tests_v2/` |

---

## Success Criteria

### Verification Commands
```bash
pytest tests_v2/ --tb=short                    # Expected: all green, 0 failures
pytest tests_v2/ --benchmark-only             # Expected: DOM 1000 update_level() calls < 1ms
python -m deep6v2 --dry-run                   # Expected: startup, Rithmic connect, clean shutdown
curl http://localhost:8000/health              # Expected: {"status": "ok", "rithmic": "connected"}
curl http://localhost:8000/signals/stream      # Expected: SSE stream of signal events
```

### Final Checklist
- [ ] All "Must Have" present and verified
- [ ] All "Must NOT Have" absent (grep verified)
- [ ] All 52 signals pass against reference fixtures
- [ ] Scorer produces correct tiers for 5 scenario fixtures
- [ ] FSM all 7 states and 11 transitions reachable
- [ ] DOM benchmark: 1,000 `update_level()` calls < 1ms
- [ ] Rithmic test environment connects and receives data
- [ ] Dashboard MVP functional (signal feed, P&L, status)
- [ ] TDD coverage: every module has corresponding test file
- [ ] structlog JSON output across all modules
