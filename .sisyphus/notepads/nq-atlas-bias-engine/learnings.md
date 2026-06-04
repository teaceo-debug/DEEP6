- Task 2: added frozen Pydantic models in nq_atlas/types.py, mutable AtlasState in nq_atlas/state.py, and QQQ?NQ mapping helpers in nq_atlas/nq_mapper.py.
- Verified import, serialization, frozen mutation guard, mapper math, and fresh degraded state; kept state stale check based on last_chain_ts + refresh interval.
- Task 5: added nq_atlas/vanna_charm.py with API-greeks-first fallback to Black-Scholes vanna/charm, dealer short-option sign flip, 1-day expiry clamp, and mixed-signal neutralization when vanna/charm magnitudes are within 10%.
- Task 6: FlowEngine uses Lee-Ready midpoint classification first, then tick-rule fallback via prev_price/_last_trade_price; midpoint ties with no prior price stay neutral and do not accumulate premium.
- QA evidence saved for bullish call premium, mixed bullish/bearish accumulation, and empty-state zero outputs in .sisyphus/evidence/.
- GEX engine aggregates contract exposure by strike, interpolates cumulative zero-crossings, and buckets expiry exposure into 0DTE/1-7/8-30/31+.

- [2026-05-14 22:30:41] run_atlas.py must seed state.spots['underlying_sym'] from Settings. MassiveClient.poll_loop reads that key to decide which underlying chain to request.
2026-05-14: AtlasState.degraded() should treat AI staleness as additive: only flag stale AI when last_ai_ts exists and exceeds 4x ai_refresh_sec; fresh chain data remains the primary gate.
- 2026-05-15: Polygon QQQ snapshot pagination can report next_url indefinitely while valid OI>=100 contracts are exhausted after the first page; a conservative max_pages cap plus early exit on zero new valid contracts prevents infinite chain polling.
- 2026-05-15: FlashAlpha SDK is synchronous; the wrapper should use loop.run_in_executor for each endpoint call and gather the endpoints in parallel before writing a consolidated state payload.

- 2026-05-15: 
q_atlas.ai_bias.BiasInterpreter._build_prompt() can safely consume optional FlashAlpha payloads by using getattr(state, 'flashalpha', None) plus nested-dict guards, avoiding any AtlasState/type changes while keeping degraded prompts valid.
