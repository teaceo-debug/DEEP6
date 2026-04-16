// SessionContext: shared per-session state passed to every ISignalDetector.OnBar() call.
//
// Python reference: deep6/state/session.py SessionContext
// Extended with NT8-specific fields for: DOM snapshot, ATR, VolEma, VAH/VAL, rolling histories.
//
// Ownership model (CONTEXT.md D-01):
//   DEEP6Footprint indicator (or DEEP6Strategy) owns the single SessionContext instance.
//   It updates fields after each bar close, then passes it to DetectorRegistry.EvaluateBar().
//   Detectors READ but do not WRITE SessionContext fields directly.
//
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Shared per-session state singleton. Updated by the indicator once per bar close
    /// before detectors are evaluated. Detectors read these fields; they never write.
    ///
    /// Python reference: deep6/state/session.py
    /// DOM arrays mirror deep6/state/dom.py DOMState.
    /// </summary>
    public sealed class SessionContext
    {
        // --- ATR / Volume ---
        /// <summary>Wilder's ATR(20) — updated per bar. Used for adaptive thresholds.</summary>
        public double Atr20;

        /// <summary>EMA(20) of bar total volume — updated per bar.</summary>
        public double VolEma20;

        // --- CVD / Delta ---
        /// <summary>Cumulative delta from prior bar — seed for current bar's CVD chain.</summary>
        public long PriorCvd;

        // --- Bar references ---
        /// <summary>Prior closed bar — used by EXH-06 (bid/ask fade), DELT-06 (trap), etc.</summary>
        public FootprintBar PriorBar;

        // --- Value Area ---
        /// <summary>Value Area High from prior bar (or session profile). Null until computed.</summary>
        public double? Vah;

        /// <summary>Value Area Low from prior bar (or session profile). Null until computed.</summary>
        public double? Val;

        // --- Instrument ---
        /// <summary>Tick size (e.g. 0.25 for NQ). Used for VA extreme proximity calculations.</summary>
        public double TickSize;

        // --- Session lifecycle ---
        /// <summary>Timestamp of session open (9:30 ET for RTH). Set at session boundary reset.</summary>
        public DateTime SessionOpen;

        /// <summary>Number of bars elapsed since session open. Reset to 0 at session boundary.</summary>
        public int BarsSinceOpen;

        // --- DOM snapshot (pre-allocated per CONTEXT.md D-11) ---
        /// <summary>Pre-allocated 40-level bid DOM snapshot. Index 0 = best bid. Updated by indicator OnMarketDepth.</summary>
        public double[] BidDomLevels;

        /// <summary>Pre-allocated 40-level ask DOM snapshot. Index 0 = best ask. Updated by indicator OnMarketDepth.</summary>
        public double[] AskDomLevels;

        /// <summary>Current best bid price.</summary>
        public double BestBid;

        /// <summary>Current best ask price.</summary>
        public double BestAsk;

        // --- Rolling histories (maxlen = MaxHistory) ---
        /// <summary>Recent close prices for regression-based detectors (DELT-10, TRAP-05).</summary>
        public Queue<double> PriceHistory;

        /// <summary>Recent CVD values (bar-end) for CVD divergence detectors (DELT-10).</summary>
        public Queue<long> CvdHistory;

        /// <summary>Recent bar deltas for delta-pattern detectors (DELT-08, DELT-11).</summary>
        public Queue<long> DeltaHistory;

        /// <summary>Recent POC prices for POC momentum (VOLP-04).</summary>
        public Queue<double> PocHistory;

        // --- Session POC ---
        /// <summary>Current session POC price — updated from each bar's PocPrice.</summary>
        public double SessionPocPrice;

        // --- P0-5: Session ATR rolling average (slow-grind veto) ---
        /// <summary>
        /// Rolling average of Atr20 across all bars in the current session.
        /// Updated by the indicator each bar after Atr20 is computed.
        /// Used by slow-grind veto: if Atr20 &lt; SlowGrindAtrRatio × SessionAvgAtr, block entry.
        /// </summary>
        public double SessionAvgAtr;

        /// <summary>Number of ATR samples accumulated this session (denominator for SessionAvgAtr).</summary>
        public int SessionAtrSamples;

        // --- Session delta extremes (DELT-09) ---
        /// <summary>Session maximum bar delta seen so far. Updated AFTER detector evaluation each bar.</summary>
        public long SessionMaxDelta;

        /// <summary>Session minimum bar delta seen so far (typically negative). Updated AFTER detector evaluation.</summary>
        public long SessionMinDelta;

        // --- Imbalance history (IMB-07 consecutive, IMB-09 reversal) ---
        /// <summary>
        /// Per-bar imbalance ratio maps: price → ratio at that level.
        /// Each dictionary represents one bar (the key is an exact price, value is the diagonal ratio).
        /// Queue contains recent bars (oldest first, maxlen = MaxHistory).
        /// IMB-07: intersect current bar's imbalance prices with prior bar entry.
        /// </summary>
        public Queue<Dictionary<double, double>> ImbalanceHistory;

        // --- Unfinished auction levels (AUCT-01 in-memory tracking; cross-session SQLite deferred Phase 18) ---
        /// <summary>
        /// Price levels with unfinished auction activity. Key=price, value=bar index when first seen.
        /// Entries expire after UnfinishedMaxAge bars. Managed by AuctionDetector each bar.
        /// </summary>
        public Dictionary<double, int> UnfinishedLevels;

        /// <summary>Max bar age before UnfinishedLevels entries are expired (100 bars).</summary>
        public const int UnfinishedMaxAge = 100;

        // --- Volume history (VOLP-01 sequencing) ---
        /// <summary>Recent bar total volumes (oldest first, maxlen = MaxHistory). Used by VOLP-01.</summary>
        public Queue<long> VolHistory;

        // --- Total vol history (DELT-08 slingshot compressed gate) ---
        /// <summary>Recent bar total volumes parallel to DeltaHistory for DELT-08 quiet-ratio calculation.</summary>
        public Queue<long> TotalVolHistory;

        // --- ENG-02 Trespass result (written by TrespassDetector, read by MicroProbDetector) ---
        /// <summary>Last trespass probability [0,1] emitted by TrespassDetector this bar. 0.5 = neutral.</summary>
        public double LastTrespassProbability;

        /// <summary>Last trespass direction emitted by TrespassDetector this bar. +1/-1/0.</summary>
        public int LastTrespassDirection;

        // --- ENG-04 Iceberg signals (written by IcebergDetector, read by MicroProbDetector) ---
        /// <summary>
        /// Signal identifiers emitted by IcebergDetector this bar.
        /// Cleared at start of each bar by BeginBar(). Read by MicroProbDetector.
        /// </summary>
        public List<string> LastIcebergSignals;

        /// <summary>Maximum depth for all rolling history queues.</summary>
        public const int MaxHistory = 50;

        public SessionContext()
        {
            // Pre-allocate DOM arrays — zero GC pressure on hot path (CONTEXT.md D-11)
            BidDomLevels = new double[40];
            AskDomLevels = new double[40];

            PriceHistory     = new Queue<double>(MaxHistory + 1);
            CvdHistory       = new Queue<long>(MaxHistory + 1);
            DeltaHistory     = new Queue<long>(MaxHistory + 1);
            TotalVolHistory  = new Queue<long>(MaxHistory + 1);
            PocHistory       = new Queue<double>(MaxHistory + 1);
            ImbalanceHistory = new Queue<Dictionary<double, double>>(MaxHistory + 1);
            VolHistory       = new Queue<long>(MaxHistory + 1);
            UnfinishedLevels = new Dictionary<double, int>();
            LastIcebergSignals = new List<string>();

            // ENG-02 defaults — neutral
            LastTrespassProbability = 0.5;
            LastTrespassDirection   = 0;
        }

        /// <summary>
        /// Push a value into a bounded queue, dropping oldest when over MaxHistory.
        /// Call this from the indicator after each bar close to maintain rolling histories.
        /// </summary>
        public static void Push<T>(Queue<T> q, T value)
        {
            q.Enqueue(value);
            while (q.Count > MaxHistory) q.Dequeue();
        }

        /// <summary>
        /// Reset per-bar ENG-02/04 fields at the start of each bar evaluation cycle.
        /// Called by DetectorRegistry before dispatching EvaluateBar to ensure detectors
        /// writing these fields don't accumulate across bars.
        /// </summary>
        public void BeginBar()
        {
            LastTrespassProbability = 0.5;
            LastTrespassDirection   = 0;
            LastIcebergSignals.Clear();
        }

        /// <summary>
        /// Reset all session-scoped state at RTH open (9:30 ET).
        /// Called by the indicator/strategy on session date change before the first bar.
        /// </summary>
        public void ResetSession()
        {
            PriorCvd        = 0;
            PriorBar        = null;
            Vah             = null;
            Val             = null;
            BarsSinceOpen   = 0;
            SessionPocPrice = 0;
            BestBid         = 0;
            BestAsk         = 0;
            SessionMaxDelta    = 0;
            SessionMinDelta    = 0;
            SessionAvgAtr      = 0.0;
            SessionAtrSamples  = 0;

            // ENG-02/04 state
            LastTrespassProbability = 0.5;
            LastTrespassDirection   = 0;
            LastIcebergSignals.Clear();

            PriceHistory.Clear();
            CvdHistory.Clear();
            DeltaHistory.Clear();
            TotalVolHistory.Clear();
            PocHistory.Clear();
            ImbalanceHistory.Clear();
            VolHistory.Clear();
            UnfinishedLevels.Clear();

            // Reset DOM arrays to zero
            Array.Clear(BidDomLevels, 0, BidDomLevels.Length);
            Array.Clear(AskDomLevels, 0, AskDomLevels.Length);
        }
    }
}
