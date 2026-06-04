# Passive vs Active (Aggressive) Market Participants

## Definition

Every executed trade has two sides: one participant used a **limit order** (passive), the other used a **market order** (aggressive/active).

- **Passive participant**: Places a limit order and waits for price to come to them. No slippage. They set the price.
- **Active/aggressive participant**: Uses a market order. Wants in immediately. Accepts whatever price is available, including slippage.

## Logic

The footprint chart records every executed trade at every price level. Each trade is classified by which side of the order book it hit:

- Trades hitting the **Ask** = aggressive buyer (market buy order)
- Trades hitting the **Bid** = aggressive seller (market sell order)

But here's what most traders miss: the other side of each trade is a passive participant sitting at that same price.

**BID side of footprint** = Aggressive Sellers + Passive Buyers  
**ASK side of footprint** = Aggressive Buyers + Passive Sellers

Both types of participants appear on both sides. You cannot isolate them from each other just by looking at the number.

## Step-by-Step Rules

1. When reading the Bid column, recognize it contains two overlapping signals: aggressive sellers hitting the bid AND passive buyers whose limit orders were filled.
2. When reading the Ask column, recognize it contains: aggressive buyers lifting the offer AND passive sellers whose limit orders were filled.
3. Never assume "high Ask volume = only buyers" or "high Bid volume = only sellers." Both sides are always present.
4. Use context (trend direction, S/R zones, delta) to infer which participant type is more likely dominant at a given price.
5. At known support zones, high Bid volume is more likely passive buyers absorbing aggressive sellers.
6. At known resistance zones, high Ask volume is more likely passive sellers absorbing aggressive buyers.

## When to Use

- Before interpreting any footprint number, confirm you understand which participant types contributed to it.
- When analyzing absorption setups: passive buyers at support absorb aggressive sellers, creating a reversal signal.
- When analyzing exhaustion setups: aggressive buyers run out of passive sellers at resistance, causing a reversal.
- Any time you're explaining footprint data to yourself or others.

## When NOT to Use

- Don't try to mathematically separate passive from aggressive volume within a single cell. The data doesn't allow it.
- Don't use this framework to make binary "buyers won / sellers won" calls on individual cells. It's more nuanced than that.

## NQ-Specific Notes

- NQ futures trade at high speed with significant algorithmic participation. Passive participants (market makers, algo limit orders) are extremely active.
- At key NQ levels (round numbers, prior day high/low, VWAP), passive order concentration is high. Bid/Ask volume at those levels reflects heavy two-sided activity.
- Aggressive sellers hitting the bid at NQ support are often absorbed by passive buyers (institutions building longs). This is the core absorption signal.
- Don't confuse high Bid volume at support as purely bearish. It may be passive buyers getting filled as aggressive sellers exhaust themselves.
