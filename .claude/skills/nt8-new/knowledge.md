# NinjaScript Code Generation Reference

## Mandatory File Structure (in order)

```csharp
// 1. Comment block
// IndicatorName — purpose, install path

// 2. Using declarations
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
// SharpDX (only if doing custom rendering):
// using SharpDX;
// using SharpDX.Direct2D1;
// using SharpDX.DirectWrite;
// using Brush = System.Windows.Media.Brush;       // resolve ambiguity
// using Brushes = System.Windows.Media.Brushes;
#endregion

// 3. GLOBAL-LEVEL ENUMS (NO namespace wrapper) — only if enum used as property type
public enum MySignalType { BullishAbsorption, BearishAbsorption, Neutral }

// 4. Namespace
namespace NinjaTrader.NinjaScript.Indicators
{
    // 5. Class
    public class MyIndicator : Indicator
    {
        // ...
    }
}
// Note: NT8 auto-generates the #region NinjaScript generated code block — do NOT write it
```

---

## OnStateChange — Mandatory Pattern

```csharp
protected override void OnStateChange()
{
    if (State == State.SetDefaults)
    {
        Description = "What this indicator does";
        Name        = "MyIndicator";
        Calculate   = Calculate.OnBarClose;   // or OnEachTick, OnPriceChange
        IsOverlay   = false;                  // true = draws on price panel
        // Set all property defaults:
        Period      = 14;
        SignalColor = Brushes.DodgerBlue;
    }
    else if (State == State.Configure)
    {
        // Add plots (shows as lines on chart):
        AddPlot(Brushes.DodgerBlue, "Signal");
        // Add secondary data series if needed:
        // AddDataSeries(BarsPeriodType.Minute, 1);
    }
    else if (State == State.DataLoaded)
    {
        // Initialize objects that need historical data loaded:
        // _myList = new List<double>();
    }
    else if (State == State.Terminated)
    {
        // Dispose unmanaged resources:
        // if (_dxBrush != null) { _dxBrush.Dispose(); _dxBrush = null; }
    }
}
```

---

## OnBarUpdate — Mandatory Guard Pattern

```csharp
protected override void OnBarUpdate()
{
    if (CurrentBar < Period - 1) return;  // not enough bars yet
    if (BarsInProgress != 0) return;      // only process primary series

    // --- logic ---
    Values[0][0] = SMA(Period)[0];  // assign to plot
}
```

---

## Property Decoration Pattern

### Numeric / bool properties:
```csharp
[NinjaScriptProperty]
[Range(1, int.MaxValue)]
[Display(Name = "Period", Description = "Lookback period in bars", Order = 1, GroupName = "Parameters")]
public int Period { get; set; }

[NinjaScriptProperty]
[Display(Name = "Show Labels", Order = 2, GroupName = "Parameters")]
public bool ShowLabels { get; set; }
```

### Brush/Color (requires serialization pair):
```csharp
[XmlIgnore]
[Display(Name = "Signal Color", Order = 3, GroupName = "Visual")]
public Brush SignalColor { get; set; }

[Browsable(false)]
public string SignalColorSerializable
{
    get { return Serialize.BrushToString(SignalColor); }
    set { SignalColor = Serialize.StringToBrush(value); }
}
```

### Enum property (enum MUST be at global namespace):
```csharp
// At global level (before namespace):
public enum MyMode { Fast, Slow, Auto }

// Inside class:
[NinjaScriptProperty]
[Display(Name = "Mode", Order = 4, GroupName = "Parameters")]
public MyMode Mode { get; set; }
```

---

## Built-In Series (use, don't reimplement)

| Series | Syntax |
|--------|--------|
| Simple MA | `SMA(period)[0]` |
| Exponential MA | `EMA(period)[0]` |
| ATR | `ATR(period)[0]` |
| VWAP | `VWAP()[0]` |
| Bollinger | `Bollinger(stdDevs, period).Upper[0]` |
| Close | `Close[0]` (current), `Close[1]` (1 bar ago) |
| OHLCV | `Open[0]`, `High[0]`, `Low[0]`, `Volume[0]` |
| High N bars ago | `High[barsAgo]` |
| MAX over range | `MAX(High, period)[0]` |
| MIN over range | `MIN(Low, period)[0]` |

---

## Draw.* Methods

```csharp
// Horizontal level
Draw.HorizontalLine(this, "tag", price, Brushes.Gold);

// Diagonal line (barsAgo = 0 is current bar, 1 is one bar ago, etc.)
Draw.Line(this, "tag", false, barsAgo1, y1, barsAgo2, y2, Brushes.White, DashStyleHelper.Solid, 2);

// Text label
Draw.Text(this, "tag", false, "text", barsAgo, y, 0,
    Brushes.White, new SimpleFont("Arial", 9) { Bold = true },
    TextAlignment.Center, null, null, 0);

// Arrows
Draw.ArrowUp(this, "tag", false, barsAgo, Low[barsAgo] - 2 * TickSize, Brushes.Lime);
Draw.ArrowDown(this, "tag", false, barsAgo, High[barsAgo] + 2 * TickSize, Brushes.Red);

// Shapes
Draw.Diamond(this, "tag", false, barsAgo, price, Brushes.Cyan);
Draw.TriangleUp(this, "tag", false, barsAgo, price, Brushes.Lime);
Draw.TriangleDown(this, "tag", false, barsAgo, price, Brushes.Red);

// Rectangle / zone
Draw.Rectangle(this, "tag", false, barsAgo1, y1, barsAgo2, y2,
    Brushes.White, Brushes.DodgerBlue, 30);  // 30 = opacity 0-100
```

---

## FORBIDDEN Patterns (compile errors)

| Pattern | Error | Fix |
|---------|-------|-----|
| `volatile double _x;` | CS0677 | Use `volatile int` + scaling, or `lock {}` block |
| `volatile float _x;` | CS0677 | Same as above |
| `using NinjaTrader.Core;` | CS0234 | Remove — this namespace does not exist in NT8 8.x |
| `Log("msg", LogLevel.Error);` | CS1061 | Use `Print("msg")` instead |
| Enum nested inside class AND used as property type | CS0246 in boilerplate | Move enum to global namespace |
| `async void OnBarUpdate()` | Build error | Not supported — NT8 is not async-friendly |
| `partial class MyIndicator` | Build error | Not supported |
| `SetDefinition(...)` | CS1061 | NT7 method, removed in NT8 |
| `Dispatcher.Invoke(...)` in OnBarUpdate | Runtime crash | Use `TriggerCustomEvent(...)` instead |

---

## SharpDX Custom Rendering (advanced)

Only use when standard Draw.* methods aren't sufficient (pixel-perfect charts, heatmaps).

```csharp
// Fields:
private SharpDX.Direct2D1.SolidColorBrush _myDxBrush;

// In OnStateChange Terminated:
if (_myDxBrush != null) { _myDxBrush.Dispose(); _myDxBrush = null; }

// In OnRenderTargetChanged:
_myDxBrush = new SharpDX.Direct2D1.SolidColorBrush(
    RenderTarget, new SharpDX.Color4(0f, 0.5f, 1f, 0.8f));  // RGBA 0-1

// In OnRender:
var rect = new SharpDX.RectangleF(chartX, chartY, width, height);
RenderTarget.FillRectangle(rect, _myDxBrush);
RenderTarget.DrawRectangle(rect, _myDxBrush, 1f);  // outline, 1px
```

Convert chart coordinates:
```csharp
float chartX = (float)ChartControl.GetXByBarIndex(ChartBars, barIndex);
float chartY = (float)ChartScale.GetYByValue(price);
```

---

## DEEP6 Namespace Conventions

| Use case | Namespace |
|----------|-----------|
| Standalone indicator | `NinjaTrader.NinjaScript.Indicators` |
| Shared types (used by multiple indicators) | `NinjaTrader.NinjaScript.AddOns.DEEP6` |
| AddOn (HTTP server, background service) | `NinjaTrader.NinjaScript.AddOns` |
| Strategy | `NinjaTrader.NinjaScript.Strategies` |

---

## Pre-Generation Checklist

Run this before writing any code:

- [ ] Enum used as property type? → place at GLOBAL namespace (before ALL namespace/class declarations)
- [ ] OnStateChange has: SetDefaults → Configure → DataLoaded → Terminated
- [ ] OnBarUpdate has early return guard (`CurrentBar < X`, `BarsInProgress != 0`)
- [ ] No `volatile double` or `volatile float`
- [ ] No `using NinjaTrader.Core;`
- [ ] Using `Print()` not `Log()`
- [ ] All standard using directives included
- [ ] Properties have `[NinjaScriptProperty]` + `[Display(...)]`
- [ ] Brush properties have serializable string partner
- [ ] Does NOT write the `#region NinjaScript generated code` block
- [ ] No `async` or `await` keywords in NinjaScript lifecycle methods
