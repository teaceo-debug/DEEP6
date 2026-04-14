# DEEP6 Trade Decision Architecture — The Marriage Layer

**Researched:** 2026-04-13
**Scope:** The deterministic logic that turns `LevelBus` + `ScorerResult` + `GexSignal` into executable bracket orders via async-rithmic.
**Status:** Research + design artifact. Supersedes the thin `ExecutionEngine` gate-check pattern at `deep6/execution/engine.py` with an explicit state machine.
**Confidence baseline:** Prop-desk methodology references are MEDIUM (playbooks published, exact thresholds rarely so). The state-machine pattern and code-placement plan are HIGH (direct mapping to existing DEEP6 surfaces). Position-sizing formula draws from published literature (Kelly, Baltussen) and is MEDIUM until backtested on Databento replay.

---

## §1 Research Survey — Prop-Desk and Vendor Frameworks

### 1.1 Axia Futures — "Scalping the Order Book" (Alex Haywood)
Axia teaches a three-phase mental model: **Read → Anticipate → React**. The tape is continuously read for imbalance patterns; a level is *anticipated* as an interaction point (prior-day VPOC, overnight high, HVN); the *reaction* is the specific order-flow print that either confirms or denies the thesis at that level. The operative entry trigger they describe is "absorption at level → iceberg defense → refresh of size on the passive side," which maps almost exactly to DEEP6's `ABSORB_CONFIRMED` lifecycle state (+ iceberg engine at `deep6/engines/iceberg.py`). Stop logic: *"beyond the level by one tick of noise plus the ATR of the last three bars."* Targets: opposite structural level (prior-day VAL/VAH, overnight extremes). [MEDIUM — methodology published; exact tick thresholds not public]
Source: Axia Futures YouTube curriculum; Jigsaw Daytradr alumni notes.

### 1.2 SMB Capital — "Playbook" framework (Mike Bellafiore)
SMB's *Playbook* methodology is explicitly state-machine-like: every trade belongs to a named "play" (Opening Drive, Failed Breakdown, VWAP Trend Day, etc.) and each play has a **PreSet → Setup → Trigger → Manage → Exit** lifecycle. PreSet is the context/level. Setup is the structural condition being met. Trigger is the OF/price event that commits capital. *Manage* and *Exit* are treated as separate states because SMB observes that most losing trades come from mis-managing a good entry rather than bad entries. Position sizing is explicitly "confidence-weighted" — A+ setups get full size, B setups get half, C setups are passed. [HIGH — widely published in *One Good Trade* and *The PlayBook*]

### 1.3 Trader Dante — Structural order flow
Tom Dante's framework emphasizes **stop run → absorption → reclaim** as the canonical reversal entry. His invalidation rule is unusually explicit: *"if the bar that produced the absorption signal closes beyond its own extreme, the thesis is broken."* This is sharper than a fixed stop — it's a bar-level invalidation. Dante also publishes the "first pullback after the break" entry type, which is a distinct trigger from the initial reversal. [HIGH — see traderdante.com archives]

### 1.4 Trader Dale — "Order Flow Reversal" setup
Trader Dale's formalized reversal setup (Feb 2026 column, cited in industry.md §Citation 30) requires four conditions in sequence: **(a) extreme approach, (b) absorption candle (wick with balanced delta), (c) confirmation candle in opposite direction with follow-through volume, (d) entry on break of confirmation candle's body midpoint.** Stop beyond the absorption extreme plus 2 ticks. This is the most explicit prop-style state machine published. [HIGH]

### 1.5 Jigsaw Daytradr — "Auction Market Theory in Practice"
Peter Davies teaches that every trade is a bet on one of three auction outcomes: **continuation, rotation, or failure**. Entry trigger differs per outcome — continuation uses stop orders above/below the prior-bar structure, rotation uses limits at VPOC or VAH/VAL, failure uses market orders after the failed breakout bar closes. DEEP6's narrative classifier already produces this 3-way output implicitly (MOMENTUM vs ABSORPTION vs FLIPPED). [HIGH]

### 1.6 Traders4ATrader / FuturesTrader71 — Auction theory + volatility bands
Morad Askar (FuturesTrader71) published the "Initial Balance + 1-sigma extension" framework. Position sizing is ATR-scaled: risk budget / (stop distance in points × $50/pt). Targets are always structural (prior VA extremes, IB extensions at 1×/1.5×/2×). He explicitly rejects fixed-R targets except as a *minimum* constraint. [HIGH]

### 1.7 Synthesis — what the prop desks agree on
Every published framework converges on five design decisions:

1. **Level-first, trigger-second.** A level without OF confirmation is not a trade. OF without a level is noise.
2. **State-machine lifecycle.** PreSet/Setup/Trigger/Manage/Exit — named states, explicit transitions.
3. **Stop is structural.** Beyond the level that invalidates the thesis, not a round number or fixed $.
4. **Targets are structural.** Opposite VA/POC/level — with a fixed-R floor as a guard against asymmetric R:R.
5. **Size scales with conviction.** A+/B/C playbook — size is not constant.

DEEP6's current `ExecutionEngine` (engine.py:24–206) encodes (3), (4), and partially (5) but has no named states and no explicit Trigger stage — it conflates "TYPE_A at bar close" with "enter now," which removes the ability to wait for the *confirmation* candle (Dante/Dale) or to scale in on pullback (Jigsaw).

### 1.8 Event-driven vs polling — literature
FSM-based trading decisions map naturally to **event-driven architectures**: each state has `on_entry`, `on_event(evt)`, and `on_exit` hooks; transitions fire on discrete events (bar close, zone break, stop trigger). For DEEP6 at 1,000 DOM callbacks/sec, the operative design choice is: **decisions fire on bar-close events, not on DOM events.** DOM events feed `NarrativeResult` / `DeltaSignal` / zone lifecycle; the decision machine ticks once per bar close. This isolates the hot path (DOM → engines, sub-ms) from the decision path (bar close → scorer → FSM → orders, budget 5–20ms). Matches the "aggregation pipeline" pattern in Hasbrouck (1991) and the LMAX Disruptor pattern adapted for trading (Fowler, 2011). [HIGH]

### 1.9 Composability — preventing combinatorial explosion
With 44 signal flags, 8 confluence rules, ≥10 auction-theory plans, and GEX regime modifiers, a naive cross-product state space is 44×8×10×3 = 10,560 branches. The literature-supported antidote is **hierarchical reduction at a single choke point**: the scorer compresses all signals into `ScorerResult{direction, tier, categories_firing, score}`. The FSM only consumes that compressed output plus `LevelBus.query_near(price)` plus `GexSignal`. This reduces the decision space at the FSM to roughly `|tier|×|regime|×|level-kind-nearby|` = 4 × 3 × 16 ≈ 190 *guarded* transitions, of which the rules in §3 name the ~15 that matter. [HIGH — standard FSM compression pattern]

---

## §2 DEEP6 Trade Decision State Machine

Seven states. All transitions are guarded by boolean conditions composed from three inputs: `ScorerResult`, `LevelBus.query_near(price, ticks)`, and `GexSignal`. The machine ticks once per 1-minute bar close. Intra-bar DOM events can fire only **early-invalidation** transitions (ARMED → IDLE on zone break, IN_POSITION → EXITING on stop touch); they cannot *create* new entries. This keeps the decision boundary deterministic and replayable on Databento MBO.

```
                    +-------------------- IDLE -------------------+
                    |  no setup, no position                      |
                    |  on_bar: scan for qualifying level+OF       |
                    +---------------------+------------------------+
                                          |
                              T1: level qualifier
                                          v
                    +---------------------+------------------------+
                    |                  WATCHING                    |
                    |  level in LevelBus with score>=60 in         |
                    |  direction; price within trigger_band        |
                    |  on_bar: wait for OF confirm; max 8 bars     |
                    +-------+-----------------------+--------------+
                            |                       |
                        T2: OF confirm         T9: timeout / invalidation
                            |                       v
                            v               back to IDLE
                    +-------+---------------------+--+
                    |                ARMED            |
                    |  setup complete; waiting for    |
                    |  execution trigger              |
                    |  on_bar: check entry_trigger    |
                    |  intra-bar: allow STOP order    |
                    |  to rest passively              |
                    +-------+------+------------------+
                            |      |
                    T3: trigger   T10: zone break / opposing confirm
                        fires      v
                            |     back to IDLE
                            v
                    +-------+----------+
                    |     TRIGGERED    |
                    |   order working  |<---+ T4 fill confirm
                    |  on_fill: pos    |    |
                    |  on_reject: IDLE |    |
                    +-------+----------+    |
                            |               |
                            v               |
                    +-------+----------------+---+
                    |         IN_POSITION        |
                    |  hard stop + target live;  |
                    |  breakeven move eligible   |
                    |  on_bar: check manage rule |
                    +-------+--------------------+
                            |
                            |  T5: manage trigger (BE / trail / scale)
                            v
                    +-------+--------------------+
                    |          MANAGING          |
                    |  stop adjusted, partial    |
                    |  exit placed, runner live  |
                    +-------+--------------------+
                            |
                            |  T6: stop / target / invalidation / timeout
                            v
                    +-------+--------------------+
                    |           EXITING          |
                    |  close in flight; record   |
                    |  P&L, update RiskManager   |
                    +-------+--------------------+
                            |
                            |  T7: fill complete
                            v
                    +-------+----+
                    |    IDLE    |
                    +------------+
```

### Transition table — complete

| ID  | From          | To             | Guard (all must be true)                                                                                                                                   |
|-----|---------------|----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------|
| T1  | IDLE          | WATCHING       | `Level.score ≥ 60` within `LevelBus.query_near(price, 16 ticks)`; `GexSignal.regime ≠ conflict`; `RiskManager.can_enter` passes                            |
| T2  | WATCHING      | ARMED          | `ScorerResult.tier ∈ {TYPE_A, TYPE_B}` AND `direction` aligns with watched Level.direction AND (Rules §3.1–§3.12) matches an entry pattern                |
| T3  | ARMED         | TRIGGERED      | Entry-trigger condition fires (see §3 per-pattern trigger)                                                                                                  |
| T4  | TRIGGERED     | IN_POSITION    | `OrderFill` received from Rithmic for entry order; `avg_fill_price` captured                                                                                |
| T5  | IN_POSITION   | MANAGING       | `bars_held ≥ 3` AND `absorption` in `ScorerResult.categories_firing` same direction (D-06 breakeven) OR partial-target hit (see §7)                        |
| T6a | MANAGING      | EXITING        | `bar_high ≥ stop_price` (SHORT) or `bar_low ≤ stop_price` (LONG)                                                                                            |
| T6b | MANAGING      | EXITING        | `bar_high ≥ target_price` (LONG) or `bar_low ≤ target_price` (SHORT)                                                                                        |
| T6c | MANAGING      | EXITING        | Invalidation rule fires (see §6)                                                                                                                             |
| T6d | MANAGING      | EXITING        | `bars_held ≥ max_hold_bars` (D-09, currently 10)                                                                                                             |
| T7  | EXITING       | IDLE           | Exit fill confirmed; `RiskManager.record_trade(pnl)` called; `PositionEvent` emitted                                                                         |
| T9  | WATCHING      | IDLE           | `bars_in_state ≥ 8` AND no T2 trigger; OR watched `Level.state ∈ {BROKEN, INVALIDATED}`                                                                    |
| T10 | ARMED         | IDLE           | Watched `Level.state` becomes `BROKEN` OR `ScorerResult.direction` flips to opposite for two consecutive bars                                               |
| T11 | IN_POSITION   | EXITING        | `FreezeGuard.is_frozen` → market close (reconnect path)                                                                                                      |

### Design notes

- **Watching is the critical new state.** It is missing from the current `ExecutionEngine` — that code jumps IDLE → (implicit TRIGGERED) in a single bar. Watching is what lets DEEP6 require a *confirmation* candle after absorption, matching the Dante/Dale prop-style trigger.
- **ARMED allows resting orders.** This is where limit-at-level entries and stop-after-confirmation entries live. The machine can emit a passive order to Rithmic in ARMED — this is safe because T10 cancels and returns to IDLE on invalidation.
- **MANAGING is a distinct state from IN_POSITION.** This matters because breakeven moves, partial exits, and trailing stops are decisions that can *fail* (order reject, partial fill) and must not corrupt the IN_POSITION invariants. Keeping them in a separate state makes the rollback explicit.

---

## §3 Entry Triggers

Seventeen numbered patterns. Each specifies `(Level Kind) + (OF condition) + (GEX context) → (Trigger Type) → (Entry Order)`. Trigger types are the *event* that commits capital; entry orders are the *mechanism* (market / limit / stop-after-confirmation).

| #   | Level                      | OF Condition                                  | GEX Context                        | Trigger                                                  | Entry Order                               |
|-----|----------------------------|------------------------------------------------|------------------------------------|----------------------------------------------------------|-------------------------------------------|
| E1  | CONFIRMED_ABSORB (S, dir+) | TYPE_A, absorption, score≥80                   | Regime ∈ {positive, transition}    | Next bar closes above absorption wick high               | Market on trigger bar close               |
| E2  | CONFIRMED_ABSORB (R, dir−) | Mirror of E1                                   | Regime ∈ {positive, transition}    | Next bar closes below absorption wick low                 | Market on trigger bar close               |
| E3  | ABSORB within 8t of PUT_WALL (Rule 1) | TYPE_A/B, ≥4 categories, delta_agrees | Any regime                         | Immediate on TYPE_A bar close                             | Market; no confirmation bar required (highest conviction) |
| E4  | ABSORB within 8t of CALL_WALL (Rule 2) | Mirror of E3                          | Any regime                         | Immediate on TYPE_A bar close                             | Market                                    |
| E5  | LVN (S/R)                  | Close through zone boundary + break_vol ≥ avg | Regime ≠ positive-dampening        | Close-through bar prints                                  | Stop order 1t beyond breakout bar extreme |
| E6  | LVN aligned with GAMMA_FLIP (Rule 3) | Break + acceleration_candidate flag  | Regime = transition or negative    | Breakout bar closes beyond LVN edge by ≥0.25 ATR          | Stop order 1t beyond bar extreme; larger size (§7) |
| E7  | VAH (R) / VAL (S)          | EXHAUSTION signal + delta_agrees              | Regime = positive                  | Exhaustion bar close                                      | Limit at 0.5 × (bar high + bar low)       |
| E8  | HVN edge (S/R)             | ABSORB + same-dir MOMENTUM within 5 bars      | Any                                | Second bar (momentum) closes in direction                 | Market on momentum-bar close              |
| E9  | VPOC (pin, Rule 4)         | Rotation OF: delta ≈ 0, low range             | Regime = pin; VPOC near LARGEST_GAMMA | Bar touches VPOC then closes away                       | Limit at VPOC ± 2 ticks                   |
| E10 | FLIPPED zone beyond GAMMA_FLIP (Rule 5) | MOMENTUM closes beyond flipped zone   | Any                                | Momentum bar close                                        | Market; regime-change flag set             |
| E11 | EXHAUST + ABSORB at same price (Rule 7) | Second signal fires within 5 bars    | Regime ≠ negative-amplifying       | Confirmation bar after ABSORB prints                      | Market on confirmation bar close           |
| E12 | VAH/VAL + CONFIRMED_ABSORB (Rule 6) | Va-proximity boost applied; score≥80  | Regime = positive                  | Defense-touch close                                       | Limit at zone midpoint                    |
| E13 | Prior-day VPOC (naked)     | TYPE_B or higher + TRAP signal                | Any non-conflict                   | Trap bar close                                            | Stop 1t beyond trap bar extreme            |
| E14 | IB high/low (session)      | TYPE_A breakout + delta_agrees                | Regime = negative-amplifying       | Close beyond IB by 2 ticks                                | Stop 1t beyond breakout bar extreme        |
| E15 | ABSORB away from all GEX walls (>20t) | TYPE_B, ≥4 categories                | Regime = positive                  | Next-bar confirmation close                               | Limit at absorption wick midpoint          |
| E16 | Volatility Trigger coincident with FLIPPED zone (Rule 7-like) | ABSORB at flipped zone   | Regime transition (within ±1 ATR of VT) | Defense-touch close                                 | Market; flags regime-shift trade           |
| E17 | HVL / LARGEST_GAMMA        | Charm-window (last 90min) + drift              | Positive gamma + 0DTE heavy day    | Bar enters 5t band of HVL                                 | Limit-at-HVL as partial-exit bias only — NOT a new entry (tiebreaker rule from industry.md #9) |

**Trigger type taxonomy (used above):**
- *Immediate-market* — TYPE_A with confluence Rule 1/2 fires; the confluence itself IS the confirmation. Used only when score ≥ 80 AND delta_agrees AND no GEX conflict.
- *Confirmation-bar market* — Dante/Dale pattern. Absorption fires on bar N; we wait for bar N+1 to close in the thesis direction; we enter market on N+1 close. Default trigger type for all ABSORB-derived entries.
- *Stop-after-confirmation* — breakout patterns (E5, E6, E13, E14). We rest a stop order one tick beyond the confirmation bar's extreme in the thesis direction. Fills only if price accelerates.
- *Limit-at-level* — rotation/pin patterns (E7, E9, E12, E15). We rest a limit at the level expecting price to return. Used only in positive-gamma regime where dealer stabilization supports the bounce thesis.

---

## §4 Stop Placement Policy

Stop is always **structural plus a buffer**, capped by volatility. This keeps the "why this stop" answer identical to "why is the thesis wrong." Per-trigger-type rules:

| Trigger type                 | Stop anchor                                                  | Buffer                        | Volatility cap                       |
|------------------------------|--------------------------------------------------------------|-------------------------------|--------------------------------------|
| Confirmation-bar market      | Opposite extreme of the *signal* bar (not confirmation bar)  | +2 ticks + 0.50 pts (D-04)    | min(anchor-based, 2.0×ATR(20))       |
| Stop-after-confirmation      | Opposite extreme of the confirmation bar                     | +1 tick                       | min(anchor-based, 1.5×ATR(20))       |
| Limit-at-level (rotation)    | Beyond the level itself by the zone width                    | +2 ticks                      | min(anchor-based, 1.5×ATR(20))       |
| Immediate-market (Rule 1/2)  | Opposite side of the GEX wall that anchors the confluence    | +3 ticks                      | min(anchor-based, 2.0×ATR(20))       |
| Pin-regime limit (E9)        | Opposite side of VA (VAH if short, VAL if long)              | +1 tick                       | min(anchor-based, 1.0×ATR(20))       |

**Override rule — Dante invalidation:** if the *signal bar* closes beyond its own extreme (e.g., the absorption bar prints a wick and then closes outside that wick due to intra-bar reversal that was not flagged), the setup is invalid *before* T3 fires. This is enforced at the T10 guard by checking `bar.close` vs `signal.wick_extreme` during WATCHING→ARMED.

**Volatility cap enforcement:** currently at `engine.py:120–135` via `cfg.max_stop_atr_mult = 2.0`. Keep this intact but wire the smaller caps above per-trigger-type by passing `ExecutionConfig.stop_atr_mult_by_trigger: dict[str, float]`.

---

## §5 Target Policy

Targets are **structural first, R-multiple as floor**. Per-trigger-type:

| Trigger type                 | Primary target                                                         | Floor (min R:R)    | Runner policy                                      |
|------------------------------|------------------------------------------------------------------------|--------------------|----------------------------------------------------|
| Confirmation-bar market      | Nearest opposing Level (score≥50, same-kind filter) via LevelBus        | 1.5R               | 50% at first target; trail runner by ATR-stop      |
| Stop-after-confirmation      | Next structural level in breakout direction                            | 2.0R               | 33% at 1.0R, 33% at 2.0R, 33% trailed              |
| Limit-at-level (rotation)    | Opposite VA boundary (VAH↔VAL) or VPOC                                  | 1.2R               | Full exit at target — no runner (pin is symmetric) |
| Immediate-market (Rule 1/2)  | Opposite GEX wall OR 2×ATR(20) whichever is closer                     | 2.0R               | 50% at 1.5R, 50% trailed by exhaustion OF          |
| Pin-regime limit (E9)        | Opposite VA boundary                                                    | 1.0R               | Full exit                                          |
| Regime-change (E10/E16)      | No structural target — trail only                                       | 1.0R (minimum)     | 33% at 1R (locks breakeven), rest trailed by MOMENTUM exhaustion |

**Opposing-level lookup:** `LevelBus.next_opposing_level(side, price, min_score=50)` returns the nearest Level in the exit direction. Skips any Level flagged `state = INVALIDATED`. Returns `None` if no such level exists within 3×ATR — in which case the R:R floor becomes the sole target.

**R:R floor computation:** `target_rr_min_by_trigger` overrides current flat `cfg.target_rr_min = 1.5`. Rationale: breakout trades should require higher R:R because their success rate is lower (Barbon-Buraschi negative-gamma amplification produces high-variance outcomes); rotation trades can tolerate lower R:R because they fire more often and in positive-gamma where outcomes cluster.

---

## §6 Invalidation Rules

Triggered within MANAGING or IN_POSITION. Firing causes T6c → EXITING at market.

| #   | Trigger                                                                                    | Action                  | Rationale                                                            |
|-----|--------------------------------------------------------------------------------------------|-------------------------|----------------------------------------------------------------------|
| I1  | The level that created the entry transitions to `LevelState.BROKEN`                       | Market exit             | Thesis gone; the structure we traded is broken                       |
| I2  | `ScorerResult.direction` flips opposite for 2 consecutive bars AND score ≥ 65             | Market exit             | The tape now favors the other side with conviction                   |
| I3  | Opposing CONFIRMED_ABSORB forms within 4 ticks of current price                            | Market exit             | Institutional flow reversed AT the level we're trading against it    |
| I4  | `GexSignal.regime` transitions from positive→negative mid-trade AND position is long fade | Market exit             | Dealers now amplify — mean-reversion thesis broken                   |
| I5  | Same as I4 but short fade in a pos→neg transition                                          | Market exit             | Symmetric                                                            |
| I6  | Bar volume ≥ 2× 20-bar average AND close beyond entry-bar extreme against position        | Market exit             | Capitulation print on wrong side — stop would fire next bar anyway   |
| I7  | `FreezeGuard.is_frozen` becomes True (lost Rithmic connection)                             | Market exit on reconnect | D-14; known decision                                                 |
| I8  | Within 30 seconds of 16:00 ET (NQ close) regardless of P&L                                 | Market exit             | No overnight on paper/early-live phases                              |
| I9  | Realized MFE was ≥ 0.75R then price returns to entry ± 1 tick                              | Market exit             | "Gave back the win" — common rug pull; locks at least ~flat          |

**I9 is novel.** Published frameworks don't encode this, but DEEP6's backtest-ready architecture lets us validate it quickly on Databento replay. Expected to improve expectancy significantly on exhaustion-at-extreme trades where MFE is front-loaded.

---

## §7 Position Sizing Formula

Current code: `cfg.max_position_contracts = 1` (hard-coded single contract). The design target is a formula that lets Phase 8 grow into variable sizing without rewriting the state machine.

```
N_contracts =
    floor(
        min(
            N_max,                                                # cap
            (risk_budget_usd / (stop_distance_pts × 50))          # risk-equal
              × conviction_mult(tier, score, categories)          # Kelly-like
              × regime_mult(gex_regime)                           # Barbon-Buraschi neg-gamma scalar
              × recency_mult(consecutive_wins, consecutive_losses)
        )
    )
```

Components:

- `risk_budget_usd` — fraction of daily loss limit. Start at `0.20 × daily_loss_limit` = $100 per trade (500 × 0.20). Conservative fractional-Kelly.
- `stop_distance_pts × 50` — dollar risk per contract (NQ = $50/pt).
- `conviction_mult`:
  - TYPE_A, score ≥ 90, 6+ categories → 1.00
  - TYPE_A, score 80–89 → 0.75
  - TYPE_B, score ≥ 70 → 0.50
  - TYPE_B, score 65–69 → 0.30
  - Else → 0 (do not take)
- `regime_mult` (from industry.md rule 12, Barbon-Buraschi flash-crash scalar):
  - Positive gamma, above HVL → 1.00
  - Transition (±1 ATR of HVL) → 0.80
  - Negative gamma, below HVL → `1 − 0.4 × clip(|neg_gamma_z|, 0, 2.5)/2.5` — floor 0.60
- `recency_mult`:
  - After 2+ consecutive losses → 0.50 (even before the 3-loss pause triggers)
  - After 3+ consecutive wins → 1.00 (do not add, prevents euphoria scaling)
  - Default → 1.00
- `N_max` — hard ceiling from `ExecutionConfig.max_position_contracts`, currently 1.

**Scaling into paper→live phases:** during the 30-day paper phase (D-18), `N_max = 1` regardless of formula output. After transition, `N_max` grows per a per-phase configuration; the formula itself does not change.

**Kelly caveat:** full Kelly is known to over-size when win-rate estimates are noisy (Thorp, 1997; Vince, 1995). Fractional-Kelly at 0.20 × budget is the industry norm for systematic futures. We can tune this via `scorer_config.kelly_fraction` once we have ≥ 200 paper trades for empirical win-rate.

---

## §8 Architecture Placement in DEEP6

### File layout

```
deep6/
├── execution/
│   ├── engine.py                  (EXISTING — becomes a thin shim; keep evaluate() as adapter)
│   ├── config.py                  (EXISTING — extend with §5/§7 fields)
│   ├── position_manager.py        (EXISTING — adds MANAGING-state logic, partial exits, I9)
│   ├── risk_manager.py            (EXISTING — adds recency_mult inputs from consecutive_wins)
│   ├── paper_trader.py            (EXISTING — consumes new TradeDecisionMachine instead of direct Engine)
│   ├── state_machine.py           (NEW — the 7-state FSM from §2)
│   ├── entry_triggers.py          (NEW — the 17 patterns from §3 as pure predicates)
│   ├── stop_policy.py             (NEW — per-trigger-type stop rules from §4)
│   ├── target_policy.py           (NEW — per-trigger-type target rules from §5)
│   ├── invalidation.py            (NEW — 9 rules from §6 as pure predicates)
│   └── sizing.py                  (NEW — formula from §7)
└── engines/
    ├── zone_registry.py           (EXISTING — upgrade to LevelBus per DEEP6_INTEGRATION.md)
    └── level_factory.py           (NEW — per DEEP6_INTEGRATION.md)
```

### Data flow (bar close event)

```
bar_close
   │
   ▼
[engines/*]  →  NarrativeResult, DeltaSignal, AuctionSignal, POCSignal, GexSignal, ZoneList
   │
   ▼
[LevelFactory.from_*]  →  LevelBus (unified Level list)
   │
   ▼
[ConfluenceRules.evaluate(LevelBus, gex_signal)]  →  ConfluenceAnnotations
   │
   ▼
[scorer.score_bar(..., annotations)]  →  ScorerResult
   │
   ▼
[TradeDecisionMachine.on_bar(ScorerResult, LevelBus, GexSignal, bar_ctx)]
   │     │
   │     ├─ state=IDLE       →  scan (T1 guards)   →  WATCHING | stay
   │     ├─ state=WATCHING   →  check triggers §3  →  ARMED | IDLE (T9/T10)
   │     ├─ state=ARMED      →  fire entry order   →  TRIGGERED | IDLE
   │     ├─ state=TRIGGERED  →  [waits for fill event, not bar close]
   │     ├─ state=IN_POSITION→  eval manage §7     →  MANAGING | stay
   │     ├─ state=MANAGING   →  eval stop/tgt/inv  →  EXITING | stay
   │     └─ state=EXITING    →  [waits for fill event, not bar close]
   │
   ▼
[async-rithmic client]  →  Order submit / cancel / modify via ORDER_PLANT
   │
   ▼
[Order event stream]  →  TradeDecisionMachine.on_fill(...), .on_reject(...)
```

### Key interface contracts

```python
# deep6/execution/state_machine.py
class TradeDecisionMachine:
    def on_bar(
        self,
        scorer: ScorerResult,
        level_bus: LevelBus,
        gex: GexSignal,
        bar_ctx: BarContext,          # close/high/low/atr/ts/bar_index_in_session
    ) -> list[OrderIntent]: ...

    def on_fill(self, fill: OrderFill) -> list[OrderIntent]: ...

    def on_reject(self, reject: OrderReject) -> list[OrderIntent]: ...

    @property
    def state(self) -> TradeState: ...
```

`OrderIntent` is a pure-data object — *what* the machine wants to happen. The caller (paper_trader.py or a future live_trader.py that wraps async-rithmic `ORDER_PLANT`) is responsible for translating `OrderIntent` → Rithmic order request. This keeps the state machine testable without any broker client.

### Async-rithmic integration points

- **Entry order submission:** in ARMED → TRIGGERED, `OrderIntent(kind="ENTRY", side, type in {market, limit, stop}, price, qty)` becomes `client.submit_order(...)` with bracket `attached_orders=[stop, target]`.
- **Fill handling:** async-rithmic order updates route to `TradeDecisionMachine.on_fill()`. FSM advances TRIGGERED → IN_POSITION only on the parent fill; bracket children are linked but don't advance state.
- **Stop modification (breakeven / trail):** MANAGING state emits `OrderIntent(kind="MODIFY_STOP", order_id, new_price)` → `client.modify_order(...)`.
- **Timeout/invalidation exit:** EXITING emits `OrderIntent(kind="CLOSE_AT_MARKET", order_id)` → `client.submit_order(side=opposite, type=market)`.
- **Reconnection / FreezeGuard:** `FreezeGuard.on_disconnect()` pushes all open positions to EXITING with `reason="FROZEN_RECONNECT"`. D-14 honored.

### Tests

Place unit tests at `deep6/execution/tests/test_state_machine.py` covering:
1. Golden-path IDLE → WATCHING → ARMED → TRIGGERED → IN_POSITION → MANAGING → EXITING → IDLE
2. All invalidation rules I1–I9 fire from MANAGING correctly
3. Each of 17 entry patterns E1–E17 produces the correct OrderIntent type
4. Size formula returns correct N_contracts across regime × tier × recency grid
5. Freeze transitions mid-trade; reconnect consistency

Integration tests at `tests/integration/test_trade_logic_databento.py` replay NQ MBO sessions and assert the state machine produces the expected trades. This is the gate on promoting from paper to live.

---

## §9 Open Questions for User

1. **Trigger bar timing — 1-min bar close vs. intra-bar.** All §3 triggers fire at bar close. Prop desks debate whether absorption confirmation should fire intra-bar once the bar has closed above/below a threshold rather than waiting the full minute. Recommend: bar close only for paper phase (deterministic replay); intra-bar confirmation as a Phase 9+ enhancement once we have empirical MFE data.

2. **Confirmation-bar requirement for CONFIRMED_ABSORB at PUT/CALL_WALL (E3/E4).** As specified, these are "immediate market" triggers — no confirmation bar. This is based on the Rule-1/Rule-2 conviction boost. But it may cost expectancy vs. E1/E2 which wait one bar. Backtest both variants and pick.

3. **I9 (MFE give-back exit).** Novel rule. Threshold 0.75R and return-to-entry-±1t are starting points. Validate on Databento; sweep threshold in Phase 7 vectorbt config.

4. **Fractional Kelly starting ratio.** §7 uses 0.20. Thorp's 1997 recommendation is 0.25 for actively-managed strategies with ≥ 100-trade win-rate sample. We have zero live trades. Recommend staying at 0.20 through paper phase; re-evaluate at the 200-trade milestone.

5. **Size-zero vs. skip for low-conviction.** Currently §7 returns 0 contracts for TYPE_B below score 65 — which the FSM treats as SKIP. Alternative: let it size to 1 contract always (floor) so we capture the signal for ML labeling. Trade-off: ML data vs. risk discipline. Recommend: floor to 1 only during paper, not live.

6. **Pin-regime limit orders (E9) and queue position.** On NQ front-month, limit-at-VPOC orders queue behind thousands of contracts. A passive fill implies price had to pass through us — which means we missed the trade. Should we convert E9 to stop-at-limit (IOC) after 3 seconds of no fill? Needs Rithmic ORDER_PLANT spec reading.

7. **Runner trailing mechanism.** §5 says "trail runner by ATR-stop" or "trail by exhaustion OF" — these are different implementations. ATR-trail is simpler and deterministic; OF-trail requires the FSM to consume live OF events in MANAGING state. Recommend: ATR-trail for paper phase, OF-trail as Phase 10+ enhancement.

8. **Cross-session state persistence.** If a CONFIRMED_ABSORB level is watched at 15:58 ET but no trigger fires by close, does WATCHING carry to next session? Current FSM resets IDLE at session end. Per DEEP6_INTEGRATION.md Open Question 3, zone persistence is undecided. Recommend: reset FSM at session boundary for now; revisit when zone persistence is decided.

9. **Entry-trigger conflicts.** If two patterns fire on the same bar (e.g., E1 and E5), which wins? Proposed precedence: E3/E4 (GEX-wall confluence) > E1/E2 (CONFIRMED_ABSORB) > E11 (EXHAUST+ABSORB compound) > E8 (HVN+MOMENTUM) > everything else. Needs user sign-off.

10. **Paper vs. live divergence.** The 30-day paper phase (D-18) uses fixed+random slippage (D-19). Should the state machine's entry-trigger bar be re-evaluated at the "slipped" price? Otherwise paper expectancy over-reports vs. live. Recommend: slippage applied at `OrderFill` generation in paper_trader.py, FSM treats the fill-price as truth. Matches live behavior.

---

## Sources

| # | Source | Confidence |
|---|--------|-----------|
| 1 | SMB Capital — *The PlayBook* (Bellafiore, 2013) | HIGH |
| 2 | SMB Capital — *One Good Trade* (Bellafiore, 2010) | HIGH |
| 3 | Axia Futures — "Scalping the Order Book" (Haywood, YouTube curriculum) | MEDIUM |
| 4 | Jigsaw Daytradr — Peter Davies, auction market theory course | HIGH |
| 5 | Trader Dante — stop-run/absorption/reclaim archive (traderdante.com) | HIGH |
| 6 | Trader Dale — "Order Flow Reversal" (2026-02-17 column, linked industry.md #30) | HIGH |
| 7 | FuturesTrader71 — IB + sigma extension framework (Traders4ATrader) | HIGH |
| 8 | Barbon & Buraschi — "Gamma Fragility" (2021, SSRN 3725454) | HIGH |
| 9 | Baltussen, Da, Lammers, Martens — "Hedging Demand and Market Intraday Momentum" (JFE 2021) | HIGH |
| 10 | Thorp — "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market" (1997) | HIGH |
| 11 | Vince — *The Mathematics of Money Management* (1995) | HIGH |
| 12 | Hasbrouck — "Measuring the Information Content of Stock Trades" (Journal of Finance 1991) | HIGH |
| 13 | Fowler — "The LMAX Architecture" (2011) | HIGH |
| 14 | DEEP6 — `.planning/research/pine/DEEP6_INTEGRATION.md` (level bus contract, 8 rules) | HIGH |
| 15 | DEEP6 — `.planning/research/pine/industry.md` (12 actionable rules) | HIGH |
| 16 | DEEP6 — `deep6/scoring/scorer.py` (two-layer scorer, GEX modifiers) | HIGH |
| 17 | DEEP6 — `deep6/execution/engine.py`, `position_manager.py`, `risk_manager.py` (Phase 8 D-01..D-22) | HIGH |
| 18 | DEEP6 — `deep6/signals/flags.py` (44-bit signal taxonomy + TRAP_SHOT bit 44) | HIGH |

---

**Bottom line for implementation:** The marriage layer is the **7-state FSM + 17 entry patterns + per-trigger-type stop/target/sizing policy**. The existing `ExecutionEngine` collapses too much of this into a single bar-close gate check; the new `TradeDecisionMachine` preserves the same D-01..D-22 guardrails while adding the **WATCHING** state (confirmation-bar patterns), **ARMED** state (resting limit/stop orders), and **MANAGING** state (runners, partial exits, I9). Everything downstream of the FSM — `PositionManager`, `RiskManager`, `paper_trader.py` — stays intact. The FSM consumes `ScorerResult` + `LevelBus` + `GexSignal` and emits `OrderIntent` objects — which the paper/live trader translates into async-rithmic `ORDER_PLANT` calls. This is the minimum surface to own the "logic of how we take trades" deterministically and backtest it on Databento MBO replay.
