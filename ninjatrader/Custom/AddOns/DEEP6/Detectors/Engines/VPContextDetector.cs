// VPContextDetector: ENG-06 Volume Profile context engine.
//
// Python reference: deep6/engines/vp_context_engine.py VPContextEngine
//
// Phase 17 scope: POC context only.
// LVN lifecycle and GEX integration deferred to Phase 18.
// See RESEARCH.md §ENG-06 Phased Scope for full algorithm description.
//
// Current implementation:
//   1. Checks if the bar closed near session POC (within POC proximity ticks).
//   2. Checks if bar close is above/below POC — context for directional bias.
//   3. Fires ENG-06 when bar close is within proximity of session POC with directional label.
//
// What is NOT implemented yet (Phase 18):
//   - LVN (Low Volume Node) gap detection and lifecycle tracking
//   - GEX-level context (FlashAlpha/massive.com data integration)
//   - ZoneRegistry cross-wiring
//   - IB (Initial Balance) extension detection
//   - VWAP context layering
//
// CRITICAL: No NinjaTrader.* using directives.
// This file must compile under net8.0 (test project) AND net48 (NT8).

using System;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Engines
{
    /// <summary>
    /// Configuration for VPContextDetector.
    /// Python reference: deep6/engines/signal_config.py VPContextConfig
    /// </summary>
    public sealed class VPContextConfig
    {
        /// <summary>
        /// Proximity threshold: bar close within this many ticks of session POC triggers ENG-06.
        /// Python: poc_proximity_ticks=4
        /// </summary>
        public int PocProximityTicks = 4;

        /// <summary>
        /// Minimum bars since session open before ENG-06 can fire.
        /// Prevents misfires when session POC has not yet stabilized.
        /// Python: min_bars_for_poc=3
        /// </summary>
        public int MinBarsForPoc = 3;
    }

    /// <summary>
    /// ENG-06 VP+Context: Volume Profile context engine.
    ///
    /// Phase 17 scope: POC context only. LVN lifecycle and GEX integration
    /// deferred to Phase 18. See file comment for full deferred scope.
    ///
    /// Reads session.SessionPocPrice and session.BarsSinceOpen.
    /// Fires ENG-06 with "POC-TEST-BULL" or "POC-TEST-BEAR" detail when bar closes
    /// within PocProximityTicks of the session POC.
    ///
    /// Python reference: deep6/engines/vp_context_engine.py VPContextEngine
    /// </summary>
    public sealed class VPContextDetector : ISignalDetector
    {
        private readonly VPContextConfig _cfg;

        public VPContextDetector() : this(new VPContextConfig()) { }

        public VPContextDetector(VPContextConfig cfg)
        {
            _cfg = cfg ?? new VPContextConfig();
        }

        /// <inheritdoc/>
        public string Name => "VPContext";

        /// <inheritdoc/>
        public void Reset() { /* stateless — all inputs read from SessionContext */ }

        /// <inheritdoc/>
        public SignalResult[] OnBar(FootprintBar bar, SessionContext session)
        {
            if (bar == null || session == null) return Array.Empty<SignalResult>();

            // Guard: POC not yet populated
            if (session.SessionPocPrice <= 0.0) return Array.Empty<SignalResult>();

            // Guard: not enough bars for POC to stabilize
            if (session.BarsSinceOpen < _cfg.MinBarsForPoc) return Array.Empty<SignalResult>();

            // Guard: tick size not set
            double tickSize = session.TickSize > 0.0 ? session.TickSize : 0.25;

            double proximityDistance = _cfg.PocProximityTicks * tickSize;
            double distanceToPoc     = System.Math.Abs(bar.Close - session.SessionPocPrice);

            // Check if bar close is within proximity of session POC
            if (distanceToPoc > proximityDistance) return Array.Empty<SignalResult>();

            // Direction: bar closed above POC = bullish context; below = bearish context
            int direction = bar.Close >= session.SessionPocPrice ? +1 : -1;

            string detail = string.Format(
                "VP-CONTEXT {0}: close={1:F2} poc={2:F2} dist={3:F2}t proximity={4}t",
                direction > 0 ? "POC-TEST-BULL" : "POC-TEST-BEAR",
                bar.Close, session.SessionPocPrice,
                distanceToPoc / tickSize,
                _cfg.PocProximityTicks);

            // Strength: 1.0 when exactly at POC, fades linearly with distance
            double strength = 1.0 - (distanceToPoc / proximityDistance);

            return new[]
            {
                new SignalResult("ENG-06", direction,
                    strength,
                    SignalFlagBits.Mask(SignalFlagBits.ENG_06),
                    detail,
                    bar.Close)
            };
        }
    }
}
