# Hermes Autonomous Backtest Discovery Loop

## TL;DR

> **Quick Summary**: Build Hermes skills and a Python backtest harness that enables fully autonomous strategy discovery. Hermes iterates over 31 days of MBO data, generating entry model hypotheses targeting Depth Radar V2 walls and Volume Profile LVN/HVN zones, backtesting them, evaluating fitness (>55% WR, >1.5:1 R:R), and evolving strategies — writing all findings to an Obsidian vault as persistent memory.
> 
> **Deliverables**:
> - MBO pre-processor (raw MBO → FootprintBars + WallEvents, run once)
> - WallDetector adapted from WallLabeler for replay-mode inference
> - StrategyConfig dataclass (config-driven strategy representation, not arbitrary code)
> - Python CLI backtest harness with IS/OOS split, DuckDB storage, Obsidian integration
> - Strategy mutation engine for hypothesis evolution
> - Hermes skill: `hermes-backtest-discovery` (.claude/skills/)
> - Obsidian vault extensions (brain/Backtest-Loop.md, templates, findings)
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 3 waves + final verification
> **Critical Path**: T1 (StrategyConfig) → T7 (Harness) → T13 (Loop Script) → T12 (Skill) → T14 (Smoke Test) → F1-F4

---

## Context

### Original Request
Build a backtesting engine that Hermes runs in an autonomous loop over 31 days of MBO data, targeting the Depth Radar V2 and Volume Profile level indicators. Discover strong entry models through iterative strategy evolution. Use Obsidian vault as persistent brain/memory. This is an ongoing, forever project.

### Interview Summary
**Key Discussions**:
- **Autonomy**: Full autonomy — Hermes generates hypotheses, codes, tests, evaluates, mutates. Reports only when fitness threshold met.
- **Entry models**: Unconstrained discovery — Hermes generates novel entry hypotheses from data patterns
- **Fitness**: Win rate >55% with R:R >1.5:1
- **Exits**: Both bracket (fixed stop/target) AND level-based exits — Hermes experiments with both
- **Persistence**: Markdown journal in Obsidian (human-readable) + DuckDB (machine-queryable)
- **Iteration**: Loop until threshold met (could be 5 or 50 iterations)
- **Indicator tuning**: Parameters yes, core logic no
- **Indicators**: Depth Radar V2 (ML wall classification) + Volume Profile (LVN/HVN zones)

**Research Findings**:
- Depth Radar V2 has trained LightGBM models (4-class: GENUINE/SPOOF/ICEBERG/STALE), 15-feature extractor, WallLabeler for MBO processing — all standalone Python
- Volume Profile Engine has FootprintBar input, zone lifecycle FSM, configurable thresholds — replay-friendly
- Existing backtesting infrastructure: MBOAdapter (MBO replay), ReplayEngine, TradeSimulator, ParamSweep, WalkForward
- MBO data: `NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst` (6.69GB compressed, 31 days)
- Obsidian vault at `C:\Users\Tea\Documents\Project\trading-vault\` with brain/, templates/, established conventions
- 27 existing Hermes skills follow `.claude/skills/name/` with SKILL.md + knowledge.md

### Metis Review
**Critical Gaps Identified** (all addressed in this plan):
- **Strategy representation**: Must be config-driven (StrategyConfig dataclass), NOT arbitrary Python code — prevents code injection, makes mutations tractable
- **MBO pre-processing**: Raw MBO replay takes hours per iteration. Must pre-process ONCE into intermediate format (FootprintBars + WallEvents), then iterate against pre-processed data
- **WallDetector missing**: No component exists to detect walls from MBO events during replay. WallLabeler has the logic but is designed for label generation, not inference. Must be adapted.
- **Overfitting protection**: 31 days + 50+ iterations = guaranteed overfit without IS/OOS split (21/10 days), minimum 30 trades, walk-forward validation
- **Parameter bounds**: Every tunable parameter needs [min, max] or Hermes will set degenerate values
- **Entry model vocabulary**: "Unconstrained" needs building blocks (signal conditions, zone interactions, wall classifications, timing filters) — not arbitrary code
- **Transaction costs**: Must include slippage + $4.12/RT commission

---

## Work Objectives

### Core Objective
Enable Hermes to autonomously discover, evaluate, and evolve NQ entry models that target Depth Radar V2 wall classifications and Volume Profile LVN/HVN zones, using 31 days of MBO data as a fixed evaluation dataset, with all knowledge persisted in an Obsidian vault.

### Concrete Deliverables
- `deep6/backtest/strategy_config.py` — StrategyConfig dataclass with entry/exit vocabulary
- `deep6/backtest/param_bounds.py` — Parameter bounds registry
- `deep6/backtest/wall_detector.py` — Wall detection from MBO events (adapted from WallLabeler)
- `scripts/preprocess_mbo.py` — One-time MBO → intermediate format converter
- `deep6/backtest/harness.py` — CLI backtest harness (config → metrics)
- `deep6/backtest/config_validator.py` — Bounds checking + contradiction detection
- `deep6/backtest/results_writer.py` — DuckDB + Obsidian integration
- `deep6/backtest/mutation_engine.py` — Strategy hypothesis evolution
- `deep6/backtest/fitness.py` — IS/OOS evaluator + fitness scoring
- `scripts/backtest_loop.py` — Loop orchestration script Hermes invokes
- `.claude/skills/hermes-backtest-discovery/SKILL.md` — Hermes skill entry point
- `.claude/skills/hermes-backtest-discovery/knowledge.md` — Master reference
- `trading-vault/brain/Backtest-Loop.md` — Obsidian brain index for loop state
- DuckDB schema: `data/backtests/discovery_loop.duckdb` with 3 tables

### Definition of Done
- [ ] `python scripts/preprocess_mbo.py` completes without error on 31-day MBO file
- [ ] `python -m deep6.backtest.harness --config test.yaml --validate` passes known-trade assertion
- [ ] Hermes invocation with `-s hermes-backtest-discovery` completes 3 full iterations
- [ ] DuckDB contains 3+ rows in `iterations` table after smoke test
- [ ] Obsidian vault contains 3+ new files in `findings/` after smoke test
- [ ] IS/OOS split produces different metrics (not identical — proves split works)

### Must Have
- Config-driven strategy representation (StrategyConfig dataclass)
- MBO pre-processing (run once, iterate many)
- Depth Radar V2 wall classification in replay mode
- Volume Profile LVN/HVN zone detection in replay mode
- IS/OOS validation split (days 1-21 / days 22-31)
- Minimum 30 trades for fitness evaluation
- Transaction costs in P&L ($4.12/RT + 1 tick slippage)
- DuckDB metrics storage (3 tables: iterations, trades, strategies)
- Obsidian vault integration (findings, backtest results, brain index)
- Parameter bounds on ALL tunable values
- Iteration budget (50 iterations before forced checkpoint/report)

### Must NOT Have (Guardrails)
- G1: **No arbitrary Python code as strategies** — StrategyConfig only, harness interprets
- G2: **No skipping OOS validation** — every strategy evaluated on IS AND OOS
- G3: **No strategies with <30 trades** — rejected automatically
- G4: **No modification of core indicator logic** — WallClassifier.classify(), SessionProfile.detect_zones(), WallFeatureExtractor are frozen
- G5: **No Obsidian brain/ modifications** — Hermes creates NEW files in findings/, 04-backtests/, 02-strategies/; NEVER modifies existing brain/ notes
- G6: **No parameters outside bounds** — harness rejects with specific error message
- G7: **No infinite loops** — single backtest timeout 15 min, total iteration budget 50
- G8: **No retraining ML models** — use existing depth_radar_classifier_4class.joblib as-is

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, tests_v2/)
- **Automated tests**: YES (tests-after — write tests for harness, config validator, mutation engine)
- **Framework**: pytest (existing in project)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Python modules**: Use Bash (pytest, python -c) — run functions, assert outputs
- **CLI scripts**: Use Bash — invoke with test args, validate stdout + exit code + file outputs
- **Hermes skills**: Use Bash (wsl hermes) — invoke skill, verify completion
- **Obsidian writes**: Use Bash (python validation script) — parse YAML frontmatter, assert fields

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation, 6 parallel tasks):
├── Task 1: StrategyConfig dataclass + entry/exit vocabulary [quick]
├── Task 2: DuckDB schema + creation script [quick]
├── Task 3: WallDetector adapted from WallLabeler [deep]
├── Task 4: MBO pre-processor script [deep]
├── Task 5: Obsidian vault extensions [quick]
└── Task 6: Parameter bounds registry [quick]

Wave 2 (After Wave 1 — harness core, 5 parallel tasks):
├── Task 7: Backtest harness CLI core (depends: 1, 3, 4, 6) [deep]
├── Task 8: Config validator (depends: 1, 6) [quick]
├── Task 9: Results writer - DuckDB + Obsidian (depends: 2, 5) [unspecified-high]
├── Task 10: Strategy mutation engine (depends: 1, 6) [deep]
└── Task 11: IS/OOS evaluator + fitness scoring (depends: 1) [unspecified-high]

Wave 3 (After Wave 2 — skills + integration, 3 tasks):
├── Task 12: hermes-backtest-discovery Hermes skill (depends: 7-11) [writing]
├── Task 13: Loop orchestration script (depends: 7, 8, 9, 10, 11) [deep]
└── Task 14: Integration smoke test — 3 iterations (depends: 12, 13) [unspecified-high]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: T1 → T7 → T13 → T12 → T14 → F1-F4 → user okay
Parallel Speedup: ~65% faster than sequential
Max Concurrent: 6 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | - | T7, T8, T10, T11 | 1 |
| T2 | - | T9 | 1 |
| T3 | - | T7 | 1 |
| T4 | - | T7 | 1 |
| T5 | - | T9 | 1 |
| T6 | - | T7, T8, T10 | 1 |
| T7 | T1, T3, T4, T6 | T12, T13 | 2 |
| T8 | T1, T6 | T13 | 2 |
| T9 | T2, T5 | T13 | 2 |
| T10 | T1, T6 | T13 | 2 |
| T11 | T1 | T13 | 2 |
| T12 | T7-T11 | T14 | 3 |
| T13 | T7-T11 | T14 | 3 |
| T14 | T12, T13 | F1-F4 | 3 |

### Agent Dispatch Summary

- **Wave 1**: **6 tasks** — T1 → `quick`, T2 → `quick`, T3 → `deep`, T4 → `deep`, T5 → `quick`, T6 → `quick`
- **Wave 2**: **5 tasks** — T7 → `deep`, T8 → `quick`, T9 → `unspecified-high`, T10 → `deep`, T11 → `unspecified-high`
- **Wave 3**: **3 tasks** — T12 → `writing`, T13 → `deep`, T14 → `unspecified-high`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. StrategyConfig Dataclass + Entry/Exit Vocabulary

  **What to do**:
  - Create `deep6/backtest/strategy_config.py` with a frozen Pydantic `StrategyConfig` model
  - Define entry condition vocabulary as composable enums/dataclasses:
    - `LevelTarget`: which level type to target (LVN, HVN, VPOC, GENUINE_WALL, ICEBERG_WALL, ANY_WALL)
    - `ApproachDirection`: ABOVE, BELOW, EITHER
    - `ConfirmationSignal`: list of signal conditions from existing 44 signals (e.g., ABS_01 > threshold, DELT_03 active)
    - `TimingFilter`: session window (RTH_OPEN, LONDON, NY_AM, NY_PM, MIDDAY_BLOCK_EXCLUDED, ANY)
    - `MultiLevelConfluence`: optional requirement for N level types within M ticks
  - Define exit condition vocabulary:
    - `BracketExit`: stop_ticks (int), target_ticks (int), rr_ratio (float)
    - `LevelExit`: exit_at_next_zone (bool), trail_to_zone_boundary (bool)
    - `TimeExit`: max_bars_in_trade (int), session_end_flatten (bool)
  - Include `generation` (int), `parent_hash` (optional str), `mutation_type` (optional str) for lineage tracking
  - Include `hash()` method that produces deterministic strategy fingerprint
  - Write tests in `tests_v2/backtest/test_strategy_config.py` — validate serialization, hash determinism, enum coverage

  **Must NOT do**:
  - No arbitrary code fields (no `custom_entry_code: str` or `eval()`)
  - No fields without type constraints
  - No mutable config (must be frozen)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []
    - Pure Python dataclass design, no domain skills needed

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5, 6)
  - **Blocks**: Tasks 7, 8, 10, 11
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6v2/backtest/param_sweep.py:SweepParams` — Existing parameterized strategy config pattern, follow this structure
  - `deep6v2/types/signal.py:SignalId` — Enum of all 64 signal types, use for ConfirmationSignal references
  - `deep6v2/types/scoring.py:ScorerResult` — How scores are structured, reference for tier/direction fields

  **API/Type References**:
  - `deep6v2/types/bar.py:FootprintBar` — Input data type the strategy evaluates against
  - `deep6/engines/volume_profile.py:VolumeZone` — Zone dataclass (top_price, bot_price, direction, score, state)
  - `deep6/ml/depth_radar/classifier.py:WallClassifier` — Classification labels (GENUINE, SPOOF, ICEBERG, STALE)

  **External References**:
  - Pydantic v2 frozen models: https://docs.pydantic.dev/latest/concepts/models/#frozen-models

  **WHY Each Reference Matters**:
  - `SweepParams` shows how the project already parameterizes strategies — follow this convention
  - `SignalId` enum contains the complete signal vocabulary Hermes can reference in configs
  - `VolumeZone` and `WallClassifier` define what level data is available for entry conditions

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Valid config serialization roundtrip
    Tool: Bash (python -c)
    Preconditions: strategy_config.py exists
    Steps:
      1. python -c "from deep6.backtest.strategy_config import StrategyConfig, LevelTarget, BracketExit; c = StrategyConfig(level_target=LevelTarget.LVN, bracket_exit=BracketExit(stop_ticks=20, target_ticks=40, rr_ratio=2.0)); j = c.model_dump_json(); c2 = StrategyConfig.model_validate_json(j); assert c == c2; print('PASS')"
    Expected Result: stdout contains "PASS", exit code 0
    Evidence: .sisyphus/evidence/task-1-config-roundtrip.txt

  Scenario: Config hash is deterministic
    Tool: Bash (python -c)
    Preconditions: strategy_config.py exists
    Steps:
      1. python -c "from deep6.backtest.strategy_config import StrategyConfig, LevelTarget; c1 = StrategyConfig(level_target=LevelTarget.HVN); c2 = StrategyConfig(level_target=LevelTarget.HVN); assert c1.config_hash() == c2.config_hash(); c3 = StrategyConfig(level_target=LevelTarget.LVN); assert c1.config_hash() != c3.config_hash(); print('PASS')"
    Expected Result: stdout contains "PASS"
    Evidence: .sisyphus/evidence/task-1-config-hash.txt

  Scenario: Frozen config rejects mutation
    Tool: Bash (python -c)
    Preconditions: strategy_config.py exists
    Steps:
      1. python -c "from deep6.backtest.strategy_config import StrategyConfig, LevelTarget; c = StrategyConfig(level_target=LevelTarget.LVN); try: c.level_target = LevelTarget.HVN; print('FAIL - mutation allowed'); except Exception: print('PASS - frozen')"
    Expected Result: stdout contains "PASS - frozen"
    Evidence: .sisyphus/evidence/task-1-config-frozen.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(backtest): add strategy config, DuckDB schema, wall detector, MBO preprocessor, param bounds`
  - Files: `deep6/backtest/strategy_config.py`, `tests_v2/backtest/test_strategy_config.py`
  - Pre-commit: `pytest tests_v2/backtest/test_strategy_config.py -v`

- [x] 2. DuckDB Schema + Creation Script

  **What to do**:
  - Create `deep6/backtest/discovery_schema.py` with schema definition and creation function
  - Define exactly 3 tables with CHECK constraints matching parameter bounds:
    ```sql
    iterations (
      id INTEGER PRIMARY KEY,
      timestamp TEXT NOT NULL,
      strategy_hash TEXT NOT NULL,
      config_json TEXT NOT NULL,
      is_win_rate REAL, is_avg_rr REAL, is_profit_factor REAL, is_max_dd REAL,
      oos_win_rate REAL, oos_avg_rr REAL, oos_profit_factor REAL, oos_max_dd REAL,
      is_trade_count INTEGER, oos_trade_count INTEGER,
      status TEXT CHECK(status IN ('running','completed','failed','rejected')),
      parent_iteration_id INTEGER REFERENCES iterations(id),
      fitness_passed BOOLEAN DEFAULT FALSE
    )
    trades (
      id INTEGER PRIMARY KEY,
      iteration_id INTEGER REFERENCES iterations(id),
      split TEXT CHECK(split IN ('is','oos')),
      date TEXT, direction TEXT CHECK(direction IN ('LONG','SHORT')),
      entry_price REAL, exit_price REAL, pnl REAL,
      exit_reason TEXT, bars_held INTEGER,
      entry_time TEXT, exit_time TEXT,
      commission REAL DEFAULT 4.12
    )
    strategies (
      hash TEXT PRIMARY KEY,
      config_json TEXT NOT NULL,
      generation INTEGER DEFAULT 0,
      parent_hash TEXT,
      mutation_type TEXT,
      best_is_fitness REAL, best_oos_fitness REAL,
      first_seen TEXT, last_seen TEXT,
      times_tested INTEGER DEFAULT 1
    )
    ```
  - Add `create_discovery_db(path: str) -> duckdb.DuckDBPyConnection` function
  - Add convenience queries: `get_best_strategies(n=5)`, `get_iteration_history()`, `strategy_already_tested(hash) -> bool`
  - Write tests in `tests_v2/backtest/test_discovery_schema.py` — create, insert, query, constraint violations

  **Must NOT do**:
  - No additional tables beyond the 3 defined
  - No ad-hoc schema changes without updating this spec

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5, 6)
  - **Blocks**: Task 9
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/backtest/result_store.py:DuckDBResultStore` — Existing DuckDB pattern in the project, follow connection/table creation style
  - `data/backtests/replay_full_5sessions.duckdb` — Existing DuckDB file, same directory for new file

  **WHY Each Reference Matters**:
  - `DuckDBResultStore` shows how to create tables, insert rows, and manage connections in this project's style
  - Existing DuckDB files confirm `data/backtests/` is the correct directory

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Schema creation and basic CRUD
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.discovery_schema import create_discovery_db; db = create_discovery_db(':memory:'); db.execute(\"INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'abc123', '{}', 'completed')\"); r = db.execute('SELECT * FROM iterations').fetchone(); assert r[0] == 1; print('PASS')"
    Expected Result: stdout contains "PASS"
    Evidence: .sisyphus/evidence/task-2-schema-crud.txt

  Scenario: CHECK constraint rejects invalid status
    Tool: Bash (python -c)
    Steps:
      1. python -c "import duckdb; from deep6.backtest.discovery_schema import create_discovery_db; db = create_discovery_db(':memory:'); try: db.execute(\"INSERT INTO iterations (id, timestamp, strategy_hash, config_json, status) VALUES (1, '2026-01-01', 'x', '{}', 'INVALID')\"); print('FAIL'); except: print('PASS - constraint enforced')"
    Expected Result: stdout contains "PASS - constraint enforced"
    Evidence: .sisyphus/evidence/task-2-schema-constraint.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `deep6/backtest/discovery_schema.py`, `tests_v2/backtest/test_discovery_schema.py`

- [x] 3. WallDetector — Adapt WallLabeler for Replay Inference

  **What to do**:
  - Create `deep6/backtest/wall_detector.py` — a streaming wall detector that processes MBO events and produces classified wall snapshots
  - Adapt wall-tracking logic from `deep6/ml/depth_radar/labeler.py:WallLabeler` — it already tracks wall lifecycle (creation, modifications, cancellations, refills) but outputs training labels instead of inference results
  - Key class: `WallDetector` with methods:
    - `process_event(mbo_event: MBOEvent)` — update internal wall state
    - `get_active_walls() -> list[ClassifiedWall]` — return current walls with classification + confidence
    - `get_walls_at_bar_close(bar_ts: int) -> list[ClassifiedWall]` — snapshot of walls at a specific timestamp
  - `ClassifiedWall` dataclass: price, size, side, classification (GENUINE/SPOOF/ICEBERG/STALE), confidence, heat, persistence_sec, refill_count, features (15-element vector)
  - Integration: Load the trained 4-class model from `deep6/models/depth_radar_classifier_4class.joblib`
  - Use `WallFeatureExtractor` from `deep6/ml/depth_radar/wall_features.py` for feature computation
  - Include rule-based fallback (from DepthRadarV2Types.cs logic) when model confidence < 0.5
  - Write tests in `tests_v2/backtest/test_wall_detector.py` — mock MBO events, verify wall tracking, verify classification

  **Must NOT do**:
  - Do NOT modify `deep6/ml/depth_radar/labeler.py` — adapt logic into new file
  - Do NOT retrain the model — use existing joblib as-is
  - Do NOT modify `deep6/ml/depth_radar/wall_features.py` or `classifier.py`

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Complex adaptation requiring understanding of WallLabeler internals, MBO event format, and ML inference pipeline

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5, 6)
  - **Blocks**: Task 7
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/ml/depth_radar/labeler.py:WallLabeler` — Contains wall-tracking logic: wall creation from size threshold, modification tracking, cancellation detection, refill counting, lifecycle management. EXTRACT and ADAPT this logic.
  - `deep6/ml/depth_radar/wall_features.py:WallFeatureExtractor` — 15-feature vector extraction with z-score normalization. USE directly, do not reimplement.
  - `deep6/ml/depth_radar/classifier.py:WallClassifier` — LightGBM inference with `.classify(features) -> (label, confidence)`. USE directly.

  **API/Type References**:
  - `deep6/models/depth_radar_classifier_4class.joblib` — Trained 4-class model (602KB), load via `WallClassifier(model_path=...)`
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DepthRadarV2Types.cs:DepthRadarV2Logic` — Rule-based fallback: SpoofScore >= 70 → SPOOF, FreshnessScore < 0.1 → STALE, RefillCount >= 2 → ICEBERG, MaxSize >= WallMinSize → GENUINE
  - `deep6/backtest/mbo_adapter.py:MBOAdapter` — MBO event format that feeds into this detector

  **WHY Each Reference Matters**:
  - WallLabeler has the EXACT wall-tracking logic needed but outputs labels not predictions — adapter pattern
  - WallFeatureExtractor and WallClassifier are ready-to-use components — compose, don't rebuild
  - Rule-based fallback from V2Types.cs provides classification when model confidence is low

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Wall detection from synthetic MBO events
    Tool: Bash (pytest)
    Steps:
      1. pytest tests_v2/backtest/test_wall_detector.py -v -k "test_wall_creation"
    Expected Result: Wall created when bid order exceeds wall_min_size threshold, classification returned
    Evidence: .sisyphus/evidence/task-3-wall-creation.txt

  Scenario: Model classification produces valid labels
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.wall_detector import WallDetector; wd = WallDetector(model_path='deep6/models/depth_radar_classifier_4class.joblib'); print('Model loaded:', wd.classifier is not None); print('PASS')"
    Expected Result: "Model loaded: True" and "PASS"
    Evidence: .sisyphus/evidence/task-3-model-load.txt

  Scenario: Rule-based fallback when confidence low
    Tool: Bash (pytest)
    Steps:
      1. pytest tests_v2/backtest/test_wall_detector.py -v -k "test_rule_fallback"
    Expected Result: When mock classifier returns confidence < 0.5, rule-based classification kicks in
    Evidence: .sisyphus/evidence/task-3-rule-fallback.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `deep6/backtest/wall_detector.py`, `tests_v2/backtest/test_wall_detector.py`

- [x] 5. Obsidian Vault Extensions

  **What to do**:
  - Create `C:\Users\Tea\Documents\Project\trading-vault\brain\Backtest-Loop.md` — index file for the discovery loop state
    - YAML frontmatter: id, type (index), status (active), date, project (deep6), tags
    - Sections: Current Status, Best Strategies Found, Iteration Log (last 10), Parameter Insights, Findings Index
    - Follow pattern of existing `brain/Memories.md`
  - Create `C:\Users\Tea\Documents\Project\trading-vault\templates\backtest-iteration.md` — template for iteration results
    - YAML frontmatter: id, type (backtest-iteration), status, date, project, iteration_number, strategy_hash, fitness_passed, tags
    - Sections: Strategy Config, IS Results, OOS Results, Trade Summary, Mutation Applied, Connections
  - Create `C:\Users\Tea\Documents\Project\trading-vault\templates\strategy-hypothesis.md` — template for strategy hypotheses
    - YAML frontmatter: id, type (strategy-hypothesis), status (research/testing/validated/rejected), date, project, generation, parent_hash, tags
    - Sections: Hypothesis, Rationale, Config, Test Results, Mutations Spawned, Verdict
  - Follow existing vault conventions: YAML frontmatter, wiki links `[[]]`, trading-specific tags

  **Must NOT do**:
  - Do NOT modify existing brain/ files (Memories.md, Signals.md, etc.)
  - Do NOT modify existing templates
  - Do NOT reorganize vault structure

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4, 6)
  - **Blocks**: Task 9
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `C:\Users\Tea\Documents\Project\trading-vault\brain\Memories.md` — Index file pattern: YAML frontmatter, topic table, quick lookup table, cross-references
  - `C:\Users\Tea\Documents\Project\trading-vault\templates\finding.md` — Template pattern: YAML frontmatter fields, evidence table, connections section, confidence calibration, promotion tracker

  **API/Type References**:
  - `C:\Users\Tea\Documents\Project\trading-vault\CLAUDE.md` — Vault conventions: YAML frontmatter, trading-specific tags (#signal/*, #cr/*, #fsm/*), note naming (kebab-case), wiki links

  **WHY Each Reference Matters**:
  - Memories.md shows the exact format for brain/ index files — follow identically
  - finding.md shows frontmatter fields and section structure — templates must match this convention
  - CLAUDE.md defines the tagging taxonomy — use existing tags, add backtest-specific ones

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Brain index file has valid frontmatter
    Tool: Bash (python -c)
    Steps:
      1. python -c "import yaml; f = open('C:/Users/Tea/Documents/Project/trading-vault/brain/Backtest-Loop.md'); lines = f.readlines(); fm_start = lines.index('---\n'); fm_end = lines.index('---\n', fm_start+1); fm = yaml.safe_load(''.join(lines[fm_start+1:fm_end])); assert fm['type'] == 'index'; assert fm['project'] == 'deep6'; print('PASS')"
    Expected Result: "PASS"
    Evidence: .sisyphus/evidence/task-5-brain-frontmatter.txt

  Scenario: Templates have all required sections
    Tool: Bash (python -c)
    Steps:
      1. python -c "t = open('C:/Users/Tea/Documents/Project/trading-vault/templates/backtest-iteration.md').read(); assert '## Strategy Config' in t; assert '## IS Results' in t; assert '## OOS Results' in t; print('PASS')"
    Expected Result: "PASS"
    Evidence: .sisyphus/evidence/task-5-template-sections.txt
  ```

  **Commit**: NO (Obsidian vault is outside git repo)

- [x] 6. Parameter Bounds Registry

  **What to do**:
  - Create `deep6/backtest/param_bounds.py` with `PARAM_BOUNDS` dictionary defining min/max/default for every tunable parameter
  - Categories:
    - **Entry params**: level_approach_ticks (2-20), confirmation_threshold (0.3-0.9), multi_level_distance_ticks (2-50)
    - **Exit params**: stop_ticks (5-100), target_ticks (5-200), max_bars_in_trade (5-60), rr_ratio (0.5-5.0)
    - **Volume Profile params**: lvn_threshold (0.10-0.50), hvn_threshold (1.20-3.00), zone_decay_rate (0.005-0.10), min_zone_ticks (1-10), max_zones (5-100)
    - **Depth Radar params**: wall_min_size (20-200), wall_stale_sec (30-300), spoof_confidence_threshold (0.3-0.9), glow_threshold (50-500)
  - `ParamBound` dataclass: name, min, max, default, dtype, description
  - `validate_config(config: StrategyConfig) -> list[str]` — returns list of violation messages (empty = valid)
  - `clamp_config(config: StrategyConfig) -> StrategyConfig` — clamps out-of-bounds values to nearest valid value
  - Write tests in `tests_v2/backtest/test_param_bounds.py`

  **Must NOT do**:
  - No open-ended bounds (must have concrete min/max for every parameter)
  - No parameters without defaults

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4, 5)
  - **Blocks**: Tasks 7, 8, 10
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6v2/config/signals.py:SignalConfig` — Shows how signal thresholds are configured with defaults
  - `deep6/engines/volume_profile.py` — Current VP defaults: lvn_threshold=0.30, hvn_threshold=1.70, min_zone_ticks=2, max_zones=50, zone_decay_rate=0.02

  **WHY Each Reference Matters**:
  - SignalConfig shows the project's pattern for threshold configuration
  - Volume Profile defaults define the baseline values — bounds should center around these

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Validate rejects out-of-bounds parameter
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.param_bounds import validate_config; from deep6.backtest.strategy_config import StrategyConfig, BracketExit; c = StrategyConfig(bracket_exit=BracketExit(stop_ticks=999)); errors = validate_config(c); assert len(errors) > 0; assert 'stop_ticks' in errors[0]; print('PASS:', errors[0])"
    Expected Result: "PASS: stop_ticks 999 outside bounds [5, 100]"
    Evidence: .sisyphus/evidence/task-6-bounds-reject.txt

  Scenario: Clamp brings values within bounds
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.param_bounds import clamp_config; from deep6.backtest.strategy_config import StrategyConfig, BracketExit; c = StrategyConfig(bracket_exit=BracketExit(stop_ticks=999)); clamped = clamp_config(c); assert clamped.bracket_exit.stop_ticks == 100; print('PASS')"
    Expected Result: "PASS"
    Evidence: .sisyphus/evidence/task-6-bounds-clamp.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `deep6/backtest/param_bounds.py`, `tests_v2/backtest/test_param_bounds.py`

- [x] 4. MBO Pre-Processor Script

  **What to do**:
  - Create `scripts/preprocess_mbo.py` — CLI script that converts raw Databento MBO data into per-session intermediate files
  - Output format per session (one file per trading day):
    ```
    data/preprocessed/session_YYYY-MM-DD.pkl (or .parquet)
    {
      "date": "2026-03-17",
      "footprint_bars": list[FootprintBar],   # 1-minute bars with bid/ask volumes
      "wall_events": list[ClassifiedWall],     # walls detected per bar close
      "vp_zones": list[VolumeZone],            # LVN/HVN zones from SessionProfile
      "metadata": { "bar_count": N, "wall_count": N, "zone_count": N, "tick_count": N }
    }
    ```
  - Pipeline: raw MBO → MBOAdapter (tick-by-tick) → BarBuilder (FootprintBars) → WallDetector (ClassifiedWalls) → SessionProfile (VolumeZones)
  - CLI: `python scripts/preprocess_mbo.py --input <dbn.zst> --output-dir <dir> [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]`
  - Progress bar (tqdm) showing bytes processed / total
  - Checkpoint: if a session file already exists, skip that day (resume support)
  - Log summary at end: total sessions, total bars, total walls, total zones, processing time

  **Must NOT do**:
  - Do NOT process in real-time — this is batch pre-processing
  - Do NOT store raw MBO events in output (too large) — only derived data
  - Do NOT modify existing scripts/ files

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Complex data pipeline stitching together 4 components (MBOAdapter, BarBuilder, WallDetector, SessionProfile)

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5, 6)
  - **Blocks**: Task 7
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/backtest/mbo_adapter.py:MBOAdapter` — Existing MBO replay adapter, replays Databento events through on_tick/on_dom callbacks. Use this to stream MBO events.
  - `deep6v2/data/bar_builder.py:BarBuilder` — Constructs FootprintBars from tick data. Feed MBO ticks into this.
  - `scripts/replay_downloaded_mbo.py` — Existing MBO replay script, use as reference for Databento file loading pattern.

  **API/Type References**:
  - `deep6/engines/volume_profile.py:SessionProfile` — Call `add_bar(footprint_bar)` per bar to build volume profile, then `detect_zones()` for LVN/HVN
  - `data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst` — The input file (6.69GB compressed)

  **WHY Each Reference Matters**:
  - MBOAdapter is the proven MBO → callback bridge — don't reimplement
  - BarBuilder handles FootprintBar construction from raw ticks — already tested
  - SessionProfile accumulates volume profile from bars — already has detect_zones()

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Pre-process 1 day of MBO data
    Tool: Bash
    Steps:
      1. python scripts/preprocess_mbo.py --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst --output-dir C:\Users\Tea\AppData\Local\Temp\opencode\preprocess_test --start-date 2026-04-08 --end-date 2026-04-08
      2. python -c "import pickle; d = pickle.load(open('C:/Users/Tea/AppData/Local/Temp/opencode/preprocess_test/session_2026-04-08.pkl','rb')); print(f'Bars: {len(d[\"footprint_bars\"])}, Walls: {len(d[\"wall_events\"])}, Zones: {len(d[\"vp_zones\"])}'); assert len(d['footprint_bars']) > 0; print('PASS')"
    Expected Result: Non-zero bar count, script completes without error
    Failure Indicators: Exception during processing, empty output, 0 bars
    Evidence: .sisyphus/evidence/task-4-preprocess-1day.txt

  Scenario: Resume support skips existing sessions
    Tool: Bash
    Steps:
      1. Run preprocess on same date twice
      2. Second run should log "Skipping session_2026-04-08 (already exists)" and complete quickly
    Expected Result: Second run completes in <5 seconds
    Evidence: .sisyphus/evidence/task-4-preprocess-resume.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Files: `scripts/preprocess_mbo.py`

- [x] 7. Backtest Harness CLI Core

  **What to do**:
  - Create `deep6/backtest/harness.py` — the main CLI entry point that takes a StrategyConfig and runs a full backtest
  - CLI: `python -m deep6.backtest.harness --config <yaml> --data-dir <preprocessed_dir> [--validate] [--is-only] [--verbose]`
  - Core loop per session:
    1. Load pre-processed session file (FootprintBars + ClassifiedWalls + VolumeZones)
    2. For each bar: evaluate entry conditions against current state (walls, zones, signals)
    3. If entry condition met: open trade (long or short based on level direction)
    4. Track open trades: check exit conditions (bracket, level-based, time-based)
    5. Record trades with P&L including $4.12 commission + 1 tick slippage
  - IS/OOS split: automatically split sessions by date (configurable, default days 1-21 IS, 22-31 OOS)
  - `--validate` mode: runs a known config on 1 session, asserts exact trade count and P&L within $0.01
  - Output to stdout (JSON): `{ "is_metrics": {...}, "oos_metrics": {...}, "trade_count": N, "fitness_passed": bool }`
  - Use existing `TradeSimulator` patterns from `deep6v2/backtest/trade_simulator.py` as reference

  **Must NOT do**:
  - No arbitrary code execution (strategy is config-only)
  - No modifying pre-processed data files
  - No real-time MBO replay (pre-processed data only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Core trading logic, requires understanding of order flow, level interaction, trade simulation

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9, 10, 11)
  - **Blocks**: Tasks 12, 13
  - **Blocked By**: Tasks 1 (StrategyConfig), 3 (WallDetector types), 4 (pre-processed data format), 6 (param bounds)

  **References**:

  **Pattern References**:
  - `deep6v2/backtest/replay_engine.py:ReplayEngine` — Existing replay engine pattern: load data → iterate bars → evaluate signals → simulate trades. Follow structure.
  - `deep6v2/backtest/trade_simulator.py:TradeSimulator` — Trade execution simulation with entry/exit logic, stop/target, P&L tracking. Use as reference for trade management.
  - `deep6/backtest/bracket_exit.py:BracketExitTracker` — Bracket exit with slippage + commission. Reference for realistic fill simulation.

  **API/Type References**:
  - `deep6/backtest/strategy_config.py:StrategyConfig` — (Task 1) Input config to evaluate
  - `deep6/backtest/wall_detector.py:ClassifiedWall` — (Task 3) Wall data in pre-processed files
  - `deep6/engines/volume_profile.py:VolumeZone` — Zone data in pre-processed files
  - `deep6v2/types/bar.py:FootprintBar` — Bar data in pre-processed files

  **WHY Each Reference Matters**:
  - ReplayEngine shows the proven replay pattern — don't reinvent
  - TradeSimulator has working entry/exit/P&L logic — adapt, don't rebuild
  - BracketExitTracker handles realistic fills with slippage/commission — copy this pattern

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Validate mode passes with known config
    Tool: Bash
    Steps:
      1. python -m deep6.backtest.harness --config tests/fixtures/test_strategy.yaml --data-dir data/preprocessed/ --validate
    Expected Result: "VALIDATION PASS" in stdout, exit code 0
    Failure Indicators: Assertion error on trade count or P&L mismatch
    Evidence: .sisyphus/evidence/task-7-harness-validate.txt

  Scenario: IS/OOS split produces different metrics
    Tool: Bash
    Steps:
      1. python -m deep6.backtest.harness --config tests/fixtures/test_strategy.yaml --data-dir data/preprocessed/ --verbose 2>&1 | python -c "import sys,json; d=json.load(sys.stdin); assert d['is_metrics']['win_rate'] != d['oos_metrics']['win_rate'] or d['is_metrics']['trade_count'] != d['oos_metrics']['trade_count']; print('PASS - splits differ')"
    Expected Result: "PASS - splits differ"
    Evidence: .sisyphus/evidence/task-7-harness-split.txt

  Scenario: Harness rejects config with <30 trades
    Tool: Bash
    Steps:
      1. Create a config targeting extremely rare conditions (LVN + 5 confirmation signals)
      2. python -m deep6.backtest.harness --config rare_config.yaml --data-dir data/preprocessed/
      3. Check output for "REJECTED: insufficient trades"
    Expected Result: status "rejected", fitness_passed false, message about trade count
    Evidence: .sisyphus/evidence/task-7-harness-reject-trades.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(backtest): add harness CLI, config validator, results writer, mutation engine, fitness evaluator`
  - Files: `deep6/backtest/harness.py`, `tests/fixtures/test_strategy.yaml`
  - Pre-commit: `pytest tests_v2/backtest/ -x`

- [x] 8. Config Validator

  **What to do**:
  - Create `deep6/backtest/config_validator.py` with comprehensive validation
  - `validate(config: StrategyConfig) -> ValidationResult` where ValidationResult has: valid (bool), errors (list[str]), warnings (list[str])
  - Validation checks:
    - All parameters within bounds (from param_bounds.py)
    - No contradictory conditions (e.g., LevelTarget.LVN + LevelTarget.HVN simultaneously if mutually exclusive)
    - Exit rules make sense (target_ticks > stop_ticks when rr_ratio > 1.0)
    - At least one entry condition defined
    - At least one exit condition defined
    - Timing filter doesn't exclude entire trading session
  - `suggest_fix(errors: list[str]) -> dict[str, Any]` — for each error, suggest the nearest valid value
  - Write tests covering each validation rule

  **Must NOT do**:
  - No auto-fixing without explicit call to suggest_fix
  - No modifying the config in-place

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9, 10, 11)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 1 (StrategyConfig), 6 (param bounds)

  **References**:

  **Pattern References**:
  - `deep6/backtest/param_bounds.py:validate_config` — (Task 6) Bounds validation, extend with semantic validation

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Contradictory config rejected
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.config_validator import validate; from deep6.backtest.strategy_config import StrategyConfig, BracketExit; c = StrategyConfig(bracket_exit=BracketExit(stop_ticks=50, target_ticks=20, rr_ratio=2.0)); r = validate(c); assert not r.valid; assert any('target_ticks' in e for e in r.errors); print('PASS:', r.errors)"
    Expected Result: "PASS" with error about target < stop when rr > 1
    Evidence: .sisyphus/evidence/task-8-config-contradiction.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `deep6/backtest/config_validator.py`, `tests_v2/backtest/test_config_validator.py`

- [x] 9. Results Writer — DuckDB + Obsidian Integration

  **What to do**:
  - Create `deep6/backtest/results_writer.py` with `ResultsWriter` class
  - DuckDB writing:
    - `write_iteration(db_path, iteration_data)` — insert into iterations table
    - `write_trades(db_path, iteration_id, trades)` — insert into trades table
    - `upsert_strategy(db_path, strategy_config)` — insert/update strategies table
  - Obsidian writing:
    - `write_finding(vault_path, finding_data)` — creates `findings/finding-YYYYMMDD-backtest-{hash}.md` using vault template
    - `write_backtest_result(vault_path, iteration_data)` — creates `04-backtests/backtest-YYYYMMDD-iter-{N}.md`
    - `write_strategy_hypothesis(vault_path, strategy_data)` — creates `02-strategies/strategy-{hash}.md`
    - `update_brain_index(vault_path, iteration_summary)` — appends to brain/Backtest-Loop.md iteration log
  - All Obsidian writes use YAML frontmatter matching vault templates (from Task 5)
  - Include `read_brain_index(vault_path) -> str` for Hermes to read current state

  **Must NOT do**:
  - Do NOT modify existing Obsidian files (except brain/Backtest-Loop.md iteration log section)
  - Do NOT write to brain/ topic notes (Memories.md, Signals.md, etc.)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 10, 11)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 2 (DuckDB schema), 5 (Obsidian templates)

  **References**:

  **Pattern References**:
  - `deep6/backtest/result_store.py:DuckDBResultStore` — Existing DuckDB write pattern
  - `C:\Users\Tea\Documents\Project\trading-vault\templates\finding.md` — Template for findings (YAML frontmatter + evidence table + connections)
  - `C:\Users\Tea\Documents\Project\trading-vault\brain\Memories.md` — Brain index pattern

  **WHY Each Reference Matters**:
  - DuckDBResultStore shows proven insert pattern with error handling
  - finding.md template defines the EXACT YAML fields and section structure to produce
  - Memories.md shows how brain indexes reference other notes with `[[wiki links]]`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: DuckDB write + read roundtrip
    Tool: Bash (python -c)
    Steps:
      1. Create in-memory DuckDB, write iteration + trades, read back, verify
    Expected Result: All fields match, trade count correct
    Evidence: .sisyphus/evidence/task-9-duckdb-roundtrip.txt

  Scenario: Obsidian finding has valid YAML frontmatter
    Tool: Bash (python -c)
    Steps:
      1. Write a finding file to temp vault dir
      2. Parse YAML frontmatter, assert required fields (id, type, status, date, project, domain, confidence)
    Expected Result: All required fields present with correct types
    Evidence: .sisyphus/evidence/task-9-obsidian-frontmatter.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `deep6/backtest/results_writer.py`, `tests_v2/backtest/test_results_writer.py`

- [x] 10. Strategy Mutation Engine

  **What to do**:
  - Create `deep6/backtest/mutation_engine.py` with `MutationEngine` class
  - Mutation types (enum: `MutationType`):
    - `TWEAK_PARAMS`: adjust 1-2 numerical parameters by ±10-30%
    - `SWAP_LEVEL_TARGET`: change LevelTarget (LVN → HVN, GENUINE_WALL → ICEBERG_WALL)
    - `ADD_CONFIRMATION`: add a confirmation signal from the 44-signal vocabulary
    - `REMOVE_CONFIRMATION`: remove one confirmation signal (simplify)
    - `SWAP_EXIT`: change exit strategy (bracket → level-based, or adjust bracket params)
    - `CHANGE_TIMING`: change timing filter (NY_AM → LONDON, etc.)
    - `CROSSOVER`: combine traits from two parent strategies
    - `RANDOM`: generate a completely random valid config
  - `mutate(parent: StrategyConfig, mutation_type: MutationType = None) -> StrategyConfig`:
    - If mutation_type is None, select probabilistically (weighted by past success of mutation types)
    - Apply mutation, validate with config_validator, retry if invalid (max 5 retries)
    - Set generation = parent.generation + 1, parent_hash = parent.config_hash()
  - `generate_initial_population(n: int) -> list[StrategyConfig]` — create diverse seed strategies
  - `select_mutation_type(history: list[IterationResult]) -> MutationType` — bias toward mutation types that improved fitness in past iterations
  - All mutations must produce configs within param_bounds
  - Write comprehensive tests

  **Must NOT do**:
  - No mutations that produce arbitrary Python code
  - No mutations outside parameter bounds
  - No mutations that remove ALL entry or exit conditions

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Requires understanding of evolutionary strategy patterns, trading condition composition

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 9, 11)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 1 (StrategyConfig), 6 (param bounds)

  **References**:

  **Pattern References**:
  - `deep6v2/backtest/param_sweep.py:SweepParams` — Shows how parameter variations are structured
  - `deep6v2/types/signal.py:SignalId` — Complete signal vocabulary (64 signals) for ADD_CONFIRMATION mutation

  **WHY Each Reference Matters**:
  - SweepParams shows the project's existing parameter variation pattern
  - SignalId enum defines the vocabulary of signals Hermes can compose into strategies

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Mutation produces valid child config
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.mutation_engine import MutationEngine; from deep6.backtest.strategy_config import StrategyConfig, LevelTarget; me = MutationEngine(); parent = StrategyConfig(level_target=LevelTarget.LVN); child = me.mutate(parent); assert child.generation == parent.generation + 1; assert child.parent_hash == parent.config_hash(); print('PASS:', child.mutation_type)"
    Expected Result: "PASS" with mutation type shown
    Evidence: .sisyphus/evidence/task-10-mutation-valid.txt

  Scenario: Random generation produces diverse configs
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.mutation_engine import MutationEngine; me = MutationEngine(); pop = me.generate_initial_population(10); hashes = {c.config_hash() for c in pop}; assert len(hashes) >= 8; print(f'PASS: {len(hashes)} unique out of 10')"
    Expected Result: At least 8 unique configs out of 10
    Evidence: .sisyphus/evidence/task-10-mutation-diversity.txt

  Scenario: Mutation stays within parameter bounds
    Tool: Bash (python -c)
    Steps:
      1. python -c "from deep6.backtest.mutation_engine import MutationEngine; from deep6.backtest.param_bounds import validate_config; me = MutationEngine(); from deep6.backtest.strategy_config import StrategyConfig; parent = StrategyConfig(); children = [me.mutate(parent) for _ in range(20)]; errors = [validate_config(c) for c in children]; invalid = [e for e in errors if e]; assert len(invalid) == 0; print(f'PASS: 20/20 within bounds')"
    Expected Result: "PASS: 20/20 within bounds"
    Evidence: .sisyphus/evidence/task-10-mutation-bounds.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `deep6/backtest/mutation_engine.py`, `tests_v2/backtest/test_mutation_engine.py`

- [x] 11. IS/OOS Evaluator + Fitness Scoring

  **What to do**:
  - Create `deep6/backtest/fitness.py` with `FitnessEvaluator` class
  - `split_sessions(sessions: list[str], is_ratio=0.68) -> tuple[list[str], list[str]]` — split by date (default: 21/31 ≈ 68% IS)
  - `compute_metrics(trades: list[Trade]) -> Metrics` dataclass:
    - win_rate, avg_rr, profit_factor, sharpe_ratio, max_drawdown_dollars, total_pnl, trade_count, avg_bars_held, avg_pnl_per_trade
  - `evaluate_fitness(is_metrics: Metrics, oos_metrics: Metrics, min_trades=30) -> FitnessResult`:
    - `passed`: bool — True if ALL criteria met on BOTH IS and OOS:
      - win_rate >= 0.55
      - avg_rr >= 1.5
      - trade_count >= min_trades (on IS; OOS prorated: min_trades * oos_ratio)
    - `score`: float — composite fitness for ranking (weighted: win_rate * 0.3 + avg_rr * 0.3 + profit_factor * 0.2 + (1 - max_dd_pct) * 0.2)
    - `rejection_reasons`: list[str] — why it failed (if failed)
  - `compare_strategies(results: list[FitnessResult]) -> list[FitnessResult]` — rank by composite score
  - Transaction cost enforcement: every trade P&L reduced by $4.12 commission + 1 tick ($5.00 for NQ) slippage
  - Write tests with known trade sets that have known metrics

  **Must NOT do**:
  - No evaluating on IS only — OOS is mandatory
  - No accepting <30 trades as valid

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 9, 10)
  - **Blocks**: Task 13
  - **Blocked By**: Task 1 (StrategyConfig for Trade type)

  **References**:

  **Pattern References**:
  - `deep6v2/backtest/trade_simulator.py` — Trade P&L calculation with commission/slippage
  - `deep6/backtest/triple_barrier.py` — Exit reason categorization (stop/target/opposing/max_bars/session_end)
  - `deep6v2/backtest/round3_walkforward.py` — Existing IS/OOS split logic

  **WHY Each Reference Matters**:
  - TradeSimulator shows how P&L is calculated with costs — match this
  - triple_barrier categorizes exit reasons — use same categories
  - round3_walkforward has working IS/OOS split — reference for date-based splitting

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Known trades produce known metrics
    Tool: Bash (python -c)
    Steps:
      1. Create 10 trades: 6 winners (avg +$200), 4 losers (avg -$100). Assert win_rate=0.60, avg_rr=2.0, profit_factor=3.0
    Expected Result: Metrics match expected values within $0.01
    Evidence: .sisyphus/evidence/task-11-fitness-known.txt

  Scenario: Transaction costs reduce P&L
    Tool: Bash (python -c)
    Steps:
      1. Create 1 trade: entry=20000, exit=20010, direction=LONG. Raw P&L = $200. After costs: $200 - $4.12 - $5.00 = $190.88
    Expected Result: trade.pnl == 190.88
    Evidence: .sisyphus/evidence/task-11-fitness-costs.txt

  Scenario: <30 trades rejected
    Tool: Bash (python -c)
    Steps:
      1. Create 20 trades, evaluate fitness with min_trades=30
    Expected Result: FitnessResult.passed == False, "insufficient trades" in rejection_reasons
    Evidence: .sisyphus/evidence/task-11-fitness-reject.txt
  ```

  **Commit**: YES (groups with Wave 2)
  - Files: `deep6/backtest/fitness.py`, `tests_v2/backtest/test_fitness.py`

- [x] 12. Hermes Backtest Discovery Skill

  **What to do**:
  - Create `.claude/skills/hermes-backtest-discovery/SKILL.md` — entry point (24-40 lines)
    - Trigger patterns: "Run backtest loop", "Discover entry strategies", "Test entry models", "Backtest against MBO data", "Continue strategy evolution", "Run discovery iteration"
    - Workflow: 5 steps (read brain → generate/mutate config → run harness → evaluate → write results)
    - Dependencies: none (self-contained)
    - Base path absolute
  - Create `.claude/skills/hermes-backtest-discovery/knowledge.md` — master reference (300-500 lines)
    - **Identity**: Autonomous strategy discovery agent for DEEP6 NQ futures
    - **Iteration Protocol**: Step-by-step loop instructions (read state → decide strategy → run backtest → evaluate → write → decide next action)
    - **Data Paths**: Absolute paths to all files (preprocessed data, DuckDB, Obsidian vault, models, scripts)
    - **CLI Commands**: Exact commands to run harness, read results, write to vault
    - **Strategy Config Reference**: All fields, enums, valid values, parameter bounds
    - **Fitness Criteria**: >55% WR, >1.5 R:R, min 30 trades, IS+OOS
    - **Mutation Strategy**: When to mutate vs generate fresh, how to read DuckDB for past results
    - **Obsidian Write Protocol**: Which files to create, template format, brain/Backtest-Loop.md update procedure
    - **Guardrails**: G1-G8 from plan, iteration budget (50), single run timeout (15 min)
    - **Decision Trees**: What to do when fitness passes, when it fails, when <30 trades, when all mutations exhausted
    - **Example Iteration**: Full worked example of one iteration from start to finish
  - Register skill in CLAUDE.md under `<!-- GSD:skills-start -->` section

  **Must NOT do**:
  - No implementation code in skill files (markdown only)
  - No referencing non-existent scripts or paths
  - No vague instructions ("figure out the best approach") — every step must be concrete

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []
    - Technical writing task — skill documents are detailed reference material

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 13, 14)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 7-11 (all harness components must exist before documenting them)

  **References**:

  **Pattern References**:
  - `.claude/skills/hermes-sd-anchor/knowledge.md` — Complex Hermes skill with frozen doctrine, review checklist, scoring rubric (308 lines). Follow this level of detail.
  - `.claude/skills/rithmic-networking/SKILL.md` — Clean skill entry point pattern
  - `.claude/skills/tradingview-mcp-trading-operator/knowledge.md` — Workflow-oriented knowledge base with canonical tool sequences

  **WHY Each Reference Matters**:
  - hermes-sd-anchor shows the GOLD STANDARD for Hermes skill detail — doctrine lock, step-by-step, no ambiguity
  - rithmic-networking shows clean SKILL.md structure with trigger patterns
  - tradingview-mcp-trading-operator shows how to document tool sequences concretely

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SKILL.md has all required sections
    Tool: Bash (python -c)
    Steps:
      1. python -c "s = open('.claude/skills/hermes-backtest-discovery/SKILL.md').read(); assert 'Invoke this skill' in s; assert '## Workflow' in s; assert 'Base path' in s; print('PASS')"
    Expected Result: "PASS"
    Evidence: .sisyphus/evidence/task-12-skill-structure.txt

  Scenario: knowledge.md references only existing files
    Tool: Bash (python -c)
    Steps:
      1. Extract all file paths from knowledge.md, verify each exists on disk
    Expected Result: All referenced paths exist
    Evidence: .sisyphus/evidence/task-12-skill-paths.txt

  Scenario: knowledge.md has complete iteration protocol
    Tool: Bash (python -c)
    Steps:
      1. python -c "k = open('.claude/skills/hermes-backtest-discovery/knowledge.md').read(); required = ['## Iteration Protocol', '## Data Paths', '## CLI Commands', '## Strategy Config', '## Fitness Criteria', '## Mutation Strategy', '## Obsidian Write Protocol', '## Guardrails']; missing = [r for r in required if r not in k]; assert len(missing) == 0, f'Missing: {missing}'; print('PASS')"
    Expected Result: "PASS" — all required sections present
    Evidence: .sisyphus/evidence/task-12-skill-sections.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(hermes): add backtest-discovery skill, loop orchestrator, integration test`
  - Files: `.claude/skills/hermes-backtest-discovery/SKILL.md`, `.claude/skills/hermes-backtest-discovery/knowledge.md`

- [x] 13. Loop Orchestration Script

  **What to do**:
  - Create `scripts/backtest_loop.py` — the script Hermes actually invokes to run one iteration
  - This is a THIN orchestrator that chains the components:
    1. Read current state from DuckDB (last iteration, best strategies)
    2. Decide action: generate initial population (if first run) OR mutate best strategy OR try random
    3. Validate config (config_validator)
    4. Run harness (subprocess call to `python -m deep6.backtest.harness`)
    5. Parse harness output (JSON)
    6. Evaluate fitness
    7. Write results (DuckDB + Obsidian)
    8. Print summary to stdout for Hermes to read
  - CLI: `python scripts/backtest_loop.py --db <duckdb_path> --data-dir <preprocessed_dir> --vault <obsidian_vault_path> [--iteration N] [--action generate|mutate|random]`
  - Output summary format (stdout, Hermes reads this):
    ```
    === ITERATION {N} COMPLETE ===
    Strategy: {hash}
    Mutation: {type} from parent {parent_hash}
    IS Win Rate: {x}% | IS R:R: {y} | IS Trades: {n}
    OOS Win Rate: {x}% | OOS R:R: {y} | OOS Trades: {n}
    FITNESS: {PASSED|FAILED} (score: {s})
    Reason: {rejection_reasons or "All criteria met"}
    Best So Far: {best_hash} (score: {best_score})
    Iterations Remaining: {50 - current}
    Files Written: {list of Obsidian files created}
    === NEXT ACTION: {mutate best|explore random|REPORT - threshold met|CHECKPOINT - budget exhausted} ===
    ```
  - Iteration budget enforcement: after 50 iterations, output "CHECKPOINT" and stop
  - Dedup: check DuckDB if strategy hash already tested, skip if so

  **Must NOT do**:
  - No embedding the full backtest logic (delegate to harness via subprocess)
  - No infinite loops (budget enforced)
  - No modifying harness components

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []
    - Orchestration logic, state management, subprocess coordination

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 12, 14)
  - **Blocks**: Task 14
  - **Blocked By**: Tasks 7 (harness), 8 (validator), 9 (results writer), 10 (mutation engine), 11 (fitness)

  **References**:

  **Pattern References**:
  - `scripts/backtest_signals.py` — Existing backtest orchestration script pattern
  - `deep6v2/backtest/param_sweep.py` — Sweep orchestration with result collection

  **WHY Each Reference Matters**:
  - backtest_signals.py shows how scripts in this project are structured (argparse, logging, main())
  - param_sweep.py shows sweep orchestration pattern with result collection from multiple runs

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: First iteration generates initial strategy
    Tool: Bash
    Steps:
      1. python scripts/backtest_loop.py --db C:\Users\Tea\AppData\Local\Temp\opencode\test_loop.duckdb --data-dir data/preprocessed/ --vault C:\Users\Tea\AppData\Local\Temp\opencode\test_vault/ --action generate
    Expected Result: "ITERATION 1 COMPLETE" in stdout, DuckDB has 1 row in iterations, exit code 0
    Evidence: .sisyphus/evidence/task-13-loop-first.txt

  Scenario: Mutation iteration references parent
    Tool: Bash
    Steps:
      1. Run iteration 1 (generate), then iteration 2 (mutate)
      2. Check DuckDB: iteration 2 has parent_iteration_id = 1
    Expected Result: Parent linkage correct in DuckDB
    Evidence: .sisyphus/evidence/task-13-loop-mutation.txt

  Scenario: Budget exhaustion triggers checkpoint
    Tool: Bash (python -c)
    Steps:
      1. Set up DuckDB with 50 fake iterations, run loop
    Expected Result: "CHECKPOINT - budget exhausted" in output, no new iteration created
    Evidence: .sisyphus/evidence/task-13-loop-budget.txt
  ```

  **Commit**: YES (groups with Wave 3)
  - Files: `scripts/backtest_loop.py`

- [x] 14. Integration Smoke Test — 3 Full Iterations

  **What to do**:
  - This is NOT a code task — it's a verification task that runs the complete pipeline end-to-end
  - Pre-requisite: MBO data must be pre-processed (Task 4 output must exist)
  - Steps:
    1. Create fresh DuckDB at `data/backtests/smoke_test.duckdb`
    2. Create temp Obsidian vault directory with brain/Backtest-Loop.md
    3. Run 3 iterations: `python scripts/backtest_loop.py --action generate` → `--action mutate` → `--action mutate`
    4. Verify DuckDB: 3 rows in iterations, trades populated, strategies populated
    5. Verify Obsidian: 3+ files created in correct directories with valid YAML frontmatter
    6. Verify lineage: iteration 2 parent = iteration 1, iteration 3 parent = iteration 2
    7. Verify metrics: IS and OOS metrics present and different
    8. Test Hermes invocation: `wsl hermes chat -q "Read the backtest loop state and describe what strategies have been tested" -s hermes-backtest-discovery -Q --yolo --max-turns 4`
    9. Clean up temp files

  **Must NOT do**:
  - No writing production code — this is pure verification
  - No modifying the harness or loop script during testing

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`hermes-backtest-discovery`]
    - Needs the skill loaded to test Hermes invocation

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential after Tasks 12, 13
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 12 (skill), 13 (loop script), and pre-processed MBO data (Task 4)

  **References**:

  **Pattern References**:
  - All previous tasks — this integrates everything

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 3 iterations complete without error
    Tool: Bash
    Steps:
      1. Run scripts/backtest_loop.py 3 times (generate, mutate, mutate)
      2. Verify exit code 0 for all 3
      3. Verify "ITERATION {N} COMPLETE" in each output
    Expected Result: All 3 iterations complete, valid output
    Evidence: .sisyphus/evidence/task-14-smoke-3iter.txt

  Scenario: DuckDB contains correct data
    Tool: Bash (python -c)
    Steps:
      1. python -c "import duckdb; db = duckdb.connect('data/backtests/smoke_test.duckdb'); iters = db.execute('SELECT COUNT(*) FROM iterations').fetchone()[0]; trades = db.execute('SELECT COUNT(*) FROM trades').fetchone()[0]; strats = db.execute('SELECT COUNT(*) FROM strategies').fetchone()[0]; assert iters == 3; assert trades > 0; assert strats >= 1; print(f'PASS: {iters} iterations, {trades} trades, {strats} strategies')"
    Expected Result: 3 iterations, >0 trades, >=1 strategies
    Evidence: .sisyphus/evidence/task-14-smoke-duckdb.txt

  Scenario: Hermes can read loop state
    Tool: Bash (wsl)
    Steps:
      1. wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Read the backtest loop brain index and tell me how many iterations have been run' -s hermes-backtest-discovery -Q --yolo --max-turns 4 2>&1"
    Expected Result: Hermes responds with "3 iterations" or similar correct count
    Failure Indicators: Hermes can't find files, errors loading skill, wrong count
    Evidence: .sisyphus/evidence/task-14-smoke-hermes.txt
  ```

  **Commit**: NO (verification only, no code changes)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan. Verify DuckDB schema matches spec (3 tables, correct columns). Verify Obsidian files follow templates.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m pytest tests_v2/ -x --tb=short`. Review all new Python files for: `as any` patterns, empty except blocks, hardcoded paths (should use config), missing type hints, unused imports. Check AI slop: excessive comments, over-abstraction, generic variable names. Verify all dataclasses are frozen/immutable where appropriate.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Run full pipeline: preprocess MBO → run harness with test config → verify DuckDB populated → verify Obsidian files written → invoke Hermes with skill for 1 iteration → verify end-to-end. Test edge cases: invalid config, out-of-bounds params, <30 trades rejection. Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Pipeline [PASS/FAIL] | Edge Cases [N/N] | Hermes [PASS/FAIL] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check guardrails G1-G8 compliance. Verify no modification to WallClassifier, SessionProfile, or WallFeatureExtractor source. Flag any unaccounted files.
  Output: `Tasks [N/N compliant] | Guardrails [N/N] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Wave | Message | Files | Pre-commit |
|------|---------|-------|------------|
| 1 | `feat(backtest): add strategy config, DuckDB schema, wall detector, MBO preprocessor, param bounds` | deep6/backtest/*.py, scripts/preprocess_mbo.py | `pytest tests_v2/backtest/ -x` |
| 2 | `feat(backtest): add harness CLI, config validator, results writer, mutation engine, fitness evaluator` | deep6/backtest/*.py | `pytest tests_v2/backtest/ -x` |
| 3 | `feat(hermes): add backtest-discovery skill, loop orchestrator, integration test` | .claude/skills/hermes-backtest-discovery/*, scripts/backtest_loop.py | `pytest tests_v2/backtest/ -x` |

---

## Success Criteria

### Verification Commands
```bash
python scripts/preprocess_mbo.py --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst --output data/preprocessed/  # Expected: creates per-session files
python -m deep6.backtest.harness --config tests/fixtures/test_strategy.yaml --validate  # Expected: PASS with known trade count
python -m pytest tests_v2/backtest/ -v  # Expected: all pass
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Run one backtest iteration with default config' -s hermes-backtest-discovery -Q --yolo --max-turns 8 2>&1"  # Expected: completes with DuckDB row + Obsidian file
```

### Final Checklist
- [ ] All "Must Have" items present and verified
- [ ] All "Must NOT Have" guardrails (G1-G8) confirmed absent
- [ ] DuckDB has correct schema (iterations, trades, strategies tables)
- [ ] Obsidian vault has brain/Backtest-Loop.md index
- [ ] Hermes completes 3 iterations without error
- [ ] IS/OOS split produces different metrics
- [ ] Config validation rejects out-of-bounds parameters
- [ ] All tests pass
