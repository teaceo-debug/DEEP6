// IcebergDetector: ENG-04 native + synthetic iceberg detection.
//
// Python reference: deep6/engines/iceberg.py IcebergEngine
//
// Two detection variants:
//   NATIVE: A price level has more traded volume this bar than the displayed DOM size × ratio.
//           Simplified: if any bar level's (AskVol+BidVol) > session.BidDomLevels[0] * native_ratio.
//   SYNTHETIC: A DOM level depletes (size drops to near 0) and refills to near-prior size
//              within refill_window_ms (default 250ms) — detected via Stopwatch monotonic clock.
//
// ENG-04 cross-wiring (RESEARCH.md §ENG-04):
//   Implements IAbsorptionZoneReceiver so DetectorRegistry can call MarkAbsorptionZone()
//   after AbsorptionDetector fires. Refills inside absorption zones get "in-abs-zone" detail.
//
// Writes signal identifiers to SessionContext.LastIcebergSignals for MicroProbDetector (ENG-05).
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// Configuration for IcebergDetector.
    /// Python reference: deep6/engines/signal_config.py IcebergConfig
    /// </summary>
    public sealed class IcebergConfig
    {
        /// <summary>Minimum ratio of traded vol to DOM displayed size to flag native iceberg. Python: native_ratio=2.0</summary>
        public double NativeRatio = 2.0;

        /// <summary>Maximum ms after depletion for a refill to be counted as synthetic. Python: refill_window_ms=250</summary>
        public double RefillWindowMs = 250.0;

        /// <summary>Size below which a level is considered "depleted". Python: depletion_threshold=5</summary>
        public long DepletionThreshold = 5;

        /// <summary>Minimum fraction of prior peak size that a refill must reach. Python: refill_ratio=0.5</summary>
        public double RefillRatio = 0.5;
    }

    /// <summary>
    /// ENG-04 Iceberg detection: native fills and synthetic DOM refills.
    ///
    /// Implements IDepthConsumingDetector + IAbsorptionZoneReceiver.
    ///   - IDepthConsumingDetector: tracks per-level size changes via OnDepth().
    ///   - IAbsorptionZoneReceiver: registers absorption zones from AbsorptionDetector
    ///     so refills near those zones get flagged as "in-abs-zone".
    ///
    /// Python reference: deep6/engines/iceberg.py IcebergEngine
    /// </summary>
    public sealed class IcebergDetector : IDepthConsumingDetector, IAbsorptionZoneReceiver
    {
        private readonly IcebergConfig _cfg;

        // Per-level depletion tracking: price → (depletedAtMs, priorPeakSize)
        private readonly Dictionary<double, (double depletedAtMs, long peakSize)> _depletions
            = new Dictionary<double, (double, long)>();

        // Per-level prior size (updated in OnDepth)
        private readonly Dictionary<double, long> _priorSizes = new Dictionary<double, long>();

        // Absorption zones: set of (roundedPrice, radiusTicks) pairs
        private readonly List<(double price, int radiusTicks)> _absorptionZones
            = new List<(double, int)>();

        // Monotonic clock reference point — Stopwatch.GetTimestamp() at construction.
        private readonly long _startTick = Stopwatch.GetTimestamp();

        // Signals emitted this bar (collected in OnDepth/OnBar, written to session, then cleared)
        private readonly List<string> _barSignals = new List<string>();

        public IcebergDetector() : this(new IcebergConfig()) { }

        public IcebergDetector(IcebergConfig cfg)
        {
            _cfg = cfg ?? new IcebergConfig();
        }

        /// <inheritdoc/>
        public string Name => "Iceberg";

        /// <inheritdoc/>
        public void Reset()
        {
            _depletions.Clear();
            _priorSizes.Clear();
            _absorptionZones.Clear();
            _barSignals.Clear();
        }

        /// <summary>
        /// Mark an absorption zone. Called by DetectorRegistry after AbsorptionDetector fires.
        /// Refills within price ± (radiusTicks × session.TickSize) will be flagged "in-abs-zone".
        /// RESEARCH.md §ENG-04 cross-detector wiring.
        /// </summary>
        public void MarkAbsorptionZone(double price, int radiusTicks)
        {
            if (price <= 0.0) return;
            _absorptionZones.Add((price, radiusTicks));
            // Cap to avoid unbounded growth (keep last 20 zones per session)
            while (_absorptionZones.Count > 20) _absorptionZones.RemoveAt(0);
        }

        /// <summary>Returns current time in milliseconds since detector construction (monotonic).</summary>
        private double NowMs() =>
            (Stopwatch.GetTimestamp() - _startTick) * 1000.0 / Stopwatch.Frequency;

        /// <summary>Returns true if price is within any registered absorption zone.</summary>
        private bool IsInAbsorptionZone(double price, double tickSize)
        {
            if (tickSize <= 0.0) tickSize = 0.25;
            foreach (var zone in _absorptionZones)
            {
                double radius = zone.radiusTicks * tickSize;
                if (System.Math.Abs(price - zone.price) <= radius) return true;
            }
            return false;
        }

        /// <inheritdoc/>
        /// <summary>
        /// Track DOM level size changes for synthetic iceberg detection.
        /// Records depletions and checks for rapid refills within RefillWindowMs.
        /// Allocation-free for the common path — only allocates when a new price level is seen.
        /// </summary>
        public void OnDepth(SessionContext session, int side, int levelIdx, double price, long size, long? priorSize)
        {
            if (session == null || price <= 0.0) return;

            double roundedPrice = System.Math.Round(price / 0.25) * 0.25;
            double tickSize     = session.TickSize > 0 ? session.TickSize : 0.25;
            double nowMs        = NowMs();

            long prior = 0;
            _priorSizes.TryGetValue(roundedPrice, out prior);

            // Depletion: level drops to near-zero (≤ DepletionThreshold)
            if (size <= _cfg.DepletionThreshold && prior > _cfg.DepletionThreshold)
            {
                _depletions[roundedPrice] = (nowMs, prior);
            }

            // Refill check: level had been depleted and is now refilling
            if (_depletions.TryGetValue(roundedPrice, out var depInfo))
            {
                double elapsedMs = nowMs - depInfo.depletedAtMs;
                if (elapsedMs <= _cfg.RefillWindowMs && size >= depInfo.peakSize * _cfg.RefillRatio && size > _cfg.DepletionThreshold)
                {
                    // Synthetic iceberg detected
                    bool inZone = IsInAbsorptionZone(roundedPrice, tickSize);
                    string detail = inZone ? "synthetic-iceberg-in-abs-zone" : "synthetic-iceberg";
                    _barSignals.Add(string.Format("{0}@{1:F2}ms", detail, elapsedMs));
                    _depletions.Remove(roundedPrice);
                }
            }

            _priorSizes[roundedPrice] = size;
        }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || session == null) return Array.Empty<SignalResult>();

            var results = new List<SignalResult>();
            double tickSize = session.TickSize > 0 ? session.TickSize : 0.25;

            // --- NATIVE iceberg check: bar traded more than visible DOM at best level ---
            // Simplified: if bar has any level where total vol > BidDomLevels[0] * native_ratio
            // (best-bid visible depth as proxy for the "expected" display size)
            long bestBidDisplay = (long)session.BidDomLevels[0];
            long bestAskDisplay = (long)session.AskDomLevels[0];
            long nativeThreshBid = (long)(bestBidDisplay * _cfg.NativeRatio);
            long nativeThreshAsk = (long)(bestAskDisplay * _cfg.NativeRatio);

            if (bar.Levels != null)
            {
                foreach (var kv in bar.Levels)
                {
                    long levelVol = kv.Value.AskVol + kv.Value.BidVol;
                    if ((nativeThreshBid > 0 && kv.Value.BidVol > nativeThreshBid) ||
                        (nativeThreshAsk > 0 && kv.Value.AskVol > nativeThreshAsk))
                    {
                        bool inZone  = IsInAbsorptionZone(kv.Key, tickSize);
                        int  dir     = kv.Value.AskVol > kv.Value.BidVol ? -1 : +1; // more ask fills → selling pressure
                        string detail = inZone
                            ? string.Format("ICEBERG NATIVE: level {0:F2} vol {1} > DOM threshold — in-abs-zone", kv.Key, levelVol)
                            : string.Format("ICEBERG NATIVE: level {0:F2} vol {1} > DOM threshold", kv.Key, levelVol);
                        results.Add(new SignalResult("ENG-04", dir, 0.75,
                            SignalFlagBits.Mask(SignalFlagBits.ENG_04), detail, kv.Key));
                        session.LastIcebergSignals.Add(string.Format("native-{0}-{1:F2}",
                            dir > 0 ? "bid" : "ask", kv.Key));
                        break; // one native iceberg per bar is sufficient
                    }
                }
            }

            // --- SYNTHETIC iceberg signals collected during OnDepth calls this bar ---
            foreach (var sig in _barSignals)
            {
                bool inZone = sig.Contains("in-abs-zone");
                int  dir    = 0; // direction unknown for synthetic without aggressor info
                string detail = inZone
                    ? string.Format("ICEBERG SYNTHETIC ({0})", sig)
                    : string.Format("ICEBERG SYNTHETIC ({0})", sig);
                results.Add(new SignalResult("ENG-04", dir, inZone ? 0.9 : 0.7,
                    SignalFlagBits.Mask(SignalFlagBits.ENG_04), detail, bar.Close));
                session.LastIcebergSignals.Add(sig);
            }
            _barSignals.Clear();

            return results.ToArray();
        }
    }
}
