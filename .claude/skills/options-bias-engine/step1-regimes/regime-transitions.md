# Regime Transitions: The Map and the Mechanics

## Why Transitions Are the Most Important Moments

A regime transition is not just a reclassification event. It's the moment when the structural forces governing price behavior change direction. The trade that was correct 5 minutes ago is now wrong. The level that was support is now resistance. The mechanical force that was buying is now selling.

Transitions are the most dangerous moments for open positions and the most profitable moments for traders who recognize them early. The early warning signals come from the four rivers before FlashAlpha confirms the new regime. The order book (Rithmic MBO) is typically the fastest signal. Flow (Massive) is second. Dark pool (Unusual Whales) is third. GEX structure (FlashAlpha) is last.

The META-RULE: When a transition is in progress, reduce size to 50% or go flat until the new regime is established. The transition itself is the most uncertain period. The exception is Setup 3 (Gamma Flip Cross), which trades the transition directly.

## The Complete Transition Map

```
REGIME A (Pos, Between)
    │
    ├──→ REGIME B (price rises to call wall)
    │       │
    │       ├──→ REGIME A (rejection, back between walls)
    │       └──→ REGIME D (wall lift in weakening gamma)
    │
    ├──→ REGIME C (price falls to put wall)
    │       │
    │       ├──→ REGIME A (bounce, back between walls)
    │       └──→ REGIME E (floor breaks, price below flip)
    │
    └──→ REGIME D (total_gex flips negative while above flip)
            │
            ├──→ REGIME A (GEX turns positive, recovery)
            └──→ REGIME E (price drops below flip)
                    │
                    ├──→ REGIME D (price reclaims flip)
                    └──→ REGIME A (full recovery, GEX turns positive)

REGIME F (Pin) ──→ any regime (pin releases at expiry or catalyst)
REGIME G (Pre-Event) ──→ any regime (event passes, reclassify)
```

## The Most Dangerous Transitions

### Transition 1: A/C → E (The Trapdoor)

**From:** Regime A (positive gamma, between walls) or Regime C (positive gamma, at put wall)
**To:** Regime E (negative gamma, below flip)

This is the most dangerous transition in the system. Everything that was "safe" becomes a trap. The mechanical buying force that was supporting price reverses to mechanical selling. Longs who were positioned for a put wall bounce get caught in a cascade.

**Why it's so dangerous:**
1. The transition is often preceded by a period of apparent stability (Regime A or C)
2. Longs are positioned at the put wall expecting a bounce
3. The floor breaks
4. The regime transitions from positive to negative gamma simultaneously
5. The mechanical force reverses from buying to selling
6. The longs' stops trigger, adding to the selling
7. The cascade accelerates

**Early warning signals (in order of speed):**

*Rithmic MBO (fastest):*
- Bids at the put wall being PULLED (not filled, cancelled)
- Offer stack appearing below the put wall
- Market sells hitting the bid without absorption
- DOM asymmetry reversing: offer depth > bid depth at the wall

*Massive (second):*
- Put sweeps ACCELERATING at and below the put wall
- Put OI increasing at strikes below the wall
- Call buying stopping completely

*Unusual Whales (third):*
- Dark pool SELLING at the put wall
- Dark pool prints appearing below the put wall

*FlashAlpha (last):*
- total_gex declining rapidly between polls
- Gamma flip rising toward spot
- Next poll shows total_gex negative

**Action on A/C → E transition:**
1. Exit all longs immediately. No averaging down.
2. Wait for the new regime to establish (15-30 minutes).
3. If total_gex is confirmed negative and spot is below the flip, classify as Regime E.
4. Apply Regime E playbook: short rallies, never buy dips.

**Speed of transition:** This transition can happen in 5-15 minutes. The put wall break is the trigger. Once the wall breaks, the cascade can accelerate rapidly. Do not wait for FlashAlpha confirmation. The Rithmic DOM signal is sufficient to exit longs.

### Transition 2: D → E (The Acceleration)

**From:** Regime D (negative gamma, above flip)
**To:** Regime E (negative gamma, below flip)

This is the second most dangerous transition. Everyone who bought the "recovery" in Regime D gets caught. The cascade is brutal because the pro-cyclical amplification is now working at maximum strength below the flip.

**Why it's so dangerous:**
1. Regime D longs bought the recovery above the flip
2. Their stops are clustered just below the flip (where they entered)
3. Price drops below the flip
4. Their stops trigger
5. The stop-triggered selling pushes price further below the flip
6. Dealer selling (pro-cyclical) amplifies the move
7. The cascade accelerates

**Early warning signals:**

*Rithmic MBO (fastest):*
- Bid depth thinning rapidly near the gamma flip
- Offer stack building below the flip
- Price approaching the flip on increasing volume (not a bounce, a push through)

*Massive (second):*
- Put sweeps appearing while price is still above the flip
- Call buying stopping
- Put OI increasing at strikes below the flip

*Unusual Whales (third):*
- Dark pool selling appearing
- Dark pool buying absent

*FlashAlpha (last):*
- total_gex becoming more negative
- Gamma flip stable or rising (not declining toward spot)

**Action on D → E transition:**
1. Exit all longs immediately.
2. If short, hold and widen trailing stop (now in Regime E, more room to run).
3. Wait 5-10 minutes for the new regime to establish.
4. Apply Regime E playbook.

**Speed of transition:** Very fast. The flip cross can happen in 1-3 minutes. The cascade below the flip accelerates immediately. Do not wait for confirmation. The flip cross is the signal.

### Transition 3: E → D (The Snapback)

**From:** Regime E (negative gamma, below flip)
**To:** Regime D (negative gamma, above flip)

This is the most profitable transition for longs who recognize it early. The short squeeze is violent and fast. Shorts who were positioned for the cascade get caught.

**Why it's so violent:**
1. Regime E shorts are positioned below the flip
2. Their stops are clustered just above the flip
3. Price rallies above the flip
4. Their stops trigger (short covering)
5. The short covering pushes price further above the flip
6. Dealer buying (pro-cyclical in negative gamma) amplifies the move
7. The squeeze accelerates

**Early warning signals:**

*Rithmic MBO (fastest):*
- Iceberg bids appearing at a specific level (institutional buying)
- Absorption of market sells (large sells hitting without price declining)
- Offer stack thinning above the flip
- Bid depth building above the flip

*Massive (second):*
- Put sweeps STOPPING (not just slowing, stopping)
- Call buying appearing and accelerating
- Put OI declining (shorts closing)
- Call OI increasing (new longs opening)

*Unusual Whales (third):*
- Dark pool BUYING appearing at or below the flip
- Large prints ($30M+) at a structural level

*FlashAlpha (last):*
- total_gex approaching zero from below
- Gamma flip declining (moving toward spot)

**Action on E → D transition:**
1. Exit all shorts immediately (or at minimum, tighten stops dramatically).
2. Wait for price to close above the flip by 25+ ticks on a 1-minute bar.
3. If all four rivers confirm, enter long (Setup 3: Gamma Flip Cross).
4. Apply Regime D playbook: momentum-follow with tight stops.

**The Setup 3 (Gamma Flip Cross) trade:**
This is the highest-conviction long in a negative gamma environment. Entry conditions:
- Price closes above the gamma flip by 25+ ticks
- Massive: Call buying accelerating, put buying stopping
- Unusual Whales: Dark pool buying at or above the flip
- Rithmic DOM: Bids building above the flip, offers thinning

Entry: Long NQ on the first pullback to the flip (old resistance becomes support).
Stop: 25 ticks below the flip.
Target: The call wall (in Regime D) or the next structural level.

**Speed of transition:** Fast. The flip cross can happen in 1-5 minutes. The squeeze above the flip accelerates quickly. The Setup 3 entry (pullback to the flip) typically occurs 5-15 minutes after the initial cross.

## All Transitions: Detailed Reference

### A → B (Price Rises to Call Wall)

**Trigger:** NQ_spot rises to within 0.3% of NQ_call_wall.
**Speed:** Gradual. Price drifts up over 30-60 minutes typically.
**Action:** Switch from Regime A playbook to Regime B playbook. Prepare for rejection or wall lift decision.
**Early warning:** Price approaching call wall on Rithmic. Call premium building on Massive.

### A → C (Price Falls to Put Wall)

**Trigger:** NQ_spot falls to within 0.3% of NQ_put_wall.
**Speed:** Gradual. Price drifts down over 30-60 minutes typically.
**Action:** Switch from Regime A playbook to Regime C playbook. Prepare for bounce or floor break decision.
**Early warning:** Price approaching put wall on Rithmic. Put premium building on Massive.

### A → D (GEX Flips Negative While Above Flip)

**Trigger:** total_gex crosses zero from positive to negative while NQ_spot remains above the gamma flip.
**Speed:** Can be sudden (large options trade) or gradual (OI restructuring over hours).
**Action:** Switch from Regime A playbook to Regime D playbook. Walls are now weaker. Momentum-follow instead of mean-reversion.
**Early warning:** total_gex declining rapidly on FlashAlpha. Put buying accelerating on Massive.

### B → A (Rejection from Call Wall)

**Trigger:** Price tests the call wall and is rejected back below the 0.3% zone.
**Speed:** Fast. Rejection typically happens in 5-15 minutes.
**Action:** Switch from Regime B playbook to Regime A playbook. Short from call wall, target HVL.
**Early warning:** Iceberg offers at call wall on Rithmic. Call premium declining on Massive.

### B → D (Call Wall Break in Weakening Gamma)

**Trigger:** Price breaks above the call wall AND total_gex is declining (or has turned negative).
**Speed:** Fast. The break happens in 1-5 minutes.
**Action:** This is unusual. The call wall has broken but the gamma regime is weakening. The break may not be sustained. Apply Regime D playbook (momentum-follow with tight stops) rather than the Regime B wall lift playbook.
**Early warning:** total_gex declining on FlashAlpha. Call sweeps above wall on Massive. But dark pool absent (no institutional conviction).

### C → A (Bounce from Put Wall)

**Trigger:** Price tests the put wall and bounces back above the 0.3% zone.
**Speed:** Fast. Bounce typically happens in 5-15 minutes.
**Action:** Switch from Regime C playbook to Regime A playbook. Long from put wall, target HVL.
**Early warning:** Iceberg bids at put wall on Rithmic. Put premium declining on Massive. Dark pool buying on Unusual Whales.

### C → E (Put Wall Breaks, Price Below Flip)

**Trigger:** Price breaks below the put wall AND total_gex turns negative (or was already negative).
**Speed:** Fast to very fast. The break can happen in 1-5 minutes. The cascade below accelerates.
**Action:** Exit all longs immediately. Wait for Regime E classification. Apply Regime E playbook.
**Early warning:** Bids pulled at put wall on Rithmic. Put sweeps accelerating on Massive. Dark pool selling on Unusual Whales.
**This is the A/C → E transition described above.**

### D → A (GEX Turns Positive While Above Flip)

**Trigger:** total_gex crosses zero from negative to positive while NQ_spot remains above the gamma flip.
**Speed:** Gradual. OI restructuring takes hours typically.
**Action:** Switch from Regime D playbook to Regime A playbook. Mean-reversion replaces momentum-follow. Walls become reliable again.
**Early warning:** total_gex approaching zero on FlashAlpha. Call buying building on Massive. Dark pool buying on Unusual Whales.

### D → E (Price Drops Below Flip)

**Trigger:** NQ_spot drops below NQ_gamma_flip by 25+ ticks.
**Speed:** Very fast. The flip cross can happen in 1-3 minutes.
**Action:** Exit all longs immediately. Apply Regime E playbook.
**Early warning:** Bid depth thinning near flip on Rithmic. Put sweeps appearing on Massive.
**This is the D → E transition described above.**

### E → D (Price Reclaims Flip)

**Trigger:** NQ_spot rises above NQ_gamma_flip by 25+ ticks.
**Speed:** Fast. The flip cross can happen in 1-5 minutes.
**Action:** Exit all shorts (or tighten stops). Consider Setup 3 (Gamma Flip Cross) long.
**Early warning:** Iceberg bids appearing on Rithmic. Put sweeps stopping on Massive. Dark pool buying on Unusual Whales.
**This is the E → D transition described above.**

### E → A (Full Recovery)

**Trigger:** Price reclaims the gamma flip AND total_gex turns positive.
**Speed:** Gradual. The GEX turning positive takes hours of OI restructuring.
**Action:** Switch from Regime E playbook to Regime A playbook. Mean-reversion replaces momentum-follow. Walls become reliable again.
**Early warning:** total_gex approaching zero on FlashAlpha. Call buying dominant on Massive. Dark pool buying on Unusual Whales.

### F → Any (Pin Releases)

**Trigger:** 0DTE options expire (4:00 PM ET) or a macro catalyst overwhelms the pin.
**Speed:** Instantaneous at expiry. Fast (1-5 minutes) for catalyst-driven breaks.
**Action:** Run full classification from `regime-identification.md`. The underlying gamma regime (A, B, C, D, or E) was present before the pin. It may still be present after.
**Early warning for catalyst break:** Price moves > 1.5x pin range in a single 1-minute bar.

### G → Any (Event Passes)

**Trigger:** The macro event occurs and 15-30 minutes have passed.
**Speed:** The event itself is instantaneous. The post-event stabilization takes 15-30 minutes.
**Action:** Run full classification from `regime-identification.md` using fresh FlashAlpha data.
**Post-event protocol:** See `regime-g-pre-event.md` for the full post-event checklist.

## How Fast Transitions Happen

**Spot-based transitions (flip cross, wall cross):** 1-5 minutes. These happen when price moves through a level. They're the fastest transitions.

**GEX-based transitions (total_gex sign change):** 15 minutes to several hours. The GEX changes as OI restructures. A single large options trade can change the sign in 15 minutes. Gradual OI restructuring takes hours.

**Wall shifts:** 15-60 minutes. Walls shift as OI at key strikes changes. A large call sweep at a new strike can shift the call wall in 15 minutes. Gradual OI changes take longer.

**Pin regime start/end:** Predictable. Starts when the 0DTE conditions are met (typically 2:00 PM ET on expiry days). Ends at 4:00 PM ET or on a catalyst.

**Pre-event regime:** Predictable. Starts 60 minutes before the event. Ends when the event occurs.

## Order Book Behavior During Transitions

The order book (Rithmic MBO) gives the earliest signal of regime change. Before FlashAlpha updates, before Massive shows the flow shift, the DOM shows what's happening.

**During A/C → E transition:**
- Bids at the put wall being cancelled (not filled, cancelled)
- Offer stack appearing below the put wall
- DOM asymmetry reversing rapidly
- Price gapping through the wall on a single large market sell

**During D → E transition:**
- Bid depth thinning near the gamma flip
- Offer stack building below the flip
- Price approaching the flip on increasing volume
- DOM asymmetry: offer depth >> bid depth near the flip

**During E → D transition:**
- Iceberg bids appearing at a specific level
- Absorption of market sells (large sells without price declining)
- Offer stack thinning above the flip
- Bid depth building above the flip

**During B → A (rejection):**
- Iceberg offers at the call wall
- Absorption of buy orders (large buys without price advancing)
- Bid depth thinning above the wall
- DOM asymmetry: offer depth >> bid depth at the wall

**During C → A (bounce):**
- Iceberg bids at the put wall
- Absorption of sell orders (large sells without price declining)
- Offer depth thinning below the wall
- DOM asymmetry: bid depth >> offer depth at the wall

## The Transition Trading Protocol

### Step 1: Detect the Transition Signal

The first signal comes from Rithmic MBO. Watch for:
- Bids being pulled (not filled, pulled) at a key level
- Offers being pulled at a key level
- DOM asymmetry reversing rapidly
- Absorption pattern changing (absorption stops = level breaking)

### Step 2: Confirm with Massive

Within 1-3 minutes of the Rithmic signal, check Massive for flow confirmation:
- Is the flow direction consistent with the transition?
- Are sweeps appearing in the transition direction?
- Is OI changing in the transition direction?

### Step 3: Reduce Size or Go Flat

Before the transition is confirmed, reduce position size to 50% or go flat. The transition is the most uncertain period. The risk of being wrong is highest here.

### Step 4: Wait for Confirmation

Wait for price to close through the key level (flip, wall) by 25+ ticks on a 1-minute bar. This is the confirmation.

### Step 5: Reclassify

Run the full classification from `regime-identification.md`. Apply the new regime's playbook.

### Step 6: Re-enter (if applicable)

If the new regime offers a clear setup, enter with full size. The transition is complete. The new regime's mechanical forces are now in effect.

## The META-RULE in Practice

**When a transition is in progress:**
- Reduce size to 50%
- Widen stops by 50%
- Do not add to existing positions
- Do not enter new positions in the old regime's direction

**When the transition is confirmed:**
- Apply the new regime's playbook
- Enter with full size
- Use the new regime's stop distances

**Exception: Setup 3 (Gamma Flip Cross)**
The E → D transition is the one transition that is traded directly. The flip cross is the entry signal. The pullback to the flip is the entry point. This is the highest-conviction long in a negative gamma environment. Full size is appropriate with the Setup 3 entry rules.

## Transition Frequency by Regime Pair

Based on historical NQ/QQQ options structure:

| Transition | Approximate Frequency | Notes |
|------------|----------------------|-------|
| A → B | 2-3x per week | Price tests call wall regularly |
| A → C | 2-3x per week | Price tests put wall regularly |
| B → A | 65% of B occurrences | Most common B outcome |
| B → D | 35% of B occurrences | Wall lift |
| C → A | 75% of C occurrences | Most common C outcome |
| C → E | 25% of C occurrences | Floor break |
| A → D | 1-2x per month | GEX flip while above flip |
| D → A | 50% of D occurrences | Recovery |
| D → E | 50% of D occurrences | Acceleration |
| E → D | 60% of E occurrences | Snapback |
| E → A | 40% of E occurrences | Full recovery |

These are rough estimates. The distribution shifts with market conditions. In high-vol environments, D and E transitions are more frequent. In low-vol environments, A is more stable.

## Cross-References

- Classification: `regime-identification.md`
- Regime A: `regime-a-positive-between.md`
- Regime B: `regime-b-positive-at-call.md`
- Regime C: `regime-c-positive-at-put.md`
- Regime D: `regime-d-negative-above-flip.md`
- Regime E: `regime-e-negative-below-flip.md`
- Regime F: `regime-f-pin.md`
- Regime G: `regime-g-pre-event.md`
