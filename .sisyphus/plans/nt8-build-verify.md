# nt8-build-verify: End-to-End NinjaTrader 8 Development Pipeline

## TL;DR

> **Quick Summary**: Build a Claude Code skill that fully automates the NT8 development loop — deploy .cs → compile → iteratively fix errors → install on chart → screenshot → LLM visual verify → report. Zero human in the loop. Leverages 11 existing PowerShell scripts (~60% reuse) with new scripts for headless compile, fix routing, chart installation, and visual verification.
>
> **Deliverables**:
> - Complete skill directory at `.claude/skills/nt8-build-verify/` with SKILL.md, knowledge.md, 12 scripts, 2 lib modules, 8 fix recipes, README.md
> - Orchestrator pipeline: deploy → compile → fix loop (max 8 iterations) → install → screenshot → verify
> - 8 fix recipes for common CS#### errors (CS0103, CS0246, CS1061, CS0019, CS0101, CS0535, BRACE_MISMATCH, MISSING_ATTRIBUTE)
> - UIA-based chart installation (Ctrl+I dialog) with workspace XML fallback
> - LLM vision verification with PASS / PASS_WITH_NOTES / FAIL verdicts
> - Full artifact trail: compile-log.json, errors.json, fix-diffs/, screenshot-{HHMMSS}.png, verdict-{HHMMSS}.json, timing.json
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES — 5 waves + Final verification
> **Critical Path**: T2 → T8 → T13 → T16 → T17 → T18 → F1-F4

---

## Context

### Original Request
Build a Claude Code skill named `nt8-build-verify` that closes the loop on NinjaTrader 8 indicator/strategy development. Given a spec (or existing .cs file), the skill must deploy, compile, iteratively fix errors, install on a chart, screenshot, visually verify, and report — with no human in the loop.

### Interview Summary
**Key Discussions**:
- **Compile strategy**: Three paths available — DEEP6DevAddon HTTP API (fastest), NinjaScript.exe /compile (headless), NinjaScript Editor F5 via UIAutomation (authoritative). Plan uses HTTP/NinjaScript.exe for fast inner loop, Editor F5 for final registration.
- **UIAutomation approach**: Existing codebase uses native PowerShell `System.Windows.Automation` exclusively (2,818 lines across 11 scripts). No pywinauto. Decision: keep PowerShell for all NT8 UI automation, Python only for logic-heavy processing.
- **Reuse map**: ~60% of needed automation exists in `ninjatrader/scripts/`. New scripts needed for: headless compile, fix routing, chart installation UIA, workspace XML mutation, visual verification, orchestrator.
- **Script location**: Skill-specific scripts go in `.claude/skills/nt8-build-verify/scripts/` (deliberate pattern break from existing skills which only contain .md files — justified because these are skill-specific orchestration, not general NT8 tooling).
- **Error fix scope**: Pattern-matching only, locked to 8 error codes for v1. No AI-semantic code understanding.

**Research Findings**:
- 11 existing PowerShell scripts totaling 2,818 lines cover: deployment (hash-based sync), UIAutomation compile (F5 + DLL poll), error scraping (DataGrid → JSON), screenshot (System.Drawing), status/context snapshots
- `nt8-ui.ps1 -Action AddIndicator` currently prints manual instructions only — no actual UIA automation for chart installation exists
- No visual verification, OCR, or image comparison code exists anywhere in the codebase
- Workspace XML (`Main.xml`) references indicators by GUID and assembly-qualified class name — chart installation via XML requires GUID discovery
- DEEP6.csproj (net48) exists with post-build deploy target; auto-deploy.ps1 uses NinjaScript.exe /compile
- Verified NT8 paths: `C:\Users\Tea\Documents\NinjaTrader 8\` (user data), `C:\Users\Tea\DEEP6\ninjatrader\Custom\` (repo source)

### Metis Review
**Identified Gaps** (all addressed):
- **Modal dialog detection**: NT8 modal dialogs (crash report, update prompt, save changes) block all UIAutomation silently → Added T5 (modal_detect.ps1) called before every UIA operation
- **Runtime exceptions after compile success**: Indicator throws OnBarUpdate exception, invisible to compile loop → Added T11 (runtime_check.ps1) for post-install log grep
- **Fix rollback**: Fixes that increase error count must be reverted → Added rollback logic to T13 (fix_router.py)
- **Vision loop limit**: Visual verification needs MAX 2 attempts to prevent infinite loops → Added to T12 and T17
- **Workspace XML GUID discovery**: Indicators referenced by GUID in workspace XML → Documented as complexity in T15
- **Script location pattern break**: No existing skills have scripts/ subdirectory → Justified: skill-specific orchestration scripts, not general NT8 tooling
- **Error code set locked for v1**: Prevent scope creep into unlimited error handling → Locked to 8 codes
- **Active strategy protection**: Must not kill/restart NT8 if live strategies running → Added safety check
- **Compile warning vs error distinction**: CS warnings should not trigger fix attempts → Added to T10 parse_errors.py

---

## Work Objectives

### Core Objective
Create the `nt8-build-verify` skill that takes a NinjaScript spec or .cs file, compiles it to a clean build, installs it on a target chart, and visually verifies it renders correctly — fully autonomously with zero human intervention.

### Concrete Deliverables
```
.claude/skills/nt8-build-verify/
├── SKILL.md                    # Trigger description + workflow entry point
├── knowledge.md                # Paths, patterns, compile strategies, troubleshooting
├── scripts/
│   ├── deploy.ps1              # Atomic deploy wrapper (dot-sources nt8-deploy.ps1)
│   ├── compile_headless.ps1    # Path A: DevAddon HTTP → NinjaScript.exe → MSBuild
│   ├── compile_editor.ps1      # Path B: UIAutomation F5 wrapper (dot-sources nt8-compile.ps1)
│   ├── modal_detect.ps1        # Detect/dismiss NT8 modal dialogs before UIA
│   ├── parse_errors.py         # Structured error enrichment from JSON
│   ├── fix_router.py           # CS#### → fix strategy dispatch + rollback
│   ├── fix_loop.ps1            # Iterative compile→parse→fix→recompile loop
│   ├── install_indicator.ps1   # Path X: UIA via Indicators dialog (Ctrl+I)
│   ├── workspace_mutator.py    # Path Y: XML backup + inject (fallback)
│   ├── screenshot_chart.ps1    # Targeted window capture (not full screen)
│   ├── runtime_check.ps1       # Post-install log grep for exceptions
│   ├── verify_visual.py        # LLM vision check + auto-checks + report
│   └── orchestrator.ps1        # Top-level pipeline: deploy → verify
├── lib/
│   ├── nt8_paths.py            # Path detection + assumption validation
│   └── diagnostics.py          # Shared diagnostic utilities + error models
├── fixes/
│   ├── CS0103.md               # Missing member fix recipe
│   ├── CS0246.md               # Type/namespace not found fix recipe
│   ├── CS1061.md               # Missing method fix recipe
│   ├── CS0019.md               # Operator mismatch fix recipe
│   ├── CS0101.md               # Duplicate type name fix recipe
│   ├── CS0535.md               # Interface not implemented fix recipe
│   ├── BRACE_MISMATCH.md       # Region/brace mismatch fix recipe
│   └── MISSING_ATTRIBUTE.md    # Missing [Browsable(false)]/[XmlIgnore] fix recipe
└── README.md                   # Setup, usage, troubleshooting
```

### Definition of Done
- [ ] `nt8-build-verify` skill triggered by Claude when user says "build this indicator and put it on my chart"
- [ ] E2E: trivial SMA indicator deploys, compiles, installs on NQ chart, screenshot shows SMA line rendering
- [ ] E2E: injected CS0246 error is automatically fixed within 8 iterations
- [ ] E2E: visual mismatch (spec says blue, renders red) detected as FAIL by LLM vision
- [ ] All artifacts under `./artifacts/<run-id>/` after every run (success or failure)
- [ ] Idempotent: running twice on same source produces same result, no duplicate indicators

### Must Have
- Atomic file deployment (temp path → move, no half-written files)
- Three-tier compile: DevAddon HTTP (fastest) → NinjaScript.exe (headless) → Editor F5 (authoritative)
- Error-fix loop with MAX_ITERATIONS=8, surgical fixes, diff per iteration, rollback on error-count increase
- Chart installation via UIA (Ctrl+I → search → add → set params → OK)
- Workspace XML mutation as fallback with mandatory backup
- Screenshot of chart window region saved as `screenshot-{HHMMSS}.png` (timestamped, never overwritten)
- LLM vision verification: PASS / PASS_WITH_NOTES / FAIL (max 2 vision attempts)
- Post-install runtime error check (log grep for exceptions matching indicator class name)
- Modal dialog detection before every UIAutomation operation
- Complete artifact trail: compile-log.json, errors.json, fix-diffs/, screenshot-{HHMMSS}.png, verdict-{HHMMSS}.json, timing.json
- Configurable timeouts: compile (60s), render settle (1500ms), UIA element wait (5s)

### Must NOT Have (Guardrails)
- **G1**: Fixes modify ONLY the file containing the error — never "improve" adjacent files
- **G2**: If fix requires semantic understanding beyond pattern matching, emit NEEDS_HUMAN and stop
- **G3**: Before ANY workspace XML write: backup to `*.backup-{timestamp}`, validate well-formedness after
- **G4**: Never kill/restart NT8 without checking for active live strategies first
- **G5**: Visual verification gets MAX 2 attempts — no infinite fix-verify-fix loops
- **G6**: Artifacts once written are never overwritten — subsequent attempts create new timestamped files
- **G7**: v1 handles ONLY locked error code set (CS0103, CS0246, CS1061, CS0019, CS0101, CS0535, BRACE_MISMATCH, MISSING_ATTRIBUTE)
- **G8**: Fixes must make intended code work — never fix by removing/commenting out the offending code
- **G9**: No strategy enablement, parameter configuration, or NT8 settings changes
- **G10**: No multi-indicator orchestration — single indicator/strategy per run
- **G11**: No fix recipe authoring/updating during execution

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: YES (pytest in pyproject.toml, Pester available for PowerShell)
- **Automated tests**: NO — acceptance criteria ARE E2E integration tests
- **Framework**: N/A — skill verification is end-to-end pipeline execution
- **QA Method**: Agent-executed QA scenarios using Bash (PowerShell commands), file verification, and LLM vision

### QA Policy
Every task MUST include agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **PowerShell scripts**: Use Bash to invoke with test parameters, assert exit codes + JSON output structure
- **Python modules**: Use Bash (`python -c "..."` or `python script.py --test`) to verify imports, function outputs
- **UIA automation**: Use Bash to invoke against running NT8, assert sentinel outputs + artifact creation
- **Visual verification**: Use LLM vision on captured screenshots + assert verdict JSON structure

---

## Execution Strategy

### Parallel Execution Waves

> Maximize throughput by grouping independent tasks into parallel waves.
> Each wave completes before the next begins.
> "Halt and report after each step" from spec → each wave is a checkpoint.

```
Wave 1 (Foundation — 7 parallel tasks, no dependencies):
├── T1:  Scaffold + SKILL.md + knowledge.md              [quick]
├── T2:  lib/nt8_paths.py (path detection + validation)   [quick]
├── T3:  lib/diagnostics.py (shared utilities)             [quick]
├── T4:  Fix recipes (8 .md files)                         [writing]
├── T5:  scripts/modal_detect.ps1                          [unspecified-high]
├── T6:  scripts/deploy.ps1 (atomic wrapper)               [quick]
└── T7:  scripts/screenshot_chart.ps1                      [unspecified-high]

Wave 2 (Core Compile + Parse — 5 parallel tasks):
├── T8:  scripts/compile_headless.ps1 (depends: T2)        [deep]
├── T9:  scripts/compile_editor.ps1 (depends: T2, T5)      [quick]
├── T10: scripts/parse_errors.py (depends: T3)             [unspecified-high]
├── T11: scripts/runtime_check.ps1 (depends: T2)           [quick]
└── T12: scripts/verify_visual.py (depends: T3, T7)        [deep]

Wave 3 (Fix + Install — 3 parallel tasks):
├── T13: scripts/fix_router.py (depends: T4, T10)          [deep]
├── T14: scripts/install_indicator.ps1 (depends: T2, T5)   [deep]
└── T15: scripts/workspace_mutator.py (depends: T2)        [unspecified-high]

Wave 4 (Fix Loop — 1 task, depends on T13):
└── T16: scripts/fix_loop.ps1 (depends: T5, T6, T8, T9, T10, T13) [deep]

Wave 5 (Full Pipeline — 1 task):
└── T17: scripts/orchestrator.ps1 (depends: ALL T1-T16)    [deep]

Wave 6 (E2E Tests — SEQUENTIAL, shared NT8 state):
├── T18: E2E: trivial SMA indicator                        [unspecified-high] ← runs first
├── T19: E2E: error injection + recovery (depends: T18)    [unspecified-high] ← runs second (reuses TestSMA.cs)
├── T20: E2E: visual fail detection (depends: T19)         [unspecified-high] ← runs third
└── T21: README.md (parallel with T18-T20, no NT8 state)   [writing]

> **NOTE**: T18/T19/T20 MUST run sequentially — they share the same NT8 instance,
> chart state, and test indicator. Running in parallel would corrupt shared state.
> T21 (README) can run in parallel since it has no NT8 dependency.

Wave FINAL (4 parallel reviews, then user okay):
├── F1: Plan compliance audit                              [oracle]
├── F2: Code quality review                                [unspecified-high]
├── F3: Real manual QA execution                           [unspecified-high]
└── F4: Scope fidelity check                               [deep]
→ Present results → Get explicit user okay

Critical Path: T2 → T8 → T13 → T16 → T17 → T18 → T19 → T20 → F1-F4 → user okay
Parallel Speedup: ~55% faster than sequential
Max Concurrent: 7 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | — | T17 | 1 |
| T2 | — | T8, T9, T11, T14, T15, T16 | 1 |
| T3 | — | T10, T12 | 1 |
| T4 | — | T13 | 1 |
| T5 | — | T9, T14, T16 | 1 |
| T6 | — | T16 | 1 |
| T7 | — | T12 | 1 |
| T8 | T2 | T16 | 2 |
| T9 | T2, T5 | T16 | 2 |
| T10 | T3 | T13, T16 | 2 |
| T11 | T2 | T17 | 2 |
| T12 | T3, T7 | T17 | 2 |
| T13 | T4, T10 | T16 | 3 |
| T14 | T2, T5 | T17 | 3 |
| T15 | T2 | T17 | 3 |
| T16 | T5, T6, T8, T9, T10, T13 | T17 | 4 |
| T17 | T1-T16 | T18-T21 | 5 |
| T18 | T17 | T19 | 6 (sequential) |
| T19 | T18 | T20 | 6 (sequential) |
| T20 | T19 | F1-F4 | 6 (sequential) |
| T21 | T17 | F1-F4 | 6 (parallel w/ T18-T20) |
| F1-F4 | T18-T21 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **7 parallel** — T1 → `quick`, T2 → `quick`, T3 → `quick`, T4 → `writing`, T5 → `unspecified-high`, T6 → `quick`, T7 → `unspecified-high`
- **Wave 2**: **5 parallel** — T8 → `deep`, T9 → `quick`, T10 → `unspecified-high`, T11 → `quick`, T12 → `deep`
- **Wave 3**: **3 parallel** — T13 → `deep`, T14 → `deep`, T15 → `unspecified-high`
- **Wave 4**: **1 task** — T16 → `deep` (blocked by T13)
- **Wave 5**: **1 task** — T17 → `deep`
- **Wave 6**: **4 tasks** — T18 → T19 → T20 → `unspecified-high` (SEQUENTIAL, shared NT8 state) + T21 → `writing` (parallel)
- **FINAL**: **4 parallel** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

> Implementation + verification = ONE task. Never separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.
> **A task WITHOUT QA Scenarios is INCOMPLETE. No exceptions.**

- [ ] 1. Scaffold Directory + SKILL.md + knowledge.md

  **What to do**:
  - Create the full directory structure: `.claude/skills/nt8-build-verify/{scripts,lib,fixes}`
  - Write `SKILL.md` following the pattern from `.claude/skills/nt8-expert/SKILL.md` (24-46 lines). Trigger patterns MUST include: "NinjaTrader", "NT8", "NinjaScript", "indicator", "strategy", ".cs file", "compile", "install on chart", "build and verify", "put it on my chart", "deploy to NT8"
  - Write `knowledge.md` covering: verified NT8 paths (table format), compile strategies (3-tier: HTTP → headless → editor), fix loop workflow, chart installation workflow, visual verification workflow, artifact structure, configurable timeouts, guardrails G1-G11, error code reference (link to fixes/*.md)
  - SKILL.md entry point must reference `knowledge.md` for full details and `scripts/orchestrator.ps1` as the main pipeline script
  - All paths must be absolute: `C:\Users\Tea\DEEP6\.claude\skills\nt8-build-verify\...`

  **Must NOT do**:
  - Do NOT write any executable scripts yet — only .md files
  - Do NOT include implementation details in SKILL.md — keep it as trigger + entry point
  - Do NOT deviate from existing SKILL.md format (see nt8-expert/SKILL.md for template)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Provides the SKILL.md template pattern and verified NT8 paths

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3, T4, T5, T6, T7)
  - **Blocks**: T17 (orchestrator needs SKILL.md for self-documentation)
  - **Blocked By**: None (can start immediately)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-expert/SKILL.md` — SKILL.md template (24 lines: trigger description + entry point + workflow steps)
  - `.claude/skills/nt8-expert/knowledge.md` — knowledge.md template (verified paths table, deploy flow, data flow, compile detection)
  - `.claude/skills/nt8-fix/knowledge.md` — Error taxonomy format, escalation checklist pattern

  **Why Each Reference Matters**:
  - `nt8-expert/SKILL.md`: Copy exact structure — trigger section with natural language patterns, numbered workflow steps, "Load knowledge.md first" instruction
  - `nt8-expert/knowledge.md`: Copy path table format and workflow step structure. New knowledge.md adds compile strategies and visual verification not present in nt8-expert
  - `nt8-fix/knowledge.md`: Error taxonomy format is exactly what's needed for the fix loop section of knowledge.md

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Skill directory structure is complete
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: Test-Path ".claude/skills/nt8-build-verify/SKILL.md"
      2. Run: Test-Path ".claude/skills/nt8-build-verify/knowledge.md"
      3. Run: Test-Path ".claude/skills/nt8-build-verify/scripts"
      4. Run: Test-Path ".claude/skills/nt8-build-verify/lib"
      5. Run: Test-Path ".claude/skills/nt8-build-verify/fixes"
    Expected Result: All 5 return True
    Evidence: .sisyphus/evidence/task-1-directory-structure.txt

  Scenario: SKILL.md contains required trigger patterns
    Tool: Bash (PowerShell)
    Preconditions: SKILL.md exists
    Steps:
      1. Run: Select-String -Path ".claude/skills/nt8-build-verify/SKILL.md" -Pattern "NinjaTrader|NT8|NinjaScript|indicator|strategy|compile|chart"
      2. Assert at least 5 distinct trigger terms found
      3. Run: Select-String -Path ".claude/skills/nt8-build-verify/SKILL.md" -Pattern "knowledge.md"
      4. Assert knowledge.md reference exists
    Expected Result: All trigger terms present, knowledge.md referenced
    Evidence: .sisyphus/evidence/task-1-skill-triggers.txt

  Scenario: knowledge.md contains verified paths table
    Tool: Bash (PowerShell)
    Preconditions: knowledge.md exists
    Steps:
      1. Run: Select-String -Path ".claude/skills/nt8-build-verify/knowledge.md" -Pattern "C:\\Users\\Tea\\Documents\\NinjaTrader 8"
      2. Assert NT8 root path present
      3. Run: Select-String -Path ".claude/skills/nt8-build-verify/knowledge.md" -Pattern "compile_headless|compile_editor|DevAddon"
      4. Assert all three compile strategies documented
    Expected Result: Paths table and all compile strategies present
    Evidence: .sisyphus/evidence/task-1-knowledge-content.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/SKILL.md`, `.claude/skills/nt8-build-verify/knowledge.md`

- [ ] 2. lib/nt8_paths.py — Path Detection + Assumption Validation

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/lib/nt8_paths.py`
  - Implement `NT8Paths` class with these capabilities:
    - Auto-detect all NT8 paths: install dir, user data dir, Custom source, Custom DLL, runtime logs (`log\log.YYYYMMDD.*.txt`), workspaces, Install.xml
    - Validate each path exists via `os.path.exists()`
    - Check assumption A1: Does `NinjaScript.exe` exist at `C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe`?
    - Check assumption A2: Is DEEP6DevAddon alive? (`urllib.request` to `http://localhost:19206/health`)
    - Return structured JSON report of all paths + validation status
    - Determine available compile paths based on validations: `["devaddon_http", "ninjascript_exe", "editor_uia"]`
  - Add `__main__` block so `python nt8_paths.py` prints the JSON report
  - Use `os.environ.get("USERPROFILE")` for Windows user directory resolution
  - Handle the case where NT8 is NOT installed — return clear error message, not exception

  **Must NOT do**:
  - Do NOT hardcode paths without environment variable fallback
  - Do NOT import any third-party packages — stdlib only (os, json, pathlib, urllib)
  - Do NOT modify any detected paths or NT8 files

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3, T4, T5, T6, T7)
  - **Blocks**: T8, T9, T11, T14, T15, T16 (all scripts needing path resolution)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-expert/knowledge.md` lines containing "Verified paths" — The exact NT8 path values to detect: `C:\Users\Tea\Documents\NinjaTrader 8\`, `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll`, etc.
  - `ninjatrader/scripts/nt8-status.ps1` — PowerShell path detection logic to replicate in Python: `$nt8Root`, `$customDll`, `$installXml` variable definitions

  **API/Type References**:
  - `ninjatrader/scripts/nt8-dev-api.ps1` — HTTP API endpoint at `http://localhost:19206/health` for DevAddon health check

  **Why Each Reference Matters**:
  - `nt8-expert/knowledge.md`: Source of truth for all NT8 paths — copy exact values, don't guess
  - `nt8-status.ps1`: Shows how existing code discovers paths — replicate this logic in Python
  - `nt8-dev-api.ps1`: Shows the health check endpoint for DEEP6DevAddon — need same check in Python

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Path detection finds all NT8 directories
    Tool: Bash (PowerShell)
    Preconditions: NT8 installed on this machine
    Steps:
      1. Run: python ".claude/skills/nt8-build-verify/lib/nt8_paths.py"
      2. Parse JSON output
      3. Assert "nt8_root" value is "C:\Users\Tea\Documents\NinjaTrader 8"
      4. Assert "custom_dll" ends with "NinjaTrader.Custom.dll"
      5. Assert "repo_source" contains "DEEP6\ninjatrader\Custom"
      6. Assert "available_compile_paths" is a non-empty list
    Expected Result: JSON with all paths resolved, at least 1 compile path available
    Failure Indicators: JSON parse error, missing keys, empty available_compile_paths
    Evidence: .sisyphus/evidence/task-2-path-detection.json

  Scenario: Graceful handling when DevAddon is not running
    Tool: Bash (PowerShell)
    Preconditions: DEEP6DevAddon may or may not be loaded in NT8
    Steps:
      1. Run: python -c "import sys; sys.path.insert(0, '.claude/skills/nt8-build-verify'); from lib.nt8_paths import NT8Paths; p = NT8Paths(); print(p.devaddon_available)"
      2. Assert output is either "True" or "False" (no exception)
    Expected Result: Boolean result, no crash
    Failure Indicators: Uncaught exception, traceback
    Evidence: .sisyphus/evidence/task-2-devaddon-check.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/lib/nt8_paths.py`

- [ ] 3. lib/diagnostics.py — Shared Diagnostic Utilities

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/lib/__init__.py` (empty, enables Python imports)
  - Create `.claude/skills/nt8-build-verify/lib/diagnostics.py`
  - Implement shared data models and utilities:
    - `CompileError` dataclass: `code: str, message: str, file: str, line: int, col: int, severity: str` (severity: "error" vs "warning"). NOTE: field is `col` not `column` — matches nt8-errors-full.ps1 output format exactly.
    - `FixResult` dataclass: `error: CompileError, fix_applied: str, diff: str, success: bool, rollback_needed: bool`
    - `RunArtifacts` class: manages artifact directory creation (`./artifacts/<run-id>/`), provides methods `save_json(name, data)`, `save_text(name, text)`, `save_screenshot(name, path)`, `get_run_dir() -> Path`
    - `generate_run_id() -> str`: format `bv-{YYYYMMDD}-{HHMMSS}-{4hex}` (e.g., `bv-20260513-143022-a1b2`)
    - `parse_sentinel(line: str) -> dict`: parse `[COMPILE-RESULT] SUCCESS <timestamp>` or `[COMPILE-RESULT] FAILED <reason>` sentinel lines from nt8-compile.ps1
    - Timing context manager: `with Timer("compile") as t:` → records elapsed, writes to timing.json
  - Stdlib only: dataclasses, json, pathlib, datetime, time, uuid

  **Must NOT do**:
  - Do NOT import third-party packages
  - Do NOT create actual artifact directories during import — only on explicit `RunArtifacts()` instantiation

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T4, T5, T6, T7)
  - **Blocks**: T10, T12 (parse_errors.py and verify_visual.py import these models)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-compile.ps1` — Sentinel line format: `[COMPILE-RESULT] SUCCESS <timestamp>` or `[COMPILE-RESULT] FAILED <reason>` (search for "COMPILE-RESULT" in the file)
  - `ninjatrader/scripts/nt8-errors-full.ps1` — Error JSON output format: `{"file":"...","message":"...","code":"CS0246","line":42,"col":10}` — match this structure in CompileError. NOTE: field is `col` (not `column`).
  - `ninjatrader/scripts/nt8-ai-loop.ps1` — Exit code convention: 0=success, 1=errors, 2=infrastructure failure, 3=max iterations — replicate in Python

  **Why Each Reference Matters**:
  - `nt8-compile.ps1`: Sentinel format must be parsed exactly — `parse_sentinel()` must handle both SUCCESS and FAILED variants
  - `nt8-errors-full.ps1`: CompileError dataclass fields must match this JSON schema so parse_errors.py can deserialize directly
  - `nt8-ai-loop.ps1`: Exit code convention ensures consistency between PowerShell and Python components

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CompileError and FixResult are valid dataclasses
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: python -c "import sys; sys.path.insert(0, '.claude/skills/nt8-build-verify'); from lib.diagnostics import CompileError, FixResult; e = CompileError('CS0246','type not found','test.cs',42,10,'error'); print(e.code, e.severity)"
      2. Assert output: "CS0246 error"
    Expected Result: Dataclass instantiation works, fields accessible
    Evidence: .sisyphus/evidence/task-3-dataclasses.txt

  Scenario: RunArtifacts creates directory and saves JSON
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: python -c "import sys; sys.path.insert(0, '.claude/skills/nt8-build-verify'); from lib.diagnostics import RunArtifacts; r = RunArtifacts(); r.save_json('test', {'key':'value'}); print(r.get_run_dir())"
      2. Assert output contains "artifacts/bv-"
      3. Assert file exists: <run_dir>/test.json
    Expected Result: Directory created, JSON file saved
    Evidence: .sisyphus/evidence/task-3-artifacts.txt

  Scenario: Sentinel parsing handles both SUCCESS and FAILED
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: python -c "import sys; sys.path.insert(0, '.claude/skills/nt8-build-verify'); from lib.diagnostics import parse_sentinel; print(parse_sentinel('[COMPILE-RESULT] SUCCESS 2026-05-13T14:30:22'))"
      2. Assert result has status="SUCCESS"
      3. Run: python -c "import sys; sys.path.insert(0, '.claude/skills/nt8-build-verify'); from lib.diagnostics import parse_sentinel; print(parse_sentinel('[COMPILE-RESULT] FAILED timeout'))"
      4. Assert result has status="FAILED", reason="timeout"
    Expected Result: Both variants parsed correctly
    Evidence: .sisyphus/evidence/task-3-sentinel.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/lib/diagnostics.py`

- [ ] 4. Fix Recipes — 8 Error-Code Markdown Files

  **What to do**:
  - Create 8 `.md` files under `.claude/skills/nt8-build-verify/fixes/`:
  - Each file follows this structure:
    ```
    # CS0246 — Type or namespace not found
    ## Pattern: `error CS0246: The type or namespace name 'X' could not be found`
    ## Root Causes (ordered by likelihood):
    1. Missing `using` directive
    2. Namespace mismatch (Indicators vs Strategies)
    3. Type defined in uncompiled/excluded file
    ## Fix Strategies:
    ### Strategy 1: Add missing `using` directive
    - Detect: error message contains type name
    - Lookup: known NT8 namespace → type mapping table
    - Fix: insert `using NinjaTrader.NinjaScript.{namespace};` after last using
    - Verify: type name appears in the added namespace
    ### Strategy 2: Fix namespace prefix
    - Detect: type exists but in wrong namespace
    - Fix: change `Indicators.DEEP6` to `Strategies.DEEP6` or vice versa
    ## NT8-Specific Type→Namespace Map:
    | Type | Namespace |
    |------|-----------|
    | Indicator | NinjaTrader.NinjaScript.Indicators |
    | Strategy | NinjaTrader.NinjaScript.Strategies |
    | ...
    ## Example Fix (diff format):
    ```
  - **CS0103.md**: Missing member — check OnStateChange guard, scope, spelling, missing `using`
  - **CS0246.md**: Type not found — namespace mismatch, missing `using`, NT8 type→namespace map
  - **CS1061.md**: Missing method — SharpDX API drift, `Series<double>` vs `ISeries<double>`, base class methods
  - **CS0019.md**: Operator mismatch — bool-to-double, nullable unwrapping, cast insertion
  - **CS0101.md**: Duplicate type name — class name collision across files, namespace qualification
  - **CS0535.md**: Interface not implemented — missing abstract method overrides, list required members
  - **BRACE_MISMATCH.md**: Region/brace errors — count braces, detect `#region`/`#endregion` imbalance
  - **MISSING_ATTRIBUTE.md**: Missing `[Browsable(false)]`, `[XmlIgnore]`, `[NinjaScriptProperty]` on derived series properties

  **Must NOT do**:
  - Do NOT include fixes for error codes outside this set of 8
  - Do NOT include runtime error fixes — compile errors only
  - Do NOT make fix recipes executable code — they are reference documents for fix_router.py

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: [`nt8-expert`, `nt8-fix`]
    - `nt8-expert`: NT8 namespace conventions, NinjaScript API patterns
    - `nt8-fix`: Existing error taxonomy, known fix patterns, escalation rules

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T5, T6, T7)
  - **Blocks**: T13 (fix_router.py reads these recipes for dispatch logic)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-fix/knowledge.md` — Error taxonomy section with CS0234, CS0246, CS0111 fix patterns — replicate and expand this structure
  - `.claude/skills/nt8-architect/architecture.md` — Namespace map: `NinjaTrader.NinjaScript.Indicators.DEEP6`, `...Strategies.DEEP6`, `...AddOns.DEEP6` — use for type→namespace lookup tables
  - `ninjatrader/scripts/nt8-fix-loop.ps1` — Error hint lookup table (search for "hints" or "CS0246") — copy these known hints into fix recipes

  **External References**:
  - Microsoft Roslyn CS error codes: `https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/compiler-messages/`

  **Why Each Reference Matters**:
  - `nt8-fix/knowledge.md`: Existing fix patterns are BATTLE-TESTED — don't reinvent, expand them
  - `architecture.md`: Namespace map is essential for CS0246 fixes — which namespace contains which type
  - `nt8-fix-loop.ps1`: Error hints are the starting point — each hint becomes a full recipe

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 8 fix recipe files exist with required sections
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: Get-ChildItem ".claude/skills/nt8-build-verify/fixes/*.md" | Measure-Object | Select-Object -ExpandProperty Count
      2. Assert count is 8
      3. For each .md file, run: Select-String -Path $file -Pattern "## Pattern:|## Root Causes|## Fix Strategies|## Example Fix"
      4. Assert each file contains all 4 sections
    Expected Result: 8 files, each with Pattern, Root Causes, Fix Strategies, Example Fix sections
    Evidence: .sisyphus/evidence/task-4-fix-recipes.txt

  Scenario: CS0246.md contains NT8 type→namespace map
    Tool: Bash (PowerShell)
    Preconditions: CS0246.md exists
    Steps:
      1. Run: Select-String -Path ".claude/skills/nt8-build-verify/fixes/CS0246.md" -Pattern "NinjaTrader\.NinjaScript\.(Indicators|Strategies)"
      2. Assert both Indicators and Strategies namespaces are in the map
    Expected Result: Type→namespace mapping table present with NT8-specific types
    Evidence: .sisyphus/evidence/task-4-cs0246-map.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/fixes/*.md`

- [ ] 5. scripts/modal_detect.ps1 — Modal Dialog Detection + Dismissal

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/modal_detect.ps1`
  - Implement modal dialog detection for NT8 process:
    - Find all top-level windows belonging to NinjaTrader process
    - Detect unexpected windows (dialogs that block the main window): crash reports, update prompts, license dialogs, "Save Changes?" dialogs, error dialogs
    - For each detected modal:
      - Log its title, class, and automation ID to artifact
      - Attempt safe dismissal: send Escape key (safest), click Cancel if present, click No if "Save Changes?"
      - If dismissal fails, return `BLOCKED` status with dialog details
    - Return structured JSON: `{"modals_found": N, "modals_dismissed": N, "blocked": bool, "details": [...]}`
  - Use `System.Windows.Automation` (UIAutomation) consistent with existing scripts
  - Add `-WhatIf` switch to detect without dismissing
  - Use the same P/Invoke pattern from `nt8-ui.ps1` for `SetForegroundWindow` and `ShowWindow`
  - Configurable timeout for modal wait: `-TimeoutSeconds` parameter (default 5)

  **Must NOT do**:
  - Do NOT dismiss dialogs by clicking "OK" or "Yes" — only Escape, Cancel, No (safety first)
  - Do NOT interact with non-NT8 windows
  - Do NOT modify any NT8 state — only detect and dismiss blocking modals

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: UIAutomation patterns, P/Invoke definitions, window class names

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T4, T6, T7)
  - **Blocks**: T9, T14, T16 (all UIA-dependent scripts call modal_detect first)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-ui.ps1` lines 1-40 — P/Invoke definitions for `SetForegroundWindow`, `ShowWindow`, `GetForegroundWindow`. Copy these exactly for window management.
  - `ninjatrader/scripts/nt8-compile.ps1` lines 1-30 — UIAutomation assembly loading: `Add-Type -AssemblyName UIAutomationClient; Add-Type -AssemblyName UIAutomationTypes`. Use same pattern.
  - `ninjatrader/scripts/nt8-errors-full.ps1` — AutomationElement tree traversal pattern: `[System.Windows.Automation.AutomationElement]::RootElement`, `FindAll()` with `TreeScope.Children`. Replicate for modal window detection.

  **Why Each Reference Matters**:
  - `nt8-ui.ps1`: Proven P/Invoke signatures — don't rewrite, dot-source or copy
  - `nt8-compile.ps1`: UIAutomation bootstrap pattern — must be identical for consistency
  - `nt8-errors-full.ps1`: Tree traversal is exactly what's needed to enumerate NT8 child windows

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No modals detected when NT8 is idle
    Tool: Bash (PowerShell)
    Preconditions: NT8 is running with no dialogs open
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/modal_detect.ps1" -WhatIf
      2. Parse JSON output
      3. Assert modals_found == 0
      4. Assert blocked == false
    Expected Result: Clean detection, no modals found
    Failure Indicators: Non-zero modals_found when no dialogs are open, exception
    Evidence: .sisyphus/evidence/task-5-modal-clean.json

  Scenario: Graceful handling when NT8 is not running
    Tool: Bash (PowerShell)
    Preconditions: NT8 may or may not be running
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/modal_detect.ps1" -WhatIf 2>&1
      2. Assert exit code is 2 (infrastructure failure) if NT8 not running
      3. Assert error message mentions "NinjaTrader process not found"
    Expected Result: Exit code 2 with clear error message, no crash
    Evidence: .sisyphus/evidence/task-5-modal-no-nt8.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/scripts/modal_detect.ps1`

- [ ] 6. scripts/deploy.ps1 — Atomic Deploy Wrapper

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/deploy.ps1`
  - Wrapper around existing `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-deploy.ps1` with enhancements:
    - Accept `-SourceFile <path>` for single-file deploy (not full project deploy)
    - Implement atomic deploy: write to `*.tmp` in target directory, then `Move-Item -Force` to final path
    - Verify file integrity after move: compare hash of source vs deployed file
    - Detect target subdirectory from file content: parse `namespace NinjaTrader.NinjaScript.Indicators` → deploy to `Indicators/DEEP6/`, parse `Strategies` → deploy to `Strategies/DEEP6/`
    - Support `-DryRun` switch: show what would be deployed without doing it
    - Return JSON: `{"source": "...", "target": "...", "hash_match": true, "already_deployed": false}`
    - If file already deployed with same hash, skip and return `already_deployed: true` (idempotent)
  - Dot-source `nt8_paths.py` output for path resolution (run Python, parse JSON)

  **Must NOT do**:
  - Do NOT deploy FootprintBar.cs (exclusion list from nt8-deploy.ps1)
  - Do NOT trigger compilation — deploy only
  - Do NOT modify the source file

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Deploy patterns, exclusion list, Custom folder structure

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T4, T5, T7)
  - **Blocks**: T16 (fix_loop.ps1 calls deploy before compile)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — Full deployment script: hash-based sync (Get-FileHash), recursive copy, exclusion list (search for "FootprintBar"), colored console output. Dot-source this for the `-All` deploy mode.
  - `ninjatrader/scripts/nt8-status.ps1` — File sync detection pattern: `Get-FileHash` comparison between source and deployed copy

  **Why Each Reference Matters**:
  - `nt8-deploy.ps1`: The proven deployment logic — this wrapper adds atomic moves and single-file support on top
  - `nt8-status.ps1`: Hash comparison pattern to detect if file is already deployed identically

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: DryRun shows deployment plan without executing
    Tool: Bash (PowerShell)
    Preconditions: A .cs file exists in the repo
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/deploy.ps1" -SourceFile "ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs" -DryRun
      2. Parse JSON output
      3. Assert "source" contains "DEEP6Signal.cs"
      4. Assert "target" contains "Indicators\DEEP6"
      5. Verify the file was NOT actually copied (target not modified)
    Expected Result: JSON with source/target, no actual file operations
    Evidence: .sisyphus/evidence/task-6-deploy-dryrun.json

  Scenario: Idempotent — second deploy is no-op
    Tool: Bash (PowerShell)
    Preconditions: File already deployed with matching hash
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/deploy.ps1" -SourceFile "ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs"
      2. Run same command again
      3. Parse second run's JSON
      4. Assert "already_deployed" == true
    Expected Result: Second run detects no changes needed
    Evidence: .sisyphus/evidence/task-6-deploy-idempotent.json
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/scripts/deploy.ps1`

- [ ] 7. scripts/screenshot_chart.ps1 — Targeted Window Capture

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/screenshot_chart.ps1`
  - Enhance existing `nt8-ui.ps1 -Action Screenshot` (which captures full primary screen) with targeted chart window capture:
    - Find the NT8 chart window by title substring (e.g., "NQ 03-26" or chart name)
    - Use `PrintWindow` Win32 API to capture the specific window (works even if partially occluded or on secondary monitor)
    - Fallback to `Graphics.CopyFromScreen()` with window rect if `PrintWindow` fails
    - Accept `-ChartTitle <string>` to target specific chart, or `-MainWindow` for the primary NT8 window
    - Accept `-OutputPath <path>` for save location (default: `./artifacts/<run-id>/screenshot-{HHMMSS}.png`)
    - Wait `-SettleMs <int>` before capture (default: 1500) to let rendering complete
    - Perform non-blank check: compute pixel variance — if < threshold, emit warning "screenshot may be blank"
    - Return JSON: `{"path": "...", "width": N, "height": N, "blank_check": "pass|warn", "capture_method": "printwindow|copyfromscreen"}`
  - Add P/Invoke for `PrintWindow` from user32.dll

  **Must NOT do**:
  - Do NOT perform OCR or visual analysis — that's verify_visual.py's job
  - Do NOT modify chart state or window position

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Window management patterns, P/Invoke signatures, display topology

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2, T3, T4, T5, T6)
  - **Blocks**: T12 (verify_visual.py consumes screenshots)
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-ui.ps1` — Screenshot action (search for "Screenshot" or "System.Drawing"): `Graphics.CopyFromScreen()`, `Bitmap`, `ImageFormat.Png`. This is the fallback approach; new script adds `PrintWindow` for targeted capture.
  - `ninjatrader/scripts/nt8-ui.ps1` — P/Invoke block: `[DllImport("user32.dll")]` signatures for `SetForegroundWindow`, `ShowWindow`, `GetForegroundWindow`. Add `PrintWindow` to this set.

  **External References**:
  - Win32 PrintWindow API: `https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-printwindow`

  **Why Each Reference Matters**:
  - `nt8-ui.ps1 Screenshot`: Existing capture code is the fallback. New script supersedes it with window-targeted capture.
  - `nt8-ui.ps1 P/Invoke`: Copy exact P/Invoke pattern, add `PrintWindow` signature

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Capture NT8 main window screenshot
    Tool: Bash (PowerShell)
    Preconditions: NT8 is running
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/screenshot_chart.ps1" -MainWindow -OutputPath "C:\Users\Tea\AppData\Local\Temp\opencode\test-screenshot.png"
      2. Parse JSON output
      3. Assert path exists and file size > 0
      4. Assert width > 100 and height > 100
      5. Assert blank_check is "pass"
    Expected Result: PNG file saved, non-blank, valid dimensions
    Failure Indicators: File size 0, blank_check "warn", exception
    Evidence: .sisyphus/evidence/task-7-screenshot.png

  Scenario: Graceful handling when chart title not found
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, no chart with title "NONEXISTENT"
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/screenshot_chart.ps1" -ChartTitle "NONEXISTENT" 2>&1
      2. Assert exit code is 1
      3. Assert error message mentions "chart not found"
    Expected Result: Clean error, no crash, exit code 1
    Evidence: .sisyphus/evidence/task-7-screenshot-notfound.txt
  ```

  **Commit**: YES (groups with Wave 1)
  - Message: `feat(skill): scaffold nt8-build-verify with foundation layer`
  - Files: `.claude/skills/nt8-build-verify/scripts/screenshot_chart.ps1`

- [ ] 8. scripts/compile_headless.ps1 — Path A: Headless Compilation

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/compile_headless.ps1`
  - Implement headless compilation with three sub-paths (tried in order):
    1. **DEEP6DevAddon HTTP**: `Invoke-RestMethod http://localhost:19206/compile -Method POST` — fastest, no UIA, IN-PROCESS compile (types are registered immediately since compile happens inside live NT8). Check DevAddon health first. NOTE: This is NOT truly headless — it triggers compilation within the running NT8 process, which means types ARE registered and a separate Editor F5 reload is NOT needed after this path succeeds.
    2. **NinjaScript.exe**: `& "C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe" /compile` — headless CLI. Check file exists first.
    3. **MSBuild**: `msbuild NinjaTrader.Custom.csproj /t:Build /p:Configuration=Release` — locate .csproj in Custom folder. Fallback only.
  - For each sub-path:
    - Capture stdout/stderr
    - Parse compile result: success vs failure
    - Extract error list (for sub-paths 2 and 3: parse Roslyn output; for sub-path 1: parse HTTP response JSON)
    - Emit `[COMPILE-RESULT] SUCCESS <timestamp>` or `[COMPILE-RESULT] FAILED <error_count>` sentinel
  - Parameters: `-TimeoutSeconds` (default 60), `-PreferredPath` (override auto-detection), `-DryRun`
  - After successful compile via NinjaScript.exe or MSBuild, DLL is updated but NT8 hasn't reloaded — caller must trigger Editor F5 for registration. NOTE: DevAddon HTTP compile is IN-PROCESS and DOES register types — no F5 needed after DevAddon success.
  - Return JSON: `{"path_used": "devaddon|ninjascript_exe|msbuild", "success": bool, "error_count": N, "errors": [...], "elapsed_ms": N}`

  **Must NOT do**:
  - Do NOT trigger NT8 reload — that's compile_editor.ps1's job
  - Do NOT modify source files
  - Do NOT attempt compilation if NT8 Custom folder doesn't exist

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NinjaScript.exe location, Custom folder structure, DevAddon HTTP API

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T9, T10, T11, T12)
  - **Blocks**: T16 (fix_loop.ps1 uses this for fast iteration)
  - **Blocked By**: T2 (nt8_paths.py for path resolution)

  **References**:

  **Pattern References**:
  - `ninjatrader/deploy/auto-deploy.ps1` — NinjaScript.exe /compile invocation pattern. Search for "NinjaScript.exe" — shows how to invoke headless compile and check result.
  - `ninjatrader/scripts/nt8-dev-api.ps1` — DevAddon HTTP compile: `Invoke-RestMethod http://localhost:19206/compile`. Search for "compile" action — shows request format and response parsing.
  - `DEEP6.csproj` — MSBuild project file: net48 target, NT8 assembly references. Shows the target framework and references needed for msbuild invocation.

  **API/Type References**:
  - `ninjatrader/scripts/nt8-compile.ps1` — `[COMPILE-RESULT]` sentinel format: lines 250-280. Emit same format for consistency with other scripts.

  **Why Each Reference Matters**:
  - `auto-deploy.ps1`: Only existing NinjaScript.exe invocation — must replicate its argument format
  - `nt8-dev-api.ps1`: HTTP compile is the fastest path — must handle its specific response format
  - `DEEP6.csproj`: MSBuild needs correct target framework and references
  - `nt8-compile.ps1`: Sentinel format must match for downstream parsing by diagnostics.py

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Headless compile succeeds with available path
    Tool: Bash (PowerShell)
    Preconditions: NT8 installed, at least one compile path available
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/compile_headless.ps1" -TimeoutSeconds 60
      2. Parse JSON output
      3. Assert "path_used" is one of: devaddon, ninjascript_exe, msbuild
      4. Assert output contains "[COMPILE-RESULT]" sentinel
      5. If success: assert error_count == 0
    Expected Result: Compilation completes, sentinel emitted, path identified
    Failure Indicators: No sentinel line, timeout, JSON parse error
    Evidence: .sisyphus/evidence/task-8-compile-headless.json

  Scenario: DryRun reports available paths without compiling
    Tool: Bash (PowerShell)
    Preconditions: NT8 installed
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/compile_headless.ps1" -DryRun
      2. Parse JSON output
      3. Assert "available_paths" is a list with at least 1 entry
      4. Verify no DLL timestamp change occurred
    Expected Result: Path enumeration without compilation
    Evidence: .sisyphus/evidence/task-8-compile-dryrun.json
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(skill): add compile infrastructure and error parsing`
  - Files: `.claude/skills/nt8-build-verify/scripts/compile_headless.ps1`

- [ ] 9. scripts/compile_editor.ps1 — Path B: UIAutomation Editor Compile

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/compile_editor.ps1`
  - Wrapper around existing `C:\Users\Tea\DEEP6\ninjatrader\scripts\nt8-compile.ps1` with enhancements:
    - Call `modal_detect.ps1` FIRST — dismiss any blocking dialogs before UIA
    - Dot-source or invoke `nt8-compile.ps1` with `-TimeoutSeconds` parameter
    - After compile, call `nt8-errors-full.ps1` to read error list from DataGrid
    - Combine compile result + error list into unified JSON output
    - Emit `[COMPILE-RESULT]` sentinel consistent with compile_headless.ps1
    - This path is AUTHORITATIVE — it registers types with the live NT8 process for chart use
    - Also serves as DLL reload: even with no source changes, F5 forces NT8 to reload Custom.dll
    - Supports `-AutoReload` mode from nt8-compile.ps1: relies on NSE file-watcher instead of manual F5 SendKeys (NSE must be open)
  - Parameters: `-TimeoutSeconds` (default 60), `-AutoReload` (use file-watcher instead of F5 SendKeys)
  - Return JSON: `{"success": bool, "error_count": N, "errors": [...], "dll_reloaded": bool, "elapsed_ms": N}`

  **Must NOT do**:
  - Do NOT proceed if modal_detect returns BLOCKED — exit with code 2
  - Do NOT modify source files
  - Do NOT dismiss compile error dialogs with "OK" — capture them

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: nt8-compile.ps1 usage, UIAutomation patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T10, T11, T12)
  - **Blocks**: T16 (fix_loop uses this for final registration after clean headless compile)
  - **Blocked By**: T2 (paths), T5 (modal detect)

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-compile.ps1` — Full compile-via-editor script: UIAutomation NSE open, F5 trigger, DLL mtime polling, Install.xml parsing, `[COMPILE-RESULT]` sentinel. Dot-source this entire script.
  - `ninjatrader/scripts/nt8-errors-full.ps1` — DataGrid error reader: UIAutomation tree walk, cell extraction, JSON output. Call this after compile to get error list.

  **Why Each Reference Matters**:
  - `nt8-compile.ps1`: This IS the compile logic — wrapper adds modal detection and error collection
  - `nt8-errors-full.ps1`: Error scraping must happen immediately after compile while DataGrid is populated

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Editor compile triggers F5 and detects result
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, NinjaScript Editor accessible
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/compile_editor.ps1" -TimeoutSeconds 60
      2. Parse JSON output
      3. Assert "dll_reloaded" is true (DLL timestamp changed)
      4. Assert output contains "[COMPILE-RESULT]" sentinel
    Expected Result: Compile triggered, DLL reloaded, result detected
    Evidence: .sisyphus/evidence/task-9-compile-editor.json

  Scenario: AutoReload mode uses file-watcher for DLL refresh
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, NinjaScript Editor open, Custom.dll exists
    Steps:
      1. Record DLL timestamp before
      2. Run: powershell ".claude/skills/nt8-build-verify/scripts/compile_editor.ps1" -AutoReload -TimeoutSeconds 30
      3. Assert dll_reloaded is true
      4. Assert no F5 SendKeys were sent (file-watcher triggered compile)
    Expected Result: DLL reload via file-watcher without manual F5
    Evidence: .sisyphus/evidence/task-9-autoreload.json
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(skill): add compile infrastructure and error parsing`
  - Files: `.claude/skills/nt8-build-verify/scripts/compile_editor.ps1`

- [ ] 10. scripts/parse_errors.py — Structured Error Enrichment

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/parse_errors.py`
  - Parse error JSON from `nt8-errors-full.ps1` output and enrich with fix metadata:
    - Accept JSON input (stdin or file path argument)
    - Deserialize into `CompileError` dataclass list (from `lib/diagnostics.py`)
    - **Filter**: Separate errors (CS####) from warnings (CS0168, CS0219, etc.) — warnings do NOT enter fix loop
    - **Enrich**: For each error, look up fix recipe file (`fixes/{code}.md`) and attach fix strategy summary
    - **Prioritize**: Sort errors by fixability — errors with known fix recipes first, unknown errors last
    - **Detect cascades**: If multiple errors reference the same type/namespace, flag as "cascade group" — fixing root cause may resolve all
    - Output enriched JSON: `{"errors": [...], "warnings": [...], "fixable_count": N, "unfixable_count": N, "cascade_groups": [...]}`
  - Import from `lib.diagnostics`: `CompileError` dataclass
  - Add `--test` flag that runs with sample error data to verify parsing

  **Must NOT do**:
  - Do NOT attempt to fix errors — only parse and enrich
  - Do NOT import third-party packages — stdlib + lib/diagnostics.py only
  - Do NOT treat warnings as errors

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T11, T12)
  - **Blocks**: T13 (fix_router.py consumes enriched error output), T16 (fix_loop uses this)
  - **Blocked By**: T3 (lib/diagnostics.py for CompileError dataclass)

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-errors-full.ps1` — JSON output format: `[{"file":"DEEP6Signal.cs","message":"The type or namespace name 'X' could not be found","code":"CS0246","line":42,"col":10}]`. This is the INPUT format parse_errors.py must handle. NOTE: field is `col` not `column`.
  - `.claude/skills/nt8-build-verify/lib/diagnostics.py` (T3) — `CompileError` dataclass with `severity` field for error vs warning distinction

  **Why Each Reference Matters**:
  - `nt8-errors-full.ps1`: Defines the exact JSON schema that parse_errors.py must consume — field names must match
  - `diagnostics.py`: CompileError is the shared data model — parse_errors.py is the primary producer

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Parse sample error JSON correctly
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: echo '[{"file":"test.cs","message":"type not found","code":"CS0246","line":10,"col":5}]' | python ".claude/skills/nt8-build-verify/scripts/parse_errors.py"
      2. Parse output JSON
      3. Assert errors list has 1 entry with code "CS0246"
      4. Assert fixable_count == 1 (CS0246 has a fix recipe)
      5. Assert warnings list is empty
    Expected Result: Error parsed, enriched with fix strategy, categorized correctly
    Evidence: .sisyphus/evidence/task-10-parse-errors.json

  Scenario: Warnings separated from errors
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Run: echo '[{"file":"a.cs","message":"type not found","code":"CS0246","line":1,"col":1},{"file":"b.cs","message":"unused var","code":"CS0168","line":5,"col":1}]' | python ".claude/skills/nt8-build-verify/scripts/parse_errors.py"
      2. Assert errors list has 1 entry (CS0246)
      3. Assert warnings list has 1 entry (CS0168)
    Expected Result: CS0168 classified as warning, not sent to fix loop
    Evidence: .sisyphus/evidence/task-10-warnings.json
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(skill): add compile infrastructure and error parsing`
  - Files: `.claude/skills/nt8-build-verify/scripts/parse_errors.py`

- [ ] 11. scripts/runtime_check.ps1 — Post-Install Runtime Error Detection

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/runtime_check.ps1`
  - After an indicator is installed on a chart, check for runtime exceptions:
    - Read NT8 runtime log: `C:\Users\Tea\Documents\NinjaTrader 8\log\log.YYYYMMDD.NNNNN.txt` (find latest matching today's date)
    - Grep for exceptions matching the indicator class name within a configurable time window
    - Look for patterns: `OnBarUpdate`, `OnStateChange`, `System.NullReferenceException`, `System.IndexOutOfRangeException` associated with the class name
    - Also check NT8 Output Window via `nt8-errors.ps1` for runtime error messages
    - Parameters: `-ClassName <string>`, `-WindowSeconds <int>` (default 10), `-LogFile <path>` (auto-detect from today's date)
    - Return JSON: `{"runtime_errors_found": N, "errors": [{"timestamp": "...", "exception": "...", "stacktrace": "..."}], "check_window_seconds": N}`
  - If no errors found within window, return `runtime_errors_found: 0` — indicator is running cleanly

  **Must NOT do**:
  - Do NOT modify the log file
  - Do NOT attempt to fix runtime errors — only detect and report
  - Do NOT read the entire log file — tail only the relevant time window

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Trace log location, log format, common exception patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T10, T12)
  - **Blocks**: T17 (orchestrator calls this after chart installation)
  - **Blocked By**: T2 (nt8_paths.py for trace log location)

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-errors.ps1` — Log tailing pattern: search for "log" — shows how to find and tail the NT8 log file. Also shows Output Window reading via UIAutomation as secondary source.
  - Verified log path: `C:\Users\Tea\Documents\NinjaTrader 8\log\log.YYYYMMDD.NNNNN.txt` (confirmed on this machine — NOT `trace/` directory)

  **Why Each Reference Matters**:
  - `nt8-errors.ps1`: Proven log tailing logic — reuse the file discovery and tail approach
  - Verified log path: Correct filename pattern is `log.YYYYMMDD.NNNNN.txt` in `log/` directory (not `trace/`)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No runtime errors for healthy indicator
    Tool: Bash (PowerShell)
    Preconditions: NT8 running with indicators loaded
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/runtime_check.ps1" -ClassName "DEEP6Signal" -WindowSeconds 5
      2. Parse JSON output
      3. Assert runtime_errors_found >= 0 (no crash)
    Expected Result: Clean check completes, returns count
    Evidence: .sisyphus/evidence/task-11-runtime-clean.json

  Scenario: Graceful when runtime log doesn't exist yet
    Tool: Bash (PowerShell)
    Preconditions: None (log may not exist for today)
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/runtime_check.ps1" -ClassName "FakeIndicator" -WindowSeconds 1
      2. Assert exit code 0 (not error)
      3. Assert output indicates "log not found" or runtime_errors_found == 0
    Expected Result: Graceful handling, no crash
    Evidence: .sisyphus/evidence/task-11-runtime-nolog.json
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(skill): add compile infrastructure and error parsing`
  - Files: `.claude/skills/nt8-build-verify/scripts/runtime_check.ps1`

- [ ] 12. scripts/verify_visual.py — LLM Vision Verification + Auto-Checks

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/verify_visual.py`
  - Two-phase visual verification:
    - **Phase 1 — Auto-checks** (no LLM needed):
      - Pixel variance check: load screenshot with Pillow, compute standard deviation of pixel values. If stddev < threshold (e.g., 5.0), flag as "likely blank"
      - Legend check: use UIAutomation (via subprocess call to a helper PS script) OR pattern match on the screenshot for indicator name text
      - File size check: screenshot < 10KB is suspicious
    - **Phase 2 — LLM Vision** (requires screenshot + spec):
      - Accept `-ScreenshotPath`, `-SpecDescription` (text describing expected appearance)
      - Read the screenshot file, encode as base64
      - Call Claude API (anthropic SDK) with vision: send screenshot + spec → ask for PASS / PASS_WITH_NOTES / FAIL with reasons
      - Parse response, extract verdict and notes
  - Final verdict logic:
    - If auto-checks fail (blank/no-legend) → FAIL without LLM call
    - If LLM says PASS → PASS
    - If LLM says PASS_WITH_NOTES → PASS_WITH_NOTES (include notes)
    - If LLM says FAIL → FAIL (include reasons for fix loop)
  - MAX 2 LLM vision attempts (guardrail G5)
  - Save verdict to `verdict-{HHMMSS}.json`: `{"verdict": "PASS|PASS_WITH_NOTES|FAIL", "auto_checks": {...}, "llm_response": "...", "attempt": N}`
  - Parameters: `--screenshot <path>`, `--spec <text>`, `--artifacts-dir <path>`, `--skip-llm` (auto-checks only)

  **Must NOT do**:
  - Do NOT modify the screenshot file
  - Do NOT make more than 2 LLM vision calls per run
  - Do NOT hardcode API keys — use `ANTHROPIC_API_KEY` env var
  - Do NOT crash if anthropic SDK is not installed — fall back to auto-checks only with warning

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with T8, T9, T10, T11)
  - **Blocks**: T17 (orchestrator calls this as final verification step)
  - **Blocked By**: T3 (diagnostics.py for RunArtifacts), T7 (screenshot_chart.ps1 provides screenshots)

  **References**:

  **Pattern References**:
  - `pyproject.toml` — `anthropic>=0.34` in optional dependencies (copilot group). Verify SDK is available.

  **External References**:
  - Anthropic Vision API: `https://docs.anthropic.com/en/docs/build-with-claude/vision` — how to send images to Claude for analysis

  **Why Each Reference Matters**:
  - `pyproject.toml`: Confirms anthropic SDK is a declared dependency — can import it
  - Anthropic Vision docs: Exact API format for sending base64 images with text prompts

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Auto-checks detect blank screenshot
    Tool: Bash (PowerShell)
    Preconditions: Create a 100x100 white PNG test image
    Steps:
      1. Create test image: python -c "from PIL import Image; Image.new('RGB',(100,100),(255,255,255)).save('C:/Users/Tea/AppData/Local/Temp/opencode/blank.png')"
      2. Run: python ".claude/skills/nt8-build-verify/scripts/verify_visual.py" --screenshot "C:/Users/Tea/AppData/Local/Temp/opencode/blank.png" --spec "Blue SMA line on chart" --skip-llm --artifacts-dir "C:/Users/Tea/AppData/Local/Temp/opencode/test-artifacts"
      3. Parse verdict.json
      4. Assert verdict is "FAIL"
      5. Assert auto_checks.blank_check is "fail"
    Expected Result: Blank screenshot detected as FAIL without LLM call
    Evidence: .sisyphus/evidence/task-12-blank-detect.json

  Scenario: Skip-LLM mode works without anthropic SDK
    Tool: Bash (PowerShell)
    Preconditions: Any non-blank screenshot available
    Steps:
      1. Run: python ".claude/skills/nt8-build-verify/scripts/verify_visual.py" --screenshot "<valid_screenshot>" --spec "Any indicator" --skip-llm --artifacts-dir "C:/Users/Tea/AppData/Local/Temp/opencode/test-artifacts2"
      2. Assert exit code 0
      3. Assert verdict.json exists with auto_checks results
    Expected Result: Completes without LLM, reports auto-check results only
    Evidence: .sisyphus/evidence/task-12-skip-llm.json
  ```

  **Commit**: YES (groups with Wave 2)
  - Message: `feat(skill): add compile infrastructure and error parsing`
  - Files: `.claude/skills/nt8-build-verify/scripts/verify_visual.py`

- [ ] 13. scripts/fix_router.py — Error Code Fix Dispatcher + Rollback

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/fix_router.py`
  - Core fix dispatch logic:
    - Accept enriched error JSON from `parse_errors.py` (stdin or file path)
    - For each fixable error, load the corresponding fix recipe from `fixes/{code}.md`
    - Apply fix strategy in order of likelihood (Strategy 1 first, then Strategy 2, etc.)
    - **Fix implementation for each error code**:
      - **CS0246**: Parse error message for missing type name → lookup in NT8 type→namespace map → insert `using` directive after last existing `using` line
      - **CS0103**: Parse for member name → check if it's a scope issue (add `this.`) or missing `using`
      - **CS1061**: Parse for method name + type → check base class API (Series vs ISeries), suggest correct method
      - **CS0019**: Parse operator and types → insert explicit cast or nullable unwrap (`.Value`)
      - **CS0101**: Detect duplicate class name → suggest namespace qualification or rename
      - **CS0535**: Parse interface name → list required members from base class → emit NEEDS_HUMAN (too complex for pattern matching)
      - **BRACE_MISMATCH**: Count `{` vs `}`, count `#region` vs `#endregion` → identify mismatch location
      - **MISSING_ATTRIBUTE**: Detect property patterns on `Series<T>` → add `[Browsable(false)]` + `[XmlIgnore]`
    - **No rollback in fix_router**: fix_router applies fixes and reports what it did. It does NOT recompile or check error counts — that's fix_loop.ps1's job (T16). fix_router is a pure transform: errors in → fixes out.
    - **Surgical fixes**: Each fix modifies ONLY the specific line(s) needed. Generate unified diff for audit trail.
    - Emit fix report JSON: `{"fixes_applied": N, "fixes_failed": N, "unfixable": [...], "diffs": [...]}`
  - Parameters: `--errors <json_file>`, `--source-dir <path>`, `--dry-run` (show fixes without applying), `--test` (run with sample data)

  **Must NOT do**:
  - G1: Fixes modify ONLY the file containing the error — never adjacent files
  - G2: If fix requires semantic understanding, emit NEEDS_HUMAN and stop for that error
  - G7: Only handle locked error code set — unknown codes → UNFIXABLE
  - G8: Never fix by removing/commenting out code
  - Do NOT rewrite files wholesale — surgical line edits only
  - Do NOT import third-party packages

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-fix`, `nt8-expert`]
    - `nt8-fix`: Error taxonomy, fix patterns, escalation rules
    - `nt8-expert`: NT8 namespace conventions, NinjaScript API patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T14, T15, T16)
  - **Blocks**: T16 (fix_loop.ps1 calls this for each iteration)
  - **Blocked By**: T4 (fix recipes must exist), T10 (parse_errors.py for enriched input format)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-build-verify/fixes/*.md` (T4) — Fix recipe files: each contains Pattern, Root Causes, Fix Strategies with concrete steps, Example Fix in diff format. fix_router.py reads these for dispatch logic.
  - `.claude/skills/nt8-fix/knowledge.md` — Error taxonomy section: existing fix patterns for CS0234, CS0246, CS0111. Search for "Error taxonomy" — copy proven patterns.
  - `.claude/skills/nt8-architect/architecture.md` — Namespace map: `NinjaTrader.NinjaScript.Indicators.DEEP6`, `...Strategies.DEEP6`. Search for "namespace" — needed for CS0246 type→namespace resolution.
  - `ninjatrader/scripts/nt8-fix-loop.ps1` — Error hint table: search for "hint" or "CS0246" — these are the starting patterns for each fix strategy.

  **Why Each Reference Matters**:
  - Fix recipes (T4): The authoritative fix strategies — fix_router implements what recipes describe
  - `nt8-fix/knowledge.md`: Battle-tested patterns from real compile failures — don't reinvent
  - `architecture.md`: Namespace map is the lookup table for CS0246 fixes — which type lives where
  - `nt8-fix-loop.ps1`: Error hints are the seed data for fix dispatch

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CS0246 fix adds correct using directive
    Tool: Bash (PowerShell)
    Preconditions: Create a test .cs file missing a using directive
    Steps:
      1. Create test file with `NinjaTrader.NinjaScript.Indicators.Indicator` reference but no `using NinjaTrader.NinjaScript.Indicators;`
      2. Create error JSON: [{"file":"test.cs","message":"The type or namespace name 'Indicator' could not be found","code":"CS0246","line":10,"col":5}]
      3. Run: python fix_router.py --errors errors.json --source-dir <test_dir>
      4. Assert fixes_applied == 1
      5. Assert diff shows `+using NinjaTrader.NinjaScript.Indicators;`
    Expected Result: Using directive added, diff generated
    Evidence: .sisyphus/evidence/task-13-cs0246-fix.json

  Scenario: DryRun shows proposed fix without applying
    Tool: Bash (PowerShell)
    Preconditions: Test file with CS0246 error
    Steps:
      1. Create error JSON for CS0246
      2. Run: python fix_router.py --errors errors.json --source-dir <test_dir> --dry-run
      3. Assert fixes_applied == 0 (dry run)
      4. Assert diffs list shows proposed changes
      5. Assert source file is unchanged
    Expected Result: Fix proposed but not applied, diff preview generated
    Evidence: .sisyphus/evidence/task-13-dryrun.json

  Scenario: Unknown error code returns UNFIXABLE
    Tool: Bash (PowerShell)
    Preconditions: None
    Steps:
      1. Create error JSON with code "CS9999" (unknown)
      2. Run: python fix_router.py --errors errors.json --source-dir <test_dir>
      3. Assert unfixable list contains CS9999
      4. Assert fixes_applied == 0
    Expected Result: Unknown code not attempted, marked unfixable
    Evidence: .sisyphus/evidence/task-13-unknown-code.json
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(skill): add fix loop, chart installation, and workspace mutation`
  - Files: `.claude/skills/nt8-build-verify/scripts/fix_router.py`

- [ ] 14. scripts/install_indicator.ps1 — Path X: UIA Chart Installation

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/install_indicator.ps1`
  - Implement chart installation via UIAutomation through the Indicators dialog:
    1. Call `modal_detect.ps1` first — abort if BLOCKED
    2. Bring target chart window to foreground
    3. Send Ctrl+I to open Indicators dialog
    4. Wait for dialog to appear (UIAutomation: find window with title containing "Indicators")
    5. Find the search/filter text box in the dialog
    6. Type the indicator class name (e.g., "DEEP6Signal")
    7. Wait for list to filter
    8. Find the indicator in the list (by AutomationElement name match)
    9. Double-click to add it to the active indicators panel
    10. If parameters specified: find parameter inputs in right panel, set values
    11. Click OK/Apply to close dialog
    12. Wait `-SettleMs` for rendering
    13. Verify indicator appears in chart legend (UIAutomation read of chart header/legend area)
  - Parameters: `-ClassName <string>`, `-ChartTitle <string>` (chart to target), `-Parameters <hashtable>` (optional input overrides), `-Panel <string>` ("price" or "sub"), `-SettleMs <int>` (default 1500)
  - Return JSON: `{"installed": bool, "chart": "...", "class_name": "...", "legend_verified": bool, "elapsed_ms": N}`
  - **Idempotency**: Before adding, check if indicator already on chart (search active indicators list in dialog). If present, skip and return `already_installed: true`.
  - **UIA Tree Discovery**: This is NEW automation — no existing script does this. Agent must use UIAutomation Spy (or tree dump) to discover the exact control hierarchy of the Indicators dialog. Include discovery steps in the script as comments for future maintenance.

  **Must NOT do**:
  - G9: Do NOT enable strategies, configure parameters beyond specified, or change NT8 settings
  - G10: Do NOT install multiple indicators in one run
  - Do NOT proceed if modal_detect returns BLOCKED
  - Do NOT modify the indicator code or properties beyond specified parameters

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 UI layout, Indicators dialog, UIAutomation patterns

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T13, T15, T16)
  - **Blocks**: T17 (orchestrator calls this to install on chart)
  - **Blocked By**: T2 (paths), T5 (modal detect)

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-ui.ps1` — AddIndicator action (search for "AddIndicator"): currently sends Shift+F10 and prints instructions. This is the STARTING POINT — new script replaces manual steps with full UIA automation.
  - `ninjatrader/scripts/nt8-compile.ps1` — UIAutomation patterns: MenuItem invocation, window finding by process ID, `TreeScope.Children` enumeration. Copy these patterns for dialog interaction.
  - `ninjatrader/scripts/nt8-errors-full.ps1` — DataGrid/ListBox enumeration via UIAutomation: `AutomationElement.FindAll()` with specific control type conditions. Use same pattern for indicator list in the dialog.

  **Why Each Reference Matters**:
  - `nt8-ui.ps1 AddIndicator`: Shows current manual approach — new script automates what this documents
  - `nt8-compile.ps1`: UIAutomation bootstrap and window finding is identical — reuse patterns
  - `nt8-errors-full.ps1`: Control enumeration pattern needed for finding indicators in the list

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Install a built-in indicator via UIA
    Tool: Bash (PowerShell)
    Preconditions: NT8 running with a chart open
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/install_indicator.ps1" -ClassName "SMA" -ChartTitle "NQ" -Panel "price"
      2. Parse JSON output
      3. Assert installed == true
      4. Assert legend_verified == true (SMA appears in chart legend)
    Expected Result: SMA indicator added to chart, visible in legend
    Failure Indicators: installed false, dialog not found, timeout
    Evidence: .sisyphus/evidence/task-14-install-sma.json

  Scenario: Idempotent — second install is no-op
    Tool: Bash (PowerShell)
    Preconditions: SMA already installed on chart from previous scenario
    Steps:
      1. Run same command again
      2. Assert already_installed == true
      3. Assert no duplicate SMA in chart legend
    Expected Result: Detects existing indicator, skips installation
    Evidence: .sisyphus/evidence/task-14-install-idempotent.json
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(skill): add fix loop, chart installation, and workspace mutation`
  - Files: `.claude/skills/nt8-build-verify/scripts/install_indicator.ps1`

- [ ] 15. scripts/workspace_mutator.py — Path Y: Workspace XML Mutation (Fallback)

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/workspace_mutator.py`
  - Fallback chart installation via workspace XML mutation:
    1. Find active workspace XML: read `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\_Workspaces.xml`, parse `<ActiveWorkspace>` element (e.g., "Main"), then open `workspaces\{ActiveWorkspace}.xml` (e.g., `Main.xml`)
    2. **BACKUP**: Copy to `{name}.backup-{YYYYMMDD-HHMMSS}.xml` (G3 guardrail)
    3. Parse XML using `xml.etree.ElementTree`
    4. Find the target chart tab element (match by instrument name or chart title in `<Tab-*>` elements)
    5. Locate the `<Indicators>` section within the chart tab
    6. Construct an `<Indicator>` element matching the observed workspace schema:
       - Assembly-qualified class name (e.g., `NinjaTrader.NinjaScript.Indicators.DEEP6.DEEP6Signal, NinjaTrader.Custom`)
       - Default property values as `<Property>` child elements
       - Panel assignment attribute
       - NOTE: Agent MUST first read an existing workspace XML to discover the exact schema — element names, attribute patterns, and property serialization format. Do NOT assume schema; parse from reality.
    7. Inject into the chart's `<Indicators>` section
    8. Validate XML well-formedness after mutation
    9. Save modified XML
    10. Trigger workspace reload WITHOUT human intervention:
        - **Option 1 (preferred)**: Use UIAutomation to invoke File → Open Workspace → select the same workspace → OK. This forces NT8 to re-read the XML.
        - **Option 2 (fallback)**: Close and reopen the specific chart tab via UIA. Workspace XML is re-read per-tab.
        - **Option 3 (last resort)**: Emit `NEEDS_RESTART` status. Orchestrator (T17) will attempt NT8 restart with `-workspace` flag if no active strategies are running (G4 compliance).
  - Parameters: `--workspace <path>` (auto-detect if omitted), `--class-name <string>`, `--chart-title <string>`, `--dry-run`
  - Return JSON: `{"backup_path": "...", "workspace": "...", "chart_found": bool, "injected": bool, "xml_valid": bool}`
  - **LIVE MUTATION IS SAFE**: This fallback runs while NT8 is active. The sequence is: backup XML → mutate → reload via UIA (File → Open Workspace → select same workspace → OK). NT8 re-reads the XML when the workspace is reopened. This is safe because the backup ensures recovery if anything goes wrong.
  - **WARNING**: This path is more fragile than UIA (T14). XML schema may change between NT8 versions. Document known schema version.

  **Must NOT do**:
  - G3: MUST create backup before ANY write — backup is the safety net for live mutation
  - Live mutation IS supported: backup → mutate → reload workspace via UIA (File → Open Workspace). NT8 re-reads XML on workspace reload.
  - Do NOT delete or overwrite backups
  - Do NOT inject if chart tab not found — fail gracefully

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: Workspace XML location, NT8 file structure

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T13, T14, T16)
  - **Blocks**: T17 (orchestrator uses this as fallback if T14 fails)
  - **Blocked By**: T2 (nt8_paths.py for workspace directory)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-expert/knowledge.md` — Workspace location: search for "workspace" — `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\`

  **Why Each Reference Matters**:
  - `nt8-expert/knowledge.md`: Workspace directory path. Note: actual XML schema must be discovered by reading a workspace file — no existing documentation of the schema exists in the codebase.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: DryRun shows mutation plan without modifying XML
    Tool: Bash (PowerShell)
    Preconditions: NT8 workspace files exist
    Steps:
      1. Run: python ".claude/skills/nt8-build-verify/scripts/workspace_mutator.py" --class-name "DEEP6Signal" --chart-title "NQ" --dry-run
      2. Parse JSON output
      3. Assert chart_found is true or false (graceful either way)
      4. Assert injected is false (dry run)
      5. Verify no workspace files were modified (compare timestamps)
    Expected Result: Plan shown, no files modified
    Evidence: .sisyphus/evidence/task-15-workspace-dryrun.json

  Scenario: Backup created before mutation
    Tool: Bash (PowerShell)
    Preconditions: Workspace XML exists
    Steps:
      1. Run: python ".claude/skills/nt8-build-verify/scripts/workspace_mutator.py" --class-name "TestIndicator" --chart-title "NQ"
      2. Assert backup_path in output exists on disk
      3. Assert backup file size > 0
      4. Assert backup file content matches original (pre-mutation)
    Expected Result: Backup verified present and valid
    Evidence: .sisyphus/evidence/task-15-workspace-backup.json
  ```

  **Commit**: YES (groups with Wave 3)
  - Message: `feat(skill): add fix loop, chart installation, and workspace mutation`
  - Files: `.claude/skills/nt8-build-verify/scripts/workspace_mutator.py`

- [ ] 16. scripts/fix_loop.ps1 — Iterative Compile→Fix→Recompile Loop

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/fix_loop.ps1`
  - Orchestrate the iterative compile-fix cycle:
    ```
    MAX_ITERATIONS = 8
    for iteration in 1..MAX_ITERATIONS:
        1. Call modal_detect.ps1 — abort if BLOCKED
        2. Call compile_headless.ps1 (fast inner loop)
        3. If success AND path_used was "devaddon" → types already registered in-process, skip Editor F5 → break with SUCCESS
        3b. If success AND path_used was "ninjascript_exe" or "msbuild" → call compile_editor.ps1 (F5 to register types with live NT8) → break with SUCCESS
        4. If errors: call nt8-errors-full.ps1 → pipe to parse_errors.py → pipe to fix_router.py
        4b. **BACKUP BEFORE FIX**: Before fix_router modifies any source file, copy it to `artifacts/<run-id>/backups/iteration-{N}/{filename}`. This is the rollback restore point.
        5. If fix_router returns unfixable errors only → break with PARTIAL (some errors remain)
        6. If fix_router applied fixes → log diff to artifacts → **ROLLBACK CHECK**: recompile via compile_headless, re-count errors. If error count INCREASED → restore source file from `artifacts/<run-id>/backups/iteration-{N}/{filename}`, re-deploy restored file, mark those errors as UNFIXABLE, log rollback to artifacts → continue loop with remaining errors
        7. If error count decreased or unchanged → continue loop
    If MAX_ITERATIONS reached → break with MAX_ITERATIONS_REACHED
    ```
  - Track per-iteration: error count before/after, fixes applied, rollbacks, elapsed time
  - Save iteration log to `artifacts/<run-id>/fix-loop-log.json`: array of `{iteration: N, errors_before: N, errors_after: N, fixes: [...], rollbacks: [...], elapsed_ms: N}`
  - Save all diffs to `artifacts/<run-id>/fix-diffs/iteration-{N}.diff`
  - Parameters: `-SourceFile <path>`, `-MaxIterations <int>` (default 8), `-TimeoutSeconds <int>` (default 60 per compile), `-ArtifactsDir <path>`
  - Exit codes: 0=clean compile, 1=errors remain, 2=infrastructure failure, 3=max iterations reached
  - Return JSON: `{"result": "SUCCESS|PARTIAL|MAX_ITERATIONS|INFRASTRUCTURE_FAILURE", "iterations": N, "final_error_count": N, "total_fixes": N, "total_rollbacks": N}`

  **Must NOT do**:
  - G1: Fix loop must NOT modify files outside the error source file
  - G8: Must NOT fix errors by removing code
  - Do NOT exceed MAX_ITERATIONS — halt and report
  - Do NOT continue if compile_editor fails for infrastructure reasons (UIA blocked)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `nt8-fix`]
    - `nt8-expert`: Compile workflow, DLL reload strategy
    - `nt8-fix`: Fix loop patterns, escalation rules

  **Parallelization**:
  - **Can Run In Parallel**: NO — depends on T13 which is in Wave 3
  - **Parallel Group**: Wave 4 (solo — runs after Wave 3 completes)
  - **Blocks**: T17 (orchestrator calls fix_loop as the compile phase)
  - **Blocked By**: T5 (modal_detect), T6 (deploy), T8 (compile_headless), T9 (compile_editor), T10 (parse_errors), T13 (fix_router — MUST complete before T16 starts)

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-ai-loop.ps1` — Existing deploy→compile→error pipeline: search for "COMPILE-RESULT" — shows the loop structure with sentinel parsing and exit codes. This script is the INSPIRATION — fix_loop.ps1 extends it with actual fix application.
  - `ninjatrader/scripts/nt8-fix-loop.ps1` — Error context snapshot generation and hint lookup. Shows how to collect context for each error. Reuse the context snapshot pattern.

  **Why Each Reference Matters**:
  - `nt8-ai-loop.ps1`: Loop structure, sentinel parsing, exit code convention — fix_loop extends this with automated fixes
  - `nt8-fix-loop.ps1`: Context snapshot pattern — fix_loop must generate similar context for audit trail

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Clean compile exits immediately
    Tool: Bash (PowerShell)
    Preconditions: All NinjaScript source compiles clean
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/fix_loop.ps1" -SourceFile "ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs" -ArtifactsDir "C:/Users/Tea/AppData/Local/Temp/opencode/fix-test"
      2. Parse JSON output
      3. Assert result == "SUCCESS"
      4. Assert iterations == 1 (compiled on first try)
      5. Assert final_error_count == 0
    Expected Result: Single compile, no fix iterations needed
    Evidence: .sisyphus/evidence/task-16-fixloop-clean.json

  Scenario: Fix loop handles injected error
    Tool: Bash (PowerShell)
    Preconditions: Create test .cs with deliberate CS0246 error
    Steps:
      1. Copy a working .cs file to temp location
      2. Add `using FakeNamespace;` to create CS0246
      3. Run fix_loop against modified file
      4. Assert result == "SUCCESS" (fixed and compiled clean)
      5. Assert iterations > 1 (needed fix iterations)
      6. Assert fix-diffs/ directory contains at least 1 diff file
    Expected Result: Error fixed automatically, diffs saved
    Evidence: .sisyphus/evidence/task-16-fixloop-recovery.json
  ```

  **Commit**: YES (Wave 4 — fix loop integration)
  - Message: `feat(skill): add fix loop orchestration with rollback`
  - Files: `.claude/skills/nt8-build-verify/scripts/fix_loop.ps1`

- [ ] 17. scripts/orchestrator.ps1 — Top-Level Pipeline

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/scripts/orchestrator.ps1`
  - The master entry point that ties all subsystems together:
    ```
    1. INIT: Generate run-id, create artifacts directory, start timing
    2. VALIDATE: Run nt8_paths.py — verify NT8 installed, determine available compile paths
    3. DEPLOY: Run deploy.ps1 -SourceFile <path> — atomic deploy to NT8 Custom
    4. COMPILE+FIX: Run fix_loop.ps1 — iterative compile/fix until clean or exhausted
       - If fix_loop returns PARTIAL or MAX_ITERATIONS → emit verdict COMPILE_FAILED, save artifacts, exit 1
    5. INSTALL: Run install_indicator.ps1 -ClassName <name> -ChartTitle <chart>
       - If UIA fails → fall back to workspace_mutator.py (which handles its own workspace reload via UIA File→Open Workspace, chart tab reopen, or NEEDS_RESTART)
       - If workspace_mutator returns NEEDS_RESTART → check for active strategies (G4), restart NT8 with -workspace flag if safe, abort if strategies running
       - If both fail → emit verdict INSTALL_FAILED, save artifacts, exit 1
    6. SETTLE: Wait -SettleMs (default 1500) for rendering
    7. RUNTIME CHECK: Run runtime_check.ps1 -ClassName <name>
       - If runtime errors found → emit verdict RUNTIME_ERROR, save artifacts, exit 1
    8. SCREENSHOT: Run screenshot_chart.ps1 -ChartTitle <chart>
    9. VERIFY: Run verify_visual.py --screenshot <path> --spec <desc>
       - If FAIL and attempt < 2 → loop back to step 4 with vision feedback as new requirements
       - If FAIL and attempt >= 2 → emit verdict VISUAL_FAIL, save artifacts, exit 1
       - If PASS or PASS_WITH_NOTES → proceed
    10. REPORT: Generate final verdict-{HHMMSS}.json, timing.json, save all artifacts. All mutable artifacts (screenshot, verdict) are timestamped per G6.
    ```
  - Parameters:
    - `-SourceFile <path>` (required) — .cs file to deploy
    - `-ChartTitle <string>` (required) — chart to install on (e.g., "NQ 03-26")
    - `-ClassName <string>` (auto-detect from source file namespace if omitted)
    - `-SpecDescription <string>` (for LLM vision verification)
    - `-Parameters <hashtable>` (optional indicator parameter overrides)
    - `-Panel <string>` ("price" or "sub", default "price")
    - `-MaxIterations <int>` (default 8)
    - `-TimeoutSeconds <int>` (default 60)
    - `-SettleMs <int>` (default 1500)
    - `-SkipVisualVerify` (skip LLM vision step)
    - `-DryRun` (show pipeline plan without executing)
    - `-ArtifactsDir <path>` (default `./artifacts`)
  - Exit codes: 0=PASS, 1=FAIL, 2=INFRASTRUCTURE
  - Final artifact listing:
    ```
    artifacts/<run-id>/
    ├── compile-log.json          # Compile results per iteration
    ├── errors.json               # Final error state (empty if clean)
    ├── fix-loop-log.json         # Fix iteration details
    ├── fix-diffs/                # Per-iteration diff files
    ├── screenshot-<timestamp>.png  # Chart screenshot (timestamped for G6 immutability)
    ├── verdict-<timestamp>.json    # Final verdict + reasons (timestamped — never overwritten)
    └── timing.json               # Per-phase timing breakdown (written once at end)
    ```

  **Must NOT do**:
  - All guardrails G1-G11 apply transitively
  - Do NOT proceed past COMPILE+FIX if errors remain (hard stop)
  - Do NOT exceed 2 visual verification attempts (G5)
  - Do NOT leave partial artifacts on failure — always write verdict-{HHMMSS}.json even on crash

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: [`nt8-expert`, `nt8-fix`]
    - `nt8-expert`: Full NT8 workflow understanding
    - `nt8-fix`: Error handling patterns, escalation

  **Parallelization**:
  - **Can Run In Parallel**: NO (sequential — integration point)
  - **Parallel Group**: Wave 5 (solo)
  - **Blocks**: T18, T19, T20, T21 (E2E tests use orchestrator)
  - **Blocked By**: ALL T1-T16

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-ai-loop.ps1` — Full pipeline pattern: deploy → compile → error-scrape with sentinel parsing and exit codes. orchestrator.ps1 extends this with chart installation, visual verification, and artifact management.
  - `ninjatrader/scripts/nt8-context.ps1` — JSON snapshot generation pattern: structured output with timing, status, and error details. Use same approach for verdict.json and timing.json.
  - All scripts in `.claude/skills/nt8-build-verify/scripts/` (T5-T16) — orchestrator calls each of these. Must understand their parameters, exit codes, and JSON output formats.

  **Why Each Reference Matters**:
  - `nt8-ai-loop.ps1`: Pipeline architecture — orchestrator is its spiritual successor with full verification
  - `nt8-context.ps1`: Artifact structure pattern — JSON output format for reports
  - All skill scripts: orchestrator must correctly invoke each and handle their outputs

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: DryRun shows full pipeline plan
    Tool: Bash (PowerShell)
    Preconditions: NT8 installed
    Steps:
      1. Run: powershell ".claude/skills/nt8-build-verify/scripts/orchestrator.ps1" -SourceFile "ninjatrader/Custom/Indicators/DEEP6/DEEP6Signal.cs" -ChartTitle "NQ" -DryRun
      2. Assert output shows each pipeline step with parameters
      3. Assert no actual compilation or deployment occurred
    Expected Result: Pipeline plan displayed, zero side effects
    Evidence: .sisyphus/evidence/task-17-orchestrator-dryrun.txt

  Scenario: Failure produces complete artifacts
    Tool: Bash (PowerShell)
    Preconditions: NT8 running
    Steps:
      1. Create a .cs file with unfixable errors
      2. Run orchestrator against it
      3. Assert exit code 1 (FAIL)
      4. Assert artifacts/<run-id>/ directory exists
      5. Assert compile-log.json exists
      6. Assert errors.json exists and is non-empty
      7. Assert verdict-*.json exists with verdict != "PASS"
      8. Assert timing.json exists
    Expected Result: Even on failure, all artifact files created
    Failure Indicators: Missing artifact files, no verdict-*.json
    Evidence: .sisyphus/evidence/task-17-orchestrator-failure-artifacts.json
  ```

  **Commit**: YES (Wave 4)
  - Message: `feat(skill): add orchestrator pipeline`
  - Files: `.claude/skills/nt8-build-verify/scripts/orchestrator.ps1`

- [ ] 18. E2E Test: Trivial SMA Indicator

  **What to do**:
  - Create a minimal NinjaScript indicator (`TestSMA.cs`) that plots a single SMA line on the price panel
  - Run the FULL orchestrator pipeline against it:
    1. `orchestrator.ps1 -SourceFile TestSMA.cs -ChartTitle "NQ" -ClassName "TestSMA" -SpecDescription "A single blue SMA(14) line on the price panel"`
  - Verify every pipeline stage completed:
    - Deploy: file appeared in NT8 Custom/Indicators/
    - Compile: clean on first try (no fix iterations needed)
    - Install: indicator appears on NQ chart
    - Screenshot: chart shows the SMA line
    - Visual verify: PASS (blue line visible on price panel)
  - After verification, CLEAN UP: remove TestSMA from chart and delete the test file from Custom folder
  - This is the PRIMARY acceptance test — if this passes, the skill works end-to-end

  **Must NOT do**:
  - Do NOT leave TestSMA installed on the chart after test
  - Do NOT use a complex indicator — keep it trivially simple (< 30 lines)
  - Do NOT modify any existing DEEP6 indicators

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`, `nt8-new`]
    - `nt8-expert`: NT8 indicator structure, NinjaScript API
    - `nt8-new`: Code generation for trivial indicator

  **Parallelization**:
  - **Can Run In Parallel**: NO — shares NT8 state with T19, T20
  - **Parallel Group**: Wave 6 (SEQUENTIAL — runs first)
  - **Blocks**: T19 (provides TestSMA.cs and clean chart state)
  - **Blocked By**: T17 (orchestrator must be complete)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-new/knowledge.md` — Indicator generation workflow: namespace, OnStateChange, OnBarUpdate patterns for creating a minimal SMA indicator

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Full E2E pipeline succeeds for trivial SMA
    Tool: Bash (PowerShell)
    Preconditions: NT8 running with NQ chart open, no test indicators installed
    Steps:
      1. Run orchestrator with TestSMA.cs targeting NQ chart
      2. Assert exit code 0
      3. Assert verdict-*.json contains verdict "PASS" or "PASS_WITH_NOTES"
      4. Assert screenshot-*.png exists and is non-blank
      5. Assert timing.json shows all phases completed
      6. Assert fix-loop-log.json shows iterations == 1 (clean compile)
      7. Clean up: remove TestSMA from chart via UIA
    Expected Result: Complete pipeline from deploy to visual verification passes
    Failure Indicators: exit code != 0, missing artifact files, FAIL verdict
    Evidence: .sisyphus/evidence/task-18-e2e-sma.json, .sisyphus/evidence/task-18-e2e-sma-screenshot.png
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(skill): add E2E tests and README`
  - Files: TestSMA.cs (temp), E2E test artifacts

- [ ] 19. E2E Test: Error Injection + Recovery

  **What to do**:
  - Take the working TestSMA.cs from T18
  - Inject a known CS0246 error: add `using FakeNamespace.DoesNotExist;` at the top
  - Run the orchestrator against the corrupted file
  - Verify:
    - Deploy succeeds (file reaches NT8 Custom)
    - First compile FAILS with CS0246
    - Fix loop detects CS0246, removes the fake using directive
    - Second compile SUCCEEDS
    - Indicator installs and passes visual verification
  - Also test: inject CS0103 error (reference a non-existent member) and verify fix loop handles it
  - Save all fix diffs to artifacts for audit

  **Must NOT do**:
  - Do NOT inject errors into real DEEP6 files — use test files only
  - Do NOT inject more than 2 errors per test run

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`, `nt8-fix`]
    - `nt8-expert`: NinjaScript structure for crafting valid error injections
    - `nt8-fix`: Error patterns to verify fix routing works

  **Parallelization**:
  - **Can Run In Parallel**: NO — shares NT8 state with T18, T20
  - **Parallel Group**: Wave 6 (SEQUENTIAL — runs second, after T18)
  - **Blocks**: T20
  - **Blocked By**: T18 (provides TestSMA.cs and clean chart state)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-build-verify/fixes/CS0246.md` (T4) — Fix recipe for CS0246. Verify fix_router applies the strategy described in this recipe.
  - `.claude/skills/nt8-build-verify/scripts/fix_router.py` (T13) — Fix dispatcher. This test verifies its CS0246 handling works in the full pipeline.

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: CS0246 error injected and auto-fixed
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, TestSMA.cs available from T18
    Steps:
      1. Copy TestSMA.cs, add "using FakeNamespace.DoesNotExist;" at line 2
      2. Run orchestrator against corrupted file
      3. Assert exit code 0 (success — error was fixed)
      4. Assert fix-loop-log.json shows iterations > 1
      5. Assert fix-diffs/ contains diff showing removal of fake using
      6. Assert final verdict is PASS
    Expected Result: Error detected, fixed, compiled clean, visual verify passes
    Evidence: .sisyphus/evidence/task-19-error-injection.json

  Scenario: Multiple errors with cascading fix
    Tool: Bash (PowerShell)
    Preconditions: NT8 running
    Steps:
      1. Inject CS0246 (bad using) AND CS0103 (bad member reference) into test file
      2. Run orchestrator
      3. Assert both errors appear in initial error list
      4. Assert fix_loop resolves within MAX_ITERATIONS
    Expected Result: Both errors fixed, clean compile achieved
    Evidence: .sisyphus/evidence/task-19-cascade-fix.json
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(skill): add E2E tests and README`

- [ ] 20. E2E Test: Visual Fail Detection

  **What to do**:
  - Create a test indicator that compiles and installs correctly but renders incorrectly:
    - Spec says: "Blue SMA(14) line on price panel"
    - Indicator actually renders: red dots on a subpanel (or blank — no plot at all)
  - Run the orchestrator with the mismatched spec
  - Verify:
    - Deploy + compile + install all succeed
    - Visual verification detects the mismatch
    - Verdict is FAIL with specific reasons (color mismatch, wrong panel, etc.)
  - Also test: indicator that throws runtime exception (OnBarUpdate crash) → visual verify sees blank chart → FAIL
  - Save screenshot + verdict for audit

  **Must NOT do**:
  - Do NOT use LLM vision if anthropic SDK is not available — test auto-checks (blank detection) instead
  - Do NOT leave broken test indicators installed after test

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: [`nt8-expert`, `nt8-new`]
    - `nt8-expert`: NinjaScript rendering, plot configuration
    - `nt8-new`: Generate indicator with intentionally wrong visual output

  **Parallelization**:
  - **Can Run In Parallel**: NO — shares NT8 state with T18, T19
  - **Parallel Group**: Wave 6 (SEQUENTIAL — runs third, after T19)
  - **Blocks**: F1-F4
  - **Blocked By**: T19 (clean chart state needed)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-visual-design/knowledge.md` — Color system: search for "Long" color (#00E676) — use to verify vision can distinguish expected vs actual colors
  - `.claude/skills/nt8-build-verify/scripts/verify_visual.py` (T12) — Vision verification script being tested

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Visual mismatch detected as FAIL
    Tool: Bash (PowerShell)
    Preconditions: NT8 running with chart
    Steps:
      1. Create indicator that plots RED dots (not blue SMA line)
      2. Run orchestrator with spec "Blue SMA(14) line on price panel"
      3. Assert verdict is FAIL
      4. Assert verdict-*.json contains reasons mentioning color or rendering mismatch
      5. Assert screenshot-*.png captured
    Expected Result: Vision detects mismatch between spec and actual rendering
    Evidence: .sisyphus/evidence/task-20-visual-fail.json, .sisyphus/evidence/task-20-visual-fail-screenshot.png

  Scenario: Blank chart detected by auto-checks (no LLM needed)
    Tool: Bash (PowerShell)
    Preconditions: NT8 running with chart
    Steps:
      1. Create indicator that throws in OnBarUpdate (blank output)
      2. Run orchestrator with --SkipVisualVerify (or rely on auto-checks)
      3. Assert runtime_check detects exception OR screenshot blank_check warns
    Expected Result: Blank/error state detected without LLM call
    Evidence: .sisyphus/evidence/task-20-blank-detect.json
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(skill): add E2E tests and README`

- [ ] 21. README.md — Setup, Usage, Troubleshooting

  **What to do**:
  - Create `.claude/skills/nt8-build-verify/README.md`
  - Sections:
    - **Overview**: What the skill does, pipeline diagram (ASCII art), entry points
    - **Prerequisites**: NT8 installed, Python 3.12+, Pillow (`pip install Pillow`), anthropic SDK (optional for LLM vision)
    - **Quick Start**: Single command to run the full pipeline with example
    - **Configuration**: All configurable parameters with defaults and environment variable overrides
    - **Pipeline Stages**: Description of each stage with success/failure behavior
    - **Fix Recipes**: List of supported error codes with brief description (link to fixes/*.md)
    - **Artifacts**: What's produced per run, where to find it, how to interpret verdict-{HHMMSS}.json. Naming convention: mutable artifacts use timestamps (G6 immutability).
    - **Troubleshooting**: Common issues with solutions:
      - NT8 not running → start NT8 first
      - Modal dialog blocks automation → run modal_detect.ps1 manually
      - Compile timeout → increase -TimeoutSeconds
      - NinjaScript.exe not found → install VS Build Tools or rely on Editor compile
      - UIA chart installation fails → use workspace XML fallback with `-UseWorkspaceXML`
      - Visual verification fails repeatedly → check spec description accuracy
    - **Architecture**: Script dependency diagram, data flow between scripts
    - **Guardrails**: List of G1-G11 with enforcement points
    - **Limitations**: v1 error code set, single indicator per run, no strategy enablement

  **Must NOT do**:
  - Do NOT include implementation details that would become stale — reference scripts for details
  - Do NOT duplicate knowledge.md content — cross-reference it

  **Recommended Agent Profile**:
  - **Category**: `writing`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (no NT8 state dependency)
  - **Parallel Group**: Wave 6 (parallel with T18-T20 sequential chain)
  - **Blocks**: F1-F4
  - **Blocked By**: T17 (needs all scripts complete to document accurately)

  **References**:

  **Pattern References**:
  - `.claude/skills/nt8-build-verify/SKILL.md` (T1) — Skill entry point reference
  - `.claude/skills/nt8-build-verify/knowledge.md` (T1) — Technical reference to cross-link

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: README contains all required sections
    Tool: Bash (PowerShell)
    Preconditions: README.md exists
    Steps:
      1. Run: Select-String -Path ".claude/skills/nt8-build-verify/README.md" -Pattern "## Overview|## Prerequisites|## Quick Start|## Troubleshooting|## Guardrails"
      2. Assert at least 5 section headers found
    Expected Result: All major sections present
    Evidence: .sisyphus/evidence/task-21-readme-sections.txt

  Scenario: Quick Start example is valid
    Tool: Bash (PowerShell)
    Preconditions: README.md exists
    Steps:
      1. Extract the Quick Start command from README
      2. Assert it references orchestrator.ps1 with -SourceFile and -ChartTitle parameters
    Expected Result: Working example command documented
    Evidence: .sisyphus/evidence/task-21-readme-quickstart.txt
  ```

  **Commit**: YES (groups with Wave 6)
  - Message: `feat(skill): add E2E tests and README`
  - Files: `.claude/skills/nt8-build-verify/README.md`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**

- [ ] F1. **Plan Compliance Audit** — `oracle`

  **What to do**:
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run script with --help, check function signatures). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in `.sisyphus/evidence/`. Compare deliverables against plan file listing.

  **QA Scenarios:**

  ```
  Scenario: All Must Have items implemented
    Tool: Bash (PowerShell)
    Steps:
      1. Read .sisyphus/plans/nt8-build-verify.md "Must Have" section
      2. For each item, verify: file exists (Test-Path), function/parameter present (Select-String), or script runs (invoke with -DryRun or --help)
      3. Tally: implemented vs missing
    Expected Result: All Must Have items verified present
    Evidence: .sisyphus/evidence/F1-must-have-audit.json

  Scenario: No Must NOT Have violations
    Tool: Bash (PowerShell)
    Steps:
      1. Read "Must NOT Have (Guardrails)" G1-G11
      2. For each guardrail, search all skill scripts for violation patterns:
         - G1: grep for file writes to paths not matching the error source file
         - G7: grep for error codes outside the locked set
         - G8: grep for "comment out", "remove", "delete" in fix logic
      3. Report any violations with file:line
    Expected Result: Zero violations found
    Evidence: .sisyphus/evidence/F1-guardrail-audit.json
  ```

  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`

  **What to do**:
  Review all PowerShell scripts for: proper error handling (try/catch, exit codes), parameter validation, consistent output format (JSON/sentinel), no hardcoded paths (should use nt8_paths.py), no stubs/TODO comments, proper cmdlet binding. Review Python files for: type hints, proper imports, no bare `except:`, no hardcoded paths.

  **QA Scenarios:**

  ```
  Scenario: All scripts have proper error handling
    Tool: Bash (PowerShell)
    Steps:
      1. For each .ps1 in scripts/: Select-String -Pattern "try\s*\{" to verify try/catch presence
      2. For each .ps1: Select-String -Pattern "exit\s+[0-2]" to verify exit codes present
      3. For each .py in scripts/: Select-String -Pattern "except\s*:" to detect bare excepts (should be 0)
      4. For each .py: Select-String -Pattern "def\s+\w+\(" to find functions, verify type hints present
    Expected Result: All scripts have error handling, no bare excepts, type hints on public functions
    Evidence: .sisyphus/evidence/F2-code-quality.json

  Scenario: No hardcoded user-specific paths
    Tool: Bash (PowerShell)
    Steps:
      1. Grep all scripts for "C:\\Users\\Tea" (should only appear in comments, not functional code)
      2. Verify functional path resolution uses nt8_paths.py or environment variables
    Expected Result: Zero hardcoded paths in functional code
    Evidence: .sisyphus/evidence/F2-hardcoded-paths.txt
  ```

  Output: `Scripts [N clean/N issues] | Python [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `nt8-expert` skill)

  **What to do**:
  Start from clean state. Execute the full orchestrator pipeline against a trivial indicator. Verify every stage completed successfully.

  **QA Scenarios:**

  ```
  Scenario: Full E2E orchestrator pipeline
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, NQ chart open, no test indicators installed
    Steps:
      1. Create trivial TestSMA.cs indicator (SMA(14) on close)
      2. Run: powershell ".claude/skills/nt8-build-verify/scripts/orchestrator.ps1" -SourceFile "TestSMA.cs" -ChartTitle "NQ" -ClassName "TestSMA" -SpecDescription "Blue SMA(14) line on price panel"
      3. Assert exit code 0
      4. Assert artifacts/<run-id>/compile-log.json exists
      5. Assert artifacts/<run-id>/errors.json exists (empty array)
      6. Assert artifacts/<run-id>/screenshot-*.png exists and non-blank
      7. Assert artifacts/<run-id>/verdict-*.json has verdict "PASS" or "PASS_WITH_NOTES"
      8. Assert artifacts/<run-id>/timing.json exists with all phases
    Expected Result: Complete pipeline passes, all artifacts present
    Evidence: .sisyphus/evidence/F3-e2e-pass.json

  Scenario: Error injection and recovery
    Tool: Bash (PowerShell)
    Preconditions: NT8 running
    Steps:
      1. Add "using FakeNamespace.DoesNotExist;" to TestSMA.cs
      2. Run orchestrator
      3. Assert exit code 0 (error was auto-fixed)
      4. Assert fix-loop-log.json shows iterations > 1
      5. Assert fix-diffs/ directory has diff showing removed using
    Expected Result: Error detected, fixed, compiled clean, pipeline completes
    Evidence: .sisyphus/evidence/F3-error-recovery.json
  ```

  Output: `E2E [PASS/FAIL] | Error Recovery [PASS/FAIL] | Artifacts [N/N present] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`

  **What to do**:
  For each task: read "What to do", read actual implementation. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check guardrails G1-G11 compliance.

  **QA Scenarios:**

  ```
  Scenario: Every planned file exists
    Tool: Bash (PowerShell)
    Steps:
      1. Read plan "Concrete Deliverables" file listing
      2. For each listed file: Test-Path and assert exists
      3. Check for UNEXPECTED files in skill directory not in the plan
    Expected Result: All planned files present, no unplanned files
    Evidence: .sisyphus/evidence/F4-file-listing.json

  Scenario: Fix recipes only cover locked error codes
    Tool: Bash (PowerShell)
    Steps:
      1. List all .md files in fixes/ directory
      2. Assert only these 8 exist: CS0103, CS0246, CS1061, CS0019, CS0101, CS0535, BRACE_MISMATCH, MISSING_ATTRIBUTE
      3. Grep fix_router.py for error code handling — assert no codes outside this set
    Expected Result: Locked error code set respected, no scope creep
    Evidence: .sisyphus/evidence/F4-error-codes.json

  Scenario: No scripts modify NT8 settings or configuration
    Tool: Bash (PowerShell)
    Steps:
      1. Grep all .ps1 and .py files for "preferences", "settings", "configuration", "registry"
      2. Assert zero functional matches (comments OK)
    Expected Result: G5/G9 compliance verified
    Evidence: .sisyphus/evidence/F4-settings-check.txt
  ```

  Output: `Tasks [N/N compliant] | Guardrails [N/N respected] | Scope Creep [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

| Wave | Commit Message | Files | Pre-commit Check |
|------|---------------|-------|-----------------|
| 1 | `feat(skill): scaffold nt8-build-verify with foundation layer` | SKILL.md, knowledge.md, nt8_paths.py, diagnostics.py, fix recipes, modal_detect.ps1, deploy.ps1, screenshot_chart.ps1 | `python -c "from lib.nt8_paths import NT8Paths; print(NT8Paths.validate())"` |
| 2 | `feat(skill): add compile infrastructure and error parsing` | compile_headless.ps1, compile_editor.ps1, parse_errors.py, runtime_check.ps1, verify_visual.py | `powershell .\compile_headless.ps1 -DryRun; python parse_errors.py --test` |
| 3 | `feat(skill): add fix loop, chart installation, and workspace mutation` | fix_router.py, fix_loop.ps1, install_indicator.ps1, workspace_mutator.py | `python fix_router.py --test; powershell .\fix_loop.ps1 -DryRun` |
| 4 | `feat(skill): add orchestrator pipeline` | orchestrator.ps1 | `powershell .\orchestrator.ps1 -DryRun` |
| 5 | `feat(skill): add E2E tests and README` | README.md, E2E test artifacts | Full E2E run |

---

## Success Criteria

### Verification Commands
```powershell
# Skill is discoverable by Claude
Get-Content ".claude/skills/nt8-build-verify/SKILL.md" | Select-String "NinjaTrader"  # Expected: trigger patterns present

# Path detection works
python ".claude/skills/nt8-build-verify/lib/nt8_paths.py"  # Expected: JSON with all paths, all validated

# Deploy is atomic and idempotent
powershell ".claude/skills/nt8-build-verify/scripts/deploy.ps1" -SourceFile "test.cs" -DryRun  # Expected: exit 0, shows what would deploy

# Compile headless works
powershell ".claude/skills/nt8-build-verify/scripts/compile_headless.ps1" -TimeoutSeconds 60  # Expected: [COMPILE-RESULT] SUCCESS or FAILED

# Error parsing handles real errors
python ".claude/skills/nt8-build-verify/scripts/parse_errors.py" --test  # Expected: structured error objects

# Fix router dispatches correctly
python ".claude/skills/nt8-build-verify/scripts/fix_router.py" --test  # Expected: fix strategies for each error code

# Full pipeline produces artifacts
powershell ".claude/skills/nt8-build-verify/scripts/orchestrator.ps1" -SourceFile "test_sma.cs" -ChartTitle "NQ"  # Expected: exit 0, artifacts/<run-id>/ has all files
```

### Final Checklist
- [ ] All "Must Have" items present and functional
- [ ] All "Must NOT Have" (G1-G11) guardrails respected
- [ ] E2E: trivial SMA → screenshot with rendering
- [ ] E2E: CS0246 injection → auto-fixed → clean compile
- [ ] E2E: visual mismatch → FAIL verdict
- [ ] Idempotent: second run on same source is no-op
- [ ] All artifacts present after every run (success or failure)
- [ ] Modal dialog detection prevents silent hangs
- [ ] Workspace XML backup created before mutation
