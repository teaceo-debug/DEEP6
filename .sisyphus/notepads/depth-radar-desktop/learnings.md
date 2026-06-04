# depth-radar-desktop — Learnings

## Progress Snapshot (ses_17ea36d88ffe4uTLcVAPoqzP9P)
- Wave 1: 5/5 complete (training, skeleton, theme, bridge, config)
- Wave 2: 5/5 complete (walls table, gauges, alerts, status bar, main window)
- Wave 3: 4/4 complete (engine worker, live tab, episode browser, model dashboard)
- Wave 4: 3/4 in progress (integration, tests, README running; T15 deferred)
- Training fix: episodes.parquet had duplicate episode_ids → added drop_duplicates in train script
- Training used --skip-label with cached parquet from data/depth_radar_v4/
- Intent F1: 0.4735, Interaction F1: 0.8520

## Session: ses_17ea36d88ffe4uTLcVAPoqzP9P | 2026-06-01

### Project Structure
- Working in C:\Users\Tea\DEEP6 (repo root, no worktree)
- Package goes at: depth_radar_desktop/ (repo root)
- Engine stays in: deep6/ml/depth_radar/ (do NOT touch)
- Models output to: deep6/models/ (training copies here)
- Training output: training_output/depth_radar_v4_3day/ and _30day/

### Critical Architecture: asyncio↔Qt Bridge
- NEVER use qasync (fragile on Windows)
- Pattern: threading.Thread runs asyncio.run(), Qt signals bridge data
- Signal.emit() IS thread-safe in PySide6 — use it for callbacks
- QMetaObject.invokeMethod() for extra safety if needed
- EngineBridge(QObject) owns the thread, exposes Signal(list) for walls

### MBO Data Files
- 3-day: data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst (897 MB)
- 30-day: data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst (6.4 GB)

### get_active_walls() Return Keys
Keys: episode_id, price, side, size, max_size, age_sec, intent, state, in_touch_band
+ all 44 causal feature keys (from CAUSAL_FEATURE_NAMES)
Side values: float (1.0=ask, 0.0=bid) — normalize for display
Intent values: PASSIVE_REAL, SPOOF_LIKE, RESERVE_REFRESH, MIGRATORY
State values: FRESH, ESTABLISHED, UNDER_ATTACK, DEFENDING, EXHAUSTED, CONSUMED, PULLED, STALE

### Model Paths (absolute required)
- Intent: deep6/models/intent_classifier_v4.joblib
- Interaction: deep6/models/interaction_predictor_v4.joblib
- Must resolve relative to project root — not CWD

### Python Version Note
- Project uses Python 3.11.9 (pytest runs on 3.11.9)
- PySide6 supports 3.8+, compatible with 3.11

### Dark Theme Colors (locked)
- background: #0d1117
- panel: #161b22
- border: #30363d
- text primary: #e6edf3
- text secondary: #8b949e
- green: #3fb950
- red: #f85149
- amber: #d29922
- blue: #58a6ff

### Skeleton Build Notes
- Package root is `depth_radar_desktop/` at repo root; imports work from repo root without installing.
- `python -m depth_radar_desktop --dry-run` should avoid importing PySide6 so skeleton verification works in minimal envs.
- Global QSS should keep dark terminal aesthetics only; avoid widget-specific styling until later UI tasks.

## Session: ses_current | 2026-06-01

### Task 4 — EngineBridge lifecycle
- For `source="none"`, emit `connection_changed(False)` synchronously in `start()` so the lifecycle smoke test can observe the event without running `QCoreApplication.exec()`.
- `LiveMBORadar` should be imported lazily inside the bridge so disconnected/demo mode works even when full live dependencies are unavailable.
- Emit copies of wall payloads (`[dict(wall) for wall in walls]`) before crossing the Qt thread boundary.
- Local verification required a temp PySide6 venv at `C:\Users\Tea\AppData\Local\Temp\opencode\depth-radar-pyside6-test`; current default Python envs in repo do not ship with PySide6.
