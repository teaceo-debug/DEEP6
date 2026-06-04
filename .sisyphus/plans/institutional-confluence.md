# Institutional Confluence System — Deploy + Adapt Plan

## TL;DR

> **Quick Summary**: Deploy 6 provided source files (~3,200 LOC) into DEEP6, replacing quantsynth API calls with local computation from existing nq_atlas data. Includes Phase 5 Equilibrium Model (SFV + strike-level GEX + 4-regime classifier). Two NT8 indicators side-by-side: Confluence HUD (top-right) + Equilibrium HUD (top-left).
> 
> **Deliverables**:
> - `confluence_system/confluence_server.py` — Adapted FastAPI middleware (quantsynth → nq_atlas)
> - `confluence_system/equilibrium_module.py` — SFV + NDX GEX + regime classifier (adapted)
> - `ninjatrader/Custom/Indicators/PeakAssetPerformance/InstitutionalConfluence.cs` — NT8 indicator
> - `ninjatrader/Custom/Indicators/PeakAssetPerformance/EquilibriumModel.cs` — NT8 sibling indicator
> - `ninjatrader/Custom/Strategies/PeakAssetPerformance/ConfluenceBiasFilter.cs` — Engine #15 bridge
> - Python tests for adapted modules
> 
> **Estimated Effort**: Medium (4-6 days)
> **Parallel Execution**: YES — 4 waves
> **Critical Path**: Task 1 → Task 2 → Task 5 → Task 7 → Task 10 → F1-F4

---

## Context

### Original Request
User wants to deploy the Institutional Confluence System from provided source files (files.zip). The code is complete (~3,200 LOC across 6 files) but references quantsynth API which user doesn't have. User wants quantsynth replaced with local computation from existing nq_atlas infrastructure (FlashAlpha + Massive clients). Additionally includes Phase 5 Equilibrium Model not in original handoff.

### Interview Summary
**Key Discussions**:
- **Chart timeframe**: 4H candles — Calculate.OnBarClose is appropriate
- **No quantsynth**: Replace with local regime/DP computation from nq_atlas data
- **Reuse nq_atlas clients**: FlashAlpha + Massive clients already running in nq_atlas/
- **Phases 1-5**: Including Equilibrium Model (Phase 5 addition from files.zip)
- **Tests after implementation**: pytest + pytest-asyncio infrastructure exists
- **Provided code is the implementation**: Deploy + adapt, not build from scratch

**Provided Files**:
| File | Lines | Purpose |
|------|-------|---------|
| `confluence_server.py` | 824 | FastAPI middleware — 3-layer scoring + equilibrium endpoint |
| `equilibrium_module.py` | 686 | SFV computation, NDX chain GEX, volatility bands, 4-regime classifier |
| `InstitutionalConfluence.cs` | 690 | NT8 indicator — HUD (top-right) + GEX lines + MTF zones + alerts |
| `EquilibriumModel.cs` | 761 | NT8 sibling indicator — HUD (top-left) + SFV line + zone bands |
| `ConfluenceBiasFilter.cs` | 308 | Engine #15 bridge with AttachEquilibrium() support |
| `README.md` | 230+ | Deployment guide + alert taxonomy |

**Research Findings**:
- `nq_atlas/flashalpha_client.py` — FlashAlpha async client with poll_loop (REUSABLE for GEX data)
- `nq_atlas/massive_client.py` — Massive/Polygon async client with retry/backoff (REUSABLE for options chain + quotes)
- `nq_atlas/server.py` — FastAPI SSE server on port 8766, already running both clients
- `nq_atlas/state.py:AtlasState` — Shared state with FlashAlpha + Massive data already populated
- Port 8765 used by deep6/api, port 8766 used by nq_atlas — need port 8767 for confluence
- DEEP6Atlas.cs E15 is occupied (HMM-5 Regime Router) — ConfluenceBiasFilter bridge works standalone, wiring into E15 is optional/deferred

### Metis Review
**Identified Gaps (all addressed)**:
- **E15 is occupied**: ConfluenceBiasFilter.cs works standalone — `ContributeToEngine15()` is callable but not auto-wired. Wiring into DEEP6Atlas is DEFERRED (separate task when ready).
- **Port conflict**: Using port 8767 for confluence server (8765=deep6, 8766=nq_atlas)
- **quantsynth dependency**: 4 fetch functions (`fetch_quantsynth_dp`, `fetch_quantsynth_regime`, `fetch_quantsynth_setup`, `fetch_quantsynth_pcr`) replaced with local computation from nq_atlas AtlasState
- **Massive TRF endpoint**: Code assumes `GET /trf/{ticker}/summary` — may need adaptation to match actual Polygon endpoint

---

## Work Objectives

### Core Objective
Deploy the provided Institutional Confluence System files into DEEP6, adapting the Python middleware to replace quantsynth with local nq_atlas computation while keeping all NT8 indicator code intact.

### Concrete Deliverables
- `confluence_system/confluence_server.py` — Adapted middleware on port 8767
- `confluence_system/equilibrium_module.py` — Adapted equilibrium module
- `ninjatrader/Custom/Indicators/PeakAssetPerformance/InstitutionalConfluence.cs`
- `ninjatrader/Custom/Indicators/PeakAssetPerformance/EquilibriumModel.cs`
- `ninjatrader/Custom/Strategies/PeakAssetPerformance/ConfluenceBiasFilter.cs`
- `confluence_system/README.md` — Updated deployment guide
- `tests/confluence_system/test_scoring.py` — Scoring + normalization tests
- `tests/confluence_system/test_equilibrium.py` — SFV + regime tests

### Definition of Done
- [ ] `python confluence_system/confluence_server.py` starts on port 8767 without quantsynth keys
- [ ] `curl http://127.0.0.1:8767/health` → 200
- [ ] `curl http://127.0.0.1:8767/confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM` → valid JSON
- [ ] `curl http://127.0.0.1:8767/equilibrium/nq?price=21000` → valid JSON with SFV + bands
- [ ] NT8 F5 compile → 0 errors for all 3 .cs files
- [ ] InstitutionalConfluence indicator loads on 4H NQ chart, HUD renders top-right
- [ ] EquilibriumModel indicator loads alongside, HUD renders top-left
- [ ] GEX lines + MTF zones visible on chart
- [ ] `pytest tests/confluence_system/ -v` → all pass

### Must Have
- All 6 source files deployed and functional
- quantsynth calls replaced with nq_atlas-derived computation (no quantsynth API key required)
- Scoring weights: DP 0.40, GEX 0.25, Regime 0.20, MTF 0.15 (assert sum=1.0)
- SFV weights: Weekly 0.50, Daily 0.35, HVL 0.15 (assert sum=1.0)
- Conflict alert taxonomy functional: STOP_BUYING, STOP_SELLING, FULL_SEND_LONG/SHORT, REGIME_DIVERGENCE, STAND_DOWN
- Equilibrium 4-regime classifier: Gamma Regime + Volatility Regime + Trend Alignment + Institutional Bias
- Both NT8 HUDs coexisting on same chart (top-right Confluence, top-left Equilibrium)
- Graceful degradation when API data unavailable
- Calculate.OnBarClose for 4H timeframe

### Must NOT Have (Guardrails)
- **DO NOT modify DEEP6Atlas.cs or EngineOutputs** — E15 wiring is DEFERRED
- **DO NOT require quantsynth API key** — system must run without it
- **DO NOT create new FlashAlpha/Massive client instances** — import from nq_atlas or read from AtlasState
- **DO NOT change scoring weights** without explicit user instruction
- **DO NOT add SSE/WebSocket streaming** — HTTP polling only
- **DO NOT build Phases 6-9** (backtest, ML calibration, webhooks, auto-tune)
- **DO NOT restructure the provided code unnecessarily** — adapt minimally, keep author's architecture

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: YES (pytest + pytest-asyncio in pyproject.toml)
- **Automated tests**: Tests-after
- **Framework**: pytest

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — copy + adapt Python):
├── Task 1: Copy files + create directory structure [quick]
├── Task 2: Adapt confluence_server.py — replace quantsynth with nq_atlas [deep]
├── Task 3: Adapt equilibrium_module.py — wire Massive chain fetcher [deep]
└── Task 4: Update .env + config for port 8767 + new env vars [quick]

Wave 2 (After Wave 1 — verify Python + deploy NT8):
├── Task 5: Smoke test Python middleware (start server, curl endpoints) [quick]
├── Task 6: Deploy NT8 files + compile [unspecified-high]
└── Task 7: Python tests for scoring + equilibrium modules [quick]

Wave 3 (After Wave 2 — end-to-end verification):
├── Task 8: End-to-end: NT8 indicator polling middleware, HUD renders [unspecified-high]
├── Task 9: Equilibrium Model: SFV line + zone bands + HUD renders [visual-engineering]
└── Task 10: Alert system: conflict alerts fire + NT8 Alert() dispatch [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3, 4, 6 | 1 |
| 2 | 1 | 5, 7 | 1 |
| 3 | 1 | 5, 7 | 1 |
| 4 | 1 | 5 | 1 |
| 5 | 2, 3, 4 | 8, 9, 10 | 2 |
| 6 | 1 | 8, 9, 10 | 2 |
| 7 | 2, 3 | — | 2 |
| 8 | 5, 6 | — | 3 |
| 9 | 5, 6 | — | 3 |
| 10 | 5, 6 | — | 3 |
| F1-F4 | ALL | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **4 tasks** — T1 → `quick`, T2 → `deep`, T3 → `deep`, T4 → `quick`
- **Wave 2**: **3 tasks** — T5 → `quick`, T6 → `unspecified-high`, T7 → `quick`
- **Wave 3**: **3 tasks** — T8 → `unspecified-high`, T9 → `visual-engineering`, T10 → `unspecified-high`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Copy Files + Create Directory Structure

  **What to do**:
  - Create `confluence_system/` directory in project root
  - Copy from `C:\Users\Tea\Downloads\files.zip` (already extracted to `C:\Users\Tea\AppData\Local\Temp\opencode\confluence-files\`):
    - `confluence_server.py` → `confluence_system/confluence_server.py`
    - `equilibrium_module.py` → `confluence_system/equilibrium_module.py`
    - `README.md` → `confluence_system/README.md`
    - `HANDOFF.md` → `confluence_system/HANDOFF.md`
  - Copy NT8 files:
    - `InstitutionalConfluence.cs` → `ninjatrader/Custom/Indicators/PeakAssetPerformance/InstitutionalConfluence.cs`
    - `EquilibriumModel.cs` → `ninjatrader/Custom/Indicators/PeakAssetPerformance/EquilibriumModel.cs`
    - `ConfluenceBiasFilter.cs` → `ninjatrader/Custom/Strategies/PeakAssetPerformance/ConfluenceBiasFilter.cs`
  - Create `confluence_system/__init__.py` (empty)
  - Create `tests/confluence_system/__init__.py` (empty)
  - Verify all files copied with correct sizes

  **Must NOT do**:
  - Do NOT modify file contents in this task — just copy
  - Do NOT put Python files in nq_atlas/ — keep confluence_system/ separate

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 2, 3, 4, 6
  - **Blocked By**: None

  **References**:
  - Source: `C:\Users\Tea\AppData\Local\Temp\opencode\confluence-files\` (extracted zip)
  - NT8 indicator directory: `ninjatrader/Custom/Indicators/PeakAssetPerformance/`
  - NT8 strategy directory: `ninjatrader/Custom/Strategies/PeakAssetPerformance/`

  **Acceptance Criteria**:
  - [ ] `Test-Path confluence_system/confluence_server.py` → True
  - [ ] `Test-Path confluence_system/equilibrium_module.py` → True
  - [ ] All 3 .cs files in correct NT8 directories
  - [ ] `python -c "import ast; ast.parse(open('confluence_system/confluence_server.py').read())"` → passes (valid Python)

  **QA Scenarios**:
  ```
  Scenario: All files deployed to correct locations
    Tool: Bash
    Steps:
      1. Run: Test-Path for each of the 7 target files
      2. Assert: all return True
      3. Compare file sizes against originals
    Expected Result: All files present with correct sizes
    Evidence: .sisyphus/evidence/task-1-files-deployed.txt
  ```

  **Commit**: YES (commit 1)
  - Message: `feat(confluence): scaffold directory + deploy source files`

- [x] 2. Adapt confluence_server.py — Replace quantsynth with nq_atlas

  **What to do**:
  - Remove/replace these quantsynth-dependent functions in `confluence_server.py`:
    - `fetch_quantsynth_dp()` → Replace with `compute_dp_from_options(state)` — derive institutional flow signal from nq_atlas AtlasState options chain data (PCR, OI skew, same logic as old plan Task 4)
    - `fetch_quantsynth_regime()` → Replace with `compute_regime_local(state)` — derive from GEX flip position + PCR + VIX (same as old plan Task 3 regime formulas)
    - `fetch_quantsynth_setup()` → Replace with a static neutral response — composite "opus verdict" layer becomes optional (returns `CompositeLayer(stale=True)`)
    - `fetch_quantsynth_pcr()` → Replace with PCR computed from Massive options chain data
  - Update import: `from equilibrium_module import ...` → `from confluence_system.equilibrium_module import ...` (or relative import)
  - Change port from 8765 to 8767: update the `uvicorn.run()` call at bottom
  - Add import of nq_atlas AtlasState: `from nq_atlas.state import atlas_state` (or read via HTTP from nq_atlas server at :8766)
  - Update the `background_refresher()` to use nq_atlas data instead of direct API calls for DP + regime layers
  - Keep FlashAlpha GEX fetch as-is (it's a direct API call, not quantsynth)
  - Keep Massive TRF fetch as-is (direct Polygon call)
  - Remove `QUANTSYNTH_API_KEY` and `QUANTSYNTH_BASE` config vars
  - Ensure the `assert abs(W_DP + W_GEX + W_REGIME + W_MTF - 1.0) < 1e-6` stays intact
  - Ensure all `normalize_*` functions remain unchanged
  - Ensure `detect_alert()` remains unchanged

  **Must NOT do**:
  - Do NOT rewrite the entire file — targeted replacements only
  - Do NOT change scoring weights
  - Do NOT remove the CompositeLayer from the payload — just make it return stale/neutral
  - Do NOT change the UnifiedPayload schema (NT8 C# DTOs must still match)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding both the provided code architecture and nq_atlas data structures
  - **Skills**: [`nq-options-algo-engine/data-sources/massive-api`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: Task 1

  **References**:
  **Pattern References**:
  - `nq_atlas/state.py:AtlasState` — Where FlashAlpha + Massive data lives
  - `nq_atlas/flow.py` — Existing options flow analysis (PCR computation reference)
  - `nq_atlas/gex.py` — GEX regime detection patterns
  - `nq_atlas/massive_client.py:get_options_chain()` — Chain data structure

  **API/Type References**:
  - `nq_atlas/types.py:ChainSnapshot` — Options chain with contracts list for PCR computation
  - `confluence_system/confluence_server.py:DarkPoolLayer` — Target output shape (lines 112-121)
  - `confluence_system/confluence_server.py:RegimeLayer` — Target output shape (lines 123-129)

  **Acceptance Criteria**:
  - [ ] `python -c "from confluence_system.confluence_server import app"` → no ImportError
  - [ ] No reference to `quantsynth` in adapted file (grep returns 0 hits for `fetch_quantsynth`)
  - [ ] `QUANTSYNTH_API_KEY` no longer required
  - [ ] Weight assertion still passes
  - [ ] UnifiedPayload schema unchanged (C# DTOs still match)

  **QA Scenarios**:
  ```
  Scenario: Server starts without quantsynth
    Tool: Bash
    Steps:
      1. Unset QUANTSYNTH_API_KEY env var
      2. Run: python -c "from confluence_system.confluence_server import app; print('OK')"
      3. Assert: exit code 0, no ImportError, no quantsynth reference
    Expected Result: App imports cleanly without quantsynth dependency
    Evidence: .sisyphus/evidence/task-2-no-quantsynth.txt

  Scenario: DP layer produces signal from options data
    Tool: Bash
    Preconditions: nq_atlas running with Massive data
    Steps:
      1. Call compute_dp_from_options() with AtlasState
      2. Assert: DarkPoolLayer with bias in (BULLISH, BEARISH, NEUTRAL), confidence > 0
    Expected Result: Institutional flow signal derived from options, not quantsynth
    Evidence: .sisyphus/evidence/task-2-dp-from-options.txt
  ```

  **Commit**: YES (commit 2)
  - Message: `feat(confluence): replace quantsynth with nq_atlas local computation`

- [x] 3. Adapt equilibrium_module.py — Wire Massive Chain Fetcher

  **What to do**:
  - The `equilibrium_module.py` has its own `fetch_chain()` function (line 212) that calls Massive/Polygon directly for NDX options chain. This is FINE as-is — it uses the same MASSIVE_API_KEY from .env
  - Update import path: ensure it works as `from confluence_system.equilibrium_module import ...`
  - Verify `fetch_chain()` endpoint shape matches actual Polygon API:
    - Current: `GET {MASSIVE_BASE}/options/{ticker}/snapshot`
    - Actual Polygon: `GET https://api.polygon.io/v3/snapshot/options/{ticker}?apiKey={key}`
    - If different, adapt the URL and response parsing
  - Verify NDX quote endpoint for NDX spot price works with Polygon
  - Test Black-Scholes gamma computation with known values
  - Ensure SFV weight assertion passes: `abs(W_WEEKLY_ZG + W_DAILY_ZG + W_HVL - 1.0) < 1e-6`
  - Add fallback: if NDX chain unavailable, try QQQ chain with `NDX_TO_NQ_RATIO_EST` scaling

  **Must NOT do**:
  - Do NOT rewrite the Black-Scholes math — it's correct
  - Do NOT change SFV weights without user instruction
  - Do NOT remove QQQ daily pressure logic (0DTE proxy)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Options chain API validation, Black-Scholes verification, NDX/NQ ratio handling
  - **Skills**: [`nq-options-algo-engine/data-sources/massive-api`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: Task 1

  **References**:
  **Pattern References**:
  - `nq_atlas/massive_client.py:get_options_chain()` — Reference for actual Polygon options endpoint
  - `confluence_system/equilibrium_module.py:fetch_chain()` (line 212) — Function to adapt

  **External References**:
  - Polygon options snapshot: `https://polygon.io/docs/options/get_v3_snapshot_options__underlyingasset`

  **Acceptance Criteria**:
  - [ ] `python -c "from confluence_system.equilibrium_module import compute_equilibrium"` → no error
  - [ ] SFV weight assertion passes
  - [ ] `bs_gamma(100, 100, 0.1, 0.045, 0.2)` returns a positive float (sanity check)
  - [ ] fetch_chain endpoint URL matches actual Polygon API

  **QA Scenarios**:
  ```
  Scenario: Black-Scholes gamma produces sane values
    Tool: Bash
    Steps:
      1. Run: python -c "from confluence_system.equilibrium_module import bs_gamma; g = bs_gamma(21000, 21000, 0.02, 0.045, 0.2); print(f'gamma={g:.8f}'); assert g > 0"
      2. Assert: positive gamma value for ATM option
    Expected Result: Valid gamma computation
    Evidence: .sisyphus/evidence/task-3-bs-gamma.txt
  ```

  **Commit**: YES (commit 2 — groups with Task 2)

- [x] 4. Update .env + Config for Port 8767 + New Env Vars

  **What to do**:
  - Add to `.env.example`:
    ```
    # Confluence System
    CONFLUENCE_PORT=8767
    CONFLUENCE_W_DP=0.40
    CONFLUENCE_W_GEX=0.25
    CONFLUENCE_W_REGIME=0.20
    CONFLUENCE_W_MTF=0.15
    REFRESH_GEX_SEC=300
    REFRESH_MASSIVE_SEC=15
    REFRESH_REGIME_SEC=900
    
    # Equilibrium Model
    EQM_W_WEEKLY=0.50
    EQM_W_DAILY=0.35
    EQM_W_HVL=0.15
    EQM_SIGMA_ZONE=1.5
    EQM_SIGMA_EXTREME=2.5
    EQM_NDX_NQ_RATIO=1.06
    EQM_USE_QQQ_DAILY=true
    REFRESH_EQUILIBRIUM_SEC=60
    ```
  - Add to `.env` (actual): port and any missing vars
  - Update `confluence_server.py` port reference to use `CONFLUENCE_PORT` env var

  **Must NOT do**:
  - Do NOT add quantsynth env vars
  - Do NOT change existing .env vars for other systems

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 2, 3)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 5
  - **Blocked By**: Task 1

  **References**:
  - `.env.example` — Existing env template to append to
  - `.env` — Live env vars

  **Acceptance Criteria**:
  - [ ] `.env.example` contains all confluence + equilibrium env vars
  - [ ] `CONFLUENCE_PORT=8767` in .env

  **QA Scenarios**:
  ```
  Scenario: Env vars present
    Tool: Bash (grep)
    Steps:
      1. Grep .env.example for CONFLUENCE_PORT, EQM_W_WEEKLY
      2. Assert: both found
    Expected Result: New env vars documented
    Evidence: .sisyphus/evidence/task-4-env.txt
  ```

  **Commit**: YES (commit 1)

- [x] 5. Smoke Test Python Middleware

  **What to do**:
  - Start the confluence server: `python -m confluence_system.confluence_server` (or direct run)
  - Verify health endpoint: `curl http://127.0.0.1:8767/health`
  - Verify status endpoint: `curl http://127.0.0.1:8767/status` — shows cache ages
  - Verify confluence endpoint: `curl 'http://127.0.0.1:8767/confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM'`
  - Verify equilibrium endpoint: `curl 'http://127.0.0.1:8767/equilibrium/nq?price=21000'`
  - Verify raw endpoint: `curl 'http://127.0.0.1:8767/confluence/nq/raw'`
  - Check: no quantsynth errors in logs
  - Check: FlashAlpha + Massive layers populate (or gracefully degrade if API keys missing)
  - Check: regime layer computes locally (not from quantsynth)

  **Must NOT do**:
  - Do NOT fix issues in this task — report them. Fixes go back to Tasks 2/3.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 8, 9, 10
  - **Blocked By**: Tasks 2, 3, 4

  **Acceptance Criteria**:
  - [ ] Server starts on port 8767
  - [ ] `/health` → 200
  - [ ] `/confluence/nq` → 200 with valid JSON containing score, layers, alert
  - [ ] `/equilibrium/nq` → 200 with valid JSON containing sfv, bands, regime
  - [ ] No quantsynth-related errors in server logs

  **QA Scenarios**:
  ```
  Scenario: All endpoints respond correctly
    Tool: Bash (curl)
    Steps:
      1. Start server in background
      2. Wait 5s for startup
      3. curl /health → assert 200
      4. curl /confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM → assert 200, JSON has "confluence_score"
      5. curl /equilibrium/nq?price=21000 → assert 200, JSON has "sfv"
      6. Kill server
    Expected Result: All endpoints functional
    Evidence: .sisyphus/evidence/task-5-smoke-test.txt

  Scenario: Graceful degradation without API keys
    Tool: Bash
    Steps:
      1. Unset MASSIVE_API_KEY and FLASHALPHA_API_KEY
      2. Start server
      3. curl /confluence/nq?price=21000 → assert 200, all layers show stale=true
    Expected Result: Server runs, returns stale data, no crash
    Evidence: .sisyphus/evidence/task-5-degradation.txt
  ```

  **Commit**: YES (commit 3)

- [x] 6. Deploy NT8 Files + Compile

  **What to do**:
  - Copy .cs files to NT8 live directories (not just the repo — actual NT8 install):
    - `InstitutionalConfluence.cs` → `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\PeakAssetPerformance\`
    - `EquilibriumModel.cs` → same directory
    - `ConfluenceBiasFilter.cs` → `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\PeakAssetPerformance\`
  - Verify `PeakAssetPerformance` subdirectory exists (create if needed)
  - Trigger F5 compile in NT8 NinjaScript Editor
  - Verify 0 compile errors
  - If compile errors: check namespace matches, verify Newtonsoft.Json available, check using declarations

  **Must NOT do**:
  - Do NOT modify the .cs file contents unless compile errors require it
  - Do NOT change namespace from `PeakAssetPerformance`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 7)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 8, 9, 10
  - **Blocked By**: Task 1

  **References**:
  - `ninjatrader/Custom/Indicators/PeakAssetPerformance/` — target indicator directory
  - NT8 NinjaScript Editor: Tools → Edit NinjaScript → F5

  **Acceptance Criteria**:
  - [ ] All 3 .cs files in NT8 live directories
  - [ ] F5 compile → 0 errors
  - [ ] InstitutionalConfluence appears in NT8 indicator list
  - [ ] EquilibriumModel appears in NT8 indicator list

  **QA Scenarios**:
  ```
  Scenario: NT8 compiles all 3 files
    Tool: Bash (HERMES via WSL)
    Steps:
      1. Deploy files to NT8 directories
      2. Trigger F5 compile
      3. Assert: 0 compile errors
      4. Screenshot NinjaScript Editor output
    Expected Result: Clean compilation
    Evidence: .sisyphus/evidence/task-6-nt8-compile.png
  ```

  **Commit**: YES (commit 4)

- [x] 7. Python Tests for Scoring + Equilibrium

  **What to do**:
  - Create `tests/confluence_system/test_scoring.py`:
    - Test weight assertion passes with defaults
    - Test weight assertion fails with bad weights
    - Test `normalize_dp()` with bullish/bearish/neutral inputs
    - Test `normalize_gex()` with above-flip/below-flip inputs
    - Test `normalize_regime()` with RISK_ON/RISK_OFF/NEUTRAL
    - Test `normalize_mtf()` with all zone combinations
    - Test `fuse_confluence()` produces correct score direction
    - Test `detect_alert()` fires STOP_BUYING, FULL_SEND_LONG correctly
    - Test `compute_dp_from_options()` (the new function replacing quantsynth)
    - Test `compute_regime_local()` (the new function replacing quantsynth)
  - Create `tests/confluence_system/test_equilibrium.py`:
    - Test `bs_gamma()` with known ATM/OTM values
    - Test `strike_gex()` call vs put sign convention
    - Test SFV weight assertion
    - Test `compute_equilibrium()` with mock data produces valid bands
    - Test regime classifier outputs valid states
  - Minimum 20 test cases across both files

  **Must NOT do**:
  - Do NOT mock external APIs with complex fixtures — test pure computation functions

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 5, 6)
  - **Parallel Group**: Wave 2
  - **Blocks**: —
  - **Blocked By**: Tasks 2, 3

  **Acceptance Criteria**:
  - [ ] `pytest tests/confluence_system/ -v` → all PASSED, 0 failures
  - [ ] Minimum 20 test cases
  - [ ] Tests cover both new replacement functions (compute_dp_from_options, compute_regime_local)

  **QA Scenarios**:
  ```
  Scenario: All tests pass
    Tool: Bash
    Steps:
      1. Run: pytest tests/confluence_system/ -v
      2. Assert: exit code 0, all passed
    Expected Result: Full test suite green
    Evidence: .sisyphus/evidence/task-7-pytest.txt
  ```

  **Commit**: YES (commit 3)

- [x] 8. End-to-End: Confluence HUD + GEX Lines + MTF Zones

  **What to do**:
  - Ensure Python middleware running on port 8767
  - Add InstitutionalConfluence indicator to 4H NQ chart in NT8:
    - Set ServerUrl = `http://127.0.0.1:8767`
    - Set PollIntervalSec = 30 (appropriate for 4H)
    - Enable: ShowGexLines=true, ShowMtfZones=true, ShowHud=true
  - Wait for first poll (~35 seconds)
  - Verify HUD panel renders top-right matching mockup:
    - "INSTITUTIONAL CONFLUENCE" title in gold
    - GEX bias line (green/red)
    - Dark pool bias line (green/red)
    - MTF zones (Daily/4H/Chart with color coding)
    - Score with breakdown
  - Verify GEX horizontal lines render:
    - Call Wall (blue/cyan dotted)
    - Put Wall (orange/magenta dotted)
    - Gamma Flip (yellow/magenta dashed)
  - Verify MTF zone bands render:
    - Premium zone (red shaded)
    - Discount zone (green shaded)
  - Screenshot for evidence

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 10 — different indicators)
  - **Parallel Group**: Wave 3
  - **Blocks**: —
  - **Blocked By**: Tasks 5, 6

  **Acceptance Criteria**:
  - [ ] HUD panel visible top-right on 4H NQ chart
  - [ ] GEX lines visible at correct prices
  - [ ] MTF zones visible as colored bands
  - [ ] Score displays with component breakdown

  **QA Scenarios**:
  ```
  Scenario: Confluence indicator renders correctly
    Tool: Bash (HERMES via WSL)
    Steps:
      1. Verify server running: curl http://127.0.0.1:8767/health
      2. Add InstitutionalConfluence to 4H NQ chart
      3. Wait 35 seconds
      4. Screenshot chart
      5. Verify HUD panel, GEX lines, MTF zones visible
    Expected Result: Full indicator rendering matching mockup
    Evidence: .sisyphus/evidence/task-8-confluence-e2e.png
  ```

  **Commit**: YES (commit 5)

- [x] 9. Equilibrium Model: SFV Line + Zone Bands + HUD

  **What to do**:
  - Add EquilibriumModel indicator to same 4H NQ chart:
    - Set ServerUrl = `http://127.0.0.1:8767`
    - Set PollIntervalSec = 60
    - Set NdxSymbol = `^NDX` (or correct NT8 symbol for NDX index)
    - Enable: ShowSfvLine=true, ShowZoneBands=true, ShowGexLines=true, ShowHud=true
  - Verify HUD panel renders top-LEFT (separate from Confluence HUD):
    - SFV value + distance from current price
    - Current zone (PREMIUM/EQUILIBRIUM/DISCOUNT)
    - Weekly + Daily GEX summary
    - 4-regime grid: Gamma / Vol / Trend / Institutional Bias
    - Alerts list
  - Verify SFV horizontal line (yellow dashed)
  - Verify premium/discount zone bands (volatility-adjusted)
  - Verify extreme bands (dotted lines at ±2.5σ)
  - Verify both HUDs coexist without overlap
  - Screenshot for evidence

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: —
  - **Blocked By**: Tasks 5, 6

  **Acceptance Criteria**:
  - [ ] Equilibrium HUD visible top-left (no overlap with Confluence HUD)
  - [ ] SFV line renders as yellow dashed horizontal
  - [ ] Zone bands visible (premium red, discount green)
  - [ ] 4-regime grid populated in HUD

  **QA Scenarios**:
  ```
  Scenario: Both indicators coexist on same chart
    Tool: Bash (HERMES via WSL)
    Steps:
      1. Ensure both indicators loaded on 4H NQ chart
      2. Screenshot full chart
      3. Verify Confluence HUD top-right, Equilibrium HUD top-left
      4. Verify no overlap between HUDs
      5. Verify SFV line + GEX lines both render
    Expected Result: Two HUDs side-by-side, all chart elements visible
    Evidence: .sisyphus/evidence/task-9-dual-hud.png
  ```

  **Commit**: YES (commit 5)

- [x] 10. Alert System: Conflict Alerts + NT8 Alert() Dispatch

  **What to do**:
  - Verify conflict alerts fire correctly from confluence endpoint:
    - Construct test scenario where GEX=bullish, DP=bearish, MTF=PREMIUM → STOP_BUYING
    - Construct test scenario where score >= +3, all aligned, RISK_ON → FULL_SEND_LONG
  - Verify NT8 renders alert box in HUD:
    - Red background rectangle for STOP_BUYING/STOP_SELLING
    - Alert text with code + reason
  - Verify NT8 Alert() fires (audible notification) on alert state change
  - Verify alert doesn't repeat on every poll (only on state change)
  - Verify Equilibrium Model alerts render in its HUD (CRITICAL/WARNING/INFO tiers)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 9)
  - **Parallel Group**: Wave 3
  - **Blocks**: —
  - **Blocked By**: Tasks 5, 6

  **Acceptance Criteria**:
  - [ ] STOP_BUYING alert renders in red box when conditions met
  - [ ] Alert clears when conditions no longer met
  - [ ] NT8 Alert() fires once per state change
  - [ ] Equilibrium alerts render in left HUD

  **QA Scenarios**:
  ```
  Scenario: Conflict alert renders in HUD
    Tool: Bash (HERMES via WSL + curl)
    Steps:
      1. Configure test data triggering STOP_BUYING
      2. Poll confluence endpoint
      3. Verify alert field in response JSON
      4. Verify red alert box in NT8 HUD screenshot
    Expected Result: Alert system functional end-to-end
    Evidence: .sisyphus/evidence/task-10-alerts.png
  ```

  **Commit**: YES (commit 5)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check all 6 source files deployed. Verify no quantsynth API key required.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `pytest tests/confluence_system/ -v`. Review adapted files for: broken imports, dead quantsynth code, empty catches, print() in prod. Verify weight assertions pass. Verify SharpDX brush disposal in both NT8 indicators. Check no duplicate FlashAlpha/Massive client instantiation.
  Output: `Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)
  Start confluence server. Curl all endpoints. Deploy all 3 .cs files to NT8. F5 compile. Load both indicators on 4H NQ chart. Verify Confluence HUD (top-right) + Equilibrium HUD (top-left) both render. Verify GEX lines. Verify SFV line. Screenshot evidence. Test graceful degradation (stop server, verify "—" placeholders).
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Verify all 6 source files present. Compare against provided files.zip originals. Verify ONLY quantsynth-related code was changed (minimal adaptation principle). Check no DEEP6Atlas.cs changes. Check no new client instances. Flag any unaccounted changes beyond quantsynth replacement.
  Output: `Files [N/N deployed] | Adaptation [MINIMAL/EXCESSIVE] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Commit | Tasks | Message | Pre-commit |
|--------|-------|---------|------------|
| 1 | 1, 4 | `feat(confluence): scaffold directory + deploy source files` | `python -c "import ast; ast.parse(open('confluence_system/confluence_server.py').read())"` |
| 2 | 2, 3 | `feat(confluence): replace quantsynth with nq_atlas local computation` | `python -c "from confluence_system.confluence_server import app"` |
| 3 | 5, 7 | `test(confluence): smoke test + unit tests for scoring and equilibrium` | `pytest tests/confluence_system/ -v` |
| 4 | 6 | `feat(confluence): deploy NT8 indicators + bias filter` | NT8 F5 compile |
| 5 | 8, 9, 10 | `feat(confluence): verified end-to-end with alerts + both HUDs` | Full QA pass |

---

## Success Criteria

### Verification Commands
```bash
# Python server starts and serves all endpoints
python confluence_system/confluence_server.py &
curl http://127.0.0.1:8767/health  # Expected: {"status": "ok"}
curl http://127.0.0.1:8767/status  # Expected: cache ages for each layer
curl 'http://127.0.0.1:8767/confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM' | python -m json.tool
curl 'http://127.0.0.1:8767/equilibrium/nq?price=21000' | python -m json.tool

# Tests pass
pytest tests/confluence_system/ -v  # Expected: all PASSED

# NT8 compiles (via HERMES)
# F5 in NinjaScript Editor → 0 errors for all 3 .cs files
```

### Final Checklist
- [ ] All 6 source files deployed in correct directories
- [ ] Server runs without quantsynth API key (no import errors, no crash)
- [ ] Scoring produces valid output with FlashAlpha + Massive data only
- [ ] Both NT8 HUDs render side-by-side (Confluence top-right, Equilibrium top-left)
- [ ] GEX lines render at correct prices
- [ ] SFV line renders on chart
- [ ] Conflict alerts fire correctly
- [ ] Graceful degradation when data unavailable
- [ ] All "Must NOT Have" absent (no DEEP6Atlas changes, no quantsynth requirement)
