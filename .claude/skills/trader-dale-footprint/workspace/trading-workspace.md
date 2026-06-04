# Order Flow Trading Workspace & TDO 2.0 Software Reference

## TDO Bars 2.0 — Installation

1. NinjaTrader 8 → Tools → Import → NinjaScript Add-On → select `TDOrderFlow-2.0.zip` (do NOT extract first)
2. Restart NinjaTrader 8
3. New → Chart → In Data Series window, set **Type = TDOFBars** and **Chart style = TDOrderFlow**
4. To change settings later: right-click chart → Data Series

## Three Toolbar Buttons (Top of Chart)

### Button 1: Cell Content
| Mode | What It Shows | When to Use |
|------|--------------|-------------|
| **Bid x Ask** | `154 x 84` format — separate bid/ask volumes per price | Confirmations, entry timing, reading individual orders |
| **Delta** | Ask minus Bid per price level (positive = buyers, negative = sellers) | Quick buyer/seller dominance read |
| **Volume** | Total volume per price (Bid + Ask combined), grey shading | Setup identification, volume clusters, works on Forex |
| **Diagonal Delta** | Same as Delta but compared diagonally (more accurate) | Advanced delta reading |

### Button 2: Summary Panel (below footprint)
Available fields: Ask, Bid, **Delta**, Max Delta, Min Delta, **Cum. Delta**, Cum Delta/Volume, **Volume**, Cum. Volume

Dale's recommended summary: **Delta + Cumulative Delta + Volume** only. Others are noise.

### Button 3: Display Toggles
| Toggle | What It Does |
|--------|-------------|
| **Volume Profile** | Shows Daily Volume Profile on left side of chart |
| **Volume Imbalances** | Shows imbalance highlighting (blue text) and stacked imbalance boxes |
| **Unfinished Business** | Draws dotted line at failed auctions until price retests |

## Data Series Settings (Right-click → Data Series)

| Setting | Description | Default | Notes |
|---------|-------------|---------|-------|
| **BarsPeriod** | Timeframe unit | Minute | |
| **Type** | Bar type | **TDOFBars** | MUST be TDOFBars for Order Flow |
| **Value** | Timeframe value | 5 | 5 = 5-minute footprints, 30 = 30-minute |
| **Min. Trade Size** | Trades Filter threshold | 0 | Set to 25 for EUR futures, 300+ for ES. 0 = show all |
| **Calculation** | Price calc method | BidAsk | |
| **Price based on** | Price source | Last | |
| **Tick Replay** | Tick-by-tick replay | OFF | Must be OFF for Cumulative Delta |

## Chart Style Settings (Right-click → Data Series → Chart Style)

| Setting | Description | Default | Recommended |
|---------|-------------|---------|-------------|
| **Chart style** | Rendering style | TDOrderFlow | Must be TDOrderFlow |
| **Ticks aggregation** | Price level grouping | 1 | **CRITICAL**: Increase for instruments with too many tick levels (e.g., NQ). Reduces cells per footprint. 2 = half as many cells, 10 = 1/10th. Makes chart readable and faster. |
| **Bar width** | Footprint width in pixels | 39 | |
| **CandleWidth** | Width of candle body | 8 | |
| **MinFontSize** | Minimum text size | 11 | |
| **Mode** | Bar or Candle | **Bar** | Bar preferred — shows volume shading (darker = heavier) |
| **Content Above Bar** | What shows above footprint | None | Can set to Volume |
| **Content Below Bar** | What shows below footprint | Delta | Shows delta below each footprint |

## POC (Point of Control) Settings

| Setting | Default | Description |
|---------|---------|-------------|
| POC Color Outline | **Black** | Black frame around highest-volume price in each footprint |
| POC Cluster Background Color | **Yellow** | Highlights when 2+ consecutive footprints have POC at same price (Multiple Node) |
| POC Outline Width | 2 | |

## Volume Imbalance Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Display Stacked Imbalances | **Checked** | |
| Imbalance Trigger in Percent | **300** | Ask must be 300%+ of Bid (or vice versa) for imbalance. Compared diagonally. |
| Stacked Imbalance Size | **3** | Minimum stacked imbalances to draw highlighted box |
| Stacked Imbalance Box Draw Mode | **UntilTested** | Box stays until price retests the zone |
| Stacked Imbalance Box Size | 5 | |
| Stacked Imbalance Opacity | 50 | |
| Minimal Imbalance Volume | 0 | Minimum volume for imbalance to register |
| Imbalance At Ask Text Color | MediumBlue | Buying imbalances shown in blue on Ask |
| Imbalance At Bid Text Color | MediumBlue | Selling imbalances shown in blue on Bid |
| Stacked Imbalance At Ask Line Color | **LightGreen** | Green highlight = Support zone |
| Stacked Imbalance At Bid Line Color | **LightCoral** | Red highlight = Resistance zone |
| Multiple Imbalances in Bar Threshold | 3 | |
| Highlight Multiple Imbalances | Unchecked | |

## Volume Profile Settings (Built into OF chart)

| Setting | Default | Description |
|---------|---------|-------------|
| Display Volume Profile | **Checked** | Shows Daily VP on chart |
| Display on Right | Unchecked | VP displays on left by default |
| Display Prices | Unchecked | |
| Display Volumes | Checked | |
| Volume at Ask color | **CadetBlue** | Volumes traded on Ask side |
| Volume at Bid color | **Red** | Volumes traded on Bid side |
| Volumecolor | SlateGray | |
| Width in pixels | 100 | |

## TD Cumulative Delta Setup (Separate Indicator)

The Cumulative Delta is a **separate indicator**, not part of the OF chart. Set it up on its own chart:

1. New → Chart → Data Series:
   - Type: **Minute**
   - Value: **1**
   - Tick Replay: **OFF** (IMPORTANT)
   - Chart style: **Line on Close**
2. Right-click chart → Indicators → find **TD Cumulative Delta 2** in the TraderDale folder
3. Double-click to add, press OK. No settings changes needed.
4. Place this chart below a 1-minute price chart for divergence analysis.

## Dale's 4-Chart Workspace Layout

All charts linked to same instrument. Changing symbol on one updates all four.

### Top Left — 30-Minute Volume Chart (Big Picture)
- Cell content: **Volume** (grey shading mode)
- Delta shown below each footprint
- Daily Volume Profile on left side
- Summary: Delta, Cumulative Delta, Volume
- **Purpose**: See big picture, identify Volume Clusters and S/R zones

### Top Right — 5-Minute Bid x Ask Chart (Entry/Exit)
- Cell content: **Bid x Ask**
- Delta below each footprint
- Summary: Delta, Cumulative Delta, Volume
- **Purpose**: Spot confirmations, time entries/exits, read individual orders

### Bottom Left — 30-Minute Trades Filter Chart
- Cell content: **Bid x Ask** with Trades Filter enabled
- Daily Volume Profile on left
- Min Trade Size: 25 (EUR Futures), 300+ (ES/NQ)
- **Purpose**: Filter noise, see only institutional-size orders

### Bottom Right — 1-Minute Price + Cumulative Delta
- Top panel: 1-minute line or candlestick price chart
- Bottom panel: TD Cumulative Delta 2 indicator (1-minute)
- **Purpose**: Spot price vs delta divergences (Confirmation #4)

## Pre-Made Workspaces

Dale provides 6 workspace templates (`.xml` files):

| Workspace | Screens | Description |
|-----------|---------|-------------|
| OF Futures (1 Screen) | 1 | 4-chart OF layout for futures |
| OF Forex (1 Screen) | 1 | 4-chart OF layout for forex |
| OF Forex JPY pairs (1 Screen) | 1 | Adjusted for inverse JPY pairs |
| OF + VP Futures (2 Screen) | 2 | OF on screen 1, VP analysis on screen 2 |
| OF + VP Forex (2 Screen) | 2 | OF + VP for forex |
| OF + VP Forex JPY pairs (2 Screen) | 2 | OF + VP for inverse JPY pairs |

**Install workspaces**: Extract `.xml` files from `Workspaces.zip` → copy to `Documents\NinjaTrader 8\workspaces` → restart NT8 → Workspaces menu → select.

## NQ-Specific Configuration Notes

- **Ticks aggregation**: NQ has 0.25-point tick size = many price levels per footprint. Set ticks aggregation to **2 or 4** to reduce clutter.
- **Trades Filter**: NQ trades heavier volume than EUR futures. Start with Min Trade Size = **100-200** and adjust to get ~5-10 signals/day during US session.
- **Timeframes**: Same as Dale's defaults — 30min for big picture, 5min for entries, 1min for cum delta.
- **Session**: Heavy NQ volume only during US session (9:30 AM - 4:00 PM ET). Asian/European sessions have thin volume — trades filter signals will be rare.
