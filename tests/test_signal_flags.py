"""Tests for SignalFlags IntFlag bitmask — 44 signal bits.

Per ARCH-05: int64 bitmask for O(popcount) scoring.
All 44 signal bits must be:
  - Distinct powers of 2
  - Fit within int64 (highest bit <= 1 << 43)
  - Combinable via bitwise OR
"""
import pytest
from deep6.signals.flags import SignalFlags


def test_none_is_zero():
    assert SignalFlags.NONE == 0
    assert int(SignalFlags.NONE) == 0


def test_all_flags_are_powers_of_two():
    seen = set()
    for flag in SignalFlags:
        if flag == SignalFlags.NONE:
            continue
        val = int(flag)
        assert val > 0 and (val & (val - 1)) == 0, f"{flag.name} is not a power of 2: {val}"
        assert val not in seen, f"Duplicate bit value {val}"
        seen.add(val)


def test_bitmask_or_popcount():
    combined = SignalFlags.ABS_CLASSIC | SignalFlags.ABS_PASSIVE
    assert bin(int(combined)).count('1') == 2


def test_fits_in_int64():
    max_val = max(int(f) for f in SignalFlags)
    assert max_val <= (1 << 63), "Flags exceed int64 capacity"
    # Phase 12-03: TRAP_SHOT added at bit 44; highest bit is now 44.
    assert max_val <= (1 << 44), "Highest flag exceeds reserved 45-bit range"


def test_flag_count():
    non_none_flags = [f for f in SignalFlags if f != SignalFlags.NONE]
    # Phase 12-03: 44 stable bits (0-43) + TRAP_SHOT (bit 44) = 45 flags
    assert len(non_none_flags) == 45, f"Expected 45 signal flags, got {len(non_none_flags)}"


def test_trap_shot_bit_44():
    """Phase 12-03: TRAP_SHOT occupies bit 44 (first free slot)."""
    assert int(SignalFlags.TRAP_SHOT) == 1 << 44


def test_delt_slingshot_still_bit_28():
    """Phase 12-03 must NOT touch the existing DELT_SLINGSHOT (bit 28).

    DELT_SLINGSHOT is a different pattern (intra-bar compressed→explosive)
    and must remain at bit 28. TRAP_SHOT is a multi-bar trapped-trader
    reversal — see 12-CONTEXT.md for disambiguation.
    """
    assert int(SignalFlags.DELT_SLINGSHOT) == 1 << 28


def test_all_stable_bits_unchanged():
    """Bit-lock regression guard.

    Bits 0-43 are STABLE per STATE.md. This test pins every single one
    explicitly so any accidental reordering surfaces immediately.
    """
    stable = [
        # ABS (0-3)
        ("ABS_CLASSIC", 0), ("ABS_PASSIVE", 1), ("ABS_STOPPING", 2), ("ABS_EFFORT_VS_R", 3),
        # EXH (4-11)
        ("EXH_ZERO_PRINT", 4), ("EXH_EXHAUSTION", 5), ("EXH_THIN_PRINT", 6),
        ("EXH_FAT_PRINT", 7), ("EXH_FADING_MOM", 8), ("EXH_BID_ASK_FD", 9),
        ("EXH_DELTA_GATE", 10), ("EXH_COOLDOWN", 11),
        # IMB (12-20)
        ("IMB_SINGLE", 12), ("IMB_MULTIPLE", 13), ("IMB_STACKED", 14),
        ("IMB_REVERSE", 15), ("IMB_INVERSE", 16), ("IMB_OVERSIZED", 17),
        ("IMB_CONSECUTIVE", 18), ("IMB_DIAGONAL", 19), ("IMB_REVERSAL_PT", 20),
        # DELT (21-31)
        ("DELT_RISE_DROP", 21), ("DELT_TAIL", 22), ("DELT_REVERSAL", 23),
        ("DELT_DIVERGENCE", 24), ("DELT_FLIP", 25), ("DELT_TRAP", 26),
        ("DELT_SWEEP", 27), ("DELT_SLINGSHOT", 28), ("DELT_MIN_MAX", 29),
        ("DELT_CVD_DIVG", 30), ("DELT_VELOCITY", 31),
        # AUCT (32-36)
        ("AUCT_UNFINISHED", 32), ("AUCT_FINISHED", 33), ("AUCT_POOR_HILOW", 34),
        ("AUCT_VOL_VOID", 35), ("AUCT_MKT_SWEEP", 36),
        # TRAP (37-41)
        ("TRAP_INVERSE_I", 37), ("TRAP_DELTA", 38), ("TRAP_FALSE_BRK", 39),
        ("TRAP_HIVOL_REJ", 40), ("TRAP_CVD", 41),
        # VOLP (42-43)
        ("VOLP_SEQUENCING", 42), ("VOLP_BUBBLE", 43),
    ]
    for name, bit in stable:
        flag = getattr(SignalFlags, name)
        assert int(flag) == (1 << bit), (
            f"BIT LOCK VIOLATION: {name} moved from bit {bit} to {int(flag).bit_length()-1}"
        )
