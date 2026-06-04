## bias-v3 Session Notes

- UnifiedBiasEngine v2 does **not** renormalize around unavailable sources; unavailable inputs are zeroed but their weights stay in the denominator, so three perfect bullish core signals still score 65.0 instead of 100.0.
- `macro_blackout` is currently context-only in v2: it is copied onto `UnifiedBiasScore` but does not automatically reduce score, confidence, grade, or setup generation.
- Trade setup generation is gated by grade in `compute()`: setup creation only happens when `current_price > 0` and grade is not `C` or `F`, even if directional score is still bullish/bearish.

- Added a standalone intermarket registry with explicit RTH-only expected-stale detection so breadth/volatility inputs can be treated as unavailable outside 9:30-16:00 ET without conflating that with feed failure.

- Added shared bias contracts in `deep6/engines/bias_contracts.py` using stdlib dataclasses + `IntEnum`/`Enum`.
- Appended v3 config dataclasses to `deep6/engines/signal_config.py` without touching existing configs.
- Basic tests should cover enum values, snapshot instantiation, and default thresholds.

- `IntermarketFeed` works best as one shared async-rithmic client plus one subscription task per intermarket symbol; symbol tasks can retry independently so a bad breadth feed does not take down treasury/futures subscriptions.
- For front-month futures (`ZN_FUT`, `RTY_FUT`), keep a `security_code -> logical symbol` map because async-rithmic ticks arrive on the resolved contract code (for example `ZNM6`) while the registry keys remain canonical (`ZN`).
- Local unit tests should not hard-require the vendor `async_rithmic` package; a small fallback `DataType`/`RithmicClient` shim keeps the feed module importable while tests inject a fake client.

- Bias hysteresis is most stable when strong-state degradation collapses to `NEUTRAL` first instead of immediately downgrading to the corresponding lean state; this matches the v3 task sequence and reduces rapid oscillation around +3/-3.
- The clean separation is: `_target_state()` handles naive score mapping, while `update()` enforces state-aware hold/degrade rules plus emergency bypass based on `emergency_delta`.

- The intraday flow bias domain should treat RTH as a hard availability gate: outside 9:30-16:00 ET it returns `score=0`, `available=False`, and `stale=True` instead of trying to interpret dormant TICK/CVD inputs.
- Flow scoring stays simple and composable when each source contributes at most ±1 (`CVD slope`, `TICK thrust`, `price vs VWAP`) and the domain clamps the sum back to its contracted ±2 range.
- The ICT session v3 domain can consume `PO3BiasState` directly without re-running PO3 logic: `above_midnight_open`, `above_weekly_open`, `in_discount`, and `judas_status` are sufficient to build a -4..+4 translation layer.
- For v3 domain scoring, unknown PO3 fields should shrink `max_range` rather than inject a directional bias; reserve `available=False` for a completely missing upstream PO3 snapshot.

- The macro intermarket v3 domain should treat ZN, DXY, and VIX as three independent ±1 components, using simple `close` vs `open` direction for ZN/DXY and fixed VIX thresholds (`<20` bullish, `>25` bearish).
- Missing or stale intermarket bars should be excluded from the score and reduce `max_range`; only mark the domain unavailable when all three components are excluded.

- `BiasComposer` is simplest when it zeroes unavailable/stale domain contributions before summing, then applies confidence penalties in order: disagreement, per-stale decay, then the `<2 active domains` haircut.
- `MarketBiasEngine` needs an explicit cold-start override (`mode=CAUTION`, `reason="Cold start"`) because the generic kill switch rules otherwise classify missing VIX/domains without preserving the desired boot-state semantics.
- The hysteresis wiring belongs after composition and before kill-switch evaluation: stabilize the raw total into `BiasState`, but keep kill switch side effects limited to `mode`/`mode_reason` so score and state remain intact.
- The cleanest TDM integration point for bias v3 is to keep the pure `guard_T2_ready()` call untouched, then apply the snapshot-aware STOP check immediately after it passes; this preserves all legacy WATCHING guards and keeps `None` bias as a no-op.
- T3 gating is safest after trigger detection but before intent construction: entering ARMED with sub-80 score avoids accidental confirmation-bar pendings in tests, and CAUTION/STOP can then block trigger execution without altering other transition logic.

- v3 API routes are easiest to test when the FastAPI app is built locally inside the test and the router module is loaded directly from file; that avoids importing optional ML dependencies from the full package tree.
- `update_snapshot()` should treat domain scores as replace-on-update state and keep a bounded in-memory history so `/history` can stay a pure read endpoint.
- Moved bias-v3 hardcoded thresholds into config dataclasses in signal_config.py; engine defaults now come from injected config objects.
- Appending a replacement KronosDomainConfig at the end of signal_config.py preserved the append-only constraint while exposing stale_threshold_sec.
- Targeted bias-v3 tests passed: 62/62.
