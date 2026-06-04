# Setup #5: Unfinished Business

---

## Overview

Unfinished Business (UB) is NOT a standalone trading setup. Dale does not use it as a primary entry signal. Instead, it's a decision-support tool that modifies how you manage existing trades, place stops, and evaluate whether a move is a pullback or a trend change.

The concept: when a bar closes without fully completing its price discovery at the high or low, it leaves "unfinished business" at that extreme. Price has a magnetic tendency to return and test that level. The software draws a dotted line from the UB level until price revisits it.

Understanding UB makes you a better manager of the four primary setups. Ignoring it leads to avoidable stop-outs and missed profit extensions.

---

## Logic Behind the Setup

A properly formed high occurs when the ask side at the high tick shows 0 contracts. This means no sellers were willing to sell at that price, so price couldn't go higher. The bar closed with the high untested from the ask side.

A properly formed low occurs when the bid side at the low tick shows 0 contracts. No buyers stepped in at that price, so price couldn't go lower. The bar closed with the low untested from the bid side.

When BOTH the bid AND ask show volume greater than 0 at the high or low, the bar's extreme was contested. Both sides transacted there. That's Unfinished Business. Price didn't cleanly reject that level. It left a loose end. Markets tend to return and resolve loose ends.

The UB magnet effect is real but not guaranteed. Price can travel far in the opposite direction before eventually returning to test the UB level. It's a tendency, not a rule.

---

## How to Identify Unfinished Business

### Properly Formed High (NO Unfinished Business)
- At the high tick of the bar: Bid > 0, Ask = 0
- Sellers were absent at the high. Price couldn't go higher. Clean rejection.

### Properly Formed Low (NO Unfinished Business)
- At the low tick of the bar: Bid = 0, Ask > 0
- Buyers were absent at the low. Price couldn't go lower. Clean rejection.

### Unfinished Business at the High
- At the high tick of the bar: Bid > 0 AND Ask > 0
- Both sides transacted at the high. The high was not cleanly rejected. Price will likely return.

### Unfinished Business at the Low
- At the low tick of the bar: Bid > 0 AND Ask > 0
- Both sides transacted at the low. The low was not cleanly rejected. Price will likely return.

The software draws a dotted horizontal line at the UB level and removes it once price revisits that level.

---

## The Four Supporting Roles

### Role 1: Take Profit Extension

**Situation:** You're in a profitable trade and price is moving in your favor toward a UB level.

**Rule:** If a UB level is close to your original profit target, stay in the trade past your target. The UB magnet will likely pull price to that level. You can extend your take profit by a few ticks or points.

**Condition:** The UB must already be close to your target when you enter the trade. Don't extend a target to reach a UB that's far away. The extension only makes sense when the UB is already nearby.

**Example:** You're long NQ from 21,050. Your target is 21,100. There's a UB at 21,108. Instead of exiting at 21,100, hold to 21,108. The UB magnet pulls price those extra 8 points.

---

### Role 2: Stop Loss Placement Awareness

**Situation:** You're placing a stop loss, and there's a UB level between your entry and your stop.

**Rule:** Do NOT place your stop between your entry and a UB level. If price approaches your stop, the UB magnet effect will likely push price through your stop to test the UB. You'll get stopped out, then watch price reverse from the UB and go in your original direction.

**Correct approach:** Place your stop beyond the UB level, not between your entry and the UB.

**Example:** You're long NQ from 21,100. Your planned stop is at 21,080. There's a UB at 21,075. If price pulls back toward 21,080, the UB at 21,075 will likely pull price through your stop. Move your stop to 21,070 (below the UB) or accept the wider risk.

---

### Role 3: Trend Continuation vs. Trend Change

**Situation:** You're in a position and price temporarily reverses against you. You're unsure if it's a pullback or a trend change.

**Rule:** If a UB formed at the reversal point, it's likely just a pullback. Price reversed to test the UB, not because the trend changed. Hold your position. Price will likely return to the UB, test it, and then continue in the original trend direction.

**Example:** You're long NQ. Price was at 21,200 and pulls back to 21,150. You're worried the trend is reversing. But you notice a UB formed at 21,150 during the pullback. The pullback was likely driven by the UB magnet. Hold the long. Price tests 21,150, then continues up.

---

### Role 4: Bad Trade Warning (Pre-Entry Filter)

**Situation:** You're about to enter a trade, but there's a UB level between your entry and your target.

**Rule:**
- **Don't enter Long** when a UB is below your entry. The UB magnet will pull price down toward it before it can go up. You'll likely get stopped out or sit in a losing trade while price tests the UB.
- **Don't enter Short** when a UB is above your entry. The UB magnet will pull price up toward it before it can go down.

**Example:** You want to enter Long NQ at 21,100. Your target is 21,200. But there's a UB at 21,080. The UB below your entry will pull price down to 21,080 before it goes up. Either wait for the UB to be tested first, or skip the trade.

---

## Step-by-Step Rules

1. Before entering any trade from Setups #1-4, check for UB levels near your entry, stop, and target.
2. If a UB is between your entry and your stop, move your stop beyond the UB.
3. If a UB is between your entry and your target (in the wrong direction), consider skipping the trade or waiting for the UB to be tested first.
4. If you're in a profitable trade and a UB is near your target, extend your target to the UB level.
5. If price reverses against your position and a UB forms at the reversal point, treat it as a pullback signal, not a trend change. Hold your position.
6. Once price tests a UB level, the dotted line disappears. The UB is resolved. It no longer acts as a magnet.

---

## Direction Rules

UB has no inherent directional bias. It's a magnet, not a signal. The direction of the pull is always toward the UB level from wherever price currently is.

- UB above current price = upward pull
- UB below current price = downward pull

This is why UB below a long entry is dangerous (pulls price down) and UB above a short entry is dangerous (pulls price up).

---

## Two Factors That Drive Price

UB doesn't follow the same two-factor logic as the primary setups. Instead, the mechanism is market structure completion. Price discovery is incomplete at a UB level. The market has a structural tendency to complete price discovery at every level. UB is the footprint evidence that a level wasn't fully explored. The market returns to finish the job.

---

## Examples Description

**TP extension:** Long NQ from 21,050, target 21,100, UB at 21,112. Hold past 21,100. Price reaches 21,112, UB resolves, exit there.

**Stop placement:** Long NQ from 21,200, planned stop at 21,170, UB at 21,165. Move stop to 21,160 (below UB) to avoid being pulled through by the magnet.

**Trend confirmation:** Long NQ, price pulls back from 21,300 to 21,250. UB formed at 21,250 during the pullback. Hold the long. Price tests 21,250, then resumes upward.

**Bad trade filter:** Want to go Long NQ at 21,100. UB at 21,085. Skip the trade or wait for price to test 21,085 first, then enter long after the UB is resolved.

---

## When to Use

- As a modifier to any of the four primary setups
- When placing stop losses (check for UB between entry and stop)
- When setting profit targets (check for UB near target for potential extension)
- When evaluating a reversal against your position (UB at reversal = likely pullback)
- When filtering trade entries (UB in the wrong direction = skip or wait)

---

## When NOT to Use

- As a standalone entry signal (it's not designed for this)
- As a Holy Grail. Price can travel far before testing a UB. Don't hold losing trades indefinitely because "UB will pull price back."
- When the UB is very far from current price. The magnet effect weakens with distance.
- When multiple UB levels exist in both directions. Conflicting magnets reduce the signal quality.

---

## Key Settings

| Setting | Value |
|---|---|
| UB at high condition | Bid > 0 AND Ask > 0 at the high tick |
| UB at low condition | Bid > 0 AND Ask > 0 at the low tick |
| Properly formed high | Ask = 0 at the high tick |
| Properly formed low | Bid = 0 at the low tick |
| Software display | Dotted horizontal line until price revisits |
| Standalone setup | No |
| Use as | Decision-support modifier for Setups #1-4 |

---

## NQ/ES-Specific Notes

- NQ moves fast and creates UB levels frequently due to its volatility. On any given 30-minute session, you'll see multiple UB levels. Focus on the ones closest to your active trade levels.
- ES UB levels tend to be more precise because ES has a smaller tick size. A UB at a specific tick on ES is a tighter target than a UB on NQ.
- During the RTH open (9:30-10:00 ET), NQ often creates UB levels in the first few bars as price discovers the day's range. These early UB levels frequently get tested within the same session.
- NQ overnight UB levels (formed during globex) often get tested during RTH. If there's a UB from the overnight session sitting near a key level, factor it into your RTH trade planning.
- The UB magnet effect is strongest when the UB level coincides with a prior day's high, low, or settlement. The confluence of technical significance + incomplete price discovery makes the pull more reliable.
- Don't use UB to justify holding a losing NQ trade indefinitely. NQ can move 50+ points against you before testing a UB. The magnet effect doesn't override risk management. If your stop is hit, exit. UB is a planning tool, not a reason to ignore stops.
