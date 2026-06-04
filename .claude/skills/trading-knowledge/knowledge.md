# Trading Knowledge Center Index

Master index only. Do not store full knowledge articles here.

## Entry Schema Template

```markdown
## [Entry-ID]: [Name]
**Category**: [Microstructure | Auction Theory | Order Flow | Delta | Volume Profile | GEX | Trap | Strategy | Pattern]
**Tags**: [comma-separated keywords]
**DEEP6 Signal(s)**: [ABS-01, CR-06, etc.] (if applicable)
**NinjaTrader File**: [path] (if applicable)
**Python File**: [path] (if applicable)

### Concept
[What it is, why it matters for NQ futures trading]

### Conditions / Setup
[When this pattern appears — market context, prerequisites, timeframe]

### Entry / Exit Rules
[Mechanical rules if strategy; detection logic if signal]

### Risk Management
[Stop placement, sizing, max loss — if applicable]

### DEEP6 Implementation
[Code references: file path + line range, threshold values, configuration]
[Both Python reference and C# NT8 implementation if both exist]

### Academic Basis
[Paper citations: Author (Year), Title, Key Finding]

### Examples / Edge Cases
[Specific market scenarios, known failure modes, when NOT to use]

### Backtest Notes
[Results if available, caveats, sample sizes]
```

## Query Routing Map

- "What is absorption / exhaustion / imbalance?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\microstructure.md`
- "What DEEP6 signal detects X?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-signals.md`
- "Which confluence rules use X?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-confluence.md`
- "Find strategies for X market condition" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\nt8-strategies.md` + `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\classic-patterns.md`
- "How does DEEP6 score signals?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-strategies.md`
- "What academic research supports X?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\academic-papers.md`
- "What does [term] mean?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\glossary.md`
- "Auction theory / IB / POC / value area" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\auction-theory.md`
- "Delta / CVD / volume profile" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\order-flow.md`
- "GEX / gamma / options flow" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md`
- "How to find NinjaTrader strategies?" → `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\strategy-methodology.md`

## File Inventory

- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\SKILL.md` — skill entry point and routing rules
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\knowledge.md` — master index and schema template
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-signals.md` — 44+ signal entries (ABS, EXH, IMB, DELT, AUCT, TRAP, VOLP, META)
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-confluence.md` — 38+ confluence rule entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\microstructure.md` — 12 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\auction-theory.md` — 13 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\deep6-strategies.md` — 10 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\order-flow.md` — 14 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\domains\gex-options.md` — 10 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\nt8-strategies.md` — 18 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\classic-patterns.md` — 15 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\strategy-methodology.md` — 1 guide
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\catalogs\deep6-strategies.md` — 10 entries
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\academic-papers.md` — 35+ papers
- `C:\Users\Tea\DEEP6\.claude\skills\trading-knowledge\references\glossary.md` — 66 terms

## Conventions

- Use absolute paths only.
- Keep `knowledge.md` as an index, not a knowledge dump.
- Add `Last verified: 2026-05-12` to each populated domain/catalog/reference file.
- Maintain at least 80% schema fill for every entry.
- Route queries before writing content; do not improvise new categories.
