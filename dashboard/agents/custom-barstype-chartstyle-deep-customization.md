# DEEP6 NinjaTrader 8 Custom BarsType + ChartStyle Reference

**Audience:** AI graphics/orderflow agent for DEEP6. Treat this as the canonical "deep customization" cheat-sheet for NT8 visual extensibility — what the API actually exposes, what it secretly hides, what you can subclass vs. what you must replace, and exactly the patterns that work for production footprint rendering.

---

## 0. Mental model — the 30-second version

NinjaTrader 8 splits "what a bar contains" from "how a bar is drawn":

```
                           ┌──────────────────────────┐
   raw market data         │   BarsType (data)        │     ChartBars (cache)
   (ticks / minutes        │   - OnDataPoint()        │     - bar OHLCV
    / market depth)  ─────▶│   - AddBar/UpdateBar     │────▶ - per-bar custom
                           │   - SessionIterator      │       payloads (e.g.
                           │   - per-bar custom data  │       Volumes[idx])
                           └──────────────────────────┘
                                       │
                                       ▼
                           ┌──────────────────────────┐
                           │   ChartStyle (render)    │     pixels on screen
                           │   - OnRender(ctrl,       │────▶ via SharpDX
                           │       scale, chartBars)  │       (Direct2D)
                           │   - BarWidth / brushes   │
                           └──────────────────────────┘
```

Two **independent** classes you subclass: `BarsType` (what's in a bar) and `ChartStyle` (how a bar paints). They are paired via `BarsType.DefaultChartStyle` — but a user can apply any compatible style to any bar type.

A third class that lives on top is the **Indicator**, which can also override `OnRender` and reach into the bar payload via `Bars.BarsSeries.BarsType as YourCustomBarsType`. For DEEP6 the rule of thumb is:

| You want to … | Do this |
|---|---|
| Add tick-by-tick aggregation / a custom "bar" definition | Subclass `BarsType` |
| Replace the default candle/footprint rendering | Subclass `ChartStyle` |
| Overlay markers, bands, signals on top of any chart | Write an `Indicator` with `OnRender` |
| Persist DOM heatmap snapshots per slot | Subclass `BarsType` + write paired `Indicator`/`ChartStyle` |
| Replace NT8's stock VolumetricBarsType entirely | Subclass `BarsType` (DEEP6 footprint) **and** subclass `ChartStyle` (DEEP6 cell renderer) |

---

## 1. BarsType — complete API surface

`NinjaTrader.NinjaScript.BarsTypes.BarsType` is the abstract base. Your custom file lives at `Documents\NinjaTrader 8\bin\Custom\BarsTypes\Deep6FootprintBarsType.cs` and is auto-compiled by NT8 on F5.

### 1.1 Class shell (mandatory pattern)

```csharp
namespace NinjaTrader.NinjaScript.BarsTypes
{
    public class Deep6FootprintBarsType : BarsType
    {
        // -- per-bar custom payload (NOT auto-serialized)
        [System.Xml.Serialization.XmlIgnore]
        public List<Deep6FootprintBar> Footprint { get; private set; } = new();

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name              = "DEEP6 Footprint";
                Description       = "DEEP6 institutional footprint — bid/ask volume per price tick + custom imbalance";
                BarsPeriod        = new BarsPeriod
                {
                    BarsPeriodType     = (BarsPeriodType)60606,        // unique id; see §1.4
                    BarsPeriodTypeName = "DEEP6 Footprint(60606)",
                    Value              = 1                              // minutes per bar (default)
                };
                BuiltFrom         = BarsPeriodType.Tick;                // we need every tick
                DefaultChartStyle = (ChartStyleType)60606;              // pair with our style
                DaysToLoad        = 5;
                IsIntraday        = true;
                IsTimeBased       = true;                               // minute-driven container
            }
            else if (State == State.Configure)
            {
                Properties.Remove(Properties.Find("BaseBarsPeriodType",     true));
                Properties.Remove(Properties.Find("PointAndFigurePriceType", true));
                Properties.Remove(Properties.Find("ReversalType",            true));
                SetPropertyName("Value",  "Bar Minutes");
                SetPropertyName("Value2", "Ticks/Level");
            }
        }

        public override void ApplyDefaultBasePeriodValue(BarsPeriod p) { }
        public override void ApplyDefaultValue(BarsPeriod p)
        {
            p.Value  = 1;     // 1-minute footprint
            p.Value2 = 1;     // 1 tick per level (max resolution)
        }

        public override int GetInitialLookBackDays(BarsPeriod p, TradingHours t, int barsBack) => 5;
        public override double GetPercentComplete(Bars bars, DateTime now) => 1.0d;

        public override string ChartLabel(DateTime t) =>
            t.ToString("T", Core.Globals.GeneralOptions.CurrentCulture);

        protected override void OnDataPoint(
            Bars bars, double open, double high, double low, double close,
            DateTime time, long volume, bool isBar, double bid, double ask)
        {
            // see §4 for the actual footprint logic
        }
    }
}
```

### 1.2 `OnDataPoint` — the only signature

There is **one** `OnDataPoint` signature:

```csharp
protected override void OnDataPoint(
    Bars     bars,        // the bars object you are building
    double   open, high, low, close,
    DateTime time, long volume,
    bool     isBar,       // true = a finished base bar, false = intra-bar update
    double   bid, double ask    // historical: only valid w/ TickReplay OR 1-tick base
)
```

Critical semantics:
- Called **once per record of the base series**. With `BuiltFrom = BarsPeriodType.Tick` you get one call per tick.
- `bars.GetOpen(idx)` reads back what **you** wrote with `AddBar`, not the input parameters.
- `bid`/`ask` are zero unless TickReplay is enabled or you pull a 1-tick base. **For DEEP6 footprint always use `BuiltFrom = BarsPeriodType.Tick` and require TickReplay = ON.**
- Real-time: `OnDataPoint` fires for every processed tick; historical: same thing only if TickReplay is on.

### 1.3 The three mutators

```csharp
AddBar(bars, open, high, low, close, time, volume);
UpdateBar(bars, high, low, close, time, volume);   // updates the LAST bar only
RemoveLastBar(bars);                                // requires IsRemoveLastBarSupported = true
```

**Rule:** `AddBar` exactly once when your bar-completion condition fires; `UpdateBar` on every other tick. Always set price values rounded to tick:
```csharp
double snapped = bars.Instrument.MasterInstrument.RoundToTickSize(rawPrice);
```

### 1.4 `BarsPeriodType` registration — the `int` cast trick

`BarsPeriodType` is a normal C# enum but NT8 lets you cast any int to it:
```csharp
BarsPeriod = new BarsPeriod {
    BarsPeriodType     = (BarsPeriodType)60606,
    BarsPeriodTypeName = "DEEP6 Footprint(60606)"
};
```
Use a value > 1023 (NT recommended floor) and ideally > 10000 to avoid collision. **Two scripts that pick the same id will silently clobber each other.**

### 1.5 Full property table

| Member | Type | Set in | Purpose |
|---|---|---|---|
| `Name` | string | SetDefaults | Internal id + UI label |
| `Description` | string | SetDefaults | Tooltip |
| `BarsPeriod` | BarsPeriod | SetDefaults | Default period config + custom enum id |
| `BuiltFrom` | BarsPeriodType | SetDefaults | Underlying base series (Tick / Minute / Day…) |
| `DefaultChartStyle` | ChartStyleType | SetDefaults | What style appears first |
| `DaysToLoad` | int | SetDefaults | Default history depth |
| `IsTimeBased` | bool | SetDefaults | True for minute-anchored bars |
| `IsIntraday` | bool | SetDefaults | True if bars span < 1 day |
| `IsRemoveLastBarSupported` | bool override | class | Rarely true |
| `SkipCaching` | bool override | class | **Set true** if you store custom per-bar state |

### 1.6 Session iteration — the canonical pattern

```csharp
protected override void OnDataPoint(Bars bars, ..., DateTime time, long volume, bool isBar, ...)
{
    if (SessionIterator == null)
        SessionIterator = new SessionIterator(bars);

    bool isNewSession = SessionIterator.IsNewSession(time, isBar);
    if (isNewSession)
        SessionIterator.GetNextSession(time, isBar);

    if (bars.Count == 0 || (bars.IsResetOnNewTradingDay && isNewSession))
    {
        // initialise per-session state, AddBar with seed values
    }
    else
    {
        // the normal hot path
    }
}
```

Call `IsNewSession` **once** per `OnDataPoint`. Calling it twice produces duplicate session prints around futures rollovers.

### 1.7 Cache pitfall — `SkipCaching`

NT8 caches built bars to `Documents\NinjaTrader 8\db\cache`. If your BarsType holds **extra per-bar payload** (footprint dict, DOM snapshot) you must opt out:

```csharp
public override bool SkipCaching => true;
```

Otherwise NT8 will hand you cached OHLC on chart reload but your `Footprint` list will be empty — you'll see candles with no histogram. **For DEEP6, set `SkipCaching = true` and accept that footprint is rebuilt from history on chart load** (the simpler, more correct option for live trading).

---

## 2. The built-in `VolumetricBarsType` — every accessor you can call

Cast pattern:
```csharp
var vt = Bars.BarsSeries.BarsType
            as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
if (vt == null) return;
var vb = vt.Volumes[CurrentBar];
```

### 2.1 `VolumetricBar` properties

| Member | Type | Meaning |
|---|---|---|
| `BarDelta` | long | Total bar delta (asks − bids) |
| `CumulativeDelta` | long | Running cumulative delta; **resets at session break** |
| `MaxSeenDelta` | long | High-water delta seen intrabar |
| `MinSeenDelta` | long | Low-water delta seen intrabar |
| `DeltaSh` | long | Delta accumulated since last touch of bar high |
| `DeltaSl` | long | Delta accumulated since last touch of bar low |
| `Trades` | long | Number of trade events in bar |
| `TotalBuyingVolume` | long | Aggressive buy volume |
| `TotalSellingVolume` | long | Aggressive sell volume |

### 2.2 `VolumetricBar` methods

| Signature | Returns | Notes |
|---|---|---|
| `GetAskVolumeForPrice(double price)` | long | Volume at the ask at that price |
| `GetBidVolumeForPrice(double price)` | long | Volume at the bid at that price |
| `GetTotalVolumeForPrice(double price)` | long | Sum |
| `GetDeltaForPrice(double price)` | long | Ask − Bid at that price |
| `GetDeltaPercent()` | double | Bar delta as % of bar volume |
| `GetMaximumVolume(bool? askVolume, out double price)` | long | `null` = combined, returns POC |
| `GetMaximumPositiveDelta()` | long | Largest positive horizontal delta in bar |
| `GetMaximumNegativeDelta()` | long | Largest negative horizontal delta in bar |

### 2.3 What VolumetricBarsType doesn't give you (why DEEP6 should replace it)

- No order-by-order data
- No resting-liquidity context — only filled trades
- No way to back-fill bid/ask without TickReplay
- `BidAsk` classification is "at-bid / at-ask"; never "above-ask" or "below-bid" stops
- `ticksPerLevel > 1` discards information irreversibly
- Cumulative delta resets at session break with no override hook
- Bid/ask brushes hard-coded to ChartStyle properties

### 2.4 `TickType` enum

`NinjaTrader.Cbi.TickType`: `BelowBid`, `AtBid`, `BetweenBidAsk`, `AtAsk`, `AboveAsk`. NT8's volumetric only uses `AtBid` vs `AtAsk` for delta. **DEEP6's custom BarsType should keep all five buckets** — `AboveAsk` and `BelowBid` are exactly the iceberg-clearing prints you want.

---

## 3. Other built-in BarsTypes worth studying

NT8 ships these source-readable in `Documents\NinjaTrader 8\bin\Custom\BarsTypes\`:
- `@TickBarsType.cs` — canonical session-iterator usage; smallest sensible reference
- `@MinuteBarsType.cs` — time-driven aggregation reference
- `@RangeBarsType.cs` — uses `RemoveLastBar` + complex re-shaping
- `@RenkoBarsType.cs` — example of fixed-step price-driven bar
- `@HeikinAshiBarsType.cs` — uses `RoundToTickSize` properly
- `@LineBreakBarsType.cs` — multi-bar look-back logic
- `@PointAndFigureBarsType.cs` — most exotic
- `@VolumeBarsType.cs` — cumulative volume gate
- `@VolumetricBarsType.cs` — **read this entire file**

---

## 4. Building DEEP6 footprint BarsType from scratch

### 4.1 The data model

```csharp
public sealed class Deep6FootprintBar
{
    // sparse price → (bid, ask, betweenBidAsk, aboveAsk, belowBid) volumes
    public readonly Dictionary<double, long[]> Cells = new();
    // index: 0=bid, 1=ask, 2=between, 3=aboveAsk, 4=belowBid

    public long BarDelta;
    public long CumulativeDelta;
    public long MaxSeenDelta, MinSeenDelta;
    public long Trades;
    public long TotalVolume;

    public double Poc;
    public double Vah, Val;
    public long Imbalance;
    public long AbsorptionScore;

    public void Apply(double price, long size, NinjaTrader.Cbi.TickType type)
    {
        if (!Cells.TryGetValue(price, out var arr))
            Cells[price] = arr = new long[5];
        switch (type)
        {
            case NinjaTrader.Cbi.TickType.AtBid:        arr[0] += size; BarDelta -= size; break;
            case NinjaTrader.Cbi.TickType.AtAsk:        arr[1] += size; BarDelta += size; break;
            case NinjaTrader.Cbi.TickType.BetweenBidAsk: arr[2] += size; break;
            case NinjaTrader.Cbi.TickType.AboveAsk:     arr[3] += size; BarDelta += size; break;
            case NinjaTrader.Cbi.TickType.BelowBid:     arr[4] += size; BarDelta -= size; break;
        }
        TotalVolume += size;
        Trades++;
        if (BarDelta > MaxSeenDelta) MaxSeenDelta = BarDelta;
        if (BarDelta < MinSeenDelta) MinSeenDelta = BarDelta;
    }
}
```

### 4.2 The `OnDataPoint` body

```csharp
private DateTime _curBarStart = DateTime.MinValue;
private long _sessionCumDelta;
private static readonly TimeSpan BarSpan = TimeSpan.FromMinutes(1);

protected override void OnDataPoint(
    Bars bars, double open, double high, double low, double close,
    DateTime time, long volume, bool isBar, double bid, double ask)
{
    if (SessionIterator == null) SessionIterator = new SessionIterator(bars);
    bool newSession = SessionIterator.IsNewSession(time, isBar);
    if (newSession) { SessionIterator.GetNextSession(time, isBar); _sessionCumDelta = 0; }

    double price = bars.Instrument.MasterInstrument.RoundToTickSize(close);

    NinjaTrader.Cbi.TickType tt;
    if      (ask > 0 && price >  ask) tt = NinjaTrader.Cbi.TickType.AboveAsk;
    else if (ask > 0 && price == ask) tt = NinjaTrader.Cbi.TickType.AtAsk;
    else if (bid > 0 && price == bid) tt = NinjaTrader.Cbi.TickType.AtBid;
    else if (bid > 0 && price <  bid) tt = NinjaTrader.Cbi.TickType.BelowBid;
    else                              tt = NinjaTrader.Cbi.TickType.BetweenBidAsk;

    DateTime slot = new(time.Year, time.Month, time.Day, time.Hour, time.Minute, 0);

    if (bars.Count == 0 || slot != _curBarStart || (bars.IsResetOnNewTradingDay && newSession))
    {
        _curBarStart = slot;
        var fb = new Deep6FootprintBar();
        fb.Apply(price, volume, tt);
        fb.CumulativeDelta = _sessionCumDelta + fb.BarDelta;
        Footprint.Add(fb);
        AddBar(bars, price, price, price, price, slot.Add(BarSpan), volume);
    }
    else
    {
        var fb = Footprint[^1];
        fb.Apply(price, volume, tt);
        fb.CumulativeDelta = _sessionCumDelta + fb.BarDelta;

        double h = Math.Max(bars.GetHigh(bars.Count - 1), price);
        double l = Math.Min(bars.GetLow (bars.Count - 1), price);
        long  v = bars.GetVolume(bars.Count - 1) + volume;
        UpdateBar(bars, h, l, price, slot.Add(BarSpan), v);
    }

    _sessionCumDelta = Footprint[^1].CumulativeDelta;
    bars.LastPrice = price;
}
```

### 4.3 Performance budget at 1000 ticks/sec

| Op | ns | Fits at 1000 tps? |
|---|---|---|
| `Dictionary<double,long[]>` get/set on warm key | ~50–80 ns | yes |
| `RoundToTickSize` | ~40 ns (interop) | yes |
| `AddBar`/`UpdateBar` per tick | ~3–8 µs | yes (0.3–0.8% CPU) |
| `SessionIterator.IsNewSession` (per call) | ~200 ns | yes |
| `Footprint.Add` allocation per new bar | ~5 µs once/min | irrelevant |

---

## 5. ChartStyle — complete API surface

`NinjaTrader.NinjaScript.ChartStyles.ChartStyle` is the abstract base. Custom file at `Documents\NinjaTrader 8\bin\Custom\ChartStyles\Deep6FootprintChartStyle.cs`.

### 5.1 Class shell

```csharp
namespace NinjaTrader.NinjaScript.ChartStyles
{
    public class Deep6FootprintChartStyle : ChartStyle
    {
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name           = "DEEP6 Footprint";
                ChartStyleType = (ChartStyleType)60606;
                BarWidth       = 30;
                IsThemeable    = true;
            }
        }

        public override int GetBarPaintWidth(int barWidth) => Math.Max(20, barWidth);

        protected override void OnRender(
            ChartControl chartControl, ChartScale chartScale, ChartBars chartBars)
        {
            // see §6 for the full footprint render
        }
    }
}
```

### 5.2 The `OnRender` signature — 3 args (this is the gotcha)

```csharp
// ChartStyle:
protected override void OnRender(ChartControl cc, ChartScale cs, ChartBars cb) { }

// Indicator/Strategy:
public override void OnRender(ChartControl cc, ChartScale cs) { }
```

If you copy an Indicator's `OnRender` into a ChartStyle the compiler will let you, but you'll never see it called. **Three-arg form is mandatory for ChartStyle.**

### 5.3 Coordinate conversion (essential)

```csharp
float x = chartControl.GetXByBarIndex(chartBars, idx);   // returns CENTER x
float y = chartScale.GetYByValue(price);

int   idx   = chartBars.GetBarIdxByX(chartControl, mouseX);
double price = chartScale.GetValueByY(mouseY);

for (int idx = chartBars.FromIndex; idx <= chartBars.ToIndex; idx++) { }
```

---

## 6. SharpDX rendering primer for footprint cells

### 6.1 Brushes — the rules

1. **Device-dependent** brushes must be created inside `OnRender` or `OnRenderTargetChanged`.
2. Convert WPF `Brush` → SharpDX with `wpfBrush.ToDxBrush(RenderTarget)`. **Cache** the result.
3. Always dispose:
    ```csharp
    using (var brush = new SolidColorBrush(RenderTarget, SharpDX.Color.DodgerBlue))
        RenderTarget.FillRectangle(rect, brush);
    ```
4. For pre-converted style brushes use `UpBrushDX` / `DownBrushDX` directly.

### 6.2 The DEEP6 footprint cell render

```csharp
protected override void OnRender(ChartControl cc, ChartScale cs, ChartBars cb)
{
    if (!(cb.Bars.BarsSeries.BarsType is Deep6FootprintBarsType bt)) return;

    double tickSize = cb.Bars.Instrument.MasterInstrument.TickSize;
    int    barW     = GetBarPaintWidth(BarWidth);
    int    half     = barW / 2;

    using var bidBrush     = new SolidColorBrush(RenderTarget, new Color4(0.85f, 0.20f, 0.25f, 0.85f));
    using var askBrush     = new SolidColorBrush(RenderTarget, new Color4(0.20f, 0.75f, 0.40f, 0.85f));
    using var pocBrush     = new SolidColorBrush(RenderTarget, SharpDX.Color.Yellow);
    using var imbalBrush   = new SolidColorBrush(RenderTarget, SharpDX.Color.Magenta);
    using var textBrushBid = new SolidColorBrush(RenderTarget, SharpDX.Color.White);
    using var textBrushAsk = new SolidColorBrush(RenderTarget, SharpDX.Color.White);
    using var fmt          = new TextFormat(Core.Globals.DirectWriteFactory, "Consolas", 9.5f)
                                  { TextAlignment = TextAlignment.Center };

    int from = cb.FromIndex, to = cb.ToIndex;
    for (int i = from; i <= to; i++)
    {
        if (i >= bt.Footprint.Count) continue;
        var fp   = bt.Footprint[i];
        float xC = cc.GetXByBarIndex(cb, i);
        double hi = cb.Bars.GetHigh(i);
        double lo = cb.Bars.GetLow (i);

        long maxVol = 1;
        for (double p = lo; p <= hi; p += tickSize)
            if (fp.Cells.TryGetValue(Math.Round(p, 6), out var arr))
                maxVol = Math.Max(maxVol, arr[0] + arr[1]);

        for (double p = lo; p <= hi; p += tickSize)
        {
            float yC = cs.GetYByValue(p);
            float yT = yC - 6, yB = yC + 6;

            long bid = 0, ask = 0;
            if (fp.Cells.TryGetValue(Math.Round(p, 6), out var arr))
            { bid = arr[0]; ask = arr[1]; }

            float bAlpha = Math.Min(1f, (float)bid / maxVol);
            float aAlpha = Math.Min(1f, (float)ask / maxVol);

            using (var bg = new SolidColorBrush(RenderTarget, new Color4(0.85f, 0.20f, 0.25f, bAlpha)))
                RenderTarget.FillRectangle(new RectangleF(xC - half, yT, half, 12), bg);
            using (var bg = new SolidColorBrush(RenderTarget, new Color4(0.20f, 0.75f, 0.40f, aAlpha)))
                RenderTarget.FillRectangle(new RectangleF(xC,        yT, half, 12), bg);

            if (bid > 0)
                RenderTarget.DrawText(bid.ToString(), fmt,
                    new RectangleF(xC - half, yT, half, 12), textBrushBid);
            if (ask > 0)
                RenderTarget.DrawText(ask.ToString(), fmt,
                    new RectangleF(xC, yT, half, 12), textBrushAsk);

            // Imbalance highlight (3:1)
            if (bid > 0 && ask > 0)
            {
                if (ask >= 3 * bid)
                    RenderTarget.DrawRectangle(new RectangleF(xC, yT, half, 12), imbalBrush, 1.5f);
                else if (bid >= 3 * ask)
                    RenderTarget.DrawRectangle(new RectangleF(xC - half, yT, half, 12), imbalBrush, 1.5f);
            }
        }

        float yPoc = cs.GetYByValue(fp.Poc);
        RenderTarget.DrawLine(
            new Vector2(xC - half, yPoc), new Vector2(xC + half, yPoc),
            pocBrush, 2f);
    }
}
```

---

## 7. Persistence, serialization, and workspace reload

### 7.1 What NT8 auto-serializes

Every **public** property on a NinjaScript object is XML-serialized. That includes BarsType properties (Value, Value2, custom int/double/string/enum) and ChartStyle properties.

### 7.2 What breaks XML serialization

`Brush` and `TimeSpan` — pattern:

```csharp
[XmlIgnore]
public Brush ImbalanceBrush { get; set; } = Brushes.Magenta;

[Browsable(false)]
public string ImbalanceBrushSerialize
{
    get => Serialize.BrushToString(ImbalanceBrush);
    set => ImbalanceBrush = Serialize.StringToBrush(value);
}
```

### 7.3 What you must NOT serialize

`List<Deep6FootprintBar>`, `Dictionary<...>`, any per-bar runtime state. Tag with `[XmlIgnore]`.

### 7.4 Static state pitfalls

A `static` field on a BarsType is **shared across every chart and strategy instance**. Always use instance fields.

---

## 8. Indicator ↔ BarsType integration

```csharp
private Deep6FootprintBarsType _ft;

protected override void OnBarUpdate()
{
    _ft ??= Bars.BarsSeries.BarsType as Deep6FootprintBarsType;
    if (_ft == null || CurrentBar < 0 || CurrentBar >= _ft.Footprint.Count) return;

    var fp = _ft.Footprint[CurrentBar];
    if (fp.AbsorptionScore > 700)
        Draw.ArrowUp(this, "abs_" + CurrentBar, true, 0,
                     fp.Cells.Keys.Min() - TickSize, Brushes.Cyan);
}
```

Always null-check the cast.

---

## 9. Memory & chart-bars compaction

- NT8 keeps in-memory bars governed by `DaysToLoad` and `MaximumBarsLookBack`.
- Old bars beyond `DaysToLoad` are GC'd from memory but recached from `Documents\NinjaTrader 8\db\cache`.
- When you change a custom BarsType's logic, **delete the cache** (`Documents\NinjaTrader 8\db\cache\<instrument>\*.cache`).
- Per-bar custom payload uses ~50 bytes × cells per bar. NQ at 50-tick range × 5 cells × 16 bytes ≈ 4 KB/bar. A 5-day chart at 1-min = ~20K bars × 4 KB = 80 MB. Acceptable.

---

## 10. Specific implementation: BookMap-style heatmap

NT8 doesn't expose DOM events to a BarsType — there is **no `OnDataPointMarketDepth` override**. The DOM stream is delivered only to:
- `Indicator.OnMarketDepth(MarketDepthEventArgs e)`
- `Strategy.OnMarketDepth(...)`
- `AddOn.IInstrumentDataProvider.OnMarketDepth`

Architecture for DEEP6 heatmap:

```
DOM events ──▶ Deep6HeatmapAddOn (singleton)
                  │ stores DomSnapshot per timeslice
                  ▼
              Deep6HeatmapStore : ConcurrentDictionary<DateTime, DomSnapshot>
                  ▲ (read by indicator & by BarsType for per-bar attribution)
                  │
              Deep6FootprintBarsType.Footprint[i].DomAtClose = store.Get(slot)
                  │
              Deep6HeatmapIndicator.OnRender ─▶ paints the heatmap from store
```

DOM event lock pattern (mandatory):
```csharp
protected override void OnMarketDepth(MarketDepthEventArgs e)
{
    lock (e.Instrument.SyncMarketDepth)
    {
        var asks = e.Instrument.MarketDepth.Asks;
        var bids = e.Instrument.MarketDepth.Bids;
    }
}
```

NT8 caps depth at 10 by default; extending requires the broker to send 40+ levels (Rithmic does, IB doesn't). For DEEP6 + Rithmic this works.

---

## 11. Pitfalls catalog with fixes

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | Footprint dict empty after chart reload | NT8 returned cached OHLC, custom payload lost | `public override bool SkipCaching => true;` |
| 2 | Bars duplicated at futures rollover | `IsNewSession` called twice per OnDataPoint | Call only once at top |
| 3 | Workspace save throws XML error | Public `Brush` property without serializer pair | `[XmlIgnore]` + `Serialize.BrushToString` partner |
| 4 | Cells appear at half-tick prices | Forgot `RoundToTickSize` on price keys | Always round before dict lookup |
| 5 | OnRender appears never called for ChartStyle | Wrong overload (2-arg copied from Indicator) | Use 3-arg form `OnRender(cc, cs, cb)` |
| 6 | Memory grows unbounded | `.ToDxBrush()` per-bar in OnRender | Cache brushes in OnRenderTargetChanged |
| 7 | Bid/Ask are zero historically | TickReplay disabled or BuiltFrom != Tick | Force `BuiltFrom = Tick` and document TickReplay |
| 8 | Two custom BarsTypes collide | Same `BarsPeriodType` int | Pick > 10000; document chosen id |
| 9 | Static `_someState` corrupts multi-chart | Static field shared across instances | Use instance fields |
| 10 | "Bars out of order" in OnDataPoint | UpdateBar called with time < last bar's time | Use `slot.Add(BarSpan)` consistently |
| 11 | Style works in dev, missing in style picker | `ChartStyleType` collides with built-in (0–10 reserved) | Use > 1023, ideally > 10000 |
| 12 | Footprint shows on first chart, gone on second | Cached cache file from old logic | Delete `Documents\NinjaTrader 8\db\cache\<instrument>\*.cache` |
| 13 | DOM events in BarsType compile error | No `OnDataPointMarketDepth` exists | Use AddOn or Indicator pattern; see §10 |
| 14 | OnRender stops rendering after a chart resize | Held device-dependent brush across RenderTarget change | Re-create in `OnRenderTargetChanged` |
| 15 | Numbers blurred/jittery at certain zooms | Default antialias on text + sub-pixel positions | Round x/y to int before DrawText |

---

## 12. Decision matrix — extend vs. subclass vs. replace

| Need | NT8 builtin sufficient? | Recommendation |
|---|---|---|
| Plain bid/ask volume per cell | VolumetricBarsType + Volumetric ChartStyle | Use stock |
| Custom imbalance scoring per cell | No | Custom BarsType + custom ChartStyle |
| Above-ask / below-bid prints split out | No | Custom BarsType (TickType bucket) |
| Block-trade-only footprint | Partial (size filter R17+) but irreversible | Custom BarsType with size_filter param |
| DOM heatmap behind candles | No | AddOn (DOM store) + Indicator (render) |
| Multi-bar composite VPOC | No | Custom BarsType helper + Indicator render |
| Just colour delta candles bid/ask differently | No new data needed | Custom ChartStyle only |
| Re-skin existing footprint | No new data needed | Custom ChartStyle that reads VolumetricBar |
| Replace footprint entirely (DEEP6) | No | **Custom BarsType + Custom ChartStyle pair** |

For DEEP6 the answer is the bottom row.

---

## 13. Reference repos in the wild

- `jjvegaes/Ninjatrader8-Indicators` — `unirenko.cs`. Complete working custom BarsType. **Best small reference.**
- NT8 sample `BarsTypes` folder: `@TickBarsType.cs`, `@MinuteBarsType.cs`, `@RangeBarsType.cs`, `@RenkoBarsType.cs`, `@HeikinAshiBarsType.cs`, `@LineBreakBarsType.cs`, `@PointAndFigureBarsType.cs`, `@KagiBarsType.cs`, `@VolumeBarsType.cs`, `@VolumetricBarsType.cs`. All open-source within the install.
- NT8 sample indicator `SampleCustomRender` — best SharpDX OnRender reference shipped with NT8.
- NT8 sample indicator `Priceline` — clean per-frame OnRender + OnRenderTargetChanged pattern.

---

## 14. Authoritative sources

- [BarsType reference (NT8 docs)](https://ninjatrader.com/support/helpguides/nt8/bars_type.htm)
- [OnDataPoint() reference](https://ninjatrader.com/support/helpGuides/nt8/ondatapoint.htm)
- [DefaultChartStyle reference](https://ninjatrader.com/support/helpguides/nt8/defaultchartstyle.htm)
- [ChartStyleType reference](https://ninjatrader.com/support/helpguides/nt8/chartstyletype.htm)
- [ChartStyle.OnRender() reference](https://ninjatrader.com/support/helpGuides/nt8/chartstyle_onrender.htm)
- [Using SharpDX for Custom Chart Rendering](https://ninjatrader.com/support/helpguides/nt8/using_sharpdx_for_custom_chart_rendering.htm)
- [VolumetricBarsType API methods](https://ninjatrader.com/support/helpguides/nt8/order_flow_volumetric_bars2.htm)
- [Order Flow Volumetric Bars operations](https://ninjatrader.com/support/helpguides/nt8/order_flow_volumetric_bars.htm)
- [AddVolumetric() overloads](https://ninjatrader.com/support/helpguides/nt8/addvolumetric.htm)
- [SessionIterator (BarsType)](https://ninjatrader.com/support/helpguides/nt8/barstype_sessioniterator.htm)
- [NinjaScript Lifecycle](https://ninjatrader.com/support/helpguides/nt8/understanding_the_lifecycle_of.htm)
- [State enum reference](https://ninjatrader.com/support/helpguides/nt8/state.htm)
- [Custom BarsType — additional data forum thread](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1090892-custom-bars-type-with-additional-data)

**Bottom-line for the DEEP6 graphics agent:** the deepest NT8 visual customization is two paired classes — a `BarsType` subclass that does its own tick-by-tick aggregation into a `[XmlIgnore] List<CustomBar>`, and a `ChartStyle` subclass with a 3-arg `OnRender(cc, cs, cb)` that walks `cb.FromIndex..ToIndex`, casts `cb.Bars.BarsSeries.BarsType` back to your custom type, and draws cells with cached SharpDX brushes. Set `SkipCaching = true`, register a `BarsPeriodType` and `ChartStyleType` int > 10000, force `BuiltFrom = BarsPeriodType.Tick`, document the TickReplay requirement, and never call `.ToDxBrush()` inside a per-bar loop.
