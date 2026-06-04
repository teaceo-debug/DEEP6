# Setup 2: Wall Break

## Overview

The Wall Break is the lower-frequency, higher-payoff counterpart to the Wall Bounce. Where the Wall Bounce fades price at a GEX wall, the Wall Break trades the continuation after a wall fails. The payoff is 2:1 to 3:1 R:R, but the win rate is lower (55-60%) because false breakouts are common.

The most important rule in this setup: do NOT enter on the break itself. The break triggers stops on the other side, creates a spike, and often snaps back. The edge is in waiting for the FIRST PULLBACK to the broken wall level, where the wall becomes support (broken call wall) or resistance (broken put wall). Waiting for the pullback filters out most false breakouts and dramatically improves the win rate.

This setup works across all regimes, but the character changes significantly. In positive gamma, wall breaks are rare and significant — when they happen, they represent a genuine regime shift. In negative gamma, wall breaks are common and part of the cascade — they're expected, not exceptional.

---

## 1. Setup Name and Overview

**Name:** Wall Break (Broken Wall Continuation)
**Type:** Momentum continuation after structural break
**Frequency:** 1-3 times per week (positive gamma); 3-8 times per week (negative gamma)
**Best variant:** Call wall break in Regime C transitioning to D (regime transition amplifies the move)
**Worst variant:** Wall break in Regime A (rare, often false, snap-back risk is high)

The setup enters on the first pullback to a broken GEX wall, trading the continuation in the direction of the break.

---

## 2. Regime Requirements

**Regime A (strong positive gamma):**
- Wall breaks are RARE. When they happen, they're significant.
- Win rate: 50-55% (high false breakout rate in strong positive gamma)
- R:R: 2.5:1 to 4:1 (when real, the move is large because it represents a genuine regime shift)
- Approach with extreme caution. Require 5/5 conviction.
- The snap-back risk is highest in Regime A because dealers are most aggressively defending walls.

**Regime B (moderate positive gamma):**
- Wall breaks are uncommon but more frequent than Regime A
- Win rate: 55-60%
- R:R: 2:1 to 3:1
- Require 4/5 conviction minimum

**Regime C (weak positive gamma / near flip):**
- Wall breaks are the most significant setup in this regime
- A put wall break in Regime C triggers a regime transition to D or E
- Win rate: 60-65% (the regime transition amplifies the move, making it more sustained)
- R:R: 2.5:1 to 4:1
- This is the highest-value wall break variant

**Regime D (negative gamma, controlled):**
- Wall breaks are common and expected
- Win rate: 55-60%
- R:R: 1.5:1 to 2.5:1
- Moves are larger but also more volatile (negative gamma amplification)
- Tighter stops required

**Regime E (negative gamma, crisis):**
- Wall breaks are continuous (cascading)
- Win rate: 50-55% (chaotic, hard to time pullbacks)
- R:R: 1.5:1 to 2:1
- Reduce position size by 50% regardless of conviction
- Only trade with 5/5 conviction

---

## 3. Entry Conditions (All Four Rivers + Derived)

### FlashAlpha (Structure) — Required
- The wall has been clearly broken: price has closed BEYOND the wall by at least 10 NQ ticks on a 1-minute bar
- The wall level is now acting as the new support (broken call wall) or resistance (broken put wall)
- OI at the broken wall strike is declining (the positions that created the wall are being closed or rolled)
- New OI is building at strikes BEYOND the broken wall (participants are repositioning at the new level)
- DEX has shifted in the direction of the break (confirming the structural change)

### Massive.com (Flow) — Required
- Premium is INCREASING at the broken wall level and beyond. The flow is not exhausting — it's accelerating.
- New OI is building at strikes beyond the broken wall (not just closing of existing positions)
- Sweeps are escalating in the direction of the break (not just a single sweep that triggered the break)
- At broken call wall: call buying is increasing at higher strikes. At broken put wall: put buying is increasing at lower strikes.
- The flow must be OPENING new positions, not closing existing ones. Check bid/ask side: at-ask = opening (conviction). At-bid = closing (less conviction).

### Unusual Whales (Dark) — Required
- Dark pool MUST confirm the direction of the break
- Broken call wall: dark pool is buying (institutional conviction that price will continue higher)
- Broken put wall: dark pool is selling (institutional conviction that price will continue lower)
- Net dark premium must be in the direction of the break by at least $10M
- Institutional sweep alerts confirming the break direction

**This is non-negotiable.** If dark pool does not confirm the break direction, the break may be a false breakout or a stop-hunt. Do not trade without dark pool confirmation.

### Rithmic MBO (DOM) — Required
- Offers PULLED at broken call wall (sellers retreating — they no longer defend the level)
- Bids PULLED at broken put wall (buyers retreating — they no longer defend the level)
- The book is THIN beyond the broken wall (no significant resting orders in the direction of the break — the path is clear)
- Aggressive market orders in the direction of the break (not just passive drift)
- No icebergs on the opposite side of the break (no hidden sellers at broken call wall, no hidden buyers at broken put wall)

### Derived — Supporting
- The next structural level (next wall, EM boundary, or gamma flip) is at least 30 NQ ticks away (room to run)
- Max pain is in the direction of the break (gravitational pull supporting the move)
- 0DTE walls have shifted in the direction of the break (the 0DTE structure is now aligned with the break)

---

## 4. Entry Execution

**The cardinal rule: Do NOT enter on the break itself.**

The break triggers stops on the other side, creates a spike, and often snaps back. The spike is not the entry. The pullback is the entry.

**Entry technique:** Wait for the FIRST PULLBACK to the broken wall level. The broken wall becomes the new support (broken call wall) or resistance (broken put wall). Enter on the pullback to this level.

**Pullback entry specifics:**
- Broken call wall (now support): Enter long when price pulls back to within 5 ticks of the broken call wall level. Place a limit order at the broken wall level.
- Broken put wall (now resistance): Enter short when price pulls back to within 5 ticks of the broken put wall level. Place a limit order at the broken wall level.

**Pullback timing:** The pullback typically occurs within 3-10 bars (3-10 minutes on a 1-minute chart) after the initial break. If no pullback occurs within 15 minutes, the opportunity has passed. Do not chase.

**If no pullback:** Skip the trade. The market is moving too fast for a safe entry. The next opportunity will come at the next structural level.

**Confirmation at pullback:** When price pulls back to the broken wall, the DOM must show that the broken wall is now acting as support/resistance. At broken call wall: bids should appear at the level. At broken put wall: offers should appear at the level. If the level is not being defended on the pullback, the break may be false.

---

## 5. Stop Loss Rules

**Primary stop:** Back inside the broken wall.

- Broken call wall (long): Stop is 5-8 ticks BELOW the broken call wall. If price closes back below the call wall, the break was false.
- Broken put wall (short): Stop is 5-8 ticks ABOVE the broken put wall. If price closes back above the put wall, the break was false.

**Why tighter than the wall bounce stop:** The wall break entry is at the broken wall level. If price goes back inside the wall, the trade is definitively wrong. There's no ambiguity. The stop should be tight.

**Regime adjustments:**
- Regime A: Stop 8-10 ticks inside the wall (snap-back risk is highest)
- Regime B/C: Stop 5-8 ticks inside the wall
- Regime D/E: Stop 5-6 ticks inside the wall (faster moves, tighter stops)

**DOM-based stop:** If the broken wall level stops acting as support/resistance (bids pull at broken call wall, offers pull at broken put wall), exit immediately. The level is not holding as the new support/resistance.

---

## 6. Profit Target Rules

**Primary target:** The next major structural level in the direction of the break.

- Broken call wall: Next call wall above, or the expected move high, or the next significant OI concentration
- Broken put wall: Next put wall below, or the expected move low, or the next significant OI concentration

**Secondary target:** The gamma flip level (if the break is moving toward the flip from the other side).

**Target distance:** The next level should be at least 30 NQ ticks away for the trade to be worth taking. If the next level is only 15 ticks away, the R:R is insufficient (stop is 5-8 ticks, target is 15 ticks = 2:1 R:R minimum, but the win rate is 55-60%, making the EV marginal).

**Partial profit taking:**
- Take 50% at the halfway point between entry and target
- Let remaining 50% run to the full target
- Move stop to breakeven after taking first partial

**Regime D/E adjustment:** Take full profit at the first target. In negative gamma, moves can reverse sharply. Don't hold for extended targets.

---

## 7. Position Sizing

| Conviction | Position Size | Notes |
|---|---|---|
| 5/5 (all conditions + dark confirmation) | 75% of max | Wall break max is 75% (lower win rate than wall bounce) |
| 4/5 (all required conditions met) | 50% of max | Standard wall break size |
| 3/5 (one required condition missing) | 25% of max | Only if dark pool confirms |
| 2/5 or below | 0% | Do not trade |

**Note:** The maximum position size for wall break is 75% of the wall bounce maximum. The lower win rate (55-60% vs 70-78%) justifies a smaller maximum size to maintain consistent risk-adjusted returns.

**Regime E adjustment:** Reduce all sizes by 50% regardless of conviction. Regime E is too chaotic for full-size positions.

---

## 8. Order Book Confirmation

**Pre-break DOM signals (watch for these to anticipate the break):**
- Resting orders at the wall are NOT reloading (the wall is being consumed)
- Aggression imbalance is strongly in the direction of the break (3:1 or more)
- Icebergs at the wall are disappearing (the hidden defense is being exhausted)
- Book is thinning on the break side (no significant resting orders beyond the wall)

**Post-break DOM signals (confirm the break is real):**
- Offers pulled at broken call wall (sellers retreating)
- Bids pulled at broken put wall (buyers retreating)
- Aggressive market orders continuing in the break direction
- Book is thin beyond the broken wall (clear path)

**Pullback DOM signals (confirm the entry):**
- At broken call wall pullback: bids appearing at the broken wall level (new support forming)
- At broken put wall pullback: offers appearing at the broken wall level (new resistance forming)
- The level is being defended on the pullback (orders reload after being hit)

**False breakout DOM signals (abort the trade):**
- Offers reappearing at broken call wall (sellers returning to defend the level)
- Bids reappearing at broken put wall (buyers returning to defend the level)
- Aggression imbalance reversing (market orders now going against the break)
- Icebergs appearing on the opposite side of the break

---

## 9. Win Rate and R:R Estimates

| Variant | Regime | Win Rate | R:R | Expected Value |
|---|---|---|---|---|
| Call wall break | A | 50-55% | 2.5:1 to 4:1 | +0.50R to +1.20R |
| Call wall break | B | 55-60% | 2:1 to 3:1 | +0.60R to +0.80R |
| Call wall break | C→D | 60-65% | 2.5:1 to 4:1 | +0.75R to +1.60R |
| Put wall break | A | 50-55% | 2.5:1 to 4:1 | +0.50R to +1.20R |
| Put wall break | B | 55-60% | 2:1 to 3:1 | +0.60R to +0.80R |
| Put wall break | C→D | 60-65% | 2.5:1 to 4:1 | +0.75R to +1.60R |
| Any wall break | D | 55-60% | 1.5:1 to 2.5:1 | +0.33R to +0.50R |
| Any wall break | E | 50-55% | 1.5:1 to 2:1 | +0.25R to +0.60R |

**The Regime C→D transition is the highest-value variant** because the regime transition amplifies the move (negative gamma kicks in after the flip is crossed) and the setup is well-defined (the put wall break IS the regime transition trigger).

---

## 10. Failure Modes

### Failure Mode 1: False Breakout (Most Common)

Price pushes through the wall, triggers stops on the other side, then snaps back inside the wall. This is the most common failure mode and the reason for the pullback entry rule.

**Why it happens:** A large sweep or block pushes price through the wall temporarily. The stops on the other side get triggered, creating a brief spike. But the underlying flow doesn't support the break, and price snaps back.

**Prevention:** The pullback entry rule filters most false breakouts. If price snaps back inside the wall before the pullback entry fills, the trade is avoided.

**Detection:** After the break, if price snaps back inside the wall within 3 bars (3 minutes), it's a false breakout. Do not enter.

### Failure Mode 2: Dark Pool Not Confirming

The break happens but dark pool doesn't confirm the direction. This is a major red flag. The break may be driven by retail flow or algorithmic stop-hunting, not institutional conviction.

**Prevention:** Require dark pool confirmation before entry. If UW doesn't show institutional activity in the break direction within 15 minutes of the break, skip the trade.

### Failure Mode 3: No Pullback (Runaway Move)

Price breaks the wall and never pulls back. The move is too fast and too strong for a safe entry.

**Response:** Skip the trade. The opportunity has passed. The next entry will be at the next structural level.

**Note:** This is not a failure — it's a missed opportunity. Missing a trade is always better than chasing a runaway move.

### Failure Mode 4: Pullback Becomes a Reversal

Price pulls back to the broken wall level but instead of bouncing, it continues back inside the wall. The break was false and the pullback entry is now a losing trade.

**Prevention:** The DOM must show defense at the broken wall level on the pullback. If the level is not being defended (no bids at broken call wall, no offers at broken put wall), do not enter.

**Response:** If already in the trade and the level fails on the pullback, exit immediately. The stop (back inside the wall) should trigger automatically.

### Failure Mode 5: Regime Doesn't Transition (Regime C)

In Regime C, a put wall break should trigger a regime transition to D or E. But sometimes the break is temporary and the regime doesn't transition — GEX stays positive, dealers continue to defend, and price reclaims the put wall.

**Detection:** After the put wall break in Regime C, check FlashAlpha. If GEX remains positive and the flip level is still above current price, the regime hasn't transitioned. The break may be false.

**Response:** Tighten stop to 3-5 ticks inside the wall. If price reclaims the wall, exit immediately.

---

## 11. Example Scenarios

### Example 1: Put Wall Break in Regime C (Best Variant)

**Setup:**
- NQ at 19,210. Put wall at 19,200. GEX = $60M (Regime C, near flip).
- FlashAlpha: GEX positive but weak. Put wall at 19,200 with 55,000 contracts OI. Flip level at 19,150.
- Massive: Put flow INCREASING as price approaches 19,200. Net put premium -$18M and growing. Put sweeps 4:1 over calls in last 30 minutes. New put OI building at 19,100 and 19,000 strikes.
- UW: Dark pool direction is net selling. Net dark premium -$22M. Institutional put sweep alerts present.
- DOM: Resting bids at 19,200 are NOT reloading (wall being consumed). Book is thin below 19,200. Aggressive market sells dominating (3:1 over buys).

**Break occurs:** NQ drops from 19,210 to 19,175 in 3 minutes. Wall broken by 25 ticks.

**Conviction check:** STRUCTURE bearish (wall broken, OI shifting), FLOW bearish (increasing put flow), DARK bearish (institutional selling), DOM bearish (thin below wall, aggressive sells), DERIVED bearish (flip level at 19,150 now in range). Score: -5. Maximum bearish conviction.

**Wait for pullback:** Price pulls back from 19,175 to 19,198 over 5 minutes.

**Entry:** Short at 19,198 (limit order at broken put wall level, now resistance).
**Stop:** 19,208 (8 ticks above broken put wall — back inside the wall).
**Target 1:** Flip level at 19,150 (48 ticks). Take 50% here.
**Target 2:** Next put wall at 19,000 (198 ticks). Let remaining 50% run.
**Size:** 75% of maximum (maximum for wall break setup).

**Result:** Price drops from 19,198 to 19,145 over 20 minutes (regime transition confirmed as GEX goes negative). First partial at 19,150 (48 ticks). Stop moved to breakeven. Price continues to 19,020. Second partial at 19,020 (178 ticks). Average exit: 113 ticks. Stop was 10 ticks. R:R achieved: 11.3:1.

### Example 2: Call Wall Break in Regime B

**Setup:**
- NQ at 19,990. Call wall at 20,000. GEX = $280M (Regime B).
- Massive: Call flow increasing. Net call premium +$25M and growing. Call sweeps 5:1 over puts. New call OI building at 20,100 and 20,200 strikes.
- UW: Dark pool net buying. Net dark premium +$20M. Institutional call sweep alerts.
- DOM: Resting offers at 20,000 are NOT reloading. Book thin above 20,000. Aggressive market buys 4:1 over sells.

**Break occurs:** NQ rallies from 19,990 to 20,025 in 4 minutes. Wall broken by 25 ticks.

**Wait for pullback:** Price pulls back from 20,025 to 20,003 over 6 minutes.

**Entry:** Long at 20,003 (limit order at broken call wall level, now support).
**Stop:** 19,993 (7 ticks below broken call wall — back inside the wall).
**Target 1:** Next call wall at 20,100 (97 ticks). Take 50% here.
**Target 2:** EM high at 20,150 (147 ticks). Let remaining 50% run.
**Size:** 50% of maximum (standard for wall break in Regime B).

**Result:** Price rallies from 20,003 to 20,108 over 35 minutes. First partial at 20,100 (97 ticks). Stop moved to breakeven. Price reaches 20,142. Second partial at 20,142 (139 ticks). Average exit: 118 ticks. Stop was 10 ticks. R:R achieved: 11.8:1.

---

## 12. Anti-Patterns (When It Looks Like This Setup But Isn't)

### Anti-Pattern 1: Break Without Dark Pool Confirmation

Price breaks a wall with strong visible flow (Massive) but dark pool is neutral or opposing. This looks like a wall break but the institutional conviction is absent. The break is likely driven by retail or algorithmic flow and has a high probability of reversing.

**Response:** Do not trade. Wait for dark pool to confirm.

### Anti-Pattern 2: Break on Low Volume

Price breaks a wall on below-average volume. Low-volume breaks are almost always false. The break needs volume to be sustained.

**Quantitative threshold:** Volume on the break bar must be at least 1.5x the 20-bar average volume. Below this, treat as a potential false breakout.

### Anti-Pattern 3: Break at End of Day (After 3:30 PM)

Wall breaks in the last 30 minutes of the session are often driven by end-of-day positioning, not genuine directional conviction. The break may not carry over to the next session.

**Response:** Reduce position size by 50% for any wall break after 3:30 PM. Do not hold overnight.

### Anti-Pattern 4: Break of a Previously Broken Wall

A wall that was broken earlier in the session and then reclaimed is not a fresh wall. Breaking it again has much lower conviction.

**Response:** Treat as a lower-conviction setup. Require 5/5 conviction and reduce size by 50%.

### Anti-Pattern 5: Break Without New OI Building Beyond the Wall

The break happens but no new OI is building at strikes beyond the broken wall. This means participants are not repositioning for a sustained move — they're just reacting to the break. The move is likely short-lived.

**Response:** Reduce target to the halfway point between the broken wall and the next level. Don't hold for the full target.

---

## 13. Time-of-Day Considerations

**9:30-10:00 AM (Opening):**
- Opening breaks are common but often false (opening range establishment)
- Wait for the opening range to establish (first 15-30 minutes) before trading wall breaks
- If a wall breaks in the first 15 minutes, wait for the pullback AND for the opening range to confirm the break direction

**10:00 AM-12:00 PM (Morning session):**
- Best time for wall break trades
- Volume is high, dark pool data is current, DOM signals are reliable
- Pullbacks are clean and well-defined

**12:00-1:30 PM (Lunch lull):**
- Wall breaks during the lunch lull are often false (low volume, thin book)
- Avoid wall break trades during this window
- If a break occurs, wait for volume to confirm before entering

**1:30-3:00 PM (Afternoon session):**
- Wall breaks are reliable in this window
- Charm flows may accelerate a break in the charm direction (see step5-setups/charm-flow.md)
- Good time for wall break trades

**3:00-4:00 PM (Power hour):**
- Wall breaks in the last hour can be violent (0DTE expiration, charm flows, end-of-day positioning)
- Reduce position size by 25%
- Take profits quickly — don't hold for extended targets in the last hour
- The pullback may not occur in the last 30 minutes (too fast)
