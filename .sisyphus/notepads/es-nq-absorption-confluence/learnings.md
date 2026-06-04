# Learnings — es-nq-absorption-confluence

## [2026-05-29] Session ses_18af0377cffeIGWKhk7EXsdKYx — Plan Start

### Codebase Conventions
- Namespace: `NinjaTrader.NinjaScript.Indicators.DEEP6`
- File location: `ninjatrader/Custom/Indicators/DEEP6/DEEP6StackedAbsorptionArrows.cs`
- NT8 deploy destination: `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\`
- Deployment: `nt8-deploy.ps1 -Target Indicators -Force` then `nt8-compile.ps1`

### VolumetricBarsType API (confirmed from ExhaustionAbsorption.cs)
- Cast: `BarsArray[bipIndex].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType`
- Access: `volBars.Volumes[CurrentBars[bip]].GetBidVolumeForPrice(price)`
- Access: `volBars.Volumes[CurrentBars[bip]].GetAskVolumeForPrice(price)`
- Delta: `volBars.Volumes[CurrentBars[bip]].BarDelta`

### Arrow Convention (from DEEP6TripleConfluenceArrows.cs)
- Bull: `Draw.ArrowUp(this, "DEEP6SAC_Bull_" + CurrentBar, true, 0, Low[0] - 4 * TickSize, Brushes.Lime)`
- Bear: `Draw.ArrowDown(this, "DEEP6SAC_Bear_" + CurrentBar, true, 0, High[0] + 4 * TickSize, Brushes.Red)`

### Architecture Decision
- 3-BIP model: BIP 0 = primary NQ chart, BIP 1 = NQ volumetric, BIP 2 = ES volumetric
- DEEP6TripleConfluenceArrows.cs uses: AddDataSeries(1-min) → BIP 1, AddVolumetric(5-min) → BIP 2
  - This is the PROVEN pattern in DEEP6. For our indicator: AddVolumetric(NQ) → BIP 1, AddVolumetric(ES) → BIP 2
- Volumetric cast in ProcessVolumetricBar: `BarsArray[2].BarsType as VolumetricBarsType`
- Arrow pattern confirmed: `Low[0] - 4 * TickSize` / `High[0] + 4 * TickSize`, tag = "DEEP6TripleConfluenceArrows_Bull_" + CurrentBar
- Calculate.OnBarClose — volumetric data still available at bar close
- DEEP6Core.cs uses `Bars.BarsType as VolumetricBarsType` (single series) — for multi-series use `BarsArray[bipIndex].BarsType`

### Key Guardrails
- NO dependency on AbsorptionDetector.cs or any DEEP6 AddOn type
- NO visual elements besides Draw.ArrowUp and Draw.ArrowDown
- Use `Instruments[bipIndex].MasterInstrument.TickSize` per instrument (not global TickSize)
- Max 30 Telegram levels

## [2026-05-29] NEW SCOPE — User pivot after T1-T3 complete

### Status of original plan
- T1 (build indicator): DONE — DEEP6StackedAbsorptionArrows.cs, 817 lines, compiles SUCCESS
- T2 (deploy+compile): DONE — [COMPILE-RESULT] SUCCESS
- T3 (CSV): DONE — sample-levels.csv created
- T4 (live verify): BLOCKED — HERMES UI automation timed out (30 min)

### New requirements (3 asks)
1. **Auto Telegram→NT8 relay**: Build custom Python integration that auto-sends MAD Levels Telegram data to NinjaTrader. Seamless, automatic, zero manual user action. "Stream-less" = no manual copying.
2. **EXISTING PIPELINE**: Screenshot shows "MADLevels: Active (NQ)" indicator already drawing yellow level lines + "TARGET 30201.75" label. A MAD Levels relay ALREADY EXISTS — must integrate, not rebuild.
3. **Download all Telegram absorption data + Python backtest** to find alpha / optimal settings.

### Screenshot observations
- Chart: NQ 06-26, DEEP6 Footprint bar type, price ~30400
- "MADLevels: Active (NQ)" indicator active (bottom-right), TARGET 30201.75
- Yellow horizontal lines = today's MAD Levels (multiple S/R levels)
- GEX overlay (CW 30242.82, PW 30001.73) green lines
- Telegram channels: NQ=J4WHzA8EE5E2N2Nl, ES=mAiBHnFQ3gA4YjA1

### Pending research (3 explore agents)
- bg_a32797aa: existing MAD Levels Telegram pipeline
- bg_f98f5491: stored Telegram data + historical market data
- bg_ff127a1f: Python backtest infra

## [2026-05-29] Session indicator-build follow-up

### Implementation learnings
- `DEEP6StackedAbsorptionArrows.cs` was created as a self-contained NT8 indicator under `NinjaTrader.NinjaScript.Indicators.DEEP6`.
- Verification passed for source-level guardrails: 2 volumetric additions, correct class/namespace, 26 `NinjaScriptProperty` declarations, and zero forbidden DEEP6 AddOn type references.
- For multi-series volumetric scans, price iteration should round with a local helper driven by the series tick size instead of the primary instrument rounder.

### Verification learnings
- LSP diagnostics were clean on the new indicator file.
- HERMES successfully copied the repo file into the live NT8 custom indicator folder.
- NT8 compile automation is currently unreliable in this environment: DevAddon compile blocked on missing editor window, and fallback `nt8-compile.ps1` timed out with unchanged DLL and no surfaced CS#### errors.
