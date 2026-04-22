# DEEP6 NT8 Architecture Map
Last verified: 2026-04-20 (full compile SUCCESS — all files active)

## Current NT8 Deployment (compiles successfully as of 2026-04-20 00:00)

### Indicators\DEEP6\

| File | Primary Namespace | Key Exports | Status |
|------|-----------------|-------------|--------|
| DEEP6Signal.cs | `NinjaTrader.NinjaScript.Indicators` | Class: DEEP6Signal; Global enums: Verdict, Tier, Regime, SignalFamily; Property: MinTier (Tier type) | ✅ Compiles |
| DEEP6GexLevels.cs | `NinjaTrader.NinjaScript.AddOns.DEEP6` (+ embedded Indicator class) | GexLevel, GexProfile, GexLevelKind | ✅ Compiles |
| CaptureHarness.cs | `NinjaTrader.NinjaScript.AddOns.DEEP6` | CaptureHarness class | ✅ Compiles |
| DEEP6Footprint.cs | `NinjaTrader.NinjaScript.Indicators` + `AddOns.DEEP6` | Footprint chart renderer; defines FootprintBar inline | ✅ Compiles (fixed: missing `}` in DrawExhaustionMarker, `System.Windows.TextAlignment` disambiguation) |

### AddOns\DEEP6\

| File | Namespace | Purpose | Status |
|------|-----------|---------|--------|
| DEEP6DevAddon.cs | `NinjaTrader.NinjaScript.AddOns` | HTTP dev API on localhost:19206 | ✅ Compiles |

### AddOns\NinjaAIBridge\

| File | Status |
|------|--------|
| NinjaAIBridge.cs | ✅ Compiles |

### Indicators\AIBridge\

| File | Status |
|------|--------|
| NinjaAIBridge.cs | ✅ Compiles (generates boilerplate for Indicators + MarketAnalyzerColumns + Strategies namespaces) |

---

### AddOns\DEEP6\ (stub implementations — all compiling)

All types that DEEP6Footprint.cs references are now deployed as stubs under `AddOns\DEEP6\`:

| Subdirectory | Files |
|---|---|
| `Registry/` | DetectorRegistry.cs, ISignalDetector.cs, SessionContext.cs, SignalFlagBits.cs, SignalResult.cs |
| `Scoring/` | ConfluenceScorer.cs, NarrativeCascade.cs, ScorerEntryGate.cs, ScorerResult.cs, ScorerSharedState.cs, SignalTier.cs, ZoneScoreCalculator.cs |
| `Detectors/Absorption/` | AbsorptionDetector.cs |
| `Detectors/Auction/` | AuctionDetector.cs |
| `Detectors/Delta/` | DeltaDetector.cs |
| `Detectors/Engines/` | CounterSpoofDetector.cs, IcebergDetector.cs, MicroProbDetector.cs, SignalConfigScaffold.cs, TrespassDetector.cs, VPContextDetector.cs |
| `Detectors/Exhaustion/` | ExhaustionDetector.cs |
| `Detectors/Imbalance/` | ImbalanceDetector.cs |
| `Detectors/Legacy/` | LegacyDetectorsBridge.cs |
| `Detectors/Trap/` | TrapDetector.cs |
| `Detectors/VolPattern/` | VolPatternDetector.cs |
| `Levels/` | ProfileAnchorLevels.cs |
| `Math/` | LeastSquares.cs, Wasserstein.cs |
| `Bridge/` | DataBridgeServer.cs |

Repo source: `C:\Users\Tea\DEEP6\ninjatrader\Custom\AddOns\DEEP6\`

---

## NT8 Compile Rules (Quick Reference)

```
ALL files in Custom\ → compile into ONE assembly (NinjaTrader.Custom.dll)
Duplicate class name across any files → CS0101 (fatal)
Enum as indicator property type → MUST be at GLOBAL namespace (no wrapper)
.NET Framework 4.8, C# 7.3 max
volatile double/float → CS0677 (illegal)
using NinjaTrader.Core → CS0234 (namespace doesn't exist in NT8 8.x)
Print("msg") ✅  |  Log("msg", ...) ❌
async OnBarUpdate() → not supported
All OnBarUpdate UI updates must use TriggerCustomEvent() or Dispatcher.BeginInvoke()
```

---

## Dependency Graph

```
DEEP6DevAddon.cs      → standalone (no DEEP6 type deps)
DEEP6Signal.cs        → standalone (NT8 built-ins only)
DEEP6GexLevels.cs     → standalone (NT8 built-ins only)
CaptureHarness.cs     → FootprintBar  ← [DEEP6Stubs.cs ⚠️ stub]
DEEP6Stubs.cs         → standalone (provides FootprintBar stub)

DEEP6Footprint.cs     → [BROKEN] needs 17 types across Registry.*, Scoring.*, Detectors.*
DataBridgeIndicator   → [BROKEN] needs Bridge.DataBridgeServer
```

---

## HTTP Dev API (localhost:19206)

Served by DEEP6DevAddon.cs when NT8 is running with a successful compile.

| Endpoint | Method | Response |
|----------|--------|----------|
| /health | GET | `{"ok":true,"port":19206}` |
| /status | GET | `{"nt8_running":true,"last_compile":"...","dll_mtime":"..."}` |
| /errors | GET | JSON array of NT8 output window lines |
| /compile | POST | `{"triggered":true}` — sends F5 to NSE |
| /log?lines=N | GET | JSON array of last N trace log lines |

Test: `Invoke-WebRequest -Uri "http://localhost:19206/health" -UseBasicParsing`

---

## DEEP6Footprint.cs Restoration — COMPLETED 2026-04-20

All steps done. DEEP6Footprint.cs is active and compiling:
- All 30 stub files created in `AddOns\DEEP6\` subdirectories
- Fixed `DrawExhaustionMarker` missing `}` (line 1247 in both deployed + repo source)
- Fixed `TextAlignment.Center` → `System.Windows.TextAlignment.Center` (SharpDX ambiguity)
- Removed DEEP6Stubs.cs (was temporary bridge; FootprintBar now defined in DEEP6Footprint.cs)
- DataBridgeIndicator.cs remains shelved (DataBridgeServer stub is deployed but indicator not yet restored)

Next step: restore `DataBridgeIndicator.cs` from `DataBridgeIndicator.cs.broken-bak` and test.

---

## DEEP6Signal.cs Architecture (L1–L7)

The main signal indicator is a self-contained 2262-line file:

| Layer | Description |
|-------|-------------|
| L1 Data | DOM + footprint data ingestion |
| L2 Features | FeatureFrame — bar-level derived features |
| L3 Engines | E1-E9 nested engine classes (per signal family) |
| L4 Regime | HmmForward + Bocpd regime detection |
| L5 Fusion | FtrlProximal + IsotonicCalibrator + TierQuantiles |
| L6 Decision | PolicyLayer (Kelly criterion, optimal stop, risk gates) |
| L7 Render | HudRenderer (SharpDX, 8Hz throttle, 6 HUD states) |

Key properties: `MinTier` (Tier enum), `MinPWin` (double)
Key enums (global): `Verdict`, `Tier`, `Regime`, `SignalFamily`
