# Pine Script Volume Profile & LVN Patterns

Pine's VP tooling spans three tiers: built-in `volume.profile_*` functions (simple, limited programmatic access), the `LibVPrf` community library (advanced, full structural decomposition), and `request.footprint()` (native per-row buy/sell, Premium only since Jan 2026). Choose based on what you need to do with the data.

---

## Tier 1: Built-In VP (Simplest)

```pinescript
//@version=5
indicator("Volume Profile", overlay=true)

profile = volume.profile_fixed(lookback=100, numberOfRows=30, valueAreaPercentage=70)

if barstate.islast and not na(profile)
    profile.plot(
        upVolumeColor   = color.new(color.lime, 40),
        downVolumeColor = color.new(color.red, 40),
        pocColor        = color.yellow,
        vahColor        = color.new(color.blue, 60),
        valColor        = color.new(color.blue, 60),
    )
```

**Limitation:** You can render the profile but cannot iterate individual rows or extract HVN/LVN prices programmatically. Use this for visual reference only. For signal generation, you need Tier 2 or 3.

---

## Previous Session POC via request.security

Pull the prior session's POC as a horizontal level. Works on any timeframe.

```pinescript
//@version=5
indicator("Prev Session POC", overlay=true)

prevPOC = request.security(
    syminfo.tickerid,
    "D",
    volume.profile_session(30, 70).poc_price[1]
)

plot(prevPOC, "Prev POC", color=color.orange, linewidth=2, style=plot.style_line)

// Alert when price crosses previous POC
alertcondition(
    ta.crossover(close, prevPOC) or ta.crossunder(close, prevPOC),
    title="POC Cross",
    message="Price crossed previous session POC at {{plot_0}}"
)
```

The `[1]` offset is critical. Without it you get the current session's POC, which changes every bar.

---

## Tier 2: LibVPrf (AustrianTradingMachine)

The most capable open-source VP library in Pine. Supports PDF volume allocation, dynamic buy/sell splitting, structural decomposition (bimodal detection), and CVD tracking.

```pinescript
//@version=5
indicator("LibVPrf Demo", overlay=true, max_boxes_count=500, max_lines_count=500)

import AustrianTradingMachine/LibVPrf/3 as vp

// Create profile with 50 buckets, dynamic range, 70% value area
profile = vp.create(
    buckets          = 50,
    rangeUp          = high,
    rangeLo          = low,
    dynamic          = true,
    valueArea        = 70,
    allot            = vp.AllotMode.pdf,      // PDF allocation (smoother than equal)
    split            = vp.SplitMode.dynamic,  // Dynamic buy/sell split
)

// Update on each bar
vp.update(profile, high, low, volume)

// Extract structural levels
poc   = vp.getPOC(profile)
vah   = vp.getVAH(profile)
val   = vp.getVAL(profile)
shape = vp.getShape(profile)  // Returns: "D", "P", "b", "B", "double"

// Render
if barstate.islast
    vp.draw(profile, x1=bar_index - 100, x2=bar_index)
    label.new(bar_index, poc, "POC: " + str.tostring(poc, "#.##"), style=label.style_label_left)
```

**AllotMode options:**
- `pdf`: Distributes volume proportionally across the bar's range using a probability density function. Produces smoother profiles.
- `equal`: Splits volume equally across all touched price levels. Faster but creates flat plateaus.

**SplitMode options:**
- `dynamic`: Estimates buy/sell split from bar close position within range.
- `fixed`: Uses a fixed ratio (e.g., 50/50).

**Shape classification:**
- `D`: Single peak near midpoint. Balanced, mean-reverting day.
- `P`: Peak in upper half. Distribution above, bearish lean.
- `b`: Peak in lower half. Accumulation below, bullish lean.
- `B`: Bimodal. Two distinct clusters. Trending or contested day.
- `double`: Two roughly equal peaks. High uncertainty, range-bound.

---

## Custom LVN Detector (No Library)

When you need full control over LVN detection logic without importing a library. Builds the profile from bar data, finds local minima, and renders as horizontal lines.

```pinescript
//@version=5
indicator("Custom LVN Detector", overlay=true, max_lines_count=500, max_boxes_count=500)

// --- Parameters ---
lookback    = input.int(100, "Lookback Bars", minval=20, maxval=500)
n_rows      = input.int(40, "Profile Rows", minval=10, maxval=100)
lvn_pct     = input.float(0.30, "LVN Threshold (fraction of mean)", minval=0.05, maxval=0.80, step=0.05)
show_hist   = input.bool(true, "Show Histogram")

// --- Build profile ---
var float[] row_prices  = array.new_float(0)
var float[] row_volumes = array.new_float(0)

if barstate.islast
    array.clear(row_prices)
    array.clear(row_volumes)

    float hi = ta.highest(high, lookback)
    float lo = ta.lowest(low, lookback)
    float row_size = (hi - lo) / n_rows

    // Initialize rows
    for i = 0 to n_rows - 1
        array.push(row_prices, lo + row_size * i + row_size * 0.5)
        array.push(row_volumes, 0.0)

    // Distribute volume
    for i = 0 to lookback - 1
        bar_lo = low[i]
        bar_hi = high[i]
        bar_vol = volume[i]

        // Count touched rows
        touched = 0
        for r = 0 to n_rows - 1
            row_lo = lo + row_size * r
            row_hi = row_lo + row_size
            if bar_hi >= row_lo and bar_lo <= row_hi
                touched += 1

        if touched > 0
            vol_per = bar_vol / touched
            for r = 0 to n_rows - 1
                row_lo = lo + row_size * r
                row_hi = row_lo + row_size
                if bar_hi >= row_lo and bar_lo <= row_hi
                    array.set(row_volumes, r, array.get(row_volumes, r) + vol_per)

    // Detect LVN: local minima below threshold
    float mean_vol = array.avg(row_volumes)
    float lvn_cutoff = mean_vol * lvn_pct
    float max_vol = array.max(row_volumes)

    for r = 1 to n_rows - 2
        vol_prev = array.get(row_volumes, r - 1)
        vol_curr = array.get(row_volumes, r)
        vol_next = array.get(row_volumes, r + 1)
        price    = array.get(row_prices, r)

        bool is_local_min = vol_curr < vol_prev and vol_curr < vol_next
        bool below_threshold = vol_curr < lvn_cutoff

        if is_local_min and below_threshold
            line.new(
                x1    = bar_index - lookback,
                y1    = price,
                x2    = bar_index + 10,
                y2    = price,
                color = color.new(color.red, 30),
                width = 1,
                style = line.style_dashed,
            )

    // Render histogram boxes
    if show_hist
        for r = 0 to n_rows - 1
            vol  = array.get(row_volumes, r)
            price = array.get(row_prices, r)
            bar_width = math.round(vol / max_vol * 20)

            box.new(
                left   = bar_index - lookback,
                top    = price + row_size * 0.45,
                right  = bar_index - lookback + bar_width,
                bottom = price - row_size * 0.45,
                bgcolor = color.new(color.blue, 70),
                border_color = color.new(color.blue, 50),
            )
```

This approach is self-contained but hits Pine's box/line limits quickly. For production use, limit to the 20 most significant LVN levels and clear old drawings on each update.

---

## request.footprint() (Jan 2026, Premium Only)

Native footprint data with per-row buy/sell volume and imbalance detection. Only available on TradingView Premium plans.

```pinescript
//@version=5
indicator("Footprint LVN", overlay=false)

// request.footprint returns intrabar data at the specified resolution
footprint = request.footprint(syminfo.tickerid, "1")  // 1-minute footprint

rows = footprint.rows()

float total_buy  = 0.0
float total_sell = 0.0
float max_row_vol = 0.0

for row in rows
    buy_vol  = row.buy_volume()
    sell_vol = row.sell_volume()
    delta    = row.delta()
    price    = row.price()
    total    = buy_vol + sell_vol

    total_buy  += buy_vol
    total_sell += sell_vol
    max_row_vol := math.max(max_row_vol, total)

// Session delta
session_delta = total_buy - total_sell
plot(session_delta, "Session Delta", color=session_delta > 0 ? color.lime : color.red)

// Imbalance detection: rows where buy/sell ratio > 3:1
for row in rows
    buy_vol  = row.buy_volume()
    sell_vol = row.sell_volume()
    if sell_vol > 0 and buy_vol / sell_vol > 3.0
        label.new(bar_index, row.price(), "BUY IMBALANCE", style=label.style_label_right, color=color.lime)
    if buy_vol > 0 and sell_vol / buy_vol > 3.0
        label.new(bar_index, row.price(), "SELL IMBALANCE", style=label.style_label_left, color=color.red)
```

**Availability:** `request.footprint()` requires TradingView Premium. It returns an array of row objects for the current bar at the specified lower timeframe. Each row has `.buy_volume()`, `.sell_volume()`, `.delta()`, `.price()`, and `.imbalance()` methods.

---

## Multi-TF Data with request.security_lower_tf()

Pull intrabar data for custom VP construction. Returns arrays of values, one per intrabar period.

```pinescript
//@version=5
indicator("Multi-TF VP", overlay=true)

// Adaptive timeframe selection
tf = timeframe.period == "D" ? "60" :
     timeframe.period == "60" ? "5" :
     timeframe.period == "15" ? "1" : "1"

// Pull intrabar highs, lows, volumes
intrabar_highs   = request.security_lower_tf(syminfo.tickerid, tf, high)
intrabar_lows    = request.security_lower_tf(syminfo.tickerid, tf, low)
intrabar_volumes = request.security_lower_tf(syminfo.tickerid, tf, volume)

// Count intrabar periods
n = array.size(intrabar_highs)

// Build mini-profile for current bar
float bar_poc = na
float max_vol = 0.0

if n > 0
    for i = 0 to n - 1
        v = array.get(intrabar_volumes, i)
        if v > max_vol
            max_vol := v
            bar_poc := (array.get(intrabar_highs, i) + array.get(intrabar_lows, i)) / 2

plot(bar_poc, "Intrabar POC", color=color.yellow, style=plot.style_circles)
```

**Limit:** `request.security_lower_tf()` returns up to 5,000 intrabar bars total. On a daily chart pulling 1-minute data, that's roughly 3-4 days of history. Plan your lookback accordingly.

---

## TradingView Limits

| Constraint | Limit |
|------------|-------|
| Max boxes | 500 |
| Max lines | 500 |
| Max labels | 500 |
| Historical bars (standard) | 5,000 |
| Historical bars (Premium) | 50,000 |
| security_lower_tf bars | 5,000 max |
| request.footprint() | Premium only |

When building VP histograms with boxes, you'll hit 500 fast. Strategies:
1. Only render the current session's profile (clear on session open).
2. Limit histogram to the value area (VAH to VAL) and render LVN lines only outside it.
3. Use lines instead of boxes for the histogram bars (500 lines vs 500 boxes = same limit, but lines are thinner and less visually cluttered).

---

## Alert Integration

Send LVN crosses to the Python backend via webhook.

```pinescript
//@version=5
strategy("LVN Alert Bridge", overlay=true)

// Assume lvn_level is computed from one of the approaches above
float lvn_level = na  // Replace with actual LVN detection

// Webhook payload format matches DEEP6 signal schema
crossed_up   = ta.crossover(close, lvn_level)
crossed_down = ta.crossunder(close, lvn_level)

if crossed_up
    alert(
        '{"signal":"LVN_CROSS","direction":"up","price":' + str.tostring(close) +
        ',"lvn":' + str.tostring(lvn_level) + ',"symbol":"' + syminfo.ticker + '"}',
        alert.freq_once_per_bar_close
    )

if crossed_down
    alert(
        '{"signal":"LVN_CROSS","direction":"down","price":' + str.tostring(close) +
        ',"lvn":' + str.tostring(lvn_level) + ',"symbol":"' + syminfo.ticker + '"}',
        alert.freq_once_per_bar_close
    )

// Named alertcondition for manual alert setup
alertcondition(crossed_up or crossed_down, title="LVN Cross", message="LVN level crossed")
```

Use `alert.freq_once_per_bar_close` to avoid duplicate alerts within a bar. The JSON payload maps directly to the DEEP6 signal schema consumed by the FastAPI webhook endpoint.
