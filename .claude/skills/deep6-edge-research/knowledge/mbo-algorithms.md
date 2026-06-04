# MBO Algorithms — Mathematical Foundations

Complete algorithmic reference for institutional-grade MBO order book analysis.
Every formula, every algorithm, every data structure needed to build a system
that processes order flow at the speed and depth of a prop trading firm.

---

## 1. ORDER BOOK STATE REPRESENTATION

### 1.1 Core Data Structures

```python
# Optimal LOB representation for NQ futures
# Price levels indexed by integer ticks (price / 0.25)

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np

@dataclass
class OrderState:
    order_id: str           # exchange_order_id
    price: float
    size: int
    side: str               # 'B' (bid) or 'A' (ask)
    add_time_ns: int        # nanosecond timestamp
    modify_count: int = 0
    priority: int = 0       # depth_order_priority
    fills: List[int] = field(default_factory=list)

@dataclass
class PriceLevelState:
    price: float
    total_size: int = 0
    order_count: int = 0
    orders: Dict[str, OrderState] = field(default_factory=dict)

class MBOOrderBook:
    """
    Full MBO order book with O(1) order lookup and O(log n) level operations.
    Maintains both individual order state and aggregated price-level view.
    """
    def __init__(self):
        # Individual order tracking (for lifecycle analysis)
        self.orders: Dict[str, OrderState] = {}
        # Price level aggregation (for DOM view)
        self.bids: Dict[int, PriceLevelState] = {}  # tick → level
        self.asks: Dict[int, PriceLevelState] = {}
        # Lifecycle history (for spoof/iceberg detection)
        self.lifecycle: Dict[str, dict] = {}  # order_id → lifecycle record

    def price_to_tick(self, price: float) -> int:
        return round(price / 0.25)

    def on_add(self, order_id: str, price: float, size: int,
               side: str, ts_ns: int, priority: int) -> None:
        tick = self.price_to_tick(price)
        order = OrderState(order_id, price, size, side, ts_ns, priority=priority)
        self.orders[order_id] = order
        levels = self.bids if side == 'B' else self.asks
        if tick not in levels:
            levels[tick] = PriceLevelState(price)
        levels[tick].total_size += size
        levels[tick].order_count += 1
        levels[tick].orders[order_id] = order
        # Start lifecycle record
        self.lifecycle[order_id] = {
            'add_time': ts_ns, 'price': price, 'size': size, 'side': side,
            'fills': [], 'cancel_time': None, 'fill_ratio': 0.0
        }

    def on_cancel(self, order_id: str, ts_ns: int) -> Optional[OrderState]:
        order = self.orders.pop(order_id, None)
        if order is None:
            return None
        tick = self.price_to_tick(order.price)
        levels = self.bids if order.side == 'B' else self.asks
        if tick in levels:
            levels[tick].total_size -= order.size
            levels[tick].order_count -= 1
            levels[tick].orders.pop(order_id, None)
            if levels[tick].total_size <= 0:
                del levels[tick]
        if order_id in self.lifecycle:
            lc = self.lifecycle[order_id]
            lc['cancel_time'] = ts_ns
            lc['life_ms'] = (ts_ns - lc['add_time']) / 1e6
            filled = sum(lc['fills'])
            lc['fill_ratio'] = filled / lc['size'] if lc['size'] > 0 else 0
        return order

    def on_trade(self, order_id: str, fill_size: int, ts_ns: int) -> None:
        if order_id in self.lifecycle:
            self.lifecycle[order_id]['fills'].append(fill_size)
        if order_id in self.orders:
            self.orders[order_id].size -= fill_size
            order = self.orders[order_id]
            tick = self.price_to_tick(order.price)
            levels = self.bids if order.side == 'B' else self.asks
            if tick in levels:
                levels[tick].total_size -= fill_size

    def best_bid(self) -> Optional[float]:
        if not self.bids:
            return None
        return max(self.bids.keys()) * 0.25

    def best_ask(self) -> Optional[float]:
        if not self.asks:
            return None
        return min(self.asks.keys()) * 0.25

    def mid(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb and ba:
            return (bb + ba) / 2
        return None

    def microprice(self) -> Optional[float]:
        """Quantity-weighted mid — better predictor than simple mid."""
        bb_tick = max(self.bids.keys()) if self.bids else None
        ba_tick = min(self.asks.keys()) if self.asks else None
        if bb_tick is None or ba_tick is None:
            return None
        bid_size = self.bids[bb_tick].total_size
        ask_size = self.asks[ba_tick].total_size
        total = bid_size + ask_size
        if total == 0:
            return None
        return (ba_tick * 0.25 * bid_size + bb_tick * 0.25 * ask_size) / total
```

---

## 2. SPOOF DETECTION ALGORITHM

### 2.1 Lifecycle-Based Spoof Detector

```python
class SpoofDetector:
    """
    Detects spoofing using order lifecycle analysis.
    Requires MBO data with exchange_order_id.

    Evidence chain (all required for high confidence):
    (a) Large order: size > SPOOF_SIZE_MULT × surrounding_avg
    (b) Short life: life_ms < SPOOF_LIFE_MS
    (c) No fills: fill_ratio < SPOOF_FILL_THRESH
    (d) Near touch: within SPOOF_TICK_DIST ticks of best bid/ask
    (e) Book imbalance changed during order's life
    (f) Optional: opposite-side aggression during order's life
    """

    SPOOF_SIZE_MULT = 5.0      # order must be 5× surrounding average
    SPOOF_LIFE_MS = 5000       # must cancel within 5 seconds
    SPOOF_FILL_THRESH = 0.05   # less than 5% filled
    SPOOF_TICK_DIST = 5        # within 5 ticks of touch

    def evaluate_lifecycle(self, order_id: str, book: MBOOrderBook,
                           cancel_ts_ns: int) -> Optional[dict]:
        lc = book.lifecycle.get(order_id)
        if lc is None:
            return None

        life_ms = (cancel_ts_ns - lc['add_time']) / 1e6
        fill_ratio = sum(lc['fills']) / lc['size'] if lc['size'] > 0 else 0

        # Check (b): short life
        if life_ms >= self.SPOOF_LIFE_MS:
            return None

        # Check (c): no fills
        if fill_ratio >= self.SPOOF_FILL_THRESH:
            return None

        # Check (a): large order
        surrounding_avg = self._compute_surrounding_avg(lc['price'], lc['side'], book)
        if surrounding_avg > 0 and lc['size'] < self.SPOOF_SIZE_MULT * surrounding_avg:
            return None

        # Check (d): near touch
        touch = book.best_bid() if lc['side'] == 'B' else book.best_ask()
        if touch is None:
            return None
        tick_dist = abs(lc['price'] - touch) / 0.25
        if tick_dist > self.SPOOF_TICK_DIST:
            return None

        # Compute confidence
        size_ratio = lc['size'] / max(surrounding_avg, 1)
        life_score = 1.0 - (life_ms / self.SPOOF_LIFE_MS)
        fill_score = 1.0 - fill_ratio
        dist_score = 1.0 - (tick_dist / self.SPOOF_TICK_DIST)
        confidence = (size_ratio / 10 * 0.4 + life_score * 0.3 +
                      fill_score * 0.2 + dist_score * 0.1)
        confidence = min(confidence, 1.0)

        return {
            'order_id': order_id,
            'price': lc['price'],
            'side': lc['side'],
            'size': lc['size'],
            'life_ms': life_ms,
            'fill_ratio': fill_ratio,
            'tick_dist': tick_dist,
            'confidence': confidence,
            'reason_codes': ['short_life', 'no_fill', 'oversized', 'near_touch'],
        }

    def _compute_surrounding_avg(self, price: float, side: str,
                                  book: MBOOrderBook) -> float:
        levels = book.bids if side == 'B' else book.asks
        tick = round(price / 0.25)
        sizes = []
        for offset in range(-5, 6):
            t = tick + offset
            if t != tick and t in levels:
                sizes.append(levels[t].total_size)
        return np.mean(sizes) if sizes else 0.0
```

---

## 3. ICEBERG DETECTION ALGORITHM

### 3.1 Refresh-Pattern Iceberg Detector

```python
class IcebergDetector:
    """
    Detects iceberg orders using refresh pattern analysis.
    Based on Zotikov (2019): HVr = traded_cum / peak_visible ≥ 2.0

    Requires tracking:
    - traded_cum: total volume traded at price level
    - peak_visible: maximum visible size ever seen at level
    - refresh_count: number of ADD events after fills at same price
    - refresh_order_ids: set of order IDs that refreshed
    """

    HVR_THRESHOLD = 2.0        # Zotikov threshold
    MIN_REFRESHES = 2          # minimum refresh events
    REFRESH_WINDOW_MS = 500    # refresh must occur within 500ms of fill

    def __init__(self):
        # Per-price tracking
        self.traded_cum: Dict[float, int] = defaultdict(int)
        self.peak_visible: Dict[float, int] = defaultdict(int)
        self.refresh_count: Dict[float, int] = defaultdict(int)
        self.last_fill_time: Dict[float, int] = {}
        self.refresh_ids: Dict[float, set] = defaultdict(set)

    def on_trade(self, price: float, size: int, ts_ns: int) -> None:
        self.traded_cum[price] += size
        self.last_fill_time[price] = ts_ns

    def on_add(self, order_id: str, price: float, size: int, ts_ns: int) -> None:
        # Update peak visible
        # (would need current level size — simplified here)
        self.peak_visible[price] = max(self.peak_visible[price], size)

        # Check if this is a refresh (ADD shortly after fill at same price)
        last_fill = self.last_fill_time.get(price)
        if last_fill and (ts_ns - last_fill) / 1e6 < self.REFRESH_WINDOW_MS:
            self.refresh_count[price] += 1
            self.refresh_ids[price].add(order_id)

    def evaluate(self, price: float) -> Optional[dict]:
        traded = self.traded_cum.get(price, 0)
        peak = self.peak_visible.get(price, 1)
        refreshes = self.refresh_count.get(price, 0)

        if peak == 0:
            return None

        hvr = traded / peak

        if hvr < self.HVR_THRESHOLD:
            return None
        if refreshes < self.MIN_REFRESHES:
            return None

        confidence = min((hvr / 5.0) * 0.6 + (refreshes / 10.0) * 0.4, 1.0)

        return {
            'price': price,
            'traded_cum': traded,
            'peak_visible': peak,
            'hvr': hvr,
            'refresh_count': refreshes,
            'confidence': confidence,
            'reason_codes': ['high_hvr', 'refresh_pattern'],
        }
```

---

## 4. ORDER FLOW IMBALANCE (OFI)

### 4.1 Multi-Level OFI Computation

```python
def compute_ofi(book_before: MBOOrderBook, book_after: MBOOrderBook,
                depth: int = 10) -> float:
    """
    Compute Order Flow Imbalance at specified depth.
    Cont, Kukanov & Stoikov (2014).

    OFI = Σ_i (ΔQ_bid_i - ΔQ_ask_i) for i in 1..depth
    where ΔQ = change in quantity at level i
    """
    ofi = 0.0

    # Get top N bid levels
    bid_ticks_before = sorted(book_before.bids.keys(), reverse=True)[:depth]
    bid_ticks_after  = sorted(book_after.bids.keys(), reverse=True)[:depth]

    # Get top N ask levels
    ask_ticks_before = sorted(book_before.asks.keys())[:depth]
    ask_ticks_after  = sorted(book_after.asks.keys())[:depth]

    # Compute bid changes
    for tick in set(bid_ticks_before) | set(bid_ticks_after):
        size_before = book_before.bids.get(tick, PriceLevelState(0)).total_size
        size_after  = book_after.bids.get(tick, PriceLevelState(0)).total_size
        ofi += (size_after - size_before)

    # Compute ask changes (subtract)
    for tick in set(ask_ticks_before) | set(ask_ticks_after):
        size_before = book_before.asks.get(tick, PriceLevelState(0)).total_size
        size_after  = book_after.asks.get(tick, PriceLevelState(0)).total_size
        ofi -= (size_after - size_before)

    return ofi


def compute_ofi_normalized(book_before: MBOOrderBook, book_after: MBOOrderBook,
                            depth: int = 10) -> float:
    """Normalized OFI in [-1, 1]."""
    raw = compute_ofi(book_before, book_after, depth)
    total = sum(l.total_size for l in book_after.bids.values()) + \
            sum(l.total_size for l in book_after.asks.values())
    return raw / total if total > 0 else 0.0
```

---

## 5. KYLE'S LAMBDA (PRICE IMPACT)

### 5.1 Real-Time Lambda Estimation

```python
class KyleLambdaEstimator:
    """
    Estimates Kyle's lambda (price impact per unit of signed order flow).
    λ = ΔP / Q where Q is signed volume (+ = buy, - = sell)

    Uses rolling OLS regression over recent trades.
    """

    def __init__(self, window: int = 100):
        self.window = window
        self.price_changes: List[float] = []
        self.signed_volumes: List[float] = []
        self.lambda_: float = 0.0

    def on_trade(self, price_change: float, size: int, aggressor: str) -> None:
        signed_vol = size if aggressor == 'BUY' else -size
        self.price_changes.append(price_change)
        self.signed_volumes.append(signed_vol)

        if len(self.price_changes) > self.window:
            self.price_changes.pop(0)
            self.signed_volumes.pop(0)

        if len(self.price_changes) >= 10:
            self._update_lambda()

    def _update_lambda(self) -> None:
        """OLS: ΔP = λ·Q + ε"""
        Q = np.array(self.signed_volumes)
        P = np.array(self.price_changes)
        if np.std(Q) < 1e-9:
            return
        # OLS estimate
        self.lambda_ = np.cov(P, Q)[0, 1] / np.var(Q)

    @property
    def current_lambda(self) -> float:
        return max(0.0, self.lambda_)  # lambda must be non-negative
```

---

## 6. HAWKES PROCESS BRANCHING RATIO

### 6.1 Real-Time Branching Ratio Estimation

```python
class HawkesEstimator:
    """
    Estimates Hawkes process branching ratio n = α/β.
    n → 1 signals endogenous cascade (momentum ignition risk).
    n < 0.5 signals exogenous-driven, mean-reversion opportunity.

    Uses method-of-moments estimation on recent event history.
    Bacry, Mastromatteo & Muzy (2015).
    """

    def __init__(self, window_ms: int = 10000, beta: float = 10.0):
        self.window_ms = window_ms
        self.beta = beta  # decay rate (events/second)
        self.event_times: List[float] = []  # milliseconds
        self.branching_ratio: float = 0.0

    def on_event(self, ts_ms: float) -> None:
        self.event_times.append(ts_ms)
        # Remove old events
        cutoff = ts_ms - self.window_ms
        self.event_times = [t for t in self.event_times if t >= cutoff]
        if len(self.event_times) >= 20:
            self._estimate()

    def _estimate(self) -> None:
        """
        Method of moments: E[N(t)] = μt/(1-n)
        Estimate n from variance/mean ratio of event counts.
        """
        times = np.array(self.event_times)
        if len(times) < 2:
            return

        # Compute inter-arrival times
        inter = np.diff(times)
        if len(inter) < 2:
            return

        # Variance/mean ratio → branching ratio
        mean_inter = np.mean(inter)
        var_inter = np.var(inter)
        if mean_inter < 1e-9:
            return

        # For Hawkes: Var/Mean = 1/(1-n)² → n = 1 - 1/√(Var/Mean)
        ratio = var_inter / (mean_inter ** 2)
        if ratio >= 1:
            n = 1.0 - 1.0 / np.sqrt(max(ratio, 1.001))
        else:
            n = 0.0

        self.branching_ratio = min(max(n, 0.0), 1.0)

    @property
    def is_critical(self) -> bool:
        return self.branching_ratio >= 0.85

    @property
    def regime(self) -> str:
        if self.branching_ratio >= 0.85:
            return 'ENDOGENOUS_CASCADE'
        elif self.branching_ratio >= 0.60:
            return 'MIXED'
        else:
            return 'EXOGENOUS'
```

---

## 7. VPIN COMPUTATION

### 7.1 Volume-Synchronized VPIN

```python
class VPINEstimator:
    """
    Volume-Synchronized Probability of Informed Trading.
    Easley, López de Prado & O'Hara (2012).

    VPIN = |V_buy - V_sell| / V_total
    computed over volume buckets of size V_bucket.
    """

    def __init__(self, bucket_size: int = 1000, n_buckets: int = 50):
        self.bucket_size = bucket_size  # contracts per bucket
        self.n_buckets = n_buckets
        self.current_bucket_buy = 0
        self.current_bucket_sell = 0
        self.current_bucket_vol = 0
        self.bucket_imbalances: List[float] = []
        self.vpin: float = 0.5

    def on_trade(self, size: int, aggressor: str) -> None:
        if aggressor == 'BUY':
            self.current_bucket_buy += size
        else:
            self.current_bucket_sell += size
        self.current_bucket_vol += size

        if self.current_bucket_vol >= self.bucket_size:
            # Close bucket
            imbalance = abs(self.current_bucket_buy - self.current_bucket_sell)
            self.bucket_imbalances.append(imbalance)
            if len(self.bucket_imbalances) > self.n_buckets:
                self.bucket_imbalances.pop(0)

            # Update VPIN
            if self.bucket_imbalances:
                self.vpin = np.mean(self.bucket_imbalances) / self.bucket_size

            # Reset bucket
            self.current_bucket_buy = 0
            self.current_bucket_sell = 0
            self.current_bucket_vol = 0

    @property
    def regime(self) -> str:
        if self.vpin >= 0.7:
            return 'HIGH_INFORMED'  # reduce size, high adverse selection
        elif self.vpin >= 0.4:
            return 'MIXED'
        else:
            return 'LOW_INFORMED'   # increase size, noise trading
```

---

## 8. QUEUE POSITION TRACKER

### 8.1 Priority-Based Queue Tracking

```python
class QueueTracker:
    """
    Tracks queue position for each order using depth_order_priority.
    Enables time-to-fill estimation and queue depletion rate.
    """

    def __init__(self):
        # price → sorted list of (priority, order_id, size)
        self.queues: Dict[float, List[tuple]] = defaultdict(list)
        self.fill_times: Dict[float, List[float]] = defaultdict(list)

    def on_add(self, order_id: str, price: float, size: int,
               priority: int, ts_ms: float) -> None:
        import bisect
        queue = self.queues[price]
        bisect.insort(queue, (priority, order_id, size))

    def on_cancel(self, order_id: str, price: float) -> None:
        self.queues[price] = [
            (p, oid, s) for p, oid, s in self.queues[price]
            if oid != order_id
        ]

    def on_trade(self, price: float, size: int, ts_ms: float) -> None:
        """Remove filled orders from front of queue."""
        queue = self.queues[price]
        remaining = size
        while queue and remaining > 0:
            priority, order_id, order_size = queue[0]
            if order_size <= remaining:
                queue.pop(0)
                remaining -= order_size
            else:
                queue[0] = (priority, order_id, order_size - remaining)
                remaining = 0
        self.fill_times[price].append(ts_ms)

    def queue_ahead(self, order_id: str, price: float) -> int:
        """Contracts ahead of this order in queue."""
        total = 0
        for priority, oid, size in self.queues[price]:
            if oid == order_id:
                break
            total += size
        return total

    def depletion_rate(self, price: float, window_ms: float = 1000) -> float:
        """Contracts filled per millisecond at this price."""
        times = self.fill_times[price]
        if len(times) < 2:
            return 0.0
        recent = [t for t in times if times[-1] - t <= window_ms]
        if len(recent) < 2:
            return 0.0
        # Approximate: assume each fill = 1 contract (simplified)
        return len(recent) / window_ms

    def time_to_fill_ms(self, order_id: str, price: float) -> Optional[float]:
        """Estimated time to fill in milliseconds."""
        ahead = self.queue_ahead(order_id, price)
        rate = self.depletion_rate(price)
        if rate <= 0:
            return None
        return ahead / rate
```

---

## 9. ABSORPTION DETECTION (MBO-NATIVE)

### 9.1 True MBO Absorption Detector

```python
class MBOAbsorptionDetector:
    """
    Detects absorption using true MBO data.
    Absorption = aggressive volume into level + level holds.

    Distinct from iceberg: absorption may use visible size.
    Key signal: aggressive_volume_into_level >> level_retreat.
    """

    MIN_AGGRESSIVE_VOLUME = 50   # minimum contracts to qualify
    HOLD_THRESHOLD = 0.80        # level must retain 80% of size

    def __init__(self):
        self.aggressive_into_level: Dict[float, int] = defaultdict(int)
        self.level_size_at_first_touch: Dict[float, int] = {}
        self.current_level_size: Dict[float, int] = {}
        self.touch_count: Dict[float, int] = defaultdict(int)

    def on_trade(self, price: float, size: int, aggressor: str,
                 book: MBOOrderBook) -> None:
        """Record aggressive volume into a level."""
        # Determine which side is being hit
        if aggressor == 'BUY':
            # Buyer hitting ask — aggressive into ask level
            level_price = price
            level_size = book.asks.get(book.price_to_tick(price),
                                        PriceLevelState(0)).total_size
        else:
            # Seller hitting bid — aggressive into bid level
            level_price = price
            level_size = book.bids.get(book.price_to_tick(price),
                                        PriceLevelState(0)).total_size

        self.aggressive_into_level[level_price] += size
        self.touch_count[level_price] += 1

        if level_price not in self.level_size_at_first_touch:
            self.level_size_at_first_touch[level_price] = level_size
        self.current_level_size[level_price] = level_size

    def evaluate(self, price: float) -> Optional[dict]:
        aggressive = self.aggressive_into_level.get(price, 0)
        if aggressive < self.MIN_AGGRESSIVE_VOLUME:
            return None

        initial_size = self.level_size_at_first_touch.get(price, 0)
        current_size = self.current_level_size.get(price, 0)

        if initial_size == 0:
            return None

        hold_ratio = current_size / initial_size
        if hold_ratio < self.HOLD_THRESHOLD:
            return None  # Level broke — not absorption

        touches = self.touch_count.get(price, 0)
        confidence = min(
            (aggressive / 200) * 0.5 +
            hold_ratio * 0.3 +
            (touches / 5) * 0.2,
            1.0
        )

        return {
            'price': price,
            'aggressive_volume': aggressive,
            'hold_ratio': hold_ratio,
            'touch_count': touches,
            'confidence': confidence,
            'reason_codes': ['aggressive_volume', 'level_held', 'multi_touch'],
        }
```

---

## 10. FEATURE VECTOR CONSTRUCTION

### 10.1 Complete Feature Set for ML Models

```python
def build_feature_vector(book: MBOOrderBook,
                          ofi_1: float, ofi_5: float, ofi_10: float,
                          vpin: float, lambda_: float,
                          branching_ratio: float,
                          recent_trades: List[dict]) -> np.ndarray:
    """
    Build 50-feature vector for ML models.
    All features normalized to [-1, 1] or [0, 1].
    """
    features = []

    # === LOB STATE FEATURES (15) ===
    bb = book.best_bid() or 0
    ba = book.best_ask() or 0
    mid = (bb + ba) / 2 if bb and ba else 0
    spread = (ba - bb) / 0.25 if bb and ba else 0  # in ticks
    mp = book.microprice() or mid

    features.extend([
        (mp - mid) / 0.25 if mid > 0 else 0,  # microprice deviation (ticks)
        min(spread / 10, 1.0),                  # spread (normalized)
        ofi_1,                                   # OFI depth 1
        ofi_5,                                   # OFI depth 5
        ofi_10,                                  # OFI depth 10
    ])

    # Depth asymmetry: bid depth vs ask depth
    bid_depth = sum(l.total_size for l in list(book.bids.values())[:10])
    ask_depth = sum(l.total_size for l in list(book.asks.values())[:10])
    total_depth = bid_depth + ask_depth
    depth_ratio = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0
    features.append(depth_ratio)

    # Level count asymmetry
    bid_levels = len(book.bids)
    ask_levels = len(book.asks)
    level_ratio = (bid_levels - ask_levels) / max(bid_levels + ask_levels, 1)
    features.append(level_ratio)

    # Top-of-book size ratio
    bb_tick = max(book.bids.keys()) if book.bids else None
    ba_tick = min(book.asks.keys()) if book.asks else None
    bb_size = book.bids[bb_tick].total_size if bb_tick else 0
    ba_size = book.asks[ba_tick].total_size if ba_tick else 0
    tob_ratio = (bb_size - ba_size) / max(bb_size + ba_size, 1)
    features.append(tob_ratio)

    # === FLOW FEATURES (10) ===
    features.extend([
        min(vpin, 1.0),                          # VPIN
        min(lambda_ * 100, 1.0),                 # Kyle's lambda (scaled)
        branching_ratio,                          # Hawkes branching ratio
    ])

    # Recent trade aggressor ratio
    if recent_trades:
        buy_vol = sum(t['size'] for t in recent_trades if t['aggressor'] == 'BUY')
        sell_vol = sum(t['size'] for t in recent_trades if t['aggressor'] == 'SELL')
        total_vol = buy_vol + sell_vol
        aggressor_ratio = (buy_vol - sell_vol) / total_vol if total_vol > 0 else 0
        features.append(aggressor_ratio)

        # Trade rate (trades per second)
        if len(recent_trades) >= 2:
            time_span = (recent_trades[-1]['ts_ms'] - recent_trades[0]['ts_ms']) / 1000
            trade_rate = len(recent_trades) / max(time_span, 0.001)
            features.append(min(trade_rate / 100, 1.0))
        else:
            features.append(0.0)

        # Average trade size
        avg_size = total_vol / len(recent_trades)
        features.append(min(avg_size / 100, 1.0))
    else:
        features.extend([0.0, 0.0, 0.0])

    # Pad to consistent length
    while len(features) < 50:
        features.append(0.0)

    return np.array(features[:50], dtype=np.float32)
```

---

## 11. INTEGRITY VALIDATION

### 11.1 Book Integrity Checks

```python
class BookIntegrityValidator:
    """
    Continuous validation of book state.
    Any CRITICAL alert pauses all downstream consumers.
    """

    def validate(self, book: MBOOrderBook, sequence: int,
                 last_sequence: int) -> List[dict]:
        alerts = []

        # Sequence gap
        if sequence != last_sequence + 1:
            alerts.append({
                'severity': 'ERROR',
                'type': 'SEQUENCE_GAP',
                'detail': f'Expected {last_sequence+1}, got {sequence}',
            })

        # Crossed book
        bb = book.best_bid()
        ba = book.best_ask()
        if bb and ba and bb >= ba:
            alerts.append({
                'severity': 'CRITICAL',
                'type': 'CROSSED_BOOK',
                'detail': f'bid={bb} >= ask={ba}',
            })

        # Negative sizes
        for tick, level in book.bids.items():
            if level.total_size < 0:
                alerts.append({
                    'severity': 'CRITICAL',
                    'type': 'NEGATIVE_SIZE',
                    'detail': f'bid level {tick*0.25} size={level.total_size}',
                })

        for tick, level in book.asks.items():
            if level.total_size < 0:
                alerts.append({
                    'severity': 'CRITICAL',
                    'type': 'NEGATIVE_SIZE',
                    'detail': f'ask level {tick*0.25} size={level.total_size}',
                })

        return alerts
```

---

## 12. PERFORMANCE TARGETS

For a production NQ MBO system:

| Component | Target | Notes |
|-----------|--------|-------|
| Order book update | < 1μs | NumPy arrays, no dict in hot path |
| Feature vector build | < 100μs | Pre-allocated arrays |
| Spoof detection | < 500μs | Per cancel event |
| Iceberg evaluation | < 200μs | Per trade event |
| OFI computation | < 50μs | Incremental update |
| Full signal pipeline | < 5ms | All 44+ signals |
| LLM reasoning | < 500ms | Claude Haiku, async |
| Total decision latency | < 10ms | From event to decision |

Python achieves these targets with:
- Pre-allocated NumPy arrays for price levels
- `array.array` for hot-path DOM state
- asyncio event loop (no threading overhead)
- Batch processing of DOM updates (10ms windows)
- Caching of expensive computations (OFI, VPIN)
