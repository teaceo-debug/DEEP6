# NinjaScript AI Generation Context

Inject this file into Claude's context whenever generating NinjaScript C# code for NT8.
It contains verified API patterns and known traps from this machine's NT8 installation.

---

## Runtime Constraints

**.NET Framework 4.8, C# 7.3 max.**

- NO `async`/`await` in any NinjaScript callback (`OnBarUpdate`, `OnMarketDepth`, `OnStateChange`, etc.)
- NO `Span<T>`, `Memory<T>`, `ReadOnlySpan<T>`
- NO `record` types
- NO `default interface members`
- NO C# 8+ features (nullable reference types `?`, switch expressions, range/index operators, etc.)
- NO `ValueTuple` without explicitly adding the NuGet reference (avoid it)
- `.csproj` may show `LangVersion 13.0` — this is a project file artifact; NT8 runtime enforces 4.8/.NET Framework restrictions regardless

---

## Namespace Rules

```csharp
namespace NinjaTrader.NinjaScript.Indicators { }       // standard indicators
namespace NinjaTrader.NinjaScript.Indicators.DEEP6 { } // DEEP6 indicators (subfolder = category)
namespace NinjaTrader.NinjaScript.Strategies { }        // strategies
namespace NinjaTrader.NinjaScript.Strategies.DEEP6 { }  // DEEP6 strategies
namespace NinjaTrader.NinjaScript.AddOns { }            // add-ons
```

---

## Class Hierarchy

```
NinjaScriptBase
  ├── Indicator   → use for all display/signal indicators
  └── Strategy    → use for indicators that place orders
```

Do not inherit from anything else unless NT8 docs explicitly say to.

---

## FORBIDDEN — Do NOT generate these

These cause compile errors (CS#### listed where known) or silent runtime crashes:

| Pattern | Why forbidden |
|---------|--------------|
| `SetDefinition()` | Method does not exist in NT8 API |
| `DrawLine()`, `DrawText()`, `DrawArrow()` | NT7 API — removed in NT8. Use `Draw.*` namespace |
| `volatile double` or `volatile float` | CS0677 — C# spec forbids volatile on these types |
| `volatile float` | CS0677 |
| `partial class` | Not supported in NinjaScript compilation model |
| `using SharpDX.Mathematics.Interop;` | Wrong namespace — causes CS0246 |
| `async void OnBarUpdate()` | Will crash NT8 — async not allowed in NinjaScript callbacks |
| `async void OnStateChange()` | Same — no async in NinjaScript callbacks |
| `AddPlot()` called outside `State.Configure` | CS or runtime error — `AddPlot` is Configure-only |
| Redefining `FootprintBar` | Already defined in `DEEP6Footprint.cs` — duplicate type error |
| Redefining `DEEP6_SIGNAL_*` constants | Already defined in `DEEP6Signal.cs` |
| Port 9200 TCP server | `DataBridgeServer` already owns this port |

---

## Mandatory State Machine

`OnStateChange` is the ONLY place where `State` should be checked. Never check `State` inside `OnBarUpdate`.

```csharp
protected override void OnStateChange()
{
    if (State == State.SetDefaults)
    {
        Name        = "MyIndicator";
        Description = "What this indicator does.";
        IsOverlay   = false;   // true = draws on price panel
        Calculate   = Calculate.OnBarClose; // or OnEachTick, OnPriceChange

        // Set ALL default property values here — NT8 reads them at SetDefaults time
        Period = 14;
    }
    else if (State == State.Configure)
    {
        // ONLY place to call AddPlot() and AddDataSeries()
        AddPlot(Brushes.DodgerBlue, "PlotName");

        // Initialize Series<T> here
        myDoubleValues = new Series<double>(this);
    }
    else if (State == State.DataLoaded)
    {
        // Safe to reference other indicators here (e.g. SMA(Close, 20))
        // Clear collections, initialize cross-indicator refs
    }
    else if (State == State.Terminated)
    {
        // Release resources: unsubscribe events, dispose objects
    }
}
```

---

## OnBarUpdate — Always Guard with CurrentBar

```csharp
protected override void OnBarUpdate()
{
    if (CurrentBar < BarsRequiredToPlot) return;

    // Price series (index 0 = current bar, 1 = previous bar, etc.):
    double c  = Close[0];
    double c1 = Close[1];
    double h  = High[0];
    double l  = Low[0];
    double o  = Open[0];
    double v  = Volume[0];

    // Write to a plot:
    Values[0][0] = someCalculatedValue;

    // Write to a named Series<double>:
    myDoubleValues[0] = someValue;
}
```

---

## Property Decoration (Parameters Visible to User)

```csharp
[NinjaScriptProperty]
[Range(1, int.MaxValue)]
[Display(Name = "Period", GroupName = "Parameters", Order = 1)]
public int Period { get; set; }

[NinjaScriptProperty]
[Range(0.001, double.MaxValue)]
[Display(Name = "Multiplier", GroupName = "Parameters", Order = 2)]
public double Multiplier { get; set; }

[NinjaScriptProperty]
[Display(Name = "Show Labels", GroupName = "Display", Order = 1)]
public bool ShowLabels { get; set; }
```

---

## Built-in Indicators (Call These — Do Not Reimplement)

```csharp
SMA(Close, 20)[0]                           // simple moving average
EMA(Close, 14)[0]                           // exponential moving average
WMA(Close, 14)[0]                           // weighted moving average
ATR(14)[0]                                  // average true range
VWAP()[0]                                   // volume-weighted average price
BollingerBands(Close, 14, 2).Upper[0]       // Bollinger upper band
BollingerBands(Close, 14, 2).Lower[0]       // Bollinger lower band
RSI(Close, 14, 3)[0]                        // RSI value
MACD(Close, 12, 26, 9).Diff[0]             // MACD histogram
StdDev(Close, 14)[0]                        // standard deviation
Highest(High, 20)[0]                        // highest value over N bars
Lowest(Low, 20)[0]                          // lowest value over N bars
```

---

## Drawing Objects (NT8 Style — All via Draw.* Static Class)

```csharp
// Line between two points (barsAgo, price)
Draw.Line(this, "tagName", false, startBarsAgo, startY, endBarsAgo, endY,
          Brushes.Red, DashStyleHelper.Solid, 2);

// Text label at a bar
Draw.Text(this, "tagName", "label text", barsAgo, y, Brushes.White);

// Arrows (up = bullish, down = bearish)
Draw.ArrowUp(this, "tagName", barsAgo, y, Brushes.Lime);
Draw.ArrowDown(this, "tagName", barsAgo, y, Brushes.Red);

// Horizontal line across entire chart
Draw.HorizontalLine(this, "tagName", priceLevel, Brushes.Orange);

// Rectangle (price box)
Draw.Rectangle(this, "tagName", barsAgo1, y1, barsAgo2, y2,
               Brushes.Transparent, Brushes.Blue, 1);

// Diamond and triangle markers (used by DEEP6 signal tiers)
Draw.Diamond(this, "tagName", true, barsAgo, y, Brushes.Gold);
Draw.TriangleUp(this, "tagName", true, barsAgo, y, Brushes.Cyan);
Draw.TriangleDown(this, "tagName", true, barsAgo, y, Brushes.Magenta);
```

Tags must be unique strings per drawing object. Reusing a tag updates the existing object in-place.

---

## Thread Safety

`OnBarUpdate` runs on a background thread. Never touch WPF/UI objects directly from it.

```csharp
// WRONG — will crash or corrupt state:
someWpfTextBlock.Text = "hello";

// RIGHT — marshal to UI thread:
Dispatcher.InvokeAsync(() =>
{
    someWpfTextBlock.Text = "hello";
});

// RIGHT — for simple cross-thread field access, use Interlocked:
Interlocked.Exchange(ref _lastScore, newScore);

// RIGHT — volatile is only allowed on integer types:
private volatile int _signalCount;  // OK
// private volatile double _score;  // CS0677 — FORBIDDEN
```

---

## Multi-Series (Watching Multiple Instruments or Timeframes)

```csharp
// In State.Configure:
AddDataSeries("ES 09-25", BarsPeriodType.Minute, 1);   // index 1
AddDataSeries("NQ 09-25", BarsPeriodType.Tick,  1);    // index 2

// In OnBarUpdate:
if (BarsInProgress == 0) { /* primary series */ }
if (BarsInProgress == 1) { /* ES 1-min series */ }
if (BarsInProgress == 2) { /* NQ tick series */ }
```

---

## Strategy Order Methods (Strategy Class Only)

```csharp
// Entry
EnterLong(quantity, "EntryTag");
EnterShort(quantity, "EntryTag");

// Exit
ExitLong("ExitTag", "EntryTag");
ExitShort("ExitTag", "EntryTag");

// Bracket orders (set before entry, keyed by EntryTag)
SetStopLoss("EntryTag", CalculationMode.Ticks, 8, false);
SetProfitTarget("EntryTag", CalculationMode.Ticks, 16);
SetTrailStop("EntryTag", CalculationMode.Ticks, 4, false);

// Position info
if (Position.MarketPosition == MarketPosition.Long) { }
double avgPrice = Position.AveragePrice;
int qty         = Position.Quantity;
```

---

## Key DEEP6 Project Gotchas

- `FootprintBar` — defined in `DEEP6Footprint.cs`. Never redefine it.
- `DEEP6_SIGNAL_*` constants — defined in `DEEP6Signal.cs`. Never redefine them.
- All DEEP6 source files use namespace `NinjaTrader.NinjaScript.Indicators.DEEP6`
- `DataBridgeServer` owns TCP port 9200. Do not create another server on that port.
- DEEP6 source lives at `C:\Users\Tea\DEEP6\ninjatrader\Custom\` — deploy scripts copy to NT8's `bin\Custom\`

---

## Minimal Working Indicator Template

Use this as a starting point. Fill in the logic; do not change the structure.

```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.SuperDom;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6MyIndicator : Indicator
    {
        private Series<double> myValues;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                    = "DEEP6MyIndicator";
                Description             = "Short description of what this does.";
                IsOverlay               = false;
                DisplayInDataBox        = true;
                DrawOnPricePanel        = false;
                PaintPriceMarkers       = false;
                ScaleJustification      = ScaleJustification.Right;
                BarsRequiredToPlot      = 20;

                // Default parameter values
                Period = 14;
            }
            else if (State == State.Configure)
            {
                AddPlot(Brushes.DodgerBlue, "Signal");
                myValues = new Series<double>(this);
            }
            else if (State == State.DataLoaded)
            {
                // Cross-indicator refs, list initialization
            }
            else if (State == State.Terminated)
            {
                // Cleanup
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < BarsRequiredToPlot) return;

            // --- Your logic here ---
            double value = EMA(Close, Period)[0];
            myValues[0]  = value;
            Values[0][0] = value;
            // -----------------------
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Period", GroupName = "Parameters", Order = 1)]
        public int Period { get; set; }
        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6MyIndicator[] cacheDEEP6MyIndicator;
        public DEEP6.DEEP6MyIndicator DEEP6MyIndicator(int period)
        {
            return DEEP6MyIndicator(Input, period);
        }

        public DEEP6.DEEP6MyIndicator DEEP6MyIndicator(ISeries<double> input, int period)
        {
            if (cacheDEEP6MyIndicator != null)
                for (int idx = 0; idx < cacheDEEP6MyIndicator.Length; idx++)
                    if (cacheDEEP6MyIndicator[idx] != null
                        && cacheDEEP6MyIndicator[idx].Period == period
                        && cacheDEEP6MyIndicator[idx].EqualsInput(input))
                        return cacheDEEP6MyIndicator[idx];
            return CacheIndicator<DEEP6.DEEP6MyIndicator>(
                new DEEP6.DEEP6MyIndicator { Period = period }, input, ref cacheDEEP6MyIndicator);
        }
    }
}
#endregion
```

---

## Quick Reference: What to Check Before Submitting Generated Code

- [ ] No `async`/`await` anywhere in the file
- [ ] No `volatile double` or `volatile float`
- [ ] `AddPlot()` only inside `State.Configure`
- [ ] `OnBarUpdate` starts with `if (CurrentBar < BarsRequiredToPlot) return;`
- [ ] Drawing uses `Draw.*` not `Draw*()` (old NT7 flat methods)
- [ ] No redefinition of `FootprintBar`, `DEEP6_SIGNAL_*`, or port 9200 server
- [ ] Namespace is `NinjaTrader.NinjaScript.Indicators.DEEP6` for DEEP6 indicators
- [ ] The generated code region at the bottom matches the class name and properties
