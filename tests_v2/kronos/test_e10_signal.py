"""Tests for E10 advisory overlay behavior."""
from __future__ import annotations

from deep6v2.kronos.e10_signal import E10BiasAdvisor
from deep6v2.kronos.pipeline import E10Prediction
from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.types.scoring import SignalTier
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


def make_signal(direction: Direction) -> SignalResult:
    return SignalResult(
        signal_id=SignalId.ABS_01,
        direction=direction,
        strength=1.0,
        detail="test signal",
        price=100.0,
        flag_bit=SignalFlagBits.ABS_01,
    )


def test_agreement_returns_true_false() -> None:
    advisor = E10BiasAdvisor()
    prediction = E10Prediction(Direction.BULLISH, 0.8, stale=False)
    assert advisor.evaluate(prediction, Direction.BULLISH) == (True, False)


def test_disagreement_returns_false_true() -> None:
    advisor = E10BiasAdvisor()
    prediction = E10Prediction(Direction.BULLISH, 0.8, stale=False)
    assert advisor.evaluate(prediction, Direction.BEARISH) == (False, True)


def test_stale_prediction_returns_none_false() -> None:
    advisor = E10BiasAdvisor()
    prediction = E10Prediction(Direction.BULLISH, 0.8, stale=True)
    assert advisor.evaluate(prediction, Direction.BEARISH) == (None, False)


def test_none_prediction_returns_none_false() -> None:
    advisor = E10BiasAdvisor()
    assert advisor.evaluate(None, Direction.BEARISH) == (None, False)


def test_neutral_prediction_returns_none_false() -> None:
    advisor = E10BiasAdvisor()
    prediction = E10Prediction(Direction.NEUTRAL, 0.0, stale=False)
    assert advisor.evaluate(prediction, Direction.BULLISH) == (None, False)


def test_e10_is_purely_advisory_and_does_not_change_final_score() -> None:
    scorer = ConfluenceScorer()
    advisor = E10BiasAdvisor()
    base = scorer.score([make_signal(Direction.BULLISH)], bar_index=10)

    agreement, caution = advisor.evaluate(
        E10Prediction(Direction.BEARISH, 0.9, stale=False),
        Direction.BULLISH,
    )
    advised = base.model_copy(update={"e10_agreement": agreement, "e10_caution": caution})

    assert base.final_score == advised.final_score
    assert base.tier == advised.tier == SignalTier.QUIET
    assert advised.e10_agreement is False
    assert advised.e10_caution is True
