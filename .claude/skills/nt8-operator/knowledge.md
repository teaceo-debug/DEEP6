# NT8 Operator Routing Knowledge

This skill is the top-level router for Hermes-style NinjaTrader work inside DEEP6.

Its job is not to replace the existing NT8 skills. Its job is to select the correct one fast, combine them in the right order, and keep the workflow safe.

## Core Principle

Do **not** treat every NT8 request as a coding task.

NT8 work falls into distinct domains:
- platform install / repair
- code generation
- compile-error fixing
- deployment and visual verification
- strategy operations and risk gating
- replay download and playback control
- chart-side verification
- architecture / dependency mapping
- visual rendering design

The operator skill decides which domain applies first.

## Routing Matrix

| Request type | Primary skill | Secondary skill(s) | Notes |
|---|---|---|---|
| Install NT8, reinstall NT8, remove NT8, repair startup, DB corruption | `nt8-install-repair` | `nt8-expert`, `ninjatrader-machine-profile` | Use this for platform health, not build workflows |
| Build a new indicator, strategy, or AddOn | `nt8-new` | `nt8-build-verify`, `nt8-visual-design` | Generate first, then verify |
| Fix compile or runtime errors | `nt8-fix` | `nt8-architect`, `ninjatrader-error-doctor` | Read repo source, not deployed files |
| Put a file on chart and prove it works | `nt8-build-verify` | `nt8-chart-verification` | Build-verify is automated; chart-verification is acceptance |
| Verify an indicator already on chart is correct | `nt8-chart-verification` | `nt8-expert`, `nt8-build-verify` | Use for reality-check work |
| Enable strategy, bind account, confirm ATM, manage safety | `nt8-strategy-operations` | `nt8-expert` | Separate from build-verify guardrails |
| Download replay data, load playback sessions, play/pause, rewind, forward, step, change replay speed | `nt8-playback-operator` | `nt8-expert`, `nt8-chart-verification` | Use for NT8 playback and replay-session operations |
| What depends on what? Where is type X? Why is namespace Y broken? | `nt8-architect` | `nt8-fix` | Architecture first, then repairs |
| Visual redesign, SharpDX rendering, footprint UX | `nt8-visual-design` | `nt8-new`, `ninjatrader-builder-doctor` | Rendering-specific |
| Generic NT8 operation / menus / settings / chart interaction | `nt8-expert` | `ninjatrader-machine-profile` | Default operational fallback |

## Recommended Multi-Skill Sequences

### 1. New indicator to verified chart
1. `nt8-new`
2. `nt8-build-verify`
3. `nt8-chart-verification`

### 2. Broken compile to working chart
1. `nt8-fix`
2. `nt8-build-verify`
3. `nt8-chart-verification`

### 3. Fresh machine to safe strategy runtime
1. `nt8-install-repair`
2. `nt8-expert`
3. `nt8-strategy-operations`
4. `nt8-chart-verification`

### 4. Visual rework of an existing footprint tool
1. `nt8-visual-design`
2. `nt8-fix` or `nt8-new` depending on scope
3. `nt8-build-verify`
4. `nt8-chart-verification`

### 5. Replay download to controlled playback
1. `nt8-playback-operator`
2. `nt8-chart-verification`

## Existing DEEP6 Automation Assets

These are the current anchors the operator should reuse instead of inventing new flows:

- `ninjatrader/scripts/nt8-deploy.ps1`
- `ninjatrader/scripts/nt8-compile.ps1`
- `ninjatrader/scripts/nt8-status.ps1`
- `ninjatrader/scripts/nt8-ui.ps1`
- `ninjatrader/scripts/nt8-errors-full.ps1`
- `ninjatrader/scripts/nt8-ai-loop.ps1`
- `.claude/skills/nt8-build-verify/scripts/orchestrator.ps1`

## Operational Boundaries

- `nt8-build-verify` intentionally does **not** enable strategies or alter NT8 safety settings.
- `nt8-fix` always edits repo source under `C:\Users\Tea\DEEP6\ninjatrader\Custom\`, never the deployed NT8 copy.
- Chart truth beats code assumptions: if the chart behavior and code intent disagree, verify on-chart before declaring success.
- Use strategy-operations for runtime enabling because live/sim account state, ATM names, and chart context matter.
- Replay download automation is already stronger than playback-control automation; use playback-operator to distinguish proven download flows from experimental control flows.


## Machine Paths

| Purpose | Path |
|---|---|
| DEEP6 repo root | `C:\Users\Tea\DEEP6` |
| NT8 root | `C:\Users\Tea\Documents\NinjaTrader 8\` |
| NT8 Custom | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` |
| NT8 DLL | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` |
| NT8 log dir | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |
| NT8 workspaces | `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\` |
