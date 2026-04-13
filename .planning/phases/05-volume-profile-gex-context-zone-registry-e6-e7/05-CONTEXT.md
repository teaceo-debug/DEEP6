# Phase 5: Volume Profile + GEX Context + Zone Registry - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Session volume profile with LVN/HVN detection, 5-state zone lifecycle FSM, GEX integration via Polygon API, centralized ZoneRegistry, and E6/E7 engine scaffold. Engines already exist — this phase validates, extracts config, fills gaps (zone FSM lifecycle, ZoneRegistry merging, GEX staleness), and adds tests.

**Key reality:** `poc.py` (228 lines), `volume_profile.py` (264 lines), `gex.py` (276 lines) all exist and fire on real data. GEX engine tested live with Polygon API key. This phase completes zone lifecycle, wires ZoneRegistry, and ensures GEX staleness/regime handling meets requirements.

</domain>

<decisions>
## Implementation Decisions

### Config Extraction
- **D-01:** Follow Phase 2/3 pattern — add `POCConfig`, `VolumeProfileConfig`, `GexConfig` to signal_config.py.

### Volume Profile
- **D-02:** LVN threshold: < 30% of session average volume. HVN threshold: > 170%. Already in volume_profile.py — verify and extract to config.
- **D-03:** Zone lifecycle FSM: Created → Defended → Broken → Flipped → Invalidated. Verify existing implementation or add if missing.

### GEX Integration
- **D-04:** Polygon API key is live. GEX engine already fetches and computes. Verify staleness threshold (15 min default per GEX-06).
- **D-05:** GEX regime gate modifies signal weighting — positive gamma favors fading, negative favors momentum. Already in get_signal(). Verify correctness.

### Zone Registry
- **D-06:** ZoneRegistry consolidates absorption, exhaustion, LVN, HVN, and GEX zones. Overlapping same-direction zones merge with combined score.
- **D-07:** Confluence between zone types produces highest conviction flag.

### E7 MLQualityEngine
- **D-08:** Returns 1.0 (neutral) until ML pipeline exists in Phase 9. Stub only.

### Claude's Discretion
- Zone merge algorithm details
- Test structure

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §POC, §VPRO, §GEX, §ZONE — All requirement IDs
- `deep6/engines/poc.py` — POC/VA computation
- `deep6/engines/volume_profile.py` — SessionProfile, zone detection
- `deep6/engines/gex.py` — GexEngine, Polygon API integration
- `deep6/engines/signal_config.py` — Config pattern from Phase 2/3

</canonical_refs>

<code_context>
## Existing Code Insights

- SessionProfile has add_bar(), detect_zones(), update_zones(), get_active_zones()
- GexEngine has fetch_and_compute(), get_signal() with regime classification
- POCEngine tracks POC streak, gap, session POC, VAH/VAL
- backtest_signals.py already calls all three

</code_context>

<specifics>
## Specific Ideas
- Polygon API key live and tested
- Use April 10 Databento data for profile validation
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 05-volume-profile-gex-context-zone-registry-e6-e7*
*Context gathered: 2026-04-13*
