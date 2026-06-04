# GSD Debug — DEEP6 Atlas install/fix execution

Status: execution kickoff
Source plan: `.hermes/plans/2026-04-26_200400-deep6-atlas-install-fix.md`

Goal
- Install the downloaded DEEP6 Atlas NinjaTrader package as-is.
- Reproduce NT8 compile errors.
- Fix only the compile blockers and verify a clean compile.

Scope
1. Stage package files into the workspace.
2. Install indicator, diagnostics indicator, strategy, and sample GEX JSON.
3. Compile in NT8 and capture exact errors.
4. Apply minimal targeted fixes.
5. Recompile until successful.

Notes
- Baseline NT8 compile was successful before Atlas install.
- User requested Claude Code for the code-analysis/fix step.
