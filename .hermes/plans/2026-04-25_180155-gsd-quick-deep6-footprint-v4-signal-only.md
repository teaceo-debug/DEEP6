---
workflow: gsd-quick
status: in_progress
version_label: version-four-signal-only
created_at: 2026-04-25 18:01:55 EDT
owner: Hermes
files_expected_to_modify:
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV4.cs
source_files_reviewed:
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV3.cs
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
artifacts_created:
  - backups/version-four-signal-only-baseline-20260425-180155/
user_request:
  - Create a new DEEP6 footprint version
  - Remove the actual footprint and gray visuals
  - Leave absorption levels, colors, and signals only
---

# /gsd-quick — DEEP6 Footprint V4 signal-only variant

Goal
Create a separate DEEP6FootprintV4 indicator that preserves the existing V3 file/class while shipping a cleaner signal-only chart.

Implementation outline
1. Fork V3 into a new V4 file/class/generated-wrapper set.
2. Change defaults so the footprint-cell layer and non-essential overlays are off by default.
3. Remove gray setup-only scorer visuals so the chart only shows colored absorption/signal markers.
4. Keep colored absorption/exhaustion markers and Tier 1/Tier 2 signal visuals.
5. Keep the result versioned side-by-side with V2/V3.

Validation
- Verify file/class/generated-region names are unique to V4.
- Verify no gray setup marker remains in the V4 scorer marker path.
- Verify defaults align with signal-only intent.
