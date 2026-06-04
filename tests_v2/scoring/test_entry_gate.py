from __future__ import annotations

from datetime import UTC, datetime

from deep6v2.scoring.entry_gate import EntryDecision, EntryGate
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.scoring import ScorerResult, SignalTier
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


def _ts() -> datetime:
    return datetime(2026, 5, 14, 14, 0, tzinfo=UTC)


def _bar(*, delta: int = 10, close: float = 21490.0) -> FootprintBar:
    return FootprintBar(
        open=21490.0,
        high=21500.0,
        low=21480.0,
        close=close,
        delta=delta,
        total_volume=2000,
        bid_volumes={21480.0: 500, 21485.0: 300},
        ask_volumes={21495.0: 300, 21500.0: 400},
        poc_price=21490.0,
        poc_volume=600,
        vah=21498.0,
        val=21484.0,
        cvd=10.0,
        bar_index=5,
        timestamp=_ts(),
        session_type=SessionType.RTH,
    )


def _ctx(*, vah: float = 21500.0, val: float = 21480.0) -> SessionContext:
    return SessionContext(
        atr=10.0,
        cvd=0.0,
        vah=vah,
        val=val,
        poc=21490.0,
        session_type=SessionType.RTH,
        session_open_bar_index=0,
    )


def _signal(
    signal_id: SignalId,
    direction: Direction = Direction.BULLISH,
    strength: float = 0.7,
    flag_bit: int = 0,
) -> SignalResult:
    return SignalResult(
        signal_id=signal_id,
        direction=direction,
        strength=strength,
        detail="test",
        price=21490.0,
        flag_bit=flag_bit,
    )


def _scorer(
    *,
    tier: SignalTier,
    final_score: float,
    signals: list[SignalResult],
) -> ScorerResult:
    return ScorerResult(
        tier=tier,
        raw_score=final_score,
        final_score=final_score,
        category_scores={},
        category_count=len(signals),
        confluence_mult=1.0,
        zone_bonus=0.0,
        gex_mult=1.0,
        agreement_mult=1.0,
        ib_mult=1.0,
        vpin_mult=1.0,
        midday_blocked=False,
        active_signals=signals,
        veto_reasons=[],
        e10_agreement=None,
        e10_caution=False,
    )


# -- six-category bullish signal set (used by many Type A tests) --
def _six_cat_bullish() -> list[SignalResult]:
    return [
        _signal(SignalId.ABS_01, Direction.BULLISH, 0.8, SignalFlagBits.ABS_01),
        _signal(SignalId.EXH_01, Direction.BULLISH, 0.7, SignalFlagBits.EXH_01),
        _signal(SignalId.IMB_01, Direction.BULLISH, 0.6, SignalFlagBits.IMB_01),
        _signal(SignalId.DELT_01, Direction.BULLISH, 0.5, SignalFlagBits.DELT_01),
        _signal(SignalId.VOLP_01, Direction.BULLISH, 0.6, SignalFlagBits.VOLP_01),
        _signal(SignalId.AUCT_01, Direction.BULLISH, 0.5, SignalFlagBits.AUCT_01),
    ]


# ── Type A ───────────────────────────────────────────────────────────


class TestTypeA:
    def test_eligible(self):
        signals = _six_cat_bullish()
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is True
        assert decision.tier is SignalTier.TYPE_A
        assert decision.veto_reasons == []
        assert decision.direction is Direction.BULLISH

    def test_not_eligible_without_absorption_or_exhaustion(self):
        signals = [
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.6),
            _signal(SignalId.DELT_01, Direction.BULLISH, 0.5),
            _signal(SignalId.VOLP_01, Direction.BULLISH, 0.6),
            _signal(SignalId.AUCT_01, Direction.BULLISH, 0.5),
            _signal(SignalId.TRAP_01, Direction.BULLISH, 0.4),
        ]
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False

    def test_not_eligible_under_5_categories(self):
        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8),
            _signal(SignalId.EXH_01, Direction.BULLISH, 0.7),
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.6),
            _signal(SignalId.DELT_01, Direction.BULLISH, 0.5),
        ]
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False


# ── Type B ───────────────────────────────────────────────────────────


class TestTypeB:
    def test_eligible_with_absorption(self):
        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.6),
            _signal(SignalId.IMB_01, Direction.BULLISH, 0.5),
        ]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is True
        assert decision.tier is SignalTier.TYPE_B

    def test_eligible_with_exhaustion(self):
        signals = [_signal(SignalId.EXH_01, Direction.BEARISH, 0.6)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=74, signals=signals)

        decision = EntryGate().evaluate(result, _bar(delta=-10), _ctx())

        assert decision.eligible is True

    def test_eligible_with_imb03(self):
        signals = [_signal(SignalId.IMB_03, Direction.BULLISH, 0.7)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=73, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is True

    def test_not_eligible_without_core(self):
        signals = [_signal(SignalId.DELT_01, Direction.BULLISH, 0.5)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False


# ── Type C ───────────────────────────────────────────────────────────


class TestTypeC:
    def test_not_eligible(self):
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, 0.8)]
        result = _scorer(tier=SignalTier.TYPE_C, final_score=55, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert decision.tier is SignalTier.TYPE_C


# ── QUIET ────────────────────────────────────────────────────────────


class TestQuiet:
    def test_not_eligible(self):
        result = _scorer(tier=SignalTier.QUIET, final_score=30, signals=[])

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert decision.tier is SignalTier.QUIET
        assert decision.direction is Direction.NEUTRAL


# ── Vetoes ───────────────────────────────────────────────────────────


class TestVetoes:
    def test_trap_veto(self):
        signals = _six_cat_bullish() + [
            _signal(SignalId.TRAP_01, Direction.BULLISH, 0.4, SignalFlagBits.TRAP_01),
            _signal(SignalId.TRAP_02, Direction.BULLISH, 0.4, SignalFlagBits.TRAP_02),
            _signal(SignalId.TRAP_03, Direction.BULLISH, 0.4, SignalFlagBits.TRAP_03),
        ]
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert any("trap_veto" in r for r in decision.veto_reasons)

    def test_chase_veto_bullish(self):
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, 0.8)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(delta=60), _ctx())

        assert decision.eligible is False
        assert any("chase_veto" in r for r in decision.veto_reasons)

    def test_chase_veto_bearish(self):
        signals = [_signal(SignalId.ABS_01, Direction.BEARISH, 0.8)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(delta=-60), _ctx())

        assert decision.eligible is False
        assert any("chase_veto" in r for r in decision.veto_reasons)

    def test_spoof_veto(self):
        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8),
            _signal(SignalId.SPOOF_VETO, Direction.NEUTRAL, 0.5, SignalFlagBits.SPOOF_VETO),
        ]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert any("spoof_veto" in r for r in decision.veto_reasons)

    def test_pin_veto(self):
        signals = [
            _signal(SignalId.ABS_01, Direction.BULLISH, 0.8),
            _signal(SignalId.PIN_REGIME, Direction.NEUTRAL, 0.5, SignalFlagBits.PIN_REGIME),
        ]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert any("pin_veto" in r for r in decision.veto_reasons)

    def test_veto_blocks_type_a(self):
        signals = _six_cat_bullish() + [
            _signal(SignalId.SPOOF_VETO, Direction.NEUTRAL, 0.5, SignalFlagBits.SPOOF_VETO),
        ]
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.eligible is False
        assert decision.tier is SignalTier.TYPE_A
        assert len(decision.veto_reasons) > 0


# ── Confluence ───────────────────────────────────────────────────────


class TestConfluence:
    def test_stacked(self):
        signals = _six_cat_bullish()  # has both ABS_01 and EXH_01 bullish
        result = _scorer(tier=SignalTier.TYPE_A, final_score=85, signals=signals)

        decision = EntryGate().evaluate(result, _bar(), _ctx())

        assert decision.confluence_type == "STACKED"

    def test_va_extreme_near_vah(self):
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, 0.85)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(close=21500.25), _ctx(vah=21500.0))

        assert decision.confluence_type == "VA_EXTREME"

    def test_va_extreme_near_val(self):
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, 0.80)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(close=21480.25), _ctx(val=21480.0))

        assert decision.confluence_type == "VA_EXTREME"

    def test_no_confluence(self):
        signals = [_signal(SignalId.ABS_01, Direction.BULLISH, 0.6)]
        result = _scorer(tier=SignalTier.TYPE_B, final_score=75, signals=signals)

        decision = EntryGate().evaluate(result, _bar(close=21490.0), _ctx())

        assert decision.confluence_type == "NONE"
