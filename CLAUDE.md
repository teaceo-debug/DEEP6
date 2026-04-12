<!-- GSD:project-start source:PROJECT.md -->
## Project

**DEEP6 v2.0**

DEEP6 is an institutional-grade footprint chart auto-trading system for NQ futures, built on NinjaTrader 8 with Rithmic Level 2 DOM data. The core engine processes up to 1,000 callbacks/second and synthesizes 44 independent market microstructure signals into a unified confidence score. A Python + Next.js web backend provides ML-driven analytics, parameter evolution, and regime detection. The system's thesis: absorption and exhaustion are the highest-alpha reversal signals in order flow — everything else exists to confirm or contextualize them.

**Core Value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via NT8 ATM Strategy.

### Constraints

- **Platform**: NinjaTrader 8 (.NET Framework 4.8) — indicator must compile and run in NT8's NinjaScript environment
- **Data feed**: Rithmic Level 2 with 40+ DOM levels required for E2/E3/E4 engines
- **Performance**: Must handle 1,000+ callbacks/second without GC pressure or frame drops in SharpDX rendering
- **Rendering**: SharpDX + WPF within NT8 — no external UI frameworks
- **GEX data**: Requires commercial API subscription (SpotGamma or equivalent) — not yet provisioned
- **ML backend**: Python + Next.js — separate from NT8 runtime, communicates via data bridge
- **Development**: macOS dev environment — can edit/plan but cannot compile/run NT8; Windows box required for testing
- **Monolithic risk**: Current DEEP6.cs is 1,010 lines with 7 engines + UI in one file — adding 44 signals + 2 new engines requires careful architecture to avoid maintainability collapse
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- C# 10.0 - NinjaScript indicator for NinjaTrader 8, compiled against .NET Framework 4.8 (`/Users/teaceo/DEEP6/Indicators/DEEP6.cs`)
- PowerShell 5.1+ - Deployment and watch scripts (`/Users/teaceo/DEEP6/scripts/Deploy-ToNT8.ps1`, `Watch-AndDeploy.ps1`, `Trigger-NT8Compile.ps1`)
## Runtime
- .NET Framework 4.8 - Required by NinjaTrader 8. Compiles against `net48` target framework (DEEP6.csproj line 4)
- .NET SDK 7.0+ - Used for local compilation via `dotnet build` and IntelliSense in VS Code. Not used by NT8 runtime; NT8 has its own embedded .NET Framework 4.8
- NuGet - Implicit; no external NuGet dependencies. All required assemblies come from NinjaTrader 8 installation
## Frameworks
- NinjaTrader 8 (NT8) NinjaScript - Main application framework. Indicator derives from `Indicator` base class in `NinjaTrader.NinjaScript.Indicators` namespace (DEEP6.cs line 48, 58)
- Required NT8 assemblies (all referenced in DEEP6.csproj lines 46-74):
- WPF (Windows Presentation Foundation) - Used for custom UI elements: header bar, left tab bar, status pills, right panel with tabs. References: `PresentationCore`, `PresentationFramework`, `System.Xaml`, `System.Windows.Forms` (DEEP6.csproj lines 102-111)
- SharpDX - DirectX/Direct2D wrapper for high-performance chart rendering (footprint cells, delta rows, signal boxes, price level lines). Direct2D used for vector graphics, DirectWrite for text rendering
- dotnet CLI - Builds via `dotnet build DEEP6.csproj` configured in VS Code tasks (tasks.json lines 9-25)
- MSBuild - Underlying build system; custom target `DeployToNT8` post-build (DEEP6.csproj lines 124-132) auto-copies compiled indicator to NT8 Custom folder
## Key Dependencies
- NinjaTrader 8 Core Assemblies (see "Frameworks" section) - No external installation; path resolved via `$(NT8Path)` variable (default: `C:\Program Files\NinjaTrader 8`)
- VolumetricBarsType - Requires NT8 Lifetime License + Order Flow+ subscription. DEEP6 detects and uses Volumetric Bars for footprint data (`NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType` cast in DEEP6.cs lines 219, 309, 338, 463)
- WPF Framework (Windows only) - Used for dynamic UI panel creation (StackPanel, Grid, Label, CheckBox, ComboBox, etc.)
- SharpDX - Vendored or provided by NT8 installation. Used for real-time chart rendering (OnRender override, lines 259-266)
- EMA Indicator (NinjaTrader built-in) - Referenced as `NinjaTrader.NinjaScript.Indicators.EMA` for 20-period exponential moving average (DEEP6.cs line 129, instantiated in OnStateChange, State.DataLoaded)
## Configuration
- NT8 Installation Path - Resolved via `$(NT8Path)` property in DEEP6.csproj (default: `C:\Program Files\NinjaTrader 8`). Can be overridden via environment variable or MSBuild parameter: `dotnet build /p:NT8Path="D:\NT8"`
- NT8 Custom Folder - Resolved via `$(NT8CustomPath)` = `$(USERPROFILE)\Documents\NinjaTrader 8\bin\Custom`. Build post-target auto-copies `Indicators\DEEP6.cs` here after compilation (DEEP6.csproj lines 124-132)
- DEEP6.csproj - .NET SDK project file (SDK="Microsoft.NET.Sdk")
- `.editorconfig` (DEEP6/.editorconfig) - EditorConfig for C# style enforcement
## Platform Requirements
- Windows 10/11 64-bit - PowerShell 5.1+, VS Code with C# Dev Kit extension
- NinjaTrader 8 - 8.0.23+ with Lifetime License (required for Volumetric Bars)
- .NET SDK 7.0+ - For local compilation and IntelliSense (not used by NT8)
- Rithmic Data Feed - Level 2 DOM with 40+ depth levels (E2/E3/E4 engines depend on this)
- Windows 10/11 64-bit (x64 only, see line 17 `<PlatformTarget>x64</PlatformTarget>`)
- NinjaTrader 8 (8.0.23+) with:
- CPU: i7-12700K / Ryzen 7 7700X minimum (i9-14900K / Ryzen 9 7950X recommended)
- RAM: 32GB DDR4 minimum (64GB DDR5 recommended)
- Storage: NVMe SSD 512GB minimum (2TB recommended, 7,000 MB/s)
- GPU: 4GB VRAM minimum (RTX 3060 8GB recommended) for SharpDX rendering
- Network: 1Gbps Ethernet (NOT WiFi), latency <20ms to CME Aurora preferred
- OS: Windows 11 Pro preferred (Windows 10 Pro supported)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- PascalCase for all public types: `GexRegime`, `DayType`, `IbType`, `SignalType`, `VwapZone`
- Example: `public enum GexRegime { NegativeAmplifying, NegativeStable, PositiveDampening, Neutral }`
- Indicator class itself: `DEEP6` (all caps as NinjaTrader convention)
- PascalCase for properties exposed via `[NinjaScriptProperty]` attributes
- Examples: `AbsorbWickMin`, `DomDepth`, `Lambda`, `LBeta`, `TressEma`, `IbMins`, `GexHvl`, `CallWall`
- All property parameters are grouped by feature area in `[Display(GroupName="...")]`
- camelCase with underscore prefix: `_fpSc`, `_fpDir`, `_cvd`, `_emaVol`, `_stkTier`, `_imb`, `_imbEma`, `_w1`, `_spEvt`
- Collections also follow underscore convention: `_dQ`, `_bV`, `_aV`, `_bP`, `_aP`, `_iLong`, `_iShort`, `_pLg`, `_pTr`, `_feed`
- UI element fields: `_hBdr`, `_pBdr`, `_tabBdr`, `_panelRoot`, `_hPrc`, `_hDT`, `_gauge`
- SharpDX brush/font fields: `_dxG`, `_dxR`, `_dxGo`, `_dxW`, `_dwF`, `_fC`, `_fS`, `_fL`
- camelCase: `RunE1()`, `RunE2()`, `RunE3()`, `SessionReset()`, `UpdateSession()`, `Scorer()`, `ChkSpoof()`, `RenderFP()`, `BuildUI()`, `InitDX()`, `DisposeDX()`
- ALL_UPPER_CASE: `VER`, `MX_FP`, `MX_TR`, `MX_SP`, `MX_IC`, `MX_MI`, `MX_VP`, `DDEPTH`
- Example: `private const double MX_FP = 25.0;`
- camelCase throughout method bodies: `score`, `direction`, `delta`, `vol`, `rng`, `bTop`, `bBot`, `prox`, `cW`, `ds`
## Code Style
- .editorconfig enforced (see `/.editorconfig`)
- Indentation: 4 spaces (not tabs)
- Line length max: 120 characters (per .editorconfig)
- Charset: UTF-8, line endings: CRLF
- Trim trailing whitespace, insert final newline
- Enables strict C# analysis: `<Nullable>enable</Nullable>` in `.csproj`
- Language version: C# 10.0 (`<LangVersion>10.0</LangVersion>`)
- Suppressions applied per .editorconfig:
- `csharp_new_line_before_open_brace = none` — opening braces stay on same line
- Example: `if (condition) { statement; }` (no newline before `{`)
- Else/catch/finally stay on same line as closing brace: `} else {` not `}\nelse {`
- Expression-bodied methods NOT preferred (silent): `private void Method() { /* statement */ }` preferred
- Expression-bodied properties ALLOWED (suggestion): `public double Value => calculation;`
- Expression-bodied accessors ALLOWED (suggestion): `public string Name { get => _name; set => _name = value; }`
- No spaces between method name and parameters: `Method(param)` not `Method (param)`
- Space after control flow keywords: `if (x)` not `if(x)`
- Prefer braces only when multiline (suggestion): `if (x) statement;` OK, but `if (x) {\n  statements;\n}` for multiline
## Import Organization
#region Using declarations
#endregion
- Common shorthand aliases for verbose types (WPF/SharpDX): `WBrush`, `WColor`, `WColors`, `WFont`
- Makes code more readable in UI rendering sections
## Error Handling
- Used selectively in hot-path rendering code where collection exceptions are expected
- Example from `RunE1()`:
- Early return prevents deep nesting (observed in `OnBarUpdate()`, `OnMarketDepth()`)
- Null propagation with guards before assignment/access:
## Logging
- Used at initialization/state transitions only (not hot-path)
- Example: `Print("[DEEP6] Loaded. Volumetric=" + v + " Instrument=" + Instrument.FullName);`
- Minimal logging — focus is on chart visualization, not console output
## Comments
- Code organized into logical regions with clear headers
- Examples:
- Minimal — code intent is clear from method names and variable names
- Example: `// E1 Footprint`, `// E2 Trespass` as section labels
- Comments in file header explain 7-layer architecture and UI components (20 lines at top)
- No XML doc comments (`///`) observed
- Naming is self-documenting: `RunE1()`, `ChkSpoof()`, `BuildUI()`, `RenderFP()`
- Used sparingly in UI construction code:
## NinjaScript-Specific Patterns
- Sets defaults in `State == State.SetDefaults` block
- Configures data series in `State == State.Configure`
- Initializes indicators in `State == State.DataLoaded`
- Builds UI in `State == State.Realtime`
- Cleans up in `State == State.Terminated`
- Transparent plots for non-visual output
- Values assigned via `Values[0][0] = _total; Values[1][0] = _imbEma;`
- `OnBarUpdate()`: Main per-tick logic
- `OnMarketDepth(MarketDepthEventArgs e)`: DOM updates (Level 2 data)
- `OnMarketData(MarketDataEventArgs e)`: Last price/volume updates
- `OnRender(ChartControl cc, ChartScale cs)`: SharpDX rendering
- `OnRenderTargetChanged()`: Resource cleanup on chart resize
- `Draw.Text()`, `Draw.HorizontalLine()` for chart annotations
- Example: `Draw.Text(this, "D6_"+CurrentBar, true, lbl, 0, y, ...)`
- Volumetric data: `BarsArray[0].BarsType as VolumetricBarsType` → `vb.Volumes[CurrentBar]`
- OHLCV: `Open[0]`, `High[0]`, `Low[0]`, `Close[0]`, `Volume[0]`
- Time: `Time[0]`, `Bars.IsFirstBarOfSession`, `(Time[0]-_sOpen).TotalMinutes`
- TickSize: `TickSize` (contract-aware price increment)
## Function Design
- Engine methods (`RunE1()` through `RunE7()`) are 15-50 lines each
- Calculation-heavy, no multi-responsibility
- Private helper methods 5-20 lines (e.g., `ChkSpoof()`, `LvPx()`, `Std()`)
- Engine methods take no parameters (use private fields for state)
- Event handlers receive framework-provided args: `OnBarUpdate()`, `OnMarketDepth(MarketDepthEventArgs e)`
- Helper methods pass context-specific data: `RenderFP(ChartControl cc, ChartScale cs)`
- Most engine methods are `void` (modify internal state)
- Helper methods return computed values: `Std()` returns double, `LvPx()` returns int
- UI helpers return tuples: `(ProgressBar, Label)`, `(Ellipse, Label)`
- Recursive helper returns nullable: `FindGrid(DependencyObject parent)` returns `Grid` or null
## Module Design
- Single public class: `DEEP6 : Indicator`
- All engine logic, rendering, and UI building is internal to this class
- Public interface = inherited Indicator methods + properties exposed via `[NinjaScriptProperty]`
- Not applicable (single-file indicator compiled to DLL)
- `public`: Only `DEEP6` class and parameter properties
- `protected override`: NinjaScript framework events
- `private`: All business logic, helpers, rendering, UI
- `private const`: Constants
## Observed Patterns
- Sparse but clean use in E3 and scoring logic
- `var` used when type is apparent: `var v = BarsArray[0].BarsType as VolumetricBarsType;`
- Explicit typing preferred for public fields and parameters
- Inline `.ToString()` with format strings: `_vwap.ToString("0.00")`, `delta.ToString("N0")`
- String.Format not used; direct concatenation in some paths
- Example: `"Δ +" + del.ToString("N0")` and string.Join("·", p) for complex builds
- Pattern for optional calculated values (VWAP only available after bars):
- `Queue<double>` for sliding window calculations: `_dQ` (delta history), `_mlH` (ML history)
- `List<T>` for timestamped events: `_pLg` (large orders), `_pTr` (trades), `_feed` (signal history)
- `RemoveAll()` used to prune old entries by timestamp comparison
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Seven independent scoring engines running on NinjaScript lifecycle callbacks
- Real-time data ingestion from Rithmic Level 2 DOM (up to 1,000 callbacks/second)
- Deterministic consensus-based scoring pipeline (agreement ratio multiplier)
- WPF overlay UI (header bar, left tabs, status pills, right panel) + SharpDX volumetric footprint rendering
- Session-scoped state tracking (VWAP, Initial Balance, POC migration, Day Type)
- NinjaTrader 8 integration via OnStateChange → OnBarUpdate → OnRender lifecycle
## Layers
- Purpose: Capture market data callbacks at tick/bar level granularity
- Location: `OnMarketDepth` (lines 246–265), `OnMarketData` (lines 267–268), `OnBarUpdate` (lines 233–244)
- Contains: Level 2 DOM queue updates, last trade price/volume, bar completion triggers
- Depends on: NinjaTrader Cbi/Data APIs, VolumetricBarsType
- Used by: All seven engines + session context
- Purpose: Compute directional bias and confidence score for each strategic pattern
- Location: `RunE1()` (lines 334–387), `RunE2()` (lines 389–402), `RunE3()` (lines 406–424), `RunE4()` (lines 427–442), `RunE5()` (lines 446–456), `RunE6()` (lines 460–480), `RunE7()` (lines 484–505)
- Contains: Footprint absorption/imbalance analysis, DOM queue trespass, Wasserstein spoof detection, iceberg pattern matching, Naive Bayes micro-probability, DEX-ARRAY context scoring, Kalman filter velocity + logistic ML quality
- Depends on: Session context state (_cvd, _vwap, _vsd, _ibH/_ibL, _pPoc, _emaVol), DOM arrays (_bV[], _aV[], _bP[], _aP[]), trade history queues
- Used by: Scorer engine
- Purpose: Maintain intra-session reference levels (VWAP, IB, POC, Day Type, GEX regime)
- Location: `SessionReset()` (lines 282–290), `UpdateSession()` (lines 292–330)
- Contains: VWAP/VAH/VAL calculation, Initial Balance tracking (type classification: Wide/Normal/Narrow), POC migration counter, Day Type classification (TrendBull/TrendBear/BalanceDay/Unknown)
- Depends on: Bar OHLCV data, VolumetricBarsType for POC extraction
- Used by: All engines (especially E6 VP+CTX), UI display (header/pills)
- Purpose: Aggregate 7 engine scores into unified 0–100 confidence metric with signal type classification
- Location: `Scorer()` (lines 509–526)
- Contains: Direction voting (bit flags for bull/bear per engine), agreement ratio multiplier (max engines / total engines), signal type classification (TypeA ≥80, TypeB ≥65, TypeC ≥50)
- Depends on: All engine outputs (_fpDir, _trDir, _icDir, _miDir, _dexDir + scores _fpSc through _vpSc)
- Used by: Signal label generation, UI panel updates, chart rendering
- Purpose: Draw volumetric footprint cells, POC lines, signal boxes, STKt markers onto chart canvas
- Location: `InitDX()` (lines 573–593), `DisposeDX()` (lines 595–602), `RenderFP()` (lines 607–655), `RenderSigBoxes()` (lines 657–678), `RenderStk()` (lines 680–691)
- Contains: Direct2D brush/font initialization, per-bar volumetric rendering (bid/ask cells with imbalance coloring), signal label box rendering, STKt triangle markers
- Depends on: SharpDX.Direct2D1/DirectWrite APIs, ChartControl coordinate transforms
- Used by: OnRender callback
- Purpose: Build and update interactive overlay UI elements (header, pills, tabs, right panel)
- Location: `BuildUI()` (line 695), `BuildHeader()` (lines 704–733), `BuildPills()` (lines 741–769), `BuildTabBar()` (lines 772–791), `BuildPanel()` (lines 794–843), `UpdatePanel()` (lines 879–927)
- Contains: WPF Border/StackPanel/Canvas hierarchy, label binding, progress bar updates, status dot indicators, score gauge drawing
- Depends on: WPF System.Windows.* namespaces, ChartControl hierarchy traversal (FindGrid)
- Used by: Realtime event handler
## Data Flow
- **Per-Bar State:** `_fpSc`, `_fpDir`, `_trSc`, `_trDir`, `_icSc`, `_icDir`, `_miSc`, `_miDir`, `_dexFired`, `_dexDir`, `_vpSc`, `_mlSc`, `_total`, `_sigDir`, `_sigTyp`
- **Per-Session State:** `_vwap`, `_vsd`, `_vah`, `_val`, `_ibH`, `_ibL`, `_ibTyp`, `_ibDone`, `_ibConf`, `_dPoc`, `_pPoc`, `_pocMB`, `_pocMU`, `_dayTyp`, `_oPx`, `_sOpen`, `_iHi`, `_iLo`, `_cvd`
- **Queues/Buffers:** `_dQ` (delta queue, 5 bars), `_iLong` (imbalance long, 62 bars), `_iShort` (imbalance short, 12 bars), `_pLg` (large orders w/ timestamp), `_pTr` (trades w/ timestamp), `_mlH` (ML quality history, 20 bars), `_feed` (signal feed, max 12 items)
## Key Abstractions
- `GexRegime`: {NegativeAmplifying, NegativeStable, PositiveDampening, Neutral} — user-supplied external GEX regime
- `DayType`: {TrendBull, TrendBear, FadeBull, FadeBear, BalanceDay, Unknown} — intra-session classification
- `IbType`: {Wide, Normal, Narrow} — Initial Balance range classification
- `SignalType`: {Quiet, TypeC, TypeB, TypeA} — signal severity
- `VwapZone`: {Above2Sd, Above1Sd, AboveVwap, AtVwap, BelowVwap, Below1Sd, Below2Sd} — price proximity to VWAP
- `MX_FP = 25.0`, `MX_TR = 20.0`, `MX_SP = 15.0`, `MX_IC = 15.0`, `MX_MI = 10.0`, `MX_VP = 15.0` — engine max point contributions
- `DDEPTH = 10` — DOM depth array size
- 7 engine-specific tuning groups (E1–E6), GEX user-supplied levels, Scoring thresholds, Display toggles
- See README.md lines 172–192 for parameter semantics
- Engine state stored as doubles: `_fpSc`, `_fpDir`, `_trSc`, `_trDir`, `_w1`, `_spSc`, `_icSc`, `_icDir`, `_pBull`, `_pBear`, `_miSc`, `_miDir`, `_vpSc`, `_dexFired`, `_mlSc`
- Session state: grouping of VWAP/IB/POC/Day-related fields
- Kalman filter state: `_kSt[2]` (position/velocity), `_kP[2,2]` (covariance matrix)
## Entry Points
- **State.SetDefaults:** Initialize all parameters with production-calibrated defaults
- **State.Configure:** Add 1-minute data series for reference
- **State.DataLoaded:** Create EMA(20) for volume/range smoothing, validate VolumetricBarsType availability
- **State.Realtime:** Build UI (header, pills, tabs, panel) on Dispatcher
- **State.Terminated:** Cleanup WPF and DirectX resources
- Skip if BarsInProgress == 1 (ignore 1-min series)
- Skip if CurrentBar < BarsRequiredToPlot (25 bars minimum)
- Session initialization if first bar of session
- Update session context (VWAP, IB, POC, Day Type)
- Execute engines: RunE1(), RunE5(), RunE6(), RunE7()
- Execute Scorer()
- Plot values
- Generate signal label if TypeB+
- Update UI (levels, panel)
- Fires ~1,000× per second during market hours
- Populate DOM arrays (_bV, _aV, _bP, _aP)
- Track large order placements (spoof detection)
- Execute E2, E3 on every call
- Last trade price/volume → E4 iceberg detection
- Chart canvas repaint callback
- Initialize DirectX on first call
- Execute RenderFP, RenderSigBoxes, RenderStk conditionally based on Show* flags
## Scoring Formula
```
```
## Cross-Cutting Concerns
- One-time print at DataLoaded: `[DEEP6] Loaded. Volumetric=true Instrument=NQ1!`
- No per-bar logging (performance-critical path)
- BarsRequiredToPlot: 25 bar minimum
- MinCellVol threshold to filter noise in RenderFP
- E3 ILong queue requires minimum 5 items before Wasserstein calc
- Not applicable (NinjaTrader sandbox environment)
- try-catch blocks in volumetric data access (VolumetricBarsType nullable checks)
- DoesNotExist guards on UI traversal (FindGrid null check, Window.GetWindow null check)
- Safe disposal pattern in DisposeDX: `D<T>(ref x)` generic helper
- EMA decay: `_emaVol = _emaVol * 0.95 + vol * 0.05` (fast response)
- Queue dequeuing: explicit `.Dequeue()` when capacity exceeded
- OnMarketDepth returns early if Position >= DDEPTH
- OnBarUpdate returns early on skip conditions
- SharpDX batches rendering per visible bar range
- Dispatcher.InvokeAsync prevents UI blocking
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
