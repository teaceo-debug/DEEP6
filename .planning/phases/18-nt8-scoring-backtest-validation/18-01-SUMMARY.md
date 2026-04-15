---
phase: 18
plan: "01"
subsystem: nt8-scoring
tags: [scoring, nt8, porting, phase-17-bugfix, confluence, NUnit]
dependency_graph:
  requires: [17-05]
  provides: [ConfluenceScorer, NarrativeCascade, ScorerResult, SignalTier]
  affects: [DEEP6Strategy.cs, ninjatrader.tests.csproj]
tech_stack:
  added: []
  patterns: [verbatim-port, System.Math-qualified, NT8-API-free, NUnit-fixture-driven]
key_files:
  created:
    - ninjatrader/Custom/AddOns/DEEP6/Scoring/SignalTier.cs
    - ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerResult.cs
    - ninjatrader/Custom/AddOns/DEEP6/Scoring/NarrativeCascade.cs
    - ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs
    - ninjatrader/tests/Scoring/ConfluenceScorerTests.cs
    - ninjatrader/tests/fixtures/scoring/type-a-all-categories.json
    - ninjatrader/tests/fixtures/scoring/type-b-no-zone.json
    - ninjatrader/tests/fixtures/scoring/type-c-suppressed.json
    - ninjatrader/tests/fixtures/scoring/quiet-zero-signals.json
    - ninjatrader/tests/fixtures/scoring/midday-block.json
  modified:
    - ninjatrader/tests/ninjatrader.tests.csproj
decisions:
  - "TypeC gate is cat_count >= 4 (not 3): Python scorer.py line 485 code overrides docstring (Pitfall 1)"
  - "System.Math fully qualified throughout Scoring/*.cs — DEEP6.Math namespace shadows System.Math"
  - "Zone bonus logic: near-edge (zoneDistTicks<=0.5 + zoneScore>=50) → +4; inside high → +8; mid → +6"
  - "Task 1 was verify-only: Phase 17 fixes (single UseNewRegistry, single EvaluateBar) already present at commit a92443e"
metrics:
  duration_minutes: 45
  completed: "2026-04-15"
  tasks_completed: 3
  files_created: 10
  tests_added: 25
  tests_total: 205
---

# Phase 18 Plan 01: ConfluenceScorer + NarrativeCascade Port — Summary

**One-liner:** NT8-API-free two-layer confluence scorer verbatim port from Python scorer.py with 25 NUnit tests covering all tier gates, zone bonuses, dedup rules, and midday block.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Phase 17 bug-fix gate (verify-only) | a92443e (existing) | DEEP6Strategy.cs |
| 2 | Create Scoring AddOn types + ConfluenceScorer + NarrativeCascade | 69c8fb0 | 4 new Scoring/*.cs + csproj |
| 3 | Create 5 scoring fixtures + ConfluenceScorerTests (25 tests) | 629e496 | 5 JSON fixtures + ConfluenceScorerTests.cs |

---

## What Was Built

### Task 1 — Phase 17 Bug-Fix Gate

Verified both blocking regressions were already fixed at commit a92443e:
- `grep -c "public bool UseNewRegistry" DEEP6Strategy.cs` → **1** (was 2 before fix)
- `grep -c "_registry.EvaluateBar" DEEP6Strategy.cs` → **1** (was 2 before fix)
- 180/180 Phase 17 tests green; risk gates untouched (24 matches on ApprovedAccountName/NewsBlackouts/DailyLossCapDollars/_killSwitch/MaxTradesPerSession)

No re-application needed — constraints confirmed.

### Task 2 — Scoring AddOn

Four NT8-API-free files created in `ninjatrader/Custom/AddOns/DEEP6/Scoring/`:

**SignalTier.cs** — enum with ordinal values matching Python IntEnum exactly: DISQUALIFIED=-1, QUIET=0, TYPE_C=1, TYPE_B=2, TYPE_A=3.

**ScorerResult.cs** — sealed POCO with TotalScore, Tier, Direction, EngineAgreement, CategoryCount, ConfluenceMult, ZoneBonus, EntryPrice, Narrative, CategoriesFiring[].

**NarrativeCascade.cs** — static class with `BuildLabel()` emitting tier labels verbatim from Python scorer.py lines 499–508:
- TypeA: `"TYPE A — TRIPLE CONFLUENCE {LONG|SHORT} (N categories, score S)"`
- TypeB: `"TYPE B — DOUBLE CONFLUENCE {LONG|SHORT} (N categories, score S)"`
- TypeC: `"TYPE C — SIGNAL (N categories, score S)"`
- QUIET/DISQUALIFIED: dominant signal detail or `"QUIET"`

**ConfluenceScorer.cs** — static class with `Score(signals, barsSinceOpen, barDelta, barClose, ...)` implementing verbatim port of Python score_bar():
- Category weights 25/18/14/13/12/10/8/1 (absorption/exhaustion/trapped/delta/imbalance/volume_profile/auction/poc)
- Tier thresholds: TypeA=80, TypeB=72, TypeC=50
- 7-gate TypeA classification, TypeB/C with cat>=4 gate
- Stacked imbalance dedup D-02 (highest tier per direction, one vote)
- Delta votes only on DELT-04/05/06/08/10; auction on AUCT-01/02/05; poc on POC-02/07/08
- Zone bonus: inside high (>=50) → +8; inside mid (>=30) → +6; near edge (dist<=0.5 + score>=50) → +4
- Confluence multiplier 1.25 when cat_count >= 5
- IB multiplier 1.15 for bars 0–59
- Midday block: bars 240–330 forced QUIET
- VPIN modifier as final stage (locked multiplier order per phase 12-01)
- EntryPrice from dominant ABS/EXH signal.Price or barClose fallback

**csproj** — added `<Compile Include="..\Custom\AddOns\DEEP6\Scoring\*.cs" />` glob. Fixture files already covered by existing `fixtures\**\*.json` glob.

### Task 3 — Fixtures + Tests

**5 JSON fixtures** in `ninjatrader/tests/fixtures/scoring/`:
- `type-a-all-categories.json` — 6 categories + zone near edge + IB → TYPE_A, score=100.0
- `type-b-no-zone.json` — 4 categories + IB, no zone → TYPE_B, score=80.5
- `type-c-suppressed.json` — 3 categories at score=56 → QUIET (Pitfall 1 documented)
- `quiet-zero-signals.json` — empty signals → QUIET, score=0.0
- `midday-block.json` — TypeA signals at bar 250 → QUIET (midday forced)

**ConfluenceScorerTests.cs** — 25 `[Test]` methods, `[Category("Scoring")]`, all green:

| # | Test | Behavior |
|---|------|----------|
| 1 | Score_AllEightCategories_ReturnsTypeA | SCOR-01/02/03: all weights + confluence + zone |
| 2 | Score_ZeroSignals_ReturnsQuiet | Empty signals → QUIET, score=0, dir=0 |
| 3 | Score_TypeBPath_FourCategoriesNoZone_ReturnsTypeB | TypeB gate |
| 4 | Score_TypeCWithThreeCats_DemotedToQuiet | Pitfall 1: cat_count=3 → QUIET |
| 5 | Score_MiddayBlock_ForcesQuiet | bars 240–330 forced QUIET |
| 6 | Score_ZoneBonusTiers_CorrectBonusPerScore | +8/+6/+4/0 tiers |
| 7 | Score_StackedImbalanceT1AndT3_VotesOnce | D-02 dedup |
| 8 | Score_DeltaRise_DoesNotVoteDelta | DELT-01/02/03 excluded |
| 9 | Score_NarrativeLabelFormat_MatchesPythonFormat | TypeA/B/QUIET label format |
| 10 | Score_ConflictingDirection_DominantWins | Losing side excluded from categories |
| 11 | Score_IbMultiplier_AppliedOnlyInFirstSixtyBars | 1.15x ratio check |
| 12 | Score_ConfluenceMult_OnlyAboveFiveCategories | 1.0 at 4, 1.25 at 5 |
| 13 | Score_TypeAMissingZone_DemotedToTypeB | All 7 TypeA gates required |
| 14 | Score_EntryPrice_DerivedFromDominantAbsExhSignal | Price + fallback |
| 15 | Score_ScoreClampedToRange | [0.0, 100.0] enforced |
| 16 | Score_DeltaVotingSignals_OnlyApprovedIDsVote | DELT-04/05/06/08/10 only |
| 17 | Score_FourCategoriesScoreAbove50_ReturnsTypeC | TypeC path |
| 18 | Score_NullSignalsArray_ReturnsQuiet | Null safety |
| 19 | Score_MiddayBlockEdges_CorrectBoundaries | bars 239/240/330/331 |
| 20–24 | Fixture_*_ExistsAndIsValidJson | 5 fixture presence + parse checks |
| 25 | Score_TypeBFormulaPrecision_MatchesHandComputed | Score=80.5 within 0.0001 |

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DEEP6.Math namespace shadows System.Math**
- **Found during:** Task 2 — first build attempt
- **Issue:** The project includes `NinjaTrader.NinjaScript.AddOns.DEEP6.Math` (LeastSquares.cs, Wasserstein.cs). With `using System;`, the unqualified `Math.Min` / `Math.Max` / `Math.Abs` / `Math.Round` resolve to the DEEP6.Math namespace rather than System.Math, causing CS0234 errors.
- **Fix:** Removed `using System;` from Scoring files; qualified all System.Math calls as `System.Math.Min`, `System.Math.Max`, `System.Math.Abs`, `System.Math.Round`, `System.Array.Sort`, `System.StringComparer`, `System.StringComparison`, `System.MidpointRounding`.
- **Files modified:** ConfluenceScorer.cs, NarrativeCascade.cs
- **Commit:** 69c8fb0

### Python Bugs Discovered

None — the port faithfully reproduced the Python scorer. The only discrepancy found was the **documented Pitfall 1**: Python scorer.py line 485 uses `cat_count >= 4` for TypeC while the docstring claims `min_categories=3`. This is a **Python documentation bug, not a code bug**. The C# port follows the actual code (>= 4), matching the docstring from `18-RESEARCH.md`.

No Python source changes needed.

---

## Test Count Delta

| Baseline | Phase 18-01 Added | Total |
|----------|-------------------|-------|
| 180 (Phase 17) | 25 (Scoring) | **205** |

---

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All scorer files are NT8-API-free in-process computation only. T-18-03 mitigation (< 500µs per bar) deferred to Wave 4 benchmark — scorer completes well under that in test runs (13ms for 25 tests).

---

## Self-Check: PASSED

All 10 output files confirmed present. Both task commits (69c8fb0, 629e496) verified in git log. Full suite 205/205 green.
