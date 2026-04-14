# DEEP6 — Recommended ATM Strategy Templates

NinjaTrader 8 ATM Strategies are bracket-order templates that NT8 places automatically when an order fills (stop loss + 1-3 profit targets, optional break-even / trail-stop logic). The DEEP6 indicator and DEEP6 Strategy both reference ATM templates **by name** — you create them once in NT8's UI, and the system attaches them to every signal-driven entry.

This doc is the recommended template set for trading off DEEP6 signals on NQ/MNQ.

## Why different ATMs per signal family

Per the trader-perspective review (see `.planning/phases/16-*/INTERACTION-LOGIC.md`):

- **Absorption** stops should be **wider** — the absorbing side defends a level, but price often *retests* the wick before the reversal sticks. Tight stops get knocked out on the retest. Stop = 1-2 ticks past the prior swing or session POC, whichever is closer.
- **Exhaustion** stops can be **tighter** — exhaustion fires after a momentum collapse; if it fails, it fails fast. Stop = 1 tick past the bar extreme.
- **Confluence (ABS+EXH stacked, or signal at wall)** uses the **tighter** of the two — the wall proves liquidity, so wider stops are wasted.

## Where to set up ATMs in NT8

1. SuperDOM (or any chart) → click the small "ATM Strategy" dropdown → **<Custom>**
2. Click **Save As…** at the bottom
3. Configure parameters per the recipes below
4. Save with the exact name in the recipe (so DEEP6 Strategy can reference them)

Note: if you trade **MNQ** instead of **NQ**, all stop/target *tick distances* stay the same (the contracts are the same instrument family, micro = 1/10 multiplier). Position size becomes 10× to keep the same risk dollars.

---

## Recipe 1 — `DEEP6_Absorption` (wider, conservative)

For ABS-01 CLASSIC, ABS-02 PASSIVE signals — fade-the-edge setups.

| Setting | Value | Why |
|---|---|---|
| Strategy name | `DEEP6_Absorption` | Strategy file references this exact name |
| Quantity | 2 | Sized for 1R = $50 on NQ ($5/tick × 5 ticks × 2 contracts) |
| Stop loss | **6 ticks** | Wide enough to survive the wick retest |
| Profit target 1 | 6 ticks (qty 1) | 1:1 R, scale half off here |
| Profit target 2 | 12 ticks (qty 1) | 2:1 R, runner |
| Auto break-even | After **+4 ticks** unrealized | Move stop to entry+1t once T1 is in reach |
| Auto trail | OFF | Let T2 work; trailing is too noisy on NQ |
| Time-in-force | DAY | Cancel at session close |

**Worst-case loss:** 6 × $5 × 2 = $60 per trade.
**Target win:** $30 (T1) + $60 (T2) = $90 if both hit.

## Recipe 2 — `DEEP6_Exhaustion` (tighter, faster)

For EXH-01 ZERO_PRINT, EXH-02 EXHAUSTION_PRINT, EXH-05 FADING_MOMENTUM — momentum-collapse fades.

| Setting | Value | Why |
|---|---|---|
| Strategy name | `DEEP6_Exhaustion` | Strategy file references this |
| Quantity | 2 | Same risk profile |
| Stop loss | **4 ticks** | Tighter — exhaustion fails fast or works |
| Profit target 1 | 4 ticks (qty 1) | 1:1 R |
| Profit target 2 | 10 ticks (qty 1) | 2.5:1 R |
| Auto break-even | After **+3 ticks** unrealized | Aggressive — exhaustion winners run quickly |
| Auto trail | 4 ticks (qty 1, runner only) | Trail T2 by 4 ticks once break-even moved |
| Time-in-force | DAY | |

**Worst-case loss:** 4 × $5 × 2 = $40.
**Target win:** $20 (T1) + $50 (T2) = $70.

## Recipe 3 — `DEEP6_Confluence` (the A+ trade)

For Tier 3 setups: stacked ABS+EXH at a wall, OR signal at VAH/VAL with strength ≥ 0.85, OR signal within 3 ticks of GEX flip.

| Setting | Value | Why |
|---|---|---|
| Strategy name | `DEEP6_Confluence` | Reserved for highest-conviction |
| Quantity | 4 | Double size — A+ trades earn more $ on same %R |
| Stop loss | **4 ticks** | Tighter; the wall/level is the invalidation |
| Profit target 1 | 4 ticks (qty 2) | Half off at 1R |
| Profit target 2 | 12 ticks (qty 1) | 3:1 R runner |
| Profit target 3 | 20 ticks (qty 1) | 5:1 R "let it run" |
| Auto break-even | After **+3 ticks** | Lock in fast |
| Auto trail | 5 ticks on T3 only | T3 trails after break-even |
| Time-in-force | DAY | |

**Worst-case loss:** 4 × $5 × 4 = $80 (still under the $250 default daily loss cap).
**Target win on full hit:** $40 + $60 + $100 = $200.

## Recipe 4 — `DEEP6_Practice` (sim only)

Identical to `DEEP6_Absorption` but quantity = 1 and tighter targets. For paper/sim accounts when you're learning the signals. Strategy can default to this template for the `Sim101` account.

---

## How DEEP6 Strategy picks an ATM

The strategy file (`DEEP6Strategy.cs`) has properties:

```
AtmTemplateAbsorption  = "DEEP6_Absorption"
AtmTemplateExhaustion  = "DEEP6_Exhaustion"
AtmTemplateConfluence  = "DEEP6_Confluence"
AtmTemplateDefault     = "DEEP6_Practice"
```

Match logic on signal fire:
1. If trigger is **stacked confluence (ABS + EXH same direction)** → `Confluence` template
2. Else if signal kind is `EXH-*` → `Exhaustion` template
3. Else if signal kind is `ABS-*` → `Absorption` template
4. Else → `Default` template

You can override any of the 4 names in the indicator's properties dialog.

## Sizing math reference

NQ futures: $5 per tick (0.25 points).
MNQ futures: $0.50 per tick.
1R = (stop in ticks) × ($/tick) × (quantity).

| Account | Recommended max %R per trade | DEEP6_Absorption qty | DEEP6_Confluence qty |
|---|---|---|---|
| $5,000 sim | 1% = $50 | 1 NQ or 10 MNQ | 2 NQ |
| $25,000 live | 0.5% = $125 | 4 NQ or 40 MNQ | 8 NQ |
| $100,000 live | 0.5% = $500 | 16 NQ | 32 NQ |

**Always** trade MNQ (or sim) until you've taken 50+ DEEP6 signals and have a positive expectancy log. The visual signals are auditable; the per-trigger expectancy is not — yet.

## Failure modes to know

- **ATM template not found** → strategy logs "ATM template DEEP6_X not found, using flat order" and submits a market entry with no bracket. **Set up all 4 templates before enabling live trading.**
- **Spread > 2 ticks** → tight ATMs slip; consider widening DEEP6_Exhaustion stop to 5 ticks during high-spread sessions (overnight).
- **Multiple signals same bar** → strategy enforces a 1-bar cooldown; only the first fires.

## Update cadence

Re-tune these recipes after every 100 logged trades. The defaults are sane starting points, not optimized values.
