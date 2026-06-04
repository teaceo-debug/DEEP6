# NT8 Chart Verification Skill

Invoke this skill when the user wants to:
- confirm an indicator is really working on the chart
- verify a strategy or indicator rendered correctly after compile
- compare expected chart behavior vs actual chart behavior
- diagnose why something compiles but still looks wrong on the live chart

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Determine whether the task is **post-build acceptance**, **visual mismatch diagnosis**, or **runtime chart validation**.
3. Verify on-chart truth before concluding the indicator or strategy works.

## Invariants

- A clean compile is necessary but not sufficient.
- If code intent and chart behavior disagree, the chart wins until proven otherwise.
- Verify pane placement, visibility, parameter state, and data prerequisites such as Tick Replay.
- If the issue is build/compile/install automation, hand off to `nt8-build-verify`.

## OpenCode Skills (Universal NT8 Knowledge)

Use when broader NT8 or NinjaScript context is needed:
- `ninjatrader-builder-doctor`
- `ninjatrader-machine-profile`
