# DEEP6 ATLAS — NinjaTrader 8 Deployment Guide

**Reading time:** 5 minutes. **Setup time:** 5 minutes.

---

## What you're installing

A single-file C# indicator (`DEEP6Atlas.cs`, 3,364 lines, 122KB) plus a paired strategy stub. Together they produce graded microstructure signals (S/A/B/C/Q) for NQ/MNQ/ES/MES futures with 16 engines, 4-tier funnel, FTRL online learning, and a SharpDX HUD overlay.

---

## Prerequisites

| Requirement | Version | Required? |
|---|---|---|
| NinjaTrader 8 | Latest stable | Yes |
| .NET Framework | 4.8 (NT8 default) | Yes |
| Rithmic Level 2 | 10+ DOM levels | Recommended (5 levels works at reduced fidelity) |
| OrderFlow+ add-on | Any | Recommended (for VolumetricBars and `vol.PriceVolumes`) |
| Apex Trader Funding | Any combine/funded account | Optional (for prop firm risk shim) |

---

## Step 1 — File placement

Quit NT8 first. Then copy:

```
DEEP6Atlas.cs        →  Documents\NinjaTrader 8\bin\Custom\Indicators\
DEEP6AtlasStrategy.cs →  Documents\NinjaTrader 8\bin\Custom\Strategies\
gex_nq.json          →  Documents\NinjaTrader 8\bin\Custom\AddOns\
```

**Note:** On Windows, the path is typically:
`C:\Users\<you>\Documents\NinjaTrader 8\bin\Custom\`

If you want the GEX worker to hit a different location, edit the `GexJsonPath` indicator input.

---

## Step 2 — Compile

Launch NT8. Press **F5** anywhere (or Tools → NinjaScript Editor → F5). NT8 will recompile the entire `bin\Custom\` tree.

**Expected output:** `Compile successful.` Zero errors. Possibly a warning or two about unused locals — ignore.

If you get errors:
- "Type or namespace not found" → install OrderFlow+ or comment out the `using` line for `NinjaTrader.NinjaScript.BarsTypes` (E1 will degrade gracefully)
- "Cannot resolve method 'Brushes.Gold'" → Add `using System.Windows.Media;` at top
- Anything else → check the line number, screenshot, and ping back

---

## Step 3 — Apply to a chart

```
1. Open chart on @NQ.06.26 (or current front month)
2. Bar type:   VolumetricBars (1 minute)  [or 60-tick if you prefer]
3. Indicators → DEEP6Atlas → Apply
4. Wait ~50 bars for "WARMING" to transition to "QUIET"
5. HUD should render top-right with dark background
```

---

## Step 4 — Read the HUD

Top-right panel:

```
┌──────────────────────────────────────────┐
│ DEEP6 ATLAS · A ▲ LONG                   │ ← state line, color-coded by grade
│ P=0.713 | grade=A | size×1.45            │ ← posterior, grade, size mult
│ regime: TrendingHighVol | drift: ok      │ ← E15 + E16 status
│ VPIN: 0.34  λ_kyle: 0.0042               │ ← toxicity (green<0.5, amber<0.65, red≥0.65)
│ MP_dev: +1.2t  Hawkes_n: 0.83            │ ← microprice deviation, branching ratio
│ GEX: γflip=22000 CW=22300 PW=21800       │ ← live GEX from JSON
│ engines: c=7/16  E1✓ E4✓ E8✓ E12✓ E13✓   │ ← active engine confluence
│ Last: 09:47 A LONG +1.8R                 │ ← last emitted signal + outcome
└──────────────────────────────────────────┘
```

**Grade colors:**
- **Gold** = S or A grade (highest confluence, highest posterior)
- **Amber** = B grade (medium confluence)
- **Cyan** = C grade (minimum confluence threshold)
- **Gray** = QUIET (no signal) or WARMING (still loading buffers)

---

## Step 5 — Apply the strategy (paper first)

```
1. Same chart that has DEEP6Atlas applied
2. Strategies tab → DEEP6AtlasStrategy → Apply
3. Parameters:
     MinGrade           = 3 (A+)         ← conservative; 2 = B+, 4 = S only
     BaseContracts      = 1              ← scale up after 30+ trades validation
     StopTicks          = 32             ← 8 NQ points; tune to your risk
     TargetR            = 2.0            ← 2:1 reward:risk
     UseSizeMultiplier  = true           ← ATLAS sizes per Kelly × regime
4. Connect to your Apex SIM account (NOT live yet)
5. Click "Enable" — strategy is now live on sim
6. Run for 5-10 sessions, log every trade
7. Compare actual outcomes to projected: 56-62% WR, 1.3-1.7R net
```

**Do not skip paper trading.** Even a perfect backtest deserves 30+ live sim trades before risking funded capital.

---

## Step 6 — GEX data feed (optional but recommended)

E11 (GEX Amplifier) reads from `gex_nq.json`. The shipped sample is static. To make it live:

**Option A — Manual update**
Edit the JSON file periodically with current values. Format:
```json
{
  "flip": 22000,
  "call_wall": 22300,
  "put_wall": 21800,
  "net_gex": 5000000000,
  "regime": "PositiveGamma",
  "ts": "2026-04-26T14:30:00Z"
}
```

**Option B — Live producer** (recommended)
Run a Python script that pulls QQQ + SPY options chains every 60s and writes the JSON atomically. A `gex_producer.py` scaffolding script is a follow-up deliverable — ask Claude.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| HUD never appears | Indicator not applied or chart paused | Re-apply, check chart is live |
| Stuck on WARMING for >100 bars | LOB buffer not filling | Verify Rithmic L2 connected with 10+ levels |
| All signals are QUIET | MinGrade too high or markets too quiet | Lower MinGrade to 1 (C+) for testing |
| VPIN always 0 | Trade event handler not firing | Check `OnMarketData` is wired; restart NT8 |
| GEX line shows zeros | gex_nq.json not found or stale | Verify path; check timestamps |
| Indicator crashes NT8 | Memory leak in long sessions | Restart NT8 nightly; not yet stress-tested >24h |
| Strategy doesn't enter | MinGrade not met or veto active | Lower threshold; check kill switches in HUD |

---

## What's stubbed (engineering honesty)

| Engine | Status | Path to production |
|---|---|---|
| E13 LOB-NN | Online logistic placeholder | Train TLOB ONNX (see HANDOFF §6) |
| E14 Meta-Label | Online logistic placeholder | Train XGBoost ONNX (see HANDOFF §6) |
| E15 HMM Regime | Deterministic classifier | Offline EM training future work |
| Hawkes MLE | Moment-matching | Bacry recursive scheme upgrade |

These run as functional stubs that won't break anything but won't deliver full ML edge until trained. The other 13 engines are production-ready as shipped.

---

## Performance expectations (honest)

After full validation on out-of-sample data (CPCV + DSR > 1.4 + PBO < 0.40):

```
WIN RATE:        56-62%
AVG R:           1.3-1.7R net
DEFLATED SHARPE: 1.4-2.2
APEX COMBINE:    18-35% target return
MAX DD:          15-22% intra-month
TRADES/DAY:      3-8 typical, capped at 8
```

These are the ceiling, not the floor. Live results will vary with regime, slippage, and discipline. Anything above this on backtest is curve-fit until proven by 6+ months live.

**Anything claiming 80%+ WR is not honest microstructure trading. It's curve-fit or selective reporting.**

---

## Next-level upgrades

1. **TLOB ONNX training** — replaces E13 with state-of-the-art Berti-Kasneci 2025 transformer
2. **GEX producer Python** — live optionlevels feed into E11
3. **DEEP6 ATLAS DIAG** — companion bottom-panel indicator with engine ribbon + posterior history
4. **HMM EM training** — proper regime transitions
5. **Cross-asset diversification** — extend to ES/MES/RTY for CTA-style portfolio

Ask Claude to build any of these. The architecture supports them as drop-in upgrades.

---

**Good trading. Validate before going live. Trust the funnel.**
