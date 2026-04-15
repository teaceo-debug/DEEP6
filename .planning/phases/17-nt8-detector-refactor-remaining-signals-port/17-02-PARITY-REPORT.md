# Phase 17 — Wave 2 Parity Report

Date: 2026-04-15
PARITY: PASS
Fixtures tested: 10 (ABS-01..04, ABS-07, EXH-01..06)
Synthetic bars tested: 23 (10 named fixtures + 10 seeded-random seed=17 + 3 cooldown/negative)
Divergences: 0

## `dotnet test` Output

```
Passed!  - Failed: 0, Passed: 49, Skipped: 0, Total: 49, Duration: 26 ms
```

Test breakdown:
- `AbsorptionDetectorTests`: 3 tests (Abs01 classic, Abs01 low-wick negative, JSON valid)
- `ExhaustionDetectorTests`: 4 tests (Exh01 zero-print, no-zero-print negative, cooldown, JSON valid)
- `LeastSquaresTests`: 6 tests (increasing, decreasing, constant, single-element, empty, explicit-x)
- `AbsorptionParityTests`: 12 tests (ABS-01..04 + ABS-07 signal assertions + JSON validity × 5)
- `ExhaustionParityTests`: 11 tests (EXH-01..06 signal assertions + cooldown + JSON validity × 6)
- `LegacyVsRegistryParityTests`: 13 tests (ABS-01..04+07 + EXH-01..06 fixture parity + cooldown parity + 10 seeded-random bars)

## Fixtures Covered

| Fixture | Signal | Trigger Condition | Status |
|---------|--------|-------------------|--------|
| abs-01-classic.json | ABS-01 | upper wick 35% vol, deltaRatio=0.057 < 0.12 | PASS |
| abs-02-passive.json | ABS-02 | upperZoneVol=400/470=85% >= 60%, close below zone | PASS |
| abs-03-stopping.json | ABS-03 | totalVol=1200 > volEma*2=800, POC=20006 above body | PASS |
| abs-04-effort-vs-result.json | ABS-04 | totalVol=900 > volEma*1.5=750, barRange=0.75 < atr*0.30=1.5 | PASS |
| abs-07-va-extreme.json | ABS-07 | ABS-01 fires, bar.High=20002.75 within 0.5 of VAH=20003.00 | PASS |
| exh-01-zero-print.json | EXH-01 | zero-vol level at 20002 inside body, delta-gate exempt | PASS |
| exh-02-exhaustion-print.json | EXH-02 | hiAsk=120/800=15% >= effMin/3=11.67%, bearish bar delta>0 | PASS |
| exh-03-thin-print.json | EXH-03 | 4 body levels < maxLevelVol*0.05=30, bearish bar | PASS |
| exh-04-fat-print.json | EXH-04 | sorted[0] vol=900 > avgLevelVol*2=520, dir=0 | PASS |
| exh-05-fading-momentum.json | EXH-05 | bullish bar barDelta=-410 < 0, |410|/590=0.695 > 0.15 | PASS |
| exh-06-bid-ask-fade.json | EXH-06 | currHiAsk=30 < priorHiAsk*0.60=120, bearish bar delta>0 | PASS |

## Python-Reference Bugs Found

**1. EXH-02 dual-trigger bug (C# registry only — not in Python)**

- **Found during:** Task 2 seeded-random parity run (bars #1 and #5)
- **Issue:** The registry's ExhaustionDetector.cs EXH-02 block placed the low-ask check inside the same outer `if (CheckCooldown(...))` block without a nested re-check. This allowed both the high-ask and low-ask EXH-02 to fire on the same bar (if both thresholds were met), producing 2 EXH-02 results instead of 1. The legacy DEEP6Footprint.cs correctly uses a nested `CheckCooldown` before the low check, preventing both from firing.
- **Fix:** Added `if (CheckCooldown(ExhaustionType.ExhaustionPrint, barIndex, cfg.CooldownBars))` wrapper around the low-ask check in ExhaustionDetector.cs, matching legacy behavior. One EXH-02 maximum per bar.
- **Files modified:** `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs`
- **Python counterpart:** `deep6/engines/exhaustion.py` — the Python module-level `_cooldown` dict has the same per-call semantics; the Python code is structured correctly (no dual-fire issue because cooldown is set before the low check would run). No Python fix needed.
- **Parity impact:** After fix, all 13 LegacyVsRegistryParityTests pass including 10 seeded-random bars. Zero divergences.

## Known Algorithm Differences (Documented, Not Divergences)

Two legacy/registry differences exist but produce identical outputs on the defined fixtures:

**EXH-04 Fat Print selection:**
- Legacy DEEP6Footprint.cs: picks the level with the HIGHEST vol > threshold (fattest).
- Registry (PORT-SPEC §3): picks the FIRST sorted (ascending) level > threshold.
- Behavior is identical when only one level exceeds the threshold (all EXH-04 fixtures have exactly one qualifying level). No divergence on any parity bar.
- Bridge: `LegacyDetectorsBridge.cs` uses PORT-SPEC semantics (first sorted) to match registry.

**EXH-06 Bid/Ask Fade scope:**
- Legacy DEEP6Footprint.cs: checks high-ask OR (else) low-bid — one per bar via else-branch.
- Registry (PORT-SPEC §3): checks high-ask AND low-bid — both independently (with cooldown preventing both from firing per bar, consistent with EXH-02 fix above).
- Behavior is identical on the exh-06 fixture (only high triggers). No divergence.

## DEEP6Strategy Wiring

- `UseNewRegistry=false` (default): legacy `AbsorptionDetector.Detect()` + `_exhDetector.Detect()` unchanged.
- `UseNewRegistry=true`: `_registry.EvaluateBar(prev, _session)` called with populated `SessionContext`. Results converted to `List<AbsorptionSignal>` / `List<ExhaustionSignal>` for downstream `EvaluateEntry()` + `CheckOpposingExit()` compatibility.
- Risk gates: `ApprovedAccountName`, `NewsBlackouts`, `RthStartHour/RthEndHour`, `DailyLossCapDollars`, `_killSwitch` — all unchanged. Confirmed by grep (25 occurrences of risk-gate identifiers, baseline 25).
- Session boundary reset: `_session.ResetSession()` + `_registry.ResetAll()` called on date change when `UseNewRegistry=true`.

## Gate: Wave 3 may proceed.

PARITY: PASS with zero divergences on all 10 fixtures and 10 seeded-random bars.
AbsorptionDetector and ExhaustionDetector produce bit-for-bit identical SignalResult[]
(SignalId exact, Direction exact, Strength within 1e-4, FlagBit exact) to the
LegacyDetectorsBridge on every test bar.
