from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class ExhaustionDetector(ISignalDetector):
    """Detect EXH_01..EXH_06 exhaustion variants from bar data and short histories."""

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        if abs(bar.delta) > bar.total_volume * 0.5:
            return []

        results: list[SignalResult] = []

        exh01 = self._detect_exh01(bar)
        if exh01 is not None:
            results.append(exh01)

        exh02 = self._detect_exh02(bar)
        if exh02 is not None:
            results.append(exh02)

        exh03 = self._detect_exh03(bar)
        if exh03 is not None:
            results.append(exh03)

        exh04 = self._detect_exh04(bar)
        if exh04 is not None:
            results.append(exh04)

        exh05 = self._detect_exh05(ctx)
        if exh05 is not None:
            results.append(exh05)

        exh06 = self._detect_exh06(bar, ctx)
        if exh06 is not None:
            results.append(exh06)

        return results

    def _detect_exh01(self, bar: FootprintBar) -> SignalResult | None:
        levels = self._ordered_levels(bar)
        if len(levels) < 2:
            return None

        zero_levels: list[float] = []
        if bar.bid_volumes.get(bar.high, 0) <= self._config.exhaustion_zero_threshold and bar.ask_volumes.get(bar.high, 0) <= self._config.exhaustion_zero_threshold:
            zero_levels.append(bar.high)
        if bar.bid_volumes.get(bar.low, 0) <= self._config.exhaustion_zero_threshold and bar.ask_volumes.get(bar.low, 0) <= self._config.exhaustion_zero_threshold:
            zero_levels.append(bar.low)

        if not zero_levels:
            return None

        bar_range = max(bar.high - bar.low, 0.0)
        top_boundary = bar.high - (bar_range * 0.3)
        bottom_boundary = bar.low + (bar_range * 0.3)

        for price in zero_levels:
            if price >= top_boundary:
                return SignalResult(
                    signal_id=SignalId.EXH_01,
                    direction=Direction.BEARISH,
                    strength=max(0.4, min(len(zero_levels) / len(levels), 1.0)),
                    detail=f"Zero print at top extreme: {price}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_01,
                )
            if price <= bottom_boundary:
                return SignalResult(
                    signal_id=SignalId.EXH_01,
                    direction=Direction.BULLISH,
                    strength=max(0.4, min(len(zero_levels) / len(levels), 1.0)),
                    detail=f"Zero print at bottom extreme: {price}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_01,
                )

        return None

    def _detect_exh02(self, bar: FootprintBar) -> SignalResult | None:
        row_volumes = self._row_volumes(bar)
        if not row_volumes:
            return None

        avg_row_vol = bar.total_volume / len(row_volumes)
        threshold = avg_row_vol * 1.5
        top_cutoff = bar.high - ((bar.high - bar.low) * 0.2)
        bottom_cutoff = bar.low + ((bar.high - bar.low) * 0.2)

        best: SignalResult | None = None
        for price, row_total in row_volumes.items():
            if row_total <= threshold:
                continue

            bid_vol = bar.bid_volumes.get(price, 0)
            ask_vol = bar.ask_volumes.get(price, 0)
            dominant_vol = max(bid_vol, ask_vol)
            opposing_vol = min(bid_vol, ask_vol)
            if dominant_vol <= opposing_vol * 2:
                continue

            if price >= top_cutoff and ask_vol > bid_vol:
                best = SignalResult(
                    signal_id=SignalId.EXH_02,
                    direction=Direction.BEARISH,
                    strength=min(dominant_vol / (avg_row_vol * (self._config.surge_mult + 0.1)), 1.0),
                    detail=f"Exhaustion print at high: ask={ask_vol}, bid={bid_vol}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_02,
                )
            elif price <= bottom_cutoff and bid_vol > ask_vol:
                best = SignalResult(
                    signal_id=SignalId.EXH_02,
                    direction=Direction.BULLISH,
                    strength=min(dominant_vol / (avg_row_vol * (self._config.surge_mult + 0.1)), 1.0),
                    detail=f"Exhaustion print at low: bid={bid_vol}, ask={ask_vol}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_02,
                )

            if best is not None:
                return best

        return None

    def _detect_exh03(self, bar: FootprintBar) -> SignalResult | None:
        row_volumes = self._row_volumes(bar)
        if not row_volumes:
            return None

        max_row_vol = max(row_volumes.values())
        if max_row_vol <= 0:
            return None

        threshold = max_row_vol * 0.05
        top_cutoff = bar.high - ((bar.high - bar.low) * 0.2)
        bottom_cutoff = bar.low + ((bar.high - bar.low) * 0.2)

        for price, row_total in sorted(row_volumes.items(), key=lambda item: item[1]):
            if row_total >= threshold:
                continue

            strength = min((1.0 - (row_total / max_row_vol)) * 0.4, 1.0)
            if price >= top_cutoff:
                return SignalResult(
                    signal_id=SignalId.EXH_03,
                    direction=Direction.BEARISH,
                    strength=strength,
                    detail=f"Thin print at high extreme: {price} vol={row_total}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_03,
                )
            if price <= bottom_cutoff:
                return SignalResult(
                    signal_id=SignalId.EXH_03,
                    direction=Direction.BULLISH,
                    strength=strength,
                    detail=f"Thin print at low extreme: {price} vol={row_total}",
                    price=price,
                    flag_bit=SignalFlagBits.EXH_03,
                )

        return None

    def _detect_exh04(self, bar: FootprintBar) -> SignalResult | None:
        row_volumes = self._row_volumes(bar)
        if not row_volumes:
            return None

        avg_row_vol = bar.total_volume / len(row_volumes)
        threshold = avg_row_vol * self._config.fat_print_mult
        best_price: float | None = None
        best_row_total = 0

        for price, row_total in row_volumes.items():
            if row_total <= threshold or row_total <= best_row_total:
                continue

            row_delta = abs(bar.ask_volumes.get(price, 0) - bar.bid_volumes.get(price, 0))
            if row_delta > row_total * self._config.delta_neutrality_threshold:
                continue

            best_price = price
            best_row_total = row_total

        if best_price is None:
            return None

        midpoint = bar.low + ((bar.high - bar.low) / 2.0)
        direction = Direction.BEARISH if best_price >= midpoint else Direction.BULLISH

        return SignalResult(
            signal_id=SignalId.EXH_04,
            direction=direction,
            strength=min(best_row_total / bar.total_volume, 1.0),
            detail=f"Fat print with neutral delta at {best_price}: vol={best_row_total}",
            price=best_price,
            flag_bit=SignalFlagBits.EXH_04,
        )

    def _detect_exh05(self, ctx: SessionContext) -> SignalResult | None:
        if len(ctx.price_history) < 3 or len(ctx.delta_history) < 3:
            return None

        prices = list(ctx.price_history)[-3:]
        deltas = list(ctx.delta_history)[-3:]
        price_change = prices[-1] - prices[0]
        delta_change = deltas[-1] - deltas[0]
        if price_change == 0 or delta_change == 0:
            return None

        if price_change > 0 and delta_change < 0:
            direction = Direction.BEARISH
        elif price_change < 0 and delta_change > 0:
            direction = Direction.BULLISH
        else:
            return None

        price_pct = abs(price_change) / max(abs(prices[0]), 1.0)
        delta_pct = abs(delta_change) / max(abs(deltas[0]), 1.0)
        strength = min((price_pct + delta_pct) / 2, 1.0)

        return SignalResult(
            signal_id=SignalId.EXH_05,
            direction=direction,
            strength=strength,
            detail=f"Price/delta divergence over last 3 bars: price={price_change:.2f}, delta={delta_change}",
            price=prices[-1],
            flag_bit=SignalFlagBits.EXH_05,
        )

    def _detect_exh06(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if not ctx.bar_history:
            return None

        prior_bar = self._find_comparable_prior_bar(bar, ctx)
        if prior_bar is None:
            return None

        current_ask_high = bar.ask_volumes.get(bar.high, 0)
        prior_ask_high = prior_bar.ask_volumes.get(bar.high, prior_bar.ask_volumes.get(prior_bar.high, 0))
        if prior_ask_high > 0 and current_ask_high < prior_ask_high * 0.6:
            return SignalResult(
                signal_id=SignalId.EXH_06,
                direction=Direction.BEARISH,
                strength=min((1.0 - (current_ask_high / prior_ask_high)) * 0.75, 1.0),
                detail=f"Ask fade at high: current={current_ask_high}, prior={prior_ask_high}",
                price=bar.high,
                flag_bit=SignalFlagBits.EXH_06,
            )

        current_bid_low = bar.bid_volumes.get(bar.low, 0)
        prior_bid_low = prior_bar.bid_volumes.get(bar.low, prior_bar.bid_volumes.get(prior_bar.low, 0))
        if prior_bid_low > 0 and current_bid_low < prior_bid_low * 0.6:
            return SignalResult(
                signal_id=SignalId.EXH_06,
                direction=Direction.BULLISH,
                strength=min((1.0 - (current_bid_low / prior_bid_low)) * 0.75, 1.0),
                detail=f"Bid fade at low: current={current_bid_low}, prior={prior_bid_low}",
                price=bar.low,
                flag_bit=SignalFlagBits.EXH_06,
            )

        return None

    @staticmethod
    def _find_comparable_prior_bar(bar: FootprintBar, ctx: SessionContext) -> FootprintBar | None:
        for prior_bar in reversed(ctx.bar_history):
            if prior_bar.high == bar.high or prior_bar.low == bar.low:
                return prior_bar
        return ctx.bar_history[-1]

    @staticmethod
    def _ordered_levels(bar: FootprintBar) -> list[float]:
        return sorted({bar.low, bar.high, *bar.bid_volumes.keys(), *bar.ask_volumes.keys()})

    @staticmethod
    def _row_volumes(bar: FootprintBar) -> dict[float, int]:
        return {
            price: bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)
            for price in ExhaustionDetector._ordered_levels(bar)
        }


__all__ = ["ExhaustionDetector"]
