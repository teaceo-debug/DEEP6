# Trader Dale Footprint Chart — Master Knowledge Index

## Purpose

This skill encodes Trader Dale's complete Order Flow trading methodology into structured AI knowledge. It covers footprint chart reading, 5 standalone trading setups, 4 confirmation setups, trade management (TP/SL), and Volume Profile integration for S/R identification. The methodology is designed for intraday trading on futures (primarily currency futures and index futures like NQ/ES) using NinjaTrader 8 with TD Order Flow software.

## Core Philosophy

1. **Track institutional activity** — Order Flow shows executed orders (not pending), revealing where big money actually traded
2. **Trade from S/R zones** — Identify strong Support/Resistance using Volume Profile or Order Flow setups, then use OF confirmations to time entries
3. **Combine macro + micro** — Volume Profile shows the big picture (where institutions accumulated), Order Flow shows the micro detail (who's active right now)
4. **Two factors drive price from S/R** — (a) Position defenders aggressively protect their entries, (b) Opposing traders close positions to avoid fighting strong participants
5. **Trade first test only** — S/R zones work best on first touch; probability drops on retests

## Course Structure (40 Lessons, 8 Parts)

| Part | Topic | Lessons | Skill Files |
|------|-------|---------|-------------|
| 1 | NinjaTrader 8 Platform | 1-6 | (covered by nt8-expert skill) |
| 2 | Order Flow Software | 7-9 | `workspace/` |
| 3 | Trading Setups | 10-14 | `setups/` |
| 4 | Confirmations | 15-19 | `confirmations/` |
| 5 | Take Profit & Stop Loss | 20-23 | `risk/` |
| 6 | Live Trading Examples | 24-28 | (examples embedded in setup/confirmation files) |
| 7 | Volume Profile Basics | 29-31 | `volume-profile/` |
| 8 | VP Support & Resistance | 32-40 | `volume-profile/` |

## Query Routing Map

### Foundations (How Order Flow Works)
- "What is bid/ask in order flow?" → `foundations/passive-vs-active.md`
- "How do I read a footprint?" → `foundations/footprint-anatomy.md`
- "What is delta?" → `foundations/delta-and-cumulative-delta.md`
- "What are imbalances?" → `reading/imbalances.md`
- "Passive vs active/aggressive participants" → `foundations/passive-vs-active.md`

### Reading Order Flow (Pattern Recognition)
- "What are volume clusters?" → `reading/volume-clusters.md`
- "What are high volume nodes / multiple nodes?" → `reading/high-volume-nodes.md`
- "What are stacked imbalances?" → `reading/imbalances.md`
- "What is unfinished business / failed auction?" → `reading/unfinished-business.md`
- "What is the trades filter?" → `reading/trades-filter.md`
- "What does cumulative delta show?" → `foundations/delta-and-cumulative-delta.md`

### Trading Setups (Standalone Strategies)
- "Volume cluster setup" → `setups/volume-clusters.md`
- "Multiple nodes setup" → `setups/multiple-nodes.md`
- "Trades filter setup" → `setups/trades-filter.md`
- "Stacked imbalances setup" → `setups/stacked-imbalances.md`
- "Unfinished business setup" → `setups/unfinished-business.md`
- "What are Dale's trading setups?" → `setups/` (all files)

### Confirmation Setups (Entry Timing at S/R)
- "Big limit order confirmation" → `confirmations/limit-orders.md`
- "Absorption confirmation" → `confirmations/absorption.md`
- "Aggressive orders / delta confirmation" → `confirmations/aggressive-orders-delta.md`
- "Cumulative delta divergence" → `confirmations/cumulative-delta-divergence.md`
- "How to confirm a trade entry?" → `confirmations/` (all files)

### Risk Management (TP, SL, Trade Management)
- "Where to place take profit?" → `risk/take-profit.md`
- "How to trail stop loss with order flow?" → `risk/trailing.md`
- "Where to place stop loss?" → `risk/stop-loss.md`
- "Warning signals to exit?" → `risk/trailing.md` (warning signals section)

### Volume Profile (S/R Identification)
- "How to find support/resistance with volume profile?" → `volume-profile/overview.md`
- "Volume accumulation setup" → `volume-profile/accumulation-setup.md`
- "Trend setup with volume profile" → `volume-profile/trend-setup.md`
- "Rejection setup" → `volume-profile/rejection-setup.md`
- "Volume profile shapes (D, P, b, thin)" → `volume-profile/overview.md`

### Workspace & Software
- "How to set up OF workspace?" → `workspace/trading-workspace.md`
- "What timeframes to use?" → `workspace/trading-workspace.md`
- "Order flow settings" → `workspace/trading-workspace.md`

## Trading Framework (Sequential Decision Process)

When a trading opportunity arises, Dale's methodology follows this sequence:

### Step 1: Identify S/R Zone (Macro)
Use Volume Profile to find strong institutional S/R:
- **Volume Accumulation** — rotation before trend = strongest S/R
- **Trend Volume Cluster** — "bump" in thin profile during trend
- **Rejection Volume Cluster** — heavy volumes in aggressive price reversal

Load: `volume-profile/accumulation-setup.md`, `volume-profile/trend-setup.md`, `volume-profile/rejection-setup.md`

### Step 2: Wait for Price to Reach S/R Zone
Do not chase. Mark the zone and wait.

### Step 3: Look for OF Standalone Setup OR Confirmation
**Option A — Standalone OF setup** (no VP S/R needed):
- Volume Clusters (trend or rejection) → `setups/volume-clusters.md`
- Multiple Nodes → `setups/multiple-nodes.md`
- Trades Filter → `setups/trades-filter.md`
- Stacked Imbalances → `setups/stacked-imbalances.md`

**Option B — OF confirmation at VP S/R** (strongest confluence):
- Big Limit Orders → `confirmations/limit-orders.md`
- Absorption → `confirmations/absorption.md`
- Aggressive Orders + Delta → `confirmations/aggressive-orders-delta.md`
- Cumulative Delta Divergence → `confirmations/cumulative-delta-divergence.md`

### Step 4: Enter Trade
Direction determined by:
- Setup type (trend direction for volume clusters, rejection direction for rejections)
- Confirmation type (limit buy on bid = long confirmation, limit sell on ask = short confirmation)

### Step 5: Manage Trade
- **Take Profit**: Place before next heavy volume zone → `risk/take-profit.md`
- **Trailing**: Continue trailing while imbalances favor your direction → `risk/trailing.md`
- **Stop Loss**: Behind heavy volume zone or fixed 10-20% of ATR → `risk/stop-loss.md`
- **Warning signals**: Exit when OF signals go against your position → `risk/trailing.md`

## Critical Rules

1. **BID shows**: Aggressive Sellers OR Passive Buyers (both — you cannot distinguish with certainty)
2. **ASK shows**: Aggressive Buyers OR Passive Sellers (both — you cannot distinguish with certainty)
3. **Trade first test only** — Don't trade the same level twice
4. **S/R are ZONES, not exact levels** — Look for confirmations anywhere within the zone
5. **Heavy volumes = institutional activity** — Dark shading on volume cells = where big money traded
6. **Price follows Delta eventually** — When price and delta diverge, price will correct to match delta
7. **Unfinished Business = magnet** — Price tends to revisit and "fix" improperly formed highs/lows
8. **Imbalances signal aggression** — 300%+ ratio between bid/ask = one side dominating
9. **Best combo**: Confirmation #1/#2 (Limit/Absorption) FOLLOWED BY Confirmation #3 (Aggressive Orders) = snowball effect
10. **Recommended timeframes**: 30min for big picture + setups, 5min for confirmations + entries, 1min for cumulative delta

## File Inventory

### Core
- `SKILL.md` — Skill entry point and trigger phrases
- `knowledge.md` — This file (master index and routing)

### Foundations (3 files)
- `foundations/passive-vs-active.md` — Passive vs Active market participants, Bid/Ask mechanics
- `foundations/footprint-anatomy.md` — How to read a footprint bar: cells, colors, HVN, delta, summary panel
- `foundations/delta-and-cumulative-delta.md` — Delta calculation, cumulative delta, divergence theory

### Reading (4 files)
- `reading/volume-clusters.md` — Heavy volume areas, darker shading, institutional activity zones
- `reading/high-volume-nodes.md` — HVN (black outline), Multiple HVN (yellow), Double/Triple Nodes
- `reading/imbalances.md` — Imbalances (300% ratio), Stacked Imbalances (3+ stacked), S/R zones
- `reading/unfinished-business.md` — Failed auctions, market imperfections, magnet effect
- `reading/trades-filter.md` — Filtering noise, showing only institutional-size orders

### Setups (5 files)
- `setups/volume-clusters.md` — Setup #1: Volume Clusters in trend + rejection (standalone)
- `setups/multiple-nodes.md` — Setup #2: Multiple HVN alignment (standalone)
- `setups/trades-filter.md` — Setup #3: Big order tracking via filter (standalone)
- `setups/stacked-imbalances.md` — Setup #4: Stacked Imbalances as S/R (standalone)
- `setups/unfinished-business.md` — Setup #5: Unfinished Business as trade helper

### Confirmations (4 files)
- `confirmations/limit-orders.md` — Confirmation #1: Big Limit Orders at S/R zones
- `confirmations/absorption.md` — Confirmation #2: Absorption of momentum at S/R
- `confirmations/aggressive-orders-delta.md` — Confirmation #3: Aggressive participants + Delta
- `confirmations/cumulative-delta-divergence.md` — Confirmation #4: Price vs Cumulative Delta divergence

### Risk Management (3 files)
- `risk/take-profit.md` — Volume-based TP placement
- `risk/trailing.md` — Trailing with imbalances + warning signals to exit
- `risk/stop-loss.md` — Fixed SL, S/R-based SL, low-volume-area SL

### Volume Profile (4 files)
- `volume-profile/overview.md` — VP basics, shapes (D/P/b/thin), why VP matters
- `volume-profile/accumulation-setup.md` — VP Setup #1: Rotation before trend
- `volume-profile/trend-setup.md` — VP Setup #2: Volume Cluster bumps in trend
- `volume-profile/rejection-setup.md` — VP Setup #3: Heavy volumes in price rejection

### Workspace (1 file)
- `workspace/trading-workspace.md` — 4-chart layout, timeframes, settings, cell content modes

## Conventions

- Use absolute paths only.
- Keep `knowledge.md` as an index, not a knowledge dump.
- Route queries before writing content.
- Each setup/confirmation file includes: Definition, Logic, Step-by-step Rules, When to Use, NQ-Specific Notes.
- Last verified: 2026-05-20
