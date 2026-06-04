# Options Bias Engine — Master Knowledge Document

## Purpose

The Options Bias Engine is a standalone directional bias system for NQ futures derived entirely from the options market. It synthesizes four independent data rivers — FlashAlpha (GEX/DEX/VEX/CHEX structure), Massive.com (options flow tape), Unusual Whales (dark pool + sweeps), and Rithmic MBO (NQ order book) — into a single directional bias with confidence scoring and trade setup recognition.

This system is SEPARATE from the DEEP6 44-signal microstructure engine. The 44 signals detect footprint events (absorption, exhaustion, imbalance, delta patterns). The Options Bias Engine tells you WHICH DIRECTION to trade and WHETHER to trust the setup given the current options landscape. They are complementary, not overlapping.

## Core Thesis

The options market is a LEADING indicator of the equity/futures market. It reveals:
- WHERE dealers are hedged (creating mechanical support/resistance via GEX walls)
- WHAT informed money is doing (via options flow, sweeps, dark pool prints)
- WHICH volatility regime the market is in (via IV structure, VIX, SKEW)
- WHETHER the order book confirms or contradicts the options story (via Rithmic MBO)

The Options Bias Engine extracts every ounce of directional information from these sources, synthesizes them through a structured 7-step decision framework, and outputs a bias with conviction level and reasoning.

## The Four Data Rivers

| Source | What It Provides | Update Method |
|--------|-----------------|---------------|
| **FlashAlpha** | GEX profile by strike, gamma flip, call/put walls, HVL, DEX, VEX, CHEX, regime classification, dealer hedging estimates | REST API, poll every 30-60 sec |
| **Massive.com** | Real-time options flow tape — every unusual trade with size, premium, bid/ask side, sentiment, OI context | REST API, poll every 10-15 sec |
| **Unusual Whales** | Dark pool prints, net premium flow, sweep alerts, institutional flow direction, block trades | REST API, poll every 20-30 sec |
| **Rithmic MBO** | Every individual order event on NQ — add, modify, cancel at 40+ price levels, 1,000+ events/sec | WebSocket stream, continuous |

## The 7-Step Decision Framework

Every decision flows through ALL seven steps sequentially. No shortcuts.

### Step 1: Regime Identification → "What world are we in?"
**Load**: `step1-regimes/regime-identification.md` first, then the specific regime playbook.

Seven regimes, each with completely different rules:
- **Regime A**: Positive gamma, price between walls → Range, mean-revert, fade extremes
- **Regime B**: Positive gamma, price at call wall → Ceiling test, bounce vs break
- **Regime C**: Positive gamma, price at put wall → Floor test, highest win-rate long
- **Regime D**: Negative gamma, price above flip → Unstable bullish, momentum with tight risk
- **Regime E**: Negative gamma, price below flip → Trending bear, short rallies, never buy dips
- **Regime F**: Pin regime (near expiry) → Fade moves away from pin strike
- **Regime G**: Pre-event → Generally no trade, wait for new regime post-event

Files: `step1-regimes/regime-a-positive-between.md` through `step1-regimes/regime-g-pre-event.md`
Transitions: `step1-regimes/regime-transitions.md`

### Step 2: Level Map → "Where are the walls, magnets, trapdoors?"
**Load**: `step2-levels/level-hierarchy.md` for priority rules by regime.

Build a ranked battlefield of options-derived levels. Priority depends on current regime.
- Call wall, put wall (FlashAlpha) — PRIMARY in positive gamma
- Gamma flip (FlashAlpha) — REGIME BOUNDARY, always critical
- 0DTE walls (derived from flow) — intraday, shift throughout session
- Expected move boundaries (derived from IV) — statistical edge
- Max pain, pin strike — gravitational pull near expiry
- Dark pool clusters (Unusual Whales) — institutional confirmation

Files: `step2-levels/wall-dynamics.md`, `step2-levels/gamma-flip-mechanics.md`, `step2-levels/expected-move-computation.md`

### Step 3: Flow Read → "What is money doing RIGHT NOW?"
**Load**: `step3-flow/flow-interpretation.md` for the six flow states.

Classify the current flow from Massive.com + Unusual Whales into one of six states:
- AGGRESSIVE BULLISH — call sweeps, escalating premium, all sources agree
- AGGRESSIVE BEARISH — put sweeps, escalating premium, all sources agree
- ACCUMULATION (Stealth Bullish) — dark pool buying, visible flow quiet, icebergs on bid
- DISTRIBUTION (Stealth Bearish) — dark pool selling, visible flow looks bullish, icebergs on ask
- HEDGING (Not Directional) — protective positioning, far OTM, long-dated, ignore for bias
- DEAD (No Signal) — sub $5M net premium, no sweeps, no blocks, NO TRADE

Files: `step3-flow/sweep-analysis.md`, `step3-flow/opening-vs-closing.md`, `step3-flow/expiry-intent.md`, `step3-flow/dark-pool-reading.md`

### Step 4: Cross-Validation → "Do all five rivers agree?"
**Load**: `step4-cross-validation/conviction-matrix.md`

Triangulate across FlashAlpha (structure) + Massive (flow) + Unusual Whales (dark) + Rithmic (book):
- 5/5 agree → MAXIMUM CONVICTION → Full size
- 4/5 agree → HIGH CONVICTION → Standard size
- 3/5 agree → MODERATE → Half size or wait
- 2/5 or fewer → NO TRADE

Special patterns: Distribution warning (flow bullish + dark bearish), Trap warning (structure positive + DOM thin).

Files: `step4-cross-validation/divergence-patterns.md`, `step4-cross-validation/distribution-accumulation.md`

### Step 5: Setup Match → "Does this match a known play?"
**Load**: The specific setup file when conditions match.

Eight defined trade setups from options data:
1. **Wall Bounce** — fade approach to wall in positive gamma (70-78% win rate)
2. **Wall Break** — break through wall with accelerating flow (55-60% WR, 2-3:1 R:R)
3. **Gamma Flip Cross** — regime transition trade (60-65% WR, 3-5:1 R:R)
4. **Vanna Rally/Selloff** — mechanical VIX-driven flow (65-70% WR)
5. **Charm Flow** — last 90 min time-decay mechanical flow (60-65% WR)
6. **Distribution/Accumulation Fade** — dark vs visible flow divergence (65-72% WR)
7. **Sweep Cascade** — 3+ sweeps same direction in 5 min (62-68% WR)
8. **Expected Move Fade** — price at EM boundary in positive gamma (68-73% WR)

Files: `step5-setups/wall-bounce.md` through `step5-setups/expected-move-fade.md`

### Step 6: Risk Gate → "Is there a reason NOT to trade?"
**Load**: `step6-risk/kill-switches.md`

Eight mandatory gates. ANY one failing = NO TRADE:
1. Regime clarity — can I identify the current regime?
2. Minimum conviction — 3+ rivers agree?
3. Flow is alive — meaningful options activity happening?
4. No event within 30 min — FOMC, CPI, NFP?
5. Not in first 5 minutes — opening noise
6. Not fighting the regime — direction opposes regime character?
7. Data freshness — all sources current?
8. Consecutive loss limit — 3 losses today = stop trading

Files: `step6-risk/position-sizing.md`, `step6-risk/session-limits.md`

### Step 7: Output → Bias + Direction + Levels + Confidence + Reasoning
**Load**: `step7-output/output-format.md`

Structured output with:
- Regime classification
- Quantitative bias score (-100 to +100)
- Per-source breakdown (structural, flow, dark, DOM scores)
- Active level map with priorities
- Matched setup (if any)
- Risk gate status
- Session narrative (human-readable synthesis)

Files: `step7-output/narrative-guidelines.md`

## Order Book Integration (Rithmic MBO)

The order book is the lie detector for every other signal. Options say "call wall at 21,350 should hold." The book tells you WHETHER IT ACTUALLY IS being defended.

**Load**: `order-book/` directory for the six order book signals:
- **OB-1: Level Defense Score** — resting orders, reload rate, icebergs at options levels
- **OB-2: Aggression Imbalance** — market buys vs sells, directional momentum
- **OB-3: Depth Asymmetry** — bid vs ask depth at current price and at options levels
- **OB-4: Iceberg Detection** — hidden orders at GEX levels (highest conviction signal)
- **OB-5: Book Depletion Velocity** — how fast resting orders get eaten (break vs absorb)
- **OB-6: Spoof Context** — fake orders near options levels, cross-reference with flow

## Domain Knowledge (Doctorate Level)

Deep theory documents for the AI to internalize. Not summaries — full knowledge at the level of a senior options market maker or quantitative researcher.

**Load from `domains/` directory:**
- `dealer-hedging-mechanics.md` — How MMs hedge, dynamic delta, inventory management, rebalancing
- `gex-theory.md` — Full GEX math, profile shapes, regime mechanics, the formula and its implications
- `dex-vex-chex.md` — Delta, vanna, charm exposure chains — the full Greek hedging cascade
- `zero-dte-mechanics.md` — 0DTE gamma explosion, intraday wall dynamics, theta decay, pin risk
- `opex-cycles.md` — Monthly, quarterly, weekly expiry effects on levels and signals
- `volatility-structure.md` — Term structure, skew, surface dynamics, VIX/VVIX/SKEW interpretation
- `nq-options-proxy.md` — QQQ/NDX as NQ proxy: ratio mapping, where it breaks, when to use which

## Data Architecture

```
FlashAlpha (poll 30-60s) ──→ LEVELS STATE (GEX walls, flip, regime, DEX/VEX/CHEX)
Massive.com (poll 10-15s) ──→ FLOW STATE (premium, sweeps, blocks, unusual trades)
Unusual Whales (poll 20-30s) ──→ DARK STATE (dark pool, institutional flow)
Rithmic MBO (stream) ──→ DOM STATE (40+ levels, icebergs, absorption, aggression)
                                │
                    ┌───────────┴───────────┐
                    │ OPTIONS BIAS ENGINE    │
                    │ Steps 1-7 sequential  │
                    │                       │
                    │ Quantitative: -100→+100 (code, sub-second)
                    │ Qualitative: Opus (AI, event-driven)
                    └───────────┬───────────┘
                                │
                    BIAS + DIRECTION + LEVELS + CONFIDENCE + REASONING
```

## Quantitative Bias Score Components

Continuously computed from state (code, not AI):

| Component | Source | Weight | Score Range |
|-----------|--------|--------|-------------|
| GEX regime | FlashAlpha | 15% | -100 to +100 |
| Wall position / magnet | FlashAlpha | 10% | -100 to +100 |
| DEX direction | FlashAlpha | 10% | -100 to +100 |
| VEX (vanna flow) | FlashAlpha + VIX | 10% | -100 to +100 |
| CHEX (charm flow) | FlashAlpha + time | 5% | -100 to +100 |
| Net premium direction | Massive.com | 15% | -100 to +100 |
| Sweep bias | Massive.com | 10% | -100 to +100 |
| Block direction | Massive.com | 5% | -100 to +100 |
| Dark pool direction | Unusual Whales | 10% | -100 to +100 |
| DOM confirmation | Rithmic MBO | 10% | -100 to +100 |

Total: weighted sum, clamped to -100 to +100.

## Opus Event Triggers

Opus is summoned on significant state changes, NOT on every tick:

| Trigger | Condition | Opus Action |
|---------|-----------|-------------|
| Regime transition | Gamma flip crossed spot | Full regime reassessment |
| Wall shift | Call/put wall moved 50+ NQ points | Update narrative + levels |
| Large sweep | $25M+ sweep detected | Evaluate: hedging or conviction? |
| Bias threshold | Score crossed ±50 | Confirm or challenge with context |
| Bias flip | Score changed sign | Full context review |
| VIX spike | VIX moved 1+ point | Reassess vanna/charm |
| Scheduled | Every 15 minutes | Session narrative update |

## Usage

When the Options Bias Engine skill is loaded:
1. Start with this file (knowledge.md) for the framework overview
2. Load the regime identification doc to classify current state
3. Load the specific regime playbook for current conditions
4. Load relevant setup docs when conditions match a pattern
5. Load domain docs when deeper theory is needed for a specific decision
6. ALWAYS cross-reference the order book signals when evaluating any level

## Critical Rules

1. NEVER take a trade without identifying the regime first
2. NEVER trust a single data source — always cross-validate
3. NEVER fight the regime (long in Regime E, short at put wall in Regime A)
4. ALWAYS check the order book at options levels before trading the level
5. ALWAYS run all 8 risk gates before any trade
6. The order book is the LIE DETECTOR for every options-derived signal
7. When flow (Massive) and dark (UW) disagree, trust dark pool
8. Icebergs at GEX levels are the highest conviction signal in the system
9. 0DTE walls MOVE — re-evaluate every 15-30 minutes
10. Three consecutive losses = stop trading for the session
