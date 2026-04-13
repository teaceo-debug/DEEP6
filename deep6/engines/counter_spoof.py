"""E3 CounterSpoofEngine — ENG-03. Wasserstein-1 DOM distribution monitor.

Alert-only — per D-07, not a trade signal. Informational flag only.

Tracks bid-side DOM distributions every 100ms (D-04 — NOT called from the 1000/sec
DOM callback path). Computes Wasserstein-1 distance between consecutive bid
distributions to detect sudden structural changes (spoof setup/teardown).

Also detects large-order cancels: a price level that had > 50 contracts and drops
to < 10 within 200ms without a matching trade (D-06).

Usage (from asyncio periodic task, not from DOM callback):

    engine = CounterSpoofEngine()

    async def _sample_dom():
        while True:
            await asyncio.sleep(0.1)
            bp, bs, ap, as_ = dom_state.snapshot()
            engine.ingest_snapshot(bp, bs, ap, as_, time.monotonic())
            anomaly = engine.get_w1_anomaly()
            alerts  = engine.get_spoof_alerts()
            if anomaly or alerts:
                handle_spoof_signal(anomaly, alerts)

NOTE: ingest_snapshot is designed for asyncio.TimerHandle or a periodic asyncio
task (e.g. asyncio.get_event_loop().call_later(0.1, ...)). It must NOT be called
from the hot DOM callback path (1000/sec).

Per D-13: When DOM has no history, get_w1_anomaly() returns None and
get_spoof_alerts() returns [].
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Optional

from scipy.stats import wasserstein_distance

from deep6.engines.signal_config import CounterSpoofConfig
from deep6.state.dom import LEVELS

# Re-export DOMSnapshot type for consumers that import from here.
DOMSnapshot = tuple  # (bid_prices, bid_sizes, ask_prices, ask_sizes) lists of LEVELS


@dataclass
class SpoofAlert:
    """Alert fired when a large order at a price level disappears rapidly.

    Per D-07: informational only — not a trade signal.

    Fields:
        price:        Price level where the cancel was detected.
        prior_size:   Order size at the level before the cancel.
        current_size: Order size at the level after the cancel.
        elapsed_ms:   Milliseconds between the large-order recording and the cancel.
        detail:       Diagnostic string.
    """
    price: float
    prior_size: float
    current_size: float
    elapsed_ms: float
    detail: str


class CounterSpoofEngine:
    """E3 Wasserstein-1 DOM distribution monitor + large-order cancel detector (ENG-03).

    All state is per-instance — no globals. Thread-safe for asyncio single-threaded use.
    Must complete ingest_snapshot in < 0.5ms.
    """

    def __init__(self, config: CounterSpoofConfig | None = None) -> None:
        self.config = config if config is not None else CounterSpoofConfig()
        self._snapshot_history: deque = deque(maxlen=self.config.spoof_history_len)
        self._w1_history: deque = deque(maxlen=self.config.spoof_history_len)
        # T-04-07: bounded by LEVELS cap (enforced in ingest_snapshot)
        self._level_timestamps: dict[float, tuple[float, float]] = {}  # price → (size, ts)
        self._pending_alerts: list[SpoofAlert] = []
        # Track which snapshots each level was last seen in (for pruning — T-04-07)
        self._level_last_seen: dict[float, int] = {}  # price → snapshot_count
        self._snapshot_count: int = 0

    def ingest_snapshot(
        self,
        bid_prices: list[float],
        bid_sizes: list[float],
        ask_prices: list[float],
        ask_sizes: list[float],
        timestamp: float,
    ) -> None:
        """Process a periodic DOM snapshot (every 100ms, per D-04).

        Computes W1 distance vs previous snapshot, detects large-order cancels.
        Must complete in < 0.5ms — called from asyncio timer task, not DOM callback.

        Args:
            bid_prices: List of LEVELS bid prices (index 0 = best bid).
            bid_sizes:  List of LEVELS bid sizes.
            ask_prices: List of LEVELS ask prices.
            ask_sizes:  List of LEVELS ask sizes.
            timestamp:  time.monotonic() at snapshot time.
        """
        self._snapshot_count += 1
        cfg = self.config

        # Step 1: Build current bid distribution (non-zero sizes only for W1).
        curr_bid_sizes = list(bid_sizes)  # shallow copy — length LEVELS

        # Step 2: Compute W1 distance vs previous snapshot if history exists.
        if self._snapshot_history:
            prev_ts, prev_bid_sizes = self._snapshot_history[-1]

            # T-04-05: Pad both to same length and guard against all-zero arrays.
            prev_arr = list(prev_bid_sizes)
            curr_arr = list(curr_bid_sizes)
            # Both already LEVELS long — ensure same length
            n = max(len(prev_arr), len(curr_arr))
            while len(prev_arr) < n:
                prev_arr.append(0.0)
            while len(curr_arr) < n:
                curr_arr.append(0.0)

            # Guard: if both are all zeros, W1=0 (wasserstein_distance handles it but
            # guard avoids potential edge cases with equal-weight distributions).
            prev_sum = sum(prev_arr)
            curr_sum = sum(curr_arr)
            if prev_sum == 0.0 and curr_sum == 0.0:
                w1 = 0.0
            elif prev_sum == 0.0:
                # No previous distribution: treat as zero distance.
                w1 = 0.0
            elif curr_sum == 0.0:
                # DOM went empty.
                w1 = 0.0
            else:
                # Use price level indices as positions for W1 (integer 0..N-1).
                positions = list(range(n))
                w1 = wasserstein_distance(positions, positions,
                                          u_weights=prev_arr, v_weights=curr_arr)
            self._w1_history.append(w1)

        # Step 3: Append current snapshot to history.
        self._snapshot_history.append((timestamp, curr_bid_sizes))

        # Step 4: Cancel detection (D-06).
        # For each level with a recorded large order, check if it has dropped below
        # cancel_threshold within cancel_window_ms.
        large = cfg.spoof_large_order
        cancel_thresh = cfg.spoof_cancel_threshold
        cancel_window_s = cfg.spoof_cancel_window_ms / 1000.0

        # Check existing tracked large orders for cancels.
        levels_to_remove: list[float] = []
        for price, (prior_size, recorded_ts) in self._level_timestamps.items():
            # Find the current size at this price level.
            try:
                idx = bid_prices.index(price)
                curr_size = bid_sizes[idx]
            except ValueError:
                # Price not in current bid prices — treat as zero.
                curr_size = 0.0

            elapsed = timestamp - recorded_ts
            if curr_size < cancel_thresh and elapsed < cancel_window_s:
                # Potential spoof cancel (D-06)
                self._pending_alerts.append(SpoofAlert(
                    price=price,
                    prior_size=prior_size,
                    current_size=curr_size,
                    elapsed_ms=elapsed * 1000.0,
                    detail=(
                        f"Large order cancel: {prior_size:.0f} → {curr_size:.0f} "
                        f"contracts at {price} in {elapsed * 1000:.1f}ms"
                    ),
                ))
                levels_to_remove.append(price)

        for p in levels_to_remove:
            self._level_timestamps.pop(p, None)
            self._level_last_seen.pop(p, None)

        # Record new large orders for tracking.
        for i in range(min(len(bid_prices), LEVELS)):
            price = bid_prices[i]
            size = bid_sizes[i]
            if size >= large:
                # Update or create entry.
                self._level_timestamps[price] = (size, timestamp)
                self._level_last_seen[price] = self._snapshot_count

        # T-04-07: Prune stale entries — levels not seen in last 5 snapshots.
        stale_cutoff = self._snapshot_count - 5
        stale_prices = [
            p for p, last in self._level_last_seen.items()
            if last <= stale_cutoff
        ]
        for p in stale_prices:
            self._level_timestamps.pop(p, None)
            self._level_last_seen.pop(p, None)

        # T-04-07: Hard cap at LEVELS to prevent unbounded growth.
        if len(self._level_timestamps) > LEVELS:
            # Keep only the most recently seen levels.
            sorted_by_recency = sorted(
                self._level_last_seen.items(), key=lambda kv: kv[1], reverse=True
            )
            keep = {p for p, _ in sorted_by_recency[:LEVELS]}
            for p in list(self._level_timestamps.keys()):
                if p not in keep:
                    self._level_timestamps.pop(p)
                    self._level_last_seen.pop(p, None)

    def get_w1_anomaly(self) -> Optional[float]:
        """Return current W1 distance if it's a statistical anomaly, else None.

        Returns None if:
          - Fewer than w1_min_samples W1 measurements in history (D-05).
          - Rolling std < 1e-9 (T-04-06: all identical distances — no signal).
          - Latest W1 <= mean + w1_anomaly_sigma * std.

        Returns:
            float: The anomalous W1 distance, or None.
        """
        cfg = self.config
        if len(self._w1_history) < cfg.w1_min_samples:
            return None

        vals = list(self._w1_history)
        n = len(vals)
        mean = sum(vals) / n
        variance = sum((v - mean) ** 2 for v in vals) / n
        std = math.sqrt(variance)

        # T-04-06: Guard — if std near zero, no anomaly possible.
        if std < 1e-9:
            return None

        latest = vals[-1]
        if latest > mean + cfg.w1_anomaly_sigma * std:
            return latest
        return None

    def get_spoof_alerts(self) -> list[SpoofAlert]:
        """Return all pending SpoofAlerts and clear the internal buffer.

        Per D-07: alerts are informational only — not trade signals.

        Returns:
            List of SpoofAlert instances since last call. Empty list if none.
        """
        alerts = list(self._pending_alerts)
        self._pending_alerts.clear()
        return alerts

    def reset(self) -> None:
        """Clear all internal state (for session start or test teardown)."""
        self._snapshot_history.clear()
        self._w1_history.clear()
        self._level_timestamps.clear()
        self._level_last_seen.clear()
        self._pending_alerts.clear()
        self._snapshot_count = 0
