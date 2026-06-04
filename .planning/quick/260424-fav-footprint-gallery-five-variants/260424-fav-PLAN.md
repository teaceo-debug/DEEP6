---
phase: quick-260424-fav
plan: 01
type: plan
version_label: footprint-gallery-five-variants
wave: 1
depends_on: []
files_expected_to_modify:
  - dashboard/app/gallery/page.tsx
  - dashboard/app/page.tsx
  - dashboard/app/layout.tsx
artifacts_planned:
  - .planning/research/futures-analytica-footprint-notes-2026-04-24.md
requirements:
  - Research Futures Analytica public footprint design patterns
  - Create five DEEP6 footprint design variants optimized for intraday readability
  - Host the variants on localhost inside the existing Next.js dashboard app
  - Keep the current dashboard intact while adding a dedicated comparison route
  - Make each version easy to compare with a clear rationale and pick recommendation path
status: in_progress
owner: Hermes
updated: 2026-04-24
---

# DEEP6 Footprint Gallery — Five Variant Design Plan

Goal:
Create a localhost-accessible DEEP6 gallery page with five professional footprint design variants inspired by public Futures Analytica visual patterns and tuned for rapid intraday interpretation.

Architecture:
Use the existing Next.js dashboard app as the host surface and add a new routed page under `dashboard/app/gallery/page.tsx`. Keep the current landing dashboard untouched, render five concept cards from shared mock footprint data, and present each style with a concise explanation of what it optimizes: location clarity, signal clarity, density, level awareness, or execution speed.

Implementation outline:
1. Capture the public design principles from Futures Analytica research into a local note.
2. Build a single gallery page that renders one shared mock market context into five alternate visual grammars.
3. Keep the palette disciplined: dark base, selective accents, strong horizontal level orientation, and sparse event highlights.
4. Add a lightweight entry link from the main dashboard so the gallery is easy to open on localhost.
5. Run the Next app, verify `/gallery`, and confirm the user can visually compare all five versions.

Planned variant set:
1. Institutional Minimal — grayscale cells with selective cyan/amber/green highlights.
2. Zone-First Pro — strongest emphasis on call/put/absorption/reaction zones.
3. Signal-First Scalper — aggressive setup/trigger badges and compressed read path.
4. Dense Analytica-Inspired — compact high-information panel with restrained teal/orange accents.
5. Executive Hybrid — best-balance design combining context rail, zones, and readable cells.

Validation:
- `cd dashboard && npm run typecheck`
- `./scripts/deep6_up.sh --force`
- open `http://localhost:3000/gallery`
- visually confirm five distinct cards render without backend dependence
