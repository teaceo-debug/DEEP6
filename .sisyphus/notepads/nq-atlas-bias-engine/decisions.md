- Task 6 decision: z-score baseline is computed from 12 rolling five-minute buckets over the last 60 minutes, with zero z-score when variance is effectively zero to avoid false spikes.
- Task 6 decision: non-call contracts are treated as puts for raw premium direction, matching the required formula direction = aggressor_sign * (call ? +1 : -1).
- Implemented 
q_atlas/gex.py as a pure analytics module with a GEXEngine class and no imports from deep6v2/.

- [2026-05-14 22:30:41] Task 10: Kept orchestration single-process asyncio with four concurrent tasks (poll_loop, compute_loop, interpret_loop, uvicorn) and separated analytics wiring into nq_atlas/orchestrator.py.
2026-05-14: Added ai_refresh_sec to AtlasState so degraded() can distinguish chain freshness from AI fallback freshness without requiring AI to be present initially.
- 2026-05-15: Keep get_options_chain() conservative: cap pagination at 20 pages and stop once a page adds zero new valid contracts, preserving the first-page spot extraction while avoiding infinite Polygon pagination loops.
- 2026-05-15: Added FlashAlpha as optional config/state plumbing only; analytics wiring stays out of scope until the foundation layer is stable.

- 2026-05-15: Kept BiasOutput/types unchanged; regime mode and sizing guidance stay prompt-only and are requested inside narrative/risk_flags so existing JSON parsing and tests remain stable.

- 2026-05-15: FlashAlpha stays optional in run_atlas; initialize FlashAlphaClient only when flashalpha_api_key is present and add its poll_loop as a conditional concurrent task.
