from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SignalId(str, Enum):
    ABS_01 = "ABS_01"
    ABS_02 = "ABS_02"
    ABS_03 = "ABS_03"
    ABS_04 = "ABS_04"
    EXH_01 = "EXH_01"
    EXH_02 = "EXH_02"
    EXH_03 = "EXH_03"
    EXH_04 = "EXH_04"
    EXH_05 = "EXH_05"
    EXH_06 = "EXH_06"
    IMB_01 = "IMB_01"
    IMB_02 = "IMB_02"
    IMB_03 = "IMB_03"
    IMB_04 = "IMB_04"
    IMB_05 = "IMB_05"
    IMB_06 = "IMB_06"
    IMB_07 = "IMB_07"
    IMB_08 = "IMB_08"
    IMB_09 = "IMB_09"
    DELT_01 = "DELT_01"
    DELT_02 = "DELT_02"
    DELT_03 = "DELT_03"
    DELT_04 = "DELT_04"
    DELT_05 = "DELT_05"
    DELT_06 = "DELT_06"
    DELT_07 = "DELT_07"
    DELT_08 = "DELT_08"
    DELT_09 = "DELT_09"
    DELT_10 = "DELT_10"
    DELT_11 = "DELT_11"
    AUCT_01 = "AUCT_01"
    AUCT_02 = "AUCT_02"
    AUCT_03 = "AUCT_03"
    AUCT_04 = "AUCT_04"
    AUCT_05 = "AUCT_05"
    TRAP_01 = "TRAP_01"
    TRAP_02 = "TRAP_02"
    TRAP_03 = "TRAP_03"
    TRAP_04 = "TRAP_04"
    TRAP_05 = "TRAP_05"
    VOLP_01 = "VOLP_01"
    VOLP_02 = "VOLP_02"
    VOLP_03 = "VOLP_03"
    VOLP_04 = "VOLP_04"
    VOLP_05 = "VOLP_05"
    VOLP_06 = "VOLP_06"
    ENG_02 = "ENG_02"
    ENG_03 = "ENG_03"
    ENG_04 = "ENG_04"
    ENG_05 = "ENG_05"
    ENG_06 = "ENG_06"
    ENG_07 = "ENG_07"
    PIN_REGIME = "PIN_REGIME"
    REGIME_CHANGE = "REGIME_CHANGE"
    SPOOF_VETO = "SPOOF_VETO"


class SignalCategory(str, Enum):
    ABSORPTION = "absorption"
    EXHAUSTION = "exhaustion"
    IMBALANCE = "imbalance"
    DELTA = "delta"
    VOLUME_PROFILE = "volume_profile"
    AUCTION = "auction"
    TRAPPED = "trapped"
    POC = "poc"


SIGNAL_TO_CATEGORY: dict[SignalId, SignalCategory | None] = {
    SignalId.ABS_01: SignalCategory.ABSORPTION,
    SignalId.ABS_02: SignalCategory.ABSORPTION,
    SignalId.ABS_03: SignalCategory.ABSORPTION,
    SignalId.ABS_04: SignalCategory.ABSORPTION,
    SignalId.EXH_01: SignalCategory.EXHAUSTION,
    SignalId.EXH_02: SignalCategory.EXHAUSTION,
    SignalId.EXH_03: SignalCategory.EXHAUSTION,
    SignalId.EXH_04: SignalCategory.EXHAUSTION,
    SignalId.EXH_05: SignalCategory.EXHAUSTION,
    SignalId.EXH_06: SignalCategory.EXHAUSTION,
    SignalId.IMB_01: SignalCategory.IMBALANCE,
    SignalId.IMB_02: SignalCategory.IMBALANCE,
    SignalId.IMB_03: SignalCategory.IMBALANCE,
    SignalId.IMB_04: SignalCategory.IMBALANCE,
    SignalId.IMB_05: SignalCategory.IMBALANCE,
    SignalId.IMB_06: SignalCategory.IMBALANCE,
    SignalId.IMB_07: SignalCategory.IMBALANCE,
    SignalId.IMB_08: SignalCategory.IMBALANCE,
    SignalId.IMB_09: SignalCategory.IMBALANCE,
    SignalId.DELT_01: SignalCategory.DELTA,
    SignalId.DELT_02: SignalCategory.DELTA,
    SignalId.DELT_03: SignalCategory.DELTA,
    SignalId.DELT_04: SignalCategory.DELTA,
    SignalId.DELT_05: SignalCategory.DELTA,
    SignalId.DELT_06: SignalCategory.DELTA,
    SignalId.DELT_07: SignalCategory.DELTA,
    SignalId.DELT_08: SignalCategory.DELTA,
    SignalId.DELT_09: SignalCategory.DELTA,
    SignalId.DELT_10: SignalCategory.DELTA,
    SignalId.DELT_11: SignalCategory.DELTA,
    SignalId.AUCT_01: SignalCategory.AUCTION,
    SignalId.AUCT_02: SignalCategory.AUCTION,
    SignalId.AUCT_03: SignalCategory.AUCTION,
    SignalId.AUCT_04: SignalCategory.AUCTION,
    SignalId.AUCT_05: SignalCategory.AUCTION,
    SignalId.TRAP_01: SignalCategory.TRAPPED,
    SignalId.TRAP_02: SignalCategory.TRAPPED,
    SignalId.TRAP_03: SignalCategory.TRAPPED,
    SignalId.TRAP_04: SignalCategory.TRAPPED,
    SignalId.TRAP_05: SignalCategory.TRAPPED,
    SignalId.VOLP_01: SignalCategory.VOLUME_PROFILE,
    SignalId.VOLP_02: SignalCategory.VOLUME_PROFILE,
    SignalId.VOLP_03: SignalCategory.VOLUME_PROFILE,
    SignalId.VOLP_04: SignalCategory.VOLUME_PROFILE,
    SignalId.VOLP_05: SignalCategory.VOLUME_PROFILE,
    SignalId.VOLP_06: SignalCategory.VOLUME_PROFILE,
    SignalId.ENG_02: None,
    SignalId.ENG_03: None,
    SignalId.ENG_04: SignalCategory.ABSORPTION,
    SignalId.ENG_05: None,
    SignalId.ENG_06: SignalCategory.POC,
    SignalId.ENG_07: None,
}


class Direction(int, Enum):
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1


class SignalFlagBits:
    ABS_01 = 1 << 0
    ABS_02 = 1 << 1
    ABS_03 = 1 << 2
    ABS_04 = 1 << 3
    EXH_01 = 1 << 4
    EXH_02 = 1 << 5
    EXH_03 = 1 << 6
    EXH_04 = 1 << 7
    EXH_05 = 1 << 8
    EXH_06 = 1 << 9
    IMB_01 = 1 << 12
    IMB_02 = 1 << 13
    IMB_03 = 1 << 14
    IMB_04 = 1 << 15
    IMB_05 = 1 << 16
    IMB_06 = 1 << 17
    IMB_07 = 1 << 18
    IMB_08 = 1 << 19
    IMB_09 = 1 << 20
    DELT_01 = 1 << 21
    DELT_02 = 1 << 22
    DELT_03 = 1 << 23
    DELT_04 = 1 << 24
    DELT_05 = 1 << 25
    DELT_06 = 1 << 26
    DELT_07 = 1 << 27
    DELT_08 = 1 << 28
    DELT_09 = 1 << 29
    DELT_10 = 1 << 30
    DELT_11 = 1 << 31
    AUCT_01 = 1 << 32
    AUCT_02 = 1 << 33
    AUCT_03 = 1 << 34
    AUCT_04 = 1 << 35
    AUCT_05 = 1 << 36
    TRAP_01 = 1 << 37
    TRAP_02 = 1 << 38
    TRAP_03 = 1 << 39
    TRAP_04 = 1 << 40
    TRAP_05 = 1 << 41
    VOLP_01 = 1 << 42
    VOLP_02 = 1 << 43
    VOLP_03 = 1 << 48
    VOLP_04 = 1 << 49
    VOLP_05 = 1 << 50
    VOLP_06 = 1 << 51
    ENG_02 = 1 << 52
    ENG_03 = 1 << 53
    ENG_04 = 1 << 54
    ENG_05 = 1 << 55
    ENG_06 = 1 << 56
    ENG_07 = 1 << 57
    PIN_REGIME = 1 << 45
    REGIME_CHANGE = 1 << 46
    SPOOF_VETO = 1 << 47
    signal_bits_mask = (1 << 45) - 1


class SignalResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: SignalId
    direction: Direction
    strength: float = Field(ge=0.0, le=1.0)
    detail: str
    price: float
    flag_bit: int


__all__ = [
    "Direction",
    "SIGNAL_TO_CATEGORY",
    "SignalCategory",
    "SignalFlagBits",
    "SignalId",
    "SignalResult",
]
