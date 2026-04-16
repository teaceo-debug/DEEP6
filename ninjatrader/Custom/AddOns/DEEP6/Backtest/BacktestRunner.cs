// BacktestRunner: Core offline backtest engine for DEEP6.
// Replays scored-bar NDJSON sessions through ConfluenceScorer + ScorerEntryGate.
// NT8-API-free — no NinjaTrader.Cbi/Data/NinjaScript usings.
// Phase quick-260415-u6v
//
// P0-2: ATR-trailing stop — tracks MFE per open trade; activates trail at TrailingActivationTicks,
//        tightens at TrailingTightenAtTicks. New exit_reason: "TRAIL".
// P0-3: VOLP-03 volume-surge regime veto — session-level flag set when VOLP-03 fires;
//        blocks all subsequent entries in that session when VolSurgeVetoEnabled.
// P0-5: Slow-grind ATR veto — blocks entry when current bar ATR < SlowGrindAtrRatio × session avg ATR.

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
            bool   inTrade        = false;
            int    entryBarIdx    = 0;
            double entryPrice     = 0.0;
            int    tradeDir       = 0;
            string tradeSignalId  = string.Empty;
            SignalTier tradeTier  = SignalTier.QUIET;
            double tradeScore     = 0.0;
            string tradeNarrative = string.Empty;
            string[] tradeCats    = new string[0];

            // P0-2: ATR-trailing stop state per open trade
            double mfe            = 0.0;   // max favorable excursion in ticks
            double trailStop      = 0.0;   // current trailing stop price (0 = not yet active)
            bool   trailActive    = false;

            // R1: Breakeven state
            bool   breakevenArmed = false;  // true once MFE >= BreakevenActivationTicks
            double stopPrice      = 0.0;    // current effective stop (entry-based or breakeven)

            // R1: Scale-out state
            bool   scaleOutDone   = false;  // true once the T1 partial exit has fired

            // P0-3: VOLP-03 session-level regime flag — reset at session start
            bool volSurgeFiredThisSession = false;

            // P0-5: Slow-grind — session ATR accumulator for rolling average
            double sessionAtrSum   = 0.0;
            int    sessionAtrCount = 0;

            ScoredBarRecord lastRecord = null;
            ScorerResult    lastScored = null;

            var bars = CaptureReplayLoader.LoadScoredBars(ndjsonPath);

            foreach (var rec in bars)
            {
                lastRecord = rec;

                // P0-5: Accumulate session ATR rolling average (using bar's Atr field if present)
                double barAtr = rec.Atr;
                if (barAtr > 0.0)
                {
                    sessionAtrSum   += barAtr;
                    sessionAtrCount++;
                }
                double sessionAvgAtr = sessionAtrCount > 0 ? sessionAtrSum / sessionAtrCount : 0.0;

                // P0-3: Check if any signal on this bar has VOLP-03 prefix — set session flag
                if (config.VolSurgeVetoEnabled && rec.Signals != null)
                {
                    foreach (var sig in rec.Signals)
                    {
                        if (sig != null && sig.SignalId != null &&
                            sig.SignalId.StartsWith("VOLP-03", System.StringComparison.Ordinal))
                        {
                            volSurgeFiredThisSession = true;
                            break;
                        }
                    }
                }

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
                    // Update MFE (max favorable excursion in ticks)
                    // -----------------------------------------------------------------
                    double currentMfe = (rec.BarClose - entryPrice) / config.TickSize * tradeDir;
                    if (currentMfe > mfe)
                        mfe = currentMfe;

                    // -----------------------------------------------------------------
                    // R1: Breakeven stop — arm once MFE >= BreakevenActivationTicks
                    // Move stop to entry + BreakevenOffsetTicks (ratchet only — never move back)
                    // -----------------------------------------------------------------
                    if (config.BreakevenEnabled && !breakevenArmed && mfe >= config.BreakevenActivationTicks)
                    {
                        breakevenArmed = true;
                        double beStop = entryPrice + tradeDir * config.BreakevenOffsetTicks * config.TickSize;
                        // Only tighten (never loosen) the stop
                        if (tradeDir == +1 && beStop > stopPrice)
                            stopPrice = beStop;
                        else if (tradeDir == -1 && beStop < stopPrice)
                            stopPrice = beStop;
                    }

                    // -----------------------------------------------------------------
                    // P0-2: Update trailing stop if enabled and ATR is available
                    // -----------------------------------------------------------------
                    if (config.TrailingStopEnabled && barAtr > 0.0)
                    {
                        if (mfe >= config.TrailingTightenAtTicks)
                        {
                            // Tightened trail: 1.0 × ATR behind current high-water mark
                            double hwm = entryPrice + tradeDir * (mfe * config.TickSize);
                            double newTrail = hwm - tradeDir * (config.TrailingTightenMult * barAtr);
                            if (!trailActive || (tradeDir == +1 ? newTrail > trailStop : newTrail < trailStop))
                            {
                                trailStop  = newTrail;
                                trailActive = true;
                            }
                        }
                        else if (mfe >= config.TrailingActivationTicks)
                        {
                            // Initial trail: 1.5 × ATR behind current high-water mark
                            double hwm = entryPrice + tradeDir * (mfe * config.TickSize);
                            double newTrail = hwm - tradeDir * (config.TrailingOffsetAtr * barAtr);
                            if (!trailActive || (tradeDir == +1 ? newTrail > trailStop : newTrail < trailStop))
                            {
                                trailStop  = newTrail;
                                trailActive = true;
                            }
                        }
                    }

                    // -----------------------------------------------------------------
                    // Check exits in priority order
                    // -----------------------------------------------------------------
                    string exitReason = null;

                    // 1. Hard stop loss (original entry-based stop)
                    if (tradeDir == +1 && rec.BarClose <= entryPrice - (config.StopLossTicks * config.TickSize))
                        exitReason = "STOP_LOSS";
                    else if (tradeDir == -1 && rec.BarClose >= entryPrice + (config.StopLossTicks * config.TickSize))
                        exitReason = "STOP_LOSS";

                    // 1b. Breakeven stop (checked after hard stop — only active once armed)
                    if (exitReason == null && breakevenArmed)
                    {
                        if (tradeDir == +1 && rec.BarClose <= stopPrice)
                            exitReason = "STOP_LOSS";
                        else if (tradeDir == -1 && rec.BarClose >= stopPrice)
                            exitReason = "STOP_LOSS";
                    }

                    // 2. R1: Scale-out partial exit at T1 (ScaleOutTargetTicks)
                    if (exitReason == null && config.ScaleOutEnabled && !scaleOutDone)
                    {
                        if (tradeDir == +1 && rec.BarClose >= entryPrice + (config.ScaleOutTargetTicks * config.TickSize))
                        {
                            // Emit partial exit record (ScaleOutPercent of position)
                            AddTrade(result, config, entryBarIdx, rec.BarIdx, entryPrice, rec.BarClose,
                                tradeDir, "SCALE_OUT_PARTIAL", tradeSignalId, tradeTier, tradeScore,
                                tradeNarrative, tradeCats, config.ScaleOutPercent);
                            scaleOutDone = true;
                            // Continue in trade with remaining position — do NOT set exitReason
                        }
                        else if (tradeDir == -1 && rec.BarClose <= entryPrice - (config.ScaleOutTargetTicks * config.TickSize))
                        {
                            AddTrade(result, config, entryBarIdx, rec.BarIdx, entryPrice, rec.BarClose,
                                tradeDir, "SCALE_OUT_PARTIAL", tradeSignalId, tradeTier, tradeScore,
                                tradeNarrative, tradeCats, config.ScaleOutPercent);
                            scaleOutDone = true;
                        }
                    }

                    // 3. Final target (TargetTicks) — applies to remaining position
                    if (exitReason == null)
                    {
                        if (tradeDir == +1 && rec.BarClose >= entryPrice + (config.TargetTicks * config.TickSize))
                            exitReason = scaleOutDone ? "SCALE_OUT_FINAL" : "TARGET";
                        else if (tradeDir == -1 && rec.BarClose <= entryPrice - (config.TargetTicks * config.TickSize))
                            exitReason = scaleOutDone ? "SCALE_OUT_FINAL" : "TARGET";
                    }

                    // 4. P0-2: Trailing stop (ADDITIVE — checked after hard stop and target)
                    if (exitReason == null && trailActive)
                    {
                        if (tradeDir == +1 && rec.BarClose <= trailStop)
                            exitReason = "TRAIL";
                        else if (tradeDir == -1 && rec.BarClose >= trailStop)
                            exitReason = "TRAIL";
                    }

                    // 5. Opposing signal
                    if (exitReason == null
                        && scored.Direction != 0
                        && scored.Direction != tradeDir
                        && scored.TotalScore >= config.ExitOnOpposingScore)
                    {
                        exitReason = "OPPOSING_SIGNAL";
                    }

                    // 6. Max bars
                    if (exitReason == null && (rec.BarIdx - entryBarIdx) >= config.MaxBarsInTrade)
                        exitReason = "MAX_BARS";

                    if (exitReason != null)
                    {
                        // Remaining position fraction: if scale-out fired, only (1 - ScaleOutPercent) remains
                        double remainFrac = (config.ScaleOutEnabled && scaleOutDone)
                            ? (1.0 - config.ScaleOutPercent)
                            : 1.0;
                        AddTrade(result, config, entryBarIdx, rec.BarIdx, entryPrice, rec.BarClose,
                            tradeDir, exitReason, tradeSignalId, tradeTier, tradeScore, tradeNarrative,
                            tradeCats, remainFrac);
                        inTrade        = false;
                        mfe            = 0.0;
                        trailStop      = 0.0;
                        trailActive    = false;
                        breakevenArmed = false;
                        stopPrice      = 0.0;
                        scaleOutDone   = false;
                    }
                }
                else
                {
                    // -----------------------------------------------------------------
                    // Check entry gate
                    // -----------------------------------------------------------------

                    // P0-3: VOLP-03 regime veto — block entry if flag is set
                    if (config.VolSurgeVetoEnabled && volSurgeFiredThisSession)
                        continue;

                    // P0-5: Slow-grind veto — block entry when ATR is below ratio × session avg
                    if (config.SlowGrindVetoEnabled && barAtr > 0.0 && sessionAvgAtr > 0.0
                        && barAtr < config.SlowGrindAtrRatio * sessionAvgAtr)
                        continue;

                    // R1: Derive bar time as HHMM from BarsSinceOpen.
                    // Session opens at 09:30 ET; each bar = 1 minute.
                    // barsSinceOpen=0 → 09:30, barsSinceOpen=30 → 10:00, etc.
                    int totalMinutes  = 9 * 60 + 30 + rec.BarsSinceOpen;
                    int barHour       = totalMinutes / 60;
                    int barMinute     = totalMinutes % 60;
                    int barTimeHHMM   = barHour * 100 + barMinute;

                    var gate = ScorerEntryGate.EvaluateWithContext(
                        scored,
                        config.ScoreEntryThreshold,
                        config.MinTierForEntry,
                        gateState:              null,
                        volSurgeVetoEnabled:    false,  // already handled inline above
                        slowGrindVetoEnabled:   false,  // already handled inline above
                        strictDirectionEnabled: config.StrictDirectionEnabled,
                        signals:                rec.Signals,
                        blackoutWindowStart:    config.BlackoutWindowStart,
                        blackoutWindowEnd:      config.BlackoutWindowEnd,
                        barTimeHHMM:            barTimeHHMM);
                    if (gate == ScorerEntryGate.GateOutcome.Passed)
                    {
                        // Apply entry slippage (buys higher, shorts sell lower)
                        entryPrice    = scored.EntryPrice + (scored.Direction * config.SlippageTicks * config.TickSize);
                        entryBarIdx   = rec.BarIdx;
                        tradeDir      = scored.Direction;
                        tradeTier     = scored.Tier;
                        tradeScore    = scored.TotalScore;
                        tradeNarrative = scored.Narrative ?? string.Empty;
                        tradeCats     = scored.CategoriesFiring ?? new string[0];
                        tradeSignalId = ExtractDominantSignalId(scored.CategoriesFiring);
                        inTrade       = true;
                        mfe           = 0.0;
                        trailStop     = 0.0;
                        trailActive   = false;
                        // R1: Initialise stop to entry-based hard stop price
                        stopPrice = tradeDir == +1
                            ? entryPrice - config.StopLossTicks * config.TickSize
                            : entryPrice + config.StopLossTicks * config.TickSize;
                        breakevenArmed = false;
                        scaleOutDone   = false;
                    }
                }
            }

            // Session-end force-exit
            if (inTrade && lastRecord != null)
            {
                double remainFrac = (config.ScaleOutEnabled && scaleOutDone)
                    ? (1.0 - config.ScaleOutPercent)
                    : 1.0;
                AddTrade(result, config, entryBarIdx, lastRecord.BarIdx, entryPrice, lastRecord.BarClose,
                    tradeDir, "SESSION_END", tradeSignalId, tradeTier, tradeScore, tradeNarrative,
                    tradeCats, remainFrac);
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
            string[] cats,
            double positionFraction = 1.0)
        {
            // Exit slippage is adverse (against us): longs exit lower, shorts exit higher
            double exitPrice = exitBarClose + (direction * config.SlippageTicks * config.TickSize * -1.0);

            double pnlTicks   = (exitPrice - entryPrice) / config.TickSize * direction;
            // Scale P&L by position fraction (e.g. 0.5 for scale-out partial)
            double pnlDollars = pnlTicks * config.TickValue * config.ContractsPerTrade * positionFraction;
            int    duration   = System.Math.Max(exitBarIdx - entryBarIdx, 1);

            result.Trades.Add(new Trade
            {
                EntryBar         = entryBarIdx,
                ExitBar          = exitBarIdx,
                EntryPrice       = entryPrice,
                ExitPrice        = exitPrice,
                Direction        = direction,
                PnlTicks         = pnlTicks,
                PnlDollars       = pnlDollars,
                SignalId         = signalId,
                Tier             = tier,
                Score            = score,
                Narrative        = narrative,
                ExitReason       = exitReason,
                DurationBars     = duration,
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
