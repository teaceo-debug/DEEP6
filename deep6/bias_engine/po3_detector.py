"""PO3 daily bias algorithms — ICT Power of 3 in Python.

Implements the AMD cycle bias-finding engine:
  - Midnight Open tracking (primary daily anchor)
  - Weekly Open tracking (macro context)
  - Asia range freeze (Accumulation session H/L)
  - Judas Swing detection (sweep + close past Asia EQ)
  - Premium/Discount zone scoring (vs previous day EQ)
  - 0-6 point bias score per the PO3 Pine Script spec

Usage:
    detector = PO3BiasDetector()
    detector.set_prev_day(high=21200, low=21050, open_=21080, close=21180)
    state = detector.update_bar(bar_time_utc, open_, high, low, close)
    print(state.direction, state.bull_pts, state.judas_status)

Feed bars chronologically from any source: Rithmic, Databento, or
reconstructed from a TradingView webhook payload.
"""
from __future__ import annotations

import zoneinfo
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from deep6.bias_engine.models import (
    BiasDirection,
    JudasStatus,
    PO3BiasState,
    PO3Phase,
)

_ET = zoneinfo.ZoneInfo("America/New_York")


def _to_et(dt: datetime) -> datetime:
    return dt.astimezone(_ET)


def _phase_from_hour(et_hour: int) -> PO3Phase:
    """Map ET hour to PO3 phase.

    Accumulation : 18:00–00:00
    Manipulation : 00:00–07:00  (London, Judas sweep)
    Distribution : 07:00–13:00  (NY AM, real move)
    Between      : 13:00–18:00  (afternoon)
    """
    if et_hour >= 18:
        return PO3Phase.ACCUMULATION
    elif et_hour < 7:
        return PO3Phase.MANIPULATION
    elif et_hour < 13:
        return PO3Phase.DISTRIBUTION
    return PO3Phase.BETWEEN


class PO3BiasDetector:
    """Stateful PO3 bias engine — call update_bar() on every OHLCV bar close.

    Thread-unsafe by design (single asyncio task feeds it). All state is
    per-day and resets automatically at the 18:00 ET Accumulation start.
    """

    def __init__(self) -> None:
        # Day anchors
        self._midnight_open: Optional[float] = None
        self._midnight_dom: int = -1          # day-of-month when MO was set

        # Week anchor
        self._weekly_open: Optional[float] = None
        self._weekly_woy: int = -1

        # Previous day OHLC (set externally via set_prev_day)
        self._pd_high: Optional[float] = None
        self._pd_low: Optional[float] = None
        self._pd_open: Optional[float] = None
        self._pd_close: Optional[float] = None

        # Live accumulation session range
        self._acc_high: Optional[float] = None
        self._acc_low: Optional[float] = None

        # Frozen Asia range (captured when Acc → Manip transition fires)
        self._asia_hi: Optional[float] = None
        self._asia_lo: Optional[float] = None
        self._asia_eq: Optional[float] = None

        # Judas state
        self._swept_lo: bool = False
        self._swept_hi: bool = False
        self._judas_bull: bool = False
        self._judas_bear: bool = False

        # Phase FSM
        self._prev_phase: PO3Phase = PO3Phase.BETWEEN

    # ──────────────────────────────────────────────────────────────────
    # External setters (call from HTF data fetch, not bar-by-bar)
    # ──────────────────────────────────────────────────────────────────

    def set_prev_day(self, high: float, low: float, open_: float, close: float) -> None:
        """Set yesterday's OHLC for premium/discount scoring."""
        self._pd_high = high
        self._pd_low = low
        self._pd_open = open_
        self._pd_close = close

    def set_weekly_open(self, price: float, week_of_year: int) -> None:
        """Set weekly open if it changed (call on new-week detection)."""
        if week_of_year != self._weekly_woy:
            self._weekly_open = price
            self._weekly_woy = week_of_year

    # ──────────────────────────────────────────────────────────────────
    # Main update loop
    # ──────────────────────────────────────────────────────────────────

    def update_bar(
        self,
        bar_time_utc: datetime,
        open_: float,
        high: float,
        low: float,
        close: float,
    ) -> PO3BiasState:
        """Process one OHLCV bar and return the updated bias state."""
        et = _to_et(bar_time_utc)
        et_hour = et.hour
        et_dom = et.day
        et_woy = et.isocalendar().week

        phase = _phase_from_hour(et_hour)
        phase_changed = phase != self._prev_phase

        # ── Midnight Open ─────────────────────────────────────────────
        if et_hour == 0 and et_dom != self._midnight_dom:
            self._midnight_open = open_
            self._midnight_dom = et_dom
            self._reset_intraday_judas()

        # ── Weekly Open ───────────────────────────────────────────────
        if et_woy != self._weekly_woy:
            self._weekly_open = open_
            self._weekly_woy = et_woy

        # ── Accumulation ──────────────────────────────────────────────
        if phase == PO3Phase.ACCUMULATION:
            if phase_changed:
                self._acc_high = high
                self._acc_low = low
                self._reset_intraday_judas()
            else:
                self._acc_high = max(self._acc_high or high, high)
                self._acc_low = min(self._acc_low or low, low)

        # ── Freeze Asia range on Acc → Manip ──────────────────────────
        if self._prev_phase == PO3Phase.ACCUMULATION and phase == PO3Phase.MANIPULATION:
            if self._acc_high is not None and self._acc_low is not None:
                self._asia_hi = self._acc_high
                self._asia_lo = self._acc_low
                self._asia_eq = (self._acc_high + self._acc_low) / 2.0

        # ── Manipulation: sweep detection + Judas confirmation ─────────
        if phase == PO3Phase.MANIPULATION and self._asia_hi is not None:
            if not self._swept_hi and high > self._asia_hi:
                self._swept_hi = True
            if not self._swept_lo and low < self._asia_lo:
                self._swept_lo = True

            if self._asia_eq is not None:
                if self._swept_lo and not self._judas_bull and close > self._asia_eq:
                    self._judas_bull = True
                if self._swept_hi and not self._judas_bear and close < self._asia_eq:
                    self._judas_bear = True

        self._prev_phase = phase
        return self._score(close, phase)

    # ──────────────────────────────────────────────────────────────────
    # Scoring
    # ──────────────────────────────────────────────────────────────────

    def _score(self, close: float, phase: PO3Phase) -> PO3BiasState:
        """Compute 0-6 bias score and final direction from current state."""
        bull = 0
        bear = 0

        # 1. vs Midnight Open  (+1)
        above_mo: Optional[bool] = None
        if self._midnight_open is not None:
            above_mo = close >= self._midnight_open
            bull += int(above_mo)
            bear += int(not above_mo)

        # 2. vs Weekly Open  (+1)
        above_wo: Optional[bool] = None
        if self._weekly_open is not None:
            above_wo = close >= self._weekly_open
            bull += int(above_wo)
            bear += int(not above_wo)

        # 3. Premium / Discount vs Previous Day EQ  (+1)
        in_discount: Optional[bool] = None
        pd_eq: Optional[float] = None
        if self._pd_high is not None and self._pd_low is not None:
            pd_eq = (self._pd_high + self._pd_low) / 2.0
            in_discount = close <= pd_eq
            bull += int(in_discount)       # discount zone = bullish opportunity
            bear += int(not in_discount)   # premium zone  = bearish opportunity

        # 4. Previous day candle direction  (+1)
        if self._pd_open is not None and self._pd_close is not None:
            if self._pd_close > self._pd_open:
                bull += 1
            else:
                bear += 1

        # 5. Judas Swing — double weight  (+2)
        if self._judas_bull:
            bull += 2
        elif self._judas_bear:
            bear += 2

        bull = min(bull, 6)
        bear = min(bear, 6)

        # Direction
        if bull > bear:
            direction = BiasDirection.STRONG_BULL if bull >= 5 else BiasDirection.BULL
        elif bear > bull:
            direction = BiasDirection.STRONG_BEAR if bear >= 5 else BiasDirection.BEAR
        else:
            direction = BiasDirection.NEUTRAL

        # Judas status
        if self._judas_bull:
            judas = JudasStatus.BULL_CONFIRMED
        elif self._judas_bear:
            judas = JudasStatus.BEAR_CONFIRMED
        elif self._swept_lo:
            judas = JudasStatus.SWEPT_LO
        elif self._swept_hi:
            judas = JudasStatus.SWEPT_HI
        else:
            judas = JudasStatus.NONE

        return PO3BiasState(
            bull_pts=bull,
            bear_pts=bear,
            direction=direction,
            phase=phase,
            above_midnight_open=above_mo,
            above_weekly_open=above_wo,
            in_discount=in_discount,
            judas_status=judas,
            midnight_open=self._midnight_open,
            weekly_open=self._weekly_open,
            asia_high=self._asia_hi,
            asia_low=self._asia_lo,
            asia_eq=self._asia_eq,
            pd_high=self._pd_high,
            pd_low=self._pd_low,
            pd_eq=pd_eq,
            current_close=close,
            timestamp=datetime.now(tz=timezone.utc),
        )

    def _reset_intraday_judas(self) -> None:
        self._swept_lo = False
        self._swept_hi = False
        self._judas_bull = False
        self._judas_bear = False


# ──────────────────────────────────────────────────────────────────────────────
# Convenience function — score from a static snapshot (e.g., TV webhook payload)
# ──────────────────────────────────────────────────────────────────────────────

def score_from_snapshot(
    close: float,
    midnight_open: Optional[float],
    weekly_open: Optional[float],
    pd_high: Optional[float],
    pd_low: Optional[float],
    pd_open: Optional[float],
    pd_close: Optional[float],
    judas_bull: bool = False,
    judas_bear: bool = False,
    swept_lo: bool = False,
    swept_hi: bool = False,
    asia_hi: Optional[float] = None,
    asia_lo: Optional[float] = None,
    phase: PO3Phase = PO3Phase.BETWEEN,
) -> PO3BiasState:
    """Score bias from a static data snapshot without a live feed.

    Used when Pine Script sends a webhook with all the current values baked in.
    """
    d = PO3BiasDetector()
    if pd_high and pd_low and pd_open and pd_close:
        d.set_prev_day(pd_high, pd_low, pd_open, pd_close)
    d._midnight_open = midnight_open
    d._midnight_dom = 0  # bypass dom check
    d._weekly_open = weekly_open
    d._weekly_woy = 0
    d._asia_hi = asia_hi
    d._asia_lo = asia_lo
    d._asia_eq = (asia_hi + asia_lo) / 2.0 if asia_hi and asia_lo else None
    d._swept_lo = swept_lo
    d._swept_hi = swept_hi
    d._judas_bull = judas_bull
    d._judas_bear = judas_bear
    return d._score(close, phase)
