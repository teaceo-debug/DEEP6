# Regime F: Pin Regime

## Classification Conditions

All four conditions must be met simultaneously:

1. **0DTE expiry:** It is the same-day expiry for the relevant options. For QQQ/SPX: Monday, Wednesday, and Friday (SPX 3x weekly). For NDX: typically Friday. Check the options calendar.
2. **Last 2 hours of trading:** After 2:00 PM ET. Pin effects strengthen as expiry approaches. Before 2:00 PM, gamma pinning is weaker and less reliable.
3. **OI concentration:** A single strike has open interest exceeding 2x the average OI across the nearest 5 strikes on each side. This identifies the pin strike.
4. **Proximity:** NQ_spot is within 0.2% of the pin strike (approximately 43 NQ points at 21,500).

If all four conditions are met, classify as Regime F regardless of the underlying gamma regime (A, B, C, D, or E). The pin mechanics override the gamma regime mechanics near expiry.

## The Physics of Gamma Pinning

Near expiry, the gamma of at-the-money options approaches infinity. This is not a metaphor. The mathematical limit of gamma as time-to-expiry approaches zero for an at-the-money option is infinity. In practice, it becomes extremely large in the final hours.

**What this means for dealer hedging:**

When a dealer is short a 0DTE call at strike K, and price is at K, the gamma of that call is enormous. A 1-point move in price causes a massive change in delta. To remain delta-neutral, the dealer must trade a large quantity of NQ futures for every small price move.

**The pinning mechanism:**

1. Price moves 5 NQ points above the pin strike K
2. Dealer's short call delta increases dramatically (high gamma)
3. Dealer sells NQ futures to rehedge (large quantity)
4. This selling pushes price back toward K
5. Price moves 5 NQ points below K
6. Dealer's short put delta increases dramatically
7. Dealer buys NQ futures to rehedge (large quantity)
8. This buying pushes price back toward K

The result is a gravitational pull toward the pin strike. Every move away from K triggers dealer hedging that pulls price back. The closer to expiry, the stronger the pull. In the final 30 minutes, the pin can be so strong that price oscillates within a 5-10 NQ point range around the pin strike.

## Identifying the Pin Strike

The pin strike is the strike with the highest combined (call + put) open interest for the 0DTE expiry.

**From FlashAlpha:**
- Look at the 0DTE OI profile. The pin strike is the highest bar in the OI histogram.
- FlashAlpha will often label this as the "max pain" level, which is closely related to the pin strike.
- The pin strike is almost always a round number: QQQ 520, 525, 530, etc. Round numbers attract OI because retail traders prefer them.

**From Massive.com:**
- Look at the 0DTE OI by strike. The pin strike has the highest combined OI.
- Verify that the OI at the pin strike is > 2x the average of the surrounding 5 strikes on each side.

**Converting to NQ:**
- Pin strike (QQQ) * ratio = NQ pin level
- Example: QQQ pin at 251.00, ratio 85.66 → NQ pin = 21,502

**The 2x threshold:**
- Average OI at strikes 245, 246, 247, 249, 250 (5 strikes below) = 15,000 contracts
- Average OI at strikes 252, 253, 254, 255, 256 (5 strikes above) = 12,000 contracts
- Average of both sides = 13,500 contracts
- Pin strike OI at 251 = 35,000 contracts
- 35,000 / 13,500 = 2.59x → Qualifies as pin (> 2x threshold)

## Expected Pin Range

The pin range is the zone within which price is expected to oscillate during the pin regime. It's derived from the 0DTE straddle price.

**Formula:**
```
pin_range = ATM_0DTE_straddle_price * 0.3
NQ_pin_range = pin_range * ratio
```

**Example:**
- QQQ ATM 0DTE straddle price = $1.20 (call + put at the pin strike)
- pin_range = $1.20 * 0.3 = $0.36 in QQQ terms
- NQ_pin_range = $0.36 * 85.66 = 30.8 NQ points
- Pin zone: NQ_pin ± 30.8 points

In low volatility (VIX < 15), the straddle is smaller and the pin range is tighter (15-25 NQ points). In high volatility (VIX > 25), the straddle is larger and the pin range is wider (40-60 NQ points).

**The pin range is the trading range for Regime F.** Price is expected to stay within this range for the duration of the pin regime. Moves outside the range are fades.

## Trade Style: Fade Moves Away from Pin

The only trade in Regime F is fading moves away from the pin strike. There is no directional trade. There is no momentum trade. There is no breakout trade.

### Setup: Fade Upper Range

**Entry conditions:**
- Price has moved to the upper boundary of the pin range (NQ_pin + NQ_pin_range)
- FlashAlpha: High 0DTE OI at pin strike confirmed
- Rithmic DOM: Offers reloading at upper boundary (dealer selling to rehedge)
- Massive: 0DTE call volume declining at upper boundary (gamma squeeze exhausting)

**Entry:** Short NQ at the upper boundary of the pin range. Limit order.

**Stop:** 15 ticks above the upper boundary. If price closes above the upper boundary by 15 ticks, the pin is breaking. Exit.

**Target:** The pin strike itself. Take full profit at the pin strike.

**Expected win rate:** 70-75% in strong pin conditions (OI > 3x average, VIX < 20).

### Setup: Fade Lower Range

**Entry conditions:**
- Price has moved to the lower boundary of the pin range (NQ_pin - NQ_pin_range)
- FlashAlpha: High 0DTE OI at pin strike confirmed
- Rithmic DOM: Bids reloading at lower boundary (dealer buying to rehedge)
- Massive: 0DTE put volume declining at lower boundary (gamma squeeze exhausting)

**Entry:** Long NQ at the lower boundary of the pin range. Limit order.

**Stop:** 15 ticks below the lower boundary. If price closes below the lower boundary by 15 ticks, the pin is breaking. Exit.

**Target:** The pin strike itself. Take full profit at the pin strike.

**Expected win rate:** 70-75% in strong pin conditions.

## What Doesn't Work in Regime F

**Directional trading:** The pin overrides directional signals. A bullish flow reading from Massive is irrelevant if the pin is strong. The gamma pinning will pull price back to the pin strike regardless of flow direction.

**Momentum signals:** RSI, MACD, moving averages, all momentum indicators are suppressed in Regime F. Price oscillates around the pin strike. Momentum signals generate false signals constantly.

**Flow signals:** Options flow in Regime F is dominated by 0DTE hedging activity, not directional positioning. A large call sweep at the pin strike might be a dealer hedging, not a bullish bet. Flow signals are unreliable.

**Dark pool signals:** Institutions generally don't fight the pin. Dark pool activity is typically absent or minimal during Regime F. The absence of dark pool is not a signal; it's the expected state.

**Wall levels:** The call wall and put wall from the gamma regime are less relevant during Regime F. The pin strike is the dominant level. The walls may still exist, but the pin mechanics override them within the pin range.

## Four-River Reading in Regime F

### River 1: FlashAlpha (GEX Structure)

**Primary use:** Identify the pin strike and confirm the OI concentration. The 0DTE GEX profile will show a massive spike at the pin strike. This is the visual confirmation of the pin.

**Secondary use:** Track whether the pin is strengthening or weakening. If OI at the pin strike is declining (options being closed or exercised early), the pin is weakening. If OI is stable or increasing, the pin is strong.

**What to ignore:** The overall gamma regime (positive or negative) is less relevant during Regime F. The pin mechanics dominate.

### River 2: Massive.com (Options Flow)

**Primary use:** Monitor 0DTE volume at the pin strike. High volume at the pin strike = active hedging = strong pin. Declining volume = pin weakening.

**Secondary use:** Watch for large sweeps AWAY from the pin strike. A large call sweep at a strike significantly above the pin could signal that someone is trying to force a pin break. This is rare but it happens.

**What to ignore:** Multi-day flow is irrelevant during Regime F. Focus exclusively on 0DTE activity.

### River 3: Unusual Whales (Dark Pool)

**Primary use:** Confirm that institutions are not fighting the pin. If dark pool is absent, the pin is clean. If dark pool buying appears significantly above the pin, someone may be positioning for a pin break.

**What to ignore:** Most dark pool signals are irrelevant during Regime F. The pin is a mechanical phenomenon, not an institutional positioning phenomenon.

### River 4: Rithmic MBO (NQ Order Book)

**Primary use:** This is the most useful river in Regime F. The order book shows the pin mechanics in real-time.

**Pin confirmation signals:**
- Bids and offers oscillating rapidly around the pin strike. The book is active but balanced.
- Large orders appearing and disappearing at the pin strike boundaries. Dealers hedging.
- Price bouncing between the pin range boundaries on thin volume.
- Iceberg orders at both the upper and lower boundaries of the pin range.

**Pin break signals:**
- Offers being pulled above the upper boundary (sellers withdrawing, path clearing)
- Bids being pulled below the lower boundary (buyers withdrawing, path clearing)
- Large directional sweep hitting the book and price moving through the boundary
- Volume spike at the boundary without price returning to the pin strike

## When to Exit the Pin Regime

The pin regime ends in two ways:

**Way 1: Scheduled end (options expiry)**
0DTE options expire at 4:00 PM ET (for QQQ/SPX). In the final 15-30 minutes, gamma approaches infinity and then drops to zero as options expire. The pin effect is strongest in the 30-60 minutes before expiry, then disappears at expiry.

**Practical rule:** Do not hold Regime F positions through the final 15 minutes. The pin can break violently as options expire and dealers unwind their hedges. Exit all Regime F positions by 3:45 PM ET.

**Way 2: External catalyst breaks the pin**
A macro event (news, Fed speaker, geopolitical event) can overwhelm the pin mechanics. If a headline causes a 50+ NQ point move in 2 minutes, the pin is broken. The gamma pinning cannot overcome a genuine macro catalyst.

**Practical rule:** If price moves more than 1.5x the pin range in a single 1-minute bar, the pin is broken. Exit all Regime F positions immediately. Reclassify the regime.

## Pin Width Calibration

The pin range formula (straddle * 0.3) is a starting point. Adjust based on conditions:

**Narrow the range (use 0.2 multiplier) when:**
- VIX < 13 (very low volatility)
- OI at pin strike > 4x average (very strong pin)
- Time to expiry < 60 minutes (pin is very strong)

**Widen the range (use 0.4 multiplier) when:**
- VIX > 20 (elevated volatility)
- OI at pin strike is 2-2.5x average (borderline pin)
- Time to expiry > 90 minutes (pin is weaker)

**Example calibration:**
- VIX = 18, OI = 3x average, 75 minutes to expiry
- Use standard 0.3 multiplier
- QQQ straddle = $1.50
- pin_range = $1.50 * 0.3 = $0.45 QQQ = $0.45 * 85.66 = 38.5 NQ points
- Pin zone: NQ_pin ± 38.5 points

## Do Not Hold Through the Pin Window

This is the most important practical rule of Regime F. The pin window is a choppy, oscillating environment. Positions held through the pin window get chopped up.

**Why positions get chopped:**
- Price oscillates between the pin range boundaries
- Each oscillation triggers stops on both sides
- The oscillation frequency increases as expiry approaches
- A position that's profitable at 2:30 PM can be stopped out by 3:00 PM and then profitable again by 3:30 PM

**The solution:** Trade the pin range boundaries as discrete setups. Enter at the boundary, target the pin strike, exit at the pin strike. Do not hold through the oscillation. Do not try to ride the full range from one boundary to the other. Take the half-range trade (boundary to pin strike) and exit.

## Concrete Example

**Session: NQ at 21,500, QQQ at 251.00**
- Ratio: 85.66x
- Date: Friday (0DTE for QQQ weekly options)
- Time: 2:15 PM ET
- FlashAlpha: 0DTE OI at QQQ 251 = 45,000 contracts. Average OI at surrounding strikes = 12,000. Ratio = 3.75x (strong pin).
- QQQ ATM 0DTE straddle = $1.40
- pin_range = $1.40 * 0.3 = $0.42 QQQ = $0.42 * 85.66 = 36 NQ points
- Pin zone: 21,502 ± 36 = 21,466 to 21,538

**Scenario: Fade upper boundary**
- 2:20 PM: NQ rallies to 21,538 (upper boundary)
- Rithmic DOM: Offers reloading at 21,538. Iceberg offers visible.
- Massive: 0DTE call volume declining at QQQ 251 strike.
- **Action: Short NQ at 21,535, stop at 21,553 (15 ticks above boundary), target 21,502 (pin strike)**
- 2:35 PM: NQ at 21,502. Close position.
- **Result: 33 NQ points. Clean pin fade.**

**Scenario: Fade lower boundary**
- 2:45 PM: NQ sells off to 21,466 (lower boundary)
- Rithmic DOM: Bids reloading at 21,466. Iceberg bids visible.
- Massive: 0DTE put volume declining at QQQ 251 strike.
- **Action: Long NQ at 21,470, stop at 21,452 (15 ticks below boundary), target 21,502 (pin strike)**
- 3:00 PM: NQ at 21,502. Close position.
- **Result: 32 NQ points. Clean pin fade.**

**Scenario: Pin break**
- 3:15 PM: Fed speaker makes hawkish comment. NQ drops 80 points in 2 minutes to 21,420.
- This is 1.5x the pin range (36 * 1.5 = 54 points) in a single bar.
- **Action: Pin is broken. Exit any Regime F positions immediately. Reclassify.**
- New regime: Depends on underlying GEX structure. Run classification from `regime-identification.md`.

## Cross-References

- Classification: `regime-identification.md`
- Regime A (positive gamma, between walls): `regime-a-positive-between.md`
- Transition mechanics: `regime-transitions.md`
- Pre-event override: `regime-g-pre-event.md`
