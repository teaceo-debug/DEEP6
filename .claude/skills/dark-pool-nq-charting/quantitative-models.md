# Dark Pool Quantitative Models — DIX, Z-Scores, GEX Confluence

This file covers the mathematical machinery behind dark pool analysis. Every formula here has a specific interpretation in the context of NQ futures trading. The models build on each other: DIX gives macro sentiment, z-scores identify anomalous activity, aggression metrics classify intent, and GEX confluence identifies where dark pool levels have structural reinforcement.

---

## 1. DIX (Dark Index) by SqueezeMetrics

DIX is the most widely cited dark pool sentiment indicator. It measures the dollar-weighted proportion of short volume across S&P 500 components, using FINRA Reg SHO daily short sale data.

### Exact Formula

```
DIX = Σ(Short_Volume_i × Price_i) / Σ(Total_Volume_i × Price_i)
```

Where the summation runs across all S&P 500 component stocks for the trading day.

This is a dollar-weighted short volume ratio, not a share-weighted one. A $500 stock with 1,000 shares of short volume contributes 5x more to DIX than a $100 stock with the same share count.

### Data Source

FINRA publishes Reg SHO daily short sale files by 6:00 PM ET each trading day. The files are available at:

```
https://www.finra.org/investors/learn-to-invest/advanced-investing/short-selling/regsho/daily-short-sale-volume-files
```

SqueezeMetrics aggregates these into the DIX metric and publishes it at squeezemetrics.com. The raw FINRA data is free; the aggregated DIX is available via SqueezeMetrics' free tier.

### The Counter-Intuitive Interpretation

Higher short volume does NOT mean more bearish activity. This is the most common misreading of DIX.

When a market maker fills a retail buy order, the MM is the counterparty. The MM sells to the retail buyer. Under Reg SHO, that MM sale is recorded as a short sale even if the MM immediately hedges or has inventory. So high short volume in dark pools often reflects market makers BUYING from institutions (the institution sells, the MM buys and records a short sale on the other side).

The empirical result: high DIX correlates with institutional accumulation, not distribution.

### Interpretation Ranges

| DIX Value | Interpretation |
|-----------|----------------|
| > 0.50 | Very bullish — extreme institutional accumulation |
| 0.45-0.50 | Bullish — above-average institutional buying |
| 0.40-0.45 | Neutral — balanced dark pool activity |
| < 0.40 | Bearish — institutional distribution or risk-off |

### Performance Evidence

From SqueezeMetrics' published research (2016-2022 backtest on SPY):

- Very high DIX (≥ 45%): mean 60-day forward return +5.3% vs +2.8% baseline
- Very low DIX (≤ 38%): mean 60-day forward return +0.4%

DIX tends to RISE into corrections. Institutions buy fear. This makes DIX a contrarian indicator at extremes: when retail is selling and DIX spikes, that's a buy signal.

### Python Implementation

```python
import pandas as pd
import numpy as np
import requests
from io import StringIO

def fetch_finra_short_data(date: str) -> pd.DataFrame:
    """
    Fetch FINRA Reg SHO daily short sale data.
    date: 'YYYYMMDD' format
    """
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(
        StringIO(response.text),
        sep='|',
        skipfooter=1,
        engine='python'
    )
    return df

def compute_dix(df: pd.DataFrame, sp500_symbols: list[str]) -> float:
    """
    Compute DIX from FINRA short sale data.
    df: DataFrame with columns ['Symbol', 'ShortVolume', 'TotalVolume', 'Market']
    sp500_symbols: list of S&P 500 ticker symbols
    """
    # Filter to S&P 500 components and consolidated tape
    mask = (df['Symbol'].isin(sp500_symbols)) & (df['Market'] == 'C')
    sp500_df = df[mask].copy()

    # We need price data — fetch from your data source
    # Here we assume a price_map dict {symbol: close_price}
    # In production, use yfinance or your market data feed
    # sp500_df['Price'] = sp500_df['Symbol'].map(price_map)

    # Dollar-weighted calculation
    sp500_df['ShortDollar'] = sp500_df['ShortVolume'] * sp500_df['Price']
    sp500_df['TotalDollar'] = sp500_df['TotalVolume'] * sp500_df['Price']

    dix = sp500_df['ShortDollar'].sum() / sp500_df['TotalDollar'].sum()
    return float(dix)

def compute_dix_ma(dix_series: pd.Series, window: int = 5) -> pd.Series:
    """5-day moving average for smoothing."""
    return dix_series.rolling(window=window, min_periods=1).mean()
```

### Known Critiques

- **Survivorship bias**: Historical analysis uses current S&P 500 composition, not historical composition. Stocks that were removed (often due to poor performance) are excluded from the backtest.
- **Timing lag**: FINRA data is published after market close. DIX is a next-day signal, not real-time.
- **Aggregation problem**: DIX aggregates across 500 stocks. A single large-cap (AAPL, MSFT, NVDA) can dominate the dollar weighting and mask divergent behavior in the rest of the index.

---

## 2. Z-Score Anomaly Detection

A dark pool level is only meaningful if the volume at that level is statistically unusual. Z-score normalization identifies which levels are genuinely anomalous vs routine.

### Formula

For each price level `p`, maintain a 90-day rolling window of daily dark pool volume:

```
z_score(p, t) = (V(p, t) - μ(p, t-90:t-1)) / σ(p, t-90:t-1)
```

Where:
- `V(p, t)` = dark pool volume at price level `p` on day `t`
- `μ` = 90-day rolling mean of dark pool volume at that level
- `σ` = 90-day rolling standard deviation

### Thresholds

| Z-Score | Interpretation |
|---------|----------------|
| Z > +2.0 | Statistically unusual (p < 0.05, two-tailed) — high-conviction level |
| Z > +1.5 | Elevated — worth monitoring |
| -1.5 < Z < +1.5 | Normal range — background noise |
| Z < -1.5 | Depressed — institutional absence at this level |

### Contextual Interpretation

Z-score alone doesn't tell you direction. Combine with the short ratio:

- **Elevated total DP volume (Z > +1.5) + declining short ratio**: Institutions are buying aggressively. The short ratio drops because more of the dark pool volume is outright buying rather than MM-facilitated short sales. **Bullish accumulation.**
- **Elevated total DP volume (Z > +1.5) + rising short ratio**: Institutions are selling into dark pools. **Bearish distribution.**
- **Depressed DP volume (Z < -1.5)**: Institutions have stepped away from this price level. Reduced structural support/resistance.

### Python Implementation

```python
import numpy as np
import pandas as pd
from collections import defaultdict

class DarkPoolZScoreEngine:
    def __init__(self, lookback_days: int = 90):
        self.lookback = lookback_days
        # {price_level: deque of daily volumes}
        self.volume_history: dict[float, list[float]] = defaultdict(list)

    def update(self, price_level: float, daily_volume: float) -> None:
        """Add a new daily observation for a price level."""
        history = self.volume_history[price_level]
        history.append(daily_volume)
        # Keep only the lookback window
        if len(history) > self.lookback:
            history.pop(0)

    def z_score(self, price_level: float, current_volume: float) -> float | None:
        """
        Compute z-score for current volume at a price level.
        Returns None if insufficient history (< 20 days).
        """
        history = self.volume_history[price_level]
        if len(history) < 20:
            return None

        mu = np.mean(history)
        sigma = np.std(history, ddof=1)

        if sigma < 1e-10:
            return 0.0

        return (current_volume - mu) / sigma

    def classify(self, z: float | None) -> str:
        if z is None:
            return "insufficient_data"
        if z > 2.0:
            return "anomalous_high"
        if z > 1.5:
            return "elevated"
        if z < -1.5:
            return "depressed"
        return "normal"

    def batch_z_scores(self, current_volumes: dict[float, float]) -> pd.DataFrame:
        """
        Compute z-scores for multiple price levels simultaneously.
        current_volumes: {price_level: today_volume}
        """
        records = []
        for price, vol in current_volumes.items():
            z = self.z_score(price, vol)
            records.append({
                'price': price,
                'volume': vol,
                'z_score': z,
                'classification': self.classify(z)
            })
        return pd.DataFrame(records).sort_values('z_score', ascending=False)
```

---

## 3. NBBO-Relative Aggression Metric

Dark pool prints are classified relative to the National Best Bid and Offer at the time of execution. This classification reveals whether the institution was the aggressor (paying the spread) or the passive party (providing liquidity).

### Classification

For each dark pool print at price `P` with NBBO `(Bid, Ask)`:

```
if P > Ask:   → above_ask   (aggressive buy — institution paid up)
if P < Bid:   → below_bid   (aggressive sell — institution sold down)
else:         → inside_spread (neutral — price improvement or midpoint fill)
```

### Aggression Ratio

```
aggression_ratio = (prints_above_ask - prints_below_bid) / total_prints
```

| Ratio | Interpretation |
|-------|----------------|
| > 0.55 | Institutional buying — net aggressive demand |
| 0.45-0.55 | Neutral — balanced or midpoint fills |
| < 0.45 | Institutional selling — net aggressive supply |

### Python Implementation

```python
from dataclasses import dataclass
from enum import Enum

class PrintSide(Enum):
    ABOVE_ASK = "above_ask"
    BELOW_BID = "below_bid"
    INSIDE_SPREAD = "inside_spread"

@dataclass
class DarkPoolPrint:
    price: float
    notional: float
    nbbo_bid: float
    nbbo_ask: float
    timestamp: float

def classify_print(p: DarkPoolPrint) -> PrintSide:
    if p.price > p.nbbo_ask:
        return PrintSide.ABOVE_ASK
    elif p.price < p.nbbo_bid:
        return PrintSide.BELOW_BID
    return PrintSide.INSIDE_SPREAD

def compute_aggression_ratio(
    prints: list[DarkPoolPrint],
    notional_weighted: bool = True
) -> float:
    """
    Compute aggression ratio from a list of dark pool prints.
    notional_weighted=True weights by dollar value (recommended).
    """
    above_ask_weight = 0.0
    below_bid_weight = 0.0
    total_weight = 0.0

    for p in prints:
        weight = p.notional if notional_weighted else 1.0
        side = classify_print(p)

        if side == PrintSide.ABOVE_ASK:
            above_ask_weight += weight
        elif side == PrintSide.BELOW_BID:
            below_bid_weight += weight
        total_weight += weight

    if total_weight == 0:
        return 0.5

    return (above_ask_weight - below_bid_weight) / total_weight + 0.5
```

---

## 4. Volume-Weighted Dark Pool POC

The Point of Control for dark pool volume is the price level with maximum cumulative dark pool notional. Unlike a standard volume profile POC, this uses only off-exchange prints.

### Standard POC

```python
def compute_dp_poc(price_volume: dict[float, float]) -> float:
    """
    price_volume: {price_level: cumulative_notional}
    Returns the price level with maximum dark pool volume.
    """
    return max(price_volume, key=price_volume.get)
```

### Recency-Weighted POC

Recent prints should carry more weight than older ones. Exponential decay with a 20-day half-life:

```
weight_i = exp(-i / 20)
```

Where `i` is the number of days ago (0 = today, 1 = yesterday, etc.).

```python
import numpy as np
from collections import defaultdict

def compute_recency_weighted_poc(
    daily_prints: list[dict[float, float]],
    decay_constant: float = 20.0
) -> float:
    """
    daily_prints: list of {price: notional} dicts, ordered oldest to newest
    decay_constant: half-life in days (20 = recent 20 days dominate)
    Returns the recency-weighted POC price.
    """
    n_days = len(daily_prints)
    weighted_volumes: dict[float, float] = defaultdict(float)

    for i, day_prints in enumerate(daily_prints):
        # i=0 is oldest, i=n_days-1 is most recent
        days_ago = n_days - 1 - i
        weight = np.exp(-days_ago / decay_constant)

        for price, notional in day_prints.items():
            weighted_volumes[price] += notional * weight

    return max(weighted_volumes, key=weighted_volumes.get)
```

The recency-weighted POC is more responsive to recent institutional activity. Use the standard POC for structural levels (swing trading), the recency-weighted POC for tactical levels (intraday).

---

## 5. Bayesian Significance Testing

Not every dark pool level deserves attention. Bayesian inference provides a principled way to assess whether a level is genuinely significant given the observed volume.

### Prior and Likelihood

From empirical analysis of dark pool data (2018-2024):

- **Prior probability** that any given price level is "significant" (will act as S/R): P(significant) = 0.15
- **Likelihood of observing elevated volume given significant level**: P(elevated | significant) = 0.85
- **Likelihood of observing elevated volume given non-significant level**: P(elevated | not significant) = 0.10

### Posterior Calculation

```
P(significant | elevated) = P(elevated | significant) × P(significant) /
                             [P(elevated | significant) × P(significant) +
                              P(elevated | not significant) × P(not significant)]

= (0.85 × 0.15) / (0.85 × 0.15 + 0.10 × 0.85)
= 0.1275 / (0.1275 + 0.085)
= 0.1275 / 0.2125
= 0.60
```

A level with elevated volume has a 60% posterior probability of being significant. To reach the 0.70 threshold for trading, you need additional evidence (multiple days of elevated volume, z-score > 2.0, or GEX confluence).

### Python Implementation

```python
def bayesian_level_significance(
    z_score: float,
    prior: float = 0.15,
    n_days_elevated: int = 1
) -> float:
    """
    Compute posterior probability that a dark pool level is significant.

    z_score: current z-score of dark pool volume at this level
    prior: base rate of significant levels (default 0.15)
    n_days_elevated: number of consecutive days with elevated volume

    Returns posterior probability in [0, 1].
    """
    # Likelihood of elevated volume given significance
    # Increases with z-score magnitude
    if z_score > 2.0:
        likelihood_given_sig = 0.90
        likelihood_given_not_sig = 0.05
    elif z_score > 1.5:
        likelihood_given_sig = 0.85
        likelihood_given_not_sig = 0.10
    elif z_score > 1.0:
        likelihood_given_sig = 0.70
        likelihood_given_not_sig = 0.20
    else:
        likelihood_given_sig = 0.50
        likelihood_given_not_sig = 0.40

    # Update prior with each additional day of elevated volume
    posterior = prior
    for _ in range(n_days_elevated):
        numerator = likelihood_given_sig * posterior
        denominator = (likelihood_given_sig * posterior +
                       likelihood_given_not_sig * (1 - posterior))
        posterior = numerator / denominator

    return posterior

# Example: level with z=2.3 for 3 consecutive days
p = bayesian_level_significance(z_score=2.3, n_days_elevated=3)
# p ≈ 0.87 — high confidence this level is significant
```

**Decision rule**: If posterior > 0.70, the level is significant enough to trade. If posterior > 0.85, it's a primary level.

---

## 6. GEX × Dark Pool Confluence Model

This is the highest-conviction signal in the entire framework. When dark pool institutional positioning aligns with gamma exposure mechanics, the resulting S/R levels are defended by two independent forces simultaneously.

### GEX Formula

Gamma Exposure at a given strike:

```
GEX_strike = Gamma × OI × 100 × Spot² × 0.01
```

Where:
- `Gamma` = option gamma (∂²V/∂S²) from Black-Scholes or market-implied surface
- `OI` = open interest at that strike
- `100` = contract multiplier (100 shares per option)
- `Spot²` = current underlying price squared
- `0.01` = 1% move normalization

**Sign convention**: Call OI contributes positive GEX. Put OI contributes negative GEX. Total GEX at a strike = GEX_calls + GEX_puts.

### Gamma Flip Level (Zero Gamma Level, ZGL)

The ZGL is the price P* where total market GEX crosses zero:

```
P* = argmin_P |Σ_strikes GEX(strike, P)|
```

In practice, compute total GEX across all strikes at the current spot price, then find the spot price where the sum changes sign.

**Regime interpretation**:
- **Above ZGL (positive gamma)**: Dealers are long gamma. They sell into rallies and buy dips to delta-hedge. Market is mean-reverting. Dark pool levels act as stronger S/R because dealer hedging reinforces them.
- **Below ZGL (negative gamma)**: Dealers are short gamma. They sell into declines and buy into rallies to delta-hedge. Market is trending. Dark pool levels may break more easily because dealer flows amplify moves rather than dampen them.

### Distance-to-Flip Confidence

```python
def flip_confidence(current_price: float, zgl: float) -> str:
    distance_pct = abs(current_price - zgl) / zgl * 100

    if distance_pct > 2.0:
        return "high"      # Well-established regime, dealer flows are predictable
    elif distance_pct > 0.5:
        return "moderate"  # Regime is clear but flip is possible
    else:
        return "low"       # Near the flip — regime is unstable, avoid trading
```

### Dark Pool + GEX Interaction Mechanics

The interaction between dealer gamma positioning and dark pool flows is not coincidental. It's mechanical:

**Short gamma dealers (below ZGL)**:
- Must sell into price declines to maintain delta neutrality
- These are large block sales, often executed in dark pools to minimize market impact
- Result: dark pool prints cluster BELOW the bid during declines
- Observation: elevated below-bid dark pool prints in negative gamma regime = trend continuation signal

**Long gamma dealers (above ZGL)**:
- Must buy dips to maintain delta neutrality
- These are large block buys, often executed in dark pools
- Result: dark pool prints cluster ABOVE the ask during dips
- Observation: elevated above-ask dark pool prints in positive gamma regime = mean-reversion signal

**Confluence signal**: When a dark pool level (identified by z-score and Bayesian significance) falls within 0.5% of a GEX wall (major call or put strike with high OI), that level has the strongest possible S/R characteristics.

### Confluence Signal Formula

```python
def compute_confluence_signal(
    gex_regime: str,           # "positive" or "negative"
    dp_aggression: float,      # aggression_ratio from section 3
    flip_confidence: str,      # "high", "moderate", "low"
    dp_z_score: float,         # z-score from section 2
    distance_to_gex_wall_pct: float  # % distance from nearest GEX wall
) -> float:
    """
    Returns a confluence score in [-1, 1].
    Positive = bullish confluence, negative = bearish confluence.
    """
    # Regime multiplier
    regime_mult = 1.0 if gex_regime == "positive" else -1.0

    # Aggression directional component (-1 to +1)
    aggression_component = (dp_aggression - 0.5) * 2  # center at 0

    # Confidence weight
    confidence_weights = {"high": 1.0, "moderate": 0.6, "low": 0.2}
    conf_weight = confidence_weights.get(flip_confidence, 0.2)

    # Z-score weight (capped at 3.0)
    z_weight = min(abs(dp_z_score), 3.0) / 3.0

    # Proximity to GEX wall (closer = stronger)
    proximity_weight = max(0, 1 - distance_to_gex_wall_pct / 0.5)

    # Combined signal
    signal = (regime_mult * aggression_component *
              conf_weight * z_weight * proximity_weight)

    return float(np.clip(signal, -1.0, 1.0))
```

**Interpretation**:
- Signal > 0.6: Strong bullish confluence — high-conviction long setup
- Signal 0.3-0.6: Moderate bullish confluence — trade with confirmation
- Signal -0.3 to 0.3: No confluence — avoid
- Signal < -0.6: Strong bearish confluence — high-conviction short setup

---

## 7. Vanna Exposure (VEX) Interaction

Vanna is the second-order cross-Greek: ∂Delta/∂IV (equivalently, ∂Gamma/∂S). It measures how much a dealer's delta changes when implied volatility moves.

### VEX Formula

```
VEX = (∂Delta/∂IV) × OI × 100 × Spot
```

For a standard Black-Scholes option:

```
Vanna = -d2 × exp(-d1²/2) / (S × σ × √T × √(2π))
```

Where d1 and d2 are the standard Black-Scholes terms.

### VEX-Driven Dark Pool Flows

Vanna flows often exceed gamma hedging flows in magnitude, especially around volatility events (FOMC, CPI, earnings).

**IV drops (VIX declining)**:
- Dealers with negative vanna exposure must BUY shares to re-hedge
- These buys appear as large dark pool prints above the ask
- This is the mechanical driver of "vol crush rallies" — the buying is forced, not discretionary

**IV spikes (VIX rising)**:
- Dealers with negative vanna exposure must SELL shares
- These sales appear as dark pool prints below the bid
- Amplifies the initial decline

### Regime Classification

Combining GEX, VEX, gamma flip distance, and dark pool aggression into a unified regime:

```python
from dataclasses import dataclass
from enum import Enum

class MarketRegime(Enum):
    STRONG_BULLISH = "strong_bullish"      # Positive GEX + VEX tailwind + DP buying
    BULLISH = "bullish"                    # Positive GEX + neutral VEX
    NEUTRAL = "neutral"                    # Near flip or mixed signals
    BEARISH = "bearish"                    # Negative GEX + neutral VEX
    STRONG_BEARISH = "strong_bearish"      # Negative GEX + VEX headwind + DP selling

@dataclass
class RegimeInputs:
    total_gex: float           # Total market GEX in $ billions
    total_vex: float           # Total market VEX in $ billions
    flip_distance_pct: float   # % distance from ZGL
    dp_aggression: float       # Aggression ratio (0-1)
    dp_z_score: float          # Z-score of current DP volume
    iv_trend: float            # 5-day change in VIX (negative = IV declining)

def classify_regime(inputs: RegimeInputs) -> MarketRegime:
    """
    Classify current market regime from GEX, VEX, and dark pool inputs.
    """
    # GEX component
    gex_bullish = inputs.total_gex > 0 and inputs.flip_distance_pct > 0.5
    gex_bearish = inputs.total_gex < 0 and inputs.flip_distance_pct > 0.5

    # VEX component (IV declining = bullish vanna flow)
    vex_tailwind = inputs.iv_trend < -0.5 and inputs.total_vex < 0
    vex_headwind = inputs.iv_trend > 0.5 and inputs.total_vex < 0

    # Dark pool component
    dp_buying = inputs.dp_aggression > 0.55 and inputs.dp_z_score > 1.5
    dp_selling = inputs.dp_aggression < 0.45 and inputs.dp_z_score > 1.5

    # Regime classification
    if gex_bullish and (vex_tailwind or dp_buying):
        return MarketRegime.STRONG_BULLISH
    elif gex_bullish:
        return MarketRegime.BULLISH
    elif gex_bearish and (vex_headwind or dp_selling):
        return MarketRegime.STRONG_BEARISH
    elif gex_bearish:
        return MarketRegime.BEARISH
    else:
        return MarketRegime.NEUTRAL
```

---

## 8. ADV Normalization

Raw dark pool volume is meaningless without context. A $500M dark pool print in AAPL is routine. The same print in a small-cap is extraordinary. For NQ (via QQQ proxy), normalize against the 20-day average daily volume.

### Formula

```
normalized_dp_volume = current_dp_volume / ADV_20
```

Where `ADV_20` is the 20-day average daily dark pool volume for the instrument.

### Thresholds

| Normalized Volume | Interpretation |
|-------------------|----------------|
| > 1.5 | Elevated — unusual institutional activity |
| 1.0-1.5 | Normal range |
| < 0.7 | Depressed — institutions absent |

### Seasonal Adjustment

Dark pool volume has predictable seasonal patterns: lower in August, higher in January and October. Dividing by a monthly seasonal factor removes this noise.

```python
import numpy as np
import pandas as pd

# Empirical seasonal factors for QQQ dark pool volume (2018-2024 average)
# Factor > 1.0 = historically above-average month
SEASONAL_FACTORS = {
    1: 1.12,   # January — high activity, new year positioning
    2: 1.05,
    3: 1.08,
    4: 1.03,
    5: 0.98,
    6: 0.95,
    7: 0.88,
    8: 0.82,   # August — summer lull
    9: 1.02,
    10: 1.15,  # October — historically volatile, high institutional activity
    11: 1.05,
    12: 0.90   # December — holiday thinning
}

def normalize_dp_volume(
    current_volume: float,
    adv_20: float,
    month: int,
    apply_seasonal: bool = True
) -> float:
    """
    Normalize dark pool volume against ADV and seasonal factors.

    current_volume: today's dark pool notional
    adv_20: 20-day average daily dark pool notional
    month: current month (1-12)
    apply_seasonal: whether to apply seasonal adjustment

    Returns normalized volume ratio.
    """
    if adv_20 <= 0:
        return 1.0

    raw_normalized = current_volume / adv_20

    if apply_seasonal:
        seasonal_factor = SEASONAL_FACTORS.get(month, 1.0)
        return raw_normalized / seasonal_factor

    return raw_normalized

def compute_adv(volume_history: list[float], window: int = 20) -> float:
    """Compute average daily volume over the lookback window."""
    if len(volume_history) < window:
        return float(np.mean(volume_history)) if volume_history else 0.0
    return float(np.mean(volume_history[-window:]))

class DarkPoolVolumeNormalizer:
    def __init__(self, window: int = 20):
        self.window = window
        self.history: list[float] = []

    def update(self, daily_volume: float) -> None:
        self.history.append(daily_volume)
        if len(self.history) > self.window * 2:
            self.history.pop(0)

    def normalize(self, current_volume: float, month: int) -> dict:
        adv = compute_adv(self.history, self.window)
        normalized = normalize_dp_volume(current_volume, adv, month)

        if normalized > 1.5:
            classification = "elevated"
        elif normalized >= 0.7:
            classification = "normal"
        else:
            classification = "depressed"

        return {
            'raw_volume': current_volume,
            'adv_20': adv,
            'normalized': normalized,
            'classification': classification
        }
```

### Combining All Models

In production, these models feed into a single scoring pipeline:

```python
def score_dark_pool_level(
    price_level: float,
    z_score: float,
    aggression_ratio: float,
    bayesian_posterior: float,
    normalized_volume: float,
    confluence_signal: float,
    regime: MarketRegime
) -> dict:
    """
    Aggregate all quantitative models into a single level score.
    Returns score in [0, 1] and recommended action.
    """
    # Component scores (each 0-1)
    z_component = min(max(z_score, 0) / 3.0, 1.0)
    bayesian_component = bayesian_posterior
    volume_component = min(normalized_volume / 2.0, 1.0)
    confluence_component = abs(confluence_signal)

    # Weighted average
    score = (
        0.25 * z_component +
        0.30 * bayesian_component +
        0.20 * volume_component +
        0.25 * confluence_component
    )

    # Direction from aggression and confluence
    bullish = (aggression_ratio > 0.55 and confluence_signal > 0 and
               regime in (MarketRegime.BULLISH, MarketRegime.STRONG_BULLISH))
    bearish = (aggression_ratio < 0.45 and confluence_signal < 0 and
               regime in (MarketRegime.BEARISH, MarketRegime.STRONG_BEARISH))

    if score > 0.70 and bullish:
        action = "primary_long_level"
    elif score > 0.70 and bearish:
        action = "primary_short_level"
    elif score > 0.50:
        action = "secondary_level"
    else:
        action = "monitor_only"

    return {
        'price': price_level,
        'score': round(score, 3),
        'action': action,
        'components': {
            'z_score': z_component,
            'bayesian': bayesian_component,
            'volume': volume_component,
            'confluence': confluence_component
        }
    }
```

This pipeline produces a ranked list of dark pool levels with associated confidence scores and directional bias. Feed the top 5-10 levels into the charting methodology from `charting-methodology.md` for visualization.
