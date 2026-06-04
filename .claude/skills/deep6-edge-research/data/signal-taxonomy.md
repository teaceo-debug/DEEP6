# DEEP6 Signal Taxonomy — Complete Reference

All 44 signals in the deep6v2 system, organized by category.
Each entry includes: detection logic, data requirements, expected edge.

---

## ABSORPTION (weight: 20.0)

### ABS_01 — Classic Wick Absorption
**File**: `deep6v2/signals/absorption.py`
**Logic**: High volume bar + wick extends beyond body + delta near zero in wick zone
**Data**: bar.bid_volumes, bar.ask_volumes, bar.delta, bar.total_volume, ctx.atr
**Direction**: Bearish wick at top → BEARISH signal (sellers absorbed). Bullish wick at bottom → BULLISH.
**Expected edge**: HIGH (confirmed in zones strategy variant D)
**Failure mode**: Fires on all wicks regardless of context — needs level confluence

### ABS_02 — Passive Absorption
**File**: `deep6v2/signals/absorption.py`
**Logic**: Large volume at bar extreme, price holds away, low body/range ratio
**Data**: bar.high/low, bar.total_volume, ctx.atr
**Direction**: Volume at high = BEARISH, volume at low = BULLISH
**Expected edge**: MEDIUM-HIGH

### ABS_03 — Stopping Volume
**File**: `deep6v2/signals/absorption.py`
**Logic**: POC in upper/lower wick (volume concentrated at extreme), total volume > threshold
**Data**: bar.poc_price, bar.high/low, bar.total_volume, ctx.atr
**Direction**: POC in upper wick → BEARISH, lower wick → BULLISH
**Expected edge**: MEDIUM

### ABS_04 — Effort vs Result
**File**: `deep6v2/signals/absorption.py`
**Logic**: High volume bar, narrow range relative to ATR (lots of effort, little movement)
**Data**: bar.total_volume, bar.high-bar.low, ctx.atr
**Direction**: Delta sign → BULLISH if delta > 0, BEARISH if delta < 0
**Expected edge**: MEDIUM (high N, inconsistent PF)

---

## EXHAUSTION (weight: 15.7)

### EXH_01 — Zero Print
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: Price level exists in range with zero bid AND zero ask volume
**Data**: bar.bid_volumes, bar.ask_volumes
**Direction**: Zero print at high → BEARISH, at low → BULLISH
**Expected edge**: HIGH but low N (rare condition)
**Note**: Most reliable on synthesized data when volume distribution has gaps

### EXH_02 — Exhaustion Print
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: High single-side volume at bar extreme, no follow-through (delta reverses next bar)
**Data**: bar.ask_volumes (at high), bar.bid_volumes (at low), bar.delta
**Direction**: Ask exhaustion at high → BEARISH, bid exhaustion at low → BULLISH
**Expected edge**: HIGH when confirmed by next-bar delta

### EXH_03 — Thin Print
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: Volume at extreme price < 5% of bar's maximum level volume
**Data**: bar.bid_volumes or bar.ask_volumes at extreme
**Direction**: Thin at high → BEARISH, thin at low → BULLISH
**Expected edge**: MEDIUM (fires often, moderate PF)

### EXH_04 — Fat Print
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: Very high volume at a price + delta neutral at that price = absorption of exhaustion
**Data**: bar.bid_volumes + bar.ask_volumes at price, bar.delta at that level
**Direction**: High volume + neutral delta at extreme
**Expected edge**: MEDIUM-HIGH

### EXH_05 — Fading Momentum
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: Price extends in one direction over 3+ bars while CVD fails to confirm (delta divergence)
**Data**: ctx.price_history (3 bars), ctx.cvd_history, ctx.delta_history
**Direction**: Price up + CVD down → BEARISH. Price down + CVD up → BULLISH
**Expected edge**: HIGH — most consistent with time-of-day filtering
**Note**: Gated by delta trajectory (EXH_07): only fires when delta trend disagrees with price

### EXH_06 — Bid/Ask Fade
**File**: `deep6v2/signals/exhaustion.py`
**Logic**: Aggressive volume at extreme drops >40% vs prior bar
**Data**: Prior bar bid/ask at extreme vs current
**Direction**: Ask fade at high → BEARISH, bid fade at low → BULLISH
**Expected edge**: MEDIUM

---

## IMBALANCE (weight: 25.0 — highest)

### IMB_01 — Single Imbalance
**File**: `deep6v2/signals/imbalance.py`
**Logic**: One price level where ask_vol / bid_vol > 3.0 (bullish) or bid/ask > 3.0 (bearish)
**Data**: bar.bid_volumes, bar.ask_volumes per price level
**Expected edge**: MEDIUM (fires very frequently)

### IMB_02 — Multiple Imbalance
Same as IMB_01 but requires 2+ consecutive imbalanced levels.

### IMB_03 — Stacked Imbalance (T1)
3+ consecutive imbalanced levels. **Highest-alpha imbalance signal**.
**Expected edge**: HIGH — rare but reliable

### IMB_04 — Stacked Imbalance (T2)
4+ consecutive imbalanced levels.

### IMB_05 — Stacked Imbalance (T3)  
5+ consecutive imbalanced levels. Very rare, very reliable.

### IMB_06 — Reverse Imbalance
Imbalance at opposite end of bar from price close.

### IMB_07 — Inverse Imbalance
Bid imbalance in bullish bar (sellers absorbing) or ask imbalance in bearish bar.
**Expected edge**: HIGH — contrarian setup

### IMB_08 — Oversized Imbalance
Single level where one side > 5x the other AND > 3x bar average.

### IMB_09 — Consecutive Imbalance
Same-direction imbalance on 3+ consecutive bars.

---

## DELTA (weight: 14.3)

### DELT_01 — Delta Rise
Large positive delta surge.

### DELT_02 — Delta Drop  
Large negative delta drop.

### DELT_03 — Delta Tail
Bar closes near low/high with opposing delta (delta didn't follow price).

### DELT_04 — Delta Reversal
Delta changes sign bar over bar significantly.

### DELT_05 — CVD Divergence
**Highest-alpha delta signal.** Price vs CVD divergence over 3-5 bars.
**Expected edge**: HIGH and consistent

### DELT_06 — Delta Flip
CVD changes sign (cumulative delta switches from positive to negative).

### DELT_07 — Delta Trap
Strong delta in one direction, price reverses (trapped aggressive traders).

### DELT_08 — Delta Sweep
Extreme single-bar delta spike (aggressive one-sided activity).

### DELT_09 — Delta Slingshot
Multi-bar trapped-trader reversal pattern (Phase 12 addition).

### DELT_10 — Delta Min/Max
Intrabar delta at session extreme.

### DELT_11 — CVD Velocity
Rate of change of CVD accelerating or decelerating.

---

## VOLUME PROFILE (weight: 20.2)

### VOLP_01 — Volume Sequencing
POC migrates in a consistent direction over multiple bars.

### VOLP_02 — Volume Bubble
Abnormal volume concentration at a price that's away from POC.

### VOLP_03 — Volume Surge
Session volume significantly exceeds average at a specific level.

### VOLP_04 — POC Momentum Wave
POC and price both accelerating in same direction.

### VOLP_05 — Delta Velocity Spike
Rapid acceleration in delta rate of change.

### VOLP_06 — Big Delta Per Level
Single price level with extreme bid-ask imbalance volume.

---

## AUCTION (weight: 12.6)

### AUCT_01 — Unfinished Business
Price tests a level multiple sessions, volume doesn't confirm.

### AUCT_02 — Finished Auction
Price completes auction at extreme, high volume, then reverses.

### AUCT_03 — Poor High/Low
Bar closes within range without testing extreme (momentum failure).

### AUCT_04 — Volume Void
Price range with very low volume (magnet for future price).

### AUCT_05 — Market Sweep
Rapid sweep through multiple price levels.

---

## TRAPPED (weight: 0.0 — currently disabled)

### TRAP_01 — Inverse Imbalance Trap
Stacked imbalance against trend direction.

### TRAP_02 — Delta Trap
Aggressive delta in one direction, price fails to follow.

### TRAP_03 — False Breakout Trap
Break of session high/low, immediate reversal.

### TRAP_04 — High-Volume Rejection Trap
High volume at extreme, price closes at opposite end of bar.

### TRAP_05 — CVD Trap
CVD diverges from price for 5+ bars, extreme reading.

**Note**: TRAP signals are disabled (weight=0) due to insufficient validation.
Re-enable by setting `trapped_weight` in ScoringConfig and running attribution.

---

## DOM ENGINES

### ENG_02 — Trespass (TrespassEngine)
**File**: `deep6v2/signals/engines/trespass.py`
**Logic**: Multi-level weighted DOM queue imbalance + logistic regression output
**Data**: DOM snapshot (requires live DOM — not available in OHLCV backtest)
**Expected edge on MBO**: HIGH

### ENG_03 — CounterSpoof (CounterSpoofDetector)
**File**: `deep6v2/signals/engines/counter_spoof.py`
**Logic**: Wasserstein-1 distance on DOM distributions + cancel rate detection
**Data**: DOM snapshots (before/after comparison)
**Expected edge on MBO**: HIGH — this is one of the most sophisticated signals

### ENG_04 — Iceberg (IcebergDetector)
**File**: `deep6v2/signals/engines/iceberg.py`
**Logic**: Fill volume >> displayed volume at level (ratio > 2x), near absorption zones
**Data**: bar.bid_volumes, bar.ask_volumes, fill tracking
**Expected edge**: HIGH on MBO (true refresh tracking). MEDIUM on OHLCV (estimated).

### ENG_05 — MicroProb (MicroProbDetector)
**File**: `deep6v2/signals/engines/micro_prob.py`
**Logic**: Naive Bayes combining ENG_02 + ENG_04 outputs
**Data**: Outputs from ENG_02 and ENG_04
**Expected edge**: HIGH (ensemble of other engines)

### ENG_06 — VPContext (VPContextDetector)
**File**: `deep6v2/signals/engines/vp_context.py`
**Logic**: Volume profile context — POC proximity, LVN/HVN detection
**Data**: Session volume profile, bar price vs POC
**Expected edge**: MEDIUM (contextual multiplier, not standalone signal)

### ENG_07 — Regime (RegimeDetector)
**Logic**: Detects PIN_REGIME (price pinned near level) and REGIME_CHANGE
**Data**: Multiple bars of price action
**Expected edge**: Context signal, not traded directly
