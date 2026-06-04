# nt8-fix Knowledge Base

## NT8 File Paths (this machine)

| Purpose | Path |
|---------|------|
| Repo source (Indicators) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\` |
| Repo source (Strategies) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\` |
| NT8 deployed (Indicators) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\` |
| NT8 deployed (Strategies) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\DEEP6\` |
| NT8 compiled DLL | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` |
| NT8 log dir | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |

## FootprintBar Deployment Rule

`FootprintBar.cs` must **never** be deployed to NT8. The inline `FootprintBar` types in `DEEP6Footprint.cs` are the deployed source of truth; the standalone file is for the net8.0 NUnit test project only.

## DEEP6 File Compile Status

| File | Status |
|------|--------|
| `DEEP6Footprint.cs` | active / compiles |
| `DEEP6GexLevels.cs` | active / compiles |
| `DEEP6Signal.cs` | active / compiles |
| `DataBridgeIndicator.cs` | active / compiles |
| `CaptureHarness.cs` | active / compiles |
| `DEEP6Strategy.cs` | active / compiles |
| `DEEP6FatPrintBacktest.cs` | active / compiles |
| `FootprintBar.cs` | shelved / test-only |

## Compile Success/Failure Detection

NT8 does **not** write CS#### compile errors to any log file. Errors exist only in the NinjaScript Editor Output Window UI.

| Signal | Path | Meaning |
|--------|------|---------|
| DLL timestamp change | `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` | Updated only on successful compile |
| Install.xml | `%USERPROFILE%\Documents\NinjaTrader 8\log\Install.xml` | Updated only on success |

Detection algorithm: record DLL `LastWriteTime` before triggering compile; poll until mtime changes (SUCCESS) or timeout elapses (FAILED).

Error retrieval: use UIAutomation on the NinjaScript Editor error grid. If UIAutomation fails, fall back to trace logs for the compile event only.

## Fix Workflow (AI Loop)

1. Read failing `.cs` from `ninjatrader/Custom/` (repo source)
2. Apply the fix
3. Run `nt8-ai-loop.ps1 -SourceFile <abs-path> -Target Indicators`
4. Check `[COMPILE-RESULT] SUCCESS`
5. If FAILED, repeat (max 3 iterations)

Invoke from repo root:

```powershell
& ".\ninjatrader\scripts\nt8-ai-loop.ps1" -SourceFile "C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6GexLevels.cs" -Target Indicators -WaitSeconds 30
```

## DEEP6 Namespace Notes

- `NinjaTrader.NinjaScript.Indicators.DEEP6`
- `NinjaTrader.NinjaScript.Strategies.DEEP6`
- `NinjaTrader.NinjaScript.AddOns.DEEP6`

## Script References

- `ninjatrader/scripts/nt8-ai-loop.ps1`
- `ninjatrader/scripts/nt8-fix-loop.ps1`

## Escalation Checklist

If compile still fails after 3 fix iterations:
1. Print the full JSON error array and current file state
2. Ask the user to paste the NT8 Output Window errors
3. Check for duplicate type / assembly conflicts
