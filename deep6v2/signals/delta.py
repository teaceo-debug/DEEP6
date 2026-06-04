from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult
from deep6v2.utils.math import least_squares_slope


class DeltaDetector(ISignalDetector):
    """Detect DELT_01..DELT_11 delta and CVD patterns."""

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []

        for detector in (
            self._detect_delt01,
            self._detect_delt02,
            self._detect_delt03,
            self._detect_delt04,
            self._detect_delt05,
            self._detect_delt06,
            self._detect_delt07,
            self._detect_delt08,
            self._detect_delt09,
            self._detect_delt10,
            self._detect_delt11,
        ):
            result = detector(bar, ctx)
            if result is not None:
                results.append(result)

        return results

    def _detect_delt01(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        threshold = self._config.big_delta_threshold
        if abs(bar.delta) <= threshold:
            return None

        direction = Direction.BULLISH if bar.delta > 0 else Direction.BEARISH
        strength = min(abs(bar.delta) / (threshold * 8), 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_01,
            direction=direction,
            strength=strength,
            detail=f"Large delta movement: delta={bar.delta}, threshold={threshold}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_01,
        )

    def _detect_delt02(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        bar_range = bar.high - bar.low
        if bar_range <= 0 or bar.delta == 0:
            return None

        tail_span = bar_range * 0.2
        low_cutoff = bar.low + tail_span
        high_cutoff = bar.high - tail_span
        low_tail = sum(volume for price, volume in bar.bid_volumes.items() if price <= low_cutoff)
        high_tail = sum(volume for price, volume in bar.ask_volumes.items() if price >= high_cutoff)
        total_delta = abs(bar.delta)

        if bar.delta > 0 and low_tail > total_delta * 0.4:
            return SignalResult(
                signal_id=SignalId.DELT_02,
                direction=Direction.BULLISH,
                strength=min(low_tail / total_delta, 1.0),
                detail=f"Tail delta at low: {low_tail} aggressive sells absorbed in wick",
                price=bar.low,
                flag_bit=SignalFlagBits.DELT_02,
            )

        if bar.delta < 0 and high_tail > total_delta * 0.4:
            return SignalResult(
                signal_id=SignalId.DELT_02,
                direction=Direction.BEARISH,
                strength=min(high_tail / total_delta, 1.0),
                detail=f"Tail delta at high: {high_tail} aggressive buys trapped in wick",
                price=bar.high,
                flag_bit=SignalFlagBits.DELT_02,
            )

        return None

    def _detect_delt03(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.delta_history or bar.delta == 0:
            return None

        prior_delta = ctx.delta_history[-1]
        if prior_delta == 0 or (prior_delta > 0) == (bar.delta > 0):
            return None

        direction = Direction.BULLISH if bar.delta > 0 else Direction.BEARISH
        strength = min(min(abs(prior_delta), abs(bar.delta)) / (self._config.big_delta_threshold * 2), 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_03,
            direction=direction,
            strength=strength,
            detail=f"Delta reversal: prior={prior_delta}, current={bar.delta}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_03,
        )

    def _detect_delt04(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if len(ctx.price_history) < 5 or len(ctx.cvd_history) < 5:
            return None

        prices = list(ctx.price_history)[-5:]
        cvds = list(ctx.cvd_history)[-5:]
        price_slope = least_squares_slope(prices)
        cvd_slope = least_squares_slope(cvds)
        if price_slope == 0 or cvd_slope == 0 or price_slope * cvd_slope >= 0:
            return None

        direction = Direction.BEARISH if price_slope > 0 else Direction.BULLISH
        strength = min(abs(cvd_slope) / self._config.big_delta_threshold, 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_04,
            direction=direction,
            strength=strength,
            detail=(
                f"CVD/price divergence: price_slope={price_slope:.2f}, "
                f"cvd_slope={cvd_slope:.2f}"
            ),
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_04,
        )

    def _detect_delt05(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.cvd_history:
            return None

        prior_cvd = ctx.cvd_history[-1]
        if prior_cvd == 0 or bar.cvd == 0 or (prior_cvd > 0) == (bar.cvd > 0):
            return None

        direction = Direction.BULLISH if bar.cvd > 0 else Direction.BEARISH
        return SignalResult(
            signal_id=SignalId.DELT_05,
            direction=direction,
            strength=0.4,
            detail=f"CVD zero flip: prior={prior_cvd:.2f}, current={bar.cvd:.2f}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_05,
        )

    def _detect_delt06(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.bar_history:
            return None

        prior_bar = ctx.bar_history[-1]
        threshold = self._config.big_delta_threshold
        if abs(prior_bar.delta) <= threshold:
            return None

        if prior_bar.delta > 0 and bar.close < prior_bar.close and bar.delta < 0:
            return SignalResult(
                signal_id=SignalId.DELT_06,
                direction=Direction.BEARISH,
                strength=min(abs(prior_bar.delta) / (threshold * 6), 1.0),
                detail=f"Delta trap: buyers trapped after prior delta {prior_bar.delta}",
                price=bar.close,
                flag_bit=SignalFlagBits.DELT_06,
            )

        if prior_bar.delta < 0 and bar.close > prior_bar.close and bar.delta > 0:
            return SignalResult(
                signal_id=SignalId.DELT_06,
                direction=Direction.BULLISH,
                strength=min(abs(prior_bar.delta) / (threshold * 6), 1.0),
                detail=f"Delta trap: sellers trapped after prior delta {prior_bar.delta}",
                price=bar.close,
                flag_bit=SignalFlagBits.DELT_06,
            )

        return None

    def _detect_delt07(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        bar_range = bar.high - bar.low
        if bar_range <= 0:
            return None

        extreme_span = bar_range * 0.25
        bottom_cutoff = bar.low + extreme_span
        top_cutoff = bar.high - extreme_span
        bottom_bid = sum(volume for price, volume in bar.bid_volumes.items() if price <= bottom_cutoff)
        top_ask = sum(volume for price, volume in bar.ask_volumes.items() if price >= top_cutoff)
        combined_extreme_flow = bottom_bid + top_ask

        if combined_extreme_flow <= bar.total_volume * 0.25:
            return None

        midpoint = (bar.high + bar.low) / 2
        if (bar.delta > 0 and bar.close >= midpoint) or (bar.delta < 0 and bar.close <= midpoint):
            return None

        direction = Direction.BULLISH if bar.close >= midpoint else Direction.BEARISH
        return SignalResult(
            signal_id=SignalId.DELT_07,
            direction=direction,
            strength=min(combined_extreme_flow / bar.total_volume, 1.0),
            detail=f"Delta sweep: bottom_bid={bottom_bid}, top_ask={top_ask}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_07,
        )

    def _detect_delt08(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.delta_history:
            return None

        threshold = self._config.big_delta_threshold
        prior_delta = ctx.delta_history[-1]
        if abs(prior_delta) >= threshold * 0.3 or abs(bar.delta) <= threshold:
            return None

        direction = Direction.BULLISH if bar.delta > 0 else Direction.BEARISH
        strength = min(abs(bar.delta) / (threshold * 8), 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_08,
            direction=direction,
            strength=strength,
            detail=f"Slingshot delta: compressed {prior_delta}, exploded to {bar.delta}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_08,
        )

    def _detect_delt09(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.cvd_history:
            return None

        prior_max = max(ctx.cvd_history)
        prior_min = min(ctx.cvd_history)
        if bar.cvd > prior_max:
            return SignalResult(
                signal_id=SignalId.DELT_09,
                direction=Direction.BULLISH,
                strength=0.4,
                detail=f"Session CVD extreme: new max {bar.cvd:.2f} > {prior_max:.2f}",
                price=bar.close,
                flag_bit=SignalFlagBits.DELT_09,
            )

        if bar.cvd < prior_min:
            return SignalResult(
                signal_id=SignalId.DELT_09,
                direction=Direction.BEARISH,
                strength=0.4,
                detail=f"Session CVD extreme: new min {bar.cvd:.2f} < {prior_min:.2f}",
                price=bar.close,
                flag_bit=SignalFlagBits.DELT_09,
            )

        return None

    def _detect_delt10(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if len(ctx.price_history) < 10 or len(ctx.cvd_history) < 10:
            return None

        prices = list(ctx.price_history)[-10:]
        cvds = list(ctx.cvd_history)[-10:]
        price_slope = least_squares_slope(prices)
        cvd_slope = least_squares_slope(cvds)
        if price_slope == 0 or cvd_slope == 0 or price_slope * cvd_slope >= 0:
            return None

        direction = Direction.BEARISH if price_slope > 0 else Direction.BULLISH
        strength = min(abs(price_slope - cvd_slope) / self._config.big_delta_threshold, 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_10,
            direction=direction,
            strength=strength,
            detail=(
                f"Polyfit divergence: price_slope={price_slope:.2f}, "
                f"cvd_slope={cvd_slope:.2f}"
            ),
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_10,
        )

    def _detect_delt11(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.delta_history or bar.delta == 0:
            return None

        prior_delta = ctx.delta_history[-1]
        velocity = abs(bar.delta - prior_delta)
        if velocity <= self._config.big_delta_threshold:
            return None

        direction = Direction.BULLISH if bar.delta > 0 else Direction.BEARISH
        strength = min(velocity / (self._config.big_delta_threshold * 5), 1.0)
        return SignalResult(
            signal_id=SignalId.DELT_11,
            direction=direction,
            strength=strength,
            detail=f"Delta velocity: prior={prior_delta}, current={bar.delta}, velocity={velocity}",
            price=bar.close,
            flag_bit=SignalFlagBits.DELT_11,
        )


__all__ = ["DeltaDetector"]
