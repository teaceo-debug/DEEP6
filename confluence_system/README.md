# Institutional Confluence System

DEEP6 ATLAS sub-system that fuses **GEX levels + Dark Pool flow + Macro regime** into a single confluence score consumed by NinjaTrader 8.

```
┌────────────────────────────────────────────────────────────────────┐
│  LAYER 1 (STRUCTURE)  FlashAlpha  → GEX levels                     │
│                       /api/v1/levels/QQQ                           │
│                       Flip · Call Wall · Put Wall · HVL · Net GEX  │
├────────────────────────────────────────────────────────────────────┤
│  LAYER 2 (FLOW)       Massive     → Raw QQQ TRF off-exchange %     │
│                       /trf/QQQ/summary                             │
│                       quantsynth  → AI-filtered block prints       │
│                       /darkpool/QQQ                                │
├────────────────────────────────────────────────────────────────────┤
│  LAYER 3 (NARRATIVE)  quantsynth  → Macro regime + composite       │
│                       /market/regime                               │
│                       /market/pcr                                  │
│                       /trade/setup/QQQ  (Opus 4.7 verdict)         │
├────────────────────────────────────────────────────────────────────┤
│  LAYER 4 (LOCAL)      NT8 native  → MTF Premium/Discount zones     │
│                       BarsArray[Daily, 4H, Chart]                  │
└────────────────────────────────────────────────────────────────────┘
                                  ↓
                  confluence_server.py  (FastAPI :8765)
                  /confluence/nq?price=...&mtf_d=...&...
                                  ↓
                  InstitutionalConfluence.cs  (NT8 indicator)
                  • GEX horizontal lines
                  • MTF Premium/Discount rectangles
                  • HUD panel (top-right) — matches mockup
                  • Conflict alerts (STOP_BUYING / FULL_SEND_LONG / …)
                                  ↓
                  ConfluenceBiasFilter.cs   (DEEP6 ATLAS bridge)
                  • Vote / confidence / weight  → Engine #15
                  • Size multiplier             → fractional Kelly
                  • Hard vetoes                 → conflict alerts
```

## Scoring (DP-DOMINANT, your choice)

```
score = 0.40 · dp_signal
      + 0.25 · gex_signal
      + 0.20 · regime_signal
      + 0.15 · mtf_signal

display = round(score · 5)   → [-5, +5]
```

Each layer normalized to `[-1, +1]` in `confluence_server.py`. Weights tunable via env vars; the assertion at line 56 enforces sum=1.0.

## Files

| File | Purpose | Lines |
|---|---|---|
| `confluence_server.py` | FastAPI middleware aggregating all 3 APIs | ~600 |
| `InstitutionalConfluence.cs` | NT8 indicator (HUD + lines + zones) | ~500 |
| `ConfluenceBiasFilter.cs` | DEEP6 ATLAS Engine #15 bridge | ~200 |

## Setup

### 1. Python middleware

```bash
pip install fastapi uvicorn httpx pydantic
```

Set env vars (use a `.env` file or your secrets manager — never hardcode):

```bash
export MASSIVE_API_KEY=...
export FLASHALPHA_API_KEY=...
export QUANTSYNTH_API_KEY=...    # free tier from quantsynth.net
```

Run:

```bash
python confluence_server.py
# Listens on http://127.0.0.1:8765
```

Verify:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/status
curl 'http://127.0.0.1:8765/confluence/nq?price=21000&mtf_d=PREMIUM&mtf_4h=EQUILIBRIUM&mtf_chart=PREMIUM' | jq
```

### 2. NT8 indicator install

Copy both `.cs` files into:

```
Documents\NinjaTrader 8\bin\Custom\Indicators\PeakAssetPerformance\InstitutionalConfluence.cs
Documents\NinjaTrader 8\bin\Custom\Strategies\PeakAssetPerformance\ConfluenceBiasFilter.cs
```

In NT8: `Tools → Edit NinjaScript → Compile` (F5).

Add to your NQ chart: `Indicators → InstitutionalConfluence`. Set:
- **Server URL** = `http://127.0.0.1:8765`
- **Poll Interval** = `15` sec
- Toggle GEX Lines / MTF Zones / HUD / Alerts as desired

## DEEP6 ATLAS Engine #15 integration

In your strategy (or `DEEP6Atlas.cs` Engine #15 entry point):

```csharp
private InstitutionalConfluence _ic;
private ConfluenceBiasFilter   _confluence;

protected override void OnStateChange()
{
    if (State == State.Configure)
    {
        _confluence = new ConfluenceBiasFilter(this);
    }
    else if (State == State.DataLoaded)
    {
        _ic = InstitutionalConfluence(
            serverUrl: "http://127.0.0.1:8765",
            pollIntervalSec: 15,
            showGexLines: true, showMtfZones: true, showHud: true,
            audibleAlerts: false);
        _confluence.Attach(_ic);
    }
}

protected override void OnBarUpdate()
{
    // Engine #15 contribution path
    var (vote, conf, weight) = _confluence.ContributeToEngine15();
    DEEP6_BayesianFusion.AddContribution(15, vote, conf, weight);

    // Direct entry gating
    if (Position.MarketPosition == MarketPosition.Flat)
    {
        if (_confluence.IsLongAllowed(minScore: 2))
        {
            double size = BaseQty * _confluence.GetSizeMultiplier();
            EnterLong((int)size, "LONG_CONFLUENCE");
        }
        else if (_confluence.IsShortAllowed(minScore: 2))
        {
            double size = BaseQty * _confluence.GetSizeMultiplier();
            EnterShort((int)size, "SHORT_CONFLUENCE");
        }
    }
}
```

## Conflict alert taxonomy

| Alert | Fires when | Strategy action |
|---|---|---|
| `STOP_BUYING` | GEX bullish + DP bearish + price in premium | Veto longs |
| `STOP_SELLING` | GEX bearish + DP bullish + price in discount | Veto shorts |
| `REGIME_DIVERGENCE` | Opus verdict opposes local confluence (score ≥ 7) | Reduce size / abstain |
| `FULL_SEND_LONG` | Score ≥ +3 + all layers aligned RISK_ON | Boost size (1.2–1.5x) |
| `FULL_SEND_SHORT` | Score ≤ -3 + all layers aligned RISK_OFF | Boost size (1.2–1.5x) |
| `STAND_DOWN` | Score = 0 + neutral regime | No new entries |

## Tuning weights

Edit env vars or hardcode in `confluence_server.py`:

```python
W_DP, W_GEX, W_REGIME, W_MTF = 0.40, 0.25, 0.20, 0.15   # DP-dominant (current)
# W_DP, W_GEX, W_REGIME, W_MTF = 0.25, 0.25, 0.25, 0.25  # Equal weight
# W_DP, W_GEX, W_REGIME, W_MTF = 0.20, 0.40, 0.20, 0.20  # GEX-dominant
```

Sum must equal 1.0 (enforced by `assert` at import time).

## Cadences

| Source | Refresh | Reason |
|---|---|---|
| Massive TRF | 15 s | Intraday flow needs fast updates |
| quantsynth DP | 2 min | AI-filtered, less granular |
| FlashAlpha GEX | 5 min | Levels don't move fast |
| quantsynth `/trade/setup` | 5 min | Composite is slow-moving |
| quantsynth `/market/regime` | 15 min | Macro regime is slowest |

Tune via env: `REFRESH_GEX_SEC`, `REFRESH_MASSIVE_SEC`, etc.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| HUD shows "—" everywhere | Middleware not running | `python confluence_server.py` |
| `stale: true` on all layers | API keys missing/invalid | Check `curl /status` |
| Score stuck at 0 | All layers stale or neutral | `curl /confluence/nq/raw \| jq` |
| Lines flicker on chart | Poll interval too short | Set ≥10s in indicator props |
| NT8 thread pool warning | HTTP timeout cascade | Increase `HTTP_TIMEOUT_SEC` to 15 |
| Score doesn't match HUD | Different price/MTF on each poll | Use `OnBarClose` calculation mode |

Debug endpoint:
```bash
curl http://127.0.0.1:8765/confluence/nq/raw | jq
```

Returns all four raw layers without scoring — useful for verifying which source is broken.

## Phase roadmap (next builds)

1. ✅ **Phase 1** Middleware aggregator
2. ✅ **Phase 2** NT8 indicator skeleton + GEX lines + MTF zones
3. ✅ **Phase 3** HUD panel + scoring + alerts
4. ✅ **Phase 4** ConfluenceBiasFilter / Engine #15 bridge
5. ✅ **Phase 5** Equilibrium Model — SFV + Weekly/Daily GEX synthesis + 4-regime classifier (see below)
6. ⏳ **Phase 6** Walk-forward backtest of confluence score + SFV-distance vs. NQ forward returns (DSR/PBO)
7. ⏳ **Phase 7** ML calibration — train Bayesian posterior on score + SFV-distance → forward returns
8. ⏳ **Phase 8** Live alerting webhook integration (Slack / Discord on FULL_SEND + CRITICAL)
9. ⏳ **Phase 9** Auto-tune weights via grid search on Apex eval period (NQForge)

## Phase 5: Equilibrium Model (NEW)

The Equilibrium Model is a sibling sub-system that adds **Synthetic Fair Value (SFV)** — a *computed mean-reversion target price* — and replaces the simple ICT-style MTF zones with **volatility-adjusted bands** derived from full options-chain GEX synthesis.

**Endpoint:** `GET /equilibrium/nq?price=...&ndx=...&rv5=...&rv30=...&ema20=...&ema50=...`

**SFV math:**
```
SFV = 0.50 · WeeklyZeroGamma + 0.35 · DailyZeroGamma + 0.15 · HVL
```

**Volatility-adjusted bands:**
```
upper_premium  = SFV + 1.5σ        // PREMIUM zone above
lower_discount = SFV − 1.5σ        // DISCOUNT zone below
extreme_upper  = SFV + 2.5σ        // hard reversion warning
extreme_lower  = SFV − 2.5σ        // hard reversion warning
where σ = realized 30d daily vol × √5  (next-week horizon in NQ points)
```

**4-regime classifier output:**

| Regime | States |
|---|---|
| Gamma Regime | POSITIVE (Risk On) / NEGATIVE (Risk Off) / NEUTRAL |
| Volatility Regime | EXPANSION / CONTRACTION / STABLE |
| Trend Alignment | BULLISH / BEARISH / NEUTRAL (short-term EMA stack) |
| **Institutional Bias** | FADE_PREMIUM / FOLLOW_MOMENTUM / DEFEND_DISCOUNT / CAUTION / NEUTRAL |

**Phase 5 files:**

| File | Purpose | Lines |
|---|---|---|
| `equilibrium_module.py` | SFV math, NDX chain fetcher, strike-level GEX, regime classifier | ~690 |
| `EquilibriumModel.cs` | NT8 sibling indicator (top-LEFT HUD, SFV line, zone bands) | ~760 |
| `ConfluenceBiasFilter.cs` updates | SFV target/stop helpers + Engine #15 overlay logic | +100 |

**NT8 indicator install:** copy `EquilibriumModel.cs` next to `InstitutionalConfluence.cs`, F5 compile, add to NQ chart alongside the Confluence indicator. The two HUDs are positioned top-LEFT (Equilibrium) and top-RIGHT (Confluence) to coexist.

**Engine #15 integration upgrade:**

```csharp
private InstitutionalConfluence _ic;
private EquilibriumModel        _eqm;
private ConfluenceBiasFilter   _confluence;

protected override void OnStateChange()
{
    if (State == State.DataLoaded)
    {
        _ic  = InstitutionalConfluence(...);
        _eqm = EquilibriumModel("http://127.0.0.1:8765", 60, "^NDX",
                                true, true, true, true, 100);

        _confluence = new ConfluenceBiasFilter(this);
        _confluence.Attach(_ic);
        _confluence.AttachEquilibrium(_eqm);    // NEW
    }
}

protected override void OnBarUpdate()
{
    if (_confluence.IsLongAllowed(minScore: 2))
    {
        double size  = BaseQty * _confluence.GetSizeMultiplier();
        double? target = _confluence.SuggestedLongTarget();   // NEW: SFV magnet
        double? stop   = _confluence.SuggestedLongStop();     // NEW: LowerDiscount
        EnterLong((int)size, "LONG_CONFLUENCE");
        if (target.HasValue) SetProfitTarget(CalculationMode.Price, target.Value);
        if (stop.HasValue)   SetStopLoss(CalculationMode.Price, stop.Value);
    }
}
```

**Tunable env vars for Phase 5:**
```bash
EQM_W_WEEKLY=0.50           # SFV weight: Weekly Zero Gamma
EQM_W_DAILY=0.35            # SFV weight: Daily Zero Gamma
EQM_W_HVL=0.15              # SFV weight: HVL
EQM_SIGMA_ZONE=1.5          # zone edge sigma multiplier
EQM_SIGMA_EXTREME=2.5       # extreme edge sigma multiplier
EQM_USE_QQQ_DAILY=true      # use QQQ for daily (0DTE) pressure
EQM_GAMMA_TH_NDX=2e9        # gamma regime threshold (±2B for NDX)
REFRESH_EQUILIBRIUM_SEC=60  # cache TTL for /equilibrium/nq

## Notes

- The middleware runs locally (`127.0.0.1`) — never expose to the public internet without auth
- Free tier quantsynth has rate limits; the TTL cache + background refresher amortizes them
- NT8 strategy threading: `ConfluenceBiasFilter` is read-only from `OnBarUpdate`; safe
- The Engine #15 weight (0.40 base) matches the global DP weight — keeps the fusion math consistent
- All scoring logic lives in Python (easy to backtest); NT8 just renders + executes

---

*Built for Peak Asset Performance LLC. Pairs with DEEP6 ATLAS · NQForge · optionlevels.com.*
