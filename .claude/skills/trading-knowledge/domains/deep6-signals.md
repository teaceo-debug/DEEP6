# DEEP6 Signal Definitions

Last verified: 2026-05-12

All 44 signal bits + 1 Phase 12 addition (TRAP_SHOT) + 3 meta-flags.
Bit positions are stable per ARCH-05 — do not reorder.

Signal families: ABS (4), EXH (8), IMB (9), DELT (11), AUCT (5), TRAP (5), VOLP (2), TRAP_SHOT (1), META (3)

---

## ABS Family — Absorption (bits 0-3)

Absorption is the highest-alpha reversal signal in DEEP6. It detects passive limit orders absorbing aggressive market orders without price movement — the strongest sign of institutional defense.

---

## ABS-01: Classic Absorption

**Category**: Microstructure
**Tags**: absorption, wick, delta, reversal, institutional
**DEEP6 Signal(s)**: ABS-01 (bit 0, `ABS_CLASSIC`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` (lines 102-133)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\AbsorptionDetectorTests.cs` (parity tests)

### Concept
Classic absorption fires when a bar's wick contains high volume AND balanced delta (both sides active). High wick volume with balanced delta means aggressive orders hit the wick but passive orders absorbed them without moving price. This is the textbook footprint absorption pattern.

### Conditions / Setup
- Wick volume >= 30% of total bar volume (scaled up to 36% if bar range > 1.5x ATR)
- |delta| / wick_volume < 0.12 (balanced — neither side dominated)
- Bar-level delta ratio also < 0.18 (whole bar not strongly directional)
- Upper wick absorption = bearish signal (sellers absorbed buyers)
- Lower wick absorption = bullish signal (buyers absorbed sellers)

### Entry / Exit Rules
Direction: +1 (bullish) for lower wick, -1 (bearish) for upper wick.
Strength: normalized 0-1 from wick percentage and delta balance.
ABS-07 bonus: if price is within 2 ticks of VAH or VAL, strength += 0.15 (capped at 1.0).

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 22-24):
- `absorb_wick_min`: 30.0 (min wick vol % of total)
- `absorb_delta_max`: 0.12 (max |delta|/vol ratio)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 102-133

---

## ABS-02: Passive Absorption

**Category**: Microstructure
**Tags**: absorption, passive, extreme, institutional, volume concentration
**DEEP6 Signal(s)**: ABS-02 (bit 1, `ABS_PASSIVE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` (lines 135-174)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\AbsorptionDetectorTests.cs` (parity tests)

### Concept
Passive absorption fires when volume concentrates heavily at a price extreme while price fails to break through. Unlike classic absorption (which looks at wick delta balance), passive absorption looks at raw volume concentration. Heavy volume at the top of a bar that doesn't close at the top = passive sellers absorbing buyers.

### Conditions / Setup
- Top zone = top 20% of bar range
- Bottom zone = bottom 20% of bar range
- Top zone vol >= 60% of total bar vol AND close < top zone = bearish passive absorption
- Bottom zone vol >= 60% of total bar vol AND close > bottom zone = bullish passive absorption

### Entry / Exit Rules
Direction: -1 (bearish) for top zone concentration, +1 (bullish) for bottom zone.
Strength: zone_vol / total_vol (capped at 1.0).

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 27-29):
- `passive_extreme_pct`: 0.20 (top/bottom fraction of range)
- `passive_vol_pct`: 0.60 (min fraction of total vol in extreme zone)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 135-174

---

## ABS-03: Stopping Volume

**Category**: Microstructure
**Tags**: absorption, stopping volume, POC, wick, high volume
**DEEP6 Signal(s)**: ABS-03 (bit 2, `ABS_STOPPING`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` (lines 176-205)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\AbsorptionDetectorTests.cs` (parity tests)

### Concept
Stopping volume fires when the bar's Point of Control (POC — the price level with the most volume) falls in the wick rather than the body, AND total bar volume exceeds 2x the volume EMA. The POC in the wick means the most-traded price was in the rejected zone — a strong sign that the market tested a level, found heavy two-sided activity there, and reversed.

### Conditions / Setup
- bar.total_vol > vol_ema * 2.0
- POC price > body_top (upper wick) = bearish stopping volume
- POC price < body_bot (lower wick) = bullish stopping volume

### Entry / Exit Rules
Direction: -1 (bearish) for POC in upper wick, +1 (bullish) for POC in lower wick.
Strength: total_vol / (vol_ema * 4.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 31):
- `stop_vol_mult`: 2.0 (volume must exceed this × vol_ema)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 176-205

---

## ABS-04: Effort vs Result

**Category**: Microstructure
**Tags**: absorption, effort, result, narrow range, high volume, Wyckoff
**DEEP6 Signal(s)**: ABS-04 (bit 3, `ABS_EFFORT_VS_R`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` (lines 207-224)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\AbsorptionDetectorTests.cs` (parity tests)

### Concept
Effort vs Result (Wyckoff concept) fires when a bar has high volume but a narrow range. High effort (volume) with no result (range) means the market tried hard to move but couldn't — absorption is occurring throughout the bar body, not just in the wick. This is a subtler but reliable absorption signal.

### Conditions / Setup
- bar.total_vol > vol_ema * 1.5
- bar.bar_range < ATR * 0.30 (range less than 30% of ATR)
- Direction inferred from delta: negative delta + narrow range = bullish (sellers absorbed)

### Entry / Exit Rules
Direction: +1 if bar_delta < 0 (sellers absorbed), -1 if bar_delta > 0 (buyers absorbed).
Strength: total_vol / (vol_ema * 3.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 34-35):
- `evr_vol_mult`: 1.5 (volume must exceed this × vol_ema)
- `evr_range_cap`: 0.30 (max bar range as fraction of ATR)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 207-224

---

## EXH Family — Exhaustion (bits 4-11)

Exhaustion detects when aggressive traders run out of steam. Unlike absorption (passive orders defending), exhaustion means the aggressor simply has no more ammunition. Weaker reversal signal than absorption but fires earlier.

Universal delta trajectory gate (EXH-07) applies to variants EXH-02 through EXH-06. EXH-01 is exempt — it's structural.

---

## EXH-01: Zero Print

**Category**: Microstructure
**Tags**: exhaustion, zero print, gap, structural, price void
**DEEP6 Signal(s)**: EXH-01 (bit 4, `EXH_ZERO_PRINT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 149-166)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
A zero print is a price level within the bar body where both bid and ask volume are exactly zero. This is a structural gap — price passed through this level so fast that no trades occurred. Zero prints are magnets: price will return to fill them. Exempt from the delta gate because they're structural facts, not delta-dependent.

### Conditions / Setup
- Price level within bar body (between open and close)
- ask_vol == 0 AND bid_vol == 0 at that level
- Cooldown: 5 bars between firings of same sub-type

### Entry / Exit Rules
Direction: +1 if bar is bullish (close > open), -1 if bearish.
Strength: fixed at 0.6.
One zero print signal per bar (first found).

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 68):
- `cooldown_bars`: 5

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 149-166

---

## EXH-02: Exhaustion Print

**Category**: Microstructure
**Tags**: exhaustion, single-side volume, extreme, no follow-through
**DEEP6 Signal(s)**: EXH-02 (bit 5, `EXH_EXHAUSTION`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 174-208)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
Exhaustion print fires when a single price level at the bar extreme has high single-side volume with no follow-through. Heavy ask volume at the bar high means buyers pushed hard to that level but couldn't go further — buyer exhaustion. Heavy bid volume at the bar low = seller exhaustion.

### Conditions / Setup
- At bar high: ask_vol at highest tick >= exhaust_wick_min/3 % of total bar vol
- At bar low: bid_vol at lowest tick >= exhaust_wick_min/3 % of total bar vol
- Delta trajectory gate must pass (EXH-07)
- Cooldown: 5 bars

### Entry / Exit Rules
Direction: -1 (bearish) for exhaustion at high, +1 (bullish) for exhaustion at low.
Strength: level_pct / 20.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 62):
- `exhaust_wick_min`: 35.0 (min wick vol % — divided by 3 for single-level check)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 174-208

---

## EXH-03: Thin Print

**Category**: Microstructure
**Tags**: exhaustion, thin print, fast move, low volume levels
**DEEP6 Signal(s)**: EXH-03 (bit 6, `EXH_THIN_PRINT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 210-231)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
Thin print fires when multiple price levels within the bar body have very low volume (< 5% of the bar's max level volume). Thin prints confirm a fast, uncontested move through those levels — the market swept through without meaningful two-sided activity. This is a momentum confirmation signal, not a reversal signal.

### Conditions / Setup
- At least 3 levels within bar body with vol < 5% of max level vol
- Delta trajectory gate must pass (EXH-07)
- Cooldown: 5 bars

### Entry / Exit Rules
Direction: +1 if bar is bullish, -1 if bearish.
Strength: thin_count / 7.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 56):
- `thin_pct`: 0.05 (max volume fraction of bar max for thin print)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 210-231

---

## EXH-04: Fat Print

**Category**: Microstructure
**Tags**: exhaustion, fat print, acceptance, support resistance, high volume level
**DEEP6 Signal(s)**: EXH-04 (bit 7, `EXH_FAT_PRINT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 233-250)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
Fat print fires when a single price level has volume > 2x the bar's average level volume. This marks a strong acceptance level — the market spent significant time and volume at this price. Fat prints become future support/resistance because they represent price levels where both sides agreed to transact heavily.

### Conditions / Setup
- Single level vol > avg_level_vol * 2.0
- Delta trajectory gate must pass (EXH-07)
- Cooldown: 5 bars
- One fat print per bar (the highest-volume level)

### Entry / Exit Rules
Direction: 0 (neutral — acceptance, not directional).
Strength: vol / (avg_level_vol * 4.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 59):
- `fat_mult`: 2.0 (min volume multiple of bar average)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 233-250

---

## EXH-05: Fading Momentum

**Category**: Microstructure
**Tags**: exhaustion, fading momentum, CVD divergence, delta opposition
**DEEP6 Signal(s)**: EXH-05 (bit 8, `EXH_FADING_MOM`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 252-272)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
Fading momentum fires when bar delta strongly opposes bar direction. A bullish bar (close > open) with negative delta means buyers pushed price up but sellers dominated the actual order flow — the move is running on fumes. The universal delta gate already confirms basic divergence; this signal requires a stronger threshold (15% of volume) for pronounced divergence.

### Conditions / Setup
- Bar has directional movement (close != open)
- |bar_delta| > total_vol * 0.15 (pronounced divergence)
- Delta trajectory gate must pass (EXH-07) — which already confirms delta opposes direction
- Cooldown: 5 bars

### Entry / Exit Rules
Direction: -1 if bar is bullish (buyers fading), +1 if bar is bearish (sellers fading).
Strength: |bar_delta| / total_vol, capped at 1.0.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 252-272
Note: Full CVD regression version planned for Phase 3 (E8 CVD engine). Current version uses bar-level delta.

---

## EXH-06: Bid/Ask Fade

**Category**: Microstructure
**Tags**: exhaustion, bid ask fade, prior bar comparison, volume decay
**DEEP6 Signal(s)**: EXH-06 (bit 9, `EXH_BID_ASK_FD`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 274-314)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
Bid/ask fade fires when the ask volume at the current bar's high is less than 60% of the prior bar's ask volume at its high. This detects waning buying pressure across bars — buyers are showing up with less and less conviction at the highs. Same logic applies to bid volume at lows for seller fade.

### Conditions / Setup
- Requires prior_bar
- curr_high_ask < prior_high_ask * 0.60 = bearish fade (buyers weakening)
- curr_low_bid < prior_low_bid * 0.60 = bullish fade (sellers weakening)
- Delta trajectory gate must pass (EXH-07)
- Cooldown: 5 bars

### Entry / Exit Rules
Direction: -1 (bearish) for ask fade at high, +1 (bullish) for bid fade at low.
Strength: 1.0 - (curr / prior), representing the magnitude of the fade.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 65):
- `fade_threshold`: 0.60 (ask/bid fade ratio threshold)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 274-314

---

## EXH-07: Delta Trajectory Gate

**Category**: Microstructure
**Tags**: exhaustion, gate, delta trajectory, filter, universal
**DEEP6 Signal(s)**: EXH-07 (bit 10, `EXH_DELTA_GATE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 70-106)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
EXH-07 is a universal filter gate applied to exhaustion variants 2-6. It only passes when cumulative delta is fading relative to price direction. A bullish bar with negative delta = buyers pushed price up but sellers are winning on delta = buyer exhaustion confirmed. If delta is too small (< 10% of volume), the gate doesn't block because tiny delta is noise.

### Conditions / Setup
- Bullish bar (close > open) + bar_delta < 0 = gate passes
- Bearish bar (close < open) + bar_delta > 0 = gate passes
- Doji (close == open) = gate always passes
- |delta| / total_vol < 0.10 = gate passes (delta too small to be meaningful)

### Entry / Exit Rules
This is a gate, not a standalone signal. It sets the `EXH_DELTA_GATE` bit when active.
Master switch: `delta_gate_enabled` (default True).

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 71-72):
- `delta_gate_min_ratio`: 0.10 (min |delta|/volume for gate to activate)
- `delta_gate_enabled`: True (master switch)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 70-106

---

## EXH-08: Cooldown Suppression

**Category**: Microstructure
**Tags**: exhaustion, cooldown, suppression, spam prevention
**DEEP6 Signal(s)**: EXH-08 (bit 11, `EXH_COOLDOWN`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` (lines 50-67)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\ExhaustionDetectorTests.cs` (parity tests)

### Concept
EXH-08 is a cooldown mechanism that prevents the same exhaustion sub-type from firing repeatedly in consecutive bars. After any exhaustion variant fires, that sub-type is suppressed for 5 bars. This prevents signal spam during trending moves where exhaustion conditions persist.

### Conditions / Setup
- Per-sub-type cooldown tracking via `_cooldown` dict
- Cooldown period: 5 bars (configurable)
- Each sub-type has independent cooldown

### Entry / Exit Rules
This is a suppression mechanism. The `EXH_COOLDOWN` bit is set when cooldown is active.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 68):
- `cooldown_bars`: 5

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 50-67

---

## IMB Family — Imbalance (bits 12-20)

Imbalances detect aggressive buying/selling at specific price levels by comparing ask volume at one level vs bid volume at adjacent levels. The diagonal comparison algorithm: ask[P] vs bid[P-1] for buy imbalance, bid[P] vs ask[P+1] for sell imbalance.

---

## IMB-01: Single Imbalance

**Category**: Order Flow
**Tags**: imbalance, single, diagonal, aggressive, directional
**DEEP6 Signal(s)**: IMB-01 (bit 12, `IMB_SINGLE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 76-127)

### Concept
A single imbalance fires when ask volume at price P is >= 3x the bid volume at price P-1 (buy imbalance), or bid volume at P is >= 3x ask volume at P+1 (sell imbalance). This diagonal comparison is the standard footprint imbalance algorithm. It identifies price levels where one side dominated the other — aggressive buyers or sellers at work.

### Conditions / Setup
- Buy: ask[P] / bid[P-1] >= 3.0 (or bid[P-1] == 0 and ask[P] > 0)
- Sell: bid[P] / ask[P+1] >= 3.0 (or ask[P+1] == 0 and bid[P] > 0)
- Ratio < 10.0 = SINGLE; ratio >= 10.0 = promoted to OVERSIZED (IMB-06)

### Entry / Exit Rules
Direction: +1 for buy imbalance, -1 for sell imbalance.
Strength: ratio / 10.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 83):
- `ratio_threshold`: 3.0 (min ask[P]/bid[P-1] for single imbalance)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 76-127

---

## IMB-02: Multiple Imbalances

**Category**: Order Flow
**Tags**: imbalance, multiple, cluster, accumulation
**DEEP6 Signal(s)**: IMB-02 (bit 13, `IMB_MULTIPLE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 129-168)

### Concept
Multiple imbalances fires when there are 3 or more imbalances in the same direction within a single bar. A cluster of buy imbalances across multiple price levels indicates sustained aggressive buying — not just a single spike but a broad accumulation pattern.

### Conditions / Setup
- >= 3 buy imbalance ticks in bar = bullish MULTIPLE
- >= 3 sell imbalance ticks in bar = bearish MULTIPLE
- One MULTIPLE signal per direction per bar (at median tick of cluster)

### Entry / Exit Rules
Direction: +1 for buy cluster, -1 for sell cluster.
Strength: count / (multiple_min * 2.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 91):
- `multiple_min_count`: 3 (min imbalances at same price tick for MULTIPLE)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 129-168

---

## IMB-03: Stacked Imbalances

**Category**: Order Flow
**Tags**: imbalance, stacked, consecutive levels, T1 T2 T3, conviction
**DEEP6 Signal(s)**: IMB-03 (bit 14, `IMB_STACKED`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 170-209)

### Concept
Stacked imbalances fires when consecutive price levels all show imbalances in the same direction. Three tiers of conviction: T1 (3+ consecutive levels), T2 (5+ levels), T3 (7+ levels). Stacked imbalances represent a wall of aggressive orders — the most powerful imbalance signal. A gap tolerance of 2 ticks allows for minor gaps in the stack.

### Conditions / Setup
- T1: 3+ consecutive imbalance levels (gap tolerance 2 ticks)
- T2: 5+ consecutive imbalance levels
- T3: 7+ consecutive imbalance levels
- Applies to both buy and sell directions

### Entry / Exit Rules
Direction: +1 for stacked buy, -1 for stacked sell.
Strength: run_length / stacked_t3, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 87-89, 97):
- `stacked_t1`: 3, `stacked_t2`: 5, `stacked_t3`: 7
- `stacked_gap_tolerance`: 2 (allow N tick gap in stacked runs)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 170-209

---

## IMB-04: Reverse Imbalance

**Category**: Order Flow
**Tags**: imbalance, reverse, two-sided, contested, indecision
**DEEP6 Signal(s)**: IMB-04 (bit 15, `IMB_REVERSE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 235-245)

### Concept
Reverse imbalance fires when a bar contains both buy imbalances AND sell imbalances. This indicates a contested bar where both sides are aggressively active — neither side has clear control. Often seen at key levels where buyers and sellers are fighting for dominance.

### Conditions / Setup
- buy_imb_ticks is non-empty AND sell_imb_ticks is non-empty

### Entry / Exit Rules
Direction: 0 (neutral — contested).
Strength: fixed at 0.5.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 235-245

---

## IMB-05: Inverse Imbalance (Trapped Traders)

**Category**: Trap
**Tags**: imbalance, inverse, trapped, longs, shorts, 80-85% win rate
**DEEP6 Signal(s)**: IMB-05 (bit 16, `IMB_INVERSE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 211-233)

### Concept
Inverse imbalance is one of the highest win-rate signals in DEEP6 (80-85%). It fires when buy imbalances appear in a red (bearish) bar, or sell imbalances appear in a green (bullish) bar. Buy imbalances in a red bar = buyers tried to push price up but the bar still closed down = those buyers are now trapped longs. The market will likely continue down to stop them out.

### Conditions / Setup
- Red bar (close < open) + >= 3 buy imbalances = trapped longs (bearish signal)
- Green bar (close > open) + >= 3 sell imbalances = trapped shorts (bullish signal)

### Entry / Exit Rules
Direction: -1 (bearish) for trapped longs, +1 (bullish) for trapped shorts.
Strength: count / 7.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 95):
- `inverse_min_imbalances`: 3 (min opposite-dir imbalances to qualify as trap)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 211-233

---

## IMB-06: Oversized Imbalance

**Category**: Order Flow
**Tags**: imbalance, oversized, extreme ratio, 10:1, institutional
**DEEP6 Signal(s)**: IMB-06 (bit 17, `IMB_OVERSIZED`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 111-127)

### Concept
Oversized imbalance is a promotion of IMB-01 (Single) when the ratio reaches 10:1 or higher. A 10:1 ratio means one side had 10x the volume of the other — extreme institutional aggression at a single price level. These levels often become significant support/resistance.

### Conditions / Setup
- Same diagonal scan as IMB-01
- ratio >= 10.0 = promoted from SINGLE to OVERSIZED

### Entry / Exit Rules
Direction: +1 for buy oversized, -1 for sell oversized.
Strength: ratio / 10.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 85):
- `oversized_threshold`: 10.0 (ratio for oversized classification)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 111-127

---

## IMB-07: Consecutive Imbalance

**Category**: Order Flow
**Tags**: imbalance, consecutive, multi-bar, persistent, institutional
**DEEP6 Signal(s)**: IMB-07 (bit 18, `IMB_CONSECUTIVE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 247-297)

### Concept
Consecutive imbalance fires when the same price tick shows an imbalance in both the current bar AND the prior bar. Persistence across bars is a stronger signal than a single-bar imbalance — it suggests institutional orders are working at that level across multiple bars.

### Conditions / Setup
- Requires prior_bar
- Same tick imbalanced in both current and prior bar (same direction)
- Minimum 2 bars (current + prior)

### Entry / Exit Rules
Direction: +1 for consecutive buy, -1 for consecutive sell.
Strength: fixed at 0.75.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 93):
- `consecutive_min_bars`: 2 (min bars for consecutive detection)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 247-297

---

## IMB-08: Diagonal Imbalance

**Category**: Order Flow
**Tags**: imbalance, diagonal, ask bid, cross-tick, algorithm
**DEEP6 Signal(s)**: IMB-08 (bit 19, `IMB_DIAGONAL`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 76-110)

### Concept
Diagonal imbalance is the core algorithm underlying all imbalance detection. It compares ask volume at price P against bid volume at price P-1 (one tick lower) for buy imbalances, and bid at P against ask at P+1 for sell imbalances. This diagonal comparison is the standard footprint chart imbalance methodology — it captures the asymmetry between aggressive buyers lifting offers vs passive sellers.

### Conditions / Setup
- Buy: ask[P] vs bid[P-1] (ask at current level vs bid at level below)
- Sell: bid[P] vs ask[P+1] (bid at current level vs ask at level above)
- This is the scan that produces buy_imb_ticks and sell_imb_ticks used by all other IMB signals

### Entry / Exit Rules
This is the foundational scan. The `IMB_DIAGONAL` bit is set when the diagonal scan produces any imbalances.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 76-110

---

## IMB-09: Imbalance Reversal Point

**Category**: Order Flow
**Tags**: imbalance, reversal, direction change, bar sequence
**DEEP6 Signal(s)**: IMB-09 (bit 20, `IMB_REVERSAL_PT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 299-359)

### Concept
Imbalance reversal point fires when the dominant imbalance direction flips between the prior bar and the current bar. Prior bar dominated by buy imbalances (2x more buys than sells) + current bar dominated by sell imbalances = bearish reversal point. This captures the moment when aggressive order flow switches sides.

### Conditions / Setup
- Requires prior_bar
- Prior dominant buy: p_buy_count >= 2 AND p_buy_count > p_sell_count * 2
- Current dominant sell: curr_sell_count >= 2 AND curr_sell_count > curr_buy_count * 2
- Reversal fires when dominant direction flips

### Entry / Exit Rules
Direction: -1 (bearish) for buy-to-sell flip, +1 (bullish) for sell-to-buy flip.
Strength: (prior_count + current_count) / 10.0, capped at 1.0.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 299-359

---

## DELT Family — Delta (bits 21-31)

Delta measures the difference between buying and selling pressure (ask_vol - bid_vol). These signals detect when delta behavior diverges from price action or reaches extremes that predict reversals.

---

## DELT-01: Delta Rise/Drop

**Category**: Delta
**Tags**: delta, rise, drop, directional, bar classification
**DEEP6 Signal(s)**: DELT-01 (bit 21, `DELT_RISE_DROP`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 128-138)

### Concept
Delta Rise/Drop is the simplest delta signal — it fires on every bar with non-zero delta. RISE fires when bar_delta > 0 (net buying), DROP fires when bar_delta < 0 (net selling). This is a bar classification signal used as a baseline for other delta signals and for the scorer's category counting.

### Conditions / Setup
- delta > 0 = RISE (+1 direction)
- delta < 0 = DROP (-1 direction)

### Entry / Exit Rules
Strength: |delta| / total_vol, capped at 1.0.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 128-138

---

## DELT-02: Delta Tail

**Category**: Delta
**Tags**: delta, tail, conviction, intrabar extreme, closing strength
**DEEP6 Signal(s)**: DELT-02 (bit 22, `DELT_TAIL`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 140-165)

### Concept
Delta tail fires when the bar closes at 95%+ of its intrabar delta extreme. If bar_delta is positive and the bar closes at 95%+ of the intrabar max_delta, buyers maintained conviction throughout the bar — no fading. This is a strong conviction signal. Uses true intrabar max/min delta (tracked live by add_trade() per Plan 12-02), not a bar-geometry proxy.

### Conditions / Setup
- Positive delta: tail_ratio = bar_delta / max_delta >= 0.95
- Negative delta: tail_ratio = bar_delta / min_delta >= 0.95
- Guard: if matching extreme is 0 (uninstrumented bar), treat as ratio 1.0

### Entry / Exit Rules
Direction: +1 for bullish tail, -1 for bearish tail.
Strength: tail_ratio (0.95-1.0 range).

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 109):
- `tail_threshold`: 0.95 (delta ratio for tail signal)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 140-165

---

## DELT-03: Delta Reversal

**Category**: Delta
**Tags**: delta, reversal, hidden, bar direction mismatch
**DEEP6 Signal(s)**: DELT-03 (bit 23, `DELT_REVERSAL`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 167-187)

### Concept
Delta reversal fires when bar delta contradicts bar direction. A bullish bar (close > open) with negative delta = bar closed up but sellers dominated the order flow = hidden bearish reversal. The market moved up on price but the actual aggression was selling. Requires minimum delta ratio to avoid noise on flat bars.

### Conditions / Setup
- |delta| / total_vol >= 0.15 (min delta ratio to avoid noise)
- Bullish bar + delta < 0 = bearish hidden reversal
- Bearish bar + delta > 0 = bullish hidden reversal

### Entry / Exit Rules
Direction: -1 for bearish hidden reversal, +1 for bullish hidden reversal.
Strength: delta_ratio_abs, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 127):
- `reversal_min_delta_ratio`: 0.15 (min |delta|/vol for reversal signal to fire)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 167-187

---

## DELT-04: Delta Divergence

**Category**: Delta
**Tags**: delta, divergence, CVD, price, highest alpha
**DEEP6 Signal(s)**: DELT-04 (bit 24, `DELT_DIVERGENCE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 189-207)

### Concept
Delta divergence is labeled "highest alpha" in the codebase. It fires when price makes a new N-bar high but CVD (cumulative volume delta) fails to confirm, or price makes a new N-bar low but CVD holds. Classic bearish divergence: price at 5-bar high but CVD below its 5-bar high = buyers are losing steam even as price pushes up.

### Conditions / Setup
- Lookback: 5 bars (configurable)
- Bearish: price[-1] == max(prices[-5:]) AND cvd[-1] < max(cvds[-5:])
- Bullish: price[-1] == min(prices[-5:]) AND cvd[-1] > min(cvds[-5:])
- Requires >= 5 bars of history

### Entry / Exit Rules
Direction: -1 for bearish divergence, +1 for bullish divergence.
Strength: fixed at 0.8.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 111):
- `divergence_lookback`: 5 (bars for divergence check)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 189-207

---

## DELT-05: CVD Flip

**Category**: Delta
**Tags**: delta, CVD, flip, zero cross, trend change
**DEEP6 Signal(s)**: DELT-05 (bit 25, `DELT_FLIP`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 209-221)

### Concept
CVD flip fires when cumulative volume delta crosses zero — from positive to negative (bearish flip) or negative to positive (bullish flip). A zero cross in CVD means the session's net order flow has switched sides. This is a trend change signal at the CVD level.

### Conditions / Setup
- Requires >= 2 bars of CVD history
- prev_cvd >= 0 AND cvd < 0 = bearish flip
- prev_cvd <= 0 AND cvd > 0 = bullish flip

### Entry / Exit Rules
Direction: -1 for bearish flip, +1 for bullish flip.
Strength: fixed at 0.6.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 209-221

---

## DELT-06: Delta Trap

**Category**: Trap
**Tags**: delta, trap, reversal, prior bar, aggressive failure
**DEEP6 Signal(s)**: DELT-06 (bit 26, `DELT_TRAP`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 223-237)

### Concept
Delta trap fires when the prior bar had strong directional delta but the current bar reverses price. Strong buying delta in the prior bar (>= 30% of volume) followed by a bearish current bar = those buyers are now trapped. The market absorbed their aggression and reversed against them.

### Conditions / Setup
- Prior bar |delta| / total_vol >= 0.30
- Prior bullish delta + current bar closes down = bearish trap
- Prior bearish delta + current bar closes up = bullish trap

### Entry / Exit Rules
Direction: -1 for bearish trap (longs trapped), +1 for bullish trap (shorts trapped).
Strength: fixed at 0.7.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 113):
- `trap_delta_ratio`: 0.3 (min |delta|/vol for trap qualification)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 223-237

---

## DELT-07: Delta Sweep

**Category**: Delta
**Tags**: delta, sweep, acceleration, multi-level, momentum
**DEEP6 Signal(s)**: DELT-07 (bit 27, `DELT_SWEEP`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 239-261)

### Concept
Delta sweep fires when a bar spans >= 5 price levels AND volume accelerates in the second half of the bar (second-half vol >= 1.5x first-half vol). This detects a sweeping move where momentum builds as price moves through levels — the market is not just moving, it's accelerating.

### Conditions / Setup
- Bar spans >= 5 price levels
- second_half_vol >= first_half_vol * 1.5
- Levels split by position (lower half vs upper half of sorted ticks)

### Entry / Exit Rules
Direction: +1 if delta >= 0, -1 if delta < 0.
Strength: fixed at 0.8.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 124-125):
- `sweep_min_levels`: 5 (min price levels in bar for sweep detection)
- `sweep_vol_increase_ratio`: 1.5 (vol increase ratio second half / first half)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 239-261

---

## DELT-08: Delta Slingshot

**Category**: Delta
**Tags**: delta, slingshot, compression, explosion, 72-78% win rate
**DEEP6 Signal(s)**: DELT-08 (bit 28, `DELT_SLINGSHOT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 263-279)

### Concept
Delta slingshot has a documented 72-78% win rate. It fires when 2+ of the prior 3 bars had compressed delta (< 10% of volume) followed by the current bar with explosive delta (>= 40% of volume). The compression-then-explosion pattern indicates coiling energy releasing — institutional accumulation followed by a directional move.

### Conditions / Setup
- Prior 3 bars: >= 2 bars with |delta| < total_vol * 0.10 (quiet)
- Current bar: |delta| > total_vol * 0.40 (explosive)
- Requires >= 4 bars of delta history

### Entry / Exit Rules
Direction: +1 if delta > 0, -1 if delta < 0.
Strength: fixed at 0.85.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 115-117):
- `slingshot_quiet_ratio`: 0.1 (max |delta|/vol for compressed bar)
- `slingshot_explosive_ratio`: 0.4 (min |delta|/vol for explosive bar)
- `slingshot_quiet_bars`: 2 (min quiet bars out of 3 before explosion)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 263-279

---

## DELT-09: Delta at Session Min/Max

**Category**: Delta
**Tags**: delta, session extreme, CVD min max, exhaustion
**DEEP6 Signal(s)**: DELT-09 (bit 29, `DELT_MIN_MAX`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 281-293)

### Concept
Delta at session min/max fires when CVD reaches its session extreme. CVD at session maximum = buyers have been the most aggressive they've been all session — potential exhaustion of buying. CVD at session minimum = sellers at their most aggressive — potential exhaustion of selling. Useful for identifying session turning points.

### Conditions / Setup
- cvd >= session_cvd_max = AT_MAX signal (+1 direction)
- cvd <= session_cvd_min = AT_MIN signal (-1 direction)
- Requires session_cvd_range > 0

### Entry / Exit Rules
Direction: +1 for AT_MAX (buyers at extreme), -1 for AT_MIN (sellers at extreme).
Strength: fixed at 0.5.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 281-293

---

## DELT-10: CVD Multi-Bar Divergence

**Category**: Delta
**Tags**: delta, CVD, multi-bar, regression, divergence, polyfit
**DEEP6 Signal(s)**: DELT-10 (bit 30, `DELT_CVD_DIVG`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 295-316)

### Concept
CVD multi-bar divergence uses linear regression (numpy polyfit) over a rolling window to detect when price slope and CVD slope are moving in opposite directions. Unlike DELT-04 (which looks at N-bar highs/lows), this uses regression slopes for a smoother, less noisy divergence signal. Requires a minimum window of 10 bars.

### Conditions / Setup
- Requires >= 10 bars of history (configurable)
- price_slope > 0 AND cvd_slope < -|price_slope| * 0.3 = bearish divergence
- price_slope < 0 AND cvd_slope > |price_slope| * 0.3 = bullish divergence

### Entry / Exit Rules
Direction: -1 for bearish divergence, +1 for bullish divergence.
Strength: fixed at 0.75.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 119-120):
- `cvd_divergence_min_bars`: 10 (min bars for CVD regression)
- `cvd_slope_divergence_factor`: 0.3 (slope divergence threshold multiplier)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 295-316

---

## DELT-11: Delta Velocity

**Category**: Delta
**Tags**: delta, velocity, acceleration, CVD rate of change
**DEEP6 Signal(s)**: DELT-11 (bit 31, `DELT_VELOCITY`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 318-328)

### Concept
Delta velocity fires when the acceleration of CVD (second derivative) exceeds a threshold. Velocity = CVD[-1] - CVD[-2]. Acceleration = velocity - prior_velocity. High acceleration means CVD is changing direction rapidly — a sudden shift in order flow momentum. Requires >= 3 bars of CVD history.

### Conditions / Setup
- Requires >= 3 bars of CVD history
- accel = (cvd[-1] - cvd[-2]) - (cvd[-2] - cvd[-3])
- |accel| > total_vol * 0.30

### Entry / Exit Rules
Direction: +1 if accel > 0 (accelerating bullish), -1 if accel < 0 (decelerating/reversing).
Strength: |accel| / total_vol, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 122):
- `velocity_accel_ratio`: 0.3 (min |accel|/vol for velocity signal)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\delta.py` lines 318-328

---

## AUCT Family — Auction Theory (bits 32-36)

Auction theory views the market as a continuous two-sided auction. Price explores until it finds acceptance (volume) or rejection (no volume). These signals detect when auctions are complete, incomplete, or in transition.

---

## AUCT-01: Unfinished Business

**Category**: Auction Theory
**Tags**: auction, unfinished, magnet, price return, bid at high
**DEEP6 Signal(s)**: AUCT-01 (bit 32, `AUCT_UNFINISHED`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py` (lines 101-135)

### Concept
Unfinished business fires when there is non-zero bid volume at the bar high, or non-zero ask volume at the bar low. A bid at the bar high means buyers were still present when price reached its extreme — the auction wasn't finished. Price will return to complete the auction. These levels are tracked in `unfinished_levels` for cross-bar reference.

### Conditions / Setup
- high_level.bid_vol > 0 = unfinished business upward (+1)
- low_level.ask_vol > 0 = unfinished business downward (-1)

### Entry / Exit Rules
Direction: +1 for unfinished at high (price will return up), -1 for unfinished at low.
Strength: fixed at 0.6.
Levels tracked in AuctionEngine.unfinished_levels dict for future reference.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 101-135

---

## AUCT-02: Finished Auction

**Category**: Auction Theory
**Tags**: auction, finished, exhaustion, zero bid, zero ask
**DEEP6 Signal(s)**: AUCT-02 (bit 33, `AUCT_FINISHED`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py` (lines 137-152)

### Concept
Finished auction fires when the bar extreme has zero bid volume at the high (buyers exhausted) or zero ask volume at the low (sellers exhausted). This is the auction theory equivalent of exhaustion — the market tested a level, found no more participants willing to transact, and the auction is complete. Stronger reversal signal than unfinished business.

### Conditions / Setup
- high_level.bid_vol == 0 AND high_level.ask_vol > 0 = finished at high (bearish)
- low_level.ask_vol == 0 AND low_level.bid_vol > 0 = finished at low (bullish)

### Entry / Exit Rules
Direction: -1 for finished at high (buyers exhausted), +1 for finished at low (sellers exhausted).
Strength: fixed at 0.7.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 137-152

---

## AUCT-03: Poor High / Poor Low

**Category**: Auction Theory
**Tags**: auction, poor high, poor low, single print, incomplete, revisit
**DEEP6 Signal(s)**: AUCT-03 (bit 34, `AUCT_POOR_HILOW`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py` (lines 154-173)

### Concept
Poor high/low fires when the bar extreme has very low volume (< 30% of average level volume). A poor high means price reached that level but barely traded there — the auction was incomplete. Poor highs and lows are magnets for future price action because the market needs to return and properly auction those levels.

### Conditions / Setup
- high_vol < avg_vol * 0.30 = poor high (bearish — price will return to test)
- low_vol < avg_vol * 0.30 = poor low (bullish — price will return to test)

### Entry / Exit Rules
Direction: -1 for poor high, +1 for poor low.
Strength: fixed at 0.5.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 138):
- `poor_extreme_vol_ratio`: 0.3 (max vol/avg_vol for poor high/low)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 154-173

---

## AUCT-04: Volume Void

**Category**: Auction Theory
**Tags**: auction, volume void, LVN, fast move zone, gap
**DEEP6 Signal(s)**: AUCT-04 (bit 35, `AUCT_VOL_VOID`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py` (lines 175-190)

### Concept
Volume void fires when there are >= 3 price levels within the bar with very low volume (< 5% of bar's max level volume). This identifies a Low Volume Node (LVN) gap within the bar — a zone where price moved through quickly with minimal acceptance. LVN zones are fast-move areas: when price re-enters them, it tends to move quickly to the next HVN.

### Conditions / Setup
- >= 3 levels with vol < max_vol * 0.05 (but vol > 0, not zero prints)
- Levels can be anywhere in the bar

### Entry / Exit Rules
Direction: +1 if bar is bullish, -1 if bearish.
Strength: void_count / 7.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 140-141):
- `void_vol_ratio`: 0.05 (max vol/max_vol for volume void level)
- `void_min_levels`: 3 (min thin levels for void signal)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 175-190

---

## AUCT-05: Market Sweep

**Category**: Auction Theory
**Tags**: auction, sweep, rapid traversal, volume acceleration, momentum
**DEEP6 Signal(s)**: AUCT-05 (bit 36, `AUCT_MKT_SWEEP`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\auction.py` (lines 192-225)

### Concept
Market sweep fires when price rapidly traverses >= 10 price levels with increasing volume in the direction of movement. For an up sweep, the upper half of levels has >= 1.5x the volume of the lower half. This indicates a sweeping institutional order that accelerates as it moves — a high-conviction directional move.

### Conditions / Setup
- Bar spans >= 10 price levels
- Up sweep: upper half vol >= lower half vol * 1.5
- Down sweep: lower half vol >= upper half vol * 1.5

### Entry / Exit Rules
Direction: +1 for up sweep, -1 for down sweep.
Strength: second_half_vol / first_half_vol / 3, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 143-144):
- `sweep_vol_increase`: 1.5 (min second-half/first-half vol ratio for sweep)
- `sweep_min_levels`: 10 (min price levels for sweep detection)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\auction.py` lines 192-225

---

## TRAP Family — Trapped Traders (bits 37-41)

Trapped trader signals identify participants caught on the wrong side of the market after committing capital. When trapped traders are forced to exit, they create predictable directional pressure.

Note: TRAP-01 (inverse imbalance) is implemented in imbalance.py as IMB-05 (INVERSE_TRAP). TRAP-02 through TRAP-05 are in trap.py.

---

## TRAP-01: Inverse Imbalance Trap

**Category**: Trap
**Tags**: trap, inverse imbalance, trapped longs, trapped shorts
**DEEP6 Signal(s)**: TRAP-01 (bit 37, `TRAP_INVERSE_I`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` (lines 211-233)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\TrapDetectorTests.cs` (parity tests)

### Concept
See IMB-05 (Inverse Imbalance). TRAP-01 and IMB-05 are the same signal — buy imbalances in a red bar (trapped longs) or sell imbalances in a green bar (trapped shorts). The bit 37 (`TRAP_INVERSE_I`) is set by the imbalance engine when `ImbalanceType.INVERSE_TRAP` fires.

### DEEP6 Implementation
Detection: See `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` lines 211-233
Note: Implemented in imbalance.py, not trap.py. The TRAP_INVERSE_I bit is set by the signal mapper when INVERSE_TRAP fires.

---

## TRAP-02: Delta Trap

**Category**: Trap
**Tags**: trap, delta, prior bar, reversal, aggressive failure
**DEEP6 Signal(s)**: TRAP-02 (bit 38, `TRAP_DELTA`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\trap.py` (lines 117-163)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\TrapDetectorTests.cs` (parity tests)

### Concept
Delta trap fires when the prior bar had strong directional delta (>= 25% of volume) AND the current bar reverses both price direction AND delta direction. This is a two-bar pattern: aggressive buying followed by a bearish reversal bar with selling delta = those buyers are trapped. Requires both price reversal AND delta reversal for confirmation.

### Conditions / Setup
- prior_bar |delta| / total_vol >= 0.25
- Prior bullish delta + current bar closes down + current delta < 0 = bearish trap
- Prior bearish delta + current bar closes up + current delta > 0 = bullish trap

### Entry / Exit Rules
Direction: +1 if current delta > 0 (shorts trapped), -1 if current delta < 0 (longs trapped).
Strength: prior_ratio / (trap_delta_ratio * 2.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 230):
- `trap_delta_ratio`: 0.25 (min |delta|/vol for prior bar to qualify)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\trap.py` lines 117-163

---

## TRAP-03: False Breakout Trap

**Category**: Trap
**Tags**: trap, false breakout, stop hunt, reversal, high volume
**DEEP6 Signal(s)**: TRAP-03 (bit 39, `TRAP_FALSE_BRK`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\trap.py` (lines 169-222)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\TrapDetectorTests.cs` (parity tests)

### Concept
False breakout trap fires when a bar breaks above the prior bar's high (or below the prior low) but closes back inside. This is the classic stop hunt pattern: price breaks out to trigger stops, then reverses. Requires above-average volume (1.8x vol_ema) to confirm institutional participation in the trap.

### Conditions / Setup
- bar.total_vol > vol_ema * 1.8
- Bear false breakout: bar.high > prior.high AND bar.close < prior.high
- Bull false breakout: bar.low < prior.low AND bar.close > prior.low

### Entry / Exit Rules
Direction: -1 for bear false breakout (longs trapped), +1 for bull false breakout (shorts trapped).
Strength: (total_vol / vol_threshold - 1.0) / 2.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 233):
- `false_breakout_vol_mult`: 1.8 (volume multiple above vol_ema)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\trap.py` lines 169-222

---

## TRAP-04: High Volume Rejection Trap

**Category**: Trap
**Tags**: trap, high volume, rejection, wick, record volume
**DEEP6 Signal(s)**: TRAP-04 (bit 40, `TRAP_HIVOL_REJ`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\trap.py` (lines 228-292)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\TrapDetectorTests.cs` (parity tests)

### Concept
High volume rejection trap fires when a bar has record volume (>= 2.5x vol_ema) AND a dominant wick (>= 35% of total volume in the wick zone). Record volume with immediate rejection means the market tried hard to move in one direction but was rejected — the high volume attracted participants who are now trapped.

### Conditions / Setup
- bar.total_vol > vol_ema * 2.5
- bar.bar_range > 0
- Upper wick zone (top 25% of range) vol >= 35% of total = upper wick dominant
- Lower wick zone (bottom 25% of range) vol >= 35% of total = lower wick dominant

### Entry / Exit Rules
Direction: -1 if upper wick dominant (price rejected from highs), +1 if lower wick dominant.
Strength: wick_frac / (hvr_wick_min * 2.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 236-237):
- `hvr_vol_mult`: 2.5 (volume multiple above vol_ema)
- `hvr_wick_min`: 0.35 (min wick volume fraction)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\trap.py` lines 228-292

---

## TRAP-05: CVD Trap

**Category**: Trap
**Tags**: trap, CVD, trend reversal, slope, linear regression
**DEEP6 Signal(s)**: TRAP-05 (bit 41, `TRAP_CVD`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\trap.py` (lines 298-349)
**NinjaTrader File**: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\TrapDetectorTests.cs` (parity tests)

### Concept
CVD trap fires when the prior CVD trend (measured by linear regression slope over 8 bars) reverses direction on the current bar. A rising CVD slope (buyers trending) followed by a bar with negative delta = the CVD trend is reversing = participants who positioned with the prior trend are now trapped. Uses numpy polyfit for slope calculation.

### Conditions / Setup
- Requires >= 8 bars of CVD history
- |slope| > 0.05 (CVD must be meaningfully trending, not flat)
- Prior slope > 0 + current delta < 0 = bearish CVD trap
- Prior slope < 0 + current delta > 0 = bullish CVD trap

### Entry / Exit Rules
Direction: +1 if current delta > 0 (shorts trapped), -1 if current delta < 0 (longs trapped).
Strength: |slope| / (cvd_trap_min_slope * 10.0), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 240-241):
- `cvd_trap_lookback`: 8 (bars for CVD slope calculation)
- `cvd_trap_min_slope`: 0.05 (min |slope| to qualify as trending CVD)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\trap.py` lines 298-349

---

## VOLP Family — Volume Patterns (bits 42-43)

Volume pattern signals detect institutional activity, accumulation/distribution, or impending directional moves through volume structure anomalies. VOLP-03 through VOLP-06 are implemented in vol_patterns.py but their bits (44-47) are reserved for Phase 5+.

---

## VOLP-01: Volume Sequencing

**Category**: Volume Profile
**Tags**: volume, sequencing, escalating, institutional, accumulation
**DEEP6 Signal(s)**: VOLP-01 (bit 42, `VOLP_SEQUENCING`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 125-173)

### Concept
Volume sequencing fires when 3 or more consecutive bars each have volume >= 115% of the prior bar's volume. Escalating volume across bars is a classic institutional accumulation/distribution pattern — each bar requires more volume than the last, indicating growing participation and conviction in the move.

### Conditions / Setup
- >= 3 consecutive bars where each vol >= prior * 1.15
- Walks backwards from current bar to find the longest qualifying run
- Direction = sign of sum of bar_delta across the qualifying sequence

### Entry / Exit Rules
Direction: +1 if net delta positive, -1 if negative, 0 if neutral.
Strength: (run_length - min_bars + 1) / (min_bars + 1), capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 252-253):
- `vol_seq_step_ratio`: 1.15 (each bar >= prior * this ratio)
- `vol_seq_min_bars`: 3 (min bars in sequence)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 125-173

---

## VOLP-02: Volume Bubble

**Category**: Volume Profile
**Tags**: volume, bubble, single level, concentration, institutional
**DEEP6 Signal(s)**: VOLP-02 (bit 43, `VOLP_BUBBLE`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 179-222)

### Concept
Volume bubble fires when a single price level has volume > 4x the bar's average level volume. This isolated high-volume level represents a price where the market spent disproportionate time — a future magnet for price. The direction is determined by whether ask or bid volume dominated at that level.

### Conditions / Setup
- avg_level_vol = total_vol / n_levels
- Single level vol > avg_level_vol * 4.0
- One signal per bar at the highest-volume bubble level

### Entry / Exit Rules
Direction: +1 if ask_vol > bid_vol at bubble level, -1 if bid_vol > ask_vol, 0 if equal.
Strength: (best_vol / threshold - 1.0) / 3.0, capped at 1.0.

### DEEP6 Implementation
Thresholds (from `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 256):
- `bubble_mult`: 4.0 (level vol > avg_level_vol * this)

Detection: See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 179-222

---

## Phase 12 Additions

---

## TRAP_SHOT: Multi-Bar Trapped Trader Reversal

**Category**: Trap
**Tags**: trap, multi-bar, z-score, GEX wall, state bypass, phase 12
**DEEP6 Signal(s)**: TRAP_SHOT (bit 44, `TRAP_SHOT`)
**Python File**: `C:\Users\Tea\DEEP6\deep6\signals\flags.py` (lines 119-126)

### Concept
TRAP_SHOT is a multi-bar trapped-trader reversal pattern added in Phase 12. It detects 2/3/4-bar variants using a z-score > 2.0 over a session-bounded delta history window. Distinct from DELT_SLINGSHOT (bit 28, intra-bar compressed-to-explosive) — TRAP_SHOT operates across multiple bars. When firing within GEX wall proximity, it emits `triggers_state_bypass=True`, allowing the setup state machine to jump directly from SCANNING to TRIGGERED.

### Conditions / Setup
- 2/3/4-bar pattern variants
- z-score > 2.0 over session-bounded delta history window
- GEX wall proximity check for state bypass

### Entry / Exit Rules
When `triggers_state_bypass=True`: setup state machine jumps SCANNING -> TRIGGERED directly.

### DEEP6 Implementation
Bit definition: See `C:\Users\Tea\DEEP6\deep6\signals\flags.py` lines 119-126
Architecture decisions: See `.planning/phases/12-*/12-CONTEXT.md`

---

## META Flags (bits 45-47)

Meta-flags are NOT signal bits. They describe regime/veto state and are emitted by `ConfluenceRules.evaluate()`. Popcount-based signal counting MUST mask these off via `SIGNAL_BITS_MASK = (1 << 45) - 1`.

---

## META: PIN_REGIME_ACTIVE

**Category**: Microstructure
**Tags**: meta, GEX, VPOC, pin, regime, gamma
**DEEP6 Signal(s)**: PIN_REGIME_ACTIVE (bit 45)
**Python File**: `C:\Users\Tea\DEEP6\deep6\signals\flags.py` (line 134)

### Concept
Set when VPOC is pinned near the largest-gamma strike (D-33). Indicates a gamma pinning regime where price is being held near a major options strike by dealer hedging flows. Not a trade signal — a regime descriptor used by the scorer for context.

### DEEP6 Implementation
Emitted by: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (ConfluenceRules.evaluate())
Config: `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 417-418 (pin_regime_min_strikes, proximity_tight_ticks)

---

## META: REGIME_CHANGE

**Category**: Microstructure
**Tags**: meta, GEX, regime, transition, gamma flip
**DEEP6 Signal(s)**: REGIME_CHANGE (bit 46)
**Python File**: `C:\Users\Tea\DEEP6\deep6\signals\flags.py` (line 135)

### Concept
Set when GEX regime transitioned this bar (D-33). A regime change means the gamma exposure profile shifted — dealers switched from net-long to net-short gamma or vice versa. This changes the expected price behavior (gamma-long = mean-reverting, gamma-short = trending).

### DEEP6 Implementation
Emitted by: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (ConfluenceRules.evaluate())
Config: `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 424 (regime_change_min_score_delta)

---

## META: SPOOF_VETO

**Category**: Microstructure
**Tags**: meta, spoof, veto, DOM manipulation, disqualified
**DEEP6 Signal(s)**: SPOOF_VETO (bit 47)
**Python File**: `C:\Users\Tea\DEEP6\deep6\signals\flags.py` (line 136)

### Concept
Set when spoofing is detected — the scorer forces DISQUALIFIED status (D-33). Spoofing detection monitors for large DOM orders that cancel quickly without trading (CounterSpoofEngine, E3). When active, no trade setup can be promoted regardless of signal score.

### DEEP6 Implementation
Emitted by: `C:\Users\Tea\DEEP6\deep6\engines\confluence_rules.py` (ConfluenceRules.evaluate())
Config: `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` line 425 (spoof_detection_min_cancel_ratio: 0.85)
CounterSpoofEngine: `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` lines 285-301

---

## Reserved VOLP Signals (Phase 5+)

The following signals are implemented in `vol_patterns.py` but their bit positions are reserved for Phase 5+. They are NOT currently mapped to SignalFlags bits.

### VOLP-03: Volume Surge
Bar volume > vol_ema * 3.0. Direction from delta if |delta/vol| > 0.15.
See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 228-261
Config: `surge_mult`: 3.0, `surge_delta_min_ratio`: 0.15

### VOLP-04: POC Momentum Wave
POC has migrated directionally for 3+ consecutive bars (monotonic).
See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 267-308
Config: `poc_wave_bars`: 3

### VOLP-05: Delta Velocity Spike
|velocity| = |bar_delta - prior_bar_delta| > vol_ema * 0.6.
See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 314-350
Config: `delta_velocity_mult`: 0.6

### VOLP-06: Big Delta Per Level
Single price level with |net_delta| > 80 contracts.
See `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` lines 356-397
Config: `big_delta_level_threshold`: 80

---

## Signal Count Summary

| Family | Bits | Count | Phase |
|--------|------|-------|-------|
| ABS | 0-3 | 4 | 2 |
| EXH | 4-11 | 8 | 2 |
| IMB | 12-20 | 9 | 3 |
| DELT | 21-31 | 11 | 3 |
| AUCT | 32-36 | 5 | 3 |
| TRAP | 37-41 | 5 | 4 |
| VOLP | 42-43 | 2 | 4 |
| TRAP_SHOT | 44 | 1 | 12 |
| META | 45-47 | 3 | 15 |
| **Total signal bits** | **0-44** | **45** | |

Signal mask: `SIGNAL_BITS_MASK = (1 << 45) - 1`
Use `flags & SIGNAL_BITS_MASK` for popcount to exclude meta-flags.

---

## NinjaTrader Parity

No dedicated Detector .cs files exist. NT8 signal detection is implemented across:
- `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6Atlas.cs` (main indicator)
- `C:\Users\Tea\DEEP6\ninjatrader\Custom\AddOns\DEEP6\Scoring\` (scoring layer)
- `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\` (parity test suite)

Parity test files per family:
- Absorption: `AbsorptionDetectorTests.cs`, `AbsorptionParityTests.cs`
- Exhaustion: `ExhaustionDetectorTests.cs`, `ExhaustionParityTests.cs`
- Imbalance: `ImbalanceDetectorTests.cs`
- Delta: `DeltaDetectorTests.cs`, `DeltaHardTests.cs`
- Auction: `AuctionDetectorTests.cs`
- Trap: `TrapDetectorTests.cs`, `TrapHardTests.cs`
- Volume Patterns: `VolPatternDetectorTests.cs`
