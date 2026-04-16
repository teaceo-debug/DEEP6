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

        /// <summary>Minimum TotalScore required to enter a trade. R1: raised to 70 (round1 meta-optimization walk-forward optimum).</summary>
        public double ScoreEntryThreshold = 70.0;

        /// <summary>Minimum signal tier required to enter a trade. P0-4: TYPE_B default (was TYPE_A).</summary>
        public SignalTier MinTierForEntry = SignalTier.TYPE_B;

        /// <summary>Dollar value per tick for the instrument (NQ = $5/tick).</summary>
        public double TickValue = 5.0;

        /// <summary>Tick size for the instrument (NQ = 0.25 pts).</summary>
        public double TickSize = 0.25;

        /// <summary>Starting capital for equity curve calculation.</summary>
        public double InitialCapital = 50000.0;

        /// <summary>Number of contracts per trade.</summary>
        public int ContractsPerTrade = 1;

        // ---- R1: Breakeven stop ----

        /// <summary>Enable breakeven stop. When MFE reaches BreakevenActivationTicks, stop moves to entry + BreakevenOffsetTicks.</summary>
        public bool BreakevenEnabled = true;

        /// <summary>MFE (in ticks) at which the stop is moved to breakeven. Default 10.</summary>
        public int BreakevenActivationTicks = 10;

        /// <summary>Offset in ticks above entry to place the breakeven stop (absorbs 1-tick slippage). Default 2.</summary>
        public int BreakevenOffsetTicks = 2;

        // ---- R1: Scale-out (partial exit) ----

        /// <summary>Enable scale-out: exit ScaleOutPercent of position at ScaleOutTargetTicks; hold remainder to TargetTicks.</summary>
        public bool ScaleOutEnabled = true;

        /// <summary>Fraction of position to exit at T1 partial target. Default 0.5 (50%).</summary>
        public double ScaleOutPercent = 0.5;

        /// <summary>First target in ticks for the partial exit. Default 16.</summary>
        public int ScaleOutTargetTicks = 16;

        // ---- P0-2: ATR-trailing stop ----

        /// <summary>Enable ATR-trailing stop. When true, a trailing stop activates once MFE reaches TrailingActivationTicks.
        /// R1 default: false (trailing hurts per meta-optimizer — trailing_stop=False mean_sharpe=35.382 vs True=23.339).</summary>
        public bool TrailingStopEnabled = false;

        /// <summary>Activate trailing stop when MFE (max favorable excursion) reaches this many ticks.</summary>
        public int TrailingActivationTicks = 15;

        /// <summary>Trail offset = ATR × this multiplier. E.g. 1.5 = trail at 1.5×ATR behind the high-water mark.</summary>
        public double TrailingOffsetAtr = 1.5;

        /// <summary>Tighten trail to TrailingTightenMult×ATR once MFE reaches this many ticks.</summary>
        public int TrailingTightenAtTicks = 25;

        /// <summary>ATR multiplier after tightening (applied when MFE >= TrailingTightenAtTicks).</summary>
        public double TrailingTightenMult = 1.0;

        // ---- R1: Time-of-day blackout window ----

        /// <summary>
        /// R1: Start of the time-of-day blackout window expressed as HHMM integer (e.g. 1530 = 15:30 ET).
        /// Entries whose bar timestamp falls within [BlackoutWindowStart, BlackoutWindowEnd] are vetoed.
        /// Default 1530. Set BlackoutWindowEnd &lt; BlackoutWindowStart to disable.
        /// Source: ENTRY-TIMING.md — 1530-1600 is worst 30-min window (25.31t avg vs 39.17t peak).
        /// </summary>
        public int BlackoutWindowStart = 1530;

        /// <summary>
        /// R1: End of the time-of-day blackout window expressed as HHMM integer (e.g. 1600 = 16:00 ET).
        /// Inclusive. Default 1600.
        /// </summary>
        public int BlackoutWindowEnd = 1600;

        // ---- R1: Strict directional agreement filter ----

        /// <summary>
        /// R1: When true, any signal on the entry bar that opposes the dominant direction vetoes the entry.
        /// Source: SIGNAL-FILTER.md section 5 — delta Sharpe +19.601 for strict mode.
        /// </summary>
        public bool StrictDirectionEnabled = true;

        // ---- P0-3: VOLP-03 volume-surge regime veto ----

        /// <summary>When true, block all entries in any session where VOLP-03 has fired on any bar so far.</summary>
        public bool VolSurgeVetoEnabled = true;

        // ---- P0-5: Slow-grind ATR veto ----

        /// <summary>When true, block entries when current ATR is below SlowGrindAtrRatio × session average ATR.</summary>
        public bool SlowGrindVetoEnabled = true;

        /// <summary>
        /// If current bar ATR &lt; this ratio × session-average ATR, the bar is considered a slow grind and entry is blocked.
        /// Default 0.5 — blocks when ATR falls below 50% of session average.
        /// </summary>
        public double SlowGrindAtrRatio = 0.5;
    }
}
