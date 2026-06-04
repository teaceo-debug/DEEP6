# LVN + GEX Regime — Gamma Determines LVN Behavior

The single most important rule in LVN trading: **LVN behavior is entirely regime-dependent.**

In positive gamma, an LVN is a fade zone. In negative gamma, it's a breakout zone. Trading LVN without knowing the gamma regime is gambling. The same price level, the same thin volume zone, the same structural setup produces opposite outcomes depending on what dealers are doing. Gamma regime is the filter that separates profitable LVN trades from losing ones.

---

## Why Gamma Regime Changes Everything

Dealers (market makers) are always delta-neutral. When they sell options, they accumulate delta exposure and must hedge it by trading the underlying. The direction of that hedging depends on whether they're net long or net short gamma.

**Net long gamma (positive GEX):** Dealers sold puts and calls, collected premium, and are now long gamma. When price moves up, their delta goes positive, so they SELL the underlying to stay neutral. When price moves down, their delta goes negative, so they BUY. They trade against price movement. This creates a dampening effect on volatility.

**Net short gamma (negative GEX):** Dealers bought options (or sold too many in one direction). When price moves up, their delta goes negative, so they BUY to stay neutral. When price moves down, their delta goes positive, so they SELL. They trade with price movement. This amplifies volatility.

At an LVN, this distinction is critical. The thin book means any additional buying or selling pressure has an outsized effect on price. Dealer hedging flows, which are systematic and large, can either absorb or amplify the LVN's natural acceleration tendency.

---

## Positive Gamma + LVN

In positive gamma, dealers are buying dips and selling rallies. This is the mean-reversion force.

**What happens at LVN in positive gamma:**
- Price slices into the LVN (thin book, expected acceleration)
- Dealers, now delta-long from the move up, start selling to rebalance
- Their selling hits the thin LVN book, amplifying the reversal
- Price gets pulled back toward the nearest HVN or gamma wall
- The LVN becomes a mean-reversion trigger, not a breakout trigger

**Strategy: FADE LVN breaks in positive gamma.**

When price breaks into an LVN in a positive gamma environment, the default expectation is reversal back into value. The dealer hedging flow acts as a rubber band, pulling price back toward the gamma wall or POC.

**Specific behaviors:**
- POC fades work well. Price moves to LVN, dealers sell, price returns to POC.
- Value area rotations are reliable. VAH to VAL and back, with LVN zones acting as reversal triggers at the edges.
- Breakouts through LVN in positive gamma tend to fail. Even if price clears the LVN, dealer selling pressure builds and eventually overwhelms the move.
- Expect price back in value area within 1-2 bars after LVN touch in strong positive gamma.

**Risk:** Positive gamma doesn't mean zero breakouts. If the fundamental catalyst is strong enough (major news, large institutional order), price can break through despite dealer hedging. The gamma dampening reduces the probability of breakout, not to zero, but significantly.

---

## Negative Gamma + LVN

In negative gamma, dealers are selling into drops and buying into rallies. This is the trend-amplification force.

**What happens at LVN in negative gamma:**
- Price breaks into LVN (thin book, acceleration begins)
- Dealers, now delta-short from the move up, start buying to rebalance
- Their buying hits the thin LVN book, amplifying the move further
- Feedback loop: price breaks LVN, dealers hedge in same direction, more momentum, cascade
- LVN becomes a launch pad, not a wall

**Strategy: TRADE LVN breaks with wide stops in negative gamma.**

When price breaks through an LVN in a negative gamma environment, the default expectation is continuation to the next HVN or beyond. The dealer hedging flow acts as an accelerant.

**Specific behaviors:**
- Breakout velocity is 2-3x higher than in positive gamma. The thin book plus dealer buying creates rapid price movement.
- Expect the move to extend 1.5-2x the expected move before finding the next HVN.
- Acceptance beyond value area is the target. Don't expect price to return to the prior value area quickly.
- Expansion targets (1.5x, 2x expected move) are realistic in strong negative gamma.

**Critical rule: NEVER fade LVN in negative gamma conditions.**

Fading an LVN break in negative gamma is fighting both the structural thin zone AND the dealer hedging flow. The losses can be severe and fast. The thin book means stops get hit quickly, and the dealer flow means price doesn't come back.

---

## Call Wall / Put Wall at LVN

When a major options strike (call wall or put wall) coincides with an LVN zone, the interaction creates extreme behavior in either direction.

**Call wall at LVN:**
- Dealers are short calls at this strike, so they're short delta above it
- As price approaches from below, dealers sell the underlying to hedge
- The LVN's thin book amplifies the impact of this selling
- In positive gamma: strong resistance, potential pin. Price bounces hard off the LVN/call wall confluence.
- In negative gamma: violent rejection. Price approaches, dealers sell aggressively, price drops fast through the thin zone below.

**Put wall at LVN:**
- Dealers are short puts at this strike, so they're long delta below it
- As price approaches from above, dealers buy the underlying to hedge
- The LVN's thin book amplifies the impact of this buying
- In positive gamma: strong support, potential pin. Price bounces hard off the LVN/put wall confluence.
- In negative gamma: violent rejection upward. Price drops to LVN/put wall, dealers buy aggressively, price snaps back.

**The pin effect:** In positive gamma, when a major strike sits inside or at the edge of an LVN, the market can pin to that strike into expiration. The thin volume zone means there's no natural resting liquidity to hold price away from the strike, and dealer hedging flows keep pulling it back.

---

## Algorithmic Decision Tree

```
# Determine LVN strategy based on gamma regime

IF gamma_regime == "positive":
    LVN_behavior = "mean_reversion_trigger"
    primary_action = "fade_breaks_toward_nearest_HVN"
    stop_placement = "beyond_LVN_midpoint"
    target = "nearest_HVN_or_POC"
    breakout_probability = "low"

ELIF gamma_regime == "negative":
    LVN_behavior = "acceleration_zone"
    primary_action = "trade_breaks_with_wide_stops"
    stop_placement = "beyond_LVN_far_edge"
    target = "next_HVN_or_1.5x_expected_move"
    breakout_probability = "high"

# Check for options wall confluence
IF (call_wall OR put_wall) IN LVN_zone:
    IF gamma_regime == "positive":
        confluence_effect = "strong_pin_risk"
        action_modifier = "increase_fade_conviction"
    ELIF gamma_regime == "negative":
        confluence_effect = "violent_rejection"
        action_modifier = "expect_sharp_fast_move"

# Transition zones (near gamma flip)
IF abs(price - gamma_flip) < 10_NQ_points:
    regime_confidence = "low"
    action_modifier = "reduce_position_size_50pct"
    note = "regime_can_flip_intraday"
```

---

## Regime Transitions at LVN

The gamma flip level is where GEX crosses zero. Above the flip, positive gamma. Below the flip, negative gamma. When price is near the flip AND near an LVN, the setup is unstable.

**Near-flip LVN behavior:**
- Regime can switch mid-trade
- Dealer hedging flows are minimal near the flip (delta exposure is small)
- LVN behaves more like a pure structural level, without gamma amplification
- Footprint signals carry more weight than gamma signals in this zone
- Reduce position size by 50% when trading LVN within 10 NQ points of the gamma flip

**Regime flip through LVN:**
- If price breaks through an LVN AND crosses the gamma flip simultaneously, expect a regime change
- The move that breaks the LVN also changes dealer behavior from dampening to amplifying
- This is the highest-velocity scenario: structural breakout + regime flip + dealer flow all in the same direction
- These moves can be 30-50 NQ points in minutes

---

## DEEP6 Integration

The DEEP6 system uses FlashAlpha API for GEX data. The integration flow:

1. FlashAlpha API returns GEX by strike for NQ (via QQQ/NDX proxy)
2. Regime classification: sum GEX above and below current price, determine net sign
3. Identify gamma flip level (zero-crossing of GEX curve)
4. Identify call wall (highest positive GEX strike above price)
5. Identify put wall (highest positive GEX strike below price)
6. Pass regime + walls to LVN strategy selector
7. LVN strategy selector outputs: fade or trade, with position sizing modifier

The regime classification runs on each FlashAlpha data refresh (typically every 15-30 minutes during market hours). The LVN strategy selection updates accordingly.

**Signal output format:**
```python
{
    "gamma_regime": "positive" | "negative" | "transitional",
    "gamma_flip": float,  # NQ price level
    "call_wall": float,   # NQ price level
    "put_wall": float,    # NQ price level
    "lvn_strategy": "fade" | "trade" | "avoid",
    "position_modifier": float,  # 0.5 to 1.0
    "regime_confidence": "high" | "medium" | "low"
}
```

This output feeds directly into the composite scoring engine, where it modifies the weight assigned to LVN-based signals.
