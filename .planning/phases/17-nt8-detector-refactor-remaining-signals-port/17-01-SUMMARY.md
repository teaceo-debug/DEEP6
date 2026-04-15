---
phase: 17-nt8-detector-refactor-remaining-signals-port
plan: 01
subsystem: ninjatrader-detector-registry
tags: [csharp, ninjascript, registry, signals, absorption, exhaustion, nunit, tdd]
requires: [16-01]
provides: [17-02]
affects: [ninjatrader/Custom/AddOns/DEEP6/Registry, ninjatrader/Custom/AddOns/DEEP6/Math, ninjatrader/Custom/AddOns/DEEP6/Detectors, ninjatrader/tests]
tech-stack:
  added: [NUnit 3.14, NUnit3TestAdapter 4.5.0, Microsoft.NET.Test.Sdk 17.9.0]
  patterns: [ISignalDetector registry, BCL-only detector pattern, fixture-driven unit testing]
key-files:
  created:
    - ninjatrader/Custom/AddOns/DEEP6/Registry/ISignalDetector.cs
    - ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs
    - ninjatrader/Custom/AddOns/DEEP6/Registry/SignalResult.cs
    - ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs
    - ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs
    - ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs
    - ninjatrader/Custom/AddOns/DEEP6/Math/LeastSquares.cs
    - ninjatrader/Custom/AddOns/DEEP6/Math/Wasserstein.cs
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs
    - ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs
    - ninjatrader/tests/ninjatrader.tests.csproj
    - ninjatrader/tests/fixtures/absorption/abs-01-classic.json
    - ninjatrader/tests/fixtures/exhaustion/exh-01-zero-print.json
    - ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs
    - ninjatrader/tests/Detectors/ExhaustionDetectorTests.cs
    - ninjatrader/tests/Math/LeastSquaresTests.cs
  modified:
    - ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs
decisions:
  - "FootprintBar.Finalize() auto-recomputes TotalVol from Levels when TotalVol==0 (test construction pattern)"
  - "AbsorptionDetector and ExhaustionDetector qualify System.Math.* to avoid DEEP6.Math namespace collision"
  - "RollForward=Major in test csproj enables .NET 10 runtime to run net8.0 test binary (no .NET 8 on dev Mac)"
  - "ExhaustionDetector uses DetectCore() returning SignalResult[] bridged by legacy Detect() for DEEP6Strategy compat"
metrics:
  duration: 12
  completed: "2026-04-15T18:40:00Z"
  tasks: 3
  files: 17
---

# Phase 17 Plan 01: Registry Scaffold + ABS/EXH Migration + NUnit Test Harness Summary

ISignalDetector registry + BCL-only AbsorptionDetector/ExhaustionDetector migrated from monolith with 13 passing NUnit smoke tests on macOS via `dotnet test`.

## What Was Built

### Task 1: Registry Scaffold + SignalFlagBits + Math Utilities + UseNewRegistry Flag

**Registry files** (`ninjatrader/Custom/AddOns/DEEP6/Registry/`):
- `ISignalDetector.cs` — interface: `Name`, `Reset()`, `OnBar(FootprintBar, SessionContext) → SignalResult[]`
- `SignalResult.cs` — output type: SignalId, Direction, Strength, FlagBit (ulong), Detail
- `DetectorRegistry.cs` — sequential registry with exception-safe `EvaluateBar()` + `ResetAll()`
- `SessionContext.cs` — shared state: Atr20, VolEma20, PriorCvd, PriorBar, Vah/Val, TickSize, double[40] DOM arrays, bounded Queue histories (MaxHistory=50)
- `SignalFlagBits.cs` — 58-bit ulong layout (bits 0–57), XML-documented per Python flags.py
- `FootprintBar.cs` — BCL-only FootprintBar + Cell stubs for test project (NT8 uses original in DEEP6Footprint.cs)

**Math files** (`ninjatrader/Custom/AddOns/DEEP6/Math/`):
- `LeastSquares.cs` — Fit1(IReadOnlyList<double>) and Fit1(double[], double[]) matching numpy.polyfit(x,y,1)
- `Wasserstein.cs` — 1D W1 distance matching scipy.stats.wasserstein_distance with Python guard (sum==0 → 0)

**DEEP6Strategy.cs** — added UseNewRegistry bool property (default false) + _registry field + Configure init with TODO comment for Wave2+ detector registration.

### SignalFlagBits Final Bit Table

| Bits  | Family | Signals |
|-------|--------|---------|
| 0–3   | ABS    | ABS_01..04 |
| 4–11  | EXH    | EXH_01..08 |
| 12–20 | IMB    | IMB_01..09 |
| 21–31 | DELT   | DELT_01..11 |
| 32–36 | AUCT   | AUCT_01..05 |
| 37–41 | TRAP   | TRAP_01..05 |
| 42–43 | VOLP   | VOLP_01..02 |
| 44    | —      | TRAP_SHOT (Phase 12 reserved) |
| 45–47 | META   | PIN_REGIME, REGIME_CHANGE, SPOOF_VETO (Phase 15 reserved) |
| 48–51 | VOLP ext | VOLP_03..06 (C# extension; bits 44-47 taken) |
| 52–57 | ENG    | ENG_02..07 |

Spot-check: `IMB_01=12` ✓, `IMB_08=19` ✓, `DELT_01=21` ✓, `VOLP_03=48` ✓, `ENG_02=52` ✓, `ENG_07=57` ✓. No collisions.

### Task 2: AbsorptionDetector + ExhaustionDetector Migration

**AbsorptionDetector** (`Detectors/Absorption/AbsorptionDetector.cs`):
- Implements `ISignalDetector`, Name="Absorption"
- Emits `ABS-01` (Classic), `ABS-02` (Passive), `ABS-03` (Stopping Vol), `ABS-04` (Effort vs Result)
- ABS-07 VA extreme bonus applied post-hoc: bumps Strength + appends "@VAH"/"@VAL" to Detail; emits diagnostic SignalResult with FlagBit=0
- Stateless (no rolling state needed for absorption)
- Zero NinjaTrader.* using directives; compiles under net8.0 and net48

**ExhaustionDetector** (`Detectors/Exhaustion/ExhaustionDetector.cs`):
- Implements `ISignalDetector`, Name="Exhaustion"
- Emits `EXH-01..EXH-06` via `DetectCore()` returning `SignalResult[]`
- EXH-01 (ZeroPrint) is delta-gate exempt — fires regardless of delta
- `_cooldown: Dictionary<ExhaustionType, int>` instance field; `Reset()` clears it
- `Detect()` legacy bridge returns `List<ExhaustionSignal>` for DEEP6Strategy compatibility
- Zero NinjaTrader.* using directives

**Preserved**: legacy ABS/EXH code in `DEEP6Footprint.cs` is untouched (46 "Absorption" occurrences unchanged). `UseNewRegistry=false` keeps live path active.

### Task 3: NUnit Test Project + Fixtures + 13 Smoke Tests

**ninjatrader.tests.csproj**: net8.0 target, NUnit 3.14.0, RollForward=Major (dev Mac has .NET 10 only)

**Fixtures**:
- `abs-01-classic.json`: upper wick 70% of total vol, deltaRatio=0.10 — triggers ABS-01 classic
- `exh-01-zero-print.json`: zero-vol level at price 20002.00 inside body — triggers EXH-01

**`dotnet test` output (13/13 passed)**:
```
Passed!  - Failed: 0, Passed: 13, Skipped: 0, Total: 13, Duration: 15 ms
```

Test breakdown:
- `AbsorptionDetectorTests`: 3 tests (Abs01_ClassicFixture, Abs01_LowWickVol_DoesNotFire, Abs01Fixture_JsonIsValid)
- `ExhaustionDetectorTests`: 4 tests (Exh01_ZeroPrintFixture, Exh01_NoZeroPrint, Exh01_Cooldown, Exh01Fixture_JsonIsValid)
- `LeastSquaresTests`: 6 tests (Increasing, Decreasing, Constant, SingleElement, Empty, ExplicitX)

## DEEP6Strategy Risk-Gate Confirmation

Risk gate code paths are UNCHANGED. Baseline grep count: 29 matches for `ApprovedAccountName|NewsBlackout|RthStart|RthEnd|DailyLossCap|killSwitch|_killSwitch`. Count after plan: 29. No risk-gate lines added, removed, or modified.

Changes to DEEP6Strategy.cs were ADD-ONLY:
- Private field `_registry`
- `UseNewRegistry` property in #region Properties (Order=100, GroupName="DEEP6 Migration")
- Initialize/nullify `_registry` in `State.Configure` block with TODO comment for Wave2+

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FootprintBar.Finalize() did not recompute TotalVol from Levels**
- **Found during:** Task 3 (test failure: ABS-01 returned null, EXH-01 returned null)
- **Root cause:** `TotalVol` is only accumulated via `AddTrade()`. Tests construct bars by setting `Levels` directly without `AddTrade()`, leaving `TotalVol=0`. All detector guards `if (bar.TotalVol == 0) return empty` then short-circuit.
- **Fix:** Added TotalVol recomputation in `Finalize()` when `TotalVol==0 && Levels.Count>0`: iterates Levels and sums `AskVol+BidVol+NeutralVol`.
- **Files modified:** `ninjatrader/Custom/AddOns/DEEP6/Registry/FootprintBar.cs`
- **Commit:** a58b502

**2. [Rule 1 - Bug] `Math.Min/Max/Abs` resolved to DEEP6.Math namespace instead of System.Math**
- **Found during:** Task 3 first build (26 CS0234 errors: "type 'Min' does not exist in namespace DEEP6.Math")
- **Root cause:** Detector files use `using System;` but when compiled into a project that includes `DEEP6.Math` namespace files, the unqualified `Math.` resolves to `NinjaTrader.NinjaScript.AddOns.DEEP6.Math` (the custom namespace) instead of `System.Math`.
- **Fix:** Qualified all `Math.` calls as `System.Math.` in AbsorptionDetector.cs and ExhaustionDetector.cs using `sed`.
- **Files modified:** `AbsorptionDetector.cs`, `ExhaustionDetector.cs`
- **Commit:** a58b502

**3. [Rule 3 - Blocking] .NET 8 runtime not installed on dev Mac (only .NET 10)**
- **Found during:** Task 3 first test run
- **Root cause:** RESEARCH.md mentions "net8.0 OR net10.0" — the dev Mac has dotnet 10.0.201 but no .NET 8 runtime.
- **Fix:** Added `<RollForward>Major</RollForward>` to test csproj. This allows the .NET 10 runtime to execute the net8.0 compiled test binary. The csproj still declares `<TargetFramework>net8.0</TargetFramework>` per plan acceptance criteria.
- **Files modified:** `ninjatrader.tests.csproj`
- **Commit:** a58b502

### Architectural Changes

None. All deviations were in-scope bug fixes and build blockers.

## Python Corrections

None found during Wave 1 porting. The absorption.py and exhaustion.py algorithms translated cleanly. The `_cooldown` module-level dict in exhaustion.py (which would be shared across calls in Python) becomes a per-instance field in the C# class — this is a correct architectural improvement, not a bug.

## Known Stubs

None. All signals (ABS-01..04, ABS-07, EXH-01..06) are fully implemented with real detection logic matching the Python reference. No placeholder values or hardcoded returns.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan creates pure computation files (C# classes, NUnit tests, JSON fixtures) with no I/O surface.

## Self-Check: PASSED

All 16 created files confirmed present on disk. All 3 task commits verified in git log.

| Check | Result |
|-------|--------|
| ISignalDetector.cs | FOUND |
| DetectorRegistry.cs | FOUND |
| SignalResult.cs | FOUND |
| SessionContext.cs | FOUND |
| SignalFlagBits.cs | FOUND |
| FootprintBar.cs | FOUND |
| LeastSquares.cs | FOUND |
| Wasserstein.cs | FOUND |
| AbsorptionDetector.cs | FOUND |
| ExhaustionDetector.cs | FOUND |
| ninjatrader.tests.csproj | FOUND |
| abs-01-classic.json | FOUND |
| exh-01-zero-print.json | FOUND |
| AbsorptionDetectorTests.cs | FOUND |
| ExhaustionDetectorTests.cs | FOUND |
| LeastSquaresTests.cs | FOUND |
| Commit 2d227cf (T1) | FOUND |
| Commit ad1bc4d (T2) | FOUND |
| Commit a58b502 (T3) | FOUND |
