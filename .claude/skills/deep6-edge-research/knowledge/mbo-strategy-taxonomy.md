# MBO Strategy Taxonomy — Complete Institutional Reference

Every known order manipulation pattern, institutional execution signature, and
microstructure phenomenon detectable from Market-by-Order data. This is the
adversarial map of the NQ futures order book.

---

## PART I: ORDER MANIPULATION STRATEGIES

### 1. SPOOFING

**Definition**: Placing large visible orders with no intent to fill, to create
false impression of supply/demand, then cancelling before execution.

**MBO Signature**:
- `action=A` (add): Large order appears, size >> surrounding level average (>5×)
- `life_ms < 5000`: Order cancelled within 5 seconds
- `action=C` (cancel): No `action=T` (trade) at that price during order's life
- Frequently coincides with opposite-side aggression during the spoof window
- `exchange_order_id` lifecycle: ADD → CANCEL, zero fills

**Variants**:
- **Single-sided spoof**: One large bid to push price up, then sell aggressively
- **Oscillating spoof**: Alternating bid/ask spoofs to create artificial volatility
- **Cross-market spoof**: Spoof ES to move NQ, trade NQ
- **Layered spoof**: Multiple orders at different prices, all cancelled together
- **Momentum spoof**: Spoof in direction of existing momentum to accelerate it

**Detection algorithm**:
```
for each order_id in lifecycle_tracker:
    if order.size > 5 * avg_surrounding_size:
        if order.life_ms < 5000:
            if order.fill_ratio < 0.05:  # less than 5% filled
                if price_moved_against_order_side during order.life:
                    SPOOF_DETECTED(confidence=high)
```

**Counter-strategy**: Fade the spoof. When large order appears and opposite-side
aggression begins, the spoof is about to be pulled. Enter in direction of aggression.

**Academic basis**: Cartea & Jaimungal (2020) "Spoofing and Price Manipulation
in Order-Driven Markets" — formal model of optimal spoofing and detection.
Eisler, Bouchaud & Kockelkoren (2012) — cancellation impact ≈ market order impact.

**CFTC enforcement**: Navinder Singh Sarao (2015) — spoofed E-mini S&P 500 for
years, contributed to 2010 Flash Crash. Used layered spoofing with automated
cancellation. Fined $38.6M.

---

### 2. LAYERING

**Definition**: Placing multiple orders at sequential price levels on one side
to create artificial depth, then cancelling as price approaches.

**MBO Signature**:
- 3+ contiguous price levels with oversized resting orders (>5× avg), same side
- Orders placed within short time window (coordinated)
- Few orders per level (1-4 orders, suggesting single participant)
- Systematic cancellation as price approaches (within 2-3 ticks)
- `depth_order_priority` shows orders placed in rapid succession

**Variants**:
- **Static layering**: Fixed levels, cancelled when approached
- **Dynamic layering**: Levels shift to maintain distance from touch
- **Asymmetric layering**: Heavy on one side to push price toward other side
- **Sandwich layering**: Layers on both sides to trap price in range

**Detection algorithm**:
```
for each price_level_group in book:
    if n_consecutive_oversized_levels >= 3:
        if n_orders_per_level <= 4:  # few orders = coordinated
            if all_same_side:
                if cancel_rate_on_approach > 0.80:
                    LAYERING_DETECTED
```

**Counter-strategy**: When layering detected, expect price to move AWAY from
the layered side. The layers are fake resistance/support.

---

### 3. MOMENTUM IGNITION

**Definition**: Triggering a cascade of stop orders and momentum algorithms
by creating artificial price movement, then reversing.

**MBO Signature**:
- Rapid aggressive orders through multiple price levels (sweep)
- Unusually high trade rate in short window (Hawkes branching ratio → 1.0)
- Price moves beyond obvious stop clusters (prior high/low, round numbers)
- Immediate reversal after sweep completes
- Aggressor dominance > 90% during ignition window

**Variants**:
- **Stop sweep ignition**: Target obvious stop clusters, reverse after triggering
- **Breakout ignition**: Fake breakout of key level, reverse when momentum traders enter
- **News ignition**: Amplify news-driven move beyond fair value, fade the overshoot

**Detection**:
- Hawkes process branching ratio > 0.85 (endogenous cascade, not organic)
- Price velocity > 3σ of normal
- Immediate delta reversal after sweep
- Volume spike without sustained follow-through

---

### 4. QUOTE STUFFING

**Definition**: Flooding the market with rapid add/cancel cycles to slow down
competitors' systems and create latency arbitrage opportunities.

**MBO Signature**:
- Burst of `action=A` followed immediately by `action=C` (< 1ms)
- No fills during burst
- Typically 1-lot orders (minimal capital at risk)
- Concentrated at specific price levels
- Correlated with HFT activity windows

**Detection**:
- Event rate > 10× normal in 100ms window
- Cancel rate > 99% in burst
- Order lifetime < 1ms
- No price impact from burst

**Note**: This is HFT noise, not a tradeable signal. Filter it out.

---

### 5. PINGING / PROBING

**Definition**: Sending small orders to detect hidden liquidity (dark pools,
icebergs, reserve orders) before committing larger size.

**MBO Signature**:
- Repeated small orders (1-5 lots) at same price level
- Fills at price where no visible order exists (hidden liquidity confirmed)
- Followed by larger order in same direction
- `action=T` at price with no corresponding `action=A` in recent history

**Detection**:
- Repeated fills at price with no visible resting order
- Small size, rapid succession
- Followed by size escalation

**Counter-strategy**: When pinging detected at a level, that level has hidden
institutional size. Trade with the hidden liquidity.

---

### 6. ICEBERG ORDERS

**Definition**: Large orders with only a small visible "tip" displayed, with
hidden reserve that automatically refreshes as fills occur.

**MBO Signature**:
- `traded_cum` at level >> `peak_visible_size` (ratio ≥ 3×)
- Repeated `action=A` events at same price after fills (refresh pattern)
- Level holds despite sustained aggression
- `exchange_order_id` changes on each refresh (new order ID per slice)
- `depth_order_priority` resets on each refresh

**Zotikov (2019) detection**:
```
HVr = traded_cum / peak_visible_size
if HVr >= 2.0 AND n_refreshes >= 2:
    ICEBERG_DETECTED(confidence = min(HVr/5, 1.0))
```

**Variants**:
- **Native iceberg**: Exchange-supported reserve order (CME supports this)
- **Synthetic iceberg**: Manually refreshed by algorithm
- **Adaptive iceberg**: Adjusts visible size based on market conditions

**Counter-strategy**: Trade WITH the iceberg. It represents institutional
conviction at that level. The level will hold until the iceberg is exhausted.

---

### 7. STOP HUNTING

**Definition**: Deliberately moving price to trigger stop-loss orders clustered
at obvious levels, then reversing to profit from the liquidity.

**MBO Signature**:
- Price approaches prior session high/low, round number, or equal highs/lows
- Aggressive sweep through the level (stop triggers)
- Immediate reversal after sweep
- Volume spike at the sweep level
- Delta reversal: aggressive buying into prior high → reversal

**Stop cluster locations** (in order of reliability):
1. Prior day high/low
2. Prior week high/low
3. Round numbers (21000, 21500, 22000 for NQ)
4. Equal highs/lows (double top/bottom)
5. Value area high/low
6. Opening range high/low

**Detection**:
- Price within 2 ticks of known stop cluster
- Aggressive sweep through level
- Immediate delta reversal after sweep
- Volume > 2× average at sweep level

---

### 8. WASH TRADING

**Definition**: Simultaneous buy and sell orders by same participant to create
artificial volume and price movement.

**MBO Signature**:
- Matching buy/sell orders at same price, same time
- `exchange_order_id` patterns suggesting same participant
- Volume without price impact
- Circular order flow

**Note**: Rare in regulated futures markets (CME surveillance). More common
in crypto. Detectable via order ID correlation analysis.

---

### 9. MARKING THE CLOSE / OPEN

**Definition**: Placing orders near session close/open to influence settlement
prices, often to benefit options positions.

**MBO Signature**:
- Unusual order flow in final 5 minutes of session
- Large orders at specific price levels (options strikes)
- Correlated with options expiry dates
- Reversal immediately after close

**Detection**:
- Time filter: last 5 minutes of RTH
- Unusual size relative to session average
- Price proximity to round numbers / options strikes

---

## PART II: INSTITUTIONAL EXECUTION SIGNATURES

### 10. VWAP EXECUTION

**Definition**: Algorithm that executes over the day proportional to volume,
targeting the volume-weighted average price.

**MBO Signature**:
- Consistent participation rate (% of volume) throughout session
- Accelerates during high-volume periods (open, close)
- Decelerates during low-volume periods (lunch)
- Orders sized proportional to current volume rate
- Rarely aggressive — mostly passive limit orders

**Detection**:
- Consistent order flow rate correlated with volume
- Passive order placement (limit orders at or inside spread)
- Predictable acceleration at open/close

**Counter-strategy**: VWAP algos are predictable. Front-run their acceleration
at open/close. They MUST buy/sell regardless of price.

---

### 11. TWAP EXECUTION

**Definition**: Time-weighted execution — equal slices over time regardless of volume.

**MBO Signature**:
- Regular order intervals (every N seconds)
- Consistent order size
- Ignores volume (unlike VWAP)
- More mechanical/predictable than VWAP

**Detection**:
- Regular time intervals between orders
- Consistent size
- No correlation with volume

---

### 12. IMPLEMENTATION SHORTFALL (IS) / ARRIVAL PRICE

**Definition**: Minimize slippage from decision price. More aggressive when
price moves away, more passive when price moves toward target.

**MBO Signature**:
- Urgency increases as price moves away from entry
- Switches from passive to aggressive as time passes
- Larger orders when spread is tight
- Reduces participation when spread widens

**Detection**:
- Increasing aggression over time
- Correlation between order aggression and price movement away from entry

---

### 13. DARK POOL INTERACTION

**Definition**: Large institutional orders executed off-exchange, appearing
as prints at mid-price with no visible order book interaction.

**MBO Signature**:
- Trades at mid-price with no corresponding visible order
- Large size (>100 lots for NQ)
- No price impact despite size
- Appears as `action=T` with `side=N` (no aggressor)

**Detection**:
- Trade at mid with no visible order
- Size >> typical trade size
- No price impact

**Counter-strategy**: Dark pool prints at key levels confirm institutional
interest. Trade with the dark pool direction.

---

## PART III: MICROSTRUCTURE PHENOMENA

### 14. ADVERSE SELECTION

**Definition**: Market makers lose money to informed traders. The spread
compensates for this risk.

**Measurement**:
- **Roll measure**: `Cov(ΔP_t, ΔP_{t-1})` — negative covariance = bid-ask bounce
- **Kyle's lambda**: `λ = ΔP / Q` — price impact per unit of order flow
- **Hasbrouck (1991)**: VAR decomposition of price into permanent + transient components
- **Glosten-Milgrom**: Spread = 2 × adverse selection cost

**NQ application**:
- High λ periods = informed trading (news, macro events)
- Low λ periods = noise trading (lunch, thin sessions)
- Trade WITH informed flow, AGAINST noise flow

---

### 15. HAWKES SELF-EXCITATION

**Definition**: Order arrivals trigger more order arrivals — endogenous cascade.

**Model**: `λ(t) = μ + Σ α·exp(-β·(t-t_i))` for past events t_i

**Key parameter**: Branching ratio `n = α/β`
- `n < 1`: Stable, exogenous-driven market
- `n → 1`: Critical state, endogenous cascade imminent
- `n > 1`: Explosive, flash crash territory

**NQ application**:
- Estimate branching ratio in real-time from recent order flow
- High branching ratio = momentum ignition risk
- Low branching ratio = mean-reversion opportunity

**Bacry, Mastromatteo & Muzy (2015)**: 70-85% of trades in liquid markets
are triggered by prior trades (endogenous), not external information.

---

### 16. QUEUE POSITION AND PRIORITY

**Definition**: Orders at same price compete by time priority. Queue position
determines fill probability.

**MBO fields**: `depth_order_priority` — lower = earlier in queue = higher priority

**Key insights**:
- Orders at front of queue: high fill probability, low adverse selection
- Orders at back of queue: low fill probability, high adverse selection
- Queue depletion rate predicts time-to-fill
- Large orders at front of queue = institutional conviction

**Detection**:
- Track `depth_order_priority` for each `exchange_order_id`
- Queue depletion rate = (fills per second) / (total queue size)
- Time-to-fill estimate = remaining_queue / depletion_rate

---

### 17. PRICE IMPACT AND MARKET DEPTH

**Definition**: How much does a trade of size Q move the price?

**Models**:
- **Linear**: `ΔP = λ·Q` (Kyle 1985)
- **Square root**: `ΔP = σ·√(Q/V)` (Almgren et al. 2005) — empirically better
- **Transient impact**: Impact decays after trade (Bouchaud et al. 2004)

**NQ application**:
- Estimate λ from recent trade history
- High λ = thin book, large moves per trade
- Low λ = deep book, small moves per trade
- Use λ to size positions: larger position when λ is low

---

### 18. ORDER FLOW IMBALANCE (OFI)

**Definition**: Net signed order flow at the best bid/ask.

**Formula** (Cont, Kukanov & Stoikov 2014):
```
OFI_t = (ΔQ_ask_t - ΔQ_bid_t) / (ΔQ_ask_t + ΔQ_bid_t)
```
where ΔQ = change in quantity at best price

**Predictive power**: OFI at depth 1 predicts next mid-price move with
55-65% accuracy at 1-second horizon (Cont et al. 2014).

**Multi-level OFI**: Extend to depth 5, 10 for stronger signal.

**NQ application**:
- Compute OFI at depth 1, 5, 10 every 100ms
- OFI > 0.5 = buying pressure → bullish
- OFI < -0.5 = selling pressure → bearish
- OFI divergence from price = reversal signal

---

### 19. VPIN (Volume-Synchronized Probability of Informed Trading)

**Definition**: Probability that a given trade is from an informed trader,
measured in volume time (not clock time).

**Formula** (Easley, López de Prado & O'Hara 2012):
```
VPIN = |V_buy - V_sell| / V_total
```
computed over volume buckets of size V_bucket

**Interpretation**:
- VPIN → 0: Balanced flow, uninformed trading
- VPIN → 1: One-sided flow, informed trading
- VPIN spike precedes volatility spike (Flash Crash predictor)

**NQ application**:
- High VPIN = reduce position size (adverse selection risk)
- Low VPIN = increase position size (noise trading, mean-reversion)
- VPIN spike = potential flash crash / large move incoming

**Controversy**: Andersen & Bondarenko (2014) dispute VPIN's predictive power.
Use as regime indicator, not threshold trigger.

---

### 20. MICROPRICE

**Definition**: Quantity-weighted mid-price, better predictor of next trade
price than simple mid.

**Formula**:
```
microprice = ask_price × (bid_size / (bid_size + ask_size)) +
             bid_price × (ask_size / (bid_size + ask_size))
```

**Interpretation**:
- microprice > mid: More size on bid → price likely to move up
- microprice < mid: More size on ask → price likely to move down
- microprice = mid: Balanced book

**NQ application**: Use microprice instead of mid for all signal calculations.
Reduces noise by 15-20% in empirical tests.

---

## PART IV: CROSS-MARKET PHENOMENA

### 21. ES-NQ LEAD-LAG

**Definition**: E-mini S&P 500 (ES) and NQ are correlated but one leads the other.

**Empirical findings**:
- ES typically leads NQ by 50-200ms in normal conditions
- NQ leads ES during tech-driven moves
- Lead-lag reverses during macro events (ES leads on economic data)

**Detection**:
- Cross-correlation of order flow between ES and NQ
- When ES OFI leads NQ OFI by 100ms → trade NQ in ES direction
- When NQ OFI leads ES OFI → tech-specific move, trade NQ

---

### 22. OPTIONS-FUTURES INTERACTION

**Definition**: Options market makers hedge delta by trading futures, creating
predictable order flow.

**Key flows**:
- **Delta hedging**: Options MM buys/sells NQ to maintain delta-neutral
- **Gamma scalping**: MM buys low vol, sells high vol, hedges continuously
- **Charm flow**: As time passes, delta of OTM options decays → hedges unwind
- **Vanna flow**: As vol changes, delta changes → hedges adjust

**GEX (Gamma Exposure)**:
- Positive GEX: MM is long gamma → they sell rallies, buy dips (stabilizing)
- Negative GEX: MM is short gamma → they buy rallies, sell dips (destabilizing)
- Zero gamma: Transition zone, high volatility

**Detection**:
- Monitor FlashAlpha GEX data
- Positive GEX + price at call wall → expect rejection
- Negative GEX → expect momentum continuation

---

## PART V: DETECTION PRIORITY MATRIX

For NQ futures, ranked by reliability and actionability:

| Rank | Pattern | Reliability | Actionability | MBO Required |
|------|---------|-------------|---------------|--------------|
| 1 | Iceberg at key level | HIGH | HIGH | YES |
| 2 | Absorption (multi-bar) | HIGH | HIGH | NO (OHLCV ok) |
| 3 | Spoof + opposite aggression | HIGH | HIGH | YES |
| 4 | Stop sweep + reversal | HIGH | HIGH | NO |
| 5 | Dark pool print at level | MEDIUM-HIGH | HIGH | YES |
| 6 | OFI divergence | MEDIUM-HIGH | MEDIUM | YES |
| 7 | VWAP algo signature | MEDIUM | MEDIUM | NO |
| 8 | Layering detection | MEDIUM | MEDIUM | YES |
| 9 | Momentum ignition | MEDIUM | HIGH | YES |
| 10 | Queue depletion | MEDIUM | MEDIUM | YES |
| 11 | VPIN spike | MEDIUM | LOW | NO |
| 12 | Hawkes branching ratio | LOW-MEDIUM | LOW | YES |

---

## PART VI: THE ADVERSARIAL FRAMEWORK

The NQ order book is a zero-sum adversarial game. Every participant is either:

**A. Informed traders** (know something others don't):
- Institutional funds with fundamental research
- HFT firms with speed advantage
- Options market makers with vol surface knowledge
- Macro traders with economic model edge

**B. Uninformed traders** (noise):
- Retail traders
- Systematic trend followers (at wrong timescale)
- Hedgers (not profit-seeking)

**C. Market makers** (provide liquidity, earn spread):
- CME designated market makers
- HFT market makers (Virtu, Citadel Securities)

**The edge**: Detect when informed traders are active (high VPIN, large iceberg,
spoof + aggression) and trade WITH them. Detect when noise traders are active
(low VPIN, random order flow) and fade them.

**The meta-edge**: The system that can simultaneously track all 22 patterns
above, weight them by current regime, and synthesize a probability-weighted
directional assessment — that system cannot be beaten by any human trader
processing the same information sequentially.
