# Market Microstructure — DEEP6 Knowledge Domain

**Last verified: 2026-05-12**
**Source research:** `C:\Users\Tea\DEEP6\.planning\research\pine\deep\microstructure.md`
**Source practitioners:** `C:\Users\Tea\DEEP6\.planning\research\pine\deep\practitioners.md`
**DEEP6 engines:** `C:\Users\Tea\DEEP6\deep6\engines\absorption.py`, `exhaustion.py`, `iceberg.py`, `imbalance.py`, `delta.py`

---

## MICRO-01: Absorption (Buy-Side and Sell-Side)

**Category**: Microstructure
**Tags**: absorption, passive, limit orders, institutional defense, reversal, stopping volume
**DEEP6 Signal(s)**: ABS-01 (Classic), ABS-02 (Passive), ABS-03 (Stopping Volume), ABS-04 (Effort vs Result)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\absorption.py`

### Concept
Absorption is the highest-alpha reversal signal in order flow. It occurs when passive limit orders on one side of the market absorb aggressive market orders from the other side without allowing price to advance. The absorbing side is defending a price level — typically an institution or large participant with a directional conviction.

Buy-side absorption: sellers aggressively push price down, but passive buyers absorb every sell order at a level. Price stalls or barely moves despite heavy sell volume. The buyers are "absorbing" the sellers.

Sell-side absorption: the mirror. Buyers push up, passive sellers absorb at a level. Price stalls at resistance.

The key distinction from exhaustion: absorption is an *active defense* by the passive side. Exhaustion is the *collapse* of the aggressive side. Both produce reversals, but absorption is the stronger signal because it implies institutional intent.

### Conditions / Setup
- Price approaches a structural level (VAH, VAL, prior-day H/L, gamma wall, round number)
- Aggressive volume hits the level repeatedly
- Price fails to advance beyond the level despite the aggression
- Delta grows (or shrinks) while price holds — the "effort vs result" mismatch
- Wick volume is high and balanced (both sides active) in the classic variant

### Entry / Exit Rules
- **Classic (ABS-01):** Wick volume >= 30% of bar total AND delta ratio < 0.35 (balanced). Direction: upper wick = bearish absorption, lower wick = bullish absorption.
- **Passive (ABS-02):** >= 40% of bar volume concentrates in the top or bottom 20% of bar range, but price closes away from that extreme.
- **Stopping Volume (ABS-03):** Bar volume > 1.5x EMA AND POC falls in the wick (not the body).
- **Effort vs Result (ABS-04):** Bar volume > 1.5x EMA AND bar range < 40% of ATR(20).
- Entry: fade the absorbed side on the next bar's confirmation close. Stop beyond the absorption extreme.
- VA extreme bonus (ABS-07): signals at VAH or VAL get a strength boost.

### Risk Management
- Stop: 1-2 ticks beyond the absorption price (the level being defended)
- Target: opposite VA boundary, VPOC, or next structural level
- Invalidation: absorption price breaks with expanding volume (not drift)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\absorption.py` lines 1-243

Four variants detected per bar:
- `AbsorptionType.CLASSIC` (lines 102-133): wick_pct >= `cfg.absorb_wick_min`, delta_ratio < `cfg.absorb_delta_max`
- `AbsorptionType.PASSIVE` (lines 135-174): top/bottom zone vol >= `cfg.passive_vol_pct`
- `AbsorptionType.STOPPING_VOLUME` (lines 176-205): total_vol > vol_ema * `cfg.stop_vol_mult`, POC in wick
- `AbsorptionType.EFFORT_VS_RESULT` (lines 207-224): total_vol > vol_ema * `cfg.evr_vol_mult`, range < atr * `cfg.evr_range_cap`
- VA extreme bonus applied at lines 229-241 via `cfg.va_extreme_ticks` proximity check

All thresholds are ATR-adaptive (ARCH-03, SCOR-05). Config lives in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py` as `AbsorptionConfig`.

### Academic Basis
- Eisler, Bouchaud & Kockelkoren (2012), *Price Impact of Order Book Events* (arXiv:0904.0900): formal decomposition showing limit-order arrivals cancel market-order impact at a level — the microstructure basis for absorption.
- Jones, Kaul & Lipson (1994), *Transactions, volume, and volatility* (RFS): volume decomposition framework.
- Formal definition: `Absorption(L, W) = Σ aggressor_volume in [L-ε, L+ε] / max(1, |Δmid in W, ticks|)`. Absorption z >= 2.5 with Δmid <= 1 tick and aggressor-side dominance >= 70% is the canonical signal.

### Examples / Edge Cases
- **Spoof wall:** A large resting order that vanishes before being tested is NOT absorption. DEEP6's `counter_spoof.py` engine (MS-08 SpoofSuppressor) vetoes absorption signals when > 60% of resting size has mean order lifetime < 500ms and cancel rate > 90%.
- **Trend day:** Absorption signals at mid-range on a trend day are noise. Only trust absorption at structural extremes.
- **Round numbers:** Absorption at NQ round numbers (every 25, 50, 100 points) gets a 1.25x weight boost per MS-10 (Bloomfield-Chin-Craig 2024 empirical finding).

### Backtest Notes
Not yet calibrated on Databento MBO. Thresholds in `AbsorptionConfig` are starting points requiring validation on historical NQ replay.

---

## MICRO-02: Exhaustion (Momentum Failure)

**Category**: Microstructure
**Tags**: exhaustion, momentum failure, zero prints, thin prints, fat prints, reversal
**DEEP6 Signal(s)**: EXH-01 (Zero Print), EXH-02 (Exhaustion Print), EXH-03 (Thin Print), EXH-04 (Fat Print), EXH-05 (Fading Momentum), EXH-06 (Bid/Ask Fade)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py`

### Concept
Exhaustion detects when aggressive traders run out of ammunition. Unlike absorption (where the passive side actively defends), exhaustion means the aggressor simply has no more fuel. Price extends in one direction, then the aggressive flow collapses — not because someone is defending, but because the buyers (or sellers) are done.

Exhaustion is an earlier warning than absorption but a weaker signal. It often precedes absorption: exhaustion fires first (aggressor fading), then absorption fires (passive side steps in). Together they form the highest-conviction reversal setup in DEEP6.

Key exhaustion signatures:
- **Zero prints:** Price levels within the bar body with zero volume on both sides — the market moved through so fast no one traded there. These are "unfinished business" magnets.
- **Thin prints:** Volume at a price row < 5% of the bar's max level volume — confirms a fast, low-conviction move.
- **Fat prints:** Volume at a price row >> average — strong acceptance, future support/resistance.
- **Exhaustion print:** Heavy single-side volume at the bar extreme with no follow-through.
- **Fading momentum:** Delta opposes price direction — buyers pushed price up but sellers are winning on delta.

### Conditions / Setup
- Price makes a new extreme (high or low)
- Delta trajectory diverges from price direction (universal gate EXH-07)
- Volume at the extreme is thin (fast move) or the delta is collapsing
- No follow-through on the next bar

### Entry / Exit Rules
- **Zero Print (EXH-01):** Any price level within bar body with ask_vol == 0 AND bid_vol == 0. Gate-exempt from delta trajectory check (structural, not delta-dependent).
- **Exhaustion Print (EXH-02):** Heavy ask vol at bar high (bearish) or heavy bid vol at bar low (bullish). Requires delta gate pass.
- **Thin Print (EXH-03):** >= 3 levels within bar body with vol < 5% of bar's max level vol.
- **Fat Print (EXH-04):** Any level with vol > `cfg.fat_mult` x average level vol — marks strong acceptance.
- **Fading Momentum (EXH-05):** |bar_delta| > 15% of total_vol AND delta opposes bar direction.
- **Bid/Ask Fade (EXH-06):** Current bar's ask at high < 60% of prior bar's ask at high (buyers fading).
- Entry: fade the exhausted direction on the next bar's rejection close.

### Risk Management
- Stop: beyond the exhaustion extreme
- Target: VPOC, prior VAH/VAL, or next structural level
- Invalidation: next bar extends the exhaustion direction

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\exhaustion.py` lines 1-316

Universal delta trajectory gate at lines 70-106 (`_delta_trajectory_gate`): bullish bar requires negative delta to pass; bearish bar requires positive delta. Gate-exempt: EXH-01 (Zero Print).

Cooldown system (EXH-08) at lines 50-67: prevents same sub-type from firing on consecutive bars. Reset at session start via `reset_cooldowns()`.

Six variants: `ExhaustionType.ZERO_PRINT` (lines 149-166), `EXHAUSTION_PRINT` (lines 174-208), `THIN_PRINT` (lines 210-231), `FAT_PRINT` (lines 233-250), `FADING_MOMENTUM` (lines 252-272), `BID_ASK_FADE` (lines 274-314).

Config: `ExhaustionConfig` in `C:\Users\Tea\DEEP6\deep6\engines\signal_config.py`.

### Academic Basis
- Bacry & Muzy (2014), *Hawkes model for price and trades* (arXiv:1301.1135): Hawkes self-excitation decays rapidly past a level — the formal model for exhaustion post-break.
- Lillo & Farmer (2004), *Long memory of the efficient market*: signed order flow has long memory (Hurst ~0.7) yet prices are efficient — because passive liquidity adjusts. When price fails to follow persistent signed flow, the passive side is absorbing. Exhaustion is the flip side: when signed flow collapses, the aggressor is done.

### Examples / Edge Cases
- **Trend day:** Thin prints in the middle of a trend day are NOT exhaustion — they're the LVN gap-through pattern. Only trust exhaustion at structural extremes.
- **Zero prints as targets:** Zero prints are "unfinished business" — price will return to fill them. Use as targets, not entries.
- **Fat prints as future S/R:** Fat prints mark strong acceptance levels. They become support on pullbacks (bullish fat print) or resistance on rallies (bearish fat print).

### Backtest Notes
Delta gate (EXH-07) was added in D-08 to reduce false positives. Cooldown system (EXH-08) prevents signal spam. Both require calibration on Databento replay.

---

## MICRO-03: Order Flow Imbalance (Bid/Ask Imbalance at Price Levels)

**Category**: Microstructure
**Tags**: order flow imbalance, OFI, queue imbalance, bid/ask, stacked imbalance, DOM
**DEEP6 Signal(s)**: MS-03 (QueueImbalanceBand), stacked imbalance signals
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py`

### Concept
Order flow imbalance (OFI) measures the net directional pressure at each price level. At any given price, if ask volume (buy aggressors) far exceeds bid volume (sell aggressors), buyers are in control at that level. The reverse signals seller control.

Queue Imbalance (QI) at the top of book: `QI = (Q_bid - Q_ask) / (Q_bid + Q_ask)`. Range -1 to +1. Positive = more resting bids (buyers defending), negative = more resting asks (sellers defending).

Stacked imbalance: 3+ consecutive diagonal imbalances across adjacent price levels (ask >= 3x bid at consecutive prices, or inverse). Signals sustained one-sided aggression across the price ladder — a breakout accelerant or a strong support/resistance zone.

The level-interaction insight: QI computed against a 1-3 tick band around a structural level inverts the normal sign relationship during absorption. Price pushes into resistance, top-of-book QI shows aggressive-side dominance (bid-lifting), yet deeper band QI shows passive-side dominance. This divergence across book depth at the level is the formal microstructure definition of absorption.

### Conditions / Setup
- At structural levels: VAH, VAL, prior-day H/L, gamma walls
- QI >= 0.6 at top-of-book with combined size >= rolling median (Gould-Bonart threshold)
- QI >= 0.8 is high-confidence regime
- Size filter mandatory: 70/30 imbalance on 3 total contracts is noise

### Entry / Exit Rules
- **QI against price approach** at a level = absorption signal (fade)
- **QI with price approach** at a level = breakout accelerant (follow)
- **Stacked imbalance (3+ levels):** enter WITH trend on pullback to stack base; stop just below/above stack base
- Strongest setups: stacked imbalance + level confirmation + breakout

### Risk Management
- Stop: just below (buy stack) or above (sell stack) the stack base
- Target: next structural level in breakout direction
- Invalidation: stack prices re-visited AND absorbed from opposite side

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\imbalance.py` — stacked imbalance detection.

MS-03 QueueImbalanceBand rule: QI computed across top-3 levels within 3 ticks of a flagged level. |QI| >= 0.6 with combined size >= rolling median. Direction interpretation: against price approach = absorption; with approach = breakout accelerant.

### Academic Basis
- Cont, Kukanov & Stoikov (2014), *Price Impact of Order Book Events* (J. Financial Econometrics 12(1), 47-88): Δprice ≈ β·OFI, β ∝ 1/depth. OFI dominates signed volume as the right regressor.
- Gould & Bonart (2016), *Queue Imbalance as One-Tick-Ahead Predictor* (arXiv:1512.03492): QI predicts next mid move with 55-65% binary accuracy for large-tick instruments. |QI| >= 0.6 threshold.
- Cont & de Larrard (2013), *Price Dynamics in Markovian LOB* (SIAM J. Fin. Math.): next move sign determined by which side's queue is thinner.
- Lipton, Pesavento & Sotiropoulos (2013), *Trade arrival dynamics and quote imbalance* (arXiv:1312.0514): closed-form up/down probability from queue state.

### Examples / Edge Cases
- **Spoofed imbalance:** Large resting orders that cancel before execution create false QI signals. DEEP6's spoof suppressor (MS-08) vetoes imbalance signals when order lifetime < 500ms.
- **Thin book:** NQ near RTH open has 1-5 contracts at top-of-book. QI is unreliable until combined size >= median.

---

## MICRO-04: Delta Divergence (CVD vs Price)

**Category**: Microstructure
**Tags**: delta, CVD, cumulative delta, divergence, effort vs result, Wyckoff
**DEEP6 Signal(s)**: MS-06 (CVDDivergenceAtLevel), EXH-05 (Fading Momentum)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\delta.py`

### Concept
Cumulative Volume Delta (CVD) is the running sum of (ask_vol - bid_vol) across all bars. It tracks the net directional pressure of aggressive traders over time.

Delta divergence: price makes a new high but CVD makes a lower high (or price makes a new low but CVD makes a higher low). This means the aggressive side is thinning — buyers pushed price up but with less and less conviction. The passive side is quietly accumulating against the trend.

This is the Wyckoff "effort vs result" principle given a quantitative form: high effort (volume) with no result (price movement) = absorption. Low effort (declining delta) with continued result (price extension) = unsustainable.

CVD divergence inside a band around a structural level is the highest-signal form. Bare CVD divergence in free space lacks the structural anchor.

### Conditions / Setup
- Price makes local extreme at or near a structural level
- CVD fails to confirm by >= 1σ of its rolling noise
- Minimum 20-bar window for the divergence
- CVD slope >= 1σ of rolling CVD noise to filter noise

### Entry / Exit Rules
- **Bullish divergence:** price makes lower low while CVD makes higher low over >= 30 bars
- **Bearish divergence:** price makes higher high while CVD makes lower high
- Entry: fade the divergence direction on the next bar's rejection close
- Require the divergence to occur at a T1/T2 structural level (Valtos rule: alone, delta divergence is noise)

### Risk Management
- Stop: beyond the divergence extreme
- Target: VPOC, opposite VA boundary
- Invalidation: new delta high/low confirms direction

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\delta.py` — CVD tracking and divergence detection.

MS-06 CVDDivergenceAtLevel: fires when price makes local extreme at/near a flagged level AND CVD fails to confirm by >= 1σ of rolling noise. Requires >= 20-bar window.

EXH-05 Fading Momentum in `exhaustion.py` lines 252-272: simpler single-bar version — |bar_delta| > 15% of total_vol AND delta opposes bar direction.

### Academic Basis
- Lillo & Farmer (2004), *Long memory of the efficient market* (Studies in Nonlinear Dynamics & Econometrics): signed order flow has long memory (Hurst ~0.7) yet prices are efficient — passive liquidity adapts. CVD divergence is the observable manifestation of this adaptation.
- Bouchaud, Gefen, Potters & Wyart (2004), *Fluctuations and response in financial markets*: passive liquidity adjusts to absorb persistent flow. When price fails to follow persistent signed flow, the passive side is absorbing.

### Examples / Edge Cases
- **Trend day:** CVD divergence on a trend day is often a false signal. Disable reversal trades when P-shape or b-shape profile is detected.
- **Academic caveat:** CVD divergence is practitioner-heavy, academically thin. Rely on Lillo-Farmer long-memory framing rather than direct academic support for the divergence pattern itself.

---

## MICRO-05: Volume Profile Basics (POC, Value Area, HVN, LVN)

**Category**: Microstructure
**Tags**: volume profile, POC, value area, HVN, LVN, VPOC, VAH, VAL
**DEEP6 Signal(s)**: POC signals, zone registry levels
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\volume_profile.py`, `C:\Users\Tea\DEEP6\deep6\engines\poc.py`

### Concept
Volume Profile is the distribution of traded volume across price levels over a session or period. It answers: "where did the most trading happen?" rather than "when?"

Key components:
- **POC (Point of Control):** The price level with the highest traded volume. The "fairest price" — where the most business was done. Acts as a magnet for price.
- **VPOC:** Volume-based POC (vs TPO-based POC in Market Profile). More actionable for HFT-dominated markets because institutions trade volume, not time.
- **Value Area (VA):** The price range containing ~70% of total volume (1 standard deviation around POC). Contains VAH and VAL.
- **VAH (Value Area High):** Upper boundary of the value area. Acts as resistance when approached from below; support when price is above it.
- **VAL (Value Area Low):** Lower boundary. Acts as support from above; resistance from below.
- **HVN (High Volume Node):** Price cluster with above-average volume. Strong support/resistance — price tends to slow or reverse here.
- **LVN (Low Volume Node):** Price cluster with below-average volume. Price tends to move through quickly — a "fast lane."

### Conditions / Setup
- Build from RTH session data (9:30-16:15 ET for NQ)
- Naked/Virgin POC (nPOC): a prior-session VPOC never revisited. Acts as magnet — ~80% get retested per Dalton.
- Composite profile: multi-day aggregation locates longer-timeframe VAH/VAL/POC

### Entry / Exit Rules
- **At POC/nPOC:** Expect absorption (large resting orders absorb aggressors, delta divergence). Trade with the absorbing side.
- **At VAH (responsive):** Look for exhaustion of the aggressor. Fade back to POC.
- **At VAH (initiative break):** Look for acceptance (sustained delta, volume expansion). Trade continuation.
- **At LVN:** Price should move fast. Do NOT enter inside an LVN; wait for resolution at the next HVN.
- **At HVN edge:** Absorption + same-direction momentum within 5 bars = entry signal (E8 trigger).

### Risk Management
- Stop: beyond the level by the zone width + 2 ticks
- Target: opposite VA boundary or next structural level
- Invalidation: acceptance at the level (volume builds where it shouldn't)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\volume_profile.py` — volume profile construction.
`C:\Users\Tea\DEEP6\deep6\engines\poc.py` — POC/VAH/VAL computation, provides vah/val to absorption engine.
`C:\Users\Tea\DEEP6\deep6\engines\zone_registry.py` — level registry including HVN/LVN zones.

ABS-07 VA extreme bonus in `absorption.py` lines 229-241: absorption signals at VAH or VAL get a strength boost via `cfg.va_extreme_ticks` proximity check.

### Academic Basis
- Cont, Stoikov & Talreja (2010), *Stochastic Model for Order Book Dynamics* (Operations Research): Markovian LOB queueing model — HVNs correspond to price levels where queue replenishment rate exceeds depletion rate.
- Cont & de Larrard (2013): queue depletion events at LVNs produce rapid price moves — the formal basis for LVN fast-lane behavior.

---

## MICRO-06: Market Depth / DOM (40+ Level Order Book)

**Category**: Microstructure
**Tags**: DOM, depth of market, order book, L2, institutional footprint, queue
**DEEP6 Signal(s)**: MS-03 (QueueImbalanceBand), MS-11 (DepthAsymmetry)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\imbalance.py`

### Concept
The Depth of Market (DOM) is the full limit order book — all resting bid and ask orders at every price level. Rithmic via async-rithmic provides 40+ levels per side, identical to what institutional participants see.

The DOM reveals institutional intent that the tape alone cannot show. A large resting bid 10 levels below the market is a signal of institutional support. A large resting ask 5 levels above is a signal of institutional resistance. These resting orders are the "walls" that absorption signals detect being defended.

Depth asymmetry: when cumulative depth within 5 ticks on one side exceeds the other by >= 3x AND the thick side faces the price approach, the thick side wins per Cont-de Larrard queue depletion theory.

### Conditions / Setup
- Rithmic L2 DOM data via async-rithmic (40+ levels per side)
- Depth asymmetry: cumulative depth within 5 ticks, one side >= 3x the other
- The thick side faces the price approach (not behind it)
- Combined size >= rolling median (size filter mandatory)

### Entry / Exit Rules
- **MS-11 DepthAsymmetry:** Fire when cumulative depth within 5 ticks on one side exceeds the other by >= 3x AND the thick side faces the price approach. Strong side wins per Cont-de Larrard.
- **MS-03 QueueImbalanceBand:** QI computed across top-3 levels within 3 ticks of a flagged level. |QI| >= 0.6 with combined size >= rolling median.

### Risk Management
- Stop: beyond the thick side's outer edge
- Invalidation: thick side disappears (spoof) or price breaks through with volume

### DEEP6 Implementation
DOM state maintained in NumPy pre-allocated price-indexed arrays (hot path). Per-event update: O(k) where k = number of levels in the band. See `C:\Users\Tea\DEEP6\.planning\research\FEATURES.md` for implementation details.

MS-11 DepthAsymmetry: cumulative depth within 5 ticks, one side >= 3x other, thick side faces approach.

### Academic Basis
- Cont, Stoikov & Talreja (2010), *Stochastic Model for Order Book Dynamics*: Markovian LOB model — queue depletion determines next price move direction.
- Cont & de Larrard (2013): conditional on queue depletion, next mid-price move sign determined by which side's queue is thinner.
- Gould & Bonart (2016): QI predicts next mid move with 55-65% binary accuracy for large-tick instruments.

---

## MICRO-07: Footprint Chart Reading (Bid/Ask Volume Per Price Level Per Bar)

**Category**: Microstructure
**Tags**: footprint, bid/ask, price level, bar, tick classification, aggressor
**DEEP6 Signal(s)**: All absorption and exhaustion signals depend on footprint data
**Python File**: `C:\Users\Tea\DEEP6\deep6\state\footprint.py`

### Concept
A footprint chart shows bid volume and ask volume at every price level within each bar. Where a standard candlestick shows only OHLCV, a footprint shows the full story: how much buying and selling happened at each price tick.

Reading a footprint bar:
- **Ask volume (right side):** Buy aggressors — market orders that lifted the offer. High ask vol at a price = buyers were aggressive there.
- **Bid volume (left side):** Sell aggressors — market orders that hit the bid. High bid vol at a price = sellers were aggressive there.
- **Delta at a level:** ask_vol - bid_vol. Positive = net buying, negative = net selling.
- **Bar delta:** sum of all level deltas. The net directional pressure for the entire bar.
- **POC of the bar:** The price level with the highest total volume within the bar.

The footprint is the raw material for every DEEP6 signal. Absorption, exhaustion, imbalance, delta divergence — all are computed from footprint data.

### Conditions / Setup
- Rithmic provides aggressor side natively via `TransactionType.BUY` or `SELL` in the `LAST_TRADE` callback
- Price stored as integer ticks (price / 0.25 for NQ) to avoid floating-point key collisions
- Bar closes trigger signal computation across all engines

### Entry / Exit Rules
- Not a standalone signal — the footprint is the data layer, not a signal itself
- All DEEP6 signals are derived from `FootprintBar.levels` (dict of tick -> FootprintLevel)

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\state\footprint.py` — `FootprintBar` and `FootprintLevel` data structures.

`FootprintBar` fields: open, high, low, close, levels (dict[int, FootprintLevel]), total_vol, bar_delta, cvd, poc_price, bar_range.
`FootprintLevel` fields: bid_vol (sell aggressor), ask_vol (buy aggressor).

Tick encoding: `price_to_tick(price) = round(price / TICK_SIZE)` where TICK_SIZE = 0.25 for NQ.

### Academic Basis
- Lee & Ready (1991), *Inferring Trade Direction from Intraday Data* (J. Finance): quote+tick test trade classifier. Superseded for DEEP6 by Rithmic's native aggressor field.
- Databento MBO: `side` field on trade records (F=buyer aggressor, A=seller aggressor) provides equivalent direct classification for historical replay.

---

## MICRO-08: Iceberg Orders (Detection via Large Passive Fills)

**Category**: Microstructure
**Tags**: iceberg, hidden liquidity, passive fills, replenishment, HVr
**DEEP6 Signal(s)**: MS-02 (IcebergAtLevel)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\iceberg.py`

### Concept
Iceberg orders are large limit orders that display only a small "tip" (visible size) while hiding the bulk of the order. When the visible slice is filled, the exchange automatically replenishes it with another slice of the same size. This continues until the full hidden order is filled.

Detection signature on the MBO tape: a market order fully clears the visible resting size at a level, then within ~1-50ms a new displayed slice of identical size appears at the same price before any opposite-side book change. This execution-replenishment pattern is statistically detectable.

Hidden Volume Ratio (HVr): cumulative executed volume at a price / cumulative displayed volume observed at that price within a rolling window. HVr >> 1 indicates an iceberg. Practitioner threshold: HVr >= 2.0 over a 60-second window.

Icebergs cluster at structural levels because institutional execution algos (TWAP/VWAP slicers) place display size at prices where passive fills are likely — prior value-area extremes, prior-day H/L, round numbers. Absorption IS iceberg execution against aggressive takers.

### Conditions / Setup
- Price at a structural level (VAH, VAL, prior-day H/L, gamma wall, round number)
- HVr >= 2.0 over 60-second window at the level
- At least 2 Zotikov replenishment events detected (market order clears visible size, new slice appears within 100ms at same price)
- Replenishment gap < 100ms, size equals prior displayed tranche within ±1 lot

### Entry / Exit Rules
- **MS-02 IcebergAtLevel:** Fire when HVr at price in [L-ε, L+ε] >= 2.0 over 60s AND at least 2 replenishment events detected.
- Iceberg presence increases fill probability at the level (Frey-Sandås: real liquidity, not withdrawal)
- Promote level's confluence grade by 1 tier when >= 3 absorption events fire at same price (Bookmap rule)
- **Iceberg failure reversal (Davies):** If iceberg-suspected level breaks AND opposite-direction stacked imbalance fires within 3 bars, flip bias and enter in break direction.

### Risk Management
- Stop: 1-2 ticks beyond the iceberg price
- Target: opposite VA boundary
- Invalidation: iceberg disappears AND opposite market orders hit size

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\iceberg.py` — iceberg detection engine.

Per-price-level circular buffer for HVr computation. Zotikov replenishment pattern detection on MBO events. O(1) amortized per event.

MS-02 IcebergAtLevel: HVr >= 2.0 over 60s AND >= 2 replenishment events at [L-ε, L+ε].

### Academic Basis
- Hautsch & Huang (2012), *On the Dark Side of the Market* (SFB 649 DP, SSRN 2004231): hidden liquidity concentrates where observable state predicts it — tight visible spreads, thin visible depth, recent adverse price movement.
- Frey & Sandås (2017), *Impact of Iceberg Orders in LOBs* (Quarterly J. of Finance 7(3)): iceberg presence increases fill probability; real liquidity, not withdrawal.
- Zotikov (2019), *CME Iceberg Order Detection* (arXiv:1909.09495): replenishment-pattern classifier >90% precision on CME. Replenishment gap < 100ms, size equals prior tranche within ±1 lot.
- Bookmap caveat: "It is impossible to visually or programmatically identify native icebergs with certainty" — treat as probabilistic.

### Backtest Notes
Zotikov's >90% precision is on CME data with MBO. DEEP6 uses Databento MBO for historical replay, which provides the same event granularity. Live detection via async-rithmic requires the full L2 DOM stream.

---

## MICRO-09: Spoofing Patterns (Large Orders That Disappear)

**Category**: Microstructure
**Tags**: spoofing, layering, manipulation, cancel rate, order lifetime, toxic flow
**DEEP6 Signal(s)**: MS-08 (SpoofSuppressor — VETO signal)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\counter_spoof.py`

### Concept
Spoofing is the placement of large limit orders with no intent to fill, designed to create a false impression of supply or demand. The spoof order induces real traders to move price, then the spoofer cancels before execution and profits from the induced move.

Spoof orders are placed just outside the BBO, canceled with probability >> 0.9 before execution, and trigger a book-imbalance signal that induces real traders to move price.

Detection features:
- Order-to-trade ratio at the quote level (> 10:1 suspicious)
- Order lifetime distribution bimodal: real orders have long or filled lifetimes; spoofs have very short (<500ms) cancellations
- Size asymmetry: spoof side carries >3x the size of the genuine side
- Cancellation clusters within ~100ms of opposite-side trade

Spoofs cluster approaching round numbers and prior-day extremes because those are where passive size looks most "believable." A genuine wall has slow arrivals, long mean lifetime, and fills contribute to price stall. A spoof wall has burst arrival, short lifetime, and vanishes before being tested.

### Conditions / Setup
- Large resting order appears at or near a structural level
- Order lifetime < 500ms AND cancel rate > 90% over last 30s
- > 60% of resting size on the "absorbing" side meets these criteria
- Size asymmetry: spoof side > 3x genuine side

### Entry / Exit Rules
- **MS-08 SpoofSuppressor:** VETO any absorption signal when > 60% of resting size on the "absorbing" side has mean order lifetime < 500ms and cancel rate > 90% over last 30s.
- This is a VETO, not a score — it overrides absorption signals entirely.
- Cancellation impact is nearly as large as market-order impact (Eisler-Bouchaud), so walls that vanish dominate walls that hold in naive feature engineering.

### Risk Management
- MS-08 is a hard prerequisite for absorption signals — spoof detection must pass before any absorption entry is considered.

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\counter_spoof.py` — spoof detection and suppression.

Per-order hash by order_id; eject after 5s max lifetime. Tracks order lifetime distribution and cancel rate per price level. O(1) per add/cancel event.

MS-08 SpoofSuppressor: VETO fires when > 60% of resting size has mean lifetime < 500ms AND cancel rate > 90% over last 30s.

### Academic Basis
- Eisler, Bouchaud & Kockelkoren (2012), *Price Impact of Order Book Events* (arXiv:0904.0900): cancellation impact ≈ market-order impact. Formal basis for why spoofing works.
- Cartea, Jaimungal & Wang (2020), *Spoofing and Price Manipulation in Order Driven Markets* (Oxford-Man Institute): optimal spoof strategy + detection conditions.
- CFTC Spoofing Corpus (2025), *Capital Markets Law Journal* (Oxford): 204 cases across CFTC/CME/ICE. Operational patterns: burst arrival, short lifetime, size asymmetry, cancellation clusters.

---

## MICRO-10: VPIN (Volume-Synchronized Probability of Informed Trading)

**Category**: Microstructure
**Tags**: VPIN, toxicity, informed trading, flow toxicity, regime indicator
**DEEP6 Signal(s)**: MS-04 (VPINRegimeShift)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py`

### Concept
VPIN (Volume-Synchronized Probability of Informed Trading) measures the probability that a given trade is from an informed participant who will adversely select passive liquidity providers. It is computed in volume time (buckets of fixed volume, not clock time):

`VPIN = E[|V_buy - V_sell|] / V_bucket`

Elevated VPIN indicates toxic (informed) flow. The key insight for DEEP6: VPIN is a regime indicator, not a threshold trigger. Its *change* around a level is what matters.

- VPIN falling while price approaches a level: absorption by informed passive = level holds
- VPIN rising while price approaches a level: informed aggressors running the stops = level breaks

### Conditions / Setup
- 50-bucket window with bucket size = ADV/50
- Operational thresholds: 0.70 (elevated), 0.85 (toxic) — must be instrument-calibrated for NQ
- MS-04 fires when VPIN over last 10 buckets drops >= 1σ from prior 40-bucket mean while price within 5 ticks of a flagged level (absorption signal)
- Opposite rule: VPIN rises >= 1σ = breakout signal

### Entry / Exit Rules
- **MS-04 VPINRegimeShift:** Fire when VPIN drops >= 1σ from prior 40-bucket mean while price within 5 ticks of a flagged level. Opposite rule for break: VPIN rises >= 1σ.
- Use as a regime filter, not a standalone entry signal.

### Risk Management
- VPIN is a modifier/filter, not a primary entry signal. Combine with absorption (MS-01) and queue imbalance (MS-03).

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py` — VPIN computation.

Running sums for V_buy and V_sell. 50-bucket FIFO. CDF updated every N buckets. O(1) per trade.

MS-04 VPINRegimeShift: VPIN over last 10 buckets vs prior 40-bucket mean. Threshold: >= 1σ change while price within 5 ticks of flagged level.

### Academic Basis
- Easley, López de Prado & O'Hara (2012), *Flow Toxicity and Liquidity in a High Frequency World* (Review of Financial Studies 25(5), 1457-1493): VPIN toxicity metric, volume-time bucketing. Flash crash precursor claim.
- Andersen & Bondarenko (2014), *VPIN and the flash crash* (J. Empirical Finance): CONTRARY EVIDENCE — VPIN peaked AFTER the flash crash, not before. Canonical 0.99 threshold has poor short-run volatility prediction. Treat canonical thresholds as LOW confidence.
- Practitioner calibration: 50-bucket window, thresholds 0.70 (elevated) and 0.85 (toxic). Must be NQ-calibrated.

### Backtest Notes
Andersen-Bondarenko (2014) is a significant caveat. Use VPIN as a regime indicator (its change, not its level) and calibrate thresholds on Databento NQ MBO data before relying on it.

---

## MICRO-11: Kyle's Lambda and Price Impact at Levels

**Category**: Microstructure
**Tags**: Kyle lambda, price impact, market impact, informed flow, liquidity
**DEEP6 Signal(s)**: MS-05 (KyleLambdaCompression)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py`

### Concept
Kyle's lambda (λ) is the price change per unit of signed order flow. It measures how much price moves per unit of buying or selling pressure. High λ = illiquid, price moves a lot per trade. Low λ = liquid, price barely moves per trade.

λ is not constant. It rises during toxic flow episodes (consistent with VPIN) and falls during benign two-sided flow. At structural levels, λ behavior reveals whether absorption is working:

- λ falls at a level: liquidity is cheap, absorption is working, level holds
- λ rises at a level: toxic run, informed aggressors dominating, level breaks

Cancellation impact is nearly as large as market-order impact (Eisler-Bouchaud), which is why spoofing works — cancellations move λ just as much as trades.

### Conditions / Setup
- Estimate λ rolling over last N trades via Welford online regression (Hasbrouck signed-√V estimator)
- Compare λ during approach to flagged level vs off-level λ
- MS-05 fires when rolling λ at level-proximity is <= 0.5x off-level λ (absorption working)

### Entry / Exit Rules
- **MS-05 KyleLambdaCompression:** Fire when rolling λ at level-proximity is <= 0.5x off-level λ. Indicates liquidity is cheap — absorption working.
- Combine with MS-01 (AbsorptionZ) for high-conviction absorption confirmation.

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py` — Kyle λ estimation.

Welford online regression for OLS slope Δmid vs signed √V. O(1) per trade.

MS-05 KyleLambdaCompression: rolling λ at L-proximity <= 0.5x off-level λ.

### Academic Basis
- Kyle (1985), *Continuous Auctions and Insider Trading* (Econometrica 53(6)): λ as price-impact-per-order-flow. Foundation paper.
- Hasbrouck (2009), *Trading Costs and Returns for US Equities* (J. Finance): signed-√V regression estimator for λ. Standard implementation.
- Eisler, Bouchaud & Kockelkoren (2012): cancellation impact ≈ market-order impact. λ decomposition.
- Collin-Dufresne & Fos (2016), *Insider Trading & Stochastic Liquidity* (J. Finance): λ varies stochastically with informed flow.

---

## MICRO-12: Hawkes Processes (Self-Excitation Near Levels)

**Category**: Microstructure
**Tags**: Hawkes, self-excitation, branching ratio, breakout, level break, trade arrival
**DEEP6 Signal(s)**: MS-07 (HawkesBranchingCritical)
**Python File**: `C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py`

### Concept
Trade arrivals are self- and mutually exciting — each trade increases the probability of the next trade. This is modeled by Hawkes processes. Empirically, the branching ratio ||Φ|| approaches 1 (near critical / endogenously driven) — 70-85% of trades are triggered by prior trades, not exogenous news.

The branching ratio is the cleanest single indicator of "level about to break" vs "level holding":
- **Cross-excitation high + same-side excitation falling:** two-sided flow, level holds (absorption)
- **Same-side excitation high + branching ratio ≈ 1:** runaway self-excited flow, level breaks (breakout)

At price limits, the Hawkes kernel parameters shift — same-direction excitation strengthens, opposite-direction excitation weakens — which is a formal breakout-acceleration model.

### Conditions / Setup
- Fit a 2-dimensional Hawkes (buys, sells) on a rolling 1-hour window
- Monitor branching ratio and cross-excitation ratio as price approaches a level
- MS-07 fires when same-side branching ratio >= 0.85 AND price within 5 ticks of a flagged level (breakout imminent)
- Inverse rule: cross-excitation ratio > same-side = two-sided, level holds

### Entry / Exit Rules
- **MS-07 HawkesBranchingCritical:** Fire when 2-dim Hawkes same-side branching ratio >= 0.85 AND price within 5 ticks of flagged level: breakout imminent. Inverse: cross-excitation > same-side = level holds.
- **MS-12 ExhaustionPostBreak:** Fire when price crosses level, Hawkes same-side excitation decays by >= 50% within 2 minutes, and aggressor-dominance reverts to <= 55%. Classic failed breakout setup.

### Risk Management
- Hawkes branching ratio is a regime indicator. Combine with MS-01 (absorption) and MS-03 (queue imbalance) for full signal.

### DEEP6 Implementation
`C:\Users\Tea\DEEP6\deep6\engines\micro_prob.py` — Hawkes process fitting.

Hawkes MLE is the only CPU-heavy signal in DEEP6. Offloaded to `ThreadPoolExecutor`, results pushed via `janus` queue. Refit every 5-10 seconds.

MS-07 HawkesBranchingCritical: same-side branching ratio >= 0.85, price within 5 ticks of flagged level.
MS-12 ExhaustionPostBreak: same-side excitation decays >= 50% within 2 minutes post-break, aggressor-dominance <= 55%.

### Academic Basis
- Bacry, Mastromatteo & Muzy (2015), *Hawkes Processes in Finance* (arXiv:1502.04592): comprehensive survey. Branching ratio near 1 empirically.
- Bacry & Muzy (2014), *Hawkes model for price and trades* (arXiv:1301.1135): 4-kernel joint price/trade Hawkes; calibrated on Bund.
- Haghighi, Fallahpour & Eyvazlu (2016), *Order arrivals at price limits* (Finance Research Letters): Hawkes kernel shifts at price-limit events — formal breakout-acceleration model.
- Morariu-Patrichi & Pakkanen (2022), *Order Book Queue Hawkes Markovian Modeling* (SIAM J. Fin. Math.): state-dependent Hawkes with queue feedback.

---

## Compositional Rules (High-Confidence Setups)

These rules synthesize multiple MICRO signals into actionable setups. From `C:\Users\Tea\DEEP6\.planning\research\pine\deep\microstructure.md` (Cross-Domain Synthesis section).

**High-confidence absorption (level holds):**
`LEVEL ∧ QI_band_against_price (MS-03) ∧ Iceberg_HVr≥2 (MS-02) ∧ VPIN_falling (MS-04) ∧ Hawkes_cross_excite_high (MS-07) ∧ Absorption_z≥2.5 (MS-01) ∧ not_spoof (MS-08)`

**Level break (level fails):**
`LEVEL ∧ QI_band_with_price (MS-03) ∧ VPIN_rising (MS-04) ∧ Hawkes_branching→1 (MS-07) ∧ λ_rising (MS-05) ∧ Aggressor_dominance>0.75 (MS-09)`

**Round number modifier (MS-10):**
Boost weight of MS-01 through MS-07 by 1.25x when the flagged level is a round number (NQ: every 25, 50, 100 points). Empirically justified by Bloomfield-Chin-Craig (2024) $850M/yr wealth transfer finding.

---

*Last verified: 2026-05-12*
*Source files: `.planning/research/pine/deep/microstructure.md`, `.planning/research/pine/deep/practitioners.md`, `deep6/engines/absorption.py`, `deep6/engines/exhaustion.py`, `deep6/engines/auction.py`, `deep6/engines/iceberg.py`*
