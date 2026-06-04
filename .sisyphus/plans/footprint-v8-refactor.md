# DEEP6 Footprint V8 — Signal Cleanup, Bias Box & Optimization

## TL;DR

> **Quick Summary**: Fork DEEP6FootprintV7.cs → V8. Audit all 10 signal variants for predictive value, kill underperformers, add granular visibility toggles, replace the exhaustion percentage diamond with a color-coded directional bias box (green LONG / red SHORT / gray NEUTRAL), and run 100+ backtest iterations to optimize thresholds. V7 preserved as rollback.
> 
> **Deliverables**:
> - `DEEP6FootprintV8.cs` — cleaned, optimized footprint indicator
> - Single-variant performance evaluator (Python) — reusable signal audit tool
> - Signal audit report — keep/kill/inconclusive verdict per variant (DuckDB)
> - Optimal parameter set — JSON from 100+ iteration optimization loop
> - Directional bias box — green/red/gray replacing percentage diamond
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 5 waves
> **Critical Path**: T1 (fork) → T5 (audit) → T8 (cleanup) → T12 (optimize) → T14 (port) → T15 (integration) → F1-F4 (verification)

---

## Context

### Original Request
User wants to work on DEEP6 v8 footprint chart. Three core problems:
1. **CLA labels everywhere** — cluttering the chart, not useful for the trader
2. **Arrows with no logical sense** — printed without meaningful conditions
3. **Percentage grade square** — needs redesign into simple long/short directional bias

Additionally: remove all signal bloat, backtest 100+ iterations to optimize, use multi-timeframe NQ data.

### Interview Summary
**Key Discussions**:
- User doesn't remember what CLA stands for → Metis discovered it's `Kind.ToString().Substring(0,3).ToUpper()` → CLA = Classic Absorption
- User doesn't know what percentage measures → It's `s.Strength * 100.0` (raw exhaustion strength scalar)
- Confirmed: NinjaTrader 8 platform, fork V7→V8, color-coded green/red box output
- Multi-timeframe optimization target (1/5/15 min NQ)

**Research Findings**:
- V7 has **4 separate arrow drawing systems** (triggered markers, absorption triangles, exhaustion arrows, tier-1 pulsing arrows)
- Absorption has **4 variants**: CLASSIC (CLA), PASSIVE (PAS), STOPPING_VOLUME (STO), EFFORT_VS_RESULT (EFF)
- Exhaustion has **6 variants**: ZERO_PRINT, EXHAUSTION_PRINT, THIN_PRINT, FAT_PRINT, FADING_MOMENTUM, BID_ASK_FADE
- Existing Python backtest framework tests **composite strategies only** — single-variant evaluator needed
- Two Python codebases exist (v1 `deep6/engines/` vs v2 `deep6v2/signals/`) — must validate which maps to V7 C#
- Existing toggles: `ShowAbsorptionMarkers`, `ShowExhaustionMarkers` — but not granular per-variant

### Metis Review
**Identified Gaps** (addressed):
- **MTF scope explosion**: V7 has zero `AddDataSeries()` calls. MTF is a NEW feature, not refactor. **Deferred to V9.** Optimization runs on 1-min data (primary timeframe).
- **Python version ambiguity**: Two Python codebases exist. Task T3 validates which maps to V7 C#.
- **No single-variant evaluator**: Existing framework tests composite only. Task T2 builds a lightweight forward-return evaluator.
- **CLA = threshold problem, not concept problem**: Classic Absorption fires too frequently. Fix sensitivity, don't delete the detection logic.
- **Optimization fitness mismatch**: Absorption/exhaustion are CONFIRMATIONS, not entries. Audit must measure confirmation value, not standalone entry value.
- **Arrow system complexity**: 4 separate drawing paths. All default OFF in V8, individually toggleable, only re-enabled if backtest-validated.

---

## Work Objectives

### Core Objective
Create DEEP6FootprintV8.cs — a data-validated, decluttered footprint indicator with a clear directional bias signal, where every visual element earns its place through backtested predictive value.

### Concrete Deliverables
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — forked from V7, all changes applied
- `deep6/backtest/variant_evaluator.py` — single-signal forward-return evaluator
- `data/backtests/v8_variant_audit.duckdb` — 10-variant performance results
- `data/backtests/v8_optimization.json` — optimal parameter set from 100+ iterations
- Bias box rendering in V8 (green LONG / red SHORT / gray NEUTRAL)
- Granular visibility toggles for every visual element type

### Definition of Done
- [ ] V8 compiles cleanly: `nt8-compile.ps1` returns `[COMPILE-RESULT] SUCCESS`
- [ ] V8 signal count ≤ V7 on same 1-day replay data
- [ ] Bias box correctly displays direction on 5 known historical setups
- [ ] 100+ optimization iterations completed in DuckDB with `status='completed'`
- [ ] Top config OOS fitness ≥ 0.55 (IS/OOS split ≥ 68/32)
- [ ] All visual elements toggleable via NinjaScript input properties

### Must Have
- Fork V7 → V8 with V7 untouched as rollback
- Granular per-variant visibility toggles (not just `ShowAbsorptionMarkers` umbrella)
- Color-coded directional bias box replacing percentage diamond
- 100+ iteration automated optimization loop
- Walk-forward validation of optimal parameters
- Every killed signal must retain a toggle to re-enable (OFF by default)

### Must NOT Have (Guardrails)
- Do NOT add multi-timeframe logic (AddDataSeries) — deferred to V9
- Do NOT modify FootprintBar construction, ConfluenceScorer architecture, or OnMarketData() tick processing
- Do NOT change the existing 30+ Input properties that other chart elements depend on
- Do NOT delete absorption/exhaustion detection logic — only gate behind quality thresholds
- Do NOT add new detection logic not present in V7
- Do NOT render more than 1 bias box per bar (no stacking)
- Do NOT change the 240px Mission Control panel layout
- Do NOT hardcode bias box thresholds — must come from optimization
- Do NOT accept optimization results without OOS validation
- Do NOT run more than 200 iterations without convergence check (plateau > 20 iterations = stop)
- Do NOT use "visually inspect" or "manually confirm" as acceptance criteria

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (Python: pytest + DuckDB backtest framework; NinjaTrader: nt8-compile.ps1)
- **Automated tests**: Tests-after (validation via backtest framework + compile gates)
- **Framework**: pytest (Python evaluator), nt8-compile.ps1 (C# compilation), backtest harness (optimization)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **NinjaScript C#**: Use Bash (`nt8-compile.ps1`) — compile, check output, verify success
- **Python evaluator**: Use Bash (`python -m pytest`) — run tests, check assertions
- **Backtest results**: Use Bash (DuckDB queries) — query iteration counts, fitness scores, parameter values
- **Visual verification**: Use NT8 chart screenshot via `nt8-ui.ps1 screenshot`

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation + research, 4 parallel):
├── Task 1: Fork V7 → V8 + clean compile gate [quick]
├── Task 2: Build single-variant forward-return evaluator [deep]
├── Task 3: Validate Python ↔ C# signal logic parity [unspecified-high]
└── Task 4: Research professional footprint signal clarity practices [librarian-only]

Wave 2 (After Wave 1 — signal audit, 3 parallel):
├── Task 5: Run 10-variant performance audit (depends: 2, 3) [deep]
├── Task 6: Arrow system audit — all 4 drawing paths (depends: 2, 3) [deep]
└── Task 7: Signal overlap/correlation analysis (depends: 2, 3) [unspecified-high]

Wave 3 (After Wave 2 — cleanup + redesign, 4 parallel):
├── Task 8: Remove killed variants + add granular toggles (depends: 5, 7) [unspecified-high]
├── Task 9: Fix arrow logic — gate behind confluence (depends: 6) [unspecified-high]
├── Task 10: Design + implement bias box algorithm (depends: 5) [deep]
└── Task 11: Add signal frequency limiter (depends: 5, 7) [quick]

Wave 4 (After Wave 3 — optimization, 3 tasks):
├── Task 12: Configure optimization loop for V8 signals (depends: 8, 9, 10, 11) [deep]
├── Task 13: Run 100+ iteration optimization + walk-forward (depends: 12) [deep]
└── Task 14: Port optimal parameters to V8 C# + compile (depends: 13) [unspecified-high]

Wave 5 (After Wave 4 — integration, 2 parallel):
├── Task 15: V8 vs V7 regression comparison (depends: 14) [unspecified-high]
└── Task 16: Deploy V8 to NT8 + chart screenshot evidence (depends: 14) [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high + nt8-expert skill)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: T1 → T5 → T8 → T12 → T13 → T14 → T15 → F1-F4 → user okay
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Waves 1 & 3)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T5, T6, T7, T8, T9, T10, T11 | 1 |
| T2 | — | T5, T6, T7 | 1 |
| T3 | — | T5, T6, T7 | 1 |
| T4 | — | T10 | 1 |
| T5 | T2, T3 | T8, T10, T11, T12 | 2 |
| T6 | T2, T3 | T9 | 2 |
| T7 | T2, T3 | T8, T11 | 2 |
| T8 | T5, T7 | T12 | 3 |
| T9 | T6 | T12 | 3 |
| T10 | T5, T4 | T12 | 3 |
| T11 | T5, T7 | T12 | 3 |
| T12 | T8, T9, T10, T11 | T13 | 4 |
| T13 | T12 | T14 | 4 |
| T14 | T13 | T15, T16 | 4 |
| T15 | T14 | F1-F4 | 5 |
| T16 | T14 | F1-F4 | 5 |

### Agent Dispatch Summary

- **Wave 1**: **4** — T1 → `quick`, T2 → `deep`, T3 → `unspecified-high`, T4 → librarian subagent
- **Wave 2**: **3** — T5 → `deep`, T6 → `deep`, T7 → `unspecified-high`
- **Wave 3**: **4** — T8 → `unspecified-high`, T9 → `unspecified-high`, T10 → `deep`, T11 → `quick`
- **Wave 4**: **3** — T12 → `deep`, T13 → `deep`, T14 → `unspecified-high`
- **Wave 5**: **2** — T15 → `unspecified-high`, T16 → `quick`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Fork V7 → V8 + Clean Compile Gate

  **What to do**:
  - Copy `DEEP6FootprintV7.cs` to `DEEP6FootprintV8.cs` in the same directory
  - Rename the class from `DEEP6FootprintV7` to `DEEP6FootprintV8`
  - Update the `[Display(Name=...)]` attribute to show "DEEP6 Footprint V8"
  - Update any internal string references (log messages, tag prefixes) from "V7" to "V8"
  - Verify the file compiles cleanly via `nt8-compile.ps1`
  - Do NOT change any logic, thresholds, or signal detection code at this stage

  **Must NOT do**:
  - Do NOT modify DEEP6FootprintV7.cs in any way
  - Do NOT change any detection logic, rendering, or input properties
  - Do NOT add new features — this is a pure fork

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file copy + rename + compile verification. No design decisions.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Needed for NT8 compilation verification and namespace conventions
  - **Skills Evaluated but Omitted**:
    - `nt8-new`: Not creating from scratch — forking existing

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 5, 6, 7, 8, 9, 10, 11
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — Source file to fork. Copy entire file, rename class and Display attribute.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs` → `V7.cs` — Reference for how previous forks were done (V6→V7 diff shows class rename pattern)

  **API/Type References**:
  - `[Display(Name="DEEP6 Footprint V7", ...)]` attribute — Change "V7" to "V8"

  **External References**:
  - `ninjatrader/scripts/nt8-compile.ps1` — Compilation verification script

  **WHY Each Reference Matters**:
  - V7 file is the exact source — copy verbatim then rename
  - V6→V7 fork history shows established rename pattern (class name, Display attribute, tag prefixes)
  - Compile script is the gate — V8 must pass before any other work begins

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 file exists and compiles cleanly
    Tool: Bash (PowerShell)
    Preconditions: V7 file exists at ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs
    Steps:
      1. Verify V8 file exists: Test-Path ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs
      2. Verify V7 is unchanged: git diff ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs → empty
      3. Verify class renamed: Select-String "class DEEP6FootprintV8" DEEP6FootprintV8.cs → match found
      4. Compile: powershell ninjatrader/scripts/nt8-compile.ps1
    Expected Result: V8 file exists, V7 unchanged, class renamed, compile returns [COMPILE-RESULT] SUCCESS
    Failure Indicators: File not found, V7 modified, class still named V7, compile fails
    Evidence: .sisyphus/evidence/task-1-v8-compile.txt

  Scenario: V8 has no logic changes from V7
    Tool: Bash (diff)
    Preconditions: Both V7 and V8 exist
    Steps:
      1. Run diff between V7 and V8: diff V7.cs V8.cs
      2. Verify only changes are: class name, Display name, tag prefixes, log messages
      3. No signal detection, threshold, or rendering changes
    Expected Result: Diff shows only rename-related changes (< 20 lines changed)
    Failure Indicators: Logic changes detected, threshold values different, new code added
    Evidence: .sisyphus/evidence/task-1-v7-v8-diff.txt
  ```

  **Commit**: YES
  - Message: `feat(footprint): fork V7 → V8 skeleton`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 2. Build Single-Variant Forward-Return Evaluator

  **What to do**:
  - Create `deep6/backtest/variant_evaluator.py` — a lightweight Python tool that tests individual signal variants in isolation
  - For each variant (ABS_01-04, EXH_01-06), the evaluator must:
    - Run the signal on historical NQ 1-min data
    - Record every signal firing (timestamp, price, direction, strength)
    - Measure forward return after each signal (1R, 2R, 3R at configurable bars forward)
    - Calculate: hit rate, average R:R, profit factor, max drawdown per signal
    - Apply IS/OOS split (68/32 default from existing fitness.py)
    - Require minimum N≥30 OOS occurrences for statistical validity
  - Output results to DuckDB: `data/backtests/v8_variant_audit.duckdb` with tables: `variants` (name, hit_rate, rr, pf, n_signals, verdict), `signals` (timestamp, variant, direction, strength, forward_return)
  - Integrate with existing `deep6/engines/signal_config.py` for threshold values
  - Must distinguish "confirmation value" from "entry value" — measure P(price moves ≥1R in signal direction within N bars | signal fires AND entry condition met)
  - CLI interface: `python -m deep6.backtest.variant_evaluator --data data/backtests/nq_1yr_1m.csv --variant ABS_01 --bars-forward 10`

  **Must NOT do**:
  - Do NOT modify existing backtest framework files (harness.py, fitness.py, mutation_engine.py)
  - Do NOT test composite strategies — this evaluates single variants in isolation
  - Do NOT use vectorbt for this — lightweight custom evaluator is faster and more targeted

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires careful statistical design, understanding of signal evaluation methodology, and integration with existing Python codebase
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `hermes-backtest-discovery`: Different scope — that's for composite strategy discovery, not single-variant audit

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Tasks 5, 6, 7
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `deep6/backtest/fitness.py` — IS/OOS split implementation (use same `is_ratio=0.68` pattern and composite score formula)
  - `deep6/backtest/harness.py` — CLI interface pattern (argparse, subprocess runner, DuckDB output)
  - `deep6/backtest/discovery_schema.py` — DuckDB schema pattern (table creation, upsert logic)

  **API/Type References**:
  - `deep6/engines/absorption.py` — Absorption variant detection logic (4 variants with `detect()` method signature)
  - `deep6/engines/exhaustion.py` — Exhaustion variant detection logic (6 variants, delta gate, cooldown)
  - `deep6/engines/signal_config.py` — Threshold values for all detectors (authoritative source)
  - `deep6/state/footprint.py` — FootprintBar state accumulator (bid/ask per level, POC, delta)

  **Test References**:
  - `tests_v2/backtest/test_fitness.py` — Testing pattern for backtest evaluation code

  **External References**:
  - `data/backtests/nq_1yr_1m.csv` — 1-year NQ 1-minute data for evaluation
  - `data/backtests/nq_3mo_1m.csv` — 3-month NQ 1-minute data (alternative shorter dataset)

  **WHY Each Reference Matters**:
  - fitness.py has the proven IS/OOS split logic — reuse, don't reinvent
  - harness.py shows how existing backtest CLI tools are structured — follow the pattern
  - signal_config.py has the exact thresholds V7 uses — evaluator must use identical values
  - FootprintBar state is needed to feed signal detectors during replay

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Evaluator runs on sample data and produces results
    Tool: Bash (Python)
    Preconditions: nq_1yr_1m.csv exists in data/backtests/
    Steps:
      1. Run: python -m deep6.backtest.variant_evaluator --data data/backtests/nq_3mo_1m.csv --variant ABS_01 --bars-forward 10
      2. Check exit code: 0
      3. Query DuckDB: SELECT count(*) FROM variants WHERE name='ABS_01' → ≥ 1 row
      4. Query DuckDB: SELECT n_signals FROM variants WHERE name='ABS_01' → > 0
      5. Verify hit_rate is between 0 and 1
    Expected Result: Evaluator completes, DuckDB has results, hit_rate is valid float
    Failure Indicators: ImportError, no DuckDB output, hit_rate outside [0,1], n_signals=0
    Evidence: .sisyphus/evidence/task-2-evaluator-run.txt

  Scenario: IS/OOS split produces different results
    Tool: Bash (Python)
    Preconditions: Evaluator runs successfully on ABS_01
    Steps:
      1. Query: SELECT is_hit_rate, oos_hit_rate FROM variants WHERE name='ABS_01'
      2. Verify is_hit_rate ≠ oos_hit_rate (different values confirm proper split)
      3. Verify both are between 0.0 and 1.0
    Expected Result: IS and OOS hit rates are different valid floats
    Failure Indicators: Identical rates (suggests no split), NaN, or out of range
    Evidence: .sisyphus/evidence/task-2-is-oos-split.txt
  ```

  **Commit**: YES
  - Message: `feat(backtest): add single-variant forward-return evaluator`
  - Files: `deep6/backtest/variant_evaluator.py`
  - Pre-commit: `python -m pytest tests_v2/backtest/ -v --tb=short`

- [x] 3. Validate Python ↔ C# Signal Logic Parity

  **What to do**:
  - Determine which Python codebase (v1 `deep6/engines/` or v2 `deep6v2/signals/`) maps to V7's C# implementation
  - Compare thresholds, variant names, detection conditions, cooldown values between the authoritative Python and V7 C#
  - Document any discrepancies in a parity report
  - If discrepancies exist, note them for T8 (cleanup) to resolve — the Python optimization must match C# behavior
  - Check: AbsorptionDetector.cs ↔ absorption.py, ExhaustionDetector.cs ↔ exhaustion.py, signal_config.py ↔ V7 hardcoded values
  - Output: `data/backtests/v8_parity_report.md` with verdict per detector (MATCH / MISMATCH + details)

  **Must NOT do**:
  - Do NOT modify any Python or C# code — this is read-only audit
  - Do NOT assume which Python version is correct — verify empirically

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Cross-language comparison requiring careful reading of both Python and C# codebases
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: For understanding NinjaScript patterns and C# signal detection conventions
  - **Skills Evaluated but Omitted**:
    - `tradingview-pine-converter`: Not Pine — this is Python↔C# comparison

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Tasks 5, 6, 7
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `deep6/engines/absorption.py` — Python v1 absorption logic (4 variants)
  - `deep6/engines/exhaustion.py` — Python v1 exhaustion logic (6 variants)
  - `deep6/engines/signal_config.py` — Python v1 threshold values
  - `deep6v2/signals/` — Python v2 signal implementations (if exists)

  **API/Type References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` — C# absorption (4 variants + VAH/VAL bonus)
  - `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs` — C# exhaustion (6 variants + delta gate + cooldown)

  **External References**:
  - `.planning/phases/16-ninjatrader-8-footprint-indicator-standalone-parallel-delive/PORT-SPEC.md` — Authoritative C# port specification

  **WHY Each Reference Matters**:
  - Python v1 and C# should be 1:1 per PORT-SPEC.md — any drift means optimization results won't transfer
  - PORT-SPEC.md is the source of truth for what C# should implement — deviations are bugs

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Parity report covers all 10 variants
    Tool: Bash (grep)
    Preconditions: Parity report generated
    Steps:
      1. Read data/backtests/v8_parity_report.md
      2. Verify all 4 absorption variants listed: ABS_01, ABS_02, ABS_03, ABS_04
      3. Verify all 6 exhaustion variants listed: EXH_01-EXH_06
      4. Verify each has MATCH or MISMATCH verdict
    Expected Result: 10 variants documented with verdicts
    Failure Indicators: Missing variants, no verdict, ambiguous conclusions
    Evidence: .sisyphus/evidence/task-3-parity-report.md

  Scenario: Threshold comparison is numerical
    Tool: Bash (grep)
    Preconditions: Parity report exists
    Steps:
      1. grep for threshold values in parity report
      2. Verify Python value and C# value are shown side-by-side
      3. Verify delta_gate, cooldown_bars, strength thresholds are compared
    Expected Result: Numerical comparison for all shared thresholds
    Failure Indicators: Vague "seems similar" without numbers
    Evidence: .sisyphus/evidence/task-3-threshold-comparison.txt
  ```

  **Commit**: YES
  - Message: `docs(backtest): Python↔C# signal parity report`
  - Files: `data/backtests/v8_parity_report.md`
  - Pre-commit: N/A (documentation only)

- [x] 15. V8 vs V7 Regression Comparison

  **What to do**:
  - Load both V7 and V8 side-by-side (or sequentially) on the same NQ chart data
  - Compare signal counts: V8 total signals ≤ V7 (must be cleaner)
  - Verify V8 with ALL toggles ON + bias box OFF produces functionally equivalent output to V7 (regression gate)
  - Verify V8 with DEFAULT settings produces a clean, uncluttered chart
  - Document comparison: `data/backtests/v8_vs_v7_comparison.md`
  - Take screenshots of V7 chart vs V8 chart (same time range) for visual comparison

  **Must NOT do**:
  - Do NOT modify V7 — it's the regression baseline
  - Do NOT skip the "all toggles ON" regression check

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Comparison analysis with visual verification and documentation
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 chart loading, indicator comparison, screenshot capture

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Task 16)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 14

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — Regression baseline
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — New version to compare

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 signal count ≤ V7
    Tool: Bash (NT8 + grep)
    Preconditions: Both V7 and V8 compiled, Output Window captures enabled
    Steps:
      1. Run V8 with default settings on 1-day NQ data
      2. Count total signals logged to Output Window
      3. Run V7 on same data
      4. Count V7 signals
      5. Verify: V8 count ≤ V7 count
    Expected Result: V8 produces equal or fewer signals than V7
    Failure Indicators: V8 produces MORE signals than V7
    Evidence: .sisyphus/evidence/task-15-signal-count-comparison.txt

  Scenario: V8 all-on matches V7 functionally
    Tool: Bash (diff)
    Preconditions: Both produce Output Window logs
    Steps:
      1. Run V8 with all toggles ON + bias box OFF
      2. Compare signal detection events (type, direction, price) against V7
      3. Verify: same signals detected (rendering may differ, detection must match)
    Expected Result: Same signal detection events, different rendering only
    Failure Indicators: V8 detects different signals than V7 (detection logic changed)
    Evidence: .sisyphus/evidence/task-15-regression.txt
  ```

  **Commit**: YES (groups with T16)
  - Message: `docs(footprint): v8 vs v7 regression comparison`
  - Files: `data/backtests/v8_vs_v7_comparison.md`
  - Pre-commit: N/A

- [x] 16. Deploy V8 to NT8 + Chart Screenshot Evidence

  **What to do**:
  - Deploy DEEP6FootprintV8.cs to NinjaTrader 8
  - Load V8 on a live NQ chart with default settings
  - Verify: chart is clean (no CLA clutter, minimal arrows, bias box visible)
  - Take screenshots showing:
    1. Default V8 view (clean chart)
    2. Bias box in action (LONG/SHORT/NEUTRAL states)
    3. V8 input settings panel (all toggles visible)
  - Save screenshots to `.sisyphus/evidence/task-16-*.png`

  **Must NOT do**:
  - Do NOT change any V8 code at this stage — deploy-only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Deployment + screenshot capture. No code changes.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 deployment, chart interaction, screenshot capture

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 5 (with Task 15)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 14

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — Deployment script
  - `ninjatrader/scripts/nt8-ui.ps1 screenshot` — Screenshot capture

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 loads on chart without errors
    Tool: Bash (PowerShell)
    Steps:
      1. Deploy: powershell ninjatrader/scripts/nt8-deploy.ps1 DEEP6FootprintV8
      2. Compile: powershell ninjatrader/scripts/nt8-compile.ps1 → SUCCESS
      3. Take screenshot: powershell ninjatrader/scripts/nt8-ui.ps1 screenshot
      4. Verify screenshot shows V8 on chart
    Expected Result: V8 deployed, compiled, visible on chart
    Failure Indicators: Deploy fails, compile fails, chart empty
    Evidence: .sisyphus/evidence/task-16-v8-deployed.png

  Scenario: Chart is visually clean with default settings
    Tool: Bash (PowerShell + visual check)
    Preconditions: V8 loaded on chart
    Steps:
      1. Take screenshot of full chart with V8 defaults
      2. Verify: no CLA labels visible (kill'd variants off)
      3. Verify: arrows only appear on high-confluence signals
      4. Verify: bias box visible as green/red/gray rectangle
    Expected Result: Clean chart with bias box, minimal signals
    Failure Indicators: CLA clutter still visible, too many arrows
    Evidence: .sisyphus/evidence/task-16-v8-clean-chart.png
  ```

  **Commit**: YES (groups with T15)
  - Message: `feat(footprint): v8 deployed and verified on NQ chart`
  - Files: Evidence files only
  - Pre-commit: N/A

- [x] 12. Configure Optimization Loop for V8 Signals

  **What to do**:
  - Adapt the existing Python backtest discovery loop (`scripts/backtest_loop.py`) to optimize V8's surviving signal parameters
  - Create V8-specific optimization config:
    - **Parent-0**: V7's current parameters as baseline (from `signal_config.py`)
    - **Mutation targets**: Signal thresholds, bias box thresholds, confluence minimums, strength minimums, cooldown values
    - **Fitness function**: Existing fitness.py criteria (>55% WR, >1.5 R:R, IS/OOS split 68/32, min 30 trades)
    - **Mutation types**: Focus on `TWEAK_PARAMS` and `REMOVE_CONFIRMATION` from existing mutation_engine
    - **Convergence check**: If best fitness plateaus for 20+ iterations, stop early (per Metis guardrail)
    - **Hard cap**: 200 iterations OR 4 hours wall-clock, whichever comes first
  - Parameter bounds (from `param_bounds.py` pattern):
    - `BiasLongThreshold`: [0.40, 0.85]
    - `BiasShortThreshold`: [-0.85, -0.40]
    - `MinArrowConfluence`: [1, 7]
    - `MinExhaustionStrength`: [0.30, 0.90]
    - `MaxSignalsPerSession`: [5, 30]
    - Per-variant enable/disable (binary)
  - Output: `data/backtests/v8_optimization.duckdb` with iteration results, parameter sets, fitness scores
  - Save optimal config as JSON: `data/backtests/v8_optimal_params.json`

  **Must NOT do**:
  - Do NOT modify the fitness function — use existing criteria
  - Do NOT optimize on multi-timeframe data (no MTF in V8 — deferred to V9)
  - Do NOT run the loop yet — this task only CONFIGURES it (T13 runs it)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires understanding existing optimization framework, adapting it for V8's specific parameter space
  - **Skills**: [`hermes-backtest-discovery`]
    - `hermes-backtest-discovery`: Complete reference for autonomous discovery loop configuration

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after Wave 3)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 8, 9, 10, 11

  **References**:

  **Pattern References**:
  - `scripts/backtest_loop.py` — Main discovery loop orchestrator (read DuckDB state, mutate, validate, run harness, compute fitness)
  - `deep6/backtest/mutation_engine.py` — 8 mutation types (TWEAK_PARAMS, REMOVE_CONFIRMATION, etc.)
  - `deep6/backtest/param_bounds.py` — Parameter bounds registry pattern (add V8 parameters here)
  - `deep6/backtest/fitness.py` — IS/OOS fitness evaluation (>55% WR, >1.5 R:R)
  - `deep6/backtest/config_validator.py` — Bounds checking + contradiction detection

  **API/Type References**:
  - `deep6/backtest/strategy_config.py` — Frozen StrategyConfig dataclass (V8 config should follow this pattern)
  - `deep6/backtest/discovery_schema.py` — DuckDB schema for iterations/trades/strategies tables

  **WHY Each Reference Matters**:
  - backtest_loop.py is the orchestrator — adapt it, don't rewrite it
  - mutation_engine already handles parameter tweaking — configure it for V8's parameter space
  - param_bounds ensures optimization stays within valid ranges

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 optimization config is valid and runnable
    Tool: Bash (Python)
    Preconditions: V8 config created
    Steps:
      1. python -c "from deep6.backtest.config_validator import validate; validate('v8_config.json')" → no errors
      2. python -c "from deep6.backtest.param_bounds import get_bounds; b = get_bounds('v8'); assert len(b) >= 6"
      3. Verify convergence check is configured: grep "plateau" in loop config
    Expected Result: Config validates, bounds registered, convergence check present
    Failure Indicators: Validation errors, missing bounds, no convergence check
    Evidence: .sisyphus/evidence/task-12-optimization-config.txt

  Scenario: Parent-0 matches V7 current parameters
    Tool: Bash (Python)
    Preconditions: V8 config with parent-0
    Steps:
      1. Read parent-0 parameters from config
      2. Compare against signal_config.py values
      3. All V7 thresholds match exactly
    Expected Result: Parent-0 is exact V7 parameter set
    Failure Indicators: Parameters don't match V7
    Evidence: .sisyphus/evidence/task-12-parent0-verification.txt
  ```

  **Commit**: YES
  - Message: `feat(backtest): v8 optimization loop configuration`
  - Files: `deep6/backtest/v8_config.py`, `data/backtests/v8_parent0.json`
  - Pre-commit: `python -m pytest tests_v2/backtest/ -v --tb=short`

- [x] 13. Run 100+ Iteration Optimization + Walk-Forward Validation

  **What to do**:
  - Execute the optimization loop configured in T12
  - Run: `python scripts/backtest_loop.py --config v8 --max-iterations 200 --convergence-patience 20 --max-hours 4`
  - Monitor progress: query DuckDB for iteration count, best fitness, convergence status
  - After loop completes (100+ iterations OR convergence OR time limit):
    - Extract top-3 parameter sets by OOS fitness
    - Run walk-forward validation on each: 60% train / 20% validate / 20% test split
    - Select the parameter set with best test-period fitness
  - Save results:
    - `data/backtests/v8_optimization.duckdb` — all iteration results
    - `data/backtests/v8_optimal_params.json` — winning parameter set
    - `data/backtests/v8_optimization_report.md` — summary with convergence plot data, top-3 comparison, walk-forward results

  **Must NOT do**:
  - Do NOT accept results without OOS validation
  - Do NOT run more than 200 iterations without convergence check
  - Do NOT optimize on 5/15 min data (V8 is single timeframe)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Long-running optimization with monitoring, statistical interpretation of results, walk-forward validation
  - **Skills**: [`hermes-backtest-discovery`]
    - `hermes-backtest-discovery`: Autonomous loop monitoring, DuckDB state queries, convergence detection

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after T12)
  - **Blocks**: Task 14
  - **Blocked By**: Task 12

  **References**:

  **Pattern References**:
  - `scripts/backtest_loop.py` — Orchestrator to invoke
  - `deep6/backtest/fitness.py` — Fitness evaluation (>55% WR, >1.5 R:R, composite score)
  - `scripts/walk_forward.py` — Existing walk-forward analysis script

  **API/Type References**:
  - `data/backtests/v8_optimization.duckdb` — Output database
  - `deep6/backtest/discovery_schema.py` — DuckDB query patterns for monitoring

  **WHY Each Reference Matters**:
  - backtest_loop.py is the execution entry point
  - walk_forward.py has the existing walk-forward methodology — reuse it
  - DuckDB schema tells us what tables to query for monitoring

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 100+ iterations completed
    Tool: Bash (Python + DuckDB)
    Preconditions: Optimization loop ran
    Steps:
      1. python -c "import duckdb; db=duckdb.connect('data/backtests/v8_optimization.duckdb'); print(db.sql('SELECT count(*) FROM iterations WHERE status=\\'completed\\'').fetchone()[0])"
      2. Verify count >= 100
    Expected Result: >= 100 completed iterations
    Failure Indicators: < 100 iterations (unless convergence stopped early — check convergence log)
    Evidence: .sisyphus/evidence/task-13-iteration-count.txt

  Scenario: Top config OOS fitness meets threshold
    Tool: Bash (Python + DuckDB)
    Preconditions: Walk-forward validation completed
    Steps:
      1. python -c "import duckdb; db=duckdb.connect('data/backtests/v8_optimization.duckdb'); print(db.sql('SELECT max(oos_fitness) FROM iterations').fetchone()[0])"
      2. Verify value >= 0.55
      3. Read v8_optimal_params.json — verify it contains all V8 parameters
    Expected Result: OOS fitness >= 0.55, optimal params JSON complete
    Failure Indicators: OOS < 0.55 (need more iterations or different parameter space), JSON incomplete
    Evidence: .sisyphus/evidence/task-13-oos-fitness.txt

  Scenario: Walk-forward validation confirms robustness
    Tool: Bash (Python)
    Preconditions: Walk-forward ran on top-3 configs
    Steps:
      1. Read v8_optimization_report.md
      2. Verify test-period results section exists
      3. Verify winning config has positive test-period P&L
    Expected Result: Walk-forward shows positive test-period performance
    Failure Indicators: Negative test-period P&L (overfitting to IS data)
    Evidence: .sisyphus/evidence/task-13-walkforward.txt
  ```

  **Commit**: YES
  - Message: `feat(backtest): v8 optimization complete — 100+ iterations, walk-forward validated`
  - Files: `data/backtests/v8_optimization.duckdb`, `data/backtests/v8_optimal_params.json`, `data/backtests/v8_optimization_report.md`
  - Pre-commit: N/A

- [x] 14. Port Optimal Parameters to V8 C# + Compile

  **What to do**:
  - Read optimal parameters from `data/backtests/v8_optimal_params.json`
  - Update DEEP6FootprintV8.cs default values for all optimized inputs:
    - `BiasLongThreshold` — from optimization
    - `BiasShortThreshold` — from optimization
    - `MinArrowConfluence` — from optimization
    - `MinExhaustionStrength` — from optimization
    - `MaxSignalsPerSession` — from optimization
    - Per-variant toggle defaults — if optimization preferred variant OFF, set default OFF
    - Any signal threshold adjustments within detection code (if optimization tuned cooldown, delta gate, etc.)
  - Ensure all values are within `param_bounds.py` ranges (validation check)
  - Compile: `nt8-compile.ps1` → SUCCESS
  - Run V8 on NT8 chart to verify it loads without errors

  **Must NOT do**:
  - Do NOT modify any detection LOGIC — only update DEFAULT VALUES and THRESHOLDS
  - Do NOT hardcode — all values must remain as `[NinjaScriptProperty]` inputs that users can override

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic parameter porting from JSON to C# property defaults
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after T13)
  - **Blocks**: Tasks 15, 16
  - **Blocked By**: Task 13

  **References**:

  **Pattern References**:
  - `data/backtests/v8_optimal_params.json` — Source of optimal values
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — Target file

  **WHY Each Reference Matters**:
  - JSON has the exact values to port — read each, find corresponding C# property, update default

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 compiles with optimal parameters
    Tool: Bash (PowerShell)
    Steps:
      1. Compile: powershell ninjatrader/scripts/nt8-compile.ps1 → SUCCESS
      2. Read v8_optimal_params.json — extract BiasLongThreshold value
      3. grep BiasLongThreshold in V8.cs — verify default matches JSON value
    Expected Result: Compiles, all defaults match optimal JSON
    Failure Indicators: Compile fails, defaults don't match JSON values
    Evidence: .sisyphus/evidence/task-14-optimal-compile.txt

  Scenario: All optimized values are within bounds
    Tool: Bash (Python)
    Steps:
      1. python -c "import json; p=json.load(open('data/backtests/v8_optimal_params.json')); assert 0.40 <= p['BiasLongThreshold'] <= 0.85; assert -0.85 <= p['BiasShortThreshold'] <= -0.40; print('All within bounds')"
    Expected Result: All values pass bounds check
    Failure Indicators: AssertionError — value outside bounds
    Evidence: .sisyphus/evidence/task-14-bounds-check.txt
  ```

  **Commit**: YES
  - Message: `feat(footprint): v8 optimized parameters ported from 100+ iteration backtest`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 8. Remove Killed Variants + Add Granular Visibility Toggles

  **What to do**:
  - In DEEP6FootprintV8.cs, apply the variant audit results from T5:
    - **KILL'd variants**: Remove their rendering code but keep detection logic intact. Add toggle input that defaults to OFF. The detection still runs (for potential future use) but no visual is drawn.
    - **KEEP'd variants**: Retain rendering, add per-variant toggle that defaults to ON.
    - **INCONCLUSIVE variants**: Keep detection, toggle defaults to OFF.
  - Add new `[NinjaScriptProperty]` inputs following the existing V7 pattern:
    - `ShowClassicAbsorption` (bool, Group "2. Display")
    - `ShowPassiveAbsorption` (bool, Group "2. Display")
    - `ShowStoppingVolume` (bool, Group "2. Display")
    - `ShowEffortVsResult` (bool, Group "2. Display")
    - `ShowZeroPrint` (bool, Group "2. Display")
    - `ShowExhaustionPrint` (bool, Group "2. Display")
    - `ShowThinPrint` (bool, Group "2. Display")
    - `ShowFatPrint` (bool, Group "2. Display")
    - `ShowFadingMomentum` (bool, Group "2. Display")
    - `ShowBidAskFade` (bool, Group "2. Display")
  - Default values based on audit verdicts: KEEP → true, KILL/INCONCLUSIVE → false
  - Wire each toggle into the respective `Draw*Marker()` method with an early return
  - Remove redundant variants identified in T7 correlation analysis (keep the better performer of each pair)
  - Compile and verify: `nt8-compile.ps1`

  **Must NOT do**:
  - Do NOT delete detection logic — only gate rendering behind toggle
  - Do NOT change the existing `ShowAbsorptionMarkers` / `ShowExhaustionMarkers` umbrella toggles — add new granular ones alongside them
  - Do NOT modify signal thresholds or detection conditions

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic C# editing with compile verification. Follows clear rules from audit data.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 compilation, NinjaScriptProperty conventions, Display attribute patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 9, 10, 11)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 5, 7

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — Target file (forked in T1)
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:145-159` — Existing `[NinjaScriptProperty]` + `[Display(..., GroupName="2. Display")]` pattern for input toggles
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:914-945` — Existing DrawAbsorptionMarker/DrawExhaustionMarker methods to gate

  **API/Type References**:
  - `data/backtests/v8_variant_audit_summary.md` — Keep/Kill/Inconclusive verdicts from T5
  - `data/backtests/v8_correlation_matrix.md` — Redundancy pairs from T7

  **WHY Each Reference Matters**:
  - V7 toggle pattern must be followed exactly — NT8 users expect consistent UI
  - Audit summary drives which toggles default ON vs OFF
  - Correlation matrix identifies which redundant variants to prioritize for removal

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 compiles with all new toggles
    Tool: Bash (PowerShell)
    Preconditions: V8 file modified with new toggles
    Steps:
      1. Compile: powershell ninjatrader/scripts/nt8-compile.ps1
      2. grep for "Show.*Absorption\|Show.*Exhaustion\|Show.*Print\|Show.*Volume\|Show.*Fade" in V8
      3. Count: should be 10 new toggle properties
    Expected Result: Compiles SUCCESS, 10 new granular toggles present
    Failure Indicators: Compile fails, missing toggles, wrong GroupName
    Evidence: .sisyphus/evidence/task-8-toggles-compile.txt

  Scenario: Kill'd variants default to OFF
    Tool: Bash (grep)
    Preconditions: V8 compiled with toggles
    Steps:
      1. For each KILL'd variant from audit: grep the default value in V8
      2. Verify: property initializer = false
      3. For each KEEP'd variant: verify default = true
    Expected Result: Kill'd → false, Keep'd → true, Inconclusive → false
    Failure Indicators: Kill'd variant defaults to true, Keep'd defaults to false
    Evidence: .sisyphus/evidence/task-8-toggle-defaults.txt
  ```

  **Commit**: YES
  - Message: `feat(footprint): v8 granular signal toggles + kill'd variants disabled`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 9. Fix Arrow Logic — Gate Behind Confluence Threshold

  **What to do**:
  - Apply arrow audit results from T6 to DEEP6FootprintV8.cs
  - For each of the 4 arrow systems:
    - `DrawTriggeredMarker()` — TYPE_A trade signals. If audit says KEEP: retain with existing confluence gate. If GATE: add minimum posterior threshold.
    - `DrawAbsorptionMarker()` — Raw absorption arrows. Gate behind confluence threshold: only draw if `ConfluenceCount >= MinArrowConfluence` (new input, default=3).
    - `DrawExhaustionMarker()` — Raw exhaustion arrows. Gate behind strength threshold: only draw if `s.Strength >= MinExhaustionStrength` (new input, default=0.65).
    - `RenderTier1Overlay()` — Pulsing animated arrows. If redundant with DrawTriggeredMarker: disable by default, add toggle.
  - Add new inputs:
    - `MinArrowConfluence` (int, range 1-7, default 3, Group "3. Signals")
    - `MinExhaustionStrength` (double, range 0.0-1.0, default 0.65, Group "3. Signals")
    - `ShowTriggeredArrows` (bool, default true, Group "2. Display")
    - `ShowTier1Overlay` (bool, default false, Group "2. Display")
  - Default all low-confidence arrows to OFF — user must explicitly enable them
  - Compile and verify

  **Must NOT do**:
  - Do NOT modify the arrow drawing API calls themselves — only add gating conditions
  - Do NOT change TYPE_A/B/C tier classification logic

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Targeted C# editing with clear rules from audit data
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 Draw API patterns, NinjaScriptProperty conventions

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 10, 11)
  - **Blocks**: Task 12
  - **Blocked By**: Task 6

  **References**:

  **Pattern References**:
  - `data/backtests/v8_arrow_audit.md` — Arrow system recommendations from T6
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:740` — DrawTriggeredMarker
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:914` — DrawAbsorptionMarker
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:927` — DrawExhaustionMarker
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:1849` — RenderTier1Overlay

  **API/Type References**:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs` — ConfluenceCount property used for gating
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/SignalTier.cs` — TYPE_A threshold reference

  **WHY Each Reference Matters**:
  - Arrow audit tells us exactly which systems to keep/gate/remove
  - Draw method line numbers are where to add `if (!ShowXxx || confluence < MinArrowConfluence) return;`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: V8 compiles with arrow gating logic
    Tool: Bash (PowerShell)
    Preconditions: Arrow gating added to V8
    Steps:
      1. Compile: powershell ninjatrader/scripts/nt8-compile.ps1
      2. grep for "MinArrowConfluence" in V8 → found
      3. grep for "MinExhaustionStrength" in V8 → found
      4. grep for "ShowTriggeredArrows" in V8 → found
    Expected Result: Compiles SUCCESS, all new inputs present
    Failure Indicators: Compile fails, missing gating inputs
    Evidence: .sisyphus/evidence/task-9-arrow-gate-compile.txt

  Scenario: Low-confluence arrows suppressed by default
    Tool: Bash (grep)
    Preconditions: V8 compiled
    Steps:
      1. Verify ShowTier1Overlay default = false
      2. Verify MinArrowConfluence default = 3
      3. Verify MinExhaustionStrength default = 0.65
    Expected Result: Conservative defaults that suppress noisy arrows
    Failure Indicators: Defaults allow all arrows through (MinConfluence=1 or MinStrength=0)
    Evidence: .sisyphus/evidence/task-9-arrow-defaults.txt
  ```

  **Commit**: YES (groups with T8)
  - Message: `feat(footprint): v8 arrow logic gated behind confluence threshold`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 10. Design + Implement Color-Coded Bias Box

  **What to do**:
  - Replace the exhaustion percentage diamond (`Draw.Diamond` + `Draw.Text` with `{strength}%`) in V8 with a directional bias box
  - **Algorithm design** (informed by T4 research and T5 audit):
    - Compute a directional bias score from the surviving signal variants
    - Score = weighted sum of recent absorption direction + exhaustion direction + strength
    - 3 output states:
      - **GREEN box "LONG"**: bias score > upper threshold (optimizable, initial default 0.60)
      - **RED box "SHORT"**: bias score < lower threshold (optimizable, initial default -0.60)
      - **GRAY box "—"**: between thresholds (neutral, no directional conviction)
    - Rendered as: `Draw.Rectangle` (colored) + `Draw.Text` ("LONG"/"SHORT"/"—") at the bar's signal price
    - One bias box per bar maximum
  - Add new inputs:
    - `ShowBiasBox` (bool, default true, Group "2. Display")
    - `BiasLongThreshold` (double, range 0.0-1.0, default 0.60, Group "3. Signals")
    - `BiasShortThreshold` (double, range -1.0-0.0, default -0.60, Group "3. Signals")
    - `ShowRawPercentage` (bool, default false, Group "2. Display") — keeps the old percentage available for debugging
  - Follow existing `SectorBrushForConfidence()` color-grading pattern from V7 (~lines 1377-1391) for consistency
  - Thresholds will be refined by optimization in T13 — use conservative defaults for now

  **Must NOT do**:
  - Do NOT hardcode final thresholds — they MUST be input properties for optimization
  - Do NOT render more than 1 bias box per bar
  - Do NOT modify the underlying strength calculation — only interpret it directionally
  - Do NOT add new detection logic — bias is derived from existing signals

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Algorithm design + C# implementation + visual rendering. Needs careful thought on bias score computation.
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]
    - `nt8-expert`: NT8 Draw API, NinjaScriptProperty patterns
    - `nt8-visual-design`: SharpDX rendering conventions, color system, visual design rules

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 9, 11)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 4, 5

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs:927-945` — Existing DrawExhaustionMarker() with Diamond + Text (replace this)
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:1377-1391` — SectorBrushForConfidence() color-grading pattern (simplified to 3 states)
  - `data/backtests/v8_signal_clarity_research.md` — Bias algorithm recommendations from T4

  **API/Type References**:
  - `Draw.Rectangle(this, tag, false, barsAgo, price1, 0, price2, brush, brush, 50)` — NinjaScript rectangle drawing
  - `Draw.Text(this, tag, false, text, barsAgo, price, offset, color, font, alignment, null, null, 0)` — Text overlay

  **External References**:
  - `.claude/skills/nt8-visual-design/knowledge.md` — DEEP6 visual design system (color palette, typography)

  **WHY Each Reference Matters**:
  - ExhaustionMarker code is what we're replacing — understand the current rendering before modifying
  - SectorBrushForConfidence shows how V7 already does color-grading — follow the same brush selection pattern
  - Visual design skill has the institutional color palette — bias box must match DEEP6 aesthetics

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Bias box renders 3 states correctly
    Tool: Bash (PowerShell + grep)
    Preconditions: V8 compiled with bias box code
    Steps:
      1. Compile: powershell ninjatrader/scripts/nt8-compile.ps1 → SUCCESS
      2. grep for "Draw.Rectangle.*LONG\|Draw.Rectangle.*SHORT" in V8 → matches found
      3. grep for "BiasLongThreshold\|BiasShortThreshold" in V8 → found as NinjaScriptProperty
      4. Verify ShowRawPercentage input exists with default=false
    Expected Result: 3-state rendering code present, thresholds are configurable inputs
    Failure Indicators: Hardcoded thresholds, missing states, no ShowRawPercentage fallback
    Evidence: .sisyphus/evidence/task-10-bias-box-compile.txt

  Scenario: Only 1 bias box per bar rendered
    Tool: Bash (grep)
    Preconditions: V8 compiled
    Steps:
      1. Search V8 for bias box tag generation logic
      2. Verify tag includes bar index (e.g., "BiasBox_" + CurrentBar) ensuring uniqueness per bar
      3. Verify no loop that could draw multiple boxes per bar
    Expected Result: One unique tag per bar, no multi-box-per-bar logic
    Failure Indicators: Tag doesn't include bar index, or loop drawing multiple boxes
    Evidence: .sisyphus/evidence/task-10-bias-box-uniqueness.txt
  ```

  **Commit**: YES (groups with T8, T9)
  - Message: `feat(footprint): v8 directional bias box (green LONG / red SHORT / gray NEUTRAL)`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 11. Add Signal Frequency Limiter

  **What to do**:
  - Add a per-session signal frequency limiter to V8 to prevent label clutter
  - Implement:
    - `MaxSignalsPerSession` (int, range 0-50, default 15, Group "3. Signals") — 0 = unlimited
    - Session counter that resets on session break (RTH open)
    - When limit reached, stop drawing new signals for remainder of session (still detect, just don't draw)
    - Priority system: higher-grade signals (S/A) can still draw even at limit, displacing lower-grade signals
  - Use existing session detection logic from V7 (session break detection via `Bars.IsFirstBarOfSession`)
  - Compile and verify

  **Must NOT do**:
  - Do NOT modify signal detection — only gate rendering output
  - Do NOT prevent logging/alerting when limit reached — only visual rendering

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple counter + conditional rendering. Clear implementation pattern.
  - **Skills**: [`nt8-expert`]

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 8, 9, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 5, 7

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs` — Target file
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs` — Session break detection pattern (`Bars.IsFirstBarOfSession`)

  **API/Type References**:
  - `Bars.IsFirstBarOfSession` — NinjaScript session boundary detection

  **WHY Each Reference Matters**:
  - Session break detection already exists in V7 — reuse the same pattern for counter reset

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Frequency limiter input exists and compiles
    Tool: Bash (PowerShell + grep)
    Steps:
      1. Compile: powershell ninjatrader/scripts/nt8-compile.ps1 → SUCCESS
      2. grep "MaxSignalsPerSession" V8 → found as NinjaScriptProperty
      3. grep "IsFirstBarOfSession" V8 → found (session reset logic)
    Expected Result: Compiles, input exists, session reset wired
    Evidence: .sisyphus/evidence/task-11-frequency-limiter.txt
  ```

  **Commit**: YES (groups with T8, T9, T10)
  - Message: `feat(footprint): v8 signal frequency limiter per session`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV8.cs`
  - Pre-commit: `powershell ninjatrader/scripts/nt8-compile.ps1`

- [x] 5. Run 10-Variant Performance Audit

  **What to do**:
  - Using the evaluator from T2 and parity-validated Python from T3, run all 10 signal variants through forward-return analysis
  - Run each variant independently: `python -m deep6.backtest.variant_evaluator --variant {VARIANT} --data data/backtests/nq_1yr_1m.csv --bars-forward 10 --bars-forward 20 --bars-forward 30`
  - Variants to test: ABS_01 (Classic), ABS_02 (Passive), ABS_03 (Stopping Volume), ABS_04 (Effort vs Result), EXH_01 (Zero Print), EXH_02 (Exhaustion Print), EXH_03 (Thin Print), EXH_04 (Fat Print), EXH_05 (Fading Momentum), EXH_06 (Bid/Ask Fade)
  - Apply verdict criteria per variant:
    - **KEEP**: OOS hit rate ≥ 55% AND R:R ≥ 1.5 AND N ≥ 30 OOS occurrences
    - **KILL**: OOS hit rate < 50% AND N ≥ 30 (statistically worse than random)
    - **INCONCLUSIVE**: N < 30 OOS occurrences — retain with toggle OFF by default
  - Record all results in `data/backtests/v8_variant_audit.duckdb`
  - Generate summary report: `data/backtests/v8_variant_audit_summary.md`

  **Must NOT do**:
  - Do NOT modify any signal detection code
  - Do NOT reject variants with insufficient sample (N < 30) — mark as "inconclusive, retain"
  - Do NOT test composite signals — each variant runs in complete isolation

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Statistical evaluation requiring careful interpretation of results, multiple variant runs, convergence assessment
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7)
  - **Blocks**: Tasks 8, 10, 11, 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `deep6/backtest/variant_evaluator.py` — Built in T2, the tool to run
  - `deep6/backtest/fitness.py` — Fitness criteria reference (>55% WR, >1.5 R:R, IS/OOS split 68/32)
  - `data/backtests/v8_parity_report.md` — From T3, confirms which Python version to trust

  **API/Type References**:
  - `deep6/engines/signal_config.py` — Variant names and threshold definitions
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs` — Signal flag enumeration (maps variant names to enum values)

  **WHY Each Reference Matters**:
  - Evaluator is the tool — run it per-variant with proper arguments
  - Fitness criteria from existing framework ensures consistency with other DEEP6 backtests
  - Parity report tells us whether Python results will accurately predict C# behavior

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 10 variants have results in DuckDB
    Tool: Bash (Python + DuckDB)
    Preconditions: Evaluator ran on all variants
    Steps:
      1. python -c "import duckdb; db=duckdb.connect('data/backtests/v8_variant_audit.duckdb'); print(db.sql('SELECT count(DISTINCT name) FROM variants').fetchone()[0])"
      2. Expected: 10
      3. python -c "import duckdb; db=duckdb.connect('data/backtests/v8_variant_audit.duckdb'); print(db.sql('SELECT name, verdict, oos_hit_rate, n_oos FROM variants ORDER BY name').fetchdf().to_string())"
      4. Verify each row has verdict in {KEEP, KILL, INCONCLUSIVE}
    Expected Result: 10 variants with verdicts, all hit_rates valid, all N counts > 0
    Failure Indicators: < 10 variants, missing verdicts, NaN values
    Evidence: .sisyphus/evidence/task-5-variant-audit.txt

  Scenario: KILL verdicts are statistically justified
    Tool: Bash (Python + DuckDB)
    Preconditions: Audit complete
    Steps:
      1. Query variants with verdict='KILL'
      2. For each: verify oos_hit_rate < 0.50 AND n_oos >= 30
      3. No variant should be KILL'd with N < 30
    Expected Result: Every KILL has sufficient sample AND sub-50% hit rate
    Failure Indicators: KILL with N < 30, or KILL with hit rate ≥ 50%
    Evidence: .sisyphus/evidence/task-5-kill-justification.txt
  ```

  **Commit**: YES (groups with T6, T7)
  - Message: `docs(footprint): v8 signal variant audit — 10 variants evaluated`
  - Files: `data/backtests/v8_variant_audit.duckdb`, `data/backtests/v8_variant_audit_summary.md`
  - Pre-commit: N/A

- [x] 6. Arrow System Audit — Evaluate All 4 Drawing Paths

  **What to do**:
  - V7 has 4 separate arrow/marker drawing systems. Audit each for predictive value:
    1. `DrawTriggeredMarker()` (~line 740) — Green/red arrows for TYPE_A trade signals
    2. `DrawAbsorptionMarker()` (~line 914) — Cyan/magenta triangles for absorption
    3. `DrawExhaustionMarker()` (~line 927) — Yellow/orange arrows for exhaustion
    4. `RenderTier1Overlay()` (~line 1849) — Pulsing animated arrows for TYPE_A signals
  - For each system, document: trigger condition, frequency (how many per session), visual overlap with other systems, and whether it adds information not already in another visual
  - Use the variant evaluator (T2) to measure forward-return of each arrow type independently
  - Recommend: which to KEEP (default ON), GATE (behind confluence threshold, default OFF), or REMOVE (not available)
  - **Critical insight from Metis**: "Arrows with no logical sense" likely means #2 and #3 fire on raw signals without confluence check. #1 and #4 fire on TYPE_A (high confluence) but may be visually redundant.

  **Must NOT do**:
  - Do NOT modify any arrow code yet — audit only
  - Do NOT combine arrow audit with signal variant audit — separate concerns

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires reading V7 C# code, understanding 4 drawing paths, cross-referencing with Python evaluation results
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: For understanding NinjaScript Draw.* API patterns and signal rendering conventions

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 7)
  - **Blocks**: Task 9
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:740` — DrawTriggeredMarker() method
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:914` — DrawAbsorptionMarker() method
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:927` — DrawExhaustionMarker() method
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:1849` — RenderTier1Overlay() method

  **API/Type References**:
  - `Draw.ArrowUp()`, `Draw.ArrowDown()`, `Draw.TriangleUp()`, `Draw.TriangleDown()` — NinjaScript drawing API
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/SignalTier.cs` — TYPE_A/B/C tier assignment logic

  **WHY Each Reference Matters**:
  - Each Draw method is a separate visual system — must understand trigger condition for each before deciding what to keep
  - SignalTier shows what "TYPE_A" means — highest confluence signals, the ones most likely to be valid

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 4 arrow systems documented with recommendations
    Tool: Bash (grep)
    Preconditions: Arrow audit report generated
    Steps:
      1. Verify report covers DrawTriggeredMarker, DrawAbsorptionMarker, DrawExhaustionMarker, RenderTier1Overlay
      2. Each system has: trigger condition, estimated frequency, recommendation (KEEP/GATE/REMOVE)
      3. Recommendations backed by forward-return data where available
    Expected Result: 4 systems documented with data-backed recommendations
    Failure Indicators: Missing system, no frequency estimate, recommendation without data
    Evidence: .sisyphus/evidence/task-6-arrow-audit.md
  ```

  **Commit**: YES (groups with T5, T7)
  - Message: `docs(footprint): arrow system audit — 4 drawing paths evaluated`
  - Files: `data/backtests/v8_arrow_audit.md`
  - Pre-commit: N/A

- [x] 7. Signal Overlap/Correlation Analysis

  **What to do**:
  - Using signal firing data from T5, analyze correlations between variants:
    - Which variants fire within N bars of each other (temporal overlap)?
    - Which variants fire at the same price level (spatial overlap)?
    - Pairwise correlation matrix for all 10 variants
  - Identify redundant pairs: if two variants have >85% temporal overlap, the weaker one is redundant
  - Identify complementary pairs: variants with <20% overlap that both have positive expectancy → candidates for combined signals
  - Output: `data/backtests/v8_correlation_matrix.md` with pairwise correlation heatmap data and redundancy recommendations

  **Must NOT do**:
  - Do NOT modify any signal code — analysis only
  - Do NOT over-optimize on correlation — focus on obvious redundancies

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Statistical analysis of signal co-occurrence patterns — moderate complexity
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 5, 6)
  - **Blocks**: Tasks 8, 11
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `data/backtests/v8_variant_audit.duckdb` — Signal firing timestamps and prices from T5
  - `deep6/backtest/signal_attribution.py` — Existing signal attribution analysis module (may have correlation utilities)
  - `data/backtests/analysis/signal_stats.csv` — Previous signal statistics for reference

  **WHY Each Reference Matters**:
  - DuckDB data from T5 has all signal firings — query for co-occurrence
  - signal_attribution.py may already have correlation calculation code to reuse
  - Previous signal stats show what analysis was done before

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Correlation matrix covers all variant pairs
    Tool: Bash (Python)
    Preconditions: T5 audit data available in DuckDB
    Steps:
      1. Read v8_correlation_matrix.md
      2. Verify 10×10 matrix (45 unique pairs)
      3. Verify redundancy section identifies pairs with >85% overlap
      4. Verify complementary section identifies pairs with <20% overlap
    Expected Result: Complete correlation matrix with clear redundancy/complementary identification
    Failure Indicators: Incomplete matrix, missing pairs, no recommendations
    Evidence: .sisyphus/evidence/task-7-correlation.txt
  ```

  **Commit**: YES (groups with T5, T6)
  - Message: `docs(footprint): signal correlation analysis — variant overlap matrix`
  - Files: `data/backtests/v8_correlation_matrix.md`
  - Pre-commit: N/A

- [x] 4. Research Professional Footprint Signal Clarity Practices

  **What to do**:
  - Research how professional footprint platforms handle signal display: ATAS, Bookmap, Sierra Chart, Exocharts, Jigsaw Daytradr
  - Focus on: How do they avoid label clutter? What visual hierarchy do they use? How do they show directional bias from order flow?
  - Look for: Signal filtering approaches, visual density management, trader-focused bias indicators
  - Specifically investigate: methods for deriving long/short bias from absorption/exhaustion signals
  - Document findings in `data/backtests/v8_signal_clarity_research.md`
  - Include concrete recommendations for V8's bias box algorithm design (inform Task 10)

  **Must NOT do**:
  - Do NOT implement anything — research only
  - Do NOT spend more than the equivalent of 30 minutes researching

  **Recommended Agent Profile**:
  - **Category**: Use `librarian` subagent directly (research task)
    - Reason: Pure research — finding best practices from external sources
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 10
  - **Blocked By**: None (can start immediately)

  **References**:

  **External References**:
  - ATAS platform documentation on signal display and filtering
  - Bookmap signal/alert display methodology
  - Sierra Chart order flow studies configuration
  - Exocharts signal filtering approach

  **Pattern References**:
  - `docs/FOOTPRINT-PATTERN-ATLAS.md` — Existing DEEP6 pattern reference (507 lines) — understand what we're already working with
  - `.planning/phases/11.2-ui-redesign/FOOTPRINT-REDESIGN-R6.md` — Previous visual redesign decisions

  **WHY Each Reference Matters**:
  - Professional platforms solved the clutter problem — learn from them instead of reinventing
  - FOOTPRINT-PATTERN-ATLAS shows our pattern vocabulary — research should complement it
  - Previous redesign (R6) shows what was already tried — don't repeat failed approaches

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Research covers at least 3 platforms
    Tool: Bash (grep)
    Preconditions: Research document generated
    Steps:
      1. Read data/backtests/v8_signal_clarity_research.md
      2. Verify ≥ 3 platform names mentioned (ATAS, Bookmap, Sierra Chart, Exocharts, Jigsaw)
      3. Verify "Bias Derivation" section exists with concrete algorithm recommendations
      4. Verify "Clutter Reduction" section exists with filtering approaches
    Expected Result: Structured research doc with platform comparisons and actionable recommendations
    Failure Indicators: Only 1 platform covered, no bias algorithm suggestions, vague recommendations
    Evidence: .sisyphus/evidence/task-4-research-summary.txt
  ```

  **Commit**: YES (groups with T3)
  - Message: `docs(footprint): signal clarity research from professional platforms`
  - Files: `data/backtests/v8_signal_clarity_research.md`
  - Pre-commit: N/A

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read V8 file, check toggles, query DuckDB for iteration count, check bias box rendering code). For each "Must NOT Have": search V8 for forbidden patterns (`AddDataSeries`, hardcoded thresholds, stacked bias boxes). Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `nt8-compile.ps1` for V8. Review V8 for: `as any` equivalent (`dynamic` casts), empty catch blocks, `Console.WriteLine` in prod, commented-out code, unused `using` statements. Check AI slop: excessive comments, over-abstraction, generic names. Verify V8 follows V7's coding patterns (same `[NinjaScriptProperty]` style, same `GroupName` conventions).
  Output: `Compile [PASS/FAIL] | Code Quality [N clean/N issues] | Pattern Compliance [N/N] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` + `nt8-expert` skill
  Load V8 onto NQ chart in NinjaTrader 8. Verify: (1) All toggles work (turn each on/off, confirm visual change), (2) Bias box renders correct colors on 5 known setups (2 long, 2 short, 1 neutral), (3) Signal count is reduced vs V7, (4) No CLA label clutter when default settings active, (5) Chart is visually clean and trader-readable. Save screenshots to `.sisyphus/evidence/final-qa/`.
  Output: `Toggles [N/N] | Bias Box [N/N correct] | Signal Count [V8 vs V7] | Visual [CLEAN/CLUTTERED] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual V8 diff (compare V7 vs V8). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance (no MTF, no FootprintBar changes, no ConfluenceScorer changes). Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Guardrails [N/N respected] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **After T1**: `feat(footprint): fork V7 → V8 skeleton` — DEEP6FootprintV8.cs
- **After T2**: `feat(backtest): add single-variant forward-return evaluator` — variant_evaluator.py
- **After Wave 2**: `docs(footprint): signal variant audit results` — v8_variant_audit.duckdb
- **After Wave 3**: `feat(footprint): v8 signal cleanup, toggles, bias box` — DEEP6FootprintV8.cs
- **After Wave 4**: `feat(footprint): v8 optimized parameters from 100+ iterations` — DEEP6FootprintV8.cs, v8_optimization.json
- **After Wave 5**: `feat(footprint): v8 integration verified` — evidence files

---

## Success Criteria

### Verification Commands
```bash
# V8 compiles
powershell ninjatrader/scripts/nt8-compile.ps1  # Expected: [COMPILE-RESULT] SUCCESS

# Optimization completed
python -c "import duckdb; db=duckdb.connect('data/backtests/v8_optimization.duckdb'); print(db.sql('SELECT count(*) FROM iterations WHERE status=\\'completed\\'').fetchone()[0])"  # Expected: >= 100

# OOS fitness meets threshold
python -c "import duckdb; db=duckdb.connect('data/backtests/v8_optimization.duckdb'); print(db.sql('SELECT max(oos_fitness) FROM iterations').fetchone()[0])"  # Expected: >= 0.55

# Signal count comparison (V8 ≤ V7)
python scripts/compare_signal_counts.py --v7 --v8  # Expected: V8 count ≤ V7 count
```

### Final Checklist
- [ ] V8 compiles cleanly in NinjaTrader 8
- [ ] All "Must Have" present (6 items)
- [ ] All "Must NOT Have" absent (10 guardrails)
- [ ] 100+ optimization iterations completed
- [ ] OOS fitness ≥ 0.55
- [ ] Bias box renders correctly on known setups
- [ ] V7 preserved untouched as rollback
- [ ] All visual elements individually toggleable
