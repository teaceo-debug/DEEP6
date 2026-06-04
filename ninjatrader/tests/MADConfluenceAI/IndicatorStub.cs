// Minimal stub so MADConfluenceAI.Scoring.cs compiles in the test project.
// The partial class MADConfluenceAI : Indicator needs this base type to exist.
// Only MADMarketState and the enums are actually tested — this is just a compile shim.
//
// Also stubs types from Data.cs and MADConfluenceAI.cs that Scoring.cs references
// but which cannot be compiled here due to NT8 dependency in the partial class.

namespace NinjaTrader.NinjaScript.Indicators
{
    public class Indicator { }
}

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    // Stub: MADSignalDirection (defined in MADConfluenceAI.Data.cs)
    public enum MADSignalDirection { Long, Short, Neutral }

    // Stub: MADSignalResult (defined in MADConfluenceAI.Data.cs)
    public sealed class MADSignalResult
    {
        public string SignalId;
        public MADSignalDirection Direction;
        public double Strength;
        public string Detail;
        public double Price;
    }

    // Stub: MADConfig (defined in MADConfluenceAI.cs)
    public struct MADConfig
    {
        public double AbsorptionWeight;
        public double ExhaustionWeight;
        public double DeltaWeight;
        public double ImbalanceWeight;
        public double IcebergWeight;
        public double LiquidityWeight;
        public double TrapWeight;
        public double MinConfidenceScore;
        public double EliteThreshold;
        public double HighThreshold;
        public double AbsorptionVolumeMultiplier;
        public double ImbalanceRatio;
        public int SweepReversalSeconds;
        public double ExhaustionDeltaDecay;
        public int TrapFailureSeconds;
        public int OpeningRangeMinutes;
        public int WarmupBars;
        public int DefaultStopTicks;
        public int DefaultTargetTicks;
        public double MaxRiskRewardRatio;

        public static MADConfig Defaults => new MADConfig
        {
            AbsorptionWeight = 1.0, ExhaustionWeight = 1.0, DeltaWeight = 1.0,
            ImbalanceWeight = 1.0, IcebergWeight = 1.0, LiquidityWeight = 1.0, TrapWeight = 1.0,
            MinConfidenceScore = 60, EliteThreshold = 90, HighThreshold = 75,
            AbsorptionVolumeMultiplier = 3.0, ImbalanceRatio = 3.0,
            SweepReversalSeconds = 15, ExhaustionDeltaDecay = 0.7, TrapFailureSeconds = 30,
            OpeningRangeMinutes = 30, WarmupBars = 50,
            DefaultStopTicks = 20, DefaultTargetTicks = 40, MaxRiskRewardRatio = 5.0
        };
    }
}
