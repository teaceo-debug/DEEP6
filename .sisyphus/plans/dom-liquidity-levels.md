# DEEP6 Liquidity Levels — DOM-Based Auto S/R Indicator for NinjaTrader 8

## TL;DR

> **Quick Summary**: Build a single ultra-lightweight NinjaTrader 8 indicator (`DEEP6LiquidityLevels.cs`) that consumes real-time Level 2 DOM data, auto-detects the top 3-5 largest liquidity walls on each side (bid/ask), and renders them as horizontal lines + zone bands on the chart overlay. NQ-optimized. Must survive NY open volatility without freezing.
> 
> **Deliverables**:
> - `DEEP6LiquidityLevels.cs` — Single NinjaScript indicator file (~400-500 lines)
> - Built-in performance profiling (render time + callback rate logged to Output window)
> - Deployed to NT8, compiled, visually verified on NQ chart
> 
> **Estimated Effort**: Short (single indicator file, well-defined scope)
> **Parallel Execution**: YES — 2 waves + final verification
> **Critical Path**: Task 1 (build) → Task 2 (deploy+compile) → Task 3 (visual QA) → Task 4 (performance verification) → Final Verification

---

## Context

### Original Request
User wants a DOM heatmap "like BestOrderFlow and Tholvi Trader" but only cares about speed, accuracy, and the levels — not the full heatmap visual. After discussion, refined to: auto-detected S/R lines from DOM depth, not a pixel-level heatmap at all.

### Data Source: Rithmic via NT8 Connection
**Confirmed**: Data source is **Rithmic**, accessed through NinjaTrader 8's native connection.
- `OnMarketDepth()` in NT8 automatically routes Level 2 data from whichever provider is connected — when NT8 is connected to Rithmic, it delivers Rithmic's full DOM feed (40+ levels per side)
- **No Rithmic-specific code needed in the indicator** — NT8 abstracts the data provider
- **Prerequisite**: Rithmic connection must be active in NT8 with Level 2 Market Depth enabled (Connections → Rithmic → Market Data subscription must include depth)
- **MNQ note**: Rithmic delivers MNQ depth separately from NQ — if user is on MNQ chart, `OnMarketDepth()` receives MNQ depth. Indicator is NQ-optimized but works on MNQ via dynamic TickSize
- **Rithmic L2 depth**: Rithmic provides up to 40 levels per side via their R|Protocol feed. NT8 exposes these via `MarketDepthEventArgs.Position` (0 = best bid/ask, up to 39)

### Interview Summary
**Key Discussions**:
- Existing DEEP6 heatmap indicators (DOMHeatMap, MBOHeatMap, LiquidityHeatMap) all freeze during high volatility — rebuild fresh
- User wants ONLY the auto-detected levels, not the heatmap visualization
- Dynamic/live behavior — levels appear/disappear as DOM liquidity changes
- Top N by volume — always show the biggest 3-5 walls per side
- Visual: thin centerline + semi-transparent zone band + volume label
- Bid/ask separated by color (bid = cyan/blue, ask = magenta/red)
- NQ-optimized (0.25 tick size, NQ volume ranges)
- Chart overlay rendering

**Research Findings**:
- Existing DEEP6DOMHeatMap.cs is thread-UNSAFE (no locks on heat arrays, but also no snapshot isolation) — root cause of freezes
- DEEP6Footprint.cs uses lock + deep-clone + volatile for dictionary-based data — NOT the pattern for this indicator (we use pre-allocated arrays with atomic long access on x64, which is inherently lock-free)
- MADConfluenceAI.Rendering.cs (1352 lines) provides reference SharpDX patterns (8Hz throttle, brush caching, Stopwatch profiling)
- DynamiDoxa Professional DOM Suite V2 achieves <2% CPU, <1ms latency via immutable snapshot pattern
- NT8 best practices: pre-allocated arrays, no allocations in OnMarketDepth/OnRender, only render visible range, AntialiasMode.Aliased

### Metis Review
**Identified Gaps** (all addressed):
- **Spoof filtering**: DOM spoofing is endemic to NQ. Added `MinPersistenceMs` parameter (default 500ms) — level must exist for N ms before displaying
- **Minimum volume floor**: Top-N alone may show trivial levels during thin sessions. Added `MinVolumeFloor` parameter (default 50 lots)
- **Connection loss handling**: No existing indicators handle this. Added 5-second timeout → clear levels + "NO DATA" status
- **Session boundary**: Reset all levels on session rollover
- **Label collision**: Offset labels if within 12px vertically
- **Historical chart scroll**: Hide levels when chart is scrolled to historical bars (DOM is real-time only)
- **Thread safety**: Existing DOMHeatMap is UNSAFE (no snapshot isolation). Plan uses lock-free array pattern (atomic long reads on x64) + volatile reference swap for computed level snapshots. This is simpler than the Footprint's lock+deep-clone pattern because arrays don't need locks (unlike dictionaries)

---

## Work Objectives

### Core Objective
Build a single, ultra-lightweight NinjaScript indicator that converts real-time Level 2 DOM depth into auto-detected support/resistance levels rendered as chart overlay lines + zones.

### Concrete Deliverables
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityLevels.cs` — Complete indicator file
- Deployed to NT8 via `nt8-deploy.ps1`
- Compiled successfully via `nt8-compile.ps1`
- Visually verified on NQ chart with live or replay data

### Definition of Done
- [ ] Indicator compiles without errors in NT8
- [ ] Displays 1-5 bid-side levels (cyan/blue lines + zones) when DOM data is active
- [ ] Displays 1-5 ask-side levels (magenta/red lines + zones) when DOM data is active
- [ ] Volume labels visible on each level
- [ ] OnRender average < 2ms per frame (logged to Output window)
- [ ] OnMarketDepth processing < 1μs per callback (no allocations)
- [ ] No freeze during high-frequency DOM updates
- [ ] Clean disposal (no timer leaks after indicator removal)

### Must Have
- Pre-allocated arrays for DOM state (O(1) price indexing, zero allocations)
- Thread-safe snapshot pattern: lock-free array access (atomic long reads on x64) + volatile reference swap for level snapshot (NOT the lock + deep-clone Footprint pattern — arrays don't need locks, unlike Footprint's dictionaries)
- Throttled top-N recomputation (250ms default, configurable)
- Dirty flag + timer for chart invalidation (not per-callback)
- All SharpDX resources pre-allocated in OnRenderTargetChanged (zero allocations in OnRender)
- AntialiasMode.Aliased for all rendering
- Only render levels within visible chart price range
- Built-in Stopwatch profiling (render time + callback rate)
- Session boundary reset
- Configurable parameters: MaxLevels (5), MinVolumeFloor (50), MinPersistenceMs (500), ThrottleIntervalMs (250), ZoneBandTicks (2)
- `Operation.Remove` handling in OnMarketDepth — zero the volume when a DOM level is pulled (universal DEEP6 pattern: `e.Operation == Operation.Remove ? 0 : (int)e.Volume`)
- `IsInHitTest` guard as FIRST line of OnRender (universal DEEP6 pattern — prevents rendering during NT8 mouse hit-testing)
- Array recentering when price drifts beyond array bounds — recenter base price and clear arrays (follow DOMHeatMap lines 174-188)
- `MakeFrozenBrush(Color)` static helper for WPF Brush property defaults (required for cross-thread serialization)
- Persistence dictionary cleanup — evict entries when corresponding DOM volume == 0 (during 250ms timer scan)
- Volume label formatting: under 1000 → raw digits ("342"); 1000+ → K-format with 1 decimal ("1.3K")

### Must NOT Have (Guardrails)
- ❌ No full heatmap pixel grid / color cells — only lines + zones at detected levels
- ❌ No Dictionary in hot path — pre-allocated arrays only (persistence Dictionary is OFF the hot path, in the 250ms timer callback only)
- ❌ No `new SolidColorBrush()`, `new TextLayout()`, or `new PathGeometry()` in OnRender (TextLayouts updated only when snapshot identity changes, not per frame)
- ❌ No string concatenation or LINQ in OnMarketDepth
- ❌ No `lock()` or `Monitor.Enter()` in OnMarketDepth — timer callback accepts transient inconsistency (individual long reads on x64 are atomic; documented trade-off)
- ❌ No Series<> storage or bar-indexed historical level data
- ❌ No integration with DEEP6 signal engine (DetectorRegistry, ConfluenceScorer, SessionContext)
- ❌ No alerting, notifications, or sound
- ❌ No delta tracking, level aging/scoring, or time-at-level
- ❌ No iceberg detection, pulling/stacking, or spoof detection
- ❌ No SuperDOM column rendering
- ❌ No multi-instrument support (NQ-optimized only, MNQ compatible via TickSize)
- ❌ No rendering when chart is scrolled to historical bars (DOM is real-time only)
- ❌ No more than 30 SharpDX draw calls total (5 levels × 2 sides × 3 primitives each)

---

## Verification Strategy

> **Code verification is fully agent-executed** — compile checks, code analysis (grep), and performance metrics (temp log file) require zero human intervention.
> **NT8 UI interactions** (adding/removing indicators from charts) are semi-automated via `nt8-ui.ps1` — the script triggers the context menu and indicator dialog but confirmation may require human assist. This is a known NinjaTrader 8 platform limitation. Screenshots are fully automated.

### Test Decision
- **Infrastructure exists**: NO (NinjaTrader indicators have no unit test framework)
- **Automated tests**: None (NT8 C# indicators, not testable via standard frameworks)
- **Framework**: N/A — verification via NT8 compilation + visual screenshot + performance logging

### QA Policy
Every task includes agent-executed QA scenarios using:
- **NT8 Compilation**: `nt8-compile.ps1` — binary pass/fail
- **NT8 Deployment**: `nt8-deploy.ps1` — file copy verification
- **NT8 Screenshots**: `nt8-ui.ps1 -Action screenshot` — visual evidence
- **NT8 Output Window**: Performance metrics logged by indicator itself
- **PowerShell**: CPU/memory measurement commands

Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — build the indicator):
└── Task 1: Build DEEP6LiquidityLevels.cs (complete indicator) [deep]

Wave 2 (After Wave 1 — deploy, compile, verify — SEQUENTIAL):
├── Task 2: Deploy to NT8 + compile + fix errors [quick]
├── Task 3: Visual QA — screenshot + verify levels render [quick] (after Task 2)
└── Task 4: Performance verification — CPU baseline → add indicator → measure [quick] (after Task 3)

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2, 3, 4 | 1 |
| 2 | 1 | 3, 4 | 2 |
| 3 | 2 | 4, F1-F4 | 2 |
| 4 | 3 | F1-F4 | 2 |
| F1-F4 | 3, 4 | — | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **1 task** — T1 → `deep` (core indicator build — performance-critical, complex SharpDX + threading)
- **Wave 2**: **3 tasks** — T2 → `quick` (deploy+compile), T3 → `quick` (screenshot), T4 → `quick` (perf check)
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Build DEEP6LiquidityLevels.cs — Complete DOM Liquidity Levels Indicator

  **What to do**:
  Build a single NinjaScript indicator file (`DEEP6LiquidityLevels.cs`) with these components, in this order:

  **A. State Management + Parameters** (~60 lines):
  - Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
  - Class: `DEEP6LiquidityLevels : Indicator`
  - `OnStateChange()`:
    - `State.SetDefaults`: Name, IsOverlay=true, Calculate=OnEachTick, DrawOnPricePanel=true, PaintPriceMarkers=false, IsSuspendedWhileInactive=false
    - `State.Configure`: Pre-allocate DOM arrays (4,000 slots = 1,000 NQ points ÷ 0.25 tick, 8 bytes/slot = 32KB per side)
    - `State.Realtime`: Start throttle timer + invalidation timer
    - `State.Terminated`: Dispose timers, call DisposeDx()
  - Configurable NinjaScript properties (with `[Display]`, `[Range]`, `[NinjaScriptProperty]`):
    - `MaxLevels` (int, default 5, range 1-10) — top N per side
    - `MinVolumeFloor` (int, default 50, range 0-5000) — minimum volume to qualify
    - `MinPersistenceMs` (int, default 500, range 0-5000) — spoof filter: level must exist N ms before display
    - `ThrottleIntervalMs` (int, default 250, range 50-2000) — top-N recomputation rate
    - `ZoneBandTicks` (int, default 2, range 0-10) — zone band width in ticks around centerline
    - `BidLevelColor` (Brush, default frozen cyan #00E0FF) — bid side color
    - `AskLevelColor` (Brush, default frozen magenta #FF1744) — ask side color

  **B. DOM Data Engine** (~80 lines):
  - Pre-allocated arrays: `long[] bidVolumes = new long[4000]`, `long[] askVolumes = new long[4000]`
  - Base price offset: calculated from first MarketDepth event (session-relative), reset on session boundary
  - `long _currentBidTicks`, `long _currentAskTicks` for BBO tracking — store as price × 10000 (long), use `Interlocked.Exchange` to write and `Interlocked.Read` to read. C# does NOT allow `volatile` on `double`.
  - `long _lastDepthTicks` for connection-loss detection — store as `DateTime.UtcNow.Ticks` (long), use `Interlocked.Exchange` to write and `Interlocked.Read` to read. C# does NOT allow `volatile` on `DateTime`.
  - `int dirtyFlag` for Interlocked invalidation
  - `OnMarketDepth(MarketDepthEventArgs e)`:
    - Compute index: `(int)((e.Price - basePrice) / tickSize) + ArrayMidpoint` (where ArrayMidpoint = 2000)
    - Bounds check: `if (index < 0 || index >= 4000)` → trigger RECENTERING (see below), do NOT silently return
    - Handle `Operation.Remove`: `int size = e.Operation == Operation.Remove ? 0 : (int)e.Volume;` (CRITICAL — every DEEP6 indicator does this; without it, removed levels persist as phantom walls)
    - Array write: `bidVolumes[index] = size` or `askVolumes[index] = size` based on `e.MarketDataType`
    - Track BBO: `if (e.Position == 0)` update `currentBid`/`currentAsk`
    - Track timing: `lastDepthUtc = DateTime.UtcNow` (using a throttled check, not every callback)
    - Set dirty: `Interlocked.Exchange(ref dirtyFlag, 1)`
    - **ZERO allocations. ZERO LINQ. ZERO string operations. ZERO lock/Monitor.Enter.**
  - **Array recentering** (when index out of bounds): Set an `int _recentering` flag via `Interlocked.Exchange(ref _recentering, 1)`. The 250ms timer callback checks this flag FIRST — if set, skip the scan (stale data during recenter). Then recenter `basePrice` to current price, `Array.Clear()` both arrays, and clear the flag. This prevents the timer from reading partially-cleared arrays. Follow DOMHeatMap pattern (lines 174-188) but add the Interlocked guard.
  - **MakeFrozenBrush helper**: Include `static Brush MakeFrozenBrush(Color c)` for WPF Brush property defaults (see DOMHeatMap.cs:411-416). WPF Brushes in NinjaScript properties MUST be frozen or NT8 throws cross-thread exceptions.
  - Session boundary detection: `OnBarUpdate()` checks `Bars.IsFirstBarOfSession` → reset arrays + base price + persistence dictionary

  **C. Level Detection Algorithm** (~80 lines):
  - `System.Threading.Timer` fires at `ThrottleIntervalMs` (default 250ms)
  - On timer callback:
    - Scan `bidVolumes[]` and `askVolumes[]` for top-N levels (simple partial sort — iterate once, maintain sorted array of top N, O(M) where M = array size)
    - Apply `MinVolumeFloor` filter — skip levels below threshold
    - Apply `MinPersistenceMs` spoof filter — each candidate tracks `firstSeenUtc`; only levels that have been continuously present for ≥ MinPersistenceMs qualify. Use a small `Dictionary<int, DateTime>` for tracking (OFF the hot path — this runs every 250ms, not every OnMarketDepth callback)
    - **Dictionary cleanup**: During the same scan, evict entries where corresponding volume == 0 (level no longer in DOM). Prevents unbounded growth over a trading session.
    - **Lock-free trade-off documentation**: Add explicit comment in the timer callback: "Timer reads arrays while OnMarketDepth writes without locking. Individual long reads on x64 are atomic. Transient inconsistency is acceptable for a visual indicator refreshing every 250ms."
    - Build immutable snapshot: `LevelSnapshot` **class** (NOT struct — must be reference type for volatile reference swap) containing:
      - `LevelEntry[] bidLevels` (max 5 entries: price as double, volume as int, label as string)
      - `LevelEntry[] askLevels` (max 5 entries: price as double, volume as int, label as string)
      - `bool hasData` flag
      - `bool isStale` flag (set if `DateTime.UtcNow.Ticks - Interlocked.Read(ref _lastDepthTicks) > 5 * TimeSpan.TicksPerSecond`)
      - Pre-formatted volume label strings (e.g., "342", "1.3K") — computed here, not in OnRender
    - `LevelEntry` is a simple **struct** (price, volume, label) — immutable once snapshot is created
    - Publish snapshot via `volatile` reference swap: `_renderSnapshot = newSnapshot;` (volatile on reference types IS valid in C#)
    - Set dirty flag for chart invalidation
  - Connection-loss handling: If `isStale`, snapshot contains zero levels + status "NO DATA"

  **D. SharpDX Rendering** (~150 lines):
  - `OnRenderTargetChanged()`:
    - Call `DisposeDx()` first
    - If `RenderTarget == null` return
    - Create ALL brushes:
      - `dxBidZone` — bid color at 25% opacity (zone band fill)
      - `dxBidLine` — bid color at 85% opacity (centerline)
      - `dxAskZone` — ask color at 25% opacity (zone band fill)
      - `dxAskLine` — ask color at 85% opacity (centerline)
      - `dxLabelText` — white at 90% opacity
      - `dxLabelBg` — dark at 70% opacity (label background)
      - `dxStatusText` — amber for "NO DATA" status
    - Create TextFormat: `fmtLabel` (Consolas 9pt), `fmtStatus` (Consolas 10pt bold)
    - **TextLayout lifecycle** (resolves the "no allocation in OnRender" constraint):
    - TextFormat objects created in OnRenderTargetChanged using `NinjaTrader.Core.Globals.DirectWriteFactory` — these persist until next render target change.
    - Volume label text is pre-formatted as strings in the LevelSnapshot class (computed in the 250ms timer, NOT in OnRender).
    - In OnRender: use `DrawText()` with the pre-created TextFormat and the snapshot's pre-formatted strings — this does NOT allocate TextLayout objects. `DrawText(string, TextFormat, RectangleF, Brush)` is the preferred zero-allocation text rendering path in SharpDX.
    - Do NOT create TextLayout objects at all — `DrawText` internally handles layout without user-managed allocation.
  - `DisposeDx()`:
    - SafeDispose all brushes and text formats (follow MADConfluenceAI pattern exactly)
  - `OnRender(ChartControl chartControl, ChartScale chartScale)`:
    - **FIRST line**: `if (IsInHitTest) return;` (CRITICAL — universal DEEP6 pattern, prevents rendering during NT8 mouse hit-testing that causes visual glitches and click interference)
    - Early exit if `RenderTarget == null || chartControl == null`
    - Read snapshot: `var snap = _renderSnapshot;` (volatile read — no lock needed)
    - If `!snap.hasData`: render "Waiting for DOM data" status text, return
    - If `snap.isStale`: render "NO DATA — DOM feed lost" in amber, return
    - Set `RenderTarget.AntialiasMode = AntialiasMode.Aliased`
    - Get visible range: `chartScale.MinValue`, `chartScale.MaxValue`
    - For each level in `snap.bidLevels` (max 5):
      - Skip if price outside visible range
      - `float y = chartScale.GetYByValue(level.Price)`
      - `float bandHeight = chartScale.GetYByValue(level.Price - ZoneBandTicks * tickSize) - y`
      - `RenderTarget.FillRectangle(zone rect, dxBidZone)` — zone band
      - `RenderTarget.DrawLine(centerline, dxBidLine, 1.5f)` — centerline
      - Draw volume label: small background rect + text. Format: under 1000 → raw digits ("342"); 1000+ → K-format with 1 decimal ("1.3K"). No commas. Pre-format in snapshot string, not in OnRender.
    - Same for `snap.askLevels` (max 5) with ask colors
    - Label collision avoidance: if two levels within 12px vertically, offset the lower label by 12px
    - **ZERO allocations in this method. ALL brushes pre-created. ALL TextLayouts pre-allocated.**

  **E. Performance Profiling** (~40 lines):
  - `Stopwatch _renderSw` — measures OnRender time
  - `double[] _renderTimes = new double[100]` — circular buffer of last 100 frame times
  - Every 100 frames: log average to BOTH Output window AND temp file:
    - `Print($"[DEEP6LiquidityLevels] Avg render: {avg:F2}ms");`
    - Append to `Path.Combine(Path.GetTempPath(), "DEEP6LiquidityLevels-perf.log")`
  - `long _depthCallbackCount` via `Interlocked.Increment` in OnMarketDepth
  - Every 10 seconds (in throttle timer): log callback rate to BOTH Output window AND temp file:
    - `Print($"[DEEP6LiquidityLevels] DOM callbacks/sec: {rate}");`
    - Append to same temp file
  - Auto-disable warning: if average render time > 12ms, print warning
  - Temp file path: `%TEMP%\DEEP6LiquidityLevels-perf.log` — this allows agent-executed reading via `Get-Content "$env:TEMP\DEEP6LiquidityLevels-perf.log" -Tail 20`
  - File write uses `File.AppendAllText` with try/catch (never crash indicator for logging failure)

  **Must NOT do**:
  - Do NOT use Dictionary in OnMarketDepth — pre-allocated arrays ONLY
  - Do NOT create any `new SolidColorBrush()`, `new TextLayout()`, or `new PathGeometry()` inside OnRender
  - Do NOT use string concatenation, LINQ, or any allocation in OnMarketDepth
  - Do NOT integrate with DetectorRegistry, ConfluenceScorer, SessionContext, or any DEEP6 component
  - Do NOT add Series<> or any bar-indexed historical storage
  - Do NOT add alerting, sound, or notification code
  - Do NOT render anything when `CurrentBar < Count - 1` (historical bars — no DOM data)
  - Do NOT hardcode tick size — read from `Instrument.MasterInstrument.TickSize` with 0.25 fallback

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Performance-critical indicator with SharpDX rendering, thread safety, and complex DOM data processing. Requires careful attention to zero-allocation constraints and cross-thread snapshot patterns.
  - **Skills**: [`nt8-expert`, `nt8-visual-design`]
    - `nt8-expert`: NT8 indicator lifecycle (OnStateChange states), deployment paths, namespace conventions, NinjaScript property attributes, compilation
    - `nt8-visual-design`: SharpDX brush creation patterns, Color4 values, font sizing, performance rendering constraints, institutional color palette
  - **Skills Evaluated but Omitted**:
    - `nt8-fix`: Only needed if compile fails — loaded in Task 2 if needed
    - `nt8-architect`: This is a single standalone file, not an architecture decision
    - `trading-knowledge`: No trading logic in this indicator — pure visualization

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation task)
  - **Parallel Group**: Wave 1 (solo)
  - **Blocks**: Tasks 2, 3, 4
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL — executor has NO context from interview):

  **Pattern References** (existing code to follow):
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DOMHeatMap.cs:26-55` — Pre-allocated array approach for DOM data (bidHeat/askHeat arrays, ring buffer, alpha LUT). Follow the array pattern but NOT the thread safety (it's unsafe). Shows how to compute tick-based indices.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6DOMHeatMap.cs:340-357` — Dirty flag + invalidation timer pattern. Copy this exactly: `Interlocked.Exchange(ref dirtyFlag, 0)`, `ChartControl.Dispatcher.BeginInvoke`, null checks.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6MBOHeatMap.cs:29-64` — SharpDX brush field declarations, TextFormat fields, StrokeStyle fields. Shows the exact field naming convention and organization.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6MBOHeatMap.cs:67-80` — OnStateChange SetDefaults pattern for overlay indicators: IsOverlay, DrawOnPricePanel, PaintPriceMarkers, ScaleJustification, IsSuspendedWhileInactive.
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs:94-100` — Render throttle + Stopwatch profiling setup: `RenderThrottleMs=125`, `Stopwatch`, circular buffer for render times, auto-disable flag.
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs:195-272` — `OnRenderTargetChanged()` GOLD STANDARD: DisposeDx() first, null check RenderTarget, create all SolidColorBrush with Color4, TextFormat with factory, StrokeStyle. Copy this structure exactly.
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs:278-291` — `DisposeDx()` pattern: `SafeDispose(ref brush)` for every resource. Copy this pattern for all brushes/formats.
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV7.cs:121-124` — Volatile reference pattern for cross-thread snapshot publishing: "volatile ensures render thread sees writes from data thread without memory barrier. Reference reads on x64 are atomic." Use this for the `_renderSnapshot` volatile reference swap — the SAME pattern but WITHOUT the lock (arrays don't need it).

  **API/Type References** (contracts to implement against):
  - NT8 `OnMarketDepth(MarketDepthEventArgs e)` — `e.Price`, `e.Volume`, `e.Position`, `e.MarketDataType` (Ask/Bid), `e.Operation` (Add/Update/Remove)
  - NT8 `OnRender(ChartControl chartControl, ChartScale chartScale)` — `chartScale.GetYByValue(price)`, `chartScale.MinValue`, `chartScale.MaxValue`, `ChartPanel.X`, `ChartPanel.W`
  - NT8 `OnRenderTargetChanged()` — `RenderTarget` (SharpDX.Direct2D1.RenderTarget)
  - NT8 `Instrument.MasterInstrument.TickSize` — dynamic tick size
  - NT8 `Bars.IsFirstBarOfSession` — session boundary detection

  **External References** (libraries and frameworks):
  - SharpDX.Direct2D1: `SolidColorBrush`, `RenderTarget.FillRectangle()`, `RenderTarget.DrawLine()`, `AntialiasMode.Aliased`
  - SharpDX.DirectWrite: `TextFormat`, `TextLayout`
  - SharpDX: `Color4`, `RectangleF`, `Vector2`
  - System.Threading: `Timer`, `Interlocked.Exchange`, `Interlocked.Increment`, `volatile`

  **WHY Each Reference Matters**:
  - DOMHeatMap array pattern: Shows how to index DOM data by price tick offset in pre-allocated arrays — the SAME approach needed here but simpler (no ring buffer, just current state)
  - DOMHeatMap dirty flag pattern: Exact timer-based invalidation code to copy — prevents per-callback InvalidateVisual() thrashing
  - MBOHeatMap brush declarations: Shows the naming convention and organization of SharpDX fields in DEEP6 indicators
  - MADConfluenceAI.Rendering OnRenderTargetChanged: The GOLD STANDARD for resource lifecycle — every new indicator must follow this exact pattern
  - FootprintV7 volatile/snapshot comments: Documents the threading contract for cross-thread data access in DEEP6 indicators

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero allocations in OnMarketDepth
    Tool: Bash (grep)
    Preconditions: File exists
    Steps:
      1. Grep for "new " inside the OnMarketDepth method body
      2. Grep for ".ToString()" inside OnMarketDepth
      3. Grep for "string." or "String." inside OnMarketDepth
      4. Grep for ".Where(" or ".Select(" or ".OrderBy(" inside OnMarketDepth (LINQ)
    Expected Result: Zero matches for any of the above patterns inside OnMarketDepth
    Failure Indicators: Any allocation pattern found between OnMarketDepth opening brace and closing brace
    Evidence: .sisyphus/evidence/task-1-zero-alloc-check.txt

  Scenario: Thread safety pattern present
    Tool: Bash (grep)
    Preconditions: File exists
    Steps:
      1. Grep for "volatile" — should find snapshot reference declaration
      2. Grep for "Interlocked" — should find dirty flag operations
      3. Grep for "lock(" or "Monitor." — should NOT be in OnMarketDepth (too slow); may be in timer callback
      4. Verify snapshot pattern: volatile reference swap in timer callback
    Expected Result: volatile + Interlocked present; no lock in OnMarketDepth hot path
    Failure Indicators: Missing volatile keyword, missing Interlocked, lock statement inside OnMarketDepth
    Evidence: .sisyphus/evidence/task-1-thread-safety-check.txt

  Scenario: Operation.Remove correctly zeros levels
    Tool: Bash (grep)
    Preconditions: File exists
    Steps:
      1. Find OnMarketDepth method body
      2. Grep for "Operation.Remove" — must be present
      3. Verify the remove case sets volume to 0 (not just returns/skips)
    Expected Result: e.Operation == Operation.Remove results in volume = 0 written to array
    Failure Indicators: No Operation.Remove check found, or return without clearing
    Evidence: .sisyphus/evidence/task-1-remove-handling.txt

  Scenario: IsInHitTest guard present
    Tool: Bash (grep)
    Preconditions: File exists
    Steps:
      1. Find OnRender method
      2. Verify "IsInHitTest" appears within the first 3 lines of OnRender body
    Expected Result: IsInHitTest guard is the first check in OnRender
    Failure Indicators: Missing IsInHitTest, or placed after other logic
    Evidence: .sisyphus/evidence/task-1-hittest-guard.txt

  Scenario: SharpDX resource lifecycle correct
    Tool: Bash (grep)
    Preconditions: File exists
    Steps:
      1. Count "new SolidColorBrush" occurrences — should ONLY appear inside OnRenderTargetChanged
      2. Count "SafeDispose" or ".Dispose()" in DisposeDx — should match brush count
      3. Verify OnRenderTargetChanged calls DisposeDx() as FIRST action
      4. Verify OnRender contains ZERO "new SolidColorBrush" or "new TextLayout"
    Expected Result: All brushes created in OnRenderTargetChanged, all disposed in DisposeDx, zero allocations in OnRender
    Failure Indicators: new SolidColorBrush found outside OnRenderTargetChanged, disposal count mismatch
    Evidence: .sisyphus/evidence/task-1-resource-lifecycle-check.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-zero-alloc-check.txt — Grep results for allocation patterns in OnMarketDepth
  - [ ] task-1-thread-safety-check.txt — Grep results for threading patterns
  - [ ] task-1-resource-lifecycle-check.txt — Grep results for SharpDX resource management
  - [ ] task-1-remove-handling.txt — Grep results for Operation.Remove handling
  - [ ] task-1-hittest-guard.txt — Grep results for IsInHitTest in OnRender

  **Commit**: YES
  - Message: `feat(nt8): add DEEP6LiquidityLevels DOM-based auto S/R indicator`
  - Files: `ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityLevels.cs`
  - Pre-commit: NT8 compile success

- [x] 2. Deploy to NT8 + Compile + Fix Errors

  **What to do**:
  - Deploy all DEEP6 indicators (including DEEP6LiquidityLevels.cs) to NinjaTrader 8 custom folder via `nt8-deploy.ps1 -Target Indicators`
  - Trigger compilation via `nt8-compile.ps1`
  - If compilation fails (`[COMPILE-RESULT] FAILED`): read full error details via `nt8-errors-full.ps1 -Format Text -Open` (UIAutomation reads the NinjaScript Editor error DataGrid — this is the ONLY way to get CS#### error text from NT8). Fix each error in the source file, redeploy with `nt8-deploy.ps1 -Target Indicators -Force`, recompile
  - Iterate until `[COMPILE-RESULT] SUCCESS`

  **Must NOT do**:
  - Do NOT change the indicator's architecture or design to fix errors — only fix syntax/reference issues
  - Do NOT add new features during error fixing
  - Do NOT modify any other DEEP6 indicator files

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Mechanical deploy + compile + fix cycle. No creative work.
  - **Skills**: [`nt8-expert`, `nt8-fix`]
    - `nt8-expert`: Deploy scripts, compile scripts, NT8 custom indicator paths
    - `nt8-fix`: Error pattern recognition and automated fixing for NT8 compile errors

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (sequential prerequisite for Tasks 3 & 4)
  - **Blocks**: Tasks 3, 4
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - `ninjatrader/scripts/nt8-deploy.ps1` — Deployment script (copies .cs files to NT8 custom folder)
  - `ninjatrader/scripts/nt8-compile.ps1` — Triggers NT8 compilation and reports result
  - `ninjatrader/scripts/nt8-status.ps1` — Check deployed files and sync state

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Successful deployment and compilation
    Tool: Bash (PowerShell)
    Preconditions: Task 1 complete, DEEP6LiquidityLevels.cs exists in ninjatrader/Custom/Indicators/DEEP6/
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-deploy.ps1" -Target Indicators -Force
      2. Assert: deployment output shows "[Indicators] Deployed N file(s) to ..." and lists DEEP6LiquidityLevels.cs
      3. Run: & "ninjatrader/scripts/nt8-compile.ps1"
      4. Assert: output contains "[COMPILE-RESULT] SUCCESS"
      5. If FAILED: Run & "ninjatrader/scripts/nt8-errors-full.ps1" -Format Text -Open
      6. Parse CS#### error codes and line numbers from output
      7. Fix each error in source file, redeploy with -Force, recompile
      8. Iterate until SUCCESS (max 5 attempts)
    Expected Result: "[COMPILE-RESULT] SUCCESS" with zero errors
    Failure Indicators: Compilation still fails after 3 fix attempts
    Evidence: .sisyphus/evidence/task-2-deploy-compile.txt

  Scenario: No other DEEP6 files broken
    Tool: Bash (PowerShell)
    Preconditions: Compilation succeeded
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-compile.ps1"
      2. Check for errors referencing OTHER DEEP6 files (not DEEP6LiquidityLevels.cs)
    Expected Result: Zero errors in any existing DEEP6 indicator
    Failure Indicators: Errors in DEEP6Footprint.cs, DEEP6Signal.cs, or any other pre-existing file
    Evidence: .sisyphus/evidence/task-2-no-regression.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-deploy-compile.txt — Full deployment + compilation output
  - [ ] task-2-no-regression.txt — Compilation output confirming no regressions

  **Commit**: NO (groups with Task 1)

- [x] 3. Visual QA — Screenshot + Verify Levels Render

  **What to do**:
  - Add DEEP6LiquidityLevels indicator to NQ chart via `nt8-ui.ps1 -Action AddIndicator -Name "DEEP6 Liquidity Levels"`
  - Take a screenshot via `nt8-ui.ps1 -Action Screenshot`
  - Verify visual output in screenshot:
    - If live DOM data is available: at least 1 bid-side level (cyan) and 1 ask-side level (magenta) should be visible
    - If no live DOM data (sim/replay/weekend): "Waiting for DOM data" or "NO DATA" status text should be visible
  - Open Output window via `nt8-ui.ps1 -Action OpenOutputWindow`, take another screenshot to capture any error messages
  - Note: Indicator removal verification is deferred to the user during /start-work final approval (NT8 lacks automated remove-indicator scripting)

  **Must NOT do**:
  - Do NOT modify the indicator code during visual QA
  - Do NOT add the indicator to charts of other instruments during V1 QA

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Screenshot + visual inspection. Mechanical verification.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 UI interaction scripts for adding indicators, taking screenshots, reading Output window

  **Parallelization**:
  - **Can Run In Parallel**: NO (Task 4 needs baseline before indicator is added)
  - **Parallel Group**: Wave 2 sequential (Task 2 → Task 3 → Task 4)
  - **Blocks**: Task 4, F1-F4
  - **Blocked By**: Task 2

  **References**:
  - `ninjatrader/scripts/nt8-ui.ps1` — UI automation: add indicator to chart, take screenshot, read Output

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Indicator renders on NQ chart
    Tool: Bash (PowerShell + nt8-ui.ps1) — semi-automated
    Preconditions: Task 2 compile succeeded, NT8 running with NQ chart open
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action AddIndicator -Name "DEEP6 Liquidity Levels"
         (Semi-automated: script opens Indicators dialog via context menu. Agent or user confirms selection.)
      2. Wait 5 seconds for DOM data to flow
      3. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action Screenshot -OutputPath ".sisyphus/evidence/task-3-visual-qa.png"
      4. Examine screenshot for: colored horizontal lines (cyan for bid, magenta for ask) OR status text ("Waiting for DOM data")
    Expected Result: Visual evidence of indicator rendering — either levels or status text visible in screenshot
    Failure Indicators: Blank chart (no levels, no status), NT8 error dialog, indicator not listed
    Evidence: .sisyphus/evidence/task-3-visual-qa.png

  Scenario: Output window shows no errors
    Tool: Bash (PowerShell + nt8-ui.ps1)
    Preconditions: Indicator added to chart
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action OpenOutputWindow
      2. Wait 2 seconds
      3. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action Screenshot -OutputPath ".sisyphus/evidence/task-3-output-window.png"
      4. Examine screenshot for: no NullReferenceException, no ObjectDisposedException, performance log lines present
    Expected Result: Output window shows "[DEEP6LiquidityLevels]" performance log entries OR is clean (no errors)
    Failure Indicators: Exception traces, "Error" lines, or crash indicators in Output window
    Evidence: .sisyphus/evidence/task-3-output-window.png
  ```

  **Evidence to Capture:**
  - [ ] task-3-visual-qa.png — Screenshot of indicator on NQ chart
  - [ ] task-3-output-window.png — Screenshot of Output window confirming no errors

  **Commit**: NO (groups with Task 1)

- [x] 4. Performance Verification — CPU, Render Time, GC

  **What to do**:
  - With DEEP6LiquidityLevels running on NQ chart, measure:
    - **OnRender time**: Read indicator's own Output window log — "Avg render: X.XXms" (should be < 2ms)
    - **DOM callback rate**: Read Output window log — "DOM callbacks/sec: XXXX" (confirms data is flowing)
    - **CPU impact**: Measure NT8 process CPU before/after adding indicator (should be < 5% incremental)
    - **Memory**: Measure NT8 working set before/after (should be < 1MB incremental)
  - If no live DOM data available (weekend/no connection): verify the indicator does NOT consume CPU (idle state) — Output should show "0 callbacks/sec" or no DOM logging

  **Must NOT do**:
  - Do NOT modify indicator code during performance verification
  - Do NOT run performance tests on instruments other than NQ

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Read Output window + run PowerShell measurement commands. Simple verification.
  - **Skills**: [`nt8-expert`]
    - `nt8-expert`: NT8 Output window reading, process measurement

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs CPU baseline before Task 3 adds indicator)
  - **Parallel Group**: Wave 2 sequential (runs AFTER Task 3)
  - **Blocks**: F1-F4
  - **Blocked By**: Task 3

  **References**:
  - `ninjatrader/Custom/Indicators/DEEP6/MADConfluenceAI/MADConfluenceAI.Rendering.cs:94-100` — Stopwatch profiling pattern being followed in DEEP6LiquidityLevels

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Render performance within budget
    Tool: Bash (PowerShell — read temp log file)
    Preconditions: Indicator running on NQ chart for at least 30 seconds
    Steps:
      1. Wait 30 seconds for metrics to accumulate
      2. Run: Get-Content "$env:TEMP\DEEP6LiquidityLevels-perf.log" -Tail 20
      3. Parse lines matching "[DEEP6LiquidityLevels] Avg render:" for the ms value
      4. Assert: average render time < 2.0ms
    Expected Result: "Avg render: X.XXms" where X.XX < 2.0
    Failure Indicators: Avg render > 2.0ms, log file missing (indicator not writing metrics), or no entries
    Evidence: .sisyphus/evidence/task-4-render-perf.txt

  Scenario: DOM callback rate confirms data flow
    Tool: Bash (PowerShell — read temp log file)
    Preconditions: Indicator running on NQ chart with live or replay data for 30+ seconds
    Steps:
      1. Run: Get-Content "$env:TEMP\DEEP6LiquidityLevels-perf.log" -Tail 20
      2. Parse lines matching "[DEEP6LiquidityLevels] DOM callbacks/sec:"
      3. If live data: assert > 0 callbacks/sec
      4. If no data (weekend): assert file exists but shows 0 or no callback entries
    Expected Result: Positive callback count during market hours, zero/idle outside
    Failure Indicators: Negative values, extremely high numbers suggesting loop bug, file missing
    Evidence: .sisyphus/evidence/task-4-callback-rate.txt

  Scenario: CPU impact within budget
    Tool: Bash (PowerShell)
    Preconditions: NT8 running, baseline CPU measured before adding indicator
    Steps:
      1. Measure baseline: (Get-Counter '\Process(NinjaTrader)\% Processor Time' -SampleInterval 2 -MaxSamples 5).CounterSamples | Select-Object CookedValue
      2. Add DEEP6LiquidityLevels to chart
      3. Wait 10 seconds
      4. Measure with indicator: same command
      5. Calculate delta
    Expected Result: CPU delta < 5% incremental
    Failure Indicators: CPU spikes > 10%, sustained high CPU
    Evidence: .sisyphus/evidence/task-4-cpu-impact.txt
  ```

  **Evidence to Capture:**
  - [ ] task-4-render-perf.txt — Render time log entries
  - [ ] task-4-callback-rate.txt — DOM callback rate log entries
  - [ ] task-4-cpu-impact.txt — CPU before/after comparison

  **Commit**: NO (groups with Task 1)

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [x] F1. **Plan Compliance Audit** — `oracle`

  ```
  Scenario: All Must Have items present, all Must NOT Have items absent
    Tool: Bash (grep + Read)
    Preconditions: DEEP6LiquidityLevels.cs deployed and compiled
    Steps:
      1. Read DEEP6LiquidityLevels.cs
      2. For each Must Have: grep for implementation evidence (pre-allocated arrays, Interlocked, Stopwatch, AntialiasMode.Aliased, Operation.Remove, IsInHitTest, MakeFrozenBrush, etc.)
      3. For each Must NOT Have: grep for forbidden patterns (Dictionary in OnMarketDepth body, new SolidColorBrush in OnRender body, Series<>, DetectorRegistry, ConfluenceScorer)
      4. Verify evidence files exist: ls .sisyphus/evidence/task-*
    Expected Result: All Must Have items found (N/N), all Must NOT Have items absent (0 matches), evidence files present
    Failure Indicators: Any Must Have missing, any Must NOT Have pattern found, evidence files missing
    Evidence: .sisyphus/evidence/f1-plan-compliance.txt
  ```
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`

  ```
  Scenario: Code meets quality standards
    Tool: Bash (grep + Read + nt8-compile.ps1)
    Preconditions: DEEP6LiquidityLevels.cs exists
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-compile.ps1" — assert SUCCESS
      2. Grep for empty catch blocks: "catch\s*{" or "catch\s*{\s*}" — assert 0 matches (except the timer try/catch which is intentional)
      3. Grep for commented-out code blocks: lines starting with "//" that contain actual code statements — flag any
      4. Verify namespace line: grep "namespace NinjaTrader.NinjaScript.Indicators.DEEP6"
      5. Verify OnRenderTargetChanged calls DisposeDx() as first action
      6. Verify every SolidColorBrush field has a corresponding SafeDispose in DisposeDx
      7. Verify OnRender checks RenderTarget != null and chartControl != null
      8. Verify all array index accesses have bounds checks
    Expected Result: Compile SUCCESS, namespace correct, resource lifecycle sound, bounds checked
    Failure Indicators: Compile fails, wrong namespace, unmatched brush create/dispose, missing null checks
    Evidence: .sisyphus/evidence/f2-code-quality.txt
  ```
  Output: `Build [PASS/FAIL] | Thread Safety [PASS/FAIL] | Resource Management [PASS/FAIL] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high` (load `nt8-expert` skill)

  ```
  Scenario: Indicator deploys, compiles, and renders on NQ chart
    Tool: Bash (PowerShell + nt8-ui.ps1) — semi-automated for UI steps
    Preconditions: NT8 running with NQ chart open
    Steps:
      1. Run: & "ninjatrader/scripts/nt8-deploy.ps1" -Target Indicators -Force — assert "copied" output
      2. Run: & "ninjatrader/scripts/nt8-compile.ps1" — assert "[COMPILE-RESULT] SUCCESS"
      3. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action AddIndicator -Name "DEEP6 Liquidity Levels" (semi-automated)
      4. Wait 5 seconds
      5. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action Screenshot -OutputPath ".sisyphus/evidence/f3-chart-screenshot.png"
      6. Examine screenshot: at least 1 colored level (cyan/magenta) OR status text "Waiting for DOM data"
      7. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action OpenOutputWindow
      8. Run: & "ninjatrader/scripts/nt8-ui.ps1" -Action Screenshot -OutputPath ".sisyphus/evidence/f3-output-window.png"
      9. Examine Output window screenshot: no NullReferenceException, no ObjectDisposedException
    Expected Result: Deploy + compile succeed, visual evidence of indicator rendering, clean Output window
    Failure Indicators: Deploy fails, compile fails, blank chart with no indicator evidence, exception traces in Output
    Evidence: .sisyphus/evidence/f3-chart-screenshot.png, .sisyphus/evidence/f3-output-window.png
  ```
  Note: Indicator removal is NOT automated (NT8 has no scripted remove-indicator action) — disposal correctness verified via code review in F2.
  Output: `Compile [PASS/FAIL] | Deploy [PASS/FAIL] | Visual [PASS/FAIL] | Output Clean [PASS/FAIL] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`

  ```
  Scenario: Indicator matches plan scope exactly — nothing missing, nothing extra
    Tool: Bash (grep + Read + glob)
    Preconditions: DEEP6LiquidityLevels.cs exists, all tasks completed
    Steps:
      1. Verify single file: glob for ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityLevels*.cs — should find exactly 1 file (note: DEEP6LiquidityHeatMap.cs also exists but is a pre-existing separate indicator)
      2. Grep for "DetectorRegistry" in file — assert 0 matches (no signal engine integration)
      3. Grep for "ConfluenceScorer" in file — assert 0 matches
      4. Grep for "SessionContext" in file — assert 0 matches
      5. Grep for "Series<" in file — assert 0 matches (no historical storage)
      6. Grep for "Alert\|PlaySound\|SendMail" in file — assert 0 matches (no alerting)
      7. Grep for "FillRectangle" in OnRender — should find zone bands only, not a pixel-level heatmap grid
      8. Verify parameters: grep for "MaxLevels", "MinVolumeFloor", "MinPersistenceMs", "ThrottleIntervalMs", "ZoneBandTicks" — all 5 must be present as NinjaScript properties
      9. Check git status for unaccounted files: any new files outside (a) ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityLevels.cs and (b) .sisyphus/ directory (evidence files and plan updates are expected)
    Expected Result: 1 file, 0 forbidden references, all 5 parameters present, no unaccounted files
    Failure Indicators: Multiple files, forbidden references found, missing parameters, unaccounted files
    Evidence: .sisyphus/evidence/f4-scope-fidelity.txt
  ```
  Output: `Scope [CLEAN/N issues] | Unaccounted Files [CLEAN/N] | VERDICT`

---

## Commit Strategy

| Task | Commit Message | Files | Pre-commit Check |
|------|---------------|-------|-----------------|
| 1-2 | `feat(nt8): add DEEP6LiquidityLevels DOM-based auto S/R indicator` | `ninjatrader/Custom/Indicators/DEEP6/DEEP6LiquidityLevels.cs` | NT8 compile success |

---

## Success Criteria

### Verification Commands
```powershell
# Deploy all indicators (includes DEEP6LiquidityLevels.cs)
& "ninjatrader/scripts/nt8-deploy.ps1" -Target Indicators  # Expected: [Indicators] Deployed N file(s) to ...

# Compile check
& "ninjatrader/scripts/nt8-compile.ps1"  # Expected: [COMPILE-RESULT] SUCCESS

# Screenshot evidence
& "ninjatrader/scripts/nt8-ui.ps1" -Action Screenshot  # Expected: screenshot saved

# Performance log (written by indicator to temp file)
Get-Content "$env:TEMP\DEEP6LiquidityLevels-perf.log" -Tail 20  # Expected: render times + callback rates
```

### Final Checklist
- [ ] All "Must Have" present in DEEP6LiquidityLevels.cs
- [ ] All "Must NOT Have" absent from DEEP6LiquidityLevels.cs
- [ ] NT8 compiles without errors
- [ ] Indicator loads on NQ chart without exception
- [ ] At least 1 level visible per side when DOM data is active
- [ ] OnRender average < 2ms (logged to Output window)
- [ ] Clean disposal on indicator removal
