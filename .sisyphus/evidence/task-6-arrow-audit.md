# Evidence — task-6 arrow audit

Date: 2026-05-24

## Source evidence read

### V7 draw-system locations
- `DEEP6FootprintV7.cs:724` → `DrawTriggeredMarker(barIdx, closedBar.Close, isLong);`
- `DEEP6FootprintV7.cs:740-757` → `DrawTriggeredMarker(...)`
- `DEEP6FootprintV7.cs:511-515` → raw absorption detection + draw loop
- `DEEP6FootprintV7.cs:914-925` → `DrawAbsorptionMarker(...)`
- `DEEP6FootprintV7.cs:518-521` → raw exhaustion detection + draw loop
- `DEEP6FootprintV7.cs:927-947` → `DrawExhaustionMarker(...)`
- `DEEP6FootprintV7.cs:1189` → `if (ShowTier1Overlay) RenderTier1Overlay(...)`
- `DEEP6FootprintV7.cs:1849-1911` → `RenderTier1Overlay(...)`

### V7 defaults
- `DEEP6FootprintV7.cs:228-229` → `ShowAbsorptionMarkers=false`, `ShowExhaustionMarkers=false`
- `DEEP6FootprintV7.cs:253` → `ShowTier1Overlay=true`

### Type / confluence thresholds
- `SignalTier.cs:25-32` → TYPE_C / TYPE_B / TYPE_A semantics
- `ConfluenceScorer.cs:445-466`:
  - TYPE_A requires `totalScore >= 80`, abs/exh present, zone present, `catCount >= 5`, delta agreement
  - TYPE_B requires `totalScore >= 72`, `catCount >= 4`, delta agreement, min strength
  - TYPE_C requires `totalScore >= 50`, `catCount >= 4`, min strength
- `ConfluenceScorer.cs:508-519` + `ScorerResult.cs:30-35` → confluence count is exposed as `CategoryCount`

### Raw detector-noise evidence
- `AbsorptionDetector.cs:109-205` → multiple raw absorption families can fire on one bar; no cooldown state in detector
- `ExhaustionDetector.cs:34-35`, `151`, `174`, `216`, `239`, `259`, `277`, `362-372` → 5-bar subtype cooldown exists for exhaustion

### Frequency evidence used for Type A estimates
- `data/backtests/analysis/overnight_findings.md:92-100` → only 65 TYPE_A bars across 332 sessions (~0.20/session)
- `deep6/backtest/regime_analysis.py:660-663` → TYPE_A fires on `<0.1%` of synthetic bars

## Interpretation summary

1. The two raw marker systems (`DrawAbsorptionMarker`, `DrawExhaustionMarker`) are not scorer-aware.
2. The two Type A lifecycle systems (`DrawTriggeredMarker`, `RenderTier1Overlay`) are already naturally sparse.
3. The cleanest gate boundary is **category confluence = 4**, because that matches the first meaningful scorer threshold instead of showing one-off detector noise.
4. The cleanest exhaustion-strength floor is **0.60**, because that preserves fixed-strength `EXH-01` and stronger prints while filtering weaker exhaustion artifacts.
