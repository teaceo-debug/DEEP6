"""Stateful MBO wall engine shared by offline and live DepthRadar flows."""
from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import time
from typing import Any

import pandas as pd

from deep6.data.databento_live import (
    _ACTION_ADD,
    _ACTION_CANCEL,
    _ACTION_CLEAR,
    _ACTION_FILL,
    _ACTION_MODIFY,
    _ACTION_TRADE,
    _OrderBookState,
    _SIDE_ASK,
    _SIDE_BID,
)
from deep6.ml.depth_radar.causal_features import CAUSAL_FEATURE_NAMES, CausalFeatureExtractor
from deep6.ml.depth_radar.episode import InteractionOutcome, WallEpisode, WallIntent, WallState
from deep6.state.dom import DOMState


RTH_START = time(13, 30)
RTH_END = time(20, 0)
_EPISODE_UUID_NAMESPACE = uuid.UUID("3b0fe316-a647-48e1-8d53-e22fa5357d11")


def _is_rth(ts: pd.Timestamp) -> bool:
    current = ts.tz_convert("UTC").time()
    return RTH_START <= current < RTH_END


@dataclass(slots=True)
class _PendingTouch:
    episode_id: str
    touch_index: int
    wall_price: float
    wall_side: str
    deadline: pd.Timestamp
    bounce_level: float
    break_level: float
    first_bounce_time: pd.Timestamp | None = None
    first_break_time: pd.Timestamp | None = None


@dataclass(slots=True)
class _WallRuntime:
    episode: WallEpisode
    current_price: float
    current_size: int
    original_size: int
    max_size_so_far: int
    first_seen: pd.Timestamp
    last_update: pd.Timestamp
    last_size_change: pd.Timestamp
    modification_times: deque[pd.Timestamp] = field(default_factory=deque)
    size_history: deque[tuple[pd.Timestamp, int]] = field(default_factory=deque)
    refill_ratios: deque[float] = field(default_factory=deque)
    current_size_since: pd.Timestamp | None = None
    previous_size: int = 0
    modifications_so_far: int = 0
    refills_so_far: int = 0
    cancel_reappear_count: int = 0
    repricing_count: int = 0
    tests_count: int = 0
    absorbed_volume: int = 0
    filled_volume: int = 0
    depletion_events: int = 0
    bbo_track_count: int = 0
    approach_near_time: pd.Timestamp | None = None
    first_test_time: pd.Timestamp | None = None
    last_test_time: pd.Timestamp | None = None
    last_attack_volume_time: pd.Timestamp | None = None
    recovery_after_test: bool = False
    pull_approach_flag: bool = False
    stale_since: pd.Timestamp | None = None
    zero_since: pd.Timestamp | None = None
    in_touch_band: bool = False

    def age_seconds(self, now: pd.Timestamp) -> float:
        return max((now - self.first_seen).total_seconds(), 0.0)


class MBOWallEngine:
    """Stateful MBO event processor that maintains wall episodes with 44 causal features.

    Shared core between offline EpisodeLabeler and live MBORadar. Processes one
    MBO event at a time. Does NOT read files or write output — callers do that.
    """

    def __init__(
        self,
        min_wall_size: int = 50,
        tick_size: float = 0.25,
        snapshot_interval_sec: int = 2,
        touch_distance_ticks: int = 4,
        bounce_ticks: int = 8,
        break_ticks: int = 4,
        lookforward_sec: int = 30,
        stale_distance_ticks: int = 10,
        stale_timeout_sec: int = 15,
        reappear_timeout_sec: int = 2,
        rth_only: bool = True,
    ) -> None:
        self.rth_only = bool(rth_only)
        self.min_wall_size = int(min_wall_size)
        self.tick_size = float(tick_size)
        self.snapshot_interval_sec = int(snapshot_interval_sec)
        self.touch_distance_ticks = int(touch_distance_ticks)
        self.bounce_ticks = int(bounce_ticks)
        self.break_ticks = int(break_ticks)
        self.lookforward_sec = int(lookforward_sec)
        self.stale_distance_ticks = int(stale_distance_ticks)
        self.stale_timeout_sec = int(stale_timeout_sec)
        self.reappear_timeout_sec = int(reappear_timeout_sec)

        self._book = _OrderBookState()
        self._dom = DOMState()
        self._extractor = CausalFeatureExtractor(tick_size=self.tick_size, normalize=False)
        self._active: dict[str, _WallRuntime] = {}
        self._price_index: dict[tuple[str, float], str] = {}
        self._completed: list[WallEpisode] = []
        self._pending_touches: list[_PendingTouch] = []
        self._delta_events: deque[tuple[pd.Timestamp, int]] = deque()
        self._trade_events: deque[tuple[pd.Timestamp, str, float, int]] = deque()
        self._price_history: deque[tuple[pd.Timestamp, float]] = deque()
        self._recent_same_side_books: dict[str, list[tuple[float, float]]] = {"bid": [], "ask": []}
        self._last_timestamp: pd.Timestamp | None = None
        self._next_snapshot_time: pd.Timestamp | None = None
        self._current_session: str | None = None
        self._cumulative_delta = 0.0

    def process_event(
        self,
        action: str,
        side: str,
        order_id: int,
        price: float,
        size: int,
        timestamp: pd.Timestamp,
    ) -> None:
        """Process a single normalized MBO event. Core method."""
        if not action:
            return
        timestamp = pd.Timestamp(timestamp)
        normalized_price = self._normalize_price(price)
        self._last_timestamp = timestamp
        self._handle_session_transition(timestamp)

        if self.rth_only and not _is_rth(timestamp):
            return

        side_code = side or "N"
        order_id = int(order_id or 0)
        size = int(size or 0)
        prev_order = self._book.orders.get(order_id)

        if action == _ACTION_CLEAR:
            self._book.clear()
            self._refresh_dom(timestamp)
            self._advance_market_state(timestamp)
            return

        if action in (_ACTION_ADD, _ACTION_MODIFY, _ACTION_CANCEL, _ACTION_FILL, _ACTION_TRADE):
            self._book.apply(order_id, normalized_price, size, side_code, action)
            self._refresh_dom(timestamp)

        if prev_order is not None and action == _ACTION_MODIFY:
            prev_price, _, prev_side_code = prev_order
            if prev_side_code == side_code and prev_price != normalized_price and side_code in (_SIDE_BID, _SIDE_ASK):
                self._handle_reprice(timestamp, side_code, self._normalize_price(prev_price), normalized_price)

        if action in (_ACTION_FILL, _ACTION_TRADE) and prev_order is not None:
            prev_price, _, prev_side_code = prev_order
            if prev_side_code in (_SIDE_BID, _SIDE_ASK):
                self._record_fill(timestamp, prev_side_code, self._normalize_price(prev_price), size)
        if action == _ACTION_TRADE and side_code in (_SIDE_BID, _SIDE_ASK):
            self._record_trade(timestamp, side_code, normalized_price, size)

        affected: set[tuple[str, float]] = set()
        if side_code in (_SIDE_BID, _SIDE_ASK):
            side_name = "bid" if side_code == _SIDE_BID else "ask"
            affected.add((side_name, normalized_price))
            if prev_order is not None:
                prev_price, _, prev_side_code = prev_order
                if prev_side_code in (_SIDE_BID, _SIDE_ASK):
                    prev_side = "bid" if prev_side_code == _SIDE_BID else "ask"
                    affected.add((prev_side, self._normalize_price(prev_price)))
        for side_name, level_price in affected:
            self._update_or_create_episode(timestamp, side_name, level_price)

        self._advance_market_state(timestamp)
        self._prune_zero_sized(timestamp)

    def get_active_walls(self) -> list[dict[str, Any]]:
        """Return current active wall episodes with latest features and classifications."""
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        if best_bid <= 0 or best_ask <= 0:
            return []
        now = self._last_timestamp if self._last_timestamp is not None else pd.Timestamp.now(tz="UTC")
        mid_price = (best_bid + best_ask) / 2.0
        touch_band = self.touch_distance_ticks * self.tick_size
        active: list[dict[str, Any]] = []
        for runtime in self._active.values():
            if runtime.current_size < self.min_wall_size:
                continue
            features = self._feature_dict(runtime, now, mid_price)
            state = self._infer_state(runtime, now, mid_price)
            intent = self._label_intent(runtime, now, state)
            row: dict[str, Any] = {
                "episode_id": runtime.episode.episode_id,
                "price": runtime.current_price,
                "side": runtime.episode.side,
                "size": runtime.current_size,
                "max_size": runtime.max_size_so_far,
                "age_sec": runtime.age_seconds(now),
                "intent": intent.value,
                "state": state.value,
                "in_touch_band": runtime.in_touch_band,
            }
            row.update(features)
            if abs(mid_price - runtime.current_price) <= touch_band:
                row.update(
                    {
                        "touch_mid_price": mid_price,
                        "touch_distance_ticks": abs(mid_price - runtime.current_price) / self.tick_size,
                        "touch_tests_count": runtime.tests_count,
                        "touch_last_test_time": runtime.last_test_time,
                    }
                )
            active.append(row)
        return active

    def get_completed_episodes(self) -> list[WallEpisode]:
        """Return and drain completed episodes. Used by EpisodeLabeler for Parquet output."""
        completed = list(self._completed)
        self._completed.clear()
        return completed

    def flush_all(self) -> list[WallEpisode]:
        """Retire all active episodes (session end). Returns completed episodes.

        Samples final snapshots and resolves pending touches before retirement
        so callers don't need to reach into private methods.
        """
        if self._last_timestamp is not None:
            self._sample_due_snapshots(self._last_timestamp, force=True)
            self._resolve_pending_touches(self._last_timestamp, force=True)
            self._flush_all(self._last_timestamp)
        return self.get_completed_episodes()

    def reset(self) -> None:
        """Reset all state for a new session."""
        self._book.clear()
        self._dom = DOMState()
        self._active.clear()
        self._price_index.clear()
        self._completed.clear()
        self._pending_touches.clear()
        self._delta_events.clear()
        self._trade_events.clear()
        self._price_history.clear()
        self._recent_same_side_books = {"bid": [], "ask": []}
        self._last_timestamp = None
        self._next_snapshot_time = None
        self._current_session = None
        self._cumulative_delta = 0.0

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    @property
    def last_timestamp(self) -> pd.Timestamp | None:
        return self._last_timestamp

    def _handle_session_transition(self, timestamp: pd.Timestamp) -> None:
        session_date = str(timestamp.tz_convert("UTC").date())
        if self._current_session is None:
            self._current_session = session_date
            return
        if session_date == self._current_session:
            return
        self._sample_due_snapshots(timestamp, force=True)
        self._resolve_pending_touches(timestamp, force=True)
        self._flush_all(timestamp)
        self._book.clear()
        self._dom = DOMState()
        self._delta_events.clear()
        self._trade_events.clear()
        self._price_history.clear()
        self._recent_same_side_books = {"bid": [], "ask": []}
        self._next_snapshot_time = None
        self._current_session = session_date
        self._cumulative_delta = 0.0

    def _refresh_dom(self, timestamp: pd.Timestamp) -> None:
        bid_prices, bid_sizes, ask_prices, ask_sizes = self._book.top_levels()
        self._dom.update(bid_prices, bid_sizes, ask_prices, ask_sizes, ts=timestamp.timestamp())

    def _advance_market_state(self, timestamp: pd.Timestamp) -> None:
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        if best_bid <= 0 or best_ask <= 0:
            return
        mid_price = (best_bid + best_ask) / 2.0
        self._append_price_history(timestamp, mid_price)
        self._sample_due_snapshots(timestamp)
        self._detect_touches(timestamp, mid_price)
        self._update_pending_touches(timestamp, mid_price)
        self._resolve_pending_touches(timestamp)
        self._update_stale_status(timestamp, mid_price)
        self._recent_same_side_books["bid"] = self._levels_for_side("bid")
        self._recent_same_side_books["ask"] = self._levels_for_side("ask")

    def _append_price_history(self, timestamp: pd.Timestamp, mid_price: float) -> None:
        self._price_history.append((timestamp, mid_price))
        cutoff = timestamp - pd.Timedelta(seconds=120)
        while self._price_history and self._price_history[0][0] < cutoff:
            self._price_history.popleft()
        trade_cutoff = timestamp - pd.Timedelta(seconds=10)
        while self._trade_events and self._trade_events[0][0] < trade_cutoff:
            self._trade_events.popleft()
        delta_cutoff = timestamp - pd.Timedelta(seconds=10)
        while self._delta_events and self._delta_events[0][0] < delta_cutoff:
            self._delta_events.popleft()

    def _record_trade(self, timestamp: pd.Timestamp, side_code: str, price: float, size: int) -> None:
        signed = size if side_code == _SIDE_ASK else -size
        self._cumulative_delta += signed
        self._delta_events.append((timestamp, signed))
        side = "ask" if side_code == _SIDE_ASK else "bid"
        self._trade_events.append((timestamp, side, price, size))

    def _record_fill(self, timestamp: pd.Timestamp, side_code: str, price: float, size: int) -> None:
        side = "bid" if side_code == _SIDE_BID else "ask"
        episode_id = self._price_index.get((side, price))
        if episode_id is None:
            return
        runtime = self._active.get(episode_id)
        if runtime is None:
            return
        runtime.filled_volume += max(int(size), 0)
        runtime.absorbed_volume += max(int(size), 0)
        runtime.last_attack_volume_time = timestamp

    def _handle_reprice(self, timestamp: pd.Timestamp, side_code: str, old_price: float, new_price: float) -> None:
        side = "bid" if side_code == _SIDE_BID else "ask"
        episode_id = self._price_index.pop((side, old_price), None)
        if episode_id is None:
            return
        runtime = self._active.get(episode_id)
        if runtime is None:
            return
        normalized_new = self._normalize_price(new_price)
        runtime.current_price = normalized_new
        runtime.repricing_count += 1
        runtime.last_update = timestamp
        self._price_index[(side, normalized_new)] = episode_id

    def _update_or_create_episode(self, timestamp: pd.Timestamp, side: str, price: float) -> None:
        price = self._normalize_price(price)
        size = self._current_level_size(side, price)
        episode_id = self._price_index.get((side, price))
        runtime = self._active.get(episode_id) if episode_id is not None else None

        if runtime is None:
            if size < self.min_wall_size:
                return
            session_date = str(timestamp.tz_convert("UTC").date())
            episode_uuid = str(uuid.uuid5(_EPISODE_UUID_NAMESPACE, f"{session_date}:{side}:{price}"))
            episode = WallEpisode(
                episode_id=episode_uuid,
                session_date=session_date,
                side=side,
                price=price,
                first_seen=timestamp,
            )
            runtime = _WallRuntime(
                episode=episode,
                current_price=price,
                current_size=size,
                original_size=size,
                max_size_so_far=size,
                first_seen=timestamp,
                last_update=timestamp,
                last_size_change=timestamp,
                current_size_since=timestamp,
                previous_size=size,
            )
            runtime.size_history.append((timestamp, size))
            self._active[episode_uuid] = runtime
            self._price_index[(side, price)] = episode_uuid
            return

        previous = runtime.current_size
        runtime.last_update = timestamp
        runtime.current_price = price
        runtime.current_size = size
        runtime.max_size_so_far = max(runtime.max_size_so_far, size)
        if size != previous:
            runtime.modifications_so_far += 1
            runtime.modification_times.append(timestamp)
            runtime.last_size_change = timestamp
            runtime.current_size_since = timestamp
            runtime.size_history.append((timestamp, size))
            if len(runtime.size_history) > 256:
                runtime.size_history.popleft()
        if previous > 0 and size == 0:
            runtime.zero_since = timestamp
            if runtime.first_test_time is None and runtime.approach_near_time is not None:
                if (timestamp - runtime.approach_near_time).total_seconds() <= 2.0:
                    runtime.pull_approach_flag = True
        elif previous == 0 and size > 0:
            runtime.cancel_reappear_count += 1
            runtime.zero_since = None
        if previous > 0:
            depleted = previous - size
            if depleted > 0 and size < (0.5 * max(runtime.max_size_so_far, previous)):
                runtime.depletion_events += 1
            if depleted > 0 and size > previous:
                pass
        if previous > 0 and size > previous and runtime.depletion_events > runtime.refills_so_far:
            runtime.refills_so_far += 1
            depleted_size = max(runtime.max_size_so_far - previous, previous - min(size, previous), 1)
            runtime.refill_ratios.append((size - previous) / max(float(depleted_size), 1.0))
            if len(runtime.refill_ratios) > 32:
                runtime.refill_ratios.popleft()
            if runtime.last_test_time is not None and (timestamp - runtime.last_test_time).total_seconds() <= 5.0:
                if size >= 0.75 * max(runtime.original_size, runtime.max_size_so_far * 0.5):
                    runtime.recovery_after_test = True
        if self._tracks_bbo(side, price):
            runtime.bbo_track_count += 1
        runtime.previous_size = previous

    def _detect_touches(self, timestamp: pd.Timestamp, mid_price: float) -> None:
        band = self.touch_distance_ticks * self.tick_size
        for runtime in self._active.values():
            if runtime.current_size < self.min_wall_size:
                runtime.in_touch_band = False
                continue
            distance = abs(mid_price - runtime.current_price)
            if distance <= band:
                runtime.approach_near_time = timestamp
                if runtime.first_test_time is None:
                    runtime.first_test_time = timestamp
                if not runtime.in_touch_band:
                    runtime.in_touch_band = True
                    runtime.tests_count += 1
                    runtime.last_test_time = timestamp
                    runtime.recovery_after_test = False
                    features = self._feature_dict(runtime, timestamp, mid_price)
                    touch_index = runtime.episode.add_touch(
                        timestamp=timestamp,
                        mid_price=mid_price,
                        wall_price=runtime.current_price,
                        wall_size=runtime.current_size,
                        features=features,
                    )
                    self._pending_touches.append(
                        _PendingTouch(
                            episode_id=runtime.episode.episode_id,
                            touch_index=touch_index,
                            wall_price=runtime.current_price,
                            wall_side=runtime.episode.side,
                            deadline=timestamp + pd.Timedelta(seconds=self.lookforward_sec),
                            bounce_level=(
                                runtime.current_price - (self.bounce_ticks * self.tick_size)
                                if runtime.episode.side == "ask"
                                else runtime.current_price + (self.bounce_ticks * self.tick_size)
                            ),
                            break_level=(
                                runtime.current_price + (self.break_ticks * self.tick_size)
                                if runtime.episode.side == "ask"
                                else runtime.current_price - (self.break_ticks * self.tick_size)
                            ),
                        )
                    )
            else:
                runtime.in_touch_band = False

    def _update_pending_touches(self, timestamp: pd.Timestamp, mid_price: float) -> None:
        for pending in self._pending_touches:
            if pending.first_bounce_time is None:
                if pending.wall_side == "ask" and mid_price <= pending.bounce_level:
                    pending.first_bounce_time = timestamp
                elif pending.wall_side == "bid" and mid_price >= pending.bounce_level:
                    pending.first_bounce_time = timestamp
            if pending.first_break_time is None:
                if pending.wall_side == "ask" and mid_price >= pending.break_level:
                    pending.first_break_time = timestamp
                elif pending.wall_side == "bid" and mid_price <= pending.break_level:
                    pending.first_break_time = timestamp

    def _resolve_pending_touches(self, timestamp: pd.Timestamp, force: bool = False) -> None:
        remaining: list[_PendingTouch] = []
        for pending in self._pending_touches:
            if not force and timestamp < pending.deadline:
                remaining.append(pending)
                continue
            episode = self._find_episode(pending.episode_id)
            if episode is None:
                continue
            outcome = InteractionOutcome.CHURN
            if pending.first_break_time is not None and pending.first_bounce_time is not None:
                outcome = (
                    InteractionOutcome.BREAK
                    if pending.first_break_time <= pending.first_bounce_time
                    else InteractionOutcome.BOUNCE
                )
            elif pending.first_break_time is not None:
                outcome = InteractionOutcome.BREAK
            elif pending.first_bounce_time is not None:
                outcome = InteractionOutcome.BOUNCE
            if pending.touch_index < len(episode.touches):
                episode.resolve_touch(pending.touch_index, outcome, resolution_time=timestamp)
        self._pending_touches = remaining

    def _sample_due_snapshots(self, timestamp: pd.Timestamp, force: bool = False) -> None:
        if self._next_snapshot_time is None:
            self._next_snapshot_time = timestamp
        while force or (self._next_snapshot_time is not None and timestamp >= self._next_snapshot_time):
            sample_time = timestamp if force else self._next_snapshot_time
            if sample_time is None:
                break
            best_bid, _ = self._dom.best_bid()
            best_ask, _ = self._dom.best_ask()
            if best_bid > 0 and best_ask > 0:
                mid_price = (best_bid + best_ask) / 2.0
                for runtime in list(self._active.values()):
                    if runtime.current_size <= 0:
                        continue
                    features = self._feature_dict(runtime, sample_time, mid_price)
                    state = self._infer_state(runtime, sample_time, mid_price)
                    runtime.episode.add_snapshot(
                        timestamp=sample_time,
                        wall_price=runtime.current_price,
                        mid_price=mid_price,
                        wall_size=runtime.current_size,
                        state=state,
                        features=features,
                    )
            if force:
                break
            self._next_snapshot_time = sample_time + pd.Timedelta(seconds=self.snapshot_interval_sec)

    def _update_stale_status(self, timestamp: pd.Timestamp, mid_price: float) -> None:
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        for runtime in list(self._active.values()):
            if runtime.current_size <= 0:
                continue
            same_side_bbo = best_ask if runtime.episode.side == "ask" else best_bid
            distance_from_bbo = abs(runtime.current_price - same_side_bbo) / self.tick_size
            distance_from_mid = abs(runtime.current_price - mid_price) / self.tick_size
            if distance_from_bbo > self.stale_distance_ticks and distance_from_mid > self.stale_distance_ticks:
                if runtime.stale_since is None:
                    runtime.stale_since = timestamp
                elif (timestamp - runtime.stale_since).total_seconds() >= self.stale_timeout_sec:
                    self._retire_episode(runtime, timestamp, WallState.STALE, "stale")
            else:
                runtime.stale_since = None

    def _prune_zero_sized(self, timestamp: pd.Timestamp) -> None:
        for runtime in list(self._active.values()):
            if runtime.zero_since is None:
                continue
            if (timestamp - runtime.zero_since).total_seconds() < self.reappear_timeout_sec:
                continue
            final_state = WallState.CONSUMED if runtime.filled_volume >= max(1, int(0.5 * runtime.max_size_so_far)) else WallState.PULLED
            reason = "consumed" if final_state == WallState.CONSUMED else "pulled"
            self._retire_episode(runtime, timestamp, final_state, reason)

    def _retire_episode(self, runtime: _WallRuntime, timestamp: pd.Timestamp, final_state: WallState, reason: str) -> None:
        runtime.episode.intent_label = self._label_intent(runtime, timestamp, final_state)
        runtime.episode.retire(timestamp, final_state=final_state, reason=reason)
        self._completed.append(runtime.episode)
        self._active.pop(runtime.episode.episode_id, None)
        self._price_index.pop((runtime.episode.side, runtime.current_price), None)

    def _flush_all(self, timestamp: pd.Timestamp) -> None:
        for runtime in list(self._active.values()):
            self._retire_episode(runtime, timestamp, self._infer_terminal_state(runtime), "session_end")

    def _feature_dict(self, runtime: _WallRuntime, timestamp: pd.Timestamp, mid_price: float) -> dict[str, float]:
        market_context = self._market_context(runtime, timestamp, mid_price)
        flow_context = self._flow_context(runtime, timestamp, mid_price)
        attack_context = self._attack_context(runtime, timestamp)
        wall_data = {
            "current_size": runtime.current_size,
            "original_size": runtime.original_size,
            "max_size_so_far": runtime.max_size_so_far,
            "age_seconds": runtime.age_seconds(timestamp),
            "side": runtime.episode.side,
            "modifications_so_far": runtime.modifications_so_far,
            "refills_so_far": runtime.refills_so_far,
            "modification_times": [max((timestamp - ts).total_seconds(), 0.0) for ts in runtime.modification_times],
            "recent_sizes": [size for ts, size in runtime.size_history if (timestamp - ts).total_seconds() <= 10.0],
            "refill_ratios": list(runtime.refill_ratios),
            "cancel_reappear_count": runtime.cancel_reappear_count,
            "pull_approach_flag": runtime.pull_approach_flag,
            "repricing_count": runtime.repricing_count,
            "time_at_current_size": (
                (timestamp - runtime.current_size_since).total_seconds() if runtime.current_size_since is not None else 0.0
            ),
            "wall_price": runtime.current_price,
        }
        vec = self._extractor.extract(wall_data, market_context, flow_context, attack_context)
        return {name: float(vec[idx]) for idx, name in enumerate(CAUSAL_FEATURE_NAMES)}

    def _market_context(self, runtime: _WallRuntime, timestamp: pd.Timestamp, mid_price: float) -> dict[str, Any]:
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        bid_levels = self._levels_for_side("bid")
        ask_levels = self._levels_for_side("ask")
        same_side_levels = bid_levels if runtime.episode.side == "bid" else ask_levels
        opposite_side_levels = ask_levels if runtime.episode.side == "bid" else bid_levels
        returns = self._recent_price_returns(seconds=120)
        recent_ranges, current_range = self._range_features(timestamp)
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "bid_volumes": [size for _, size in bid_levels],
            "ask_volumes": [size for _, size in ask_levels],
            "same_side_levels": same_side_levels,
            "opposite_side_levels": opposite_side_levels,
            "prior_same_side_levels": self._recent_same_side_books[runtime.episode.side],
            "session_phase": self._session_phase(timestamp),
            "minutes_since_open": self._minutes_since_open(timestamp),
            "price_returns_2m": returns,
            "recent_ranges": recent_ranges,
            "current_range": current_range,
        }

    def _flow_context(self, runtime: _WallRuntime, timestamp: pd.Timestamp, mid_price: float) -> dict[str, Any]:
        return {
            "cumulative_delta": self._cumulative_delta,
            "delta_2s": self._window_delta(timestamp, 2),
            "delta_10s": self._window_delta(timestamp, 10),
            "approach_speed": self._approach_speed(timestamp, runtime.current_price, runtime.episode.side),
            "consecutive_aggressor": self._consecutive_aggressor(),
            "sweep_flag": self._sweep_flag(timestamp),
        }

    def _attack_context(self, runtime: _WallRuntime, timestamp: pd.Timestamp) -> dict[str, Any]:
        time_since_last_test = (
            (timestamp - runtime.last_test_time).total_seconds() if runtime.last_test_time is not None else 0.0
        )
        attack_intensity = 0.0
        if runtime.last_attack_volume_time is not None and runtime.last_test_time is not None:
            elapsed = max((timestamp - runtime.last_test_time).total_seconds(), 1.0)
            attack_intensity = runtime.absorbed_volume / elapsed
        return {
            "absorbed_volume": runtime.absorbed_volume,
            "tests_count": runtime.tests_count,
            "recovery_after_test": runtime.recovery_after_test,
            "time_since_last_test": time_since_last_test,
            "attack_intensity": attack_intensity,
        }

    def _infer_state(self, runtime: _WallRuntime, timestamp: pd.Timestamp, mid_price: float) -> WallState:
        distance_ticks = abs(mid_price - runtime.current_price) / self.tick_size
        if runtime.current_size <= 0:
            return WallState.PULLED
        if runtime.filled_volume >= max(1, int(0.5 * runtime.max_size_so_far)):
            return WallState.CONSUMED
        if distance_ticks <= 2:
            if runtime.absorbed_volume > 0 and runtime.recovery_after_test:
                return WallState.DEFENDING
            if runtime.current_size <= 0.25 * max(runtime.max_size_so_far, 1):
                return WallState.EXHAUSTED
            return WallState.UNDER_ATTACK
        if runtime.age_seconds(timestamp) < 30 and runtime.tests_count == 0:
            return WallState.FRESH
        if runtime.stale_since is not None:
            return WallState.STALE
        return WallState.ESTABLISHED

    def _infer_terminal_state(self, runtime: _WallRuntime) -> WallState:
        if runtime.current_size <= 0:
            if runtime.filled_volume >= max(1, int(0.5 * runtime.max_size_so_far)):
                return WallState.CONSUMED
            return WallState.PULLED
        if runtime.stale_since is not None:
            return WallState.STALE
        if runtime.current_size <= 0.25 * max(runtime.max_size_so_far, 1):
            return WallState.EXHAUSTED
        return WallState.ESTABLISHED

    def _label_intent(self, runtime: _WallRuntime, timestamp: pd.Timestamp, final_state: WallState) -> WallIntent:
        if runtime.first_test_time is None and final_state == WallState.PULLED:
            return WallIntent.SPOOF_LIKE
        if runtime.pull_approach_flag:
            return WallIntent.SPOOF_LIKE
        if runtime.refills_so_far >= 2 and runtime.depletion_events >= 1:
            return WallIntent.RESERVE_REFRESH
        if runtime.repricing_count >= 3 and runtime.bbo_track_count >= 2:
            return WallIntent.MIGRATORY
        if runtime.age_seconds(timestamp) >= 30.0 or runtime.absorbed_volume >= max(10, int(0.25 * runtime.max_size_so_far)):
            return WallIntent.PASSIVE_REAL
        return WallIntent.PASSIVE_REAL

    def _levels_for_side(self, side: str) -> list[tuple[float, float]]:
        prices, sizes = (
            (list(self._dom.bid_prices), list(self._dom.bid_sizes))
            if side == "bid"
            else (list(self._dom.ask_prices), list(self._dom.ask_sizes))
        )
        return [(float(price), float(size)) for price, size in zip(prices, sizes, strict=False) if price > 0 and size > 0]

    def _range_features(self, timestamp: pd.Timestamp) -> tuple[list[float], float]:
        if not self._price_history:
            return [], 0.0
        current_cutoff = timestamp - pd.Timedelta(seconds=12)
        current_prices = [price for ts, price in self._price_history if ts >= current_cutoff]
        current_range = ((max(current_prices) - min(current_prices)) / self.tick_size) if len(current_prices) >= 2 else 0.0
        recent_ranges: list[float] = []
        for idx in range(1, 11):
            window_end = timestamp - pd.Timedelta(seconds=12 * idx)
            window_start = window_end - pd.Timedelta(seconds=12)
            prices = [price for ts, price in self._price_history if window_start <= ts < window_end]
            if len(prices) >= 2:
                recent_ranges.append((max(prices) - min(prices)) / self.tick_size)
        return recent_ranges, float(current_range)

    def _recent_price_returns(self, seconds: int) -> list[float]:
        if len(self._price_history) < 2:
            return []
        cutoff = self._price_history[-1][0] - pd.Timedelta(seconds=seconds)
        filtered = [(ts, price) for ts, price in self._price_history if ts >= cutoff]
        returns: list[float] = []
        for idx in range(1, len(filtered)):
            returns.append((filtered[idx][1] - filtered[idx - 1][1]) / self.tick_size)
        return returns

    def _window_delta(self, timestamp: pd.Timestamp, seconds: int) -> float:
        cutoff = timestamp - pd.Timedelta(seconds=seconds)
        return float(sum(delta for ts, delta in self._delta_events if ts >= cutoff))

    def _approach_speed(self, timestamp: pd.Timestamp, wall_price: float, side: str) -> float:
        if not self._price_history:
            return 0.0
        cutoff = timestamp - pd.Timedelta(seconds=5)
        reference_ts, reference_price = self._price_history[0]
        for ts, price in self._price_history:
            reference_ts, reference_price = ts, price
            if ts >= cutoff:
                break
        elapsed = max((timestamp - reference_ts).total_seconds(), 1e-9)
        current_mid = self._price_history[-1][1]
        move_toward = (current_mid - reference_price) if side == "ask" else (reference_price - current_mid)
        if abs(current_mid - wall_price) > abs(reference_price - wall_price):
            move_toward *= -1.0
        return (move_toward / self.tick_size) / elapsed

    def _consecutive_aggressor(self) -> float:
        if not self._trade_events:
            return 0.0
        last_side = self._trade_events[-1][1]
        streak = 0
        for _, side, _, _ in reversed(self._trade_events):
            if side != last_side:
                break
            streak += 1
        return float(streak)

    def _sweep_flag(self, timestamp: pd.Timestamp) -> bool:
        cutoff = timestamp - pd.Timedelta(milliseconds=500)
        prices = {round(price, 10) for ts, _, price, _ in self._trade_events if ts >= cutoff}
        return len(prices) >= 3

    def _tracks_bbo(self, side: str, price: float) -> bool:
        best_bid, _ = self._dom.best_bid()
        best_ask, _ = self._dom.best_ask()
        bbo = best_ask if side == "ask" else best_bid
        return abs(price - bbo) <= self.tick_size

    def _current_level_size(self, side: str, price: float) -> int:
        if side == "bid":
            return int(self._book.bid_levels.get(price, 0))
        return int(self._book.ask_levels.get(price, 0))

    def _session_phase(self, timestamp: pd.Timestamp) -> int:
        minutes = self._minutes_since_open(timestamp)
        if minutes < 0:
            return 0
        if minutes < 30:
            return 1
        if minutes < 150:
            return 2
        if minutes < 270:
            return 3
        if minutes < 360:
            return 4
        return 5

    def _minutes_since_open(self, timestamp: pd.Timestamp) -> float:
        ts = timestamp.tz_convert("UTC")
        open_ts = pd.Timestamp.combine(ts.date(), RTH_START).tz_localize("UTC")
        return (ts - open_ts).total_seconds() / 60.0

    def _find_episode(self, episode_id: str) -> WallEpisode | None:
        runtime = self._active.get(episode_id)
        if runtime is not None:
            return runtime.episode
        for episode in self._completed:
            if episode.episode_id == episode_id:
                return episode
        return None

    def _normalize_price(self, price: float) -> float:
        ticks = round(float(price) / self.tick_size)
        return round(ticks * self.tick_size, 10)


__all__ = ["MBOWallEngine"]
