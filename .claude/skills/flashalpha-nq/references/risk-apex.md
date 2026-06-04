# Apex Risk Discipline — Peak Asset Performance LLC

## Account parameters
- Account size: $50,000 (standard Apex)
- Trailing drawdown: 2.5% = **$1,250 max loss**
- Profit target: 10% = $5,000
- Contract: NQ (full, $20/point) or MNQ ($2/point)

## Drawdown math
```
3 losing MNQ trades × 20 points × $2/pt = $120
3 losing full NQ trades × 20 points × $20/pt = $1,200 (near daily limit)
1 losing full NQ trade × 63 points × $20/pt = $1,260 (BLOWS DRAWDOWN)
```
**One bad full NQ trade can end your account. Size kills, not direction.**

## Conviction-based sizing

| Conviction | Regime | Size |
|-----------|--------|------|
| < 40 | Any | No trade |
| 40–55 | Positive gamma (range) | 1 MNQ |
| 40–55 | Negative gamma (trend) | 1 MNQ |
| 56–70 | Positive gamma | 1–2 MNQ |
| 56–70 | Negative gamma | 2 MNQ |
| 71–85 | Positive gamma | 2–3 MNQ |
| 71–85 | Negative gamma | 2–4 MNQ |
| 86–100 | Positive gamma | 3–5 MNQ |
| 86–100 | Negative gamma | 4–6 MNQ |
| Any | Flip zone (±0.5%) | STAND DOWN |
| Any | OPEX Friday PM | Halve all sizes |

## Session stop rules
- 2 losing trades in a session: **stop trading for the day**
- Loss ≥ $400 in a session: stop regardless of trade count
- After session stop: journal entry mandatory, review before next session

## Time-based rules
- No trades in first 5 minutes (9:30–9:35 ET) — let the open settle
- No new positions after 3:45 PM ET (risk of stop-hunt into close)
- FOMC days: reduce to MNQ only until after announcement, then full size if conviction > 70

## NQ vs MNQ selection
- MNQ for: testing new setups, low conviction, high-volatility days
- NQ for: high conviction (>70), established regime, clear level confluence
- Never: mix NQ and MNQ in same setup (directional confusion)

## Level-based stops
- Positive gamma trade: stop just beyond the wall you're fading
- Negative gamma trade: stop at previous structure before breakout
- Flip zone: N/A — no trades
- Maximum stop: 25 NQ points (MNQ) / 15 NQ points (full NQ)
