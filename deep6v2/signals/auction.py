from __future__ import annotations

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class AuctionDetector(ISignalDetector):
    """Detect AUCT_01..AUCT_05 auction-style footprint signals."""

    _TICK_SIZE = 0.25
    _UNFINISHED_MAX_VOLUME = 5

    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []
        results.extend(self._detect_auct01(bar))

        auct02 = self._detect_auct02(bar)
        if auct02 is not None:
            results.append(auct02)

        auct03 = self._detect_auct03(bar)
        if auct03 is not None:
            results.append(auct03)

        auct04 = self._detect_auct04(bar)
        if auct04 is not None:
            results.append(auct04)

        auct05 = self._detect_auct05(bar, ctx)
        if auct05 is not None:
            results.append(auct05)

        return results

    def _detect_auct01(self, bar: FootprintBar) -> list[SignalResult]:
        results: list[SignalResult] = []

        high_volume = self._level_volume(bar, bar.high)
        if high_volume <= self._UNFINISHED_MAX_VOLUME:
            results.append(
                SignalResult(
                    signal_id=SignalId.AUCT_01,
                    direction=Direction.BULLISH,
                    strength=0.35,
                    detail=f"Unfinished auction at high: {high_volume} contracts at {bar.high}",
                    price=bar.high,
                    flag_bit=SignalFlagBits.AUCT_01,
                )
            )

        low_volume = self._level_volume(bar, bar.low)
        if low_volume <= self._UNFINISHED_MAX_VOLUME:
            results.append(
                SignalResult(
                    signal_id=SignalId.AUCT_01,
                    direction=Direction.BEARISH,
                    strength=0.35,
                    detail=f"Unfinished auction at low: {low_volume} contracts at {bar.low}",
                    price=bar.low,
                    flag_bit=SignalFlagBits.AUCT_01,
                )
            )

        return results

    def _detect_auct02(self, bar: FootprintBar) -> SignalResult | None:
        levels = self._traded_levels(bar)
        if len(levels) < 3:
            return None

        top_volumes = [self._level_volume(bar, level) for level in levels[-3:]]
        if self._strictly_decreasing(top_volumes):
            return SignalResult(
                signal_id=SignalId.AUCT_02,
                direction=Direction.BEARISH,
                strength=min(self._average_relative_decay(top_volumes) * 0.65, 1.0),
                detail=f"Finished auction at high: taper {top_volumes}",
                price=bar.high,
                flag_bit=SignalFlagBits.AUCT_02,
            )

        bottom_volumes = [self._level_volume(bar, level) for level in reversed(levels[:3])]
        if self._strictly_decreasing(bottom_volumes):
            return SignalResult(
                signal_id=SignalId.AUCT_02,
                direction=Direction.BULLISH,
                strength=min(self._average_relative_decay(bottom_volumes) * 0.65, 1.0),
                detail=f"Finished auction at low: taper {bottom_volumes}",
                price=bar.low,
                flag_bit=SignalFlagBits.AUCT_02,
            )

        return None

    def _detect_auct03(self, bar: FootprintBar) -> SignalResult | None:
        levels = self._traded_levels(bar)
        if not levels:
            return None

        row_volumes = [self._level_volume(bar, level) for level in levels]
        avg_row_volume = sum(row_volumes) / len(row_volumes)
        if avg_row_volume <= 0:
            return None

        high_volume = self._level_volume(bar, bar.high)
        if high_volume > avg_row_volume * 2.0:
            return SignalResult(
                signal_id=SignalId.AUCT_03,
                direction=Direction.BEARISH,
                strength=min(high_volume / (avg_row_volume * 4.0), 1.0),
                detail=(
                    f"Poor high rejection: extreme={high_volume}, avg_row={avg_row_volume:.1f}"
                ),
                price=bar.high,
                flag_bit=SignalFlagBits.AUCT_03,
            )

        low_volume = self._level_volume(bar, bar.low)
        if low_volume > avg_row_volume * 2.0:
            return SignalResult(
                signal_id=SignalId.AUCT_03,
                direction=Direction.BULLISH,
                strength=min(low_volume / (avg_row_volume * 4.0), 1.0),
                detail=(
                    f"Poor low rejection: extreme={low_volume}, avg_row={avg_row_volume:.1f}"
                ),
                price=bar.low,
                flag_bit=SignalFlagBits.AUCT_03,
            )

        return None

    def _detect_auct04(self, bar: FootprintBar) -> SignalResult | None:
        levels = self._traded_levels(bar)
        if len(levels) < 2:
            return None

        max_volume = max(self._level_volume(bar, level) for level in levels)
        if max_volume <= 0:
            return None

        low_volume_threshold = max_volume * 0.05
        best_void: list[float] = []
        current_void: list[float] = []

        for level in levels:
            total_volume = self._level_volume(bar, level)
            is_low_volume = total_volume < low_volume_threshold

            if is_low_volume and current_void and abs(level - current_void[-1] - self._TICK_SIZE) < 1e-9:
                current_void.append(level)
            elif is_low_volume:
                current_void = [level]
            else:
                if len(current_void) >= 2 and len(current_void) > len(best_void):
                    best_void = current_void[:]
                current_void = []

        if len(current_void) >= 2 and len(current_void) > len(best_void):
            best_void = current_void[:]

        if len(best_void) < 2:
            return None

        midpoint = sum(best_void) / len(best_void)
        direction = Direction.BULLISH if midpoint > bar.poc_price else Direction.BEARISH
        return SignalResult(
            signal_id=SignalId.AUCT_04,
            direction=direction,
            strength=min(len(best_void) / (len(best_void) + 3.0), 1.0),
            detail=(
                f"Volume void across {len(best_void)} levels from {best_void[0]} to {best_void[-1]}"
            ),
            price=best_void[0] if direction is Direction.BULLISH else best_void[-1],
            flag_bit=SignalFlagBits.AUCT_04,
        )

    def _detect_auct05(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if ctx.atr <= 0:
            return None

        bar_range = bar.high - bar.low
        if bar_range <= ctx.atr:
            return None

        levels = self._traded_levels(bar)
        if len(levels) < 3:
            return None

        midpoint = (bar.high + bar.low) / 2
        if bar.close <= midpoint:
            sweep_levels = levels[-3:]
            sweep_volumes = [self._level_volume(bar, level) for level in sweep_levels]
            if not self._strictly_decreasing(sweep_volumes):
                return None

            return SignalResult(
                signal_id=SignalId.AUCT_05,
                direction=Direction.BEARISH,
                strength=min(self._average_relative_decay(sweep_volumes), 0.5),
                detail=(
                    f"Market sweep to high: range {bar_range:.2f} vs ATR {ctx.atr:.2f}, taper {sweep_volumes}"
                ),
                price=bar.high,
                flag_bit=SignalFlagBits.AUCT_05,
            )

        sweep_levels = list(reversed(levels[:3]))
        sweep_volumes = [self._level_volume(bar, level) for level in sweep_levels]
        if not self._strictly_decreasing(sweep_volumes):
            return None

        return SignalResult(
            signal_id=SignalId.AUCT_05,
            direction=Direction.BULLISH,
            strength=min(self._average_relative_decay(sweep_volumes), 0.5),
            detail=(
                f"Market sweep to low: range {bar_range:.2f} vs ATR {ctx.atr:.2f}, taper {sweep_volumes}"
            ),
            price=bar.low,
            flag_bit=SignalFlagBits.AUCT_05,
        )

    @staticmethod
    def _traded_levels(bar: FootprintBar) -> list[float]:
        levels = set(bar.bid_volumes) | set(bar.ask_volumes) | {bar.low, bar.high}
        return sorted(levels)

    @staticmethod
    def _strictly_decreasing(volumes: list[int]) -> bool:
        return len(volumes) >= 3 and all(left > right for left, right in zip(volumes, volumes[1:], strict=False))

    @staticmethod
    def _average_relative_decay(volumes: list[int]) -> float:
        decays = [(left - right) / left for left, right in zip(volumes, volumes[1:], strict=False) if left > 0]
        if not decays:
            return 0.0
        return sum(decays) / len(decays)

    @staticmethod
    def _level_volume(bar: FootprintBar, price: float) -> int:
        return bar.bid_volumes.get(price, 0) + bar.ask_volumes.get(price, 0)


__all__ = ["AuctionDetector"]
