# Backtest Results — TIER 3 Follow-Signal

**Hypothesis:** TYPE_C bars (score 50-72) are predictive when traded in the
direction of the underlying absorption / exhaustion signal.

**Data:** NQ.c.0 1-min OHLCV, Jan 2 – Apr 10, 2026 (~85 RTH sessions)
**Signals:** Bar-structure absorption (wick ≥40%, vol ≥1.2x avg) + exhaustion
(failed 3-bar thrust, vol ≥1.4x avg, close ≥60% against direction)

## Summary — All Variants

| Metric | A (Aggressive) | B (Balanced) | C (Tight stop) |
|--------|---------------|--------------|----------------|
| Trades | 155 | 155 | 155 |
| Net PnL ($) | 3,606.50 | 4,786.50 | 986.50 |
| Win Rate (%) | 40.00 | 38.70 | 23.90 |
| Avg PnL ($) | 23.27 | 30.88 | 6.36 |
| Max DD ($) | 2,338.20 | 2,818.20 | 3,027.30 |
| Profit Factor | 1.24 | 1.25 | 1.08 |
| Sharpe | 1.63 | 1.68 | 0.53 |
| Longest Losing Streak | 8 | 8 | 18 |
| Expectancy ($) | 23.27 | 30.88 | 6.36 |

**Best variant:** B (Net PnL $4,786.50)

## Signal Type Split (Variant B)

**Both:** 155 trades — WR 38.7%, net $4,786.50, PF 1.25

## Time-of-Day Distribution — Winners vs Losers (Variant B)

| Hour | Winners | Losers | Win% |
|------|---------|--------|------|
| 09:00 | 3 | 9 | 25% |
| 10:00 | 22 | 43 | 34% |
| 11:00 | 5 | 4 | 56% |
| 12:00 | 3 | 8 | 27% |
| 13:00 | 13 | 10 | 57% |
| 14:00 | 7 | 11 | 39% |
| 15:00 | 7 | 10 | 41% |

## Variant A — Stop 8.0pts / Target 15.0pts

- Trades: **155**, Win%: **40.0%**
- Net PnL: **$3,606.50**, Avg: $23.27
- Max DD: $2,338.20, PF: 1.24, Sharpe: 1.63

Exit reasons: FLATTEN=1, STOP=93, TARGET=61

## Variant B — Stop 10.0pts / Target 20.0pts

- Trades: **155**, Win%: **38.7%**
- Net PnL: **$4,786.50**, Avg: $30.88
- Max DD: $2,818.20, PF: 1.25, Sharpe: 1.68

Exit reasons: FLATTEN=1, STOP=95, TARGET=59

## Variant C — Stop 5.0pts / Target 17.5pts

- Trades: **155**, Win%: **23.9%**
- Net PnL: **$986.50**, Avg: $6.36
- Max DD: $3,027.30, PF: 1.08, Sharpe: 0.53

Exit reasons: FLATTEN=1, STOP=118, TARGET=36
