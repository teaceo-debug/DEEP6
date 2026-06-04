# Step 6: Risk — Position Sizing

## Overview

Position sizing is the mechanism that translates conviction into capital deployment. The system uses a three-factor multiplicative model: conviction level, regime character, and setup-specific adjustment. These three factors multiply together to produce a final size as a fraction of the base position.

The base position is user-configured. One unit might be 1 NQ contract, 2 MNQ contracts, or any other denomination. The sizing model outputs a multiplier (0.0 to 1.0) that is applied to that base. The system never recommends more than 1.0x base (no leverage beyond the configured unit).

The hard constraint: stop distance in NQ points times position size in contracts times $20/point must never exceed 2% of account equity. This constraint overrides all other sizing calculations. If the conviction and regime multipliers produce a size that violates the 2% rule, reduce size until the rule is satisfied.

---

## Base Position Definition

Define your base position before the session starts. This is the maximum size you're willing to deploy on a 5/5 conviction, optimal regime trade.

Example configurations:
- Conservative: 1 NQ contract (base = 1 NQ)
- Moderate: 2 NQ contracts (base = 2 NQ)
- Aggressive: 5 NQ contracts (base = 5 NQ)
- MNQ-based: 10 MNQ contracts (base = 10 MNQ, equivalent to 1 NQ)

The system outputs size as a fraction of base. "0.75x base" means 75% of whatever you've configured as your base.

---

## Factor 1: Conviction-Based Sizing

Conviction is measured as X/5 where X is the number of data dimensions agreeing on direction. The conviction multiplier maps directly to position size.

| Conviction | Label | Size Multiplier |
|------------|-------|-----------------|
| 5/5 | MAXIMUM | 1.00x (full base) |
| 4/5 | HIGH | 0.75x |
| 3/5 | MODERATE | 0.50x |
| 2/5 | LOW | 0.00x (no trade) |
| 1/5 | MINIMAL | 0.00x |
| 0/5 | NONE | 0.00x |

The iceberg exception from kill-switches Gate 2 applies here: if 2/5 dimensions agree but one is an iceberg at a GEX level, treat as 3/5 and apply the 0.50x multiplier.

### Conviction multiplier rationale

The step from 3/5 to 4/5 is the most important threshold in the system. At 3/5, you have a majority but not a strong majority. At 4/5, four independent data streams are aligned — this is a high-quality signal. The jump from 0.50x to 0.75x reflects this quality difference.

At 5/5, all five dimensions agree. This is rare (perhaps 5-10% of setups) and represents the highest-quality trade the system can identify. Full base size is appropriate.

At 2/5, the system has no edge. Two dimensions agreeing is within the noise of random agreement. No trade.

---

## Factor 2: Regime-Based Adjustment

The regime multiplier adjusts for the structural risk of the current market environment. Some regimes have higher win rates and more predictable behavior. Others are inherently unstable or have poor R:R characteristics.

| Regime | Name | Multiplier | Rationale |
|--------|------|------------|-----------|
| A | Positive gamma, mid-range | 1.00x | Standard regime. Highest win rate for wall bounces. Full size. |
| B | Positive gamma, at call wall | 0.85x | Wall test adds uncertainty. Wall may break or hold. Slight reduction. |
| C | Positive gamma, at put wall | 1.10x | Highest win rate setup in the system. Put wall bounce in positive gamma is the most reliable trade. Slight increase. |
| D | Negative gamma, above flip | 0.60x | Unstable. Dealers are short gamma but price hasn't broken down yet. Regime can flip either direction. Significant reduction. |
| E | Negative gamma, below flip | 0.70x | Trending down. Dealer cascade amplifies moves. Trend-following trades have good R:R but the regime is volatile. Moderate reduction. |
| F | Pin regime | 0.50x | Tight range. Small moves. R:R is compressed. Half size. |
| G | Pre-event | 0.00x | No trade. Kill switch Gate 4 should have already blocked this. |

### Regime C explanation (1.10x)

Regime C is the put wall in positive gamma. This is the single highest win-rate setup in the entire system. The put wall in positive gamma has:
- GEX mechanics pushing price away from the wall (dealers buy dips)
- Historical win rate > 70% for the bounce trade
- Clear stop level (just below the put wall)
- Clear target (HVL or mid-range)

The 1.10x multiplier reflects this edge. It's the only regime where size increases above base.

### Regime D explanation (0.60x)

Regime D is the most dangerous regime for the system. Price is above the gamma flip but total GEX is negative. This means:
- Dealers are short gamma (amplify moves)
- But price hasn't broken down yet (still above flip)
- The regime can resolve either way: back to positive gamma (bullish) or through the flip (bearish cascade)

The uncertainty is maximum. 0.60x reflects this. If you're trading in Regime D, you're taking a lower-quality bet and should size accordingly.

---

## Factor 3: Setup-Specific Adjustment

Different setups have different win rates and R:R profiles. The setup multiplier adjusts for these characteristics.

| Setup | Name | Multiplier | Rationale |
|-------|------|------------|-----------|
| 1 | Wall Bounce | 1.00x | Standard. Highest win rate. Full conviction × regime. |
| 2 | Wall Break | 0.80x | Lower win rate (~45-55%) but higher R:R (3:1+). Reduce size to compensate for lower win rate. |
| 3 | Gamma Flip Cross | 0.70x | Lowest win rate (~40-50%) but highest R:R (5:1+). Significant size reduction. |
| 4 | Vanna Rally | 1.00x | Standard. Mechanical flow with predictable direction. |
| 5 | Charm Flow | 0.50x | Uncertain magnitude. Charm flows are directional but the size of the move is hard to predict. Half size. |
| 6 | Distribution Fade | 1.00x | Standard. Clear setup with defined entry and stop. |
| 7 | Sweep Cascade | Variable | See below. |
| 8 | EM Fade | 1.00x | Standard. Statistical edge at expected move boundaries. |

### Setup 7 (Sweep Cascade) variable sizing

The Sweep Cascade setup's size depends on dark pool confirmation:
- Dark pool confirms sweep direction (buying/selling in same direction as sweep): 1.00x
- Dark pool is neutral (no clear dark pool signal): 0.50x
- Dark pool opposes sweep direction: 0.00x (no trade — conflicting signals)

The sweep cascade is a momentum setup. Without dark pool confirmation, it's a lower-quality signal. With confirmation, it's full size.

### Setup 2 and 3 size reduction rationale

Wall Break (Setup 2) and Gamma Flip Cross (Setup 3) are the two setups with the lowest win rates in the system. They're included because their R:R ratios are exceptional — when they work, they work big. But they fail more often than they succeed.

The size reduction (0.80x and 0.70x) is not about reducing expected value. It's about managing the variance. A 45% win rate setup with 3:1 R:R has positive expected value, but the losing streaks can be psychologically and financially damaging if sized at full base. Reducing size keeps the losses manageable during the inevitable losing streaks.

---

## Final Size Calculation

```
final_size = base × conviction_mult × regime_mult × setup_mult
```

Then apply the 2% account risk constraint:
```
max_risk_dollars = account_equity × 0.02
max_contracts = max_risk_dollars / (stop_distance_pts × 20)
final_size = min(final_size, max_contracts)
```

### Example calculations

**Example 1: High-quality put wall bounce**
- Base: 2 NQ contracts
- Conviction: 4/5 → 0.75x
- Regime: C (at put wall, positive gamma) → 1.10x
- Setup: 1 (Wall Bounce) → 1.00x
- Raw size: 2 × 0.75 × 1.10 × 1.00 = 1.65 contracts → round to 2 NQ (or 16 MNQ)
- Stop: 8 NQ points below put wall
- Risk check: 2 contracts × 8 pts × $20 = $320. If account = $50,000, max risk = $1,000. $320 < $1,000. PASSES.
- Final: 2 NQ contracts

**Example 2: Moderate conviction gamma flip cross**
- Base: 2 NQ contracts
- Conviction: 3/5 → 0.50x
- Regime: D (negative gamma, above flip) → 0.60x
- Setup: 3 (Gamma Flip Cross) → 0.70x
- Raw size: 2 × 0.50 × 0.60 × 0.70 = 0.42 contracts → round to 0 NQ (below minimum)
- Result: NO TRADE. The combined multipliers produce a size below 1 contract. This is the system telling you the setup is too weak to trade at your base size.

**Example 3: Maximum conviction wall break**
- Base: 2 NQ contracts
- Conviction: 5/5 → 1.00x
- Regime: A (positive gamma, mid-range) → 1.00x
- Setup: 2 (Wall Break) → 0.80x
- Raw size: 2 × 1.00 × 1.00 × 0.80 = 1.6 contracts → round to 2 NQ
- Stop: 12 NQ points (tight, just below the broken wall)
- Risk check: 2 contracts × 12 pts × $20 = $480. If account = $50,000, max risk = $1,000. $480 < $1,000. PASSES.
- Final: 2 NQ contracts

**Example 4: 2% rule override**
- Base: 5 NQ contracts
- Conviction: 5/5 → 1.00x
- Regime: C → 1.10x
- Setup: 1 → 1.00x
- Raw size: 5 × 1.00 × 1.10 × 1.00 = 5.5 → round to 5 NQ
- Stop: 15 NQ points (wide stop due to volatile conditions)
- Risk check: 5 contracts × 15 pts × $20 = $1,500. If account = $50,000, max risk = $1,000. $1,500 > $1,000. FAILS.
- Override: max_contracts = $1,000 / (15 × $20) = 3.33 → round to 3 NQ
- Final: 3 NQ contracts (2% rule overrides the conviction/regime calculation)

### Rounding rules

- Round to the nearest whole contract (NQ) or nearest 2 MNQ
- If the calculated size is between 0 and 0.5 contracts, round DOWN to 0 (no trade)
- If the calculated size is between 0.5 and 1.0 contracts, round UP to 1 (minimum trade size)
- Never round up beyond the 2% account risk constraint

---

## Scaling In and Out

### Scaling in (adding to a position)

After entry, if new confirming data arrives that increases conviction, you can add to the position. Rules:
- Only add if conviction increases by at least 1 level (e.g., 3/5 → 4/5)
- Maximum add: 25-50% of original position size
- Never add if the position is already at a loss (no averaging down)
- Never add in negative gamma regimes (Regime D or E) — the amplification works against you

Example: Entered 1 NQ at 3/5 conviction (0.50x base). New iceberg detected at the level, upgrading to 4/5. Can add 0.5 NQ (25% of base). Total position: 1.5 NQ → round to 2 NQ.

### Scaling out (taking profits)

The standard scaling-out protocol:
1. Take 50% of position at the first target (HVL, nearest significant level, or 8-10 NQ points profit)
2. Move stop on remaining 50% to breakeven
3. Trail the remaining 50% with a 5-point trailing stop
4. Close remaining position at second target or end of session

This protocol locks in profit while allowing the position to run if the move extends. The 50% at first target ensures the trade is profitable even if the second half stops out at breakeven.

### Never average down in negative gamma

In Regime D or E (negative gamma), averaging down on a losing position is prohibited. Negative gamma means dealers amplify moves. A position that's going against you in negative gamma is going against you with dealer amplification. Adding to a losing position in this environment can result in catastrophic losses.

In positive gamma regimes (A, B, C), averaging down is still generally inadvisable, but the regime mechanics are less dangerous. Even so, the system does not recommend averaging down as a standard practice.

---

## The 2% Account Risk Rule

This is the hardest constraint in the sizing model. It overrides everything else.

**Formula:**
```
position_risk_dollars = contracts × stop_distance_pts × $20_per_point
max_allowed = account_equity × 0.02
```

If `position_risk_dollars > max_allowed`, reduce contracts until the constraint is satisfied.

### Why 2%

The 2% rule is the standard institutional risk management threshold. It ensures that even a string of maximum-loss trades doesn't destroy the account. With a 2% per-trade risk limit:
- 10 consecutive maximum losses = 20% drawdown (painful but survivable)
- 20 consecutive maximum losses = 40% drawdown (severe but recoverable)

In practice, the system's kill switches (especially Gate 8, consecutive loss limit) will stop trading long before 10 consecutive losses. The 2% rule is a backstop for the backstop.

### Stop distance estimation

The stop distance must be estimated BEFORE entry, not after. The stop is placed at a logical level (below the put wall for longs, above the call wall for shorts, or at the gamma flip for flip cross trades). The distance from entry to stop determines the risk per contract.

If the logical stop is too far away (making the 2% rule binding at a very small position size), the trade may not be worth taking. A trade where the 2% rule limits you to 0.5 contracts is a signal that the stop is too wide or the account is too small for this setup.

---

## Size Summary Table

For quick reference during live trading, with a 2 NQ contract base:

| Conviction | Regime A | Regime B | Regime C | Regime D | Regime E | Regime F |
|------------|----------|----------|----------|----------|----------|----------|
| 5/5 | 2.0 NQ | 1.7 NQ | 2.2 NQ | 1.2 NQ | 1.4 NQ | 1.0 NQ |
| 4/5 | 1.5 NQ | 1.3 NQ | 1.7 NQ | 0.9 NQ | 1.1 NQ | 0.8 NQ |
| 3/5 | 1.0 NQ | 0.9 NQ | 1.1 NQ | 0.6 NQ | 0.7 NQ | 0.5 NQ |

All values subject to setup multiplier and 2% account risk constraint. Values below 0.5 NQ round to 0 (no trade). Values above 0.5 NQ round to nearest whole NQ contract.

Setup multipliers applied on top of table values:
- Wall Bounce: ×1.00 (use table as-is)
- Wall Break: ×0.80
- Gamma Flip Cross: ×0.70
- Vanna Rally: ×1.00
- Charm Flow: ×0.50
- Distribution Fade: ×1.00
- Sweep Cascade (confirmed): ×1.00
- Sweep Cascade (unconfirmed): ×0.50
- EM Fade: ×1.00
