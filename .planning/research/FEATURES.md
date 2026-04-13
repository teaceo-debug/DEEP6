# Feature Landscape: DEEP6 v2.0 — Python Footprint Engine

**Domain:** Python footprint chart engine + 44-signal orderflow system (NQ futures)
**Researched:** 2026-04-11
**Milestone context:** Python rewrite — all 44 signal definitions carry forward from v1 NT8 research. This document focuses on HOW to implement them in Python from raw Rithmic L2/tick data, not whether to build them (already decided).
**Confidence:** HIGH for core footprint construction and tick classification; MEDIUM for Kronos inference pipeline; HIGH for signal detection algorithms

---

## Core Implementation: Footprint Chart Engine

The footprint engine is the foundation. Every signal in all 8 categories depends on having correct bid/ask volume per price level per bar. Getting this wrong means all 44 signals are wrong.

### Feature 1: Tick Classification (Aggressor Side Detection)

**The problem:** A trade tick from Rithmic arrives with a price and size. To build a footprint, you must know whether it was a buy aggressor (hit the ask — add to ask volume at that price) or sell aggressor (hit the bid — add to bid volume at that price).

**The solution — Rithmic provides aggressor side natively:**

The Rithmic Protocol Buffer `ResponseHistoricalLastTrade` (and the equivalent live `LAST_TRADE` message) contains an `aggressor` field of type `TransactionType { BUY = 1; SELL = 2; }`. This is the authoritative field — do NOT implement Lee-Ready or tick rule in Python. Use `data["aggressor"]` directly from async-rithmic's `DataType.LAST_TRADE` callback.

Confidence: HIGH — confirmed from Rithmic protobuf source (igorrivin/rithmic on GitHub).

**async-rithmic callback pattern:**
```python
from async_rithmic import RithmicClient, DataType, LastTradePresenceBits, TransactionType

async def on_tick(data: dict):
    if data["data_type"] == DataType.LAST_TRADE:
        if data["presence_bits"] & LastTradePresenceBits.LAST_TRADE:
            price = data["trade_price"]
            size  = data["trade_size"]
            side  = data["aggressor"]  # TransactionType.BUY or SELL
            # route to bar builder
            bar_builder.on_trade(price, size, side)
```

**Fallback (if aggressor field absent):** Compare trade price to last best bid/ask from the BBO stream. Trade at ask price → buy aggressor. Trade at bid price → sell aggressor. Trade between → use tick rule (uptick = buy, downtick = sell). This is Lee-Ready simplified, accuracy ~85% — acceptable fallback but Rithmic's native field should be preferred.

**Research finding on alternatives:** Academic research (Chakrabarty et al.) confirms bulk volume classification (BVC) outperforms Lee-Ready in electronic markets. However, since Rithmic provides the aggressor field directly, neither algorithm is needed for live data. For Databento MBO historical replay, the `side` field on trade records (F=buyer aggressor, A=seller aggressor in CME MBO data) provides equivalent direct classification.

---

### Feature 2: Footprint Bar Data Structure

**The core data structure for one bar:**

```python
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict

@dataclass
class FootprintLevel:
    bid_vol: int = 0   # sell aggressor volume at this price
    ask_vol: int = 0   # buy aggressor volume at this price

@dataclass
class FootprintBar:
    open: float = 0.0
    high: float = 0.0
    low: float = float('inf')
    close: float = 0.0
    levels: DefaultDict[int, FootprintLevel] = field(
        default_factory=lambda: defaultdict(FootprintLevel)
    )
    # Derived fields (computed on bar close)
    total_vol: int = 0
    bar_delta: int = 0      # sum(ask) - sum(bid) across all levels
    cvd: int = 0            # running cumulative delta (updated at bar close)
    poc_price: float = 0.0  # price with highest total volume
    bar_range: float = 0.0  # high - low in ticks
```

**Price key encoding:** Store price levels as integers in ticks (divide float price by tick_size, round to int). For NQ, tick_size = 0.25. This avoids floating-point key collisions in dict lookups.

```python
TICK_SIZE = 0.25

def price_to_tick(price: float) -> int:
    return round(price / TICK_SIZE)

def tick_to_price(tick: int) -> float:
    return tick * TICK_SIZE
```

**Why dict not numpy array per bar:** Dict (defaultdict) is the correct choice for the live accumulation path. The price range of a bar is unknown until it closes — a numpy array would require pre-allocation with a worst-case range or expensive resize. Dict grows naturally, lookup is O(1), and the full bar is small enough that dict overhead is negligible. Convert to numpy array ONLY after bar close for vectorized signal detection.

**Volume accumulation on each tick:**
```python
def on_trade(self, price: float, size: int, side: TransactionType):
    tick = price_to_tick(price)
    if side == TransactionType.BUY:
        self.current_bar.levels[tick].ask_vol += size
    else:
        self.current_bar.levels[tick].bid_vol += size
    self.current_bar.high = max(self.current_bar.high, price)
    self.current_bar.low  = min(self.current_bar.low,  price)
    self.current_bar.close = price
    if self.current_bar.open == 0.0:
        self.current_bar.open = price
```

**Replication of NT8's VolumetricBarsType methods:**

| NT8 Method | Python Equivalent |
|-----------|------------------|
| `GetAskVolumeForPrice(price)` | `bar.levels[price_to_tick(price)].ask_vol` |
| `GetBidVolumeForPrice(price)` | `bar.levels[price_to_tick(price)].bid_vol` |
| `GetTotalVolumeForPrice(price)` | `bar.levels[tick].ask_vol + bar.levels[tick].bid_vol` |
| `GetDeltaForPrice(price)` | `bar.levels[tick].ask_vol - bar.levels[tick].bid_vol` |
| `BarDelta` | `bar.bar_delta` (computed at bar close) |
| `TotalBuyingVolume` | `sum(lv.ask_vol for lv in bar.levels.values())` |
| `TotalSellingVolume` | `sum(lv.bid_vol for lv in bar.levels.values())` |

---

### Feature 3: Bar Builder and Bar Finalization Event

**The Python equivalent of NT8's `OnBarUpdate` on bar close:**

NT8's event model fires `OnBarUpdate` with `IsFirstTickOfBar=true` on the first tick of each new bar — that's when you process the CLOSED bar's data. Python must replicate this with a time-based bar builder that finalizes bars on a schedule.

**Bar builder architecture:**

```python
import asyncio
from datetime import datetime, timedelta

class BarBuilder:
    def __init__(self, bar_period_seconds: int, on_bar_close_callback):
        self.period = bar_period_seconds
        self.on_bar_close = on_bar_close_callback
        self.current_bar = FootprintBar()
        self.bar_open_time: datetime = None

    async def run(self):
        """Background task that fires bar-close events on schedule."""
        while True:
            now = datetime.utcnow()
            # Align to bar boundaries (e.g., every 60s on the minute)
            next_bar = self._next_bar_time(now)
            await asyncio.sleep((next_bar - now).total_seconds())
            closed_bar = self._finalize_bar()
            await self.on_bar_close(closed_bar)

    def _finalize_bar(self) -> FootprintBar:
        bar = self.current_bar
        # Compute derived fields
        bar.bar_delta = sum(
            lv.ask_vol - lv.bid_vol for lv in bar.levels.values()
        )
        bar.total_vol = sum(
            lv.ask_vol + lv.bid_vol for lv in bar.levels.values()
        )
        bar.poc_price = tick_to_price(max(
            bar.levels.keys(),
            key=lambda t: bar.levels[t].ask_vol + bar.levels[t].bid_vol
        )) if bar.levels else 0.0
        bar.bar_range = bar.high - bar.low
        self.current_bar = FootprintBar()  # reset for next bar
        return bar

    def on_trade(self, price, size, side):
        # Route to current bar accumulator (called from async callback)
        self.current_bar.on_trade(price, size, side)
```

**Critical: asyncio single-threaded model.** All Rithmic callbacks and the bar builder run in the same asyncio event loop. There is no thread contention. The `on_trade()` accumulator is synchronous (not async) so it runs inline with no context switch. The bar finalization coroutine yields control only during `asyncio.sleep`, which is safe because ticks cannot arrive during that yield in a single-threaded loop.

**Performance for 1,000 callbacks/sec:** asyncio coroutines are lightweight (microsecond overhead per dispatch). The hot path (`on_trade`) is a dict lookup + integer addition — well under 1 microsecond. At 1,000/sec, total CPU load from the accumulation loop is negligible. Signal detection runs only at bar close (once per minute for 1-minute bars), not per-tick. This matches NT8's design philosophy: E2/E3 DOM engines use per-tick data for state; E1/all others run on bar close.

---

## Signal Detection Implementation

### Feature 4: Absorption Variants — Python Implementation

All four absorption variants detect from the completed `FootprintBar` struct.

**Classic Absorption:**
```python
def detect_classic_absorption(bar: FootprintBar, atr: float, params) -> tuple[bool, int]:
    wick_up = bar.high - max(bar.open, bar.close)
    wick_dn = min(bar.open, bar.close) - bar.low
    body = abs(bar.close - bar.open)
    wick = max(wick_up, wick_dn)
    wick_ratio_ok = wick >= body * params.abs_wick_mult * (atr / params.baseline_atr)
    delta_ok = abs(bar.bar_delta) <= bar.total_vol * params.abs_balance_ratio
    if wick_ratio_ok and delta_ok:
        direction = -1 if wick_up > wick_dn else 1  # wick up = bearish absorption
        score = min(int((wick / body) * 10), 100)
        return True, direction, score
    return False, 0, 0
```

**Passive Absorption (limit order wall defense):**
```python
def detect_passive_absorption(bar: FootprintBar, params) -> tuple[bool, int, int]:
    """Detects high volume concentrating at price extremes while price holds."""
    ticks = sorted(bar.levels.keys())
    if not ticks:
        return False, 0, 0
    bar_range_ticks = ticks[-1] - ticks[0]
    if bar_range_ticks == 0:
        return False, 0, 0
    threshold_ticks = max(1, int(bar_range_ticks * 0.20))  # top/bottom 20%

    top_ticks = ticks[-threshold_ticks:]
    bot_ticks = ticks[:threshold_ticks]

    top_vol = sum(bar.levels[t].bid_vol + bar.levels[t].ask_vol for t in top_ticks)
    bot_vol = sum(bar.levels[t].bid_vol + bar.levels[t].ask_vol for t in bot_ticks)

    # Passive buy absorption: heavy vol at bottom, price held (didn't break low)
    if bot_vol >= bar.total_vol * params.passive_concentration_ratio:
        if bar.close > bar.low + (bar.bar_range * 0.30):  # price held above extreme
            return True, 1, int(bot_vol / bar.total_vol * 100)
    # Passive sell absorption: heavy vol at top, price held
    if top_vol >= bar.total_vol * params.passive_concentration_ratio:
        if bar.close < bar.high - (bar.bar_range * 0.30):
            return True, -1, int(top_vol / bar.total_vol * 100)
    return False, 0, 0
```

**Stopping Volume:**
```python
def detect_stopping_volume(bar: FootprintBar, poc_in_wick: bool,
                           rolling_peak_vol: float, params) -> tuple[bool, int, int]:
    """POC in wick + volume exceeds rolling session peak."""
    if not poc_in_wick:
        return False, 0, 0
    if bar.total_vol < rolling_peak_vol * params.stop_vol_mult:
        return False, 0, 0
    # POC in upper wick = sellers absorbed, bullish
    poc_tick = price_to_tick(bar.poc_price)
    bar_mid_tick = (price_to_tick(bar.high) + price_to_tick(bar.low)) // 2
    close_tick = price_to_tick(bar.close)
    if poc_tick > bar_mid_tick and close_tick < poc_tick:  # POC in upper wick
        direction = -1  # bearish — high-volume rejection
    else:
        direction = 1
    score = min(int((bar.total_vol / rolling_peak_vol) * 50), 100)
    return True, direction, score
```

**Effort vs. Result:**
```python
def detect_effort_vs_result(bar: FootprintBar, ema_vol: float,
                             atr: float, params) -> tuple[bool, int, int]:
    vol_ratio = bar.total_vol / ema_vol if ema_vol > 0 else 0
    range_ratio = bar.bar_range / atr if atr > 0 else 0
    if vol_ratio > params.evr_vol_mult and range_ratio < params.evr_range_cap:
        # High effort, minimal result — absorption or exhaustion
        score = min(int(vol_ratio * 20), 100)
        return True, 0, score  # direction determined by context (bar close vs. midpoint)
    return False, 0, 0
```

**POC-in-wick helper** (required by stopping volume):
```python
def poc_in_wick(bar: FootprintBar) -> bool:
    body_high = max(bar.open, bar.close)
    body_low  = min(bar.open, bar.close)
    return bar.poc_price > body_high or bar.poc_price < body_low
```

---

### Feature 5: Exhaustion Variants — Python Implementation

**Zero Print and Thin Print (scan price levels in bar):**
```python
import numpy as np

def detect_zero_and_thin_prints(bar: FootprintBar, params) -> dict:
    """Returns lists of zero-print ticks, thin-print ticks, fat-print ticks."""
    if not bar.levels:
        return {"zero": [], "thin": [], "fat": []}

    all_ticks = range(price_to_tick(bar.low), price_to_tick(bar.high) + 1)
    max_row_vol = max(
        (bar.levels[t].ask_vol + bar.levels[t].bid_vol for t in bar.levels),
        default=0
    )
    avg_row_vol = bar.total_vol / len(list(all_ticks)) if all_ticks else 0

    zero_prints, thin_prints, fat_prints = [], [], []
    for tick in all_ticks:
        vol = bar.levels[tick].ask_vol + bar.levels[tick].bid_vol if tick in bar.levels else 0
        if vol == 0:
            zero_prints.append(tick)
        elif vol < max_row_vol * params.thin_pct_threshold:
            thin_prints.append(tick)
        elif vol > avg_row_vol * params.fat_mult:
            fat_prints.append(tick)

    return {"zero": zero_prints, "thin": thin_prints, "fat": fat_prints}
```

**Zero prints at bar high → poor high (unfinished auction). Zero prints at bar low → poor low.** This directly feeds E9 Auction State Machine.

**Exhaustion Print (failed follow-through — multi-bar):**
```python
def detect_exhaustion_print(current_bar: FootprintBar, prev_bar: FootprintBar,
                             params) -> tuple[bool, int, int]:
    """High single-side volume at extreme + no follow-through in next bar."""
    # Get ask vol at prior bar's high (extreme buyer aggression)
    prev_high_tick = price_to_tick(prev_bar.high)
    ask_at_high = prev_bar.levels.get(prev_high_tick, FootprintLevel()).ask_vol
    # No follow-through: current bar fails to exceed prior high
    if (ask_at_high > prev_bar.total_vol * params.exhaustion_print_pct
            and current_bar.high < prev_bar.high):
        score = min(int(ask_at_high / prev_bar.total_vol * 100), 100)
        return True, -1, score  # bearish exhaustion
    # Symmetric: bid vol at low + price fails to break down
    prev_low_tick = price_to_tick(prev_bar.low)
    bid_at_low = prev_bar.levels.get(prev_low_tick, FootprintLevel()).bid_vol
    if (bid_at_low > prev_bar.total_vol * params.exhaustion_print_pct
            and current_bar.low > prev_bar.low):
        score = min(int(bid_at_low / prev_bar.total_vol * 100), 100)
        return True, 1, score  # bullish exhaustion
    return False, 0, 0
```

**Bid/Ask Fade (aggressor thinning at extremes — multi-bar):**
```python
def detect_bid_ask_fade(current_bar: FootprintBar, prev_bar: FootprintBar,
                         params) -> tuple[bool, int, int]:
    """Ask volume at current high < 60% of prior bar's ask at equivalent extreme."""
    curr_high_tick = price_to_tick(current_bar.high)
    prev_high_tick = price_to_tick(prev_bar.high)
    curr_ask = current_bar.levels.get(curr_high_tick, FootprintLevel()).ask_vol
    prev_ask = prev_bar.levels.get(prev_high_tick, FootprintLevel()).ask_vol
    if prev_ask > 0 and curr_ask < prev_ask * params.fade_ratio:
        score = int((1 - curr_ask / prev_ask) * 100)
        return True, -1, score  # bearish — buying is fading at highs
    # Symmetric for bid at lows
    curr_low_tick = price_to_tick(current_bar.low)
    prev_low_tick = price_to_tick(prev_bar.low)
    curr_bid = current_bar.levels.get(curr_low_tick, FootprintLevel()).bid_vol
    prev_bid = prev_bar.levels.get(prev_low_tick, FootprintLevel()).bid_vol
    if prev_bid > 0 and curr_bid < prev_bid * params.fade_ratio:
        score = int((1 - curr_bid / prev_bid) * 100)
        return True, 1, score  # bullish — selling is fading at lows
    return False, 0, 0
```

---

### Feature 6: Imbalance Detection — Python Implementation

**Diagonal imbalance algorithm** (industry standard per Quantower, ATAS documentation):
```python
def detect_imbalances(bar: FootprintBar, params) -> list[dict]:
    """
    Diagonal imbalance: compare ask[price] to bid[price - 1 tick].
    A buy imbalance at level P means: ask_vol[P] > bid_vol[P-1] * ratio.
    A sell imbalance at level P means: bid_vol[P] > ask_vol[P+1] * ratio.
    Returns list of {tick, direction, ratio, is_stacked} dicts.
    """
    ticks = sorted(bar.levels.keys())
    imbalances = []
    ratio = params.imbalance_ratio  # e.g., 3.0 = 300%

    for i, tick in enumerate(ticks):
        # Buy imbalance: ask at this level vs bid one level down
        if i > 0:
            ask = bar.levels[tick].ask_vol
            bid_below = bar.levels[ticks[i-1]].bid_vol
            if bid_below > 0 and ask / bid_below >= ratio:
                imbalances.append({
                    "tick": tick, "direction": 1,
                    "ratio": ask / bid_below, "is_stacked": False
                })
        # Sell imbalance: bid at this level vs ask one level up
        if i < len(ticks) - 1:
            bid = bar.levels[tick].bid_vol
            ask_above = bar.levels[ticks[i+1]].ask_vol
            if ask_above > 0 and bid / ask_above >= ratio:
                imbalances.append({
                    "tick": tick, "direction": -1,
                    "ratio": bid / ask_above, "is_stacked": False
                })

    # Mark stacked imbalances (N consecutive imbalances same direction)
    _mark_stacked(imbalances, min_stack=params.min_stack_count)
    return imbalances

def _mark_stacked(imbalances: list, min_stack: int = 3):
    """Mark consecutive same-direction imbalances as stacked."""
    for i, imb in enumerate(imbalances):
        if i < min_stack - 1:
            continue
        streak = all(
            imbalances[i - j]["direction"] == imb["direction"]
            for j in range(min_stack)
        )
        if streak:
            for j in range(min_stack):
                imbalances[i - j]["is_stacked"] = True
```

**Inverse imbalance (trapped trader detection):**
```python
def detect_inverse_imbalances(bar: FootprintBar,
                                imbalances: list[dict]) -> list[dict]:
    """
    Inverse imbalance: high-volume side is NOT where price went.
    Bearish inverse: bid imbalance cells at bar LOW + price closes ABOVE midpoint
                     + bar_delta POSITIVE (buyers won).
    Bullish inverse: ask imbalance cells at bar HIGH + price closes BELOW midpoint
                     + bar_delta NEGATIVE (sellers won).
    """
    bar_mid = (bar.high + bar.low) / 2
    inverse = []
    low_tick = price_to_tick(bar.low)
    high_tick = price_to_tick(bar.high)

    sell_imbs_near_low = [i for i in imbalances
                          if i["direction"] == -1
                          and abs(i["tick"] - low_tick) <= 4]  # within 4 ticks of low
    buy_imbs_near_high = [i for i in imbalances
                          if i["direction"] == 1
                          and abs(i["tick"] - high_tick) <= 4]

    # Bearish inverse: sellers trapped at low
    if sell_imbs_near_low and bar.close > bar_mid and bar.bar_delta > 0:
        inverse.append({"direction": 1, "strength": len(sell_imbs_near_low),
                        "type": "trapped_seller"})

    # Bullish inverse: buyers trapped at high
    if buy_imbs_near_high and bar.close < bar_mid and bar.bar_delta < 0:
        inverse.append({"direction": -1, "strength": len(buy_imbs_near_high),
                        "type": "trapped_buyer"})

    return inverse
```

---

### Feature 7: E8 CVD Multi-Bar Divergence Engine

**Linear regression slope over deque of bar deltas:**
```python
from collections import deque
import numpy as np

class CVDEngine:
    def __init__(self, window: int = 5):
        self.window = window
        self.delta_history = deque(maxlen=window)
        self.price_history  = deque(maxlen=window)
        self.cvd = 0  # cumulative

    def update(self, bar: FootprintBar) -> dict:
        self.cvd += bar.bar_delta
        self.delta_history.append(bar.bar_delta)
        self.price_history.append(bar.close)

        result = {"divergence": False, "direction": 0, "score": 0, "cvd": self.cvd}
        if len(self.delta_history) < self.window:
            return result

        x = np.arange(self.window, dtype=float)
        delta_slope = np.polyfit(x, list(self.delta_history), 1)[0]
        price_slope  = np.polyfit(x, list(self.price_history), 1)[0]

        # Divergence: slopes have opposite signs AND delta slope is meaningful
        if (np.sign(delta_slope) != np.sign(price_slope)
                and abs(delta_slope) > params.cvd_div_slope_min):
            result["divergence"] = True
            result["direction"]  = 1 if delta_slope > 0 else -1
            result["score"] = min(int(abs(delta_slope) / params.cvd_norm_factor * 100), 100)
        return result
```

**Inference frequency:** Every bar close (once per minute for 1m bars). The deque holds only the last N bar deltas — no per-tick state needed.

---

### Feature 8: LVN/HVN Volume Profile — Python Implementation

**Session histogram construction:**
```python
import numpy as np
from scipy.signal import find_peaks

class VolumeProfile:
    def __init__(self, tick_size: float = 0.25):
        self.tick_size = tick_size
        self.profile: DefaultDict[int, int] = defaultdict(int)  # tick -> total_vol

    def add_bar(self, bar: FootprintBar):
        """Accumulate bar's volume into session profile."""
        for tick, level in bar.levels.items():
            self.profile[tick] += level.ask_vol + level.bid_vol

    def get_lvn_hvn(self, params) -> dict:
        """
        Detect LVN and HVN from session volume profile.
        LVN: bin volume < LVN_THRESHOLD * avg_bin
        HVN: bin volume > HVN_THRESHOLD * avg_bin
        Valley detection via scipy.signal.find_peaks on inverted histogram.
        """
        if not self.profile:
            return {"lvn": [], "hvn": [], "poc": None}

        ticks = sorted(self.profile.keys())
        vols  = np.array([self.profile[t] for t in ticks], dtype=float)
        avg_vol = vols.mean()

        # POC: highest volume node
        poc_idx = np.argmax(vols)
        poc_price = tick_to_price(ticks[poc_idx])

        # HVN: explicit threshold
        hvn_mask = vols > avg_vol * params.hvn_threshold  # e.g., 1.70
        hvn_prices = [tick_to_price(ticks[i]) for i, v in enumerate(hvn_mask) if v]

        # LVN: invert and find peaks (peaks in inverted = valleys in original)
        inverted = -vols
        lvn_indices, _ = find_peaks(
            inverted,
            height=-avg_vol * params.lvn_threshold,  # vol < threshold * avg
            distance=params.lvn_min_separation_ticks   # min gap between LVNs
        )
        lvn_prices = [tick_to_price(ticks[i]) for i in lvn_indices]

        return {"lvn": lvn_prices, "hvn": hvn_prices, "poc": poc_price}
```

**Why scipy.signal.find_peaks for valleys:** The standard approach is to negate the volume array and call `find_peaks` on the negated signal. This is the canonical Python pattern for valley detection — confirmed by scipy documentation. The `distance` parameter enforces the minimum LVN zone separation (equivalent to NT8's `LvnSeparationMinTicks`). The `height` parameter with a threshold relative to `avg_vol` replicates the `bin_vol < LVN_THRESHOLD * avgBin` logic from v1 research.

**Zone lifecycle FSM** — unchanged from v1 research design. States: Created → Defended → Broken → Flipped → Invalidated. In Python this is a simple dataclass with a `state: LVNState` enum field and methods `touch()`, `break_zone()`, `flip_zone()`.

---

### Feature 9: E9 Auction State Machine — Python Implementation

**Inputs come from zero/thin print scan (Feature 5):**

```python
from enum import Enum, auto

class AuctionState(Enum):
    OPEN       = auto()
    POOR_HIGH  = auto()  # zero/thin prints at bar high
    POOR_LOW   = auto()  # zero/thin prints at bar low
    VOLUME_VOID = auto() # 3+ consecutive LVN bins between current price and prior HVN
    UNFINISHED  = auto() # session close with poor high/low, no revisit
    FINISHED    = auto() # price returned to prior single print area

class AuctionStateMachine:
    def __init__(self):
        self.state = AuctionState.OPEN
        self.unfinished_levels: list[float] = []  # survive session reset

    def update(self, bar: FootprintBar, prints: dict, lvn_zones: list) -> AuctionState:
        ticks = prints
        high_tick = price_to_tick(bar.high)
        low_tick  = price_to_tick(bar.low)

        # Check for poor high (zero/thin prints at bar extreme)
        poor_high = any(t >= high_tick - 2 for t in ticks["zero"] + ticks["thin"])
        poor_low  = any(t <= low_tick  + 2 for t in ticks["zero"] + ticks["thin"])

        if poor_high:
            self.state = AuctionState.POOR_HIGH
            self.unfinished_levels.append(bar.high)
        elif poor_low:
            self.state = AuctionState.POOR_LOW
            self.unfinished_levels.append(bar.low)
        else:
            # Check if price returned to fill a prior unfinished level
            for level in self.unfinished_levels[:]:
                if abs(bar.low - level) <= 2 * TICK_SIZE or abs(bar.high - level) <= 2 * TICK_SIZE:
                    self.state = AuctionState.FINISHED
                    self.unfinished_levels.remove(level)
            else:
                self.state = AuctionState.OPEN

        return self.state
```

**Cross-session persistence:** `self.unfinished_levels` is NOT reset on session open. Serialize to JSON/SQLite at session end, reload at session start. This is the key difference from all other bar-state variables.

---

### Feature 10: E10 — Kronos Directional Bias Signal

**What Kronos provides:** A foundation model (decoder-only Transformer) trained on K-line sequences from 45+ exchanges. Accepts OHLCV dataframes, outputs probabilistic forecasts of future OHLCV values.

**Input requirements:**
- DataFrame with columns `['open', 'high', 'low', 'close']` (volume optional)
- `x_timestamp`: historical timestamps
- `y_timestamp`: future period timestamps (defines `pred_len`)
- `max_context`: 512 (model's sequence window limit)

**Directional bias extraction — not provided natively, must be computed:**

Kronos outputs forecasted future candles, not a direction label. To produce E10's directional bias signal:

```python
from kronos import KronosPredictor

class KronosBiasEngine:
    def __init__(self, model, tokenizer, horizon_bars: int = 5):
        self.predictor = KronosPredictor(model, tokenizer, max_context=512)
        self.horizon = horizon_bars
        self.n_samples = 20  # ensemble samples for confidence scoring

    def get_bias(self, ohlcv_df, current_timestamps, future_timestamps) -> dict:
        """
        Run N stochastic samples, average forecasted close prices.
        Direction = sign(avg_forecast_close[-1] - current_close).
        Confidence = 1 - (std across samples / abs(mean forecast delta)).
        """
        forecasts = []
        for _ in range(self.n_samples):
            forecast_df = self.predictor.predict(
                ohlcv_df, current_timestamps, future_timestamps,
                pred_len=self.horizon
            )
            forecasts.append(forecast_df["close"].values)

        samples = np.array(forecasts)  # shape: (n_samples, horizon)
        mean_close = samples.mean(axis=0)
        std_close   = samples.std(axis=0)

        current_close = ohlcv_df["close"].iloc[-1]
        delta = mean_close[-1] - current_close

        direction = 1 if delta > 0 else -1 if delta < 0 else 0
        # Confidence: low std relative to delta magnitude = high confidence
        uncertainty = std_close[-1] / (abs(delta) + 1e-6)
        confidence = max(0.0, min(1.0, 1.0 - uncertainty))
        score = int(confidence * 100)

        return {
            "direction": direction,
            "confidence": confidence,
            "score": score,
            "forecast_delta": delta
        }
```

**Inference frequency:** Every N bars (recommended N=5 for 1-minute bars = every 5 minutes). Running 20 stochastic samples per bar close is expensive; batching to every 5 bars gives the model sufficient new information to produce a materially different forecast. Between Kronos updates, the prior bias signal persists with a decay factor (e.g., confidence multiplied by 0.95 per bar that passes without re-inference).

**GPU vs. CPU:** Kronos-mini (4.1M params) runs on CPU with ~200ms latency per call. Kronos-small (24.7M) requires GPU for sub-second latency. Kronos-base (102.3M) requires GPU. At every-5-bar inference, even CPU latency is acceptable for 1-minute bars.

**Confidence scoring rationale:** Kronos's probabilistic framework allows generating multiple distinct future trajectories from the same context via stochastic sampling. Averaging N samples (the ensemble approach documented in Kronos's AAAI 2026 paper) reduces prediction variance. The confidence signal is inversely proportional to the spread of the sample distribution — high spread = low confidence = lower E10 weight in scoring.

---

### Feature 11: Narrative Bar Classification — Python Implementation

**Hierarchical classification (absorption > exhaustion > momentum > rejection > quiet):**

```python
class BarNarrative(Enum):
    QUIET      = 0
    REJECTION  = 1
    MOMENTUM   = 2
    EXHAUSTION = 3
    ABSORPTION = 4

def classify_bar_narrative(
    bar: FootprintBar,
    absorption_signals: list,   # from Features 4
    exhaustion_signals: list,   # from Features 5
    params,
    atr: float
) -> BarNarrative:
    """
    Strict hierarchy: only the highest-priority narrative is returned.
    Confirmation window logic is handled by the caller (2-bar lookahead buffer).
    """
    if any(s["fired"] for s in absorption_signals):
        return BarNarrative.ABSORPTION
    if any(s["fired"] for s in exhaustion_signals):
        return BarNarrative.EXHAUSTION

    # Momentum: large directional bar with aligned delta
    if bar.bar_range > atr * params.momentum_range_min:
        delta_aligned = (bar.bar_delta > 0 and bar.close > bar.open) or \
                        (bar.bar_delta < 0 and bar.close < bar.open)
        if delta_aligned:
            return BarNarrative.MOMENTUM

    # Rejection: significant wick with no body follow-through
    body = abs(bar.close - bar.open)
    upper_wick = bar.high - max(bar.open, bar.close)
    lower_wick = min(bar.open, bar.close) - bar.low
    if max(upper_wick, lower_wick) > body * params.rejection_wick_mult:
        return BarNarrative.REJECTION

    return BarNarrative.QUIET
```

---

## Data Pipeline Architecture

### Feature 12: Databento MBO Historical Replay for Backtesting

**MBO record fields for footprint reconstruction:**

Databento MBO records for CME futures (`GLBX.MDP3`) contain:
- `action`: `'T'` = trade, `'A'` = add order, `'C'` = cancel, `'M'` = modify
- `side`: `'B'` = bid (sell aggressor hit the bid), `'A'` = ask (buy aggressor lifted the ask)
- `price`, `size` — tick price and quantity

**Footprint construction from MBO:**
```python
for record in databento_client.replay():
    if record.action == 'T':  # trade only
        side = TransactionType.SELL if record.side == 'B' else TransactionType.BUY
        bar_builder.on_trade(record.price / 1e9, record.size, side)
```

The Databento MBO data has nanosecond timestamps, enabling exact replay identical to live. The `action == 'T'` filter is the critical step — add/cancel/modify events do NOT create footprint volume, only executed trades do.

---

## Table Stakes (Signal Implementation Requirements)

All 44 signals carry forward from v1 research. Below are the Python-specific implementation notes for each category:

| Category | Signals | Implementation Path | Per-tick or Per-bar |
|----------|---------|---------------------|---------------------|
| Absorption (4) | Classic, Passive, Stopping Vol, Effort vs Result | From `FootprintBar` struct at bar close | Per-bar |
| Exhaustion (6) | Zero print, Thin print, Fat print, Exhaustion print, Fading momentum (CVD), Bid/ask fade | Zero/thin/fat from level scan; CVD from E8 deque; multi-bar need prev_bar | Per-bar |
| Imbalance (9) | Diagonal, Stacked, Inverse (trapped) + variants | From level dict, diagonal comparison algorithm | Per-bar |
| Delta (11) | Bar delta, CVD, divergence, climax delta + variants | Bar delta from accumulator; CVD deque; regression slope | Per-bar |
| Absorption variants require multi-bar state: prev 2 bars held in ring buffer | | | |
| Auction Theory (5) | Poor high/low, unfinished business, volume void, market sweep | Zero/thin prints + LVN zones | Per-bar (cross-session persist) |
| Trapped Traders (5) | Inverse imbalance, fake absorption, failed breakout + variants | From imbalance list + close-vs-extreme logic | Per-bar |
| Volume Patterns (6) | Stopping volume, effort-vs-result, volume climax, sequence | From FootprintBar totals + EMA vol | Per-bar |
| POC/Value Area (8) | POC position, VWAP zones, VAH/VAL, value area migration | From VP profile + VWAP calculation | Per-bar |

**Per-tick signals (E2/E3 DOM equivalents in Python):**

E2 (DOM imbalance engine) and E3 (DOM momentum engine) need per-tick L2 DOM updates, not trade data. In async-rithmic, subscribe to DOM depth callbacks (`DataType.DOM_LEVEL`). These run inline with the asyncio event loop:

```python
async def on_dom_update(data: dict):
    # Track bid/ask depth at each of 40 levels
    # Compute bid_total_depth vs ask_total_depth
    # DOM imbalance = bid_depth / ask_depth (or inverse)
    dom_engine.update(data["bid_prices"], data["bid_sizes"],
                      data["ask_prices"], data["ask_sizes"])
```

DOM state is sampled at bar close for signal detection — the live per-tick DOM state is stored in the engine but signals are generated only when a bar closes.

---

## Anti-Features (Python-specific)

### Anti-Feature 1: Per-Tick Signal Detection for Bar-Close Signals

**What it is:** Running absorption/exhaustion detection on every tick (1,000/sec) rather than on bar close.

**Why to avoid:** Absorption is a bar-level phenomenon — it requires the complete distribution of bid/ask volume across all price levels within a bar. Detecting it mid-bar produces false signals (a bar can start with heavy selling and end with balanced absorption). Bar close is the correct temporal resolution for 42 of the 44 signals. DOM signals (E2/E3) are the only exceptions.

**What to do instead:** All footprint signals run in the `on_bar_close` callback, not in `on_trade`. The `on_trade` callback is a pure accumulator — it stores data, detects nothing.

---

### Anti-Feature 2: Rebuilding the DOM Orderbook from Scratch

**What it is:** Attempting to reconstruct the full limit order book by tracking every add/cancel/modify event from Rithmic L2 rather than using the pre-built DOM snapshot updates.

**Why to avoid:** async-rithmic delivers L2 DOM as pre-aggregated price level snapshots (40+ levels, bid price + size + ask price + size per level). Rithmic's own processing already handles the orderbook reconstruction at their server. Rebuilding from raw order events in Python would require processing L3 MBO-equivalent data, which Rithmic's R|Protocol does not expose at the same level Databento's MBO feed does. Use async-rithmic's DOM depth callbacks as intended.

**What to do instead:** Subscribe to DOM depth updates, store the latest snapshot per price level, compute depth ratios per E2/E3 logic.

---

### Anti-Feature 3: Numpy Pre-allocated Arrays for Live Bar Accumulation

**What it is:** Using a pre-allocated numpy array for bid/ask volume accumulation during the live bar, with array index = price tier.

**Why to avoid:** NQ's intraday range can be 100+ points (400+ ticks). A numpy array covering the full possible range would require pre-allocating thousands of entries per bar even when only 20-30 price levels actually trade. Worse, if the bar range exceeds the pre-allocated window, the array must be resized (expensive). Dict accumulation with O(1) lookup is strictly superior for the live path.

**What to do instead:** Accumulate in `defaultdict` during the bar. Convert to sorted numpy arrays only after bar close for vectorized signal detection (imbalance scan, zero/thin print scan). Both can be done in O(levels) at bar finalization.

---

## Feature Dependencies (Python-specific order)

```
Tick Classifier (Feature 1)  [async-rithmic aggressor field]
  └─> FootprintBar accumulator (Feature 2)
        └─> Bar Builder finalization event (Feature 3)
              └─> [ALL signal detectors run here at bar close]
              |
              ├─> Absorption variants (Feature 4)
              |     └─> Requires: ATR(20) from rolling bar history
              |
              ├─> Exhaustion variants (Feature 5)
              |     └─> Requires: prev_bar ring buffer (depth=2)
              |     └─> Requires: E8 CVD Engine (Feature 7)
              |
              ├─> Imbalance detection (Feature 6)
              |     └─> Inverse imbalance requires bar.bar_delta
              |
              ├─> E8 CVD Engine (Feature 7)
              |     └─> Feeds: Fading momentum exhaustion signal
              |     └─> Feeds: Delta category signals
              |
              ├─> LVN/HVN Volume Profile (Feature 8)
              |     └─> Accumulates all session bars
              |     └─> Feeds: LVN zone proximity in scoring
              |
              ├─> E9 Auction State Machine (Feature 9)
              |     └─> Requires: zero/thin prints from Feature 5
              |     └─> Cross-session state persists
              |
              ├─> Narrative Classification (Feature 11)
              |     └─> Requires: all absorption + exhaustion signals
              |
              └─> Confluence Scoring (from v1 design, unchanged)
                    └─> Requires: all 8 signal categories
                    └─> Requires: LVN proximity (Feature 8)
                    └─> Requires: GEX levels (FlashAlpha API)

E10 Kronos Bias (Feature 10)
  └─> Runs every 5 bars (independent of tick stream)
  └─> Requires: OHLCV history from bar ring buffer
  └─> Outputs: directional bias + confidence → E10 score

DOM Depth updates [async-rithmic DataType.DOM_LEVEL]
  └─> E2 DOM Imbalance engine (per-tick accumulation, bar-close signal)
  └─> E3 DOM Momentum engine (per-tick accumulation, bar-close signal)
```

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Tick classification (aggressor field) | HIGH | Confirmed from Rithmic protobuf source — `TransactionType {BUY=1; SELL=2}` is natively provided |
| Footprint data structure (dict per bar) | HIGH | Corroborated by OrderFlowChart library, MQL5 footprint article, standard practice across implementations |
| Bar builder (asyncio time-based) | HIGH | asyncio event loop is well-understood; 1,000 callbacks/sec is far within Python's async throughput |
| Imbalance detection algorithm | HIGH | Diagonal comparison algorithm confirmed by Quantower, ATAS, GoCharting documentation |
| Absorption/exhaustion Python formulas | HIGH | Direct translation from v1 C# formulas; validated by ATAS and footprint chart literature |
| LVN via scipy find_peaks | HIGH | Standard scipy pattern; valley detection via negation is canonical |
| CVD linear regression (E8) | HIGH | numpy polyfit standard pattern; divergence detection from CVD is well-documented |
| Kronos directional bias extraction | MEDIUM | Kronos outputs OHLCV forecasts not direction labels; confidence via ensemble sampling is inferred from AAAI paper description, not explicit documentation |
| Kronos inference frequency (every 5 bars) | LOW | No documented recommendation; 5-bar is engineering judgment based on compute vs. staleness tradeoff |
| Databento MBO footprint reconstruction | MEDIUM | MBO schema fields confirmed from Databento docs; 'T' action filter is standard but exact field names need live validation |

---

## MVP Implementation Order

**Phase order within the footprint engine milestone:**

1. Tick classifier + FootprintBar accumulator + Bar builder (Features 1-3) — foundation; blocks everything
2. ATR normalization utility (volatility scaling) — low complexity; unblocks all signal thresholds
3. Absorption all 4 variants (Feature 4) — core alpha
4. Zero/thin/fat print scan + Exhaustion print + Bid/ask fade (Feature 5) — extends bar struct
5. Imbalance + inverse imbalance detection (Feature 6) — adds trapped trader signals
6. E8 CVD engine (Feature 7) — enables fading momentum exhaustion variant
7. Narrative classification (Feature 11) — refactors to hierarchical; unblocks TypeA gate
8. LVN/HVN Volume Profile (Feature 8) — session profile; enables LVN proximity scoring
9. E9 Auction State Machine (Feature 9) — builds on zero/thin prints
10. E10 Kronos bias (Feature 10) — independent; can run in parallel with 4-9
11. DOM depth integration (E2/E3 engines) — final; requires stable bar stream first

**Defer:**
- Full 44-signal scoring confluence (requires all engines) — build skeleton, fill in as engines complete
- Databento MBO backtesting — parallel effort; same bar builder, different data source
- Kronos-base model (GPU required) — start with Kronos-mini on CPU, upgrade if latency is acceptable

---

## Sources

- async-rithmic Python library: https://github.com/rundef/async_rithmic
- async-rithmic docs (real-time data): https://async-rithmic.readthedocs.io/en/latest/realtime_data.html
- Rithmic protobuf (aggressor field): https://github.com/igorrivin/rithmic/blob/master/response_historical_last_trade.proto
- Kronos foundation model (AAAI 2026): https://github.com/shiyu-coder/Kronos
- Kronos arXiv paper: https://arxiv.org/html/2508.02739v1
- Kronos HuggingFace: https://huggingface.co/NeoQuasar/Kronos-base
- NinjaTrader VolumetricBarsType API: https://ninjatrader.com/support/helpguides/nt8/order_flow_volumetric_bars2.htm
- OrderFlowChart Python library: https://github.com/murtazayusuf/OrderflowChart
- Quantower imbalance documentation: https://quantower.medium.com/imbalance-on-footprint-chart-a0454368c909
- Databento MBO schema: https://databento.com/docs/schemas-and-data-formats/mbo
- scipy.signal.find_peaks: https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html
- ATAS absorption documentation: https://atas.net/volume-analysis/strategies-and-trading-patterns/absorption-of-demand-and-supply-in-the-footprint-chart/
- TradeDevils inverse imbalance: https://tradedevils-indicators.com/pages/the-best-order-flow-footprint-indicator-for-ninjatrader-8-page-2
- Bookmap CVD divergence: https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy
- Emoji Trading unfinished business: https://www.emojitrading.com/docs/order-flow-basics/key-order-flow-traded-volume-concepts/unfinished-business/
- Trade classification algorithms review: https://www.sciencedirect.com/science/article/abs/pii/S1386418115000415
