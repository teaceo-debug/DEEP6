---
version_label: gex-magnet-v3
created: 20260501-110405
---

# DEEP6 GEX Magnet V3 — side-by-side new version

Goal: create a new GEX levels version that preserves the original indicator's selective OI-gamma magnet behavior instead of replacing it with always-on/far-away flow levels.

Scope:
- Keep DEEP6GexLevels.cs and DEEP6GexLevelsV2.cs intact.
- Add DEEP6GexLevelsV3.cs side-by-side.
- Prefer local JSON from massive_gex_map_service.py so NT8 does not own API/TLS/parsing reliability.
- Only render near-price levels by default. If no high-quality nearby level exists, show no level rather than forcing a far-away wall.
- Keep settings adjustable: max rendered levels, max distance points, freshness, labels/HUD.

Implementation notes:
- V3 reads massive_gex_map.json.
- V3 renders compact horizontal magnet levels and status only; no stop/target overlays.
- Sidecar keeps OI-based original GEX formula and adds distance cap / original-selective role selection.
