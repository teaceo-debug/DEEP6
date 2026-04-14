"""Clock abstraction — pluggable time source for live vs. replay.

Phase 13-01 rationale:
    DEEP6 has ~12 hot-path sites that consult the wall clock (session
    boundaries, persistence timestamps, reconnect backoff, GEX staleness,
    etc.). In live operation these must read true wall-clock time. In
    backtest replay they must advance in lockstep with historical event
    timestamps, not real time — otherwise "reconnect in 5s" would literally
    stall the replay for 5 seconds and session boundaries would never fire.

Design:
    - `Clock` is a `typing.runtime_checkable` Protocol exposing `now()` and
      `monotonic()`. Any object with those two methods satisfies it.
    - `WallClock` is the default. `SharedState.clock: Clock = WallClock()`
      preserves live behavior byte-for-byte.
    - `EventClock` is instantiated by `ReplaySession` and ticked forward by
      `MBOAdapter.advance(event.ts_event / 1e9)` before each dispatch.

Safety:
    - `EventClock.advance()` clamps backward timestamps to the last-seen
      value (Databento MBO can emit non-monotonic events across contract
      roll; see 13-01 FOOTGUN 3 in plan). A structlog warning is emitted
      the first time a backward event arrives.
    - `EventClock.monotonic()` is a separate counter — it increments by a
      fixed `_mono_step` on each `advance()` call regardless of wall ts,
      so latency instrumentation in replay produces sensible deltas.
"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import structlog

log = structlog.get_logger(__name__)


@runtime_checkable
class Clock(Protocol):
    """Protocol for pluggable time sources.

    Two methods because DEEP6 code mixes wall-clock (session boundaries,
    persistence) and monotonic (latency instrumentation) reads. Both must
    be swappable together.
    """

    def now(self) -> float: ...

    def monotonic(self) -> float: ...


class WallClock:
    """Live-mode clock — thin shim over ``time.time()`` / ``time.monotonic()``.

    Zero-allocation, zero-overhead: calls resolve to the stdlib C functions
    directly. This is the default value of ``SharedState.clock``.
    """

    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


class EventClock:
    """Replay-mode clock — driven by MBO event timestamps.

    ``now()`` returns the most recent timestamp passed to ``advance()``.
    ``monotonic()`` returns a separate, always-increasing counter seeded
    at 0.0 and bumped by ``_mono_step`` each advance — decouples latency
    instrumentation from the event-time axis.

    Non-monotonic events are clamped: if a backward timestamp arrives
    (e.g. across a Databento contract roll) ``now()`` stays at the prior
    max and a warning is logged. This is Footgun 3 mitigation from the
    plan and threat model T-13-01-03.
    """

    def __init__(self, mono_step: float = 1e-6) -> None:
        self._now: float = 0.0
        self._mono: float = 0.0
        self._mono_step: float = mono_step
        self._backward_warned: bool = False

    def advance(self, ts: float) -> None:
        """Advance the clock to ``ts`` (seconds since epoch).

        Clamps to ``max(_now, ts)`` — backward timestamps are dropped with
        a one-shot structlog warning. ``_mono`` always increments by
        ``_mono_step`` regardless of whether ``_now`` moved.
        """
        if ts < self._now:
            if not self._backward_warned:
                log.warning(
                    "eventclock.backward_ts",
                    incoming=ts,
                    current=self._now,
                    delta=self._now - ts,
                    action="clamping; subsequent backward events suppressed",
                )
                self._backward_warned = True
        else:
            self._now = ts
        self._mono += self._mono_step

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._mono
