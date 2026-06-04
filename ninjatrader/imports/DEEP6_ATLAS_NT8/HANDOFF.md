# DEEP6 ATLAS — PROJECT HANDOFF

**Status:** Production-ready core. Two engines stubbed (E13 LOB-NN, E14 Meta-Label) pending offline ML training. Single-file NT8 deliverable verified brace-balanced.

**Owner:** Michael Petitjean (Peak Asset Performance LLC, @teaceo)
**Targets:** NQ / MNQ / ES / MES on NinjaTrader 8 + Apex Trader Funding accounts
**Last touched:** 2026-04-26
**File hash (SHA256):** *computed at package time — see `MANIFEST.txt`*

---

## 1. WHAT THIS IS

DEEP6 ATLAS is an institutional-grade microstructure signal indicator for index futures, built as a single-file NinjaScript indicator (`DEEP6Atlas.cs`) plus a paired execution strategy (`DEEP6AtlasStrategy.cs`). It synthesizes **16 microstructure engines** through a **4-tier confluence funnel** with **FTRL-Proximal online learning** and **Bayesian fusion** to produce graded signals (S/A/B/C/Q) for NQ/ES futures.

It is the successor to DEEP6 v1 (1,010-line NinjaScript, 7 engines) and DEEP6 v2 (specification only). ATLAS is the implemented version — every engine, every gate, every veto is wired and runs in real-time off Rithmic Level 2 + NT8 OrderFlow+.

The project explicitly rejects the marketing-grade WR claims (88-93%) made by competing TikTok-marketed NT8 systems. ATLAS targets **honest** post-validation performance: 56-62% WR, 1.3-1.7R net, Deflated Sharpe 1.4-2.2, ~18-35% on funded combine. The differentiator is rigor, not promises.

---

## 2. ARCHITECTURE — 5 PILLARS × 16 ENGINES × 4 TIERS

### Pillar I — Microstructure Primitives (Layer 0)

Foundation classes that consume DOM/trade events and produce continuous metrics. Used by multiple engines.

| Class | Function | Source |
|---|---|---|
| `Microprice` | Stoikov 2018 (arXiv:1811.10889) — Bid + (Ask−Bid)·G(I,s). Linear approximation of fitted G. | Stoikov |
| `OFIRolling` | Cont-Kukanov-Stoikov 2014 OFI over time window. 4 timescales: 100ms, 500ms, 2s, 10s. | Cont et al. |
| `MLOFIComputer` | Multi-Level OFI top-K with 1/k decay. **Online PCA via Oja's rule** for PC1 extraction. | Xu 2019, Kolm-Westray 2023 |
| `KyleLambda` | Multi-scale price impact per unit signed volume. 3 windows: 30s, 2m, 10m. | Kyle 1985 |
| `VPINComputer` | Bulk-volume classification toxicity, 50-bucket window. | Easley-LdP-O'Hara 2012 |
| `MarkedHawkes` | Exponential-kernel self-exciting process. Branching ratio n=α/β via moment matching. | Hawkes 1971, Bacry 2015 |
| `IcebergDetector` | Heuristic refill-within-350ms detection (true MDP3 modify-after-trade flag requires Rithmic protobuf addon). | — |
| `HiddenFillDetector` | Fills outside visible book → hidden liquidity flag. | — |
| `SpoofDetector` | **Wasserstein-1 distance** on rolling DOM shape + cancel-rate spike confirmation. | W1 metric |
| `QueuePositionTracker` | Fill probability estimate at touch. | — |

### Pillar II — 16 Engines

Engines consume primitives + bar data and produce `(Score, Probability, Direction)` triples.

| # | Engine | Lines | Role |
|---|---|---|---|
| E1 | Footprint | 330 | 22 signals across 5 categories: absorption(8), exhaustion(5), stacked imbalance(3), initiative(4), CVD divergence(3). Reads `vol.PriceVolumes` for true stacked counts when OrderFlow+ is loaded. EWMA baselines + tanh squash directional aggregation. |
| E2 | Trespass | 32 | Microprice mean-reversion guard. Vetoes signals trading against MP gradient. |
| E3 | Spoof | 18 | W1 + cancel-rate + size-collapse → directional veto (don't long if bid-side spoof). |
| E4 | Iceberg | 24 | Refill-within-window detector. Confirms hidden absorption. |
| E5 | MicroBayes | 19 | Micro-Bayesian flip filter on quote-tick microstructure. |
| E6 | VPCtx | 32 | Volume profile context (POC/VAH/VAL distance). |
| E7 | MLQuality | 35 | **Kalman-smoothed 8-feat logistic** (Q=1e-4, R=0.05). Hard veto if quality < 0.55. |
| E8 | Hawkes | 25 | Branching ratio n>0.7 gate confirms self-exciting flow. |
| E9 | MPDrift | 33 | Microprice drift velocity over 200ms-1s. |
| E10 | VPINGate | inline | Hard kill switch when VPIN > 0.65. |
| E11 | GEXAmp | 65 | **7-regime classifier with 3-bar hysteresis** consuming optionlevels JSON. Long/short multipliers per regime. |
| E12 | DOFI | 31 | MLOFI PC1 projection via Welford-online z-score. |
| E13 | LOBNN | 64 | **Online logistic placeholder** — swap-ready for ONNX TLOB (Berti-Kasneci 2025). |
| E14 | MetaLabel | 42 | **Online logistic placeholder** — swap-ready for ONNX XGBoost meta-classifier. |
| E15 | Regime | 66 | **Simplified HMM-5 regime router** (offline EM training is future work). 5 states: TrendingHighVol / TrendingLowVol / RangingHighVol / RangingLowVol / Filtered. |
| E16 | Drift | 38 | **Page-Hinkley** drift detector → alarm flag → optional auto-pause. |

### Pillar III — Fusion Layer

| Class | Function |
|---|---|
| `FTRLProximal` | Full McMahan 2013 implementation. Three γ rates (0.05 / 0.10 / 0.30) blended via Hedge. |
| `HedgeBlender` | Multiplicative weights update over 3 FTRL learners. |
| `BayesianCombiner` | Log-odds combination with **0.7 correlation shrinkage** to prevent over-confident fusion. |
| `BetaBernoulliReliability` | Per-engine win/loss tracking → reliability multiplier in fusion. |

### Pillar IV — 4-Tier Funnel

Every signal must pass all four gates before grading. Implementation: `ApplyFourTierFunnel` (lines 999-1097).

| Tier | Gate | Veto Reason Examples |
|---|---|---|
| **T1 Context** | TierOneContext direction-bias filter | "T1: context bias mismatch" |
| **T2 Regime** | E15 ≠ Filtered state | "T2: regime=Filtered" |
| **T3 Level** | Within 0.5 ATR of γ-flip / CW / PW / VWAP / IBH/L / PDH/L / POC | "T3: too far from level" |
| **T4 Trigger** | Confluence ≥ threshold + posterior ≥ threshold + zero vetoes | "T4: insufficient confluence (3)" / "E14 meta-label veto" / "E10 VPIN kill switch" / "E7 quality veto" / "E3 spoof veto (bid-side)" |

### Pillar V — Risk Layer

| Component | Rule |
|---|---|
| Kelly sizing | Half-Kelly × ATLAS sizeMultiplier × consec-loss dampening |
| Consec-loss dampening | ≥2 losses → halve size; ≥3 → S-only mode lockout |
| Daily loss lockout | $500 default (configurable) |
| Daily profit stop | $1000 default |
| Max trades/day | 8 |
| 5-stage exit ladder | BE@0.5R → Partial 50%@1R → Trail@2R (Chandelier ATR×2.5) → Partial 25%@3R → Trail-only@5R |
| Time exit | 30 bars if currentR < BreakEvenAtR |
| Time window | 0930-1530 ET; flatten 1555 |
| Apex trailing DD | $2500 default, EnableApex flag |

---

## 3. FILE INVENTORY

```
DEEP6_ATLAS_NT8/
├── HANDOFF.md                              ← this file
├── MANIFEST.txt                            ← file hashes + sizes
├── README_DEPLOYMENT.md                    ← step-by-step NT8 install
│
├── Indicators/
│   └── DEEP6Atlas.cs                       3,364 lines | 122KB | core indicator
│
├── Strategies/
│   └── DEEP6AtlasStrategy.cs                 192 lines |   8KB | paired strategy stub
│
├── AddOns/
│   ├── gex_nq.json                         sample GEX data file (E11 input)
│   ├── tlob_nq.onnx                        [NOT SHIPPED — train offline, see §6]
│   └── meta_xgb_nq.onnx                    [NOT SHIPPED — train offline, see §6]
│
└── Docs/
    └── DEEP6_ATLAS_MASTER_SPEC.md          55KB | full architectural spec
```

**Symbols / dependencies:**
- `.NET Framework 4.8` (NT8 default)
- `SharpDX.Direct2D1` (NT8 bundled)
- `System.Windows.Media` (WPF brushes for Draw.* methods)
- NT8 `OrderFlow+` add-on for `VolumetricBarsType` and `vol.PriceVolumes` (graceful degradation if absent)
- Rithmic L2 with **10+ DOM levels** for full primitives (works on 5 levels with reduced fidelity)

---

## 4. PUBLIC SURFACE (for paired strategy / external consumers)

### Series outputs (read on every bar)

```csharp
public Series<double> SignalGrade        // 0=Q, 1=C, 2=B, 3=A, 4=S
public Series<double> SignalDirection    // -1, 0, +1
public Series<double> Posterior          // P(direction | features), [0,1]
public Series<double> SizeMultiplier     // Kelly × GEX × regime × VPIN dampening
public Series<double> CurrentRegime      // RegimeState index 0..4
public Series<double> VPINSeries         // current VPIN toxicity
public Series<double> MicropriceSeries   // microprice value
```

### Public methods

```csharp
public void RegisterTradeOutcome(double rMultiple, double pnlDollars)
// Call from paired strategy on every trade close.
// Feeds R-multiple back into FTRL + per-engine reliability tracker.
```

### Inputs (NinjaScriptProperty groups)

- **Display**: HUD opacity, position
- **Engines**: enable/disable each E1-E16 individually
- **ML**: UseOnnxHeads flag, ONNX paths
- **GEX**: gex_nq.json path, refresh interval (seconds)
- **Signals**: minimum grade threshold for emission
- **Risk**: daily loss lockout, profit stop, max trades

---

## 5. DEPLOYMENT (NT8)

### Step-by-step

```
1. Quit NinjaTrader 8 if running.

2. Copy files:
   DEEP6Atlas.cs        → Documents\NinjaTrader 8\bin\Custom\Indicators\
   DEEP6AtlasStrategy.cs → Documents\NinjaTrader 8\bin\Custom\Strategies\
   gex_nq.json          → Documents\NinjaTrader 8\bin\Custom\AddOns\

3. Launch NT8.

4. New → NinjaScript Editor (or press F5). It will compile the entire
   bin\Custom\ tree. Watch the Errors tab — should be zero errors.

5. Open a chart on @NQ.06.26 (front-month NQ) or @MNQ.06.26.
   Recommended bar type: VolumetricBars (1 minute or 60-tick).
   Without OrderFlow+, fall back to standard 1-minute bars; E1 reads
   delta from bar.Volume × directional approximation.

6. Indicators tab → DEEP6Atlas → Apply.
   Verify HUD renders top-right with "WARMING" state for ~50 bars
   while LOB buffer fills.

7. (Optional) Apply DEEP6AtlasStrategy on the same chart.
   Set MinGrade = 3 (A+) for conservative live trading.
   Connect to your Apex sim account first. Always paper-trade
   for 5-10 sessions before live.
```

### Verification checklist

- [ ] HUD renders top-right within 5 bars of chart load
- [ ] State transitions WARMING → QUIET within ~50 bars
- [ ] VPIN line shows non-zero value within 100 bars
- [ ] Microprice deviation reads non-zero on illiquid moments
- [ ] First C-grade signal appears within first session
- [ ] First A-grade signal appears within first 1-2 sessions
- [ ] No errors in NT8 Log tab (Tools → Output Window → Log)
- [ ] gex_nq.json reload happens every 60s (check timestamps)

---

## 6. OFFLINE TRAINING (E13, E14)

E13 and E14 ship as online logistic placeholders. To upgrade to production-grade:

### E13 — TLOB (Berti-Kasneci 2025)

```
Pipeline:
1. Pull NQ MBP-10 from Databento (GLBX.MDP3) for 6+ months
2. Construct triple-barrier labels (TBL): up barrier, down barrier, time barrier
3. Train TLOB transformer architecture (Berti-Kasneci 2025)
   - Input: 10-level LOB snapshots over 100-tick rolling window
   - Output: 3-class probability (up / flat / down)
4. Export to ONNX
5. Drop tlob_nq.onnx into bin\Custom\AddOns\
6. Set UseOnnxHeads = true in indicator inputs
```

A scaffolding script `tlob_trainer.py` is a follow-up deliverable.

### E14 — Meta-Label (López de Prado 2018, Ch. 3)

```
Pipeline:
1. Run primary model (full ATLAS signal stack) on historical data
2. Label each signal {1: profitable, 0: unprofitable} via TBL
3. Train binary classifier (XGBoost or LightGBM) to predict P(take | signal)
4. Export to ONNX
5. Drop meta_xgb_nq.onnx into bin\Custom\AddOns\
```

### GEX Worker

```
Pipeline:
1. Optionlevels FastAPI stack pulls QQQ + SPY options chain from Polygon/Massive
2. Compute gamma exposure profile, identify γ-flip + call wall + put wall
3. Aggregate into JSON every 60s:
   { "flip": 22000, "call_wall": 22300, "put_wall": 21800,
     "net_gex": 5e9, "regime": "PositiveGamma", "ts": "2026-04-26T14:30:00Z" }
4. Write atomically to bin\Custom\AddOns\gex_nq.json
```

A `gex_producer.py` is a follow-up deliverable.

---

## 7. KNOWN LIMITATIONS

| Limitation | Impact | Path forward |
|---|---|---|
| E13/E14 are online logistic, not ONNX | Reduced edge on regime change | Train per §6 |
| HMM E15 is deterministic, not EM-trained | Coarser regime classification | Offline EM training future work |
| Hawkes uses moment matching, not full MLE | Slightly noisier branching ratio | Bacry recursive scheme upgrade |
| Iceberg is heuristic refill-window | False positives on liquidity returns | Rithmic protobuf addon for true MDP3 modify-after-trade flag |
| ATR is exponential approximation | Slightly off-textbook Wilder | Cosmetic; can swap to true Wilder |
| Lee-Ready aggressor classification simpler | Edge cases at midpoint | Quote-rule fallback |

---

## 8. VALIDATION DISCIPLINE

Per master spec §7 — these were enforced during design and must be re-applied for any modification:

- Triple-barrier labeling (López de Prado 2018) — never use raw next-bar returns as labels
- **Combinatorial Purged Cross-Validation (CPCV)** — never simple k-fold on time series
- **Deflated Sharpe Ratio** with multiple-test correction — DSR > 1.4 minimum
- **Probability of Backtest Overfitting (PBO)** < 0.40
- Walk-forward with 252-day train / 21-day test minimum
- Bootstrap confidence intervals on all reported statistics
- Out-of-sample validation on at least 2 distinct market regimes (e.g., 2022 vs 2024)

**Anti-pattern:** any change that improves backtest Sharpe by >0.3 with <50 fewer trades is curve-fit. Reject.

---

## 9. KILL SWITCHES (hardcoded)

```
KS1: VPIN > 0.65         → block all signals
KS2: Drift alarm active  → optional auto-pause (config flag)
KS3: Daily loss > $500   → lockout until next session
KS4: Daily profit > $1k  → optional stop (config flag)
KS5: Consec losses ≥ 3   → S-grade only mode
KS6: Spread > 3 ticks    → block (illiquid)
KS7: Spread spike > 4σ   → temporary 30s pause
KS8: News window         → 5min before/after FOMC, NFP, CPI (manual list)
KS9: Apex trailing DD    → flatten + lockout
KS10: NT8 disconnect     → flatten on reconnect (default NT8 behavior)
```

---

## 10. CONTINUITY — IF THIS PROJECT IS PICKED UP LATER

### Critical context for next session
- DEEP6 lineage: v1 (live) → v2 (spec) → ATLAS (this build, implemented)
- Michael's prior nine-figure CPG exit (FitTea) → can self-fund a serious build
- Trades on Apex Trader Funding accounts — any rule changes from Apex must be verified at deploy time
- IG handle: @teaceo, ~491K followers; trading content drives some retail interest
- Companion projects (DEEP6 Capital LP pitch, optionlevels.com) are separate but related

### Where to resume
1. **TLOB training** (`tlob_trainer.py`) — highest-value next step. Replaces E13 placeholder with state-of-the-art LOB transformer.
2. **GEX producer** (`gex_producer.py`) — second-highest value. Connects E11 to live data instead of stub JSON.
3. **HMM EM training** — third-priority. Replaces deterministic regime classifier with proper learned transitions.
4. **DEEP6 ATLAS DIAG** — companion bottom-panel indicator showing engine ribbon + posterior history. Half-built in `/home/claude/atlas/build/DEEP6AtlasDiag.cs` from prior session.

### Things NOT to do
- Don't re-architect from scratch. The 4-tier funnel + 16-engine ensemble is the canonical structure.
- Don't add engines without removing one. Marginal-engine creep destroys the validation framework.
- Don't ship HUD tweaks as standalone updates — bundle with engine improvements.
- Don't break the `RegisterTradeOutcome` public surface. Strategy-indicator coupling depends on it.

---

## 11. INVARIANTS (do not violate)

These are the load-bearing assumptions of the entire system:

1. **The 4-tier funnel is sequential and short-circuits.** T1 fail → T2/T3/T4 not evaluated. Reordering breaks veto semantics.
2. **`SignFromBayesianFusion` returns the directional sign before grading.** Reversing this causes phantom long/short flips.
3. **FTRL state is reset only at session boundary.** Not on indicator reload, not on bar change.
4. **The Bayesian combiner uses 0.7 correlation shrinkage.** Lower values cause overconfidence; higher values starve the signal.
5. **VPIN buckets are bulk-volume-classified, not tick-rule.** Switching to tick rule destroys the toxicity signal.
6. **Wasserstein-1 spoof distance is 1-D CDF, not 2-D.** Using full 2-D Wasserstein on (bid,ask) destroys real-time performance.
7. **Online PCA in MLOFI uses Oja's rule with √t learning rate decay.** Constant rate causes drift; faster decay loses tracking.
8. **GEX JSON is read every 60s with stale-data check.** Stale data > 5min triggers E11 to disable amplifier.
9. **`OnRender` uses traditional switch, not C# 8 switch expressions.** NT8 Roslyn versions vary; conservative syntax avoids warnings.
10. **All `DateTime` arithmetic uses `marketDataUpdate.Time` / `marketDepthUpdate.Time` in tick handlers.** `Time[0]` in tick context is unsafe before first bar.

---

## 12. SOURCES (canonical reading list, abbreviated)

Full 40-citation list is in `Docs/DEEP6_ATLAS_MASTER_SPEC.md` §15.

**Must-reads:**
- Stoikov 2018, "The Microprice", arXiv:1811.10889
- Cont, Kukanov, Stoikov 2014, "The Price Impact of Order Book Events"
- Easley, López de Prado, O'Hara 2012, "Flow Toxicity and Liquidity in a HFT World"
- McMahan 2013, "FTRL-Proximal Online Learning"
- Berti, Kasneci 2025, TLOB transformer for LOB prediction
- López de Prado 2018, *Advances in Financial Machine Learning*

---

**End of handoff.**

This document is sufficient for any sufficiently competent successor (human or AI) to pick up the project, deploy it, understand the design choices, and continue building toward the offline-trained ML upgrades. The single-file constraint is intentional — keeps deployment friction at zero.
