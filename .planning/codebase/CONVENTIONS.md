# Coding Conventions

**Analysis Date:** 2026-04-11

## Naming Patterns

**Types and Classes:**
- PascalCase for all public types: `GexRegime`, `DayType`, `IbType`, `SignalType`, `VwapZone`
- Example: `public enum GexRegime { NegativeAmplifying, NegativeStable, PositiveDampening, Neutral }`
- Indicator class itself: `DEEP6` (all caps as NinjaTrader convention)

**Public Properties:**
- PascalCase for properties exposed via `[NinjaScriptProperty]` attributes
- Examples: `AbsorbWickMin`, `DomDepth`, `Lambda`, `LBeta`, `TressEma`, `IbMins`, `GexHvl`, `CallWall`
- All property parameters are grouped by feature area in `[Display(GroupName="...")]`

**Private Fields:**
- camelCase with underscore prefix: `_fpSc`, `_fpDir`, `_cvd`, `_emaVol`, `_stkTier`, `_imb`, `_imbEma`, `_w1`, `_spEvt`
- Collections also follow underscore convention: `_dQ`, `_bV`, `_aV`, `_bP`, `_aP`, `_iLong`, `_iShort`, `_pLg`, `_pTr`, `_feed`
- UI element fields: `_hBdr`, `_pBdr`, `_tabBdr`, `_panelRoot`, `_hPrc`, `_hDT`, `_gauge`
- SharpDX brush/font fields: `_dxG`, `_dxR`, `_dxGo`, `_dxW`, `_dwF`, `_fC`, `_fS`, `_fL`

**Private Methods:**
- camelCase: `RunE1()`, `RunE2()`, `RunE3()`, `SessionReset()`, `UpdateSession()`, `Scorer()`, `ChkSpoof()`, `RenderFP()`, `BuildUI()`, `InitDX()`, `DisposeDX()`

**Constants:**
- ALL_UPPER_CASE: `VER`, `MX_FP`, `MX_TR`, `MX_SP`, `MX_IC`, `MX_MI`, `MX_VP`, `DDEPTH`
- Example: `private const double MX_FP = 25.0;`

**Local Variables:**
- camelCase throughout method bodies: `score`, `direction`, `delta`, `vol`, `rng`, `bTop`, `bBot`, `prox`, `cW`, `ds`

## Code Style

**Formatting:**
- .editorconfig enforced (see `/.editorconfig`)
- Indentation: 4 spaces (not tabs)
- Line length max: 120 characters (per .editorconfig)
- Charset: UTF-8, line endings: CRLF
- Trim trailing whitespace, insert final newline

**Linting:**
- Enables strict C# analysis: `<Nullable>enable</Nullable>` in `.csproj`
- Language version: C# 10.0 (`<LangVersion>10.0</LangVersion>`)
- Suppressions applied per .editorconfig:
  - `CS0618` (obsolete members) = none (acceptable in NT8 hot-path code)
  - `CS1591` (missing XML docs) = none (optional, not enforced)
  - Additional suppressions in .csproj: `CS0108`, `CS0114`

**Brace Style:**
- `csharp_new_line_before_open_brace = none` — opening braces stay on same line
- Example: `if (condition) { statement; }` (no newline before `{`)
- Else/catch/finally stay on same line as closing brace: `} else {` not `}\nelse {`

**Ternary & Expression Bodies:**
- Expression-bodied methods NOT preferred (silent): `private void Method() { /* statement */ }` preferred
- Expression-bodied properties ALLOWED (suggestion): `public double Value => calculation;`
- Expression-bodied accessors ALLOWED (suggestion): `public string Name { get => _name; set => _name = value; }`

**Spacing:**
- No spaces between method name and parameters: `Method(param)` not `Method (param)`
- Space after control flow keywords: `if (x)` not `if(x)`
- Prefer braces only when multiline (suggestion): `if (x) statement;` OK, but `if (x) {\n  statements;\n}` for multiline

## Import Organization

**Using Block Order (observed in file):**
```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using System.Windows.Threading;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using WBrush  = System.Windows.Media.SolidColorBrush;
using WColor  = System.Windows.Media.Color;
using WColors = System.Windows.Media.Colors;
using WFont   = System.Windows.Media.FontFamily;
#endregion
```

**Pattern:**
1. System.* namespaces first
2. Third-party (SharpDX, Windows)
3. NinjaTrader namespaces
4. Alias declarations at end for brevity (e.g., `using WBrush = ...`)

**Path Aliases:**
- Common shorthand aliases for verbose types (WPF/SharpDX): `WBrush`, `WColor`, `WColors`, `WFont`
- Makes code more readable in UI rendering sections

## Error Handling

**Pattern - Try-Catch with Suppression:**
- Used selectively in hot-path rendering code where collection exceptions are expected
- Example from `RunE1()`:
```csharp
try
{
    for (double p=Low[0]; p<High[0]; p+=TickSize)
    {
        // volumetric data access — may throw
        double ask=vb.Volumes[CurrentBar].GetAskVolumeForPrice(p+TickSize);
        double bid=vb.Volumes[CurrentBar].GetBidVolumeForPrice(p);
        // ...
    }
}
catch { }
```

**Pattern - Guard Clauses:**
- Early return prevents deep nesting (observed in `OnBarUpdate()`, `OnMarketDepth()`)
```csharp
protected override void OnBarUpdate()
{
    if (BarsInProgress == 1 || CurrentBar < BarsRequiredToPlot) return;
    if (Bars.IsFirstBarOfSession) SessionReset();
    // ... rest of logic
}
```

**Pattern - Null Checks:**
- Null propagation with guards before assignment/access:
```csharp
if (vb != null) { /* safe to use */ }
if (_panelRoot != null && ChartControl?.Controls != null) { /* safe */ }
```

## Logging

**Framework:** `Print()` method (NT8 NinjaScript API)

**Patterns:**
- Used at initialization/state transitions only (not hot-path)
- Example: `Print("[DEEP6] Loaded. Volumetric=" + v + " Instrument=" + Instrument.FullName);`
- Minimal logging — focus is on chart visualization, not console output

## Comments

**Strategies Observed:**

**Region Markers:**
- Code organized into logical regions with clear headers
- Examples:
  - `#region Using declarations`
  - `#region Enums`
  - `#region Constants`
  - `#region Parameters` (parameter blocks with property annotations)
  - `#region Private Fields`
  - `#region OnStateChange`
  - `#region Event Handlers`
  - `#region E1 Footprint`, `#region E2 Trespass`, etc. (one per engine)
  - `#region Scorer`
  - `#region Chart Labels & Price Levels`
  - `#region SharpDX Rendering`
  - `#region WPF UI Construction`
  - `#region Panel Update`
  - `#region WPF Helpers`

**Inline Comments:**
- Minimal — code intent is clear from method names and variable names
- Example: `// E1 Footprint`, `// E2 Trespass` as section labels
- Comments in file header explain 7-layer architecture and UI components (20 lines at top)

**Method Documentation:**
- No XML doc comments (`///`) observed
- Naming is self-documenting: `RunE1()`, `ChkSpoof()`, `BuildUI()`, `RenderFP()`

**ASCII Separators:**
- Used sparingly in UI construction code:
```csharp
// ── Header Bar ─────────────────────────────────────────────────────
// ── Status Pills ───────────────────────────────────────────────────
// ── Left Tab Bar ───────────────────────────────────────────────────
```

## NinjaScript-Specific Patterns

**Indicator Property Exposure:**
All user-configurable parameters use `[NinjaScriptProperty]` + `[Display(...)]` attributes:
```csharp
[NinjaScriptProperty][Display(Name="Absorb Min Wick %", Order=1, GroupName="E1 Footprint")]
public double AbsorbWickMin { get; set; }
```

**State Management (`OnStateChange()`):**
- Sets defaults in `State == State.SetDefaults` block
- Configures data series in `State == State.Configure`
- Initializes indicators in `State == State.DataLoaded`
- Builds UI in `State == State.Realtime`
- Cleans up in `State == State.Terminated`

**Plot Declaration:**
- Transparent plots for non-visual output
```csharp
AddPlot(Brushes.Transparent, "Score");
AddPlot(Brushes.Transparent, "Trespass");
```
- Values assigned via `Values[0][0] = _total; Values[1][0] = _imbEma;`

**Event Handlers:**
- `OnBarUpdate()`: Main per-tick logic
- `OnMarketDepth(MarketDepthEventArgs e)`: DOM updates (Level 2 data)
- `OnMarketData(MarketDataEventArgs e)`: Last price/volume updates
- `OnRender(ChartControl cc, ChartScale cs)`: SharpDX rendering
- `OnRenderTargetChanged()`: Resource cleanup on chart resize

**Draw Methods:**
- `Draw.Text()`, `Draw.HorizontalLine()` for chart annotations
- Example: `Draw.Text(this, "D6_"+CurrentBar, true, lbl, 0, y, ...)`

**Data Access Patterns:**
- Volumetric data: `BarsArray[0].BarsType as VolumetricBarsType` → `vb.Volumes[CurrentBar]`
- OHLCV: `Open[0]`, `High[0]`, `Low[0]`, `Close[0]`, `Volume[0]`
- Time: `Time[0]`, `Bars.IsFirstBarOfSession`, `(Time[0]-_sOpen).TotalMinutes`
- TickSize: `TickSize` (contract-aware price increment)

## Function Design

**Size & Scope:**
- Engine methods (`RunE1()` through `RunE7()`) are 15-50 lines each
- Calculation-heavy, no multi-responsibility
- Private helper methods 5-20 lines (e.g., `ChkSpoof()`, `LvPx()`, `Std()`)

**Parameters:**
- Engine methods take no parameters (use private fields for state)
- Event handlers receive framework-provided args: `OnBarUpdate()`, `OnMarketDepth(MarketDepthEventArgs e)`
- Helper methods pass context-specific data: `RenderFP(ChartControl cc, ChartScale cs)`

**Return Values:**
- Most engine methods are `void` (modify internal state)
- Helper methods return computed values: `Std()` returns double, `LvPx()` returns int
- UI helpers return tuples: `(ProgressBar, Label)`, `(Ellipse, Label)`
- Recursive helper returns nullable: `FindGrid(DependencyObject parent)` returns `Grid` or null

## Module Design

**Exports:**
- Single public class: `DEEP6 : Indicator`
- All engine logic, rendering, and UI building is internal to this class
- Public interface = inherited Indicator methods + properties exposed via `[NinjaScriptProperty]`

**Barrel Files:**
- Not applicable (single-file indicator compiled to DLL)

**Visibility Rules:**
- `public`: Only `DEEP6` class and parameter properties
- `protected override`: NinjaScript framework events
- `private`: All business logic, helpers, rendering, UI
- `private const`: Constants

## Observed Patterns

**Lambda & LINQ:**
- Sparse but clean use in E3 and scoring logic
```csharp
double mL = _iLong.Average(), mS = _iShort.Count > 0 ? _iShort.Average() : mL;
var m = _pLg.FirstOrDefault(o => o.lv == lv && o.bid == bid && (DateTime.Now - o.ts) < cw);
_pLg.RemoveAll(o => (DateTime.Now - o.ts).TotalSeconds > 10);
```

**Type Inference:**
- `var` used when type is apparent: `var v = BarsArray[0].BarsType as VolumetricBarsType;`
- Explicit typing preferred for public fields and parameters

**String Formatting:**
- Inline `.ToString()` with format strings: `_vwap.ToString("0.00")`, `delta.ToString("N0")`
- String.Format not used; direct concatenation in some paths
- Example: `"Δ +" + del.ToString("N0")` and string.Join("·", p) for complex builds

**Double.NaN Checks:**
- Pattern for optional calculated values (VWAP only available after bars):
```csharp
if (!double.IsNaN(_vwap)) { /* use _vwap */ }
_vwap = double.IsNaN(_emaVol) ? vol : _emaVol * 0.95 + vol * 0.05;
```

**Queue & Collection Usage:**
- `Queue<double>` for sliding window calculations: `_dQ` (delta history), `_mlH` (ML history)
- `List<T>` for timestamped events: `_pLg` (large orders), `_pTr` (trades), `_feed` (signal history)
- `RemoveAll()` used to prune old entries by timestamp comparison

---

*Convention analysis: 2026-04-11*
