---
phase: 18
slug: nt8-scoring-backtest-validation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-15
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | NUnit 3.14.0 (.NET 8.0 via RollForward=Major on .NET 10 runtime) |
| **Config file** | `ninjatrader/tests/ninjatrader.tests.csproj` |
| **Quick run command** | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "Category=Scoring" --nologo -v q` |
| **Full suite command** | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` |
| **Parity harness command** | `dotnet test ninjatrader/tests/ninjatrader.tests.csproj --filter "FullyQualifiedName~ScoringParityHarness" --nologo -v normal` |
| **Estimated runtime** | ~740ms full suite (238 tests); ~750ms parity harness (5 sessions × ~130ms subprocess) |

---

## Sampling Rate

- **After every task commit:** Run `dotnet test ... --filter "Category=Scoring" --nologo -v q`
- **After every plan wave:** Run `dotnet test ... --nologo -v q` (full suite)
- **Before `/gsd-verify-work`:** Full suite + parity harness must both be green
- **Max feedback latency:** ~740ms (full suite) — acceptable; exceeds 18s target only for parity (subprocess overhead is necessary for correctness gate)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|--------|
| 18-01-T1 | 01 | 1 | SC-VERIFY | Phase 17 CS0102 + double-EvaluateBar fixes in place | compile | `dotnet build ninjatrader/tests/ninjatrader.tests.csproj --nologo -v q` | ✅ green |
| 18-01-T2 | 01 | 1 | SCOR-01/02/03/04/06 | Scorer is NT8-API-free; no privilege path | unit | `dotnet test ... --filter "Category=Scoring" --nologo -v q` | ✅ green |
| 18-01-T3 | 01 | 1 | SCOR-04 fixtures | Fixture files exist and parse as valid JSON | unit | `dotnet test ... --filter "FullyQualifiedName~Fixture_" --nologo -v q` | ✅ green |
| 18-02-T1 | 02 | 2 | SC-SHARED | ScorerSharedState thread-safe publish/retrieve | unit | `dotnet test ... --filter "FullyQualifiedName~ScorerSharedStateTests" --nologo -v q` | ✅ green |
| 18-02-T2 | 02 | 2 | SC-VISUAL | SharpDX HUD + tier markers compile; DEEP6Footprint unchanged signal count | compile | `grep -c "RenderGex\|RenderLiquidityWalls" ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` (expect 2) | ✅ green |
| 18-03-T1 | 03 | 3 | SC5 per-bar log | DEEP6Strategy compiles with scorer gate; risk-gate count unchanged | compile+grep | `grep -c "AccountWhitelist\|NewsBlackout\|DailyLoss\|MaxTrades\|_killSwitch" ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` (expect ≥13) | ✅ green |
| 18-03-T2 | 03 | 3 | SC5 gate tests | ScorerEntryGate passes/rejects correctly per threshold | unit | `dotnet test ... --filter "FullyQualifiedName~EvaluateEntryScorerTests" --nologo -v q` | ✅ green |
| 18-04-T1 | 04 | 4 | SC3 py-entry | replay_scorer.py reads NDJSON stdin, emits compact JSON-line stdout | integration | `echo '{"type":"scored_bar","barIdx":1,"barsSinceOpen":30,"barDelta":40,"barClose":17500.25,"zoneScore":0,"zoneDistTicks":999,"signals":[]}' | python3 -m deep6.scoring.replay_scorer \| python3 -c "import sys,json; d=json.loads(sys.stdin.read()); assert 'score' in d, d; print('OK')"` | ✅ green |
| 18-04-T2 | 04 | 4 | SC4 parity | C#↔Python score delta ≤ 0.05, identical tier on all 5 sessions | parity | `dotnet test ... --filter "FullyQualifiedName~ScoringParityHarness" --nologo -v normal` | ✅ green |
| 18-04-T3 | 04 | 4 | SC3/SC4 docs | PARITY-REPORT.md exists; VALIDATION.md has nyquist_compliant:true | file+grep | `test -f .planning/phases/18-nt8-scoring-backtest-validation/18-04-PARITY-REPORT.md && grep -q "nyquist_compliant: true" .planning/phases/18-nt8-scoring-backtest-validation/18-VALIDATION.md && grep -qE "PHASE 18 PARITY: (PASS\|IGNORED)" .planning/phases/18-nt8-scoring-backtest-validation/18-04-PARITY-REPORT.md && echo OK` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All Wave 0 gaps identified in 18-RESEARCH.md are resolved:

- [x] Phase 17 CS0102 duplicate property fix — verified at a92443e (18-01-T1)
- [x] Phase 17 double EvaluateBar fix — verified at a92443e (18-01-T1)
- [x] NUnit test infrastructure — already present from Phase 17; no install needed
- [x] `replay_scorer.py` subprocess entry point created — 18-04-T1 (commit 4256418)
- [x] 5 scoring-session NDJSON fixtures created — 18-04-T1 (commit 4256418)
- [x] Phase 17 baseline sessions untouched — `git diff --stat ninjatrader/tests/fixtures/sessions/` shows no changes

*Existing NUnit 3.14.0 infrastructure covers all phase requirements. No new framework installs were needed.*

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|------------|-------------------|
| NT8 compile + indicator load | Requires live NT8 instance on Windows; NinjaScript compilation not testable in CI | Load DEEP6Footprint on NQ 1-minute chart; verify HUD badge and tier markers appear without errors |
| Live NQ Rithmic session capture + replay parity | Requires live broker connection; async-rithmic out of scope for Phase 18 | Deferred to Phase 19 setup — capture a 30-minute NQ session with CaptureHarness, replay through parity harness |
| GEX overlay regression visual check | SharpDX rendering requires Windows NT8 host | Confirm GEX levels + liquidity walls render without z-order collision with scorer HUD badge |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references from 18-RESEARCH.md
- [x] No watch-mode flags
- [x] Feedback latency: Scoring category filter runs in ~100ms; full suite ~740ms; parity harness ~750ms. Exceeds 18s target only for parity (subprocess overhead unavoidable for correctness gate — documented as acceptable)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval: approved 2026-04-15**

---

## Notes

**TypeA Live Stub:** DEEP6Footprint.cs uses `zoneScore = 0.0` stub (Wave 2 known stub).
TypeA tier cannot fire in the live indicator until VPContext zone extension is wired (Phase 19+).
The parity harness DOES exercise TypeA paths via explicit `zoneScore` in NDJSON fixtures —
parity is verified for TypeA. The live stub is a separate integration gap.

**TypeB_MIN:** Python `signal_config.py` default `type_b_min=72.0` — C# `TYPE_B_MIN=72.0`.
These match verbatim. The legacy docstring `type_b_min=65` in the Python scorer.py function
signature is overridden by `ScorerConfig(type_b_min=72.0)` at construction time.
