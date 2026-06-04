# Exposure Analytics — GEX, DEX, VEX, CHEX, Dealer Positioning

This document covers the four core exposure metrics FlashAlpha computes, the gamma regime framework, and how dealer hedging creates mechanical price flows.

---

## GEX (Gamma Exposure)

### Formula

```
GEX = Σ(gamma × OI × 100 × S²)
```

Per contract: `gamma × open_interest × 100 × spot_price²`

Sign convention:
- Calls: **positive** GEX contribution
- Puts: **negative** GEX contribution

Net GEX = sum across all strikes and expirations.

### What it measures

GEX quantifies how much dollar gamma dealers are carrying. Because market makers are typically short options (they sell to retail and institutional buyers), their net position is usually short gamma. But when call OI dominates, net GEX can go positive.

The sign tells you which way dealers must hedge when spot moves:

| Net GEX | Dealer position | Spot moves up | Spot moves down |
|---------|----------------|---------------|-----------------|
| Positive | Long gamma | Dealers SELL (short delta) | Dealers BUY (long delta) |
| Negative | Short gamma | Dealers BUY (long delta) | Dealers SELL (short delta) |

Positive gamma dealers act as a stabilizing force. Negative gamma dealers amplify moves.

### Key fields

- `net_gex` — total dollar gamma exposure
- `net_gex_label` — "positive" or "negative"
- `gex_by_strike` — GEX at each strike (use to find walls)
- `gex_by_expiry` — GEX bucketed by expiration

---

## Gamma Flip Level

The gamma flip is the strike where cumulative GEX crosses zero. It's the single most important structural level in options analytics.

**How to find it:** Sort strikes by price. Compute cumulative GEX from lowest to highest. The flip is where the running sum changes sign.

**Interpretation:**
- Spot **above** flip = positive gamma regime
- Spot **below** flip = negative gamma regime
- Spot **at** flip = transition zone, highest uncertainty

The flip acts as a regime boundary, not a support/resistance level in the traditional sense. Price doesn't "bounce" off it. Instead, crossing it changes the character of price action.

**FlashAlpha field:** `gamma_flip` in the exposure levels response.

---

## Gamma Regime

### Positive Gamma Regime (above flip)

Dealers are net long gamma. Their hedging is counter-trend:
- Spot rallies → dealers accumulated short delta → they sell → rally dampened
- Spot drops → dealers accumulated long delta → they buy → drop cushioned

Result: mean-reverting price action, compressed realized vol, range-bound behavior. IV tends to stay low. Breakouts fail more often. This is the "sell the rip, buy the dip" environment.

### Negative Gamma Regime (below flip)

Dealers are net short gamma. Their hedging is pro-trend:
- Spot rallies → dealers need more long delta → they buy → rally accelerated
- Spot drops → dealers need more short delta → they sell → drop accelerated

Result: trending, volatile, breakout-prone behavior. Realized vol expands. Moves are larger and more sustained. This is the "let winners run" environment.

### Transition through the flip

The flip zone itself is the most dangerous. Dealers are near-flat gamma, so their hedging is minimal. But small moves can flip the regime, causing sudden character changes. Expect whipsaw and unpredictable behavior near the flip.

---

## DEX (Delta Exposure)

### Formula

```
DEX = Σ(delta × OI × 100 × S)
```

Measures the total share-equivalent delta that dealers must hedge across all positions.

### Interpretation

Because dealers are typically short options, their delta exposure is the opposite of the options they sold:
- Sold calls → short delta → must buy shares to hedge
- Sold puts → long delta → must sell shares to hedge

**Net positive DEX:** Dealers are net short delta. They must buy underlying to stay delta-neutral. This creates a structural bid under the market.

**Net negative DEX:** Dealers are net long delta. They must sell underlying. This creates structural overhead resistance.

DEX is less dynamic than GEX (delta doesn't change as fast as gamma), but it tells you the baseline directional pressure from dealer hedging.

### Key fields

- `net_dex` — total dollar delta exposure
- `dex_by_strike` — delta exposure per strike
- `dealer_shares_to_trade` — estimated shares dealers must trade on a ±1% spot move

---

## VEX (Vanna Exposure)

### Formula

```
VEX = Σ(vanna × OI × 100 × S)
```

Where vanna = ∂Δ/∂σ (how delta changes when implied volatility changes).

### What it measures

VEX tells you how dealer delta changes when IV moves. This creates mechanical flows whenever volatility compresses or expands, independent of spot price movement.

### Interpretation table

| Net VEX | IV direction | Dealer action | Price effect |
|---------|-------------|---------------|--------------|
| Positive | Falling | Dealers SELL delta (buy underlying) | Bullish |
| Positive | Rising | Dealers BUY delta (sell underlying) | Bearish |
| Negative | Falling | Dealers BUY delta (sell underlying) | Bearish |
| Negative | Rising | Dealers SELL delta (buy underlying) | Bullish |

Wait — the direction is counterintuitive. Here's the mechanics:

When IV falls, OTM options lose delta faster than ATM options. If dealers are short those OTM options (positive vanna position), their net delta becomes less negative (or more positive). To stay delta-neutral, they must sell underlying. But from the market's perspective, this selling pressure is bearish.

The FlashAlpha `interpretation` field handles this for you:
- `"vol_up_dealers_sell"` — IV rising causes dealers to sell
- `"vol_down_dealers_buy"` — IV falling causes dealers to buy
- `"vol_up_dealers_buy"` — IV rising causes dealers to buy
- `"vol_down_dealers_sell"` — IV falling causes dealers to sell

### VEX rally (the most important use case)

Post-FOMC, post-earnings, or any vol crush event: IV compresses rapidly. If net VEX is positive, this triggers mechanical dealer buying. The market rallies not because of fundamental news but because dealers must buy to rebalance. This is the "vanna rally" or "vol crush rally."

Magnitude: `net_vex × Δσ` gives approximate dollar flow from vanna rebalancing.

### Key fields

- `net_vex` — total vanna exposure
- `interpretation` — human-readable dealer action description
- `vex_by_strike` — vanna exposure per strike (shows where the flows concentrate)

---

## CHEX (Charm Exposure)

### Formula

```
CHEX = Σ(charm × OI × 100 × S)
```

Where charm = ∂Δ/∂t (how delta changes as time passes).

### What it measures

CHEX tells you how dealer delta changes purely from time passing, with no spot or vol movement. This creates predictable intraday flows, especially into the close and on expiration days.

### Interpretation

**Positive CHEX:** As time passes, dealer delta decreases (becomes less positive or more negative). To stay delta-neutral, dealers must BUY underlying. This creates buying pressure into the close.

**Negative CHEX:** As time passes, dealer delta increases. Dealers must SELL. This creates selling pressure into the close.

The FlashAlpha `interpretation` field:
- `"time_decay_dealers_buy"` — time passing causes dealers to buy
- `"time_decay_dealers_sell"` — time passing causes dealers to sell

### 0DTE charm

On expiration day, charm is most extreme. ATM options have the highest charm magnitude. As the session progresses:
- OTM options rapidly lose delta (charm effect)
- ITM options rapidly gain delta (charm effect)
- Dealers must rebalance continuously

This creates the characteristic "pinning" behavior near high-OI strikes. The charm flows reinforce the pin.

### Key fields

- `net_chex` — total charm exposure
- `interpretation` — dealer action description
- `chex_by_strike` — charm exposure per strike

---

## Dealer Hedging Estimates

FlashAlpha computes how many shares dealers must trade on a ±1% spot move:

```
dealer_shares_to_trade_up   # shares bought/sold if spot +1%
dealer_shares_to_trade_down # shares bought/sold if spot -1%
```

In **positive gamma**: `up` is negative (dealers sell on rally), `down` is positive (dealers buy on dip). Stabilizing.

In **negative gamma**: `up` is positive (dealers buy on rally), `down` is negative (dealers sell on dip). Amplifying.

The magnitude tells you how much mechanical flow to expect from a given move. Large absolute values = strong dealer influence on price action.

---

## Call Wall / Put Wall

### Call Wall

The strike with the highest net positive GEX. This is where dealer long-gamma hedging is most concentrated on the upside.

In positive gamma regime: the call wall acts as a ceiling. Dealers sell aggressively as spot approaches, capping the rally.

In negative gamma regime: the call wall is a breakout target. Once breached, dealers must buy through it, accelerating the move.

**FlashAlpha field:** `call_wall` in exposure levels.

### Put Wall

The strike with the highest net negative GEX (most negative). This is where dealer short-gamma hedging is most concentrated on the downside.

In positive gamma regime: the put wall acts as a floor. Dealers buy aggressively as spot approaches, supporting the decline.

In negative gamma regime: the put wall is a breakdown target. Once breached, dealers must sell through it, accelerating the drop.

**FlashAlpha field:** `put_wall` in exposure levels.

### Wall behavior summary

| Regime | Call wall | Put wall |
|--------|-----------|----------|
| Positive gamma | Resistance ceiling | Support floor |
| Negative gamma | Breakout target | Breakdown target |

---

## Zero-DTE Magnet Strike

The strike with the highest 0DTE net GEX magnitude near spot. This is the gravitational center for same-day expiry options.

As expiry approaches, gamma at this strike becomes enormous. Dealers must hedge aggressively near it. The result: price gets "pinned" to this strike in the final hour of trading.

**FlashAlpha field:** `zero_dte_magnet` in exposure levels.

Most powerful when:
- Pin score > 60 (see zero-dte.md)
- Less than 2 hours to close
- High OI concentration at the magnet strike

---

## OI-Weighted DTE

The average days-to-expiry across all open interest, weighted by OI size.

```
oi_weighted_dte = Σ(OI_i × DTE_i) / Σ(OI_i)
```

**Low value (< 7 days):** Positioning is near-term heavy. The market is gamma-sensitive. Small spot moves create large dealer hedging flows. Expect more volatile, reactive price action.

**High value (> 30 days):** Positioning is long-dated. The market is vega/vanna-sensitive. IV moves matter more than spot moves. Dealer flows are driven by volatility changes, not price changes.

**FlashAlpha field:** `oi_weighted_dte` in exposure summary.

---

## Exposure Summary Interpretation

The `exposure_summary` endpoint (Growth tier) returns a composite view:

```json
{
  "net_gex": 2.3e9,
  "net_gex_label": "positive",
  "gamma_flip": 480.0,
  "call_wall": 490.0,
  "put_wall": 470.0,
  "net_dex": -1.2e8,
  "net_vex": 4.5e7,
  "net_chex": 2.1e6,
  "vex_interpretation": "vol_down_dealers_buy",
  "chex_interpretation": "time_decay_dealers_buy",
  "dealer_shares_to_trade_up": -850000,
  "dealer_shares_to_trade_down": 920000,
  "oi_weighted_dte": 12.3,
  "zero_dte_magnet": 482.0
}
```

Reading this example:
- Positive gamma regime (net_gex positive, spot presumably above 480 flip)
- Call wall at 490 = ceiling. Put wall at 470 = floor.
- VEX: if IV falls, dealers buy (bullish mechanical flow)
- CHEX: time passing causes dealers to buy (supportive into close)
- Dealer hedging: on +1% move, dealers sell 850K shares (dampening). On -1%, they buy 920K (supporting).
- OI-weighted DTE of 12.3 = near-term positioning, gamma-sensitive environment
