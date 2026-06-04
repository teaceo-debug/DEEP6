# DEEP6 Existing VP Infrastructure & Extension Points

Before adding any new VP or LVN feature, check this map. The existing engine covers more ground than it appears. Duplicating it creates two sources of truth and breaks the signal weighting system.

---

## Existing Engine Inventory

| Engine | File | Purpose |
|--------|------|---------|
| SessionProfile | `deep6/engines/volume_profile.py` | Cumulative session VP from FootprintBar, LVN/HVN detection, zone lifecycle FSM (VPRO-01..08) |
| POCEngine | `deep6/engines/poc.py` | 8 POC/VA signal variants (POC-01..08), migration tracking |
| E6VPContextEngine | `deep6/engines/vp_context_engine.py` | Unified macro context: POC + SessionProfile + GEX + ZoneRegistry |
| E7MLQualityEngine | `deep6/engines/vp_context_engine.py` | Dynamic quality multiplier for Phase 9 weights |
| ZoneRegistry | `deep6/engines/zone_registry.py` | Active zone management, confluence scoring, lifecycle events |
| VPContextDetector | `deep6v2/signals/engines/vp_context.py` | v2 VAH/VAL/POC proximity + LVNZone FSM scaffold |

The v1 engines (`deep6/engines/`) are the production path. The v2 detector (`deep6v2/`) is the scaffold for the next architecture iteration. New features should target v2 unless the change is a bug fix in v1.

---

## Configuration

From `signal_config.py`:

```python
@dataclass
class VolumeProfileConfig:
    lvn_threshold: float = 0.30      # Fraction of mean volume; below = LVN
    hvn_threshold: float = 1.70      # Fraction of mean volume; above = HVN
    min_zone_ticks: int = 2          # Minimum zone width in ticks
    max_zones: int = 20              # Maximum active zones in ZoneRegistry
    tick_size: float = 0.25          # NQ minimum increment
    prices_per_row: int = 4          # 1.0-point bins (4 ticks)
    value_area_pct: float = 0.70     # Standard 70% value area


@dataclass
class POCConfig:
    va_pct: float = 0.70             # Value area percentage
    poc_gap_ticks: int = 4           # Minimum gap between POC and current price to signal
    migration_window: int = 20       # Bars to track POC migration direction


# Zone scoring weights (must sum to 1.0)
ZONE_SCORING_WEIGHTS = {
    "type_weight": 0.35,    # LVN vs HVN vs structural
    "recency": 0.25,        # How recently the zone formed
    "touches": 0.25,        # Number of price touches without breaking
    "defense": 0.15,        # Volume defense events at the zone
}
```

Do not change these defaults without updating the corresponding test fixtures in `tests/test_volume_profile.py`. The VPRO-xx tests are parameterized against these values.

---

## Zone Lifecycle FSM

Zones transition through a defined state machine. Each state has specific entry conditions and exit triggers.

```
CREATED --> DEFENDED --> BROKEN --> FLIPPED --> INVALIDATED
    |                      |
    +-------> INVALIDATED  +-------> INVALIDATED
```

| State | Entry Condition | Exit Trigger |
|-------|----------------|--------------|
| CREATED | LVN/HVN detected in profile | First price touch |
| DEFENDED | Price touches zone, volume defense event fires | Price closes through zone |
| BROKEN | Price closes through zone without defense | Price returns and holds |
| FLIPPED | Broken zone holds as support/resistance on retest | Price closes through again |
| INVALIDATED | Zone age exceeds decay threshold, or price closes through FLIPPED zone | Terminal state |

```python
# From deep6/engines/zone_registry.py (reference, do not modify)
class ZoneState(Enum):
    CREATED = "created"
    DEFENDED = "defended"
    BROKEN = "broken"
    FLIPPED = "flipped"
    INVALIDATED = "invalidated"


@dataclass
class Zone:
    price: float
    zone_type: ZoneType          # LVN, HVN, STRUCTURAL
    state: ZoneState
    created_bar: int
    touch_count: int = 0
    defense_count: int = 0
    score: float = 0.0

    def is_active(self) -> bool:
        return self.state not in (ZoneState.INVALIDATED,)
```

Zones persist across sessions with a decay function. A zone that hasn't been touched in 20+ bars loses score weight but remains active until explicitly invalidated.

---

## Signal Variants

### VPRO-01..08 (SessionProfile signals)

| Signal | Condition |
|--------|-----------|
| VPRO-01 | Price enters LVN from below (bullish pass-through risk) |
| VPRO-02 | Price enters LVN from above (bearish pass-through risk) |
| VPRO-03 | Price stalls at LVN (potential reversal) |
| VPRO-04 | Price exits LVN with volume confirmation |
| VPRO-05 | HVN defense: price touches HVN, volume spikes, price rejects |
| VPRO-06 | HVN break: price closes through HVN on above-average volume |
| VPRO-07 | POC magnet: price within poc_gap_ticks of POC, trending toward it |
| VPRO-08 | Value area boundary: price at VAH or VAL with rejection candle |

### POC-01..08 (POCEngine signals)

| Signal | Condition |
|--------|-----------|
| POC-01 | POC cross bullish (price crosses POC from below) |
| POC-02 | POC cross bearish |
| POC-03 | POC migration bullish (POC moving up over migration_window bars) |
| POC-04 | POC migration bearish |
| POC-05 | Price above POC + above VAH (strong bullish context) |
| POC-06 | Price below POC + below VAL (strong bearish context) |
| POC-07 | Price inside value area, approaching POC |
| POC-08 | POC unchanged for 10+ bars (pinning, low conviction) |

---

## NinjaScript Counterparts

These are the NT8 equivalents of the Python engines. They exist for reference and visual verification in NinjaTrader, not for production signal generation.

| File | Purpose |
|------|---------|
| `VPLowTFLVNLevels.cs` | Multi-TF LVN levels from 1-min bars (Daily/Weekly/Monthly profiles) |
| `DEEP6LVNRadarStrategy.cs` | Self-contained LVN cross strategy with Depth Radar integration |
| `DEEP6LowVolumeNodeTool.cs` | Interactive range-based VP drawing tool for manual analysis |

These files are in `NinjaTrader/Custom/Indicators/` and `NinjaTrader/Custom/Strategies/`. They are not part of the Python signal pipeline. Do not port logic from them without verifying it matches the Python implementation.

---

## What Exists vs What's Missing

### Exists

- LVN/HVN detection via relative extrema (argrelextrema, order=2)
- Zone FSM with CREATED/DEFENDED/BROKEN/FLIPPED/INVALIDATED states
- POC signals (8 variants) with migration tracking
- VP context engine combining POC + SessionProfile + GEX + ZoneRegistry
- Zone registry with confluence scoring and lifecycle events
- v2 scaffold with VAH/VAL/POC proximity detection

### Missing

- **VP shape classification** (D/P/b/B): `SessionProfile` has no `classify_shape()` method. The shape enum doesn't exist yet.
- **Composite multi-session profiles**: No function to merge RTH + overnight with configurable weights.
- **VP-to-GEX explicit bridge**: `E6VPContextEngine` references GEX data but the cross-asset confluence score is not implemented.
- **TPO (Time Price Opportunity)**: No TPO implementation anywhere in the codebase.
- **LVN quality scoring**: The current threshold is binary (below `lvn_threshold` = LVN). No quality score with width, contrast, formation context, confluence, age, and touch count.
- **KDE and GMM approaches**: Only argrelextrema is implemented. KDE and GMM are not.

---

## Extension Points

### 1. VP Shape Classifier

Add to `deep6/engines/volume_profile.py`:

```python
from enum import Enum


class ShapeType(Enum):
    D = "d_shape"        # Single peak near midpoint
    P = "p_shape"        # Peak in upper half (distribution)
    b = "b_shape"        # Peak in lower half (accumulation)
    B = "b_bimodal"      # Two distinct peaks
    DOUBLE = "double"    # Two roughly equal peaks
    UNKNOWN = "unknown"


def classify_shape(self) -> ShapeType:
    """
    Classify the VP shape based on peak distribution.
    Call on SessionProfile after sufficient bars have accumulated.
    """
    if len(self._nodes) < 10:
        return ShapeType.UNKNOWN

    prices = sorted(self._nodes.keys())
    volumes = [self._nodes[p].volume for p in prices]
    total_vol = sum(volumes)
    mid_price = (prices[0] + prices[-1]) / 2

    # Find peaks
    from scipy.signal import argrelextrema
    import numpy as np
    vol_arr = np.array(volumes)
    peak_idx, = argrelextrema(vol_arr, np.greater, order=3)

    if len(peak_idx) == 0:
        return ShapeType.UNKNOWN

    if len(peak_idx) >= 2:
        # Check if two peaks are roughly equal
        peak_vols = [volumes[i] for i in peak_idx]
        if max(peak_vols) / min(peak_vols) < 1.5:
            return ShapeType.DOUBLE
        return ShapeType.B

    # Single peak
    peak_price = prices[peak_idx[0]]
    range_pct = (peak_price - prices[0]) / (prices[-1] - prices[0])

    if 0.35 <= range_pct <= 0.65:
        return ShapeType.D
    elif range_pct > 0.65:
        return ShapeType.P
    else:
        return ShapeType.b
```

### 2. Composite Profile Method

Add to `deep6/engines/volume_profile.py`:

```python
@classmethod
def composite_profiles(
    cls,
    profiles: list["SessionProfile"],
    weights: list[float] | None = None,
) -> "SessionProfile":
    """
    Merge multiple SessionProfile instances into one weighted composite.

    Args:
        profiles: List of session profiles. Typically [rth, overnight].
        weights: Per-profile weights. Default: equal. Typical: [2.0, 1.0].

    Returns:
        New SessionProfile with merged volume.
    """
    if not profiles:
        raise ValueError("Need at least one profile")

    if weights is None:
        weights = [1.0] * len(profiles)

    composite = cls(
        tick_size=profiles[0].tick_size,
        prices_per_row=profiles[0].prices_per_row,
    )

    for profile, weight in zip(profiles, weights):
        for price, node in profile._nodes.items():
            key = composite.round_to_row(price)
            if key not in composite._nodes:
                composite._nodes[key] = VolumeNode(price=key, volume=0.0)
            composite._nodes[key].volume += node.volume * weight
            composite._total_volume += node.volume * weight

    return composite
```

### 3. VP-to-GEX Confluence Score

Extend `E6VPContextEngine.process()` in `deep6/engines/vp_context_engine.py`:

```python
def _compute_gex_vp_confluence(
    self,
    lvn_prices: list[float],
    gex_walls: list[float],
    tolerance_ticks: int = 4,
) -> float:
    """
    Score how many LVN levels align with GEX walls.

    Args:
        lvn_prices: LVN price levels from SessionProfile.
        gex_walls: GEX wall prices from FlashAlpha data.
        tolerance_ticks: How close (in ticks) counts as alignment.

    Returns:
        Confluence score 0.0-1.0. 1.0 = every LVN aligns with a GEX wall.
    """
    if not lvn_prices or not gex_walls:
        return 0.0

    tolerance = tolerance_ticks * 0.25  # Convert ticks to points
    aligned = 0

    for lvn in lvn_prices:
        for wall in gex_walls:
            if abs(lvn - wall) <= tolerance:
                aligned += 1
                break

    return aligned / len(lvn_prices)
```

### 4. LVN Quality Score

New dataclass for richer LVN characterization. Add to `deep6/engines/volume_profile.py`:

```python
from dataclasses import dataclass


@dataclass
class LVNQualityScore:
    price: float
    width: float              # Price range of the LVN in points
    contrast: float           # Ratio of adjacent HVN volume to LVN volume
    formation_context: str    # 'trending', 'balanced', 'transitional'
    confluence: float         # 0.0-1.0, alignment with GEX/structural levels
    age: int                  # Bars since LVN formed
    touch_count: int          # Times price has touched this LVN
    composite_score: float    # Weighted combination of above fields

    @classmethod
    def compute(
        cls,
        price: float,
        profile: "SessionProfile",
        zone: "Zone | None" = None,
        gex_confluence: float = 0.0,
    ) -> "LVNQualityScore":
        nodes = profile.snapshot()
        prices = sorted(nodes.keys())

        if price not in nodes:
            raise ValueError(f"Price {price} not in profile")

        lvn_vol = nodes[price].volume
        mean_vol = sum(n.volume for n in nodes.values()) / len(nodes)

        # Width: count consecutive below-threshold rows
        idx = prices.index(price)
        width = profile.row_size
        for i in range(idx + 1, min(idx + 10, len(prices))):
            if nodes[prices[i]].volume < mean_vol * profile.lvn_threshold:
                width += profile.row_size
            else:
                break

        # Contrast: ratio of nearest HVN to this LVN
        adjacent_vols = []
        for offset in [-2, -1, 1, 2]:
            adj_idx = idx + offset
            if 0 <= adj_idx < len(prices):
                adjacent_vols.append(nodes[prices[adj_idx]].volume)
        contrast = max(adjacent_vols) / max(lvn_vol, 1.0) if adjacent_vols else 1.0

        # Composite score
        score = (
            min(contrast / 5.0, 1.0) * 0.35 +
            min(width / 4.0, 1.0) * 0.25 +
            gex_confluence * 0.25 +
            (min(zone.touch_count / 5.0, 1.0) if zone else 0.0) * 0.15
        )

        return cls(
            price=price,
            width=width,
            contrast=contrast,
            formation_context="balanced",  # Extend with shape classifier
            confluence=gex_confluence,
            age=zone.created_bar if zone else 0,
            touch_count=zone.touch_count if zone else 0,
            composite_score=score,
        )
```

### 5. New ZoneType Variants

Extend the `ZoneType` enum in `deep6/engines/zone_registry.py`:

```python
class ZoneType(Enum):
    LVN = "lvn"
    HVN = "hvn"
    STRUCTURAL = "structural"
    # New sub-types
    LVN_BREAKOUT_READY = "lvn_breakout_ready"   # High contrast, untouched, trending context
    LVN_FADE_READY = "lvn_fade_ready"           # High touch count, defended, balanced context
    LVN_EXHAUSTED = "lvn_exhausted"             # Multiple breaks, low remaining significance
```

---

## Test File Reference

| Test File | Coverage |
|-----------|---------|
| `tests/test_volume_profile.py` | VPRO-01..08, SessionProfile, LVN/HVN detection |
| `tests/test_poc.py` | POC-01..08, migration tracking, VA computation |
| `tests/test_vp_context_engine.py` | E6VPContextEngine, E7MLQualityEngine, cross-signal context |
| `tests/test_zone_registry.py` | ZoneRegistry, zone FSM transitions, confluence scoring |

New features must include tests following the VPRO-xx naming pattern. Each test should cover:
1. Happy path (signal fires correctly)
2. Edge case (empty profile, single bar, price at boundary)
3. FSM transition (zone moves from one state to the next correctly)

When adding `LVNQualityScore`, add tests as `LVNQ-01`, `LVNQ-02`, etc. When adding shape classification, add `SHAPE-01` through `SHAPE-05` (one per ShapeType).
