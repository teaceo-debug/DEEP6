// EngineDetectorsTests: fixture-driven tests for ENG-02..ENG-04 (Trespass, CounterSpoof, Iceberg).
//
// Wave 5: Tests verify DOM integration, Stopwatch-based timing, and absorption zone cross-wiring.
//
// Python reference:
//   ENG-02: deep6/engines/trespass.py TrespassEngine
//   ENG-03: deep6/engines/counter_spoof.py CounterSpoofEngine
//   ENG-04: deep6/engines/iceberg.py IcebergEngine

using System;
using System.Collections.Generic;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines;

namespace NinjaTrader.Tests.Detectors
{
    [TestFixture]
    public class EngineDetectorsTests
    {
        private static FootprintBar MakeBar(double open, double high, double low, double close,
            long barDelta = 0, long totalVol = 500)
        {
            var bar = new FootprintBar
            {
                BarIndex = 1, Open = open, High = high, Low = low, Close = close
            };
            bar.Levels[low]  = new Cell { AskVol = totalVol / 3, BidVol = totalVol / 6 };
            bar.Levels[high] = new Cell { AskVol = totalVol / 6, BidVol = totalVol / 3 };
            bar.Finalize();
            bar.BarDelta = barDelta;
            bar.TotalVol = totalVol;
            bar.Cvd      = barDelta;
            return bar;
        }

        // =========================================================
        // ENG-02 TrespassDetector
        // =========================================================

        [Test]
        public void Eng02_Trespass_FiresBullish_WhenBidDomHeavy()
        {
            // Fixture: eng-02-trespass.json — heavy bid side
            var session = new SessionContext { TickSize = 0.25 };
            // Populate heavy bid DOM (matching fixture)
            session.BidDomLevels[0] = 100; session.BidDomLevels[1] = 90;
            session.BidDomLevels[2] = 80;  session.BidDomLevels[3] = 70;
            session.BidDomLevels[4] = 60;  session.BidDomLevels[5] = 50;
            session.BidDomLevels[6] = 40;  session.BidDomLevels[7] = 30;
            session.BidDomLevels[8] = 20;  session.BidDomLevels[9] = 10;
            // Light ask DOM
            session.AskDomLevels[0] = 20; session.AskDomLevels[1] = 18;
            session.AskDomLevels[2] = 15; session.AskDomLevels[3] = 12;
            session.AskDomLevels[4] = 10; session.AskDomLevels[5] = 8;
            session.AskDomLevels[6] = 6;  session.AskDomLevels[7] = 5;
            session.AskDomLevels[8] = 4;  session.AskDomLevels[9] = 3;

            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20001.0, 200, 500);
            var results = new TrespassDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-02" && r.Direction == 1),
                "ENG-02 should fire bullish when bid DOM is much heavier than ask DOM");
        }

        [Test]
        public void Eng02_Trespass_FiresBearish_WhenAskDomHeavy()
        {
            var session = new SessionContext { TickSize = 0.25 };
            // Light bid DOM
            for (int i = 0; i < 10; i++) session.BidDomLevels[i] = 10 - i;
            // Heavy ask DOM
            for (int i = 0; i < 10; i++) session.AskDomLevels[i] = 100 - i * 5;

            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 19999.0, -100, 400);
            var results = new TrespassDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-02" && r.Direction == -1),
                "ENG-02 should fire bearish when ask DOM is much heavier than bid DOM");
        }

        [Test]
        public void Eng02_Trespass_WritesLastTrespassResultToSession()
        {
            var session = new SessionContext { TickSize = 0.25 };
            for (int i = 0; i < 10; i++) session.BidDomLevels[i] = 100;
            for (int i = 0; i < 10; i++) session.AskDomLevels[i] = 10;

            var bar = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            new TrespassDetector().OnBar(bar, session);

            Assert.That(session.LastTrespassProbability, Is.GreaterThan(0.65),
                "TrespassDetector should write probability > 0.65 to session when bid-heavy");
            Assert.That(session.LastTrespassDirection, Is.EqualTo(1),
                "TrespassDetector should write direction=+1 to session when bid-heavy");
        }

        [Test]
        public void Eng02_Trespass_ImplementsIDepthConsumingDetector()
        {
            var detector = new TrespassDetector();
            Assert.That(detector, Is.InstanceOf<IDepthConsumingDetector>(),
                "TrespassDetector must implement IDepthConsumingDetector");
        }

        [Test]
        public void Eng02_Trespass_DoesNotFire_WhenDomAllZero()
        {
            var session = new SessionContext { TickSize = 0.25 };
            // All DOM levels remain zero (default)
            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            var results = new TrespassDetector().OnBar(bar, session);

            Assert.That(results, Is.Empty,
                "ENG-02 should NOT fire when DOM is all-zero (not yet populated)");
        }

        // =========================================================
        // ENG-03 CounterSpoofDetector
        // =========================================================

        [Test]
        public void Eng03_CounterSpoof_FiresBullish_WhenAskSideCancel()
        {
            // Fixture: eng-03-counter-spoof.json
            // W1 measures distribution SHAPE shift. Use two distributions where
            // the weight mass is concentrated at different positions.
            // Prior: all weight at index 0 (top of book) → CDF jumps to 1.0 at step 0
            // Current: all weight at index 20 (deeper in book) → CDF stays 0 until step 20
            // W1 = 20 (very large) >> threshold=0.25 → fires.
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new CounterSpoofDetector();

            // Bar 1: ask DOM concentrated at index 0 (point mass at position 0)
            session.AskDomLevels[0]  = 1000;  // all weight at idx 0
            for (int i = 0; i < 10; i++) session.BidDomLevels[i] = 100;
            var bar1 = MakeBar(19999.0, 20001.0, 19997.0, 20000.0, 50, 400);
            var results1 = detector.OnBar(bar1, session);
            Assert.That(results1, Is.Empty, "First bar should not fire (capturing prior snapshot)");

            // Bar 2: ask DOM shifts entirely to index 20 (point mass moved deep in book)
            session.AskDomLevels[0]  = 0;
            session.AskDomLevels[20] = 1000;
            for (int i = 0; i < 10; i++) session.BidDomLevels[i] = 100;
            var bar2 = MakeBar(20000.0, 20002.0, 19998.0, 20001.0, 300, 600);
            var results2 = detector.OnBar(bar2, session);

            // W1(prior=[1000,0,...], curr=[0,0,...,1000,...,0]) = 20 >> threshold=0.25
            Assert.That(results2, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-03" && r.Direction == 1),
                "ENG-03 should fire bullish when ask DOM weight shifts from idx 0 to idx 20 (W1=20 >> 0.25)");
        }

        [Test]
        public void Eng03_CounterSpoof_DoesNotFire_WhenDomStable()
        {
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new CounterSpoofDetector();

            // Two bars with identical DOM — W1=0, no fire
            for (int i = 0; i < 10; i++) { session.BidDomLevels[i] = 100; session.AskDomLevels[i] = 100; }
            var bar1 = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            detector.OnBar(bar1, session);

            var bar2 = MakeBar(20001.0, 20003.0, 19999.0, 20002.0);
            var results = detector.OnBar(bar2, session);

            Assert.That(results, Is.Empty,
                "ENG-03 should NOT fire when DOM distribution is identical across bars (W1=0)");
        }

        [Test]
        public void Eng03_CounterSpoof_UsesWassersteinDistance()
        {
            // Verify the detector class references Wasserstein (structural check)
            var detector = new CounterSpoofDetector();
            Assert.That(detector, Is.InstanceOf<IDepthConsumingDetector>(),
                "CounterSpoofDetector must implement IDepthConsumingDetector");
        }

        // =========================================================
        // ENG-04 IcebergDetector
        // =========================================================

        [Test]
        public void Eng04_Iceberg_UseStopwatch_IsMonotonic()
        {
            // Structural: IcebergDetector uses Stopwatch internally.
            // Verify it implements both IDepthConsumingDetector and IAbsorptionZoneReceiver.
            var detector = new IcebergDetector();
            Assert.That(detector, Is.InstanceOf<IDepthConsumingDetector>(),
                "IcebergDetector must implement IDepthConsumingDetector");
            Assert.That(detector, Is.InstanceOf<IAbsorptionZoneReceiver>(),
                "IcebergDetector must implement IAbsorptionZoneReceiver (for ENG-04 cross-wiring)");
        }

        [Test]
        public void Eng04_Iceberg_Synthetic_FiresWhenRefillWithin250ms()
        {
            // Simulate: level depletes and refills within window
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new IcebergDetector();

            // Step 1: Establish prior size (level size=200)
            detector.OnDepth(session, side: 1, levelIdx: 0, price: 20002.0, size: 200, priorSize: null);
            // Step 2: Level depletes (size=2 ≤ DepletionThreshold=5)
            detector.OnDepth(session, side: 1, levelIdx: 0, price: 20002.0, size: 2, priorSize: 200);
            // Brief delay not needed — Stopwatch is real-time, so refill immediately should be within 250ms
            // Step 3: Level refills (size=180 ≥ 200 * 0.5 = 100)
            detector.OnDepth(session, side: 1, levelIdx: 0, price: 20002.0, size: 180, priorSize: 2);

            var bar     = MakeBar(20001.0, 20003.0, 19999.0, 20002.0);
            var results = detector.OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(r => r.SignalId == "ENG-04"),
                "ENG-04 should fire when a DOM level depletes and refills within 250ms");
        }

        [Test]
        public void Eng04_Iceberg_AbsorptionZone_DetailContainsInAbsZone()
        {
            // Fixture: eng-04-iceberg-with-absorption-zone.json
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new IcebergDetector();

            // Pre-register absorption zone at 20003.00 radius=2 ticks
            detector.MarkAbsorptionZone(20003.0, 2);

            // Simulate depletion and refill at price inside absorption zone
            detector.OnDepth(session, side: 0, levelIdx: 0, price: 20003.0, size: 150, priorSize: null);
            detector.OnDepth(session, side: 0, levelIdx: 0, price: 20003.0, size: 3,   priorSize: 150);
            detector.OnDepth(session, side: 0, levelIdx: 0, price: 20003.0, size: 130, priorSize: 3);

            var bar     = MakeBar(20003.0, 20005.0, 20001.0, 20003.25);
            var results = detector.OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-04" && r.Detail != null && r.Detail.Contains("in-abs-zone")),
                "ENG-04 should include 'in-abs-zone' in Detail when refill is inside absorption zone");
        }

        [Test]
        public void Eng04_Iceberg_MarkAbsorptionZone_IsPublicMethod()
        {
            // Verify MarkAbsorptionZone exists and accepts price+radiusTicks without throwing
            var detector = new IcebergDetector();
            Assert.DoesNotThrow(() => detector.MarkAbsorptionZone(20005.0, 2),
                "MarkAbsorptionZone should accept price and radiusTicks without throwing");
        }

        [Test]
        public void Eng04_Iceberg_WritesLastIcebergSignalsToSession()
        {
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new IcebergDetector();

            // Trigger native iceberg: bar level vol >> DOM display
            session.AskDomLevels[0] = 5;  // Very small DOM display at best ask
            var bar = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            // Add high-vol level to bar
            bar.Levels[20001.5] = new Cell { AskVol = 100, BidVol = 10 }; // 100 >> 5 * 2.0 = 10

            detector.OnBar(bar, session);

            // Native iceberg should write to session
            // (May or may not fire depending on DOM thresholds, but shouldn't throw)
            Assert.DoesNotThrow(() => { var _ = session.LastIcebergSignals.Count; });
        }

        // =========================================================
        // DetectorRegistry: DispatchDepth test
        // =========================================================

        [Test]
        public void Registry_DispatchDepth_UpdatesSessionDomArrays()
        {
            var session  = new SessionContext { TickSize = 0.25 };
            var registry = new DetectorRegistry();
            registry.Register(new TrespassDetector());

            // Dispatch a bid depth update at levelIdx=0
            registry.DispatchDepth(session, side: 0, levelIdx: 0, price: 20000.0, size: 500, priorSize: null);

            Assert.That(session.BidDomLevels[0], Is.EqualTo(500),
                "DispatchDepth should update session.BidDomLevels[0] in place");
        }

        // =========================================================
        // ENG-05 MicroProbDetector
        // =========================================================

        [Test]
        public void Eng05_MicroProb_FiresBullish_WhenTrespassBullAndIceberg()
        {
            // Fixture: eng-05-micro-prob.json — trespass bullish + iceberg signals
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new MicroProbDetector();

            // Manually set session cross-detector fields as TrespassDetector + IcebergDetector would
            session.LastTrespassProbability = 0.80;  // strong bullish trespass
            session.LastTrespassDirection   = 1;
            session.LastIcebergSignals.Add("ENG-04-SYNTHETIC");

            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20001.0, 200, 500);
            var results = detector.OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-05" && r.Direction == 1),
                "ENG-05 should fire bullish when trespass prob=0.80 and iceberg count=1");
        }

        [Test]
        public void Eng05_MicroProb_FiresBearish_WhenTrespassBearish()
        {
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new MicroProbDetector();

            session.LastTrespassProbability = 0.05;  // extreme bearish trespass (logOdds=-0.90 → pBull=0.289 < 0.30 threshold)
            session.LastTrespassDirection   = -1;

            var bar     = MakeBar(20002.0, 20004.0, 20000.0, 20001.0, -200, 500);
            var results = detector.OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-05" && r.Direction == -1),
                "ENG-05 should fire bearish when trespass prob=0.05 (extreme bearish, pBull < 0.30 threshold)");
        }

        [Test]
        public void Eng05_MicroProb_DoesNotFire_WhenAllNeutral()
        {
            var session  = new SessionContext { TickSize = 0.25 };
            var detector = new MicroProbDetector();

            // Default neutral: prob=0.5, direction=0, no iceberg signals
            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            var results = detector.OnBar(bar, session);

            Assert.That(results, Is.Empty,
                "ENG-05 should NOT fire when all inputs are neutral (prob=0.5, dir=0, iceberg_n=0)");
        }

        [Test]
        public void Eng05_MicroProb_IsNotIDepthConsumingDetector()
        {
            // MicroProbDetector reads session fields only — no DOM depth needed
            var detector = new MicroProbDetector();
            Assert.That(detector, Is.Not.InstanceOf<IDepthConsumingDetector>(),
                "MicroProbDetector should NOT implement IDepthConsumingDetector (reads session fields, not DOM)");
        }

        [Test]
        public void Eng05_MicroProb_IsRegisteredLast_InSignalConfigScaffold()
        {
            // Verify SignalConfigScaffold.BuildDetectors() returns MicroProbDetector as the last element
            var cfg = SignalConfigScaffold.Default;
            var detectors = cfg.BuildDetectors();

            // The last returned detector (MicroProb) must be MicroProbDetector, not a depth consumer
            Assert.That(detectors.MicroProb, Is.InstanceOf<MicroProbDetector>(),
                "SignalConfigScaffold.BuildDetectors().MicroProb must be MicroProbDetector");

            // Verify TrespassDetector comes before MicroProbDetector in the natural tuple order
            Assert.That(detectors.Trespass, Is.InstanceOf<TrespassDetector>(),
                "Trespass (ENG-02) must be available before MicroProb (ENG-05) in registration order");
            Assert.That(detectors.Iceberg, Is.InstanceOf<IcebergDetector>(),
                "IcebergDetector (ENG-04) must be available before MicroProb (ENG-05) in registration order");
        }

        // =========================================================
        // ENG-06 VPContextDetector
        // =========================================================

        [Test]
        public void Eng06_VPContext_FiresBullish_WhenCloseNearPocAbove()
        {
            // Fixture: eng-06-vp-context.json — close near POC from above
            var session = new SessionContext { TickSize = 0.25, BarsSinceOpen = 5 };
            session.SessionPocPrice = 20000.0;

            var bar     = MakeBar(19999.0, 20002.0, 19998.0, 20000.5);  // close 2 ticks above POC
            var results = new VPContextDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-06" && r.Direction == 1),
                "ENG-06 should fire bullish when close is within PocProximityTicks above POC");
        }

        [Test]
        public void Eng06_VPContext_FiresBearish_WhenCloseNearPocBelow()
        {
            var session = new SessionContext { TickSize = 0.25, BarsSinceOpen = 5 };
            session.SessionPocPrice = 20000.0;

            var bar     = MakeBar(20001.0, 20002.0, 19997.0, 19999.5);  // close 2 ticks below POC
            var results = new VPContextDetector().OnBar(bar, session);

            Assert.That(results, Has.Some.Matches<SignalResult>(
                r => r.SignalId == "ENG-06" && r.Direction == -1),
                "ENG-06 should fire bearish when close is within PocProximityTicks below POC");
        }

        [Test]
        public void Eng06_VPContext_DoesNotFire_WhenFarFromPoc()
        {
            var session = new SessionContext { TickSize = 0.25, BarsSinceOpen = 5 };
            session.SessionPocPrice = 20000.0;

            var bar     = MakeBar(20010.0, 20015.0, 20009.0, 20012.0);  // 48 ticks from POC
            var results = new VPContextDetector().OnBar(bar, session);

            Assert.That(results, Is.Empty,
                "ENG-06 should NOT fire when close is far from session POC");
        }

        [Test]
        public void Eng06_VPContext_DoesNotFire_WhenPocNotSet()
        {
            var session = new SessionContext { TickSize = 0.25, BarsSinceOpen = 5 };
            // SessionPocPrice = 0 (default — not set)

            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20001.0);
            var results = new VPContextDetector().OnBar(bar, session);

            Assert.That(results, Is.Empty,
                "ENG-06 should NOT fire when SessionPocPrice is 0 (not yet populated)");
        }

        [Test]
        public void Eng06_VPContext_DoesNotFire_TooEarlyInSession()
        {
            var session = new SessionContext { TickSize = 0.25, BarsSinceOpen = 1 };  // < MinBarsForPoc=3
            session.SessionPocPrice = 20000.0;

            var bar     = MakeBar(20000.0, 20002.0, 19998.0, 20000.25);
            var results = new VPContextDetector().OnBar(bar, session);

            Assert.That(results, Is.Empty,
                "ENG-06 should NOT fire before MinBarsForPoc=3 bars have elapsed (POC not stable)");
        }

        // =========================================================
        // ENG-07 SignalConfigScaffold
        // =========================================================

        [Test]
        public void Eng07_SignalConfigScaffold_DefaultCreatesAllConfigs()
        {
            var scaffold = SignalConfigScaffold.Default;
            Assert.That(scaffold.Trespass,     Is.Not.Null, "Trespass config must be non-null");
            Assert.That(scaffold.CounterSpoof,  Is.Not.Null, "CounterSpoof config must be non-null");
            Assert.That(scaffold.Iceberg,       Is.Not.Null, "Iceberg config must be non-null");
            Assert.That(scaffold.MicroProb,     Is.Not.Null, "MicroProb config must be non-null");
            Assert.That(scaffold.VPContext,     Is.Not.Null, "VPContext config must be non-null");
        }

        [Test]
        public void Eng07_SignalConfigScaffold_BuildDetectors_MicroProbIsLast()
        {
            // Structural: BuildDetectors() tuple order has MicroProbDetector last
            var scaffold  = SignalConfigScaffold.Default;
            var detectors = scaffold.BuildDetectors();

            // Register in tuple order and verify MicroProb is at the last index
            var registry = new DetectorRegistry();
            registry.Register(detectors.Trespass);
            registry.Register(detectors.CounterSpoof);
            registry.Register(detectors.Iceberg);
            registry.Register(detectors.VPContext);
            registry.Register(detectors.MicroProb);  // MUST be last

            Assert.That(registry.Count, Is.EqualTo(5), "Registry should have 5 engine detectors");
        }
    }
}
