"""Execution layer configuration — all Phase 8 thresholds in one frozen dataclass.

Per D-01..D-22 from .planning/phases/08-auto-execution-risk-layer/08-CONTEXT.md.
frozen=True prevents mutation between paper/live mode transitions (T-08-01).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class ExecutionConfig:
    """All Phase 8 execution thresholds in one immutable config.

    Covers D-01..D-22 as defined in 08-CONTEXT.md.
    frozen=True prevents mutation after instantiation (T-08-01 mitigation).
    """

    # D-04/D-05: Stop placement
    stop_buffer_ticks: int = 2          # Ticks beyond zone boundary
    max_stop_atr_mult: float = 2.0      # Max stop distance = 2x ATR

    # D-07/D-08: Target placement
    target_rr_min: float = 1.5          # Minimum R:R (secondary target, D-08)

    # D-03: Entry timing
    entry_delay_seconds: float = 3.0    # Max wait for better fill when prob < threshold
    entry_prob_threshold: float = 0.55  # E5 probability below this triggers delay

    # D-09: Max hold bars
    max_hold_bars: int = 10

    # D-10: Daily loss circuit breaker
    daily_loss_limit: float = 500.0     # USD per contract

    # D-11: Consecutive loss pause
    consecutive_loss_limit: int = 3
    pause_minutes: float = 30.0

    # D-12: Position size
    max_position_contracts: int = 3     # Paper default; live = configurable

    # D-13: Max trades per day
    max_trades_per_day: int = 10

    # Heat management: max aggregate open-risk (USD) across all open positions
    max_open_risk_usd: float = 100.0

    # Risk-per-trade R unit (USD) used for daily_R_ratio and graduated DD response
    risk_per_trade_R: float = 100.0

    # Minimum minutes between a closed loss and a new entry in the same direction
    loss_cooldown_minutes: float = 10.0

    # D-18/D-19/D-20: Paper trading gate
    paper_trading_days: int = 30
    paper_slippage_fixed_ticks: int = 1
    paper_slippage_random_ticks: int = 1  # 0 or 1 additional tick (random)


@dataclass
class ExecutionDecision:
    """Output of ExecutionEngine.evaluate() for one bar.

    action values:
      "ENTER"        — submit bracket order now
      "WAIT_CONFIRM" — TYPE_B signal, wait for operator confirmation (D-02)
      "SKIP"         — gate blocked (risk/regime/frozen/tier)
      "FROZEN"       — FreezeGuard is active; no orders (D-14)

    Per T-08-04: no dollar amounts or account IDs stored here.
    Only price levels and ticks are logged — operator sees these in dashboard.
    """
    action: str
    reason: str
    side: OrderSide | None = None
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    stop_ticks: float = 0.0
    signal_score: float = 0.0
    signal_tier: str = ""
