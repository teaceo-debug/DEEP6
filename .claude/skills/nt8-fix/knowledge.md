# nt8-fix Knowledge Base

## NT8 NinjaScript Compile Environment

- **Runtime**: .NET Framework 4.8 (NOT .NET Core / .NET 5+)
- **C# version**: C# 7.3 — no C# 8+ features (no nullable reference types `string?`, no switch expressions with `=>` chaining, no `IAsyncEnumerable`)
- **Threading**: `async/await` is NOT supported in NinjaScript (or only partially in limited contexts — avoid)
- **No `Span<T>`**, no `ValueTuple` without explicit `System.ValueTuple` nuget (not available in NT8)
- **All UI operations** must happen on the NT8 UI thread via `Dispatcher.InvokeAsync()` or `TriggerCustomEvent()`
- **`OnBarUpdate()`** runs on a background thread — never update UI from it directly

---

## CS Error Quick Reference

| Code | Name | Common Cause | Fix |
|------|------|-------------|-----|
| CS0103 | Name does not exist | Typo; variable out of scope; missing field declaration | Check spelling; declare the field in class body |
| CS0246 | Type/namespace not found | Missing `using` statement; wrong namespace; NT8 API type misspelled | Add correct `using`; verify type name against NT8 API |
| CS0677 | Volatile field invalid type | `volatile double` or `volatile float` declared | Change to `volatile int` or remove `volatile`; use `Interlocked` for atomics |
| CS1061 | No definition / extension method | Method or property doesn't exist on that type; version mismatch | Check NT8 API; verify method name; check NT8 version |
| CS0101 | Type already defined | Two `.cs` files in the same NT8 Custom subfolder define the same class name | Remove or rename the duplicate; check for `FootprintBar.cs` deploy exclusion |
| CS0116 | Member declaration outside class | Code placed outside a class/namespace block | Wrap in correct class body |
| CS0029 | Cannot implicitly convert | Type mismatch on assignment | Explicit cast `(int)`, `(double)`, etc. |
| CS0120 | Object reference required | Called instance method as static | Add `this.` or create instance |
| CS0117 | Does not contain definition | Wrong class for the method | Check which class owns the method |
| CS0428 | Cannot convert method group | Passed method name without `()` or delegate mismatch | Add `()` to call; check delegate signature |
| CS0234 | Namespace does not exist | Wrong namespace path in `using` | Verify exact NT8 namespace |
| CS1502/CS1503 | Wrong argument type/count | Method overload mismatch | Check NT8 API signature; fix argument types |

---

## NT8-Specific API Pitfalls

### `volatile` fields
```csharp
// WRONG — CS0677
private volatile double _lastPrice;

// RIGHT — use int with scaling or use lock
private volatile int _lastPriceScaled;   // store price * 100
// or
private readonly object _lock = new object();
private double _lastPrice;
```

### Threading from indicator to UI
```csharp
// WRONG — called from OnBarUpdate background thread
MyLabel.Content = "hello";

// RIGHT — marshal to UI thread
Dispatcher.InvokeAsync(() => { MyLabel.Content = "hello"; });
// or NT8's own:
TriggerCustomEvent((o, e) => { MyLabel.Content = "hello"; }, null);
```

### `OnBarUpdate()` — always check `CurrentBar` before indexing
```csharp
protected override void OnBarUpdate()
{
    if (CurrentBar < 1) return;   // prevents index-out-of-range on bar 0
    double prev = Close[1];
}
```

### Series access — `[0]` is current bar, `[1]` is one bar ago
```csharp
Close[0]   // current close
Close[1]   // previous close
High[0]    // current high
Volume[0]  // current volume (double, not int)
```

### `AddDataSeries` — must be called in `OnStateChange` / `State.SetDefaults` or `State.Configure`
```csharp
protected override void OnStateChange()
{
    if (State == State.Configure)
    {
        AddDataSeries(BarsPeriodType.Minute, 5);
    }
}
```

### Namespace rules
```csharp
// Indicators:
namespace NinjaTrader.NinjaScript.Indicators { }
// or with DEEP6 subfolder:
namespace NinjaTrader.NinjaScript.Indicators.DEEP6 { }

// Strategies:
namespace NinjaTrader.NinjaScript.Strategies { }
namespace NinjaTrader.NinjaScript.Strategies.DEEP6 { }

// AddOns:
namespace NinjaTrader.NinjaScript.AddOns { }
```

---

## Duplicate Type / CS0101

NT8 compiles ALL `.cs` files in the `Custom/` subtree together. If two files define the same class name, CS0101 fires.

**Known exclusion**: `FootprintBar.cs` must NOT be deployed to NT8. The types it defines are declared inline in `DEEP6Footprint.cs` for NT8 compatibility. The standalone file exists for the net8.0 NUnit test project only.

`nt8-deploy.ps1` has `$NT8_EXCLUDE = @("FootprintBar.cs")` — the exclusion is automatic.

If you see CS0101 for any other type, check whether two source files both declare it and remove/rename one.

---

## Compile Success/Failure Detection

NT8 does NOT write CS#### compile errors to any log file. Errors exist only in the NT8 NinjaScript Editor Output Window UI.

| Signal | Path | Meaning |
|--------|------|---------|
| DLL timestamp change | `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` | Updated ONLY on successful compile |
| Install.xml | `%USERPROFILE%\Documents\NinjaTrader 8\log\Install.xml` — `<CompiledCustomAssembly>` | Updated ONLY on success |

**Detection algorithm** (used by `nt8-compile.ps1`): record DLL `LastWriteTime` before triggering compile; poll until mtime changes (SUCCESS) or timeout elapses (FAILED — errors in Output Window).

**Error retrieval** (used by `nt8-errors.ps1` and `nt8-errors-full.ps1`): UIAutomation tree walk on the NT8 NinjaScript Editor window to scrape the error DataGrid. Falls back to NT8 trace log if UIAutomation cannot reach the window.

---

## Fix Workflow (AI Loop)

```
1. Read failing .cs from ninjatrader/Custom/ (repo source)
2. Identify errors from JSON payload returned by nt8-ai-loop.ps1
3. Apply fixes to repo source file
4. Run:  nt8-ai-loop.ps1 -SourceFile <abs-path-to-.cs> -Target Indicators
5. Check output for [COMPILE-RESULT] SUCCESS
6. If FAILED, read JSON errors, go to step 3
7. After 3 failed iterations, report to user with full error + file state
```

**Invoke command** (PowerShell, run from repo root):
```powershell
& ".\ninjatrader\scripts\nt8-ai-loop.ps1" -SourceFile "C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6GexLevels.cs" -Target Indicators -WaitSeconds 30
```

---

## Common NinjaScript Patterns for DEEP6 Indicators

### Indicator shell
```csharp
#region Using declarations
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.Core.FloatingPoint;
using NinjaTrader.NinjaScript.DrawingTools;
using System;
using System.Collections.Generic;
using System.Windows.Media;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6MyIndicator : Indicator
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 indicator description";
                Name        = "DEEP6MyIndicator";
                Calculate   = Calculate.OnBarClose;
                IsOverlay   = false;
            }
            else if (State == State.Configure)
            {
                // Add data series, setup here
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 1) return;
            // Signal logic here
        }
    }
}
```

### Drawing on chart (use `Draw.*` helpers)
```csharp
Draw.Line(this, "myLine", false, 0, High[0], -10, High[10], Brushes.Cyan, DashStyleHelper.Solid, 2);
Draw.Text(this, "myLabel", "SIGNAL", 0, High[0], Brushes.White);
Draw.Diamond(this, "myDiamond", true, 0, Low[0], Brushes.Lime);
Draw.TriangleUp(this, "myTri", true, 0, Low[0], Brushes.Lime);
```

### `OnRender` for custom pixel-level drawing
```csharp
protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    base.OnRender(chartControl, chartScale);
    // use chartControl.RenderTarget (SharpDX RenderTarget)
    // or use WPF DrawingContext via OnRender override
}
```

---

## NT8 File Paths (this machine)

| Purpose | Path |
|---------|------|
| Repo source (Indicators) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\` |
| Repo source (Strategies) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\` |
| NT8 deployed (Indicators) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\` |
| NT8 deployed (Strategies) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\DEEP6\` |
| NT8 compiled DLL | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` |
| NT8 log dir | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |

**Always edit repo source. Never edit the deployed NT8 copy.**

---

## DEEP6 File Inventory

| File | Type | Purpose |
|------|------|---------|
| `DEEP6Footprint.cs` | Indicator | Footprint chart rendering; defines `FootprintBar` types inline |
| `DEEP6GexLevels.cs` | Indicator | GEX level overlay from FlashAlpha JSON |
| `DEEP6Signal.cs` | Indicator | Signal overlay (TYPE_A / TYPE_B entries, score/category viz) |
| `DataBridgeIndicator.cs` | Indicator | Exports DOM data to Python signal engine via JSON |
| `CaptureHarness.cs` | Indicator | Bar capture for backtesting replay |
| `DEEP6Strategy.cs` | Strategy | Main auto-trade strategy |
| `DEEP6FatPrintBacktest.cs` | Strategy | Fat print backtesting strategy |

---

## Escalation Checklist

If compile still fails after 3 fix iterations:
1. Print full JSON error array and the current file state
2. Ask user to open NT8 Output Window (View > Output Window) and paste its content
3. Check for assembly conflict: `The type ... is defined in assembly` — solution is clean NT8 Custom obj folders and restart NT8
4. Check for NT8 version constraint: some APIs require specific NT8 build numbers
