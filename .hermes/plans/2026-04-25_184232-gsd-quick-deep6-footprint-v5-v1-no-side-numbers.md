---
workflow: gsd-quick
status: in_progress
version_label: version-five-v1-no-side-numbers
created_at: 2026-04-25 18:42:32 EDT
owner: Hermes
files_expected_to_modify:
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV5.cs
source_files_reviewed:
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs
  - ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV3.cs
artifacts_created:
  - backups/version-five-v1-no-side-numbers-20260425-184232/
user_request:
  - Use version 1 code as the base
  - Use version 3 only as reference/build guidance
  - Remove only the gray footprint numbers on the left and right
  - Save as version 5
---

# /gsd-quick — DEEP6 Footprint V5 from V1 with side numbers removed

Goal
Create a separate DEEP6FootprintV5 indicator derived from DEEP6Footprint.cs (version 1 style), preserving the gray setup marker and other markers while removing only the footprint bid/ask number text from each cell.

Implementation outline
1. Fork DEEP6Footprint.cs into DEEP6FootprintV5.cs with unique class/wrapper names.
2. Keep V1 defaults/behavior unless versioning requires name/description updates.
3. Remove only the per-cell DrawTextLayout label block in OnRender.
4. Deploy V5 to NinjaTrader and compile.

Validation
- V5 is a separate file/class/wrapper set.
- Cell fills and markers remain.
- Footprint side-number text draw path is removed.
- Deploy succeeds; compile status reported.
