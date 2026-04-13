# Architecture

**Analysis Date:** 2026-04-11

## Pattern Overview

**Overall:** Monolithic single-indicator with embedded modular engines + SharpDX/WPF rendering

**Key Characteristics:**
- Seven independent scoring engines running on NinjaScript lifecycle callbacks
- Real-time data ingestion from Rithmic Level 2 DOM (up to 1,000 callbacks/second)
- Deterministic consensus-based scoring pipeline (agreement ratio multiplier)
- WPF overlay UI (header bar, left tabs, status pills, right panel) + SharpDX volumetric footprint rendering
- Session-scoped state tracking (VWAP, Initial Balance, POC migration, Day Type)
- NinjaTrader 8 integration via OnStateChange → OnBarUpdate → OnRender lifecycle

## Layers

**Data Ingestion (Event Handler Layer):**
- Purpose: Capture market data callbacks at tick/bar level granularity
- Location: `OnMarketDepth` (lines 246–265), `OnMarketData` (lines 267–268), `OnBarUpdate` (lines 233–244)
- Contains: Level 2 DOM queue updates, last trade price/volume, bar completion triggers
- Depends on: NinjaTrader Cbi/Data APIs, VolumetricBarsType
- Used by: All seven engines + session context

**Engine Layer:**
- Purpose: Compute directional bias and confidence score for each strategic pattern
- Location: `RunE1()` (lines 334–387), `RunE2()` (lines 389–402), `RunE3()` (lines 406–424), `RunE4()` (lines 427–442), `RunE5()` (lines 446–456), `RunE6()` (lines 460–480), `RunE7()` (lines 484–505)
- Contains: Footprint absorption/imbalance analysis, DOM queue trespass, Wasserstein spoof detection, iceberg pattern matching, Naive Bayes micro-probability, DEX-ARRAY context scoring, Kalman filter velocity + logistic ML quality
- Depends on: Session context state (_cvd, _vwap, _vsd, _ibH/_ibL, _pPoc, _emaVol), DOM arrays (_bV[], _aV[], _bP[], _aP[]), trade history queues
- Used by: Scorer engine

**Session Context Layer:**
- Purpose: Maintain intra-session reference levels (VWAP, IB, POC, Day Type, GEX regime)
- Location: `SessionReset()` (lines 282–290), `UpdateSession()` (lines 292–330)
- Contains: VWAP/VAH/VAL calculation, Initial Balance tracking (type classification: Wide/Normal/Narrow), POC migration counter, Day Type classification (TrendBull/TrendBear/BalanceDay/Unknown)
- Depends on: Bar OHLCV data, VolumetricBarsType for POC extraction
- Used by: All engines (especially E6 VP+CTX), UI display (header/pills)

**Scoring & Consensus Layer:**
- Purpose: Aggregate 7 engine scores into unified 0–100 confidence metric with signal type classification
- Location: `Scorer()` (lines 509–526)
- Contains: Direction voting (bit flags for bull/bear per engine), agreement ratio multiplier (max engines / total engines), signal type classification (TypeA ≥80, TypeB ≥65, TypeC ≥50)
- Depends on: All engine outputs (_fpDir, _trDir, _icDir, _miDir, _dexDir + scores _fpSc through _vpSc)
- Used by: Signal label generation, UI panel updates, chart rendering

**Rendering Layer (SharpDX):**
- Purpose: Draw volumetric footprint cells, POC lines, signal boxes, STKt markers onto chart canvas
- Location: `InitDX()` (lines 573–593), `DisposeDX()` (lines 595–602), `RenderFP()` (lines 607–655), `RenderSigBoxes()` (lines 657–678), `RenderStk()` (lines 680–691)
- Contains: Direct2D brush/font initialization, per-bar volumetric rendering (bid/ask cells with imbalance coloring), signal label box rendering, STKt triangle markers
- Depends on: SharpDX.Direct2D1/DirectWrite APIs, ChartControl coordinate transforms
- Used by: OnRender callback

**UI Construction Layer (WPF):**
- Purpose: Build and update interactive overlay UI elements (header, pills, tabs, right panel)
- Location: `BuildUI()` (line 695), `BuildHeader()` (lines 704–733), `BuildPills()` (lines 741–769), `BuildTabBar()` (lines 772–791), `BuildPanel()` (lines 794–843), `UpdatePanel()` (lines 879–927)
- Contains: WPF Border/StackPanel/Canvas hierarchy, label binding, progress bar updates, status dot indicators, score gauge drawing
- Depends on: WPF System.Windows.* namespaces, ChartControl hierarchy traversal (FindGrid)
- Used by: Realtime event handler

## Data Flow

**Rithmic L2 → OnMarketDepth → E2/E3 Engines:**

1. Rithmic Level 2 DOM snapshot arrives via `OnMarketDepth(MarketDepthEventArgs e)`
2. Bid/Ask prices and volumes stored in `_bV[level]`, `_aV[level]`, `_bP[level]`, `_aP[level]` arrays (up to 10 levels)
3. Large order detection: if volume ≥ `SpooQty`, logged to `_pLg` for spoof tracking
4. If operation = Remove, `ChkSpoof()` flags cancellations within `SpooCancelMs` window
5. `RunE2()` executes: exponential-decay weighted imbalance formula, logistic regression → `_pUp`, `_trSc`, `_trDir`
6. `RunE3()` executes: Wasserstein-1 distribution + cancel event count → `_spSc`

**Last Trade → OnMarketData → E4 Engine:**

1. Last trade (price, volume, isAsk) arrives via `OnMarketData(MarketDataEventArgs e)` MarketDataType.Last
2. `RunE4()` maps trade to DOM level, detects native iceberg (trade volume > displayed volume × 1.5)
3. Synthetic iceberg: checks `_pTr` history (trades within last 250ms at same price/direction)
4. Computes imbalance ratio: `(iceBull - iceBear) / total` → `_icSc`, `_icDir`

**Bar Close → OnBarUpdate → Full Scoring Pipeline:**

1. Bar completes: `OnBarUpdate()` fires (if BarsInProgress == 0, skip 1-min series)
2. `SessionReset()` if first bar of session (initializes VWAP, IB, CVD, etc.)
3. `UpdateSession()`: incremental VWAP, VAH/VAL, POC migration, Day Type, VWAP zone classification
4. `RunE1()`: footprint absorption/exhaustion detection, stacked imbalance tiers (StkT1/T2/T3), CVD delta
5. `RunE5()`: Naive Bayes micro-probability from E1/E2/E4 likelihoods
6. `RunE6()`: DEX-ARRAY pattern, VWAP proximity, IB extension, POC migration, GEX regime context
7. `RunE7()`: Kalman filter price/velocity, 8-feature logistic quality classifier
8. `Scorer()`: Aggregate scores, count bull/bear votes, apply agreement ratio multiplier
9. Plot values: `Values[0][0] = _total` (Score), `Values[1][0] = _imbEma` (Trespass EMA)
10. If signal fired (TypeB+): `MakeSigLabel()` (Draw.Text), `PushFeed()` (feed history)
11. If ShowLvls: `DrawLevels()` (Draw.HorizontalLine VWAP/IB/GEX/pdVAH/pdVAL/etc.)
12. If ShowPanel: `UpdatePanel()` (refresh UI gauges, status dots, bars)

**OnRender → SharpDX Footprint + UI Updates:**

1. OnRender callback fires at chart repaint
2. `InitDX()`: one-time brush/font factory initialization (if _dxOk == false)
3. `RenderFP()`: iterate visible bars [FromIndex, ToIndex]
   - For each bar, iterate price levels [Low, High] at TickSize increments
   - Fetch bid/ask volumes from VolumetricBarsType
   - Color cells: green (ask imbalance), red (bid imbalance), cyan (LVN), transparent (balanced)
   - Highlight POC row with gold left border
   - Render delta row below bar (format: "Δ +1,340" or "Δ -2,218")
4. `RenderSigBoxes()`: overlay first 5 feed items as gold/amber bordered boxes with multi-line labels
5. `RenderStk()`: draw orange triangle + "STKt{tier}" text at current bar if tier > 0
6. WPF UI updates run on Dispatcher.InvokeAsync (non-blocking)

**State Management:**

- **Per-Bar State:** `_fpSc`, `_fpDir`, `_trSc`, `_trDir`, `_icSc`, `_icDir`, `_miSc`, `_miDir`, `_dexFired`, `_dexDir`, `_vpSc`, `_mlSc`, `_total`, `_sigDir`, `_sigTyp`
- **Per-Session State:** `_vwap`, `_vsd`, `_vah`, `_val`, `_ibH`, `_ibL`, `_ibTyp`, `_ibDone`, `_ibConf`, `_dPoc`, `_pPoc`, `_pocMB`, `_pocMU`, `_dayTyp`, `_oPx`, `_sOpen`, `_iHi`, `_iLo`, `_cvd`
- **Queues/Buffers:** `_dQ` (delta queue, 5 bars), `_iLong` (imbalance long, 62 bars), `_iShort` (imbalance short, 12 bars), `_pLg` (large orders w/ timestamp), `_pTr` (trades w/ timestamp), `_mlH` (ML quality history, 20 bars), `_feed` (signal feed, max 12 items)

## Key Abstractions

**Enums (lines 49–55):**
- `GexRegime`: {NegativeAmplifying, NegativeStable, PositiveDampening, Neutral} — user-supplied external GEX regime
- `DayType`: {TrendBull, TrendBear, FadeBull, FadeBear, BalanceDay, Unknown} — intra-session classification
- `IbType`: {Wide, Normal, Narrow} — Initial Balance range classification
- `SignalType`: {Quiet, TypeC, TypeB, TypeA} — signal severity
- `VwapZone`: {Above2Sd, Above1Sd, AboveVwap, AtVwap, BelowVwap, Below1Sd, Below2Sd} — price proximity to VWAP

**Constants (lines 59–68):**
- `MX_FP = 25.0`, `MX_TR = 20.0`, `MX_SP = 15.0`, `MX_IC = 15.0`, `MX_MI = 10.0`, `MX_VP = 15.0` — engine max point contributions
- `DDEPTH = 10` — DOM depth array size

**Parameters (lines 71–120):**
- 7 engine-specific tuning groups (E1–E6), GEX user-supplied levels, Scoring thresholds, Display toggles
- See README.md lines 172–192 for parameter semantics

**State Structs (implicit):**
- Engine state stored as doubles: `_fpSc`, `_fpDir`, `_trSc`, `_trDir`, `_w1`, `_spSc`, `_icSc`, `_icDir`, `_pBull`, `_pBear`, `_miSc`, `_miDir`, `_vpSc`, `_dexFired`, `_mlSc`
- Session state: grouping of VWAP/IB/POC/Day-related fields
- Kalman filter state: `_kSt[2]` (position/velocity), `_kP[2,2]` (covariance matrix)

## Entry Points

**NinjaScript Lifecycle:**

`OnStateChange()` (lines 184–229):
- **State.SetDefaults:** Initialize all parameters with production-calibrated defaults
- **State.Configure:** Add 1-minute data series for reference
- **State.DataLoaded:** Create EMA(20) for volume/range smoothing, validate VolumetricBarsType availability
- **State.Realtime:** Build UI (header, pills, tabs, panel) on Dispatcher
- **State.Terminated:** Cleanup WPF and DirectX resources

`OnBarUpdate()` (lines 233–244):
- Skip if BarsInProgress == 1 (ignore 1-min series)
- Skip if CurrentBar < BarsRequiredToPlot (25 bars minimum)
- Session initialization if first bar of session
- Update session context (VWAP, IB, POC, Day Type)
- Execute engines: RunE1(), RunE5(), RunE6(), RunE7()
- Execute Scorer()
- Plot values
- Generate signal label if TypeB+
- Update UI (levels, panel)

`OnMarketDepth()` (lines 246–265):
- Fires ~1,000× per second during market hours
- Populate DOM arrays (_bV, _aV, _bP, _aP)
- Track large order placements (spoof detection)
- Execute E2, E3 on every call

`OnMarketData()` (lines 267–268):
- Last trade price/volume → E4 iceberg detection

`OnRender()` (lines 270–278):
- Chart canvas repaint callback
- Initialize DirectX on first call
- Execute RenderFP, RenderSigBoxes, RenderStk conditionally based on Show* flags

## Scoring Formula

```
Raw Score = E1_FOOTPRINT(_fpSc)    +  E2_TRESPASS(_trSc)       +  E3_COUNTERSPOOF(_spSc)
          + E4_ICEBERG(_icSc)      +  E5_MICRO(_miSc)          +  E6_VP+CTX(_vpSc)
          + E7_ML_QUALITY(_mlSc)

Engine Voting:
  Bull Engines  = Count engines where _dir == +1
  Bear Engines  = Count engines where _dir == -1
  Agreement Ratio = max(Bull, Bear) / (Bull + Bear)

Direction Consensus:
  if max(Bull, Bear) >= MinAgree (default 4):
    _total = min(Raw_Score × max(Agreement_Ratio, 0.7), 100)
    _sigDir = +1 if Bull > Bear, -1 if Bear > Bull
  else:
    _total = 0  (silence signal if consensus fails)

Signal Type:
  TypeA: _total >= TypeAMin (80) + ≥4 engines agree
  TypeB: _total >= TypeBMin (65) + ≥4 engines agree
  TypeC: _total >= 50 (no minimum consensus, alerts only)
  Quiet: _total < 50

Engine Contribution Thresholds (for label composition):
  ABSORB: _fpSc >= 12 AND _fpDir == _sigDir
  TRESS:  _trSc >= 10 AND _trDir == _sigDir
  ICE:    _icSc >= 8 AND _icDir == _sigDir
  LVN:    _vpSc >= 10 (no direction check — context layer)
  DEX:    _dexFired AND _dexDir == _sigDir

_sigLbl = "ABSORB·TRESS·ICE·LVN·DEX" (only firing components)
```

## Cross-Cutting Concerns

**Logging:**
- One-time print at DataLoaded: `[DEEP6] Loaded. Volumetric=true Instrument=NQ1!`
- No per-bar logging (performance-critical path)

**Validation:**
- BarsRequiredToPlot: 25 bar minimum
- MinCellVol threshold to filter noise in RenderFP
- E3 ILong queue requires minimum 5 items before Wasserstein calc

**Authentication:**
- Not applicable (NinjaTrader sandbox environment)

**Error Handling:**
- try-catch blocks in volumetric data access (VolumetricBarsType nullable checks)
- DoesNotExist guards on UI traversal (FindGrid null check, Window.GetWindow null check)
- Safe disposal pattern in DisposeDX: `D<T>(ref x)` generic helper

**Performance Optimization:**
- EMA decay: `_emaVol = _emaVol * 0.95 + vol * 0.05` (fast response)
- Queue dequeuing: explicit `.Dequeue()` when capacity exceeded
- OnMarketDepth returns early if Position >= DDEPTH
- OnBarUpdate returns early on skip conditions
- SharpDX batches rendering per visible bar range
- Dispatcher.InvokeAsync prevents UI blocking

---

*Architecture analysis: 2026-04-11*
