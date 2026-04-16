// CsvTradeExporterTests: NUnit tests for CsvTradeExporter.
// Phase quick-260415-u6v

using System.IO;
using System.Linq;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Backtest
{
    [TestFixture]
    public class CsvTradeExporterTests
    {
        private string _tempFile;

        [SetUp]
        public void SetUp()
        {
            _tempFile = Path.Combine(Path.GetTempPath(), "csv_test_" + Path.GetRandomFileName() + ".csv");
        }

        [TearDown]
        public void TearDown()
        {
            if (File.Exists(_tempFile)) File.Delete(_tempFile);
        }

        private static BacktestResult MakeResult(int tradeCount = 2)
        {
            var result = new BacktestResult { InitialCapital = 50000.0 };
            for (int i = 0; i < tradeCount; i++)
            {
                result.Trades.Add(new Trade
                {
                    EntryBar        = i * 2,
                    ExitBar         = i * 2 + 1,
                    EntryPrice      = 17500.0 + i * 10,
                    ExitPrice       = 17510.0 + i * 10,
                    Direction       = 1,
                    PnlTicks        = 40.0,
                    PnlDollars      = 200.0,
                    SignalId        = "ABS",
                    Tier            = SignalTier.TYPE_A,
                    Score           = 85.5,
                    Narrative       = "Bull absorption at support",
                    ExitReason      = "TARGET",
                    DurationBars    = 1,
                    CategoriesFiring = new[] { "absorption", "delta" },
                });
            }
            return result;
        }

        [Test]
        public void Export_WritesHeaderRow()
        {
            CsvTradeExporter.Export(MakeResult(), _tempFile);
            string[] lines = File.ReadAllLines(_tempFile);

            Assert.GreaterOrEqual(lines.Length, 1, "CSV must have at least a header row.");
            Assert.AreEqual(
                "EntryBar,ExitBar,EntryPrice,ExitPrice,Direction,PnlTicks,PnlDollars,SignalId,Tier,Score,Narrative,ExitReason,DurationBars,CategoriesFiring",
                lines[0],
                "Header row should match expected column names.");
        }

        [Test]
        public void Export_WritesCorrectColumnCount()
        {
            CsvTradeExporter.Export(MakeResult(3), _tempFile);
            string[] lines = File.ReadAllLines(_tempFile);

            // Header + 3 data rows
            Assert.AreEqual(4, lines.Length, "Should have header + 3 data rows.");

            // Each data row should have 14 fields when split by comma
            // NOTE: CategoriesFiring uses | delimiter, Narrative may be quoted
            for (int i = 1; i < lines.Length; i++)
            {
                // Simple check: count commas outside quotes
                int commas = CountCommasOutsideQuotes(lines[i]);
                Assert.AreEqual(13, commas, $"Row {i} should have 13 commas (14 fields). Line: {lines[i]}");
            }
        }

        [Test]
        public void Export_RoundTrip_ParseableByPython()
        {
            // Write CSV with a narrative that contains commas (tests quoting)
            var result = new BacktestResult { InitialCapital = 50000.0 };
            result.Trades.Add(new Trade
            {
                EntryBar        = 5,
                ExitBar         = 8,
                EntryPrice      = 17500.25,
                ExitPrice       = 17510.75,
                Direction       = 1,
                PnlTicks        = 42.0,
                PnlDollars      = 210.0,
                SignalId        = "ABS",
                Tier            = SignalTier.TYPE_B,
                Score           = 75.0,
                Narrative       = "Test narrative, with comma, and more",
                ExitReason      = "TARGET",
                DurationBars    = 3,
                CategoriesFiring = new[] { "absorption", "delta", "imbalance" },
            });

            CsvTradeExporter.Export(result, _tempFile);
            string[] lines = File.ReadAllLines(_tempFile);

            Assert.AreEqual(2, lines.Length, "Should have header + 1 data row.");

            // Parse header
            string[] headers = lines[0].Split(',');
            Assert.AreEqual(14, headers.Length, "Should have 14 header columns.");

            // Verify specific numeric fields parseable with InvariantCulture
            // Manually parse the non-quoted fields
            // Fields: EntryBar(0),ExitBar(1),EntryPrice(2),ExitPrice(3),...
            // The data row line[1] — find EntryBar=5
            StringAssert.Contains("5,8", lines[1], "EntryBar=5 and ExitBar=8 should appear in data row.");
            StringAssert.Contains("17500.25", lines[1], "EntryPrice should appear in InvariantCulture format.");
            StringAssert.Contains("17510.75", lines[1], "ExitPrice should appear in data row.");
            StringAssert.Contains("absorption|delta|imbalance", lines[1], "CategoriesFiring should be pipe-delimited.");

            // Narrative with commas should be quoted
            StringAssert.Contains("\"Test narrative, with comma, and more\"", lines[1],
                "Narrative containing commas must be double-quoted.");
        }

        // ------------------------------------------------------------------
        // Helper: count commas not inside double-quoted fields
        // ------------------------------------------------------------------
        private static int CountCommasOutsideQuotes(string line)
        {
            int count = 0;
            bool inQuote = false;
            for (int i = 0; i < line.Length; i++)
            {
                char c = line[i];
                if (c == '"')
                {
                    // Handle doubled-quote escape ""
                    if (inQuote && i + 1 < line.Length && line[i + 1] == '"')
                    { i++; continue; }
                    inQuote = !inQuote;
                }
                else if (c == ',' && !inQuote)
                {
                    count++;
                }
            }
            return count;
        }
    }
}
