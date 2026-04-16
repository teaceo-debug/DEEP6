# DEEP6 NinjaTrader 8 Setup Guide

## Prerequisites

- Windows 10/11 PC with NinjaTrader 8 installed (8.1.x)
- Rithmic data feed connected (via Apex or Lucid broker account)
- NQ futures contract (NQM6 or current front-month) in your market data subscription

---

## Step 1: Copy Files to NinjaTrader

Open File Explorer and navigate to your NinjaTrader custom folder:

```
%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\
```

Copy these folders from the repo:

| From (repo)                                    | To (NT8)                              |
|------------------------------------------------|---------------------------------------|
| `ninjatrader/Custom/Indicators/DEEP6/`         | `Custom/Indicators/DEEP6/`            |
| `ninjatrader/Custom/Strategies/DEEP6/`         | `Custom/Strategies/DEEP6/`            |
| `ninjatrader/Custom/AddOns/DEEP6/`             | `Custom/AddOns/DEEP6/`                |

You should end up with:

```
Documents\NinjaTrader 8\bin\Custom\
  AddOns\DEEP6\
    Registry\          (ISignalDetector, DetectorRegistry, SessionContext, etc.)
    Scoring\           (ConfluenceScorer, ScorerEntryGate, ZoneScoreCalculator, etc.)
    Detectors\         (Absorption/, Exhaustion/, Imbalance/, Delta/, Auction/, Trap/, VolPattern/, Engine/)
    Levels\            (ProfileAnchorLevels)
    Math\              (LeastSquares, Wasserstein)
  Indicators\DEEP6\
    DEEP6Footprint.cs  (footprint chart + scoring HUD + profile anchors)
    DEEP6GexLevels.cs  (optional — standalone GEX overlay)
  Strategies\DEEP6\
    DEEP6Strategy.cs   (auto-trader)
```

Do NOT copy `ninjatrader/tests/` — that's the macOS test project, not NT8 code.

---

## Step 2: Compile in NinjaTrader

1. Open NinjaTrader 8
2. Go to **Tools > NinjaScript Editor**
3. Press **F5** (or click the compile button)
4. Wait for compilation — should see **"0 errors"** in the output panel
5. If you see errors, check the Output tab — most common issues:
   - Missing file: verify all folders copied correctly
   - Namespace error: verify the folder structure matches exactly

---

## Step 3: Add DEEP6Footprint Indicator to Chart

1. Open a chart: **NQ** (front-month), **1 Minute** timeframe
2. Right-click chart > **Indicators...**
3. Find **DEEP6Footprint** under the DEEP6 category
4. Click **Add**
5. Configure these properties (leave others at default):

| Property | Value | Group |
|----------|-------|-------|
| ShowFootprintCells | True | 2. Profile |
| ShowPoc | True | 2. Profile |
| ShowValueArea | True | 2. Profile |
| ShowAbsorptionMarkers | True | 3. Signals |
| ShowExhaustionMarkers | True | 3. Signals |
| ShowProfileAnchors | True | 4. Levels |
| ShowPriorDayLevels | True | 4. Levels |
| ShowNakedPocs | True | 4. Levels |
| ShowLiquidityWalls | True | 4. Levels |
| ShowScoreHud | True | 5. Score |

6. Click **OK**
7. You should see footprint cells rendering on each bar with bid x ask volume

### Optional: Add DEEP6GexLevels

If you want GEX overlay (gamma-flip, call/put walls):
1. Right-click chart > **Indicators...** > find **DEEP6GexLevels**
2. Set `GexApiKey` to your massive.com API key (from `.env` file: `MASSIVE_API_KEY`)
3. Set `GexUnderlying` to `QQQ`
4. Click **OK** — GEX levels appear as colored horizontal lines

---

## Step 4: Create ATM Bracket Template

The strategy uses an ATM template called **DEEP6_Confluence** for order management.

1. Open **Tools > ATM Strategy Parameters** (or click the ATM dropdown on ChartTrader)
2. Click **New** to create a new template
3. Name it: `DEEP6_Confluence`
4. Configure:

```
Stop Loss:
  Type:          Ticks
  Value:         20
  
Target 1 (scale-out):
  Type:          Ticks
  Value:         16
  Quantity:      50%    (half position exits here)

Target 2 (final):
  Type:          Ticks
  Value:         32
  Quantity:      50%    (remaining position exits here)

Breakeven:
  Trigger:       10 ticks in profit
  Offset:        +2 ticks (locks 2 ticks of profit)
```

5. Click **Save**

---

## Step 5: Add DEEP6Strategy (Paper Trading Mode)

1. Right-click chart > **Strategies...**
2. Find **DEEP6Strategy** under DEEP6
3. Click **Add**
4. Configure these critical properties:

### Group 1: Safety (MOST IMPORTANT)

| Property | Value | Notes |
|----------|-------|-------|
| **EnableLiveTrading** | **FALSE** | CRITICAL — keeps you in dry-run mode |
| ApprovedAccountName | `Sim101` | Your sim account name (check Account tab) |
| MaxContractsPerTrade | 2 | For scale-out (1 exits at T1, 1 at T2) |
| MaxTradesPerSession | 5 | Conservative limit |
| DailyLossCapDollars | 500 | Locks out after $500 loss |
| NewsBlackoutMinutes | `825,1000,1400` | Fed minutes, CPI, etc. |

### Group 2: Entry

| Property | Value |
|----------|-------|
| ScoreEntryThreshold | 70.0 |
| MinTierForEntry | TYPE_B |
| StrictDirectionEnabled | True |
| BlackoutWindowStart | 1530 |
| BlackoutWindowEnd | 1600 |

### Group 3: Exit

| Property | Value |
|----------|-------|
| StopLossTicks | 20 |
| ScaleOutEnabled | True |
| ScaleOutPercent | 0.5 |
| ScaleOutTargetTicks | 16 |
| TargetTicks | 32 |
| BreakevenEnabled | True |
| BreakevenActivationTicks | 10 |
| MaxBarsInTrade | 60 |

### Group 4: Filters

| Property | Value |
|----------|-------|
| VolSurgeVetoEnabled | True |
| SlowGrindVetoEnabled | True |
| SlowGrindAtrRatio | 0.5 |

### Group 5: Score

| Property | Value |
|----------|-------|
| UseNewRegistry | True |
| AtmTemplateName | DEEP6_Confluence |

5. Click **OK**
6. The strategy starts in **DRY RUN** mode — you'll see signals in the Output window but NO orders are placed

---

## Step 6: Verify It's Working

### Check the Output Window (Ctrl+O)

You should see lines like:

```
[DEEP6 Strategy] UseNewRegistry=true: Waves 1-5 detectors registered
[DEEP6 Strategy] Initialized. EnableLiveTrading=False, Account=Sim101
[DEEP6 Strategy] DRY RUN — no orders will be submitted.
```

On each bar close:
```
[DEEP6 Scorer] bar=42 score=+68.30 tier=TYPE_C narrative=
[DEEP6 Registry] IMB-03 dir=+1 str=0.85 | STACKED BUY x3 (T1) at 20045.00
[DEEP6 Registry] ABS-01 dir=+1 str=0.72 | CLASSIC absorption upper wick
```

When a trade would fire (dry-run):
```
[DEEP6 DRY RUN] LONG entry: score=+82.50, tier=TYPE_B, narrative=ABSORBED @VAL + STACKED IMB T1
```

### Check the Chart

- **Footprint cells**: bid x ask numbers inside each bar
- **POC**: yellow horizontal stripe at the highest-volume price level
- **VAH/VAL**: olive horizontal lines bracketing the value area
- **Profile anchors**: right-side labels (PDH, PDL, PDM, PD POC, PD VAH, PD VAL, nPOC)
- **Signal markers**: teal triangles (absorption), orange outlines (exhaustion)
- **Scoring HUD**: top-right box showing Score / Tier / Narrative (appears when signals fire)
- **Tier markers**: diamonds (TypeA), triangles (TypeB), dots (TypeC) at entry prices

---

## Step 7: Record Live Sessions for Backtesting

The capture harness records OnMarketData + OnMarketDepth events to NDJSON:

1. In the NinjaScript Output window, look for capture lines:
   ```
   [DEEP6 Capture] Writing to captures/2026-04-16-session.ndjson
   ```
2. Sessions are saved to `Documents\NinjaTrader 8\bin\Custom\captures\`
3. After each RTH session, copy the `.ndjson` file to your repo:
   ```
   ninjatrader/captures/2026-04-16-session.ndjson
   ```
4. Once you have 20+ sessions, re-run the optimizer on real data:
   ```bash
   python3 -m deep6.backtest.vbt_harness --mode sweep \
     --sessions-dir ninjatrader/captures/ \
     --output-dir ninjatrader/backtests/results-live/
   ```

---

## Step 8: Paper Trading (Phase 19)

After 5+ sessions of dry-run observation with no errors:

1. Change `ApprovedAccountName` to your Apex sim account name (e.g., `APEX-262674-SIM`)
2. Verify `EnableLiveTrading` is still **FALSE**
3. Change `EnableLiveTrading` to **TRUE**
4. The strategy now submits real paper orders via the ATM bracket template
5. Monitor for 30 consecutive RTH sessions

### Go/No-Go Thresholds (from PRE-LIVE-CHECKLIST.md)

| Metric | Minimum | Action if below |
|--------|---------|-----------------|
| Win Rate | >= 75% | Do NOT go live — re-optimize |
| Profit Factor | >= 2.0 | Do NOT go live — re-optimize |
| Max Drawdown | < $1,000 | Acceptable |
| Sessions without crash | 30 consecutive | Required |
| All risk gates fired at least once | Yes | Required |

---

## Troubleshooting

### "0 trades firing"
- Check Output window for `[DEEP6 Scorer]` lines — is the score reaching 70+?
- Lower `ScoreEntryThreshold` to 50 temporarily to see if signals exist
- Verify `UseNewRegistry = True` (not False)
- Check `ApprovedAccountName` matches your actual account name exactly

### "Compile errors"
- Verify folder structure matches Step 1 exactly
- Check for duplicate files (no old DEEP6 files in the folder)
- Press F5 again after fixing — NT8 caches compile state

### "Footprint cells not showing"
- Chart must be 1-minute timeframe (or tick-based)
- `Calculate` must be `OnBarClose` (set automatically)
- Verify `ShowFootprintCells = True` in indicator properties

### "GEX levels not appearing"
- DEEP6GexLevels is a SEPARATE indicator — add it alongside DEEP6Footprint
- Check `GexApiKey` is set (get from massive.com dashboard)
- Check Output window for `[GEX]` status messages

---

## File Reference

| File | Purpose |
|------|---------|
| `DEEP6Footprint.cs` | Main indicator — footprint, scoring HUD, profile anchors, tier markers |
| `DEEP6GexLevels.cs` | Optional standalone GEX overlay (gamma flip, call/put walls) |
| `DEEP6Strategy.cs` | Auto-trader — scorer-driven entries, ATM brackets, risk gates |
| `AddOns/DEEP6/Registry/` | Signal detection framework (44 detectors) |
| `AddOns/DEEP6/Scoring/` | Confluence scorer + entry gate + zone calculator |
| `AddOns/DEEP6/Detectors/` | 7 detector families (ABS/EXH/IMB/DELT/AUCT/TRAP/VOLP/ENG) |
| `AddOns/DEEP6/Levels/` | Profile anchor levels (PDH/PDL/POC/VAH/VAL/naked POCs) |
| `AddOns/DEEP6/Math/` | LeastSquares + Wasserstein (zero-dependency math utils) |

---

*Setup guide for DEEP6 v2.0 — NinjaScript Edition*
*Generated: 2026-04-16*
*Config: R3 Final (3 optimization rounds, 290 NUnit tests, 12 NT8 audit fixes)*
