# NT8 Expert Knowledge Base

## Verified Paths (this machine)

| Purpose | Path |
|---------|------|
| NT8 root | `C:\Users\Tea\Documents\NinjaTrader 8\` |
| Custom source (all types) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` |
| Indicators | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\` |
| Strategies | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\` |
| AddOns | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\AddOns\` |
| DEEP6 repo source | `C:\Users\Tea\DEEP6\ninjatrader\Custom\` |
| DEEP6 Indicators (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\` |
| DEEP6 Strategies (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\` |
| DEEP6 AddOns (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\AddOns\DEEP6\` |

## Deploy Flow

1. Copy `.cs` files from repo source → NT8 Custom folder (matching subfolder)
2. Compile through the running NT8 process
3. Verify compile success from DLL mtime / Install.xml / Output Window

Use `ninjatrader/scripts/nt8-deploy.ps1` for the full copy → compile → verify flow.

## Script Hooks

- `ninjatrader/scripts/nt8-deploy.ps1`
- `ninjatrader/scripts/nt8-compile.ps1`
- `ninjatrader/scripts/nt8-ui.ps1`

## DEEP6 Data Flow for NT8

```
Rithmic feed → NT8 Data engine → OnBarUpdate() / OnMarketDepth()
                                  ↓
                          DEEP6 Indicators (.cs)
                          DataBridgeIndicator.cs → JSON export → Python signal engine
                          CaptureHarness.cs → bar capture for backtesting
                          DEEP6Footprint.cs → footprint chart rendering
                          DEEP6GexLevels.cs → GEX level overlay
                                  ↓
                          DEEP6Strategy.cs → order execution
```

## DEEP6-Specific Files

| File | Location | Purpose |
|------|----------|---------|
| `DEEP6Strategy.cs` | Strategies/DEEP6/ | Main auto-trade strategy |
| `DEEP6Footprint.cs` | Indicators/DEEP6/ | Footprint chart rendering |
| `DataBridgeIndicator.cs` | Indicators/DEEP6/ | Exports DOM data to Python |
| `CaptureHarness.cs` | Indicators/DEEP6/ | Bar capture for backtesting |
| `DEEP6GexLevels.cs` | Indicators/DEEP6/ | GEX level overlay |

## Compile Success/Failure Detection (April 2026)

NT8 does **not** write CS#### compile errors to any log file. Errors exist only in the NT8 Output Window UI.

| Signal | Path | Meaning |
|--------|------|---------|
| DLL timestamp | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` | Updated only on successful compile |
| Install.xml | `C:\Users\Tea\Documents\NinjaTrader 8\log\Install.xml` | Updated only on success |

Detection algorithm: record DLL `LastWriteTime` before triggering compile → poll until mtime changes (SUCCESS) or timeout elapses (FAILED).

Error text retrieval: use UIAutomation against the NinjaScript Editor Output Window, or NT8 trace logs for the compile event.

## DEEP6 Namespace Conventions

Use the DEEP6 subfolder namespaces for repo source and deployed NT8 files. Keep indicators, strategies, and add-ons under the matching `DEEP6` namespace tree; do not use the generic NT8 namespace rules here.

## Playback / DB Corruption Troubleshooting (April 2026)

- `db\NinjaTrader.sqlite` can become corrupt enough for `PRAGMA integrity_check` to fail.
- Startup can loop on persisted `NinjaTrader.NinjaScript.Strategies.DEEP6.DEEP6Strategy` rows.
- Recovery: stop NT8, back up DB + Config.xml, rebuild SQLite, purge bad strategy rows if needed, restart via AutoLogin shortcut.

## GEXCommand / JSON-backed Indicator Troubleshooting (April 2026)

- Avoid duplicate wrapper properties when using `JavaScriptSerializer`.
- Deserialize raw JSON fields directly in `GEXCommand.cs`.
- If compile fails, check for unrelated duplicate root-level files before blaming the new indicator.

## Critical Lessons (April 2026 Session)

- `nt8-deploy.ps1 -Target AddOns` copies recursively; manually copy single AddOn files when needed.
- Enum properties must use a global-namespace enum.
- `nt8-compile.ps1` uses DLL mtime + 500ms polling; `-TimeoutSeconds 45` is safer for large compiles.

## ⚠️ UIAutomation Critical Rules (May 2026 Session)

### RULE 1: NEVER type text when NT8 chart has keyboard focus
Typing any text while the NT8 chart panel has focus triggers the **Symbol/Instrument Search** popup ("Press esc to cancel"), NOT the Indicators dialog search. This happens with `$wsh.SendKeys("text")` and any other keyboard injection while the chart area is the active control.

**Symptom**: A dropdown appears listing stocks, futures, crypto, indices.
**Recovery**: `$wsh.SendKeys("{ESCAPE}")` twice.

### RULE 2: Correct way to open Indicators dialog
```
RIGHT-CLICK on the chart (use mouse_event, not keyboard)
→ click "Indicators..." menu item
→ dialog opens
→ CLICK inside the dialog's search box coordinates
→ THEN type indicator name
```
Ctrl+I only works if chart is focused but avoids the symbol search — test before relying on it.

### RULE 3: AddDataSeries() forces indicator into sub-panel
If an indicator calls `AddDataSeries()`, NT8 may place it in a sub-panel pane. Only `Draw.HorizontalLine()` spans across panels; `Draw.TextFixed()`, `Draw.Text()`, SharpDX text all stay in the sub-panel. Fix: remove `AddDataSeries()`, recompile, remove+re-add indicator from chart.

### RULE 4: Draw.Rectangle(barsAgo) can crash OnRender
If `barsAgo` exceeds available bars, `Draw.Rectangle()` throws in `OnRender`, silently aborting all remaining renders. Check Output Window for "Error on calling 'OnRender'" messages. Fix: guard with `if (CurrentBars[0] < barsAgo + 1) return;` or remove the Rectangle.

### RULE 5: Custom bar type charts (footprint) suppress managed draw text
On charts using custom bar types (DEEP6Footprint, etc.): `Draw.TextFixed()`, `Draw.Text()`, `Draw.ArrowUp()` may not render. Use SharpDX direct rendering (`RenderTarget.DrawText()`) instead. `Draw.HorizontalLine()` works on all chart types.

### RULE 6: Print() may not appear in Output Window on custom bar type charts
Use `Draw.HorizontalLine()` with a distinctive color (magenta) as a diagnostic instead of `Print()` when debugging indicators on footprint charts.

**Full details**: See `nt8-chart-verification/knowledge.md` — "NT8 UIAutomation Critical Pitfalls" section.
