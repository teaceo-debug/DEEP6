# Requirements: DEEP6 v2.0 — Python Edition

**Defined:** 2026-04-13
**Core Value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades via direct Rithmic orders — all in Python, running on macOS.

## v1 Requirements

### Data Pipeline (DATA)

- [x] **DATA-01**: async-rithmic connection established to Rithmic with L2 DOM subscription for NQ (40+ levels per side)
- [x] **DATA-02**: Aggressor side field verified in async-rithmic tick callback — exchange-provided, not inferred
- [x] **DATA-03**: FootprintBar accumulator built from raw ticks — bid/ask volume per price level per bar using defaultdict[int, FootprintLevel]
- [x] **DATA-04**: BarBuilder coroutine fires on_bar_close at configurable intervals (1min default) with complete FootprintBar
- [x] **DATA-05**: DOM state maintained as pre-allocated arrays updated in-place — zero allocation per callback
- [x] **DATA-06**: asyncio event loop with uvloop handles 1,000+ DOM callbacks/sec without blocking
- [x] **DATA-07**: Session state persistence to disk (SQLite) survives process restart without losing IB/VWAP/CVD
- [x] **DATA-08**: Reconnection logic with freeze state — no new orders until position reconciliation after reconnect
- [x] **DATA-09**: GC disabled during trading hours; manual GC at session breaks only
- [ ] **DATA-10**: Footprint accuracy validated against ATAS/Quantower — bid/ask volumes per level per bar must match

### Architecture (ARCH)

- [x] **ARCH-01**: Python package structure: deep6/{data, engines, signals, scoring, execution, ml, api, dashboard}
- [x] **ARCH-02**: Process boundary: asyncio event loop (I/O) in main process, Kronos inference in dedicated subprocess via multiprocessing.Pipe
- [x] **ARCH-03**: ATR(20) normalization layer provides volatility-adaptive thresholds for all 44 signals
- [x] **ARCH-04**: Pairwise signal correlation matrix computed (Pearson) to identify and document redundant signals before implementation
- [x] **ARCH-05**: SignalFlags bitmask (int64) covers all 44 signals for O(popcount) scoring

### Absorption (ABS)

- [ ] **ABS-01**: Classic absorption detected — wick volume >= threshold with balanced delta (|delta| < ratio × total volume)
- [ ] **ABS-02**: Passive absorption detected — high volume concentrates at price extreme (top/bottom 20% of range) while price holds
- [ ] **ABS-03**: Stopping volume detected — POC falls in wick (not body) with volume exceeding ATR-scaled peak threshold
- [ ] **ABS-04**: Effort vs result detected — volume > 1.5× ATR-scaled average AND bar range < 30% of ATR
- [ ] **ABS-05**: Absorption signals prioritized highest in narrative cascade (absorption > exhaustion > momentum > rejection)
- [ ] **ABS-06**: Absorption confirmation logic — defense or same-direction momentum within N bars upgrades zone score
- [ ] **ABS-07**: Absorption at VA extremes (VAH/VAL) receives conviction bonus in zone scoring

### Exhaustion (EXH)

- [ ] **EXH-01**: Zero print detected — price level with 0 volume on both bid and ask (fast-move gap)
- [ ] **EXH-02**: Exhaustion print detected — high single-side volume at extreme with no follow-through next bar
- [ ] **EXH-03**: Thin print detected — volume at price row < 5% of bar's max row volume inside body
- [ ] **EXH-04**: Fat print detected — volume at price row > threshold × bar's average row volume (strong acceptance)
- [ ] **EXH-05**: Fading momentum detected via E8 CVD engine — 3-bar linear regression slope of delta diverges from price
- [ ] **EXH-06**: Bid/ask fade detected — ask volume at bar extreme < 60% of prior bar's ask at same relative position
- [ ] **EXH-07**: Delta trajectory divergence gate — exhaustion only fires when cumulative delta fading relative to price direction
- [ ] **EXH-08**: Exhaustion cooldown — suppress same sub-type for N bars after firing to prevent signal clustering

### Imbalance (IMB)

- [ ] **IMB-01**: Single imbalance detected at configurable ratio threshold (default 300%+)
- [ ] **IMB-02**: Multiple imbalance (3+ at same price) detected
- [ ] **IMB-03**: Stacked imbalances T1/T2/T3 (3/5/7 consecutive levels) detected with tier classification
- [ ] **IMB-04**: Reverse imbalance detected (opposite direction imbalance within bar)
- [ ] **IMB-05**: Inverse imbalance (trapped traders) detected — buy imbalances in red bar / sell imbalances in green bar (80-85% win rate)
- [ ] **IMB-06**: Oversized imbalance detected (10:1+ ratio at single level)
- [ ] **IMB-07**: Consecutive imbalance detected (same level across multiple bars)
- [ ] **IMB-08**: Diagonal imbalance detected — ask[P] vs bid[P-1] (one tick down) per confirmed algorithm
- [ ] **IMB-09**: Reversal imbalance pattern detected (imbalance direction change within bar sequence)

### Delta (DELT)

- [ ] **DELT-01**: Delta rise/drop classified per bar
- [ ] **DELT-02**: Delta tail detected — bar delta closes at 95%+ of its extreme value
- [ ] **DELT-03**: Delta reversal detected — intrabar delta flip from one extreme to opposite
- [ ] **DELT-04**: Delta divergence detected — price making new high/low while delta fails to confirm
- [ ] **DELT-05**: Delta flip detected — sign change in cumulative delta
- [ ] **DELT-06**: Delta trap detected — aggressive delta in one direction followed by price reversal
- [ ] **DELT-07**: Delta sweep detected — rapid delta accumulation across multiple price levels
- [ ] **DELT-08**: Delta slingshot detected — compressed delta followed by explosive expansion (72-78% win rate)
- [ ] **DELT-09**: Delta at min/max classified relative to session range
- [ ] **DELT-10**: CVD multi-bar divergence detected via numpy polyfit linear regression over 5-20 bar window
- [ ] **DELT-11**: Delta velocity computed — rate of change of cumulative delta per unit time

### Auction Theory (AUCT)

- [ ] **AUCT-01**: Unfinished business detected — non-zero bid at bar high or ask at bar low (price will return)
- [ ] **AUCT-02**: Finished auction detected — zero volume on bid at high or ask at low (exhaustion confirmation)
- [ ] **AUCT-03**: Poor high/low detected — single-print or low-volume extreme (incomplete auction)
- [ ] **AUCT-04**: Volume void (LVN gap) detected within bar — fast-move zone with no acceptance
- [ ] **AUCT-05**: Market sweep detected — rapid price traversal through multiple levels with increasing volume

### Trapped Traders (TRAP)

- [ ] **TRAP-01**: Inverse imbalance trap detected — stacked buy imbalances in red bar (longs trapped, must exit)
- [ ] **TRAP-02**: Delta trap detected — strong delta in one direction with price failure and reversal
- [ ] **TRAP-03**: False breakout trap detected — price breaks level, triggers stops, reverses immediately
- [ ] **TRAP-04**: High volume rejection trap detected — record volume at level with immediate rejection
- [ ] **TRAP-05**: CVD trap detected — CVD trend reversal trapping trend followers

### Volume Patterns (VOLP)

- [ ] **VOLP-01**: Volume sequencing detected — institutional accumulation/distribution pattern across 3+ bars
- [ ] **VOLP-02**: Volume bubble detected — isolated high-volume price level within bar
- [ ] **VOLP-03**: Volume surge detected — bar volume exceeds N× session average
- [ ] **VOLP-04**: POC momentum wave detected — POC migrating consistently in one direction across bars
- [ ] **VOLP-05**: Delta velocity spike detected — acceleration in delta rate-of-change
- [ ] **VOLP-06**: Big delta per level detected — single price level with outsized net delta

### POC / Value Area (POC)

- [ ] **POC-01**: Above/below POC classification per bar (bias indicator)
- [ ] **POC-02**: Extreme POC detected — POC at bar high or low (P/B reversal profile)
- [ ] **POC-03**: Continuous POC detected — same POC price defended across 3+ bars (strong acceptance)
- [ ] **POC-04**: POC gap detected — current bar POC more than N ticks from prior bar POC
- [ ] **POC-05**: POC delta computed — net delta specifically at the POC price level
- [ ] **POC-06**: Engulfing VA detected — current value area fully contains prior value area
- [ ] **POC-07**: VA gap detected — current value area has no overlap with prior value area
- [ ] **POC-08**: Bullish/bearish POC classified based on POC position relative to bar open/close

### Volume Profile Levels (VPRO)

- [ ] **VPRO-01**: Session volume profile computed with tick-level bin resolution using numpy
- [ ] **VPRO-02**: LVN zones detected — bins with volume < 30% of session average, merged into zones
- [ ] **VPRO-03**: HVN zones detected — bins with volume > 170% of session average
- [ ] **VPRO-04**: LVN zone lifecycle managed — 5-state FSM (Created → Defended → Broken → Flipped → Invalidated)
- [ ] **VPRO-05**: Zone scoring formula applied — type(0.35) + recency(0.25) + touches(0.25) + defense(0.15)
- [ ] **VPRO-06**: LVN reactivity validated — zones tested against historical price action for bounce/acceleration rate
- [ ] **VPRO-07**: Multi-session LVN persistence — developing profile carries forward with decay weighting
- [ ] **VPRO-08**: POC migration tracking — session POC movement direction and velocity computed per bar

### GEX Integration (GEX)

- [ ] **GEX-01**: GEX data ingested from FlashAlpha API (or Massive.com if better evaluated)
- [ ] **GEX-02**: Call wall, put wall, gamma flip level, and HVL available as price levels
- [ ] **GEX-03**: GEX regime classified — positive gamma (mean-reverting) vs negative gamma (amplifying)
- [ ] **GEX-04**: GEX regime modifies signal weighting — below gamma flip prefers trend signals, above prefers fade signals
- [ ] **GEX-05**: GEX-signal confluence scored — absorption at call/put wall receives conviction bonus
- [ ] **GEX-06**: GEX data staleness handled — stale flag when data age > threshold, weight decays

### Engines (ENG)

- [ ] **ENG-01**: E1 Footprint engine — absorption/exhaustion/stacked imbalances/CVD from FootprintBar data
- [ ] **ENG-02**: E2 Trespass engine — multi-level weighted DOM queue imbalance with logistic regression
- [ ] **ENG-03**: E3 CounterSpoof engine — Wasserstein-1 distribution monitor + large-order cancel detection
- [ ] **ENG-04**: E4 Iceberg engine — native (trade > DOM) + synthetic (refill < 250ms) iceberg detection
- [ ] **ENG-05**: E5 Micro probability engine — Naïve Bayes with decorrelated inputs from new signal categories
- [ ] **ENG-06**: E6 VP+CTX engine — DEX-ARRAY + VWAP/IB/GEX/POC with LVN zone lifecycle
- [ ] **ENG-07**: E7 ML Quality engine — Kalman filter + XGBoost classifier (replaces logistic) with 16+ features
- [ ] **ENG-08**: E8 CVD engine — cumulative volume delta with multi-bar divergence via numpy polyfit
- [ ] **ENG-09**: E9 Auction State Machine — FSM tracking auction theory states across bars
- [ ] **ENG-10**: E10 Kronos bias engine — foundation model directional prediction from OHLCV via subprocess

### Kronos Integration (KRON)

- [ ] **KRON-01**: Kronos-small (24.7M params) loaded from HuggingFace in dedicated subprocess
- [ ] **KRON-02**: multiprocessing.Pipe bridge for non-blocking inference requests from main event loop
- [ ] **KRON-03**: 20 stochastic samples per inference for directional confidence scoring (0-100)
- [ ] **KRON-04**: Re-inference every 5 bars with 0.95/bar confidence decay between inferences
- [ ] **KRON-05**: GPU inference preferred (RTX 3060+); CPU fallback with latency budget validation
- [ ] **KRON-06**: Kronos output integrated into E10 score contributing to confluence scorer

### TradingView MCP (TVMCP)

- [ ] **TVMCP-01**: TradingView MCP server configured in Claude Code ~/.claude/.mcp.json
- [ ] **TVMCP-02**: TradingView Desktop launched with --remote-debugging-port=9222
- [ ] **TVMCP-03**: Claude can read chart state (prices, indicators, Pine Script line levels)
- [ ] **TVMCP-04**: Claude can inject/modify Pine Script on live chart for visual validation
- [ ] **TVMCP-05**: Claude can capture chart screenshots for visual analysis
- [ ] **TVMCP-06**: Pine Script absorption/exhaustion zones from Bookmap Liquidity Mapper readable as cross-reference

### Zone Registry (ZONE)

- [ ] **ZONE-01**: Centralized ZoneRegistry manages all zone types (absorption, exhaustion, LVN, HVN, GEX levels)
- [ ] **ZONE-02**: Zone-signal interaction scored — absorption at LVN + GEX confluence = highest conviction
- [ ] **ZONE-03**: Zone merge logic — overlapping same-direction zones consolidate with combined score
- [ ] **ZONE-04**: Zone visual representation in dashboard — strong/medium/weak with distinct styling
- [ ] **ZONE-05**: Peak bucket cluster — zones narrowed to volume concentration peak

### Scoring & Confluence (SCOR)

- [ ] **SCOR-01**: Two-layer consensus — engine-level agreement ratio + category-level confluence multiplier
- [ ] **SCOR-02**: Category-level confluence — 8 signal categories each vote; 5+ agreement triggers 1.25× multiplier
- [ ] **SCOR-03**: Zone bonus scoring — zones scoring ≥50 add +6 to +8 points to confluence score
- [ ] **SCOR-04**: TypeA/B/C signal classification — TypeA requires absorption/exhaustion + zone confluence + 5+ category agreement
- [ ] **SCOR-05**: Volatility-adaptive scoring — all thresholds scale with ATR(20)
- [ ] **SCOR-06**: Signal narrative labels — human-readable context (ABSORBED @VAH, EXHAUSTED, DON'T CHASE)

### Auto-Execution (EXEC)

- [ ] **EXEC-01**: Direct Rithmic order submission via async-rithmic from TypeA/B confluence signals
- [ ] **EXEC-02**: Risk management — circuit breakers (max daily loss), position sizing (max contracts), consecutive loss limits
- [ ] **EXEC-03**: Entry timing — configurable delay after signal to confirm (avoid false triggers)
- [ ] **EXEC-04**: Stop placement — stops placed beyond absorption/exhaustion zone boundary via server-side bracket orders
- [ ] **EXEC-05**: Target placement — targets at opposing zone, VWAP, or next LVN/HVN level
- [ ] **EXEC-06**: Regime-aware execution — disabled in specific GEX regimes or low-volume conditions
- [ ] **EXEC-07**: Reconnection freeze — halt all execution during reconnection until position reconciliation complete
- [ ] **EXEC-08**: 30-day minimum paper trading before live capital

### Backtesting (TEST)

- [ ] **TEST-01**: Databento MBO historical replay engine — same code path as live for signal generation
- [ ] **TEST-02**: Footprint accuracy validation — Python footprint vs ATAS/Quantower on same bars
- [ ] **TEST-03**: Signal CSV export with timestamp, signal type, score, price, outcome per bar
- [ ] **TEST-04**: vectorbt parameter sweep framework for threshold optimization
- [ ] **TEST-05**: Walk-forward validation pipeline with WFE > 70% gate before any ML weights go live
- [ ] **TEST-06**: P&L attribution per signal type — which signals contribute to edge vs add noise
- [ ] **TEST-07**: Session state persistence validated — restart mid-session produces identical signals as continuous run

### ML Backend (ML)

- [ ] **ML-01**: FastAPI service in same asyncio event loop — receives signal + trade events directly
- [ ] **ML-02**: XGBoost model trained on signal history to optimize signal weighting
- [ ] **ML-03**: Optuna Bayesian hyperparameter optimization for all 44 signal thresholds
- [ ] **ML-04**: Regime detection classifier (HMM) — identifies market regime from signal patterns
- [ ] **ML-05**: Walk-forward cross-validation with purged splits (no future leakage)
- [ ] **ML-06**: Weight file generation — JSON config with per-signal weights, per-regime adjustments
- [ ] **ML-07**: Model performance tracking — win rate, profit factor, Sharpe per signal type per regime
- [ ] **ML-08**: Human approval gate — no weight file deployed without explicit operator confirmation

### Analytics Dashboard (DASH)

- [ ] **DASH-01**: Next.js 15 App Router dashboard with WebSocket for real-time updates from FastAPI
- [ ] **DASH-02**: Signal performance view — win rate, avg P&L, frequency per signal type with time filters
- [ ] **DASH-03**: Regime visualization — current and historical regime classification
- [ ] **DASH-04**: Parameter evolution view — ML threshold adjustments over time
- [ ] **DASH-05**: Zone analysis — which zone types produce best outcomes, lifecycle statistics
- [ ] **DASH-06**: Footprint chart rendering via Lightweight Charts v5.1 custom series plugin
- [ ] **DASH-07**: Session replay — review any session with all signals and zones reconstructed

### Trading Web App (APP)

- [x] **APP-01**: Custom footprint chart via Lightweight Charts v5.1 custom series — bid/ask volume per price level with zone overlays (LVN, HVN, GEX, absorption)
- [ ] **APP-02**: One-click trade execution panel — TYPE_A/B signals displayed with full context (categories, GEX regime, zones, Kronos bias), confirm or auto-execute
- [x] **APP-03**: Real-time WebSocket from FastAPI — signal events, bar updates, position state, P&L pushed within 200ms of bar close
- [x] **APP-04**: Session replay — reconstruct any historical session bar-by-bar with all signals, zones, orders visible, step forward/back
- [ ] **APP-05**: Mobile push notifications via service worker — TYPE_A alerts to phone within 5 seconds
- [x] **APP-06**: Portfolio dashboard — live P&L, daily/weekly/monthly performance, win rate by tier, drawdown, circuit breaker status
- [ ] **APP-07**: Authentication + multi-device — operator monitors from laptop and phone simultaneously
- [x] **APP-08**: Zero TradingView dependency — complete trading workflow (chart, signals, execution, replay) within DEEP6 web app

## v2 Requirements

### Multi-Instrument

- **MULTI-01**: ES (S&P 500) futures support with recalibrated thresholds
- **MULTI-02**: YM, RTY, CL, GC futures support
- **MULTI-03**: Per-instrument ML models with independent weight files

### Advanced ML

- **AML-01**: Deep learning models (LSTM/Transformer) for sequence prediction
- **AML-02**: Reinforcement learning for dynamic position sizing
- **AML-03**: Cross-instrument signal correlation for macro regime detection

### Full Web Charting

- **WEB-01**: Custom web-based footprint chart (replace TradingView dependency)
- **WEB-02**: Mobile-responsive dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| NinjaTrader 8 / C# | Replaced by Python + async-rithmic |
| Pine Script maintenance | Reference only — Python is the single codebase |
| Social/community features | Single-user institutional tool |
| Mobile app | Desktop + web dashboard |
| Options trading execution | Futures only; options data for GEX context |
| Multi-instrument (v1) | NQ only — perfect on one first |

## Traceability

Updated during roadmap creation (2026-04-11).

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Pending |
| DATA-06 | Phase 1 | Pending |
| DATA-07 | Phase 1 | Complete |
| DATA-08 | Phase 1 | Complete |
| DATA-09 | Phase 1 | Complete |
| DATA-10 | Phase 1 | Pending |
| ARCH-01 | Phase 1 | Pending |
| ARCH-02 | Phase 1 | Complete |
| ARCH-03 | Phase 1 | Complete |
| ARCH-04 | Phase 1 | Complete |
| ARCH-05 | Phase 1 | Pending |
| ABS-01 | Phase 2 | Pending |
| ABS-02 | Phase 2 | Pending |
| ABS-03 | Phase 2 | Pending |
| ABS-04 | Phase 2 | Pending |
| ABS-05 | Phase 2 | Pending |
| ABS-06 | Phase 2 | Pending |
| ABS-07 | Phase 2 | Pending |
| EXH-01 | Phase 2 | Pending |
| EXH-02 | Phase 2 | Pending |
| EXH-03 | Phase 2 | Pending |
| EXH-04 | Phase 2 | Pending |
| EXH-05 | Phase 2 | Pending |
| EXH-06 | Phase 2 | Pending |
| EXH-07 | Phase 2 | Pending |
| EXH-08 | Phase 2 | Pending |
| IMB-01 | Phase 3 | Pending |
| IMB-02 | Phase 3 | Pending |
| IMB-03 | Phase 3 | Pending |
| IMB-04 | Phase 3 | Pending |
| IMB-05 | Phase 3 | Pending |
| IMB-06 | Phase 3 | Pending |
| IMB-07 | Phase 3 | Pending |
| IMB-08 | Phase 3 | Pending |
| IMB-09 | Phase 3 | Pending |
| DELT-01 | Phase 3 | Pending |
| DELT-02 | Phase 3 | Pending |
| DELT-03 | Phase 3 | Pending |
| DELT-04 | Phase 3 | Pending |
| DELT-05 | Phase 3 | Pending |
| DELT-06 | Phase 3 | Pending |
| DELT-07 | Phase 3 | Pending |
| DELT-08 | Phase 3 | Pending |
| DELT-09 | Phase 3 | Pending |
| DELT-10 | Phase 3 | Pending |
| DELT-11 | Phase 3 | Pending |
| AUCT-01 | Phase 3 | Pending |
| AUCT-02 | Phase 3 | Pending |
| AUCT-03 | Phase 3 | Pending |
| AUCT-04 | Phase 3 | Pending |
| AUCT-05 | Phase 3 | Pending |
| ENG-01 | Phase 3 | Pending |
| ENG-08 | Phase 3 | Pending |
| ENG-09 | Phase 3 | Pending |
| TRAP-01 | Phase 4 | Pending |
| TRAP-02 | Phase 4 | Pending |
| TRAP-03 | Phase 4 | Pending |
| TRAP-04 | Phase 4 | Pending |
| TRAP-05 | Phase 4 | Pending |
| VOLP-01 | Phase 4 | Pending |
| VOLP-02 | Phase 4 | Pending |
| VOLP-03 | Phase 4 | Pending |
| VOLP-04 | Phase 4 | Pending |
| VOLP-05 | Phase 4 | Pending |
| VOLP-06 | Phase 4 | Pending |
| ENG-02 | Phase 4 | Pending |
| ENG-03 | Phase 4 | Pending |
| ENG-04 | Phase 4 | Pending |
| ENG-05 | Phase 4 | Pending |
| POC-01 | Phase 5 | Pending |
| POC-02 | Phase 5 | Pending |
| POC-03 | Phase 5 | Pending |
| POC-04 | Phase 5 | Pending |
| POC-05 | Phase 5 | Pending |
| POC-06 | Phase 5 | Pending |
| POC-07 | Phase 5 | Pending |
| POC-08 | Phase 5 | Pending |
| VPRO-01 | Phase 5 | Pending |
| VPRO-02 | Phase 5 | Pending |
| VPRO-03 | Phase 5 | Pending |
| VPRO-04 | Phase 5 | Pending |
| VPRO-05 | Phase 5 | Pending |
| VPRO-06 | Phase 5 | Pending |
| VPRO-07 | Phase 5 | Pending |
| VPRO-08 | Phase 5 | Pending |
| GEX-01 | Phase 5 | Pending |
| GEX-02 | Phase 5 | Pending |
| GEX-03 | Phase 5 | Pending |
| GEX-04 | Phase 5 | Pending |
| GEX-05 | Phase 5 | Pending |
| GEX-06 | Phase 5 | Pending |
| ZONE-01 | Phase 5 | Pending |
| ZONE-02 | Phase 5 | Pending |
| ZONE-03 | Phase 5 | Pending |
| ZONE-04 | Phase 5 | Pending |
| ZONE-05 | Phase 5 | Pending |
| ENG-06 | Phase 5 | Pending |
| ENG-07 | Phase 5 | Pending |
| KRON-01 | Phase 6 | Pending |
| KRON-02 | Phase 6 | Pending |
| KRON-03 | Phase 6 | Pending |
| KRON-04 | Phase 6 | Pending |
| KRON-05 | Phase 6 | Pending |
| KRON-06 | Phase 6 | Pending |
| TVMCP-01 | Phase 6 | Pending |
| TVMCP-02 | Phase 6 | Pending |
| TVMCP-03 | Phase 6 | Pending |
| TVMCP-04 | Phase 6 | Pending |
| TVMCP-05 | Phase 6 | Pending |
| TVMCP-06 | Phase 6 | Pending |
| ENG-10 | Phase 6 | Pending |
| SCOR-01 | Phase 7 | Pending |
| SCOR-02 | Phase 7 | Pending |
| SCOR-03 | Phase 7 | Pending |
| SCOR-04 | Phase 7 | Pending |
| SCOR-05 | Phase 7 | Pending |
| SCOR-06 | Phase 7 | Pending |
| TEST-01 | Phase 7 | Pending |
| TEST-02 | Phase 7 | Pending |
| TEST-03 | Phase 7 | Pending |
| TEST-04 | Phase 7 | Pending |
| TEST-05 | Phase 7 | Pending |
| TEST-06 | Phase 7 | Pending |
| TEST-07 | Phase 7 | Pending |
| EXEC-01 | Phase 8 | Pending |
| EXEC-02 | Phase 8 | Pending |
| EXEC-03 | Phase 8 | Pending |
| EXEC-04 | Phase 8 | Pending |
| EXEC-05 | Phase 8 | Pending |
| EXEC-06 | Phase 8 | Pending |
| EXEC-07 | Phase 8 | Pending |
| EXEC-08 | Phase 8 | Pending |
| ML-01 | Phase 9 | Pending |
| ML-02 | Phase 9 | Pending |
| ML-03 | Phase 9 | Pending |
| ML-04 | Phase 9 | Pending |
| ML-05 | Phase 9 | Pending |
| ML-06 | Phase 9 | Pending |
| ML-07 | Phase 9 | Pending |
| ML-08 | Phase 9 | Pending |
| DASH-01 | Phase 10 | Pending |
| DASH-02 | Phase 10 | Pending |
| DASH-03 | Phase 10 | Pending |
| DASH-04 | Phase 10 | Pending |
| DASH-05 | Phase 10 | Pending |
| DASH-06 | Phase 10 | Pending |
| DASH-07 | Phase 10 | Pending |

| APP-01 | Phase 11 | Complete |
| APP-02 | Phase 11 | Pending |
| APP-03 | Phase 11 | Complete |
| APP-04 | Phase 11 | Complete |
| APP-05 | Phase 11 | Pending |
| APP-06 | Phase 11 | Complete |
| APP-07 | Phase 11 | Pending |
| APP-08 | Phase 11 | Complete |

**Coverage:**
- v1 requirements: 159 total (22 categories)
- Mapped to phases: 159
- Unmapped: 0

---
*Requirements defined: 2026-04-13*
*Last updated: 2026-04-11 — traceability populated by roadmapper*
