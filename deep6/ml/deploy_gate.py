"""Deploy gate — 3-part weight deployment validation.

Enforces:
1. Operator confirmation token (T-09-04: DEPLOY_SECRET)
2. WFE >= 0.70 (D-16, D-19)
3. Minimum 200 OOS trades total (D-17)
4. Weight cap: no single signal > 3x baseline (D-15)

Security: T-09-11: structlog audit on every deploy attempt.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep6.ml.lgbm_trainer import WeightFile

log = logging.getLogger(__name__)


@dataclass
class DeployDecision:
    """Result of a DeployGate.evaluate() call.

    allowed: True only when all gates pass.
    reason: human-readable explanation of pass or failure.
    wfe: candidate WFE value (may be None if candidate has no wfe set).
    oos_counts: per-signal-tier OOS trade counts at evaluation time.
    weight_cap_violations: list of signal names that exceed the 3x cap.
    before_after: {"before": WeightFile.to_json() | None, "after": WeightFile.to_json()}
    """
    allowed: bool
    reason: str
    wfe: float | None = None
    oos_counts: dict[str, int] = field(default_factory=dict)
    weight_cap_violations: list[str] = field(default_factory=list)
    before_after: dict[str, Any] | None = None


class DeployGate:
    """Enforces 3-part gate before weight deployment.

    Usage:
        gate = DeployGate()
        token = gate.generate_token()
        # Show token to operator via GET /ml/deploy-token
        decision = gate.evaluate(candidate, current, oos_counts, operator_token, token)
        if decision.allowed:
            loader.write_atomic(candidate)
    """

    def __init__(
        self,
        wfe_threshold: float = 0.70,
        min_oos_trades: int = 200,
        weight_cap: float = 3.0,
    ) -> None:
        self.wfe_threshold = wfe_threshold
        self.min_oos_trades = min_oos_trades
        self.weight_cap = weight_cap
        self._pending_token: str | None = None

    def generate_token(self) -> str:
        """Generate and store a one-time confirmation token.

        Returns a 32-char hex string (16 bytes entropy).
        The generated token is stored as self._pending_token.
        Operators copy this from GET /ml/deploy-token before submitting
        POST /weights/deploy.
        """
        token = secrets.token_hex(16)
        self._pending_token = token
        return token

    def evaluate(
        self,
        candidate: "WeightFile",
        current: "WeightFile | None",
        oos_counts: dict[str, int],
        confirmation_token: str,
        expected_token: str,
    ) -> DeployDecision:
        """Evaluate all 3 deployment gates.

        Gate order (fail-fast):
          1. Token match
          2. WFE threshold
          3. OOS trade count (aggregate)
          4. Weight cap (collects violations but only blocks without override)

        T-09-11: All deploy attempts are logged regardless of outcome.

        Args:
            candidate: WeightFile produced by latest training run.
            current: Currently deployed WeightFile, or None if first deploy.
            oos_counts: Per-tier trade counts from EventStore.count_oos_trades_per_signal().
            confirmation_token: Token provided by operator in deploy request.
            expected_token: Server-side expected token (from generate_token() or DEPLOY_SECRET).

        Returns:
            DeployDecision with allowed=True only when all gates pass.
        """
        before_after = {
            "before": current.to_json() if current is not None else None,
            "after": candidate.to_json(),
        }

        # --- Gate 1: Confirmation token ---
        if confirmation_token != expected_token:
            log.warning(
                "deploy_gate.token_mismatch",
                extra={"wfe": candidate.wfe, "provided_len": len(confirmation_token)},
            )
            return DeployDecision(
                allowed=False,
                reason="Invalid confirmation token",
                wfe=candidate.wfe,
                oos_counts=oos_counts,
                before_after=before_after,
            )

        # --- Gate 2: WFE threshold (D-16) ---
        if candidate.wfe is None or candidate.wfe < self.wfe_threshold:
            log.warning(
                "deploy_gate.wfe_failed",
                extra={"wfe": candidate.wfe, "threshold": self.wfe_threshold},
            )
            return DeployDecision(
                allowed=False,
                reason=f"WFE {candidate.wfe} < {self.wfe_threshold}",
                wfe=candidate.wfe,
                oos_counts=oos_counts,
                before_after=before_after,
            )

        # --- Gate 3: OOS trade count (D-17) ---
        total_oos = sum(oos_counts.values())
        if total_oos < self.min_oos_trades:
            log.warning(
                "deploy_gate.oos_insufficient",
                extra={"total_oos": total_oos, "required": self.min_oos_trades},
            )
            return DeployDecision(
                allowed=False,
                reason=f"Insufficient OOS trades: {total_oos} < {self.min_oos_trades}",
                wfe=candidate.wfe,
                oos_counts=oos_counts,
                before_after=before_after,
            )

        # --- Gate 4: Weight cap check (D-15) ---
        violations = [
            signal
            for signal, weight in candidate.weights.items()
            if weight > self.weight_cap
        ]

        if violations:
            log.warning(
                "deploy_gate.weight_cap_exceeded",
                extra={"violations": violations, "cap": self.weight_cap},
            )
            return DeployDecision(
                allowed=False,
                reason=f"Weight cap {self.weight_cap}x exceeded for: {violations}",
                wfe=candidate.wfe,
                oos_counts=oos_counts,
                weight_cap_violations=violations,
                before_after=before_after,
            )

        # --- All gates pass ---
        log.info(
            "deploy_gate.approved",
            extra={
                "wfe": candidate.wfe,
                "total_oos": total_oos,
                "n_samples": candidate.n_samples,
                "training_date": candidate.training_date,
            },
        )
        return DeployDecision(
            allowed=True,
            reason="All gates passed",
            wfe=candidate.wfe,
            oos_counts=oos_counts,
            weight_cap_violations=[],
            before_after=before_after,
        )
