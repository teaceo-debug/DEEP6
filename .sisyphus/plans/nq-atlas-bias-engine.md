# NQ ATLAS — Options-Positioning Bias Engine

## TL;DR

> **Quick Summary**: Build a focused, custom options-positioning bias engine that ingests QQQ equity options data from Massive.com, computes GEX/vanna/charm/signed-flow analytics, and uses Claude AI to deliver a clear bullish/bearish bias for NQ futures with conviction level and key price levels — all served via an auto-refreshing FastAPI dashboard.
> 
> **Deliverables**:
> - `nq_atlas/` Python package (13 files) — complete options bias engine
> - `run_atlas.py` — single entry point, starts FastAPI server at localhost:8766
> - `tests_nq_atlas/` — test suite covering all modules
> - Auto-refreshing dark-mode dashboard showing: bias direction, conviction, NQ levels, raw analytics, AI narrative
> 
> **Estimated Effort**: Medium (3-5 days with parallel execution)
> **Parallel Execution**: YES — 4 waves, peak 5 concurrent tasks
> **Critical Path**: Task 1 → Task 2 → Task 3 → Tasks 4-8 → Task 9 → Task 10 → Task 11

---

## Context

### Original Request
Build NQ ATLAS as a focused tool providing an NQ trader's alpha on whether the market is bullish or bearish. Custom-built from scratch using Massive.com API. Purpose-built, fast, efficient — no academic bloat, no prior code imports.

### Interview Summary
**Key Discussions**:
- **Scope**: ONE job — is NQ bullish or bearish right now? With conviction and key levels.
- **Data source**: Massive.com API only (OPRA equity options — QQQ as primary proxy for NQ)
- **Output**: Dashboard only (FastAPI web UI, auto-refreshing)
- **Integration**: Independent service — NOT feeding into DEEP6's 44-signal scorer
- **Tests**: After core works (pytest infrastructure exists)
- **Platform**: Windows (this machine)
- **Build approach**: From scratch. No prior NQ ATLAS code. Only domain knowledge from handoff informs architecture decisions.

**Research Findings**:
- DEEP6 has Python 3.12+, FastAPI, DuckDB, pytest — infrastructure exists but no options analytics
- Massive.com = rebranded Polygon.io — official Python SDK available (`polygon-api-client` or `massive-api-client`)
- WebSocket cap of 1,000 contracts makes REST polling the right choice for full-chain analysis
- QQQ→NQ ratio drifts 1-2% intraday — must use live NQ price, not static multiplier
- Three evidence-backed edges: (1) dealer hedging → intraday momentum, (2) vanna rallies post-events, (3) 0DTE gamma sign → vol regime

### Metis Review
**Identified Gaps** (addressed):
- Massive.com subscription tier validation added as first validation step in Task 3
- Greeks availability check built into data client — uses API Greeks when available, falls back to IV solver
- 0DTE gamma singularity handled with T≥1/365 clamping in GEX engine
- Low-liquidity strike filtering (OI≥100) built into chain processing
- Deep ITM/missing Greeks handled gracefully (skip, don't crash)
- After-hours/weekend state shows "MARKET CLOSED" with last-known bias + staleness warning
- API outage shows stale data with visual degraded indicator
- Port 8766 chosen to avoid conflict with existing DEEP6 server on 8765
- Multiple QQQ expirations aggregated by default, term-bucketed for display

---

## Work Objectives

### Core Objective
Build a self-contained Python service that continuously ingests QQQ options data from Massive.com, computes dealer positioning analytics (GEX, vanna/charm, signed premium flow), converts to NQ-equivalent levels, feeds a structured prompt to Claude AI for bias interpretation, and serves the result on an auto-refreshing web dashboard at `http://localhost:8766`.

### Concrete Deliverables
- `nq_atlas/` package with 13 Python/HTML files
- `run_atlas.py` entry point
- `tests_nq_atlas/` test directory
- Dashboard accessible at `http://localhost:8766`
- JSON API at `GET /bias`, `GET /state`, `GET /health`

### Definition of Done
- [ ] `python run_atlas.py` starts server, begins polling Massive.com, updates dashboard
- [ ] `curl http://localhost:8766/bias` returns JSON with `direction`, `conviction`, `levels`, `updated_at`
- [ ] Dashboard auto-refreshes and shows current bias within 2 polling cycles of startup
- [ ] `pytest tests_nq_atlas/ -v` passes all tests
- [ ] System handles Massive.com API outage gracefully (shows stale data, no crash)
- [ ] System handles Claude API outage gracefully (shows raw data without narrative)

### Must Have
- GEX computation: gamma flip, call wall, put wall, net GEX sign
- Vanna/charm computation: dealer hedge exposure direction
- Signed premium flow: net smart-money direction
- QQQ→NQ level conversion using live price ratio
- Claude AI interpretation producing bullish/bearish + conviction (0-100) + key levels
- Auto-refreshing dashboard showing all of the above
- Staleness detection and degraded-mode indicators
- Configurable via environment variables (API keys, refresh interval, Claude model, port)

### Must NOT Have (Guardrails)
- **No SVI vol surface fitting** — use Massive.com pre-computed Greeks. If unavailable, use scipy.optimize.brentq for IV, NOT a full surface model
- **No SPX/SPY/Mag7 support in v1** — QQQ only. Single underlying keeps it focused
- **No WebSocket streaming for options** — REST polling every 10s is sufficient and faster than WS for full-chain snapshots
- **No integration with DEEP6's 44-signal scorer** — this is independent
- **No backtesting, replay, or historical analysis** — out of scope
- **No trade execution or signal triggering** — this is a BIAS ENGINE (opinion), not a trade signal
- **No plugin system or "generic analytics framework"** — hardcode the three engines directly
- **No abstract base classes** — concrete classes, Protocol only if needed for test mocking
- **No CLI entry point** — runs as FastAPI server only
- **No comprehensive error handling for future scenarios** (multi-exchange, failover, circuit breakers)
- **No over-documentation** — one-line docstrings on public functions, no JSDoc-style blocks

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest 8.0+, pytest-asyncio, tests_v2/ with 44 files)
- **Automated tests**: Tests-after (build core first, add tests in final task)
- **Framework**: pytest with asyncio_mode="auto" (matches existing DEEP6 config)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API/Backend**: Use Bash (curl) — Send requests, assert status + response fields
- **Library/Module**: Use Bash (python -c / pytest) — Import, call functions, compare output
- **Dashboard/UI**: Use Playwright — Navigate, verify elements render, screenshot

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — scaffolding + types):
├── Task 1: Package scaffolding + pyproject.toml updates          [quick]
├── Task 2: Core types + state object + NQ mapper utility         [quick]

Wave 2 (Data + Analytics — MAX PARALLEL after Wave 1):
├── Task 3: Massive.com data client + chain ingestion             [unspecified-high]
├── Task 4: GEX engine                                            [deep]
├── Task 5: Vanna/charm engine                                    [deep]
├── Task 6: Signed premium flow engine                            [deep]
├── Task 7: AI bias interpreter (Claude API)                      [unspecified-high]

Wave 3 (Server + Integration — after Wave 2):
├── Task 8: FastAPI server + API endpoints                        [unspecified-high]
├── Task 9: Dashboard HTML UI                                     [visual-engineering]
├── Task 10: Asyncio orchestrator + entry point                   [deep]

Wave 4 (Tests — after Wave 3):
├── Task 11: Test suite                                           [unspecified-high]

Wave FINAL (Verification — 4 parallel reviews):
├── F1: Plan compliance audit                                     [oracle]
├── F2: Code quality review                                       [unspecified-high]
├── F3: Real QA execution                                         [unspecified-high]
├── F4: Scope fidelity check                                      [deep]
→ Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3-7 | 1 |
| 2 | 1 | 3-10 | 1 |
| 3 | 1, 2 | 8, 10 | 2 |
| 4 | 1, 2 | 8, 10 | 2 |
| 5 | 1, 2 | 8, 10 | 2 |
| 6 | 1, 2 | 8, 10 | 2 |
| 7 | 1, 2 | 8, 10 | 2 |
| 8 | 3-7 | 9, 10 | 3 |
| 9 | 8 | 10 | 3 |
| 10 | 3-9 | 11 | 3 |
| 11 | 10 | F1-F4 | 4 |
| F1-F4 | 11 | — | FINAL |

**Critical Path**: T1 → T2 → T4 (GEX, longest analytics) → T8 → T10 → T11 → F1-F4
**Parallel Speedup**: ~55% faster than sequential
**Max Concurrent**: 5 (Wave 2)

### Agent Dispatch Summary

| Wave | Tasks | Categories |
|------|-------|-----------|
| 1 | 2 | T1 → `quick`, T2 → `quick` |
| 2 | 5 | T3 → `unspecified-high`, T4 → `deep`, T5 → `deep`, T6 → `deep`, T7 → `unspecified-high` |
| 3 | 3 | T8 → `unspecified-high`, T9 → `visual-engineering`, T10 → `deep` |
| 4 | 1 | T11 → `unspecified-high` |
| FINAL | 4 | F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep` |

---

## TODOs

- [x] 1. Package Scaffolding + Configuration + Dependencies

  **What to do**:
  - Create `nq_atlas/` package directory with `__init__.py` (exports version string)
  - Create `nq_atlas/config.py` using `pydantic_settings.BaseSettings` with `env_prefix="NQ_ATLAS_"`:
    - `massive_api_key: str` — Massive.com API key
    - `anthropic_api_key: str` — Claude API key
    - `anthropic_model: str = "claude-haiku-4-5-20251001"` — default to Haiku (fast + cheap)
    - `refresh_interval_sec: int = 10` — options chain polling cadence (as fast as API allows; 10s default, Massive rate limits may require adjustment)
    - `ai_refresh_sec: int = 15` — Claude interpretation cadence (Haiku responds in ~1s; 15s balances speed vs cost at ~$20-40/day)
    - `host: str = "0.0.0.0"`
    - `port: int = 8766` — avoids conflict with DEEP6's 8765
    - `underlying: str = "QQQ"` — primary underlying for options chain
    - `min_oi: int = 100` — minimum open interest filter for strikes
    - `log_level: str = "INFO"`
  - Create `run_atlas.py` at repo root (skeleton only — `if __name__ == "__main__": pass`)
  - Create `.env.atlas.example` with all config variables documented
  - Update `pyproject.toml`: add `nq_atlas` to packages, add dependencies:
    - `polygon-api-client>=1.14` (Massive.com SDK — still published under Polygon name on PyPI)
    - `anthropic>=0.40`
    - `scipy>=1.14`
  - Create `tests_nq_atlas/` directory with empty `conftest.py`

  **Must NOT do**:
  - Do NOT create abstract base classes or plugin systems
  - Do NOT add SPX/SPY configuration — QQQ only
  - Do NOT import anything from `deep6v2/` — this package is independent

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure scaffolding — creating files, directories, config classes. No complex logic.
  - **Skills**: []
    - No specialized skills needed for boilerplate creation.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 2)
  - **Blocks**: Tasks 2, 3, 4, 5, 6, 7 (everything needs the package structure)
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References** (existing code to follow):
  - `deep6v2/config/app.py` — Pydantic BaseSettings pattern with env_prefix, nested delimiter. Copy this exact style.
  - `deep6v2/__init__.py` — Package init pattern with version export
  - `pyproject.toml` — Existing dependency declarations and package listing. Add nq_atlas alongside deep6v2.

  **WHY Each Reference Matters**:
  - `app.py` shows the DEEP6 convention for config: `model_config = SettingsConfigDict(env_prefix=..., env_nested_delimiter="__")`. Match this exactly.
  - `pyproject.toml` shows how dependencies are declared — follow same format (name>=version).

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Package imports successfully
    Tool: Bash (python -c)
    Preconditions: nq_atlas/ directory exists with __init__.py
    Steps:
      1. Run: python -c "import nq_atlas; print(nq_atlas.__version__)"
      2. Assert output contains a version string (e.g., "0.1.0")
    Expected Result: Exit code 0, version printed
    Failure Indicators: ImportError, ModuleNotFoundError
    Evidence: .sisyphus/evidence/task-1-package-import.txt

  Scenario: Config loads from environment
    Tool: Bash (python -c with env vars)
    Preconditions: nq_atlas/config.py exists
    Steps:
      1. Run: NQ_ATLAS_MASSIVE_API_KEY=test NQ_ATLAS_ANTHROPIC_API_KEY=test python -c "from nq_atlas.config import Settings; s = Settings(); print(s.port, s.refresh_interval_sec)"
      2. Assert output: "8766 60"
    Expected Result: Config loads with defaults, env vars override
    Failure Indicators: ValidationError, missing required fields without env vars
    Evidence: .sisyphus/evidence/task-1-config-load.txt

  Scenario: Dependencies install cleanly
    Tool: Bash (pip)
    Preconditions: pyproject.toml updated
    Steps:
      1. Run: pip install polygon-api-client anthropic scipy --dry-run
      2. Assert: all packages resolve without conflicts
    Expected Result: No dependency conflicts
    Failure Indicators: ResolutionImpossible, version conflict
    Evidence: .sisyphus/evidence/task-1-deps-install.txt
  ```

  **Commit**: YES (groups with Task 2)
  - Message: `feat(nq-atlas): scaffold package with types, config, and state`
  - Files: `nq_atlas/__init__.py`, `nq_atlas/config.py`, `run_atlas.py`, `.env.atlas.example`, `pyproject.toml`, `tests_nq_atlas/conftest.py`
  - Pre-commit: `python -c "from nq_atlas.config import Settings"`

---

- [x] 2. Core Types + State Object + NQ Mapper Utility

  **What to do**:
  - Create `nq_atlas/types.py` with frozen Pydantic models:
    - `OptionsContract`: symbol, strike, expiry, call_put, bid, ask, last, volume, oi, greeks (delta, gamma, theta, vega, iv) — all Optional[float] (Greeks may be missing from API)
    - `ChainSnapshot`: underlying, spot_price, timestamp, contracts: list[OptionsContract]
    - `GEXResult`: spot, flip_level, call_wall, put_wall, net_gex, regime_sign (+1/-1), by_expiry: dict[str, float]
    - `VannaCharmResult`: net_vanna_exposure, net_charm_exposure, dealer_hedge_direction (+1/-1), vanna_per_iv_bp
    - `FlowResult`: signed_premium_5m, signed_premium_15m, net_direction (+1/-1), z_score
    - `BiasOutput`: direction (BULLISH/BEARISH/NEUTRAL), conviction (0-100), levels: NQLevels, narrative: str, updated_at: datetime, degraded: bool
    - `NQLevels`: gex_flip, call_wall, put_wall, support, resistance
    - `FullState`: spots, gex, vanna_charm, flow, bias, last_chain_ts, last_ai_ts, errors
  - Create `nq_atlas/state.py`:
    - `AtlasState` class (mutable, NOT frozen) holding current system state
    - `degraded() -> bool` — True if any critical data older than `2 × refresh_interval`
    - `snapshot_dict() -> dict` — JSON-serializable snapshot of full state
    - Thread-safe reads (single-writer per field, asyncio guarantees no preemption)
  - Create `nq_atlas/nq_mapper.py`:
    - `map_qqq_to_nq(qqq_level: float, qqq_spot: float, nq_spot: float) -> float` — converts QQQ price level to NQ equivalent: `qqq_level / qqq_spot * nq_spot`
    - `map_chain_levels(gex: GEXResult, qqq_spot: float, nq_spot: float) -> NQLevels` — batch convert all levels

  **Must NOT do**:
  - Do NOT make types generic or parameterized — concrete types for THIS system only
  - Do NOT add validators beyond basic range checks (conviction 0-100, direction in enum)
  - Do NOT create inheritance hierarchies — flat models only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Data modeling — define shapes, no complex logic. Straightforward Pydantic.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Task 1)
  - **Blocks**: Tasks 3-10 (all downstream code uses these types)
  - **Blocked By**: Task 1 (needs package structure to exist)

  **References**:

  **Pattern References**:
  - `deep6v2/types/bar.py` — Frozen Pydantic BaseModel pattern with `model_config = ConfigDict(frozen=True)`. Match this style exactly.
  - `deep6v2/types/signal.py` — How DEEP6 defines signal output types (SignalResult, SignalDirection enum). Use as style reference for BiasOutput.
  - `deep6v2/types/dom.py` — DOMSnapshot model. Shows how DEEP6 types handle optional numeric fields.

  **External References**:
  - Handoff §3 "Canonical output JSON schema" (lines 158-194) — Use the `bias`, `gex`, `vanna_charm`, `nq_levels` key structure as inspiration for type field names. Don't copy verbatim — adapt to our focused scope.
  - Handoff §11 "State object" (lines 434-454) — AtlasState design inspiration. Our state is simpler (no mag7, no premium_tape detail).

  **WHY Each Reference Matters**:
  - `bar.py` demonstrates the exact Pydantic config pattern DEEP6 uses — frozen models with explicit ConfigDict
  - Handoff JSON schema provides field naming conventions (`_b` = billions, `_z` = z-score) — adopt these for consistency

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Types construct and serialize correctly
    Tool: Bash (python -c)
    Preconditions: nq_atlas/types.py exists
    Steps:
      1. Run: python -c "from nq_atlas.types import BiasOutput, NQLevels; b = BiasOutput(direction='BULLISH', conviction=75, levels=NQLevels(gex_flip=21200, call_wall=21400, put_wall=21000, support=21050, resistance=21350), narrative='GEX positive, vanna supportive', updated_at='2026-05-14T10:00:00', degraded=False); print(b.model_dump_json())"
      2. Assert output is valid JSON with all fields present
    Expected Result: JSON string with direction="BULLISH", conviction=75, all level fields
    Failure Indicators: ValidationError, missing fields, serialization error
    Evidence: .sisyphus/evidence/task-2-types-serialize.txt

  Scenario: Frozen types reject mutation
    Tool: Bash (python -c)
    Preconditions: BiasOutput is frozen
    Steps:
      1. Run: python -c "from nq_atlas.types import BiasOutput, NQLevels; b = BiasOutput(direction='BULLISH', conviction=75, levels=NQLevels(gex_flip=0,call_wall=0,put_wall=0,support=0,resistance=0), narrative='test', updated_at='2026-05-14T10:00:00', degraded=False); b.direction = 'BEARISH'"
      2. Assert: raises ValidationError or AttributeError
    Expected Result: Exception on mutation attempt
    Failure Indicators: Mutation succeeds silently
    Evidence: .sisyphus/evidence/task-2-types-frozen.txt

  Scenario: NQ mapper converts levels correctly
    Tool: Bash (python -c)
    Preconditions: nq_atlas/nq_mapper.py exists
    Steps:
      1. Run: python -c "from nq_atlas.nq_mapper import map_qqq_to_nq; nq = map_qqq_to_nq(qqq_level=520.0, qqq_spot=518.0, nq_spot=21240.0); print(f'{nq:.1f}')"
      2. Assert output: approximately 21320.8 (520/518 * 21240 = 21322.0)
    Expected Result: NQ level = QQQ level × (NQ spot / QQQ spot)
    Failure Indicators: Wrong math, division by zero on qqq_spot=0
    Evidence: .sisyphus/evidence/task-2-nq-mapper.txt

  Scenario: State degraded detection works
    Tool: Bash (python -c)
    Preconditions: nq_atlas/state.py exists
    Steps:
      1. Run: python -c "from nq_atlas.state import AtlasState; s = AtlasState(); print('degraded:', s.degraded())"
      2. Assert: degraded() returns True on fresh state (no data yet)
    Expected Result: True (no chain data loaded = degraded)
    Failure Indicators: Returns False when no data exists
    Evidence: .sisyphus/evidence/task-2-state-degraded.txt
  ```

  **Commit**: YES (groups with Task 1)
  - Message: `feat(nq-atlas): scaffold package with types, config, and state`
  - Files: `nq_atlas/types.py`, `nq_atlas/state.py`, `nq_atlas/nq_mapper.py`
  - Pre-commit: `python -c "from nq_atlas.types import BiasOutput, GEXResult, VannaCharmResult, FlowResult"`

- [x] 3. Massive.com Data Client + Chain Ingestion

  **What to do**:
  - Create `nq_atlas/massive_client.py`:
    - `MassiveClient` class wrapping the `polygon-api-client` SDK (Massive.com = Polygon rebranded)
    - `__init__(api_key: str)` — initialize REST client
    - `async validate_connection() -> dict` — test API access, return tier info (Greeks available? Real-time?)
    - `async get_options_chain(underlying: str = "QQQ") -> ChainSnapshot` — fetch full chain via `GET /v3/snapshot/options/{underlying}`, parse into ChainSnapshot type
      - Filter: only contracts with OI ≥ `min_oi` (default 100)
      - Filter: skip contracts where ALL Greeks are None/zero (deep ITM gaps)
      - Clamp: `time_to_expiry = max(T, 1/365)` to prevent 0DTE gamma singularity
      - Group by expiry bucket: 0DTE, 1-7 DTE, 8-30 DTE, 31+ DTE
    - `async get_nq_quote() -> float` — fetch NQ futures quote from Massive.com for QQQ→NQ conversion. Use `GET /v2/aggs/ticker/NQ1!/prev` or equivalent futures endpoint. If unavailable, fall back to index proxy `GET /v2/last/trade/I:NDX` × multiplier.
    - `async poll_loop(state: AtlasState, interval: int)` — async polling loop that calls `get_options_chain()` every `interval` seconds, updates `state.chain`, `state.spots`, `state.last_chain_ts`
  - Handle API errors gracefully:
    - 401: log "Invalid API key", raise ConfigError
    - 403: log "Subscription tier insufficient for this endpoint"
    - 429: exponential backoff with jitter (start 5s, max 120s)
    - 5xx / timeout: retry 3× with backoff, then set `state.degraded`
  - If API response does NOT include Greeks (lower-tier subscription):
    - Log warning: "Greeks not available from API. Computing from bid/ask IV."
    - Use `scipy.optimize.brentq` to solve Black-Scholes for IV from mid-price
    - Compute delta, gamma from solved IV using standard BS formulas
    - This is the fallback path — NOT the preferred path

  **Must NOT do**:
  - Do NOT use WebSocket streaming for options (1,000-contract cap is too limiting)
  - Do NOT build a generic "data provider" abstraction — this client is for Massive.com only
  - Do NOT cache chain data beyond the current snapshot — always use latest

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: API integration with error handling, async polling, SDK usage — moderate complexity requiring careful handling of edge cases.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 5, 6, 7)
  - **Blocks**: Tasks 8, 10 (server and orchestrator need data)
  - **Blocked By**: Tasks 1, 2 (needs package + types)

  **References**:

  **Pattern References**:
  - `deep6v2/data/rithmic_client.py` — Async client wrapper pattern with ConnectionState FSM. Shows how DEEP6 wraps an external SDK with async methods and error handling. Follow the same structural approach.
  - `deep6v2/config/app.py` — How config values are injected into service classes.

  **External References**:
  - Polygon.io REST API reference: `https://polygon.io/docs/options/get_v3_snapshot_options__underlyingasset` — This is the exact endpoint. Massive.com uses same API.
  - `polygon-api-client` PyPI: `https://pypi.org/project/polygon-api-client/` — Official SDK. Import as `from polygon import RESTClient`.
  - Handoff §2.1 `ingest_massive.py` description (lines 69) — Mentions "Polygon-compatible URLs" confirming Massive uses Polygon API format.
  - Handoff §6 gap audit (lines 269) — Notes "QQQ × ratio approximation" drifts 5-15 NQ points. Our `get_nq_quote()` addresses this with live price.

  **WHY Each Reference Matters**:
  - `rithmic_client.py` shows DEEP6's pattern for wrapping external data SDKs — connection state tracking, async methods, error isolation. Match this pattern.
  - Polygon docs are the authoritative API reference. The snapshot endpoint returns contracts with Greeks (if tier supports it).

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Client initializes and validates connection
    Tool: Bash (python -c)
    Preconditions: polygon-api-client installed, nq_atlas/massive_client.py exists
    Steps:
      1. Run: python -c "from nq_atlas.massive_client import MassiveClient; c = MassiveClient(api_key='test_key'); print('initialized')"
      2. Assert: no import errors, client object created
    Expected Result: "initialized" printed, exit code 0
    Failure Indicators: ImportError, SDK not found
    Evidence: .sisyphus/evidence/task-3-client-init.txt

  Scenario: Chain parsing handles missing Greeks gracefully
    Tool: Bash (pytest)
    Preconditions: Test file with mocked API response
    Steps:
      1. Create mock response with 5 contracts: 3 with full Greeks, 1 with partial Greeks, 1 with no Greeks
      2. Run: parse chain → assert 4 contracts returned (1 with no Greeks filtered out)
      3. Assert all remaining contracts have at minimum delta and gamma populated
    Expected Result: Missing-Greeks contracts filtered, partial-Greeks contracts preserved
    Failure Indicators: Crash on None Greeks, all contracts filtered
    Evidence: .sisyphus/evidence/task-3-chain-parse.txt

  Scenario: OI filter removes low-liquidity strikes
    Tool: Bash (pytest)
    Preconditions: Mock response with contracts at varying OI levels
    Steps:
      1. Create mock: 10 contracts with OI = [0, 50, 99, 100, 150, 500, 1000, 5000, 10000, 50000]
      2. Parse with min_oi=100
      3. Assert: 7 contracts returned (OI ≥ 100)
    Expected Result: Contracts with OI < 100 excluded
    Failure Indicators: Wrong count, filter not applied
    Evidence: .sisyphus/evidence/task-3-oi-filter.txt

  Scenario: API error handling — 429 rate limit
    Tool: Bash (pytest)
    Preconditions: Mock HTTP client returning 429
    Steps:
      1. Mock REST client to return 429 on first call, 200 on second
      2. Call get_options_chain()
      3. Assert: retried with backoff, eventually succeeded
    Expected Result: Chain returned after retry
    Failure Indicators: Crash on 429, no retry
    Evidence: .sisyphus/evidence/task-3-rate-limit.txt
  ```

  **Commit**: YES
  - Message: `feat(nq-atlas): add Massive.com data client with chain ingestion`
  - Files: `nq_atlas/massive_client.py`
  - Pre-commit: `python -c "from nq_atlas.massive_client import MassiveClient"`

---

- [x] 4. GEX Engine (Gamma Exposure)

  **What to do**:
  - Create `nq_atlas/gex.py`:
    - `GEXEngine` class:
      - `compute(chain: ChainSnapshot) -> GEXResult` — main computation
      - For each contract in chain:
        - `contract_gex = gamma × OI × 100 × spot² × 0.01`
        - Sign convention: calls contribute POSITIVE GEX, puts contribute NEGATIVE GEX
      - **Gamma Flip Level**: price where cumulative GEX crosses zero (net dealer exposure flips from long gamma to short gamma). Interpolate between nearest positive/negative GEX prices.
      - **Call Wall**: strike with highest positive GEX (largest call gamma × OI)
      - **Put Wall**: strike with highest absolute negative GEX (largest put gamma × OI)
      - **Net GEX**: sum of all contract GEX — positive = dealers long gamma (mean-reverting), negative = dealers short gamma (trending)
      - **Regime Sign**: +1 if net GEX > 0 (suppress vol), -1 if net GEX < 0 (amplify vol)
      - **By-expiry breakdown**: aggregate GEX per expiry bucket (0DTE, 1-7, 8-30, 31+)
    - Handle edge cases:
      - If gamma is None for a contract → skip that contract
      - If chain has < 10 valid contracts → return degraded GEXResult with `regime_sign=0`
      - 0DTE contracts: use `T = max(T_actual, 1/365)` — already clamped in ingestion, but double-check here

  **Must NOT do**:
  - Do NOT build SVI vol surface to recompute Greeks — use API-provided gamma directly
  - Do NOT "intraday-adjust OI" — use snapshot OI as-is for v1 (the handoff's intraday OI adjustment is future work)
  - Do NOT add term-structure modeling — simple expiry bucketing only

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core financial computation with specific math formulas, edge case handling, and domain-specific sign conventions that must be exactly right.
  - **Skills**: [`trading-knowledge`]
    - `trading-knowledge`: GEX is a core trading concept — this skill provides context on gamma exposure, dealer positioning, and how GEX flip levels work.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 5, 6, 7)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `deep6v2/signals/absorption.py` — Signal engine pattern in DEEP6. Shows how a compute function takes input data and returns a typed result. Follow similar function signature style.

  **External References**:
  - SqueezeMetrics (2017) GEX white paper — definitive reference for gamma exposure calculation formula and sign conventions
  - Handoff §5 code patterns table (line 250) — GEX engine formula: `gamma × OI × 100 × spot² × 0.01`. This is the canonical formula.
  - Handoff §4 edge claim #3 (line 216) — "0DTE dealer net gamma sign predicts intraday vol regime" — the regime_sign output is the key signal

  **WHY Each Reference Matters**:
  - SqueezeMetrics defines the standard GEX formula used by SpotGamma, MenthorQ, and all commercial GEX tools. Our implementation MUST match this.
  - Handoff §4 explains WHY GEX sign matters: positive gamma = dealers suppress vol (mean-revert), negative gamma = dealers amplify vol (trend).

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: GEX computation with known test vector
    Tool: Bash (python -c)
    Preconditions: nq_atlas/gex.py exists
    Steps:
      1. Create a minimal chain: QQQ spot=500, one ATM call (strike=500, gamma=0.005, OI=10000), one ATM put (strike=500, gamma=0.005, OI=8000)
      2. Compute: call_gex = 0.005 × 10000 × 100 × 500² × 0.01 = +$1,250,000
      3. Compute: put_gex = -(0.005 × 8000 × 100 × 500² × 0.01) = -$1,000,000
      4. Net GEX = +$250,000 → regime_sign = +1
      5. Assert GEXResult.net_gex ≈ 250000, regime_sign = 1
    Expected Result: Net GEX = $250,000, positive regime (dealers long gamma)
    Failure Indicators: Wrong sign convention, math error, missing × 100 multiplier
    Evidence: .sisyphus/evidence/task-4-gex-test-vector.txt

  Scenario: Gamma flip level interpolation
    Tool: Bash (pytest)
    Preconditions: Chain with GEX crossing zero between two strikes
    Steps:
      1. Create chain where cumulative GEX is positive at strike 495, negative at strike 505
      2. Compute flip level — should interpolate between 495 and 505
      3. Assert: flip_level is between 495 and 505 (not at a strike boundary)
    Expected Result: Flip level interpolated, not snapped to nearest strike
    Failure Indicators: Flip at exact strike, no interpolation, flip outside chain range
    Evidence: .sisyphus/evidence/task-4-gex-flip.txt

  Scenario: Degraded result on thin chain
    Tool: Bash (python -c)
    Preconditions: gex.py handles edge cases
    Steps:
      1. Create chain with only 5 contracts (below 10-contract threshold)
      2. Compute GEX
      3. Assert: regime_sign = 0 (degraded/uncertain)
    Expected Result: GEXResult with regime_sign=0 indicating insufficient data
    Failure Indicators: Crash, or regime_sign = ±1 despite thin data
    Evidence: .sisyphus/evidence/task-4-gex-degraded.txt
  ```

  **Commit**: YES (groups with Tasks 5, 6)
  - Message: `feat(nq-atlas): add GEX, vanna/charm, and flow analytics engines`
  - Files: `nq_atlas/gex.py`
  - Pre-commit: `python -c "from nq_atlas.gex import GEXEngine"`

---

- [x] 5. Vanna/Charm Engine

  **What to do**:
  - Create `nq_atlas/vanna_charm.py`:
    - `VannaCharmEngine` class:
      - `compute(chain: ChainSnapshot) -> VannaCharmResult`
      - **Vanna** (∂Δ/∂σ): measures how dealer delta changes when IV moves
        - Formula: `vanna = -pdf(d1) × d2 / σ` where d1, d2 are BS d-values
        - Net vanna exposure = Σ(vanna × OI × 100 × spot) across all contracts
        - If IV drops (post-event vol crush): positive net vanna → dealers must BUY underlying to hedge → BULLISH pressure
        - If IV rises: negative net vanna → dealers must SELL underlying → BEARISH pressure
      - **Charm** (∂Δ/∂t): measures how dealer delta changes as time passes
        - Formula: complex — use scipy or direct BS partial derivative
        - Net charm exposure = Σ(charm × OI × 100 × spot) per day
        - Charm tells you: as time decays, are dealers mechanically buying or selling?
      - **Dealer hedge direction**: combined signal from vanna + charm
        - +1 = dealers are net buying underlying (BULLISH pressure)
        - -1 = dealers are net selling underlying (BEARISH pressure)
      - If API provides vanna/charm directly: USE THEM (no recomputation)
      - If API does NOT provide vanna/charm: compute from delta, gamma, IV, T using BS formulas:
        - `d1 = (ln(S/K) + (r + σ²/2)T) / (σ√T)`
        - `d2 = d1 - σ√T`
        - `vanna = -pdf(d1) × d2 / σ`
        - `charm = -pdf(d1) × (2rT - d2×σ√T) / (2T×σ√T)` (for calls)
      - Use `r = 0.05` (risk-free rate, hardcoded, update quarterly) or fetch from API if available

  **Must NOT do**:
  - Do NOT build a full Black-Scholes pricing engine — only compute the two Greeks we need
  - Do NOT implement Heston or SABR models
  - Do NOT add dividend yield adjustments — use BS without dividends for v1

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Financial math with specific partial derivatives, probability density functions, and sign convention logic that requires careful implementation.
  - **Skills**: [`trading-knowledge`]
    - `trading-knowledge`: Vanna and charm are advanced Greeks — this skill covers dealer hedging mechanics.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4, 6, 7)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: Tasks 1, 2

  **References**:

  **External References**:
  - Handoff §5 code patterns (line 246) — `bs_greeks()` function description: "Black-Scholes Greeks + vanna/charm". Lists the canonical formulas.
  - Handoff §4 edge claim #2 (line 215) — "Vol-crush vanna rallies are scheduled and front-runnable... ATM IV compresses 3-8 vol points → dealer delta unwind buys mechanically"
  - John Hull "Options, Futures, and Other Derivatives" — BS Greeks formulas (standard reference)
  - Gatheral (2004) "A Parsimonious Arbitrage-Free Implied Volatility Parameterization" — referenced in handoff for understanding vol surface behavior

  **WHY Each Reference Matters**:
  - The handoff's edge claim #2 is the entire REASON vanna matters — it explains the causal mechanism (vol drops → vanna → dealer buying → NQ rallies)
  - Getting the vanna sign convention right is critical. Wrong sign = opposite bias. The handoff's `bs_greeks()` is the authoritative reference.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Vanna computation with known values
    Tool: Bash (python -c)
    Preconditions: nq_atlas/vanna_charm.py exists
    Steps:
      1. Create ATM option: S=500, K=500, T=30/365, σ=0.20, r=0.05
      2. Compute d1, d2, vanna manually: d1≈0.157, d2≈0.105, vanna≈-0.209
      3. Run engine with single contract (OI=10000)
      4. Assert: net_vanna_exposure matches hand-calculated value within 1%
    Expected Result: Vanna exposure = vanna × OI × 100 × spot ≈ expected value
    Failure Indicators: Wrong sign, off by orders of magnitude, NaN
    Evidence: .sisyphus/evidence/task-5-vanna-known.txt

  Scenario: Dealer hedge direction on vol-crush scenario
    Tool: Bash (pytest)
    Preconditions: Engine handles vol-crush logic
    Steps:
      1. Create chain with net positive vanna (typical pre-expiry, ATM-heavy call OI)
      2. Simulate: "IV is dropping" context (positive net vanna in a falling-IV environment)
      3. Assert: dealer_hedge_direction = +1 (bullish — dealers buying to hedge)
    Expected Result: Positive vanna + falling IV = bullish dealer flow
    Failure Indicators: Wrong direction, direction=0
    Evidence: .sisyphus/evidence/task-5-vanna-volcrush.txt

  Scenario: Handles missing vanna in API gracefully
    Tool: Bash (pytest)
    Preconditions: Contracts without vanna field
    Steps:
      1. Create chain where all contracts have delta, gamma, IV but NO vanna/charm
      2. Engine should compute vanna from BS formula using delta, gamma, IV, T
      3. Assert: VannaCharmResult populated with computed values
    Expected Result: Fallback computation produces valid vanna/charm
    Failure Indicators: Returns zero, crashes, skips all contracts
    Evidence: .sisyphus/evidence/task-5-vanna-fallback.txt
  ```

  **Commit**: YES (groups with Tasks 4, 6)
  - Message: `feat(nq-atlas): add GEX, vanna/charm, and flow analytics engines`
  - Files: `nq_atlas/vanna_charm.py`
  - Pre-commit: `python -c "from nq_atlas.vanna_charm import VannaCharmEngine"`

---

- [x] 6. Signed Premium Flow Engine

  **What to do**:
  - Create `nq_atlas/flow.py`:
    - `FlowEngine` class:
      - `update(trade: dict) -> None` — process individual option trade tick
      - `compute() -> FlowResult` — return current flow state
      - **Aggressor Classification** (Lee-Ready algorithm):
        - If trade price > midpoint(bid, ask) → buyer-initiated (CALL buy = bullish, PUT buy = bearish)
        - If trade price < midpoint → seller-initiated (CALL sell = bearish, PUT sell = bullish)
        - If trade price = midpoint → use tick rule (compare to previous trade)
      - **Signed Premium**: for each classified trade:
        - `signed_premium = trade_price × volume × 100 × direction_sign`
        - direction_sign: +1 for bullish-classified, -1 for bearish-classified
      - **Rolling Windows**: maintain rolling signed premium over 5-minute and 15-minute windows
        - Use `collections.deque` with timestamp-based expiry
      - **Z-Score**: compute z-score of current 5-min signed premium vs rolling 60-min baseline
        - `z = (current_5m - mean_60m) / std_60m`
      - **Net Direction**: +1 if signed_premium_5m > 0 (bullish flow), -1 if < 0 (bearish flow)
    - Handle edge cases:
      - No trades yet → FlowResult with direction=0, z_score=0
      - All trades at midpoint → use tick rule, fallback to direction=0 if no history
      - Division by zero on z-score (std=0) → z_score=0

  **Must NOT do**:
  - Do NOT build VPIN (Volume-Synchronized Probability of Informed Trading) — that's separate from signed flow
  - Do NOT weight by option Greeks (delta-adjusted flow) — raw premium flow only in v1
  - Do NOT build real-time WebSocket trade ingestion — this engine processes trades from REST snapshot data

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Financial microstructure algorithm (Lee-Ready) with rolling window statistics, requiring correct sign convention and edge case handling.
  - **Skills**: [`trading-knowledge`]
    - `trading-knowledge`: Aggressor classification and signed flow are core order flow concepts.

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4, 5, 7)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: Tasks 1, 2

  **References**:

  **External References**:
  - Pan, Poteshman (2006) "The Information of Option Volume" RFS 19(3) — foundational paper on using option volume direction to predict stock returns. Our signed flow is a simplified version.
  - Lee, Ready (1991) "Inferring Trade Direction from Intraday Data" — the definitive reference for the Lee-Ready aggressor classification algorithm.
  - Handoff §5 (line 251) — "Aggressor classifier" using `engines.py:Aggressor` pattern. We're building a simpler version focused on premium flow.
  - Handoff §8 anti-pattern #1 (line 337) — "Don't trust raw exchange P/C ratios. Always use signed/aggressor-classified flow (Pan-Poteshman methodology)." This is why we build signed flow, not raw P/C.

  **WHY Each Reference Matters**:
  - The anti-pattern warning is critical: raw P/C ratios are meaningless. SIGNED flow (who is the aggressor?) is the actual signal. This engine implements that distinction.
  - Lee-Ready is the standard algorithm — other approaches exist but this is canonical for options flow.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Aggressor classification — buyer-initiated
    Tool: Bash (python -c)
    Preconditions: nq_atlas/flow.py exists
    Steps:
      1. Create trade: price=5.20, bid=5.10, ask=5.30 (trade above midpoint 5.20 → at midpoint)
      2. Create trade: price=5.25, bid=5.10, ask=5.30 (trade above midpoint → buyer-initiated)
      3. Assert: second trade classified as buyer-initiated
    Expected Result: Trade above midpoint = buyer-initiated
    Failure Indicators: Wrong classification, crash on edge case
    Evidence: .sisyphus/evidence/task-6-flow-aggressor.txt

  Scenario: Signed premium accumulation
    Tool: Bash (pytest)
    Preconditions: Flow engine with rolling windows
    Steps:
      1. Feed 10 trades: 7 buyer-initiated calls ($500 each), 3 seller-initiated puts ($300 each)
      2. Net signed premium = 7×500 - 3×300 = $2,600 (bullish)
      3. Assert: signed_premium_5m > 0, net_direction = +1
    Expected Result: Positive net signed premium, bullish direction
    Failure Indicators: Wrong sign, wrong accumulation math
    Evidence: .sisyphus/evidence/task-6-flow-premium.txt

  Scenario: Z-score computation
    Tool: Bash (pytest)
    Preconditions: Flow engine with 60-min baseline
    Steps:
      1. Seed 60 minutes of baseline data with mean=$1000, std=$500
      2. Current 5-min window = $3000 (4 standard deviations above mean)
      3. Assert: z_score ≈ 4.0
    Expected Result: Z-score reflects deviation from baseline
    Failure Indicators: z_score=0 (no baseline), NaN, division by zero
    Evidence: .sisyphus/evidence/task-6-flow-zscore.txt
  ```

  **Commit**: YES (groups with Tasks 4, 5)
  - Message: `feat(nq-atlas): add GEX, vanna/charm, and flow analytics engines`
  - Files: `nq_atlas/flow.py`
  - Pre-commit: `python -c "from nq_atlas.flow import FlowEngine"`

---

- [x] 7. AI Bias Interpreter (Claude API)

  **What to do**:
  - Create `nq_atlas/ai_bias.py`:
    - `BiasInterpreter` class:
      - `__init__(api_key: str, model: str)` — initialize Anthropic client
      - `async interpret(state: AtlasState) -> BiasOutput` — build structured prompt from current state, call Claude, parse JSON response
      - **Structured Prompt Design** (key-value sections, NOT prose wall):
        ```
        ROLE: You are a quantitative NQ futures bias analyst.

        CURRENT STATE:
        - QQQ Spot: {spot}
        - NQ Price: {nq_price}
        - Net GEX: {net_gex} ({regime_sign_label})
        - GEX Flip: {flip} (QQQ) / {nq_flip} (NQ)
        - Call Wall: {call_wall} / {nq_call_wall}
        - Put Wall: {put_wall} / {nq_put_wall}
        - Net Vanna Exposure: {vanna}
        - Dealer Hedge Direction: {vanna_direction}
        - Signed Premium Flow (5m): {flow_5m} (z={z_score})
        - Flow Direction: {flow_direction}

        TASK: Based on the above dealer positioning data, provide your bias assessment.

        RESPOND IN JSON ONLY:
        {
          "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
          "conviction": 0-100,
          "support_nq": <nearest support level in NQ points>,
          "resistance_nq": <nearest resistance level in NQ points>,
          "narrative": "<2-3 sentence explanation of WHY this bias>",
          "risk_flags": ["<any warnings>"]
        }
        ```
      - **Parse response**: extract JSON from Claude's response (handle markdown code blocks)
      - **Map to BiasOutput**: populate all fields including NQLevels from response
      - **Error handling**:
        - Claude API timeout (>10s) → return last known bias with `degraded=True`
        - Claude returns invalid JSON → log error, return last known bias
        - Claude API 5xx → retry once, then return last known bias
      - `async interpret_loop(state: AtlasState, interval: int)` — async loop calling interpret() every `interval` seconds, updating `state.bias` and `state.last_ai_ts`

  **Must NOT do**:
  - Do NOT write the prompt as a wall of text — structured key-value sections only (handoff anti-pattern #10)
  - Do NOT include chain-level detail (individual contracts) — summary statistics only
  - Do NOT include bias history in prompt (future enhancement, not v1)
  - Do NOT use streaming — single request/response is fine at 15s cadence (Haiku responds in ~1s)
  - Do NOT hardcode model — read from config (default Haiku)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: API integration with prompt engineering, JSON parsing, error handling, and async loop management.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4, 5, 6)
  - **Blocks**: Tasks 8, 10
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `deep6v2/data/rithmic_client.py` — Async client pattern with retry logic and connection state tracking

  **External References**:
  - Anthropic Python SDK: `https://docs.anthropic.com/en/api/client-sdks` — `from anthropic import AsyncAnthropic; client.messages.create()`
  - Handoff §2.1 `ai_bias.py` description (line 71) — "Builds structured prompt with full state, parses JSON response, writes to state.bias." We use 15s cadence for maximum speed.
  - Handoff §8 anti-pattern #10 (line 348) — "Don't write the AI prompt as a wall of text. Structured key-value sections."
  - Handoff §10 decision: "Why Claude API at 60s intervals" (line 420) — original cost rationale. We use 15s for speed priority; Haiku keeps cost ~$20-40/day.

  **WHY Each Reference Matters**:
  - Anti-pattern #10 is a hard rule: structured prompts perform better than prose for market data interpretation
  - User prioritizes speed — 15s AI cadence with Haiku delivers near-real-time bias at manageable cost

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Interpreter produces valid BiasOutput from mocked Claude response
    Tool: Bash (pytest)
    Preconditions: Test with mocked Anthropic client
    Steps:
      1. Mock Claude to return: {"direction": "BULLISH", "conviction": 72, "support_nq": 21100, "resistance_nq": 21350, "narrative": "GEX positive with supportive vanna flow", "risk_flags": []}
      2. Call interpret() with sample state
      3. Assert: BiasOutput.direction == "BULLISH", conviction == 72, levels populated
    Expected Result: Valid BiasOutput with all fields from Claude response
    Failure Indicators: Parse error, missing fields, type mismatch
    Evidence: .sisyphus/evidence/task-7-ai-interpret.txt

  Scenario: Graceful fallback on Claude API failure
    Tool: Bash (pytest)
    Preconditions: Mock Claude to raise timeout
    Steps:
      1. Mock Anthropic client to raise httpx.TimeoutError
      2. Set state.bias to a previous valid bias
      3. Call interpret()
      4. Assert: returns previous bias with degraded=True
    Expected Result: Last known bias returned, degraded flag set
    Failure Indicators: Crash, returns None, returns empty BiasOutput
    Evidence: .sisyphus/evidence/task-7-ai-fallback.txt

  Scenario: Prompt structure is key-value, not prose
    Tool: Bash (pytest)
    Preconditions: Can inspect prompt content
    Steps:
      1. Call interpret() with sample state
      2. Capture the prompt sent to Claude
      3. Assert: prompt contains "CURRENT STATE:" section with key-value pairs
      4. Assert: prompt does NOT contain paragraphs of prose
    Expected Result: Structured prompt with labeled data sections
    Failure Indicators: Prose wall, missing data fields, unstructured
    Evidence: .sisyphus/evidence/task-7-ai-prompt-structure.txt
  ```

  **Commit**: YES
  - Message: `feat(nq-atlas): add Claude AI bias interpreter`
  - Files: `nq_atlas/ai_bias.py`
  - Pre-commit: `python -c "from nq_atlas.ai_bias import BiasInterpreter"`

- [x] 8. FastAPI Server + API Endpoints

  **What to do**:
  - Create `nq_atlas/server.py`:
    - FastAPI app with `APIRouter(prefix="/", tags=["atlas"])`
    - **Endpoints**:
      - `GET /` — redirect to dashboard HTML
      - `GET /health` — `{"status": "ok"|"degraded", "massive_connected": bool, "last_chain_ts": ISO, "last_ai_ts": ISO, "uptime_sec": int}`
      - `GET /state` — full state snapshot via `state.snapshot_dict()` — all raw analytics data
      - `GET /bias` — just the bias output: `{"direction": str, "conviction": int, "levels": {...}, "narrative": str, "updated_at": ISO, "degraded": bool}`
      - `GET /gex` — GEX details: flip, walls, net, regime sign, by-expiry breakdown
      - `GET /dashboard` — serve the `dashboard.html` file as `HTMLResponse`
    - **SSE endpoint** (REQUIRED for fast refresh):
      - `GET /stream` — Server-Sent Events pushing full state on every analytics update (not just bias changes)
      - Use `StreamingResponse` with `text/event-stream` content type
      - Send JSON with bias + gex + vanna_charm + flow on each engine computation cycle
      - Keepalive ping every 10s
    - **CORS**: allow all origins (LAN-trust, no auth)
    - **Static serving**: serve `dashboard.html` from `nq_atlas/` package directory
    - Wire the app to accept `AtlasState` via FastAPI dependency injection or module-level reference

  **Must NOT do**:
  - Do NOT add authentication — LAN-trust per handoff scope boundaries
  - Do NOT add WebSocket endpoint — SSE is sufficient for one-way push
  - Do NOT create multiple router files — single `server.py` is enough for 6 endpoints
  - Do NOT add request logging middleware — structlog in each endpoint is enough

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: FastAPI server with multiple endpoints, SSE streaming, HTML serving — standard web backend work.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 9, 10)
  - **Blocks**: Task 9 (dashboard needs endpoints to exist)
  - **Blocked By**: Tasks 3-7 (needs all engine outputs to serve)

  **References**:

  **Pattern References**:
  - `deep6v2/api/app.py` — FastAPI app creation pattern with routers, CORS middleware, lifespan. Copy this structure.
  - `deep6v2/api/replay.py` — APIRouter pattern with typed response models. Shows how DEEP6 structures endpoints.

  **External References**:
  - FastAPI SSE documentation: `https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse` — StreamingResponse for SSE
  - Handoff §2.1 `server.py` (line 72) — Lists exact endpoints: `/`, `/state`, `/bias`, `/health`. Follow this URL scheme.

  **WHY Each Reference Matters**:
  - `app.py` shows DEEP6's FastAPI conventions — CORS setup, lifespan, router registration. Match these patterns.
  - Handoff endpoint scheme is simple and proven — no need to deviate.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Health endpoint returns valid JSON
    Tool: Bash (curl)
    Preconditions: Server running at localhost:8766
    Steps:
      1. Run: curl -s http://localhost:8766/health
      2. Assert: JSON with "status" field ("ok" or "degraded")
      3. Assert: "massive_connected" field is boolean
    Expected Result: {"status": "ok"|"degraded", "massive_connected": true|false, ...}
    Failure Indicators: 404, 500, non-JSON response
    Evidence: .sisyphus/evidence/task-8-health-endpoint.txt

  Scenario: Bias endpoint returns structured output
    Tool: Bash (curl)
    Preconditions: Server running with at least one bias computation completed
    Steps:
      1. Run: curl -s http://localhost:8766/bias
      2. Assert: JSON with fields: direction (string), conviction (int 0-100), levels (object), narrative (string), updated_at (ISO), degraded (bool)
      3. Assert: direction is one of BULLISH, BEARISH, NEUTRAL
    Expected Result: Complete BiasOutput JSON
    Failure Indicators: Missing fields, wrong types, stale/empty response
    Evidence: .sisyphus/evidence/task-8-bias-endpoint.txt

  Scenario: State endpoint returns full analytics
    Tool: Bash (curl)
    Preconditions: Server running with data populated
    Steps:
      1. Run: curl -s http://localhost:8766/state
      2. Assert: JSON contains "gex", "vanna_charm", "flow", "bias", "spots" sections
    Expected Result: Complete state snapshot with all engine outputs
    Failure Indicators: Empty object, missing sections, 500 error
    Evidence: .sisyphus/evidence/task-8-state-endpoint.txt
  ```

  **Commit**: YES (groups with Task 9)
  - Message: `feat(nq-atlas): add FastAPI server and dashboard UI`
  - Files: `nq_atlas/server.py`
  - Pre-commit: `python -c "from nq_atlas.server import app"`

---

- [x] 9. Dashboard HTML UI

  **What to do**:
  - Create `nq_atlas/dashboard.html` — single-page, self-contained, dark-mode auto-refreshing dashboard
  - **Layout** (top-to-bottom, mobile-friendly):
    - **Header Bar**: "NQ ATLAS" title + connection status indicator (green dot = live, yellow = degraded, red = disconnected) + last update timestamp
    - **Bias Hero Section** (large, central):
      - Direction word: "BULLISH" / "BEARISH" / "NEUTRAL" in large text (green/red/gray)
      - Conviction bar: 0-100 horizontal bar with color gradient
      - Key levels: GEX Flip, Call Wall, Put Wall (all in NQ points)
    - **AI Narrative**: Claude's 2-3 sentence explanation in a card
    - **Analytics Grid** (3 columns on desktop, 1 on mobile):
      - **GEX Card**: Net GEX, regime (Positive/Negative Gamma), flip level, call wall, put wall
      - **Vanna/Charm Card**: Net vanna exposure, net charm, dealer hedge direction arrow
      - **Flow Card**: Signed premium (5m/15m), z-score, flow direction arrow
    - **Risk Flags**: any warnings from Claude shown as yellow/red badges
  - **Auto-refresh**: connect to SSE endpoint `GET /stream` for instant push updates (preferred), with `fetch()` polling every 1 second as fallback
    - SSE: EventSource connected to /stream — receives bias updates immediately when state changes
    - Fallback: if SSE disconnects, fall back to polling `GET /bias` and `GET /state` every 1 second
    - On connection failure: show "CONNECTION LOST" banner, keep retrying every 2s
  - **Styling**: dark background (#0d1117), card borders (#1c2333), green for bullish (#22c55e), red for bearish (#ef4444), gray for neutral
  - **No external dependencies**: pure HTML + CSS + vanilla JS (no React, no npm, no build step)
  - **Market hours awareness**: if `updated_at` is > 30 min old, show "MARKET CLOSED — Last known bias" banner

  **Must NOT do**:
  - Do NOT use React, Vue, or any framework — plain HTML/CSS/JS
  - Do NOT add charts (GEX-by-strike, vol surface, etc.) — text and numbers only for v1
  - Do NOT add trading controls or order buttons — this is read-only
  - Do NOT add login or auth — LAN-trust

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Dashboard UI with responsive layout, color design, status indicators, auto-refresh — front-end visual work.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 10)
  - **Blocks**: Task 10 (orchestrator serves dashboard)
  - **Blocked By**: Task 8 (needs API endpoints to fetch from)

  **References**:

  **External References**:
  - Handoff §2.1 `dashboard.html` (line 73) — "Single-page dark-mode UI. Auto-refreshes every 2s." Our version refreshes every 3s.
  - TradingView dark theme colors — use as inspiration for financial dashboard palette

  **WHY Each Reference Matters**:
  - Handoff dashboard description confirms: single-page, dark-mode, auto-refresh is the proven approach.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dashboard loads and displays bias
    Tool: Playwright
    Preconditions: Server running at localhost:8766 with mock data
    Steps:
      1. Navigate to http://localhost:8766/
      2. Wait for page load (max 5s)
      3. Assert: element with class ".bias-direction" exists and contains "BULLISH", "BEARISH", or "NEUTRAL"
      4. Assert: element with class ".conviction-bar" exists
      5. Assert: element with class ".nq-levels" exists and contains numeric values
    Expected Result: Dashboard renders with bias direction, conviction bar, and NQ levels visible
    Failure Indicators: Blank page, missing elements, JavaScript errors in console
    Evidence: .sisyphus/evidence/task-9-dashboard-load.png

  Scenario: Dashboard auto-refreshes
    Tool: Playwright
    Preconditions: Server running with changing mock data
    Steps:
      1. Navigate to http://localhost:8766/
      2. Read initial conviction value
      3. Wait 5 seconds (covers at least 1 refresh cycle)
      4. Read conviction value again
      5. Assert: timestamp in header has changed (data refreshed)
    Expected Result: Dashboard shows updated data within 5 seconds
    Failure Indicators: Stale data, no refresh, timestamp frozen
    Evidence: .sisyphus/evidence/task-9-dashboard-refresh.png

  Scenario: Degraded state shows warning
    Tool: Playwright
    Preconditions: Server running with degraded=True in state
    Steps:
      1. Navigate to http://localhost:8766/
      2. Assert: yellow or red status indicator visible
      3. Assert: text "DEGRADED" or "STALE" visible on page
    Expected Result: Visual degraded indicator prominent
    Failure Indicators: No warning shown when data is stale
    Evidence: .sisyphus/evidence/task-9-dashboard-degraded.png
  ```

  **Commit**: YES (groups with Task 8)
  - Message: `feat(nq-atlas): add FastAPI server and dashboard UI`
  - Files: `nq_atlas/dashboard.html`
  - Pre-commit: N/A (HTML file)

---

- [x] 10. Asyncio Orchestrator + Entry Point

  **What to do**:
  - Complete `run_atlas.py` — the single entry point that wires everything together:
    - Load config from env via `Settings()`
    - Initialize `AtlasState`
    - Initialize `MassiveClient(api_key=config.massive_api_key)`
    - Initialize `GEXEngine()`, `VannaCharmEngine()`, `FlowEngine()`
    - Initialize `BiasInterpreter(api_key=config.anthropic_api_key, model=config.anthropic_model)`
    - Create FastAPI app and mount state
    - `async main()`:
      - **Task group** (all run concurrently via `asyncio.gather`):
        1. `massive_client.poll_loop(state, config.refresh_interval_sec)` — fetches chain every N seconds
        2. `compute_loop(state, engines, config)` — after each chain update, runs GEX → vanna/charm → flow → NQ mapper, updates state
        3. `bias_interpreter.interpret_loop(state, config.ai_refresh_sec)` — calls Claude every N seconds
        4. `uvicorn.Server(config).serve()` — serves FastAPI on configured host:port
      - **Graceful shutdown**: catch SIGINT/SIGTERM, cancel all tasks, log final state
      - **Error isolation**: if one task crashes, log error and restart it, don't kill the whole system
    - Create `nq_atlas/orchestrator.py` if the logic is complex enough to separate from `run_atlas.py`
    - `compute_loop` detail:
      - Wait for `state.chain` to be populated (poll_loop produces first chain)
      - Run: `state.gex = gex_engine.compute(state.chain)`
      - Run: `state.vanna_charm = vanna_engine.compute(state.chain)`
      - Run: `state.flow = flow_engine.compute()` (flow uses trade data from chain)
      - Run: `state.nq_levels = nq_mapper.map_chain_levels(state.gex, qqq_spot, nq_spot)`
      - Log: summary line with GEX regime, vanna direction, flow direction
    - Add `--dry-run` flag: validates config, tests Massive API connection, prints "Ready", exits

  **Must NOT do**:
  - Do NOT use multiprocessing — single-process asyncio is sufficient
  - Do NOT add a CLI framework (click, argparse beyond --dry-run) — keep it minimal
  - Do NOT add Redis or message bus — direct function calls within asyncio
  - Do NOT add restart logic for individual engines — if an engine fails, log and continue with stale data

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Asyncio orchestration with concurrent task groups, error isolation, graceful shutdown — requires careful async programming.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (depends on all prior tasks)
  - **Blocks**: Task 11 (tests need working orchestrator)
  - **Blocked By**: Tasks 3-9 (needs all components to wire together)

  **References**:

  **Pattern References**:
  - `deep6v2/api/app.py` — FastAPI lifespan pattern with async context manager. Shows how DEEP6 starts/stops background tasks alongside the web server.
  - `scripts/` directory — Various entry point scripts showing how DEEP6 launches services.

  **External References**:
  - Handoff §2.1 `run.py` (line 65) — "Asyncio orchestrator. Single entry point. Wires ingest → engines → ai_bias → server." Our run_atlas.py follows this exact pattern.
  - Handoff §10 "Why a single shared State object" (line 424) — "Single-host, single-process deployment. asyncio guarantees no preemption. Lock-free reads with single-writer-per-field convention."

  **WHY Each Reference Matters**:
  - The handoff's architectural decision (shared State, no message bus) is the RIGHT call for a single-process system. We adopt this.
  - `app.py` lifespan shows how to start uvicorn alongside background tasks — critical pattern.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dry-run validates config and API access
    Tool: Bash
    Preconditions: .env configured with API keys
    Steps:
      1. Run: python run_atlas.py --dry-run
      2. Assert: output contains "Config loaded" and "Massive API: connected" (or clear error if key invalid)
      3. Assert: exit code 0 on success
    Expected Result: Config validation passes, API access confirmed
    Failure Indicators: Crash before validation, unclear error messages
    Evidence: .sisyphus/evidence/task-10-dry-run.txt

  Scenario: Full startup and first bias cycle
    Tool: Bash
    Preconditions: .env configured, Massive API accessible
    Steps:
      1. Run: python run_atlas.py (in background)
      2. Wait 90 seconds (covers 1 polling cycle + 1 AI cycle)
      3. Run: curl -s http://localhost:8766/bias
      4. Assert: JSON response with direction != null, updated_at within last 120s
      5. Kill the process
    Expected Result: Full pipeline produces bias output within 2 minutes of startup
    Failure Indicators: No bias after 2 minutes, crash during startup, stale updated_at
    Evidence: .sisyphus/evidence/task-10-full-startup.txt

  Scenario: Graceful shutdown on Ctrl+C
    Tool: Bash
    Preconditions: Server running
    Steps:
      1. Start run_atlas.py
      2. Send SIGINT (Ctrl+C)
      3. Assert: process exits within 5 seconds
      4. Assert: log contains "Shutting down gracefully"
    Expected Result: Clean shutdown, no orphan tasks, no error stack traces
    Failure Indicators: Hangs, asyncio CancelledError traceback, orphan uvicorn process
    Evidence: .sisyphus/evidence/task-10-shutdown.txt
  ```

  **Commit**: YES
  - Message: `feat(nq-atlas): add orchestrator and entry point`
  - Files: `run_atlas.py`, `nq_atlas/orchestrator.py` (if created)
  - Pre-commit: `python run_atlas.py --dry-run`

---

- [x] 11. Test Suite

  **What to do**:
  - Create `tests_nq_atlas/` test directory with comprehensive coverage:
  - `tests_nq_atlas/conftest.py`:
    - Shared fixtures: `sample_chain()` (mock QQQ options chain with 20 contracts), `sample_state()` (populated AtlasState), `mock_massive_client()`, `mock_anthropic_client()`
    - Use `pytest-asyncio` for async test support (already configured in pyproject.toml)
  - `tests_nq_atlas/test_massive_client.py`:
    - Test chain parsing with valid/invalid/partial API responses
    - Test OI filter, Greeks filter, T clamping
    - Test error handling (401, 429, 5xx, timeout)
    - Test NQ quote fetch with mock response
    - Use `httpx` mocking or `unittest.mock.patch` on the SDK
  - `tests_nq_atlas/test_gex.py`:
    - Test known test vector (QQQ=500, strike=500, gamma=0.005, OI=10000)
    - Test flip level interpolation
    - Test call wall / put wall identification
    - Test regime sign (+1 for positive net GEX, -1 for negative)
    - Test degraded result on thin chain (<10 contracts)
    - Test with missing gamma contracts
  - `tests_nq_atlas/test_vanna_charm.py`:
    - Test vanna computation against known BS values
    - Test charm computation
    - Test dealer hedge direction determination
    - Test fallback computation when API vanna missing
  - `tests_nq_atlas/test_flow.py`:
    - Test Lee-Ready aggressor classification (above/below/at midpoint)
    - Test signed premium accumulation
    - Test rolling window expiry
    - Test z-score computation
    - Test edge case: no trades, all at midpoint
  - `tests_nq_atlas/test_ai_bias.py`:
    - Test prompt structure (key-value, not prose)
    - Test JSON parsing from Claude response
    - Test fallback on API failure (timeout, 5xx)
    - Test degraded flag on stale bias
    - Mock Anthropic client entirely
  - `tests_nq_atlas/test_server.py`:
    - Test all endpoints return expected status codes and shapes
    - Use `httpx.AsyncClient` with `ASGITransport(app=app)` pattern from DEEP6
    - Test /health, /bias, /state, /gex responses
  - `tests_nq_atlas/test_nq_mapper.py`:
    - Test level conversion math
    - Test batch conversion
    - Test edge case: qqq_spot=0 (should handle gracefully)

  **Must NOT do**:
  - Do NOT test against live Massive.com API — all external calls mocked
  - Do NOT test against live Claude API — all Anthropic calls mocked
  - Do NOT add integration tests that require running services — unit tests only
  - Do NOT over-test (100% coverage is not a goal — test the MATH and the ERROR PATHS)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Writing comprehensive test suite across 7 modules, each with specific test vectors and edge cases.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Wave 4 — final implementation task)
  - **Blocks**: F1-F4 verification
  - **Blocked By**: Task 10 (needs all modules working to test)

  **References**:

  **Pattern References**:
  - `tests_v2/conftest.py` — Shared fixtures pattern (FootprintBar, SessionContext). Copy this structure for NQ ATLAS fixtures.
  - `tests_v2/api/test_replay.py` — Async API test pattern using `httpx.AsyncClient` with `ASGITransport`. Use this exact pattern for server tests.
  - `tests_v2/data/test_rithmic_client.py` — External SDK mocking pattern (FakeAsyncRithmicClient). Shows how to mock external data clients for unit testing.
  - `tests_v2/signals/test_absorption.py` — Signal engine test pattern with known test vectors.

  **WHY Each Reference Matters**:
  - `test_rithmic_client.py` shows the EXACT pattern for mocking external SDKs — we need the same for Massive client
  - `test_replay.py` shows how to test FastAPI endpoints without running a server — async client with ASGI transport

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass
    Tool: Bash (pytest)
    Preconditions: All nq_atlas/ modules exist, tests_nq_atlas/ populated
    Steps:
      1. Run: pytest tests_nq_atlas/ -v --tb=short
      2. Assert: all tests pass (0 failures)
      3. Assert: at least 20 tests total across all test files
    Expected Result: Full green test run, ≥20 tests
    Failure Indicators: Any test failure, fewer than 20 tests
    Evidence: .sisyphus/evidence/task-11-test-results.txt

  Scenario: Tests run without external dependencies
    Tool: Bash (pytest)
    Preconditions: No MASSIVE_API_KEY or ANTHROPIC_API_KEY set
    Steps:
      1. Unset all NQ_ATLAS_* environment variables
      2. Run: pytest tests_nq_atlas/ -v
      3. Assert: all tests pass (mocked, no real API calls)
    Expected Result: Tests pass without any API keys configured
    Failure Indicators: Tests fail due to missing API keys, real HTTP calls attempted
    Evidence: .sisyphus/evidence/task-11-tests-no-env.txt
  ```

  **Commit**: YES
  - Message: `test(nq-atlas): add test suite for all modules`
  - Files: `tests_nq_atlas/*.py`
  - Pre-commit: `pytest tests_nq_atlas/ -v`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `pytest tests_nq_atlas/ -v`. Review all nq_atlas/ files for: `as any`/type:ignore, empty catches, console.log/print in prod code, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp), unnecessary base classes.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real QA Execution** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (full pipeline: ingest → compute → interpret → serve). Test edge cases: stale data, API failure, 0DTE expiry. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT Have" compliance (no SVI, no SPX, no WebSocket streaming, no DEEP6 integration, no backtesting, no trade execution). Flag unaccounted files.
  Output: `Tasks [N/N compliant] | Scope Violations [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| After Task(s) | Commit Message | Pre-commit Check |
|---------------|---------------|-----------------|
| 1-2 | `feat(nq-atlas): scaffold package with types, config, and state` | `python -c "from nq_atlas.types import BiasOutput"` |
| 3 | `feat(nq-atlas): add Massive.com data client with chain ingestion` | `python -c "from nq_atlas.massive_client import MassiveClient"` |
| 4-6 | `feat(nq-atlas): add GEX, vanna/charm, and flow analytics engines` | `python -c "from nq_atlas.gex import GEXEngine"` |
| 7 | `feat(nq-atlas): add Claude AI bias interpreter` | `python -c "from nq_atlas.ai_bias import BiasInterpreter"` |
| 8-9 | `feat(nq-atlas): add FastAPI server and dashboard UI` | `curl -s http://localhost:8766/health` |
| 10 | `feat(nq-atlas): add orchestrator and entry point` | `python run_atlas.py --dry-run` |
| 11 | `test(nq-atlas): add test suite for all modules` | `pytest tests_nq_atlas/ -v` |

---

## Success Criteria

### Verification Commands
```bash
python run_atlas.py                    # Expected: server starts, begins polling
curl http://localhost:8766/health      # Expected: {"status": "ok"}
curl http://localhost:8766/bias        # Expected: JSON with direction, conviction, levels
curl http://localhost:8766/state       # Expected: full state snapshot
pytest tests_nq_atlas/ -v             # Expected: all tests pass
```

### Final Checklist
- [ ] `nq_atlas/` package exists with all 13 files
- [ ] `run_atlas.py` starts the server successfully
- [ ] Dashboard loads at http://localhost:8766 and auto-refreshes
- [ ] Bias output includes direction (BULLISH/BEARISH/NEUTRAL), conviction (0-100), NQ levels
- [ ] Raw GEX/vanna/flow data visible on dashboard alongside AI narrative
- [ ] Stale data shows degraded indicator
- [ ] No SVI, no SPX, no WebSocket streaming, no DEEP6 integration, no backtesting
- [ ] All tests pass
