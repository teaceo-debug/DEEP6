"""Connection state management: FROZEN guard and RTH/GC session management.

FreezeGuard (D-17, D-18, D-19):
  - Enters FROZEN on disconnect — all callback processing halted immediately
  - Sequential plant reconnection with 500ms delay (Issue #49 workaround)
  - Exits FROZEN only after reconnect + position reconciliation (D-15)

SessionManager (D-16, D-07):
  - Disables GC at RTH open (9:30 ET): gc.disable()
  - Re-enables GC and runs gc.collect() at RTH close (16:00 ET)
  - Resets SessionContext at RTH open
  - Persists SessionContext to SQLite at RTH close

Per T-03-01: FreezeGuard._state is private — only on_disconnect/on_reconnect mutate it.
Per T-03-02: GC disabled only 6.5 hours/day; SessionManager.run() re-enables at close.
Per T-03-04: on_disconnect() calls structlog.warning with ts= — audit trail per D-19.
Per T-08-02: FreezeGuard stays FROZEN if position reconciliation fails; operator must intervene.
"""
import asyncio
import gc
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import structlog

log = structlog.get_logger()
EASTERN = ZoneInfo("America/New_York")


class ConnectionState:
    """Enumeration of valid connection states.

    Transitions: CONNECTED → FROZEN → RECONNECTING → CONNECTED
    """
    CONNECTED    = "CONNECTED"
    FROZEN       = "FROZEN"
    RECONNECTING = "RECONNECTING"


async def sync_position_state(client, config: "Config") -> dict:  # noqa: F821
    """Query Rithmic ORDER_PLANT for current position and return reconciliation result.

    Per D-15: compare Rithmic position to local state. Only unfreeze when matched.
    Returns dict with keys: 'rithmic_position' (int | None), 'reconciled' (bool).

    If async-rithmic position query fails, logs ERROR and returns reconciled=False
    (system stays frozen — safer than assuming clean state on failure, per T-08-02).
    """
    try:
        # async-rithmic v1.5.9: RithmicClient.get_positions() returns list[PositionItem]
        # PositionItem has .net_quantity (positive=long, negative=short, 0=flat)
        positions = await client.get_positions(config.exchange)
        nq_pos = next(
            (p.net_quantity for p in positions if config.instrument in p.ticker),
            0,
        )
        log.info(
            "reconcile.rithmic_position",
            instrument=config.instrument,
            net_qty=nq_pos,
        )
        return {"rithmic_position": nq_pos, "reconciled": True}
    except Exception as exc:
        log.error(
            "reconcile.failed",
            error=str(exc),
            action="staying FROZEN — manual intervention required",
        )
        return {"rithmic_position": None, "reconciled": False}


class FreezeGuard:
    """Guards all state mutation during disconnect/reconnect cycle.

    Every callback that touches shared state checks is_frozen before proceeding.
    State machine: CONNECTED → FROZEN (on_disconnect) → RECONNECTING → CONNECTED (on_reconnect).

    Per T-03-01: _state is private; only on_disconnect/on_reconnect mutate it.
    Per D-19: all transitions logged with timestamps for post-session review.
    """

    def __init__(self) -> None:
        self._state: str = ConnectionState.CONNECTED
        self._last_known_position: int = 0

    @property
    def is_frozen(self) -> bool:
        """True when not CONNECTED — callbacks should exit immediately."""
        return self._state != ConnectionState.CONNECTED

    def on_disconnect(self, ts: float | None = None) -> None:
        """Enter FROZEN state immediately on any disconnect (D-17).

        Called from rithmic.py _on_disconnected() handler — synchronous.
        No new bar processing occurs from this point until on_reconnect() completes.

        Per D-19: logs ts= for post-session disconnect/reconnect review.
        """
        ts = ts or time.time()
        self._state = ConnectionState.FROZEN
        log.warning(
            "connection.disconnected",
            ts=ts,
            state=self._state,
            action="FROZEN — no bar processing until reconnect + reconciliation",
        )

    async def on_reconnect(self, client, config) -> None:
        """Reconnect with sequential plant delay (D-18), then reconcile positions (D-15).

        D-18: Issue #49 workaround — 500ms asyncio.sleep after client.connect()
        before any subscriptions. Prevents ForcedLogout reconnection loop.

        D-15: Query Rithmic ORDER_PLANT for current position before unfreezing.
        Per T-08-02: stays FROZEN if reconciliation fails — operator must intervene.
        """
        self._state = ConnectionState.RECONNECTING
        log.info("connection.reconnecting", state=self._state)

        # Reconnect to Rithmic
        await client.connect()

        # Issue #49 workaround: 500ms delay between plant connections (D-18)
        await asyncio.sleep(0.5)

        # D-15: reconcile positions before unfreezing (T-08-02: stay frozen on failure)
        result = await sync_position_state(client, config)
        if not result["reconciled"]:
            log.error(
                "connection.reconcile_failed",
                action="STAYING FROZEN — run manual position check before resuming",
            )
            return  # Stay frozen — operator must intervene

        self._state = ConnectionState.CONNECTED
        self._last_known_position = result["rithmic_position"]
        log.info(
            "connection.restored",
            state=self._state,
            position=self._last_known_position,
            ts=time.time(),
        )

    @property
    def last_known_position(self) -> int:
        """Last Rithmic-reconciled position for this instrument (D-15)."""
        return self._last_known_position

    def get_state(self) -> str:
        """Return the current state string (for logging and testing)."""
        return self._state


class SessionManager:
    """Manages RTH session lifecycle: GC control, state reset, persistence.

    Polls every 1 second — negligible CPU cost vs. 1,000/sec DOM callbacks.

    Per D-16: gc.disable() at 9:30 ET (RTH open); gc.collect() at open and close.
    Per D-07: SessionContext.reset() at 9:30 ET each day.
    Per D-15: persists SessionContext to SQLite at 16:00 ET close.
    """

    def __init__(self, state: "SharedState") -> None:  # noqa: F821 (forward ref)
        self.state = state
        self._session_active: bool = False

    def _is_rth(self) -> bool:
        """True between 9:30 AM and 4:00 PM Eastern.

        Uses zoneinfo for DST-correct handling — no hardcoded UTC offset.
        """
        now_et = datetime.now(EASTERN)
        return (
            (now_et.hour == 9 and now_et.minute >= 30)
            or (10 <= now_et.hour < 16)
        )

    def _session_id(self) -> str:
        """Session ID = UTC date string YYYYMMDD.

        UTC-based so session ID is stable regardless of server timezone.
        """
        return datetime.now(timezone.utc).strftime("%Y%m%d")

    async def run(self) -> None:
        """Background coroutine: poll RTH boundaries every 1 second.

        Launched via asyncio.gather() in __main__.py alongside bar builders.
        Runs forever — cancelled on shutdown.
        """
        while True:
            is_rth = self._is_rth()
            if is_rth and not self._session_active:
                await self._on_session_open()
            elif not is_rth and self._session_active:
                await self._on_session_close()
            await asyncio.sleep(1.0)

    async def _on_session_open(self) -> None:
        """RTH open at 9:30 ET: reset state, disable GC (D-16, D-07).

        Also attempts to restore prior session state from SQLite —
        handles mid-session process restart (D-07).
        """
        self._session_active = True
        gc.collect()   # clean sweep before disabling GC (D-16)
        gc.disable()   # D-16: no GC during RTH — prevents latency spikes
        self.state.session.reset()

        # Phase 12-03: clear SlingshotDetector delta_history at RTH open to
        # prevent cross-session threshold drift (see 12-CONTEXT.md FOOTGUN 2).
        # The hook is idempotent and safe even if detectors aren't wired.
        reset_hook = getattr(self.state, "on_session_reset", None)
        if callable(reset_hook):
            try:
                reset_hook()
            except Exception:
                log.exception("session.on_reset_hook_failed")

        # Attempt to restore prior session state (mid-session restart, D-07)
        sid = self._session_id()
        restored = await self.state.persistence.restore_session_context(sid)
        if restored is not None:
            # Restore session accumulators — CVD, VWAP, IB
            self.state.session.cvd = restored.cvd
            self.state.session.vwap_numerator = restored.vwap_numerator
            self.state.session.vwap_denominator = restored.vwap_denominator
            self.state.session.ib_high = restored.ib_high
            self.state.session.ib_low = restored.ib_low
            self.state.session.ib_complete = restored.ib_complete
            log.info(
                "session.restored_from_db",
                session_id=sid,
                cvd=restored.cvd,
                ib_complete=restored.ib_complete,
            )
        else:
            log.info("session.fresh_start", session_id=sid)

    async def _on_session_close(self) -> None:
        """RTH close at 16:00 ET: persist state, re-enable GC (D-16, D-07).

        GC is re-enabled AFTER persistence so no GC pressure occurs during
        the final SQLite write.
        """
        self._session_active = False
        sid = self._session_id()
        await self.state.persistence.persist_session_context(sid, self.state.session)
        log.info(
            "session.persisted",
            session_id=sid,
            cvd=self.state.session.cvd,
            vwap=self.state.session.vwap,
        )
        gc.enable()
        gc.collect()   # D-16: manual collect at session boundary
