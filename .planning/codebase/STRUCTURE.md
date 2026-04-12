# Codebase Structure

**Analysis Date:** 2026-04-11

## Directory Layout

```
DEEP6/
├── Indicators/
│   └── DEEP6.cs                      # Main indicator (1,010 lines)
│
├── scripts/
│   ├── Deploy-ToNT8.ps1              # Copy to NT8 Custom folder (120 lines)
│   ├── Watch-AndDeploy.ps1           # Auto-deploy on save (75 lines)
│   └── Trigger-NT8Compile.ps1        # Bring NT8 to foreground (44 lines)
│
├── docs/
│   ├── DEEP6_Master_Blueprint_v2.md  # Complete UI/element spec
│   └── DEEP6_Master_Execution_Plan.docx  # 42-page hedge fund requirements
│
├── tests/
│   └── DEEP6.Tests.md                # Engine unit test spec (pending Phase 4)
│
├── .vscode/
│   ├── settings.json                 # Editor + OmniSharp config
│   ├── extensions.json               # Recommended extensions (C# Dev Kit, etc.)
│   ├── tasks.json                    # Build/deploy/watch tasks
│   └── launch.json                   # Debugger attach to NT8
│
├── DEEP6.csproj                      # .NET Framework 4.8 project file (134 lines)
├── .editorconfig                     # Code style rules
├── .gitignore
├── README.md                         # User guide + quick start
└── .planning/
    └── codebase/                     # Architecture docs (this directory)
        ├── ARCHITECTURE.md
        └── STRUCTURE.md
```

## Directory Purposes

**Indicators/:**
- Purpose: NinjaScript indicator source code
- Contains: Single C# class inheriting from `Indicator` base
- Key files: `DEEP6.cs` (all engines + UI/rendering in one file)

**scripts/:**
- Purpose: PowerShell deployment automation for NT8 integration
- Contains: Build output copying, file watch, process management
- Key files: `Deploy-ToNT8.ps1` (primary deployment), `Watch-AndDeploy.ps1` (hot-reload during dev)

**docs/:**
- Purpose: Design specifications and requirements
- Contains: Complete UI element catalog, algorithm specs, IB/DEX/STKt/GEX/VWAP zone definitions
- Key files: `DEEP6_Master_Blueprint_v2.md` (~1,300 lines of detailed specs)

**tests/:**
- Purpose: Test specifications for Phase 4 (Backtesting Config)
- Contains: Planned unit test definitions
- Status: Not yet implemented (roadmap milestone P4a)

**.vscode/:**
- Purpose: VS Code editor configuration
- Contains: C# analyzer settings, build tasks, debugger launch config
- Key files: `tasks.json` (Ctrl+Shift+B build, deploy task, watch task)

## Key File Locations

**Entry Points:**

- `Indicators/DEEP6.cs` (line 57): Main class definition `public class DEEP6 : Indicator`
- `Indicators/DEEP6.cs` (line 183): `OnStateChange()` — NinjaScript lifecycle entry
- `Indicators/DEEP6.cs` (line 233): `OnBarUpdate()` — Bar completion event handler
- `Indicators/DEEP6.cs` (line 246): `OnMarketDepth()` — DOM callback (1,000/sec)
- `Indicators/DEEP6.cs` (line 267): `OnMarketData()` — Last trade callback
- `Indicators/DEEP6.cs` (line 270): `OnRender()` — Chart repaint callback

**Configuration:**

- `DEEP6.csproj` (line 16): NT8 install path (default `C:\Program Files\NinjaTrader 8`)
- `.editorconfig` (present): C# formatting rules
- `.vscode/settings.json`: OmniSharp analyzer, code analysis rules
- `.vscode/tasks.json`: Build/deploy command definitions
- `.vscode/launch.json`: Debugger process ID targeting

**Core Logic:**

- `Indicators/DEEP6.cs` (lines 281–330): Session context (VWAP, IB, POC, Day Type)
- `Indicators/DEEP6.cs` (lines 333–387): E1 Footprint engine
- `Indicators/DEEP6.cs` (lines 389–402): E2 Trespass engine (DOM imbalance)
- `Indicators/DEEP6.cs` (lines 406–424): E3 CounterSpoof engine (Wasserstein + cancel tracking)
- `Indicators/DEEP6.cs` (lines 427–442): E4 Iceberg engine (trade vs DOM detection)
- `Indicators/DEEP6.cs` (lines 446–456): E5 Micro engine (Naive Bayes probability)
- `Indicators/DEEP6.cs` (lines 460–480): E6 VP+CTX engine (DEX-ARRAY + VWAP/IB/GEX context)
- `Indicators/DEEP6.cs` (lines 484–505): E7 ML Quality engine (Kalman + logistic classifier)
- `Indicators/DEEP6.cs` (lines 509–526): Scorer engine (consensus voting + agreement ratio)

**Testing:**

- `tests/DEEP6.Tests.md`: Engine test specification file (pending implementation)

## Naming Conventions

**Files:**

- **Indicator files:** `DEEP6.cs` — matches NinjaScript class name (required)
- **Script files:** `Deploy-ToNT8.ps1`, `Watch-AndDeploy.ps1`, `Trigger-NT8Compile.ps1` — PascalCase with hyphens, action-verb prefix
- **Config files:** `.editorconfig`, `DEEP6.csproj`, `.gitignore` — lowercase dotfiles
- **Documentation:** `README.md`, `DEEP6_Master_Blueprint_v2.md`, `DEEP6.Tests.md` — UPPERCASE.md pattern

**Directories:**

- **Source:** `Indicators/`, `scripts/`, `docs/`, `tests/`, `.vscode/` — lowercase, plural for collections

**C# Naming (within DEEP6.cs):**

**Classes:**
- `DEEP6` — public indicator class
- No additional classes (monolithic design)

**Methods:**
- **Lifecycle:** `OnStateChange()`, `OnBarUpdate()`, `OnMarketDepth()`, `OnMarketData()`, `OnRender()` — NinjaScript overrides (PascalCase)
- **Engines:** `RunE1()`, `RunE2()`, `RunE3()`, `RunE4()`, `RunE5()`, `RunE6()`, `RunE7()` — verb-noun (PascalCase, non-private)
- **Session:** `SessionReset()`, `UpdateSession()` — verb-subject (PascalCase, private)
- **Scorer:** `Scorer()` — single name (PascalCase, private)
- **Rendering:** `RenderFP()`, `RenderSigBoxes()`, `RenderStk()`, `InitDX()`, `DisposeDX()` — verb-noun (PascalCase, private)
- **UI:** `BuildUI()`, `BuildHeader()`, `BuildPills()`, `BuildTabBar()`, `BuildPanel()`, `UpdatePanel()`, `RefreshFeed()`, `RefreshLog()` — verb-object (PascalCase, private)
- **Helpers:** `DrawGauge()`, `DrawLevels()`, `MakeSigLabel()`, `PushFeed()`, `ChkSpoof()`, `LvPx()`, `Std()`, `FV()`, `FC()`, `FindGrid()`, `Lbl()`, `Pill()`, `HC()`, `SBar()`, `SH()`, `SR()`, `HR()`, `SBr()`, `SD()` — verb-object or abbreviation (camelCase, private helpers)

**Fields:**

- **Engines:** `_fpSc`, `_fpDir`, `_trSc`, `_trDir`, `_spSc`, `_icSc`, `_icDir`, `_miSc`, `_miDir`, `_vpSc`, `_dexFired`, `_dexDir`, `_mlSc` — leading underscore, 2-3 letter abbreviation + descriptor (camelCase, private)
- **Session:** `_vwap`, `_vsd`, `_vah`, `_val`, `_ibH`, `_ibL`, `_ibTyp`, `_ibDone`, `_ibConf`, `_dayTyp`, `_pocMB`, `_pocMU`, `_cvd`, `_dPoc`, `_pPoc`, `_sOpen`, `_oPx`, `_iHi`, `_iLo` — leading underscore, 3–5 letter abbreviations (camelCase)
- **DOM/Queues:** `_bV[]`, `_aV[]`, `_bP[]`, `_aP[]`, `_dQ`, `_iLong`, `_iShort`, `_pLg`, `_pTr`, `_mlH`, `_feed`, `_emaVol`, `_emaRng`, `_pUp`, `_w1` — leading underscore, cryptic abbreviations (performance-critical)
- **Kalman:** `_kSt[]`, `_kP[,]`, `_kVel` — leading underscore, K-prefix (PascalCase suffix)
- **WPF Controls:** `_hBdr`, `_hPrc`, `_hPct`, `_hDT`, `_hIBT`, `_hGR`, `_hVZ`, `_hSP`, `_hTR`, `_hCV`, `_domDot`, `_pbFP`, `_ptFP`, `_dFP`, `_vFP`, `_gauge`, `_lblST`, `_lblSD`, `_feedPnl`, `_gexPnl`, `_lvlPnl`, `_logPnl`, `_panelRoot`, `_tabBdr`, `_pBdr` — leading underscore, 2–3 letter prefix (_h header, _p pill, _d dot, _v value, _pb progressbar, etc.)
- **SharpDX:** `_dxG`, `_dxR`, `_dxGo`, `_dxW`, `_dxGr`, `_dxO`, `_dxT`, `_dxC`, `_dxP`, `_dxBg`, `_dxCB`, `_dxCS`, `_dxBd`, `_dwF`, `_fC`, `_fS`, `_fL`, `_dxOk` — leading underscore, DX-prefix + single letter (camelCase, color/font shortcuts)

**Constants:**

- `VER = "v1.0.0"` — version string (UPPER_SNAKE)
- `MX_FP = 25.0`, `MX_TR = 20.0`, etc. — engine max points (UPPER_SNAKE)
- `DDEPTH = 10` — DOM depth (UPPER_SNAKE)

**Properties (Parameters):**

- `AbsorbWickMin`, `AbsorbDeltaMax`, `ImbRatio`, `StkT1`, `StkT2`, `StkT3` — Engine-grouped, PascalCase (NinjaScript convention)
- `DomDepth`, `Lambda`, `LBeta`, `TressEma`, `SpooLong`, `SpooShort`, etc.
- `GexReg`, `IbMins`, `DexLB`, `TypeAMin`, `TypeBMin`, `MinAgree` — abbreviated property names
- Show* display toggles: `ShowFp`, `ShowDelta`, `ShowStk`, `ShowLvls`, `ShowSigBox`, `ShowHeader`, `ShowPills`, `ShowPanel`

**Enums & Type Names:**

- `GexRegime`, `DayType`, `IbType`, `SignalType`, `VwapZone` — PascalCase nouns
- Enum values: `NegativeAmplifying`, `TrendBull`, `TypeA` — PascalCase

## Region Organization

`Indicators/DEEP6.cs` uses `#region` blocks for logical grouping:

```
#region Using declarations            (lines 1–22)
#region Enums                          (lines 49–55)
#region Constants                      (lines 59–68)
#region Parameters                     (lines 71–120)
#region Private Fields                 (lines 123–180)
#region OnStateChange                  (lines 183–229)
#region Event Handlers                 (lines 232–279)
#region Session Context                (lines 281–330)
#region E1 Footprint                   (lines 333–387)
#region E2 Trespass                    (lines 389–402)
#region E3 CounterSpoof                (lines 406–424)
#region E4 Iceberg                     (lines 427–442)
#region E5 Micro                       (lines 446–456)
#region E6 VP+CTX + DEX-ARRAY          (lines 460–480)
#region E7 ML Quality                  (lines 484–505)
#region Scorer                         (lines 509–526)
#region Chart Labels & Price Levels    (lines 529–569)
#region SharpDX Rendering              (lines 572–691)
#region WPF UI Construction            (lines 694–843)
#region Panel Update                   (lines 879–927)
#region WPF Helpers                    (lines 978–end)
```

## Where to Add New Code

**New Engine (Hypothetical E8):**

1. Add enum value to `GexRegime` (or create new enum if needed)
2. Add parameters in `#region Parameters` with `[NinjaScriptProperty]` and Display attributes (see E1–E6 pattern, line 71+)
3. Add private fields for engine state: `private double _e8Sc, _e8Dir; private string _e8St = "---";`
4. Add `#region E8 [Name]` region after E7 (lines 484+)
   - Implement `private void RunE8()` method
   - Populate `_e8Sc`, `_e8Dir`, `_e8St` based on algorithm
   - Max points constant: `private const double MX_E8 = ...;`
5. Call `RunE8()` from `OnBarUpdate()` line 238 (or `OnMarketDepth()` if tick-level)
6. Add `_e8Dir` to `dirs` array in `Scorer()` line 511
7. Add `_e8Sc` to raw score sum in `Scorer()` line 515
8. Add contribution check in `Scorer()` label logic (lines 519–524) if appropriate

**New UI Component:**

1. Add WPF field to `#region Private Fields` line 167+ (prefix `_h`, `_p`, `_d`, `_pb`, etc.)
2. Create in appropriate `BuildXxx()` method:
   - Header → `BuildHeader()` line 704 (construct label/value pair)
   - Pill → `BuildPills()` line 741 (use `Pill()` helper, specify color)
   - Right panel → `BuildPanel()` line 794 (add to appropriate StackPanel)
3. Update in `UpdatePanel()` line 879 (refresh data binding)
4. Use helper methods:
   - `Lbl()` for labels (line 978+)
   - `Pill()` for pill buttons (line 766)
   - `SBar()` for progress bars (line 825+)
   - `SR()` for status rows (line 832+)

**New Price Level Line:**

1. Add to `DrawLevels()` method (line 551+)
2. Use `HL()` lambda helper: `HL("id_key", "LABEL PRICE", price_value, WColor, DashStyle, width)`
3. Set ShowLvls = true in OnStateChange() defaults (line 209) or toggle via parameter

**New Signal Type or Feature:**

1. Add to enum if new type (e.g., `SignalType`)
2. Update `Scorer()` signal type logic (line 518) with new threshold
3. Add to signal label generation (lines 519–525) if contributing engine
4. Add to `MakeSigLabel()` rendering (line 530+) if new label variant needed
5. Test with `ShowSigBox = true` to verify rendering

## Special Directories

**.vscode/:**
- Purpose: Editor environment configuration
- Generated: No (committed to git)
- Committed: Yes (dev environment settings)

**tests/:**
- Purpose: Test specifications (future implementation)
- Generated: No (template-based)
- Committed: Yes (roadmap artifact)

**docs/:**
- Purpose: Design specifications and requirements
- Generated: No (hand-authored)
- Committed: Yes (design artifacts)

**.planning/ (hidden):**
- Purpose: Codebase analysis documents (generated by GSD mapper)
- Generated: Yes (on-demand via `/gsd-map-codebase` command)
- Committed: Depends on team preference (typically not committed, regenerated per session)

---

*Structure analysis: 2026-04-11*
