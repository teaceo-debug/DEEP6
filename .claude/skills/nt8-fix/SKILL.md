# nt8-fix Skill

Invoke this skill when the user reports a NinjaScript compile error, runtime crash, or CS#### error code and wants it diagnosed and fixed.

## When to Invoke

- User pastes CS#### error text (e.g. `CS0246`, `CS0677`, `CS1061`, etc.)
- Compile fails after deploy — errors returned from `nt8-ai-loop.ps1`
- NinjaScript indicator or strategy causes NT8 to crash or hang on load
- User says "it won't compile" or "there's an error in the indicator"

## Skill Entry Point

1. Load `knowledge.md` in this directory for the error taxonomy, fix patterns, and NT8 constraints
2. Read the failing `.cs` file from `ninjatrader/Custom/` (repo source — NOT the deployed NT8 copy)
3. Apply the fix
4. Run `nt8-ai-loop.ps1 -SourceFile <path>` to deploy + compile + get errors as JSON
5. Iterate until `[COMPILE-RESULT] SUCCESS` with empty error JSON

## Invariants

- NEVER edit files under `C:\Users\Tea\Documents\NinjaTrader 8\` — that is the deployed copy. Always edit repo source under `C:\Users\Tea\DEEP6\ninjatrader\Custom\`
- NEVER click Build in Visual Studio — NT8 owns compilation
- After fixing, always call `nt8-ai-loop.ps1` to confirm the fix compiled cleanly
- If errors remain after 3 iterations, escalate to the user with full error JSON and the current file state
