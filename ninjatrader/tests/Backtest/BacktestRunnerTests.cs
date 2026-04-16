// BacktestRunnerTests: NUnit tests for BacktestRunner and BacktestResult.
// Phase quick-260415-u6v

using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Backtest
{
    [TestFixture]
    public class BacktestRunnerTests
    {
        private string _tempDir;
        private List<string> _tempFiles;

        [SetUp]
        public void SetUp()
        {
            _tempDir  = Path.Combine(Path.GetTempPath(), "bt_tests_" + Path.GetRandomFileName());
            Directory.CreateDirectory(_tempDir);
            _tempFiles = new List<string>();
        }

        [TearDown]
        public void TearDown()
        {
            foreach (var f in _tempFiles)
                if (File.Exists(f)) File.Delete(f);
            if (Directory.Exists(_tempDir))
                Directory.Delete(_tempDir, true);
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        /// <summary>Write an NDJSON file and register for cleanup.</summary>
        private string WriteNdjson(string name, IEnumerable<string> lines)
        {
            string path = Path.Combine(_tempDir, name);
            File.WriteAllLines(path, lines);
            _tempFiles.Add(path);
            return path;
        }

        /// <summary>Build a scored_bar JSON line with strong bull signals.</summary>
        private static string BullBar(int barIdx, int barsSinceOpen, double barClose,
            double zoneScore = 60.0, double zoneDistTicks = 2.0, long barDelta = 35)
        {
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":{barDelta},\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneScore\":{zoneScore.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneDistTicks\":{zoneDistTicks.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                "\"signals\":[" +
                "{\"signalId\":\"ABS-01\",\"direction\":1,\"strength\":0.8,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"ABS\"}," +
                "{\"signalId\":\"EXH-02\",\"direction\":1,\"strength\":0.7,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"EXH\"}," +
                "{\"signalId\":\"DELT-04\",\"direction\":1,\"strength\":0.6,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"DELT\"}," +
                "{\"signalId\":\"IMB-T2\",\"direction\":1,\"strength\":0.5,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"STACKED_T2\"}," +
                "{\"signalId\":\"AUCT-01\",\"direction\":1,\"strength\":0.55,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"AUCT\"}" +
                "]}";
        }

        /// <summary>Build a scored_bar JSON line with strong bear signals.</summary>
        private static string BearBar(int barIdx, int barsSinceOpen, double barClose,
            double zoneScore = 60.0, double zoneDistTicks = 2.0, long barDelta = -35)
        {
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":{barDelta},\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneScore\":{zoneScore.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                $"\"zoneDistTicks\":{zoneDistTicks.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                "\"signals\":[" +
                "{\"signalId\":\"ABS-01\",\"direction\":-1,\"strength\":0.8,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"ABS\"}," +
                "{\"signalId\":\"EXH-02\",\"direction\":-1,\"strength\":0.7,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"EXH\"}," +
                "{\"signalId\":\"DELT-04\",\"direction\":-1,\"strength\":0.6,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"DELT\"}," +
                "{\"signalId\":\"IMB-T2\",\"direction\":-1,\"strength\":0.5,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"STACKED_T2\"}," +
                "{\"signalId\":\"AUCT-01\",\"direction\":-1,\"strength\":0.55,\"price\":" + barClose.ToString(System.Globalization.CultureInfo.InvariantCulture) + ",\"detail\":\"AUCT\"}" +
                "]}";
        }

        /// <summary>Build a neutral (no-signal) bar line.</summary>
        private static string NeutralBar(int barIdx, int barsSinceOpen, double barClose)
        {
            return
                $"{{\"type\":\"scored_bar\",\"barIdx\":{barIdx},\"barsSinceOpen\":{barsSinceOpen}," +
                $"\"barDelta\":0,\"barClose\":{barClose.ToString(System.Globalization.CultureInfo.InvariantCulture)}," +
                "\"zoneScore\":0.0,\"zoneDistTicks\":999.0,\"signals\":[]}}";
        }

        private static BacktestConfig DefaultConfig() => new BacktestConfig
        {
            SlippageTicks       = 1.0,
            StopLossTicks       = 20,
            TargetTicks         = 40,
            MaxBarsInTrade      = 30,
            ExitOnOpposingScore = 0.50,
            ScoreEntryThreshold = 80.0,
            MinTierForEntry     = SignalTier.TYPE_A,
            TickSize            = 0.25,
            TickValue           = 5.0,
            InitialCapital      = 50000.0,
            ContractsPerTrade   = 1,
        };

        // ------------------------------------------------------------------
        // Tests
        // ------------------------------------------------------------------

        [Test]
        public void Run_EmptySession_ReturnsZeroTrades()
        {
            string path = WriteNdjson("empty.ndjson", new[] { "" });
            var result = new BacktestRunner().Run(DefaultConfig(), new[] { path });
            Assert.AreEqual(0, result.TotalTrades, "Empty session should produce zero trades.");
        }

        [Test]
        public void Run_SingleEntrySignal_CreatesOneTrade()
        {
            // Bar 0: strong bull entry (zoneScore=60 enables zone bonus for TypeA)
            // Bar 1: neutral — no exit trigger, session end forces exit
            string path = WriteNdjson("single_entry.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17500.25),
            });
            var result = new BacktestRunner().Run(DefaultConfig(), new[] { path });
            Assert.AreEqual(1, result.TotalTrades, "Should have exactly 1 trade.");
            Assert.AreEqual("SESSION_END", result.Trades[0].ExitReason);
        }

        [Test]
        public void Run_StopLossHit_ExitsAtStopWithCorrectPnl()
        {
            // Bar 0: bull entry at 17500.0 + 1 tick slippage = 17500.25
            // Bar 1: price drops to 17500.25 - (20 * 0.25) - 0.25 = 17495.0 → below SL
            double entryBarClose = 17500.0;
            double stopBarClose  = entryBarClose - (20 * 0.25) - 0.25; // below stop

            string path = WriteNdjson("sl_test.ndjson", new[]
            {
                BullBar(0, 0, entryBarClose),
                NeutralBar(1, 1, stopBarClose),
            });

            var config = DefaultConfig();
            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades, "Should have 1 trade.");
            var trade = result.Trades[0];
            Assert.AreEqual("STOP_LOSS", trade.ExitReason, "Should exit via stop loss.");
            Assert.Less(trade.PnlTicks, 0.0, "Stop loss should be a losing trade.");
        }

        [Test]
        public void Run_TargetHit_ExitsAtTargetWithCorrectPnl()
        {
            // Bar 0: bull entry; Bar 1: price rises to entry + (40 * 0.25) + 0.25 → above target
            double entryBarClose = 17500.0;
            double targetBarClose = entryBarClose + (40 * 0.25) + 0.25;

            string path = WriteNdjson("target_test.ndjson", new[]
            {
                BullBar(0, 0, entryBarClose),
                NeutralBar(1, 1, targetBarClose),
            });

            var config = DefaultConfig();
            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            var trade = result.Trades[0];
            Assert.AreEqual("TARGET", trade.ExitReason, "Should exit via target.");
            Assert.Greater(trade.PnlTicks, 0.0, "Target hit should be a winning trade.");
        }

        [Test]
        public void Run_OpposingSignal_ExitsOnOpposingScore()
        {
            // Bar 0: bull entry; Bar 1: strong bear signal → opposing exit
            string path = WriteNdjson("opposing_test.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                BearBar(1, 1, 17500.5),
            });

            var config = DefaultConfig();
            // Lower ExitOnOpposingScore so bear bar triggers it
            config.ExitOnOpposingScore = 0.1;

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            Assert.AreEqual("OPPOSING_SIGNAL", result.Trades[0].ExitReason,
                "Should exit on opposing signal.");
        }

        [Test]
        public void Run_MaxBarsTimeout_ExitsAfterMaxBars()
        {
            // MaxBarsInTrade=2 → entry at bar 0, neutral bars follow, exit at bar 2
            var config = DefaultConfig();
            config.MaxBarsInTrade = 2;

            string path = WriteNdjson("maxbars_test.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17500.0),
                NeutralBar(2, 2, 17500.0),
                NeutralBar(3, 3, 17500.0),
            });

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            Assert.AreEqual("MAX_BARS", result.Trades[0].ExitReason,
                "Should exit at max bars timeout.");
        }

        [Test]
        public void Run_SlippageApplied_EntryPriceAdjusted()
        {
            // Long entry: slippage pushes entry price UP by 1 tick
            var config = DefaultConfig();
            config.SlippageTicks = 2.0;

            string path = WriteNdjson("slip_entry.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17500.0),
            });

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            // ABS-01 price = 17500.0 → entry = 17500.0 + (1 * 2 * 0.25) = 17500.50
            Assert.AreEqual(17500.50, result.Trades[0].EntryPrice, 0.001,
                "Entry price should include 2-tick long slippage.");
        }

        [Test]
        public void Run_SlippageApplied_ExitPriceAdjusted()
        {
            // Long exit: slippage pushes exit price DOWN by 1 tick (adverse)
            var config = DefaultConfig();
            config.SlippageTicks = 1.0;

            string path = WriteNdjson("slip_exit.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17500.0),
            });

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            // Exit at bar close 17500.0; long exit slippage = -1 * 0.25 = -0.25 → 17499.75
            Assert.AreEqual(17499.75, result.Trades[0].ExitPrice, 0.001,
                "Long exit price should be lower than bar close by 1 tick.");
        }

        [Test]
        public void Run_ShortTrade_CorrectPnlCalculation()
        {
            // Short entry at bar 0; price rises (loss for short) → SESSION_END exit
            var config = DefaultConfig();

            string path = WriteNdjson("short_test.ndjson", new[]
            {
                BearBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17510.0), // price rises — bad for short
            });

            var result = new BacktestRunner().Run(config, new[] { path });

            Assert.AreEqual(1, result.TotalTrades);
            var trade = result.Trades[0];
            Assert.AreEqual(-1, trade.Direction, "Should be a short trade.");
            // Short entry: entry = 17500.0 + (-1 * 1 * 0.25) = 17499.75
            Assert.Less(trade.PnlTicks, 0.0, "Short losing trade should have negative PnlTicks.");
        }

        [Test]
        public void Run_MultipleSessionFiles_AggregatesTrades()
        {
            string path1 = WriteNdjson("session_a.ndjson", new[]
            {
                BullBar(0, 0, 17500.0),
                NeutralBar(1, 1, 17500.0),
            });
            string path2 = WriteNdjson("session_b.ndjson", new[]
            {
                BullBar(0, 0, 17600.0),
                NeutralBar(1, 1, 17600.0),
            });

            var result = new BacktestRunner().Run(DefaultConfig(), new[] { path1, path2 });

            Assert.AreEqual(2, result.TotalTrades, "Should aggregate trades from both sessions.");
        }

        [Test]
        public void Run_BacktestResult_SummaryStats_Correct()
        {
            // Manually construct a known-good BacktestResult and verify computed properties.
            var result = new BacktestResult { InitialCapital = 50000.0 };

            // 3 wins of +10 ticks each
            for (int i = 0; i < 3; i++)
                result.Trades.Add(new Trade { PnlTicks = 10.0, PnlDollars = 50.0, ExitReason = "TARGET", DurationBars = 1 });

            // 2 losses of -5 ticks each
            for (int i = 0; i < 2; i++)
                result.Trades.Add(new Trade { PnlTicks = -5.0, PnlDollars = -25.0, ExitReason = "STOP_LOSS", DurationBars = 1 });

            Assert.AreEqual(5, result.TotalTrades);
            Assert.AreEqual(0.6, result.WinRate, 1e-9, "WinRate should be 3/5 = 0.6");
            Assert.AreEqual(10.0, result.AvgWinTicks, 1e-9);
            Assert.AreEqual(5.0, result.AvgLossTicks, 1e-9, "AvgLossTicks returned as positive value");
            // ProfitFactor = 30 / 10 = 3.0
            Assert.AreEqual(3.0, result.ProfitFactor, 1e-9);
            Assert.AreEqual(2, result.MaxConsecutiveLosses, "2 losses appended at end = max run of 2");
            Assert.GreaterOrEqual(result.SharpeEstimate, 0.0, "Sharpe should be non-negative for net-positive trades");
        }

        [Test]
        public void Run_Session01Fixture_ProducesNonZeroTrades()
        {
            string testDir  = TestContext.CurrentContext.TestDirectory;
            string fixtures = Path.Combine(testDir, "fixtures", "scoring", "sessions");
            string session1 = Path.Combine(fixtures, "scoring-session-01.ndjson");

            // Lower thresholds so real sessions (which may not have TypeA bars) still fire trades
            var config = DefaultConfig();
            config.ScoreEntryThreshold = 40.0;
            config.MinTierForEntry     = SignalTier.TYPE_C;

            var result = new BacktestRunner().Run(config, new[] { session1 });

            Assert.Greater(result.TotalTrades, 0, "Expected at least 1 trade from session-01 fixture.");

            // All trades must have valid ExitReason
            foreach (var t in result.Trades)
            {
                Assert.IsNotEmpty(t.ExitReason, "Trade ExitReason should not be empty.");
                StringAssert.IsMatch("OPPOSING_SIGNAL|STOP_LOSS|TARGET|MAX_BARS|SESSION_END",
                    t.ExitReason, $"Unexpected ExitReason: {t.ExitReason}");
            }
        }
    }
}
