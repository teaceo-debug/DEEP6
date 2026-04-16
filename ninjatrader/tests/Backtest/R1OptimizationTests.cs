// R1OptimizationTests: NUnit tests for Round-1 optimization improvements.
//
// Coverage (8+ tests):
//   1. Weight change: thesis-heavy weights produce correct base score (abs=32, exh=24)
//   2. Weight change: trapped category contributes 0 weight but still counts toward catCount
//   3. Breakeven: MFE=10 triggers breakeven (stop moves to entry+2t)
//   4. Breakeven: MFE=9 does NOT trigger breakeven (stop stays at hard stop)
//   5. Scale-out: 50% exits at ScaleOutTargetTicks=16, remainder continues to TargetTicks=32
//   6. Scale-out: SCALE_OUT_PARTIAL + SCALE_OUT_FINAL records emitted correctly
//   7. Directional filter: mixed-direction signals vetoed (DirectionalDisagreementVeto)
//   8. Directional filter: all-agreeing signals pass
//   9. Time blackout: entry at 1530 blocked (BlackoutVeto)
//  10. Time blackout: entry at 1529 passes (just before blackout)
//  11. Time blackout: entry at 1601 passes (just after blackout)
//  12. Breakeven: ratchet-only — stop does not move back below breakeven level

using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Backtest
{
    [TestFixture]
    [Category("R1Optimization")]
    public class R1OptimizationTests
    {
        private string _tempDir;

        [SetUp]
        public void SetUp()
        {
            _tempDir = Path.Combine(Path.GetTempPath(), "r1_tests_" + Path.GetRandomFileName());
            Directory.CreateDirectory(_tempDir);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, true);
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        private static SignalResult SR(string id, int dir, double strength)
            => new SignalResult(id, dir, strength, 0UL, string.Empty, 0.0);

        private string WriteSession(string name, IEnumerable<string> lines)
        {
            string path = Path.Combine(_tempDir, name);
            File.WriteAllLines(path, lines);
            return path;
        }

        /// <summary>Bull entry bar at barsSinceOpen, with strong signals and zone score.</summary>
        private static string BullBar(int barIdx, int barsSinceOpen, double barClose, double atr = 0.0)
        {
            string atrField = atr > 0 ? $",\"atr\":{atr.ToString(System.Globalization.CultureInfo.InvariantCulture)}" : "";
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":35,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneScore\":60.0,\"zoneDistTicks\":2.0{atrField}," +
                "\"signals\":[" +
                "{\"signalId\":\"ABS-01\",\"direction\":1,\"strength\":0.8,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"ABS\"}," +
                "{\"signalId\":\"EXH-02\",\"direction\":1,\"strength\":0.7,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"EXH\"}," +
                "{\"signalId\":\"DELT-04\",\"direction\":1,\"strength\":0.6,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"DELT\"}," +
                "{\"signalId\":\"IMB-T2\",\"direction\":1,\"strength\":0.5,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"STACKED_T2\"}," +
                "{\"signalId\":\"AUCT-01\",\"direction\":1,\"strength\":0.55,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"AUCT\"}" +
                "]}";
        }

        /// <summary>Bull bar with one bear signal mixed in (for directional filter tests).</summary>
        private static string MixedBar(int barIdx, int barsSinceOpen, double barClose)
        {
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":10,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                "\"zoneScore\":60.0,\"zoneDistTicks\":2.0," +
                "\"signals\":[" +
                "{\"signalId\":\"ABS-01\",\"direction\":1,\"strength\":0.8,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"ABS\"}," +
                "{\"signalId\":\"EXH-02\",\"direction\":1,\"strength\":0.7,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"EXH\"}," +
                "{\"signalId\":\"DELT-04\",\"direction\":1,\"strength\":0.6,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"DELT\"}," +
                "{\"signalId\":\"IMB-T2\",\"direction\":1,\"strength\":0.5,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"STACKED_T2\"}," +
                // Opposing signal — should trigger DirectionalDisagreementVeto
                "{\"signalId\":\"TRAP-01\",\"direction\":-1,\"strength\":0.4,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"TRAP\"}" +
                "]}";
        }

        /// <summary>Quiet bar with no signals.</summary>
        private static string QuietBar(int barIdx, int barsSinceOpen, double barClose)
        {
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":0,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                "\"zoneScore\":0.0,\"zoneDistTicks\":999.0,\"signals\":[]}}";
        }

        private static BacktestConfig BaseConfig() => new BacktestConfig
        {
            ScoreEntryThreshold  = 40.0,
            MinTierForEntry      = SignalTier.TYPE_C,
            StopLossTicks        = 40,
            TargetTicks          = 32,
            MaxBarsInTrade       = 50,
            TickSize             = 0.25,
            TickValue            = 5.0,
            VolSurgeVetoEnabled  = false,
            SlowGrindVetoEnabled = false,
            TrailingStopEnabled  = false,
            ScaleOutEnabled      = false,
            BreakevenEnabled     = false,
            StrictDirectionEnabled = false,
            BlackoutWindowStart  = 0,   // disabled by default in base config
            BlackoutWindowEnd    = 0,
        };

        // =====================================================================
        // 1. Weight change: R3 attribution-optimized weights — abs=20+exh=15.7 base score
        // R3: was R1 abs(32)+exh(24)=56; now abs(20)+exh(15.7)=35.7
        // =====================================================================

        [Test]
        public void Weights_R1_AbsExhBaseScore_Is56()
        {
            // R3 weights: abs(20.0) + exh(15.7) = 35.7; bars=100 (no IB); agreement=1.0; no zone → score=35.7
            var signals = new[]
            {
                SR("ABS-01", +1, 0.8),
                SR("EXH-03", +1, 0.6),
            };
            var result = ConfluenceScorer.Score(signals, barsSinceOpen: 100, barDelta: 10, barClose: 17500.0);

            // 2 categories, score = 35.7 (R3: abs=20.0 + exh=15.7)
            Assert.That(result.TotalScore, Is.InRange(35.6999, 35.7001),
                "R3 abs(20.0)+exh(15.7)=35.7 base score");
            Assert.That(result.CategoryCount, Is.EqualTo(2), "abs + exh = 2 categories");
        }

        // =====================================================================
        // 2. Weight change: trapped contributes 0 weight but still counted in catCount
        // R3: abs(20)+exh(15.7)+trap(0)+delta(14.3)=50.0; catCount=4
        // =====================================================================

        [Test]
        public void Weights_R1_TrappedZeroWeight_StillCountsCategory()
        {
            // R3: abs(20.0)+exh(15.7)+trap(0)+delta(14.3) = 50.0; catCount=4
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-03",  +1, 0.6),
                SR("TRAP-01", +1, 0.5),
                SR("DELT-04", +1, 0.5),
            };
            var result = ConfluenceScorer.Score(signals, barsSinceOpen: 100, barDelta: 10, barClose: 17500.0);

            Assert.That(result.CategoryCount, Is.EqualTo(4),
                "trapped still counted as category even with W_TRAPPED=0");
            Assert.That(result.TotalScore, Is.InRange(49.9999, 50.0001),
                "R3: abs(20)+exh(15.7)+trap(0)+delta(14.3)=50.0 base score");
            Assert.That(result.CategoriesFiring, Does.Contain("trapped"),
                "trapped appears in CategoriesFiring despite zero weight");
        }

        // =====================================================================
        // 3. Breakeven: MFE=10 triggers breakeven stop
        // =====================================================================

        [Test]
        public void Breakeven_MFE10_TriggersBreakeven()
        {
            // Entry bar close = 17500.0. Entry price = 17500.0 + 1t slippage = 17500.25.
            // MFE is measured from entryPrice. To get MFE=10 ticks, bar close must reach
            // entryPrice + 10*tickSize = 17500.25 + 2.50 = 17502.75.
            // Breakeven arms at entryPrice + 2t = 17500.75.
            // Then price drops to 17500.50 (below 17500.75) → BE stop triggers.
            double entryClose = 17500.0;
            double tickSize   = 0.25;
            double entryPrice = entryClose + 1 * tickSize; // 17500.25 (slippage=1)

            var lines = new List<string>
            {
                BullBar(0, 10, entryClose),                            // entry bar
                QuietBar(1, 11, entryPrice + 10 * tickSize),           // MFE=10t exactly → arms BE at +2t
                QuietBar(2, 12, entryPrice + 1.5 * tickSize),          // below BE stop (entry+2t) → STOP
            };

            string path = WriteSession("be_mfe10.ndjson", lines);
            var config = BaseConfig();
            config.BreakevenEnabled         = true;
            config.BreakevenActivationTicks = 10;
            config.BreakevenOffsetTicks     = 2;
            config.StopLossTicks            = 40; // hard stop far away

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1), "Should have exactly 1 trade");
            Assert.That(result.Trades[0].ExitReason, Is.EqualTo("STOP_LOSS"),
                "Breakeven triggered should produce STOP_LOSS exit");
            // P&L should be near breakeven (small positive from +2t offset, minus slippage)
            Assert.That(result.Trades[0].PnlTicks, Is.GreaterThanOrEqualTo(-2.0),
                "Breakeven stop limits loss to near-zero");
        }

        // =====================================================================
        // 4. Breakeven: MFE=9 does NOT trigger breakeven
        // =====================================================================

        [Test]
        public void Breakeven_MFE9_DoesNotTriggerBreakeven()
        {
            // Entry price = 17500.0 + 1t slippage = 17500.25.
            // MFE=9 means bar close reaches entryPrice + 9t = 17502.50 — one tick short of BE trigger.
            // Price returns near entry and exits via MAX_BARS (hard stop at 40t is far away).
            double entryClose = 17500.0;
            double tickSize   = 0.25;
            double entryPrice = entryClose + 1 * tickSize; // 17500.25

            var lines = new List<string>
            {
                BullBar(0, 10, entryClose),
                QuietBar(1, 11, entryPrice + 9 * tickSize),   // MFE=9t — BE not armed
                QuietBar(2, 12, entryPrice - 1 * tickSize),   // drop — but hard stop is 40t away
                QuietBar(3, 13, entryPrice),
            };

            string path = WriteSession("be_mfe9.ndjson", lines);
            var config = BaseConfig();
            config.BreakevenEnabled         = true;
            config.BreakevenActivationTicks = 10;
            config.BreakevenOffsetTicks     = 2;
            config.MaxBarsInTrade           = 3;

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1));
            Assert.That(result.Trades[0].ExitReason, Is.EqualTo("MAX_BARS"),
                "MFE=9 should not arm breakeven; trade exits via MAX_BARS");
        }

        // =====================================================================
        // 5 & 6. Scale-out: 50% exits at 16t, remainder at 32t
        // =====================================================================

        [Test]
        public void ScaleOut_50Pct_At16t_Then_FinalAt32t()
        {
            // Entry at 17500+slippage=17500.25.
            // Bar 1: price = 17500.25 + 16*0.25 = 17504.25 → SCALE_OUT_PARTIAL fires (50%)
            // Bar 2: price = 17500.25 + 32*0.25 = 17508.25 → SCALE_OUT_FINAL fires (remaining 50%)
            double entryClose = 17500.0;
            double tickSize   = 0.25;
            // entry price = 17500.0 + 1*0.25 = 17500.25 (slippage=1)
            double entryPrice = entryClose + tickSize;  // 17500.25

            var lines = new List<string>
            {
                BullBar(0, 10, entryClose),
                QuietBar(1, 11, entryPrice + 16 * tickSize),  // hits T1=16t from entry
                QuietBar(2, 12, entryPrice + 32 * tickSize),  // hits T2=32t from entry
            };

            string path = WriteSession("scaleout_test.ndjson", lines);
            var config = BaseConfig();
            config.ScaleOutEnabled      = true;
            config.ScaleOutPercent      = 0.5;
            config.ScaleOutTargetTicks  = 16;
            config.TargetTicks          = 32;

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(2),
                "Scale-out should produce 2 trade records (partial + final)");

            var partial = result.Trades[0];
            var final   = result.Trades[1];

            Assert.That(partial.ExitReason, Is.EqualTo("SCALE_OUT_PARTIAL"),
                "First record must be SCALE_OUT_PARTIAL");
            Assert.That(final.ExitReason, Is.EqualTo("SCALE_OUT_FINAL"),
                "Second record must be SCALE_OUT_FINAL");

            // Partial P&L should be half of full position (PnlDollars scaled by 0.5)
            Assert.That(partial.PnlTicks, Is.GreaterThan(0), "Partial exit should be profitable");
            Assert.That(final.PnlTicks,   Is.GreaterThan(0), "Final exit should be profitable");

            // PnlDollars of partial should be ~half of final (both hit targets; partial at 16t, final at 32t)
            // partial: ~16t pnl * 0.5 fraction; final: ~32t pnl * 0.5 fraction
            Assert.That(partial.PnlDollars, Is.LessThan(final.PnlDollars),
                "Partial at 16t (half position) earns less dollars than final at 32t (half position)");
        }

        // =====================================================================
        // 7. Directional filter: mixed signals vetoed via EvaluateWithContext
        // =====================================================================

        [Test]
        public void DirectionalFilter_MixedSignals_ReturnsDisagreementVeto()
        {
            // Dominant direction = +1 (bull). One signal has direction=-1 → veto.
            var signals = new[]
            {
                SR("ABS-01", +1, 0.8),
                SR("EXH-02", +1, 0.7),
                SR("DELT-04", +1, 0.6),
                SR("IMB-T2", +1, 0.5),
                SR("TRAP-01", -1, 0.4),  // opposing signal
            };

            var scored = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 60.0, zoneDistTicks: 2.0);

            // scored.Direction should be +1 (bull dominates)
            Assert.That(scored.Direction, Is.EqualTo(+1), "Bull should dominate");

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:        40.0,
                minTier:               SignalTier.TYPE_C,
                gateState:             new ScorerEntryGate.SessionGateState(),
                volSurgeVetoEnabled:   false,
                slowGrindVetoEnabled:  false,
                strictDirectionEnabled: true,
                signals:               signals);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.DirectionalDisagreementVeto),
                "Mixed-direction signals must trigger DirectionalDisagreementVeto");
        }

        // =====================================================================
        // 8. Directional filter: all-agreeing signals pass
        // =====================================================================

        [Test]
        public void DirectionalFilter_AllAgreeingSignals_Passes()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-02",  +1, 0.7),
                SR("DELT-04", +1, 0.6),
                SR("IMB-T2",  +1, 0.5),
                SR("AUCT-01", +1, 0.55),
            };

            var scored = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 60.0, zoneDistTicks: 2.0);

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:        40.0,
                minTier:               SignalTier.TYPE_C,
                gateState:             new ScorerEntryGate.SessionGateState(),
                volSurgeVetoEnabled:   false,
                slowGrindVetoEnabled:  false,
                strictDirectionEnabled: true,
                signals:               signals);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed),
                "All-agreeing signals with strict mode should pass");
        }

        // =====================================================================
        // 9. Time blackout: barTimeHHMM=1530 blocked
        // =====================================================================

        [Test]
        public void TimeBlackout_1530_IsBlocked()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-02",  +1, 0.7),
                SR("DELT-04", +1, 0.6),
                SR("IMB-T2",  +1, 0.5),
                SR("AUCT-01", +1, 0.55),
            };
            var scored = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 60.0, zoneDistTicks: 2.0);

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            new ScorerEntryGate.SessionGateState(),
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: false,
                strictDirectionEnabled: false,
                signals:              signals,
                blackoutWindowStart:  1530,
                blackoutWindowEnd:    1600,
                barTimeHHMM:          1530);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.BlackoutVeto),
                "barTimeHHMM=1530 must be blocked by blackout window [1530, 1600]");
        }

        // =====================================================================
        // 10. Time blackout: barTimeHHMM=1529 passes (just before window)
        // =====================================================================

        [Test]
        public void TimeBlackout_1529_Passes()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-02",  +1, 0.7),
                SR("DELT-04", +1, 0.6),
                SR("IMB-T2",  +1, 0.5),
                SR("AUCT-01", +1, 0.55),
            };
            var scored = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 60.0, zoneDistTicks: 2.0);

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            new ScorerEntryGate.SessionGateState(),
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: false,
                strictDirectionEnabled: false,
                signals:              signals,
                blackoutWindowStart:  1530,
                blackoutWindowEnd:    1600,
                barTimeHHMM:          1529);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed),
                "barTimeHHMM=1529 is before blackout window — must pass");
        }

        // =====================================================================
        // 11. Time blackout: barTimeHHMM=1601 passes (just after window)
        // =====================================================================

        [Test]
        public void TimeBlackout_1601_Passes()
        {
            var signals = new[]
            {
                SR("ABS-01",  +1, 0.8),
                SR("EXH-02",  +1, 0.7),
                SR("DELT-04", +1, 0.6),
                SR("IMB-T2",  +1, 0.5),
                SR("AUCT-01", +1, 0.55),
            };
            var scored = ConfluenceScorer.Score(
                signals, barsSinceOpen: 30, barDelta: 20, barClose: 17500.0,
                zoneScore: 60.0, zoneDistTicks: 2.0);

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            new ScorerEntryGate.SessionGateState(),
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: false,
                strictDirectionEnabled: false,
                signals:              signals,
                blackoutWindowStart:  1530,
                blackoutWindowEnd:    1600,
                barTimeHHMM:          1601);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed),
                "barTimeHHMM=1601 is after blackout window — must pass");
        }

        // =====================================================================
        // 12. Breakeven: ratchet-only — stop never moves back
        // =====================================================================

        [Test]
        public void Breakeven_RatchetOnly_StopNeverMovesBack()
        {
            // After BE arms at MFE=10, price retraces. Stop stays at entry+2t = 17500.75.
            // Bar 3 close at entry+1t=17500.50 < BE stop 17500.75 → triggers STOP_LOSS.
            double entryClose = 17500.0;
            double tickSize   = 0.25;
            double entryPrice = entryClose + tickSize;  // 17500.25 after slippage

            var lines = new List<string>
            {
                BullBar(0, 10, entryClose),
                QuietBar(1, 11, entryPrice + 10 * tickSize),  // MFE=10t → BE arms at entry+2t=17500.75
                QuietBar(2, 12, entryPrice + 5 * tickSize),   // partial retrace — still above BE stop
                QuietBar(3, 13, entryPrice + 1 * tickSize),   // 17500.50 < BE stop 17500.75 → STOP_LOSS
            };

            string path = WriteSession("be_ratchet.ndjson", lines);
            var config = BaseConfig();
            config.BreakevenEnabled         = true;
            config.BreakevenActivationTicks = 10;
            config.BreakevenOffsetTicks     = 2;
            config.StopLossTicks            = 40; // hard stop far away — must not trigger

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1));
            Assert.That(result.Trades[0].ExitReason, Is.EqualTo("STOP_LOSS"),
                "Price crossing BE stop (not hard stop) should produce STOP_LOSS");
            // P&L should be positive (stopped out above entry, BE offset=+2t)
            Assert.That(result.Trades[0].PnlTicks, Is.GreaterThanOrEqualTo(0.0),
                "BE ratchet stop should lock in non-negative P&L");
        }
    }
}
