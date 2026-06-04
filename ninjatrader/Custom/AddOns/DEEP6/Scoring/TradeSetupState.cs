// TradeSetupState: lifecycle state for Version Two footprint trade setups.
//
// Setup marker (gray square) is context only. A trade becomes actionable only after
// progressing through Armed -> Triggered. Invalid / Expired states preserve chart history
// while making the setup non-tradeable.

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    /// <summary>
    /// Lifecycle for footprint-driven trade setups.
    /// </summary>
    public enum TradeSetupState
    {
        /// <summary>Initial setup detected on the signal bar. Context only; not executable.</summary>
        Setup = 0,

        /// <summary>Setup has enough confluence to watch for an explicit entry trigger.</summary>
        Armed = 1,

        /// <summary>Entry trigger has fired. Entry / stop / target plan is active.</summary>
        Triggered = 2,

        /// <summary>Setup was invalidated before triggering.</summary>
        Invalid = 3,

        /// <summary>Setup timed out without triggering.</summary>
        Expired = 4,
    }
}
