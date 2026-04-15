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
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Sequential registry for ISignalDetector instances.
    ///
    /// Usage by DEEP6Strategy (when UseNewRegistry = true):
    ///   1. Create _registry = new DetectorRegistry()
    ///   2. Register each detector: _registry.Register(new AbsorptionDetector())
    ///   3. On each bar close: var results = _registry.EvaluateBar(bar, session)
    ///   4. On session boundary: _registry.ResetAll()
    ///
    /// Python reference: RESEARCH.md Pattern 2 (DetectorRegistry)
    /// </summary>
    public sealed class DetectorRegistry
    {
        private readonly List<ISignalDetector> _detectors = new List<ISignalDetector>();
        private SignalResult[] _lastResults = Array.Empty<SignalResult>();

        /// <summary>Register a detector. Called once at strategy initialization.</summary>
        public void Register(ISignalDetector detector)
        {
            if (detector != null)
                _detectors.Add(detector);
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
            var all = new List<SignalResult>();
            foreach (var detector in _detectors)
            {
                try
                {
                    var results = detector.OnBar(bar, session);
                    if (results != null && results.Length > 0)
                        all.AddRange(results);
                }
                catch (Exception ex)
                {
                    // Swallow per-detector exceptions — log but do not abort the bar.
                    // In NT8 runtime: Print("[DEEP6 Registry] WARNING: {0} threw {1}: {2}", detector.Name, ex.GetType().Name, ex.Message)
                    // In test context: this is surfaced via the exception message below.
                    Console.Error.WriteLine(string.Format(
                        "[DEEP6 Registry] WARNING: detector '{0}' threw {1}: {2}",
                        detector.Name, ex.GetType().Name, ex.Message));
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
