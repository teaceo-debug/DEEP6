# GEX Doctor v2.0 — Institutional Options Bias Terminal

## TL;DR

> **Quick Summary**: Build a standalone 800×800 retro green terminal that continuously analyzes the options market across 3 data sources (FlashAlpha, Massive.com, Unusual Whales), synthesizes via Claude API interpretation, and displays NQ directional bias — all in a single glance. Accuracy is maximized through multi-source cross-validation and regime-aware weighting; a fixed-dataset replay validation task (Task 23) measures signal quality before final verification.
>
> **Deliverables**:
> - Python async backend: orchestration loop polling 3 sources every 30s, Claude API interpretation on material change, FastAPI SSE streaming
> - Next.js retro terminal UI: 800×800 fixed window, phosphor green on black, CRT effects, all analysis dimensions visible simultaneously
> - Bidirectional DEEP6 integration: pushes GEXDoctorPayload (score:int, max_range:int=3, updated_at:float) to bias engine via POST /api/gex/ingest, reads bias_score+bias_label from GET /api/v3/bias
> - Unusual Whales dark pool client (Phase 2)
>
> **Estimated Effort**: Large (3d+)
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: Task 1 → Task 6 → Task 10 → Task 16 → Task 17 → Task 17b → F1-F4

---

## Context

### Original Request
Build a "GEX Doctor" — an old school 80s green terminal that acts as a Python data center where Claude constantly analyzes the GEX/options market to determine NQ bullish/bearish bias. Uses FlashAlpha, Massive.com, and Unusual Whales data. All information visible on a single panel with one glance. Spawn design agents for the visual and architecture agents for the backend.

### Interview Summary
**Key Discussions**:
- **Deployment**: Completely separate standalone app (own Next.js + FastAPI)
- **Claude's Role**: Claude API in Python backend for periodic narrative interpretation
- **Data Sources**: All three — FlashAlpha ($299/mo), Massive ($999/mo), Unusual Whales
- **Display**: Everything on ONE panel, single glance, no tabs/drill-down
- **Refresh**: Every 30 seconds
- **Screen**: Fixed 800×800 square window, retro 80s phosphor green
- **Integration**: Full bidirectional with DEEP6's bias engine

**Research Findings**:
- ~80% of Python backend ALREADY EXISTS in nq_atlas/, gexdoctor/, deep6/
- Existing dashboard has CRT effects (Scanlines.tsx, Grain.tsx, CRTSweep.tsx)
- Oracle recommends: single-process async Python, regime-aware weighted ensemble, SSE output
- FlashAlpha has pre-computed GEX/DEX/VEX/CHEX — no raw computation needed
- Massive.com provides raw options chain — must compute GEX manually (nq_atlas.gex does this)
- Unusual Whales has 100+ endpoints documented in skills but ZERO existing client code

### Metis Review
**Identified Gaps** (addressed):
- ~80% of backend is imports from existing modules — plan structured as composition, not rebuild
- Claude call frequency: conditional on material state change (not every 30s) — reduces cost 7-14×
- Unusual Whales has no existing client — phased as Wave 5 (Phase 2)
- 800×800 is tight for "everything" — fixed line budget per section, ASCII mockup required first
- Inter-process communication is HTTP, not shared memory
- PID lock prevents double-launch
- Market hours edge cases (stale data after 4PM, OpEx resets, flash crash override)

---

## Work Objectives

### Core Objective
Build a standalone, continuously-running Python data center + retro 80s terminal UI that synthesizes options market data from 3 sources and displays NQ directional bias in an 800×800 fixed green terminal window. The system maximizes signal quality through multi-source cross-validation, regime-aware weighted ensemble scoring, and conditional Claude interpretation. Signal quality is validated in Task 23 against a fixed historical replay dataset with explicit pass thresholds.

### Concrete Deliverables
- `gex_terminal/` — New top-level directory in DEEP6 repo
- `gex_terminal/engine/` — Python async backend (adapters, analysis, orchestration)
- `gex_terminal/server.py` — FastAPI SSE server
- `gex_terminal/ui/` — Next.js retro terminal app
- Bidirectional HTTP integration with DEEP6 bias engine
- Test suite covering all components

### Definition of Done
- [ ] `python -m gex_terminal` starts backend, serves UI on configured port
- [ ] Browser at `http://localhost:PORT` shows 800×800 terminal with live GEX data
- [ ] All 8+ data sections populate within 60 seconds of startup
- [ ] Claude narrative appears within 90 seconds of startup
- [ ] Source degradation shows `STALE` badges (test with invalid API key)
- [ ] `curl http://localhost:PORT/health` returns source status JSON
- [ ] GEX Doctor pushes data to DEEP6 bias engine and reads back updated bias

### Must Have
- Fixed 800×800 retro green terminal (phosphor green #00FF41 on black #0D0D0D)
- CRT effects (scanlines, subtle glow) — cosmetic, not distracting
- ALL analysis dimensions visible simultaneously: regime, GEX levels, dealer positioning, flow, 0DTE, vanna/charm, Claude narrative, bias verdict + confidence
- 30-second refresh cycle
- Claude API interpretation (conditional on material change)
- FlashAlpha + Massive.com data integration
- Bidirectional DEEP6 bias engine integration
- Source health indicators
- Claude cost tracking visible in UI
- PID lock (prevent double-launch)
- Graceful degradation per source

### Must NOT Have (Guardrails)
- **NO trade execution** — display only, no orders
- **NO charts/graphs** — text and numbers only, this is a terminal
- **NO scrolling** — everything fits in one static frame
- **NO boot animation** — no typing effects, no phosphor decay, no screen jitter
- **NO settings UI** — use .env file for configuration
- **NO alerting** — no Telegram, Discord, email notifications
- **NO persistence** — JSONL audit trail max, no database
- **NO multi-symbol** — NQ only
- **NO API client rewrites** — MUST import from nq_atlas/ (FlashAlpha, Massive, GEX, VannaCharm, Flow)
- **NO variable-height sections** — fixed line count per UI section
- **NO configuration UI** — .env + config.yaml only
- CRT effects budget: ≤ 50 lines of CSS total, ONE task max

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest 8.0+ with asyncio_mode="auto" for Python, vitest for Next.js)
- **Automated tests**: TDD (RED-GREEN-REFACTOR) for Python engine; tests-after for UI components
- **Framework**: pytest (Python), vitest (Next.js)
- **If TDD**: Each task follows RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Backend/API**: Use Bash (curl) — Send requests, assert status + response fields
- **Frontend/UI**: Use Playwright — Navigate, interact, assert DOM, screenshot at 800×800
- **Integration**: Use Bash — Start services, verify health, push/read data
- **Process**: Use Bash — PID lock, graceful shutdown, logging verification

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation + Design — start immediately):
├── Task 1: Project scaffolding + configuration [quick]
├── Task 2: Pydantic data contracts + schemas [quick]
├── Task 3: ASCII layout design mockup (800×800) [visual-engineering]
├── Task 4: Next.js terminal shell + CRT theme [visual-engineering]
└── Task 5: FastAPI app skeleton (health, state, stream) [quick]

Wave 2 (Data Pipeline — needs schemas from Wave 1):
├── Task 6: FlashAlpha polling adapter [quick]
├── Task 7: Massive.com adapter + GEX computation [unspecified-high]
├── Task 8: Analysis engine (regime, levels, dealer, vanna/charm) [deep]
├── Task 9: Claude interpreter (conditional calls, budget tracking) [deep]
└── Task 10: Orchestration loop (30s cycle, snapshot, health) [deep]

Wave 3 (Terminal UI — needs data from Wave 2, layout from Wave 1):
├── Task 11: Verdict + Regime panel [visual-engineering]
├── Task 12: Levels panel (flip, walls, magnet, 0DTE) [visual-engineering]
├── Task 13: Analysis panels (dealer, flow, vanna/charm) [visual-engineering]
├── Task 14: Narrative panel (Claude's interpretation) [visual-engineering]
├── Task 15: Status footer (health, cost, refresh timer) [visual-engineering]
└── Task 16: SSE integration + real-time store [unspecified-high]

Wave 4 (Integration + Hardening — needs Wave 3):
├── Task 17: DEEP6 bidirectional bridge [deep]
├── Task 18: Source degradation + edge cases [unspecified-high]
├── Task 19: Process management (PID lock, shutdown, logging) [quick]
└── Task 20: Launch script + startup orchestration [quick]

Wave 5 (Unusual Whales + Validation — Phase 2, needs Wave 4):
├── Task 21: UW API client (greenfield async httpx) [unspecified-high]
├── Task 22: UW dark pool data + terminal integration [deep]
└── Task 23: Signal quality validation (replay dataset) [deep]

Wave FINAL (Verification — after ALL tasks):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high + playwright)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 5, 6, 7, 8, 9, 10 | 1 |
| 2 | — | 6, 7, 8, 9, 10, 16, 17 | 1 |
| 3 | — | 4, 11, 12, 13, 14, 15 | 1 |
| 4 | 3 | 11, 12, 13, 14, 15 | 1 |
| 5 | 1 | 10, 16 | 1 |
| 6 | 1, 2 | 10 | 2 |
| 7 | 1, 2 | 10 | 2 |
| 8 | 1, 2 | 10, 23 | 2 |
| 9 | 1, 2 | 10 | 2 |
| 10 | 5, 6, 7, 8, 9 | 16, 17, 18 | 2 |
| 11 | 3, 4 | 16 | 3 |
| 12 | 3, 4 | 16 | 3 |
| 13 | 3, 4 | 16 | 3 |
| 14 | 3, 4 | 16 | 3 |
| 15 | 3, 4 | 16 | 3 |
| 16 | 5, 10, 11-15 | 17b, 18 | 3 |
| 17 | 2, 10 | 17b | 4 |
| 17b | 2, 10, 16, 17 | 18 | 4 |
| 18 | 10, 16, 17b | 19, 20 | 4 |
| 19 | 10 | 20 | 4 |
| 20 | 17b, 18, 19 | 21 | 4 |
| 21 | 1, 2 | 22 | 5 |
| 22 | 10, 16, 21 | F1-F4 | 5 |
| 23 | 8 | F1-F4 | 5 |

### Agent Dispatch Summary

- **Wave 1**: 5 tasks — T1 → `quick`, T2 → `quick`, T3 → `visual-engineering`, T4 → `visual-engineering`, T5 → `quick`
- **Wave 2**: 5 tasks — T6 → `quick`, T7 → `unspecified-high`, T8 → `deep`, T9 → `deep`, T10 → `deep`
- **Wave 3**: 6 tasks — T11-T15 → `visual-engineering`, T16 → `unspecified-high`
- **Wave 4**: 5 tasks — T17 → `quick`, T17b → `deep`, T18 → `unspecified-high`, T19 → `quick`, T20 → `quick`
- **Wave 5**: 3 tasks — T21 → `unspecified-high`, T22 → `deep`, T23 → `deep`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

Critical Path: T1 → T6 → T10 → T16 → T17 → T17b → T20 → T22 → T23 → F1-F4 → user okay
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 6 (Wave 3)

---

## TODOs

- [x] 1. Project Scaffolding + Configuration

  **What to do**:
  - Create `gex_terminal/` directory at DEEP6 root with proper Python package structure
  - Create `gex_terminal/__init__.py`, `gex_terminal/__main__.py` (entry point)
  - Create `gex_terminal/config.py` — Pydantic BaseSettings with `GEX_TERMINAL_` env prefix
  - Config fields: `flashalpha_api_key`, `massive_api_key`, `uw_api_key`, `anthropic_api_key`, `refresh_interval_sec=30`, `server_port=8780`, `deep6_bias_url=http://localhost:8765`, `claude_model=claude-haiku-4-5-20251001`, `claude_budget_daily_usd=10.0`, `log_level=INFO`
  - Create `.env.gex_terminal.example` with all fields documented
  - Create `gex_terminal/requirements.txt` referencing nq_atlas and local dependencies
  - Add `gex_terminal/tests/__init__.py`
  - Follow pattern from `nq_atlas/config.py` and `gexdoctor/config.yaml`

  **Must NOT do**:
  - Do NOT create a separate virtual environment — uses DEEP6's main env
  - Do NOT add dependencies that duplicate what nq_atlas already provides

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Reason: Standard scaffolding, no domain knowledge needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 2, 5, 6, 7, 8, 9, 10
  - **Blocked By**: None

  **References**:
  - `nq_atlas/config.py` — Pydantic BaseSettings pattern with env prefix, field validators, .env loading
  - `nq_atlas/__init__.py` — Package init pattern
  - `gexdoctor/config.yaml` — Alternative YAML config pattern (we use Pydantic BaseSettings instead)
  - `gexdoctor/.env.gexdoctor.example` — .env template format

  **Acceptance Criteria**:
  - [ ] `python -c "from gex_terminal.config import Settings; s = Settings(); print(s.server_port)"` prints `8780`
  - [ ] `python -m gex_terminal --help` shows usage (or starts with default config)

  **QA Scenarios**:
  ```
  Scenario: Config loads with defaults
    Tool: Bash
    Preconditions: No .env file present
    Steps:
      1. Run: python -c "from gex_terminal.config import Settings; s = Settings(); print(s.server_port, s.refresh_interval_sec, s.claude_model)"
      2. Assert output contains: 8780 30 claude-haiku-4-5-20251001
    Expected Result: All defaults load correctly
    Failure Indicators: ImportError or missing default values
    Evidence: .sisyphus/evidence/task-1-config-defaults.txt

  Scenario: Config validates missing required keys
    Tool: Bash
    Preconditions: No env vars or .env file for API keys
    Steps:
      1. Run: python -c "from gex_terminal.config import Settings; s = Settings()" with no API key env vars
      2. Assert: Should load (API keys can be empty for development — adapters handle missing keys)
    Expected Result: Config loads without error; API keys default to empty string
    Evidence: .sisyphus/evidence/task-1-config-missing-keys.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(gex-terminal): scaffold project, schemas, layout mockup`
  - Files: `gex_terminal/__init__.py`, `gex_terminal/__main__.py`, `gex_terminal/config.py`, `.env.gex_terminal.example`
  - Pre-commit: `python -c "from gex_terminal.config import Settings"`

- [x] 2. Pydantic Data Contracts + Schemas

  **What to do**:
  - Create `gex_terminal/schemas.py` with all data contracts for the system
  - `SourceHealth` — per-source status: `name`, `status` (ok/stale/error/pending), `last_update`, `ttl_sec`, `error_msg`
  - `GEXLevels` — `gamma_flip`, `call_wall`, `put_wall`, `hvl`, `zero_dte_magnet`, `expected_move_up`, `expected_move_down`
  - `DealerPositioning` — `net_gex`, `net_dex`, `net_vex`, `net_chex`, `regime` (positive/negative/neutral), `hedge_direction`
  - `FlowSummary` — `direction` (bullish/bearish/neutral), `intensity`, `sweep_count`, `block_count`, `z_score`
  - `VannaCharmState` — `vanna_exposure`, `charm_exposure`, `net_hedge_direction`
  - `ZeroDTEState` — `gex_pct_of_total`, `pin_risk`, `gamma_acceleration`
  - `ClaudeNarrative` — `text` (≤240 chars), `model`, `timestamp`, `cached` (bool), `cost_usd`
  - `BiasVerdict` — `direction` (BULLISH/BEARISH/NEUTRAL), `confidence` (0-100), `grade` (A+/A/B/C/F), `regime_name`
  - `GEXTerminalSnapshot` — Immutable top-level: `timestamp`, `bias`, `levels`, `dealer`, `flow`, `vanna_charm`, `zero_dte`, `narrative`, `sources: dict[str, SourceHealth]`, `deep6_bias_score` (from bidirectional), `cost_today_usd`
  - `GEXDoctorPayload` — Pydantic model pushed TO DEEP6 bias engine via POST /api/gex/ingest. Fields match `DomainScore` exactly: `domain: str`, `score: int`, `max_range: int = 3`, `available: bool`, `stale: bool`, `detail: dict`, `updated_at: float` (Unix timestamp)
  - All models: frozen Pydantic BaseModel, `model_config = ConfigDict(frozen=True)`

  **Must NOT do**:
  - Do NOT duplicate types that exist in `nq_atlas/types.py` — import and extend where possible
  - Do NOT add optional fields without defaults

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Reason: Schema definition is straightforward data modeling

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5)
  - **Blocks**: Tasks 6, 7, 8, 9, 10, 16, 17
  - **Blocked By**: None

  **References**:
  - `nq_atlas/types.py` — Existing Pydantic schemas: `GEXResult`, `VannaCharmResult`, `FlowResult`, `ChainSnapshot`
  - `deep6/engines/bias_contracts.py` — `DomainScore`, `BiasState`, `BiasMode`, `MarketBiasSnapshot` — MUST match for bidirectional integration
  - `gexdoctor/monitor/schemas.py` — Existing schemas: `FADealerRisk`, `FAFeedQuality`, `FARegime`, `FlashAlphaSnapshot`
  - `deep6/bias_engine/models.py` — Bias engine data models

  **Acceptance Criteria**:
  - [ ] `python -c "from gex_terminal.schemas import GEXTerminalSnapshot; print(GEXTerminalSnapshot.model_fields.keys())"` lists all fields
  - [ ] All schemas are frozen (immutable)
  - [ ] `GEXDoctorPayload` has fields: `domain:str`, `score:int`, `max_range:int`, `available:bool`, `stale:bool`, `detail:dict`, `updated_at:float` — matching `DomainScore` exactly

  **QA Scenarios**:
  ```
  Scenario: Schemas are frozen and serializable
    Tool: Bash
    Preconditions: gex_terminal package importable
    Steps:
      1. Run: python -c "from gex_terminal.schemas import BiasVerdict; v = BiasVerdict(direction='BULLISH', confidence=85, grade='A', regime_name='Positive Between'); print(v.model_dump_json())"
      2. Assert output is valid JSON containing: "direction", "confidence", "grade", "regime_name"
      3. Run: python -c "
from gex_terminal.schemas import BiasVerdict
from pydantic import ValidationError
v = BiasVerdict(direction='BULLISH', confidence=85, grade='A', regime_name='test')
try:
    v.confidence = 90
    print('FAIL: mutation allowed')
except (ValidationError, TypeError):
    print('PASS: frozen model')
"
      4. Assert: output is "PASS: frozen model"
    Expected Result: JSON serialization works; mutation raises error
    Evidence: .sisyphus/evidence/task-2-schemas-frozen.txt

  Scenario: GEXDoctorPayload conforms to DomainScore interface
    Tool: Bash
    Preconditions: Both gex_terminal and deep6 packages importable
    Steps:
      1. Run: python -c "
from deep6.engines.bias_contracts import DomainScore
import dataclasses
fields = {(f.name, f.type) for f in dataclasses.fields(DomainScore)}
print('DomainScore fields:', sorted(f[0] for f in fields))
# Expected: ['available', 'detail', 'domain', 'max_range', 'score', 'stale', 'updated_at']
"
      2. Assert: output contains all 7 field names
      3. Run: python -c "
from gex_terminal.schemas import GEXDoctorPayload
import pydantic
fields = GEXDoctorPayload.model_fields
required = {'domain', 'score', 'max_range', 'available', 'stale', 'detail', 'updated_at'}
missing = required - set(fields.keys())
type_issues = []
if fields.get('score') and 'int' not in str(fields['score'].annotation): type_issues.append('score must be int')
if fields.get('max_range') and 'int' not in str(fields['max_range'].annotation): type_issues.append('max_range must be int')
if fields.get('updated_at') and 'float' not in str(fields['updated_at'].annotation): type_issues.append('updated_at must be float')
print('Missing:', missing if missing else 'NONE')
print('Type issues:', type_issues if type_issues else 'NONE')
"
      4. Assert: both outputs show "NONE"
    Expected Result: GEXDoctorPayload has all required DomainScore fields with correct types (score:int, max_range:int, updated_at:float)
    Evidence: .sisyphus/evidence/task-2-domain-score-compat.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(gex-terminal): scaffold project, schemas, layout mockup`
  - Files: `gex_terminal/schemas.py`
  - Pre-commit: `python -c "from gex_terminal.schemas import GEXTerminalSnapshot"`

- [x] 3. ASCII Layout Design Mockup (800×800)

  **What to do**:
  - Design the complete terminal layout as an ASCII mockup in `gex_terminal/docs/LAYOUT.md`
  - 800×800 CSS pixels at 11px JetBrains Mono ≈ 96 columns × 55 rows (accounting for line-height 1.4)
  - **Fixed line budget per section** — NO variable-height sections:
    - Header (2 lines): Title + timestamp + connection status
    - Verdict (4 lines): BULLISH/BEARISH in large ASCII art, confidence bar, regime badge
    - Levels (6 lines): Gamma flip, call wall, put wall, HVL, 0DTE magnet, expected move
    - Dealer (4 lines): Net GEX/DEX/VEX/CHEX with regime indicator
    - Flow (3 lines): Direction, intensity bar, sweep/block counts
    - Vanna/Charm (2 lines): Exposures + hedge direction
    - 0DTE (2 lines): GEX %, pin risk, gamma acceleration
    - Narrative (3 lines): Claude's 240-char interpretation
    - DEEP6 Bias (2 lines): Score from bidirectional integration
    - Footer (2 lines): Source health dots, cost tracker, refresh countdown
    - Separator lines: ~5 lines
    - **Total: ~35 lines** — fits within 55-line budget with breathing room
  - Use box-drawing characters: `╔═╗║╚═╝╠╣╦╩╬─│┌┐└┘├┤┬┴┼`
  - Show exact character positions for all data fields
  - Include color annotations (bright green, dim green, red, amber)
  - Create 3 mockup states: BULLISH, BEARISH, DEGRADED (source failure)

  **Must NOT do**:
  - Do NOT include any charts, sparklines, or graphical elements
  - Do NOT use more than 96 columns width
  - Do NOT allow any section to exceed its allocated line count

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []
  - Reason: Layout design requires visual thinking and information hierarchy expertise

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: Tasks 4, 11, 12, 13, 14, 15
  - **Blocked By**: None

  **References**:
  - `dashboard/app/globals.css` — Existing design tokens, neon palette, spacing system
  - `dashboard/components/layout/HeaderStrip.tsx` — Information density patterns (price, bias, regime, clock in 44px)
  - `dashboard/components/score/ConfluencePulse.tsx` — How to condense complex scoring into compact visual
  - `gexdoctor/brain/flashalpha_knowledge.yaml` — Regime names, field names for levels/flow/dealer sections

  **Acceptance Criteria**:
  - [ ] `LAYOUT.md` contains 3 complete ASCII mockups (BULLISH, BEARISH, DEGRADED)
  - [ ] Each mockup is exactly 96 chars wide
  - [ ] Total line count ≤ 55 per mockup
  - [ ] Every data field has a labeled position

  **QA Scenarios**:
  ```
  Scenario: Layout fits 800×800 at 11px font
    Tool: Bash
    Preconditions: LAYOUT.md exists
    Steps:
      1. Read gex_terminal/docs/LAYOUT.md
      2. Count: max line length across all mockups (must be ≤ 96 chars)
      3. Count: max number of lines in any single mockup (must be ≤ 55)
      4. Verify all 8 sections are present: header, verdict, levels, dealer, flow, vanna/charm, narrative, footer
    Expected Result: Layout fits within 96×55 character budget
    Failure Indicators: Any line > 96 chars or mockup > 55 lines
    Evidence: .sisyphus/evidence/task-3-layout-dimensions.txt

  Scenario: Three states documented
    Tool: Bash
    Preconditions: LAYOUT.md exists
    Steps:
      1. Grep for "BULLISH", "BEARISH", "DEGRADED" in LAYOUT.md
      2. Assert all 3 states have complete mockups
    Expected Result: 3 distinct mockup states present
    Evidence: .sisyphus/evidence/task-3-layout-states.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(gex-terminal): scaffold project, schemas, layout mockup`
  - Files: `gex_terminal/docs/LAYOUT.md`

- [x] 4. Next.js Terminal Shell + CRT Green Theme

  **What to do**:
  - Create `gex_terminal/ui/` as a minimal Next.js app (App Router)
  - `package.json` with: Next.js 16, React 19, Tailwind 4, afterglow-crt
  - `app/layout.tsx` — Root layout: fixed 800×800 viewport, JetBrains Mono font, phosphor green theme
  - `app/page.tsx` — Single page with terminal container, scanline overlay, vignette effect
  - `app/globals.css` — Green terminal design tokens:
    - `--terminal-green: #00FF41`, `--terminal-dim: #00AA00`, `--terminal-dark: #006600`
    - `--terminal-bg: #0D0D0D`, `--terminal-border: #00FF41`
    - `--terminal-red: #FF4444` (bearish), `--terminal-amber: #FFB000` (warning)
    - Scanlines (CSS gradient, 2px spacing, 0.3 opacity)
    - Text glow: `text-shadow: 0 0 8px #00FF41`
    - Vignette: radial-gradient edge fade
    - Box-shadow glow on terminal border
  - `components/TerminalFrame.tsx` — The outer "CRT monitor" frame with border glow + scanlines
  - Fixed window size: `<meta name="viewport" content="width=800, initial-scale=1">` or CSS `width: 800px; height: 800px`
  - CRT effects: scanlines + subtle border glow ONLY. No flicker, no typing effects, no boot animation.
  - Total CRT CSS: ≤ 50 lines

  **Must NOT do**:
  - Do NOT add screen flicker or jitter animations
  - Do NOT add typing/typewriter effects
  - Do NOT add boot sequence
  - Do NOT exceed 50 lines of CRT-specific CSS
  - Do NOT copy full dashboard design system — this is a SEPARATE green monochrome theme

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []
  - Reason: CRT aesthetic requires visual design expertise

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5)
  - **Blocks**: Tasks 11, 12, 13, 14, 15
  - **Blocked By**: Task 3 (needs layout mockup to structure the page)

  **References**:
  - `dashboard/app/globals.css` — Existing design tokens pattern (don't copy — adapt for green monochrome)
  - `dashboard/components/atmosphere/Scanlines.tsx` — CRT scanline implementation (can reference but NOT copy — different aesthetic)
  - `dashboard/app/layout.tsx` — JetBrains Mono font loading pattern

  **Acceptance Criteria**:
  - [ ] `npm run dev` in `gex_terminal/ui/` serves the app
  - [ ] Browser shows 800×800 green terminal frame with scanlines
  - [ ] No scrollbars visible
  - [ ] CRT CSS ≤ 50 lines

  **QA Scenarios**:
  ```
  Scenario: Terminal renders at 800×800
    Tool: Playwright
    Preconditions: Next.js dev server running on configured port
    Steps:
      1. Navigate to http://localhost:3001
      2. Set viewport: page.setViewportSize({width: 800, height: 800})
      3. Assert: document.querySelector('.terminal-frame') exists
      4. Assert: computed background-color of body is rgb(13, 13, 13)
      5. Assert: computed color of .terminal-frame contains green (rgb(0, 255, 65))
      6. Assert: no scrollbar visible (document.documentElement.scrollHeight <= 800)
      7. Screenshot
    Expected Result: Green terminal frame on dark background, no overflow
    Evidence: .sisyphus/evidence/task-4-terminal-800x800.png

  Scenario: Scanlines visible
    Tool: Playwright
    Preconditions: Dev server running
    Steps:
      1. Navigate to http://localhost:3001
      2. Assert: element with class containing 'scanline' or pseudo-element with repeating-linear-gradient
      3. Screenshot at 2× resolution to see scanline detail
    Expected Result: Horizontal scanline effect visible
    Evidence: .sisyphus/evidence/task-4-scanlines.png
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(gex-terminal): scaffold project, schemas, layout mockup`
  - Files: `gex_terminal/ui/package.json`, `gex_terminal/ui/app/layout.tsx`, `gex_terminal/ui/app/page.tsx`, `gex_terminal/ui/app/globals.css`

- [x] 5. FastAPI App Skeleton

  **What to do**:
  - Create `gex_terminal/server.py` — FastAPI application with lifespan context manager
  - Endpoints:
    - `GET /health` — Returns `{"status": "ok", "sources": {...}, "uptime_sec": N}`
    - `GET /state` — Returns current `GEXTerminalSnapshot` as JSON
    - `GET /stream` — SSE endpoint streaming snapshots every 30s (EventSource compatible)
  - Follow pattern from `nq_atlas/server.py` for SSE streaming
  - CORS middleware (allow localhost origins)
  - Uvicorn startup in `__main__.py`: `uvicorn.run("gex_terminal.server:app", port=settings.server_port)`
  - Health check returns per-source status from orchestrator (stubbed until Task 10)
  - SSE uses `StreamingResponse` with `text/event-stream` media type

  **Must NOT do**:
  - Do NOT add WebSocket — SSE is sufficient for this use case
  - Do NOT add authentication — local-only service
  - Do NOT add database or persistence endpoints

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Reason: Standard FastAPI boilerplate following existing pattern

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4)
  - **Blocks**: Tasks 10, 16
  - **Blocked By**: Task 1 (needs config)

  **References**:
  - `nq_atlas/server.py` — FastAPI SSE streaming pattern: `StreamingResponse`, `asyncio.Event`, state broadcast
  - `deep6/api/app.py` — FastAPI app factory with lifespan, CORS middleware
  - `nq_atlas/config.py` — Settings loading pattern

  **Acceptance Criteria**:
  - [ ] `python -m gex_terminal` starts server on port 8780
  - [ ] `curl http://localhost:8780/health` returns JSON with status field
  - [ ] `curl -N http://localhost:8780/stream` receives `data:` events

  **QA Scenarios**:
  ```
  Scenario: Health endpoint returns valid JSON
    Tool: Bash (curl)
    Preconditions: gex_terminal server running
    Steps:
      1. Run: curl -s http://localhost:8780/health | python -m json.tool
      2. Assert: JSON has "status" key with value "ok" or "degraded"
      3. Assert: JSON has "sources" key (dict)
      4. Assert: JSON has "uptime_sec" key (number >= 0)
    Expected Result: Valid health response with all required fields
    Evidence: .sisyphus/evidence/task-5-health-endpoint.json

  Scenario: SSE stream emits events
    Tool: Bash (curl)
    Preconditions: Server running
    Steps:
      1. Run: timeout 10 curl -N -s http://localhost:8780/stream | head -5
      2. Assert: output contains "data:" prefix
      3. Assert: data is valid JSON
    Expected Result: SSE events streaming
    Evidence: .sisyphus/evidence/task-5-sse-stream.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(gex-terminal): scaffold project, schemas, layout mockup`
  - Files: `gex_terminal/server.py`
  - Pre-commit: `python -c "from gex_terminal.server import app"`

- [x] 6. FlashAlpha Polling Adapter

  **What to do**:
  - Create `gex_terminal/engine/adapters/flashalpha.py`
  - IMPORT existing `nq_atlas.flashalpha_client.FlashAlphaClient` — do NOT rewrite
  - Wrap in a thin adapter that:
    - Polls 5 endpoints every 30s: `exposure_summary`, `exposure_levels`, `zero_dte`, `vex`, `chex`
    - Normalizes responses into `gex_terminal.schemas` types (GEXLevels, DealerPositioning, ZeroDTEState)
    - Tracks source health (last_update timestamp, error count, stale detection)
    - Handles errors gracefully: log, mark source as STALE, return last-known data
    - Emits `SourceHealth` on every poll cycle
  - Symbol: QQQ (hardcoded — NQ proxy via nq_mapper)
  - Use `nq_atlas.nq_mapper` for QQQ→NQ level conversion
  - TDD: Write tests first in `gex_terminal/tests/test_flashalpha_adapter.py`

  **Must NOT do**:
  - Do NOT rewrite the FlashAlpha API client — IMPORT from nq_atlas
  - Do NOT hardcode NQ/QQQ conversion ratios — use nq_mapper
  - Do NOT call all endpoints sequentially — use asyncio.gather for parallel polling

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`flashalpha-options`]
  - `flashalpha-options`: API reference for endpoint signatures and response formats

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `nq_atlas/flashalpha_client.py` — Existing FlashAlpha SDK wrapper: `FlashAlphaClient` class, sync SDK via executor
  - `nq_atlas/nq_mapper.py` — QQQ→NQ level conversion logic
  - `gexdoctor/monitor/adapters/flashalpha.py` — 338-line production adapter with polling, fallback, feed quality — reference pattern
  - `.claude/skills/flashalpha-options/api-reference.md` — FlashAlpha endpoint signatures

  **Acceptance Criteria**:
  - [ ] Tests: `pytest gex_terminal/tests/test_flashalpha_adapter.py -v` → PASS
  - [ ] Adapter imports `FlashAlphaClient` from `nq_atlas.flashalpha_client` (verified by grep)
  - [ ] Returns `GEXLevels`, `DealerPositioning`, `ZeroDTEState`, `SourceHealth`

  **QA Scenarios**:
  ```
  Scenario: Adapter polls and normalizes FlashAlpha data
    Tool: Bash
    Preconditions: Valid FLASHALPHA_API_KEY in environment
    Steps:
      1. Run: python -c "import asyncio; from gex_terminal.engine.adapters.flashalpha import FlashAlphaAdapter; a = FlashAlphaAdapter(); result = asyncio.run(a.poll()); print(result)"
      2. Assert: result contains GEXLevels with gamma_flip, call_wall, put_wall values > 0
      3. Assert: result contains SourceHealth with status='ok'
    Expected Result: Live data fetched and normalized
    Evidence: .sisyphus/evidence/task-6-flashalpha-poll.json

  Scenario: Adapter degrades gracefully with invalid key
    Tool: Bash
    Preconditions: FLASHALPHA_API_KEY set to "invalid_key"
    Steps:
      1. Run: python -c "import asyncio; from gex_terminal.engine.adapters.flashalpha import FlashAlphaAdapter; a = FlashAlphaAdapter(); result = asyncio.run(a.poll()); print(result.source_health)"
      2. Assert: SourceHealth.status is 'error' and error_msg is non-empty
    Expected Result: Graceful failure with error status
    Evidence: .sisyphus/evidence/task-6-flashalpha-degraded.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `feat(gex-terminal): data pipeline + orchestration loop`
  - Files: `gex_terminal/engine/adapters/flashalpha.py`, `gex_terminal/tests/test_flashalpha_adapter.py`

- [x] 7. Massive.com Adapter + GEX Computation

  **What to do**:
  - Create `gex_terminal/engine/adapters/massive.py`
  - IMPORT existing `nq_atlas.massive_client.MassiveClient` — do NOT rewrite
  - IMPORT existing `nq_atlas.gex.GEXEngine` — for computing GEX from raw chain data
  - Adapter wraps MassiveClient to:
    - Fetch QQQ options chain snapshot every 30s
    - Feed chain into GEXEngine to compute net GEX, flip, walls (cross-validates FlashAlpha)
    - Track source health
    - Handle Massive API errors/timeouts gracefully
  - The computed GEX from Massive serves as INDEPENDENT CROSS-VALIDATION of FlashAlpha's pre-computed values
  - TDD: Write tests in `gex_terminal/tests/test_massive_adapter.py`

  **Must NOT do**:
  - Do NOT rewrite MassiveClient or GEXEngine — IMPORT from nq_atlas
  - Do NOT duplicate NQ conversion — use nq_mapper

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nq-options-algo-engine/data-sources/massive-api`]
  - Reason: Massive API has more complexity than FlashAlpha; needs careful error handling

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `nq_atlas/massive_client.py` — MassiveClient: async httpx, retry, pagination, NQ quote, 298 lines
  - `nq_atlas/gex.py` — GEXEngine: net GEX, flip, walls, regime, expiry buckets
  - `scripts/massive_gex_map_service_v2.py` — Gamma Decision Surface V2 reference (1,380 lines)
  - `.claude/skills/nq-options-algo-engine/data-sources/massive-api.md` — Massive API reference

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_massive_adapter.py -v`
  - [ ] Adapter imports from nq_atlas (no rewrites)
  - [ ] Produces GEXLevels that can be compared with FlashAlpha's values

  **QA Scenarios**:
  ```
  Scenario: Massive adapter computes GEX from chain
    Tool: Bash
    Preconditions: Valid MASSIVE_API_KEY in environment
    Steps:
      1. Run: python -c "import asyncio; from gex_terminal.engine.adapters.massive import MassiveAdapter; a = MassiveAdapter(); result = asyncio.run(a.poll()); print(f'Flip: {result.levels.gamma_flip}, Wall: {result.levels.call_wall}')"
      2. Assert: gamma_flip and call_wall are reasonable NQ price levels (15000-25000 range)
    Expected Result: GEX computed from raw chain data
    Evidence: .sisyphus/evidence/task-7-massive-gex.json

  Scenario: Massive adapter handles API timeout
    Tool: Bash
    Preconditions: MASSIVE_API_KEY set to "invalid"
    Steps:
      1. Run adapter poll with invalid key
      2. Assert: SourceHealth.status is 'error', no crash
    Expected Result: Graceful degradation
    Evidence: .sisyphus/evidence/task-7-massive-error.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `feat(gex-terminal): data pipeline + orchestration loop`
  - Files: `gex_terminal/engine/adapters/massive.py`, `gex_terminal/tests/test_massive_adapter.py`

- [x] 8. Analysis Engine (Regime, Levels, Dealer, Vanna/Charm)

  **What to do**:
  - Create `gex_terminal/engine/analyzer.py`
  - IMPORT and compose existing engines:
    - `nq_atlas.gex.GEXEngine` → regime classification
    - `nq_atlas.vanna_charm.VannaCharmEngine` → dealer vanna/charm exposure
    - `nq_atlas.flow.FlowEngine` → flow direction and intensity
    - `gexdoctor.monitor.magnet_scorer.MagnetScorer` → magnet level selection
  - `GEXAnalyzer` class that takes raw adapter outputs and produces:
    - `BiasVerdict` — synthesized directional bias with confidence
    - `DealerPositioning` — aggregated dealer state
    - `VannaCharmState` — exposure summaries
    - `FlowSummary` — flow direction and intensity
  - Implement regime-aware weighted ensemble (from Oracle consultation):
    - `effective_weight = base_weight × regime_factor × freshness × source_health`
    - Family caps: prevent correlated GEX features from dominating
    - Separate bias (direction) from confidence (conviction)
  - Detect material state change (for conditional Claude calls)
  - TDD: `gex_terminal/tests/test_analyzer.py`

  **Must NOT do**:
  - Do NOT rewrite GEXEngine, VannaCharmEngine, FlowEngine, MagnetScorer
  - Do NOT create a new regime classification system — use existing
  - Do NOT hard-code weights — make them configurable in Settings

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`options-bias-engine/knowledge`, `nq-options-algo-engine/algo-patterns/composite-scoring`]
  - Reason: Synthesizing multiple analytical models requires deep domain expertise

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `nq_atlas/gex.py` — GEXEngine: compute_gex(), net GEX, flip, regime
  - `nq_atlas/vanna_charm.py` — VannaCharmEngine: compute(), dealer exposure
  - `nq_atlas/flow.py` — FlowEngine: classify(), z-score, Lee-Ready
  - `gexdoctor/monitor/magnet_scorer.py` — MagnetScorer: 6-candidate scoring, anti-flicker
  - `deep6/engines/gex_options_domain.py` — GEX→bias domain adapter: scores -3..+3 (197 lines)
  - `deep6/engines/bias_composer.py` — 5-domain synthesis pattern
  - `.claude/skills/options-bias-engine/step4-cross-validation/conviction-matrix.md` — 5-river conviction scoring

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_analyzer.py -v`
  - [ ] Produces BiasVerdict with direction + confidence from mock data
  - [ ] Material change detection works (returns True when regime flips)

  **QA Scenarios**:
  ```
  Scenario: Analyzer produces verdict from mock data
    Tool: Bash
    Preconditions: Test fixtures with mock GEX/flow/vanna data
    Steps:
      1. Run: pytest gex_terminal/tests/test_analyzer.py::test_bullish_verdict -v
      2. Assert: BiasVerdict.direction == 'BULLISH', confidence > 60
      3. Run: pytest gex_terminal/tests/test_analyzer.py::test_bearish_verdict -v
      4. Assert: BiasVerdict.direction == 'BEARISH', confidence > 60
    Expected Result: Correct directional verdicts from mock data
    Evidence: .sisyphus/evidence/task-8-analyzer-verdicts.txt

  Scenario: Material change detection
    Tool: Bash
    Steps:
      1. Run test: pytest gex_terminal/tests/test_analyzer.py::test_material_change -v
      2. Assert: regime flip triggers material_change=True
      3. Assert: minor value fluctuation triggers material_change=False
    Expected Result: Only significant changes trigger Claude calls
    Evidence: .sisyphus/evidence/task-8-material-change.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `feat(gex-terminal): data pipeline + orchestration loop`
  - Files: `gex_terminal/engine/analyzer.py`, `gex_terminal/tests/test_analyzer.py`

- [x] 9. Claude Interpreter (Conditional Calls, Budget Tracking)

  **What to do**:
  - Create `gex_terminal/engine/interpreter.py`
  - IMPORT existing `nq_atlas.ai_bias.BiasInterpreter` for Claude API call pattern
  - IMPORT existing `deep6.copilot.budget.BudgetTracker` for cost tracking
  - `ClaudeInterpreter` class:
    - Calls Claude API ONLY when `material_change=True` (from analyzer)
    - Default model: `claude-haiku-4-5-20251001` (cheapest, adequate for structured interpretation)
    - System prompt: adapted from `gexdoctor/brain/flashalpha_interpreter.md`
    - Output: `ClaudeNarrative` (≤240 chars, structured interpretation)
    - Budget enforcement: if daily spend > $10, reduce to 5-minute intervals
    - Logs every call to `~/.deep6/gexdoctor_v2_usage.jsonl`
    - On API error: return last cached narrative with `cached=True`
    - On rate limit (429): exponential backoff, use cached
  - Prompt structure: inject current GEXTerminalSnapshot as JSON, ask for 3-line interpretation
  - TDD: `gex_terminal/tests/test_interpreter.py` (mock Claude API)

  **Must NOT do**:
  - Do NOT call Claude on every 30s tick — ONLY on material change
  - Do NOT use Opus (too expensive at this frequency)
  - Do NOT embed API key in code — use Settings.anthropic_api_key

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`options-bias-engine/step7-output/narrative-guidelines`]
  - Reason: Prompt engineering + cost management requires careful design

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `nq_atlas/ai_bias.py` — BiasInterpreter: Claude API call pattern, prompt building, interpret loop
  - `deep6/copilot/budget.py` — BudgetTracker: token counting, cost logging, throttling at 80%
  - `deep6/bias_engine/claude_synth.py` — Three-agent consensus, prompt caching pattern
  - `gexdoctor/brain/flashalpha_interpreter.md` — System prompt for GEX interpretation
  - `gexdoctor/brain/flashalpha_knowledge.yaml` — Regime playbook, heuristics, modifiers

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_interpreter.py -v`
  - [ ] Claude is called ONLY when material_change=True (verified in test)
  - [ ] Budget tracking logs to JSONL file
  - [ ] Narrative ≤ 240 characters

  **QA Scenarios**:
  ```
  Scenario: Conditional Claude calling
    Tool: Bash
    Steps:
      1. Run test: pytest gex_terminal/tests/test_interpreter.py::test_conditional_call -v
      2. Assert: mock Claude API called exactly once for material change
      3. Assert: mock Claude API NOT called for non-material change (returns cached)
    Expected Result: Claude API calls are conditional
    Evidence: .sisyphus/evidence/task-9-conditional-calls.txt

  Scenario: Budget enforcement
    Tool: Bash
    Steps:
      1. Run test: pytest gex_terminal/tests/test_interpreter.py::test_budget_enforcement -v
      2. Assert: when daily spend > $10, interpreter.should_call returns False
    Expected Result: Budget ceiling enforced
    Evidence: .sisyphus/evidence/task-9-budget-enforcement.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `feat(gex-terminal): data pipeline + orchestration loop`
  - Files: `gex_terminal/engine/interpreter.py`, `gex_terminal/tests/test_interpreter.py`

- [x] 10. Orchestration Loop (30s Cycle, Snapshot, Health)

  **What to do**:
  - Create `gex_terminal/engine/orchestrator.py`
  - `GEXOrchestrator` class — the main engine loop:
    - Every 30 seconds: poll all adapters in parallel (`asyncio.gather`)
    - Stagger initial fetches: FlashAlpha T+0, Massive T+5s, UW T+10s (prevents thundering herd at market open)
    - Feed adapter results into `GEXAnalyzer`
    - If material change detected → call `ClaudeInterpreter`
    - Build immutable `GEXTerminalSnapshot` from all results
    - Push snapshot to SSE subscribers
    - Update source health map
    - Track daily cost
  - Follow pattern from `nq_atlas/orchestrator.py` and `gexdoctor/monitor/producer.py`
  - Graceful degradation: if one source fails, continue with remaining sources + stale badge
  - Market hours awareness: during extended hours (4PM-9:30AM), show STALE badge on GEX data
  - TDD: `gex_terminal/tests/test_orchestrator.py`

  **Must NOT do**:
  - Do NOT poll sources sequentially — use asyncio.gather
  - Do NOT crash if one source fails — degrade gracefully
  - Do NOT call Claude every cycle — only on material change

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nq-options-algo-engine/implementation/async-pipeline`]
  - Reason: Core orchestration logic requires careful async design + error handling

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after Wave 2 adapters)
  - **Blocks**: Tasks 16, 17, 18
  - **Blocked By**: Tasks 5, 6, 7, 8, 9

  **References**:
  - `nq_atlas/orchestrator.py` — Async compute loop pattern: GEX → vanna/charm → flow → mapper
  - `gexdoctor/monitor/producer.py` — Enhanced gex_producer orchestration loop pattern
  - `nq_atlas/state.py` — AtlasState: shared mutable container, degradation detection

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_orchestrator.py -v`
  - [ ] Orchestrator polls all adapters in parallel (verified in test with mock adapters)
  - [ ] Produces GEXTerminalSnapshot on each cycle
  - [ ] Handles source failures without crash

  **QA Scenarios**:
  ```
  Scenario: Full orchestration cycle with mock adapters
    Tool: Bash
    Steps:
      1. Run: pytest gex_terminal/tests/test_orchestrator.py::test_full_cycle -v
      2. Assert: GEXTerminalSnapshot produced with all sections populated
      3. Assert: cycle completes in < 15 seconds
    Expected Result: Complete snapshot produced from mock data
    Evidence: .sisyphus/evidence/task-10-full-cycle.txt

  Scenario: Graceful degradation on source failure
    Tool: Bash
    Steps:
      1. Run: pytest gex_terminal/tests/test_orchestrator.py::test_source_failure -v
      2. Assert: one adapter raises error, orchestrator continues with remaining
      3. Assert: failed source shows status='error' in SourceHealth
    Expected Result: Partial data with error indicators
    Evidence: .sisyphus/evidence/task-10-degradation.txt
  ```

  **Commit**: YES (group with Wave 2)
  - Message: `feat(gex-terminal): data pipeline + orchestration loop`
  - Files: `gex_terminal/engine/orchestrator.py`, `gex_terminal/tests/test_orchestrator.py`

- [x] 11. Terminal UI — Verdict + Regime Panel

  **What to do**:
  - Create `gex_terminal/ui/components/VerdictPanel.tsx`
  - Top section of the terminal (4 lines allocated):
    - Line 1: `║ ▲ BULLISH ▲  │ CONFIDENCE: ████████░░ 82%  ║` (or ▼ BEARISH ▼)
    - Line 2: `║ Regime: POSITIVE BETWEEN                       ║`
    - Line 3: `║ Grade: A  │ NQ: 21,450.25  │ Δ +125.75        ║`
    - Line 4: separator
  - Direction uses bright green (BULLISH), red (BEARISH), dim green (NEUTRAL)
  - Confidence bar: 10 filled/empty blocks (████████░░)
  - Regime name from analyzer's classification
  - Grade from BiasVerdict
  - NQ price from adapter data
  - Updates on every SSE event

  **Must NOT do**:
  - Do NOT use variable height — fixed 4 lines
  - Do NOT add animations beyond color change on direction flip

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []
  - Reason: Terminal UI panel with retro aesthetic

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 13, 14, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 4

  **References**:
  - `gex_terminal/docs/LAYOUT.md` — ASCII mockup (from Task 3) defines exact character positions
  - `dashboard/components/score/KronosBar.tsx` — Compact bias display pattern
  - `gex_terminal/ui/app/globals.css` — Green terminal color tokens

  **Acceptance Criteria**:
  - [ ] Component renders with mock data showing BULLISH and BEARISH states
  - [ ] Exactly 4 lines tall (no overflow)
  - [ ] Confidence bar renders 0-100% as block characters

  **Mock Data Mechanism** (used by Tasks 11-15):
  - Create `gex_terminal/ui/public/mock-snapshot.json` — a static `GEXTerminalSnapshot` fixture
  - When `NEXT_PUBLIC_MOCK_DATA=true` env var is set, `useGEXStream` hook reads from `/mock-snapshot.json` instead of SSE
  - Two fixture files: `mock-snapshot-bullish.json` and `mock-snapshot-bearish.json`
  - Playwright tests set `NEXT_PUBLIC_MOCK_DATA=true` and serve the appropriate fixture

  **QA Scenarios**:
  ```
  Scenario: Verdict panel displays BULLISH state
    Tool: Playwright
    Preconditions: Next.js dev server running with NEXT_PUBLIC_MOCK_DATA=true, mock-snapshot-bullish.json served
    Steps:
      1. Run: NEXT_PUBLIC_MOCK_DATA=true npm run dev (in gex_terminal/ui/)
      2. Navigate to http://localhost:3001
      3. Set viewport: 800×800
      4. Wait 2 seconds for mock data to load
      5. Assert: page.locator('[data-testid="verdict-direction"]').textContent() === "BULLISH"
      6. Assert: page.locator('[data-testid="verdict-confidence"]').textContent() matches /\d+%/
      7. Assert: page.locator('[data-testid="verdict-regime"]').isVisible()
      8. Screenshot
    Expected Result: BULLISH verdict clearly displayed
    Evidence: .sisyphus/evidence/task-11-verdict-bullish.png

  Scenario: Verdict panel displays BEARISH state
    Tool: Playwright
    Preconditions: Dev server running with mock-snapshot-bearish.json
    Steps:
      1. Navigate to http://localhost:3001?mock=bearish
      2. Set viewport: 800×800
      3. Assert: page.locator('[data-testid="verdict-direction"]').textContent() === "BEARISH"
      4. Screenshot
    Expected Result: BEARISH verdict with red color
    Evidence: .sisyphus/evidence/task-11-verdict-bearish.png
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/components/VerdictPanel.tsx`

- [x] 12. Terminal UI — Levels Panel

  **What to do**:
  - Create `gex_terminal/ui/components/LevelsPanel.tsx`
  - 6 lines allocated:
    - `║ GAMMA FLIP: 21,380  ▲ (price above = bullish)       ║`
    - `║ CALL WALL:  21,500  │ PUT WALL: 20,900              ║`
    - `║ HVL:        21,425  │ MAGNET:   21,450              ║`
    - `║ 0DTE MAGN:  21,400  │ PIN RISK: LOW                 ║`
    - `║ EM+: 21,620 (+170)  │ EM-: 21,280 (-170)           ║`
    - separator
  - All prices converted to NQ (via nq_mapper in backend)
  - Distance from current price shown where useful
  - Color coding: levels above price = green, below = dim
  - Price formatting: comma-separated thousands

  **Must NOT do**:
  - Do NOT add mini charts or sparklines
  - Do NOT exceed 6 lines

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 13, 14, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 4

  **References**:
  - `gex_terminal/docs/LAYOUT.md` — Exact layout positions
  - `gexdoctor/brain/flashalpha_knowledge.yaml` — Level field names and meanings

  **Acceptance Criteria**:
  - [ ] Renders all 6 level fields with formatted NQ prices
  - [ ] Exactly 6 lines tall
  - [ ] Prices formatted with comma separator (21,450)

  **QA Scenarios**:
  ```
  Scenario: Levels panel shows all key levels
    Tool: Playwright
    Preconditions: Dev server running with NEXT_PUBLIC_MOCK_DATA=true, mock-snapshot-bullish.json served
    Steps:
      1. Navigate to http://localhost:3001
      2. Set viewport: 800×800
      3. Wait 2 seconds for mock data
      4. Assert: page.locator('[data-testid="levels-gamma-flip"]').isVisible()
      5. Assert: page.locator('[data-testid="levels-call-wall"]').isVisible()
      6. Assert: page.locator('[data-testid="levels-put-wall"]').isVisible()
      7. Assert: page.locator('[data-testid="levels-0dte"]').isVisible()
      8. Assert: page.locator('[data-testid="levels-gamma-flip"]').textContent() matches /\d{2},\d{3}/ (comma-formatted)
      9. Screenshot
    Expected Result: All levels displayed with comma-formatted NQ prices
    Evidence: .sisyphus/evidence/task-12-levels-panel.png
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/components/LevelsPanel.tsx`

- [x] 13. Terminal UI — Analysis Panels (Dealer, Flow, Vanna/Charm)

  **What to do**:
  - Create `gex_terminal/ui/components/DealerPanel.tsx` (4 lines)
  - Create `gex_terminal/ui/components/FlowPanel.tsx` (3 lines)
  - Create `gex_terminal/ui/components/VannaCharmPanel.tsx` (2 lines)
  - **Dealer Panel** (4 lines):
    - `║ GEX: +3.2B (positive) │ DEX: -1.1B (short delta)   ║`
    - `║ VEX: +450M (long vol)  │ CHEX: -200M (time drag)    ║`
    - `║ REGIME: POSITIVE  │ HEDGE: BUYING                   ║`
    - separator
  - **Flow Panel** (3 lines):
    - `║ FLOW: ▲ BULLISH (z: +1.8) │ INT: ████████░░ HIGH   ║`
    - `║ SWEEPS: 14 │ BLOCKS: 3   │ NET: +$24M              ║`
    - separator
  - **Vanna/Charm Panel** (2 lines):
    - `║ VANNA: +$850M (tailwind) │ CHARM: -$320M (drag)    ║`
    - separator
  - Use abbreviations consistently (B=billion, M=million)
  - Color: positive values bright green, negative dim green or red

  **Must NOT do**:
  - Do NOT exceed allocated line counts per section
  - Do NOT add tooltips or expandable sections

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 14, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 4

  **References**:
  - `gex_terminal/docs/LAYOUT.md` — Layout positions
  - `.claude/skills/options-bias-engine/domains/dex-vex-chex.md` — DEX/VEX/CHEX meaning and display

  **Acceptance Criteria**:
  - [ ] DealerPanel: 4 lines, shows GEX/DEX/VEX/CHEX
  - [ ] FlowPanel: 3 lines, shows direction + sweeps + blocks
  - [ ] VannaCharmPanel: 2 lines, shows exposures
  - [ ] Values formatted with B/M suffixes

  **QA Scenarios**:
  ```
  Scenario: All analysis panels render
    Tool: Playwright
    Preconditions: Dev server running with NEXT_PUBLIC_MOCK_DATA=true, mock-snapshot-bullish.json served
    Steps:
      1. Navigate to http://localhost:3001
      2. Set viewport: 800×800
      3. Wait 2 seconds for mock data
      4. Assert: page.locator('[data-testid="dealer-gex"]').isVisible()
      5. Assert: page.locator('[data-testid="dealer-gex"]').textContent() matches /[+-]?\d+\.?\d*[BM]/
      6. Assert: page.locator('[data-testid="flow-direction"]').isVisible()
      7. Assert: page.locator('[data-testid="vanna-exposure"]').isVisible()
      8. Screenshot
    Expected Result: All 3 panels display data with B/M formatted values
    Evidence: .sisyphus/evidence/task-13-analysis-panels.png
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/components/DealerPanel.tsx`, `FlowPanel.tsx`, `VannaCharmPanel.tsx`

- [x] 14. Terminal UI — Narrative Panel (Claude's Interpretation)

  **What to do**:
  - Create `gex_terminal/ui/components/NarrativePanel.tsx`
  - 3 lines allocated:
    - `║ AI: Positive gamma regime. Dealers hedging into     ║`
    - `║     strength. Call wall 21,500 = magnet. Expect     ║`
    - `║     mean-reversion to flip.       [HAIKU · LIVE]    ║`
  - Claude's narrative text wraps within 80-char width
  - Bottom-right shows model name + status: `[HAIKU · LIVE]` or `[HAIKU · CACHED]` or `[RATE LIMITED]`
  - Text color: dim green (secondary) to distinguish from data panels
  - Narrative updates only on Claude call (not every 30s)

  **Must NOT do**:
  - Do NOT add typing animation when narrative updates
  - Do NOT exceed 3 lines (240 chars max from backend)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 13, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 4

  **References**:
  - `gex_terminal/docs/LAYOUT.md` — Layout positions
  - `gexdoctor/brain/flashalpha_interpreter.md` — Narrative style reference

  **Acceptance Criteria**:
  - [ ] Renders 3-line narrative from mock data
  - [ ] Shows model name + status badge
  - [ ] Text wraps correctly within 80-char width

  **QA Scenarios**:
  ```
  Scenario: Narrative panel shows Claude interpretation
    Tool: Playwright
    Preconditions: Dev server running with NEXT_PUBLIC_MOCK_DATA=true, mock-snapshot-bullish.json served
    Steps:
      1. Navigate to http://localhost:3001
      2. Set viewport: 800×800
      3. Wait 2 seconds for mock data
      4. Assert: page.locator('[data-testid="narrative-label"]').textContent() === "AI:"
      5. Assert: page.locator('[data-testid="narrative-text"]').textContent().length > 10
      6. Assert: page.locator('[data-testid="narrative-badge"]').textContent() matches /HAIKU|CACHED|RATE LIMITED/
      7. Screenshot
    Expected Result: Narrative displayed with status badge
    Evidence: .sisyphus/evidence/task-14-narrative-panel.png
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/components/NarrativePanel.tsx`

- [x] 15. Terminal UI — Status Footer

  **What to do**:
  - Create `gex_terminal/ui/components/StatusFooter.tsx`
  - 2 lines at bottom:
    - `║ FA:● MAS:● UW:○  │ $2.14 today │ ⟳ 28s │ 14:32 ET  ║`
    - `╚══════════════════════════════════════════════════════════╝`
  - Source health dots: ● green (ok), ● amber (stale), ○ gray (error/pending)
  - Daily Claude cost: `$X.XX today`
  - Refresh countdown: `⟳ Ns` counting down from 30
  - Clock: current ET time
  - Countdown updates every second (separate timer, not SSE-dependent)
  - On countdown reaching 0, brief flash to indicate data refresh

  **Must NOT do**:
  - Do NOT exceed 2 lines
  - Do NOT add complex animations

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 13, 14)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 3, 4

  **References**:
  - `gex_terminal/docs/LAYOUT.md` — Footer layout
  - `dashboard/components/layout/HeaderStrip.tsx` — Compact status display pattern

  **Acceptance Criteria**:
  - [ ] Shows 3 source health indicators
  - [ ] Shows daily cost
  - [ ] Countdown timer updates every second
  - [ ] Clock shows ET time

  **QA Scenarios**:
  ```
  Scenario: Footer displays all status elements
    Tool: Playwright
    Steps:
      1. Navigate to terminal
      2. Assert: "FA:" visible with colored dot
      3. Assert: "$" visible (cost display)
      4. Assert: "⟳" or countdown number visible
      5. Assert: time in HH:MM format visible
    Expected Result: All footer elements present
    Evidence: .sisyphus/evidence/task-15-footer.png
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/components/StatusFooter.tsx`

- [x] 16. SSE Integration + Real-Time Store

  **What to do**:
  - Create `gex_terminal/ui/hooks/useGEXStream.ts` — EventSource hook connecting to `/stream`
  - Create `gex_terminal/ui/store/gexStore.ts` — Zustand store for GEXTerminalSnapshot
  - Create `gex_terminal/ui/types/gex.ts` — TypeScript types mirroring Python schemas
  - EventSource hook:
    - Connects to `http://localhost:8780/stream`
    - Parses SSE `data:` events as GEXTerminalSnapshot JSON
    - Updates Zustand store on each event
    - Reconnection logic (exponential backoff, 5 steps)
    - Connection status tracking (connected/reconnecting/disconnected)
  - Zustand store:
    - Holds current `GEXTerminalSnapshot`
    - Version counter for selective re-rendering
    - Connection status
    - Last update timestamp
  - Wire all panel components to subscribe to store via `useGEXStream`
  - Page.tsx composes all panels into the layout from LAYOUT.md

  **Must NOT do**:
  - Do NOT use WebSocket — EventSource (SSE) is sufficient
  - Do NOT add buffering/history — only current snapshot

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []
  - Reason: Wiring SSE to React store with reconnection requires careful implementation

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (needs all panels + server)
  - **Blocks**: Tasks 17, 18
  - **Blocked By**: Tasks 5, 10, 11, 12, 13, 14, 15

  **References**:
  - `dashboard/hooks/useWebSocket.ts` — Existing connection hook with reconnection (adapt for SSE)
  - `dashboard/store/tradingStore.ts` — Zustand store pattern with version counters
  - `dashboard/types/deep6.ts` — TypeScript type definition pattern

  **Acceptance Criteria**:
  - [ ] `useGEXStream` connects to SSE endpoint and receives events
  - [ ] Zustand store updates on each event
  - [ ] All panels re-render with live data
  - [ ] Reconnection works after server restart

  **QA Scenarios**:
  ```
  Scenario: Full terminal renders with live data
    Tool: Playwright
    Preconditions: Backend running with live adapters
    Steps:
      1. Navigate to http://localhost:3001
      2. Set viewport: 800×800
      3. Wait 60 seconds for data
      4. Assert: verdict panel shows direction (BULLISH or BEARISH)
      5. Assert: levels panel shows gamma_flip (number > 15000)
      6. Assert: footer shows at least one green source dot
      7. Screenshot
    Expected Result: Full terminal with live data
    Evidence: .sisyphus/evidence/task-16-live-terminal.png

  Scenario: Reconnection after server restart
    Tool: Bash + Playwright
    Steps:
      1. Start server, wait for connection
      2. Kill server process
      3. Assert: terminal shows disconnected state
      4. Restart server
      5. Wait 30 seconds
      6. Assert: terminal reconnects and shows data
    Expected Result: Automatic reconnection
    Evidence: .sisyphus/evidence/task-16-reconnection.txt
  ```

  **Commit**: YES (group with Wave 3)
  - Message: `feat(gex-terminal): retro terminal UI with all panels`
  - Files: `gex_terminal/ui/hooks/useGEXStream.ts`, `gex_terminal/ui/store/gexStore.ts`, `gex_terminal/ui/types/gex.ts`

- [x] 17. DEEP6 Ingestion Endpoint (in deep6 codebase)

  **What to do**:
  - Add a new POST endpoint to the DEEP6 API that accepts GEX Doctor's data
  - Create `deep6/api/routes/gex_ingest.py`:
    - `POST /api/gex/ingest` — accepts a `GEXDoctorPayload` Pydantic model
    - `GEXDoctorPayload` fields (matching `deep6/engines/bias_contracts.py` `DomainScore` exactly):
      - `domain: str = "gex_doctor"`
      - `score: int` — integer -3 to +3 (bearish to bullish, matching other domain scores)
      - `max_range: int = 3`
      - `available: bool`
      - `stale: bool`
      - `detail: dict` — raw GEX data (regime, flip, walls, confidence)
      - `updated_at: float` — Unix timestamp (time.time()), NOT datetime
    - Endpoint stores the payload in a module-level `_latest_gex_doctor: GEXDoctorPayload | None = None`
    - `GET /api/v3/bias/domains` returns all domain scores as a dict — wire `_latest_gex_doctor` into `_domain_scores` dict in `bias_v3.py` so it appears in the domains endpoint
  - Register the new router in `deep6/api/app.py`
  - TDD: `tests/test_gex_ingest_endpoint.py`

  **Must NOT do**:
  - Do NOT modify existing bias_v3.py routes — add a new route file
  - Do NOT add a database — in-memory latest value only
  - Do NOT change the DomainScore interface — conform to it exactly

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
  - Reason: Small FastAPI endpoint following existing patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 18, 19)
  - **Blocks**: Task 17b
  - **Blocked By**: Tasks 2, 10

  **References**:
  - `deep6/api/routes/bias_v3.py` — Existing bias routes pattern (lines 28-47 for GET /api/v3/bias)
  - `deep6/engines/bias_contracts.py` — `DomainScore` dataclass: `domain`, `score`, `max_range`, `available`, `stale`, `detail`, `updated_at`
  - `deep6/api/app.py` — Router registration pattern

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest tests/test_gex_ingest_endpoint.py -v`
  - [ ] `curl -X POST http://localhost:8765/api/gex/ingest -H "Content-Type: application/json" -d '{"domain":"gex_doctor","score":2,"max_range":3,"available":true,"stale":false,"detail":{},"updated_at":1748527200.0}'` returns HTTP 200
  - [ ] After POST, `curl http://localhost:8765/api/v3/bias/domains` response includes a key `"gex_doctor"` (domain scores are at `/api/v3/bias/domains`, not `/api/v3/bias`)

  **QA Scenarios**:
  ```
  Scenario: Ingest endpoint accepts valid GEXDoctorPayload
    Tool: Bash (curl)
    Preconditions: DEEP6 API running on port 8765
    Steps:
      1. Run: curl -s -X POST http://localhost:8765/api/gex/ingest \
           -H "Content-Type: application/json" \
           -d '{"domain":"gex_doctor","score":2,"max_range":3,"available":true,"stale":false,"detail":{"regime":"positive","flip":21380.0},"updated_at":1748527200.0}'
      2. Assert: HTTP 200 response
      3. Assert: response body contains {"status": "ok"}
    Expected Result: Payload accepted
    Evidence: .sisyphus/evidence/task-17-ingest-ok.json

  Scenario: Ingested data appears in bias response
    Tool: Bash (curl)
    Preconditions: DEEP6 API running, ingest endpoint called (step above)
    Steps:
      1. Run: curl -s http://localhost:8765/api/v3/bias/domains | python -c "import json,sys; d=json.load(sys.stdin); print('gex_doctor' in d)"
      2. Assert: output is "True"
    Expected Result: gex_doctor domain visible in /api/v3/bias/domains response
    Evidence: .sisyphus/evidence/task-17-bias-includes-gex.json
  ```

  **Commit**: YES (group with Wave 4)
  - Message: `feat(gex-terminal): DEEP6 integration + hardening`
  - Files: `deep6/api/routes/gex_ingest.py`, `tests/test_gex_ingest_endpoint.py`, edit to `deep6/api/app.py`

- [x] 17b. DEEP6 Bidirectional Bridge (in gex_terminal)

  **What to do**:
  - Create `gex_terminal/engine/deep6_bridge.py`
  - **Outbound** (GEX Doctor → DEEP6):
    - After each orchestration cycle, POST `GEXDoctorPayload` to `http://localhost:8765/api/gex/ingest`
    - Payload fields: `domain="gex_doctor"`, `score: int` (integer -3..+3 from BiasVerdict: BULLISH confidence 80%+ → +3, 60-80% → +2, 50-60% → +1; BEARISH mirrors; NEUTRAL → 0), `max_range=3`, `available=True`, `stale=False`, `detail={regime, flip, walls, confidence}`, `updated_at=time.time()` (Unix float)
    - On failure: log, continue — don't block terminal operation
  - **Inbound** (DEEP6 → GEX Doctor):
    - Periodically GET `http://localhost:8765/api/v3/bias` to read MarketBiasSnapshot
    - Extract `bias_score: int` field from response (the composite score, range -6..+6 based on 5 domains × max_range 3 each, but actual range depends on active domains)
    - Also extract `bias_label: str` (e.g., "LEAN_BULL") and `confidence: float`
    - Populate `GEXTerminalSnapshot.deep6_bias_score` (int), `deep6_bias_label` (str), `deep6_confidence` (float)
  - Use `httpx.AsyncClient` with 5s timeout and 2 retries
  - If DEEP6 is not running, degrade gracefully (deep6_bias_score = None)
  - TDD: `gex_terminal/tests/test_deep6_bridge.py`

  **Must NOT do**:
  - Do NOT import deep6 modules directly — HTTP only (separate processes)
  - Do NOT block orchestration loop if DEEP6 is unreachable

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after Task 17)
  - **Blocks**: Task 18
  - **Blocked By**: Tasks 2, 10, 16, 17

  **References**:
  - `deep6/api/routes/gex_ingest.py` — The endpoint created in Task 17 (exact URL: POST /api/gex/ingest)
  - `deep6/api/routes/bias_v3.py` — GET /api/v3/bias response shape: `{bias_score: int, bias_label: str, confidence: float, bias_state: int, ...}` (see `_snapshot_to_dict()` in that file for full shape)
  - `nq_atlas/server.py` — httpx async client pattern

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_deep6_bridge.py -v`
  - [ ] Outbound: sends GEXDoctorPayload via HTTP POST to /api/gex/ingest
  - [ ] Inbound: reads `bias_score` (int) and `bias_label` (str) from GET /api/v3/bias response
  - [ ] Graceful degradation when DEEP6 is not running

  **QA Scenarios**:
  ```
  Scenario: Bridge works when DEEP6 is running
    Tool: Bash
    Preconditions: DEEP6 API running on port 8765, GEX terminal running on port 8780
    Steps:
      1. Wait 60s after both services start
      2. Run: curl -s http://localhost:8780/state | python -c "import json,sys; d=json.load(sys.stdin); print(type(d.get('deep6_bias_score')).__name__, d.get('deep6_bias_label'))"
      3. Assert: output shows "int" followed by a bias label (e.g., "int LEAN_BULL")
    Expected Result: Bidirectional data flow confirmed — bias_score is int, label is string
    Evidence: .sisyphus/evidence/task-17b-bridge-active.json

  Scenario: Bridge degrades when DEEP6 is offline
    Tool: Bash
    Preconditions: DEEP6 API NOT running, GEX terminal running
    Steps:
      1. Wait 60s after GEX terminal starts
      2. Run: curl -s http://localhost:8780/state | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('deep6_bias_score'))"
      3. Assert: output is "None" or "null"
      4. Run: curl -s http://localhost:8780/health | python -c "import json,sys; d=json.load(sys.stdin); print(d['status'])"
      5. Assert: status is "ok" or "degraded" (not error/crash)
    Expected Result: Graceful degradation
    Evidence: .sisyphus/evidence/task-17b-bridge-degraded.txt
  ```

  **Commit**: YES (group with Wave 4)
  - Message: `feat(gex-terminal): DEEP6 integration + hardening`
  - Files: `gex_terminal/engine/deep6_bridge.py`, `gex_terminal/tests/test_deep6_bridge.py`

- [x] 18. Source Degradation + Edge Cases

  **What to do**:
  - Enhance all adapters and orchestrator with edge case handling:
  - **Market hours**: Detect when options market is closed (4PM-9:30AM ET). Show `STALE` on GEX data. Use `zoneinfo` with `America/New_York`.
  - **OpEx detection**: Detect monthly/weekly OpEx. After 4PM on OpEx, show `EXPIRY RESET`.
  - **Flash crash**: If NQ price change > 3% in 5 minutes, show `⚠ EXTREME MOVE` override.
  - **Stale data badges**: Each source shows time-since-last-update. If > 2× refresh interval → STALE.
  - **0DTE availability**: Show `NO 0DTE TODAY` on Tue/Thu (when no NQ weekly options expire).
  - **API key expiration**: On 401/403, immediately mark source as AUTH FAILED.
  - TDD: `gex_terminal/tests/test_edge_cases.py`

  **Must NOT do**:
  - Do NOT hardcode UTC offsets — use zoneinfo
  - Do NOT suppress errors silently — always show status in UI

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 17, 19, 20)
  - **Blocks**: Tasks 19, 20
  - **Blocked By**: Tasks 10, 16, 17

  **References**:
  - Metis edge case analysis (E1-E10 in consultation notes)
  - `nq_atlas/state.py` — Degradation detection patterns
  - `deep6/engines/kill_switch.py` — Market hours, event day detection

  **Acceptance Criteria**:
  - [ ] Tests pass for all edge cases
  - [ ] Stale badges appear when sources are delayed
  - [ ] Market hours detection works correctly
  - [ ] Flash crash override triggers on rapid price movement

  **QA Scenarios**:
  ```
  Scenario: Stale badge appears on delayed source
    Tool: Bash
    Steps:
      1. Run test: pytest gex_terminal/tests/test_edge_cases.py::test_stale_detection -v
      2. Assert: source with update > 60s ago marked as STALE
    Expected Result: Stale detection works
    Evidence: .sisyphus/evidence/task-18-stale-badge.txt
  ```

  **Commit**: YES (group with Wave 4)
  - Message: `feat(gex-terminal): DEEP6 integration + hardening`
  - Files: `gex_terminal/engine/edge_cases.py`, `gex_terminal/tests/test_edge_cases.py`

- [x] 19. Process Management (PID Lock, Shutdown, Logging)

  **What to do**:
  - Add PID lock in `gex_terminal/__main__.py`:
    - Write PID to `~/.deep6/gexdoctor_v2.pid` on startup
    - Check for existing PID — if process alive, print error and exit
    - Remove PID file on graceful shutdown
  - Graceful shutdown: handle SIGINT/SIGTERM, close adapters, close SSE connections
  - Structured logging: `gex_terminal/engine/logger.py`
    - Log to `~/.deep6/gexdoctor_v2.log` (rotating, 10MB max, 3 backups)
    - JSON format for machine parsing
    - Log levels: INFO for cycle summaries, WARNING for stale sources, ERROR for failures
  - JSONL audit trail: `~/.deep6/gexdoctor_v2_audit.jsonl`
    - One line per cycle: timestamp, bias, confidence, sources_ok, claude_called, cost

  **Must NOT do**:
  - Do NOT use SQLite or any database for audit — JSONL only
  - Do NOT add a daemon/service manager — manual start/stop

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with Tasks 17, 18, 20)
  - **Blocks**: Task 20
  - **Blocked By**: Task 10

  **References**:
  - `nq_atlas/config.py` — Log configuration pattern
  - `deep6/copilot/budget.py` — JSONL logging pattern

  **Acceptance Criteria**:
  - [ ] PID lock prevents double launch
  - [ ] Graceful shutdown cleans up PID file
  - [ ] Logs write to ~/.deep6/gexdoctor_v2.log

  **QA Scenarios**:
  ```
  Scenario: PID lock prevents double launch
    Tool: Bash
    Steps:
      1. Start gex_terminal in background
      2. Attempt to start second instance
      3. Assert: second instance prints error and exits with code 1
      4. Kill first instance
      5. Assert: PID file removed
    Expected Result: Only one instance can run
    Evidence: .sisyphus/evidence/task-19-pid-lock.txt
  ```

  **Commit**: YES (group with Wave 4)
  - Message: `feat(gex-terminal): DEEP6 integration + hardening`
  - Files: `gex_terminal/engine/logger.py`, edits to `__main__.py`

- [x] 20. Launch Script + Startup Orchestration

  **What to do**:
  - Update `gex_terminal/__main__.py` to be the full entry point:
    - Parse CLI args: `--port`, `--refresh`, `--dry-run`, `--log-level`
    - Load settings from `.env.gex_terminal`
    - PID lock check
    - Start FastAPI server (uvicorn) in background task
    - Start orchestration loop
    - Start Next.js dev server (subprocess) or document manual startup
    - Print startup banner with ASCII art terminal frame
  - Create `scripts/start_gex_terminal.sh` (or `.ps1` for Windows):
    - Starts Python backend
    - Starts Next.js frontend
    - Opens browser to configured port
  - Document in `gex_terminal/README.md`:
    - Prerequisites (API keys in .env)
    - Start command: `python -m gex_terminal`
    - Development mode: separate backend + frontend
    - Troubleshooting

  **Must NOT do**:
  - Do NOT create Docker or systemd configs — manual start
  - Do NOT auto-start browser unless explicitly requested

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (needs everything from Wave 4)
  - **Blocks**: Tasks 21, 22
  - **Blocked By**: Tasks 17, 18, 19

  **References**:
  - `nq_atlas/server.py` — Uvicorn startup pattern
  - `gexdoctor/launch.py` — Launch orchestrator pattern

  **Acceptance Criteria**:
  - [ ] `python -m gex_terminal` starts the full system
  - [ ] `python -m gex_terminal --dry-run` validates config without connecting
  - [ ] README documents all startup steps

  **QA Scenarios**:
  ```
  Scenario: Full system starts with one command
    Tool: Bash
    Preconditions: API keys configured in .env
    Steps:
      1. Run: python -m gex_terminal &
      2. Wait 15 seconds
      3. Assert: curl http://localhost:8780/health returns status ok
      4. Kill process
    Expected Result: System starts and serves health endpoint
    Evidence: .sisyphus/evidence/task-20-startup.txt
  ```

  **Commit**: YES (group with Wave 4)
  - Message: `feat(gex-terminal): DEEP6 integration + hardening`
  - Files: `gex_terminal/__main__.py`, `scripts/start_gex_terminal.ps1`, `gex_terminal/README.md`

- [x] 21. Unusual Whales API Client (Phase 2 — Greenfield)

  **What to do**:
  - Create `gex_terminal/engine/adapters/unusual_whales.py`
  - This is GREENFIELD — no existing UW client code exists in the project
  - Build async httpx client for Unusual Whales REST API:
    - `GET /api/darkpool/recent` — recent dark pool prints for QQQ/SPY
    - `GET /api/stock/{symbol}/darkpool/levels` — clustered dark pool levels
    - `GET /api/stock/{symbol}/flow/alerts` — unusual options flow alerts
  - Rate limiting: respect UW API limits (use skills/unusual-whales/api-reference.md)
  - Convert dark pool QQQ levels to NQ via nq_mapper
  - Normalize to `DarkPoolSummary` schema: `levels: list[float]`, `net_premium`, `institutional_bias`
  - TDD: `gex_terminal/tests/test_uw_adapter.py`

  **Must NOT do**:
  - Do NOT build WebSocket streaming (REST polling is sufficient for Phase 2)
  - Do NOT implement ALL 100+ UW endpoints — focus on dark pool + flow alerts only

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`unusual-whales/api-reference`, `unusual-whales/dark-pool`, `unusual-whales/implementation`]
  - Reason: Greenfield API client needs reference documentation

  **Parallelization**:
  - **Can Run In Parallel**: YES (independent from other Wave 5 tasks initially)
  - **Parallel Group**: Wave 5
  - **Blocks**: Task 22
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `.claude/skills/unusual-whales/api-reference.md` — 100+ endpoints, authentication, rate limits
  - `.claude/skills/unusual-whales/dark-pool.md` — Dark pool levels as S/R, clustering, NQ proxy
  - `.claude/skills/unusual-whales/implementation.md` — Python async client patterns, rate limiting
  - `nq_atlas/massive_client.py` — httpx async client pattern to follow

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_uw_adapter.py -v`
  - [ ] Client authenticates and fetches dark pool data
  - [ ] Levels converted to NQ prices

  **QA Scenarios**:
  ```
  Scenario: UW adapter fetches dark pool levels
    Tool: Bash
    Preconditions: Valid UW API key
    Steps:
      1. Run: python -c "import asyncio; from gex_terminal.engine.adapters.unusual_whales import UWAdapter; a = UWAdapter(); result = asyncio.run(a.poll()); print(result)"
      2. Assert: DarkPoolSummary has non-empty levels list
      3. Assert: levels are in NQ price range (15000-25000)
    Expected Result: Dark pool data fetched and converted
    Evidence: .sisyphus/evidence/task-21-uw-darkpool.json
  ```

  **Commit**: YES (group with Wave 5)
  - Message: `feat(gex-terminal): unusual whales dark pool integration`
  - Files: `gex_terminal/engine/adapters/unusual_whales.py`, `gex_terminal/tests/test_uw_adapter.py`

- [x] 22. UW Dark Pool Data + Terminal Integration

  **What to do**:
  - Add `DarkPoolPanel.tsx` to terminal UI (2 lines):
    - `║ DARK POOL: 21,380 21,420 21,450  │ BIAS: BUY +$18M  ║`
    - separator
  - Wire UW adapter into orchestrator polling cycle (staggered: T+10s after FlashAlpha)
  - Add `dark_pool` field to `GEXTerminalSnapshot`
  - Add UW to source health display in footer: `UW:●`
  - Update SSE stream to include dark pool data
  - Update analyzer to factor dark pool levels into bias calculation
  - If UW key not configured, show `UW:○ (not configured)` and skip

  **Must NOT do**:
  - Do NOT make UW required — system must work without it
  - Do NOT give UW data equal weight to FlashAlpha — it's supplementary

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`unusual-whales/dark-pool`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after UW client)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 10, 16, 21

  **References**:
  - `.claude/skills/unusual-whales/dark-pool.md` — Level clustering, NQ proxy conversion
  - `.claude/skills/dark-pool-nq-charting/charting-methodology.md` — Dark pool visualization

  **Acceptance Criteria**:
  - [ ] Dark pool panel shows clustered levels in NQ prices
  - [ ] System works without UW key configured
  - [ ] UW appears in source health footer

  **QA Scenarios**:
  ```
  Scenario: Terminal includes dark pool section
    Tool: Playwright
    Preconditions: Full system running with UW key
    Steps:
      1. Navigate to terminal
      2. Assert: "DARK POOL:" text visible
      3. Assert: price levels displayed
      4. Assert: footer shows "UW:●" (green dot)
    Expected Result: Dark pool data integrated
    Evidence: .sisyphus/evidence/task-22-darkpool-terminal.png

  Scenario: System works without UW
    Tool: Playwright
    Preconditions: System running WITHOUT UW key
    Steps:
      1. Navigate to terminal
      2. Assert: all other panels have data
      3. Assert: footer shows "UW:○" (gray dot)
      4. Assert: no crash or error
    Expected Result: Graceful degradation without UW
    Evidence: .sisyphus/evidence/task-22-no-uw.png
  ```

  **Commit**: YES (group with Wave 5)
  - Message: `feat(gex-terminal): unusual whales dark pool integration`
  - Files: `gex_terminal/ui/components/DarkPoolPanel.tsx`, edits to orchestrator + schemas

- [x] 23. Signal Quality Validation (Replay Dataset)

  **What to do**:
  - Create `gex_terminal/tests/test_signal_quality.py` — validates bias signal quality against a fixed historical replay dataset
  - Use existing `nq_atlas/` historical data or a small fixed JSON fixture (10-20 known market sessions)
  - **Fixture format**: `gex_terminal/tests/fixtures/replay_sessions.json`
    - Each session: `{date, gex_regime, flip_level, call_wall, put_wall, nq_open, nq_close, actual_direction}`
    - `actual_direction`: "BULLISH" (close > open + 0.1%), "BEARISH" (close < open - 0.1%), "NEUTRAL"
    - Minimum 10 sessions covering: 3 positive gamma, 3 negative gamma, 2 pin, 2 pre-event
  - **Test**: Feed each session's GEX data through `GEXAnalyzer.analyze()` and compare predicted direction vs actual
  - **Pass thresholds** (explicit, measurable):
    - Overall directional accuracy ≥ 55% (better than coin flip)
    - Positive gamma regime accuracy ≥ 60%
    - Negative gamma regime accuracy ≥ 55%
    - NEUTRAL predictions allowed when confidence < 50% (no penalty)
    - Must NOT produce BULLISH when actual is BEARISH with confidence > 80% (catastrophic error check)
  - Create the fixture from publicly available GEX data (FlashAlpha historical or manually curated)
  - Document methodology: how sessions were selected, data sources, date range

  **Must NOT do**:
  - Do NOT use live API data in this test — fixture only (deterministic, reproducible)
  - Do NOT set thresholds so low they're trivially met (55% is the floor, not the target)
  - Do NOT cherry-pick sessions to inflate accuracy

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`options-bias-engine/knowledge`, `nq-options-algo-engine/deep-expertise/gex-model-validation`]
  - Reason: Requires domain expertise to create meaningful test fixtures and interpret results

  **Parallelization**:
  - **Can Run In Parallel**: YES (can run alongside Task 22)
  - **Parallel Group**: Wave 5 (with Task 22)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 8 (analyzer must exist)

  **References**:
  - `.claude/skills/nq-options-algo-engine/deep-expertise/gex-model-validation.md` — GEX model validation with honest limitations
  - `.claude/skills/options-bias-engine/step1-regimes/regime-identification.md` — Regime classification rules
  - `nq_atlas/gex.py` — GEXEngine for computing regime from fixture data

  **Acceptance Criteria**:
  - [ ] Tests pass: `pytest gex_terminal/tests/test_signal_quality.py -v`
  - [ ] Fixture has ≥ 10 sessions with documented sources
  - [ ] Overall accuracy ≥ 55% on fixture
  - [ ] No catastrophic errors (BULLISH when BEARISH with confidence > 80%)
  - [ ] Test output shows per-regime accuracy breakdown

  **QA Scenarios**:
  ```
  Scenario: Signal quality meets minimum thresholds
    Tool: Bash
    Preconditions: gex_terminal package importable, fixture file exists
    Steps:
      1. Run: pytest gex_terminal/tests/test_signal_quality.py -v --tb=short 2>&1 | tail -30
      2. Assert: all tests PASS
      3. Assert: output shows "Overall accuracy: X%" where X >= 55
      4. Assert: output shows "Positive gamma accuracy: X%" where X >= 60
      5. Assert: output shows "No catastrophic errors: PASS"
    Expected Result: Signal quality validated above minimum thresholds
    Evidence: .sisyphus/evidence/task-23-signal-quality.txt

  Scenario: Fixture is deterministic (same result on re-run)
    Tool: Bash
    Steps:
      1. Run: pytest gex_terminal/tests/test_signal_quality.py -v 2>&1 | grep "Overall accuracy"
      2. Run again: pytest gex_terminal/tests/test_signal_quality.py -v 2>&1 | grep "Overall accuracy"
      3. Assert: both outputs are identical
    Expected Result: Deterministic results (no live API calls in test)
    Evidence: .sisyphus/evidence/task-23-deterministic.txt
  ```

  **Commit**: YES (group with Wave 5)
  - Message: `feat(gex-terminal): signal quality validation with replay dataset`
  - Files: `gex_terminal/tests/test_signal_quality.py`, `gex_terminal/tests/fixtures/replay_sessions.json`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run linter + `pytest gex_terminal/tests/ -v`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names (data/result/item/temp). Verify NO API client code was rewritten — must be imports from nq_atlas/.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill)
  Start from clean state. Launch `python -m gex_terminal`. Open browser at configured port. Set viewport to 800×800. Verify all sections display data within 60s. Test source degradation (invalid key). Test PID lock (launch twice). Test after-hours behavior. Screenshot all states. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec. Check "Must NOT do" compliance — especially: no charts, no scrolling, no trade execution, no API client rewrites. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- After Wave 1: `feat(gex-terminal): scaffold project, schemas, layout mockup`
- After Wave 2: `feat(gex-terminal): data pipeline + orchestration loop`
- After Wave 3: `feat(gex-terminal): retro terminal UI with all panels`
- After Wave 4: `feat(gex-terminal): DEEP6 integration + hardening`
- After Wave 5: `feat(gex-terminal): unusual whales dark pool integration + signal quality validation`

---

## Success Criteria

### Verification Commands
```bash
# Backend health check
curl http://localhost:8780/health
# Expected: {"status": "ok", "sources": {"flashalpha": "ok", "massive": "ok", "uw": "pending"}}

# State snapshot
curl http://localhost:8780/state
# Expected: JSON with gex, regime, levels, narrative, bias, confidence fields

# SSE stream
curl -N http://localhost:8780/stream
# Expected: data: events every 30 seconds

# UI render at 800x800
npx playwright test gex_terminal/ui/tests/render.spec.ts
# Expected: all sections visible, no overflow, no scrollbar

# Python tests
pytest gex_terminal/tests/ -v
# Expected: all pass

# Cost tracking
cat ~/.deep6/gexdoctor_v2_usage.jsonl | wc -l
# Expected: >= 1 after first Claude call
```

### Final Checklist
- [x] All "Must Have" present
- [x] All "Must NOT Have" absent
- [x] All tests pass
- [x] 800×800 screenshot shows all sections with data
- [x] Source degradation works (STALE badges appear)
- [x] DEEP6 bidirectional integration verified
- [x] Claude narrative populates
- [x] PID lock prevents double-launch
- [x] Signal quality ≥ 55% overall accuracy on replay fixture (Task 23)
- [x] No catastrophic errors in signal quality test
