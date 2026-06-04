# V8 Optimization Report

- Iterations completed: **100**
- Stop reason: **plateau>20 after minimum iteration gate**
- Best validation OOS fitness: **1.0000**
- Winning config test fitness: **0.6105**
- Target OOS >= 0.55: **met**

## Top-3 validation configs

| Rank | Iteration | OOS fitness | OOS win rate | OOS avg R:R | OOS trades | OOS total pnl |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 82 | 1.0000 | 1.0000 | 99.0000 | 3 | 16.0330 |
| 2 | 84 | 1.0000 | 1.0000 | 99.0000 | 3 | 13.8485 |
| 3 | 67 | 1.0000 | 1.0000 | 99.0000 | 4 | 11.2405 |

## Walk-forward test results (final 20%)

| Rank | Iteration | Validation fitness | Test fitness | Test win rate | Test avg R:R | Test trades | Test total pnl |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 82 | 1.0000 | 0.0000 | 0.0000 | 0.0000 | 2 | -5.7693 |
| 2 | 84 | 1.0000 | 0.2000 | 0.0000 | 0.0000 | 0 | 0.0000 |
| 3 | 67 | 1.0000 | 0.6105 | 0.4286 | 4.4421 | 7 | 18.0372 |

## Winner

- Iteration: **67**
- Validation OOS fitness: **1.0000**
- Test fitness: **0.6105**
- Test total pnl: **18.0372**

```json
{
  "BiasLongThreshold": 0.59481,
  "BiasLookback": 4,
  "BiasShortThreshold": -0.649336,
  "MaxSignalsPerSession": 23,
  "MinArrowConfluence": 4,
  "MinExhaustionStrength": 0.504331,
  "ShowBidAskFade": 1,
  "ShowClassicAbsorption": 1,
  "ShowEffortVsResult": 1,
  "ShowExhaustionPrint": 1,
  "ShowFadingMomentum": 0,
  "ShowFatPrint": 1,
  "ShowPassiveAbsorption": 0,
  "ShowStoppingVolume": 0,
  "ShowThinPrint": 0,
  "ShowZeroPrint": 0
}
```
