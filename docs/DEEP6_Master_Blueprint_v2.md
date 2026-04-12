# DEEP6 · COMPLETE MASTER BLUEPRINT v2
## Full Element Catalog from Images + Complete Build Specification
---

## ════════════════════════════════════════════════════════
## SECTION 1: COMPLETE UI ELEMENT CATALOG
## (Every pixel documented from the two reference images)
## ════════════════════════════════════════════════════════

## 1.1 TOP HEADER BAR
Fixed bar spanning full chart width. Two rows.

### Row 1 — Branding + Instrument
```
[DEEP6]  [v1.0.0]  |  [NQ1!]  [19,484.00]  [+0.64%]
```
- DEEP6: neon teal #00D4AA, 14pt bold Consolas
- v1.0.0: gray #666, 9pt
- NQ1!: white #FFF, 13pt bold
- Price: white #FFF, 18pt bold
- +0.64%: green #00FF87, 12pt (red if negative)

### Row 2 — Status columns (7 data columns + 2 indicators)
```
DAY TYPE  │  IB     │  IB TIER │  GEX      │  VWAP   │  SPOOF  │  TRESPASS │  CVD      │ DOM ● LIVE │ TICK REPLAY
TREND BULL│  TYPE   │  NARROW  │  REGIME   │  ZONE   │  SCORE  │           │           │            │
```
Column specs:
- **DAY TYPE: TREND BULL** — two-line cell: label gray, value neon green
- **IB TYPE** — two-line: label + value
- **IB TIER: NARROW** — two-line (WIDE/NORMAL/NARROW)
- **GEX REGIME: NEGATIVE** — label + RED value when negative
- **VWAP ZONE: +1σ** — label + sigma value
- **SPOOF SCORE: 0.12** — label + decimal (green when < 0.3)
- **TRESPASS: +0.68** — label + signed decimal (green pos, red neg)
- **CVD: +4,218** — label + signed volume
- **DOM ● LIVE** — green pulsing dot + LIVE text (red DOT + DISC when disconnected)
- **TICK REPLAY** — toggle indicator (gray when live, orange when replay)

Background: #0D0F1E, border-bottom: 1px solid #1E2540

---

## 1.2 LEFT VERTICAL TAB BAR
Vertical tab strip on LEFT edge of chart (NOT top, NOT bottom).
Width ~55px. Dark background #08090F.

Tabs (top to bottom, each ~40px height):
```
[ IN ]         ← Intraday overview (current)
[ 3 MIN ]      ← 3-minute chart view
[ 5 MIN ]      ← 5-minute chart view
[ FOOTPRINT ]  ← Footprint/volumetric view ← ACTIVE by default
[ VOL PROFILE] ← Volume profile overlay
[ VWAP ±2σ ]  ← VWAP with 2 standard deviation bands
[ GEX LEVELS ] ← GEX gamma exposure levels
[ IB LEVELS ]  ← Initial Balance levels view
[ SIGNALS ]    ← Signals log view
```

Active tab: neon green text #00FF87, green left border 2px
Inactive: gray #4A5070, no border
Tab text: 8pt Consolas, rotated 0° (readable, not rotated)
Dividers: 1px #1A1E35 between tabs

---

## 1.3 STATUS PILLS ROW
Single row below the chart tabs, above the chart area itself.
Each pill is a rounded-rect label with specific background color.

### The 9 pills (left to right):
```
[TREND BULL] [IB] [NARROW · C-CONFIRMED] [GEX] [NEG GAMMA · AMPLIFYING] [DEV POC] [MIGRATING ↑ · 8 BARS] [VWAP-POC] [28 ticks · TRENDING]
```

| Pill | Text | BG Color | Text Color |
|------|------|----------|------------|
| 1 | TREND BULL | #0B3D1E | #00FF87 |
| 2 | IB | #1A1E35 | #8090C0 |
| 3 | NARROW · C-CONFIRMED | #0D3535 | #00D4AA |
| 4 | GEX | #1A1E35 | #8090C0 |
| 5 | NEG GAMMA · AMPLIFYING | #3D0B0B | #FF4444 |
| 6 | DEV POC | #1A1E35 | #8090C0 |
| 7 | MIGRATING ↑ · 8 BARS | #3D2800 | #FF9500 |
| 8 | VWAP-POC | #1A1E35 | #8090C0 |
| 9 | 28 ticks · TRENDING | #0D2535 | #5AC8FA |

Pill styling: padding 4×8, border-radius 3, border 1px (30% opacity of text color), margin 2px

---

## 1.4 MAIN CHART AREA — FOOTPRINT RENDERING (SharpDX)

### Chart background:
- Primary bg: #0A0C16
- Grid lines: #111520 (very subtle horizontal lines at price levels)
- Price axis: right side, 40px wide, #0D0F1E bg

### Footprint bar structure (per bar, via SharpDX OnRender):
Each bar consists of cells — one cell per price tick in the bar's range.

**Cell layout:**
```
[  BID_VOL  |  PRICE.XX  |  ASK_VOL  ]
```
- Cell width = bar_pixel_width (typically 35-50px)
- Cell height = Y-distance between adjacent ticks = chartScale.GetYByValue(price) - chartScale.GetYByValue(price + tickSize)
- BID_VOL column: left 40% of cell width
- PRICE column: center 20%
- ASK_VOL column: right 40%

**Cell color logic:**
```csharp
double imbalRatio = askVol > 0 && bidVol > 0 ? askVol / bidVol : 1.0;
Color cellBg;
if (imbalRatio >= ImbalanceRatio)         // buy imbalance (ask dominates)
    cellBg = Color.FromArgb(alpha, 0, 80, 40);   // dark green
else if (1.0 / imbalRatio >= ImbalanceRatio)  // sell imbalance
    cellBg = Color.FromArgb(alpha, 80, 0, 0);    // dark red
else if (isThinLevel)                     // low volume = LVN
    cellBg = Color.FromArgb(30, 200, 200, 255);  // pale blue
else
    cellBg = Color.Transparent;
```

**POC row highlighting:**
- Bold border: 1px #FFD700 on left side of POC cell
- Background: slightly brighter

**Absorption highlighting:**
- Cell where absorption fires: amber/gold background
- Stacked imbalance: sequential cells with increasing green/red intensity

**Delta row (below each bar):**
- Displayed below the bar using SharpDX
- Format: "△ +1,340" (or "△ -2,218 · BULL ABSORB" for absorption signals)
- Color: green for positive, red for negative
- Font: 8pt Consolas

**Volume text inside cells:**
- Bid volume: left-aligned, gray #B0B8D0
- Ask volume: right-aligned, gray #B0B8D0
- Numbers highlighted when imbalance: white for dominant side
- Zero values: not shown (empty string)

### Price level lines (horizontal, via SharpDX or Draw.Line):
Each line has a label anchored to the right:

| Level | Label Format | Color | Style |
|-------|-------------|-------|-------|
| Session VWAP | "VWAP · 19,455" | #FFFFFF80 | Solid 1px |
| VWAP +1σ | "VWAP +1σ · 19,545" | #8A8A8A | Dash 1px |
| VWAP -1σ | "VWAP -1σ · xx,xxx" | #8A8A8A | Dash 1px |
| VWAP +2σ | "VWAP +2σ · xx,xxx" | #5A5A5A | Dash 1px (thin) |
| VWAP -2σ | "VWAP -2σ · xx,xxx" | #5A5A5A | Dash 1px (thin) |
| GEX HVL | "⚡ GEX HVL · 19,620" | #FFD700 | Solid 2px |
| Call Wall | "📞 CALL WALL · 19,600" | #9B59B6 | Solid 1px (purple) |
| Put Wall | "⬇ PUT WALL · xx,xxx" | #E74C3C | Solid 1px (red) |
| IB High | "IBH · 19,xxx" | #00D4AA | Dashed 1px teal |
| IB Low | "IBL · 19,xxx" | #00D4AA | Dashed 1px teal |
| DEV POC | "DEV POC · 19,440" | #FF9500 | Dotted 1px orange |
| pdVAH | "pdVAH · 19,425" | #5AC8FA | Solid 1px cyan |
| pdVAL | "pdVAL · xx,xxx" | #5AC8FA | Solid 1px cyan |
| IGH | "IGH · 19,475" | #FFD700 | Dotted 1px |

### Signal labels on chart (SharpDX rendered boxes):
**TYPE A box:**
```
┌─────────────────────────────┐  ← gold border #FFD700, 1.5px
│ TYPE A · 92pts              │
│ ABSORB·TRESS·ICE·LVN        │
│ 09:34 · A  ▲               │
└─────────────────────────────┘
```
- Background: #1A1500 (very dark gold tint)
- Header: "TYPE A · 92pts" — neon green #00FF87, 9pt bold
- Sub: "ABSORB·TRESS·ICE·LVN" — #C8D0E0, 7.5pt Consolas  
- Footer: "09:34 · A  ▲" — gray #8090B0, 7pt + green ▲
- Box width: 130px, padding: 5px
- Position: above/below the bar depending on direction, offset 8px from bar

**TYPE B box:**
```
┌─────────────────────────────┐  ← gold border, lighter #A08000
│ TYPE B · 78pts              │
│ GEX+TRESS+MICRO>82          │
│ 09:36 DEX                   │
└─────────────────────────────┘
```
- Header: gold #FFD700, 9pt bold
- Sub: #A0A8B8, 7.5pt
- Footer: #6070A0, 7pt

**Triangle markers on chart (below bar for bull, above for bear):**
- Orange filled triangle ▲ at signal point
- Size: 8px
- Color: #FF9500 for neutral, #00FF87 for confirmed bull, #FF4444 for bear

### Sub-signals directly on bars:
**STKt3 marker:**
- Small orange triangle with "STKt3" text below
- Appears at the bar where Stacked T3 (tier 3 stacked imbalance) fires
- STKt1/t2/t3 = 3/5/7+ consecutive imbalances

---

## 1.5 RIGHT PANEL — FULL SPECIFICATION
Width: 230px, background: #0A0C16 tinted

### Panel tab row:
```
[DEEP6]  [GEX]  [LEVELS]  [LOG]
```
Active tab: neon green border-bottom 2px, bright text
Inactive: gray #3A4060

---

### TAB 1: DEEP6 (Primary)

**A. UNIFIED SCORE gauge:**
- Label: "UNIFIED SCORE" — gray #6070A0, 8pt, uppercase
- Circular gauge: 80px diameter
  - Track: dark #1A2040, 8px stroke
  - Progress arc: COLOR by score, 6px stroke
  - Center: score number (e.g. "92"), 18pt bold Consolas
  - Below number: "/ 100" gray, 7pt
  - Arc angle: 270° total (225° start, clockwise)
- Signal type label: "TYPE A · TRIPLE CONFLUENCE" — neon green #00FF87, 10pt bold

**B. LAYER SCORE BARS:**
```
FOOTPRINT   ████████████████████░░░ 22
TRESPASS    ████████████████░░░░░░░ 18
SPOOF       ████████████░░░░░░░░░░░ 11
ICEBERG     ██████████░░░░░░░░░░░░░ 10
MICRO       ███████░░░░░░░░░░░░░░░░  7
VP + CTX    █████████████████████░░ 24
```
- Bar height: 6px
- Track: #161B30
- Colors: FOOTPRINT/TRESPASS/SPOOF/MICRO = #00FF87, ICEBERG = #FF69B4, VP+CTX = #FFD700
- Right number: bold, same color as bar
- Label: 8pt Consolas, #8090B0

**C. LAYER STATUS section:**
9 rows, each row:
```
[●] [Name 14chr     ] [Value          ]
```
Dot colors:
- GREEN: #39D353 — footprint, trespass, counterspoof
- PINK: #FF69B4 — iceberg
- CYAN: #5AC8FA — DEX-ARRAY
- YELLOW: #FFD700 — CVD, GEX, ML Quality

Values (from image):
| Row | Name | Value |
|-----|------|-------|
| 1 | Footprint | ABSORBT |
| 2 | Trespass | +0.68 |
| 3 | CounterSpoof | 0.12 ✓ |
| 4 | Iceberg | BULL @492 |
| 5 | DEX-ARRAY | FIRED ✓ |
| 6 | Microprobability | L:84 S:16 |
| 7 | CVD | +4,218 ↑ |
| 8 | GEX Regime | NEG AMP |
| 9 | ML Sig Quality | P=0.74 +12% |

**D. SIGNAL FEED:**
Each feed item:
```
[TYPE A] Bull Absorption + LVN  19,484  09:34  +E
```
- TYPE A badge: #00FF87 on #001A0D bg
- Text: "Bull Absorption + LVN" — #C0C8E0, 7.5pt
- Price: #8090B0, 7pt
- Time: #506080, 7pt
- "+E" suffix: edge signal indicator

---

### TAB 2: GEX
Display:
- Current GEX level (positive/negative value)
- Gamma flip level (price where GEX = 0)
- Top call walls (sorted by size)
- Top put walls (sorted by size)
- GEX regime label + description
- GEX chart (optional bar chart of GEX by strike)

Layout:
```
GEX REGIME: NEG AMPLIFYING
Gamma Flip: 19,250

CALL WALLS           PUT WALLS
19,600  (2.4B)      19,200  (1.8B)
19,700  (1.9B)      19,100  (1.5B)
19,800  (1.2B)      19,000  (1.1B)

HVL (High Vol Level): 19,620
```

---

### TAB 3: LEVELS
All key price levels organized:

```
SESSION LEVELS
  VWAP       19,455
  VAH        19,545
  VAL        19,365
  DEV POC    19,440

INITIAL BALANCE
  IBH        19,xxx
  IBL        19,xxx
  IB Range   xx ticks (NARROW)
  Status     C-CONFIRMED

PREVIOUS DAY
  pdVAH      19,425
  pdVAL      18,xxx
  pdPOC      19,xxx
  
OPTIONS LEVELS
  Call Wall  19,600
  Put Wall   19,200
  GEX HVL    19,620
  Gamma Flip 19,250
  
CONTEXT
  VWAP Zone  +1σ (BETWEEN VAH-VWAP)
  POC Status MIGRATING ↑  8 bars
  VWAP-POC   28 ticks (TRENDING)
```

---

### TAB 4: LOG
Timestamped event log:
```
09:36:12  TYPE B 78pts  GEX+TRESS+MICRO  SHORT  19,492
09:34:08  TYPE A 92pts  ABSORB+TRESS+ICE LONG   19,484
09:33:45  STKt3         Stacked T3 Bull  —      19,490
09:33:21  TRESPASS      Imb +0.68 Bull   —      19,488
09:32:55  DOM LIVE      Rithmic L2 conn  —      —
```
Each row: timestamp | signal type | description | direction | price
Color: TYPE A green, TYPE B gold, others gray

---

## ════════════════════════════════════════════════════════
## SECTION 2: COMPLETE ALGORITHM SPECIFICATIONS
## ════════════════════════════════════════════════════════

## 2.1 DEX-ARRAY Algorithm
**Definition:** Delta EXpansion ARRAY — detects when consecutive bars form a "delta array" pattern where delta is consistently one-directional AND expanding.

```
// A "DEX array" requires N consecutive bars where:
// 1. Delta sign is same direction each bar
// 2. Absolute delta is increasing (expansion) OR consistently above avg
// 3. Price is confirming direction

int DEX_LOOKBACK = 3;  // min consecutive bars for array

bool IsDexArray(int dir)  // dir = +1 bull, -1 bear
{
    if (CurrentBar < DEX_LOOKBACK) return false;
    
    // Check N consecutive bars
    double prevDelta = 0;
    bool arrayForming = true;
    for (int i = DEX_LOOKBACK - 1; i >= 0; i--)
    {
        double barDelta = vb.Volumes[CurrentBar - i].BarDelta;
        
        // Check direction consistency
        if (Math.Sign(barDelta) != dir) { arrayForming = false; break; }
        
        // Check expansion (each bar's delta > previous, OR > avg)
        double avgD = _emaVol * 0.1;  // 10% of avg vol as delta threshold
        if (Math.Abs(barDelta) < avgD) { arrayForming = false; break; }
        
        prevDelta = barDelta;
    }
    return arrayForming;
}

// DEX fires when array forms AND current bar confirms direction
_dexFired = IsDexArray(_signalDir);
_dexDir   = _signalDir;
_dexStatus = _dexFired ? "FIRED ✓" : "—";
```

**Scoring contribution:** DEX-ARRAY firing adds 8 pts to VP+CTX score when aligned with primary direction. It can upgrade TYPE C → TYPE B or TYPE B → TYPE A.

---

## 2.2 STKt Signals (Stacked Imbalance Tiers)

**Definition:** Stacked imbalance at specific threshold tiers.

```
// Tier thresholds:
// STKt1: 3 consecutive imbalances (basic signal)
// STKt2: 5 consecutive imbalances (medium signal)
// STKt3: 7+ consecutive imbalances (high-conviction)

int GetStackedTier(bool bullSide)
{
    int stack = 0;
    int maxStack = 0;
    
    for (double p = Low[0]; p < High[0]; p += TickSize)
    {
        double ask = vb.Volumes[CurrentBar].GetAskVolumeForPrice(p + TickSize);
        double bid = vb.Volumes[CurrentBar].GetBidVolumeForPrice(p);
        
        bool imbalanced = bullSide
            ? (bid > 0 && ask / bid >= ImbalanceRatio)  // bull: ask dominates
            : (ask > 0 && bid / ask >= ImbalanceRatio); // bear: bid dominates
            
        if (imbalanced) { stack++; maxStack = Math.Max(maxStack, stack); }
        else            { stack = 0; }
    }
    
    if (maxStack >= 7) return 3;  // STKt3
    if (maxStack >= 5) return 2;  // STKt2
    if (maxStack >= 3) return 1;  // STKt1
    return 0;
}
```

**Chart rendering:** Small triangle marker + "STKt3" text label directly on the bar at the price level where stacking begins.

---

## 2.3 IB Pattern Classification

```
// IB Type
double ibRange = _ibHigh - _ibLow;
double avgIbRange = GetHistoricalAvgIbRange();  // Rolling 20-session avg
IbType ibType = ibRange > avgIbRange * 1.3 ? IbType.Wide :
                ibRange < avgIbRange * 0.7 ? IbType.Narrow : IbType.Normal;

// IB Pattern Codes
// A = Acceptance: price extends beyond IB in first 30 min, then accepts
// B = Balance: price oscillates within IB, both extensions rejected
// C = Compression: price compresses to IB midpoint (narrowing)
// D = Distribution: price one-directional move from IB
string ibPattern = "—";
if (price returns to IBMid after extension): ibPattern = "A";
if (IBL and IBH both tested, neither broken): ibPattern = "B";
if (price range < 50% of IB range): ibPattern = "C";
if (price sustained above IBH or below IBL): ibPattern = "D";

// IB Confirmation = pattern is clearly established (30+ min in)
bool ibConfirmed = (Time[0] - _ibEndTime).TotalMinutes > 30;

// Pill text
string ibPillText = $"{ibType} · {ibPattern}-CONFIRMED";
// → "NARROW · C-CONFIRMED"
```

---

## 2.4 VWAP Zone Classification
```
// Zones (from distance to VWAP in std devs)
string GetVwapZone(double price, double vwap, double sd)
{
    double dist = price - vwap;
    if (dist > 2 * sd)       return "+2σ";
    if (dist > 1 * sd)       return "+1σ";  // ← IMAGE shows "+1σ"
    if (dist > 0.25 * sd)    return "ABOVE";
    if (dist > -0.25 * sd)   return "AT";
    if (dist > -1 * sd)      return "BELOW";
    if (dist > -2 * sd)      return "-1σ";
    return "-2σ";
}
```

---

## 2.5 POC Migration Status
```
// Track POC movement across last N bars
int _pocMigBars = 0;
bool _pocMigUp = false;

// On each bar:
if (curPOC > _prevPOC + TickSize * 0.5) {
    if (_pocMigUp) _pocMigBars++;      // continuing up
    else { _pocMigUp = true; _pocMigBars = 1; }  // started up
}
else if (curPOC < _prevPOC - TickSize * 0.5) {
    if (!_pocMigUp) _pocMigBars++;
    else { _pocMigUp = false; _pocMigBars = 1; }
}
else { _pocMigBars = 0; }  // POC stable

// Pill: "MIGRATING ↑ · 8 BARS"
string pocPillText = _pocMigBars > 0
    ? $"MIGRATING {(_pocMigUp ? "↑" : "↓")} · {_pocMigBars} BARS"
    : "POC STABLE";
```

---

## 2.6 VWAP-POC Relationship
```
// Distance between session VWAP and Developing POC
double vwapPocDist = Math.Abs(_vwap - _devPOC) / TickSize;

// Regime classification
string vwapPocRegime = vwapPocDist > 25 ? "TRENDING" :
                       vwapPocDist > 10 ? "DIVERGING" : "BALANCED";

// Pill: "28 ticks · TRENDING"
string vwapPocPill = $"{(int)vwapPocDist} ticks · {vwapPocRegime}";
```

---

## 2.7 ML Signal Quality — "+12%" Component
```
// Track rolling average of ML quality scores (last 20 signals)
Queue<double> _mlHistory = new Queue<double>(20);
double _mlBaseline = double.NaN;

// After each score computation:
_mlHistory.Enqueue(_mlScore);
if (_mlHistory.Count > 20) _mlHistory.Dequeue();
_mlBaseline = _mlHistory.Average();

// % deviation from recent average
double mlDevPct = _mlBaseline > 0
    ? (_mlScore - _mlBaseline) / _mlBaseline * 100
    : 0;

// Status: "P=0.74 +12%"
_mlStatus = $"P={qualityProb:0.00} {(mlDevPct >= 0 ? "+" : "")}{mlDevPct:0}%";
```

---

## 2.8 Day Type Classification
```
// Full day type taxonomy:
// TREND BULL:  Strong directional move up throughout session
// TREND BEAR:  Strong directional move down throughout session
// FADE BULL:   Opened up, faded below prior close
// FADE BEAR:   Opened down, faded above prior close
// BALANCE:     Oscillating within prior day's range
// BREAKOUT UP: Clean break above prior range with momentum
// BREAKOUT DN: Clean break below prior range with momentum
// NEUTRAL:     No clear pattern yet (first 30 min)

DayType ClassifyDayType()
{
    if ((Time[0] - _sessionOpen).TotalMinutes < 30)
        return DayType.Unknown;
    
    double openToNow = Close[0] - _openPrice;
    double rangeToNow = _intraHigh - _intraLow;
    bool trendingUp = Close[0] > _openPrice + TickSize * 12;
    bool trendingDn = Close[0] < _openPrice - TickSize * 12;
    bool balanced   = rangeToNow < TickSize * 20;
    
    if (trendingUp && rangeToNow > TickSize * 30)  return DayType.TrendBull;
    if (trendingDn && rangeToNow > TickSize * 30)  return DayType.TrendBear;
    if (balanced)                                   return DayType.BalanceDay;
    return DayType.Unknown;
}
```

---

## ════════════════════════════════════════════════════════
## SECTION 3: SHARPDX RENDERING ARCHITECTURE
## ════════════════════════════════════════════════════════

## 3.1 OnRender Structure
```csharp
protected override void OnRender(ChartControl cc, ChartScale cs)
{
    base.OnRender(cc, cs);
    
    // Ensure brushes initialized
    if (!_brushesInitialized) InitBrushes();
    
    // 1. Footprint cells (SharpDX rectangles + text)
    RenderFootprintBars(cc, cs);
    
    // 2. Price level lines (VWAP, IB, GEX, pdVAH, etc.)
    RenderPriceLevels(cc, cs);
    
    // 3. Signal boxes (TYPE A/B labels)
    RenderSignalBoxes(cc, cs);
    
    // 4. Sub-bar markers (STKt3, delta values)
    RenderBarMarkers(cc, cs);
    
    // 5. Build WPF panel if not yet built
    if (_rootBorder == null) BuildPanel();
}
```

## 3.2 Footprint Cell Rendering
```csharp
private void RenderFootprintBars(ChartControl cc, ChartScale cs)
{
    bool isVol = BarsArray[0].BarsType is VolumetricBarsType;
    if (!isVol) return;
    var vb = BarsArray[0].BarsType as VolumetricBarsType;
    
    int firstBar = Math.Max(0, ChartBars.FromIndex);
    int lastBar  = Math.Min(CurrentBar, ChartBars.ToIndex);
    
    for (int barIdx = firstBar; barIdx <= lastBar; barIdx++)
    {
        int    xLeft  = cc.GetXByBarIndex(ChartBars, barIdx);
        int    xRight = cc.GetXByBarIndex(ChartBars, barIdx + 1) - 1;
        float  barW   = xRight - xLeft;
        
        double hi = Highs[0].GetValueAt(barIdx);
        double lo = Lows[0].GetValueAt(barIdx);
        double poc = vb.Volumes[barIdx].PointOfControl;
        
        // Render each price level cell
        for (double price = lo; price <= hi; price += TickSize)
        {
            float yTop = (float)cs.GetYByValue(price + TickSize);
            float yBot = (float)cs.GetYByValue(price);
            float cellH = yBot - yTop;
            if (cellH < 2) continue;  // too small to render
            
            double bid = vb.Volumes[barIdx].GetBidVolumeForPrice(price);
            double ask = vb.Volumes[barIdx].GetAskVolumeForPrice(price);
            bool   isPOC = Math.Abs(price - poc) < TickSize * 0.5;
            
            // Cell background color
            var bgBrush = GetCellBrush(bid, ask, isPOC);
            RenderTarget.FillRectangle(
                new RectangleF(xLeft, yTop, barW, cellH),
                bgBrush);
            
            // Bid/Ask text
            if (bid > 0 || ask > 0)
            {
                string bidStr = bid > 0 ? bid.ToString("0") : "";
                string askStr = ask > 0 ? ask.ToString("0") : "";
                string priceStr = (price % 1 == 0) 
                    ? ((int)price % 100).ToString("D2") 
                    : price.ToString("0.00");
                
                // Render text (bid | price | ask)
                // Left: bid, Center: price, Right: ask
                RenderCellText(xLeft, yTop, barW, cellH, bidStr, priceStr, askStr,
                    bid, ask);
            }
        }
        
        // Delta row below bar
        RenderDeltaRow(cc, cs, barIdx, vb);
    }
}
```

## 3.3 Price Level Lines (SharpDX)
```csharp
private void RenderPriceLevels(ChartControl cc, ChartScale cs)
{
    float chartWidth = (float)cc.ActualWidth;
    
    // VWAP line
    if (!double.IsNaN(_vwap))
        DrawPriceLine(cs, _vwap, chartWidth, "VWAP", _vwap, 
            _brushWhite40, DashStyle.Solid, 1f);
    
    // VAH (VWAP +1σ)
    if (!double.IsNaN(_vah))
        DrawPriceLine(cs, _vah, chartWidth, $"VWAP +1σ · {_vah:0.00}",
            _vah, _brushGray50, DashStyle.Dash, 1f);
    
    // VAL (VWAP -1σ)  
    if (!double.IsNaN(_val))
        DrawPriceLine(cs, _val, chartWidth, $"VWAP -1σ · {_val:0.00}",
            _val, _brushGray50, DashStyle.Dash, 1f);
    
    // IB levels
    if (_ibComplete)
    {
        DrawPriceLine(cs, _ibHigh, chartWidth, $"IBH · {_ibHigh:0.00}",
            _ibHigh, _brushTeal, DashStyle.DashDot, 1f);
        DrawPriceLine(cs, _ibLow,  chartWidth, $"IBL · {_ibLow:0.00}",
            _ibLow,  _brushTeal, DashStyle.DashDot, 1f);
    }
    
    // DEV POC
    if (!double.IsNaN(_devPOC))
        DrawPriceLine(cs, _devPOC, chartWidth, $"DEV POC · {_devPOC:0.00}",
            _devPOC, _brushOrange, DashStyle.Dot, 1f);
    
    // GEX levels (from user input)
    if (GexHvl > 0)
        DrawPriceLineWithIcon(cs, GexHvl, chartWidth, 
            $"⚡ GEX HVL · {GexHvl:0.00}", _brushGold, DashStyle.Solid, 2f);
    if (CallWall > 0)
        DrawPriceLineWithIcon(cs, CallWall, chartWidth,
            $"📞 CALL WALL · {CallWall:0.00}", _brushPurple, DashStyle.Solid, 1f);
}
```

---

## ════════════════════════════════════════════════════════
## SECTION 4: COMPLETE BUILD ORDER (PHASES)
## ════════════════════════════════════════════════════════

### Phase 1 (DONE): Foundation + WPF right panel shell ✅
### Phase 2 (DONE): All 7 engines with algorithms ✅
### Phase 3: Complete UI rebuild

**Phase 3a: Header bar**
- Add row above chart via ChartWindow.MainTabControl manipulation
- All 10 header columns
- DOM LIVE indicator with pulse animation
- Color-coded values

**Phase 3b: Left vertical tab bar**
- Add column to left of ChartGrid
- 9 tab buttons (IN, 3MIN, 5MIN, FOOTPRINT, VOL PROFILE, VWAP±2σ, GEX LEVELS, IB LEVELS, SIGNALS)
- Tab selection state
- Active = green border + bright text

**Phase 3c: Status pills row**  
- Add row between tabs and chart area
- 9 pills with live data binding
- Auto-update from session context

**Phase 3d: SharpDX footprint rendering**
- OnRender with VolumetricBarsType cell rendering
- Bid/ask text inside cells
- Cell color by imbalance ratio
- POC highlighting
- Delta row below bars

**Phase 3e: Price level lines**
- SharpDX line rendering for all 15 levels
- Label anchored to right side
- Special icons for GEX HVL and Call/Put Walls

**Phase 3f: Signal label boxes**  
- TYPE A/B bordered boxes directly on chart
- STKt3 triangle markers
- Delta text row

**Phase 3g: Right panel tabs 2-4**
- GEX tab content
- LEVELS tab content
- LOG tab content

**Phase 3h: DEX-ARRAY + STKt engine**
- Implement DEX-ARRAY detection
- Wire to panel layer status
- Implement STKt1/t2/t3 tier detection
- Render STKt markers on chart

**Phase 3i: ML baseline tracking**
- Rolling P history
- "+12%" deviation display

---

## ════════════════════════════════════════════════════════
## SECTION 5: ADDITIONAL PARAMETERS NEEDED
## ════════════════════════════════════════════════════════

New parameters (from image analysis):
```
// GEX levels (user-supplied or from GEX engine)
[NinjaScriptProperty] double GexHvl       // High Volatility Level
[NinjaScriptProperty] double CallWall     // Largest call strike
[NinjaScriptProperty] double PutWall      // Largest put strike
[NinjaScriptProperty] double GammaFlip   // GEX=0 level

// Previous day levels (user-supplied or from Vol Profile)  
[NinjaScriptProperty] double PdVah       // prev day Value Area High
[NinjaScriptProperty] double PdVal       // prev day Value Area Low
[NinjaScriptProperty] double PdPoc       // prev day POC

// Footprint display
[NinjaScriptProperty] double ImbalanceRatio  // default 1.5 (150%)
[NinjaScriptProperty] int    MinVolDisplay   // min vol to show in cell
[NinjaScriptProperty] bool   ShowDeltaRow    // show delta below bars
[NinjaScriptProperty] bool   ShowStkMarkers  // show STKt markers
[NinjaScriptProperty] bool   ShowPriceLevels // show all price lines
[NinjaScriptProperty] bool   ShowSignalBoxes // show TYPE A/B boxes

// DEX Array
[NinjaScriptProperty] int    DexArrayLookback  // bars for array (default 3)

// IB tracking
[NinjaScriptProperty] int    IbMinutes        // IB window (default 60)
[NinjaScriptProperty] double AvgIbRangeTicks  // historical avg (default 30)
```

---

## ════════════════════════════════════════════════════════
## SECTION 6: COLOR SYSTEM (COMPLETE)
## ════════════════════════════════════════════════════════
```
// Background family
BG_PRIMARY       = #0A0C16  (chart background)
BG_PANEL         = #0D0F1E  (header/panel background)
BG_TAB_ACTIVE    = #08090F  (active tab background)
BG_PILL          = #141828  (default pill background)

// Text family
TEXT_PRIMARY     = #E0E8FF  (main content text)
TEXT_SECONDARY   = #8090B0  (labels, secondary info)
TEXT_DIM         = #4A5070  (inactive/disabled)

// Signal family
SIGNAL_TYPE_A    = #00FF87  (neon lime green)
SIGNAL_TYPE_B    = #FFD700  (gold)
SIGNAL_TYPE_C    = #5AC8FA  (ice blue)
SIGNAL_QUIET     = #2A3050  (muted)

// Status family
DOT_GREEN        = #39D353  (footprint, trespass, micro)
DOT_PINK         = #FF69B4  (iceberg)
DOT_CYAN         = #5AC8FA  (DEX-ARRAY)
DOT_YELLOW       = #FFD700  (CVD, GEX, ML)
DOT_INACTIVE     = #282E48  (not firing)

// Market data family
COLOR_BUY        = #00D080  (bullish)
COLOR_SELL       = #FF4040  (bearish)
COLOR_NEUTRAL    = #404868  (balanced)
COLOR_ABSORB     = #FFB000  (absorption)
COLOR_EXHAUST    = #FF6B35  (exhaustion)

// Price level family
COLOR_VWAP       = #FFFFFF60 (VWAP main)
COLOR_VA         = #808080   (value area bands)
COLOR_IB         = #00D4AA   (initial balance - teal)
COLOR_POC        = #FF9500   (developing POC - orange)
COLOR_PDVAH      = #5AC8FA   (prev day levels - cyan)
COLOR_GEX        = #FFD700   (GEX levels - gold)
COLOR_CALLWALL   = #9B59B6   (call wall - purple)
COLOR_PUTWALL    = #E74C3C   (put wall - red)

// Pill family (each pill has unique tint)
PILL_TREND       = bg:#0B3D1E text:#00FF87
PILL_IB          = bg:#1A1E35 text:#8090C0
PILL_IB_CONF     = bg:#0D3535 text:#00D4AA
PILL_GEX         = bg:#1A1E35 text:#8090C0
PILL_NEG_GAMMA   = bg:#3D0B0B text:#FF4444
PILL_DEV_POC     = bg:#1A1E35 text:#8090C0
PILL_POC_MIG     = bg:#3D2800 text:#FF9500
PILL_VWAP_POC    = bg:#1A1E35 text:#8090C0
PILL_TRENDING    = bg:#0D2535 text:#5AC8FA
```

---

## ════════════════════════════════════════════════════════
## SECTION 7: TYPOGRAPHY
## ════════════════════════════════════════════════════════
```
Primary font:  "Consolas" (monospace — all numbers, status values)
Secondary:     "Segoe UI" or "Inter" (labels)
Score number:  Consolas 18pt bold (92)
Header price:  Consolas 18pt bold (19,484.00)
Signal type:   Consolas 10pt bold (TYPE A · TRIPLE CONFLUENCE)  
Layer names:   Consolas 8pt (Footprint, Trespass...)
Bar delta:     Consolas 8pt (△ +1,340)
Cell values:   Consolas 7-8pt (bid/ask volume numbers)
Pill text:     Consolas 8pt bold (TREND BULL)
```
