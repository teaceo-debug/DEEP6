// NUnit fixtures for ProfileAnchorLevels.
//
// Test seam pattern: build FootprintBar instances by setting Levels[px] directly,
// call Finalize(0), then feed via OnBarClose with a deterministic DateTime.
// All price comparisons use Within(TickSize/2) to tolerate floating-point tick step.

using System;
using System.Collections.Generic;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;

namespace NinjaTrader.Tests.Levels
{
    [TestFixture]
    public class ProfileAnchorLevelsTests
    {
        private const double Tick = 0.25;

        // ─── Helpers ────────────────────────────────────────────────────────────

        private static FootprintBar MakeBar(double open, double high, double low, double close,
                                             Dictionary<double, long> askVols)
        {
            var bar = new FootprintBar { Open = open, High = high, Low = low, Close = close };
            foreach (var kv in askVols)
                bar.Levels[kv.Key] = new Cell { AskVol = kv.Value, BidVol = 0 };
            bar.Finalize(0);
            return bar;
        }

        /// <summary>Feed a single bar into the aggregator with the given session date.</summary>
        private static void FeedBar(ProfileAnchorLevels pal, FootprintBar bar, DateTime sessionDate)
        {
            // Use a time that is definitely within the same day as sessionDate
            pal.OnBarClose(bar, sessionDate.Date.AddHours(10));
        }

        // ─── Test 1: Single session — POC matches max-volume price ───────────────

        [Test]
        public void SingleSession_PocMatchesMaxVolumePrice()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var date = new DateTime(2026, 1, 2);

            // 17100 has vol=500 (highest), 17200 has vol=200, 17300 has vol=100
            FeedBar(pal, MakeBar(17100, 17300, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 500 },
                { 17200, 200 },
                { 17300, 100 },
            }), date);

            // Trigger boundary to finalize session
            pal.OnSessionBoundary(date.AddDays(1));

            var snap = pal.BuildSnapshot();
            var pdPoc = snap.Levels.Find(l => l.Kind == ProfileAnchorKind.PriorDayPoc);
            Assert.That(pdPoc, Is.Not.Null, "PriorDayPoc should be present");
            Assert.That(pdPoc.Price, Is.EqualTo(17100.0).Within(Tick / 2), "POC should be at max-volume price 17100");
        }

        // ─── Test 2: Single session — VAH/VAL respect 70% algorithm ─────────────

        [Test]
        public void SingleSession_VahValRespect70PctAlgorithm()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var date = new DateTime(2026, 1, 2);

            // Distribute volume across 4 prices: 100, 200, 300, 400
            // Sorted desc by vol: 17200(400) → 17300(300) → accumulated 700/1000=70%
            // So VA includes prices 17200 and 17300 → VAH=17300+tick, VAL=17200
            FeedBar(pal, MakeBar(17100, 17400, 17100, 17400, new Dictionary<double, long>
            {
                { 17100, 100 },
                { 17200, 400 },
                { 17300, 300 },
                { 17400, 200 },
            }), date);

            pal.OnSessionBoundary(date.AddDays(1));
            var snap = pal.BuildSnapshot();

            var pdVah = snap.Levels.Find(l => l.Kind == ProfileAnchorKind.PriorDayVah);
            var pdVal = snap.Levels.Find(l => l.Kind == ProfileAnchorKind.PriorDayVal);

            Assert.That(pdVah, Is.Not.Null, "PD VAH should be present");
            Assert.That(pdVal, Is.Not.Null, "PD VAL should be present");
            Assert.That(pdVah.Price, Is.GreaterThan(pdVal.Price), "VAH must be above VAL");

            // VA should contain >= 70% of total volume
            // Total = 1000, target = 700; 400+300=700 → prices 17200, 17300
            Assert.That(pdVah.Price, Is.EqualTo(17300.0 + Tick).Within(Tick / 2), "VAH = 17300 + tick");
            Assert.That(pdVal.Price, Is.EqualTo(17200.0).Within(Tick / 2), "VAL = 17200");
        }

        // ─── Test 3: Two sessions — prior-day uses completed session only ────────

        [Test]
        public void TwoSessions_PriorDayLevelsUseCompletedSessionOnly()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var day1 = new DateTime(2026, 1, 2);
            var day2 = new DateTime(2026, 1, 3);

            // Day 1: POC at 17100
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 800 }, { 17200, 200 },
            }), day1);

            // Day 2 bar (in-progress session): POC would be at 17500 if completed
            pal.OnSessionBoundary(day2);
            FeedBar(pal, MakeBar(17500, 17600, 17500, 17600, new Dictionary<double, long>
            {
                { 17500, 999 }, { 17600, 1 },
            }), day2);

            // Do NOT call OnSessionBoundary again — day 2 is still in progress
            var snap = pal.BuildSnapshot();

            var pdPoc = snap.Levels.Find(l => l.Kind == ProfileAnchorKind.PriorDayPoc);
            Assert.That(pdPoc, Is.Not.Null, "PriorDayPoc should exist from day 1");
            Assert.That(pdPoc.Price, Is.EqualTo(17100.0).Within(Tick / 2),
                "PD POC should be day-1 value, not in-progress day-2");
        }

        // ─── Test 4: Naked POC remains naked when not retraded ───────────────────

        [Test]
        public void NakedPoc_RemainsNakedWhenNotRetraded()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var day1 = new DateTime(2026, 1, 2);
            var day2 = new DateTime(2026, 1, 3);

            // Session A: POC @ 17100
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 900 }, { 17200, 100 },
            }), day1);
            pal.OnSessionBoundary(day2);

            // Session B bar: low=17101, high=17102 (does NOT cover 17100)
            FeedBar(pal, MakeBar(17101, 17102, 17101, 17102, new Dictionary<double, long>
            {
                { 17101, 500 }, { 17102, 500 },
            }), day2);

            var snap = pal.BuildSnapshot();
            var naked = snap.Levels.FindAll(l => l.Kind == ProfileAnchorKind.NakedPoc);
            Assert.That(naked.Count, Is.GreaterThan(0), "Naked POC should be present");
            Assert.That(naked.Exists(n => System.Math.Abs(n.Price - 17100.0) < Tick / 2),
                Is.True, "nPOC @ 17100 should still be naked");
        }

        // ─── Test 5: Naked POC marked retested when later bar covers it ──────────

        [Test]
        public void NakedPoc_MarkedRetestedWhenLaterBarCovers()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var day1 = new DateTime(2026, 1, 2);
            var day2 = new DateTime(2026, 1, 3);

            // Session A: POC @ 17100
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 900 }, { 17200, 100 },
            }), day1);
            pal.OnSessionBoundary(day2);

            // Session B bar: low=17099, high=17101 → covers 17100
            FeedBar(pal, MakeBar(17099, 17101, 17099, 17101, new Dictionary<double, long>
            {
                { 17099, 300 }, { 17100, 400 }, { 17101, 300 },
            }), day2);

            var snap = pal.BuildSnapshot();
            // Retested naked POCs should be absent from snapshot (Retested=true filtered out)
            var naked = snap.Levels.FindAll(l => l.Kind == ProfileAnchorKind.NakedPoc);
            Assert.That(naked.Exists(n => System.Math.Abs(n.Price - 17100.0) < Tick / 2),
                Is.False, "nPOC @ 17100 should be retested and excluded from snapshot");
        }

        // ─── Test 6: Naked POC expires after NakedPocMaxAgeSessions ─────────────

        [Test]
        public void NakedPoc_ExpiresAfter20Sessions()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick, NakedPocMaxAgeSessions = 20 };
            var start = new DateTime(2026, 1, 2);

            // Session 0: POC @ 17100 (to become naked)
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 900 }, { 17200, 100 },
            }), start);

            // Sessions 1–20: POC far away, range 18000–18100 (never covers 17100)
            for (int i = 1; i <= 20; i++)
            {
                var d = start.AddDays(i);
                pal.OnSessionBoundary(d);
                FeedBar(pal, MakeBar(18000, 18100, 18000, 18100, new Dictionary<double, long>
                {
                    { 18000, 500 }, { 18100, 500 },
                }), d);
            }

            // After 20 additional sessions, AgeSessions == 20 → still within limit
            pal.OnSessionBoundary(start.AddDays(21));
            var snap20 = pal.BuildSnapshot();
            bool presentAt20 = snap20.Levels.Exists(l => l.Kind == ProfileAnchorKind.NakedPoc &&
                                                          System.Math.Abs(l.Price - 17100.0) < Tick / 2);
            Assert.That(presentAt20, Is.True, "nPOC @ 17100 should still be present after exactly 20 sessions");

            // Session 21: age becomes 21 → exceeds limit → should be dropped
            FeedBar(pal, MakeBar(18000, 18100, 18000, 18100, new Dictionary<double, long>
            {
                { 18000, 500 }, { 18100, 500 },
            }), start.AddDays(21));
            pal.OnSessionBoundary(start.AddDays(22));

            var snap21 = pal.BuildSnapshot();
            bool presentAt21 = snap21.Levels.Exists(l => l.Kind == ProfileAnchorKind.NakedPoc &&
                                                           System.Math.Abs(l.Price - 17100.0) < Tick / 2);
            Assert.That(presentAt21, Is.False, "nPOC @ 17100 should expire after 21 sessions (> max 20)");
        }

        // ─── Test 7: Prior-week POC aggregates last 5 sessions ───────────────────

        [Test]
        public void PriorWeekPoc_AggregatesLast5Sessions()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var start = new DateTime(2026, 1, 2);

            // Sessions 1–5: each puts heavy volume at a different price.
            // Session 1: 17100 × 1000
            // Sessions 2–5: 17200 × 200 each
            // Aggregate: 17100=1000, 17200=800 → PW POC = 17100
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 1000 },
            }), start);
            pal.OnSessionBoundary(start.AddDays(1));

            for (int i = 1; i <= 4; i++)
            {
                var d = start.AddDays(i);
                FeedBar(pal, MakeBar(17200, 17300, 17200, 17300, new Dictionary<double, long>
                {
                    { 17200, 200 },
                }), d);
                pal.OnSessionBoundary(start.AddDays(i + 1));
            }

            var snap = pal.BuildSnapshot();
            var pwPoc = snap.Levels.Find(l => l.Kind == ProfileAnchorKind.PriorWeekPoc);
            Assert.That(pwPoc, Is.Not.Null, "PriorWeekPoc should be present");
            Assert.That(pwPoc.Price, Is.EqualTo(17100.0).Within(Tick / 2),
                "PW POC should be at 17100 (highest aggregate volume across 5 sessions)");
        }

        // ─── Test 8: Composite VA null before threshold, computed after ──────────

        [Test]
        public void CompositeVA_NullBeforeThresholdReachesThenComputed()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick, CompositeSessions = 5 };
            var start = new DateTime(2026, 1, 2);

            // After 2 sessions: CompositeVah/Val should be null
            for (int i = 0; i < 2; i++)
            {
                var d = start.AddDays(i);
                FeedBar(pal, MakeBar(17100, 17300, 17100, 17200, new Dictionary<double, long>
                {
                    { 17100, 300 }, { 17200, 400 }, { 17300, 300 },
                }), d);
                pal.OnSessionBoundary(start.AddDays(i + 1));
            }

            var snap2 = pal.BuildSnapshot();
            Assert.That(snap2.CompositeVah, Is.Null, "CompositeVah should be null before 5 sessions");
            Assert.That(snap2.CompositeVal, Is.Null, "CompositeVal should be null before 5 sessions");

            // Add 3 more sessions (total 5)
            for (int i = 2; i < 5; i++)
            {
                var d = start.AddDays(i);
                FeedBar(pal, MakeBar(17100, 17300, 17100, 17200, new Dictionary<double, long>
                {
                    { 17100, 300 }, { 17200, 400 }, { 17300, 300 },
                }), d);
                pal.OnSessionBoundary(start.AddDays(i + 1));
            }

            var snap5 = pal.BuildSnapshot();
            Assert.That(snap5.CompositeVah, Is.Not.Null, "CompositeVah should be non-null after 5 sessions");
            Assert.That(snap5.CompositeVal, Is.Not.Null, "CompositeVal should be non-null after 5 sessions");
            Assert.That(snap5.CompositeVah.Value, Is.GreaterThan(snap5.CompositeVal.Value),
                "CompositeVah must be above CompositeVal");
        }

        // ─── Test 9: Session boundary reset starts fresh aggregation ────────────

        [Test]
        public void SessionBoundaryReset_NewDateStartsFreshAggregation()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var day1 = new DateTime(2026, 1, 2);
            var day2 = new DateTime(2026, 1, 3);

            // Day 1: feed a bar
            FeedBar(pal, MakeBar(17100, 17200, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 500 },
            }), day1);

            // Boundary → finalizes day 1, starts day 2
            pal.OnSessionBoundary(day2);

            // CurrentSession should now have date = day2 and empty VolumeAtPrice
            Assert.That(pal.CurrentSession.SessionDate.Date, Is.EqualTo(day2.Date),
                "CurrentSession date should be day2 after boundary");
            Assert.That(pal.CurrentSession.VolumeAtPrice.Count, Is.EqualTo(0),
                "New session should start with empty VolumeAtPrice");
            Assert.That(pal.CompletedSessions.Count, Is.EqualTo(1),
                "Day 1 session should be finalized in CompletedSessions");

            // Feed a bar into day 2
            FeedBar(pal, MakeBar(17500, 17600, 17500, 17600, new Dictionary<double, long>
            {
                { 17500, 300 },
            }), day2);

            Assert.That(pal.CurrentSession.VolumeAtPrice.Count, Is.EqualTo(1),
                "Day 2 session should accumulate the new bar");
            Assert.That(pal.CurrentSession.VolumeAtPrice.ContainsKey(17500), Is.True,
                "Day 2 VolumeAtPrice should contain price from new bar");
        }

        // ─── Test 10: Labels match spec ─────────────────────────────────────────

        [Test]
        public void Snapshot_LabelsMatchSpec()
        {
            var pal = new ProfileAnchorLevels { TickSize = Tick };
            var day1 = new DateTime(2026, 1, 2);

            FeedBar(pal, MakeBar(17100, 17300, 17100, 17200, new Dictionary<double, long>
            {
                { 17100, 100 }, { 17200, 500 }, { 17300, 400 },
            }), day1);
            pal.OnSessionBoundary(day1.AddDays(1));

            var snap = pal.BuildSnapshot();
            var labels = new System.Collections.Generic.HashSet<string>();
            foreach (var l in snap.Levels) labels.Add(l.Label);

            Assert.That(labels.Contains("PD POC"), Is.True, "PD POC label");
            Assert.That(labels.Contains("PD VAH"), Is.True, "PD VAH label");
            Assert.That(labels.Contains("PD VAL"), Is.True, "PD VAL label");
            Assert.That(labels.Contains("PDH"),    Is.True, "PDH label");
            Assert.That(labels.Contains("PDL"),    Is.True, "PDL label");
            Assert.That(labels.Contains("PDM"),    Is.True, "PDM label");
            Assert.That(labels.Contains("nPOC"),   Is.True, "nPOC label for naked POC");
        }
    }
}
