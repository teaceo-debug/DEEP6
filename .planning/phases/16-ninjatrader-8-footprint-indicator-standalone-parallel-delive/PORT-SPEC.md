# DEEP6 Python → NinjaTrader 8 C# Port Specification

**Authoritative spec for porting absorption, exhaustion, footprint, POC/VA from Python to C#.**
Source files cited inline. Do not deviate from these thresholds or algorithms.

---

## 1. Core Types

### Cell (per-price level)
```csharp
public sealed class Cell {
    public long BidVol;      // sell-aggressor volume (tick price <= best bid)
    public long AskVol;      // buy-aggressor volume  (tick price >= best ask)
    public long NeutralVol;  // between-spread prints (usually 0; not used in signals)
}
```

### FootprintBar (per bar)
```csharp
public sealed class FootprintBar {
    public int   BarIndex;
    public double Open, High, Low, Close;
    public SortedDictionary<double, Cell> Levels = new();  // key = price (NOT tick)
    public long  TotalVol;      // sum of (BidVol + AskVol) across all levels
    public long  BarDelta;      // sum of (AskVol - BidVol) across all levels
    public long  Cvd;           // cumulative delta carried forward
    public double PocPrice;     // price level with max volume
    public double BarRange;     // High - Low
    public long  RunningDelta;  // intrabar live delta
    public long  MaxDelta;      // intrabar max
    public long  MinDelta;      // intrabar min

    public void AddTrade(double price, long size, int aggressor) {
        if (!Levels.TryGetValue(price, out var lv)) { lv = new Cell(); Levels[price] = lv; }
        if (aggressor == 1) { lv.AskVol += size; RunningDelta += size; }
        else if (aggressor == 2) { lv.BidVol += size; RunningDelta -= size; }
        if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
        if (RunningDelta < MinDelta) MinDelta = RunningDelta;
        if (Open == 0) Open = price;
        if (price > High) High = price;
        if (Low == 0 || price < Low) Low = price;
        Close = price;
        TotalVol += size;
    }

    public void Finalize(long priorCvd = 0) {
        BarDelta = 0;
        foreach (var lv in Levels.Values) BarDelta += lv.AskVol - lv.BidVol;
        if (Levels.Count > 0) {
            double bestPx = 0; long bestVol = -1;
            foreach (var kv in Levels) {
                long v = kv.Value.AskVol + kv.Value.BidVol;
                if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
            }
            PocPrice = bestPx;
        }
        BarRange = High - Low;
        Cvd = priorCvd + BarDelta;
    }
}
```

### POC / VAH / VAL (bar-level, 70% value area)
Python ref: `/deep6/engines/poc.py:231-257`
```csharp
// Sort levels by volume desc; accumulate until >= 70% of TotalVol.
// VAH = max price in VA + TickSize (top of highest tick)
// VAL = min price in VA
public static (double vah, double val) ComputeValueArea(FootprintBar bar, double tickSize, double vaPct = 0.70) {
    if (bar.Levels.Count == 0 || bar.TotalVol == 0) return (bar.High, bar.Low);
    var sorted = bar.Levels.OrderByDescending(kv => kv.Value.AskVol + kv.Value.BidVol).ToList();
    double target = bar.TotalVol * vaPct;
    double acc = 0;
    var ticksInVa = new List<double>();
    foreach (var kv in sorted) {
        acc += kv.Value.AskVol + kv.Value.BidVol;
        ticksInVa.Add(kv.Key);
        if (acc >= target) break;
    }
    if (ticksInVa.Count == 0) return (bar.High, bar.Low);
    return (ticksInVa.Max() + tickSize, ticksInVa.Min());
}
```

### Aggressor classification (NT8-specific)
Inside `OnMarketData`:
- Cache `bestBid`, `bestAsk` from `MarketDataType.Bid`/`Ask` updates.
- On `MarketDataType.Last`: `aggressor = (price >= bestAsk) ? 1 /* buy */ : (price <= bestBid) ? 2 /* sell */ : 0 /* neutral */`.
- Pass to `AddTrade`. If aggressor==0, bump NeutralVol; do not update delta (matches Python gate).

---

## 2. Absorption Detector (4 variants)

**Source:** `/deep6/engines/absorption.py:1-244`, `/deep6/engines/signal_config.py:16-44`

### Config
```csharp
public sealed class AbsorptionConfig {
    public double AbsorbWickMin       = 30.0;   // wick vol % of total
    public double AbsorbDeltaMax      = 0.12;   // max |delta|/wick_vol
    public double PassiveExtremePct   = 0.20;   // fraction of range at top/bot
    public double PassiveVolPct       = 0.60;   // fraction of total vol in extreme zone
    public double StopVolMult         = 2.0;    // × vol_ema
    public double EvrVolMult          = 1.5;    // × vol_ema
    public double EvrRangeCap         = 0.30;   // × atr
    public double VaExtremeTicks      = 2.0;    // tick proximity
    public double VaExtremeStrengthBonus = 0.15;
}
```

### Signal output
```csharp
public enum AbsorptionType { Classic, Passive, StoppingVolume, EffortVsResult }
public sealed record AbsorptionSignal(
    AbsorptionType Kind, int Direction, double Price, string Wick,
    double Strength, double WickPct, double DeltaRatio, string Detail, bool AtVaExtreme);
```

### Algorithm (C# faithful port)
```csharp
public static List<AbsorptionSignal> Detect(
    FootprintBar bar, double atr, double volEma, AbsorptionConfig cfg,
    double? vah, double? val, double tickSize)
{
    var sigs = new List<AbsorptionSignal>();
    if (bar.Levels.Count == 0 || bar.TotalVol == 0 || bar.BarRange == 0) return sigs;

    double bodyTop = Math.Max(bar.Open, bar.Close);
    double bodyBot = Math.Min(bar.Open, bar.Close);

    long upperVol = 0, upperDelta = 0, lowerVol = 0, lowerDelta = 0, bodyVol = 0;
    foreach (var kv in bar.Levels) {
        double px = kv.Key;
        long v  = kv.Value.AskVol + kv.Value.BidVol;
        long d  = kv.Value.AskVol - kv.Value.BidVol;
        if (px > bodyTop)      { upperVol += v; upperDelta += d; }
        else if (px < bodyBot) { lowerVol += v; lowerDelta += d; }
        else                   { bodyVol  += v; }
    }

    double effWickMin = cfg.AbsorbWickMin * (bar.BarRange > atr * 1.5 ? 1.2 : 1.0);
    double barDeltaRatio = bar.TotalVol == 0 ? 0 : (double)Math.Abs(bar.BarDelta) / bar.TotalVol;

    // ABS-01: CLASSIC (upper then lower)
    TryClassic(upperVol, upperDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax, barDeltaRatio,
        bar.High, "upper", -1, sigs);
    TryClassic(lowerVol, lowerDelta, bar.TotalVol, effWickMin, cfg.AbsorbDeltaMax, barDeltaRatio,
        bar.Low,  "lower", +1, sigs);

    // ABS-02: PASSIVE
    double extremeRange = bar.BarRange * cfg.PassiveExtremePct;
    long upperZoneVol = 0, lowerZoneVol = 0;
    foreach (var kv in bar.Levels) {
        long v = kv.Value.AskVol + kv.Value.BidVol;
        if (kv.Key >= bar.High - extremeRange) upperZoneVol += v;
        if (kv.Key <= bar.Low  + extremeRange) lowerZoneVol += v;
    }
    if (upperZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct && bar.Close < bar.High - extremeRange) {
        double strength = Math.Min(upperZoneVol / (double)bar.TotalVol, 1.0);
        sigs.Add(new AbsorptionSignal(AbsorptionType.Passive, -1, bar.High, "upper", strength,
            upperZoneVol*100.0/bar.TotalVol, 0, "PASSIVE upper", false));
    }
    if (lowerZoneVol / (double)bar.TotalVol >= cfg.PassiveVolPct && bar.Close > bar.Low + extremeRange) {
        double strength = Math.Min(lowerZoneVol / (double)bar.TotalVol, 1.0);
        sigs.Add(new AbsorptionSignal(AbsorptionType.Passive, +1, bar.Low, "lower", strength,
            lowerZoneVol*100.0/bar.TotalVol, 0, "PASSIVE lower", false));
    }

    // ABS-03: STOPPING VOLUME
    if (bar.TotalVol > volEma * cfg.StopVolMult) {
        double strength = Math.Min(bar.TotalVol / (volEma * cfg.StopVolMult * 2.0), 1.0);
        if (bar.PocPrice > bodyTop)
            sigs.Add(new AbsorptionSignal(AbsorptionType.StoppingVolume, -1, bar.PocPrice, "upper",
                strength, 0, 0, "STOPPING VOL upper", false));
        else if (bar.PocPrice < bodyBot)
            sigs.Add(new AbsorptionSignal(AbsorptionType.StoppingVolume, +1, bar.PocPrice, "lower",
                strength, 0, 0, "STOPPING VOL lower", false));
    }

    // ABS-04: EFFORT vs RESULT
    if (bar.TotalVol > volEma * cfg.EvrVolMult && atr > 0 && bar.BarRange < atr * cfg.EvrRangeCap) {
        int dir = bar.BarDelta < 0 ? +1 : -1;
        double strength = Math.Min(bar.TotalVol / (volEma * cfg.EvrVolMult * 2.0), 1.0);
        double deltaRatio = bar.TotalVol == 0 ? 0 : Math.Abs(bar.BarDelta) / (double)bar.TotalVol;
        sigs.Add(new AbsorptionSignal(AbsorptionType.EffortVsResult, dir,
            (bar.High + bar.Low) / 2.0, "body", strength, 0, deltaRatio, "EFFORT vs RESULT", false));
    }

    // ABS-07: VA EXTREME BONUS (post-processing)
    double prox = cfg.VaExtremeTicks * tickSize;
    for (int i = 0; i < sigs.Count; i++) {
        var s = sigs[i];
        bool atVah = vah.HasValue && Math.Abs(s.Price - vah.Value) <= prox;
        bool atVal = val.HasValue && Math.Abs(s.Price - val.Value) <= prox;
        if (atVah || atVal) {
            sigs[i] = s with {
                AtVaExtreme = true,
                Strength = Math.Min(s.Strength + cfg.VaExtremeStrengthBonus, 1.0),
                Detail = s.Detail + (atVah ? " @VAH" : " @VAL")
            };
        }
    }
    return sigs;
}

private static void TryClassic(long wickVol, long wickDelta, long totalVol,
    double effWickMin, double deltaMax, double barDeltaRatio,
    double price, string side, int direction, List<AbsorptionSignal> sigs)
{
    if (wickVol == 0 || totalVol == 0) return;
    double wickPct = wickVol * 100.0 / totalVol;
    double deltaRatio = Math.Abs(wickDelta) / (double)wickVol;
    if (wickPct >= effWickMin && deltaRatio < deltaMax && barDeltaRatio < deltaMax * 1.5) {
        double strength = Math.Min(wickPct / 60.0, 1.0) * (1.0 - deltaRatio / deltaMax);
        sigs.Add(new AbsorptionSignal(AbsorptionType.Classic, direction, price, side,
            Math.Max(0, strength), wickPct, deltaRatio, $"CLASSIC {side}", false));
    }
}
```

---

## 3. Exhaustion Detector (6 variants + delta gate)

**Source:** `/deep6/engines/exhaustion.py:1-317`, `/deep6/engines/signal_config.py:48-73`

### Config
```csharp
public sealed class ExhaustionConfig {
    public double ThinPct             = 0.05;   // max vol frac of max-level vol
    public double FatMult             = 2.0;    // × avg level vol
    public double ExhaustWickMin      = 35.0;   // wick vol % of total
    public double FadeThreshold       = 0.60;   // curr/prior fade ratio
    public int    CooldownBars        = 5;      // suppression window
    public bool   DeltaGateEnabled    = true;
    public double DeltaGateMinRatio   = 0.10;
}
```

### Signal output
```csharp
public enum ExhaustionType { ZeroPrint, ExhaustionPrint, ThinPrint, FatPrint, FadingMomentum, BidAskFade }
public sealed record ExhaustionSignal(
    ExhaustionType Kind, int Direction, double Price, double Strength, string Detail);
```

### Cooldown state (instance-level on detector class, reset at session boundary)
```csharp
private readonly Dictionary<ExhaustionType, int> _cooldown = new();
public void ResetCooldowns() => _cooldown.Clear();

private bool CheckCooldown(ExhaustionType t, int barIndex, int cooldownBars) {
    if (!_cooldown.TryGetValue(t, out int last)) return true;
    return (barIndex - last) >= cooldownBars;
}
private void SetCooldown(ExhaustionType t, int barIndex) { _cooldown[t] = barIndex; }
```

### Delta trajectory gate
```csharp
private static bool DeltaGate(FootprintBar bar, ExhaustionConfig cfg) {
    if (!cfg.DeltaGateEnabled) return true;
    if (bar.TotalVol == 0) return true;
    double r = Math.Abs(bar.BarDelta) / (double)bar.TotalVol;
    if (r < cfg.DeltaGateMinRatio) return true;   // too small → don't block
    if (bar.Close > bar.Open) return bar.BarDelta < 0;   // bullish bar: buyers must be fading
    if (bar.Close < bar.Open) return bar.BarDelta > 0;   // bearish bar: sellers must be fading
    return true;                                          // doji: allow
}
```

### Main Detect() — port lines 109-316 faithfully
- **Zero print** (EXH-01) is **gate-exempt** — evaluated before gate check.
- **Gate check** runs after zero print, before variants 2-6.
- Each variant checks its cooldown, then fires and sets cooldown.
- **EXH-02 EXHAUSTION_PRINT:** iterate high tick (top) + low tick (bottom); threshold = `ExhaustWickMin/3` (lower for single level); strength = `min(pct/20, 1)`.
- **EXH-03 THIN_PRINT:** count levels in body where `vol < maxLevelVol * ThinPct`; fire if `thinCount >= 3`; strength = `min(thinCount/7, 1)`.
- **EXH-04 FAT_PRINT:** first level where `vol > avgLevelVol * FatMult`; direction=0; strength = `min(vol/(avgLevelVol*FatMult*2), 1)`; break after first.
- **EXH-05 FADING_MOMENTUM:** `|barDelta| > totalVol * 0.15` → direction opposite to bar direction; strength = `min(|barDelta|/totalVol, 1)`.
- **EXH-06 BID_ASK_FADE:** needs `priorBar`; compare `currHighAsk vs priorHighAsk * FadeThreshold` and mirror for bids.

---

## 4. NT8 Integration Contract

- Indicator subscribes per-tick via `OnMarketData` (`Calculate.OnEachTick`).
- `OnBarUpdate` with `IsFirstTickOfBar`: **prev bar is now closed** → call `Finalize(priorCvd)`, run Absorption + Exhaustion detectors, draw markers via `Draw.TriangleUp/Down` on prev bar.
- Maintain rolling state: `atr` (ATR(20) from NT8 built-in), `volEma` (EMA of TotalVol across last 20 bars), `priorCvd` (from prior bar's `Cvd`), `priorBar` reference (for fade).
- Session reset: detect RTH open (9:30 ET) in `OnBarUpdate` and call `exhaustionDetector.ResetCooldowns()`, reset session VAH/VAL tracker.

---

## 5. Signal Direction Convention
- `+1` = bullish reversal (long opportunity)
- `-1` = bearish reversal (short opportunity)
- `0` = neutral/context (FAT_PRINT only)

Markers on chart:
- Bullish absorption/exhaustion → up triangle/arrow below bar low
- Bearish absorption/exhaustion → down triangle/arrow above bar high
- Color: absorption = cyan/magenta; exhaustion = yellow/orange
