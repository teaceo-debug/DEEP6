// =================================================================================
//  ConfluenceBiasFilter.cs
//  =======================
//  DEEP6 ATLAS bridge -- consumes InstitutionalConfluence indicator output
//  and exposes a clean bias scalar + gating API for Engine #15 (Dark Pool Confluence)
//  and any other engine that wants to consume institutional state.
//
//  Usage from a strategy / engine:
//
//      // In your strategy class:
//      private ConfluenceBiasFilter _confluence;
//
//      // State.Configure:
//      _confluence = new ConfluenceBiasFilter(this);
//
//      // OnBarUpdate (after the indicator has loaded):
//      _confluence.Attach(InstitutionalConfluence("http://127.0.0.1:8765", 15,
//                                                  true, true, true, false));
//
//      // Per-trade decisions:
//      if (!_confluence.IsLongAllowed(minScore: 1)) return;
//      double sizeMultiplier = _confluence.GetSizeMultiplier();
//      ExecuteOrder(LongQty * sizeMultiplier);
//
//  Author: Michael / Peak Asset Performance LLC
// =================================================================================

#region Using declarations
using System;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators.PeakAssetPerformance;
#endregion

namespace NinjaTrader.NinjaScript.Strategies.PeakAssetPerformance
{
    public class ConfluenceBiasFilter
    {
        private readonly NinjaScriptBase _owner;
        private InstitutionalConfluence  _ic;
        private EquilibriumModel         _eqm;       // optional Equilibrium Model attachment

        public ConfluenceBiasFilter(NinjaScriptBase owner)
        {
            _owner = owner ?? throw new ArgumentNullException(nameof(owner));
        }

        // -------------------------------------------------------------------------
        //  Attach indicators
        // -------------------------------------------------------------------------
        public void Attach(InstitutionalConfluence ic)
        {
            _ic = ic ?? throw new ArgumentNullException(nameof(ic));
        }

        /// <summary>
        /// Attach the Equilibrium Model sibling indicator (optional). When attached,
        /// SFV target / 4-regime bias / distance-to-SFV become available and the
        /// Engine #15 contribution incorporates SFV mean-reversion signals.
        /// </summary>
        public void AttachEquilibrium(EquilibriumModel eqm)
        {
            _eqm = eqm ?? throw new ArgumentNullException(nameof(eqm));
        }

        // -------------------------------------------------------------------------
        //  Snapshot accessors -- safe to call from OnBarUpdate
        // -------------------------------------------------------------------------
        public bool   IsReady    { get { return _ic?.Latest != null; } }
        public int    Score      { get { return _ic?.Latest?.confluence_score ?? 0; } }
        public string Alert      { get { return _ic?.Latest?.alert; } }
        public string AlertReason{ get { return _ic?.Latest?.alert_reason; } }

        public string GexBias    { get { return _ic?.Latest?.gex?.bias       ?? "NEUTRAL"; } }
        public string DpBias     { get { return _ic?.Latest?.darkpool?.bias  ?? "NEUTRAL"; } }
        public string MacroRegime{ get { return _ic?.Latest?.regime?.macro   ?? "NEUTRAL"; } }
        public string OpusVerdict{ get { return _ic?.Latest?.composite?.opus_verdict ?? "UNKNOWN"; } }

        public double DpConfidence  { get { return _ic?.Latest?.darkpool?.confidence ?? 0.0; } }
        public double QqqSetupScore { get { return _ic?.Latest?.composite?.qqq_setup_score ?? 0.0; } }

        public double? GexFlip      { get { return _ic?.Latest?.gex?.flip;      } }
        public double? GexCallWall  { get { return _ic?.Latest?.gex?.call_wall; } }
        public double? GexPutWall   { get { return _ic?.Latest?.gex?.put_wall;  } }
        public double? DpVwap       { get { return _ic?.Latest?.darkpool?.dp_vwap; } }

        // -------------------------------------------------------------------------
        //  EQUILIBRIUM MODEL ACCESSORS  (available when AttachEquilibrium called)
        // -------------------------------------------------------------------------
        public bool    EquilibriumReady   { get { return _eqm?.Latest != null; } }
        public double? Sfv                { get { return _eqm?.Latest?.sfv;            } }
        public double? UpperPremium       { get { return _eqm?.Latest?.upper_premium;  } }
        public double? LowerDiscount      { get { return _eqm?.Latest?.lower_discount; } }
        public double? ExtremeUpper       { get { return _eqm?.Latest?.extreme_upper;  } }
        public double? ExtremeLower       { get { return _eqm?.Latest?.extreme_lower;  } }
        public double? DistanceToSfv      { get { return _eqm?.Latest?.distance_to_sfv; } }
        public double? SigmaPoints        { get { return _eqm?.Latest?.sigma_points;   } }
        public string  EquilibriumZone    { get { return _eqm?.Latest?.current_zone    ?? "UNKNOWN"; } }
        public string  GammaRegime        { get { return _eqm?.Latest?.regime?.gamma_regime       ?? "NEUTRAL"; } }
        public string  VolatilityRegime   { get { return _eqm?.Latest?.regime?.volatility_regime  ?? "STABLE";  } }
        public string  TrendAlignment     { get { return _eqm?.Latest?.regime?.trend_alignment    ?? "NEUTRAL"; } }
        public string  InstitutionalBias  { get { return _eqm?.Latest?.regime?.institutional_bias ?? "NEUTRAL"; } }

        // -------------------------------------------------------------------------
        //  GATING API  -- the engine calls these to decide entry / sizing
        // -------------------------------------------------------------------------

        /// <summary>
        /// Long entry allowed when confluence score >= minScore AND no STOP_BUYING alert.
        /// Returns false if indicator not yet loaded (fail-safe -- no trade without data).
        /// </summary>
        public bool IsLongAllowed(int minScore = 1, bool requireFreshData = true)
        {
            if (!IsReady) return false;
            if (Score < minScore) return false;
            if (Alert == "STOP_BUYING") return false;
            if (Alert == "REGIME_DIVERGENCE" && OpusVerdict == "BEAR") return false;
            if (requireFreshData && IsStale()) return false;
            return true;
        }

        /// <summary>
        /// Short entry allowed when confluence score <= -minScore AND no STOP_SELLING alert.
        /// </summary>
        public bool IsShortAllowed(int minScore = 1, bool requireFreshData = true)
        {
            if (!IsReady) return false;
            if (Score > -minScore) return false;
            if (Alert == "STOP_SELLING") return false;
            if (Alert == "REGIME_DIVERGENCE" && OpusVerdict == "BULL") return false;
            if (requireFreshData && IsStale()) return false;
            return true;
        }

        /// <summary>
        /// Size multiplier in [0.0, 1.5] for fractional Kelly-style position adjustment.
        /// - Score 0 .. ±1  -> 0.5x  (low conviction)
        /// - Score ±2       -> 0.8x
        /// - Score ±3       -> 1.0x  (baseline)
        /// - Score ±4       -> 1.2x
        /// - Score ±5       -> 1.5x  (max conviction, FULL_SEND alert)
        /// </summary>
        public double GetSizeMultiplier()
        {
            if (!IsReady) return 0.0;
            int abs = Math.Abs(Score);
            switch (abs)
            {
                case 0: return 0.0;     // no trade -- forces gating layer to also reject
                case 1: return 0.5;
                case 2: return 0.8;
                case 3: return 1.0;
                case 4: return 1.2;
                default: return 1.5;
            }
        }

        /// <summary>
        /// Bias scalar in [-1, +1] for engine voting. Used by Engine #15 to contribute to
        /// the DEEP6 ATLAS Bayesian fusion layer.
        /// </summary>
        public double GetBiasScalar()
        {
            if (!IsReady) return 0.0;
            return Math.Max(-1.0, Math.Min(1.0, Score / 5.0));
        }

        /// <summary>
        /// True if the payload is older than threshold (default 60 s).
        /// </summary>
        public bool IsStale(int thresholdSec = 60)
        {
            if (!IsReady) return true;
            if (string.IsNullOrEmpty(_ic.Latest.ts)) return true;
            try
            {
                var ts  = DateTime.Parse(_ic.Latest.ts).ToUniversalTime();
                var age = (DateTime.UtcNow - ts).TotalSeconds;
                return age > thresholdSec;
            }
            catch { return true; }
        }

        /// <summary>
        /// Convenience: structured single-line summary for Print() / logging.
        /// </summary>
        public string FormatSummary()
        {
            if (!IsReady) return "[Confluence] not ready";
            return string.Format(
                "[Confluence] score={0:+0;-0;0}  GEX={1}  DP={2}({3:F0}%)  Regime={4}  Opus={5}  Alert={6}",
                Score, GexBias, DpBias, DpConfidence * 100, MacroRegime, OpusVerdict,
                Alert ?? "—");
        }

        // -------------------------------------------------------------------------
        //  ENGINE #15 INTEGRATION HOOK
        //
        //  Engine #15 (Dark Pool Confluence) in DEEP6 ATLAS expects a contributor
        //  that returns: (vote, confidence, weight).
        //
        //    vote:       +1 = bullish, -1 = bearish, 0 = abstain
        //    confidence: 0..1
        //    weight:     0..1 (multiplier in the supermajority vote)
        //
        //  Call this from Engine #15's Compute() method.
        // -------------------------------------------------------------------------
        public (int vote, double confidence, double weight) ContributeToEngine15()
        {
            if (!IsReady || IsStale()) return (0, 0.0, 0.0);

            int vote = Score >= 2 ? 1 : Score <= -2 ? -1 : 0;
            double conf = Math.Min(1.0, Math.Abs(Score) / 5.0);

            // Weight = 0.4 base (DP-dominant) + DP confidence boost
            double weight = 0.40 + 0.20 * DpConfidence;

            // Hard veto path -- conflict alerts force abstain
            if (Alert == "STOP_BUYING" || Alert == "STOP_SELLING" ||
                Alert == "REGIME_DIVERGENCE")
            {
                vote   = 0;
                weight = 0.10;   // still contribute "abstain" signal weakly
            }
            // FULL_SEND alerts boost weight
            if (Alert == "FULL_SEND_LONG" || Alert == "FULL_SEND_SHORT")
            {
                weight = Math.Min(1.0, weight + 0.30);
                conf   = Math.Min(1.0, conf   + 0.20);
            }

            // ---- EQUILIBRIUM MODEL OVERLAY (if attached) -----------------------
            //
            //  FADE_PREMIUM / FADE setups override momentum vote in counter-trend
            //  CAUTION + extreme bands force vote=0
            //  FULL_SEND that AGREES with InstitutionalBias gets weight bonus
            //
            if (EquilibriumReady)
            {
                string ib = InstitutionalBias;
                double? dist = DistanceToSfv;
                double? sigPts = SigmaPoints;

                // Hard veto: price beyond extreme band → mean reversion
                if (dist.HasValue && sigPts.HasValue && sigPts.Value > 0)
                {
                    double zScore = dist.Value / sigPts.Value;
                    if (zScore >= 2.5 && vote > 0) { vote = 0; weight = 0.10; }   // long at extreme top
                    if (zScore <= -2.5 && vote < 0) { vote = 0; weight = 0.10; }  // short at extreme bottom
                }

                // Bias-aligned boost
                if (ib == "FOLLOW_MOMENTUM" && vote != 0)
                    weight = Math.Min(1.0, weight + 0.10);

                // Counter-trend veto
                if (ib == "FADE_PREMIUM" && vote > 0)    { vote = 0; weight = 0.15; }
                if (ib == "DEFEND_DISCOUNT" && vote < 0) { vote = 0; weight = 0.15; }

                // CAUTION damping
                if (ib == "CAUTION") { weight *= 0.5; conf *= 0.7; }
            }

            return (vote, conf, weight);
        }

        // -------------------------------------------------------------------------
        //  EQUILIBRIUM-AWARE TARGET HELPERS  (for trade management)
        // -------------------------------------------------------------------------

        /// <summary>
        /// Suggested take-profit target for a long entry: SFV (mean reversion magnet).
        /// Falls back to UpperPremium if no SFV; null if neither available.
        /// </summary>
        public double? SuggestedLongTarget()
        {
            if (!EquilibriumReady) return null;
            return Sfv ?? UpperPremium;
        }

        /// <summary>
        /// Suggested take-profit target for a short entry: SFV (mean reversion magnet).
        /// Falls back to LowerDiscount if no SFV; null if neither available.
        /// </summary>
        public double? SuggestedShortTarget()
        {
            if (!EquilibriumReady) return null;
            return Sfv ?? LowerDiscount;
        }

        /// <summary>
        /// Suggested stop loss for a long entry: LowerDiscount or ExtremeLower.
        /// </summary>
        public double? SuggestedLongStop()
        {
            if (!EquilibriumReady) return null;
            return LowerDiscount ?? ExtremeLower;
        }

        /// <summary>
        /// Suggested stop loss for a short entry: UpperPremium or ExtremeUpper.
        /// </summary>
        public double? SuggestedShortStop()
        {
            if (!EquilibriumReady) return null;
            return UpperPremium ?? ExtremeUpper;
        }
    }
}
