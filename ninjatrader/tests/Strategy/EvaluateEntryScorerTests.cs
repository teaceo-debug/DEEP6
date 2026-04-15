// EvaluateEntryScorerTests: NUnit tests for ScorerEntryGate — the NT8-API-free
// entry gate extracted from DEEP6Strategy.EvaluateEntry in Phase 18-03.
//
// Approach A per plan: test ScorerEntryGate.Evaluate() and BuildLogLine() directly.
// DEEP6Strategy itself is NOT instantiated — it requires an NT8 host runtime.
//
// Coverage:
//   Test 1  — score below threshold → GateOutcome.BelowScore
//   Test 2  — tier below MinTierForEntry (TypeB when min=TypeA) → GateOutcome.BelowTier
//   Test 3  — direction = 0 (ambiguous) → GateOutcome.NoDirection
//   Test 4  — all-pass TypeA long → GateOutcome.Passed
//   Test 5  — scorer result is null → GateOutcome.NoScore
//   Test 6  — TypeA short direction=-1 all-pass → GateOutcome.Passed, direction preserved
//   Test 7  — TypeB at MinTier=TypeB threshold → GateOutcome.Passed (TypeB accepted when min=TypeB)
//   Test 8  — TypeC rejected by MinTierForEntry=TypeB gate → GateOutcome.BelowTier
//   Test 9  — per-bar log format matches expected [DEEP6 Scorer] pattern
//   Test 10 — BuildLogLine returns empty string when scored is null
//
// Risk-gate regression note: RiskGatesPass is an NT8 Strategy method — it cannot be
// tested here without the NT8 host. The gate ordering invariant (ScorerEntryGate BEFORE
// RiskGatesPass BEFORE EnterWithAtm) is enforced by the DEEP6Strategy source structure
// and verified by the dotnet-test compile pass + grep acceptance criteria in 18-03-PLAN.md.
//
// Phase 18-03

using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Strategy
{
    [TestFixture]
    [Category("Scoring")]
    public class EvaluateEntryScorerTests
    {
        // -------------------------------------------------------------------------
        // Helpers
        // -------------------------------------------------------------------------

        private static ScorerResult MakeResult(
            double score,
            SignalTier tier,
            int direction = 1,
            string narrative = "TEST NARRATIVE",
            double entryPrice = 19000.0)
        {
            return new ScorerResult
            {
                TotalScore  = score,
                Tier        = tier,
                Direction   = direction,
                Narrative   = narrative,
                EntryPrice  = entryPrice,
                EngineAgreement  = 1.0,
                CategoryCount    = 5,
                ConfluenceMult   = 1.25,
                ZoneBonus        = 8.0,
                CategoriesFiring = new[] { "absorption", "exhaustion", "delta", "auction", "volume_profile" }
            };
        }

        // -------------------------------------------------------------------------
        // Test 1: Score below threshold → BelowScore
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_ScoreBelowThreshold_ReturnsBelowScore()
        {
            // Score 79.9 is just below the 80.0 TypeA threshold.
            var scored = MakeResult(score: 79.9, tier: SignalTier.TYPE_A, direction: 1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.BelowScore));
        }

        // -------------------------------------------------------------------------
        // Test 2: Tier below MinTierForEntry (TypeB result, min=TypeA) → BelowTier
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_TierBelowMinTier_ReturnsBelowTier()
        {
            // Score passes (85.0 >= 80.0) but TypeB (ordinal 2) < TypeA (ordinal 3).
            var scored = MakeResult(score: 85.0, tier: SignalTier.TYPE_B, direction: 1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.BelowTier));
        }

        // -------------------------------------------------------------------------
        // Test 3: Direction = 0 → NoDirection
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_DirectionZero_ReturnsNoDirection()
        {
            var scored = MakeResult(score: 90.0, tier: SignalTier.TYPE_A, direction: 0);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.NoDirection));
        }

        // -------------------------------------------------------------------------
        // Test 4: All-pass TypeA long → Passed
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_AllPassTypeALong_ReturnsPassed()
        {
            var scored = MakeResult(score: 87.5, tier: SignalTier.TYPE_A, direction: 1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed));
        }

        // -------------------------------------------------------------------------
        // Test 5: Scorer result null → NoScore (indicator not loaded or no bars yet)
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_NullResult_ReturnsNoScore_NoException()
        {
            ScorerResult scored = null;
            ScorerEntryGate.GateOutcome outcome = ScorerEntryGate.GateOutcome.Passed; // will be overwritten
            Assert.DoesNotThrow(() =>
            {
                outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            });
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.NoScore));
        }

        // -------------------------------------------------------------------------
        // Test 6: All-pass TypeA short (direction = -1) → Passed
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_AllPassTypeAShort_ReturnsPassed()
        {
            var scored = MakeResult(score: 82.0, tier: SignalTier.TYPE_A, direction: -1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 80.0, minTier: SignalTier.TYPE_A);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed));
            // Verify direction is preserved on the result for the caller to use.
            Assert.That(scored.Direction, Is.EqualTo(-1));
        }

        // -------------------------------------------------------------------------
        // Test 7: TypeB at MinTier=TypeB → Passed (TypeB is acceptable when gate is relaxed)
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_TypeB_AtMinTierTypeB_ReturnsPassed()
        {
            // Score 75.0 >= 72.0 (TypeB threshold); tier=TypeB; minTier=TypeB → should pass.
            var scored = MakeResult(score: 75.0, tier: SignalTier.TYPE_B, direction: 1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 72.0, minTier: SignalTier.TYPE_B);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed));
        }

        // -------------------------------------------------------------------------
        // Test 8: TypeC rejected by MinTierForEntry=TypeB gate → BelowTier
        // -------------------------------------------------------------------------
        [Test]
        public void Evaluate_TypeC_RejectedByTypeBMinTierGate_ReturnsBelowTier()
        {
            // Score 55.0 >= 50.0 TypeC threshold, but TypeC (ordinal 1) < TypeB (ordinal 2).
            var scored = MakeResult(score: 55.0, tier: SignalTier.TYPE_C, direction: 1);
            var outcome = ScorerEntryGate.Evaluate(scored, scoreThreshold: 50.0, minTier: SignalTier.TYPE_B);
            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.BelowTier));
        }

        // -------------------------------------------------------------------------
        // Test 9: Per-bar log format — [DEEP6 Scorer] bar / score / tier / narrative
        // -------------------------------------------------------------------------
        [Test]
        public void BuildLogLine_KnownInputs_MatchesExpectedFormat()
        {
            var scored = MakeResult(score: 87.34, tier: SignalTier.TYPE_A, direction: 1,
                narrative: "ABSORBED @VAH");
            string line = ScorerEntryGate.BuildLogLine(barIdx: 123, scored: scored);

            // The line must start with the sentinel prefix.
            Assert.That(line, Does.StartWith("[DEEP6 Scorer] bar=123"));

            // Score must appear with sign and 2 decimal places.
            Assert.That(line, Does.Contain("score=+87.34"));

            // Tier name must appear.
            Assert.That(line, Does.Contain("tier=TYPE_A"));

            // Narrative must appear.
            Assert.That(line, Does.Contain("narrative=ABSORBED @VAH"));
        }

        // -------------------------------------------------------------------------
        // Test 10: BuildLogLine returns empty string when scored is null
        // -------------------------------------------------------------------------
        [Test]
        public void BuildLogLine_NullResult_ReturnsEmptyString()
        {
            string line = ScorerEntryGate.BuildLogLine(barIdx: 5, scored: null);
            Assert.That(line, Is.EqualTo(string.Empty));
        }
    }
}
