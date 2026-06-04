# Display Topology Skill — 4-Screen Monitor Knowledge Base

## TL;DR

> **Quick Summary**: Create a `display-topology` skill that documents the user's 4-screen monitor setup (ASUS ZenBook Duo + INNOVIEW INVPM609 dual external) with exact Windows coordinates, screen mapping, and PowerShell commands to dynamically locate any window on any screen.
> 
> **Deliverables**:
> - `.claude/skills/display-topology/knowledge.md` — Hardware map, coordinate system, screen mapping table, runtime detection commands, edge case handling
> - `.claude/skills/display-topology/SKILL.md` — Invocation triggers and workflow
> - `CLAUDE.md` edit — Skill registration in the Project Skills section
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — sequential (3 small deliverables, tight dependencies)
> **Critical Path**: knowledge.md → SKILL.md → CLAUDE.md registration → verify

---

## Context

### Original Request
User wants a new skill so agents know their multi-monitor layout. They have an ASUS ZenBook Duo UX8406MA (dual-screen laptop) connected to an INNOVIEW INVPM609 (dual 23.8" external monitor) via HDMI and USB-C. When agents do UI automation, screenshots, or window management for NinjaTrader/TradingView, they need to know where all 4 screens are and how to find windows on them.

### Interview Summary
**Key Discussions**:
- All applications (NinjaTrader, TradingView, terminal, Claude) have **RANDOM** screen placement — no fixed positions
- Physical layout: Laptop to the LEFT of user, dual monitors directly IN FRONT
- User's numbering convention: Screen 1 (ZenBook top), Screen 2 (ZenBook bottom), Screen 3 (InnoView top), Screen 4 (InnoView bottom)
- Layout is fixed — always the same 4-screen desk setup (ignore travel mode)

**Research Findings — Hardware Discovery (verified via WMI/Win32)**:

| Screen | Hardware ID | Physical Size | Connection | Windows ID |
|--------|-------------|---------------|------------|------------|
| Screen 1 (ZenBook Top) | SDC419D (UID8392785) | 30×19cm (14") | DisplayPort Internal | DISPLAY1 (Primary) |
| Screen 2 (ZenBook Bot) | SDC419D (UID8388688) | 30×19cm (14") | Internal Bus | DISPLAY3 |
| Screen 3 (InnoView Top) | YCT428A (UID8261) | 53×29cm (23.8") | USB-C (DP Alt Mode) | DISPLAY2 |
| Screen 4 (InnoView Bot) | YCT428A (UID41016) | 53×29cm (23.8") | HDMI | DISPLAY4 |

**Windows Coordinate Rectangles (AllScreens — logical/scaled pixels)**:

| Windows ID | Position (X,Y) | Size (W×H) | Working Area H | Scaling | Native Resolution |
|------------|---------------|-------------|----------------|---------|-------------------|
| DISPLAY1 | (0, 0) | 1440×900 | 852 | 200% | 2880×1800 |
| DISPLAY3 | (0, 1800) | 1440×900 | 852 | 200% | 2880×1800 |
| DISPLAY2 | (2880, 586) | 1920×1080 | 1032 | 100% | 1920×1080 |
| DISPLAY4 | (2880, 1666) | 1920×1080 | 1032 | 100% | 1920×1080 |

### Metis Review
**Identified Gaps** (addressed):
- DPI scaling confusion (logical vs native pixels) — addressed: knowledge.md will explicitly document both coordinate spaces and which APIs use which
- Edge cases (minimized windows, multi-process apps, windows spanning two screens) — addressed: included in knowledge.md
- "Last verified" datestamp on hardcoded coordinates — addressed: included
- Must NOT create .ps1 scripts — all commands inline in knowledge.md
- Must NOT duplicate P/Invoke from existing nt8-ui.ps1 — reference it instead

---

## Work Objectives

### Core Objective
Create a skill that gives any agent complete knowledge of the 4-screen display topology — screen coordinates, hardware mapping, and runtime commands to find any window on any screen.

### Concrete Deliverables
- `.claude/skills/display-topology/knowledge.md` — Complete monitor reference
- `.claude/skills/display-topology/SKILL.md` — Skill definition
- `CLAUDE.md` — Updated with skill registration

### Definition of Done
- [ ] `Test-Path ".claude/skills/display-topology/SKILL.md"` returns True
- [ ] `Test-Path ".claude/skills/display-topology/knowledge.md"` returns True
- [ ] `Select-String "display-topology" CLAUDE.md` returns match
- [ ] knowledge.md contains coordinate data for all 4 screens
- [ ] knowledge.md contains runtime detection commands (FromHandle/AllScreens)
- [ ] knowledge.md contains user-name ↔ Windows-ID mapping table

### Must Have
- Exact pixel coordinate rectangles (Bounds, WorkingArea) for all 4 screens
- Explicit DPI scaling documentation (200% on ZenBook, 100% on InnoView)
- User numbering convention (Screen 1-4) mapped to Windows DISPLAY IDs
- PowerShell commands to detect which screen any window is on
- Edge case handling: minimized windows, multi-process apps, no-window processes
- "Last verified: DATE" stamp on hardcoded coordinate data
- ASCII layout diagram of the 4-screen arrangement

### Must NOT Have (Guardrails)
- No `.ps1` script files — all commands inline in knowledge.md
- No window-moving/rearranging automation — this is READ-ONLY topology
- No screenshot-taking logic — that belongs in nt8-expert/nt8-ui.ps1
- No duplicated P/Invoke code from nt8-ui.ps1 — reference it
- No travel mode or alternate layout variations
- No hardware specs beyond what's needed for coordinate math (no color gamut, response time, contrast ratios, etc.)
- No per-application default screen preferences — all placement is RANDOM

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (PowerShell for file checks + content grep)
- **Automated tests**: None (markdown files — no code to test)
- **Framework**: PowerShell `Test-Path` + `Select-String` for acceptance checks

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **File verification**: Use Bash (Test-Path, Select-String) — verify files exist and contain required content
- **Content verification**: Use Bash (Select-String with patterns) — verify all required sections present

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Sequential — tight dependencies):
├── Task 1: Create knowledge.md with full monitor topology [quick]
├── Task 2: Create SKILL.md + register in CLAUDE.md (depends: 1) [quick]
└── Task 3: Verify all deliverables (depends: 1, 2) [quick]

Critical Path: Task 1 → Task 2 → Task 3
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3 | 1 |
| 2 | 1 | 3 | 1 |
| 3 | 1, 2 | — | 1 |

### Agent Dispatch Summary

- **Wave 1**: **3 tasks** — T1 → `quick`, T2 → `quick`, T3 → `quick`

---

## TODOs

- [x] 1. Create knowledge.md — Full Monitor Topology Reference

  **What to do**:
  - Create directory `.claude/skills/display-topology/`
  - Create `knowledge.md` with the following sections:

  **Section 1 — Overview**: One paragraph explaining this is a 4-screen setup (ZenBook Duo + INNOVIEW dual external)

  **Section 2 — Screen Mapping Table**: The canonical mapping between user names, Windows IDs, and hardware:

  ```
  | User Name | Windows ID | Hardware | Size | Connection | Physical Position |
  |-----------|-----------|----------|------|------------|-------------------|
  | Screen 1 | \\.\DISPLAY1 (Primary) | SDC419D (Samsung OLED) | 14" | DisplayPort Internal | LEFT, upper |
  | Screen 2 | \\.\DISPLAY3 | SDC419D (Samsung OLED) | 14" | Internal Bus | LEFT, lower |
  | Screen 3 | \\.\DISPLAY2 | YCT428A (InnoView IPS) | 23.8" | USB-C (DP Alt Mode) | FRONT, upper |
  | Screen 4 | \\.\DISPLAY4 | YCT428A (InnoView IPS) | 23.8" | HDMI | FRONT, lower |
  ```

  **CRITICAL NOTE**: Windows DISPLAY numbering does NOT match user's screen numbering. Screen 2 = DISPLAY3, Screen 3 = DISPLAY2. The mapping table is the single source of truth.

  **Section 3 — Windows Coordinate System**: Exact pixel rectangles for all 4 screens. Include:
  - Bounds (X, Y, Width, Height) in logical/scaled pixels
  - WorkingArea (excludes taskbar)
  - DPI scaling factor per screen (200% for ZenBook, 100% for InnoView)
  - Native resolution vs logical resolution
  - Explicit note: "Most Windows APIs (GetWindowRect, AllScreens.Bounds) report LOGICAL pixels. ZenBook screens are 2880×1800 native but 1440×900 logical at 200% DPI."
  - Include "Last verified: 2026-05-13" stamp

  Use this verified data:
  ```
  DISPLAY1: Bounds=(0, 0, 1440, 900), WorkingArea=(0, 0, 1440, 852), Primary=True, 200% DPI
  DISPLAY3: Bounds=(0, 1800, 1440, 900), WorkingArea=(0, 1800, 1440, 852), 200% DPI
  DISPLAY2: Bounds=(2880, 586, 1920, 1080), WorkingArea=(2880, 586, 1920, 1032), 100% DPI
  DISPLAY4: Bounds=(2880, 1666, 1920, 1080), WorkingArea=(2880, 1666, 1920, 1032), 100% DPI
  ```

  **Section 4 — ASCII Layout Diagram**: Visual representation of the 4-screen grid:
  ```
  LEFT (Laptop)                 FRONT (External Monitors)
  ┌─────────────────┐
  │   Screen 1      │
  │   DISPLAY1      │           ┌───────────────────────┐
  │   1440×900      │           │   Screen 3            │
  │   (PRIMARY)     │           │   DISPLAY2            │
  │   200% DPI      │           │   1920×1080           │
  └─────────────────┘           │   100% DPI            │
                                └───────────────────────┘
  ┌─────────────────┐           ┌───────────────────────┐
  │   Screen 2      │           │   Screen 4            │
  │   DISPLAY3      │           │   DISPLAY4            │
  │   1440×900      │           │   1920×1080           │
  │   200% DPI      │           │   100% DPI            │
  └─────────────────┘           └───────────────────────┘
  ```

  **Section 5 — Runtime Window Detection Commands**: PowerShell commands (inline, NOT .ps1 scripts) for agents to use:

  1. **Find which screen a window is on** (by process name):
  ```powershell
  Add-Type -AssemblyName System.Windows.Forms
  $proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  if ($proc) { [System.Windows.Forms.Screen]::FromHandle($proc.MainWindowHandle) }
  ```

  2. **List all screens with current coordinates** (re-scan if layout changed):
  ```powershell
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.Screen]::AllScreens | ForEach-Object { "$($_.DeviceName) | Primary=$($_.Primary) | Bounds=$($_.Bounds) | WorkingArea=$($_.WorkingArea)" }
  ```

  3. **Find a window's exact position** (by process name):
  ```powershell
  $proc = Get-Process -Name 'NinjaTrader' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
  if ($proc) { Add-Type -AssemblyName System.Windows.Forms; $screen = [System.Windows.Forms.Screen]::FromHandle($proc.MainWindowHandle); Write-Output "Window on: $($screen.DeviceName) | Bounds: $($screen.Bounds)" }
  ```

  4. **Map a pixel coordinate to a screen**:
  ```powershell
  Add-Type -AssemblyName System.Windows.Forms
  [System.Windows.Forms.Screen]::FromPoint([System.Drawing.Point]::new($x, $y))
  ```

  **Section 6 — Edge Cases**: Document these for agents:
  - **Minimized windows**: Position reports as (-32000, -32000). Must restore window first before querying position.
  - **Multi-process apps**: NinjaTrader and TradingView may spawn multiple processes. Filter to `MainWindowHandle -ne 0` to find the one with a visible window.
  - **Window spanning two screens**: `FromHandle()` returns the screen containing the majority of the window area.
  - **TradingView Desktop vs Browser**: Desktop process name is `TradingView`. If using browser-based TradingView, process name varies (chrome, msedge, etc.).
  - **Windows DISPLAY IDs can change**: After driver updates or cable swaps, Windows may reassign DISPLAY numbers. Always verify with the re-scan command.
  - **Reference for window management P/Invoke**: See `ninjatrader/scripts/nt8-ui.ps1` for existing `SetForegroundWindow`, `ShowWindow`, `MainWindowHandle` usage. Do NOT duplicate that code — use it via the nt8-expert skill.

  **Section 7 — Re-scan Command**: Full PowerShell block to re-verify the entire topology if monitors change. Combine WMI monitor ID query + AllScreens bounds + connection type.

  **Must NOT do**:
  - Do NOT create any .ps1 script files
  - Do NOT include color gamut, response time, contrast ratio, or other hardware specs irrelevant to coordinate math
  - Do NOT include window-moving or rearranging commands
  - Do NOT duplicate P/Invoke code from nt8-ui.ps1
  - Do NOT hardcode any per-application screen preferences

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single markdown file with known content — no research or complex logic needed
  - **Skills**: []
    - No skills needed — all data is provided in the plan
  - **Skills Evaluated but Omitted**:
    - `nt8-expert`: Not needed — we reference nt8-ui.ps1 but don't modify it

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (must complete before Task 2)
  - **Blocks**: Task 2, Task 3
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):

  **Pattern References**:
  - `.claude/skills/nt8-expert/knowledge.md` — Follow the knowledge.md structure: headers, code blocks, reference tables
  - `.claude/skills/trading-knowledge/knowledge.md` — Example of a knowledge.md with multiple sections and subsections

  **Data References** (use these EXACT values — already verified via live system query):
  - DISPLAY1: Bounds=(0, 0, 1440, 900), WorkingArea=(0, 0, 1440, 852), Primary, 200% DPI, native 2880×1800
  - DISPLAY2: Bounds=(2880, 586, 1920, 1080), WorkingArea=(2880, 586, 1920, 1032), 100% DPI, native 1920×1080
  - DISPLAY3: Bounds=(0, 1800, 1440, 900), WorkingArea=(0, 1800, 1440, 852), 200% DPI, native 2880×1800
  - DISPLAY4: Bounds=(2880, 1666, 1920, 1080), WorkingArea=(2880, 1666, 1920, 1032), 100% DPI, native 1920×1080
  - Hardware IDs: SDC419D = Samsung Display (ZenBook OLED), YCT428A = InnoView (INNOVIEW IPS)
  - Connection: DISPLAY1=DP Internal, DISPLAY2=USB-C, DISPLAY3=Internal Bus, DISPLAY4=HDMI

  **External References**:
  - `ninjatrader/scripts/nt8-ui.ps1` — Existing P/Invoke for window management (reference, don't duplicate)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: knowledge.md contains all 4 screen coordinate entries
    Tool: Bash (Select-String)
    Preconditions: Task 1 completed, file exists
    Steps:
      1. Run: Select-String "DISPLAY1" ".claude/skills/display-topology/knowledge.md"
      2. Run: Select-String "DISPLAY2" ".claude/skills/display-topology/knowledge.md"
      3. Run: Select-String "DISPLAY3" ".claude/skills/display-topology/knowledge.md"
      4. Run: Select-String "DISPLAY4" ".claude/skills/display-topology/knowledge.md"
    Expected Result: All 4 return at least one match
    Failure Indicators: Any Select-String returns no matches
    Evidence: .sisyphus/evidence/task-1-coordinate-data.txt

  Scenario: knowledge.md contains runtime detection commands
    Tool: Bash (Select-String)
    Preconditions: Task 1 completed
    Steps:
      1. Run: Select-String "FromHandle|FromPoint|AllScreens" ".claude/skills/display-topology/knowledge.md"
    Expected Result: At least 3 matches (FromHandle, FromPoint, AllScreens all present)
    Failure Indicators: Fewer than 3 matches
    Evidence: .sisyphus/evidence/task-1-detection-commands.txt

  Scenario: knowledge.md contains DPI scaling documentation
    Tool: Bash (Select-String)
    Preconditions: Task 1 completed
    Steps:
      1. Run: Select-String "200%" ".claude/skills/display-topology/knowledge.md"
      2. Run: Select-String "100%" ".claude/skills/display-topology/knowledge.md"
      3. Run: Select-String "logical|native" ".claude/skills/display-topology/knowledge.md"
    Expected Result: All return matches — DPI scaling is explicitly documented
    Failure Indicators: Missing DPI documentation
    Evidence: .sisyphus/evidence/task-1-dpi-docs.txt

  Scenario: knowledge.md does NOT contain forbidden content
    Tool: Bash (Select-String)
    Preconditions: Task 1 completed
    Steps:
      1. Run: Select-String "color gamut|contrast ratio|response time|DCI-P3" ".claude/skills/display-topology/knowledge.md"
    Expected Result: No matches — hardware specs beyond coordinate math are excluded
    Failure Indicators: Any match found = scope creep
    Evidence: .sisyphus/evidence/task-1-no-forbidden.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-coordinate-data.txt
  - [ ] task-1-detection-commands.txt
  - [ ] task-1-dpi-docs.txt
  - [ ] task-1-no-forbidden.txt

  **Commit**: YES (groups with Task 2)
  - Message: `feat(skills): add display-topology skill with 4-screen monitor map`
  - Files: `.claude/skills/display-topology/knowledge.md`, `.claude/skills/display-topology/SKILL.md`, `CLAUDE.md`
  - Pre-commit: `Test-Path ".claude/skills/display-topology/knowledge.md"`

- [x] 2. Create SKILL.md + Register in CLAUDE.md

  **What to do**:

  **Part A — Create SKILL.md**:
  Create `.claude/skills/display-topology/SKILL.md` following the `nt8-expert/SKILL.md` pattern:

  ```markdown
  # Display Topology Skill

  Invoke this skill when the user asks you to:
  - Take a screenshot of a specific application window
  - Find which screen an application is on
  - Interact with UI elements across multiple monitors
  - Position or find windows for NinjaTrader, TradingView, or any application
  - Understand the monitor layout for UI automation
  - Debug display or window positioning issues

  ## Skill Entry Point

  Load `knowledge.md` in this directory for the complete 4-screen monitor map,
  Windows coordinate system, and runtime window detection commands.

  ## Workflow

  1. Load `knowledge.md` to understand the 4-screen topology
  2. Use the Screen Mapping Table to translate between user names (Screen 1-4) and Windows DISPLAY IDs
  3. Use the Runtime Detection Commands to find which screen a target window is on
  4. Use the Coordinate System section to understand pixel positions and DPI scaling
  5. For window management P/Invoke (SetForegroundWindow, ShowWindow), reference `ninjatrader/scripts/nt8-ui.ps1`

  ## Base path: C:\Users\Tea\DEEP6\.claude\skills\display-topology\
  ```

  **Part B — Register in CLAUDE.md**:
  Edit `CLAUDE.md` to insert the skill registration BEFORE the `<!-- GSD:skills-end -->` marker (after the `trading-knowledge` entry, line 319). Use this exact format:

  ```markdown
  ### display-topology — Multi-Monitor Display Map

  Skill location: `.claude/skills/display-topology/`

  Invoke this skill when:
  - Taking screenshots or interacting with UI across multiple monitors
  - Finding which screen NinjaTrader, TradingView, or any application is on
  - Doing UI automation that needs to know monitor positions and coordinates
  - Debugging window positioning or display layout issues

  Load `.claude/skills/display-topology/knowledge.md` for the complete 4-screen monitor map,
  coordinate system, DPI scaling reference, and runtime window detection commands.
  ```

  Insert AFTER line 318 (`Load .claude/skills/trading-knowledge/knowledge.md...`) and BEFORE line 320 (`<!-- GSD:skills-end -->`). Add a blank line before and after for consistent formatting.

  **Must NOT do**:
  - Do NOT modify any content outside the skills section markers
  - Do NOT change existing skill registrations
  - Do NOT add the registration outside the `<!-- GSD:skills-start -->` / `<!-- GSD:skills-end -->` markers

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Boilerplate creation + targeted file edit — trivial work
  - **Skills**: []
    - No skills needed
  - **Skills Evaluated but Omitted**:
    - `nt8-expert`: Not needed — we're creating a new skill, not modifying NT8

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (after Task 1)
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References** (CRITICAL):

  **Pattern References**:
  - `.claude/skills/nt8-expert/SKILL.md` — Follow this exact SKILL.md structure (invocation triggers → entry point → workflow → base path)
  - `CLAUDE.md:310-319` — Registration format for `trading-knowledge` skill — follow this pattern exactly

  **Insertion Point**:
  - `CLAUDE.md:319` — After `Load .claude/skills/trading-knowledge/knowledge.md first, then route to the relevant domain, catalog, or reference file as needed.`
  - `CLAUDE.md:320` — Before `<!-- GSD:skills-end -->`
  - Insert new registration between these two lines

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: SKILL.md exists with correct structure
    Tool: Bash (Test-Path + Select-String)
    Preconditions: Task 2 completed
    Steps:
      1. Run: Test-Path ".claude/skills/display-topology/SKILL.md"
      2. Run: Select-String "Invoke this skill when" ".claude/skills/display-topology/SKILL.md"
      3. Run: Select-String "knowledge.md" ".claude/skills/display-topology/SKILL.md"
      4. Run: Select-String "Base path" ".claude/skills/display-topology/SKILL.md"
    Expected Result: Test-Path returns True; all Select-String return matches
    Failure Indicators: File missing or missing required sections
    Evidence: .sisyphus/evidence/task-2-skill-md.txt

  Scenario: CLAUDE.md contains display-topology registration
    Tool: Bash (Select-String)
    Preconditions: Task 2 completed
    Steps:
      1. Run: Select-String "display-topology" CLAUDE.md
      2. Run: Select-String "Multi-Monitor Display Map" CLAUDE.md
      3. Run: Select-String "Invoke this skill when" CLAUDE.md | Where-Object { $_.LineNumber -gt 310 }
    Expected Result: All return matches in the skills section
    Failure Indicators: Registration missing or in wrong location
    Evidence: .sisyphus/evidence/task-2-claude-md.txt

  Scenario: CLAUDE.md skills section is not corrupted
    Tool: Bash (Select-String)
    Preconditions: Task 2 completed
    Steps:
      1. Run: Select-String "GSD:skills-start" CLAUDE.md
      2. Run: Select-String "GSD:skills-end" CLAUDE.md
      3. Run: Select-String "nt8-expert|nt8-fix|nt8-new|nt8-architect|nt8-visual-design|trading-knowledge" CLAUDE.md
    Expected Result: Both GSD markers present; all existing skills still registered
    Failure Indicators: Missing markers or missing existing skill entries = corruption
    Evidence: .sisyphus/evidence/task-2-no-corruption.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-skill-md.txt
  - [ ] task-2-claude-md.txt
  - [ ] task-2-no-corruption.txt

  **Commit**: YES (same commit as Task 1)
  - Message: `feat(skills): add display-topology skill with 4-screen monitor map`
  - Files: `.claude/skills/display-topology/SKILL.md`, `CLAUDE.md`

- [x] 3. Final Verification — All Deliverables

  **What to do**:
  Run all acceptance checks to verify the skill is complete and correct.

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure verification — run commands and check output
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (final)
  - **Blocks**: None
  - **Blocked By**: Task 1, Task 2

  **References**:
  - `.claude/skills/display-topology/knowledge.md` — Verify content
  - `.claude/skills/display-topology/SKILL.md` — Verify structure
  - `CLAUDE.md` — Verify registration

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Complete file existence check
    Tool: Bash (Test-Path)
    Preconditions: Tasks 1 and 2 completed
    Steps:
      1. Run: Test-Path ".claude/skills/display-topology/SKILL.md"
      2. Run: Test-Path ".claude/skills/display-topology/knowledge.md"
    Expected Result: Both return True
    Failure Indicators: Either returns False
    Evidence: .sisyphus/evidence/task-3-files-exist.txt

  Scenario: knowledge.md comprehensive content check
    Tool: Bash (Select-String)
    Preconditions: File exists
    Steps:
      1. Run: Select-String "Screen 1|Screen 2|Screen 3|Screen 4" ".claude/skills/display-topology/knowledge.md"
      2. Run: Select-String "DISPLAY1|DISPLAY2|DISPLAY3|DISPLAY4" ".claude/skills/display-topology/knowledge.md"
      3. Run: Select-String "FromHandle" ".claude/skills/display-topology/knowledge.md"
      4. Run: Select-String "AllScreens" ".claude/skills/display-topology/knowledge.md"
      5. Run: Select-String "200%" ".claude/skills/display-topology/knowledge.md"
      6. Run: Select-String "minimized|Minimized" ".claude/skills/display-topology/knowledge.md"
      7. Run: Select-String "Last verified" ".claude/skills/display-topology/knowledge.md"
    Expected Result: All return at least one match
    Failure Indicators: Any returns no match = missing required content
    Evidence: .sisyphus/evidence/task-3-content-check.txt

  Scenario: CLAUDE.md registration integrity
    Tool: Bash (Select-String)
    Preconditions: Registration added
    Steps:
      1. Run: (Select-String "### " CLAUDE.md | Where-Object { $_ -match "skills" }).Count
      2. Verify count is 7 (6 existing + 1 new display-topology)
    Expected Result: 7 skill headers in CLAUDE.md
    Failure Indicators: Count != 7 (missing or extra entries)
    Evidence: .sisyphus/evidence/task-3-registration.txt
  ```

  **Evidence to Capture:**
  - [ ] task-3-files-exist.txt
  - [ ] task-3-content-check.txt
  - [ ] task-3-registration.txt

  **Commit**: NO (verification only — no file changes)

---

## Final Verification Wave

> Since this is a small skill creation (3 markdown deliverables), the Final Verification is integrated into Task 3 rather than requiring 4 separate review agents. Task 3 performs all necessary checks.

---

## Commit Strategy

- **1**: `feat(skills): add display-topology skill with 4-screen monitor map` — `.claude/skills/display-topology/knowledge.md`, `.claude/skills/display-topology/SKILL.md`, `CLAUDE.md`

---

## Success Criteria

### Verification Commands
```powershell
Test-Path ".claude/skills/display-topology/SKILL.md"      # Expected: True
Test-Path ".claude/skills/display-topology/knowledge.md"   # Expected: True
Select-String "display-topology" CLAUDE.md                 # Expected: match found
Select-String "DISPLAY1" ".claude/skills/display-topology/knowledge.md"  # Expected: match
Select-String "DISPLAY2" ".claude/skills/display-topology/knowledge.md"  # Expected: match
Select-String "DISPLAY3" ".claude/skills/display-topology/knowledge.md"  # Expected: match
Select-String "DISPLAY4" ".claude/skills/display-topology/knowledge.md"  # Expected: match
Select-String "FromHandle|AllScreens" ".claude/skills/display-topology/knowledge.md"  # Expected: match
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] knowledge.md contains all 4 screen coordinates
- [ ] knowledge.md contains runtime detection commands
- [ ] SKILL.md follows nt8-expert convention
- [ ] CLAUDE.md registration follows existing format
