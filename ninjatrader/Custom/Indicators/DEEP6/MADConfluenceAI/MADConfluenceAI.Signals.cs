// MADConfluenceAI.Signals.cs — All 12 signal detectors implemented
// Order Flow: ABS-01, ABS-02, EXH-01, EXH-02, DELT-01, DELT-02, IMB-01
// Liquidity: ICE-01, LIQSW-01, FAIL-01, TRAP-01
// Context: REG-01
using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public partial class MADConfluenceAI : Indicator
    {
        // ── ABS-01: Classic Absorption ──────────────────────────────────
        // High volume at single price level with zero/minimal price progress.
        // If dominant side is BidVol (sellers absorbed by passive buyers) → Long.
        // If AskVol dominant (buyers absorbed by passive sellers) → Short.
        private MADSignalResult DetectAbs01(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0) return null;

            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            double threshold = AbsorptionVolumeMultiplier * avgLevelVol;

            // Bar range must be < 8 ticks (2.0 points for NQ, tick = 0.25)
            if (bar.BarRange > 2.0) return null;

            double bestPrice = 0;
            long bestVol = 0;
            MADCell bestCell = null;

            foreach (var kv in bar.Levels)
            {
                if (kv.Value.TotalVol > threshold && kv.Value.TotalVol > bestVol)
                {
                    bestVol = kv.Value.TotalVol;
                    bestPrice = kv.Key;
                    bestCell = kv.Value;
                }
            }

            if (bestCell == null) return null;

            var direction = bestCell.BidVol > bestCell.AskVol
                ? MADSignalDirection.Long   // sellers absorbed by passive buyers
                : MADSignalDirection.Short;  // buyers absorbed by passive sellers

            double strength = Math.Min(1.0, (double)bestCell.TotalVol / (AbsorptionVolumeMultiplier * 2.0 * avgLevelVol));

            return new MADSignalResult
            {
                SignalId = "ABS-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Classic absorption at {0}, vol={1}, avg={2:F0}",
                    bestPrice, bestVol, avgLevelVol),
                Price = bestPrice
            };
        }

        // ── ABS-02: Passive Absorption ─────────────────────────────────
        // Look back 3 bars. If cumulative |delta| > 3 × avgBarDelta AND
        // price range over those 3 bars < 12 ticks (3.0 points): passive absorption.
        // Direction: opposite to delta direction.
        private MADSignalResult DetectAbs02(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state)
        {
            if (bars == null || bars.Count < 3) return null;

            int start = bars.Count - 3;
            long cumDelta = 0;
            double highestHigh = double.MinValue;
            double lowestLow = double.MaxValue;

            for (int i = start; i < bars.Count; i++)
            {
                cumDelta += bars[i].BarDelta;
                if (bars[i].High > highestHigh) highestHigh = bars[i].High;
                if (bars[i].Low < lowestLow) lowestLow = bars[i].Low;
            }

            double priceRange = highestHigh - lowestLow;
            if (priceRange > 3.0) return null; // must be < 12 ticks

            // Average bar delta across all available bars
            long totalAbsDelta = 0;
            foreach (var b in bars)
                totalAbsDelta += Math.Abs(b.BarDelta);
            double avgBarDelta = bars.Count > 0 ? (double)totalAbsDelta / bars.Count : 1.0;
            if (avgBarDelta < 1.0) avgBarDelta = 1.0;

            if (Math.Abs(cumDelta) <= 3.0 * avgBarDelta) return null;

            // Direction opposite to delta (if delta strongly negative = sellers aggressive but price held → Long)
            var direction = cumDelta < 0
                ? MADSignalDirection.Long
                : MADSignalDirection.Short;

            double strength = Math.Min(1.0, Math.Abs(cumDelta) / (avgBarDelta * 5.0));

            return new MADSignalResult
            {
                SignalId = "ABS-02",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Passive absorption over 3 bars, cumDelta={0}, range={1:F2}",
                    cumDelta, priceRange),
                Price = bar.Close
            };
        }

        // ── EXH-01: Exhaustion Print ───────────────────────────────────
        // Find highest-volume level at bar High or Low. If that volume > 2 × avgLevelVol
        // AND bar closes away from that extreme by > 50% of bar range: exhaustion.
        // Gate: DeltaQualityScalar() > 0.5 required.
        private MADSignalResult DetectExh01(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.TotalVol == 0) return null;
            if (bar.BarRange <= 0) return null;
            if (bar.DeltaQualityScalar() <= 0.3) return null;

            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            double volThreshold = 2.0 * avgLevelVol;

            // Find volume at High and Low
            MADCell cellAtHigh = null;
            MADCell cellAtLow = null;
            bar.Levels.TryGetValue(bar.High, out cellAtHigh);
            bar.Levels.TryGetValue(bar.Low, out cellAtLow);

            long volAtHigh = cellAtHigh != null ? cellAtHigh.TotalVol : 0;
            long volAtLow = cellAtLow != null ? cellAtLow.TotalVol : 0;

            // Pick the extreme with highest volume
            bool exhaustionAtHigh = volAtHigh > volAtLow && volAtHigh > volThreshold;
            bool exhaustionAtLow = volAtLow > volAtHigh && volAtLow > volThreshold;

            if (!exhaustionAtHigh && !exhaustionAtLow) return null;

            double midpoint = bar.Low + bar.BarRange * 0.5;
            double exhaustionPrice;
            MADSignalDirection direction;
            double distanceFromExtreme;

            if (exhaustionAtHigh)
            {
                if (bar.Close >= midpoint) return null; // close must be below midpoint for buying exhaustion
                exhaustionPrice = bar.High;
                direction = MADSignalDirection.Short; // buying exhaustion
                distanceFromExtreme = bar.High - bar.Close;
            }
            else
            {
                if (bar.Close <= midpoint) return null; // close must be above midpoint for selling exhaustion
                exhaustionPrice = bar.Low;
                direction = MADSignalDirection.Long; // selling exhaustion
                distanceFromExtreme = bar.Close - bar.Low;
            }

            double strength = Math.Min(1.0, distanceFromExtreme / bar.BarRange);

            return new MADSignalResult
            {
                SignalId = "EXH-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Exhaustion print at {0}, vol={1}, close distance={2:F2}",
                    exhaustionPrice, exhaustionAtHigh ? volAtHigh : volAtLow, distanceFromExtreme),
                Price = exhaustionPrice
            };
        }

        // ── EXH-02: Fading Momentum ────────────────────────────────────
        // Look back 3 bars. If delta consistently decays by > ExhaustionDeltaDecay per bar
        // AND all 3 deltas in same direction AND price still pushing same direction.
        // Direction: opposite to fading direction.
        private MADSignalResult DetectExh02(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state)
        {
            if (bars == null || bars.Count < 3) return null;

            int n = bars.Count;
            var b0 = bars[n - 1]; // most recent
            var b1 = bars[n - 2];
            var b2 = bars[n - 3]; // oldest of the 3

            long d0 = b0.BarDelta;
            long d1 = b1.BarDelta;
            long d2 = b2.BarDelta;

            // All 3 deltas must be in the same direction
            if (d2 == 0) return null;
            bool positive = d2 > 0;
            if (positive && (d1 <= 0 || d0 <= 0)) return null;
            if (!positive && (d1 >= 0 || d0 >= 0)) return null;

            // Check decay: |d0| < decay * |d1| AND |d1| < decay * |d2|
            double absD0 = Math.Abs(d0);
            double absD1 = Math.Abs(d1);
            double absD2 = Math.Abs(d2);

            if (absD2 == 0) return null;
            if (absD0 >= ExhaustionDeltaDecay * absD1) return null;
            if (absD1 >= ExhaustionDeltaDecay * absD2) return null;

            // Price still pushing same direction
            bool pricePushingUp = b0.Close > b2.Close;
            bool pricePushingDown = b0.Close < b2.Close;
            if (positive && !pricePushingUp) return null;
            if (!positive && !pricePushingDown) return null;

            // Direction: opposite to fading direction
            var direction = positive
                ? MADSignalDirection.Short  // fading bullish momentum → bearish
                : MADSignalDirection.Long;  // fading bearish momentum → bullish

            double strength = Math.Min(1.0, 1.0 - (absD0 / absD2));

            return new MADSignalResult
            {
                SignalId = "EXH-02",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Fading momentum: delta {0}→{1}→{2}",
                    d2, d1, d0),
                Price = b0.Close
            };
        }

        // ── DELT-01: Delta Divergence ──────────────────────────────────
        // Use MADDeltaPipeline.CheckDivergence(lookback=10).
        // Positive → bullish divergence (price down, CVD up) → Long.
        // Negative → bearish divergence (price up, CVD down) → Short.
        private MADSignalResult DetectDelt01(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state, MADDeltaPipeline deltaPipeline)
        {
            if (deltaPipeline == null || deltaPipeline.Count < 5) return null;

            double divergence = deltaPipeline.CheckDivergence(10);
            if (divergence == 0) return null;

            var direction = divergence > 0
                ? MADSignalDirection.Long   // bullish divergence
                : MADSignalDirection.Short; // bearish divergence

            double strength = Math.Min(1.0, Math.Abs(divergence) / 500.0);

            return new MADSignalResult
            {
                SignalId = "DELT-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("{0} divergence, magnitude={1:F2}",
                    divergence > 0 ? "Bullish" : "Bearish", Math.Abs(divergence)),
                Price = bar != null ? bar.Close : 0
            };
        }

        // ── DELT-02: CVD Acceleration ──────────────────────────────────
        // Use MADDeltaPipeline.DeltaAccel. If acceleration changes sign with
        // sufficient magnitude: potential reversal signal.
        private MADSignalResult DetectDelt02(MADFootprintBar bar, List<MADFootprintBar> bars, MADMarketState state, MADDeltaPipeline deltaPipeline)
        {
            if (deltaPipeline == null || deltaPipeline.Count < 6) return null;

            double accel = deltaPipeline.DeltaAccel;
            double roc = deltaPipeline.DeltaRoC;

            if (Math.Abs(accel) < 1.0) return null; // minimum magnitude threshold

            MADSignalDirection direction;
            // DeltaAccel positive while DeltaRoC was negative → CVD decelerating downward → Long
            // DeltaAccel negative while DeltaRoC was positive → CVD decelerating upward → Short
            if (accel > 0 && roc < 0)
                direction = MADSignalDirection.Long;
            else if (accel < 0 && roc > 0)
                direction = MADSignalDirection.Short;
            else
                return null; // no sign change = no inflection

            double strength = Math.Min(1.0, Math.Abs(accel) / 100.0);

            return new MADSignalResult
            {
                SignalId = "DELT-02",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("CVD acceleration={0:F1}, RoC={1:F1}",
                    accel, roc),
                Price = bar != null ? bar.Close : 0
            };
        }

        // ── IMB-01: Stacked Imbalance ──────────────────────────────────
        // 3+ consecutive levels with imbalance ratio > threshold AND
        // each level totalVol >= 5 contracts. Same direction throughout.
        private MADSignalResult DetectImb01(MADFootprintBar bar, double imbalanceRatio)
        {
            if (bar == null || bar.Levels.Count < 3) return null;

            int bestRun = 0;
            double bestStartPrice = 0;
            bool bestAskDom = false;

            int currentRun = 0;
            double currentStartPrice = 0;
            bool currentAskDom = false;

            foreach (var kv in bar.Levels)
            {
                var cell = kv.Value;
                if (cell.TotalVol < 5 || cell.ImbalanceRatio < imbalanceRatio)
                {
                    currentRun = 0;
                    continue;
                }

                bool askDom = cell.AskVol > cell.BidVol;

                if (currentRun == 0 || askDom != currentAskDom)
                {
                    currentRun = 1;
                    currentStartPrice = kv.Key;
                    currentAskDom = askDom;
                }
                else
                {
                    currentRun++;
                }

                if (currentRun > bestRun)
                {
                    bestRun = currentRun;
                    bestStartPrice = currentStartPrice;
                    bestAskDom = currentAskDom;
                }
            }

            if (bestRun < 3) return null;

            var direction = bestAskDom
                ? MADSignalDirection.Long    // ask dominant = aggressive buying
                : MADSignalDirection.Short;  // bid dominant = aggressive selling

            double strength = Math.Min(1.0, (bestRun - 2.0) / 5.0);

            return new MADSignalResult
            {
                SignalId = "IMB-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Stacked imbalance: {0} levels, {1}-dominant",
                    bestRun, bestAskDom ? "ask" : "bid"),
                Price = bestStartPrice
            };
        }

        // ── ICE-01: Iceberg Detection ──────────────────────────────────
        // Detect passive hidden orders refilled repeatedly at the same price.
        // refillCount >= 3 at a price → iceberg detected.
        private MADSignalResult DetectIce01(MADFootprintBar bar, bool isDomAvailable, Func<double, int> getRefillCount)
        {
            if (bar == null || bar.Levels.Count == 0 || !isDomAvailable || getRefillCount == null) return null;

            double bestPrice = 0;
            int bestRefills = 0;
            MADCell bestCell = null;

            foreach (var kv in bar.Levels)
            {
                int refills = getRefillCount(kv.Key);
                if (refills >= 3 && refills > bestRefills)
                {
                    bestRefills = refills;
                    bestPrice = kv.Key;
                    bestCell = kv.Value;
                }
            }

            if (bestCell == null) return null;

            var direction = bestCell.BidVol > bestCell.AskVol
                ? MADSignalDirection.Long    // bid-side iceberg → passive buyers
                : MADSignalDirection.Short;  // ask-side iceberg → passive sellers

            double strength = Math.Min(1.0, bestRefills / 10.0);

            return new MADSignalResult
            {
                SignalId = "ICE-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Iceberg at {0}, refills={1}", bestPrice, bestRefills),
                Price = bestPrice
            };
        }

        // ── LIQSW-01: Liquidity Sweep ──────────────────────────────────
        // Bar breaks a key level then reverses back. Volume > 2× average.
        // Returns the strongest signal if multiple levels swept.
        private MADSignalResult DetectLiqSw01(MADFootprintBar bar, List<MADLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || nearbyLevels == null || nearbyLevels.Count == 0) return null;
            if (bar.BarRange <= 0) return null;
            if (avgBarVol > 0 && bar.TotalVol <= 2.0 * avgBarVol) return null;

            MADSignalResult best = null;
            double bestStrength = 0;

            foreach (var level in nearbyLevels)
            {
                double lp = level.Price;

                // Sweep above: broke above then closed below
                if (bar.High > lp && bar.Close < lp)
                {
                    double reversal = Math.Abs(bar.Close - bar.High);
                    double s = Math.Min(1.0, reversal / bar.BarRange);
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "LIQSW-01",
                            Direction = MADSignalDirection.Short,
                            Strength = s,
                            Detail = string.Format("Sweep above {0}, reversed to {1:F2}", lp, bar.Close),
                            Price = lp
                        };
                    }
                }

                // Sweep below: broke below then closed above
                if (bar.Low < lp && bar.Close > lp)
                {
                    double reversal = Math.Abs(bar.Close - bar.Low);
                    double s = Math.Min(1.0, reversal / bar.BarRange);
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "LIQSW-01",
                            Direction = MADSignalDirection.Long,
                            Strength = s,
                            Detail = string.Format("Sweep below {0}, reversed to {1:F2}", lp, bar.Close),
                            Price = lp
                        };
                    }
                }
            }

            return best;
        }

        // ── FAIL-01: Failed Auction ────────────────────────────────────
        // POC at bar extreme + close away from extreme + sparse levels at extreme.
        private MADSignalResult DetectFail01(MADFootprintBar bar)
        {
            if (bar == null || bar.Levels.Count == 0 || bar.BarRange <= 0) return null;

            MADCell pocCell;
            if (!bar.Levels.TryGetValue(bar.PocPrice, out pocCell) || pocCell == null) return null;

            double tickSize = 0.25;
            bool atHigh = Math.Abs(bar.PocPrice - bar.High) <= tickSize;
            bool atLow = Math.Abs(bar.PocPrice - bar.Low) <= tickSize;
            if (!atHigh && !atLow) return null;

            double midpoint = bar.Low + bar.BarRange * 0.5;
            MADSignalDirection direction;
            double extremePrice;

            if (atHigh && bar.Close < midpoint)
            {
                direction = MADSignalDirection.Short;
                extremePrice = bar.High;
            }
            else if (atLow && bar.Close > midpoint)
            {
                direction = MADSignalDirection.Long;
                extremePrice = bar.Low;
            }
            else
            {
                return null;
            }

            // Single print check: <= 2 levels within 1 tick of extreme
            int levelsNearExtreme = 0;
            foreach (var kv in bar.Levels)
            {
                if (Math.Abs(kv.Key - extremePrice) <= tickSize)
                    levelsNearExtreme++;
            }
            if (levelsNearExtreme > 2) return null;

            double avgLevelVol = (double)bar.TotalVol / bar.Levels.Count;
            double strength = Math.Min(1.0, pocCell.TotalVol / (avgLevelVol * 3.0));

            return new MADSignalResult
            {
                SignalId = "FAIL-01",
                Direction = direction,
                Strength = strength,
                Detail = string.Format("Failed auction at {0}, POC vol={1}",
                    atHigh ? "high" : "low", pocCell.TotalVol),
                Price = extremePrice
            };
        }

        // ── TRAP-01: False Breakout Trap ───────────────────────────────
        // Prior bar broke a level, current bar reversed back inside.
        // Trapped traders become fuel for the reversal.
        private MADSignalResult DetectTrap01(MADFootprintBar bar, List<MADFootprintBar> bars, List<MADLevel> nearbyLevels, double avgBarVol)
        {
            if (bar == null || bars == null || bars.Count < 2) return null;
            if (nearbyLevels == null || nearbyLevels.Count == 0) return null;

            var priorBar = bars[bars.Count - 2];
            MADSignalResult best = null;
            double bestStrength = 0;

            foreach (var level in nearbyLevels)
            {
                double lp = level.Price;

                // Trapped longs: prior bar broke above, current closed below
                if (priorBar.High > lp && bar.Close < lp)
                {
                    double s = avgBarVol > 0
                        ? Math.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0))
                        : 0.5;
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "TRAP-01",
                            Direction = MADSignalDirection.Short,
                            Strength = s,
                            Detail = string.Format("Trapped longs above {0}", lp),
                            Price = lp
                        };
                    }
                }

                // Trapped shorts: prior bar broke below, current closed above
                if (priorBar.Low < lp && bar.Close > lp)
                {
                    double s = avgBarVol > 0
                        ? Math.Min(1.0, (double)priorBar.TotalVol / (avgBarVol * 2.0))
                        : 0.5;
                    if (s > bestStrength)
                    {
                        bestStrength = s;
                        best = new MADSignalResult
                        {
                            SignalId = "TRAP-01",
                            Direction = MADSignalDirection.Long,
                            Strength = s,
                            Detail = string.Format("Trapped shorts below {0}", lp),
                            Price = lp
                        };
                    }
                }
            }

            return best;
        }

        // ── REG-01: Regime Classifier ──────────────────────────────────
        // Classify market as Trending, Ranging, Volatile, or Thin.
        // Context signal — direction is always Neutral.
        private MADSignalResult DetectReg01(MADMarketState state, MADDeltaPipeline deltaPipeline, List<MADFootprintBar> bars)
        {
            if (state == null || bars == null || bars.Count < 10) return null;

            var lastBar = bars[bars.Count - 1];
            string regime;
            double confidence;

            // Thin: volume < 0.5x VolEma (highest priority)
            if (state.VolEma > 0 && lastBar.TotalVol < 0.5 * state.VolEma)
            {
                regime = "Thin";
                double ratio = (double)lastBar.TotalVol / (state.VolEma * 0.5);
                confidence = Math.Max(0, Math.Min(1.0, 1.0 - ratio));
            }
            else
            {
                // ATR percentile from bar ranges over last 50 bars
                int lookback = Math.Min(50, bars.Count);
                double[] ranges = new double[lookback];
                for (int i = 0; i < lookback; i++)
                    ranges[i] = bars[bars.Count - 1 - i].BarRange;
                Array.Sort(ranges);

                int belowAtr = 0;
                for (int i = 0; i < lookback; i++)
                {
                    if (ranges[i] <= state.Atr20) belowAtr++;
                }
                double atrPct = (double)belowAtr / lookback;

                if (atrPct > 0.75)
                {
                    regime = "Volatile";
                    confidence = Math.Min(1.0, (atrPct - 0.75) / 0.25);
                }
                else if (atrPct < 0.25)
                {
                    regime = "Ranging";
                    confidence = Math.Min(1.0, (0.25 - atrPct) / 0.25);
                }
                else
                {
                    // Delta trend: count consecutive same-sign deltas from most recent bar
                    int sameSignCount = 0;
                    bool lastPositive = lastBar.BarDelta >= 0;
                    for (int i = bars.Count - 1; i >= Math.Max(0, bars.Count - 10); i--)
                    {
                        if ((bars[i].BarDelta >= 0) == lastPositive)
                            sameSignCount++;
                        else
                            break;
                    }

                    bool htfAligned = state.HtfBias != MADTrend.Neutral;

                    if (sameSignCount >= 7 && htfAligned)
                    {
                        regime = "Trending";
                        confidence = Math.Min(1.0, sameSignCount / 10.0);
                    }
                    else
                    {
                        regime = "Ranging";
                        confidence = Math.Min(1.0, 1.0 - (sameSignCount / 10.0));
                    }
                }
            }

            return new MADSignalResult
            {
                SignalId = "REG-01",
                Direction = MADSignalDirection.Neutral,
                Strength = confidence,
                Detail = string.Format("Regime: {0}", regime),
                Price = lastBar.Close
            };
        }
    }
}
