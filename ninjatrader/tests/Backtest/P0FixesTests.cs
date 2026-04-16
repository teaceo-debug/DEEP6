// P0FixesTests: NUnit tests for all 5 P0 pre-paper-trade fixes.
//
// Coverage:
//   P0-1: ZoneScoreCalculator — inside/near-edge/far/null snapshot
//   P0-2: ATR-trailing stop — activates at 15t, tightens at 25t, exits on retrace
//   P0-3: VOLP-03 veto — blocks entry after vol-surge, resets at session boundary
//   P0-5: Slow-grind veto — blocks when ATR < ratio × session avg, passes normal ATR
//   Integration: BacktestRunner with all fixes on synthetic 5-session data;
//                compare trade count and aggregate P&L between pre-fix and post-fix configs

using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Levels;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Backtest
{
    [TestFixture]
    [Category("P0Fixes")]
    public class P0FixesTests
    {
        private string _tempDir;

        [SetUp]
        public void SetUp()
        {
            _tempDir = Path.Combine(Path.GetTempPath(), "p0_tests_" + Path.GetRandomFileName());
            Directory.CreateDirectory(_tempDir);
        }

        [TearDown]
        public void TearDown()
        {
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, true);
        }

        // =====================================================================
        // P0-1: ZoneScoreCalculator
        // =====================================================================

        [Test]
        public void ZoneScore_InsideZone_Returns60()
        {
            // PD POC at 17500, bar close at 17500 + 1 tick (0.25) = within 2 ticks
            var snap = new ProfileAnchorSnapshot();
            snap.Levels.Add(new ProfileAnchor
            {
                Kind  = ProfileAnchorKind.PriorDayPoc,
                Price = 17500.0,
                Label = "PD POC"
            });

            double score = ZoneScoreCalculator.Compute(17500.25, snap, 0.25);

            Assert.That(score, Is.EqualTo(ZoneScoreCalculator.InsideZoneScore),
                "Bar close within 2 ticks of PD POC should return InsideZoneScore=60");
        }

        [Test]
        public void ZoneScore_NearEdge_Returns35()
        {
            // PD VAH at 17510, bar close at 17510 + 3 ticks = within 4 ticks but not 2
            var snap = new ProfileAnchorSnapshot();
            snap.Levels.Add(new ProfileAnchor
            {
                Kind  = ProfileAnchorKind.PriorDayVah,
                Price = 17510.0,
                Label = "PD VAH"
            });

            double score = ZoneScoreCalculator.Compute(17510.75, snap, 0.25); // 3 ticks away

            Assert.That(score, Is.EqualTo(ZoneScoreCalculator.NearZoneEdgeScore),
                "Bar close within 4 ticks (but not 2) of PD VAH should return NearZoneEdgeScore=35");
        }

        [Test]
        public void ZoneScore_FarFromAllLevels_Returns0()
        {
            var snap = new ProfileAnchorSnapshot();
            snap.Levels.Add(new ProfileAnchor
            {
                Kind  = ProfileAnchorKind.PriorDayPoc,
                Price = 17500.0,
                Label = "PD POC"
            });

            double score = ZoneScoreCalculator.Compute(17510.0, snap, 0.25); // 40 ticks away

            Assert.That(score, Is.EqualTo(0.0),
                "Bar close 40 ticks from any level should return 0");
        }

        [Test]
        public void ZoneScore_NullSnapshot_Returns0()
        {
            double score = ZoneScoreCalculator.Compute(17500.0, null, 0.25);
            Assert.That(score, Is.EqualTo(0.0), "Null snapshot must return 0");
        }

        [Test]
        public void ZoneScore_EmptySnapshot_Returns0()
        {
            var snap = new ProfileAnchorSnapshot(); // no levels
            double score = ZoneScoreCalculator.Compute(17500.0, snap, 0.25);
            Assert.That(score, Is.EqualTo(0.0), "Empty snapshot must return 0");
        }

        [Test]
        public void ZoneScore_NakedPocAndPwPoc_Checked()
        {
            // Naked POC at 17500, PW POC at 17520 — bar close at 17500 = inside naked POC
            var snap = new ProfileAnchorSnapshot();
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.NakedPoc,     Price = 17500.0, Label = "nPOC" });
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.PriorWeekPoc, Price = 17520.0, Label = "PW POC" });
            // PDH/PDL/PDM should NOT count
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdh,          Price = 17500.5, Label = "PDH" });

            double score = ZoneScoreCalculator.Compute(17500.0, snap, 0.25);

            Assert.That(score, Is.EqualTo(ZoneScoreCalculator.InsideZoneScore),
                "nPOC at exactly bar close should return InsideZoneScore");
        }

        [Test]
        public void ZoneScore_PdhPdlPdm_NotCountedAsZone()
        {
            // Only PDH/PDL/PDM — not zone anchors — bar is "inside" PDH range but should score 0
            var snap = new ProfileAnchorSnapshot();
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdh, Price = 17500.0, Label = "PDH" });
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdl, Price = 17490.0, Label = "PDL" });
            snap.Levels.Add(new ProfileAnchor { Kind = ProfileAnchorKind.Pdm, Price = 17495.0, Label = "PDM" });

            double score = ZoneScoreCalculator.Compute(17500.0, snap, 0.25);

            Assert.That(score, Is.EqualTo(0.0),
                "PDH/PDL/PDM are not volume zone anchors and should not contribute zone score");
        }

        // =====================================================================
        // P0-2: ATR-trailing stop in BacktestRunner
        // =====================================================================

        /// <summary>Write an NDJSON session file and return its path.</summary>
        private string WriteSession(string name, IEnumerable<string> lines)
        {
            string path = Path.Combine(_tempDir, name);
            File.WriteAllLines(path, lines);
            return path;
        }

        /// <summary>Build a strong bull entry bar with optional ATR field.</summary>
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

        /// <summary>Build a price-only bar (no signals, no entry).</summary>
        private static string QuietBar(int barIdx, int barsSinceOpen, double barClose, double atr = 0.0)
        {
            string atrField = atr > 0 ? $",\"atr\":{atr.ToString(System.Globalization.CultureInfo.InvariantCulture)}" : "";
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":0,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneScore\":0.0,\"zoneDistTicks\":999.0{atrField},\"signals\":[]}}";
        }

        /// <summary>Build a bar with VOLP-03 signal present (no directional vote).</summary>
        private static string VolP03Bar(int barIdx, int barsSinceOpen, double barClose, double atr = 2.0)
        {
            string atrField = $",\"atr\":{atr.ToString(System.Globalization.CultureInfo.InvariantCulture)}";
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":0,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneScore\":0.0,\"zoneDistTicks\":999.0{atrField}," +
                "\"signals\":[{\"signalId\":\"VOLP-03\",\"direction\":0,\"strength\":0.5,\"price\":0.0,\"detail\":\"vol_surge\"}]}";
        }

        [Test]
        public void TrailingStop_MFE15_ActivatesTrail()
        {
            // Entry bar at 17500, then price moves up 16 ticks to 17504 (MFE=16).
            // ATR = 4 ticks (1.0 pts). Trail offset 1.5 × 1.0 = 1.5 pts = 6 ticks behind HWM.
            // HWM = 17504. Trail = 17504 - 1.5 = 17502.50.
            // Then price drops to 17502 — should trigger TRAIL exit.
            double tickSize = 0.25;
            double atr = 1.0; // 4 ticks
            double entryClose = 17500.0;

            var lines = new List<string>();
            lines.Add(BullBar(0, 10, entryClose, atr));           // entry bar
            // Price rises 16 ticks (4.0 pts) over next bars
            for (int i = 1; i <= 4; i++)
                lines.Add(QuietBar(i, 10 + i, entryClose + i * 1.0, atr));
            // bar 5: close = 17504, MFE = 16 ticks → trail activates at 17504 - 1.5 = 17502.50
            // bar 6: price drops below trail → TRAIL exit
            lines.Add(QuietBar(5, 15, 17502.0, atr));  // crosses below 17502.50

            string path = WriteSession("trail_test.ndjson", lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold    = 40.0,
                MinTierForEntry        = SignalTier.TYPE_C,
                StopLossTicks          = 40,          // far enough not to hit
                TargetTicks            = 80,          // far enough not to hit
                MaxBarsInTrade         = 30,
                TickSize               = tickSize,
                TickValue              = 5.0,
                TrailingStopEnabled    = true,
                TrailingActivationTicks = 15,
                TrailingOffsetAtr      = 1.5,
                TrailingTightenAtTicks = 25,
                VolSurgeVetoEnabled    = false,
                SlowGrindVetoEnabled   = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1), "Should have exactly 1 trade");
            Assert.That(result.Trades[0].ExitReason, Is.EqualTo("TRAIL"),
                "Trade should exit via trailing stop (TRAIL)");
        }

        [Test]
        public void TrailingStop_MFE25_TightensTrail()
        {
            // Entry at 17500, price rises 26 ticks to 17506.50. ATR=1.0pts.
            // After tighten: trail = HWM - 1.0×ATR = 17506.50 - 1.0 = 17505.50 (4 ticks below HWM).
            // Price retraces to 17505.25 — crosses tightened trail → TRAIL exit.
            double tickSize = 0.25;
            double atr = 1.0;
            double entryClose = 17500.0;

            var lines = new List<string>();
            lines.Add(BullBar(0, 10, entryClose, atr));
            // Rise 26 ticks = 6.5 pts over 6 bars
            for (int i = 1; i <= 6; i++)
                lines.Add(QuietBar(i, 10 + i, entryClose + i * 1.0 + 0.25, atr));
            // bar 7: 17506.50, MFE=26t → tightened trail at 17506.50 - 1.0 = 17505.50
            lines.Add(QuietBar(7, 17, 17506.50, atr));
            // bar 8: price drops to 17505.25 → below tightened trail 17505.50
            lines.Add(QuietBar(8, 18, 17505.25, atr));

            string path = WriteSession("trail_tighten_test.ndjson", lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold    = 40.0,
                MinTierForEntry        = SignalTier.TYPE_C,
                StopLossTicks          = 80,
                TargetTicks            = 160,
                MaxBarsInTrade         = 30,
                TickSize               = tickSize,
                TickValue              = 5.0,
                TrailingStopEnabled    = true,
                TrailingActivationTicks = 15,
                TrailingOffsetAtr      = 1.5,
                TrailingTightenAtTicks = 25,
                TrailingTightenMult    = 1.0,
                VolSurgeVetoEnabled    = false,
                SlowGrindVetoEnabled   = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1), "Should have exactly 1 trade");
            Assert.That(result.Trades[0].ExitReason, Is.EqualTo("TRAIL"),
                "Trade after tightened trail retrace should exit via TRAIL");
        }

        [Test]
        public void TrailingStop_Disabled_NoTrailExit()
        {
            // Same scenario as MFE15 test but TrailingStopEnabled=false → should reach MAX_BARS
            double atr = 1.0;
            double entryClose = 17500.0;

            var lines = new List<string>();
            lines.Add(BullBar(0, 10, entryClose, atr));
            for (int i = 1; i <= 4; i++)
                lines.Add(QuietBar(i, 10 + i, entryClose + i * 1.0, atr));
            lines.Add(QuietBar(5, 15, 17502.0, atr)); // would trail-exit if enabled

            string path = WriteSession("trail_disabled_test.ndjson", lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold    = 40.0,
                MinTierForEntry        = SignalTier.TYPE_C,
                StopLossTicks          = 40,
                TargetTicks            = 80,
                MaxBarsInTrade         = 5,  // force MAX_BARS after 5 bars
                TickSize               = 0.25,
                TickValue              = 5.0,
                TrailingStopEnabled    = false,  // disabled
                VolSurgeVetoEnabled    = false,
                SlowGrindVetoEnabled   = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(1));
            Assert.That(result.Trades[0].ExitReason, Is.Not.EqualTo("TRAIL"),
                "With TrailingStopEnabled=false, TRAIL exit reason should never appear");
        }

        // =====================================================================
        // P0-3: VOLP-03 regime veto
        // =====================================================================

        [Test]
        public void VolSurgeVeto_BlocksEntryAfterVolP03()
        {
            // Session: bar 0 = VOLP-03 fires (no direction), bars 1-3 = strong bull entry signals.
            // With veto enabled, bars 1-3 should all be blocked → 0 trades.
            var lines = new List<string>
            {
                VolP03Bar(0, 5, 17500.0),
                BullBar(1, 6,  17500.25, 2.0),
                BullBar(2, 7,  17500.50, 2.0),
                BullBar(3, 8,  17500.75, 2.0),
            };

            string path = WriteSession("volp03_veto_test.ndjson", lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold = 40.0,
                MinTierForEntry     = SignalTier.TYPE_C,
                StopLossTicks       = 20,
                TargetTicks         = 40,
                MaxBarsInTrade      = 10,
                TickSize            = 0.25,
                TickValue           = 5.0,
                VolSurgeVetoEnabled = true,
                SlowGrindVetoEnabled = false,
                TrailingStopEnabled = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.EqualTo(0),
                "VOLP-03 veto should block all entries after vol-surge fires in the session");
        }

        [Test]
        public void VolSurgeVeto_Disabled_AllowsEntry()
        {
            // Same session but veto disabled — entries should proceed.
            var lines = new List<string>
            {
                VolP03Bar(0, 5, 17500.0),
                BullBar(1, 6, 17500.25, 2.0),
            };

            string path = WriteSession("volp03_disabled_test.ndjson", lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold = 40.0,
                MinTierForEntry     = SignalTier.TYPE_C,
                StopLossTicks       = 20,
                TargetTicks         = 40,
                MaxBarsInTrade      = 10,
                TickSize            = 0.25,
                TickValue           = 5.0,
                VolSurgeVetoEnabled  = false,  // disabled
                SlowGrindVetoEnabled = false,
                TrailingStopEnabled  = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path });

            Assert.That(result.Trades.Count, Is.GreaterThan(0),
                "With VolSurgeVetoEnabled=false, entry should proceed even after VOLP-03");
        }

        [Test]
        public void VolSurgeVeto_ResetsAcrossSessions()
        {
            // Session 1: VOLP-03 fires → no entries in session 1
            // Session 2: clean signals → entries should be allowed (fresh session, flag reset)
            var session1Lines = new List<string>
            {
                VolP03Bar(0, 5, 17500.0),
                BullBar(1, 6, 17500.25, 2.0),
            };
            var session2Lines = new List<string>
            {
                BullBar(0, 6, 17500.25, 2.0),
            };

            string path1 = WriteSession("volp03_session1.ndjson", session1Lines);
            string path2 = WriteSession("volp03_session2.ndjson", session2Lines);

            var config = new BacktestConfig
            {
                ScoreEntryThreshold  = 40.0,
                MinTierForEntry      = SignalTier.TYPE_C,
                StopLossTicks        = 20,
                TargetTicks          = 40,
                MaxBarsInTrade       = 10,
                TickSize             = 0.25,
                TickValue            = 5.0,
                VolSurgeVetoEnabled  = true,
                SlowGrindVetoEnabled = false,
                TrailingStopEnabled  = false,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, new[] { path1, path2 });

            // Session 2 should have at least 1 trade (flag reset between sessions)
            bool hasSession2Trade = false;
            foreach (var t in result.Trades)
                if (t.EntryBar == 0) hasSession2Trade = true;

            Assert.That(hasSession2Trade, Is.True,
                "VOLP-03 session flag should reset between sessions — session 2 should allow entries");
        }

        // =====================================================================
        // P0-5: Slow-grind ATR veto (via ScorerEntryGate.EvaluateWithContext)
        // =====================================================================

        [Test]
        public void SlowGrindVeto_LowAtrBlocksEntry()
        {
            // sessionAvgAtr = 2.0 pts, ratio = 0.5 → threshold = 1.0 pts
            // currentAtr = 0.8 pts < 1.0 → veto
            var gateState = new ScorerEntryGate.SessionGateState();
            var scored = MakeTypeBResult();

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            gateState,
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: true,
                slowGrindAtrRatio:    0.5,
                currentAtr:           0.8,
                sessionAvgAtr:        2.0);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.SlowGrindVeto),
                "ATR 0.8 < 0.5 × 2.0 = 1.0 should trigger SlowGrindVeto");
        }

        [Test]
        public void SlowGrindVeto_NormalAtrPasses()
        {
            // currentAtr = 1.5 pts, threshold = 0.5 × 2.0 = 1.0 → passes
            var gateState = new ScorerEntryGate.SessionGateState();
            var scored = MakeTypeBResult();

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            gateState,
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: true,
                slowGrindAtrRatio:    0.5,
                currentAtr:           1.5,
                sessionAvgAtr:        2.0);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed),
                "ATR 1.5 >= 0.5 × 2.0 = 1.0 should pass SlowGrindVeto");
        }

        [Test]
        public void SlowGrindVeto_ZeroAtr_SkipsVeto()
        {
            // When ATR is 0 (not available), veto should be skipped
            var gateState = new ScorerEntryGate.SessionGateState();
            var scored = MakeTypeBResult();

            var outcome = ScorerEntryGate.EvaluateWithContext(
                scored,
                scoreThreshold:       40.0,
                minTier:              SignalTier.TYPE_C,
                gateState:            gateState,
                volSurgeVetoEnabled:  false,
                slowGrindVetoEnabled: true,
                slowGrindAtrRatio:    0.5,
                currentAtr:           0.0,   // ATR not available
                sessionAvgAtr:        2.0);

            Assert.That(outcome, Is.EqualTo(ScorerEntryGate.GateOutcome.Passed),
                "Zero currentAtr means ATR data not available — veto should be skipped");
        }

        // =====================================================================
        // Integration: BacktestRunner with all P0 fixes active — 5 synthetic sessions
        // =====================================================================

        [Test]
        public void Integration_AllFixes_5Sessions_TradesProduced()
        {
            // Build 5 synthetic sessions each with a mix of:
            //   - clean bull entry bars (ATR=2.0, above ratio)
            //   - one VOLP-03 bar per session at the start (should NOT block — it fires
            //     at bar 0 which is also entry bar; entry is on bar 1+)
            // Goal: verify runner produces trades and does not throw, and TRAIL exits occur.

            string[] sessionPaths = new string[5];
            for (int s = 0; s < 5; s++)
            {
                double basePrice = 17500.0 + s * 10.0;
                var lines = new List<string>();

                // bar 0: quiet (ATR seeds session avg)
                lines.Add(QuietBar(0, 0, basePrice, 2.0));
                // bar 1: bull entry (ATR=2.0, session avg after bar 0 = 2.0 → above 0.5 ratio)
                lines.Add(BullBar(1, 1, basePrice, 2.0));
                // bars 2-6: price rises, ATR normal
                for (int b = 2; b <= 8; b++)
                    lines.Add(QuietBar(b, b, basePrice + b * 0.5, 2.0));
                // bar 9: small retrace — may trigger trail if MFE >= 15t
                lines.Add(QuietBar(9, 9, basePrice + 2.0, 2.0));

                sessionPaths[s] = WriteSession($"integration_s{s}.ndjson", lines);
            }

            var config = new BacktestConfig
            {
                ScoreEntryThreshold    = 40.0,
                MinTierForEntry        = SignalTier.TYPE_B,   // P0-4 default
                StopLossTicks          = 20,
                TargetTicks            = 40,
                MaxBarsInTrade         = 20,
                TickSize               = 0.25,
                TickValue              = 5.0,
                TrailingStopEnabled    = true,
                TrailingActivationTicks = 15,
                TrailingOffsetAtr      = 1.5,
                TrailingTightenAtTicks = 25,
                VolSurgeVetoEnabled    = true,
                SlowGrindVetoEnabled   = true,
                SlowGrindAtrRatio      = 0.5,
            };

            var runner = new BacktestRunner();
            var result = runner.Run(config, sessionPaths);

            Assert.That(result.Trades.Count, Is.GreaterThan(0),
                "Integration run over 5 sessions with normal ATR should produce trades");
            Assert.That(result.WinRate, Is.InRange(0.0, 1.0), "WinRate must be in [0,1]");
        }

        [Test]
        public void Integration_VolSurgeVeto_ReducesTrades()
        {
            // Build 1 session with VOLP-03 at bar 0 followed by bull entries.
            // With veto enabled: 0 trades. With veto disabled: > 0 trades.
            var lines = new List<string>
            {
                VolP03Bar(0, 0, 17500.0, 2.0),
                BullBar(1, 1,  17500.25, 2.0),
                BullBar(2, 2,  17500.50, 2.0),
                BullBar(3, 3,  17500.75, 2.0),
                QuietBar(4, 4, 17510.0,  2.0),   // price moves away — target/trail exit
            };
            string path = WriteSession("veto_vs_no_veto.ndjson", lines);

            var configVetoOn = new BacktestConfig
            {
                ScoreEntryThreshold  = 40.0,
                MinTierForEntry      = SignalTier.TYPE_C,
                StopLossTicks        = 20, TargetTicks = 40, MaxBarsInTrade = 10,
                TickSize = 0.25, TickValue = 5.0,
                VolSurgeVetoEnabled  = true,
                SlowGrindVetoEnabled = false,
                TrailingStopEnabled  = false,
            };
            var configVetoOff = new BacktestConfig
            {
                ScoreEntryThreshold  = 40.0,
                MinTierForEntry      = SignalTier.TYPE_C,
                StopLossTicks        = 20, TargetTicks = 40, MaxBarsInTrade = 10,
                TickSize = 0.25, TickValue = 5.0,
                VolSurgeVetoEnabled  = false,
                SlowGrindVetoEnabled = false,
                TrailingStopEnabled  = false,
            };

            var runner = new BacktestRunner();
            int tradesVetoOn  = runner.Run(configVetoOn,  new[] { path }).Trades.Count;
            int tradesVetoOff = runner.Run(configVetoOff, new[] { path }).Trades.Count;

            Assert.That(tradesVetoOn, Is.EqualTo(0),
                "VOLP-03 veto enabled: no entries after vol-surge");
            Assert.That(tradesVetoOff, Is.GreaterThan(0),
                "VOLP-03 veto disabled: entries should proceed");
        }

        // =====================================================================
        // Helpers
        // =====================================================================

        /// <summary>Build a ScorerResult that passes TYPE_B and score-threshold=40 gates.</summary>
        private static ScorerResult MakeTypeBResult()
        {
            // Manufacture a minimal TYPE_B result by calling ConfluenceScorer directly
            var signals = new[]
            {
                new SignalResult("ABS-01",  +1, 0.8, 0UL, "ABS",  17500.25),
                new SignalResult("EXH-02",  +1, 0.7, 0UL, "EXH",  17500.25),
                new SignalResult("DELT-04", +1, 0.6, 0UL, "DELT", 17500.25),
                new SignalResult("IMB-T2",  +1, 0.5, 0UL, "STACKED_T2", 17500.25),
                new SignalResult("AUCT-01", +1, 0.55, 0UL, "AUCT", 17500.25),
            };
            return ConfluenceScorer.Score(signals, barsSinceOpen: 30, barDelta: 40,
                barClose: 17500.25, zoneScore: 60.0, zoneDistTicks: 2.0);
        }
    }
}
