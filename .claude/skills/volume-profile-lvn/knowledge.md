# Volume Profile & LVN — Master Knowledge Index

**Skill ID:** `volume-profile-lvn`
**Version:** 1.0.0
**Status:** Active
**Last verified:** 2026-05-25

## Purpose

This skill encodes institutional-grade Volume Profile and Low Volume Node (LVN) trading methodology for NQ futures. It bridges auction market theory (Steidlmayer/Dalton) with modern order flow analysis, GEX regime filtering, and quantitative evidence to produce codifiable trading rules. Every strategy has discrete entry/exit criteria suitable for DEEP6's 44-signal engine.

## Core Thesis

1. **LVN = Rejected Price, Not Random Noise** — LVNs form when the auction process fails to find two-sided agreement. They mark structural inefficiency.
2. **LVN Behavior is Regime-Dependent** — In positive gamma, LVNs are mean-reversion zones (fade breaks). In negative gamma, LVNs are acceleration zones (trade breaks). Never trade LVN without knowing the gamma regime.
3. **LVN is Context, Not Edge** — Academic evidence (Mesfin 2026) shows standalone OHLCV patterns fail at 5-min resolution after friction. LVN's value is as a **confluence filter** amplifying order flow signals, not as a primary signal.
4. **First Touch Has Highest Probability** — LVN rejection probability: 1st touch ~70-80%, 2nd touch ~40-50%, 3rd+ touch <20%. The structural edge decays as new volume fills the trough.
5. **Order Flow Confirms, Profile Maps** — Volume Profile shows WHERE to look (macro structure). Order flow shows WHAT to do (micro confirmation). Neither works alone.

## The 5-Step LVN Decision Framework

Every LVN trade decision flows through ALL 5 steps sequentially. No shortcuts.

### Step 1: Identify Structure — "Where are the LVNs?"
**Load**: `reading/lvn-identification.md` + `reading/composite-profiles.md`

Build the volume profile map. Identify POC, VAH, VAL, HVN clusters, and LVN gaps. Score LVN quality (width, contrast, significance). Use composite profiles for structural LVN that persists across sessions. Mark naked VPOCs as magnets.

### Step 2: Classify Regime — "What gamma environment are we in?"
**Load**: `confluence/lvn-gex-regime.md`

Determine gamma regime (positive/negative) from GEX data. This ENTIRELY determines whether LVN is a fade zone or breakout zone. Check 0DTE gamma separately from full-chain. Identify call/put walls near LVN for amplified reactions.

### Step 3: Select Setup — "Which strategy fits this context?"
**Load**: `setups/` (select the matching setup file)

Match market conditions to one of 6 codified strategies:
- **Trending + negative gamma** → `setups/lvn-breakout-acceleration.md`
- **First touch + absorption visible** → `setups/lvn-rejection-fade.md`
- **Confirmed breakout, now pulling back** → `setups/lvn-retest-support.md`
- **Overnight gap through LVN** → `setups/lvn-gap-fill.md`
- **Institutional reload at prior LVN** → `setups/lvn-institutional-defense.md`
- **AMT trend/reversion context** → `setups/amt-trend-reversion.md`

### Step 4: Confirm with Order Flow — "Does the footprint agree?"
**Load**: `confluence/lvn-order-flow.md` + `confluence/a-plus-setup.md`

Check absorption, delta divergence, stacked imbalances, and CVD at the LVN zone. An A+ setup requires ALL THREE: VP level + footprint confirmation + CVD signal. Without order flow confirmation, do not enter.

### Step 5: Execute with Risk Controls — "Where is stop, target, and session filter?"
**Load**: `risk/stop-placement.md` + `risk/session-filters.md`

Place stops beyond HVN edges (NEVER inside LVN). Target next HVN. Apply time-of-day filters (optimal: 10:30 AM - 2:00 PM ET). Check R:R minimum (2:1). Size position based on stop distance.

## Query Routing Map

### Foundations (Theory & Evidence)
- "What is auction market theory?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\foundations\auction-market-theory.md`
- "Why do LVNs form? What do they mean structurally?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\foundations\lvn-structural-significance.md`
- "Is there statistical evidence for VP trading edge?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\foundations\academic-evidence.md`

### Reading Volume Profile (Identification & Analysis)
- "What are VP profile shapes (D, P, b, B)?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\reading\profile-shapes.md`
- "How do I identify and score LVN quality?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\reading\lvn-identification.md`
- "How do composite/multi-session profiles work?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\reading\composite-profiles.md`
- "What is value migration, naked VPOC?" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\reading\value-migration.md`

### Trading Setups (Codified Strategies)
- "LVN breakout acceleration" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\lvn-breakout-acceleration.md`
- "LVN rejection/fade (first touch)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\lvn-rejection-fade.md`
- "LVN retest as S/R after breakout" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\lvn-retest-support.md`
- "Overnight gap-fill through LVN" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\lvn-gap-fill.md`
- "Institutional defense/reload at LVN" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\lvn-institutional-defense.md`
- "AMT trend continuation + mean reversion" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\setups\amt-trend-reversion.md`

### Confluence (Multi-Signal Integration)
- "LVN + order flow (absorption, delta, imbalances)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\confluence\lvn-order-flow.md`
- "LVN + GEX regime (positive/negative gamma)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\confluence\lvn-gex-regime.md`
- "LVN + 0DTE gamma (intraday amplification)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\confluence\lvn-0dte-gamma.md`
- "A+ setup criteria (triple confluence)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\confluence\a-plus-setup.md`

### Implementation (Code & Integration)
- "Python Volume Profile algorithms (KDE, extrema, GMM)" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\implementation\python-algorithms.md`
- "Pine Script VP/LVN patterns" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\implementation\pine-script-patterns.md`
- "DEEP6 existing VP engine integration" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\implementation\deep6-integration.md`

### Risk Management
- "Stop placement for LVN trades" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\risk\stop-placement.md`
- "Session and time-of-day filters" → `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\risk\session-filters.md`

## Strategy Summary Table

| Strategy | Best For | Entry | Stop | Target | R:R | Regime |
|----------|----------|-------|------|--------|-----|--------|
| **LVN Breakout** | Trending + neg gamma | Break + 1.5x vol | Inside LVN | Next HVN | 3:1-5:1 | Negative gamma |
| **LVN Rejection Fade** | 1st touch only | Rejection at edge | Beyond LVN | POC/VA | 1:2-1:3 | Positive gamma |
| **LVN Retest S/R** | Confirmed breakouts | Retest bounce | Prior VA | Next HVN | 2:1-3:1 | Either |
| **LVN Gap Fill** | Overnight gaps | Return to LVN | Beyond LVN | Opposite HVN | 2:1-3:1 | Either |
| **Institutional Defense** | Reload setups | OF confirm at LVN | Below LVN | HOD/LOD | 2:1-3:1 | Either |
| **AMT Trend/Reversion** | Balance/imbalance | LVN + aggression | 5-10% risk | Prior POC | 2:1-3:1 | Either |

## File Inventory

### Root Files
- `SKILL.md` — entry point, triggers, workflow, dependencies
- `knowledge.md` — master index, routing map, decision framework (this file)

### foundations/ (3 files)
- `auction-market-theory.md` — AMT framework: balance/imbalance, price discovery, two-way auction
- `lvn-structural-significance.md` — Why LVNs form, rejection theory, single prints, poor highs/lows
- `academic-evidence.md` — Quantitative evidence review including Mesfin 2026 falsification

### reading/ (4 files)
- `profile-shapes.md` — D, P, b, B, Normal profile shapes and what they signal
- `lvn-identification.md` — LVN quality scoring, width rules, NQ-specific thresholds
- `composite-profiles.md` — Multi-session composites, structural LVN, session weighting
- `value-migration.md` — VPOC naked/tested, value migration direction, IB relationship

### setups/ (6 files)
- `lvn-breakout-acceleration.md` — High R:R breakout through thin zone
- `lvn-rejection-fade.md` — First-touch fade with structural decay rules
- `lvn-retest-support.md` — Broken LVN as new S/R on pullback
- `lvn-gap-fill.md` — Overnight gap-fill through LVN zones
- `lvn-institutional-defense.md` — Carmine defense + institutional reload patterns
- `amt-trend-reversion.md` — AMT-based trend continuation and mean reversion via LVN

### confluence/ (4 files)
- `lvn-order-flow.md` — Absorption, delta divergence, stacked imbalances, CVD at LVN
- `lvn-gex-regime.md` — Gamma regime filtering: positive = fade, negative = breakout
- `lvn-0dte-gamma.md` — 0DTE gamma amplification, final-hour effects, vanna/charm
- `a-plus-setup.md` — Triple-confluence criteria (VP level + footprint + CVD)

### implementation/ (3 files)
- `python-algorithms.md` — Extrema, KDE, GMM detection; streaming VP; py-market-profile
- `pine-script-patterns.md` — Built-in VP, LibVPrf, custom LVN detector, request.footprint()
- `deep6-integration.md` — Existing DEEP6 VP engine map and extension points

### risk/ (2 files)
- `stop-placement.md` — Stop rules: never inside LVN, HVN edge placement, R:R minimums
- `session-filters.md` — Time-of-day rules, RTH vs overnight, session-specific behavior
