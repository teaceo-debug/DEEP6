# DEEP6 Complete Installation — Give This to an AI

## What This Is

You are installing DEEP6 — an automated NQ futures trading system — on a fresh Windows machine with NinjaTrader 8. Follow every step in order. Do not skip anything. Do not improvise.

**Owner:** Michael Gonzalez (michael.gonzalez5@gmail.com)
**GitHub:** https://github.com/teaceo-debug/DEEP6.git

---

## Phase 1: Windows Machine Setup

### 1.1 Install Required Software

Open PowerShell as Administrator and run:

```powershell
# Install Git
winget install Git.Git --accept-package-agreements --accept-source-agreements

# Install Node.js (needed for Claude Code)
winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements

# Install Claude Code
npm install -g @anthropic-ai/claude-code

# Verify installs
git --version
node --version
claude --version
```

### 1.2 Install NinjaTrader 8

1. Download from: https://ninjatrader.com/Download
2. Run the installer — accept all defaults
3. Launch NinjaTrader 8
4. Login with your NT8 license key (or use the free sim license)
5. Close NinjaTrader after first launch (it creates the folder structure we need)

### 1.3 Connect Rithmic Data Feed

1. Open NinjaTrader 8
2. Go to **Connections > Configure...**
3. Click **Add**
4. Select **Rithmic** as the provider
5. Enter your credentials:
   - For Apex: use your Apex Rithmic credentials
   - For Lucid: use your Lucid Rithmic credentials
   - Server: select your broker's Rithmic gateway
6. Click **Connect**
7. Verify: the Connection Status light turns green
8. Verify: open a chart with NQ (front-month) — you should see live price data

---

## Phase 2: Deploy DEEP6 Code

### 2.1 Clone the Repository

Open PowerShell (regular, not Admin):

```powershell
cd $env:USERPROFILE
git clone https://github.com/teaceo-debug/DEEP6.git
cd DEEP6
```

### 2.2 Copy Files to NinjaTrader

```powershell
$source = "$env:USERPROFILE\DEEP6\ninjatrader\Custom"
$dest = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"

# Verify NT8 directory exists
if (!(Test-Path $dest)) {
    Write-Host "ERROR: NinjaTrader Custom directory not found at $dest"
    Write-Host "Make sure NinjaTrader 8 has been launched at least once."
    exit 1
}

# Copy AddOns (44 signal detectors + scoring + math + levels)
xcopy "$source\AddOns\DEEP6" "$dest\AddOns\DEEP6\" /E /I /Y

# Copy Indicators (footprint chart + GEX overlay)
xcopy "$source\Indicators\DEEP6" "$dest\Indicators\DEEP6\" /E /I /Y

# Copy Strategies (auto-trader)
xcopy "$source\Strategies\DEEP6" "$dest\Strategies\DEEP6\" /E /I /Y

# Verify file count
$total = (Get-ChildItem "$dest\AddOns\DEEP6","$dest\Indicators\DEEP6","$dest\Strategies\DEEP6" -Recurse -Filter *.cs | Measure-Object).Count
Write-Host "Deployed $total .cs files to NinjaTrader"
Write-Host "Expected: ~40+ files. If significantly less, re-check the copy."
```

### 2.3 Compile in NinjaTrader

1. Open NinjaTrader 8 (or switch to it if already open)
2. Go to **Tools > NinjaScript Editor**
3. Press **F5** (compile button)
4. Wait for compilation to finish
5. Check the Output panel at the bottom

**Expected result:** `0 errors`

**If you see errors:** Read Phase 4 (Troubleshooting) below. The most common issue is missing files — re-run the xcopy commands.

---

## Phase 3: Configure DEEP6

### 3.1 Create ATM Bracket Template

This template controls how orders are managed (stop loss, targets, scale-out).

1. In NinjaTrader, open any NQ chart
2. On the right side, find the **ChartTrader** panel (or press Ctrl+T)
3. Click the **ATM Strategy** dropdown > **<Custom...>**
4. Click **New** (or the + icon)
5. Set the template name to exactly: `DEEP6_Confluence`
6. Configure:

```
Stop Loss Strategy:
  Stop 1:
    Type:          Ticks
    Ticks:         20
    Auto Breakeven:
      Profit trigger: 10 ticks
      Plus:          2 ticks

Target Strategy:
  Target 1:
    Type:          Ticks
    Ticks:         16
    Quantity:      50%

  Target 2:
    Type:          Ticks
    Ticks:         32
    Quantity:      50%
```

7. Click **Save** (or the disk icon)
8. Verify the template appears in the ATM dropdown as `DEEP6_Confluence`

### 3.2 Add DEEP6Footprint Indicator

1. Open a chart: **Instrument = NQ** (front-month, e.g., NQ 06-26), **Period = 1 Minute**
2. Right-click on the chart > **Indicators...**
3. In the search box, type `DEEP6`
4. Select **DEEP6Footprint** > click **Add** (or double-click)
5. In the properties panel on the right, set:

```
--- Group: 2. Profile ---
ShowFootprintCells     = True
ShowPoc                = True
ShowValueArea          = True
CellColumnWidth        = 60
CellFontSize           = 9

--- Group: 3. Signals ---
ShowAbsorptionMarkers  = True
ShowExhaustionMarkers  = True

--- Group: 4. Levels ---
ShowProfileAnchors     = True
ShowPriorDayLevels     = True
ShowNakedPocs          = True
ShowCompositeVA        = False
ShowLiquidityWalls     = True
LiquidityWallMin       = 200
LiquidityWallStaleSec  = 60
LiquidityMaxPerSide    = 4

--- Group: 5. Score ---
ShowScoreHud           = True
ScoreHudPaddingPx      = 12
```

6. Click **OK**
7. Verify: you should see bid×ask volume numbers inside each bar, a gold POC line, olive VAH/VAL lines, and right-side labels (PDH, PDL, PD POC, etc.)

### 3.3 Add DEEP6GexLevels Indicator (Optional)

Only if GEX overlay (options gamma levels) is wanted:

1. Right-click chart > **Indicators...** > search `DEEP6GexLevels` > **Add**
2. Set:
```
ShowGexLevels   = True
GexUnderlying   = QQQ
GexApiKey        = (your massive.com API key)
```
3. Click **OK**
4. Verify: colored horizontal lines appear (gamma flip = yellow, call wall = green, put wall = red)

### 3.4 Add DEEP6Strategy (DRY RUN MODE)

**CRITICAL: Start in dry-run mode. Do NOT enable live trading until paper-trade validation is complete.**

1. Right-click chart > **Strategies...**
2. Search `DEEP6` > select **DEEP6Strategy** > **Add**
3. Set ALL of these properties exactly:

```
--- Group: 1. Safety ---
EnableLiveTrading        = False        ← MANDATORY: dry-run first
ApprovedAccountName      = Sim101       ← must match your sim account name exactly
MaxContractsPerTrade     = 2
MaxTradesPerSession      = 5
DailyLossCapDollars      = 500
NewsBlackoutMinutes      = 825,1000,1400
RthStartHour             = 9
RthStartMinute           = 35
RthEndHour               = 15
RthEndMinute             = 50

--- Group: 2. Entry ---
ScoreEntryThreshold      = 70.0
MinTierForEntry          = TYPE_B
StrictDirectionEnabled   = True
BlackoutWindowStart      = 1530
BlackoutWindowEnd        = 1600

--- Group: 3. Exit ---
StopLossTicks            = 20
ScaleOutEnabled          = True
ScaleOutPercent          = 0.5
ScaleOutTargetTicks      = 16
TargetTicks              = 32
BreakevenEnabled         = True
BreakevenActivationTicks = 10
BreakevenOffsetTicks     = 2
MaxBarsInTrade           = 60
ExitOnOpposingScore      = 0.3

--- Group: 4. Filters ---
VolSurgeVetoEnabled      = True
SlowGrindVetoEnabled     = True
SlowGrindAtrRatio        = 0.5

--- Group: 5. Score ---
UseNewRegistry           = True
AtmTemplateName          = DEEP6_Confluence

--- Group: DEEP6 Migration ---
UseNewRegistry           = True
```

4. Click **OK**
5. If asked to enable the strategy, click **Yes**

### 3.5 Verify Everything Is Working

Open the **Output** window: press **Ctrl+O** or go to **New > Output**

You should see these lines appear:

```
[DEEP6 Strategy] UseNewRegistry=true: Waves 1-5 detectors registered (ABS/EXH/IMB/DELT/AUCT/VOLP/TRAP + ENG-02..07).
[DEEP6 Strategy] Initialized. EnableLiveTrading=False, Account=Sim101, ApprovedAccount=Sim101
[DEEP6 Strategy] DRY RUN — no orders will be submitted.
```

On each 1-minute bar close, you should see:
```
[DEEP6 Scorer] bar=42 score=+68.30 tier=TYPE_C narrative=
```

When a high-conviction setup appears:
```
[DEEP6 DRY RUN] LONG entry: score=+82.50, tier=TYPE_B, narrative=ABSORBED @VAL + STACKED IMB T1
```

### 3.6 Visual Verification Checklist

Look at the chart and confirm each element:

- [ ] **Footprint cells**: bid × ask numbers visible inside each bar
- [ ] **POC**: yellow horizontal stripe at the highest-volume price in each bar
- [ ] **VAH/VAL**: olive horizontal lines above and below the main volume area
- [ ] **Profile anchors**: right-side labels — PDH, PDL, PDM, PD POC, PD VAH, PD VAL
- [ ] **Naked POCs**: dotted/dimmed horizontal lines from prior sessions (if any exist)
- [ ] **Liquidity walls**: blue (bid) and orange (ask) horizontal lines at large L2 orders
- [ ] **Signal markers**: teal filled triangles (absorption) and orange outline triangles (exhaustion) near bar extremes
- [ ] **Scoring HUD**: top-right box showing Score / Tier when signals fire (empty when quiet)
- [ ] **ChartTrader toolbar**: row of toggle buttons top-left (Cells, POC, VA, IMB, ABS, EXH, Tiers, Walls, Levels, HUD)

---

## Phase 4: Troubleshooting

### Compile Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `CS0246: type or namespace not found` | Missing .cs file | Re-run xcopy commands; verify AddOns/DEEP6/ has all subdirectories (Registry, Scoring, Detectors, Levels, Math) |
| `CS0102: already contains a definition` | Duplicate file or old code | Delete ALL files in the three DEEP6 folders, re-copy from repo |
| `CS0535: does not implement interface` | Partial file copy | Re-copy the entire AddOns/DEEP6/ tree |
| Multiple errors mentioning `NinjaTrader.Tests` | BacktestRunner in wrong location | BacktestRunner.cs should be in `tests/Backtest/` NOT in `AddOns/DEEP6/Backtest/`. If it's in AddOns, delete it. |

### Runtime Issues

| Symptom | Check | Fix |
|---------|-------|-----|
| No footprint cells | Chart period | Must be 1-minute (or tick-based). 5-min and above won't show cells. |
| No signals in Output | UseNewRegistry | Must be True. Check strategy properties. |
| "Account not approved" | ApprovedAccountName | Must exactly match the account name shown in NT8's Account tab |
| Strategy not loading | Chart instrument | Strategy must be on an NQ chart with active Rithmic data |
| HUD not showing | ShowScoreHud | Must be True in indicator properties. Only shows when score > 0. |
| GEX levels missing | Separate indicator | DEEP6GexLevels is a different indicator — must be added separately |

### Nuclear Reset

If nothing works, start fresh:

```powershell
# Delete all DEEP6 files from NT8
$dest = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"
Remove-Item "$dest\AddOns\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\Indicators\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\Strategies\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue

# Re-clone and re-copy
cd $env:USERPROFILE
Remove-Item DEEP6 -Recurse -Force -ErrorAction SilentlyContinue
git clone https://github.com/teaceo-debug/DEEP6.git
cd DEEP6

$source = "ninjatrader\Custom"
xcopy "$source\AddOns\DEEP6" "$dest\AddOns\DEEP6\" /E /I /Y
xcopy "$source\Indicators\DEEP6" "$dest\Indicators\DEEP6\" /E /I /Y
xcopy "$source\Strategies\DEEP6" "$dest\Strategies\DEEP6\" /E /I /Y

# Open NT8, press F5
```

---

## Phase 5: Ongoing Operation

### Daily Routine

1. **Before market open (9:25 AM ET):** Verify NT8 is running, Rithmic connected, strategy loaded
2. **During RTH (9:30-4:00 ET):** Watch Output window for signals. DRY RUN mode — no orders placed.
3. **After close (4:15 PM ET):** Review signals that fired. Do they match setups you'd have taken manually?

### Recording Sessions for Backtesting

The capture harness records tick data to NDJSON files:
```
Documents\NinjaTrader 8\bin\Custom\captures\2026-04-17-session.ndjson
```

Copy these back to the repo for analysis:
```powershell
copy "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\captures\*.ndjson" "$env:USERPROFILE\DEEP6\ninjatrader\captures\"
cd $env:USERPROFILE\DEEP6
git add ninjatrader/captures/
git commit -m "data: live session capture $(Get-Date -Format 'yyyy-MM-dd')"
git push origin main
```

### Enabling Paper Trading (After 5+ Dry-Run Sessions)

1. Verify: 5 sessions of clean dry-run output, no crashes, signals look sensible
2. Change `ApprovedAccountName` to your sim account name
3. Change `EnableLiveTrading` to **True**
4. Strategy now submits real paper orders via the ATM bracket template
5. Monitor for 30 consecutive sessions before considering live capital

### Go/No-Go Thresholds for Live Capital

| Metric | Minimum Required |
|--------|-----------------|
| Win Rate | >= 75% |
| Profit Factor | >= 2.0 |
| Max Drawdown | < $1,000 |
| Consecutive clean sessions | 30 |
| All risk gates fired at least once | Yes |

---

## File Inventory

After successful deployment, your NT8 Custom directory should contain:

```
Documents\NinjaTrader 8\bin\Custom\
├── AddOns\DEEP6\
│   ├── Registry\
│   │   ├── ISignalDetector.cs
│   │   ├── DetectorRegistry.cs
│   │   ├── SessionContext.cs
│   │   ├── SignalResult.cs
│   │   ├── SignalFlagBits.cs
│   │   └── FootprintBar.cs
│   ├── Scoring\
│   │   ├── ConfluenceScorer.cs
│   │   ├── NarrativeCascade.cs
│   │   ├── ScorerResult.cs
│   │   ├── ScorerEntryGate.cs
│   │   ├── ScorerSharedState.cs
│   │   └── ZoneScoreCalculator.cs
│   ├── Detectors\
│   │   ├── Absorption\AbsorptionDetector.cs
│   │   ├── Exhaustion\ExhaustionDetector.cs
│   │   ├── Imbalance\ImbalanceDetector.cs
│   │   ├── Delta\DeltaDetector.cs
│   │   ├── Auction\AuctionDetector.cs
│   │   ├── Trap\TrapDetector.cs
│   │   ├── VolPattern\VolPatternDetector.cs
│   │   └── Engine\
│   │       ├── TrespassDetector.cs
│   │       ├── CounterSpoofDetector.cs
│   │       ├── IcebergDetector.cs
│   │       ├── MicroProbDetector.cs
│   │       ├── VPContextDetector.cs
│   │       └── SignalConfigScaffold.cs
│   ├── Levels\
│   │   └── ProfileAnchorLevels.cs
│   └── Math\
│       ├── LeastSquares.cs
│       └── Wasserstein.cs
├── Indicators\DEEP6\
│   ├── DEEP6Footprint.cs
│   └── DEEP6GexLevels.cs
└── Strategies\DEEP6\
    └── DEEP6Strategy.cs
```

Total: ~35-40 .cs files. If your count is significantly different, something is missing.

---

*DEEP6 Complete Installation Guide — v1.0*
*Give this entire document to an AI and say "install this"*
*System: 44 signal detectors, R3-optimized scorer, production config locked*
