# Trading Knowledge Center Smoke Test — Phase 3

Date: 2026-05-12

## Query 1
**Prompt**: What is absorption and how does DEEP6 detect it?

**Files used**:
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-signals.md`

**Verification**:
- ABS-01 through ABS-04 are present.
- Each entry includes concept text and a Python code reference.
- References validated earlier in `p3-code-refs-validation.txt`.

**Answer summary**:
Absorption is DEEP6's core reversal thesis: passive limit orders absorb aggressive market orders without allowing price to continue. The knowledge base explains four detection variants: classic wick absorption (ABS-01), passive extreme-zone absorption (ABS-02), stopping volume with POC in the wick (ABS-03), and Wyckoff effort-vs-result narrow-range high-volume absorption (ABS-04). Each entry names the thresholds and points back to `deep6/engines/absorption.py` plus `signal_config.py`.

**Result**: PASS

---

## Query 2
**Prompt**: What NinjaTrader strategies use absorption signals?

**Files used**:
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\nt8-strategies.md`
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-signals.md`

**Verification**:
- Catalog contains multiple strategies explicitly tagged with `ABS-01` or absorption/order-flow logic.
- At least two valid examples found.

**Answer summary**:
The knowledge base can answer this cleanly. Examples include:
- `NT8-STR-02` TDU Auto Orderflow Footprint Trader — explicitly lists absorption, exhaustion, stacked imbalances, and delta-based signals.
- `NT8-STR-03` MZpack Footprint Action Strategy — includes hammer-with-absorption and other footprint triggers.
- `NT8-STR-06` MZpack GhostResistance — uses stop-hunt reversal logic with absorption zones.
- `NT8-STR-07` Emoji Trading Order Flow Suite — includes Absorption Pro and reversal confluence tools.
- `NT8-STR-13` TDU Delta Divergence Reversal — uses delta divergence plus absorption/stopping volume confirmation.
- `NT8-STR-17` LargeTrades Strategy NT8 — effectively targets large-trade absorption behavior.

**Result**: PASS

---

## Query 3
**Prompt**: What is the difference between positive and negative GEX?

**Files used**:
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md`

**Verification**:
- GEX-02 clearly defines positive GEX regime.
- GEX-03 clearly defines negative GEX regime.
- Both entries explain dealer hedging behavior and DEEP6 scoring impact.

**Answer summary**:
Positive GEX means price is above the gamma flip, dealers are long gamma, and hedging dampens moves: they sell into rallies and buy dips, which favors mean reversion. DEEP6 therefore boosts absorption/exhaustion and suppresses momentum. Negative GEX means price is below the gamma flip, dealers are short gamma, and hedging amplifies moves: they sell into selloffs and buy into rallies, which favors trending behavior. DEEP6 therefore suppresses absorption/exhaustion and boosts momentum-style signals.

**Result**: PASS

---

## Routing Verification

`knowledge.md` routing coverage verified for all required files:
- `domains/microstructure.md`
- `domains/deep6-signals.md`
- `domains/deep6-confluence.md`
- `domains/auction-theory.md`
- `domains/order-flow.md`
- `domains/gex-options.md`
- `domains/deep6-strategies.md`
- `catalogs/nt8-strategies.md`
- `catalogs/classic-patterns.md`
- `catalogs/strategy-methodology.md`
- `references/academic-papers.md`
- `references/glossary.md`

No routing update was required.

## Final Result

- Query 1: PASS
- Query 2: PASS
- Query 3: PASS
- Routing map coverage: PASS
