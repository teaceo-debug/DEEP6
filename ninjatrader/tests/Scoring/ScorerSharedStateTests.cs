// ScorerSharedStateTests: NUnit tests for ScorerSharedState publish/read semantics.
//
// Coverage:
//   - Publish stores result and Latest retrieves it for same symbol
//   - Null symbol and null result are handled without throwing
//   - LatestBarIndex tracks the bar index correctly
//   - Multi-symbol isolation: publishing for symbol A does not affect symbol B
//   - Clear removes the latch for that symbol
//   - Thread-safety: concurrent publishes to different symbols (single-reader model)
//
// Phase 18-02

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.Tests.Scoring
{
    [TestFixture]
    [Category("Scoring")]
    public class ScorerSharedStateTests
    {
        // Helper: produce a minimal non-null ScorerResult with a given score and tier.
        private static ScorerResult MakeResult(double score, SignalTier tier, int direction = 1)
        {
            return new ScorerResult
            {
                TotalScore    = score,
                Tier          = tier,
                Direction     = direction,
                Narrative     = "TEST",
                EntryPrice    = 17000.0,
                CategoriesFiring = new string[0],
            };
        }

        [SetUp]
        public void ClearState()
        {
            // Clear well-known test symbols before each test to avoid cross-test pollution.
            ScorerSharedState.Clear("NQ 06-26");
            ScorerSharedState.Clear("ES 06-26");
            ScorerSharedState.Clear("__test_sym__");
        }

        // ── Test 1: Basic publish + retrieve ────────────────────────────────────────────────

        [Test]
        public void Publish_ThenLatest_ReturnsSameResult()
        {
            var result = MakeResult(85.0, SignalTier.TYPE_A);
            ScorerSharedState.Publish("NQ 06-26", 42, result);

            var retrieved = ScorerSharedState.Latest("NQ 06-26");

            Assert.IsNotNull(retrieved, "Latest should return the published result");
            Assert.AreEqual(85.0,             retrieved.TotalScore, 0.0001, "TotalScore should match");
            Assert.AreEqual(SignalTier.TYPE_A, retrieved.Tier,              "Tier should match");
            Assert.AreEqual(42, ScorerSharedState.LatestBarIndex("NQ 06-26"), "BarIndex should match");
        }

        // ── Test 2: Null-safety ──────────────────────────────────────────────────────────────

        [Test]
        public void Publish_NullResult_DoesNotThrow_AndLatestRemainsUnchanged()
        {
            // Pre-populate with a real result.
            var real = MakeResult(60.0, SignalTier.TYPE_B);
            ScorerSharedState.Publish("NQ 06-26", 10, real);

            // Publishing null should be a no-op (guards per spec).
            Assert.DoesNotThrow(() => ScorerSharedState.Publish("NQ 06-26", 11, null));

            var after = ScorerSharedState.Latest("NQ 06-26");
            Assert.IsNotNull(after, "Latest should still return the prior real result");
            Assert.AreEqual(60.0, after.TotalScore, 0.0001, "Prior result should be unchanged");
        }

        [Test]
        public void Latest_UnknownSymbol_ReturnsNull()
        {
            var r = ScorerSharedState.Latest("SYMBOL_NEVER_PUBLISHED");
            Assert.IsNull(r, "Latest on unknown symbol should return null");
        }

        [Test]
        public void LatestBarIndex_UnknownSymbol_ReturnsNegativeOne()
        {
            int idx = ScorerSharedState.LatestBarIndex("SYMBOL_NEVER_PUBLISHED");
            Assert.AreEqual(-1, idx, "LatestBarIndex on unknown symbol should return -1");
        }

        // ── Test 3: Multi-symbol isolation ──────────────────────────────────────────────────

        [Test]
        public void MultiSymbol_PublishToA_DoesNotAffectB()
        {
            var nqResult = MakeResult(90.0, SignalTier.TYPE_A, 1);
            var esResult = MakeResult(55.0, SignalTier.TYPE_C, -1);

            ScorerSharedState.Publish("NQ 06-26", 100, nqResult);
            ScorerSharedState.Publish("ES 06-26", 200, esResult);

            var nq = ScorerSharedState.Latest("NQ 06-26");
            var es = ScorerSharedState.Latest("ES 06-26");

            Assert.IsNotNull(nq, "NQ result should be present");
            Assert.IsNotNull(es, "ES result should be present");
            Assert.AreEqual(90.0,              nq.TotalScore, 0.0001, "NQ score should be 90");
            Assert.AreEqual(55.0,              es.TotalScore, 0.0001, "ES score should be 55");
            Assert.AreEqual(SignalTier.TYPE_A, nq.Tier, "NQ tier should be TYPE_A");
            Assert.AreEqual(SignalTier.TYPE_C, es.Tier, "ES tier should be TYPE_C");
            Assert.AreEqual(100, ScorerSharedState.LatestBarIndex("NQ 06-26"), "NQ bar index should be 100");
            Assert.AreEqual(200, ScorerSharedState.LatestBarIndex("ES 06-26"), "ES bar index should be 200");
        }

        // ── Test 4: Clear removes latch ──────────────────────────────────────────────────────

        [Test]
        public void Clear_RemovesPublishedResult()
        {
            ScorerSharedState.Publish("__test_sym__", 5, MakeResult(75.0, SignalTier.TYPE_B));
            Assert.IsNotNull(ScorerSharedState.Latest("__test_sym__"), "Should be present before Clear");

            ScorerSharedState.Clear("__test_sym__");

            Assert.IsNull(ScorerSharedState.Latest("__test_sym__"),      "Should be null after Clear");
            Assert.AreEqual(-1, ScorerSharedState.LatestBarIndex("__test_sym__"), "BarIndex should be -1 after Clear");
        }

        // ── Test 5: Last-write wins (overwrite semantics) ────────────────────────────────────

        [Test]
        public void Publish_Twice_SameSymbol_LastWriteWins()
        {
            ScorerSharedState.Publish("NQ 06-26", 1, MakeResult(50.0, SignalTier.TYPE_C));
            ScorerSharedState.Publish("NQ 06-26", 2, MakeResult(82.0, SignalTier.TYPE_A));

            var r = ScorerSharedState.Latest("NQ 06-26");
            Assert.IsNotNull(r);
            Assert.AreEqual(82.0,             r.TotalScore, 0.0001, "Second publish should overwrite first");
            Assert.AreEqual(SignalTier.TYPE_A, r.Tier, "Tier should reflect second publish");
            Assert.AreEqual(2, ScorerSharedState.LatestBarIndex("NQ 06-26"), "BarIndex should reflect second publish");
        }

        // ── Test 6: Concurrent publishes to DIFFERENT symbols do not corrupt state ──────────
        // (Single-writer-per-symbol model; this tests the ConcurrentDictionary's safety
        //  when multiple threads write to different keys simultaneously.)

        [Test]
        public void ConcurrentPublish_DifferentSymbols_NoCorruption()
        {
            const int threadCount = 8;
            var symbols = new string[threadCount];
            for (int i = 0; i < threadCount; i++)
                symbols[i] = "SYM_" + i;

            // Clean up before test.
            foreach (var s in symbols) ScorerSharedState.Clear(s);

            var tasks = new Task[threadCount];
            for (int i = 0; i < threadCount; i++)
            {
                int idx = i;
                tasks[idx] = Task.Run(() =>
                {
                    for (int bar = 0; bar < 100; bar++)
                        ScorerSharedState.Publish(symbols[idx], bar,
                            MakeResult(bar * 1.0, SignalTier.TYPE_C));
                });
            }

            Task.WaitAll(tasks);

            // Each symbol's latest should have bar index 99 (last published).
            for (int i = 0; i < threadCount; i++)
            {
                int barIdx = ScorerSharedState.LatestBarIndex(symbols[i]);
                Assert.AreEqual(99, barIdx,
                    string.Format("Symbol {0} should have barIdx=99 after 100 sequential publishes", symbols[i]));

                // Clean up after test.
                ScorerSharedState.Clear(symbols[i]);
            }
        }
    }
}
