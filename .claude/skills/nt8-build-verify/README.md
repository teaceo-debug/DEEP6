# nt8-build-verify

Fully automated NinjaTrader 8 indicator and strategy development pipeline. Takes a `.cs` source file from zero to a visually verified chart render, fixing compile errors along the way.

---

## 1. Overview

The skill orchestrates nine sequential stages: deploy the source file, compile it, run an auto-fix loop on any errors, install the indicator on a live chart, wait for rendering to settle, check for runtime exceptions, capture a screenshot, run visual verification, and emit a structured report.

```
Source .cs -> Deploy -> Compile -> Fix Loop -> Install -> Screenshot -> Verify -> Report
                                      ^            |
                                 Fix Router   Workspace XML
                                      ^         (fallback)
                                 Parse Errors
```

**Entry points:**

- **CLI:** `scripts/orchestrator.ps1` with `-SourceFile`, `-ChartTitle`, and optional flags
- **Claude invocation:** load `SKILL.md` in this directory; Claude reads the trigger patterns and calls `orchestrator.ps1` on your behalf

The skill is self-contained. All scripts, Python helpers, fix recipes, and artifacts live under `.claude/skills/nt8-build-verify/`.

---

## 2. Prerequisites

| Requirement | Notes |
|-------------|-------|
| NinjaTrader 8 | Must be running before the pipeline starts |
| Python 3.10+ | 3.12 recommended; must be in `PATH` |
| Pillow | `pip install Pillow` — used by `verify_visual.py` for blank-frame detection |
| anthropic SDK | `pip install anthropic` — optional; enables LLM vision verification |
| `ANTHROPIC_API_KEY` | Optional env var; if absent, verification falls back to pixel-only checks |

The pipeline does not install Python packages for you. Set up the environment once before first use.

---

## 3. Quick Start

```powershell
# Full pipeline: deploy, compile, install on NQ chart, screenshot + verify
powershell ".claude/skills/nt8-build-verify/scripts/orchestrator.ps1" `
    -SourceFile "path/to/MyIndicator.cs" `
    -ChartTitle "NQ" `
    -SpecDescription "Blue SMA(14) line on price panel"

# Dry run: see the plan without executing anything
powershell ".claude/skills/nt8-build-verify/scripts/orchestrator.ps1" `
    -SourceFile "path/to/MyIndicator.cs" `
    -ChartTitle "NQ" `
    -DryRun
```

The pipeline prints stage-by-stage progress to stdout and writes all artifacts to `artifacts/<run-id>/`. A final `PASS` or `FAIL` verdict appears at the end with total elapsed time.

---

## 4. Configuration

All parameters are passed to `orchestrator.ps1`. None are positional; use named flags.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-SourceFile` | string | required | Absolute or relative path to the `.cs` file to build |
| `-ChartTitle` | string | required | Window title substring of the target NT8 chart (e.g. `"NQ"`) |
| `-SpecDescription` | string | `""` | Natural-language description of what the indicator should look like; used by LLM vision verification |
| `-DryRun` | switch | off | Print the execution plan and exit without running anything |
| `-TimeoutSeconds` | int | `60` | Per-stage compile timeout in seconds |
| `-MaxFixIterations` | int | `8` | Maximum fix loop iterations before giving up |
| `-SkipVerify` | switch | off | Skip screenshot and visual verification stages |
| `-ArtifactsDir` | string | `artifacts/` | Root directory for run artifacts |
| `-Verbose` | switch | off | Emit detailed per-step logging |

---

## 5. Pipeline Stages

### Stage 1: VALIDATE

**Script:** `lib/nt8_paths.py`

Confirms that the NT8 installation exists at the expected base path and that the source file is readable. Fails fast with a clear error if NT8 is not installed or the source file is missing. No files are modified.

### Stage 2: DEPLOY

**Script:** `scripts/deploy.ps1`

Copies the `.cs` file to the appropriate NT8 Custom directory (`Indicators\` or `Strategies\` based on the class declaration). Writes a `deploy-log.json` artifact. Fails if the destination is not writable.

### Stage 3: COMPILE + FIX LOOP

**Scripts:** `scripts/fix_loop.ps1` orchestrates `scripts/compile_headless.ps1`, `scripts/compile_editor.ps1`, `lib/parse_errors.py`, `lib/fix_router.py`

Compile is attempted via the 3-tier strategy (DevAddon HTTP first, NinjaScript.exe second, Editor F5 third). If errors are found, `parse_errors.py` extracts structured error records and `fix_router.py` selects the appropriate recipe from `fixes/*.md`.

Each iteration:
1. Detect and dismiss any modal dialogs (`modal_detect.ps1`)
2. Compile
3. Parse errors
4. Route to fix recipe
5. Apply fix to source
6. Back up the file and write a `.diff` to `fix-diffs/iteration-{N}.diff`
7. Recompile and check whether error count decreased

If error count increases after a fix, the file is rolled back from backup and the error is marked `UNFIXABLE`. The loop exits after `MAX_ITERATIONS` (default 8) or when zero errors remain.

Writes `compile-log.json`, `errors.json`, and `fix-loop-log.json`.

### Stage 4: INSTALL

**Scripts:** `scripts/install_indicator.ps1`, fallback: `lib/workspace_mutator.py`

Primary path (Path X): UIAutomation opens the Indicators dialog (`Ctrl+I`), searches for the indicator by name, adds it, sets parameters, and confirms. If UIAutomation fails, the fallback (Path Y) backs up the active workspace XML, injects the indicator node, and reloads the workspace via UIA.

### Stage 5: SETTLE

A configurable render-settle wait (default 1500ms) gives NT8 time to draw the indicator before the screenshot is taken. Not configurable via CLI in v1; edit `orchestrator.ps1` directly if needed.

### Stage 6: RUNTIME CHECK

**Script:** `scripts/runtime_check.ps1`

Reads the NT8 runtime log for exceptions or `[ERROR]` entries that appeared after installation. A clean log is required to proceed. If exceptions are found, the pipeline fails with the log excerpt attached to the report.

### Stage 7: SCREENSHOT

**Script:** `scripts/screenshot_chart.ps1`

Captures the target chart window using the Windows Graphics API. Output is written to `artifacts/<run-id>/screenshot-{HHMMSS}.png`. The timestamp suffix ensures the file is never overwritten (guardrail G6).

### Stage 8: VERIFY

**Script:** `lib/verify_visual.py`

Two-phase verification:

- **Phase 1 (auto):** Pixel variance check (blank frame detection), file size sanity, legend text detection via Pillow.
- **Phase 2 (LLM vision):** If `ANTHROPIC_API_KEY` is set and a `SpecDescription` was provided, the screenshot is sent to Claude with the spec. The response is one of `PASS`, `PASS_WITH_NOTES`, or `FAIL`. Maximum 2 vision attempts (guardrail G5).

If `ANTHROPIC_API_KEY` is absent, only Phase 1 runs.

### Stage 9: REPORT

Writes `verdict-{HHMMSS}.json` and `timing.json`. Prints a final summary to stdout:

```
[PASS] MyIndicator deployed, compiled, installed, and verified in 34.2s
```

or

```
[FAIL] Stage: VERIFY — LLM verdict: FAIL — indicator not visible on chart
```

---

## 6. Fix Recipes

The fix loop handles a locked set of 8 error codes in v1. Each code has a dedicated recipe file under `fixes/`.

| Error Code | Description | Auto-fixable |
|------------|-------------|--------------|
| `CS0103` | Name does not exist in current context | Yes |
| `CS0246` | Type or namespace not found | Yes |
| `CS1061` | Member does not exist on type | Yes |
| `CS0019` | Operator cannot be applied to operands | Yes |
| `CS0101` | Namespace already contains a definition | Yes |
| `CS0535` | Class does not implement interface member | Yes |
| `BRACE_MISMATCH` | Unbalanced `{` / `}` | Yes |
| `MISSING_ATTRIBUTE` | Required NinjaScript attribute absent | Yes |

Errors outside this set cause the loop to emit `NEEDS_HUMAN` and stop. See `fixes/<CODE>.md` for the exact transformation each recipe applies.

Guardrail G7 enforces this locked set. No new codes are added during execution (G11).

---

## 7. Artifacts

Every run writes to a timestamped directory so nothing is ever overwritten.

```
artifacts/<run-id>/
├── compile-log.json          <- compile attempt results, all tiers
├── deploy-log.json           <- source path, destination path, copy result
├── errors.json               <- structured error records from parse_errors.py
├── fix-loop-log.json         <- per-iteration fix decisions and outcomes
├── fix-diffs/
│   └── iteration-{N}.diff   <- unified diff of each fix applied
├── screenshot-{HHMMSS}.png  <- chart capture (timestamped, never overwritten)
├── verdict-{HHMMSS}.json    <- visual verification result (timestamped)
└── timing.json               <- per-stage elapsed times
```

`<run-id>` is generated at pipeline start as `YYYYMMDD-HHMMSS-<indicator-name>`. Screenshot and verdict files carry their own `HHMMSS` suffix per guardrail G6 so re-runs within the same second don't collide.

---

## 8. Troubleshooting

**NT8 is not running**
Start NinjaTrader 8 before invoking the pipeline. Stage 1 (VALIDATE) will fail immediately if NT8 paths are not accessible.

**A modal dialog is blocking compile**
Run `scripts/modal_detect.ps1 -WhatIf` to see what dialogs are present without dismissing them. The fix loop calls `modal_detect.ps1` automatically at the start of each iteration, but if a dialog appears mid-compile it may not be caught.

**Compile times out**
Increase `-TimeoutSeconds`. The default is 60s. On slower machines or large files, 120s is a reasonable starting point.

**NinjaScript.exe not found**
The pipeline falls back to Editor F5 (Path C) automatically. If the DevAddon HTTP endpoint is also unavailable, Path C is the only option. Ensure the NinjaScript Editor is open in NT8.

**UIAutomation install fails**
The workspace XML fallback (Path Y) activates automatically. If that also fails, check that the workspace file at `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\` is not locked by another process.

**Visual verification fails with a correct-looking chart**
The `SpecDescription` may not match what the indicator actually renders. Make the description more specific (e.g., "thin blue line in the main price panel, no separate pane") or use `-SkipVerify` and inspect the screenshot manually.

**Python not found**
Ensure Python 3.10+ is in `PATH`. Run `python --version` in a new PowerShell window to confirm. The pipeline calls `python` directly; aliases like `python3` are not tried.

---

## 9. Architecture

Script dependency tree for `orchestrator.ps1`:

```
orchestrator.ps1
├── deploy.ps1
├── fix_loop.ps1
│   ├── modal_detect.ps1
│   ├── compile_headless.ps1
│   ├── compile_editor.ps1
│   ├── parse_errors.py        (-> lib/diagnostics.py)
│   └── fix_router.py          (-> fixes/*.md)
├── install_indicator.ps1
│   └── modal_detect.ps1
├── workspace_mutator.py       (fallback for install)
├── runtime_check.ps1
├── screenshot_chart.ps1
├── verify_visual.py           (-> lib/diagnostics.py)
└── lib/
    ├── nt8_paths.py           (path constants + validation)
    └── diagnostics.py         (shared error parsing + verdict types)
```

`lib/diagnostics.py` is the shared type layer. Both `parse_errors.py` and `verify_visual.py` import from it so error records and verdict structures stay consistent across the pipeline.

`fix_router.py` reads `fixes/*.md` at runtime to select the correct transformation. It does not modify those files (G11).

---

## 10. Guardrails

These constraints are enforced by the pipeline and cannot be overridden via CLI flags.

| ID | Description | Enforcement Point |
|----|-------------|-------------------|
| G1 | Fixes modify only the file that contains the error | `fix_router.py` |
| G2 | Semantic errors emit `NEEDS_HUMAN` and stop the loop | `fix_router.py` |
| G3 | Workspace XML is backed up before any mutation | `workspace_mutator.py` |
| G4 | Active strategies are checked before any NT8 restart | `orchestrator.ps1` |
| G5 | Maximum 2 LLM vision verification attempts | `verify_visual.py` |
| G6 | Artifacts are never overwritten; screenshots and verdicts are timestamped | `orchestrator.ps1`, `screenshot_chart.ps1` |
| G7 | Only the 8 locked error codes are auto-fixed | `fix_router.py` |
| G8 | Fixes never remove code; they add or correct | `fix_router.py` |
| G9 | No strategy enablement or NT8 settings changes | `orchestrator.ps1` |
| G10 | Single indicator or strategy per run | `orchestrator.ps1` |
| G11 | Fix recipe files are read-only during execution | `fix_router.py` |

---

## 11. Limitations

**v1 error code set only.** The fix loop handles exactly 8 error codes. Any error outside that set stops the loop and requires manual intervention. New codes will be added in future versions.

**Single indicator per run.** G10 prevents batch processing. Run the pipeline once per `.cs` file.

**No strategy enablement.** G9 means the pipeline installs indicators only. Strategies are deployed and compiled but not enabled or connected to an account.

**Fix recipes are static.** G11 prevents the pipeline from learning or updating recipes based on what it encounters. Recipe improvements require editing `fixes/*.md` outside of a pipeline run.

**Workspace XML schema.** The fallback installer writes workspace XML directly. NT8 may change its workspace schema between versions. If the fallback fails after an NT8 update, check `workspace_mutator.py` against the current schema in `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\`.

**LLM vision is optional.** Without `ANTHROPIC_API_KEY`, verification is pixel-only. Pixel checks catch blank frames but cannot confirm that the indicator is rendering the correct data or colors.

---

*For NT8 path constants and compile tier details, see `knowledge.md`. For trigger patterns and Claude invocation, see `SKILL.md`.*
