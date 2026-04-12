# Requirements: DEEP6 v2.0

**Defined:** 2026-04-12
**Core Value:** Detect absorption and exhaustion with the highest accuracy of any footprint system ever built, and auto-execute trades from those signals via NT8 ATM Strategy.

## v1 Requirements

### Architecture (ARCH)

- [ ] **ARCH-01**: Monolithic DEEP6.cs decomposed into partial classes via AddOns pattern (~15 files, zero behavior change)
- [ ] **ARCH-02**: GC hot-path fixes applied (Std() pre-allocation, brush caching, RemoveAll() replaced with index-based removal) before any signal expansion
- [ ] **ARCH-03**: ATR(20) normalization layer provides volatility-adaptive thresholds for all 44 signals
- [ ] **ARCH-04**: Pairwise signal correlation matrix computed to identify and document redundant signals before implementation
- [ ] **ARCH-05**: SignalFlags bitmask (ulong) covers all 44 signals for O(popcount) scoring regardless of signal count

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
- [ ] **IMB-08**: Diagonal imbalance detected (cross-tick ask[n+1] vs bid[n] comparison per FutTrader methodology)
- [ ] **IMB-09**: Reversal imbalance pattern detected (imbalance direction change within bar sequence)

### Delta (DELT)

- [ ] **DELT-01**: Delta rise/drop classified per bar
- [ ] **DELT-02**: Delta tail detected — bar delta closes at 95%+ of its extreme value
- [ ] **DELT-03**: Delta reversal detected — intrabar delta flip from one extreme to opposite
- [ ] **DELT-04**: Delta divergence detected — price making new high/low while delta fails to confirm (highest alpha delta signal)
- [ ] **DELT-05**: Delta flip detected — sign change in cumulative delta
- [ ] **DELT-06**: Delta trap detected — aggressive delta in one direction followed by price reversal
- [ ] **DELT-07**: Delta sweep detected — rapid delta accumulation across multiple price levels
- [ ] **DELT-08**: Delta slingshot detected — compressed delta followed by explosive expansion (72-78% win rate)
- [ ] **DELT-09**: Delta at min/max classified relative to session range
- [ ] **DELT-10**: CVD multi-bar divergence detected via linear regression over 5-20 bar window
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
- [ ] **POC-02**: Extreme POC detected — POC at bar high or low (P/B reversal profile per JumpstartTrading)
- [ ] **POC-03**: Continuous POC detected — same POC price defended across 3+ bars (strong acceptance)
- [ ] **POC-04**: POC gap detected — current bar POC more than N ticks from prior bar POC
- [ ] **POC-05**: POC delta computed — net delta specifically at the POC price level
- [ ] **POC-06**: Engulfing VA detected — current value area fully contains prior value area
- [ ] **POC-07**: VA gap detected — current value area has no overlap with prior value area
- [ ] **POC-08**: Bullish/bearish POC classified based on POC position relative to bar open/close

### Volume Profile Levels (VPRO)

- [ ] **VPRO-01**: Session volume profile computed with configurable bin resolution (tick-level precision)
- [ ] **VPRO-02**: LVN zones detected — bins with volume < 30% of session average, merged into zones
- [ ] **VPRO-03**: HVN zones detected — bins with volume > 170% of session average
- [ ] **VPRO-04**: LVN zone lifecycle managed — 5-state FSM (Created → Defended → Broken → Flipped → Invalidated)
- [ ] **VPRO-05**: Zone scoring formula applied — type(0.35) + recency(0.25) + touches(0.25) + defense(0.15)
- [ ] **VPRO-06**: LVN reactivity validated — zones tested against historical price action for bounce/acceleration rate
- [ ] **VPRO-07**: Multi-session LVN persistence — developing profile carries forward with decay weighting
- [ ] **VPRO-08**: POC migration tracking — session POC movement direction and velocity computed per bar

### GEX Integration (GEX)

- [ ] **GEX-01**: GEX data ingested from commercial API (evaluate FlashAlpha vs Massive.com vs custom calculation)
- [ ] **GEX-02**: Call wall, put wall, gamma flip level, and HVL displayed as price levels on chart
- [ ] **GEX-03**: GEX regime classified — positive gamma (mean-reverting) vs negative gamma (amplifying)
- [ ] **GEX-04**: GEX regime modifies signal weighting — below gamma flip prefers trend signals, above prefers fade signals
- [ ] **GEX-05**: GEX-signal confluence scored — absorption at call/put wall receives conviction bonus
- [ ] **GEX-06**: GEX data staleness handled — commercial API updates every 1-15 min; stale flag when data age > threshold

### Existing Engine Enhancement (ENG)

- [ ] **ENG-01**: E2 Trespass engine enhanced — multi-level weighted DOM queue imbalance upgraded with volatility-adaptive thresholds and improved logistic regression calibration
- [ ] **ENG-02**: E3 CounterSpoof engine enhanced — Wasserstein-1 distribution monitor upgraded with adaptive thresholds and improved large-order cancel detection sensitivity
- [ ] **ENG-03**: E4 Iceberg engine enhanced — native + synthetic iceberg detection upgraded with refined refill timing windows and volume threshold scaling
- [ ] **ENG-04**: E5 Micro probability engine enhanced — Naïve Bayes combination upgraded to account for signal correlation (decorrelated inputs) and expanded feature set from new signals
- [ ] **ENG-05**: E6 VP+CTX engine enhanced — DEX-ARRAY upgraded with LVN zone lifecycle integration and enhanced VWAP/IB/GEX context
- [ ] **ENG-06**: E7 ML Quality engine enhanced — Kalman filter upgraded with expanded 8-feature → 16+ feature logistic classifier incorporating new signal categories
- [ ] **ENG-07**: E8 CVD engine created — cumulative volume delta with multi-bar divergence detection via linear regression
- [ ] **ENG-08**: E9 Auction State Machine created — finite state machine tracking auction theory states across bars

### Zone Registry (ZONE)

- [ ] **ZONE-01**: Centralized ZoneRegistry manages all zone types (absorption zones, exhaustion zones, LVN, HVN, GEX levels)
- [ ] **ZONE-02**: Zone-signal interaction scored — absorption at LVN + GEX confluence = highest conviction
- [ ] **ZONE-03**: Zone merge logic — overlapping same-direction zones consolidate with combined score
- [ ] **ZONE-04**: Zone visual tiering — strong/medium/weak zones rendered with distinct opacity and border styles via SharpDX
- [ ] **ZONE-05**: Peak bucket cluster — zones narrowed to volume concentration peak (from Pine Script reference)

### Scoring & Confluence (SCOR)

- [ ] **SCOR-01**: Two-layer consensus — engine-level agreement ratio + category-level confluence multiplier
- [ ] **SCOR-02**: Category-level confluence — 8 signal categories each vote; 5+ agreement triggers 1.25× multiplier
- [ ] **SCOR-03**: Zone bonus scoring — zones scoring ≥50 add +6 to +8 points to confluence score
- [ ] **SCOR-04**: TypeA/B/C signal classification updated — TypeA requires absorption/exhaustion + zone confluence + 5+ category agreement
- [ ] **SCOR-05**: Volatility-adaptive scoring — all thresholds scale with ATR(20) so system works in both slow and fast markets
- [ ] **SCOR-06**: Signal narrative labels — human-readable text on chart (ABSORBED, EXHAUSTED, MOMENTUM, etc. with context like "@VAH" or "DON'T CHASE")

### Auto-Execution (EXEC)

- [ ] **EXEC-01**: NT8 ATM Strategy integration — automated entry orders from TypeA/B confluence signals
- [ ] **EXEC-02**: Risk management — circuit breakers (max daily loss), position sizing (max contracts), consecutive loss limits
- [ ] **EXEC-03**: Entry timing — configurable delay after signal to confirm (avoid false triggers)
- [ ] **EXEC-04**: Stop placement — stops placed beyond absorption/exhaustion zone boundary
- [ ] **EXEC-05**: Target placement — targets at opposing zone, VWAP, or next LVN/HVN level
- [ ] **EXEC-06**: Regime-aware execution — auto-execution disabled in specific GEX regimes or low-volume conditions

### Backtesting (TEST)

- [ ] **TEST-01**: NT8 Strategy Analyzer configured for tick replay backtesting of E1/E5/E6/E7 signals
- [ ] **TEST-02**: Market Replay Recorder enabled for DOM data accumulation (E2/E3/E4 future backtesting)
- [ ] **TEST-03**: Signal CSV export from NT8 for Python analysis (timestamp, signal type, score, price, outcome)
- [ ] **TEST-04**: Python vectorbt parameter sweep framework for threshold optimization
- [ ] **TEST-05**: Walk-forward validation pipeline with WFE > 70% gate before any ML weights go live
- [ ] **TEST-06**: P&L attribution per signal type — which signals contribute to edge vs add noise

### Data Bridge (BRDG)

- [ ] **BRDG-01**: TCP socket bridge from NT8 to Python backend via System.Net.Sockets.TcpClient (native .NET 4.8)
- [ ] **BRDG-02**: ConcurrentQueue + background thread pattern keeps NT8 bar thread non-blocking
- [ ] **BRDG-03**: Signal event stream — every signal firing sent to Python with full context (type, score, price, zone, regime)
- [ ] **BRDG-04**: Trade event stream — every ATM entry/exit sent to Python for ML training
- [ ] **BRDG-05**: ML weight pull — NT8 reads Python-generated JSON config at session start (session-invariant weights)

### ML Backend (ML)

- [ ] **ML-01**: FastAPI service receives signal + trade events from NT8 via TCP bridge
- [ ] **ML-02**: XGBoost model trained on signal history to optimize signal weighting
- [ ] **ML-03**: Optuna Bayesian hyperparameter optimization for all 44 signal thresholds
- [ ] **ML-04**: Regime detection classifier — identifies market regime (trending, ranging, volatile, quiet) from signal patterns
- [ ] **ML-05**: Walk-forward cross-validation with purged splits (no future leakage)
- [ ] **ML-06**: Weight file generation — JSON config with per-signal weights, per-regime adjustments, updated per session
- [ ] **ML-07**: Model performance tracking — win rate, profit factor, Sharpe per signal type per regime

### Analytics Dashboard (DASH)

- [ ] **DASH-01**: Next.js 15 App Router dashboard with SSE for real-time updates from Python backend
- [ ] **DASH-02**: Signal performance view — win rate, avg P&L, frequency per signal type with time filters
- [ ] **DASH-03**: Regime visualization — current and historical regime classification with overlay on price chart
- [ ] **DASH-04**: Parameter evolution view — how ML is adjusting thresholds over time, with before/after comparison
- [ ] **DASH-05**: Zone analysis — which zone types produce best outcomes, zone lifecycle statistics
- [ ] **DASH-06**: TradingView Lightweight Charts integration for OHLC display with signal overlay
- [ ] **DASH-07**: Session replay — review any trading session with all signals and zones reconstructed

## v2 Requirements

### Multi-Instrument

- **MULTI-01**: ES (S&P 500) futures support with recalibrated thresholds
- **MULTI-02**: YM, RTY, CL, GC futures support
- **MULTI-03**: Per-instrument ML models with independent weight files

### Advanced ML

- **AML-01**: Deep learning models (LSTM/Transformer) for sequence prediction
- **AML-02**: Reinforcement learning for dynamic position sizing
- **AML-03**: Cross-instrument signal correlation for macro regime detection

### Full Web Platform

- **WEB-01**: Web-based charting replacing NT8 dependency
- **WEB-02**: Direct broker API integration (Rithmic/CQG)
- **WEB-03**: Mobile-responsive dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| TradingView Pine Script maintenance | Reference architecture only — one codebase to maintain |
| Direct Rithmic API execution | Using NT8 ATM Strategy — proven, lower risk |
| Social/community features | Single-user institutional tool |
| Mobile app | Desktop + web dashboard sufficient for v1 |
| Options trading execution | Futures only — options data for GEX context, not execution |
| HFT/co-location | Sub-second execution not required — signal-based entries |
| Custom GEX calculator from raw OPRA data | Evaluate commercial APIs first; build only if needed |

## Traceability

Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (populated by roadmapper) | | |

**Coverage:**
- v1 requirements: 97 total
- Mapped to phases: 0
- Unmapped: 97

---
*Requirements defined: 2026-04-12*
*Last updated: 2026-04-12 after initial definition*
