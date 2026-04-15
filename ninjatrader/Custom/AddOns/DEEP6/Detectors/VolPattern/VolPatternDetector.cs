// VolPatternDetector: ISignalDetector implementation for VOLP-02, VOLP-03, VOLP-06.
//
// Python reference: deep6/engines/vol_patterns.py VolPatternEngine
// Signal IDs:
//   VOLP-02: Volume Bubble — isolated high-volume price level
//   VOLP-03: Volume Surge — bar volume > surge_mult × vol_ema
//   VOLP-06: Big Delta Per Level — one price level with dominant net delta
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).
//
// Note: VOLP-01, VOLP-04, VOLP-05 come in a later wave (require bar history deque).

using System;
using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.VolPattern
{
    /// <summary>
    /// Configuration for VolPatternDetector.
    /// Python reference: deep6/engines/signal_config.py VolPatternConfig lines 245-270
    /// </summary>
    public sealed class VolPatternConfig
    {
        /// <summary>Level vol > avg_level_vol * this to fire VOLP-02. Python: bubble_mult=4.0</summary>
        public double BubbleMult = 4.0;

        /// <summary>Bar vol > vol_ema * this to fire VOLP-03. Python: surge_mult=3.0</summary>
        public double SurgeMult = 3.0;

        /// <summary>Min |delta/vol| to assign directional bias for VOLP-03. Python: surge_delta_min_ratio (check delta dominance)</summary>
        public double SurgeDeltaMinRatio = 0.20;

        /// <summary>Min |net_delta| at single level to fire VOLP-06. Python: big_delta_level_threshold=80</summary>
        public int BigDeltaLevelThreshold = 80;
    }

    /// <summary>
    /// Detects VOLP-02 (Volume Bubble), VOLP-03 (Volume Surge), VOLP-06 (Big Delta Per Level).
    ///
    /// Implements ISignalDetector; stateless between bars.
    /// Python reference: deep6/engines/vol_patterns.py VolPatternEngine
    /// </summary>
    public sealed class VolPatternDetector : ISignalDetector
    {
        private readonly VolPatternConfig _cfg;

        public VolPatternDetector() : this(new VolPatternConfig()) { }

        public VolPatternDetector(VolPatternConfig cfg)
        {
            _cfg = cfg ?? new VolPatternConfig();
        }

        /// <inheritdoc/>
        public string Name => "VolPattern";

        /// <inheritdoc/>
        public void Reset()
        {
            // Stateless detector — nothing to reset.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || bar.Levels == null || bar.Levels.Count == 0 || bar.TotalVol == 0)
                return Array.Empty<SignalResult>();

            double volEma = session != null && session.VolEma20 > 0 ? session.VolEma20 : bar.TotalVol;

            var results = new List<SignalResult>();

            // --- VOLP-02: VOLUME BUBBLE ---
            // Python vol_patterns.py lines 179-222:
            //   Find highest-volume level where level_vol > avg_level_vol * bubble_mult.
            //   Fires one signal at the max-volume bubble level.
            //   Direction from level net delta (ask-bid sign).
            //   Strength = min((best_vol / threshold - 1.0) / 3.0, 1.0)
            {
                int    nLevels     = bar.Levels.Count;
                double avgLevelVol = (double)bar.TotalVol / nLevels;
                double threshold   = avgLevelVol * _cfg.BubbleMult;

                double bestVol   = 0.0;
                double bestPx    = double.NaN;
                long   bestAsk   = 0, bestBid = 0;

                foreach (var kv in bar.Levels)
                {
                    long levelVol = kv.Value.AskVol + kv.Value.BidVol;
                    if (levelVol > threshold && levelVol > bestVol)
                    {
                        bestVol = levelVol;
                        bestPx  = kv.Key;
                        bestAsk = kv.Value.AskVol;
                        bestBid = kv.Value.BidVol;
                    }
                }

                if (!double.IsNaN(bestPx))
                {
                    double str = System.Math.Min((bestVol / threshold - 1.0) / 3.0, 1.0);
                    long   net = bestAsk - bestBid;
                    int    dir = net > 0 ? +1 : (net < 0 ? -1 : 0);
                    results.Add(new SignalResult(
                        "VOLP-02", dir, System.Math.Max(0.0, str),
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_02),
                        string.Format("VOL BUBBLE at {0:F2}: {1} contracts ({2:F1}x avg level vol)",
                            bestPx, (long)bestVol, bestVol / avgLevelVol)));
                }
            }

            // --- VOLP-03: VOLUME SURGE ---
            // Python vol_patterns.py lines 228-261:
            //   bar.total_vol > vol_ema * surge_mult.
            //   Direction: sign of bar_delta if |delta/vol| > surge_delta_min_ratio, else 0.
            //   Strength = min((total_vol / threshold - 1.0) / 2.0, 1.0)
            {
                double surgeThreshold = volEma * _cfg.SurgeMult;
                if (surgeThreshold > 0 && bar.TotalVol > surgeThreshold)
                {
                    double deltaRatio = bar.TotalVol > 0
                        ? (double)System.Math.Abs(bar.BarDelta) / bar.TotalVol
                        : 0.0;
                    int dir = deltaRatio > _cfg.SurgeDeltaMinRatio
                        ? (bar.BarDelta > 0 ? +1 : -1)
                        : 0;
                    double str = System.Math.Min((bar.TotalVol / surgeThreshold - 1.0) / 2.0, 1.0);
                    results.Add(new SignalResult(
                        "VOLP-03", dir, System.Math.Max(0.0, str),
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_03),
                        string.Format("VOL SURGE: {0} contracts ({1:F1}x ema); delta {2:+#;-#;0} ({3:F1}%)",
                            bar.TotalVol, (double)bar.TotalVol / volEma,
                            bar.BarDelta, deltaRatio * 100)));
                }
            }

            // --- VOLP-06: BIG DELTA PER LEVEL ---
            // Python vol_patterns.py lines 352-397:
            //   Find level with highest |net_delta| (ask_vol - bid_vol).
            //   Fires if best |net_delta| >= big_delta_level_threshold.
            //   Direction = sign of net_delta at that level.
            //   Strength = min((best_abs - threshold) / (threshold * 2.0), 1.0)
            //
            // Note: plan spec says also check against bar.BarDelta * 0.40 and avgLevelDelta * 3.0,
            //       but Python reference only checks a single threshold (big_delta_level_threshold).
            //       Port matches Python: single absolute threshold, no ratio vs bar delta.
            {
                long   bestAbsDelta = 0;
                long   bestNetDelta = 0;
                double bestPx6      = double.NaN;

                foreach (var kv in bar.Levels)
                {
                    long netDelta = kv.Value.AskVol - kv.Value.BidVol;
                    long absDelta = System.Math.Abs(netDelta);
                    if (absDelta > bestAbsDelta)
                    {
                        bestAbsDelta = absDelta;
                        bestNetDelta = netDelta;
                        bestPx6      = kv.Key;
                    }
                }

                if (!double.IsNaN(bestPx6) && bestAbsDelta >= _cfg.BigDeltaLevelThreshold)
                {
                    int    dir = bestNetDelta > 0 ? +1 : -1;
                    double th  = _cfg.BigDeltaLevelThreshold;
                    double str = System.Math.Min((bestAbsDelta - th) / (th * 2.0), 1.0);
                    results.Add(new SignalResult(
                        "VOLP-06", dir, System.Math.Max(0.0, str),
                        SignalFlagBits.Mask(SignalFlagBits.VOLP_06),
                        string.Format("BIG DELTA/LEVEL at {0:F2}: net_delta {1:+#;-#;0} (threshold {2})",
                            bestPx6, bestNetDelta, _cfg.BigDeltaLevelThreshold)));
                }
            }

            return results.ToArray();
        }
    }
}
