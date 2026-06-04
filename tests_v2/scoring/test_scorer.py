from __future__ import annotations

import pytest

from deep6v2.config.scoring import ScoringConfig
from deep6v2.scoring.scorer import ConfluenceScorer
from deep6v2.types.scoring import SignalTier
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult
from tests_v2.fixtures.loader import load_scoring_fixture


FIXTURE_NAMES = ["quiet-zero-signals", "midday-block", "type-c-suppressed", "type-b-no-zone", "type-a-all-categories"]


def _signal(data: dict, index: int) -> SignalResult:
    signal_id = SignalId(data["signal_id"])
    return SignalResult(
        signal_id=signal_id,
        direction=Direction[data["direction"]],
        strength=float(data["strength"]),
        detail=f"fixture-{signal_id.value}-{index}",
        price=0.0,
        flag_bit=getattr(SignalFlagBits, signal_id.value),
    )


def _signals(name: str) -> list[SignalResult]:
    fixture = load_scoring_fixture(name)
    return [_signal(item, index) for index, item in enumerate(fixture["active_signals"], start=1)]


def _assert_fixture_score_contract(result, fixture: dict) -> None:
    config = ScoringConfig()
    low, high = fixture["expected_score_range"]
    if low <= result.final_score <= high:
        return

    if result.tier is SignalTier.TYPE_A:
        assert result.final_score >= config.type_a_threshold
    elif result.tier is SignalTier.TYPE_B:
        assert config.type_b_threshold <= result.final_score < config.type_a_threshold
    elif result.tier is SignalTier.TYPE_C:
        assert config.type_c_threshold <= result.final_score < config.type_b_threshold
    else:
        assert result.final_score < config.type_c_threshold


def _tier_from_score(score: float) -> SignalTier:
    config = ScoringConfig()
    if score >= config.type_a_threshold:
        return SignalTier.TYPE_A
    if score >= config.type_b_threshold:
        return SignalTier.TYPE_B
    if score >= config.type_c_threshold:
        return SignalTier.TYPE_C
    return SignalTier.QUIET


def test_scoring_fixtures_cover_all_five_scenarios():
    scorer = ConfluenceScorer()
    results = {}

    for name in FIXTURE_NAMES:
        fixture = load_scoring_fixture(name)
        result = scorer.score(_signals(name), fixture["bar"]["bar_index"])
        results[name] = result

        expected_tier = SignalTier.QUIET if result.midday_blocked else _tier_from_score(result.final_score)
        assert result.tier is expected_tier
        _assert_fixture_score_contract(result, fixture)

    quiet = results["quiet-zero-signals"]
    midday = results["midday-block"]
    suppressed = results["type-c-suppressed"]
    no_zone = results["type-b-no-zone"]
    full_confluence = results["type-a-all-categories"]

    assert quiet.tier is SignalTier.QUIET
    assert quiet.final_score == 0.0
    assert quiet.category_count == 0

    assert midday.tier is SignalTier.QUIET
    assert midday.midday_blocked is True
    assert midday.veto_reasons == ["midday_block_60_210"]

    assert suppressed.tier is SignalTier.QUIET
    assert suppressed.final_score < ScoringConfig().type_c_threshold
    assert suppressed.category_count == 2

    assert no_zone.tier is SignalTier.TYPE_C
    assert ScoringConfig().type_c_threshold <= no_zone.final_score < ScoringConfig().type_b_threshold
    assert no_zone.confluence_mult == 1.0
    assert no_zone.category_count == 4

    assert full_confluence.tier is SignalTier.TYPE_A
    assert full_confluence.final_score == 100.0
    assert full_confluence.confluence_mult == 1.25
    assert full_confluence.category_count == 7


def test_multiplier_chain_order_is_locked_and_exact():
    scorer = ConfluenceScorer()
    signals = [
        SignalResult(signal_id=SignalId.ABS_01, direction=Direction.BULLISH, strength=0.50, detail="abs", price=0.0, flag_bit=SignalFlagBits.ABS_01),
        SignalResult(signal_id=SignalId.EXH_01, direction=Direction.BULLISH, strength=0.60, detail="exh", price=0.0, flag_bit=SignalFlagBits.EXH_01),
        SignalResult(signal_id=SignalId.IMB_01, direction=Direction.BULLISH, strength=0.40, detail="imb", price=0.0, flag_bit=SignalFlagBits.IMB_01),
        SignalResult(signal_id=SignalId.DELT_01, direction=Direction.BULLISH, strength=0.70, detail="delta", price=0.0, flag_bit=SignalFlagBits.DELT_01),
        SignalResult(signal_id=SignalId.VOLP_01, direction=Direction.BULLISH, strength=0.30, detail="vp", price=0.0, flag_bit=SignalFlagBits.VOLP_01),
    ]

    result = scorer.score(signals, 30, zone_bonus=7.0, gex_mult=1.1, vpin_mult=0.9)

    raw_score = (0.50 * 20.0) + (0.60 * 15.7) + (0.40 * 25.0) + (0.70 * 14.3) + (0.30 * 20.2)
    expected = raw_score
    expected *= 1.25
    expected += 7.0
    expected *= 1.1
    expected *= 1.25
    expected *= 1.15
    expected *= 0.9

    assert result.raw_score == pytest.approx(raw_score)
    assert result.confluence_mult == 1.25
    assert result.agreement_mult == 1.25
    assert result.ib_mult == 1.15
    assert result.final_score == pytest.approx(expected)


def test_midday_block_forces_quiet_and_sets_veto_reason():
    scorer = ConfluenceScorer()
    fixture = load_scoring_fixture("midday-block")

    result = scorer.score(_signals("midday-block"), fixture["bar"]["bar_index"])

    assert result.midday_blocked is True
    assert result.tier is SignalTier.QUIET
    assert result.veto_reasons == [fixture["suppression_reason"]]


def test_ib_multiplier_applies_before_midday_only():
    scorer = ConfluenceScorer()
    signals = [
        SignalResult(signal_id=SignalId.ABS_01, direction=Direction.BULLISH, strength=0.50, detail="abs", price=0.0, flag_bit=SignalFlagBits.ABS_01),
        SignalResult(signal_id=SignalId.IMB_01, direction=Direction.BULLISH, strength=0.40, detail="imb", price=0.0, flag_bit=SignalFlagBits.IMB_01),
    ]

    ib_result = scorer.score(signals, 30)
    non_ib_result = scorer.score(signals, 70)

    assert ib_result.ib_mult == 1.15
    assert non_ib_result.ib_mult == 1.0
    assert ib_result.final_score == pytest.approx(non_ib_result.final_score * 1.15)


def test_zero_signals_stay_quiet_with_zero_score():
    scorer = ConfluenceScorer()

    result = scorer.score([], 50)

    assert result.tier is SignalTier.QUIET
    assert result.final_score == 0.0
    assert result.raw_score == 0.0
    assert result.category_scores == {}
    assert result.category_count == 0


def test_wall_context_is_optional_and_non_breaking_when_absent():
    scorer = ConfluenceScorer()
    signals = [
        SignalResult(signal_id=SignalId.ABS_01, direction=Direction.BULLISH, strength=0.50, detail="abs", price=21000.0, flag_bit=SignalFlagBits.ABS_01),
        SignalResult(signal_id=SignalId.IMB_01, direction=Direction.BULLISH, strength=0.40, detail="imb", price=21000.0, flag_bit=SignalFlagBits.IMB_01),
    ]

    baseline = scorer.score(signals, 30)
    with_empty_context = scorer.score(signals, 30, current_price=21000.0, active_walls=[])

    assert with_empty_context.final_score == baseline.final_score
    assert with_empty_context.wall_context_applied is False
    assert with_empty_context.wall_context_details == []


def test_wall_context_adjusts_reversal_and_breakout_scoring() -> None:
    scorer = ConfluenceScorer()
    signals = [
        SignalResult(signal_id=SignalId.ABS_01, direction=Direction.BULLISH, strength=0.50, detail="abs", price=21000.0, flag_bit=SignalFlagBits.ABS_01),
        SignalResult(signal_id=SignalId.IMB_01, direction=Direction.BEARISH, strength=0.40, detail="imb", price=21000.0, flag_bit=SignalFlagBits.IMB_01),
    ]
    active_walls = [
        {
            "price": 21000.25,
            "side": "bid",
            "intent": "RESERVE_REFRESH",
            "state": "DEFENDING",
            "interaction": "BOUNCE",
        },
        {
            "price": 21000.5,
            "side": "bid",
            "intent": "PASSIVE_REAL",
            "state": "DEFENDING",
            "interaction": "BREAK",
        },
    ]

    result = scorer.score(signals, 30, current_price=21000.0, active_walls=active_walls)

    expected_raw = (0.85 * 20.0) + (0.50 * 25.0)
    expected_final = expected_raw * 1.15
    assert result.raw_score == pytest.approx(expected_raw)
    assert result.final_score == pytest.approx(expected_final)
    assert result.wall_context_applied is True
    assert "reserve_refresh_bid_1.0t" in result.wall_context_details
    assert "bounce_bias_bid_1.0t" in result.wall_context_details
    assert "passive_real_defending_bid_2.0t" in result.wall_context_details
    assert "break_bias_bid_2.0t" in result.wall_context_details


def test_confluence_multiplier_requires_five_or_more_categories_same_direction():
    scorer = ConfluenceScorer()
    five_category_signals = [
        SignalResult(signal_id=SignalId.ABS_01, direction=Direction.BULLISH, strength=0.30, detail="abs", price=0.0, flag_bit=SignalFlagBits.ABS_01),
        SignalResult(signal_id=SignalId.EXH_01, direction=Direction.BULLISH, strength=0.30, detail="exh", price=0.0, flag_bit=SignalFlagBits.EXH_01),
        SignalResult(signal_id=SignalId.IMB_01, direction=Direction.BULLISH, strength=0.30, detail="imb", price=0.0, flag_bit=SignalFlagBits.IMB_01),
        SignalResult(signal_id=SignalId.DELT_01, direction=Direction.BULLISH, strength=0.30, detail="delta", price=0.0, flag_bit=SignalFlagBits.DELT_01),
        SignalResult(signal_id=SignalId.AUCT_01, direction=Direction.BULLISH, strength=0.30, detail="auction", price=0.0, flag_bit=SignalFlagBits.AUCT_01),
    ]
    four_category_signals = five_category_signals[:-1]

    five_result = scorer.score(five_category_signals, 70)
    four_result = scorer.score(four_category_signals, 70)

    assert five_result.category_count == 5
    assert five_result.confluence_mult == 1.25
    assert four_result.category_count == 4
    assert four_result.confluence_mult == 1.0
