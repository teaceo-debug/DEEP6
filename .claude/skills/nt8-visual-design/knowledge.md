# NT8 Visual Design Bible
> Load this skill for ANY NinjaTrader 8 visual/rendering work.
> Synthesized from: Bloomberg Terminal, Jigsaw Daytradr, ATAS, Bookmap, Exocharts,
> Sierra Chart, CQG, Trading Technologies + DEEP6 codebase + color science research.

---

## Section 1: COLOR SYSTEM

### Primary Palette — "Institutional"

These are the foundation colors for all DEEP6 NinjaTrader indicators. Designed for extended dark-background trading sessions (6+ hours) with minimal eye strain.

| Role | Hex | RGB | Color4 (SharpDX) | Usage |
|------|-----|-----|-------------------|-------|
| Background | `#0E1014` | `14, 16, 20` | `new Color4(0.055f, 0.063f, 0.078f, 1f)` | Chart background, panel fills |
| Surface | `#1A1A2E` | `26, 26, 46` | `new Color4(0.102f, 0.102f, 0.180f, 1f)` | Card backgrounds, elevated panels, HUD containers |
| Grid | `#262C36` | `38, 44, 54` | `new Color4(0.149f, 0.173f, 0.212f, 1f)` | Grid lines, subtle borders, separators |
| Text Primary | `#F2F4F8` | `242, 244, 248` | `new Color4(0.949f, 0.957f, 0.973f, 1f)` | Main data, prices, volumes, scores |
| Text Secondary | `#9BA3AE` | `155, 163, 174` | `new Color4(0.608f, 0.639f, 0.682f, 1f)` | Labels, headers, descriptions |
| Text Tertiary | `#5A636E` | `90, 99, 110` | `new Color4(0.353f, 0.388f, 0.431f, 1f)` | Timestamps, footnotes, inactive states |

### Semantic Colors

These colors encode meaning. They are never decorative — every color communicates a specific market condition.

| Semantic Role | Hex | RGB | Color4 (SharpDX) | When to Use |
|---------------|-----|-----|-------------------|-------------|
| Long / Buy | `#00E676` | `0, 230, 118` | `new Color4(0f, 0.902f, 0.463f, 1f)` | Buy signals, long entries, positive delta, bid absorption confirmation |
| Short / Sell | `#FF1744` | `255, 23, 68` | `new Color4(1f, 0.090f, 0.267f, 1f)` | Sell signals, short entries, negative delta, ask absorption confirmation |
| Watch / Caution | `#FFB300` | `255, 179, 0` | `new Color4(1f, 0.702f, 0f, 1f)` | Approaching threshold, building signal, pre-trigger states |
| Neutral | `#8A929E` | `138, 146, 158` | `new Color4(0.541f, 0.573f, 0.620f, 1f)` | No signal, idle state, balanced conditions |
| Absorption | `#00E0FF` | `0, 224, 255` | `new Color4(0f, 0.878f, 1f, 1f)` | Absorption detected — large resting orders absorbing aggression |
| Exhaustion | `#FF38C8` | `255, 56, 200` | `new Color4(1f, 0.220f, 0.784f, 1f)` | Exhaustion detected — aggressive side running out of fuel |
| POC (Point of Control) | `#FFD23F` | `255, 210, 63` | `new Color4(1f, 0.824f, 0.247f, 1f)` | Highest volume price in footprint bar, value area center |
| VAH / VAL | `#C8D17A` | `200, 209, 122` | `new Color4(0.784f, 0.820f, 0.478f, 1f)` | Value Area High / Low boundaries (70% volume range) |

### Tinted Fills (Alpha Overlays)

Used for background fills on cells, zones, and regions. Alpha values are carefully calibrated for dark backgrounds.

| Fill Purpose | Base Color | Alpha | Color4 (SharpDX) | Usage |
|-------------|-----------|-------|-------------------|-------|
| Absorption Zone | `#00E0FF` (Cyan) | 22% (0.22f) | `new Color4(0f, 0.878f, 1f, 0.22f)` | Background fill for cells with absorption detected |
| Exhaustion Zone | `#FF38C8` (Magenta) | 22% (0.22f) | `new Color4(1f, 0.220f, 0.784f, 0.22f)` | Background fill for cells with exhaustion detected |
| Imbalance Tier 1 (Mild) | Direction color | 18% (0.18f) | Long: `new Color4(0f, 0.902f, 0.463f, 0.18f)` | 150-300% diagonal imbalance ratio |
| Imbalance Tier 2 (Strong) | Direction color | 28% (0.28f) | Long: `new Color4(0f, 0.902f, 0.463f, 0.28f)` | 300-500% diagonal imbalance ratio |
| Imbalance Tier 3 (Extreme) | Direction color | 40% (0.40f) | Long: `new Color4(0f, 0.902f, 0.463f, 0.40f)` | 500%+ diagonal imbalance ratio (add corner brackets) |

### Color4 Conversion Reference

SharpDX `Color4` uses normalized floats (0.0–1.0), not 0–255 bytes.

**Conversion formula:**
```csharp
// Hex to Color4
// #RRGGBB → new Color4(R/255f, G/255f, B/255f, alpha)
// Example: #00E676 → new Color4(0x00/255f, 0xE6/255f, 0x76/255f, 1f)
//                   = new Color4(0f, 0.902f, 0.463f, 1f)

// Quick reference for common alpha values:
// 100% = 1.00f    80% = 0.80f    60% = 0.60f
//  50% = 0.50f    40% = 0.40f    28% = 0.28f
//  22% = 0.22f    18% = 0.18f    10% = 0.10f

// From System.Windows.Media.Color to SharpDX Color4:
private SharpDX.Color4 ToColor4(System.Windows.Media.Color c, float alphaOverride = -1f)
{
    return new SharpDX.Color4(
        c.R / 255f,
        c.G / 255f,
        c.B / 255f,
        alphaOverride >= 0f ? alphaOverride : c.A / 255f
    );
}
```

### Color Blindness Safety Rules

**Critical fact:** ~8% of males have red-green color vision deficiency (deuteranopia/protanopia). Trading is male-dominated. You MUST design for this.

**Rules:**
1. **NEVER rely on red vs green alone** to convey long/short. Always pair with a secondary indicator:
   - Shape: ▲ for long, ▼ for short
   - Label text: "LONG" / "SHORT" or "BUY" / "SELL"
   - Position: long markers above price, short markers below
   - Pattern: solid fill for long, hatched/dashed for short
2. **Use luminance contrast** — `#00E676` (green) has different luminance than `#FF1744` (red). This helps but is not sufficient alone.
3. **Absorption (#00E0FF cyan) vs Exhaustion (#FF38C8 magenta)** — this pair is safe. Cyan and magenta are distinguishable by all common color vision types.
4. **Test with a simulator** — use Coblis (Color Blindness Simulator) or Chrome DevTools → Rendering → Emulate vision deficiencies.
5. **When in doubt, add a text label.** Text is universally accessible.

### Alternative Palettes

#### "High Contrast" — Daylight / Bright Ambient

For traders in sunlit rooms or using low-contrast monitors.

| Role | Hex | Notes |
|------|-----|-------|
| Background | `#FAFBFC` | Near-white, not pure white (avoids glare) |
| Surface | `#F0F2F5` | Slight gray lift |
| Grid | `#D1D5DB` | Visible on light background |
| Text Primary | `#111827` | Near-black |
| Text Secondary | `#6B7280` | Medium gray |
| Long / Buy | `#059669` | Darker green (meets WCAG AA on light bg) |
| Short / Sell | `#DC2626` | Darker red (meets WCAG AA on light bg) |
| Absorption | `#0891B2` | Darker cyan |
| Exhaustion | `#C026D3` | Darker magenta |

#### "Night Trading" — Extended Session (6+ Hours)

Ultra-low luminance for overnight/marathon sessions. Reduces total screen light output by ~40% vs Institutional palette.

| Role | Hex | Notes |
|------|-----|-------|
| Background | `#08090B` | Near-black |
| Surface | `#111318` | Barely visible elevation |
| Grid | `#1C2028` | Subtle, not distracting |
| Text Primary | `#D4D8E0` | Dimmed white (less harsh) |
| Text Secondary | `#7A8290` | Dimmed secondary |
| Long / Buy | `#00C853` | Slightly dimmed green |
| Short / Sell | `#E53935` | Slightly dimmed red |
| Absorption | `#00B8D4` | Slightly dimmed cyan |
| Exhaustion | `#E040A0` | Slightly dimmed magenta |

---

## Section 2: TYPOGRAPHY

### Font Stack

| Priority | Font | Usage | Rationale |
|----------|------|-------|-----------|
| Primary Data | **Consolas** | All numeric data: prices, volumes, deltas, scores, counts | Monospace ensures columnar alignment; tabular numerals prevent layout shifts; pre-installed on all Windows |
| Labels & Headers | **Segoe UI** | Section headers, signal names, status text, descriptive labels | Windows system font; clean humanist sans-serif; excellent at small sizes |
| Glyphs & Symbols | **Segoe UI Symbol** | ▲ ▼ ● ◆ ◀ ▶ ★ ⚡ arrows, geometric shapes | Fallback for Unicode symbols when Consolas lacks the glyph |

### Size Hierarchy

All sizes in device-independent points (pt). SharpDX `TextFormat` takes points directly.

| Level | Size | Font | Weight | Usage | Example |
|-------|------|------|--------|-------|---------|
| Hero | 32pt | Consolas | Bold (700) | Primary action word on HUD | "LONG", "SHORT", "WAIT" |
| Score | 20pt | Consolas | SemiBold (600) | Confidence score, main metric | "87", "92.4" |
| Tier | 14pt | Segoe UI | SemiBold (600) | Signal tier, category labels | "TIER 1", "ABSORPTION" |
| Entry / Stop | 12pt | Consolas | Medium (500) | Price levels, entry/stop/target | "21,450.25", "SL: 21,438.00" |
| Cells | 9pt | Consolas | Regular (400) | Footprint cell bid/ask volumes | "  42 x 87  " |
| Labels | 8pt | Segoe UI | Regular (400) | Axis labels, timestamps, footnotes | "14:32:05", "NQ 03-26" |

### Dark Background Typography Rules

On dark backgrounds (#0E1014 to #1A1A2E), thin text becomes illegible due to subpixel rendering. Follow these rules:

1. **Minimum weight: 500 (Medium)** — Never use Regular (400) or Light (300) for text smaller than 14pt on dark backgrounds. Exception: 9pt cell data where Consolas Regular at 400 is acceptable because monospace fonts have naturally wider strokes.
2. **Letter spacing: +0.5px at small sizes** — For text ≤ 10pt, add 0.5px letter spacing to prevent character collision. In SharpDX, use `TextLayout` and adjust `SetCharacterSpacing()`.
3. **Rendering mode: NaturalSymmetric** — Use `SharpDX.DirectWrite.RenderingMode.NaturalSymmetric` for best clarity on dark backgrounds. This gives symmetrical anti-aliasing that prevents the "thin on one side" artifact.
4. **ClearType limitation** — SharpDX renders text with grayscale anti-aliasing, not ClearType. This means text looks slightly different from WPF/GDI+ rendered text. Accept this — do not fight it.

### Tabular Numerals

**Mandatory for all price and volume data.** Tabular (fixed-width) numerals ensure that "1" takes the same horizontal space as "8", preventing layout shifts when values change.

- Consolas is inherently monospace — all characters including digits are tabular. ✓
- If using Segoe UI for any numeric display (not recommended), you must enable OpenType `tnum` feature.
- Test: render "111,111" and "888,888" — they must be exactly the same pixel width.

```csharp
// SharpDX TextFormat creation with correct settings
private SharpDX.DirectWrite.TextFormat CreateDataFont(float sizePt)
{
    return new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory,
        "Consolas",                                    // Monospace = tabular numerals
        SharpDX.DirectWrite.FontWeight.Medium,         // 500 weight for dark bg
        SharpDX.DirectWrite.FontStyle.Normal,
        sizePt                                         // Size in points
    );
}

// For labels (non-numeric):
private SharpDX.DirectWrite.TextFormat CreateLabelFont(float sizePt)
{
    return new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory,
        "Segoe UI",
        SharpDX.DirectWrite.FontWeight.SemiBold,       // 600 for headers
        SharpDX.DirectWrite.FontStyle.Normal,
        sizePt
    );
}
```

---

## Section 3: SHARPDX RENDERING TECHNIQUES

### Brush Creation Pattern

**CRITICAL:** Brushes are GPU resources tied to a specific RenderTarget. They MUST be created in `OnRenderTargetChanged()` and disposed there (or in the previous cycle). Creating brushes in `OnRender()` causes GPU memory leaks and frame drops.

```csharp
// === Correct brush lifecycle ===

// Fields
private SharpDX.Direct2D1.Brush longBrush;
private SharpDX.Direct2D1.Brush shortBrush;
private SharpDX.Direct2D1.Brush absorptionBrush;
private SharpDX.Direct2D1.Brush absorptionFillBrush;
private SharpDX.Direct2D1.Brush surfaceBrush;
private SharpDX.Direct2D1.Brush textPrimaryBrush;

public override void OnRenderTargetChanged()
{
    // Dispose old brushes first (SafeDispose handles null)
    if (longBrush != null)        { longBrush.Dispose();        longBrush = null; }
    if (shortBrush != null)       { shortBrush.Dispose();       shortBrush = null; }
    if (absorptionBrush != null)  { absorptionBrush.Dispose();  absorptionBrush = null; }
    if (absorptionFillBrush != null) { absorptionFillBrush.Dispose(); absorptionFillBrush = null; }
    if (surfaceBrush != null)     { surfaceBrush.Dispose();     surfaceBrush = null; }
    if (textPrimaryBrush != null) { textPrimaryBrush.Dispose(); textPrimaryBrush = null; }

    if (RenderTarget == null) return;

    // Create new brushes for current render target
    longBrush           = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.902f, 0.463f, 1f));      // #00E676
    shortBrush          = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1f, 0.090f, 0.267f, 1f));      // #FF1744
    absorptionBrush     = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 1f));          // #00E0FF
    absorptionFillBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 0.22f));       // #00E0FF @ 22%
    surfaceBrush        = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.102f, 0.102f, 0.180f, 1f));  // #1A1A2E
    textPrimaryBrush    = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0.949f, 0.957f, 0.973f, 1f));  // #F2F4F8
}
```

### SafeDispose Pattern

```csharp
// Helper for safe resource disposal — use throughout OnRenderTargetChanged and OnStateChange(Terminated)
private void SafeDispose<T>(ref T resource) where T : class, IDisposable
{
    try
    {
        if (resource != null)
        {
            resource.Dispose();
            resource = null;
        }
    }
    catch (Exception) { resource = null; }
}

// Usage:
SafeDispose(ref longBrush);
SafeDispose(ref shortBrush);
SafeDispose(ref cellTextFormat);
```

### LinearGradientBrush — Volume Heatmaps

Use for coloring cells or bars by relative volume intensity. Multi-stop gradients create smooth transitions.

```csharp
// Volume heatmap: Blue (low) → Cyan → Yellow → Red (high)
private SharpDX.Direct2D1.LinearGradientBrush volumeHeatmapBrush;

// In OnRenderTargetChanged():
var gradientStops = new SharpDX.Direct2D1.GradientStop[]
{
    new SharpDX.Direct2D1.GradientStop { Position = 0.0f, Color = new Color4(0.180f, 0.259f, 0.518f, 1f) },  // #2E4284 Deep blue (low vol)
    new SharpDX.Direct2D1.GradientStop { Position = 0.33f, Color = new Color4(0f, 0.878f, 1f, 1f) },          // #00E0FF Cyan (moderate)
    new SharpDX.Direct2D1.GradientStop { Position = 0.66f, Color = new Color4(1f, 0.824f, 0.247f, 1f) },      // #FFD23F Yellow (high)
    new SharpDX.Direct2D1.GradientStop { Position = 1.0f, Color = new Color4(1f, 0.090f, 0.267f, 1f) },       // #FF1744 Red (extreme)
};

using (var stopCollection = new SharpDX.Direct2D1.GradientStopCollection(RenderTarget, gradientStops))
{
    volumeHeatmapBrush = new SharpDX.Direct2D1.LinearGradientBrush(
        RenderTarget,
        new SharpDX.Direct2D1.LinearGradientBrushProperties
        {
            StartPoint = new SharpDX.Vector2(cellRect.Left, cellRect.Top),
            EndPoint   = new SharpDX.Vector2(cellRect.Left, cellRect.Bottom)  // Vertical gradient
        },
        stopCollection
    );
}

// For dynamic per-cell heatmap, create a simple SolidColorBrush and interpolate the color:
private Color4 GetHeatmapColor(float normalizedVolume)
{
    // normalizedVolume: 0.0 (min) to 1.0 (max)
    if (normalizedVolume < 0.33f)
    {
        float t = normalizedVolume / 0.33f;
        return Color4.Lerp(new Color4(0.180f, 0.259f, 0.518f, 1f), new Color4(0f, 0.878f, 1f, 1f), t);
    }
    else if (normalizedVolume < 0.66f)
    {
        float t = (normalizedVolume - 0.33f) / 0.33f;
        return Color4.Lerp(new Color4(0f, 0.878f, 1f, 1f), new Color4(1f, 0.824f, 0.247f, 1f), t);
    }
    else
    {
        float t = (normalizedVolume - 0.66f) / 0.34f;
        return Color4.Lerp(new Color4(1f, 0.824f, 0.247f, 1f), new Color4(1f, 0.090f, 0.267f, 1f), t);
    }
}
```

### RadialGradientBrush — Glow Effects

Use sparingly for signal activation indicators, absorption/exhaustion hotspots. **Limit to 3-5 per frame** — radial gradients are expensive.

```csharp
// Glow effect around an absorption signal point
private void DrawGlowEffect(SharpDX.Direct2D1.RenderTarget rt, SharpDX.Vector2 center, float radius, Color4 glowColor)
{
    var gradientStops = new SharpDX.Direct2D1.GradientStop[]
    {
        new SharpDX.Direct2D1.GradientStop { Position = 0.0f, Color = new Color4(glowColor.Red, glowColor.Green, glowColor.Blue, 0.6f) },
        new SharpDX.Direct2D1.GradientStop { Position = 0.5f, Color = new Color4(glowColor.Red, glowColor.Green, glowColor.Blue, 0.2f) },
        new SharpDX.Direct2D1.GradientStop { Position = 1.0f, Color = new Color4(glowColor.Red, glowColor.Green, glowColor.Blue, 0.0f) },
    };

    using (var stopCollection = new SharpDX.Direct2D1.GradientStopCollection(rt, gradientStops))
    using (var radialBrush = new SharpDX.Direct2D1.RadialGradientBrush(
        rt,
        new SharpDX.Direct2D1.RadialGradientBrushProperties
        {
            Center = center,
            RadiusX = radius,
            RadiusY = radius,
            GradientOriginOffset = new SharpDX.Vector2(0, 0)
        },
        stopCollection))
    {
        rt.FillEllipse(new SharpDX.Direct2D1.Ellipse(center, radius, radius), radialBrush);
    }
}
```

### RoundedRectangle — Modern Panels

Use for HUD containers, signal cards, dashboards. RadiusX/Y of 6-8px gives a modern, professional look without being too "rounded".

```csharp
// Panel background with rounded corners
private void DrawPanel(SharpDX.Direct2D1.RenderTarget rt, RectangleF bounds)
{
    var roundedRect = new SharpDX.Direct2D1.RoundedRectangle
    {
        Rect    = new SharpDX.RectangleF(bounds.X, bounds.Y, bounds.X + bounds.Width, bounds.Y + bounds.Height),
        RadiusX = 7f,
        RadiusY = 7f
    };

    // Fill
    rt.FillRoundedRectangle(roundedRect, surfaceBrush);     // #1A1A2E

    // Border (subtle)
    rt.DrawRoundedRectangle(roundedRect, gridBrush, 1f);    // #262C36, 1px
}

// For elevated panels (hover state or active), use a slightly lighter surface:
// Surface elevated: #222240 → new Color4(0.133f, 0.133f, 0.251f, 1f)
```

### PathGeometry — Custom Arrows

For directional indicators (entry arrows, signal direction markers).

```csharp
// Filled triangle arrow pointing up (for Long signals)
private void DrawUpArrow(SharpDX.Direct2D1.RenderTarget rt, float centerX, float topY, float size)
{
    using (var geometry = new SharpDX.Direct2D1.PathGeometry(Core.Globals.D2DFactory))
    {
        using (var sink = geometry.Open())
        {
            sink.BeginFigure(
                new SharpDX.Vector2(centerX, topY),                        // Top point
                SharpDX.Direct2D1.FigureBegin.Filled
            );
            sink.AddLine(new SharpDX.Vector2(centerX + size / 2f, topY + size));  // Bottom right
            sink.AddLine(new SharpDX.Vector2(centerX - size / 2f, topY + size));  // Bottom left
            sink.EndFigure(SharpDX.Direct2D1.FigureEnd.Closed);
            sink.Close();
        }
        rt.FillGeometry(geometry, longBrush);
    }
}

// Down arrow (for Short signals) — invert the Y coordinates
private void DrawDownArrow(SharpDX.Direct2D1.RenderTarget rt, float centerX, float bottomY, float size)
{
    using (var geometry = new SharpDX.Direct2D1.PathGeometry(Core.Globals.D2DFactory))
    {
        using (var sink = geometry.Open())
        {
            sink.BeginFigure(
                new SharpDX.Vector2(centerX, bottomY),                     // Bottom point
                SharpDX.Direct2D1.FigureBegin.Filled
            );
            sink.AddLine(new SharpDX.Vector2(centerX + size / 2f, bottomY - size));  // Top right
            sink.AddLine(new SharpDX.Vector2(centerX - size / 2f, bottomY - size));  // Top left
            sink.EndFigure(SharpDX.Direct2D1.FigureEnd.Closed);
            sink.Close();
        }
        rt.FillGeometry(geometry, shortBrush);
    }
}
```

### StrokeStyle — Dashed Lines

For level markers (VAH, VAL, support/resistance, targets).

```csharp
// Pre-create in OnRenderTargetChanged or OnStateChange(Configure):
private SharpDX.Direct2D1.StrokeStyle dashedStyle;
private SharpDX.Direct2D1.StrokeStyle dashDotStyle;
private SharpDX.Direct2D1.StrokeStyle customDashStyle;

// In OnStateChange(State.Configure) or OnRenderTargetChanged:
// Standard dash
dashedStyle = new SharpDX.Direct2D1.StrokeStyle(
    Core.Globals.D2DFactory,
    new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash }
);

// Dash-dot (for secondary levels)
dashDotStyle = new SharpDX.Direct2D1.StrokeStyle(
    Core.Globals.D2DFactory,
    new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.DashDot }
);

// Custom dash pattern: long dash, short gap, dot, short gap
customDashStyle = new SharpDX.Direct2D1.StrokeStyle(
    Core.Globals.D2DFactory,
    new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Custom },
    new float[] { 6f, 2f, 1f, 2f }   // dash, gap, dash, gap (in stroke-width multiples)
);

// Usage:
// VAH line — olive dashed
RenderTarget.DrawLine(
    new SharpDX.Vector2(x1, vahY),
    new SharpDX.Vector2(x2, vahY),
    vahBrush,       // #C8D17A
    1f,             // stroke width
    dashedStyle     // dashed
);
```

### TextLayout — Text Measurement and Centering

Essential for precise text positioning in cells and panels. `TextLayout` gives you measured width/height before rendering.

```csharp
// Measure text dimensions, then center-align in a cell
private void DrawCenteredText(
    SharpDX.Direct2D1.RenderTarget rt,
    string text,
    SharpDX.DirectWrite.TextFormat format,
    SharpDX.Direct2D1.Brush brush,
    SharpDX.RectangleF bounds)
{
    using (var layout = new SharpDX.DirectWrite.TextLayout(
        Core.Globals.DirectWriteFactory,
        text,
        format,
        bounds.Right - bounds.Left,    // max width
        bounds.Bottom - bounds.Top))   // max height
    {
        var metrics = layout.Metrics;
        float x = bounds.Left + (bounds.Right - bounds.Left - metrics.Width) / 2f;
        float y = bounds.Top + (bounds.Bottom - bounds.Top - metrics.Height) / 2f;
        rt.DrawTextLayout(new SharpDX.Vector2(x, y), layout, brush);
    }
}

// Right-align text (for bid side of footprint)
private void DrawRightAlignedText(
    SharpDX.Direct2D1.RenderTarget rt,
    string text,
    SharpDX.DirectWrite.TextFormat format,
    SharpDX.Direct2D1.Brush brush,
    SharpDX.RectangleF bounds)
{
    using (var layout = new SharpDX.DirectWrite.TextLayout(
        Core.Globals.DirectWriteFactory,
        text,
        format,
        bounds.Right - bounds.Left,
        bounds.Bottom - bounds.Top))
    {
        var metrics = layout.Metrics;
        float x = bounds.Right - metrics.Width - 2f;  // 2px right padding
        float y = bounds.Top + (bounds.Bottom - bounds.Top - metrics.Height) / 2f;
        rt.DrawTextLayout(new SharpDX.Vector2(x, y), layout, brush);
    }
}
```

### Corner Bracket Markers — Extreme Imbalance

For Tier 3 (extreme) imbalance cells, draw corner brackets to create a "targeting" visual.

```csharp
// Draw corner brackets around a cell (top-left, top-right, bottom-left, bottom-right)
private void DrawCornerBrackets(
    SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect,
    SharpDX.Direct2D1.Brush bracketBrush,
    float bracketLength = 6f,
    float strokeWidth = 1.5f)
{
    float l = cellRect.Left;
    float r = cellRect.Right;
    float t = cellRect.Top;
    float b = cellRect.Bottom;

    // Top-left corner
    rt.DrawLine(new SharpDX.Vector2(l, t), new SharpDX.Vector2(l + bracketLength, t), bracketBrush, strokeWidth);
    rt.DrawLine(new SharpDX.Vector2(l, t), new SharpDX.Vector2(l, t + bracketLength), bracketBrush, strokeWidth);

    // Top-right corner
    rt.DrawLine(new SharpDX.Vector2(r, t), new SharpDX.Vector2(r - bracketLength, t), bracketBrush, strokeWidth);
    rt.DrawLine(new SharpDX.Vector2(r, t), new SharpDX.Vector2(r, t + bracketLength), bracketBrush, strokeWidth);

    // Bottom-left corner
    rt.DrawLine(new SharpDX.Vector2(l, b), new SharpDX.Vector2(l + bracketLength, b), bracketBrush, strokeWidth);
    rt.DrawLine(new SharpDX.Vector2(l, b), new SharpDX.Vector2(l, b - bracketLength), bracketBrush, strokeWidth);

    // Bottom-right corner
    rt.DrawLine(new SharpDX.Vector2(r, b), new SharpDX.Vector2(r - bracketLength, b), bracketBrush, strokeWidth);
    rt.DrawLine(new SharpDX.Vector2(r, b), new SharpDX.Vector2(r, b - bracketLength), bracketBrush, strokeWidth);
}
```

### Anti-Aliasing Control

```csharp
// Anti-aliasing modes in OnRender:
// Default is AntialiasMode.PerPrimitive — smooth edges, 2-3x rendering cost

// For filled rectangles (footprint cells), disable AA for crisp pixel boundaries:
RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;
RenderTarget.FillRectangle(cellRect, cellFillBrush);

// Re-enable for borders, lines, and shapes that need smooth edges:
RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.PerPrimitive;
RenderTarget.DrawRoundedRectangle(panelRect, borderBrush, 1f);
RenderTarget.DrawLine(startPoint, endPoint, lineBrush, 1.5f);

// Rule: Aliased for fills (crisp), PerPrimitive for borders/lines/shapes (smooth)
// Never use PerPrimitive for mass cell fills — it's 2-3x slower
```

---

## Section 4: FOOTPRINT CELL RENDERING

### Cell Layout Geometry

Each footprint cell represents one price level within one time bar. The cell is divided into bid (left) and ask (right) halves.

```
Bar N                 Bar N+1
┌───────────────┐    ┌───────────────┐
│  Bid  │  Ask  │    │  Bid  │  Ask  │
│ right │ left  │    │ right │ left  │
│aligned│aligned│    │aligned│aligned│
├───────┼───────┤    ├───────┼───────┤
│   42  │ 87    │ ◄─ POC (yellow line)
├───────┼───────┤    ├───────┼───────┤
│   31  │ 56    │    │       │       │
└───────────────┘    └───────────────┘
```

**Coordinate calculation:**
```csharp
// Per-bar cell positioning
float barCenterX = chartControl.GetXByBarIndex(chartBars, barIndex);
float cellWidth  = chartControl.Properties.BarDistance;  // or custom width
float cellLeft   = barCenterX - cellWidth / 2f;
float cellRight  = barCenterX + cellWidth / 2f;
float midX       = barCenterX;  // Divider between bid and ask

// Per-price-level Y positioning
float cellTop    = chartScale.GetYByValue(price + tickSize / 2.0);
float cellBottom = chartScale.GetYByValue(price - tickSize / 2.0);

// Full cell rectangle
var cellRect = new SharpDX.RectangleF(cellLeft, cellTop, cellWidth, cellBottom - cellTop);

// Bid half (left)
var bidRect = new SharpDX.RectangleF(cellLeft, cellTop, cellWidth / 2f, cellBottom - cellTop);

// Ask half (right)
var askRect = new SharpDX.RectangleF(midX, cellTop, cellWidth / 2f, cellBottom - cellTop);
```

### Text Format — Cell Data

```csharp
// Cell text: "  42 x 87  "
// Bid is right-aligned in left half, Ask is left-aligned in right half
// Use 9pt Consolas monospace for guaranteed columnar alignment

string bidText = bidVolume.ToString().PadLeft(4);   // "  42"
string askText = askVolume.ToString().PadRight(4);  // "87  "
string cellText = $"{bidText} x {askText}";

// Or render bid and ask separately for independent coloring:
// Bid in left half, right-aligned
DrawRightAlignedText(RenderTarget, bidVolume.ToString(), cellTextFormat, bidTextBrush, bidRect);

// "x" separator at center
DrawCenteredText(RenderTarget, "x", cellTextFormat, separatorBrush, cellRect);

// Ask in right half, left-aligned
// (offset left by 2px for padding)
RenderTarget.DrawText(askVolume.ToString(), cellTextFormat,
    new SharpDX.RectangleF(midX + 2f, cellTop, cellWidth / 2f - 4f, cellBottom - cellTop),
    askTextBrush);
```

### 3-Tier Imbalance Coloring

Imbalances use **diagonal comparison**: bid volume at price N vs ask volume at price N+1 (one tick above). This detects aggressive buying/selling pressure.

```
Price Level    Bid    Ask    Diagonal Comparison
─────────────────────────────────────────────────
21,450.25       12     87   ← Ask here (87) vs Bid at 21,450.50 (5)
21,450.50        5     42     Ratio: 87/5 = 17.4x → Tier 3 EXTREME
21,450.75       31     23
```

```csharp
// Diagonal imbalance calculation
float imbalanceRatio = 0f;
bool isBuyImbalance = false;

// Buy imbalance: ask@N vs bid@(N+1)
if (bidVolumeAbove > 0)
{
    float ratio = (float)askVolume / bidVolumeAbove;
    if (ratio > 1.5f)  // Minimum threshold
    {
        imbalanceRatio = ratio;
        isBuyImbalance = true;
    }
}

// Sell imbalance: bid@N vs ask@(N-1)
if (askVolumeBelow > 0)
{
    float ratio = (float)bidVolume / askVolumeBelow;
    if (ratio > 1.5f && ratio > imbalanceRatio)
    {
        imbalanceRatio = ratio;
        isBuyImbalance = false;
    }
}

// Tier assignment
int tier = 0;
if (imbalanceRatio >= 5.0f)      tier = 3;  // Extreme: 500%+
else if (imbalanceRatio >= 3.0f) tier = 2;  // Strong:  300-500%
else if (imbalanceRatio >= 1.5f) tier = 1;  // Mild:    150-300%

// Cell fill based on tier
Color4 fillColor;
switch (tier)
{
    case 1:
        fillColor = isBuyImbalance
            ? new Color4(0f, 0.902f, 0.463f, 0.18f)   // Long green @ 18%
            : new Color4(1f, 0.090f, 0.267f, 0.18f);   // Short red @ 18%
        break;
    case 2:
        fillColor = isBuyImbalance
            ? new Color4(0f, 0.902f, 0.463f, 0.28f)   // Long green @ 28%
            : new Color4(1f, 0.090f, 0.267f, 0.28f);   // Short red @ 28%
        break;
    case 3:
        fillColor = isBuyImbalance
            ? new Color4(0f, 0.902f, 0.463f, 0.40f)   // Long green @ 40%
            : new Color4(1f, 0.090f, 0.267f, 0.40f);   // Short red @ 40%
        // Also draw corner brackets for Tier 3
        DrawCornerBrackets(RenderTarget, cellRect, isBuyImbalance ? longBrush : shortBrush);
        break;
    default:
        fillColor = new Color4(0f, 0f, 0f, 0f);       // Transparent — no imbalance
        break;
}
```

### POC Line (Point of Control)

```csharp
// POC = price level with highest total volume (bid + ask) in the bar
// Draw as a yellow horizontal line spanning the full cell width

float pocY = chartScale.GetYByValue(pocPrice);
RenderTarget.DrawLine(
    new SharpDX.Vector2(cellLeft, pocY),
    new SharpDX.Vector2(cellRight, pocY),
    pocBrush,       // #FFD23F → new Color4(1f, 0.824f, 0.247f, 1f)
    2f              // 2px width — stands out from 1px grid
);
```

### VAH / VAL Lines (Value Area)

```csharp
// VAH/VAL = boundaries of 70% volume concentration
// Draw as olive dashed lines

float vahY = chartScale.GetYByValue(vahPrice);
float valY = chartScale.GetYByValue(valPrice);

RenderTarget.DrawLine(
    new SharpDX.Vector2(cellLeft, vahY),
    new SharpDX.Vector2(cellRight, vahY),
    vahValBrush,    // #C8D17A → new Color4(0.784f, 0.820f, 0.478f, 1f)
    1f,
    dashedStyle
);

RenderTarget.DrawLine(
    new SharpDX.Vector2(cellLeft, valY),
    new SharpDX.Vector2(cellRight, valY),
    vahValBrush,
    1f,
    dashedStyle
);
```

### Zoom-Aware Degradation

As the chart zooms out, cells get smaller. Rendering all text at all zoom levels wastes GPU time and creates visual noise. Degrade gracefully:

| Cell Height (px) | Render Mode | What to Show |
|-------------------|------------|--------------|
| ≥ 40px | **Full text** | `"  42 x 87  "` with bid/ask text, imbalance fill, POC/VAH/VAL |
| 20–40px | **Color only** | Cell fill color (imbalance tier), no text. POC/VAH lines. |
| 8–20px | **Heatmap** | Single color per cell based on volume intensity. No lines. |
| < 8px | **Skip** | Don't render individual cells. Show bar-level summary only. |

```csharp
float cellHeight = cellBottom - cellTop;

if (cellHeight >= 40f)
{
    // Full rendering: fill + text + POC + VAH/VAL
    RenderCellFull(rt, cellRect, bidVol, askVol, tier, isPOC, isVAH, isVAL);
}
else if (cellHeight >= 20f)
{
    // Color-only: fill + POC/VAH lines, no text
    RenderCellColorOnly(rt, cellRect, tier, isPOC);
}
else if (cellHeight >= 8f)
{
    // Heatmap: single color based on normalized volume
    float normalizedVol = (float)(bidVol + askVol) / maxBarVolume;
    using (var heatBrush = new SolidColorBrush(rt, GetHeatmapColor(normalizedVol)))
    {
        rt.FillRectangle(cellRect, heatBrush);
    }
}
// else: skip rendering entirely
```

---

## Section 5: DASHBOARD / HUD PATTERNS

### Right-Side Decision Rail

A fixed 240px panel anchored to the right edge of the chart. Contains the complete trading decision at a glance.

```
┌─────────────────────────────────┐  ← ChartPanel.X + ChartPanel.W - 250
│                                 │
│          L O N G                │  ← Hero 32pt, Consolas Bold, #00E676
│                                 │
│            87                   │  ← Score 20pt, Consolas SemiBold
│                                 │
│  ── TIER 1 ──────────────────  │  ← Tier 14pt, Segoe UI SemiBold, left stripe
│                                 │
│  Entry   21,450.25             │  ← 12pt Consolas
│  Stop    21,438.00             │  ← 12pt Consolas, #FF1744
│  Target  21,474.50             │  ← 12pt Consolas, #00E676
│  R:R     1 : 2.1               │
│                                 │
│  ─── WHY NOW ─────────────────  │
│  • Absorption confirmed (E2)   │  ← 10pt Segoe UI
│  • Exhaustion building (E3)    │
│  • Delta divergence (E5)       │
│  • GEX support at 21,435 (E9) │
│                                 │
│  ▓▓▓▓▓▓▓▓▓▓░░░  87%           │  ← Confidence bar
│                                 │
└─────────────────────────────────┘
```

```csharp
// Decision rail coordinates
float railWidth  = 240f;
float railRight  = ChartPanel.X + ChartPanel.W - 10f;  // 10px margin from edge
float railLeft   = railRight - railWidth;
float railTop    = ChartPanel.Y + 20f;                  // 20px from top

// Panel background
var railRect = new SharpDX.Direct2D1.RoundedRectangle
{
    Rect = new SharpDX.RectangleF(railLeft, railTop, railRight, railTop + 380f),
    RadiusX = 7f,
    RadiusY = 7f
};
RenderTarget.FillRoundedRectangle(railRect, surfaceBrush);
RenderTarget.DrawRoundedRectangle(railRect, gridBrush, 1f);
```

### Five-State Visual System

Every signal display has exactly five visual states. No exceptions.

| State | Visual | Behavior | Color |
|-------|--------|----------|-------|
| **Idle** | Gray panel, dim text | No signal conditions met | `#8A929E` text, `#1A1A2E` bg |
| **Watch** | Amber left stripe, brighter text | Signal building, approaching threshold | `#FFB300` stripe, `#F2F4F8` text |
| **Armed** | Direction-colored left stripe | Signal threshold met, awaiting confirmation | `#00E676` or `#FF1744` stripe |
| **Triggered** | Full panel glow + pulsing | Signal confirmed, trade action imminent | Pulsing opacity 0.8→1.0 at 2Hz |
| **Expired** | Fade to gray over 500ms | Signal timed out or invalidated | Linear alpha fade from current → `#8A929E` |

```csharp
// State-based rendering
private enum SignalState { Idle, Watch, Armed, Triggered, Expired }

private void RenderHUDState(SharpDX.Direct2D1.RenderTarget rt, SignalState state, bool isLong)
{
    SharpDX.Direct2D1.Brush stripeBrush;
    SharpDX.Direct2D1.Brush textBrush;
    float bgAlpha;

    switch (state)
    {
        case SignalState.Idle:
            stripeBrush = neutralBrush;      // #8A929E
            textBrush   = textTertiaryBrush; // #5A636E
            bgAlpha     = 0.6f;
            break;

        case SignalState.Watch:
            stripeBrush = watchBrush;        // #FFB300
            textBrush   = textPrimaryBrush;  // #F2F4F8
            bgAlpha     = 0.85f;
            break;

        case SignalState.Armed:
            stripeBrush = isLong ? longBrush : shortBrush;  // Direction color
            textBrush   = textPrimaryBrush;
            bgAlpha     = 1.0f;
            break;

        case SignalState.Triggered:
            stripeBrush = isLong ? longBrush : shortBrush;
            textBrush   = textPrimaryBrush;
            // Pulse: oscillate alpha between 0.8 and 1.0 at 2Hz
            float pulse = 0.9f + 0.1f * (float)Math.Sin(DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond * 0.0125664);  // 2Hz
            bgAlpha     = pulse;
            break;

        case SignalState.Expired:
            stripeBrush = neutralBrush;
            textBrush   = textSecondaryBrush;  // #9BA3AE
            bgAlpha     = 0.4f;
            break;
    }

    // Draw left stripe (4px wide, full height of panel)
    var stripeRect = new SharpDX.RectangleF(railLeft, railTop, railLeft + 4f, railTop + panelHeight);
    rt.FillRectangle(stripeRect, stripeBrush);
}
```

### Floating HUD Alternative

For indicators that don't need a full rail. Right-aligned, compact, expandable.

```
Armed state (96px height):
┌─────────────────────────┐
│ ▌ LONG  87  21,450.25  │  ← Single line: stripe + action + score + price
│ ▌ SL 21,438  TP 21,474 │  ← Stops + targets
│ ▌ Absorption + Delta    │  ← Key signals
└─────────────────────────┘

Standby state (28px height):
┌─────────────────────────┐
│ ▌ IDLE  ·  no signal    │
└─────────────────────────┘
```

```csharp
// Floating HUD positioning
float hudWidth  = 290f;
float hudRight  = ChartPanel.X + ChartPanel.W - 10f;
float hudLeft   = hudRight - hudWidth;
float hudTop    = ChartPanel.Y + 10f;
float hudHeight = isArmedOrTriggered ? 96f : 28f;  // Expand when active

// Tier stripe on left edge
var stripeRect = new SharpDX.RectangleF(hudLeft, hudTop, hudLeft + 4f, hudTop + hudHeight);
```

### Coordinate System Reference

```csharp
// ChartPanel coordinates (for HUD/dashboard positioning)
float panelLeft   = ChartPanel.X;
float panelTop    = ChartPanel.Y;
float panelWidth  = ChartPanel.W;
float panelHeight = ChartPanel.H;
float panelRight  = ChartPanel.X + ChartPanel.W;
float panelBottom = ChartPanel.Y + ChartPanel.H;

// Price ↔ Y coordinate conversion
float y = chartScale.GetYByValue(price);    // Price → Y pixel
double price = chartScale.GetValueByY(y);   // Y pixel → Price

// Bar index ↔ X coordinate conversion
float x = chartControl.GetXByBarIndex(chartBars, barIndex);   // Bar → X pixel
int barIndex = chartControl.GetBarIndexByX(chartBars, (int)x); // X pixel → Bar

// Visible bar range
int firstVisibleBar = chartControl.GetSlotIndexByX(ChartPanel.X);
int lastVisibleBar  = chartControl.GetSlotIndexByX(ChartPanel.X + ChartPanel.W);
```

---

## Section 6: PERFORMANCE RULES

### 8Hz Render Throttle

NinjaTrader's chart rendering can fire at 60Hz+ during volatile markets. Your `OnRender()` must not do expensive work every frame.

```csharp
private DateTime lastRenderTime = DateTime.MinValue;
private const int RENDER_INTERVAL_MS = 125;  // 8Hz = 125ms

protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    base.OnRender(chartControl, chartScale);

    // Throttle to 8Hz
    var now = DateTime.Now;
    if ((now - lastRenderTime).TotalMilliseconds < RENDER_INTERVAL_MS)
        return;
    lastRenderTime = now;

    // Actual rendering below...
}
```

### Resource Lifecycle Table

| Resource Type | Create Where | Dispose Where | Notes |
|---------------|-------------|---------------|-------|
| `SolidColorBrush` | `OnRenderTargetChanged()` | `OnRenderTargetChanged()` (dispose old first) + `OnStateChange(Terminated)` | Tied to RenderTarget |
| `LinearGradientBrush` | `OnRenderTargetChanged()` | `OnRenderTargetChanged()` + `OnStateChange(Terminated)` | Tied to RenderTarget |
| `RadialGradientBrush` | `OnRender()` (inside `using`) | End of `using` block | Too expensive to cache; create per-use |
| `TextFormat` | `OnStateChange(Configure)` | `OnStateChange(Terminated)` | NOT tied to RenderTarget — stable across RT changes |
| `TextLayout` | `OnRender()` (inside `using`) | End of `using` block | Must be recreated when text changes |
| `StrokeStyle` | `OnStateChange(Configure)` | `OnStateChange(Terminated)` | Factory resource, not RT-dependent |
| `PathGeometry` | `OnRender()` (inside `using`) | End of `using` block | Recreate each frame (geometry is cheap) |
| `GradientStopCollection` | Inside `using` when creating gradient brush | End of `using` block | Intermediate object |

### Performance Budget

| Metric | Budget | Action if Exceeded |
|--------|--------|-------------------|
| Total `OnRender()` time | < 12ms per frame | Profile with Stopwatch; disable lowest-priority elements first |
| Max footprint cells | 1,200 (30 bars × 40 levels) | Clip to visible range; skip off-screen cells |
| Max brushes | ~30 persistent | Consolidate similar colors; use alpha variants of same brush |
| Max text layouts per frame | ~50 | Cache static text; skip text at small zoom levels |
| Glow effects (radial gradients) | ≤ 5 per frame | Only for triggered/active signals |
| Anti-aliased draw calls | Minimize | Use Aliased mode for fills; PerPrimitive only for borders |

```csharp
// Performance monitoring in OnRender:
#if DEBUG
private System.Diagnostics.Stopwatch renderWatch = new System.Diagnostics.Stopwatch();

protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
{
    renderWatch.Restart();

    // ... all rendering code ...

    renderWatch.Stop();
    if (renderWatch.ElapsedMilliseconds > 12)
    {
        Print($"[PERF WARNING] OnRender took {renderWatch.ElapsedMilliseconds}ms (budget: 12ms)");
    }
}
#endif
```

### Safe Disposal Pattern

```csharp
// Complete disposal in OnStateChange(Terminated):
protected override void OnStateChange()
{
    if (State == State.SetDefaults)
    {
        // ...
    }
    else if (State == State.Configure)
    {
        // Create TextFormats and StrokeStyles here
    }
    else if (State == State.Terminated)
    {
        // Dispose ALL resources — brushes, formats, styles
        try
        {
            SafeDispose(ref longBrush);
            SafeDispose(ref shortBrush);
            SafeDispose(ref absorptionBrush);
            SafeDispose(ref absorptionFillBrush);
            SafeDispose(ref exhaustionBrush);
            SafeDispose(ref exhaustionFillBrush);
            SafeDispose(ref surfaceBrush);
            SafeDispose(ref gridBrush);
            SafeDispose(ref textPrimaryBrush);
            SafeDispose(ref textSecondaryBrush);
            SafeDispose(ref textTertiaryBrush);
            SafeDispose(ref pocBrush);
            SafeDispose(ref vahValBrush);
            SafeDispose(ref watchBrush);
            SafeDispose(ref neutralBrush);

            SafeDispose(ref cellTextFormat);
            SafeDispose(ref labelTextFormat);
            SafeDispose(ref heroTextFormat);
            SafeDispose(ref scoreTextFormat);
            SafeDispose(ref tierTextFormat);
            SafeDispose(ref entryStopTextFormat);

            SafeDispose(ref dashedStyle);
            SafeDispose(ref dashDotStyle);
            SafeDispose(ref customDashStyle);

            SafeDispose(ref volumeHeatmapBrush);
        }
        catch (Exception ex)
        {
            Print($"[DISPOSE ERROR] {ex.Message}");
        }
    }
}
```

---

## Section 7: INSTITUTIONAL DESIGN PRINCIPLES

Ten rules that govern all DEEP6 visual decisions. Memorize these — they override personal aesthetic preference.

### Rule 1: Contrast Over Decoration
Never add a visual element for aesthetics. Every pixel must encode information or improve readability. If removing an element doesn't reduce information content, remove it.

### Rule 2: Density Is a Feature
Professional traders need maximum information density. Bloomberg Terminal shows 400+ data points per screen. Don't fear dense displays — fear sparse ones that hide critical data behind clicks or scrolls. But density ≠ clutter: use alignment, grouping, and whitespace as organizing tools.

### Rule 3: Consistency Over Innovation
Once you establish a visual pattern (e.g., "green = long, red = short"), never break it. A trader's eye builds muscle memory for spatial-chromatic patterns. Inconsistency causes cognitive friction and trading errors. If Signal A uses a left stripe for tier indication, all signals must use left stripes.

### Rule 4: Performance Over Beauty
A 30ms frame is worse than an ugly 5ms frame. The market doesn't wait for your gradient to render. Drop the gradient, keep the alpha fill. Always benchmark before shipping visual features. If an effect puts you over 12ms, it doesn't ship.

### Rule 5: Monospace for Money
All financial data (prices, volumes, deltas, ratios, scores) must be in Consolas monospace. Proportional fonts cause layout shifts when digits change, creating distracting jitter during live trading. The "1" must be the same width as the "8".

### Rule 6: Color as Information
Color is not decoration — it's a data channel. Every color in the palette has a defined semantic meaning (see Section 1). Never use a semantic color for a non-semantic purpose. Don't use `#00E676` (Long green) for a decorative border. Don't use `#FF1744` (Short red) for an error message.

### Rule 7: Spatial Consistency
Elements must appear in the same position every time. The decision rail is always right-aligned. The score is always below the action word. Entry is always above stop. Target is always below stop. If a trader looks at position (X, Y) expecting to see the confidence score, it must be there.

### Rule 8: Calm When Idle
When there's no signal, the display should be calm — gray, low-contrast, unobtrusive. Idle state should not compete for attention with active signals. A trader scanning 4 charts should be able to instantly identify which chart has an active signal by its brightness alone.

### Rule 9: Unmissable When Active
When a signal triggers, it must be impossible to miss. Use:
- Brightness jump (gray → full-saturation color)
- Size expansion (28px standby → 96px armed)
- Motion (pulsing at 2Hz for triggered state)
- Color saturation (muted → vivid)
But always provide an off-ramp (expired state) — don't let active visuals persist after the signal is no longer valid.

### Rule 10: Bloomberg Flash-Fade Pattern
The gold standard for data updates in trading terminals:
1. **Flash** (150ms): New value appears with a bright highlight behind it (slightly brighter version of the semantic color, or a subtle background flash)
2. **Fade** (150ms): Highlight fades back to the normal background
3. Total animation: 300ms. Anything longer is distracting. Anything shorter is imperceptible.

```csharp
// Flash-fade implementation
private DateTime flashStartTime;
private bool isFlashing;

private void TriggerFlash()
{
    flashStartTime = DateTime.Now;
    isFlashing = true;
}

private float GetFlashAlpha()
{
    if (!isFlashing) return 0f;

    double elapsedMs = (DateTime.Now - flashStartTime).TotalMilliseconds;
    if (elapsedMs > 300)
    {
        isFlashing = false;
        return 0f;
    }

    if (elapsedMs < 150)
    {
        // Flash phase: ramp up
        return (float)(elapsedMs / 150.0) * 0.4f;  // Max flash alpha: 0.4
    }
    else
    {
        // Fade phase: ramp down
        return (float)(1.0 - (elapsedMs - 150.0) / 150.0) * 0.4f;
    }
}

// In OnRender, draw flash overlay:
float flashAlpha = GetFlashAlpha();
if (flashAlpha > 0.01f)
{
    using (var flashBrush = new SolidColorBrush(RenderTarget, new Color4(1f, 1f, 1f, flashAlpha)))
    {
        RenderTarget.FillRectangle(valueRect, flashBrush);
    }
}
```

---

## Section 8: PROVEN DEEP6 CODEBASE PATTERNS

### Files to Study

These existing DEEP6 files contain proven visual patterns. Reference them when building new indicators.

| File | Key Pattern | What to Learn |
|------|-------------|---------------|
| `DEEP6Footprint.cs` | Cell rendering | Complete footprint cell layout, bid/ask text positioning, imbalance coloring, POC/VAH/VAL rendering |
| `DEEP6Signal.cs` | HUD / dashboard | Decision rail layout, state-based color switching, score display, signal list rendering |
| `DEEP6FootprintV7.cs` | Clean state management | Well-structured state machine, render throttling, zoom-aware degradation |
| `DEEP6BiasV3.cs` | JSON-driven HUD | Dynamic HUD content from deserialized JSON, flexible label/value pairs, data-driven layout |

### State-Based Brush Selection Pattern

Instead of if/else chains for color selection, use a dictionary or switch on an enum. This pattern appears throughout the DEEP6 codebase.

```csharp
// Define the state enum
public enum ConfidenceTier
{
    None,       // 0-25: No signal
    Low,        // 25-50: Weak signal
    Medium,     // 50-75: Moderate signal
    High,       // 75-90: Strong signal
    Extreme     // 90-100: Maximum confidence
}

// Map state → brush (populated in OnRenderTargetChanged)
private Dictionary<ConfidenceTier, SharpDX.Direct2D1.Brush> tierBrushes;

// In OnRenderTargetChanged():
tierBrushes = new Dictionary<ConfidenceTier, SharpDX.Direct2D1.Brush>
{
    { ConfidenceTier.None,    new SolidColorBrush(RenderTarget, new Color4(0.541f, 0.573f, 0.620f, 1f)) },   // #8A929E Neutral
    { ConfidenceTier.Low,     new SolidColorBrush(RenderTarget, new Color4(0.541f, 0.573f, 0.620f, 0.7f)) }, // Neutral dimmed
    { ConfidenceTier.Medium,  new SolidColorBrush(RenderTarget, new Color4(1f, 0.702f, 0f, 1f)) },           // #FFB300 Watch
    { ConfidenceTier.High,    new SolidColorBrush(RenderTarget, new Color4(0f, 0.902f, 0.463f, 1f)) },       // #00E676 Long green
    { ConfidenceTier.Extreme, new SolidColorBrush(RenderTarget, new Color4(0f, 0.878f, 1f, 1f)) },           // #00E0FF Absorption cyan
};

// In OnRender — clean, no if/else:
var brush = tierBrushes[currentTier];
RenderTarget.FillRectangle(scoreRect, brush);

// Disposal in OnRenderTargetChanged (before recreation) and Terminated:
if (tierBrushes != null)
{
    foreach (var kvp in tierBrushes)
        kvp.Value?.Dispose();
    tierBrushes.Clear();
}
```

### Tier-Based Color Coding Pattern

A generalized pattern for any multi-level indicator (imbalance strength, volume percentile, signal confidence).

```csharp
// Tier definition struct
public struct TierDefinition
{
    public float Threshold;       // Minimum value for this tier
    public Color4 FillColor;      // Background fill
    public Color4 TextColor;      // Text color
    public Color4 BorderColor;    // Border color (if applicable)
    public float BorderWidth;     // 0 = no border
    public bool ShowBrackets;     // Draw corner brackets
    public string Label;          // Optional label ("MILD", "STRONG", "EXTREME")
}

// Tier configuration (customize per indicator)
private static readonly TierDefinition[] ImbalanceTiers = new[]
{
    new TierDefinition   // Tier 0: No imbalance
    {
        Threshold = 0f,
        FillColor = new Color4(0f, 0f, 0f, 0f),          // Transparent
        TextColor = new Color4(0.608f, 0.639f, 0.682f, 1f), // #9BA3AE
        BorderColor = new Color4(0f, 0f, 0f, 0f),
        BorderWidth = 0f,
        ShowBrackets = false,
        Label = ""
    },
    new TierDefinition   // Tier 1: Mild (150-300%)
    {
        Threshold = 1.5f,
        FillColor = new Color4(0f, 0.902f, 0.463f, 0.18f),  // Green @ 18%
        TextColor = new Color4(0.949f, 0.957f, 0.973f, 1f),  // #F2F4F8
        BorderColor = new Color4(0f, 0f, 0f, 0f),
        BorderWidth = 0f,
        ShowBrackets = false,
        Label = "MILD"
    },
    new TierDefinition   // Tier 2: Strong (300-500%)
    {
        Threshold = 3.0f,
        FillColor = new Color4(0f, 0.902f, 0.463f, 0.28f),  // Green @ 28%
        TextColor = new Color4(0.949f, 0.957f, 0.973f, 1f),
        BorderColor = new Color4(0f, 0.902f, 0.463f, 0.5f),  // Green @ 50% border
        BorderWidth = 1f,
        ShowBrackets = false,
        Label = "STRONG"
    },
    new TierDefinition   // Tier 3: Extreme (500%+)
    {
        Threshold = 5.0f,
        FillColor = new Color4(0f, 0.902f, 0.463f, 0.40f),  // Green @ 40%
        TextColor = new Color4(0.949f, 0.957f, 0.973f, 1f),
        BorderColor = new Color4(0f, 0.902f, 0.463f, 0.8f),  // Green @ 80% border
        BorderWidth = 1.5f,
        ShowBrackets = true,
        Label = "EXTREME"
    }
};

// Tier lookup (iterate from highest threshold down)
private TierDefinition GetTier(float value)
{
    for (int i = ImbalanceTiers.Length - 1; i >= 0; i--)
    {
        if (value >= ImbalanceTiers[i].Threshold)
            return ImbalanceTiers[i];
    }
    return ImbalanceTiers[0];
}

// Usage in OnRender:
var tier = GetTier(imbalanceRatio);

// Apply fill
using (var fillBrush = new SolidColorBrush(RenderTarget, tier.FillColor))
    RenderTarget.FillRectangle(cellRect, fillBrush);

// Apply border if defined
if (tier.BorderWidth > 0f)
{
    using (var borderBrush = new SolidColorBrush(RenderTarget, tier.BorderColor))
        RenderTarget.DrawRectangle(cellRect, borderBrush, tier.BorderWidth);
}

// Apply corner brackets if extreme
if (tier.ShowBrackets)
{
    using (var bracketBrush = new SolidColorBrush(RenderTarget, tier.BorderColor))
        DrawCornerBrackets(RenderTarget, cellRect, bracketBrush);
}
```

---

## Quick Reference Card

```
COLORS (Institutional Dark)
  Background   #0E1014    Surface      #1A1A2E    Grid        #262C36
  Text Primary #F2F4F8    Text Second  #9BA3AE    Text Third  #5A636E
  Long/Buy     #00E676    Short/Sell   #FF1744    Watch       #FFB300
  Neutral      #8A929E    Absorption   #00E0FF    Exhaustion  #FF38C8
  POC          #FFD23F    VAH/VAL      #C8D17A

FONTS
  Data:   Consolas 9-32pt (monospace, tabular numerals)
  Labels: Segoe UI 8-14pt (humanist sans-serif)
  Glyphs: Segoe UI Symbol (▲▼●◆)

PERFORMANCE
  Render:  8Hz max (125ms throttle)
  Budget:  <12ms per frame
  Cells:   Max 1,200 (30 bars × 40 levels)
  Glows:   Max 5 per frame

IMBALANCE TIERS (diagonal comparison)
  Tier 1  150-300%  18% alpha fill
  Tier 2  300-500%  28% alpha fill
  Tier 3  500%+     40% alpha fill + corner brackets

STATES
  Idle → Watch → Armed → Triggered → Expired
  Gray → Amber → Color → Pulsing   → Fade
```

---

## Section 10: ADVANCED SHARPDX API REFERENCE

### RenderTarget Drawing Methods — Complete Table

Every draw call available on `SharpDX.Direct2D1.RenderTarget`. These are your atomic primitives — all DEEP6 visuals decompose into combinations of these calls.

| Method | Signature | Cost | When to Use |
|--------|-----------|------|-------------|
| `DrawLine` | `(Vector2 p0, Vector2 p1, Brush, float strokeWidth, StrokeStyle?)` | Low | Grid lines, POC/VAH/VAL levels, connectors, separators |
| `DrawRectangle` | `(RectangleF, Brush, float strokeWidth, StrokeStyle?)` | Low | Cell borders, panel outlines, selection rectangles |
| `FillRectangle` | `(RectangleF, Brush)` | Low | Cell fills, backgrounds, heatmap cells, bars |
| `DrawRoundedRectangle` | `(RoundedRectangle, Brush, float strokeWidth, StrokeStyle?)` | Medium | HUD panel borders, card outlines, modern UI containers |
| `FillRoundedRectangle` | `(RoundedRectangle, Brush)` | Medium | HUD panel fills, tooltip backgrounds, signal cards |
| `DrawEllipse` | `(Ellipse, Brush, float strokeWidth, StrokeStyle?)` | Medium | Signal dots (outline), status indicators, circular markers |
| `FillEllipse` | `(Ellipse, Brush)` | Medium | Signal dots (filled), trade markers, glow center points |
| `DrawGeometry` | `(Geometry, Brush, float strokeWidth, StrokeStyle?)` | High | Custom arrow outlines, complex shapes, bracket connectors |
| `FillGeometry` | `(Geometry, Brush)` | High | Filled arrows, custom polygons, irregular shapes |
| `DrawBitmap` | `(Bitmap, RectangleF?, float opacity, BitmapInterpolationMode, RectangleF?)` | Medium | Cached textures, pre-rendered elements, icon overlays |
| `DrawText` | `(string, TextFormat, RectangleF, Brush, DrawTextOptions, MeasuringMode)` | Medium | Simple text without measurement — fast but no precise centering |
| `DrawTextLayout` | `(Vector2 origin, TextLayout, Brush, DrawTextOptions)` | Medium | Measured/centered text — use when precise positioning matters |
| `Clear` | `(Color4?)` | Low | Reset entire render target to a color — use at start of full-panel render |

### The Five Brush Types

Brushes define how shapes are painted. All brushes are GPU resources tied to a `RenderTarget`.

```csharp
// 1. SolidColorBrush — 95% of your usage. Flat color + alpha.
var solidBrush = new SharpDX.Direct2D1.SolidColorBrush(
    RenderTarget,
    new Color4(0f, 0.902f, 0.463f, 1f)  // #00E676 fully opaque
);
// Dynamic opacity: solidBrush.Opacity = 0.5f; (cheaper than creating new brush)

// 2. LinearGradientBrush — Volume heatmaps, progress bars, signal strength.
// See Section 3 for full creation pattern with GradientStopCollection.
// Key: StartPoint + EndPoint define gradient axis. Stops define color transitions.
// Performance: ~2x cost of SolidColorBrush. Cache when possible.

// 3. RadialGradientBrush — Glow effects, hotspot indicators.
// See Section 3 for full creation pattern.
// Key: Center + RadiusX/Y define falloff. GradientOriginOffset shifts highlight.
// Performance: ~3-4x cost of SolidColorBrush. ALWAYS create inside using() blocks.

// 4. BitmapBrush — Tiling patterns, texture fills (rare in trading UI).
var bitmapBrush = new SharpDX.Direct2D1.BitmapBrush(
    RenderTarget,
    cachedBitmap,
    new SharpDX.Direct2D1.BitmapBrushProperties
    {
        ExtendModeX = SharpDX.Direct2D1.ExtendMode.Wrap,
        ExtendModeY = SharpDX.Direct2D1.ExtendMode.Wrap,
        InterpolationMode = SharpDX.Direct2D1.BitmapInterpolationMode.Linear
    }
);

// 5. ImageBrush (ID2D1DeviceContext only) — Same as BitmapBrush but for ID2D1Image.
// Requires casting RenderTarget to DeviceContext. Use only for advanced effects pipeline.
// Not recommended for NT8 indicators — stick with SolidColor + LinearGradient.
```

### PathGeometry and GeometrySink — Custom Shapes

`PathGeometry` is how you draw anything that isn't a rectangle, ellipse, or line. The `GeometrySink` API follows a cursor model: move to a point, then draw lines/arcs/beziers from there.

```csharp
// Complete PathGeometry example: Diamond shape with arc top
private void DrawDiamondSignal(
    SharpDX.Direct2D1.RenderTarget rt,
    float centerX, float centerY,
    float size,
    SharpDX.Direct2D1.Brush fillBrush,
    SharpDX.Direct2D1.Brush borderBrush)
{
    float half = size / 2f;

    using (var geometry = new SharpDX.Direct2D1.PathGeometry(Core.Globals.D2DFactory))
    {
        using (var sink = geometry.Open())
        {
            // BeginFigure: starting point + whether filled or hollow
            sink.BeginFigure(
                new SharpDX.Vector2(centerX, centerY - half),  // Top vertex
                SharpDX.Direct2D1.FigureBegin.Filled
            );

            // AddLine: straight line segment to next point
            sink.AddLine(new SharpDX.Vector2(centerX + half, centerY));    // Right vertex

            // AddArc: curved segment (sweep direction, arc size)
            sink.AddArc(new SharpDX.Direct2D1.ArcSegment
            {
                Point = new SharpDX.Vector2(centerX, centerY + half),      // Bottom vertex
                Size = new SharpDX.Size2F(half * 1.2f, half * 0.8f),       // Elliptical arc radii
                RotationAngle = 0f,
                SweepDirection = SharpDX.Direct2D1.SweepDirection.Clockwise,
                ArcSize = SharpDX.Direct2D1.ArcSize.Small
            });

            // AddBezier: cubic bezier curve (two control points + endpoint)
            sink.AddBezier(new SharpDX.Direct2D1.BezierSegment
            {
                Point1 = new SharpDX.Vector2(centerX - half * 0.6f, centerY + half * 0.5f),  // Control 1
                Point2 = new SharpDX.Vector2(centerX - half * 0.8f, centerY - half * 0.3f),  // Control 2
                Point3 = new SharpDX.Vector2(centerX, centerY - half)                         // End (back to top)
            });

            // EndFigure: Closed = connect last point back to first; Open = leave open
            sink.EndFigure(SharpDX.Direct2D1.FigureEnd.Closed);
            sink.Close();
        }

        // Fill the shape
        rt.FillGeometry(geometry, fillBrush);
        // Draw the outline
        rt.DrawGeometry(geometry, borderBrush, 1.5f);
    }
}

// GeometrySink method summary:
// BeginFigure(Vector2, FigureBegin.Filled|Hollow)  — start a sub-path
// AddLine(Vector2)                                   — straight line to point
// AddLines(Vector2[])                                — multiple connected lines
// AddArc(ArcSegment)                                 — elliptical arc
// AddBezier(BezierSegment)                           — cubic bezier (2 control + 1 end)
// AddQuadraticBezier(QuadraticBezierSegment)         — quadratic bezier (1 control + 1 end)
// AddQuadraticBeziers(QuadraticBezierSegment[])      — multiple connected quad beziers
// EndFigure(FigureEnd.Closed|Open)                   — close the sub-path
// Close()                                            — finalize the geometry (MUST call)
```

### Layer Operations — Clipping and Opacity Masking

Layers let you apply clipping regions or group opacity to a set of draw calls. Essential for panels that overflow their bounds or for fade effects across multiple elements.

```csharp
// PushAxisAlignedClip — Simple rectangular clipping (fast)
// Use for: panel content that shouldn't render outside panel bounds
var clipRect = new SharpDX.RectangleF(panelLeft, panelTop, panelRight, panelBottom);
RenderTarget.PushAxisAlignedClip(clipRect, SharpDX.Direct2D1.AntialiasMode.PerPrimitive);

// ... draw anything here — it will be clipped to clipRect ...
RenderTarget.DrawText(longText, textFormat, oversizedRect, textBrush);  // Won't bleed outside

RenderTarget.PopAxisAlignedClip();  // MUST pair with Push

// PushLayer — Advanced: opacity mask, geometric clip, group opacity
// Use for: fading an entire group of elements, non-rectangular clip regions
using (var layerParams = new SharpDX.Direct2D1.LayerParameters
{
    ContentBounds = new SharpDX.RectangleF(panelLeft, panelTop, panelRight, panelBottom),
    Opacity = 0.7f,   // Entire layer at 70% opacity
    // GeometricMask = somePathGeometry,  // Optional: non-rectangular clip
    // MaskTransform = Matrix3x2.Identity
})
using (var layer = new SharpDX.Direct2D1.Layer(RenderTarget))
{
    RenderTarget.PushLayer(layerParams, layer);

    // Everything drawn here gets 70% group opacity
    RenderTarget.FillRectangle(bgRect, surfaceBrush);
    RenderTarget.DrawText("FADED", textFormat, labelRect, textBrush);

    RenderTarget.PopLayer();  // MUST pair with PushLayer
}
// Warning: Layers allocate GPU memory. Max 2-3 active layers per frame in NT8.
```

### Matrix3x2 Transforms

Apply rotation, scaling, skew, or translation to all subsequent draw calls. Useful for rotated text labels, scaled elements, or animated transitions.

```csharp
// Save current transform
var originalTransform = RenderTarget.Transform;

// Rotate text 90° counter-clockwise around a pivot point
float pivotX = labelCenterX;
float pivotY = labelCenterY;
RenderTarget.Transform =
    Matrix3x2.Rotation((float)(-Math.PI / 2), new Vector2(pivotX, pivotY));

RenderTarget.DrawText("VOLUME", labelFormat, labelRect, textSecondaryBrush);

// Restore original transform — ALWAYS do this
RenderTarget.Transform = originalTransform;

// Common transforms:
// Matrix3x2.Rotation(radians, center)            — rotate around point
// Matrix3x2.Scaling(scaleX, scaleY, center)      — scale from center
// Matrix3x2.Translation(dx, dy)                  — shift position
// Matrix3x2.Skew(angleX, angleY, center)         — perspective-like distortion
// Combine: transform1 * transform2               — compose transforms (applied right-to-left)
```

### StrokeStyle — Complete Reference

```csharp
// Full StrokeStyle with all properties
var fullStyle = new SharpDX.Direct2D1.StrokeStyle(
    Core.Globals.D2DFactory,
    new SharpDX.Direct2D1.StrokeStyleProperties
    {
        StartCap  = SharpDX.Direct2D1.CapStyle.Round,    // Round, Flat, Square, Triangle
        EndCap    = SharpDX.Direct2D1.CapStyle.Round,     // Affects line endpoints
        DashCap   = SharpDX.Direct2D1.CapStyle.Round,     // Affects each dash end
        LineJoin  = SharpDX.Direct2D1.LineJoin.Round,      // Round, Bevel, Miter, MiterOrBevel
        MiterLimit = 10f,                                   // Max miter extension before bevel
        DashStyle = SharpDX.Direct2D1.DashStyle.Custom,    // Dash, Dot, DashDot, DashDotDot, Custom
        DashOffset = 0f                                     // Phase offset for animated dashes
    },
    new float[] { 4f, 2f, 1f, 2f }  // Custom dash pattern: dash(4), gap(2), dot(1), gap(2)
);

// Animated dashed line (marching ants effect):
// Increment DashOffset each frame — but StrokeStyle is immutable, so recreate:
private float dashPhase = 0f;

// In OnRender (throttled):
dashPhase += 0.5f;  // Speed of march
if (dashPhase > 20f) dashPhase = 0f;

using (var marchingStyle = new SharpDX.Direct2D1.StrokeStyle(
    Core.Globals.D2DFactory,
    new SharpDX.Direct2D1.StrokeStyleProperties
    {
        DashStyle = SharpDX.Direct2D1.DashStyle.Dash,
        DashOffset = dashPhase
    }))
{
    RenderTarget.DrawRectangle(selectionRect, highlightBrush, 1.5f, marchingStyle);
}
```

### Built-In Effects (43 Total) — Reference Table

Effects require casting `RenderTarget` to `SharpDX.Direct2D1.DeviceContext`. In NT8, this cast may fail on older GPU drivers. **Use effects sparingly — they are powerful but risky in the NT8 runtime.**

| Category | Effects | Performance Impact |
|----------|---------|-------------------|
| **Blur** | GaussianBlur, DirectionalBlur, Shadow, Morphology | High — GPU shader per pixel |
| **Color** | ColorMatrix, Saturation, HueRotation, Brightness, Contrast, Gamma, Tint, Exposure, Grayscale, Invert, Sepia, TemperatureAndTint, Vignette | Low-Medium — per-pixel color math |
| **Compositing** | Blend (26 modes), Composite (13 modes), ArithmeticComposite, CrossFade, Opacity | Low — compositing is GPU-native |
| **Transform** | 2DAffineTransform, 3DPerspectiveTransform, 3DTransform, Scale, Border, Crop, Tile, Atlas | Medium — resampling cost |
| **Lighting** | PointSpecular, PointDiffuse, SpotSpecular, SpotDiffuse, DistantSpecular, DistantDiffuse | High — per-pixel lighting math |
| **Convolution** | ConvolveMatrix, EdgeDetection, Emboss, Sharpen | High — kernel convolution |
| **Other** | DisplacementMap, Turbulence, Flood, LinearTransfer, GammaTransfer, TableTransfer, DiscreteTransfer, DpiCompensation, Histogram, ColorManagement | Varies |

```csharp
// Example: Gaussian blur on a bitmap (for frosted glass panel background)
// WARNING: Only attempt if you verify DeviceContext cast works on target machine
var deviceContext = RenderTarget as SharpDX.Direct2D1.DeviceContext;
if (deviceContext != null)
{
    using (var blurEffect = new SharpDX.Direct2D1.Effects.GaussianBlur(deviceContext))
    {
        blurEffect.SetInput(0, sourceBitmap, true);
        blurEffect.StandardDeviation = 4.0f;  // Blur radius in pixels
        blurEffect.BorderMode = SharpDX.Direct2D1.BorderMode.Soft;
        deviceContext.DrawImage(blurEffect);
    }
}
// Rule: If DeviceContext cast returns null, fall back to opaque panel background.
// Never let an effect failure crash your indicator.
```

---

## Section 11: INTERACTIVE UI PATTERNS

### TraderButton — Clickable Toggle Component

A reusable button class for on-chart toggles (show/hide layers, switch modes, enable/disable features). Buttons must have generous hit targets (minimum 32×24px) because traders click fast during live markets.

```csharp
// TraderButton: a self-contained clickable element for SharpDX rendering
public class TraderButton
{
    public string Label { get; set; }
    public RectangleF Bounds { get; set; }
    public Func<bool> Get { get; set; }        // Read current state
    public Action<bool> Set { get; set; }      // Write new state
    public bool IsHovered { get; set; }

    // Minimum size constants
    public const float MinWidth = 48f;
    public const float MinHeight = 28f;
    public const float Padding = 6f;
    public const float CornerRadius = 4f;

    public bool IsActive => Get?.Invoke() ?? false;

    public void Toggle()
    {
        bool current = Get?.Invoke() ?? false;
        Set?.Invoke(!current);
    }

    public bool HitTest(float x, float y)
    {
        return x >= Bounds.Left && x <= Bounds.Right &&
               y >= Bounds.Top && y <= Bounds.Bottom;
    }
}

// Button factory — create a row of toggle buttons
private List<TraderButton> CreateButtonRow(float startX, float startY)
{
    var buttons = new List<TraderButton>();
    float currentX = startX;

    buttons.Add(new TraderButton
    {
        Label = "FP",       // Footprint layer
        Get = () => ShowFootprint,
        Set = (v) => { ShowFootprint = v; ForceRefresh(); },
        Bounds = new RectangleF(currentX, startY, 48f, 28f)
    });
    currentX += 52f;  // 48 width + 4 gap

    buttons.Add(new TraderButton
    {
        Label = "IMB",      // Imbalances
        Get = () => ShowImbalances,
        Set = (v) => { ShowImbalances = v; ForceRefresh(); },
        Bounds = new RectangleF(currentX, startY, 48f, 28f)
    });
    currentX += 52f;

    buttons.Add(new TraderButton
    {
        Label = "HUD",      // Decision HUD
        Get = () => ShowHUD,
        Set = (v) => { ShowHUD = v; ForceRefresh(); },
        Bounds = new RectangleF(currentX, startY, 48f, 28f)
    });

    return buttons;
}
```

### Mouse Event Handling — Click and Hover Detection

NinjaTrader exposes mouse events through `ChartControl`. You must subscribe in `OnStateChange(DataLoaded)` and unsubscribe in `OnStateChange(Terminated)`.

```csharp
// Subscribe to mouse events
protected override void OnStateChange()
{
    if (State == State.DataLoaded)
    {
        if (ChartControl != null)
        {
            ChartControl.MouseDown  += OnChartMouseDown;
            ChartControl.MouseMove  += OnChartMouseMove;
            ChartControl.MouseLeave += OnChartMouseLeave;
        }
    }
    else if (State == State.Terminated)
    {
        if (ChartControl != null)
        {
            ChartControl.MouseDown  -= OnChartMouseDown;
            ChartControl.MouseMove  -= OnChartMouseMove;
            ChartControl.MouseLeave -= OnChartMouseLeave;
        }
    }
}

// Mouse down handler — button click detection
private void OnChartMouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
{
    if (e.ChangedButton != System.Windows.Input.MouseButton.Left) return;

    // Get position relative to chart panel
    var pos = e.GetPosition(ChartControl as System.Windows.IInputElement);
    float mx = (float)pos.X;
    float my = (float)pos.Y;

    // AABB hit-test against all buttons
    foreach (var button in traderButtons)
    {
        if (button.HitTest(mx, my))
        {
            button.Toggle();
            e.Handled = true;    // Prevent chart from processing this click
            ForceRefresh();      // Request re-render
            return;
        }
    }
}

// Mouse move handler — hover state for visual feedback
private void OnChartMouseMove(object sender, System.Windows.Input.MouseEventArgs e)
{
    var pos = e.GetPosition(ChartControl as System.Windows.IInputElement);
    float mx = (float)pos.X;
    float my = (float)pos.Y;

    bool anyChanged = false;
    foreach (var button in traderButtons)
    {
        bool wasHovered = button.IsHovered;
        button.IsHovered = button.HitTest(mx, my);
        if (wasHovered != button.IsHovered) anyChanged = true;
    }
    if (anyChanged) ForceRefresh();
}

// Mouse leave — clear all hover states
private void OnChartMouseLeave(object sender, System.Windows.Input.MouseEventArgs e)
{
    foreach (var button in traderButtons)
        button.IsHovered = false;
    ForceRefresh();
}
```

### Rendering the TraderButton

```csharp
// In OnRender — draw each button with state-appropriate styling
private void RenderButtons(SharpDX.Direct2D1.RenderTarget rt)
{
    foreach (var button in traderButtons)
    {
        var rect = new SharpDX.Direct2D1.RoundedRectangle
        {
            Rect = new SharpDX.RectangleF(
                button.Bounds.Left, button.Bounds.Top,
                button.Bounds.Right, button.Bounds.Bottom),
            RadiusX = TraderButton.CornerRadius,
            RadiusY = TraderButton.CornerRadius
        };

        // Background: active = tinted surface, inactive = dark surface, hovered = slightly lighter
        SharpDX.Direct2D1.Brush bgBrush;
        if (button.IsActive)
            bgBrush = activeButtonBgBrush;    // Surface with 15% direction color tint
        else if (button.IsHovered)
            bgBrush = hoverButtonBgBrush;     // Surface + 5% white lift
        else
            bgBrush = inactiveButtonBgBrush;  // #1A1A2E surface

        rt.FillRoundedRectangle(rect, bgBrush);
        rt.DrawRoundedRectangle(rect, button.IsActive ? accentBorderBrush : gridBrush, 1f);

        // Label text
        var textBrush = button.IsActive ? textPrimaryBrush : textSecondaryBrush;
        DrawCenteredText(rt, button.Label, buttonTextFormat, textBrush,
            new SharpDX.RectangleF(
                button.Bounds.Left, button.Bounds.Top,
                button.Bounds.Right, button.Bounds.Bottom));
    }
}
```

### WPF Brush Serialization — [XmlIgnore] Companion Pattern

NinjaTrader's property system serializes `System.Windows.Media.Brush` objects to XML for workspace persistence. SharpDX brushes cannot be serialized. The pattern: expose a WPF `Brush` property for the UI, then convert to SharpDX in `OnRenderTargetChanged()`.

```csharp
// Public WPF property for NinjaTrader's property grid (user-configurable)
[NinjaScriptProperty]
[XmlIgnore]
[Display(Name = "Long Color", GroupName = "Colors", Order = 1)]
public System.Windows.Media.Brush LongColorBrush
{ get; set; }

// Serialization companion — stores as string for XML persistence
[Browsable(false)]
public string LongColorBrushSerialize
{
    get { return Serialize.BrushToString(LongColorBrush); }
    set { LongColorBrush = Serialize.StringToBrush(value); }
}

// In OnStateChange(SetDefaults):
LongColorBrush = System.Windows.Media.Brushes.Green;  // Default

// In OnRenderTargetChanged — convert WPF → SharpDX:
SafeDispose(ref longBrush);
if (RenderTarget != null && LongColorBrush != null)
{
    var mediaColor = ((System.Windows.Media.SolidColorBrush)LongColorBrush).Color;
    longBrush = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, ToColor4(mediaColor));
}
```

### Thread Safety — Volatile Snapshots and Locks

`OnBarUpdate()` runs on the market data thread. `OnRender()` runs on the UI/rendering thread. Sharing data between them requires thread safety.

```csharp
// Pattern 1: volatile for simple value types (int, float, bool, enum)
// Use when: single atomic value that render reads and data writes
private volatile float currentConfidenceScore;
private volatile SignalState currentState;
private volatile bool isLong;

// In OnBarUpdate (data thread):
currentConfidenceScore = CalculateScore();
currentState = DetermineState(currentConfidenceScore);
isLong = currentConfidenceScore > 0;

// In OnRender (UI thread) — safe to read volatile:
float score = currentConfidenceScore;  // Snapshot
RenderHUDState(rt, currentState, isLong);

// Pattern 2: lock for collections and complex objects
// Use when: arrays, lists, dictionaries shared between threads
private readonly object dataLock = new object();
private List<FootprintBar> footprintBars = new List<FootprintBar>();

// In OnBarUpdate (data thread):
lock (dataLock)
{
    footprintBars.Add(newBar);
    if (footprintBars.Count > MaxBarsToRender)
        footprintBars.RemoveAt(0);
}

// In OnRender (UI thread):
List<FootprintBar> barsSnapshot;
lock (dataLock)
{
    barsSnapshot = new List<FootprintBar>(footprintBars);  // Shallow copy under lock
}
// Render from snapshot — no lock held during expensive GPU operations

// Pattern 3: ForceRefresh() — request re-render from data thread
// Call after updating any volatile/locked data that affects visuals
if (ChartControl != null)
    ChartControl.Dispatcher.InvokeAsync(() => ForceRefresh());
```

---

## Section 12: MICRO-INTERACTIONS & VISUAL POLISH

### Trade Print Flash — Aggressive Trade Highlighting

When a large aggressive trade fires (e.g., 50+ contracts at-market), flash the corresponding footprint cell to draw the trader's eye. The animation uses cubic ease-out for a natural "pop then settle" feel.

**Timing envelope:** 500ms total = 200ms fade-in + 100ms hold + 200ms fade-out

```csharp
// Trade flash state per cell
public struct CellFlash
{
    public DateTime StartTime;
    public Color4 FlashColor;    // Direction-colored: green for buy, red for sell
    public float MaxAlpha;       // 0.6 for normal, 0.9 for large prints
    public bool IsActive;
}

// Track active flashes (sparse — only cells with recent prints)
private Dictionary<(int barIndex, double price), CellFlash> activeFlashes
    = new Dictionary<(int, double), CellFlash>();

// Trigger a flash when a large print arrives
private void OnLargePrint(int barIndex, double price, int volume, bool isBuy)
{
    float maxAlpha = volume >= 100 ? 0.9f : 0.6f;  // Larger prints flash brighter
    Color4 color = isBuy
        ? new Color4(0f, 0.902f, 0.463f, 1f)    // #00E676
        : new Color4(1f, 0.090f, 0.267f, 1f);    // #FF1744

    lock (dataLock)
    {
        activeFlashes[(barIndex, price)] = new CellFlash
        {
            StartTime = DateTime.Now,
            FlashColor = color,
            MaxAlpha = maxAlpha,
            IsActive = true
        };
    }
}

// Cubic ease-out: fast start, smooth deceleration
private float CubicEaseOut(float t)
{
    t = t - 1f;
    return t * t * t + 1f;
}

// Calculate flash alpha at current time
private float GetFlashAlpha(CellFlash flash)
{
    double elapsedMs = (DateTime.Now - flash.StartTime).TotalMilliseconds;

    if (elapsedMs >= 500)
        return 0f;  // Expired

    if (elapsedMs < 200)
    {
        // Fade-in phase: 0 → maxAlpha over 200ms with cubic ease-out
        float t = (float)(elapsedMs / 200.0);
        return CubicEaseOut(t) * flash.MaxAlpha;
    }
    else if (elapsedMs < 300)
    {
        // Hold phase: steady at maxAlpha
        return flash.MaxAlpha;
    }
    else
    {
        // Fade-out phase: maxAlpha → 0 over 200ms
        float t = (float)((elapsedMs - 300.0) / 200.0);
        return (1f - CubicEaseOut(t)) * flash.MaxAlpha;
    }
}

// In OnRender — overlay flash on cell
private void RenderCellFlash(SharpDX.Direct2D1.RenderTarget rt, SharpDX.RectangleF cellRect,
    int barIndex, double price)
{
    CellFlash flash;
    bool hasFlash;
    lock (dataLock)
    {
        hasFlash = activeFlashes.TryGetValue((barIndex, price), out flash);
    }

    if (!hasFlash || !flash.IsActive) return;

    float alpha = GetFlashAlpha(flash);
    if (alpha < 0.01f)
    {
        // Clean up expired flash
        lock (dataLock) { activeFlashes.Remove((barIndex, price)); }
        return;
    }

    using (var flashBrush = new SolidColorBrush(rt,
        new Color4(flash.FlashColor.Red, flash.FlashColor.Green, flash.FlashColor.Blue, alpha)))
    {
        rt.FillRectangle(cellRect, flashBrush);
    }
}
```

### Bloomberg Flash-Fade — Directional Price Update

The standard Bloomberg/Reuters pattern for updating prices: old value flashes with the direction color (green for up-tick, red for down-tick), then fades back to neutral in 300ms total.

```csharp
// Track last known value and flash state per data field
public class FlashableValue
{
    public double CurrentValue { get; private set; }
    public double PreviousValue { get; private set; }
    public DateTime LastChangeTime { get; private set; }
    public bool IsUp { get; private set; }

    private const double FLASH_DURATION_MS = 300.0;

    public void Update(double newValue)
    {
        if (Math.Abs(newValue - CurrentValue) < double.Epsilon) return;
        PreviousValue = CurrentValue;
        CurrentValue = newValue;
        IsUp = newValue > PreviousValue;
        LastChangeTime = DateTime.Now;
    }

    public float GetFlashIntensity()
    {
        double elapsed = (DateTime.Now - LastChangeTime).TotalMilliseconds;
        if (elapsed >= FLASH_DURATION_MS) return 0f;

        // Triangle wave: ramp up first half, ramp down second half
        float halfDuration = (float)(FLASH_DURATION_MS / 2.0);
        if (elapsed < halfDuration)
            return (float)(elapsed / halfDuration) * 0.35f;
        else
            return (float)(1.0 - (elapsed - halfDuration) / halfDuration) * 0.35f;
    }

    public Color4 GetFlashColor()
    {
        float intensity = GetFlashIntensity();
        if (intensity < 0.01f) return new Color4(0, 0, 0, 0);

        return IsUp
            ? new Color4(0f, 0.902f, 0.463f, intensity)    // Green flash
            : new Color4(1f, 0.090f, 0.267f, intensity);    // Red flash
    }
}
```

### Data Freshness Dot — Connection Status Indicator

A 6px dot in the corner of any real-time panel showing whether data is flowing. Uses three states with distinct visuals. The green state has a subtle 1Hz pulse to confirm liveness (static green could mean "frozen at last good state").

```csharp
// Freshness states
public enum DataFreshness { Live, Stale, Disconnected }

private DataFreshness currentFreshness = DataFreshness.Live;
private DateTime lastDataTimestamp = DateTime.Now;

// Check freshness (call from OnBarUpdate or timer)
private void UpdateFreshness()
{
    double secondsSinceData = (DateTime.Now - lastDataTimestamp).TotalSeconds;
    if (secondsSinceData < 3.0)
        currentFreshness = DataFreshness.Live;
    else if (secondsSinceData < 15.0)
        currentFreshness = DataFreshness.Stale;
    else
        currentFreshness = DataFreshness.Disconnected;
}

// Render the freshness dot
private void RenderFreshnessDot(SharpDX.Direct2D1.RenderTarget rt, float x, float y)
{
    float radius = 3f;  // 6px diameter
    var center = new SharpDX.Vector2(x, y);
    var ellipse = new SharpDX.Direct2D1.Ellipse(center, radius, radius);

    switch (currentFreshness)
    {
        case DataFreshness.Live:
            // Green with 1Hz pulse (alpha oscillates 0.7 → 1.0)
            float pulse = 0.85f + 0.15f * (float)Math.Sin(
                DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond * 0.00628318);  // 1Hz
            using (var dotBrush = new SolidColorBrush(rt, new Color4(0f, 0.902f, 0.463f, pulse)))
                rt.FillEllipse(ellipse, dotBrush);
            break;

        case DataFreshness.Stale:
            // Solid yellow — no animation (animation = "alive", stale = "not alive")
            using (var dotBrush = new SolidColorBrush(rt, new Color4(1f, 0.702f, 0f, 1f)))
                rt.FillEllipse(ellipse, dotBrush);
            break;

        case DataFreshness.Disconnected:
            // Red with dark border ring for emphasis
            using (var dotBrush = new SolidColorBrush(rt, new Color4(1f, 0.090f, 0.267f, 1f)))
            {
                rt.FillEllipse(ellipse, dotBrush);
                using (var ringBrush = new SolidColorBrush(rt, new Color4(1f, 0.090f, 0.267f, 0.4f)))
                    rt.DrawEllipse(new SharpDX.Direct2D1.Ellipse(center, radius + 2f, radius + 2f),
                        ringBrush, 1.5f);
            }
            break;
    }
}
```

### Zebra Striping — Alternating Row Tint

For any tabular data (signal list, trade log, DOM levels), alternate rows with a barely-visible white tint to aid eye tracking across columns.

```csharp
// Zebra stripe overlay — apply to every other row
// Alpha must be extremely low: 3% white on #0E1014 background = #111519 (barely visible)
private readonly Color4 zebraStripeColor = new Color4(1f, 1f, 1f, 0.03f);

private void RenderZebraStripe(SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF rowRect, int rowIndex)
{
    if (rowIndex % 2 == 1)
    {
        using (var stripeBrush = new SolidColorBrush(rt, zebraStripeColor))
            rt.FillRectangle(rowRect, stripeBrush);
    }
}
```

### Drop Shadow Simulation

SharpDX in NT8 doesn't have a box-shadow CSS equivalent. Simulate with a slightly offset, semi-transparent dark rectangle behind the main element. Cost: one extra FillRoundedRectangle call.

```csharp
// Drop shadow behind a panel — draw BEFORE the panel itself
private void RenderDropShadow(SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF panelBounds, float offsetX = 2f, float offsetY = 2f)
{
    var shadowRect = new SharpDX.Direct2D1.RoundedRectangle
    {
        Rect = new SharpDX.RectangleF(
            panelBounds.Left + offsetX,
            panelBounds.Top + offsetY,
            panelBounds.Right + offsetX,
            panelBounds.Bottom + offsetY),
        RadiusX = 7f,
        RadiusY = 7f
    };

    // 20% black shadow — darker shadow = more "elevation"
    using (var shadowBrush = new SolidColorBrush(rt, new Color4(0f, 0f, 0f, 0.20f)))
        rt.FillRoundedRectangle(shadowRect, shadowBrush);
}

// Usage in panel render:
RenderDropShadow(rt, panelBounds);          // Shadow first
rt.FillRoundedRectangle(panelRect, surfaceBrush);  // Panel on top
rt.DrawRoundedRectangle(panelRect, gridBrush, 1f); // Border
```

### Badge / Pill Design — Compact Status Labels

Small rounded labels for signal tags, status codes, tier badges. Used in signal lists, trade logs, HUD annotations.

```csharp
// Badge rendering: "TIER 1" or "ABS" or "EXH" in a colored pill
private void RenderBadge(SharpDX.Direct2D1.RenderTarget rt,
    string text, float x, float y,
    Color4 bgColor, Color4 borderColor, Color4 textColor)
{
    // Measure text width for auto-sizing
    using (var layout = new SharpDX.DirectWrite.TextLayout(
        Core.Globals.DirectWriteFactory, text, badgeTextFormat, 200f, 20f))
    {
        float textWidth = layout.Metrics.Width;
        float textHeight = layout.Metrics.Height;
        float padX = 8f;
        float padY = 3f;
        float pillWidth = textWidth + padX * 2f;
        float pillHeight = textHeight + padY * 2f;
        float cornerRadius = pillHeight / 2f;  // Fully rounded ends = pill shape

        var pillRect = new SharpDX.Direct2D1.RoundedRectangle
        {
            Rect = new SharpDX.RectangleF(x, y, x + pillWidth, y + pillHeight),
            RadiusX = cornerRadius,
            RadiusY = cornerRadius
        };

        // Tinted background (10-15% of the semantic color)
        using (var bgBrush = new SolidColorBrush(rt, bgColor))
            rt.FillRoundedRectangle(pillRect, bgBrush);

        // 1px border in the full semantic color
        using (var borderBrush = new SolidColorBrush(rt, borderColor))
            rt.DrawRoundedRectangle(pillRect, borderBrush, 1f);

        // Centered text
        using (var textBrush = new SolidColorBrush(rt, textColor))
            rt.DrawTextLayout(new SharpDX.Vector2(x + padX, y + padY), layout, textBrush);
    }
}

// Example badges:
// Absorption: bgColor = cyan@12%, borderColor = cyan@60%, textColor = cyan@100%
// Exhaustion: bgColor = magenta@12%, borderColor = magenta@60%, textColor = magenta@100%
// Tier 1:     bgColor = green@10%, borderColor = green@50%, textColor = green@100%
```

### Persistent Signal Markers vs Ephemeral Flashes

**Design rule:** Signals that result in a trading decision (entry, exit) must leave a persistent visual marker on the chart. Ephemeral animations (flashes, pulses) are for attention — they must NOT be the only record of a signal.

```csharp
// Persistent: diamond marker at signal bar — stays on chart until scrolled away
private void RenderPersistentSignalMarker(SharpDX.Direct2D1.RenderTarget rt,
    int barIndex, double price, bool isLong, float confidence)
{
    float x = chartControl.GetXByBarIndex(chartBars, barIndex);
    float y = (float)chartScale.GetYByValue(price);
    float size = 8f + (confidence / 100f) * 8f;  // 8-16px based on confidence

    // Filled diamond with border
    DrawDiamondSignal(rt, x, isLong ? y - size - 4f : y + size + 4f, size,
        isLong ? longBrush : shortBrush,          // Fill
        textPrimaryBrush);                         // Border
}

// Ephemeral: flash overlay — fades away after 500ms, purely for attention
// (Use CellFlash pattern from above)
// NEVER rely on ephemeral-only. Always pair with persistent.
```

### Warm-Up Skeleton Screen

During indicator warm-up (first N bars loading, data not yet available), show a subtle pulsing skeleton instead of a blank panel or error text. This communicates "loading" without alarming the trader.

```csharp
// Skeleton pulse: slow 0.5Hz opacity oscillation on placeholder rectangles
private void RenderSkeleton(SharpDX.Direct2D1.RenderTarget rt, SharpDX.RectangleF panelBounds)
{
    float pulse = 0.04f + 0.03f * (float)Math.Sin(
        DateTime.Now.Ticks / TimeSpan.TicksPerMillisecond * 0.00314159);  // 0.5Hz

    using (var skelBrush = new SolidColorBrush(rt, new Color4(1f, 1f, 1f, pulse)))
    {
        float y = panelBounds.Top + 12f;
        float lineHeight = 16f;
        float gap = 8f;

        // Simulate text lines at different widths
        float[] widths = { 0.7f, 0.5f, 0.8f, 0.4f, 0.6f };
        foreach (float w in widths)
        {
            var lineRect = new SharpDX.Direct2D1.RoundedRectangle
            {
                Rect = new SharpDX.RectangleF(
                    panelBounds.Left + 12f, y,
                    panelBounds.Left + 12f + (panelBounds.Right - panelBounds.Left - 24f) * w,
                    y + lineHeight),
                RadiusX = 3f,
                RadiusY = 3f
            };
            rt.FillRoundedRectangle(lineRect, skelBrush);
            y += lineHeight + gap;
        }
    }
}
```

### Empty State — "No Signal" Display

When the confidence score is 0 or the system is idle with no actionable signal, display a calm, low-contrast empty state. Never leave the panel blank.

```csharp
// Empty state rendering
private void RenderEmptyState(SharpDX.Direct2D1.RenderTarget rt, SharpDX.RectangleF panelBounds)
{
    // Centered "—" em-dash as universal "nothing to show"
    DrawCenteredText(rt, "—", heroTextFormat, textTertiaryBrush, panelBounds);

    // Subtext below center
    var subtextRect = new SharpDX.RectangleF(
        panelBounds.Left, panelBounds.Top + panelBounds.Bottom * 0.55f,
        panelBounds.Right, panelBounds.Bottom);
    DrawCenteredText(rt, "No active signal", labelTextFormat, textTertiaryBrush, subtextRect);
}
```

---

## Section 13: PREMIUM INDICATOR MARKET

### Overview — What Traders Pay For

Understanding the premium NinjaTrader indicator market is essential for DEEP6 because it establishes the visual and functional bar that professional traders expect. If DEEP6's footprint rendering looks worse than a $500 commercial product, traders won't trust it.

### MZpack — The Market Standard ($500+)

**MZpack Volume Footprint** is the most widely used premium footprint indicator for NinjaTrader 8. It defines trader expectations for footprint visualization.

| Feature | Implementation | DEEP6 Equivalent |
|---------|---------------|-------------------|
| 8 display styles | Bid×Ask, Delta, Delta%, Total Volume, Buy Volume, Sell Volume, Bid×Ask Profile, Delta Profile | DEEP6 supports Bid×Ask + Delta + Heatmap. Add remaining styles for parity. |
| Cluster statistics | POC, VAH, VAL, Delta, Max Delta, Min Delta, Volume, Bid Total, Ask Total per bar | DEEP6 has POC/VAH/VAL + delta. Add per-bar stat summary row below each bar. |
| On-the-fly settings | Right-click context menu to change style, colors, thresholds without opening properties | DEEP6 uses TraderButton row. Consider adding right-click context menu. |
| Diagonal imbalance | Configurable ratio threshold, visual highlighting | DEEP6 has 3-tier imbalance with corner brackets. Comparable. |
| Unfinished business | Marks prices where the last print was a buy/sell but the opposite side hasn't traded | Not yet in DEEP6. Add as a subtle dot or small triangle at cell edge. |
| Cumulative delta profile | Running delta by price level across the visible range | Not yet in DEEP6. Requires session-level price×delta accumulator. |

**Visual quality bar:** MZpack uses clean grid lines, clear bid/ask separation, readable 9pt Consolas equivalent, and the POC is always the brightest element in each bar. Their heatmap uses a blue→yellow→red gradient similar to DEEP6's volume heatmap.

**Common complaint:** MZpack's settings dialog has 100+ options and is overwhelming for new users. DEEP6 should expose 10-15 key settings max, with intelligent defaults.

### OrderFlow v2 by Ninja Algo ($516)

| Feature | Notes | DEEP6 Implication |
|---------|-------|-------------------|
| Delta OHLC candles | Candle body colored by delta open/close, wicks by delta high/low | Novel visualization — consider as an optional overlay mode |
| No tick replay required | Processes historical data without NinjaTrader's expensive tick replay | DEEP6 should document whether it requires tick replay or can work from historical bid/ask volume |
| Stack imbalance | Highlights 3+ consecutive imbalanced price levels in the same direction | DEEP6 has individual cell imbalance. Add stack detection: scan vertically for consecutive imbalance cells and highlight with a bracket connector. |
| Pullback detector | Marks bars where price pulled back to a stack imbalance level | Higher-level pattern — implement in signal engine, not footprint renderer |

**Visual quality bar:** OrderFlow v2 uses a slightly more colorful aesthetic than MZpack, with thicker imbalance highlighting and prominent delta annotations. Text rendering is less refined than MZpack.

### ICF Pro by Investor/CT Fund ($350)

| Feature | Notes | DEEP6 Implication |
|---------|-------|-------------------|
| Aesthetic focus | Designed for clean screenshots and presentation | DEEP6 should look good in screenshots for journals and trade review |
| Fast settings panel | Floating panel with dropdowns for quick style switching | Similar to DEEP6's TraderButton concept but with more options |
| Volume profile per bar | Horizontal volume histogram within each bar's vertical range | Nice visual but low information density. Implement as optional mode. |
| Color themes | 6+ built-in themes (dark, light, blue, etc.) | DEEP6 has 3 palettes (Institutional, High Contrast, Night). Consider adding 2-3 more. |

### TradeDevils Footprint (Mid-Tier)

| Feature | Notes | DEEP6 Implication |
|---------|-------|-------------------|
| 14 templates | Pre-configured setups for different trading styles and markets | Good UX idea: ship DEEP6 with named presets ("NQ Scalp", "NQ Swing", "Deep Analysis") |
| 6 themes | Dark, Light, and custom color scheme slots | DEEP6 should support user-defined custom themes via WPF Brush properties |
| Bar statistics footer | Row below each bar showing total volume, delta, delta %, trade count | Add a summary row feature to DEEP6 footprint — configurable which metrics to show |

### What Justifies Premium Pricing ($300-$500+)

From analyzing customer reviews and product comparisons:

1. **Reliability:** Zero crashes during live trading. The indicator must never throw an unhandled exception. DEEP6 must wrap every `OnRender` and `OnBarUpdate` in try/catch at the top level.

2. **Performance:** No visible lag at 1-tick resolution on NQ. Customers complain loudly about indicators that slow down their charts. DEEP6's 8Hz throttle and 12ms budget address this.

3. **Visual clarity at every zoom level:** Text must be readable at 40px cells AND the heatmap must be informative at 8px cells. The zoom-aware degradation system is essential.

4. **Correct data:** Footprint volumes must match the exchange exactly. Any discrepancy versus the Time & Sales window destroys trust. Verify bid/ask assignment logic against NinjaTrader's built-in Order Flow tools.

5. **Documentation + Support:** Premium products include video tutorials, PDF manuals, and responsive email support. DEEP6 should have inline tooltips and a concise user guide.

### Common Complaints and Solutions

| Complaint | Frequency | Solution for DEEP6 |
|-----------|-----------|-------------------|
| "Too many settings" | Very common | Ship with 10-15 settings max. Use named presets for advanced configs. Hide advanced options behind an "Advanced" expander. |
| "Crashes on historical data" | Common | Null-check all bar data access. Validate `BarsInProgress` and `CurrentBars[n]` before accessing historical bars. |
| "Slow on ES/NQ" | Common | The 8Hz render throttle + visible-bar-only rendering + zoom-aware degradation solve this. |
| "Colors are ugly" | Occasional | DEEP6's institutional palette is rigorously designed. Offer 3+ themes and user-customizable colors via WPF Brush properties. |
| "Doesn't match Time & Sales" | Rare but severe | This is a data accuracy bug. Always verify: bid volume = trades at bid or below, ask volume = trades at ask or above. Match NinjaTrader's MarketDataType.Ask vs MarketDataType.Bid classification. |
| "No trial version" | Very common | If DEEP6 is ever distributed, offer a 14-day trial or a free version with limited features (e.g., footprint only, no HUD). |

---

## Section 14: RESPONSIVE DESIGN

### Priority Hide Order — What Disappears First

When chart space shrinks (window resize, multi-chart layout, mobile-sized panels), elements must disappear in a defined priority order. Critical data stays visible longest.

| Priority | Element | Hide When | Rationale |
|----------|---------|-----------|-----------|
| 1 (hide first) | Volume text in cells | Cell height < 40px | Text becomes illegible; switch to color-only mode |
| 2 | HUD "Why Now" signal list | Panel width < 200px | Secondary information; action + score are sufficient |
| 3 | Badge/pill labels | Panel width < 180px | Replace with color-coded dots |
| 4 | Entry/Stop/Target prices | Panel width < 160px | Available via tooltip or data window |
| 5 | Confidence bar (progress) | Panel width < 140px | Score number is sufficient |
| 6 | VAH/VAL dashed lines | Cell height < 20px | Merge into heatmap; POC line persists longer |
| 7 | POC line | Cell height < 12px | Even POC becomes noise at this zoom level |
| 8 | Imbalance cell fills | Cell height < 8px | Below heatmap threshold — skip all rendering |
| 9 (hide last) | Action word (LONG/SHORT) | Never | The action word is the single most important element. It is always visible. |
| — | Candle bodies | Never | Price action is sacrosanct. Footprint overlays never hide candles. |

```csharp
// Responsive layout calculation
private struct LayoutMode
{
    public bool ShowCellText;
    public bool ShowSignalList;
    public bool ShowBadges;
    public bool ShowPrices;
    public bool ShowConfidenceBar;
    public bool ShowVAHVAL;
    public bool ShowPOC;
    public bool ShowImbalanceFills;
    public bool ShowActionWord;
}

private LayoutMode CalculateLayout(float cellHeight, float panelWidth)
{
    return new LayoutMode
    {
        ShowCellText        = cellHeight >= 40f,
        ShowSignalList      = panelWidth >= 200f,
        ShowBadges          = panelWidth >= 180f,
        ShowPrices          = panelWidth >= 160f,
        ShowConfidenceBar   = panelWidth >= 140f,
        ShowVAHVAL          = cellHeight >= 20f,
        ShowPOC             = cellHeight >= 12f,
        ShowImbalanceFills  = cellHeight >= 8f,
        ShowActionWord      = true   // ALWAYS visible
    };
}
```

### Font Scaling — Adaptive Text Size

Text size must scale with available cell space. Below minimum legibility, skip text entirely rather than rendering unreadable glyphs.

| Bar Width (px) | Font Size | Weight | Rendering |
|----------------|-----------|--------|-----------|
| ≥ 80px | 10pt | Medium (500) | Full `"  42 x 87  "` with padding |
| 60–80px | 9pt | Medium (500) | Compact `"42x87"` no padding |
| 40–60px | 8pt | Medium (500) | Bid only or Ask only (alternate rows) |
| 20–40px | 6pt | SemiBold (600) | Volume number only, no separator |
| < 20px | Skip | — | Color-only or heatmap mode |

```csharp
// Dynamic text format selection based on cell dimensions
private SharpDX.DirectWrite.TextFormat GetCellTextFormat(float cellWidth, float cellHeight)
{
    if (cellWidth >= 80f && cellHeight >= 40f)
        return cellTextFormat10pt;    // 10pt full mode
    else if (cellWidth >= 60f && cellHeight >= 30f)
        return cellTextFormat9pt;     // 9pt compact mode
    else if (cellWidth >= 40f && cellHeight >= 25f)
        return cellTextFormat8pt;     // 8pt minimal mode
    else if (cellWidth >= 20f && cellHeight >= 16f)
        return cellTextFormat6pt;     // 6pt number-only mode
    else
        return null;                  // Skip text rendering
}

// Create all format variants in OnStateChange(Configure):
private void CreateTextFormats()
{
    cellTextFormat10pt = new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory, "Consolas",
        SharpDX.DirectWrite.FontWeight.Medium, SharpDX.DirectWrite.FontStyle.Normal, 10f);

    cellTextFormat9pt = new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory, "Consolas",
        SharpDX.DirectWrite.FontWeight.Medium, SharpDX.DirectWrite.FontStyle.Normal, 9f);

    cellTextFormat8pt = new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory, "Consolas",
        SharpDX.DirectWrite.FontWeight.Medium, SharpDX.DirectWrite.FontStyle.Normal, 8f);

    cellTextFormat6pt = new SharpDX.DirectWrite.TextFormat(
        Core.Globals.DirectWriteFactory, "Consolas",
        SharpDX.DirectWrite.FontWeight.SemiBold, SharpDX.DirectWrite.FontStyle.Normal, 6f);
    // SemiBold at 6pt to compensate for reduced stroke visibility at small sizes
}
```

### Zoom-Aware Cell Rendering — Four Modes

This extends Section 4's zoom degradation into a formal mode system with specific rendering instructions per mode.

```csharp
public enum CellRenderMode { Full, ColoredRect, Heatmap, Skip }

private CellRenderMode GetCellRenderMode(float cellHeight, float cellWidth)
{
    if (cellHeight >= 40f && cellWidth >= 40f)
        return CellRenderMode.Full;           // Text + fill + borders + POC/VAH
    else if (cellHeight >= 20f && cellWidth >= 20f)
        return CellRenderMode.ColoredRect;    // Imbalance fill + POC line, no text
    else if (cellHeight >= 8f)
        return CellRenderMode.Heatmap;        // Single color per cell by volume
    else
        return CellRenderMode.Skip;           // Don't render individual cells
}

// Full mode: everything visible
private void RenderCellFull(SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect, int bidVol, int askVol,
    int tier, bool isPOC, bool isVAH, bool isVAL)
{
    // 1. Imbalance fill
    if (tier > 0)
        ApplyTierFill(rt, cellRect, tier);

    // 2. Grid border (0.5px, subtle)
    rt.DrawRectangle(cellRect, gridBrush, 0.5f);

    // 3. Bid text (right-aligned in left half)
    var bidRect = new SharpDX.RectangleF(
        cellRect.Left, cellRect.Top, cellRect.Left + (cellRect.Right - cellRect.Left) / 2f, cellRect.Bottom);
    DrawRightAlignedText(rt, bidVol.ToString(), GetCellTextFormat(cellRect.Right - cellRect.Left, cellRect.Bottom - cellRect.Top),
        textPrimaryBrush, bidRect);

    // 4. Ask text (left-aligned in right half)
    float midX = cellRect.Left + (cellRect.Right - cellRect.Left) / 2f;
    var askRect = new SharpDX.RectangleF(
        midX + 2f, cellRect.Top, cellRect.Right - 2f, cellRect.Bottom);
    rt.DrawText(askVol.ToString(), GetCellTextFormat(cellRect.Right - cellRect.Left, cellRect.Bottom - cellRect.Top),
        askRect, textPrimaryBrush);

    // 5. POC highlight
    if (isPOC)
    {
        float pocY = cellRect.Top + (cellRect.Bottom - cellRect.Top) / 2f;
        rt.DrawLine(new SharpDX.Vector2(cellRect.Left, pocY),
            new SharpDX.Vector2(cellRect.Right, pocY), pocBrush, 2f);
    }

    // 6. Corner brackets for Tier 3
    if (tier >= 3)
        DrawCornerBrackets(rt, cellRect, longBrush);
}

// ColoredRect mode: fills and lines only
private void RenderCellColoredRect(SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect, int tier, bool isPOC)
{
    if (tier > 0) ApplyTierFill(rt, cellRect, tier);
    if (isPOC)
    {
        float pocY = cellRect.Top + (cellRect.Bottom - cellRect.Top) / 2f;
        rt.DrawLine(new SharpDX.Vector2(cellRect.Left, pocY),
            new SharpDX.Vector2(cellRect.Right, pocY), pocBrush, 1.5f);
    }
}

// Heatmap mode: single color per cell based on volume intensity
private void RenderCellHeatmap(SharpDX.Direct2D1.RenderTarget rt,
    SharpDX.RectangleF cellRect, float normalizedVolume)
{
    Color4 heatColor = GetHeatmapColor(normalizedVolume);
    using (var heatBrush = new SolidColorBrush(rt, heatColor))
        rt.FillRectangle(cellRect, heatBrush);
}
```

### Abbreviated Numbers — Compact Formatting

When cell space is tight, abbreviate large numbers to save horizontal space while maintaining data comprehension.

```csharp
// Number abbreviation for tight cells
private string FormatVolume(int volume, float cellWidth)
{
    if (cellWidth >= 60f)
    {
        // Full number with comma separators
        return volume.ToString("N0");  // "1,234" or "42"
    }
    else if (cellWidth >= 40f)
    {
        // Abbreviated: 1.2K, 15K, 1.5M
        if (volume >= 1_000_000)
            return (volume / 1_000_000f).ToString("0.#") + "M";
        else if (volume >= 10_000)
            return (volume / 1_000f).ToString("0") + "K";     // "15K"
        else if (volume >= 1_000)
            return (volume / 1_000f).ToString("0.#") + "K";   // "1.2K"
        else
            return volume.ToString();                           // "42"
    }
    else
    {
        // Ultra-compact: just the number, no separators
        if (volume >= 1_000_000)
            return (volume / 1_000_000f).ToString("0") + "M";
        else if (volume >= 1_000)
            return (volume / 1_000f).ToString("0") + "K";
        else
            return volume.ToString();
    }
}

// Usage in cell rendering:
string bidText = FormatVolume(bidVolume, cellWidth / 2f);  // Half cell for each side
string askText = FormatVolume(askVolume, cellWidth / 2f);
```

### Multi-Monitor and DPI Considerations

NinjaTrader 8 runs on WPF, which supports per-monitor DPI scaling. SharpDX rendering coordinates are in device-independent pixels (DIPs), but the actual pixel density varies.

```csharp
// DPI-aware sizing
// ChartControl provides the scaling factor:
// chartControl.Properties.ChartTrader  — not directly, but through PresentationSource

// Get DPI scale factor (1.0 = 96 DPI, 1.25 = 120 DPI, 1.5 = 144 DPI, 2.0 = 192 DPI)
private float GetDpiScale()
{
    if (ChartControl == null) return 1.0f;

    var source = System.Windows.PresentationSource.FromVisual(
        ChartControl as System.Windows.Media.Visual);
    if (source?.CompositionTarget != null)
        return (float)source.CompositionTarget.TransformToDevice.M11;

    return 1.0f;
}

// DPI-aware minimum sizes
private float GetMinCellHeight()
{
    float dpiScale = GetDpiScale();
    // At 2x DPI (4K monitor), 40px physical = 20 DIPs, so text is still readable
    // At 1x DPI (1080p), 40px = 40px, normal rendering
    // Scale thresholds DOWN for high DPI (text is physically larger per DIP)
    return 40f / dpiScale;
}

// Multi-monitor layout notes:
// - NinjaTrader windows can span monitors with different DPIs
// - GetDpiScale() may return different values if chart is moved between monitors
// - OnRenderTargetChanged() fires when DPI changes — brushes are recreated automatically
// - TextFormat is DPI-independent (points are absolute) — no adjustment needed
// - Use chartControl.Properties.BarDistance for zoom-aware sizing, not fixed pixel values
// - Test on both 1080p (100% scaling) and 4K (150-200% scaling) monitors
```

### Quick Reference — Responsive Breakpoints

```
CELL HEIGHT BREAKPOINTS
  ≥40px    Full text mode: bid×ask, grid, POC, VAH/VAL, imbalance tiers
  20-40px  Color-only mode: tier fills, POC line, no text
  8-20px   Heatmap mode: single color per cell by volume intensity
  <8px     Skip: no individual cells, bar-level summary only

CELL WIDTH BREAKPOINTS
  ≥80px    Full text with padding: "  42 x 87  "
  60-80px  Compact text: "42x87"
  40-60px  Single column: bid OR ask
  20-40px  Abbreviated: "1.2K"
  <20px    No text, color only

HUD PANEL WIDTH BREAKPOINTS
  ≥240px   Full decision rail: action, score, prices, signals, bar
  200-240px  Compact: action, score, prices
  160-200px  Minimal: action, score
  140-160px  Ultra-compact: action word only + confidence dot
  <140px   Collapse to floating badge: direction arrow + score number

FONT SCALING
  Bar ≥80px   10pt Consolas Medium
  Bar 60-80px  9pt Consolas Medium
  Bar 40-60px  8pt Consolas Medium
  Bar 20-40px  6pt Consolas SemiBold
  Bar <20px    No text
```
