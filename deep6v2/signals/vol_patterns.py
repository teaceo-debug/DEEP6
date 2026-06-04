from __future__ import annotations

from statistics import fmean

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class VolPatternDetector(ISignalDetector):
    def __init__(self, config: SignalConfig | None = None) -> None:
        self._config = config or SignalConfig()

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []

        volp01 = self._detect_volp01(bar, ctx)
        if volp01 is not None:
            results.append(volp01)

        volp02 = self._detect_volp02(bar, ctx)
        if volp02 is not None:
            results.append(volp02)

        volp03 = self._detect_volp03(bar, ctx)
        if volp03 is not None:
            results.append(volp03)

        volp04 = self._detect_volp04(bar, ctx)
        if volp04 is not None:
            results.append(volp04)

        volp05 = self._detect_volp05(bar, ctx)
        if volp05 is not None:
            results.append(volp05)

        volp06 = self._detect_volp06(bar)
        if volp06 is not None:
            results.append(volp06)

        return results

    def _detect_volp01(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if len(ctx.bar_history) < 2 or len(ctx.vol_history) < 2:
            return None

        bars = [*list(ctx.bar_history)[-2:], bar]
        volumes = [*list(ctx.vol_history)[-2:], bar.total_volume]

        if not (volumes[0] < volumes[1] < volumes[2]):
            return None

        directions = [self._bar_direction(candidate) for candidate in bars]
        if Direction.NEUTRAL in directions or len(set(directions)) != 1:
            return None

        vol_growth_rate = volumes[-1] / volumes[0]
        direction = directions[-1]
        return SignalResult(
            signal_id=SignalId.VOLP_01,
            direction=direction,
            strength=min(vol_growth_rate - 1.0, 1.0),
            detail=(
                f"Volume sequencing: {volumes[0]} -> {volumes[1]} -> {volumes[2]} "
                f"with {direction.name.lower()} closes"
            ),
            price=bar.close,
            flag_bit=SignalFlagBits.VOLP_01,
        )

    def _detect_volp02(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        vol_ema = self._volume_average(ctx)
        if vol_ema is None or not ctx.vol_history:
            return None

        prior_volume = ctx.vol_history[-1]
        threshold = vol_ema * 3.0
        if bar.total_volume <= threshold or prior_volume >= vol_ema:
            return None

        direction = self._bar_direction(bar)
        return SignalResult(
            signal_id=SignalId.VOLP_02,
            direction=direction,
            strength=min(bar.total_volume / threshold, 1.0),
            detail=(
                f"Volume bubble: current {bar.total_volume} vs {threshold:.0f} threshold "
                f"after below-average prior bar {prior_volume}"
            ),
            price=bar.close,
            flag_bit=SignalFlagBits.VOLP_02,
        )

    def _detect_volp03(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        vol_ema = self._volume_average(ctx)
        if vol_ema is None:
            return None

        threshold = vol_ema * self._config.surge_mult
        if bar.total_volume <= threshold:
            return None

        direction = self._bar_direction(bar)
        return SignalResult(
            signal_id=SignalId.VOLP_03,
            direction=direction,
            strength=min(bar.total_volume / threshold, 1.0),
            detail=f"Volume surge: {bar.total_volume} vs {threshold:.0f} threshold",
            price=bar.close,
            flag_bit=SignalFlagBits.VOLP_03,
        )

    def _detect_volp04(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if ctx.atr <= 0 or len(ctx.poc_history) < 3:
            return None

        poc_values = [*list(ctx.poc_history)[-3:], bar.poc_price]
        increasing = all(left < right for left, right in zip(poc_values, poc_values[1:]))
        decreasing = all(left > right for left, right in zip(poc_values, poc_values[1:]))
        if not increasing and not decreasing:
            return None

        direction = Direction.BULLISH if increasing else Direction.BEARISH
        poc_displacement = abs(poc_values[-1] - poc_values[0])
        return SignalResult(
            signal_id=SignalId.VOLP_04,
            direction=direction,
            strength=min(poc_displacement / ctx.atr, 1.0),
            detail=(
                f"POC momentum wave: {poc_values[0]:.2f} -> {poc_values[-1]:.2f} "
                f"over 3 bars"
            ),
            price=bar.poc_price,
            flag_bit=SignalFlagBits.VOLP_04,
        )

    def _detect_volp05(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        if len(ctx.delta_history) < 2:
            return None

        prior_delta = ctx.delta_history[-1]
        older_delta = ctx.delta_history[-2]
        current_velocity = abs(bar.delta - prior_delta)
        prior_velocity = abs(prior_delta - older_delta)
        if current_velocity <= (prior_velocity * 2):
            return None

        if current_velocity <= self._config.big_delta_threshold:
            return None

        direction = self._delta_direction(bar.delta)
        return SignalResult(
            signal_id=SignalId.VOLP_05,
            direction=direction,
            strength=min(current_velocity / (self._config.big_delta_threshold * 2), 1.0),
            detail=(
                f"Delta velocity spike: current {current_velocity} vs prior {prior_velocity} "
                f"with delta {bar.delta}"
            ),
            price=bar.close,
            flag_bit=SignalFlagBits.VOLP_05,
        )

    def _detect_volp06(self, bar: FootprintBar) -> SignalResult | None:
        max_price: float | None = None
        max_level_delta = 0

        for price in set(bar.bid_volumes) | set(bar.ask_volumes):
            level_delta = bar.ask_volumes.get(price, 0) - bar.bid_volumes.get(price, 0)
            if abs(level_delta) > abs(max_level_delta):
                max_price = price
                max_level_delta = level_delta

        if max_price is None or abs(max_level_delta) <= self._config.big_delta_threshold:
            return None

        direction = self._delta_direction(max_level_delta)
        return SignalResult(
            signal_id=SignalId.VOLP_06,
            direction=direction,
            strength=min(abs(max_level_delta) / (self._config.big_delta_threshold * 2), 1.0),
            detail=f"Big delta per level: {max_level_delta} at {max_price}",
            price=max_price,
            flag_bit=SignalFlagBits.VOLP_06,
        )

    @staticmethod
    def _bar_direction(bar: FootprintBar) -> Direction:
        if bar.close > bar.open:
            return Direction.BULLISH
        if bar.close < bar.open:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _delta_direction(delta: int) -> Direction:
        if delta > 0:
            return Direction.BULLISH
        if delta < 0:
            return Direction.BEARISH
        return Direction.NEUTRAL

    @staticmethod
    def _volume_average(ctx: SessionContext) -> float | None:
        if not ctx.vol_history:
            return None
        return fmean(ctx.vol_history)


__all__ = ["VolPatternDetector"]
