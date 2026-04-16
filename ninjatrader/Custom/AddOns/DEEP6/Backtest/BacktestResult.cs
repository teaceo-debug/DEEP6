// BacktestResult: Aggregated result from a BacktestRunner run.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v

using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest
{
    /// <summary>
    /// Aggregated backtest output. Computed properties derive summary stats from Trades list.
    /// </summary>
    public sealed class BacktestResult
    {
        /// <summary>All completed trades from the backtest run.</summary>
        public List<Trade> Trades { get; } = new List<Trade>();

        /// <summary>Initial capital used for equity curve reference.</summary>
        public double InitialCapital { get; set; }

        // -------------------------------------------------------------------------
        // Computed summary properties
        // -------------------------------------------------------------------------

        /// <summary>Total number of trades.</summary>
        public int TotalTrades => Trades.Count;

        /// <summary>Win rate: fraction of trades with PnlTicks > 0.</summary>
        public double WinRate
        {
            get
            {
                if (Trades.Count == 0) return 0.0;
                int wins = 0;
                foreach (var t in Trades) if (t.PnlTicks > 0) wins++;
                return (double)wins / Trades.Count;
            }
        }

        /// <summary>Average winning trade in ticks.</summary>
        public double AvgWinTicks
        {
            get
            {
                double sum = 0.0;
                int count = 0;
                foreach (var t in Trades) { if (t.PnlTicks > 0) { sum += t.PnlTicks; count++; } }
                return count > 0 ? sum / count : 0.0;
            }
        }

        /// <summary>Average losing trade in ticks (returned as a positive number).</summary>
        public double AvgLossTicks
        {
            get
            {
                double sum = 0.0;
                int count = 0;
                foreach (var t in Trades) { if (t.PnlTicks < 0) { sum += t.PnlTicks; count++; } }
                return count > 0 ? -sum / count : 0.0;
            }
        }

        /// <summary>Profit factor: gross wins / abs(gross losses). 0 if no losses.</summary>
        public double ProfitFactor
        {
            get
            {
                double grossWin = 0.0, grossLoss = 0.0;
                foreach (var t in Trades)
                {
                    if (t.PnlTicks > 0) grossWin  += t.PnlTicks;
                    else                grossLoss  += t.PnlTicks;
                }
                if (grossLoss == 0.0) return grossWin > 0 ? double.PositiveInfinity : 0.0;
                return grossWin / System.Math.Abs(grossLoss);
            }
        }

        /// <summary>Maximum peak-to-trough drawdown in cumulative tick PnL.</summary>
        public double MaxDrawdownTicks
        {
            get
            {
                if (Trades.Count == 0) return 0.0;
                double peak = 0.0, cumPnl = 0.0, maxDD = 0.0;
                foreach (var t in Trades)
                {
                    cumPnl += t.PnlTicks;
                    if (cumPnl > peak) peak = cumPnl;
                    double dd = peak - cumPnl;
                    if (dd > maxDD) maxDD = dd;
                }
                return maxDD;
            }
        }

        /// <summary>Maximum number of consecutive losing trades.</summary>
        public int MaxConsecutiveLosses
        {
            get
            {
                int maxRun = 0, curRun = 0;
                foreach (var t in Trades)
                {
                    if (t.PnlTicks <= 0) { curRun++; if (curRun > maxRun) maxRun = curRun; }
                    else curRun = 0;
                }
                return maxRun;
            }
        }

        /// <summary>
        /// Sharpe estimate: mean(PnlTicks) / stddev(PnlTicks) * sqrt(252).
        /// Returns 0 if fewer than 2 trades.
        /// </summary>
        public double SharpeEstimate
        {
            get
            {
                if (Trades.Count < 2) return 0.0;
                double sum = 0.0;
                foreach (var t in Trades) sum += t.PnlTicks;
                double mean = sum / Trades.Count;
                double varSum = 0.0;
                foreach (var t in Trades) { double d = t.PnlTicks - mean; varSum += d * d; }
                double stddev = System.Math.Sqrt(varSum / (Trades.Count - 1));
                if (stddev == 0.0) return 0.0;
                return (mean / stddev) * System.Math.Sqrt(252.0);
            }
        }

        /// <summary>Net P&amp;L in dollars across all trades.</summary>
        public double NetPnlDollars
        {
            get
            {
                double sum = 0.0;
                foreach (var t in Trades) sum += t.PnlDollars;
                return sum;
            }
        }
    }
}
