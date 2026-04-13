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
    assert max_val <= (1 << 43), "Highest flag exceeds reserved 44-bit range"


def test_flag_count():
    non_none_flags = [f for f in SignalFlags if f != SignalFlags.NONE]
    assert len(non_none_flags) == 44, f"Expected 44 signal flags, got {len(non_none_flags)}"
