# NT8 New Indicator / Strategy Generator

Invoke this skill when the user wants to:
- Create a new NT8 indicator, strategy, or AddOn from scratch
- Describe a trading concept and get NinjaScript C# code
- "write an indicator that...", "create a strategy for...", "build something that shows..."

## Entry Point

Load `knowledge.md` from this directory before generating any code.

## Workflow

1. **Clarify** (if not clear): indicator vs strategy vs AddOn? Overlay on price panel or separate pane?
   What data (price, volume, DOM)? Configurable parameters? What does it draw or signal?

2. **Read a template** — use as structural reference:
   - Simple standalone: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6GexLevels.cs` (first 50 lines)
   - Signal indicator: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6Signal.cs` (first 130 lines)

3. **Generate** following ALL rules in knowledge.md — run the pre-generation checklist before writing

4. **Write** to repo source:
   `C:\Users\Tea\DEEP6\ninjatrader\Custom\[Type]\DEEP6\[Name].cs`

5. **Deploy** — copy to NT8:
   `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\[Type]\DEEP6\[Name].cs`

6. **Compile**:
   ```powershell
   .\ninjatrader\scripts\nt8-compile.ps1 -TimeoutSeconds 45
   ```
   Check for `[COMPILE-RESULT] SUCCESS` or `FAILED`.

7. **Fix errors** if FAILED: invoke the nt8-fix skill workflow (max 3 iterations).
   Read errors via `.\ninjatrader\scripts\nt8-errors-full.ps1 -Format Json`

8. **Report**: what was created, where it lives, how to add to chart:
   Right-click chart → Indicators → DEEP6 category → double-click name

## Base path: `C:\Users\Tea\DEEP6`
