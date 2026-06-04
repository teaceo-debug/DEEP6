# Gamma Regime Playbook for NQ

## Positive Gamma Regime
**FA signal**: regime = "positive_gamma", spot above gamma_flip

**Dealer behavior**: Long gamma → dealers fade moves
- Price rallies → dealers sell → move dampened
- Price drops → dealers buy → move dampened
- Result: mean-reverting, range-bound action

**Trading mode**: RANGE / MEAN-REVERSION
- Buy at/near put wall in NQ | Sell at/near call wall in NQ
- Stops INSIDE the range (tight)
- Target: mean of range or opposite wall
- 0DTE: pin risk matters — magnet strikes will attract price
- Prefer: silver bullets at wall levels, not breakout chases

**Confirmation**: price bouncing repeatedly at walls, low realized vol

---

## Negative Gamma Regime
**FA signal**: regime = "negative_gamma", spot below gamma_flip

**Dealer behavior**: Short gamma → dealers amplify moves
- Price rallies → dealers buy more → momentum builds
- Price drops → dealers sell more → momentum builds
- Result: trending, volatile, breakout behavior

**Trading mode**: TREND / BREAKOUT
- Enter on breakout confirmation through key levels
- Do NOT fade the trend at walls (they break)
- Stops OUTSIDE recent structure (wider)
- Target: next major level (flip, prior day high/low)
- 0DTE: less pinning — gamma doesn't suppress as strongly

**Confirmation**: price breaking through walls with follow-through, expanding ranges

---

## Flip Zone (Stand Down)
**FA signal**: spot within 0.5% of gamma_flip in either direction

**Behavior**: Regime transition — highly unpredictable
- Dealers flip net exposure rapidly
- Gamma can change sign intraday
- Moves can reverse violently

**Trading mode**: STAND DOWN or MNQ only with tight stops
- No full-size trades in flip zone
- Wait for decisive break above or below flip
- If stuck in a position: honor stops aggressively

---

## 0DTE vs Full-Chain Divergence
**When 0DTE = positive gamma but full-chain = negative gamma:**
- Short-term: price suppressed near current level (0DTE dealers fading)
- Intraday: accumulating trend pressure from full-chain negative gamma
- Setup: choppy morning → accelerating move into PM when 0DTE expires
- Best entry: late AM after 0DTE gamma diminishes

**When 0DTE = negative gamma but full-chain = positive gamma:**
- Short-term volatility despite macro mean-reversion regime
- Watch for morning spike/washout then reversion
- Do not chase the morning move

---

## OPEX Week Rules
- Monday/Tuesday OPEX week: full-chain regime dominant, less 0DTE distortion
- Wednesday–Thursday: gamma decay accelerates, watch charm pressure
- **OPEX Friday PM (after 2 PM ET)**: reduce all position sizes 50%
  - Gamma crashes at expiry, unpredictable moves common
  - Dealers unwinding hedges mechanically, not directional

---

## FOMC Days
- Pre-FOMC: vol compressed, positive-gamma-like even in negative regime
- FOMC announcement: vol spike → if negative vanna: dealers sell → amplifies drop
- Post-FOMC: vol crush → if positive vanna: dealers buy → vanna rally
- Best trade: post-FOMC vanna rally when VEX shows vol_up_dealers_buy
