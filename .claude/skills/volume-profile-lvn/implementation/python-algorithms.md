# Python Volume Profile & LVN Detection Algorithms

Three approaches cover the full spectrum from fast production baseline to statistically rigorous cluster detection. Pick based on latency budget and signal quality requirements.

---

## Libraries

| Library | Stars | Purpose | Install |
|---------|-------|---------|---------|
| py-market-profile | 389 | Fixed-range VP with HVN/LVN detection | `pip install marketprofile` |
| srl-python-indicators | 25 | Composite profiles, parallel processing | GitHub clone |
| FLOX | — | Rust-backed, streaming VP, per-level delta | `pip install flox` |

`py-market-profile` is the fastest path to a working VP. FLOX is worth evaluating if you need per-level delta alongside volume. `srl-python-indicators` is useful for composite multi-session profiles but requires manual installation.

---

## Approach A: Relative Extrema (scipy.signal.argrelextrema)

Fastest. Production baseline. No distribution assumptions.

```python
from scipy.signal import argrelextrema
import numpy as np
import pandas as pd


def detect_lvn_hvn(volume_profile: pd.Series, order: int = 2):
    """
    Detect HVN and LVN from a volume profile Series.

    Args:
        volume_profile: pd.Series indexed by price level, values are volume.
        order: How many neighbors on each side must be smaller (HVN) or larger (LVN).
               order=2 is the production default for NQ 5-min bars.

    Returns:
        (hvn, lvn): Two pd.Series of detected nodes.
    """
    vals = volume_profile.values

    hvn_idx, = argrelextrema(vals, np.greater, order=order)
    lvn_idx, = argrelextrema(vals, np.less, order=order)

    hvn = volume_profile.iloc[hvn_idx]
    lvn = volume_profile.iloc[lvn_idx]

    return hvn, lvn


def build_volume_profile(
    bars: pd.DataFrame,
    tick_size: float = 0.25,
    prices_per_row: int = 4,
) -> pd.Series:
    """
    Build a volume profile from OHLCV bars.

    Args:
        bars: DataFrame with columns [open, high, low, close, volume].
        tick_size: Minimum price increment. NQ = 0.25.
        prices_per_row: Ticks per bin. 4 = 1.0 per row for NQ.

    Returns:
        pd.Series indexed by price level (float), values are volume.
    """
    row_size = tick_size * prices_per_row
    profile: dict[float, float] = {}

    for _, bar in bars.iterrows():
        lo = round(bar["low"] / row_size) * row_size
        hi = round(bar["high"] / row_size) * row_size
        levels = np.arange(lo, hi + row_size * 0.5, row_size)
        if len(levels) == 0:
            continue
        vol_per_level = bar["volume"] / len(levels)
        for lvl in levels:
            lvl = round(lvl, 4)
            profile[lvl] = profile.get(lvl, 0.0) + vol_per_level

    series = pd.Series(profile).sort_index()
    return series
```

**NQ tuning:**
- `tick_size=0.25` (NQ minimum increment)
- `prices_per_row=4` gives 1.0-point bins, which is the standard for intraday NQ VP
- `order=2` catches most meaningful nodes without over-detecting noise
- Increase `order` to 3-4 for daily profiles where you want only major structural nodes

---

## Approach B: Kernel Density Estimation (KDE)

Smooth, continuous. No bin artifacts. Bandwidth selection is the critical parameter.

```python
from scipy.stats import gaussian_kde
import numpy as np


def kde_volume_profile(
    prices: np.ndarray,
    volumes: np.ndarray,
    n_points: int = 200,
    bw_method: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Estimate volume distribution via KDE.

    Args:
        prices: Array of price levels (one per bar or tick).
        volumes: Array of volumes corresponding to each price.
        n_points: Resolution of the output density curve.
        bw_method: KDE bandwidth. Lower = more peaks, higher = smoother.
                   0.3-0.5 works well for NQ intraday.

    Returns:
        (price_grid, density): Arrays for plotting or LVN detection.
    """
    # Repeat each price by its volume to weight the KDE
    price_samples = np.repeat(prices, volumes.astype(int))

    kde = gaussian_kde(price_samples, bw_method=bw_method)

    price_grid = np.linspace(prices.min(), prices.max(), n_points)
    density = kde(price_grid)

    return price_grid, density


def detect_lvn_from_kde(
    price_grid: np.ndarray,
    density: np.ndarray,
    prominence_threshold: float = 0.15,
) -> np.ndarray:
    """
    Find LVN price levels from a KDE density curve.

    Args:
        price_grid: Price levels from kde_volume_profile.
        density: Density values from kde_volume_profile.
        prominence_threshold: Fraction of max density below which a trough qualifies as LVN.

    Returns:
        Array of LVN price levels.
    """
    from scipy.signal import argrelextrema

    trough_idx, = argrelextrema(density, np.less, order=3)
    max_density = density.max()

    lvn_prices = price_grid[trough_idx[density[trough_idx] < max_density * prominence_threshold]]
    return lvn_prices
```

**Pros:** No bin-edge artifacts. Smooth transitions between nodes. Works well for detecting structural LVNs that span multiple ticks.

**Cons:** Heavier computation than argrelextrema. Bandwidth selection is non-obvious. `bw_method=0.5` is a reasonable starting point for NQ 5-min data; tune by visual inspection.

---

## Approach C: Gaussian Mixture Model (GMM)

Identifies distinct volume clusters. Best for classifying VP shape (D-shape, P-shape, b-shape).

```python
from scipy.optimize import curve_fit
import numpy as np


def gaussian(x, amplitude, mean, std):
    return amplitude * np.exp(-0.5 * ((x - mean) / std) ** 2)


def multi_gaussian(x, *params):
    """Sum of N Gaussians. params = [amp1, mean1, std1, amp2, mean2, std2, ...]"""
    result = np.zeros_like(x, dtype=float)
    for i in range(0, len(params), 3):
        result += gaussian(x, params[i], params[i + 1], params[i + 2])
    return result


def fit_gmm_profile(
    price_grid: np.ndarray,
    density: np.ndarray,
    n_components: int = 3,
) -> list[dict]:
    """
    Fit a sum of Gaussians to a volume profile density curve.

    Args:
        price_grid: Price levels.
        density: Volume density at each price level.
        n_components: Number of Gaussian components. NQ typically needs 2-4 per session.

    Returns:
        List of dicts with keys: mean, std, amplitude, type ('hvn' or 'lvn').
    """
    mid = price_grid.mean()
    spread = price_grid.std()

    # Initial guess: evenly spaced means, equal amplitudes
    p0 = []
    for i in range(n_components):
        mean_guess = mid - spread + (2 * spread * i / max(n_components - 1, 1))
        p0.extend([density.max() / n_components, mean_guess, spread / n_components])

    try:
        popt, _ = curve_fit(multi_gaussian, price_grid, density, p0=p0, maxfev=10000)
    except RuntimeError:
        return []

    components = []
    for i in range(0, len(popt), 3):
        amp, mean, std = popt[i], popt[i + 1], abs(popt[i + 2])
        components.append({
            "amplitude": amp,
            "mean": mean,
            "std": std,
            "type": "hvn" if amp > density.mean() else "lvn",
        })

    return sorted(components, key=lambda c: c["mean"])
```

**NQ notes:** Typically 2-4 clusters per RTH session. A single dominant cluster = D-shape (balanced). Two clusters = P-shape (distribution above) or b-shape (accumulation below). Three or more = complex/trending day.

---

## DevelopingVolumeProfile: Real-Time Streaming

Designed for the async event loop. Handles incremental bar updates without rebuilding from scratch.

```python
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class VolumeNode:
    price: float
    volume: float
    buy_volume: float = 0.0
    sell_volume: float = 0.0

    @property
    def delta(self) -> float:
        return self.buy_volume - self.sell_volume


class DevelopingVolumeProfile:
    """
    Streaming volume profile that updates incrementally.
    Thread-safe for use with janus queue from Rithmic callbacks.
    """

    def __init__(
        self,
        tick_size: float = 0.25,
        prices_per_row: int = 4,
        lvn_threshold: float = 0.30,
        hvn_threshold: float = 1.70,
    ):
        self.tick_size = tick_size
        self.row_size = tick_size * prices_per_row
        self.lvn_threshold = lvn_threshold  # fraction of mean volume
        self.hvn_threshold = hvn_threshold  # fraction of mean volume
        self._nodes: dict[float, VolumeNode] = {}
        self._total_volume: float = 0.0

    def round_to_row(self, price: float) -> float:
        return round(round(price / self.row_size) * self.row_size, 4)

    def add_bar(
        self,
        low: float,
        high: float,
        volume: float,
        buy_volume: float = 0.0,
        sell_volume: float = 0.0,
    ) -> None:
        """Add a completed bar. Distributes volume proportionally across touched levels."""
        lo = self.round_to_row(low)
        hi = self.round_to_row(high)
        levels = np.arange(lo, hi + self.row_size * 0.5, self.row_size)

        if len(levels) == 0:
            return

        vol_per = volume / len(levels)
        buy_per = buy_volume / len(levels)
        sell_per = sell_volume / len(levels)

        for lvl in levels:
            key = round(float(lvl), 4)
            if key not in self._nodes:
                self._nodes[key] = VolumeNode(price=key, volume=0.0)
            node = self._nodes[key]
            node.volume += vol_per
            node.buy_volume += buy_per
            node.sell_volume += sell_per

        self._total_volume += volume

    def get_poc(self) -> Optional[float]:
        """Point of Control: price level with highest volume."""
        if not self._nodes:
            return None
        return max(self._nodes.values(), key=lambda n: n.volume).price

    def get_value_area(self, pct: float = 0.70) -> tuple[float, float]:
        """
        Value Area High and Low containing pct of total volume.

        Returns:
            (vah, val): Value Area High and Low prices.
        """
        if not self._nodes:
            return (0.0, 0.0)

        target = self._total_volume * pct
        poc = self.get_poc()
        sorted_nodes = sorted(self._nodes.values(), key=lambda n: n.volume, reverse=True)

        accumulated = 0.0
        included_prices = []
        for node in sorted_nodes:
            accumulated += node.volume
            included_prices.append(node.price)
            if accumulated >= target:
                break

        return (max(included_prices), min(included_prices))

    def get_lvn(self, order: int = 2) -> list[float]:
        """Return LVN price levels using relative extrema detection."""
        if len(self._nodes) < order * 2 + 1:
            return []

        from scipy.signal import argrelextrema

        prices = sorted(self._nodes.keys())
        volumes = np.array([self._nodes[p].volume for p in prices])

        lvn_idx, = argrelextrema(volumes, np.less, order=order)
        mean_vol = volumes.mean()

        return [
            prices[i] for i in lvn_idx
            if volumes[i] < mean_vol * self.lvn_threshold
        ]

    def get_hvn(self, order: int = 2) -> list[float]:
        """Return HVN price levels using relative extrema detection."""
        if len(self._nodes) < order * 2 + 1:
            return []

        from scipy.signal import argrelextrema

        prices = sorted(self._nodes.keys())
        volumes = np.array([self._nodes[p].volume for p in prices])

        hvn_idx, = argrelextrema(volumes, np.greater, order=order)
        mean_vol = volumes.mean()

        return [
            prices[i] for i in hvn_idx
            if volumes[i] > mean_vol * self.hvn_threshold
        ]

    def snapshot(self) -> dict[float, VolumeNode]:
        """Return a copy of current nodes for signal processing."""
        return dict(self._nodes)
```

---

## Composite Profile

Merge multiple session profiles with configurable weights. RTH gets 2x weight vs overnight.

```python
def composite_profiles(
    profiles: list[DevelopingVolumeProfile],
    weights: Optional[list[float]] = None,
) -> DevelopingVolumeProfile:
    """
    Merge multiple DevelopingVolumeProfile instances into one weighted composite.

    Args:
        profiles: List of session profiles to merge.
        weights: Per-profile weights. Defaults to equal weighting.
                 Typical: [2.0, 1.0] for [RTH, overnight].

    Returns:
        New DevelopingVolumeProfile with merged volume.
    """
    if not profiles:
        raise ValueError("Need at least one profile")

    if weights is None:
        weights = [1.0] * len(profiles)

    if len(weights) != len(profiles):
        raise ValueError("weights length must match profiles length")

    composite = DevelopingVolumeProfile(
        tick_size=profiles[0].tick_size,
        prices_per_row=int(profiles[0].row_size / profiles[0].tick_size),
    )

    for profile, weight in zip(profiles, weights):
        for price, node in profile._nodes.items():
            key = composite.round_to_row(price)
            if key not in composite._nodes:
                composite._nodes[key] = VolumeNode(price=key, volume=0.0)
            composite._nodes[key].volume += node.volume * weight
            composite._nodes[key].buy_volume += node.buy_volume * weight
            composite._nodes[key].sell_volume += node.sell_volume * weight
            composite._total_volume += node.volume * weight

    return composite
```

---

## Session Splitting

Separate RTH and overnight profiles. Overnight inventory detection tells you whether the market opened with a long or short bias.

```python
from datetime import time, datetime
import pytz


RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
EASTERN = pytz.timezone("America/New_York")


def split_session_profiles(
    bars: pd.DataFrame,
    tick_size: float = 0.25,
    prices_per_row: int = 4,
) -> tuple[DevelopingVolumeProfile, DevelopingVolumeProfile]:
    """
    Split bars into RTH and overnight profiles.

    Args:
        bars: DataFrame with DatetimeIndex (UTC) and columns [open, high, low, close, volume].

    Returns:
        (rth_profile, overnight_profile)
    """
    rth = DevelopingVolumeProfile(tick_size, prices_per_row)
    overnight = DevelopingVolumeProfile(tick_size, prices_per_row)

    for ts, bar in bars.iterrows():
        et = ts.astimezone(EASTERN).time()
        profile = rth if RTH_OPEN <= et < RTH_CLOSE else overnight
        profile.add_bar(bar["low"], bar["high"], bar["volume"])

    return rth, overnight


def overnight_inventory(
    overnight_profile: DevelopingVolumeProfile,
    settlement_price: float,
) -> str:
    """
    Classify overnight inventory as long, short, or balanced.

    Args:
        overnight_profile: Overnight session VP.
        settlement_price: Previous day's settlement (4:15 PM ET close for NQ).

    Returns:
        'long', 'short', or 'balanced'
    """
    nodes = overnight_profile.snapshot()
    if not nodes:
        return "balanced"

    vol_above = sum(n.volume for p, n in nodes.items() if p > settlement_price)
    vol_below = sum(n.volume for p, n in nodes.items() if p < settlement_price)
    total = vol_above + vol_below

    if total == 0:
        return "balanced"

    ratio = vol_above / total
    if ratio > 0.60:
        return "long"
    elif ratio < 0.40:
        return "short"
    return "balanced"
```

---

## Bin Size Reference for NQ

| Timeframe | Bin Size | Ticks | Approx Bins/Day |
|-----------|----------|-------|-----------------|
| 1-min | 0.25 | 1 | 64,000 |
| 5-min | 1.0 | 4 | 4,000 |
| 15-min | 2.0-4.0 | 8-16 | 2,000-4,000 |
| Daily | 10.0-25.0 | 40-100 | 500-1,000 |

For signal generation, 5-min bars with 1.0-point bins is the standard. Daily profiles at 10-point bins give clean structural levels without noise.

---

## Rithmic Integration (Async)

Feed DOM ticks from async-rithmic into `DevelopingVolumeProfile` via a janus queue. The profile lives in the async event loop; Rithmic callbacks push bar completions through the queue.

```python
import asyncio
import janus
from async_rithmic import RithmicClient, DataType


async def run_developing_vp(symbol: str = "NQM5"):
    """
    Stream Rithmic bars into a developing volume profile.
    Publishes LVN updates to a downstream signal queue.
    """
    profile = DevelopingVolumeProfile(tick_size=0.25, prices_per_row=4)
    bar_queue: janus.Queue = janus.Queue()

    async def on_bar(bar_data):
        await bar_queue.async_q.put(bar_data)

    client = RithmicClient(
        uri="wss://rituz00100.rithmic.com",
        system_name="Rithmic Test",
        user="YOUR_USER",
        password="YOUR_PASS",
    )

    await client.connect()
    await client.subscribe_bar(symbol, callback=on_bar, bar_type="1min")

    while True:
        bar = await bar_queue.async_q.get()
        profile.add_bar(
            low=bar.low,
            high=bar.high,
            volume=bar.volume,
            buy_volume=getattr(bar, "buy_volume", 0.0),
            sell_volume=getattr(bar, "sell_volume", 0.0),
        )

        lvns = profile.get_lvn()
        poc = profile.get_poc()
        vah, val = profile.get_value_area()

        # Publish to signal engine
        yield {
            "poc": poc,
            "vah": vah,
            "val": val,
            "lvns": lvns,
            "total_volume": profile._total_volume,
        }
```

The `janus.Queue` is the correct bridge when Rithmic callbacks arrive on a background thread and the signal engine runs in the asyncio event loop. Do not use `asyncio.Queue` directly from a non-async callback.
