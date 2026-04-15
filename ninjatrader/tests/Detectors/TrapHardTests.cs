// TrapHardTests: fixture-driven tests for TRAP-05 (CVD Trend Reversal Trap via polyfit).
//
// Wave 5 addition. TRAP-05 uses LeastSquares.Fit1 to measure CVD slope over a lookback window
// and fires when current bar delta opposes the prior trend.
//
// Python reference: deep6/engines/trap.py TrapEngine._detect_cvd_trap() lines 298-349

using System;
using System.Collections.Generic;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Trap;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class TrapHardTests
    {
        private static FootprintBar MakeBar(double open, double high, double low, double close,
            long barDelta, long totalVol)
        {
            var bar = new FootprintBar
            {
                BarIndex = 1, Open = open, High = high, Low = low, Close = close,
            };
            bar.Levels[low]  = new Cell { AskVol = totalVol / 3, BidVol = totalVol / 6 };
            bar.Levels[high] = new Cell { AskVol = totalVol / 6, BidVol = totalVol / 3 };
            bar.Finalize();
            bar.BarDelta = barDelta;
            bar.TotalVol = totalVol;
            bar.Cvd      = barDelta;
            bar.MaxDelta = barDelta > 0 ? barDelta : 50;
            bar.MinDelta = barDelta < 0 ? barDelta : -50;
            return bar;
        }

        private static SessionContext MakeSessionWithCvdHistory(long[] cvdHistory)
        {
            var session = new SessionContext { TickSize = 0.25, VolEma20 = 500 };
            foreach (var v in cvdHistory)
                SessionContext.Push(session.CvdHistory, v);
            return session;
        }

        // -------------------------------------------------------------------
        // TRAP-05: Fires when current delta opposes prior CVD trend
        // -------------------------------------------------------------------

        [Test]
        public void Trap05_FiresBearish_WhenCvdTrendingUpAndDeltaNegative_FromFixture()
        {
            // Fixture: trap-05-cvd-trap.json
            // cvdHistory ascending (slope ~100/bar > min_slope=50), current barDelta=-500 (bearish)
            var session = MakeSessionWithCvdHistory(
                new long[] { 0, 100, 200, 300, 400, 500, 600, 700, 800, 900 });

            var bar = MakeBar(20010.0, 20012.0, 20002.0, 20003.0, -500, 800);
            var results = new TrapDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "TRAP-05" && r.Direction == -1),
                "TRAP-05 should fire bearish when prior CVD trend is up but current delta is negative");
        }

        [Test]
        public void Trap05_FiresBullish_WhenCvdTrendingDownAndDeltaPositive()
        {
            // cvdHistory descending (slope ~-100/bar), current barDelta=+500 (bullish)
            var session = MakeSessionWithCvdHistory(
                new long[] { 900, 800, 700, 600, 500, 400, 300, 200, 100, 0 });

            var bar = MakeBar(19995.0, 20008.0, 19993.0, 20005.0, 500, 800);
            var results = new TrapDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "TRAP-05" && r.Direction == 1),
                "TRAP-05 should fire bullish when prior CVD trend is down but current delta is positive");
        }

        [Test]
        public void Trap05_FiresOnlyWhenCurrentDeltaOpposesPriorCvdSlope()
        {
            // CVD trending up (slope ~100), current barDelta also positive → NO fire (no reversal)
            var session = MakeSessionWithCvdHistory(
                new long[] { 0, 100, 200, 300, 400, 500, 600, 700, 800, 900 });

            var bar = MakeBar(20000.0, 20010.0, 19998.0, 20008.0, 500, 800);
            var results = new TrapDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "TRAP-05"),
                "TRAP-05 should NOT fire when current delta aligns with prior CVD trend (both bullish)");
        }

        [Test]
        public void Trap05_DoesNotFire_WhenCvdTooFlat()
        {
            // CVD slope is too small (slope < min_slope=50): all values ~constant
            var session = MakeSessionWithCvdHistory(
                new long[] { 100, 101, 99, 100, 102, 98, 100, 101, 100, 99 });

            var bar = MakeBar(20000.0, 20005.0, 19995.0, 20000.0, -300, 600);
            var results = new TrapDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "TRAP-05"),
                "TRAP-05 should NOT fire when CVD slope is below minimum threshold (flat CVD)");
        }

        [Test]
        public void Trap05_DoesNotFire_WithInsufficientHistory()
        {
            // Only 5 bars in history — lookback is 10
            var session = MakeSessionWithCvdHistory(new long[] { 0, 100, 200, 300, 400 });

            var bar = MakeBar(20005.0, 20008.0, 20000.0, 20002.0, -400, 700);
            var results = new TrapDetector().OnBar(bar, session);

            Assert.That(results, Has.None.Matches<SignalResult>(r => r.SignalId == "TRAP-05"),
                "TRAP-05 should NOT fire when CvdHistory has fewer entries than CvdTrapLookback");
        }

        [Test]
        public void Trap05_DetailString_MentionsSlopeOrPolyfit()
        {
            var session = MakeSessionWithCvdHistory(
                new long[] { 0, 100, 200, 300, 400, 500, 600, 700, 800, 900 });

            var bar = MakeBar(20010.0, 20012.0, 20002.0, 20003.0, -500, 800);
            var results = new TrapDetector().OnBar(bar, session);

            var trap05 = Array.Find(results, r => r.SignalId == "TRAP-05");
            Assert.That(trap05, Is.Not.Null, "TRAP-05 should fire");
            Assert.That(trap05.Detail, Does.Contain("slope").Or.Contain("polyfit"),
                "TRAP-05 Detail should mention slope/polyfit for diagnostic traceability");
        }
    }
}
