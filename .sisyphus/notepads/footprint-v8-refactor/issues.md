# Issues — footprint-v8-refactor

## Session Start: 2026-05-24

### Known Issues Going In
- CLA labels fire too frequently (Classic Absorption threshold too sensitive)
- 4 arrow systems draw without confluence gate — fire on raw signals
- Percentage diamond shows raw strength (0-100%) with no directional meaning
- No per-variant visibility control (only umbrella ShowAbsorptionMarkers)

### Issues Discovered During Work
(append as encountered)
- The first optimizer run leaked provenance keys from `v8_parent0.json` (`source`, `version`, `v7_signal_thresholds`) into the candidate payload; filtering `normalize_params()` down to `V8_PARAM_BOUNDS` fixed the params hash/JSON output.
