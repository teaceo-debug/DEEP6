# NT8 Expert Skill

Invoke this skill when the user asks you to:
- Deploy, install, or update an indicator or strategy in NinjaTrader 8
- Compile or recompile NinjaScript code
- Add an indicator or strategy to a chart
- Navigate NT8 settings, connections, or menus
- Troubleshoot NT8 errors (compile errors, connection issues, strategy issues)
- Manage NT8 workspaces, templates, or data series
- Interact with NT8 in any way — clicking, configuring, or automating

## Skill Entry Point

Load `knowledge.md` in this directory for the full NT8 knowledge base, then
load `scripts.md` for the automation scripts available.

Always check the actual NT8 paths on disk before acting — do not assume.
Verified base path: `C:\Users\Tea\Documents\NinjaTrader 8\`

## OpenCode Skills (Universal NT8 Knowledge)
For universal NT8 knowledge, invoke these opencode skills:
- `ninjatrader-machine-profile` — NT8 platform, installation, editor, state machine, namespaces
- `ninjatrader-builder-doctor` — NinjaScript development patterns, indicators, strategies, SharpDX
- `ninjatrader-error-doctor` — Error diagnosis, CS error codes, runtime exceptions
