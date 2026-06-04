# V8 Signal Variant Correlation Matrix

**Date**: 2026-05-24
**Data**: `nq_3mo_1m.csv` (96,100 bars, 85 sessions, Jan-Mar 2026)
**Method**: OHLCV proxy heuristics via `variant_evaluator.py`
**Window**: 5 bars (5 minutes) for co-occurrence
**Forward horizon**: 10 bars for hit-rate/RR evaluation

## Variant Summary

| Variant | Description | Signals | OOS HR | RR | PF | Verdict |
|---------|-------------|--------:|-------:|----:|----:|---------|
| ABS_01 | Classic Absorption | 42,403 | 0.9719 | 1.154 | 1.966 | INCONCLUSIVE |
| ABS_02 | Passive Absorption | 37,082 | 0.9715 | 1.154 | 1.953 | INCONCLUSIVE |
| ABS_03 | Stopping Volume | 2,487 | 0.8482 | 1.075 | 1.994 | INCONCLUSIVE |
| ABS_04 | Effort vs Result | 27 | 0.8889 | 0.794 | 0.855 | INCONCLUSIVE |
| EXH_01 | Large Body | 47,594 | 0.7718 | 1.023 | 1.002 | INCONCLUSIVE |
| EXH_02 | Wick Rejection | 55,644 | 0.9709 | 1.167 | 2.087 | INCONCLUSIVE |
| EXH_03 | Volume Divergence | 20,074 | 0.7709 | 1.045 | 1.264 | INCONCLUSIVE |
| EXH_04 | Compressed Range | 2,092 | 0.8208 | 0.990 | 1.079 | INCONCLUSIVE |
| EXH_05 | Rejection Divergence | 18,098 | 0.7935 | 1.024 | 1.003 | INCONCLUSIVE |
| EXH_06 | Wick Fade | 30,195 | 0.9692 | 1.080 | 2.067 | INCONCLUSIVE |

**Note**: All verdicts are INCONCLUSIVE because the fitness criteria require OOS HR >= 55% AND RR >= 1.5. Most variants meet the HR threshold but not the RR threshold. ABS_04 has N=27 (too few for statistical significance).

## Full Pairwise Co-Occurrence Matrix

45 unique pairs, sorted by maximum overlap descending.

**Reading the table**:
- **A>B%**: Percentage of variant A firings where variant B also fired within 5 bars
- **B>A%**: Percentage of variant B firings where variant A also fired within 5 bars
- **MaxOvl**: max(A>B%, B>A%) — the redundancy metric
- **DirAgr**: Percentage of co-occurring pairs where both variants agree on direction (LONG/SHORT)

| Pair | N(A) | N(B) | A>B% | B>A% | MaxOvl | DirAgr% |
|------|-----:|-----:|-----:|-----:|-------:|--------:|
| ABS_01 x ABS_02 | 42,403 | 37,082 | 99.9 | 100.0 | **100.0** | 54.4 |
| ABS_01 x ABS_03 | 42,403 | 2,487 | 21.5 | 100.0 | **100.0** | 57.6 |
| ABS_01 x EXH_02 | 42,403 | 55,644 | 100.0 | 99.9 | **100.0** | 51.7 |
| ABS_02 x EXH_02 | 37,082 | 55,644 | 100.0 | 99.7 | **100.0** | 51.8 |
| ABS_03 x EXH_02 | 2,487 | 55,644 | 100.0 | 21.4 | **100.0** | 50.5 |
| ABS_04 x EXH_04 | 27 | 2,092 | 100.0 | 2.4 | **100.0** | 14.8 |
| EXH_01 x EXH_02 | 47,594 | 55,644 | 100.0 | 99.7 | **100.0** | 49.5 |
| EXH_02 x EXH_05 | 55,644 | 18,098 | 89.0 | 100.0 | **100.0** | 52.4 |
| EXH_01 x EXH_05 | 47,594 | 18,098 | 91.9 | 99.9 | 99.9 | 43.2 |
| EXH_02 x EXH_03 | 55,644 | 20,074 | 84.7 | 99.9 | 99.9 | 51.9 |
| EXH_02 x EXH_06 | 55,644 | 30,195 | 99.1 | 99.9 | 99.9 | 52.5 |
| ABS_01 x EXH_01 | 42,403 | 47,594 | 99.7 | 99.8 | 99.8 | 50.3 |
| ABS_01 x EXH_05 | 42,403 | 18,098 | 90.3 | 99.8 | 99.8 | 54.0 |
| ABS_02 x ABS_03 | 37,082 | 2,487 | 21.5 | 99.8 | 99.8 | 57.9 |
| ABS_01 x EXH_03 | 42,403 | 20,074 | 84.9 | 99.7 | 99.7 | 51.3 |
| ABS_02 x EXH_01 | 37,082 | 47,594 | 99.7 | 99.5 | 99.7 | 50.1 |
| EXH_01 x EXH_06 | 47,594 | 30,195 | 99.3 | 99.7 | 99.7 | 50.7 |
| ABS_01 x EXH_06 | 42,403 | 30,195 | 99.0 | 99.6 | 99.6 | 52.5 |
| ABS_02 x EXH_05 | 37,082 | 18,098 | 90.5 | 99.6 | 99.6 | 54.9 |
| EXH_01 x EXH_03 | 47,594 | 20,074 | 84.6 | 99.6 | 99.6 | 52.3 |
| ABS_02 x EXH_03 | 37,082 | 20,074 | 85.0 | 99.5 | 99.5 | 51.2 |
| ABS_03 x EXH_01 | 2,487 | 47,594 | 99.4 | 20.4 | 99.4 | 48.1 |
| ABS_02 x EXH_06 | 37,082 | 30,195 | 99.0 | 99.3 | 99.3 | 52.5 |
| EXH_02 x EXH_04 | 55,644 | 2,092 | 18.5 | 99.2 | 99.2 | 55.9 |
| ABS_03 x EXH_06 | 2,487 | 30,195 | 99.1 | 20.8 | 99.1 | 50.1 |
| EXH_03 x EXH_06 | 20,074 | 30,195 | 99.1 | 84.7 | 99.1 | 49.8 |
| EXH_04 x EXH_06 | 2,092 | 30,195 | 98.9 | 19.2 | 98.9 | 54.4 |
| EXH_05 x EXH_06 | 18,098 | 30,195 | 98.9 | 88.6 | 98.9 | 52.2 |
| ABS_01 x EXH_04 | 42,403 | 2,092 | 18.6 | 98.8 | 98.8 | 56.0 |
| ABS_02 x EXH_04 | 37,082 | 2,092 | 18.5 | 98.2 | 98.2 | 56.2 |
| EXH_01 x EXH_04 | 47,594 | 2,092 | 18.0 | 97.8 | 97.8 | 51.4 |
| EXH_03 x EXH_05 | 20,074 | 18,098 | 89.9 | 85.4 | 89.9 | 47.6 |
| ABS_03 x EXH_05 | 2,487 | 18,098 | 88.3 | 20.9 | 88.3 | 55.5 |
| EXH_04 x EXH_05 | 2,092 | 18,098 | 85.6 | 18.2 | 85.6 | 51.7 |
| ABS_01 x ABS_04 | 42,403 | 27 | 0.1 | 74.1 | 74.1 | 30.8 |
| ABS_04 x EXH_02 | 27 | 55,644 | 74.1 | 0.1 | 74.1 | 20.0 |
| ABS_02 x ABS_04 | 37,082 | 27 | 0.1 | 70.4 | 70.4 | 29.4 |
| EXH_03 x EXH_04 | 20,074 | 2,092 | 12.2 | 67.6 | 67.6 | 49.7 |
| ABS_03 x EXH_03 | 2,487 | 20,074 | 63.9 | 14.1 | 63.9 | 50.3 |
| ABS_04 x EXH_06 | 27 | 30,195 | 63.0 | 0.1 | 63.0 | 23.5 |
| ABS_04 x EXH_01 | 27 | 47,594 | 48.1 | 0.0 | 48.1 | 61.5 |
| ABS_04 x EXH_05 | 27 | 18,098 | 44.4 | 0.1 | 44.4 | 16.7 |
| ABS_03 x EXH_04 | 2,487 | 2,092 | 37.6 | 42.3 | 42.3 | 60.0 |
| ABS_03 x ABS_04 | 2,487 | 27 | 0.6 | 40.7 | 40.7 | 33.3 |
| ABS_04 x EXH_03 | 27 | 20,074 | 40.7 | 0.1 | 40.7 | 45.5 |

## Redundant Pairs (MaxOverlap > 85%)

**34 out of 45 pairs** exceed the 85% overlap threshold. This extreme redundancy is driven by two factors:
1. OHLCV proxy heuristics use overlapping bar characteristics (wick %, body ratio, volume, close position)
2. The 5-bar window on 1-minute data is generous — 5 minutes captures bars that cluster during volatile periods

### Critical Observation: Direction Agreement is ~50%

Despite near-total temporal overlap, **direction agreement averages only 51-55%**. This means variants fire on the same bars but often disagree on direction. In a trading context, temporal overlap alone does NOT mean signal redundancy — a LONG absorption and SHORT exhaustion on the same bar are not redundant signals.

### Within-Family Redundancy (Actionable)

#### Absorption Family (ABS_01 through ABS_04)

| Pair | Overlap | Dir Agree | Recommendation |
|------|--------:|----------:|----------------|
| ABS_01 x ABS_02 | 100.0% | 54.4% | **KEEP ABS_01** (OOS HR 0.9719 vs 0.9715, marginally better RR). ABS_02 is functionally identical. |
| ABS_01 x ABS_03 | 100.0% | 57.6% | **KEEP both**. ABS_03 is a strict subset of ABS_01 (100% of ABS_03 fires near ABS_01, but only 21.5% reverse). ABS_03's 2,487 signals are selective high-volume events within ABS_01's broader 42K set. |
| ABS_04 | N=27 | — | **INSUFFICIENT DATA**. Only 27 signals across 3 months. Cannot evaluate meaningfully. |

**ABS family recommendation**: Keep ABS_01 as primary. Drop ABS_02 (duplicate). Retain ABS_03 as a high-conviction subset filter. Defer ABS_04 until footprint-level data is available.

#### Exhaustion Family (EXH_01 through EXH_06)

| Pair | Overlap | Dir Agree | Key Metrics |
|------|--------:|----------:|-------------|
| EXH_01 x EXH_02 | 100.0% | 49.5% | EXH_02 dominates: higher HR (0.971 vs 0.772), better RR (1.167 vs 1.023) |
| EXH_02 x EXH_03 | 99.9% | 51.9% | EXH_02 dominates: much higher HR and RR |
| EXH_02 x EXH_05 | 100.0% | 52.4% | EXH_02 dominates |
| EXH_02 x EXH_06 | 99.9% | 52.5% | Near-identical HR (0.971 vs 0.969), EXH_02 has better RR |
| EXH_01 x EXH_05 | 99.9% | 43.2% | Lowest direction agreement — they disagree more than agree |
| EXH_03 x EXH_05 | 89.9% | 47.6% | Both have ~77-79% OOS HR, similar performance |

**EXH family recommendation**: Keep EXH_02 as primary (highest HR, RR, and PF). Keep EXH_06 as secondary (strong HR/PF, 99.1% overlap with EXH_02 but ~50% direction agreement means they provide different directional reads). Drop EXH_01, EXH_03, EXH_05 (subsumed by EXH_02 with worse metrics). Retain EXH_04 as a specialized low-count filter (2,092 signals, moderate HR).

#### Cross-Family Redundancy

| Pair | Overlap | Dir Agree | Note |
|------|--------:|----------:|------|
| ABS_01 x EXH_02 | 100.0% | 51.7% | Both fire everywhere, but 48% direction disagreement = different signal semantics |
| ABS_01 x EXH_01 | 99.8% | 50.3% | Essentially coin-flip on direction |
| ABS_01 x EXH_06 | 99.6% | 52.5% | High temporal overlap but moderate direction agreement |

**Cross-family conclusion**: ABS and EXH variants fire on the same bars because OHLCV characteristics that produce large wicks/unusual volume trigger both absorption and exhaustion detectors. However, **they are NOT semantically redundant** — absorption detects hidden buying/selling within wicks, while exhaustion detects momentum failure. The ~50% direction agreement confirms they interpret the same price action differently.

## Complementary Pairs (MaxOverlap < 20%)

**Zero pairs** have < 20% max overlap. The lowest max overlap is 40.7% (ABS_03 x ABS_04, ABS_04 x EXH_03). All involve ABS_04 which has only 27 signals.

### Near-Complementary Analysis

The least-overlapping pairs with meaningful sample sizes:

| Pair | MaxOvl | MinOvl | Note |
|------|-------:|-------:|------|
| ABS_03 x EXH_03 | 63.9% | 14.1% | ABS_03 (stopping volume) and EXH_03 (volume divergence) are conceptually different but still overlap 64% when ABS_03 fires |
| ABS_03 x EXH_04 | 42.3% | 37.6% | Most balanced pair — roughly equal overlap in both directions. Both are low-count specialists (2,487 vs 2,092). 60% direction agreement is the highest of any pair. |
| EXH_03 x EXH_04 | 67.6% | 12.2% | EXH_04 (compressed range) is moderately selective within EXH_03's firing windows |

## Recommendations Summary

### Keep (3 variants)
| Variant | Why |
|---------|-----|
| **ABS_01** (Classic Absorption) | Best OOS HR among absorption variants (0.972), highest signal count (42K), best RR (1.154) |
| **EXH_02** (Wick Rejection) | Best metrics across all variants: OOS HR 0.971, RR 1.167, PF 2.087, highest count (55K) |
| **EXH_06** (Wick Fade) | Strong OOS HR (0.969), high PF (2.067), distinct conceptual basis (prior bar comparison) |

### Keep as Subset Filters (2 variants)
| Variant | Why |
|---------|-----|
| **ABS_03** (Stopping Volume) | 2,487 signals = selective subset of ABS_01. Higher PF (1.994). Useful as a "high-conviction" filter within absorption signals. |
| **EXH_04** (Compressed Range) | 2,092 signals. Moderate HR (0.821), but lowest overlap with other EXH variants. Best direction agreement (60%) with ABS_03 — potentially additive when they co-fire. |

### Drop (4 variants)
| Variant | Why |
|---------|-----|
| **ABS_02** (Passive Absorption) | 100% redundant with ABS_01, marginally worse on every metric |
| **EXH_01** (Large Body) | Subsumed by EXH_02, much worse OOS HR (0.772 vs 0.971) and near-zero PF edge (1.002) |
| **EXH_03** (Volume Divergence) | Subsumed by EXH_02, worse metrics (HR 0.771, PF 1.264) |
| **EXH_05** (Rejection Divergence) | Subsumed by EXH_02, moderate HR (0.794), minimal PF (1.003) |

### Defer (1 variant)
| Variant | Why |
|---------|-----|
| **ABS_04** (Effort vs Result) | N=27 signals. Insufficient for statistical analysis. Requires footprint-level data (volume vs range at tick level) to fire meaningfully on OHLCV. |

## Important Caveats

1. **OHLCV proxy limitation**: These results use 1-minute OHLCV bar characteristics as proxy heuristics for what are fundamentally order-flow (footprint) signals. At the footprint level, where actual bid/ask volume, delta, and individual price-level activity are visible, the variants would likely show much greater differentiation.

2. **Direction agreement ~50% is key**: The temporal overlap metric alone overstates redundancy. Two variants firing on the same bar but disagreeing on direction are providing genuinely different information. This cross-family pattern (ABS detecting hidden buying while EXH detects momentum failure on the same bar) is expected behavior, not a flaw.

3. **ABS_04 data insufficiency**: The Effort vs Result detector requires volume-to-range ratio analysis that OHLCV bars don't capture well. Its near-zero signal count (27) reflects this limitation, not the concept's invalidity.

4. **"INCONCLUSIVE" verdicts**: The fitness function requires OOS HR >= 55% AND RR >= 1.5. Most variants meet HR comfortably but fall short on RR. The 10-bar forward horizon may be too short for these reversal signals to mature.

## Evidence

- Raw pairwise data: `.sisyphus/evidence/task-7-correlation.txt`
- DuckDB with all signals: `data/backtests/v8_variant_audit.duckdb`
- Analysis script: computed in-memory via `variant_evaluator.py` extract
