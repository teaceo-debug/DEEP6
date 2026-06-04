# DEEP6 Bias v3 ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â NinjaTrader 8 HUD Display

## TL;DR

> **Quick Summary**: Render the v3 bias engine output on NinjaTrader 8 charts as a SharpDX HUD overlay. Python writes MarketBiasSnapshot as JSON, NT8 indicator polls and renders a top-left panel showing BIAS direction, SCORE, CONFIDENCE, MODE traffic light, and SESSION state.
>
> **Deliverables**:
> - Python JSON writer that serializes MarketBiasSnapshot to bias_v3.json
> - NinjaScript indicator (DEEP6BiasV3.cs) with SharpDX HUD panel
> - Deploy via nt8-deploy.ps1
>
> **Estimated Effort**: Medium
> **Parallel Execution**: YES ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â 2 waves
> **Critical Path**: T1 -> T2 -> T3 -> T4 -> Final
> **Dependency**: Requires bias-v3 plan to complete first (MarketBiasEngine must exist)

---

## Context

### Original Request
User wants to display the v3 bias engine output on NinjaTrader 8 charts.

### Interview Summary
- **Transport**: JSON file polling (like GEXCommand.cs pattern)
- **Display**: HUD panel overlay in top-left (like DEEP6Signal.cs pattern)
- **Content**: BIAS direction + SCORE + CONFIDENCE + MODE (GO/CAUTION/STOP) + SESSION
- **Deploy**: Via existing nt8-deploy.ps1 script
- **Dependency**: bias-v3 plan must complete first

### Design Reference
docs/market-bias-engine-design.md section 7 specifies the chart output:
- Bias banner: BIAS label, SCORE, CONF%, MODE, SESSION
- Color coding: green for bullish, red for bearish, amber for neutral/caution
- Warning states shown separately from bias

---

## Work Objectives

### Core Objective
Render MarketBiasSnapshot from the v3 bias engine as a persistent HUD overlay on NinjaTrader 8 charts, using the proven GEXCommand.cs file-polling pattern for data transport and DEEP6Signal.cs SharpDX pattern for rendering.

### Deliverables
- deep6/engines/bias_json_writer.py ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â serializes MarketBiasSnapshot to JSON file
- ninjatrader/Custom/Indicators/DEEP6/DEEP6BiasV3.cs ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â NinjaScript indicator with HUD
- Deploy verification via nt8-deploy.ps1

### Definition of Done
- [ ] Python writes bias_v3.json on every MarketBiasEngine.compute_bias() call
- [ ] NT8 indicator reads JSON, renders HUD with correct bias data
- [ ] HUD shows: direction label, signed score, confidence %, traffic light, session
- [ ] Indicator compiles clean (0 errors) in NinjaScript Editor
- [ ] Stale data handling: HUD shows "STALE" after configurable timeout
- [ ] Cold start: HUD shows "WAITING" when no JSON file exists

### Must Have
- File-based JSON transport (Python writes, NT8 reads)
- SharpDX HUD panel with bias direction, score, confidence, mode, session
- Color-coded traffic light: green (GO), amber (CAUTION), red (STOP)
- Direction color: green (BULL), red (BEAR), gray (NEUTRAL)
- Stale data detection (file age > threshold)
- Cold start handling (no file yet)
- Configurable refresh interval (default 5s)
- Configurable file path

### Must NOT Have
- DO NOT modify any existing NT8 indicators
- DO NOT use WebSocket or TCP ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â JSON file only
- DO NOT render on the price panel ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â separate HUD overlay
- DO NOT include trade setup details (entry/SL/TP) ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â bias only
- DO NOT hard-code file paths ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â use NinjaTrader user properties

---

## Verification Strategy

> NT8 indicators cannot be pytest-tested. Verification is compile + deploy + visual.

### Test Decision
- **Python writer**: pytest (unit test with mock MarketBiasSnapshot)
- **NT8 indicator**: Compile verification via F5 in NinjaScript Editor
- **Integration**: Deploy + attach to chart + visual verification

### QA Policy
- Python: pytest for JSON writer
- NT8: nt8-deploy.ps1 + compile check + screenshot evidence

---

## Execution Strategy

### Waves

```
Wave 0 (Python side ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â can start after bias-v3 Wave 3 completes):
  Task 1: Bias JSON writer [quick]
  Task 2: JSON schema definition [quick]

Wave 1 (NT8 side ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â after Wave 0):
  Task 3: DEEP6BiasV3.cs indicator [deep]
  Task 4: Deploy + compile verification [quick]

Wave FINAL:
  F1: Plan compliance (oracle)
  F2: Code quality (unspecified-high)
  F3: Visual QA on NT8 chart (unspecified-high)
  F4: Scope fidelity (deep)
```

### Dependencies
| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | bias-v3 T15 | 3 | 0 |
| 2 | 1 | 3 | 0 |
| 3 | 1, 2 | 4 | 1 |
| 4 | 3 | F1-F4 | 1 |

---

## TODOs

- [x] 1. Bias JSON Writer (Python)

  **What to do**:
  - Create deep6/engines/bias_json_writer.py:
    - BiasJsonWriter class: serializes MarketBiasSnapshot to JSON file
    - write(snapshot: MarketBiasSnapshot, path: Path) -> None
    - JSON structure: flat dict with all display-relevant fields:
      - bias_label (str): "STRONG BULL" / "LEAN BULL" / "NEUTRAL" / "LEAN BEAR" / "STRONG BEAR"
      - bias_score (int): -9 to +9
      - confidence (float): 0.0 to 1.0
      - confidence_pct (int): 0 to 100 (pre-formatted for display)
      - mode (str): "GO" / "CAUTION" / "STOP"
      - mode_reason (str): human-readable reason
      - session_label (str): "A+ OPEN" / "MID-AM" / "LUNCH" / "POWER" / "AVOID"
      - xamd_phase (str): "ACCUMULATION" / "MANIPULATION" / "DISTRIBUTION" / "BETWEEN"
      - domain_scores (dict): {ict: int, macro: int, flow: int, kronos: int}
      - setup_quality (int): 0-5
      - updated_ts (float): Unix timestamp
      - version (str): "v3"
    - Atomic write: write to temp file then rename (prevents NT8 reading partial JSON)
    - File path default: configurable, default to %USERPROFILE%/Documents/NinjaTrader 8/templates/DEEP6/bias_v3.json
  - Hook into MarketBiasEngine.compute_bias() to auto-write after each computation
  - Tests: tests/test_bias_json_writer.py

  **Must NOT do**:
  - Do NOT use WebSocket or TCP
  - Do NOT write to NT8's Custom/ directory ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â use templates/DEEP6/

  **Agent**: quick | **Skills**: [] | **Wave**: 0 | **Blocks**: 3 | **Blocked By**: bias-v3 T15

  **References**:
  - deep6/engines/market_bias_engine.py ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â MarketBiasSnapshot (from bias-v3 plan)
  - deep6/engines/bias_contracts.py ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â MarketBiasSnapshot, BiasState, BiasMode dataclasses
  - ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs:166-170 ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â how NT8 reads JSON (must match structure)

  **Acceptance**:
  - [ ] deep6/engines/bias_json_writer.py created
  - [ ] pytest tests/test_bias_json_writer.py -> PASS
  - [ ] JSON file written with atomic rename

  **QA Scenarios**:
  ```
  Scenario: JSON written with correct structure
    Tool: Bash (python -m pytest)
    Steps:
      1. pytest tests/test_bias_json_writer.py::test_write_snapshot -v
      2. Mock MarketBiasSnapshot, write to temp path, read back, assert all fields present
    Expected: All fields present, bias_label == "STRONG BULL", mode == "GO"
    Evidence: .sisyphus/evidence/task-1-json-write.txt

  Scenario: Atomic write prevents partial reads
    Tool: Bash (python -m pytest)
    Steps:
      1. pytest tests/test_bias_json_writer.py::test_atomic_write -v
      2. Verify temp file created then renamed (not direct write)
    Evidence: .sisyphus/evidence/task-1-atomic.txt
  ```

  **Commit**: YES
  - Message: feat(bias-v3): add JSON writer for NT8 bias display
  - Pre-commit: pytest tests/test_bias_json_writer.py

- [x] 2. JSON Schema Definition

  **What to do**:
  - Create ninjatrader/Custom/AddOns/DEEP6/bias_v3_schema.json:
    - JSON Schema document defining the expected structure for bias_v3.json
    - Serves as the contract between Python writer (T1) and NT8 reader (T3)
    - Include field descriptions, types, and value ranges
  - This is documentation/contract only ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â not executable code

  **Agent**: quick | **Wave**: 0 | **Blocks**: 3 | **Blocked By**: 1

  **Acceptance**: Schema file created with all field definitions matching T1 output

  **Commit**: YES (groups with T1)

- [x] 3. DEEP6BiasV3.cs Ã¢â‚¬â€ NinjaScript HUD Indicator

  **What to do**:
  - Create ninjatrader/Custom/Indicators/DEEP6/DEEP6BiasV3.cs:
    - NinjaTrader 8 indicator that reads bias_v3.json and renders HUD overlay
    - **Data Loading** (follow GEXCommand.cs pattern):
      - Timer-based refresh (configurable RefreshSeconds, default 5)
      - Read JSON via System.Web.Script.Serialization.JavaScriptSerializer
      - FileShare.ReadWrite for non-blocking reads
      - Track file modify time to skip re-parse when unchanged
      - Stale detection: if file age > StaleThresholdSeconds (default 30), show "STALE"
      - Cold start: if file doesn't exist, show "WAITING FOR BIAS ENGINE"
    - **HUD Rendering** (follow DEEP6Signal.cs pattern):
      - Position: top-left corner with configurable offset
      - Size: approximately 280x120px
      - Background: dark semi-transparent panel with rounded corners
      - Layout (top to bottom):
        - Row 1: BIAS direction label + arrow glyph (e.g., "STRONG BULL ^")
          - Color: green (#00C853) for BULL states, red (#FF1744) for BEAR, gray (#78909C) for NEUTRAL
          - Font: bold, 14pt
        - Row 2: "Score: +7" + "Conf: 85%" (side by side)
          - Score colored same as direction
          - Confidence: white text
        - Row 3: MODE traffic light ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â circle + label
          - GO: green circle + "GO" in green
          - CAUTION: amber circle + "CAUTION" in amber
          - STOP: red circle + "STOP" in red
        - Row 4: Session label + XAMD phase
          - e.g., "A+ OPEN | DISTRIBUTION"
        - Row 5 (if stale): "STALE (15s ago)" in amber/red
      - SharpDX rendering with 8Hz throttle (125ms minimum between renders)
      - Dispose all SharpDX resources properly in OnRenderTargetChanged
    - **User Properties** (configurable in NT8 UI):
      - JsonFilePath (string): path to bias_v3.json
      - RefreshSeconds (int, default 5): polling interval
      - StaleThresholdSeconds (int, default 30): when to show STALE
      - HudOffsetX (int, default 15): X offset from chart edge
      - HudOffsetY (int, default 15): Y offset from chart edge
      - HudOpacity (float, default 0.85): background opacity
    - Namespace: NinjaTrader.NinjaScript.Indicators.DEEP6

  **Must NOT do**:
  - Do NOT modify any existing indicator files
  - Do NOT render on the price panel (IsOverlay = true, DrawOnPricePanel = false)
  - Do NOT use WebSocket or HTTP ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â file-based only
  - Do NOT include trade setup rendering (entry/SL/TP) ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â bias only
  - Do NOT forget to dispose SharpDX resources (memory leak)

  **Agent**: deep | **Skills**: [nt8-new] | **Wave**: 1 | **Blocks**: 4 | **Blocked By**: 1, 2

  **References**:
  - ninjatrader/Custom/Indicators/DEEP6/GEXCommand.cs ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â File polling pattern (Timer, JavaScriptSerializer, FileStream with FileShare.ReadWrite). Lines 166-170 for JSON reading, Timer setup pattern.
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â SharpDX HUD rendering pattern. Lines 1-80 for imports/setup, HudRenderer nested class for SharpDX rendering with throttle, resource disposal patterns.
  - docs/market-bias-engine-design.md:388-425 ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â Section 7 bias banner specification
  - ninjatrader/Custom/AddOns/DEEP6/bias_v3_schema.json ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â from T2, JSON structure contract

  **WHY Each Reference Matters**:
  - GEXCommand.cs is the EXACT pattern for file-based external data consumption ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â copy the Timer + FileStream + JavaScriptSerializer approach
  - DEEP6Signal.cs shows how to build SharpDX overlays that don't flicker, properly dispose resources, and throttle rendering
  - Design doc section 7 defines WHAT to display ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â follow it exactly

  **Acceptance**:
  - [ ] DEEP6BiasV3.cs created in ninjatrader/Custom/Indicators/DEEP6/
  - [ ] Follows GEXCommand.cs file-reading pattern
  - [ ] Follows DEEP6Signal.cs SharpDX rendering pattern
  - [ ] All SharpDX resources properly disposed
  - [ ] User properties configurable in NT8 UI

  **QA Scenarios**:
  ```
  Scenario: Indicator compiles clean
    Tool: Bash (nt8-deploy.ps1 + nt8-compile.ps1)
    Preconditions: NT8 running, NinjaScript Editor accessible
    Steps:
      1. Run: .\ninjatrader\scripts\nt8-deploy.ps1 -Target Indicators
      2. Run: .\ninjatrader\scripts\nt8-compile.ps1
      3. Assert: [COMPILE-RESULT] SUCCESS, 0 errors
    Expected: Clean compile, indicator appears in NT8 indicator list
    Evidence: .sisyphus/evidence/task-3-compile.txt

  Scenario: HUD renders with mock JSON
    Tool: Bash (create test JSON + screenshot)
    Preconditions: Indicator compiled and added to NQ chart
    Steps:
      1. Write test bias_v3.json with: bias_label="LEAN BULL", score=+5, confidence=0.72, mode="GO", session="MID-AM"
      2. Wait 5s for indicator to poll
      3. Capture screenshot via nt8-ui.ps1
      4. Assert: HUD panel visible in top-left with correct values
    Expected: Green "LEAN BULL" label, "+5" score, "72%" confidence, green GO circle
    Evidence: .sisyphus/evidence/task-3-hud-render.png

  Scenario: Stale data shows warning
    Tool: Bash (age JSON file + screenshot)
    Steps:
      1. Write bias_v3.json with updated_ts = 60 seconds ago
      2. Wait for indicator to poll
      3. Assert: "STALE" warning visible in amber/red
    Evidence: .sisyphus/evidence/task-3-stale.png

  Scenario: Cold start shows waiting message
    Tool: Bash (delete JSON + screenshot)
    Steps:
      1. Delete bias_v3.json (or point to nonexistent path)
      2. Wait for indicator to poll
      3. Assert: "WAITING FOR BIAS ENGINE" message displayed
    Evidence: .sisyphus/evidence/task-3-cold-start.png
  ```

  **Commit**: YES
  - Message: feat(nt8): add DEEP6BiasV3 HUD indicator for v3 bias display
  - Pre-commit: nt8-deploy.ps1 + nt8-compile.ps1

- [x] 4. Deploy and Compile Verification

  **What to do**:
  - Deploy DEEP6BiasV3.cs to NT8 via nt8-deploy.ps1
  - Verify clean compile (0 errors) in NinjaScript Editor
  - Add indicator to an NQ chart
  - Write a test bias_v3.json and verify HUD renders
  - Capture screenshot evidence

  **Agent**: quick | **Skills**: [nt8-expert] | **Wave**: 1 | **Blocks**: F1-F4 | **Blocked By**: 3

  **Acceptance**:
  - [ ] nt8-deploy.ps1 completes without errors
  - [ ] F5 compile: 0 errors
  - [ ] Indicator appears in NT8 indicator list
  - [ ] HUD renders on chart with test data

  **Commit**: NO (verification only)

---

## Final Verification Wave

- [x] F1. **Plan Compliance** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â oracle: Verify all deliverables, Must Have/Must NOT Have.
- [x] F2. **Code Quality** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â unspecified-high: Review C# for resource leaks, proper disposal, no hard-coded paths.
- [x] F3. **Visual QA** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â unspecified-high (+ nt8-expert skill): Attach to NQ chart, verify all 5 HUD rows render correctly, test GO/CAUTION/STOP states, test stale/cold-start.
- [x] F4. **Scope Fidelity** ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â deep: No existing indicators modified, only DEEP6BiasV3.cs is new.

---

## Commit Strategy

| Wave | Message | Pre-commit |
|------|---------|------------|
| 0 | feat(bias-v3): add JSON writer for NT8 bias display | pytest tests/test_bias_json_writer.py |
| 1 | feat(nt8): add DEEP6BiasV3 HUD indicator | nt8-deploy.ps1 + nt8-compile.ps1 |

---

## Success Criteria

### Verification Commands
```
pytest tests/test_bias_json_writer.py -v       # JSON writer tests pass
.\ninjatrader\scripts\nt8-deploy.ps1            # Deploy to NT8
.\ninjatrader\scripts\nt8-compile.ps1           # Compile clean
```

### Final Checklist
- [ ] Python writes valid bias_v3.json with atomic rename
- [ ] NT8 indicator compiles clean (0 errors)
- [ ] HUD renders all 5 rows: direction, score+conf, mode, session, stale warning
- [ ] GO/CAUTION/STOP traffic light colors correct
- [ ] Stale data detected and displayed
- [ ] Cold start handled gracefully
- [ ] No existing indicators modified
- [ ] All SharpDX resources properly disposed