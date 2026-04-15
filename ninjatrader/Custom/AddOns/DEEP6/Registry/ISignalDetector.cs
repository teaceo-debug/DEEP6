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
    /// receive depth updates via the indicator's OnMarketDepth override, routed through
    /// DetectorRegistry.DispatchDepth().
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

    /// <summary>
    /// Optional interface for detectors that consume real-time DOM depth updates.
    /// ENG-02 (TrespassDetector), ENG-03 (CounterSpoofDetector), ENG-04 (IcebergDetector)
    /// implement this interface. DetectorRegistry.DispatchDepth() routes depth events only
    /// to detectors that implement IDepthConsumingDetector.
    ///
    /// Called from the indicator's OnMarketDepth override (up to 1000/sec on NQ).
    /// Implementations MUST be allocation-free (no new, no LINQ) on the hot path.
    /// </summary>
    public interface IDepthConsumingDetector : ISignalDetector
    {
        /// <summary>
        /// Process a single DOM depth update.
        /// </summary>
        /// <param name="session">Shared session state — may update BidDomLevels/AskDomLevels in-place.</param>
        /// <param name="side">0 = bid, 1 = ask.</param>
        /// <param name="levelIdx">Level index 0..39 (0 = best bid/ask).</param>
        /// <param name="price">Price at this DOM level.</param>
        /// <param name="size">Current size (quantity) at this level. 0 means level cleared.</param>
        /// <param name="priorSize">Prior size at this level before the update. Null if not tracked.</param>
        void OnDepth(SessionContext session, int side, int levelIdx, double price, long size, long? priorSize);
    }
}
