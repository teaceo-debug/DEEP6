// SignalResult: per-signal output returned by ISignalDetector.OnBar().
//
// Python reference: deep6/signals/flags.py (SignalFlags bit layout)
// Per-signal output shape mirrors Python AbsorptionSignal / ExhaustionSignal dataclasses.
//
// Direction convention:
//   +1 = bullish reversal (long opportunity)
//   -1 = bearish reversal (short opportunity)
//    0 = neutral / context only

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Single signal result emitted by a detector at bar close.
    /// Returned as SignalResult[] from ISignalDetector.OnBar().
    /// </summary>
    public sealed class SignalResult
    {
        /// <summary>Signal identifier, e.g. "ABS-01", "EXH-03", "IMB-07".</summary>
        public string SignalId;

        /// <summary>Trade direction: +1 long, -1 short, 0 neutral.</summary>
        public int Direction;

        /// <summary>Normalized signal strength, range [0.0, 1.0].</summary>
        public double Strength;

        /// <summary>Single-bit ulong mask from SignalFlagBits. Use SignalFlagBits.Mask(bit).</summary>
        public ulong FlagBit;

        /// <summary>Human-readable diagnostic string for logging and visual overlays.</summary>
        public string Detail;

        /// <summary>
        /// Triggering price level (bar.Close, absorption level, etc.).
        /// Used by ENG-04 absorption-zone wiring and Phase 18 scorer.
        /// Default 0.0 when not set.
        /// </summary>
        public double Price;

        public SignalResult() { }

        public SignalResult(string signalId, int direction, double strength, ulong flagBit, string detail)
        {
            SignalId  = signalId;
            Direction = direction;
            Strength  = strength;
            FlagBit   = flagBit;
            Detail    = detail;
        }

        public SignalResult(string signalId, int direction, double strength, ulong flagBit, string detail, double price)
        {
            SignalId  = signalId;
            Direction = direction;
            Strength  = strength;
            FlagBit   = flagBit;
            Detail    = detail;
            Price     = price;
        }
    }
}
