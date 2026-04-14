"""LiveBridge — adapter from real engine output to WSManager broadcasts.

Connects real DEEP6 engine output (FootprintBar, ScorerResult, signal events,
trade prints) to WSManager.broadcast(), translating internal engine types into
wire-format Pydantic schemas.

Design goals:
  - TYPE-ROBUST: accepts real engine dataclass instances OR plain dicts — no
    hard import dependency on the engine at class definition time, so the API
    can import this module even when the full engine stack is not installed.
  - GRACEFUL FALLBACK: missing fields fall back to safe defaults (0, "", etc.)
  - SERIALIZATION SAFE: NaN and Infinity floats become 0.0; None becomes "".

Usage (real engine):
    bridge = LiveBridge(ws_manager)
    bridge.on_bar_close(footprint_bar)        # → LiveBarMessage broadcast
    bridge.on_signal_fired(signal_event)      # → LiveSignalMessage broadcast
    bridge.on_score_update(scorer_result)     # → LiveScoreMessage broadcast
    bridge.on_tape_print(trade_event)         # → LiveTapeMessage broadcast
    bridge.on_status_update(status_dict)      # → LiveStatusMessage broadcast
    await bridge.periodic_status()            # call every ~10s for keepalive

Usage (test / demo):
    bridge = LiveBridge(ws_manager)
    # Pass a plain dict — bridge handles both shapes transparently.
    await bridge.on_bar_close({"session_id": "demo", "bar_index": 0, ...})

"Going live" checklist — hook the bridge into the engine:
    1. bar close:   call ``await bridge.on_bar_close(bar)`` inside the bar-close
                    callback of your FootprintBuilder.
    2. signal fire: call ``await bridge.on_signal_fired(scorer_result)`` whenever
                    score_bar() returns tier >= TYPE_C.
    3. score update: call ``await bridge.on_score_update(scorer_result)`` on every
                    bar to keep the dashboard score card current.
    4. tape prints: call ``await bridge.on_tape_print(trade_event)`` in the
                    on_trade() callback of the Rithmic feed.
    5. status:      schedule ``asyncio.create_task(bridge.periodic_status())``
                    inside the engine startup coroutine, or call every 10s.

Fallback to demo:
    Pass ``--source=demo`` to ``scripts/run_live.py`` — the bridge is not
    invoked; demo_broadcast.py posts directly to /api/live/test-broadcast.

Mixed mode (tomorrow if engine is not ready):
    Use demo_broadcast.py for market data (bars + tape) and call
    ``bridge.on_score_update`` / ``bridge.on_signal_fired`` from the partial
    engine. The dashboard cannot tell the difference.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any

from deep6.api.ws_manager import WSManager
from deep6.api.schemas import (
    BarEventIn,
    BarLevelOut,
    LiveBarMessage,
    LiveScoreMessage,
    LiveSignalMessage,
    LiveStatusMessage,
    LiveTapeMessage,
    SignalEventIn,
    TapeEventIn,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v: Any, default: float = 0.0) -> float:
    """Return v coerced to float, replacing NaN/Infinity/None with default."""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    """Return v coerced to int, returning default on failure."""
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _safe_str(v: Any, default: str = "") -> str:
    """Return v as str, returning default for None."""
    if v is None:
        return default
    return str(v)


def _getattr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    """Duck-type accessor: try attribute first, then dict key, then default."""
    val = getattr(obj, key, _SENTINEL)
    if val is not _SENTINEL:
        return val
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


_SENTINEL = object()

# Default session ID when the engine does not provide one (startup / test).
_DEFAULT_SESSION_ID = "live"


# ---------------------------------------------------------------------------
# LiveBridge
# ---------------------------------------------------------------------------

class LiveBridge:
    """Adapter: real engine output → WSManager broadcasts.

    All public ``on_*`` methods are coroutines. Call them from the asyncio
    event loop that runs the engine (same loop as the FastAPI app).

    Parameters
    ----------
    ws_manager:
        The WSManager singleton stored at ``app.state.ws_manager``.
    session_id:
        Trading session identifier included in bar messages.  Defaults to
        "live"; callers should pass the current session ID if available.
    """

    def __init__(
        self,
        ws_manager: WSManager,
        session_id: str = _DEFAULT_SESSION_ID,
    ) -> None:
        self.ws_manager = ws_manager
        self.session_id = session_id
        self._session_start_ts: float = time.time()
        self._bars_received: int = 0
        self._signals_fired: int = 0
        self._last_signal_tier: str = ""
        # P&L and circuit-breaker state are injected externally via on_status_update
        self._pnl: float = 0.0
        self._circuit_breaker_active: bool = False
        self._feed_stale: bool = False

    # ------------------------------------------------------------------
    # Public event handlers
    # ------------------------------------------------------------------

    async def on_bar_close(self, bar: Any) -> None:
        """Convert engine FootprintBar (or dict) → LiveBarMessage and broadcast.

        Increments the internal bar counter and syncs the WSManager counter so
        keepalive status messages reflect accurate bar counts.
        """
        try:
            msg = self._bar_to_message(bar)
            await self.ws_manager.broadcast(msg.model_dump())
            self._bars_received += 1
            self.ws_manager.bars_received = self._bars_received
            log.debug("live_bridge.bar_close bar_index=%d", msg.bar_index)
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.on_bar_close failed")

    async def on_signal_fired(self, sig: Any) -> None:
        """Convert engine ScorerResult (or dict) → LiveSignalMessage and broadcast.

        Increments the signal counter and captures the tier for keepalive status.
        Only broadcasts when tier is TYPE_C or better (score >= threshold).
        """
        try:
            msg = self._signal_to_message(sig)
            # Resolve tier from raw object BEFORE calling _safe_str so enum
            # .name is read while the object still has that attribute.
            tier_raw = _getattr_or_key(sig, "tier", "")
            if hasattr(tier_raw, "name"):
                tier_str = str(tier_raw.name)
            elif hasattr(tier_raw, "value"):
                tier_str = str(tier_raw.value)
            else:
                tier_str = _safe_str(tier_raw, "")
            await self.ws_manager.broadcast(msg.model_dump())
            self._signals_fired += 1
            self._last_signal_tier = str(tier_str)
            self.ws_manager.signals_fired = self._signals_fired
            self.ws_manager.last_signal_tier = self._last_signal_tier
            log.debug("live_bridge.signal_fired tier=%s", tier_str)
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.on_signal_fired failed")

    async def on_score_update(self, score: Any) -> None:
        """Convert engine ScorerResult (or dict) → LiveScoreMessage and broadcast.

        Called on every bar close to keep the dashboard score card current,
        regardless of tier.
        """
        try:
            msg = self._score_to_message(score)
            await self.ws_manager.broadcast(msg.model_dump())
            log.debug("live_bridge.score_update score=%.1f", msg.total_score)
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.on_score_update failed")

    async def on_tape_print(self, trade: Any) -> None:
        """Convert a trade event (or dict) → LiveTapeMessage and broadcast."""
        try:
            msg = self._tape_to_message(trade)
            await self.ws_manager.broadcast(msg.model_dump())
            log.debug("live_bridge.tape_print price=%.2f", msg.event.price)
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.on_tape_print failed")

    async def on_status_update(self, status: dict[str, Any]) -> None:
        """Accept external P&L / circuit-breaker state and broadcast LiveStatusMessage.

        Callers (e.g. PositionManager) pass a plain dict with optional keys:
          - pnl (float)
          - circuit_breaker_active (bool)
          - feed_stale (bool)
        """
        try:
            self._pnl = _safe_float(status.get("pnl"), self._pnl)
            self._circuit_breaker_active = bool(status.get("circuit_breaker_active", self._circuit_breaker_active))
            self._feed_stale = bool(status.get("feed_stale", self._feed_stale))
            await self.periodic_status()
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.on_status_update failed")

    async def periodic_status(self) -> None:
        """Broadcast a status snapshot — call every ~10s from the engine loop.

        Reads internal counters and syncs them to WSManager before building
        the LiveStatusMessage so the keepalive loop and this path agree.
        """
        try:
            self.ws_manager.bars_received = self._bars_received
            self.ws_manager.signals_fired = self._signals_fired
            self.ws_manager.last_signal_tier = self._last_signal_tier
            self.ws_manager.session_start_ts = self._session_start_ts
            await self.ws_manager.broadcast_status(
                connected=True,
                pnl=self._pnl,
                circuit_breaker_active=self._circuit_breaker_active,
                feed_stale=self._feed_stale,
            )
        except Exception:  # noqa: BLE001
            log.exception("live_bridge.periodic_status failed")

    # ------------------------------------------------------------------
    # Private converters
    # ------------------------------------------------------------------

    def _bar_to_message(self, bar: Any) -> LiveBarMessage:
        """Convert FootprintBar (dataclass or dict) → LiveBarMessage.

        Field mapping (engine → wire):
            FootprintBar.timestamp       → BarEventIn.ts
            FootprintBar.open/high/...   → BarEventIn.open/high/...
            FootprintBar.levels          → BarEventIn.levels (dict[str, BarLevelOut])
            FootprintBar.bar_delta       → BarEventIn.bar_delta
            FootprintBar.cvd             → BarEventIn.cvd
            FootprintBar.poc_price       → BarEventIn.poc_price
            FootprintBar.bar_range       → BarEventIn.bar_range
            FootprintBar.running_delta   → BarEventIn.running_delta
            FootprintBar.max_delta       → BarEventIn.max_delta
            FootprintBar.min_delta       → BarEventIn.min_delta

        For dict input (e.g. from demo or test), all keys are accessed via
        _getattr_or_key so both shapes work.
        """
        # Session / index — may be on the bar or need a default
        session_id = _safe_str(
            _getattr_or_key(bar, "session_id", self.session_id), self.session_id
        )
        bar_index = _safe_int(_getattr_or_key(bar, "bar_index", self._bars_received))

        # Timestamps — FootprintBar uses .timestamp; wire shape uses .ts
        ts_raw = _getattr_or_key(bar, "ts", None)
        if ts_raw is None:
            ts_raw = _getattr_or_key(bar, "timestamp", time.time())
        ts = _safe_float(ts_raw, time.time())

        # OHLCV
        open_  = _safe_float(_getattr_or_key(bar, "open", 0.0))
        high   = _safe_float(_getattr_or_key(bar, "high", 0.0))
        low    = _safe_float(_getattr_or_key(bar, "low", 0.0))
        close  = _safe_float(_getattr_or_key(bar, "close", 0.0))
        total_vol = _safe_int(_getattr_or_key(bar, "total_vol", 0))

        # Delta fields
        bar_delta     = _safe_int(_getattr_or_key(bar, "bar_delta", 0))
        cvd           = _safe_int(_getattr_or_key(bar, "cvd", 0))
        running_delta = _safe_int(_getattr_or_key(bar, "running_delta", 0))
        max_delta     = _safe_int(_getattr_or_key(bar, "max_delta", 0))
        min_delta     = _safe_int(_getattr_or_key(bar, "min_delta", 0))

        # POC / range
        poc_price = _safe_float(_getattr_or_key(bar, "poc_price", 0.0))
        bar_range = _safe_float(_getattr_or_key(bar, "bar_range", 0.0))

        # Levels — handle both engine (defaultdict[int, FootprintLevel]) and
        # wire (dict[str, {"bid_vol": int, "ask_vol": int}]) shapes.
        levels_raw = _getattr_or_key(bar, "levels", {})
        levels: dict[str, BarLevelOut] = {}
        if isinstance(levels_raw, dict):
            for k, v in levels_raw.items():
                try:
                    bid_vol = _safe_int(_getattr_or_key(v, "bid_vol", 0))
                    ask_vol = _safe_int(_getattr_or_key(v, "ask_vol", 0))
                    levels[str(k)] = BarLevelOut(bid_vol=bid_vol, ask_vol=ask_vol)
                except Exception:  # noqa: BLE001
                    pass  # skip malformed level rows

        bar_event = BarEventIn(
            session_id=session_id,
            bar_index=bar_index,
            ts=ts,
            open=open_,
            high=high,
            low=low,
            close=close,
            total_vol=total_vol,
            bar_delta=bar_delta,
            cvd=cvd,
            poc_price=poc_price,
            bar_range=bar_range,
            running_delta=running_delta,
            max_delta=max_delta,
            min_delta=min_delta,
            levels=levels,
        )

        return LiveBarMessage(
            session_id=session_id,
            bar_index=bar_index,
            bar=bar_event,
        )

    def _signal_to_message(self, sig: Any) -> LiveSignalMessage:
        """Convert ScorerResult (dataclass or dict) → LiveSignalMessage.

        Field mapping (engine → wire):
            ScorerResult.total_score         → SignalEventIn.total_score
            ScorerResult.tier (SignalTier)   → SignalEventIn.tier (str)
            ScorerResult.direction           → SignalEventIn.direction
            ScorerResult.engine_agreement    → SignalEventIn.engine_agreement
            ScorerResult.category_count      → SignalEventIn.category_count
            ScorerResult.categories_firing   → SignalEventIn.categories_firing
            ScorerResult.label               → LiveSignalMessage.narrative

        Engine also provides gex_regime via GexSignal — passed separately when
        available; defaults to "NEUTRAL" otherwise.
        """
        ts          = _safe_float(_getattr_or_key(sig, "ts", time.time()), time.time())
        bar_index   = _safe_int(_getattr_or_key(sig, "bar_index_in_session", self._bars_received))
        total_score = _safe_float(_getattr_or_key(sig, "total_score", 0.0))
        direction   = _safe_int(_getattr_or_key(sig, "direction", 0))
        engine_agr  = _safe_float(_getattr_or_key(sig, "engine_agreement", 0.0))
        cat_count   = _safe_int(_getattr_or_key(sig, "category_count", 0))
        kronos_bias = _safe_float(_getattr_or_key(sig, "kronos_bias", 0.0))

        # tier — may be SignalTier IntEnum, its .name, or a plain string
        tier_raw = _getattr_or_key(sig, "tier", "QUIET")
        if hasattr(tier_raw, "name"):
            tier_str = tier_raw.name
        else:
            tier_str = _safe_str(tier_raw, "QUIET")

        # categories_firing — list or set; convert to sorted list
        cats_raw = _getattr_or_key(sig, "categories_firing", [])
        if cats_raw is None:
            cats_raw = []
        categories_firing = sorted([_safe_str(c) for c in cats_raw])

        # gex_regime — may come as GexRegime enum or string
        gex_raw = _getattr_or_key(sig, "gex_regime", "NEUTRAL")
        if hasattr(gex_raw, "value"):
            gex_regime = _safe_str(gex_raw.value, "NEUTRAL")
        else:
            gex_regime = _safe_str(gex_raw, "NEUTRAL")

        # narrative / label
        narrative = _safe_str(_getattr_or_key(sig, "label", ""), "")
        if not narrative:
            narrative = _safe_str(_getattr_or_key(sig, "narrative", ""), "")

        event = SignalEventIn(
            ts=ts,
            bar_index_in_session=bar_index,
            total_score=total_score,
            tier=tier_str,
            direction=direction,
            engine_agreement=engine_agr,
            category_count=cat_count,
            categories_firing=categories_firing,
            gex_regime=gex_regime,
            kronos_bias=kronos_bias,
        )
        return LiveSignalMessage(event=event, narrative=narrative)

    def _score_to_message(self, score: Any) -> LiveScoreMessage:
        """Convert ScorerResult (dataclass or dict) → LiveScoreMessage.

        LiveScoreMessage is the lightweight per-bar score card update.
        Unlike LiveSignalMessage it fires on every bar, not just signal tiers.
        """
        total_score = _safe_float(_getattr_or_key(score, "total_score", 0.0))
        direction   = _safe_int(_getattr_or_key(score, "direction", 0))
        kronos_bias = _safe_float(_getattr_or_key(score, "kronos_bias", 0.0))

        tier_raw = _getattr_or_key(score, "tier", "QUIET")
        if hasattr(tier_raw, "name"):
            tier_str = tier_raw.name
        else:
            tier_str = _safe_str(tier_raw, "QUIET")

        cats_raw = _getattr_or_key(score, "categories_firing", [])
        if cats_raw is None:
            cats_raw = []
        categories_firing = sorted([_safe_str(c) for c in cats_raw])

        # category_scores — dict[str, float]; may not exist on ScorerResult
        cat_scores_raw = _getattr_or_key(score, "category_scores", {})
        if cat_scores_raw is None:
            cat_scores_raw = {}
        category_scores = {
            _safe_str(k): _safe_float(v)
            for k, v in (cat_scores_raw.items() if isinstance(cat_scores_raw, dict) else {}.items())
        }

        gex_raw = _getattr_or_key(score, "gex_regime", "NEUTRAL")
        if hasattr(gex_raw, "value"):
            gex_regime = _safe_str(gex_raw.value, "NEUTRAL")
        else:
            gex_regime = _safe_str(gex_raw, "NEUTRAL")

        # kronos_direction — may come from separate KronosResult or be embedded
        kd_raw = _getattr_or_key(score, "kronos_direction", "NEUTRAL")
        kronos_direction = _safe_str(kd_raw, "NEUTRAL")

        return LiveScoreMessage(
            total_score=total_score,
            tier=tier_str,
            direction=direction,
            categories_firing=categories_firing,
            category_scores=category_scores,
            kronos_bias=kronos_bias,
            kronos_direction=kronos_direction,
            gex_regime=gex_regime,
        )

    def _tape_to_message(self, trade: Any) -> LiveTapeMessage:
        """Convert a trade event (dataclass, Rithmic trade callback, or dict) → LiveTapeMessage.

        Expected fields (any missing → safe default):
          ts     — epoch float
          price  — float
          size   — int
          side   — "BID" or "ASK"   (aggressor=2→BID, aggressor=1→ASK in Rithmic)
          marker — "" | "SWEEP" | "ICEBERG" | "KRONOS"

        Rithmic async-rithmic trade callbacks use ``aggressor`` (int) rather
        than ``side`` (str). This converter handles both:
          aggressor=1 (trade hit ask, buyer initiated) → "ASK"
          aggressor=2 (trade hit bid, seller initiated) → "BID"
        """
        ts    = _safe_float(_getattr_or_key(trade, "ts", time.time()), time.time())
        price = _safe_float(_getattr_or_key(trade, "price", 0.0))
        size  = _safe_int(_getattr_or_key(trade, "size", 0))
        marker = _safe_str(_getattr_or_key(trade, "marker", ""), "")

        # Side — normalise aggressor int → BID/ASK string
        side_raw = _getattr_or_key(trade, "side", None)
        if side_raw is None:
            aggressor = _safe_int(_getattr_or_key(trade, "aggressor", 0))
            if aggressor == 1:
                side = "ASK"
            elif aggressor == 2:
                side = "BID"
            else:
                side = "ASK"  # safe default
        else:
            side_str = _safe_str(side_raw, "ASK").upper()
            side = "ASK" if side_str not in ("BID", "ASK") else side_str

        event = TapeEventIn(
            ts=ts,
            price=price,
            size=size,
            side=side,  # type: ignore[arg-type]  # Literal enforced at validation
            marker=marker,  # type: ignore[arg-type]
        )
        return LiveTapeMessage(event=event)

    # ------------------------------------------------------------------
    # Accessors (for tests / introspection)
    # ------------------------------------------------------------------

    @property
    def bars_received(self) -> int:
        return self._bars_received

    @property
    def signals_fired(self) -> int:
        return self._signals_fired

    @property
    def last_signal_tier(self) -> str:
        return self._last_signal_tier

    @property
    def session_start_ts(self) -> float:
        return self._session_start_ts
