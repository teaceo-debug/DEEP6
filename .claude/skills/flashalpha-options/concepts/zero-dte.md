# Zero-DTE Analytics — Pin Risk, Expected Move, Charm Regime, Gamma Acceleration

Zero-days-to-expiry (0DTE) options have transformed modern equity market microstructure. They now account for 40-50% of SPX/SPY options volume on expiration days. Their extreme gamma creates mechanical flows that dominate intraday price action.

---

## Why 0DTE Is Different

Standard options have days or weeks for gamma to decay. 0DTE options have hours. This creates:

1. **Extreme gamma near ATM** — gamma is inversely proportional to time. At expiry, ATM gamma approaches infinity.
2. **Rapid delta changes** — a small spot move causes massive delta swings in 0DTE options.
3. **Dealer hedging dominance** — dealers must rebalance continuously, creating mechanical flows that can overwhelm fundamental price discovery.
4. **Pin gravity** — high-OI strikes become gravitational attractors as expiry approaches.

---

## Expected Move

### Full-day expected move

```
implied_1sd_dollars ≈ ATM_straddle_mid_price
                    ≈ ATM_IV × S × √(T/252)
```

Where T = 1 (one trading day), S = spot price.

This is the market's implied 1-standard-deviation range for the entire session. Roughly 68% of sessions should close within this range (assuming log-normal returns, which is an approximation).

**FlashAlpha field:** `implied_1sd_dollars`

### Remaining expected move (intraday)

```
remaining_1sd_dollars = implied_1sd_dollars × √(hours_remaining / 6.5)
```

Scales the full-day move to the time remaining in the session. This is the more useful number intraday.

**FlashAlpha fields:**
- `remaining_1sd_dollars` — scaled to time remaining
- `upper_bound` = spot + remaining_1sd_dollars
- `lower_bound` = spot - remaining_1sd_dollars

### Interpretation

If pin_score > 50, price tends to stay INSIDE the expected move bounds. The expected move is not a prediction — it's the market's priced-in range. Moves outside it are statistically unusual but not impossible.

When spot is near the upper or lower bound with high pin score, the probability of reversal increases mechanically (dealers are long gamma at those strikes, creating resistance/support).

---

## Pin Risk Score (0-100)

The pin risk score is a composite measure of how strongly price is being pulled toward the magnet strike.

### Sub-components

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| OI concentration | 30% | How clustered is open interest near spot? High concentration = strong pin. |
| Proximity to magnet | 25% | How close is spot to the highest-OI strike? Closer = stronger pull. |
| Time remaining | 25% | Less time = stronger pin. < 2 hours = maximum pin force. |
| Gamma magnitude | 20% | Larger absolute gamma at magnet strike = stronger mechanical force. |

### Score interpretation

| Score | Regime | Behavior |
|-------|--------|----------|
| > 70 | Strong pin | Price likely to stay near magnet strike. Expect range compression. |
| 40-70 | Moderate pin | Some gravitational pull but breakouts possible. |
| < 40 | Weak pin | Little pinning force. Price free to trend. |

### FlashAlpha fields

- `pin_score` — composite 0-100 score
- `magnet_strike` — the specific strike exerting gravitational pull
- `pin_probability` — probability estimate of closing at/near magnet (related to max pain)

---

## Magnet Strike

The strike with the highest 0DTE net GEX magnitude near spot. This is the single strike where dealer gamma hedging is most concentrated.

As expiry approaches, the magnet strike becomes increasingly powerful:
- Dealers at this strike must hedge aggressively in both directions
- Any move away from the strike triggers immediate counter-hedging
- The result: price oscillates around the magnet, getting pulled back repeatedly

**FlashAlpha field:** `magnet_strike` in both zero_dte and exposure_levels responses.

### Magnet vs. max pain

These are related but different:
- **Magnet strike**: highest gamma concentration. Mechanical force from dealer hedging.
- **Max pain**: strike where total option value is minimized. Theoretical "where market makers want price to close."

In practice, the magnet strike is more reliable intraday because it's based on actual gamma mechanics, not theoretical pain calculations.

---

## Gamma Acceleration

```
gamma_acceleration = 0DTE_ATM_gamma / equivalent_7DTE_ATM_gamma
```

Measures how much more gamma-sensitive the market is today vs. a "normal" day.

### Typical values

- Normal day (no expiry): 1.0 (baseline)
- Expiry day, early session: 3-5x
- Expiry day, final 2 hours: 7-15x
- Expiry day, final 30 minutes: can exceed 20x

### Why it matters

Higher gamma acceleration = more violent dealer hedging per unit of spot movement. A 0.1% spot move on a day with gamma_acceleration = 10 creates the same dealer hedging flow as a 1% move on a normal day.

This is why expiration days can have explosive intraday moves that seem disconnected from news or fundamentals. The moves are mechanical.

**FlashAlpha field:** `gamma_acceleration`

---

## Theta Decay (0DTE)

### Net theta dollars

```
net_theta_dollars = Σ(theta × OI × 100) across all 0DTE contracts
```

Total dollar value bleeding out of 0DTE options per day. This is the total premium that option sellers collect (and buyers lose) over the session.

**FlashAlpha field:** `net_theta_dollars`

### Theta per hour remaining

```
theta_per_hour_remaining = net_theta_dollars / hours_remaining
```

How many dollars of option premium decay per hour of remaining session. This accelerates as expiry approaches (theta is not linear — it accelerates near expiry).

**FlashAlpha field:** `theta_per_hour_remaining`

### Dealer implications

Option sellers (who collected premium) benefit from theta. But dealers who are short options must manage the resulting delta changes as theta decays. This is the charm effect — theta and charm are mathematically linked (charm = ∂theta/∂S, or equivalently ∂delta/∂t).

---

## Charm Regime (0DTE)

Charm is the rate of delta change with time. On 0DTE, charm is extreme.

### Mechanics

For a call option near ATM:
- As time passes with spot above strike: delta decays toward 0.5 (from above)
- As time passes with spot below strike: delta decays toward 0 (from above)

For dealers short those calls:
- Their short delta position changes as charm acts
- They must continuously rebalance

### Charm regime interpretation

**`time_decay_dealers_buy`:** As time passes, dealer net delta decreases (becomes less positive or more negative). To stay delta-neutral, dealers must BUY underlying. This creates a mechanical bid that strengthens into the close.

**`time_decay_dealers_sell`:** As time passes, dealer net delta increases. Dealers must SELL. This creates mechanical selling pressure into the close.

The charm regime can reverse intraday if spot crosses key strikes. A session that starts with `time_decay_dealers_buy` can flip to `time_decay_dealers_sell` if spot drops below the dominant put strikes.

**FlashAlpha fields:**
- `charm_regime` — "time_decay_dealers_buy" or "time_decay_dealers_sell"
- `net_chex_0dte` — charm exposure from 0DTE contracts only

---

## 0DTE Flow Metrics

### Volume ratios

- `call_volume` — total 0DTE call contracts traded
- `put_volume` — total 0DTE put contracts traded
- `pc_ratio_volume` = put_volume / call_volume
  - < 1.0 = call-heavy = bullish sentiment
  - > 1.0 = put-heavy = bearish sentiment
  - > 2.0 = extreme put buying = fear or hedging

### OI ratios

- `pc_ratio_oi` = put OI / call OI
  - Structural positioning (slower-moving than volume ratio)
  - High put OI = structural hedging demand = put wall support

### ATM concentration

- `atm_volume_share_pct` — what % of 0DTE volume is at ATM strikes
  - High (> 40%) = market makers are focused on ATM. Pin risk elevated.
  - Low (< 20%) = volume spread across strikes. Less pin gravity.

---

## 0DTE Intraday Timeline

Understanding how 0DTE mechanics evolve through the session:

### Open (9:30-10:30 ET)
- Gamma acceleration moderate (3-5x)
- Expected move full-day range active
- Pin score typically low (< 40) — too much time for pinning
- Charm effect minimal

### Midday (10:30-14:00 ET)
- Gamma acceleration building (5-8x)
- Remaining expected move shrinking
- Pin score rising if spot near magnet
- Charm flows becoming noticeable

### Power hour (14:00-15:00 ET)
- Gamma acceleration high (8-12x)
- Pin score often > 50 if near magnet
- Charm flows significant
- Dealer hedging dominates price action

### Final 30 minutes (15:30-16:00 ET)
- Gamma acceleration extreme (15-25x)
- Pin score often > 70 near magnet
- Charm flows at maximum
- Price frequently "snaps" to magnet strike
- Expected move bounds act as hard walls

---

## Common 0DTE Patterns

### The pin

Conditions: pin_score > 60, spot within 0.3% of magnet_strike, < 2 hours to close.

Behavior: price oscillates tightly around magnet. Each move away triggers dealer counter-hedging that pulls it back. Range compresses into close.

### The gamma squeeze

Conditions: negative gamma regime, spot breaks through call wall or put wall.

Behavior: dealers must buy (on upside break) or sell (on downside break) to rebalance. This accelerates the move. The further from the wall, the more dealers must trade. Self-reinforcing until a new equilibrium.

### The vol crush rally

Conditions: post-event (FOMC, earnings), IV compresses rapidly, positive VEX.

Behavior: falling IV triggers vanna rebalancing. Dealers buy underlying mechanically. Price rallies even if the news was neutral. The rally is proportional to `net_vex × Δσ`.

### The charm drift

Conditions: positive CHEX, afternoon session, spot near ATM.

Behavior: time passing causes dealers to buy. Price drifts higher into close without obvious catalyst. Strongest in final 2 hours.
