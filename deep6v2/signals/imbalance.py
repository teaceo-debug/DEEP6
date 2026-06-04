from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class ImbalanceDetector(ISignalDetector):
    """Detect IMB_01..IMB_09 imbalance variants from bar data only."""

    _tick_size = 0.25

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []
        imbalances = self._compute_level_imbalances(bar)

        imb01 = self._detect_imb01(imbalances)
        if imb01 is not None:
            results.append(imb01)

        imb02 = self._detect_imb02(imbalances, ctx)
        if imb02 is not None:
            results.append(imb02)

        imb03 = self._detect_imb03(imbalances)
        if imb03 is not None:
            results.append(imb03)

        imb04 = self._detect_imb04(imbalances)
        if imb04 is not None:
            results.append(imb04)

        imb05 = self._detect_imb05(bar, imbalances)
        if imb05 is not None:
            results.append(imb05)

        imb06 = self._detect_imb06(imbalances)
        if imb06 is not None:
            results.append(imb06)

        imb07 = self._detect_imb07(imbalances, ctx)
        if imb07 is not None:
            results.append(imb07)

        imb08 = self._detect_imb08(bar)
        if imb08 is not None:
            results.append(imb08)

        imb09 = self._detect_imb09(imbalances, ctx)
        if imb09 is not None:
            results.append(imb09)

        ctx.imbalance_history.append(imbalances)
        return results

    def _detect_imb01(self, imbalances: dict[float, float]) -> SignalResult | None:
        strongest = self._strongest_imbalance(imbalances)
        if strongest is None:
            return None

        price, ratio = strongest
        return SignalResult(
            signal_id=SignalId.IMB_01,
            direction=self._direction_for_ratio(ratio),
            strength=min(abs(ratio) / (self._config.imbalance_ratio * 3.0), 1.0),
            detail=f"Single imbalance at {price}: ratio={abs(ratio):.2f}",
            price=price,
            flag_bit=SignalFlagBits.IMB_01,
        )

    def _detect_imb02(self, imbalances: dict[float, float], ctx: SessionContext) -> SignalResult | None:
        match = self._best_consecutive_match(imbalances, ctx, minimum_count=3)
        if match is None:
            return None

        price, ratio, count = match
        return SignalResult(
            signal_id=SignalId.IMB_02,
            direction=self._direction_for_ratio(ratio),
            strength=min(count / 5.0, 1.0),
            detail=f"Repeated imbalance at {price}: {count} consecutive bars",
            price=price,
            flag_bit=SignalFlagBits.IMB_02,
        )

    def _detect_imb03(self, imbalances: dict[float, float]) -> SignalResult | None:
        stack = self._best_stack(imbalances)
        if stack is None:
            return None

        direction, levels = stack
        level_count = len(levels)
        tier = 3 if level_count >= 7 else 2 if level_count >= 5 else 1
        anchor_price = levels[0] if direction is Direction.BULLISH else levels[-1]

        return SignalResult(
            signal_id=SignalId.IMB_03,
            direction=direction,
            strength=tier / 3.0,
            detail=f"Stacked imbalance T{tier}: {level_count} adjacent levels",
            price=anchor_price,
            flag_bit=SignalFlagBits.IMB_03,
        )

    def _detect_imb04(self, imbalances: dict[float, float]) -> SignalResult | None:
        buy_side = [(price, ratio) for price, ratio in imbalances.items() if ratio > 0]
        sell_side = [(price, ratio) for price, ratio in imbalances.items() if ratio < 0]
        if not buy_side or not sell_side:
            return None

        strongest_buy = max(buy_side, key=lambda item: (item[1], -abs(item[0])))
        strongest_sell = max(sell_side, key=lambda item: (abs(item[1]), -abs(item[0])))
        contested_price = round((strongest_buy[0] + strongest_sell[0]) / 2.0, 10)
        dominant_buy = abs(strongest_buy[1]) >= abs(strongest_sell[1])
        contested_strength = min(
            min(abs(strongest_buy[1]), abs(strongest_sell[1])) / (self._config.imbalance_ratio * 3.0),
            1.0,
        )

        return SignalResult(
            signal_id=SignalId.IMB_04,
            direction=Direction.BEARISH if dominant_buy else Direction.BULLISH,
            strength=contested_strength,
            detail=(
                f"Reverse imbalance around {contested_price}: "
                f"buy={abs(strongest_buy[1]):.2f}, sell={abs(strongest_sell[1]):.2f}"
            ),
            price=contested_price,
            flag_bit=SignalFlagBits.IMB_04,
        )

    def _detect_imb05(self, bar: FootprintBar, imbalances: dict[float, float]) -> SignalResult | None:
        if bar.close == bar.open:
            return None

        is_red_bar = bar.close < bar.open
        candidates: list[tuple[float, float]] = []
        for price, ratio in imbalances.items():
            if is_red_bar and ratio > 0:
                candidates.append((price, ratio))
            elif not is_red_bar and ratio < 0:
                candidates.append((price, ratio))

        if not candidates:
            return None

        price, ratio = max(candidates, key=lambda item: abs(item[1]))
        return SignalResult(
            signal_id=SignalId.IMB_05,
            direction=self._direction_for_ratio(ratio),
            strength=min(abs(ratio) / (self._config.imbalance_ratio * 2.0), 1.0),
            detail=f"Inverse imbalance at {price}: ratio={abs(ratio):.2f} against bar color",
            price=price,
            flag_bit=SignalFlagBits.IMB_05,
        )

    def _detect_imb06(self, imbalances: dict[float, float]) -> SignalResult | None:
        oversized = [item for item in imbalances.items() if abs(item[1]) >= 10.0]
        if not oversized:
            return None

        price, ratio = max(oversized, key=lambda item: abs(item[1]))
        return SignalResult(
            signal_id=SignalId.IMB_06,
            direction=self._direction_for_ratio(ratio),
            strength=min(abs(ratio) / 15.0, 1.0),
            detail=f"Oversized imbalance at {price}: ratio={abs(ratio):.2f}",
            price=price,
            flag_bit=SignalFlagBits.IMB_06,
        )

    def _detect_imb07(self, imbalances: dict[float, float], ctx: SessionContext) -> SignalResult | None:
        match = self._best_consecutive_match(imbalances, ctx, minimum_count=2)
        if match is None:
            return None

        price, ratio, count = match
        return SignalResult(
            signal_id=SignalId.IMB_07,
            direction=self._direction_for_ratio(ratio),
            strength=min(count / 5.0, 1.0),
            detail=f"Persistent imbalance at {price}: {count} consecutive bars",
            price=price,
            flag_bit=SignalFlagBits.IMB_07,
        )

    def _detect_imb08(self, bar: FootprintBar) -> SignalResult | None:
        diagonals = self._compute_diagonal_imbalances(bar)
        strongest = self._strongest_imbalance(diagonals)
        if strongest is None:
            return None

        price, ratio = strongest
        return SignalResult(
            signal_id=SignalId.IMB_08,
            direction=self._direction_for_ratio(ratio),
            strength=min(abs(ratio) / (self._config.imbalance_ratio * 3.0), 1.0),
            detail=f"Diagonal imbalance at {price}: ratio={abs(ratio):.2f}",
            price=price,
            flag_bit=SignalFlagBits.IMB_08,
        )

    def _detect_imb09(self, imbalances: dict[float, float], ctx: SessionContext) -> SignalResult | None:
        if not ctx.imbalance_history:
            return None

        prior = ctx.imbalance_history[-1]
        reversals: list[tuple[float, float]] = []
        for price, ratio in imbalances.items():
            prior_ratio = prior.get(price)
            if prior_ratio is None or prior_ratio * ratio >= 0:
                continue
            reversals.append((price, ratio))

        if not reversals:
            return None

        price, ratio = max(reversals, key=lambda item: abs(item[1]))
        return SignalResult(
            signal_id=SignalId.IMB_09,
            direction=self._direction_for_ratio(ratio),
            strength=0.8,
            detail=f"Imbalance reversal at {price}: prior direction flipped",
            price=price,
            flag_bit=SignalFlagBits.IMB_09,
        )

    def _compute_level_imbalances(self, bar: FootprintBar) -> dict[float, float]:
        imbalances: dict[float, float] = {}
        common_prices = sorted(set(bar.bid_volumes) & set(bar.ask_volumes))
        for price in common_prices:
            bid_volume = bar.bid_volumes.get(price, 0)
            ask_volume = bar.ask_volumes.get(price, 0)
            ratio = self._signed_ratio(bid_volume, ask_volume)
            if ratio is not None:
                imbalances[price] = ratio
        return imbalances

    def _compute_diagonal_imbalances(self, bar: FootprintBar) -> dict[float, float]:
        diagonals: dict[float, float] = {}

        for price, ask_volume in bar.ask_volumes.items():
            bid_volume = bar.bid_volumes.get(round(price - self._tick_size, 10))
            if bid_volume is None:
                continue
            ratio = self._ratio(ask_volume, bid_volume)
            if ratio >= self._config.imbalance_ratio:
                diagonals[price] = ratio

        for price, bid_volume in bar.bid_volumes.items():
            ask_volume = bar.ask_volumes.get(round(price + self._tick_size, 10))
            if ask_volume is None:
                continue
            ratio = self._ratio(bid_volume, ask_volume)
            if ratio >= self._config.imbalance_ratio:
                diagonals[price] = -ratio

        return diagonals

    def _best_consecutive_match(
        self,
        imbalances: dict[float, float],
        ctx: SessionContext,
        *,
        minimum_count: int,
    ) -> tuple[float, float, int] | None:
        best: tuple[float, float, int] | None = None

        for price, ratio in imbalances.items():
            count = 1
            for history_entry in reversed(ctx.imbalance_history):
                prior_ratio = history_entry.get(price)
                if prior_ratio is None or prior_ratio * ratio <= 0:
                    break
                count += 1

            if count < minimum_count:
                continue

            candidate = (price, ratio, count)
            if best is None or self._is_better_consecutive(candidate, best):
                best = candidate

        return best

    def _best_stack(self, imbalances: dict[float, float]) -> tuple[Direction, list[float]] | None:
        best_direction: Direction | None = None
        best_levels: list[float] = []

        for direction in (Direction.BULLISH, Direction.BEARISH):
            prices = sorted(price for price, ratio in imbalances.items() if self._direction_for_ratio(ratio) is direction)
            if len(prices) < 3:
                continue

            current_run = [prices[0]]
            for price in prices[1:]:
                if self._is_adjacent(current_run[-1], price):
                    current_run.append(price)
                else:
                    if len(current_run) > len(best_levels):
                        best_direction = direction
                        best_levels = current_run[:]
                    current_run = [price]

            if len(current_run) > len(best_levels):
                best_direction = direction
                best_levels = current_run[:]

        if best_direction is None or len(best_levels) < 3:
            return None

        return best_direction, best_levels

    @staticmethod
    def _is_adjacent(left: float, right: float) -> bool:
        return abs((right - left) - ImbalanceDetector._tick_size) <= 1e-9

    @staticmethod
    def _is_better_consecutive(candidate: tuple[float, float, int], current: tuple[float, float, int]) -> bool:
        _, candidate_ratio, candidate_count = candidate
        _, current_ratio, current_count = current
        return (candidate_count, abs(candidate_ratio)) > (current_count, abs(current_ratio))

    def _signed_ratio(self, bid_volume: int, ask_volume: int) -> float | None:
        buy_ratio = self._ratio(ask_volume, bid_volume)
        if buy_ratio >= self._config.imbalance_ratio:
            return buy_ratio

        sell_ratio = self._ratio(bid_volume, ask_volume)
        if sell_ratio >= self._config.imbalance_ratio:
            return -sell_ratio

        return None

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        if numerator <= 0:
            return 0.0
        if denominator <= 0:
            return float("inf")
        return numerator / denominator

    @staticmethod
    def _direction_for_ratio(ratio: float) -> Direction:
        return Direction.BULLISH if ratio > 0 else Direction.BEARISH

    @staticmethod
    def _strongest_imbalance(imbalances: dict[float, float]) -> tuple[float, float] | None:
        if not imbalances:
            return None
        return max(imbalances.items(), key=lambda item: abs(item[1]))


__all__ = ["ImbalanceDetector"]
