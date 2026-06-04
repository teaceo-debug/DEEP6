## 2026-05-12 Wave1 done

---

## 2026-05-12: Domain extraction — deep6-strategies, order-flow, gex-options

### Source files read
- `deep6/scoring/scorer.py` (528 lines) — full scoring cascade, tier logic, category weights
- `deep6/engines/live_pipeline.py` (272 lines) — pipeline execution order, per-timeframe state
- `deep6/engines/delta.py` (330 lines) — 11 delta signal variants (DELT-01..11)
- `deep6/engines/vol_patterns.py` (397 lines) — 6 volume pattern variants (VOLP-01..06)
- `deep6/engines/gex.py` (313 lines) — GEX computation, regime classification, wall detection

### Key findings

**Scoring cascade (locked, phase 12-01)**:
- Multiplier order: base → confluence_mult → zone_bonus → ib_mult → vpin_modifier → clip(0,100)
- IB multiplier and VPIN are SEPARATE line items — never fuse them (FOOTGUN 1)
- VPIN applies to fused total_score only, not per-signal scores

**R3 weight profile (2026-04-15)**:
- imbalance weight raised from 13 → 25 (IMB-03 confirmed alpha-positive, 81.2% WR)
- absorption weight reduced from 32 → 20 (grid optimizer finding)
- volume_profile weight raised from 5 → 20.2

**TYPE_A requirements** (all must be true):
1. score >= 80
2. absorption OR exhaustion present
3. zone_bonus > 0 (price at/near volume zone)
4. category_count >= 5
5. delta_agrees (bar delta sign matches direction)
6. Not in midday block (bars 240-330)
7. No trap veto (< 3 trap signals)
8. No delta chase
9. No SPOOF_DETECTED veto

**GEX integration points** (3 places in scorer):
1. Category weight modification (before base score)
2. Wall bonus +5.0 (after base score, before IB mult)
3. Direction conflict → blocks TYPE_A/B

**Delta divergence** is labeled "highest alpha" in delta.py module docstring.
**Delta slingshot** has documented 72-78% win rate.

**No research docs found** in `.planning/research/` — glob returned empty. Either the directory structure is different or research docs don't exist yet.

### Patterns observed
- All engines use duck-typing for backward compatibility (VolumeZone vs Level)
- All engine failures are caught and logged; pipeline never raises on bar close
- Per-timeframe state isolation: 1m and 5m never share history
- `bar_index_in_session = i % 390` assumes 390 bars per RTH session

### Files created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-strategies.md` (10 entries)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\order-flow.md` (14 entries)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md` (10 entries)

## 2026-05-12 deep6-confluence.md created

- All 38 CR-XX rules extracted from `deep6/engines/confluence_rules.py` (807 lines)
- RULES.md at `.planning/phases/15-levelbus-confluence-rules-trade-decision-fsm/RULES.md` is the canonical source of truth for rule names, thresholds, and tier assignments
- Rule groups: GEX+Absorption Core (CR-01..10), GEX Advanced CALIB-GATED (CR-11..15), Microstructure (CR-16..27), Auction Theory (CR-28..38)
- Tier counts: EASY=9, MEDIUM=20, CALIBRATION-GATED=9 (total 38)
- Score deltas range from +3 (round number) to +20 (absorption at put wall, exhaust+absorb compound)
- CR-23 is the only VETO rule — forces DISQUALIFIED tier via SPOOF_DETECTED
- CR-04 emits PIN regime (highest priority); CR-05/CR-10 emit TREND; CR-10/CR-35 emit BALANCE
- scorer.py multiplier order (locked): base → confluence_mult → zone_bonus → IB mult → VPIN → clip(0,100)
- R3 category weights: imbalance=25.0 (highest), absorption=20.0, volume_profile=20.2, delta=14.3, exhaustion=15.7, auction=12.6
- Level.meta fields are the primary data bus between upstream engines and confluence rules
- 9 CALIBRATION-GATED rules are stubs (CR-12..15, CR-19, CR-22) or require Kronos/Hawkes compute (CR-37, CR-27, CR-11)

## 2026-05-12: microstructure.md and auction-theory.md created

### Source files read
- `.planning/research/pine/deep/microstructure.md` (297 lines) — 9 academic domains, 12 MS rules, full citation table
- `.planning/research/pine/deep/auction_theory.md` (237 lines) — Dalton/Steidlmayer framework, 6 day types, 5 open types, 15 trade-plan generators
- `.planning/research/pine/deep/practitioners.md` (301 lines) — Axia, Jigsaw, Bookmap, Valtos, Trader Dale pattern library
- `.planning/research/pine/deep/trade_logic.md` (432 lines) — 7-state FSM, 17 entry triggers, stop/target/sizing policy
- `deep6/engines/absorption.py` (243 lines) — 4 absorption variants (ABS-01..04), ABS-07 VA bonus
- `deep6/engines/exhaustion.py` (316 lines) — 6 exhaustion variants (EXH-01..06), EXH-07 gate, EXH-08 cooldown
- `deep6/engines/auction.py` (255 lines) — 5 auction signals (AUCT-01..05), E9 state machine

### Key findings

**Absorption formal definition** (from microstructure.md):
`Absorption(L, W) = Σ aggressor_volume in [L-ε, L+ε] / max(1, |Δmid in W, ticks|)`
Absorption z >= 2.5 with Δmid <= 1 tick and aggressor-side dominance >= 70% is the canonical signal.

**Exhaustion vs Absorption distinction**:
- Absorption = active defense by passive side (institutional intent)
- Exhaustion = collapse of aggressive side (no more fuel)
- Exhaustion fires first (earlier warning), absorption fires second (stronger signal)
- Together = highest-conviction reversal setup

**VPIN caveat** (Andersen-Bondarenko 2014): VPIN peaked AFTER the flash crash, not before. Canonical 0.99 threshold has poor short-run volatility prediction. Use VPIN as regime indicator (its change, not its level).

**Spoof suppressor is a VETO** (MS-08): Not a score modifier. Overrides absorption signals entirely when > 60% of resting size has mean lifetime < 500ms and cancel rate > 90%.

**Hawkes branching ratio** is the cleanest single indicator of level-about-to-break (branching → 1, same-side dominant) vs level-holding (cross-excitation dominant). Offloaded to ThreadPoolExecutor, refit every 5-10s.

**Round number weighting** (MS-10): 1.25x boost empirically justified by Bloomfield-Chin-Craig (2024) $850M/yr wealth transfer finding. Not folklore.

**Auction theory is a state machine**: Dalton's framework produces deterministic, enumerable trade plans from level structure. DEEP6 implements this as the 7-state TradeDecisionMachine (IDLE → WATCHING → ARMED → TRIGGERED → IN_POSITION → MANAGING → EXITING).

**WATCHING state is the critical missing piece** in the original ExecutionEngine: it allows DEEP6 to require a confirmation candle after absorption (Dante/Dale prop-style trigger) before committing capital.

**Footprint × MP synthesis rule**: Signals are meaningless without context. Evaluate footprint signals conditionally at MP-defined levels only. (Tom Alexander's core teaching.)

**Multi-timeframe level hierarchy**: A-grade (T1+T2) = × 1.5 confidence. B-grade (T2 alone) = × 1.0. C-grade (T3/T4 alone) = × 0.6. No level = no reversal trade.

### Files created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\microstructure.md` (12 entries: MICRO-01..12 + compositional rules)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\auction-theory.md` (13 entries: AUCT-01..13 + level hierarchy)

---

## 2026-05-12: deep6-signals.md created — all 44 signal definitions

### Source files read
- `deep6/signals/flags.py` (144 lines) — all 44 signal bits + TRAP_SHOT + 3 meta-flags
- `deep6/engines/signal_config.py` (460 lines) — all threshold dataclasses
- `deep6/engines/absorption.py` (243 lines) — ABS-01..04
- `deep6/engines/exhaustion.py` (316 lines) — EXH-01..08
- `deep6/engines/imbalance.py` (361 lines) — IMB-01..09
- `deep6/engines/delta.py` (330 lines) — DELT-01..11
- `deep6/engines/auction.py` (255 lines) — AUCT-01..05 + E9 state machine
- `deep6/engines/trap.py` (349 lines) — TRAP-02..05 (TRAP-01 is in imbalance.py)
- `deep6/engines/vol_patterns.py` (397 lines) — VOLP-01..06 (only 01-02 have bits; 03-06 reserved Phase 5+)

### Key findings

**Signal bit layout**: 44 signal bits (0-43) + TRAP_SHOT (44) + 3 meta-flags (45-47). Total 48 bits, fits in int64.
**SIGNAL_BITS_MASK = (1 << 45) - 1** — use this for popcount to exclude meta-flags.

**TRAP-01 is IMB-05**: The TRAP_INVERSE_I bit (37) is set by the imbalance engine when INVERSE_TRAP fires. No separate trap.py implementation.

**VOLP-03..06 are implemented but unregistered**: vol_patterns.py has all 6 VOLP variants, but only VOLP-01 (bit 42) and VOLP-02 (bit 43) have SignalFlags bits. VOLP-03..06 are Phase 5+ reserved.

**No dedicated Detector .cs files**: NT8 parity is in test files under `ninjatrader/tests/Detectors/` and the main DEEP6Atlas.cs indicator. No separate Detector class files exist.

**Highest-alpha signals** (per code comments):
- DELT-04 (Delta Divergence): labeled "highest alpha" in delta.py
- DELT-08 (Slingshot): documented 72-78% win rate
- IMB-05 (Inverse Imbalance): documented 80-85% win rate

**ABS-07 is a bonus modifier, not a separate signal**: VA extreme conviction bonus is applied to all 4 ABS variants when price is within 2 ticks of VAH/VAL. Strength += 0.15.

**EXH-07 is a gate, not a standalone signal**: The delta trajectory gate blocks EXH-02..06 when delta doesn't oppose bar direction. EXH-01 (zero print) is exempt.

**EXH-08 is a cooldown mechanism**: Per-sub-type cooldown of 5 bars. The EXH_COOLDOWN bit is set when suppression is active.

### Files created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-signals.md` (964 lines, 44 signal entries + TRAP_SHOT + META flags)

---

## 2026-05-12: NT8 Strategy Catalog created � 18 entries

### Research sources
- NinjaTrader Ecosystem User App Share (https://ninjatraderecosystem.com/user-app-share/)
- GitHub open-source repositories (OrderFlowBot, beer-money, ARKO TBORB, Inside Bar, ATSQuadro)
- Vendor sites: TradeDevils, MZpack, OrderFlow Hub, NinjaVendors, Emoji Trading, Trading123
- NinjaTrader community forums

### Key findings

**Order flow strategy landscape**:
- TDU (TradeDevils) is the most complete order flow strategy vendor with 21 built-in signals and 120+ data points
- MZpack provides 10 delta/order flow signals with AND/OR pattern builder
- OrderFlowBot (GitHub) is the best open-source order flow framework
- Beer Money (GitHub) provides the best open-source VWAP + order flow analysis

**Signal overlap with DEEP6**:
- 9 of 18 cataloged strategies use absorption detection (ABS-01 equivalent)
- 6 of 18 use delta divergence (CR-06 equivalent)
- 4 of 18 use stacked imbalances (IMB-03 equivalent)
- DEEP6's 44-signal + confluence scoring approach is more comprehensive than any single vendor

**Pricing landscape**:
- Free (User App Share): 5 strategies, quality varies widely
- Free (GitHub): 5 strategies/frameworks, generally well-documented
- Paid: $89/mo (Emoji) to $1,497 one-time (Trading123)
- Most paid strategies: $197-$299 range

**Patterns observed**:
- Morning session (8:00-11:30 AM) is the dominant focus for order flow strategies
- Peak hours strategies (12:30-4:30 PM) are a secondary niche
- Most vendors require NT8 Order Flow+ ($59/mo or Lifetime) � Emoji Trading is the exception
- Stacked imbalances and delta divergence are the two most commonly automated order flow signals
- No vendor approaches DEEP6's level of signal count (44) or confluence scoring sophistication

### File created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\nt8-strategies.md` (18 entries across 6 categories)

---

## 2026-05-12: Classic patterns, strategy methodology, and academic papers created

### Source files read
- `.planning/research/pine/deep/microstructure.md` (297 lines) — 35 academic citations with full metadata

---

## 2026-05-12: Phase 3 validation + smoke test

- Cross-reference validation completed across all 7 domain files.
- Total absolute code references checked: 355.
- Valid references: 355.
- Invalid references: 0.
- Evidence written to `C:\Users\Tea\DEEP6\.sisyphus\evidence\p3-code-refs-validation.txt`.
- Smoke-tested 3 routing scenarios successfully:
  - absorption explanation via `domains/deep6-signals.md`
  - NT8 absorption strategy lookup via `catalogs/nt8-strategies.md`
  - positive vs negative GEX via `domains/gex-options.md`
- Evidence written to `C:\Users\Tea\DEEP6\.sisyphus\evidence\p3-smoke-test.md`.
- `knowledge.md` routing already covered all required 12 domain/catalog/reference files; no edit needed.
- `.planning/phases/12-integrate-borrowed-orderflow-patterns-vpin-confidence-modifi/12-RESEARCH.md` (527 lines) — VPIN, slingshot, walk-forward research
- `.planning/phases/02-absorption-exhaustion-core/02-DISCUSSION-LOG.md` — threshold decisions
- `.planning/research/pine/deep/auction_theory.md` (237 lines) — Dalton/Steidlmayer framework
- `.planning/research/pine/deep/practitioners.md` (301 lines) — Axia, Jigsaw, Bookmap, Valtos pattern library

### Key findings

**Academic citation density**: microstructure.md is the richest source — 35 papers with full venue, year, and key finding. All citations are HIGH or MEDIUM confidence. No LOW-confidence citations were included in the academic-papers.md index.

**VPIN contrary evidence**: Andersen-Bondarenko (2014) is a critical caveat — VPIN peaked AFTER the flash crash. The canonical 0.99 threshold is explicitly rejected. DEEP6 uses VPIN as a regime indicator (change, not level).

**Bloomfield-Chin-Craig (2024)**: The $850M/yr round-number wealth transfer finding is a working paper (Georgetown CRI), not peer-reviewed. Marked MEDIUM confidence. Still justifies MS-10 (RoundNumberProximity) 1.25× boost.

**Dalton/Steidlmayer**: Auction theory probability figures (70-75% failed IB extension reversal) are educator-derived, not directly from primary text. Marked MEDIUM confidence for exact probabilities, HIGH for framework.

**Strategy methodology**: The 6-step evaluation framework (sample size, OOS, slippage, forward test, market condition dependency, DEEP6 integration) is synthesized from multiple sources. The minimum 200-trade sample size and 30-day forward test period are conservative but defensible.

**Classic patterns**: 15 patterns documented with DEEP6 signal mappings. CP-10 (Failed Breakout) and CP-14 (Liquidity Sweep) are the most NQ-specific patterns. CP-15 (Orderblock) is the ICT-derived pattern with the strongest DEEP6 signal alignment.

### Files created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\classic-patterns.md` (15 patterns, CP-01..15)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\strategy-methodology.md` (6 sections: sources, evaluation, red flags, NQ adaptation, DEEP6 integration, workflow)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\academic-papers.md` (35 papers indexed across 8 domains)

---

## 2026-05-12: glossary.md created � 69 terms

### Approach
- Read all 5 domain files: deep6-signals.md, microstructure.md, auction-theory.md, order-flow.md, gex-options.md
- Extracted all required terms from task spec plus additional terms for completeness
- Organized alphabetically A-Z with category tags and cross-references

### Stats
- 69 terms total (target was 60-70)
- 566 lines (limit was 800)
- All 50+ required terms from task spec confirmed present

### Patterns observed
- Domain files are comprehensive enough to write concise definitions without needing to read source code
- Category tags ([Microstructure], [Auction], [Order Flow], [GEX], [DEEP6], [Market Internal]) map cleanly to the domain file structure
- Cross-references use relative paths to domain files for portability
- Several terms span multiple domains (e.g., POC appears in both auction-theory.md and microstructure.md)

### File created
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\glossary.md` (69 terms, 566 lines)

## 2026-05-12 — Compliance Gap Fixes

### knowledge.md inventory
- Was: "0 entries yet" for all three directory lines
- Fixed: Replaced with per-file entry counts (15 files listed with actual counts)
- Pattern: Always list individual files, not just directories

### glossary.md See also removal
- Found 69 "See also:" lines across 66 terms (some terms had multiple)
- Removed via PowerShell regex: \r?\n\r?\n\*\*See also\*\*:[^\r\n]*
- Result: 428 lines (down from 566), 0 remaining See also lines
- Each definition now stands alone — no cross-reference chains

### deep6-signals.md NinjaTrader File refs
- Dedicated detector .cs files do NOT exist at 
injatrader/Custom/AddOns/DEEP6/Detectors/
- Parity test files DO exist at 
injatrader/tests/Detectors/
- ABS-01 already had a NinjaTrader File line pointing to AbsorptionDetectorTests.cs — used as pattern
- Added NinjaTrader File lines to: ABS-02, ABS-03, ABS-04 (AbsorptionDetectorTests.cs)
- Added to: EXH-01 through EXH-08 (ExhaustionDetectorTests.cs)
- Added to: TRAP-01 through TRAP-05 (TrapDetectorTests.cs)
- Total NinjaTrader File lines in file: 17
- Final line count: 1388 (under 1500 limit)
