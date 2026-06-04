# Regime Identification: The Classification Engine

## Purpose

This document is the master decision tree for classifying the current market regime from the four data rivers. Every session begins here. Every trade setup is downstream of this classification. Getting the regime wrong means applying the wrong playbook, which means trading against the structural forces that actually control price.

The seven regimes are not arbitrary categories. They describe fundamentally different dealer hedging dynamics, which produce fundamentally different price behavior. A level that is support in Regime A is a trapdoor in Regime E. A breakout attempt that fails in Regime B succeeds in Regime D. The regime is the context that makes everything else interpretable.

## The Four Data Rivers

Before running the classification, you need current readings from all four sources. Stale data produces wrong classifications.

**River 1: FlashAlpha (GEX/DEX/VEX/CHEX)**
- Poll frequency: Every 15 minutes during RTH, every 30 minutes pre-market
- Critical fields: `total_gex` (sign and magnitude), `gamma_flip` (price level in QQQ terms), `call_wall` (highest positive GEX strike), `put_wall` (highest negative GEX strike), `hvl` (high-volume level / zero-gamma level), `dex` (delta exposure), `vex` (vanna exposure), `chex` (charm exposure)
- Unit conversion: All FlashAlpha levels are in QQQ price. Convert to NQ using the current QQQ-to-NQ ratio. The ratio is approximately 85.7x but drifts. Compute it fresh each session: `NQ_spot / QQQ_spot`. Apply this ratio to all FlashAlpha levels before using them.
- Example: If FlashAlpha shows `gamma_flip = 480.00` and today's ratio is 85.7, then `NQ_gamma_flip = 480.00 * 85.7 = 41,136`.

**River 2: Massive.com (Options Flow)**
- Poll frequency: Continuous during RTH. Snapshot every 5 minutes for regime classification.
- Critical fields: Net premium direction (call vs put), sweep vs limit ratio, OI changes at key strikes, 0DTE vs multi-day flow split, unusual activity flags
- What you're reading: Is institutional money buying calls or puts? Is it aggressive (sweeps) or passive (limits)? Is new OI being created (new positions) or is OI declining (closing)?

**River 3: Unusual Whales (Dark Pool)**
- Poll frequency: Every 10-15 minutes. Dark pool prints are delayed 15-30 minutes by regulation.
- Critical fields: Dark pool print size, price level of prints, direction (buy-side vs sell-side), sector context (QQQ-correlated names)
- What you're reading: Where are institutions transacting off-exchange? Dark pool buying at a level = institutional support. Dark pool selling = institutional distribution. Absence of dark pool = no institutional conviction.

**River 4: Rithmic MBO (NQ Order Book)**
- Poll frequency: Continuous. This is the real-time river.
- Critical fields: Bid/ask depth at key levels, iceberg detection (large hidden orders), absorption events (large market orders absorbed without price movement), DOM asymmetry (bid depth vs ask depth ratio), sweep detection
- What you're reading: What is the order book doing at the levels FlashAlpha identified? The book confirms or denies what the options data predicts.

## Unit Conversion Reference

The QQQ-to-NQ ratio is the most important conversion in this system. Every FlashAlpha level must be converted before use.

```
ratio = NQ_spot / QQQ_spot

NQ_gamma_flip  = FlashAlpha.gamma_flip  * ratio
NQ_call_wall   = FlashAlpha.call_wall   * ratio
NQ_put_wall    = FlashAlpha.put_wall    * ratio
NQ_hvl         = FlashAlpha.hvl         * ratio
```

Typical ratio range: 84x to 87x. Recompute at session open and after any large NQ move (>1%). The ratio shifts when QQQ and NQ diverge intraday due to different constituent weighting and futures premium.

**Example session (NQ at 21,500, QQQ at 251.00):**
- Ratio = 21,500 / 251.00 = 85.66x
- FlashAlpha gamma_flip = 248.50 → NQ equivalent = 248.50 * 85.66 = 21,287
- FlashAlpha call_wall = 255.00 → NQ equivalent = 255.00 * 85.66 = 21,843
- FlashAlpha put_wall = 245.00 → NQ equivalent = 245.00 * 85.66 = 20,987

## Priority Rules (Read Before the Flowchart)

These rules override the flowchart when they apply. Check them first.

**Priority 1: Pre-Event Override (Regime G)**
If a macro event is within 60 minutes, classify as Regime G regardless of GEX structure. Events: FOMC announcement, CPI, NFP, PCE, PPI, ISM Manufacturing, mega-cap earnings (AAPL, MSFT, NVDA, GOOG, AMZN, META). The GEX structure is valid but the event uncertainty makes it untradeable. See `regime-g-pre-event.md`.

**Priority 2: Pin Override (Regime F)**
If it is 0DTE (same-day expiry, typically Friday for SPX/QQQ weekly options, but also Monday and Wednesday for SPX 3x weekly), AND the last 2 hours of trading, AND OI at a single strike exceeds 2x the average OI across the nearest 5 strikes on each side, AND spot is within 0.2% of that strike, classify as Regime F. The pin mechanics override gamma regime mechanics near expiry. See `regime-f-pin.md`.

**Priority 3: Gamma Regime (Default)**
If neither Priority 1 nor Priority 2 applies, run the full flowchart below to determine Regime A, B, C, D, or E.

## The Classification Flowchart

```
START: Collect all four rivers. Convert FlashAlpha to NQ terms.
       Compute ratio = NQ_spot / QQQ_spot.
       
       ┌─────────────────────────────────────────────────────┐
       │  PRIORITY CHECK 1: Is a macro event within 60 min?  │
       └─────────────────────────────────────────────────────┘
                              │
              YES ────────────┴──────────── NO
               │                            │
               ▼                            ▼
         REGIME G                  ┌─────────────────────────────────────────┐
         (Pre-Event)               │  PRIORITY CHECK 2: Is it 0DTE last 2hr? │
         See regime-g.md           │  AND OI at single strike > 2x average?  │
                                   │  AND spot within 0.2% of that strike?   │
                                   └─────────────────────────────────────────┘
                                                      │
                                     YES ─────────────┴──────── NO
                                      │                          │
                                      ▼                          ▼
                                REGIME F              ┌──────────────────────┐
                                (Pin)                 │  STEP 1: Read        │
                                See regime-f.md       │  FlashAlpha          │
                                                      │  total_gex sign      │
                                                      └──────────────────────┘
                                                                 │
                                              POSITIVE ──────────┴──────── NEGATIVE
                                                 │                              │
                                                 ▼                              ▼
                                    ┌────────────────────┐        ┌─────────────────────┐
                                    │  STEP 2: Where is  │        │  STEP 2: Where is   │
                                    │  spot relative to  │        │  spot relative to   │
                                    │  NQ_gamma_flip?    │        │  NQ_gamma_flip?     │
                                    └────────────────────┘        └─────────────────────┘
                                              │                              │
                              ABOVE ──────────┴──── BELOW      ABOVE ───────┴──── BELOW
                                │                    │            │                  │
                                ▼                    ▼            ▼                  ▼
                       ┌──────────────┐    ┌──────────────┐  REGIME D          REGIME E
                       │  STEP 3:     │    │  Unusual:    │  (Neg Gamma,       (Neg Gamma,
                       │  Where is    │    │  Positive    │  Above Flip)       Below Flip)
                       │  spot vs     │    │  GEX but     │  See regime-d.md   See regime-e.md
                       │  walls?      │    │  below flip. │
                       └──────────────┘    │  Verify GEX  │
                              │            │  reading.    │
                              │            └──────────────┘
              ┌───────────────┼───────────────┐
              │               │               │
         AT CALL          BETWEEN         AT PUT
         WALL             WALLS           WALL
         (within          (>0.3%          (within
         0.3%)            from both)      0.3%)
              │               │               │
              ▼               ▼               ▼
         REGIME B         REGIME A        REGIME C
         (Pos Gamma,      (Pos Gamma,     (Pos Gamma,
         At Call Wall)    Between)        At Put Wall)
         See regime-b.md  See regime-a.md See regime-c.md
```

## Step-by-Step Classification Protocol

### Step 1: Read Total GEX Sign

Open FlashAlpha. Read `total_gex`. This is the aggregate gamma exposure across all strikes and expirations for QQQ and NDX options.

- `total_gex > 0`: Positive gamma regime. Dealers are net long gamma. They hedge counter-cyclically (sell rallies, buy dips). Price is dampened.
- `total_gex < 0`: Negative gamma regime. Dealers are net short gamma. They hedge pro-cyclically (buy rallies, sell dips). Price is amplified.
- `total_gex` near zero (within ±$200M notional): Transitional. The regime is unstable. Treat as negative gamma for risk purposes until a clear sign establishes.

**Magnitude matters.** A `total_gex` of +$5B is a strong positive gamma environment. A `total_gex` of +$200M is barely positive and can flip intraday. Track the magnitude, not just the sign.

Typical NQ session ranges:
- Strong positive: total_gex > +$2B
- Moderate positive: +$500M to +$2B
- Weak positive: +$50M to +$500M (treat with caution)
- Near zero: -$200M to +$200M (unstable, use negative gamma rules)
- Weak negative: -$50M to -$500M
- Moderate negative: -$500M to -$2B
- Strong negative: total_gex < -$2B

### Step 2: Locate Spot Relative to Gamma Flip

The gamma flip is the price level where total dealer gamma exposure crosses zero. Above the flip, dealers are net long gamma (positive). Below the flip, dealers are net short gamma (negative). This is the most important single level in the system.

Convert FlashAlpha's `gamma_flip` to NQ terms using the session ratio.

- `NQ_spot > NQ_gamma_flip + 25 ticks`: Comfortably above flip. Proceed to Step 3 (positive gamma) or classify Regime D (negative gamma).
- `NQ_spot < NQ_gamma_flip - 25 ticks`: Comfortably below flip. Proceed to Step 3 (positive gamma, unusual) or classify Regime E (negative gamma).
- `NQ_spot` within 25 ticks of `NQ_gamma_flip`: At the flip. This is a transition zone. The regime is unstable. Treat as negative gamma for risk purposes. Watch for the cross.

25 ticks = 6.25 NQ points (each tick = 0.25 NQ points). This buffer prevents false regime assignments from noise.

### Step 3: Locate Spot Relative to Walls (Positive Gamma Only)

If total_gex is positive and spot is above the gamma flip, determine where spot sits relative to the call wall and put wall.

Convert `call_wall` and `put_wall` to NQ terms.

**At Call Wall:** `NQ_spot >= NQ_call_wall - (NQ_call_wall * 0.003)` AND `NQ_spot <= NQ_call_wall + (NQ_call_wall * 0.003)`
- 0.3% of NQ at 21,500 = 64.5 NQ points = approximately 258 ticks
- This is a wide band. The call wall is not a single tick; it's a zone.

**At Put Wall:** `NQ_spot >= NQ_put_wall - (NQ_put_wall * 0.003)` AND `NQ_spot <= NQ_put_wall + (NQ_put_wall * 0.003)`

**Between Walls:** Spot is more than 0.3% away from both walls.

**Above Call Wall:** Spot has broken above the call wall. This is unusual in positive gamma. Verify the GEX reading. If confirmed, the call wall may be lifting (new OI above it). Check Massive for call buying at higher strikes.

**Below Put Wall:** Spot has broken below the put wall in positive gamma. This is a regime transition signal. Verify immediately. If confirmed, check if total_gex is still positive. If GEX is turning negative, you're watching a live transition from Regime C to Regime E.

## Numeric Thresholds Summary

| Parameter | Threshold | Source | Notes |
|-----------|-----------|--------|-------|
| total_gex positive | > 0 | FlashAlpha | Strong if > $2B |
| total_gex negative | < 0 | FlashAlpha | Strong if < -$2B |
| total_gex near zero | -$200M to +$200M | FlashAlpha | Treat as negative |
| At call wall | Within 0.3% of NQ_call_wall | FlashAlpha + ratio | ~64 NQ pts at 21,500 |
| At put wall | Within 0.3% of NQ_put_wall | FlashAlpha + ratio | ~64 NQ pts at 21,500 |
| At gamma flip | Within 25 ticks (6.25 pts) | FlashAlpha + ratio | Transition zone |
| Pin OI concentration | Single strike > 2x avg nearby | Massive / FlashAlpha | 0DTE only |
| Pin proximity | Within 0.2% of pin strike | Rithmic spot | ~43 NQ pts at 21,500 |
| Pre-event window | Within 60 minutes | Event calendar | Hard override |

## Regime Frequency Distribution (Historical Baseline)

Based on NQ/QQQ options structure across 2022-2024:

| Regime | Approximate Frequency | Notes |
|--------|----------------------|-------|
| A (Pos, Between) | ~40% of RTH sessions | Most common |
| B (Pos, At Call) | ~10% of RTH sessions | Often brief |
| C (Pos, At Put) | ~10% of RTH sessions | Often brief |
| D (Neg, Above Flip) | ~8% of RTH sessions | Deceptive |
| E (Neg, Below Flip) | ~15% of RTH sessions | Trending bear |
| F (Pin) | ~7% of RTH sessions | 0DTE afternoons |
| G (Pre-Event) | ~10% of RTH sessions | Macro calendar |

These are rough estimates. The distribution shifts with market conditions. In high-vol environments (VIX > 25), Regimes D and E become more frequent. In low-vol environments (VIX < 15), Regime A dominates.

## Regime Stability Assessment

After classifying the regime, assess its stability. An unstable regime is more likely to transition within the session.

**Stability indicators (all from FlashAlpha):**
- `total_gex` magnitude: Higher magnitude = more stable. A $5B positive GEX environment won't flip to negative in one session. A $300M positive GEX can flip on a single large options trade.
- Distance from gamma flip: Spot 200+ NQ points from flip = stable. Spot within 50 NQ points of flip = unstable, watch for transition.
- Wall distance: Spot near a wall = potential transition incoming. Spot mid-range = stable.
- OI structure: Concentrated OI at few strikes = more stable walls. Distributed OI = walls can shift quickly.

**Stability rating:**
- HIGH: total_gex > $2B, spot > 100 NQ pts from flip, spot > 100 NQ pts from nearest wall
- MEDIUM: total_gex $500M-$2B, spot 50-100 NQ pts from flip or wall
- LOW: total_gex < $500M, spot < 50 NQ pts from flip or wall
- CRITICAL: total_gex near zero, spot within 25 NQ pts of flip

At LOW or CRITICAL stability, reduce position size by 50%. At CRITICAL, consider no directional positions until regime clarifies.

## Regime Reclassification Schedule

Regimes are not static. Reclassify at these intervals:

- **Every 15 minutes during RTH**: Full reclassification using fresh FlashAlpha poll
- **On any NQ move > 50 points**: Immediate reclassification. A 50-point move can cross a wall or the flip.
- **On any large options sweep**: Massive alert for sweep > $5M premium. Reclassify after seeing it.
- **On any dark pool print > $50M notional**: Unusual Whales alert. Reclassify.
- **At 2:00 PM ET**: Charm flows begin. Regime can shift as delta decays. Reclassify.
- **At 3:00 PM ET**: Final hour. Pin effects strengthen if 0DTE. Reclassify.

## Cross-References

- Regime A playbook: `regime-a-positive-between.md`
- Regime B playbook: `regime-b-positive-at-call.md`
- Regime C playbook: `regime-c-positive-at-put.md`
- Regime D playbook: `regime-d-negative-above-flip.md`
- Regime E playbook: `regime-e-negative-below-flip.md`
- Regime F playbook: `regime-f-pin.md`
- Regime G playbook: `regime-g-pre-event.md`
- Transition mechanics: `regime-transitions.md`

## Common Classification Errors

**Error 1: Using QQQ levels directly as NQ levels.**
Always convert. A QQQ call wall at 480 is not an NQ level of 480. It's 480 * ratio = ~41,136.

**Error 2: Ignoring total_gex magnitude.**
A barely-positive GEX is not the same as a strongly-positive GEX. The dampening effect is proportional to magnitude. Treat weak positive GEX with negative gamma caution.

**Error 3: Missing the pre-event override.**
Traders get excited about a perfect Regime A setup and forget there's a CPI print in 45 minutes. Check the event calendar before every session and before every trade.

**Error 4: Classifying regime from a single river.**
The regime classification uses FlashAlpha as the primary source, but the other three rivers validate it. If FlashAlpha says positive gamma but Massive shows massive put sweeps and dark pool is selling, something is wrong. Either the GEX data is stale or a transition is in progress. Don't trade until the rivers align.

**Error 5: Not updating the QQQ-to-NQ ratio.**
The ratio drifts. A ratio computed at session open may be 0.5-1% off by afternoon. Recompute after any large NQ move.
