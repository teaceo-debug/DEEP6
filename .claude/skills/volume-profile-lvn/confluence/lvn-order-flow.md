# LVN + Order Flow — Footprint Confirmation at Volume Nodes

Volume profile tells you WHERE the market has structural significance. Footprint tells you WHAT is actually happening when price arrives there. Neither is sufficient alone. Together, they form the highest-accuracy reversal detection available from raw order flow data.

The core principle: LVN identifies a price zone where the market previously moved through quickly, leaving little traded volume. When price returns to that zone, the footprint reveals whether institutions are defending it (absorption, reversal) or ignoring it (continuation). The footprint is the verdict.

---

## LVN + Absorption

Absorption is the single most powerful confirmation signal at an LVN boundary. It means a passive institutional player is absorbing aggressive orders on one side, preventing price from moving despite significant volume.

**Signature at LVN:**
- Price arrives at LVN boundary (VAH, VAL, or composite HVN edge)
- One side of the footprint cell shows 5-10x normal volume
- Price stalls or barely moves despite that volume
- The opposite side shows minimal activity

What you're seeing: a large passive player sitting at the LVN edge, absorbing every aggressive order thrown at them. They're not chasing price. They're waiting for it to come to them, then filling against it.

**Why it works at LVN specifically:** In a high-volume zone (HVN), absorption is harder to read because there's always resting liquidity. At an LVN boundary, the book is thin. Any absorption that appears there is conspicuous. The passive player chose this thin zone deliberately, which signals conviction.

**Result:** Reversal. The absorbed side runs out of aggression. Price snaps back toward the nearest HVN or POC.

**Conviction level:** Higher than LVN alone. The LVN gives you the structural reason. The absorption gives you the timing and the institutional fingerprint.

---

## LVN + Delta Divergence

Delta divergence at an LVN is one of the most reliable reversal signals in order flow trading. It reveals a hidden battle between aggressive and passive participants.

**The setup:**
- Price breaks into or through an LVN (expected: acceleration, thin book)
- CVD (Cumulative Volume Delta) flattens or moves in the opposite direction of price
- This means: passive buyers or sellers are absorbing the aggressive flow despite price movement

**Strongest configuration:**
- Price makes a lower low at or inside the LVN
- CVD makes a higher low (bullish divergence)
- This means: aggressive sellers are pushing price down, but passive buyers are absorbing more than the previous swing

The divergence reveals that the aggressive side is losing ground even as they appear to be winning on price. The passive side is accumulating. When the aggressive side exhausts, the reversal is sharp because the passive side has built a large position.

**Why LVN amplifies this:** In a normal zone, divergence can persist for many bars as liquidity absorbs the flow gradually. At an LVN, the thin book means the passive player's absorption is more visible and the exhaustion happens faster. The divergence resolves more quickly.

**Bearish version:** Price makes higher high at LVN, CVD makes lower high. Passive sellers absorbing aggressive buyers. Reversal down.

---

## LVN + Stacked Imbalances

Stacked imbalances are 3 or more consecutive price levels within a single bar showing extreme directional imbalance (3:1 ratio or greater on one side). They indicate institutional aggression, not passive accumulation.

**Through LVN (continuation signal):**
- Price enters LVN zone
- Footprint shows 3+ consecutive levels with 3:1+ ask imbalance (for upward move)
- This means: aggressive buyers are not slowing down in the thin zone
- No passive sellers are stepping in to absorb
- Result: price accelerates through the LVN to the next HVN

This is the breakout confirmation. The stacked imbalances tell you the institutional aggressor has enough size and conviction to push through the thin zone without meeting resistance. The LVN becomes a runway, not a wall.

**At LVN boundary (reversal signal):**
- Price approaches LVN from below
- Footprint shows stacked imbalances on the BID side (sellers) at the LVN edge
- This means: aggressive sellers are defending the LVN boundary
- Combined with absorption on the ask side: double confirmation of reversal

**The 3:1 threshold:** Below 3:1, the imbalance could be noise. At 3:1 and above, it represents a meaningful skew in who is executing aggressively at that level. At 5:1 and above, it's institutional.

---

## LVN + CVD Behavior

CVD (Cumulative Volume Delta) tracks the running sum of buy volume minus sell volume. At LVN zones, CVD behavior is a direct read on institutional intent.

**Rising CVD through LVN (continuation):**
- Aggressive buyers are lifting offers in the thin zone
- No passive sellers absorbing the flow
- Price and CVD moving together = trend continuation
- The LVN is being treated as a runway, not a wall
- Target: next HVN or composite resistance

**Flat or declining CVD through LVN (reversal signal):**
- Price moving up, CVD flat or declining
- Passive sellers absorbing aggressive buyers in the thin zone
- The thin book makes this absorption more visible and more significant
- Result: reversal. The aggressive side is being neutralized.

**CVD spike at LVN boundary:**
- Sudden sharp move in CVD at the exact LVN edge
- Indicates institutional entry, either aggressive buying or selling
- If spike is in direction of prior trend: continuation
- If spike is against prior trend: reversal (institutional counter-trend entry)

**Reading CVD timeframes:** Use 1-minute CVD for entry timing. Use 5-minute CVD for trend context. If 5-minute CVD is rising but 1-minute CVD spikes down at LVN, the 1-minute spike is likely noise. If both timeframes show divergence at LVN, conviction is high.

---

## LVN + Aggressive Orders

The type of order used at a price level reveals institutional intent. At HVN, institutions use limit orders (passive accumulation, patient). At LVN, institutions use market orders (aggressive, riding momentum).

**Why this matters at LVN:**
- LVN means thin book, wide spreads, poor execution quality
- A rational institution would NOT use market orders in a thin zone unless they have strong directional conviction
- When you see large market order flow through an LVN, it means the institution is willing to pay the spread premium to get filled immediately
- This is a signal of urgency and conviction

**NQ-specific context:** NQ's book is thinner than ES. Institutional market orders through an NQ LVN are highly visible in the footprint because there's less resting liquidity to absorb them. The footprint cells show large numbers on one side with minimal opposition.

**Aggressive orders confirming breakout:**
- Large market buy orders through LVN = institutional conviction on upside
- No passive sellers absorbing = clean breakout
- CVD rising sharply = confirms the aggression

**Aggressive orders at LVN boundary (reversal):**
- Large market sell orders appearing at LVN upper edge
- Passive buyers absorbing below
- CVD declining despite price holding = institutional distribution

---

## Footprint Signatures: HVN vs LVN Behavior

| Dimension | HVN Behavior | LVN Behavior |
|-----------|-------------|-------------|
| Resting orders | Dense, multiple price levels | Sparse, few resting orders |
| Institutional memory | High (prior activity) | Low (price moved through quickly) |
| Absorption signal | Harder to read (noise) | Clear and significant |
| Delta behavior | Slow, gradual shifts | Sharp, fast shifts |
| Execution quality | Good (tight spreads) | Poor (wide spreads) |
| Stop placement | Stops cluster here | Stops rarely placed here |
| Breakout behavior | Slow, contested | Fast, uncontested |
| Reversal behavior | Gradual, multiple tests | Sharp, single test |
| Institutional order type | Limit orders (passive) | Market orders (aggressive) |
| CVD response | Gradual | Spike-like |

---

## Practical Workflow

The three-layer confirmation process:

**Layer 1: Volume Profile (WHERE)**
- Identify the LVN zone on the session or composite profile
- Mark the boundaries: upper edge, lower edge, midpoint
- Note the nearest HVN above and below (these are your targets)
- Note any naked VPOCs or prior session POCs nearby

**Layer 2: Footprint (WHAT)**
- Watch the footprint as price approaches the LVN
- Look for absorption (high volume, minimal movement)
- Look for stacked imbalances (3+ consecutive 3:1 ratios)
- Look for delta flip (negative turning positive, or vice versa)
- The footprint must show the micro behavior confirming the macro level

**Layer 3: Delta (WHO)**
- Check CVD for divergence or confirmation
- Rising CVD through LVN = continuation
- Flat or declining CVD through LVN = reversal
- CVD spike at boundary = institutional entry

**Entry rule:** Enter only when all three layers align. VP gives the level. Footprint gives the signal. Delta gives the conviction. Any two without the third is a lower-grade setup.

**Stop placement:** Below the LVN lower boundary for longs. Above the LVN upper boundary for shorts. The LVN itself is the invalidation zone. If price accepts inside the LVN (multiple bars, volume building), the structural thesis is wrong.

**Target:** Nearest HVN in the direction of the trade. LVN to HVN is the natural range of motion. Don't hold through the HVN without fresh footprint confirmation.
