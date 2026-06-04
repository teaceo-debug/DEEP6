# GEX Doctor v2.0 — Accuracy Mega-Upgrade

## TL;DR

> **Quick Summary**: Wire ALL unused analytical capabilities into GEX Doctor to transform it from a regime classifier into an institutional-grade NQ trading system. 9 upgrade tracks executed in maximum parallel. Replace Kronos with Claude-in-the-loop learning model that improves daily.
>
> **Estimated Effort**: Large (multi-day, barrage execution)
> **Parallel Execution**: YES — 9 tracks, max agents

---

## Context

### What Oracle Said Matters Most
1. Dynamic QQQ→NQ proxy (fixes systematic level errors)
2. Flow engine integration (GEX = map, flow = whether money is pushing)
3. VEX/CHEX + 0DTE mechanics (drives EOD behavior)
4. HMM regime detector (absorb/trend/chaotic vs simple pos/neg)
5. Conviction matrix (multi-source agreement scoring)
6. PO3 daily bias anchor
7. Gamma Decision Surface V2
8. Confluence rules (38 rules, spoof detection, false breakout filter)
9. Claude learning model (replaces Kronos — learns daily, saves to memory)

### What User Added
- Unusual Whales API key: configured
- No Kronos — Claude IS the directional model, learning daily
- Build skills every day, save learnings to memory
- NT8 indicator needs to show levels for tomorrow's session

---

## TODOs

- [x] 1. Dynamic QQQ→NQ Proxy Fix

  **What to do**:
  - In `gex_terminal/engine/analyzer.py`: replace `DEFAULT_NQ_QQQ_RATIO = 38.5` with dynamic computation
  - Get live NQ spot from Massive adapter (already fetches NQ quote)
  - Get live QQQ spot from FlashAlpha adapter (already in response)
  - Compute ratio: `nq_spot / qqq_spot` on every cycle
  - Add NDX cross-check: if QQQ-derived levels diverge >200pts from NDX-derived, reduce confidence
  - Add basis monitor: if NQ/QQQ ratio deviates >5% from trailing average, flag PROXY DIVERGENCE

  **Category**: `quick`
  **Skills**: []

- [x] 2. Flow Engine Integration

  **What to do**:
  - Wire `nq_atlas/flow.py` FlowEngine into gex_terminal orchestrator
  - Pass flow results (direction, z_score, intensity) to analyzer
  - In analyzer: add flow-regime interaction scoring:
    - Positive GEX + bullish flow → +10 confidence
    - Positive GEX + bearish flow → -15 confidence (flow contradicts structure)
    - Negative GEX + bearish flow → +10 confidence
    - Negative GEX + bullish flow → -15 confidence
  - Add flow z_score to confidence: |z| > 2.0 → +5pts, |z| < 0.5 → -5pts
  - Add flow direction to GEXTerminalSnapshot and UI display

  **Category**: `deep`
  **Skills**: [`options-bias-engine/step3-flow/flow-interpretation`]

- [x] 3. VEX/CHEX + 0DTE Mechanics

  **What to do**:
  - Wire `nq_atlas/vanna_charm.py` VannaCharmEngine into orchestrator
  - Cross-validate FlashAlpha VEX/CHEX with Massive-computed vanna/charm
  - Add to analyzer:
    - VEX/CHEX alignment bonus: both point same direction → +5 confidence
    - VEX/CHEX divergence: opposite directions → -5 confidence
    - 0DTE gamma as % of total: >50% → pin risk flag, reduce directional confidence
    - Near-expiry charm drift: last hour + 0DTE → add charm direction to bias
  - Add 0DTE pin risk to UI display
  - Factor by_expiry buckets (0DTE vs 7-30 vs 30+) into regime classification

  **Category**: `deep`
  **Skills**: [`options-bias-engine/domains/dex-vex-chex`, `options-bias-engine/domains/zero-dte-mechanics`]

- [x] 4. HMM Regime Detector Integration

  **What to do**:
  - Import `deep6/ml/hmm_regime.py` HMMRegimeDetector
  - Feed it: ATR ratio, spread, trade rate, delta, range-to-ATR (5 features)
  - Use as tradability gate:
    - ABSORPTION_FRIENDLY → full confidence, GEX walls are sticky
    - TRENDING → reduce GEX wall confidence -15%, momentum signals weighted up
    - CHAOTIC → reduce ALL confidence -25%, add "LOW CONVICTION" warning
  - Add regime state to GEXTerminalSnapshot and UI display
  - Retrain nightly via ThreadPoolExecutor (existing pattern)

  **Category**: `deep`
  **Skills**: [`options-bias-engine/step1-regimes/regime-identification`]

- [x] 5. Conviction Matrix (Multi-Source Agreement)

  **What to do**:
  - Implement 5-river conviction scoring from options-bias-engine:
    - River 1: GEX regime + level structure
    - River 2: Flow direction + intensity
    - River 3: Vanna/charm alignment
    - River 4: Dark pool (UW) institutional bias
    - River 5: Claude AI interpretation confidence
  - Score: 5/5 agree = A+ (max conviction), 4/5 = A, 3/5 = B, 2/5 = C (no trade), <2 = F
  - Override the simple confidence % with conviction-weighted confidence
  - Add conviction grade to UI display
  - When <3 rivers agree → show "LOW CONVICTION — STAND ASIDE" in narrative

  **Category**: `deep`
  **Skills**: [`options-bias-engine/step4-cross-validation/conviction-matrix`]

- [x] 6. PO3 Daily Bias Anchor

  **What to do**:
  - Import `deep6/bias_engine/po3_detector.py` PO3Detector
  - Feed daily OHLC + previous day close
  - Get: Midnight Open anchor, Judas Swing detection, Premium/Discount zone, AMD phase
  - Add to analyzer:
    - PO3 bullish + GEX bullish → strong confirmation (+10 confidence)
    - PO3 bearish + GEX bullish → conflict, reduce confidence -10
    - PO3 phase = DISTRIBUTION → reduce long bias confidence
  - Add PO3 state to UI: "PO3: BULL │ Phase: MANIPULATION │ MO: 21,420"
  - Requires daily OHLC — can get from Massive/Polygon or Rithmic

  **Category**: `deep`
  **Skills**: [`options-bias-engine/step1-regimes/regime-identification`]

- [x] 7. Magnet Scorer + Anti-Flicker

  **What to do**:
  - Import `gexdoctor/monitor/magnet_scorer.py` MagnetScorer
  - Replace simple level selection with scored magnet system:
    - Level type weights: pin_magnet=1.0, gamma_flip=0.9, walls=0.85, max_pain=0.4-0.8
    - Anti-flicker: new candidate must exceed current by 0.12 margin
    - Freshness decay: levels older than 300s lose priority
  - Add primary magnet level to GEXTerminalSnapshot
  - Draw magnet level prominently in NT8 indicator (thicker line, ⚡ label)
  - Add magnet to terminal UI display

  **Category**: `unspecified-high`
  **Skills**: []

- [x] 8. GEX Model Validation (VIX/IV Controls)

  **What to do**:
  - Add VIX regime modifier to confidence scoring:
    - VIX < 15: GEX walls high confidence (+5), pin/mean-revert base case
    - VIX 15-25: neutral, no modifier
    - VIX > 25: GEX walls low confidence (-10), trend/breakout weighted up
    - VIX > 35: EXTREME — reduce all GEX confidence -20%, add kill switch warning
  - Get VIX from Massive/Polygon (already available)
  - Add VIX level to terminal UI footer
  - Add academic honest assessment: GEX predicts vol regime (r=-0.36), NOT direction after controlling for VIX

  **Category**: `quick`
  **Skills**: [`nq-options-algo-engine/deep-expertise/gex-model-validation`]

- [ ] 9. Claude Learning Model (Daily Memory + Skill Building)

  **What to do**:
  - Replace Kronos with Claude-in-the-loop learning system
  - After each session:
    - Save the day's GEX state, bias calls, and actual NQ outcome to memory
    - Claude analyzes: "What worked? What didn't? What regime was this?"
    - Save learnings to `.sisyphus/notepads/gex-doctor-learnings/` as dated entries
    - Build a running "bias playbook" that accumulates daily
  - Before each session:
    - Load last 5 days of learnings from memory
    - Feed to Claude as context: "Here's what we've learned recently..."
    - Claude adjusts confidence based on recent regime performance
  - Use `mcp_Agentmemory_memory_save` to persist key insights
  - Use `mcp_Agentmemory_memory_recall` to retrieve relevant past patterns
  - Create skill file: `.claude/skills/gex-doctor-learnings/knowledge.md`
  - Goal: system gets smarter every day, not just static rules

  **Category**: `deep`
  **Skills**: [`options-bias-engine/knowledge`, `nq-options-algo-engine/knowledge`]

- [x] 10. Unusual Whales Dark Pool + NT8 Fixes

  **What to do**:
  - Verify UW adapter now has API key and fetches real data
  - Wire UW dark pool levels into conviction matrix (River 4)
  - Wire UW institutional bias into confidence scoring
  - Fix NT8 indicator if needed:
    - Verify GEXTerminal.cs reads gex_terminal_nt8.json correctly
    - Verify levels render on NQ chart
    - Add GEXTerminal to user's default NQ chart template
  - Verify bridge is running and JSON is updating every 10s
  - Test: kill and restart backend → bridge auto-recovers

  **Category**: `unspecified-high`
  **Skills**: [`unusual-whales/dark-pool`, `nt8-expert`]

---

## Execution Strategy

All 10 tracks can start in parallel. Dependencies:
- T1 (dynamic ratio) unblocks T2, T3 (they need accurate levels)
- T5 (conviction matrix) needs T2, T3, T4 (needs all rivers)
- T9 (learning model) needs T5 (needs conviction scoring to evaluate)
- T10 (UW + NT8) is independent

### Wave 1 (start immediately, all parallel):
T1 (ratio fix), T4 (HMM), T7 (magnet scorer), T8 (VIX controls), T10 (UW + NT8)

### Wave 2 (after T1):
T2 (flow engine), T3 (VEX/CHEX), T6 (PO3)

### Wave 3 (after T2, T3, T4):
T5 (conviction matrix)

### Wave 4 (after T5):
T9 (Claude learning model)

---

## Success Criteria

- [ ] Dynamic NQ/QQQ ratio computed from live prices on every cycle
- [ ] Flow z-score factors into confidence scoring
- [ ] VEX/CHEX alignment bonus/penalty in confidence
- [ ] HMM regime gates tradability (CHAOTIC = suppress signals)
- [ ] 5-river conviction matrix produces grade (A+/A/B/C/F)
- [ ] PO3 daily bias anchors directional call
- [ ] Magnet scorer with anti-flicker replaces simple level selection
- [ ] VIX modifier adjusts GEX confidence by vol regime
- [ ] Claude learning model saves daily learnings and loads recent context
- [ ] UW dark pool levels factor into conviction
- [ ] NT8 indicator shows levels on NQ chart for tomorrow's session
- [ ] All 75+ existing Python tests still pass
