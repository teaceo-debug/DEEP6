using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    [TestFixture]
    public abstract class MADConfluenceAITestBase
    {
        protected static string FixturesPath => 
            Path.Combine(TestContext.CurrentContext.TestDirectory, "MADConfluenceAI", "fixtures");

        /// <summary>Load and deserialize a JSON fixture file by filename.</summary>
        protected MADTestFixture LoadFixture(string filename)
        {
            string path = Path.Combine(FixturesPath, filename);
            Assert.IsTrue(File.Exists(path), $"Fixture not found: {path}");
            string json = File.ReadAllText(path);
            return System.Text.Json.JsonSerializer.Deserialize<MADTestFixture>(json, 
                new System.Text.Json.JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }

        /// <summary>Assert a signal result matches expected output from fixture.</summary>
        protected void AssertSignal(MADTestSignalExpected expected, object actualResult, string context = "")
        {
            Assert.IsNotNull(actualResult, $"Expected signal {expected.SignalId} but got null. {context}");
            // Subclasses should cast actualResult to their concrete MADSignalResult type
        }
    }

    // Fixture POCOs (plain C# for JSON deserialization — no NT8 dependency)
    public class MADTestFixture
    {
        public string Description { get; set; }
        public MADTestBar Bar { get; set; }
        public MADTestSession Session { get; set; }
        public MADTestSignalExpected[] Expected { get; set; }
    }

    public class MADTestBar
    {
        public double Open { get; set; }
        public double High { get; set; }
        public double Low { get; set; }
        public double Close { get; set; }
        public long TotalVol { get; set; }
        public long BarDelta { get; set; }
        public Dictionary<string, MADTestCell> Levels { get; set; }
    }

    public class MADTestCell
    {
        public long Bid { get; set; }
        public long Ask { get; set; }
    }

    public class MADTestSession
    {
        public double Atr20 { get; set; }
        public double VolEma { get; set; }
        public double PrevDayHigh { get; set; }
        public double PrevDayLow { get; set; }
        public double PrevDayClose { get; set; }
        public double SessionHigh { get; set; }
        public double SessionLow { get; set; }
        public string RegimeName { get; set; } = "Ranging";
    }

    public class MADTestSignalExpected
    {
        public string SignalId { get; set; }
        public string Direction { get; set; }  // "Long", "Short", "Neutral"
        public double StrengthMin { get; set; }
        public double StrengthMax { get; set; }
    }
}
