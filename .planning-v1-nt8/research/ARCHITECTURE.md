# Architecture Patterns: DEEP6 v2.0 — 44-Signal Footprint System

**Domain:** Institutional footprint auto-trading system (NQ futures, NT8, Rithmic L2)
**Researched:** 2026-04-11
**Overall confidence:** HIGH (NT8 constraints) / MEDIUM (scoring algorithm design)
**Milestone context:** Evolving from monolithic 1,010-line indicator to multi-component system

---

## Recommended Architecture

### System Boundary Map

```
┌─────────────────────────────────────────────────────────────────────┐
│  NinjaTrader 8 Process (Windows, .NET 4.8)                          │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  DEEP6.cs  (Facade + NT8 lifecycle owner)                   │    │
│  │  - OnStateChange / OnBarUpdate / OnMarketDepth              │    │
│  │  - OnMarketData / OnRender                                  │    │
│  │  - Owns: SessionContext, Scorer, SignalBus, IpcBridge       │    │
│  └───┬───────┬───────┬───────┬───────┬───────┬──────┬─────────┘    │
│      │       │       │       │       │       │      │               │
│  ┌───▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐        │
│  │ E1   │ │ E2  │ │ E3  │ │ E4  │ │ E5  │ │ E6  │ │ E7  │        │
│  │FTPRT │ │TRES │ │SPOOF│ │ICBG │ │MICRO│ │VCTX │ │ML   │        │
│  └──────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  E8 CVD      │  │  E9 AUCTION  │  │  ZoneRegistry            │  │
│  │  Engine      │  │  StateMachine│  │  (LVN/HVN + GEX + zones) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  Scorer (SignalBus consumer)                                  │   │
│  │  - 44-signal weighted cascade scoring                        │   │
│  │  - Zone/level interaction bonuses                            │   │
│  │  - Confluence multiplier (5+ category agreement)             │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ExecutionLayer (Strategy or indicator-triggered ATM)        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  IpcBridge (TcpClient, background thread, JSON payload)      │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
         │ TCP JSON (fire-and-forget, non-blocking)
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Python ML Backend (FastAPI, separate process, Windows localhost) │
│  - Signal history ingestion                                       │
│  - Regime detection (HMM or clustering)                          │
│  - Weight evolution (Bayesian or gradient-based)                 │
│  - Trade outcome attribution per engine                          │
└──────────────────────────────────────────────────────────────────┘
         │ REST API
         ▼
┌──────────────────────────────────────────────────────────────────┐
│  Next.js Dashboard (browser)                                     │
│  - Signal history, regime state, weight evolution charts         │
└──────────────────────────────────────────────────────────────────┘
```

---

## NT8 File Decomposition Strategy

### The Core Constraint

NinjaTrader 8 auto-generates wrapper code for every file in the Indicators folder that inherits from `Indicator`. If you place a second file with `partial class DEEP6` in the Indicators folder, NT8 will try to add wrapper code to both files, causing compilation errors. (MEDIUM confidence — based on community forum evidence.)

### Recommended Pattern: AddOns Folder for Engine Classes

The correct NT8 pattern for modularizing a large indicator is:

1. **Main file** (`Indicators/DEEP6.cs`) — inherits `Indicator`, owns all NT8 lifecycle methods. This is the only file NT8 knows about as an indicator. Keeps the `partial class DEEP6` facade.

2. **AddOns partial files** (`AddOns/DEEP6.E1Footprint.cs`, etc.) — same namespace `NinjaTrader.NinjaScript.Indicators`, declared as `partial class DEEP6`. NT8 does NOT auto-generate wrapper code for files in the AddOns folder, so partial classes there are safe. Files in AddOns are compiled into the same assembly.

3. **Engine host classes** (inside AddOns files) — standalone C# classes (not inheriting anything from NT8) that receive data as method arguments and return result structs. These are plain C# and can be unit-tested in isolation.

```
Documents/NinjaTrader 8/bin/Custom/
├── Indicators/
│   └── DEEP6.cs                    ← NT8 facade + lifecycle only
├── AddOns/
│   ├── DEEP6.Engines.cs            ← IEngine interface + EngineResult struct
│   ├── DEEP6.E1Footprint.cs        ← FootprintEngine class + partial DEEP6 RunE1()
│   ├── DEEP6.E2Trespass.cs         ← TrespassEngine class + partial DEEP6 RunE2()
│   ├── DEEP6.E3Counterspoof.cs     ← CounterspoofEngine class + partial DEEP6 RunE3()
│   ├── DEEP6.E4Iceberg.cs          ← IcebergEngine class + partial DEEP6 RunE4()
│   ├── DEEP6.E5Micro.cs            ← MicroEngine class + partial DEEP6 RunE5()
│   ├── DEEP6.E6VPCtx.cs            ← VPCtxEngine class + partial DEEP6 RunE6()
│   ├── DEEP6.E7MLQuality.cs        ← MLQualityEngine class + partial DEEP6 RunE7()
│   ├── DEEP6.E8CVD.cs              ← CvdEngine class + partial DEEP6 RunE8()
│   ├── DEEP6.E9Auction.cs          ← AuctionStateMachine + partial DEEP6 RunE9()
│   ├── DEEP6.ZoneRegistry.cs       ← ZoneRegistry class + partial DEEP6 zone methods
│   ├── DEEP6.Scorer.cs             ← ScoringEngine class + partial DEEP6 Scorer()
│   ├── DEEP6.SessionContext.cs     ← SessionContext struct + partial DEEP6 session methods
│   ├── DEEP6.Rendering.cs          ← partial DEEP6 SharpDX render methods
│   ├── DEEP6.UI.cs                 ← partial DEEP6 WPF build/update methods
│   └── DEEP6.IpcBridge.cs          ← IpcBridge class + partial DEEP6 push methods
```

### What Goes in Each Partial File

Each AddOns file contains two things:
- A **standalone class** with the algorithmic logic (receives inputs by argument, returns `EngineResult`)
- A **thin partial DEEP6 method** that connects NT8 state to the standalone class

This separation means the algorithmic core can be tested outside NT8 (on a test console app or in a separate .NET Framework 4.8 test project). The NT8 lifecycle methods remain only in `DEEP6.cs`.

### Compilation Caution

When exporting as a compiled assembly (`.dll`), ALL AddOns files must be included in the export. If any file is missed, NT8 will throw `CS0103` (name not found). This is a known limitation. Document the export checklist explicitly.

---

## Component Boundaries

| Component | Responsibility | Inputs | Outputs | Thread |
|-----------|---------------|--------|---------|--------|
| DEEP6.cs (Facade) | NT8 lifecycle owner; routes callbacks to engines | NT8 callbacks | — | NT8 main |
| SessionContext | VWAP, IB, POC, DayType, VwapZone | Bar OHLCV + VolumetricBarsType | SessionSnapshot struct | Bar thread |
| E1 FootprintEngine | Absorption/exhaustion/imbalance/CVD signals (core 4 categories) | VolumetricBarsType per bar | EngineResult (score, dir, fired signals[]) | Bar thread |
| E2 TrespassEngine | DOM queue imbalance + logistic regression | DOM arrays (hot path) | EngineResult | Depth thread |
| E3 CounterspoofEngine | Wasserstein-1 + cancel detection | DOM large orders (hot path) | EngineResult | Depth thread |
| E4 IcebergEngine | Native/synthetic iceberg detection | Last trade events | EngineResult | Data thread |
| E5 MicroEngine | Naive Bayes combination of E1/E2/E4 | E1, E2, E4 likelihoods | EngineResult | Bar thread |
| E6 VPCtxEngine | DEX-ARRAY + VWAP/IB/POC/GEX context | SessionSnapshot + ZoneRegistry | EngineResult | Bar thread |
| E7 MLQualityEngine | Kalman filter + logistic quality classifier | Bar OHLCV + history | EngineResult (quality multiplier) | Bar thread |
| E8 CvdEngine | Multi-bar CVD divergence via linear regression | CVD series (N bars) | EngineResult | Bar thread |
| E9 AuctionStateMachine | FSM: unfinished business / finished auction / poor H/L / void | Bar series + volume profile | AuctionState enum + EngineResult | Bar thread |
| ZoneRegistry | Create/defend/break/flip/invalidate zones (LVN + absorption zones + GEX) | VolumetricBarsType + GEX API + signal events | ZoneCollection | Bar thread |
| Scorer | 44-signal weighted cascade → 0-100 unified score + confluence multiplier | All EngineResults + ZoneCollection | ScorerResult (total, dir, type, label) | Bar thread |
| ExecutionLayer | NT8 ATM order entry/exit from ScorerResult | ScorerResult | NT8 orders | Bar thread |
| IpcBridge | Non-blocking fire-and-forget TCP push of ScorerResult + signal snapshot | ScorerResult + SignalSnapshot | JSON over TCP to Python | Background thread |
| UI/Rendering | WPF + SharpDX visual display | ScorerResult + ZoneCollection + SessionSnapshot | Chart canvas + WPF panels | Render thread |

---

## Data Flow: Signal Detection to Execution

### Hot Path (Depth Thread, ~1,000/sec)

```
Rithmic L2 update
  → OnMarketDepth(e)
      → DOM arrays updated (_bV, _aV, _bP, _aP)
      → E2_TrespassEngine.Update(domArrays) → EngineResult stored (volatile double)
      → E3_CounterspoofEngine.Update(domArrays, largeOrderLog) → EngineResult stored
      [No scoring. No UI. No allocation in hot path.]
```

### Tick Path (Data Thread, per trade)

```
Last trade event
  → OnMarketData(e)
      → E4_IcebergEngine.Update(trade, domArrays) → EngineResult stored
      [Returns immediately. No allocation.]
```

### Bar Path (Bar Thread, per bar close + real-time ticks)

```
Bar update
  → OnBarUpdate()
      → SessionContext.Update(bar, volumetric) → SessionSnapshot
      → E1_FootprintEngine.Run(bar, volumetric, sessionSnap) → EngineResult[signals[]]
      → E8_CvdEngine.Run(cvdSeries) → EngineResult
      → E9_AuctionStateMachine.Transition(bar, volumetric, sessionSnap) → AuctionState + EngineResult
      → E5_MicroEngine.Run(e1Result, e2Result, e4Result) → EngineResult
      → E6_VPCtxEngine.Run(sessionSnap, zoneRegistry, e1Result) → EngineResult
      → E7_MLQualityEngine.Run(bar, mlHistory) → EngineResult (quality multiplier)
      → ZoneRegistry.Update(bar, e1Result, gexLevels, volumetric) [zone lifecycle]
      → Scorer.Score(allEngineResults, zoneRegistry, sessionSnap) → ScorerResult
      → If ScorerResult.type >= TypeB:
          → ExecutionLayer.Evaluate(scorerResult, positionState) → ATM order or pass
          → IpcBridge.PushAsync(scorerResult, signalSnapshot) [fire-and-forget, no await]
          → RenderingState.Enqueue(scorerResult)
      → Plot() → Draw.Text() signal labels
      → UpdatePanel() via Dispatcher.InvokeAsync
```

### Render Path (Render Thread, every chart repaint)

```
OnRender()
  → RenderFP() — footprint cells from cached volumetric data
  → RenderZones() — LVN/GEX/absorption zone boxes from ZoneRegistry
  → RenderSigBoxes() — signal feed labels from RenderingState queue
  → RenderStk() — STKt markers
```

### Thread Safety Rules

- Engine results shared between depth/bar threads MUST be `volatile double` fields on the facade (current pattern — keep it).
- ZoneRegistry is only mutated on the bar thread (OnBarUpdate). OnRender reads it for display — this is a read from the render thread while bar thread may write. Protect with a `ReaderWriterLockSlim` or snapshot-and-swap pattern (copy zone list before each render).
- IpcBridge runs on a background thread. Queue entries with `ConcurrentQueue<T>`. Background thread dequeues and sends. No blocking on bar thread.

---

## The 44-Signal Scoring Algorithm

### Design Principle

The system has two distinct layers of scoring:

1. **Engine layer** — each of the 9 engines produces a score (0 to its max) and a direction. This is the current architecture.
2. **Signal layer** — each engine fires specific named signals. The scorer knows which signals fired. Signal-layer scoring enables zone-interaction bonuses, category-level confluence, and priority cascade weighting.

### EngineResult Struct

```csharp
public struct EngineResult
{
    public double Score;           // 0 to MaxScore
    public int Direction;          // +1 bull, -1 bear, 0 neutral
    public SignalFlags Fired;      // bitmask of which named signals fired
    public int CategoryMask;       // which of 8 categories contributed
}

[Flags]
public enum SignalFlags : ulong
{
    // Imbalance (bits 0-8)
    ImbSingle        = 1UL << 0,
    ImbStacked_T1    = 1UL << 1,
    ImbStacked_T2    = 1UL << 2,
    ImbStacked_T3    = 1UL << 3,
    ImbReverse       = 1UL << 4,
    ImbInverse       = 1UL << 5,
    ImbOversized     = 1UL << 6,
    ImbDiagonal      = 1UL << 7,
    ImbReversal      = 1UL << 8,

    // Delta (bits 9-19)
    DeltaRise        = 1UL << 9,
    DeltaDrop        = 1UL << 10,
    DeltaTail        = 1UL << 11,
    DeltaReversal    = 1UL << 12,
    DeltaDivergence  = 1UL << 13,
    DeltaFlip        = 1UL << 14,
    DeltaTrap        = 1UL << 15,
    DeltaSweep       = 1UL << 16,
    DeltaSlingshot   = 1UL << 17,
    DeltaAtMin       = 1UL << 18,
    DeltaAtMax       = 1UL << 19,

    // Absorption (bits 20-23)
    AbsorbClassic    = 1UL << 20,
    AbsorbPassive    = 1UL << 21,
    AbsorbStopping   = 1UL << 22,
    AbsorbEffort     = 1UL << 23,

    // Exhaustion (bits 24-29)
    ExhZeroPrint     = 1UL << 24,
    ExhExhPrint      = 1UL << 25,
    ExhThinPrint     = 1UL << 26,
    ExhFatPrint      = 1UL << 27,
    ExhFadeMom       = 1UL << 28,
    ExhBidAskFade    = 1UL << 29,

    // Auction Theory (bits 30-34)
    AuctUnfinished   = 1UL << 30,
    AuctFinished     = 1UL << 31,
    AuctPoorHL       = 1UL << 32,
    AuctVolumeVoid   = 1UL << 33,
    AuctSweep        = 1UL << 34,

    // Trapped Traders (bits 35-39)
    TrapInvImbalance = 1UL << 35,
    TrapDelta        = 1UL << 36,
    TrapFalseBreak   = 1UL << 37,
    TrapHVRejection  = 1UL << 38,
    TrapCVD          = 1UL << 39,

    // Volume Patterns (bits 40-45)
    VolSequencing    = 1UL << 40,
    VolBubble        = 1UL << 41,
    VolSurge         = 1UL << 42,
    VolPOCWave       = 1UL << 43,
    VolDeltaVelocity = 1UL << 44,
    VolBigDeltaLevel = 1UL << 45,

    // POC/Value Area (bits 46-53)
    POCAbove         = 1UL << 46,
    POCBelow         = 1UL << 47,
    POCExtreme       = 1UL << 48,
    POCContinuous    = 1UL << 49,
    POCGap           = 1UL << 50,
    POCDelta         = 1UL << 51,
    VAEngulf         = 1UL << 52,
    VAGap            = 1UL << 53,
}
```

### Priority Cascade: Narrative Classification

Adopt the Pine Script's narrative hierarchy, but implement it as a scoring cascade, not an exclusive branch. Every bar gets a primary narrative label based on which signals are present, but ALL signals still contribute points:

```
Priority Order (for label/narrative):
  1. Absorption (AbsorbClassic | AbsorbPassive | AbsorbStopping)  ← highest signal quality
  2. Exhaustion  (ExhZeroPrint | ExhExhPrint | ExhFatPrint | ExhFadeMom)
  3. Momentum    (DeltaVelocity | DeltaTrap | DeltaSlingshot | TrapInvImbalance)
  4. Rejection   (ImbReversal | DeltaReversal | TrapHVRejection)
  5. Quiet       (no primary signal)

Narrative label = highest priority category with ≥1 signal fired in signal direction
Score = sum of ALL fired signals (no exclusion)
```

### Category Weights

Derived from the Pine Script zone scoring (type:25 + volume:25 + touches:25 + recency:25) and the project's stated signal hierarchy:

| Category | Max Points | Rationale |
|----------|-----------|-----------|
| Absorption | 22 | Highest alpha per project thesis |
| Exhaustion | 20 | Second highest alpha |
| Trapped Traders | 16 | Inverse imbalance = 80-85% win rate per research |
| Delta | 14 | Direction confirmation |
| Volume Patterns | 10 | Context + confirmation |
| Auction Theory | 8 | Structural context |
| Imbalance | 6 | Base confirmation (already captured in E1) |
| POC/Value Area | 4 | Context layer |
| **Total signal points** | **100** | |

Within each category, individual signals share the category budget proportionally to their specificity. Higher-confidence signals (e.g., AbsorbStopping > AbsorbClassic) receive larger proportional weight.

### Zone and Level Interaction Bonuses

This is additive to the signal score, bounded to prevent overflow:

```
Zone Bonuses (applied AFTER base signal score):
  + 8 pts  : Signal fires AT an LVN zone (price within 2 ticks of LVN midpoint)
  + 6 pts  : Signal fires AT an absorption/exhaustion zone (prior generated zone)
  + 5 pts  : Signal direction MATCHES GEX bias (gamma flow alignment)
  + 4 pts  : Signal fires near VWAP (within 0.5 SD)
  + 3 pts  : Signal fires at Initial Balance boundary (±2 ticks)
  + 3 pts  : Signal fires at prior day VAH/VAL/POC

Zone bonuses are capped at +20 pts total.
Final score = min(signal_score + zone_bonus, 100)
```

Zone interaction design rule: zones do NOT replace signals; they amplify signals. A signal with no zone bonus can still reach TypeA. A zone alone with no signal is invisible.

### Confluence Multiplier

Apply the multiplier LAST, after zone bonuses:

```csharp
// Count how many of the 8 categories contributed ≥1 signal in the trade direction
int categoriesAgreeing = PopCount(result.CategoryMask & directionMask);

double confluenceMultiplier = categoriesAgreeing switch {
    >= 6 => 1.30,   // 6 of 8 categories agree: exceptional confluence
    5    => 1.20,   // Pine Script's 1.25 calibrated down slightly (5 categories)
    4    => 1.10,   // 4 categories: moderate confluence
    _    => 1.00    // < 4: no multiplier
};

double finalScore = Math.Min(baseWithZoneBonus * confluenceMultiplier, 100.0);
```

Rationale for 1.20 rather than Pine Script's 1.25: NT8 already applies an agreement ratio multiplier from the engine voting layer. Double-compounding at 1.25 × 1.25 would inflate scores too aggressively. Calibrate after first backtesting pass.

### Engine Voting Layer (existing, keep unchanged)

The existing agreement ratio multiplier (max(bull, bear) / total engines) remains. It is computed from the engine-level direction votes (E1–E9), not from the signal-level category mask. These are two independent consensus signals — engine-level and category-level — and both must agree for a high score:

```
Engine agreement ratio: rewards agreement among the 9 engines
Category confluence:    rewards breadth across signal categories
```

A score can only reach TypeA if both are high.

---

## Zone / Level Integration Architecture

### ZoneRegistry

A single ZoneRegistry instance owns all active zone objects. Engines do not store zones — they notify the registry.

```
ZoneType enum:
  LVN_Static      — from volume profile (session or composite)
  HVN_Static      — from volume profile
  AbsorptionZone  — created by E1 when AbsorbClassic/Stopping fires
  ExhaustionZone  — created by E1 when ExhZeroPrint/FatPrint fires
  GEX_CallWall    — from external GEX API
  GEX_PutWall     — from external GEX API
  GEX_GammaFlip   — from external GEX API
  VWAP_Band       — ±1SD, ±2SD dynamic levels
```

Zone lifecycle states (from Pine Script reference):
- `Created` — newly detected
- `Defending` — price retested zone, held
- `Breaking` — price penetrating zone
- `Flipped` — zone changed polarity (resistance → support or vice versa)
- `Invalidated` — zone breached convincingly, no longer active

ZoneRegistry exposes:
- `GetZonesAt(price, tolerance)` → `Zone[]` — used by Scorer for zone bonuses
- `GetActiveZones()` → `Zone[]` — used by rendering to draw zone boxes
- `RegisterSignalZone(price, type, dir)` — called by E1 when signal fires
- `Update(bar)` — advance zone lifecycle state machine each bar

### Zone Scoring (separate from signal scoring)

Zones maintain their own quality score (0–100), matching the Pine Script formula:

```
Zone Quality = ZoneType_points + Volume_points + TouchCount_points + Recency_points

ZoneType_points (max 25):
  GEX levels: 25
  LVN_Static:  20
  AbsorbZone:  18
  ExhZone:     15

Volume_points (max 25):
  Proportional to zone volume vs session average

TouchCount_points (max 25):
  1 touch: 5, 2: 12, 3: 18, 4+: 25

Recency_points (max 25):
  Same session: 25, 1-2 sessions ago: 15, older: 5
```

Zone quality score does NOT directly enter the bar signal score. It gates whether a zone qualifies for the bonus: only zones with quality ≥ 50 are eligible for the +6 to +8 zone bonus in the Scorer.

---

## NT8 ↔ ML Backend Data Flow

### Transport: TCP Socket (fire-and-forget)

**Recommendation: TCP socket with TcpClient in C#, asyncio TCP server in Python (FastAPI wraps it).**

Rationale:
- NT8 runs on Windows localhost. Python backend runs on same machine (initially) or LAN.
- File-based (StreamWriter) has known issue: indicator suspends when NT8 window is not in focus. This is unacceptable for live trading.
- WebSocket adds complexity without benefit for a localhost point-to-point link.
- ZeroMQ works but requires adding a third-party DLL to NT8's reference path, which creates deployment fragility.
- Named pipes work on Windows localhost but are harder to consume from Python asyncio.
- TCP socket is the minimal viable, stable, and performant choice. NT8 natively supports `System.Net.Sockets.TcpClient` without DLL additions.

**IpcBridge design:**

```csharp
// In AddOns/DEEP6.IpcBridge.cs
public class IpcBridge : IDisposable
{
    private readonly ConcurrentQueue<string> _queue = new();
    private readonly Thread _worker;
    private volatile bool _running = true;
    private TcpClient _client;
    private NetworkStream _stream;

    public IpcBridge(string host, int port)
    {
        _worker = new Thread(WorkerLoop) { IsBackground = true, Name = "DEEP6-IPC" };
        _worker.Start();
    }

    // Called from bar thread — non-blocking
    public void Push(ScorerResult result, SignalSnapshot snap)
    {
        string json = SerializeToJson(result, snap);  // no Newtonsoft: use manual string build
        _queue.Enqueue(json);
    }

    private void WorkerLoop()
    {
        while (_running)
        {
            EnsureConnected();
            if (_queue.TryDequeue(out var msg))
                TrySend(msg);  // if send fails, reconnect on next iteration
            else
                Thread.Sleep(10);  // idle: 10ms polling
        }
    }
}
```

**JSON payload structure (per TypeB+ signal fire):**

```json
{
  "ts": "2026-04-11T14:32:01.123Z",
  "bar_time": "2026-04-11T14:32:00Z",
  "instrument": "NQ1!",
  "score": 82.4,
  "dir": 1,
  "type": "TypeA",
  "narrative": "ABSORPTION",
  "signals_fired": ["AbsorbClassic", "AbsorbStopping", "DeltaTrap", "ImbStacked_T2"],
  "categories_agreeing": 5,
  "zone_bonus": 11,
  "engines": {
    "e1_fp": {"score": 22.0, "dir": 1},
    "e2_tr": {"score": 16.0, "dir": 1},
    "e3_sp": {"score": 8.0, "dir": 0},
    "e4_ic": {"score": 12.0, "dir": 1},
    "e5_mi": {"score": 7.0, "dir": 1},
    "e6_vp": {"score": 10.0, "dir": 1},
    "e7_ml": {"score": 6.0, "dir": 1},
    "e8_cv": {"score": 4.0, "dir": 1},
    "e9_au": {"score": 5.0, "dir": 1}
  },
  "session": {
    "day_type": "TrendBull",
    "vwap_zone": "Above1Sd",
    "ib_type": "Normal",
    "poc_migration": 3
  },
  "zones_at_price": [
    {"type": "LVN_Static", "quality": 78, "price": 18245.50},
    {"type": "GEX_CallWall", "quality": 90, "price": 18250.00}
  ],
  "trade_outcome": null
}
```

Python backend writes `trade_outcome` back into the record when the trade closes (matched by `ts` key). This is the training label for ML weight optimization.

### Python Backend Role

- **Ingest:** asyncio TCP server receives JSON, stores in SQLite (dev) or PostgreSQL (prod)
- **Regime detection:** rolling HMM on session-level features (day type, VWAP zone distribution, CVD trend) — classify regime per session
- **Weight evolution:** after N completed trades per regime, run Bayesian update on signal category weights (prior = current weights, likelihood = win/loss per category)
- **Threshold evolution:** per-regime optimal TypeA/TypeB thresholds derived from P&L attribution
- **Weight push:** Python writes updated weights to a JSON config file that DEEP6 reads at session start (pull model, not push — avoids live mutation)

### Weight Pull (NT8 side)

At `State.DataLoaded` (session start), DEEP6 reads `ml_weights.json` from a known path:

```
C:\Users\<user>\Documents\NinjaTrader 8\bin\Custom\deep6_ml_weights.json
```

If file is absent or malformed, fall back to hardcoded defaults. Never mutate weights during live trading session — only apply at session start.

---

## Suggested Build Order (Phase Dependencies)

### Phase A: Decompose the Monolith (Foundation for everything else)

1. Create AddOns folder structure
2. Move E1–E7 engine logic into standalone classes in AddOns files
3. Verify NT8 compiles — all behavior unchanged
4. Add `EngineResult` struct + `SignalFlags` enum

This is the prerequisite for every subsequent phase. Without it, adding 37 more signals to DEEP6.cs will push it to 5,000+ lines and create unmaintainable chaos.

### Phase B: Signal Layer Expansion (E1 is highest priority)

1. Expand E1 FootprintEngine: add all 4 absorption + 6 exhaustion signals
2. Add E8 CVD engine (CVD multi-bar divergence — was partially in E1 before)
3. Expand delta signals in E1: add 11 delta signals using existing CVD/delta infrastructure
4. Add trapped trader signals (inverse imbalance is highest alpha — prioritize)

Dependency: Phase A must be complete (standalone class pattern makes adding signals trivial without risking compilation of the full file).

### Phase C: Zone Registry

1. Implement ZoneRegistry with LVN detection from volume profile
2. Add zone lifecycle state machine
3. Wire E1 to register absorption/exhaustion zones on signal fire
4. Add GEX level ingestion (initially manual or file-based — API later)

Dependency: Phase B (zones are created by signals, so signals must exist first).

### Phase D: Scoring Upgrade

1. Implement 44-signal category weights (replace flat engine contribution model)
2. Add zone bonus calculation in Scorer
3. Add confluence multiplier (category-level)
4. Add volatility-adaptive thresholds (ATR-scaled)

Dependency: Phases B and C (need signals and zones to score them).

### Phase E: New Engines (E9 Auction + expansion of E2/E3/E4)

1. Implement E9 Auction Theory state machine
2. Expand E2 Trespass: add volume sequencing + DOM-based trapped trader signals
3. Add volume pattern signals (E6 expansion)
4. Add POC/Value Area signals (E6 expansion)

Dependency: Phase D scoring must exist to weight these signals correctly.

### Phase F: IpcBridge + Python Backend

1. Implement IpcBridge (TCP, ConcurrentQueue, background thread)
2. Build FastAPI server with asyncio TCP listener
3. Signal history storage (SQLite)
4. Regime detection baseline

Dependency: Phase D (need stable signal payload shape before building the consumer).

### Phase G: Auto-Execution

1. Implement ExecutionLayer (ATM strategy invocation from ScorerResult)
2. Risk management guardrails (max daily loss, consecutive loss circuit breaker)
3. Position sizing based on score confidence tier

Dependency: Phase D (needs stable scoring). Can run in parallel with Phase F.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Signals-as-Engine-Score (Current Architecture's Limitation)

**What:** Expanding the current flat engine score model to cover 44 signals by adding more `double` fields and more score constants (`MX_FP`, `MX_TR`, etc.).
**Why bad:** At 44 signals across 9 engines, the flat model requires O(44) fields on the facade class, O(44) score constants, and O(44) if-branches in Scorer. This is how you get to 5,000+ unmaintainable lines.
**Instead:** Use the `SignalFlags` bitmask + category weight table. The scorer reads the bitmask and sums category weights — adding a new signal is one enum value + one weight entry.

### Anti-Pattern 2: Zone State in Engines

**What:** Each engine maintains its own list of zones it created.
**Why bad:** Zones from different engines (LVN from E6, absorption zone from E1, GEX from external) cannot interact. Scoring bonuses require a unified view.
**Instead:** Centralized ZoneRegistry. Engines emit zone creation events; registry owns lifecycle.

### Anti-Pattern 3: Blocking IPC on Bar Thread

**What:** Calling `TcpClient.Send()` synchronously inside `OnBarUpdate()`.
**Why bad:** Network latency (even localhost) adds milliseconds to bar processing. At high frequency, this causes bar processing queue backup. NT8 will show lag warnings.
**Instead:** ConcurrentQueue + background thread. Bar thread only enqueues a string. Network I/O happens off the critical path.

### Anti-Pattern 4: Weighting All Signals Equally

**What:** Every one of the 44 signals gets 100/44 = 2.27 points.
**Why bad:** A diagonal imbalance is not equivalent to a zero print or an inverse imbalance trap. Equal weighting destroys the signal hierarchy.
**Instead:** Category-level budget allocation (absorption gets 22 pts, POC/VA gets 4 pts) with intra-category proportional distribution. ML backend evolves weights after backtesting.

### Anti-Pattern 5: Real-Time ML Inference in NT8

**What:** Running the Python ML model inside NT8 via IronPython or a subprocess call on every bar.
**Why bad:** Python startup overhead, GIL interactions, and inference latency are incompatible with NT8's bar processing loop. Would cause severe lag.
**Instead:** ML runs in a separate process, produces a weight file, DEEP6 reads it at session start. Inference stays on NT8 side using the pre-computed weights (trivially fast).

### Anti-Pattern 6: Mutating Weights Mid-Session

**What:** Python backend pushes new weights via TCP mid-session and NT8 applies them immediately.
**Why bad:** Changes scoring behavior while positions are open. Makes debugging impossible (which weights produced this trade?). Creates potential instability.
**Instead:** Weights are session-invariant. Apply new weights only at session start (State.DataLoaded). Log which weight version was active during each trading session.

---

## Scalability Considerations

| Concern | Current (7 engines, ~15 signals) | Target (9 engines, 44 signals) | At Full ML Deployment |
|---------|----------------------------------|--------------------------------|----------------------|
| Code volume | 1,010 lines (1 file) | ~3,000 lines (15 files) | Same — no code growth from ML |
| Per-bar processing | ~0.5ms estimated | ~1.5ms estimated | +0.01ms (weight file read is session-once) |
| Memory | ~50KB state | ~200KB state (ZoneRegistry + signal history) | +10MB SQLite cache (Python side only) |
| IPC latency | None | <1ms TCP on localhost | <1ms |
| Scoring complexity | O(7) sum | O(bitmask popcount + zone lookup) ≈ O(1) | O(1) |

The bitmask approach (`SignalFlags`) is critical: scoring 44 signals via bitmask + lookup table is O(1) — faster than the current O(7) loop, not slower.

---

## Sources

- NinjaTrader 8 forum: partial class AddOns folder pattern — [Exporting Indicator as Assembly when using Partial Classes](https://forum.ninjatrader.com/forum/ninjatrader-8/indicator-development/1057478-exporting-indicator-as-assembly-when-using-partial-classes) (MEDIUM confidence — community, not official docs)
- NinjaTrader 8 forum: NT8-Python IPC approaches — [Connecting NT8 and Python](https://forum.ninjatrader.com/forum/ninjatrader-8/add-on-development/1188722-connecting-nt8-and-python) (MEDIUM confidence)
- NinjaTrader 8 forum: ZeroMQ NinjaScript bindings confirmed working — [0mq bindings for Ninjatrader](https://forum.ninjatrader.com/forum/ninjatrader-7/general-development/42759-0mq-bindings-for-ninjatrader) (LOW confidence — NT7 era)
- Numin framework: Dynamic Weighted Majority Algorithm for trading signal weighting — [Numin: Weighted-Majority Ensembles for Intraday Trading](https://arxiv.org/html/2412.03167v1) (HIGH confidence — peer reviewed)
- Current project: Pine Script reference (zone scoring formula 25+25+25+25, confluence 1.25×, cascade priority) — internal reference architecture
- Current project: DEEP6 v1 architecture (engine score structure, agreement ratio multiplier, existing data flow) — `.planning/codebase/ARCHITECTURE.md`
- Current project: Known concerns (monolithic risk, GC pressure, thread safety) — `.planning/codebase/CONCERNS.md`
