# Feature Landscape: DEEP6 v2.0 — 44-Signal Expansion

**Domain:** Institutional footprint auto-trading system (NQ futures, NinjaTrader 8)
**Researched:** 2026-04-11
**Milestone context:** Expanding from 3 signal types (absorption/exhaustion/stacked imbalance) to full 44-signal taxonomy
**Engine baseline:** 7 engines (E1–E7) functional, 0-100 scoring system in production

---

## Table Stakes

Features the system must have or it has no defensible edge over TradeDevils, ATAS, or Sierra Chart.

### 1. Absorption: All Four Variants Detected

**Why expected:** Absorption is DEEP6's stated core value proposition. A system that only detects "some" absorption is inferior to TradeDevils, which ships classic + stopping volume + passive + effort-vs-result out of the box.

| Variant | Detection Logic | Complexity | Extends |
|---------|----------------|------------|---------|
| Classic absorption | Wick ≥ 1.5× body + balanced delta (|delta| < AbsRatio × total volume) | Low | E1 RunE1() |
| Passive absorption | High volume concentrates at price extreme (top/bottom 20% of bar range) while price holds — limit order wall defense | Medium | E1 + new level scan |
| Stopping volume | POC falls in wick (not body) + volume exceeds session record (or ATR-scaled peak threshold) at extremes | Medium | E1 + VP context |
| Effort vs. result | Volume > 1.5× ATR-scaled average AND bar range < 30% of ATR — high effort, minimal result | Low | E1 |

**Detection algorithm for each:**
- Classic: `wickSize >= bodySize * AbsWickMult AND Math.Abs(delta) <= totalVol * AbsBalanceRatio`
- Passive: scan bid/ask vol array by price row; top/bottom 20% rows have > 60% of total bar volume while price does not break extreme
- Stopping volume: `barPOC == barHigh OR barPOC == barLow AND totalVol > rollingPeakVol * StopVolMult`
- Effort vs. result: `totalVol > _emaVol * EvRVolMult AND barRange < ATR(20) * EvRRangeCap`

**Confidence:** HIGH — ATAS documentation, TradeDevils product description, footprint textbook definitions all align.

**Dependency:** Volatility-adaptive thresholds (Feature #10) must exist for stopping volume and effort-vs-result to avoid false signals in low-vol sessions.

---

### 2. Exhaustion: All Six Variants Detected

**Why expected:** Exhaustion is the completion signal — without it, the system detects when institutions are absorbing but not when aggressors run out of ammunition. Zero print, thin print, fat print, and exhaustion print are all shipped by TradeDevils, OrderFlows, and Emoji Trading's suite.

| Variant | Detection Logic | Complexity | Extends |
|---------|----------------|------------|---------|
| Zero print | Price level within bar has 0 volume on both bid and ask sides — fast-move gap | Low | E1 renderer scan |
| Exhaustion print | High single-side volume (bid or ask) at price extreme with no follow-through (price fails to extend next bar) | Medium | E1 multi-bar |
| Thin print | Volume at price row < ThinPct (e.g., 5%) of bar's max row volume, inside bar body — confirms momentum | Low | E1 renderer scan |
| Fat print | Volume at price row > FatMult × bar's average row volume — strong acceptance level, future S/R | Low | E1 renderer scan |
| Fading momentum | Delta trajectory: 3-bar linear regression slope of per-bar delta is negative while price still advancing (divergence) | High | New E8 CVD engine |
| Bid/ask fade | Ask volume at bar extreme < 60% of prior bar's ask at same relative position — aggressor thinning out | Medium | E1 multi-bar |

**CVD delta trajectory divergence for fading momentum:**
- Pine Script reference uses cumulative delta fading relative to price as the primary exhaustion confirmation
- Implementation: maintain `_deltaSlope` as linear regression over last N bars (recommend 5) of per-bar delta values
- Divergence fires when `price making new high AND _deltaSlope < -DivSlopeThreshold`
- This IS the best approach per research — it catches exhaustion earlier than single-bar signals because it tracks the trajectory of aggressor commitment, not just one bar's delta

**Confidence:** HIGH — Confirmed across TradeDevils documentation, Orderflows platform, Emoji Trading documentation, and CVD divergence principles in Bookmap's blog.

**Dependency:** E8 CVD Engine (listed in PROJECT.md active requirements) is a prerequisite for fading momentum detection. Bid/ask fade requires multi-bar state tracking in E1.

---

### 3. LVN/HVN Volume Profile with Zone Lifecycle

**Why expected:** LVN levels are "extremely reactive in testing" per the user. Without explicit LVN detection and lifecycle tracking, the system cannot distinguish between a normal pullback and a pullback to a liquidity vacuum where price will accelerate.

**Detection algorithm (from research + VP LVN Pine Script reference):**
```
Step 1: Build per-session volume profile histogram (price bins = TickSize)
Step 2: Compute rolling average volume per bin across all bins
Step 3: LVN: bin volume < LvnThreshold × avgBin (e.g., 0.30 = 30% of average)
Step 4: HVN: bin volume > HvnThreshold × avgBin (e.g., 1.70 = 170% of average)
Step 5: Merge adjacent LVN bins into zones (min gap = 4 ticks between distinct zones)
Step 6: Rank LVN zones by: (1-normalizedVolume) × recencyWeight × touchCount
```

**Zone lifecycle states:**
| State | Trigger | Action |
|-------|---------|--------|
| Created | LVN bin detected in profile | Add to LVN registry, draw line |
| Defended | Price touches zone + absorption/stopping-vol fires within 2 bars | Increment touchCount, increase zone score |
| Broken | Price closes 2 bars through zone without absorption | Mark as broken, reduce confidence weight |
| Flipped | Broken zone subsequently causes failed retest | Reclassify: prior support → resistance |
| Invalidated | Session close without return + recency decay → score < threshold | Remove from active zones |

**Scoring formula (per zone):**
```
zoneScore = (1 - normalizedVolume) × 0.35
          + recencyWeight × 0.25           // decays 10%/session
          + (touchCount / maxTouches) × 0.25
          + (state == Defended ? 0.15 : 0)
```

**Complexity:** High — requires persistent cross-bar state, zone registry with lifecycle FSM, and SharpDX rendering for multiple zone lines with opacity indicating score.

**Extends:** E6 VP+CTX engine (DEX-ARRAY); replaces the current placeholder `ShowLvls` flat line rendering.

---

### 4. Signal Confluence Scoring with 44-Signal Taxonomy

**Why expected:** With 44 signals across 8 categories, a flat weighted-sum approach will generate noise. Professional systems (TradeDevils with 42 alert triggers, Pine Script reference with zone scoring) all use hierarchical confluence. Without this, the system will have too many false TypeA signals.

**Architecture:**

```
Layer 1 — Primary signal (absorption OR exhaustion fires) — required
Layer 2 — Context confirmation:
  - LVN zone proximity (within 3 ticks of zone) → +multiplier
  - GEX level proximity (within 5 ticks of call/put wall, gamma flip, HVL) → +multiplier
  - VWAP/VA alignment (price at VWAP ±1σ, VAH, VAL) → +multiplier
Layer 3 — Category agreement (N of 8 signal categories confirm direction) → agreement ratio
Layer 4 — Engine consensus (existing 7-engine voting system)
```

**44-signal category multipliers (by priority):**
| Category | Weight | Rationale |
|----------|--------|-----------|
| Absorption (4 signals) | 1.0 base + confirms | Primary alpha — absorption is the hypothesis |
| Exhaustion (6 signals) | 1.0 base + confirms | Secondary alpha — completion signal |
| Trapped Traders (5 signals) | 0.85 | Inverse imbalance is 80-85% win rate per research |
| Delta (11 signals) | 0.70 | Confirmation layer — delta direction validates absorption/exhaustion |
| Volume Patterns (6 signals) | 0.65 | Context — volume sequencing shows institutional intent |
| POC/Value Area (8 signals) | 0.60 | Level context — highest weight when near LVN |
| Imbalance (9 signals) | 0.55 | Structural — stacked imbalance T2/T3 are high value |
| Auction Theory (5 signals) | 0.50 | Regime context — unfinished business + poor high/low are leading signals |

**Interaction rules:**
- Absorption fires WITHOUT exhaustion confirmation → TypeC only (alert, no auto-execution)
- Absorption + exhaustion both fire → TypeB eligible
- Absorption + exhaustion + LVN proximity → TypeA eligible
- GEX level proximity adds a flat +8 to unified score (not direction-dependent)
- Inverse imbalance alone (no absorption) → standalone TypeC with separate execution logic

**Complexity:** High — requires refactor of Scorer() to accept per-category votes rather than per-engine votes; introduces signal registry pattern.

**Extends:** Scorer() in current architecture; partially replaces current agreement-ratio logic.

---

### 5. GEX Level Integration (SpotGamma API)

**Why expected:** The visual target explicitly shows call wall, put wall, gamma flip, and HVL on the chart. GEX levels define market-maker hedging regimes that directly affect NQ order flow — above gamma flip, MMs dampen volatility; below it, they amplify it. Ignoring GEX means ignoring a structural force on the order book.

**Key levels from SpotGamma:**
| Level | Behavior | Use in DEEP6 |
|-------|----------|-------------|
| Call Wall | Highest net call gamma strike — structural resistance | Fade absorption signals pointing above Call Wall |
| Put Wall | Highest net put gamma strike — structural support (floor) | Amplify absorption signals pointing to Put Wall defense |
| Gamma Flip | Net GEX = 0 — regime change boundary | Adjust DayType classification; below = amplifying regime (trend signals preferred) |
| HVL (High Vol Level) | Strike with highest total gamma (IV pinning zone) | Avoid fading near HVL — magnetic price behavior expected |

**API sourcing:** SpotGamma is confirmed to integrate with NinjaTrader and provides NQ futures levels. Research found GEX Profile [PRO] on TradingView as a self-updating indicator. For DEEP6, the approach is: SpotGamma API or CSV import daily (pre-market) with manual override capability as fallback.

**Implementation note:** GEX levels change daily with options expiration cycles. The system needs to handle: (a) levels updated pre-market, (b) intraday level degradation toward zero as gamma bleeds at expiration, (c) weekly vs. monthly expiration weighting differences.

**Complexity:** Medium — the API call and level storage is simple; the behavior logic (regime above/below gamma flip) requires E6 VP+CTX extension.

**Extends:** E6 VP+CTX (currently has GEX regime as user-supplied enum — this replaces manual entry with API data); GexRegime enum already exists.

---

### 6. Volatility-Adaptive Thresholds (ATR Normalization)

**Why expected:** Fixed thresholds calibrated to a 15-point ATR(20) NQ day will generate dozens of false signals on a 45-point ATR(20) trending day. All 44 signal thresholds must breathe with volatility or the system degrades in high-volatility regimes. TradeDevils' Orderflow Zigzag uses ATR-swing detection precisely for this reason.

**Implementation:**
```csharp
double atr = ATR(20)[0];
double atrMult = atr / BaselineATR; // BaselineATR = production-calibrated constant (e.g., 15.0 for NQ)
double adaptedAbsWick = AbsWickMinTicks * atrMult;
double adaptedStopVolMult = StopVolMult / Math.Sqrt(atrMult); // volume thresholds scale sublinearly
```

**Applied to:** AbsWickMinTicks, EvRVolMult, EvRRangeCap, StopVolMult, ThinPctThreshold, LvnSeparationMinTicks, ZeroPrintGapTicks.

**Not applied to:** GEX levels (options-market derived, independent of realized vol), LVN zone scores (volume-normalized already), DayType classification (uses IB range which is inherently vol-scaled).

**Complexity:** Low — single multiplication pass on threshold parameters; BaselineATR becomes a calibration constant in parameters.

**Extends:** All E1 signal detection code paths; does not replace any engine.

---

### 7. Auto-Execution via NT8 ATM Strategy

**Why expected:** The system's value proposition is auto-trading, not manual signal alerting. Without execution, DEEP6 is an expensive indicator, not a trading system.

**Signal gate for execution:**
- Minimum: TypeB signal (score ≥ 65, ≥ 4 engines agree)
- Preferred: TypeA with LVN confirmation OR GEX level alignment
- Blocked: Score < 65, consensus < 4, cooldown period active (configurable, e.g., 3 bars)
- Blocked: Signal direction conflicts with GEX regime (e.g., long signal below gamma flip in amplifying regime without additional confirmation)

**ATM integration points:**
- `AtmStrategyCreate()` — create bracket order on TypeA signal
- `AtmStrategyClose()` — close on opposing TypeA signal or stop
- Signal direction → order direction (long/short)
- Entry at market on close of signal bar (bar close execution, not intrabar)

**Complexity:** Medium — NT8 ATM API is well-documented; the gate logic is the complexity, not the execution.

**Extends:** New execution layer — does not replace any existing engine; sits after Scorer().

---

## Differentiators

Features that provide competitive advantage over ATAS, Sierra Chart, TradeDevils, and Bookmap.

### 8. Narrative Candle Classification (Pine Script Port)

**What:** Classify each bar into a hierarchy: Absorption > Exhaustion > Momentum > Rejection > Quiet, following the Andrea Chimmy / Pine Script reference framework. Only the highest-priority narrative wins per bar. Confirmation logic: absorption is confirmed only if defense or same-direction momentum fires within N bars (configurable, e.g., 2).

**Why differentiating:** No commercial NQ footprint platform implements a unified narrative hierarchy with confirmation windows. ATAS and TradeDevils detect individual signals; they do not synthesize them into a single narrative per bar. The Pine Script's approach — where the narrative drives signal classification rather than each signal being independent — produces far fewer false positives.

**Implementation:**
```csharp
enum BarNarrative { Quiet, Rejection, Momentum, Exhaustion, Absorption }

BarNarrative ClassifyBar(BarData bar) {
    if (IsAbsorption(bar)) return BarNarrative.Absorption;
    if (IsExhaustion(bar)) return BarNarrative.Exhaustion;
    if (IsMomentum(bar))   return BarNarrative.Momentum;
    if (IsRejection(bar))  return BarNarrative.Rejection;
    return BarNarrative.Quiet;
}
```

**Complexity:** Medium — requires refactoring E1 from parallel-signal detection to hierarchical classification; introduces confirmation look-forward buffer.

**Extends:** E1 RunE1() — significant internal refactor, same external interface.

---

### 9. Inverse Imbalance Trap Detection (Highest-Alpha Trapped Trader Signal)

**What:** Detect inverse imbalances — bid/ask imbalance cells where the high-volume side is NOT where price is going. Example: massive ask volume at price extreme (sellers) but price does NOT break down — the sellers are trapped. Typically followed by aggressive price extension in opposite direction (short squeeze / liquidation).

**Why differentiating:** Research cites 80-85% win rate for this signal. No commercial platform surfaces it as a standalone classified signal with a confidence weight. TradeDevils detects individual imbalance types but does not classify trapped-trader imbalance as distinct from directional imbalance.

**Detection logic:**
```
Bearish inverse: bid imbalance cells appear at bar LOW (sellers are trapped)
                 + price closes ABOVE midpoint of bar
                 + delta is POSITIVE (buyers won despite sell imbalance)
Bullish inverse: ask imbalance cells appear at bar HIGH (buyers are trapped)
                 + price closes BELOW midpoint of bar
                 + delta is NEGATIVE (sellers won despite buy imbalance)
```

**Complexity:** Low-Medium — detection is straightforward from existing VolumetricBarsType data; the complexity is correct integration with Trapped Traders category in the 44-signal scoring system.

**Extends:** E1 RunE1() (reads same volumetric data); adds a new signal category contribution.

---

### 10. ML Backend: Adaptive Signal Weighting + Regime Detection

**What:** Python FastAPI service that consumes DEEP6 signal history (signals fired, outcome, market state at signal time) and outputs optimized weights per signal category per market regime. Regime detection classifies the current session as: TrendBull, TrendBear, BalanceDay, HighVolatility, LowVolatility.

**Why differentiating:** Every commercial platform has static weights. DEEP6 v2.0 is the only system that evolves its own signal weighting based on what has actually worked in recent history. This is the long-horizon moat: as the system trades, the ML backend continuously narrows the effective signal set to only high-probability configurations per regime.

**Features within the ML backend:**
- Signal effectiveness tracker: (signal_type, regime, near_LVN, near_GEX) → win_rate, avg_PnL
- Weight optimizer: gradient descent on portfolio Sharpe ratio, updated nightly
- Regime classifier: Hidden Markov Model or logistic regression on ATR(20), VWAP deviation, IB expansion rate
- Entry timing model: classify whether to enter on signal bar close or wait for first retest

**Complexity:** High — requires data bridge (NT8 → Python), model training infrastructure, and safe deployment mechanism to push new weights back to NT8 without restart.

**Extends:** E7 ML Quality engine (currently Kalman + logistic in-process); the Python backend replaces the in-process logistic classifier for weight optimization while E7 retains real-time quality scoring.

---

### 11. E8 CVD Multi-Bar Divergence Engine

**What:** Dedicated cumulative delta divergence engine. Track rolling CVD over 5-bar windows, compute linear regression slope, detect divergence when price slope and CVD slope have opposite signs. Feeds directly into fading momentum exhaustion signal and the overall Engine Vote.

**Why differentiating:** Currently CVD is tracked as `_cvd` but there is no dedicated engine contributing to the vote. Research confirms delta trajectory divergence is the best early-warning exhaustion indicator — it fires 1-3 bars before single-bar exhaustion prints, giving earlier entry with better R:R.

**Logic:**
```csharp
// E8 RunE8(): called on OnBarUpdate
_deltaHistory.Enqueue(barDelta); // keep last N bars
if (_deltaHistory.Count >= N) {
    double deltaSlope = LinearRegressionSlope(_deltaHistory);
    double priceSlope = LinearRegressionSlope(_priceHistory);
    _cvdDivFired = Math.Sign(deltaSlope) != Math.Sign(priceSlope)
                   && Math.Abs(deltaSlope) > CvdDivSlopeMin;
    _e8Dir = _cvdDivFired ? (deltaSlope > 0 ? 1 : -1) : 0;
    _e8Sc  = _cvdDivFired ? Math.Min(Math.Abs(deltaSlope) / NormFactor * MX_E8, MX_E8) : 0;
}
```

**Complexity:** Medium — linear regression is O(N), runs on bar close, no real-time path; clean new engine following established pattern.

**Extends:** New E8 engine; Scorer() must be updated to include E8 in the vote.

---

### 12. E9 Auction State Machine (Unfinished Business + Poor High/Low)

**What:** Finite state machine tracking auction theory states across bars. States: OpenAuction, FinishedAuction, UnfinishedBusiness, PoorHigh, PoorLow, VolumeVoid. Transition logic based on how bars close relative to their range (single prints at extreme = poor high/poor low; price returns to fill = finished auction; no return = unfinished business).

**Why differentiating:** Auction theory is used by top-tier institutional traders but absent from all commercial footprint platforms as an explicit classified state. Poor highs/poor lows are among the highest-reliability "return to fill" predictors in NQ, particularly combined with LVN alignment.

**States and transitions:**
| State | Condition | Signal contribution |
|-------|-----------|-------------------|
| PoorHigh | Bar's high has single-print (zero/thin row) at top | Bearish bias — unfinished auction above |
| PoorLow | Bar's low has single-print (zero/thin row) at bottom | Bullish bias — unfinished auction below |
| VolumeVoid | 3+ consecutive LVN bins between current price and prior HVN | Acceleration expected — low friction zone |
| UnfinishedBusiness | Session closes with poor high/low AND no revisit | High-priority next-session level |
| FinishedAuction | Price returns to prior single-print and trades through | Cancels UnfinishedBusiness flag |
| MarketSweep | Price sweeps through prior session extreme + absorption fires | Sweep + absorption = high-conviction reversal |

**Complexity:** Medium — FSM is well-defined; main complexity is cross-session state persistence (unfinished business survives session reset).

**Extends:** New E9 engine; reads zero/thin print data from E1 (dependency).

---

### 13. Next.js Analytics Dashboard

**What:** Web interface for ML model performance visualization, signal analysis by regime, parameter evolution tracking, win rate by signal type and market condition.

**Why differentiating:** No commercial platform provides a personalized, trade-history-driven analytics view of which specific signal combinations are working for this system on this instrument. ATAS and Sierra Chart show indicators; they do not show "last 30 days: absorption+LVN proximity signals had 78% win rate in TrendBull sessions."

**Key views:**
- Signal effectiveness heatmap (signal_type × regime × proximity_context → win_rate)
- P&L attribution (which engines/signals drove profit vs. loss)
- Regime timeline (DayType classification history with P&L overlay)
- Parameter drift tracker (how ML has shifted weights over time)
- Live feed of active signals via NT8 data bridge (WebSocket)

**Complexity:** High — requires data bridge, dashboard framework, and ML integration; independent of NT8 runtime.

**Extends:** Entirely new system; no existing engine to extend.

---

## Anti-Features

Things to deliberately NOT build — over-engineering traps.

### Anti-Feature 1: Intrabar (Tick-Level) Execution

**What it is:** Triggering ATM strategy execution intrabar when absorption fires on a single tick rather than waiting for bar close.

**Why to avoid:** NinjaTrader's bar-update lifecycle is designed for bar-close execution. Intrabar execution via `OnMarketData` bypasses the signal validation pipeline (which runs on `OnBarUpdate`) and creates race conditions between engine state and execution state. The 1,000 callbacks/second throughput of `OnMarketDepth` is used by E2/E3 for DOM state, not for execution decisions.

**What to do instead:** Execute on bar close of the signal bar. If latency is a concern, investigate NT8 ATM's built-in entry timing options.

---

### Anti-Feature 2: Fully Automated Parameter Optimization Without Human Review Gate

**What it is:** The ML backend automatically pushes new signal weights to the live system without a human approval step.

**Why to avoid:** An ML model optimizing on recent trade history can overfit to a recent regime. If the model silently increases the weight of a signal that happened to work for 3 weeks, then regime changes, losses can be severe. The human review gate is not bureaucratic — it is the only safeguard against silent model degradation.

**What to do instead:** ML backend generates new weight candidates; operator reviews via dashboard; one-click deploy. Never fully autonomous.

---

### Anti-Feature 3: Multi-Instrument Support in v2.0

**What it is:** Extending 44-signal detection to ES, YM, MNQ simultaneously.

**Why to avoid:** NQ has instrument-specific calibration for every threshold in all 44 signals. The ATR baseline, LVN depth thresholds, GEX level sources, and even the absorption wick multiplier are NQ-specific. Premature multi-instrument support means maintaining instrument-specific parameter sets before the NQ system is proven.

**What to do instead:** Build per-instrument parameter namespacing into the architecture so future expansion is clean, but gate actual expansion on NQ system profitability.

---

### Anti-Feature 4: TradingView / Pine Script Maintenance

**What it is:** Keeping the Pine Script reference implementation up to date as DEEP6 evolves.

**Why to avoid:** This is explicitly out of scope. Pine Script is reference architecture only. Maintaining two codebases (C# + Pine Script) for the same logic doubles the maintenance burden with no trading benefit.

**What to do instead:** Extract all Pine Script logic into DEEP6 C# once during this milestone. Archive the Pine Script. Never update it again.

---

### Anti-Feature 5: Real-Time Web Charting

**What it is:** Replicating the NT8 footprint chart in the Next.js dashboard.

**Why to avoid:** NT8 handles rendering with SharpDX at chart repaint frequency. A web-based footprint chart requires WebSocket streaming of tick data, a canvas rendering engine, and ongoing synchronization — this is months of engineering for a feature that is already handled by NT8.

**What to do instead:** The Next.js dashboard is analytics-only (historical signal performance, ML model state, regime tracking). Live chart view stays in NT8.

---

### Anti-Feature 6: Sub-Tick Orderbook Reconstruction

**What it is:** Attempting to reconstruct the full Rithmic Level 2 orderbook beyond the 10 DOM levels currently tracked (DDEPTH = 10), or inferring hidden liquidity from order flow patterns.

**Why to avoid:** Rithmic Level 2 provides up to 40+ DOM levels, but DEEP6 currently tracks 10 (DDEPTH = 10) for performance reasons. Full orderbook reconstruction at 40 levels at 1,000 callbacks/second substantially increases GC pressure and risks frame drops in SharpDX rendering. The marginal signal quality improvement does not justify the performance risk.

**What to do instead:** Increase DDEPTH only if performance profiling shows headroom. Keep at 10 for the 44-signal expansion milestone.

---

## Feature Dependencies

```
ATR Normalization (#6)
  └─> Required by: Classic Absorption (#1), Stopping Volume (#1), Effort vs Result (#1),
                   Exhaustion Prints (#2), LVN Separation (#3)

Narrative Candle Classification (#8)
  └─> Required by: Auto-execution gate (#7) — execution only triggers on classified bar, not raw signal

E8 CVD Engine (#11)
  └─> Required by: Fading Momentum Exhaustion Variant (#2)

E1 Zero/Thin Print Detection
  └─> Required by: E9 Auction State Machine (#12) — reads single-print data from E1

LVN Zone Registry (#3)
  └─> Required by: Confluence Scoring LVN proximity multiplier (#4)
  └─> Required by: Auto-execution gate — LVN confirmation upgrades TypeB → TypeA (#7)

GEX Level Integration (#5)
  └─> Required by: Confluence Scoring GEX proximity multiplier (#4)
  └─> Required by: Auto-execution gate — regime check (#7)

Signal Confluence Scoring (#4)
  └─> Required by: Auto-execution gate (#7)
  └─> Required by: Narrative Classification contributes to (#8)

NT8 ↔ Web Data Bridge
  └─> Required by: ML Backend (#10)
  └─> Required by: Next.js Dashboard (#13)

ML Backend (#10)
  └─> Required by: Next.js Dashboard (#13) — dashboard visualizes ML state
```

---

## MVP Recommendation for This Milestone

**Implement in this order (each unblocks the next):**

1. ATR Normalization (#6) — foundational, low complexity, unblocks all signal detection
2. Absorption all 4 variants (#1) — core alpha, extends E1
3. Exhaustion zero/thin/fat/exhaustion print (#2 — four non-CVD variants) — extends E1, no new engine needed
4. Narrative candle classification (#8) — refactors E1 from parallel to hierarchical; unblocks TypeA gate
5. LVN zone detection + lifecycle FSM (#3) — medium complexity; enables LVN-gated execution
6. Signal confluence scoring with 44-signal taxonomy (#4) — medium complexity; requires LVN + GEX
7. GEX level integration (#5) — medium complexity; SpotGamma API or CSV import
8. E8 CVD engine (#11) — enables fading momentum exhaustion variant; adds 8th engine to vote
9. Inverse imbalance trap detection (#9 as standalone signal) — low-medium, high-alpha add
10. Auto-execution via NT8 ATM (#7) — requires #4 + #5 + #8 gating to be safe
11. E9 Auction State Machine (#12) — requires E1 zero/thin print; adds 9th engine
12. Volatility-adaptive thresholds revisit (performance tuning pass after live testing)
13. NT8 ↔ Web Data Bridge + ML Backend (#10) — async; can start in parallel with #5+
14. Next.js Dashboard (#13) — last; requires ML backend + data bridge

**Defer entirely:**
- Multi-instrument support (Anti-Feature #3)
- Sub-45-day ML weight deployment without human gate (Anti-Feature #2)
- Intrabar execution (Anti-Feature #1)

---

## Competitive Gap Analysis

| Feature | ATAS | Sierra Chart | Bookmap | TradeDevils | DEEP6 v2.0 |
|---------|------|-------------|---------|-------------|------------|
| Classic absorption | Yes | Partial | No (heatmap focus) | Yes | Yes (#1) |
| Passive absorption | Partial | No | Yes (limit wall vis.) | Yes | Yes (#1) |
| Stopping volume | Yes | Yes | Partial | Yes | Yes (#1) |
| Effort vs. result | Partial | Partial | No | No | Yes (#1) |
| Fading momentum (CVD slope) | Partial | Partial | CVD chart only | No | Yes (#2 + E8) |
| LVN zone lifecycle FSM | No | No | No | No | Yes (#3) — differentiator |
| Narrative candle hierarchy | No | No | No | No | Yes (#8) — differentiator |
| Inverse imbalance trap | No | No | No | No | Yes (#9) — differentiator |
| GEX level integration | No | Via plugin | Via CloudNotes | No | Yes (#5) |
| ML-adaptive signal weights | No | No | No | No | Yes (#10) — differentiator |
| Auction state machine | No | No | No | No | Yes (#12) — differentiator |

---

## Sources

Research findings drawn from:
- ATAS absorption/exhaustion documentation: https://atas.net/volume-analysis/strategies-and-trading-patterns/absorption-of-demand-and-supply-in-the-footprint-chart/
- Bookmap CVD divergence analysis: https://bookmap.com/blog/how-cumulative-volume-delta-transform-your-trading-strategy
- Bookmap platform comparison: https://bookmap.com/blog/comparing-bookmap-to-dom-footprint-and-volume-profile
- TradeDevils footprint indicator features: https://tradedevils-indicators.com/pages/the-best-order-flow-footprint-indicator-for-ninjatrader-8-page-2
- SpotGamma GEX concepts: https://support.spotgamma.com/hc/en-us/articles/15214161607827-GEX-Gamma-Exposure-Explained-What-It-Is-and-How-SpotGamma-Uses-It
- SpotGamma call wall: https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall
- SpotGamma put wall: https://support.spotgamma.com/hc/en-us/articles/15297856056979-Put-Wall
- SpotGamma gamma flip: https://support.spotgamma.com/hc/en-us/articles/15413261162387-Gamma-Flip
- SpotGamma NQ futures integration: https://spotgamma.com/trading-nq-futures-vanna-hiro-indicator/
- LVN detection methodology: https://www.mql5.com/en/articles/20327
- PhenLabs LVN/HVN auto-detection: https://www.tradingview.com/script/RvNPu7jq-LVN-HVN-Auto-Detection-PhenLabs/
- LuxAlgo volume profile map: https://www.luxalgo.com/blog/volume-profile-map-where-smart-money-trades/
- Orderflows print signal definitions: https://www.orderflows.com/oft5.html
- Effort vs. result VSA framework: https://oboe.com/learn/mastering-volume-spread-analysis-h448y2/effort-vs-result-mastering-volume-spread-analysis-1
- LiteFinance footprint complete guide: https://www.litefinance.org/blog/for-beginners/trading-strategies/order-flow-trading-with-footprint-charts/
- FuturesHive footprint guide 2025: https://www.futureshive.com/blog/footprint-charts-complete-guide-2025
