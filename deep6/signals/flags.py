"""SignalFlags: 44-bit IntFlag covering all DEEP6 signals.

Per ARCH-05: int64 bitmask for O(popcount) scoring.
Bit positions are STABLE — do not reorder once committed (would break serialized state).

Signal groups and bit allocations (44 total):
  ABS  (Absorption):        bits  0-3   (4 signals: ABS-01..04)
  EXH  (Exhaustion):        bits  4-11  (8 signals: EXH-01..08)
  IMB  (Imbalance):         bits 12-20  (9 signals: IMB-01..09)
  DELT (Delta):             bits 21-31  (11 signals: DELT-01..11)
  AUCT (Auction Theory):    bits 32-36  (5 signals: AUCT-01..05)
  TRAP (Trapped Traders):   bits 37-41  (5 signals: TRAP-01..05)
  VOLP (Volume Patterns):   bits 42-43  (2 signals: VOLP-01..02; VOLP-03..06 reserved Phase 4+)

Total: 4 + 8 + 9 + 11 + 5 + 5 + 2 = 44 signal bits
Highest bit: 1 << 43 — fits comfortably in int64 (max 1 << 63).

Implementation phases per REQUIREMENTS.md:
  Phase 2: ABS, EXH
  Phase 3: IMB, DELT, AUCT
  Phase 4: TRAP, VOLP-01..02
  Phase 5+: VOLP-03..06 (reserved, not yet defined)

Bit positions are reserved here even for later phases to ensure stable serialization.
"""
from enum import IntFlag


class SignalFlags(IntFlag):
    NONE = 0

    # -----------------------------------------------------------------------
    # Absorption (ABS-01..04) — Phase 2
    # Classic footprint absorption patterns at price extremes
    # -----------------------------------------------------------------------
    ABS_CLASSIC     = 1 << 0   # ABS-01: wick volume + balanced delta (classic absorption)
    ABS_PASSIVE     = 1 << 1   # ABS-02: high volume at price extreme (passive absorption)
    ABS_STOPPING    = 1 << 2   # ABS-03: POC in wick + ATR volume threshold (stopping volume)
    ABS_EFFORT_VS_R = 1 << 3   # ABS-04: vol > 1.5x ATR, range < 30% ATR (effort vs result)

    # -----------------------------------------------------------------------
    # Exhaustion (EXH-01..08) — Phase 2
    # Volume-based exhaustion signals at bar extremes
    # -----------------------------------------------------------------------
    EXH_ZERO_PRINT  = 1 << 4   # EXH-01: price level with 0 vol bid+ask (zero print)
    EXH_EXHAUSTION  = 1 << 5   # EXH-02: high single-side vol, no follow-through
    EXH_THIN_PRINT  = 1 << 6   # EXH-03: vol < 5% of max row vol in bar body (thin print)
    EXH_FAT_PRINT   = 1 << 7   # EXH-04: vol > threshold x avg row vol (fat print)
    EXH_FADING_MOM  = 1 << 8   # EXH-05: CVD 3-bar regression diverges from price
    EXH_BID_ASK_FD  = 1 << 9   # EXH-06: ask vol at extreme < 60% prior bar (bid/ask fade)
    EXH_DELTA_GATE  = 1 << 10  # EXH-07: delta trajectory divergence gate
    EXH_COOLDOWN    = 1 << 11  # EXH-08: cooldown suppression active (prevents signal spam)

    # -----------------------------------------------------------------------
    # Imbalance (IMB-01..09) — Phase 3
    # Bid/ask volume imbalance patterns across price levels
    # -----------------------------------------------------------------------
    IMB_SINGLE      = 1 << 12  # IMB-01: single imbalance >= 300% at one level
    IMB_MULTIPLE    = 1 << 13  # IMB-02: 3+ imbalances at the same price
    IMB_STACKED     = 1 << 14  # IMB-03: T1/T2/T3 consecutive level stacking
    IMB_REVERSE     = 1 << 15  # IMB-04: opposite direction imbalance within bar
    IMB_INVERSE     = 1 << 16  # IMB-05: buy imbalance in red bar / sell imb in green bar
    IMB_OVERSIZED   = 1 << 17  # IMB-06: 10:1+ ratio at single level (extreme imbalance)
    IMB_CONSECUTIVE = 1 << 18  # IMB-07: same imbalance level across multiple consecutive bars
    IMB_DIAGONAL    = 1 << 19  # IMB-08: ask[P] vs bid[P-1] diagonal imbalance
    IMB_REVERSAL_PT = 1 << 20  # IMB-09: direction change in bar sequence imbalance pattern

    # -----------------------------------------------------------------------
    # Delta (DELT-01..11) — Phase 3
    # Cumulative delta and intrabar delta patterns
    # -----------------------------------------------------------------------
    DELT_RISE_DROP  = 1 << 21  # DELT-01: delta rises then drops within bar (rise-drop)
    DELT_TAIL       = 1 << 22  # DELT-02: delta closes at 95%+ of its extreme (delta tail)
    DELT_REVERSAL   = 1 << 23  # DELT-03: intrabar delta flip (sign change mid-bar)
    DELT_DIVERGENCE = 1 << 24  # DELT-04: price new high/low but delta fails to confirm
    DELT_FLIP       = 1 << 25  # DELT-05: sign change in cumulative delta (CVD flip)
    DELT_TRAP       = 1 << 26  # DELT-06: aggressive delta followed by price reversal
    DELT_SWEEP      = 1 << 27  # DELT-07: rapid accumulation across multiple levels
    DELT_SLINGSHOT  = 1 << 28  # DELT-08: compressed delta then explosive expansion
    DELT_MIN_MAX    = 1 << 29  # DELT-09: delta at session minimum or maximum
    DELT_CVD_DIVG   = 1 << 30  # DELT-10: CVD polyfit divergence over 5-20 bar window
    DELT_VELOCITY   = 1 << 31  # DELT-11: rate of change of cumulative delta (CVD velocity)

    # -----------------------------------------------------------------------
    # Auction Theory (AUCT-01..05) — Phase 3
    # Market profile and auction completion signals
    # -----------------------------------------------------------------------
    AUCT_UNFINISHED = 1 << 32  # AUCT-01: non-zero bid at high / ask at low (unfinished auction)
    AUCT_FINISHED   = 1 << 33  # AUCT-02: zero vol at extreme (auction finished)
    AUCT_POOR_HILOW = 1 << 34  # AUCT-03: single-print extreme (poor high or poor low)
    AUCT_VOL_VOID   = 1 << 35  # AUCT-04: LVN gap within bar (volume void)
    AUCT_MKT_SWEEP  = 1 << 36  # AUCT-05: rapid traversal + increasing vol (market sweep)

    # -----------------------------------------------------------------------
    # Trapped Traders (TRAP-01..05) — Phase 4
    # Patterns identifying traders caught on wrong side
    # -----------------------------------------------------------------------
    TRAP_INVERSE_I  = 1 << 37  # TRAP-01: stacked buy imbalance in red bar (trapped buyers)
    TRAP_DELTA      = 1 << 38  # TRAP-02: strong delta + price failure (delta trap)
    TRAP_FALSE_BRK  = 1 << 39  # TRAP-03: break + stop-trigger + reversal (false breakout)
    TRAP_HIVOL_REJ  = 1 << 40  # TRAP-04: record volume + immediate rejection
    TRAP_CVD        = 1 << 41  # TRAP-05: CVD trend reversal (trapped via CVD divergence)

    # -----------------------------------------------------------------------
    # Volume Patterns (VOLP-01..02) — Phase 4
    # VOLP-03..06 reserved for Phase 5+ (bits 44-47 would be used)
    # -----------------------------------------------------------------------
    VOLP_SEQUENCING = 1 << 42  # VOLP-01: institutional accumulation/distribution pattern
    VOLP_BUBBLE     = 1 << 43  # VOLP-02: isolated high-volume price level (volume bubble)
