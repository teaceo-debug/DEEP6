# Phase 18-04 Parity Report

**Date:** 2026-04-15
**Phase:** 18 (nt8-scoring-backtest-validation) — Wave 4 gate
**Status:** PHASE 18 PARITY: PASS
**Test command:** `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ScoringParityHarness" --nologo -v normal`
**Full suite:** `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q`

---

## Summary

C# `ConfluenceScorer.Score()` and Python `deep6.scoring.replay_scorer` produce identical
per-bar results across all 5 scoring sessions (165 bars total). Max score delta = 0.0000.
Zero tier mismatches. Phase 18 parity gate: **PASS**.

---

## Per-Session Results

| Session | Bars Scored | Signals | Max \|Δscore\| | Tier Mismatches | Verdict |
|---------|-------------|---------|----------------|-----------------|---------|
| scoring-session-01 | 30 | 105 | 0.0000 | 0 | PASS |
| scoring-session-02 | 40 | 145 | 0.0000 | 0 | PASS |
| scoring-session-03 | 30 | 114 | 0.0000 | 0 | PASS |
| scoring-session-04 | 40 | 130 | 0.0000 | 0 | PASS |
| scoring-session-05 | 25 | 110 | 0.0000 | 0 | PASS |
| **AGGREGATE** | **165** | **604** | **0.0000** | **0** | **PASS** |

---

## Tier Distribution

| Session | TYPE_A | TYPE_B | TYPE_C | QUIET | Design Purpose |
|---------|--------|--------|--------|-------|----------------|
| session-01 | 15 | 10 | 0 | 5 | IB window TypeA/TypeB + zone variants |
| session-02 | 15 | 16 | 4 | 5 | Mixed tiers bso 30-70, exits IB mid-session |
| session-03 | 0 | 4 | 14 | 12 | Direction conflict / majority-vote resolution |
| session-04 | 5 | 0 | 10 | 25 | Midday block bso 220-259 (240-330 forced QUIET) |
| session-05 | 0 | 0 | 5 | 20 | Stacked dedup + delta-vote-5-only |

---

## Divergence Summary

**None.** All 165 bars matched exactly (Δscore = 0.0000) with no tier mismatches.

Root cause analysis: not required (no divergences found).

---

## Coverage Matrix

| Scorer Path Tested | Session(s) | Notes |
|--------------------|-----------|-------|
| TypeA gate (5 cats + zone + IB mult) | session-01, session-02 | IB mult (bso < 60) exercised |
| TypeB gate (4 cats, no zone) | session-01, session-02, session-03 | Various direction combos |
| TypeC gate (4 cats, score 50-72) | session-02, session-03, session-04, session-05 | Post-IB, no zone |
| QUIET (0 signals / below thresholds) | all sessions | Empty signal bars |
| Midday block forced QUIET (bso 240-330) | session-04 | TypeA-grade signals silenced |
| Direction conflict / majority-vote | session-03 | 3-vs-3 ties → QUIET; 4-vs-1 → bull wins |
| Zone bonus ZONE_HIGH (+8, inside zone) | session-01, session-02 | zoneScore=60, zoneDistTicks=2.0 |
| Zone bonus ZONE_NEAR (+4, near edge) | session-01, session-02 | zoneScore=55, zoneDistTicks=0.0 |
| Zone bonus ZONE_MID (+6) | session-01 | zoneScore=35 |
| Stacked imbalance D-02 dedup | session-05 | T1+T2+T3 fire, only highest tier votes once |
| DELT-01/02/03 excluded from delta vote | session-05 | Only DELT-04/05/06/08/10 count |
| Delta-agrees gate (TypeA veto) | session-04 | barDelta disagrees → TypeA vetoed → TypeC |
| Delta chase veto (barDelta > 50 same-dir) | session-01 | barDelta=35 (no chase); design avoids delta>50 |
| IB multiplier (1.15x) | session-01, session-02 | bso < 60 triggers 1.15x boost |
| AUCT-01/02/05 voting | session-02, session-01 | Auction signals fire + vote |
| **TypeA (zone stub)** | **N/A** | **DEFERRED — see Known Limitations** |

---

## Known Limitations (TypeA Parity Scope)

TypeA tier requires `zone_bonus > 0`, which requires a non-stub `zoneScore` input.
The scoring sessions in this report DO exercise TypeA paths by supplying `zoneScore > 0`
in the NDJSON wire format. TypeA fires in sessions 1 and 2 (15 bars each).

However, in the **live DEEP6Footprint indicator**, `zoneScore` is currently stubbed to `0.0`
(Wave 2 known stub in DEEP6Footprint.cs: `zoneScore = 0.0`). This means:

- **Parity harness**: TypeA DOES fire and IS verified (sessions use explicit zoneScore)
- **Live indicator**: TypeA cannot fire until VPContext zone extension is wired (Phase 19+)

This is **documented, not a blocker**. The parity gate tests what the scorer CAN produce;
the live stub is a separate integration gap tracked in 18-02-SUMMARY.md Known Stubs.

---

## Python Bugs Fixed During Parity

None. The Python scorer.py was correct as implemented. No Python source changes were
required during this parity run. (The only known discrepancy — TypeC min_categories=4 vs
docstring=3 — was already documented as Pitfall 1 in 18-01-SUMMARY.md and the C# port
correctly uses >= 4 to match the Python code.)

---

## Environment

| Property | Value |
|----------|-------|
| Python version | 3.11.9 (C:\Users\Tea\AppData\Local\Programs\Python\Python311\python.exe) |
| Python module path | `python -m deep6.scoring.replay_scorer` |
| PYTHON3_PATH | auto-detected via Windows-aware fallback (no venv; uses system python) |
| dotnet version | 8.0.420 (.NET 8) |
| NUnit | 3.14.0 |
| Test runtime | ~3.5s parity harness (5 sessions × ~450ms subprocess); ~2.7s full suite |
| Platform | Windows 11 Pro (win32) |
| Fix applied | `ScoringParityHarness.cs` + `BacktestE2ETests.cs` updated for Windows Python path detection (`python` fallback on Windows; checks `.venv\Scripts\python.exe` before bare command) |

---

## Phase 18 Gate Verdict

```
PHASE 18 PARITY: PASS

Criterion:  |Δscore| ≤ 0.05 AND identical tier verdict per bar across all 5 sessions
Result:     Max |Δscore| = 0.0000, tier mismatches = 0 (165/165 bars matched)
Sessions:   5/5 PASS
Full suite: 289/290 tests green (1 pre-existing failure: E2E_FiveSessions_BacktestAndExportAndVbt
            — vectorbt not installed in this environment; unrelated to Phase 18-04)
```
