# Greeks — All 15 Sensitivities (First, Second, Third Order)

Greeks measure how an option's value changes with respect to various inputs. They're the language of options risk management. Market makers use them to hedge positions. Exposure analytics (GEX, VEX, CHEX) are aggregated Greeks scaled by open interest.

---

## First Order Greeks (Primary Sensitivities)

These measure direct sensitivity to a single input changing.

---

### Delta (Δ)

```
Δ = ∂V/∂S
```

Change in option value per $1 change in spot price.

**Range:**
- Call: 0 to +1 (deep OTM ≈ 0, deep ITM ≈ 1, ATM ≈ 0.5)
- Put: -1 to 0 (deep OTM ≈ 0, deep ITM ≈ -1, ATM ≈ -0.5)

**Interpretation:**
- Delta = 0.5 means the option moves $0.50 for every $1 spot move
- Delta also approximates the probability of expiring ITM (risk-neutral probability)
- ATM call delta ≈ 0.5 means roughly 50% chance of expiring ITM

**Dealer hedging:** Dealers who sold a call with delta 0.5 must buy 50 shares per contract (100 shares × 0.5) to be delta-neutral. As spot moves, delta changes (gamma), requiring continuous rebalancing.

**FlashAlpha:** `delta` per contract in optionquote response. Aggregated as DEX.

---

### Gamma (Γ)

```
Γ = ∂²V/∂S² = ∂Δ/∂S
```

Rate of delta change per $1 spot move. How fast delta is changing.

**Properties:**
- Always positive for long options (calls and puts)
- Highest at ATM, decreases as you move OTM or ITM
- Increases as expiry approaches (for ATM options)
- 0DTE ATM gamma can be 10-20x that of 30DTE ATM

**Interpretation:**
- Gamma = 0.05 means delta changes by 0.05 for every $1 spot move
- High gamma = option is very sensitive to spot moves = expensive to hedge
- Long gamma = you benefit from large moves (in either direction)
- Short gamma = you lose from large moves (you need spot to stay still)

**Dealer hedging:** Dealers short gamma must continuously rebalance delta as spot moves. In negative gamma regime, this rebalancing amplifies moves. In positive gamma, it dampens them.

**FlashAlpha:** `gamma` per contract. Aggregated as GEX.

---

### Theta (Θ)

```
Θ = ∂V/∂t
```

Change in option value per day of time passing (with all else equal).

**Properties:**
- Always negative for long options (time decay hurts buyers)
- Accelerates near expiry (theta is not linear)
- Highest for ATM options near expiry
- 0DTE theta is extreme — options lose most of their value in hours

**Interpretation:**
- Theta = -0.05 means the option loses $0.05 per day from time decay alone
- Option sellers collect theta. Option buyers pay it.
- Theta and gamma are inversely related: high gamma = high theta cost

**FlashAlpha:** `theta` per contract. Aggregated as net_theta_dollars in 0DTE analytics.

---

### Vega (ν)

```
ν = ∂V/∂σ
```

Change in option value per 1% (1 vol point) change in implied volatility.

**Properties:**
- Always positive for long options (higher IV = more valuable options)
- Highest for ATM options with longer expiry
- Decreases as expiry approaches (0DTE options have near-zero vega)
- Long vega = you benefit from IV increases

**Interpretation:**
- Vega = 0.10 means the option gains $0.10 if IV rises 1 vol point
- Long options are long vega. Short options are short vega.
- Vega is why options get expensive before events (IV rises) and cheap after (vol crush)

**FlashAlpha:** `vega` per contract in optionquote response.

---

### Rho (ρ)

```
ρ = ∂V/∂r
```

Change in option value per 1% change in the risk-free interest rate.

**Properties:**
- Calls: positive rho (higher rates = more valuable calls)
- Puts: negative rho (higher rates = less valuable puts)
- Usually the smallest first-order Greek in practice
- More important for long-dated options and in high-rate environments

**Interpretation:**
- Rho = 0.05 means the option gains $0.05 if rates rise 1%
- In normal rate environments, rho is often ignored for short-dated options
- Becomes relevant for LEAPS (1-2 year options) or when rates are volatile

**FlashAlpha:** `rho` per contract (available in Greeks compute endpoint).

---

## Second Order Greeks (Cross-Sensitivities)

These measure how first-order Greeks change with respect to another input. They drive the mechanical dealer flows that FlashAlpha's VEX and CHEX capture.

---

### Vanna

```
Vanna = ∂Δ/∂σ = ∂Vega/∂S
```

How delta changes when implied volatility changes. Equivalently, how vega changes when spot moves.

**This is the most important second-order Greek for understanding VEX.**

**Sign and behavior:**
- OTM call: positive vanna (when IV rises, delta increases toward 0.5)
- OTM put: negative vanna (when IV rises, delta decreases toward -0.5)
- Deep ITM options: vanna approaches zero (delta already near ±1)
- ATM options: vanna is near zero (delta already at ±0.5)

**Dealer hedging mechanics:**
When IV falls (vol crush):
- OTM calls lose delta (vanna effect). Dealers who sold them are less short delta. They must sell underlying to rebalance.
- OTM puts lose delta magnitude (become less negative). Dealers who sold them are less long delta. They must buy underlying to rebalance.

The net effect depends on the balance of call vs. put OI and their moneyness. This is what VEX captures.

**FlashAlpha:** `vanna` per contract. Aggregated as VEX. Per-strike vanna surface available on Alpha tier.

---

### Charm

```
Charm = ∂Δ/∂t = ∂Θ/∂S
```

How delta changes as time passes. Equivalently, how theta changes when spot moves.

**This is the most important second-order Greek for understanding CHEX.**

**Sign and behavior:**
- OTM call: negative charm (delta decays toward 0 as time passes)
- ITM call: positive charm (delta increases toward 1 as time passes)
- ATM call: charm is near zero but changes sign around ATM
- Puts: opposite signs to calls

**Dealer hedging mechanics:**
As time passes on expiration day:
- OTM options lose delta rapidly (charm effect)
- ITM options gain delta rapidly
- Dealers must continuously rebalance

The net direction of rebalancing (buy or sell) depends on the aggregate charm of all positions. This is what CHEX captures.

**FlashAlpha:** `charm` per contract. Aggregated as CHEX. 0DTE charm is extreme.

---

### Vomma (Volga)

```
Vomma = ∂Vega/∂σ = ∂²V/∂σ²
```

How vega changes when implied volatility changes. The convexity of vega.

**Properties:**
- Always positive for long options (vega increases as IV rises)
- Highest for OTM options (they have the most to gain from IV spikes)
- Long vomma = you benefit from large IV moves (vol-of-vol)

**Interpretation:**
- High vomma = option value accelerates as IV rises
- OTM options are long vomma — they benefit disproportionately from vol spikes
- Tail hedges (far OTM puts) have high vomma — they explode in value during crises

**FlashAlpha:** `vomma` per contract (available in advanced Greeks).

---

### Dual Delta

```
Dual Delta = ∂V/∂K
```

How option value changes with respect to the strike price.

**Properties:**
- Related to the risk-neutral probability of expiring ITM
- For a call: Dual Delta = -N(d2) (negative, since higher strike = less valuable call)
- For a put: Dual Delta = N(-d2) (positive, since higher strike = more valuable put)

**Interpretation:**
- Dual delta is used in digital option pricing
- It gives the probability-weighted payoff at expiry
- Less commonly used in practice than the other second-order Greeks

**FlashAlpha:** Available in advanced Greeks compute endpoint.

---

## Third Order and Advanced Greeks

These measure how second-order Greeks change. Used by sophisticated market makers for path-dependent hedging and risk management.

---

### Speed

```
Speed = ∂Γ/∂S = ∂³V/∂S³
```

How gamma changes when spot moves.

**Properties:**
- Positive for OTM options (gamma increases as spot approaches strike)
- Negative for ITM options (gamma decreases as spot moves away from strike)
- Zero at ATM (gamma is at its maximum there)

**Interpretation:**
- High speed = gamma is changing rapidly with spot moves
- Important for path-dependent hedging: a dealer's gamma exposure changes as spot moves
- 0DTE options have extreme speed near ATM

---

### Zomma

```
Zomma = ∂Γ/∂σ
```

How gamma changes when implied volatility changes.

**Properties:**
- Positive for OTM options (higher IV = more gamma)
- Negative for ITM options (higher IV = less gamma)
- Near zero for ATM options

**Interpretation:**
- Zomma measures the interaction between gamma and vanna
- When IV rises, OTM options gain gamma (zomma effect)
- Important for understanding how gamma exposure changes during vol events

---

### Color

```
Color = ∂Γ/∂t
```

How gamma changes as time passes. The rate of gamma decay.

**Properties:**
- Negative for most options (gamma decays as time passes, except near expiry for ATM)
- ATM options near expiry: color is positive (gamma accelerates into expiry)
- 0DTE color is extreme — gamma is changing rapidly hour by hour

**Interpretation:**
- Color tells you how fast your gamma exposure is changing
- On expiration day, ATM color is large and positive — gamma is accelerating
- This is why 0DTE options become increasingly explosive as the session progresses

---

### Ultima

```
Ultima = ∂Vomma/∂σ = ∂³V/∂σ³
```

Third-order volatility sensitivity. How vomma changes when IV changes.

**Properties:**
- Measures the convexity of vomma
- Relevant for vol arb desks and variance swap traders
- Rarely used in standard options analytics

**Interpretation:**
- High ultima = option value is highly sensitive to large IV moves
- Used in pricing exotic options and variance products
- FlashAlpha provides this on Alpha tier for advanced analytics

---

### Lambda (Λ) — Elasticity

```
Λ = (∂V/∂S) × (S/V) = Δ × S/V
```

The percentage change in option value per 1% change in spot price. Option leverage.

**Properties:**
- Always > 1 for options (options are leveraged instruments)
- Higher for OTM options (more leverage, more risk)
- Decreases as options go deeper ITM (less leverage, more like owning stock)

**Interpretation:**
- Lambda = 10 means the option gains 10% for every 1% spot move
- Useful for comparing leverage across different options
- High lambda = high leverage = high risk/reward

**FlashAlpha field:** `lambda` per contract.

---

### Veta

```
Veta = ∂Vega/∂t
```

How vega changes as time passes. The rate of vega decay.

**Properties:**
- Negative for most options (vega decays as time passes)
- Longer-dated options lose vega more slowly than shorter-dated
- Near expiry, vega approaches zero rapidly

**Interpretation:**
- Veta tells you how fast your vega exposure is decaying
- Important for calendar spread management
- Long-dated options (LEAPS) have slow veta — vega is stable over time
- Short-dated options have fast veta — vega disappears quickly

---

## Greeks in FlashAlpha API

### Compute your own (Free tier)

```
GET /v1/pricing/greeks
```

Provide: S, K, T, r, sigma. Returns all first and second order Greeks.

```python
greeks = fa.compute_greeks(
    spot=480.0,
    strike=485.0,
    dte=7,
    rate=0.05,
    iv=0.18,
    option_type="call"
)
# Returns: delta, gamma, theta, vega, rho, vanna, charm, vomma, ...
```

### Pre-computed per contract (Growth tier)

```
GET /v1/optionquote/{symbol}
```

Returns all Greeks pre-computed for every listed contract. Includes delta, gamma, theta, vega, rho, vanna, charm, lambda.

### Historical Greeks (Alpha tier)

```
GET https://historical.flashalpha.com/v1/optionquote/{symbol}?at=YYYY-MM-DDTHH:mm:ss
```

Same response shape as live, but for any historical timestamp.

### Per-strike vanna/charm surfaces (Alpha tier)

```
GET /v1/adv_volatility/{symbol}
```

Returns vanna and charm at every strike and expiration. Used to build the full VEX and CHEX surface, not just the net aggregate.

---

## Greeks Quick Reference

| Greek | Order | Formula | Drives |
|-------|-------|---------|--------|
| Delta | 1st | ∂V/∂S | DEX, dealer delta hedge |
| Gamma | 1st | ∂²V/∂S² | GEX, gamma regime |
| Theta | 1st | ∂V/∂t | 0DTE theta decay |
| Vega | 1st | ∂V/∂σ | IV sensitivity |
| Rho | 1st | ∂V/∂r | Rate sensitivity |
| Vanna | 2nd | ∂Δ/∂σ | VEX, vol crush flows |
| Charm | 2nd | ∂Δ/∂t | CHEX, time decay flows |
| Vomma | 2nd | ∂Vega/∂σ | Vol-of-vol sensitivity |
| Dual Delta | 2nd | ∂V/∂K | Risk-neutral probability |
| Speed | 3rd | ∂Γ/∂S | Path-dependent gamma |
| Zomma | 3rd | ∂Γ/∂σ | Gamma-vol interaction |
| Color | 3rd | ∂Γ/∂t | Gamma acceleration (0DTE) |
| Ultima | 3rd | ∂Vomma/∂σ | Vol arb, variance swaps |
| Lambda | — | Δ×S/V | Option leverage |
| Veta | — | ∂Vega/∂t | Vega decay rate |
