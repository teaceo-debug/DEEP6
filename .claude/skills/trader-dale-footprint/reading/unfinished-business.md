# Unfinished Business (Failed Auctions)

## Definition

Unfinished Business is a market imperfection where a bar's high or low was not properly formed. TD Order Flow auto-detects these and draws a dotted line (green for UB at a low, red for UB at a high) that persists until price revisits and "fixes" the level.

**Properly formed HIGH:** 0 contracts traded on the Bid at the bar's high price.  
**Properly formed LOW:** 0 contracts traded on the Ask at the bar's low price.

When price reverses without meeting these conditions, the high or low is "unfinished." The market left business undone at that price.

## Logic

When a bar's high forms with Bid volume > 0, it means sellers were still actively transacting at the top. The market didn't fully reject that price. It reversed for other reasons (time, news, momentum) but left unfilled orders behind.

The market tends to return to these levels to complete the auction. Unfinished Business acts as a magnet. It doesn't guarantee a reversal when price gets there, but it does pull price toward it.

This is a supplementary tool. It doesn't generate trade setups on its own. It helps you:
1. Extend profit targets
2. Avoid bad trades
3. Confirm trend direction
4. Stay aware of nearby magnets

## Step-by-Step Rules

1. Let TD Order Flow auto-detect UB. Don't manually calculate it. The software draws the dotted line automatically.
2. Note the direction: green dotted line = UB at a low (price will be pulled down to test it), red dotted line = UB at a high (price will be pulled up to test it).
3. **TP extension:** If you're in a trade and UB is in your direction, consider extending your TP to the UB level. Price is likely to reach it.
4. **SL awareness:** If UB is behind your entry (in the direction you just came from), be aware price may retrace to test it. Factor this into your SL placement.
5. **Trend confirmation:** If price is trending up and UB is above current price, the trend has a magnet pulling it higher. Confirms bullish bias.
6. **Warning against bad trades:** Do NOT enter Long when UB is below your entry. Price has a magnet pulling it down. Do NOT enter Short when UB is above your entry. Price has a magnet pulling it up.
7. Once price revisits the UB level, the dotted line disappears. The level is resolved.
8. UB that has persisted for many bars without being tested becomes a stronger magnet. The longer it remains unresolved, the more likely price will eventually test it.

## When to Use

- Extending profit targets when UB aligns with your trade direction.
- Filtering out trades where UB is working against you.
- Confirming trend direction when UB is stacked in the trend's direction.
- As a secondary check before entering any trade: scan for nearby UB levels.

## When NOT to Use

- Don't use UB as a primary entry signal. It's a supplementary tool only.
- Don't assume price will immediately test UB. It can move far away before returning. UB is a magnet, not a timer.
- Don't ignore UB just because it's far away. A distant UB can still pull price over multiple sessions.
- Don't use UB to override a strong setup. If your setup is valid but UB is slightly against you, the setup still takes priority. UB is a warning, not a veto.

## NQ-Specific Notes

- NQ frequently leaves Unfinished Business at session highs and lows, especially when price reverses sharply on news or at key levels.
- UB at NQ's overnight high or low is particularly significant. The day session often tests these levels to resolve the unfinished auction.
- When NQ has UB above and below current price, it's in a "magnetic range." Price will oscillate between the two UB levels until one is resolved.
- NQ's fast moves (news spikes, open range breaks) create UB frequently. Check for UB after any sharp directional move.
- UB combined with a Multiple Node or stacked imbalance at the same price creates a very high-conviction target level. Price is pulled there by both the UB magnet and the institutional S/R zone.
