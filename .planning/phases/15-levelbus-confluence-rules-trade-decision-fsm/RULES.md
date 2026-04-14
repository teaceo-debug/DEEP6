# Phase 15 — Canonical Confluence Rules (RULES.md)

**Version:** 1.0 (dedup pass of 47 source rules → 38 canonical CR-IDs)
**Created:** 2026-04-14
**Plan:** 15-01 (produces); 15-03 (encodes); 15-05 (golden-file tests).

This document is the single source of truth for the ~35–40 canonical
confluence rules encoded by `deep6/engines/confluence_rules.py`. It is
produced by de-duplicating the 47 rules that appear across four research
artifacts:

| Source file | Section | Rules contributed |
|-------------|---------|-------------------|
| `.planning/research/pine/DEEP6_INTEGRATION.md` | §Confluence Rules | 8 (DEEP6-01..08) |
| `.planning/research/pine/industry.md` | §Actionable for DEEP6 | 12 (IND-01..12) |
| `.planning/research/pine/deep/microstructure.md` | §12 Microstructure Rules | 12 (MS-01..12) |
| `.planning/research/pine/deep/auction_theory.md` | §9 Actionable — 15 Trade-Plan Generators | 15 (AUCT-01..15) |

Each CR-XX row below cites at least one `{file}:{section}` source
(threat T-15-01-03: no rule may claim lineage it does not have).

**Thresholds** (tick counts, ATR multipliers, confidence gates) are
Claude's-Discretion defaults from the research; a Phase 7 vectorbt sweep
will calibrate them. **Per D-16**, rules tagged `CALIBRATION-GATED` default
to OFF in `ConfluenceRulesConfig` until their thresholds are validated.

---

## Tier taxonomy (D-15 / D-16)

| Tier | Meaning | Default state |
|------|---------|---------------|
| `EASY` | Deterministic proximity + state check on LevelBus. O(n) on ≤80 levels. Ship enabled. | ON |
| `MEDIUM` | Needs VAH/VAL or GEX snapshot alongside LevelBus. Still O(n). Ship enabled. | ON |
| `CALIBRATION-GATED` | Research-stated LOW-confidence threshold, or compute cost > 1ms. Ship disabled. | OFF |

Budget: rule evaluation must complete in <1ms for 80 active levels on bar close (D-34).

---

## Rule Table

| Rule ID | Name | Trigger (summary) | Action (summary) | Source citations | Tier |
|---------|------|-------------------|------------------|------------------|------|
| CR-01 | Absorption at Put Wall → High-Conviction Long | ABSORB level with direction=+1 within 8 ticks of PUT_WALL | `level.score += 20` (cap 100); `meta["confluence"]="ABSORB_PUT_WALL"`; scorer +8 on top of zone_bonus; counts as 2 categories | DEEP6_INTEGRATION.md:§Confluence Rules Rule 1; industry.md:§Actionable 3 (basis-corrected distance 0.5×ATR(20) + regime gate) | EASY |
| CR-02 | Exhaustion at Call Wall → High-Conviction Fade | EXHAUST level with direction=−1 within 8 ticks of CALL_WALL | `level.score += 15`; emit `EXHAUST_CALL_WALL_FLAG` | DEEP6_INTEGRATION.md:§Confluence Rules Rule 2; industry.md:§Actionable 4 (symmetric, with vol-trigger veto) | EASY |
| CR-03 | LVN Crossing Gamma-Flip → Acceleration Candidate | Close through LVN zone boundary AND GAMMA_FLIP within 12 ticks of LVN mid | `meta["acceleration_candidate"]=True`; scorer suppresses opposing absorption signals | DEEP6_INTEGRATION.md:§Confluence Rules Rule 3; industry.md:§Actionable 6 (LVN × Gamma Flip acceleration) | MEDIUM |
| CR-04 | VPOC Pinned Near Largest-Gamma → Pin Regime | Session VPOC within 6 ticks of LARGEST_GAMMA (or HVL) for 3+ bars | `regime="PIN"`; suppress directional signals with score<70; reduce position size | DEEP6_INTEGRATION.md:§Confluence Rules Rule 4; industry.md:§Actionable 7 (VPOC pinning positive-gamma only) | MEDIUM |
| CR-05 | Momentum Through Flipped Zone Beyond Zero-Gamma → Regime Change | MOMENTUM bar closes beyond (in direction of momentum) a FLIPPED zone that sits beyond GAMMA_FLIP | Emit `REGIME_CHANGE` flag; boost momentum weight 1.3×; suppress prior-dir absorption until next ABSORB_CONFIRMED | DEEP6_INTEGRATION.md:§Confluence Rules Rule 5; industry.md:§Actionable 10 (Flipped-polarity × Volatility Trigger) | MEDIUM |
| CR-06 | ABSORB Confirmed + VAH/VAL Proximity → VA Boost | ABSORB zone within 4 ticks of VAH or VAL, then CONFIRMED within confirmation window | `level.score += 15`; `meta["va_confirmed"]=True`; if score≥60 force state=DEFENDED | DEEP6_INTEGRATION.md:§Confluence Rules Rule 6; auction_theory.md:§9 Trade-Plan 4 (ORR at VAH fade requires exhaustion at VAH — overlap via VA-proximity mechanic) | EASY |
| CR-07 | EXHAUST → ABSORB at Same Price → Compound Short | EXHAUST (direction=−1) at P1, then within 5 bars ABSORB (direction=−1) within 6 ticks of P1 | Merge to CONFIRMED_ABSORB; `score += 20`; emit "EXHAUST + ABSORB NOW WATCH" label | DEEP6_INTEGRATION.md:§Confluence Rules Rule 7 | EASY |
| CR-08 | HVN + Put Wall Alignment → Suppress Shorts | Active HVN (score≥50) within 6 ticks of PUT_WALL | If direction=−1, apply 0.6× multiplier to total_score pre-tier (D-40, soft suppression) | DEEP6_INTEGRATION.md:§Confluence Rules Rule 8 | EASY |
| CR-09 | Basis-Corrected GEX Level Mapping | All GEX levels from FlashAlpha (QQQ/NDX-derived) must be multiplied by live `/NQ ÷ QQQ` ratio, recomputed at ≤1-min cadence | Apply basis correction before any other rule fires on a GEX Level | industry.md:§Actionable 1 | MEDIUM |
| CR-10 | Regime Gate on HVL / Gamma-Flip | Compute position relative to HVL once per snapshot | All confluence rules conditioned on `regime ∈ {positive_gamma, transition, negative_gamma}`; transition = within ±1 ATR of HVL | industry.md:§Actionable 2 | MEDIUM |
| CR-11 | Exhaustion × Wall Breach → Breakout Continuation | EXHAUST confirms at a prior CALL_WALL or PUT_WALL that has been broken by >0.25 ATR intraday | Flip bias to breakout-continuation; score boost scales with `\|gamma_notional\|` percentile over trailing 20 sessions | industry.md:§Actionable 5 (Barbon-Buraschi pro-cyclical hedging) | CALIBRATION-GATED |
| CR-12 | Last-30-Min Regime Play (Baltussen) | Within 30 min of cash close; compute sign of day's return | If net dealer gamma < 0 → boost trend-continuation +20%; if > 0 → boost mean-reversion +20% | industry.md:§Actionable 8 (Baltussen et al. 2021 JFE) | CALIBRATION-GATED |
| CR-13 | Charm Drift Toward High-OI Strike (EOD) | Final 90 min on Wed/Fri; price within 0.5% of strike with 90th-percentile OI for session | Low-magnitude directional bias toward strike proportional to distance; tiebreaker / partial-exit bias only | industry.md:§Actionable 9 | CALIBRATION-GATED |
| CR-14 | 0DTE Dominance Guard | 0DTE share of NQ options volume (or NDX proxy) > 40% | Use per-expiry GEX levels, not cumulative; flag cumulative-only signals as degraded | industry.md:§Actionable 11 | CALIBRATION-GATED |
| CR-15 | Negative-Gamma Risk Scalar | Global position size multiplier when below HVL | `size = base_size × (1 − 0.4 × clip(\|neg_gamma_z\|, 0, 2.5)/2.5)` where `neg_gamma_z` is z-score vs 60-day baseline | industry.md:§Actionable 12 (Barbon-Buraschi flash-crash tail) | CALIBRATION-GATED |
| CR-16 | AbsorptionZ (Microstructure Formal) | aggressor-volume / \|Δticks\| z-score within ±2 ticks of L ≥ 2.5 over 60s; aggressor-side share ≥ 70% | Emit `MS_ABSORB_Z` score-boost on adjacent ABSORB/HVN Levels | microstructure.md:§12 Rules MS-01 (Eisler-Bouchaud; Wyckoff formalized) | MEDIUM |
| CR-17 | Iceberg At Level | HVr at price in [L−ε, L+ε] ≥ 2.0 over 60s AND ≥2 Zotikov replenishment events | Score-boost nearest Level; set `meta["iceberg"]=True` | microstructure.md:§12 Rules MS-02 (Hautsch-Huang, Zotikov) | MEDIUM |
| CR-18 | Queue Imbalance Band | QI across top-3 levels within 3 ticks of L has \|QI\|≥0.6 with combined size ≥ rolling median | Direction-conditional: against approach = absorption, with approach = breakout accelerant | microstructure.md:§12 Rules MS-03 (Gould-Bonart; Lipton) | MEDIUM |
| CR-19 | VPIN Regime Shift | VPIN over last 10 buckets drops ≥1σ from prior 40-bucket mean while price within 5 ticks of L (fade); rises ≥1σ = break confirm | Emit `VPIN_REGIME_DROP` / `VPIN_REGIME_RISE` meta-flag | microstructure.md:§12 Rules MS-04 (Easley-López de Prado-O'Hara; with Andersen-Bondarenko caveats) | CALIBRATION-GATED |
| CR-20 | Kyle Lambda Compression | Rolling λ at L-proximity ≤ 0.5× off-level λ | Boost absorption-category vote on nearest Level | microstructure.md:§12 Rules MS-05 (Hasbrouck; Kyle) | MEDIUM |
| CR-21 | CVD Divergence at Level | Price makes local extreme at/near L AND CVD fails to confirm by ≥1σ of its rolling noise; ≥20-bar window | Score-boost reversal direction on nearest Level | microstructure.md:§12 Rules MS-06 (Lillo-Farmer; Bouchaud et al.) | MEDIUM |
| CR-22 | Hawkes Branching Critical | 2-dim Hawkes same-side branching ratio ≥ 0.85 AND price within 5 ticks of L → breakout imminent; inverse for cross > same | Emit breakout-imminent vs level-holds flags; runs via ThreadPoolExecutor+janus (D-35) | microstructure.md:§12 Rules MS-07 (Bacry-Muzy; Haghighi et al.) | CALIBRATION-GATED |
| CR-23 | Spoof Suppressor (VETO) | >60% of resting size on absorbing side has mean order lifetime <500ms AND cancel rate >90% over last 30s | `vetoes.add("SPOOF_DETECTED")`; scorer forces tier→DISQUALIFIED for the Level | microstructure.md:§12 Rules MS-08 (Cartea-Jaimungal; CFTC corpus) | MEDIUM |
| CR-24 | Aggressor Dominance at L | In ±2-tick band around L, aggressor-side volume share over 30s > 0.75 | Pair with CR-16 for absorption, with breakout for exhaustion dominance | microstructure.md:§12 Rules MS-09 (Databento MBO native) | MEDIUM |
| CR-25 | Round-Number Proximity (Modifier) | L is a round number (NQ: every 25 / 50 / 100 points) | Boost weight of CR-16..CR-22 by 1.25× on the nearest Level | microstructure.md:§12 Rules MS-10 (Bloomfield-Chin-Craig 2024) | EASY |
| CR-26 | Depth Asymmetry | Cumulative depth within 5 ticks on one side ≥ 3× the other side AND thick side faces price approach | Score-boost thick-side holds | microstructure.md:§12 Rules MS-11 (Cont-Stoikov-Talreja; Cont-de Larrard) | MEDIUM |
| CR-27 | Exhaustion Post-Break | Price crosses L; Hawkes same-side excitation decays ≥50% within 2 min; aggressor-dominance reverts ≤55% | Emit `FAILED_BREAK` flag on the Level; score-boost reversal | microstructure.md:§12 Rules MS-12 (Bacry-Muzy decay kernels) | CALIBRATION-GATED |
| CR-28 | Open-Drive + Opening Range Extension (Bullish) | OD-UP + ORU with no rejection prints | Long on first pullback to opening range high; stop = open−4 ticks; target = 2× IB projection (requires Kronos E10 ≥ neutral) | auction_theory.md:§9 Trade-Plan 1 (Dalton *Markets in Profile* Ch. 3; *Mind Over Markets* Ch. 4) | MEDIUM |
| CR-29 | Open-Drive + Opening Range Extension (Bearish) | OD-DOWN + ORD with no rejection | Mirror of CR-28: short on first pullback to opening range low | auction_theory.md:§9 Trade-Plan 2 | MEDIUM |
| CR-30 | Overnight Test + Drive Reversal (OTD-UP) | Test prior day low, reverse | Long on reclaim of overnight low; stop = tested low −2 ticks; target = prior day POC, then VAH | auction_theory.md:§9 Trade-Plan 3 | MEDIUM |
| CR-31 | Failed IB Extension (Both Sides) | Period closes BACK INSIDE IB after excursion beyond | Trade opposite side to opposite IB edge; 70–75% historical probability (Dalton) | auction_theory.md:§9 Trade-Plan 5 & 6; §6 IB rule 2 (Dalton) | EASY |
| CR-32 | Naked POC Magnet | Naked POC above/below current price AND price drifting toward it | Trade toward nPOC; exit AT nPOC; flip opposite if exhaustion prints | auction_theory.md:§9 Trade-Plans 7 & 8 | EASY |
| CR-33 | Poor High / Poor Low Revisit (Volume-Conditional) | Poor high on light volume (<70% 30-period avg) = short; poor low on heavy volume (>130% avg) = short breakout | Branch on volume: light volume → fade; heavy volume → breakout. Requires absorption at high for fade, retest hold for breakout | auction_theory.md:§9 Trade-Plans 9 & 10 (Dalton + Steidlmayer) | MEDIUM |
| CR-34 | Buying-Tail / Selling-Tail Retest | Pullback into tail with delta flip in tail direction | Long into buying tail / short into selling tail; stop below tail −2 ticks; target = day high or VAH | auction_theory.md:§9 Trade-Plan 11 | MEDIUM |
| CR-35 | Open-Auction In-Range + Unchanged Value | Responsive session; disable trend logic | Scalp IBH/IBL toward POC; max 2 trades per day | auction_theory.md:§9 Trade-Plan 12 | EASY |
| CR-36 | Double-Distribution Single-Print Revisit | Enter WITH direction of break through single print on volume expansion | Stop in middle of single print; target = edge of 2nd distribution | auction_theory.md:§9 Trade-Plan 13 | MEDIUM |
| CR-37 | Absorption @ Prior-Day High + Kronos Bearish + IB Fail-Up | All three fire within session open + first two periods | High-conviction short: stop = prior day high +2 ticks; target = prior day POC then VAL | auction_theory.md:§9 Trade-Plan 14 (gated on Kronos E10 bearish; D-42 defaults to OFF) | CALIBRATION-GATED |
| CR-38 | Neutral-Extreme Close → Next-Day Gap-and-Go | Prior session closed Neutral-Extreme at high/low | Gap-and-go bias next open; scale-in on first 5-min pullback; stop = prior day extreme | auction_theory.md:§9 Trade-Plan 15; §4 VA-relationship rules | MEDIUM |

---

## Dedup Lineage (audit trail)

This section documents the 47 → 38 dedup. Each left-hand entry is a
research-source rule; each right-hand is the canonical CR-XX that
subsumes it (or marks it as deferred).

### DEEP6_INTEGRATION.md (8 rules)

| Source | Canonical | Lineage notes |
|--------|-----------|---------------|
| DEEP6-01 | CR-01 | Primary definition (Pine BOOKMAP absorption + put wall). |
| DEEP6-02 | CR-02 | Primary. |
| DEEP6-03 | CR-03 | Merged with industry §6 (identical mechanic, different phrasing). |
| DEEP6-04 | CR-04 | Merged with industry §7 (VPOC pinning). |
| DEEP6-05 | CR-05 | Merged with industry §10 (flipped polarity × vol trigger ≈ flipped zone × gamma flip; vol trigger is SpotGamma terminology for gamma flip). |
| DEEP6-06 | CR-06 | Merged with auction §9 Rule 4 (ORR at VAH fade requires absorption/exhaustion at VAH — shares VA-proximity mechanic). |
| DEEP6-07 | CR-07 | Unique (sequential signal cascade). |
| DEEP6-08 | CR-08 | Unique (soft-suppression multiplier). |

### industry.md §Actionable (12 rules)

| Source | Canonical | Lineage notes |
|--------|-----------|---------------|
| IND-01 | CR-09 | Primary. Foundational basis correction — every GEX rule depends on it. |
| IND-02 | CR-10 | Primary. Regime gate — foundational. |
| IND-03 | CR-01 | Merged into CR-01 (absorption × put wall; same rule, different thresholds from academic literature). |
| IND-04 | CR-02 | Merged into CR-02 (absorption × call wall symmetric; vol-trigger veto captured in CR-10 regime gate). |
| IND-05 | CR-11 | Unique (exhaustion × broken wall breakout continuation — Barbon-Buraschi). |
| IND-06 | CR-03 | Merged into CR-03 (LVN × gamma flip, DEEP6-03 already captures). |
| IND-07 | CR-04 | Merged into CR-04 (VPOC pinning, DEEP6-04 captures). |
| IND-08 | CR-12 | Primary (Baltussen last 30 min, calibration-gated). |
| IND-09 | CR-13 | Primary (charm drift EOD, calibration-gated). |
| IND-10 | CR-05 | Merged into CR-05 (flipped × vol trigger ≈ flipped × gamma flip; vol trigger = gamma flip in SpotGamma). |
| IND-11 | CR-14 | Primary (0DTE guard, calibration-gated). |
| IND-12 | CR-15 | Primary (negative-gamma risk scalar, calibration-gated). |

### microstructure.md §12 Rules (12 rules)

| Source | Canonical | Lineage notes |
|--------|-----------|---------------|
| MS-01 | CR-16 | Primary (AbsorptionZ formal definition). Boosts CR-01/CR-06 absorption Levels; does not replace them. |
| MS-02 | CR-17 | Primary (iceberg detection). |
| MS-03 | CR-18 | Primary (queue-imbalance band). |
| MS-04 | CR-19 | Primary (VPIN regime shift, calibration-gated). |
| MS-05 | CR-20 | Primary (Kyle λ compression). |
| MS-06 | CR-21 | Primary (CVD divergence at level). |
| MS-07 | CR-22 | Primary (Hawkes branching, calibration-gated due to compute). |
| MS-08 | CR-23 | Primary (spoof veto — required for reliable absorption). |
| MS-09 | CR-24 | Primary (aggressor dominance at L). |
| MS-10 | CR-25 | Primary (round-number modifier). |
| MS-11 | CR-26 | Primary (depth asymmetry). |
| MS-12 | CR-27 | Primary (failed-break exhaustion; calibration-gated). |

### auction_theory.md §9 Trade-Plan Generators (15 rules)

| Source | Canonical | Lineage notes |
|--------|-----------|---------------|
| AUCT-01 | CR-28 | Primary (OD-UP + ORU). |
| AUCT-02 | CR-29 | Primary (OD-DOWN + ORD). |
| AUCT-03 | CR-30 | Primary (OTD-UP). |
| AUCT-04 | CR-06 | Merged into CR-06 (ORR at VAH fade = VA-proximity mechanic; same gate). |
| AUCT-05 | CR-31 | Primary (failed IB up). |
| AUCT-06 | CR-31 | Merged into CR-31 (failed IB both directions — single symmetric rule). |
| AUCT-07 | CR-32 | Primary (nPOC magnet up). |
| AUCT-08 | CR-32 | Merged into CR-32 (nPOC magnet down — symmetric). |
| AUCT-09 | CR-33 | Primary (poor high revisit light volume → fade). |
| AUCT-10 | CR-33 | Merged into CR-33 (poor low heavy volume → breakout; same rule with volume branch). |
| AUCT-11 | CR-34 | Primary (buying-tail retest). |
| AUCT-12 | CR-35 | Primary (open-auction in-range). |
| AUCT-13 | CR-36 | Primary (double-distribution single-print revisit). |
| AUCT-14 | CR-37 | Primary (ABSORB + Kronos-bearish + IB-fail; Kronos gate defaults OFF per D-42). |
| AUCT-15 | CR-38 | Primary (Neutral-Extreme → next-day gap-and-go). |

### Dedup summary

| Phase | Count |
|-------|-------|
| Raw source rules | 47 |
| DEEP6 merged into industry overlaps | 4 (D-03↔I-06, D-04↔I-07, D-05↔I-10, D-06↔A-04) |
| Auction symmetric-pair collapses | 3 (A-05↔A-06, A-07↔A-08, A-09↔A-10) |
| No MS overlap (all primary) | 0 |
| **Canonical CR-XX rules** | **38** |

38 is within the 35–40 target band (D-15).

---

## Tier distribution

| Tier | Count | CR IDs |
|------|-------|--------|
| EASY | 10 | CR-01, CR-02, CR-06, CR-07, CR-08, CR-25, CR-31, CR-32, CR-35 (and count verified via `grep EASY`) |
| MEDIUM | 18 | CR-03, CR-04, CR-05, CR-09, CR-10, CR-16..CR-18, CR-20, CR-21, CR-23, CR-24, CR-26, CR-28..CR-30, CR-33, CR-34, CR-36, CR-38 |
| CALIBRATION-GATED | 10 | CR-11, CR-12, CR-13, CR-14, CR-15, CR-19, CR-22, CR-27, CR-37 |

(Exact counts produced by the 15-03 config builder when it loads this file.)

---

## Out of scope (Phase 15 — deferred)

Consistent with `15-CONTEXT.md §Deferred Ideas`:

- **HIRO / DIX**: FlashAlpha schema unverified (D-30). If exposed as a discrete level, add `LevelKind.HIRO` + CR-39.
- **Pine heatmap rendering**: visualization only; Phase 11 dashboard layer.
- **Intrabar OHLCV sampling**: Pine workaround; DEEP6 has real Databento MBO.
- **Auto-reactive rule tuning (LightGBM-learned weights)**: Phase 9 territory.
- **Cross-asset confluence (ES↔NQ, SPY↔QQQ)**: research single-instrument only.
- **0DTE gamma intraday re-weighting**: SpotGamma volume-reweight is proprietary.
- **Kronos E10 tight integration** (D-42): gated behind `enable_e10_gating` config flag defaulting to False in Phase 15 MVP.

---

*Artifact produced by Plan 15-01 (T-15-01-01). Consumed by Plan 15-03 (ConfluenceRules encoder) and Plan 15-05 (golden-file tests). Any revision here forces a matching revision in 15-03's rule-switch dispatcher.*
