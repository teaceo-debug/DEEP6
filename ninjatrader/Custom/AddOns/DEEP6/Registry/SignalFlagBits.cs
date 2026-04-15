// SignalFlagBits: canonical 64-bit ulong bit assignments for all 44 DEEP6 signals + meta-flags.
//
// Python reference: deep6/signals/flags.py (SignalFlags IntFlag, bits 0-47)
//   Bits 0-44 in Python; C# extends to bits 48-57 for VOLP-03..06 and ENG-02..07.
//   This file is the AUTHORITATIVE bit table for the C# registry. Do not reorder
//   any bit after it is committed — would break serialized state.
//
// Bit assignment table (from RESEARCH.md §SignalFlags Bit Assignment for New Families):
//   Bits 0-3:   ABS-01..04     (Absorption)
//   Bits 4-11:  EXH-01..08     (Exhaustion)
//   Bits 12-20: IMB-01..09     (Imbalance)
//   Bits 21-31: DELT-01..11    (Delta)
//   Bits 32-36: AUCT-01..05    (Auction Theory)
//   Bits 37-41: TRAP-01..05    (Trapped Traders)
//   Bits 42-43: VOLP-01..02    (Volume Patterns)
//   Bit  44:    TRAP_SHOT      (Phase 12 — multi-bar trapped reversal)
//   Bits 45-47: META-FLAGS     (PIN_REGIME, REGIME_CHANGE, SPOOF_VETO — reserved Phase 15)
//   Bits 48-51: VOLP-03..06    (VOLP extension — bits 44-47 taken by TRAP_SHOT + META)
//   Bits 52-57: ENG-02..07     (Engine signals)
//
// CRITICAL: No NinjaTrader.* using directives.

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    /// <summary>
    /// Canonical bit assignments for SignalFlags ulong. Use Mask(bit) to produce
    /// the single-bit mask for SignalResult.FlagBit.
    ///
    /// Python reference: deep6/signals/flags.py SignalFlags
    /// Bits 0-44 match Python 1:1. Bits 48-57 are C# extensions for signals
    /// that didn't fit in the Python 45-bit layout.
    /// </summary>
    public static class SignalFlagBits
    {
        // -----------------------------------------------------------------------
        // Absorption (ABS-01..04) — Phase 2
        // Python ref: deep6/signals/flags.py bits 0-3
        // -----------------------------------------------------------------------
        /// <summary>ABS-01: Classic absorption — wick vol + balanced delta at price extreme.</summary>
        public const int ABS_01 = 0;
        /// <summary>ABS-02: Passive absorption — high vol at extreme while price holds.</summary>
        public const int ABS_02 = 1;
        /// <summary>ABS-03: Stopping volume — POC in wick + ATR-scaled vol threshold.</summary>
        public const int ABS_03 = 2;
        /// <summary>ABS-04: Effort vs Result — high vol + narrow range.</summary>
        public const int ABS_04 = 3;

        // -----------------------------------------------------------------------
        // Exhaustion (EXH-01..08) — Phase 2
        // Python ref: deep6/signals/flags.py bits 4-11
        // -----------------------------------------------------------------------
        /// <summary>EXH-01: Zero print — price level with 0 vol bid+ask (gate-exempt).</summary>
        public const int EXH_01 = 4;
        /// <summary>EXH-02: Exhaustion print — high single-side vol at extreme.</summary>
        public const int EXH_02 = 5;
        /// <summary>EXH-03: Thin print — vol &lt; 5% of max row vol in bar body.</summary>
        public const int EXH_03 = 6;
        /// <summary>EXH-04: Fat print — vol &gt; threshold × avg row vol.</summary>
        public const int EXH_04 = 7;
        /// <summary>EXH-05: Fading momentum — delta trajectory diverges from price.</summary>
        public const int EXH_05 = 8;
        /// <summary>EXH-06: Bid/ask fade — ask vol at extreme &lt; 60% of prior bar.</summary>
        public const int EXH_06 = 9;
        /// <summary>EXH-07: Delta gate — delta trajectory divergence (universal gate for EXH-02..06).</summary>
        public const int EXH_07 = 10;
        /// <summary>EXH-08: Cooldown suppression active (prevents signal spam).</summary>
        public const int EXH_08 = 11;

        // -----------------------------------------------------------------------
        // Imbalance (IMB-01..09) — Phase 3
        // Python ref: deep6/signals/flags.py bits 12-20
        // -----------------------------------------------------------------------
        /// <summary>IMB-01: Single imbalance &gt;= 300% at one level.</summary>
        public const int IMB_01 = 12;
        /// <summary>IMB-02: Multiple imbalance — 3+ at the same price.</summary>
        public const int IMB_02 = 13;
        /// <summary>IMB-03: Stacked T1/T2/T3 — 3/5/7 consecutive levels.</summary>
        public const int IMB_03 = 14;
        /// <summary>IMB-04: Reverse imbalance — both buy_imb and sell_imb in same bar.</summary>
        public const int IMB_04 = 15;
        /// <summary>IMB-05: Inverse imbalance — buy imb in red bar (trapped buyers).</summary>
        public const int IMB_05 = 16;
        /// <summary>IMB-06: Oversized imbalance — 10:1+ ratio at single level.</summary>
        public const int IMB_06 = 17;
        /// <summary>IMB-07: Consecutive imbalance — same imbalance level across consecutive bars.</summary>
        public const int IMB_07 = 18;
        /// <summary>IMB-08: Diagonal imbalance — ask[P] vs bid[P-1].</summary>
        public const int IMB_08 = 19;
        /// <summary>IMB-09: Reversal imbalance pattern — direction change in bar sequence.</summary>
        public const int IMB_09 = 20;

        // -----------------------------------------------------------------------
        // Delta (DELT-01..11) — Phase 3
        // Python ref: deep6/signals/flags.py bits 21-31
        // -----------------------------------------------------------------------
        /// <summary>DELT-01: Delta rise/drop — delta rises then drops within bar.</summary>
        public const int DELT_01 = 21;
        /// <summary>DELT-02: Delta tail — delta closes at 95%+ of its extreme.</summary>
        public const int DELT_02 = 22;
        /// <summary>DELT-03: Delta reversal — intrabar delta flip (sign change mid-bar).</summary>
        public const int DELT_03 = 23;
        /// <summary>DELT-04: Delta divergence — price new high/low but delta fails to confirm.</summary>
        public const int DELT_04 = 24;
        /// <summary>DELT-05: CVD flip — sign change in cumulative delta.</summary>
        public const int DELT_05 = 25;
        /// <summary>DELT-06: Delta trap — aggressive delta followed by price reversal.</summary>
        public const int DELT_06 = 26;
        /// <summary>DELT-07: Delta sweep — rapid accumulation across multiple levels.</summary>
        public const int DELT_07 = 27;
        /// <summary>DELT-08: Delta slingshot — compressed delta then explosive expansion.</summary>
        public const int DELT_08 = 28;
        /// <summary>DELT-09: Delta at session min/max.</summary>
        public const int DELT_09 = 29;
        /// <summary>DELT-10: CVD polyfit divergence over 5-20 bar window.</summary>
        public const int DELT_10 = 30;
        /// <summary>DELT-11: Delta velocity — rate of change of CVD.</summary>
        public const int DELT_11 = 31;

        // -----------------------------------------------------------------------
        // Auction Theory (AUCT-01..05) — Phase 3
        // Python ref: deep6/signals/flags.py bits 32-36
        // -----------------------------------------------------------------------
        /// <summary>AUCT-01: Unfinished auction — non-zero bid at high / ask at low.</summary>
        public const int AUCT_01 = 32;
        /// <summary>AUCT-02: Finished auction — zero vol at extreme.</summary>
        public const int AUCT_02 = 33;
        /// <summary>AUCT-03: Poor high/low — single-print extreme.</summary>
        public const int AUCT_03 = 34;
        /// <summary>AUCT-04: Volume void — LVN gap within bar.</summary>
        public const int AUCT_04 = 35;
        /// <summary>AUCT-05: Market sweep — rapid traversal + increasing vol.</summary>
        public const int AUCT_05 = 36;

        // -----------------------------------------------------------------------
        // Trapped Traders (TRAP-01..05) — Phase 4
        // Python ref: deep6/signals/flags.py bits 37-41
        // -----------------------------------------------------------------------
        /// <summary>TRAP-01: Inverse imbalance trap — stacked buy imbalance in red bar.</summary>
        public const int TRAP_01 = 37;
        /// <summary>TRAP-02: Delta trap — strong delta + price failure.</summary>
        public const int TRAP_02 = 38;
        /// <summary>TRAP-03: False breakout trap — break + stop-trigger + reversal.</summary>
        public const int TRAP_03 = 39;
        /// <summary>TRAP-04: High volume rejection — record volume + immediate rejection.</summary>
        public const int TRAP_04 = 40;
        /// <summary>TRAP-05: CVD trend reversal trap (polyfit).</summary>
        public const int TRAP_05 = 41;

        // -----------------------------------------------------------------------
        // Volume Patterns (VOLP-01..02) — Phase 4
        // Python ref: deep6/signals/flags.py bits 42-43
        // -----------------------------------------------------------------------
        /// <summary>VOLP-01: Volume sequencing — 3+ bars escalating institutional pattern.</summary>
        public const int VOLP_01 = 42;
        /// <summary>VOLP-02: Volume bubble — isolated high-volume price level.</summary>
        public const int VOLP_02 = 43;

        // -----------------------------------------------------------------------
        // Phase 12 addition (bit 44)
        // Python ref: deep6/signals/flags.py TRAP_SHOT = 1 << 44
        // -----------------------------------------------------------------------
        /// <summary>TRAP_SHOT: Multi-bar trapped-trader reversal (Phase 12). Keep reserved.</summary>
        public const int TRAP_SHOT = 44;

        // -----------------------------------------------------------------------
        // Phase 15 Meta-flags (bits 45-47) — NOT signal bits
        // Python ref: deep6/signals/flags.py PIN_REGIME_ACTIVE / REGIME_CHANGE / SPOOF_VETO
        // These describe regime/veto state; must be masked off before popcount-based scoring.
        // -----------------------------------------------------------------------
        /// <summary>META: VPOC pinned near largest-gamma strike (PIN_REGIME_ACTIVE).</summary>
        public const int META_PIN_REGIME     = 45;
        /// <summary>META: GEX regime transitioned this bar (REGIME_CHANGE).</summary>
        public const int META_REGIME_CHANGE  = 46;
        /// <summary>META: Spoofing detected — scorer forces DISQUALIFIED (SPOOF_VETO).</summary>
        public const int META_SPOOF_VETO     = 47;

        // -----------------------------------------------------------------------
        // VOLP extension (bits 48-51) — C# only; fits in ulong but not Python int64
        // Python flags.py comment: "VOLP-03..06 reserved Phase 4+; bits 44-47 would be used"
        // TRAP_SHOT (44) + META (45-47) took those slots; shifted to 48-51.
        // -----------------------------------------------------------------------
        /// <summary>VOLP-03: Volume surge — &gt; 3× vol_ema (C# extension, bit 48).</summary>
        public const int VOLP_03 = 48;
        /// <summary>VOLP-04: POC momentum wave — POC migrating direction (C# extension, bit 49).</summary>
        public const int VOLP_04 = 49;
        /// <summary>VOLP-05: Delta velocity spike — delta acceleration (C# extension, bit 50).</summary>
        public const int VOLP_05 = 50;
        /// <summary>VOLP-06: Big delta per level — single level dominant delta (C# extension, bit 51).</summary>
        public const int VOLP_06 = 51;

        // -----------------------------------------------------------------------
        // Engine signals (bits 52-57) — C# only; ported from Python ENG family
        // Python ref: deep6/engines/trespass.py (ENG-02), counter_spoof.py (ENG-03),
        //   iceberg.py (ENG-04), micro_prob.py (ENG-05), vp_context_engine.py (ENG-06),
        //   signal_config.py (ENG-07)
        // -----------------------------------------------------------------------
        /// <summary>ENG-02: Trespass — weighted DOM queue imbalance + logistic approx (bit 52).</summary>
        public const int ENG_02 = 52;
        /// <summary>ENG-03: CounterSpoof — Wasserstein-1 DOM + large-order cancel detection (bit 53).</summary>
        public const int ENG_03 = 53;
        /// <summary>ENG-04: Iceberg — native fill &gt; DOM + synthetic refill &lt; 250ms (bit 54).</summary>
        public const int ENG_04 = 54;
        /// <summary>ENG-05: MicroEngine — Naïve Bayes micro probability (bit 55).</summary>
        public const int ENG_05 = 55;
        /// <summary>ENG-06: VP+Context — POC/VWAP/IB/GEX/ZoneRegistry + LVN lifecycle (bit 56).</summary>
        public const int ENG_06 = 56;
        /// <summary>ENG-07: Signal config scaffold (bit 57).</summary>
        public const int ENG_07 = 57;

        // -----------------------------------------------------------------------
        // Helper
        // -----------------------------------------------------------------------
        /// <summary>
        /// Produce the single-bit ulong mask for a given bit position.
        /// Use for SignalResult.FlagBit: <c>FlagBit = SignalFlagBits.Mask(SignalFlagBits.ABS_01)</c>
        /// </summary>
        public static ulong Mask(int bit) => 1UL << bit;

        /// <summary>
        /// Mask covering all signal bits (0-44) — same as Python SIGNAL_BITS_MASK.
        /// Apply before popcount-based scoring to exclude META bits 45-47 and C# extensions 48+.
        /// </summary>
        public const ulong SignalBitsMask = (1UL << 45) - 1UL;
    }
}
