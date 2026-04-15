---
phase: 17-nt8-detector-refactor-remaining-signals-port
verified: 2026-04-15T23:00:00Z
status: gaps_found
score: 3/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "DEEP6Footprint.cs split into modular files per detector family; no single file exceeds 2000 LOC"
    status: partial
    reason: "DEEP6Footprint.cs is 2002 lines — 2 lines over the 2000 LOC limit specified in ROADMAP SC1. All new detector files are well under 2000 LOC (largest is DeltaDetector.cs at 505 lines). The file was intentionally NOT split further (legacy code + GEX client remain) but the raw LOC count violates the success criterion as stated."
    artifacts:
      - path: "ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs"
        issue: "2002 lines — 2 over the 2000 LOC cap in ROADMAP SC1"
    missing:
      - "Trim or split 2 lines from DEEP6Footprint.cs to bring it to 2000 LOC or below, OR confirm the intent was that NO NEW per-family detector file exceeds 2000 LOC (in which case the criterion is met and should be overridden)"

  - truth: "DEEP6Strategy.cs compiles without error in NT8 (no duplicate property)"
    status: failed
    reason: "DEEP6Strategy.cs contains two declarations of 'public bool UseNewRegistry { get; set; }' — at line 698 (Wave 3 artifact, no default initializer) and line 805 (Wave 5 addition, = true). This is CS0102 in standard C#. The dotnet test project passes because it does not compile DEEP6Strategy.cs. NT8's C# compiler WILL reject this file, preventing the strategy from loading in NinjaTrader 8."
    artifacts:
      - path: "ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs"
        issue: "Duplicate property 'UseNewRegistry' at lines 698 and 805 — CS0102 compile error in NT8"
    missing:
      - "Remove the stale line 698 declaration (no default, stale Wave 3 Display Name 'Use New Registry (Wave 3/4)'). Keep only the line 805 declaration (= true, GroupName='DEEP6 Migration') which is the Wave 5 canonical version."

  - truth: "All 34 ported signals fire on live NT8 Rithmic feed bar-for-bar matching Python reference on a recorded session replay (ROADMAP SC3)"
    status: failed
    reason: "The Wave 5 parity report (17-05-PARITY-REPORT.md) documents parity on 5 SYNTHETIC sessions only. The ROADMAP SC3 says 'on a live NT8 Rithmic feed bar-for-bar matching the Python reference engine on a recorded session replay.' No real NT8+Rithmic session captures were recorded and replayed. The Wave 5 parity report explicitly defers 'Live session capture validation (requires running NT8 instance) → Phase 18'. Additionally, the DEEP6Strategy.cs duplicate property bug (SC above) means the strategy cannot load in NT8 to run any live sessions."
    artifacts:
      - path: ".planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-05-PARITY-REPORT.md"
        issue: "5 sessions tested were synthetic (generated fixtures), not recorded from live NT8 Rithmic feed"
      - path: "ninjatrader/Custom/Indicators/DEEP6/CaptureHarness.cs"
        issue: "Capture harness exists but no captures have been recorded from a real NT8 session"
    missing:
      - "Record at least 1 live NQ session via CaptureHarness.cs on a running NT8+Rithmic connection"
      - "Run SessionReplayParityTests against real captures"
      - "Document signal-count delta per signal type per session in 17-05-PARITY-REPORT.md (or a new report)"
human_verification:
  - test: "Load DEEP6Strategy.cs in NinjaTrader 8 with the duplicate property bug fixed and confirm the strategy compiles and loads without CS0102 error"
    expected: "Strategy appears in NinjaTrader Strategy Manager without compile errors; UseNewRegistry property is visible in strategy properties panel with default=true"
    why_human: "NT8 compilation requires a running NinjaTrader 8 instance — cannot verify programmatically on macOS"
  - test: "Enable CaptureHarness in DEEP6Footprint indicator on a live Rithmic NQ feed, record at least one 1-hour RTH session, replay through SessionReplayParityTests, verify all 44 detectors produce signal counts within ±2 of the Python reference"
    expected: "17-05-PARITY-REPORT.md updated with real-session captures; signal count delta ≤ ±2 per type per session for all 44 signal IDs"
    why_human: "Requires live Rithmic connection, running NT8 instance, and manual comparison vs Python reference engine output — cannot verify programmatically"
  - test: "Confirm no regression in massive.com GEX overlay: with UseNewRegistry=true, GEX levels still render on DEEP6Footprint chart (ROADMAP SC5)"
    expected: "GEX levels (MajorPositive, MajorNegative, GammaFlip) continue to render correctly on the footprint chart; no NullReferenceException or missing overlay after Phase 17 changes"
    why_human: "GEX overlay rendering requires live NT8 UI — cannot inspect visually from codebase alone"
---

# Phase 17: NT8 Detector Refactor + Remaining Signals Port — Verification Report

**Phase Goal:** DEEP6Footprint.cs monolith split into per-family detector files behind ISignalDetector registry; migrate 10 live signals (ABS-01..04, ABS-07, EXH-01..06) into new layout; port 34 remaining signals (IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07) from Python reference into NinjaScript; all firing on live NT8 Rithmic NQ feed.
**Verified:** 2026-04-15T23:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| SC1 | DEEP6Footprint.cs split into modular files per detector family; no single file exceeds 2000 LOC | PARTIAL | All 12 new detector files are 121–505 LOC. DEEP6Footprint.cs is 2002 lines — 2 over the 2000 LOC cap. All registry, math, and detector files are well within the limit. |
| SC2 | ISignalDetector interface + detector registry implemented; EvaluateEntry iterates the registry — no hardcoded ABS+EXH routing | PARTIAL | Registry exists and is called. DEEP6Strategy UseNewRegistry=true routes ABS+EXH through DetectorRegistry.EvaluateBar(). All 34 new signals also fire via the same registry call. However: (a) EvaluateEntry() still accepts only List<AbsorptionSignal>/List<ExhaustionSignal> — the 34 new signals are logged but do not gate orders; (b) there is a double EvaluateBar() call per bar (lines 334 and 384) when UseNewRegistry=true that would advance stateful detectors' rolling-history queues twice; (c) the duplicate UseNewRegistry property is a C# compile error blocking NT8 loading. Phase 17 plans explicitly deferred full order gating of the 34 new signals to Phase 18 scoring/confluencer. For the narrow reading of "registry is the integration point, no raw static calls," SC2 is substantially met except for the compile error. |
| SC3 | All 34 ported signals fire on live NT8 Rithmic feed bar-for-bar matching Python reference on recorded session replay (tolerance-bounded parity) | FAILED | Wave 5 parity used 5 synthetic NDJSON sessions. Live session capture deferred to Phase 18 per 17-05-PARITY-REPORT.md. The compile error in DEEP6Strategy.cs also blocks running the strategy in NT8. |
| SC4 | Per-family unit test fixtures committed under ninjatrader/tests/ | VERIFIED | 53 JSON fixtures across absorption (5), exhaustion (6), imbalance (9), auction (5), delta (11), volpattern (6), trap (5), engines (7) + 5 NDJSON session fixtures. All families covered. 180/180 NUnit tests pass. |
| SC5 | No regression in existing 10 signals (ABS-01..04, ABS-07, EXH-01..06) or GEX overlay behavior | PARTIAL | The 10 legacy signals: LegacyVsRegistryParityTests passes (49 parity tests, 0 divergences). GEX code (MassiveGexClient, lines 685–2002 in DEEP6Footprint.cs) is intact with 5 references confirmed present. Risk gates (ApprovedAccountName, NewsBlackouts, RthStartHour/End, DailyLossCapDollars, _killSwitch) all confirmed present and unchanged at baseline count. HOWEVER: the duplicate UseNewRegistry property (lines 698 + 805) is a CS0102 compile error that prevents NT8 from loading DEEP6Strategy.cs — blocking the strategy from running on live feed at all, which constitutes a regression in the ability to use Phase 16 signals live. |

**Score:** 1.5/5 fully verified (SC4 clean PASS; SC1/SC2/SC5 partial; SC3 failed)

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Live NT8 Rithmic feed session capture + replay parity with real sessions | Phase 18 | Phase 17-05-PARITY-REPORT.md: "Live session capture validation (requires running NT8 instance) → Phase 18"; Phase 18 SC3: "Replay harness consumes recorded tick/depth data and emits per-bar signal + score output" |
| 2 | All 34 new signals gate orders via EvaluateEntry / full confluencer | Phase 18 | Phase 17 Wave 4 decision: "registry results logged only, do not gate orders until Wave 5 confluencer wiring"; Phase 18 goal: "Two-layer confluence scorer ported from Python into NinjaScript" |

### Required Artifacts

| Artifact | Expected | Status | Details |
|---------|----------|--------|---------|
| `ninjatrader/Custom/AddOns/DEEP6/Registry/ISignalDetector.cs` | Interface definition | VERIFIED | Present, contains `interface ISignalDetector` |
| `ninjatrader/Custom/AddOns/DEEP6/Registry/DetectorRegistry.cs` | Sequential registry | VERIFIED | Present, contains `class DetectorRegistry` |
| `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs` | Shared per-session state | VERIFIED | Present, contains `class SessionContext`, `new double[40]` DOM arrays |
| `ninjatrader/Custom/AddOns/DEEP6/Registry/SignalFlagBits.cs` | 64-bit bit assignments 0–57 | VERIFIED | Present, all signal constants confirmed (IMB_01=12, ENG_07=57) |
| `ninjatrader/Custom/AddOns/DEEP6/Math/LeastSquares.cs` | Hand-rolled polyfit | VERIFIED | Present, contains `public static class LeastSquares`, `Fit1` method |
| `ninjatrader/Custom/AddOns/DEEP6/Math/Wasserstein.cs` | W1 distance | VERIFIED | Present, contains `public static double Distance` |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs` | ABS-01..04, ABS-07 | VERIFIED | Present, 234 LOC, `class AbsorptionDetector : ISignalDetector`, all 4 SignalId literals |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs` | EXH-01..06 | VERIFIED | Present, 388 LOC, all 6 EXH SignalId literals, `_cooldown` field |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Imbalance/ImbalanceDetector.cs` | IMB-01..09 | VERIFIED | Present, 453 LOC, all 9 IMB SignalId literals, TickSize diagonal direction guard |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Delta/DeltaDetector.cs` | DELT-01..11 | VERIFIED | Present, 505 LOC, all 11 DELT SignalId literals, CvdHistory/DeltaHistory SessionContext integration |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Auction/AuctionDetector.cs` | AUCT-01..05 | VERIFIED | Present, 274 LOC, all 5 AUCT SignalId literals |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/VolPattern/VolPatternDetector.cs` | VOLP-01..06 | VERIFIED | Present, 330 LOC, all 6 VOLP SignalId literals |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Trap/TrapDetector.cs` | TRAP-01..05 | VERIFIED | Present, 361 LOC, all 5 TRAP SignalId literals |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/TrespassDetector.cs` | ENG-02 | VERIFIED | Present, 156 LOC, `class TrespassDetector : ISignalDetector` |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/CounterSpoofDetector.cs` | ENG-03 | VERIFIED | Present, 144 LOC, `class CounterSpoofDetector : ISignalDetector` |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/IcebergDetector.cs` | ENG-04 | VERIFIED | Present, 220 LOC, `class IcebergDetector : ISignalDetector`, IAbsorptionZoneReceiver |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/MicroProbDetector.cs` | ENG-05 (LAST) | VERIFIED | Present, 128 LOC, `class MicroProbDetector : ISignalDetector`, registered last in DEEP6Strategy |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/VPContextDetector.cs` | ENG-06 | VERIFIED | Present, 121 LOC, POC proximity only (LVN/GEX deferred to Phase 18) |
| `ninjatrader/Custom/AddOns/DEEP6/Detectors/Engines/SignalConfigScaffold.cs` | ENG-07 config scaffold | VERIFIED | Present, contains `class SignalConfigScaffold`, `BuildDetectors()` factory |
| `ninjatrader/Custom/Indicators/DEEP6/CaptureHarness.cs` | NDJSON capture writer | VERIFIED | Present, contains `class CaptureHarness` |
| `ninjatrader/tests/ninjatrader.tests.csproj` | net8.0 NUnit project | VERIFIED | Present, `<TargetFramework>net8.0</TargetFramework>`, NUnit 3.14.0 |
| `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` | Compiles with UseNewRegistry=true | STUB | Present but has duplicate `UseNewRegistry` property at lines 698 and 805 — CS0102 compile error in NT8 |
| `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` | ≤ 2000 LOC | PARTIAL | 2002 lines — 2 over the limit. Legacy ABS/EXH code marked `[System.Obsolete]`. GEX client intact. |
| `.planning/phases/17-nt8-detector-refactor-remaining-signals-port/17-05-PARITY-REPORT.md` | PHASE 17 PARITY: PASS | VERIFIED (synthetic only) | Present, `PHASE 17 PARITY: PASS` / `PARITY: PASS`, 180/180 tests. Sessions are synthetic, not live Rithmic captures. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| DEEP6Strategy.cs (UseNewRegistry=true) | DetectorRegistry.EvaluateBar() | `if (UseNewRegistry && _registry != null)` at line 322 | WIRED | All 12 detectors registered in Configure; EvaluateBar called for ABS/EXH extraction at line 334 |
| DEEP6Strategy.cs | All 34 new detectors (logging path) | `if (_registry != null)` at line 377, second EvaluateBar call | WIRED (logging only) | Double-call per bar is a potential stateful-detector state-advancement bug |
| DEEP6Strategy.cs UseNewRegistry=true | Legacy path suppressed | else-branch at line 369 | WIRED | Legacy AbsorptionDetector.Detect() + _exhDetector.Detect() only called when UseNewRegistry=false |
| ninjatrader.tests.csproj | All AddOns/DEEP6/**/*.cs sources | `<Compile Include>` globs | WIRED | Correct globs for Registry, Math, all Detector families |
| CaptureHarness.cs | NDJSON output on disk | `captures/YYYY-MM-DD-session.ndjson` | WIRED (code only) | CaptureHarness exists; no real captures recorded yet (deferred to Phase 18) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---------|---------------|--------|--------------------|--------|
| AbsorptionDetector.OnBar() | FootprintBar.Levels | Passed from DEEP6Strategy via _registry.EvaluateBar(prev, _session) | YES — bar.Levels populated from NT8 OnMarketData in DEEP6Footprint.cs | FLOWING |
| DeltaDetector.OnBar() | session.DeltaHistory / CvdHistory | SessionContext queues pushed per bar | YES — queues pushed at end of OnBar per design | FLOWING |
| MicroProbDetector.OnBar() | session.LastTrespassProbability + LastIcebergSignals | Written by TrespassDetector (ENG-02) and IcebergDetector (ENG-04) in same bar cycle | YES — registration order enforced (ENG-05 last) | FLOWING |
| VPContextDetector.OnBar() | session.PocHistory | Pushed by VolPatternDetector or DEEP6Strategy-side logic | UNCERTAIN — need to verify PocHistory is populated by DEEP6Strategy before EvaluateBar | UNCERTAIN |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 180 NUnit tests pass | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo --verbosity quiet` | `Passed! - Failed: 0, Passed: 180, Skipped: 0, Total: 180, Duration: 66 ms` | PASS |
| All 44 signal IDs present in detector code | `grep -roE '"(ABS\|EXH\|IMB\|DELT\|AUCT\|TRAP\|VOLP\|ENG)-[0-9]+"' Detectors/` | 52 unique signal literals found (ABS-01..07, EXH-01..06, IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..06) | PASS |
| No NT8 using directives in detector classes | `grep -r "using NinjaTrader\.(Cbi\|Data\|Gui\|NinjaScript\.Indicators)" Detectors/` | No matches | PASS |
| Duplicate UseNewRegistry in DEEP6Strategy.cs | `grep -c "public bool UseNewRegistry" DEEP6Strategy.cs` | 2 — duplicate found at lines 698 and 805 | FAIL |
| DEEP6Footprint.cs LOC count | `wc -l DEEP6Footprint.cs` | 2002 lines — 2 over 2000 LOC cap | FAIL |
| LegacyVsRegistryParityTests | `dotnet test --filter "LegacyVsRegistryParity"` | 13/13 PASS (included in 180 total) | PASS |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| IMB-01..09 | 17-03, 17-04 | All 9 imbalance types | SATISFIED | ImbalanceDetector.cs, 9 fixtures, tests passing |
| DELT-01..11 | 17-03, 17-04, 17-05 | All 11 delta types | SATISFIED | DeltaDetector.cs, 11 fixtures, tests passing |
| AUCT-01..05 | 17-03, 17-04 | All 5 auction types | SATISFIED | AuctionDetector.cs, 5 fixtures, tests passing |
| TRAP-01..05 | 17-04, 17-05 | All 5 trap types | SATISFIED | TrapDetector.cs, 5 fixtures, tests passing |
| VOLP-01..06 | 17-03, 17-04 | All 6 volume pattern types | SATISFIED | VolPatternDetector.cs, 6 fixtures, tests passing |
| ENG-02 | 17-05 | TrespassDetector | SATISFIED | TrespassDetector.cs, eng-02-trespass.json, tests passing |
| ENG-03 | 17-05 | CounterSpoofDetector | SATISFIED | CounterSpoofDetector.cs, eng-03-counter-spoof.json, Wasserstein parity tests |
| ENG-04 | 17-05 | IcebergDetector | SATISFIED | IcebergDetector.cs, eng-04-iceberg*.json, IAbsorptionZoneReceiver wired |
| ENG-05 | 17-05 | MicroProbDetector | SATISFIED | MicroProbDetector.cs, eng-05-micro-prob.json, registered LAST |
| ENG-06 | 17-05 | VPContextDetector (POC only) | SATISFIED (partial scope) | VPContextDetector.cs, eng-06-vp-context.json; LVN+GEX deferred to Phase 18 per plan |
| ENG-07 | 17-05 | SignalConfigScaffold | SATISFIED | SignalConfigScaffold.cs, BuildDetectors() factory |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` | 698 | Duplicate property `public bool UseNewRegistry { get; set; }` — stale Wave 3 artifact | BLOCKER | CS0102 compile error in NT8; strategy cannot load; all Phase 16 live signals blocked |
| `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` | 376–392 | Second `_registry.EvaluateBar()` call for logging — runs AFTER the first call at line 334 | WARNING | Stateful detectors (DeltaDetector, TrapDetector) advance rolling history queues twice per bar when UseNewRegistry=true; may cause off-by-one on sequential signals like DELT-05, TRAP-05 |
| `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` | entire file | 2002 lines — 2 over 2000 LOC cap | WARNING | Technically violates ROADMAP SC1; marginal overage; no functional impact |

### Human Verification Required

#### 1. NT8 Compile + Strategy Load

**Test:** Remove the duplicate `UseNewRegistry` at line 698 (stale Wave 3 version), reload DEEP6Strategy.cs in NinjaTrader 8. Confirm no compile error and the strategy appears in the NinjaScripts list.
**Expected:** Strategy compiles clean; `UseNewRegistry` property visible in Properties with default `true` (GroupName "DEEP6 Migration"); no CS0102 error in NT8 Output window.
**Why human:** NT8 C# compilation requires a running NinjaTrader 8 instance on Windows — cannot run on macOS command line.

#### 2. Live Rithmic Feed Session Capture + Replay Parity

**Test:** Start DEEP6Footprint indicator with CaptureHarness enabled on NT8 with Rithmic NQ live data feed. Record one full RTH session (9:35am–3:50pm ET). Run the recorded NDJSON through `SessionReplayParityTests` and compare signal counts vs Python reference engine output on the same bars.
**Expected:** Per ROADMAP SC3 — all 34 ported signals fire bar-for-bar; signal count delta ≤ ±2 per signal type per session; parity report updated with real-capture verdict.
**Why human:** Requires live Rithmic connection + running NT8 instance; cannot simulate real Level 2 DOM callbacks on macOS without NT8+Rithmic.

#### 3. GEX Overlay Regression Check

**Test:** With UseNewRegistry=true (default after Phase 17), load DEEP6Footprint on an NQ chart with valid MASSIVE_API_KEY. Confirm GEX levels (gamma flip, major positive/negative nodes) still render as colored horizontal lines on the footprint chart.
**Expected:** No NullReferenceException or missing GEX paint in NT8 Output; GEX overlay visually identical to pre-Phase-17 behavior.
**Why human:** GEX overlay is visual rendering in NT8 chart — cannot inspect from codebase; requires running NT8 UI.

### Gaps Summary

Two actionable code gaps block goal achievement:

**Gap 1 — CS0102 duplicate property (BLOCKER):** `DEEP6Strategy.cs` has `UseNewRegistry` declared twice. The Wave 3 property at line 698 was not removed when Wave 5 added the proper one at line 805. This compiles fine in the `dotnet test` project (which excludes DEEP6Strategy.cs) but will fail NT8's C# compiler with CS0102. Fix: delete lines 695–698 (the stale Wave 3 declaration with `GroupName="1. Safety"` and no default initializer). Keep lines 801–805 (the Wave 5 declaration with `GroupName="DEEP6 Migration"` and `= true` default).

**Gap 2 — 2 LOC over limit (MARGINAL):** `DEEP6Footprint.cs` is 2002 lines vs the 2000 LOC cap in ROADMAP SC1. This is 2 blank lines or comments. Fix: trim 2 lines anywhere in the file, or document that the 2000 LOC cap was intended to apply to newly-created detector files only (which are all well under 600 LOC) and add an override for the legacy indicator file.

**Gap 3 — SC3 live Rithmic parity (HUMAN NEEDED):** Phase 17 delivered synthetic-session parity. ROADMAP SC3 specifically calls for "live NT8 Rithmic feed bar-for-bar matching the Python reference engine on a recorded session replay." Wave 5 deferred this to Phase 18 per the parity report. This is addressed in Phase 18 roadmap SC3 ("Replay harness consumes recorded tick/depth data"). The deferred item is documented in the frontmatter above.

---

_Verified: 2026-04-15T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
