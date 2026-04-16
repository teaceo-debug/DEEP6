// BacktestConfig: Configuration for the offline backtest engine.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v

using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest
{
    /// <summary>
    /// Configuration record for BacktestRunner. All public fields with sensible NQ defaults.
    /// </summary>
    public sealed class BacktestConfig
    {
        /// <summary>Slippage in ticks applied at entry and exit (against us).</summary>
        public double SlippageTicks = 1.0;

        /// <summary>Stop-loss distance in ticks from entry price.</summary>
        public int StopLossTicks = 20;

        /// <summary>Profit target distance in ticks from entry price.</summary>
        public int TargetTicks = 40;

        /// <summary>Maximum bars to hold a position before forced exit.</summary>
        public int MaxBarsInTrade = 30;

        /// <summary>Opposing-direction score threshold that triggers an early exit.</summary>
        public double ExitOnOpposingScore = 0.50;

        /// <summary>Minimum TotalScore required to enter a trade.</summary>
        public double ScoreEntryThreshold = 80.0;

        /// <summary>Minimum signal tier required to enter a trade.</summary>
        public SignalTier MinTierForEntry = SignalTier.TYPE_A;

        /// <summary>Dollar value per tick for the instrument (NQ = $5/tick).</summary>
        public double TickValue = 5.0;

        /// <summary>Tick size for the instrument (NQ = 0.25 pts).</summary>
        public double TickSize = 0.25;

        /// <summary>Starting capital for equity curve calculation.</summary>
        public double InitialCapital = 50000.0;

        /// <summary>Number of contracts per trade.</summary>
        public int ContractsPerTrade = 1;
    }
}
