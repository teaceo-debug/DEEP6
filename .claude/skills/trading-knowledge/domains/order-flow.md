# Order Flow Knowledge Domain

Last verified: 2026-05-12

---

## OF-01: Delta — Bid vs Ask Volume Per Bar

**Category**: Order Flow
**Tags**: delta, bid_vol, ask_vol, bar_delta, buying_pressure, selling_pressure
**DEEP6 Signal(s)**: DELT-01 (RISE/DROP)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 128–138)

### Concept

Delta is the net difference between aggressive buying and aggressive selling within a single bar:

```
bar_delta = ask_volume - bid_volume
```

- Positive delta: more contracts traded at the ask (buyers were aggressive)
- Negative delta: more contracts traded at the bid (sellers were aggressive)
- Delta does NOT measure passive orders — only the aggressor side

Delta is the most fundamental order flow metric. It answers: "Who was more aggressive this bar?"

### Conditions / Setup

Delta is computed per bar from tick-level data. Each trade is classified as:
- Ask-side (aggressor is buyer): adds to ask_vol
- Bid-side (aggressor is seller): adds to bid_vol

For NQ futures, a single tick = $5. A delta of +500 means 500 more contracts traded at the ask than the bid.

### Entry / Exit Rules

DELT-01 (RISE/DROP) fires on every bar with non-zero delta:
- `delta > 0` → RISE signal, direction +1, strength = delta/total_vol
- `delta < 0` → DROP signal, direction -1, strength = |delta|/total_vol

These are informational signals — they contribute to the delta category vote in the scorer but don't trigger trades alone.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 128–138: DELT-01 RISE/DROP detection
  Lines 48–54:   DeltaSignal dataclass (delta_type, direction, strength, value, detail)
  Lines 76–86:   DeltaEngine.__init__ — CVD history, price history, session extremes
  Lines 113–116: bar_delta and cvd read from FootprintBar
```

```
C:\Users\Tea\DEEP6\deep6\state\footprint.py
  FootprintBar.bar_delta: computed as sum(ask_vol - bid_vol) across all price levels
  FootprintBar.cvd: cumulative delta from session start
```

### Academic Basis

- Aggressive order flow as price discovery mechanism: Glosten & Milgrom (1985), "Bid, Ask and Transaction Prices in a Specialist Market"
- Delta as short-term directional predictor: Easley et al. (2012), "Flow Toxicity and Liquidity in a High Frequency World"

### Examples / Edge Cases

- **Neutral delta on trending bar**: Price moves up 10 points but delta is near zero → passive buyers absorbed selling. This is an absorption signal, not a delta signal.
- **High delta on flat bar**: Large positive delta but price doesn't move → sellers absorbed all buying. Bearish context.
- **Delta noise on low-volume bars**: Small absolute delta values on low-volume bars are meaningless. DEEP6 guards against this via `bar.total_vol == 0` checks.

---

## OF-02: CVD — Cumulative Volume Delta

**Category**: Order Flow
**Tags**: cvd, cumulative_delta, trend_confirmation, session_delta
**DEEP6 Signal(s)**: DELT-05 (FLIP), DELT-09 (AT_MIN/AT_MAX), DELT-10 (CVD_DIVERGENCE), DELT-11 (VELOCITY)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 80–126)

### Concept

CVD (Cumulative Volume Delta) is the running sum of bar deltas from session open:

```
CVD[n] = CVD[n-1] + bar_delta[n]
```

CVD shows the net directional pressure over the entire session. A rising CVD means buyers have been consistently more aggressive. A falling CVD means sellers dominate.

CVD is the primary trend confirmation tool in order flow analysis. Price and CVD should trend together in a healthy move. When they diverge, it signals potential reversal.

### Conditions / Setup

CVD is maintained as a session-level running total. DEEP6 tracks:
- `session_cvd_min`: lowest CVD value this session
- `session_cvd_max`: highest CVD value this session
- `cvd_history`: rolling deque of recent CVD values (lookback window)

### Entry / Exit Rules

CVD-based signals:

**DELT-05 (FLIP)**: CVD crosses zero
- `prev_cvd >= 0 and cvd < 0` → bearish flip, direction -1
- `prev_cvd <= 0 and cvd > 0` → bullish flip, direction +1
- Strength: 0.6 (moderate conviction)

**DELT-09 (AT_MIN/AT_MAX)**: CVD at session extreme
- `cvd >= session_cvd_max` → AT_MAX, direction +1
- `cvd <= session_cvd_min` → AT_MIN, direction -1
- Strength: 0.5 (informational)

**DELT-11 (VELOCITY)**: Rate of change of CVD accelerating
- `accel = (cvd[-1] - cvd[-2]) - (cvd[-2] - cvd[-3])`
- Fires if `|accel| > total_vol × velocity_accel_ratio`
- Direction = sign of acceleration

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 80–86:   CVD history and session extremes initialization
  Lines 119–126: CVD history update and session extreme tracking
  Lines 209–221: DELT-05 FLIP detection
  Lines 281–293: DELT-09 AT_MIN/AT_MAX detection
  Lines 318–328: DELT-11 VELOCITY detection
```

### Examples / Edge Cases

- **CVD flip as false signal**: CVD crossing zero on low volume is noise. The scorer requires category agreement — a lone CVD flip rarely reaches TYPE_B.
- **Session reset**: CVD resets to 0 at session open. Overnight CVD is not carried forward.
- **CVD at extreme**: CVD at session max while price is also at session high = confirmation. CVD at session max while price is below session high = potential exhaustion.

---

## OF-03: Delta Divergence — Price vs CVD Disagreement

**Category**: Order Flow
**Tags**: delta_divergence, cvd_divergence, highest_alpha, reversal_signal
**DEEP6 Signal(s)**: DELT-04 (DIVERGENCE), DELT-10 (CVD_DIVERGENCE)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 189–316)

### Concept

Delta divergence is the highest-alpha signal in the delta family. It occurs when price makes a new extreme but CVD fails to confirm:

- **Bearish divergence**: Price at N-bar high, but CVD is NOT at N-bar high → buyers are exhausted, sellers absorbing
- **Bullish divergence**: Price at N-bar low, but CVD is NOT at N-bar low → sellers are exhausted, buyers absorbing

The logic: if price is making new highs but the buying pressure (CVD) is declining, the move is running out of fuel. Smart money is distributing into retail buying.

DELT-10 extends this to multi-bar linear regression: if price slope is positive but CVD slope is negative (or vice versa), it's a sustained divergence.

### Conditions / Setup

**DELT-04 (bar-level divergence)**:
- Requires `len(price_history) >= divergence_lookback` (default lookback)
- Bearish: `prices[-1] == max(prices[-N:])` AND `cvds[-1] < max(cvds[-N:])`
- Bullish: `prices[-1] == min(prices[-N:])` AND `cvds[-1] > min(cvds[-N:])`
- Strength: 0.8 (high conviction)

**DELT-10 (multi-bar regression divergence)**:
- Requires `len(cvd_history) >= cvd_divergence_min_bars`
- Uses `np.polyfit` to compute price slope and CVD slope
- Bearish: `price_slope > 0` AND `cvd_slope < -|price_slope| × cvd_slope_divergence_factor`
- Bullish: `price_slope < 0` AND `cvd_slope > |price_slope| × cvd_slope_divergence_factor`
- Strength: 0.75

### Entry / Exit Rules

Divergence signals contribute to the delta category vote. They are among the most reliable reversal precursors in DEEP6's signal stack.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 189–207: DELT-04 bar-level divergence
  Lines 295–316: DELT-10 multi-bar CVD regression divergence
  Lines 1–18:    Module docstring: "Divergence: highest alpha"
```

### Academic Basis

- Price/volume divergence as reversal predictor: Blau (1995), "Momentum, Direction and Divergence"
- Order flow divergence in futures: Chordia et al. (2002), "Order Imbalance, Liquidity, and Market Returns"

### Examples / Edge Cases

- **False divergence in trending market**: In a strong trend, CVD can lag price for many bars before catching up. Divergence alone is not sufficient — requires zone confluence for TYPE_A.
- **Divergence at key level**: Bearish divergence at a call wall or resistance zone is the highest-quality setup. DEEP6 captures this via GEX wall bonus + divergence category vote.

---

## OF-04: Delta Slingshot — Compressed Then Explosive

**Category**: Order Flow
**Tags**: slingshot, compression, explosive_delta, delt_08, 72_78_win_rate
**DEEP6 Signal(s)**: DELT-08 (SLINGSHOT)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 263–279)

### Concept

The slingshot pattern occurs when delta is compressed (small, near-zero) for several bars, then suddenly explodes in one direction. The compression represents a coiling of energy — neither buyers nor sellers dominating. The explosion represents one side capitulating or a large institutional order hitting the market.

Documented win rate: 72–78% (from module docstring).

### Conditions / Setup

- At least 3 of the prior 4 bars have `|delta| < total_vol × slingshot_quiet_ratio` (small delta)
- Current bar has `|delta| > total_vol × slingshot_explosive_ratio` (large delta)
- Direction = sign of current bar delta

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 263–279: DELT-08 slingshot detection
  Lines 7–18:    Module docstring: "Slingshot: 72-78% win rate"
```

### Examples / Edge Cases

- **Pre-news compression**: Markets often compress delta before major economic releases. The slingshot fires on the first bar after the release.
- **False slingshot**: Compression followed by a single large delta bar that immediately reverses. Requires zone confluence to filter.

---

## OF-05: Delta Trap — Aggressive Delta Followed by Reversal

**Category**: Order Flow
**Tags**: delta_trap, trapped_traders, delt_06, reversal
**DEEP6 Signal(s)**: DELT-06 (TRAP)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 223–237)

### Concept

The delta trap fires when strong directional delta in one bar is immediately followed by price moving in the opposite direction. This indicates that aggressive traders were trapped — they bought/sold aggressively but the market reversed against them, forcing them to exit at a loss.

### Conditions / Setup

- Bullish trap: `prev_delta > total_vol × trap_delta_ratio` (strong buying) AND `bar.close < bar.open` (price dropped)
- Bearish trap: `prev_delta < -total_vol × trap_delta_ratio` (strong selling) AND `bar.close > bar.open` (price rose)
- Strength: 0.7

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 223–237: DELT-06 trap detection
```

---

## OF-06: Volume Profile — POC, Value Area, HVL, LVL

**Category**: Volume Profile
**Tags**: volume_profile, poc, value_area, hvl, lvl, developing_value, tpo
**DEEP6 Signal(s)**: VOLP-04 (POC_MOMENTUM_WAVE)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\volume_profile.py`

### Concept

Volume Profile shows how much volume traded at each price level over a session or period. Key levels:

**POC (Point of Control)**: The price level with the highest volume. This is where the most business was done — the "fairest" price. Price tends to return to POC after excursions.

**Value Area**: The range containing 70% of total volume (one standard deviation equivalent). The Value Area High (VAH) and Value Area Low (VAL) are key support/resistance levels.

**HVL (High Volume Level)**: A price level with significantly above-average volume. Acts as a magnet — price tends to revisit these levels.

**LVL (Low Volume Level)**: A price level with significantly below-average volume. Price tends to move through these quickly (low acceptance).

**Developing Value Area**: The value area as it builds in real-time during the session. Watching how the developing POC migrates tells you where the market is finding acceptance.

### Conditions / Setup

Volume profile is built bar-by-bar. DEEP6 uses `SessionProfile` to:
- Accumulate volume at each price level
- Detect zones (HVL/LVL clusters) every 10 bars
- Update zone scores as price interacts with them

Zone scoring determines whether a zone qualifies for the zone bonus in the scorer (see STRAT-06).

### Entry / Exit Rules

Volume profile levels are used as:
1. Zone bonus trigger in scorer (price at/near zone → +6 to +8 points)
2. "volume_profile" category vote when price is at a zone
3. Context for absorption/exhaustion signals (absorption at POC = highest quality)

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\volume_profile.py
  SessionProfile class: bar-by-bar volume accumulation
  detect_zones(): identifies HVL/LVL clusters
  update_zones(): updates zone scores as price interacts

C:\Users\Tea\DEEP6\deep6\scoring\scorer.py
  Lines 385–405: Zone proximity check and bonus assignment
  Lines 229:     active_zones = profile.get_active_zones(min_score=20)
```

### Academic Basis

- Market Profile theory: Steidlmayer (1984), "Markets and Market Logic"
- Volume at price as support/resistance: Kroll (1993), "The Professional Commodity Trader"
- POC as mean-reversion anchor: Dalton (1990), "Mind Over Markets"

### Examples / Edge Cases

- **POC migration**: If the developing POC migrates upward for 3+ consecutive bars, VOLP-04 fires (POC momentum wave). This indicates the market is finding acceptance at higher prices.
- **LVL as air pocket**: Price moving through an LVL accelerates — there's no volume to slow it down. Use LVLs to identify where stops will run.
- **VAH/VAL as overnight reference**: Previous session's VAH/VAL are key levels for the next day's open.

---

## OF-07: Footprint Chart Interpretation

**Category**: Order Flow
**Tags**: footprint, bid_ask_at_price, level_data, reading_footprint
**Python File**: `C:\Users\Tea\DEEP6\deep6\state\footprint.py`

### Concept

A footprint chart shows bid volume and ask volume at every price level within each bar. Unlike a standard candlestick (which only shows OHLC), a footprint reveals the internal structure of each bar.

Reading a footprint bar:
- Each row = one price level (one tick = 0.25 NQ points = $5)
- Left column = bid volume (sellers were aggressive at this price)
- Right column = ask volume (buyers were aggressive at this price)
- Net delta per level = ask_vol - bid_vol

Key patterns:
- **Absorption**: Large bid volume at a price level but price doesn't fall → buyers absorbing selling
- **Exhaustion**: Large ask volume at a price level but price doesn't rise → sellers absorbing buying
- **Imbalance**: One side dramatically exceeds the other (e.g., 500 ask vs 10 bid = 50:1 ratio)
- **Stacked imbalance**: Multiple consecutive price levels all showing the same directional imbalance

### Conditions / Setup

DEEP6 stores footprint data in `FootprintBar.levels` — a dict mapping tick (integer price) to `LevelData(bid_vol, ask_vol)`.

The footprint is built tick-by-tick via `add_trade()` as trades arrive from the Rithmic feed.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\state\footprint.py
  FootprintBar.levels: dict[int, LevelData] — tick → (bid_vol, ask_vol)
  FootprintBar.bar_delta: sum of (ask_vol - bid_vol) across all levels
  FootprintBar.max_delta / min_delta: intrabar delta extremes (Plan 12-02)
  FootprintBar.poc_price: price level with highest total volume
```

### Examples / Edge Cases

- **Unfinished auction**: Bar closes with large imbalance at the high or low → market didn't finish its business at that level. Expect a return.
- **Absorption at support**: Large bid volume at a key support level with price holding → institutional buyers defending the level.
- **Iceberg detection**: Repeated large bid/ask volume at the same price level across multiple bars → hidden large order being worked.

---

## OF-08: Volume Sequencing (VOLP-01)

**Category**: Volume Profile
**Tags**: volp_01, volume_sequencing, escalating_volume, institutional_buildup
**DEEP6 Signal(s)**: VOLP-01 (SEQUENCING)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 125–173)

### Concept

Volume sequencing detects 3 or more consecutive bars where each bar's volume is at least `step_ratio` (e.g., 1.1×) greater than the prior bar. This escalating volume pattern indicates institutional accumulation or distribution — a large player is building a position over multiple bars.

Direction is determined by the net delta across the qualifying sequence.

### Conditions / Setup

- Minimum 3 consecutive bars (configurable via `vol_seq_min_bars`)
- Each bar's volume >= prior bar's volume × `vol_seq_step_ratio`
- Direction = sign of sum of bar_delta across the sequence
- Strength = `min((run_length - min_bars + 1) / (min_bars + 1), 1.0)`

### Entry / Exit Rules

VOLP-01 contributes to the volume_profile category vote in the scorer. A 5-bar escalating volume sequence with positive delta is a strong bullish signal.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py
  Lines 125–173: _detect_sequencing() — VOLP-01
  Lines 140–154: Walk-backwards run detection
  Lines 159–160: Direction from net delta across run
```

### Examples / Edge Cases

- **Pre-breakout buildup**: Volume sequencing often precedes breakouts. The escalating volume shows increasing conviction.
- **Distribution top**: Escalating volume with negative delta at a resistance level = institutional selling into retail buying.

---

## OF-09: Volume Bubble (VOLP-02)

**Category**: Volume Profile
**Tags**: volp_02, volume_bubble, isolated_high_volume, price_level_anomaly
**DEEP6 Signal(s)**: VOLP-02 (BUBBLE)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 179–222)

### Concept

A volume bubble is a single price level within a bar that has dramatically more volume than the average level in that bar. It indicates that a large order was worked at a specific price — either a large institutional order or a stop cluster being triggered.

The bubble level becomes a reference point: price often returns to it, or it acts as support/resistance.

### Conditions / Setup

- `avg_level_vol = bar.total_vol / len(bar.levels)`
- Bubble threshold = `avg_level_vol × bubble_mult` (configurable)
- Fires at the highest-volume level exceeding the threshold
- Direction: ask dominance (ask_vol > bid_vol) = bullish, bid dominance = bearish
- Strength = `min((best_vol / threshold - 1.0) / 3.0, 1.0)`

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py
  Lines 179–222: _detect_bubble() — VOLP-02
  Lines 191–192: avg_level_vol and threshold computation
  Lines 206–211: Direction from ask/bid dominance at bubble level
```

### Examples / Edge Cases

- **Stop cluster**: A bubble at a round number or prior swing high/low often represents stops being triggered. The direction of the bubble tells you who was stopped out.
- **Iceberg order**: Repeated bubbles at the same price across multiple bars = large hidden order.
- **False bubble on thin bars**: Bars with very few price levels can produce bubbles from small absolute volume. The scorer's zone requirement filters most of these.

---

## OF-10: Time & Sales Analysis for Institutional Detection

**Category**: Order Flow
**Tags**: time_and_sales, institutional_detection, large_prints, block_trades
**Python File**: `C:\Users\Tea\DEEP6\deep6\state\footprint.py`

### Concept

Time & Sales (T&S) is the raw trade tape — every individual transaction with price, size, and side. Institutional traders leave footprints in T&S:

- **Large prints**: Single trades of 50+ contracts (NQ) stand out against typical 1–5 contract retail flow
- **Sweeps**: Rapid sequence of trades at the same price, exhausting all available liquidity at that level
- **Blocks**: Single large trades negotiated off-exchange, printed at a specific price
- **Iceberg detection**: Repeated same-size prints at the same price = hidden large order being worked in pieces

For NQ futures, institutional activity typically shows as:
- 20+ contract prints at key levels
- Rapid bid/ask sweeps through multiple price levels
- Consistent same-side aggression over multiple bars

### Conditions / Setup

DEEP6 captures T&S data via the Rithmic tick feed. Each trade arrives as a callback with price, size, and aggressor side. The `FootprintBar.add_trade()` method accumulates this into the footprint structure.

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\state\footprint.py
  FootprintBar.add_trade(price, size, is_ask): accumulates tick data
  FootprintBar.levels: resulting bid/ask volume per price level
  FootprintBar.max_delta / min_delta: intrabar extremes from tick stream
```

### Examples / Edge Cases

- **Spoofing detection**: Large orders placed and immediately cancelled create false T&S signals. DEEP6's SPOOF_DETECTED veto (via ConfluenceAnnotations) handles this.
- **Wash trades**: Some exchanges allow wash trades that inflate volume without directional meaning. NQ CME data is generally clean.
- **Pre-market vs RTH**: T&S during pre-market hours has different institutional patterns. DEEP6 focuses on RTH (9:30–16:00 ET).

---

## OF-11: POC Momentum Wave (VOLP-04)

**Category**: Volume Profile
**Tags**: volp_04, poc_wave, poc_migration, developing_value, trend_confirmation
**DEEP6 Signal(s)**: VOLP-04 (POC_MOMENTUM_WAVE)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 267–308)

### Concept

The POC momentum wave fires when the Point of Control has migrated monotonically in one direction for N consecutive bars. A rising POC means the market is finding acceptance at progressively higher prices — a bullish structural signal. A falling POC indicates the opposite.

This is distinct from price momentum: the POC can migrate upward even on a sideways price bar if volume concentrates at higher levels.

### Conditions / Setup

- `poc_history` must have at least `poc_wave_bars` entries
- All consecutive differences in the window must have the same sign (monotonic)
- Direction = sign of (last POC - first POC in window)
- Strength = `min(displacement / 10.0, 1.0)` (10 NQ points = full strength)

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py
  Lines 267–308: _detect_poc_wave() — VOLP-04
  Lines 287–294: Monotonic check via consecutive differences
  Lines 296–297: Displacement-based strength

C:\Users\Tea\DEEP6\deep6\engines\live_pipeline.py
  Line 269: self._poc_history[label].append(bar.poc_price)
```

### Examples / Edge Cases

- **Choppy POC**: If the POC oscillates between two levels, the monotonic check fails and no signal fires. This correctly identifies a balanced/rotational market.
- **POC wave at resistance**: POC migrating up into a known resistance zone = distribution signal. Combine with bearish absorption for highest conviction.

---

## OF-12: Delta Tail (DELT-02) — Closing at Intrabar Extreme

**Category**: Order Flow
**Tags**: delt_02, delta_tail, intrabar_extreme, conviction, plan_12_02
**DEEP6 Signal(s)**: DELT-02 (TAIL)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py` (lines 140–165)

### Concept

The delta tail fires when a bar closes at or near its intrabar delta extreme. If a bar's delta peaked at +800 intrabar but closed at +780 (97.5% of the extreme), that's a tail — the buying conviction was sustained through the entire bar.

This is distinct from a bar that briefly spiked to +800 delta but faded to +200 by close. The tail measures whether the directional pressure was maintained.

Plan 12-02 upgraded this from a bar-geometry proxy to true intrabar tracking via `FootprintBar.max_delta` and `min_delta`, which are updated live by `add_trade()`.

### Conditions / Setup

- `delta > 0`: `tail_ratio = delta / max_delta` (if max_delta > 0)
- `delta < 0`: `tail_ratio = delta / min_delta` (if min_delta < 0)
- Fires if `tail_ratio >= cfg.tail_threshold` (default 0.95)
- Strength = tail_ratio

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\delta.py
  Lines 140–165: DELT-02 tail detection (Plan 12-02 version)
  Lines 148–150: FOOTGUN 3 guard for zero extreme
  Lines 62–67:   DeltaResult with delta_quality scalar
  Lines 69–73:   DELTA_FAMILY_BITS whitelist for delta_quality consumers
```

---

## OF-13: Delta Velocity Spike (VOLP-05)

**Category**: Order Flow
**Tags**: volp_05, delta_velocity, rapid_delta_change, momentum_shift
**DEEP6 Signal(s)**: VOLP-05 (DELTA_VELOCITY_SPIKE)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 314–350)

### Concept

Delta velocity spike detects a rapid change in bar delta between consecutive bars. If the prior bar had delta of -200 and the current bar has delta of +600, the velocity is +800 — a sudden shift from selling to buying pressure.

This often precedes or accompanies a reversal, as it shows the dominant side switching rapidly.

### Conditions / Setup

- `velocity = bar.bar_delta - prior_bar.bar_delta`
- Threshold = `vol_ema × delta_velocity_mult`
- Fires if `|velocity| > threshold`
- Direction = sign of velocity
- Strength = `min(|velocity| / (threshold × 3.0), 1.0)`

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py
  Lines 314–350: _detect_delta_velocity() — VOLP-05
```

---

## OF-14: Big Delta Per Level (VOLP-06)

**Category**: Order Flow
**Tags**: volp_06, big_delta_per_level, level_dominance, institutional_level
**DEEP6 Signal(s)**: VOLP-06 (BIG_DELTA_PER_LEVEL)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py` (lines 356–397)

### Concept

Big delta per level fires when a single price level within a bar has a dominant net delta (ask_vol - bid_vol). This indicates that at one specific price, one side was overwhelmingly more aggressive — a sign of institutional activity at that level.

### Conditions / Setup

- Iterates all levels in `bar.levels`
- `net_delta = ask_vol - bid_vol` per level
- Fires at the level with highest `|net_delta|` if it exceeds `big_delta_level_threshold`
- Direction = sign of net_delta at that level
- Strength = `min((|net_delta| - threshold) / (threshold × 2.0), 1.0)`

### DEEP6 Implementation

```
C:\Users\Tea\DEEP6\deep6\engines\vol_patterns.py
  Lines 356–397: _detect_big_delta_per_level() — VOLP-06
```
