# NQ/QQQ Proxy Bridge

## The math
NQ futures and QQQ track the same underlying (NDX/NASDAQ-100).

```
ratio = NQ_price / QQQ_price
nq_level = qqq_level * ratio
```

Example (May 2026 session):
- QQQ: $710.64 | NQ prev close: 29,580
- Ratio: 29,580 / 710.64 = 41.63×
- FlashAlpha call wall $718 → NQ: 718 × 41.63 = 29,892

## Recompute at session open
Run at 09:35 ET with live prices. Do not use prior day ratio for level calculation.

## When the proxy breaks
| Event | Proxy reliability | Action |
|-------|------------------|--------|
| Single large-cap catalyst (AAPL, NVDA, MSFT) | Reduced | Cross-check ES/SPY divergence |
| Index rebalance day | Low pre-market | Wait for open |
| After-hours (>6 PM ET) | Poor | Use NDX futures or wait |
| Futures basis event (roll week) | Slightly off | Add/subtract roll cost |
| Dividend ex-date (QQQ pays quarterly) | Minor skew | Note in levels, <0.5% effect |

## Sanity check formula
```
Cross-check: ES_level × 1.043 ≈ NQ_level (rough, varies by regime)
If |NQ_actual - cross_check| > 0.5%: basis event likely, reduce position size
```

## ES/SPY confirmation
- ES and NQ should confirm direction
- If NQ bullish but ES/SPY options show strong negative gamma: use ES as governor
- Dispersion signal: if SPX GEX positive but QQQ GEX negative → Mag-7 specific vs broad move
