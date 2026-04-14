"""WalkForwardTracker — per-category × per-regime outcome resolution (phase 12-05).

Records every signal at bar-close and resolves it at the 5/10/20-bar horizons
against the live price stream. Outcomes are labeled CORRECT / INCORRECT /
NEUTRAL / EXPIRED, where EXPIRED flags signals whose horizon would span the
RTH session close (FOOTGUN 1). EXPIRED outcomes are persisted to EventStore
but excluded from rolling-Sharpe statistics.

Sliced by the 8 category groups that match ``WeightFile.weights`` (phase 09-02)
and by the HMM regime state at entry (phase 09-02 HMMRegimeDetector). For each
(category, regime) cell the tracker maintains a rolling 200-signal in-memory
window of realized pnl_ticks and computes Sharpe = mean/std. Cells whose
rolling Sharpe falls below ``disable_sharpe_threshold`` are auto-disabled;
subsequent ``recovery_window`` signals with Sharpe above
``recovery_sharpe_threshold`` re-enable them. Disabled cells propagate to
the LightGBM meta-learner via ``WeightFile.regime_adjustments`` — see
``deep6.ml.weight_loader.apply_walk_forward_overrides``.

Persistence LOCKED to EventStore (phase 09-01 + new walk_forward_outcomes
table) — **no JSON-on-disk sink** (FOOTGUN 2).
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

import structlog

log = structlog.get_logger(__name__)
_stdlog = logging.getLogger("deep6.orderflow.walk_forward_live")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PendingOutcome:
    """One pending resolution, one per (signal, horizon)."""

    category: str
    regime: str
    direction: str            # "LONG" / "SHORT"
    entry_price: float
    entry_bar_index: int
    session_id: str
    signal_event_id: Optional[int]
    horizon: int
    # Whether this pending was flagged EXPIRED at record time (bars_until_close
    # < horizon). Kept on the pending list so the resolution pass still writes
    # the EXPIRED row at horizon; _record_pnl skips EXPIRED rows from the
    # Sharpe cache.
    will_expire: bool = False


@dataclass
class ResolvedOutcome:
    """One resolved outcome, emitted on update_price."""

    category: str
    regime: str
    direction: str
    entry_price: float
    entry_bar_index: int
    session_id: str
    horizon: int
    outcome_label: str         # CORRECT / INCORRECT / NEUTRAL / EXPIRED
    pnl_ticks: float
    resolved_at_bar_index: int
    resolved_at_ts: float
    signal_event_id: Optional[int] = None


# ---------------------------------------------------------------------------
# WalkForwardTracker
# ---------------------------------------------------------------------------


class WalkForwardTracker:
    """Rolling per-category × per-regime walk-forward tracker.

    Inputs are driven entirely through two methods:
      - ``record_signal`` at bar-close when the scorer emits a voting category
      - ``update_price`` at every subsequent bar-close; returns resolved rows

    ``get_weights_override`` returns the regime → category → multiplier map
    consumed by the LightGBM fusion weight loader. Disabled cells map to 0.0;
    all other cells default to 1.0.
    """

    def __init__(
        self,
        store: Any,                                      # EventStore
        horizons: tuple[int, ...] = (5, 10, 20),
        sharpe_window: int = 200,
        disable_sharpe_threshold: float = 0.0,
        recovery_sharpe_threshold: float = 0.3,
        recovery_window: int = 50,
        neutral_threshold_ticks: float = 0.5,
        max_pending: int = 1000,
        session_close_buffer_bars: int = 20,
    ) -> None:
        self.store = store
        self.horizons = tuple(sorted(horizons))
        self.sharpe_window = int(sharpe_window)
        self.disable_sharpe_threshold = float(disable_sharpe_threshold)
        self.recovery_sharpe_threshold = float(recovery_sharpe_threshold)
        self.recovery_window = int(recovery_window)
        self.neutral_threshold_ticks = float(neutral_threshold_ticks)
        self.max_pending = int(max_pending)
        self.session_close_buffer_bars = int(session_close_buffer_bars)

        # Pending outcomes — bounded deque; oldest dropped silently when full
        # (threat T-12-05-01 mitigation).
        self._pending: Deque[PendingOutcome] = deque(maxlen=self.max_pending)

        # Rolling per-cell pnl cache: (regime, category) -> deque of pnl_ticks.
        # EXPIRED pnl values are NOT recorded here — Sharpe excludes them.
        self._pnl_cache: dict[tuple[str, str], Deque[float]] = {}

        # Per-cell disabled state + count-since-disable for recovery
        # windowing.  bool: True = disabled. int: number of non-EXPIRED
        # resolutions observed since the disable event (reset on disable/enable).
        self._disabled: dict[tuple[str, str], bool] = {}
        self._since_disable: dict[tuple[str, str], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def record_signal(
        self,
        category: str,
        regime: str,
        direction: str,
        entry_price: float,
        bar_index: int,
        session_id: str,
        signal_event_id: Optional[int] = None,
        bars_until_rth_close: int = 10_000,
    ) -> None:
        """Record one signal at bar-close — one pending entry per horizon."""
        for h in self.horizons:
            will_expire = bars_until_rth_close < h
            self._pending.append(
                PendingOutcome(
                    category=category,
                    regime=regime,
                    direction=direction,
                    entry_price=float(entry_price),
                    entry_bar_index=int(bar_index),
                    session_id=session_id,
                    signal_event_id=signal_event_id,
                    horizon=h,
                    will_expire=will_expire,
                )
            )

    async def update_price(
        self,
        close_price: float,
        bar_index: int,
        session_id: str,
        bars_until_rth_close: int = 10_000,
    ) -> list[ResolvedOutcome]:
        """Resolve any pending outcomes whose horizon has elapsed.

        Returns the list of resolutions emitted in this call. Each row is
        also persisted to EventStore.walk_forward_outcomes.
        """
        resolved: list[ResolvedOutcome] = []
        still_pending: list[PendingOutcome] = []
        ts = time.time()

        while self._pending:
            p = self._pending.popleft()
            target_bar = p.entry_bar_index + p.horizon
            # Only resolve same-session entries; cross-session carry-over is
            # also EXPIRED (session_id changed before horizon elapsed).
            if p.session_id != session_id:
                label = "EXPIRED"
                pnl = 0.0
                row = self._build_resolved(p, pnl, label, bar_index, ts)
                await self._persist(row)
                resolved.append(row)
                continue

            if bar_index < target_bar:
                # Not yet due — put back.
                still_pending.append(p)
                continue

            # Horizon elapsed — compute pnl and label.
            pnl = self._compute_pnl_ticks(p.direction, p.entry_price, close_price)
            if p.will_expire:
                label = "EXPIRED"
            elif abs(pnl) < self.neutral_threshold_ticks:
                label = "NEUTRAL"
            elif pnl > 0:
                label = "CORRECT"
            else:
                label = "INCORRECT"

            row = self._build_resolved(p, pnl, label, bar_index, ts)
            await self._persist(row)
            resolved.append(row)

            # Update cache + disable/recovery logic (EXPIRED excluded)
            if label != "EXPIRED":
                self._record_pnl(p.category, p.regime, pnl)
                self._maybe_update_disable_state(p.category, p.regime)

        # Restore remaining.
        for p in still_pending:
            self._pending.append(p)

        return resolved

    def get_weights_override(self) -> dict[str, dict[str, float]]:
        """Regime → category → multiplier (0.0 for disabled cells, 1.0 else).

        Only disabled cells appear — callers merge into existing
        ``WeightFile.regime_adjustments`` via
        ``deep6.ml.weight_loader.apply_walk_forward_overrides``.
        """
        out: dict[str, dict[str, float]] = {}
        for (regime, category), is_disabled in self._disabled.items():
            if not is_disabled:
                continue
            out.setdefault(regime, {})[category] = 0.0
        return out

    def is_disabled(self, category: str, regime: str) -> bool:
        return bool(self._disabled.get((regime, category), False))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_pnl_ticks(direction: str, entry_price: float, close_price: float) -> float:
        diff = close_price - entry_price
        if direction.upper() == "SHORT":
            return -diff
        return diff

    def _build_resolved(
        self,
        p: PendingOutcome,
        pnl: float,
        label: str,
        resolved_bar_index: int,
        ts: float,
    ) -> ResolvedOutcome:
        return ResolvedOutcome(
            category=p.category,
            regime=p.regime,
            direction=p.direction,
            entry_price=p.entry_price,
            entry_bar_index=p.entry_bar_index,
            session_id=p.session_id,
            horizon=p.horizon,
            outcome_label=label,
            pnl_ticks=float(pnl),
            resolved_at_bar_index=int(resolved_bar_index),
            resolved_at_ts=ts,
            signal_event_id=p.signal_event_id,
        )

    async def _persist(self, r: ResolvedOutcome) -> None:
        """Write one resolved outcome to EventStore. Swallow DB errors so a
        slow / broken DB never breaks the bar-close path (T-12-05-04)."""
        try:
            await self.store.record_walk_forward_outcome(
                category=r.category,
                regime=r.regime,
                direction=r.direction,
                entry_price=r.entry_price,
                entry_bar_index=r.entry_bar_index,
                session_id=r.session_id,
                horizon=r.horizon,
                outcome_label=r.outcome_label,
                pnl_ticks=r.pnl_ticks,
                resolved_at_ts=r.resolved_at_ts,
                signal_event_id=r.signal_event_id,
            )
        except Exception:
            log.exception(
                "walk_forward.persist_failed",
                category=r.category,
                regime=r.regime,
                horizon=r.horizon,
            )

    def _record_pnl(self, category: str, regime: str, pnl: float) -> None:
        key = (regime, category)
        dq = self._pnl_cache.get(key)
        if dq is None:
            dq = deque(maxlen=self.sharpe_window)
            self._pnl_cache[key] = dq
        dq.append(float(pnl))
        # Count recoveries-eligible samples since last disable
        if self._disabled.get(key, False):
            self._since_disable[key] = self._since_disable.get(key, 0) + 1

    def _compute_rolling_sharpe(
        self, category: str, regime: str
    ) -> Optional[float]:
        """Return Sharpe = mean / (std + 1e-9) over the rolling window.

        Returns None if the cell has fewer than ``sharpe_window`` samples
        (FOOTGUN 5: gate to avoid disabling on small-sample noise).
        """
        key = (regime, category)
        dq = self._pnl_cache.get(key)
        if dq is None or len(dq) < self.sharpe_window:
            return None
        vals = list(dq)
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        std = math.sqrt(var)
        return mean / (std + 1e-9)

    def _compute_recovery_sharpe(
        self, category: str, regime: str
    ) -> Optional[float]:
        """Sharpe over the last ``recovery_window`` samples."""
        key = (regime, category)
        dq = self._pnl_cache.get(key)
        if dq is None or len(dq) < self.recovery_window:
            return None
        vals = list(dq)[-self.recovery_window :]
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        std = math.sqrt(var)
        return mean / (std + 1e-9)

    def _maybe_update_disable_state(self, category: str, regime: str) -> None:
        key = (regime, category)
        currently_disabled = self._disabled.get(key, False)
        if currently_disabled:
            # Recovery path: check after recovery_window non-EXPIRED samples
            # since disable.
            seen = self._since_disable.get(key, 0)
            if seen < self.recovery_window:
                return
            sharpe = self._compute_recovery_sharpe(category, regime)
            if sharpe is not None and sharpe > self.recovery_sharpe_threshold:
                self._disabled[key] = False
                self._since_disable[key] = 0
                log.info(
                    "walk_forward.cell_recovered",
                    category=category,
                    regime=regime,
                    sharpe=sharpe,
                )
                _stdlog.info(
                    "cell recovered: %s/%s sharpe=%.3f",
                    category,
                    regime,
                    sharpe,
                )
            else:
                # Reset window for another shot (rolling 50-signal check).
                self._since_disable[key] = 0
            return

        # Disable path
        sharpe = self._compute_rolling_sharpe(category, regime)
        if sharpe is None:
            return
        if sharpe < self.disable_sharpe_threshold:
            self._disabled[key] = True
            self._since_disable[key] = 0
            log.warning(
                "walk_forward.cell_disabled",
                category=category,
                regime=regime,
                sharpe=sharpe,
            )
            _stdlog.warning(
                "cell disabled: %s/%s sharpe=%.3f",
                category,
                regime,
                sharpe,
            )
