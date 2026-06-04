# Display Topology Skill

Invoke this skill when the user asks you to:
- Take a screenshot of a specific application window
- Find which screen an application is on
- Interact with UI elements across multiple monitors
- Position or find windows for NinjaTrader, TradingView, or any application
- Understand the monitor layout for UI automation
- Debug display or window positioning issues

## Skill Entry Point

Load `knowledge.md` in this directory for the complete 4-screen monitor map,
Windows coordinate system, and runtime window detection commands.

## Workflow

1. Load `knowledge.md` to understand the 4-screen topology
2. Use the Screen Mapping Table to translate between user names (Screen 1–4) and Windows DISPLAY IDs
3. Use the Runtime Detection Commands to find which screen a target window is on
4. Use the Coordinate System section to understand pixel positions and DPI scaling
5. For window management P/Invoke (SetForegroundWindow, ShowWindow), reference `ninjatrader/scripts/nt8-ui.ps1` via the `nt8-expert` skill

## Base path: C:\Users\Tea\DEEP6\.claude\skills\display-topology\
