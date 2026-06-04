# Stop Placement for LVN Trades

Stops are where most traders lose money on otherwise valid LVN setups. The rules here aren't suggestions. They're the difference between a system that survives drawdowns and one that blows up on a single bad fill.

---

## Rule #1: Never Place Stops Inside an LVN

This is the foundational rule. LVN zones have thin liquidity by definition. When your stop sits inside one, you're placing it in a region where there are almost no resting orders to absorb execution. The result: terrible fill prices, wide slippage, and a loss that's larger than your model predicted.

Stop hunts through LVN zones are common precisely because they're cheap to trigger. A large player can push price through a thin zone with minimal capital, triggering retail stops, then reverse. If your stop is inside the LVN, you're the liquidity being harvested.

The fix is simple: stops go on the other side of structural levels, not inside the thin air between them.

---

## Stop Placement by Setup Type

| Setup | Stop Location | Rationale | Typical Width (NQ pts) |
|---|---|---|---|
| LVN Breakout | Just inside LVN on entry side | If price returns to LVN, breakout failed | 3-8 |
| LVN Rejection Fade | Beyond LVN boundary (opposite side) | If price breaks through, rejection failed | 5-12 |
| LVN Retest S/R | Back inside prior value area | If returns to old VA, polarity flip failed | 8-15 |
| LVN Gap Fill | Beyond opposite side of LVN | Full rejection of gap fill | 5-10 |
| Institutional Defense | Just beyond LVN or recent swing | Institution isn't defending | 5-10 |
| AMT Trend/Reversion | Failed high/low or 5-10% account risk | Trend/reversion thesis invalidated | Dynamic |

"Just inside" and "just beyond" mean 1-2 NQ points past the structural boundary, not at the exact edge. Give the level a tick of breathing room so normal noise doesn't clip you.

---

## Position Sizing from Stop Distance

Fixed dollar risk per trade is the only sane approach. Varying risk based on conviction is how traders blow up.

**Formula:**

```
Contracts = Dollar Risk / (Stop Distance in pts x $20 per pt)
```

**Examples:**

- $500 risk, 5-pt stop: 500 / (5 x 20) = 5 contracts
- $500 risk, 10-pt stop: 500 / (10 x 20) = 2.5 → 2 contracts (round down)
- $500 risk, 15-pt stop: 500 / (15 x 20) = 1.67 → 1 contract

Never increase contracts to maintain a target R:R ratio. If the stop is wide and the math gives you 1 contract, trade 1 contract. Adjust the target instead, or skip the trade entirely if R:R falls below minimum.

---

## HVN Edge Placement Principle

Stops should always anchor to an HVN edge whenever possible. HVN edges are where real support and resistance exists. Volume was transacted there. Institutional positions were built there. For price to reach your stop, it has to break through those positions.

This is your structural protection. A stop floating in empty space between levels has no such protection. An HVN-anchored stop forces the market to do real work before taking you out.

When no nearby HVN edge exists, use the most recent swing high/low as the anchor. Never use a round number or an arbitrary point count as your only rationale.

---

## Trailing Stop Rules

Once a trade is working, the goal shifts from protection to profit capture. These rules apply in sequence:

1. **Price clears LVN and reaches midpoint to target HVN:** Trail stop to breakeven. You're now playing with house money.

2. **Price reaches 75% of the distance to target:** Trail stop to entry plus 50% of the distance traveled. Lock in a partial win.

3. **Price reaches target HVN:** Either take full profit or trail stop to the LVN exit edge. Don't let a winner turn into a loser by holding through an HVN without a plan.

Don't trail too aggressively in the early part of the move. LVN traversal can be fast but choppy. Give the trade room to breathe until it's clearly working.

---

## Minimum R:R by Setup

If the setup doesn't meet minimum R:R, skip it. There will be another one.

| Setup | Minimum R:R | Skip If Below |
|---|---|---|
| LVN Breakout | 2.5:1 | 2:1 |
| LVN Rejection Fade | 1.5:1 | 1:1 |
| LVN Retest | 2:1 | 1.5:1 |
| Gap Fill | 2:1 | 1.5:1 |
| Institutional Defense | 2:1 | 1.5:1 |
| AMT Trend/Reversion | 2:1 | 1.5:1 |

Rejection fades get a lower minimum because the entry is typically tighter and the setup resolves quickly. Breakouts get a higher minimum because they carry more false-breakout risk.

---

## Daily Loss Limits

**Maximum daily loss: 3% of account.** When you hit it, stop trading for the day. No exceptions, no "one more setup." LVN setups cluster in time, and a bad day can compound fast if you keep firing.

**Maximum consecutive losses: 3.** After three consecutive LVN losses, step back before the next trade. Ask:

- Are you in the wrong gamma regime? Negative GEX environments make LVN structures less reliable.
- Is the profile stale? If the VP was built on yesterday's data and price has moved significantly, the LVN map is wrong.
- Is session time suboptimal? Afternoon and pre-market LVN setups fail at higher rates.

Three consecutive losses is a signal that something in the environment has changed, not just bad luck. Diagnose before continuing.
