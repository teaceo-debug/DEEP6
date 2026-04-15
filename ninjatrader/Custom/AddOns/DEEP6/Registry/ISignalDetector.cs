// ISignalDetector: minimum interface for all 44 per-family signal detectors.
//
// Python reference: deep6/engines/ (each engine file defines a detect_*() function;
//   this interface is the C# equivalent of that function signature with stateful instances).
//
// Design decision (CONTEXT.md D-01):
//   Stateful instances — each detector owns its own rolling state (CVD deque,
//   prior-bar reference, cooldown counters). Shared state (ATR, session POC,
//   CVD seed, bar history) lives on SessionContext and is passed as a parameter.
//
// CRITICAL: No NinjaTrader.* using directives in this file.
//   Detector classes must compile under net8.0 (test TFM) as well as net48 (NT8).
//   See RESEARCH.md §NUnit on macOS — Critical Finding.

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Common interface for all 44 signal detectors in the DEEP6 registry.
    ///
    /// Implementation pattern: each detector family (Absorption, Exhaustion, Imbalance, etc.)
    /// provides one class implementing this interface. OnBar() is called once per closed bar
    /// by DetectorRegistry.EvaluateBar(). DOM-consuming detectors (ENG-02, ENG-04) also
    /// receive depth updates via the indicator's OnMarketDepth override, but NOT through
    /// this interface (they maintain their own arrays updated externally).
    /// </summary>
    public interface ISignalDetector
    {
        /// <summary>Family name for logging and registry identification, e.g. "Absorption".</summary>
        string Name { get; }

        /// <summary>
        /// Reset all rolling state at session boundary (RTH open).
        /// Called by DetectorRegistry.ResetAll() on session date change.
        /// </summary>
        void Reset();

        /// <summary>
        /// Evaluate a finalized footprint bar and return any signals that fired.
        /// Returns an empty array (not null) when no signals fire this bar.
        /// </summary>
        /// <param name="bar">Finalized FootprintBar at bar close.</param>
        /// <param name="session">Shared session state (ATR, CVD, VAH/VAL, bar history).</param>
        SignalResult[] OnBar(FootprintBar bar, SessionContext session);
    }
}
