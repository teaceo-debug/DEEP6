# GEX Reaction Sensor — Design Pattern Knowledge Base

## Pattern: GEX Level x Order Flow Cross-Reference

### What it is
An NT8 indicator pattern that bridges structural GEX positioning (from DEEP6GammaDecisionSurface
V2 JSON) with real-time order flow confirmation (from the DEEP6 AddOns detector registry).

### Files
- Indicator: `ninjatrader/Custom/Indicators/DEEP6/DEEP6GammaReactionSensor.cs`
- JSON source: `massive_gex_map_v2.json` (same as GDS V2)
- AddOns depended on: AbsorptionDetector, ExhaustionDetector, FootprintBar, SessionContext

### Core Architecture

#### Three parallel streams:
1. **GDS V2 JSON stream** (timer, 2s) -> GdsLevel[] with behavior_state, tier, price
2. **Footprint stream** (OnMarketData, tick) -> FootprintBar.AddTrade(price, size, aggressor)
3. **Delta accumulation** (OnMarketData, tick) -> per-level DeltaAccum for active levels

#### Per-level state machine:
```
IDLE -> [price enters proximity band] -> ACTIVE
ACTIVE -> accumulate delta, count absorb/exhaust hits
ACTIVE -> [fire criteria met] -> SIGNAL FIRED -> COOLDOWN
COOLDOWN -> [CooldownBars elapsed] -> IDLE or ACTIVE
```

### API Reference

#### AbsorptionDetector (AddOns)
```csharp
// Namespace: NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Absorption
var detector = new AbsorptionDetector();            // or new AbsorptionDetector(config)
detector.Reset();                                   // no-op (stateless between bars)
SignalResult[] results = detector.OnBar(bar, session);
// ABS-01: Classic wick, ABS-02: Passive, ABS-03: Stopping vol, ABS-04: Effort vs result
// ABS-07: VA extreme bonus (post-hoc mutation on existing results)
// result.Direction: +1 = buy signal, -1 = sell signal
// result.Strength: 0.0-1.0
// result.Detail: human-readable string
```

#### ExhaustionDetector (AddOns)
```csharp
// Namespace: NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion
var detector = new ExhaustionDetector();
detector.Reset();                                   // clears cooldown state
SignalResult[] results = detector.OnBar(bar, session);
// EXH-01: ZeroPrint (delta-gate exempt), EXH-02: ExhaustionPrint, EXH-03: ThinPrint
// EXH-04: FatPrint, EXH-05: FadingMomentum, EXH-06: BidAskFade
// Has internal cooldown state -- must Reset() at session boundary
```

#### FootprintBar (AddOns)
```csharp
// Namespace: NinjaTrader.NinjaScript.AddOns.DEEP6
var bar = new FootprintBar { BarIndex = CurrentBar };
bar.AddTrade(price, size, aggressor);    // aggressor: 1=buy, 2=sell, 0=neutral
bar.Finalize(priorCvd);                  // call at bar close
var va = FootprintBar.ComputeValueArea(bar, TickSize);  // returns (vah, val)
// bar.Levels: SortedDictionary<double, Cell>
// bar.BarDelta, bar.TotalVol, bar.PocPrice, bar.Cvd, bar.BarRange
```

#### SessionContext (AddOns)
```csharp
// Namespace: NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
var session = new SessionContext();
session.TickSize = TickSize;           // set before use
session.Atr20 = _atr;                 // update per bar
session.VolEma20 = _volEma;           // update per bar
session.PriorBar = lastFinalizedBar;  // update per bar
session.Vah = vah;                    // nullable double
session.Val = val;                    // nullable double
session.ResetSession();               // call at session boundary
SessionContext.Push(session.PriceHistory, bar.Close);  // rolling history
SessionContext.Push(session.CvdHistory, bar.Cvd);      // rolling history
```

### VolEma + ATR Pattern (from V7)
```csharp
// EMA of bar volume (20-period)
private double _volEma;
private const double VolEmaAlpha = 2.0 / (20.0 + 1.0);
_volEma = _volEma == 0 ? bar.TotalVol : _volEma + VolEmaAlpha * (bar.TotalVol - _volEma);

// ATR via rolling window of BarRange (20-period simple average)
private readonly Queue<double> _atrWindow = new Queue<double>();
private const int AtrPeriod = 20;
private double _atr = 1.0;
_atrWindow.Enqueue(bar.BarRange);
if (_atrWindow.Count > AtrPeriod) _atrWindow.Dequeue();
if (_atrWindow.Count > 0) { double s = 0; foreach (var v in _atrWindow) s += v; _atr = s / _atrWindow.Count; }
```

### Behavior-Driven Signal Logic
| Behavior | Expect | Signal fires when | Direction |
|---|---|---|---|
| DEFEND | Sellers press, bid absorbs | DeltaAccum < -threshold AND AbsorbHits >= N | +1 (long) |
| REJECT | Buyers press, ask absorbs/exhausts | DeltaAccum > +threshold AND (AbsorbHits >= N OR ExhaustHits >= 1) | -1 (short) |
| ATTRACT | Price moves toward level | abs(DeltaAccum) >= DeltaThreshold | sign(level - close) |
| FLIP | Price crosses zero-GEX level | abs(DeltaAccum) >= FlipDeltaThreshold | sign(DeltaAccum) |

### Critical NT8 Notes
- GDS DTOs (GdsPayload, GdsAsset, GdsLevel, etc.) are defined in `DEEP6GammaDecisionSurface.cs`
  in namespace `NinjaTrader.NinjaScript.Indicators.DEEP6` -- do NOT redefine in same namespace
- All .cs files compile into one NT8 DLL -- duplicate class names in same namespace = CS0101
- Detectors need Reset() at session boundary (date change)
- AbsorptionDetector is stateless (Reset() is no-op); ExhaustionDetector has cooldown state
- OHLC reconciliation: always set bar.Open/High/Low/Close from Bars.GetOpen/High/Low/Close
  BEFORE calling bar.Finalize() -- ensures BarRange matches NT8's authoritative bar values
- FootprintBar.ComputeValueArea returns C# 7 value tuple (double vah, double val)

### Thread Safety Pattern
- `_barsLock` (object) protects `_bars` dictionary -- OnMarketData writes, OnBarUpdate reads
- `_sync` (object) protects `_payload`, `_asset`, `_levelStates`, `_signals` -- timer writes, render reads
- `LevelState.DeltaAccum` written from OnMarketData (data thread) -- no lock needed because
  LevelState[] is replaced atomically by ReadSnapshot, and accumulation is additive
- SharpDX resources created in OnRenderTargetChanged, disposed in DisposeDx + OnStateChange(Terminated)

### Aggressor Classification (from V7)
```csharp
int aggressor;
if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;      // buy aggressor
else if (!double.IsNaN(_bestBid) && e.Price <= _bestBid) aggressor = 2;  // sell aggressor
else aggressor = 0;                                                       // neutral
```

### Visual Layer Order
1. Proximity bands (very low alpha fills around each active level)
2. Signal markers (triangles at fired signal bars, with halo text labels)
3. Status pills (right edge, below GDS V2 regime strip, with accent stripe)

### GDS JSON ExpandJsonPath Pattern
```csharp
// Handles %USERPROFILE% environment variable expansion
private string ExpandJsonPath(string raw)
{
    string docs = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
    string profile = Directory.GetParent(docs) != null ? Directory.GetParent(docs).FullName : docs;
    return (raw ?? string.Empty).Replace("%USERPROFILE%", profile).Replace("%USERPROFILE%\\Documents", docs);
}
```

### Default Parameter Values
| Parameter | Default | Purpose |
|---|---|---|
| ProximityPoints | 15.0 | NQ points from GEX level to activate tracking |
| MinAbsorbHits | 2 | Absorption signals needed before firing |
| DeltaThreshold | 200.0 | Minimum absolute delta accumulation |
| FlipDeltaThreshold | 350.0 | Higher threshold for FLIP behavior |
| CooldownBars | 5 | Bars before same level can re-fire |
| RefreshSeconds | 2 | JSON file polling interval |
| OnlyT1T2 | true | Filter out T3 (low confidence) levels |
