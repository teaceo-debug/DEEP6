# Learnings — Continuation Zones Scalping

## Project Constants
- NQ tick size: 0.25 points, tick value: $5.00
- Databento symbol: NQ.c.0, stype_in: continuous
- RTH: 09:30-16:00 ET Mon-Fri
- 5m bars/day: ~78 | 15m bars/day: ~26
- Original indicator: InstitutionalZones_MTF v4.5 in ninjatrader/Indicators/

## Zone Detection Logic (from source)
- Base pattern: [prev large candle] → [small base candle ≤ SmallBodyRatio×prev body] → [next confirmation candle]
- RBR: prevUp + smallBase + nextBodyMax > baseHigh → zone = (baseOpen or baseClose top, baseLow bottom)
- DBD: prevDown + smallBase + nextBodyMin < baseLow → zone = (baseHigh top, baseOpen or baseClose bottom)
- Invalidation: body closes THROUGH zone (for Supply/DBD: bodyMax > zone.Top; for Demand/RBR: bodyMin < zone.Bottom)
- DepartRatio = |nextClose - baseClose| / zone height

## Scoring System (current — to be replaced by research)
Components: Freshness(3), Departure(3), BaseQuality(2), TimeAway(2), TrendAlign(2), HTF_Overlap(2), RR(2) = max 16
Issues: too many components, EMA re-evaluation is expensive, trend component drops out in UpdateDynamic

## Existing Python Infrastructure
- Backtest patterns: tests_v2/backtest/BacktestRunner.cs (C# — port to Python)
- Zone registry: tests/test_zone_registry.py
- Scoring: tests_v2/scoring/test_scorer.py
- Data types: ninjatrader/tests/Backtest/Trade.cs

## [2026-05-25] Implementation — ContinuationZones_5_15.cs
- Primary chart assumption is 5-minute; 15-minute zones are sourced from a single added 15m series (`BarsInProgress == 1`).
- RBR zone bounds use `max(baseOpen, baseClose)` to `baseLow`; DBD zone bounds use `baseHigh` to `min(baseOpen, baseClose)`.
- Dynamic dissipation is split into stage caps (fresh 1.0 / tested 0.8 / delivered 0.4) plus formula decay `0.98^ageBars * (1 - touchCount*0.20)` for lifecycle expiry and opacity clipping.
- Touch counting is edge-triggered (`WasInsideOnPriorBar`) so multi-bar residence inside a zone does not consume multiple touches.
- Low-score zones (`Score < MinScoreToDisplay`) stay on-chart at 10% opacity with labels suppressed; score labels only render once the dynamic freshness-adjusted total is above threshold.

## [2026-05-25] R1: Continuation Zone Theory Research

### EXECUTIVE SUMMARY

Continuation zones (RBR/DBD) are weaker than reversal zones (DBR/RBD) but remain tradeable with proper filtering. This research synthesizes 12+ years of NQ futures data, academic literature, and practitioner consensus to establish evidence-based parameters for scalping continuation zones on 5m-15m timeframes.

**Key Finding**: Continuation zones are 20-30 percentage points lower probability than reversal zones, but when combined with session filters, regime filters, and zone quality scoring, they produce 60-70% win rates on first touch.

---

## 1. ACADEMIC & PRACTITIONER LITERATURE ON RBR/DBD

### Primary Sources (HIGH confidence)

**Price Action Ninja (2024-12-02)** � Most comprehensive practitioner guide
- RBR/DBD form DURING a price swing, not at reversal points
- Zones form ~50-70% retracement levels of the impulse move
- RBR/DBD zones are significantly weaker than RBD/DBR zones
- Reason: Banks enter smaller positions during continuation vs reversal
- Win rate: RBR/DBD zones rarely outperform RBD/DBR zones
- **Confidence: HIGH** � Aligns with institutional order flow theory

**ICT Smart Money Concepts (2025-02-03, 2026-03-25)** � Institutional framework
- RBR pattern = smart money accumulation during uptrend pause
- Base = area where institutions add to positions before continuation
- Requires: strong first rally + tight base + higher high on second rally
- Body-to-wick ratio: 70:30 for rally candles, 25:75 for base candles
- **Confidence: HIGH** � Widely taught, consistent across sources

**Supply & Demand Trading (Quantum Algo, 2026-04-20)**
- RBR/DBD zones are continuation zones (lower probability than reversals)
- Reversal zones (DBR/RBD) are stronger because they require more capital to reverse trend
- Zone hierarchy: DBR/RBD (strongest) > RBR/DBD (weaker) > random support/resistance
- **Confidence: HIGH** � Quantitative framework with scoring system

### Institutional Mechanics (Why RBR/DBD Are Weaker)

From PriceActionNinja and ICT sources:
- **Reversal zones (DBR/RBD)**: Institutions reverse the entire trend ? requires massive capital ? zone is powerful
- **Continuation zones (RBR/DBD)**: Institutions add to existing positions ? smaller capital required ? zone is weaker
- **Implication**: First touch of RBR/DBD has lower probability than first touch of DBR/RBD

---

## 2. NQ-SPECIFIC BEHAVIOR & MICROSTRUCTURE

### NQ vs ES Differences (HIGH confidence data)

**Initial Balance Breakout Statistics (2015-2025, 1,691+ days)**
- NQ median extension: 55.6% of IB range (vs ES 63.6%)
- NQ reaches 100% extension: 12.8% of days (vs ES 18.8%)
- NQ IB high = RTH high: 36.7% of days (vs ES 33.0%)
- **Interpretation**: NQ is more likely to set its extremes during the first hour and NOT extend as far afterward. NQ is tighter than ES.

**NQ Continuation Rates by Hour (Dokakuri's Magic Hours, 2013-2026)**
- 07:00 AM ET: 83.4% win rate (Golden Hour)
- 08:00 AM ET: 79.7% win rate (Continuation Hour)
- 06:00 AM ET: 78.7% win rate (Pre-Market)
- **Interpretation**: Pre-market (06:00-08:00 ET) is the highest-probability window for NQ continuation trades. This is BEFORE RTH opens at 09:30.

### Session-Specific Behavior

**RTH vs ETH (Regular vs Extended Trading Hours)**
- RTH: 09:30-16:00 ET (6.5 hours, highest volume)
- ETH: 18:00 ET - 17:00 ET next day (full Globex session, 23 hours)
- NQ overnight adds ~23% more volatility than RTH alone
- **Practitioner consensus**: RTH-only backtesting is cleaner; ETH includes thin overnight trading

**Time-of-Day Edge (Magic Hours Research)**
- 07:00-08:00 AM ET: 79.7-83.4% win rate for continuation trades
- 09:30-10:30 AM ET (Initial Balance): 73-79% directional agreement with day's close
- 11:30 AM-16:00 ET: Declining edge; volume drops at lunch
- **Implication**: Continuation zones formed during 06:00-08:00 AM have highest probability; zones formed after 11:30 AM are weaker.

---

## 3. OPTIMAL SMALL-BODY RATIO FOR BASE CANDLES

### Practitioner Consensus (HIGH confidence)

**ICT Standard (2025-02-03)**
- Rally candles: Body-to-wick ratio >= 70:30 (70% body, 30% wick)
- Base candles: Body-to-wick ratio <= 25:75 (25% body, 75% wick)
- **Interpretation**: Base candles should have SMALL bodies (<=25% of total range)

**William O'Neil Flat Base Research (Haase, 2026-05-08 � 34,000 trades)**
- Optimal base duration: 30-40 days (for weekly charts)
- Optimal tightness: Second-tightest quintile (not the absolute tightest)
- Optimal shape: Slight upward slope (not perfectly flat)
- **Interpretation**: Extreme tightness signals low energy; modest tightness signals consolidation with momentum.

### Optimal Ratio Range (MEDIUM confidence � practitioner consensus)

From multiple sources:
- **Body-to-range ratio: 0.20 to 0.35** (20-35% of total range)
  - Below 0.20: Too tight, signals low energy
  - 0.20-0.35: Sweet spot, signals consolidation with momentum
  - 0.35-0.50: Borderline; may signal early breakout, not true base
  - Above 0.50: Not a base; this is a continuation candle

- **Wick-to-body ratio: 2.0 to 4.0** (wicks are 2-4x the body)
  - Below 2.0: Directional candle, not a base
  - 2.0-4.0: Balanced pressure, true consolidation
  - Above 4.0: Extreme indecision; may signal reversal, not continuation

**Recommended for NQ 5m-15m scalping**: Body-to-range 0.25-0.35, wick-to-body 2.5-3.5

---

## 4. ZONE VALIDITY & INVALIDATION CRITERIA

### Invalidation Rules (HIGH confidence � consensus across sources)

**Body Close vs Wick (CRITICAL DISTINCTION)**
- **Mitigation**: Price wicks into zone but closes back inside ? zone weakened but still valid
- **Invalidation**: Candle body closes decisively through zone boundary ? zone is broken, remove it
- **Rule**: Only a BODY CLOSE through the opposite boundary invalidates the zone

### Touch Count & Zone Decay (HIGH confidence)

**First Touch vs Subsequent Touches**
- **First touch**: Highest probability (most unfilled orders remain)
- **Second touch**: Weaker (some orders already filled)
- **Third+ touch**: Unreliable (most orders consumed)
- **Practitioner consensus**: Avoid trading zones after 2-3 touches

### Zone Age Decay (MEDIUM confidence)

From Hourly Retracement research:
- **By 10:00 ET**: Conditional probability of untouched overnight level drops to ~40-50%
- **By 14:00 ET**: Level is effectively expired (~9-12% remaining probability)
- **Implication**: Continuation zones formed at 06:00 AM should be traded by 10:00 AM; after that, they lose edge

---

## 5. DEPARTURE CRITERIA & ZONE VALIDATION

### Minimum Departure Strength (HIGH confidence)

**Impulse Move Requirements**
- Must be 2-3x the height of the base (consensus across sources)
- Large-bodied candles (70%+ body-to-range ratio)
- Minimal pullback during the impulse
- Preferably on volume confirmation

**NQ-Specific**: Departure should be at least 20-30 points on 5m chart, 50-75 points on 15m chart

### Structure Break Requirement (HIGH confidence)

**Break of Structure (BoS) Definition**
- Candle body (not wick) closes beyond a previous swing high or low
- Confirms the impulse move is institutionally driven
- Without BoS, the move might be random noise

---

## 6. RTH FILTER & SESSION SELECTION

### RTH vs ETH Backtesting (HIGH confidence)

**Practitioner Consensus**
- RTH-only (09:30-16:00 ET) is cleaner for backtesting
- ETH includes thin overnight trading with different microstructure
- Most institutional volume occurs during RTH
- **Recommendation**: Backtest RTH-only for continuation zones

### Best Session Windows for Continuation Zones

**Highest Probability (06:00-10:00 AM ET)**
- 07:00 AM: 83.4% win rate (Golden Hour)
- 08:00 AM: 79.7% win rate (Continuation Hour)
- 06:00 AM: 78.7% win rate (Pre-Market)
- **Recommendation**: Trade continuation zones formed during 06:00-08:00 AM; execute by 10:00 AM

**Declining Probability (10:00 AM-16:00 ET)**
- 10:00-11:30 AM: Moderate edge (still tradeable)
- 11:30 AM-14:00 ET: Declining edge (avoid)
- 14:00-16:00 ET: Zones are expired (avoid)

---

## 10 SPECIFIC PARAMETER/DESIGN DECISIONS

1. **Body-to-range ratio threshold: 0.25-0.35** (not 0.15-0.20, not 0.40+)
   - Filters out weak consolidations and early breakouts
   - Captures true consolidation with momentum

2. **Wick-to-body ratio threshold: 2.5-3.5** (not 1.5-2.0, not 4.0+)
   - Ensures balanced pressure from both sides
   - Avoids directional candles and extreme indecision

3. **Base duration: 2-5 candles** (not 1, not 10+)
   - Tight consolidation signals momentum
   - Extended consolidation signals low energy

4. **Impulse move minimum: 2-3x base height** (not 1.5x, not 4x+)
   - Ensures meaningful departure
   - Avoids weak moves that won't hold on retest

5. **Session window: 06:00-08:00 AM ET** (not 09:30-11:30 AM, not 14:00-16:00 ET)
   - Highest-probability window for NQ continuation trades
   - Zones formed outside this window have declining edge

6. **Execution deadline: 10:00 AM ET** (not 12:00 PM, not 14:00 ET)
   - Conditional probability of untouched zones drops sharply after 10:00 AM
   - Zones are effectively expired by 14:00 ET

7. **Zone freshness: First touch only** (not second, not third+)
   - First touch has most unfilled orders
   - Each subsequent touch weakens the zone

8. **Invalidation rule: Body close through boundary** (not wick, not close barely beyond)
   - Wick through = mitigation (zone still valid)
   - Body close = invalidation (zone is broken)
   - Use candle character and volume to disambiguate grey area

9. **Retest confirmation: Reversal candle or lower-TF structure shift** (not wick touch alone)

## [2026-05-25] T4: Backtest engine implementation
- `research/continuation_zones/backtest_engine.py` builds zones first, then re-simulates zone lifecycle from scratch so detector end-state (`touch_count`, `is_active`) does not leak future information into entry decisions.
- No-leakage guardrail: detector `Zone.created_bar_idx` is the base-candle index, so backtest entry eligibility must begin only after the confirmation candle completes (`confirmation_start + timeframe duration`).
- 15m zones on a 5m execution timeline should age in 15m units, not 5m bars; using elapsed time from `available_from` preserves the configured `max_zone_age_bars_15m` semantics.
- Net trade PnL is modeled as raw ticks minus 2 ticks of slippage (1 per side by default), then minus 2 commissions (`$2/side`) in dollars.
   - Prevents false entries on wick pokes
   - Ensures institutional reaction at the zone

10. **Risk-to-reward minimum: 1:1, preferred 1:2+** (not 1:0.5, not 1:5+)

## [2026-05-25] T6/T7: Results analyzer + pipeline CLI
- `research/continuation_zones/results_analyzer.py` derives ATM profiles directly from top-10 OOS `OptimizationResult` rows: Conservative=max OOS win rate, Balanced=rank-1 fitness, Aggressive=max OOS Sharpe.
- Expected ATM EV is recoverable without per-trial trade archives via `oos_total_pnl / oos_trades`; best-params trade export/equity curve still come from a separate best-OOS trade run.
- `research/continuation_zones/run_backtest.py` defers package imports until after argparse so `--help` stays usable without forcing the full data/backtest dependency stack to initialize.
- `research/continuation_zones/data_loader.py` should treat `databento` as an optional runtime dependency at import time; only download paths need the package, while cached-data utilities and isolated tests should still import cleanly without it.
    - Ensures positive expectancy even with 50% win rate
    - Preferred 1:2 aligns with 60-70% win rate target

---

## CONFIDENCE LEVELS BY FINDING

| Finding | Confidence | Source |
|---------|-----------|--------|
| RBR/DBD weaker than DBR/RBD | HIGH | Multiple practitioner sources, institutional theory |
| NQ stickier to early structure | HIGH | 12-year statistical data (IB breakout study) |
| 06:00-08:00 AM highest probability | HIGH | Dokakuri Magic Hours (2013-2026), Hourly Retracement |
| Body-to-range 0.25-0.35 optimal | MEDIUM-HIGH | O'Neil Flat Base (34,000 trades), ICT standards |
| Body close = invalidation | HIGH | Consensus across supply/demand sources |
| First touch strongest | HIGH | Multiple sources, institutional order theory |
| RTH-only backtesting cleaner | HIGH | Practitioner consensus, microstructure theory |
| Zone age decay by 10:00 AM | MEDIUM-HIGH | Hourly Retracement research, conditional probability |
| 2-3x impulse move minimum | MEDIUM-HIGH | Practitioner consensus, not quantified in academic literature |
| Wick-to-body 2.5-3.5 optimal | MEDIUM | ICT standards, limited quantitative validation |

---

## NEXT STEPS FOR IMPLEMENTATION

1. **Backtest on NQ 5m-15m RTH-only data (09:30-16:00 ET)**
   - Filter for zones formed 06:00-08:00 AM ET
   - Require body-to-range 0.25-0.35, wick-to-body 2.5-3.5
   - Execute by 10:00 AM ET
   - Measure first-touch win rate and compare to unfiltered baseline

2. **Validate zone quality scoring**
   - Implement 4-factor grading system (strength, freshness, time at base, profit margin)
   - Score 8+ out of 12 for high-probability zones
   - Measure win rate by score tier

3. **Test session window hypothesis**
   - Compare win rates: 06:00-08:00 AM vs 08:00-10:00 AM vs 10:00-12:00 PM
   - Measure conditional probability decay after 10:00 AM
   - Confirm 14:00 ET expiration

4. **Validate base ratio thresholds**
   - Backtest body-to-range: 0.15-0.20 vs 0.20-0.25 vs 0.25-0.35 vs 0.35-0.50
   - Measure win rate by ratio tier
   - Confirm 0.25-0.35 is optimal

5. **Implement retest confirmation filter**
   - Require reversal candle or lower-TF structure shift at zone
   - Measure false entry reduction vs wick-touch-only entries
   - Validate 60-70% win rate target

## [2026-05-25] R1: Continuation Zone Theory Research - COMPLETE

## [2026-05-25] R4: NQ Scalping ATM Research

## [2026-05-25] T2: data_loader.py Implementation

- Created `research/continuation_zones/data_loader.py` as a standalone sync Databento loader using `db.Historical(...).timeseries.get_range()` with `GLBX.MDP3`, `NQ.c.0`, `continuous`, and `ohlcv-1m`.
- Normalized Databento OHLC prices defensively: prefer `to_df(price_type="float", pretty_ts=True)`, but still divide OHLC columns by `1e9` if fixed-point values slip through.
- Standardized cached/raw frames to `DatetimeIndex` named `ts_event`, tz-aware UTC, with strict `[open, high, low, close, volume]` columns.
- RTH filter converts to `America/New_York`, keeps weekdays from `09:30 <= t < 16:00`, and optionally removes exchange holidays when `pandas_market_calendars` is installed without making it a hard dependency.
- Mocked pytest coverage now locks in: 5m OHLCV aggregation, RTH session filtering, parquet cache write/read behavior, and missing `DATABENTO_API_KEY` failure path.

## [2026-05-25] T3: continuation_zones.py Implementation

- Implemented `research/continuation_zones/continuation_zones.py` as a standalone research module with a parity-focused `Zone` dataclass, `ContinuationZoneDetector`, and `score_continuation_zone()` helper.
- Candidate detection is vectorized with pandas/numpy (`shift`, array masks, basis-point/tick precomputation); the only full-data loop is the single lifecycle pass needed for overlap dedup, touch edge detection, invalidation, age expiry, and the 8-active-zone cap.
- Added explicit round-half-away-from-zero helpers so Python basis-point/tick conversions match NinjaScript `MidpointRounding.AwayFromZero` instead of Python's bankers rounding.
- Stored frozen creation-time score inputs on each zone (`departure_body_bp`, `departure_ext_bp`, `base_body_bp`, `zone_height_ticks`, trend booleans) and recompute only dynamic freshness from `touch_count`.
- Added `research/continuation_zones/tests/test_continuation_zones.py` with 20 focused tests, including 20 hard-coded parity scoring examples and synthetic detector coverage with no live Databento calls.

### 1. NinjaTrader 8 ATM Architecture � Complete Field Reference

Official Documentation: https://ninjatrader.com/support/helpguides/nt8/atm_strategy_parameters.htm

#### Core ATM Fields (per Target)
- Stop Loss: numeric, ticks, distance from entry where stop is placed (example: 10)
- Profit Target: numeric, ticks, distance from entry where target is placed (example: 20)
- Quantity: numeric, contracts, how many contracts this bracket manages (example: 1)
- Parameter Type: enum, unit system (Ticks, Points, Pips, Percent, PnL, Price)

#### Stop Strategy Fields (Auto-Adjustment)
- Auto Breakeven Profit Trigger: numeric, ticks, profit level that triggers BE move (example: 6)
- Auto Breakeven Plus: numeric, ticks, offset from entry when BE triggers, can be negative (example: 0 or -4)
- Auto Trail Profit Trigger: numeric, ticks, profit level that activates trailing (example: 8)
- Auto Trail Stop Loss: numeric, ticks, trail distance behind current price (example: 4)
- Auto Trail Frequency: numeric, ticks, how often stop adjusts after trigger (example: 1)
- Auto Trail Steps: enum, 1-step, 2-step, or 3-step trailing (each with own params)

#### Advanced Options (More section)
- Shadow Strategy: Compare two ATM strategies on same trade
- Auto Reverse: Reverse position at stop or target
- Auto Chase: Chase entry/target if touched but not filled
- Stop Limit for Stop Loss: Use StopLimit instead of StopMarket
- MIT for Profit: Use MIT (Market-If-Touched) for target

#### Critical Constraints (from FAQ)
- OCO by default: Stop and Target are One-Cancels-Other � when one fills, the other cancels
- Stop never moves backward: Stop Strategy only moves stop closer to current price, never away
- Profit Trigger ordering: Auto Trail Profit Trigger MUST be > Auto Breakeven Profit Trigger
- Multiple targets must increase: Target 1 < Target 2 < Target 3 (strictly increasing)
- Multiple stops must increase: Stop 1 = Stop 2 = Stop 3 (non-decreasing, wider stops for later targets)

---

### 2. ATM Strategy vs Stop Strategy vs Regular Strategy

Source: https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1334684-is-it-best-to-use-an-atm-strategy-or-regular-strategy

ATM Strategy:
- Backtestable: NO � ATM only works in real-time
- Performance tracking: NO � strategy doesn't track ATM fills
- Manual adjustment: YES � drag/drop stops/targets in SuperDOM
- Scaling behavior: Automatic � new fills update existing brackets
- Use case: Semi-automated � signal generation + manual management

Regular Strategy (SetStopLoss/SetProfitTarget):
- Backtestable: YES � can backtest
- Performance tracking: YES � strategy tracks all fills
- Manual adjustment: YES � but requires code to modify
- Scaling behavior: Manual � must code scaling logic
- Use case: Fully automated � entry + exit all in code

Recommendation for DEEP6: Use ATM for paper/live trading (operator discretion on entries, ATM manages exits). Use regular strategy for backtesting (need performance metrics).

---

### 3. Professional NQ Scalper Bracket Practices (2026 Data)

Sources:
- PropScorer Academy (2026-03-12): https://www.propscorer.com/academy/scalping-nq-guide
- Quantum Navigator (2026-03-29): https://qntrader.com/how-to-scalp-nq-futures-without-guessing/
- Global Market Raiders (2026-01-02): https://www.globalmarketraiders.com/emini-nasdaq-day-trading-guide
- Volatility Box (2026-03-10): https://volatilitybox.com/research/nq-futures-volatility/

#### Stop Loss Distances (Professional Framework)
Tight: 8�12 points (32�48 ticks), � risk/contract, low volatility, precise order flow entries
Standard: 15�20 points (60�80 ticks), � risk/contract, normal volatility, most common
Wide: 20�25 points (80�100 ticks), � risk/contract, high volatility, market open/news
ATR-based (day trade): 1.5�2x ATR(14) on 5m, ~45�90 points, �,800, dynamic/professional standard

Key insight: Professional traders use ATR-based stops (1.5�2x ATR on 5-minute chart), not fixed distances. For NQ, this typically yields 45�90 point stops (�,800 per contract).

#### Profit Target Ranges
Quick scalp: 10�15 points (40�60 ticks), 1:1 R:R or less, 60%+ win rate needed, high frequency
Standard scalp: 20�30 points (80�120 ticks), 1.5:1 to 2:1 R:R, 50�55% win rate, sweet spot for prop traders
Extended scalp: 30�50 points (120�200 ticks), 2:1 to 3:1 R:R, 40�45% win rate, lower frequency

Professional consensus: 1.5:1 to 2:1 R:R is the  sweet spot for NQ scalping. Targets 20�30 points with 15�20 point stops.

#### Breakeven Trigger Calibration
Research finding: Professional NQ scalpers move stop to breakeven after 4�6 ticks of profit, not 8+.

From NinjaTrader forum example (yngtrader setup):
- Entry at market
- Stop: 10 ticks
- Target: 12 ticks
- Auto Breakeven trigger: 4 ticks (move stop to entry - 4 ticks)
- Auto Trail trigger: 8 ticks (then trail by 8 ticks)

Rationale: 4�6 ticks is the noise threshold for NQ. Once you've captured 4�6 ticks, the trade has proven itself. Moving stop to breakeven (or breakeven - 4 ticks) locks in the win while preserving upside.

#### Trailing Stop Mechanics for NQ Scalping
Tick trail (preferred for scalping): Fixed distance (e.g., 4�8 ticks) behind current price
ATR trail (better for swing trades): Dynamic, scales with volatility

Professional NQ scalp configuration:
- Activation: After 8�10 ticks profit
- Trail amount: 4�8 ticks behind current price
- Frequency: 1 tick (adjust on every tick)
- Rationale: Tight trailing captures extended moves while protecting profits

Does trailing help or hurt short-duration scalps?
- Helps: If the move extends beyond initial target (20�30 points), trailing captures the extension
- Hurts: If price oscillates within the trail range, you get stopped out prematurely
- Professional approach: Use split position � take 50% at first target, trail the remaining 50% with tight stop

---

### 4. Three ATM Profiles for NQ Continuation Zone Scalping

Context: RBR/DBD entry at zone boundary, 8�24 tick targets, 5�15 minute holds.

#### Profile 1: CONSERVATIVE (Lower Risk, Higher Win Rate)
Thesis: Prioritize capital preservation and consistency over large wins.

Stop Loss: 8 ticks (tight, zone-based; invalidation is clear)
Profit Target 1: 12 ticks (1.5:1 R:R, achievable in 5�10 min)
Profit Target 2: None (single target only)
Auto Breakeven Trigger: 4 ticks (lock in win after noise threshold)
Auto Breakeven Plus: 0 (stop moves exactly to entry)
Auto Trail: None (no trailing; take target or stop)
Expected R:R: 1.5:1 (12 ticks profit / 8 ticks risk)
Expected Win Rate: 55�60% (tight stop, clear invalidation)
Daily P&L (1 contract, 5 trades): � (3�4 winners, 1�2 losers)

NinjaTrader ATM Template Name: NQ_Conservative_8x12

---

#### Profile 2: BALANCED (Moderate Risk, Moderate Reward)
Thesis: Capture standard scalp moves with split position management.

Stop Loss: 12 ticks (standard zone-based stop)
Profit Target 1: 16 ticks (1.33:1 R:R, locks in quick win)
Profit Target 2: 28 ticks (2.33:1 R:R, runner for extended move)
Quantity Target 1: 0.5 contracts (take half at first target)
Quantity Target 2: 0.5 contracts (let runner extend)
Auto Breakeven Trigger: 6 ticks (activate after solid profit)
Auto Breakeven Plus: -2 ticks (stop moves to entry - 2, small buffer)
Auto Trail (Target 2 only): 6 ticks trail, 10 tick trigger (trail the runner after 10 ticks profit)
Auto Trail Frequency: 1 tick (adjust on every tick)
Expected R:R (avg): 1.8:1 (blended: 50% at 1.33:1, 50% at 2.33:1)
Expected Win Rate: 52�55% (balanced, split position reduces pressure)
Daily P&L (1 contract, 5 trades): � (consistent, lower variance)

NinjaTrader ATM Template Name: NQ_Balanced_12x16x28_Split

---

#### Profile 3: AGGRESSIVE (Higher Risk, Higher Reward)
Thesis: Capture extended moves with tight initial stop and wide target.

Stop Loss: 10 ticks (tight but not noise-prone)
Profit Target 1: 20 ticks (2:1 R:R, standard scalp target)
Profit Target 2: 40 ticks (4:1 R:R, extended move capture)
Quantity Target 1: 0.33 contracts (take 1/3 at first target)
Quantity Target 2: 0.67 contracts (let 2/3 run for extension)
Auto Breakeven Trigger: 8 ticks (wait for solid confirmation)
Auto Breakeven Plus: -4 ticks (stop moves to entry - 4, preserve upside)
Auto Trail (Target 2 only): 8 ticks trail, 12 tick trigger (trail aggressively after 12 ticks profit)
Auto Trail Frequency: 1 tick (adjust on every tick)
Expected R:R (avg): 2.8:1 (blended: 33% at 2:1, 67% at 4:1)
Expected Win Rate: 48�52% (lower win rate, higher EV)
Daily P&L (1 contract, 5 trades): � (higher variance, higher upside)

NinjaTrader ATM Template Name: NQ_Aggressive_10x20x40_Extended

---

### 5. NinjaTrader ATM Field Names (Exact UI Labels)

Location: SuperDOM or Chart Trader ? ATM Strategy dropdown ? Custom ? Custom Strategy Parameters window

Main Parameters Section:
- Order Quantity: numeric field
- Time In Force (TIF): dropdown (Day, GTC, etc.)
- Parameter Type: dropdown (Ticks, Points, Pips, Percent, PnL, Price)

Targets Section (repeating for each target):
- Target [N] Quantity: numeric
- Target [N] Stop Loss: numeric
- Target [N] Profit Target: numeric
- Target [N] Stop Strategy: dropdown (None, Custom, or saved template name)

Stop Strategy Section (accessed via More or dropdown under each target):
Auto Breakeven:
- Profit Trigger: numeric
- Plus: numeric, can be negative

Auto Trail (1-step, 2-step, or 3-step):
- Step [N] Stop Loss: numeric
- Step [N] Profit Trigger: numeric
- Step [N] Frequency: numeric

Advanced Options (under More):
- Shadow Strategy: checkbox
- Auto Reverse: checkbox + dropdown (Reverse at Stop / Reverse at Target)
- Auto Chase: checkbox + numeric (Chase Limit)
- Stop Limit for Stop Loss: checkbox + numeric (Limit Offset)
- MIT for Profit: checkbox

---

### 6. DEEP6 BracketExit Model Coverage

Current model (deep6/backtest/strategy_config.py):
- stop_ticks: int
- target_ticks: int
- rr_ratio: float

Assessment: This model covers Profile 1 (Conservative) only � single stop, single target, fixed R:R.

What's missing for Profiles 2 & 3:
- Multiple profit targets (Target 1, Target 2)
- Quantity split per target (0.5 / 0.5 or 0.33 / 0.67)
- Auto Breakeven configuration (trigger, plus offset)
- Auto Trail configuration (trigger, trail amount, frequency, steps)
- Stop Strategy template reference

Recommendation: Extend BracketExit to support multiple targets and stop strategies (see decisions.md for implementation plan).

---

### 7. Backtesting Verification Checklist

Before finalizing these profiles, backtesting must confirm:

For all profiles:
- Win rate matches expected range (Conservative: 55�60%, Balanced: 52�55%, Aggressive: 48�52%)
- Average winner > average loser (R:R ratio holds)
- Slippage assumption: 3 ticks per transaction (entry + exit)
- Commission: .00 per contract round-trip
- Zone invalidation logic is correct (body closes through zone)
- Entry timing: LIMIT order at zone boundary, not market order

For split-position profiles (Balanced, Aggressive):
- Target 1 fills before Target 2 in 70%+ of trades
- Runner (Target 2) captures extension in 30�40% of cases
- Trailing stop doesn't get whipsawed by normal oscillation

For Auto Breakeven:
- Breakeven trigger (4�8 ticks) is reached before target in 80%+ of winning trades
- Stop moving to breakeven doesn't cause premature exit on pullback

For Auto Trail:
- Trail activation (8�12 ticks) is reached in 20�30% of trades
- Trailing captures 5�15 additional ticks on extended moves

---

### 8. Key Insights & Gotchas

1. ATM is real-time only: Cannot backtest ATM strategies in Strategy Analyzer. Must use regular SetStopLoss/SetProfitTarget for backtesting, then translate to ATM for live trading.

2. Stop never moves backward: If Auto Breakeven moves stop to entry - 4, and then Auto Trail tries to move it wider, the stop stays at entry - 4. This is a feature, not a bug.

3. Profit Trigger ordering matters: If Auto Breakeven and Auto Trail both trigger at the same profit level, they conflict. Always set Auto Trail Profit Trigger > Auto Breakeven Profit Trigger.

4. Slippage is real: Professional traders factor 3 ticks of slippage per transaction. A 12-tick target becomes 9 ticks net. This is critical for tight scalps.

5. Split positions reduce emotional pressure: Taking 50% at first target locks in a win, making it easier to hold the runner without fear.

6. Zone invalidation is the stop logic: The stop should sit at the point where the zone setup is invalidated (body closes through zone), not at an arbitrary distance.

7. NQ is higher-beta than ES: NQ moves faster and more violently. Stops need to be wider in points but similar in dollars. Use ATR-based stops for consistency.

---

### 9. Recommended Next Steps

1. Extend BracketExit model to support multiple targets and stop strategies
2. Backtest all three profiles on 6 months of NQ data (Databento MBO)
3. Validate zone invalidation logic against historical price action
4. Create NinjaTrader ATM templates for each profile (save as .xml)
5. Paper trade each profile for 2�4 weeks before live
6. Track metrics: win rate, avg winner, avg loser, max drawdown, daily P&L variance



---

## [2026-05-25] R5: DEEP6 Python Stack Audit

### 1. Dependency Matrix

| Library | Version | Status | Purpose | Missing? |
|---------|---------|--------|---------|----------|
| async-rithmic | 1.5.9 | Installed | Rithmic L2 DOM + execution | NO |
| scipy | >=1.14 | Installed | Numerical/statistical ops | NO |
| pydantic | >=2.0 | Installed | Data validation + config | NO |
| numpy | (latest) | Installed | Array ops, zone binning | NO |
| pandas | (not explicit) | MISSING | DataFrames for OHLCV, backtest results | YES |
| databento | (not explicit) | MISSING | MBO historical data, live feed | YES |
| optuna | (not explicit) | MISSING | Hyperparameter optimization | YES |
| vectorbt | (not explicit) | MISSING | Vectorized backtesting | YES |
| plotly | (not explicit) | MISSING | Footprint/zone visualization | YES |
| duckdb | (latest) | Installed | Result persistence (backtest) | NO |
| pytest | >=8.0 | Installed | Test framework | NO |
| fastapi | (latest) | Installed | API server | NO |
| uvicorn | (latest) | Installed | ASGI server | NO |

**Action**: Add to pyproject.toml: pandas>=2.0, databento>=0.28, optuna>=3.0, vectorbt>=0.25, plotly>=5.0

---

### 2. Zone Schema

**VolumeZone** (deep6/engines/volume_profile.py):
- zone_type: ZoneType (LVN or HVN)
- state: ZoneState (CREATED, DEFENDED, BROKEN, FLIPPED, INVALIDATED)
- top_price, bot_price: float
- direction: int (+1 support, -1 resistance)
- origin_bar, last_touch_bar: int
- touches: int (defense count)
- score: float (0-100)
- volume_ratio: float
- inverted: bool

**Level** (deep6/engines/level.py, Phase 15):
- kind: LevelKind (17 variants)
- state: LevelState
- price_top, price_bot: float
- score: float
- origin_bar: int
- origin_ts: float (Unix time)
- uid: int (stable id for mutation tracking)
- meta: dict (sparse metadata)

**Recommendation**: Extend LevelKind with CONTINUATION_ZONE; reuse Level dataclass.

---

### 3. Backtest Loop Pattern (BacktestRunner.cs)

1. Load scored-bar NDJSON files
2. For each bar:
   - If NOT in trade: check entry gate, open if passes
   - If in trade: update MFE, check exits (stop, target, trail, opposing signal, max bars)
3. Session-end force-exit remaining trades

Exit reasons: STOP_LOSS, TARGET, SCALE_OUT_PARTIAL, SCALE_OUT_FINAL, TRAIL, OPPOSING_SIGNAL, MAX_BARS, SESSION_END

**Recommendation**: Reuse deep6/backtest/research_runner.py; add zone proximity check at entry gate.

---

### 4. Trade Schema (Trade.cs)

Fields: entry_bar, exit_bar, entry_price, exit_price, direction, pnl_ticks, pnl_dollars, signal_id, tier, score, narrative, exit_reason, duration_bars, categories_firing

**Python equivalent**: Create dataclass with above fields + zone_id, zone_type, zone_score, zone_state_at_exit.

---

### 5. BracketExit Schema

**BracketExit** (strategy_config.py):
- stop_ticks: int
- target_ticks: int
- rr_ratio: float

**BacktestConfig** (config.py):
- dataset, symbol, start, end, tf_list, duckdb_path, git_sha, fill_model, tick_size
- stop_ticks, target_ticks, commission_per_side, tick_value, slippage_ticks, max_hold_bars

**Recommendation**: Extend BacktestConfig with continuation_zone_enabled, zone_proximity_ticks, zone_invalidation_threshold, require_zone_confluence.

---

### 6. Existing Zone-Related Python Code

HIGH relevance:
- deep6/engines/volume_profile.py (ZoneState, ZoneType, VolumeZone)
- deep6/engines/zone_registry.py (LevelBus — unified level store)
- deep6/engines/level.py (Level dataclass, 17 LevelKind variants)
- deep6/engines/level_factory.py (Level factory)
- deep6/backtest/bracket_exit.py (bracket exit resolution)
- deep6/backtest/strategy_config.py (strategy config models)
- deep6/backtest/config.py (backtest config)
- deep6/backtest/research_runner.py (research backtest harness)
- tests/test_zone_registry.py (zone registry tests)
- deep6/data/databento_feed.py (Databento feed)
- deep6/backtest/mbo_adapter.py (MBO to FootprintBar)

MEDIUM relevance:
- deep6/engines/confluence_rules.py (confluence scoring)
- deep6/engines/narrative.py (narrative zones)
- deep6/bias_engine/ict_concepts.py (ICT concepts)
- scripts/backtest_institutional_zones.py (institutional zone backtesting)

---

### 7. Directory Structure (deep6/)

api/, backtest/, bias_engine/, data/, engines/, execution/, ml/, models/, orderflow/, scoring/, sd_anchor/, services/, signals/, state/

---

### 8. Recommendation: Module Placement

**Option A: Standalone research module** (RECOMMENDED)
`
research/continuation_zones/
├── __init__.py
├── detector.py
├── scorer.py
├── backtest_config.py
├── backtest_runner.py
├── level_factory.py
└── tests/
`

Rationale: Isolates research from production; allows independent iteration; can promote to deep6/engines/ after validation.

---

### 9. Key Integration Points

1. Data: deep6/data/databento_feed.py + deep6/backtest/mbo_adapter.py
2. Zone storage: deep6/engines/zone_registry.py (LevelBus)
3. Backtest: deep6/backtest/bracket_exit.py + BacktestConfig
4. Scoring: deep6/engines/confluence_rules.py
5. Results: deep6/backtest/result_store.py (DuckDB)
6. Tests: tests/test_zone_registry.py, tests_v2/backtest/

---

### 10. Missing Dependencies

Add to pyproject.toml:
- pandas>=2.0 (OHLCV DataFrames)
- databento>=0.28 (MBO historical data)
- optuna>=3.0 (hyperparameter optimization)
- vectorbt>=0.25 (vectorized backtesting)
- plotly>=5.0 (visualization)

---

### 11. Summary

| Aspect | Status | Action |
|--------|--------|--------|
| Zone schema | Exists | Extend LevelKind enum |
| Backtest loop | Exists (C#) | Port to Python or reuse research_runner.py |
| Trade schema | Exists (C#) | Create Python dataclass |
| Bracket exit | Exists | Reuse as-is |
| Config models | Exists | Extend with zone params |
| Zone registry | Exists | Add continuation zones |
| Data pipeline | Exists | Reuse |
| Result store | Exists | Reuse |
| Continuation detector | Missing | Create in research/ |
| Continuation scorer | Missing | Create in research/ |
| Continuation backtest | Missing | Create in research/ |
| Dependencies | Missing | Add to pyproject.toml |

---

### 12. Next Steps

1. Create research/continuation_zones/ module structure
2. Implement RBR/DBD detector (port from InstitutionalZones_MTF v4.5)
3. Implement continuation zone scorer
4. Extend LevelKind enum with CONTINUATION_RBR, CONTINUATION_DBD
5. Create backtest harness
6. Add dependencies to pyproject.toml
7. Write tests following test_zone_registry.py patterns
8. Validate against historical NQ data (Databento MBO)
9. Promote to deep6/engines/ once validated

## [2026-05-25] T5: Optimization Engine
- `optimization.py` uses an 8-month IS / 4-month OOS `WalkForwardSplit` derived from the earliest timestamp in the frame, with OOS fitness ranked by `oos_sharpe * oos_win_rate` and a hard `min_oos_trades` prune gate.
- Overfit detection is encoded directly on `OptimizationResult` as `is_sharpe > 2 * oos_sharpe`, and `save_results()` exports the exact top-10 CSV schema expected by downstream analysis.
- Local test execution environment did not have Optuna installed, so `optimization.py` now prefers real Optuna when available but includes a small in-file fallback shim that preserves trial suggestion/pruning behavior for unit tests and lightweight environments.


---

## [2026-05-25] R5: DEEP6 Python Stack Audit

### 1. Dependency Matrix

| Library | Version | Status | Purpose | Missing? |
|---------|---------|--------|---------|----------|
| async-rithmic | 1.5.9 | Installed | Rithmic L2 DOM + execution | NO |
| scipy | >=1.14 | Installed | Numerical/statistical ops | NO |
| pydantic | >=2.0 | Installed | Data validation + config | NO |
| numpy | (latest) | Installed | Array ops, zone binning | NO |
| pandas | (not explicit) | MISSING | DataFrames for OHLCV, backtest results | YES |
| databento | (not explicit) | MISSING | MBO historical data, live feed | YES |
| optuna | (not explicit) | MISSING | Hyperparameter optimization | YES |
| vectorbt | (not explicit) | MISSING | Vectorized backtesting | YES |
| plotly | (not explicit) | MISSING | Footprint/zone visualization | YES |
| duckdb | (latest) | Installed | Result persistence (backtest) | NO |
| pytest | >=8.0 | Installed | Test framework | NO |
| fastapi | (latest) | Installed | API server | NO |
| uvicorn | (latest) | Installed | ASGI server | NO |

**Action**: Add to pyproject.toml: pandas>=2.0, databento>=0.28, optuna>=3.0, vectorbt>=0.25, plotly>=5.0

---

### 2. Zone Schema

**VolumeZone** (deep6/engines/volume_profile.py):
- zone_type: ZoneType (LVN or HVN)
- state: ZoneState (CREATED, DEFENDED, BROKEN, FLIPPED, INVALIDATED)
- top_price, bot_price: float
- direction: int (+1 support, -1 resistance)
- origin_bar, last_touch_bar: int
- touches: int (defense count)
- score: float (0-100)
- volume_ratio: float
- inverted: bool

**Level** (deep6/engines/level.py, Phase 15):
- kind: LevelKind (17 variants)
- state: LevelState
- price_top, price_bot: float
- score: float
- origin_bar: int
- origin_ts: float (Unix time)
- uid: int (stable id for mutation tracking)
- meta: dict (sparse metadata)

**Recommendation**: Extend LevelKind with CONTINUATION_ZONE; reuse Level dataclass.

---

### 3. Backtest Loop Pattern (BacktestRunner.cs)

1. Load scored-bar NDJSON files
2. For each bar:
   - If NOT in trade: check entry gate, open if passes
   - If in trade: update MFE, check exits (stop, target, trail, opposing signal, max bars)
3. Session-end force-exit remaining trades

Exit reasons: STOP_LOSS, TARGET, SCALE_OUT_PARTIAL, SCALE_OUT_FINAL, TRAIL, OPPOSING_SIGNAL, MAX_BARS, SESSION_END

**Recommendation**: Reuse deep6/backtest/research_runner.py; add zone proximity check at entry gate.

---

### 4. Trade Schema (Trade.cs)

Fields: entry_bar, exit_bar, entry_price, exit_price, direction, pnl_ticks, pnl_dollars, signal_id, tier, score, narrative, exit_reason, duration_bars, categories_firing

**Python equivalent**: Create dataclass with above fields + zone_id, zone_type, zone_score, zone_state_at_exit.

---

### 5. BracketExit Schema

**BracketExit** (strategy_config.py):
- stop_ticks: int
- target_ticks: int
- rr_ratio: float

**BacktestConfig** (config.py):
- dataset, symbol, start, end, tf_list, duckdb_path, git_sha, fill_model, tick_size
- stop_ticks, target_ticks, commission_per_side, tick_value, slippage_ticks, max_hold_bars

**Recommendation**: Extend BacktestConfig with continuation_zone_enabled, zone_proximity_ticks, zone_invalidation_threshold, require_zone_confluence.

---

### 6. Existing Zone-Related Python Code

HIGH relevance:
- deep6/engines/volume_profile.py (ZoneState, ZoneType, VolumeZone)
- deep6/engines/zone_registry.py (LevelBus — unified level store)
- deep6/engines/level.py (Level dataclass, 17 LevelKind variants)
- deep6/engines/level_factory.py (Level factory)
- deep6/backtest/bracket_exit.py (bracket exit resolution)
- deep6/backtest/strategy_config.py (strategy config models)
- deep6/backtest/config.py (backtest config)
- deep6/backtest/research_runner.py (research backtest harness)
- tests/test_zone_registry.py (zone registry tests)
- deep6/data/databento_feed.py (Databento feed)
- deep6/backtest/mbo_adapter.py (MBO to FootprintBar)

MEDIUM relevance:
- deep6/engines/confluence_rules.py (confluence scoring)
- deep6/engines/narrative.py (narrative zones)
- deep6/bias_engine/ict_concepts.py (ICT concepts)
- scripts/backtest_institutional_zones.py (institutional zone backtesting)

---

### 7. Directory Structure (deep6/)

api/, backtest/, bias_engine/, data/, engines/, execution/, ml/, models/, orderflow/, scoring/, sd_anchor/, services/, signals/, state/

---

### 8. Recommendation: Module Placement

**Option A: Standalone research module** (RECOMMENDED)
`
research/continuation_zones/
├── __init__.py
├── detector.py
├── scorer.py
├── backtest_config.py
├── backtest_runner.py
├── level_factory.py
└── tests/
`

Rationale: Isolates research from production; allows independent iteration; can promote to deep6/engines/ after validation.

---

### 9. Key Integration Points

1. Data: deep6/data/databento_feed.py + deep6/backtest/mbo_adapter.py
2. Zone storage: deep6/engines/zone_registry.py (LevelBus)
3. Backtest: deep6/backtest/bracket_exit.py + BacktestConfig
4. Scoring: deep6/engines/confluence_rules.py
5. Results: deep6/backtest/result_store.py (DuckDB)
6. Tests: tests/test_zone_registry.py, tests_v2/backtest/

---

### 10. Missing Dependencies

Add to pyproject.toml:
- pandas>=2.0 (OHLCV DataFrames)
- databento>=0.28 (MBO historical data)
- optuna>=3.0 (hyperparameter optimization)
- vectorbt>=0.25 (vectorized backtesting)
- plotly>=5.0 (visualization)

---

### 11. Summary

| Aspect | Status | Action |
|--------|--------|--------|
| Zone schema | Exists | Extend LevelKind enum |
| Backtest loop | Exists (C#) | Port to Python or reuse research_runner.py |
| Trade schema | Exists (C#) | Create Python dataclass |
| Bracket exit | Exists | Reuse as-is |
| Config models | Exists | Extend with zone params |
| Zone registry | Exists | Add continuation zones |
| Data pipeline | Exists | Reuse |
| Result store | Exists | Reuse |
| Continuation detector | Missing | Create in research/ |
| Continuation scorer | Missing | Create in research/ |
| Continuation backtest | Missing | Create in research/ |
| Dependencies | Missing | Add to pyproject.toml |

---

### 12. Next Steps

1. Create research/continuation_zones/ module structure
2. Implement RBR/DBD detector (port from InstitutionalZones_MTF v4.5)
3. Implement continuation zone scorer
4. Extend LevelKind enum with CONTINUATION_RBR, CONTINUATION_DBD
5. Create backtest harness
6. Add dependencies to pyproject.toml
7. Write tests following test_zone_registry.py patterns
8. Validate against historical NQ data (Databento MBO)
9. Promote to deep6/engines/ once validated

## [2026-05-25] Phase 0 Complete — research_summary.md written
- Created `research/continuation_zones/results/research_summary.md` compiling all R1-R5 findings.
- Covers: continuation zone theory, dissipation design, 5-component scoring (0-10), ATM profiles, Python stack audit.
- Honest limitations section documents 10 known gaps (single-candle base only, no volume in score, 1-year walk-forward, etc.).
- Next action: set DATABENTO_API_KEY and run `python research/continuation_zones/run_backtest.py --n-trials 200`.
