"""SetupTracker — 5-state setup lifecycle machine (phase 12-04).

States: SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN → SCANNING

Consumes ScorerResult (from deep6.scoring.scorer) and SlingshotResult (from
deep6.orderflow.slingshot) — shape-based, so tests can drop in lightweight
fakes without pulling the full scoring pipeline.

Critical invariants (LOCKED per 12-CONTEXT.md):

1. MANAGING → COOLDOWN is NEVER auto-advanced by a bar tick. It transitions
   only via an explicit close_trade(setup_id, outcome) call from the
   execution layer (PaperTrader / RithmicExecutor).

2. Failsafe: if bars_managing exceeds `managing_failsafe_bars` (default 30),
   the tracker emits a WARNING log and force-transitions to COOLDOWN as a
   wedge-prevention guardrail. This is an emergency brake, not a normal path.

3. Soak bonus (DEVELOPING): current_weight() ramps linearly from 1.0 at
   soak_bars=0 to 5.0 at soak_bars=10+ using formula::

       weight = 1.0 + 0.4 * min(soak_bars, 10)

   Each bar that a DEVELOPING setup persists (aligned direction, non-noise
   tier) adds one soak bar.

4. Slingshot bypass: if SlingshotResult.triggers_state_bypass is True and the
   tracker is in SCANNING or DEVELOPING, the setup jumps straight to
   TRIGGERED — no soak required. This is the GEX-wall short-circuit.

5. Setup IDs are prefixed by the timeframe label ("1m-..." / "5m-...") so
   the execution layer can route close_trade() events unambiguously even
   when 1m and 5m run in parallel.

Reference footgun (DO NOT PORT): the original kronos-tv-autotrader
setup_tracker.py auto-transitioned MANAGING → COOLDOWN after 1 cycle. That
pattern is explicitly rejected here — see plan 12-04 FOOTGUN 1 and
plan-checker flag.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

log = structlog.get_logger(__name__)

# Also use stdlib logging so tests using caplog can capture our warnings.
# structlog routes through stdlib by default in the DEEP6 config, but the
# failsafe warning is important enough to log both ways explicitly.
_stdlog = logging.getLogger("deep6.orderflow.setup_tracker")


STATES = ("SCANNING", "DEVELOPING", "TRIGGERED", "MANAGING", "COOLDOWN")


# Tier promotion thresholds. Expressed as strings so tests (and the real
# ScorerResult.tier IntEnum, which str()s as "TYPE_A"/etc. via its .name
# attribute) can both feed them. We read .name if it looks like an enum,
# otherwise fall back to str(). Direction is the same story.
_DEVELOPING_TIERS = frozenset({"TYPE_B", "TYPE_C"})
_TIER_A = "TYPE_A"

# Score thresholds
SCORE_MIN_DEVELOP = 35.0
SCORE_MIN_TIER_A_CROSS = 80.0
SCORE_SOAK_DROP = 25.0  # DEVELOPING below this → reset to SCANNING


@dataclass
class ActiveSetup:
    """State bound to a single in-flight setup.

    setup_id is stable from SCANNING → DEVELOPING → TRIGGERED → MANAGING; the
    COOLDOWN transition clears it so the next scan starts fresh. It is used
    by the execution layer to route close_trade() events.
    """
    setup_id: str
    setup_type: str               # "SOAK", "SLINGSHOT_BYPASS", "TIER_CROSS", ...
    direction: str                # "LONG" | "SHORT"
    entry_score: float
    soak_bars: int = 0
    bars_managing: int = 0
    started_at_bar: int = 0


@dataclass
class SetupTransition:
    """Emitted on every state transition. Logged by SharedState to EventStore.

    Fields chosen to match the setup_transitions table schema added in
    plan 12-04 task 2.
    """
    timeframe: str
    setup_id: str
    from_state: str
    to_state: str
    trigger: str                  # short machine-readable reason code
    weight: float                 # current_weight() at transition time
    bar_index: int
    ts: float = field(default_factory=time.time)


def _name_of(x: Any) -> str:
    """Coerce enum-ish or plain string to uppercase string name."""
    if x is None:
        return ""
    n = getattr(x, "name", None)
    if isinstance(n, str):
        return n.upper()
    return str(x).upper()


def _direction_str(d: Any) -> str:
    """Normalize direction to 'LONG' / 'SHORT' / 'NEUTRAL'.

    Accepts either ScorerResult.direction (int +1/-1/0) or a string
    'LONG'/'SHORT'/'NEUTRAL'.
    """
    if isinstance(d, int):
        if d > 0:
            return "LONG"
        if d < 0:
            return "SHORT"
        return "NEUTRAL"
    s = str(d).upper()
    if s in ("LONG", "SHORT", "NEUTRAL"):
        return s
    # Also tolerate "BULL"/"BEAR"
    if s in ("BULL", "BULLISH"):
        return "LONG"
    if s in ("BEAR", "BEARISH"):
        return "SHORT"
    return "NEUTRAL"


class SetupTracker:
    """5-state setup lifecycle. One instance per timeframe.

    Args:
        timeframe: "1m" / "5m" — used for setup_id prefix and logging labels.
        cooldown_bars: Bars to remain in COOLDOWN before returning to SCANNING.
        managing_failsafe_bars: Emergency brake — bars_managing > this value
            forces COOLDOWN with WARNING log. Default 30.
    """

    def __init__(
        self,
        timeframe: str,
        cooldown_bars: int = 5,
        managing_failsafe_bars: int = 30,
    ) -> None:
        self.timeframe = timeframe
        self.cooldown_bars = cooldown_bars
        self.managing_failsafe_bars = managing_failsafe_bars
        self.state: str = "SCANNING"
        self.active_setup: Optional[ActiveSetup] = None
        self._cooldown_remaining: int = 0

    # ----- public API --------------------------------------------------------

    def current_weight(self) -> float:
        """Soak-based weight multiplier.

        - SCANNING / COOLDOWN: 0.0
        - DEVELOPING: linear 1.0 → 5.0 over 0→10 soak bars
        - TRIGGERED / MANAGING: 5.0 (held at max)
        """
        if self.state in ("SCANNING", "COOLDOWN"):
            return 0.0
        if self.state == "DEVELOPING" and self.active_setup is not None:
            bars = min(self.active_setup.soak_bars, 10)
            return 1.0 + 0.4 * bars
        # TRIGGERED / MANAGING
        return 5.0

    def update(
        self,
        scorer_result: Any,
        slingshot_result: Any,
        current_bar_index: int,
    ) -> Optional[SetupTransition]:
        """Advance the state machine by one bar close.

        Returns a SetupTransition if a state change occurred, else None.
        """
        tier = _name_of(getattr(scorer_result, "tier", "NONE"))
        direction = _direction_str(getattr(scorer_result, "direction", "NEUTRAL"))
        score = float(getattr(scorer_result, "total_score", 0.0))

        sling_fired = bool(getattr(slingshot_result, "fired", False))
        sling_bypass = bool(getattr(slingshot_result, "triggers_state_bypass", False))
        sling_dir = _direction_str(getattr(slingshot_result, "direction", None))

        # -- Slingshot bypass: highest priority, skips DEVELOPING entirely. --
        # Only fires from SCANNING / DEVELOPING (not TRIGGERED/MANAGING — we're
        # already holding a position there).
        if (
            sling_fired
            and sling_bypass
            and sling_dir in ("LONG", "SHORT")
            and self.state in ("SCANNING", "DEVELOPING")
        ):
            return self._bypass_to_triggered(
                direction=sling_dir,
                score=max(score, SCORE_MIN_TIER_A_CROSS),
                bar_index=current_bar_index,
            )

        # -- Normal state dispatch ---------------------------------------------
        if self.state == "SCANNING":
            return self._scanning(tier, direction, score, current_bar_index)
        if self.state == "DEVELOPING":
            return self._developing(tier, direction, score, current_bar_index)
        if self.state == "TRIGGERED":
            return self._triggered(current_bar_index)
        if self.state == "MANAGING":
            return self._managing(current_bar_index)
        if self.state == "COOLDOWN":
            return self._cooldown(current_bar_index)
        return None

    def close_trade(
        self, setup_id: str, outcome: str = "CLOSED"
    ) -> Optional[SetupTransition]:
        """Explicit close from execution layer.

        ONLY path out of MANAGING that is not the failsafe. No-op if:
          - we are not in MANAGING
          - setup_id doesn't match the active setup (stale / cross-wired event)

        The no-op defensive check prevents the tracker from reacting to
        somebody else's fill (e.g., a lingering 5m event arriving at the 1m
        tracker because routing broke).
        """
        if self.state != "MANAGING" or self.active_setup is None:
            return None
        if self.active_setup.setup_id != setup_id:
            log.warning(
                "setup_tracker.close_trade.id_mismatch",
                timeframe=self.timeframe,
                given=setup_id,
                active=self.active_setup.setup_id,
            )
            return None

        # Trigger is the machine-readable reason code; outcome (TARGET_HIT /
        # STOP_HIT / MANUAL_EXIT) is preserved in structured logs but kept out
        # of the trigger string so downstream consumers can match on a stable
        # token.
        log.info(
            "setup_tracker.close_trade",
            timeframe=self.timeframe,
            setup_id=setup_id,
            outcome=outcome,
        )
        return self._to_cooldown(trigger="EXPLICIT_CLOSE", bar_index=-1)

    # ----- private state handlers -------------------------------------------

    def _scanning(
        self, tier: str, direction: str, score: float, bar_index: int
    ) -> Optional[SetupTransition]:
        if (
            tier in _DEVELOPING_TIERS
            and direction in ("LONG", "SHORT")
            and score >= SCORE_MIN_DEVELOP
        ):
            return self._enter_developing(direction, score, bar_index)
        return None

    def _developing(
        self, tier: str, direction: str, score: float, bar_index: int
    ) -> Optional[SetupTransition]:
        setup = self.active_setup
        assert setup is not None, "active_setup must exist in DEVELOPING"

        # Direction flip — reset soak. Drop to SCANNING, then attempt
        # re-entry under the new direction in the same bar (so the new
        # signal isn't lost).
        if direction in ("LONG", "SHORT") and direction != setup.direction:
            self._reset_to_scanning()
            return self._scanning(tier, direction, score, bar_index)

        # Score collapsed — soak invalidated
        if score < SCORE_SOAK_DROP:
            return self._to_scanning(trigger="SCORE_COLLAPSE", bar_index=bar_index)

        # Signal weakened to QUIET / NONE — do not increment soak, but don't
        # reset either (allow minor dropouts within an active soak).
        if tier not in _DEVELOPING_TIERS and tier != _TIER_A:
            return None

        # Aligned soak bar
        setup.soak_bars += 1

        # Tier-A crossing after full soak → TRIGGERED
        if (
            setup.soak_bars >= 10
            and tier == _TIER_A
            and score >= SCORE_MIN_TIER_A_CROSS
        ):
            return self._to_triggered(trigger="TIER_CROSS", bar_index=bar_index)

        return None

    def _triggered(self, bar_index: int) -> Optional[SetupTransition]:
        # One bar grace for entry confirmation, then → MANAGING.
        return self._to_managing(bar_index)

    def _managing(self, bar_index: int) -> Optional[SetupTransition]:
        assert self.active_setup is not None
        self.active_setup.bars_managing += 1

        # FAILSAFE ONLY — no normal auto-transition. Real close goes via
        # close_trade(). This branch is the wedge-prevention guardrail.
        if self.active_setup.bars_managing > self.managing_failsafe_bars:
            msg = (
                f"[setup_tracker:{self.timeframe}] FAILSAFE: setup "
                f"{self.active_setup.setup_id} held in MANAGING for "
                f"{self.active_setup.bars_managing} bars (> "
                f"{self.managing_failsafe_bars}) — forcing COOLDOWN"
            )
            log.warning(
                "setup_tracker.managing.failsafe",
                timeframe=self.timeframe,
                setup_id=self.active_setup.setup_id,
                bars_managing=self.active_setup.bars_managing,
                limit=self.managing_failsafe_bars,
            )
            _stdlog.warning(msg)
            return self._to_cooldown(trigger="FAILSAFE", bar_index=bar_index)

        return None

    def _cooldown(self, bar_index: int) -> Optional[SetupTransition]:
        self._cooldown_remaining -= 1
        if self._cooldown_remaining <= 0:
            return self._to_scanning(trigger="COOLDOWN_ELAPSED", bar_index=bar_index)
        return None

    # ----- transition helpers -----------------------------------------------

    def _new_setup_id(self) -> str:
        return f"{self.timeframe}-{uuid.uuid4().hex[:12]}"

    def _enter_developing(
        self, direction: str, score: float, bar_index: int
    ) -> SetupTransition:
        self.active_setup = ActiveSetup(
            setup_id=self._new_setup_id(),
            setup_type="SOAK",
            direction=direction,
            entry_score=score,
            soak_bars=1,
            started_at_bar=bar_index,
        )
        return self._emit_transition(
            from_state="SCANNING",
            to_state="DEVELOPING",
            trigger="ALIGNED_TIER_B_OR_C",
            bar_index=bar_index,
        )

    def _bypass_to_triggered(
        self, direction: str, score: float, bar_index: int
    ) -> SetupTransition:
        from_state = self.state
        self.active_setup = ActiveSetup(
            setup_id=self._new_setup_id(),
            setup_type="SLINGSHOT_BYPASS",
            direction=direction,
            entry_score=score,
            soak_bars=0,
            started_at_bar=bar_index,
        )
        self.state = "TRIGGERED"
        return self._emit_transition(
            from_state=from_state,
            to_state="TRIGGERED",
            trigger="SLINGSHOT_BYPASS",
            bar_index=bar_index,
        )

    def _to_triggered(self, trigger: str, bar_index: int) -> SetupTransition:
        self.state = "TRIGGERED"
        return self._emit_transition(
            from_state="DEVELOPING",
            to_state="TRIGGERED",
            trigger=trigger,
            bar_index=bar_index,
        )

    def _to_managing(self, bar_index: int) -> SetupTransition:
        self.state = "MANAGING"
        return self._emit_transition(
            from_state="TRIGGERED",
            to_state="MANAGING",
            trigger="ENTRY_CONFIRMED",
            bar_index=bar_index,
        )

    def _to_cooldown(self, trigger: str, bar_index: int) -> SetupTransition:
        from_state = self.state
        setup_id = self.active_setup.setup_id if self.active_setup else ""
        weight = self.current_weight()
        self.state = "COOLDOWN"
        self._cooldown_remaining = self.cooldown_bars
        # We keep active_setup reference out — the setup is closed.
        self.active_setup = None
        tr = SetupTransition(
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state="COOLDOWN",
            trigger=trigger,
            weight=weight,
            bar_index=bar_index,
        )
        log.info(
            "setup_tracker.transition",
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state="COOLDOWN",
            trigger=trigger,
        )
        return tr

    def _to_scanning(self, trigger: str, bar_index: int) -> SetupTransition:
        from_state = self.state
        setup_id = self.active_setup.setup_id if self.active_setup else ""
        weight = self.current_weight()
        self.state = "SCANNING"
        self.active_setup = None
        self._cooldown_remaining = 0
        tr = SetupTransition(
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state="SCANNING",
            trigger=trigger,
            weight=weight,
            bar_index=bar_index,
        )
        log.info(
            "setup_tracker.transition",
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state="SCANNING",
            trigger=trigger,
        )
        return tr

    def _reset_to_scanning(self) -> None:
        """Drop to SCANNING WITHOUT emitting a transition — used before an
        immediate re-entry attempt in the same bar (direction flip path)."""
        self.state = "SCANNING"
        self.active_setup = None
        self._cooldown_remaining = 0

    def _emit_transition(
        self,
        from_state: str,
        to_state: str,
        trigger: str,
        bar_index: int,
    ) -> SetupTransition:
        # advance state AFTER assembling payload so from_state is correct
        if to_state == "DEVELOPING":
            self.state = "DEVELOPING"
        # TRIGGERED / MANAGING state advances are set by their callers so
        # that current_weight() reports the correct value below.
        weight = self.current_weight()
        setup_id = self.active_setup.setup_id if self.active_setup else ""
        tr = SetupTransition(
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            weight=weight,
            bar_index=bar_index,
        )
        log.info(
            "setup_tracker.transition",
            timeframe=self.timeframe,
            setup_id=setup_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            weight=weight,
        )
        return tr
