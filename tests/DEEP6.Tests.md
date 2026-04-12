# DEEP6 Engine Unit Tests — Phase 4a

Standalone validation of engine logic (no NT8 required).

## E1 Footprint
- Absorption wick >= 30% + |delta|/vol < 0.12 → score = 15
- STKt3 (7+ consecutive imbalances) → stkTier = 3
- Delta divergence (price down, cumD > 0) → bull +7pts

## E2 Trespass
- 100% bid imbalance DOM → imbEma approaches +1.0, score = 20
- EMA(5) convergence: 5 ticks in → stable signal

## E3 CounterSpoof
- W1 = 0.6 (> SpooW1=0.4) → spoof flagged, score elevated
- Cancel within 500ms after large order → _spEvt++

## E4 Iceberg
- trade_size > display_size * 1.5 → native iceberg detected
- Refill at same price within 250ms → synthetic iceberg

## E5 Micro
- All 4 likelihood inputs bull → P(bull) > 0.84
- Mixed inputs → P(bull) ≈ 0.50

## E7 ML Quality
- qP=0.80 vs baseline=0.71 → "+12%" displayed
- Kalman: velocity converges to price derivative after 5 bars

## Scorer
- 5 engines agree bull, score=85 → TYPE A
- 3 engines agree (< MinAgree=4) → score=0, QUIET
