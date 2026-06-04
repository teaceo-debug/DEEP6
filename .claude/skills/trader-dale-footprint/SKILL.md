# Trader Dale Footprint Chart — Order Flow Mastery

Invoke this skill when:
- User asks about reading footprint/order flow charts
- User asks about Trader Dale's Order Flow setups or confirmations
- User asks about TDO Bars software features, settings, or workspace
- User asks about passive vs active market participants in order flow
- User asks about volume clusters, imbalances, stacked imbalances, unfinished business
- User asks about delta, cumulative delta, or delta divergence
- User asks about order flow confirmations (limit orders, absorption, aggressive orders)
- User asks about take profit or stop loss placement using order flow
- User asks about combining Volume Profile with Order Flow
- User wants to build NinjaScript indicators/strategies on top of TDO Bars
- User says "how does Trader Dale trade", "order flow setup", "footprint confirmation"

## Skill Entry Point

Load `knowledge.md` in this directory first. Then identify the query domain,
load the relevant subdirectory file, and answer with references.

## Workflow

1. Read `knowledge.md` as the master index.
2. Identify the query domain from the routing map.
3. Load the relevant file from the appropriate subdirectory.
4. Answer using the indexed source files and absolute paths.
5. If multiple domains apply, use the minimum set of files needed.

## Dependencies

- `trading-knowledge` — For general microstructure concepts, DEEP6 signal mapping
- `nt8-expert` — For NinjaTrader 8 platform operations when deploying TDO Bars
- `ninjatrader-builder-doctor` — For building NinjaScript on top of TDO Bars

## Source Material

Content synthesized from:
- Trader Dale "Order Flow: Trading Setups" book (152 pages, Golden Ticket Edition 2024)
- Trader Dale membership site OF Video Course (40 lessons, 8 parts)
- Trader Dale Order Flow Methodology community content

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\trader-dale-footprint\`
