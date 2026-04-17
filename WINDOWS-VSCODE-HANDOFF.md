# DEEP6 → Windows VS Code: Complete Handoff

## What You're Getting

The entire DEEP6 project — 543 commits of work, fully built NQ futures trading system.

| Component | Size | What it is |
|-----------|------|------------|
| `ninjatrader/Custom/` | 36 .cs files | NinjaTrader 8 indicator + strategy + 44 signal detectors |
| `deep6/` | 240 .py files | Python reference engine + backtesting + vectorbt |
| `.planning/` | 220 docs | 18 phases of planning, 3 optimization rounds, design specs |
| `dashboard/` | 611 MB | Next.js dashboard (reference only for NT8 track) |
| `ninjatrader/tests/` | NUnit project | 290 tests (runs via `dotnet test` on net8.0) |
| `ninjatrader/backtests/` | Results | 50 synthetic sessions, sweep results, production config |

---

## Step 1: Clone on Windows

Open PowerShell in VS Code terminal:

```powershell
cd $env:USERPROFILE
git clone https://github.com/teaceo-debug/DEEP6.git
cd DEEP6
code .
```

This opens the full repo in VS Code.

---

## Step 2: Install VS Code Extensions

In VS Code, install these (Ctrl+Shift+X):

1. **C#** (Microsoft) — for .cs files in ninjatrader/
2. **Python** (Microsoft) — for deep6/ backtesting
3. **NuGet Package Manager** — if you need to manage test dependencies
4. **Claude Code** (Anthropic) — AI assistant in the terminal

---

## Step 3: Understand the Folder Structure

```
DEEP6/
├── ninjatrader/
│   ├── Custom/                    ← THE NT8 CODE (copy to NT8 to compile)
│   │   ├── AddOns/DEEP6/
│   │   │   ├── Registry/          ISignalDetector, DetectorRegistry, SessionContext
│   │   │   ├── Detectors/         7 families × 1 file each (44 signals total)
│   │   │   ├── Scoring/           ConfluenceScorer, ScorerEntryGate, ZoneScore
│   │   │   ├── Levels/            ProfileAnchorLevels (PDH/PDL/POC/VAH/VAL/naked POCs)
│   │   │   └── Math/              LeastSquares, Wasserstein (zero deps)
│   │   ├── Indicators/DEEP6/
│   │   │   ├── DEEP6Footprint.cs  Main indicator (footprint + HUD + anchors)
│   │   │   └── DEEP6GexLevels.cs  Optional GEX overlay (standalone)
│   │   └── Strategies/DEEP6/
│   │       └── DEEP6Strategy.cs   Auto-trader (scorer-driven entries + ATM brackets)
│   │
│   ├── tests/                     ← NUnit test project (runs on Windows or Mac)
│   │   ├── ninjatrader.tests.csproj
│   │   ├── Detectors/            Per-detector test classes
│   │   ├── Scoring/              Scorer + parity tests
│   │   ├── Backtest/             BacktestRunner + E2E tests
│   │   └── fixtures/             JSON test data
│   │
│   ├── backtests/
│   │   ├── sessions/             50 synthetic NDJSON sessions
│   │   └── results/
│   │       ├── round1/           R1 optimization (entry/exit/weights/risk/signals)
│   │       ├── round2/           R2 stress test + execution sim + config
│   │       └── round3/           R3 FINAL (post-imbalance-fix, config locked)
│   │
│   ├── captures/                 ← Live session recordings go here
│   │
│   └── deploy/
│       ├── INSTALL-EVERYTHING.md  Give to AI → installs NT8 + DEEP6
│       ├── WINDOWS-AI-AGENT.md    Autonomous build/deploy/monitor loop
│       ├── COMMS-PROTOCOL.md      Mac ↔ Windows communication via GitHub Issues
│       └── auto-deploy.ps1        PowerShell deploy script
│
├── deep6/                         ← Python reference engine
│   ├── engines/                   44 signal detector implementations (port source)
│   ├── scoring/                   ConfluenceScorer (Python version, parity with C#)
│   ├── backtest/                  Optimizer, signal attribution, regime analysis, vectorbt
│   └── state/                     FootprintBar, DOMState, SessionContext (Python)
│
├── .planning/                     ← GSD planning system
│   ├── PROJECT.md                 Project definition (NT8-primary since 2026-04-15)
│   ├── ROADMAP.md                 19 phases (17+18 complete, 19 = paper trading)
│   ├── STATE.md                   Current progress
│   ├── REQUIREMENTS.md            Signal IDs + requirements
│   ├── phases/                    Per-phase context, research, plans, summaries
│   │   ├── 17-nt8-detector.../    Phase 17 (44 signal ports)
│   │   └── 18-nt8-scoring.../     Phase 18 (scorer + HUD + parity)
│   ├── design/
│   │   └── ninjatrader-chart/     5 visual design specs + HTML mockup
│   └── quick/                     Quick task history
│
├── dashboard/                     ← Next.js dashboard (reference only, not active)
│   └── agents/
│       ├── ninjascript-error-surgeon-v2.md   NT8 error reference
│       └── vectorbt-backtesting-expert.md    VectorBT API reference
│
├── CLAUDE.md                      ← Project conventions for AI
├── WINDOWS-VSCODE-HANDOFF.md      ← THIS FILE
└── ninjatrader/
    ├── AI-HANDOFF.md              ← System architecture for AI agents
    ├── SETUP-GUIDE.md             ← Human setup guide
    └── FOOTPRINT-VISUAL-SPEC.md   ← Chart rendering spec
```

---

## Step 4: Deploy to NinjaTrader

From VS Code terminal:

```powershell
$source = "$env:USERPROFILE\DEEP6\ninjatrader\Custom"
$dest = "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom"

# Clean old files
Remove-Item "$dest\AddOns\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\Indicators\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$dest\Strategies\DEEP6" -Recurse -Force -ErrorAction SilentlyContinue

# Copy fresh
xcopy "$source\AddOns\DEEP6" "$dest\AddOns\DEEP6\" /E /I /Y
xcopy "$source\Indicators\DEEP6" "$dest\Indicators\DEEP6\" /E /I /Y
xcopy "$source\Strategies\DEEP6" "$dest\Strategies\DEEP6\" /E /I /Y

Write-Host "Deployed. Open NT8 → Tools → NinjaScript Editor → F5"
```

---

## Step 5: Run Tests (from VS Code)

```powershell
cd $env:USERPROFILE\DEEP6\ninjatrader\tests
dotnet test --verbosity minimal
```

Expected: **290 passed, 0 failed**

---

## Step 6: Run Backtests (from VS Code)

```powershell
# Quick backtest on 5 scoring sessions
dotnet test --filter "E2E_FiveSessions" --verbosity normal

# Full 50-session optimizer sweep
cd $env:USERPROFILE\DEEP6
python -m deep6.backtest.optimizer

# Signal attribution analysis
python -m deep6.backtest.signal_attribution

# Regime analysis
python -m deep6.backtest.regime_analysis
```

---

## Step 7: Communication with Mac

GitHub Issues are the message bus between Mac and Windows:

```powershell
# READ messages from Mac
gh issue list --repo teaceo-debug/DEEP6 --label "from-mac" --state open

# WRITE status back to Mac
gh issue create --repo teaceo-debug/DEEP6 --title "[STATUS] description" --body "details" --label "from-windows"

# Report errors
gh issue create --repo teaceo-debug/DEEP6 --title "[ERROR] description" --body "details" --label "from-windows" --label "urgent"
```

---

## Key Reference Files (read these first)

| Priority | File | What it tells you |
|----------|------|-------------------|
| 1 | `ninjatrader/AI-HANDOFF.md` | Complete system architecture + every property value |
| 2 | `ninjatrader/deploy/INSTALL-EVERYTHING.md` | Step-by-step NT8 install + configure |
| 3 | `ninjatrader/backtests/results/round3/FINAL-PRODUCTION-CONFIG.md` | Locked production parameters |
| 4 | `ninjatrader/backtests/results/round3/FINAL-PRE-LIVE-CHECKLIST.md` | 84-item go-live checklist |
| 5 | `dashboard/agents/ninjascript-error-surgeon-v2.md` | Every NT8 compile/runtime error + fix |
| 6 | `ninjatrader/deploy/WINDOWS-AI-AGENT.md` | Autonomous loop for build/deploy/monitor |
| 7 | `ninjatrader/deploy/COMMS-PROTOCOL.md` | How to talk to Mac agent via GitHub Issues |

---

## Current System Status

- **Phase 17:** COMPLETE — 44 signal detectors ported from Python to NinjaScript
- **Phase 18:** COMPLETE — Scorer + HUD + parity harness
- **Optimization:** 3 rounds complete, config locked (R3)
- **NT8 audit:** 12 fixes shipped (threading, Calculate mode, ExtractStackedTier scoring bug)
- **Tests:** 290 NUnit green
- **Next:** Get strategy compiling + trading on NT8 sim → Phase 19 (30-day paper gate)

### Production Config (R3 Final)
```
Scorer weights: abs=20, exh=15.7, imb=25, vol_profile=20.2, delta=14.3, auction=12.6
Entry: threshold=70, MinTier=TYPE_B, strict direction, blackout 1530-1600
Exit: stop=20t, scale-out 50%@16t, target=32t, breakeven@MFE≥10t
Filters: VOLP-03 veto ON, slow-grind veto ON
Risk: 1-2 contracts, $500 daily cap
```

### Core Thesis
Absorption at value area extremes + stacked imbalance confirmation = 81.2% win rate. ABS-01 + IMB-03 are the two load-bearing alpha signals. Everything else confirms or filters.

---

## GitHub Repo
```
https://github.com/teaceo-debug/DEEP6.git
```

543 commits. Everything pushed. Clone it and you have the complete system.

---

*DEEP6 Windows VS Code Handoff — v1.0*
*Generated: 2026-04-16*
*Owner: Michael Gonzalez (michael.gonzalez5@gmail.com) — Peak Asset Performance LLC*
