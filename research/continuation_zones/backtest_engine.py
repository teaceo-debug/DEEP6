from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from .continuation_zones import ContinuationZoneDetector, Zone, score_continuation_zone
from .data_loader import OHLCV_COLUMNS, apply_rth_filter


EPSILON_SCALE = 1e-6


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    zone_kind: Literal["RBR", "DBD"]
    zone_timeframe: int
    zone_score: int
    zone_score_at_entry: int
    entry_price: float
    exit_price: float
    direction: Literal["long", "short"]
    stop_price: float
    target_price: float
    pnl_ticks: float
    pnl_dollars: float
    exit_reason: Literal["target", "stop", "trail", "session_end", "invalidation"]
    bars_held: int
    mae_ticks: float
    mfe_ticks: float


@dataclass
class BacktestConfig:
    small_body_ratio: float = 0.35
    min_zone_ticks: int = 2
    max_zone_age_bars_5m: int = 300
    max_zone_age_bars_15m: int = 100
    max_touch_count: int = 3
    min_score: int = 5
    stop_ticks: int = 10
    target_ticks: int = 16
    breakeven_ticks: int = 6
    trail_ticks: int = 0
    trail_activation_ticks: int = 10
    tick_size: float = 0.25
    tick_value: float = 5.0
    rth_only: bool = True
    slippage_ticks: int = 1
    commission_per_side: float = 2.0


@dataclass
class _ZoneState:
    zone: Zone
    confirmation_start: pd.Timestamp
    available_from: pd.Timestamp
    initial_score: int
    touch_count: int
    score: int
    is_active: bool
    prior_overlap: bool


@dataclass
class _Position:
    zone_state: _ZoneState
    direction: Literal["long", "short"]
    entry_idx: int
    entry_time: pd.Timestamp
    entry_price: float
    initial_stop_price: float
    target_price: float
    current_stop_price: float
    trail_active: bool
    trail_updated: bool
    zone_score_at_entry: int
    mfe_ticks: float = 0.0
    mae_ticks: float = 0.0


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self._epsilon = config.tick_size * EPSILON_SCALE

    def run(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame) -> list[Trade]:
        frame_5m = self._prepare_frame(df_5m)
        frame_15m = self._prepare_frame(df_15m)

        detector_5m = ContinuationZoneDetector(
            small_body_ratio=self.config.small_body_ratio,
            min_zone_ticks=self.config.min_zone_ticks,
            max_zone_age_bars=self.config.max_zone_age_bars_5m,
            max_touch_count=self.config.max_touch_count,
            min_score=self.config.min_score,
            tick_size=self.config.tick_size,
        )
        zones_5m = detector_5m.detect(frame_5m, timeframe_min=5)

        detector_15m = ContinuationZoneDetector(
            small_body_ratio=self.config.small_body_ratio,
            min_zone_ticks=self.config.min_zone_ticks,
            max_zone_age_bars=self.config.max_zone_age_bars_15m,
            max_touch_count=self.config.max_touch_count,
            min_score=self.config.min_score,
            tick_size=self.config.tick_size,
        )
        zones_15m = detector_15m.detect(frame_15m, timeframe_min=15)

        zone_states = self._build_zone_states(frame_5m, frame_5m, zones_5m)
        zone_states.extend(self._build_zone_states(frame_15m, frame_5m, zones_15m))
        zone_states.sort(key=lambda state: (state.available_from, state.zone.timeframe_min, state.zone.created_bar_idx))

        trades: list[Trade] = []
        open_position: _Position | None = None

        for bar_idx, (timestamp, bar) in enumerate(frame_5m.iterrows()):
            touched_zone_ids: set[int] = set()

            if open_position is None:
                chosen_state = self._select_entry_zone(zone_states, timestamp, bar)
                if chosen_state is not None:
                    touched_zone_ids.add(id(chosen_state))
                    zone_score_at_entry = chosen_state.score
                    self._register_touch(chosen_state)
                    open_position = self._open_position(chosen_state, bar_idx, timestamp, zone_score_at_entry)

            if open_position is not None:
                trade = self._manage_position(open_position, bar_idx, timestamp, bar, frame_5m)
                if trade is not None:
                    trades.append(trade)
                    open_position = None

            self._update_zone_lifecycle(zone_states, timestamp, bar, touched_zone_ids)

        return trades

    def _prepare_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        frame = df.copy()
        if "ts_event" in frame.columns:
            frame = frame.set_index("ts_event")
        if not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
        elif frame.index.tz is None:
            frame.index = frame.index.tz_localize("UTC")
        else:
            frame.index = frame.index.tz_convert("UTC")
        frame.index.name = "ts_event"
        missing = [column for column in OHLCV_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(f"frame missing required columns: {missing}")
        frame = frame.loc[:, OHLCV_COLUMNS].sort_index()
        return apply_rth_filter(frame) if self.config.rth_only else frame

    def _build_zone_states(
        self,
        source_frame: pd.DataFrame,
        timeline_5m: pd.DataFrame,
        zones: list[Zone],
    ) -> list[_ZoneState]:
        states: list[_ZoneState] = []
        for zone in zones:
            confirmation_idx = zone.created_bar_idx + 1
            if confirmation_idx >= len(source_frame):
                continue
            confirmation_start = pd.Timestamp(source_frame.index[confirmation_idx])
            available_from = confirmation_start + pd.Timedelta(minutes=zone.timeframe_min)
            if timeline_5m.index.searchsorted(available_from, side="left") >= len(timeline_5m.index):
                continue
            states.append(
                _ZoneState(
                    zone=self._clone_zone(zone),
                    confirmation_start=confirmation_start,
                    available_from=available_from,
                    initial_score=zone.score,
                    touch_count=0,
                    score=zone.score,
                    is_active=True,
                    prior_overlap=False,
                )
            )
        return states

    def _clone_zone(self, zone: Zone) -> Zone:
        return Zone(
            kind=zone.kind,
            timeframe_min=zone.timeframe_min,
            top=zone.top,
            bottom=zone.bottom,
            entry_price=zone.entry_price,
            created_bar_idx=zone.created_bar_idx,
            created_at=zone.created_at,
            score=zone.score,
            score_freshness=zone.score_freshness,
            score_departure=zone.score_departure,
            score_base=zone.score_base,
            score_trend=zone.score_trend,
            score_height=zone.score_height,
            touch_count=0,
            is_active=True,
            departure_body_bp=zone.departure_body_bp,
            departure_ext_bp=zone.departure_ext_bp,
            base_body_bp=zone.base_body_bp,
            zone_height_ticks=zone.zone_height_ticks,
            trend_close_ok=zone.trend_close_ok,
            trend_slope_ok=zone.trend_slope_ok,
        )

    def _select_entry_zone(
        self,
        zone_states: list[_ZoneState],
        timestamp: pd.Timestamp,
        bar: pd.Series,
    ) -> _ZoneState | None:
        triggered: list[_ZoneState] = []
        for state in zone_states:
            if not self._zone_is_tradeable(state, timestamp):
                continue
            if state.zone.kind == "RBR" and float(bar["low"]) <= state.zone.entry_price + self._epsilon:
                triggered.append(state)
            elif state.zone.kind == "DBD" and float(bar["high"]) >= state.zone.entry_price - self._epsilon:
                triggered.append(state)
        if not triggered:
            return None
        triggered.sort(key=lambda state: (state.score, state.zone.timeframe_min), reverse=True)
        return triggered[0]

    def _zone_is_tradeable(self, state: _ZoneState, timestamp: pd.Timestamp) -> bool:
        if not state.is_active or timestamp < state.available_from:
            return False
        if state.score < self.config.min_score:
            return False
        if self._age_bars(state, timestamp) > self._max_zone_age(state.zone.timeframe_min):
            return False
        return state.touch_count < self.config.max_touch_count

    def _open_position(
        self,
        state: _ZoneState,
        bar_idx: int,
        timestamp: pd.Timestamp,
        zone_score_at_entry: int,
    ) -> _Position:
        direction: Literal["long", "short"] = "long" if state.zone.kind == "RBR" else "short"
        entry_price = state.zone.entry_price
        stop_offset = self.config.stop_ticks * self.config.tick_size
        target_offset = self.config.target_ticks * self.config.tick_size
        initial_stop = entry_price - stop_offset if direction == "long" else entry_price + stop_offset
        target_price = entry_price + target_offset if direction == "long" else entry_price - target_offset
        return _Position(
            zone_state=state,
            direction=direction,
            entry_idx=bar_idx,
            entry_time=timestamp,
            entry_price=entry_price,
            initial_stop_price=initial_stop,
            target_price=target_price,
            current_stop_price=initial_stop,
            trail_active=False,
            trail_updated=False,
            zone_score_at_entry=zone_score_at_entry,
        )

    def _manage_position(
        self,
        position: _Position,
        bar_idx: int,
        timestamp: pd.Timestamp,
        bar: pd.Series,
        frame_5m: pd.DataFrame,
    ) -> Trade | None:
        high = float(bar["high"])
        low = float(bar["low"])
        open_price = float(bar["open"])
        close = float(bar["close"])

        if position.direction == "long":
            position.mfe_ticks = max(position.mfe_ticks, max(0.0, (high - position.entry_price) / self.config.tick_size))
            position.mae_ticks = max(position.mae_ticks, max(0.0, (position.entry_price - low) / self.config.tick_size))
            target_hit = high >= position.target_price - self._epsilon
            stop_hit = low <= position.current_stop_price + self._epsilon
            invalidated = min(open_price, close) < position.zone_state.zone.bottom - self._epsilon
        else:
            position.mfe_ticks = max(position.mfe_ticks, max(0.0, (position.entry_price - low) / self.config.tick_size))
            position.mae_ticks = max(position.mae_ticks, max(0.0, (high - position.entry_price) / self.config.tick_size))
            target_hit = low <= position.target_price + self._epsilon
            stop_hit = high >= position.current_stop_price - self._epsilon
            invalidated = max(open_price, close) > position.zone_state.zone.top + self._epsilon

        if target_hit:
            reason: Literal["target", "stop", "trail", "session_end", "invalidation"] = "target"
            exit_price = position.target_price
            return self._finalize_trade(position, bar_idx, timestamp, exit_price, reason)

        if stop_hit:
            reason = "trail" if position.trail_updated else "stop"
            exit_price = position.current_stop_price
            return self._finalize_trade(position, bar_idx, timestamp, exit_price, reason)

        if invalidated:
            return self._finalize_trade(position, bar_idx, timestamp, close, "invalidation")

        if self._is_session_end(frame_5m, bar_idx):
            return self._finalize_trade(position, bar_idx, timestamp, close, "session_end")

        self._update_protective_stops(position)
        return None

    def _update_protective_stops(self, position: _Position) -> None:
        be_distance = self.config.breakeven_ticks
        if be_distance > 0 and position.mfe_ticks >= be_distance:
            if position.direction == "long":
                position.current_stop_price = max(position.current_stop_price, position.entry_price)
            else:
                position.current_stop_price = min(position.current_stop_price, position.entry_price)

        if self.config.trail_ticks <= 0 or position.mfe_ticks < self.config.trail_activation_ticks:
            return

        position.trail_active = True
        position.trail_updated = True
        if position.direction == "long":
            candidate = position.entry_price + max(0.0, position.mfe_ticks - self.config.trail_ticks) * self.config.tick_size
            position.current_stop_price = max(position.current_stop_price, candidate)
        else:
            candidate = position.entry_price - max(0.0, position.mfe_ticks - self.config.trail_ticks) * self.config.tick_size
            position.current_stop_price = min(position.current_stop_price, candidate)

    def _finalize_trade(
        self,
        position: _Position,
        bar_idx: int,
        timestamp: pd.Timestamp,
        exit_price: float,
        exit_reason: Literal["target", "stop", "trail", "session_end", "invalidation"],
    ) -> Trade:
        direction_sign = 1.0 if position.direction == "long" else -1.0
        raw_pnl_ticks = ((exit_price - position.entry_price) * direction_sign) / self.config.tick_size
        net_pnl_ticks = raw_pnl_ticks - (2 * self.config.slippage_ticks)
        net_pnl_dollars = (net_pnl_ticks * self.config.tick_value) - (2 * self.config.commission_per_side)
        return Trade(
            entry_time=position.entry_time,
            exit_time=timestamp,
            zone_kind=position.zone_state.zone.kind,
            zone_timeframe=position.zone_state.zone.timeframe_min,
            zone_score=position.zone_state.initial_score,
            zone_score_at_entry=position.zone_score_at_entry,
            entry_price=position.entry_price,
            exit_price=exit_price,
            direction=position.direction,
            stop_price=position.initial_stop_price,
            target_price=position.target_price,
            pnl_ticks=float(net_pnl_ticks),
            pnl_dollars=float(net_pnl_dollars),
            exit_reason=exit_reason,
            bars_held=(bar_idx - position.entry_idx) + 1,
            mae_ticks=float(position.mae_ticks),
            mfe_ticks=float(position.mfe_ticks),
        )

    def _update_zone_lifecycle(
        self,
        zone_states: list[_ZoneState],
        timestamp: pd.Timestamp,
        bar: pd.Series,
        touched_zone_ids: set[int],
    ) -> None:
        high = float(bar["high"])
        low = float(bar["low"])
        body_max = max(float(bar["open"]), float(bar["close"]))
        body_min = min(float(bar["open"]), float(bar["close"]))

        for state in zone_states:
            if not state.is_active or timestamp < state.available_from:
                continue

            invalidated = (
                body_min < state.zone.bottom - self._epsilon
                if state.zone.kind == "RBR"
                else body_max > state.zone.top + self._epsilon
            )
            if invalidated:
                state.is_active = False
                state.prior_overlap = False
                continue

            overlaps = high >= state.zone.bottom - self._epsilon and low <= state.zone.top + self._epsilon
            if overlaps and not state.prior_overlap and id(state) not in touched_zone_ids:
                self._register_touch(state)
            state.prior_overlap = overlaps

            if self._age_bars(state, timestamp) > self._max_zone_age(state.zone.timeframe_min):
                state.is_active = False
                continue
            if state.touch_count >= self.config.max_touch_count:
                state.is_active = False

    def _register_touch(self, state: _ZoneState) -> None:
        state.touch_count += 1
        state.zone.touch_count = state.touch_count
        score, components = score_continuation_zone(
            timeframe_min=state.zone.timeframe_min,
            touch_count=state.touch_count,
            departure_body_to_height_bp=state.zone.departure_body_bp,
            departure_close_extension_to_height_bp=state.zone.departure_ext_bp,
            base_candle_count=1,
            max_base_body_ratio_bp=state.zone.base_body_bp,
            trend_close_side_ok=state.zone.trend_close_ok,
            trend_slope_ok=state.zone.trend_slope_ok,
            zone_height_ticks=state.zone.zone_height_ticks,
        )
        state.zone.score_freshness = components["freshness"]
        state.zone.score = score
        state.score = score

    def _age_bars(self, state: _ZoneState, timestamp: pd.Timestamp) -> int:
        if timestamp < state.available_from:
            return -1
        elapsed = timestamp - state.available_from
        bar_size = pd.Timedelta(minutes=state.zone.timeframe_min)
        return max(0, int(elapsed // bar_size))

    def _max_zone_age(self, timeframe_min: int) -> int:
        return self.config.max_zone_age_bars_5m if timeframe_min == 5 else self.config.max_zone_age_bars_15m

    def _is_session_end(self, frame_5m: pd.DataFrame, bar_idx: int) -> bool:
        if bar_idx == len(frame_5m) - 1:
            return True
        current = frame_5m.index[bar_idx].tz_convert("America/New_York")
        nxt = frame_5m.index[bar_idx + 1].tz_convert("America/New_York")
        return current.date() != nxt.date()


__all__ = ["BacktestConfig", "BacktestEngine", "Trade"]
