# DEEP6 v2.0 — VS Code Agent Handoff

**Date:** 2026-04-16
**Owner:** Michael Gonzalez (michael.gonzalez5@gmail.com) — Peak Asset Performance LLC
**Accounts:** Apex (APEX-262674) + Lucid Trading (LT-45N3KIV8)

---

## What This Project Is

DEEP6 is an institutional-grade footprint chart auto-trading system for **NQ futures** running on **NinjaTrader 8 (NT8)**. It detects absorption and exhaustion reversal signals from Level 2 order flow data and auto-executes trades via ATM bracket orders.

**Thesis:** Absorption and exhaustion are the highest-alpha reversal signals in order flow. Everything else confirms or contextualizes them.

**44 market microstructure signals** across 8 categories → two-layer confluence scorer → TypeA/B/C entry classification → NT8 ATM bracket order execution.

---

## Architecture

```
NinjaTrader 8 (.NET Framework 4.8)
├── DEEP6Footprint.cs          — Indicator: footprint chart + scoring HUD + tier markers + profile anchors
├── DEEP6GexLevels.cs          — Indicator: standalone GEX overlay (massive.com API)
├── DEEP6Strategy.cs           — Strategy: auto-trader with scorer-gated entries + ATM brackets
└── AddOns/DEEP6/
    ├── Registry/              — ISignalDetector interface + DetectorRegistry (44 signal detectors)
    ├── Detectors/             — 7 families: Absorption, Exhaustion, Imbalance, Delta, Auction, Trap, VolPattern + Engine
    ├── Scoring/               — ConfluenceScorer, NarrativeCascade, ScorerEntryGate, ZoneScoreCalculator
    ├── Levels/                — ProfileAnchorLevels (PDH/PDL/PDM, PD POC, PD VAH/VAL, naked POCs, PW POC)
    └── Math/                  — LeastSquares + Wasserstein (zero-dependency math utilities)
```

**Signal flow:**
```
OnMarketData (ticks)
  → FootprintBar accumulation
  → DetectorRegistry.EvaluateBar (44 detectors, all families)
  → ScorerSharedState.Publish (indicator → strategy hand-off)
  → ConfluenceScorer.Score (two-layer confluence)
  → ScorerEntryGate.Evaluate (threshold + tier + veto gates)
  → RiskGatesPass (account whitelist, news blackout, daily loss cap, max trades)
  → EnterWithAtm (DEEP6_Confluence bracket template via Rithmic)
```

---

## File Locations

| What | Where in Repo | Copy to NT8 |
|------|--------------|-------------|
| Footprint indicator + GEX indicator | `ninjatrader/Custom/Indicators/DEEP6/` | `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\` |
| Strategy | `ninjatrader/Custom/Strategies/DEEP6/` | `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\DEEP6\` |
| AddOns (scorer, detectors, registry) | `ninjatrader/Custom/AddOns/DEEP6/` | `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\DEEP6\` |
| NUnit tests (macOS only, don't copy to NT8) | `ninjatrader/tests/` | — |
| Python reference engine (not live runtime) | `deep6/` | — |
| Planning artifacts + phase history | `.planning/` | — |

---

## Current State (as of 2026-04-16)

**Overall progress: 93% complete (15/21 planned phases done)**

### What's Built and Working
- **Phase 16 COMPLETE:** NT8 NinjaScript footprint indicator (`DEEP6Footprint.cs`) with:
  - Native Rithmic L2 footprint rendering (bid/ask volume per price level, POC, VAH/VAL, delta)
  - Absorption + exhaustion detection (ABS-01..04/07 + EXH-01..06)
  - GEX overlay via massive.com API (call wall, put wall, gamma flip, HVL) — **NOTE: MASSIVE_API_KEY needed in .env**
  - Profile anchor levels (PDH, PDL, PDM, PD POC, PD VAH/VAL, naked POC retest, PW POC, composite VA)

- **Phase 17 COMPLETE (2026-04-15):** All 44 signal detectors ported to NinjaScript
  - `ISignalDetector` interface + `DetectorRegistry` — modular detector registration
  - All 34 remaining signals ported: IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07
  - `UseNewRegistry=true` is the default (flip confirmed after 180/180 NUnit parity tests pass)
  - 180/180 NUnit tests green

- **Phase 18 Plans 01–03 COMPLETE (2026-04-15):**
  - `ConfluenceScorer.cs` — two-layer confluence scorer fully ported from Python (engine agreement + category agreement + zone bonus)
  - `NarrativeCascade.cs` — signal narrative rendering on chart
  - `ScorerSharedState.cs` — thread-safe indicator→strategy score hand-off
  - SharpDX HUD badge (top-right, score + tier + narrative)
  - TypeA/B/C tier markers on chart (Diamond / Triangle / Dot)
  - `ScorerEntryGate.cs` — NT8-API-free static gate, GateOutcome enum (NoScore/NoDirection/BelowScore/BelowTier/Passed)
  - `DEEP6Strategy.EvaluateEntry` fully migrated to scorer-gated entry
  - Per-bar `[DEEP6 Scorer] bar=N score=+XX.XX tier=TYPE_X narrative=...` log
  - 233 NUnit tests green

### What's Next (Phase 18 Plan 04 — NOT STARTED)

**This is where work stopped. The next task is 18-04-PLAN.md.**

Three tasks to complete Phase 18:

1. **Python `replay_scorer.py`** — subprocess entry point that reads scored-bar NDJSON from stdin, emits scored JSON lines on stdout (used by parity harness)
2. **5 augmented scoring-session NDJSON fixtures** — under `ninjatrader/tests/fixtures/scoring/sessions/` (do NOT touch `fixtures/sessions/` — Phase 17 baseline)
3. **`ScoringParityHarness.cs`** — NUnit test that runs both C# ConfluenceScorer and Python replay_scorer on each session, asserts `|Δscore| ≤ 0.05` AND identical tier per bar on all 5 sessions
4. **`18-04-PARITY-REPORT.md`** + finalize **`18-VALIDATION.md`** with `nyquist_compliant: true`

Full plan specification: `.planning/phases/18-nt8-scoring-backtest-validation/18-04-PLAN.md`

---

## Phase 19 (After Phase 18 is complete)

30-day paper-trade gate on Apex (APEX-262674) + Lucid (LT-45N3KIV8):
- Run `DEEP6Strategy` with `EnableLiveTrading=False` for 30 consecutive RTH sessions
- Verify all risk gates fire correctly at least once each
- Win rate ≥ 75%, profit factor ≥ 2.0 before enabling live capital
- Go/no-go decision committed to `.planning/`

---

## Key Configurations

### Scorer Weights (locked in `ConfluenceScorer.cs`)

| Category | Weight |
|----------|--------|
| absorption | 20.0 |
| exhaustion | 15.7 |
| imbalance | 25.0 |
| volume_profile | 20.2 |
| delta | 14.3 |
| auction | 12.6 |
| trapped | 0.0 |
| engine/poc | 0.0 |

### Score Thresholds

| Tier | Min Score |
|------|-----------|
| TYPE_A | 80.0 |
| TYPE_B | 72.0 |
| TYPE_C | 50.0 |

### ATM Bracket Template: `DEEP6_Confluence`

```
Stop Loss:   20 ticks ($100)
Target 1:    16 ticks ($80)  @ 50%
Target 2:    32 ticks ($160) @ 50%
Breakeven:   Trigger at 10 ticks profit, offset +2 ticks
```

### Strategy Properties (dry-run safe defaults)

```
EnableLiveTrading = FALSE  ← CRITICAL: start here
ApprovedAccountName = Sim101
MaxContractsPerTrade = 2
MaxTradesPerSession = 5
DailyLossCapDollars = 500
ScoreEntryThreshold = 80.0
MinTierForEntry = TYPE_A
UseNewRegistry = True
AtmTemplateName = DEEP6_Confluence
StopLossTicks = 20
ScaleOutEnabled = True
ScaleOutPercent = 0.5
ScaleOutTargetTicks = 16
TargetTicks = 32
BreakevenEnabled = True
BreakevenActivationTicks = 10
```

---

## Python Reference Engine

The Python engine (`deep6/`) is **reference-only** — it is not the live runtime. It served as the source-of-truth for porting all 44 signals into NinjaScript. It remains valuable for:
- Verifying signal logic against the C# implementation
- Running the Phase 18 parity harness (`deep6/scoring/replay_scorer.py`)
- The Python scorer is the "ground truth" — fix Python bugs first, then mirror to C#

**Key Python files for parity work:**
- `deep6/scoring/scorer.py` — `score_bar()` function, `ScorerConfig`, `SignalTier`
- `deep6/engines/narrative.py` — `NarrativeResult` construction
- `deep6/engines/signal_config.py` — `ScorerConfig` defaults

**Run Python tests:**
```bash
cd DEEP6
python -m pytest tests/ -v
```

---

## Running the NUnit Tests

```bash
# Full test suite (from DEEP6/ root)
dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q

# Scoring-only (fast)
dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "Category=Scoring" --nologo -v q

# Parity harness (Phase 18-04, after it's built)
dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ScoringParityHarness" --nologo -v normal
```

Expected: **233 passing** (as of Phase 18-03 completion). Phase 18-04 will add 5 more.

---

## NT8 Setup (on Windows machine)

1. Copy three folders into NT8 Custom directory (see File Locations table above)
2. Open NT8 → Tools > NinjaScript Editor → F5 to compile → expect **0 errors**
3. Create ATM template `DEEP6_Confluence` (Tools > ATM Strategy Parameters > New)
4. Add DEEP6Footprint indicator to 1-minute NQ chart
5. Add DEEP6Strategy with `EnableLiveTrading=FALSE` and `UseNewRegistry=True`
6. Open Output window (Ctrl+O) — verify:
   ```
   [DEEP6 Strategy] UseNewRegistry=true: Waves 1-5 detectors registered (ABS/EXH/IMB/DELT/AUCT/VOLP/TRAP + ENG-02..07).
   [DEEP6 Strategy] DRY RUN — no orders will be submitted.
   ```
7. On each bar close: `[DEEP6 Scorer] bar=N score=+XX.XX tier=TYPE_X narrative=...`

Full setup guide: `ninjatrader/SETUP-GUIDE.md`

---

## Known Issues / Active Stubs

| Issue | File | Notes |
|-------|------|-------|
| `zoneScore = 0.0` stub | `DEEP6Footprint.cs` | VPContext zone proximity not wired; TypeA cannot fire live until Phase 19+ wires this |
| `ConfluenceVaExtremeStrength` + `ConfluenceWallProximityTicks` | `DEEP6Strategy.cs` | Marked `[Obsolete]`, retained to avoid breaking saved NT8 XML configs; remove in Phase 19+ |

---

## GEX Integration

- Provider: **massive.com** (not FlashAlpha — CLAUDE.md is stale on this point)
- ENV var: `MASSIVE_API_KEY` (in `.env` at DEEP6 root)
- Underlying: QQQ/NDX proxy for NQ gamma exposure
- Fetches every 60 seconds: call wall, put wall, gamma flip, HVL
- `DEEP6GexLevels.cs` — standalone indicator, add separately from DEEP6Footprint

---

## Important Context: Architecture Pivot

The Python engine was originally the intended live runtime (via `async-rithmic`). On 2026-04-15, **Apex refused to enable Rithmic API/plugin mode** for account APEX-262674, blocking the Python live path. The project pivoted to NinjaScript C# as the live runtime.

- Python Phases 1–15: validated reference, not live
- NT8 NinjaScript Phases 16–19: the live path
- The 44-signal taxonomy, absorption/exhaustion thesis, LVN lifecycle, and scoring architecture are unchanged — only runtime and language changed

---

## Repo Structure Summary

```
DEEP6/
├── ninjatrader/
│   ├── Custom/
│   │   ├── Indicators/DEEP6/    ← copy to NT8 (DEEP6Footprint.cs, DEEP6GexLevels.cs)
│   │   ├── Strategies/DEEP6/    ← copy to NT8 (DEEP6Strategy.cs)
│   │   └── AddOns/DEEP6/        ← copy to NT8 (~35 .cs files across 8 subdirs)
│   ├── tests/                   ← NUnit test project (macOS, don't copy to NT8)
│   │   └── fixtures/
│   │       ├── sessions/        ← Phase 17 parity fixtures (DO NOT MODIFY)
│   │       └── scoring/sessions/ ← Phase 18 parity fixtures (to be created in 18-04)
│   ├── captures/                ← Recorded live NDJSON sessions
│   └── backtests/               ← Optimization results (3 rounds, 50 synthetic sessions)
├── deep6/                       ← Python reference engine (not live)
│   ├── scoring/scorer.py        ← Python source-of-truth for C# ConfluenceScorer
│   ├── engines/                 ← Signal engines (44 signals)
│   └── scoring/replay_scorer.py ← TO BE CREATED in Phase 18-04
├── .planning/
│   ├── STATE.md                 ← Current position in roadmap
│   ├── ROADMAP.md               ← All 19 phases with plans
│   ├── PROJECT.md               ← Decisions, constraints, what's in/out of scope
│   └── phases/
│       └── 18-nt8-scoring-backtest-validation/
│           ├── 18-04-PLAN.md    ← NEXT TASK TO EXECUTE
│           └── 18-VALIDATION.md ← Phase 18 validation contract
├── CLAUDE.md                    ← Project conventions (GSD workflow)
├── AI-HANDOFF.md (in ninjatrader/) ← NT8-specific setup handoff
└── HANDOFF.md                   ← This file
```

---

## Immediate Next Steps (in order)

1. **Execute Phase 18 Plan 04** — see `.planning/phases/18-nt8-scoring-backtest-validation/18-04-PLAN.md` for full spec
   - Task 1: Create `deep6/scoring/replay_scorer.py` + 5 NDJSON scoring fixtures
   - Task 2: Create `ScoringParityHarness.cs` NUnit test + extend `CaptureReplayLoader.cs`
   - Task 3: Write `18-04-PARITY-REPORT.md` + finalize `18-VALIDATION.md`
   - Verify: `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` → ≥238 passing

2. **After Phase 18 is green** → begin Phase 19 (Apex/Lucid 30-day paper-trade gate)

3. **Phase 19 gate criteria before enabling live capital:**
   - Strategy compiled with 0 errors on Windows NT8 machine
   - 30 consecutive paper sessions without crashes
   - Win rate ≥ 75%, profit factor ≥ 2.0
   - All risk gates verified firing (daily loss cap, news blackout, RTH window, max trades)
   - Written go/no-go decision committed to `.planning/`

---

## Contact

- Owner: Michael Gonzalez (michael.gonzalez5@gmail.com)
- Company: Peak Asset Performance LLC
- GitHub: https://github.com/teaceo-debug/DEEP6

---

*Handoff generated: 2026-04-16*
*Last AI session stopped at: Completed 18-03-PLAN.md (2026-04-15)*
*Tests at handoff: 233/233 NUnit green*
*Next: 18-04-PLAN.md — Python parity harness + ScoringParityHarness NUnit*
