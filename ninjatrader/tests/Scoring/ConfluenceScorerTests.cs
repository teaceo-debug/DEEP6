// ConfluenceScorerTests: NUnit fixture tests for Phase 18 two-layer confluence scorer.
//
// Covers SCOR-01..SCOR-06 requirements and all 15 behavior cases from 18-01-PLAN.md.
// Tests are deterministic — no random inputs, no time-dependent behavior.
//
// Python reference: deep6/scoring/scorer.py score_bar()
// Port verification: bit-for-bit score match (within 0.0001) on hand-crafted fixtures.

using System;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Scoring
{
    [TestFixture]
    [Category("Scoring")]
    public class ConfluenceScorerTests
    {
        private static string FixtureDir => System.IO.Path.Combine(
            TestContext.CurrentContext.TestDirectory, "fixtures", "scoring");

        // -----------------------------------------------------------------------
        // Helper: build a SignalResult quickly
        // -----------------------------------------------------------------------
        private static SignalResult SR(string id, int dir, double strength, double price = 0.0, string detail = "")
            => new SignalResult(id, dir, strength, 0UL, detail, price);

        // -----------------------------------------------------------------------
        // Test 1 (SCOR-01/02/03): All 8 categories fire bullish → score capped at 100, TYPE_A
        // R1 weights: abs(32)+exh(24)+trap(0)+delta(14)+imb(13)+vp(5)+auct(12)+poc(0)=100
        // zone near edge + high score → zoneBonus=4; catCount=8>=5 → mult=1.25
        // IB: bars=30; agreement=1.0; score=min((100*1.25+4)*1.0*1.15,100)=100
        // -----------------------------------------------------------------------
        [Test]
        public void Score_AllEightCategories_ReturnsTypeA()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8, 17500.25, "ABSORBED @VAL"),
                SR("EXH-05",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.7, 0.0, "STACKED_T3"),
                SR("AUCT-02", +1, 0.5),
                SR("POC-02",  +1, 0.4),
            };

            // zoneScore=60>=50, zoneDistTicks=0<=0.5 -> ZONE_NEAR_BONUS=4, adds volume_profile
            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 40, barClose: 17500.25,
                zoneScore: 60.0, zoneDistTicks: 0.0);

            Assert.That(result.Tier,          Is.EqualTo(SignalTier.TYPE_A), "Tier must be TYPE_A");
            Assert.That(result.Direction,     Is.EqualTo(+1),               "Direction must be bullish");
            Assert.That(result.CategoryCount, Is.EqualTo(8),                "All 8 categories must fire");
            Assert.That(result.TotalScore,    Is.InRange(80.0, 100.0),      "Score must be in TypeA band");
            Assert.That(result.ConfluenceMult, Is.EqualTo(1.25),            "Confluence mult must be 1.25 (cat>=5)");
            Assert.That(result.ZoneBonus,     Is.EqualTo(4.0),              "Zone near bonus must be 4");
            Assert.That(result.Narrative,     Does.Contain("TYPE A"),       "Narrative must say TYPE A");
        }

        // -----------------------------------------------------------------------
        // Test 2 (SCOR-01): Zero signals → QUIET, score=0, direction=0
        // -----------------------------------------------------------------------
        [Test]
        public void Score_ZeroSignals_ReturnsQuiet()
        {
            var result = ConfluenceScorer.Score(
                new SignalResult[0], barsSinceOpen: 50, barDelta: 0, barClose: 17500.0);

            Assert.That(result.Tier,          Is.EqualTo(SignalTier.QUIET), "No signals must produce QUIET");
            Assert.That(result.TotalScore,    Is.EqualTo(0.0),              "Score must be 0 with no signals");
            Assert.That(result.Direction,     Is.EqualTo(0),                "Direction must be neutral");
            Assert.That(result.CategoryCount, Is.EqualTo(0),                "Zero categories must fire");
            Assert.That(result.Narrative,     Is.EqualTo("QUIET"),          "Narrative must be QUIET");
        }

        // -----------------------------------------------------------------------
        // Test 3 (SCOR-04): TypeB path — score>=72, cat>=4, delta agrees, strength>=0.3
        // R1 weights: abs(32)+exh(24)+trap(0)+delta(14)=70; ibMult=1.15; score=80.5; no zone -> TypeA blocked
        // trap category still counted (catCount=4) but contributes 0 weight.
        // -----------------------------------------------------------------------
        [Test]
        public void Score_TypeBPath_FourCategoriesNoZone_ReturnsTypeB()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8, 17500.0, "ABSORBED @LOW"),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 20, barDelta: 10, barClose: 17500.0,
                zoneScore: 0.0, zoneDistTicks: 999.0);

            Assert.That(result.Tier,          Is.EqualTo(SignalTier.TYPE_B), "Must be TYPE_B");
            Assert.That(result.Direction,     Is.EqualTo(+1),               "Bullish");
            Assert.That(result.CategoryCount, Is.EqualTo(4),                "Exactly 4 categories");
            Assert.That(result.TotalScore,    Is.InRange(72.0, 100.0),      "Score in TypeB+ band");
            Assert.That(result.ZoneBonus,     Is.EqualTo(0.0),              "No zone bonus");
            Assert.That(result.Narrative,     Does.Contain("TYPE B"),       "Narrative says TYPE B");
        }

        // -----------------------------------------------------------------------
        // Test 4 (SCOR-04 Pitfall 1): TypeC requires cat_count >= 4, NOT 3.
        // 3 categories at score ~56 → QUIET (not TypeC).
        // Python scorer.py line 485: cat_count >= 4 — the docstring says 3, the code says 4.
        // -----------------------------------------------------------------------
        [Test]
        public void Score_TypeCWithThreeCats_DemotedToQuiet()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.5),
                SR("EXH-03",  +1, 0.4),
                SR("DELT-04", +1, 0.4),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 100, barDelta: 15, barClose: 17500.0,
                zoneScore: 0.0, zoneDistTicks: 999.0);

            Assert.That(result.Tier,          Is.EqualTo(SignalTier.QUIET), "3 cats must NOT reach TypeC");
            Assert.That(result.CategoryCount, Is.EqualTo(3),               "Exactly 3 categories");
            Assert.That(result.TotalScore,    Is.GreaterThanOrEqualTo(50.0), "Score >=50 but tier still QUIET");
        }

        // -----------------------------------------------------------------------
        // Test 5 (SCOR-05): Midday block barsSinceOpen=250 forces QUIET regardless of score
        // -----------------------------------------------------------------------
        [Test]
        public void Score_MiddayBlock_ForcesQuiet()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8, 17500.25, "ABSORBED @VAL"),
                SR("EXH-05",  +1, 0.6),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.7, 0.0, "STACKED_T3"),
                SR("AUCT-02", +1, 0.5),
                SR("POC-02",  +1, 0.4),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 250, barDelta: 40, barClose: 17500.25,
                zoneScore: 60.0, zoneDistTicks: 0.0);

            Assert.That(result.Tier,       Is.EqualTo(SignalTier.QUIET), "Midday block must force QUIET");
            Assert.That(result.TotalScore, Is.GreaterThanOrEqualTo(80.0), "Score still computed high");
            Assert.That(result.Direction,  Is.EqualTo(+1),               "Direction still resolved");
        }

        // -----------------------------------------------------------------------
        // Test 6 (SCOR-03): Zone bonus tiers — high/mid/near/none
        // -----------------------------------------------------------------------
        [Test]
        public void Score_ZoneBonusTiers_CorrectBonusPerScore()
        {
            var signals = new[]
            {
                SR("ABS-01", +1, 0.8),
                SR("EXH-03", +1, 0.6),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.5, 0.0, "STACKED_T3"),
            };

            // zoneScore>=50, zoneDistTicks far → ZONE_HIGH_BONUS=8
            var r8 = ConfluenceScorer.Score(signals, 50, 10, 17500.0, zoneScore: 60.0, zoneDistTicks: 5.0);
            Assert.That(r8.ZoneBonus, Is.EqualTo(8.0), "zone>=50 + far -> +8 bonus");

            // zoneScore>=30 but <50 → ZONE_MID_BONUS=6
            var r6 = ConfluenceScorer.Score(signals, 50, 10, 17500.0, zoneScore: 35.0, zoneDistTicks: 5.0);
            Assert.That(r6.ZoneBonus, Is.EqualTo(6.0), "zone>=30 -> +6 bonus");

            // zoneScore>=50 + within 0.5 ticks → ZONE_NEAR_BONUS=4
            var r4 = ConfluenceScorer.Score(signals, 50, 10, 17500.0, zoneScore: 55.0, zoneDistTicks: 0.3);
            Assert.That(r4.ZoneBonus, Is.EqualTo(4.0), "zone>=50 + near 0.3 ticks -> +4 bonus");

            // zoneScore<30 → no bonus
            var r0 = ConfluenceScorer.Score(signals, 50, 10, 17500.0, zoneScore: 20.0, zoneDistTicks: 0.0);
            Assert.That(r0.ZoneBonus, Is.EqualTo(0.0), "zone<30 -> no bonus");
        }

        // -----------------------------------------------------------------------
        // Test 7 (D-02): Stacked imbalance dedup — IMB-03-T1 and IMB-03-T3 both bullish
        // → "imbalance" counted ONCE (not twice)
        // -----------------------------------------------------------------------
        [Test]
        public void Score_StackedImbalanceT1AndT3_VotesOnce()
        {
            var signals = new[]
            {
                SR("ABS-01",     +1, 0.8),
                SR("IMB-03-T1",  +1, 0.5, 0.0, "STACKED_T1"),
                SR("IMB-03-T3",  +1, 0.7, 0.0, "STACKED_T3"),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 50, barDelta: 10, barClose: 17500.0);

            // Should have absorption + imbalance = 2 categories (NOT 3)
            Assert.That(result.CategoryCount,  Is.EqualTo(2),      "Stacked IMB dedup: only 2 categories");
            Assert.That(result.CategoriesFiring, Does.Contain("absorption"), "absorption category present");
            Assert.That(result.CategoriesFiring, Does.Contain("imbalance"),  "imbalance category present (once)");
        }

        // -----------------------------------------------------------------------
        // Test 8: Delta voting rule — DELT-01 (RISE) does NOT vote "delta".
        // Only DELT-04/05/06/08/10 add the delta category.
        // -----------------------------------------------------------------------
        [Test]
        public void Score_DeltaRise_DoesNotVoteDelta()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("DELT-01", +1, 0.6),  // RISE — should NOT vote
                SR("DELT-02", +1, 0.5),  // DROP (same reason) — should NOT vote
                SR("DELT-03", +1, 0.4),  // TAIL — should NOT vote
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 50, barDelta: 20, barClose: 17500.0);

            Assert.That(result.CategoryCount, Is.EqualTo(1),  "Only absorption category; DELT-01/02/03 excluded");
            Assert.That(result.CategoriesFiring, Does.Contain("absorption"), "absorption present");
            Assert.That(result.CategoriesFiring, Does.Not.Contain("delta"),  "delta must NOT be added by RISE/DROP/TAIL");
        }

        // -----------------------------------------------------------------------
        // Test 9 (SCOR-06): Narrative label format for TypeA/B/C/QUIET
        // -----------------------------------------------------------------------
        [Test]
        public void Score_NarrativeLabelFormat_MatchesPythonFormat()
        {
            // TypeA
            var sigsA = new[]
            {
                SR("ABS-01",  +1, 0.8, 0.0, "ABSORBED @VAL"),
                SR("EXH-05",  +1, 0.6),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.7, 0.0, "STACKED_T3"),
                SR("AUCT-02", +1, 0.5),
                SR("POC-02",  +1, 0.4),
            };
            var rA = ConfluenceScorer.Score(sigsA, 30, 40, 17500.0, zoneScore: 60.0, zoneDistTicks: 0.0);
            Assert.That(rA.Tier, Is.EqualTo(SignalTier.TYPE_A));
            Assert.That(rA.Narrative, Does.StartWith("TYPE A \u2014 TRIPLE CONFLUENCE LONG"), "TypeA label format");

            // TypeB (use same IB trick as test 3)
            var sigsB = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
            };
            var rB = ConfluenceScorer.Score(sigsB, 20, 10, 17500.0, zoneScore: 0.0);
            Assert.That(rB.Tier, Is.EqualTo(SignalTier.TYPE_B));
            Assert.That(rB.Narrative, Does.StartWith("TYPE B \u2014 DOUBLE CONFLUENCE LONG"), "TypeB label format");

            // QUIET: no signals
            var rQ = ConfluenceScorer.Score(new SignalResult[0], 50, 0, 17500.0);
            Assert.That(rQ.Tier,      Is.EqualTo(SignalTier.QUIET));
            Assert.That(rQ.Narrative, Is.EqualTo("QUIET"), "QUIET label when no signals");
        }

        // -----------------------------------------------------------------------
        // Test 10: Conflicting direction — dominant side wins, losing side excluded
        // -----------------------------------------------------------------------
        [Test]
        public void Score_ConflictingDirection_DominantWins()
        {
            var signals = new[]
            {
                SR("ABS-01", +1, 0.8),   // bull absorption
                SR("ABS-02", +1, 0.7),   // bull absorption
                SR("EXH-03", -1, 0.5),   // bear exhaustion (losing side)
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 50, barDelta: 20, barClose: 17500.0);

            Assert.That(result.Direction, Is.EqualTo(+1),   "Bull must dominate");
            Assert.That(result.CategoriesFiring, Does.Contain("absorption"), "absorption (dominant) present");
            Assert.That(result.CategoriesFiring, Does.Not.Contain("exhaustion"), "exhaustion (losing side) excluded");
        }

        // -----------------------------------------------------------------------
        // Test 11 (SCOR-02): IB multiplier — barsSinceOpen=30 applies 1.15x; =120 applies 1.0
        // -----------------------------------------------------------------------
        [Test]
        public void Score_IbMultiplier_AppliedOnlyInFirstSixtyBars()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("DELT-04", +1, 0.5),
            };

            var rIb     = ConfluenceScorer.Score(signals, barsSinceOpen: 30,  barDelta: 10, barClose: 17500.0);
            var rNoIb   = ConfluenceScorer.Score(signals, barsSinceOpen: 120, barDelta: 10, barClose: 17500.0);

            // IB score should be 1.15x the non-IB score (same signals, same agreement)
            Assert.That(rIb.TotalScore, Is.GreaterThan(rNoIb.TotalScore),
                "IB score must be higher than non-IB score");
            Assert.That(rIb.TotalScore / rNoIb.TotalScore,
                Is.InRange(1.149, 1.151),
                "IB mult must be 1.15x");
        }

        // -----------------------------------------------------------------------
        // Test 12 (SCOR-02): Confluence multiplier — cat_count=4 → 1.0; cat_count=5 → 1.25
        // -----------------------------------------------------------------------
        [Test]
        public void Score_ConfluenceMult_OnlyAboveFiveCategories()
        {
            // 4 categories — no confluence mult
            var sigs4 = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
            };
            var r4 = ConfluenceScorer.Score(sigs4, 100, 10, 17500.0);
            Assert.That(r4.ConfluenceMult, Is.EqualTo(1.0), "4 cats → confluence mult must be 1.0");

            // 5 categories (add auction) — triggers 1.25x
            var sigs5 = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
                SR("AUCT-02", +1, 0.5),
            };
            var r5 = ConfluenceScorer.Score(sigs5, 100, 10, 17500.0);
            Assert.That(r5.ConfluenceMult, Is.EqualTo(1.25), "5 cats → confluence mult must be 1.25");
        }

        // -----------------------------------------------------------------------
        // Test 13 (SCOR-04): TypeA requires ALL 7 gates — missing any demotes
        // Specifically: TypeA fails without zone (has_zone=false → demotes to TypeB)
        // -----------------------------------------------------------------------
        [Test]
        public void Score_TypeAMissingZone_DemotedToTypeB()
        {
            // Would be TypeA except no zone bonus → has_zone=false
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-05",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.7, 0.0, "STACKED_T3"),
            };

            // R1 weights + IB + 5 categories: base=abs(32)+exh(24)+trap(0)+delta(14)+imb(13)=83
            // mult=1.25; score=min(83*1.25*1.0*1.15,100)=min(119.3125,100)=100
            // But no zone → has_zone=false → TypeA blocked
            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 0.0, zoneDistTicks: 999.0);

            Assert.That(result.Tier, Is.Not.EqualTo(SignalTier.TYPE_A), "TypeA must fail without zone");
            Assert.That(result.Tier, Is.EqualTo(SignalTier.TYPE_B),     "Demoted to TypeB");
        }

        // -----------------------------------------------------------------------
        // Test 14: EntryPrice from dominant ABS/EXH signal's Price; fallback to barClose
        // -----------------------------------------------------------------------
        [Test]
        public void Score_EntryPrice_DerivedFromDominantAbsExhSignal()
        {
            double absPrice = 17500.25;

            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8, absPrice, "ABSORBED @VAL"),
                SR("EXH-05",  +1, 0.6),
                SR("DELT-04", +1, 0.5),
                SR("IMB-03-T3", +1, 0.7, 0.0, "STACKED_T3"),
                SR("AUCT-02", +1, 0.5),
            };

            var rWithPrice = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 99999.0,
                zoneScore: 60.0, zoneDistTicks: 0.0);

            Assert.That(rWithPrice.EntryPrice, Is.EqualTo(absPrice),
                "EntryPrice must come from ABS-01.Price, not barClose");

            // Fallback: ABS signal has no price set
            var sigsNoPrice = new[]
            {
                SR("DELT-04", +1, 0.5),
                SR("AUCT-02", +1, 0.5),
            };
            double fallback = 17600.0;
            var rFallback = ConfluenceScorer.Score(
                sigsNoPrice, barsSinceOpen: 100, barDelta: 10, barClose: fallback);

            Assert.That(rFallback.EntryPrice, Is.EqualTo(fallback),
                "EntryPrice must fall back to barClose when no ABS/EXH price set");
        }

        // -----------------------------------------------------------------------
        // Test 15: Score clamped [0.0, 100.0] after all multipliers
        // -----------------------------------------------------------------------
        [Test]
        public void Score_ScoreClampedToRange()
        {
            // Max possible: all 8 categories + max zone bonus + max IB mult
            var signals = new[]
            {
                SR("ABS-01",   +1, 1.0),
                SR("EXH-05",   +1, 1.0),
                SR("TRAP-01",  +1, 1.0),
                SR("DELT-04",  +1, 1.0),
                SR("IMB-03-T3", +1, 1.0, 0.0, "STACKED_T3"),
                SR("AUCT-02",  +1, 1.0),
                SR("POC-02",   +1, 1.0),
            };

            // Extremely high GEX mults to push score above 100
            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 10, barDelta: 10, barClose: 17500.0,
                zoneScore: 80.0, zoneDistTicks: 5.0,
                gexAbsMult: 3.0, gexMomentumMult: 3.0, gexNearWallBonus: 50.0,
                vpinModifier: 2.0);

            Assert.That(result.TotalScore, Is.LessThanOrEqualTo(100.0), "Score must be clamped to 100");
            Assert.That(result.TotalScore, Is.GreaterThanOrEqualTo(0.0), "Score must be >= 0");

            // Minimum: vpinModifier=0 should produce score=0
            var rZero = ConfluenceScorer.Score(
                signals, barsSinceOpen: 50, barDelta: 10, barClose: 17500.0,
                vpinModifier: 0.0);
            Assert.That(rZero.TotalScore, Is.EqualTo(0.0), "vpinModifier=0 must produce score=0");
        }

        // -----------------------------------------------------------------------
        // Test 16: Delta-only-5 vote rule — DELT-04/08/10 DO vote; DELT-01/02/03 do NOT
        // -----------------------------------------------------------------------
        [Test]
        public void Score_DeltaVotingSignals_OnlyApprovedIDsVote()
        {
            // Non-voting DELT signals only
            var nonVoters = new[]
            {
                SR("DELT-01", +1, 0.8),  // RISE
                SR("DELT-02", +1, 0.7),  // DROP
                SR("DELT-03", +1, 0.6),  // TAIL
                SR("DELT-07", +1, 0.5),  // REVERSAL
                SR("DELT-09", +1, 0.5),  // SWEEP
            };
            var rNoVote = ConfluenceScorer.Score(nonVoters, 50, 10, 17500.0);
            Assert.That(rNoVote.CategoryCount, Is.EqualTo(0), "Non-approved DELT IDs must not vote");

            // Voting DELT signals
            var voters = new[]
            {
                SR("DELT-04", +1, 0.5),  // DIVERGENCE
                SR("DELT-05", +1, 0.5),  // FLIP
                SR("DELT-06", +1, 0.5),  // TRAP
                SR("DELT-08", +1, 0.5),  // SLINGSHOT
                SR("DELT-10", +1, 0.5),  // CVD_DIVERGENCE
            };
            var rVote = ConfluenceScorer.Score(voters, 50, 10, 17500.0);
            Assert.That(rVote.CategoryCount, Is.EqualTo(1),   "Approved DELT IDs add exactly 1 delta category");
            Assert.That(rVote.CategoriesFiring, Does.Contain("delta"), "delta category must be present");
        }

        // -----------------------------------------------------------------------
        // Test 17: TypeC path — 4 categories at score>=50 but <72, no delta disagree → TYPE_C
        // R1 weights: abs(32)+delta(14)+imbalance(13)+auction(12)=71; catCount=4; confluenceMult=1.0
        // ibMult=1.0 (bars=100); agreement=1.0; score=71
        // TypeA fails (no zone); TypeB fails (71<72); TypeC: 71>=50 + catCount=4>=4 + minStrength → TYPE_C
        // -----------------------------------------------------------------------
        [Test]
        public void Score_FourCategoriesScoreAbove50_ReturnsTypeC()
        {
            // Use abs+delta+imbalance+auction to get base=71 (just below TypeB threshold of 72).
            // Exhaustion excluded so abs(32)+delta(14)+imbalance(13)+auction(12)=71.
            var signals = new[]
            {
                SR("ABS-01",      +1, 0.5),
                SR("DELT-04",     +1, 0.4),
                SR("IMB-03-T2",   +1, 0.4, 0.0, "STACKED_T2"),
                SR("AUCT-02",     +1, 0.3),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 100, barDelta: 10, barClose: 17500.0,
                zoneScore: 0.0, zoneDistTicks: 999.0);

            Assert.That(result.Tier, Is.EqualTo(SignalTier.TYPE_C), "4 cats + score>=50 but <72 must be TYPE_C");
            Assert.That(result.TotalScore, Is.InRange(50.0, 71.9999), "Score in TypeC band");
        }

        // -----------------------------------------------------------------------
        // Test 18: Null signals array handled gracefully (no crash)
        // -----------------------------------------------------------------------
        [Test]
        public void Score_NullSignalsArray_ReturnsQuiet()
        {
            var result = ConfluenceScorer.Score(
                null, barsSinceOpen: 50, barDelta: 0, barClose: 17500.0);

            Assert.That(result.Tier,      Is.EqualTo(SignalTier.QUIET), "Null signals must produce QUIET");
            Assert.That(result.TotalScore, Is.EqualTo(0.0),             "Score must be 0 with null signals");
        }

        // -----------------------------------------------------------------------
        // Test 19: Midday block edges — bar 239 not blocked, bar 240 is, bar 330 is, bar 331 not
        // -----------------------------------------------------------------------
        [Test]
        public void Score_MiddayBlockEdges_CorrectBoundaries()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
                SR("AUCT-02", +1, 0.5),
            };

            var r239 = ConfluenceScorer.Score(signals, barsSinceOpen: 239, barDelta: 10, barClose: 17500.0);
            var r240 = ConfluenceScorer.Score(signals, barsSinceOpen: 240, barDelta: 10, barClose: 17500.0);
            var r330 = ConfluenceScorer.Score(signals, barsSinceOpen: 330, barDelta: 10, barClose: 17500.0);
            var r331 = ConfluenceScorer.Score(signals, barsSinceOpen: 331, barDelta: 10, barClose: 17500.0);

            Assert.That(r239.Tier, Is.Not.EqualTo(SignalTier.QUIET), "Bar 239 must NOT be blocked");
            Assert.That(r240.Tier, Is.EqualTo(SignalTier.QUIET),     "Bar 240 must be blocked (midday start)");
            Assert.That(r330.Tier, Is.EqualTo(SignalTier.QUIET),     "Bar 330 must be blocked (midday end)");
            Assert.That(r331.Tier, Is.Not.EqualTo(SignalTier.QUIET), "Bar 331 must NOT be blocked");
        }

        // -----------------------------------------------------------------------
        // Test 20: JSON fixture files exist and are valid JSON
        // -----------------------------------------------------------------------
        [Test]
        public void Fixture_TypeAAllCategories_ExistsAndIsValidJson()
        {
            string path = Path.Combine(FixtureDir, "type-a-all-categories.json");
            Assert.That(File.Exists(path), Is.True, "type-a-all-categories.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Fixture_TypeBNoZone_ExistsAndIsValidJson()
        {
            string path = Path.Combine(FixtureDir, "type-b-no-zone.json");
            Assert.That(File.Exists(path), Is.True, "type-b-no-zone.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Fixture_TypeCSuppressed_ExistsAndIsValidJson()
        {
            string path = Path.Combine(FixtureDir, "type-c-suppressed.json");
            Assert.That(File.Exists(path), Is.True, "type-c-suppressed.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Fixture_QuietZeroSignals_ExistsAndIsValidJson()
        {
            string path = Path.Combine(FixtureDir, "quiet-zero-signals.json");
            Assert.That(File.Exists(path), Is.True, "quiet-zero-signals.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        [Test]
        public void Fixture_MiddayBlock_ExistsAndIsValidJson()
        {
            string path = Path.Combine(FixtureDir, "midday-block.json");
            Assert.That(File.Exists(path), Is.True, "midday-block.json must exist");
            Assert.DoesNotThrow(() => JsonDocument.Parse(File.ReadAllText(path)));
        }

        // -----------------------------------------------------------------------
        // Test 25: Score formula precision — hand-computed fixture matches to 0.0001
        // R1 weights: abs(32)+exh(24)+trap(0)+delta(14)=70; ibMult=1.15; confluenceMult=1.0; agreement=1.0
        // trap category still counted (catCount=4) but W_TRAPPED=0 contributes nothing to base.
        // Expected: 70 * 1.0 * 1.0 * 1.15 = 80.5
        // -----------------------------------------------------------------------
        [Test]
        public void Score_TypeBFormulaPrecision_MatchesHandComputed()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
            };

            var result = ConfluenceScorer.Score(
                signals, barsSinceOpen: 20, barDelta: 10, barClose: 17500.0,
                zoneScore: 0.0, zoneDistTicks: 999.0);

            // R1: abs(32)+exh(24)+trap(0)+delta(14)=70; mult=1.0; zone=0; agreement=1.0; ibMult=1.15
            // total = min(70 * 1.0 * 1.0 * 1.15, 100) = 80.5
            const double expected = 80.5;
            Assert.That(result.TotalScore, Is.InRange(expected - 0.0001, expected + 0.0001),
                $"Hand-computed score must match {expected} within 0.0001");
        }
    }
}
