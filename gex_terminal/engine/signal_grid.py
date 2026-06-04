"""10-signal institutional grid with confluence scoring."""
from __future__ import annotations

from gex_terminal.schemas_institutional import SignalGrid, SignalGridRow


class SignalGridEngine:
    """Scores 10 independent signals and computes confluence."""

    _BUY_STATES = {"BUY", "BULLISH", "BUY LEAN", "ACCUMULATION"}
    _SELL_STATES = {"SELL", "BEARISH", "SELL LEAN", "DISTRIBUTION"}
    _HOLD_STATES = {"HOLD", "HOLDING"}
    _MIXED_STATES = {"MIXED"}

    def compute(
        self,
        *,
        inst_flow_direction: str = "NEUTRAL",
        floor_flow_direction: str = "neutral",
        dp_bias: str = "neutral",
        market_tide_direction: str = "MIXED",
        multi_day_swing: str = "neutral",
        daily_oi_bias: str = "neutral",
        sweep_flow_direction: str = "neutral",
        block_flow_direction: str = "neutral",
        oi_change_direction: str = "neutral",
        dp_level_bias: str = "neutral",
    ) -> SignalGrid:
        rows = [
            self._resolve("13f_inst", "13F Institutions", inst_flow_direction),
            self._resolve("floor_lit", "Floor/Lit Flow", floor_flow_direction),
            self._resolve("dp_bias", "Dark Pool Bias", dp_bias),
            self._resolve("mkt_tide", "Market Tide", market_tide_direction),
            self._resolve("multi_day", "Multi-Day Swing", multi_day_swing),
            self._resolve("daily_oi", "Daily OI Bias", daily_oi_bias),
            self._resolve("sweep", "Sweep Flow", sweep_flow_direction),
            self._resolve("block", "Block Flow", block_flow_direction),
            self._resolve("oi_change", "OI Change", oi_change_direction),
            self._resolve("dp_blocks", "DP Blocks", dp_level_bias),
        ]

        buy_count = sum(1 for row in rows if row.state == "BUY")
        sell_count = sum(1 for row in rows if row.state == "SELL")

        return SignalGrid(
            rows=rows,
            confluence_buy=buy_count,
            confluence_sell=sell_count,
            total_signals=len(rows),
        )

    def _resolve(self, signal_id: str, label: str, direction: str | None) -> SignalGridRow:
        normalized = (direction or "NEUTRAL").upper().strip()

        if normalized in self._BUY_STATES:
            return SignalGridRow(signal_id=signal_id, label=label, state="BUY", score=1)
        if normalized in self._SELL_STATES:
            return SignalGridRow(signal_id=signal_id, label=label, state="SELL", score=-1)
        if normalized in self._HOLD_STATES:
            return SignalGridRow(signal_id=signal_id, label=label, state="HOLD", score=0)
        if normalized in self._MIXED_STATES:
            return SignalGridRow(signal_id=signal_id, label=label, state="MIXED", score=0)
        return SignalGridRow(signal_id=signal_id, label=label, state="NEUTRAL", score=0)


__all__ = ["SignalGridEngine"]
