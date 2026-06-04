# Dark Pool Charting Methodology — Plotting Institutional Levels on NQ

Dark pool levels are not magic lines. They're price zones where institutions transacted large notional value off-exchange, and those institutions don't forget where they filled. The methodology below treats dark pool data as a structural input, not a signal in isolation.

---

## 1. Visualization Methods

| Method | Description | Best For |
|--------|-------------|----------|
| Horizontal Lines | Fixed lines at each DP level; opacity and thickness scale with notional value | Quick S/R scanning |
| Heatmap Overlay | Price levels colored by volume intensity (cool = low, hot = high) | Seeing concentration at a glance |
| Volume Profile Integration | DP volume as a separate histogram alongside regular VP | Comparing dark vs lit distribution |
| Opacity Scaling | Line opacity proportional to notional value (min 0.2, max 1.0) | Distinguishing major from minor levels |
| Zone Consolidation | Merge nearby levels within 0.5% into a single zone | Treating clusters as zones, not exact prices |

**Implementation note:** Never plot more than 10-15 levels simultaneously. Cognitive overload kills execution. Filter by notional value and keep only the top levels for the current session's range.

---

## 2. QQQ to NQ Conversion

NQ futures don't have direct dark pool data. The proxy is QQQ (and to a lesser extent NDX options flow). Converting QQQ dark pool levels to NQ price requires a live ratio, not a fixed multiplier.

### Formula

```
NQ_Level = QQQ_Level × (NQ_Current / QQQ_Current)
```

### Example

QQQ dark pool print at $630. NQ trading at 21,500. QQQ trading at 465.

```
Ratio = 21500 / 465 = 46.24
NQ_Level = 630 × 46.24 = 29,131
```

### Why the ratio is not fixed

The NQ/QQQ ratio expands and contracts continuously because:

- **Volatility differential**: NQ is 2.5-3.2x more volatile than ES on an intraday basis. QQQ tracks NDX but with ETF-specific flows (creation/redemption, dividend adjustments) that create transient basis.
- **Tracking error**: QQQ holds 100 stocks weighted by market cap. NQ futures track the index directly. Rebalancing events, corporate actions, and index reconstitutions create temporary divergence.
- **Intraday basis changes**: Futures carry a cost-of-carry premium that shifts throughout the day as rates and dividends are priced in. The ratio at 9:31 AM is not the same as at 3:45 PM.

**You must recalculate the ratio on every bar.** A level that was 29,131 at the open may be 29,180 by noon if QQQ has drifted relative to NQ.

### Pine Script pattern for real-time conversion

```pine
//@version=5
indicator("Dark Pool NQ Levels", overlay=true)

// Fetch QQQ price for ratio calculation
qqq_close = request.security("NASDAQ:QQQ", timeframe.period, close)
nq_close = close  // assumes chart is NQ1! or MNQ1!

// Live ratio — recalculates every bar
nq_qqq_ratio = nq_close / qqq_close

// Convert a QQQ dark pool level to NQ
qqq_dp_level = input.float(630.0, "QQQ Dark Pool Level")
nq_dp_level = qqq_dp_level * nq_qqq_ratio

// Plot
line.new(bar_index - 50, nq_dp_level, bar_index, nq_dp_level,
         color=color.new(color.orange, 30), width=2, extend=extend.right)
```

For multiple levels, store QQQ prints in an array and iterate. The ratio calculation stays the same for all of them.

---

## 3. Time-of-Day Reliability

Dark pool prints don't carry equal weight throughout the session. Institutional activity clusters around specific windows.

| Time Window | Reliability | Why |
|-------------|-------------|-----|
| Pre-market 8:00-9:30 ET | HIGH | Institutions position before the open; large blocks transact on thin liquidity |
| NY Open 9:30-11:00 ET | VERY HIGH | The "killzone" — highest institutional participation, most dark pool volume, levels tested immediately |
| Midday 11:00-1:00 ET | MEDIUM | Retail-dominated, lower volume, dark pool levels less likely to be defended |
| Afternoon 1:00-4:00 ET | MEDIUM-HIGH | Renewed institutional activity, especially 3:00-4:00 for MOC positioning |
| After-hours | LOW | Thin volume, prints are often noise or small retail-adjacent flows |

**Practical rule:** Only trade dark pool levels during the NY open killzone (9:30-11:00) and the afternoon window (1:00-4:00). Midday levels that hold are worth noting for the afternoon session, but don't trade them in real time.

---

## 4. Intraday vs Swing Approaches

The same dark pool data serves different purposes depending on your timeframe.

### Intraday (1-15 minute charts)

- Use DP levels from the most recent 1-3 trading days
- Plot the 5-10 most significant levels by notional value within the current session's expected range
- Purpose: tactical entry and exit, identifying where price is likely to pause or reverse
- Refresh levels each morning before the open
- Discard levels more than 3 standard deviations from current price

### Swing (4H-daily charts)

- Use historical DP levels from the past 1-3 months
- Plot only the top 3-5 levels by total cumulative notional value
- Purpose: structural support and resistance, identifying major institutional cost basis zones
- These levels often align with volume profile POC and major option strikes
- Update weekly, not daily

The key difference: intraday levels are tactical, swing levels are structural. A swing-level dark pool zone that price approaches on an intraday chart is a high-conviction setup because both timeframes agree.

---

## 5. Tested vs Fresh Levels

Level status determines how you trade it.

**Fresh level** (price has never touched it since the print):
- Render as a solid line, full opacity
- This is a PRIMARY entry zone
- Institutions who printed here haven't had a chance to exit or add
- Treat as hard support/resistance until proven otherwise

**Tested level** (price has already touched it at least once):
- Render as a dashed line, 50% opacity
- This is a SECONDARY target or confirmation zone
- The institution may have partially exited, reducing the level's defensive strength
- Still valid, but lower conviction

**Marking logic:**
- A level becomes "tested" when price touches within 2-3 ticks of the level
- A level becomes "broken" when price closes through it on above-average volume
- Broken levels often flip: former support becomes resistance and vice versa
- Keep broken levels on the chart for 2-3 sessions as potential flip zones

```pine
// Pseudocode for level status tracking
var bool level_tested = false
if math.abs(close - dp_level) <= (syminfo.mintick * 3)
    level_tested := true

line_style = level_tested ? line.style_dashed : line.style_solid
line_opacity = level_tested ? 50 : 0
```

---

## 6. Dark Pool Volume Profile

A standard volume profile shows where all volume traded. A dark pool volume profile shows where institutional off-exchange volume concentrated. The divergence between the two is the signal.

### Construction

1. Collect all dark pool prints for the lookback period (typically 20 trading days)
2. Bin prints by price level (use 0.1% price buckets for NQ)
3. Sum notional value within each bucket
4. Normalize by total dark pool notional to get percentage distribution

### K-Means Clustering for Zone Identification

Raw dark pool prints are noisy. K-Means clustering identifies the true concentration zones.

```python
import numpy as np
from sklearn.cluster import KMeans

def cluster_dark_pool_levels(prints: list[dict], n_clusters: int = 5) -> list[dict]:
    """
    prints: list of {'price': float, 'notional': float}
    Returns cluster centers weighted by notional value.
    """
    if len(prints) < n_clusters:
        return prints

    prices = np.array([p['price'] for p in prints])
    weights = np.array([p['notional'] for p in prints])

    # Weight the price array by notional for volume-weighted clustering
    weighted_prices = np.repeat(
        prices,
        np.round(weights / weights.min()).astype(int)
    ).reshape(-1, 1)

    kmeans = KMeans(n_clusters=n_clusters, n_init=20, max_iter=50, random_state=42)
    kmeans.fit(weighted_prices)

    clusters = []
    for center in sorted(kmeans.cluster_centers_.flatten()):
        # Find all prints assigned to this cluster
        distances = np.abs(prices - center)
        cluster_mask = distances < (center * 0.005)  # within 0.5%
        cluster_notional = weights[cluster_mask].sum()
        clusters.append({
            'price': float(center),
            'notional': float(cluster_notional),
            'print_count': int(cluster_mask.sum())
        })

    return clusters
```

### Dark Pool POC and Value Area

- **Dark Pool POC**: The price level with maximum cumulative dark pool volume within a cluster
- **Dark Pool Value Area**: The price range containing 70% of total dark pool volume, expanded symmetrically from the POC

```python
def compute_dp_value_area(price_bins: dict[float, float], target_pct: float = 0.70) -> tuple[float, float]:
    """
    price_bins: {price_level: notional_volume}
    Returns (value_area_low, value_area_high)
    """
    total = sum(price_bins.values())
    poc = max(price_bins, key=price_bins.get)

    sorted_prices = sorted(price_bins.keys())
    poc_idx = sorted_prices.index(poc)

    accumulated = price_bins[poc]
    low_idx, high_idx = poc_idx, poc_idx

    while accumulated / total < target_pct:
        can_expand_low = low_idx > 0
        can_expand_high = high_idx < len(sorted_prices) - 1

        if not can_expand_low and not can_expand_high:
            break

        next_low = price_bins[sorted_prices[low_idx - 1]] if can_expand_low else 0
        next_high = price_bins[sorted_prices[high_idx + 1]] if can_expand_high else 0

        if next_high >= next_low and can_expand_high:
            high_idx += 1
            accumulated += price_bins[sorted_prices[high_idx]]
        elif can_expand_low:
            low_idx -= 1
            accumulated += price_bins[sorted_prices[low_idx]]

    return sorted_prices[low_idx], sorted_prices[high_idx]
```

### Lit vs Dark POC Divergence

When the lit volume profile POC and the dark pool POC are at different prices, the dark pool POC is the "true fair value" — where institutions actually want to be positioned, not where retail volume happened to concentrate. Price tends to gravitate toward the dark pool POC over the following 1-3 sessions.

---

## 7. Chart Patterns

Five patterns repeat with enough frequency to trade systematically.

### a) Print Pong

Price oscillates between two dark pool levels, bouncing off each in turn. The setup is the break: when price finally closes through one of the levels on elevated volume, the move is typically 1.5-2x the distance between the levels.

**Entry**: Close through the level, retest from the other side, enter on the retest.

### b) Absorption at DP Level

High volume at a dark pool level with minimal price movement. A passive institution is absorbing all incoming orders. This is the highest-conviction reversal signal in order flow.

**Confirmation**: Footprint shows large bid/ask imbalance at the level, delta diverges from price direction, volume spikes but price doesn't move.

**Entry**: First bar that closes away from the level after absorption completes.

### c) Dark Pool Level Break

Price closes through a dark pool level on above-average volume. These breaks are faster and more sustained than traditional technical S/R breaks because the institutional order that created the level is no longer defending it.

**Entry**: Retest of the broken level from the other side (former support becomes resistance, vice versa).

### d) Dark Pool Divergence

- **Bullish**: Dark pool buying (prints above ask) increasing while price is declining. Institutions are accumulating into weakness.
- **Bearish**: Dark pool selling (prints below bid) increasing while price is rising. Institutions are distributing into strength.

This divergence typically resolves within 3-5 sessions. The dark pool side wins.

### e) Accumulation / Distribution

Dark pool prints cluster at a support level over multiple days = accumulation. Institutions are building a position. The longer the accumulation, the larger the eventual move.

Dark pool prints cluster at a resistance level over multiple days = distribution. Institutions are exiting. The longer the distribution, the larger the eventual decline.

**Minimum threshold**: 3+ prints at the same level over 2+ days before calling it accumulation or distribution.

---

## 8. Daily Charting Workflow

### Pre-Market (7:00-9:30 ET)

- [ ] Pull latest dark pool data from data source (Unusual Whales, Quiver Quant, or FINRA Reg SHO)
- [ ] Identify top 10 QQQ/NDX dark pool levels by notional value from prior session
- [ ] Convert QQQ levels to NQ using current pre-market ratio
- [ ] Plot on NQ chart, color-coded by notional (top 3 = full opacity, rest = 50%)
- [ ] Mark each level as fresh or tested based on recent price action
- [ ] Note any levels that align with major GEX walls or volume profile POC

### NY Open (9:30-11:00 ET)

- [ ] Watch for liquidity grabs at dark pool levels in the first 5-15 minutes
- [ ] Monitor footprint for absorption at key levels (high volume, no price movement)
- [ ] Track delta divergence: price moving one way, delta moving the other
- [ ] Note which levels are holding and which are breaking
- [ ] Update tested/fresh status as price touches levels

### Intraday (11:00-3:00 ET)

- [ ] Monitor price at dark pool levels, especially during volume spikes
- [ ] Watch for print pong between two levels
- [ ] Track accumulation/distribution patterns forming at key levels
- [ ] Note any new large dark pool prints hitting the tape (if real-time data available)

### End of Day (3:30-4:00 ET)

- [ ] Document which levels held and which broke
- [ ] Update level status (fresh/tested/broken) for tomorrow
- [ ] Note any new large prints from the session
- [ ] Prepare level list for next morning

---

## 9. Common Mistakes

**Trading single prints.** One dark pool print at a price level means nothing. You need 3+ prints at the same level over 2+ trading days before the level has structural significance. Single prints are noise.

**Ignoring time-of-day.** A dark pool level that holds at 12:30 PM during low-volume midday trading is not the same as one that holds at 9:45 AM during the killzone. Only trade levels during high-participation windows.

**Not confirming with order flow.** Dark pool levels alone produce roughly 50% win rates. That's a coin flip. Confirmation from footprint (absorption, delta divergence, imbalance stacking) pushes win rates to 60-70%. Never trade a dark pool level without order flow confirmation.

**Using stale levels.** Dark pool levels older than 5 trading days have significantly reduced predictive power unless they're major structural levels (top 3 by notional over 30+ days). Refresh your level list daily.

**Treating levels as exact prices.** Dark pool prints are reported at the transaction price, but institutions defend zones, not exact ticks. Use a 2-3 tick buffer around each level. If NQ is at 21,500 and the dark pool level is 21,498, you're at the level.

**Over-plotting.** More than 10-15 levels on a chart creates analysis paralysis. Filter ruthlessly. The top 5 levels by notional value for the current session's range are enough.
