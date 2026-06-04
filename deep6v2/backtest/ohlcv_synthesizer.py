from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from deep6v2.types.bar import FootprintBar, SessionType

ET = ZoneInfo("America/New_York")
TICK = 0.25


def synthesize_footprint(
    ts: datetime,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: int,
    bar_index: int,
    cvd_accum: float,
) -> FootprintBar:
    """Convert an OHLCV bar into a synthetic FootprintBar."""
    total_volume = max(int(volume), 1)
    low = round(float(low), 2)
    high = round(float(high), 2)
    open_ = round(float(open_), 2)
    close = round(float(close), 2)

    bar_range = max(high - low, TICK)
    levels = _price_levels(low, high)
    if not levels:
        levels = [close]

    body_bias = 0.0 if bar_range <= 0 else max(-1.0, min(1.0, (close - open_) / bar_range))
    close_bias = 0.0 if bar_range <= 0 else max(-1.0, min(1.0, (((close - low) / bar_range) * 2.0) - 1.0))
    vwap_anchor = ((open_ + high + low + close) / 4.0) + (close_bias * (bar_range * 0.12))
    sigma = max(bar_range / 5.0, TICK / 2.0)

    weights: list[float] = []
    for level in levels:
        pos = 0.5 if bar_range <= 0 else (level - low) / bar_range
        gaussian = math.exp(-0.5 * ((level - vwap_anchor) / sigma) ** 2)
        tail_bonus = 1.0 + (0.30 * (1.0 - abs((pos * 2.0) - 1.0)))
        close_pull = 1.0 + (0.20 * close_bias * ((pos * 2.0) - 1.0))
        weights.append(max(gaussian * tail_bonus * close_pull, 0.001))

    total_weight = sum(weights) or 1.0
    normalized = [weight / total_weight for weight in weights]
    level_volumes = [int(total_volume * weight) for weight in normalized]

    allocated = sum(level_volumes)
    remainder = total_volume - allocated
    if remainder > 0:
        ranked = sorted(range(len(levels)), key=lambda idx: normalized[idx], reverse=True)
        for i in range(remainder):
            level_volumes[ranked[i % len(ranked)]] += 1
    elif remainder < 0:
        ranked = sorted(range(len(levels)), key=lambda idx: level_volumes[idx], reverse=True)
        for idx in ranked:
            if remainder == 0:
                break
            removable = min(level_volumes[idx], -remainder)
            level_volumes[idx] -= removable
            remainder += removable

    bid_volumes: dict[float, int] = {}
    ask_volumes: dict[float, int] = {}
    for idx, level in enumerate(levels):
        total_at_level = max(level_volumes[idx], 0)
        if total_at_level == 0:
            bid_volumes[level] = 0
            ask_volumes[level] = 0
            continue

        pos = 0.5 if bar_range <= 0 else (level - low) / bar_range
        position_bias = ((pos * 2.0) - 1.0) * 0.30
        directional_bias = body_bias * 0.28
        close_position_bias = close_bias * 0.18
        ask_pct = 0.50 + position_bias + directional_bias + close_position_bias
        ask_pct = max(0.05, min(0.95, ask_pct))
        ask_volume = int(round(total_at_level * ask_pct))
        ask_volume = max(0, min(total_at_level, ask_volume))
        bid_volume = total_at_level - ask_volume

        if total_at_level > 1 and bid_volume == 0:
            bid_volume = 1
            ask_volume -= 1
        if total_at_level > 1 and ask_volume == 0:
            ask_volume = 1
            bid_volume -= 1

        bid_volumes[level] = bid_volume
        ask_volumes[level] = ask_volume

    combined = {level: bid_volumes[level] + ask_volumes[level] for level in levels}
    total_bid = sum(bid_volumes.values())
    total_ask = sum(ask_volumes.values())
    delta = int(total_ask - total_bid)
    poc_price = max(combined, key=lambda price: (combined[price], -abs(price - close)))
    poc_volume = combined[poc_price]
    vah, val = _value_area(combined, total_volume, poc_price, high, low)
    cvd = cvd_accum + delta

    return FootprintBar(
        open=open_,
        high=high,
        low=low,
        close=close,
        delta=delta,
        total_volume=total_volume,
        bid_volumes=bid_volumes,
        ask_volumes=ask_volumes,
        poc_price=poc_price,
        poc_volume=poc_volume,
        vah=vah,
        val=val,
        cvd=cvd,
        bar_index=bar_index,
        timestamp=ts,
        session_type=SessionType.RTH,
    )


def _price_levels(low: float, high: float) -> list[float]:
    levels: list[float] = []
    current = low
    ceiling = high + 1e-9
    while current <= ceiling:
        levels.append(round(current, 2))
        current = round(current + TICK, 10)
    if levels and levels[-1] != round(high, 2):
        levels.append(round(high, 2))
    return sorted(set(levels))


def _value_area(
    combined: dict[float, int],
    total_volume: int,
    poc_price: float,
    high: float,
    low: float,
) -> tuple[float, float]:
    if not combined:
        return high, low

    target = total_volume * 0.70
    ordered_levels = sorted(combined)
    included = {poc_price}
    running = combined[poc_price]
    poc_index = ordered_levels.index(poc_price)
    left = poc_index - 1
    right = poc_index + 1

    while running < target and (left >= 0 or right < len(ordered_levels)):
        left_volume = combined[ordered_levels[left]] if left >= 0 else -1
        right_volume = combined[ordered_levels[right]] if right < len(ordered_levels) else -1
        if right_volume > left_volume:
            included.add(ordered_levels[right])
            running += right_volume
            right += 1
        else:
            included.add(ordered_levels[left])
            running += left_volume
            left -= 1

    return max(included) if included else high, min(included) if included else low


__all__ = ["ET", "TICK", "synthesize_footprint"]
