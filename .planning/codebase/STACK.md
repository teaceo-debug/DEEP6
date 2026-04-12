# Technology Stack

**Analysis Date:** 2026-04-11

## Languages

**Primary:**
- C# 10.0 - NinjaScript indicator for NinjaTrader 8, compiled against .NET Framework 4.8 (`/Users/teaceo/DEEP6/Indicators/DEEP6.cs`)

**Secondary:**
- PowerShell 5.1+ - Deployment and watch scripts (`/Users/teaceo/DEEP6/scripts/Deploy-ToNT8.ps1`, `Watch-AndDeploy.ps1`, `Trigger-NT8Compile.ps1`)

## Runtime

**Environment:**
- .NET Framework 4.8 - Required by NinjaTrader 8. Compiles against `net48` target framework (DEEP6.csproj line 4)

**SDK for Development:**
- .NET SDK 7.0+ - Used for local compilation via `dotnet build` and IntelliSense in VS Code. Not used by NT8 runtime; NT8 has its own embedded .NET Framework 4.8

**Package Manager:**
- NuGet - Implicit; no external NuGet dependencies. All required assemblies come from NinjaTrader 8 installation

## Frameworks

**Core:**
- NinjaTrader 8 (NT8) NinjaScript - Main application framework. Indicator derives from `Indicator` base class in `NinjaTrader.NinjaScript.Indicators` namespace (DEEP6.cs line 48, 58)
- Required NT8 assemblies (all referenced in DEEP6.csproj lines 46-74):
  - `NinjaTrader.Core.dll` - Core platform APIs
  - `NinjaTrader.Client.dll` - Client-side chart and UI APIs
  - `NinjaTrader.Data.dll` - Market data and bars
  - `NinjaTrader.Gui.dll` - WPF integration for custom UI
  - `NinjaTrader.NinjaScript.dll` - NinjaScript base types
  - `NinjaTrader.NinjaScript.AddOns.dll` - Add-on framework
  - `NinjaTrader.Custom.dll` - Custom indicator bridge

**UI/Graphics:**
- WPF (Windows Presentation Foundation) - Used for custom UI elements: header bar, left tab bar, status pills, right panel with tabs. References: `PresentationCore`, `PresentationFramework`, `System.Xaml`, `System.Windows.Forms` (DEEP6.csproj lines 102-111)
- SharpDX - DirectX/Direct2D wrapper for high-performance chart rendering (footprint cells, delta rows, signal boxes, price level lines). Direct2D used for vector graphics, DirectWrite for text rendering
  - `SharpDX.dll` - Core DirectX bindings
  - `SharpDX.Direct2D1.dll` - 2D vector graphics rendering
  - `SharpDX.DirectWrite.dll` - Text layout and rendering
  - `SharpDX.Mathematics.dll` - Vector/matrix math utilities
  - Referenced in DEEP6.cs lines 12-13, initialized in OnRender handler (line 259, implemented in RenderFP/RenderSigBoxes/RenderStk methods)

**Build/Dev:**
- dotnet CLI - Builds via `dotnet build DEEP6.csproj` configured in VS Code tasks (tasks.json lines 9-25)
- MSBuild - Underlying build system; custom target `DeployToNT8` post-build (DEEP6.csproj lines 124-132) auto-copies compiled indicator to NT8 Custom folder

## Key Dependencies

**Critical (Built-in, from NT8):**
- NinjaTrader 8 Core Assemblies (see "Frameworks" section) - No external installation; path resolved via `$(NT8Path)` variable (default: `C:\Program Files\NinjaTrader 8`)
- VolumetricBarsType - Requires NT8 Lifetime License + Order Flow+ subscription. DEEP6 detects and uses Volumetric Bars for footprint data (`NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType` cast in DEEP6.cs lines 219, 309, 338, 463)

**Infrastructure:**
- WPF Framework (Windows only) - Used for dynamic UI panel creation (StackPanel, Grid, Label, CheckBox, ComboBox, etc.)
- SharpDX - Vendored or provided by NT8 installation. Used for real-time chart rendering (OnRender override, lines 259-266)
- EMA Indicator (NinjaTrader built-in) - Referenced as `NinjaTrader.NinjaScript.Indicators.EMA` for 20-period exponential moving average (DEEP6.cs line 129, instantiated in OnStateChange, State.DataLoaded)

## Configuration

**Environment:**
- NT8 Installation Path - Resolved via `$(NT8Path)` property in DEEP6.csproj (default: `C:\Program Files\NinjaTrader 8`). Can be overridden via environment variable or MSBuild parameter: `dotnet build /p:NT8Path="D:\NT8"`
- NT8 Custom Folder - Resolved via `$(NT8CustomPath)` = `$(USERPROFILE)\Documents\NinjaTrader 8\bin\Custom`. Build post-target auto-copies `Indicators\DEEP6.cs` here after compilation (DEEP6.csproj lines 124-132)

**Build:**
- DEEP6.csproj - .NET SDK project file (SDK="Microsoft.NET.Sdk")
  - Debug configuration: full symbols, no optimization (DEEP6.csproj lines 26-31)
  - Release configuration: optimized, no debug info (lines 33-37)
  - Output: x64 only, library DLL in `bin\` folder (lines 12-13, 17-18)
  - Documentation XML: generated to `bin\DEEP6.xml` (line 14)
  - Warnings suppressed: CS0618 (obsolete), CS1591 (missing docs), CS0108/CS0114 (member hiding) — acceptable for NT8 hot-path code (line 16)

**Code Style:**
- `.editorconfig` (DEEP6/.editorconfig) - EditorConfig for C# style enforcement
  - Indentation: 4 spaces for C#
  - Line length: max 120 characters
  - Naming: `_camelCase` for private fields, `ALL_CAPS` for const
  - Formatting: Brace style `none`, no newline before `else`/`catch`/`finally`
  - Expression bodies enabled for properties/accessors/lambdas
  - Roslyn analyzer exclusions: CS0618 (obsolete), CS1591 (missing XML docs)

## Platform Requirements

**Development:**
- Windows 10/11 64-bit - PowerShell 5.1+, VS Code with C# Dev Kit extension
- NinjaTrader 8 - 8.0.23+ with Lifetime License (required for Volumetric Bars)
- .NET SDK 7.0+ - For local compilation and IntelliSense (not used by NT8)
- Rithmic Data Feed - Level 2 DOM with 40+ depth levels (E2/E3/E4 engines depend on this)

**Production (Runtime):**
- Windows 10/11 64-bit (x64 only, see line 17 `<PlatformTarget>x64</PlatformTarget>`)
- NinjaTrader 8 (8.0.23+) with:
  - Lifetime License
  - Order Flow+ subscription (for Volumetric Bars)
  - Rithmic Level 2 DOM data feed (40+ levels)
  - Calculate mode: OnEachTick (required for 1,000 callbacks/second tick processing)

**Hardware (Recommended):**
- CPU: i7-12700K / Ryzen 7 7700X minimum (i9-14900K / Ryzen 9 7950X recommended)
- RAM: 32GB DDR4 minimum (64GB DDR5 recommended)
- Storage: NVMe SSD 512GB minimum (2TB recommended, 7,000 MB/s)
- GPU: 4GB VRAM minimum (RTX 3060 8GB recommended) for SharpDX rendering
- Network: 1Gbps Ethernet (NOT WiFi), latency <20ms to CME Aurora preferred
- OS: Windows 11 Pro preferred (Windows 10 Pro supported)

---

*Stack analysis: 2026-04-11*
