from __future__ import annotations

from statistics import fmean

from deep6v2.config.signals import SignalConfig
from deep6v2.types.bar import FootprintBar
from deep6v2.types.interfaces import ISignalDetector
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalFlagBits, SignalId, SignalResult


class TrapDetector(ISignalDetector):
    """Detect TRAP_01..TRAP_05 trapped-trader signals. Disabled by default (zero alpha)."""

    def __init__(self, config: SignalConfig | None = None, *, enabled: bool = False) -> None:
        self._config = config or SignalConfig()
        self._enabled = enabled

    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]:
        if not self._enabled or bar.total_volume <= 0:
            return []

        results: list[SignalResult] = []

        trap01 = self._detect_trap01(bar, ctx)
        if trap01 is not None:
            results.append(trap01)

        trap02 = self._detect_trap02(bar, ctx)
        if trap02 is not None:
            results.append(trap02)

        trap03 = self._detect_trap03(bar, ctx)
        if trap03 is not None:
            results.append(trap03)

        trap04 = self._detect_trap04(bar, ctx)
        if trap04 is not None:
            results.append(trap04)

        trap05 = self._detect_trap05(bar, ctx)
        if trap05 is not None:
            results.append(trap05)

        return results

    def _detect_trap01(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        """Inverse Imbalance Trap: prior bar imbalance levels now underwater."""
        if not ctx.imbalance_history:
            return None

        prior_imbalances = ctx.imbalance_history[-1]
        if not prior_imbalances:
            return None

        threshold = self._config.imbalance_ratio

        trapped_buy_ratios = [
            ratio
            for price, ratio in prior_imbalances.items()
            if ratio >= threshold and price > bar.close
        ]

        trapped_sell_ratios = [
            abs(ratio)
            for price, ratio in prior_imbalances.items()
            if ratio <= -threshold and price < bar.close
        ]

        if trapped_buy_ratios:
            max_ratio = max(trapped_buy_ratios)
            strength = min(max_ratio / (threshold * 2), 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_01,
                direction=Direction.BEARISH,
                strength=strength,
                detail=f"Buyers trapped above {bar.close}: {len(trapped_buy_ratios)} imbalance levels",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_01,
            )

        if trapped_sell_ratios:
            max_ratio = max(trapped_sell_ratios)
            strength = min(max_ratio / (threshold * 2), 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_01,
                direction=Direction.BULLISH,
                strength=strength,
                detail=f"Sellers trapped below {bar.close}: {len(trapped_sell_ratios)} imbalance levels",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_01,
            )

        return None

    def _detect_trap02(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        """Delta Trap: large prior delta reversed by current bar."""
        if not ctx.delta_history or not ctx.bar_history:
            return None

        prior_delta = ctx.delta_history[-1]
        prior_bar = ctx.bar_history[-1]
        threshold = self._config.big_delta_threshold

        if abs(prior_delta) <= threshold:
            return None

        if prior_delta > 0 and bar.close < prior_bar.close:
            strength = min(abs(prior_delta) / (threshold * 3), 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_02,
                direction=Direction.BEARISH,
                strength=strength,
                detail=f"Trapped buyers: prior delta {prior_delta}, price dropped {prior_bar.close:.0f}\u2192{bar.close:.0f}",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_02,
            )

        if prior_delta < 0 and bar.close > prior_bar.close:
            strength = min(abs(prior_delta) / (threshold * 3), 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_02,
                direction=Direction.BULLISH,
                strength=strength,
                detail=f"Trapped sellers: prior delta {prior_delta}, price rose {prior_bar.close:.0f}\u2192{bar.close:.0f}",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_02,
            )

        return None

    def _detect_trap03(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        """False Breakout: price exceeds prior range then reverses back inside."""
        if not ctx.bar_history or ctx.atr <= 0:
            return None

        prior_bar = ctx.bar_history[-1]

        if bar.high > prior_bar.high and bar.close < prior_bar.high:
            breakout_distance = bar.high - prior_bar.high
            strength = min(breakout_distance / ctx.atr, 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_03,
                direction=Direction.BEARISH,
                strength=strength,
                detail=f"False breakout above {prior_bar.high}: high={bar.high}, close={bar.close}",
                price=prior_bar.high,
                flag_bit=SignalFlagBits.TRAP_03,
            )

        if bar.low < prior_bar.low and bar.close > prior_bar.low:
            breakout_distance = prior_bar.low - bar.low
            strength = min(breakout_distance / ctx.atr, 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_03,
                direction=Direction.BULLISH,
                strength=strength,
                detail=f"False breakout below {prior_bar.low}: low={bar.low}, close={bar.close}",
                price=prior_bar.low,
                flag_bit=SignalFlagBits.TRAP_03,
            )

        return None

    def _detect_trap04(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        """High Volume Rejection: high-volume bar rejects from an extreme."""
        if not ctx.vol_history:
            return None

        vol_avg = fmean(ctx.vol_history)
        if vol_avg <= 0:
            return None

        if bar.total_volume <= vol_avg * 1.5:
            return None

        bar_range = bar.high - bar.low
        if bar_range < 0.25:
            return None

        close_position = (bar.close - bar.low) / bar_range

        if close_position < 0.35:
            return SignalResult(
                signal_id=SignalId.TRAP_04,
                direction=Direction.BEARISH,
                strength=min(bar.total_volume / vol_avg / 3, 1.0),
                detail=f"High volume rejection at high: vol={bar.total_volume}, avg={vol_avg:.0f}",
                price=bar.high,
                flag_bit=SignalFlagBits.TRAP_04,
            )

        if close_position > 0.65:
            return SignalResult(
                signal_id=SignalId.TRAP_04,
                direction=Direction.BULLISH,
                strength=min(bar.total_volume / vol_avg / 3, 1.0),
                detail=f"High volume rejection at low: vol={bar.total_volume}, avg={vol_avg:.0f}",
                price=bar.low,
                flag_bit=SignalFlagBits.TRAP_04,
            )

        return None

    def _detect_trap05(self, bar: FootprintBar, ctx: SessionContext) -> SignalResult | None:
        """CVD Trap: CVD trending one way while price reverses."""
        if len(ctx.cvd_history) < 3 or len(ctx.price_history) < 2:
            return None

        cvd_vals = list(ctx.cvd_history)
        trend_entries = cvd_vals[:-1]
        if len(trend_entries) < 2:
            return None

        slope = (trend_entries[-1] - trend_entries[0]) / max(len(trend_entries) - 1, 1)

        if abs(slope) < 10:
            return None

        price_vals = list(ctx.price_history)
        price_change = price_vals[-1] - price_vals[-2]

        if slope > 0 and price_change < 0:
            strength = min(abs(slope) / self._config.big_delta_threshold, 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_05,
                direction=Direction.BEARISH,
                strength=strength,
                detail=f"CVD trending up (slope={slope:.1f}) but price falling",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_05,
            )

        if slope < 0 and price_change > 0:
            strength = min(abs(slope) / self._config.big_delta_threshold, 1.0)
            return SignalResult(
                signal_id=SignalId.TRAP_05,
                direction=Direction.BULLISH,
                strength=strength,
                detail=f"CVD trending down (slope={slope:.1f}) but price rising",
                price=bar.close,
                flag_bit=SignalFlagBits.TRAP_05,
            )

        return None


__all__ = ["TrapDetector"]
