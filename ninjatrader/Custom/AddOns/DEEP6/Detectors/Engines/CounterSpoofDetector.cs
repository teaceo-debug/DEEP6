// CounterSpoofDetector: ENG-03 Wasserstein-1 DOM distribution monitor + large-order cancel detection.
//
// Python reference: deep6/engines/counter_spoof.py CounterSpoofEngine
//
// Algorithm (counter_spoof.py lines 110-144):
//   Per OnBar (simplified from Python's periodic 100ms snapshot model):
//     1. Compute W1 distance between current BidDomLevels and _prevBid snapshot.
//     2. Compute W1 distance between current AskDomLevels and _prevAsk snapshot.
//     3. Fire ENG-03 if either exceeds spoof_threshold.
//     4. Copy current DOM to _prev after checking.
//
// Python all-zero guard:
//   counter_spoof.py lines 128-140: if prev_sum==0 or curr_sum==0 → w1=0.
//   This is already handled inside Wasserstein.Distance() (returns 0.0 when either array sums to 0).
//
// Direction:
//   Bid-side spike (large cancel on bid) → bearish (sellers withdrew support).
//   Ask-side spike (large cancel on ask) → bullish (sellers removed their offers).
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Math;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// Configuration for CounterSpoofDetector.
    /// Python reference: deep6/engines/signal_config.py CounterSpoofConfig
    /// </summary>
    public sealed class CounterSpoofConfig
    {
        /// <summary>W1 distance threshold to fire ENG-03. Python: spoof_w1_threshold=0.25</summary>
        public double SpoofThreshold = 0.25;
    }

    /// <summary>
    /// ENG-03 CounterSpoof: Wasserstein-1 DOM distribution monitor.
    ///
    /// Detects sudden structural changes in the bid or ask DOM distribution by
    /// measuring W1 distance between consecutive bar-close DOM snapshots.
    ///
    /// Implements IDepthConsumingDetector to receive live DOM updates (though the main
    /// detection runs in OnBar comparing bar-close snapshots, not tick-by-tick).
    ///
    /// Python reference: deep6/engines/counter_spoof.py CounterSpoofEngine
    /// </summary>
    public sealed class CounterSpoofDetector : IDepthConsumingDetector
    {
        private readonly CounterSpoofConfig _cfg;

        // Prior bar DOM snapshots (instance-level, not in SessionContext — detector-internal state).
        private readonly double[] _prevBid = new double[40];
        private readonly double[] _prevAsk = new double[40];
        private bool _hasPrior = false;

        public CounterSpoofDetector() : this(new CounterSpoofConfig()) { }

        public CounterSpoofDetector(CounterSpoofConfig cfg)
        {
            _cfg = cfg ?? new CounterSpoofConfig();
        }

        /// <inheritdoc/>
        public string Name => "CounterSpoof";

        /// <inheritdoc/>
        public void Reset()
        {
            Array.Clear(_prevBid, 0, _prevBid.Length);
            Array.Clear(_prevAsk, 0, _prevAsk.Length);
            _hasPrior = false;
        }

        /// <inheritdoc/>
        /// <summary>OnDepth: no-op for CounterSpoofDetector — detection happens at bar close via OnBar.</summary>
        public void OnDepth(SessionContext session, int side, int levelIdx, double price, long size, long? priorSize)
        {
            // No-op: CounterSpoofDetector compares bar-close DOM snapshots in OnBar,
            // not individual depth ticks. Session DOM arrays are updated by DispatchDepth.
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || session == null) return Array.Empty<SignalResult>();

            if (!_hasPrior)
            {
                // First bar — capture snapshot and return without firing.
                Array.Copy(session.BidDomLevels, _prevBid, 40);
                Array.Copy(session.AskDomLevels, _prevAsk, 40);
                _hasPrior = true;
                return Array.Empty<SignalResult>();
            }

            // Compute W1 distances between current and prior DOM distributions.
            // Wasserstein.Distance() handles the all-zero guard (returns 0.0 per Python guard).
            double w1Bid = Wasserstein.Distance(_prevBid, session.BidDomLevels);
            double w1Ask = Wasserstein.Distance(_prevAsk, session.AskDomLevels);

            // Update prior snapshot AFTER computing distances (Python: step 4 in ingest_snapshot).
            Array.Copy(session.BidDomLevels, _prevBid, 40);
            Array.Copy(session.AskDomLevels, _prevAsk, 40);

            double threshold = _cfg.SpoofThreshold;
            bool bidSpike = w1Bid > threshold;
            bool askSpike = w1Ask > threshold;

            if (!bidSpike && !askSpike) return Array.Empty<SignalResult>();

            // Direction: bid-side cancel (bid DOM changed) → bearish; ask-side → bullish.
            // If both spikes, use the larger one to determine direction.
            int    direction;
            double w1Max;
            string sideLabel;
            if (bidSpike && (!askSpike || w1Bid >= w1Ask))
            {
                direction = -1;   // Bid support withdrew — bearish
                w1Max     = w1Bid;
                sideLabel = "bid";
            }
            else
            {
                direction = +1;   // Ask pressure removed — bullish
                w1Max     = w1Ask;
                sideLabel = "ask";
            }

            double strength = System.Math.Min(w1Max / (threshold * 4.0), 1.0);

            return new[]
            {
                new SignalResult("ENG-03", direction, strength,
                    SignalFlagBits.Mask(SignalFlagBits.ENG_03),
                    string.Format("COUNTER-SPOOF: W1_{0}={1:F4} > threshold={2:F4} — large DOM distribution shift",
                        sideLabel, w1Max, threshold),
                    bar.Close)
            };
        }
    }
}
