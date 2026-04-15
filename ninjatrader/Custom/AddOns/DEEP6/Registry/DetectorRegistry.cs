// DetectorRegistry: sequential registry calling each ISignalDetector and aggregating results.
//
// Python reference: each deep6/engines/*.py detect_*() function; this registry
//   calls them in registration order (same order DEEP6Strategy configures detectors).
//
// Design (CONTEXT.md D-01 + RESEARCH.md Pattern 2):
//   List-based; registration order controls iteration.
//   EvaluateBar() iterates all detectors and concatenates SignalResult[].
//   Per-detector exceptions are swallowed to a Print warning — a faulty detector
//   must not abort the bar evaluation for other detectors.
//
// Wave 5 additions:
//   - DispatchDepth(): routes DOM depth events to IDepthConsumingDetector instances.
//   - BeginBar() call at start of EvaluateBar() to clear per-bar ENG-02/04 session fields.
//   - IcebergDetector cross-wiring: after AbsorptionDetector signals, calls
//     _absorptionZoneReceiver?.MarkAbsorptionZone() so iceberg detection gets absorption context.
//     Uses IAbsorptionZoneReceiver interface to avoid forward type reference to IcebergDetector.
//
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Interface for detectors that can receive absorption zone notifications.
    /// Implemented by IcebergDetector (ENG-04) to boost synthetic refill confidence
    /// when the refill occurs within a known absorption price zone.
    ///
    /// RESEARCH.md §ENG-04 cross-detector wiring.
    /// </summary>
    public interface IAbsorptionZoneReceiver
    {
        /// <summary>
        /// Mark a price zone as an absorption area. Called by DetectorRegistry after
        /// AbsorptionDetector fires an ABS-* signal, so subsequent iceberg refills
        /// at nearby prices can be flagged as "in-abs-zone".
        /// </summary>
        void MarkAbsorptionZone(double price, int radiusTicks);
    }

    /// <summary>
    /// Sequential registry for ISignalDetector instances.
    ///
    /// Usage by DEEP6Strategy (when UseNewRegistry = true):
    ///   1. Create _registry = new DetectorRegistry()
    ///   2. Register each detector: _registry.Register(new AbsorptionDetector())
    ///   3. On each DOM event: _registry.DispatchDepth(session, side, levelIdx, price, size, priorSize)
    ///   4. On each bar close: var results = _registry.EvaluateBar(bar, session)
    ///   5. On session boundary: _registry.ResetAll()
    ///
    /// Python reference: RESEARCH.md Pattern 2 (DetectorRegistry)
    /// </summary>
    public sealed class DetectorRegistry
    {
        private readonly List<ISignalDetector> _detectors = new List<ISignalDetector>();
        private SignalResult[] _lastResults = Array.Empty<SignalResult>();

        // Typed references for ENG-04 cross-wiring.
        // Use interfaces to avoid forward type references that break compilation order.
        private IAbsorptionZoneReceiver _absorptionZoneReceiver;  // set when IcebergDetector registers
        private int _absorptionDetectorIndex = -1;               // index in _detectors list

        /// <summary>Register a detector. Called once at strategy initialization.</summary>
        public void Register(ISignalDetector detector)
        {
            if (detector == null) return;

            // Cache IAbsorptionZoneReceiver (IcebergDetector implements this for cross-wiring).
            var azr = detector as IAbsorptionZoneReceiver;
            if (azr != null && _absorptionZoneReceiver == null)
                _absorptionZoneReceiver = azr;

            // Cache index of absorption detector (identified by Name or ABS SignalId convention).
            // We identify it by its Name property matching "Absorption".
            if (detector.Name == "Absorption")
                _absorptionDetectorIndex = _detectors.Count;

            _detectors.Add(detector);
        }

        /// <summary>
        /// Route a DOM depth update to all IDepthConsumingDetector instances.
        /// Called from the indicator's OnMarketDepth override (up to 1000/sec).
        /// Allocation-free hot path — only casts/interface checks.
        ///
        /// Also updates session.BidDomLevels / AskDomLevels in place so all detectors
        /// see the same canonical DOM state snapshot.
        /// </summary>
        public void DispatchDepth(SessionContext session, int side, int levelIdx, double price, long size, long? priorSize)
        {
            if (session == null) return;

            // Update shared DOM arrays in session (canonical source for all consumers).
            if (side == 0 && levelIdx >= 0 && levelIdx < session.BidDomLevels.Length)
                session.BidDomLevels[levelIdx] = size;
            else if (side == 1 && levelIdx >= 0 && levelIdx < session.AskDomLevels.Length)
                session.AskDomLevels[levelIdx] = size;

            for (int i = 0; i < _detectors.Count; i++)
            {
                var dc = _detectors[i] as IDepthConsumingDetector;
                if (dc == null) continue;
                try { dc.OnDepth(session, side, levelIdx, price, size, priorSize); }
                catch (Exception ex)
                {
                    Console.Error.WriteLine(string.Format(
                        "[DEEP6 Registry] WARNING: detector '{0}' OnDepth threw {1}: {2}",
                        _detectors[i].Name, ex.GetType().Name, ex.Message));
                }
            }
        }

        /// <summary>
        /// Evaluate all registered detectors for a finalized bar.
        /// Iterates detectors in registration order. Swallows per-detector exceptions
        /// to a logged warning — a faulty detector must not abort the bar.
        ///
        /// Returns the aggregated SignalResult[] from all detectors that fired this bar.
        /// The result is also stored as GetLastResults() for callers that read it separately.
        /// </summary>
        public SignalResult[] EvaluateBar(FootprintBar bar, SessionContext session)
        {
            // Reset per-bar ENG-02/04 cross-detector fields before any detector runs.
            session?.BeginBar();

            var all = new List<SignalResult>();
            for (int idx = 0; idx < _detectors.Count; idx++)
            {
                var detector = _detectors[idx];
                SignalResult[] results = null;
                try
                {
                    results = detector.OnBar(bar, session);
                    if (results != null && results.Length > 0)
                        all.AddRange(results);
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine(string.Format(
                        "[DEEP6 Registry] WARNING: detector '{0}' threw {1}: {2}",
                        detector.Name, ex.GetType().Name, ex.Message));
                }

                // ENG-04 cross-wiring: after AbsorptionDetector fires, notify IcebergDetector
                // of the absorption zone so synthetic refills in that zone get "in-abs-zone" boost.
                // RESEARCH.md §ENG-04 cross-detector wiring.
                if (idx == _absorptionDetectorIndex && _absorptionZoneReceiver != null && results != null)
                {
                    foreach (var r in results)
                    {
                        if (r != null && r.SignalId != null && r.SignalId.StartsWith("ABS-"))
                        {
                            double zonePrice = r.Price > 0.0 ? r.Price : (bar != null ? bar.Close : 0.0);
                            try { _absorptionZoneReceiver.MarkAbsorptionZone(zonePrice, 2); }
                            catch { /* cross-wiring must not abort bar */ }
                        }
                    }
                }
            }
            _lastResults = all.ToArray();
            return _lastResults;
        }

        /// <summary>Returns the SignalResult[] from the most recent EvaluateBar() call.</summary>
        public SignalResult[] GetLastResults() => _lastResults;

        /// <summary>
        /// Reset all registered detectors at session boundary (RTH open).
        /// Calls Reset() on each detector in registration order.
        /// </summary>
        public void ResetAll()
        {
            foreach (var detector in _detectors)
            {
                try { detector.Reset(); }
                catch (Exception ex)
                {
                    Console.Error.WriteLine(string.Format(
                        "[DEEP6 Registry] WARNING: detector '{0}' Reset() threw {1}: {2}",
                        detector.Name, ex.GetType().Name, ex.Message));
                }
            }
        }

        /// <summary>Number of registered detectors.</summary>
        public int Count => _detectors.Count;
    }
}
