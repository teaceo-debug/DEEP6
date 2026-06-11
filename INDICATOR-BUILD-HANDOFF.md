# DEEP6 Compound Signal Indicator — Build Handoff for HERMES

## What to Build
A NinjaTrader 8 indicator called `DEEP6CompoundSignals` that paints arrows when validated high-accuracy signal setups fire on NQ futures.

## Source Material
- **Master summary**: `C:\Users\Tea\DEEP6\data\backtests\analysis\MASTER_BACKTEST_SUMMARY_V5.txt`
- **NT8 architecture map**: Explore agent mapped the full pattern in the R6-R8 session (see below)
- **Existing DEEP6 codebase**: `C:\Users\Tea\DEEP6\ninjatrader\Custom\`
- **Backtesting scripts**: `C:\Users\Tea\DEEP6\scripts\round*.py` (45+ scripts, 1,200+ filters tested)

## Top 15 Signals to Implement (Ranked by Validated Win Rate)

### Tier 1: GREEN arrows (highest conviction, 85%+ WR)
1. **absorption + 60m_extreme + 15m_trend + NOT lunch** — 90.9% WR, OOS 92.3%, ~0.4/week
2. **Stable vol + 60m_extreme + 15m_trend + first_hour** — 98.4% WR30, N=64, ~0.2/day
3. **CVD divergence + doji + 60m_extreme + 15m_trend + NOT killers** — 89.8% WR30, N=88

### Tier 2: YELLOW arrows (high conviction, 80-85% WR)
4. **Doji + 60m_extreme + 15m_trend + NOT killers + first_hour** — 87.9% WR30, OOS 83.7%, ~2.6/week
5. **Morning/evening star + 60m_extreme + 15m_trend + NOT killers + first_hour** — 92.0% WR30, N=88
6. **60m_extreme + 15m_trend + NOT killers + first_hour** — 86.5% WR30, N=2,457, ~51/week (the workhorse)
7. **score >= 60 + 60m_extreme + 15m_trend + first_hour + NOT killers** — 83.5%->88.5% GROWING

### Tier 3: ORANGE arrows (good conviction, 75-80% WR)
8. **CVD divergence + 60m_extreme + 15m_trend** — 82.4% WR, N=807, OOS validated
9. **Doji + 60m_extreme + 15m_trend** — 80.6% WR, N=1,340, OOS 79.8%
10. **3 narrowing ranges + 60m_extreme + 15m_trend** — 81.6% WR, N=1,971, OOS 81.8%
11. **Failed OR breakout + 60m_extreme + 15m_trend** — 80.5% WR, N=2,613
12. **Engulfing + 60m_extreme + 15m_trend** — 76.7% WR, N=1,756
13. **Hammer/shooting star + 60m_extreme + 15m_trend** — 78.5% WR, N=177
14. **|delta|/vol < 0.05 + 60m_extreme + 15m_trend** — 82.8%->89.4% GROWING
15. **Small overnight move + 60m_extreme + 15m_trend** — 88.8% WR30, N=581

## Signal Killers (ALWAYS EXCLUDE — these destroy edge)
When ANY of these conditions are true, DO NOT paint an arrow:
1. **Signal closes in middle 40-60% of 60m range** — bar is not truly at the extreme (-16.6pp)
2. **Volume spike > 3x 20-bar EMA** — climactic volume = exhaustion, not reversal (-8.4pp)
3. **Bar delta > 90th percentile same direction** — move already happened (-6.5pp)
4. **Next bar delta flips opposite** — this is a DIAGNOSTIC only (can't know at signal time)

## Core Filter Definitions

### 60m Extreme (THE anchor filter)
```
For bullish signals: bar_low is in bottom 20% of current 60-minute bar range
For bearish signals: bar_high is in top 20% of current 60-minute bar range

pos_in_60m = (anchor_price - low_60m) / (high_60m - low_60m)
bullish: pos_in_60m <= 0.20
bearish: pos_in_60m >= 0.80
```

### 15m Trend Aligned
```
direction_sign matches sign(15m_close - 15m_open)
If 15m candle is green (close > open), trend = +1 (bullish)
If 15m candle is red (close < open), trend = -1 (bearish)
Signal direction must match 15m trend direction
```

### First Hour
```
Bar time between 09:30 and 10:30 ET (inclusive)
```

### NOT Lunch
```
Bar time NOT between 12:00 and 14:00 ET
```

### NOT Killers
```
NOT (pos_in_60m between 0.40 and 0.60)  — not in middle of 60m range
AND NOT (bar_volume > 3.0 * rolling_20_bar_volume_EMA)  — not a volume spike
```

## Pattern Definitions

### Doji
```
body = abs(close - open)
range = high - low
is_doji = (range > 0) AND (body / range < 0.10)
Direction: sign(bar_delta) — positive delta = bullish, negative = bearish
```

### CVD Divergence
```
Build CVD per session: cvd = cumsum(bar_delta)
Bearish divergence: price makes new session high BUT cvd < session cvd high
Bullish divergence: price makes new session low BUT cvd > session cvd low
Direction: bearish for high divergence, bullish for low divergence
```

### 3 Narrowing Ranges
```
current bar range < prior bar range < bar-before-that range
(3 consecutive bars with decreasing range = compression)
Direction: sign(bar_delta)
```

### Morning Star (bullish)
```
bar[-2] is red (close < open)
bar[-1] is doji (body < 10% of range)
bar[0] is green (close > open)
bar[0] close > midpoint of bar[-2] body
Direction: +1 (bullish)
```

### Evening Star (bearish)
```
bar[-2] is green
bar[-1] is doji
bar[0] is red
bar[0] close < midpoint of bar[-2] body
Direction: -1 (bearish)
```

### Hammer (bullish)
```
lower_wick = min(open, close) - low
upper_wick = high - max(open, close)
body = abs(close - open)
is_hammer = lower_wick > 2 * body AND upper_wick < 0.5 * body AND close > open
Direction: +1
```

### Shooting Star (bearish)
```
upper_wick > 2 * body AND lower_wick < 0.5 * body AND close < open
Direction: -1
```

### Engulfing
```
Bullish: current body fully contains prior body, current close > current open
Bearish: current body fully contains prior body, current close < current open
body_high = max(open, close), body_low = min(open, close)
is_engulfing = current_body_high > prior_body_high AND current_body_low < prior_body_low
```

### Failed OR Breakout
```
Build opening range from first 15 minutes (09:30-09:45)
Failed breakout: bar_high broke above OR_high at some point, then bar_close < OR_high
Failed breakdown: bar_low broke below OR_low, then bar_close > OR_low
Direction: bearish for failed breakout (trapped longs), bullish for failed breakdown
```

### Stable Volatility
```
vol_of_vol = rolling 10-bar standard deviation of ATR20
is_stable_vol = vol_of_vol < 25th percentile of vol_of_vol distribution
(Low vol-of-vol = calm, stable market regime)
```

### |delta|/vol Ratio (Absorption Proxy)
```
delta_vol_ratio = abs(bar_delta) / bar_volume
is_low_delta_vol = delta_vol_ratio < 0.05
(Very balanced volume = true absorption behavior)
```

### Small Overnight Move
```
overnight_move = abs(session_open - prior_session_close)
is_small_overnight = overnight_move < 5 points (20 ticks)
```

## NT8 Architecture (from explore agent mapping)

### Multi-Timeframe Access
```csharp
// In State.Configure:
AddVolumetric("NQ 09-26", BarsPeriodType.Minute, 60, VolumetricDeltaType.BidAsk, 1); // 60m
AddVolumetric("NQ 09-26", BarsPeriodType.Minute, 15, VolumetricDeltaType.BidAsk, 1); // 15m

// BarsInProgress routing in OnBarUpdate:
// BIP 0 = primary (chart timeframe)
// BIP 1 = 60m bars
// BIP 2 = 15m bars
```

### Signal Rendering
```csharp
// GREEN arrow (Tier 1 — highest conviction)
Draw.ArrowUp(this, "T1_BULL_" + CurrentBar, true, 0, Low[0] - 4 * TickSize, Brushes.LimeGreen);
Draw.ArrowDown(this, "T1_BEAR_" + CurrentBar, true, 0, High[0] + 4 * TickSize, Brushes.LimeGreen);

// YELLOW arrow (Tier 2)
Draw.ArrowUp(this, "T2_BULL_" + CurrentBar, true, 0, Low[0] - 6 * TickSize, Brushes.Gold);

// ORANGE arrow (Tier 3)
Draw.ArrowUp(this, "T3_BULL_" + CurrentBar, true, 0, Low[0] - 8 * TickSize, Brushes.Orange);
```

### Existing Detector Integration
The DEEP6 codebase already has `DetectorRegistry`, `AbsorptionDetector`, `TrapDetector`, etc. in:
`C:\Users\Tea\DEEP6\ninjatrader\Custom\AddOns\DEEP6\`

The new indicator should either:
- **Option A**: Consume the existing `DetectorRegistry.EvaluateBar()` for absorption/trap/exhaustion signals, then add bar-pattern detection (doji, hammer, engulfing, CVD) as new logic
- **Option B**: Build standalone detection for all patterns using raw bar data (simpler, no dependency on AddOns)

Recommend Option A for absorption signals (already proven), Option B for new candlestick patterns.

## 16 Universal Trading Rules (Encode as Constants/Comments)
1. 60m extreme = universal edge
2. 15m trend alignment = strongest secondary
3. First hour (09:30-10:30) = optimal window
4. Lunch (12:00-14:00) = danger zone
5. Edges GROW over time (5b to 30b)
6. Exclude 4 signal killers
7. CVD divergence at structure = alpha source
8. Doji/hammer/engulfing at structure = pattern family
9. Stable vol + first hour = highest WR regime
10. Enter at T+0 (don't wait)
11. IB extension context matters
12. Adaptive narrow range > fixed thresholds
13. Score 50-65 = scalable sweet spot
14. Gap absorption = premium setup
15. Signals are INDEPENDENT (no redundancy)
16. Wide stops (-80t/20pts) maximize expectancy

## Risk Parameters (from R40/R42/R43)
- **Optimal stop**: -80 ticks (20 points) for most setups; -40 ticks for absorption-specific
- **Position sizing**: Bayesian Quarter Kelly recommended
- **All setups survive heavy friction** (6 tick slippage + $2 commission)
- **No signal fatigue** — quality stable throughout session
- **Edge persists beyond 30 bars** for all setups
- **All top 10 setups confirmed ROBUST** across all market regimes (Q1-Q4 2025, Q1-Q2 2026)

## User-Configurable Properties
```
[Parameters]
- EnableTier1 (bool, default true) — show GREEN arrows
- EnableTier2 (bool, default true) — show YELLOW arrows
- EnableTier3 (bool, default true) — show ORANGE arrows
- EnableAlerts (bool, default true) — sound alerts on Tier 1 signals
- ExcludeLunch (bool, default true) — suppress signals 12:00-14:00
- FirstHourOnly (bool, default false) — only show first-hour signals
- ShowKillerZones (bool, default false) — shade middle 40-60% of 60m range as danger zone

[Colors]
- Tier1Color (Brush, default LimeGreen)
- Tier2Color (Brush, default Gold)
- Tier3Color (Brush, default Orange)
- KillerZoneColor (Brush, default Red with 20% opacity)

[Risk]
- StopTicks (int, default 80) — recommended stop distance
- AbsorptionStopTicks (int, default 40) — tighter stop for absorption signals
```

## How to Give This to HERMES

Run this command:
```bash
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Read /mnt/c/Users/Tea/DEEP6/INDICATOR-BUILD-HANDOFF.md and build the DEEP6CompoundSignals NinjaTrader 8 indicator according to the specifications. Deploy to NT8, compile, and verify it works on an NQ chart.' -s deep6-deployment-operator,tradingview-mcp-desktop-operator -Q --yolo --max-turns 20 2>&1"
```

Or break into phases:
```bash
# Phase 1: Build the indicator
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Read /mnt/c/Users/Tea/DEEP6/INDICATOR-BUILD-HANDOFF.md. Write the NinjaScript indicator file DEEP6CompoundSignals.cs implementing the top 15 signals with 3 tiers of colored arrows. Save to /mnt/c/Users/Tea/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6CompoundSignals.cs' -s deep6-deployment-operator -Q --yolo --max-turns 12 2>&1"

# Phase 2: Deploy and compile
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Deploy /mnt/c/Users/Tea/DEEP6/ninjatrader/Custom/Indicators/DEEP6/DEEP6CompoundSignals.cs to NinjaTrader 8, compile, check for errors, fix if needed' -s deep6-deployment-operator -Q --yolo --max-turns 12 2>&1"

# Phase 3: Verify on chart
wsl bash -c "cd /home/tea/.hermes/hermes-agent && ./venv/bin/hermes chat -q 'Add DEEP6CompoundSignals indicator to the NQ chart, take a screenshot, verify arrows appear' -s deep6-deployment-operator,tradingview-mcp-desktop-operator -Q --yolo --max-turns 8 2>&1"
```
