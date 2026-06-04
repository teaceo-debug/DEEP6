# NT8 Strategy Operations Skill

Invoke this skill when the user wants to:
- add a strategy to a chart
- enable or disable a strategy safely
- bind a strategy to the correct account
- verify ATM template names and runtime safety settings
- manage sim-vs-live strategy execution posture

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Determine whether the task is **installation on chart**, **enablement**, **runtime validation**, or **ATM/account repair**.
3. Treat runtime safety as part of the task, not an optional extra.

## Invariants

- Start in sim/dry-run mode unless the user explicitly and knowingly wants a live change.
- Account name, ATM template name, and enabled state must all be verified before declaring success.
- `nt8-build-verify` does not handle strategy enablement; use this skill when runtime state matters.
- If the strategy code is broken, hand off to `nt8-fix` or `nt8-build-verify` before enabling anything.

## OpenCode Skills (Universal NT8 Knowledge)

Use when broader strategy/platform knowledge is needed:
- `ninjatrader-builder-doctor`
- `ninjatrader-machine-profile`
