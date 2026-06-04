from __future__ import annotations

from statistics import fmean

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import IAbsorptionZoneReceiver, ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class AbsorptionDetector(ISignalDetector):
    """Detect ABS_01..ABS_04 absorption variants from bar data only."""

    def __init__(
        self,
        config: SignalConfig | None = None,
        receivers: list[IAbsorptionZoneReceiver] | None = None,
    ) -> None:
        self._config = config or SignalConfig()
        self._receivers = list(receivers or [])

    def register_receiver(self, receiver: IAbsorptionZoneReceiver) -> None:
        self._receivers.append(receiver)

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []

        abs01 = self._detect_abs01(bar)
        if abs01 is not None:
            results.append(abs01)
            self._notify_absorption_zone(abs01.price, abs01.direction, abs01.strength)

        abs02 = self._detect_abs02(bar, ctx)
        if abs02 is not None:
            results.append(abs02)

        abs03 = self._detect_abs03(bar, ctx)
        if abs03 is not None:
            results.append(abs03)

        abs04 = self._detect_abs04(bar, ctx)
        if abs04 is not None:
            results.append(abs04)

        return results

    def _detect_abs01(self, bar: FootprintBar) -> SignalResult | None:
        bar_range = bar.high - bar.low
        if bar_range < 0.25:
            return None

        wick_pct = self._config.absorption_wick_pct
        neutrality = self._config.delta_neutrality_threshold
        low_cutoff = bar.low + (bar_range * 0.2)
        high_cutoff = bar.high - (bar_range * 0.2)

        low_wick_vol = sum(volume for price, volume in bar.bid_volumes.items() if price <= low_cutoff)
        high_wick_vol = sum(volume for price, volume in bar.ask_volumes.items() if price >= high_cutoff)
        delta_neutral = abs(bar.delta) < bar.total_volume * neutrality

        if low_wick_vol > bar.total_volume * wick_pct and delta_neutral:
            strength = min(low_wick_vol / bar.total_volume, 1.0)
            return SignalResult(
                signal_id=SignalId.ABS_01,
                direction=Direction.BULLISH,
                strength=strength,
                detail=f"Low wick absorption: {low_wick_vol}/{bar.total_volume} vol at low extreme",
                price=bar.low,
                flag_bit=SignalFlagBits.ABS_01,
            )

        if high_wick_vol > bar.total_volume * wick_pct and delta_neutral:
            strength = min(high_wick_vol / bar.total_volume, 1.0)
            return SignalResult(
                signal_id=SignalId.ABS_01,
                direction=Direction.BEARISH,
                strength=strength,
                detail=f"High wick absorption: {high_wick_vol}/{bar.total_volume} vol at high extreme",
                price=bar.high,
                flag_bit=SignalFlagBits.ABS_01,
            )

        return None

    def _detect_abs02(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        vol_ema = self._volume_average(ctx)
        if vol_ema is None:
            return None

        bar_range = bar.high - bar.low
        if bar_range < 0.25:
            return None

        passive_mult = 1.5
        low_cutoff = bar.low + (bar_range * 0.15)
        high_cutoff = bar.high - (bar_range * 0.15)

        low_extreme_vol = sum(volume for price, volume in bar.bid_volumes.items() if price <= low_cutoff)
        high_extreme_vol = sum(volume for price, volume in bar.ask_volumes.items() if price >= high_cutoff)
        close_away_from_low = bar.close > bar.low + (bar_range * 0.3)
        close_away_from_high = bar.close < bar.high - (bar_range * 0.3)

        threshold = vol_ema * passive_mult
        if low_extreme_vol > threshold and close_away_from_low:
            return SignalResult(
                signal_id=SignalId.ABS_02,
                direction=Direction.BULLISH,
                strength=min(low_extreme_vol / threshold, 1.0),
                detail=f"Passive absorption at low: {low_extreme_vol:.0f} vol, price holds",
                price=bar.low,
                flag_bit=SignalFlagBits.ABS_02,
            )

        if high_extreme_vol > threshold and close_away_from_high:
            return SignalResult(
                signal_id=SignalId.ABS_02,
                direction=Direction.BEARISH,
                strength=min(high_extreme_vol / threshold, 1.0),
                detail=f"Passive absorption at high: {high_extreme_vol:.0f} vol, price holds",
                price=bar.high,
                flag_bit=SignalFlagBits.ABS_02,
            )

        return None

    def _detect_abs03(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        vol_ema = self._volume_average(ctx)
        if vol_ema is None:
            return None

        if bar.total_volume < vol_ema * self._config.stopping_mult:
            return None

        bar_range = bar.high - bar.low
        if bar_range < 0.25:
            return None

        if bar.poc_price <= bar.low + (bar_range * 0.25):
            return SignalResult(
                signal_id=SignalId.ABS_03,
                direction=Direction.BULLISH,
                strength=min(bar.poc_volume / bar.total_volume, 1.0),
                detail=f"Stopping volume at low wick: POC={bar.poc_price}, vol={bar.total_volume}",
                price=bar.low,
                flag_bit=SignalFlagBits.ABS_03,
            )

        if bar.poc_price >= bar.high - (bar_range * 0.25):
            return SignalResult(
                signal_id=SignalId.ABS_03,
                direction=Direction.BEARISH,
                strength=min(bar.poc_volume / bar.total_volume, 1.0),
                detail=f"Stopping volume at high wick: POC={bar.poc_price}, vol={bar.total_volume}",
                price=bar.high,
                flag_bit=SignalFlagBits.ABS_03,
            )

        return None

    def _detect_abs04(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        vol_ema = self._volume_average(ctx)
        if vol_ema is None or ctx.atr <= 0:
            return None

        if bar.total_volume < vol_ema * self._config.effort_mult:
            return None

        bar_range = bar.high - bar.low
        if bar_range > ctx.atr * self._config.effort_range_pct:
            return None

        midpoint = (bar.high + bar.low) / 2
        if bar.close >= midpoint:
            direction = Direction.BULLISH
            price = bar.low
        else:
            direction = Direction.BEARISH
            price = bar.high

        return SignalResult(
            signal_id=SignalId.ABS_04,
            direction=direction,
            strength=min(bar.total_volume / (vol_ema * self._config.effort_mult), 1.0),
            detail=(
                f"Effort vs Result: {bar.total_volume:.0f} vol, {bar_range:.2f} range "
                f"vs ATR {ctx.atr:.2f}"
            ),
            price=price,
            flag_bit=SignalFlagBits.ABS_04,
        )

    def _notify_absorption_zone(self, price: float, direction: Direction, strength: float) -> None:
        for receiver in self._receivers:
            try:
                receiver.mark_absorption_zone(price, direction, strength)
            except Exception:
                continue

    @staticmethod
    def _volume_average(ctx: SessionContext) -> float | None:
        if not ctx.vol_history:
            return None
        return fmean(ctx.vol_history)


__all__ = ["AbsorptionDetector"]
