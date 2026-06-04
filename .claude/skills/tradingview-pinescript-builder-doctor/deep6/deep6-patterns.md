# DEEP6 Pine Build Patterns

Last verified: 2026-05-22

Use this file when Pine work is part of DEEP6 rather than a generic TradingView script.

## Current DEEP6 Pine Inventory

- `C:\Users\Tea\DEEP6\Indicators\sd_anchor_ai.pine` — StdDev Anchor AI overlay and candidate-scoring logic
- `C:\Users\Tea\DEEP6\scripts\po3_webhook_additions.pine` — backend-facing webhook event bridge
- `C:\Users\Tea\DEEP6\.planning\research\pine\VP_LVN.pine` — research-only volume-profile LVN prototype
- `C:\Users\Tea\DEEP6\.planning\research\pine\BOOKMAP_LIQUIDITY_MAPPER.pine` — research-only liquidity/zone prototype

## Local Design Priorities

- use Pine as a visual analysis and signal-surface layer, not canonical execution authority
- keep series logic inspectable enough to compare with Python-side DEEP6 logic
- preserve deterministic naming for labels, lines, and alert payload fields where possible
- document Python integration touchpoints when Pine emits external events

## Integration Reference

See `C:\Users\Tea\DEEP6\.planning\research\pine\DEEP6_INTEGRATION.md` for the level-bus blueprint and cross-system primitive mapping.

## Inventory Update Convention

When a new `.pine` file is added to this repository:
1. Add it to the inventory table above with path, description, and status (production/research)
2. If it emits alerts or webhook payloads, document the event names and JSON schema
3. If it has Python integration points, note them and reference the relevant Python module
4. Update `Last verified` date on this file
