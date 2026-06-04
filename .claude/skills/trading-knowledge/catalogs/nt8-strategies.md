# NinjaTrader 8 Strategy Catalog — NQ / ES Index Futures

Last verified: 2026-05-12

This catalog indexes NinjaTrader 8 strategies relevant to NQ and ES index futures trading.
Sources: NinjaTrader User App Share, NT8 Marketplace/Ecosystem vendors, GitHub open-source repositories.

---

## Table of Contents

| ID | Name | Category | Price | Source |
|----|------|----------|-------|--------|
| NT8-STR-01 | OrderFlowBot | Order Flow | Free / Open Source | GitHub |
| NT8-STR-02 | TDU Auto Orderflow Footprint Trader | Order Flow | $299 | Vendor |
| NT8-STR-03 | MZpack Footprint Action Strategy | Order Flow | Subscription | Vendor |
| NT8-STR-04 | OrderFlow Hub Eisler Framework | Order Flow | $297 | Vendor |
| NT8-STR-05 | Order Flow X — Stacked Imbalance Trader | Order Flow / Volume Profile | $197 | Vendor |
| NT8-STR-06 | MZpack GhostResistance | Volume Profile / Reversal | Subscription | Vendor |
| NT8-STR-07 | Emoji Trading Order Flow Suite | Volume Profile / Order Flow | $89/mo | Vendor |
| NT8-STR-08 | Eagle Eye Peak Hours Trading NQ | Momentum | Free | User App Share |
| NT8-STR-09 | Automated Strategy for Trading NQ | Momentum | Free | User App Share |
| NT8-STR-10 | ARKO Quantum Time-Based ORB | Breakout | Free / Open Source | GitHub |
| NT8-STR-11 | Inside Bar Breakout Strategy | Breakout | Free / Open Source | GitHub |
| NT8-STR-12 | Accumulation/Distribution Range Breakout | Breakout | Free | User App Share |
| NT8-STR-13 | TDU Delta Divergence Reversal | Reversal | Code Sample (requires TDU) | Vendor Docs |
| NT8-STR-14 | Trading123 Order Flow Strategy | Reversal | $1,497 | Vendor |
| NT8-STR-15 | Beer Money (VWAP + Imbalance) | Mean Reversion | Free / Open Source | GitHub |
| NT8-STR-16 | Eagle Eye River Scalper | Scalping | Free | User App Share |
| NT8-STR-17 | LargeTrades Strategy NT8 | Scalping | Free | User App Share |
| NT8-STR-18 | ATSQuadroStrategyBase | Framework | Free / Open Source | GitHub |

---

## ORDER FLOW / FOOTPRINT STRATEGIES

---

## NT8-STR-01: OrderFlowBot
**Category**: Strategy
**Tags**: order-flow, footprint, stacked-imbalances, volumetric, semi-automated, ATM, open-source
**DEEP6 Signal(s)**: ABS-01 (absorption), IMB-03 (stacked imbalances), EXH-01 (exhaustion)
**NinjaTrader File**: https://github.com/WaleeTheRobot/order-flow-bot
**Price**: Free / Open Source

### Concept
Open-source NinjaTrader 8 strategy that trades order flow patterns using NinjaTrader's built-in volumetric data. Supports semi-automated and fully automated execution via ATM strategies. Provides access to imbalances, stacked imbalances, and value areas per bar — features not natively exposed by NT8's volumetric bars API.

### Conditions / Setup
- Requires NinjaTrader 8.1.2.1+ (C# 8 features)
- Requires NT8 Order Flow+ (volumetric bars data)
- Works on any futures instrument; best on ES/NQ with sufficient tick volume
- Any intraday timeframe; designed for footprint-style bars

### Entry / Exit Rules
- **Stacked Imbalances Strategy** (built-in example): Triggers long/short when stacked bid/ask imbalances are detected at consecutive price levels
- Supports standard and inverse order modes (inverse useful in range-bound markets)
- Users implement custom strategies by inheriting from `StrategyBase` and placing files in `Models/Strategies/Implementations`
- ATM strategy handles stop/target management

### Risk Management
- Configurable via NinjaTrader ATM strategies (bracket orders)
- Semi-auto mode recommended — bot identifies setups, trader confirms execution
- Full auto mode available but author warns against it unless strategy is proven profitable

### DEEP6 Integration
- Stacked imbalance detection maps directly to DEEP6's IMB-03 signal
- Value area tracking per bar aligns with DEEP6's auction theory framework
- Custom strategies could incorporate DEEP6 absorption/exhaustion detectors as additional filters
- Reference: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6LiquidityImbalance.cs`

### Examples / Edge Cases
- Stacked imbalance signals can become invalid if price reverses shortly after detection
- Low-volume environments produce unreliable imbalance readings
- Author explicitly notes this is a framework, not a turnkey profitable system

---

## NT8-STR-02: TDU Auto Orderflow Footprint Trader
**Category**: Strategy
**Tags**: order-flow, footprint, delta-divergence, delta-trap, exhaustion, absorption, stacked-imbalances, automated, signal-designer
**DEEP6 Signal(s)**: ABS-01 (absorption), EXH-01 (exhaustion), CR-06 (delta divergence), IMB-03 (stacked imbalances), TRAP-01 (delta trap)
**NinjaTrader File**: https://tradedevils-indicators.com/products/orderflow-footprint-trader
**Price**: $299 (one-time, includes updates)

### Concept
The most feature-rich automated order flow strategy for NinjaTrader 8. Reads real-time footprint data (delta, volume at price, POC, value area, imbalances) and places trades when configured conditions are met. Ships with 21 built-in signals plus 16 custom signal slots via a visual signal designer or C# scripting.

### Conditions / Setup
- Requires tick data feed (Rithmic, Continuum, etc.)
- Works on any bar type but uses tick data internally
- Designed for ES, NQ, CL, and other liquid futures
- Does NOT require the TDU Footprint Indicator (standalone strategy)

### Entry / Exit Rules
**21 Built-in Signals include:**
- Delta Divergence: Price and delta disagree at swing extremes
- Delta Trap: Traders caught on wrong side (heavy buying → price drops)
- Delta Reversal: Extreme intrabar delta swings (tug-of-war at turning points)
- Delta Slingshot: Delta reverses then accelerates past prior extreme
- Delta Flip: Sudden shift from positive to negative delta (or vice versa)
- Stacked Imbalances: Consecutive price levels with aggressive directional volume
- Exhaustion at swing highs/lows
- Absorption (passive limit order detection)

**Combination Modes:**
- **Any**: At least one enabled signal fires
- **All**: Every enabled signal must fire on same bar (triple/quad confirmation)
- **Many**: Configurable minimum count (e.g., 3 of 6 must confirm)

**Exits:** 6 stop loss types, 6 trailing stop types, 6 break-even types, 6 target types, scalp + runner dual-position system

### Risk Management
- Minimum volume filter: Ensures sufficient market participation per bar
- Minimum delta filter: Requires directional conviction behind each entry
- Daily profit/loss/drawdown limits
- Session and weekday filters
- 3 position sizing modes

### DEEP6 Integration
- The 21 signals overlap heavily with DEEP6's 44-signal engine — delta divergence, absorption, exhaustion, stacked imbalances, trapped traders
- TDU's 120+ order flow data points provide a benchmark for validating DEEP6 signal outputs
- DEEP6 confluence scoring could be replicated using TDU's "Many" mode (N of M confirmation)
- TDU's visual signal designer concept influenced DEEP6's modular signal architecture

---

## NT8-STR-03: MZpack Footprint Action Strategy
**Category**: Strategy
**Tags**: order-flow, footprint, delta-divergence, delta-trap, delta-slingshot, stacked-imbalances, volume-sequencing, pattern-builder
**DEEP6 Signal(s)**: CR-06 (delta divergence), TRAP-01 (delta trap), IMB-03 (stacked imbalances), ABS-01 (absorption)
**NinjaTrader File**: https://www.mzpack.pro/footprint-action-strategy-for-ninjatrader/
**Price**: Part of MZpack Strategies subscription

### Concept
Order flow strategy built on the mzFootprint indicator. Provides 10 delta and order flow signals that can be combined using AND/OR logic to form composite trading patterns. Includes volume, delta, and delta % filters applied across all bars in a signal pattern.

### Conditions / Setup
- Requires MZpack for NinjaTrader 8 (subscription)
- Auto trade and Manual modes
- Works on any intraday timeframe with volumetric data

### Entry / Exit Rules
**10 Signals:**
1. **Delta Divergence**: Price makes new extreme while delta moves opposite direction
2. **Delta Tail**: Negative delta across all levels except bottom (absorption at extreme)
3. **Delta Surge/Drop**: 4-bar momentum buildup signal
4. **Delta Flip**: 2-bar sudden delta shift (reversal)
5. **Delta Trap**: 3-bar delta reversal followed by renewed strength
6. **Delta Slingshot**: Extreme delta overrun by opposite extreme
7. **Above/Below POC**: Bar opens and closes on same side of its Point of Control
8. **Stacked Imbalances**: Multiple imbalances at consecutive price levels
9. **Volume Sequencing**: Increasing volume at multiple price levels (large trader activity)
10. **Hammer with Absorption**: Absorption detected in wick of hammer candle

**Pattern Builder:** Select X signals, require minimum Y to validate (e.g., 6 selected, 3 must confirm)

### Risk Management
- Custom ATM or NinjaTrader ATM order management
- Volume/delta/delta % filters per signal
- Time filters (specific trading hours)
- Daily loss and profit filters
- Opposite signal actions: Close, Reverse, or None

### DEEP6 Integration
- Volume Sequencing maps to DEEP6's institutional footprint detection
- Hammer with Absorption directly relates to DEEP6's absorption-at-extremes thesis
- MZpack's composite pattern builder concept validates DEEP6's confluence scoring approach
- Delta Tail is a specialized form of DEEP6's exhaustion detection

---

## NT8-STR-04: OrderFlow Hub Eisler-Style Framework
**Category**: Strategy
**Tags**: order-flow, quant, microstructure, event-impact, NQ-specific, latency-aware, academic
**DEEP6 Signal(s)**: Multiple — microstructure-based (market impact model)
**NinjaTrader File**: https://orderflow-hub.com/product/nt8-order-flow-algorithmic-framework-high-frequency-quant-strategy-c/
**Price**: $297 (one-time, full source code)

### Concept
Professional-grade C# algorithmic template for NinjaTrader 8 based on the Eisler-Bouchaud-Kockelkoren academic paper on price impact of order book events. Built for NQ 1-minute Volumetric bars. Implements an event-impact model that predicts price changes based on aggregate order flow history rather than individual events.

### Conditions / Setup
- NQ 1-minute Volumetric bars
- Optimized trading window: 9:50 AM – 11:30 AM ET (avoids initial volatility)
- 5-minute buffer resets: Flushes internal arrays/state machine periodically
- Level-II independence: Uses L1 Bid/Ask/Last + Volumetric bar aggregates only
- No `OnMarketDepth()` subscription needed

### Entry / Exit Rules
- Regime switching between large-tick and small-tick environments
- Concave, impact-based position sizing scaled to market activity proxy
- Multi-tick confirmation before signal fires (jitter-robust)
- Latency-aware order handling with strict hold times and auto expiration

### Risk Management
- **Staleness Gate**: Blocks entries if measured inter-arrival times indicate stale data
- **Jitter Gate (p95)**: Blocks entries when 95th percentile of inter-arrival time is too high (protects against feed micro-bursts)
- **Dynamic Tightening**: Auto-adjusts entry threshold and limit offsets based on real-time latency
- Hold time limits with automatic cancellation

### DEEP6 Integration
- The VAR (Vector Autoregression) approach to order flow history parallels DEEP6's multi-bar signal lookback architecture
- Jitter/latency awareness is critical for DEEP6's Python async event loop operating at 1,000+ DOM callbacks/sec
- Academic basis (Eisler et al.) provides theoretical backing for DEEP6's microstructure thesis
- Reference: `C:\Users\Tea\DEEP6\deep6\` — Python reference engine handles similar event-impact concepts

### Academic Basis
- Eisler, Bouchaud, Kockelkoren (2012), "The price impact of order book events: market orders, limit orders and cancellations"

---

## NT8-STR-05: Order Flow X — Stacked Imbalance Trader
**Category**: Strategy
**Tags**: order-flow, stacked-imbalances, automated, plug-and-play, ATM, NQ, ES
**DEEP6 Signal(s)**: IMB-03 (stacked imbalances)
**NinjaTrader File**: https://www.ninjavendors.com/advanced-logic-systems/order-flow-x
**Price**: $197 (one-time, lifetime access)

### Concept
Automated strategy that detects stacked order book imbalances — clusters of aggressive buying or selling across multiple price levels signaling sudden directional intent. Automates detection and execution that manual traders try to spot visually on footprint/DOM.

### Conditions / Setup
- NinjaTrader 8, any license tier with Order Flow+ data
- Optimized for ES, NQ, RTY, CL, YM
- Flexible across timeframes (1-minute scalps to multi-hour swings)
- Plug-and-play: no coding required

### Entry / Exit Rules
- Scans for user-defined stacked imbalance thresholds
- Executes immediately when imbalances appear
- Supports ATM bracket orders (stops, targets, trailing stops via NT8 ATM Strategy Builder)
- User controls direction (long, short, or both)
- Configurable time windows and contract sizing

### Risk Management
- Configurable stop-loss levels
- Time window filters (e.g., RTH only)
- Profit targets in ticks
- ATM strategy handles bracket management

### DEEP6 Integration
- Direct overlap with DEEP6's stacked imbalance detection in `DEEP6LiquidityImbalance.cs`
- DEEP6 adds context that Order Flow X lacks: absorption confirmation, exhaustion filtering, GEX levels
- Order Flow X's single-signal approach demonstrates why DEEP6's multi-signal confluence is superior

---

## VOLUME PROFILE / MARKET PROFILE STRATEGIES

---

## NT8-STR-06: MZpack GhostResistance
**Category**: Strategy
**Tags**: volume-profile, reversal, liquidity-trap, absorption, big-trade, stop-hunt
**DEEP6 Signal(s)**: ABS-01 (absorption), TRAP-01 (trapped traders), VP-01 (volume profile levels)
**NinjaTrader File**: https://docs.mzpack.pro/docs/strategies/built-in-strategies
**Price**: Part of MZpack Strategies subscription

### Concept
Reversal strategy targeting liquidity traps — situations where price pushes beyond support/resistance, triggering stops and breakout entries from trapped traders, then reverses sharply back into the prior value area. Combines absorption zones, big trade detection, bar metrics, and volume profile levels.

### Conditions / Setup
- Requires MZpack indicators (mzFootprint, mzBigTrade, mzVolumeProfile)
- Works best on liquid futures (ES, NQ) with sufficient tick volume
- Uses session or weekly volume profiles for level identification

### Entry / Exit Rules
**Four Signal Groups (all must validate):**
1. **Bar Metrics**: Minimum volume, delta, delta %, wick %, optional hammer pattern
2. **Absorption**: S/R zones from mzFootprint with configurable percentage, depth, consecutive levels
3. **Big Trade**: Significant trades detected by mzBigTrade (iceberg detection, aggression/sweep filter)
4. **Profile Levels**: Price approaching session or weekly volume profile level (optional — can run pure order flow mode)

### Risk Management
- Multi-factor validation prevents low-quality entries
- Configurable via ATM strategies
- Session cumulative delta provides additional context

### DEEP6 Integration
- GhostResistance's thesis (stop hunts + absorption = reversal) is the core DEEP6 thesis
- DEEP6's absorption detection at key levels directly maps to GhostResistance signal group 2
- Big trade / iceberg detection aligns with DEEP6's institutional footprint tracking
- Reference: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\DEEP6LiquidityImbalance.cs`

---

## NT8-STR-07: Emoji Trading Order Flow Suite
**Category**: Strategy (Indicator Suite with Strategy Signals)
**Tags**: order-flow, absorption, exhaustion, delta-divergence, POC, unfinished-business, volume-profile
**DEEP6 Signal(s)**: ABS-01, EXH-01, CR-06, VP-01
**NinjaTrader File**: https://emojitrading.com/ninjatrader/order-flow-suite
**Price**: $89/mo or $599/yr (14-day free trial)

### Concept
Suite of 8 order flow indicators plus 6 educator-endorsed indicators. Key tools: Absorption Pro (passive buyer/seller accumulation), Delta Divergence Pro (buying/selling exhaustion across MTF), Price Rejector Pro (reversal points using absorption + exhaustion + aggression), POC Pro, and Unfinished Business.

### Conditions / Setup
- Works with NinjaTrader 8 Free, Lease, or Lifetime license (no Order Flow+ required)
- Compatible with multiple footprint add-ons (Gomi, NOFT, MZPack) and emoji's own FreePrint
- Any futures instrument

### Entry / Exit Rules
- **Price Rejector Pro**: Identifies key reversal points via confluence of absorption, exhaustion, and aggression
- **Absorption Pro**: Tracks to-the-tick where passive buyers/sellers accumulate/distribute
- **Delta Divergence Pro**: Multi-timeframe exhaustion detection
- **Unfinished Business**: Locates price levels with reason to be retested
- **Small Prints**: Exhaustion and aggression via zero prints, single prints at extremes

### Risk Management
- Advanced lookback with flexible price and time filtering
- EmojiZone visualizations qualify levels that will hold or break

### DEEP6 Integration
- Absorption Pro's per-tick tracking directly parallels DEEP6's absorption detection
- Price Rejector Pro's triple-confirmation (absorption + exhaustion + aggression) validates DEEP6's confluence scoring design
- Unfinished Business concept maps to DEEP6's auction theory incomplete auction detection
- Does NOT require Order Flow+ — provides alternative data access method

---

## MOMENTUM / BREAKOUT STRATEGIES

---

## NT8-STR-08: Eagle Eye Peak Hours Trading NQ
**Category**: Strategy
**Tags**: momentum, multi-indicator, peak-hours, NQ, automated, trend-following
**DEEP6 Signal(s)**: None directly (indicator-based, not order-flow)
**NinjaTrader File**: https://ninjatraderecosystem.com/user-app-share-download/strategy-eagle-eye-peak-hours-trading-nq/
**Price**: Free (MIT/Open Source License)

### Concept
Automated NQ trading strategy targeting peak market hours (12:30 PM – 4:30 PM ET). Uses EMA crossovers, RSI, VWAP positioning, SMA, ATR, and volume trends for multi-indicator confirmation of entries and exits.

### Conditions / Setup
- 15-minute NQ chart (author's recommendation; adjustable)
- Active during 12:30 – 16:30 ET only
- Requires standard NinjaTrader data feed
- 617+ downloads on User App Share

### Entry / Exit Rules
- **Long**: Close above shorter EMA, RSI > 50, price above VWAP, volatility filter met, volume above 20-period SMA
- **Short**: Close below shorter EMA, RSI < 50, price below VWAP, other conditions met
- **Exits**: Customizable profit target, trailing stop, break-even triggers, time-based exits, trend reversal exits

### Risk Management
- Maximum drawdown exit mechanism
- Break-even trigger to protect profits
- Time-based exits (session close)
- Volatility filter ensures trades only during high-volatility periods

### DEEP6 Integration
- DEEP6 order flow signals could filter this strategy's entries to avoid low-quality setups
- Peak hours focus (afternoon session) is when institutional order flow patterns are most detectable
- Strategy serves as a baseline for comparing DEEP6's order-flow-based entries vs indicator-based entries

---

## NT8-STR-09: Automated Strategy for Trading NQ
**Category**: Strategy
**Tags**: trend-following, mean-reversion, multi-indicator, NQ, automated
**DEEP6 Signal(s)**: None directly
**NinjaTrader File**: https://ninjatraderecosystem.com/user-app-share-download/automated-strategy-for-trading-nq/
**Price**: Free

### Concept
Multi-indicator NQ strategy combining trend-following and mean-reversion logic. Uses EMAs, ADX, MACD, RSI, VWAP, Bollinger Bands, and volume for comprehensive entry/exit signals. Adaptable to other futures instruments.

### Conditions / Setup
- NQ primary instrument (works on other futures)
- Standard NinjaTrader 8 data feed
- 2,996+ downloads on User App Share (most popular free NQ strategy)

### Entry / Exit Rules
- Dual-mode: trend-following entries when ADX/EMA/MACD align, mean-reversion entries when price reaches Bollinger Band extremes near VWAP
- Multiple indicator confirmation required for entry
- Exit on indicator reversal or target/stop

### Risk Management
- Built-in stop loss and profit targets
- Multi-indicator exit conditions

### DEEP6 Integration
- Provides a traditional indicator-based benchmark strategy for DEEP6 A/B testing
- DEEP6 absorption/exhaustion signals could replace or supplement the mean-reversion component
- Volume filter could be enhanced with DEEP6's tick-level volume analysis

---

## NT8-STR-10: ARKO Quantum Time-Based Opening Range Breakout (TBORB)
**Category**: Strategy
**Tags**: breakout, opening-range, ORB, initial-balance, automated, intraday, open-source
**DEEP6 Signal(s)**: None directly (structural, not order-flow)
**NinjaTrader File**: https://github.com/ARKO-Q/AQ_TBORB
**Price**: Free / Open Source

### Concept
Custom NinjaTrader 8 automated strategy for American futures markets. Captures intraday breakouts within a user-defined time-based opening range. Places stop market orders above and below the range after the window ends. Uses range high/low as exposure triggers rather than ATR-based volatility calculations.

### Conditions / Setup
- Configurable opening range start and end times
- Works on any futures instrument
- Designed for intraday trading during RTH

### Entry / Exit Rules
- Captures high and low during defined time window
- Submits stop market orders immediately after window closes
- Long entry: price breaks above range high
- Short entry: price breaks below range low
- Auto break-even at configurable percentage of opening range width
- Fee coverage in ticks (adjusts break-even for commissions)

### Risk Management
- Stop on opposite side of opening range
- Auto break-even with fee coverage
- Time-based account flattening (end of session)
- ATM strategy integration available

### DEEP6 Integration
- Opening range breakout is a structural setup; DEEP6 order flow signals could confirm/deny the breakout
- Absorption at range boundaries (DEEP6 ABS-01) would filter false breakouts
- Volume analysis at breakout level confirms institutional participation

---

## NT8-STR-11: Inside Bar Breakout Strategy
**Category**: Strategy
**Tags**: breakout, price-action, inside-bar, ATR, automated, micro-futures, open-source
**DEEP6 Signal(s)**: None directly (price-action based)
**NinjaTrader File**: https://github.com/andrzej-nowak/ninjatrader-trading (fork of dbergstrom1207)
**Price**: Free / Open Source (MIT)

### Concept
Identifies inside bars (current bar doesn't close above or below previous bar) and sends buy or sell orders when price breaks above or below the inside bar range. Fully automated with ATR-based stops and trailing stops. Trades micro futures (/MES, /MNQ) but imports mini futures data (/ES, /NQ) for signals.

### Conditions / Setup
- Micro futures chart (/MES, /MNQ, /MYM)
- Uses mini futures data for signal generation
- Any intraday timeframe

### Entry / Exit Rules
- **Long**: Price breaks above inside bar high
- **Short**: Price breaks below inside bar low
- Stop loss and profit target based on ATR
- Trailing stop moves as price moves favorably
- Orders placed on break of inside bar (not bar close)

### Risk Management
- ATR-based stop loss (dynamic, adapts to volatility)
- ATR-based profit targets
- Trailing stop follows price
- Author notes: live signals trigger on break (not at bar close as displayed in backtesting)

### DEEP6 Integration
- Inside bars at key DEEP6 levels (absorption zones, POC) become high-probability setups
- DEEP6 delta analysis on the inside bar itself reveals whether accumulation/distribution is occurring
- Simple template strategy for testing DEEP6 signal integration

---

## NT8-STR-12: Accumulation/Distribution Range Breakout
**Category**: Strategy
**Tags**: breakout, accumulation-distribution, S&C, range, automated
**DEEP6 Signal(s)**: None directly
**NinjaTrader File**: https://ninjatraderecosystem.com/user-app-share/ (search "Accumulation Distribution Range Breakout")
**Price**: Free

### Concept
Published in Stocks & Commodities magazine (August 2018). Breakout strategy using Accumulation/Distribution indicator to confirm range breakouts. Identifies ranges where A/D diverges from price, then trades the breakout with A/D confirmation.

### Conditions / Setup
- Standard NinjaTrader 8 data feed
- 11,825+ downloads (one of the most downloaded User App Share strategies)
- Any futures instrument

### Entry / Exit Rules
- Detects price range (consolidation)
- Monitors Accumulation/Distribution indicator for divergence during range
- Enters on breakout when A/D confirms directional bias
- Published methodology from S&C magazine

### Risk Management
- Range-defined stops (opposite side of breakout range)
- S&C magazine methodology includes sizing guidance

### DEEP6 Integration
- A/D divergence during ranges parallels DEEP6's delta divergence detection
- DEEP6 footprint data provides granular view of accumulation/distribution that A/D only approximates
- High download count (11K+) suggests broad community validation of the concept

---

## REVERSAL / MEAN REVERSION STRATEGIES

---

## NT8-STR-13: TDU Delta Divergence Reversal Strategy
**Category**: Strategy
**Tags**: reversal, delta-divergence, absorption, stopping-volume, order-flow, sample-code
**DEEP6 Signal(s)**: CR-06 (delta divergence), ABS-01 (absorption), EXH-01 (stopping volume)
**NinjaTrader File**: https://tradedevils-indicators.com/pages/order-flow-footprint-indicator-strategies (code sample)
**Price**: Requires TDU Footprint Indicator ($149+)

### Concept
Sample strategy from TDU documentation demonstrating delta divergence reversal trading. Enters reversals when delta diverges from price AND absorption or stopping volume confirms the reversal. Published as educational NinjaScript code.

### Conditions / Setup
- Requires TDU Footprint Indicator (TDUFootPrintPlots)
- 1-tick secondary data series for precise order placement
- Minimum 20-bar lookback
- Flat position required for new entry

### Entry / Exit Rules
- **Bullish Reversal**: Delta divergence detected + delta < 0 + (absorption == 1 OR stopping volume == 1)
- **Bearish Reversal**: Delta divergence detected + delta > 0 + (absorption == -1 OR stopping volume == -1)
- Stop loss: 30 ticks
- Profit target: 45 ticks (1.5:1 reward-to-risk)

### Risk Management
- Fixed 30-tick stop loss
- Fixed 45-tick profit target
- Single entry per direction (EntriesPerDirection = 1)
- Only enters from flat (no pyramiding)

### DEEP6 Integration
- This strategy IS the DEEP6 thesis in miniature: delta divergence + absorption = reversal
- DEEP6 extends this with 44 signals instead of 3, confluence scoring instead of binary AND/OR
- The 30/45 tick stop/target could be optimized using DEEP6's ATR-based dynamic sizing
- Reference: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\DEEP6Strategy.cs`

---

## NT8-STR-14: Trading123 Order Flow Strategy
**Category**: Strategy
**Tags**: order-flow, volume-delta, automated, ES-specific, absorption, imbalance
**DEEP6 Signal(s)**: ABS-01 (absorption), CR-06 (delta analysis)
**NinjaTrader File**: https://www.trading123.net/product/order-flow-strategy-ninjatrader/
**Price**: $1,497 (one-time, lifetime)

### Concept
Fully automated order flow strategy reading real-time buying/selling pressure through Volume Delta. Designed specifically for ES/MES futures. Determines which side (buyers vs sellers) controls the market and trades accordingly. Analyzes volume delta, bid/ask imbalance, large market orders, and absorption.

### Conditions / Setup
- ES / MES futures only (optimized for S&P 500 liquidity)
- Requires tick data feed (Rithmic or Continuum)
- Trading window: 8:00 AM – 11:55 AM ET only
- 2-4 trades per day

### Entry / Exit Rules
- Entry based on Volume Delta momentum shifts (buyer/seller control change)
- Combines: Volume Delta, bid/ask imbalance, large market orders, absorption, footprint activity
- Handles entries, exits, stops, trailing stops, and profit targets automatically
- No afternoon trading (avoids low-volume chop)

### Risk Management
- Automated stop loss and profit targets
- Trailing stop for trend-following exits
- Session time limit (no afternoon exposure)
- Limited to 2-4 trades/day (avoids overtrading)

### DEEP6 Integration
- Trading123's morning-only window validates DEEP6's assumption that order flow signals are most reliable during high-liquidity RTH hours
- Volume Delta approach is a simplified version of DEEP6's comprehensive delta analysis
- ES-only focus means DEEP6's NQ-specific calibration may differ in optimal parameters

---

## NT8-STR-15: Beer Money (VWAP + Order Flow Indicator)
**Category**: Strategy (Indicator with Strategy Signals)
**Tags**: mean-reversion, VWAP, volume-profile, imbalance, divergent-bars, delta-efficiency, open-source
**DEEP6 Signal(s)**: ABS-01 (absorption via divergent bars), VP-01 (volume profile), CR-06 (delta efficiency)
**NinjaTrader File**: https://github.com/WaleeTheRobot/beer-money
**Price**: Free / Open Source

### Concept
NinjaTrader 8 indicator for order flow analysis combining rolling window VWAP with volume profile, diagonal imbalances, and divergent bar detection. Dual VWAP system (Bias VWAP for trend direction + Trigger VWAP for entry timing) identifies momentum and mean reversion opportunities. By the same author as OrderFlowBot.

### Conditions / Setup
- Requires NinjaTrader OrderFlow+ package (volumetric data)
- Uses 4 configurable data series (Primary, Base for ATR, Bias volumetric, Trigger volumetric)
- Configurable bar types: Tick, Minute, Second, Range, or Volume

### Entry / Exit Rules
**Long Setup Confluence Checklist:**
- Price at or near VAL or below POC
- Large white circles (high volume bullish imbalances) appearing
- Multiple cyan bars (hidden accumulation — buyers absorbing selling pressure)
- VWAP diff spreading positive

**Short Setup Confluence Checklist:**
- Price at or near VAH or above POC
- Large orange circles (high volume bearish imbalances)
- Multiple magenta bars (hidden distribution)
- VWAP diff spreading negative

**Delta Efficiency Colors:**
- Cyan (0-30%): Choppy, indecisive — favorable for mean reversion
- Other ranges indicate trending conditions

### Risk Management
- VWAP bands define mean-reversion zones
- ATR from configurable base series for stop sizing (70-80% of ATR increases probability)
- Volume profile levels (POC/VAH/VAL) provide structural stops

### DEEP6 Integration
- Divergent bars (hidden accumulation/distribution) directly parallel DEEP6's absorption detection
- Dual VWAP system provides institutional fair-value context for DEEP6's signal engine
- Delta efficiency metric is a novel approach DEEP6 could adopt for regime classification
- Same author as OrderFlowBot — consistent order flow philosophy

---

## SCALPING STRATEGIES

---

## NT8-STR-16: Eagle Eye River Scalper
**Category**: Strategy
**Tags**: scalping, EMA, RSI, Chaikin-Money-Flow, volume-oscillator, NQ, automated
**DEEP6 Signal(s)**: None directly (indicator-based)
**NinjaTrader File**: https://ninjatraderecosystem.com/user-app-share-download/strategyeagleeyeriverscalper/
**Price**: Free

### Concept
Automated NinjaTrader 8 scalping strategy capturing small, quick profits from short-term price movements. Uses dual EMA trend identification with multiple confirmation filters (Chaikin Money Flow, Volume Oscillator, RSI, ATR) to generate high-quality scalp entries.

### Conditions / Setup
- Designed for NQ futures (works on other instruments)
- Short timeframes (1-5 minute charts)
- Standard NinjaTrader 8 data feed
- Part of the Eagle Eye strategy family by trgui7883

### Entry / Exit Rules
- **Long**: Price closes above both EMAs, faster EMA above slower, Chaikin Money Flow positive, Volume Oscillator rising, volume above 20-period SMA, RSI not overbought
- **Short**: Price closes below both EMAs, faster EMA below slower, Chaikin Money Flow negative, RSI not oversold
- Fixed tick-based profit targets and stop losses
- Session close exits all positions (no overnight risk)

### Risk Management
- Fixed profit target and stop loss (user-configurable ticks)
- ATR filter avoids entries during extreme volatility
- RSI overbought/oversold filter prevents chasing
- Mandatory session-close exit
- Customizable EMA periods

### DEEP6 Integration
- Scalping framework could use DEEP6 order flow as primary entry signal instead of EMA crossovers
- Volume filter could be replaced with DEEP6's tick-level delta analysis for higher precision
- Session-close risk management is a good practice DEEP6 execution should adopt

---

## NT8-STR-17: LargeTrades Strategy NT8
**Category**: Strategy
**Tags**: scalping, large-trades, volume-excess, limit-order-detection, 1-minute
**DEEP6 Signal(s)**: ABS-01 (absorption — detects large limit orders), ICE-01 (iceberg detection)
**NinjaTrader File**: https://ninjatraderecosystem.com/user-app-share-download/largetrades-strategy-nt8/
**Price**: Free

### Concept
Scalping strategy that trades based on major transactions occurring during short time periods at the same price level. Detects excess volume from limit buyers/sellers — essentially identifying institutional absorption events. 1-minute timeframe focus.

### Conditions / Setup
- 1-minute chart
- Any liquid futures instrument (ES, NQ)
- Requires sufficient tick data to detect volume clustering

### Entry / Exit Rules
- Detects clusters of large trades at a single price level within a short window
- Enters in the direction of the detected large participant
- Scalping exits (tight targets)

### Risk Management
- Scalping stops (tight risk per trade)
- Volume threshold filters

### DEEP6 Integration
- Directly relates to DEEP6's absorption and iceberg detection signals
- Large limit order detection at a single price is the fundamental absorption pattern DEEP6 targets
- Could serve as a simplified standalone version of DEEP6's ABS-01 signal
- Reference: `C:\Users\Tea\DEEP6\ninjatrader\tests\Detectors\AbsorptionDetectorTests.cs`

---

## FRAMEWORK / MULTI-STRATEGY

---

## NT8-STR-18: ATSQuadroStrategyBase
**Category**: Strategy Framework
**Tags**: framework, unmanaged-mode, hybrid, semi-automated, bracket-orders, multi-exit, open-source, WPF
**DEEP6 Signal(s)**: N/A (framework, not a specific strategy)
**NinjaTrader File**: https://github.com/GithubRealFan/Ninja-Trader-8 (26 stars, MIT License)
**Price**: Free / Open Source

### Concept
Hybrid algorithmic trading framework for NinjaTrader 8 using unmanaged mode trade engine. Provides 4-bracket capacity with all-in/scale-out single entry position and multiple exits per trade. Top-layer Hybrid mode has UI controls for semi-auto/auto switching — best of both worlds. Developed by MicroTrends Ltd.

### Conditions / Setup
- NinjaTrader 8 with connected data feed
- C# development skills required for customization
- Includes WPF UI components for strategy control panel
- Sample strategy: ATSSamplePriceReversalTestHybridAlgo.cs

### Entry / Exit Rules
- Framework provides:
  - 4 bracket order capacity per position
  - Single entry, multiple exits (non-compounding)
  - Overfill prevention
  - Semi-auto mode (bot identifies, trader confirms) and full-auto mode
- Users implement specific entry/exit logic by deriving from base classes

### Risk Management
- Built-in bracket order management
- Overfill prevention at the engine level
- Scale-out capability (partial profit taking)
- Semi-auto mode as safety net

### DEEP6 Integration
- ATSQuadro's unmanaged mode approach is relevant for DEEP6's Python-based execution via async-rithmic
- Multi-exit bracket pattern (scale-out) is exactly what DEEP6's execution engine needs
- Semi-auto/auto hybrid mode validates DEEP6's planned operator confirmation flow
- Reference: `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\DEEP6AtlasStrategy.cs` — DEEP6's own strategy uses similar patterns

---

## Summary: DEEP6 Signal Coverage Map

| DEEP6 Signal | Strategies That Use Similar Logic |
|---|---|
| ABS-01 (Absorption) | NT8-STR-01, 02, 03, 06, 07, 13, 14, 15, 17 |
| EXH-01 (Exhaustion) | NT8-STR-01, 02, 07, 13 |
| IMB-03 (Stacked Imbalances) | NT8-STR-01, 02, 03, 05 |
| CR-06 (Delta Divergence) | NT8-STR-02, 03, 07, 13, 14, 15 |
| TRAP-01 (Trapped Traders) | NT8-STR-02, 03, 06 |
| VP-01 (Volume Profile) | NT8-STR-06, 07, 15 |
| ICE-01 (Iceberg Detection) | NT8-STR-06, 17 |

---

## Source Index

| Source Type | Count | Examples |
|---|---|---|
| GitHub Open Source | 5 | OrderFlowBot, ARKO TBORB, Inside Bar, Beer Money, ATSQuadro |
| User App Share (Free) | 5 | Eagle Eye Peak Hours, Automated NQ, River Scalper, LargeTrades, A/D Range Breakout |
| Paid Vendor | 7 | TDU, MZpack (x2), OrderFlow Hub, Order Flow X, Emoji Trading, Trading123 |
| Code Sample | 1 | TDU Delta Divergence Reversal |

---

*Catalog maintained by DEEP6 Trading Knowledge Center. Entries describe strategy concepts only — no source code is reproduced. Verify vendor pricing and availability at linked URLs.*
