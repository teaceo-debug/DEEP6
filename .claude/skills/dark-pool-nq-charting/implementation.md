# Dark Pool NQ Charting — Python & Pine Script Implementation

All code. No theory. For theory, see `foundations.md`, `microstructure-theory.md`, and `quantitative-models.md`.

---

## 1. Dark Pool Level Clustering (Premium-Weighted)

The core algorithm. Sorts prints by price, merges adjacent prints within `merge_pct` of the running cluster center (weighted by premium), then finalizes each cluster with aggression scoring.

```python
import numpy as np
import pandas as pd
from scipy.stats import norm


def cluster_dark_pool_prints(prints: list[dict], merge_pct: float = 0.005) -> list[dict]:
    """
    Cluster dark pool prints into institutional price levels.

    Args:
        prints: List of {price, size, premium, executed_at, nbbo_bid, nbbo_ask}
        merge_pct: Merge threshold as fraction (0.005 = 0.5%)

    Returns: List of {center_price, total_volume, total_premium, print_count, aggression}
    """
    if not prints:
        return []

    # Sort by price
    sorted_prints = sorted(prints, key=lambda p: p['price'])

    clusters = []
    current_cluster = {
        'prices': [sorted_prints[0]['price']],
        'volumes': [sorted_prints[0]['size']],
        'premiums': [sorted_prints[0]['premium']],
        'aggression_scores': []
    }

    # Classify aggression for first print
    p = sorted_prints[0]
    current_cluster['aggression_scores'].append(
        1 if p['price'] > p['nbbo_ask'] else (-1 if p['price'] < p['nbbo_bid'] else 0)
    )

    for p in sorted_prints[1:]:
        cluster_center = np.average(
            current_cluster['prices'],
            weights=current_cluster['premiums']
        )

        if abs(p['price'] - cluster_center) / cluster_center <= merge_pct:
            # Add to current cluster
            current_cluster['prices'].append(p['price'])
            current_cluster['volumes'].append(p['size'])
            current_cluster['premiums'].append(p['premium'])
            current_cluster['aggression_scores'].append(
                1 if p['price'] > p['nbbo_ask'] else (-1 if p['price'] < p['nbbo_bid'] else 0)
            )
        else:
            # Finalize current cluster, start new one
            clusters.append(_finalize_cluster(current_cluster))
            current_cluster = {
                'prices': [p['price']],
                'volumes': [p['size']],
                'premiums': [p['premium']],
                'aggression_scores': [
                    1 if p['price'] > p['nbbo_ask'] else (-1 if p['price'] < p['nbbo_bid'] else 0)
                ]
            }

    clusters.append(_finalize_cluster(current_cluster))

    # Sort by total premium descending — highest conviction levels first
    return sorted(clusters, key=lambda c: c['total_premium'], reverse=True)


def _finalize_cluster(cluster: dict) -> dict:
    center = np.average(cluster['prices'], weights=cluster['premiums'])
    return {
        'center_price': round(center, 2),
        'total_volume': sum(cluster['volumes']),
        'total_premium': sum(cluster['premiums']),
        'print_count': len(cluster['prices']),
        'aggression': sum(cluster['aggression_scores']) / len(cluster['aggression_scores']),
        'price_range': (min(cluster['prices']), max(cluster['prices']))
    }
```

**Aggression interpretation**:
- `aggression > 0.3`: net buying pressure (prints above ask)
- `aggression < -0.3`: net selling pressure (prints below bid)
- `-0.3 to 0.3`: neutral / midpoint execution

---

## 2. DBSCAN Alternative Clustering

Use when you don't want to tune `merge_pct` manually. DBSCAN auto-detects cluster count and handles irregular spacing. Slower than the greedy merge above but more robust on noisy data.

```python
from sklearn.cluster import DBSCAN


def dbscan_dark_pool_clusters(
    prints: list[dict],
    eps_pct: float = 0.003,
    min_samples: int = 3
) -> list[dict]:
    """
    DBSCAN-based clustering. Auto-detects number of clusters.

    Args:
        prints: List of {price, premium, ...}
        eps_pct: Neighborhood radius as fraction of mean price (0.003 = 0.3%)
        min_samples: Minimum prints to form a cluster (noise rejection)

    Returns: List of cluster dicts sorted by total_premium descending.
             Noise points (label=-1) are discarded.
    """
    if len(prints) < min_samples:
        return []

    prices = np.array([p['price'] for p in prints]).reshape(-1, 1)
    premiums = np.array([p['premium'] for p in prints])

    # Scale eps to current price level
    mean_price = float(np.mean(prices))
    eps_abs = mean_price * eps_pct

    clustering = DBSCAN(eps=eps_abs, min_samples=min_samples).fit(prices)

    labels = clustering.labels_
    unique_labels = set(labels) - {-1}  # Discard noise

    clusters = []
    for label in unique_labels:
        mask = labels == label
        cluster_prices = prices[mask].flatten()
        cluster_premiums = premiums[mask]

        clusters.append({
            'center_price': float(np.average(cluster_prices, weights=cluster_premiums)),
            'total_premium': float(cluster_premiums.sum()),
            'print_count': int(mask.sum()),
            'price_range': (float(cluster_prices.min()), float(cluster_prices.max()))
        })

    return sorted(clusters, key=lambda c: c['total_premium'], reverse=True)
```

**When to use DBSCAN vs greedy merge**:
- Greedy merge: faster, predictable, good for real-time streaming
- DBSCAN: better for batch analysis, handles multi-modal distributions, no manual threshold tuning

---

## 3. Kernel Density Estimation

Produces a continuous density curve over the price range. Useful for visualizing where institutional interest is concentrated without committing to discrete levels. Good for dashboard heatmaps.

```python
from sklearn.neighbors import KernelDensity
from scipy.signal import find_peaks


def dark_pool_kde(
    prints: list[dict],
    bandwidth: float = 0.5,
    n_points: int = 500
) -> dict:
    """
    Smooth dark pool prints into a continuous density curve.

    Args:
        prints: List of {price, premium}
        bandwidth: KDE bandwidth in price units (0.5 = half a dollar)
        n_points: Resolution of the output grid

    Returns: {prices, density, peak_prices, peak_densities}
    """
    prices = np.array([p['price'] for p in prints]).reshape(-1, 1)
    weights = np.array([p['premium'] for p in prints])

    # Premium-weighted KDE
    kde = KernelDensity(kernel='gaussian', bandwidth=bandwidth)
    kde.fit(prices, sample_weight=weights)

    # Evaluate on uniform grid
    price_grid = np.linspace(float(prices.min()), float(prices.max()), n_points).reshape(-1, 1)
    log_density = kde.score_samples(price_grid)
    density = np.exp(log_density)

    # Find peaks above 75th percentile
    peaks, _ = find_peaks(density, height=np.percentile(density, 75))

    return {
        'prices': price_grid.flatten(),
        'density': density,
        'peak_prices': price_grid[peaks].flatten(),
        'peak_densities': density[peaks]
    }
```

**Bandwidth guidance for NQ proxy (QQQ)**:
- `bandwidth=0.5`: fine-grained, many peaks, good for intraday
- `bandwidth=1.0`: medium, good for daily levels
- `bandwidth=2.0`: coarse, only major institutional zones

---

## 4. QQQ to NQ Conversion

NQ has no direct dark pool data. Convert QQQ levels using the live price ratio. The ratio drifts intraday as QQQ and NQ diverge slightly, so refresh it at least every 5 minutes during market hours.

```python
async def convert_qqq_levels_to_nq(
    uw_client,
    dp_levels: list[dict],
    nq_price: float | None = None
) -> list[dict]:
    """
    Convert QQQ dark pool levels to NQ equivalents using live ratio.

    Args:
        uw_client: Unusual Whales async client
        dp_levels: Clustered QQQ levels from cluster_dark_pool_prints()
        nq_price: Current NQ price. If None, must be provided externally
                  (from Rithmic or TradingView MCP quote_get).

    Returns: dp_levels with nq_price, qqq_price, and conversion_ratio added.
    """
    # Get current QQQ price
    qqq_quote = await uw_client._get("/stock/QQQ/last-stock-state")
    qqq_price = float(qqq_quote['data']['last_price'])

    if nq_price is None:
        raise ValueError(
            "nq_price must be provided. "
            "Get it from Rithmic: await rithmic_client.get_last_price('NQ') "
            "or TradingView MCP: quote_get(symbol='NQ1!')"
        )

    ratio = nq_price / qqq_price

    nq_levels = []
    for level in dp_levels:
        nq_levels.append({
            **level,
            'nq_price': round(level['center_price'] * ratio, 2),
            'qqq_price': level['center_price'],
            'conversion_ratio': ratio
        })

    return nq_levels
```

**Ratio stability**: The QQQ/NQ ratio is stable over hours but drifts ~0.1-0.3% intraday. For levels used as S/R, this drift is negligible. For precise entry triggers, refresh the ratio before each use.

---

## 5. Full Pipeline: Unusual Whales to NQ Levels

End-to-end function. Fetches QQQ prints, clusters, filters by z-score, converts to NQ, and aggregates top-5 component signals for directional bias.

```python
async def get_nq_dark_pool_levels(
    uw_client,
    nq_price: float,
    lookback_days: int = 5,
    min_premium: int = 100_000,
    z_threshold: float = 1.5
) -> dict:
    """
    End-to-end: fetch QQQ dark pool -> cluster -> convert to NQ levels.

    Args:
        uw_client: Unusual Whales async client
        nq_price: Current NQ futures price (from Rithmic or TradingView)
        lookback_days: Days of dark pool history to fetch
        min_premium: Minimum print premium to include (filters noise)
        z_threshold: Z-score threshold for significant levels

    Returns: {nq_levels, component_signals, bullish_components, nq_bias}
    """
    # 1. Fetch QQQ dark pool prints
    prints_response = await uw_client.get_darkpool_ticker("QQQ", min_premium=min_premium)
    prints = prints_response.get('data', [])

    if not prints:
        return {'nq_levels': [], 'component_signals': {}, 'bullish_components': 0, 'nq_bias': 'neutral'}

    # 2. Cluster into levels
    levels = cluster_dark_pool_prints(prints, merge_pct=0.005)

    # 3. Z-score filtering — keep only statistically significant levels
    volumes = [l['total_volume'] for l in levels]
    mean_vol = np.mean(volumes)
    std_vol = np.std(volumes) or 1.0  # Guard against zero std

    significant = [
        {**l, 'z_score': (l['total_volume'] - mean_vol) / std_vol}
        for l in levels
        if (l['total_volume'] - mean_vol) / std_vol > z_threshold
    ]

    # 4. Convert to NQ
    nq_levels = await convert_qqq_levels_to_nq(uw_client, significant, nq_price=nq_price)

    # 5. Top-5 component aggregation for directional bias
    components = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    component_signals = {}

    for ticker in components:
        try:
            component_data = await uw_client.get_darkpool_ticker(ticker, min_premium=50_000)
            ticker_prints = component_data.get('data', [])

            buy_count = sum(
                1 for p in ticker_prints
                if float(p.get('price', 0)) > float(p.get('nbbo_ask', 0))
            )
            sell_count = sum(
                1 for p in ticker_prints
                if float(p.get('price', 0)) < float(p.get('nbbo_bid', 0))
            )
            total = len(ticker_prints) or 1

            component_signals[ticker] = {
                'aggression': (buy_count - sell_count) / total,
                'print_count': total
            }
        except Exception:
            component_signals[ticker] = {'aggression': 0.0, 'print_count': 0}

    bullish_count = sum(1 for s in component_signals.values() if s['aggression'] > 0.1)

    return {
        'nq_levels': nq_levels,
        'component_signals': component_signals,
        'bullish_components': bullish_count,
        'nq_bias': 'bullish' if bullish_count >= 3 else ('bearish' if bullish_count <= 1 else 'neutral')
    }
```

---

## 6. Dark Pool Level Tracker Class

Stateful tracker for live sessions. Maintains a rolling window of prints, tracks which levels have been tested, and computes GEX confluence.

```python
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class DarkPoolLevel:
    center_price: float
    total_volume: int
    total_premium: float
    print_count: int
    aggression: float
    z_score: float
    created_at: datetime
    tested: bool = False
    test_count: int = 0
    last_tested_at: datetime | None = None
    gex_aligned: bool = False


class DarkPoolLevelTracker:
    """
    Stateful dark pool level tracker for live trading sessions.

    Maintains a rolling window of prints, re-clusters on update,
    tracks level tests, and computes GEX confluence.
    """

    def __init__(
        self,
        merge_pct: float = 0.005,
        z_threshold: float = 1.5,
        max_age_hours: int = 48,
        max_prints: int = 10_000
    ):
        self.merge_pct = merge_pct
        self.z_threshold = z_threshold
        self.max_age = timedelta(hours=max_age_hours)
        self._prints: deque[dict] = deque(maxlen=max_prints)
        self._levels: list[DarkPoolLevel] = []
        self._last_cluster_time: datetime | None = None
        self._cluster_interval = timedelta(minutes=5)

    def update(self, print_data: dict) -> None:
        """
        Add a new dark pool print and re-cluster if interval has elapsed.

        Args:
            print_data: {price, size, premium, executed_at, nbbo_bid, nbbo_ask}
        """
        self._prints.append(print_data)

        now = datetime.utcnow()
        if (
            self._last_cluster_time is None
            or now - self._last_cluster_time >= self._cluster_interval
        ):
            self._recluster()
            self._last_cluster_time = now

    def _recluster(self) -> None:
        """Re-run clustering on current print window."""
        # Prune old prints
        cutoff = datetime.utcnow() - self.max_age
        active_prints = [
            p for p in self._prints
            if datetime.fromisoformat(p['executed_at']) > cutoff
        ]

        if not active_prints:
            self._levels = []
            return

        raw_clusters = cluster_dark_pool_prints(active_prints, self.merge_pct)

        # Z-score filter
        volumes = [c['total_volume'] for c in raw_clusters]
        mean_vol = np.mean(volumes)
        std_vol = np.std(volumes) or 1.0

        new_levels = []
        for c in raw_clusters:
            z = (c['total_volume'] - mean_vol) / std_vol
            if z > self.z_threshold:
                # Preserve test state from existing levels if price is close
                existing = self._find_existing_level(c['center_price'])
                new_levels.append(DarkPoolLevel(
                    center_price=c['center_price'],
                    total_volume=c['total_volume'],
                    total_premium=c['total_premium'],
                    print_count=c['print_count'],
                    aggression=c['aggression'],
                    z_score=z,
                    created_at=existing.created_at if existing else datetime.utcnow(),
                    tested=existing.tested if existing else False,
                    test_count=existing.test_count if existing else 0,
                    last_tested_at=existing.last_tested_at if existing else None,
                    gex_aligned=existing.gex_aligned if existing else False
                ))

        self._levels = new_levels

    def _find_existing_level(self, price: float, tolerance: float = 0.003) -> DarkPoolLevel | None:
        """Find an existing level within tolerance of the given price."""
        for level in self._levels:
            if abs(level.center_price - price) / price <= tolerance:
                return level
        return None

    def get_significant_levels(self, z_threshold: float | None = None) -> list[DarkPoolLevel]:
        """
        Return levels above z_threshold, sorted by z-score descending.

        Args:
            z_threshold: Override instance threshold. None uses instance default.
        """
        threshold = z_threshold if z_threshold is not None else self.z_threshold
        return sorted(
            [l for l in self._levels if l.z_score >= threshold],
            key=lambda l: l.z_score,
            reverse=True
        )

    def get_confluence_with_gex(
        self,
        gex_data: dict,
        gamma_flip: float,
        proximity_pct: float = 0.005
    ) -> list[DarkPoolLevel]:
        """
        Mark levels that align with GEX walls or the gamma flip.

        Args:
            gex_data: {call_walls: [price, ...], put_walls: [price, ...]}
            gamma_flip: Gamma flip price level
            proximity_pct: How close a level must be to a GEX wall (0.005 = 0.5%)

        Returns: Levels with gex_aligned=True set in place.
        """
        gex_prices = (
            gex_data.get('call_walls', [])
            + gex_data.get('put_walls', [])
            + [gamma_flip]
        )

        for level in self._levels:
            level.gex_aligned = any(
                abs(level.center_price - gex_price) / level.center_price <= proximity_pct
                for gex_price in gex_prices
                if gex_price > 0
            )

        return [l for l in self._levels if l.gex_aligned]

    def mark_tested(self, price: float, tolerance_pct: float = 0.002) -> list[DarkPoolLevel]:
        """
        Mark levels as tested when price trades through them.

        Args:
            price: Current market price
            tolerance_pct: How close price must be to mark as tested

        Returns: List of levels that were just marked tested.
        """
        newly_tested = []
        for level in self._levels:
            if abs(level.center_price - price) / level.center_price <= tolerance_pct:
                level.tested = True
                level.test_count += 1
                level.last_tested_at = datetime.utcnow()
                newly_tested.append(level)
        return newly_tested

    def get_fresh_levels(self) -> list[DarkPoolLevel]:
        """
        Return significant levels that have NOT been tested yet.
        These are the highest-value S/R candidates.
        """
        return [l for l in self.get_significant_levels() if not l.tested]

    def get_level_summary(self) -> dict:
        """Summary stats for logging and dashboard."""
        levels = self._levels
        return {
            'total_levels': len(levels),
            'significant_levels': len(self.get_significant_levels()),
            'fresh_levels': len(self.get_fresh_levels()),
            'gex_aligned': sum(1 for l in levels if l.gex_aligned),
            'bullish_levels': sum(1 for l in levels if l.aggression > 0.3),
            'bearish_levels': sum(1 for l in levels if l.aggression < -0.3),
            'total_prints': len(self._prints)
        }
```

---

## 7. Pine Script: Dark Pool Level Overlay

Manual input version. You paste QQQ dark pool levels from the Python pipeline into the indicator inputs. The indicator converts them to NQ using the live QQQ/NQ ratio and draws horizontal lines with width proportional to premium.

```pine
//@version=6
indicator("NQ Dark Pool Levels", overlay=true, max_lines_count=50, max_labels_count=50)

// ─── Inputs ───────────────────────────────────────────────────────────────────

var string GRP_LEVELS = "Dark Pool Levels (QQQ prices)"
var string GRP_STYLE  = "Style"

// Up to 10 manual levels. Extend as needed.
l1_price   = input.float(0.0, "Level 1 QQQ Price",   group=GRP_LEVELS, inline="l1")
l1_premium = input.float(0.0, "Level 1 Premium ($M)", group=GRP_LEVELS, inline="l1")
l2_price   = input.float(0.0, "Level 2 QQQ Price",   group=GRP_LEVELS, inline="l2")
l2_premium = input.float(0.0, "Level 2 Premium ($M)", group=GRP_LEVELS, inline="l2")
l3_price   = input.float(0.0, "Level 3 QQQ Price",   group=GRP_LEVELS, inline="l3")
l3_premium = input.float(0.0, "Level 3 Premium ($M)", group=GRP_LEVELS, inline="l3")
l4_price   = input.float(0.0, "Level 4 QQQ Price",   group=GRP_LEVELS, inline="l4")
l4_premium = input.float(0.0, "Level 4 Premium ($M)", group=GRP_LEVELS, inline="l4")
l5_price   = input.float(0.0, "Level 5 QQQ Price",   group=GRP_LEVELS, inline="l5")
l5_premium = input.float(0.0, "Level 5 Premium ($M)", group=GRP_LEVELS, inline="l5")

line_extend = input.bool(true, "Extend Lines Right", group=GRP_STYLE)
show_labels = input.bool(true, "Show Labels",        group=GRP_STYLE)
dp_color    = input.color(color.new(color.purple, 20), "Level Color", group=GRP_STYLE)

// ─── QQQ → NQ Conversion ─────────────────────────────────────────────────────

qqq_close = request.security("NASDAQ:QQQ", timeframe.period, close)
ratio     = close / qqq_close  // NQ / QQQ live ratio

// ─── Draw Level ───────────────────────────────────────────────────────────────

draw_dp_level(qqq_price, premium_m) =>
    if qqq_price <= 0.0
        na
    nq_price = qqq_price * ratio
    lw       = math.max(1, math.min(4, math.round(premium_m)))  // 1-4px width
    ext      = line_extend ? extend.right : extend.none

    l = line.new(
         bar_index - 100, nq_price,
         bar_index,       nq_price,
         color=dp_color, width=lw, style=line.style_solid, extend=ext
    )

    if show_labels
        label.new(
             bar_index, nq_price,
             text  = "DP " + str.tostring(nq_price, "#.##") +
                     " ($" + str.tostring(premium_m, "#.#") + "M)",
             color = color.new(color.purple, 75),
             textcolor = color.white,
             style = label.style_label_left,
             size  = size.small
        )

// ─── Plot All Levels ──────────────────────────────────────────────────────────

if barstate.islast
    draw_dp_level(l1_price, l1_premium)
    draw_dp_level(l2_price, l2_premium)
    draw_dp_level(l3_price, l3_premium)
    draw_dp_level(l4_price, l4_premium)
    draw_dp_level(l5_price, l5_premium)
```

**Usage**: Run the Python pipeline, take the top 5 `nq_levels` by `total_premium`, enter the `qqq_price` and `total_premium / 1e6` for each level into the indicator inputs.

---

## 8. Data Pipeline Architecture

```
Unusual Whales API (REST + WebSocket)
    |
    v
AsyncClient (httpx, rate limited, circuit breaker)
    |
    v
Dark Pool Print Ingestion (QQQ + top-5 components: AAPL, MSFT, NVDA, GOOGL, AMZN)
    |
    v
Clustering Engine (premium-weighted greedy merge OR DBSCAN)
    |
    v
Z-Score Significance Filter (threshold: 1.5 default, 2.0 for high-conviction only)
    |
    v
QQQ -> NQ Conversion (live ratio, refresh every 5 min)
    |
    v
GEX Confluence Check (FlashAlpha call/put walls + gamma flip proximity)
    |
    v
NQ Level Output (center_price, total_premium, aggression, z_score, gex_aligned)
    |
    +---> TradingView (Pine Script overlay via manual input or MCP injection)
    |
    +---> Dashboard (Lightweight Charts horizontal lines via WebSocket push)
    |
    +---> DarkPoolLevelTracker (stateful, tracks tests, fresh levels)
```

**Refresh cadence**:
- Full re-fetch from UW API: every 15 minutes during market hours
- Re-cluster from cached prints: every 5 minutes
- QQQ/NQ ratio update: every 5 minutes
- GEX confluence check: on each re-cluster

---

## 9. Real-Time Dark Pool Monitor via WebSocket

Subscribe to the Unusual Whales `off-lit-trades` channel and feed prints directly into `DarkPoolLevelTracker`. Uses the queue + processor pattern from `unusual-whales/websocket.md`.

```python
import asyncio
import json
from datetime import datetime

import websockets


class RealTimeDarkPoolMonitor:
    """
    Subscribes to Unusual Whales WebSocket off-lit-trades channel
    and maintains live dark pool levels via DarkPoolLevelTracker.
    """

    WS_URL = "wss://api.unusualwhales.com/ws"

    def __init__(
        self,
        api_key: str,
        tracker: DarkPoolLevelTracker,
        symbols: list[str] | None = None,
        min_premium: float = 100_000
    ):
        self.api_key = api_key
        self.tracker = tracker
        self.symbols = symbols or ["QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
        self.min_premium = min_premium
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10_000)
        self._running = False

    async def start(self) -> None:
        """Start the WebSocket listener and processor concurrently."""
        self._running = True
        await asyncio.gather(
            self._listen(),
            self._process()
        )

    async def stop(self) -> None:
        self._running = False

    async def _listen(self) -> None:
        """WebSocket listener. Reconnects on disconnect."""
        while self._running:
            try:
                async with websockets.connect(
                    self.WS_URL,
                    extra_headers={"Authorization": f"Bearer {self.api_key}"},
                    ping_interval=30,
                    ping_timeout=10
                ) as ws:
                    # Subscribe to off-lit-trades for each symbol
                    for symbol in self.symbols:
                        await ws.send(json.dumps({
                            "action": "subscribe",
                            "channel": "off-lit-trades",
                            "symbol": symbol
                        }))

                    async for raw_message in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_message)
                            await self._queue.put(msg)
                        except json.JSONDecodeError:
                            continue

            except (websockets.ConnectionClosed, OSError) as e:
                if self._running:
                    # Exponential backoff: 1s, 2s, 4s, max 30s
                    await asyncio.sleep(min(30, 2 ** getattr(self, '_retry_count', 0)))
                    self._retry_count = getattr(self, '_retry_count', 0) + 1
            else:
                self._retry_count = 0

    async def _process(self) -> None:
        """Drain the queue and feed prints into the tracker."""
        while self._running:
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                self._handle_message(msg)
            except Exception:
                pass  # Never let a bad print crash the processor
            finally:
                self._queue.task_done()

    def _handle_message(self, msg: dict) -> None:
        """Parse a raw WebSocket message and update the tracker."""
        # UW off-lit-trades message shape:
        # {type: "off-lit-trade", data: {symbol, price, size, premium,
        #  executed_at, nbbo_bid, nbbo_ask, venue, ...}}
        if msg.get('type') != 'off-lit-trade':
            return

        data = msg.get('data', {})
        premium = float(data.get('premium', 0))

        if premium < self.min_premium:
            return  # Filter noise below threshold

        print_data = {
            'price':       float(data['price']),
            'size':        int(data['size']),
            'premium':     premium,
            'executed_at': data.get('executed_at', datetime.utcnow().isoformat()),
            'nbbo_bid':    float(data.get('nbbo_bid', data['price'])),
            'nbbo_ask':    float(data.get('nbbo_ask', data['price'])),
            'symbol':      data.get('symbol', ''),
            'venue':       data.get('venue', '')
        }

        self.tracker.update(print_data)


# ─── Usage ────────────────────────────────────────────────────────────────────

async def main():
    tracker = DarkPoolLevelTracker(
        merge_pct=0.005,
        z_threshold=1.5,
        max_age_hours=48
    )

    monitor = RealTimeDarkPoolMonitor(
        api_key="YOUR_UW_API_KEY",
        tracker=tracker,
        symbols=["QQQ", "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        min_premium=100_000
    )

    # Run monitor in background, poll levels in foreground
    async def poll_levels():
        while True:
            await asyncio.sleep(60)
            summary = tracker.get_level_summary()
            fresh = tracker.get_fresh_levels()
            print(f"Levels: {summary}")
            for level in fresh[:5]:
                print(f"  NQ proxy: {level.center_price:.2f} | "
                      f"z={level.z_score:.1f} | "
                      f"aggression={level.aggression:+.2f} | "
                      f"GEX aligned={level.gex_aligned}")

    await asyncio.gather(
        monitor.start(),
        poll_levels()
    )


if __name__ == "__main__":
    asyncio.run(main())
```

**Queue sizing**: `maxsize=10_000` handles burst traffic during high-volatility events. At normal dark pool print rates (~50-200 prints/minute for QQQ), the queue stays near-empty. During FOMC or earnings, it can spike to 500+ prints/minute. The 10,000 cap prevents unbounded memory growth.

**Reconnection**: The listener uses exponential backoff capped at 30 seconds. The processor keeps running during reconnects, draining whatever is in the queue. No prints are lost during brief disconnects.

---

## Integration Points

| Component | How to Connect |
|-----------|---------------|
| Rithmic (NQ price for ratio) | `await rithmic_client.get_last_price("NQ")` in `convert_qqq_levels_to_nq()` |
| FlashAlpha GEX | Pass `{call_walls, put_walls}` to `tracker.get_confluence_with_gex()` |
| TradingView MCP | Use `pine_set_source` to inject the Pine overlay, then `pine_smart_compile` |
| Dashboard (Lightweight Charts) | Push `tracker.get_significant_levels()` via FastAPI WebSocket on each re-cluster |
| DEEP6 signal engine | Call `tracker.get_fresh_levels()` in the signal scoring loop; GEX-aligned fresh levels score +2 |
