// BacktestRunner: Core offline backtest engine for DEEP6.
// Replays scored-bar NDJSON sessions through ConfluenceScorer + ScorerEntryGate.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v

using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.Tests.SessionReplay;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Backtest
{
    /// <summary>
    /// Replays one or more scored-bar NDJSON session files through the
    /// ConfluenceScorer + ScorerEntryGate pipeline and simulates trade fills.
    /// </summary>
    public sealed class BacktestRunner
    {
        /// <summary>
        /// Run a backtest over the given NDJSON session files with the provided config.
        /// </summary>
        /// <param name="config">Backtest parameters.</param>
        /// <param name="ndjsonPaths">Paths to scored-bar NDJSON files.</param>
        /// <returns>BacktestResult containing all completed trades.</returns>
        public BacktestResult Run(BacktestConfig config, string[] ndjsonPaths)
        {
            var result = new BacktestResult { InitialCapital = config.InitialCapital };

            foreach (string path in ndjsonPaths)
            {
                RunSession(config, path, result);
            }

            return result;
        }

        private static void RunSession(BacktestConfig config, string ndjsonPath, BacktestResult result)
        {
            // Track open trade state
            bool   inTrade       = false;
            int    entryBarIdx   = 0;
            double entryPrice    = 0.0;
            int    tradeDir      = 0;
            string tradeSignalId = string.Empty;
            SignalTier tradeTier = SignalTier.QUIET;
            double tradeScore    = 0.0;
            string tradeNarrative = string.Empty;
            string[] tradeCats   = new string[0];

            ScoredBarRecord lastRecord = null;
            ScorerResult    lastScored = null;

            var bars = CaptureReplayLoader.LoadScoredBars(ndjsonPath);

            foreach (var rec in bars)
            {
                lastRecord = rec;

                // Score this bar
                var scored = ConfluenceScorer.Score(
                    rec.Signals,
                    rec.BarsSinceOpen,
                    rec.BarDelta,
                    rec.BarClose,
                    rec.ZoneScore,
                    rec.ZoneDistTicks,
                    config.TickSize);

                lastScored = scored;

                if (inTrade)
                {
                    // -----------------------------------------------------------------
                    // Check exits in priority order
                    // -----------------------------------------------------------------
                    string exitReason = null;

                    // 1. Stop loss
                    if (tradeDir == +1 && rec.BarClose <= entryPrice - (config.StopLossTicks * config.TickSize))
                        exitReason = "STOP_LOSS";
                    else if (tradeDir == -1 && rec.BarClose >= entryPrice + (config.StopLossTicks * config.TickSize))
                        exitReason = "STOP_LOSS";

                    // 2. Target
                    if (exitReason == null)
                    {
                        if (tradeDir == +1 && rec.BarClose >= entryPrice + (config.TargetTicks * config.TickSize))
                            exitReason = "TARGET";
                        else if (tradeDir == -1 && rec.BarClose <= entryPrice - (config.TargetTicks * config.TickSize))
                            exitReason = "TARGET";
                    }

                    // 3. Opposing signal
                    if (exitReason == null
                        && scored.Direction != 0
                        && scored.Direction != tradeDir
                        && scored.TotalScore >= config.ExitOnOpposingScore)
                    {
                        exitReason = "OPPOSING_SIGNAL";
                    }

                    // 4. Max bars
                    if (exitReason == null && (rec.BarIdx - entryBarIdx) >= config.MaxBarsInTrade)
                        exitReason = "MAX_BARS";

                    if (exitReason != null)
                    {
                        AddTrade(result, config, entryBarIdx, rec.BarIdx, entryPrice, rec.BarClose,
                            tradeDir, exitReason, tradeSignalId, tradeTier, tradeScore, tradeNarrative, tradeCats);
                        inTrade = false;
                    }
                }
                else
                {
                    // -----------------------------------------------------------------
                    // Check entry gate
                    // -----------------------------------------------------------------
                    var gate = ScorerEntryGate.Evaluate(scored, config.ScoreEntryThreshold, config.MinTierForEntry);
                    if (gate == ScorerEntryGate.GateOutcome.Passed)
                    {
                        // Apply entry slippage (buys higher, shorts sell lower)
                        entryPrice = scored.EntryPrice + (scored.Direction * config.SlippageTicks * config.TickSize);
                        entryBarIdx   = rec.BarIdx;
                        tradeDir      = scored.Direction;
                        tradeTier     = scored.Tier;
                        tradeScore    = scored.TotalScore;
                        tradeNarrative = scored.Narrative ?? string.Empty;
                        tradeCats     = scored.CategoriesFiring ?? new string[0];
                        tradeSignalId = ExtractDominantSignalId(scored.CategoriesFiring);
                        inTrade       = true;
                    }
                }
            }

            // Session-end force-exit
            if (inTrade && lastRecord != null)
            {
                AddTrade(result, config, entryBarIdx, lastRecord.BarIdx, entryPrice, lastRecord.BarClose,
                    tradeDir, "SESSION_END", tradeSignalId, tradeTier, tradeScore, tradeNarrative, tradeCats);
            }
        }

        private static void AddTrade(
            BacktestResult result,
            BacktestConfig config,
            int entryBarIdx,
            int exitBarIdx,
            double entryPrice,
            double exitBarClose,
            int direction,
            string exitReason,
            string signalId,
            SignalTier tier,
            double score,
            string narrative,
            string[] cats)
        {
            // Exit slippage is adverse (against us): longs exit lower, shorts exit higher
            double exitPrice = exitBarClose + (direction * config.SlippageTicks * config.TickSize * -1.0);

            double pnlTicks   = (exitPrice - entryPrice) / config.TickSize * direction;
            double pnlDollars = pnlTicks * config.TickValue * config.ContractsPerTrade;
            int    duration   = System.Math.Max(exitBarIdx - entryBarIdx, 1);

            result.Trades.Add(new Trade
            {
                EntryBar       = entryBarIdx,
                ExitBar        = exitBarIdx,
                EntryPrice     = entryPrice,
                ExitPrice      = exitPrice,
                Direction      = direction,
                PnlTicks       = pnlTicks,
                PnlDollars     = pnlDollars,
                SignalId       = signalId,
                Tier           = tier,
                Score          = score,
                Narrative      = narrative,
                ExitReason     = exitReason,
                DurationBars   = duration,
                CategoriesFiring = cats,
            });
        }

        private static string ExtractDominantSignalId(string[] cats)
        {
            if (cats == null || cats.Length == 0) return "MIXED";
            foreach (var c in cats)
            {
                if (c == "absorption") return "ABS";
                if (c == "exhaustion") return "EXH";
            }
            return "MIXED";
        }
    }
}
