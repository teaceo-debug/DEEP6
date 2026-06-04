# NQ Futures — Market Regime Patterns

Complete reference for NQ market regimes, detection methods, and edge profiles.
Regime identification is the first-order filter for all DEEP6 signals. Getting
the regime wrong means applying the right signal in the wrong context.

---

## WHY REGIME MATTERS

The same signal can be a high-confidence trade in one regime and a losing trade
in another. ABS_04 (effort vs result absorption) has PF 3.94 in mean-reverting
regime and near-zero edge in trending regime. DELT_01 (OFI momentum) has PF 2.1
in trending regime and negative edge in choppy regime.

Regime is not a secondary consideration. It's the primary filter.

**Empirical basis**:
- Lo (2004) "The Adaptive Markets Hypothesis": market efficiency varies by regime
- Ang & Timmermann (2012): regime-switching models outperform single-state models
  for equity returns prediction
- DEEP6 internal: signal accuracy varies by 20-40 percentage points across regimes

---

## REGIME TAXONOMY

### REGIME 1: MEAN-REVERTING (most common, ~60-70% of sessions)

**Definition**: Price oscillates around a central value (VWAP, POC) without
sustained directional commitment. Buyers and sellers are roughly balanced.
Institutional participants are distributing or accumulating, not trending.

**Detection criteria** (require 3 of 5):
- Price within 1.5× ATR of VWAP for 60+ minutes
- CVD oscillates without sustained direction (net CVD change < 0.5× session average)
- ATR within 80-120% of 14-bar average (normal volatility)
- Volume within 80-120% of 20-day average
- OFI oscillates around zero (no persistent imbalance)

**Quantitative thresholds**:
```
mean_reverting = (
    abs(price - vwap) < 1.5 * atr AND
    abs(cvd_net_change) < 0.5 * cvd_session_avg AND
    0.8 < current_atr / atr_14bar < 1.2 AND
    0.8 < current_volume / volume_20day < 1.2
)
```

**Edge profile**:
- ABS_04 (effort vs result): PF 3.94, WR 78% — BEST regime for this signal
- VOLP_06 (value area return): PF 2.8, WR 72% — works well
- ABS_02 (iceberg detection): PF 2.6, WR 68% — works well
- DELT_01 (OFI momentum): PF 1.1, WR 52% — marginal, avoid
- DELT_02 (multi-level OFI): PF 1.2, WR 53% — marginal, avoid
- Zones strategy (Variant D): PF 4.93, WR 80.2% — OPTIMAL regime

**Signal weights in this regime**:
- Absorption signals: 1.5× normal weight
- Volume profile signals: 1.3× normal weight
- Auction theory signals: 1.3× normal weight
- Momentum/delta signals: 0.5× normal weight
- Minimum score threshold: 65 (lower than other regimes)

**Why absorption works here**:
- Price is seeking fair value, not trending
- Institutional orders absorb aggressive flow at key levels
- After absorption, price returns to value area
- No sustained momentum to override the absorption signal

**Common patterns**:
- Morning spike fades back to VWAP by 10:30 ET
- Price oscillates between value area high and low
- Multiple tests of same level with declining volume (exhaustion)
- POC acts as magnet throughout session

---

### REGIME 2: TRENDING

**Definition**: Price moves directionally with sustained commitment. Buyers or
sellers are in control. Institutional participants are executing large directional
orders (VWAP algos, program trading).

**Detection criteria** (require 3 of 5):
- ADX > 25 (directional movement index)
- Price > VWAP by > 2× ATR for 30+ consecutive bars (uptrend)
- CVD consistently one-sided: net CVD change > 1.5× session average
- Volume expanding in trend direction (volume > 120% of average on trend bars)
- OFI persistently positive (uptrend) or negative (downtrend) for 30+ minutes

**Quantitative thresholds**:
```
trending = (
    adx > 25 AND
    (abs(price - vwap) > 2 * atr OR
     abs(cvd_net_change) > 1.5 * cvd_session_avg) AND
    volume_trend_bars > 1.2 * volume_20day
)
```

**Edge profile**:
- DELT_01 (OFI momentum): PF 2.1, WR 62% — BEST regime for this signal
- DELT_02 (multi-level OFI): PF 2.3, WR 64% — works well
- DELT_03 (delta divergence): PF 1.8, WR 58% — works as exhaustion signal
- ABS_04 (effort vs result): PF 1.2, WR 51% — marginal, use only at extremes
- VOLP_06 (value area return): PF 0.9, WR 48% — AVOID (fading a trend)
- Zones strategy (Variant D): PF 1.4, WR 55% — reduced effectiveness

**Signal weights in this regime**:
- Momentum/delta signals: 1.5× normal weight
- Sweep/aggression signals: 1.3× normal weight
- Absorption signals: 0.5× normal weight (only at extremes)
- Volume profile mean-reversion signals: 0.3× normal weight
- Minimum score threshold: 75 (higher bar required)

**Why momentum works here**:
- Institutional VWAP algos must execute regardless of price
- Each execution creates more momentum (self-reinforcing)
- Stop orders above/below trend create predictable acceleration points
- Mean-reversion signals generate continuous losses (fading a trend)

**Common patterns**:
- Opening range break with follow-through
- VWAP acts as support/resistance (not magnet)
- Pullbacks to VWAP are buying opportunities (uptrend)
- Volume expands on trend bars, contracts on pullbacks

**Transition signals** (trend ending):
- Volume declining on trend bars (exhaustion)
- Price making new highs/lows but CVD not confirming (divergence)
- Absorption detected at trend extreme (ABS_04 signal)
- Hawkes branching ratio declining (endogenous momentum fading)

---

### REGIME 3: CHOPPY/NOISE

**Definition**: Price moves randomly without directional commitment or
mean-reversion structure. Volume is thin, spread is wide, institutional
participation is minimal. This is the worst regime for all signals.

**Detection criteria** (require 3 of 5):
- Volume below 70% of 20-day average
- ATR below 70% of 14-bar average (compressed volatility)
- VPIN < 0.2 (low probability of informed trading)
- No directional bias in OFI (oscillates randomly)
- Price range < 50% of prior session range

**Quantitative thresholds**:
```
choppy = (
    current_volume < 0.7 * volume_20day AND
    current_atr < 0.7 * atr_14bar AND
    vpin < 0.2 AND
    abs(ofi_30min) < 0.2
)
```

**Edge profile**:
- ALL signals: degraded 30-50% from normal
- No signal has reliable edge in this regime
- False positive rate increases significantly
- Adverse selection risk is highest (HFT dominates thin market)

**Signal weights in this regime**:
- ALL signals: 0.3× normal weight
- Minimum score threshold: 85 (very high bar)
- Preferred action: no new positions

**Why signals fail here**:
- Thin market = HFT dominates = signals are noise
- Low volume = any signal can be manufactured by small participant
- No institutional participation = no "smart money" to follow
- Random walk behavior: no predictable structure

**When this regime occurs**:
- 11:00-13:00 ET (lunch hour)
- Pre-holiday sessions (day before Thanksgiving, Christmas Eve)
- Low-news days with no macro catalysts
- After major news events when uncertainty is high

**Survival strategy**:
- Reduce all position sizes 50%
- Only trade A+ confluence (score ≥ 85)
- Prefer to sit out entirely
- Use time to review prior trades, not generate new ones

---

### REGIME 4: VOLATILITY EXPANSION

**Definition**: ATR expanding rapidly, VPIN spiking, bid-ask spread widening.
Typically triggered by macro news, Fed announcements, or exogenous shocks.
All signal confidences degrade; risk management becomes primary.

**Detection criteria** (require 2 of 4):
- ATR expanding: current ATR > 1.5× 14-bar average
- VPIN spiking: VPIN > 0.6 (high probability of informed trading)
- Bid-ask spread > 2× normal
- News/macro event context (FOMC, CPI, NFP, geopolitical)

**Quantitative thresholds**:
```
vol_expansion = (
    current_atr > 1.5 * atr_14bar OR
    vpin > 0.6 OR
    spread > 2 * normal_spread
)
```

**Edge profile**:
- All signal confidences degrade 40-60%
- Hawkes branching ratio → 1.0 (endogenous cascade risk)
- Options market creates predictable flow (GEX gamma cascade)
- Stop sweep reversals still work but require wider stops

**Signal weights in this regime**:
- ALL signals: 0.4× normal weight
- Minimum score threshold: 90
- Stop distances: 2× normal
- Position sizes: 50% of normal

**Why signals degrade**:
- High VPIN = informed trading dominates = adverse selection risk
- Endogenous cascades (Hawkes branching ratio → 1.0) override signal logic
- Bid-ask spread widens = execution costs increase
- Price moves faster than signal computation

**Hawkes cascade risk**:
- When branching ratio > 0.85: reduce all positions 50%
- When branching ratio > 0.95: close all positions, wait for stabilization
- Flash Crash (2010): branching ratio reached 1.0 during the cascade
- Recovery: branching ratio drops below 0.7 within 5-10 minutes of stabilization

**Options-driven volatility**:
- GEX gamma cascade: when price breaks through gamma flip level, MM must buy/sell
  aggressively to maintain delta-neutral → amplifies the move
- Vanna cascade: when VIX spikes, delta of all options changes → massive hedging flow
- These create predictable but dangerous order flow patterns

**Survival strategy**:
- Identify the news catalyst before trading
- Wait for initial volatility to subside (first 5-10 minutes after news)
- Look for absorption at key levels after the initial move
- Use wider stops (2× normal ATR)
- Reduce size to 50% of normal

---

### REGIME 5: GEX POSITIVE GAMMA

**Definition**: Options market makers are net long gamma (long calls + long puts
relative to their delta hedges). They sell rallies and buy dips to maintain
delta-neutral. This creates a mean-reversion force in the underlying.

**Detection**:
- FlashAlpha net GEX > 0 for NQ (via QQQ/NDX proxy)
- Price between put wall and call wall
- Options MM long gamma (confirmed by GEX sign)

**Data source**: FlashAlpha API ($49/month)
```
gex_positive = flashalpha.net_gex > 0 AND price_between_walls
```

**Edge profile**:
- Mean-reversion tendency: MM sells rallies, buys dips
- Zones strategy (Variant D): OPTIMAL (price pinned to levels)
- Absorption signals: highly reliable (MM absorption reinforces signal)
- Morning spike often fades back to VWAP
- Realized volatility lower than implied volatility

**Signal weights in this regime**:
- Absorption signals: 1.4× normal weight
- Volume profile signals: 1.3× normal weight
- Momentum signals: 0.6× normal weight
- Minimum score threshold: 60 (lower bar, high-confidence regime)

**Key levels in positive GEX**:
- Call wall: price level with highest call OI = resistance
- Put wall: price level with highest put OI = support
- Gamma flip: level where GEX changes sign = key pivot
- Price tends to oscillate between put wall and call wall

**Typical session structure**:
- Open: initial volatility as overnight positions adjust
- 9:45-10:30 ET: morning spike fades back to VWAP
- 10:30-13:00 ET: price oscillates in value area
- 13:00-15:00 ET: afternoon positioning, price returns to POC
- 15:00-16:00 ET: pre-close, price pins to highest OI strike

**Why this regime is favorable for DEEP6**:
- MM buying/selling at key levels reinforces absorption signals
- Predictable mean-reversion structure = high win rate for zones strategy
- Lower volatility = tighter stops = better risk/reward

---

### REGIME 6: GEX NEGATIVE GAMMA

**Definition**: Options market makers are net short gamma. They buy rallies and
sell dips to maintain delta-neutral. This creates a momentum force in the
underlying. Volatility is higher, ranges are wider, levels break more often.

**Detection**:
- FlashAlpha net GEX < 0 for NQ (via QQQ/NDX proxy)
- Price outside call wall (above) or put wall (below)
- Options MM short gamma (confirmed by GEX sign)

**Data source**: FlashAlpha API ($49/month)
```
gex_negative = flashalpha.net_gex < 0 OR price_outside_walls
```

**Edge profile**:
- Momentum tendency: MM buys rallies, sells dips
- Zones strategy (Variant D): REDUCED effectiveness (levels break)
- Delta/sweep signals: work well (follow the sweep, don't fade it)
- Wider ranges, higher volatility
- Realized volatility higher than implied volatility

**Signal weights in this regime**:
- Momentum/delta signals: 1.4× normal weight
- Sweep signals: 1.3× normal weight
- Absorption signals: 0.5× normal weight (levels break more often)
- Minimum score threshold: 75

**Key levels in negative GEX**:
- Gamma flip: price above flip = momentum up; price below flip = momentum down
- Call wall: becomes a target, not resistance (price accelerates through it)
- Put wall: becomes a target, not support (price accelerates through it)
- Round numbers: still act as temporary resistance/support

**Typical session structure**:
- Open: directional move from overnight positioning
- 9:30-10:30 ET: strong directional momentum
- 10:30-11:00 ET: brief consolidation, then continuation
- 13:00-15:00 ET: afternoon continuation or reversal
- 15:00-16:00 ET: pre-close momentum, often accelerates

**Risk management in negative GEX**:
- Wider stops required (levels break more often)
- Reduce position sizes 20-30%
- Don't fade sweeps (MM is buying/selling with you)
- Watch for gamma cascade: if price breaks through gamma flip, move accelerates

---

### REGIME 7: OPEX (Options Expiry)

**Definition**: Options expiration creates predictable order flow as market
makers and traders close/roll positions. 0DTE (zero days to expiry) options
create intraday gamma effects. Monthly opex creates weekly positioning effects.

**Detection**:
- 0DTE options concentration > 30% of total OI
- 1-5 days before monthly opex (third Friday of month)
- High OI at round number strikes (21000, 21500, 22000 for NQ)
- FlashAlpha charm/vanna flow data

**Types of opex effects**:

**0DTE gamma pinning**:
- 0DTE options have extreme gamma near expiry
- MM must hedge aggressively as price approaches strike
- Creates "pinning" effect: price gravitates to highest OI strike
- Strongest effect in final 2 hours of session (1:00-4:00 PM ET)

**Monthly opex (third Friday)**:
- Large OI at round number strikes creates strong pinning
- Morning volatility often manufactured (MM adjusting positions)
- 1:00-4:00 PM ET: expiry window, strong directional moves as positions close
- Charm flow: directional from open to close as delta decays

**Weekly opex (every Friday)**:
- Smaller effect than monthly
- Still creates pinning at highest weekly OI strike
- Strongest in final hour of session

**Edge profile**:
- Strong gamma pinning at highest OI strike: ~65% probability of pin
- Morning volatility often fades: ~60% of morning moves reverse by noon
- 1:00-4:00 PM ET: directional moves as positions close
- Charm flow creates directional bias from open to close

**Signal weights in this regime**:
- Options-flow signals: 1.5× normal weight
- Absorption at OI strikes: 1.4× normal weight
- Momentum signals: 1.2× normal weight (expiry moves are directional)
- Minimum score threshold: 70

**Key levels in opex**:
- Highest OI strike: primary pin target
- Second-highest OI strike: secondary target
- Gamma flip level: key pivot for direction
- Round numbers: always relevant, especially near expiry

---

## REGIME DETECTION ALGORITHM

For each 5-minute bar, compute a regime score vector:

```python
def classify_regime(bar_data, options_data):
    """
    Returns: regime_name, confidence (0-1), signal_multipliers dict
    """
    
    # Component scores (each 0-1)
    trend_score = compute_trend_score(bar_data)
    volume_score = compute_volume_score(bar_data)
    vpin_score = compute_vpin_score(bar_data)
    gex_score = compute_gex_score(options_data)
    ofi_score = compute_ofi_score(bar_data)
    vol_expansion_score = compute_vol_expansion_score(bar_data)
    opex_score = compute_opex_score(options_data)
    
    # Regime classification (priority order)
    if vol_expansion_score > 0.7:
        return "vol_expansion", vol_expansion_score, VOL_EXPANSION_MULTIPLIERS
    
    if opex_score > 0.6:
        return "opex", opex_score, OPEX_MULTIPLIERS
    
    if gex_score > 0.6:
        return "gex_positive", gex_score, GEX_POSITIVE_MULTIPLIERS
    
    if gex_score < -0.6:
        return "gex_negative", abs(gex_score), GEX_NEGATIVE_MULTIPLIERS
    
    if trend_score > 0.6:
        return "trending", trend_score, TRENDING_MULTIPLIERS
    
    if volume_score < 0.3 and vpin_score < 0.2:
        return "choppy", 1 - volume_score, CHOPPY_MULTIPLIERS
    
    return "mean_reverting", 1 - trend_score, MEAN_REVERTING_MULTIPLIERS


def compute_trend_score(bar_data):
    """0 = mean-reverting, 1 = strongly trending"""
    adx = calculate_adx(bar_data, period=14)
    vwap_distance = abs(bar_data.close - bar_data.vwap) / bar_data.atr
    cvd_direction = abs(bar_data.cvd_net_change) / bar_data.cvd_session_avg
    
    return (
        min(adx / 50, 1.0) * 0.4 +
        min(vwap_distance / 3, 1.0) * 0.3 +
        min(cvd_direction / 2, 1.0) * 0.3
    )


def compute_volume_score(bar_data):
    """0 = very thin, 1 = very active"""
    return min(bar_data.current_volume / bar_data.volume_20day_avg, 2.0) / 2.0


def compute_vpin_score(bar_data):
    """0 = uninformed, 1 = highly informed"""
    return bar_data.vpin  # already 0-1


def compute_gex_score(options_data):
    """Negative = negative gamma, Positive = positive gamma"""
    if options_data is None:
        return 0.0
    return np.clip(options_data.net_gex / options_data.gex_scale, -1.0, 1.0)


def compute_vol_expansion_score(bar_data):
    """0 = normal vol, 1 = extreme vol expansion"""
    atr_ratio = bar_data.current_atr / bar_data.atr_14bar
    vpin_component = bar_data.vpin
    spread_ratio = bar_data.current_spread / bar_data.normal_spread
    
    return min(
        (atr_ratio - 1.0) / 1.0 * 0.4 +
        vpin_component * 0.3 +
        (spread_ratio - 1.0) / 2.0 * 0.3,
        1.0
    )
```

---

## EDGE BY REGIME (empirical from DEEP6 attribution)

| Regime | Best Signals | Zones Strategy | MBO Detectors | Score Threshold |
|--------|-------------|----------------|----------------|-----------------|
| Mean-Reverting | ABS_04, VOLP_06, ABS_02 | Excellent (PF 4.93) | High value | 65 |
| Trending | DELT_01, DELT_02, DELT_03 | Poor (PF 1.4) | Moderate | 75 |
| Choppy | None reliable | Avoid | Low value | 85 |
| Vol Expansion | None | Avoid | High (if available) | 90 |
| GEX Positive | ABS signals, VOLP signals | Excellent | High value | 60 |
| GEX Negative | DELT signals, sweep signals | Poor | Moderate | 75 |
| OPEX | Options-flow, ABS at OI strikes | Moderate | High value | 70 |

---

## REGIME TRANSITIONS

Regime transitions are often the highest-alpha moments. The transition from
trending to mean-reverting is where absorption signals fire most reliably.

### Trending → Mean-Reverting

**Signals**:
- Volume declining on trend bars (exhaustion)
- Price making new highs/lows but CVD not confirming (divergence)
- ABS_04 fires at trend extreme (effort vs result)
- Hawkes branching ratio declining (endogenous momentum fading)
- ADX declining from peak

**Action**:
- Increase absorption signal weight
- Decrease momentum signal weight
- Look for first reversal signal at extreme

**Historical accuracy**: ~65% of trend exhaustion signals lead to mean-reversion
within 3-5 bars. The other 35% are continuation patterns (brief consolidation).

### Mean-Reverting → Trending

**Signals**:
- Volume expanding on directional bar
- CVD breaking out of oscillation range
- OFI persistently one-sided for 15+ minutes
- Price breaking out of value area with volume confirmation
- ADX rising above 20

**Action**:
- Increase momentum signal weight
- Decrease absorption signal weight
- Don't fade the breakout (wait for pullback confirmation)

**Historical accuracy**: ~55% of value area breakouts lead to sustained trending.
The other 45% are false breakouts that return to value area.

### Any Regime → Vol Expansion

**Signals**:
- ATR expanding rapidly (> 1.3× in 5 minutes)
- VPIN spiking (> 0.5 in 5 minutes)
- News/macro event (FOMC, CPI, NFP)
- Bid-ask spread widening

**Action**:
- Immediately reduce all position sizes 50%
- Widen stops to 2× normal
- Raise score threshold to 90
- Consider closing all positions if branching ratio > 0.9

**Recovery**:
- Wait for ATR to stabilize (< 1.2× 14-bar average)
- Wait for VPIN to decline (< 0.4)
- Wait for spread to normalize
- Resume normal weights after 10-15 minutes of stability

---

## INTRADAY REGIME SCHEDULE (NQ typical)

Based on empirical observation of NQ session structure:

| Time (ET) | Typical Regime | Dominant Signals | Notes |
|-----------|---------------|-----------------|-------|
| 9:30-9:45 | Vol Expansion | None reliable | Opening volatility, wait |
| 9:45-10:30 | Trending or Mean-Rev | DELT or ABS | Highest institutional participation |
| 10:30-11:00 | Transition | ABS_04 | First hour reversal window |
| 11:00-13:00 | Choppy | None | Lunch, avoid |
| 13:00-13:30 | Transition | Watch for regime | European close, positioning begins |
| 13:30-14:30 | Mean-Rev or Trending | ABS or DELT | Afternoon session begins |
| 14:30-15:30 | Trending | DELT signals | Pre-close momentum |
| 15:30-16:00 | Vol Expansion | None reliable | Close volatility, avoid |

**Note**: This is a statistical tendency, not a rule. Macro events override
the schedule. FOMC days are entirely different. Always check the economic
calendar before applying time-of-day regime assumptions.

---

## REGIME INTERACTION WITH GEX

GEX regime and price action regime interact multiplicatively:

| Price Regime | GEX Positive | GEX Negative |
|-------------|-------------|-------------|
| Mean-Reverting | OPTIMAL (PF 4.93+) | Moderate (PF 2.1) |
| Trending | Moderate (PF 1.8) | STRONG (PF 2.8) |
| Choppy | Avoid | Avoid |
| Vol Expansion | Caution | Danger |

**Best combination**: Mean-Reverting + GEX Positive = highest win rate for
absorption signals. This is the DEEP6 sweet spot.

**Worst combination**: Trending + GEX Negative = momentum cascade risk.
All absorption signals fail. Follow the trend or stay out.

---

## REGIME PERSISTENCE STATISTICS

How long does each regime typically last?

| Regime | Median Duration | 75th Percentile | Notes |
|--------|----------------|-----------------|-------|
| Mean-Reverting | 45-90 min | 2-3 hours | Most persistent |
| Trending | 20-45 min | 90 min | Often transitions to mean-rev |
| Choppy | 60-120 min | 3 hours | Lunch period |
| Vol Expansion | 5-15 min | 30 min | Short-lived, high intensity |
| GEX Positive | 1-5 days | 2 weeks | Options-driven, slow to change |
| GEX Negative | 1-5 days | 2 weeks | Options-driven, slow to change |
| OPEX | 1-5 days | 1 week | Calendar-driven |

**Implication**: GEX regime is a slow-moving background condition. Price action
regime changes intraday. The combination determines signal weights at any moment.

---

## REGIME FAILURE MODES

### False trending detection

**Problem**: Strong opening move looks like trending regime, but it's a stop
sweep that will reverse.

**Detection**:
- Volume spike at the extreme (stop sweep signature)
- Immediate delta reversal after the move
- Price returns to value area within 30 minutes

**Solution**: Require 30+ minutes of sustained trend before classifying as
trending regime. Don't classify based on first 15 minutes of session.

### False mean-reversion detection

**Problem**: Quiet period before a large move looks like mean-reverting regime.

**Detection**:
- VPIN rising (informed trading increasing)
- Volume building (accumulation before breakout)
- OFI persistently one-sided despite price not moving

**Solution**: Monitor VPIN and OFI even in apparent mean-reverting regime.
Rising VPIN = potential regime change incoming.

### GEX data lag

**Problem**: FlashAlpha GEX data has 15-minute delay. Regime may have changed.

**Solution**:
- Use price action signals to confirm GEX regime
- If price is trending strongly, treat as negative GEX regardless of data
- Update GEX regime classification every 15 minutes, not every bar

---

## PRACTICAL IMPLEMENTATION

### Regime state machine

```python
class RegimeStateMachine:
    """
    Tracks regime with hysteresis to prevent rapid switching.
    Requires regime signal to persist for min_bars before switching.
    """
    
    def __init__(self, min_bars_to_switch=3):
        self.current_regime = "mean_reverting"
        self.candidate_regime = None
        self.candidate_bars = 0
        self.min_bars = min_bars_to_switch
    
    def update(self, new_regime_signal):
        if new_regime_signal == self.current_regime:
            self.candidate_regime = None
            self.candidate_bars = 0
            return self.current_regime
        
        if new_regime_signal == self.candidate_regime:
            self.candidate_bars += 1
            if self.candidate_bars >= self.min_bars:
                self.current_regime = self.candidate_regime
                self.candidate_regime = None
                self.candidate_bars = 0
        else:
            self.candidate_regime = new_regime_signal
            self.candidate_bars = 1
        
        return self.current_regime
    
    def get_signal_multipliers(self):
        return REGIME_MULTIPLIERS[self.current_regime]
```

### Signal weight multipliers by regime

```python
REGIME_MULTIPLIERS = {
    "mean_reverting": {
        "absorption": 1.5,
        "volume_profile": 1.3,
        "auction": 1.3,
        "momentum": 0.5,
        "sweep": 0.7,
        "score_threshold": 65
    },
    "trending": {
        "absorption": 0.5,
        "volume_profile": 0.7,
        "auction": 0.7,
        "momentum": 1.5,
        "sweep": 1.3,
        "score_threshold": 75
    },
    "choppy": {
        "absorption": 0.3,
        "volume_profile": 0.3,
        "auction": 0.3,
        "momentum": 0.3,
        "sweep": 0.3,
        "score_threshold": 85
    },
    "vol_expansion": {
        "absorption": 0.4,
        "volume_profile": 0.4,
        "auction": 0.4,
        "momentum": 0.4,
        "sweep": 0.4,
        "score_threshold": 90
    },
    "gex_positive": {
        "absorption": 1.4,
        "volume_profile": 1.3,
        "auction": 1.2,
        "momentum": 0.6,
        "sweep": 0.7,
        "score_threshold": 60
    },
    "gex_negative": {
        "absorption": 0.5,
        "volume_profile": 0.7,
        "auction": 0.7,
        "momentum": 1.4,
        "sweep": 1.3,
        "score_threshold": 75
    },
    "opex": {
        "absorption": 1.2,
        "volume_profile": 1.1,
        "auction": 1.1,
        "momentum": 1.2,
        "sweep": 1.1,
        "score_threshold": 70
    }
}
```

---

## ACADEMIC FOUNDATIONS

**Regime-switching models**:
- Hamilton (1989): Markov regime-switching model for business cycles
- Ang & Timmermann (2012): "Regime Changes and Financial Markets" — comprehensive review
- Guidolin & Timmermann (2008): regime-switching in equity returns, 4-state model

**Volatility regimes**:
- Engle (1982): ARCH model — volatility clustering
- Bollerslev (1986): GARCH — persistent volatility regimes
- Heston (1993): stochastic volatility model

**Market microstructure regimes**:
- Admati & Pfleiderer (1988): intraday trading patterns, informed vs uninformed
- Kyle (1985): informed trading model — lambda as regime indicator
- Easley & O'Hara (1992): information-based trading model

**GEX and options flow**:
- Kris Sidial (2021): "The Gamma Exposure Framework" — practical GEX application
- SpotGamma research (2020-2024): empirical GEX regime studies
- Bittman (2009): "Trading Index Options" — options MM hedging mechanics

**DEEP6 empirical results**:
- Zones Variant D: PF 4.93, WR 80.2% over 16 months (mean-reverting + GEX positive)
- ABS_04 (effort vs result): PF 3.94 strongest single signal
- Regime filtering: 20-40 percentage point accuracy improvement across all signals
