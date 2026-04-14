# Open-Source Landscape: GEX × Volume Profile × Order Flow

**Researched:** 2026-04-13
**Scope:** Repos combining dealer gamma exposure, structural volume-profile levels, and order-flow behavioral zones — with a bias toward code DEEP6 can study, borrow, or explicitly avoid duplicating.

## Repo table

| Repo | Stars | Language | Relevance | License |
|------|-------|----------|-----------|---------|
| [bfolkens/py-market-profile](https://github.com/bfolkens/py-market-profile) | 390 | Python | HIGH — POC/VA/HVN/LVN direct API | BSD |
| [murtazayusuf/OrderflowChart](https://github.com/murtazayusuf/OrderflowChart) | 228 | Python | MEDIUM — footprint viz (archived 2025-11) | Apache-2.0 |
| [Matteo-Ferrara/gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) | 188 | Python | HIGH — CBOE-scraped dealer GEX | unstated |
| [jensolson/SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure) | 158 | Python | HIGH — CBOE_GEX + py_vollib Greeks | unstated |
| [AndreaFerrante/Orderflow](https://github.com/AndreaFerrante/Orderflow) | 120 | Python | MEDIUM — tick reshape + VWAP/VP/imbalance | MIT |
| [American-Dynasty/GEX-Dashboard](https://github.com/American-Dynasty/GEX-Dashboard) | ~ | Python+React | MEDIUM — FastAPI+React GEX UI | unstated |
| [Proshotv2/Gamma-Vanna-Options-Exposure](https://github.com/Proshotv2/Gamma-Vanna-Options-Exposure) | ~ | Python (Dash) | MEDIUM — GEX+VEX+DEX via Tradier | unstated |
| [aakash-code/GammaGEX](https://github.com/aakash-code/GammaGEX) | ~ | Python | LOW — Indian market (Upstox) | MIT |
| [phammings/SPX500-Gamma-Exposure-Calculator](https://github.com/phammings/SPX500-Gamma-Exposure-Calculator) | ~ | Python | MEDIUM — gamma-flip concept demo | unstated |
| [alpacahq/gamma-scalping](https://github.com/alpacahq/gamma-scalping) | ~ | Python | LOW — scalping template, not GEX levels | Apache-2.0 |
| [bmoscon/orderbook](https://github.com/bmoscon/orderbook) | ~ | C/Python | HIGH — LOB state mgmt (reference) | unstated |

Confidence: HIGH that this table captures the realistic OSS universe. LOW confidence that a confluence engine combining GEX + VP exists in OSS — exhaustive searches did not surface one.

## GEX compute

**[gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker)** (188★) — the de-facto reference implementation. Scrapes CBOE's public JSON quote endpoint, computes per-strike notional gamma `CallGamma = S · γ · OI · 100 · S · 0.01`, and plots GEX by strike and by expiry plus a 3-D term structure. Files: `main.py` is the entire pipeline. Gotcha: no explicit gamma-flip / call-wall / put-wall labels — those are derived by eye from the by-strike plot. License is unstated; contact author before vendoring.

**[SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure)** (158★) — older but cleaner math. Three functions: `CBOE_GEX` (simple, CBOE source), `TRTH_GEX` (Reuters tick history), `CBOE_Greeks` (full Black-Scholes surface using `py_vollib`). The `CBOE_GEX` sensitivity table is the closest thing in OSS to a gamma-flip solver — it re-prices GEX at spot ±N% and finds the zero-crossing. Worth reading even though NQ uses QQQ/NDX proxies via FlashAlpha, because the zero-crossing logic is generic.

**[GEX-Dashboard](https://github.com/American-Dynasty/GEX-Dashboard)** — full-stack FastAPI + React reference. Useful as a UI comparison point for DEEP6's Next.js dashboard, not as a compute library.

**[Proshotv2/Gamma-Vanna-Options-Exposure](https://github.com/Proshotv2/Gamma-Vanna-Options-Exposure)** — adds vanna and delta exposure on top of gamma; pulls from Tradier. Interesting if DEEP6 eventually layers vanna/charm levels on top of gamma.

**Not useful for NQ:** `GammaGEX` (Indian OpenAlgo), `alpacahq/gamma-scalping` (delta-hedging template, not level generation).

## Volume profile / order flow

**[py-market-profile](https://github.com/bfolkens/py-market-profile)** (390★, BSD) — the only OSS library that exposes `poc_price`, `value_area` (VAH/VAL tuple), `low_value_nodes`, `high_value_nodes`, `initial_balance`, `open_range`, and `balanced_target` as first-class attributes on a sliceable time-indexed profile object. BSD license means DEEP6 can vendor it directly. It is TPO/volume-only and pandas-based — fine for session profiles, not fast enough for tick-by-tick footprint updates.

**[OrderflowChart](https://github.com/murtazayusuf/OrderflowChart)** (228★, Apache-2.0, **archived 2025-11-27**) — the Plotly footprint reference. Reads `bid_size / price / ask_size / identifier` CSVs and auto-computes per-level imbalance. Archived status means no bug fixes will come upstream; fork if borrowing. Already flagged in `CLAUDE.md`.

**[AndreaFerrante/Orderflow](https://github.com/AndreaFerrante/Orderflow)** (120★, MIT) — tick-reshape toolkit with VWAP, volume profile, and imbalance computed over polars DataFrames. Explicit research-only disclaimer. Useful for backtest scaffolding against Databento MBO, not live hot-path.

**[bmoscon/orderbook](https://github.com/bmoscon/orderbook)** — C-backed LOB data structure already acknowledged in `CLAUDE.md` as the reference implementation. DEEP6 should stay on NumPy arrays for hot-path but borrow invariants (crossed book, self-trade, stale level pruning) from the bmoscon test suite.

**No OSS library computes absorption/exhaustion/momentum/rejection zones.** The four behavioral zones DEEP6 builds from tape are genuinely novel territory in open source — every hit in search returned vendor tools (Orderflows, Bookmap, NinjaTrader add-ons) or marketing copy.

## Confluence engines

**This is the gap.** After exhaustive searching — GitHub topics, QuantConnect algorithm library, NautilusTrader examples, freqtrade strategies, Jesse bot, r/thetagang shares, awesome-quant curated lists, academic paper code — **no public repo combines options-derived gamma levels with tape-derived structural levels into a single signal/score**. The closest adjacent work:

- `alpacahq/gamma-scalping` — uses gamma but only for delta-hedging P&L, not for level generation.
- FlashAlpha / SpotGamma / Menthor Q — all **closed-source commercial** (their moat).
- The TradingView script "Support and Resistance levels from Options Data" (marsrides) is Pine-only and single-source, not a true confluence engine.

**Implication:** DEEP6's confluence layer (GEX level × VP level × behavioral zone → confidence score) is greenfield. Borrowing individual level-generators is fine; the fusion logic must be original.

## Honorable mentions

- **[QuantLib](https://www.quantlib.org/)** — gold-standard Greeks and BS pricing; overkill for per-strike GEX but worth knowing for vanna/charm surfaces.
- **[py_vollib](https://pypi.org/project/py-vollib/)** — lightweight BS Greeks used by `jensolson/SPX-Gamma-Exposure`. Drop-in replacement if FlashAlpha ever goes down and DEEP6 needs a self-computed fallback from a raw options chain.
- **[awesome-quant](https://github.com/wilsonfreitas/awesome-quant)** — curated index; periodically check `options` and `orderflow` sections for new releases.
- **freqtrade issue #6845** — two-year-old open request to add volume profile to freqtrade. Confirms no mainstream bot framework ships VP natively.
- **Perfiliev's GEX tutorial** (linked in search results) — not code, but the cleanest walkthrough of computing zero-gamma / gamma-flip from a raw chain. Useful as a spec if DEEP6 builds a FlashAlpha-independent fallback.

## Recommended borrowings for DEEP6

1. **Vendor `py-market-profile` (BSD) into the backtest module** for session/weekly VP computation from Databento daily bars. Its `low_value_nodes` API directly feeds DEEP6's LVN level layer — do not reimplement. Wrap it with a thin adapter that also emits the LVN list in the format the confluence engine expects.

2. **Port `jensolson/SPX-Gamma-Exposure`'s `CBOE_GEX` zero-crossing sensitivity table** as the fallback gamma-flip solver for when FlashAlpha is unavailable or for backtesting pre-FlashAlpha dates. Use `py_vollib` for Greeks (already a trivial dep). Scope it explicitly as *fallback only* — FlashAlpha stays primary in prod.

3. **Study `AndreaFerrante/Orderflow` (MIT) polars pipelines** as the template for the Databento MBO → footprint-bar reshaping step. Do not vendor — just mirror the polars `group_by` patterns. It is faster than pandas for the historical replay scale (weeks of MBO ticks).

4. **Fork `OrderflowChart` before relying on it** — the repo archived on 2025-11-27 means no upstream fixes. For the Next.js dashboard use Lightweight Charts custom series per `CLAUDE.md`; keep the forked Plotly version strictly for Jupyter research notebooks during signal debugging.

5. **Treat the confluence layer as original IP.** No OSS reference exists. Spend planning energy on the scoring function itself, not on looking for prior art. When documenting, be explicit in RESEARCH/PLAN that the fusion logic is new — future maintainers will otherwise waste time searching for a reference that does not exist.

## Sources

- [Matteo-Ferrara/gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker)
- [jensolson/SPX-Gamma-Exposure](https://github.com/jensolson/SPX-Gamma-Exposure)
- [American-Dynasty/GEX-Dashboard](https://github.com/American-Dynasty/GEX-Dashboard)
- [Proshotv2/Gamma-Vanna-Options-Exposure](https://github.com/Proshotv2/Gamma-Vanna-Options-Exposure)
- [phammings/SPX500-Gamma-Exposure-Calculator](https://github.com/phammings/SPX500-Gamma-Exposure-Calculator)
- [aakash-code/GammaGEX](https://github.com/aakash-code/GammaGEX)
- [bfolkens/py-market-profile](https://github.com/bfolkens/py-market-profile)
- [murtazayusuf/OrderflowChart](https://github.com/murtazayusuf/OrderflowChart)
- [AndreaFerrante/Orderflow](https://github.com/AndreaFerrante/Orderflow)
- [bmoscon/orderbook](https://github.com/bmoscon/orderbook)
- [alpacahq/gamma-scalping](https://github.com/alpacahq/gamma-scalping)
- [wilsonfreitas/awesome-quant](https://github.com/wilsonfreitas/awesome-quant)
- [Perfiliev — How to Calculate GEX and Zero Gamma Level](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)
