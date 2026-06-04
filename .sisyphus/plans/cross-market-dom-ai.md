# Cross-Market MBO DOM + Options/GEX + MADLevels AI Engine

## TL;DR

> **Quick Summary**: Build a production-grade cross-market liquidity intelligence engine for NQ futures from scratch. Combines Rithmic MBO order book data (individual order IDs), options/GEX dealer positioning, and MADLevels absorption zones — all feeding an LLM expert reasoning layer and statistical classifiers. Output is WATCH assessments with falsifiable criteria, not auto-execution.
>
> **Deliverables**:
> - New `cross_market/` Python package (standalone, ~90 modules)
> - MBO order book reconstructor with order lifecycle tracking
> - 6 MBO-native detectors (spoof, iceberg, absorption, sweep, layering, vacuum)
> - Options/GEX/MADLevels context engines with cross-market confluence scoring
> - LLM expert reasoning layer (Claude Haiku, <500ms, strict JSON, exemplar retrieval)
> - XGBoost/LightGBM/CatBoost classifier pipeline with meta-model
> - Synchronized cross-market replay engine (Databento MBO)
> - Shadow mode (live without trading + 30s/60s outcome scoring)
> - FastAPI dashboard (DOM, GEX, MADLevels, AI decisions, replay)
>
> **Estimated Effort**: XL (7 phases, 46 tasks including 4 final verification)
> **Parallel Execution**: YES — 8 waves + final verification
> **Critical Path**: Task 1→3→9→10→11(HARD GATE)+13(replay parity)→15→28→30→32→37→F1-F4→user okay

---

> **DATA SOURCE NOTE (updated 2026-05-19)**:
> - NQStats removed — no API subscription available
> - Databento MBO subscription not active — no API key in `.env`
> - Available data: `data/backtests/nq_1yr_1m.csv` (Jan 2025 → Apr 2026, 458k 1-min bars, runs in ~7s)
> - Existing strategy with strong results: zones entry — Variant C: PF 4.48, WR 76.7%, Sharpe 8.68, MaxDD $1,366 over 16 months
> - Run: `python scripts/backtest_zones_1yr.py`

---

## Context

### Source Documents (External — must be copied into repo during Task 3)
- **Handoff**: `C:\Users\Tea\Downloads\Cross_Market_DOM_AI_Handoff.md` (1153 lines) — copy to `cross_market/docs/handoff.md`
- **Skills**: `C:\Users\Tea\Downloads\dom_expert_skills.md` (398 lines) — copy to `cross_market/llm_expert/dom_expert_skills.md`
- **Prompt**: `dom_expert_prompt.md` — to be authored during Task 30 based on handoff §9 and skills §1

> **CRITICAL**: All "Handoff §N" references below refer to `C:\Users\Tea\Downloads\Cross_Market_DOM_AI_Handoff.md`. All "dom_expert_skills.md §N" references refer to `C:\Users\Tea\Downloads\dom_expert_skills.md`. Task 3 MUST copy both into the `cross_market/` package before any downstream task can reference them as local paths.

### Original Request
User provided two comprehensive documents:
1. `Cross_Market_DOM_AI_Handoff.md` (1153 lines) — Full engineering handoff with architecture, schemas, detectors, build phases
2. `dom_expert_skills.md` (398 lines) — LLM expert competencies, 13 required competencies, 6 few-shot exemplars

### Interview Summary
**Key Decisions**:
- **Clean slate**: Do NOT reuse deep6v2 signals (44 signals) or scoring (confluence scorer) — they haven't been profitable
- **New package**: Standalone `cross_market/` package, not extending deep6v2
- **Reuse only plumbing**: Rithmic connection (`deep6v2.data.rithmic_client`), execution layer (`deep6v2.execution.*`), nq_atlas data clients (FlashAlpha, Massive.com, NQ mapper)
- **MBO confirmed**: async-rithmic's `DepthByOrder` proto has `exchange_order_id`, `update_type` (NEW/CHANGE/DELETE), `depth_order_priority` — full MBO capability
- **NQStats**: ~~NQStats.com (RoadToTrading) API~~ — REMOVED, no subscription
- **MADLevels**: Both integrate existing (NT8/Telegram alerts) AND build custom engine from MBO detectors
- **LLM**: Claude (Haiku for real-time <500ms, tool_use for structured JSON)
- **Test strategy**: TDD + Databento MBO replay validation
- **All 7 phases**: One comprehensive plan, profitability-validated at every phase

**Research Findings**:
- async-rithmic `DepthByOrder` proto: `exchange_order_id`, `update_type` (NEW/CHANGE/DELETE), `depth_order_priority`, `sequence_number` — confirmed MBO-capable
- Rithmic R|Protocol: `subscribe_order_book()` for MBO (native), `subscribe_order_book_summary()` for MBP
- **Subscription model**: `subscribe_to_market_depth(symbol, exchange, depth_price)` may require per-price subscriptions — must validate in Phase 0
- Databento MBO: `order_id` (u64), `action` (A/C/M/T/F/R), nanosecond timestamps, $179/mo
- Massive.com (ex-Polygon): Python SDK (`massive-api-client`), WebSocket + REST, real-time options chain/Greeks/IV/OI
- FlashAlpha: Growth tier ($49/mo), full GEX/DEX/VEX/CHEX/0DTE — already integrated in nq_atlas
- Claude Haiku: <500ms latency, tool_use for structured JSON, Anthropic SDK installed
- No production Python MBO reconstructor exists for CME — must build custom
- Existing reference: `deep6/backtest/mbo_adapter.py` converts Databento MBO → live callback shape

### Metis Review
**Identified Gaps** (addressed):
1. **Phase 0 Validation**: Added Wave 0 to verify MBO data availability before building entire system on it
2. **WATCH vs Execute**: Clarified — system produces WATCH assessments only. Execution layer reused for FUTURE capability, but initially outputs are advisory signals with falsifiable criteria
3. **Profitability Targets**: Added numerical targets — minimum profit factor 1.3, win rate >55% on replay, max drawdown <$2,000/session
4. **Per-Price Subscription Risk**: Added to Wave 0 — must test if `subscribe_to_market_depth()` requires per-price subscriptions or supports full-book subscription
5. **Existing MBO Adapter**: Referenced `deep6/backtest/mbo_adapter.py` as starting point for Databento replay engine
6. **NQStats API**: REMOVED — no subscription; session context dropped from scope
7. **MADLevels Import**: Designed dual-path — NT8 CSV/JSON export + Telegram webhook listener + custom engine

---

## Work Objectives

### Core Objective
Build a cross-market liquidity intelligence engine that determines whether a price level is real, fake, absorbing, spoofing, trapped, pinned, or ready to expand — using MBO order book data cross-referenced with options/GEX dealer positioning and MADLevels absorption zones.

### Concrete Deliverables
- `cross_market/` Python package with ~90 modules across 18 directories
- 6 MBO-native detectors with reason codes and confidence scores
- 3 context engines (Options, GEX, MADLevels) with level registry
- LLM expert layer with 13 competencies, exemplar retrieval, outcome logging
- 3 classifier pipelines (XGBoost, LightGBM, CatBoost) with meta-model
- Synchronized replay engine for backtesting validation
- Shadow mode for live paper validation
- FastAPI + dashboard for monitoring and replay review

### Definition of Done
- [ ] `pytest cross_market/tests/ -v` → all tests pass, >80% coverage on detectors
- [ ] MBO replay of full NQ session completes without book integrity errors
- [ ] Spoof/iceberg/absorption detectors produce reason-coded outputs on replay data
- [ ] LLM expert outputs strict JSON with confirmation/invalidation criteria on every call
- [ ] Shadow mode runs 5 full sessions, high-confidence calls confirm >70% on 30s forward
- [ ] Classifier out-of-sample profit factor ≥1.3 on held-out replay data

### Must Have
- Raw MBO events saved before any transformation (Parquet)
- Book reconstruction validated before any detector logic runs
- Order lifecycle tracked by `exchange_order_id` when available
- Every detector output includes `reason_codes[]`
- Every LLM output is strict JSON with `confirmation_criteria` and `invalidation_criteria`
- LLM never issues buy/sell/enter/exit commands — WATCH assessments only
- No repainting — historical labels separate from live inference
- Every prediction, snapshot, and outcome is logged
- Replay must work before live trading
- Shadow mode must work before production

### Must NOT Have (Guardrails)
- No reuse of deep6v2 signal definitions or scoring weights
- No auto-execution — system outputs WATCH states, not orders
- No LLM fine-tuning initially — operational training through prompts + exemplars only
- No lookahead in live mode — labels computed only from past data
- No single-detector decisions — require convergence of 3+ signals for high confidence
- No hardcoded thresholds without config — all parameters in `settings.yaml`
- No MBP fallback without explicit confidence degradation marking

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest 8.0+ with pytest-asyncio in pyproject.toml)
- **Automated tests**: TDD (RED → GREEN → REFACTOR)
- **Framework**: pytest + pytest-asyncio
- **Replay validation**: Databento MBO data for detector and classifier validation

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Detectors**: Run against Databento MBO replay → compare outputs against known patterns
- **LLM Expert**: Send test snapshots → verify strict JSON schema + competency checklist
- **Classifiers**: Train/test split → verify out-of-sample metrics
- **APIs/Connectors**: curl/httpx against test endpoints → assert response schemas
- **Shadow Mode**: Run mini-session → verify outcome logging + scoring

### Profitability Acceptance Criteria (from Metis review)
- **Profit Factor**: ≥1.3 on held-out replay data (Phase 6)
- **Win Rate**: >55% for high-confidence calls on 30s forward outcome (Phase 5)
- **Max Drawdown**: <$2,000 per simulated session (Phase 5)
- **Calibration**: High-confidence calls confirm more often than medium/low (Phase 5)
- **No-Signal Discipline**: System says "no edge" on >60% of snapshots (Phase 4)

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Validation — MUST PASS before any code):
├── Task 1: Verify Rithmic MBO (DepthByOrder) data [quick]
└── Task 2: Verify data provider connections [quick]

Wave 1 (Foundation — all parallel, start after Wave 0):
├── Task 3: Package scaffolding + config + settings.yaml [quick]
├── Task 4: Core types + data schemas (all Pydantic models) [quick]
├── Task 5: Raw event store + Parquet writer [quick]
├── Task 6: Connection health + WebSocket manager [quick]
├── Task 7: Time synchronization + monotonic clock [quick]
└── Task 8: Test infrastructure + conftest + fixtures [quick]

Wave 2 (Data Pipeline — after Wave 1):
├── Task 9: MBO connector (DepthByOrder via async-rithmic) [deep]
├── Task 10: MBO order book reconstructor + order lifecycle tracker [deep]
├── Task 11: Book integrity validator [unspecified-high]  ◆ HARD GATE — must PASS before ANY Wave 3 detector runs
├── Task 12: Trade classifier + aggressor detector + delta engine [unspecified-high]
├── Task 13: Databento MBO replay engine [deep]  ◆ Replay parity check is part of the HARD GATE
└── Task 14: Queue position tracker [unspecified-high]
HARD GATE: Task 11 (book integrity) + Task 13 (replay parity) must both pass verification
before ANY detector in Wave 3 starts. This is NOT a soft dependency — if book reconstruction
has integrity errors or replay doesn't match sequential processing, ALL downstream work is invalid.

Wave 3 (Detectors — all parallel after Wave 2):
├── Task 15: Spoof detector (order lifecycle-based) [deep]
├── Task 16: Iceberg detector (refresh tracking via order IDs) [deep]
├── Task 17: Absorption detector (MBO-native) [deep]
├── Task 18: Sweep detector [unspecified-high]
├── Task 19: Layering detector [unspecified-high]
└── Task 20: Liquidity vacuum detector [unspecified-high]

Wave 4 (Context Engines — STAGGERED start, see notes):
├── Task 21: Options chain engine (Massive.com) [unspecified-high]  ← starts after Wave 0/1 (parallel with Wave 2)
├── Task 22: Options flow engine + dealer pressure [unspecified-high]  ← starts after Task 21
├── Task 23: GEX engine (FlashAlpha + regime) [unspecified-high]  ← starts after Wave 0/1 (parallel with Wave 2)
├── ~~Task 24: NQStats engine~~ REMOVED — no subscription
├── Task 25: MADLevels engine (custom + NT8/Telegram import) [deep]  ← starts after Wave 3 (depends on ALL detectors T15-20)
├── Task 26: Level registry + freshness scoring [unspecified-high]  ← starts after Tasks 21-25 all complete
└── Task 27: Confluence scoring engine [deep]  ← starts after Task 26
NOTE: T21, T23, T24 depend only on Wave 0/1 — they can run in parallel with Wave 2/3.
      T25 depends on ALL Wave 3 detectors (T15-20). T26-27 are sequential at the tail.

Wave 5 (LLM Expert — after Waves 3+4):
├── Task 28: Feature extraction (DOM + cross-market) [unspecified-high]
├── Task 29: Expert rules + no-trade rules [unspecified-high]
├── Task 30: Snapshot builder [unspecified-high]
├── Task 31: Exemplar store + retriever [deep]
├── Task 32: LLM router + strict JSON (Claude tool_use) [deep]
└── Task 33: Outcome logger + critic + exemplar curator [deep]

Wave 6 (Classifiers + Shadow — after Wave 5):
├── Task 34: Label generator [unspecified-high]
├── Task 35: XGBoost/LightGBM/CatBoost pipelines [deep]
├── Task 36: Meta-model + inference engine [deep]
├── Task 37: Shadow mode runner [deep]
└── Task 38: Synchronized cross-market replay [deep]

Wave 7 (Dashboard + Hardening — after Wave 6):
├── Task 39: DOM + GEX + AI dashboards [visual-engineering]
├── Task 40: MADLevels + replay dashboards [visual-engineering]
├── Task 41: Risk engine + trade filter + calibrator [deep]
├── Task 42: Health monitor + alert engine [unspecified-high]
└── Task 43: Production entry point + README [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real agent-executed QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: T1→T3→T9→T10→T11(HARD GATE)+T13(replay parity)→T15→T28→T30→T32→T37→F1-F4→user okay
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 7-8 (Wave 2 + Wave 4 early tasks T21/T23/T24 overlap)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 3-8 | 0 |
| 2 | — | 21-25 | 0 |
| 3 | 1 | 9-14, 21-27 | 1 |
| 4 | 1 | 9-14, 21-27, 28-33 | 1 |
| 5 | 1 | 9, 13 | 1 |
| 6 | 1 | 9 | 1 |
| 7 | 1 | 9, 13 | 1 |
| 8 | 1,4 | all tests | 1 |
| 9 | 3,4,5,6,7 | 10,11,12,14 | 2 |
| 10 | 4,9 | 11,14,15-20 | 2 |
| 11 | 10 | 15-20 (HARD GATE) | 2 |
| 12 | 4,9 | 17,18,20 | 2 |
| 13 | 4,5,7 | 15-20 (HARD GATE), 34, 38 | 2 |
| 14 | 10 | 15 | 2 |
| 15 | 10,11,13,14 | 28 | 3 |
| 16 | 10,11,13 | 28 | 3 |
| 17 | 10,11,12,13 | 25,28 | 3 |
| 18 | 11,12,13 | 28 | 3 |
| 19 | 10,11,13 | 28 | 3 |
| 20 | 10,11,12,13 | 28 | 3 |
| 21 | 2,4 | 22,26 | 4 |
| 22 | 21 | 27,28 | 4 |
| 23 | 2,4 | 26,27 | 4 |
| 24 | REMOVED (NQStats — no subscription) | — | — |
| 25 | 15-20 | 26,27 | 4 |
| 26 | 21-23, 25 | 27 | 4 |
| 27 | 26 | 28,29,30 | 4 |
| 28 | 15-20, 22-23, 25-27 | 29,30,34 | 5 |
| 29 | 28 | 30 | 5 |
| 30 | 28,29 | 31,32 | 5 |
| 31 | 30 | 32 | 5 |
| 32 | 30,31 | 33,37 | 5 |
| 33 | 32 | 37 | 5 |
| 34 | 13,28 | 35 | 6 |
| 35 | 34 | 36 | 6 |
| 36 | 35 | 37 | 6 |
| 37 | 32,33,36 | 39-43 | 6 |
| 38 | 13,28 | 40 | 6 |
| 39 | 37 | F1-F4 | 7 |
| 40 | 38 | F1-F4 | 7 |
| 41 | 27,36 | F1-F4 | 7 |
| 42 | 37 | F1-F4 | 7 |
| 43 | 37 | F1-F4 | 7 |

### Agent Dispatch Summary

- **Wave 0**: **2** — T1→`quick`, T2→`quick`
- **Wave 1**: **6** — T3-T8→`quick`
- **Wave 2**: **6** — T9→`deep`, T10→`deep`, T11→`unspecified-high`, T12→`unspecified-high`, T13→`deep`, T14→`unspecified-high`
- **Wave 3**: **6** — T15→`deep`, T16→`deep`, T17→`deep`, T18→`unspecified-high`, T19→`unspecified-high`, T20→`unspecified-high`
- **Wave 4**: **6** — T21-T22→`unspecified-high`, T23→`unspecified-high`, T25→`deep`, T26→`unspecified-high`, T27→`deep` (T24 removed)
- **Wave 5**: **6** — T28-T30→`unspecified-high`, T31→`deep`, T32→`deep`, T33→`deep`
- **Wave 6**: **5** — T34→`unspecified-high`, T35→`deep`, T36→`deep`, T37→`deep`, T38→`deep`
- **Wave 7**: **5** — T39-T40→`visual-engineering`, T41→`deep`, T42→`unspecified-high`, T43→`quick`
- **FINAL**: **4** — F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep`

---

## TODOs

> Implementation + Test = ONE Task. Every task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Verify Rithmic MBO (DepthByOrder) Data Availability

  **What to do**:
  - Connect to Rithmic test environment (`wss://rituz00100.rithmic.com`) using `async_rithmic` library directly (NOT the deep6v2 wrapper — it lacks subscription methods)
  - Subscribe to NQ via `subscribe_to_market_depth()` / `DataType.ORDER_BOOK`
  - Load credentials from process environment: `RITHMIC_USER` (not USERNAME), `RITHMIC_PASSWORD`, `RITHMIC_SYSTEM_NAME`, `RITHMIC_URI` — or load `.env` via `python-dotenv`
  - Verify `DepthByOrder` messages arrive with: `exchange_order_id`, `update_type` (NEW/CHANGE/DELETE), `depth_order_priority`, `sequence_number`
  - Test subscription model: does it require per-price subscriptions or deliver full book?
  - Log raw protobuf messages to file for analysis
  - If MBO is NOT available: document what IS available, report to user immediately — this blocks the entire plan
  - Write test: `test_rithmic_mbo_fields.py`

  **Must NOT do**:
  - Do not build any production code — this is validation only
  - Do not modify deep6v2 Rithmic client

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2)
  - **Parallel Group**: Wave 0
  - **Blocks**: Tasks 3-8 (all Wave 1)
  - **Blocked By**: None

  **References**:
  - `deep6v2/data/rithmic_client.py` — existing Rithmic connection wrapper
  - `deep6v2/config/rithmic.py` — Rithmic config (URI, credentials, reconnect)
  - `.env.example` — `RITHMIC_USER`, `RITHMIC_PASSWORD`, `RITHMIC_SYSTEM_NAME`, `RITHMIC_URI` variables (note: env var is `RITHMIC_USER`, not `RITHMIC_USERNAME`)
  - `tests_v2/integration/test_rithmic_connection.py` — existing integration test pattern using `RITHMIC_USER` env var
  - async-rithmic `depth_by_order.proto`: https://github.com/rundef/async_rithmic/blob/main/async_rithmic/protocol_buffers/source/depth_by_order.proto — DepthByOrder message definition with `exchange_order_id`, `update_type`, `depth_order_priority`
  - async-rithmic real-time docs: https://async-rithmic.readthedocs.io/en/latest/realtime_data.html — subscription methods

  **Acceptance Criteria**:
  - [ ] Test file: `cross_market/tests/test_rithmic_mbo_validation.py`
  - [ ] Raw protobuf log saved: `.sisyphus/evidence/task-1-mbo-raw.log`

  **QA Scenarios**:
  ```
  Scenario: MBO fields present in DepthByOrder messages
    Tool: Bash (python script)
    Preconditions: Rithmic test environment accessible, credentials in .env
    Steps:
      1. Run: python -c "import asyncio; from cross_market.tests.test_rithmic_mbo_validation import validate_mbo; asyncio.run(validate_mbo())"
      2. Script connects to wss://rituz00100.rithmic.com
      3. Subscribes to NQ depth
      4. Captures first 100 DepthByOrder messages
      5. Asserts each message has: exchange_order_id (non-empty), update_type (in [NEW,CHANGE,DELETE]), depth_order_priority (>0), sequence_number (>0)
    Expected Result: All 100 messages have required MBO fields. Log file created.
    Failure Indicators: Empty exchange_order_id, missing update_type, connection refused, or timeout >30s
    Evidence: .sisyphus/evidence/task-1-mbo-fields.txt

  Scenario: MBO subscription model test
    Tool: Bash (python script)
    Preconditions: Connection established
    Steps:
      1. Subscribe with single call (no per-price parameter)
      2. Observe if messages arrive for multiple price levels
      3. If single-call works: log "FULL_BOOK" mode
      4. If not: test per-price subscription for 5 price levels, log "PER_PRICE" mode
    Expected Result: Subscription model documented. Either FULL_BOOK or PER_PRICE with workaround.
    Failure Indicators: No messages arrive, or only partial book
    Evidence: .sisyphus/evidence/task-1-subscription-model.txt
  ```

  **Commit**: YES
  - Message: `chore(cross_market): validate Rithmic MBO DepthByOrder availability`
  - Files: `cross_market/tests/test_rithmic_mbo_validation.py`

- [ ] 2. Verify Data Provider Connections

  **What to do**:
  - Test Massive.com/Polygon options chain API: fetch QQQ chain, verify Greeks/IV/OI fields
  - Test FlashAlpha API: fetch exposure_summary for QQQ, verify GEX/DEX/VEX/CHEX fields
  - ~~Test NQStats.com API~~ — REMOVED from scope
  - Test Databento MBO historical: fetch 5 minutes of NQ MBO data, verify `order_id` + `action` fields
  - Write validation script: `validate_providers.py`

  **Must NOT do**:
  - Do not build production connectors — validation only
  - Do not store credentials in code

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 1)
  - **Parallel Group**: Wave 0
  - **Blocks**: Tasks 21-25 (context engines)
  - **Blocked By**: None

  **References**:
  - `nq_atlas/flashalpha_client.py` — existing FlashAlpha polling client
  - `nq_atlas/massive_client.py` — existing Polygon/Massive options chain client
  - `.env.example` — API keys for all providers
  - Massive.com docs: https://massive.com/docs/rest/options/snapshots/option-chain-snapshot
  - FlashAlpha skill: `.claude/skills/flashalpha-options/api-reference.md`
  - Databento MBO schema: https://databento.com/docs/schemas-and-data-formats/mbo

  **Acceptance Criteria**:
  - [ ] Validation script: `cross_market/tests/test_provider_validation.py`
  - [ ] Provider status report saved to `.sisyphus/evidence/task-2-providers.txt`

  **QA Scenarios**:
  ```
  Scenario: All provider connections verified
    Tool: Bash (python script)
    Preconditions: API keys in .env for Massive, FlashAlpha, Databento
    Steps:
      1. Run: python cross_market/tests/test_provider_validation.py
      2. Script attempts: Massive QQQ chain fetch, FlashAlpha exposure_summary, Databento NQ MBO sample
      3. Each provider: assert response has expected fields (Greeks for Massive, GEX for FlashAlpha, order_id for Databento)
    Expected Result: Status report: Massive=OK, FlashAlpha=OK, Databento=OK
    Failure Indicators: Any provider returns 401/403 (auth), 404 (endpoint), or timeout
    Evidence: .sisyphus/evidence/task-2-provider-status.txt


  ```

  **Commit**: YES
  - Message: `chore(cross_market): validate data provider connections`
  - Files: `cross_market/tests/test_provider_validation.py`

- [ ] 3. Package Scaffolding + Config + settings.yaml

  **What to do**:
  - **FIRST**: Copy source documents into repo:
    - `C:\Users\Tea\Downloads\Cross_Market_DOM_AI_Handoff.md` → `cross_market/docs/handoff.md`
    - `C:\Users\Tea\Downloads\dom_expert_skills.md` → `cross_market/llm_expert/dom_expert_skills.md`
  - Create `cross_market/docs/` directory for reference documentation
  - Create `cross_market/` directory structure matching handoff §2 architecture
  - Create `pyproject.toml` (or add to existing) with cross_market package entry
  - Create `cross_market/__init__.py`, `cross_market/__main__.py` (CLI entry)
  - Create `cross_market/config/settings.yaml` with all configurable thresholds from handoff §8 (confluence weights, detector thresholds, session times, LLM settings)
  - Create `cross_market/config/symbols.yaml` (NQ tick size, contract specs)
  - Create `cross_market/config/sessions.yaml` (Asia/London/NY session times, macro windows)
  - Create `cross_market/config/thresholds.yaml` (spoof, iceberg, absorption, sweep thresholds)
  - Create `cross_market/config/app.py` (Pydantic Settings loading from yaml + env)
  - All 18 subdirectories: connectors/, book/, tape/, options/, stats/, levels/, features/, rules/, llm_expert/, models/, labels/, replay/, storage/, dashboard/, risk/, tests/, config/, types/

  **Must NOT do**:
  - Do not import any deep6v2 signal or scoring modules
  - Do not create implementation code — only scaffolding with `__init__.py` and config

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 4-8)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 9-14, 21-27
  - **Blocked By**: Task 1 (MBO validation must pass)

  **References**:
  - Handoff §2 `Final System Architecture` — complete directory tree with all file names
  - `deep6v2/config/app.py` — Pydantic Settings pattern to follow
  - `pyproject.toml` — existing project config (add cross_market package discovery)
  - Handoff §8 `Confluence Scoring` — weight values for settings.yaml

  **Acceptance Criteria**:
  - [ ] `cross_market/` directory with 18 subdirectories created (including types/ and docs/)
  - [ ] `cross_market/config/settings.yaml` contains all threshold values from handoff
  - [ ] `python -c "import cross_market"` succeeds

  **QA Scenarios**:
  ```
  Scenario: Package importable and structure matches handoff
    Tool: Bash
    Preconditions: Package scaffolding created
    Steps:
      1. Run: python -c "import cross_market; print(cross_market.__name__)"
      2. Run: python -c "from cross_market.config.app import Settings; s = Settings(); print(s)"
      3. Verify directories exist: for d in connectors book tape options stats levels features rules llm_expert models labels replay storage dashboard risk tests config types docs; check cross_market/$d/__init__.py exists
    Expected Result: Import succeeds, Settings loads from yaml, all 18 subdirectories exist with __init__.py
    Failure Indicators: ImportError, missing directory, yaml parse error
    Evidence: .sisyphus/evidence/task-3-scaffold.txt

  Scenario: Settings contain all handoff thresholds
    Tool: Bash
    Preconditions: settings.yaml created
    Steps:
      1. Parse settings.yaml
      2. Assert keys exist: spoof.life_ms_threshold, spoof.size_multiplier, iceberg.ratio_threshold, iceberg.min_refreshes, absorption.min_trades, confluence.madlevel_weight, confluence.gex_weight, confluence.dom_weight, llm.model, llm.timeout_ms
    Expected Result: All threshold keys present with numeric values
    Evidence: .sisyphus/evidence/task-3-settings.txt
  ```

  **Commit**: YES (groups with Tasks 4-8)
  - Message: `feat(cross_market): package scaffolding, config, settings`
  - Files: `cross_market/**/__init__.py`, `cross_market/config/*.yaml`, `cross_market/config/app.py`

- [ ] 4. Core Types + Data Schemas

  **What to do**:
  - Create Pydantic models for ALL data schemas from handoff §3:
    - `cross_market/types/mbo_event.py`: MBOEvent (§3.1 — timestamp_exchange_ns, source, symbol, event_type, side, price, size, order_id, sequence_id, etc.)
    - `cross_market/types/options_event.py`: OptionsEvent (§3.2 — underlying, strike, type, Greeks, IV, OI)
    - `cross_market/types/gex_event.py`: GEXEvent (§3.3 — net_gex, zero_gamma, call_wall, put_wall, dex, vex, chex, regime)
    - `cross_market/types/level.py`: LevelRegistryObject (§3.4 — source_types, level_type, freshness_score, confluence_score, status)
  - Create detector output types from handoff §4:
    - `cross_market/types/detectors.py`: SpoofResult, IcebergResult, AbsorptionResult, SweepResult, LayeringResult, VacuumResult
  - Create LLM types from handoff §9:
    - `cross_market/types/llm.py`: LLMInput, LLMAssessment (primary_pattern, evidence, confidence, confirmation_criteria, invalidation_criteria, trader_read)
  - Create classifier types from handoff §11:
    - `cross_market/types/classifier.py`: MetaModelOutput (bullish/bearish/neutral probabilities, spoof/iceberg/absorption probabilities)
  - ~~NQStats types~~ — REMOVED (no subscription)
  - Create MADLevel types from handoff §7:
    - `cross_market/types/madlevel.py`: MADLevel (level_price, level_type, touch_count, absorption_score, status)
  - Create exemplar type from handoff §10:
    - `cross_market/types/exemplar.py`: Exemplar (snapshot, gold_assessment, pattern, outcome_30s, outcome_60s, was_correct)
  - Write tests for all type validation (Pydantic validation rules)

  **Must NOT do**:
  - Do not import deep6v2/types/ — create fresh types matching handoff schemas exactly
  - Do not add business logic to type definitions

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3, 5-8)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 9-14, 21-33
  - **Blocked By**: Task 1

  **References**:
  - Handoff §3.1 `Futures MBO event` — exact JSON schema for MBOEvent
  - Handoff §3.2 `Options event` — exact JSON schema for OptionsEvent
  - Handoff §3.3 `GEX event` — exact JSON schema for GEXEvent
  - Handoff §3.4 `Level registry object` — exact JSON schema for LevelRegistryObject
  - Handoff §4.1 `Spoof detector output` — SpoofResult schema
  - Handoff §9.3 `LLM output` — LLMAssessment JSON schema
  - Handoff §11.3 `Meta-model output` — MetaModelOutput JSON schema

  - Handoff §7.2 `MADLevel object` — MADLevel JSON schema
  - Handoff §10.1 `Exemplar database` — Exemplar schema

  **Acceptance Criteria**:
  - [ ] Test file: `cross_market/tests/test_types.py`
  - [ ] `pytest cross_market/tests/test_types.py` → PASS (all schemas validate)

  **QA Scenarios**:
  ```
  Scenario: All Pydantic models validate against handoff JSON schemas
    Tool: Bash
    Preconditions: Type files created
    Steps:
      1. Run: pytest cross_market/tests/test_types.py -v
      2. Tests instantiate each model with valid data from handoff examples
      3. Tests verify required fields raise ValidationError when missing
      4. Tests verify enum constraints (event_type, side, level_type, etc.)
    Expected Result: All type tests pass. Every field from handoff §3 schemas is represented.
    Failure Indicators: ValidationError on valid data, missing field, wrong type
    Evidence: .sisyphus/evidence/task-4-types.txt

  Scenario: Type models reject invalid data
    Tool: Bash
    Preconditions: Type files created
    Steps:
      1. Test: MBOEvent with negative price → ValidationError
      2. Test: SpoofResult with life_ms < 0 → ValidationError
      3. Test: LLMAssessment without confirmation_criteria → ValidationError
      4. Test: GEXEvent with invalid regime string → ValidationError
    Expected Result: All invalid inputs correctly rejected
    Evidence: .sisyphus/evidence/task-4-types-invalid.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(cross_market): core Pydantic types for all data schemas`
  - Files: `cross_market/types/*.py`, `cross_market/tests/test_types.py`

- [ ] 5. Raw Event Store + Parquet Writer

  **What to do**:
  - `cross_market/storage/raw_event_store.py`: Append-only store for all raw events BEFORE transformation. Must handle 1,000+ events/sec. Buffer in memory, flush to Parquet periodically (every 5s or 10,000 events).
  - `cross_market/storage/parquet_writer.py`: Write MBO events, options events, GEX events to partitioned Parquet files (by date/session). Use PyArrow.
  - `cross_market/storage/feature_store.py`: Store computed features per timestamp (for classifier training).
  - `cross_market/storage/prediction_store.py`: Store LLM assessments and classifier predictions.
  - `cross_market/storage/outcome_store.py`: Store 30s/60s outcome results linked to prediction_id.
  - All stores must support: append, query by time range, query by pattern type, export to DataFrame.
  - **File ownership**: This task owns `raw_event_store.py`, `parquet_writer.py`, `feature_store.py`, `prediction_store.py`, `outcome_store.py` ONLY. The `exemplar_store.py` is owned by Task 31 (exemplar retrieval system).
  - Write tests with synthetic data.

  **Must NOT do**: Do not use deep6v2 persistence (SQLite/DuckDB) — use Parquet for raw events, DuckDB only for analytics queries.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3,4,6-8)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 9, 13
  - **Blocked By**: Task 1

  **References**:
  - Handoff §2 `/storage` directory — all store file names
  - `deep6v2/state/persistence.py` — existing persistence pattern (reference only, don't import)
  - PyArrow Parquet: https://arrow.apache.org/docs/python/parquet.html

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_storage.py` → PASS
  - [ ] Can write 10,000 MBO events and read back with time-range query in <1s

  **QA Scenarios**:
  ```
  Scenario: Raw event store handles 1,000+ events/sec
    Tool: Bash
    Steps:
      1. Generate 10,000 synthetic MBOEvents
      2. Write all to raw_event_store at >1,000/sec rate
      3. Flush to Parquet
      4. Read back with time-range query covering middle 1,000 events
      5. Assert all 1,000 events returned with correct fields
    Expected Result: Write throughput >1,000 events/sec. Read returns exact match.
    Evidence: .sisyphus/evidence/task-5-throughput.txt

  Scenario: Parquet partitioning by date
    Tool: Bash
    Steps:
      1. Write events spanning 3 dates
      2. Query single date
      3. Assert only that date's events returned
      4. Check file system: separate Parquet files per date
    Expected Result: Partition pruning works, only relevant files read
    Evidence: .sisyphus/evidence/task-5-partition.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(cross_market): raw event store and Parquet writer`
  - Files: `cross_market/storage/*.py`, `cross_market/tests/test_storage.py`

- [ ] 6. Connection Health + WebSocket Manager

  **What to do**:
  - `cross_market/connectors/websocket_manager.py`: Generic async WebSocket manager with: auto-reconnect (exponential backoff + jitter), heartbeat monitoring, connection state tracking, message rate monitoring.
  - `cross_market/connectors/connection_health.py`: Health check registry. Each connector reports: connected/disconnected, last message time, message rate, latency, error count. Aggregated health status (GREEN/YELLOW/RED).
  - Must handle: Rithmic disconnect, Massive.com rate limits, FlashAlpha polling failures.
  - Write tests with mock WebSocket server.

  **Must NOT do**: Do not build Rithmic-specific logic here — this is generic infrastructure.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3-5, 7-8)
  - **Parallel Group**: Wave 1
  - **Blocks**: Task 9
  - **Blocked By**: Task 1

  **References**:
  - Handoff §2 `/connectors` — `websocket_manager.py`, `connection_health.py`
  - `deep6v2/data/rithmic_client.py` — existing FreezeGuard safety gate pattern (reference)
  - `nq_atlas/orchestrator.py` — existing async orchestration pattern (reference)

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_connection.py` → PASS
  - [ ] Health check reports correct state for connected/disconnected mock

  **QA Scenarios**:
  ```
  Scenario: WebSocket reconnects after disconnect
    Tool: Bash
    Steps:
      1. Start mock WebSocket server
      2. Connect websocket_manager
      3. Kill mock server (simulate disconnect)
      4. Assert health transitions to RED
      5. Restart mock server
      6. Assert auto-reconnect within 10s
      7. Assert health transitions back to GREEN
    Expected Result: Auto-reconnect works, health state accurate
    Evidence: .sisyphus/evidence/task-6-reconnect.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `cross_market/connectors/websocket_manager.py`, `cross_market/connectors/connection_health.py`

- [ ] 7. Time Synchronization + Monotonic Clock

  **What to do**:
  - `cross_market/connectors/time_sync.py`: Unified time management per handoff §1.3:
    - Monotonic event clock (strictly increasing)
    - Dual timestamps: provider timestamp (exchange) + local receipt timestamp
    - Latency measurement per source (Rithmic, Massive, FlashAlpha)
    - UTC storage everywhere
    - Exchange/session timezone conversion (ET for NQ)
    - Event-time vs processing-time separation
    - NTP drift detection (warn if local clock >50ms off)
  - Write tests verifying monotonic ordering and timezone conversion.

  **Must NOT do**: Do not use `datetime.now()` anywhere — all times via the unified clock.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3-6, 8)
  - **Parallel Group**: Wave 1
  - **Blocks**: Tasks 9, 13
  - **Blocked By**: Task 1

  **References**:
  - Handoff §1.3 `Time synchronization matters` — all requirements listed
  - `deep6v2/clock.py` — existing clock module (reference pattern)

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_time_sync.py` → PASS
  - [ ] Timestamps are always monotonic even with out-of-order inputs

  **QA Scenarios**:
  ```
  Scenario: Monotonic clock handles out-of-order events
    Tool: Bash
    Steps:
      1. Feed 100 events with deliberately out-of-order timestamps
      2. Assert unified clock assigns monotonically increasing sequence
      3. Assert original provider timestamps preserved alongside
    Expected Result: Monotonic sequence maintained, original timestamps available
    Evidence: .sisyphus/evidence/task-7-monotonic.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `cross_market/connectors/time_sync.py`, `cross_market/tests/test_time_sync.py`

- [ ] 8. Test Infrastructure + conftest + Fixtures

  **What to do**:
  - `cross_market/tests/conftest.py`: Shared pytest fixtures for all test modules:
    - `sample_mbo_event()`: Factory for synthetic MBO events
    - `sample_depth_snapshot()`: 10-level bid/ask book
    - `sample_options_event()`: QQQ option with Greeks
    - `sample_gex_event()`: GEX snapshot with regime
    - `sample_spoof_sequence()`: Order lifecycle (ADD → CANCEL in 2s, no fills)
    - `sample_iceberg_sequence()`: Order lifecycle with refreshes (ratio 20x)
    - `sample_absorption_sequence()`: 200 contracts traded, level holds
  - `cross_market/tests/fixtures/`: JSON fixture files matching handoff schemas
  - Copy DOM expert exemplars from `dom_expert_skills.md` §2 into `cross_market/tests/fixtures/exemplars/` as JSON
  - Configure pytest in cross_market package (markers: integration, slow, replay)

  **Must NOT do**: Do not copy fixtures from tests_v2/ — create fresh matching handoff schemas.

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 3-7)
  - **Parallel Group**: Wave 1
  - **Blocks**: All subsequent tests
  - **Blocked By**: Task 4 (needs types)

  **References**:
  - `tests_v2/conftest.py` — existing fixture patterns (reference)
  - `dom_expert_skills.md` §2 — 6 exemplar snapshots + gold assessments (EXEMPLAR 1-6)
  - Handoff §3 — all data schemas for fixture generation

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/ --collect-only` shows fixtures available
  - [ ] All 6 exemplars from dom_expert_skills.md converted to JSON fixtures

  **QA Scenarios**:
  ```
  Scenario: Fixtures generate valid typed objects
    Tool: Bash
    Steps:
      1. Run: pytest cross_market/tests/test_fixtures.py -v
      2. Each fixture factory creates a valid Pydantic model instance
      3. Spoof sequence has correct lifecycle (ADD → CANCEL, life_ms < 5000)
      4. Iceberg sequence has traded_cum/peak_visible ratio > 3x
    Expected Result: All fixture factories produce valid, schema-compliant objects
    Evidence: .sisyphus/evidence/task-8-fixtures.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `cross_market/tests/conftest.py`, `cross_market/tests/fixtures/*.json`

- [ ] 9. MBO Connector (DepthByOrder via async-rithmic)

  **What to do**:
  - `cross_market/connectors/rithmic_mbo_connector.py`: Subscribe to `DepthByOrder` messages (not aggregated OrderBook). Parse repeated fields: `exchange_order_id[]`, `update_type[]`, `depth_price[]`, `depth_size[]`, `depth_order_priority[]`, `transaction_type[]`, `sequence_number`. Handle update batches (BEGIN/MIDDLE/END/SOLO). Emit individual `MBOEvent` objects to downstream consumers via async queue. Integrate with connection_health for status reporting.
  - Handle subscription model discovered in Task 1 (FULL_BOOK or PER_PRICE with subscription manager).
  - Persist raw DepthByOrder messages to raw_event_store BEFORE parsing.
  - Write integration test against Rithmic test environment.

  **Must NOT do**: Do not modify `deep6v2.data.rithmic_client` — wrap it. Do not aggregate to MBP — keep individual orders.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 10-14 after dependencies met)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 10, 11, 12, 14
  - **Blocked By**: Tasks 3, 4, 5, 6, 7

  **References**:
  - Task 1 evidence: `.sisyphus/evidence/task-1-mbo-fields.txt` — confirmed MBO field availability
  - Task 1 evidence: `.sisyphus/evidence/task-1-subscription-model.txt` — FULL_BOOK or PER_PRICE
  - `deep6v2/data/rithmic_client.py` — Rithmic connection wrapper to reuse
  - async-rithmic `depth_by_order.proto` — DepthByOrder message definition
  - async-rithmic docs: https://async-rithmic.readthedocs.io/en/latest/realtime_data.html

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_mbo_connector.py` → PASS
  - [ ] Can receive and parse 1,000+ DepthByOrder messages/sec without backpressure

  **QA Scenarios**:
  ```
  Scenario: MBO connector emits individual order events
    Tool: Bash
    Preconditions: Rithmic test env accessible
    Steps:
      1. Start connector, subscribe to NQ
      2. Collect 500 MBOEvent objects from async queue
      3. Assert each has: order_id (non-empty), event_type (add|modify|cancel|trade), price, size, side, sequence_id
      4. Assert events arrive at >100/sec sustained rate
    Expected Result: 500 events collected with all required fields
    Evidence: .sisyphus/evidence/task-9-mbo-events.txt

  Scenario: Raw events persisted before parsing
    Tool: Bash
    Steps:
      1. Start connector for 10 seconds
      2. Check raw_event_store: assert raw DepthByOrder bytes saved
      3. Assert raw count >= parsed event count (no drops)
    Expected Result: Raw persistence confirmed, zero event loss
    Evidence: .sisyphus/evidence/task-9-raw-persist.txt
  ```

  **Commit**: YES
  - Message: `feat(cross_market): MBO connector via DepthByOrder`
  - Files: `cross_market/connectors/rithmic_mbo_connector.py`

- [ ] 10. MBO Order Book Reconstructor + Order Lifecycle Tracker

  **What to do**:
  - `cross_market/book/mbo_order_book.py`: Maintain full order book state from individual order events. Data structure: dict of `{order_id: OrderState}` where OrderState tracks price, size, side, add_time, modify_count, priority. Also maintain price-level aggregation (for quick depth queries). Handle NEW (add order), CHANGE (modify price/size), DELETE (cancel), and TRADE (fill) events. Emit events on significant state changes.
  - `cross_market/book/order_lifecycle_tracker.py`: Track complete lifecycle per `exchange_order_id`: time_added, time_modified[], time_cancelled, time_traded, original_size, final_size, fills[], life_duration_ms, was_filled, fill_ratio. This is the foundation for spoof/iceberg detection.
  - `cross_market/book/book_reconstructor.py`: Orchestrates MBOEvent stream → order_book state + lifecycle tracking. Handles atomic update batches (BEGIN→END). Supports snapshot initialization.
  - `cross_market/book/mbp_order_book.py`: Aggregated view derived from MBO state — for consumers that need price-level depth (e.g., imbalance calculation). Clearly marked as derived, not primary.
  - Write extensive tests: add/modify/cancel sequences, concurrent orders at same price, order replacement.

  **Must NOT do**: Do not use bmoscon/orderbook (loses order IDs). Do not use dict for hot-path lookups — use sorted structures or NumPy arrays indexed by price.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 9)
  - **Parallel Group**: Wave 2 (sequential within wave)
  - **Blocks**: Tasks 11, 14, 15-20
  - **Blocked By**: Tasks 4, 9

  **References**:
  - Handoff §1.2 `Book integrity is the foundation` — integrity requirements
  - Handoff §2 `/book` directory — file names and responsibilities
  - Handoff §4.2 `Iceberg detector` — needs traded_cum/peak_visible from lifecycle tracker
  - Handoff §4.1 `Spoof detector` — needs order_id lifecycle (add→cancel, no fills)
  - async-rithmic `depth_by_order.proto` — field definitions for update_type, exchange_order_id

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_book.py` → PASS (20+ test cases)
  - [ ] Book correctly reconstructs from sequence of ADD/MODIFY/CANCEL/TRADE events
  - [ ] Lifecycle tracker computes correct life_duration_ms and fill_ratio

  **QA Scenarios**:
  ```
  Scenario: Book reconstruction from MBO events
    Tool: Bash
    Steps:
      1. Feed 1,000 synthetic MBO events (mix of ADD, MODIFY, CANCEL, TRADE)
      2. Query book state at each price level
      3. Assert total book size matches: sum(ADD sizes) - sum(CANCEL sizes) - sum(TRADE sizes)
      4. Assert no negative sizes at any level
      5. Assert order_id lookup returns correct current state
    Expected Result: Book state consistent after all events. Zero negative sizes.
    Evidence: .sisyphus/evidence/task-10-reconstruction.txt

  Scenario: Lifecycle tracker computes spoof-relevant metrics
    Tool: Bash
    Steps:
      1. Create order lifecycle: ADD(order_id="R001", size=400, price=21550) → CANCEL(order_id="R001", time_delta=2500ms)
      2. Query lifecycle tracker for R001
      3. Assert: life_duration_ms=2500, was_filled=False, fill_ratio=0.0, original_size=400
    Expected Result: Lifecycle correctly tracked for spoof detection
    Evidence: .sisyphus/evidence/task-10-lifecycle.txt
  ```

  **Commit**: YES
  - Message: `feat(cross_market): MBO order book reconstructor and lifecycle tracker`
  - Files: `cross_market/book/*.py`, `cross_market/tests/test_book.py`

- [ ] 11. Book Integrity Validator

  **What to do**:
  - `cross_market/book/book_integrity.py`: Continuous integrity validation per handoff §1.2:
    - Sequence gap detection (missing sequence_number)
    - Crossed book detection (best_bid >= best_ask)
    - Negative size detection (any level < 0)
    - Stale level detection (no updates for >30s during active session)
    - Inconsistent cancel detection (CANCEL for unknown order_id)
    - Duplicate order ID detection (ADD for existing order_id)
    - Reconnect snapshot rebuild (request fresh snapshot after gap)
  - Emit integrity alerts with severity (WARN, ERROR, CRITICAL).
  - On CRITICAL: pause all downstream consumers until resolved.
  - Write tests for each integrity check.

  **◆ HARD GATE — This task is a verification checkpoint:**
  - After implementation, run Task 13's replay engine through the book reconstructor (Task 10)
  - Task 11's validator MUST report zero CRITICAL or ERROR alerts on a full NQ replay session
  - If replay reveals integrity violations → fix book reconstructor (Task 10) before ANY Wave 3 detector starts
  - This gate ensures detectors operate on trustworthy book state — without it, detector outputs are meaningless
  - Evidence of gate passage: `.sisyphus/evidence/task-11-gate-pass.txt` containing: session replayed, event count, alert summary (zero CRITICAL/ERROR)

  **Must NOT do**: Do not silently ignore integrity violations — always log and alert. Do not allow Wave 3 to proceed if this gate fails.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 12, 13, 14 — after Task 10)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 15-20 (detectors require validated book)
  - **Blocked By**: Task 10

  **References**:
  - Handoff §1.2 `Book integrity is the foundation` — complete list of integrity checks
  - Handoff §1.9 — raw event persistence before transformation

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_integrity.py` → PASS
  - [ ] Each of 7 integrity checks has dedicated test

  **QA Scenarios**:
  ```
  Scenario: Crossed book detected and flagged
    Tool: Bash
    Steps:
      1. Build book with best_bid=21550.25, best_ask=21550.00 (crossed)
      2. Assert integrity validator emits CRITICAL alert
      3. Assert downstream consumers paused
    Expected Result: Crossed book immediately detected, CRITICAL alert
    Evidence: .sisyphus/evidence/task-11-crossed.txt

  Scenario: Sequence gap detected
    Tool: Bash
    Steps:
      1. Feed events with sequence: 100, 101, 103 (gap at 102)
      2. Assert WARN alert with gap details
    Expected Result: Gap detected, alert includes missing sequence 102
    Evidence: .sisyphus/evidence/task-11-seqgap.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `cross_market/book/book_integrity.py`, `cross_market/tests/test_integrity.py`

- [ ] 12. Trade Classifier + Aggressor Detector + Delta Engine

  **What to do**:
  - `cross_market/tape/trade_classifier.py`: Classify each trade as buyer-aggressive or seller-aggressive. Use: (1) trade price vs best bid/ask at time of trade, (2) Lee-Ready tick rule as fallback. Output: aggressor_side for each trade.
  - `cross_market/tape/aggressor_detector.py`: Track aggression intensity: rolling window aggressor ratio, burst detection (>N trades same direction in <M ms), large-trade detection (>threshold size).
  - `cross_market/tape/delta_engine.py`: Compute cumulative delta (buy volume - sell volume), rolling delta windows (1s, 5s, 30s, 1m, 5m), delta divergence (price up + delta down or vice versa), per-level delta.
  - `cross_market/tape/sweep_detector.py`: Core sweep detection engine — identifies raw multi-level aggressive execution events (rapid sequential prints through 3+ price levels in one direction). This is the canonical sweep implementation. Task 18's `sweep_features.py` is a feature extractor that wraps this detector's outputs into numeric features for the classifier pipeline — it does NOT duplicate detection logic.
  - Write tests with known aggressor sequences.

  **Must NOT do**: Do not use deep6v2 tick_classifier — build fresh with MBO-aware classification.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 11, 13, 14)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 17, 18, 20
  - **Blocked By**: Tasks 4, 9

  **References**:
  - Handoff §4.6 `Sweep detector` — evidence requirements
  - Handoff §2 `/tape` — file names
  - `nq_atlas/flow.py` — Lee-Ready classification reference (don't import, rebuild)

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_tape.py` → PASS
  - [ ] Delta engine produces correct cumulative delta for known sequence

  **QA Scenarios**:
  ```
  Scenario: Trade classification accuracy on known sequence
    Tool: Bash
    Steps:
      1. Create 100 trades: 60 at ask (buyer), 40 at bid (seller)
      2. Run trade_classifier
      3. Assert 60 classified as buy, 40 as sell
      4. Assert cumulative delta = +20 (normalized)
    Expected Result: 100% classification accuracy on unambiguous trades
    Evidence: .sisyphus/evidence/task-12-classification.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `cross_market/tape/*.py`, `cross_market/tests/test_tape.py`

- [ ] 13. Databento MBO Replay Engine

  **What to do**:
  - `cross_market/replay/mbo_replay_engine.py`: Replay historical Databento MBO data through the same pipeline as live data. Load from Databento `.dbn` files or API. Convert Databento MBOMsg (order_id, action A/C/M/T/F/R, price, size, side B/A/N) to cross_market MBOEvent format. Support time-scaled replay (1x, 2x, 10x, max speed). Callback interface identical to live connector.
  - Reference existing `deep6/backtest/mbo_adapter.py` as starting point for Databento→MBOEvent conversion.
  - **Note**: `cross_market/replay/synchronized_replay.py` is owned by Task 38. This task (T13) does NOT create it — T38 builds the full synchronized replay.
  - Write test: replay 5 minutes of sample data, verify book reconstruction matches.

  **Must NOT do**: Do not build options/GEX replay yet — that's Task 38. Focus on MBO only.

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 10, 11, 12, 14)
  - **Parallel Group**: Wave 2
  - **Blocks**: Tasks 15-20 (HARD GATE — replay parity must pass), 34, 38
  - **Blocked By**: Tasks 4, 5, 7

  **References**:
  - `deep6/backtest/mbo_adapter.py` — existing Databento MBO → callback conversion (reference/starting point)
  - Databento MBO schema: https://databento.com/docs/schemas-and-data-formats/mbo
  - Databento Python SDK: https://github.com/databento/databento-python

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_replay.py` → PASS
  - [ ] Can replay 5 minutes of Databento NQ MBO data without errors

  **QA Scenarios**:
  ```
  Scenario: MBO replay produces identical book state as sequential processing
    Tool: Bash
    Steps:
      1. Download 5 minutes of NQ MBO data from Databento
      2. Replay through mbo_replay_engine at max speed
      3. At end: query book state
      4. Process same data sequentially through book_reconstructor
      5. Assert book states match
    Expected Result: Replay and sequential processing produce identical book state
    Evidence: .sisyphus/evidence/task-13-replay.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `cross_market/replay/mbo_replay_engine.py`, `cross_market/tests/test_replay.py`

- [ ] 14. Queue Position Tracker

  **What to do**:
  - `cross_market/book/queue_tracker.py`: Track queue position per price level using `depth_order_priority` from DepthByOrder. For each resting order: estimate queue position (how many contracts ahead in the queue). Track queue depletion rate (how fast the queue is being consumed by trades). This enables: time-to-fill estimation, queue jump detection, priority-based iceberg detection.
  - Write tests with known queue sequences.

  **Must NOT do**: Do not estimate queue position without `depth_order_priority` — if field is not available, log warning and skip.

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 11, 12, 13)
  - **Parallel Group**: Wave 2
  - **Blocks**: Task 15
  - **Blocked By**: Task 10

  **References**:
  - Handoff §2 `/book/queue_tracker.py`
  - async-rithmic `depth_by_order.proto` — `depth_order_priority` field

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_queue.py` → PASS
  - [ ] Queue position updates correctly on ADD/CANCEL/TRADE events

  **QA Scenarios**:
  ```
  Scenario: Queue position tracks correctly through lifecycle
    Tool: Bash
    Steps:
      1. ADD 5 orders at price 21550.00 with priorities 1,2,3,4,5
      2. TRADE at 21550.00 (fills priority 1)
      3. Assert remaining queue: priorities 2,3,4,5
      4. CANCEL priority 3
      5. Assert remaining: priorities 2,4,5
    Expected Result: Queue correctly reflects fills and cancels
    Evidence: .sisyphus/evidence/task-14-queue.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `cross_market/book/queue_tracker.py`, `cross_market/tests/test_queue.py`

- [ ] 15. Spoof Detector (Order Lifecycle-Based)

  **What to do**:
  - `cross_market/features/spoof_features.py` (spoof detection only — layering goes in Task 19's `layering_features.py`; spoof rules go in Task 29's `expert_dom_rules.py`): Detect spoofing per handoff §4.1. Required evidence chain: (a) large order (>5× surrounding level avg), (b) specific order_id tracked via lifecycle_tracker, (c) short life (<5s), (d) cancelled before meaningful trade at that price during its life, (e) near enough to influence behavior (within 5 ticks of touch), (f) book imbalance changed while order existed, (g) optional opposite-side aggression after pull. Output `SpoofResult` with all fields from handoff §4.1: pattern, side, price, order_id, life_ms, size, executed_qty, distance_to_touch_ticks, spoof_probability, reason_codes[].
  - **File ownership**: This task owns ONLY `cross_market/features/spoof_features.py`. The rule-layer file `cross_market/rules/expert_dom_rules.py` is owned by Task 29.
  - Write tests using `sample_spoof_sequence()` fixture and Exemplar 1 from dom_expert_skills.md.

  **Must NOT do**: Do not call spoof on routine cancels after fills. Do not call spoof on small orders.

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Parallel with Tasks 16-20 | Wave 3 | **Blocks**: Task 28 | **Blocked By**: Tasks 10, 11 (HARD GATE), 13 (replay parity), 14

  **References**:
  - Handoff §4.1 `Spoof detector` — complete evidence chain and output schema
  - `dom_expert_skills.md` §1.4 `Spoof detection` — pass/fail criteria for spoof calls
  - `dom_expert_skills.md` EXEMPLAR 1 — clean spoof with gold assessment (order R8841290, 412 lots, 2840ms)
  - `cross_market/tests/fixtures/exemplars/exemplar_1_spoof.json` — test fixture

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_spoof.py` → PASS
  - [ ] Correctly identifies Exemplar 1 spoof pattern (R8841290)
  - [ ] Does NOT flag routine cancel-after-fill as spoof

  **QA Scenarios**:
  ```
  Scenario: Detect Exemplar 1 spoof (R8841290, 412 lots, 2840ms life)
    Tool: Bash
    Steps:
      1. Feed Exemplar 1 order sequence through detector
      2. Assert SpoofResult emitted with: order_id="R8841290", life_ms=2840, size=412, spoof_probability>0.7
      3. Assert reason_codes includes "short_life", "no_fill", "oversized"
    Expected Result: Spoof detected with high confidence
    Evidence: .sisyphus/evidence/task-15-spoof.txt

  Scenario: No false positive on legitimate cancel
    Tool: Bash
    Steps:
      1. Create order: ADD(size=50) → TRADE(size=30) → CANCEL(remaining 20)
      2. Assert NO SpoofResult emitted (order was filled before cancel)
    Expected Result: No spoof flag on cancel-after-partial-fill
    Evidence: .sisyphus/evidence/task-15-no-false-positive.txt
  ```

  **Commit**: YES (groups with Wave 3) | Files: `cross_market/features/spoof_features.py`, `cross_market/tests/test_spoof.py`

- [ ] 16. Iceberg Detector (Refresh Tracking via Order IDs)

  **What to do**:
  - `cross_market/features/iceberg_features.py`: Detect icebergs per handoff §4.2. Required evidence: (a) traded_cum at level meaningfully exceeds peak_visible (≥3×), (b) refresh ADD events at same price after fills, (c) level holds despite aggression, (d) order book replenishment persists. Track per-price: traded_cum, peak_visible_size, refresh_count, refresh_order_ids. Output `IcebergResult` with ratio, refreshes, traded_cum, peak_visible.
  - Use Exemplar 2 from dom_expert_skills.md as test case (ratio 20.58×, 9 refreshes).

  **Must NOT do**: Do not call iceberg on traded volume alone without refresh evidence (per §1.3 failure mode).

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Parallel with Tasks 15, 17-20 | Wave 3 | **Blocks**: Task 28 | **Blocked By**: Tasks 10, 11 (HARD GATE), 13 (replay parity)

  **References**:
  - Handoff §4.2 `Iceberg detector` — evidence requirements
  - `dom_expert_skills.md` §1.3 `Iceberg detection` — pass/fail criteria
  - `dom_expert_skills.md` EXEMPLAR 2 — iceberg at 21555.25 (ratio 20.58×, 9 refreshes, gold assessment)

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_iceberg.py` → PASS
  - [ ] Correctly identifies Exemplar 2 iceberg (ratio 20.58×, 9 refreshes)

  **QA Scenarios**:
  ```
  Scenario: Detect Exemplar 2 iceberg (21555.25, ratio 20.58×)
    Tool: Bash
    Steps:
      1. Feed Exemplar 2 sequence: 247 contracts traded, peak visible 12, 9 refreshes
      2. Assert IcebergResult: ratio≈20.58, refreshes=9, traded_cum=247
    Expected Result: Iceberg detected with high confidence
    Evidence: .sisyphus/evidence/task-16-iceberg.txt
  ```

  **Commit**: YES (groups with Wave 3) | Files: `cross_market/features/iceberg_features.py`, `cross_market/tests/test_iceberg.py`

- [ ] 17. Absorption Detector (MBO-Native)

  **What to do**:
  - `cross_market/features/absorption_features.py`: Detect absorption per handoff §4.3. Bid absorption: aggressive sellers hit bid, price doesn't break lower, bid remains/reloads, seller aggression slows. Ask absorption: mirror. Track per-level: aggressive_volume_into_level, level_hold_duration, reload_count, aggressor_exhaustion_rate. Output `AbsorptionResult`.
  - Use Exemplar 4 from dom_expert_skills.md (184 contracts, 22 trades, level holds).

  **Must NOT do**: Do not call absorption when the level cleared (it broke, not absorbed).

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Parallel with Tasks 15-16, 18-20 | Wave 3 | **Blocks**: Task 25, 28 | **Blocked By**: Tasks 10, 11 (HARD GATE), 12, 13 (replay parity)

  **References**:
  - Handoff §4.3 `Absorption detector` — evidence requirements
  - `dom_expert_skills.md` §1.5 `Absorption recognition` — pass/fail criteria
  - `dom_expert_skills.md` EXEMPLAR 4 — absorption at 21562.50 (184 contracts, level holds)

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_absorption.py` → PASS
  - [ ] Correctly identifies Exemplar 4 absorption pattern

  **QA Scenarios**:
  ```
  Scenario: Detect absorption (184 contracts, level holds)
    Tool: Bash
    Steps:
      1. Feed Exemplar 4: 184 sell-aggressive contracts into 21562.50, level still at 88 lots
      2. Assert AbsorptionResult with side=bid, size_traded=184, level_held=True
    Expected Result: Absorption detected
    Evidence: .sisyphus/evidence/task-17-absorption.txt
  ```

  **Commit**: YES (groups with Wave 3) | Files: `cross_market/features/absorption_features.py`, `cross_market/tests/test_absorption.py`

- [ ] 18. Sweep Detector

  **What to do**:
  - `cross_market/features/sweep_features.py` (feature extractor — wraps Task 12's `tape/sweep_detector.py` outputs into numeric features for classifiers, does NOT duplicate detection logic): Extract sweep features per handoff §4.6. Rapid sequential prints through 3+ price levels in one direction. Track: levels_taken, total_volume, time_span_ms, target_reference (prior H/L, round number). Output `SweepResult`.

  **Must NOT do**: Do not call sweep on a single aggressive trade (per §1.7 failure mode).

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Parallel with Wave 3 | **Blocks**: Task 28 | **Blocked By**: Tasks 11 (HARD GATE), 12, 13 (replay parity)

  **References**: Handoff §4.6, `dom_expert_skills.md` §1.7

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_sweep.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Detect 5-level sweep with target reference
    Tool: Bash
    Steps:
      1. Feed rapid buy trades through 5 consecutive ask levels in 500ms
      2. Assert SweepResult: levels_taken=5, direction=up, total_volume>0, time_span_ms<1000
    Expected Result: Sweep detected with correct metrics
    Evidence: .sisyphus/evidence/task-18-sweep.txt

  Scenario: No false positive on single aggressive trade
    Tool: Bash
    Steps:
      1. Feed single buy trade at ask (1 level only, size=50)
      2. Assert NO SweepResult emitted (per §1.7 — single trade is not a sweep)
    Expected Result: No sweep flag on single trade
    Evidence: .sisyphus/evidence/task-18-no-false-positive.txt
  ```

  **Commit**: YES (groups with Wave 3) | Files: `cross_market/features/sweep_features.py`

- [ ] 19. Layering Detector

  **What to do**:
  - `cross_market/features/layering_features.py` (separate file from spoof — avoids parallel write collision): Detect layering per handoff §4.5. At least 3 contiguous levels with stacked oversized size (>5× avg), comparable sizes, few orders (suggesting coordinated participant), dissolves as price approaches. Output `LayeringResult`.
  - Use Exemplar 3 from dom_expert_skills.md (3 levels at 245/280/310, 3-4 orders each).

  **Must NOT do**: Do not call layering on a single large level (that's a wall, per §1.6 failure mode).

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Parallel with Wave 3 | **Blocks**: Task 28 | **Blocked By**: Tasks 10, 11 (HARD GATE), 13 (replay parity)

  **References**: Handoff §4.5, `dom_expert_skills.md` §1.6, EXEMPLAR 3

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_layering.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Detect Exemplar 3 layering (3 levels, 245/280/310)
    Tool: Bash
    Steps:
      1. Feed Exemplar 3 book state
      2. Assert LayeringResult with n_levels=3, sizes=[245,280,310], side=bid
    Expected Result: Layering detected with medium confidence
    Evidence: .sisyphus/evidence/task-19-layering.txt
  ```

  **Commit**: YES (groups with Wave 3) | Files: `cross_market/features/layering_features.py`

- [ ] 20. Liquidity Vacuum Detector

  **What to do**:
  - `cross_market/features/vacuum_features.py` (separate file — sweep is in Task 18's sweep_features.py): Detect liquidity vacuum per handoff §4.4. Inputs: near-touch depth collapse, multi-level cancel wave, spread instability, fast aggressive flow, price acceleration, low resting liquidity ahead. Output `VacuumResult` with: direction, depth_collapse_pct, spread_expansion_ticks, cancel_wave_count, vacuum_probability.

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Parallel with Wave 3 | **Blocks**: Task 28 | **Blocked By**: Tasks 10, 11 (HARD GATE), 12, 13 (replay parity)

  **References**: Handoff §4.4 `Liquidity vacuum detector`

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_vacuum.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Detect vacuum when near-touch depth collapses
    Tool: Bash
    Steps:
      1. Build book with 200 lots at touch, then cancel 180 lots in 500ms
      2. Assert VacuumResult with depth_collapse_pct>0.9, direction based on which side collapsed
    Expected Result: Vacuum detected with high probability
    Evidence: .sisyphus/evidence/task-20-vacuum.txt
  ```

  **Commit**: YES (groups with Wave 3)

- [ ] 21. Options Chain Engine (Massive.com)

  **What to do**:
  - `cross_market/options/options_chain_engine.py`: Fetch full QQQ options chain from Massive.com/Polygon API. Parse into OptionsEvent objects. Compute: bid/ask spread, mid price, IV, Greeks (delta, gamma, theta, vega). Group by expiry and strike. Handle pagination (250 contracts/page).
  - `cross_market/options/options_quote_engine.py`: Real-time quote updates via WebSocket (Massive WS /options/Q).
  - `cross_market/options/cross_asset_mapper.py`: Map QQQ/NDX/SPX option levels to NQ futures price. Use spot ratio (NQ/QQQ) with configurable offset.
  - Reuse `nq_atlas/massive_client.py` for API communication, but build new chain parsing logic.

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: [`flashalpha-options`]
  **Parallelization**: Parallel with Tasks 23, 24 | Wave 4 | **Blocks**: Tasks 22, 26 | **Blocked By**: Tasks 2, 4

  **References**:
  - Handoff §5 `Options/GEX Engine` — required features
  - `nq_atlas/massive_client.py` — existing Polygon client to reuse for API communication
  - `nq_atlas/nq_mapper.py` — existing QQQ→NQ mapper to reuse
  - Massive.com API: https://massive.com/docs/rest/options/snapshots/option-chain-snapshot

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_options.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Fetch and parse QQQ options chain
    Tool: Bash
    Steps:
      1. Fetch QQQ chain from Massive.com API
      2. Assert ≥100 OptionsEvent objects returned
      3. Assert each has: strike, expiry, type(call|put), greeks.delta, iv
      4. Map 3 strike prices to NQ equivalent via cross_asset_mapper
    Expected Result: Chain fetched, parsed, mapped to NQ prices
    Evidence: .sisyphus/evidence/task-21-options.txt

  Scenario: Graceful handling of API failure
    Tool: Bash
    Steps:
      1. Set Massive.com API key to invalid value
      2. Attempt chain fetch
      3. Assert: raises ProviderError (not unhandled exception), logs warning, returns empty chain
    Expected Result: Graceful error with clear message, no crash
    Evidence: .sisyphus/evidence/task-21-api-error.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [ ] 22. Options Flow Engine + Dealer Pressure

  **What to do**:
  - `cross_market/options/options_flow_engine.py`: Real-time options flow analysis. Track: signed premium (call vs put, buy vs sell), sweep intensity, block trades, unusual OI changes, 0DTE concentration.
  - `cross_market/options/dealer_pressure_engine.py`: Compute dealer hedge pressure from GEX + flow. Dealer shares to trade per ±1% move. Net dealer delta direction.
  - `cross_market/options/strike_mapper.py`: Map individual strike activity to NQ price levels for level registry.

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: [`flashalpha-options`]
  **Parallelization**: Parallel with Wave 4 | **Blocks**: Tasks 27, 28 | **Blocked By**: Task 21

  **References**: Handoff §5.1 required features, `nq_atlas/flow.py` — signed premium analytics reference

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_flow.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Signed premium flow classification
    Tool: Bash
    Steps:
      1. Feed 50 synthetic options trades (30 call buys at ask, 20 put buys at ask)
      2. Run flow_engine.compute_flow()
      3. Assert net_premium_direction="bullish", call_premium > put_premium
    Expected Result: Flow correctly classified as bullish
    Evidence: .sisyphus/evidence/task-22-flow.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [ ] 23. GEX Engine (FlashAlpha + Regime Classification)

  **What to do**:
  - `cross_market/options/gex_engine.py`: Compute/fetch GEX analytics. Integrate FlashAlpha client (reuse `nq_atlas/flashalpha_client.py`). Features per handoff §5.1: net GEX, distance to zero gamma, distance to call/put wall, peak gamma proximity, GEX regime (positive/negative/transition), dealer pressure score, charm/vanna exposure. Regime classification per handoff §5.2: positive gamma (pinning), negative gamma (expansion), zero gamma (transition).

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: [`flashalpha-options`]
  **Parallelization**: Parallel with Wave 4 | **Blocks**: Tasks 26, 27 | **Blocked By**: Tasks 2, 4

  **References**:
  - Handoff §5 `Options/GEX Engine`
  - `nq_atlas/flashalpha_client.py` — FlashAlpha client to reuse
  - `nq_atlas/gex.py` — GEX computation reference
  - `.claude/skills/flashalpha-options/` — complete FlashAlpha API reference

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_gex.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: GEX regime classification
    Tool: Bash
    Steps:
      1. Fetch FlashAlpha exposure_summary for QQQ
      2. Assert GEX engine outputs: regime (positive|negative|transition), gamma_flip price, call_wall, put_wall
      3. Verify distance_to_flip computed correctly from current NQ price
    Expected Result: Regime correctly classified with all level distances
    Evidence: .sisyphus/evidence/task-23-gex.txt
  ```

  **Commit**: YES (groups with Wave 4)

- ~~24. NQStats Engine~~ — **REMOVED** (no RoadToTrading/NQStats subscription available)

- [ ] 25. MADLevels Engine (Custom + NT8/Telegram Import)

  **What to do**:
  - `cross_market/levels/madlevels_engine.py`: Custom MADLevel detection per handoff §7. Create MADLevel when DOM shows: aggressive traders failing, repeated rejection, absorption, delta divergence, hidden liquidity holding, failed continuation, strong reaction after test. Uses outputs from Tasks 15-20 (spoof, iceberg, absorption, sweep detectors). Output MADLevel objects per §7.2.
  - `cross_market/connectors/madlevels_connector.py`: Import external MADLevels from: (a) NT8 CSV/JSON export file (watch directory for new files), (b) Telegram webhook listener (parse level messages), (c) Manual config file.
  - **Note**: Level freshness scoring (`level_freshness.py`) is owned by Task 26, not this task.

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Depends on Wave 3 detectors | Wave 4 | **Blocks**: Tasks 26, 27 | **Blocked By**: Tasks 15-20 (all Wave 3 detectors)

  **References**: Handoff §7 `MADLevels-Style Engine`, §7.2 MADLevel object schema

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_madlevels.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Custom MADLevel creation from detector outputs
    Tool: Bash
    Steps:
      1. Feed absorption signal at 21550.00 (184 contracts, level held)
      2. Assert MADLevel created: level_price=21550.00, level_type="bid_absorption", status="fresh"
      3. Feed second touch → assert touch_count=2, status transitions to "active"
    Expected Result: MADLevel lifecycle managed correctly
    Evidence: .sisyphus/evidence/task-25-madlevel.txt

  Scenario: MADLevel import from config file
    Tool: Bash
    Steps:
      1. Create CSV: "price,type,source\n21600,ask_absorption,nt8"
      2. Import via madlevels_connector
      3. Assert MADLevel registered with source="external"
    Expected Result: External levels imported into registry
    Evidence: .sisyphus/evidence/task-25-import.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [ ] 26. Level Registry + Freshness Scoring

  **What to do**:
  - `cross_market/levels/level_registry.py`: Unified registry for ALL price levels from ALL sources per handoff §1.9. Each level graded by confluence. Sources: MADLevel absorption/failure, GEX call/put wall/zero gamma, prior RTH H/L, VWAP, volume profile HVN/LVN, live MBO iceberg, live MBO absorption, options flow alignment. (NQStats target/reference removed — no subscription) Deduplication: merge levels within 2 ticks. Dynamic: levels added/removed/updated in real-time.
  - `cross_market/levels/level_freshness.py`: Freshness scoring — decay over time, boost on retest, source-specific TTL.
  - **File ownership**: This task owns `level_registry.py` and `level_freshness.py` ONLY. The confluence scoring file `level_confluence.py` is owned by Task 27.

  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: After Tasks 21-25 | Wave 4 | **Blocks**: Task 27 | **Blocked By**: Tasks 21-25

  **References**: Handoff §1.9 `Level hierarchy`, §8 `Confluence Scoring` — complete weight table

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_levels.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Level deduplication within 2 ticks
    Tool: Bash
    Steps:
      1. Register level at 21550.00 from GEX, 21550.25 from MADLevels (1 tick apart)
      2. Assert merged into single level with source_types=["gex","madlevels"]
    Expected Result: Levels within 2 ticks merged, sources combined
    Evidence: .sisyphus/evidence/task-26-dedup.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [ ] 27. Confluence Scoring Engine

  **What to do**:
  - `cross_market/levels/level_confluence.py` (scoring logic): Implement confluence scoring from handoff §8. Weights: +25 MADLevel, +20 GEX wall/gamma, +20 DOM absorption, +15 iceberg, +15 options flow, +5 prior session levels. Penalties: -25 spoof risk, -25 DOM rejects, -20 options conflict, -15 noise regime. Grades: A+(85-100), A(70-84), B(55-69), C(40-54), Ignore(<40). (NQStats +20 weight removed — no subscription; redistributed to MADLevel +5 and DOM absorption +5)
  - `cross_market/rules/cross_market_rules.py`: Rules for cross-market confirmation/conflict. E.g., GEX positive gamma + DOM absorption at level = higher confidence. GEX negative gamma + DOM layering = lower confidence (expect breakout).

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: [`flashalpha-options`]
  **Parallelization**: After Task 26 | Wave 4 | **Blocks**: Tasks 28-30 | **Blocked By**: Task 26

  **References**: Handoff §8 `Confluence Scoring` — full weight table and grade thresholds

  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_confluence.py` → PASS

  **QA Scenarios**:
  ```
  Scenario: Confluence scoring matches updated weights
    Tool: Bash
    Steps:
      1. Register level with: active MADLevel (+25), GEX call wall nearby (+20), DOM absorption (+20) = 65
      2. Assert confluence_score=65, grade="B"
      3. Add spoof risk (-25) → score=40, grade="C"
    Expected Result: Scores match handoff weight table exactly
    Evidence: .sisyphus/evidence/task-27-confluence.txt
  ```

  **Commit**: YES (groups with Wave 4)

- [ ] 28. Feature Extraction (DOM + Cross-Market)

  **What to do**: Create `cross_market/features/dom_features.py` (OFI at depth 1/5/10, spread, book depth ratio, trade rate, delta, spoof/iceberg counts), `options_features.py` (IV rank, skew, OI concentration, 0DTE share, sweep intensity), `gex_features.py` (distance_to_flip/walls, regime_sign, dealer_pressure, vex/chex direction), `madlevels_features.py` (nearest_level_distance/type/score), `cross_market_features.py` (confluence_score_at_price, n_sources_agree, regime×dom interactions). All serializable to numpy arrays. (`nqstats_features.py` removed — no NQStats subscription)
  **Must NOT do**: Do not import deep6v2 signal features.
  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 29, 30, 34 | **Blocked By**: 15-20, 22-27
  **References**: Handoff §2 `/features` — file names, §5.1 required GEX features
  **Acceptance Criteria**: [ ] `pytest cross_market/tests/test_features.py` → PASS
  **QA Scenarios**:
  ```
  Scenario: Features produce valid numpy arrays
    Tool: Bash
    Steps:
      1. Build state: book 10 levels, 2 detectors active, GEX="positive"
      2. Run all feature extractors
      3. Assert no NaN values, correct dimensions
    Expected Result: All feature vectors valid
    Evidence: .sisyphus/evidence/task-28-features.txt
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 29. Expert Rules + No-Trade Rules

  **What to do**: `cross_market/rules/expert_dom_rules.py`, `options_rules.py`, `madlevels_rules.py`, `trap_rules.py`. (`nqstats_rules.py` removed — no NQStats subscription) CRITICAL: `no_trade_rules.py` per §1.5 — rules for: no_edge, too_noisy, near_news, spoof_risk_high, options_conflict, gex_pin, dom_not_confirming, level_not_tested, low_confidence. Each outputs reason codes.
  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 30 | **Blocked By**: 28
  **References**: Handoff §1.5, §2 `/rules`
  **Acceptance Criteria**: [ ] No-trade rules fire on Exemplar 5 (balanced book) and Exemplar 6 (macro window)
  **QA Scenarios**:
  ```
  Scenario: No-trade fires on macro window (Exemplar 6)
    Tool: Bash
    Steps:
      1. Provide context: macro_release="CPI", seconds_to_release=12
      2. Assert no_trade_rules returns: do_not_trade=True, reason="near_news"
    Expected Result: No-trade correctly blocks near macro
    Evidence: .sisyphus/evidence/task-29-notrade.txt
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 30. Snapshot Builder + Prompt/Skills Documents

  **What to do**: `cross_market/llm_expert/snapshot_builder.py` — assemble JSON for LLM input per §9.2 (DOM snapshot, lifecycle evidence, detector outputs, MADLevels, GEX, confluence scores, macro risk, exemplars). Author `cross_market/llm_expert/dom_expert_prompt.md` based on §9. Snapshot must be <4K tokens.
  - **File ownership**: `dom_expert_skills.md` was already copied by Task 3 to `cross_market/llm_expert/`. This task does NOT re-copy it — it references the copy in place. This task owns `snapshot_builder.py` and `dom_expert_prompt.md` ONLY.
  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 31, 32 | **Blocked By**: 28, 29
  **References**: Handoff §9.2, `C:\Users\Tea\Downloads\dom_expert_skills.md` §1
  **Acceptance Criteria**: [ ] Snapshot <4K tokens, contains all 12 input categories
  **QA Scenarios**:
  ```
  Scenario: Snapshot includes all required categories
    Tool: Bash
    Steps:
      1. Build snapshot from Exemplar 1 data
      2. Parse JSON, assert keys: dom_snapshot, spoof_candidates, iceberg_candidates, absorption_signals, gex_context, confluence_scores, exemplars
    Expected Result: All 12 categories present
    Evidence: .sisyphus/evidence/task-30-snapshot.txt
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 31. Exemplar Store + Retriever

  **What to do**: `cross_market/llm_expert/exemplar_retriever.py` — cosine similarity retrieval. Seed with 6 exemplars from `dom_expert_skills.md` §2. Retrieve top-3 most similar for few-shot injection. `cross_market/storage/exemplar_store.py` — add, query_similar, query_by_pattern, get_outcome_stats.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 32 | **Blocked By**: 30
  **References**: Handoff §10.1-10.2, `C:\Users\Tea\Downloads\dom_expert_skills.md` §2 exemplars
  **Acceptance Criteria**: [ ] Retriever returns top-3 with cosine similarity >0.7
  **QA Scenarios**:
  ```
  Scenario: Retrieve similar exemplars
    Tool: Bash
    Steps:
      1. Seed store with 6 exemplars
      2. Query with Exemplar 1-like features (spoof pattern)
      3. Assert top result is Exemplar 1, similarity >0.8
    Expected Result: Correct exemplar retrieved
    Evidence: .sisyphus/evidence/task-31-retrieval.txt
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 32. LLM Router + Strict JSON (Claude tool_use)

  **What to do**:
  - `cross_market/llm_expert/llm_router.py` — Claude Haiku via Anthropic SDK, tool_use with forced tool_choice for strict JSON per §9.3. Timeout 450ms, fallback to rule-based. Temperature 0.
  - `cross_market/llm_expert/validation_harness.py` — validate against all 13 competencies from `dom_expert_skills.md` §1 using the competency matrix below.

  **13-Competency LLM QA Matrix** (each competency MUST pass on relevant exemplars):

  | # | Competency | Pass Criterion | Failure Mode (must NOT exhibit) | Test Exemplars |
  |---|-----------|---------------|-------------------------------|----------------|
  | 1.1 | MBO vs MBP discipline | References specific order IDs and lifecycle, not just level totals | Calling "iceberg" on level total alone, "spoof" on level disappearance | E1, E2 |
  | 1.2 | Intentions vs transactions | Qualifies every size assessment by whether tested (fills printed, aggression absorbed) | Saying "strong support" without qualification | E1, E3, E4 |
  | 1.3 | Iceberg detection | Cites both `traded_cum/peak_visible` ratio AND `refreshes` count | Calling iceberg on traded volume alone with no refresh evidence | E2 |
  | 1.4 | Spoof detection | Cites order_id, life_ms, size, and absence of fills at the order's price | Calling spoof on cancel-after-fill or small orders (<5× avg) | E1 |
  | 1.5 | Absorption recognition | Cites trades/size/aggressor-direction and notes level remained resting | Calling absorption when the level cleared | E4 |
  | 1.6 | Layering recognition | Cites ≥3 contiguous levels with comparable oversized size on same side | Calling layering on a single large level | E3 |
  | 1.7 | Sweep / liquidity-run | Cites multi-level trade sequence and identifies targeted reference | Calling sweep on a single aggressive trade | (synthetic) |
  | 1.8 | Hidden liquidity (non-iceberg) | Cites trade print with no matching ADD/CANCEL at that price | Conflating hidden with iceberg refresh | (synthetic) |
  | 1.9 | Quote stuffing / pinging | Cites event count in short window or repeated small fills | Treating as directional signals | (synthetic) |
  | 1.10 | Calibrated uncertainty | Confidence varies with evidence quality; high requires MBO evidence + context fit | Always "high" or always "medium" | E1(high), E5(low/none) |
  | 1.11 | Context modifiers | References session/killzone/macro/GEX in evidence or confidence calibration | Ignoring provided context | E6 |
  | 1.12 | Falsifiability discipline | Confirmation and invalidation criteria are concrete (prices, sizes, time windows) and opposed | Vague criteria ("if it holds") | All 6 exemplars |
  | 1.13 | No-signal discipline | No "buy", "sell", "long", "short", "enter", "exit" or directional targets | Issuing any trade recommendation | All 6 exemplars |

  **Validation harness** must:
  1. Run each exemplar through LLM router
  2. Parse JSON output
  3. Check EVERY applicable competency from the matrix above
  4. Report pass/fail per competency per exemplar
  5. Overall: 100% pass on competencies 1.10, 1.12, 1.13 (non-negotiable); ≥80% on others

  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 33, 37 | **Blocked By**: 30, 31

  **References**:
  - Handoff §9 `LLM Expert Layer` — prompt structure, JSON schema, tool_use
  - `cross_market/llm_expert/dom_expert_skills.md` §1 — all 13 competency definitions with pass/fail criteria (copied from source in Task 3)
  - `cross_market/llm_expert/dom_expert_skills.md` §2 — 6 exemplar snapshots + gold assessments
  - Anthropic tool_use docs: https://docs.anthropic.com/en/docs/build-with-claude/tool-use

  **Acceptance Criteria**:
  - [ ] Valid JSON on 100% of calls (6/6 exemplars)
  - [ ] Exemplar 1 → primary_pattern="spoof", confidence="high"
  - [ ] Exemplar 2 → primary_pattern="iceberg", cites ratio + refreshes
  - [ ] Exemplar 3 → primary_pattern="layering", cites ≥3 levels
  - [ ] Exemplar 4 → primary_pattern="absorption", cites level held
  - [ ] Exemplar 5 → primary_pattern="none" (balanced book, no edge)
  - [ ] Exemplar 6 → primary_pattern="none", do_not_trade=true (macro window)
  - [ ] Competencies 1.10, 1.12, 1.13 → 100% pass rate
  - [ ] All other competencies → ≥80% pass rate
  - [ ] Validation harness report saved

  **QA Scenarios**:
  ```
  Scenario: LLM strict JSON on all 6 exemplars
    Tool: Bash
    Steps:
      1. Run: python -m cross_market.llm_expert.validation_harness --exemplars all
      2. Assert each exemplar returns valid LLMAssessment JSON
      3. Assert Exemplar 1: primary_pattern="spoof", confidence="high", order_id="R8841290" cited
      4. Assert Exemplar 2: primary_pattern="iceberg", ratio cited, refreshes cited
      5. Assert Exemplar 5: primary_pattern="none"
      6. Assert Exemplar 6: do_not_trade=true, reason includes "near_news" or "macro_window"
      7. Assert ALL outputs have non-empty confirmation_criteria + invalidation_criteria
      8. Assert NO output contains "buy"/"sell"/"long"/"short"/"enter"/"exit"
    Expected Result: 6/6 valid JSON, patterns match gold assessments, zero signal violations
    Failure Indicators: JSON parse error, wrong pattern, missing criteria, trade signal in output
    Evidence: .sisyphus/evidence/task-32-llm-exemplars.json

  Scenario: 13-competency validation matrix
    Tool: Bash
    Steps:
      1. Run: python -m cross_market.llm_expert.validation_harness --competency-matrix
      2. For each competency (1.1-1.13): check applicable exemplars
      3. Assert competency 1.10 (calibrated uncertainty): E1=high, E5=none/low → PASS
      4. Assert competency 1.12 (falsifiability): all 6 have concrete criteria → PASS
      5. Assert competency 1.13 (no-signal): all 6 have zero trade words → PASS
      6. Report: [competency_id, pass_count, total_count, pass_rate]
    Expected Result: 1.10/1.12/1.13 at 100%. Others ≥80%.
    Failure Indicators: Any non-negotiable competency <100%, others <80%
    Evidence: .sisyphus/evidence/task-32-competency-matrix.json

  Scenario: Fallback to rule-based on LLM timeout
    Tool: Bash
    Steps:
      1. Set LLM timeout to 1ms (force timeout)
      2. Send Exemplar 1 snapshot
      3. Assert fallback rule-based output returned within 500ms
      4. Assert output has primary_pattern field (may be less accurate but structurally valid)
    Expected Result: Graceful fallback, no crash, valid JSON structure
    Evidence: .sisyphus/evidence/task-32-fallback.json
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 33. Outcome Logger + Critic + Exemplar Curator

  **What to do**: `outcome_logger.py` — check every LLM call after 30s/60s per §10.3. `outcome_critic.py` — score: did confirmation trigger? Was trader_read correct? Rolling accuracy by pattern/confidence. `exemplar_curator.py` — wrong high-confidence calls → exemplar store, track failure modes per §1.10.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 5 | **Blocks**: 37 | **Blocked By**: 32
  **References**: Handoff §10.3, §1.10 failure mode library
  **Acceptance Criteria**: [ ] Outcome logged with 30s/60s data, critic scores match expected
  **QA Scenarios**:
  ```
  Scenario: Outcome scoring with known result
    Tool: Bash
    Steps:
      1. Log LLM call: primary_pattern="absorption", confirmation="level holds for 30s"
      2. Simulate 30s: level held → assert confirmed=True
      3. Assert outcome_store contains entry with confirmed=True
    Expected Result: Outcome correctly scored
    Evidence: .sisyphus/evidence/task-33-outcome.txt
  ```
  **Commit**: YES (groups with Wave 5)

- [ ] 34. Label Generator

  **What to do**: `cross_market/labels/label_generator.py` + sub-modules per §11.2: `forward_return_labels.py` (+10 before -8 ticks etc.), `sweep_labels.py`, `trap_labels.py`, `absorption_labels.py`, `gamma_reaction_labels.py`, `madlevel_reaction_labels.py`. No lookahead.
  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Wave 6 | **Blocks**: 35 | **Blocked By**: 13, 28
  **References**: Handoff §11.2 target definitions
  **Acceptance Criteria**: [ ] Labels from replay, no lookahead verified
  **QA Scenarios**:
  ```
  Scenario: Forward return labels computed without lookahead
    Tool: Bash
    Steps:
      1. Replay 10 minutes of NQ data
      2. Compute +10/-8 tick labels
      3. Assert each label computed from data AFTER the feature timestamp
    Expected Result: No lookahead leakage
    Evidence: .sisyphus/evidence/task-34-labels.txt
  ```
  **Commit**: YES (groups with Wave 6)

- [ ] 35. XGBoost/LightGBM/CatBoost Training Pipelines

  **What to do**: `train_xgboost.py`, `train_lightgbm.py`, `train_catboost.py`. 80/20 time-based split. Optuna hyperparameter tuning (50 trials). `model_registry.py` for versioning.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 6 | **Blocks**: 36 | **Blocked By**: 34
  **References**: Handoff §11
  **Acceptance Criteria**: [ ] At least one model profit_factor ≥1.3 on holdout
  **QA Scenarios**:
  ```
  Scenario: Model training with holdout evaluation
    Tool: Bash
    Steps:
      1. Train XGBoost on 80% data
      2. Evaluate on 20% holdout
      3. Assert profit_factor, win_rate, max_drawdown reported
    Expected Result: Metrics computed, model saved to registry
    Evidence: .sisyphus/evidence/task-35-training.txt
  ```
  **Commit**: YES (groups with Wave 6)

- [ ] 36. Meta-Model + Inference Engine

  **What to do**: `meta_model.py` — combine XGB/LGBM/CatBoost + LLM into per §11.3 output. `inference_engine.py` — real-time <100ms.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 6 | **Blocks**: 37 | **Blocked By**: 35
  **References**: Handoff §11.3 output schema
  **Acceptance Criteria**: [ ] Meta-model matches §11.3 schema, inference <100ms
  **QA Scenarios**:
  ```
  Scenario: Meta-model inference latency
    Tool: Bash
    Steps:
      1. Run inference on 100 feature vectors
      2. Assert p95 latency <100ms
      3. Assert output has all §11.3 fields
    Expected Result: Fast inference with correct schema
    Evidence: .sisyphus/evidence/task-36-inference.txt
  ```
  **Commit**: YES (groups with Wave 6)

- [ ] 37. Shadow Mode Runner

  **What to do**: `cross_market/replay/shadow_mode.py` — full live system without trading per Phase 5. All data sources → book → detectors → features → rules → LLM → classifier. Log every call. Score 30s/60s outcomes.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 6 | **Blocks**: 39-43 | **Blocked By**: 32, 33, 36
  **References**: Handoff Phase 5, §12 decision states
  **Acceptance Criteria**: [ ] Full session without crash, high-confidence >70% on 30s
  **QA Scenarios**:
  ```
  Scenario: Shadow mode mini-session
    Tool: Bash
    Steps:
      1. Run shadow mode for 5 minutes against replay data
      2. Assert: decisions logged, outcomes scored, no crashes
      3. Assert high-confidence calls tracked separately from low
    Expected Result: Shadow session completes, logs correct
    Evidence: .sisyphus/evidence/task-37-shadow.txt
  ```
  **Commit**: YES (groups with Wave 6)

- [ ] 38. Synchronized Cross-Market Replay

  **What to do**: `synchronized_replay.py` — replay ALL sources time-aligned per §1.7. `options_replay_engine.py`, `gex_replay_engine.py`.
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 6 | **Blocks**: 40 | **Blocked By**: 13, 28
  **References**: Handoff §1.7
  **Acceptance Criteria**: [ ] 30-min synchronized replay completes
  **QA Scenarios**:
  ```
  Scenario: Time-aligned multi-source replay
    Tool: Bash
    Steps:
      1. Replay 30 minutes: MBO + options + GEX
      2. Assert timestamps never exceed 1s drift between sources
    Expected Result: All sources time-aligned
    Evidence: .sisyphus/evidence/task-38-synced.txt
  ```
  **Commit**: YES (groups with Wave 6)

- [ ] 39. DOM + GEX + AI Decision Dashboards

  **What to do**: FastAPI endpoints: `dom_dashboard.py` (book state, detector highlights, levels), `gex_dashboard.py` (regime, walls, dealer pressure), `ai_decision_dashboard.py` (LLM history, confidence dist, outcome stats, 14 decision states per §12). SSE for real-time.
  **Recommended Agent Profile**: **Category**: `visual-engineering` | **Skills**: []
  **Parallelization**: Wave 7 | **Blocks**: F1-F4 | **Blocked By**: 37
  **QA Scenarios**:
  ```
  Scenario: Dashboard endpoints return valid JSON
    Tool: Bash (curl)
    Steps:
      1. Start FastAPI server
      2. GET /api/dom → assert JSON with book_state, active_detectors
      3. GET /api/gex → assert JSON with regime, gamma_flip, walls
      4. GET /api/decisions → assert JSON with recent LLM assessments
    Expected Result: All endpoints return valid JSON
    Evidence: .sisyphus/evidence/task-39-dashboard.txt

  Scenario: Dashboard returns 503 when data source disconnected
    Tool: Bash (curl)
    Steps:
      1. Start server with no Rithmic connection
      2. GET /api/dom → assert HTTP 503 with {"status": "unavailable", "reason": "rithmic_disconnected"}
    Expected Result: Graceful degradation, not crash
    Evidence: .sisyphus/evidence/task-39-unavailable.txt
  ```

  **Acceptance Criteria**:
  - [ ] `curl http://localhost:8000/api/dom` → 200 with valid JSON schema
  - [ ] `curl http://localhost:8000/api/gex` → 200 with regime field
  - [ ] `curl http://localhost:8000/api/decisions` → 200 with assessments array
  - [ ] SSE endpoint streams updates without disconnecting for 60s

  **Commit**: YES (groups with Wave 7)

- [ ] 40. MADLevels + Replay Dashboards

  **What to do**: `madlevels_dashboard.py`, `replay_dashboard.py` (controls, timeline, detector overlay). (`nqstats_dashboard.py` removed — no NQStats subscription)
  **Recommended Agent Profile**: **Category**: `visual-engineering` | **Skills**: []
  **Parallelization**: Wave 7 | **Blocks**: F1-F4 | **Blocked By**: 38
  **QA Scenarios**:
  ```
  Scenario: Replay dashboard with timeline
    Tool: Bash (curl)
    Steps:
      1. GET /api/replay/sessions → assert list of available sessions
      2. GET /api/replay/{session}/timeline → assert timestamps with event counts
    Expected Result: Replay API works
    Evidence: .sisyphus/evidence/task-40-replay-dash.txt
  ```

  **Acceptance Criteria**:
  - [ ] `curl http://localhost:8000/api/madlevels` → 200 with active_levels array
  - [ ] `curl http://localhost:8000/api/madlevels` → 200 with active_levels array
  - [ ] `curl http://localhost:8000/api/replay/sessions` → 200 with session list

  **Commit**: YES (groups with Wave 7)

- [ ] 41. Risk Engine + Trade Filter + Confidence Calibrator

  **What to do**: `risk_engine.py`, `regime_gater.py` (gate by GEX regime), `news_filter.py` (block ±30s of macro releases), `trade_filter.py` (aggregate no-trade rules), `confidence_calibrator.py` (rolling calibration tracking).
  **Recommended Agent Profile**: **Category**: `deep` | **Skills**: []
  **Parallelization**: Wave 7 | **Blocks**: F1-F4 | **Blocked By**: 27, 36
  **QA Scenarios**:
  ```
  Scenario: News filter blocks during CPI
    Tool: Bash
    Steps:
      1. Set macro_events=[{"type":"CPI","time":"2026-05-18T08:30:00"}]
      2. Query at 08:29:45 → assert blocked=True, reason="near_CPI"
      3. Query at 08:31:00 → assert blocked=False
    Expected Result: Blocking within ±30s window only
    Evidence: .sisyphus/evidence/task-41-newsfilter.txt
  ```

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_risk.py` → PASS
  - [ ] News filter correctly blocks within ±30s of CPI/FOMC/NFP
  - [ ] Confidence calibrator tracks rolling accuracy by pattern type

  **Commit**: YES (groups with Wave 7)

- [ ] 42. Health Monitor + Alert Engine

  **What to do**: Aggregate connection_health + book_integrity + LLM response rate + detector error rate → system status (GREEN/YELLOW/RED). Alert on: connection loss, integrity violation, LLM timeout >20%, detector silence >5min.
  **Recommended Agent Profile**: **Category**: `unspecified-high` | **Skills**: []
  **Parallelization**: Wave 7 | **Blocks**: F1-F4 | **Blocked By**: 37
  **File ownership**: This task owns `cross_market/dashboard/health_dashboard.py` (alert engine + aggregation dashboard) ONLY. The `cross_market/connectors/connection_health.py` module is owned by Task 6 — this task IMPORTS and CONSUMES it, does not create or modify it.
  **QA Scenarios**:
  ```
  Scenario: Health degrades on connection loss
    Tool: Bash
    Steps:
      1. Report Rithmic connected, FlashAlpha connected → assert GREEN
      2. Report Rithmic disconnected → assert YELLOW
      3. Report book integrity CRITICAL → assert RED
    Expected Result: Health correctly aggregates
    Evidence: .sisyphus/evidence/task-42-health.txt
  ```

  **Acceptance Criteria**:
  - [ ] `pytest cross_market/tests/test_health.py` → PASS
  - [ ] Health monitor aggregates all source statuses into GREEN/YELLOW/RED
  - [ ] Alert fires within 5s of connection loss detection

  **Commit**: YES (groups with Wave 7)

- [ ] 43. Production Entry Point + README

  **What to do**: `cross_market/main.py` — CLI: `live`, `shadow`, `replay`, `train`, `dashboard`. Graceful shutdown. `cross_market/README.md` — setup, config, running modes.
  **Recommended Agent Profile**: **Category**: `quick` | **Skills**: []
  **Parallelization**: Wave 7 | **Blocks**: F1-F4 | **Blocked By**: 37
  **QA Scenarios**:
  ```
  Scenario: CLI help output
    Tool: Bash
    Steps:
      1. Run: python -m cross_market --help
      2. Assert output lists modes: live, shadow, replay, train, dashboard
    Expected Result: CLI works with all modes
    Evidence: .sisyphus/evidence/task-43-cli.txt
  ```

  **Acceptance Criteria**:
  - [ ] `python -m cross_market --help` → lists all 5 modes
  - [ ] `cross_market/README.md` exists with setup, config, and running instructions
  - [ ] Graceful shutdown on SIGINT (KeyboardInterrupt) without orphan processes

  **Commit**: YES (groups with Wave 7)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan. Verify profitability targets are met on replay data.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | Profitability [PASS/FAIL] | VERDICT: APPROVE/REJECT`

  **QA Scenarios**:
  ```
  Scenario: Must Have compliance
    Tool: Bash
    Steps:
      1. Read plan "Must Have" list (10 items)
      2. For each: grep cross_market/ for implementation evidence
      3. Run: pytest cross_market/tests/ -v → assert all pass
      4. Check .sisyphus/evidence/ → assert ≥60 evidence files exist (each task has 1-3 scenarios)
    Expected Result: All Must Have items verified with code evidence
    Evidence: .sisyphus/evidence/F1-compliance.txt

  Scenario: Must NOT Have enforcement (all 7 guardrails)
    Tool: Bash
    Steps:
      1. Run: grep -r "from deep6v2.signals" cross_market/ → assert zero matches (no signal reuse)
      2. Run: grep -r "from deep6v2.scoring" cross_market/ → assert zero matches (no scoring reuse)
      3. Run: grep -rn "buy\|sell\|enter\|exit" cross_market/llm_expert/llm_router.py → assert zero trade commands (WATCH only)
      4. Run: grep -rn "fine_tun\|finetun\|FineTun" cross_market/ → assert zero matches (no LLM fine-tuning)
      5. Run: grep -rn "datetime.now()" cross_market/ --include="*.py" | grep -v tests/ → assert zero matches (no lookahead via wall-clock in live mode; all times via unified clock)
      6. Verify cross_market/config/settings.yaml contains ALL detector thresholds — grep -c "threshold\|_ms\|_ratio\|_min\|_max" cross_market/config/settings.yaml → assert ≥15 configurable params (no hardcoded thresholds)
      7. Verify MBP fallback marking: grep -rn "mbp_fallback\|confidence_degraded\|data_quality" cross_market/book/ → assert degradation marking exists if MBP path is used
    Expected Result: All 7 Must NOT Have guardrails verified clean
    Evidence: .sisyphus/evidence/F1-forbidden.txt
  ```

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m compileall cross_market/` + `pytest cross_market/tests/ -v` + `python -m py_compile cross_market/**/*.py`. Review all files for: empty catches, print() in production, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item). Verify no deep6v2 signal/scoring imports.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: Build and test pass
    Tool: Bash
    Steps:
      1. Run: python -m compileall cross_market/ → assert exit code 0
      2. Run: pytest cross_market/tests/ -v --tb=short → assert all pass
      3. Run: grep -rn "print(" cross_market/ --include="*.py" | grep -v "tests/" | grep -v "__pycache__" → assert zero matches in production code
    Expected Result: Compiles clean, tests pass, no print() in production
    Evidence: .sisyphus/evidence/F2-quality.txt
  ```

- [ ] F3. **Real Agent QA** — `unspecified-high`
  Start from clean state. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration (detectors feeding LLM, LLM feeding classifiers). Test edge cases: empty book, disconnection recovery, macro window behavior. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: Cross-task integration (detector → LLM → classifier)
    Tool: Bash
    Steps:
      1. Replay 5 minutes of NQ MBO data through full pipeline
      2. Assert: book reconstructed, detectors produced outputs, features extracted, LLM called, classifier predicted
      3. Assert each stage's output fed correctly into next stage
    Expected Result: End-to-end pipeline works
    Evidence: .sisyphus/evidence/F3-integration.txt

  Scenario: Edge case — empty book
    Tool: Bash
    Steps:
      1. Feed zero MBO events
      2. Assert: no crash, detectors return empty results, LLM returns "none" pattern
    Expected Result: Graceful handling of empty state
    Evidence: .sisyphus/evidence/F3-empty-book.txt
  ```

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance — especially no deep6v2 signal/scoring reuse. Verify handoff document coverage — 31 of 33 deliverables from §14 addressed (excludes #28 optional sequence model scaffold and #33 README which is covered by Task 43).
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Handoff Coverage [N/33] | VERDICT`

  **QA Scenarios**:
  ```
  Scenario: Handoff deliverable coverage
    Tool: Bash
    Steps:
      1. Read handoff §14 deliverable list (33 items). Exclude #28 (optional sequence model — deferred to future phase) and #33 (README — covered by Task 43)
      2. For each of the remaining 31: find corresponding file in cross_market/
      3. Assert file exists and contains non-trivial implementation (>10 lines)
    Expected Result: 31/33 deliverables have corresponding implementation (2 excluded with justification)
    Evidence: .sisyphus/evidence/F4-coverage.txt

  Scenario: No deep6v2 signal/scoring contamination
    Tool: Bash
    Steps:
      1. Run: grep -rn "deep6v2.signals\|deep6v2.scoring\|from deep6v2.signals\|from deep6v2.scoring" cross_market/ → assert zero
      2. Run: grep -rn "SignalId\|ConfluenceScorer\|DetectorRegistry" cross_market/ --include="*.py" → assert only local definitions, no deep6v2 imports
    Expected Result: Zero contamination from deep6v2 signal/scoring
    Evidence: .sisyphus/evidence/F4-contamination.txt
  ```

---

## Commit Strategy

Each wave gets one or more atomic commits:
- **Wave 0**: `chore(cross_market): validate MBO data availability`
- **Wave 1**: `feat(cross_market): package scaffolding, types, config, event store`
- **Wave 2**: `feat(cross_market): MBO connector, book reconstructor, replay engine`
- **Wave 3**: `feat(cross_market): spoof, iceberg, absorption, sweep, layering, vacuum detectors`
- **Wave 4**: `feat(cross_market): options, GEX, MADLevels context engines`
- **Wave 5**: `feat(cross_market): LLM expert layer with exemplars and outcome logging`
- **Wave 6**: `feat(cross_market): classifiers, meta-model, shadow mode`
- **Wave 7**: `feat(cross_market): dashboards, risk engine, production hardening`

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
pytest cross_market/tests/ -v --tb=short

# Book reconstruction validates
python -m cross_market replay --validate --session 2026-05-15

# Detector outputs on replay
python -m cross_market replay --detectors --session 2026-05-15

# LLM expert strict JSON
python -m cross_market test-llm --snapshot fixtures/test_snapshot.json

# Shadow mode mini-session
python -m cross_market shadow --duration 30m --log .sisyphus/evidence/shadow-test/

# Classifier metrics
python -m cross_market train --evaluate --holdout 0.2
```

### Final Checklist
- [ ] All "Must Have" items present and verified
- [ ] All "Must NOT Have" items confirmed absent
- [ ] All tests pass (>80% detector coverage)
- [ ] MBO replay completes without integrity errors
- [ ] LLM outputs strict JSON on 100% of calls
- [ ] Shadow mode: high-confidence confirms >70% on 30s forward
- [ ] Classifier profit factor ≥1.3 on held-out data
- [ ] No deep6v2 signal/scoring imports in cross_market/
