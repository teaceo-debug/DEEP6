"""ATRTracker: incremental Wilder's ATR(20) — no pandas, no history buffer.

Per ARCH-03: provides volatility-adaptive threshold baseline for all 44 signals.
Not used by signals directly in Phase 1 — scaffolded here, consumed in Phase 2+.
"""


class ATRTracker:
    """Wilder's ATR(N) computed incrementally.

    Phase 1: scaffolded but not invoked by signal engines.
    Phase 2+: all 44 signals use atr_tracker.atr as volatility-adaptive baseline.

    Seeding: first N bars use simple average of true ranges to initialize ATR.
    After N bars: Wilder's exponential smoothing: ATR = prev * (N-1)/N + TR * (1/N)
    """

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self.alpha = 1.0 / period
        self._atr: float = 0.0
        self._initialized: bool = False
        self._bar_count: int = 0
        self._prev_close: float = 0.0
        self._seed_trs: list[float] = []  # collect first N for simple average seed

    def update(self, high: float, low: float, close: float) -> None:
        """Update ATR with one new bar's OHLC.

        True Range = max(high-low, |high-prev_close|, |low-prev_close|)
        First bar (no prev_close): TR = high - low only.
        """
        tr = high - low
        if self._prev_close > 0:
            tr = max(tr, abs(high - self._prev_close), abs(low - self._prev_close))
        self._prev_close = close
        self._bar_count += 1

        if not self._initialized:
            self._seed_trs.append(tr)
            if self._bar_count >= self.period:
                # Seed with simple average of first N true ranges (Wilder's convention)
                self._atr = sum(self._seed_trs) / self.period
                self._initialized = True
        else:
            # Wilder's exponential smoothing (equivalent to EMA with alpha=1/N)
            self._atr = self._atr * (1.0 - self.alpha) + tr * self.alpha

    @property
    def ready(self) -> bool:
        """True once N bars have been seen and ATR is seeded."""
        return self._initialized

    @property
    def atr(self) -> float:
        """Current ATR value. Returns 0.0 if not yet ready."""
        return self._atr if self._initialized else 0.0
