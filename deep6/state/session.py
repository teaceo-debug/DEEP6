"""SessionContext: VWAP, CVD, and IB accumulators for one RTH session.

Persisted to SQLite (Plan 03) and restored on restart (D-07, D-15).
State resets at 9:30 ET each day (D-07).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionContext:
    """Accumulated session state. All fields reset at session open (D-07).

    Serialisable via to_dict() / from_dict() for SQLite persistence (Plan 03).
    """

    # CVD tracking — updated from each closed FootprintBar
    cvd: int = 0

    # VWAP accumulation
    # vwap = vwap_numerator / vwap_denominator
    # numerator  = sum(close_price * bar_volume)
    # denominator = sum(bar_volume)
    vwap_numerator: float = 0.0
    vwap_denominator: float = 0.0

    # Initial Balance (first 60 minutes of RTH: 9:30-10:30 ET)
    ib_high: float = 0.0
    ib_low: float = float('inf')
    ib_complete: bool = False  # True after 10:30 ET (1 full IB hour elapsed)

    # Opening range (first bar of RTH — 9:30-9:31 ET for 1-min bars)
    opening_range_high: float = 0.0
    opening_range_low: float = float('inf')

    # Session day type — set by SessionManager once IB is known
    # Values: "trend", "normal", "neutral", "unknown"
    day_type: str = "unknown"

    @property
    def vwap(self) -> float:
        """Current session VWAP. Returns 0.0 before any trades."""
        if self.vwap_denominator == 0:
            return 0.0
        return self.vwap_numerator / self.vwap_denominator

    def update(self, bar: "FootprintBar") -> None:  # noqa: F821 (forward ref)
        """Update session accumulators from a closed FootprintBar.

        Called by BarBuilder after each bar close.
        """
        self.cvd = bar.cvd
        if bar.total_vol > 0 and bar.close > 0:
            # VWAP: weight close price by bar volume (bar-close approximation)
            self.vwap_numerator += bar.close * bar.total_vol
            self.vwap_denominator += bar.total_vol

    def reset(self) -> None:
        """Reset all session accumulators at session open (D-07).

        Called at 9:30 ET each day by SessionManager.
        """
        self.cvd = 0
        self.vwap_numerator = 0.0
        self.vwap_denominator = 0.0
        self.ib_high = 0.0
        self.ib_low = float('inf')
        self.ib_complete = False
        self.opening_range_high = 0.0
        self.opening_range_low = float('inf')
        self.day_type = "unknown"

    def to_dict(self) -> dict:
        """Serialise to key-value dict for SQLite persistence (Plan 03).

        All values are strings — SQLite stores TEXT; from_dict() casts on read.
        """
        return {
            "cvd": str(self.cvd),
            "vwap_numerator": str(self.vwap_numerator),
            "vwap_denominator": str(self.vwap_denominator),
            "ib_high": str(self.ib_high),
            "ib_low": str(self.ib_low),
            "ib_complete": str(self.ib_complete),
            "opening_range_high": str(self.opening_range_high),
            "opening_range_low": str(self.opening_range_low),
            "day_type": self.day_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SessionContext":
        """Restore from SQLite key-value dict (Plan 03).

        Missing keys fall back to field defaults — safe for partial restores.
        """
        ctx = cls()
        ctx.cvd = int(d.get("cvd", "0"))
        ctx.vwap_numerator = float(d.get("vwap_numerator", "0.0"))
        ctx.vwap_denominator = float(d.get("vwap_denominator", "0.0"))
        ctx.ib_high = float(d.get("ib_high", "0.0"))
        ctx.ib_low = float(d.get("ib_low", str(float('inf'))))
        ctx.ib_complete = d.get("ib_complete", "False") == "True"
        ctx.opening_range_high = float(d.get("opening_range_high", "0.0"))
        ctx.opening_range_low = float(d.get("opening_range_low", str(float('inf'))))
        ctx.day_type = d.get("day_type", "unknown")
        return ctx
