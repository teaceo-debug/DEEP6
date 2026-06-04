# flashalpha-options — Complete Options Analytics Expert Skill
# Based on: https://flashalpha.com/skill.md (official)
# Expanded with: full 77-concept glossary, NQ-specific context

## Identity

FlashAlpha is an options analytics API for US equities and ETFs. It provides computed exposure analytics (GEX, DEX, VEX, CHEX), volatility surfaces, BSM Greeks, dealer positioning, max pain analysis, VRP, and options screening for 6,000+ symbols.

Two hosts:
- Live: https://lab.flashalpha.com
- Historical replay (Alpha tier): https://historical.flashalpha.com with required `?at=YYYY-MM-DDTHH:mm:ss`

Auth: `X-Api-Key` header OR `apiKey` query param. Same key for both hosts.

## When to invoke this skill

- Any FlashAlpha API question
- Options market structure question (GEX, vanna, charm, etc.)
- Gamma regime / dealer positioning question
- Options analytics integration or interpretation
- "What does [FlashAlpha field] mean?"
- "How do I interpret [VEX/CHEX/0DTE/VRP]?"
- Any question about dealer hedging mechanics
- Greeks computation or interpretation
- Volatility surface, skew, term structure questions

## Skill Files

Load these for deeper context:

- `concepts/exposure-analytics.md` — GEX, DEX, VEX, CHEX, flip, walls, regime, dealer hedging
- `concepts/zero-dte.md` — 0DTE analytics, expected move, pin risk, charm regime, gamma acceleration
- `concepts/volatility.md` — VRP, IV, realized vol, skew, term structure, SVI
- `concepts/greeks.md` — all 15 Greeks (first, second, third order)
- `api-reference.md` — complete endpoint reference with tiers

## SDK Quick Start

```python
from flashalpha import FlashAlpha
fa = FlashAlpha("YOUR_KEY")

# Key endpoints for NQ/QQQ bias work
summary = fa.exposure_summary("QQQ")  # regime + full exposure + interpretations [Growth]
levels  = fa.exposure_levels("QQQ")   # gamma flip, call wall, put wall [Free]
zte     = fa.zero_dte("QQQ")          # 0DTE pin risk, expected move, charm [Growth]
vex     = fa.vex("QQQ")               # vanna exposure [Basic]
chex    = fa.chex("QQQ")              # charm exposure [Basic]
mp      = fa.max_pain("QQQ")          # max pain, pin probability [Basic]
vol     = fa.volatility("QQQ")        # IV, VRP, skew, term structure [Growth]
```

## Tier Summary

| Tier | Monthly | Key Access |
|------|---------|------------|
| Free | $0 | Exposure levels (flip, walls), basic Greeks compute |
| Basic | $29 | VEX, CHEX, max pain, screening |
| Growth | $49 | Full summary, 0DTE, volatility, narratives, simulation |
| Alpha | $149 | Historical API, SVI params, VRP z-score, raw flow, advanced vol |

## Core Concepts at a Glance

**Exposure analytics** — how dealer hedging creates mechanical price flows:
- GEX: gamma exposure. Positive = dealers absorb moves. Negative = dealers amplify moves.
- DEX: delta exposure. Net dealer delta hedge requirement.
- VEX: vanna exposure. Dealer delta change when IV moves.
- CHEX: charm exposure. Dealer delta change as time passes.

**Gamma regime** — the single most important structural context:
- Above gamma flip = positive gamma = mean-reverting, range-bound
- Below gamma flip = negative gamma = trending, volatile, breakout behavior

**0DTE** — zero-days-to-expiry options dominate modern flow:
- Pin risk: gravity toward high-OI strikes near expiry
- Expected move: market-implied 1SD range for the session
- Charm regime: whether time decay creates buying or selling pressure

**Volatility** — the IV/RV relationship:
- VRP: implied vol premium over realized vol. Positive = options rich.
- Skew: put IV > call IV (normal). Widens before events.
- Term structure: contango (normal) vs backwardation (crisis).

## Anti-Hallucination Rules

- ONLY reference endpoints listed in `api-reference.md`. Do not invent endpoints.
- ONLY use field names documented there. Do not guess field names.
- Never mix live and historical hosts in the same response.
- If unsure about tier access: assume the user has Growth; flag Alpha-only features explicitly.
- GEX sign convention: calls positive, puts negative. Net GEX = sum. Do not reverse this.
- VEX interpretation: positive VEX + falling IV = dealers BUY. Negative VEX + falling IV = dealers SELL.
- CHEX interpretation: positive CHEX = time decay causes dealers to BUY. Negative = dealers SELL.
- Pin score > 70 = strong pin. Not "pin score > 50 = strong pin."

## Concept Index (77 concepts)

### Exposure
1. GEX (Gamma Exposure)
2. Net GEX
3. GEX per strike
4. Gamma flip level
5. Gamma regime (positive/negative)
6. DEX (Delta Exposure)
7. Net DEX
8. VEX (Vanna Exposure)
9. Net VEX
10. VEX interpretation (vol_up/vol_down)
11. CHEX (Charm Exposure)
12. Net CHEX
13. CHEX interpretation (time_decay_dealers_buy/sell)
14. Dealer shares to trade (±1% move)
15. Call wall
16. Put wall
17. Zero-DTE magnet strike
18. OI-weighted DTE

### 0DTE
19. Expected move (implied 1SD)
20. Remaining expected move (intraday)
21. Upper/lower bounds
22. Pin risk score (0-100)
23. Pin score sub-components (OI concentration, proximity, time, gamma)
24. Magnet strike
25. Gamma acceleration ratio
26. Net theta dollars (0DTE)
27. Theta per hour remaining
28. Charm regime (0DTE)
29. 0DTE call/put volume
30. 0DTE put/call ratio (volume)
31. 0DTE put/call ratio (OI)
32. ATM volume share %

### Volatility
33. Implied Volatility (IV)
34. ATM IV
35. IV surface
36. Realized Volatility (RV)
37. RV windows (5d, 10d, 20d, 30d, 60d)
38. VRP (Volatility Risk Premium)
39. VRP z-score (Alpha)
40. VRP regime (positive/negative)
41. GEX-conditioned VRP
42. IV Rank
43. IV Percentile
44. Volatility skew
45. 25-delta risk reversal
46. IV term structure
47. Contango (term structure)
48. Backwardation (term structure)
49. SVI model (Stochastic Volatility Inspired)
50. SVI parameters (a, b, rho, m, sigma)
51. SVI arbitrage flag
52. Variance swap pricing (Alpha)
53. Harvest score (Alpha)
54. Dealer flow risk score (Alpha)
55. Iron condor score (Alpha)
56. Strangle score (Alpha)
57. Calendar score (Alpha)

### Greeks (First Order)
58. Delta
59. Gamma
60. Theta
61. Vega
62. Rho

### Greeks (Second Order)
63. Vanna
64. Charm
65. Vomma
66. Dual Delta

### Greeks (Third Order / Advanced)
67. Speed
68. Zomma
69. Color
70. Ultima
71. Lambda (elasticity)
72. Veta

### Market Structure
73. Max pain
74. Pin probability
75. Open interest (OI) by strike
76. Options flow (tape)
77. Flow outliers / unusual activity
