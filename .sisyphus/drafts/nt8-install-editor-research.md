# NT8 Installation, Uninstallation & NinjaScript Editor Research

> **Purpose:** Universal NinjaTrader 8 knowledge for incorporation into the `ninjatrader-machine-profile` opencode skill. All content is generic NT8 — no project-specific references.
>
> **Sources:** NinjaTrader official help guides, developer docs, support forum, official PDF guides.

---

## Installation

### System Requirements

#### Minimum
| Requirement | Specification |
|---|---|
| OS | Windows 11, Windows Server 2016 or later (64-bit) |
| CPU | 1 GHz or faster 64-bit processor |
| RAM | 2 GB |
| .NET | Microsoft .NET Framework 4.8 (pre-installed on most PCs) |
| Display | 1024 x 768 screen resolution |
| GPU | DirectX 10 compatible graphics card (highly recommended) |

#### Recommended
| Requirement | Specification |
|---|---|
| CPU | 2 GHz or faster quad-core 64-bit processor |
| RAM | 8 GB |
| GPU | DirectX 10 compatible graphics card |
| Storage | SSD hard drive |

> NT8 utilizes all available CPU cores and additional memory. Strategy optimizations benefit directly from more RAM proportional to CPU core count.

### Download & Install Steps

1. **Ensure .NET 4.8** is installed. Download from https://dotnet.microsoft.com/download/dotnet-framework/net48 if missing.
2. **Log in** to your NinjaTrader account at https://account.ninjatrader.com/welcome
3. **Import license** (if existing): Settings → Plans → Import a License. Upgrades auto-import.
4. **Download:** Select "Download" from the left menu in your account dashboard. Choose latest release or a specific version.
5. **Run the installer.** Close any previous NT8 instance before running.
6. **Firewall:** Grant NinjaTrader internet access — it contacts NinjaTrader servers on login for validation. Failure to whitelist causes login errors.
7. **Connect to broker:** Follow the appropriate Connection Guide to establish a connection to your broker or data feed provider.

> **Warning:** Exclude `Documents\NinjaTrader 8\` from cloud backup services (Dropbox, OneDrive, etc.) — cloud sync creates file access conflicts that corrupt workspaces and data.

### License Types

| License | Features | Cost |
|---|---|---|
| Free / Sim | Full platform with simulated trading, paper trading, backtesting, market replay. No real-money trading. | Free |
| Lease | Full platform + live trading. Monthly/annual subscription. | Varies |
| Lifetime | Full platform + live trading. One-time purchase. | One-time fee |

- Free license provides full charting, NinjaScript development, strategy backtesting, and sim trading.
- Live trading requires a paid license (lease or lifetime) AND a connected funded brokerage account.
- All licenses use the same installer — the license key determines feature access.

### Broker Connection Setup

**Test Environment (Free):**
- NinjaTrader provides a simulated data feed connection for development and testing.
- Control Center → Connections → configure "Simulated Data Feed" — no broker account needed.
- Playback connection lets you replay historical data.

**Live Broker Connection:**
1. Control Center → Connections → configure connection.
2. Select your broker from the dropdown (e.g., NinjaTrader Brokerage, Rithmic, CQG, Interactive Brokers).
3. Enter credentials provided by your broker.
4. For Rithmic: broker must enable "API/plugin mode" — test environment URL: `wss://rituz00100.rithmic.com` (free for development).
5. Connection status shown in Control Center status bar.

### First Launch

- On first launch after fresh install, NT8 creates the `Documents\NinjaTrader 8\` folder structure automatically.
- You will be prompted to log in with your NinjaTrader account credentials.
- The default workspace opens with the Control Center window.
- Connection wizard or manual connection setup follows.

---

## Uninstallation & Clean Reinstall

### Standard Uninstall (Preserves Settings)

Use when you want to remove NT8 but keep your settings, workspaces, and custom scripts for later:

1. Close NinjaTrader completely (check Task Manager — ensure no `NinjaTrader.exe` processes).
2. Navigate to `Documents\NinjaTrader 8\` → **rename** to `NinjaTrader 8 OLD` (do NOT delete).
3. Uninstall NinjaTrader via Windows: Start → Settings → Apps, or Control Panel → Programs & Features.
4. Navigate to `C:\Program Files (x86)\` → delete the `NinjaTrader 8` folder if it still exists.
5. Reboot PC.

### Complete Uninstall (Full Wipe)

Per the official NinjaTrader Uninstallation Guide PDF:

1. Close all running applications.
2. Navigate to `Documents` folder → **delete** the `NinjaTrader 8` folder.
3. Uninstall NinjaTrader via Windows Control Panel.
4. Navigate to `C:\Program Files (x86)\` → delete the `NinjaTrader 8` folder if it exists.

> **This permanently removes ALL settings, workspaces, templates, custom scripts, indicators, strategies, historical data, and market replay files.**

### Clean Reinstall (Fresh Start + Restore)

Use when NT8 is sluggish, crashes on launch, or has corrupted files:

1. **Shut down** NinjaTrader completely.
2. **Rename** `Documents\NinjaTrader 8\` to `NinjaTrader 8 OLD`.
3. **Uninstall** via Windows Control Panel.
4. **Delete** `C:\Program Files (x86)\NinjaTrader 8\` if it exists.
5. **Reboot** PC.
6. **Download and install** fresh from your NinjaTrader account dashboard.
7. **Launch** — this creates a brand-new `Documents\NinjaTrader 8\` with default settings.
8. **Verify** the base platform works (open a chart, connect to sim data).

**Selective Restore (from OLD folder):**

Restore one folder/file at a time, testing between each:

| Order | Item | Path in Documents\NinjaTrader 8\ | Notes |
|---|---|---|---|
| 1 | Config file | `Config` | Connection settings |
| 2 | UI layout | `UI.xml` | Window layout. If NT8 won't launch, rename to `OldUI.xml` |
| 3 | Templates | `templates\` | Chart, indicator, strategy templates |
| 4 | Workspaces | `workspaces\` | Saved workspace layouts |
| 5 | Custom scripts | `bin\Custom\` | NinjaScript indicators, strategies, add-ons |
| 6 | Database | `db\` | Historical data, NinjaTrader.sqlite |

> **Key principle:** Restore one item → relaunch NT8 → test. If issue returns, that item is corrupt. Remove it and skip.

### Platform Repair (Before Full Reinstall)

Before doing a full reinstall, try a repair:

1. Control Panel → Programs & Features.
2. Left-click NinjaTrader 8 → select **Repair**.
3. Let repair complete → relaunch and test.

If repair doesn't fix the issue, proceed to clean reinstall.

### What NT8 Leaves Behind After Uninstall

| Location | Contents | Preserved? |
|---|---|---|
| `Documents\NinjaTrader 8\` | All user data, workspaces, templates, custom scripts, database | Yes (uninstaller does NOT touch this) |
| `C:\Program Files (x86)\NinjaTrader 8\` | Platform binaries | Usually removed, but verify |
| Registry entries | License, settings | Removed by uninstaller |

> The `Documents\NinjaTrader 8\` folder is **never** deleted by the uninstaller. You must manually delete or rename it.

### Safe Mode Test

If NT8 won't launch, try Safe Mode to rule out 3rd-party add-on interference:

1. Shut down NinjaTrader fully.
2. Hold `Ctrl` key while launching NinjaTrader.
3. This loads NT8 without 3rd-party scripts.
4. If it launches in Safe Mode, the issue is a corrupt or incompatible add-on.

### Resetting UI Layout

If NT8 hangs on launch or windows are misarranged:

1. Shut down NinjaTrader.
2. Go to `Documents\NinjaTrader 8\`.
3. Rename `UI.xml` to `OldUI.xml`.
4. Relaunch — NT8 creates a fresh default UI layout.

---

## NinjaScript Editor

### Opening the Editor

| Method | Steps |
|---|---|
| Menu | Control Center → New menu → NinjaScript Editor |
| Chart right-click | Right-click indicator on chart → "Edit NinjaScript" (opens that script directly) |

> Note: There is no single global hotkey (like F12) that opens the NinjaScript Editor from anywhere. You access it through the New menu or by editing a specific script.

### Editor Layout & Panes

The NinjaScript Editor window contains:

1. **NinjaScript Explorer** (left/right panel) — folder tree of all scripts by type (Indicators, Strategies, AddOns, etc.)
2. **Toolbar** — icons for common actions (compile, new, save, etc.)
3. **Code editor** — main editing area with line numbers
4. **Line modification markers** — yellow = unsaved changes, green = saved changes
5. **Tabs** — work on multiple scripts simultaneously
6. **Compile errors panel** (bottom) — errors/warnings appear here after compilation

### Editor Properties

| Setting | Description |
|---|---|
| Auto hide NinjaScript explorer | Collapse explorer by default |
| Debug mode | Generate debug DLL for Visual Studio attachment |
| Inline syntax checking | Detect errors/warnings as you type (without compiling) |
| Auto bracket completion | Auto-close `()`, `[]`, `{}`, `<>` |
| Show indentation lines | Display vertical indent guides |
| Show Warnings | Show compiler warnings alongside errors |

### Intelliprompt (Auto-Complete)

- Type `this.` to display the full list of available methods and properties.
- `Ctrl+Space` after partial text: brings up auto-complete list or auto-inserts if unique match.
- `Ctrl+Shift+Space`: show method parameter signatures.
- Use arrow keys to scroll the list, then `Tab` or `Enter` to insert.
- Type any letter while in the list to jump to items starting with that letter.
- Method signatures: type `(` after a method name to see descriptions and overloads. Arrow up/down to scroll through overloads (e.g., "1 of 3").

### Context Menu (Right-Click)

| Item | Description |
|---|---|
| Save | Save current script |
| Save As | Copy script with auto-renamed class |
| Insert Code Snippet | Insert predefined code template |
| Go To Line... | Jump to specific line number |
| Undo / Redo | Standard undo/redo |
| Cut / Copy / Paste / Remove | Standard clipboard operations |
| Select All | Select entire file |
| Debug Mode | Toggle debug DLL generation |
| References... | View/manage DLL references used by NinjaTrader |
| Show Warnings | Toggle warning display |
| Always On Top | Pin editor above other windows |
| Print / Share | Output content |
| Properties | Open editor settings |

### Code Snippets

The NinjaScript Editor supports insertable code snippets for common patterns. Access via right-click → Insert Code Snippet. Snippets provide template code for event handlers, properties, and common NinjaScript patterns.

---

## Compiling NinjaScript

### How to Compile

| Method | Action |
|---|---|
| **F5** | Compile **all** NinjaScript files (full rebuild) |
| Right-click → Compile | Same as F5 |
| Toolbar compile icon | Same as F5 |

> **Critical:** F5 compiles ALL NinjaScript files — not just the open file. All custom scripts are compiled into a single `NinjaTrader.Custom.dll` assembly for performance. A single broken script blocks compilation of everything.

### Reading Compile Errors

Errors appear in the panel at the bottom of the NinjaScript Editor:

| Element | Description |
|---|---|
| Error list | Light-colored rows = errors in currently open file; dark rows = errors in other files |
| File column | Which `.cs` file contains the error |
| Description | Human-readable error message |
| Error code | Clickable link (e.g., CS0246) — opens help documentation |
| Line:Column | Exact location in source code |
| Red wavy underline | Visual marker in the code editor on the error line |

### Error Navigation

- **Double-click** an error row → loads the problem file and highlights the error line.
- **Click the error code** link → opens NT8 help guide for that specific error.
- **Right-click** an error → option to "Exclude From Compilation" (ignore the problem file).
  - "Exclude From Compilation" — ignores only the selected file.
  - "Exclude All From Compilation" — ignores all files with errors.

### Excluding Scripts from Compilation

When a script you can't fix is blocking compilation of everything else:

1. In NinjaScript Explorer: right-click the script → "Exclude From Compilation".
2. Or from the error panel: right-click → "Exclude From Compilation" / "Exclude All From Compilation".
3. Excluded scripts appear **faded** in the NinjaScript Explorer.
4. To re-include: right-click the faded script → uncheck "Exclude From Compilation".

> This is essential when 3rd-party add-ons cause errors — exclude them to compile your own code.

---

## NinjaScript Explorer

### Overview

The NinjaScript Explorer is a folder tree panel inside the NinjaScript Editor showing all script categories:

- **Locked scripts** — pre-built system scripts (read-only, required for compilation)
- **Custom scripts** — user-created or imported scripts (editable)
- **Ignored scripts** — scripts excluded from compilation (faded display)

### Script Management

| Action | Method |
|---|---|
| Open script | Double-click, or right-click → Open |
| Open in new editor | Right-click → Open In New NinjaScript Editor |
| Create new script | Right-click category → New... (opens NinjaScript Wizard) |
| Create folder | Right-click → New Folder |
| Rename | Right-click → Rename, or select + F2 |
| Remove/delete | Right-click → Remove, or select + DEL key |
| Move script | Drag and drop within same category |
| Exclude from compile | Right-click → Exclude From Compilation |

### Folder Rules

- Folders created in the Explorer are mirrored in the file system: `Documents\NinjaTrader 8\bin\Custom\{Category}\{YourFolder}\`
- Cannot move locked system scripts.
- Can only move/rename closed scripts.
- Scripts can only move within their own category (indicators stay under Indicators, etc.).
- Moving a child script called by a parent requires updating the namespace reference.

> **Warning:** Folder changes made directly in Windows File Explorer are NOT reflected in the NinjaScript Editor. Always manage folders from within the editor.

### NinjaScript Wizard

Right-click a category → New... opens the NinjaScript Wizard:
- Generates boilerplate code for the selected script type (Indicator, Strategy, AddOn, etc.)
- Sets up the correct class inheritance, namespaces, and required method stubs.
- Creates the `.cs` file in the appropriate folder.

---

## Output Window

### Overview

The NinjaScript Output window displays debugging output from `Print()` calls and `TraceOrders` in strategies. It only shows data when scripts actively write to it.

### Opening

- Control Center → New menu → NinjaScript Output

### Features

| Feature | Description |
|---|---|
| Two tabs | Separate output streams (Tab 1 / Tab 2) for different scripts |
| Click to highlight | Left-click a line to pin-highlight it; stays highlighted during scrolling |
| Dual view | Right-click → Dual View — split both tabs side-by-side |
| Synchronized scrolling | In dual view, right-click → Synchronized Vertical Scrolling — both tabs scroll together |
| Find (Ctrl+F) | Search for text, optionally case-sensitive, highlights all matches |
| Double-click text | Auto-highlights that term across the entire output |
| Clear | Right-click → Clear — erase all output in current tab |
| Save As | Right-click → Save As — export output as `.txt` file |
| Utilization monitor | Right-click → NinjaScript Utilization — diagnostic tool for performance issues |

---

## Keyboard Shortcuts (NinjaScript Editor)

### Compilation
| Shortcut | Action |
|---|---|
| **F5** | **Compile all NinjaScript files** |

### Clipboard & Editing
| Shortcut | Action |
|---|---|
| Ctrl+C / Ctrl+Insert | Copy |
| Ctrl+X / Shift+Delete | Cut |
| Ctrl+L | Cut entire line |
| Ctrl+V / Shift+Insert | Paste |
| Ctrl+Z | Undo |
| Ctrl+Y / Ctrl+Shift+Z | Redo |
| Ctrl+Backspace | Backspace to previous word |
| Ctrl+Delete | Delete to next word |
| Ctrl+Shift+L | Delete entire line |

### Code Intelligence
| Shortcut | Action |
|---|---|
| Ctrl+Space | Intelliprompt auto-complete |
| Ctrl+Shift+Space | Show method parameter info |

### Line Operations
| Shortcut | Action |
|---|---|
| Ctrl+Enter | Open new line above |
| Ctrl+Shift+Enter | Open new line below |
| Alt+Up | Move selected lines up |
| Alt+Down | Move selected lines down |
| Shift+Tab | Remove tab indent |

### Text Transforms
| Shortcut | Action |
|---|---|
| Ctrl+T | Transpose characters |
| Ctrl+Shift+T | Transpose words |
| Shift+Alt+T | Transpose lines |
| Ctrl+Shift+U | Make uppercase |

### Navigation
| Shortcut | Action |
|---|---|
| Ctrl+Left | Move to previous word |
| Ctrl+Right | Move to next word |
| Ctrl+Home | Move to document start |
| Ctrl+End | Move to document end |
| Ctrl+PageUp | Move to visible top |
| Ctrl+PageDown | Move to visible bottom |
| Ctrl+] | Move to matching bracket |
| Ctrl+Up | Scroll up |
| Ctrl+Down | Scroll down |

### Selection
| Shortcut | Action |
|---|---|
| Shift+PageUp | Select all above |
| Shift+PageDown | Select all below |
| Ctrl+Shift+PageUp | Select visible area above |
| Ctrl+Shift+PageDown | Select visible area below |
| Ctrl+Shift+W | Select word |
| Ctrl+Shift+] | Select to matching bracket |
| Shift+Alt+Arrow Keys | Expand/contract selection region |

### Explorer & File Management
| Shortcut | Action |
|---|---|
| F2 | Rename selected script |
| DEL | Delete selected script |

---

## Workspace Management

### What is a Workspace?

A workspace saves the complete window arrangement: which charts, Market Analyzers, SuperDOMs, and other windows are open and how they're positioned. Workspaces are stored as files in `Documents\NinjaTrader 8\workspaces\`.

### Creating & Managing Workspaces

| Action | Steps |
|---|---|
| Save current workspace | Control Center → Workspaces menu → Save |
| Save to new name | Control Center → Workspaces menu → Save As → enter name |
| Switch workspace | Control Center → Workspaces menu → select workspace name |
| Delete workspace | Control Center → Workspaces menu → manage/remove |

### Import / Export Workspaces

| Action | Steps |
|---|---|
| Export | Control Center → Workspaces → Export → check workspaces → Export → choose filename |
| Import | Control Center → Workspaces → Import → select `.xml` workspace file |

### Workspace Recovery

- By default, NT8 retains **10 previously saved versions** of each workspace.
- Restore via: Control Center → Tools → Database Management → Restore Workspace.
- Configure retention count: Control Center → Tools → Options → General → Preferences → "Versions of recovery workspaces".

### File Location

- Workspaces: `Documents\NinjaTrader 8\workspaces\`
- Sub-folders in the workspaces directory are NOT visible in the platform menu.
- Copy/paste workspace files only when NT8 is fully closed.
- If Documents folder is redirected (e.g., to OneDrive), workspaces follow the redirect.

---

## NT8 Data Folder Structure

Standard locations under `Documents\NinjaTrader 8\`:

| Path | Contents |
|---|---|
| `bin\Custom\` | All NinjaScript source files (Indicators, Strategies, AddOns, etc.) |
| `bin\Custom\NinjaTrader.Custom.dll` | Compiled NinjaScript assembly |
| `db\` | Database folder |
| `db\NinjaTrader.sqlite` | Main database (instruments, accounts, etc.) |
| `db\day\`, `db\minute\`, `db\tick\` | Historical price data |
| `db\replay\` | Market Replay compressed data files |
| `templates\` | Template root |
| `templates\Chart\` | Chart templates |
| `templates\Strategy\` | Strategy templates |
| `templates\Indicator\` | Indicator templates |
| `templates\MarketAnalyzer\` | Market Analyzer templates |
| `workspaces\` | Workspace layout files |
| `Config` | Connection configuration |
| `UI.xml` | Window layout state |
| `log\` | Application log files |

---

## Backup & Restore

### Creating a Backup

1. Disconnect from all data providers.
2. Control Center → Tools → Export → Backup File...
3. Select items to back up:

| Item | Description |
|---|---|
| NinjaScript files | Custom indicators, strategies, add-ons |
| Templates | Chart, indicator, strategy templates |
| Workspaces | Window layout files |
| Settings | Platform configuration |
| Market replay | Level 1 & 2 replay data |
| Historical data | Chart data (day/minute/tick) |

4. Press Export → choose location and filename.
5. Default location: `Documents\NinjaTrader 8 Backup\` with date as filename.

> **Tip:** Historical data and market replay can often be re-downloaded from your data provider. Exclude them to save backup time and space.

### Restoring a Backup

1. Control Center → Tools → Import → Backup File...
2. Select the backup `.zip` file.
3. Choose which items to restore.

---

## Market Replay

### Data Location

- Replay files: `Documents\NinjaTrader 8\db\replay\`
- Files are compressed and can be shared by copying to another NT8 installation.
- Alternatively, use Backup & Restore to create a portable backup.

### Playback Connection

- Two data types: **Market Replay** (recorded L1/L2 data) and **Historical** (tick data).
- NinjaTrader servers provide downloadable replay data for popular Futures and Forex instruments.
- Access via Control Center → Connections → Playback.

---

## Adding Scripts to Charts After Compiling

### Adding an Indicator
1. Right-click on chart → Indicators...
2. Find your indicator in the available list.
3. Configure properties in the panel.
4. Click OK/Apply.

### Adding a Strategy
1. Right-click on chart → Strategies...
2. Find your strategy in the available list.
3. Configure properties.
4. Click OK/Apply.
5. For automated strategies: enable the strategy from the Strategies tab in Control Center.

### Import/Export NinjaScript

**Import:**
- Control Center → Tools → Import → NinjaScript Add-On...
- Select the `.zip` file provided by the vendor.
- NT8 extracts and places files in the correct folders.
- Compile after import.

**Export:**
- NinjaScript Editor → right-click script → Export...
- Creates a distributable `.zip` file.

---

## Connection Reference

### Built-in Connection Types
| Connection | Purpose |
|---|---|
| Simulated Data Feed | Free simulated market data for testing |
| Playback | Replay historical or recorded market data |
| NinjaTrader Brokerage | Direct NT8 brokerage connection |
| Rithmic | Third-party data + execution |
| CQG | Third-party data + execution |
| Interactive Brokers | Third-party data + execution |
| Kinetick | Market data only (EOD free, real-time paid) |

### Test Environment
- Simulated Data Feed requires no account or credentials.
- Provides simulated bid/ask/last data for all instruments.
- Suitable for NinjaScript development, strategy backtesting, and UI familiarization.

---

## Sources

| Source | URL |
|---|---|
| Installation Guide | https://ninjatrader.com/support/helpguides/nt8/installation_guide.htm |
| System Requirements | https://ninjatrader.com/support/helpguides/nt8/minimum_system_requirements.htm |
| Uninstallation Guide (PDF) | https://ninjatrader.com/PDF/NinjaTrader-Uninstallation-Guide.pdf |
| NinjaScript Editor Components | https://ninjatrader.com/support/helpGuides/nt8/ns_editor_components.htm |
| NinjaScript Explorer | https://ninjatrader.com/support/helpGuides/nt8/ns_explorer.htm |
| Compile Errors | https://ninjatrader.com/support/helpguides/nt8/compile_errors.htm |
| Intelliprompt | https://ninjatrader.com/support/helpGuides/nt8/intelliprompt.htm |
| Output Window | https://ninjatrader.com/support/helpguides/nt8/output.htm |
| Editor Keyboard Shortcuts | https://ninjatrader.com/support/helpguides/nt8/editor_keyboard_shortcuts.htm |
| Workspaces Menu | https://ninjatrader.com/support/helpguides/nt8/workspaces_menu.htm |
| Backup & Restore | https://ninjatrader.com/support/helpguides/nt8/creating_a_backup_archive.htm |
| Playback Data Files | https://ninjatrader.com/support/helpGuides/nt8/data_files.htm |
| Clean Install Forum Thread | https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/1317674 |
| Re-install Keep Workspaces Forum | https://forum.ninjatrader.com/forum/ninjatrader-8/platform-technical-support-aa/1329965 |
| Developer Docs (Editor Overview) | https://developer.ninjatrader.com/docs/desktop/ninjascript_editor_overview |
