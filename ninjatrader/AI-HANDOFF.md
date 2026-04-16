# DEEP6 NinjaTrader 8 — AI Agent Handoff Document

## What You're Setting Up

DEEP6 is a production-ready institutional-grade footprint chart auto-trading system for NQ (E-mini NASDAQ 100) futures running on NinjaTrader 8. It detects absorption and exhaustion reversal signals from Level 2 order flow data and auto-executes trades via ATM bracket orders.

**Owner:** Michael Gonzalez (michael.gonzalez5@gmail.com) — Peak Asset Performance LLC
**Trading accounts:** Apex (APEX-262674) + Lucid Trading (LT-45N3KIV8) — funded prop accounts
**Data feed:** Rithmic (via NT8's native connection)
**Instrument:** NQ futures only (front-month continuous)

---

## System Architecture

```
NinjaTrader 8 (.NET Framework 4.8)
├── DEEP6Footprint.cs          — Indicator: footprint chart + scoring HUD + tier markers + profile anchors
├── DEEP6GexLevels.cs          — Indicator: standalone GEX overlay (optional, separate from main)
├── DEEP6Strategy.cs           — Strategy: auto-trader with scorer-driven entries + ATM brackets
└── AddOns/DEEP6/
    ├── Registry/              — ISignalDetector interface + DetectorRegistry (44 signal detectors)
    ├── Detectors/             — 7 families: Absorption, Exhaustion, Imbalance, Delta, Auction, Trap, VolPattern + Engine
    ├── Scoring/               — ConfluenceScorer (two-layer), NarrativeCascade, ScorerEntryGate, ZoneScoreCalculator
    ├── Levels/                — ProfileAnchorLevels (PDH/PDL/PDM, PD POC, PD VAH/VAL, naked POCs, PW POC)
    └── Math/                  — LeastSquares + Wasserstein (zero-dependency math utilities)
```

**Signal flow:** OnMarketData (ticks) → FootprintBar accumulation → DetectorRegistry.EvaluateBar (44 detectors) → ConfluenceScorer.Score (two-layer confluence) → ScorerEntryGate.Evaluate (threshold + tier + vetoes) → ATM bracket order via DEEP6Strategy

---

## Step-by-Step Setup Instructions

### Prerequisites
- Windows 10/11 PC
- NinjaTrader 8 installed (8.1.x) with valid license
- Rithmic data feed connected (Apex or Lucid broker account)
- NQ futures in market data subscription

### 1. Get the Code

The repo is at: `https://github.com/teaceo-debug/DEEP6.git`

Clone it or download the ZIP. The NT8 files are under `ninjatrader/Custom/`.

### 2. Copy Files to NinjaTrader

Copy these three folders into the NT8 custom directory:

```
FROM: ninjatrader/Custom/Indicators/DEEP6/    → TO: %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\
FROM: ninjatrader/Custom/Strategies/DEEP6/    → TO: %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\DEEP6\
FROM: ninjatrader/Custom/AddOns/DEEP6/        → TO: %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\DEEP6\
```

Do NOT copy `ninjatrader/tests/` — that's the macOS test project.

### 3. Compile

1. Open NinjaTrader 8
2. Tools > NinjaScript Editor
3. Press F5 (compile)
4. Expected: **0 errors**

If compile fails, check:
- All three folder trees copied completely (AddOns has ~35 .cs files across 8 subdirectories)
- No duplicate old DEEP6 files in the Custom folder
- Folder names match exactly (case-sensitive on some NT8 versions)

### 4. Create ATM Bracket Template

Open Tools > ATM Strategy Parameters > New:

```
Template Name: DEEP6_Confluence

Stop Loss:
  Type:    Ticks
  Value:   20        ($100 on NQ at $5/tick)

Target 1:
  Type:    Ticks
  Value:   16        ($80 — 50% of position exits here)
  Qty:     50%

Target 2:
  Type:    Ticks
  Value:   32        ($160 — remaining 50% exits here)
  Qty:     50%

Breakeven:
  Trigger: 10 ticks profit
  Offset:  +2 ticks  (locks $10 profit per contract)
```

Save the template.

### 5. Add Indicator to Chart

1. Open chart: NQ front-month, 1-minute timeframe
2. Right-click > Indicators > find DEEP6Footprint > Add
3. Set these properties:

```
Group "2. Profile":
  ShowFootprintCells = True
  ShowPoc = True
  ShowValueArea = True
  CellColumnWidth = 60

Group "3. Signals":
  ShowAbsorptionMarkers = True
  ShowExhaustionMarkers = True

Group "4. Levels":
  ShowProfileAnchors = True
  ShowPriorDayLevels = True
  ShowNakedPocs = True
  ShowCompositeVA = False
  ShowLiquidityWalls = True

Group "5. Score":
  ShowScoreHud = True
```

4. Click OK — footprint chart renders

### 6. Add Strategy (DRY RUN FIRST)

Right-click chart > Strategies > find DEEP6Strategy > Add:

```
Group "1. Safety":
  EnableLiveTrading = FALSE          ← CRITICAL: start in dry-run
  ApprovedAccountName = Sim101       ← match your sim account exactly
  MaxContractsPerTrade = 2
  MaxTradesPerSession = 5
  DailyLossCapDollars = 500
  NewsBlackoutMinutes = 825,1000,1400

Group "2. Entry":
  ScoreEntryThreshold = 70.0
  MinTierForEntry = TYPE_B
  StrictDirectionEnabled = True
  BlackoutWindowStart = 1530
  BlackoutWindowEnd = 1600

Group "3. Exit":
  StopLossTicks = 20
  ScaleOutEnabled = True
  ScaleOutPercent = 0.5
  ScaleOutTargetTicks = 16
  TargetTicks = 32
  BreakevenEnabled = True
  BreakevenActivationTicks = 10
  MaxBarsInTrade = 60
  ExitOnOpposingScore = 0.3

Group "4. Filters":
  VolSurgeVetoEnabled = True
  SlowGrindVetoEnabled = True
  SlowGrindAtrRatio = 0.5

Group "5. Score":
  UseNewRegistry = True
  AtmTemplateName = DEEP6_Confluence
```

### 7. Verify

Open Output window (Ctrl+O). On strategy load you should see:

```
[DEEP6 Strategy] UseNewRegistry=true: Waves 1-5 detectors registered (ABS/EXH/IMB/DELT/AUCT/VOLP/TRAP + ENG-02..07).
[DEEP6 Strategy] Initialized. EnableLiveTrading=False, Account=Sim101, ApprovedAccount=Sim101
[DEEP6 Strategy] DRY RUN — no orders will be submitted.
```

On each bar close:
```
[DEEP6 Scorer] bar=N score=+XX.XX tier=TYPE_X narrative=...
```

When a trade would fire:
```
[DEEP6 DRY RUN] LONG entry: score=+82.50, tier=TYPE_B, narrative=ABSORBED @VAL + STACKED IMB T1
```

### 8. Optional: Add GEX Overlay

If GEX levels are wanted (separate indicator):
1. Right-click chart > Indicators > find DEEP6GexLevels > Add
2. Set GexApiKey = (the massive.com API key)
3. Set GexUnderlying = QQQ
4. OK — gamma flip, call/put walls render as colored horizontal lines

---

## Production Configuration Reference

These are the optimized values from 3 rounds of backtesting (50 synthetic sessions, 19,500 bars, walk-forward validated):

### Scorer Weights (locked in ConfluenceScorer.cs)

| Category | Weight | Notes |
|----------|--------|-------|
| absorption | 20.0 | Core thesis signal |
| exhaustion | 15.7 | Reversal confirmation |
| imbalance | 25.0 | Highest weight — IMB-03 stacked is load-bearing alpha |
| volume_profile | 20.2 | Zone proximity scoring |
| delta | 14.3 | Divergence confirmation |
| auction | 12.6 | Unfinished business / poor highs-lows |
| trapped | 0.0 | Zero contribution in backtest |
| engine/poc | 0.0 | Scaffold only |

### Key Signals (proven alpha)

| Signal | Role | Win Rate |
|--------|------|----------|
| ABS-01 (Classic Absorption) | Primary entry trigger | 77.8% |
| IMB-03 (Stacked Imbalance T1) | Required confluence partner | 81.2% combined |
| EXH-02 (Exhaustion Print) | Confirmation (regime-filtered) | 92.3% at strict threshold |

### Risk Management

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Contracts | 2 (scale-out) | 1 exits at T1, 1 at T2 |
| Daily loss cap | $500 | 4 full stops before lockout |
| Stop loss | 20 ticks ($100) | Robust to ±10% perturbation |
| Target 1 | 16 ticks ($80) @50% | Quick partial profit |
| Target 2 | 32 ticks ($160) @50% | Let winner run |
| Breakeven | Activate at MFE ≥ 10 ticks | Lock +$10 profit |
| VOLP-03 veto | Session-level block after volume surge | Prevents all volatile-regime losses |
| Slow-grind veto | Block when ATR < 0.5× session avg | 37% WR without this = bleeding |
| Time blackout | 1530-1600 ET | Low-edge close-of-day window |

---

## Troubleshooting Checklist

| Symptom | Check | Fix |
|---------|-------|-----|
| Compile errors | Missing files in AddOns/DEEP6/ subdirectories | Re-copy all folders; verify 35+ .cs files present |
| No footprint cells | Chart not 1-min; or ShowFootprintCells=False | Switch to 1-min NQ chart; enable property |
| No signals firing | UseNewRegistry=False; or no Rithmic data flowing | Set UseNewRegistry=True; verify Rithmic connection in Connection Center |
| Score always 0 | Scorer not invoked; or zoneScore not wired | Check Output for [DEEP6 Scorer] lines; verify indicator is on same chart as strategy |
| Strategy not trading | EnableLiveTrading=False (intended for dry-run) | Only flip to True after 30 paper sessions |
| "Account not approved" | ApprovedAccountName doesn't match exactly | Check Account tab for exact name string |
| ATM not creating | Template name mismatch | Verify DEEP6_Confluence template exists in ATM Strategy Parameters |
| GEX not showing | DEEP6GexLevels not added as separate indicator | Add it independently; set API key |

---

## Paper Trading → Live Checklist (abbreviated)

Full 84-item checklist at: `ninjatrader/backtests/results/round3/FINAL-PRE-LIVE-CHECKLIST.md`

**Must-pass before flipping EnableLiveTrading=True:**

- [ ] Strategy compiled with 0 errors on this Windows machine
- [ ] 5+ dry-run sessions with correct signals in Output (no crashes)
- [ ] ATM template DEEP6_Confluence created and tested manually
- [ ] ApprovedAccountName matches funded account (not sim)
- [ ] 30 consecutive paper-trade sessions completed
- [ ] Win rate ≥ 75% over those 30 sessions
- [ ] Profit factor ≥ 2.0
- [ ] All risk gates verified firing at least once (daily loss cap, news blackout, RTH window, max trades)
- [ ] DailyLossCapDollars = 500 confirmed in properties
- [ ] Written go/no-go decision committed to .planning/

---

## Repository Structure

```
DEEP6/
├── ninjatrader/
│   ├── Custom/
│   │   ├── Indicators/DEEP6/     ← copy to NT8
│   │   ├── Strategies/DEEP6/     ← copy to NT8
│   │   └── AddOns/DEEP6/         ← copy to NT8
│   ├── tests/                     ← macOS NUnit tests (don't copy to NT8)
│   ├── backtests/                 ← optimization results + sessions
│   ├── captures/                  ← recorded live sessions (NDJSON)
│   └── SETUP-GUIDE.md            ← human-readable setup guide
├── deep6/                         ← Python reference engine (not needed for NT8)
├── .planning/                     ← GSD planning artifacts
│   ├── design/ninjatrader-chart/  ← 5 visual design specs + HTML mockup
│   └── phases/                    ← 18 completed phases
└── CLAUDE.md                      ← project conventions
```

---

## Contact

- Owner: Michael Gonzalez (michael.gonzalez5@gmail.com)
- Company: Peak Asset Performance LLC
- GitHub: https://github.com/teaceo-debug/DEEP6

---

*AI Handoff Document — DEEP6 v2.0 NinjaScript Edition*
*Generated: 2026-04-16*
*System: 44 signal detectors, 290 NUnit tests, 3 optimization rounds, 12 NT8 audit fixes*
*Config: R3 Final (absorption=20 + imbalance=25 + exhaustion=15.7 + vol_profile=20.2)*
