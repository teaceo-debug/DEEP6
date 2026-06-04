\n+## 2026-05-23
- Keep param bounds in a standalone registry module under deep6/backtest so validation/clamping is reusable.
- Use model_dump/model_validate when available; fall back to dict mutation for generic compatibility.

## 2026-05-29
- Keep FlashAlpha integration as a wrapper around nq_atlas.flashalpha_client without reimplementing API calls or conversions.
- Preserve raw payloads on the result object for debugging and regression triage.
