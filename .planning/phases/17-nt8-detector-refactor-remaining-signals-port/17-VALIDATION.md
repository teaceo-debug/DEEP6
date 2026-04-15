---
phase: 17
slug: nt8-detector-refactor-remaining-signals-port
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-15
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

Wave 0 note: This phase's Wave 0 (test infrastructure bootstrap) is completed by 17-01 Task 3 (net8.0 NUnit project + first fixtures). All subsequent tasks run against that infrastructure.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | NUnit 3.14 + dotnet test (net8.0) |
| **Config file** | `ninjatrader/tests/ninjatrader.tests.csproj` |
| **Quick run command** | `dotnet test ninjatrader/tests/ --filter Category=quick` |
| **Full suite command** | `dotnet test ninjatrader/tests/` |
| **Estimated runtime** | ~60 seconds (full suite at end of Phase 17) |

---

## Sampling Rate

- **After every task commit:** Filtered run scoped to the task's signal ID / detector (e.g. `dotnet test --filter "FullyQualifiedName~AbsorptionDetector"` — the same command already in each task's `<verify><automated>` block)
- **After every plan wave:** Full suite run `dotnet test ninjatrader/tests/`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds for full suite; filtered runs ~5-15s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | infra (registry, SignalFlagBits, math utils, feature flag) | N/A — no security model for detector port | N/A | unit (structural greps) | `grep -l "interface ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Registry/ISignalDetector.cs && grep -l "class DetectorRegistry" ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs && grep -l "class SessionContext" ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs && grep -l "public const int IMB_01 = 12" ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs && grep -l "public const int VOLP_03 = 48" ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs && grep -l "public const int ENG_02 = 52" ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs && grep -l "public static class LeastSquares" ninjatrader/Custom/AddOns/DEEP6/Math/LeastSquares.cs && grep -l "public static double Distance" ninjatrader/Custom/AddOns/DEEP6/Math/Wasserstein.cs && grep -l "UseNewRegistry" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` | ✅ after task | ⬜ pending |
| 17-01-02 | 01 | 1 | infra (ABS/EXH migration) | N/A | N/A | unit (structural greps) | `grep -l "class AbsorptionDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs && grep -l "class ExhaustionDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs && ! grep -rE "using NinjaTrader\.(Cbi\|Data\|Gui\|NinjaScript\.Indicators)" ninjatrader/Custom/AddOns/DEEP6/Detectors/` | ✅ after task | ⬜ pending |
| 17-01-03 | 01 | 1 | infra (Wave 0 — NUnit project + first fixtures) | N/A | N/A | unit (NUnit smoke — ABS-01, EXH-01, LeastSquares) | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo --verbosity quiet` | ✅ after task | ⬜ pending |
| 17-02-01 | 02 | 2 | infra (ABS/EXH fixtures parity coverage) | N/A | N/A | parity (NUnit fixture-driven) | `for f in ninjatrader/tests/fixtures/absorption/abs-02-passive.json ...; do python3 -c "import json;json.load(open('$f'))" \|\| exit 1; done && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~AbsorptionParity\|FullyQualifiedName~ExhaustionParity" --nologo` | ✅ after task | ⬜ pending |
| 17-02-02 | 02 | 2 | ENG-07 (feature-flag wiring precursor) + parity gate | N/A | N/A | parity (legacy-vs-registry) | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~LegacyVsRegistryParity" --nologo && grep -q "PARITY: PASS" .planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-02-PARITY-REPORT.md && grep -q "if (UseNewRegistry" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && grep -q "AccountWhitelist\|IsAccountAllowed" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` | ✅ after task | ⬜ pending |
| 17-03-01 | 03 | 3 | IMB-01, IMB-06, IMB-08, AUCT-02 | N/A | N/A | unit (fixture-driven) | `grep -l "class ImbalanceDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && grep -l "class AuctionDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/AuctionDetector.cs && grep -E '"IMB-01"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && grep -E '"IMB-06"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && grep -E '"IMB-08"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && grep -E 'TickSize' ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ImbalanceDetector\|FullyQualifiedName~AuctionDetector" --nologo` | ✅ after task | ⬜ pending |
| 17-03-02 | 03 | 3 | DELT-01, DELT-02, DELT-03, DELT-05, DELT-09 | N/A | N/A | unit (fixture-driven + multi-bar) | `grep -l "class DeltaDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && grep -E '"DELT-01"\|"DELT-02"\|"DELT-03"\|"DELT-05"\|"DELT-09"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && grep -E 'CvdHistory\|DeltaHistory' ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~DeltaDetector" --nologo` | ✅ after task | ⬜ pending |
| 17-03-03 | 03 | 3 | VOLP-02, VOLP-03, VOLP-06 + Wave 3 registration | N/A | N/A | unit (fixture-driven) + integration (registry registration) | `grep -l "class VolPatternDetector : ISignalDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs && grep -E '"VOLP-02"\|"VOLP-03"\|"VOLP-06"' ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs && grep -E "Register\(new ImbalanceDetector" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && grep -E "Register\(new DeltaDetector" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && grep -E "Register\(new AuctionDetector" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && grep -E "Register\(new VolPatternDetector" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo` | ✅ after task | ⬜ pending |
| 17-04-01 | 04 | 4 | IMB-02, IMB-03, IMB-04, IMB-05, IMB-07, IMB-09, AUCT-01, AUCT-03, AUCT-04, AUCT-05 | N/A | N/A | unit (fixture-driven + tier-classification) | `grep -E '"IMB-02"\|"IMB-03"\|"IMB-04"\|"IMB-05"\|"IMB-07"\|"IMB-09"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs && grep -E '"AUCT-01"\|"AUCT-03"\|"AUCT-04"\|"AUCT-05"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/AuctionDetector.cs && grep -E "UnfinishedLevels\|ImbalanceHistory" ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ImbalanceDetector\|FullyQualifiedName~AuctionDetector" --nologo` | ✅ after task | ⬜ pending |
| 17-04-02 | 04 | 4 | DELT-04, DELT-06, DELT-07, DELT-11, VOLP-01, VOLP-04, VOLP-05 | N/A | N/A | unit (fixture-driven + monotonic-POC regression) | `grep -E '"DELT-04"\|"DELT-06"\|"DELT-07"\|"DELT-11"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && grep -E '"VOLP-01"\|"VOLP-04"\|"VOLP-05"' ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~DeltaDetector\|FullyQualifiedName~VolPatternDetector" --nologo` | ✅ after task | ⬜ pending |
| 17-04-03 | 04 | 4 | TRAP-01, TRAP-02, TRAP-03, TRAP-04 + TrapDetector registration | N/A | N/A | unit (fixture-driven) + integration | See 17-04 Task 3 `<verify><automated>` block (TrapDetector greps + dotnet test filtered on TrapDetector) | ✅ after task | ⬜ pending |
| 17-05-01 | 05 | 5 | DELT-08, DELT-10, TRAP-05 + polyfit numeric parity | N/A | N/A | unit + numeric-parity (vs numpy.polyfit) | `grep -E '"DELT-08"\|"DELT-10"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && grep -E '"TRAP-05"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs && grep -E "LeastSquares\.Fit1" ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs && grep -E "LeastSquares\.Fit1" ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs && python3 -c "import json;assert len(json.load(open('ninjatrader/tests/Parity/fixtures/polyfit-cases.json'))) >= 10" && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~DeltaHard\|FullyQualifiedName~TrapHard\|FullyQualifiedName~PolyfitVsNumpy" --nologo` | ✅ after task | ⬜ pending |
| 17-05-02 | 05 | 5 | ENG-02, ENG-03, ENG-04 + Wasserstein parity + IcebergDetector.MarkAbsorptionZone wiring | N/A | N/A | unit + numeric-parity (vs scipy) + cross-detector wiring | `grep -l "class TrespassDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/TrespassDetector.cs && grep -l "class CounterSpoofDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/CounterSpoofDetector.cs && grep -l "class IcebergDetector" ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/IcebergDetector.cs && grep -E '"ENG-02"' ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/TrespassDetector.cs && grep -E 'Wasserstein\.Distance' ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/CounterSpoofDetector.cs && grep -E 'Stopwatch' ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/IcebergDetector.cs && grep -E "public void MarkAbsorptionZone" ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/IcebergDetector.cs && grep -E "_icebergDetector\?\.MarkAbsorptionZone" ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs && python3 -c "import json;assert len(json.load(open('ninjatrader/tests/Parity/fixtures/wasserstein-cases.json'))) >= 10" && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~EngineDetectors\|FullyQualifiedName~WassersteinVsScipy" --nologo` | ✅ after task | ⬜ pending |
| 17-05-03 | 05 | 5 | ENG-05, ENG-06, ENG-07 + registration ordering | N/A | N/A | unit + integration (registration order) | See 17-05 Task 3 `<verify><automated>` block | ✅ after task | ⬜ pending |
| 17-05-04 | 05 | 5 | Capture harness + 5-session replay parity + flag flip + legacy Obsolete marking | N/A | N/A | integration (NDJSON replay) + parity gate + structural | `grep -l "class CaptureHarness" ninjatrader/Custom/Indicators/DEEP6/CaptureHarness.cs && grep -l "class CaptureReplayLoader" ninjatrader/tests/Parity/CaptureReplayLoader.cs && grep -l "class SessionReplayParityTests" ninjatrader/tests/Parity/SessionReplayParityTests.cs && ls ninjatrader/tests/fixtures/sessions/*.ndjson 2>/dev/null \| wc -l \| awk '{if ($1 < 5) exit 1}' && grep -E "PHASE 17 PARITY: PASS" .planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-05-PARITY-REPORT.md && grep -E "UseNewRegistry.*=.*true" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs && grep -E "\[Obsolete" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs && dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo` | ✅ after task | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `ninjatrader/tests/ninjatrader.tests.csproj` — net8.0 NUnit 3.14 test project (created by 17-01 Task 3)
- [ ] `ninjatrader/tests/fixtures/absorption/abs-01-classic.json` — first ABS fixture (17-01 Task 3)
- [ ] `ninjatrader/tests/fixtures/exhaustion/exh-01-zero-print.json` — first EXH fixture (17-01 Task 3)
- [ ] `ninjatrader/tests/Detectors/AbsorptionDetectorTests.cs`, `ExhaustionDetectorTests.cs`, `Math/LeastSquaresTests.cs` — smoke tests (17-01 Task 3)

Wave 0 completion marker: 17-01 Task 3's `dotnet test` exits 0 on macOS. All subsequent tasks depend on this infrastructure; they add fixtures + tests into the existing csproj Compile globs.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live NT8 strategy loads DEEP6Strategy with UseNewRegistry=true after Phase 17 close | 17-05 T4 (merged) flag flip | Requires NT8 runtime + connected feed | Open NinjaTrader 8, add DEEP6Strategy to chart, verify property defaults to true, verify ABS/EXH still fire against live tape |
| Live capture harness records NDJSON during paper session | 17-05 T4 CaptureHarness wire-up | Requires live Rithmic feed | Phase 19 operator task; out-of-scope for Phase 17 automated verification |

*All 44 signal-fire behaviors have automated fixture-driven verification. Only runtime-wiring sanity checks are manual.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (Wave 0 = 17-01 T3)
- [x] No watch-mode flags
- [x] Feedback latency < 60s for full suite; filtered runs <15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-15
