# DEEP6 Round 1: Signal Filter Optimization

**Sessions:** 50 | **Bars:** 19,500 | **Analysis date:** 2026-04-15
**Config:** ScoreEntryThreshold=40, MinTier=TYPE_C, Stop=8t, Target=16t

## Baseline (no filters)

| Metric | Value |
|--------|-------|
| Trades | 87 |
| Win Rate | 69.0% |
| Avg P&L | 4.28t |
| Sharpe | 4.047 |
| Profit Factor | 1.54 |
| Total P&L | 372.2t |

## 1. Drop-One Signal Pruning

Removing each signal in turn. Delta Sharpe = (new Sharpe) − (baseline Sharpe).
**Positive delta = removing this signal IMPROVES performance (noise signal).**

| Signal | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe | Delta PF | Verdict |
|--------|--------|------|---------|--------|-------------|---------|---------|
| EXH-02 | 27 | 77.8% | 13.43t | 25.414 | +21.367 | +7.91 | **NOISE** + |
| DELT-04 | 68 | 75.0% | 10.40t | 20.258 | +16.211 | +4.20 | **NOISE** + |
| AUCT-01 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | +0.00 | **NEUTRAL** ~ |
| DELT-01 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | +0.00 | **NEUTRAL** ~ |
| DELT-03 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | +0.00 | **NEUTRAL** ~ |
| IMB-01 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | +0.00 | **NEUTRAL** ~ |
| VOLP-03 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | +0.00 | **NEUTRAL** ~ |
| EXH-01 | 69 | 69.6% | 3.07t | 2.667 | -1.380 | -0.21 | **ALPHA** - |
| ABS-01 | 0 | 0.0% | 0.00t | 0.000 | -4.047 | -1.54 | **ALPHA** - |
| IMB-03 | 10 | 0.0% | -53.71t | -204.794 | -208.841 | -1.54 | **ALPHA** - |

**Noise signals (removing improves Sharpe):** EXH-02, DELT-04
**Alpha signals (removing hurts Sharpe):** EXH-01, ABS-01, IMB-03

## 2. Minimum Signal Count Filter

Require N signals in agreed direction on the entry bar.

| Min Signals | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe | Profit Factor |
|-------------|--------|------|---------|--------|-------------|---------------|
| 1 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | 1.54 |
| 2 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | 1.54 |
| 3 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | 1.54 |
| 4 | 73 | 76.7% | 11.24t | 21.801 | +17.754 | 6.50 | **<-- BEST**
| 5 | 41 | 70.7% | 9.01t | 16.851 | +12.804 | 4.57 |
| 6 | 0 | 0.0% | 0.00t | 0.000 | -4.047 | 0.00 |

**Sweet spot:** min_signals=4 → Sharpe 21.801 (+17.754 vs baseline)

## 3. Signal Recency Filter

Require at least one agreed-direction signal that fired within N bars of the entry bar.
max_age=unlimited is the baseline (no recency filter).

| Max Age (bars) | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe |
|---------------|--------|------|---------|--------|-------------|
| 1 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | **<-- BEST**
| 2 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 3 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 5 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 8 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| unlimited | 87 | 69.0% | 4.28t | 4.047 | +0.000 |

**Finding:** Signal recency matters: max_age=1 bars is optimal (Sharpe 4.047).

## 4. Category Diversity Filter

Require signals from at least K different scoring categories.

| Min Categories | Trades | Win% | Avg P&L | Sharpe | Delta Sharpe |
|---------------|--------|------|---------|--------|-------------|
| 1 | 87 | 69.0% | 4.28t | 4.047 | +0.000 | **<-- BEST**
| 2 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 3 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 4 | 87 | 69.0% | 4.28t | 4.047 | +0.000 |
| 5 | 0 | 0.0% | 0.00t | 0.000 | -4.047 |

**Sweet spot:** min_categories=1 → Sharpe 4.047 (+0.000 vs baseline)

## 5. Directional Agreement Filter

| Mode | Trades | Win% | Avg P&L | Sharpe | Profit Factor |
|------|--------|------|---------|--------|---------------|
| Mixed (allow opposing signals) | 87 | 69.0% | 4.28t | 4.047 | 1.54 |
| Strict (all signals agree) | 72 | 79.2% | 12.06t | 23.648 | 7.37 |

**Winner: STRICT** — delta Sharpe = +19.601 in favor of strict

## 6. VOLP-03 Regime Gate

From the P0 analysis: VOLP-03 co-occurrence = 0% win, -53.7t avg P&L.
Block any entry where VOLP-03 fired within the last 2 bars.

| Mode | Trades | Win% | Avg P&L | Sharpe | Total P&L |
|------|--------|------|---------|--------|-----------|
| No gate (baseline) | 87 | 69.0% | 4.28t | 4.047 | 372.2t |
| VOLP-03 gate active | 77 | 77.9% | 11.81t | 22.968 | 909.3t |

**Delta Sharpe: +18.921** — VOLP-03 gate RECOMMENDED

## 7. Essential Signal Set

Greedy forward selection to capture 100.0% of winning trades with minimum signals.

### Selection Steps

| Step | Signal Added | New Entries Captured | Cumulative | Coverage % |
|------|-------------|---------------------|-----------|-----------|
| 1 | **ABS-01** | +60 | 60/60 | 100.0% |

### Essential Set Performance

**Essential signals (1):** ABS-01

| Metric | Essential Set | Baseline | Delta |
|--------|--------------|----------|-------|
| Trades | 87 | 87 | +0 |
| Win Rate | 69.0% | 69.0% | +0.0% |
| Avg P&L | 4.28t | 4.28t | +0.00t |
| Sharpe | 4.047 | 4.047 | +0.000 |
| Profit Factor | 1.54 | 1.54 | +0.00 |
| Coverage | 100.0% | 100% | — |

## 8. Recommended Filter Combination

Based on the analysis above, the optimal entry filter configuration:

```
1. VOLP-03 regime gate: block entry if VOLP-03 fired within last 2 bars
2. Min signal count: 4 signals in agreed direction
3. Min categories: 1 distinct scoring categories
4. Directional agreement: strict mode
5. Signal recency: max 1 bars
6. Essential signal set: ABS-01
```

### Expected Impact vs Baseline

| Filter | Delta Sharpe | Trade Reduction | Recommendation |
|--------|-------------|-----------------|---------------|
| VOLP-03 gate | +18.921 | 10 | **APPLY** |
| Min signals=4 | +17.754 | 14 | **APPLY** |
| Min categories=1 | +0.000 | 0 | NEUTRAL |
| Directional=strict | +19.601 | 15 | **APPLY** |
| Recency<=1bars | +0.000 | 0 | NEUTRAL |

*Generated by `deep6/backtest/round1_signal_filter.py`*