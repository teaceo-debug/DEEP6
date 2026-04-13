# Testing Patterns

**Analysis Date:** 2026-04-11

## Current Test State

**Status:** Phase 4a (Proposed, Not Implemented)

**Test Framework:** Not yet integrated

**Test Files Location:** `/Users/teaceo/DEEP6/tests/DEEP6.Tests.md` — specification document only (no executable tests)

**Actual Test Count:** 0

## Test Specification Document

The file `tests/DEEP6.Tests.md` defines unit test specifications for the seven-layer scoring engine, but these are **declarative specs only** — no test runner, assertion framework, or actual test code exists yet.

### Proposed Test Coverage (from DEEP6.Tests.md)

**E1 Footprint Tests:**
- Absorption wick >= 30% + |delta|/vol < 0.12 → score = 15
- STKt3 (7+ consecutive imbalances) → stkTier = 3
- Delta divergence (price down, cumD > 0) → bull +7pts

**E2 Trespass Tests:**
- 100% bid imbalance DOM → imbEma approaches +1.0, score = 20
- EMA(5) convergence: 5 ticks in → stable signal

**E3 CounterSpoof Tests:**
- W1 = 0.6 (> SpooW1=0.4) → spoof flagged, score elevated
- Cancel within 500ms after large order → _spEvt++

**E4 Iceberg Tests:**
- trade_size > display_size * 1.5 → native iceberg detected
- Refill at same price within 250ms → synthetic iceberg

**E5 Micro Tests:**
- All 4 likelihood inputs bull → P(bull) > 0.84
- Mixed inputs → P(bull) ≈ 0.50

**E7 ML Quality Tests:**
- qP=0.80 vs baseline=0.71 → "+12%" displayed
- Kalman: velocity converges to price derivative after 5 bars

**Scorer Tests:**
- 5 engines agree bull, score=85 → TYPE A
- 3 engines agree (< MinAgree=4) → score=0, QUIET

## Recommended Testing Framework

**For NinjaTrader 8 Indicator Unit Tests:**

### Option 1: xUnit + NUnit (Standalone Unit Tests)

**Rationale:**
- NT8 indicator code is a class (`DEEP6 : Indicator`) with calculateable logic
- Can extract calculation engines (E1-E7) into testable private-method wrappers
- No integration with NT8 runtime needed for scoring logic validation

**Framework Setup:**
```xml
<!-- In DEEP6.csproj -->
<ItemGroup Condition="'$(Configuration)' == 'Debug'">
  <PackageReference Include="xunit" Version="2.6.1" />
  <PackageReference Include="xunit.runner.visualstudio" Version="2.5.1" />
  <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.8.0" />
</ItemGroup>
```

**Test Project Structure:**
```
DEEP6.Tests/
├── DEEP6.Tests.csproj
├── E1FootprintTests.cs
├── E2TrespassTests.cs
├── E3CounterSpoofTests.cs
├── E4IcebergTests.cs
├── E5MicroTests.cs
├── E7MLQualityTests.cs
├── ScorerTests.cs
├── Fixtures/
│   └── TestDataFactory.cs
└── Utilities/
    └── MockMarketData.cs
```

### Option 2: Custom Test Harness (Minimal Dependency)

**Rationale:**
- Keep NT8 codebase decoupled from test frameworks
- Create thin test wrapper that instantiates DEEP6 and feeds mock market data
- Validate output via assertion helpers (no framework dependency in main code)

**Approach:**
```csharp
// In tests/DEEP6.Tests/E1FootprintTestHarness.cs
public class E1FootprintTestHarness
{
    private DEEP6 _indicator;
    
    [Test]
    public void AbsorptionWickAbove30Percent_WithLowDeltaRatio_ScoresMax15()
    {
        // Arrange: mock volumetric bar with specific wick/delta ratios
        // Act: call indicator RunE1() via reflection or internal helper
        // Assert: verify _fpSc == 15
    }
}
```

**Advantage:** No external dependencies in main `.csproj`

## Test File Organization

**Location Pattern (if xUnit adopted):**
- Test files: `tests/DEEP6.Tests/` (separate project or folder)
- Naming: `{Engine}Tests.cs` or `{Feature}TestSuite.cs`
- Fixtures: `tests/DEEP6.Tests/Fixtures/` (mock market data builders)

**Current State:**
- Test spec exists: `/Users/teaceo/DEEP6/tests/DEEP6.Tests.md`
- No .cs test files exist yet
- No test runner configured

## Proposed Test Structure

### Engine-Level Unit Tests (Standalone, No NT8)

```csharp
public class E1FootprintTests
{
    private DEEP6 _engine;
    private MockVolumetricData _marketData;
    
    [SetUp]
    public void Setup()
    {
        _engine = new DEEP6();
        _engine.SetDefaults();
        _marketData = new MockVolumetricData();
    }
    
    [Test]
    public void WickAbsorption_30PercentWick_LowDelta_Scores15()
    {
        // Arrange
        _marketData.SetWickPercentage(0.35);
        _marketData.SetDeltaRatio(0.10);
        
        // Act — need public method or reflection
        var score = _engine.CalculateE1Score(_marketData);
        
        // Assert
        Assert.AreEqual(15.0, score);
    }
    
    [Test]
    public void STKt3_SevenConsecutiveImbalances_Returns3()
    {
        // Arrange
        _marketData.SetConsecutiveImbalances(7, isBid: true);
        
        // Act
        var tier = _engine.GetStkTier(_marketData);
        
        // Assert
        Assert.AreEqual(3, tier);
    }
}
```

### Issues with Current Code

**Problem 1: Private Engine Methods**
- `RunE1()`, `RunE2()`, etc. are `private void`
- Cannot be called from test code directly
- **Solution:** Extract into `internal` helper class for testing, or use reflection for private method invocation

**Problem 2: Tight Coupling to NinjaTrader APIs**
- Engine methods access `Close[0]`, `Volume[0]`, `TickSize`, `BarsArray[0]`, `Instrument`
- No dependency injection or abstraction layer
- **Solution:** Create `IMarketData` interface that wraps NT8 data access

**Problem 3: State Mutation**
- Engines read/modify private fields directly: `_fpSc`, `_imbEma`, `_total`
- Hard to unit test in isolation
- **Solution:** Return calculation results instead of storing in fields, or refactor to functional style

## Refactoring Path for Testability

**Phase 4a: Extract Engine Logic**

```csharp
// New file: Indicators/DEEP6.Engines.cs
public class DEEP6Engines
{
    public static class E1Footprint
    {
        public struct Result
        {
            public double Score { get; set; }
            public int Direction { get; set; }
            public int StkTier { get; set; }
        }
        
        public static Result Calculate(IMarketData data, E1Parameters parms)
        {
            // Pure calculation logic, testable
            double uwPct = /* calc */;
            bool absorbed = uwPct >= parms.AbsorbWickMin;
            return new Result { Score = absorbed ? 15.0 : 0.0, /* ... */ };
        }
    }
}

// Interface for dependency injection
public interface IMarketData
{
    double Open { get; }
    double High { get; }
    double Low { get; }
    double Close { get; }
    long Volume { get; }
    double TickSize { get; }
    IVolumetricBars Volumetric { get; }
}
```

**Phase 4b: Add Test Fixtures**

```csharp
// tests/DEEP6.Tests/Fixtures/MockMarketData.cs
public class MockMarketData : IMarketData
{
    public double Open { get; set; }
    public double High { get; set; }
    public double Low { get; set; }
    public double Close { get; set; }
    public long Volume { get; set; }
    public double TickSize { get; set; } = 0.25;
    public IVolumetricBars Volumetric { get; set; }
}
```

## Mocking Strategy

**What to Mock:**
- NinjaTrader data series: `Close[0]`, `Volume[0]`, `High[0]`, `Low[0]`
- Volumetric data: `VolumetricBarsType.Volumes[bar].BarDelta`, `GetBidVolumeForPrice()`, etc.
- DOM data: bid/ask prices and volumes from `OnMarketDepth()` args
- Time: `Time[0]`, `DateTime.Now`
- Instrument metadata: `TickSize`, `Instrument.FullName`

**What NOT to Mock:**
- Calculation logic itself (this is what we're testing)
- Standard .NET classes: `Queue<T>`, `List<T>`, `Math`, `Linq`
- Enum values: `GexRegime`, `SignalType`, `DayType`

## Coverage Gaps (Current)

**Untested Areas:**

| Area | What's Not Tested | Risk | Priority |
|------|-------------------|------|----------|
| E1 Footprint | All calculations | High — absorption scoring affects overall signal | High |
| E2 Trespass | DOM imbalance EMA, logistic sigmoid | High — key confluence signal | High |
| E3 CounterSpoof | Wasserstein distance (W1), event tracking | Medium — enhances but not critical | Medium |
| E4 Iceberg | Trade volume vs display detection, refill logic | Medium — nice-to-have feature | Medium |
| E5 Micro | Bayesian probability calculation | High — core convergence test | High |
| E6 VP+CTX | DEX-ARRAY, VWAP/IB context scoring | Medium — context-dependent | Medium |
| E7 ML | Kalman filter state updates, quality classifier | Medium — derivative calculation | Medium |
| Scorer | Engine agreement logic, TYPE A/B thresholds | High — final signal generation | High |
| UI/Rendering | SharpDX footprint cells, WPF panel binding | Low — visual only | Low |
| Session State | VWAP/VAH/VAL accumulation, POC migration | Medium — accumulator logic | Medium |

## Integration Testing Challenges

**Why Full Integration Tests Are Hard:**
1. **NT8 Runtime Dependency:** Indicator runs in NinjaTrader's threading/data model
2. **Real Market Data Required:** Volumetric bars, Level 2 DOM require actual/simulated tick stream
3. **UI Rendering:** SharpDX/WPF rendering cannot run in automated test environment (no graphics context)
4. **Stateful Design:** Indicator accumulates session state across ticks; hard to reset

**Workaround:**
- **Unit tests** on extracted engine logic (with mock data)
- **Manual regression testing** on live/replay data in NT8
- **No CI/CD automated UI tests** (visual inspection only)

## Recommended Test Approach (Phase 4a)

**Priority 1 (High):**
1. Extract E1, E2, E5, Scorer logic to `DEEP6.Engines.cs` (pure functions)
2. Create xUnit tests for each engine with mock `IMarketData`
3. Test coverage target: 70% on scoring logic

**Priority 2 (Medium):**
4. Add E3, E4, E6, E7 tests
5. Create `TestDataFactory` for common market scenarios (trend, range, spike, etc.)
6. Manual testing protocol for full indicator in NT8

**Priority 3 (Low):**
7. Snapshot tests for signal feed format (text output stability)
8. Performance benchmarks for hot-path code (RunE1-E7 per tick)

## Test Execution

**When Implemented:**

```bash
# Run all tests
dotnet test DEEP6.Tests.csproj

# Run specific engine tests
dotnet test --filter "Category=E1Footprint"

# Coverage report
dotnet test /p:CollectCoverage=true /p:CoverageFormat=opencover
```

## Known Test Challenges

1. **Volumetric Data Access:**
   - `GetBidVolumeForPrice()` / `GetAskVolumeForPrice()` are NT8 internals
   - Cannot easily mock in unit tests
   - Workaround: Test via extracted interface, not direct API calls

2. **State Interdependency:**
   - E5 Micro depends on E1, E2, E4 results
   - Cannot test E5 in isolation without also testing upstream engines
   - **Solution:** Set mock input values directly, don't depend on engine output

3. **Session Accumulation:**
   - VWAP, CVD accumulate across session
   - Hard to test "after 30 minutes" logic in unit tests
   - **Solution:** Add test helper to simulate elapsed time

4. **Rendering Logic:**
   - `OnRender()`, `RenderFP()`, `RenderSigBoxes()` depend on SharpDX/WPF
   - Cannot run headless
   - **Decision:** Skip UI rendering in automated tests; manual verification only

## Documentation for Future Test Writer

**Entry Point for Test Development:**
- Read `/Users/teaceo/DEEP6/tests/DEEP6.Tests.md` for specification
- Consult `/Users/teaceo/DEEP6/Indicators/DEEP6.cs` lines 334-506 for engine calculation logic
- Reference `.editorconfig` for naming conventions (tests should follow same style)

**Key Calculation Entry Points:**
- `RunE1()` — line 334: footprint absorption, STK imbalance scoring
- `RunE2()` — line 389: DOM imbalance EMA and logistic scoring
- `RunE3()` — line 406: W1 Wasserstein distance calculation
- `RunE4()` — line 427: iceberg detection via trade size comparison
- `RunE5()` — line 446: Bayesian probability aggregation
- `RunE6()` — line 460: DEX-ARRAY, VWAP/IB context scoring
- `RunE7()` — line 484: Kalman filter + ML quality classifier
- `Scorer()` — line 509: engine agreement logic and signal type determination

**Parameters to Expose for Testing:**
- Default values in `OnStateChange()` State.SetDefaults block (line 191-209)
- All user-adjustable parameters exposed via `[NinjaScriptProperty]` (lines 72-119)

---

*Testing analysis: 2026-04-11*
