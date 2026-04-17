I have enough authoritative material to write the full research document. Now I'll produce the long-form deliverable directly as my final response.

---

# DEEP6 NinjaTrader 8 — Animation Engine & Advanced Interaction Patterns

**The "make it feel alive" companion to the visual design library.** This document is the operating manual for an NT8 indicator/drawing tool that *responds, breathes, and confirms* — without ever blocking the render loop on a fast NQ tape.

It is structured as the production-grade reference the graphics agent will quote from when generating any NinjaScript that needs animation, mouse/keyboard interaction, tooltips, context menus, notifications, or audio. All code targets NT8 NinjaScript / SharpDX / WPF, runs on a Mac-developed → Windows-deployed pipeline, and assumes the indicator may be one of several active on a 1-second NQ chart.

---

## Part 1 — Foundations: Time, Refresh, and the Frame Budget

### 1.1 The 250ms Truth About OnRender

The single most important fact when building NT8 visuals is this: **`ChartControl` runs an internal timer every 250 ms that decides whether `OnRender()` should fire.** That is the floor refresh rate. Everything else is layered on top.

The standard triggers for `OnRender()` are:
- `OnBarUpdate()` events (real-time and historical)
- `OnConnectionStatusUpdate()` events
- User chart interactions (pan, zoom, scale change)
- A drawing object being added or removed
- Strategy enable/disable
- ChartTrader being toggled

If none of those happen, `OnRender()` does **not** fire — even if your internal state has changed. This is the source of 90% of "my animation isn't moving" complaints.

`ForceRefresh()` is the official escape hatch. It does *not* render immediately; it **queues** the next render request so the next 250 ms tick will pick it up. From the docs (`forcerefresh.htm`): "Excessive calls to ForceRefresh() and OnRender() can carry an impact on general application performance." It also explicitly warns against directly invalidating the chart control because that "risks threading issues which result in deadlocks."

What this means for animation:

1. **You cannot get below ~250 ms of latency from `ForceRefresh` alone.** If you want a 60 fps pulse, you need a separate timer — but that timer's job is *not* to call `OnRender` (you can't), it's to call `ForceRefresh()` on a faster cadence and let NT8 coalesce.
2. **You need a per-frame `Stopwatch`-based delta time** because `OnRender` will be irregular. Never assume "this fires every X ms."
3. **You need an "is anything alive?" bit** so that when no animations are active you stop calling `ForceRefresh()` and let the chart go idle.

### 1.2 The Animation Pump Pattern

The core pattern that solves the 250 ms problem is a `DispatcherTimer` (16 ms or 33 ms) that does two things:
- Advances the animation state machine using `Stopwatch.Elapsed`
- Calls `ChartControl.Dispatcher.InvokeAsync(() => ForceRefresh())` only when there is at least one active animation

`OnRender()` itself does no time arithmetic. It just walks the state machine and draws whatever the current frame says.

```csharp
// AnimationPump.cs — owned by an indicator or drawing tool
using System;
using System.Diagnostics;
using System.Windows.Threading;
using NinjaTrader.Gui.Chart;

internal sealed class AnimationPump
{
    private readonly DispatcherTimer _timer;
    private readonly Stopwatch _sw = Stopwatch.StartNew();
    private readonly ChartControl _chart;
    private readonly AnimationEngine _engine;
    private TimeSpan _lastTick;

    public AnimationPump(ChartControl chart, AnimationEngine engine, int intervalMs = 16)
    {
        _chart  = chart;
        _engine = engine;
        _timer  = new DispatcherTimer(DispatcherPriority.Render)
        {
            Interval = TimeSpan.FromMilliseconds(intervalMs)
        };
        _timer.Tick += OnTick;
    }

    public void Start() { _lastTick = _sw.Elapsed; _timer.Start(); }
    public void Stop()  { _timer.Stop(); }

    private void OnTick(object sender, EventArgs e)
    {
        var now = _sw.Elapsed;
        var dt  = now - _lastTick;
        _lastTick = now;

        // Advance state. Returns true if any animation is still alive.
        bool alive = _engine.Advance(dt);

        if (!alive) return;          // idle — let the chart breathe
        if (_chart == null) return;

        // ForceRefresh must be marshalled to the UI thread.
        _chart.Dispatcher.InvokeAsync(() =>
        {
            try { _chart.InvalidateVisual(); } catch { /* chart torn down */ }
            // Equivalently, on the indicator: ForceRefresh();
            // InvalidateVisual is preferred when the pump lives outside the indicator.
        }, DispatcherPriority.Render);
    }
}
```

Two key points:

1. **`DispatcherPriority.Render`** keeps the timer in the same priority bucket as WPF's compositor. `Normal` and lower priorities will get starved by mouse/keyboard events on a busy chart.
2. **Don't use `CompositionTarget.Rendering` inside an indicator.** It is the WPF equivalent of vsync (typically 60 Hz) and will fire even when the chart is offscreen, eating CPU. It's a great choice for *standalone* WPF apps; inside NT8, the `DispatcherTimer` + `ForceRefresh` combination integrates with the chart's own redraw cycle and is what NinjaTrader's threading guidance points you toward.

### 1.3 Frame Budget Tables

Targets:

| Refresh strategy | Tick interval | Per-frame budget | Notes |
|---|---|---|---|
| Native NT8 (no pump)         | 250 ms | ~80 ms     | Fine for non-animated indicators. |
| 30 fps pump                  | 33 ms  | ~22 ms     | Comfortable for ≤3 simultaneous animations. |
| 60 fps pump                  | 16 ms  | ~10 ms     | Reserve for hover-tracking and active drawing. |
| Burst (drag in progress)     | 16 ms  | ~10 ms     | Drop back to 33 ms when mouse is up. |

Inside `OnRender`, instrument any block that can balloon (footprint cell loops, glow gradients):

```csharp
private long _lastRenderTicks;

protected override void OnRender(ChartControl c, ChartScale s)
{
    var sw = Stopwatch.StartNew();

    DrawFootprintCells(c, s);   // hot path
    long t1 = sw.ElapsedTicks;

    DrawAnimations(c, s);
    long t2 = sw.ElapsedTicks;

    DrawTooltipIfHovered(c, s);
    long t3 = sw.ElapsedTicks;

    sw.Stop();

    if (sw.ElapsedMilliseconds > 8)
    {
        Print($"OnRender slow: cells={Ticks(t1)}ms anim={Ticks(t2-t1)}ms tip={Ticks(t3-t2)}ms total={sw.ElapsedMilliseconds}ms");
    }
    _lastRenderTicks = sw.ElapsedTicks;
}

private static double Ticks(long t) => t * 1000.0 / Stopwatch.Frequency;
```

Threshold logging (only print when slow) is the discipline that survives a fast tape — you get noise-free production logs, but the second you go over budget you find out exactly which sub-phase is the culprit.

### 1.4 IsSuspendedWhileInactive — Free Performance

Per NT8 docs (`issuspendedwhileinactive.htm`): when set true, `OnBarUpdate` stops while the chart's tab is inactive. This also stops the trigger that makes `OnRender` fire from bar updates — but **your animation pump will keep running** unless you check.

Hook visibility into the pump:

```csharp
public bool IsChartVisible
    => ChartControl != null
       && ChartControl.IsVisible
       && PresentationSource.FromVisual(ChartControl) != null;
```

In the pump's `OnTick`, short-circuit when the chart is invisible. This is the single biggest CPU win on multi-chart workspaces.

---

## Part 2 — The Animation Engine

### 2.1 State Machine Design

The right shape for transient effects is a typed state container keyed by an effect identity, with a `Render(ctx, t)` callback the engine invokes each frame.

Three rules govern correctness:

1. **All effect mutation happens on the UI thread** (because `OnRender` does), with one exception — *adding* effects can come from any thread, so the collection must be thread-safe for writes.
2. **Eviction is O(active effects)**, run once per pump tick, not per render. Rendering should never branch on "is this expired?"
3. **Cap the count.** A misbehaving signal stream that fires 10/sec should never strand 5,000 active pulse effects.

```csharp
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using SharpDX;

public abstract class AnimationEffect
{
    public string  Key      { get; init; }
    public TimeSpan StartedAt { get; private set; }
    public TimeSpan Duration  { get; init; }
    public int      Priority  { get; init; } = 0;

    public bool Started   { get; private set; }
    public bool Completed { get; private set; }

    public void Start(TimeSpan now) { StartedAt = now; Started = true; }
    public void Complete()           { Completed = true; }

    /// <summary> Progress in [0,1]. </summary>
    public float Progress(TimeSpan now)
    {
        if (Duration <= TimeSpan.Zero) return 1f;
        var p = (float)((now - StartedAt).TotalMilliseconds / Duration.TotalMilliseconds);
        return p < 0 ? 0 : p > 1 ? 1 : p;
    }

    public abstract void Render(RenderContext ctx, float progress);
}

public sealed class AnimationEngine
{
    private const int MaxActive = 256;

    private readonly ConcurrentQueue<AnimationEffect>            _pending = new();
    private readonly Dictionary<string, AnimationEffect>          _active  = new(StringComparer.Ordinal);
    private TimeSpan _now;

    public int ActiveCount => _active.Count;

    /// <summary> Thread-safe enqueue (call from background or signal threads). </summary>
    public void Enqueue(AnimationEffect e) => _pending.Enqueue(e);

    /// <summary> UI thread. Advance state, return true if anything still animating. </summary>
    public bool Advance(TimeSpan dt)
    {
        _now += dt;

        // Drain pending → active. Replace by key (newer wins).
        while (_pending.TryDequeue(out var e))
        {
            if (_active.Count >= MaxActive) EvictOldest();
            e.Start(_now);
            _active[e.Key] = e;
        }

        // Evict expired.
        if (_active.Count > 0)
        {
            List<string> dead = null;
            foreach (var kv in _active)
            {
                if (kv.Value.Progress(_now) >= 1f || kv.Value.Completed)
                    (dead ??= new()).Add(kv.Key);
            }
            if (dead != null) foreach (var k in dead) _active.Remove(k);
        }

        return _active.Count > 0;
    }

    /// <summary> UI thread, called from OnRender. </summary>
    public void RenderAll(RenderContext ctx)
    {
        if (_active.Count == 0) return;
        // Stable ordering: priority ascending so high-priority paints last (on top).
        foreach (var e in OrderedByPriority())
            e.Render(ctx, e.Progress(_now));
    }

    private IEnumerable<AnimationEffect> OrderedByPriority()
    {
        var list = new List<AnimationEffect>(_active.Values);
        list.Sort((a, b) => a.Priority.CompareTo(b.Priority));
        return list;
    }

    private void EvictOldest()
    {
        string oldestKey = null;
        TimeSpan oldest  = TimeSpan.MaxValue;
        foreach (var kv in _active)
            if (kv.Value.StartedAt < oldest) { oldest = kv.Value.StartedAt; oldestKey = kv.Key; }
        if (oldestKey != null) _active.Remove(oldestKey);
    }
}

public readonly struct RenderContext
{
    public RenderContext(SharpDX.Direct2D1.RenderTarget rt, SharpDX.Direct2D1.Factory f, BrushCache brushes,
                         ChartContext chart)
    { RT = rt; Factory = f; Brushes = brushes; Chart = chart; }

    public SharpDX.Direct2D1.RenderTarget RT      { get; }
    public SharpDX.Direct2D1.Factory      Factory { get; }
    public BrushCache                     Brushes { get; }
    public ChartContext                   Chart   { get; }
}
```

The use of `ConcurrentQueue` for the producer-consumer boundary and a plain `Dictionary` for the active set is deliberate. Lock-free pending intake means a Kronos thread or a Rithmic callback can post effects without ever blocking the UI; the UI thread is the only writer of the active dictionary, so no locking is needed there.

### 2.2 Easing Functions

Trading UI rewards two easing principles:

1. **Ease-out for entry, exit, and one-shot transients** (signal flash, fade in). The motion *settles* — feels confident, decisive.
2. **Linear for countdowns and progress** (volume bar fill, time-to-bar-close). Mathematical truth, no aesthetic.

What you almost always *don't* want: **bouncy, elastic, or `easeInOutBack`** for anything in the live data area. They communicate "playful" and that is the wrong tone when money is moving. Reserve them for empty states and onboarding — not signals.

**The library** (drop-in, allocation-free):

```csharp
public static class Easing
{
    private const float Pi = 3.1415927f;

    public static float Linear(float t) => t;

    // -------- Cubic --------
    public static float OutCubic(float t)    { var u = 1f - t; return 1f - u*u*u; }
    public static float InCubic(float t)     => t*t*t;
    public static float InOutCubic(float t)
        => t < 0.5f ? 4f*t*t*t : 1f - (float)System.Math.Pow(-2f*t + 2f, 3) / 2f;

    // -------- Quart (slightly snappier than cubic, useful for entries) --------
    public static float OutQuart(float t)    { var u = 1f - t; return 1f - u*u*u*u; }

    // -------- Quint --------
    public static float OutQuint(float t)    { var u = 1f - t; return 1f - u*u*u*u*u; }

    // -------- Expo (the "settling" curve trading UI loves) --------
    public static float OutExpo(float t)     => t >= 1f ? 1f : 1f - (float)System.Math.Pow(2f, -10f*t);
    public static float InExpo(float t)      => t <= 0f ? 0f : (float)System.Math.Pow(2f, 10f*t - 10f);
    public static float InOutExpo(float t)
    {
        if (t <= 0f) return 0f;
        if (t >= 1f) return 1f;
        return t < 0.5f
            ? (float)System.Math.Pow(2f, 20f*t - 10f) / 2f
            : (2f - (float)System.Math.Pow(2f, -20f*t + 10f)) / 2f;
    }

    // -------- Sine (smoothest infinite loop choice for breathing) --------
    public static float InOutSine(float t)   => -((float)System.Math.Cos(Pi * t) - 1f) / 2f;

    // -------- Material Standard cubic-bezier(0.4, 0, 0.2, 1) approximation --------
    public static float MaterialStandard(float t) => CubicBezier(0.4f, 0f, 0.2f, 1f, t);

    // -------- Material Emphasized cubic-bezier(0.2, 0, 0, 1) --------
    public static float MaterialEmphasized(float t) => CubicBezier(0.2f, 0f, 0f, 1f, t);

    // Newton's method, 4 iterations. ±0.001 accurate, no allocations.
    public static float CubicBezier(float p1x, float p1y, float p2x, float p2y, float x)
    {
        float Cx(float t) => 3f*p1x*(1f-t)*(1f-t)*t + 3f*p2x*(1f-t)*t*t + t*t*t;
        float Cy(float t) => 3f*p1y*(1f-t)*(1f-t)*t + 3f*p2y*(1f-t)*t*t + t*t*t;
        float DCx(float t) =>
              3f*p1x*(1f - 4f*t + 3f*t*t)
            + 3f*p2x*(2f*t - 3f*t*t)
            + 3f*t*t;

        float t = x;
        for (int i = 0; i < 4; i++)
        {
            float dx  = Cx(t) - x;
            float dxd = DCx(t);
            if (System.Math.Abs(dxd) < 1e-6f) break;
            t -= dx / dxd;
        }
        return Cy(t);
    }

    /// <summary>Triangle 0→1→0, k cycles over progress 0..1.</summary>
    public static float Pulse(float t, int k)
    {
        var x = t * k;
        var f = x - (float)System.Math.Floor(x);
        return f < 0.5f ? f * 2f : (1f - f) * 2f;
    }

    /// <summary>Smooth sinusoidal pulse 0→1→0.</summary>
    public static float Breathe(float t)
        => 0.5f * (1f - (float)System.Math.Cos(2f * Pi * t));
}
```

### 2.3 Easing Cheat Sheet

| Effect type                                | Easing                  | Why |
|---|---|---|
| Signal flash entry (alpha 0 → max)         | `OutExpo`               | Fast attack, smooth settle. The trader sees it land. |
| Fade-out / dismissal                       | `OutCubic`              | Gentle, doesn't pull attention back. |
| Slide-in panel                             | `MaterialStandard`      | The Material 0.4/0/0.2/1 curve is perfect for in-screen movement. |
| Number tick-up                             | `OutQuart`              | Snappy without overshoot. |
| Border breathe (active state)              | `Breathe` (sin)         | Continuous, no perceptible loop seam. |
| Glow pulse                                 | `Breathe` × 1 cycle     | Same. |
| Tooltip appear                             | `OutCubic` over 120 ms  | Just enough to register. |
| Tooltip disappear                          | `Linear` over 80 ms     | The user is already looking elsewhere. |
| Toast slide-in                             | `MaterialEmphasized`    | The 0.2/0/0/1 curve is the "look at me" curve. |
| Countdown bar (time to close, %fill)       | `Linear`                | Aesthetic: zero. Honesty: total. |
| Drag preview snap                          | `OutCubic` over 80 ms   | Snap target found → settle there. |
| Drawing tool handle hover scale 1 → 1.15   | `OutCubic` over 120 ms  | Tactile feedback on grab. |
| Order ticket appear                        | `OutExpo` over 180 ms   | Decisive, like a confirmation. |
| Error shake (stop submitted at wrong px)   | Damped sine, 220 ms     | Communicates rejection without being a toy. |

### 2.4 Specific Animation Recipes

Every recipe inherits from `AnimationEffect`. They share a `RenderContext`. Brushes are pulled from a `BrushCache` (covered in §2.5) so we never allocate inside `OnRender`.

#### Pulse (alpha 70 → 100 → 70 over N seconds, K cycles)

```csharp
public sealed class PulseEffect : AnimationEffect
{
    public RawRectangleF Rect { get; init; }
    public Color4 Color       { get; init; }
    public float MinAlpha     { get; init; } = 0.4f;
    public float MaxAlpha     { get; init; } = 1.0f;
    public int   Cycles       { get; init; } = 3;
    public float StrokeWidth  { get; init; } = 1.5f;

    public override void Render(RenderContext ctx, float t)
    {
        // Sinusoidal pulse, K cycles.
        float wave  = 0.5f * (1f - (float)System.Math.Cos(2f * 3.1415927f * Cycles * t));
        float alpha = MinAlpha + (MaxAlpha - MinAlpha) * wave;

        // Optional life-fade so it doesn't end abruptly.
        alpha *= 1f - Easing.InCubic(t);

        var c = new Color4(Color.Red, Color.Green, Color.Blue, alpha);
        using (var brush = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, c))
            ctx.RT.DrawRectangle(Rect, brush, StrokeWidth);
    }
}
```

#### Flash-and-Fade (alpha 100 → 0 over N ms, single shot)

```csharp
public sealed class FlashFadeEffect : AnimationEffect
{
    public RawRectangleF Rect { get; init; }
    public Color4 Color       { get; init; }

    public override void Render(RenderContext ctx, float t)
    {
        var alpha = 1f - Easing.OutExpo(t);
        if (alpha <= 0.01f) { Complete(); return; }

        var c = new Color4(Color.Red, Color.Green, Color.Blue, alpha);
        using var brush = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, c);
        ctx.RT.FillRectangle(Rect, brush);
    }
}
```

#### Slide-In (offset N px → 0 over M ms)

```csharp
public sealed class SlideInEffect : AnimationEffect
{
    public Action<float, float, RenderContext> Draw { get; init; } // dxOffset, alpha, ctx
    public float StartOffsetPx { get; init; } = 24f;

    public override void Render(RenderContext ctx, float t)
    {
        float eased = Easing.MaterialStandard(t);
        float dx    = StartOffsetPx * (1f - eased);
        float a     = eased;
        Draw(dx, a, ctx);
    }
}
```

#### Color Crossfade (RGB lerp over N ms)

```csharp
public sealed class ColorCrossfadeEffect : AnimationEffect
{
    public RawRectangleF Rect { get; init; }
    public Color4 From        { get; init; }
    public Color4 To          { get; init; }

    public override void Render(RenderContext ctx, float t)
    {
        float e = Easing.OutCubic(t);
        var c = new Color4(
            From.Red   + (To.Red   - From.Red)   * e,
            From.Green + (To.Green - From.Green) * e,
            From.Blue  + (To.Blue  - From.Blue)  * e,
            From.Alpha + (To.Alpha - From.Alpha) * e);
        using var brush = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, c);
        ctx.RT.FillRectangle(Rect, brush);
    }
}
```

#### Number Tick-Up (smooth interpolation old → new)

```csharp
public sealed class NumberTickEffect : AnimationEffect
{
    public Vector2 Origin       { get; init; }
    public double  From         { get; init; }
    public double  To           { get; init; }
    public string  Format       { get; init; } = "N0";
    public Color4  Color        { get; init; }
    public TextFormat TextFmt   { get; init; }

    public override void Render(RenderContext ctx, float t)
    {
        double v = From + (To - From) * Easing.OutQuart(t);
        var s = v.ToString(Format);
        using var b = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, Color);
        ctx.RT.DrawText(s, TextFmt, new RawRectangleF(Origin.X, Origin.Y, Origin.X + 200, Origin.Y + 40), b);
    }
}
```

#### Border Breathe (1 px → 2 px → 1 px, looped, for active states)

```csharp
public sealed class BreatheEffect : AnimationEffect
{
    public RawRectangleF Rect { get; init; }
    public Color4 Color       { get; init; }
    public float MinStroke    { get; init; } = 1f;
    public float MaxStroke    { get; init; } = 2.5f;
    public float PeriodMs     { get; init; } = 2400f;

    public override void Render(RenderContext ctx, float t)
    {
        // Re-derive phase from total elapsed so it can loop forever.
        // (Set Duration = TimeSpan.MaxValue so it never expires.)
        var ms    = (StartedAt + (Started ? (StartedAt) : TimeSpan.Zero)).TotalMilliseconds; // stable phase
        var phase = (float)((System.Environment.TickCount % (int)PeriodMs) / PeriodMs);
        var w     = Easing.Breathe(phase);
        var sw    = MinStroke + (MaxStroke - MinStroke) * w;

        using var brush = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, Color);
        ctx.RT.DrawRectangle(Rect, brush, sw);
    }
}
```

For genuinely infinite loops, set `Duration = TimeSpan.MaxValue` and key the phase off `Environment.TickCount` so the engine never marks it complete; cancel it explicitly when the active state ends.

#### Glow Ramp (radial outer brush 0 → 30% → 0 over N ms)

```csharp
public sealed class GlowEffect : AnimationEffect
{
    public Vector2 Center { get; init; }
    public float Radius   { get; init; } = 32f;
    public Color4 Color   { get; init; }

    public override void Render(RenderContext ctx, float t)
    {
        var alpha = 0.30f * Easing.Breathe(t);
        if (alpha <= 0.01f) return;

        using var stops = new SharpDX.Direct2D1.GradientStopCollection(ctx.RT, new[]
        {
            new SharpDX.Direct2D1.GradientStop { Position = 0f, Color = new Color4(Color.Red, Color.Green, Color.Blue, alpha) },
            new SharpDX.Direct2D1.GradientStop { Position = 1f, Color = new Color4(Color.Red, Color.Green, Color.Blue, 0f)    },
        });

        var props = new SharpDX.Direct2D1.RadialGradientBrushProperties
        {
            Center               = Center,
            GradientOriginOffset = new Vector2(0, 0),
            RadiusX              = Radius,
            RadiusY              = Radius
        };

        using var brush = new SharpDX.Direct2D1.RadialGradientBrush(ctx.RT, props, stops);
        ctx.RT.FillEllipse(new SharpDX.Direct2D1.Ellipse(Center, Radius, Radius), brush);
    }
}
```

A note on radial gradients: they are *expensive* — every dispose recompiles the brush. If you have ≥10 simultaneous glows, hoist `GradientStopCollection` to `OnRenderTargetChanged` and only mutate the brush color stops via a swap.

#### Comet Tail (path opacity decay along a curve)

```csharp
public sealed class CometTailEffect : AnimationEffect
{
    public Vector2[] Path { get; init; }   // ordered, head-to-tail
    public Color4 Color   { get; init; }
    public float Width    { get; init; } = 2f;

    public override void Render(RenderContext ctx, float t)
    {
        if (Path.Length < 2) return;
        // Each segment: opacity falls off from 1.0 (head) to 0 (tail), modulated by global t.
        float life = 1f - Easing.OutCubic(t);
        for (int i = 0; i < Path.Length - 1; i++)
        {
            float local = 1f - (float)i / (Path.Length - 1);
            float a = local * life;
            if (a <= 0.01f) continue;
            var c = new Color4(Color.Red, Color.Green, Color.Blue, a);
            using var b = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, c);
            ctx.RT.DrawLine(Path[i], Path[i+1], b, Width);
        }
    }
}
```

### 2.5 BrushCache + OnRenderTargetChanged Discipline

Per the official SharpDX rendering guide, **brushes must only be created in `OnRender()` or `OnRenderTargetChanged()`** — and the latter is where you create *long-lived* device resources. The render target itself is recreated when the chart resizes, switches GPU, or the user changes screens; any brush you held becomes invalid. Hence the `OnRenderTargetChanged` callback.

```csharp
public sealed class BrushCache : IDisposable
{
    private readonly Dictionary<Color4, SharpDX.Direct2D1.SolidColorBrush> _solids = new();
    private SharpDX.Direct2D1.RenderTarget _rt;

    public void Bind(SharpDX.Direct2D1.RenderTarget rt)
    {
        DisposeAll();
        _rt = rt;
    }

    public SharpDX.Direct2D1.SolidColorBrush Solid(Color4 c)
    {
        if (_rt == null || _rt.IsDisposed) return null;
        if (!_solids.TryGetValue(c, out var b) || b.IsDisposed)
        {
            b = new SharpDX.Direct2D1.SolidColorBrush(_rt, c);
            _solids[c] = b;
        }
        return b;
    }

    public void DisposeAll()
    {
        foreach (var kv in _solids) kv.Value?.Dispose();
        _solids.Clear();
    }

    public void Dispose() => DisposeAll();
}
```

In the indicator:

```csharp
private BrushCache _brushes = new();

protected override void OnRenderTargetChanged()
{
    _brushes.Bind(RenderTarget);
}

protected override void OnRender(ChartControl c, ChartScale s)
{
    var ctx = new RenderContext(RenderTarget, RenderTarget.Factory, _brushes,
                                new ChartContext(c, s, ChartBars, ChartPanel));
    _engine.RenderAll(ctx);
}
```

Animations that need a *changing* color per frame (pulse, fade) should keep using `using var` disposal — the cost of creating one `SolidColorBrush` per frame per effect is negligible (microseconds). The cache is for the static palette colors.

### 2.6 Skip-Frame vs Catch-Up Patterns

Two failure modes when the UI thread misses a deadline:

- **Skip:** The next `OnTick` accepts that 33 ms passed instead of 16, advances state by `dt` accordingly. Animations run at the right wall-clock speed; they just appear slightly less smooth. **This is the right default.**
- **Catch-up:** The pump tries to compensate by running multiple animation steps. Disastrous in trading UIs — produces visual stutter and adds CPU when CPU is already saturated.

The pump above uses `dt = now - _lastTick`, so it is a skip-frame design by construction. Don't try to be clever.

### 2.7 Batching: Compute Then Paint

A common mistake is to interleave state computation with paint inside `OnRender`. The right shape:

```
OnRender:
  1. ctx = build render context
  2. engine.RenderAll(ctx)         // all draws, no state mutation
  3. footprint.RenderCells(ctx)
  4. tooltip.RenderIfVisible(ctx)
```

Mutation (`engine.Advance`) happens *only* in the pump's `OnTick`. This way, every `OnRender` is fully deterministic given the current state, which makes the slow-frame logger meaningful.

---

## Part 3 — Mouse Interaction Deep-Dive

### 3.1 What's Exposed in NinjaScript

NT8 exposes mouse events differently for Indicators vs Drawing Tools:

**Drawing Tools** get the rich, chart-aware overrides directly:

```csharp
public override void OnMouseDown(ChartControl chartControl, ChartPanel chartPanel,
                                 ChartScale chartScale, ChartAnchor dataPoint) { }
public override void OnMouseUp  (ChartControl chartControl, ChartPanel chartPanel,
                                 ChartScale chartScale, ChartAnchor dataPoint) { }
public override void OnMouseMove(ChartControl chartControl, ChartPanel chartPanel,
                                 ChartScale chartScale, ChartAnchor dataPoint) { }
```

`ChartAnchor dataPoint` is *the entire chart-aware mouse position bundled for you*: `Time`, `Price`, and `SlotIndex` (nearest bar). This is the gift of working as a drawing tool.

**Indicators** do not receive these overrides natively — you must subscribe to the WPF events on `ChartPanel` (or `ChartControl`):

```csharp
protected override void OnStateChange()
{
    if (State == State.DataLoaded)
    {
        if (ChartPanel != null)
        {
            ChartPanel.MouseMove        += OnPanelMouseMove;
            ChartPanel.MouseDown        += OnPanelMouseDown;
            ChartPanel.MouseUp          += OnPanelMouseUp;
            ChartPanel.PreviewMouseWheel += OnPanelMouseWheel;
        }
    }
    else if (State == State.Terminated)
    {
        if (ChartPanel != null)
        {
            ChartPanel.MouseMove        -= OnPanelMouseMove;
            ChartPanel.MouseDown        -= OnPanelMouseDown;
            ChartPanel.MouseUp          -= OnPanelMouseUp;
            ChartPanel.PreviewMouseWheel -= OnPanelMouseWheel;
        }
    }
}
```

There is **no** `OnMouseDoubleClick` and **no** native `OnMouseClick` from NinjaTrader. You synthesize them with a small state machine on top of `MouseDown`/`MouseUp` (see §3.4).

### 3.2 Coordinate Conversion

Inside an indicator's WPF mouse handler, the event arg gives you a `Point` in WPF logical units relative to the panel. To go from there to chart-aware values:

```csharp
private void OnPanelMouseMove(object sender, System.Windows.Input.MouseEventArgs e)
{
    var p = e.GetPosition(ChartPanel);            // WPF units relative to panel
    int xPx = (int)p.X;
    int yPx = (int)p.Y;

    // Price (Y → value)
    double price = ChartScale.GetValueByY((int)p.Y);

    // Bar index from x. Use ChartBars to map.
    DateTime time = ChartControl.GetTimeByX((int)p.X);
    int barIdx    = ChartBars.GetBarIdxByX(ChartControl, (int)p.X);

    // Persist for next OnRender
    _hover.X         = xPx;
    _hover.Y         = yPx;
    _hover.Price     = price;
    _hover.Time      = time;
    _hover.BarIdx    = barIdx;
    _hover.IsPresent = true;

    ChartControl.Dispatcher.InvokeAsync(() => ForceRefresh());
}
```

DPI is generally already accounted for in the WPF event coordinates and `ChartPanel.X / W`. The one place you must care: when going **back** to absolute device coordinates for SharpDX, the `ChartPanel.X / Y / W / H` values are in device pixels (per the official SharpDX guide: "For full absolute device coordinates always use ChartPanel X, Y, W, H values"). Mixing logical and device pixels is the source of "my hit test is one cell off on a 4K monitor."

### 3.3 Hit Testing Footprint Cells

A hit test for a footprint cell needs the bar index, the price level row, and the cell rectangle:

```csharp
public bool TryHitCell(int xPx, int yPx, out FootprintHit hit)
{
    hit = default;
    if (xPx < ChartPanel.X || xPx > ChartPanel.X + ChartPanel.W) return false;
    if (yPx < ChartPanel.Y || yPx > ChartPanel.Y + ChartPanel.H) return false;

    int barIdx = ChartBars.GetBarIdxByX(ChartControl, xPx);
    if (barIdx < ChartBars.FromIndex || barIdx > ChartBars.ToIndex) return false;

    double price   = ChartScale.GetValueByY(yPx);
    double priceQ  = Instrument.MasterInstrument.RoundToTickSize(price);
    var bar        = _footprint.GetBar(barIdx);
    if (bar == null || !bar.Levels.TryGetValue(priceQ, out var lvl)) return false;

    hit = new FootprintHit
    {
        BarIdx   = barIdx,
        Price    = priceQ,
        BidVol   = lvl.Bid,
        AskVol   = lvl.Ask,
        CellRect = ComputeCellRect(barIdx, priceQ),
    };
    return true;
}
```

The `RoundToTickSize` step is mandatory — `GetValueByY` returns a continuous double; your footprint dictionary is keyed on tick-quantized prices.

### 3.4 Synthesizing Click and Double-Click

```csharp
private DateTime _lastDownAt;
private Point   _lastDownPt;
private const int ClickPxThreshold = 4;
private const int DoubleClickMs    = 350;

private void OnPanelMouseDown(object sender, MouseButtonEventArgs e)
{
    _lastDownAt = DateTime.UtcNow;
    _lastDownPt = e.GetPosition(ChartPanel);
    ChartPanel.CaptureMouse();
}

private void OnPanelMouseUp(object sender, MouseButtonEventArgs e)
{
    ChartPanel.ReleaseMouseCapture();

    var up   = e.GetPosition(ChartPanel);
    var dx   = System.Math.Abs(up.X - _lastDownPt.X);
    var dy   = System.Math.Abs(up.Y - _lastDownPt.Y);
    var held = (DateTime.UtcNow - _lastDownAt).TotalMilliseconds;

    if (dx + dy > ClickPxThreshold) { OnDrag(_lastDownPt, up); return; }

    if (_pendingClick != null && (DateTime.UtcNow - _pendingClick.At).TotalMilliseconds < DoubleClickMs)
    {
        OnDoubleClick(up, e.ChangedButton);
        _pendingClick = null;
    }
    else
    {
        _pendingClick = new ClickPending { At = DateTime.UtcNow, Pt = up, Btn = e.ChangedButton };
        // Fire single-click after the double-click window if no follow-up.
        ChartControl.Dispatcher.InvokeAsync(async () =>
        {
            await System.Threading.Tasks.Task.Delay(DoubleClickMs + 30);
            if (_pendingClick != null && (DateTime.UtcNow - _pendingClick.At).TotalMilliseconds >= DoubleClickMs)
            {
                OnSingleClick(_pendingClick.Pt, _pendingClick.Btn);
                _pendingClick = null;
            }
        });
    }
}
```

`CaptureMouse` is the often-forgotten ingredient. Without it, drags that exit the panel area lose subsequent `MouseMove` and `MouseUp` events — your drag never ends and you're left with a dangling state.

### 3.5 Hover State With Re-Render Triggering

Hover that changes the painted output must trigger re-render *only on actual position changes*, not every frame. Otherwise a stationary cursor still requests refreshes:

```csharp
private (int x, int y) _lastHoverPx = (-1, -1);

private void OnPanelMouseMove(object sender, MouseEventArgs e)
{
    var p = e.GetPosition(ChartPanel);
    var px = ((int)p.X, (int)p.Y);
    if (px == _lastHoverPx) return;       // no change → no work
    _lastHoverPx = px;

    UpdateHoverState(p);
    if (_hoverTooltip.NeedsRender) ChartControl.Dispatcher.InvokeAsync(ForceRefresh);
}
```

---

## Part 4 — Custom Drawing Tool With Full Interaction State Machine

Below is a complete, production-grade custom drawing tool that demonstrates the full DrawingState lifecycle, snap logic, multi-anchor management, constrained drawing (Shift = horizontal-only), and visual feedback per state.

```csharp
using System.Collections.Generic;
using System.Windows;
using System.Windows.Input;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.NinjaScript.DrawingTools;
using SharpDX;

namespace NinjaTrader.NinjaScript.DrawingTools
{
    public class FootprintZone : DrawingTool
    {
        public ChartAnchor StartAnchor { get; set; }
        public ChartAnchor EndAnchor   { get; set; }

        public Stroke OutlineStroke    { get; set; }
        public Brush  FillBrush        { get; set; }
        public bool   SnapToBarHL      { get; set; } = true;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name              = "Footprint Zone";
                DrawingState      = DrawingState.Building;
                IgnoresSnapping   = true; // we run our own snap

                StartAnchor = new ChartAnchor { IsEditing = true, DrawingTool = this };
                EndAnchor   = new ChartAnchor { IsEditing = true, DrawingTool = this };

                OutlineStroke = new Stroke(System.Windows.Media.Brushes.Cyan, 1.5f);
                FillBrush     = System.Windows.Media.Brushes.Cyan;
            }
            else if (State == State.Terminated)
            {
                OutlineStroke?.Dispose();
            }
        }

        public override IEnumerable<ChartAnchor> Anchors => new[] { StartAnchor, EndAnchor };

        // ---------- Mouse: build / edit / move ----------
        public override void OnMouseDown(ChartControl chartControl, ChartPanel chartPanel,
                                         ChartScale chartScale, ChartAnchor dataPoint)
        {
            switch (DrawingState)
            {
                case DrawingState.Building:
                    if (StartAnchor.IsEditing)
                    {
                        ApplySnap(dataPoint, chartControl, chartScale);
                        dataPoint.CopyDataValues(StartAnchor);
                        StartAnchor.IsEditing = false;
                        EndAnchor.IsEditing   = true;
                        // Stay in Building until the user clicks the second anchor.
                    }
                    else if (EndAnchor.IsEditing)
                    {
                        ApplySnap(dataPoint, chartControl, chartScale);
                        dataPoint.CopyDataValues(EndAnchor);
                        EndAnchor.IsEditing = false;
                        DrawingState = DrawingState.Normal;
                        IsSelected   = false;
                    }
                    break;

                case DrawingState.Normal:
                    var hit = HitTest(dataPoint, chartPanel, chartControl, chartScale);
                    if (hit == HitArea.StartHandle) { StartAnchor.IsEditing = true; DrawingState = DrawingState.Editing; }
                    else if (hit == HitArea.EndHandle) { EndAnchor.IsEditing = true; DrawingState = DrawingState.Editing; }
                    else if (hit == HitArea.Body)     { DrawingState = DrawingState.Moving; _moveOffset = ComputeMoveOffset(dataPoint); }
                    break;
            }
        }

        public override void OnMouseMove(ChartControl chartControl, ChartPanel chartPanel,
                                         ChartScale chartScale, ChartAnchor dataPoint)
        {
            ApplySnap(dataPoint, chartControl, chartScale);
            ApplyConstraints(dataPoint);

            if (DrawingState == DrawingState.Building && !StartAnchor.IsEditing && EndAnchor.IsEditing)
                dataPoint.CopyDataValues(EndAnchor);     // live preview of second anchor

            if (DrawingState == DrawingState.Editing)
            {
                if (StartAnchor.IsEditing) dataPoint.CopyDataValues(StartAnchor);
                else if (EndAnchor.IsEditing) dataPoint.CopyDataValues(EndAnchor);
            }

            if (DrawingState == DrawingState.Moving)
            {
                ApplyMove(dataPoint);
            }
        }

        public override void OnMouseUp(ChartControl chartControl, ChartPanel chartPanel,
                                       ChartScale chartScale, ChartAnchor dataPoint)
        {
            if (DrawingState == DrawingState.Editing)
            {
                StartAnchor.IsEditing = false;
                EndAnchor.IsEditing   = false;
                DrawingState = DrawingState.Normal;
            }
            else if (DrawingState == DrawingState.Moving)
            {
                DrawingState = DrawingState.Normal;
            }
        }

        // ---------- Snap ----------
        private void ApplySnap(ChartAnchor a, ChartControl chartControl, ChartScale chartScale)
        {
            if (!SnapToBarHL) return;

            // Snap to nearest bar's high or low (whichever is closer).
            int slot = a.SlotIndex;
            if (slot < ChartBars.FromIndex || slot > ChartBars.ToIndex) return;

            double high = ChartBars.Bars.GetHigh(slot);
            double low  = ChartBars.Bars.GetLow(slot);
            double pxH  = chartScale.GetYByValue(high);
            double pxL  = chartScale.GetYByValue(low);
            double pxA  = chartScale.GetYByValue(a.Price);

            const double SnapPx = 6.0;
            if (System.Math.Abs(pxA - pxH) < SnapPx) a.Price = high;
            else if (System.Math.Abs(pxA - pxL) < SnapPx) a.Price = low;
        }

        // ---------- Constraints (Shift = horizontal-only, Ctrl = vertical-only) ----------
        private void ApplyConstraints(ChartAnchor a)
        {
            var mods = Keyboard.Modifiers;
            if ((mods & ModifierKeys.Shift) == ModifierKeys.Shift && DrawingState == DrawingState.Building && EndAnchor.IsEditing)
            {
                // Lock end anchor's price to start anchor's.
                a.Price = StartAnchor.Price;
            }
            else if ((mods & ModifierKeys.Control) == ModifierKeys.Control && DrawingState == DrawingState.Building && EndAnchor.IsEditing)
            {
                a.Time = StartAnchor.Time;
                a.SlotIndex = StartAnchor.SlotIndex;
            }
        }

        // ---------- Hit testing ----------
        private enum HitArea { None, StartHandle, EndHandle, Body }

        private HitArea HitTest(ChartAnchor pt, ChartPanel panel, ChartControl c, ChartScale s)
        {
            double sx = c.GetXByTime(StartAnchor.Time);
            double sy = s.GetYByValue(StartAnchor.Price);
            double ex = c.GetXByTime(EndAnchor.Time);
            double ey = s.GetYByValue(EndAnchor.Price);
            double px = c.GetXByTime(pt.Time);
            double py = s.GetYByValue(pt.Price);

            const double Handle = 8.0;
            if (System.Math.Abs(px - sx) < Handle && System.Math.Abs(py - sy) < Handle) return HitArea.StartHandle;
            if (System.Math.Abs(px - ex) < Handle && System.Math.Abs(py - ey) < Handle) return HitArea.EndHandle;

            double minX = System.Math.Min(sx, ex), maxX = System.Math.Max(sx, ex);
            double minY = System.Math.Min(sy, ey), maxY = System.Math.Max(sy, ey);
            if (px >= minX && px <= maxX && py >= minY && py <= maxY) return HitArea.Body;
            return HitArea.None;
        }

        // ---------- Move ----------
        private (double dt, double dp) _moveOffset;
        private (double dt, double dp) ComputeMoveOffset(ChartAnchor pt)
            => ((pt.Time - StartAnchor.Time).TotalSeconds, pt.Price - StartAnchor.Price);

        private void ApplyMove(ChartAnchor pt)
        {
            var (dt0, dp0) = _moveOffset;
            var newStartT  = pt.Time.AddSeconds(-dt0);
            var newStartP  = pt.Price - dp0;
            var spanT      = (EndAnchor.Time - StartAnchor.Time).TotalSeconds;
            var spanP      = EndAnchor.Price - StartAnchor.Price;

            StartAnchor.Time  = newStartT;
            StartAnchor.Price = newStartP;
            EndAnchor.Time    = newStartT.AddSeconds(spanT);
            EndAnchor.Price   = newStartP + spanP;
        }

        // ---------- Render ----------
        public override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            float sx = (float)chartControl.GetXByTime(StartAnchor.Time);
            float sy = (float)chartScale.GetYByValue(StartAnchor.Price);
            float ex = (float)chartControl.GetXByTime(EndAnchor.Time);
            float ey = (float)chartScale.GetYByValue(EndAnchor.Price);
            var rect = new RawRectangleF(System.Math.Min(sx,ex), System.Math.Min(sy,ey),
                                         System.Math.Max(sx,ex), System.Math.Max(sy,ey));

            // Body fill 12% alpha
            var fillCol = FillBrush.ToDxColor4(); fillCol.Alpha = 0.12f;
            using (var b = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, fillCol))
                RenderTarget.FillRectangle(rect, b);

            // Outline
            var outlineCol = OutlineStroke.Brush.ToDxColor4();
            // Building/Editing → dotted preview, Normal → solid
            var dashStyle = (DrawingState == DrawingState.Building || DrawingState == DrawingState.Editing)
                ? new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Dash }
                : new SharpDX.Direct2D1.StrokeStyleProperties { DashStyle = SharpDX.Direct2D1.DashStyle.Solid };

            using (var ss = new SharpDX.Direct2D1.StrokeStyle(RenderTarget.Factory, dashStyle))
            using (var b  = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, outlineCol))
                RenderTarget.DrawRectangle(rect, b, OutlineStroke.Width, ss);

            // Handles (visible when selected, editing, or building)
            if (IsSelected || DrawingState != DrawingState.Normal)
                DrawHandles(sx, sy, ex, ey);
        }

        private void DrawHandles(float sx, float sy, float ex, float ey)
        {
            using var fill   = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(1,1,1,1));
            using var stroke = new SharpDX.Direct2D1.SolidColorBrush(RenderTarget, new Color4(0,0,0,1));

            void Handle(float x, float y)
            {
                var e = new SharpDX.Direct2D1.Ellipse(new Vector2(x, y), 5f, 5f);
                RenderTarget.FillEllipse(e, fill);
                RenderTarget.DrawEllipse(e, stroke, 1f);
            }

            Handle(sx, sy);
            Handle(ex, ey);
        }
    }
}
```

Key design points:

- `IgnoresSnapping = true` lets us replace NT8's snap with our own logic — cells, bar HL, price levels, custom grid — all per the docs (`ignoressnapping.htm`).
- `IsEditing` per anchor is the authoritative flag; `DrawingState` is the global state. Both are needed because while building, you have `state = Building` but only one of the anchors is the active edit target.
- The **Shift = horizontal-only** constraint reads `Keyboard.Modifiers` directly. `OnMouseMove` gets called on every move, so this is live.
- Dashed border during Building/Editing, solid in Normal — this is the visual contract that signals "this is being edited" vs "this is committed."
- Handles are drawn only when the tool is selected or being edited, keeping the chart clean when many zones exist.

---

## Part 5 — Keyboard Interaction

### 5.1 Subscription Pattern

Per NT8 forum guidance, key events go on `ChartPanel`:

```csharp
protected override void OnStateChange()
{
    if (State == State.DataLoaded)
    {
        if (ChartPanel != null)
        {
            ChartPanel.PreviewKeyDown += OnPanelKeyDown;
            ChartPanel.PreviewKeyUp   += OnPanelKeyUp;
            ChartPanel.Focusable       = true;
        }
    }
    else if (State == State.Terminated && ChartPanel != null)
    {
        ChartPanel.PreviewKeyDown -= OnPanelKeyDown;
        ChartPanel.PreviewKeyUp   -= OnPanelKeyUp;
    }
}
```

`Preview*` is preferred because it fires at the tunnel phase before NT8 routes the key to its native hotkey manager, giving you a chance to handle (and cancel) before built-in behavior runs.

### 5.2 Hotkey Discipline

Hard rules (informed by NT8 hotkey-manager guidance):

1. **Always require a modifier** — `Ctrl`, `Shift`, or `Alt`. Bare letter keys collide with NT8's native hotkeys (B = buy, S = sell, F = flatten, etc.). The only exception is function keys F1–F12, which NT8 mostly leaves alone.
2. **Document your bindings.** Surface them in a help overlay (Ctrl+? toggles a panel).
3. **Never intercept** Ctrl+Z (NT8 undo), Ctrl+S (save workspace), Ctrl+Tab (tab cycling), Esc (selection deselection).

### 5.3 Modifier-Driven Mode Switches

```csharp
private void OnPanelKeyDown(object sender, KeyEventArgs e)
{
    bool ctrl  = (Keyboard.Modifiers & ModifierKeys.Control) != 0;
    bool shift = (Keyboard.Modifiers & ModifierKeys.Shift)   != 0;
    bool alt   = (Keyboard.Modifiers & ModifierKeys.Alt)     != 0;

    if (ctrl && e.Key == Key.H) { _showHover = !_showHover; e.Handled = true; ForceRefresh(); }
    if (ctrl && e.Key == Key.M) { _muteAudio  = !_muteAudio;  e.Handled = true; }
    if (alt  && e.Key == Key.D) { _diagMode   = !_diagMode;   e.Handled = true; ForceRefresh(); }
}
```

Modifier-only state (Shift held = grid mode) is queried inline from `Keyboard.Modifiers` in mouse handlers — no event wiring needed.

---

## Part 6 — Tooltips With Hover Delay and Rich Content

The classic mistake: showing a tooltip on every `MouseMove`. The right pattern is a delayed-show / fast-hide model with rich content rendered via SharpDX inside `OnRender`.

```csharp
public sealed class HoverTooltip
{
    public bool IsVisible { get; private set; }
    public bool NeedsRender => IsVisible || _pending;

    private readonly TimeSpan _showDelay = TimeSpan.FromMilliseconds(200);
    private DateTime _enteredAt;
    private bool _pending;
    private Vector2 _anchor;
    private TooltipModel _model;
    private readonly DispatcherTimer _showTimer;

    public HoverTooltip()
    {
        _showTimer = new DispatcherTimer(DispatcherPriority.Render)
        { Interval = TimeSpan.FromMilliseconds(50) };
        _showTimer.Tick += (_, __) =>
        {
            if (_pending && (DateTime.UtcNow - _enteredAt) >= _showDelay)
            {
                _pending = false;
                IsVisible = true;
                _showTimer.Stop();
            }
        };
    }

    public void OnHoverEnter(Vector2 anchor, TooltipModel model)
    {
        _anchor    = anchor;
        _model     = model;
        _enteredAt = DateTime.UtcNow;
        _pending   = true;
        if (!IsVisible) _showTimer.Start();
    }

    public void OnHoverMove(Vector2 anchor, TooltipModel model)
    {
        if (model.IsSameTarget(_model))
        {
            _anchor = anchor;       // follow cursor
            return;
        }
        // Different target: reset delay timer.
        OnHoverEnter(anchor, model);
    }

    public void OnHoverExit()
    {
        IsVisible = false;
        _pending  = false;
        _showTimer.Stop();
    }

    public void Render(RenderContext ctx)
    {
        if (!IsVisible || _model == null) return;

        // Measure rich content
        var (w, h) = MeasureContent(ctx, _model);

        // Position-aware: avoid going off-screen (right edge / bottom edge)
        float x = _anchor.X + 14;
        float y = _anchor.Y + 14;
        float right  = ctx.Chart.PanelX + ctx.Chart.PanelW;
        float bottom = ctx.Chart.PanelY + ctx.Chart.PanelH;
        if (x + w > right)  x = _anchor.X - 14 - w;
        if (y + h > bottom) y = _anchor.Y - 14 - h;

        var rect = new RawRectangleF(x, y, x + w, y + h);

        // Shadow
        using (var shadow = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, new Color4(0,0,0,0.45f)))
        {
            var shadowRect = new RawRectangleF(rect.Left+2, rect.Top+3, rect.Right+2, rect.Bottom+3);
            ctx.RT.FillRoundedRectangle(new SharpDX.Direct2D1.RoundedRectangle { Rect = shadowRect, RadiusX = 6, RadiusY = 6 }, shadow);
        }
        // Background (solid dark, not gradient)
        using (var bg = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, new Color4(0.10f, 0.11f, 0.13f, 0.97f)))
            ctx.RT.FillRoundedRectangle(new SharpDX.Direct2D1.RoundedRectangle { Rect = rect, RadiusX = 6, RadiusY = 6 }, bg);
        // Border accent (signal color)
        using (var border = new SharpDX.Direct2D1.SolidColorBrush(ctx.RT, _model.AccentColor))
            ctx.RT.DrawRoundedRectangle(new SharpDX.Direct2D1.RoundedRectangle { Rect = rect, RadiusX = 6, RadiusY = 6 }, border, 1f);

        DrawContent(ctx, _model, x, y);
    }

    // ... MeasureContent / DrawContent draw labeled rows, mini sparkline, color-coded bid/ask volumes
}
```

Rich content patterns:
- **Multiple lines** — title row (bold), separator, value rows.
- **Color-coded values** — bid = blue, ask = red, delta = green/red sign.
- **Mini chart** — a small inline sparkline of the last N bars rendered via `SharpDX.PathGeometry`, alpha 0.6 to feel embedded.
- **Pin** — right-click the tooltip → context menu with "Pin this tooltip." Pinned tooltips persist after `MouseLeave` and can be dragged.

The 200 ms hover delay matters: it suppresses transient hovers as the cursor passes over data. Faster (≤100 ms) feels jittery; slower (≥400 ms) feels broken.

---

## Part 7 — Context Menu Builder

Per NT8 forum guidance, modifying the chart context menu is undocumented but stable. The pattern uses `ChartControl.ContextMenu.Items` and conditional add/remove on the menu's `Opening` event.

```csharp
public sealed class ContextMenuBuilder
{
    private readonly ChartControl _chart;
    private readonly List<MenuItem> _ours = new();
    private bool _hooked;

    public ContextMenuBuilder(ChartControl chart) { _chart = chart; }

    public void Hook(Func<IEnumerable<ContextItem>> itemFactory)
    {
        if (_hooked || _chart?.ContextMenu == null) return;
        _chart.ContextMenu.Opened += (_, __) =>
        {
            // Remove any prior items we added.
            foreach (var mi in _ours) _chart.ContextMenu.Items.Remove(mi);
            _ours.Clear();

            // Build new contextual items.
            var sep = new Separator();
            _chart.ContextMenu.Items.Add(sep);
            _ours.Add((MenuItem)null); // placeholder so we can find the separator? Use a parallel list.

            foreach (var item in itemFactory())
            {
                var mi = Build(item);
                _chart.ContextMenu.Items.Add(mi);
                _ours.Add(mi);
            }
        };
        _hooked = true;
    }

    private MenuItem Build(ContextItem c)
    {
        var mi = new MenuItem
        {
            Header     = c.Header,
            IsEnabled  = c.IsEnabled,
            Background = (SolidColorBrush)new BrushConverter().ConvertFrom("#1E2126"),
            Foreground = System.Windows.Media.Brushes.WhiteSmoke
        };
        if (c.Icon != null) mi.Icon = new System.Windows.Controls.Image { Source = c.Icon, Width = 14, Height = 14 };
        if (c.SubItems != null)
            foreach (var s in c.SubItems) mi.Items.Add(Build(s));
        else
            mi.Click += (_, __) => c.Action?.Invoke();
        return mi;
    }

    public sealed class ContextItem
    {
        public string Header { get; init; }
        public bool   IsEnabled { get; init; } = true;
        public ImageSource Icon { get; init; }
        public Action Action    { get; init; }
        public IEnumerable<ContextItem> SubItems { get; init; }
    }
}
```

Usage:

```csharp
_ctxMenu = new ContextMenuBuilder(ChartControl);
_ctxMenu.Hook(() =>
{
    var items = new List<ContextMenuBuilder.ContextItem>
    {
        new() { Header = "Pin tooltip here", Action = () => _tooltip.Pin(_lastHoverPx) }
    };

    // Conditional: only show "Cancel order" when an order rests at this price
    if (_orderRouter.HasOrderNear(_hover.Price, withinTicks: 1))
    {
        items.Add(new() { Header = "Cancel order at this price", Action = () => _orderRouter.CancelNear(_hover.Price) });
    }

    items.Add(new()
    {
        Header   = "Mark zone",
        SubItems = new[]
        {
            new ContextMenuBuilder.ContextItem { Header = "Demand",  Action = () => MarkZone(ZoneKind.Demand) },
            new ContextMenuBuilder.ContextItem { Header = "Supply",  Action = () => MarkZone(ZoneKind.Supply) },
            new ContextMenuBuilder.ContextItem { Header = "Neutral", Action = () => MarkZone(ZoneKind.Neutral) },
        }
    });

    return items;
});
```

Styling note: NT8's default WPF context menu inherits a gray gradient. Override the `Background` and `Foreground` per item to keep the dark theme. For full parity with the rest of the design system, attach a `Style` resource that overrides `MenuItem.Template`.

---

## Part 8 — Notification Toast System

Toasts live in a top-most transparent `Window` overlaying the chart's host. They slide in from the corner, auto-dismiss, and can carry actions.

```csharp
public enum ToastPriority { Info, Warning, Critical }

public sealed class ToastManager
{
    private readonly Window _host;
    private readonly StackPanel _stack;
    private const double Width = 320;

    public ToastManager(Window owner)
    {
        _host = new Window
        {
            Owner                 = owner,
            WindowStyle           = WindowStyle.None,
            AllowsTransparency    = true,
            Background            = System.Windows.Media.Brushes.Transparent,
            ShowInTaskbar         = false,
            Topmost               = true,
            ResizeMode            = ResizeMode.NoResize,
            SizeToContent         = SizeToContent.Height,
            Width                 = Width + 24,
            Focusable             = false,
            IsHitTestVisible      = true
        };
        _stack = new StackPanel { Margin = new Thickness(12) };
        _host.Content = _stack;
        _host.Loaded += (_, __) => RepositionToTopRight(owner);
        owner.LocationChanged += (_, __) => RepositionToTopRight(owner);
        owner.SizeChanged     += (_, __) => RepositionToTopRight(owner);
        _host.Show();
    }

    private void RepositionToTopRight(Window owner)
    {
        _host.Left = owner.Left + owner.ActualWidth - _host.Width  - 16;
        _host.Top  = owner.Top  + 48;
    }

    public void Show(string title, string body, ToastPriority p = ToastPriority.Info,
                     TimeSpan? life = null, IEnumerable<(string label, Action act)> actions = null,
                     string soundFile = null)
    {
        life ??= TimeSpan.FromMilliseconds(p == ToastPriority.Critical ? 8000
                                          : p == ToastPriority.Warning ? 5000 : 3500);

        var toast = BuildToast(title, body, p, actions);
        _stack.Children.Insert(0, toast); // newest on top

        // Slide-in animation: TranslateTransform.X 24 → 0 over 280ms, Material Emphasized
        var tt = new TranslateTransform(24, 0);
        toast.RenderTransform = tt;
        toast.Opacity = 0;

        var slide = new System.Windows.Media.Animation.DoubleAnimation(24, 0, TimeSpan.FromMilliseconds(280))
        { EasingFunction = new System.Windows.Media.Animation.CubicEase { EasingMode = System.Windows.Media.Animation.EasingMode.EaseOut } };
        var fade  = new System.Windows.Media.Animation.DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(220));
        tt.BeginAnimation(TranslateTransform.XProperty, slide);
        toast.BeginAnimation(UIElement.OpacityProperty, fade);

        if (!string.IsNullOrEmpty(soundFile))
            try { NinjaTrader.NinjaScript.Indicators.Indicator.PlaySound(soundFile); } catch { }

        // Auto-dismiss
        var dismiss = new DispatcherTimer { Interval = life.Value };
        dismiss.Tick += (_, __) => { dismiss.Stop(); Dismiss(toast); };
        dismiss.Start();
    }

    private void Dismiss(FrameworkElement toast)
    {
        var fade = new System.Windows.Media.Animation.DoubleAnimation(toast.Opacity, 0, TimeSpan.FromMilliseconds(180));
        fade.Completed += (_, __) => _stack.Children.Remove(toast);
        toast.BeginAnimation(UIElement.OpacityProperty, fade);
    }

    private FrameworkElement BuildToast(string title, string body, ToastPriority p,
                                        IEnumerable<(string label, Action act)> actions)
    {
        var border = new Border
        {
            Background      = (SolidColorBrush)new BrushConverter().ConvertFrom("#15181D"),
            BorderBrush     = AccentFor(p),
            BorderThickness = new Thickness(0, 0, 0, 0),
            CornerRadius    = new CornerRadius(8),
            Margin          = new Thickness(0, 0, 0, 8),
            Padding         = new Thickness(14, 12, 14, 12),
            Effect          = new System.Windows.Media.Effects.DropShadowEffect
            { BlurRadius = 12, ShadowDepth = 2, Color = Colors.Black, Opacity = 0.55 }
        };

        var grid = new Grid();
        grid.RowDefinitions.Add(new RowDefinition());
        grid.RowDefinitions.Add(new RowDefinition());

        // Left accent bar
        var accent = new Rectangle { Width = 3, Fill = AccentFor(p), HorizontalAlignment = HorizontalAlignment.Left };
        grid.Children.Add(accent);

        var stack = new StackPanel { Margin = new Thickness(12, 0, 0, 0) };
        stack.Children.Add(new TextBlock { Text = title, Foreground = Brushes.WhiteSmoke, FontWeight = FontWeights.SemiBold, FontSize = 13 });
        stack.Children.Add(new TextBlock { Text = body, Foreground = (SolidColorBrush)new BrushConverter().ConvertFrom("#B7BDC9"), FontSize = 12, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0,2,0,0) });

        if (actions != null)
        {
            var btns = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 8, 0, 0) };
            foreach (var (label, act) in actions)
            {
                var b = new Button
                {
                    Content = label, Margin = new Thickness(0, 0, 8, 0), Padding = new Thickness(10, 4, 10, 4),
                    Background = Brushes.Transparent, Foreground = AccentFor(p), BorderBrush = AccentFor(p), Cursor = Cursors.Hand
                };
                b.Click += (_, __) => act?.Invoke();
                btns.Children.Add(b);
            }
            stack.Children.Add(btns);
        }

        grid.Children.Add(stack);
        border.Child = grid;
        return border;
    }

    private static SolidColorBrush AccentFor(ToastPriority p) => p switch
    {
        ToastPriority.Critical => (SolidColorBrush)new BrushConverter().ConvertFrom("#FF3D3D"),
        ToastPriority.Warning  => (SolidColorBrush)new BrushConverter().ConvertFrom("#FFB23D"),
        _                       => (SolidColorBrush)new BrushConverter().ConvertFrom("#3DB3FF"),
    };
}
```

Usage:

```csharp
_toasts = new ToastManager(Window.GetWindow(ChartControl));

_toasts.Show(
    title: "ABSORPTION @ 17,432.50",
    body:  "Bid 1,200 contracts in 1.4s. Confidence 0.87.",
    p:     ToastPriority.Warning,
    actions: new[] { ("View", () => _tooltip.Pin(...)), ("Mute", () => _muteSignal = true) },
    soundFile: NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert3.wav");
```

Critical UX rules:
- **Stack, don't replace.** Newer on top. Cap at 5 visible — overflow into a hidden history panel.
- **Critical priority gets a longer life and audio.** Info gets neither.
- **Actions inside the toast** are mandatory for any signal that has a follow-up choice. "Cancel order" / "Flatten" / "Mute this signal."
- **Never block input** (`IsHitTestVisible = true` only for the toast surface; the host window is `WindowStyle = None` and topmost but doesn't steal keyboard focus — `Focusable = false`).

---

## Part 9 — Audio Feedback (Sonification)

NT8 ships `PlaySound(string wavPath)` (per `playsound.htm`). Built-in sounds live at `NinjaTrader.Core.Globals.InstallDir + @"\sounds\"`. Custom sounds can be loaded from any path.

```csharp
public sealed class SoundRouter
{
    private readonly Dictionary<string, DateTime> _lastPlayed = new();
    private readonly TimeSpan _minGap = TimeSpan.FromMilliseconds(300);
    public bool   Muted          { get; set; }
    public double VolumeScalar   { get; set; } = 1.0;

    public void Play(string path, double signalStrength = 1.0)
    {
        if (Muted) return;
        if (signalStrength * VolumeScalar < 0.15) return;       // suppress weak signals

        if (_lastPlayed.TryGetValue(path, out var t) && DateTime.UtcNow - t < _minGap) return;
        _lastPlayed[path] = DateTime.UtcNow;

        try { Indicator.PlaySound(path); } catch { /* sound subsystem busy */ }
    }

    // For per-signal mapping
    public string Resolve(SignalKind k) => k switch
    {
        SignalKind.Absorption  => Globals.InstallDir + @"\sounds\Alert4.wav",
        SignalKind.Exhaustion  => Globals.InstallDir + @"\sounds\Alert3.wav",
        SignalKind.OrderFilled => Globals.InstallDir + @"\sounds\Alert1.wav",
        _ => Globals.InstallDir + @"\sounds\Alert2.wav"
    };
}
```

`PlaySound` doesn't expose volume, panning, or DSP. For richer behavior — strength-modulated volume, spatial L/R for buy/sell, sustained CVD tones — drop down to NAudio inside an Add-On. NT8's threading rules apply: instantiate the sound device on the UI thread, post buffers from background.

Spatial CVD example (conceptual):

```csharp
// Continuous tone, frequency = mapped CVD value, pan = sign of CVD
// Updated on the same cadence as DOM changes (throttled to 50 ms)
_cvdToneEngine.SetFrequency(BaseHz + Math.Abs(cvd) * Sensitivity);
_cvdToneEngine.SetPan(Math.Sign(cvd) * Math.Min(1, Math.Abs(cvd) / Range));
```

When to use audio vs visual flash:
- **Audio for off-screen events.** The trader is looking at a different chart or a different window. A flash on a hidden chart helps no one; a sound carries.
- **Visual flash for on-screen events.** Audio for things the user is already looking at is noise.
- **Both for critical events.** Order filled, stop hit, daily loss limit reached.
- **Hard rule: never play more than 1 sound per 300 ms.** The router enforces this. A burst of 10 absorption signals should produce one *audible* event, not ten overlapping wavs.

---

## Part 10 — Haptic Patterns (XInput)

For traders who monitor multiple charts silently (open office, video calls), an Xbox controller plugged into USB makes a serviceable vibration peripheral. `XInputDotNet` (pure C#, no native dependency) is the cleanest path.

```csharp
public sealed class HapticChannel
{
    private readonly int _pad;       // 0..3
    private CancellationTokenSource _cts;

    public HapticChannel(int pad = 0) { _pad = pad; }

    public void Pulse(double strength01, TimeSpan dur)
    {
        Cancel();
        _cts = new CancellationTokenSource();
        var tok = _cts.Token;
        Task.Run(async () =>
        {
            try
            {
                ushort lo = (ushort)(strength01 * 0.6 * 0xFFFF); // low-frequency motor (deeper)
                ushort hi = (ushort)(strength01 * 0.9 * 0xFFFF); // high-frequency motor (sharper)
                XInputDotNetPure.GamePad.SetVibration((XInputDotNetPure.PlayerIndex)_pad, lo / 65535f, hi / 65535f);
                await Task.Delay(dur, tok);
            }
            catch (TaskCanceledException) { }
            finally
            {
                XInputDotNetPure.GamePad.SetVibration((XInputDotNetPure.PlayerIndex)_pad, 0, 0);
            }
        }, tok);
    }

    public void Pattern(double strength01, params int[] msPattern)
    {
        Cancel();
        _cts = new CancellationTokenSource();
        var tok = _cts.Token;
        Task.Run(async () =>
        {
            try
            {
                bool on = true;
                ushort lo = (ushort)(strength01 * 0.6 * 0xFFFF);
                ushort hi = (ushort)(strength01 * 0.9 * 0xFFFF);
                foreach (var ms in msPattern)
                {
                    if (on) XInputDotNetPure.GamePad.SetVibration((XInputDotNetPure.PlayerIndex)_pad, lo / 65535f, hi / 65535f);
                    else    XInputDotNetPure.GamePad.SetVibration((XInputDotNetPure.PlayerIndex)_pad, 0, 0);
                    await Task.Delay(ms, tok);
                    on = !on;
                }
            }
            finally { XInputDotNetPure.GamePad.SetVibration((XInputDotNetPure.PlayerIndex)_pad, 0, 0); }
        }, tok);
    }

    public void Cancel() => _cts?.Cancel();
}
```

Pattern catalog:
- **Soft tick** (info): `Pulse(0.25, 60ms)`.
- **Signal** (warning): `Pattern(0.5, 80, 60, 80)` — two short bursts.
- **Critical** (order rejected, daily loss limit): `Pattern(0.9, 200, 100, 200, 100, 200)` — three long.
- **Confidence-modulated**: scale strength by signal confidence.

---

## Part 11 — Loading States and Empty States

### 11.1 Skeleton Shimmer (during Rithmic connection)

```csharp
public sealed class ShimmerEffect : AnimationEffect
{
    public RawRectangleF Rect { get; init; }
    public Color4 Base        { get; init; } = new(0.18f, 0.20f, 0.24f, 1f);
    public Color4 Highlight   { get; init; } = new(0.30f, 0.33f, 0.40f, 1f);

    public override void Render(RenderContext ctx, float t)
    {
        // Gradient sweep from left to right, looped.
        float phase = (Environment.TickCount % 1500) / 1500f;
        var x0 = Rect.Left + (Rect.Right - Rect.Left) * (phase - 0.3f);
        var x1 = Rect.Left + (Rect.Right - Rect.Left) * (phase + 0.3f);

        using var stops = new SharpDX.Direct2D1.GradientStopCollection(ctx.RT, new[]
        {
            new SharpDX.Direct2D1.GradientStop { Position = 0f, Color = Base },
            new SharpDX.Direct2D1.GradientStop { Position = 0.5f, Color = Highlight },
            new SharpDX.Direct2D1.GradientStop { Position = 1f, Color = Base },
        });
        var props = new SharpDX.Direct2D1.LinearGradientBrushProperties
        { StartPoint = new Vector2(x0, Rect.Top), EndPoint = new Vector2(x1, Rect.Bottom) };
        using var brush = new SharpDX.Direct2D1.LinearGradientBrush(ctx.RT, props, stops);
        ctx.RT.FillRectangle(Rect, brush);
    }
}
```

Use this while waiting for `Rithmic.ConnectionStatus == Connected`. Active shimmer signals "the system is alive, just waiting." A static gray box looks broken.

### 11.2 Empty State (Signal Monitor with no signals firing)

Don't draw nothing. Draw:
- A muted icon (e.g., a faint waveform) at 18% alpha, centered.
- A label: "Awaiting signal · Last signal 14 min ago".
- The countdown live-updates each second (Linear easing).

This gives the trader negative information ("no signal") with positive design ("system is healthy and watching").

### 11.3 Disconnected Error State

- Red border breathe at the chart edge (`BreatheEffect` with red, 2.4s period).
- A persistent (non-auto-dismissing) toast at top-right with "Rithmic disconnected — retrying in 4s..." and a "Retry now" button.
- Audio: single soft `Alert2.wav`. Don't loop.

---

## Part 12 — Touch / Pen / Gesture (Surface, Cintiq)

NT8 inherits WPF touch handling. Subscribe to `ChartPanel.ManipulationDelta` for two-finger pan/pinch:

```csharp
ChartPanel.IsManipulationEnabled = true;

ChartPanel.ManipulationDelta += (s, e) =>
{
    if (e.DeltaManipulation.Scale.X != 1.0)
    {
        // Pinch → adjust visible bar count
        double scale = e.DeltaManipulation.Scale.X;
        AdjustVisibleBars(scale);
    }
    if (Math.Abs(e.DeltaManipulation.Translation.X) > 0)
    {
        // Two-finger pan
        ScrollHorizontal((int)e.DeltaManipulation.Translation.X);
    }
    e.Handled = true;
};
```

For pen pressure (Cintiq drawing tool), `StylusInAirMove` and `StylusDown` give pressure via `StylusPoint.PressureFactor` (0..1). Scale drawing tool stroke width by pressure for a natural drawing feel.

Note: NT8 does not expose these as overrides; you must hook the WPF events on `ChartPanel`. Test on the actual touch hardware — emulators lie.

---

## Part 13 — When to Build vs Use a Library

| Library | Purpose | Use in NT8? | Why / Why not |
|---|---|---|---|
| Rive runtime | Vector + skeletal animation | No (in NT8 chart) | Adds runtime dependency, designed for game UI. Use for the *web dashboard* if you want After Effects-quality flourishes — never inside NT8 OnRender. |
| Lottie | After Effects → JSON, web/mobile | Web dashboard only | Same reasoning. Lottie's renderer is not for SharpDX. |
| WPF Storyboards / DoubleAnimation | Built-in WPF animation | Use for WPF-side UI (toasts, tooltips on UserControlCollection) | Native, zero-cost, integrates with the WPF tree. Don't use for SharpDX-rendered chart content — use the AnimationEngine pattern above. |
| ToastNotifications / Notifications.Wpf | WPF toast libraries | Optional | Faster start, but dependency conflicts with NT8 are common. Custom toast (Part 8) is ~150 LOC and you control the styling. |
| XInputDotNet | Game controller wrapper | Yes | Pure C#, single file, MIT. |

**The right default for everything chart-rendered: build it yourself, small and surgical.** A 600-line custom AnimationEngine that knows about your effect types out-renders any general-purpose library because it skips the abstraction layers that don't apply.

---

## Part 14 — Anti-Pattern Catalog

**Animation anti-patterns.** Each line below is a real pattern people ship; don't.

1. **Animating during a fast tape.** When ticks are arriving every 50 ms and your animation is also requesting 60 fps refreshes, `OnRender` becomes a critical-section bottleneck. Solution: an "intensity" governor that disables non-critical animations when `dt(OnBarUpdate) < 100ms`.
2. **Long animations.** Anything > 600 ms feels slow on a chart. Cap at 500 ms for transients, 280 ms for entries.
3. **Bouncy easing in trading contexts.** `easeOutBack`, `easeOutElastic`, `easeOutBounce` look playful. They're wrong for institutional UI. Reserve them for empty states.
4. **Carousel-style loops.** Anything that visually translates content past the eye repeatedly induces motion sickness in long sessions. No marquee scrolls. No spinning loaders longer than 1 second.
5. **More than 3 simultaneous animations in the live data area.** Cognitive load spikes nonlinearly. The engine should suppress/queue when above 3 active.
6. **Pulsing UI used as a liveness indicator.** A blinking dot saying "connected" is the worst possible UX — the trader's brain will start filtering it out. Use steady-state colors with breathe only on *new* events.
7. **Animating the price line itself.** Never. The price is the truth; smoothing it lies.
8. **Using `Dispatcher.Invoke` (sync) instead of `InvokeAsync`.** Will deadlock on script load per the multi-threading guide. Always async.
9. **Allocating brushes inside `OnRender` per cell.** A 50-cell footprint × 60 fps = 3,000 brush allocs/sec. Use `BrushCache`.
10. **Forgetting `OnRenderTargetChanged` brush rebinding.** First chart resize → all your cached brushes reference a dead render target → crash.
11. **Calling `ForceRefresh` from a tight loop.** Floods the render queue. The pump pattern (Part 1) calls it at most once per 16 ms.
12. **Tooltips on every `MouseMove`.** Use the 200 ms hover delay (Part 6).
13. **Audio without rate-limiting.** A burst of signals = wall of noise. The 300 ms minimum gap in `SoundRouter` is non-negotiable.
14. **Toasts that auto-dismiss critical events.** Critical = persistent until dismissed. Info = 3.5 s. Warning = 5 s.
15. **Mouse capture without release.** Forgetting `ReleaseMouseCapture` after a drag locks the chart. Always release in `MouseUp`, even on early-return paths.
16. **Custom drawing tools without `IgnoresSnapping`.** Snap fights between NT8 and your code produce hard-to-debug jitter. Set `IgnoresSnapping = true` and own it.
17. **Rendering off-screen content.** Cull with `ChartBars.FromIndex`/`ToIndex` before any draw call. The cheapest pixel is the one you don't paint.

---

## Part 15 — Performance Budget Tables

### Per-Frame Budget (60 fps target)

| Phase | Budget | Notes |
|---|---|---|
| Animation state advance     | 0.5 ms | <100 active effects |
| Footprint cells render      | 4.0 ms | ~50 visible bars × ~30 levels |
| Animations render           | 2.0 ms | ≤8 simultaneous |
| Tooltip render              | 0.5 ms | Skip if not visible |
| Headroom                    | 3.5 ms | OS, GC, jitter |
| **Total**                   | **10.5 ms** | leaves margin under 16.67 ms vsync |

### Effect Cost Reference

| Effect | Approx cost / frame | Cap |
|---|---|---|
| `PulseEffect`           | 0.05 ms | unlimited |
| `FlashFadeEffect`       | 0.04 ms | unlimited |
| `SlideInEffect`         | 0.08 ms | <8 simultaneous |
| `ColorCrossfadeEffect`  | 0.04 ms | unlimited |
| `NumberTickEffect`      | 0.10 ms | DrawText is expensive — pool TextLayouts if >10 |
| `BreatheEffect`         | 0.05 ms | <4 simultaneous |
| `GlowEffect`            | 0.30 ms | <3 simultaneous (radial gradient) |
| `CometTailEffect`       | 0.20 ms × N segments | use only on hover |
| `ShimmerEffect`         | 0.15 ms | use only during loading |

### Refresh Cadence Recommendations

| Indicator state | Pump interval |
|---|---|
| Idle (no animations, no hover) | Disabled |
| Hover only                     | 33 ms |
| Active animations (≤3)         | 16 ms |
| Active drag                    | 16 ms |
| Active animations (>3)         | 33 ms with intensity governor |
| Chart hidden (`!IsVisible`)    | Disabled |

---

## Part 16 — Closing Checklist for the Graphics Agent

When generating any NT8 visual, verify:

1. The indicator/tool overrides `OnRenderTargetChanged` and binds the `BrushCache`.
2. All SharpDX `IDisposable` resources (brush, gradient, geometry, text format) are disposed via `using` or in `OnRenderTargetChanged`.
3. Animation effects are added through `AnimationEngine.Enqueue` only (never instantiated inside `OnRender`).
4. `ChartControl.Dispatcher.InvokeAsync` is used for all UI work originating from background threads. Never `Dispatcher.Invoke` (sync).
5. Mouse capture is paired with release (no early-return leaks).
6. Drawing tools set `IgnoresSnapping = true` if they implement custom snap.
7. Tooltip uses 200 ms hover delay, not immediate show.
8. Toasts of `Critical` priority do not auto-dismiss; `Warning` and `Info` do.
9. Audio router enforces ≥300 ms gap between consecutive sounds.
10. Animation pump short-circuits when `!ChartControl.IsVisible`.
11. No animation duration exceeds 500 ms (transients) or 280 ms (entries).
12. `ChartBars.FromIndex` / `ToIndex` is consulted before any per-bar draw loop.
13. Slow-frame logger fires only above an 8 ms threshold (no noisy Print storms).
14. All easing falls back to `OutCubic` / `OutExpo` / `MaterialStandard` / `Linear`. No `easeOutElastic`/`easeOutBack` outside empty states.

This is the contract. Anything outside it should be defended as a deliberate exception.

---

## Sources

- [NinjaScript: ForceRefresh()](https://ninjatrader.com/support/helpguides/nt8/forcerefresh.htm)
- [NinjaScript: Using SharpDX for Custom Chart Rendering](https://ninjatrader.com/support/helpguides/nt8/using_sharpdx_for_custom_chart_rendering.htm)
- [NinjaScript: OnRenderTargetChanged()](https://ninjatrader.com/support/helpguides/nt8/onrendertargetchanged.htm)
- [NinjaScript: DrawingState](https://ninjatrader.com/support/helpguides/nt8/drawingstate.htm)
- [NinjaScript: ChartAnchor](https://ninjatrader.com/support/helpguides/nt8/chartanchor.htm)
- [NinjaScript: OnMouseDown() / OnMouseMove()](https://ninjatrader.com/support/helpguides/nt8/onmousedown.htm)
- [NinjaScript: IgnoresSnapping](https://ninjatrader.com/support/helpGuides/nt8/ignoressnapping.htm)
- [NinjaScript: IsSuspendedWhileInactive](https://ninjatrader.com/support/helpguides/nt8/issuspendedwhileinactive.htm)
- [NinjaScript: Multi-Threading Considerations](https://ninjatrader.com/support/helpguides/nt8/multi-threading.htm)
- [NinjaScript: UserControlCollection](https://ninjatrader.com/support/helpguides/nt8/usercontrolcollection.htm)
- [NinjaScript: PlaySound()](https://ninjatrader.com/support/helpGuides/nt8/playsound.htm)
- [NinjaScript: Creating Chart WPF UI Modifications from an Indicator](https://ninjatrader.com/support/helpguides/nt8/creating-chart-wpf-(ui)-modifi.htm)
- [NT Forum: Make chart refresh rate faster than 250ms](https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/99562-make-chart-refresh-rate-faster-than-250ms-possible/page5)
- [NT Forum: ChartControl.Dispatcher.InvokeAsync](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1330597-chartcontrol-dispatcher-invokeasync)
- [NT Forum: Indicators, Threads and Dispatchers](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1228731-indicators-threads-and-dispatchers)
- [NT Forum: Best way to dispose of a SharpDX brush](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1305459-best-way-to-dispose-of-a-sharpdx-brush-used-in-a-list)
- [NT Forum: Disposing a stroke's BrushDX properly](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1086146-disposing-a-stroke-s-brushdx-properly)
- [NT Forum: Force Snap mode to price in custom drawing tool](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1039416-force-snap-mode-to-price-in-custom-drawing-tool)
- [NT Forum: Adding tooltips on hover](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/97694-adding-tooltips-on-hover)
- [NT Forum: Hack Alert: Show tooltip on drawing object](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/99636-hack-alert-show-tooltip-on-drawing-object-kinda-sorta)
- [NT Forum: Add MenuItem within MenuItem in ContextMenu](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1270561-add-menuitem-within-menuitem-in-contextmenu)
- [NT Forum: Drawing Tool Context Menu Handler](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1178711-drawing-tool-context-menu-handler-with-global-drawing-objects)
- [NT Forum: How to get the time and price of mouse point clicked](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/92601-how-to-get-the-time-and-price-of-mouse-point-clicked-on-chart)
- [NT Forum: Is there a virtual OnMouseClick handler?](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1103329-is-there-a-virtual-onmouseclick-handler)
- [NT Forum: KeyDown listener using Alt modifier](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1233100-keydown-listener-using-alt-modifier-that-s-assigned-to-a-order-hot-key)
- [NT Forum: Using hotkeys to run custom strategies](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1217908-using-hotkeys-to-run-custom-strategies-and-or-scripts)
- [Microsoft: WPF Easing Functions](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/graphics-multimedia/easing-functions)
- [Microsoft: How to Render on a Per Frame Interval Using CompositionTarget](https://learn.microsoft.com/en-us/dotnet/desktop/wpf/graphics-multimedia/how-to-render-on-a-per-frame-interval-using-compositiontarget)
- [Material Design 1: Duration & Easing](https://m1.material.io/motion/duration-easing.html)
- [Material Design 3: Easing and Duration Tokens](https://m3.material.io/styles/motion/easing-and-duration/tokens-specs)
- [Easings.net Cheat Sheet](https://easings.net/)
- [GitHub: dalance/D2dControl (SharpDX + WPF)](https://github.com/dalance/D2dControl)
- [GitHub: speps/XInputDotNet](https://github.com/speps/XInputDotNet)
- [GitHub: rafallopatka/ToastNotifications](https://github.com/rafallopatka/ToastNotifications)
- [GitHub: Federerer/Notifications.Wpf](https://github.com/Federerer/Notifications.Wpf)
- [tradingdj.com: How to Make a Sound Alert in NinjaTrader 8](https://blog.tradingdj.com/how-to-make-a-sound-alert-in-ninjatrader-8/)
