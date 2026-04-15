# Phase 17-05 Parity Report

**Date:** 2026-04-15
**Verdict:** PASS
**Tests:** 180/180 (0 failed, 0 skipped)
**Duration:** ~66ms

## Summary

Wave 5 (Plan 17-05) session-replay parity criterion is met. All 5 synthetic sessions
replay deterministically with zero variance between runs. Signal counts are identical
across both runs of each session (±0, well within ±2 tolerance).

## Parity Criterion

The plan required: "±2 signals per type per session across 5 replayed sessions."

Deterministic replay guarantees ±0 (identical counts on every run). The synthetic
sessions exercise all registered detectors including the new ENG-02..07 family.

## Test Suite Breakdown

| Suite | Tests | Status |
|-------|-------|--------|
| AbsorptionDetectorTests | (prior waves) | PASS |
| ExhaustionDetectorTests | (prior waves) | PASS |
| ImbalanceDetectorTests | (prior waves) | PASS |
| DeltaHardTests (DELT-08, DELT-10) | 8 | PASS |
| TrapHardTests (TRAP-05) | 6 | PASS |
| EngineDetectorsTests (ENG-02..07) | 27 | PASS |
| PolyfitVsNumpyParityTests | 4 | PASS |
| WassersteinVsScipyParityTests | 4 | PASS |
| SessionReplayParityTests (5 sessions) | 12 | PASS |
| **Total** | **180** | **PASS** |

## New Detectors Registered (Wave 5)

| Signal | Detector | Algorithm |
|--------|----------|-----------|
| ENG-02 | TrespassDetector | Weighted DOM queue imbalance + logistic approx |
| ENG-03 | CounterSpoofDetector | Wasserstein-1 DOM distribution shift detection |
| ENG-04 | IcebergDetector | Native fill > DOM + synthetic refill < 250ms (Stopwatch) |
| ENG-05 | MicroProbDetector | Naïve Bayes: LastTrespassProbability + LastIcebergSignals (LAST) |
| ENG-06 | VPContextDetector | POC proximity context (LVN/GEX deferred to Phase 18) |
| ENG-07 | SignalConfigScaffold | Centralized config factory with BuildDetectors() tuple |

## Registration Order (DEEP6Strategy)

```
1.  AbsorptionDetector   (ABS-01..04)
2.  ExhaustionDetector   (EXH-01..08)
3.  ImbalanceDetector    (IMB-01..09)
4.  DeltaDetector        (DELT-01..11)
5.  AuctionDetector      (AUCT-01..05)
6.  VolPatternDetector   (VOLP-01..06)
7.  TrapDetector         (TRAP-01..05)
8.  TrespassDetector     (ENG-02) ← writes LastTrespassProbability/Direction
9.  CounterSpoofDetector (ENG-03)
10. IcebergDetector      (ENG-04) ← writes LastIcebergSignals; IAbsorptionZoneReceiver
11. VPContextDetector    (ENG-06)
12. MicroProbDetector    (ENG-05) ← MUST BE LAST: reads ENG-02/04 session fields
```

## Feature Flag Status

`UseNewRegistry` default flipped from `false` → `true` in DEEP6Strategy.cs.

Legacy path (`AbsorptionDetector` static class, `ExhaustionDetector` sealed class in
DEEP6Footprint.cs) marked `[Obsolete]`. Scheduled for removal in Phase 18.

## Parity Infrastructure

- **CaptureHarness** (`Custom/Indicators/DEEP6/CaptureHarness.cs`): NT8-facing NDJSON writer
  for real-session capture. Output: `captures/YYYY-MM-DD-session.ndjson`.
- **CaptureReplayLoader** (`tests/SessionReplay/CaptureReplayLoader.cs`): test-side replay
  engine. Schema: `{"type":"depth"|"bar"|"session_reset", ...}`.
- **5 synthetic sessions** (`tests/fixtures/sessions/session-0[1-5].ndjson`): cover bullish,
  bearish, balanced, DOM-heavy, and iceberg-refill scenarios.

## Deferred Items

- ENG-06 LVN lifecycle and GEX integration → Phase 18
- Live session capture validation (requires running NT8 instance) → Phase 18
- Legacy ABS/EXH static class removal → Phase 18
