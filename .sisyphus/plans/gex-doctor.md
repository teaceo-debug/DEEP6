# GEX DOCTOR — Magnet Level Engine (Merged Build)

## TL;DR

> **Quick Summary**: Build a unified FlashAlpha-powered magnet engine that identifies NQ's primary GEX magnet level and displays it on the NinjaTrader chart. Python computes (FlashAlpha adapter + interpreter brain + magnet scoring), writes enriched JSON, NT8 indicator reads and renders.
> 
> **Deliverables**:
> - `gexdoctor/` Python package with FlashAlpha adapter, interpreter, magnet scorer
> - Enriched `gex_nq.json` output (magnet, confidence, bias, invalidation, walls)
> - NT8 `GEXDoctor` indicator (C#) rendering magnet + walls + bias on chart
> - Full TDD test suite
> 
> **Existing Assets Being Integrated**:
> - `gex_producer.py` — proven Python→NT8 file bridge pattern
> - `flashalpha_interpreter.md` — agent system prompt (brain)
> - `flashalpha_knowledge.yaml` — lookups, heuristics, modifiers
> - `flashalpha_snapshot_schema.json` — data contract
> - `DEEP6Atlas.cs` — reference NT8 indicator that reads gex_nq.json
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 4 waves + final
> **Critical Path**: T1 → T5 → T7/T8 → T9 → T12 → F1-F4

---

## Context

### Original Request
Build GEX DOCTOR — a magnet-first GEX confirmation engine for NQ. Originally spec'd with 3 sources (GexBot, FlashAlpha, TradeGEX) and a pywebview HUD. Pivoted during planning to: FlashAlpha-only positioning with Massive/Polygon for NQ price, displayed on NinjaTrader chart via file-based bridge.

### Pivot Rationale (from handoff + interview)
1. **GexBot dropped** — Canvas-rendered (pixels, not data). No structured API. Cannot be scraped.
2. **TradeGEX dropped** — Replaced by direct FlashAlpha integration. No Playwright/Vision needed.
3. **pywebview HUD dropped** — NinjaTrader chart is the display surface. Python writes JSON, NT8 reads it.
4. **Interpreter brain already built** — flashalpha_interpreter.md + knowledge.yaml handle the analysis logic.
5. **Python→NT8 bridge already proven** — gex_producer.py writes gex_nq.json atomically, DEEP6Atlas.cs reads it.

### Research Findings
- `DEEP6_ATLAS_NT8/PythonTools/gex_producer.py` — Working bridge: fetches from optionlevels.com, converts QQQ→NQ, writes gex_nq.json atomically. Template for our enhanced producer.
- `DEEP6_ATLAS_NT8/AddOns/gex_nq.json` — Current NT8 contract: flip, call_wall, put_wall, next_call, next_put, net_gex, regime, as_of, source. We'll enrich this.
- `flashalpha_snapshot_schema.json` — 98-line JSON schema mapping to FlashAlpha `/v1/flow/live/{symbol}` bundle. The adapter's output contract.
- `flashalpha_knowledge.yaml` — 145-line brain: regime_playbook (5 states), price_zone (4 zones), vol_outlook, 7 heuristics, modifiers, session routine.
- `flashalpha_interpreter.md` — Agent prompt: deterministic lookups first, then heuristics with caveats, outputs Regime/Map/Flow/Vol/Lean/Invalidation.
- `nq_atlas/flashalpha_client.py` — Existing FlashAlpha SDK wrapper with `run_in_executor` pattern.
- `nq_atlas/nq_mapper.py` — Proven QQQ→NQ ratio math.

---

## Work Objectives

### Core Objective
Answer "Where is NQ most likely being pulled right now?" by ingesting FlashAlpha dealer-positioning data, scoring magnet candidates, and displaying the primary magnet level + call/put walls + bias direction on the NinjaTrader chart.

### Concrete Deliverables
- `gexdoctor/` Python package at DEEP6 root
- `gexdoctor/monitor/adapters/flashalpha.py` — FlashAlpha data adapter producing FlashAlphaSnapshot
- `gexdoctor/monitor/price_service.py` — NQ spot price (Polygon + FlashAlpha)
- `gexdoctor/monitor/convert.py` — QQQ/NDX→NQ conversion
- `gexdoctor/monitor/magnet_scorer.py` — Magnet level scoring + selection
- `gexdoctor/monitor/interpreter.py` — Knowledge.yaml lookups + bias determination
- `gexdoctor/monitor/producer.py` — Enhanced gex_producer writing enriched JSON
- `gexdoctor/brain/` — flashalpha_interpreter.md, knowledge.yaml, snapshot_schema.json
- NT8 `GEXDoctor.cs` indicator — renders magnet, walls, bias, confidence on chart
- `gexdoctor/tests/` — TDD test suite

### Definition of Done
- [ ] `python -m gexdoctor --dry-run` → exit 0, config valid
- [ ] FlashAlpha adapter returns FlashAlphaSnapshot from live API
- [ ] Magnet scorer selects primary magnet with confidence ≥ 0.65 or returns "no magnet"
- [ ] Enhanced `gex_nq.json` written atomically with: flip, call_wall, put_wall, primary_magnet, magnet_confidence, bias_direction, invalidation_level, regime, as_of
- [ ] NT8 GEXDoctor indicator displays magnet level, call/put walls, bias arrow, confidence on chart
- [ ] Anti-flicker: magnet doesn't change every refresh
- [ ] All tests pass: `pytest gexdoctor/tests/ -v`

### Must Have
- Single primary magnet level output (not a list)
- Call wall + put wall + gamma flip displayed as key levels
- Bias direction (bullish/bearish/neutral/no_vote) derived from interpreter logic
- Magnet confidence score (0-1.0, minimum 0.65 to be valid)
- Anti-flicker magnet lock
- Invalidation level for every magnet
- File-based Python→NT8 bridge (atomic JSON writes)
- Audit trail (JSON logs per cycle)
- TDD test coverage

### Must NOT Have (Guardrails)
- **No trade execution** — decision support only
- **No browser automation** — no Playwright, no TradeGEX, no scraping
- **No pywebview/desktop GUI** — NT8 is the only display surface
- **No GexBot** — dropped entirely
- **No ML** — deterministic scoring from knowledge.yaml lookups
- **No database** — JSON file persistence only
- **No web server** — file-based bridge, no FastAPI, no ports
- **No multi-symbol** — NQ only (QQQ/NDX as proxy inputs, not tracked separately)
- **No cross-package imports** — don't import from nq_atlas/, deep6/, deep6v2/
- **No hardcoded ratios** — live NQ/QQQ computation

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed.

### Test Decision
- **Infrastructure**: YES (pytest 8.0+, asyncio_mode="auto")
- **Automated tests**: TDD (RED-GREEN-REFACTOR)
- **Framework**: pytest with pytest-asyncio

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: `pytest gexdoctor/tests/test_X.py -v`
- **NT8 indicator**: Build verification via NT8 compile check
- **End-to-end**: `python -m gexdoctor --dry-run` + JSON output validation

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 4 parallel, start immediately):
├── T1:  Project scaffold + integrate handoff assets [quick]
├── T2:  Pydantic schemas (FlashAlphaSnapshot, MagnetResult, EnrichedGexOutput) [quick]
├── T3:  NQ conversion module (QQQ→NQ, NDX→NQ) [quick]
└── T4:  Logger + config (config.yaml, env vars, structured logging) [quick]

Wave 2 (Data + Scoring — 4 parallel, after Wave 1):
├── T5:  FlashAlpha data adapter (live bundle + settled fallback) [deep]
├── T6:  NQ price service (Polygon NQ + FlashAlpha QQQ spot) [unspecified-high]
├── T7:  Magnet scoring engine (level scoring, selection, anti-flicker) [deep]
└── T8:  Interpreter integration (knowledge.yaml lookups → bias/regime) [unspecified-high]

Wave 3 (Output + Integration — 3 parallel, after Wave 2):
├── T9:  Enhanced gex_producer (orchestrator loop → enriched JSON) [unspecified-high]
├── T10: NT8 GEXDoctor indicator (C# — reads enriched JSON, renders on chart) [deep]
└── T11: CLI entry point + dry-run [quick]

Wave 4 (Tests — after Wave 3):
└── T12: Integration + edge case tests [deep]

Wave FINAL (4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: T1 → T5 → T7 → T9 → T11 → T12 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Waves 1 & 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T5,T6,T7,T8,T9 | 1 |
| T2 | — | T5,T6,T7,T8,T9,T10 | 1 |
| T3 | — | T5,T6,T7 | 1 |
| T4 | — | T5,T6,T9 | 1 |
| T5 | T1,T2,T3,T4 | T7,T8,T9 | 2 |
| T6 | T1,T2,T3 | T7,T9 | 2 |
| T7 | T2,T3,T5,T6 | T9 | 2 |
| T8 | T1,T2 | T9 | 2 |
| T9 | T5,T6,T7,T8 | T11,T12 | 3 |
| T10 | T2 | T12 | 3 |
| T11 | T9 | T12 | 3 |
| T12 | T9,T10,T11 | F1-F4 | 4 |

### Agent Dispatch Summary

| Wave | Tasks | Dispatch |
|------|-------|----------|
| 1 | 4 | T1→`quick`, T2→`quick`, T3→`quick`, T4→`quick` |
| 2 | 4 | T5→`deep`, T6→`unspecified-high`, T7→`deep`, T8→`unspecified-high` |
| 3 | 3 | T9→`unspecified-high`, T10→`deep`, T11→`quick` |
| 4 | 1 | T12→`deep` |
| FINAL | 4 | F1→`oracle`, F2→`unspecified-high`, F3→`unspecified-high`, F4→`deep` |

---

## TODOs

- [x] 1. Project Scaffold + Integrate Handoff Assets

  **What to do**:
  - Create `gexdoctor/` directory at DEEP6 root:
    ```
    gexdoctor/
    ├── pyproject.toml          # standalone deps: pydantic, httpx, flashalpha, pytest
    ├── config.yaml             # FlashAlpha cadence, source weights, thresholds
    ├── .env.gexdoctor.example  # FLASHALPHA_API_KEY, MASSIVE_API_KEY, ANTHROPIC_API_KEY
    ├── __init__.py
    ├── __main__.py             # CLI skeleton
    ├── monitor/
    │   ├── __init__.py
    │   ├── adapters/
    │   │   ├── __init__.py
    │   │   └── flashalpha.py   # placeholder
    │   ├── schemas.py          # placeholder
    │   ├── convert.py          # placeholder
    │   ├── magnet_scorer.py    # placeholder
    │   ├── interpreter.py      # placeholder
    │   ├── price_service.py    # placeholder
    │   ├── producer.py         # placeholder
    │   └── logger.py           # placeholder
    ├── brain/
    │   ├── flashalpha_interpreter.md    # COPY from handoff
    │   ├── flashalpha_knowledge.yaml   # COPY from handoff
    │   └── flashalpha_snapshot_schema.json  # COPY from handoff
    ├── logs/       # gitkeep
    └── tests/
        ├── __init__.py
        ├── conftest.py
        └── fixtures/   # gitkeep
    ```
  - Copy handoff assets from `C:\Users\Tea\Downloads\files (3).zip` (already extracted to temp) into `gexdoctor/brain/`
  - Copy `gex_producer.py` from `DEEP6_ATLAS_NT8_extracted` into `gexdoctor/reference/` as a reference (not to run directly — we'll build enhanced version)
  - Copy `gex_nq.json` as `gexdoctor/reference/gex_nq_sample.json` for schema reference
  - Write minimal `__main__.py` with `--dry-run` flag
  - TDD: `tests/test_scaffold.py` — verify brain files load, config structure valid

  **Must NOT do**:
  - Do NOT import from nq_atlas/, deep6/, deep6v2/
  - Do NOT add database, web server, or Playwright dependencies
  - Do NOT modify any file outside gexdoctor/ except NT8 indicator (T10)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (with T2, T3, T4)
  - **Blocks**: T5, T6, T7, T8, T9
  - **Blocked By**: None

  **References**:
  - `C:\Users\Tea\AppData\Local\Temp\opencode\flashalpha_handoff\` — 3 brain files to copy
  - `C:\Users\Tea\Downloads\DEEP6_ATLAS_NT8_extracted\DEEP6_ATLAS_NT8\PythonTools\gex_producer.py` — reference producer
  - `C:\Users\Tea\Downloads\DEEP6_ATLAS_NT8_extracted\DEEP6_ATLAS_NT8\AddOns\gex_nq.json` — reference JSON schema
  - `nq_atlas/config.py` — BaseSettings pattern with env_prefix

  **Acceptance Criteria**:
  - [ ] `gexdoctor/brain/` contains all 3 handoff files
  - [ ] `pytest gexdoctor/tests/test_scaffold.py -v` → PASS
  - [ ] `python -m gexdoctor --dry-run` → exit 0

  **QA Scenarios**:
  ```
  Scenario: Brain files accessible
    Tool: Bash
    Steps:
      1. Test-Path "gexdoctor/brain/flashalpha_knowledge.yaml"
      2. Test-Path "gexdoctor/brain/flashalpha_interpreter.md"
      3. Test-Path "gexdoctor/brain/flashalpha_snapshot_schema.json"
    Expected Result: All True
    Evidence: .sisyphus/evidence/task-1-brain-files.txt
  ```

  **Commit**: YES (Wave 1) — `feat(gexdoctor): scaffold project + integrate handoff assets`

- [x] 2. Pydantic Schemas

  **What to do**:
  - Create `gexdoctor/monitor/schemas.py` with all models (frozen Pydantic v2):
    - `FlashAlphaSnapshot` — matches `flashalpha_snapshot_schema.json` exactly (regime, dealer_risk, pin, oi_simulator, profile_shape, higher_order, vol_context, feed_quality)
    - `MagnetCandidate` — level, level_type, source, score, confidence
    - `MagnetResult` — primary_magnet, magnet_confidence, invalidation_level, invalidation_reason, supporting_levels
    - `BiasResult` — direction (bullish/bearish/neutral/no_vote), regime, lean, confidence_label, caveats
    - `EnrichedGexOutput` — the enriched gex_nq.json contract: flip, call_wall, put_wall, primary_magnet, magnet_confidence, bias_direction, invalidation_level, regime, net_gex, as_of, source, vanna_context, charm_context
    - `SourceHealth` — fresh_sec, stale, latency_ms, read_status
    - `NQQuote` — nq_price, qqq_price, ndx_price, source, timestamp
  - All use `ConfigDict(frozen=True)`, `from __future__ import annotations`, `__all__`
  - TDD: `tests/test_schemas.py` — creation, frozen enforcement, serialization to JSON

  **Must NOT do**:
  - No ORM, no database columns, no methods with I/O

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 1 (with T1, T3, T4)
  - **Blocks**: T5, T6, T7, T8, T9, T10
  - **Blocked By**: None

  **References**:
  - `gexdoctor/brain/flashalpha_snapshot_schema.json` — exact field mapping for FlashAlphaSnapshot
  - `C:\Users\Tea\Downloads\DEEP6_ATLAS_NT8_extracted\DEEP6_ATLAS_NT8\AddOns\gex_nq.json` — current gex_nq fields to extend for EnrichedGexOutput
  - `nq_atlas/types.py` — `ConfigDict(frozen=True)` pattern to follow

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_schemas.py -v` → PASS
  - [ ] FlashAlphaSnapshot importable and matches snapshot schema fields
  - [ ] EnrichedGexOutput includes: primary_magnet, magnet_confidence, bias_direction, invalidation_level
  - [ ] All models frozen (mutation raises error)

  **QA Scenarios**:
  ```
  Scenario: Schemas match data contracts
    Tool: Bash
    Steps:
      1. cd gexdoctor && python -m pytest tests/test_schemas.py -v --tb=short
    Expected Result: All PASSED
    Evidence: .sisyphus/evidence/task-2-schemas.txt
  ```

  **Commit**: YES (Wave 1) — `feat(gexdoctor): add Pydantic schemas`

- [x] 3. NQ Conversion Module

  **What to do**:
  - Create `gexdoctor/monitor/convert.py` — same spec as before:
    - `compute_nq_qqq_factor(nq_spot, qqq_spot) -> float`
    - `qqq_to_nq(qqq_level, factor) -> float`
    - `ndx_to_nq(ndx_level, nq_ndx_basis) -> float`
    - `normalize_level(level, symbol, nq_spot, qqq_spot, ndx_spot) -> float`
    - SPX → ValueError (regime context only)
    - Division-by-zero guards
    - All conversions logged
  - TDD: `tests/test_convert.py`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (with T1, T2, T4) — Blocks T5, T6, T7

  **References**:
  - `nq_atlas/nq_mapper.py:6-9` — proven QQQ→NQ math
  - `gex_producer.py:123-149` — translate_to_nq function (copy the scaling logic)
  - Spec section 5 from original master prompt — conversion rules

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_convert.py -v` → PASS
  - [ ] QQQ→NQ conversion matches expected values
  - [ ] SPX rejected, zero-division guarded

  **Commit**: YES (Wave 1) — `feat(gexdoctor): add NQ conversion module`

- [x] 4. Logger + Config

  **What to do**:
  - `gexdoctor/monitor/logger.py` — JSON structured logging + audit trail (same as original T3)
  - `gexdoctor/config.yaml` with: FlashAlpha cadence (15s), scoring thresholds (0.65 min confidence, 0.12 anti-flicker margin), output path (default NT8 AddOns path), source weights
  - Config loading via Pydantic BaseSettings with `GEXDOCTOR_` env prefix
  - TDD: `tests/test_config.py`, `tests/test_logger.py`

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 1 (with T1, T2, T3) — Blocks T5, T6, T9

  **References**:
  - `nq_atlas/config.py` — BaseSettings pattern
  - `gex_producer.py:62-70` — DEFAULT_OUTPUT_PATH for NT8 AddOns directory

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_config.py gexdoctor/tests/test_logger.py -v` → PASS
  - [ ] Config loads from yaml + env vars

  **Commit**: YES (Wave 1) — `feat(gexdoctor): add config + structured logger`

- [x] 5. FlashAlpha Data Adapter

  **What to do**:
  - Create `gexdoctor/monitor/adapters/flashalpha.py`:
    - `FlashAlphaAdapter` — async adapter producing `FlashAlphaSnapshot`
    - **Primary feed**: `GET /v1/flow/live/{symbol}` bundle (Alpha tier) → regime, dealer_risk, pin, oi_simulator
    - **Settled fallback**: `/v1/exposure/gex/{symbol}` + `/v1/exposure/levels/{symbol}` (Basic tier) if live unavailable
    - **Per-strike profile**: `/v1/flow/gex/{symbol}` → derive `profile_shape` (distribution, dominant_strike, dominant_side)
    - **Higher-order**: `/v1/exposure/vex`, `/v1/exposure/chex` → vex_sign, chex_sign
    - Wraps FlashAlpha SDK with `asyncio.run_in_executor` (sync SDK → async)
    - Auth: `X-Api-Key` header, base URL `https://lab.flashalpha.com`
    - **⚠ Field trap**: top-level `live_gex_delta` is actually net DEX — pull DEX from `flow_adjusted_dealer_risk.live_net_dex` (handoff section 5 warning)
    - Graceful degradation: missing fields → add to `feed_quality.missing_fields`, reduce confidence
    - Staleness: track poll timestamp, mark stale if > 120s
    - Cadence minimum: 15s
    - Returns `FlashAlphaSnapshot` (Pydantic model from T2)
  - TDD: `tests/test_flashalpha_adapter.py` — mock SDK responses, test live bundle parsing, test settled fallback, test field trap handling, test stale detection

  **Must NOT do**:
  - Do NOT import from nq_atlas/flashalpha_client.py — build fresh
  - Do NOT poll faster than 15s
  - Do NOT ignore the DEX field trap (handoff §5)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nq-options-algo-engine/data-sources/flashalpha-bridge`]
    - Contains FlashAlpha polling patterns, tier optimization, response normalization, stale detection

  **Parallelization**:
  - **Can Run In Parallel**: YES — Wave 2 (with T6, T7, T8)
  - **Blocks**: T7, T8, T9
  - **Blocked By**: T1, T2, T3, T4

  **References**:
  - `nq_atlas/flashalpha_client.py` — SDK wrapping pattern (run_in_executor). Copy the approach.
  - `gexdoctor/brain/flashalpha_snapshot_schema.json` — EXACT output schema to produce
  - Handoff section 5 — FlashAlpha API reference, endpoints, field trap warning
  - Handoff section 6.1 — "Build the data adapter" — exactly this task
  - `.claude/skills/nq-options-algo-engine/data-sources/flashalpha-bridge.md` — polling guide

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_flashalpha_adapter.py -v` → PASS (6+ tests)
  - [ ] Mock live bundle → returns valid FlashAlphaSnapshot with all regime fields
  - [ ] Settled fallback when live unavailable → returns partial snapshot with missing_fields
  - [ ] DEX field trap handled (uses dealer_risk.live_net_dex, not top-level live_gex_delta)
  - [ ] Stale data (>120s) → freshness penalty

  **QA Scenarios**:
  ```
  Scenario: Adapter produces valid snapshot
    Tool: Bash
    Steps:
      1. cd gexdoctor && python -m pytest tests/test_flashalpha_adapter.py -v --tb=short
    Expected Result: All PASSED — live bundle, settled fallback, field trap, stale detection
    Evidence: .sisyphus/evidence/task-5-flashalpha.txt
  ```

  **Commit**: YES (Wave 2) — `feat(gexdoctor): add FlashAlpha data adapter`

- [x] 6. NQ Price Service

  **What to do**:
  - Create `gexdoctor/monitor/price_service.py`:
    - `NQPriceService` — async multi-source NQ spot
    - Source 1: Polygon.io `GET /v2/last/trade/NQ%3ACME` via httpx
    - Source 2: FlashAlpha `underlying_price` from snapshot (QQQ → convert to NQ)
    - Returns `NQQuote` with nq_price, qqq_price, conversion factors
    - Fallback: if Polygon fails → use FlashAlpha QQQ × ratio
    - Cache: last known price with stale tracking (stale > 30s)
    - Refresh: every 5s minimum
  - TDD: `tests/test_price_service.py` — test primary, fallback, stale, cache

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 2 (with T5, T7, T8) — Blocks T7, T9

  **References**:
  - `nq_atlas/massive_client.py` — Polygon NQ quote endpoint pattern
  - `gex_producer.py:113-120` — compute_nq_qqq_ratio function

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_price_service.py -v` → PASS
  - [ ] Polygon → NQ price returned
  - [ ] Polygon fails → FlashAlpha QQQ fallback works

  **Commit**: YES (Wave 2) — `feat(gexdoctor): add NQ price service`

- [x] 7. Magnet Scoring Engine

  **What to do**:
  - Create `gexdoctor/monitor/magnet_scorer.py`:
    - `MagnetScorer` — scores FlashAlpha levels as magnet candidates
    - **Candidate extraction**: From FlashAlphaSnapshot, identify magnet candidates:
      - `gamma_flip` — regime boundary, common pivot (weight 0.90)
      - `call_wall` — upper magnet/cap (weight 0.85)
      - `put_wall` — lower magnet/floor (weight 0.85)
      - `max_pain` — pin target into expiry (weight 0.80 when 0DTE, 0.40 otherwise)
      - `pin.magnet_strike` — direct magnet from FlashAlpha (weight 1.00 when pin_risk > 65)
    - **Scoring formula** (simplified from 3-source to single-source):
      ```
      MagnetScore = level_type_weight × distance_relevance × regime_alignment
                    × freshness × pin_boost × confidence_modifier
      ```
      - Distance relevance: inverse distance from current NQ (closer = higher)
      - Regime alignment: does the level's pull direction match regime?
      - Pin boost: if pin_risk > 65 and level is magnet_strike, boost significantly
      - Confidence modifier: feed_quality.oi_delta_confidence
    - **Selection**: Highest score above 0.65 threshold → primary magnet
    - **Anti-flicker** (from original spec section 8):
      - Replace only if new_score >= current_score + 0.12
      - OR current invalidated / stale / source changed
    - **Invalidation**: For each magnet, compute invalidation level:
      - Gamma flip → opposite side of flip
      - Call/put wall → break + acceptance beyond wall
      - Max pain/pin → regime flip invalidates
    - Returns `MagnetResult`
  - TDD: `tests/test_magnet_scorer.py` — test scoring, selection, threshold, anti-flicker, invalidation

  **Must NOT do**:
  - No ML — deterministic scoring only
  - No historical tracking of magnet accuracy

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nq-options-algo-engine/algo-patterns/composite-scoring`]

  **Parallelization**: Wave 2 (with T5, T6, T8) — Blocks T9

  **References**:
  - Original master prompt sections 6-9 — magnet definition, scoring, anti-flicker, invalidation
  - `gexdoctor/brain/flashalpha_knowledge.yaml` — price_zone lookups inform scoring
  - `deep6/bias_engine/gex_client.py` — weighted scoring pattern

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_magnet_scorer.py -v` → PASS (8+ tests)
  - [ ] Pin strike with pin_risk=80 near expiry → selected as primary magnet
  - [ ] Score below 0.65 → "no magnet"
  - [ ] Anti-flicker: +0.11 margin → not replaced; +0.13 → replaced
  - [ ] Every magnet has invalidation level

  **QA Scenarios**:
  ```
  Scenario: Magnet scoring and anti-flicker
    Tool: Bash
    Steps:
      1. cd gexdoctor && python -m pytest tests/test_magnet_scorer.py -v --tb=short
    Expected Result: All PASSED
    Evidence: .sisyphus/evidence/task-7-magnet-scorer.txt
  ```

  **Commit**: YES (Wave 2) — `feat(gexdoctor): add magnet scoring engine`

- [x] 8. Interpreter Integration

  **What to do**:
  - Create `gexdoctor/monitor/interpreter.py`:
    - `PositioningInterpreter` — deterministic interpreter using knowledge.yaml
    - **Loads** `gexdoctor/brain/flashalpha_knowledge.yaml` on init
    - **Step 1 — Regime**: `snapshot.regime.gex_sign` → vocabulary lookup → "long gamma" or "short gamma"
    - **Step 2 — Price Zone**: locate `underlying_price` vs `gamma_flip`, `call_wall`, `put_wall` → `price_zone` lookup (4 zones)
    - **Step 3 — Flow State**: `dealer_risk.flow_direction` × `gex_sign` → `regime_playbook` (5 states)
    - **Step 4 — Vol Outlook**: flow_direction × gex → `vol_outlook` lookup
    - **Step 5 — Heuristics**: fire applicable heuristics (pin, stale_anchor, low_confidence, flip_proximity, vanna, charm, dex) — each returns a caveat string
    - **Step 6 — Bias Direction**:
      - Price zone + regime → bullish/bearish/neutral
      - Flow amplifying/dampening modifies confidence
      - Near flip → neutral (unstable zone)
    - Returns `BiasResult` with direction, regime, lean, confidence_label, caveats
    - This is the DETERMINISTIC part of the interpreter — no LLM calls. Pure lookups from knowledge.yaml.
  - TDD: `tests/test_interpreter.py` — test each lookup, each heuristic trigger, bias determination

  **Must NOT do**:
  - Do NOT call Claude/LLM here — this is deterministic lookup logic
  - Do NOT invent levels — read only from FlashAlphaSnapshot

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 2 (with T5, T6, T7) — Blocks T9

  **References**:
  - `gexdoctor/brain/flashalpha_knowledge.yaml` — THE source of truth. Every lookup/heuristic/modifier defined here.
  - `gexdoctor/brain/flashalpha_interpreter.md` — procedure (6 steps). Implement steps 1-6 as Python code.
  - Handoff section 3 — FlashAlpha model explanation (settled vs flow, dealer risk join)

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_interpreter.py -v` → PASS (10+ tests)
  - [ ] Positive GEX + amplifying → regime_playbook = "range_tightening"
  - [ ] Price above call_wall + positive GEX → zone = "above_call_wall", read = "stretched/likely rejected"
  - [ ] pin_risk=80, 0DTE → pin_into_expiry heuristic fires
  - [ ] low oi_delta_confidence → low_confidence heuristic fires, defers to settled

  **QA Scenarios**:
  ```
  Scenario: Interpreter lookups correct
    Tool: Bash
    Steps:
      1. cd gexdoctor && python -m pytest tests/test_interpreter.py -v --tb=short
    Expected Result: All regime_playbook, price_zone, vol_outlook, heuristic tests PASSED
    Evidence: .sisyphus/evidence/task-8-interpreter.txt
  ```

  **Commit**: YES (Wave 2) — `feat(gexdoctor): add positioning interpreter`

- [x] 9. Enhanced gex_producer (Orchestrator + JSON Writer)

  **What to do**:
  - Create `gexdoctor/monitor/producer.py` — the enhanced gex_producer:
    - `GexDoctorProducer` — main orchestrator class
    - **Poll cycle** (async):
      1. Fetch NQ spot from price_service
      2. Fetch FlashAlpha data via adapter → FlashAlphaSnapshot
      3. Normalize all QQQ levels to NQ via convert.py
      4. Run interpreter → BiasResult (regime, direction, lean, caveats)
      5. Run magnet_scorer → MagnetResult (primary_magnet, confidence, invalidation)
      6. Apply anti-flicker (compare to previous magnet)
      7. Build EnrichedGexOutput (all fields for gex_nq.json)
      8. Write atomically to output path (tmp + rename, same as gex_producer.py:152-158)
      9. Write audit log
    - **Output JSON** (enriched `gex_nq.json`):
      ```json
      {
        "instrument": "NQ",
        "flip": 22000.0,
        "call_wall": 22300.0,
        "put_wall": 21800.0,
        "next_call": 22250.0,
        "next_put": 21850.0,
        "net_gex": 5000000000,
        "regime": "POS_GEX",
        "primary_magnet": 22100.0,
        "magnet_confidence": 0.82,
        "bias_direction": "bullish",
        "invalidation_level": 21950.0,
        "invalidation_reason": "Break below gamma flip",
        "lean": "mean-revert toward call wall",
        "pin_risk": 72,
        "max_pain": 22050.0,
        "caveats": ["stale_anchor: settled may be stale, trust live"],
        "as_of": "2026-05-28T14:30:00-04:00",
        "source": "flashalpha-QQQ-x45.42",
        "stale_after_seconds": 300
      }
      ```
    - **Output path**: configurable, default `C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\AddOns\gex_nq.json`
    - **Atomic write**: write to .tmp, then rename (prevents NT8 reading mid-write)
    - **Configurable interval**: default 15s
    - Error isolation: if adapter fails, write last-known with stale flag
  - TDD: `tests/test_producer.py` — test full cycle with mocks, test atomic write, test stale fallback, test output JSON shape

  **Must NOT do**:
  - Do NOT add web server or SSE — file-based output only
  - Do NOT modify files outside gexdoctor/ (except the gex_nq.json output path which is in NT8 directory)

  **Recommended Agent Profile**: `unspecified-high`
  **Parallelization**: Wave 3 — Blocks T11, T12

  **References**:
  - `gex_producer.py:152-158` — atomic write pattern (tmp + rename). Copy exactly.
  - `gex_producer.py:164-204` — run_loop pattern with consecutive failure handling
  - `gex_nq_sample.json` — base JSON shape to extend

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/test_producer.py -v` → PASS
  - [ ] Mock cycle → writes valid JSON with all enriched fields
  - [ ] Atomic write: .tmp file created then renamed
  - [ ] Adapter failure → last-known output with stale flag

  **Commit**: YES (Wave 3) — `feat(gexdoctor): add enhanced gex producer`

- [x] 10. NT8 GEXDoctor Indicator

  **What to do**:
  - Create NinjaTrader indicator `GEXDoctor.cs` that reads enriched `gex_nq.json`:
    - **File reader**: polls `gex_nq.json` every 60s (configurable) from AddOns directory
    - **JSON parsing**: reads all enriched fields including primary_magnet, magnet_confidence, bias_direction, invalidation_level
    - **Chart rendering**:
      - **Primary Magnet**: Horizontal line at magnet level (bright color, thicker line, labeled "MAGNET 22100")
      - **Call Wall**: Horizontal line (green/teal, labeled "CW 22300")
      - **Put Wall**: Horizontal line (red/orange, labeled "PW 21800")
      - **Gamma Flip**: Horizontal line (yellow/gold, dashed, labeled "FLIP 22000")
      - **Invalidation**: Horizontal line (gray, dotted, labeled "INVALID 21950")
      - **Bias indicator**: Text label or arrow showing direction + confidence ("Bullish 82%")
      - **Regime badge**: Small text showing "POS_GEX" or "NEG_GEX"
      - **Stale warning**: If data older than stale_after_seconds, show "STALE" badge in red
    - **Colors**: Follow DEEP6 visual design conventions (dark theme compatible)
    - **Configurable**: colors, line widths, show/hide individual levels, poll interval
    - Deploy to: `C:\Users\Public\Documents\NinjaTrader 8\bin\Custom\Indicators\GEXDoctor.cs`
  - TDD: Since this is C#/NinjaScript, verify via compilation check

  **Must NOT do**:
  - Do NOT add trade execution (no EnterLong, no SubmitOrder)
  - Do NOT add complex SharpDX rendering — use standard Draw.* methods
  - Do NOT modify DEEP6Atlas.cs or any existing indicator

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-new`, `nt8-visual-design`]
    - `nt8-new`: NinjaScript code generation patterns
    - `nt8-visual-design`: Color palettes, layout conventions for NT8 overlays

  **Parallelization**: Wave 3 (parallel with T9, T11) — Blocks T12

  **References**:
  - `DEEP6_ATLAS_NT8/Indicators/DEEP6Atlas.cs` — reference indicator that reads gex_nq.json. Copy the JSON reading pattern but build a simpler, focused indicator.
  - `gex_nq.json` sample — the JSON schema this indicator consumes
  - `.claude/skills/nt8-visual-design/knowledge.md` — DEEP6 visual design conventions

  **Acceptance Criteria**:
  - [ ] `GEXDoctor.cs` compiles without errors in NinjaTrader
  - [ ] Reads gex_nq.json and draws: magnet line, call wall, put wall, gamma flip, invalidation
  - [ ] Shows bias direction + confidence as text label
  - [ ] Shows stale warning when data is old
  - [ ] All colors follow DEEP6 conventions

  **QA Scenarios**:
  ```
  Scenario: NT8 indicator compiles
    Tool: Bash (nt8-compile.ps1 if available)
    Steps:
      1. Copy GEXDoctor.cs to NT8 Indicators directory
      2. Trigger NT8 compile
      3. Check for compile errors
    Expected Result: 0 compile errors
    Evidence: .sisyphus/evidence/task-10-nt8-compile.txt
  ```

  **Commit**: YES (Wave 3) — `feat(gexdoctor): add NT8 GEXDoctor indicator`

- [x] 11. CLI Entry Point + Dry-Run

  **What to do**:
  - Complete `gexdoctor/__main__.py` and `gexdoctor/launch.py`:
    - `--dry-run` — validate config, check API keys present, verify output path writable, exit 0/1
    - `--once` — run one poll cycle, write JSON, exit (for testing)
    - `--interval N` — override poll interval (seconds)
    - `--output PATH` — override output JSON path
    - `--verbose` — DEBUG logging
    - `--source QQQ|NDX` — which FlashAlpha symbol to track
    - Default: continuous loop at configured interval, writing gex_nq.json
    - Graceful shutdown on Ctrl+C
    - Startup banner: "GEX Doctor v0.1 — FlashAlpha → NQ Magnet Engine"
  - TDD: `tests/test_cli.py` — test --dry-run, test --once, test flag parsing

  **Recommended Agent Profile**: `quick`
  **Parallelization**: Wave 3 (with T9, T10) — Blocks T12

  **References**:
  - `gex_producer.py:207-228` — argparse CLI pattern
  - `deep6v2/__main__.py` — CLI entry point pattern

  **Acceptance Criteria**:
  - [ ] `python -m gexdoctor --dry-run` → exit 0 with valid config
  - [ ] `python -m gexdoctor --once --output /tmp/test.json` → writes one JSON file
  - [ ] `pytest gexdoctor/tests/test_cli.py -v` → PASS

  **Commit**: YES (Wave 3) — `feat(gexdoctor): add CLI entry point`

- [x] 12. Integration + Edge Case Tests

  **What to do**:
  - Create `gexdoctor/tests/test_integration.py`:
    - Full pipeline: mock FlashAlpha → adapter → interpreter → scorer → producer → JSON
    - Verify output JSON has all enriched fields
    - Verify bias_direction matches expected for given regime + price zone
    - Verify primary_magnet is the highest-scoring candidate
  - Create `gexdoctor/tests/test_edge_cases.py`:
    - FlashAlpha API down → stale fallback, JSON still written with stale flag
    - All levels null/missing → "no magnet" in output
    - Pin risk high (>65), 0DTE → magnet_strike selected as primary
    - Regime flip → old magnet invalidated, new selection forced
    - NQ price unavailable → conversion uses cached ratio
    - Anti-flicker: rapid score changes within margin → magnet stable
    - Division by zero in conversion → graceful error
    - Malformed FlashAlpha response → adapter returns None, cycle skips
    - Config missing API key → dry-run fails with clear error
  - Create `gexdoctor/tests/fixtures/` with:
    - `sample_live_bundle.json` — mock FlashAlpha live bundle response
    - `sample_settled.json` — mock settled exposure response
    - `sample_enriched_output.json` — expected gex_nq.json output
  - All tests use fixtures, no live API calls

  **Recommended Agent Profile**: `deep`
  **Parallelization**: Wave 4 (after T9, T10, T11) — Blocks F1-F4

  **References**:
  - `gexdoctor/brain/flashalpha_snapshot_schema.json` — field reference for fixture data
  - `tests_v2/conftest.py` — pytest fixture patterns

  **Acceptance Criteria**:
  - [ ] `pytest gexdoctor/tests/ -v --tb=short` → ALL PASS, 0 failures
  - [ ] 40+ total tests across all test files
  - [ ] Full pipeline test produces valid enriched JSON
  - [ ] All edge cases handled without crashes

  **QA Scenarios**:
  ```
  Scenario: Full test suite green
    Tool: Bash
    Steps:
      1. cd gexdoctor && python -m pytest tests/ -v --tb=short 2>&1
    Expected Result: All PASSED, 0 FAILED, 40+ tests
    Evidence: .sisyphus/evidence/task-12-full-suite.txt

  Scenario: No live API keys needed
    Tool: Bash
    Steps:
      1. cd gexdoctor && $env:FLASHALPHA_API_KEY=""; python -m pytest tests/ -v -k "not integration" --tb=short 2>&1
    Expected Result: All non-integration tests PASSED without API keys
    Evidence: .sisyphus/evidence/task-12-no-keys.txt
  ```

  **Commit**: YES (Wave 4) — `test(gexdoctor): add integration + edge case tests`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  For each "Must Have": verify implementation exists. For each "Must NOT Have": search for forbidden patterns (browser automation, database, web server, cross-package imports). Check enriched gex_nq.json contains all required fields. Verify NT8 indicator compiles.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | VERDICT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `pytest gexdoctor/tests/ -v`. Review all Python files for: empty catches, `print()` in prod, unused imports. Verify Pydantic models use `frozen=True`. Check NinjaScript follows DEEP6 conventions.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Run `python -m gexdoctor --dry-run`. Verify enriched gex_nq.json output is valid JSON with all fields. Run full test suite. Verify NT8 indicator compiles (nt8-compile.ps1 if available).
  Output: `Scenarios [N/N pass] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  Verify: no files outside gexdoctor/ (except NT8 indicator). No database code. No trade execution. No browser automation. No GexBot code. No pywebview. All changes match plan scope.
  Output: `Tasks [N/N compliant] | Scope [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Wave | Message | Key Files |
|------|---------|-----------|
| 1 | `feat(gexdoctor): scaffold + schemas + convert + config` | gexdoctor/** |
| 2 | `feat(gexdoctor): FlashAlpha adapter + price service + magnet scorer + interpreter` | gexdoctor/monitor/** |
| 3 | `feat(gexdoctor): enhanced producer + NT8 indicator + CLI` | gexdoctor/monitor/producer.py, ninjatrader/ |
| 4 | `test(gexdoctor): integration + edge case tests` | gexdoctor/tests/** |

---

## Success Criteria

### Verification Commands
```bash
cd gexdoctor
python -m gexdoctor --dry-run                    # Expected: exit 0, "Config valid"
pytest tests/ -v --tb=short                       # Expected: all green
python -m gexdoctor --once --output /tmp/test.json  # Expected: valid enriched JSON
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass
- [ ] gex_nq.json has: primary_magnet, magnet_confidence, bias_direction, invalidation_level
- [ ] NT8 indicator shows magnet + walls + bias on chart
- [ ] Anti-flicker prevents magnet jitter
- [ ] Audit logs written per cycle
