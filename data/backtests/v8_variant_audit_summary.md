# V8 Variant Audit Summary

Source data: `data/backtests/nq_3mo_1m.csv`  
Evaluator: `deep6.backtest.variant_evaluator`  
Forward horizon used for verdicts: `10` bars

Verdict rules:
- `KEEP`: `oos_hit_rate >= 0.55` and `rr >= 1.5` and `n_oos >= 30`
- `KILL`: `oos_hit_rate < 0.50` and `n_oos >= 30`
- `INCONCLUSIVE`: `n_oos < 30` or high-hit/low-RR cases

| Variant | n_oos | oos_hit_rate | rr | verdict |
|---|---:|---:|---:|---|
| ABS_01 | 13710 | 0.971918 | 1.153691 | INCONCLUSIVE |
| ABS_02 | 12030 | 0.971488 | 1.154364 | INCONCLUSIVE |
| ABS_03 | 850 | 0.848235 | 1.074606 | INCONCLUSIVE |
| ABS_04 | 27 | 0.888889 | 0.793752 | INCONCLUSIVE |
| EXH_01 | 15686 | 0.771771 | 1.022469 | INCONCLUSIVE |
| EXH_02 | 17921 | 0.970872 | 1.166765 | INCONCLUSIVE |
| EXH_03 | 6415 | 0.770850 | 1.044710 | INCONCLUSIVE |
| EXH_04 | 787 | 0.820839 | 0.990124 | INCONCLUSIVE |
| EXH_05 | 5869 | 0.793491 | 1.023513 | INCONCLUSIVE |
| EXH_06 | 9674 | 0.969196 | 1.080140 | INCONCLUSIVE |

## Audit verdicts

- **KEEP:** none
- **KILL:** none
- **INCONCLUSIVE:** all 10 variants

## Notes

- `ABS_01`, `ABS_02`, `EXH_02`, and `EXH_06` posted very high OOS hit rates but failed the `rr >= 1.5` gate, so they stay **INCONCLUSIVE** rather than **KILL**.
- `ABS_04` remains **INCONCLUSIVE** because `n_oos = 27`, below the minimum sample threshold.
- On the 3-month proxy run, no variant met the combined entry-quality bar needed for **KEEP**.
