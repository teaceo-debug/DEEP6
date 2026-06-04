# Confirmation #1: Big Limit Orders

## Overview

Big Limit Orders is the first of four order flow confirmations used to time entries at pre-identified S/R zones. It works by spotting unusually large passive orders sitting at a level, revealing that a significant player was already waiting there — just like you.

This is **not a standalone strategy**. You must identify your S/R zone first (via Volume Profile, POC, HVN, or an order flow setup), then look for this confirmation when price arrives at that zone.

---

## When to Use Confirmations

Use this confirmation when any of the following apply:

- Price has reached a VP-based S/R zone and you want timing confirmation before entering
- You're uncertain about the setup and want additional evidence
- Price moved aggressively against your level (momentum is strong, you need proof it's stalling)
- The level isn't particularly strong on its own and needs extra validation

Never skip S/R identification. The confirmation only has meaning in the context of a level.

---

## Step-by-Step Rules

**Short (Resistance) Setup:**

1. Identify resistance zone using Volume Profile (HVN, POC, prior value area high, etc.)
2. Wait for price to reach or approach that zone
3. Open a 5-minute Bid x Ask footprint chart
4. Watch the ASK column at the resistance zone for unusually large numbers
5. A large number on the ASK = a big Limit Sell order sitting there, absorbing buying pressure
6. Once you can clearly identify the large limit order, enter short

**Long (Support) Setup:**

1. Identify support zone using Volume Profile
2. Wait for price to reach or approach that zone
3. Open a 5-minute Bid x Ask footprint chart
4. Watch the BID column at the support zone for unusually large numbers
5. A large number on the BID = a big Limit Buy order sitting there, absorbing selling pressure
6. Once you can clearly identify the large limit order, enter long

---

## What to Look For

**The critical distinction — which column to watch:**

| Direction | Order Type | Column | Meaning |
|-----------|-----------|--------|---------|
| Short | Limit Sell | **ASK** | Passive seller waiting at resistance |
| Long | Limit Buy | **BID** | Passive buyer waiting at support |

This trips up a lot of traders. Limit Sell orders show on the ASK because they're being hit by aggressive buyers. Limit Buy orders show on the BID because they're being hit by aggressive sellers.

**What counts as "unusually large":**

There's no fixed number. Compare the cell volume to recent average cell volumes for that instrument and session. If a cell is 3-5x the typical size, that's your signal. NQ and ES have different baseline volumes, and pre-market vs. regular session volumes differ significantly.

**Iceberg behavior:**

Large orders don't always appear all at once. A big player may be feeding their order in pieces to avoid detection. Give it a few minutes. If you see a cell that's notably large and keeps refreshing with more volume at the same price, that's iceberg behavior — the full order is bigger than what's visible at any single moment.

---

## Timeframe

**Primary:** 5-minute Bid x Ask footprint chart

The 5-minute gives enough bar duration to accumulate meaningful volume at a price level without being too slow to act on. Shorter timeframes (1-minute) can show the order but with more noise. Longer timeframes (30-minute) may confirm it too late for a clean entry.

---

## Combo With Other Confirmations

Big Limit Orders pairs especially well with Confirmation #3 (Aggressive Orders and Delta).

The ideal sequence:
1. Big limit order appears at the S/R zone (passive player enters first)
2. Shortly after, aggressive market orders pile in from other participants who see the same level and don't want to miss the move

This creates a snowball effect. The passive limit order acts as the anchor; the aggressive orders that follow are the momentum. Together they produce the highest-conviction signal of all four confirmations.

Can also combine with Confirmation #2 (Absorption) — both involve heavy volume at a level, but absorption looks at both sides simultaneously while this confirmation focuses on one side.

---

## NQ/ES Notes

**NQ (Nasdaq futures):**
- NQ moves faster and has thinner liquidity than ES. "Unusually large" on NQ might be 200-400 contracts in a single cell during regular session, but this varies. Build your baseline by watching a few sessions before trading.
- NQ is more prone to iceberg orders because large players don't want to show their hand in a thinner book.
- False signals are more common in NQ during low-volume periods (pre-market, lunch). Stick to the first 2 hours of regular session and the last hour for the cleanest reads.

**ES (S&P 500 futures):**
- ES has much deeper liquidity. A "big" limit order needs to be proportionally larger to stand out. Cells of 500-1000+ contracts may be needed to qualify as unusual during regular session.
- ES levels tend to hold more cleanly than NQ, so the confirmation is often more reliable when it appears.
- Both instruments: always compare to the same session's recent average, not a fixed threshold.
