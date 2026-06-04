# nt8-build-verify Knowledge Base

## Verified NT8 Paths

| Purpose | Path |
|---------|------|
| NT8 root | `C:\Users\Tea\Documents\NinjaTrader 8\` |
| Custom source (all types) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` |
| Indicators | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\` |
| Strategies | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\` |
| DEEP6 repo source | `C:\Users\Tea\DEEP6\ninjatrader\Custom\` |
| DEEP6 Indicators (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\` |
| DEEP6 Strategies (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\` |
| Custom DLL | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` |
| Install.xml | `C:\Users\Tea\Documents\NinjaTrader 8\log\Install.xml` |
| Runtime logs | `C:\Users\Tea\Documents\NinjaTrader 8\log\log.YYYYMMDD.NNNNN.txt` |
| Workspaces | `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\` |
| NinjaScript.exe | `C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe` |

## Compile Strategies

3-tier compile order, tried in order:

- **Path A — DevAddon HTTP**: `POST http://localhost:19206/compile` (fastest, IN-PROCESS — types registered immediately, no F5 needed)
- **Path B — NinjaScript.exe**: `NinjaScript.exe /compile` (headless CLI, DLL updated but not reloaded — needs Editor F5 for registration)
- **Path C — Editor F5**: UIAutomation sends F5 in NinjaScript Editor (authoritative — registers all types with live NT8)

## Fix Loop Workflow

- `MAX_ITERATIONS = 8`
- Each iteration: modal detect → compile → parse errors → route to fix → apply fix → backup + diff → recompile → check error count
- If error count increases after fix → rollback from backup, mark as `UNFIXABLE`
- Locked error codes for v1: `CS0103`, `CS0246`, `CS1061`, `CS0019`, `CS0101`, `CS0535`, `BRACE_MISMATCH`, `MISSING_ATTRIBUTE`

## Chart Installation Workflow

- Primary (Path X): UIAutomation via Indicators dialog (`Ctrl+I` → search → add → set params → OK)
- Fallback (Path Y): Workspace XML mutation (backup → inject → reload workspace via UIA)

## Visual Verification Workflow

- Phase 1: Auto-checks (pixel variance, file size, legend detection)
- Phase 2: LLM Vision (Claude API with screenshot + spec → `PASS` / `PASS_WITH_NOTES` / `FAIL`)
- `MAX 2` vision attempts

## Artifact Structure

```
artifacts/<run-id>/
├── compile-log.json
├── errors.json
├── fix-loop-log.json
├── fix-diffs/
├── screenshot-{HHMMSS}.png
├── verdict-{HHMMSS}.json
└── timing.json
```

## Configurable Timeouts

- compile: `60s`
- render settle: `1500ms`
- UIA element wait: `5s`

## Guardrails G1-G11

- G1: Fixes modify ONLY the error file
- G2: Emit NEEDS_HUMAN for semantic fixes
- G3: Backup before workspace XML write
- G4: Check active strategies before NT8 restart
- G5: MAX 2 visual verification attempts
- G6: Artifacts never overwritten (timestamped)
- G7: Only locked error code set
- G8: Never fix by removing code
- G9: No strategy enablement or NT8 settings changes
- G10: Single indicator per run
- G11: No fix recipe updates during execution

## Error Code Reference

- `fixes/CS0103.md`
- `fixes/CS0246.md`
- `fixes/CS1061.md`
- `fixes/CS0019.md`
- `fixes/CS0101.md`
- `fixes/CS0535.md`
- `fixes/BRACE_MISMATCH.md`
- `fixes/MISSING_ATTRIBUTE.md`

## DEEP6 Namespace Conventions

- `NinjaTrader.NinjaScript.Indicators.DEEP6`
- `NinjaTrader.NinjaScript.Strategies.DEEP6`
- `NinjaTrader.NinjaScript.AddOns.DEEP6`
