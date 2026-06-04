# Institutional Confluence System — HANDOFF

> **Read this first if you are picking up this build cold.**
> Last touched: 2026-05-26 · Owner: Michael / Peak Asset Performance LLC
> Pairs with: DEEP6 ATLAS · NQForge · optionlevels.com

---

## 1. ONE-LINE SUMMARY

A 3-layer institutional confluence engine (GEX + Dark Pool + Macro) that runs as a Python FastAPI middleware (port 8765) and is consumed by an NT8 indicator that renders a HUD + GEX lines + MTF zones on the NQ chart, with a bridge class that feeds DEEP6 ATLAS **Engine #15 (Dark Pool Confluence)**.

## 2. STATUS

| Phase | Description | Status | Artifact |
|---|---|---|---|
| 1 | FastAPI middleware aggregator | ✅ DONE | `confluence_server.py` (824 LOC) |
| 2 | NT8 indicator skeleton + GEX lines + MTF zones | ✅ DONE | `InstitutionalConfluence.cs` (690 LOC) |
| 3 | HUD panel + scoring + conflict alerts | ✅ DONE | (same file as Phase 2) |
| 4 | DEEP6 ATLAS Engine #15 bridge | ✅ DONE | `ConfluenceBiasFilter.cs` (306 LOC) |
| 5 | Equilibrium Model: SFV + GEX synthesis + 4-regime | ✅ DONE | `equilibrium_module.py` (686 LOC) + `EquilibriumModel.cs` (761 LOC) |
| 6 | Walk-forward backtest (DSR/PBO) | ⏳ QUEUED | — |
| 7 | ML calibration (Bayesian posterior on score → fwd returns) | ⏳ QUEUED | — |
| 8 | Slack/Discord webhook on FULL_SEND + CRITICAL alerts | ⏳ QUEUED | — |
| 9 | NQForge weight auto-tune via grid search | ⏳ QUEUED | — |

**Total shipped: 3,884 LOC across 8 files.**

## 3. DECISION LOG

| Decision | Choice | Rationale |
|---|---|---|
| Platform | NinjaTrader 8 (NT8) | DEEP6 ATLAS is NT8; Engine #15 integration |
| Target instrument | NQ futures with QQQ as DP proxy | No native DP data for futures; QQQ correlates |
| Data sources | Massive (TRF) + FlashAlpha (GEX) + quantsynth.net (AI) | Three orthogonal layers, complementary not redundant |
| Architecture | Python middleware (port 8765) → NT8 polls | NT8 async HTTP is fragile; one local cache > three C# clients |
| Scoring weights | **DP-DOMINANT 0.40/0.25/0.20/0.15** (dp/gex/regime/mtf) | Michael's call — DP is "the edge" |
| Refresh cadences | Massive 15s, qs_dp 2min, GEX 5min, setup 5min, regime 15min | Match update frequency of each source |
| MTF calculation | NT8-side from `BarsArray`, posted as query params | No need to round-trip price data; ICT zones are local |
| HUD rendering | SharpDX `OnRender` override, Consolas font | Matches user's mockup; native NT8 chart layer |
| Alert dispatch | NT8 `Alert()` on UI thread via `Dispatcher.InvokeAsync` | Prevents calc-thread deadlock |
| **Phase 5 added** | Equilibrium Model as SIBLING (not replacement) | Preserves MTF zones; adds SFV magnet + 4-regime |
| **SFV components** | 0.50 WeeklyZG + 0.35 DailyZG + 0.15 HVL | Weekly anchors structure, Daily adds pressure, HVL tilts |
| **GEX chain source** | NDX primary, QQQ for daily 0DTE proxy | NDX has no true 0DTE; QQQ provides the pressure layer |
| **Volatility bands** | σ_zone = 1.5, σ_extreme = 2.5 (next-week horizon) | Industry-standard tail-cut; aligns with options expiry math |
| **HUD placement** | EquilibriumModel top-LEFT, InstitutionalConfluence top-RIGHT | Both indicators coexist on the same chart without overlap |
| **NDX→NQ scale** | dynamic ratio from poll-time NQ/NDX prices | Avoids hardcoded multiplier; tracks real NQ-vs-NDX basis drift |

## 4. FILE INVENTORY

```
confluence_system/
├── confluence_server.py         824 LOC   FastAPI middleware (+ /equilibrium/nq endpoint)
├── equilibrium_module.py        686 LOC   Phase 5: SFV + chain + regime classifier
├── InstitutionalConfluence.cs   690 LOC   NT8 indicator (HUD + lines + MTF zones)
├── EquilibriumModel.cs          761 LOC   Phase 5: SFV indicator + 4-regime panel
├── ConfluenceBiasFilter.cs      306 LOC   DEEP6 ATLAS Engine #15 bridge (+ SFV helpers)
├── README.md                    +180 LOC  Phase 5 docs added
├── HANDOFF.md                   THIS FILE
└── AGENT_PROMPT.md              Claude Code sub-agent prompt
```

## 5. KEY ENTRY POINTS

| What you want to change | Where to edit |
|---|---|
| Scoring weights | `confluence_server.py` lines 56–60 (`W_DP`, `W_GEX`, ...) |
| Signal normalization | `confluence_server.py:normalize_dp()`, `normalize_gex()`, `normalize_regime()`, `normalize_mtf()` |
| Alert taxonomy | `confluence_server.py:detect_alert()` |
| Refresh cadences | `confluence_server.py` lines 47–53 (`REFRESH_*_SEC`) |
| API endpoint URLs | `confluence_server.py:fetch_flashalpha_gex()`, `fetch_massive_trf()`, `fetch_quantsynth_*()` |
| HUD layout (Confluence) | `InstitutionalConfluence.cs:DrawHud()` |
| HUD layout (Equilibrium) | `EquilibriumModel.cs:DrawHud()` |
| GEX line styling | `InstitutionalConfluence.cs:DrawGexLines()` / `EquilibriumModel.cs:DrawGexLevelLines()` |
| MTF zone bands | `InstitutionalConfluence.cs:ClassifyZone()` (currently 65/35 around midpoint) |
| MTF lookback windows | `InstitutionalConfluence.cs:OnBarUpdate()` (5d daily, 24h 4H, 50bar chart) |
| Engine #15 vote/weight | `ConfluenceBiasFilter.cs:ContributeToEngine15()` |
| Size multiplier curve | `ConfluenceBiasFilter.cs:GetSizeMultiplier()` |
| **SFV weights** | `equilibrium_module.py` lines 51–53 (`W_WEEKLY_ZG`, `W_DAILY_ZG`, `W_HVL`) |
| **Sigma band multipliers** | `equilibrium_module.py` lines 56–57 (`SIGMA_ZONE_K`, `SIGMA_EXTREME_K`) |
| **BS gamma + strike GEX** | `equilibrium_module.py:bs_gamma()`, `strike_gex()` |
| **Zero Gamma detection** | `equilibrium_module.py:_find_zero_gamma()` (linear interp) |
| **4-regime classification** | `equilibrium_module.py:classify_regime()` |
| **3-tier alert engine** | `equilibrium_module.py:build_alerts()` |
| **NDX→NQ scale ratio** | `equilibrium_module.py:compute_equilibrium()` (dynamic from poll-time prices) |
| **SFV target / stop helpers** | `ConfluenceBiasFilter.cs:SuggestedLongTarget()` etc. |
| **Equilibrium overlay logic** | `ConfluenceBiasFilter.cs:ContributeToEngine15()` (Phase 5 additions) |

## 6. VERIFIED vs UNVERIFIED

### Verified
- ✅ Python syntax (`ast.parse` passes)
- ✅ Pydantic v2 schema matches `UnifiedPayload`
- ✅ Weight assertion sums to 1.0 at import
- ✅ NT8 indicator boilerplate cache pattern (3 partial classes)
- ✅ quantsynth endpoint shapes (`/darkpool/{ticker}`, `/market/regime`, `/market/pcr`, `/trade/setup/{ticker}` per quantsynth.net public docs)
- ✅ NT8 `Dispatcher.InvokeAsync` for cross-thread alerts
- ✅ `System.Threading.Timer` non-blocking poll pattern

### Unverified / needs validation against live APIs
- ⚠️ **FlashAlpha endpoint shape** — assumed `GET /api/v1/levels/{ticker}` with `Authorization: Bearer` header. Confirm against actual FlashAlpha Growth tier docs.
- ⚠️ **Massive TRF endpoint** — assumed `GET /trf/{ticker}/summary` returning `{off_exchange_pct, trf_vwap, timestamp}`. Confirm against Massive (Polygon) docs.
- ⚠️ **quantsynth free-tier rate limits** — not documented publicly; TTL cache provides graceful degradation but tune if hit.
- ⚠️ **SharpDX rendering on NT8 8.1.4.1+** — code uses standard `OnRenderTargetChanged` pattern but test on actual target NT8 version.
- ⚠️ **`Newtonsoft.Json` availability** — assumed bundled with NT8 (it is, in standard installs).

### Known bugs / quirks
- 🐛 `DrawMtfZones()` only draws chart-level zones, not Daily/4H zones (deliberate — Daily/4H state lives in HUD text only). Restore if you want full 3-zone overlay.
- 🐛 Background refresher uses integer modulo on `tick`; with non-15s intervals tuning may shift cadence by ±15s. Tighten if precision needed.

## 7. ACTIVE TODOs

In priority order:

1. **API endpoint validation** — Wire actual FlashAlpha + Massive keys, hit `/confluence/nq/raw`, confirm JSON field mapping. May require renaming fields in `fetch_flashalpha_gex()` and `fetch_massive_trf()`.
2. **NT8 compile test** — Drop both `.cs` files into a sandbox NT8 install, F5 compile, verify no errors.
3. **End-to-end smoke test** — Start middleware, load indicator on NQ 5-min chart, confirm HUD populates within 30s.
4. **Phase 5: Backtest** — Pull 6 months of NQ + QQQ options + DP data, replay through scoring, compute DSR/PBO on score buckets.
5. **Phase 6: ML calibration** — Train isotonic regression mapping `confluence_score` → P(NQ +N points in next 30 min).

## 8. INTEGRATION CONTRACT WITH DEEP6 ATLAS

Engine #15 (Dark Pool Confluence) calls `ConfluenceBiasFilter.ContributeToEngine15()` which returns `(vote, confidence, weight)`:

```
vote        ∈ {-1, 0, +1}      direction
confidence  ∈ [0, 1]           magnitude of conviction
weight      ∈ [0, 1]           multiplier in DEEP6 supermajority vote
```

**Weight policy:**
- Base weight = 0.40 (matches global DP weight in scoring)
- + 0.20 × DP confidence (boost when quantsynth confident)
- + 0.30 on `FULL_SEND_*` alerts
- = 0.10 (abstain weight) on `STOP_BUYING`/`STOP_SELLING`/`REGIME_DIVERGENCE`

## 9. CONFLICT ALERT TAXONOMY

| Alert | Trigger | Engine #15 action |
|---|---|---|
| `STOP_BUYING` | GEX bullish + DP bearish + price in premium | Vote→0, weight=0.10 |
| `STOP_SELLING` | GEX bearish + DP bullish + price in discount | Vote→0, weight=0.10 |
| `REGIME_DIVERGENCE` | Opus verdict opposes local confluence (qs score ≥ 7) | Vote→0, weight=0.10 |
| `FULL_SEND_LONG` | Score ≥ +3 + all layers aligned + RISK_ON | Boost weight +0.30 |
| `FULL_SEND_SHORT` | Score ≤ -3 + all layers aligned + RISK_OFF | Boost weight +0.30 |
| `STAND_DOWN` | Score = 0 + neutral regime | Soft abstain |

## 10. DEPLOYMENT

```bash
# 1. Python middleware
pip install fastapi uvicorn httpx pydantic
export MASSIVE_API_KEY=...
export FLASHALPHA_API_KEY=...
export QUANTSYNTH_API_KEY=...
python confluence_server.py

# 2. Verify
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/status
curl 'http://127.0.0.1:8765/confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM' | jq

# 3. NT8 install
cp InstitutionalConfluence.cs ~/Documents/NinjaTrader\ 8/bin/Custom/Indicators/PeakAssetPerformance/
cp ConfluenceBiasFilter.cs    ~/Documents/NinjaTrader\ 8/bin/Custom/Strategies/PeakAssetPerformance/
# Open NT8 → Tools → Edit NinjaScript → F5
# Add indicator to NQ chart with ServerUrl=http://127.0.0.1:8765
```

## 11. GLOSSARY

| Term | Meaning |
|---|---|
| GEX | Gamma Exposure — dealer net gamma positioning |
| Flip | GEX flip point — price where dealer gamma sign changes |
| Call Wall / Put Wall | Largest positive/negative gamma strikes (resistance/support) |
| HVL | High Volatility Level — high-vol concentration strike |
| DP | Dark Pool — off-exchange institutional flow |
| TRF | Trade Reporting Facility — off-exchange print stream |
| MTF | Multi-Timeframe |
| P/D/Eq | Premium / Discount / Equilibrium (ICT range bisector) |
| ICT | Inner Circle Trader methodology |
| DSR | Deflated Sharpe Ratio (López de Prado) |
| PBO | Probability of Backtest Overfitting |
| Apex | Apex Trader Funding — prop firm with 2.5% trailing DD, 10% target |
| Engine #15 | Dark Pool Confluence engine in DEEP6 ATLAS (NT8 indicator) |
| Opus verdict | Final BULL/BEAR/NEUTRAL from quantsynth's Pass 6 (Claude Opus 4.7) |
| PCR | Put/Call Ratio |
| FULL_SEND | Internal alert code for max-conviction aligned setup |

## 12. NON-OBVIOUS GOTCHAS

1. **MTF zone state lives in NT8, not the middleware.** The indicator passes `mtf_d`/`mtf_4h`/`mtf_chart` as query params on every poll. If you call `/confluence/nq` without them, `mtf_signal` will be 0.0 (unknown).
2. **The `assert` on weights** at module load will crash the server if you tune weights and they don't sum to 1.0. This is intentional — fail fast.
3. **`Calculate.OnEachTick`** is set in NT8 indicator defaults. If you switch to `OnBarClose`, the price posted to the middleware will be stale by up to one bar. Acceptable for 5-min charts; not for scalping.
4. **`_isPolling` re-entrancy guard** in `PollServerAsync()` — if a poll takes >15s, the next tick is skipped. By design, prevents request stacking.
5. **quantsynth uses `X-API-Key` header**, FlashAlpha (assumed) uses `Authorization: Bearer`, Massive (assumed) uses `X-API-Key`. Don't mix these up.
6. **`ContributeToEngine15()` returns `(0, 0.0, 0.0)`** if indicator not ready or stale. Engine #15 must handle the abstain case gracefully (don't divide by total weight if it's 0).

---

*End of handoff. For continuing work, paste `AGENT_PROMPT.md` into a fresh Claude Code session.*
