# NT8 Operator Routing Skill

Invoke this skill when the user wants Hermes to act like a full NinjaTrader 8 operator instead of a single-purpose code generator.

Use it for requests like:
- "handle everything for NinjaTrader"
- "figure out which NT8 skill to use"
- "build, fix, install, verify, and manage this in NT8"
- "what part of NinjaTrader is broken?"
- "take this from code to chart to strategy"

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Classify the request into one of the routing domains.
3. Hand off to the smallest correct NT8 skill instead of doing everything through one generic workflow.

## Routing Rule

- Use `nt8-new` for creating new indicators, strategies, or AddOns.
- Use `nt8-fix` for compile errors, runtime exceptions, and broken NinjaScript.
- Use `nt8-build-verify` for deploy → compile → install → screenshot → visual verification.
- Use `nt8-install-repair` for fresh-machine setup, uninstall, corruption recovery, or repair.
- Use `nt8-strategy-operations` for account binding, ATM templates, enable/disable, and runtime safety.
- Use `nt8-chart-verification` for confirming an indicator or strategy is actually working on the real chart.
- Use `nt8-playback-operator` for Market Replay downloads, playback control, stepping, rewinding, forwarding, and replay-session workflows.
- Use `nt8-expert` for general NT8 operation, menus, settings, and platform interaction.
- Use `nt8-architect` for dependency mapping, deployment state, and missing-type analysis.
- Use `nt8-visual-design` for SharpDX visuals, layout, color systems, and rendering design.

## Universal NT8 Knowledge

For platform-wide NT8 knowledge, also invoke these OpenCode skills when needed:
- `ninjatrader-machine-profile`
- `ninjatrader-builder-doctor`
- `ninjatrader-error-doctor`
