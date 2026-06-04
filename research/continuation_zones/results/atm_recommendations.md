# NQ Continuation Zone Scalping — ATM Recommendations
Generated: 2026-05-26 02:17:26 UTC
Based on: 20 Optuna trials, walk-forward OOS period 2025-01-02 to 2026-04-24

## Summary

| Profile | Stop | Target | R:R | Win Rate | EV/Trade | OOS Sharpe |
|---------|------|--------|-----|----------|----------|------------|
| Conservative | 12 ticks | 14 ticks | 1.17:1 | 99.6% | $55.51 | 110.76 |
| Balanced | 6 ticks | 10 ticks | 1.67:1 | 99.6% | $35.69 | 113.75 |
| Aggressive | 8 ticks | 14 ticks | 1.75:1 | 99.6% | $35.69 | 113.75 |

## Profile 1: Conservative

### NinjaTrader ATM Settings
| Field | Value |
|-------|-------|
| Stop Loss | 12 ticks |
| Profit Target | 14 ticks |
| Auto Breakeven — Profit Trigger | 10 ticks |
| Auto Breakeven — Plus | 0 ticks |
| Auto Trail — Type | Tick |
| Auto Trail — Amount | 2 ticks |
| Auto Trail — Profit Trigger | 12 ticks |

### Performance (OOS)
- Win Rate: 99.6%
- Expected Value per Trade: $55.51
- OOS Sharpe: 110.76
- OOS Trades: 266

### Recommended For
- Zone type: both
- Minimum zone score: 4

## Profile 2: Balanced

### NinjaTrader ATM Settings
| Field | Value |
|-------|-------|
| Stop Loss | 6 ticks |
| Profit Target | 10 ticks |
| Auto Breakeven — Profit Trigger | 4 ticks |
| Auto Breakeven — Plus | 0 ticks |
| Auto Trail — Type | Tick |
| Auto Trail — Amount | 4 ticks |
| Auto Trail — Profit Trigger | 6 ticks |

### Performance (OOS)
- Win Rate: 99.6%
- Expected Value per Trade: $35.69
- OOS Sharpe: 113.75
- OOS Trades: 514

### Recommended For
- Zone type: both
- Minimum zone score: 4

## Profile 3: Aggressive

### NinjaTrader ATM Settings
| Field | Value |
|-------|-------|
| Stop Loss | 8 ticks |
| Profit Target | 14 ticks |
| Auto Breakeven — Profit Trigger | 6 ticks |
| Auto Breakeven — Plus | 0 ticks |
| Auto Trail — Type | Tick |
| Auto Trail — Amount | 4 ticks |
| Auto Trail — Profit Trigger | 6 ticks |

### Performance (OOS)
- Win Rate: 99.6%
- Expected Value per Trade: $35.69
- OOS Sharpe: 113.75
- OOS Trades: 514

### Recommended For
- Zone type: both
- Minimum zone score: 4

## Zone Detection Parameters (Best OOS Set)
| Parameter | Value |
|-----------|-------|
| SmallBodyRatio | 0.65 |
| MinZoneTicks | 2 |
| MaxAgeBars5m | 20 |
| MaxAgeBars15m | 20 |
| MaxTouchCount | 3 |
| MinScore | 4 |
| RTH Only | True |

## Honest Limitations
- Backtest uses limit order fills at zone boundary — real fills may differ
- Slippage assumed: 1 tick per side
- Commission assumed: $2.00 per contract per side
- Walk-forward OOS period: 2025-01-02 to 2026-04-24 (16 months)
- Minimum OOS trades required: 200
- Results should be paper-traded before live deployment
