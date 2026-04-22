# NT8 Expert Knowledge Base

## Verified Paths (this machine)

| Purpose | Path |
|---------|------|
| NT8 root | `C:\Users\Tea\Documents\NinjaTrader 8\` |
| Custom source (all types) | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` |
| **Indicators** | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\` |
| **Strategies** | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Strategies\` |
| **AddOns** | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\AddOns\` |
| BarsTypes | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\BarsTypes\` |
| DrawingTools | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\DrawingTools\` |
| Templates | `C:\Users\Tea\Documents\NinjaTrader 8\templates\` |
| Workspaces | `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\` |
| Logs | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |
| Trace logs | `C:\Users\Tea\Documents\NinjaTrader 8\trace\` |
| DB (instrument, account) | `C:\Users\Tea\Documents\NinjaTrader 8\db\` |
| Config | `C:\Users\Tea\Documents\NinjaTrader 8\Config.xml` |
| NT8 executable | `C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe` |
| DEEP6 repo source | `C:\Users\Tea\DEEP6\ninjatrader\Custom\` |
| DEEP6 Indicators (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Indicators\DEEP6\` |
| DEEP6 Strategies (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\Strategies\DEEP6\` |
| DEEP6 AddOns (source) | `C:\Users\Tea\DEEP6\ninjatrader\Custom\AddOns\DEEP6\` |

## NT8 Folder Rules

- **Indicators** go in `Indicators\` — can be in subfolders (e.g. `Indicators\DEEP6\`)
- **Strategies** go in `Strategies\` — can be in subfolders (e.g. `Strategies\DEEP6\`)
- **AddOns** go in `AddOns\` — must match the namespace declared in the .cs file
- Files are `.cs` (C# source). NT8 compiles them; do NOT put pre-compiled DLLs here
- NT8 ships built-in indicators prefixed with `@` (e.g. `@ATR.cs`) — never modify these
- User/custom indicators have no `@` prefix
- Subfolder name (e.g. `DEEP6`) becomes the **category** shown in NT8 indicator picker UI

## Deploy Flow (manual or scripted)

1. **Copy** `.cs` files from repo source → NT8 Custom folder (matching subfolder)
2. **Compile** — NT8 must recompile for changes to take effect
3. **Verify** — check for compile errors in NT8 output window or log

Use `ninjatrader/scripts/nt8-deploy.ps1` for steps 1–3 automated.

## Triggering Compilation

NT8 has **no CLI compiler**. Compilation must be done through the running NT8 process.

### Method 1: UI Automation (SendKeys) — PREFERRED
Open NinjaScript Editor via menu, then send F5 or click Compile button.
Script: `ninjatrader/scripts/nt8-compile.ps1`

### Method 2: File watcher trigger
NT8 8.1.x+ auto-detects changes to Custom/ when a chart is open.
Close and reopen the NinjaScript Editor to force re-scan.

### Method 3: Tools menu sequence
1. NT8 Control Center → Tools → NinjaScript Editor (or press Ctrl+Shift+N... actually via menu only)
2. In editor: Build → Compile (or F5)
3. Check Output window for errors

### NT8 Keyboard Shortcuts (in NinjaScript Editor)
| Action | Shortcut |
|--------|----------|
| Compile | F5 |
| Save | Ctrl+S |
| Close editor | Alt+F4 |

## Adding Indicator to a Chart

### Via NT8 UI:
1. Right-click on chart → **Indicators...**
2. Find indicator in left panel (look under category = subfolder name, e.g. "DEEP6")
3. Double-click or click **Add >>**
4. Configure parameters in right panel
5. Click **OK**

### Via UI Automation script:
`ninjatrader/scripts/nt8-ui.ps1 -Action AddIndicator -IndicatorName "DEEP6Footprint"`

## Adding Strategy to a Chart

### Via NT8 UI:
1. Right-click on chart → **Strategies...**
2. Find strategy under category (e.g. "DEEP6 > DEEP6Strategy")
3. Double-click to add
4. Configure: instrument, account, quantity, parameters
5. Toggle **Enable** checkbox → click **OK**

## NT8 Control Center Navigation

| Task | Menu Path |
|------|-----------|
| NinjaScript Editor | Tools > NinjaScript Editor |
| Strategy Analyzer | New > Strategy Analyzer |
| Sim account reset | Tools > Account Data Reset (sim only) |
| Connection manager | Tools > Options > General |
| Data series | Tools > Historical Data |
| Export NinjaScript | Tools > Export NinjaScript |
| Import NinjaScript | Tools > Import NinjaScript |
| Output window | View > Output Window |

## Common NT8 Compile Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `CS0246` — type not found | Missing using statement or wrong namespace | Add `using NinjaTrader.NinjaScript.Indicators;` etc. |
| `CS0677` — volatile field type not allowed | Declared `volatile double/float` | Use `volatile int` or remove `volatile`; use `Interlocked` for thread safety |
| `CS0103` — name does not exist | Typo or wrong scope | Check spelling; confirm the variable/method exists in this class |
| `CS1061` — no definition for X | Method/property doesn't exist on type | Check NT8 API docs; confirm NT8 version |
| Duplicate type name | Two files define same class | Rename one class or delete the duplicate file |
| `The type ... is defined in assembly` | Assembly reference conflict | Clean bin/Custom/obj folders; restart NT8 |

## NinjaScript Namespace Rules

```csharp
// Indicators must be in:
namespace NinjaTrader.NinjaScript.Indicators { }
// or subfolder:
namespace NinjaTrader.NinjaScript.Indicators.DEEP6 { }

// Strategies must be in:
namespace NinjaTrader.NinjaScript.Strategies { }
// or subfolder:
namespace NinjaTrader.NinjaScript.Strategies.DEEP6 { }

// AddOns:
namespace NinjaTrader.NinjaScript.AddOns { }
```

## NT8 Data Flow for DEEP6

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

## NT8 Connection Types

| Connection | Purpose | Config location |
|-----------|---------|----------------|
| Market Data | Price/volume feed (Rithmic) | Connections menu > Configure |
| Order Router | Trade execution (Rithmic) | Connections menu > Configure |
| Playback | Historical simulation | Connections menu > Playback |

## DEEP6-Specific Files

| File | Location | Purpose |
|------|----------|---------|
| `DEEP6Strategy.cs` | Strategies/DEEP6/ | Main auto-trade strategy |
| `DEEP6Footprint.cs` | Indicators/DEEP6/ | Footprint chart rendering |
| `DataBridgeIndicator.cs` | Indicators/DEEP6/ | Exports DOM data to Python |
| `CaptureHarness.cs` | Indicators/DEEP6/ | Bar capture for backtesting |
| `DEEP6GexLevels.cs` | Indicators/DEEP6/ | GEX level overlay |

## NT8 Log Locations

| Log type | Path |
|---------|------|
| General log | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |
| Strategy analyzer | `C:\Users\Tea\Documents\NinjaTrader 8\strategyanalyzerlogs\` |
| Trace (verbose) | `C:\Users\Tea\Documents\NinjaTrader 8\trace\` |
| NinjaScript compile output | NT8 Output Window (View > Output Window) |

## Checking Compile Errors Without NT8 UI

Read the NT8 log for compile error lines:
```powershell
Get-Content "C:\Users\Tea\Documents\NinjaTrader 8\log\$(Get-Date -Format 'yyyy-MM-dd').txt" |
    Select-String -Pattern "error|Error|ERROR|compile|Compile"
```

## NT8 Window Management (PowerShell)

```powershell
# Find NT8 main window
$nt8 = Get-Process -Name "NinjaTrader" -ErrorAction SilentlyContinue
# Bring to foreground
Add-Type -Name Win32 -Namespace W -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);'
[W.Win32]::SetForegroundWindow($nt8.MainWindowHandle)
```

## SendKeys Reference (for UI automation)

```powershell
$wsh = New-Object -ComObject WScript.Shell
$wsh.AppActivate("NinjaTrader")
Start-Sleep -Milliseconds 300
$wsh.SendKeys("%t")          # Alt+T = Tools menu
Start-Sleep -Milliseconds 200
$wsh.SendKeys("n")           # n = NinjaScript Editor
Start-Sleep -Milliseconds 500
$wsh.SendKeys("{F5}")        # F5 = Compile
```

## NT8 Version Info (this machine)

- NT8 version: 8.x (check Help > About for exact build)
- NT8 executable: `C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe`
- .NET framework: NT8 uses .NET Framework 4.8 (not .NET Core)
- C# version: C# 7.3 features supported (not C# 8+)

## Important NT8 Constraints

- NT8 uses **.NET Framework 4.8** — no `async/await` in NinjaScript (or very limited)
- No `Span<T>`, no `ValueTuple` without explicit reference
- `volatile double` is **not allowed** (CS0677) — use `volatile int` or locks
- All UI operations must happen on the NT8 UI thread — use `Dispatcher.InvokeAsync()` or `TriggerCustomEvent()`
- `OnBarUpdate()` runs on a background thread — do not update UI directly
- Maximum recommended indicators per chart: 10-15 (performance degrades)

---

## Compile Success/Failure Detection (NEW — April 2026)

Key discovery: NT8 does **NOT** write CS#### compile errors to any log file. Errors exist **only** in the NT8 Output Window UI.

### Detection Strategy

| Signal | Path | Meaning |
|--------|------|---------|
| DLL timestamp | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll` | Updated **only** on successful compile |
| Install.xml | `C:\Users\Tea\Documents\NinjaTrader 8\log\Install.xml` — `<CompiledCustomAssembly>` element | Updated **only** on success |

**Detection algorithm**: record DLL `LastWriteTime` before triggering compile → poll until mtime changes (SUCCESS) or timeout elapses (FAILED).

**Error text retrieval**: errors are only available via UIAutomation — walk NT8's WPF tree to scrape the Output Window, or parse NT8 trace logs for the compile event.

### Scripts

| Script | Purpose | Output |
|--------|---------|--------|
| `nt8-compile.ps1` | Triggers compile via UI automation, uses DLL-timestamp detection | `[COMPILE-RESULT] SUCCESS` or `[COMPILE-RESULT] FAILED` |
| `nt8-errors.ps1` | UIAutomation-based Output Window scraper | JSON error array |
| `nt8-ai-loop.ps1` | Master orchestration: deploy → compile → return errors as JSON for Claude | JSON (errors or empty array on success) |

---

## VS 2022 Integration (NEW)

The full NT8 project is already on this machine:

```
C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.csproj
```

Open in VS 2022 for:
- Full IntelliSense against NT8 assemblies (`NinjaTrader.Core.xml` ships with NT8)
- F12 Go-to-Definition into decompiled NT8 internals
- Breakpoint debugging: NT8 NSE → enable Debug Mode → VS 2022 → Debug → Attach to Process → `NinjaTrader.exe`

**CRITICAL**: Do **NOT** click Build in VS. NT8 owns compilation. VS is editor + debugger only. Save in VS → NT8 file watcher triggers auto-recompile (NinjaScript Editor must be open).

---

## F5 on Chart = In-Place Reload (NEW)

Click the **chart window** (not the NinjaScript Editor), then press **F5** → indicator reloads in place with all parameters preserved.

Do NOT remove and re-add the indicator. This is the fastest iteration path once an indicator is on the chart.

---

## ninjatrader-autodocs MCP (NEW)

Added to `.claude/settings.json` as `"ninjatrader-autodocs"` — a gitmcp server serving reflection-generated NT8 API signatures with LLM-generated comments.

When Claude has this in context, it can look up actual method signatures before generating code, eliminating CS1061 (method doesn't exist) errors.

**URL**: `https://gitmcp.io/matdev83/ninjatrader-autodocs`

---

## AI Code Generation Workflow (NEW)

Standard AI-assisted NinjaScript workflow for DEEP6:

1. Load `ninjatrader/ninjascript-ai-context.md` into context
2. Provide the relevant existing DEEP6 indicator as a template (few-shot example)
3. Describe the new indicator in if/then logic referencing specific NT8 series (`Close[0]`, `Volume[0]`, etc.)
4. Ask Claude to write **only** the `OnBarUpdate()` body first — wrap it in the shell yourself
5. Run `nt8-ai-loop.ps1` — deploy + compile + get errors as JSON
6. Paste JSON errors back to Claude → fix → repeat (usually 1–3 iterations with grounded context)

**Community finding**: Claude Sonnet/Opus outperforms GPT-4o on NinjaScript generation. Claude is significantly better at fixing errors when given the full error text vs generating from scratch.

---

## UIAutomation Error Reading (VERIFIED — April 2026)

The ONLY way to read full compile error messages from NT8. CS#### errors are NOT in any log file.

### Working PowerShell code (tested and verified):
```powershell
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$nt8 = Get-Process "NinjaTrader" -ErrorAction SilentlyContinue
$root = [System.Windows.Automation.AutomationElement]::RootElement
$pidCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $nt8.Id)
$windows = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $pidCond)

$nse = $null
foreach ($w in $windows) { if ($w.Current.Name -like "*NinjaScript*") { $nse = $w; break } }

$gridCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::DataGrid)
$grid = $nse.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $gridCond)

$rows = $grid.FindAll([System.Windows.Automation.TreeScope]::Children, 
    [System.Windows.Automation.Condition]::TrueCondition)

foreach ($row in $rows) {
    $cells = $row.FindAll([System.Windows.Automation.TreeScope]::Children, 
        [System.Windows.Automation.Condition]::TrueCondition)
    $vals = @()
    foreach ($cell in $cells) {
        try {
            $vp = $cell.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
            $v = $vp.Current.Value
            if ($v) { $vals += $v }
        } catch { }
    }
    # vals[0]=empty, vals[1]=filename, vals[2]=message, vals[3]=code, vals[4]=line, vals[5]=col
    # Header row has "NinjaScript File", "Error", "Code" etc. -- skip it
    $codeVal = $vals | Where-Object { $_ -match "^CS\d{4}$" } | Select-Object -First 1
    if ($codeVal) {
        Write-Host "FILE: $($vals[1]) LINE: $($vals[4]) CODE: $codeVal"
        Write-Host "MSG: $($vals[2])"
    }
}
```

### NT8 window discovery:
- 3 top-level windows by PID: unnamed (WindowsForms), "NinjaScript Editor - New tab" (WPF), "ControlCenter"
- Find NSE by: `$w.Current.Name -like "*NinjaScript*"`
- The error DataGrid is inside the NSE window
- DataGrid rows: first row = header (values are column names); subsequent rows = errors
- Each error row has 6 cells: empty | filename | message | code | line | column

---

## Critical Lessons (April 2026 Session)

### Deploy bug -- -Target AddOns deploys everything recursively
`nt8-deploy.ps1 -Target AddOns` copies ALL files from `ninjatrader/Custom/AddOns/` recursively, including subdirectory files that may also be in `ninjatrader/Custom/Indicators/`. This caused CS0101 (duplicate type) errors.

**Workaround**: For AddOns deployment, manually copy ONLY the intended .cs file:
```powershell
Copy-Item ".\ninjatrader\Custom\AddOns\DEEP6\DEEP6DevAddon.cs" `
          "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\AddOns\DEEP6\DEEP6DevAddon.cs" -Force
```

### Enum placement rule (CRITICAL)
NT8 generates boilerplate factory methods in 3 namespaces: `Indicators`, `MarketAnalyzerColumns`, `Strategies`. If an indicator has a public property of a custom enum type, that enum MUST be at GLOBAL namespace level (no namespace wrapper).

**WRONG** (causes CS0246 in generated boilerplate):
```csharp
namespace NinjaTrader.NinjaScript.Indicators {
    public enum Tier { Q, C, B, A, S }  // WRONG: inside namespace
    public class DEEP6Signal : Indicator { ... }
}
```

**CORRECT** (matches @BlockVolume.cs built-in pattern):
```csharp
public enum Tier { Q, C, B, A, S }  // CORRECT: global namespace, before ALL namespace declarations

namespace NinjaTrader.NinjaScript.Indicators {
    public class DEEP6Signal : Indicator { ... }
}
```

Reference: `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\Indicators\@BlockVolume.cs` lines 101-105 shows the correct pattern.

### Truncated filenames from bad deploy
A previous deploy run created files with truncated names (`vels.cs`, `rint.cs`, `l.cs`) in NT8 Custom folders. These contain the full file content but are unreachable by the correct name.

**Fix**: Delete the entire affected subfolder, then redeploy:
```powershell
Remove-Item "$env:USERPROFILE\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6" -Recurse -Force
# Then redeploy from repo
```

### Pre-existing compile failure detection
If DLL mtime hasn't changed in >24 hours, compile has been broken for a while. Check both:
1. `(Get-Item $dll).LastWriteTime` -- when DLL was last successfully compiled
2. `$xml.SelectSingleNode("//CompiledCustomAssembly").InnerText` in Install.xml -- NT8-confirmed compile timestamp

If these don't match (DLL newer than Install.xml), NT8 wrote the DLL but didn't update Install.xml -- investigate.

### Compile success detection timing
The DLL timestamp check needs a 500ms polling interval. Compile takes 3-30 seconds depending on number of files. Set `-TimeoutSeconds 45` for safety (default 30 may be too short for large files).
