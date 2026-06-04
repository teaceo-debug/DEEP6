# LVN Breakout Acceleration

**Highest R:R Setup in the LVN Playbook**

## Overview

Trade the acceleration as price breaks through an LVN with volume confirmation. LVNs have no structural friction — price moves 2-3x faster through them than through HVN clusters. The edge here is mechanical: thin volume zones offer no resistance, so a committed breakout with volume behind it travels to the next HVN with minimal chop.

Best in negative gamma regime. Worst in positive gamma. Regime identification is not optional.

---

## Setup Conditions

All conditions must be met before considering entry.

1. **Clear LVN gap identified** between two HVN clusters on the session or composite profile
2. **Volume on breakout bar >= 1.5x session average** (confirms committed participation, not a probe)
3. **Minimum 2 bars on 5-minute chart closing fully beyond the LVN boundary** (acceptance, not a spike)
4. **Stacked imbalances on footprint** in the breakout direction: 3:1 bid/ask ratio or better across at least 3 consecutive price levels
5. **Gamma regime: NEGATIVE** (dealers hedge with price movement, amplifying momentum)
6. **No major news event within 15 minutes** of entry (news can reverse breakouts instantly)

If any condition is missing, skip the trade. The setup is only high-probability when all five align.

---

## Entry Rules

**Entry trigger:** Second bar closing fully beyond the LVN boundary on the 5-minute chart.

- Do not enter on the first bar through the LVN. First bars are probes. Second bars are acceptance.
- Entry is a limit order at the LVN boundary (the edge price just cleared), not a market order chasing.
- If price gaps through the LVN without a clean second-bar close, wait for a retest of the LVN boundary before entering. See `lvn-retest-support.md` for that setup.
- Entry window: 10:30 AM to 2:00 PM ET only. Breakouts outside this window have lower follow-through.

**Entry direction table:**

| Breakout direction | Entry side | Entry price |
|--------------------|------------|-------------|
| Bullish (upward) | Long | At or just above LVN upper boundary |
| Bearish (downward) | Short | At or just below LVN lower boundary |

---

## Stop Loss Rules

**Stop placement:** Just inside the LVN on the entry side.

- For longs: stop below the LVN lower boundary (the side price came from)
- For shorts: stop above the LVN upper boundary

The LVN is narrow by definition. This produces a tight stop, which is the mechanical source of the high R:R. If the stop feels too tight, the LVN is not narrow enough and the setup is marginal.

**Stop adjustment rules:**
- Do not widen the stop to accommodate noise. If price re-enters the LVN, the breakout has failed.
- Move stop to breakeven after price travels 50% of the distance to the target HVN.
- Trail stop to prior swing low/high after 75% of the distance to target.

**Invalidation:** If price closes back inside the LVN on a 5-minute bar, exit immediately. The breakout has failed. Do not hold hoping for recovery.

---

## Profit Target Rules

**Primary target:** The next HVN on the other side of the LVN.

HVNs are where price slows and consolidates. That's where the breakout momentum exhausts. Take full or partial profit at the HVN boundary.

**Target scaling:**
- 50% of position at the near edge of the target HVN
- Remaining 50% at the HVN POC (point of control)
- If price stalls at the HVN near edge with absorption visible on footprint, take full exit there

**Extended target:** If the target HVN is thin or price blows through it with volume, extend to the next structural level (prior day high/low, weekly level, or next HVN cluster).

---

## NQ-Specific Rules

- **Volume threshold:** NQ breakout bar volume >= 1.5x the 20-bar rolling average. On NQ, this typically means 3,000+ contracts on a 5-minute bar during RTH.
- **LVN distance from POC:** LVN should be at least 60 NQ points away from the session POC. LVNs close to POC are often noise, not structure.
- **Best time window:** 10:30 AM to 2:00 PM ET. The 9:30-10:30 AM window has too many fakeouts from opening range discovery. After 2:00 PM, volume thins and breakouts lose follow-through.
- **Avoid entering mid-LVN.** If price is already inside the LVN when you identify the setup, wait for the second bar close beyond the far boundary. Entering mid-LVN gives no structural reference for the stop.
- **NQ tick size:** 0.25 points. LVN boundaries should be defined to the nearest 0.25 point. Fuzzy boundaries produce fuzzy stops.

---

## Order Flow Confirmation

Required before entry. Do not enter without at least two of these three:

**1. Stacked imbalances (required)**
- Footprint shows 3:1 or better bid/ask imbalance across 3+ consecutive price levels in the breakout direction
- Imbalances must be on the breakout bar or the bar immediately preceding entry

**2. Delta confirmation**
- CVD (cumulative volume delta) trending in the breakout direction
- No divergence: price making new extreme AND CVD making new extreme in the same direction
- If CVD diverges (price new high, CVD lower high), the breakout is suspect

**3. Absorption absence**
- No large passive orders absorbing the breakout at the LVN boundary
- If footprint shows high volume at the LVN boundary with minimal price movement, that's absorption — the breakout is being defended against, not confirmed

---

## Gamma Regime Filter

This filter is non-negotiable. Ignoring it is the single most common reason this setup fails.

**NEGATIVE gamma (trade this setup):**
- Dealers are short gamma. They hedge by buying when price rises and selling when price falls.
- This dealer hedging amplifies price movement in the direction of the breakout.
- LVN breakouts in negative gamma can run 2-3x their normal distance.
- Identify: GEX is negative, price is above the gamma flip level, or FlashAlpha shows negative net GEX.

**POSITIVE gamma (do not trade this setup):**
- Dealers are long gamma. They hedge by selling when price rises and buying when price falls.
- This dealer hedging dampens price movement and causes mean reversion.
- LVN breakouts in positive gamma frequently fail and reverse back through the LVN.
- In positive gamma, use `lvn-rejection-fade.md` instead.

**NEUTRAL gamma (marginal):**
- Near the gamma flip level. Dealer hedging is minimal.
- Only trade if order flow confirmation is exceptionally strong (all three OF signals present).

---

## Risk-Reward Profile

| Metric | Typical range |
|--------|---------------|
| Win rate | 60-65% |
| R:R per trade | 3:1 to 5:1 |
| Stop width | 5-15 NQ points (LVN width) |
| Target distance | 30-80 NQ points (LVN to next HVN) |
| Expected value | +1.8R to +2.5R per trade |

The high R:R comes from the structural asymmetry: LVNs are narrow (tight stop) and the distance to the next HVN is typically much larger (wide target). This is not a scalp. Let the trade run to the HVN.

---

## Common Mistakes

**1. Entering mid-LVN**
The stop has no structural reference if you enter inside the LVN. Wait for the second bar close beyond the boundary.

**2. Ignoring gamma regime**
Trading this setup in positive gamma is the fastest way to turn a 3:1 R:R setup into a consistent loser. Check gamma before every trade.

**3. Chasing after price already cleared the LVN**
If price has already traveled 50%+ of the distance to the target HVN, the entry is late. The R:R is no longer 3:1. Skip it or wait for a retest.

**4. Using a single bar for acceptance**
One bar through an LVN is a probe. Two bars are acceptance. Entering on the first bar produces a much lower win rate.

**5. Trading during the first 30 minutes of RTH**
9:30-10:00 AM is price discovery. LVN breakouts during this window fail at a much higher rate. Wait for the market to find its footing.

**6. Skipping the volume confirmation**
A breakout on below-average volume is a low-conviction move. Institutions are not participating. These fail at 2-3x the rate of volume-confirmed breakouts.

**7. Holding through the target HVN**
HVNs are where price slows. Holding through the target HVN hoping for more is greed. Take the profit. The next LVN-to-HVN move is a separate trade.
