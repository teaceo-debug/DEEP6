// ConfluenceScorer: Two-layer confluence scorer — NT8-API-free port of Python scorer.py.
//
// Python reference: deep6/scoring/scorer.py score_bar() function
// Port: Phase 18-01 — verbatim weights, thresholds, formula, and tier logic.
//
// Layer 1: Engine-level agreement ratio (what fraction of signal votes agree on direction)
// Layer 2: Category-level confluence multiplier (how many signal categories agree)
//
// Multiplier order (locked — matches Python phase 12-01):
//   base → confluence_mult → zone_bonus + gex_near_wall → agreement → ib_mult → vpin → clip(0,100)
//
// NT8-API-free: no NinjaTrader.Cbi, NinjaTrader.NinjaScript.Indicators, or NinjaTrader.Data usings.
//
// FOOTGUN: Do NOT fuse ib_mult and vpin_modifier into a single coefficient applied to per-signal
// scores. They must be separate final-stage multipliers applied to the fused total_score only.
// (See Python scorer.py phase 12-01 FOOTGUN 1 note.)
//
// NOTE: System.Math is fully qualified throughout (System.Math.Min / Max / Abs) because
// the project also contains a NinjaTrader.NinjaScript.AddOns.DEEP6.Math namespace that
// would otherwise shadow the System.Math class.

using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring
{
    using SR = NinjaTrader.NinjaScript.AddOns.DEEP6.Registry.SignalResult;

    /// <summary>
    /// NT8-API-free two-layer confluence scorer.
    /// Static class — call Score() once per bar close.
    ///
    /// Python source-of-truth: deep6/scoring/scorer.py score_bar()
    /// Category weights, tier thresholds, formula order all verbatim from Python.
    /// </summary>
    public static class ConfluenceScorer
    {
        // -------------------------------------------------------------------------
        // Category weights — R3 attribution-optimized profile
        // Source: ninjatrader/backtests/results/round3/WEIGHT-OPTIMIZATION-R3.md
        //
        // R3 key finding: IMB-03 stacked imbalance is ALPHA-POSITIVE (81.2% WR, 19.5t avg P&L,
        // SNR=28.76 per SIGNAL-REATTRIBUTION.md). With imbalance now actively scoring,
        // optimal grid config is abs=20, imb=24-25, with exh proportionally adjusted.
        // Named config 5_attribution_r3 (abs=20.2, exh=15.7, imb=28.5, vol=20.2, auct=12.6)
        // yields +12.0% Sharpe improvement vs R1 baseline (0.9026 → 1.0107).
        //
        // R3 changes from R1:
        //   absorption: 32.0 → 20.0  (over-weighted in R1; grid avg confirms 20 optimal)
        //   exhaustion:  24.0 → 15.7  (reduced proportionally)
        //   imbalance:   13.0 → 25.0  (IMB-03 confirmed alpha; weight raised to grid optimal)
        //   volume_profile: 5.0 → 20.2 (attribution-r3 profile raises vol_profile weight)
        //   delta:       14.0 → 14.3  (nominal change, grid proportional distribution)
        //   auction:     12.0 → 12.6  (nominal change)
        //   trapped:      0.0 → 0.0   (unchanged — near-zero SNR)
        //   poc:          0.0 → 0.0   (unchanged — negligible SNR)
        //
        // Rounded to 1 decimal; sum ≈ 107.8 (rounded — scorer clips to 100 via Math.Min).
        // -------------------------------------------------------------------------
        private const double W_ABSORPTION     = 20.0;
        private const double W_EXHAUSTION     = 15.7;
        private const double W_TRAPPED        = 0.0;
        private const double W_DELTA          = 14.3;
        private const double W_IMBALANCE      = 25.0;
        private const double W_VOLUME_PROFILE = 20.2;
        private const double W_AUCTION        = 12.6;
        private const double W_POC            = 0.0;

        // -------------------------------------------------------------------------
        // Tier thresholds — verbatim from Python signal_config.py ScorerConfig lines 195–198
        // -------------------------------------------------------------------------
        private const double TYPE_A_MIN = 80.0;
        private const double TYPE_B_MIN = 72.0;
        private const double TYPE_C_MIN = 50.0;

        // -------------------------------------------------------------------------
        // Confluence multiplier threshold — cat_count >= 5 → 1.25x (SCOR-02)
        // -------------------------------------------------------------------------
        private const int    CONFLUENCE_THRESHOLD = 5;
        private const double CONFLUENCE_MULT      = 1.25;

        // -------------------------------------------------------------------------
        // IB (Initial Balance) multiplier — bars 0–59 get 1.15x boost
        // -------------------------------------------------------------------------
        private const double IB_MULT    = 1.15;
        private const int    IB_BAR_END = 60;  // exclusive

        // -------------------------------------------------------------------------
        // Midday block — bars 240–330 (10:30–13:00 ET RTH) forced QUIET
        // Forensic finding: accumulated -$1,622 across 25 days (Python scorer.py lines 493–496)
        // -------------------------------------------------------------------------
        private const int MIDDAY_START = 240;
        private const int MIDDAY_END   = 330;

        // -------------------------------------------------------------------------
        // TypeA veto gates
        // -------------------------------------------------------------------------
        private const int  TRAP_VETO_COUNT = 3;   // >= 3 trap signals veto TypeA
        private const long DELTA_CHASE_MAG = 50L; // |barDelta| > 50 same-dir = chase, veto TypeA

        // -------------------------------------------------------------------------
        // Zone bonus tiers — verbatim from Python signal_config.py ScorerConfig lines 203–209
        // -------------------------------------------------------------------------
        private const double ZONE_HIGH_MIN   = 50.0;
        private const double ZONE_HIGH_BONUS = 8.0;
        private const double ZONE_MID_MIN    = 30.0;
        private const double ZONE_MID_BONUS  = 6.0;
        private const double ZONE_NEAR_BONUS = 4.0;
        private const double ZONE_NEAR_TICKS = 0.5;

        // -------------------------------------------------------------------------
        // Minimum strength gate for TypeB / TypeC
        // -------------------------------------------------------------------------
        private const double MIN_STRENGTH = 0.3;

        /// <summary>
        /// Score a bar using two-layer confluence. Verbatim port of Python score_bar().
        /// </summary>
        /// <param name="signals">All SignalResult[] returned by DetectorRegistry.EvaluateBar() for this bar.</param>
        /// <param name="barsSinceOpen">Bar index within RTH session (0 = first bar at 9:30).</param>
        /// <param name="barDelta">Current bar's net delta (positive=buyers, negative=sellers).</param>
        /// <param name="barClose">Current bar close price.</param>
        /// <param name="zoneScore">Active zone score (0–100). Default 0 → no zone bonus.</param>
        /// <param name="zoneDistTicks">Distance from bar close to nearest zone edge in ticks. Default MaxValue.</param>
        /// <param name="tickSize">Instrument tick size (e.g. 0.25 for NQ). Default 0.25.</param>
        /// <param name="gexAbsMult">GEX multiplier for absorption/exhaustion weight. Default 1.0.</param>
        /// <param name="gexMomentumMult">GEX multiplier for delta/imbalance weight. Default 1.0.</param>
        /// <param name="gexNearWallBonus">Bonus points when near GEX wall and direction aligns. Default 0.0.</param>
        /// <param name="vpinModifier">VPIN flow-toxicity modifier, final stage before clip. Default 1.0.</param>
        public static ScorerResult Score(
            SR[]   signals,
            int    barsSinceOpen,
            long   barDelta,
            double barClose,
            double zoneScore        = 0.0,
            double zoneDistTicks    = double.MaxValue,
            double tickSize         = 0.25,
            double gexAbsMult       = 1.0,
            double gexMomentumMult  = 1.0,
            double gexNearWallBonus = 0.0,
            double vpinModifier     = 1.0)
        {
            // ----------------------------------------------------------------
            // Layer 1: Directional vote resolution
            // ----------------------------------------------------------------
            double bullWeightSum = 0.0;
            double bearWeightSum = 0.0;

            var categoriesBull = new HashSet<string>(System.StringComparer.Ordinal);
            var categoriesBear = new HashSet<string>(System.StringComparer.Ordinal);

            // Stacked imbalance dedup (D-02)
            int stackedBullTier = 0;
            int stackedBearTier = 0;

            double maxBullStrength = 0.0;
            double maxBearStrength = 0.0;

            if (signals != null)
            {
                foreach (var r in signals)
                {
                    if (r == null || r.Direction == 0) continue;

                    string id = r.SignalId ?? string.Empty;

                    // ---- Absorption (ABS-*) ----
                    if (id.StartsWith("ABS", System.StringComparison.Ordinal))
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("absorption");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("absorption");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // ---- Exhaustion (EXH-*) ----
                    if (id.StartsWith("EXH", System.StringComparison.Ordinal))
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("exhaustion");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("exhaustion");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // ---- Trapped (TRAP-*) ----
                    if (id.StartsWith("TRAP", System.StringComparison.Ordinal))
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("trapped");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("trapped");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // ---- Imbalance stacked (IMB-*) — dedup by highest tier (D-02) ----
                    if (id.StartsWith("IMB", System.StringComparison.Ordinal))
                    {
                        int stackTier = ExtractStackedTier(id, r.Detail);
                        if (stackTier > 0)
                        {
                            if (r.Direction > 0)
                            {
                                maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                                stackedBullTier = System.Math.Max(stackedBullTier, stackTier);
                            }
                            else
                            {
                                maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                                stackedBearTier = System.Math.Max(stackedBearTier, stackTier);
                            }
                        }
                        continue;
                    }

                    // ---- Delta — only DELT-04/05/06/08/10 vote ----
                    if (id == "DELT-04" || id == "DELT-05" || id == "DELT-06" || id == "DELT-08" || id == "DELT-10")
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("delta");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("delta");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // ---- Auction — only AUCT-01/02/05 vote ----
                    if (id == "AUCT-01" || id == "AUCT-02" || id == "AUCT-05")
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("auction");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("auction");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // ---- POC — only POC-02/07/08 vote ----
                    if (id == "POC-02" || id == "POC-07" || id == "POC-08")
                    {
                        if (r.Direction > 0)
                        {
                            bullWeightSum += r.Strength;
                            categoriesBull.Add("poc");
                            maxBullStrength = System.Math.Max(maxBullStrength, r.Strength);
                        }
                        else
                        {
                            bearWeightSum += r.Strength;
                            categoriesBear.Add("poc");
                            maxBearStrength = System.Math.Max(maxBearStrength, r.Strength);
                        }
                        continue;
                    }

                    // All other IDs: no category vote
                }
            }

            // D-02: resolve stacked imbalance dedup — one vote per direction, highest tier wins
            if (stackedBullTier > 0) { bullWeightSum += 0.5; categoriesBull.Add("imbalance"); }
            if (stackedBearTier > 0) { bearWeightSum += 0.5; categoriesBear.Add("imbalance"); }

            // Determine dominant direction by weighted strength sum
            int    direction;
            double agreement;
            HashSet<string> categoriesAgreeing;
            double maxDominantStrength;

            if (bullWeightSum > bearWeightSum)
            {
                direction = +1;
                int bullVotes = CountSideVotes(signals, +1, stackedBullTier);
                int bearVotes = CountSideVotes(signals, -1, stackedBearTier);
                int total     = bullVotes + bearVotes;
                agreement           = total > 0 ? (double)bullVotes / total : 0.0;
                categoriesAgreeing  = categoriesBull;
                maxDominantStrength = maxBullStrength;
            }
            else if (bearWeightSum > bullWeightSum)
            {
                direction = -1;
                int bullVotes = CountSideVotes(signals, +1, stackedBullTier);
                int bearVotes = CountSideVotes(signals, -1, stackedBearTier);
                int total     = bullVotes + bearVotes;
                agreement           = total > 0 ? (double)bearVotes / total : 0.0;
                categoriesAgreeing  = categoriesBear;
                maxDominantStrength = maxBearStrength;
            }
            else
            {
                direction           = 0;
                agreement           = 0.0;
                categoriesAgreeing  = new HashSet<string>(System.StringComparer.Ordinal);
                maxDominantStrength = 0.0;
            }

            // ----------------------------------------------------------------
            // Delta-direction agreement gate (Python scorer.py lines 299–302)
            // ----------------------------------------------------------------
            bool deltaAgrees = true;
            if (barDelta != 0 && direction != 0)
            {
                if ((direction > 0 && barDelta < 0) || (direction < 0 && barDelta > 0))
                    deltaAgrees = false;
            }

            // ----------------------------------------------------------------
            // IB multiplier — first 60 bars of session
            // ----------------------------------------------------------------
            double ibMult = (barsSinceOpen >= 0 && barsSinceOpen < IB_BAR_END) ? IB_MULT : 1.0;

            // ----------------------------------------------------------------
            // Layer 2: Zone proximity → "volume_profile" category (SCOR-03)
            // Phase 18: scalar zoneScore interface (vs Python's active_zones list).
            // Logic mirrors Python scorer.py lines 379–399.
            // ----------------------------------------------------------------
            double zoneBonus = 0.0;

            if (zoneScore >= ZONE_HIGH_MIN)
            {
                if (zoneDistTicks <= ZONE_NEAR_TICKS)
                {
                    // Near zone edge + high score → near bonus (+4)
                    zoneBonus = ZONE_NEAR_BONUS;
                }
                else
                {
                    // Inside high-score zone → high bonus (+8)
                    zoneBonus = ZONE_HIGH_BONUS;
                }
                categoriesAgreeing.Add("volume_profile");
            }
            else if (zoneScore >= ZONE_MID_MIN)
            {
                zoneBonus = ZONE_MID_BONUS;
                categoriesAgreeing.Add("volume_profile");
            }

            int catCount = categoriesAgreeing.Count;

            // ----------------------------------------------------------------
            // Confluence multiplier (SCOR-02)
            // ----------------------------------------------------------------
            double confluenceMult = catCount >= CONFLUENCE_THRESHOLD ? CONFLUENCE_MULT : 1.0;

            // ----------------------------------------------------------------
            // Base score: sum of category weights with GEX modifiers applied
            // ----------------------------------------------------------------
            double baseScore = 0.0;
            foreach (var cat in categoriesAgreeing)
            {
                double weight = CategoryWeight(cat);
                if (cat == "absorption" || cat == "exhaustion")
                    weight *= gexAbsMult;
                else if (cat == "delta" || cat == "imbalance")
                    weight *= gexMomentumMult;
                baseScore += weight;
            }

            // ----------------------------------------------------------------
            // Formula (verbatim Python scorer.py line 421):
            // total_score = min((base * confluence_mult + zone_bonus + gex_near_wall) * agreement * ib_mult, 100)
            // ----------------------------------------------------------------
            double totalScore = System.Math.Min(
                (baseScore * confluenceMult + zoneBonus + gexNearWallBonus) * agreement * ibMult,
                100.0);

            // D-01: Confirmation bonus — ABS-06 confirmed absorptions
            // Phase 18: default 0 confirmed absorptions; wired when ABS-06 port completes.

            // VPIN final stage (phase 12-01, locked order — SEPARATE from ib_mult)
            totalScore *= vpinModifier;
            totalScore  = System.Math.Max(0.0, System.Math.Min(100.0, totalScore));

            // ----------------------------------------------------------------
            // Tier classification (SCOR-04)
            // Verbatim from Python scorer.py lines 472–488
            // ----------------------------------------------------------------
            bool hasAbsorption = categoriesAgreeing.Contains("absorption");
            bool hasExhaustion = categoriesAgreeing.Contains("exhaustion");
            bool hasZone       = zoneBonus > 0.0;
            bool minStrength   = maxDominantStrength >= MIN_STRENGTH;

            // Trap veto: >= 3 trap signals veto TypeA (Python scorer.py lines 444–445)
            int trapCount = 0;
            if (signals != null)
                foreach (var r in signals)
                    if (r != null && r.SignalId != null && r.SignalId.StartsWith("TRAP", System.StringComparison.Ordinal))
                        trapCount++;
            bool trapVeto = trapCount >= TRAP_VETO_COUNT;

            // Delta chase: large same-direction delta blocks TypeA (Python scorer.py lines 450–459)
            bool deltaChase = false;
            if (barDelta != 0 && direction != 0)
            {
                long deltaMag = System.Math.Abs(barDelta);
                if (deltaMag > DELTA_CHASE_MAG)
                {
                    if ((direction > 0 && barDelta > 0) || (direction < 0 && barDelta < 0))
                        deltaChase = true;
                }
            }

            SignalTier tier;

            if (totalScore >= TYPE_A_MIN
                && (hasAbsorption || hasExhaustion)
                && hasZone
                && catCount >= 5
                && deltaAgrees
                && !trapVeto
                && !deltaChase)
            {
                tier = SignalTier.TYPE_A;
            }
            else if (totalScore >= TYPE_B_MIN
                     && catCount >= 4
                     && deltaAgrees
                     && minStrength)
            {
                tier = SignalTier.TYPE_B;
            }
            else if (totalScore >= TYPE_C_MIN
                     && catCount >= 4   // NOTE: Python scorer.py line 485 uses >= 4, NOT 3 per docstring (Pitfall 1)
                     && minStrength)
            {
                tier = SignalTier.TYPE_C;
            }
            else
            {
                tier = SignalTier.QUIET;
            }

            // ----------------------------------------------------------------
            // Midday block (scorer.py lines 493–496):
            // Bars 240–330 forced QUIET. DISQUALIFIED takes priority.
            // ----------------------------------------------------------------
            if (tier != SignalTier.DISQUALIFIED
                && barsSinceOpen >= MIDDAY_START
                && barsSinceOpen <= MIDDAY_END)
            {
                tier = SignalTier.QUIET;
            }

            // ----------------------------------------------------------------
            // EntryPrice: dominant ABS/EXH signal's Price (nonzero) or barClose fallback
            // ----------------------------------------------------------------
            double entryPrice = 0.0;
            if (signals != null)
            {
                foreach (var r in signals)
                {
                    if (r == null || r.Direction != direction || r.Price == 0.0) continue;
                    string eid = r.SignalId ?? string.Empty;
                    if (eid.StartsWith("ABS", System.StringComparison.Ordinal)
                        || eid.StartsWith("EXH", System.StringComparison.Ordinal))
                    {
                        entryPrice = r.Price;
                        break;
                    }
                }
            }
            if (entryPrice == 0.0)
                entryPrice = barClose;

            // ----------------------------------------------------------------
            // Build result
            // ----------------------------------------------------------------
            var result = new ScorerResult
            {
                TotalScore      = totalScore,
                Tier            = tier,
                Direction       = direction,
                EngineAgreement = agreement,
                CategoryCount   = catCount,
                ConfluenceMult  = confluenceMult,
                ZoneBonus       = zoneBonus,
                EntryPrice      = entryPrice,
                CategoriesFiring = SortedCategories(categoriesAgreeing),
            };

            result.Narrative = NarrativeCascade.BuildLabel(result, signals);

            return result;
        }

        // -------------------------------------------------------------------------
        // Helper: extract stacked imbalance tier from signal ID suffix or detail string
        // Phase 17 convention: ID suffix "-T3"/"-T2"/"-T1" or Detail "STACKED_T3" etc.
        // -------------------------------------------------------------------------
        private static int ExtractStackedTier(string signalId, string detail)
        {
            if (signalId != null)
            {
                if (signalId.EndsWith("-T3", System.StringComparison.OrdinalIgnoreCase)) return 3;
                if (signalId.EndsWith("-T2", System.StringComparison.OrdinalIgnoreCase)) return 2;
                if (signalId.EndsWith("-T1", System.StringComparison.OrdinalIgnoreCase)) return 1;
            }
            if (detail != null)
            {
                // ImbalanceDetector emits: "STACKED BUY x3 (T3) at 19500.00" — match (T3)/(T2)/(T1)
                if (detail.IndexOf("(T3)", System.StringComparison.OrdinalIgnoreCase) >= 0) return 3;
                if (detail.IndexOf("(T2)", System.StringComparison.OrdinalIgnoreCase) >= 0) return 2;
                if (detail.IndexOf("(T1)", System.StringComparison.OrdinalIgnoreCase) >= 0) return 1;
            }
            return 0;
        }

        // -------------------------------------------------------------------------
        // Helper: count raw directional vote-contributing signals for agreement ratio.
        // Mirrors Python's raw vote count (not weighted sum) for the agreement fraction.
        // -------------------------------------------------------------------------
        private static int CountSideVotes(SR[] signals, int direction, int stackedTier)
        {
            int count = 0;
            if (signals != null)
            {
                foreach (var r in signals)
                {
                    if (r == null || r.Direction != direction) continue;
                    string id = r.SignalId ?? string.Empty;
                    if (id.StartsWith("ABS",  System.StringComparison.Ordinal)) { count++; continue; }
                    if (id.StartsWith("EXH",  System.StringComparison.Ordinal)) { count++; continue; }
                    if (id.StartsWith("TRAP", System.StringComparison.Ordinal)) { count++; continue; }
                    if (id == "DELT-04" || id == "DELT-05" || id == "DELT-06" || id == "DELT-08" || id == "DELT-10") { count++; continue; }
                    if (id == "AUCT-01" || id == "AUCT-02" || id == "AUCT-05") { count++; continue; }
                    if (id == "POC-02"  || id == "POC-07"  || id == "POC-08")  { count++; continue; }
                }
            }
            // One imbalance vote if any stacked tier exists for this direction
            if (stackedTier > 0) count++;
            return count;
        }

        // -------------------------------------------------------------------------
        // Helper: lookup category weight (verbatim Python values)
        // -------------------------------------------------------------------------
        private static double CategoryWeight(string cat)
        {
            switch (cat)
            {
                case "absorption":     return W_ABSORPTION;
                case "exhaustion":     return W_EXHAUSTION;
                case "trapped":        return W_TRAPPED;
                case "delta":          return W_DELTA;
                case "imbalance":      return W_IMBALANCE;
                case "volume_profile": return W_VOLUME_PROFILE;
                case "auction":        return W_AUCTION;
                case "poc":            return W_POC;
                default:               return 5.0;  // unknown category fallback (Python default)
            }
        }

        // -------------------------------------------------------------------------
        // Helper: sorted array of category names (Python: sorted(categories_agreeing))
        // -------------------------------------------------------------------------
        private static string[] SortedCategories(HashSet<string> cats)
        {
            var arr = new string[cats.Count];
            int i   = 0;
            foreach (var c in cats) arr[i++] = c;
            System.Array.Sort(arr, System.StringComparer.Ordinal);
            return arr;
        }
    }
}
