// Trade: Represents a single completed trade from the backtest engine.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v

using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest
{
    /// <summary>
    /// A single completed trade produced by BacktestRunner.
    /// All fields are public for CSV serialization compatibility.
    /// </summary>
    public sealed class Trade
    {
        /// <summary>Bar index at entry.</summary>
        public int EntryBar;

        /// <summary>Bar index at exit.</summary>
        public int ExitBar;

        /// <summary>Entry fill price (includes slippage).</summary>
        public double EntryPrice;

        /// <summary>Exit fill price (includes slippage).</summary>
        public double ExitPrice;

        /// <summary>Trade direction: +1 = long, -1 = short.</summary>
        public int Direction;

        /// <summary>Profit/loss in ticks (positive = win).</summary>
        public double PnlTicks;

        /// <summary>Profit/loss in dollars (positive = win).</summary>
        public double PnlDollars;

        /// <summary>Dominant ABS/EXH signal ID from ScorerResult, or "MIXED".</summary>
        public string SignalId;

        /// <summary>Signal tier at entry.</summary>
        public SignalTier Tier;

        /// <summary>TotalScore at entry.</summary>
        public double Score;

        /// <summary>Narrative string from ScorerResult at entry.</summary>
        public string Narrative;

        /// <summary>Exit reason: OPPOSING_SIGNAL, STOP_LOSS, TARGET, MAX_BARS, or SESSION_END.</summary>
        public string ExitReason;

        /// <summary>Trade duration in bars (ExitBar - EntryBar).</summary>
        public int DurationBars;

        /// <summary>Categories firing at entry from ScorerResult.</summary>
        public string[] CategoriesFiring;
    }
}
