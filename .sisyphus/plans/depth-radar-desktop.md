# Depth Radar V4 Desktop Application + MBO Model Training

## TL;DR

> **Quick Summary**: Build a standalone PySide6/Qt desktop application ("Depth Radar Desktop") that displays real-time wall detection and classification from the MBO wall engine, plus train V4 LightGBM models on Databento MBO data.
> 
> **Deliverables**:
> - Trained V4 intent classifier and interaction predictor models (LightGBM)
> - Standalone `depth_radar_desktop/` Python package with PySide6 GUI
> - Live panel: Active Walls table, Feature Gauges, Touch Alerts
> - Research panel: Episode Browser, Model Performance Dashboard
> - Dark trading terminal theme, Rithmic live connection, single-process architecture
> 
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 4 waves + final verification
> **Critical Path**: Task 1 → Task 4 → Task 11 → Task 12 → Task 16 → F1-F4

---

## Context

### Original Request
Build a standalone downloadable desktop application (like GEX Doctor software) that visualizes all Depth Radar V4 MBO data, and train the V4 models on existing Databento MBO files.

### Interview Summary
**Key Discussions**:
- Framework: PySide6/Qt — native Python, lightweight, professional trading tool feel
- Two-tab layout: Live (trading companion) + Research (after-hours analysis)
- Live panel: Active Walls Table, Feature Gauges, Touch/Interaction Alerts
- Research panel: Episode Browser (historical walls), Model Performance Dashboard
- Live data: Rithmic via async-rithmic (existing broker, free)
- Visual: Dark mode trading terminal (black/dark gray, green/red, monospace)
- Training: 3-day MBO first (quick validation), then 30-day for production
- Tests: Pragmatic — tests after for critical paths

**Research Findings**:
- 84/84 depth radar tests pass — engine is fully operational
- MBO Wall Engine processes events, detects walls, extracts 44 causal features
- V4 training pipeline ready at `scripts/train_depth_radar_v4.py`
- MBO data files: 6.4 GB (30-day) + 897 MB (3-day) at `data/databento/nq_mbo/raw_dbn/`
- LiveMBORadar already supports Rithmic source with synthetic order IDs
- CausalClassifier has graceful degradation when models are missing

### Metis Review
**Identified Gaps** (addressed):
- **asyncio↔Qt event loop conflict**: Resolved with dedicated asyncio thread + Qt Signal bridge (NOT qasync — fragile on Windows)
- **Model path resolution**: Must use absolute paths anchored to package root, not CWD-relative
- **Package placement**: Standalone `depth_radar_desktop/` at repo root (follows `gexdoctor/` pattern)
- **Rithmic credential config**: `.env` file loading at startup (matches existing project pattern)
- **Training in GUI vs CLI**: Training stays CLI-only; Research tab reads results from training output
- **Markets closed behavior**: Show "Markets Closed" with last session data frozen
- **Touch alerts form**: Visual only (row highlight, flash) for v1 — no OS toast/sound

---

## Work Objectives

### Core Objective
Deliver a production-quality standalone desktop application that serves as a real-time wall monitoring and classification tool during trading, and an episode analysis/model review tool after hours — plus produce trained V4 models from real MBO data.

### Concrete Deliverables
- `depth_radar_desktop/` — standalone PySide6 package at repo root
- `deep6/models/intent_classifier_v4.joblib` — trained V4 intent model
- `deep6/models/interaction_predictor_v4.joblib` — trained V4 interaction model
- Training output parquet files (episodes, snapshots, touches)
- Launch command: `python -m depth_radar_desktop`

### Definition of Done
- [ ] `python -m depth_radar_desktop` launches desktop app without errors
- [ ] Live tab shows Active Walls Table, Feature Gauges, Touch Alerts
- [ ] Research tab shows Episode Browser and Model Performance Dashboard
- [ ] V4 models load and classify walls with non-zero confidence
- [ ] All critical-path tests pass

### Must Have
- Dark trading terminal theme (black/dark gray, green/red accents, monospace data)
- Real-time wall updates from Rithmic via MBOWallEngine
- Connection status indicator (connected/disconnected/reconnecting)
- Graceful degradation when models not loaded or Rithmic unavailable
- Episode browser with filtering by intent, outcome, date range
- Model metrics display (F1, confusion matrix, feature importance)
- Single-process architecture (engine thread + Qt main thread)

### Must NOT Have (Guardrails)
- Chart rendering (candlestick, footprint, price charts — use TradingView)
- Order entry or position management
- Data download/management UI
- Multi-symbol support (NQ only for v1)
- Plugin/extension system
- User account/authentication
- Auto-update mechanism
- Custom indicator creation
- Backtesting from the GUI
- Training controls in the GUI (training is CLI-only)
- qasync dependency (undermaintained, fragile on Windows)
- Any GUI code inside `deep6/` or `deep6v2/` packages

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest + pytest-asyncio in project)
- **Automated tests**: Tests-after (pragmatic)
- **Framework**: pytest + pytest-qt for widget testing
- **Approach**: Build first, then add tests for critical paths (engine integration, data parsing, model loading, widget rendering)

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Training**: Use Bash — run training commands, verify output files, check metrics
- **GUI widgets**: Use pytest-qt — instantiate widgets, verify rendering, check data population
- **Engine integration**: Use Bash — run replay source, verify wall output, check feature extraction
- **Package**: Use Bash — install package, run entry point, verify launch

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — training + foundation, 5 parallel):
├── Task 1: Train V4 models on 3-day MBO file [quick]
├── Task 2: Create standalone package skeleton [quick]
├── Task 3: Dark trading terminal theme + constants [quick]
├── Task 4: asyncio↔Qt bridge layer [deep]
├── Task 5: App config + .env loading [quick]

Wave 2 (After Wave 1 — core widgets, 5 parallel):
├── Task 6: Active Walls QTableView + model (depends: 2, 3) [unspecified-high]
├── Task 7: Feature Gauges widget (depends: 2, 3) [visual-engineering]
├── Task 8: Touch/Interaction Alerts panel (depends: 2, 3) [unspecified-high]
├── Task 9: Connection status bar widget (depends: 2, 3) [quick]
├── Task 10: Main window + tab layout (depends: 2, 3) [unspecified-high]

Wave 3 (After Wave 2 — live pipeline + research, 5 parallel):
├── Task 11: Rithmic engine worker thread (depends: 4, 5) [deep]
├── Task 12: Live tab assembly (depends: 6, 7, 8, 9, 10, 11) [unspecified-high]
├── Task 13: Episode Browser widget (depends: 2, 3, 1) [unspecified-high]
├── Task 14: Model Performance Dashboard (depends: 2, 3, 1) [unspecified-high]
├── Task 15: Train V4 models on 30-day MBO file (depends: 1) [quick]

Wave 4 (After Wave 3 — integration + polish, 4 parallel):
├── Task 16: Full integration test + error handling (depends: 12, 13, 14) [deep]
├── Task 17: Graceful degradation + edge cases (depends: 12) [unspecified-high]
├── Task 18: Tests for critical paths (depends: 16) [unspecified-high]
├── Task 19: Package launch script + README (depends: 16) [quick]

Wave FINAL (After ALL — 4 parallel reviews, then user okay):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
├── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 13, 14, 15 | 1 |
| 2 | — | 6-10, 13, 14 | 1 |
| 3 | — | 6-10 | 1 |
| 4 | — | 11 | 1 |
| 5 | — | 11 | 1 |
| 6 | 2, 3 | 12 | 2 |
| 7 | 2, 3 | 12 | 2 |
| 8 | 2, 3 | 12 | 2 |
| 9 | 2, 3 | 12 | 2 |
| 10 | 2, 3 | 12 | 2 |
| 11 | 4, 5 | 12 | 3 |
| 12 | 6-11 | 16, 17 | 3 |
| 13 | 2, 3, 1 | 16 | 3 |
| 14 | 2, 3, 1 | 16 | 3 |
| 15 | 1 | — | 3 |
| 16 | 12, 13, 14 | 18, 19 | 4 |
| 17 | 12 | — | 4 |
| 18 | 16 | — | 4 |
| 19 | 16 | — | 4 |

### Agent Dispatch Summary

- **Wave 1**: 5 tasks — T1 → `quick`, T2 → `quick`, T3 → `quick`, T4 → `deep`, T5 → `quick`
- **Wave 2**: 5 tasks — T6 → `unspecified-high`, T7 → `visual-engineering`, T8 → `unspecified-high`, T9 → `quick`, T10 → `unspecified-high`
- **Wave 3**: 5 tasks — T11 → `deep`, T12 → `unspecified-high`, T13 → `unspecified-high`, T14 → `unspecified-high`, T15 → `quick`
- **Wave 4**: 4 tasks — T16 → `deep`, T17 → `unspecified-high`, T18 → `unspecified-high`, T19 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Train V4 Models on 3-Day MBO File

  **What to do**:
  - Run the existing training pipeline against the 3-day Databento MBO file
  - Execute: `python scripts/train_depth_radar_v4.py --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst --output-dir training_output/depth_radar_v4_3day`
  - Verify Stage 1 produces episodes, snapshots, and touches parquet files
  - Verify Stage 2 produces intent_classifier_v4.joblib with reasonable metrics (F1 > 0.3)
  - Verify Stage 3 produces interaction_predictor_v4.joblib (or skips with documented reason)
  - Verify Stage 5 copies models to `deep6/models/intent_classifier_v4.joblib` and `deep6/models/interaction_predictor_v4.joblib`
  - Capture full training stdout to `training_output/depth_radar_v4_3day/training_log.txt`
  - NOTE: This may take 10-30 minutes depending on CPU. The 3-day file is 897 MB compressed, ~3 GB uncompressed.

  **Must NOT do**:
  - Do NOT modify the training script itself — run it as-is
  - Do NOT skip Stage 1 labeling (no `--skip-label` flag for first run)
  - Do NOT run the 30-day file yet (that's Task 15)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: This is a CLI execution task — run a command and verify output. No code writing needed.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - None needed — this is pure CLI execution

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 13, 14, 15
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `scripts/train_depth_radar_v4.py` — The complete training pipeline. Read the `main()` function (line 487-553) to understand the 5-stage flow: labeling → intent → interaction → validate → copy.
  - `deep6/ml/depth_radar/episode_labeler.py:64-80` — `process_mbo_file()` method shows how MBO records become episodes. This is Stage 1.

  **API/Type References**:
  - `deep6/ml/depth_radar/episode.py` — `WallEpisode`, `WallIntent`, `InteractionOutcome` — the data classes that training produces
  - `deep6/ml/depth_radar/causal_features.py:CAUSAL_FEATURE_NAMES` — the 44 feature names that training uses as columns

  **Data References**:
  - `data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst` — 3-day MBO file (897 MB, Apr 8-11 2026)
  - `data/databento/nq_mbo/manifest.json` — File metadata and SHA256 checksums

  **WHY Each Reference Matters**:
  - The training script is run as-is — understanding its stages helps verify output at each step
  - Episode labeler shows what "success" looks like (episodes + snapshots + touches)
  - Causal features list ensures the model uses exactly 44 features (not more, not fewer)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Training pipeline completes successfully
    Tool: Bash
    Preconditions: CWD is C:\Users\Tea\DEEP6, Python 3.11+ available, lightgbm installed
    Steps:
      1. Run: python scripts/train_depth_radar_v4.py --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst --output-dir training_output/depth_radar_v4_3day 2>&1 | Tee-Object training_output/depth_radar_v4_3day/training_log.txt
      2. Assert exit code 0
      3. Assert file exists: training_output/depth_radar_v4_3day/episodes.parquet
      4. Assert file exists: training_output/depth_radar_v4_3day/snapshots.parquet
      5. Assert file exists: training_output/depth_radar_v4_3day/touches.parquet
      6. Assert file exists: training_output/depth_radar_v4_3day/intent_classifier_v4.joblib
      7. Run: python -c "import pandas as pd; df=pd.read_parquet('training_output/depth_radar_v4_3day/episodes.parquet'); print(f'Episodes: {len(df)}'); assert len(df) >= 10, f'Too few episodes: {len(df)}'"
    Expected Result: Pipeline completes with exit 0, all files produced, ≥10 episodes labeled
    Failure Indicators: Non-zero exit code, missing output files, zero episodes
    Evidence: .sisyphus/evidence/task-1-training-3day.txt

  Scenario: V4 models copied to production location and loadable
    Tool: Bash
    Preconditions: Task 1 Scenario 1 passed
    Steps:
      1. Assert file exists: deep6/models/intent_classifier_v4.joblib
      2. Assert file exists: deep6/models/interaction_predictor_v4.joblib (or log skip reason)
      3. Run: python -c "import joblib; m = joblib.load('deep6/models/intent_classifier_v4.joblib'); assert m['version'] == 'v4'; assert len(m['feature_names']) == 44; print(f'Intent model: {len(m[\"class_names\"])} classes, F1={m[\"training_metrics\"][\"weighted_f1\"]:.4f}')"
      4. Run: python -c "from deep6.ml.depth_radar.causal_classifier import CausalClassifier; c = CausalClassifier(); print(f'Intent loaded: {c.intent_model_loaded}, Interaction loaded: {c.interaction_model_loaded}')"
    Expected Result: Models exist at production paths, version is "v4", 44 features, CausalClassifier loads them
    Failure Indicators: FileNotFoundError, assertion failures, version mismatch
    Evidence: .sisyphus/evidence/task-1-model-verification.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-training-3day.txt — full training stdout with metrics
  - [ ] task-1-model-verification.txt — model load and validation output

  **Commit**: YES
  - Message: `feat(depth-radar): train V4 intent + interaction models from 3-day MBO data`
  - Files: `deep6/models/intent_classifier_v4.joblib`, `deep6/models/interaction_predictor_v4.joblib`, `training_output/depth_radar_v4_3day/`
  - Pre-commit: `python -c "import joblib; m = joblib.load('deep6/models/intent_classifier_v4.joblib'); assert m['version'] == 'v4'"`

- [x] 2. Create Standalone Package Skeleton

  **What to do**:
  - Create `depth_radar_desktop/` directory at repo root
  - Create `depth_radar_desktop/pyproject.toml` with PySide6 dependency, entry point `depth_radar_desktop.__main__:main`
  - Create `depth_radar_desktop/__init__.py` with `__version__ = "0.1.0"`
  - Create `depth_radar_desktop/__main__.py` with minimal `main()` that creates QApplication + placeholder window
  - Create `depth_radar_desktop/tests/` directory with `conftest.py` (pytest-qt fixtures)
  - Follow `gexdoctor/` package structure pattern for standalone tool at repo root
  - Add `--dry-run` flag to `__main__.py` that validates imports and exits without opening window
  - Dependencies: `PySide6>=6.6`, `deep6` (local path reference for engine access)

  **Must NOT do**:
  - Do NOT put any GUI code inside `deep6/` or `deep6v2/`
  - Do NOT add qasync dependency
  - Do NOT create more than the skeleton files listed above

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward file creation with known patterns
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5)
  - **Blocks**: Tasks 6, 7, 8, 9, 10, 13, 14
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - Check if `gexdoctor/` exists at repo root — if so, follow its `pyproject.toml` structure for standalone packages
  - `deep6/ml/depth_radar/__init__.py` — follows the `__all__` export pattern

  **External References**:
  - PySide6 docs: https://doc.qt.io/qtforpython-6/

  **WHY Each Reference Matters**:
  - gexdoctor pattern (if exists) establishes the repo convention for standalone tools
  - PySide6 docs for correct QApplication setup boilerplate

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Package skeleton is importable
    Tool: Bash
    Preconditions: CWD is C:\Users\Tea\DEEP6
    Steps:
      1. Run: python -c "import depth_radar_desktop; print(depth_radar_desktop.__version__)"
      2. Assert output contains "0.1.0"
    Expected Result: Package imports without error, version is 0.1.0
    Failure Indicators: ImportError, ModuleNotFoundError
    Evidence: .sisyphus/evidence/task-2-import.txt

  Scenario: Dry-run mode works without display
    Tool: Bash
    Preconditions: Package skeleton created
    Steps:
      1. Run: python -m depth_radar_desktop --dry-run
      2. Assert exit code 0
      3. Assert output contains "dry-run" or "OK"
    Expected Result: Clean exit without opening a window
    Failure Indicators: Non-zero exit, window opens, crash
    Evidence: .sisyphus/evidence/task-2-dryrun.txt
  ```

  **Commit**: YES (groups with Task 3)
  - Message: `feat(depth-radar-desktop): create standalone PySide6 package skeleton`
  - Files: `depth_radar_desktop/__init__.py`, `depth_radar_desktop/__main__.py`, `depth_radar_desktop/pyproject.toml`, `depth_radar_desktop/tests/conftest.py`
  - Pre-commit: `python -c "import depth_radar_desktop"`

- [x] 3. Dark Trading Terminal Theme + App Constants

  **What to do**:
  - Create `depth_radar_desktop/theme.py` — complete dark trading terminal color scheme and font definitions
  - Colors: background `#0d1117`, panel `#161b22`, border `#30363d`, text primary `#e6edf3`, text secondary `#8b949e`, green `#3fb950`, red `#f85149`, amber `#d29922`, blue `#58a6ff`
  - Fonts: monospace for data (Consolas/Menlo/Courier New), sans-serif for labels (Segoe UI/SF Pro)
  - Create `depth_radar_desktop/constants.py` — app name "Depth Radar Desktop", version, default window size (1400×900), minimum size (1000×600), update interval (500ms for live data), NQ tick size (0.25)
  - Create `apply_theme(app: QApplication)` function that sets global QSS stylesheet
  - Theme should cover: QMainWindow, QTabWidget, QTableView, QLabel, QPushButton, QStatusBar, QHeaderView, QScrollBar
  - Follow professional trading terminal aesthetics: high contrast data, muted chrome, green/red for buy/sell

  **Must NOT do**:
  - Do NOT add custom widget styling yet (that goes in individual widget files)
  - Do NOT add icon assets or images (text/unicode only for v1)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Well-defined styling task with clear color specs
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: Tasks 6, 7, 8, 9, 10
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/services/live_mbo_radar.py:49` — `DEFAULT_SNAPSHOT_INTERVAL_SEC = 2.0` — constants pattern in the project

  **External References**:
  - Qt Stylesheet Reference: https://doc.qt.io/qt-6/stylesheet-reference.html

  **WHY Each Reference Matters**:
  - Constants pattern ensures consistency with how the project defines configuration defaults
  - QSS reference for proper selector syntax in Qt stylesheets

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Theme applies without error
    Tool: Bash
    Preconditions: Package skeleton exists (Task 2)
    Steps:
      1. Run: python -c "from depth_radar_desktop.theme import apply_theme, COLORS; print(COLORS); assert '#0d1117' in str(COLORS)"
      2. Assert no import errors
    Expected Result: Theme module imports, COLORS dict contains expected hex values
    Failure Indicators: ImportError, missing color keys
    Evidence: .sisyphus/evidence/task-3-theme.txt

  Scenario: Constants are accessible
    Tool: Bash
    Steps:
      1. Run: python -c "from depth_radar_desktop.constants import APP_NAME, TICK_SIZE, UPDATE_INTERVAL_MS; assert TICK_SIZE == 0.25; assert UPDATE_INTERVAL_MS == 500; print('Constants OK')"
    Expected Result: All constants import and have correct values
    Evidence: .sisyphus/evidence/task-3-constants.txt
  ```

  **Commit**: YES (groups with Task 2)
  - Message: `feat(depth-radar-desktop): create standalone PySide6 package skeleton`
  - Files: `depth_radar_desktop/theme.py`, `depth_radar_desktop/constants.py`

- [x] 4. asyncio↔Qt Bridge Layer

  **What to do**:
  - Create `depth_radar_desktop/engine_bridge.py` — the critical threading layer between asyncio and Qt
  - Implement `EngineBridge(QObject)` class that:
    - Owns a `threading.Thread` running `asyncio.run(self._engine_loop())`
    - Defines Qt Signals: `walls_updated = Signal(list)`, `connection_changed = Signal(bool)`, `error_occurred = Signal(str)`, `engine_stats = Signal(dict)`
    - Provides `start()` and `stop()` methods (thread-safe)
    - Provides `configure(rithmic_user, rithmic_password, ...)` method
    - Internally creates `LiveMBORadar` (or `MBOWallEngine` directly) in the asyncio thread
    - Uses `on_walls_updated` callback from LiveMBORadar → emits `walls_updated` signal (thread-safe via `QMetaObject.invokeMethod`)
    - Handles engine errors gracefully — emits `error_occurred` signal instead of crashing
  - The bridge is the SINGLE connection between the async engine world and the Qt UI world
  - All data flows through signals — never access engine state directly from the Qt thread
  - Support `source` parameter: "rithmic" (live), "replay" (file), "none" (disconnected/demo)

  **Must NOT do**:
  - Do NOT use qasync or any async↔Qt library — use plain threading.Thread
  - Do NOT call any Qt method from the asyncio thread (except via QMetaObject.invokeMethod or Signal.emit)
  - Do NOT access engine internals from the Qt main thread
  - Do NOT import PySide6 widgets in this module (only QObject, Signal, QMetaObject)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Threading + event loop integration is the most complex part of this project. Requires careful concurrency design.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5)
  - **Blocks**: Task 11
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/services/live_mbo_radar.py:109-248` — `LiveMBORadar` class — the engine this bridge wraps. Pay attention to `start()`, `stop()`, `on_walls_updated` callback, and `_run_rithmic_source()`.
  - `deep6/services/live_mbo_radar.py:382-422` — Rithmic source implementation showing async-rithmic integration
  - `deep6/services/live_mbo_radar.py:569-608` — `_output_loop` and `_emit_snapshot` showing how walls are collected and emitted

  **API/Type References**:
  - `deep6/ml/depth_radar/mbo_wall_engine.py:200-238` — `get_active_walls()` return type: `list[dict[str, Any]]` with keys: episode_id, price, side, size, max_size, age_sec, intent, state, in_touch_band, plus all 44 feature keys

  **External References**:
  - PySide6 threading: https://doc.qt.io/qtforpython-6/overviews/thread-basics.html

  **WHY Each Reference Matters**:
  - LiveMBORadar is what the bridge wraps — its API (start/stop/callback) defines the bridge's internal contract
  - get_active_walls() return shape defines what the Qt Signals will carry
  - PySide6 threading docs explain the correct Signal.emit pattern from non-Qt threads

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Bridge starts and stops without deadlock
    Tool: Bash
    Steps:
      1. Run: python -c "
         from depth_radar_desktop.engine_bridge import EngineBridge
         from PySide6.QtCore import QCoreApplication
         import sys, time
         app = QCoreApplication(sys.argv)
         bridge = EngineBridge(source='none')
         bridge.start()
         time.sleep(1)
         bridge.stop()
         print('Bridge start/stop OK')
         "
      2. Assert output contains "Bridge start/stop OK"
      3. Assert process exits cleanly (no hang)
    Expected Result: Bridge creates thread, starts, stops, and process exits within 5 seconds
    Failure Indicators: Deadlock (process hangs), thread exception, Qt signal errors
    Evidence: .sisyphus/evidence/task-4-bridge-lifecycle.txt

  Scenario: Bridge emits signals on wall updates
    Tool: Bash
    Steps:
      1. Create a test that instantiates EngineBridge with source='none'
      2. Manually inject a wall update via the bridge's internal callback mechanism
      3. Verify walls_updated signal is emitted with correct data shape
    Expected Result: Signal carries list of wall dicts, received on Qt thread
    Evidence: .sisyphus/evidence/task-4-bridge-signals.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar-desktop): add asyncio-Qt engine bridge layer`
  - Files: `depth_radar_desktop/engine_bridge.py`
  - Pre-commit: `python -c "from depth_radar_desktop.engine_bridge import EngineBridge"`

- [x] 5. App Configuration + .env Loading

  **What to do**:
  - Create `depth_radar_desktop/config.py` — Pydantic BaseSettings for all configurable values
  - Settings class: `DepthRadarConfig(BaseSettings)` with fields:
    - `rithmic_user: str = ""`, `rithmic_password: str = ""`, `rithmic_system_name: str = ""`, `rithmic_url: str = ""`
    - `rithmic_symbol: str = "NQM6"`, `rithmic_exchange: str = "CME"`
    - `model_dir: Path = Path("deep6/models")` — resolved to absolute at load time
    - `training_output_dir: Path = Path("training_output")` — for Research tab parquet reading
    - `source: str = "rithmic"` — data source selection
    - `min_wall_size: int = 50`
    - `update_interval_ms: int = 500`
    - `rth_only: bool = True`
  - Load from `.env` file at project root (match existing project convention)
  - Resolve all relative paths to absolute using project root detection (find `.git/` or `deep6/` directory)
  - Provide `load_config()` function that returns populated DepthRadarConfig

  **Must NOT do**:
  - Do NOT create a settings GUI dialog (just .env file for v1)
  - Do NOT store credentials in any file tracked by git

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward Pydantic model + .env loading
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4)
  - **Blocks**: Task 11
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `deep6/services/live_mbo_radar.py:645-654` — `_load_env()` and `_env()` helper showing the .env loading pattern used in the project
  - `deep6/services/live_mbo_radar.py:683-701` — constructor params showing all Rithmic config fields

  **WHY Each Reference Matters**:
  - The existing .env loading pattern must be matched for consistency
  - Rithmic config fields must exactly match what LiveMBORadar expects

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Config loads defaults without .env file
    Tool: Bash
    Steps:
      1. Run: python -c "from depth_radar_desktop.config import load_config; c = load_config(); assert c.rithmic_symbol == 'NQM6'; assert c.min_wall_size == 50; print('Config defaults OK')"
    Expected Result: Config loads with sensible defaults even without .env
    Evidence: .sisyphus/evidence/task-5-config-defaults.txt

  Scenario: Config resolves model paths to absolute
    Tool: Bash
    Steps:
      1. Run: python -c "from depth_radar_desktop.config import load_config; c = load_config(); assert c.model_dir.is_absolute(); print(f'Model dir: {c.model_dir}')"
    Expected Result: model_dir is an absolute path, not relative
    Evidence: .sisyphus/evidence/task-5-config-paths.txt
  ```

  **Commit**: YES (groups with Task 4)
  - Message: `feat(depth-radar-desktop): add asyncio-Qt engine bridge layer`
  - Files: `depth_radar_desktop/config.py`

- [x] 6. Active Walls QTableView + Model

  **What to do**:
  - Create `depth_radar_desktop/live/walls_table.py`
  - Implement `WallsTableModel(QAbstractTableModel)` backed by a `list[dict]` of wall data
  - Columns: Price, Side (Bid/Ask), Size, Max Size, Intent (PASSIVE_REAL/SPOOF_LIKE/RESERVE_REFRESH/MIGRATORY), State (FRESH/ESTABLISHED/UNDER_ATTACK/DEFENDING/EXHAUSTED/CONSUMED/PULLED/STALE), Confidence (%), Age (sec)
  - Color coding: Bid rows tinted green, Ask rows tinted red. SPOOF_LIKE intent highlighted amber. UNDER_ATTACK state highlighted red. Confidence column as color-gradient bar.
  - Implement `WallsTableView(QTableView)` with fixed column widths, alternating row colors (subtle), sort-by-column
  - Provide `update_walls(walls: list[dict])` method that diffs and updates the model (minimize flicker)
  - Display "No Active Walls" placeholder when list is empty
  - Display "Markets Closed" when engine reports no data flow

  **Must NOT do**:
  - Do NOT connect to the engine bridge (that happens in Task 12)
  - Do NOT add click-to-detail functionality (v1 shows table only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Custom QTableModel with color-coded cells and data diffing requires careful Qt model/view implementation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8, 9, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `deep6/ml/depth_radar/mbo_wall_engine.py:200-238` — `get_active_walls()` return shape defines the data this table displays. Keys: episode_id, price, side, size, max_size, age_sec, intent, state, in_touch_band, plus 44 features.
  - `deep6/ml/depth_radar/episode.py` — `WallState` enum (8 values) and `WallIntent` enum (4 values) — these are the classification labels to display

  **WHY Each Reference Matters**:
  - get_active_walls() return shape is the contract — table columns map directly to its keys
  - WallState and WallIntent enums define the valid values for State and Intent columns

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Table renders with mock wall data
    Tool: Bash (pytest-qt)
    Steps:
      1. Create test: instantiate WallsTableView, call update_walls() with 3 mock wall dicts
      2. Assert table model rowCount() == 3
      3. Assert column headers match spec (Price, Side, Size, ...)
      4. Assert bid wall row has green-tinted background
      5. Assert SPOOF_LIKE intent cell has amber text
    Expected Result: Table renders correctly with color coding
    Evidence: .sisyphus/evidence/task-6-walls-table.txt

  Scenario: Empty state shows placeholder
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate WallsTableView with empty data
      2. Assert "No Active Walls" placeholder text is visible
    Expected Result: Placeholder displayed when no walls
    Evidence: .sisyphus/evidence/task-6-empty-state.txt
  ```

  **Commit**: YES (groups with Tasks 7, 8, 9)
  - Message: `feat(depth-radar-desktop): add live panel widgets`
  - Files: `depth_radar_desktop/live/walls_table.py`

- [x] 7. Feature Gauges Widget

  **What to do**:
  - Create `depth_radar_desktop/live/feature_gauges.py`
  - Implement `FeatureGaugesPanel(QWidget)` — a horizontal panel of 4-6 key diagnostic gauges
  - Gauges to display (from the 44 causal features — pick the most actionable):
    - **Absorption Ratio** (`absorption_ratio` feature) — how much volume the wall has absorbed vs its size
    - **Delta Pressure** (`delta_2s` feature) — recent directional aggression
    - **Approach Speed** (`approach_speed` feature) — how fast price is moving toward nearest wall
    - **Wall Density** (computed: count of active walls within 20 ticks of mid) — market structure context
  - Each gauge: vertical bar or arc meter with label, value, and color (green=safe, amber=caution, red=danger)
  - Thresholds for color mapping: configurable via constants, sensible defaults
  - Provide `update_gauges(walls: list[dict], mid_price: float)` method

  **Must NOT do**:
  - Do NOT use matplotlib or plotly for gauges — pure Qt painting (QPainter/QSS)
  - Do NOT display all 44 features — only the 4-6 most actionable

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Custom-painted gauge widgets require careful QPainter rendering and visual design
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 8, 9, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `deep6/ml/depth_radar/causal_features.py:CAUSAL_FEATURE_NAMES` — the 44 feature names. The gauges show: `absorption_ratio`, `delta_2s`, `approach_speed` (indices vary — look them up in the list)
  - `deep6/ml/depth_radar/mbo_wall_engine.py:595-619` — `_feature_dict()` shows how features are computed — useful for understanding value ranges

  **WHY Each Reference Matters**:
  - CAUSAL_FEATURE_NAMES tells you the exact key names to extract from wall dicts
  - _feature_dict() helps set sensible gauge thresholds (e.g., absorption_ratio is 0.0-1.0+)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Gauges render with mock data
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate FeatureGaugesPanel
      2. Call update_gauges() with mock wall data containing known feature values
      3. Assert 4 gauge sub-widgets are present
      4. Assert labels match: "Absorption", "Delta", "Approach Speed", "Wall Density"
    Expected Result: Four gauges render with correct labels and values
    Evidence: .sisyphus/evidence/task-7-gauges.txt

  Scenario: Gauges handle zero/empty data gracefully
    Tool: Bash (pytest-qt)
    Steps:
      1. Call update_gauges(walls=[], mid_price=0.0)
      2. Assert gauges show 0/default values, no crash
    Expected Result: Gauges display zero state without errors
    Evidence: .sisyphus/evidence/task-7-gauges-empty.txt
  ```

  **Commit**: YES (groups with Tasks 6, 8, 9)
  - Files: `depth_radar_desktop/live/feature_gauges.py`

- [x] 8. Touch/Interaction Alerts Panel

  **What to do**:
  - Create `depth_radar_desktop/live/alerts_panel.py`
  - Implement `AlertsPanel(QWidget)` — a scrollable log of recent touch events
  - Each alert row: timestamp, wall price, wall side, predicted outcome (BOUNCE/BREAK/CHURN), distance from mid
  - Visual: new alerts flash briefly (QPropertyAnimation on background color), then settle
  - Maximum 50 alerts retained (FIFO), with auto-scroll to latest
  - Color: BOUNCE predictions green, BREAK predictions red, CHURN predictions gray
  - Provide `add_alert(wall: dict, mid_price: float, predicted_outcome: str)` method
  - Provide `update_from_walls(walls: list[dict], mid_price: float)` — auto-detects when walls enter touch band (`in_touch_band == True`) and fires alerts

  **Must NOT do**:
  - Do NOT add system notifications (OS toast) — visual only for v1
  - Do NOT add sound alerts
  - Do NOT predict outcomes in this widget — consume predictions from CausalClassifier

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Custom scrollable alert log with animations
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 9, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `deep6/ml/depth_radar/mbo_wall_engine.py:446-490` — `_detect_touches()` shows what `in_touch_band` means and when it triggers
  - `deep6/ml/depth_radar/episode.py:InteractionOutcome` — BOUNCE, BREAK, CHURN enum values

  **WHY Each Reference Matters**:
  - _detect_touches() defines the touch band logic — alerts fire when `in_touch_band` transitions from False to True
  - InteractionOutcome enum is the label set for predicted outcomes

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Alert fires when wall enters touch band
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate AlertsPanel
      2. Call update_from_walls() with a wall where in_touch_band=True
      3. Assert alert row appears with correct price and side
    Expected Result: Alert row added to panel
    Evidence: .sisyphus/evidence/task-8-alerts.txt

  Scenario: Alerts cap at 50 entries
    Tool: Bash (pytest-qt)
    Steps:
      1. Fire 60 alerts via add_alert()
      2. Assert panel contains exactly 50 entries (oldest 10 removed)
    Expected Result: FIFO capping at 50
    Evidence: .sisyphus/evidence/task-8-alerts-cap.txt
  ```

  **Commit**: YES (groups with Tasks 6, 7, 9)
  - Files: `depth_radar_desktop/live/alerts_panel.py`

- [x] 9. Connection Status Bar Widget

  **What to do**:
  - Create `depth_radar_desktop/widgets/status_bar.py`
  - Implement `ConnectionStatusBar(QStatusBar)` with:
    - Connection indicator: green dot + "Connected" / yellow dot + "Reconnecting..." / red dot + "Disconnected"
    - Model status: "Models: ✓ Intent ✓ Interaction" or "Models: ✗ Not Loaded"
    - Active wall count: "Walls: 7 active"
    - Last update timestamp: "Last: 14:32:05.123"
  - Provide `set_connected(connected: bool)`, `set_model_status(intent: bool, interaction: bool)`, `update_stats(wall_count: int, timestamp: str)` methods
  - Unicode dots for status indicators (●/○), no image assets needed

  **Must NOT do**:
  - Do NOT add clickable actions to the status bar (display only)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple QStatusBar subclass with formatted text labels
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 10)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `deep6/services/live_mbo_radar.py:274-285` — health endpoint response shape shows the status fields available

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Status bar shows disconnected state
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate ConnectionStatusBar
      2. Call set_connected(False)
      3. Assert status text contains "Disconnected" and red indicator
    Expected Result: Red indicator with "Disconnected" text
    Evidence: .sisyphus/evidence/task-9-status.txt
  ```

  **Commit**: YES (groups with Tasks 6, 7, 8)
  - Files: `depth_radar_desktop/widgets/status_bar.py`

- [x] 10. Main Window + Tab Layout

  **What to do**:
  - Create `depth_radar_desktop/main_window.py`
  - Implement `DepthRadarMainWindow(QMainWindow)` with:
    - Window title: "Depth Radar Desktop v0.1.0 — NQ"
    - Default size: 1400×900, minimum: 1000×600
    - Central widget: QTabWidget with two tabs — "⚡ Live" and "📊 Research"
    - Live tab: QSplitter layout — left 70% for WallsTableView, right 30% split vertically for FeatureGaugesPanel (top) and AlertsPanel (bottom)
    - Research tab: QSplitter — left for EpisodeBrowser, right for ModelDashboard (placeholder QLabels for now — actual widgets in Tasks 13, 14)
    - Status bar: ConnectionStatusBar at bottom
    - Menu bar: File → Exit, View → Toggle Live/Research tabs
  - Apply dark theme from `theme.py` during window init
  - Connect to `EngineBridge` signals (placeholder slots that print to console for now)

  **Must NOT do**:
  - Do NOT implement the actual Live or Research widget contents (those are separate tasks)
  - Do NOT add toolbar or dock widgets

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Main window layout orchestration with QSplitter, QTabWidget, menu bar
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7, 8, 9)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 2, 3

  **References**:

  **Pattern References**:
  - `depth_radar_desktop/theme.py` (Task 3) — `apply_theme()` function to call during init
  - `depth_radar_desktop/constants.py` (Task 3) — window dimensions, app name

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Main window opens with two tabs
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate DepthRadarMainWindow
      2. Assert window title contains "Depth Radar Desktop"
      3. Assert QTabWidget has 2 tabs
      4. Assert tab labels contain "Live" and "Research"
    Expected Result: Window renders with two tabs and dark theme
    Evidence: .sisyphus/evidence/task-10-mainwindow.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar-desktop): add main window with tab layout`
  - Files: `depth_radar_desktop/main_window.py`

- [x] 11. Rithmic Engine Worker Thread

  **What to do**:
  - Create `depth_radar_desktop/live/engine_worker.py`
  - Implement `EngineWorker` class that configures and manages the `EngineBridge`:
    - Reads `DepthRadarConfig` to get Rithmic credentials + engine params
    - Configures `EngineBridge` with source, credentials, model paths
    - Implements `start_live()`, `stop_live()`, `start_replay(file_path)` methods
    - Manages wall update polling: every `update_interval_ms`, gets active walls from engine via bridge signal
    - Enriches walls with CausalClassifier classifications (intent + interaction prediction)
    - Emits enriched wall data through the bridge's `walls_updated` signal
  - Handle Rithmic connection lifecycle: initial connect, disconnect events, reconnection status
  - Handle "markets closed" detection: if no wall updates for 60+ seconds during expected RTH, signal markets-closed state
  - Support graceful shutdown: stop engine, drain pending updates, close connections

  **Must NOT do**:
  - Do NOT access Qt widgets from the engine thread
  - Do NOT create new threading patterns — use EngineBridge from Task 4
  - Do NOT re-implement Rithmic connection logic — delegate to LiveMBORadar

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Critical integration layer — async engine + thread bridge + connection lifecycle. Must be correct for the entire app to function.
  - **Skills**: [`rithmic-networking`]
    - `rithmic-networking`: Rithmic connection patterns, system names, error handling

  **Parallelization**:
  - **Can Run In Parallel**: YES (but depends on Wave 1 tasks)
  - **Parallel Group**: Wave 3 (with Tasks 12, 13, 14, 15)
  - **Blocks**: Task 12
  - **Blocked By**: Tasks 4, 5

  **References**:

  **Pattern References**:
  - `depth_radar_desktop/engine_bridge.py` (Task 4) — the bridge layer this worker configures
  - `deep6/services/live_mbo_radar.py:109-170` — LiveMBORadar constructor showing all params the worker must pass through
  - `deep6/services/live_mbo_radar.py:382-422` — `_run_rithmic_source()` showing Rithmic subscription flow
  - `deep6/ml/depth_radar/causal_classifier.py` — `classify_wall()` method for enriching wall data with classifications

  **WHY Each Reference Matters**:
  - EngineBridge is the foundation — worker must use its API correctly
  - LiveMBORadar constructor params are what the worker passes through from config
  - classify_wall() enriches raw walls with intent/interaction predictions before emitting to UI

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Worker starts with replay source
    Tool: Bash
    Preconditions: 3-day MBO file exists
    Steps:
      1. Instantiate EngineWorker with source="replay", replay_file=<3-day MBO path>
      2. Start worker
      3. Wait 5 seconds
      4. Assert walls_updated signal was emitted at least once
      5. Stop worker cleanly
    Expected Result: Worker processes MBO replay and emits wall updates
    Evidence: .sisyphus/evidence/task-11-worker-replay.txt

  Scenario: Worker handles missing Rithmic credentials gracefully
    Tool: Bash
    Steps:
      1. Instantiate EngineWorker with source="rithmic" but empty credentials
      2. Start worker
      3. Assert error_occurred signal is emitted with descriptive message
      4. Assert app doesn't crash
    Expected Result: Error signal emitted, no crash
    Evidence: .sisyphus/evidence/task-11-worker-error.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `feat(depth-radar-desktop): add live engine worker + Rithmic integration`
  - Files: `depth_radar_desktop/live/engine_worker.py`

- [x] 12. Live Tab Assembly

  **What to do**:
  - Create `depth_radar_desktop/live/live_tab.py`
  - Implement `LiveTab(QWidget)` that wires together all live panel components:
    - Instantiates WallsTableView (Task 6), FeatureGaugesPanel (Task 7), AlertsPanel (Task 8)
    - Layout: QSplitter — left 70% walls table, right 30% stacked gauges (top) + alerts (bottom)
    - Connects `EngineBridge.walls_updated` signal → `WallsTableView.update_walls()` + `FeatureGaugesPanel.update_gauges()` + `AlertsPanel.update_from_walls()`
    - Connects `EngineBridge.connection_changed` → updates status bar
    - Adds QTimer for periodic UI refresh (500ms) — repaints gauges and updates age column in table
    - Handle "no data" state: when no walls for 60 seconds, show overlay "Waiting for data..." or "Markets Closed"
  - Update `__main__.py` to wire LiveTab into MainWindow's Live tab
  - Update `main_window.py` to accept and embed actual widgets instead of placeholders

  **Must NOT do**:
  - Do NOT create new widgets (use existing ones from Tasks 6-9)
  - Do NOT add new features beyond what's in the Live panel spec

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Integration/wiring task connecting multiple components with signal/slot patterns
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — requires all live widgets + engine worker
  - **Parallel Group**: Wave 3 (sequential within wave)
  - **Blocks**: Tasks 16, 17
  - **Blocked By**: Tasks 6, 7, 8, 9, 10, 11

  **References**:

  **Pattern References**:
  - All Task 6-9 widget APIs (update_walls, update_gauges, update_from_walls, set_connected)
  - `depth_radar_desktop/engine_bridge.py` (Task 4) — Signal definitions: walls_updated, connection_changed, error_occurred

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Live tab renders all components
    Tool: Bash (pytest-qt)
    Steps:
      1. Instantiate LiveTab with mock EngineBridge
      2. Assert WallsTableView is present in layout
      3. Assert FeatureGaugesPanel is present
      4. Assert AlertsPanel is present
    Expected Result: All three widgets render in the correct layout positions
    Evidence: .sisyphus/evidence/task-12-live-tab.txt

  Scenario: Data flows from bridge to all widgets
    Tool: Bash (pytest-qt)
    Steps:
      1. Emit mock wall data through EngineBridge.walls_updated
      2. Assert WallsTableView model has rows
      3. Assert FeatureGaugesPanel values updated
      4. Assert AlertsPanel has entries (if walls had in_touch_band=True)
    Expected Result: Signal propagates to all child widgets
    Evidence: .sisyphus/evidence/task-12-data-flow.txt
  ```

  **Commit**: YES (groups with Task 11)
  - Files: `depth_radar_desktop/live/live_tab.py`, updated `main_window.py`, updated `__main__.py`

- [x] 13. Episode Browser Widget

  **What to do**:
  - Create `depth_radar_desktop/research/episode_browser.py`
  - Implement `EpisodeBrowser(QWidget)` with:
    - Left panel: QTableView listing episodes from parquet files (episode_id, date, side, price, intent_label, final_state, touch_count, snapshot_count)
    - Right panel: Detail view showing selected episode's full lifecycle (all snapshots as mini-timeline, all touches with outcomes)
    - Top: Filter controls — QComboBox for intent (All/PASSIVE_REAL/SPOOF_LIKE/RESERVE_REFRESH/MIGRATORY), QComboBox for outcome (All/BOUNCE/BREAK/CHURN), QDateEdit for date range
    - Data source: Read episodes.parquet, snapshots.parquet, touches.parquet from training output directory
    - Provide `load_data(directory: Path)` method that reads parquet files and populates the table
    - Handle missing files gracefully: show "No training data found. Run training first." message

  **Must NOT do**:
  - Do NOT add episode editing or re-labeling
  - Do NOT add chart/plot rendering (text + table only for v1)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Master-detail view with filtering, parquet reading, and dual-panel layout
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 14, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 2, 3, 1 (needs training output parquet)

  **References**:

  **Pattern References**:
  - `scripts/train_depth_radar_v4.py:87-89` — parquet file names: episodes.parquet, snapshots.parquet, touches.parquet
  - `deep6/ml/depth_radar/episode.py` — `WallEpisode.to_parquet_rows()` defines the schema of the parquet files. Understand the episode row structure, snapshot rows, and touch rows.
  - `scripts/train_depth_radar_v4.py:31-44` — class name lists for intent (4 values) and interaction outcome (3 values) — these populate the filter dropdowns

  **WHY Each Reference Matters**:
  - Parquet file names must match exactly what the training pipeline produces
  - Episode schema defines the columns available for the table and detail view
  - Class name lists define the filter dropdown options

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Episode browser loads training output
    Tool: Bash (pytest-qt)
    Preconditions: Training output exists from Task 1
    Steps:
      1. Instantiate EpisodeBrowser
      2. Call load_data(Path("training_output/depth_radar_v4_3day"))
      3. Assert episode table has ≥10 rows
      4. Assert filter dropdowns contain correct options
    Expected Result: Episodes load and display in table with working filters
    Evidence: .sisyphus/evidence/task-13-episode-browser.txt

  Scenario: Episode browser handles missing data
    Tool: Bash (pytest-qt)
    Steps:
      1. Call load_data(Path("nonexistent/directory"))
      2. Assert "No training data found" message is displayed
      3. Assert no crash
    Expected Result: Graceful error message, no crash
    Evidence: .sisyphus/evidence/task-13-missing-data.txt
  ```

  **Commit**: YES (groups with Task 14)
  - Message: `feat(depth-radar-desktop): add research panel (episodes + model dashboard)`
  - Files: `depth_radar_desktop/research/episode_browser.py`

- [x] 14. Model Performance Dashboard

  **What to do**:
  - Create `depth_radar_desktop/research/model_dashboard.py`
  - Implement `ModelDashboard(QWidget)` with:
    - Intent model card: Model name, version, training date, class count
    - Metrics display: Weighted F1, Precision, Recall, Accuracy — large readable numbers
    - Confusion matrix: QTableWidget colored by value (darker = more samples). Rows/columns labeled with class names.
    - Per-class metrics: table showing precision/recall/F1/support per class
    - Feature importance: Top 15 features listed with horizontal bar indicators (pure QSS/QPainter, no matplotlib)
    - Separate sections for intent model and interaction model (if available)
  - Data source: Read `training_metrics` dict from joblib model files
  - Provide `load_model_metrics(model_path: Path)` method
  - Handle missing models: show "Model not trained yet" with guidance to run training command

  **Must NOT do**:
  - Do NOT use matplotlib, plotly, or any charting library — pure Qt widgets
  - Do NOT add SHAP values or advanced ML analysis (v1 is summary metrics only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Custom dashboard layout with multiple metric displays and confusion matrix widget
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Tasks 11, 12, 13, 15)
  - **Blocks**: Task 16
  - **Blocked By**: Tasks 2, 3, 1 (needs trained model joblib)

  **References**:

  **Pattern References**:
  - `scripts/train_depth_radar_v4.py:258-295` — `build_metrics()` function defines the exact metrics dict structure saved in the joblib. Keys: `weighted_f1`, `precision`, `recall`, `accuracy`, `confusion_matrix` (list of lists), `per_class` (dict of dicts), `feature_importance` (dict name→float)
  - `scripts/train_depth_radar_v4.py:413-422` — joblib payload structure: `{"model": ..., "mode": ..., "class_names": [...], "feature_names": [...], "training_metrics": {...}, "version": "v4"}`

  **WHY Each Reference Matters**:
  - build_metrics() output is the EXACT data this dashboard reads — every key in the metrics dict maps to a UI element
  - joblib payload structure tells you how to extract metrics: `payload["training_metrics"]`

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Dashboard loads model metrics
    Tool: Bash (pytest-qt)
    Preconditions: V4 intent model exists from Task 1
    Steps:
      1. Instantiate ModelDashboard
      2. Call load_model_metrics(Path("deep6/models/intent_classifier_v4.joblib"))
      3. Assert F1, Precision, Recall, Accuracy labels show non-zero values
      4. Assert confusion matrix table has correct dimensions (4×4 for intent)
      5. Assert feature importance list shows ≥15 features
    Expected Result: All metric sections populated with real training data
    Evidence: .sisyphus/evidence/task-14-model-dashboard.txt

  Scenario: Dashboard handles missing model
    Tool: Bash (pytest-qt)
    Steps:
      1. Call load_model_metrics(Path("nonexistent/model.joblib"))
      2. Assert "Model not trained yet" message displayed
    Expected Result: Graceful error message
    Evidence: .sisyphus/evidence/task-14-missing-model.txt
  ```

  **Commit**: YES (groups with Task 13)
  - Files: `depth_radar_desktop/research/model_dashboard.py`

- [ ] 15. Train V4 Models on 30-Day MBO File

  **What to do**:
  - Run the full 30-day training after 3-day training (Task 1) succeeds
  - Execute: `python scripts/train_depth_radar_v4.py --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst --output-dir training_output/depth_radar_v4_30day`
  - This will take significantly longer than the 3-day file (possibly 1-4 hours)
  - Verify output metrics are better than or comparable to 3-day training
  - Verify models are copied to production location (overwrites 3-day models)
  - Capture full training log

  **Must NOT do**:
  - Do NOT run this if Task 1 failed — debug 3-day training first
  - Do NOT modify the training script

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: CLI execution task (same as Task 1 but different input file)
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with other Wave 3 tasks — this is independent)
  - **Parallel Group**: Wave 3
  - **Blocks**: None (production models already exist from Task 1; this upgrades them)
  - **Blocked By**: Task 1

  **References**:
  - Same as Task 1
  - `data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst` — 6.4 GB, 30 days Mar 15–Apr 14 2026

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: 30-day training completes and produces improved models
    Tool: Bash
    Steps:
      1. Run training command (may take hours — use timeout 14400000 ms / 4 hours)
      2. Assert exit code 0
      3. Assert file exists: training_output/depth_radar_v4_30day/episodes.parquet
      4. Run: python -c "import pandas as pd; df=pd.read_parquet('training_output/depth_radar_v4_30day/episodes.parquet'); print(f'Episodes: {len(df)}'); assert len(df) >= 100"
      5. Assert models copied to deep6/models/
    Expected Result: More episodes than 3-day, models at production path
    Evidence: .sisyphus/evidence/task-15-training-30day.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar): upgrade V4 models with 30-day MBO training data`
  - Files: `deep6/models/intent_classifier_v4.joblib`, `deep6/models/interaction_predictor_v4.joblib`

- [ ] 16. Full Integration Test + Error Handling

  **What to do**:
  - Create `depth_radar_desktop/live/__init__.py` and `depth_radar_desktop/research/__init__.py`
  - Wire Research tab: update `main_window.py` to embed EpisodeBrowser (Task 13) and ModelDashboard (Task 14) into Research tab
  - Wire `__main__.py` complete flow: config → bridge → main window → live tab → research tab → status bar
  - Add comprehensive error handling in `__main__.py`:
    - Catch PySide6 import errors with helpful message ("pip install PySide6")
    - Catch deep6 import errors with helpful message about package path
    - Catch model loading failures → show in status bar, app continues
    - Catch Rithmic connection failures → show in status bar, app continues
    - Global unhandled exception handler → log to file + show error dialog
  - Add `--source none` mode for testing without live data
  - Test full app lifecycle: launch → connect → receive walls → display → research tab → close

  **Must NOT do**:
  - Do NOT add new features — this is integration and hardening only
  - Do NOT modify the engine or ML code

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: End-to-end integration touching all components, error handling across async/sync boundaries
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO — must have all components ready
  - **Parallel Group**: Wave 4
  - **Blocks**: Tasks 18, 19
  - **Blocked By**: Tasks 12, 13, 14

  **References**:
  - All previous task outputs (Tasks 2-14)
  - `depth_radar_desktop/__main__.py` — the entry point to update

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full app launches and renders both tabs
    Tool: Bash (pytest-qt)
    Steps:
      1. Run: python -m depth_radar_desktop --source none
      2. Assert window appears with dark theme
      3. Assert Live tab has walls table, gauges, alerts
      4. Assert Research tab has episode browser and model dashboard
      5. Assert status bar shows "Disconnected" (no source)
    Expected Result: Complete UI renders without errors
    Evidence: .sisyphus/evidence/task-16-full-launch.txt

  Scenario: App handles missing PySide6 gracefully
    Tool: Bash
    Steps:
      1. Run: python -c "import depth_radar_desktop.__main__" in an environment where concept is tested
      2. Assert helpful error message if PySide6 missing
    Expected Result: Clear error message, not a raw traceback
    Evidence: .sisyphus/evidence/task-16-missing-deps.txt
  ```

  **Commit**: YES
  - Message: `feat(depth-radar-desktop): full integration with engine + error handling`
  - Files: `depth_radar_desktop/**`

- [ ] 17. Graceful Degradation + Edge Cases

  **What to do**:
  - Test and handle all degradation scenarios:
    - No V4 models: App launches, Live tab works but shows "Models Not Loaded" in status bar, classifications show "UNKNOWN"
    - No Rithmic credentials: App launches, shows "Not Configured" status, Research tab fully functional
    - No training output: Research tab shows "No training data" placeholder
    - Engine thread crash: Main window remains responsive, error shown in status bar, auto-restart option
    - Model file corrupted: CausalClassifier fallback to no-classification mode
  - Add "Markets Closed" overlay for Live tab during non-RTH hours
  - Ensure window close properly shuts down engine thread (no zombie processes)
  - Ensure Ctrl+C in terminal kills app cleanly

  **Must NOT do**:
  - Do NOT add auto-recovery logic beyond what's listed
  - Do NOT add logging configuration UI

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Systematic edge case testing and error handling refinement
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 18, 19)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 12

  **References**:
  - `deep6/ml/depth_radar/causal_classifier.py` — graceful degradation patterns for missing models
  - `deep6/services/live_mbo_radar.py:216-248` — `stop()` method for clean shutdown

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: App works without trained models
    Tool: Bash
    Steps:
      1. Temporarily rename deep6/models/intent_classifier_v4.joblib
      2. Launch app: python -m depth_radar_desktop --source none
      3. Assert status bar shows "Models: ✗ Not Loaded"
      4. Assert app is responsive (not crashed)
      5. Restore model file
    Expected Result: App runs in degraded mode
    Evidence: .sisyphus/evidence/task-17-no-models.txt

  Scenario: App shuts down cleanly
    Tool: Bash
    Steps:
      1. Launch app with --source none
      2. Close window via window manager
      3. Assert process exits within 5 seconds (no zombie thread)
    Expected Result: Clean exit, no hanging threads
    Evidence: .sisyphus/evidence/task-17-clean-shutdown.txt
  ```

  **Commit**: YES (groups with Task 16)
  - Files: updated `depth_radar_desktop/**`

- [ ] 18. Tests for Critical Paths

  **What to do**:
  - Create `depth_radar_desktop/tests/test_engine_bridge.py` — test bridge start/stop, signal emission, thread safety
  - Create `depth_radar_desktop/tests/test_walls_table.py` — test table model with mock data, column mapping, color coding
  - Create `depth_radar_desktop/tests/test_config.py` — test config loading, path resolution, defaults
  - Create `depth_radar_desktop/tests/test_episode_browser.py` — test parquet loading, filtering, missing data handling
  - Create `depth_radar_desktop/tests/test_model_dashboard.py` — test metrics display, missing model handling
  - Use `pytest-qt` for widget tests — `qtbot` fixture for widget instantiation
  - Focus on: data correctness (right values in right cells), error handling (missing files, bad data), thread safety (bridge signal delivery)

  **Must NOT do**:
  - Do NOT aim for 100% coverage — focus on critical paths that would cause data corruption or crashes
  - Do NOT test PySide6 rendering pixel-perfectly

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Multiple test files with pytest-qt, mocking, and thread-safety testing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 19)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 16

  **References**:
  - All widget APIs from Tasks 6-14
  - pytest-qt docs: https://pytest-qt.readthedocs.io/

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All tests pass
    Tool: Bash
    Steps:
      1. Run: python -m pytest depth_radar_desktop/tests/ -v --tb=short
      2. Assert exit code 0
      3. Assert ≥15 tests pass
    Expected Result: All critical path tests pass
    Evidence: .sisyphus/evidence/task-18-tests.txt
  ```

  **Commit**: YES
  - Message: `test(depth-radar-desktop): add critical path tests`
  - Files: `depth_radar_desktop/tests/test_*.py`

- [ ] 19. Package Launch Script + README

  **What to do**:
  - Update `depth_radar_desktop/pyproject.toml` with correct dependencies, entry point, and metadata
  - Create `depth_radar_desktop/README.md` with:
    - Quick start: `pip install -e ./depth_radar_desktop && python -m depth_radar_desktop`
    - Configuration: .env file format for Rithmic credentials
    - Training: how to run V4 training before first use
    - Screenshots or ASCII diagrams of the two-tab layout
    - Troubleshooting: common issues (no PySide6, no models, no Rithmic)
  - Verify `pip install -e ./depth_radar_desktop` works
  - Verify `python -m depth_radar_desktop --dry-run` works after install
  - Add `depth_radar_desktop` to repo .gitignore patterns if needed (e.g., __pycache__)

  **Must NOT do**:
  - Do NOT create a compiled executable (.exe) — Python package only for v1
  - Do NOT set up CI/CD for the desktop app

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Package config and documentation — straightforward
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 18)
  - **Parallel Group**: Wave 4
  - **Blocks**: None
  - **Blocked By**: Task 16

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Package installs and launches
    Tool: Bash
    Steps:
      1. Run: pip install -e ./depth_radar_desktop
      2. Assert exit code 0
      3. Run: python -m depth_radar_desktop --dry-run
      4. Assert exit code 0
    Expected Result: Clean install and launch
    Evidence: .sisyphus/evidence/task-19-package.txt
  ```

  **Commit**: YES
  - Message: `docs(depth-radar-desktop): add README and finalize package config`
  - Files: `depth_radar_desktop/pyproject.toml`, `depth_radar_desktop/README.md`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, launch app, check widget). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m py_compile` on all new files + linter. Review all changed files for: `type: ignore`, empty catches, print() in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify PySide6 best practices: no direct Qt thread manipulation from non-main thread, signal/slot connections correct.
  Output: `Compile [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Launch `python -m depth_radar_desktop`. Verify dark theme renders. Check Live tab widgets appear (table, gauges, alerts, status bar). Check Research tab loads (episode browser with data, model dashboard with metrics). Test connection status without Rithmic (should show disconnected). Test with replay source if available. Save screenshots to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual files. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination. Flag any chart rendering, order execution, or other excluded features.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| Group | Message | Files | Pre-commit |
|-------|---------|-------|------------|
| Training | `feat(depth-radar): train V4 intent + interaction models from MBO data` | `deep6/models/*.joblib`, `training_output_*/**` | verify model loads |
| Package skeleton | `feat(depth-radar-desktop): create standalone PySide6 package skeleton` | `depth_radar_desktop/**` | `python -m depth_radar_desktop --help` |
| Live widgets | `feat(depth-radar-desktop): add live panel widgets (table, gauges, alerts)` | `depth_radar_desktop/live/**` | pytest |
| Research widgets | `feat(depth-radar-desktop): add research panel (episodes, model dashboard)` | `depth_radar_desktop/research/**` | pytest |
| Integration | `feat(depth-radar-desktop): full integration with engine + Rithmic` | `depth_radar_desktop/**` | full test suite |

---

## Success Criteria

### Verification Commands
```bash
# Models trained and loadable
python -c "import joblib; m = joblib.load('deep6/models/intent_classifier_v4.joblib'); assert m['version'] == 'v4'; assert len(m['feature_names']) == 44; print('Intent model OK')"
python -c "import joblib; m = joblib.load('deep6/models/interaction_predictor_v4.joblib'); assert m['version'] == 'v4'; print('Interaction model OK')"

# CausalClassifier loads both models
python -c "from deep6.ml.depth_radar.causal_classifier import CausalClassifier; c = CausalClassifier(); assert c.intent_model_loaded and c.interaction_model_loaded; print('Both models loaded')"

# Desktop app launches
python -m depth_radar_desktop --dry-run  # Verify import/init without opening window

# Package structure
python -c "import depth_radar_desktop; print(depth_radar_desktop.__version__)"

# Tests pass
python -m pytest depth_radar_desktop/tests/ -v
```

### Final Checklist
- [ ] V4 intent classifier model exists and loads correctly
- [ ] V4 interaction predictor model exists and loads correctly
- [ ] Desktop app launches with dark theme
- [ ] Live tab: Active Walls table renders
- [ ] Live tab: Feature Gauges render
- [ ] Live tab: Touch Alerts panel renders
- [ ] Live tab: Connection status shows state
- [ ] Research tab: Episode Browser loads parquet data
- [ ] Research tab: Model Dashboard shows metrics
- [ ] All "Must NOT Have" items absent from codebase
- [ ] Tests pass for critical paths
