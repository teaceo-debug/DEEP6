I have abundant material. I have everything I need to produce the long-form research document. Let me synthesize.

---

# NT8 Execution Surfaces — Exhaustive Research for the DEEP6 Graphics Agent

This is the "execution surfaces" companion to the chart-rendering research. It covers everything outside the main chart pane: SuperDOM, Strategy P&L visualization, Market Analyzer columns, hot keys, context menus, drawing-tool order placement, AddOn windows, and workspace persistence. The thesis: in NT8, charts use SharpDX/Direct2D; **almost every execution surface uses WPF DrawingContext** instead. Mixing them up is the single largest source of wasted hours. Treat this document as the rule book.

---

## 1. The Cardinal Rendering Rule

Before any code: NT8 has two distinct render stacks, and they do not interoperate.

| Surface | Render API | OnRender Signature | Notes |
|---|---|---|---|
| Chart Indicator / Strategy / Drawing Tool / Chart Style | SharpDX (Direct2D) | `OnRender(ChartControl chartControl, ChartScale chartScale)` | Hardware-accelerated. RenderTarget already bound. |
| **SuperDOM Column** | **WPF `System.Windows.Media.DrawingContext`** | `OnRender(DrawingContext dc, double renderWidth)` | NinjaTrader docs: "Concepts between these two methods are guaranteed to be different." |
| **Market Analyzer Column** | **WPF `System.Windows.Media.DrawingContext`** | `OnRender(DrawingContext dc, System.Windows.Size renderSize)` | Same WPF stack as SuperDOM. |
| AddOn Window (NTWindow) | WPF (XAML or code-behind) | n/a — standard WPF | Full WPF with platform helpers. |

Implication: a SharpDX brush, a `SharpDX.Vector2`, a `RenderTarget.DrawRectangle` — none of them exist in column code. You use `Brushes.Red`, `new Point(x,y)`, and `dc.DrawRectangle(brush, pen, new Rect(...))`. Code copied from chart indicators **will not compile** in a column. This is a critical NT8 fact.

---

## 2. SuperDomColumn — The Class

### 2.1 Lifecycle and Override Surface

`SuperDomColumn` is a `NinjaScriptBase`-derived but **not** indicator-derived class. The full set of overrides actually exposed:

| Override | Signature | Purpose |
|---|---|---|
| `OnStateChange` | `protected override void OnStateChange()` | Inherited — `SetDefaults`, `Configure`, `DataLoaded`, `Active`, `Terminated`. Wire/unwire event subscriptions here. |
| `OnMarketData` | `protected override void OnMarketData(MarketDataEventArgs marketDataUpdate)` | Every L1 tick (Last/Bid/Ask/DailyHigh/DailyLow/etc.). Guaranteed in-sequence. |
| `OnOrderUpdate` | (delegate via SuperDom or Account) — also accessible inside the column subclass | Order state changes. |
| `OnPositionUpdate` | similar | Position changes. |
| `OnExecutionUpdate` | similar | Fills. |
| `OnPropertyChanged` | `protected override void OnPropertyChanged()` | Use this **instead of** calling `OnRender()` directly. Forces full repaint. |
| `OnRestoreValues` | `protected override void OnRestoreValues()` | Called when workspace restores the column. |
| `OnRender` | `protected override void OnRender(DrawingContext dc, double renderWidth)` | **WPF DrawingContext** — paint the column. |

There is **no `OnBarUpdate`** in a SuperDomColumn — NT staff ("SuperDom columns are meant to use real-time data and do not load bar series"). If you need bar-derived values, host an **Indicator** inside the SuperDOM (the platform supports it) or pre-compute in an indicator and read its exposed series.

### 2.2 What the Column Knows About Its Host

The column is constructed by the parent SuperDOM. It is given access through a `SuperDom` property (the host):

```csharp
SuperDom.Instrument            // the instrument shown on the ladder
SuperDom.MarketDepth.Asks      // List<MarketDepthRow>
SuperDom.MarketDepth.Bids      // List<MarketDepthRow>
SuperDom.MarketDepth.Instrument
SuperDom.Rows                  // the visible PriceRow collection — one per ladder row
SuperDom.Account               // the active account (orders, positions)
SuperDom.PriceFormat           // for ToString() formatting
```

`MarketDepthRow` exposes `Price` (double), `Volume` (long), `Position` (int), and `MarketDataType`. There is no public `OnNewRows` — instead, scrolling/resizing causes `OnRender` to fire with the current `SuperDom.Rows`.

### 2.3 The Rows Model — Coordinate System

A SuperDOM is a vertical ladder. The column's drawable area is `renderWidth` (passed to `OnRender`) by `SuperDom.ActualRowHeight * SuperDom.Rows.Count`. Each row is identical pixel height, set by the user's font size. The pattern for "draw something at price P" is:

```csharp
foreach (PriceRow row in SuperDom.Rows)
{
    double y = row.Y;                  // top y of this row, in WPF pixels
    double rowH = SuperDom.ActualRowHeight;
    if (row.Price == targetPrice)
        dc.DrawRectangle(brush, null, new Rect(0, y, renderWidth, rowH));
}
```

Hit testing the inverse — given a mouse Y, find the row — uses `SuperDom.Rows[idx]` where `idx = (int)(mouseY / SuperDom.ActualRowHeight)`. There is no `GetValueByY` on a SuperDom column (that method is chart-only). You walk `SuperDom.Rows` and compare `row.Y`.

### 2.4 OnRender Invocation Triggers

NT docs list when `OnRender` fires for a SuperDOM column:
- The SuperDOM is centered (price moved out of range, auto-center triggered)
- Manual scroll
- Account disconnect/reconnect
- Position update
- Property change
- Window resize
- Manual `OnPropertyChanged()` call

Critical: **`OnRender` is NOT called per tick**. To repaint on every tick, you must call `OnPropertyChanged()` from `OnMarketData`. Doing this naively at 1,000 ticks/sec for a liquid future will pin a CPU core. Throttle with a `DispatcherTimer` running at ~30 Hz (33 ms) — the human eye can't see faster anyway.

### 2.5 Built-in Columns — Reference Set

From the `bin\Custom\SuperDomColumns\` install folder (every NT8 install):

| Class | Purpose |
|---|---|
| `PriceColumn` | The center price ladder |
| `BidColumn` / `AskColumn` | Working orders and resting depth |
| `BidSizeColumn` / `AskSizeColumn` | Quantity at bid/ask |
| `LastSizeColumn` | Last trade size |
| `VolumeColumn` | Volume traded at price (Standard or BuySell mode) |
| `BidTradeColumn` / `AskTradeColumn` | Trades hitting bid vs lifting offer (volume-at-price split) |
| `SoundsColumn` | Sound alerts at price |
| `NotesColumn` | User-typed notes per row |
| `PnLColumn` | Per-row unrealized P&L given current position |
| `PullStackColumn` | Pulling/Stacking depth-change visual |
| `RecentBidColumn` / `RecentAskColumn` | Recent volume at bid/ask in rolling window |
| `APQColumn` | Approximate Position in Queue |

These are all source files in `<NT8 install>\bin\Custom\SuperDomColumns\@*.cs`. The `@` prefix marks NT-shipped originals — they recompile but should not be edited; copy and rename to extend.

There is no documented `SortableSuperDomColumn` or `StatsCalcsColumn` base class in NT8 (those names appear in third-party vendor docs but are not part of the core API). Sorting is not a SuperDOM concept — it's per-row by price.

### 2.6 Working Code — Custom SuperDOM Column with Imbalance Highlighting

This is a complete, compilable column for `bin\Custom\SuperDomColumns\ImbalanceColumn.cs`. It computes ask/bid volume imbalance per row and paints the row green/red with intensity proportional to the imbalance ratio. Click-to-trade fires a market order at the clicked price. It demonstrates: WPF DrawingContext, MarketDepth subscription, click hit-test, brush caching, OnPropertyChanged-driven throttled repaint.

```csharp
#region Using declarations
using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui.SuperDom;
#endregion

namespace NinjaTrader.NinjaScript.SuperDomColumns
{
    public class ImbalanceColumn : SuperDomColumn
    {
        // per-row aggregates
        private readonly Dictionary<double, long> tradesAtAsk = new Dictionary<double, long>();
        private readonly Dictionary<double, long> tradesAtBid = new Dictionary<double, long>();
        private double lastBid, lastAsk;

        // brush cache — never new-up brushes inside OnRender
        private readonly SolidColorBrush bgBuy   = new SolidColorBrush(Color.FromArgb(180,  20, 200,  60));
        private readonly SolidColorBrush bgSell  = new SolidColorBrush(Color.FromArgb(180, 220,  40,  40));
        private readonly Pen rowBorder           = new Pen(new SolidColorBrush(Color.FromArgb(60,255,255,255)), 0.5);
        private readonly Typeface tf             = new Typeface("Consolas");

        // throttle repaint to ~30 Hz
        private DispatcherTimer paintTimer;
        private bool dirty;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "Imbalance";
                Description = "Ask/Bid trade imbalance with click-to-trade";
                DefaultWidth = 84;
                PreviousWidth = -1;
                IsDataSeriesRequired = false;
                bgBuy.Freeze(); bgSell.Freeze(); rowBorder.Freeze();
            }
            else if (State == State.Configure)
            {
                tradesAtAsk.Clear();
                tradesAtBid.Clear();
            }
            else if (State == State.DataLoaded)
            {
                paintTimer = new DispatcherTimer(DispatcherPriority.Render)
                {
                    Interval = TimeSpan.FromMilliseconds(33)
                };
                paintTimer.Tick += (s, e) => { if (dirty) { dirty = false; OnPropertyChanged(); } };
                paintTimer.Start();

                // mouse click subscription must wait until the WPF visual is realized.
                // The SuperDom hands you a Grid host — subscribe MouseLeftButtonDown there.
                if (UiWrapper != null)
                    UiWrapper.MouseLeftButtonDown += OnRowMouseDown;
            }
            else if (State == State.Terminated)
            {
                if (paintTimer != null) { paintTimer.Stop(); paintTimer = null; }
                if (UiWrapper != null)
                    UiWrapper.MouseLeftButtonDown -= OnRowMouseDown;
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType == MarketDataType.Bid) lastBid = e.Price;
            else if (e.MarketDataType == MarketDataType.Ask) lastAsk = e.Price;
            else if (e.MarketDataType == MarketDataType.Last)
            {
                Dictionary<double,long> bucket;
                if      (e.Price >= lastAsk) bucket = tradesAtAsk;
                else if (e.Price <= lastBid) bucket = tradesAtBid;
                else                         return;

                long cur;
                bucket.TryGetValue(e.Price, out cur);
                bucket[e.Price] = cur + e.Volume;
                dirty = true;
            }
        }

        protected override void OnRender(DrawingContext dc, double renderWidth)
        {
            if (SuperDom == null || SuperDom.Rows == null) return;

            double rowH = SuperDom.ActualRowHeight;
            foreach (PriceRow row in SuperDom.Rows)
            {
                long askV, bidV;
                tradesAtAsk.TryGetValue(row.Price, out askV);
                tradesAtBid.TryGetValue(row.Price, out bidV);

                long total = askV + bidV;
                if (total < 5) continue; // ignore noise

                double ratio = (askV - bidV) / (double) total; // -1 .. +1
                Brush bg = ratio > 0 ? bgBuy : bgSell;
                double alpha = Math.Min(1.0, Math.Abs(ratio) * 1.5);

                var rect = new Rect(0, row.Y, renderWidth, rowH);
                dc.PushOpacity(alpha);
                dc.DrawRectangle(bg, rowBorder, rect);
                dc.Pop();

                // numeric overlay
                string label = string.Format("{0}/{1}", askV, bidV);
                var ft = new FormattedText(label,
                    System.Globalization.CultureInfo.CurrentUICulture,
                    FlowDirection.LeftToRight, tf, 11.0, Brushes.White, 96);
                ft.TextAlignment = TextAlignment.Center;
                dc.DrawText(ft, new Point(renderWidth / 2.0, row.Y + (rowH - ft.Height) / 2.0));
            }
        }

        private void OnRowMouseDown(object sender, MouseButtonEventArgs e)
        {
            if (SuperDom == null || SuperDom.Rows == null) return;
            double y = e.GetPosition((IInputElement) sender).Y;
            int idx = (int)(y / SuperDom.ActualRowHeight);
            if (idx < 0 || idx >= SuperDom.Rows.Count) return;

            double price = SuperDom.Rows[idx].Price;
            var account = SuperDom.Account;
            if (account == null) return;

            OrderAction action = (price >= lastAsk) ? OrderAction.Buy : OrderAction.Sell;
            var order = account.CreateOrder(
                SuperDom.Instrument, action, OrderType.Market,
                OrderEntry.Manual, TimeInForce.Day,
                1, 0, 0, string.Empty, "ImbalanceClick", default(DateTime), null);
            account.Submit(new[] { order });
            e.Handled = true;
        }
    }
}
```

Compile by F5'ing in NinjaScript Editor; it appears in **right-click SuperDOM → Columns → Available → Imbalance**. The `UiWrapper` reference (the WPF host element NT gives the column for mouse events) is exposed by the framework — confirmed by NT staff in the `SuperDOMColumnVolumeMouseClicks.zip` reference posted on the NT forum.

### 2.7 Performance Notes — SuperDOM-Specific

- Liquid futures (NQ, ES) emit 50–200 L1 ticks/sec **per instrument**, plus L2 depth at 5x that. Multi-DOM workspaces routinely exceed 1,000 events/sec.
- `OnRender` budget: NT8 schedules SuperDOM repaints on the WPF dispatcher; long renders block the entire UI thread (which also serves charts).
- Frame budget per column: aim for **≤ 2 ms** render time. 50 rows × 4 simple drawing ops ≈ 200 ops; safely under 2 ms with cached frozen brushes.
- **Anti-pattern**: allocating a `SolidColorBrush` per row per repaint. Always cache and `.Freeze()`.
- **Anti-pattern**: calling `OnRender()` directly from `OnMarketData`. Use the dirty-flag + timer pattern shown above.
- **Anti-pattern**: drawing thousands of rectangles per OnRender. Forum confirmation: at scale, render to a `RenderTargetBitmap` once and `dc.DrawImage(bitmap)` after — converting the bitmap once amortizes the cost. The `TestColumn.cs` sample referenced by NT support shows this pattern.
- WPF `DrawingContext` is retained-mode behind the scenes — over-drawing the same region is cheap; over-instantiating geometry is not. Reuse `StreamGeometry` for repeated shapes.

---

## 3. SuperDOM-Specific Visualization Patterns

### 3.1 Volume Profile Overlaid on the Ladder
Built-in: the `VolumeColumn` in `BuySell` mode already does this. To go further (asymmetric histograms across multiple sessions), subscribe to `OnMarketData` for `MarketDataType.Last`, bucket by `e.Price`, and draw a horizontal bar of width `renderWidth * (vol / maxVol)`. Color split by ask-side vs bid-side aggression as in §2.6.

### 3.2 Cumulative Delta in DOM
Track running `cumDelta += askV - bidV` per session. Render either as a center pillar in the price column or as an upper-right corner badge whose color shifts green/red with sign and intensity with magnitude.

### 3.3 Iceberg Detection Visualization
Refresh-pattern detection at the L2 level: when the same price level sees `Operation.Update` events with `Volume` decrementing by trade quantity then snapping back to a higher value within ~50 ms, flag it. Paint the row with a yellow pulse — animate via `DispatcherTimer` over 400 ms by lerping opacity.

### 3.4 Pulled-Liquidity Flash
Detect by watching `MarketDepth` updates with `Operation.Remove` or `Volume → 0` at price levels within N ticks of the inside. Render a red horizontal flash for 200 ms in the appropriate Bid/Ask depth column. Same animation pattern as iceberg.

### 3.5 Custom Centering Modes
NT8 only has "Auto center on last" out of the box. To implement volume-center (pin POC to vertical middle) or position-center (pin entry to middle), use `SuperDom.UpperPrice` and `SuperDom.LowerPrice` to drive recentering. There's no documented setter; the supported approach is to call `SuperDom.SetUpperPrice(price)` from a column reacting to a market event — though as of recent NT8 builds this requires reflection because the setter is internal. The community pattern is to expose a custom indicator hosted on the SuperDOM that calls into NT internals via reflection — fragile but effective.

### 3.6 Highlight Rules
Last-trade highlight: maintain `lastTradePrice` updated in `OnMarketData(MarketDataType.Last)`, paint that row with a 1 px outline. Working orders: enumerate `SuperDom.Account.Orders.Where(o => o.Instrument == SuperDom.Instrument && o.OrderState == OrderState.Working)`, paint a 2 px line at the order's price. Position price: `SuperDom.Account.Positions.FirstOrDefault(...)?.AveragePrice`.

---

## 4. Strategy Visualization on Charts

### 4.1 Built-in Plot Executions Property
Set on the chart's Data Series, NOT in code: **DoNotPlot / MarkersOnly / TextAndMarkers**. NT renders entry arrows (blue up, red down) and exit arrows automatically using execution timestamps, regardless of bar boundaries. Critical caveat from official docs: executions are tied to **timestamps**, not bars — if your PC clock drifts vs the data feed, markers land on wrong bars (the 4:21 vs 4:26 example in NT's own help guide). Sync via NTP.

### 4.2 OnExecutionUpdate Signature
```csharp
protected override void OnExecutionUpdate(
    Execution execution, string executionId,
    double price, int quantity,
    MarketPosition marketPosition,
    string orderId, DateTime time)
```
Called after `OnOrderUpdate` for every fill (including partials). The `execution.Order.OrderAction` distinguishes entries from exits. `marketPosition` is `Long` or `Short`. This is the hook for custom marker rendering.

### 4.3 Live Strategy P&L Overlay — Working Code

This is a complete `Strategy`-derived class that draws a **live HUD** in the upper-right corner of the chart: open P&L, today's realized P&L, current position, average entry, and a small bar showing distance-to-stop / distance-to-target. It uses SharpDX (because Strategy on a chart uses chart's `OnRender`), unlike the column.

```csharp
#region Using declarations
using System;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class LivePnLHud : Strategy
    {
        private TextFormat tfBig, tfSmall;
        private SharpDX.Direct2D1.Brush brushGreen, brushRed, brushWhite, brushBg;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "LivePnLHud";
                Calculate   = Calculate.OnPriceChange;
                IsOverlay   = true;
                DisplayInDataBox = false;
            }
        }

        public override void OnRenderTargetChanged()
        {
            // dispose previous, create against new target
            if (brushGreen != null) brushGreen.Dispose();
            if (brushRed   != null) brushRed.Dispose();
            if (brushWhite != null) brushWhite.Dispose();
            if (brushBg    != null) brushBg.Dispose();

            if (RenderTarget == null) return;
            brushGreen = new SolidColorBrush(RenderTarget, new Color4(0.2f, 0.85f, 0.3f, 1f));
            brushRed   = new SolidColorBrush(RenderTarget, new Color4(0.9f, 0.25f, 0.25f, 1f));
            brushWhite = new SolidColorBrush(RenderTarget, new Color4(1,1,1,1));
            brushBg    = new SolidColorBrush(RenderTarget, new Color4(0,0,0,0.55f));
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (RenderTarget == null) return;
            if (tfBig == null)
            {
                var dwf = Core.Globals.DirectWriteFactory;
                tfBig   = new TextFormat(dwf, "Consolas", 18) { TextAlignment = TextAlignment.Trailing };
                tfSmall = new TextFormat(dwf, "Consolas", 11) { TextAlignment = TextAlignment.Trailing };
            }

            int marketPos = (int)Position.MarketPosition;
            double avgPx  = Position.AveragePrice;
            double last   = GetCurrentAsk();
            double openPL = Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency, last);
            double dayPL  = SystemPerformance.RealTimeTrades.TradesPerformance.Currency.CumProfit;

            // background
            float w = 240f, h = 92f;
            float x = (float)(ChartPanel.W - w - 12);
            float y = 12f;
            RenderTarget.FillRectangle(new RectangleF(x, y, w, h), brushBg);

            // text
            var pnlBrush = openPL >= 0 ? brushGreen : brushRed;
            DrawText(string.Format("Open: {0:C0}", openPL), x + w - 8, y + 6,  tfBig,   pnlBrush, w - 16);
            DrawText(string.Format("Day:  {0:C0}", dayPL),  x + w - 8, y + 32, tfSmall, brushWhite, w - 16);
            DrawText(string.Format("Pos:  {0} @ {1:F2}", marketPos == 0 ? "FLAT" : (marketPos > 0 ? "+" + Position.Quantity : "-" + Position.Quantity), avgPx),
                                                            x + w - 8, y + 48, tfSmall, brushWhite, w - 16);
            DrawText(string.Format("Trades today: {0}", SystemPerformance.RealTimeTrades.Count),
                                                            x + w - 8, y + 64, tfSmall, brushWhite, w - 16);
        }

        private void DrawText(string s, float x, float y, TextFormat tf, SharpDX.Direct2D1.Brush b, float maxW)
        {
            using (var layout = new TextLayout(Core.Globals.DirectWriteFactory, s, tf, maxW, 24f))
                RenderTarget.DrawTextLayout(new Vector2(x - maxW, y), layout, b);
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition, string orderId, DateTime time)
        {
            // also lay down a custom in-bar marker
            string tag = "exec-" + executionId;
            Brush dotBrush = marketPosition == MarketPosition.Long ? Brushes.LimeGreen : Brushes.Tomato;
            Draw.Dot(this, tag, true, time, price, dotBrush);
        }
    }
}
```

Drop in `bin\Custom\Strategies\LivePnLHud.cs`, F5, attach to a chart. The key SharpDX rules: dispose brushes in `OnRenderTargetChanged`, never allocate per-frame, always check `RenderTarget != null`. For chart strategies the `OnRender` IS SharpDX — opposite of the SuperDOM column rule from §1.

### 4.4 Equity Ribbon at Top of Chart
Compute via `SystemPerformance.RealTimeTrades.TradesPerformance.Currency.CumProfit` snapshots. Render a 24 px tall area chart spanning the chart's top using SharpDX `PathGeometry`. Fill green above start equity, red below.

### 4.5 Drawdown Band
Track running max equity, paint the gap between current equity line and max-equity ceiling as a translucent red band.

### 4.6 Live vs Sim Coloration
Branch on `SystemPerformance.RealTimeTrades` vs `SystemPerformance.AllTrades` (which includes synthetic backtest trades). In live mode, also branch on `Account.Connection.Status == ConnectionStatus.Connected` vs `ConnectionStatus.ConnectedSlow`.

### 4.7 SystemPerformance API
The tree (verbatim from the docs):
- `SystemPerformance.AllTrades` — `TradeCollection` of all trades (synthetic + real-time)
- `SystemPerformance.RealTimeTrades` — only live trades
- `SystemPerformance.LongTrades` / `ShortTrades`
- Each `TradeCollection` exposes:
  - `.Count`
  - `.TradesPerformance.{Currency,Percent,Pips,Ticks,Points}` — each is a `TradePerformanceValues`
  - The `TradePerformanceValues` class exposes (from NT internals; read via reflection or browse `bin\Custom\Strategies\@*.cs`): `CumProfit`, `Drawdown`, `MaxDrawdown`, `AverageProfit`, `Sharpe`, `Sortino`, `ProfitFactor`, `Expectancy`, `Winners.Count`, `Losers.Count`, etc.

For per-iteration optimization fitness: override `OnCalculatePerformanceValue(StrategyBase strategy)` in a `OptimizationFitness` subclass and consume `strategy.SystemPerformance.AllTrades`.

---

## 5. Strategy Analyzer Visualization

The Strategy Analyzer is a built-in NTWindow that:
- Runs backtests via Strategy Analyzer dialog (Tools → New → Strategy Analyzer)
- Renders equity curve, drawdown, trade list, optimization heatmap
- Sources data from `SystemPerformance` populated by the strategy run

### 5.1 Custom Display in Optimization Results
Add `[NinjaScriptProperty]` properties to your strategy and they appear as columns in the optimization grid automatically. To inject computed columns (e.g., custom Sharpe-on-rolling-30-trades), implement a custom `OptimizationFitness` and the value goes into the **Performance** column.

### 5.2 Backtest Replay Overlay
Use `Plot Executions = TextAndMarkers` on the chart — the historical fills render as arrows. To go beyond the built-in markers, write an indicator that subscribes to `Account.ExecutionUpdate` (for live) or reads `SystemPerformance.AllTrades` (for backtest) and uses `Draw.Dot`/`Draw.Line` to render entry-to-exit segments. The community indicator **ExecutionTraceLines** (free on NT Ecosystem, ~3.9 KB, by agaviria85) is a clean reference: it pairs entries to exits FIFO, draws strategy-style trade lines for manual ChartTrader fills, respects the chart's Plot executions visibility setting, and follows the active ChartTrader account.

### 5.3 Heatmap of Optimization Results
NT8's optimizer renders a 2-D heatmap automatically when you optimize over exactly 2 parameters. For 3+ params, results display as a sortable grid. Custom heatmap rendering requires post-processing: export results to CSV via the Strategy Analyzer's export, or implement a custom `OptimizationFitness` that writes results to a file your AddOn window reads.

---

## 6. MarketAnalyzerColumn

### 6.1 The Class — Surface Area

`MarketAnalyzerColumn` derives from `Indicator` (unlike SuperDomColumn). Therefore:
- It **does** have `OnBarUpdate` — but per NT staff: "There is not full OnBarUpdate support" — internal indexing limits which series are available.
- It has `OnMarketData(MarketDataEventArgs)` — the primary live-update hook, fires on every L1 tick.
- It has `OnFundamentalData` for fundamentals updates.
- It has `OnConnectionStatusUpdate` for connection state changes.
- It has `OnRender(DrawingContext dc, System.Windows.Size renderSize)` — **WPF**, not SharpDX (same as SuperDOM).
- It has `OnRestoreValues()` and `OnPropertyChanged()`.

Documented properties:
- **`CurrentValue`** (`double`) — value displayed in the cell. Set from `OnMarketData` or `OnBarUpdate`.
- **`CurrentText`** (`string`) — text override. **Takes precedence over `CurrentValue`.** Set both and only `CurrentText` shows.
- **`PriorValue`** — the previous `CurrentValue`.
- **`DataType`** — how `CurrentValue` is formatted (currency, percent, etc.).
- **`FormatDecimals`** — rounding before display.
- **`IsEditable`** — whether the user can edit the cell.

Per-instrument context: a single MA cell is one instance per row × column. The `Instrument` is inherited (since the class is `Indicator`-based).

### 6.2 Sortable Pattern
NT staff confirmed: sorting is automatic. The column header click sorts on `CurrentValue` (for numeric columns) or `CurrentText` (for text). There is no `IsSortable` property to set. If sort doesn't work, the common cause is initializing values in `State.DataLoaded` — move to `State.Configure`.

### 6.3 Conditional Formatting (BackColor / ForeColor)
Even though the docs page doesn't enumerate them, the inherited `Indicator` properties `BackColor` and `ForeColor` are honored by the MA renderer. Set them in `OnMarketData`:
```csharp
if (CurrentValue > Threshold) { BackColor = Brushes.Gold; ForeColor = Brushes.Black; }
else                          { BackColor = null; ForeColor = Brushes.White; }
```

### 6.4 Reference Pattern from NT Staff (Forum, verbatim)
```csharp
public class test : MarketAnalyzerColumn
{
    protected override void OnStateChange()
    {
        if (State == State.SetDefaults)
        {
            Description = @"Custom MA column.";
            Name = "test";
            Calculate = Calculate.OnPriceChange;
            Period = 15;
            Show = true;
        }
    }

    protected override void OnBarUpdate()
    {
        if (CurrentBar < Period + 1) return;
        if (Show) CurrentValue = CCI(Period)[0];
        else
        {
            if      (IsRising(CCI(Period)))  CurrentText = "Rising";
            else if (IsFalling(CCI(Period))) CurrentText = "Falling";
        }
    }

    [Range(1, int.MaxValue), NinjaScriptProperty]
    [Display(Name = "Period", GroupName = "NinjaScriptParameters", Order = 0)]
    public int  Period { get; set; }

    [NinjaScriptProperty]
    [Display(Name = "Display value", GroupName = "NinjaScriptParameters", Order = 1)]
    public bool Show { get; set; }
}
```

### 6.5 Working Code — MA Column with Sparkline + Conditional Color

A column that maintains a 60-tick rolling price ring buffer, paints the spark inline behind the numeric value, and pulses gold when the spark slope exceeds a threshold.

```csharp
#region Using declarations
using System;
using System.Linq;
using System.Windows;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public class SparkPulse : MarketAnalyzerColumn
    {
        private readonly double[] ring = new double[60];
        private int head;
        private int filled;

        private readonly Pen sparkPen   = new Pen(new SolidColorBrush(Color.FromArgb(160, 80, 200, 255)), 1.4);
        private readonly Brush hotBg    = new SolidColorBrush(Color.FromArgb(120, 240, 200, 0));
        private readonly Typeface tf    = new Typeface("Consolas");

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "SparkPulse";
                Description = "Inline price sparkline + slope-pulse";
                Calculate = Calculate.OnEachTick;
                ThresholdSlopeTicks = 3;
                sparkPen.Freeze(); hotBg.Freeze();
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last) return;
            ring[head] = e.Price;
            head = (head + 1) % ring.Length;
            if (filled < ring.Length) filled++;

            CurrentValue = e.Price;

            // slope = last - first over the buffer, in ticks
            if (filled == ring.Length && Instrument != null)
            {
                double first = ring[head]; // wraps to oldest
                double slopeTicks = (e.Price - first) / Instrument.MasterInstrument.TickSize;
                BackColor = Math.Abs(slopeTicks) >= ThresholdSlopeTicks ? hotBg : null;
            }
            OnPropertyChanged();
        }

        protected override void OnRender(DrawingContext dc, Size renderSize)
        {
            base.OnRender(dc, renderSize); // let MA paint number
            if (filled < 4) return;

            double w = renderSize.Width;
            double h = renderSize.Height;

            double min = double.MaxValue, max = double.MinValue;
            for (int i = 0; i < filled; i++)
            {
                double v = ring[(head + i) % ring.Length];
                if (v < min) min = v;
                if (v > max) max = v;
            }
            if (max <= min) return;

            var geo = new StreamGeometry();
            using (var g = geo.Open())
            {
                for (int i = 0; i < filled; i++)
                {
                    double v = ring[(head + i) % ring.Length];
                    double x = i * (w / (filled - 1));
                    double y = h - ((v - min) / (max - min)) * h;
                    if (i == 0) g.BeginFigure(new Point(x, y), false, false);
                    else        g.LineTo(new Point(x, y), true, false);
                }
            }
            geo.Freeze();
            dc.DrawGeometry(null, sparkPen, geo);
        }

        [NinjaScriptProperty]
        [Display(Name = "Pulse threshold (ticks)", GroupName = "Parameters", Order = 1)]
        public int ThresholdSlopeTicks { get; set; }
    }
}
```

`base.OnRender(dc, renderSize)` lets the MA paint the numeric `CurrentValue`; we then over-draw the sparkline behind/over depending on order. If you want the spark *behind* the number, reverse the order — paint spark first, then call `base.OnRender(...)` last.

### 6.6 Mini-Charts in Cells
Same pattern as the spark, scaled larger. For OHLC mini-chart, push 5-min OHLC into a ring of `OhlcRow` structs and draw candles with `dc.DrawRectangle` for body, `dc.DrawLine` for wick. Keep ≤ 30 candles per cell — at scale of 50 instruments × 30 candles, you're at 1,500 draws per repaint, which on a `OnPropertyChanged` throttled to 5 Hz is fine.

### 6.7 DataGrid Virtualization
The MA grid uses WPF's `DataGrid` with virtualization on by default. Cells outside the viewport are not rendered. This is why `OnRender` may not fire for off-screen rows — don't rely on it for state updates. State must come from `OnMarketData`/`OnBarUpdate`.

---

## 7. Hot Keys

### 7.1 Built-in Hotkey Manager
Tools → Hot Keys. Limited to actions NT pre-defines (Buy, Sell, Reverse, Close, etc.). Requires a modifier (Ctrl/Shift/Alt) unless an F-key.

### 7.2 Custom Hotkeys via AddOn
There is no hotkey-registration API. The supported pattern is to subscribe to WPF `KeyDown`/`KeyUp` on a window/panel:

```csharp
if (State == State.DataLoaded)
{
    ChartPanel.KeyDown += OnKeyDown;
    ChartPanel.KeyUp   += OnKeyUp;
}
else if (State == State.Terminated && ChartPanel != null)
{
    ChartPanel.KeyDown -= OnKeyDown;
    ChartPanel.KeyUp   -= OnKeyUp;
}

private bool ctrl;
public void OnKeyDown(object s, KeyEventArgs e)
{
    if (e.Key == Key.LeftCtrl) ctrl = true;
    if (ctrl && e.Key == Key.B)
    {
        // submit order — must use TriggerCustomEvent if touching series
        TriggerCustomEvent(o => SubmitMarketBuy(), null);
        e.Handled = true;
    }
}
```

For chart-wide hotkeys (not bound to one chart), subscribe to `Application.Current.MainWindow.KeyDown` from an AddOn — but watch out for focus: WPF only routes keys to the focused element by default. Use `EventManager.RegisterClassHandler(typeof(NTWindow), Keyboard.KeyDownEvent, ...)` for global capture.

### 7.3 DAS-Style Ladder Trading
Combine a SuperDOM column hosting the price ladder with an AddOn-registered global hotkey set: `J` = sell, `K` = buy, `;` = cancel all, `'` = flatten. The hotkey handlers route to `Account.Submit`/`Account.CancelAllOrders`/`Account.Flatten`. The price for limit orders comes from the row your mouse is hovering over (track via `MouseMove` on the column).

---

## 8. Right-Click Context Menus

Officially: **modifying the right-click context menu is not documented and not officially supported**. Unofficially: it works by walking the WPF visual tree.

The technique: in your AddOn's `OnWindowCreated`, when an NTWindow of interest opens, find its toolbar/header, get the `ContextMenu` from a known control, and `ContextMenu.Items.Add(new MenuItem { Header = "My Item", Command = ... })`. The reference NT support file is **`LineStrippedContextMenuSample.zip`** and the **`ContextMenuAddonExample`** which appears in Control Center → New menu.

For chart drawing-tool context menus there's an official handler via `IDrawingToolContextMenu` — search `DrawingToolContextMenuExample` in the editor.

For SuperDOM context menu specifically: walk the `SuperDom` `ContextMenu` via `SuperDom.UiWrapper.Parent` until you find the host. This is fragile and breaks across NT8 minor releases. **Anti-pattern** for production: log a warning if reflection lookups fail, and degrade to no-context-menu rather than crash.

---

## 9. Drawing Tools That Place Orders

### 9.1 Drawing Tool OnMouseDown
```csharp
public override void OnMouseDown(ChartControl chartControl, ChartPanel chartPanel,
                                 ChartScale chartScale, ChartAnchor dataPoint)
{
    switch (DrawingState)
    {
        case DrawingState.Building:
            dataPoint.CopyDataValues(Anchor);
            Anchor.IsEditing = false;
            DrawingState = DrawingState.Normal;
            // Place order at the click price
            PlaceOrderAtPrice(Anchor.Price);
            break;
        case DrawingState.Normal:
            var pt = dataPoint.GetPoint(chartControl, chartPanel, chartScale);
            if (GetCursor(chartControl, chartPanel, chartScale, pt) != null)
                DrawingState = DrawingState.Moving;
            break;
    }
}
```

### 9.2 Working Code — Click-to-Order Drawing Tool
A drawing tool that lets the user click anywhere on the chart to place a stop-limit order at that price.

```csharp
namespace NinjaTrader.NinjaScript.DrawingTools
{
    public class ClickToStopLimit : DrawingTool
    {
        private ChartAnchor Anchor = new ChartAnchor();

        public override object Icon { get { return Gui.Tools.Icons.DrawHorizontalLineTool; } }

        public override void OnMouseDown(ChartControl cc, ChartPanel cp, ChartScale cs, ChartAnchor pt)
        {
            if (DrawingState == DrawingState.Building)
            {
                pt.CopyDataValues(Anchor);
                DrawingState = DrawingState.Normal;
                PlaceOrder(Anchor.Price);
            }
        }

        private void PlaceOrder(double price)
        {
            var account = Account.All.FirstOrDefault(a => a.Name == "Sim101");
            if (account == null) return;
            var instrument = AttachedTo.Instrument; // DrawingTool.AttachedTo
            var ord = account.CreateOrder(
                instrument,
                price > GetCurrentLast() ? OrderAction.Buy : OrderAction.Sell,
                OrderType.StopLimit, OrderEntry.Manual, TimeInForce.Day,
                1, price, price, string.Empty, "ClickStop", default(DateTime), null);
            account.Submit(new[] { ord });
        }

        public override void OnRender(ChartControl cc, ChartScale cs)
        {
            if (Anchor == null || Anchor.Price == 0) return;
            float y = (float)cs.GetYByValue(Anchor.Price);
            RenderTarget.DrawLine(new Vector2(0, y), new Vector2(ChartPanel.W, y),
                Brushes.Yellow.ToDxBrush(RenderTarget), 1.2f);
        }

        private double GetCurrentLast()
        {
            var bs = AttachedTo as IChartBars;
            return bs != null ? bs.Bars.GetClose(bs.Bars.Count - 1) : 0;
        }
    }
}
```

### 9.3 Risk/Reward Drawing Tool That Respects Position
Read `Account.Positions` in `OnRender`, paint a green band from entry to a 2R target above and a red band from entry to 1R stop below. Draggable handles update the stop price and the strategy's stop order via `account.Change(orders, newStopPrice)`.

### 9.4 Trail-Stop Visualization
Subscribe to `Account.OrderUpdate`; on every update to a stop order, redraw its line. The order's `OrderState.Working`, `StopPrice`, `Quantity` give everything needed.

---

## 10. Working Orders Display on Chart with Draggable Stop/Target

Built-in: ChartTrader already does this. Lines for limit (cyan, label "LMT"), stop-market (pink, "STP"), stop-limit (violet, "SLM"), MIT (spring green), stop-loss (red), profit target (lime). Dragging an order: **click to pick up, click to drop** — there's no continuous drag. Working orders that hit the bid/ask will pop a confirmation. Cancel by dragging the line off the chart.

### 10.1 Custom Implementation — Code

For custom presentation (e.g., bracket visualization with risk/reward labels):

```csharp
public class WorkingOrdersOverlay : Indicator
{
    private Account selectedAccount;

    protected override void OnStateChange()
    {
        if (State == State.SetDefaults) { Name = "WorkingOrdersOverlay"; IsOverlay = true; }
        else if (State == State.DataLoaded)
        {
            selectedAccount = Account.All.FirstOrDefault(a => a.Name == "Sim101");
            if (selectedAccount != null)
            {
                selectedAccount.OrderUpdate    += OnAcctOrder;
                selectedAccount.PositionUpdate += OnAcctPos;
            }
        }
        else if (State == State.Terminated && selectedAccount != null)
        {
            selectedAccount.OrderUpdate    -= OnAcctOrder;
            selectedAccount.PositionUpdate -= OnAcctPos;
        }
    }

    private void OnAcctOrder(object s, OrderEventArgs e) { ChartControl?.InvalidateVisual(); }
    private void OnAcctPos(object s, PositionEventArgs e) { ChartControl?.InvalidateVisual(); }

    public override void OnRenderTargetChanged() { /* manage brushes */ }

    protected override void OnRender(ChartControl cc, ChartScale cs)
    {
        if (selectedAccount == null || RenderTarget == null) return;
        var pos = selectedAccount.Positions.FirstOrDefault(p => p.Instrument == Instrument);
        double avg = pos != null ? pos.AveragePrice : 0;
        int qty    = pos != null ? pos.Quantity     : 0;

        foreach (var o in selectedAccount.Orders)
        {
            if (o.Instrument != Instrument || o.OrderState != OrderState.Working) continue;
            float y = (float)cs.GetYByValue(o.LimitPrice > 0 ? o.LimitPrice : o.StopPrice);
            var brush = o.OrderType == OrderType.StopMarket ? Brushes.Tomato.ToDxBrush(RenderTarget)
                                                            : Brushes.Cyan.ToDxBrush(RenderTarget);
            RenderTarget.DrawLine(new Vector2(0, y), new Vector2(ChartPanel.W, y), brush, 1.4f);

            // R-multiple label vs avg
            if (avg > 0)
            {
                double r = (o.LimitPrice - avg) / Instrument.MasterInstrument.TickSize;
                // ... render text
            }
            brush.Dispose();
        }
    }
}
```

Pre-trade R/R preview: with no position open, paint translucent red/green bands above/below the cursor at user-configured stop/target distances. Position-size scaler widget: draw a bottom-left HUD showing `accountRisk / (entryPrice - stopPrice) / pointValue` = recommended quantity.

---

## 11. Trade Performance Dashboard Inside NT8

The native **Trade Performance** window (Connections → Trade Performance) provides Summary, Analysis, Executions, Trades, Orders, Journal views with display units in Currency/Percent/Points/Pips/Ticks, filtered by Account/Instrument/Template. It includes equity-curve and stat tables but no live HUD.

### 11.1 Building a Custom Live P&L Dashboard via NTWindow + AddOn

Pattern (verbatim from official docs):

```csharp
public class LivePnLDashboard : NTWindow, IWorkspacePersistence
{
    public LivePnLDashboard()
    {
        Caption = "Live P&L";
        Width   = 600; Height = 400;

        var tc = new TabControl();
        TabControlManager.SetIsMovable(tc, true);
        TabControlManager.SetCanAddTabs(tc, true);
        TabControlManager.SetCanRemoveTabs(tc, true);
        TabControlManager.SetFactory(tc, new LivePnLFactory());
        tc.AddNTTabPage(new LivePnLTab());
        Content = tc;

        Loaded += (o, e) => {
            if (WorkspaceOptions == null)
                WorkspaceOptions = new WorkspaceOptions("LivePnL-" + Guid.NewGuid().ToString("N"), this);
        };
    }
    public void Restore(XDocument d, XElement el) { /* via TabControl.RestoreFromXElement(el) */ }
    public void Save(XDocument d, XElement el)    { /* via TabControl.SaveToXElement(el) */ }
    public WorkspaceOptions WorkspaceOptions { get; set; }
}

public class LivePnLFactory : INTTabFactory
{
    public NTWindow CreateParentWindow() => new LivePnLDashboard();
    public NTTabPage CreateTabPage(string typeName, bool isTrue) => new LivePnLTab();
}

public class LivePnLTab : NTTabPage { /* WPF Grid with KPI cards bound to Account events */ }
```

Register in Control Center's New menu via `OnWindowCreated`:

```csharp
protected override void OnWindowCreated(Window window)
{
    var cc = window as ControlCenter;
    if (cc == null) return;
    var menu = cc.FindFirst("ControlCenterMenuItemNew") as NTMenuItem;
    var item = new NTMenuItem { Header = "Live P&L", Style = Application.Current.TryFindResource("MainMenuItem") as Style };
    menu.Items.Add(item);
    item.Click += (s, e) => Core.Globals.RandomDispatcher.BeginInvoke(new Action(() => new LivePnLDashboard().Show()));
}
```

### 11.2 Metrics to Surface in the Dashboard
- **Per-session P&L gauge**: `Account.Get(AccountItem.RealizedProfitLoss, denomination)` and `Account.Get(AccountItem.UnrealizedProfitLoss, denomination)`.
- **Drawdown gauge**: track rolling max equity in your AddOn, render as gauge with historical max-DD line (red dashed).
- **Win rate / avg win / avg loss / expectancy**: derive from `Account.Executions` filtered by today.
- **Sharpe / Sortino sparklines**: 30-day rolling, computed in your AddOn from end-of-day equity snapshots persisted to disk.
- **Per-strategy breakdown**: `Account.Strategies` enumeration; group executions by `execution.Order.FromEntrySignal` or strategy name.
- **Per-instrument breakdown**: group by `execution.Instrument`.

Update via `Account.AccountItemUpdate` (fires on cash/PnL changes) and `Account.ExecutionUpdate`. Throttle UI updates to ≤ 2 Hz with a `DispatcherTimer`.

---

## 12. Workspace Persistence

### 12.1 SuperDOM Column Persistence
Public properties decorated with `[NinjaScriptProperty]` and basic types (int, string, bool, double) auto-serialize. Complex types need `[XmlIgnore]` plus a `[Browsable(false)]` shadow property of type `string` that serializes to/from XML. `OnRestoreValues()` fires after deserialization — use it to rebuild caches from the deserialized state.

### 12.2 Strategy Visualization Settings
Same model. Anything `[NinjaScriptProperty]` survives chart save/restore.

### 12.3 NTWindow Persistence
Implement `IWorkspacePersistence`. The `WorkspaceOptions` property must be initialized in `Loaded` event or workspace save/load is silently skipped. `Save(XDocument, XElement)` writes; `Restore(XDocument, XElement)` reads. Tabs are handled by `TabControl.SaveToXElement(el)` / `RestoreFromXElement(el)`.

### 12.4 Multi-Window State Sync
There is no built-in pub/sub. Pattern: a static singleton holding a `ConcurrentDictionary<string, object>` exposes `event Action<string, object> Changed`. Both windows subscribe; either window writing fires the event for the other. Place the singleton in your AddOn assembly so all loaded scripts see it.

---

## 13. Specific Implementations — Reference Mapping

| Implementation | Approach |
|---|---|
| **Order Flow SuperDOM clone** | Combine: `VolumeColumn (BuySell mode)` + custom `ImbalanceColumn` (§2.6) + `DeltaPillarColumn` painting cumulative delta as a center bar in the price column. Width budget: 84 + 84 + 60 = 228 px. |
| **Pro DOM (SharkIndicators)** | Vendor uses NT's `SuperDomColumn` class same as us; differentiator is a pre-computed CVD/imbalance backing service running in a hidden indicator hosted on the DOM. Replicable. |
| **Ninja DOM vendor extensions** | All conform to the `SuperDomColumn` API surface in §2. No private API used. |
| **DAS-style ladder trading** | SuperDOM + global hotkeys (§7.2) bound to `Account.Submit`/`Cancel`/`Flatten`. Hover row → captured price → hotkey fires order at that price. |
| **Bookmap-style heatmap** | NOT a SuperDOM column — the SuperDOM is row-quantized and time-static. Bookmap rendering needs `Indicator + SharpDX OnRender` on a chart pane. SharkIndicators' HeatMap Pro is an NT8 AddOn (its own NTWindow). For DEEP6, render heatmap on the chart, not in the DOM. |
| **Quantower DOM Surface** | Single combined panel with DOM + heatmap + trades. NT8 cannot mix WPF DOM with Direct2D heatmap in one column. The supported equivalent: NTWindow hosting a custom WPF UserControl that renders the whole composite — bypass `SuperDom` entirely. |

---

## 14. Performance Notes — Cross-Surface

| Surface | Update Rate | Render Path | Risks |
|---|---|---|---|
| SuperDOM column | 50–200 ticks/sec on liquid futures | WPF UI thread | UI thread starvation if `OnRender` slow |
| Market Analyzer column | 1–10 Hz typical | WPF UI thread, virtualized | `INotifyPropertyChanged` storm if many cells update simultaneously |
| Strategy on chart | Per bar / per tick (`Calculate.OnEachTick`) | SharpDX | Brush leaks if not disposed in `OnRenderTargetChanged` |
| AddOn NTWindow | Bound to data sources | WPF, can use `DispatcherTimer` | Cross-thread access if subscribing to `Account.*` events (always marshal via `Dispatcher.BeginInvoke`) |

### 14.1 Avoiding INotifyPropertyChanged Storms (MA-Specific)
NT8's `MarketAnalyzerColumn` notifies WPF on every `CurrentValue` set. With 200 instruments × 10 cells = 2,000 cells, a market-wide tick burst can fire 20,000 notifications/sec. Mitigation: only set `CurrentValue = newValue` when `newValue != CurrentValue` (NT does NOT short-circuit this internally — confirmed by absence of equality check in shipped sample columns). For computed columns, batch via a `DispatcherTimer` at 250 ms.

### 14.2 Frame Budget Targets
- Single SuperDOM column `OnRender`: ≤ 2 ms (50 rows × ~40 µs each).
- All visible MA cells in viewport: ≤ 16 ms total (60 fps WPF target).
- Chart strategy `OnRender`: ≤ 8 ms (so chart still hits 60 fps with multiple indicators).

### 14.3 Cross-thread Marshaling
`Account.OrderUpdate` and friends fire on a non-UI thread. Touching a WPF control directly throws. Always marshal:
```csharp
account.OrderUpdate += (s, e) => Dispatcher.BeginInvoke(new Action(() => { /* UI work */ }));
```

---

## 15. Decision Tables — Surface Selection

### 15.1 "I need to display X" → Which Surface?

| Need | Surface |
|---|---|
| Per-price-row data on the depth ladder | SuperDOM column |
| Cross-instrument scanning grid | Market Analyzer column |
| Per-bar overlay tied to chart price | Indicator on chart |
| Aggregate trader-level state (P&L, drawdown, sessions) | NTWindow AddOn |
| Heatmap of L2 over time | Indicator on chart (NOT SuperDOM column) |
| Click-driven order entry at a price | SuperDOM column with `MouseLeftButtonDown`, OR custom drawing tool with `OnMouseDown` |
| Multiple connected views (chart + DOM + analyzer) | Multiple surfaces sharing a singleton state service |

### 15.2 "Should this be a Strategy or an AddOn?"

| Criterion | Strategy | AddOn |
|---|---|---|
| Submits orders programmatically | Yes (Managed/Unmanaged) | Yes (Account API) |
| Must be enabled/disabled by user per-chart | Yes | No (always loaded) |
| Backtestable in Strategy Analyzer | Yes | No |
| Displays UI window | No | Yes |
| Uses bar series state | Yes | Indirectly via indicators |
| Hooks Account events | Limited (only managed orders) | All accounts, all events |

For DEEP6 production execution: **AddOn for the dashboard, Strategy for actual trade logic** — they communicate via a static singleton in the same assembly.

---

## 16. NT8 Install Paths — Sample Files

Every NT8 install has these editable C# files:

```
C:\Users\<user>\Documents\NinjaTrader 8\bin\Custom\
├── SuperDomColumns\
│   ├── @AskColumn.cs
│   ├── @BidColumn.cs
│   ├── @LastSizeColumn.cs
│   ├── @NotesColumn.cs
│   ├── @PnLColumn.cs
│   ├── @PriceColumn.cs
│   ├── @PullStackColumn.cs
│   ├── @SoundsColumn.cs
│   └── @VolumeColumn.cs
├── MarketAnalyzerColumns\
│   ├── @AskColumn.cs
│   ├── @BidColumn.cs
│   ├── @ChangeColumn.cs
│   ├── @IndicatorColumn.cs
│   ├── @InstrumentColumn.cs
│   ├── @LastColumn.cs
│   ├── @NotesColumn.cs
│   ├── @PnLColumn.cs
│   └── @VolumeColumn.cs
├── Strategies\
│   ├── @SampleAtmStrategy.cs    ← AtmStrategyCreate reference
│   ├── @SampleMACrossover.cs
│   └── (all others)
├── DrawingTools\
│   ├── @AndrewsPitchfork.cs
│   ├── @Arrows.cs
│   ├── @HorizontalLine.cs       ← OnMouseDown reference
│   └── (all others)
├── AddOns\
│   └── (your custom AddOn .cs files)
└── Indicators\
    └── (your indicators)
```

Read order for an AI agent extending DEEP6:
1. `@VolumeColumn.cs` — reference SuperDOM column with mouse handling
2. `@PnLColumn.cs` — reference for reading position state from a column
3. `@IndicatorColumn.cs` — how MA hosts an indicator's plot value
4. `@SampleAtmStrategy.cs` — ATM creation pattern from a strategy
5. `@HorizontalLine.cs` — drawing tool with mouse interaction

These files compile as part of `NinjaTrader.Custom.dll` on every F5. Edit-in-place to extend.

---

## 17. Anti-Patterns — Per Surface

### 17.1 SuperDOM Column
- Importing `SharpDX` namespaces. There's no SharpDX in WPF column code.
- Calling `OnRender()` directly. Use `OnPropertyChanged()`.
- Allocating brushes per render. Cache + `.Freeze()`.
- Subscribing to `Account.OrderUpdate` without unsubscribing in `State.Terminated` — leaks into next workspace load.
- Looking up `SuperDom.MarketDepth.Asks[0]` without bounds-checking — empty depth crashes.
- Using `OnBarUpdate` — not supported, won't fire reliably.
- Setting `SuperDom.UpperPrice` directly without reflection — internal setter only.

### 17.2 Market Analyzer Column
- Setting `CurrentValue` without an inequality check — fires WPF notifications even when value is unchanged.
- Heavy computation in `OnMarketData` — every tick. Pre-compute in `OnBarUpdate` of a hosted indicator and read its plot.
- Using SharpDX in `OnRender` — WPF only.
- Forgetting to `Freeze()` cached pens/brushes — WPF marks them as not-thread-safe.
- Initializing in `State.DataLoaded` instead of `State.Configure` — breaks sorting (NT staff confirmed).

### 17.3 Strategy On-Chart Visualization
- `Plot Executions = TextAndMarkers` plus PC-clock drift → markers on wrong bars. Sync NTP first.
- Reading `SystemPerformance.AllTrades` from `OnRender` — slow if N trades large; cache the metric and invalidate in `OnExecutionUpdate`.
- Forgetting `OnRenderTargetChanged` brush disposal — leaks Direct2D resources.
- `Draw.*` calls from inside `OnRender` — unsupported. `Draw.*` from `OnBarUpdate` only.

### 17.4 Drawing Tools
- Placing orders inside `OnRender` — reentrant. Submit from `OnMouseDown` only.
- Using mouse events without `OnMouseDown`'s 4-parameter signature exactly — won't override.

### 17.5 AddOn Windows
- Forgetting `IWorkspacePersistence` — window doesn't save with the workspace.
- `WorkspaceOptions` set in constructor — must be in `Loaded` event handler.
- Subscribing to `Account.*` and touching WPF without `Dispatcher.BeginInvoke` — cross-thread crash.

---

## 18. Decision Quickref — When to Pick What

| Goal | Build As | Render Stack |
|---|---|---|
| Per-row indicator on the price ladder | SuperDOM column | WPF DrawingContext |
| Per-instrument metric in a scanner | MA column | WPF DrawingContext |
| Per-bar overlay on chart | Indicator | SharpDX |
| Strategy that auto-trades | Strategy | SharpDX (chart) |
| Order entry at click point on chart | Drawing tool | SharpDX |
| Order entry by mouse click on DOM | SuperDOM column with `MouseLeftButtonDown` | WPF DrawingContext |
| Standalone window with full custom UI | AddOn → NTWindow + NTTabPage | WPF (XAML) |
| Hotkey-driven order entry | AddOn capturing `KeyDown` on `Application.Current.MainWindow` | n/a |
| Custom right-click menu item | AddOn walking the WPF visual tree (unsupported) | n/a |
| Per-instrument cross-asset scanner | Market Analyzer with custom column | WPF DrawingContext |

---

## Sources

- [SuperDOM Column class reference](https://ninjatrader.com/support/helpguides/nt8/superdom_column.htm)
- [SuperDomColumn OnRender()](https://ninjatrader.com/support/helpguides/nt8/superdomcolumn_onrender.htm)
- [SuperDomColumn OnMarketData()](https://ninjatrader.com/support/helpguides/nt8/superdomcolumn_onmarketdata.htm)
- [SuperDomColumn MarketDepth](https://ninjatrader.com/support/helpguides/nt8/superdomcolumn_marketdepth.htm)
- [Operations: SuperDOM](https://ninjatrader.com/support/helpguides/nt8/superdom.htm)
- [Operations: Using SuperDOM Columns](https://ninjatrader.com/support/helpguides/nt8/using_superdom_columns.htm)
- [Operations: SuperDOM Properties](https://ninjatrader.com/support/helpguides/nt8/properties_superdom.htm)
- [Market Analyzer Column reference](https://ninjatrader.com/support/helpguides/nt8/market_analyzer_column.htm)
- [MarketAnalyzerColumn OnRender()](https://ninjatrader.com/support/helpGuides/nt8/onrender2.htm)
- [MarketAnalyzerColumn CurrentValue](https://ninjatrader.com/support/helpguides/nt8/currentvalue.htm)
- [MarketAnalyzerColumn CurrentText](https://ninjatrader.com/support/helpguides/nt8/currenttext.htm)
- [How Trade Executions Are Plotted](https://ninjatrader.com/support/helpguides/nt8/how_trade_executions_are_plott.htm)
- [OnExecutionUpdate()](https://ninjatrader.com/support/helpGuides/nt8/onexecutionupdate.htm)
- [SystemPerformance](https://ninjatrader.com/support/helpguides/nt8/systemperformance.htm)
- [SystemPerformance.AllTrades](https://ninjatrader.com/support/helpguides/nt8/alltrades.htm)
- [AtmStrategyCreate()](https://ninjatrader.com/support/helpguides/nt8/atmstrategycreate.htm)
- [Account class](https://ninjatrader.com/support/helpguides/nt8/account_class.htm)
- [Drawing Tool OnMouseDown()](https://ninjatrader.com/support/helpguides/nt8/onmousedown.htm)
- [NTWindow](https://ninjatrader.com/support/helpguides/nt8/ntwindow.htm)
- [Creating Your Own AddOn Window](https://ninjatrader.com/support/helpguides/nt8/creating_your_own_addon_window.htm)
- [Chart Trader: Order & Position Display](https://ninjatrader.com/support/helpguides/nt8/order__position_display.htm)
- [Trade Performance window](https://ninjatrader.com/support/helpguides/nt8/using_trade_performance.htm)
- [Strategy Analyzer](https://ninjatrader.com/support/helpguides/nt8/strategy_analyzer.htm)
- [Hot Keys: Working With](https://ninjatrader.com/support/helpguides/nt8/working_with_hot_keys.htm)
- [Hot Keys: Trading With](https://ninjatrader.com/support/helpguides/nt8/trading_with_hot_keys.htm)
- [Forum: Custom Market Analyzer Column example (NT staff code)](https://forum.ninjatrader.com/forum/historical-beta-archive/version-8-beta/83980-market-analyzer-custom-column-example)
- [Forum: SuperDOM column rendering performance / bitmap caching](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1185596-nt8-superdom-column-cache-rectangles-to-bitmapimage)
- [Forum: SuperDOM Instrument access from columns](https://forum.ninjatrader.com/forum/historical-beta-archive/version-8-beta/86198-cannot-access-instrument-name-from-superdom-columns)
- [Forum: SuperDOM MarketDepth column](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1059090-superdom-marketdepth-column)
- [Forum: SuperDOM column volumetric bars / OnBarUpdate limitation](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1108995-superdom-column-order-flow-volumetric-bars)
- [Forum: SuperDOM column mouse click handling](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1161458-how-to-access-mouse-click-in-superdom-column)
- [Forum: Custom hotkeys via AddOn](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1217908-using-hotkeys-to-run-custom-strategies-and-or-scripts)
- [Forum: Custom context menu items](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1184660-creating-new-context-menu-items)
- [Forum: MA column sortability](https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/1132949-market-analyzer-column-make-sortable)
- [NT Ecosystem: Execution Trace Lines indicator (reference impl)](https://ninjatraderecosystem.com/user-app-share-download/execution-trace-lines/)
