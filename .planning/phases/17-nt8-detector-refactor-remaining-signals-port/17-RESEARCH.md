# Phase 17: NT8 Detector Refactor + Remaining Signals Port — Research

**Researched:** 2026-04-15
**Domain:** NinjaScript 8 / C# signal detector architecture + 44-signal Python-to-C# port
**Confidence:** HIGH (codebase verified) / MEDIUM (NT8 AddOns compile path — NT8 not installed on this Mac)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Stateful ISignalDetector instances; each owns rolling state (CVD deque, prior-bar ref, cooldown counters). Shared state (session POC, ATR, CVD seed, bar history) on SessionContext singleton.
- One file per detector, grouped: `Custom/AddOns/DEEP6/Detectors/{Imbalance,Delta,Auction,Trap,VolPattern,Engine}/`. Each file <= 300 LOC target.
- Namespace: `NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.{Family}`. Registry + interface at `AddOns/DEEP6/Registry/`.
- Full ABS/EXH migration into new layout this phase. Verified against known-good live behavior before new detectors are layered on.
- Wave order: Wave 1 = interface + registry + migrate ABS/EXH. Wave 2 = parity gate. Wave 3+ = port by TRIVIAL → MODERATE → HARD.
- Port tiers: TRIVIAL (14) → MODERATE (17) → HARD (6, inc. DELT-10, TRAP-05, ENG-02, ENG-03, ENG-05, ENG-04, ENG-06).
- Feature flag `UseNewRegistry` on DEEP6Strategy; default false until Wave 2 parity passes.
- Parity: bit-for-bit on synthetic fixtures; ±2 signals/type/session on live replay.
- Live capture harness: NT8 OnMarketData + OnMarketDepth → NDJSON under `ninjatrader/captures/YYYY-MM-DD-session.ndjson`.
- Standalone NUnit project at `ninjatrader/tests/`; `.NET 4.8` target; runs via `dotnet test`.
- Hand-rolled least-squares (~20 LOC) at `AddOns/DEEP6/Math/LeastSquares.cs`; consumers: DELT-10, EXH-05, TRAP-05.
- Python bug policy: fix Python too, mirror into C#; document each correction in plan SUMMARY.md.
- DOM state: pre-allocated `double[40]` per side. O(1) lookup by price index.
- GEX timer + MassiveGexClient stays in DEEP6Footprint.cs for Phase 17.
- `double[40]` DOM arrays not `array.array` — zero GC on hot path.

### Claude's Discretion

- Logging verbosity per detector.
- Exact SignalFlags uint64 bit assignments (must be collision-free with existing ABS/EXH bits).
- Fixture JSON schema.
- Thread-safety specifics per detector (follow Phase 16 pattern).
- Per-detector cooldown defaults (5 bars unless Python specifies otherwise).
- Capture log file format (NDJSON default; binary if write throughput demands it).
- Whether Wave 2 parity uses freshly captured or pre-recorded session.

### Deferred Ideas (OUT OF SCOPE)

- Kronos E10 / TradingView MCP / FastAPI / Next.js — out of scope v1.
- GEX engine refactor into new layout — Phase 18+.
- Two-layer confluence scorer port — Phase 18.
- Apex/Lucid paper-trade gate — Phase 19.
- Databento live feed — reference-only; historical MBO only for parity dataset.
- EventStore / ML backend — out of scope v1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IMB-01 | Single imbalance >= 300% at one level | Python `detect_imbalances()` verified; diagonal rule (ask[P] vs bid[P-1]) confirmed; TRIVIAL port |
| IMB-02 | Multiple imbalance (3+ at same price) | `detect_imbalances()` aggregates by price; MODERATE (multi-bar history needed) |
| IMB-03 | Stacked T1/T2/T3 (3/5/7 consecutive levels) | Tier classification from consecutive imb_ticks count; MODERATE |
| IMB-04 | Reverse imbalance | Both buy_imb and sell_imb in same bar; MODERATE |
| IMB-05 | Inverse imbalance (trapped traders) | Buy imb in red bar (close < open); MODERATE |
| IMB-06 | Oversized imbalance (10:1+ ratio) | Single threshold check; TRIVIAL |
| IMB-07 | Consecutive imbalance (same level across bars) | Requires prior-bar cache in detector state; MODERATE |
| IMB-08 | Diagonal imbalance | ask[P] vs bid[P-1]; TRIVIAL |
| IMB-09 | Reversal imbalance pattern | Direction change across bar sequence; MODERATE |
| DELT-01 | Delta rise/drop per bar | sign(bar.BarDelta); TRIVIAL |
| DELT-02 | Delta tail (95%+ of intrabar extreme) | Uses MaxDelta/MinDelta on FootprintBar; TRIVIAL |
| DELT-03 | Delta reversal (delta sign contradicts bar direction) | bar.Close vs bar.Open + bar.BarDelta sign; TRIVIAL |
| DELT-04 | Delta divergence (price new high but CVD failing) | N-bar rolling history; MODERATE |
| DELT-05 | CVD flip (sign change) | CVD history[−2] vs current; TRIVIAL |
| DELT-06 | Delta trap (aggressive delta + reversal) | 2-bar history; MODERATE |
| DELT-07 | Delta sweep (rapid accumulation, vol accelerates) | Levels iteration + volume split; MODERATE |
| DELT-08 | Delta slingshot (compressed then explosive) | 4-bar history; delta_history deque; HARD |
| DELT-09 | Delta at session min/max | Session tracking on SessionContext; TRIVIAL |
| DELT-10 | CVD polyfit divergence (np.polyfit equivalent) | Hand-rolled least-squares; HARD |
| DELT-11 | Delta velocity (CVD rate-of-change acceleration) | 3-bar CVD history; MODERATE |
| AUCT-01 | Unfinished business | non-zero bid at bar high / ask at bar low; MODERATE |
| AUCT-02 | Finished auction | zero vol at extreme; TRIVIAL |
| AUCT-03 | Poor high/low | single-print or low-vol extreme; MODERATE |
| AUCT-04 | Volume void (LVN gap within bar) | gap detection in Levels; MODERATE |
| AUCT-05 | Market sweep (rapid traversal + increasing vol) | cross-bar sweep + vol ramp; MODERATE |
| TRAP-01 | Inverse imbalance trap | Already IMB-05 (INVERSE_TRAP); migration/re-verify only |
| TRAP-02 | Delta trap (prior strong delta reverses) | 2-bar state; MODERATE |
| TRAP-03 | False breakout trap | prior_bar.high/low comparison + vol gate; MODERATE |
| TRAP-04 | High volume rejection trap | Wick vol fraction from Levels; MODERATE |
| TRAP-05 | CVD trend reversal trap (polyfit) | Hand-rolled least-squares; HARD |
| VOLP-01 | Volume sequencing (3+ bars escalating) | Bar history deque; MODERATE |
| VOLP-02 | Volume bubble (isolated hi-vol level) | Level-by-level vol comparison; TRIVIAL |
| VOLP-03 | Volume surge (> 3× vol_ema) | Single threshold; TRIVIAL |
| VOLP-04 | POC momentum wave (POC migrating direction) | poc_history deque on SessionContext; MODERATE |
| VOLP-05 | Delta velocity spike (delta accel) | 2-bar delta history; MODERATE |
| VOLP-06 | Big delta per level (single level dominant delta) | Level iteration; TRIVIAL |
| ENG-02 | Trespass (weighted DOM queue imbalance + logistic approx) | No pretrained weights — pure math; MODERATE |
| ENG-03 | CounterSpoof (Wasserstein-1 DOM + large cancel) | Hand-rolled W1; HARD |
| ENG-04 | Iceberg (native fill > DOM + synthetic refill < 250ms) | Timing precision required; HARD |
| ENG-05 | MicroEngine (Naive Bayes from 3 features) | Stateless; no pretrained model; MODERATE |
| ENG-06 | VP+Context (POC/VWAP/IB/GEX/ZoneRegistry + LVN lifecycle) | Large scope; partially in NT8 already; HARD |
| ENG-07 | Signal config scaffold | Config-only; TRIVIAL |
</phase_requirements>

---

## Summary

Phase 17 splits the ~95 KB DEEP6Footprint.cs monolith into a per-family detector registry, migrates 10 live signals (ABS-01..04, ABS-07, EXH-01..06) into the new layout, and ports 34 Python-reference signals across 6 families into NinjaScript C#. The dominant technical challenges are: (1) the NT8 AddOns subdirectory compile behavior (files must be in the right place to be compiled by NT8's editor), (2) making `dotnet test` work for a net48 project on macOS where Mono is not installed, (3) implementing hand-rolled least-squares matching numpy.polyfit exactly, and (4) porting ENG-03 (Wasserstein-1) without SciPy.

**Primary recommendation:** Use the existing DEEP6.csproj (net48 target with Microsoft.NETFramework.ReferenceAssemblies) pattern for the standalone test project, but target **net8.0** (not net48) for the test project specifically — this allows `dotnet test` to run on macOS without Mono, while keeping detector source files compilable under both .NET 4.8 (NT8) and .NET 8 (tests) via multi-targeting or conditional compilation. Detector classes with zero NT8-API dependencies will compile cleanly under both TFMs.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| NinjaScript / .NET Framework 4.8 | NT8 8.1.x | Live detector runtime in NT8 | NT8 mandates .NET 4.8 |
| C# 10.0 (LangVersion in .csproj) | 10.0 | Language version for detector files | Already set in DEEP6.csproj [VERIFIED: DEEP6.csproj] |
| NUnit 3.14.0 | 3.14.0 | Test framework for C# detector unit tests | Standard for .NET; NUnit3TestAdapter supports `dotnet test` [VERIFIED: NuGet restore test above] |
| NUnit3TestAdapter 4.5.0 | 4.5.0 | Bridge between NUnit and `dotnet test` runner | Required by Microsoft.NET.Test.Sdk pattern [VERIFIED: local test] |
| Microsoft.NET.Test.Sdk 17.9.0 | 17.9.0 | Test execution harness | Required by `dotnet test` [VERIFIED: local test] |
| Microsoft.NETFramework.ReferenceAssemblies 1.0.3 | 1.0.3 | net48 reference assemblies for macOS build | Enables net48 targets without Windows SDK [VERIFIED: local restore test] |
| Newtonsoft.Json (NT8 bundled) | 13.0.x | NDJSON capture serialization in NT8 | Bundled with NT8 in `bin/` — no separate install [ASSUMED] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| System.Text.Json (in test project) | stdlib | Fixture JSON parsing in net8.0 test project | Test project only; avoids Newtonsoft dep in test TFM |
| Newtonsoft.Json NuGet | 13.0.3 | If test project needs to read capture NDJSON | Only if test project shares NDJSON parsing logic |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| net8.0 test project | net48 test + Mono | Mono not installed on this Mac; net8.0 runs cleanly on dotnet 10 SDK already present [VERIFIED: local test] |
| net8.0 test project | net48 test on Windows CI | Only viable if CI is Windows; unnecessary given dotnet 10 present on dev Mac |
| Hand-rolled W1 | SciPy via Python subprocess | Python-side only; C# must be self-contained |

**Installation:**
```bash
# Test project only — dotnet 10 already at /usr/local/share/dotnet/dotnet
# No extra installs needed for dotnet test on macOS
# NT8 runtime stays on Windows machine
```

**Version verification:**
```bash
# NuGet packages verified via dotnet restore success on /tmp/test48proj
# net48 restore: Restored /tmp/test48proj/test48.csproj (in 2.02 sec) [VERIFIED: 2026-04-15]
# net10 test run: Passed! 1 test [VERIFIED: 2026-04-15]
# Newtonsoft.Json: bundled in NT8 bin/ — version not verifiable without NT8 install [ASSUMED ~13.0]
```

---

## Architecture Patterns

### Recommended Project Structure
```
ninjatrader/
├── Custom/
│   ├── Indicators/DEEP6/
│   │   └── DEEP6Footprint.cs       # Monolith being SPLIT (GEX stays here Phase 17)
│   ├── Strategies/DEEP6/
│   │   └── DEEP6Strategy.cs        # Add UseNewRegistry flag
│   └── AddOns/DEEP6/
│       ├── Registry/
│       │   ├── ISignalDetector.cs  # Interface definition
│       │   ├── SignalResult.cs     # Result type
│       │   └── DetectorRegistry.cs # Registration + dispatch
│       ├── State/
│       │   └── SessionContext.cs   # NT8 C# port of Python SessionContext
│       ├── Math/
│       │   └── LeastSquares.cs     # Hand-rolled OLS (~20 LOC)
│       └── Detectors/
│           ├── Absorption/
│           │   ├── AbsorptionDetector.cs      # Migrated from monolith
│           │   └── AbsorptionConfig.cs        # (can be one file <= 300 LOC)
│           ├── Exhaustion/
│           │   ├── ExhaustionDetector.cs      # Migrated from monolith
│           │   └── ExhaustionConfig.cs
│           ├── Imbalance/
│           │   └── ImbalanceDetector.cs       # IMB-01..09 (~9 methods)
│           ├── Delta/
│           │   └── DeltaDetector.cs           # DELT-01..11
│           ├── Auction/
│           │   └── AuctionDetector.cs         # AUCT-01..05
│           ├── Trap/
│           │   └── TrapDetector.cs            # TRAP-01..05
│           ├── VolPattern/
│           │   └── VolPatternDetector.cs      # VOLP-01..06
│           └── Engine/
│               ├── TrespassDetector.cs        # ENG-02
│               ├── CounterSpoofDetector.cs    # ENG-03
│               ├── IcebergDetector.cs         # ENG-04
│               ├── MicroProbDetector.cs       # ENG-05
│               └── VPContextDetector.cs       # ENG-06
tests/                                         # ninjatrader/tests/
├── ninjatrader.tests.csproj                   # net8.0 + NUnit 3.14 (runs via dotnet test)
├── fixtures/
│   ├── absorption/abs-01-classic.json
│   ├── imbalance/imb-01-single.json
│   └── ...
└── Detectors/
    ├── AbsorptionDetectorTests.cs
    ├── ImbalanceDetectorTests.cs
    └── ...
```

### Pattern 1: ISignalDetector Interface
**What:** Minimum surface area — OnBar receives finalized FootprintBar + SessionContext; optionally OnMarketDepth for DOM-consuming detectors.
**When to use:** All 44 detectors implement this.
**Example:**
```csharp
// Source: CONTEXT.md locked decision + Python engine pattern
namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Registry
{
    public interface ISignalDetector
    {
        /// <summary>Called at bar close with finalized footprint data.</summary>
        SignalResult[] OnBar(FootprintBar bar, SessionContext session);

        /// <summary>Called from OnMarketDepth — only DOM-consuming detectors implement body.</summary>
        void OnMarketDepth(double price, long size, int side, int position, DateTime ts);

        /// <summary>Reset state at session boundary.</summary>
        void Reset();

        /// <summary>Family name for logging/registry identification.</summary>
        string Family { get; }
    }

    public sealed class SignalResult
    {
        public string SignalId;      // "IMB-01", "DELT-10", etc.
        public int Direction;        // +1, -1, 0
        public double Strength;      // 0-1
        public ulong FlagBit;        // bit position in SignalFlags ulong (see bit table)
        public string Detail;        // diagnostic string
    }
}
```

### Pattern 2: DetectorRegistry
**What:** List-based registry; registration order controls iteration; exposes results to DEEP6Strategy via a snapshot method.
**When to use:** Called from DEEP6Strategy.OnBarUpdate after bar is finalized.
**Example:**
```csharp
// Source: CONTEXT.md locked decisions
public sealed class DetectorRegistry
{
    private readonly List<ISignalDetector> _detectors = new List<ISignalDetector>();
    private SignalResult[] _lastResults = Array.Empty<SignalResult>();

    public void Register(ISignalDetector detector) { _detectors.Add(detector); }

    public void RunBar(FootprintBar bar, SessionContext session)
    {
        var all = new List<SignalResult>();
        foreach (var d in _detectors)
        {
            var results = d.OnBar(bar, session);
            if (results != null && results.Length > 0)
                all.AddRange(results);
        }
        _lastResults = all.ToArray();
    }

    public SignalResult[] GetLastResults() => _lastResults;
    public void ResetAll() { foreach (var d in _detectors) d.Reset(); }
}
```

**Performance note:** 44 detectors × O(n) per detector at bar close (~1/min for 1-min bars) is negligible. No per-callback overhead from the registry. [VERIFIED: Python engine same pattern, no hot-path issue]

### Pattern 3: SessionContext (C# port)
**What:** Singleton holding shared cross-detector state updated once per bar. Detectors read, never write directly.
**When to use:** Passed into every `OnBar()` call; lifecycle tied to NT8 indicator State.DataLoaded / date-change reset.
```csharp
// Source: deep6/state/session.py [VERIFIED]
public sealed class SessionContext
{
    public long   Cvd;
    public double Vwap;
    public double IbHigh, IbLow;
    public bool   IbComplete;
    public double AtrValue;           // Wilder's ATR(20) — updated per bar
    public double VolEma;             // EMA of TotalVol — updated per bar
    public double SessionPocPrice;    // Current session POC
    // Rolling histories (for detectors that need N-bar lookback):
    public Queue<long>   CvdHistory;   // maxlen = DeltaConfig.lookback (default 20)
    public Queue<double> PriceHistory; // close prices
    public Queue<long>   DeltaHistory; // bar deltas
    public Queue<double> PocHistory;   // POC prices (for VOLP-04)
    public Queue<FootprintBar> BarHistory; // recent finalized bars (maxlen = 10 for TRAP/VOLP)
}
```

### Pattern 4: Hand-Rolled Least-Squares (LeastSquares.cs)
**What:** OLS polynomial fit matching `numpy.polyfit(x, y, 1)` — returns slope and intercept at double precision.
**When to use:** DELT-10, EXH-05, TRAP-05.
**Example:**
```csharp
// Source: numpy.polyfit(x, y, 1) formula verified [VERIFIED: numpy docs pattern]
// numpy.polyfit uses lstsq; for degree=1 the closed form is:
//   n = len(x)
//   sx = sum(x), sy = sum(y), sxy = sum(x*y), sxx = sum(x*x)
//   slope = (n*sxy - sx*sy) / (n*sxx - sx*sx)
//   intercept = (sy - slope*sx) / n
public static class LeastSquares
{
    public static (double slope, double intercept) Fit(IReadOnlyList<double> y)
    {
        int n = y.Count;
        if (n < 2) return (0.0, y.Count > 0 ? y[0] : 0.0);

        // x = 0, 1, 2, ..., n-1 (same as numpy arange)
        double sx = n * (n - 1) * 0.5;           // sum of 0..n-1
        double sxx = n * (n - 1) * (2*n - 1) / 6.0; // sum of i^2
        double sy = 0.0, sxy = 0.0;
        for (int i = 0; i < n; i++)
        {
            sy  += y[i];
            sxy += i * y[i];
        }

        double denom = n * sxx - sx * sx;
        if (Math.Abs(denom) < 1e-12) return (0.0, sy / n); // degenerate: all same x
        double slope     = (n * sxy - sx * sy) / denom;
        double intercept = (sy - slope * sx) / n;
        return (slope, intercept);
    }
}
```

**Numerical stability notes:**
- For n=5..20 bars (DELT-10 default window), sxx fits exactly in double precision — no catastrophic cancellation risk [ASSUMED: for n <= 20, max sxx ~ 2660, well within double range].
- Python `np.polyfit` with deg=1 uses QR decomposition internally (more stable) — for n <= 20 the closed-form and QR produce identical results to 14 significant figures [ASSUMED: standard numerical analysis result].
- Edge case: all y equal (e.g., constant CVD during flat market) → slope = 0 correctly.
- Edge case: n < 2 → return (0, y[0]) as no-op, not a signal.

### Pattern 5: DOM State in C# (double[40])
**What:** Pre-allocated bid and ask arrays indexed by position (0 = best bid/ask), updated in-place from OnMarketDepth. Matches Python `DOMState` exactly.
**When to use:** TrespassDetector, IcebergDetector. Array passed by reference to detectors.
```csharp
// Source: deep6/state/dom.py + CONTEXT.md locked decision [VERIFIED]
// In SessionContext or DEEP6Footprint:
public double[] DomBidPrices = new double[40];
public double[] DomBidSizes  = new double[40];
public double[] DomAskPrices = new double[40];
public double[] DomAskSizes  = new double[40];

// OnMarketDepth handler (matches DEEP6Strategy.cs pattern):
void OnMarketDepth_UpdateDOM(MarketDepthEventArgs e)
{
    if (e.Position >= 40) return;  // clip at 40 levels
    if (e.MarketDataType == MarketDataType.Bid)
    {
        DomBidPrices[e.Position] = e.Operation == Operation.Remove ? 0 : e.Price;
        DomBidSizes[e.Position]  = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
    }
    else if (e.MarketDataType == MarketDataType.Ask)
    {
        DomAskPrices[e.Position] = e.Operation == Operation.Remove ? 0 : e.Price;
        DomAskSizes[e.Position]  = e.Operation == Operation.Remove ? 0 : (long)e.Volume;
    }
}
```

### Pattern 6: NDJSON Capture Harness
**What:** Write OnMarketData + OnMarketDepth events as newline-delimited JSON to `ninjatrader/captures/YYYY-MM-DD-session.ndjson`.
**When to use:** Live RTH session capture on Apex sim; minimum 5 sessions before parity declared.
**Example event schema:**
```json
{"t":"trade","ts":"2026-04-15T14:35:22.1234567Z","price":21050.25,"size":3,"aggressor":1,"bid":21050.00,"ask":21050.25}
{"t":"depth","ts":"2026-04-15T14:35:22.1230000Z","side":"bid","op":"update","pos":0,"price":21050.00,"size":150}
```
**NT8 serialization:** Use `Newtonsoft.Json.JsonConvert.SerializeObject(obj)` + `StreamWriter` with `AutoFlush=false`; flush every 1000 events to reduce I/O impact on callback thread. [ASSUMED: Newtonsoft.Json bundled in NT8 bin/]

### Anti-Patterns to Avoid
- **Allocating in OnMarketDepth:** Any `new` in the 1000/sec callback causes GC pressure. All state must be pre-allocated arrays. [VERIFIED: Python pattern + CONTEXT.md]
- **Iterating registry in OnMarketDepth:** Registry.RunBar() is called once per bar close, not per tick. DOM-consuming detectors implement `OnMarketDepth` on their instance but the registry calls it directly from the indicator's OnMarketDepth override.
- **Calling Print() in hot path:** NT8 Print() is thread-safe but expensive — gate behind a debug flag or call only at bar close.
- **SortedDictionary iteration in signal loops:** Existing AbsorptionDetector + ExhaustionDetector do `LINQ OrderBy` inside Detect(). This allocates. For new detectors, iterate `bar.Levels` directly (it's already a SortedDictionary, ascending order).
- **Feature-flagging per-signal vs per-registry:** The `UseNewRegistry` flag gates the entire registry. Do not add per-signal flags — it creates a combinatorial test surface.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHA/HMAC for NDJSON integrity | custom hash | None needed | Capture files are local; integrity via filename timestamp |
| Polynomial regression | multi-library solution | LeastSquares.cs (~20 LOC) | Only degree-1 OLS needed; closed form is 10 lines [VERIFIED: numpy formula] |
| Wasserstein-1 distance | SciPy Python bridge | Hand-rolled W1 (~30 LOC) | W1 on 1D uniform-weight arrays = sorting + prefix-sum; pure C# [see ENG-03 section below] |
| Naive Bayes | ML.NET | 20-line product-of-likelihoods | Stateless, fixed 3 features, fixed likelihood — no training needed [VERIFIED: micro_prob.py] |
| JSON serialization | custom serializer | Newtonsoft.Json (NT8-bundled) | Already in NT8 runtime [ASSUMED] |
| Cooldown per signal type | dictionary keyed by signal | Dictionary<string, int> barIndex | Already proven in ExhaustionDetector._cooldown pattern [VERIFIED: DEEP6Footprint.cs line 421-430] |

**Key insight:** SciPy is the only Python dependency that has no direct C# NuGet equivalent for production NT8 use. The Wasserstein-1 computation used in ENG-03 is algorithmically simple enough to hand-roll in ~30 LOC. See the ENG-03 pitfall section below.

---

## SignalFlags Bit Assignment for New Families

The Python `SignalFlags` bitmask is 45 bits (bits 0–44). [VERIFIED: deep6/signals/flags.py]

Current assignments:
| Range | Family | Count |
|-------|--------|-------|
| 0–3   | ABS (ABS-01..04) | 4 |
| 4–11  | EXH (EXH-01..08) | 8 |
| 12–20 | IMB (IMB-01..09) | 9 |
| 21–31 | DELT (DELT-01..11) | 11 |
| 32–36 | AUCT (AUCT-01..05) | 5 |
| 37–41 | TRAP (TRAP-01..05) | 5 |
| 42–43 | VOLP (VOLP-01..02) | 2 |
| 44    | TRAP_SHOT (Phase 12) | 1 |
| 45–47 | Meta-flags (PIN_REGIME, REGIME_CHANGE, SPOOF_VETO) | 3 |

**VOLP-03..06 extension (bits 44 is taken by TRAP_SHOT):**
VOLP bits 42–43 are reserved in flags.py; VOLP-03..06 need 4 new bits. The comment in flags.py says "VOLP-03..06 reserved Phase 4+, bits 44-47 would be used". Bit 44 is TRAP_SHOT. So VOLP-03..06 must use bits 48–51 (or 45–47 overlap with meta — they don't because meta are Phase 15 additions).

**C# ulong (64-bit) has room for bits 0–63:** The Python int64 bitmask fits in a C# `ulong`. New bit assignments for the C# SignalFlags:

| Bit | Signal ID | Family |
|-----|-----------|--------|
| 0–43 | ABS/EXH/IMB/DELT/AUCT/TRAP/VOLP-01..02 + TRAP_SHOT | Same as Python |
| 44 | TRAP_SHOT | Phase 12 |
| 45–47 | Meta-flags (reserved — do not use for signals) | Phase 15 |
| 48 | VOLP-03 (Volume surge) | VOLP extension |
| 49 | VOLP-04 (POC momentum wave) | VOLP extension |
| 50 | VOLP-05 (Delta velocity spike) | VOLP extension |
| 51 | VOLP-06 (Big delta per level) | VOLP extension |
| 52–57 | ENG-02..07 reserved | ENG family |

**Planner discretion note:** The exact bit assignments for bits 48–57 are Claude's discretion per CONTEXT.md. The above table is the recommended layout; it maintains Python compatibility for bits 0–44 and leaves bits 48+ available for ENG family.

---

## Hard Signal Deep-Dives

### DELT-08 (Delta Slingshot)
**What makes it hard:** Requires rolling 4-bar delta history; the "compressed" gate counts bars where `|delta| < total_vol * quiet_ratio`; the explosive gate checks `|delta| > total_vol * explosive_ratio`. [VERIFIED: delta.py lines 263–279]

**Port approach:** DeltaDetector owns a `Queue<long> deltaHistory` (maxlen matching Python default). Check queue on each OnBar call. No external state needed beyond what SessionContext already provides.

**Known Python bug to fix:** None found — algorithm is straightforward and tests pass. [ASSUMED: no bug found by reading source]

### DELT-10 (CVD Polyfit Divergence)
**What makes it hard:** Uses `numpy.polyfit(x, y, 1)` over 5–20 bar window. Must match Python double-precision output exactly on synthetic fixtures.

**Port approach:** Use LeastSquares.Fit(cvdHistory) and LeastSquares.Fit(priceHistory) to get slopes. Compare sign/magnitude per Python algorithm:
- If price_slope > 0 AND cvd_slope < -|price_slope| × divergence_factor → bearish divergence
- If price_slope < 0 AND cvd_slope > |price_slope| × divergence_factor → bullish divergence

**Fixture generation:** Generate 5–20 bar windows in Python, call numpy.polyfit, record expected slope values, assert C# matches to 6 decimal places.

### TRAP-05 (CVD Trap / polyfit)
**What makes it hard:** Same least-squares dependency as DELT-10. Window = `cvd_trap_lookback` bars. Fires when |slope| > min_slope AND current bar delta opposes prior CVD slope direction. [VERIFIED: trap.py lines 298–349]

### ENG-02 (Trespass / Logistic Approximation)
**What makes it hard:** NOT a pretrained model. The "logistic regression" in the Python source (`trespass.py`) is a **closed-form approximation** — `probability = min(max((ratio - 1.0) * 0.5 + 0.5, 0), 1)`. There are no weights to serialize. [VERIFIED: trespass.py lines 129–131]

**Port approach:** Straightforward — weight array pre-computed at construction, weighted sum, ratio, logistic approximation. No external dependency. Complexity is MODERATE, not HARD. (The CONTEXT.md classified ENG-02 as MODERATE; confirming that is correct.)

**DOM passthrough:** TrespassDetector implements `OnMarketDepth` to update the double[40] arrays in-place. OnBar reads a snapshot of those arrays.

### ENG-03 (Wasserstein-1 / CounterSpoof)
**What makes it hard:** Python uses `scipy.stats.wasserstein_distance`. SciPy is not available in NT8 C#.

**Wasserstein-1 hand-roll (~30 LOC):** For 1D distributions the W1 distance (Earth Mover's Distance with uniform positions 0..N-1) is:
```
Given u_weights[] and v_weights[] (both length N, non-negative):
  Normalize to pmf: u_pmf[i] = u_weights[i] / sum(u_weights)
  Compute CDF difference: CDF_diff[i] = sum(u_pmf[0..i]) - sum(v_pmf[0..i])
  W1 = sum(|CDF_diff[i]|) for i in 0..N-1
```
This matches SciPy's `wasserstein_distance(positions, positions, u_weights, v_weights)` when positions are 0..N-1 and both distributions are normalized. [CITED: https://en.wikipedia.org/wiki/Wasserstein_metric — 1D formula]

**The Python source does exactly this** — it passes `positions = list(range(n))` as both `u` and `v` position arrays to scipy.wasserstein_distance, meaning it's measuring how much weight moved along the index axis. [VERIFIED: counter_spoof.py lines 140–143]

**Port approach:**
```csharp
// LeastSquares.cs can host this as a sibling static class or separate file
public static double Wasserstein1(double[] u, double[] v)
{
    int n = Math.Min(u.Length, v.Length);
    double sumU = 0, sumV = 0;
    for (int i = 0; i < n; i++) { sumU += u[i]; sumV += v[i]; }
    if (sumU == 0 && sumV == 0) return 0.0;
    if (sumU == 0 || sumV == 0) return 0.0;  // match Python guard
    double w1 = 0, cdfU = 0, cdfV = 0;
    for (int i = 0; i < n; i++)
    {
        cdfU += u[i] / sumU;
        cdfV += v[i] / sumV;
        w1   += Math.Abs(cdfU - cdfV);
    }
    return w1;
}
```

**Guard match:** Python guards `prev_sum == 0 → w1 = 0` and `curr_sum == 0 → w1 = 0`. [VERIFIED: counter_spoof.py lines 128–140]

### ENG-04 (Synthetic Iceberg Refill < 250ms)
**What makes it hard:** Requires sub-millisecond timestamp tracking of DOM depletion/refill cycles. The `refill_window_ms` default is 250ms; precision required to avoid false positives.

**NT8 timestamp source:** In NT8, `OnMarketDepth` does not provide a per-event high-resolution timestamp. Use `DateTime.UtcNow.Ticks` (100-nanosecond resolution on .NET). Convert ticks to ms: `ticks / 10000.0`. [ASSUMED: DateTime.UtcNow precision on Windows is ~15ms kernel timer tick; for production accuracy use a Stopwatch-based monotonic clock instead]

**Better approach:** Use `System.Diagnostics.Stopwatch.GetTimestamp()` converted to ms: `(Stopwatch.GetTimestamp() - _startTick) * 1000.0 / Stopwatch.Frequency`. This provides ~100ns resolution regardless of system timer. [CITED: https://docs.microsoft.com/en-us/dotnet/api/system.diagnostics.stopwatch.gettimestamp]

**Absorption zone registration:** `IcebergDetector.MarkAbsorptionZone(price, radiusTicks)` must be called by the registry when AbsorptionDetector fires. This is a detector-to-detector dependency; handle via a cross-detector notification in DetectorRegistry after AbsorptionDetector.OnBar().

### ENG-05 (MicroEngine / Naive Bayes)
**What makes it hard:** Depends on E2 (TrespassResult) and E4 (IcebergSignal list) outputs — must be ordered last in the registry so those are already computed.

**No pretrained weights:** All "probabilities" are hardcoded likelihood constants (default bull_likelihood = 0.65). Fully deterministic from inputs. [VERIFIED: micro_prob.py lines 74–131]

**Port approach:** Pass TrespassResult and IcebergSignals as `SessionContext` fields populated by the time MicroProbDetector.OnBar() runs. Or use a second-pass pattern where the registry runs ENG-02 and ENG-04 first, collects results, then passes to ENG-05.

### ENG-06 (VP+Context Engine)
**What makes it hard:** Large scope — integrates POCEngine, SessionProfile (volume profile), GexEngine (already in DEEP6Footprint.cs), ZoneRegistry + LVN lifecycle FSM. Much of this is Phase 18 scorer territory.

**Phase 17 scope:** Port the ENG-06 signal outputs (POC signals, zone signals) as a detector, not the full scoring integration. The `VPContextResult` shape is the target. The GEX piece stays in DEEP6Footprint.cs for now (per CONTEXT.md specifics). The LVN lifecycle is out of scope (Phase 18). Port POCEngine + SessionProfile only.

**POCEngine in NT8:** POC is already computed by FootprintBar.Finalize() → `PocPrice`. POC signals (POC-01..08) are value-adds on top of that. For Phase 17, ENG-06 = POC signal detection using `PocHistory` from SessionContext.

---

## NT8 AddOns Compile Path

### How NT8 Loads AddOns Files
NT8's NinjaScript editor compiles all `.cs` files found recursively under:
- `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\`
- `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\`
- `%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\AddOns\`

**Subdirectory support is confirmed for modern NT8 (8.1.x):** NT8 compiles subdirectories recursively. The constraint is that all .cs files in Custom/ are compiled into a single assembly (`NinjaTrader.Custom.dll`). Subdirectory placement is a code organization convention only — NT8 does not enforce namespace-to-directory correspondence. [ASSUMED: based on community documentation pattern; not verifiable without NT8 installed on this Mac]

**Critical constraint:** Because all Custom files compile into one assembly, namespace collisions between detector files and existing indicator files must be prevented. The namespace split `NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.{Family}` avoids this. The using statements in DEEP6Footprint.cs already include `using NinjaTrader.NinjaScript.AddOns.DEEP6;` confirming the namespace exists. [VERIFIED: DEEP6Footprint.cs line 37]

**File naming:** NT8 editor may have issues with files that share partial names across subdirectories. Use fully qualified file names (`ImbalanceDetector.cs`, not `Detector.cs`) to avoid editor confusion.

**Installation:** User must copy detector files to the appropriate subdirectory under NT8 Custom. Export via Tools → Export NinjaScript after import is verified.

---

## NUnit on macOS — Critical Finding

### Problem
`dotnet test` on macOS for **net48** targets requires Mono. Mono is NOT installed on this Mac. [VERIFIED: `dotnet test` produced `Could not find 'mono' host` error — 2026-04-15]

### Solution
**Use net8.0 (or net10.0) as the test project TFM, not net48.** Detector classes that contain no NT8 API references (no `NinjaTrader.*` using directives) compile cleanly under net8.0. [VERIFIED: net10 NUnit test ran successfully — 2026-04-15]

### Implementation
1. Detector source files use only BCL types (`System.*`) — no NT8 imports. NT8-specific types (MarketDataEventArgs, etc.) are only in the indicator/strategy outer wrapper.
2. `FootprintBar`, `Cell`, `SessionContext`, `LeastSquares`, all detectors → no NT8 imports.
3. Test project `.csproj` targets `net8.0` (or `net10.0`); includes detector source files directly via `<Compile Include="...">` relative paths pointing to `Custom/AddOns/DEEP6/**/*.cs`.
4. NT8-specific shims (empty `NinjaTrader.Cbi` namespace stubs) can be in a `Shims/` folder if any detector accidentally pulls in an NT8 type — but the design must prevent this.
5. `dotnet test` path: `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj`

### Alternative (if NT8 types needed in detectors)
If any detector must reference NT8 types: use `#if NINJASCRIPT_RUNTIME` conditional compilation, or stub out the type locally in the test project.

**Quick run command:** `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj -x` (stop on first failure)
**Full suite command:** `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj`

---

## Common Pitfalls

### Pitfall 1: net48 Tests Require Mono on macOS
**What goes wrong:** Developer creates `ninjatrader/tests/` targeting net48, `dotnet test` aborts with "Could not find 'mono' host".
**Why it happens:** .NET Framework 4.8 binaries on non-Windows require Mono runtime. .NET SDK's test runner (VSTest) on macOS routes net48 test execution to Mono.
**How to avoid:** Target net8.0 in test project; keep detector classes free of NT8 API imports.
**Warning signs:** `dotnet test` exits immediately with `mono not found` error.

### Pitfall 2: NT8 AddOns Files Not Found After Subdirectory Creation
**What goes wrong:** Files under `AddOns/DEEP6/Detectors/Imbalance/` are not compiled by NT8; indicator throws "type not found" exceptions.
**Why it happens:** NT8 8.1.x recursively compiles, but file must be saved and F5 pressed in NinjaScript editor — the editor does not auto-watch new subdirectories after initial compilation.
**How to avoid:** After creating a new subdirectory and files, open NT8 NinjaScript editor, press F5 (compile all) explicitly. Verify in the Output tab that no errors appear before running the indicator.
**Warning signs:** NT8 throws `TypeLoadException` or "class not found" when applying indicator.

### Pitfall 3: SortedDictionary Levels Key Type Mismatch
**What goes wrong:** Python `bar.levels` uses `int` tick keys; C# `FootprintBar.Levels` uses `double` price keys. Code ported from Python that uses `tick_to_price()` / `price_to_tick()` will fail silently if the mapping isn't applied.
**Why it happens:** Python's `FootprintBar` stores `levels: dict[int, FootprintLevel]` keyed by ticks. C#'s `FootprintBar.Levels` is `SortedDictionary<double, Cell>` keyed by price.
**How to avoid:** When porting Python algorithms that iterate `bar.levels.keys()`, replace tick iteration with price iteration on `bar.Levels.Keys`. The IMB diagonal rule in C# iterates prices, not ticks. [VERIFIED: DEEP6Footprint.cs ImbalanceDetection + imbalance.py comparison]
**Warning signs:** C# detector produces zero signals on bars where Python engine produces signals; or key-not-found exceptions.

### Pitfall 4: polyfit Edge Cases
**What goes wrong:** `LeastSquares.Fit()` returns NaN or Inf when all CVD values are identical (flat market), or n < 2.
**Why it happens:** Denominator `n*sxx - sx*sx` = 0 when all x are identical (impossible for integer x = 0..n-1) OR when n < 2. However, if all y values equal y0, slope is 0 — that's fine. The dangerous case is n < 2.
**How to avoid:** Guard `n < 2 → return (0, y[0])`. The denominator cannot be 0 for integer x = 0..n-1 with n >= 2 (can be verified: n=2, sx=1, sxx=1, n*sxx-sx*sx = 2-1 = 1). [VERIFIED: math derivation]
**Warning signs:** DELT-10 or TRAP-05 fires on every bar or on flat markets.

### Pitfall 5: W1 Distance All-Zero Guard
**What goes wrong:** CounterSpoofDetector computes W1 = 0 (or NaN) when previous snapshot has all-zero bid sizes (first snapshot of session).
**Why it happens:** Python explicitly returns 0.0 when prev_sum or curr_sum = 0. [VERIFIED: counter_spoof.py lines 128–140]
**How to avoid:** Mirror the Python guard exactly: `if (sumU == 0 || sumV == 0) return 0.0;`
**Warning signs:** CounterSpoofDetector fires anomaly on session open before any DOM data arrives.

### Pitfall 6: DELT-08 Requires Prior Bar Delta Values in History
**What goes wrong:** DeltaDetector.deltaHistory doesn't contain the prior 3 bar deltas on session open, causing DELT-08 to fire on the first few bars with garbage history.
**Why it happens:** Queue is empty at session start; the `recent = list(delta_history)[-4:]` check in Python quietly handles this via `len(self.delta_history) >= 4`.
**How to avoid:** Guard `if (deltaHistory.Count < 4) return;` before computing DELT-08. Matches Python's guard. [VERIFIED: delta.py line 264]

### Pitfall 7: ENG-06 Scope Creep
**What goes wrong:** Phase 17 VPContextDetector implementation grows to include LVN lifecycle FSM, zone scoring, and GEX integration — blocking the wave it's in.
**Why it happens:** Python E6 is large and cross-cutting. Easy to scope all of it.
**How to avoid:** For Phase 17, VPContextDetector outputs only POC signals (POC-01..08 subset relevant to ENG-06). LVN lifecycle, zone scoring, and GEX integration are Phase 18.

---

## Code Examples

### IMB-01 Diagonal Scan (C# pattern)
```csharp
// Source: imbalance.py lines 75-97 — diagonal rule: ask[P] vs bid[P-1]
// C# version iterates SortedDictionary<double, Cell> (ascending by price)
var sortedPrices = bar.Levels.Keys.ToList(); // already sorted ascending
for (int i = 1; i < sortedPrices.Count; i++)
{
    double currPx = sortedPrices[i];
    double prevPx = sortedPrices[i - 1];
    long currAsk = bar.Levels[currPx].AskVol;
    long prevBid = bar.Levels[prevPx].BidVol;
    // Buy imbalance: ask[P] vs bid[P-1]
    if (prevBid > 0 && (double)currAsk / prevBid >= cfg.RatioThreshold)
        buyImbPrices.Add(currPx);
    else if (prevBid == 0 && currAsk > 0)
        buyImbPrices.Add(currPx);  // infinite ratio
}
```

### ENG-02 Trespass Weighted Sum (C#)
```csharp
// Source: trespass.py lines 100-133 [VERIFIED]
double weightedBid = 0, weightedAsk = 0;
for (int i = 0; i < depth && i < 40; i++)
{
    double w = 1.0 / (i + 1);  // harmonic weights, pre-computable
    weightedBid += domBidSizes[i] * w;
    weightedAsk += domAskSizes[i] * w;
}
double ratio = weightedAsk > 0 ? weightedBid / weightedAsk : 0.0;
double probability = Math.Max(0, Math.Min(1, (ratio - 1.0) * 0.5 + 0.5));
```

### ENG-05 Naive Bayes (C#)
```csharp
// Source: micro_prob.py lines 125-148 [VERIFIED]
// Features: (1) trespass direction, (2) iceberg direction, (3) imbalance direction
double pBull = 1.0, pBear = 1.0;
const double L = 0.65;  // bull_likelihood default
foreach (int dir in activeFeatureDirections)
{
    if (dir > 0) { pBull *= L; pBear *= (1.0 - L); }
    else         { pBull *= (1.0 - L); pBear *= L; }
}
double denom = pBull + pBear;
double prob = denom < 1e-9 ? 0.5 : pBull / denom;
```

### Feature Flag Integration in DEEP6Strategy
```csharp
// Add to DEEP6Strategy properties:
[NinjaScriptProperty]
[Display(Name = "Use New Detector Registry", Order = 50, GroupName = "Registry")]
public bool UseNewRegistry { get; set; }

// In EvaluateEntry():
if (UseNewRegistry && _registry != null)
{
    // Use registry results
    var results = _registry.GetLastResults();
    // ... map to confluence evaluation
}
else
{
    // Legacy ABS/EXH static calls (unchanged)
    var absSigs = AbsorptionDetector.Detect(...);
    var exhSigs = _exhDetector.Detect(...);
    // ... existing confluence logic
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Monolithic detector in indicator .cs | ISignalDetector registry + per-family files | Phase 17 | Testability, maintainability |
| static AbsorptionDetector.Detect() | Stateful instance implementing ISignalDetector | Phase 17 | Enables rolling state per detector |
| No C# tests | NUnit 3.14 test project with synthetic fixtures | Phase 17 | CI-ready regression guard |
| numpy.polyfit | Hand-rolled OLS (LeastSquares.Fit) | Phase 17 | Zero external C# deps for regression math |
| scipy.wasserstein_distance | Hand-rolled W1 (~30 LOC) | Phase 17 | Zero external deps for ENG-03 |

**Deprecated:**
- The single-file `DEEP6Footprint.cs` with inline AbsorptionDetector/ExhaustionDetector classes — those are extracted to AddOns per this phase. The monolith becomes a thin indicator wrapper.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | NT8 8.1.x compiles subdirectories under Custom/AddOns/ recursively | NT8 AddOns Compile Path | If subdirs aren't compiled, all new detector files fail to load in NT8. Mitigation: verify on NT8 machine before Wave 3+ ports begin |
| A2 | Newtonsoft.Json is bundled in NT8 bin/ (version ~13.0) | Standard Stack, Capture Harness | If not bundled, NDJSON serialization needs a different approach. Mitigation: use manual JSON string construction if Newtonsoft is absent |
| A3 | numpy.polyfit with deg=1 for n <= 20 is numerically equivalent to the closed-form OLS formula to 14 significant figures | LeastSquares / DELT-10 | If not equivalent, parity fixtures will show small float deltas. Mitigation: generate fixtures at Python side, verify C# matches to 6 decimals only |
| A4 | DELT-08, DELT-10, ENG-02 have no latent Python bugs | Python Bug Policy | If a Python bug exists and isn't fixed before parity fixtures are generated, both engines will carry the same bug and parity will pass for the wrong reason |

---

## Open Questions

1. **NT8 AddOns subdirectory compile behavior**
   - What we know: NT8 8.1.x documentation (community) says AddOns/ is compiled recursively. The using directive in DEEP6Footprint.cs (`using NinjaTrader.NinjaScript.AddOns.DEEP6;`) confirms AddOns namespace is active.
   - What's unclear: Whether NT8's editor requires a manual "include in project" step analogous to Visual Studio, or if it scans directories automatically.
   - Recommendation: Wave 1 first commit includes a trivial AddOns/DEEP6/Registry/ISignalDetector.cs; verify NT8 compiles before proceeding.

2. **Newtonsoft.Json availability in NT8 runtime**
   - What we know: NT8 bundles many third-party DLLs. Newtonsoft.Json is standard in .NET ecosystem.
   - What's unclear: Exact path and version bundled with NT8 8.1.x.
   - Recommendation: Use manual JSON string construction (`string.Format`) as fallback if Newtonsoft is not found at runtime; NDJSON events are simple enough.

3. **Stopwatch precision for ENG-04 on NT8 Windows machine**
   - What we know: `Stopwatch.GetTimestamp()` is monotonic, high-resolution on Windows.
   - What's unclear: Whether NT8's data thread (where OnMarketDepth fires) has any timer resolution limitations from NT8's own scheduler.
   - Recommendation: Use Stopwatch; document measurement in first capture session.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| dotnet SDK | Test project (macOS) | YES | 10.0.201 [VERIFIED] | — |
| NUnit 3.14 | Test project | YES (via NuGet restore) | 3.14.0 [VERIFIED] | — |
| Microsoft.NETFramework.ReferenceAssemblies | net48 build on macOS | YES (via NuGet) | 1.0.3 [VERIFIED] | — |
| Mono | net48 test execution on macOS | NO [VERIFIED] | — | Use net8.0 test project instead |
| NT8 installation | Detector compilation + live testing | NO (macOS dev machine) | — | Windows machine with NT8 8.1.x |
| Python 3.12 + pytest | Fixture generation + parity validation | YES (project constraint) | 3.12 [ASSUMED: project constraint] | — |
| Newtonsoft.Json | NDJSON capture in NT8 | UNKNOWN | ~13.0 [ASSUMED] | Manual string.Format JSON construction |

**Missing dependencies with no fallback:**
- NT8 installation on macOS — live testing requires Windows machine. CI for the test project (net8.0) can run on macOS; NT8 live validation must happen on Windows.

**Missing dependencies with fallback:**
- Mono: fallback = net8.0 test project (already verified to work).
- Newtonsoft.Json: fallback = manual JSON string construction for NDJSON capture.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | NUnit 3.14.0 |
| Config file | ninjatrader/tests/ninjatrader.tests.csproj (to be created in Wave 0) |
| Quick run command | `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj -x` |
| Full suite command | `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj` |

### Validation Dimension 1: Correctness (Bit-for-Bit Parity on Synthetic Fixtures)

Each detector has per-signal NUnit fixtures. A fixture is a JSON file at `ninjatrader/tests/fixtures/{family}/{signal-id}.json` containing:
- Input: `FootprintBar` fields + SessionContext state snapshot + prior bar (where needed)
- Expected: list of `{signalId, direction, strength (to 4 decimals), flagBit}`

**Correctness standard:** C# output matches Python output exactly on all synthetic fixtures. Strength values match to 4 decimal places. Signal fires/no-fires match 100%.

**Fixture generation workflow:**
1. Python: run `pytest tests/test_{family}.py -v --generate-fixtures` (fixture generation script to be created in Wave 0)
2. Verify fixture JSON manually for 2 edge cases per signal
3. NUnit tests load fixture JSON, construct C# FootprintBar, run detector, assert output matches

### Validation Dimension 2: Performance (No Callback Drops, Registry Budget)

| Check | Target | Method |
|-------|--------|--------|
| Registry.RunBar() latency per bar | < 5ms total for all 44 detectors | NT8 Print() timing at bar close in debug build |
| OnMarketDepth handler (DOM update) | < 0.1ms | Stopwatch measurement in DOM callback |
| Memory: no allocation in OnMarketDepth | 0 bytes/callback | NT8 GC pause counter; also verify by inspection |
| Signal count per bar | N/A | Log to NT8 Output Tab for 1 session |

**NT8 verify pattern:** Add `_debugTimingEnabled` flag to DetectorRegistry; when true, wrap `RunBar()` in `Stopwatch` and `Print()` elapsed.

### Validation Dimension 3: Safety (Live Strategy Regression Protection)

1. **Feature flag gate:** `UseNewRegistry = false` (default) keeps legacy ABS/EXH static calls active in DEEP6Strategy. Strategy behavior is identical to Phase 16 baseline until flag is explicitly toggled.
2. **Wave 2 parity gate:** Run migrated ABS/EXH detectors through 5 recorded sessions. C# signal counts within ±2/type/session vs Python reference.
3. **No-regression rule:** If any session replay shows ABS or EXH signal count outside ±2 vs Phase 16 baseline, Wave 2 parity gate FAILS and `UseNewRegistry` stays false.
4. **Risk gate paths untouched:** DEEP6Strategy.cs risk gates (account whitelist, RTH window, news blackout, daily loss cap) must not be modified in this phase (CONTEXT.md specifics). Verify via diff: only `OnBarUpdate` and property section should change.

### Validation Dimension 4: Completeness (All 34 Ported, All 10 Migrated, All Tests Green)

| Gate | How to Verify |
|------|---------------|
| 34 new signals ported | `dotnet test` reports green for all IMB/DELT/AUCT/TRAP/VOLP/ENG fixtures |
| 10 legacy signals migrated | ABS-01..04/ABS-07 and EXH-01..06 exist in new layout + pass all legacy fixture tests |
| Feature flag integration | DEEP6Strategy compiles and loads in NT8 with `UseNewRegistry` property visible in Properties panel |
| Parity dataset (5 sessions) | 5 × `ninjatrader/captures/YYYY-MM-DD-session.ndjson` committed to repo |
| Parity pass | Replay harness outputs ≤ ±2 signals/type/session for all 44 signals |
| No broken existing tests | `pytest tests/` green (Python side; any Python bug fixes verified) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IMB-01 | Single diagonal imbalance >= 300% | unit | `dotnet test --filter TestCategory=IMB` | No — Wave 0 |
| IMB-02 | Multiple (3+) at same price | unit | same | No — Wave 0 |
| IMB-03 | Stacked T1/T2/T3 | unit | same | No — Wave 0 |
| IMB-04..09 | Remaining IMB variants | unit | same | No — Wave 0 |
| DELT-01..09,11 | Non-polyfit delta signals | unit | `dotnet test --filter TestCategory=DELT` | No — Wave 0 |
| DELT-10 | CVD polyfit divergence | unit | same | No — Wave 0 |
| AUCT-01..05 | Auction signals | unit | `dotnet test --filter TestCategory=AUCT` | No — Wave 0 |
| TRAP-01..05 | Trap signals | unit | `dotnet test --filter TestCategory=TRAP` | No — Wave 0 |
| VOLP-01..06 | Volume pattern signals | unit | `dotnet test --filter TestCategory=VOLP` | No — Wave 0 |
| ENG-02..07 | Engine signals | unit | `dotnet test --filter TestCategory=ENG` | No — Wave 0 |
| ABS-01..04,07 | Migrated absorption (parity) | unit + parity | `dotnet test --filter TestCategory=ABS` | No — Wave 0 |
| EXH-01..06 | Migrated exhaustion (parity) | unit + parity | `dotnet test --filter TestCategory=EXH` | No — Wave 0 |

### Sampling Rate
- **Per task commit:** `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj -x`
- **Per wave merge:** `/usr/local/share/dotnet/dotnet test ninjatrader/tests/ninjatrader.tests.csproj`
- **Phase gate:** Full suite green + 5-session parity harness green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `ninjatrader/tests/ninjatrader.tests.csproj` — net8.0 target, NUnit 3.14, references detector source files
- [ ] `ninjatrader/tests/Helpers/BarBuilder.cs` — shared fixture builder (mirrors Python `make_bar()` in test_imbalance.py)
- [ ] `ninjatrader/tests/fixtures/` — directory structure created; at least 1 fixture per signal in scope
- [ ] `ninjatrader/tests/Detectors/ImbalanceDetectorTests.cs` — Wave 3 coverage for IMB-01..09
- [ ] `ninjatrader/tests/Detectors/DeltaDetectorTests.cs` — DELT-01..11
- [ ] `ninjatrader/tests/Detectors/AuctionDetectorTests.cs`, TrapDetectorTests.cs, VolPatternDetectorTests.cs, EngineTests.cs
- [ ] `ninjatrader/tests/Math/LeastSquaresTests.cs` — validates polyfit parity with numpy reference values
- [ ] Framework install: already available (`/usr/local/share/dotnet/dotnet` v10.0.201) — no additional install needed

---

## Security Domain

> `security_enforcement` is absent from config.json — treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No user auth in NT8 detector layer |
| V3 Session Management | No | NT8 session = bar data session, not user session |
| V4 Access Control | No | No multi-user access in NT8 indicator |
| V5 Input Validation | YES | Guard all detector inputs: null bar, zero TotalVol, empty Levels, NaN/Inf prices |
| V6 Cryptography | No | NDJSON captures are local files, no encryption requirement |
| V9 Communication | YES (partial) | NDJSON capture writes to local disk — no network exposure |

### Known Threat Patterns for NinjaScript / NDJSON Capture

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Null/zero footprint bar causes detector division by zero | Tampering | Guard: `if (bar == null || bar.TotalVol == 0) return empty` — already pattern in Python, must mirror in C# |
| NDJSON capture file grows unboundedly during session | Denial of Service | Cap at configurable max file size; rotate to new file; default cap = 100MB per session |
| Price injection via crafted tick — NaN or Inf propagates to detector | Tampering | `double.IsNaN(e.Price) || double.IsInfinity(e.Price)` guard in OnMarketData before AddTrade() |
| DOM array out-of-bounds via e.Position | Tampering | `if (e.Position >= 40) return;` guard — already in DEEP6Strategy.cs [VERIFIED: line 193] |

---

## Sources

### Primary (HIGH confidence)
- `deep6/engines/imbalance.py` — IMB-01..09 algorithms [VERIFIED: read in session]
- `deep6/engines/delta.py` — DELT-01..11 algorithms including DELT-08 slingshot + DELT-10 polyfit [VERIFIED: read in session]
- `deep6/engines/auction.py` — AUCT-01..05 + E9 FSM [VERIFIED: read in session]
- `deep6/engines/trap.py` — TRAP-02..05 algorithms including TRAP-05 polyfit [VERIFIED: read in session]
- `deep6/engines/vol_patterns.py` — VOLP-01..06 [VERIFIED: read in session]
- `deep6/engines/trespass.py` — ENG-02 weighted DOM + logistic approx [VERIFIED: read in session]
- `deep6/engines/counter_spoof.py` — ENG-03 W1 + cancel detection [VERIFIED: read in session]
- `deep6/engines/iceberg.py` — ENG-04 native + synthetic iceberg [VERIFIED: read in session]
- `deep6/engines/micro_prob.py` — ENG-05 Naive Bayes [VERIFIED: read in session]
- `deep6/engines/vp_context_engine.py` — ENG-06 structure [VERIFIED: read in session]
- `deep6/signals/flags.py` — 45-bit bitmask layout (bits 0–47) [VERIFIED: read in session]
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` — existing ABS/EXH C# implementation [VERIFIED: read in session]
- `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` — existing strategy + confluence evaluator [VERIFIED: read in session]
- `DEEP6.csproj` — net48 build config, NT8 reference paths, LangVersion=10.0 [VERIFIED: read in session]
- Local `dotnet test` experiments — confirmed net48 requires Mono (not installed), net10 works [VERIFIED: 2026-04-15]
- Local `dotnet restore` — confirmed Microsoft.NETFramework.ReferenceAssemblies 1.0.3 restores successfully [VERIFIED: 2026-04-15]

### Secondary (MEDIUM confidence)
- Wikipedia — Wasserstein-1 formula for 1D discrete distributions [CITED: https://en.wikipedia.org/wiki/Wasserstein_metric]
- Microsoft docs — Stopwatch.GetTimestamp() [CITED: https://docs.microsoft.com/en-us/dotnet/api/system.diagnostics.stopwatch.gettimestamp]

### Tertiary (LOW confidence)
- NT8 AddOns subdirectory recursive compilation behavior [ASSUMED: community pattern; not verified against NT8 source or official docs without NT8 installed]
- Newtonsoft.Json bundled in NT8 bin/ [ASSUMED: standard .NET ecosystem expectation]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all NuGet packages verified via local restore/test
- Architecture: HIGH — derived from verified Python source + existing C# patterns
- Hard signal algorithms: HIGH — derived from reading verified Python source
- NT8 compile path: MEDIUM — NT8 not installed on this Mac; community-documented behavior
- Pitfalls: HIGH (Mono finding) / MEDIUM (NT8 AddOns) — empirically verified where testable
- Assumptions: 4 assumptions documented in log above

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 for stable stack choices (net48/NUnit versions); 7 days for NT8 AddOns behavior if NT8 gets an update
