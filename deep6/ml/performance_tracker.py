"""PerformanceTracker — rolling window P&L metrics per signal tier and HMM regime.

Per D-22: Rolling windows of 50, 200, 500 trades; win_rate, profit_factor, Sharpe.
Per D-23: Per-regime breakdown slices same metrics by HMM regime state.

Design: Pure synchronous compute() + async fetch_and_compute() wrapper.
No external dependencies beyond numpy (already installed).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from deep6.api.store import EventStore

# Closed event types — matching CLOSED_EVENTS from plan interfaces
_CLOSED_TYPES = frozenset({"STOP_HIT", "TARGET_HIT", "TIMEOUT_EXIT", "MANUAL_EXIT"})

# Valid signal tiers
_TIERS = ("TYPE_A", "TYPE_B", "TYPE_C")

# Valid HMM regime labels
_REGIMES = ("ABSORPTION_FRIENDLY", "TRENDING", "CHAOTIC")

# Trading days per year (annualisation factor for Sharpe)
_TRADING_DAYS = 252.0


@dataclass
class TierMetrics:
    """Per-tier (optionally per-regime) rolling-window performance metrics.

    tier:           Signal tier label — "TYPE_A", "TYPE_B", or "TYPE_C".
    n_trades:       Number of closed trades in the rolling window used.
    win_rate:       wins / n_trades (0.0 if n_trades == 0).
    profit_factor:  sum(positive_pnl) / abs(sum(negative_pnl)); inf if no losses.
    sharpe:         mean(pnl) / std(pnl) * sqrt(252); 0.0 if std == 0 or n == 0.
    avg_pnl:        mean P&L per trade.
    total_pnl:      sum of P&L for the window.
    regime:         None = all regimes aggregated; "ABSORPTION_FRIENDLY" etc. for slices.
    window:         Rolling window size requested (50, 200, or 500).
    """

    tier: str
    n_trades: int
    win_rate: float
    profit_factor: float
    sharpe: float
    avg_pnl: float
    total_pnl: float
    regime: str | None
    window: int

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        d = asdict(self)
        # Replace inf/nan with None for JSON safety
        for key in ("win_rate", "profit_factor", "sharpe", "avg_pnl", "total_pnl"):
            v = d[key]
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[key] = None
        return d


def _compute_metrics(
    pnl_array: np.ndarray,
    tier: str,
    regime: str | None,
    window: int,
) -> TierMetrics:
    """Compute TierMetrics from a 1-D float array of P&L values.

    Args:
        pnl_array: 1-D numpy array of per-trade P&L values (can be empty).
        tier:      Signal tier label.
        regime:    Regime label or None for all-regime aggregate.
        window:    Requested window size (informational — actual n may be smaller).

    Returns:
        TierMetrics instance.
    """
    n = len(pnl_array)
    if n == 0:
        return TierMetrics(
            tier=tier,
            n_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            sharpe=0.0,
            avg_pnl=0.0,
            total_pnl=0.0,
            regime=regime,
            window=window,
        )

    wins = pnl_array[pnl_array > 0]
    losses = pnl_array[pnl_array <= 0]

    win_rate = float(len(wins)) / n

    gross_profit = float(wins.sum()) if len(wins) > 0 else 0.0
    gross_loss = float(losses.sum()) if len(losses) > 0 else 0.0  # negative number
    if gross_loss == 0.0:
        # No losing trades — profit factor is infinite
        profit_factor = float("inf")
    else:
        profit_factor = gross_profit / abs(gross_loss)

    avg_pnl = float(pnl_array.mean())
    total_pnl = float(pnl_array.sum())

    std_pnl = float(pnl_array.std())
    if std_pnl == 0.0:
        sharpe = 0.0
    else:
        sharpe = avg_pnl / std_pnl * math.sqrt(_TRADING_DAYS)

    return TierMetrics(
        tier=tier,
        n_trades=n,
        win_rate=win_rate,
        profit_factor=profit_factor,
        sharpe=sharpe,
        avg_pnl=avg_pnl,
        total_pnl=total_pnl,
        regime=regime,
        window=window,
    )


class PerformanceTracker:
    """Computes rolling-window P&L metrics per signal tier and HMM regime.

    Per D-22: Rolling windows of 50, 200, 500 trades.
    Per D-23: Per-regime breakdown slices metrics by HMM regime state.

    Usage:
        tracker = PerformanceTracker()
        metrics = tracker.compute(trade_rows)
        # Or async:
        metrics = await tracker.fetch_and_compute(event_store)
    """

    def __init__(self, windows: list[int] | None = None) -> None:
        """Initialise the tracker.

        Args:
            windows: Rolling window sizes. Defaults to [50, 200, 500] (D-22).
        """
        self.windows: list[int] = windows if windows is not None else [50, 200, 500]

    def compute(self, trade_rows: list[dict]) -> list[TierMetrics]:
        """Compute all TierMetrics from a list of trade event dicts.

        Pure synchronous — safe to call from any context (T-09-15: < 5ms on 2000 rows).

        Computation steps:
        1. Filter to closed trades (event_type in CLOSED_TYPES).
        2. Sort by ts ascending (chronological order).
        3. For each tier × window: compute all-regime TierMetrics from last N trades.
        4. For each tier × regime × window: compute regime-sliced TierMetrics.

        Args:
            trade_rows: List of dicts from EventStore.fetch_trade_events().
                        Expected keys: event_type, pnl, signal_tier, ts, regime_label.

        Returns:
            Flat list of TierMetrics (all tiers + all regimes + all windows).
        """
        # Step 1: Filter to closed trades only
        closed = [
            row for row in trade_rows
            if row.get("event_type") in _CLOSED_TYPES
        ]

        if not closed:
            # Return zero-filled metrics for all combinations
            result: list[TierMetrics] = []
            for tier in _TIERS:
                for window in self.windows:
                    result.append(_compute_metrics(np.array([], dtype=np.float64), tier, None, window))
                for regime in _REGIMES:
                    for window in self.windows:
                        result.append(_compute_metrics(np.array([], dtype=np.float64), tier, regime, window))
            return result

        # Step 2: Sort by ts ascending
        closed.sort(key=lambda r: float(r.get("ts") or 0.0))

        result = []

        for tier in _TIERS:
            # All trades for this tier (sorted asc)
            tier_rows = [r for r in closed if r.get("signal_tier") == tier]
            tier_pnl = np.array([float(r.get("pnl") or 0.0) for r in tier_rows], dtype=np.float64)

            # Step 3: All-regime metrics per window
            for window in self.windows:
                window_pnl = tier_pnl[-window:] if len(tier_pnl) > 0 else tier_pnl
                result.append(_compute_metrics(window_pnl, tier, None, window))

            # Step 4: Per-regime sliced metrics
            for regime in _REGIMES:
                regime_rows = [r for r in tier_rows if r.get("regime_label") == regime]
                regime_pnl = np.array(
                    [float(r.get("pnl") or 0.0) for r in regime_rows], dtype=np.float64
                )
                for window in self.windows:
                    window_pnl = regime_pnl[-window:] if len(regime_pnl) > 0 else regime_pnl
                    result.append(_compute_metrics(window_pnl, tier, regime, window))

        return result

    async def fetch_and_compute(
        self,
        store: "EventStore",
        limit: int = 2000,
    ) -> list[TierMetrics]:
        """Fetch trade events from EventStore and compute metrics.

        Args:
            store: EventStore instance (must be initialized).
            limit: Maximum trade rows to fetch (default 2000).

        Returns:
            List of TierMetrics — same as compute() output.
        """
        trade_rows = await store.fetch_trade_events(limit=limit)
        return self.compute(trade_rows)
