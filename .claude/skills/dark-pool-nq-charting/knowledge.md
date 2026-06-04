# Dark Pool NQ Charting — Doctorate-Level Expertise

> Institutional dark pool flow as leading support/resistance for NQ futures.
> Academic microstructure theory → quantitative models → charting methodology → Python/Pine implementation.

## Identity

This skill provides **doctorate-level expertise** on dark pools and how to chart them for NQ futures trading. It goes far beyond API reference (see `unusual-whales/` for that) into the *theory, mechanics, quantitative models, and practical charting workflow* that a professional quant or institutional trader would use.

**Core thesis**: Dark pool prints in QQQ/NDX components cluster at prices where institutions are accumulating or distributing. These levels become support/resistance for NQ futures 1–3 days before the move appears in price action. Combined with GEX walls and options flow, dark pool levels produce 55–70% directional accuracy.

## When to Load This Skill

Load when the task involves ANY of:
- Understanding dark pool mechanics at an academic level (market microstructure, price discovery)
- Charting dark pool levels on NQ/ES futures charts
- Building quantitative dark pool signals (DIX, z-scores, aggression metrics)
- Understanding the GEX ↔ dark pool interaction model
- Converting QQQ dark pool levels to NQ price equivalents
- Evaluating dark pool data quality, biases, and limitations
- Implementing dark pool clustering algorithms in Python
- Building Pine Script indicators for dark pool level overlays

Do NOT load for:
- Unusual Whales API endpoints → load `unusual-whales/api-reference`
- WebSocket streaming setup → load `unusual-whales/websocket`
- Pure GEX theory without dark pool context → load `options-bias-engine/domains/gex-theory`
- Footprint chart reading (no dark pool) → load `trader-dale-footprint/`

---

## Sub-Skill Routing Table

| File | Domain | Depth Level |
|------|--------|-------------|
| `foundations.md` | What dark pools ARE — venues, FINRA reporting, data mechanics, biases, retail internalization vs true ATS | Graduate |
| `microstructure-theory.md` | Academic theory — Kyle lambda, Glosten-Milgrom adverse selection, Zhu sorting mechanism, Comerton-Forde tipping point, Nimalendran informational linkages | PhD |
| `charting-methodology.md` | How to chart dark pool levels on NQ — visualization methods, QQQ→NQ conversion, volume profiles, chart patterns, daily workflow | Practitioner |
| `quantitative-models.md` | DIX formula, z-score anomaly detection, NBBO aggression metric, dark pool POC, Bayesian significance, GEX×dark pool confluence model | PhD/Quant |
| `implementation.md` | Python clustering code, Pine Script overlays, real-time WebSocket pipeline, Lightweight Charts rendering | Engineer |

---

## The Dark Pool Information Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                  DARK POOL DATA PYRAMID                      │
│                                                              │
│  Level 5: CONFLUENCE SIGNAL                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Dark pool level + GEX wall + options flow + footprint│    │
│  │ = 65-70% directional accuracy on NQ                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 4: CHARTED LEVELS                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Clustered prints → horizontal S/R on NQ chart        │    │
│  │ QQQ→NQ conversion via live ratio                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 3: QUANTITATIVE SIGNALS                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ DIX, z-scores, aggression ratio, dark pool POC       │    │
│  │ Statistical significance testing                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 2: RAW DARK POOL PRINTS                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Price, size, NBBO context, venue, timestamp          │    │
│  │ Individual trade records from FINRA TRF              │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Level 1: MARKET MICROSTRUCTURE THEORY                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Kyle lambda, adverse selection, sorting mechanism    │    │
│  │ Why dark pools exist and what they reveal            │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Critical Numbers to Know

| Metric | Value | Source |
|--------|-------|--------|
| Dark pool share of US equity volume | 40.3% (Q1 2026, record high) | FINRA ATS |
| True ATS dark pool volume | ~15-18% of total | FINRA |
| Retail internalization (Citadel/Virtu) | ~25-30% of total | SEC filings |
| FINRA TRF reporting latency (median) | 2.5 milliseconds | NYU Stern 2021 |
| FINRA TRF reporting latency (95th pct) | 200 milliseconds | NYU Stern 2021 |
| Dark pool trades at stale prices | ~4% | BIS 2023 |
| Canceled dark pool orders (invisible) | 7-10% | SEC Rule 605 |
| Informative dark pool volume | ~35% | Kolm et al. 2023 |
| Dark pool tipping point (price discovery harm) | >10% of stock's volume | Comerton-Forde 2015 |
| DIX bullish threshold | >0.45 | SqueezeMetrics |
| DIX mean 60-day return at high levels | +5.3% vs +2.8% baseline | SqueezeMetrics |
| Dark pool + GEX + flow confluence accuracy | 65-70% | Practitioner evidence |

## NQ Proxy Architecture

NQ futures have NO direct dark pool data. The proxy chain:

```
QQQ Dark Pool Prints (direct Nasdaq-100 ETF)
    ↓ Convert via live ratio: NQ_Level = QQQ_Level × (NQ/QQQ)
    
Top-5 NQ Component Aggregation (AAPL, MSFT, NVDA, GOOGL, AMZN)
    ↓ 3+ of 5 showing accumulation = bullish NQ signal
    
QQQ Options GEX (gamma walls from options chain)
    ↓ Dark pool prints clustering within 0.5% of GEX wall = strongest signal
```

## Academic Foundation (Key Papers)

| Paper | Finding | Relevance |
|-------|---------|-----------|
| Kyle (1985) | Price impact coefficient λ; informed traders hide in order flow | Why institutions use dark pools |
| Glosten-Milgrom (1985) | Adverse selection drives bid-ask spreads | Why dark pools execute at midpoint |
| Zhu (2014) | Informed traders cluster → lower execution in dark pools → self-sort to lit exchanges | Dark pools IMPROVE price discovery |
| Comerton-Forde & Putniņš (2015) | >10% dark volume harms price discovery; block trades are exception | Tipping point for dark pool signals |
| Nimalendran & Ray (2014) | Abnormal dark pool volume predicts future returns | Empirical basis for dark pool signals |

## Sources

| Source | URL | Type |
|--------|-----|------|
| FINRA ATS Transparency Data | https://www.finra.org/finra-data/browse-catalog/alternative-trading-system-ats-transparency-data/ | Official |
| FINRA Short Sale Volume (Daily) | https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files | Official |
| SEC Form ATS-N Filings | https://www.sec.gov/about/divisions-offices/division-trading-markets/alternative-trading-systems/form-ats-n-filings-information | Official |
| SqueezeMetrics DIX/GEX | https://squeezemetrics.com/monitor/dix | Practitioner |
| Quant Data (Dark Pool Levels) | https://v3.quantdata.us | Practitioner |
| Unusual Whales API | https://api.unusualwhales.com/docs | API |
| Zhu 2014 (SSRN) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712173 | Academic |
| Comerton-Forde 2015 (SSRN) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2183392 | Academic |
| NYU Stern TRF Latency Study | https://pages.stern.nyu.edu/~jhasbrou/SternMicroMtg/ | Academic |
