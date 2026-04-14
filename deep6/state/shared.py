"""SharedState: single container object passed to all callbacks and coroutines.

No locks needed — single asyncio event loop thread owns all state.
All callback functions receive 'state' as their only context argument.
Assembled once in __main__.py via SharedState.build(config); never reconstructed
during a session.

Per ARCH-02: SharedState is the backbone connecting all Plan 01-03 components.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from deep6.config import Config
from deep6.state.dom import DOMState
from deep6.state.session import SessionContext
from deep6.state.connection import FreezeGuard, SessionManager
from deep6.state.persistence import SessionPersistence
from deep6.signals.atr import ATRTracker
from deep6.orderflow.vpin import VPINEngine
from deep6.orderflow.slingshot import SlingshotDetector, SlingshotResult
from deep6.orderflow.setup_tracker import SetupTracker, SetupTransition
from deep6.signals.flags import SignalFlags


@dataclass
class SharedState:
    """All shared state for DEEP6. Assembled once at startup.

    Attributes:
        config:        Immutable runtime configuration (Config dataclass).
        dom:           Pre-allocated Level 2 order book arrays (DOMState).
        session:       VWAP/CVD/IB session accumulators (SessionContext).
        freeze_guard:  FROZEN state guard for disconnect safety (FreezeGuard).
        persistence:   Async SQLite persistence for session state (SessionPersistence).
        bar_builders:  List of BarBuilder instances — populated by __main__.py.
                       [0] = 1-minute BarBuilder, [1] = 5-minute BarBuilder.
        atr_trackers:  Dict of ATRTracker keyed by bar label ("1m", "5m").
        _on_bar_close_fn: Optional override for the on_bar_close dispatch method.
                       None in Phase 1 (logs only). Signal engines attach in Phase 2+.

    Thread safety: all attributes are accessed from the single asyncio event loop.
    No locking required.
    """

    config: Config
    dom: DOMState = field(default_factory=DOMState)
    session: SessionContext = field(default_factory=SessionContext)
    freeze_guard: FreezeGuard = field(default_factory=FreezeGuard)
    persistence: SessionPersistence = field(default=None)  # type: ignore[assignment]

    # Bar builders (1m and 5m) — appended by __main__.py after BarBuilder creation
    # Kept as a list so tick_feed.py can iterate: for builder in state.bar_builders
    bar_builders: list = field(default_factory=list)

    # ATR trackers — one per timeframe label
    atr_trackers: dict = field(default_factory=lambda: {
        "1m": ATRTracker(period=20),
        "5m": ATRTracker(period=20),
    })

    # VPIN engine (phase 12-01) — 1m only. 5m deferred.
    # Fed inside on_bar_close BEFORE the scorer runs; modifier is read by
    # downstream scorer invocations as a final-stage multiplier on the fused
    # total_score.
    vpin: VPINEngine = field(default_factory=VPINEngine)

    # Slingshot detectors (phase 12-03, TRAP_SHOT @ bit 44) — independent
    # 1m and 5m instances. Each maintains its own delta_history; both reset
    # at the RTH session boundary via on_session_reset(). Last firing per
    # timeframe is exposed for phase 12-04 setup state machine consumption.
    slingshot_1m: SlingshotDetector = field(default_factory=SlingshotDetector)
    slingshot_5m: SlingshotDetector = field(default_factory=SlingshotDetector)
    last_slingshot_1m: SlingshotResult | None = field(default=None, repr=False)
    last_slingshot_5m: SlingshotResult | None = field(default=None, repr=False)

    # Rolling bar cache per timeframe (for slingshot multi-bar lookback).
    # Kept short (last 5) — slingshot needs up to 4 bars.
    _bar_cache_1m: list = field(default_factory=list, repr=False)
    _bar_cache_5m: list = field(default_factory=list, repr=False)

    # Optional GEX-distance provider (ticks) — set by __main__.py once the
    # GEX engine is wired. Signature: () -> float | None. None when GEX
    # context is unavailable, which degrades slingshot to no-bypass firing.
    gex_distance_provider: Callable | None = field(default=None, repr=False)

    # Phase 12-04: setup state machines — one per timeframe, independent.
    # Consume ScorerResult + SlingshotResult via feed_scorer_result() and
    # are the sole path by which setup transitions are emitted into the
    # EventStore (below). close_trade() routes by setup_id prefix.
    setup_tracker_1m: SetupTracker = field(
        default_factory=lambda: SetupTracker(timeframe="1m")
    )
    setup_tracker_5m: SetupTracker = field(
        default_factory=lambda: SetupTracker(timeframe="5m")
    )

    # Optional EventStore handle — when set (e.g. in the FastAPI lifespan),
    # setup transitions are persisted via record_setup_transition. None is
    # fine for tests and offline harnesses: transitions still fire through
    # the trackers, they just aren't written to disk.
    event_store: object | None = field(default=None, repr=False)

    # Optional on_bar_close override (set by signal pipeline in Phase 2+)
    _on_bar_close_fn: Callable | None = field(default=None, repr=False)

    async def on_bar_close(self, label: str, bar) -> None:
        """Dispatched by BarBuilder at each bar close.

        Phase 1: logs bar close diagnostics; does nothing else.
        Phase 2+: signal engines attach via __main__.py by setting _on_bar_close_fn.

        Args:
            label: Timeframe label — "1m" or "5m".
            bar:   Closed FootprintBar with finalized fields.
        """
        import structlog
        log = structlog.get_logger()
        log.debug(
            "bar.closed",
            label=label,
            timestamp=bar.timestamp,
            close=bar.close,
            bar_delta=bar.bar_delta,
            cvd=bar.cvd,
            poc=bar.poc_price,
            total_vol=bar.total_vol,
            bar_range=bar.bar_range,
        )
        # Phase 12-01: feed VPIN engine before any downstream scoring runs.
        # 1m only — 5m VPIN deferred (see 12-CONTEXT.md). No-op for malformed
        # / zero-volume bars (handled inside VPINEngine.update_from_bar).
        if label == "1m":
            try:
                self.vpin.update_from_bar(bar)
            except Exception:
                # VPIN must never break the bar-close path. Log and continue.
                log.exception("vpin.update_failed", label=label)

        # Phase 12-03: feed SlingshotDetector and run pattern detection.
        # Must never break the bar-close path — wrapped in try/except.
        try:
            self._run_slingshot(label, bar)
        except Exception:
            log.exception("slingshot.detect_failed", label=label)

        if self._on_bar_close_fn is not None:
            await self._on_bar_close_fn(label, bar)

    def _run_slingshot(self, label: str, bar) -> int:
        """Run SlingshotDetector for the given timeframe and return the flag bitmask.

        Appends bar_delta to the detector's history, maintains the rolling
        bar cache, runs detect(), stores last result, and returns
        int(SignalFlags.TRAP_SHOT) if fired (else 0).

        Return value is used by the signal bitmask assembly in phase 12-04
        and by integration tests.
        """
        if label == "1m":
            detector = self.slingshot_1m
            cache = self._bar_cache_1m
        elif label == "5m":
            detector = self.slingshot_5m
            cache = self._bar_cache_5m
        else:
            return 0

        detector.update_history(int(getattr(bar, "bar_delta", 0)))
        cache.append(bar)
        # Keep only the last 5 bars (slingshot needs at most 4).
        if len(cache) > 5:
            del cache[: len(cache) - 5]

        gex_distance = None
        if self.gex_distance_provider is not None:
            try:
                gex_distance = self.gex_distance_provider()
            except Exception:
                gex_distance = None

        result = detector.detect(cache, gex_distance)
        if label == "1m":
            self.last_slingshot_1m = result
        else:
            self.last_slingshot_5m = result

        return int(SignalFlags.TRAP_SHOT) if result.fired else 0

    async def feed_scorer_result(
        self,
        label: str,
        scorer_result,
        slingshot_result,
        current_bar_index: int,
    ) -> SetupTransition | None:
        """Drive the setup state machine for a given timeframe.

        Called by downstream scoring code after it has produced a ScorerResult
        and the bar-close path has populated ``last_slingshot_*``. If the
        tracker emits a transition, it is persisted to the EventStore when
        one is attached.

        Phase 12-04 wiring. Keeping this as its own entry point (rather than
        inlining into on_bar_close) preserves the ability to run the state
        machine from offline replay harnesses, backtests, and unit tests
        without needing the full bar-close dispatch.
        """
        tracker = self._tracker_for(label)
        if tracker is None:
            return None

        transition = tracker.update(
            scorer_result, slingshot_result, current_bar_index
        )
        if transition is not None and self.event_store is not None:
            await self._persist_transition(transition)
        return transition

    def close_trade(
        self, setup_id: str, outcome: str = "CLOSED"
    ) -> SetupTransition | None:
        """Route a close-trade event to the correct tracker by setup_id prefix.

        Called from the execution layer (PaperTrader / RithmicExecutor) on
        trade close. ``setup_id`` is guaranteed to be prefixed ``1m-`` or
        ``5m-`` because SetupTracker._new_setup_id builds it that way; any
        other prefix is a routing bug and returns None (defensive no-op).
        """
        if setup_id.startswith("1m-"):
            tracker = self.setup_tracker_1m
        elif setup_id.startswith("5m-"):
            tracker = self.setup_tracker_5m
        else:
            return None

        transition = tracker.close_trade(setup_id, outcome)
        if transition is not None and self.event_store is not None:
            # Schedule the persistence without awaiting — close_trade is a
            # synchronous call site (execution layer). If the caller has an
            # event loop running, the task completes opportunistically.
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._persist_transition(transition))
            except RuntimeError:
                # No running loop — callers outside an event loop can still
                # close trades; the transition just isn't persisted. This
                # matches behaviour in unit-test harnesses.
                pass
        return transition

    def _tracker_for(self, label: str) -> SetupTracker | None:
        if label == "1m":
            return self.setup_tracker_1m
        if label == "5m":
            return self.setup_tracker_5m
        return None

    async def _persist_transition(self, tr: SetupTransition) -> None:
        """Write a SetupTransition to the EventStore. Must never raise into
        the bar-close path — failures are logged and swallowed."""
        import structlog
        log = structlog.get_logger()
        try:
            await self.event_store.record_setup_transition(  # type: ignore[union-attr]
                timeframe=tr.timeframe,
                setup_id=tr.setup_id,
                from_state=tr.from_state,
                to_state=tr.to_state,
                trigger=tr.trigger,
                weight=tr.weight,
                bar_index=tr.bar_index,
                ts=tr.ts,
            )
        except Exception:
            log.exception(
                "setup_transition.persist_failed",
                timeframe=tr.timeframe,
                setup_id=tr.setup_id,
            )

    def on_session_reset(self) -> None:
        """Hook invoked at RTH session open (9:30 ET) by SessionManager.

        Per 12-CONTEXT.md FOOTGUN 2: both slingshot detectors must clear
        their delta_history at the session boundary to avoid threshold drift
        across the overnight gap. Bar caches are also cleared so pre-open
        bars (if any) cannot satisfy multi-bar patterns on the first fresh
        RTH bar.
        """
        self.slingshot_1m.reset_session()
        self.slingshot_5m.reset_session()
        self._bar_cache_1m.clear()
        self._bar_cache_5m.clear()
        self.last_slingshot_1m = None
        self.last_slingshot_5m = None

    @classmethod
    def build(cls, config: Config) -> "SharedState":
        """Factory: build SharedState with all sub-components wired up.

        This is the single entry point for constructing SharedState.
        Called once in __main__.py at startup.

        Sub-components initialised here:
          - SessionPersistence (backed by config.db_path — may be file or :memory:)
          - All other components use their field defaults (DOMState, SessionContext, etc.)

        Note: persistence.initialize() (creates the SQLite table) must be called
        separately in an async context before first use.
        """
        persistence = SessionPersistence(config.db_path)
        state = cls(config=config, persistence=persistence)
        return state

    def session_manager(self) -> SessionManager:
        """Return a SessionManager bound to this state.

        Convenience accessor for use in asyncio.gather():
            asyncio.gather(
                bar_builder_1m.run(),
                bar_builder_5m.run(),
                state.session_manager().run(),
            )
        """
        return SessionManager(self)
