# DEEP6 Edge Research — Master Knowledge Base

## 1. Project Context

**System**: DEEP6 — NQ futures order flow trading system
**Thesis**: Absorption and exhaustion are the highest-alpha reversal signals in order flow.
**Live path**: NinjaTrader 8 (NT8) with Rithmic L2 DOM data
**Research path**: Python, deep6v2 package, 1yr OHLCV CSV + Databento MBO

The backtesting pipeline runs on **two data layers**:

| Layer | Data | Coverage | Use |
|-------|------|----------|-----|
| OHLCV (available now) | `data/backtests/nq_1yr_1m.csv` | Jan 2025 → Apr 2026 | Synthesized footprint signals |
| MBO (when downloaded) | `data/databento/nq_mbo/raw_dbn/` | Target: 3 weeks | True order-lifecycle signals |

---

## 2. Data Assets

### Available now (no key needed)
```
data/backtests/nq_1yr_1m.csv          # 458k 1-min RTH bars, Jan 2025–Apr 2026
data/backtests/nq_3mo_1m.csv          # 96k bars, ~3 months subset
data/backtests/signal_events.csv      # ~1.5M signal fires (run signal_collect.py)
data/backtests/analysis/              # Attribution outputs from signal_analyze.py
```

### Databento MBO (requires API key in .env)
```
DATABENTO_API_KEY=db-...  → add to .env
# Download 3 weeks:
python scripts/databento/download_nq_mbo.py --start 2026-04-28 --end 2026-05-19
# Output: data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-28_2026-05-19.dbn.zst
```

### Existing results
```
data/backtests/zones_1yr_variant_C_equity.png   # PF 4.48, WR 76.7%, Sharpe 8.68
data/backtests/tier3_followsignal_A_trades.csv  # Tier3 follow-signal trades
scripts/results_zones_1yr.txt                   # Full zones strategy report
```

---

## 3. Infrastructure Map

### Core pipeline scripts
```
scripts/signal_collect.py    # Step 1: collect all signal fires → signal_events.csv (~3 min)
scripts/signal_analyze.py    # Step 2: fast analysis → attribution tables + charts
scripts/signal_attribution.py # All-in-one (slower, for reference)
scripts/backtest_zones_1yr.py # Zones entry strategy (best known result: Variant C/D)
```

### Python packages
```
deep6v2/signals/registry.py        # DetectorRegistry — all 12 detector classes
deep6v2/signals/absorption.py      # ABS_01..04 — 4 absorption variants
deep6v2/signals/exhaustion.py      # EXH_01..06 — 6 exhaustion variants
deep6v2/signals/imbalance.py       # IMB_01..09 — 9 imbalance types
deep6v2/signals/delta.py           # DELT_01..11 — 11 delta signals
deep6v2/signals/auction.py         # AUCT_01..05 — 5 auction theory signals
deep6v2/signals/trap.py            # TRAP_01..05 — 5 trapped trader signals (weight=0 currently)
deep6v2/signals/vol_patterns.py    # VOLP_01..06 — 6 volume pattern signals
deep6v2/signals/engines/           # ENG_02..07 — DOM depth engines
deep6v2/backtest/replay_engine.py  # Full replay with trade simulation
deep6v2/backtest/ohlcv_synthesizer.py # OHLCV → synthetic FootprintBar
deep6v2/backtest/trade_simulator.py   # Trade entry/exit/P&L
deep6v2/scoring/scorer.py             # ConfluenceScorer — synthesizes all signals
```

### Current scoring weights (ScoringConfig — may need reoptimization)
```python
absorption_weight   = 20.0  # currently scored highest
exhaustion_weight   = 15.7
imbalance_weight    = 25.0  # highest weight
delta_weight        = 14.3
volume_profile_weight = 20.2
auction_weight      = 12.6
trapped_weight      = 0.0   # DISABLED — not enough evidence
poc_weight          = 0.0   # DISABLED
# Confluence multiplier: 1.25x when 5+ categories agree same direction
# Midday block: bars 60-210 per session (11:00-14:30 ET approx)
# TypeA threshold: 80, TypeB: 72, TypeC: 50
```

---

## 4. Signal Taxonomy

### 8 categories, 44 signals + engines

| Category | Signals | What they detect |
|----------|---------|-----------------|
| ABSORPTION | ABS_01-04 | Buyers/sellers absorbing aggression without giving ground |
| EXHAUSTION | EXH_01-06 | Momentum running out — thin prints, fading delta |
| IMBALANCE | IMB_01-09 | Stacked bid/ask imbalance at price levels |
| DELTA | DELT_01-11 | CVD divergence, delta traps, slingshot, reversals |
| VOLUME_PROFILE | VOLP_01-06 | POC sequencing, volume bubbles, LVN/HVN context |
| AUCTION | AUCT_01-05 | Unfinished business, poor high/low, market sweeps |
| TRAPPED | TRAP_01-05 | Trapped longs/shorts at extremes — currently weighted 0 |
| POC | (poc signals) | Point of control context — currently weighted 0 |
| DOM engines | ENG_02-05 | Queue imbalance, counter-spoof, iceberg, micro-probability |

### Key signal details

**ABS_01** — Classic wick absorption: high volume in wick + delta neutral
**ABS_02** — Passive absorption: large volume at extreme, price holds
**ABS_03** — Stopping volume: POC in wick, volume > ATR threshold
**ABS_04** — Effort vs result: high volume, narrow range relative to ATR

**EXH_01** — Zero print: price level with 0 volume (both sides)
**EXH_02** — Exhaustion print: high single-side volume at extreme, no continuation
**EXH_03** — Thin print: volume < 5% of bar's max at that price
**EXH_04** — Fat print: high volume, neutral delta at price
**EXH_05** — Fading momentum: price/delta divergence over 3 bars
**EXH_06** — Bid/ask fade: ask/bid volume at extreme < 60% of prior bar

**ENG_03** — CounterSpoof: DOM snapshot displacement + cancel rate (Wasserstein distance)
**ENG_04** — Iceberg: fill volume >> displayed volume at a level (ratio 2x)
**ENG_02** — Trespass: multi-level weighted DOM queue imbalance + logistic regression

### Synthesis-only signals (not in events CSV, computed from others)
**ENG_05** — MicroProb: Naive Bayes combining ENG_02 + ENG_04 outputs
**ENG_07** — ML quality engine (stub, returns 1.0 until trained)

---

## 5. Edge Research Methodology

### Step 1: Run signal collection
```bash
python scripts/signal_collect.py
# Output: data/backtests/signal_events.csv (~40MB)
# Time: ~3 minutes
```

### Step 2: Run base attribution
```bash
python scripts/signal_analyze.py
# Output: data/backtests/analysis/attribution_5b.txt + charts
# Time: ~30 seconds
```

### Step 3: Category deep dives (parallel agents)
```bash
python scripts/signal_analyze.py --category absorption --window 5
python scripts/signal_analyze.py --category exhaustion --window 5
python scripts/signal_analyze.py --category imbalance --window 10
python scripts/signal_analyze.py --signal ENG_02,ENG_03,ENG_04 --window 5
```

### Step 4: Read results
Key metrics to interpret:

| Metric | Interpretation |
|--------|---------------|
| **Profit Factor (PF)** | >1.5 = strong edge. >1.2 = moderate. <1.0 = negative alpha or noise |
| **Win Rate** | Context-dependent. 50-60% with 2:1 R:R = fine. 70%+ at 1:1 = excellent |
| **Sharpe** | >2.0 = good. >5.0 = exceptional (like Variant C). <1.0 = noisy |
| **N (fires)** | <10 = not statistically meaningful. >50 = usable. >200 = robust |
| **Forward decay** | Does edge persist at 1b, 2b, 5b, 10b, 30b? Fading fast = noise |
| **Time of day** | Strong signals should show consistent edge across hours, not just 09:30 |

### Step 5: Hypothesis testing
Once you find a signal with edge, validate it:
1. Walk-forward: split into 70/30 train/test on time axis
2. Regime conditioning: does edge hold in trending AND mean-reverting regimes?
3. Pair synergy: does the signal improve when combined with another?
4. Score threshold: does PF improve when requiring score >= 70 (TYPE_A)?

---

## 6. DOM Signal Theory (what we're looking for)

### The core thesis
**Absorption** at a level means informed buyers/sellers are willing to consume
all incoming aggression without retreating. This is the highest-alpha pattern
because it reveals where institutions are positioned.

**Evidence hierarchy for absorption (strongest first):**
1. Volume traded into level >> visible size (iceberg → true size hidden)
2. Multiple fills at exact price without level breaking
3. Delta divergence: aggressive selling into bid that holds → bullish
4. Refresh events: level restores after partial fill (MBO only)

### What synthetic OHLCV can and cannot tell us

| Can detect (OHLCV + synthesized footprint) | Cannot detect without MBO |
|---------------------------------------------|--------------------------|
| Wick-based absorption (ABS_01) | Order lifecycle (spoof by order ID) |
| Volume at price levels (synthesized) | True iceberg refresh tracking |
| Delta approximation from OHLCV shape | Queue position |
| POC, VAH, VAL from session profile | Cancel rate per order |
| Imbalance ratios (bid/ask split estimate) | Multi-order layering detection |
| Exhaustion prints | True fill vs display ratio |

**Implication**: OHLCV-based results are directionally useful but understate
the true edge of DOM signals. When Databento MBO data arrives, re-run all
detectors on real order-book data — expect signal quality to improve significantly
for ABS, EXH, ENG_03, ENG_04.

### Known strong signals from zones backtest (best validated result)
- **Zones strategy Variant D**: PF 4.93, WR 80.2%, MaxDD $1,366 over 16 months
- Setup: 15-min zone detection (Supply/Demand/RBR/DBD), exhaustion wick entry,
  score≥6, 10:00-15:00 ET, 1:1 R:R, distal+4t stop

---

## 7. New Signal Development Protocol

When building a new DOM detector:

1. **Write the detector** in `deep6v2/signals/` following `AbsorptionDetector` pattern
2. **Register it** in `DetectorRegistry.create_default()` in `registry.py`
3. **Write unit tests** in `tests_v2/signals/` with synthetic bar fixtures from `conftest.py`
4. **Re-run collection**: `python scripts/signal_collect.py` (overwrites events CSV)
5. **Analyze**: `python scripts/signal_analyze.py --signal MY_NEW_SIGNAL`
6. **Validate**: walk-forward split, time-of-day breakdown, regime conditioning

### MBO-native detectors (require Databento data)
These live in `cross_market/features/` (the cross-market plan package):
- `spoof_features.py` — order lifecycle: ADD → no fill → CANCEL in <5s
- `iceberg_features.py` — refresh tracking: traded_cum/peak_visible ≥ 3×, multiple ADD events
- `absorption_features.py` — MBO-native: aggressive_volume_into_level, level holds
- `sweep_features.py` — rapid multi-level prints, aggressor dominance
- `layering_features.py` — 3+ contiguous oversized levels, same side
- `vacuum_features.py` — near-touch depth collapse + cancel wave

---

## 8. Interpreting Results for Strategy Development

### What to look for in attribution output

**Tier distribution** — healthy system should show:
- TypeA (score≥80): rare (5-15 bars/session), very high conviction
- TypeB (score≥72): occasional, strong but not perfect setup
- TypeC (score≥50): more frequent, borderline edge
- QUIET: most bars (this is correct — the system should say "no edge" 80%+ of time)

**Signal co-occurrence matrix** — pairs with PF > individual signals = synergistic alpha.
Look especially for:
- Absorption + Delta divergence (confirming from two angles)
- Exhaustion + Imbalance (fading momentum with book evidence)
- Iceberg + Absorption (hidden and visible evidence of same level)

**Time-of-day breakdown** — alpha should concentrate in:
- 09:30-10:30 ET (NY open, highest institutional activity)
- 13:30-15:30 ET (afternoon session, pre-close positioning)
- Avoid: 11:00-13:00 ET (lunch, thin book, low confidence)
  → This is already partially handled by midday_block in scorer

**Forward decay** — if edge disappears by 5 bars (5 min on 1-min data):
- Signal is noise (random coincidence with price)
- Or: signal fires too late (price already moved)
If edge persists to 15-30 bars:
- Signal detects real structural support/resistance
- Wider targets appropriate

---

## 9. Files to Read Before Any Research Task

Always load these before starting work:

```
deep6v2/signals/registry.py         # Understand what detectors exist
deep6v2/config/scoring.py           # Current weights and thresholds
data/backtests/analysis/attribution_5b.txt  # Last attribution run (if exists)
scripts/results_zones_1yr.txt       # Best validated strategy for reference
```

Optional deep dives:
```
.planning/research/pine/deep/microstructure.md   # Academic signal theory
.planning/research/FEATURES.md                   # Full implementation research (898 lines)
deep6v2/signals/absorption.py                    # Reference detector implementation
```
