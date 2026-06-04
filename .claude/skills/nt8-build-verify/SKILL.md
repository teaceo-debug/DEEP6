# nt8-build-verify Skill

Invoke this skill when the user asks you to:
- Build, compile, and verify a NinjaTrader 8 indicator or strategy end-to-end
- Deploy a .cs file to NT8 and verify it compiles cleanly
- Install an indicator or strategy on a chart and visually verify it renders correctly
- Run the full build-verify pipeline: deploy → compile → fix errors → install → screenshot → verify
- Auto-fix NinjaScript compile errors (CS0246, CS0103, CS1061, etc.)

Trigger patterns: "build this indicator", "put it on my chart", "compile and verify", "build and verify", "deploy to NT8", "install on chart", "NinjaScript", "NT8", ".cs file"

## Skill Entry Point

1. Load `knowledge.md` in this directory for verified NT8 paths, compile strategies, fix loop workflow, and guardrails.
2. The main pipeline script is `scripts/orchestrator.ps1` — it orchestrates: deploy → compile → fix loop → install → screenshot → visual verify → report.

Always check the actual NT8 paths on disk before acting — do not assume.
Verified base path: `C:\Users\Tea\Documents\NinjaTrader 8\`

## OpenCode Skills (Universal NT8 Knowledge)
For universal NT8 knowledge, invoke these opencode skills:
- `ninjatrader-machine-profile` — NT8 platform, installation, editor, state machine, namespaces
- `ninjatrader-builder-doctor` — NinjaScript development patterns, indicators, strategies, SharpDX
- `ninjatrader-error-doctor` — Error diagnosis, CS error codes, runtime exceptions
