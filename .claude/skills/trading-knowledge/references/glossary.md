# Trading Glossary — DEEP6 Quick Reference

Last verified: 2026-05-12

Alphabetical reference for all terminology used across the DEEP6 knowledge base.
Each entry includes a category tag and a cross-reference to the domain file where the concept is explained in depth.

Category tags: [Microstructure] [Auction] [Order Flow] [GEX] [DEEP6] [Market Internal]

---

## Absorption [Microstructure]

**Definition**: Passive limit orders on one side of the market absorb aggressive market orders from the other side without allowing price to advance. The absorbing side is actively defending a price level. Distinct from exhaustion: absorption is an active defense; exhaustion is the collapse of the aggressor.

---

## ADD (Advance/Decline) [Market Internal]

**Definition**: The net number of advancing issues minus declining issues on an exchange. Used as a breadth indicator to confirm or contradict price moves in index futures like NQ. Divergence between ADD and NQ price is a warning sign.

---

## Ask Fade [Microstructure]

**Definition**: A condition where ask volume at the current bar's high is less than 60% of the prior bar's ask volume at its high. Signals waning buying pressure across bars — buyers showing up with less conviction at the highs. Detected by EXH-06.

---

## Auction Theory [Auction]

**Definition**: The framework that treats price as an advertising mechanism and the market as a continuous two-sided auction. Price explores until it finds acceptance (volume) or rejection (no volume). Developed by J. Peter Steidlmayer at the CBOT; popularized by James Dalton.

---

## Bid Fade [Microstructure]

**Definition**: A condition where bid volume at the current bar's low is less than 60% of the prior bar's bid volume at its low. Signals waning selling pressure — sellers weakening at the lows. The bullish mirror of Ask Fade. Detected by EXH-06.

---

## Call Wall [GEX]

**Definition**: The strike price with the largest call gamma times open interest. Dealers who sold calls must sell the underlying as price approaches from below, creating structural resistance. In positive GEX regime, a reliable ceiling. Can be broken in negative GEX, triggering a gamma squeeze upward.

---

## CVD (Cumulative Volume Delta) [Order Flow]

**Definition**: The running sum of bar deltas from session open. Tracks net directional pressure of aggressive traders over the entire session. A rising CVD confirms bullish price action; a falling CVD confirms bearish. Divergence between CVD and price is the highest-alpha delta signal in DEEP6.

---

## Delta [Order Flow]

**Definition**: The net difference between aggressive buying and aggressive selling within a single bar: `bar_delta = ask_volume - bid_volume`. Positive delta means buyers were more aggressive; negative means sellers dominated. Delta measures only the aggressor side, not passive orders.

---

## Delta Divergence [Order Flow]

**Definition**: Price makes a new N-bar high but CVD fails to confirm (or price makes a new low but CVD holds). Labeled "highest alpha" in the DEEP6 delta engine. Indicates the aggressive side is losing steam even as price extends. Requires structural level confluence for highest reliability.

---

## Delta Gate [DEEP6]

**Definition**: A universal filter (EXH-07) applied to exhaustion signals EXH-02 through EXH-06. Passes only when cumulative delta is fading relative to price direction. A bullish bar with negative delta passes the gate; a bullish bar with positive delta does not. EXH-01 (Zero Print) is exempt.

---

## DOM (Depth of Market) [Microstructure]

**Definition**: The full limit order book showing all resting bid and ask orders at every price level. Rithmic via async-rithmic provides 40+ levels per side. The DOM reveals institutional intent that the tape alone cannot show — large resting orders signal support or resistance before price arrives.

---

## Effort vs Result [Microstructure]

**Definition**: A Wyckoff concept: high volume (effort) with no price movement (no result) indicates absorption throughout the bar body. Detected by ABS-04 when bar volume exceeds 1.5x the volume EMA and bar range is less than 30% of ATR. The mismatch between effort and result is the signal.

---

## Excess [Auction]

**Definition**: A sharp rejection of a price level marking the end of one auction and the start of another. Types include buying tails (2+ single TPOs at session low in first 2 periods) and selling tails (mirror at high). Excess signals the market found no business at that price and reversed aggressively.

---

## Exhaustion [Microstructure]

**Definition**: When aggressive traders run out of ammunition. Unlike absorption (passive side defending), exhaustion means the aggressor simply has no more fuel. Price extends in one direction, then aggressive flow collapses. An earlier warning than absorption but a weaker signal. Often precedes absorption.

---

## Fat Print [Microstructure]

**Definition**: A single price level within a bar with volume greater than 2x the bar's average level volume. Marks strong acceptance — the market spent significant time and volume at this price. Fat prints become future support or resistance. Detected by EXH-04 (direction neutral).

---

## Finished Auction [Auction]

**Definition**: A bar extreme where zero bid volume exists at the high (buyers exhausted) or zero ask volume at the low (sellers exhausted). The auction is complete — no unfinished business. Stronger reversal signal than unfinished business. Detected by AUCT-02.

---

## Footprint Chart [Microstructure]

**Definition**: A chart type showing bid volume and ask volume at every price level within each bar. Where a standard candlestick shows only OHLCV, a footprint reveals the full internal structure: how much buying and selling happened at each price tick. The raw data layer for all DEEP6 signals.

---

## Gamma Flip [GEX]

**Definition**: The price level where net GEX crosses zero. Above it: positive GEX (dampening, mean-reverting). Below it: negative GEX (amplifying, trending). The most important GEX level for regime classification. Crossing it changes the entire market dynamic. Also called "zero gamma."

---

## GEX (Gamma Exposure) [GEX]

**Definition**: The total gamma held by options market makers across all strikes and expirations. Quantifies how much dealers must buy or sell the underlying to stay delta-neutral as price moves. Positive GEX dampens volatility; negative GEX amplifies it. DEEP6 uses QQQ options as a proxy for NQ.

---

## HVL (High Volatility Level) [GEX]

**Definition**: The strike with the highest absolute net GEX value. Where dealer hedging activity is most intense. Price can move rapidly through HVL in either direction. Distinct from the gamma flip (where GEX = 0) and from call/put walls (which are directional).

---

## HVN (High Volume Node) [Auction]

**Definition**: A price cluster with above-average volume in the volume profile. Strong support or resistance — price tends to slow or reverse at HVNs. The market found acceptance here; participants are likely to defend these levels again.

---

## Iceberg Order [Microstructure]

**Definition**: A large limit order that displays only a small visible slice while hiding the bulk. When the visible slice fills, the exchange replenishes it automatically. Detection signature: a market order clears visible size, then a new identical slice appears within 50ms at the same price. Absorption IS iceberg execution against aggressive takers.

---

## Imbalance [Order Flow]

**Definition**: A condition where ask volume at price P is 3x or more the bid volume at price P-1 (buy imbalance), or bid at P is 3x or more the ask at P+1 (sell imbalance). The diagonal comparison algorithm is the standard footprint imbalance methodology. Identifies price levels where one side dominated.

---

## Initial Balance (IB) [Auction]

**Definition**: The price range of the first 60 minutes of RTH (9:30-10:30 ET for NQ, periods A+B). Defines the initial auction range. IB width classifies the day: narrow IB signals trend-day potential; wide IB signals normal or responsive day. Range extension beyond IB signals new timeframe participation.

---

## Initiative Trade [Auction]

**Definition**: Buying above value or selling below value — the trader is initiating new price discovery. Appropriate on trend days, open-drive opens, and successful range extensions. The opposite of responsive trade. Requires confirmation via stacked imbalances and delta expansion.

---

## Kronos E10 [DEEP6]

**Definition**: The directional bias signal from the Kronos foundation model (Kronos-small, 24.7M parameters). Trained on financial K-lines from 45+ exchanges. Provides a predicted next-bar close relative to current close. Used as a bias filter in DEEP6 trade entries — bearish E10 blocks long entries on open-drive setups.

---

## Kyle's Lambda [Microstructure]

**Definition**: The price change per unit of signed order flow. Measures how much price moves per unit of buying or selling pressure. High lambda means illiquid (price moves a lot per trade); low lambda means liquid. Lambda falling at a level indicates absorption is working; lambda rising indicates toxic flow breaking through.

---

## Level (NQ Price Level) [DEEP6]

**Definition**: A structural price reference used to contextualize footprint signals. Tiers: T1 (weekly H/L, gamma flip, largest call/put wall), T2 (prior-day H/L, VPOC/VAH/VAL), T3 (IB H/L, overnight H/L, VWAP), T4 (developing VPOC/VAH/VAL, intraday LVN). Signals at A-grade levels (2+ tiers aligned) get 1.5x weight.

---

## Liquidity [Microstructure]

**Definition**: The availability of resting orders at a price level. High liquidity means large resting size — price moves slowly through it. Low liquidity (LVN) means price moves fast. Liquidity is not static: it can be spoofed (fake) or genuine (iceberg). DEEP6 distinguishes via order lifetime and cancel rate.

---

## LVN (Low Volume Node) [Auction]

**Definition**: A price cluster with below-average volume in the volume profile. Price tends to move through LVNs quickly — a "fast lane." Do not enter countertrend inside an LVN; wait for resolution at the next HVN. The footprint equivalent is a volume void (AUCT-04).

---

## MAD Levels [DEEP6]

**Definition**: Multi-timeframe Auction Derived levels — the set of T1 through T4 structural references mapped pre-market. Includes weekly H/L, prior-day VPOC/VAH/VAL, gamma walls, IB H/L, and developing session levels. The context layer that determines WHERE footprint signals should be trusted.

---

## Market Profile [Auction]

**Definition**: A charting method developed by J. Peter Steidlmayer that displays price as a histogram of TPOs (Time-Price Opportunities) per 30-minute period. A bell-shaped profile indicates balance; an elongated profile indicates imbalance. Provides the WHERE context for footprint triggers.

---

## MBO (Market-by-Order) [Order Flow]

**Definition**: Level 3 market data showing every individual order event (add, modify, cancel) at every price level with nanosecond timestamps. Provides full order book reconstructibility. Used by DEEP6 via Databento for historical backtesting. Enables iceberg detection and spoof detection that L2 data cannot support.

---

## Naked POC (nPOC) [Auction]

**Definition**: A prior-session VPOC that has never been revisited since it was formed. Acts as a magnet — approximately 80% get retested per Dalton. When price drifts toward an nPOC, it is a high-probability target. Once price revisits and accepts the level, it is no longer naked.

---

## Negative GEX [GEX]

**Definition**: A regime where spot price is below the gamma flip level. Dealers are net short gamma and their hedging amplifies moves: price falls, dealers sell more; price rises, dealers buy more. Creates trending, high-volatility conditions. DEEP6 boosts momentum signals (1.3x) and suppresses absorption signals (0.7x) in this regime.

---

## OTF (One-Time Framing) [Auction]

**Definition**: Three or more consecutive 30-minute bars without violating the prior bar's opposite extreme. Indicates a trend in progress — the market is making consistent directional progress. OTF break (a bar violates the prior boundary) signals the end of the trend leg.

---

## POC (Point of Control) [Auction]

**Definition**: The price level with the highest traded volume in a session or period. Represents the "fairest price" — where the most business was done. Acts as a magnet for price. VPOC (volume-based POC) is more actionable than TPO POC for HFT-dominated markets.

---

## Poor High / Poor Low [Auction]

**Definition**: A session extreme with very low volume at the bar high or low (less than 30% of average level volume). Indicates the auction was incomplete — price reached the extreme but barely traded there. Poor highs and lows are statistically revisited and broken. Detected by AUCT-03.

---

## Positive GEX [GEX]

**Definition**: A regime where spot price is above the gamma flip level. Dealers are net long gamma and their hedging dampens moves: price rises, dealers sell; price falls, dealers buy. Creates mean-reverting, range-bound conditions. DEEP6 boosts absorption signals (1.3x) and suppresses momentum signals (0.8x) in this regime.

---

## Put Wall [GEX]

**Definition**: The strike price with the largest put gamma times open interest. Dealers who sold puts must buy the underlying as price approaches from above, creating structural support. In positive GEX regime, a reliable floor. Breaking below the put wall triggers aggressive dealer selling (gamma squeeze downward).

---

## Regime [DEEP6]

**Definition**: The current market state that determines which signals are trusted and which are suppressed. Two primary regime axes: (1) GEX regime (positive dampening vs negative amplifying), and (2) Auction state (balanced vs breakout vs breakdown). Regime determines the trade playbook.

---

## Responsive Trade [Auction]

**Definition**: Buying below value or selling above value — fading the move back toward the value area. The dominant strategy on balance days. Appropriate when the value area is unchanged or overlapping from the prior day and no range extension has occurred.

---

## Reversal [DEEP6]

**Definition**: A price move that changes direction after a signal cluster. In DEEP6, a high-conviction reversal requires absorption or exhaustion at a structural level, confirmed by delta divergence and GEX regime alignment. TYPE_A setups are the highest-conviction reversals.

---

## Rithmic [DEEP6]

**Definition**: The market data and order routing infrastructure used by DEEP6. Provides Level 2 DOM data (40+ levels per side), tick data, and order execution via the R|Protocol WebSocket + protobuf interface. Accessed via the `async-rithmic` Python library (v1.5.9). Zero additional cost beyond existing broker account.

---

## RTH (Regular Trading Hours) [Market Internal]

**Definition**: The standard exchange trading session. For NQ futures: 9:30 AM to 4:15 PM ET. DEEP6 builds volume profiles and computes IB from RTH data only. Globex (overnight) session data is tracked separately as inventory context.

---

## Scalping [DEEP6]

**Definition**: Short-duration trades targeting small price moves, typically 4-8 NQ points. DEEP6's TYPE_B setups are scalp-grade. Appropriate at POC revisits, OAIR days, and bracket trading within the value area. Requires tight stops (1-2 ticks beyond the signal level).

---

## Signal Confluence [DEEP6]

**Definition**: The alignment of multiple independent signals pointing in the same direction at the same structural level. DEEP6's scorer synthesizes 44 signals into a confidence score. TYPE_A requires score >= 80 with signals from multiple families (absorption, delta, auction, GEX). Confluence is the core thesis: no single signal is sufficient.

---

## Spoofing [Microstructure]

**Definition**: Placement of large limit orders with no intent to fill, designed to create a false impression of supply or demand. Spoof orders have very short lifetimes (< 500ms), cancel rates > 90%, and vanish before execution. DEEP6's SpoofSuppressor (MS-08) vetoes absorption signals when spoof conditions are detected.

---

## Stacked Imbalances [Order Flow]

**Definition**: Three or more consecutive price levels all showing imbalances in the same direction. Three tiers: T1 (3+ levels), T2 (5+ levels), T3 (7+ levels). Represents a wall of aggressive orders — the most powerful imbalance signal. A gap tolerance of 2 ticks allows minor gaps in the stack. Detected by IMB-03.

---

## Stopping Volume [Microstructure]

**Definition**: A bar where the Point of Control falls in the wick rather than the body AND total volume exceeds 2x the volume EMA. The POC in the wick means the most-traded price was in the rejected zone — a strong sign the market tested a level, found heavy two-sided activity, and reversed. Detected by ABS-03.

---

## TICK [Market Internal]

**Definition**: The NYSE TICK index — the number of NYSE stocks on an uptick minus those on a downtick at any moment. Used as a market breadth indicator for NQ futures. Extreme TICK readings (+1000 or -1000) signal short-term exhaustion of the broad market.

---

## Thin Print [Microstructure]

**Definition**: A price level within a bar body with volume less than 5% of the bar's maximum level volume. Three or more thin prints confirm a fast, uncontested move through those levels. A momentum confirmation signal, not a reversal signal. Detected by EXH-03.

---

## Time & Sales [Order Flow]

**Definition**: The raw trade tape — every individual transaction with price, size, and aggressor side. Institutional traders leave footprints in T&S via large prints (50+ contracts), sweeps (rapid same-price fills), and iceberg patterns (repeated same-size prints). DEEP6 captures T&S via the Rithmic tick feed.

---

## TPO (Time Price Opportunity) [Auction]

**Definition**: One letter on a 30-minute Market Profile chart — the opportunity to transact at a specific price during a specific period. The profile is a histogram of TPOs per price over a session. A bell-shaped TPO distribution indicates balance; an elongated distribution indicates imbalance.

---

## Trap [DEEP6]

**Definition**: A price move that lures participants into a position, then reverses against them. DEEP6's TRAP signal family (bits 37-41) detects trapped traders via inverse imbalances, delta traps, false breakouts, high-volume rejections, and CVD traps. Trapped traders create predictable directional pressure as they exit.

---

## Trapped Traders [Order Flow]

**Definition**: Participants caught on the wrong side of the market after committing capital. When trapped traders are forced to exit, they create predictable directional pressure in the direction of the trap. The highest win-rate DEEP6 signal (IMB-05, 80-85%) detects trapped longs and shorts via inverse imbalances.

---

## TYPE_A Setup [DEEP6]

**Definition**: The highest-conviction trade tier in DEEP6. Requires a confidence score >= 80 with signals from multiple families, structural level confluence, and no GEX direction conflict. Executes with full position size. Typically involves absorption or exhaustion at a T1/T2 level with delta confirmation and GEX alignment.

---

## TYPE_B Setup [DEEP6]

**Definition**: A moderate-conviction trade tier in DEEP6. Score threshold below TYPE_A. Executes with reduced position size. Appropriate for scalp entries at POC revisits, bracket trades, and setups with fewer confirming signals. GEX direction conflict blocks TYPE_B (maximum tier becomes TYPE_C).

---

## Unfinished Business [Auction]

**Definition**: A bar extreme where non-zero bid volume exists at the bar high, or non-zero ask volume at the bar low. The auction was not finished — buyers or sellers were still present when price reached its extreme. Price will return to complete the auction. Tracked across bars as a target. Detected by AUCT-01.

---

## Unusual Options Activity (UOA) [GEX]

**Definition**: Options volume significantly above average open interest at a specific strike, often preceding large moves. For NQ/QQQ: large call sweeps above current price signal bullish informed activity; large put sweeps below signal bearish. Sweeps (multi-exchange simultaneous fills) are more directionally informative than blocks.

---

## VAH (Value Area High) [Auction]

**Definition**: The upper boundary of the price range containing approximately 70% of session volume. Acts as resistance when approached from below (responsive trade: fade back to POC) and as support when price is above it (initiative break: continuation). ABS-07 gives absorption signals at VAH a strength bonus.

---

## VAL (Value Area Low) [Auction]

**Definition**: The lower boundary of the price range containing approximately 70% of session volume. Acts as support when approached from above (responsive trade: fade back to POC) and as resistance when price is below it (initiative break: continuation). Mirror of VAH.

---

## Value Area [Auction]

**Definition**: The price range containing approximately 70% of total session volume (one standard deviation around POC). Bounded by VAH and VAL. Represents "accepted value" — where the market agreed to do business. Value migration (VA shifting higher or lower day-over-day) is the primary Market Profile bias signal.

---

## VOLD [Market Internal]

**Definition**: NYSE volume delta — the difference between uptick volume and downtick volume on the NYSE. A broader measure than TICK (which counts issues, not volume). Used alongside TICK and ADD to assess broad market participation in NQ moves.

---

## Volume Profile [Order Flow]

**Definition**: The distribution of traded volume across price levels over a session or period. Answers "where did the most trading happen?" rather than "when?" Key components: POC, Value Area (VAH/VAL), HVN, and LVN. The foundation for all structural level identification in DEEP6.

---

## Volume Void [Auction]

**Definition**: A zone within a bar containing multiple price levels with volume far below the bar's maximum (less than 5% of max level volume). The footprint equivalent of a Market Profile LVN. Price moves through volume voids quickly — they are "fast lanes," not support or resistance. Detected by AUCT-04.

---

## VPOC (Volume Point of Control) [Auction]

**Definition**: The volume-based Point of Control — the price level with the highest traded volume, as opposed to the TPO-based POC (most time spent). More actionable than TPO POC for HFT-dominated markets because institutions trade volume, not time. DEEP6 uses VPOC throughout.

---

## VPIN (Volume-Synchronized Probability of Informed Trading) [Microstructure]

**Definition**: A metric measuring the probability that a given trade is from an informed participant who will adversely select passive liquidity providers. Computed in volume time (fixed-volume buckets). VPIN falling at a level signals absorption by informed passive participants (level holds); VPIN rising signals informed aggressors (level breaks).

---

## Zero Print [Microstructure]

**Definition**: A price level within the bar body where both bid and ask volume are exactly zero. Price passed through so fast that no trades occurred. Zero prints are structural gaps and act as magnets — price will return to fill them. Exempt from the delta gate because they are structural facts, not delta-dependent. Detected by EXH-01.

---

*Last verified: 2026-05-12*
*Source domains: microstructure.md, auction-theory.md, order-flow.md, gex-options.md, deep6-signals.md*
*Total terms: 65*
