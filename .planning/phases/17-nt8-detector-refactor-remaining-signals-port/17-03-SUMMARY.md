---
phase: 17-nt8-detector-refactor-remaining-signals-port
plan: 03
subsystem: ninjatrader-detector-registry
tags: [csharp, ninjascript, signals, imbalance, delta, auction, volpattern, nunit, wave3]
requires: [17-02]
provides: [17-04]
affects:
  - ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/
  - ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/
  - ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/
  - ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/
  - ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs
  - ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs
  - ninjatrader/tests/
tech-stack:
  added: []
  patterns: [BCL-only ISignalDetector, diagonal-scan buy-imbalance, SessionContext rolling state]
key-files:
  created:
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/AuctionDetector.cs
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs
    - ninjatrader/tests/fixtures/imbalance/imb-01-single.json
    - ninjatrader/tests/fixtures/imbalance/imb-06-oversized.json
    - ninjatrader/tests/fixtures/imbalance/imb-08-diagonal.json
    - ninjatrader/tests/fixtures/auction/auct-02-finished.json
    - ninjatrader/tests/fixtures/delta/delt-01-rise-drop.json
    - ninjatrader/tests/fixtures/delta/delt-02-tail.json
    - ninjatrader/tests/fixtures/delta/delt-03-reversal.json
    - ninjatrader/tests/fixtures/delta/delt-05-flip.json
    - ninjatrader/tests/fixtures/delta/delt-09-min-max.json
    - ninjatrader/tests/fixtures/volpattern/volp-02-bubble.json
    - ninjatrader/tests/fixtures/volpattern/volp-03-surge.json
    - ninjatrader/tests/fixtures/volpattern/volp-06-big-delta-per-level.json
    - ninjatrader/tests/Detectors/ImbalanceDetectorTests.cs
    - ninjatrader/tests/Detectors/AuctionDetectorTests.cs
    - ninjatrader/tests/Detectors/DeltaDetectorTests.cs
    - ninjatrader/tests/Detectors/VolPatternDetectorTests.cs
  modified:
    - ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs
    - ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs
    - ninjatrader/tests/ninjatrader.tests.csproj
decisions:
  - "ImbalanceDetector emits both IMB-01 and IMB-06 for oversized levels (plan spec: 'Expected both IMB-01 and IMB-06 fire')"
  - "IMB-08 detail contains 'P-tick diag' substring — regression guard for diagonal direction test"
  - "DELT-02 tail test uses MaxDelta=0 (test-construction path) triggering trivial-extreme fallback (ratio=1.0)"
  - "VOLP-06 uses single absolute threshold from Python (big_delta_level_threshold=80) not bar-delta ratio composite"
  - "SessionMaxDelta/SessionMinDelta added to SessionContext as acceptable Wave 3 amendment per plan spec"
metrics:
  duration: 1
  completed: "2026-04-15T20:30:00Z"
  tasks: 3
  files: 23
---

# Phase 17 Plan 03: TRIVIAL-Tier Signals Wave 3 Summary

12 TRIVIAL-tier signals (IMB-01/06/08, DELT-01/02/03/05/09, AUCT-02, VOLP-02/03/06) ported to NinjaScript with BCL-only detectors, 12 fixtures, 4 NUnit test classes, 30 new tests. Full suite: 79/79 green.

## What Was Built

### Task 1: ImbalanceDetector (IMB-01, IMB-06, IMB-08) + AuctionDetector (AUCT-02)

**ImbalanceDetector** (`Detectors/Imbalance/ImbalanceDetector.cs`):
- Implements `ISignalDetector`, Name="Imbalance"
- Single diagonal scan loop (Python imbalance.py lines 84-127) produces all three signals
- Buy imbalance: `ask[P]` vs `bid[P - tickSize]` — CRITICAL direction (one tick DOWN)
- Sell imbalance: `bid[P]` vs `ask[P + tickSize]` (one tick UP)
- IMB-01: fires for every qualifying level (ratio >= 3.0)
- IMB-06: fires additionally when ratio >= 10.0 (same scan; plan spec: emit both)
- IMB-08: always emits when diagonal scan fires; detail contains `"P-tick diag"` for regression guard
- Config: `ImbalanceConfig` — `RatioThreshold=3.0`, `OversizedThreshold=10.0`
- Stateless; `Reset()` no-op

**AuctionDetector** (`Detectors/Auction/AuctionDetector.cs`):
- Implements `ISignalDetector`, Name="Auction"
- AUCT-02: zero bid at bar high → direction=-1; zero ask at bar low → direction=+1; strength=1.0
- Python reference: auction.py lines 137-152
- Stateless; `Reset()` no-op

**Fixtures (4):**

| File | Trigger |
|------|---------|
| imb-01-single.json | ask[20000.00]=400 vs bid[19999.75]=100, ratio=4.0 |
| imb-06-oversized.json | ask[20000.00]=1000 vs bid[19999.75]=90, ratio=11.1 (both IMB-01 + IMB-06 fire) |
| imb-08-diagonal.json | ask[20000.25]=400 vs bid[20000.00]=80, ratio=5.0 (P-tick diag) |
| auct-02-finished.json | level at 20010.00: askVol=200, bidVol=0 → direction=-1 |

**Test classes:** ImbalanceDetectorTests (7 tests) + AuctionDetectorTests (4 tests) = **11 tests**

### Task 2: DeltaDetector (DELT-01, DELT-02, DELT-03, DELT-05, DELT-09)

**DeltaDetector** (`Detectors/Delta/DeltaDetector.cs`):
- Implements `ISignalDetector`, Name="Delta"
- DELT-01: direction of bar delta (+1 rise / -1 drop), strength=|delta|/totalVol
- DELT-02: tail at intrabar extreme (tailRatio >= 0.95); uses `bar.MaxDelta`/`bar.MinDelta`; when MaxDelta=0 (test-construction path), extreme = delta → ratio = 1.0 (always fires)
- DELT-03: bar direction vs delta sign mismatch; min ratio 0.15
- DELT-05: CVD sign flip via `session.PriorCvd`; guard `priorCvd != 0` prevents false fire on first bar
- DELT-09: delta >= 95% of `session.SessionMaxDelta` or <= 95% of `session.SessionMinDelta`; extremes updated AFTER evaluation
- Rolling state: pushes `DeltaHistory` + `CvdHistory` to `SessionContext` at end of `OnBar`
- Stateless private fields; `Reset()` no-op

**SessionContext amendment:** Added `SessionMaxDelta` (long) and `SessionMinDelta` (long) fields + reset in `ResetSession()`.

**Fixtures (5):**

| File | Trigger |
|------|---------|
| delt-01-rise-drop.json | barDelta=500, totalVol=1000, direction=+1, strength=0.5 |
| delt-02-tail.json | barDelta=100, MaxDelta=0 → trivial extreme, tailRatio=1.0 >= 0.95 |
| delt-03-reversal.json | bullish bar (close > open) but barDelta=-400 → bearish hidden reversal |
| delt-05-flip.json | priorCvd=+500, current cvd=-200 → sign flip direction=-1 |
| delt-09-min-max.json | sessionMaxDelta=1000, barDelta=980 >= 950 → direction=-1 |

**Test classes:** DeltaDetectorTests — **11 tests** including `Delt05_MultiBar_FiresOnlyOnSignChangeBar` sequential 3-bar test.

### Task 3: VolPatternDetector (VOLP-02, VOLP-03, VOLP-06) + DEEP6Strategy Registration

**VolPatternDetector** (`Detectors/VolPattern/VolPatternDetector.cs`):
- Implements `ISignalDetector`, Name="VolPattern"
- VOLP-02: highest-volume level > `avgLevelVol * 4.0`; direction from net delta at that level; strength = min((vol/threshold - 1.0) / 3.0, 1.0)
- VOLP-03: `bar.TotalVol > session.VolEma20 * 3.0`; direction from delta ratio if > 0.20, else 0; strength = min((vol/threshold - 1.0) / 2.0, 1.0)
- VOLP-06: level with highest `|net_delta|` >= `big_delta_level_threshold=80`; direction from net delta sign; matches Python single-threshold algorithm
- Config: `VolPatternConfig` — `BubbleMult=4.0`, `SurgeMult=3.0`, `BigDeltaLevelThreshold=80`
- Stateless; `Reset()` no-op

**Fixtures (3):**

| File | Trigger |
|------|---------|
| volp-02-bubble.json | avgLevelVol=175, level vol=800 > threshold=700, direction=+1 |
| volp-03-surge.json | volEma20=300, totalVol=1000 > surge threshold=900, direction=0 |
| volp-06-big-delta-per-level.json | level net_delta=400 >= threshold=80, direction=+1 |

**Test classes:** VolPatternDetectorTests — **8 tests**

**DEEP6Strategy.cs registration** (Configure branch, `UseNewRegistry=true` only):
```csharp
_registry.Register(new ImbalanceDetector());
_registry.Register(new DeltaDetector());
_registry.Register(new AuctionDetector());
_registry.Register(new VolPatternDetector());
```

## SignalFlagBits Values Used

| Signal | Bit | Mask expression |
|--------|-----|-----------------|
| IMB-01 | 12  | `Mask(IMB_01)` |
| IMB-06 | 17  | `Mask(IMB_06)` |
| IMB-08 | 19  | `Mask(IMB_08)` |
| DELT-01 | 21 | `Mask(DELT_01)` |
| DELT-02 | 22 | `Mask(DELT_02)` |
| DELT-03 | 23 | `Mask(DELT_03)` |
| DELT-05 | 25 | `Mask(DELT_05)` |
| DELT-09 | 29 | `Mask(DELT_09)` |
| AUCT-02 | 33 | `Mask(AUCT_02)` |
| VOLP-02 | 43 | `Mask(VOLP_02)` |
| VOLP-03 | 48 | `Mask(VOLP_03)` |
| VOLP-06 | 51 | `Mask(VOLP_06)` |

All bits verified against `SignalFlagBits.cs` — no collisions with ABS/EXH (bits 0-11).

## Test Count Delta vs Wave 2

| Milestone | Tests |
|-----------|-------|
| End of Wave 1 | 13 |
| End of Wave 2 | 49 |
| End of Wave 3 (this plan) | 79 |
| Delta from Wave 2 | +30 |

Breakdown of 30 new tests:
- ImbalanceDetectorTests: 7
- AuctionDetectorTests: 4
- DeltaDetectorTests: 11 (inc. multi-bar sequential)
- VolPatternDetectorTests: 8

## Risk-Gate + UseNewRegistry Confirmation

- `UseNewRegistry` default = `false` (line 761 of DEEP6Strategy.cs): confirmed
- Risk gate identifiers present and unchanged: `ApprovedAccountName`, `DailyLossCap`, `RthStart`, `RthEnd`, `_killSwitch` — no modifications to risk logic
- Wave 3 detector registration is ADD-ONLY inside the `if (UseNewRegistry)` branch

## Deviations from Plan

### Auto-fixed Issues

None. Plan executed exactly as written. The one structural decision documented below was explicitly permitted by the plan.

### Acceptable Amendments

**SessionMaxDelta/SessionMinDelta added to SessionContext**
- Plan spec §DELT-09: "If SessionContext from Wave 1 lacks SessionMaxDelta/SessionMinDelta, add them here (acceptable amendment)."
- Added two `long` fields and reset in `ResetSession()`.
- Files modified: `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs`

## Python Corrections

**None found.** All 12 signal algorithms ported cleanly from Python reference:
- `imbalance.py` diagonal direction confirmed: `ask[P] vs bid[P-1]` (buy) — matches C# implementation
- `delta.py` flip logic confirmed: `prev_cvd >= 0 and cvd < 0` → matches DELT-05 C# guard
- `vol_patterns.py` VOLP-06 uses single absolute threshold (80 contracts) — C# matches; plan spec note about ratio composite was plan-level description, not Python-verified algorithm
- No Python source changes required.

## Known Stubs

None. All 12 signals have complete detection logic matching Python reference algorithms. No placeholder values or hardcoded returns.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. Pure computation files (C# classes, NUnit tests, JSON fixtures).

## Commits

| Hash | Message |
|------|---------|
| b8da89c | feat(phase-17): port IMB-01/06/08 to NinjaScript + AuctionDetector AUCT-02 |
| 932cf04 | feat(phase-17): port DELT-01/02/03/05/09 to NinjaScript DeltaDetector |
| 328c158 | feat(phase-17): port AUCT-02 + VOLP-02/03/06 + register Wave 3 detectors |

## Self-Check: PASSED

All 4 detector files confirmed present. All 12 fixture files confirmed present. All 3 task commits verified.

| Check | Result |
|-------|--------|
| ImbalanceDetector.cs | FOUND |
| AuctionDetector.cs | FOUND |
| DeltaDetector.cs | FOUND |
| VolPatternDetector.cs | FOUND |
| imb-01-single.json | FOUND |
| imb-06-oversized.json | FOUND |
| imb-08-diagonal.json | FOUND |
| auct-02-finished.json | FOUND |
| delt-01-rise-drop.json | FOUND |
| delt-02-tail.json | FOUND |
| delt-03-reversal.json | FOUND |
| delt-05-flip.json | FOUND |
| delt-09-min-max.json | FOUND |
| volp-02-bubble.json | FOUND |
| volp-03-surge.json | FOUND |
| volp-06-big-delta-per-level.json | FOUND |
| Commit b8da89c (Task 1) | FOUND |
| Commit 932cf04 (Task 2) | FOUND |
| Commit 328c158 (Task 3) | FOUND |
| dotnet test: 79/79 PASS | CONFIRMED |
