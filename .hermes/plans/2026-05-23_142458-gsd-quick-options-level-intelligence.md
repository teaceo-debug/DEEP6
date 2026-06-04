# GSD Quick — DEEP6 Options Level Intelligence Service

Status: execution kickoff

Goal
- Build a Python sidecar that consumes existing DEEP6 options-flow/GEX/context JSON and emits a reduced set of prominent NQ support/resistance/target levels.

Scope
1. Add a standalone service next to the current Windows DEEP6 sidecars.
2. Consume `massive_options_icebergs.json`, `massive_gex_map.json`, and optional `institutional_context.json`.
3. Score, merge, classify, and reduce raw levels into max 1-3 prominent levels.
4. Keep settings configurable through CLI arguments.
5. Emit a NinjaTrader-friendly JSON contract: `options_level_intelligence.json`.
6. Validate syntax and run a sample once-mode generation.

Constraints
- Do not replace existing GEX/options sidecars.
- Do not alter NinjaTrader chart indicators in this pass.
- Keep GEX/level filtering configurable, not hardcoded.
- Avoid clutter: hide weak/stale/duplicate levels.
- Treat these as map/target/support/resistance context, not standalone trade triggers.
