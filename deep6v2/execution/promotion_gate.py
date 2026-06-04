from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PromotionConfig:
    required_sessions: int = 30
    min_cumulative_pnl: float = 0.0
    max_drawdown_limit: float = -2000.0
    min_win_rate: float = 0.40
    max_freeze_duration_seconds: int = 300


@dataclass
class PromotionStatus:
    sessions_completed: int
    cumulative_pnl: float
    max_drawdown: float
    win_rate: float
    crash_free: bool
    risk_gates_exercised: bool
    eligible: bool
    blocking_reasons: list[str] = field(default_factory=list)


class PromotionGate:
    """Paper-to-live promotion criteria evaluator."""

    def __init__(self, config: PromotionConfig | None = None) -> None:
        self._config = config or PromotionConfig()
        self._sessions: list[dict] = []

    def record_session(self, pnl: float, win_rate: float, max_dd: float, *, crashed: bool = False) -> None:
        self._sessions.append({"pnl": pnl, "win_rate": win_rate, "max_dd": max_dd, "crashed": crashed})

    def evaluate(self) -> PromotionStatus:
        reasons: list[str] = []
        n = len(self._sessions)
        cum_pnl = sum(s["pnl"] for s in self._sessions)
        max_dd = min((s["max_dd"] for s in self._sessions), default=0.0)
        avg_wr = sum(s["win_rate"] for s in self._sessions) / n if n else 0.0
        crash_free = not any(s["crashed"] for s in self._sessions)

        if n < self._config.required_sessions:
            reasons.append(f"need_{self._config.required_sessions}_sessions_have_{n}")
        if cum_pnl < self._config.min_cumulative_pnl:
            reasons.append("negative_cumulative_pnl")
        if max_dd < self._config.max_drawdown_limit:
            reasons.append("max_drawdown_exceeded")
        if avg_wr < self._config.min_win_rate:
            reasons.append("win_rate_below_minimum")
        if not crash_free:
            reasons.append("session_crash_detected")

        return PromotionStatus(
            sessions_completed=n,
            cumulative_pnl=cum_pnl,
            max_drawdown=max_dd,
            win_rate=avg_wr,
            crash_free=crash_free,
            risk_gates_exercised=True,
            eligible=len(reasons) == 0,
            blocking_reasons=reasons,
        )


__all__ = ["PromotionConfig", "PromotionGate", "PromotionStatus"]
