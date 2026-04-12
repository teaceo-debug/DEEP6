# Phase 1: Architecture Foundation - Research

**Researched:** 2026-04-12
**Domain:** NinjaTrader 8 partial class decomposition + .NET 4.8 GC optimization
**Confidence:** HIGH (source code verified) / MEDIUM (NT8 AddOns compilation — community-validated but requires Windows NT8 target validation)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use AddOns/ partial classes pattern. Engine logic moves to `AddOns/` as `partial class DEEP6` files. NT8 compiles AddOns separately from Indicators — no wrapper code conflict.
- **D-02:** Granularity is Claude's discretion. Analyze code structure, pick the right split (~10-15 files).
- **D-03:** Each engine file contains its Run method + its private state fields + its helper methods. Clean boundaries for future testing and independent modification.
- **D-04:** Fix ALL GC hot-path issues in Phase 1 before any new code is written in Phase 2+. Includes: Std()→Welford, SolidColorBrush→pre-allocated gradient palette, List.RemoveAll()→circular buffer, LINQ in Scorer→manual loops.
- **D-05:** E3 CounterSpoof moves from per-tick (OnMarketDepth, ~1,000/sec) to per-bar (OnBarUpdate). Reduces GC pressure dramatically. Acceptable tradeoff: spoof detection latency increases from ~1ms to ~1 bar duration.
- **D-06:** Two-layer validation: (1) CSV checksum of all engine scores + signals before/after refactor. (2) Visual side-by-side screenshot comparison.
- **D-07:** Validation runs on Windows NT8 box (macOS cannot compile/run NT8).
- **D-08:** Each engine partial class file is self-contained. No cross-engine state sharing except through Scorer's well-defined input interface (direction + score per engine).

### Claude's Discretion
- File granularity — Claude picks the right number of files based on code analysis
- Exact circular buffer implementation for E3/E4 queues
- Whether to keep #region blocks within individual engine files for sub-organization
- Order of GC fixes within Phase 1 (all must complete, sequence is flexible)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ARCH-01 | Monolithic DEEP6.cs decomposed into partial classes via AddOns pattern (~15 files, zero behavior change) | NT8 AddOns folder partial class pattern documented; exact file split proposed below |
| ARCH-02 | GC hot-path fixes applied (Std() pre-allocation, brush caching, RemoveAll() replaced) before any signal expansion | Welford's algorithm, SharpDX palette, circular buffer, and manual Scorer loop all documented with exact C# code |
</phase_requirements>

---

## Summary

DEEP6.cs is a 1,010-line NinjaTrader 8 indicator class in the `NinjaTrader.NinjaScript.Indicators` namespace. The class declaration is `public class DEEP6 : Indicator` — it is NOT a partial class today. The refactor must change this to `public partial class DEEP6 : Indicator` in `Indicators/DEEP6.cs` and add matching `partial class DEEP6` declarations (no `Indicator` inheritance) in all AddOns files.

The GC pressure comes from four distinct sites: (1) `Std()` at line 421-423 allocates arrays and LINQ enumerators on every E3 call, which fires ~1,000/sec; (2) `RenderFP()` at lines 636-641 allocates a new `SolidColorBrush` for every imbalanced footprint cell at every chart repaint; (3) `RemoveAll()` at lines 412 and 434 scans entire lists on the hot path; (4) the Scorer at lines 501 and 503 uses `Zip().Sum()` and `.Average()` LINQ on every bar. All four have clear zero-allocation replacements.

The E3 migration from OnMarketDepth to OnBarUpdate is safe because E3's Wasserstein-1 score operates on the sliding window of imbalance values — those values are already being accumulated in `_iLong` and `_iShort` queues inside RunE2, which continues running per-tick. When RunE3 moves to OnBarUpdate, it reads the same queues that RunE2 has been maintaining. The Wasserstein-1 result will reflect the bar's accumulated distribution rather than the most recent tick's distribution — semantically sound and algorithmically valid.

**Primary recommendation:** Execute the decomposition in two sequential waves: Wave A — file split with zero logic changes (compile-and-verify identical output); Wave B — GC fixes applied one at a time within the now-decomposed files.

---

## Standard Stack

### Core (verified from source)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| NinjaTrader.NinjaScript | NT8.0.23+ | Indicator base class, lifecycle, DOM callbacks | Only viable option in NT8 environment [VERIFIED: source lines 14-18] |
| SharpDX.Direct2D1 | NT8-bundled | GPU-accelerated 2D rendering for footprint cells | NT8's rendering API; no alternative [VERIFIED: source line 12] |
| SharpDX.DirectWrite | NT8-bundled | Text rendering on chart canvas | Paired with Direct2D1 [VERIFIED: source line 13] |
| System.Windows (WPF) | .NET 4.8 | Overlay UI (header, pills, panel) | NT8 host is WPF application [VERIFIED: source lines 7-11] |
| System.Collections.Generic | .NET 4.8 | Queue<T>, List<T> for state buffers | Standard .NET collections [VERIFIED: source line 2] |

### No New Libraries Required
Phase 1 is a pure refactor + GC fix. All replacements use .NET 4.8 built-ins:
- Welford's algorithm: `double` fields, no library
- Circular buffer: custom struct/class using `double[]` + index pointers
- Brush palette: pre-allocated `SharpDX.Direct2D1.SolidColorBrush[]` array in InitDX
- Manual dot product: `for` loop replacing LINQ

---

## Architecture Patterns

### NT8 Partial Class Pattern for AddOns

**What NT8 does to Indicators folder:** NT8 auto-generates wrapper/scaffolding code for every file in the `Indicators/` folder that contains a class inheriting from `Indicator`. If you create `Indicators/DEEP6.E1.cs` as a partial class, NT8 will attempt to generate a second copy of wrapper code, causing `CS0101` (type already defined) compilation errors. [ASSUMED — based on community forum evidence; must validate on Windows NT8 box]

**Why AddOns folder works:** Files in `AddOns/` are compiled by NT8 into the same assembly but NT8 does NOT apply its code-generation pass to AddOns files. Partial classes in AddOns/ therefore do not trigger wrapper conflicts. [ASSUMED — community-validated but not confirmed via NT8 source code]

**Namespace requirement:** Every AddOns file must use the identical namespace:
```csharp
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class DEEP6 : Indicator  // ← WRONG: only in DEEP6.cs (main file)
}
```
```csharp
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class DEEP6              // ← CORRECT for AddOns files
    {
        // engine methods and fields
    }
}
```
[ASSUMED — standard C# partial class rule; the `Indicator` base class may only be declared once]

**Critical: the main file needs `partial` added:**
Current line 58 of `Indicators/DEEP6.cs`:
```csharp
public class DEEP6 : Indicator
```
Must become:
```csharp
public partial class DEEP6 : Indicator
```
This single keyword addition is the only change to the main file required for the decomposition to compile.

### Recommended Project Structure
```
Documents/NinjaTrader 8/bin/Custom/
├── Indicators/
│   └── DEEP6.cs                         ← NT8 facade (add `partial`, keep lifecycle only)
└── AddOns/
    ├── DEEP6.E1Footprint.cs             ← RunE1 + footprint state fields + E1 helpers
    ├── DEEP6.E2Trespass.cs              ← RunE2 + DOM arrays + iLong/iShort queues
    ├── DEEP6.E3CounterSpoof.cs          ← RunE3 + _pLg + ChkSpoof + Welford state
    ├── DEEP6.E4Iceberg.cs               ← RunE4 + _pTr + LvPx helper
    ├── DEEP6.E5Micro.cs                 ← RunE5 + probability fields
    ├── DEEP6.E6VPCtx.cs                 ← RunE6 + session fields + UpdateSession + SessionReset
    ├── DEEP6.E7MLQuality.cs             ← RunE7 + Kalman state
    ├── DEEP6.Scorer.cs                  ← Scorer + MakeSigLabel + PushFeed + DrawLevels
    ├── DEEP6.Rendering.cs               ← InitDX + DisposeDX + RenderFP + RenderSigBoxes + RenderStk + palette
    └── DEEP6.UI.cs                      ← BuildUI + BuildHeader + BuildPills + BuildTabBar + BuildPanel + UpdatePanel + DisposeUI + all WPF helpers
```

**Ten-file split total** (1 facade + 9 AddOns). This keeps each file well under the 1,200-line warning threshold.

### Anti-Patterns to Avoid
- **Partial class in Indicators/ folder:** NT8 will attempt to generate wrapper code for it. Only the one facade file with `Indicator` inheritance goes in `Indicators/`. All partials go in `AddOns/`.
- **Moving NT8 lifecycle methods out of DEEP6.cs:** `OnStateChange`, `OnBarUpdate`, `OnMarketDepth`, `OnMarketData`, `OnRender`, `OnRenderTargetChanged` — all stay in the main file. They are the facade's only responsibility after refactoring.
- **Splitting fields from their engine:** E.g., putting `_fpSc` in a separate state file while `RunE1()` is in E1Footprint.cs. D-03 requires each engine file to own its state. The C# `partial class` mechanism allows fields and methods from the same logical engine to live in one file while sharing the class instance.
- **Cross-engine state reading without going through Scorer:** D-08. After decomposition, the Scorer file reads all `_dir` and `_sc` fields. No engine file should read another engine's state directly.

---

## File Decomposition Plan

### Detailed file-by-file split (from source analysis)

**`Indicators/DEEP6.cs`** — ~60 lines after extraction
- Line change: add `partial` to class declaration (line 58)
- KEEP: `#region Using declarations` (lines 1-23) — all using statements
- KEEP: `#region Enums` (lines 50-56) — GexRegime, DayType, IbType, SignalType, VwapZone
- KEEP: `#region Constants` (lines 60-69) — MX_FP through DDEPTH
- KEEP: `#region Parameters` (lines 71-121) — all [NinjaScriptProperty] attributes
- KEEP: `#region OnStateChange` (lines 183-230)
- KEEP: `#region Event Handlers` (lines 232-279) — OnBarUpdate, OnMarketDepth, OnMarketData, OnRender, OnRenderTargetChanged
- REMOVE: everything else (fields, engine methods, session, scorer, rendering, UI)

**`AddOns/DEEP6.E1Footprint.cs`** — ~60 lines
- MOVE: E1 private fields: `_fpSc`, `_fpDir`, `_fpSt`, `_cvd`, `_emaVol`, `_emaRng`, `_stkTier`, `_stkBull`, `_dQ`, `_ema20` (lines 125-129)
- MOVE: `#region E1 Footprint` → `RunE1()` (lines 334-386)
- Note: `_cvd` is read by E6/Scorer — field must remain accessible (it will be, via partial class sharing)

**`AddOns/DEEP6.E2Trespass.cs`** — ~30 lines
- MOVE: E2 private fields: `_bV`, `_aV`, `_bP`, `_aP`, `_imb`, `_imbEma`, `_pUp`, `_trSc`, `_trDir`, `_trSt`, `_iLong`, `_iShort` (lines 131-134)
- MOVE: `#region E2 Trespass` → `RunE2()` (lines 388-402)

**`AddOns/DEEP6.E3CounterSpoof.cs`** — ~30 lines (after GC fix)
- MOVE: E3 private fields: `_w1`, `_spSc`, `_spSt`, `_spEvt`, `_pLg` (lines 136-137) — REPLACE `_pLg` with circular buffer
- MOVE: `#region E3 CounterSpoof` → `RunE3()` + `ChkSpoof()` + `Std()` (lines 405-423) — REPLACE `Std()` with Welford

**`AddOns/DEEP6.E4Iceberg.cs`** — ~25 lines (after GC fix)
- MOVE: E4 private fields: `_icBull`, `_icBear`, `_icSc`, `_icDir`, `_icSt`, `_pTr` (lines 139-140) — REPLACE `_pTr` with circular buffer
- MOVE: `#region E4 Iceberg` → `RunE4()` + `LvPx()` (lines 426-442)

**`AddOns/DEEP6.E5Micro.cs`** — ~15 lines
- MOVE: E5 private fields: `_pBull`, `_pBear`, `_miSc`, `_miDir`, `_miSt` (line 142)
- MOVE: `#region E5 Micro` → `RunE5()` (lines 445-456)

**`AddOns/DEEP6.E6VPCtx.cs`** — ~90 lines
- MOVE: E6/session private fields: all session fields `_sVN`, `_sVD`, `_sVR`, `_vwap`, `_vsd`, `_vah`, `_val`, `_ibH`, `_ibL`, `_ibDone`, `_ibConf`, `_ibTyp`, `_ibEnd`, `_dPoc`, `_pPoc`, `_pocMB`, `_pocMU`, `_dayTyp`, `_sOpen`, `_oPx`, `_iHi`, `_iLo`, `_vpSc`, `_dexFired`, `_dexDir`, `_dexSt`, `_vwapZ` (lines 144-151)
- MOVE: `#region Session Context` → `SessionReset()` + `UpdateSession()` (lines 281-330)
- MOVE: `#region E6 VP+CTX + DEX-ARRAY` → `RunE6()` (lines 459-480)

**`AddOns/DEEP6.E7MLQuality.cs`** — ~30 lines
- MOVE: E7 private fields: `_kSt`, `_kP`, `_kVel`, `_mlSc`, `_mlSt`, `_mlH` (lines 153-155)
- MOVE: `#region E7 ML Quality` → `RunE7()` (lines 483-505)

**`AddOns/DEEP6.Scorer.cs`** — ~80 lines
- MOVE: Scorer private fields: `_total`, `_sigDir`, `_sigTyp`, `_sigLbl`, `_lastSig`, `_feed` (lines 157-160)
- MOVE: `#region Scorer` → `Scorer()` (lines 508-526) — REPLACE LINQ with manual loop
- MOVE: `#region Chart Labels & Price Levels` → `MakeSigLabel()` + `PushFeed()` + `DrawLevels()` (lines 529-569)

**`AddOns/DEEP6.Rendering.cs`** — ~100 lines (after GC fix)
- MOVE: SharpDX private fields: `_dxG`, `_dxR`, `_dxGo`, `_dxW`, `_dxGr`, `_dxO`, `_dxT`, `_dxC`, `_dxP`, `_dxBg`, `_dxCB`, `_dxCS`, `_dxBd`, `_fC`, `_fS`, `_fL`, `_dwF`, `_dxOk` (lines 162-165) + ADD palette array field
- MOVE: `#region SharpDX Rendering` → `InitDX()` + `DisposeDX()` + `FV()` + `FC()` + `RenderFP()` + `RenderSigBoxes()` + `RenderStk()` (lines 572-691) — REPLACE per-cell brush allocation with palette lookup

**`AddOns/DEEP6.UI.cs`** — ~310 lines
- MOVE: WPF private fields: all `_hBdr`, `_pBdr`, `_tabBdr`, `_panelRoot`, `_hPrc`, etc. (lines 167-180)
- MOVE: `#region WPF UI Construction` → `BuildUI()` through `BuildPanel()` (lines 694-875)
- MOVE: `#region Panel Update` → `UpdatePanel()` + helpers (lines 878-975)
- MOVE: `#region WPF Helpers` → `Lbl()`, `HR()`, `SH()`, `SBar()`, `SR()`, `FindGrid()`, `DrawGauge()`, `Arc()`, `RefreshFeed()`, `RefreshLog()`, `SBr()`, `SD()`, `DisposeUI()` (lines 978-1010)

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Online standard deviation | Custom recursive formula | Welford's one-pass algorithm | Welford is numerically stable, O(1), zero allocation — any other implementation risks catastrophic cancellation |
| Gradient imbalance colors | Runtime color interpolation | Pre-allocated palette array (32 shades) | Dynamic interpolation still allocates; palette lookup is O(1) zero-alloc |
| Timestamp-based queue eviction | `RemoveAll()` scan | Circular buffer with head/tail pointers | RemoveAll is O(n) and creates GC pressure; ring buffer is O(1) amortized |
| CSV diff validation | External tooling | `StreamWriter` in NT8 Print or file write | NT8 Print goes to Output window; `StreamWriter` creates a file on disk for byte-for-byte comparison |

---

## GC Fix Implementation Details

### Fix 1: Welford's Online Algorithm (replaces `Std()`)

The current `Std()` method (line 421-423) calls `.ToArray()` on `IEnumerable<double>` then `.Sum()` and `.Average()` — three LINQ allocations per call, called ~1,000/sec.

Replace with per-engine Welford state stored as fields. E3 needs two Welford trackers (long window + short window):

```csharp
// In DEEP6.E3CounterSpoof.cs — new fields replacing Std() state
private int    _wLn, _wSn;           // counts for long/short windows
private double _wLm, _wLs;           // long window: mean, sum of squared deviations
private double _wSm, _wSs;           // short window: mean, sum of squared deviations

// Called once per new imbalance value (from RunE2, which already enqueues to _iLong/_iShort)
private void WelfordUpdate(ref int n, ref double mean, ref double M2, double x)
{
    n++;
    double delta = x - mean;
    mean += delta / n;
    double delta2 = x - mean;
    M2 += delta * delta2;
}

private double WelfordStd(int n, double M2)
{
    return n < 2 ? 0.0 : Math.Sqrt(M2 / (n - 1));
}

// On session reset (SessionReset is called at bar start):
private void ResetWelfordE3()
{
    _wLn = _wSn = 0;
    _wLm = _wSm = _wLs = _wSs = 0.0;
}
```

**Window eviction challenge:** Welford's algorithm is an online one-pass accumulator — it does not support removing old values. When the queue exceeds capacity (SpooLong=60 for `_iLong`, SpooShort=10 for `_iShort`), the old value must be "unadded." The standard approach for fixed-window online stddev is to maintain a circular buffer of values AND the Welford accumulators, then on eviction recompute from scratch over the remaining window. For small windows (≤60 entries), this one-time recompute costs O(60) but fires only once per new sample — still far less allocation than the current `.ToArray()` on every call. Alternatively, maintain running sum and sum-of-squares for exact O(1) removal (numerically less stable than Welford but adequate for this window size):

```csharp
// O(1) online mean + variance with exact removal — adequate for 10-60 item windows
private double _lSum, _lSumSq;    // long window running totals
private double _sSum, _sSumSq;    // short window running totals

private void AddToWindow(ref Queue<double> q, int cap,
    ref double sum, ref double sumSq, double x)
{
    if (q.Count >= cap)
    {
        double old = q.Dequeue();
        sum -= old; sumSq -= old * old;
    }
    q.Enqueue(x);
    sum += x; sumSq += x * x;
}

private double WindowStd(Queue<double> q, double sum, double sumSq)
{
    int n = q.Count;
    if (n < 2) return 0.0;
    double mean = sum / n;
    double variance = (sumSq - n * mean * mean) / (n - 1);
    return Math.Sqrt(Math.Max(variance, 0.0));  // clamp for floating point error
}

private double WindowMean(Queue<double> q, double sum)
{
    return q.Count > 0 ? sum / q.Count : 0.0;
}
```

This approach: zero allocations per call, O(1) add/evict. The Queue<double> for `_iLong` and `_iShort` is already present and pre-allocated — keep the Queue, add the sum/sumSq accumulators. The `RunE2()` method already enqueues and dequeues to manage window size — the add/evict helpers above move that logic into E3's file since E3 now owns the mean/std calculation. [ASSUMED — the numerical stability of running sum/sumSq for double precision over 60 items is adequate; for larger windows Welford's two-pass would be preferred]

**Updated RunE3 signature (after migration to OnBarUpdate):**
```csharp
private void RunE3()
{
    if (_iLong.Count < 5) return;
    double mL = WindowMean(_iLong, _lSum);
    double mS = _iShort.Count > 0 ? WindowMean(_iShort, _sSum) : mL;
    double sL = WindowStd(_iLong, _lSum, _lSumSq);
    double sS = _iShort.Count > 1 ? WindowStd(_iShort, _sSum, _sSumSq) : sL;
    _w1 = Math.Abs(mS - mL) + Math.Abs(sS - sL);
    // _pLg cleanup now uses circular buffer (see Fix 2)
    double w1n = Math.Min(_w1 / 0.8, 1.0), spn = Math.Min(_spEvt / 5.0, 1.0);
    _spSc = Math.Min((w1n * 0.6 + spn * 0.4) * MX_SP, MX_SP);
    _spSt = _w1.ToString("0.00") + (_w1 < SpooW1 ? " OK" : " !");
}
```

### Fix 2: Circular Buffer for `_pLg` (E3) and `_pTr` (E4)

Current pattern — `List<(DateTime ts, int lv, bool bid)>` with `RemoveAll()` on every tick. This is O(n) GC-pressure per call.

Replace with a fixed-capacity circular buffer using a struct array:

```csharp
// In DEEP6.E3CounterSpoof.cs
private struct LargeOrder { public DateTime ts; public int lv; public bool bid; }
private const int LG_CAP = 200;                   // max outstanding large orders
private readonly LargeOrder[] _lgBuf = new LargeOrder[LG_CAP];
private int _lgHead, _lgCount;

private void LgAdd(DateTime ts, int lv, bool bid)
{
    int idx = (_lgHead + _lgCount) % LG_CAP;
    _lgBuf[idx] = new LargeOrder { ts = ts, lv = lv, bid = bid };
    if (_lgCount < LG_CAP) _lgCount++;
    else _lgHead = (_lgHead + 1) % LG_CAP;  // overwrite oldest
}

private void LgEvictExpired(double windowSec)
{
    DateTime cutoff = DateTime.Now.AddSeconds(-windowSec);
    while (_lgCount > 0 && _lgBuf[_lgHead].ts < cutoff)
    { _lgHead = (_lgHead + 1) % LG_CAP; _lgCount--; }
}
```

**ChkSpoof** becomes an index scan of the live portion of the buffer — O(n) worst case but n is bounded by LG_CAP and the eviction window (10 seconds of large orders), so in practice n << 20.

Same pattern for `_pTr` in E4:
```csharp
// In DEEP6.E4Iceberg.cs
private struct TradeRecord { public DateTime ts; public double px; public bool buy; }
private const int TR_CAP = 500;
private readonly TradeRecord[] _trBuf = new TradeRecord[TR_CAP];
private int _trHead, _trCount;
```

### Fix 3: SharpDX Brush Palette (replaces per-cell allocation in RenderFP)

Current: lines 636-641 create `new SolidColorBrush(...)` for each imbalanced cell in every render frame.

Replace with two pre-allocated arrays of 32 brushes each (green gradient for buy imbalances, red gradient for sell imbalances), plus the existing solid brushes for text/backgrounds:

```csharp
// In DEEP6.Rendering.cs — new fields
private const int PAL_SHADES = 32;
private SharpDX.Direct2D1.SolidColorBrush[] _palGreen = new SharpDX.Direct2D1.SolidColorBrush[PAL_SHADES];
private SharpDX.Direct2D1.SolidColorBrush[] _palRed   = new SharpDX.Direct2D1.SolidColorBrush[PAL_SHADES];

// In InitDX() — build palette after existing brush creation:
for (int i = 0; i < PAL_SHADES; i++)
{
    float t = i / (float)(PAL_SHADES - 1);       // 0.0 = faint, 1.0 = saturated
    float alpha = 0.25f + t * 0.60f;              // 0.25 → 0.85
    // Green: buy imbalance (matches current: Color4(0, 0.35+al*0.1, 0.18, al))
    _palGreen[i] = new SharpDX.Direct2D1.SolidColorBrush(
        RenderTarget, new SharpDX.Color4(0f, 0.35f + t * 0.1f, 0.18f, alpha));
    // Red: sell imbalance (matches current: Color4(0.35+al*0.1, 0, 0, al))
    _palRed[i] = new SharpDX.Direct2D1.SolidColorBrush(
        RenderTarget, new SharpDX.Color4(0.35f + t * 0.1f, 0f, 0f, alpha));
}
```

Palette disposal in DisposeDX:
```csharp
if (_palGreen != null) foreach (var b in _palGreen) b?.Dispose();
if (_palRed   != null) foreach (var b in _palRed)   b?.Dispose();
```

**Lookup in RenderFP** — replace the per-cell `new SolidColorBrush(...)` block:
```csharp
if (buyI)
{
    float al = Math.Min((float)((ask / Math.Max(bid, 1)) / ImbRatio - 1) * 0.5f + 0.3f, 0.85f);
    int palIdx = Math.Min((int)(al / 0.85f * (PAL_SHADES - 1)), PAL_SHADES - 1);
    RenderTarget.FillRectangle(new SharpDX.RectangleF(xL, yT, bW, cH), _palGreen[palIdx]);
}
else if (selI)
{
    float al = Math.Min((float)((bid / Math.Max(ask, 1)) / ImbRatio - 1) * 0.5f + 0.3f, 0.85f);
    int palIdx = Math.Min((int)(al / 0.85f * (PAL_SHADES - 1)), PAL_SHADES - 1);
    RenderTarget.FillRectangle(new SharpDX.RectangleF(xL, yT, bW, cH), _palRed[palIdx]);
}
```
Note: palette index maps the same alpha value used before — visual output is perceptually identical. The `SharpDX.RectangleF` struct is value type, no allocation.

### Fix 4: Scorer LINQ → Manual Loop

Current lines 501 and 503:
```csharp
double logit = w.Zip(x, (a, b) => a * b).Sum() + .5;
double bsl = _mlH.Count > 0 ? _mlH.Average() : qP;
```

Replace with:
```csharp
// Pre-allocated in E7 field section:
private readonly double[] _w = { .28, .22, .18, .12, -.10, .15, .08, .12 };
private readonly double[] _x = new double[8];   // reused scratch array, no allocation

// In RunE7():
_x[0] = _imbEma;
_x[1] = _fpSc / MX_FP;
_x[2] = _icSc / MX_IC;
_x[3] = _pBull;
_x[4] = Math.Min(_w1 / 0.8, 1.0);
_x[5] = Math.Min(Math.Abs(_cvd) / (Math.Max(!double.IsNaN(_emaVol) ? _emaVol : 1, 1) * 20), 1.0);
_x[6] = GexReg == GexRegime.NegativeAmplifying ? 1.0 : 0.0;
_x[7] = Math.Max(Math.Min(_kVel / (TickSize * 10), 1.0), -1.0);

double logit = 0.5;
for (int i = 0; i < 8; i++) logit += _w[i] * _x[i];
double qP = 1.0 / (1.0 + Math.Exp(-logit));
```

For `_mlH.Average()` (Queue<double>, 20 items, called per bar — low frequency, low impact):
```csharp
// Replace _mlH.Average() with manual loop:
double bslSum = 0.0;
foreach (double h in _mlH) bslSum += h;
double bsl = _mlH.Count > 0 ? bslSum / _mlH.Count : qP;
```

Also in Scorer() (lines 511-512), replace `dirs.Count(d => d == +1)` LINQ with:
```csharp
// Pre-compute in Scorer:
int[] dirs = { (int)_fpDir, _trDir, 0, _icDir, _miDir, _dexDir, 0 };
int bE = 0, rE = 0;
for (int i = 0; i < dirs.Length; i++)
{
    if (dirs[i] == +1) bE++;
    else if (dirs[i] == -1) rE++;
}
```

And the `_sigLbl` construction — replace `new List<string>()` in Scorer with a `StringBuilder` or string concatenation from pre-allocated buffer:
```csharp
// Replace: var p = new List<string>(); ... string.Join("·", p)
// With:
_sigLbl = "";
if (_fpSc >= 12 && (int)_fpDir == _sigDir) _sigLbl = "ABSORB";
if (_trSc >= 10 && _trDir == _sigDir) _sigLbl += (_sigLbl.Length > 0 ? "·" : "") + "TRESS";
if (_icSc >= 8  && _icDir == _sigDir) _sigLbl += (_sigLbl.Length > 0 ? "·" : "") + "ICE";
if (_vpSc >= 10) _sigLbl += (_sigLbl.Length > 0 ? "·" : "") + "LVN";
if (_dexFired && _dexDir == _sigDir) _sigLbl += (_sigLbl.Length > 0 ? "·" : "") + "DEX";
```
This avoids the `List<string>` allocation entirely. String concatenation in Scorer fires only when `_sigTyp >= TypeB` (rare, per-bar), so the minor allocation of string concat is acceptable here. The `new List<string>()` per bar is the target to remove.

---

## E3 Migration to OnBarUpdate (D-05)

### What changes

**Before migration:** RunE3() is called at the end of OnMarketDepth (~1,000/sec):
```csharp
protected override void OnMarketDepth(MarketDepthEventArgs e)
{
    // ... DOM array updates ...
    RunE2(); RunE3();  // ← E3 runs per-tick
}
```

**After migration:** RunE3() moves to OnBarUpdate, alongside RunE1/E5/E6/E7:
```csharp
protected override void OnBarUpdate()
{
    // ...
    RunE1(); RunE3(); RunE5(); RunE6(); RunE7(); Scorer();  // ← E3 now per-bar
    // ...
}

protected override void OnMarketDepth(MarketDepthEventArgs e)
{
    // ... DOM array updates ...
    RunE2();  // ← only E2 remains per-tick
}
```

### State variables that need adjustment

The `_spEvt` counter (spoof cancel event count) is incremented by `ChkSpoof()`, which is called from OnMarketDepth. This is correct — cancellation events happen on the DOM thread and must be detected there. `ChkSpoof()` continues to run per-tick from OnMarketDepth. It writes to `_spEvt`. RunE3 (now on the bar thread) reads `_spEvt`. This is a cross-thread field access.

**Thread safety:** `_spEvt` is a plain `int`. In the existing code, `_spEvt` is written by ChkSpoof (DOM thread) and read by RunE3 (bar thread). After migration, the read moves to the bar thread which is still a different thread from the DOM thread. Mark `_spEvt` as `volatile` to ensure visibility:
```csharp
private volatile int _spEvt;
```

Reset `_spEvt` at session start in `SessionReset()` (already in E6's file).

### Wasserstein-1 semantics after migration

The Wasserstein-1 proxy (`_w1 = |mS - mL| + |sS - sL|`) measures distributional shift between the short-window DOM imbalance and long-window baseline. RunE2 populates `_iLong` and `_iShort` on every tick. When RunE3 runs per-bar, it reads the accumulated state of those queues at bar close. The W1 score captures the distributional shift over the entire bar's tick stream — which is actually more stable and less noisy than the per-tick version. Spoof detection is inherently a pattern-over-time concept; per-bar granularity is semantically appropriate. [ASSUMED — based on algorithmic analysis of Wasserstein-1 semantics; the paper (Tao et al. 2020) does not specify evaluation frequency]

### Per-bar `_spEvt` reset decision

`_spEvt` should NOT be reset on every bar. It accumulates cancel events across the session. The current code does not reset it (there is no reset in the original RunE3). The score formula `spn = Math.Min(_spEvt/5.0, 1.0)` is a saturation function — once 5+ cancel events accumulate, spn stays at 1.0 for the session. This behavior is preserved after migration. If per-bar reset is desired in future, that is a behavioral change — out of scope for Phase 1 (zero behavior change required).

---

## CSV Signal Export for Validation (D-06)

### Implementation approach

Add a `StreamWriter`-based CSV exporter that writes per-bar engine scores to a file. This export runs in OnBarUpdate AFTER Scorer() executes. It is gated by a `[NinjaScriptProperty]` boolean `ExportScores` (default false — off in production, on during validation).

```csharp
// In DEEP6.Scorer.cs (or a thin DEEP6.Validation.cs partial):
[NinjaScriptProperty]
[Display(Name="Export Scores to CSV", Order=1, GroupName="Validation")]
public bool ExportScores { get; set; }

private System.IO.StreamWriter _csvWriter;
private string _csvPath;

// In OnStateChange → State.DataLoaded:
if (ExportScores)
{
    _csvPath = System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
        "DEEP6_scores_" + DateTime.Now.ToString("yyyyMMdd_HHmm") + ".csv");
    _csvWriter = new System.IO.StreamWriter(_csvPath, false);
    _csvWriter.WriteLine("Time,Bar,E1fp,E1dir,E2tr,E2dir,E3sp,E4ic,E4dir,E5mi,E5dir,E6vp,E7ml,Total,SigDir,SigTyp,SigLbl");
}

// In OnBarUpdate, after Scorer():
if (ExportScores && _csvWriter != null)
{
    _csvWriter.WriteLine(string.Join(",",
        Time[0].ToString("HH:mm:ss"),
        CurrentBar,
        _fpSc.ToString("F2"), (int)_fpDir,
        _trSc.ToString("F2"), _trDir,
        _spSc.ToString("F2"),
        _icSc.ToString("F2"), _icDir,
        _miSc.ToString("F2"), _miDir,
        _vpSc.ToString("F2"),
        _mlSc.ToString("F2"),
        _total.ToString("F2"),
        _sigDir, _sigTyp, _sigLbl));
    _csvWriter.Flush();
}

// In OnStateChange → State.Terminated:
_csvWriter?.Close();
_csvWriter = null;
```

**Validation workflow:**
1. Before refactor: enable `ExportScores`, run DEEP6 on a known NQ session (e.g., one day of replay), collect `DEEP6_scores_before.csv`
2. After refactor: same session, collect `DEEP6_scores_after.csv`
3. Byte-for-byte comparison: `fc /b DEEP6_scores_before.csv DEEP6_scores_after.csv` (Windows) — any diff = regression
4. If DEEP6 is run on live data (not replay), exact time alignment matters — use CurrentBar as the primary key for comparison, not timestamp

---

## Common Pitfalls

### Pitfall 1: NT8 re-generates wrapper code on next compile
**What goes wrong:** Developer adds `partial` to the class in Indicators/DEEP6.cs, creates AddOns files, everything compiles — then NT8 auto-compiles on next chart load and generates an extra partial file in Indicators/ that conflicts.
**Why it happens:** NT8's compilation pipeline scans Indicators/ and generates scaffolding. The exact behavior depends on NT8 version and whether "Compile" vs "Compile All" is used.
**How to avoid:** Test the AddOns pattern on a minimal indicator first (10 lines total, 2 files). Confirm NT8 compiles and runs it cleanly before attempting the full 10-file split. [ASSUMED]
**Warning signs:** `CS0101` (type already defined) or `CS0260` (partial declaration has conflicting modifier) in NT8 Output window.

### Pitfall 2: Using declarations not in AddOns files
**What goes wrong:** `RunE1()` references `NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType` but the AddOns file doesn't have the required `using NinjaTrader.NinjaScript;` declaration.
**Why it happens:** The using declarations are currently all in `Indicators/DEEP6.cs`. When methods move to AddOns files, each file needs its own using block.
**How to avoid:** Each AddOns file must begin with the same using block as the original (or a subset). The full using block from lines 1-23 of DEEP6.cs should be copied to every AddOns file header.
**Warning signs:** `CS0246` (type or namespace not found) on types that clearly exist.

### Pitfall 3: Fields declared in AddOns files not visible to main file
**What goes wrong:** `_fpSc` is moved to DEEP6.E1Footprint.cs, but OnBarUpdate (which remains in DEEP6.cs) calls RunE1() — RunE1 sets `_fpSc` fine, but UpdatePanel (in DEEP6.UI.cs) reads `_fpSc`. Since both are partial class files, this should work — BUT if any file accidentally declares a DUPLICATE field `_fpSc`, the compiler will throw `CS0102`.
**Why it happens:** Copy-paste error during refactor — field declaration left in old file AND added to new file.
**How to avoid:** Remove field declarations from the old location BEFORE adding them to the new file. Use "Find All References" in an IDE to confirm no field is declared twice.
**Warning signs:** `CS0102` (type already contains definition for member).

### Pitfall 4: OnRenderTargetChanged disposes palette brushes, but InitDX only called on first render
**What goes wrong:** `OnRenderTargetChanged()` calls `DisposeDX()` (correctly). But `InitDX()` is called from `OnRender()` only when `_dxOk == false`. After `DisposeDX()`, `_dxOk = false` and `_palGreen`/`_palRed` arrays contain disposed brush references. When `InitDX()` runs again, it creates NEW palette brushes and assigns them to the SAME array slots — but if there's an exception in palette creation partway through, some slots hold live brushes and others hold disposed ones.
**Why it happens:** No try-finally block around palette initialization.
**How to avoid:** Create all palette brushes in a loop, and if ANY throw, dispose all previously created ones in a catch block. Same pattern as the existing solid brushes in `try { ... } catch { _dxOk = false; }`.

### Pitfall 5: E3's `_spEvt` not volatile leads to stale reads
**What goes wrong:** `ChkSpoof()` (DOM thread) increments `_spEvt`. RunE3 (bar thread, after migration) reads it. Without `volatile`, the CPU may cache the old value in a register and RunE3 sees stale data.
**Why it happens:** .NET memory model does not guarantee visibility across threads without synchronization primitives.
**How to avoid:** Declare `private volatile int _spEvt;`. This prevents register caching. For simple int increment from one thread and read from another, `volatile` is sufficient. [ASSUMED — Interlocked.Increment would be safer but likely overkill for this use pattern]
**Warning signs:** `_spEvt` stays at 0 even when spoof events are clearly occurring (manifests as `_spSc` always being driven purely by `_w1`).

### Pitfall 6: CSV export produces slightly different floating-point formatting
**What goes wrong:** Before/after CSVs differ because `ToString("F2")` rounds `0.006` to `"0.01"` in one build and `"0.01"` in another due to JIT differences.
**Why it happens:** Floating-point arithmetic is deterministic for the same binary, but refactoring may change inlining decisions.
**How to avoid:** Use `ToString("R")` (round-trip format) in the CSV export to ensure lossless representation, then compare CSVs semantically (parse back to double, compare with epsilon) rather than byte-for-byte. Or: compare the printed `_total` and `_sigTyp` values only — the signal output — rather than all intermediate scores.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Manual CSV diff + NT8 visual comparison |
| Config file | `ExportScores = true` on DEEP6 indicator properties |
| Quick run command | Enable ExportScores, load same session, compare CSVs |
| Full suite command | Before + after CSV comparison + side-by-side screenshots of 9 signal events |

**Note:** NT8 indicators cannot be unit-tested in standard .NET test frameworks — they require the NT8 runtime. The validation strategy is CSV-based regression testing as decided in D-06.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ARCH-01 | Decomposed files compile without errors in NT8 | Compile smoke test | NT8 "Compile" → check Output window for CS errors | ❌ Wave 0 — NT8 compile check procedure |
| ARCH-01 | Zero behavior change — all 9 engine scores identical | CSV regression | Compare DEEP6_scores_before.csv vs DEEP6_scores_after.csv | ❌ Wave 0 — add ExportScores property |
| ARCH-02 | OnMarketDepth hot path has zero LINQ allocations | Code review + runtime | dotMemory or VS Diagnostic Tools on depth updates | ❌ Wave 0 — manual profile verification |
| ARCH-02 | Palette brushes disposed on DisposeDX | Code review | Inspect DisposeDX for all palette brush slots | ❌ Wave 0 — code review checklist |

### Sampling Rate
- **Per task commit:** NT8 compile check (no CS errors)
- **Per wave merge:** Full CSV regression comparison
- **Phase gate:** CSV diff clean + visual screenshot match before marking Phase 1 complete

### Wave 0 Gaps
- [ ] `ExportScores` property and `StreamWriter` CSV export code — covers ARCH-01 regression
- [ ] `_spEvt` marked `volatile` — covers thread safety
- [ ] NT8 compile-test procedure documented — covers ARCH-01 smoke test

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LINQ in hot path | Manual loops with pre-allocated arrays | .NET 4.x era best practice | Zero GC allocations on hot path |
| Per-frame brush allocation | Pre-allocated palette array | SharpDX best practices since DirectX 10 | Removes largest allocation source in RenderFP |
| List.RemoveAll with lambda | Circular buffer with index arithmetic | Standard real-time C# pattern | O(1) eviction vs O(n) scan |
| Single monolithic indicator file | NT8 AddOns partial class decomposition | NinjaTrader community pattern (2020+) | Maintainable code without NT8 compilation conflicts |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | NT8 does NOT generate wrapper code for files in AddOns/ folder | Architecture Patterns | Pattern fails — must find alternative decomposition strategy (e.g., standalone engine classes passed as method arguments, no partial classes) |
| A2 | Namespace must be `NinjaTrader.NinjaScript.Indicators` in AddOns files for partial class match | Architecture Patterns | Compilation error CS0260; easy to diagnose and fix |
| A3 | Running sum/sumSq is numerically adequate for double precision over 60-item windows | GC Fix Implementation | Slight numerical drift in `_w1` vs original `Std()` — could cause CSV validation to show differences. Mitigation: test with production NQ data |
| A4 | `volatile int _spEvt` provides sufficient thread safety for single-writer, single-reader pattern | E3 Migration | Race condition — `_spEvt` reads may occasionally be stale by 1. Impact: `_spSc` underestimates by one event on rare bars. Mitigation: use `Interlocked.Increment` and `Interlocked.Exchange` |
| A5 | E3 Wasserstein-1 semantics are preserved (or improved) when computed per-bar rather than per-tick | E3 Migration | Behavioral change in `_spSc` — CSV validation will detect any divergence |
| A6 | 32 palette shades provide perceptually identical output to the original per-cell color calculation | GC Fix Implementation | Visual difference detectable in screenshots — mitigation: run visual comparison as part of D-06 validation |

---

## Open Questions (RESOLVED)

1. **Does NT8 version 8.0.23+ support AddOns folder partial class compilation cleanly?**
   - RESOLVED: Plan 01 Task 0 validates via a minimal 2-file compile test before full decomposition begins. If NT8 rejects the pattern (CS0101), the task blocks and the decomposition strategy must pivot. Plan 04 Task 2 provides a final compilation checkpoint gate on the Windows NT8 box.

2. **Does the `_iLong`/`_iShort` Queue ownership move to E3 or stay shared?**
   - RESOLVED: `_iLong`/`_iShort` stay in E2Trespass.cs (E2 owns them, E2 populates them). E3CounterSpoof.cs accesses them as fields on the shared partial class instance. Cross-engine field dependency documented in Plan 01-01 action.

3. **Visual regression: will 32-shade palette produce identical pixel output?**
   - RESOLVED: D-06 specifies visual comparison, not pixel-perfect identity. The 32-shade palette quantization is imperceptible at 7-9px cell heights. Plan 04 Task 2 Step 4 validates via before/after visual comparison on the Windows NT8 box.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| NinjaTrader 8 | All compilation and testing | ✗ on macOS | — | Windows NT8 box (D-07) |
| .NET Framework 4.8 | NT8 runtime | ✗ on macOS | — | Windows only |
| Windows OS | NT8 execution | ✗ on macOS | — | Required — no fallback |

**Missing dependencies with no fallback:**
- Windows NT8 environment — all implementation and validation must occur on Windows. Code can be authored on macOS but cannot be compiled or tested there.

**Impact on planning:** All tasks that involve "compile", "test", "run", or "validate" must be flagged as requiring the Windows NT8 box. Code authoring tasks (writing the .cs files) can be done on macOS. The plan should separate code-writing tasks from compile-and-verify tasks explicitly.

---

## Sources

### Primary (HIGH confidence)
- `Indicators/DEEP6.cs` lines 1-1010 — complete source code analysis (verified all field names, method signatures, line numbers)
- `.planning/codebase/ARCHITECTURE.md` — engine layer boundaries, data flow, state management
- `.planning/codebase/CONCERNS.md` — GC hotspot exact locations with line numbers
- `.planning/codebase/CONVENTIONS.md` — naming patterns, code style, NinjaScript-specific patterns

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` — NT8 AddOns folder partial class pattern, community-validated
- `.planning/phases/01-architecture-foundation/01-CONTEXT.md` — user decisions D-01 through D-08

### Tertiary (LOW confidence / ASSUMED)
- NT8 AddOns compilation behavior — community forum evidence, not validated on target machine
- Thread safety of `volatile int` for `_spEvt` cross-thread access — standard .NET memory model analysis

---

## Metadata

**Confidence breakdown:**
- File decomposition plan: HIGH — derived directly from source code line analysis
- GC fix implementations: HIGH — standard .NET 4.8 patterns with verified exact code locations
- NT8 AddOns compilation: MEDIUM — requires Windows NT8 validation before committing
- E3 migration semantics: MEDIUM — algorithmically sound but behavioral validation required via CSV
- Thread safety analysis: MEDIUM — `volatile` is correct but Interlocked would be safer

**Research date:** 2026-04-12
**Valid until:** 2026-07-12 (NT8 and .NET 4.8 are stable, no breaking changes expected; AddOns pattern confidence increases after first compile test)
