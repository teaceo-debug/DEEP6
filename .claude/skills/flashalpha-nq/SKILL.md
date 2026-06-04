# flashalpha-nq — NQ Futures Dealer-State Playbook

## When to invoke
- "What does FlashAlpha say about NQ?"
- "What's the gamma regime right now?"
- "Where are the GEX walls for today?"
- "Is it positive or negative gamma?"
- Any options-positioning → NQ trading question
- Pre-session planning, level identification, regime classification

## Core mechanic: QQQ→NQ proxy bridge
FlashAlpha covers QQQ (NDX tracking ETF). NQ futures track NDX directly.

```
ratio = NQ_price / QQQ_price   # recompute each session
nq_level = qqq_level × ratio   # apply to every FlashAlpha level
```

Current ratio range: ~40–43 (varies with futures basis and dividend seasonality).
Verify at session open: if ratio diverges >2% from prior day, note it.

## FlashAlpha endpoint → NQ decision map

| Endpoint | Key output | NQ use |
|----------|-----------|--------|
| `exposure_summary` | regime, gamma_flip, interpretations | Primary regime classification |
| `exposure_levels` | call_wall, put_wall, zero_dte_magnet | Session pivot levels |
| `zero_dte` | pin_score, expected_move, regime | Intraday range and magnet |
| `vex` | net_vex, vex_interpretation | Vanna pressure direction |
| `chex` | net_chex, chex_interpretation | Time-decay hedging flow |

## Quick decision table

| FA signal | NQ trading mode |
|-----------|----------------|
| Negative gamma, spot below flip | Trend mode — add at breakouts, not fades |
| Positive gamma, spot in range | Range mode — fade at walls, buy support |
| Spot within 0.5% of flip | Stand down — transition zone, unpredictable |
| Pin score > 60 | Pin mode — expect magnet pull toward 0DTE magnet strike |
| VEX vol_up_dealers_sell | Downside amplified if vol spikes |
| CHEX time_decay_dealers_buy | Supportive into close (0DTE charm) |
| CHEX time_decay_dealers_sell | Selling pressure into close |

## DEEP6 integration
FlashAlpha outputs feed DEEP6 as Context tier:
- `regime_score`: 1 (positive gamma) / -1 (negative gamma)
- `wall_proximity_score`: distance from call/put wall in ATR units
- `pin_risk_score`: 0–100 from zero_dte.pin_risk.pin_score
- `harvest_score`: from FlashAlpha screener (if Alpha tier)

Load references: nq-qqq-proxy.md, regime-playbook.md, ict-confluence.md, risk-apex.md
