# DEEP6 Round 3 — FINAL SWEEP (Imbalance Scoring Fix)

**Generated:** 2026-04-15
**Sessions:** 50 NQ sessions × 5 regimes (regenerated post-R2 + 12 NT8 audit fixes)
**Joint combos swept:** 864
**Walk-forward split:** 30 train / 10 validate / 10 test

---

## Executive Summary

**R3 key change:** ExtractStackedTier fix — imbalance signals now correctly
contribute to `cats`, `max_str`, and `bull_w/bear_w`. In R2, all IMB signals
used `continue` after updating `stacked_bull/bear`, which meant imbalance
never affected tier classification (TYPE_A/B/C) or signal strength thresholds.

**R3 stacked tier factor:** T1→0.5×imb_w, T2→0.75×imb_w, T3→1.0×imb_w
(replaces flat 0.5×imb_w for all tiers in R2).

**R2 optimal test-set Sharpe (walk-forward):** 38.584
**R3 optimal test-set Sharpe (walk-forward):** 36.993
**Delta R2→R3:** -4.1%
**Convergence verdict:** **CONVERGED**

---

## 1. Imbalance Fix Impact Audit

Measured on all 50 sessions, thesis_heavy weight profile:

| Metric | Value |
|--------|-------|
| Total bars analyzed | 19,500 |
| Bars with active categories (R2) | 1,817 |
| Bars with active categories (R3) | 3,368 |
| Tier upgrades (QUIET→C/B or B→A) | 65 (0.33% of bars) |
| New entry-qualifying bars in R3 | 21 |

---

## 2. Full-Dataset Sweep Results (R3)

### 2.1 Weight Profile Comparison

| weight_profile   |   mean_sharpe |   max_sharpe |   median_sharpe |   total_configs |
|:-----------------|--------------:|-------------:|----------------:|----------------:|
| current          |        27.419 |       52.325 |          26.870 |             288 |
| equal            |        25.364 |       52.325 |          24.168 |             288 |
| thesis_heavy     |        25.676 |       44.012 |          25.197 |             288 |

### 2.2 Entry Threshold Impact

|   entry_threshold |   mean_sharpe |   max_sharpe |
|------------------:|--------------:|-------------:|
|            40.000 |        31.120 |       44.012 |
|            50.000 |        27.583 |       42.920 |
|            60.000 |        21.919 |       40.994 |
|            70.000 |        23.990 |       52.325 |

### 2.3 Veto Filter & Stop Impact

**VOLP-03 veto:**

| volp03_veto   |   mean_sharpe |   total_net_pnl |
|:--------------|--------------:|----------------:|
| False         |        26.464 |     3879245.309 |
| True          |        25.842 |      653857.564 |

**Slow-grind veto:**

| slow_grind_veto   |   mean_sharpe |   total_net_pnl |
|:------------------|--------------:|----------------:|
| False             |        22.493 |     2561208.488 |
| True              |        29.812 |     1971894.385 |

**Trailing stop:**

| trailing_stop   |   mean_sharpe |
|:----------------|--------------:|
| False           |        29.027 |
| True            |        23.279 |

### 2.4 Top 10 Configurations (Full Dataset)

| weight_profile   |   entry_threshold |   stop_ticks |   target_ticks | trailing_stop   | volp03_veto   | slow_grind_veto   |   rr_ratio |   total_trades |   win_rate |   profit_factor |   sharpe |   net_pnl |
|:-----------------|------------------:|-------------:|---------------:|:----------------|:--------------|:------------------|-----------:|---------------:|-----------:|----------------:|---------:|----------:|
| current          |                70 |           12 |             24 | False           | False         | True              |      2.000 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| current          |                70 |           16 |             24 | False           | False         | True              |      1.500 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| current          |                70 |           20 |             24 | False           | False         | True              |      1.200 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| equal            |                70 |           12 |             24 | False           | False         | True              |      2.000 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| equal            |                70 |           16 |             24 | False           | False         | True              |      1.500 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| equal            |                70 |           20 |             24 | False           | False         | True              |      1.200 |             12 |      1.000 |             inf |   52.325 |  1114.850 |
| current          |                70 |           12 |             32 | False           | False         | True              |      2.667 |             11 |      1.000 |             inf |   44.499 |  1166.326 |
| current          |                70 |           16 |             32 | False           | False         | True              |      2.000 |             11 |      1.000 |             inf |   44.499 |  1166.326 |
| current          |                70 |           20 |             32 | False           | False         | True              |      1.600 |             11 |      1.000 |             inf |   44.499 |  1166.326 |
| equal            |                70 |           12 |             32 | False           | False         | True              |      2.667 |             11 |      1.000 |             inf |   44.499 |  1166.326 |

---

## 3. Walk-Forward Validation (Top 10 Configs)

- **Train:** session-21-ranging-01.ndjson, session-22-ranging-02.ndjson, session-23-ranging-03.ndjson, session-24-ranging-04.ndjson, session-25-ranging-05.ndjson... (30 sessions)
- **Validate:** session-27-ranging-07.ndjson, session-28-ranging-08.ndjson, session-47-slow_grind-07.ndjson... (10 sessions)
- **Test:** session-29-ranging-09.ndjson, session-30-ranging-10.ndjson, session-49-slow_grind-09.ndjson... (10 sessions)

|   rank | cfg_weight_profile   |   cfg_entry_threshold |   cfg_stop_ticks |   cfg_target_ticks | cfg_trailing_stop   | cfg_volp03_veto   | cfg_slow_grind_veto   |   train_sharpe |   val_sharpe |   test_sharpe |   test_pf |   test_net_pnl |   test_maxdd | passed_validation   |
|-------:|:---------------------|----------------------:|-----------------:|-------------------:|:--------------------|:------------------|:----------------------|---------------:|-------------:|--------------:|----------:|---------------:|-------------:|:--------------------|
|      1 | equal                |                    40 |               20 |                 40 | False               | False             | False                 |         40.143 |       68.183 |        36.993 |    40.108 |       4609.018 |      111.588 | True                |
|      2 | thesis_heavy         |                    50 |               20 |                 40 | False               | False             | False                 |         39.732 |       68.183 |        36.242 |    38.652 |       4437.424 |      111.588 | True                |
|      3 | current              |                    40 |               20 |                 40 | False               | False             | False                 |         39.711 |       68.183 |        37.000 |    40.128 |       4611.354 |      111.588 | True                |
|      4 | equal                |                    40 |               20 |                 32 | True                | False             | False                 |         37.066 |       74.018 |        40.113 |    33.447 |       4472.951 |      101.588 | True                |
|      5 | current              |                    40 |               20 |                 32 | True                | False             | False                 |         36.812 |       74.018 |        40.128 |    33.591 |       4492.786 |      101.588 | True                |
|      6 | thesis_heavy         |                    50 |               20 |                 32 | True                | False             | False                 |         36.806 |       74.018 |        38.993 |    31.753 |       4239.431 |      101.588 | True                |
|      7 | thesis_heavy         |                    40 |               20 |                 40 | False               | False             | True                  |         36.049 |       60.938 |        75.244 |   626.871 |       3921.688 |        6.266 | True                |
|      8 | equal                |                    40 |               20 |                 40 | False               | False             | True                  |         35.779 |       60.966 |        72.382 |   583.002 |       3646.805 |        6.266 | True                |
|      9 | current              |                    40 |               20 |                 40 | False               | False             | True                  |         35.511 |       60.966 |        75.198 |   626.348 |       3918.414 |        6.266 | True                |
|     10 | thesis_heavy         |                    40 |               20 |                 40 | False               | False             | False                 |         35.270 |       39.268 |        32.919 |    32.685 |       4587.690 |      111.588 | True                |

**10/10 configs passed walk-forward validation.**

---

## 4. R2 vs R3 Direct Comparison

| Metric | R2 (reference) | R3 (imbalance fix) | Delta R2→R3 |
|--------|---------------|-------------------|-------------|
| Test Sharpe (walk-forward) | 38.584 | 36.993 | -4.1% |
| Test Net PnL ($) | 4182.52 | 4609.02 | — |
| Test Win Rate | 0.939 | 0.946 | — |
| Max Drawdown ($) | 111.59 | 111.59 | — |

### 4.1 R2 vs R3 Parameter Config

| Parameter | R2 Recommended | R3 Optimal |
|-----------|---------------|------------|
| weight_profile | equal | equal |
| entry_threshold | 40 | 40 |
| stop_ticks | 20 | 20 |
| target_ticks | 40 | 40 |
| trailing_stop | False | False |
| volp03_veto | False | False |
| slow_grind_veto | False | False |

---

## 5. Stability Analysis — Top 3 Configs (±10% Sensitivity)

| config_label                                                            | param           | perturbation   |   orig_value |   perturbed_value |   baseline_sharpe |   perturbed_sharpe |   sharpe_pct_change | fragile   |
|:------------------------------------------------------------------------|:----------------|:---------------|-------------:|------------------:|------------------:|-------------------:|--------------------:|:----------|
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | entry_threshold | plus_10pct     |           40 |                44 |            42.484 |             34.085 |             -19.800 | False     |
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | entry_threshold | minus_10pct    |           40 |                36 |            42.484 |             42.470 |              -0.000 | False     |
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | stop_ticks      | plus_10pct     |           20 |                22 |            42.484 |             42.064 |              -1.000 | False     |
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | stop_ticks      | minus_10pct    |           20 |                18 |            42.484 |             37.928 |             -10.700 | False     |
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | target_ticks    | plus_10pct     |           40 |                44 |            42.484 |             44.277 |               4.200 | False     |
| wp=equal, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False        | target_ticks    | minus_10pct    |           40 |                36 |            42.484 |             41.182 |              -3.100 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | entry_threshold | plus_10pct     |           50 |                55 |            42.060 |             34.078 |             -19.000 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | entry_threshold | minus_10pct    |           50 |                45 |            42.060 |             42.220 |               0.400 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | stop_ticks      | plus_10pct     |           20 |                22 |            42.060 |             41.642 |              -1.000 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | stop_ticks      | minus_10pct    |           20 |                18 |            42.060 |             37.532 |             -10.800 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | target_ticks    | plus_10pct     |           40 |                44 |            42.060 |             43.782 |               4.100 | False     |
| wp=thesis_heavy, thr=50, sl=20, tp=40, trail=False, v03=False, sg=False | target_ticks    | minus_10pct    |           40 |                36 |            42.060 |             40.836 |              -2.900 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | entry_threshold | plus_10pct     |           40 |                44 |            42.220 |             42.060 |              -0.400 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | entry_threshold | minus_10pct    |           40 |                36 |            42.220 |             42.223 |               0.000 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | stop_ticks      | plus_10pct     |           20 |                22 |            42.220 |             41.802 |              -1.000 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | stop_ticks      | minus_10pct    |           20 |                18 |            42.220 |             37.682 |             -10.700 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | target_ticks    | plus_10pct     |           40 |                44 |            42.220 |             43.994 |               4.200 | False     |
| wp=current, thr=40, sl=20, tp=40, trail=False, v03=False, sg=False      | target_ticks    | minus_10pct    |           40 |                36 |            42.220 |             40.996 |              -2.900 | False     |

**No fragile parameters detected.** All ±10% perturbations within 50% Sharpe tolerance.

---

## 6. Convergence Verdict & Next Steps

**R2 optimal walk-forward test Sharpe:** 38.584
**R3 optimal walk-forward test Sharpe:** 36.993
**Sharpe improvement R2→R3:** -4.1%

### Verdict: CONVERGED

R3 sweep is within 5% of R2 optimal Sharpe. The imbalance fix had
minimal effect on the aggregate score distribution across these 50 sessions.
This indicates the existing 50-session dataset has few bars where stacked
imbalance tiers drive the primary entry signal.

**Recommended next steps:**
1. Lock the R3 FINAL-CONFIG.json for live deployment
2. Monitor live imbalance signal firing rate as ground truth for fix impact
3. Expand to 200+ session dataset to validate robustness

---

## 7. FINAL Production Configuration (R3)

```
weight_profile     : equal
entry_threshold    : 40
stop_ticks         : 20 (5.00 pts / $100)
target_ticks       : 40 (10.00 pts / $200)
trailing_stop      : False
volp03_veto        : False
slow_grind_veto    : False
R:R ratio          : 2.00
# R1/R2 features (active, not swept):
breakeven_enabled          : True  (activation=10t, offset=2t)
scale_out_enabled          : True  (50% at 16t)
strict_direction_enabled   : True
blackout_window            : 1530-1600 ET
# R3 signal fix:
imbalance_extract_stacked  : True  (T1=0.5, T2=0.75, T3=1.0 × imb_w)
```

*Generated by deep6/backtest/round3_final_sweep.py*