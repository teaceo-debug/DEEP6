from __future__ import annotations

from deep6v2.signals.engines.wall_intent import WallIntentDetector
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


def _signal(signal_id: SignalId, direction: Direction, strength: float = 0.5, price: float = 21000.0) -> SignalResult:
    return SignalResult(
        signal_id=signal_id,
        direction=direction,
        strength=strength,
        detail=f"{signal_id.value}-fixture",
        price=price,
        flag_bit=getattr(SignalFlagBits, signal_id.value),
    )


def test_spoof_wall_suppresses_nearby_signals() -> None:
    detector = WallIntentDetector()
    signals = [_signal(SignalId.ABS_01, Direction.BULLISH)]
    walls = [{"price": 21000.75, "side": "bid", "intent": "SPOOF_LIKE", "state": "FRESH"}]

    result = detector.evaluate(walls, current_price=21000.0, signals=signals)
    adjusted = result.apply(signals)

    assert result.nearby_wall_count == 1
    assert adjusted[0].strength == 0.35
    assert "spoof_like_bid_3.0t" in result.details


def test_defending_and_bounce_confirm_bullish_reversal() -> None:
    detector = WallIntentDetector()
    signals = [_signal(SignalId.ABS_01, Direction.BULLISH)]
    walls = [
        {
            "price": 20999.5,
            "side": "bid",
            "intent": "PASSIVE_REAL",
            "state": "DEFENDING",
            "interaction": "BOUNCE",
        }
    ]

    result = detector.evaluate(walls, current_price=21000.0, signals=signals)
    adjusted = result.apply(signals)

    assert adjusted[0].strength == 0.7
    assert "passive_real_defending_bid_2.0t" in result.details
    assert "bounce_bias_bid_2.0t" in result.details


def test_reserve_refresh_and_break_confirm_bearish_breakout_from_bid_wall() -> None:
    detector = WallIntentDetector()
    signals = [_signal(SignalId.IMB_01, Direction.BEARISH)]
    walls = [
        {
            "price": 21000.25,
            "side": "bid",
            "classification": "ICEBERG",
            "state": "DEFENDING",
            "interaction": "BREAK",
        }
    ]

    result = detector.evaluate(walls, current_price=21000.0, signals=signals)
    adjusted = result.apply(signals)

    assert adjusted[0].strength == 0.6
    assert "break_bias_bid_1.0t" in result.details


def test_far_walls_are_ignored() -> None:
    detector = WallIntentDetector()
    signals = [_signal(SignalId.EXH_01, Direction.BEARISH)]
    walls = [{"price": 21002.0, "side": "ask", "intent": "PASSIVE_REAL", "state": "DEFENDING"}]

    result = detector.evaluate(walls, current_price=21000.0, signals=signals)

    assert result.nearby_wall_count == 0
    assert result.modifiers == ()
