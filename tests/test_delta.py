"""Test suite for all 11 delta/CVD signal variants (DELT-01..11).

Covers:
  - DELT-01: Rise/Drop — positive/negative delta
  - DELT-02: Tail — |delta|/total_vol >= 0.95
  - DELT-03: Reversal — delta sign opposes bar direction
  - DELT-04: Divergence — price new high/low but CVD fails
  - DELT-05: Flip — CVD crosses zero
  - DELT-06: Trap — strong prior delta then price reverses
  - DELT-07: Sweep — many levels with volume acceleration
  - DELT-08: Slingshot — compressed then explosive delta
  - DELT-09: At Min/Max — CVD at session extreme
  - DELT-10: CVD Multi-Bar Divergence — regression slope divergence
  - DELT-11: Velocity — large CVD acceleration
  - Engine reset clears histories and session extremes
  - Config override behavior
"""
from collections import defaultdict

import pytest

from deep6.engines.delta import DeltaEngine, DeltaType, DeltaSignal
from deep6.engines.signal_config import DeltaConfig
from deep6.state.footprint import FootprintBar, FootprintLevel, price_to_tick, tick_to_price


# ---------------------------------------------------------------------------
# Helper: build a FootprintBar with explicit delta and volume
# ---------------------------------------------------------------------------

def make_bar(
    delta: int = 0,
    total_vol: int = 100,
    open_px: float = 21000.0,
    close: float = 21000.0,
    cvd: float = 0.0,
    levels: dict | None = None,
    max_delta: int | None = None,
    min_delta: int | None = None,
) -> FootprintBar:
    """Build a FootprintBar with specified delta and volume.

    For most delta tests, we only care about bar_delta, total_vol, open, close, and cvd.
    When levels is provided (dict of {price: (bid_vol, ask_vol)}), levels are built explicitly.
    Otherwise, a minimal two-level bar is synthesized to match the requested delta/vol.

    Plan 12-02: intrabar extremes (max_delta / min_delta) default to the closing-at-extreme
    case (max_delta=delta if delta>0 else 0; min_delta=delta if delta<0 else 0). Callers
    that want the peaked-and-faded variant pass max_delta / min_delta explicitly.
    running_delta is set equal to bar_delta (post-finalize invariant).
    """
    bar = FootprintBar()
    bar.open = open_px
    bar.close = close
    bar.bar_delta = delta
    bar.total_vol = total_vol
    bar.cvd = cvd
    bar.running_delta = delta
    bar.max_delta = max_delta if max_delta is not None else max(delta, 0)
    bar.min_delta = min_delta if min_delta is not None else min(delta, 0)

    if levels is not None:
        prices = sorted(levels.keys())
        for price, (bid, ask) in levels.items():
            tick = price_to_tick(price)
            bar.levels[tick] = FootprintLevel(bid_vol=bid, ask_vol=ask)
        if prices:
            bar.high = max(prices)
            bar.low = min(prices)
            bar.bar_range = bar.high - bar.low
    else:
        # Synthesize minimal two adjacent levels to satisfy delta/vol constraints
        # ask_vol - bid_vol = delta; ask_vol + bid_vol = total_vol
        ask_vol = (total_vol + delta) // 2
        bid_vol = (total_vol - delta) // 2
        if ask_vol < 0 or bid_vol < 0:
            ask_vol = max(0, ask_vol)
            bid_vol = max(0, bid_vol)
        bar.levels[price_to_tick(21000.00)] = FootprintLevel(bid_vol=bid_vol, ask_vol=ask_vol)
        bar.levels[price_to_tick(21000.25)] = FootprintLevel(bid_vol=1, ask_vol=1)
        bar.high = 21000.25
        bar.low = 21000.0
        bar.bar_range = 0.25

    return bar


def feed_bars(engine: DeltaEngine, bars: list) -> list:
    """Feed a list of bars to engine and return signals from last bar."""
    result = []
    for bar in bars:
        result = engine.process(bar)
    return result


# ---------------------------------------------------------------------------
# Edge case: empty bar
# ---------------------------------------------------------------------------

def test_empty_bar_returns_no_signals():
    """Bar with total_vol == 0 returns empty signal list."""
    engine = DeltaEngine()
    bar = FootprintBar()  # total_vol = 0 by default
    result = engine.process(bar)
    assert result == []


# ---------------------------------------------------------------------------
# DELT-01: Rise and Drop
# ---------------------------------------------------------------------------

def test_rise_signal():
    """DELT-01: Positive delta fires RISE signal."""
    engine = DeltaEngine()
    bar = make_bar(delta=50, total_vol=100)
    signals = engine.process(bar)
    rises = [s for s in signals if s.delta_type == DeltaType.RISE]
    assert len(rises) >= 1
    assert rises[0].direction == +1
    assert rises[0].value == 50


def test_drop_signal():
    """DELT-01: Negative delta fires DROP signal."""
    engine = DeltaEngine()
    bar = make_bar(delta=-50, total_vol=100)
    signals = engine.process(bar)
    drops = [s for s in signals if s.delta_type == DeltaType.DROP]
    assert len(drops) >= 1
    assert drops[0].direction == -1
    assert drops[0].value == -50


def test_zero_delta_no_rise_drop():
    """DELT-01: Zero delta does not fire RISE or DROP."""
    engine = DeltaEngine()
    bar = make_bar(delta=0, total_vol=100)
    signals = engine.process(bar)
    rise_drops = [s for s in signals if s.delta_type in (DeltaType.RISE, DeltaType.DROP)]
    assert len(rise_drops) == 0


# ---------------------------------------------------------------------------
# DELT-02: Tail
# ---------------------------------------------------------------------------

def test_tail_signal_closing_at_extreme():
    """DELT-02 (Plan 12-02 fix): bar_delta == max_delta → ratio 1.0 >= 0.95 → TAIL fires.

    Previous impl used |delta|/total_vol (bar-geometry proxy). Now uses the TRUE
    intrabar extreme: ratio = bar_delta / max_delta (positive) or bar_delta / min_delta (negative).
    """
    engine = DeltaEngine()
    bar = make_bar(delta=96, total_vol=100, max_delta=96)
    signals = engine.process(bar)
    tails = [s for s in signals if s.delta_type == DeltaType.TAIL]
    assert len(tails) >= 1
    assert tails[0].direction == +1


def test_tail_not_fired_when_peaked_and_faded():
    """DELT-02 (Plan 12-02 fix): bar_delta = 0.5 * max_delta → ratio 0.5 < 0.95 → no TAIL.

    Intrabar peaked at +100 then faded to +50 at close — NOT closing-at-extreme.
    Old proxy (|delta|/total_vol = 0.5) also would not fire, but for the wrong reason.
    """
    engine = DeltaEngine()
    bar = make_bar(delta=50, total_vol=200, max_delta=100)
    signals = engine.process(bar)
    tails = [s for s in signals if s.delta_type == DeltaType.TAIL]
    assert len(tails) == 0


def test_negative_tail_signal_closing_at_min():
    """DELT-02 (Plan 12-02 fix): bar_delta == min_delta → TAIL direction=-1."""
    engine = DeltaEngine()
    bar = make_bar(delta=-96, total_vol=100, min_delta=-96)
    signals = engine.process(bar)
    tails = [s for s in signals if s.delta_type == DeltaType.TAIL]
    assert len(tails) >= 1
    assert tails[0].direction == -1


def test_tail_ratio_trivial_fallback_when_max_delta_zero():
    """FOOTGUN 3 guard: if max_delta==0 and bar_delta>0, treat max_delta=bar_delta.

    Prevents division-by-zero and gives conservative closing-at-trivial-extreme.
    make_bar() defaults max_delta=delta for delta>0, so this explicitly zeroes it.
    """
    engine = DeltaEngine()
    bar = make_bar(delta=50, total_vol=100, max_delta=0)
    signals = engine.process(bar)
    tails = [s for s in signals if s.delta_type == DeltaType.TAIL]
    # bar_delta == effective max_delta → ratio 1.0 → TAIL fires
    assert len(tails) >= 1


# --- Plan 12-02: delta_quality on DeltaResult/DeltaSignal emission ---

def test_delta_quality_closing_at_extreme():
    """DeltaResult carries delta_quality=1.15 when bar closes at max_delta (strong conviction)."""
    engine = DeltaEngine()
    bar = make_bar(delta=80, total_vol=100, max_delta=80)
    result = engine.process_with_quality(bar)
    assert result.delta_quality == pytest.approx(1.15)


def test_delta_quality_peaked_and_faded():
    """DeltaResult carries delta_quality=0.7 when bar peaked and faded."""
    engine = DeltaEngine()
    # max_delta=100, bar_delta=20 → ratio 0.2 < 0.35 → 0.7
    bar = make_bar(delta=20, total_vol=200, max_delta=100)
    result = engine.process_with_quality(bar)
    assert result.delta_quality == pytest.approx(0.7)


def test_delta_family_bits_whitelist_contains_only_delta_bits():
    """DELTA_FAMILY_BITS is the whitelist of bits that may consume delta_quality.

    Must cover bits 21-32 (DELT-01..DELT-11 + CVD velocity). Must NOT include
    absorption (0-3), exhaustion (4-11), or any other bit — scalar is orthogonal.
    """
    from deep6.engines.delta import DELTA_FAMILY_BITS
    # All 12 delta-family bits present (bit 22 = DELT_TAIL).
    expected = {21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32}
    assert DELTA_FAMILY_BITS == expected


# ---------------------------------------------------------------------------
# DELT-03: Reversal (bar-level approximation)
# ---------------------------------------------------------------------------

def test_reversal_signal_bearish():
    """DELT-03: Up bar (close > open) with negative delta fires REVERSAL direction=-1."""
    engine = DeltaEngine()
    # Bar goes up but strong selling delta (> 15% of vol by default threshold)
    bar = make_bar(delta=-30, total_vol=100, open_px=21000.0, close=21001.0)
    signals = engine.process(bar)
    reversals = [s for s in signals if s.delta_type == DeltaType.REVERSAL]
    assert len(reversals) >= 1
    assert reversals[0].direction == -1


def test_reversal_signal_bullish():
    """DELT-03: Down bar (close < open) with positive delta fires REVERSAL direction=+1."""
    engine = DeltaEngine()
    bar = make_bar(delta=30, total_vol=100, open_px=21001.0, close=21000.0)
    signals = engine.process(bar)
    reversals = [s for s in signals if s.delta_type == DeltaType.REVERSAL]
    assert len(reversals) >= 1
    assert reversals[0].direction == +1


# ---------------------------------------------------------------------------
# DELT-04: Divergence
# ---------------------------------------------------------------------------

def test_divergence_bearish():
    """DELT-04: Price at 5-bar high but CVD not at high fires DIVERGENCE direction=-1.

    Strategy: Feed 4 bars where CVD peaks then falls; current bar has price at new high
    but CVD is below that peak — the classic bearish divergence pattern.
    """
    config = DeltaConfig(divergence_lookback=5)
    engine = DeltaEngine(config)

    # Feed 4 bars: prices rising, CVD rises to 50 then falls back to 20
    # Bar 1: price 21000, CVD 10
    # Bar 2: price 21001, CVD 50   <- CVD peak
    # Bar 3: price 21002, CVD 30
    # Bar 4: price 21003, CVD 20
    prior_data = [
        (21000.0, 10.0),
        (21001.0, 50.0),
        (21002.0, 30.0),
        (21003.0, 20.0),
    ]
    for price, cvd in prior_data:
        bar = make_bar(delta=10, total_vol=100, close=price, cvd=cvd)
        engine.process(bar)

    # 5th bar: price at new 5-bar high (21005), but CVD = 25 < max(10,50,30,20,25) = 50
    current = make_bar(delta=-5, total_vol=100, close=21005.0, cvd=25.0)
    signals = engine.process(current)
    divergences = [s for s in signals if s.delta_type == DeltaType.DIVERGENCE]
    bearish_div = [d for d in divergences if d.direction == -1]
    assert len(bearish_div) >= 1


def test_divergence_bullish():
    """DELT-04: Price at 5-bar low but CVD not at low fires DIVERGENCE direction=+1."""
    config = DeltaConfig(divergence_lookback=5)
    engine = DeltaEngine(config)

    # Feed 4 bars: prices falling, CVD falling then recovering
    prior_prices = [21005.0, 21004.0, 21003.0, 21002.0]
    prior_cvds = [-10.0, -20.0, -30.0, -20.0]
    for price, cvd in zip(prior_prices, prior_cvds):
        bar = make_bar(delta=-5, total_vol=100, close=price, cvd=cvd)
        engine.process(bar)

    # 5th bar: price at 5-bar low (21001.0), CVD NOT at new low (-15 > -30)
    current = make_bar(delta=5, total_vol=100, close=21001.0, cvd=-15.0)
    signals = engine.process(current)
    divergences = [s for s in signals if s.delta_type == DeltaType.DIVERGENCE]
    bullish_div = [d for d in divergences if d.direction == +1]
    assert len(bullish_div) >= 1


# ---------------------------------------------------------------------------
# DELT-05: Flip (CVD crosses zero)
# ---------------------------------------------------------------------------

def test_flip_to_negative():
    """DELT-05: CVD crosses zero downward fires FLIP direction=-1."""
    engine = DeltaEngine()
    # First bar: CVD = +50 (positive)
    bar1 = make_bar(delta=50, total_vol=100, cvd=50.0)
    engine.process(bar1)
    # Second bar: CVD = -10 (crossed below zero)
    bar2 = make_bar(delta=-60, total_vol=100, cvd=-10.0)
    signals = engine.process(bar2)
    flips = [s for s in signals if s.delta_type == DeltaType.FLIP]
    assert len(flips) >= 1
    assert flips[0].direction == -1


def test_flip_to_positive():
    """DELT-05: CVD crosses zero upward fires FLIP direction=+1."""
    engine = DeltaEngine()
    # First bar: CVD = -50 (negative)
    bar1 = make_bar(delta=-50, total_vol=100, cvd=-50.0)
    engine.process(bar1)
    # Second bar: CVD = +10 (crossed above zero)
    bar2 = make_bar(delta=60, total_vol=100, cvd=10.0)
    signals = engine.process(bar2)
    flips = [s for s in signals if s.delta_type == DeltaType.FLIP]
    assert len(flips) >= 1
    assert flips[0].direction == +1


# ---------------------------------------------------------------------------
# DELT-06: Trap
# ---------------------------------------------------------------------------

def test_trap_bullish():
    """DELT-06: Strong buying delta then price drops fires TRAP direction=-1.

    Prior bar: delta = 50, total_vol=100 -> 50% buying (> 30% trap_delta_ratio)
    Current bar: close < open (price dropped despite prior buying)
    """
    engine = DeltaEngine()
    # Bar 1: strong positive delta
    bar1 = make_bar(delta=50, total_vol=100, open_px=21000.0, close=21001.0)
    engine.process(bar1)
    # Bar 2: price drops (close < open) -> trap
    bar2 = make_bar(delta=-10, total_vol=100, open_px=21001.0, close=21000.0)
    signals = engine.process(bar2)
    traps = [s for s in signals if s.delta_type == DeltaType.TRAP]
    assert len(traps) >= 1
    # Trap is bearish (prior buyers got trapped)
    bear_traps = [t for t in traps if t.direction == -1]
    assert len(bear_traps) >= 1


def test_trap_bearish():
    """DELT-06: Strong selling delta then price rises fires TRAP direction=+1."""
    engine = DeltaEngine()
    # Bar 1: strong negative delta
    bar1 = make_bar(delta=-50, total_vol=100, open_px=21001.0, close=21000.0)
    engine.process(bar1)
    # Bar 2: price rises (close > open) -> bull trap
    bar2 = make_bar(delta=10, total_vol=100, open_px=21000.0, close=21001.0)
    signals = engine.process(bar2)
    traps = [s for s in signals if s.delta_type == DeltaType.TRAP]
    bull_traps = [t for t in traps if t.direction == +1]
    assert len(bull_traps) >= 1


# ---------------------------------------------------------------------------
# DELT-07: Sweep
# ---------------------------------------------------------------------------

def test_sweep_signal():
    """DELT-07: Many levels with accelerating volume (second half > 1.5x first half) fires SWEEP."""
    engine = DeltaEngine()
    # Build bar with 10 levels where second half has much more volume than first half
    levels = {}
    # First 5 levels (lower prices): low volume
    for i in range(5):
        price = 21000.0 + i * 0.25
        levels[price] = (5, 5)  # 10 vol per level, 50 total in first half
    # Second 5 levels (upper prices): high volume
    for i in range(5, 10):
        price = 21000.0 + i * 0.25
        levels[price] = (15, 15)  # 30 vol per level, 150 total in second half
    # 150 / 50 = 3.0 > sweep_vol_increase_ratio=1.5 -> SWEEP fires

    bar = make_bar(
        delta=50,
        total_vol=200,
        open_px=21000.0,
        close=21002.25,  # up bar -> direction +1
        levels=levels,
    )
    # Fix OHLC from levels
    bar.open = 21000.0
    bar.close = 21002.25
    bar.high = max(levels.keys())
    bar.low = min(levels.keys())
    signals = engine.process(bar)
    sweeps = [s for s in signals if s.delta_type == DeltaType.SWEEP]
    assert len(sweeps) >= 1


# ---------------------------------------------------------------------------
# DELT-08: Slingshot
# ---------------------------------------------------------------------------

def test_slingshot_signal():
    """DELT-08: 3 quiet bars then explosive delta fires SLINGSHOT.

    Quiet bars: |delta| < 10% of total_vol (< 0.1 * 100 = 10)
    Explosive bar: |delta| > 40% of total_vol (> 0.4 * 100 = 40)
    """
    engine = DeltaEngine()

    # 3 quiet bars: small delta relative to volume
    for _ in range(3):
        quiet_bar = make_bar(delta=5, total_vol=100)  # 5% < 10%
        engine.process(quiet_bar)

    # Explosive 4th bar: large delta
    explosive_bar = make_bar(delta=50, total_vol=100)  # 50% > 40%
    signals = engine.process(explosive_bar)

    slingshots = [s for s in signals if s.delta_type == DeltaType.SLINGSHOT]
    assert len(slingshots) >= 1
    assert slingshots[0].direction == +1


def test_slingshot_bearish():
    """DELT-08: Slingshot fires with negative explosive delta."""
    engine = DeltaEngine()
    for _ in range(3):
        quiet_bar = make_bar(delta=-5, total_vol=100)
        engine.process(quiet_bar)
    explosive_bar = make_bar(delta=-50, total_vol=100)
    signals = engine.process(explosive_bar)
    slingshots = [s for s in signals if s.delta_type == DeltaType.SLINGSHOT]
    assert len(slingshots) >= 1
    assert slingshots[0].direction == -1


# ---------------------------------------------------------------------------
# DELT-09: At Min/Max
# ---------------------------------------------------------------------------

def test_at_max():
    """DELT-09: CVD at session maximum fires AT_MAX."""
    engine = DeltaEngine()
    # Establish a range: first go up to 100, then down to -50
    engine.process(make_bar(delta=50, total_vol=100, cvd=50.0))
    engine.process(make_bar(delta=50, total_vol=100, cvd=100.0))
    engine.process(make_bar(delta=-30, total_vol=100, cvd=70.0))
    # session_cvd_max = 100.0, session_cvd_min = 0.0
    # New bar at CVD 100.0 should fire AT_MAX
    bar = make_bar(delta=30, total_vol=100, cvd=100.0)
    signals = engine.process(bar)
    at_max = [s for s in signals if s.delta_type == DeltaType.AT_MAX]
    assert len(at_max) >= 1


def test_at_min():
    """DELT-09: CVD at session minimum fires AT_MIN."""
    engine = DeltaEngine()
    engine.process(make_bar(delta=-50, total_vol=100, cvd=-50.0))
    engine.process(make_bar(delta=-50, total_vol=100, cvd=-100.0))
    engine.process(make_bar(delta=30, total_vol=100, cvd=-70.0))
    # session_cvd_min = -100.0
    bar = make_bar(delta=-30, total_vol=100, cvd=-100.0)
    signals = engine.process(bar)
    at_min = [s for s in signals if s.delta_type == DeltaType.AT_MIN]
    assert len(at_min) >= 1


# ---------------------------------------------------------------------------
# DELT-10: CVD Multi-Bar Divergence
# ---------------------------------------------------------------------------

def test_cvd_multi_bar_divergence_bearish():
    """DELT-10: 10+ bars with rising price but declining CVD fires CVD_DIVERGENCE direction=-1."""
    config = DeltaConfig(cvd_divergence_min_bars=10, cvd_slope_divergence_factor=0.1)
    engine = DeltaEngine(config)

    # Feed 10 bars: price rises steadily, CVD falls steadily
    for i in range(10):
        bar = make_bar(
            delta=-10, total_vol=100,
            close=21000.0 + i * 1.0,    # rising price
            cvd=float(100 - i * 20),    # declining CVD: 100, 80, 60, ..., -80
        )
        engine.process(bar)

    # Check last signal from the last bar
    bar = make_bar(
        delta=-10, total_vol=100,
        close=21010.0,
        cvd=-100.0,
    )
    signals = engine.process(bar)
    cvd_div = [s for s in signals if s.delta_type == DeltaType.CVD_DIVERGENCE]
    bearish_div = [d for d in cvd_div if d.direction == -1]
    assert len(bearish_div) >= 1


def test_cvd_multi_bar_divergence_bullish():
    """DELT-10: 10+ bars with falling price but rising CVD fires CVD_DIVERGENCE direction=+1."""
    config = DeltaConfig(cvd_divergence_min_bars=10, cvd_slope_divergence_factor=0.1)
    engine = DeltaEngine(config)

    for i in range(10):
        bar = make_bar(
            delta=10, total_vol=100,
            close=21010.0 - i * 1.0,   # falling price
            cvd=float(-100 + i * 20),  # rising CVD: -100, -80, ..., 80
        )
        engine.process(bar)

    bar = make_bar(
        delta=10, total_vol=100,
        close=21000.0,
        cvd=100.0,
    )
    signals = engine.process(bar)
    cvd_div = [s for s in signals if s.delta_type == DeltaType.CVD_DIVERGENCE]
    bullish_div = [d for d in cvd_div if d.direction == +1]
    assert len(bullish_div) >= 1


# ---------------------------------------------------------------------------
# DELT-11: Velocity
# ---------------------------------------------------------------------------

def test_velocity_signal():
    """DELT-11: Large CVD acceleration fires VELOCITY.

    velocity = cvd[-1] - cvd[-2]
    accel = velocity - (cvd[-2] - cvd[-3])
    accel must be > total_vol * velocity_accel_ratio (default 0.3)
    """
    config = DeltaConfig(velocity_accel_ratio=0.3)
    engine = DeltaEngine(config)

    # Bar 1: CVD = 0
    engine.process(make_bar(delta=0, total_vol=100, cvd=0.0))
    # Bar 2: CVD = 10 (velocity = 10)
    engine.process(make_bar(delta=10, total_vol=100, cvd=10.0))
    # Bar 3: CVD = 60 (velocity = 50, accel = 50 - 10 = 40 > 100 * 0.3 = 30)
    signals = engine.process(make_bar(delta=50, total_vol=100, cvd=60.0))
    velocity_sigs = [s for s in signals if s.delta_type == DeltaType.VELOCITY]
    assert len(velocity_sigs) >= 1


# ---------------------------------------------------------------------------
# Engine reset
# ---------------------------------------------------------------------------

def test_engine_reset():
    """reset() clears histories and session extremes."""
    engine = DeltaEngine()
    engine.process(make_bar(delta=50, total_vol=100, cvd=50.0))
    engine.process(make_bar(delta=-80, total_vol=100, cvd=-30.0))

    assert engine.bar_count == 2
    assert len(engine.cvd_history) == 2
    assert engine.session_cvd_max == 50.0
    assert engine.session_cvd_min == -30.0

    engine.reset()

    assert engine.bar_count == 0
    assert len(engine.cvd_history) == 0
    assert len(engine.price_history) == 0
    assert len(engine.delta_history) == 0
    assert engine.session_cvd_min == 0.0
    assert engine.session_cvd_max == 0.0


# ---------------------------------------------------------------------------
# Config override tests
# ---------------------------------------------------------------------------

def test_config_tail_threshold_override():
    """DeltaConfig(tail_threshold=0.99) suppresses 0.96 tails (default fires at 0.95).

    Plan 12-02: ratio is now bar_delta / max_delta (true intrabar extreme).
    bar_delta=96, max_delta=100 → ratio 0.96 fires at default 0.95 but not at 0.99.
    """
    # Default: 0.96 >= 0.95 -> TAIL fires
    engine_default = DeltaEngine()
    bar = make_bar(delta=96, total_vol=100, max_delta=100)
    sigs_default = engine_default.process(bar)
    tails_default = [s for s in sigs_default if s.delta_type == DeltaType.TAIL]
    assert len(tails_default) >= 1

    # Strict config: 0.96 < 0.99 -> TAIL suppressed
    engine_strict = DeltaEngine(DeltaConfig(tail_threshold=0.99))
    sigs_strict = engine_strict.process(bar)
    tails_strict = [s for s in sigs_strict if s.delta_type == DeltaType.TAIL]
    assert len(tails_strict) == 0


def test_config_velocity_ratio_override():
    """DeltaConfig with higher velocity_accel_ratio suppresses marginal velocity signals."""
    # accel = 40, total_vol = 100: ratio = 0.4 -> fires at default (0.3) but not at 0.5
    engine_default = DeltaEngine(DeltaConfig(velocity_accel_ratio=0.3))
    engine_strict = DeltaEngine(DeltaConfig(velocity_accel_ratio=0.5))

    for engine in [engine_default, engine_strict]:
        engine.process(make_bar(delta=0, total_vol=100, cvd=0.0))
        engine.process(make_bar(delta=10, total_vol=100, cvd=10.0))

    sigs_default = engine_default.process(make_bar(delta=50, total_vol=100, cvd=60.0))
    vel_default = [s for s in sigs_default if s.delta_type == DeltaType.VELOCITY]
    assert len(vel_default) >= 1  # 40/100 = 0.4 > 0.3

    sigs_strict = engine_strict.process(make_bar(delta=50, total_vol=100, cvd=60.0))
    vel_strict = [s for s in sigs_strict if s.delta_type == DeltaType.VELOCITY]
    assert len(vel_strict) == 0  # 40/100 = 0.4 < 0.5
