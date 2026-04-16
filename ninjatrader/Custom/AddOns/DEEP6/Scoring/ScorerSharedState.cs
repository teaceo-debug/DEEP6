// ScorerSharedState: Single-writer (indicator) / single-reader (strategy) latest-value latch.
//
// Keyed by instrument symbol to support multi-chart scenarios.
//
// Design:
//   DEEP6Footprint indicator calls Publish() once per bar close after ConfluenceScorer.Score().
//   DEEP6Strategy (Wave 3) calls Latest() to retrieve the result for entry gating.
//
// NT8-API-free: no NinjaTrader.* using directives — compiles under both net48 and net8.0.
//
// Thread-safety: ConcurrentDictionary provides safe concurrent reads and writes. The
// single-writer-per-symbol pattern means ConcurrentDictionary's Compare-And-Swap semantics
// are not needed — direct assignment is correct here.
//
// Phase 18-02

using System.Collections.Concurrent;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Static latch that holds the latest <see cref="ScorerResult"/> per instrument symbol.
    ///
    /// Writer: DEEP6Footprint indicator — calls <see cref="Publish"/> once per bar close.
    /// Reader: DEEP6Strategy — calls <see cref="Latest"/> inside EvaluateEntry (Wave 3 wires this).
    ///
    /// Keyed by <c>Instrument.FullName</c> (e.g., "NQ 06-26") so two charts on different
    /// contract months don't share state.
    /// </summary>
    public static class ScorerSharedState
    {
        private static readonly ConcurrentDictionary<string, ScorerResult> _latest =
            new ConcurrentDictionary<string, ScorerResult>(System.StringComparer.Ordinal);

        private static readonly ConcurrentDictionary<string, int> _latestBarIdx =
            new ConcurrentDictionary<string, int>(System.StringComparer.Ordinal);

        // R1: Session average ATR for slow-grind veto — published by DEEP6Footprint alongside the scored result.
        private static readonly ConcurrentDictionary<string, double> _latestSessionAvgAtr =
            new ConcurrentDictionary<string, double>(System.StringComparer.Ordinal);

        /// <summary>
        /// Publish the scorer result for the given symbol and bar index.
        /// Call once per bar close, after <see cref="ConfluenceScorer.Score"/> returns.
        /// </summary>
        /// <param name="symbol">Instrument.FullName — the per-symbol key.</param>
        /// <param name="barIdx">CurrentBar index at the time of scoring (for staleness checks).</param>
        /// <param name="result">The scored result to latch. Must not be null.</param>
        public static void Publish(string symbol, int barIdx, ScorerResult result)
        {
            if (symbol == null || result == null) return;
            _latest[symbol]       = result;
            _latestBarIdx[symbol] = barIdx;
        }

        /// <summary>
        /// R1: Publish with session average ATR for the slow-grind veto.
        /// Call from DEEP6Footprint after computing SessionAvgAtr on the SessionContext.
        /// </summary>
        /// <param name="symbol">Instrument.FullName — the per-symbol key.</param>
        /// <param name="barIdx">CurrentBar index at the time of scoring.</param>
        /// <param name="result">The scored result to latch. Must not be null.</param>
        /// <param name="sessionAvgAtr">Rolling session-average ATR from SessionContext.SessionAvgAtr.</param>
        public static void Publish(string symbol, int barIdx, ScorerResult result, double sessionAvgAtr)
        {
            if (symbol == null || result == null) return;
            _latest[symbol]            = result;
            _latestBarIdx[symbol]      = barIdx;
            _latestSessionAvgAtr[symbol] = sessionAvgAtr;
        }

        /// <summary>
        /// Retrieve the latest published result for the given symbol.
        /// Returns null if no result has been published yet.
        /// </summary>
        public static ScorerResult Latest(string symbol)
        {
            ScorerResult r;
            return _latest.TryGetValue(symbol ?? string.Empty, out r) ? r : null;
        }

        /// <summary>
        /// Retrieve the bar index at which the latest result was published.
        /// Returns -1 if no result has been published yet.
        /// </summary>
        public static int LatestBarIndex(string symbol)
        {
            int idx;
            return _latestBarIdx.TryGetValue(symbol ?? string.Empty, out idx) ? idx : -1;
        }

        /// <summary>
        /// R1: Retrieve the session average ATR published alongside the latest result.
        /// Returns 0.0 if no ATR has been published yet (slow-grind veto will be skipped).
        /// </summary>
        public static double LatestSessionAvgAtr(string symbol)
        {
            double v;
            return _latestSessionAvgAtr.TryGetValue(symbol ?? string.Empty, out v) ? v : 0.0;
        }

        /// <summary>
        /// Clear the latch for a specific symbol (e.g., on indicator termination).
        /// Safe to call from any thread.
        /// </summary>
        public static void Clear(string symbol)
        {
            if (symbol == null) return;
            ScorerResult dummy;
            int idxDummy;
            double atrDummy;
            _latest.TryRemove(symbol, out dummy);
            _latestBarIdx.TryRemove(symbol, out idxDummy);
            _latestSessionAvgAtr.TryRemove(symbol, out atrDummy);
        }
    }
}
