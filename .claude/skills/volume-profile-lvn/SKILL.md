# Volume Profile & LVN — Institutional Price Structure Analysis

Expert-level Volume Profile and Low Volume Node (LVN) trading skill for NQ futures. Covers auction market theory foundations, LVN identification and quality scoring, 6 codified trading strategies, order flow + GEX confluence rules, and Python/Pine implementation patterns. All strategies grounded in Steidlmayer/Dalton auction theory and validated against academic evidence.

## Invoke this skill when:

- User asks about Volume Profile shapes, LVN, HVN, POC, VAH, VAL, or value area
- User asks about Low Volume Nodes as entry zones, acceleration zones, or rejection levels
- User asks about profile-based NQ trading strategies (breakout, fade, gap-fill, retest)
- User asks about combining Volume Profile with order flow (absorption, delta, imbalances at LVN)
- User asks about combining Volume Profile with GEX/options (gamma regime + LVN behavior)
- User asks about Market Profile, TPO, auction market theory, or Dalton/Steidlmayer methodology
- User asks about composite profiles, value migration, naked VPOC, or structural LVN
- User asks about implementing Volume Profile in Python or Pine Script
- User asks about DEEP6's existing VP infrastructure (SessionProfile, POCEngine, E6VPContextEngine)
- User says "LVN setup", "volume profile strategy", "where is support/resistance from VP", "profile shapes"

## Skill Entry Point

Load `knowledge.md` in this directory first. It contains the master index, 5-step decision framework, and query routing map. Then load the minimum set of files needed for the specific query.

## Workflow

1. Read `knowledge.md` as the master index.
2. Identify the query domain from the routing map.
3. Load the relevant file(s) from the appropriate subdirectory.
4. Answer using the indexed source files and absolute paths.
5. If multiple domains apply, use the minimum set of files needed.
6. For implementation questions, always cross-reference `implementation/deep6-integration.md` with the existing codebase.

## Dependencies

- `trader-dale-footprint` — For order flow confirmation methodology (absorption, imbalances, delta)
- `options-bias-engine` — For GEX regime classification, gamma flip mechanics, wall dynamics
- `nq-options-algo-engine` — For algo implementation patterns, signal templates, data fusion
- `trading-knowledge` — For general microstructure concepts, DEEP6 signal mapping

## Key Codebase Files

| File | Purpose |
|------|---------|
| `deep6/engines/volume_profile.py` | SessionProfile with LVN/HVN detection, zone lifecycle FSM |
| `deep6/engines/poc.py` | POCEngine with 8 POC signal variants |
| `deep6/engines/vp_context_engine.py` | E6VPContextEngine integrating POC + VP + GEX |
| `deep6/engines/zone_registry.py` | Zone lifecycle management and confluence scoring |
| `deep6/engines/signal_config.py` | VolumeProfileConfig, POCConfig thresholds |
| `deep6v2/signals/engines/vp_context.py` | VPContextDetector (ENG-06) with LVNZone FSM |
| `ninjatrader/Custom/Indicators/DEEP6/VPLowTFLVNLevels.cs` | NinjaScript multi-TF LVN indicator |
| `ninjatrader/Custom/Strategies/DEEP6/DEEP6LVNRadarStrategy.cs` | NinjaScript LVN cross strategy |
| `tests/test_volume_profile.py` | SessionProfile tests (VPRO-01..08) |
| `tests/test_poc.py` | POCEngine tests (POC-01..08) |

## Source Material

Content synthesized from:
- J. Peter Steidlmayer — Original Market Profile creator (CBOT, 1980s)
- James F. Dalton — "Markets in Profile", "Mind Over Markets" (Wiley)
- Trader Dale — Order Flow + Volume Profile integration methodology
- Carmine — Professional LVN defense strategy (Tradezella)
- Fabio — Auction Market Theory playbook (Tradezella)
- Mesfin (2026) — Systematic falsification of OHLCV patterns on MNQ (arXiv:2605.04004)
- FlashAlpha — 0DTE gamma exposure and dealer positioning research
- StrikeWatch EA — Volume profile + institutional trading research
- RawStocks LLC — Volume Profile + options greeks confluence
- NexusFi Academy — LVN decay and touch analysis
- py-market-profile (389 stars) — Python VP implementation
- LibVPrf (AustrianTradingMachine) — Pine Script VP library

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\volume-profile-lvn\`
