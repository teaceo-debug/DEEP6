# Draft: HTF MadLevels + Big Orders Bubbles

## Requirements (confirmed)
- **HTF Source**: 4-hour chart levels (MadLevels logic applied to 4H bars)
- **Big Orders**: Real-time large order detection shown as circles/bubbles on chart
- **Visual Goal**: "Easy on the eyes and easy to understand" — clean, minimal, institutional
- **Platform**: TradingView Pine Script indicator

## Technical Decisions
- MadLevels core logic: Trapped Sellers, Trapped Buyers, Failed Pullbacks — adapted from NT8 DEEP6MADLevels.cs
- Pine limitation: No direct DOM/tick data — must approximate absorption using volume + price action patterns on 4H bars
- Big orders bubbles: Large volume prints detected and rendered as sized circles

## Research Findings
- **Existing MadLevels (NT8)**: 4 signal types (TS, TB, FPB, FPS), strength scoring, level clustering — C# only, no Pine version exists
- **BOOKMAP_LIQUIDITY_MAPPER.pine**: Has zone detection architecture (absorption/exhaustion) — potential pattern reference
- **sd_anchor_ai.pine**: Active Pine indicator with DEEP6 visual language (cyan bullish, orange-red bearish)
- **DEEP6 Color Standard**: Cyan #00BCD4 (bullish), Orange-Red #FF5722 (bearish), Gold #FFD600 (absorption), Gray #9E9E9E (idle)

## Confirmed Answers
- **Viewing TF**: 4-hour chart itself — no MTF request.security() needed for levels
- **Bubble triggers**: BOTH — volume spikes (vol > Nx avg) + high-volume wick absorption (long wick + high vol)
- **Architecture**: Single-TF indicator on 4H — levels and bubbles both computed from 4H bars directly

## Open Questions
- How many levels max visible at once?
- Should levels expire/invalidate when price closes through them?
- Test strategy?

## Scope Boundaries
- INCLUDE: HTF MadLevels overlay + big order bubbles + clean visuals
- EXCLUDE: Full MADConfluenceAI (12 signals, scoring engine, decision rail) — this is a focused HTF+bubbles tool
