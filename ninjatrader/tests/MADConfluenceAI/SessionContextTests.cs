// SessionContextTests: NUnit tests for MADMarketState session tracking.
//
// Covers ATR20 computation, session rollover, opening range, RTH detection,
// session highs, and volume EMA. All standalone — no NT8 dependency.

using System;
using NUnit.Framework;
using NinjaTrader.NinjaScript.Indicators.DEEP6;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    [TestFixture]
    [Category("MADConfluenceAI")]
    public class SessionContextTests
    {
        private MADMarketState _state;

        [SetUp]
        public void SetUp()
        {
            _state = new MADMarketState();
        }

        // -----------------------------------------------------------------
        // Test 1: ATR20 is non-zero after 20 bars with known high/low
        // -----------------------------------------------------------------
        [Test]
        public void Atr20_After20Bars_IsNonZero()
        {
            var baseTime = new DateTime(2026, 1, 5, 10, 0, 0); // 10:00 ET, RTH
            for (int i = 0; i < 25; i++)
            {
                double high = 18000 + i * 2;
                double low = 17995 + i * 2;
                double close = 17998 + i * 2;
                _state.Update(high, low, close, 500, baseTime.AddMinutes(i));
            }

            Assert.That(_state.Atr20, Is.GreaterThan(0), "ATR20 should be positive after 20+ bars");
            // Each bar has range of 5 pts; true range with prior close should be ~5 (small gaps)
            Assert.That(_state.Atr20, Is.InRange(4.0, 7.0), "ATR20 should reflect ~5pt bar ranges");
        }

        // -----------------------------------------------------------------
        // Test 2: Session rollover stores PrevDay levels from Day1
        // -----------------------------------------------------------------
        [Test]
        public void SessionRollover_SetsPriorDayLevels()
        {
            // Day 1 — feed 5 bars
            var day1 = new DateTime(2026, 1, 5, 10, 0, 0);
            _state.Update(18010, 17990, 18005, 1000, day1);
            _state.Update(18020, 17985, 18015, 1200, day1.AddMinutes(1));
            _state.Update(18025, 17980, 18000, 800, day1.AddMinutes(2));
            _state.Update(18015, 17995, 18010, 900, day1.AddMinutes(3));
            _state.Update(18018, 17992, 18008, 1100, day1.AddMinutes(4)); // last bar close = 18008

            // Verify Day 1 session extremes
            Assert.That(_state.SessionHigh, Is.EqualTo(18025), "Day1 session high");
            Assert.That(_state.SessionLow, Is.EqualTo(17980), "Day1 session low");

            // Day 2 — first bar triggers rollover
            var day2 = new DateTime(2026, 1, 6, 10, 0, 0);
            _state.Update(18050, 18040, 18045, 1500, day2);

            Assert.That(_state.PrevDayHigh, Is.EqualTo(18025), "PrevDayHigh should be Day1 session high");
            Assert.That(_state.PrevDayLow, Is.EqualTo(17980), "PrevDayLow should be Day1 session low");
            Assert.That(_state.PrevDayClose, Is.EqualTo(18008), "PrevDayClose should be Day1 last close");
        }

        // -----------------------------------------------------------------
        // Test 3: Opening range captured from first 30 minutes of RTH
        // -----------------------------------------------------------------
        [Test]
        public void OpeningRange_CapturedFromFirst30MinBars()
        {
            // Bars within RTH opening range (9:30 - 10:00 ET)
            var rthOpen = new DateTime(2026, 1, 5, 9, 30, 0);
            _state.Update(18005, 17995, 18000, 500, rthOpen);                  // min 0
            _state.Update(18015, 17990, 18010, 600, rthOpen.AddMinutes(10));   // min 10
            _state.Update(18020, 17988, 18012, 700, rthOpen.AddMinutes(20));   // min 20

            Assert.That(_state.OpeningRangeHigh, Is.EqualTo(18020), "OR high should be max of first 30min bars");
            Assert.That(_state.OpeningRangeLow, Is.EqualTo(17988), "OR low should be min of first 30min bars");

            // Bar at minute 31 — should finalize OR, not extend it
            _state.Update(18030, 17970, 18025, 800, rthOpen.AddMinutes(31));

            // OR should be locked at the values set before minute 31
            Assert.That(_state.OpeningRangeHigh, Is.EqualTo(18020), "OR high should not change after OR period");
            Assert.That(_state.OpeningRangeLow, Is.EqualTo(17988), "OR low should not change after OR period");
        }

        // -----------------------------------------------------------------
        // Test 4: IsRth true at 10:00 ET, false at 17:00 ET
        // -----------------------------------------------------------------
        [Test]
        public void IsRth_TrueWithinRthHours_FalseOutside()
        {
            var day = new DateTime(2026, 1, 5);

            // 10:00 ET — within RTH (9:30-16:00)
            _state.Update(18000, 17995, 17998, 500, day.Add(new TimeSpan(10, 0, 0)));
            Assert.That(_state.IsRth, Is.True, "10:00 ET should be RTH");

            // 9:30 ET — exact start of RTH
            _state.Update(18001, 17996, 17999, 500, day.Add(new TimeSpan(9, 30, 0)));
            Assert.That(_state.IsRth, Is.True, "9:30 ET should be RTH (inclusive)");

            // 17:00 ET — after RTH close (16:00)
            _state.Update(18002, 17997, 18000, 500, day.Add(new TimeSpan(17, 0, 0)));
            Assert.That(_state.IsRth, Is.False, "17:00 ET should NOT be RTH");

            // 8:00 ET — pre-market
            _state.Update(18003, 17998, 18001, 500, day.Add(new TimeSpan(8, 0, 0)));
            Assert.That(_state.IsRth, Is.False, "8:00 ET should NOT be RTH");

            // 16:00 ET — exact end (exclusive)
            _state.Update(18004, 17999, 18002, 500, day.Add(new TimeSpan(16, 0, 0)));
            Assert.That(_state.IsRth, Is.False, "16:00 ET should NOT be RTH (exclusive end)");
        }

        // -----------------------------------------------------------------
        // Test 5: SessionHigh updates as bars reach new highs
        // -----------------------------------------------------------------
        [Test]
        public void SessionHigh_UpdatesWithNewHighs()
        {
            var t = new DateTime(2026, 1, 5, 10, 0, 0);

            _state.Update(18000, 17990, 17995, 500, t);
            Assert.That(_state.SessionHigh, Is.EqualTo(18000));

            _state.Update(18005, 17992, 18000, 600, t.AddMinutes(1));
            Assert.That(_state.SessionHigh, Is.EqualTo(18005), "SessionHigh should update to 18005");

            // Bar with lower high — should NOT decrease SessionHigh
            _state.Update(18002, 17998, 18001, 700, t.AddMinutes(2));
            Assert.That(_state.SessionHigh, Is.EqualTo(18005), "SessionHigh should not decrease");

            // New session high
            _state.Update(18010, 18000, 18008, 800, t.AddMinutes(3));
            Assert.That(_state.SessionHigh, Is.EqualTo(18010), "SessionHigh should update to 18010");
        }

        // -----------------------------------------------------------------
        // Test 6: VolEma updates after each bar (non-zero after 5 bars)
        // -----------------------------------------------------------------
        [Test]
        public void VolEma_UpdatesAfterEachBar_NonZeroAfter5Bars()
        {
            var t = new DateTime(2026, 1, 5, 10, 0, 0);

            // First bar initializes VolEma to the volume value
            _state.Update(18000, 17990, 17995, 1000, t);
            Assert.That(_state.VolEma, Is.EqualTo(1000), "VolEma should equal first bar's volume");

            // Feed 4 more bars with varying volume
            long[] volumes = { 1200, 800, 1500, 900 };
            for (int i = 0; i < volumes.Length; i++)
            {
                _state.Update(18000, 17990, 17995, volumes[i], t.AddMinutes(i + 1));
            }

            Assert.That(_state.VolEma, Is.GreaterThan(0), "VolEma should be positive after 5 bars");
            // EMA should be between min and max of all volumes seen
            Assert.That(_state.VolEma, Is.InRange(800.0, 1500.0),
                "VolEma should be within range of observed volumes");
        }

        // -----------------------------------------------------------------
        // Test 7: Reset clears all state
        // -----------------------------------------------------------------
        [Test]
        public void Reset_ClearsAllState()
        {
            var t = new DateTime(2026, 1, 5, 10, 0, 0);
            for (int i = 0; i < 25; i++)
                _state.Update(18000 + i, 17990 + i, 17995 + i, 1000, t.AddMinutes(i));

            _state.SetPriorDayPoc(18050);
            _state.HtfBias = MADTrend.Bullish;
            _state.HtfMomentum = 0.8;

            _state.Reset();

            Assert.That(_state.Atr20, Is.EqualTo(0));
            Assert.That(_state.VolEma, Is.EqualTo(0));
            Assert.That(_state.SessionHigh, Is.EqualTo(0));
            Assert.That(_state.SessionLow, Is.EqualTo(0));
            Assert.That(_state.OpeningRangeHigh, Is.EqualTo(0));
            Assert.That(_state.OpeningRangeLow, Is.EqualTo(0));
            Assert.That(_state.PrevDayHigh, Is.EqualTo(0));
            Assert.That(_state.PrevDayLow, Is.EqualTo(0));
            Assert.That(_state.PrevDayClose, Is.EqualTo(0));
            Assert.That(_state.PrevDayPoc, Is.EqualTo(0));
            Assert.That(_state.HtfBias, Is.EqualTo(MADTrend.Neutral));
            Assert.That(_state.HtfMomentum, Is.EqualTo(0));
        }

        // -----------------------------------------------------------------
        // Test 8: SetPriorDayPoc sets PrevDayPoc
        // -----------------------------------------------------------------
        [Test]
        public void SetPriorDayPoc_SetsValue()
        {
            _state.SetPriorDayPoc(18100.50);
            Assert.That(_state.PrevDayPoc, Is.EqualTo(18100.50));
        }

        // -----------------------------------------------------------------
        // Test 9: ATR20 correctly uses prior close for true range (gap detection)
        // -----------------------------------------------------------------
        [Test]
        public void Atr20_AccountsForGaps_ViaRealTrueRange()
        {
            var t = new DateTime(2026, 1, 5, 10, 0, 0);

            // Bar 1: range = 10 (no prior close, TR = high - low)
            _state.Update(18010, 18000, 18005, 500, t);

            // Bar 2: gap up — close was 18005, now bar opens at 18020
            // TR = max(18025-18015, |18025-18005|, |18015-18005|) = max(10, 20, 10) = 20
            _state.Update(18025, 18015, 18020, 500, t.AddMinutes(1));

            // Feed 18 more bars with small range (5 pts each)
            for (int i = 2; i < 20; i++)
            {
                double h = 18020 + 5;
                double l = 18020;
                _state.Update(h, l, 18022, 500, t.AddMinutes(i));
            }

            // ATR20 should reflect the gap bar's larger TR, so avg > 5
            Assert.That(_state.Atr20, Is.GreaterThan(5.0),
                "ATR20 should be > 5 due to gap bar contributing TR=20");
        }
    }
}
