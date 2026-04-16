# DEEP6 Windows Setup — AI Handoff Document

**Owner:** Michael Gonzalez (michael.gonzalez5@gmail.com)
**Date:** 2026-04-16
**Purpose:** Set up NinjaTrader 8 on Windows with all DEEP6 files + Data Bridge for the macOS simulator

---

## What This Does

The macOS machine has a NinjaScript simulator that can validate, backtest, optimize, and visualize the DEEP6 trading strategy — but it needs live market data from NinjaTrader 8 running on this Windows machine. This setup installs all DEEP6 files in NT8 and activates the Data Bridge that pipes live NQ data to the Mac.

## Prerequisites

- NinjaTrader 8 installed and licensed
- Connected to a funded account (Apex APEX-262674 or Lucid LT-45N3KIV8)
- NQ chart open with market data subscription active
- Network: Mac and Windows on the same network (or use SSH tunnel)

---

## Step 1: Locate the DEEP6 Repository

The repo should be cloned or available at a known path. If not cloned yet:

```powershell
cd $HOME\Documents
git clone https://github.com/teaceo-debug/DEEP6.git
```

Set the repo path variable for the rest of the instructions:

```powershell
$REPO = "$HOME\Documents\DEEP6"
```

## Step 2: Copy All DEEP6 Files to NinjaTrader 8

NT8 custom files live at: `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\`

```powershell
$NT8_CUSTOM = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"

# ── Indicators ──
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\Indicators\DEEP6"
Copy-Item "$REPO\ninjatrader\Custom\Indicators\DEEP6\DEEP6Footprint.cs" "$NT8_CUSTOM\Indicators\DEEP6\" -Force
Copy-Item "$REPO\ninjatrader\Custom\Indicators\DEEP6\DEEP6GexLevels.cs" "$NT8_CUSTOM\Indicators\DEEP6\" -Force
Copy-Item "$REPO\ninjatrader\Custom\Indicators\DEEP6\CaptureHarness.cs" "$NT8_CUSTOM\Indicators\DEEP6\" -Force
Copy-Item "$REPO\ninjatrader\Custom\Indicators\DEEP6\DataBridgeIndicator.cs" "$NT8_CUSTOM\Indicators\DEEP6\" -Force

# ── Strategies ──
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\Strategies\DEEP6"
Copy-Item "$REPO\ninjatrader\Custom\Strategies\DEEP6\DEEP6Strategy.cs" "$NT8_CUSTOM\Strategies\DEEP6\" -Force

# ── AddOns (Detectors, Registry, Scoring, Math, Levels, Bridge) ──
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Registry"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Levels"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Math"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Scoring"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Bridge"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Absorption"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Exhaustion"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Imbalance"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Delta"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Auction"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\VolPattern"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Trap"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Engines"
New-Item -ItemType Directory -Force -Path "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Legacy"

# IMPORTANT: Exclude FootprintBar.cs — it's test-only and duplicates types in DEEP6Footprint.cs
Get-ChildItem "$REPO\ninjatrader\Custom\AddOns\DEEP6\Registry\*.cs" | Where-Object { $_.Name -ne "FootprintBar.cs" } | Copy-Item -Destination "$NT8_CUSTOM\AddOns\DEEP6\Registry\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Levels\*" "$NT8_CUSTOM\AddOns\DEEP6\Levels\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Math\*" "$NT8_CUSTOM\AddOns\DEEP6\Math\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Scoring\*" "$NT8_CUSTOM\AddOns\DEEP6\Scoring\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Bridge\*" "$NT8_CUSTOM\AddOns\DEEP6\Bridge\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Absorption\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Absorption\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Exhaustion\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Exhaustion\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Imbalance\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Imbalance\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Delta\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Delta\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Auction\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Auction\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\VolPattern\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\VolPattern\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Trap\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Trap\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Engines\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Engines\" -Force
Copy-Item "$REPO\ninjatrader\Custom\AddOns\DEEP6\Detectors\Legacy\*" "$NT8_CUSTOM\AddOns\DEEP6\Detectors\Legacy\" -Force
```

## Step 3: Compile in NinjaTrader

1. Open NinjaTrader 8
2. Go to **Tools → NinjaScript Editor** (or press Ctrl+Shift+N in older versions)
3. Press **F5** to compile all NinjaScript files
4. Expected result: **0 errors**
5. If errors appear, check the Output Window — the `ninjascript-error-surgeon-v2.md` in the repo's `dashboard/agents/` has fixes for every known error

### Common Compile Issues

| Error | Fix |
|-------|-----|
| `CS0101: duplicate type 'Cell'` | The `#if !NINJASCRIPT_SIM` guards should prevent this. If it fires, the DEEP6Footprint.cs copy is outdated — re-copy from repo |
| `CS0246: type not found` | Missing AddOn files — verify all Detectors/ subdirectories were copied |
| `CS0234: 'Math' namespace` | The `System.Math.Max` fix should be in the latest files — re-copy from repo |

## Step 4: Create ATM Templates

In NinjaTrader 8, create three ATM bracket templates:

### Template: DEEP6_Absorption
1. Right-click on Chart Trader panel → **ATM Strategy** → **Custom...**
2. Set:
   - **Name:** DEEP6_Absorption
   - **Quantity:** 1
   - **Stop Loss:** 20 ticks
   - **Profit Target:** 32 ticks
3. Save

### Template: DEEP6_Exhaustion
1. Same process
2. Set:
   - **Name:** DEEP6_Exhaustion
   - **Quantity:** 1
   - **Stop Loss:** 20 ticks
   - **Profit Target:** 32 ticks
3. Save

### Template: DEEP6_Confluence (Scale-Out)
1. Same process
2. Set:
   - **Name:** DEEP6_Confluence
   - **Quantity:** 2
   - **Stop Loss:** 20 ticks
   - **Profit Target 1:** 16 ticks (1 contract — 50% scale out at T1)
   - **Profit Target 2:** 32 ticks (1 contract — remainder runs to T2)
3. Save

### Template: DEEP6_Practice
1. Same process
2. Set:
   - **Name:** DEEP6_Practice
   - **Quantity:** 1
   - **Stop Loss:** 20 ticks
   - **Profit Target:** 32 ticks
3. Save

## Step 5: Add Indicators to NQ Chart

### 5a. Open an NQ Chart
- **Instrument:** NQ 06-26 (front month)
- **Period:** 1 minute
- **Data type:** Last (with tick replay if available)

### 5b. Add DEEP6 Footprint Indicator
1. Right-click chart → **Indicators...**
2. Find **DEEP6Footprint** in the list
3. Configure defaults (all should be pre-set):
   - Imbalance Ratio: 3.0
   - Show Footprint Cells: True
   - Show Absorption/Exhaustion Markers: True
   - Show POC / Value Area: True
   - Show Profile Anchors: True
   - Show Liquidity Walls: True
   - Show Score HUD: True
4. Click **OK**

### 5c. Add DEEP6 DataBridge Indicator
1. Right-click chart → **Indicators...**
2. Find **DEEP6 DataBridge** in the list
3. Configure:
   - **Bridge Port:** 9200 (default)
4. Click **OK**
5. Check the NT8 Output Window — you should see:
   ```
   [DEEP6 Bridge] Server started on port 9200. Waiting for simulator connection...
   ```

### 5d. (Optional) Add DEEP6 Strategy for Dry-Run Testing
1. Right-click chart → **Strategies...**
2. Find **DEEP6 Strategy**
3. Configure:
   - **Enable Live Trading:** False (DRY RUN — no real orders)
   - **Approved Account Name:** Sim101
   - **UseNewRegistry:** True
   - All other defaults are production-ready (Phase 18 R1/R2 locked config)
4. Click **OK**

## Step 6: Open Firewall for Data Bridge

The Data Bridge runs on TCP port 9200. If the Mac is on the same network:

```powershell
# Allow inbound TCP on port 9200 (run as Administrator)
netsh advfirewall firewall add rule name="DEEP6 DataBridge" dir=in action=allow protocol=TCP localport=9200
```

Find this machine's IP:
```powershell
ipconfig | findstr "IPv4"
```

Give the IP to the Mac. On the Mac, run:
```bash
dotnet run --project ninjatrader/simulator -- bridge <WINDOWS_IP>:9200
```

## Step 7: Verify the Bridge Connection

On the Mac, you should see:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 NinjaScript Simulator — NT8 Data Bridge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Connecting to <WINDOWS_IP>:9200...
  Connected! Receiving live data from NT8.
  Trades: 0  Depth: 0  Bars: 0
```

Once market data is flowing (during RTH 9:30-16:00 ET), the counters will start incrementing.

On the NT8 Output Window, you should see the bridge logging every bar close.

## Step 8: Record a Full Session

On the Mac, record an entire RTH session:
```bash
dotnet run --project ninjatrader/simulator -- bridge <WINDOWS_IP>:9200 --record rtb-2026-04-17.ndjson
```

Let it run from 9:30 AM to 4:00 PM ET. Press Ctrl+C when done.

Then run the full analytics pipeline:
```bash
# Backtest with trade journal + equity curve
dotnet run --project ninjatrader/simulator -- backtest rtb-2026-04-17.ndjson --trades trades.csv --equity equity.html

# Signal attribution
dotnet run --project ninjatrader/simulator -- signals rtb-2026-04-17.ndjson

# Footprint chart
dotnet run --project ninjatrader/simulator -- footprint rtb-2026-04-17.ndjson

# Design studio
dotnet run --project ninjatrader/simulator -- design rtb-2026-04-17.ndjson

# Open everything
open equity.html footprint.html design-studio.html
```

---

## File Inventory (what gets installed)

| Location | Files | Purpose |
|----------|-------|---------|
| `Indicators\DEEP6\` | DEEP6Footprint.cs, DEEP6GexLevels.cs, CaptureHarness.cs, DataBridgeIndicator.cs | Main indicator + GEX + capture + bridge |
| `Strategies\DEEP6\` | DEEP6Strategy.cs | Auto-trader (dry-run by default) |
| `AddOns\DEEP6\Registry\` | FootprintBar.cs, ISignalDetector.cs, DetectorRegistry.cs, SessionContext.cs, SignalResult.cs, SignalFlagBits.cs | Core types + signal interface |
| `AddOns\DEEP6\Scoring\` | ConfluenceScorer.cs, ScorerEntryGate.cs, ScorerResult.cs, NarrativeCascade.cs, ZoneScoreCalculator.cs, ScorerSharedState.cs | Confluence scoring engine |
| `AddOns\DEEP6\Detectors\` | 14 files across 9 subdirectories | All 44 signal detectors |
| `AddOns\DEEP6\Levels\` | ProfileAnchorLevels.cs | Prior-day POC/VAH/VAL, naked POCs |
| `AddOns\DEEP6\Math\` | LeastSquares.cs, Wasserstein.cs | Math utilities |
| `AddOns\DEEP6\Bridge\` | DataBridgeServer.cs | TCP server for simulator bridge |

**Total: ~34 production files, ~10,500 lines of NinjaScript C#**

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bridge not connecting | Firewall blocking port 9200 | Run the `netsh` command in Step 6 |
| Bridge connects but no data | Chart not receiving market data | Verify NQ chart shows live candles |
| Compile errors after F5 | Files out of date | Re-copy all files from repo (Step 2) |
| `rpCode=13` in Output | API mode not enabled (not relevant for bridge) | Bridge doesn't need API mode — it runs inside NT8 |
| Strategy says "DRY RUN" | EnableLiveTrading=False (correct default) | This is expected — change to True only when ready for live |
| No signals firing | Too few bars loaded | Wait for 20+ bars to accumulate (BarsRequiredToTrade=20) |

---

## Important Safety Notes

- **DEEP6Strategy defaults to DRY RUN** — no orders are submitted unless you explicitly set `EnableLiveTrading=True` AND `ApprovedAccountName` matches your account
- **Daily loss cap:** $500 per session (kill switch activates automatically)
- **Max trades:** 5 per session
- The bridge indicator is **invisible** — it has no chart rendering, just data forwarding
- The bridge only **reads** data from NT8 — it cannot place orders or modify anything
