## [2026-05-27] Task 2: Formal DOM taxonomy is now explicit and testable.
- Added a frozen metadata record for each detector with tier, replay safety, and first-release scope.
- Used a single dict registry keyed by detector_id to keep ordering stable and make duplicate IDs impossible at the registry level.
- Kept Tier 1 mechanical detectors replay-safe, Tier 2 heuristic detectors replay-degraded, and Tier 3 discretionary overlays live-only / out of first release.
- Added helper filters for mechanical, heuristic, first-release, and replay-safe detectors so downstream code can consume the taxonomy without reimplementing classification logic.

## [2026-05-27] Task 1: DOM intelligence contract follows existing v2 type patterns while staying dataclass-first.
- New DOM intelligence contracts use stdlib dataclasses with slots, mirroring SessionContext's lightweight style instead of introducing new Pydantic models into the hot path.
- The ownership boundary is explicit at the module level: detectors consume DOMSnapshot derived from deep6v2/state/dom.py and must not construct a shadow DOMState.
- Feature rows normalize feature_values to a 1D float64 numpy array and enforce name/value length parity so downstream ML and heuristic consumers can rely on positional alignment.
- Event/output contracts carry detector tier and replay-safety metadata directly on the event bundle, keeping detector classification attached to the emitted payload instead of scattered across registry consumers.

## [2026-05-27] Task 3: Architecture boundary is enforced with file-level static checks.
- Loaded `boundary.py` in tests via `importlib.util.spec_from_file_location(...)` so the boundary contract can be verified without importing `deep6v2.signals.__init__` and its heavier runtime dependencies.
- The approved contract keeps `deep6v2.state.dom.DOMState` as the single DOM ownership point while allowing V1 depth-radar reuse only as optional feature/classifier imports.
- Dashboard isolation is safest to enforce as raw text scanning because the frontend must consume structured transport/state surfaces, never Python detector modules.

## [2026-05-27] Task 4: LiveDOMAdapter bridges DOMState into DOMIntelligenceOutput.
- `DOMUpdate.side` is `OrderSide` (BUY/SELL) but `DOMState.update_level()` takes string "bid"/"ask" — adapter handles mapping via `_SIDE_MAP` dict.
- `Direction` enum uses `BULLISH/NEUTRAL/BEARISH` (not LONG/SHORT) and `SignalId` uses coded IDs like `ABS_01` (not descriptive names like `ABSORPTION`) — always check actual enum members before using in tests.
- Adapter is pure translation: receives DOMState in constructor (identity reference), applies updates, increments version counter, packages into DOMIntelligenceOutput. No detection logic.
- FeedStaleError provides clean disconnect handling — `mark_stale()` / `clear_stale()` / `is_stale()` triplet for reconnect lifecycle.
- 17 tests across 7 test classes (spec required 7 categories, each expanded into multiple assertions for thoroughness).

## [2026-05-27] Task 5: ReplayDOMAdapter stays deterministic by owning version/event counters only.
- Replay snapshots cannot call `DOMState.snapshot()` without an explicit timestamp because `datetime.now()` would break parity; the adapter stamps snapshots from a fixed UTC epoch plus event index.
- `ReplayDOMAdapter` must reuse the injected `DOMState` and only translate `OrderSide.BUY/SELL` into DOMState's `bid`/`ask` strings before incrementing a local version counter.
- `build_output()` can preserve parity with the live adapter signature while still normalizing emitted events by attaching the current `DOMSnapshot` when a detector event omitted it.

## [2026-05-27] Task 6: Golden-session records should stay stdlib-serializable while preserving nested detector payloads.
- `GoldenSessionRecord` stays a plain dataclass and stores only JSON-friendly primitives plus dict payloads; nested Pydantic DOM models are converted with `model_dump(mode="json")` and dataclass payloads are recursively normalized.
- `DOMUpdate` does not carry a timestamp field, so the recorder stamps each update with an injected clock to make golden-session ordering and replay parity deterministic in tests.
- `DOMIntelligenceOutput` round-trips cleanly when event metadata and nested `DOMSnapshot` payloads are preserved as JSON dicts, which keeps detector metadata and level data available for parity diffs.

## [2026-05-27] Task 7: Feed safety needs explicit reconnect/session-boundary reset hooks.
- `FeedStateManager` can stay thin by wrapping the existing `LiveDOMAdapter` stale flag instead of introducing any new network logic.
- Session rollover should reset the underlying shared `DOMState`, zero the adapter version counter, and assign the new session id so stale or book data cannot bleed into the next session.
- Reconnect flow is safest when it records a visible `RECONNECTING` step before returning to `CONNECTED`, because the transition history becomes auditable and the final connected state is unambiguous.

## [2026-05-27] Task 6B: Golden session inventory created with 3 synthetic fixtures
- GoldenSessionRecorder works well for synthetic generation � use deterministic Random seeds + synthetic clock for reproducibility
- _normalize_update adds timestamp_ns to each DOMUpdate dict at serialization time
- _to_jsonable handles Enum?value, BaseModel?model_dump, dataclass?field dict, ndarray?tolist recursively
- For disconnect simulation: swap the recorder's _clock to create timestamp gaps (>1s gap detected by tests)
- DOMIntelligenceFeatureRow requires 1D float64 array and matching feature_names length � enforced at __post_init__
- Generation script is deterministic (seeded RNG) so re-running produces identical fixtures

## [2026-05-27] Task 7A: Compatibility gate should freeze DOM scoring through existing SignalId families only.
- `SignalId` names in `deep6v2/types/signal.py` are intentionally coded (`ABS_01`, `IMB_01`, `DELT_01`, `ENG_04`) rather than descriptive, so the safest MVP contract is a literal detector→existing-enum mapping file.
- `ConfluenceScorer` only cares about `SIGNAL_TO_CATEGORY`, while `EntryGate` hard-codes absorption/core ID sets; therefore DOM MVP compatibility must document both reused IDs and the fact that no new DOM-specific IDs may reach gating semantics.
- Tier 2 heuristic and Tier 3 discretionary DOM detectors should stay `None`-mapped in the contract so they can emit feature rows or overlays without silently mutating scorer weights or gate behavior.

## [2026-05-27] Task 7C: Rollback is safest as a pure env-var gate with caller-side registration control.
- `DOM_INTELLIGENCE_ENABLED` should default to enabled so existing behavior stays unchanged until an explicit rollback signal is set.
- The rollback helper functions are intentionally tiny and side-effect-only: they only set the env var, leaving registry/scorer logic untouched.
- Tests should restore environment state around direct force-enable/force-disable calls because those helpers write to `os.environ` outside pytest's automatic tracking.

## [2026-05-27] Task 7B: Backward-compat fixtures prove DOM outputs don't break registry/scorer consumers.
- DOMIntelligenceEvent -> SignalResult conversion is straightforward: map signal_id, direction, confidence->strength, price, and derive flag_bit from SignalFlagBits by name.
- ConfluenceScorer.score() silently skips signals with None category (line 36: `if category is None: continue`), which is the exact mechanism that prevents Tier-2 None-mapped detectors from scoring.
- Pydantic V2.11 deprecates accessing `model_fields` on instances; must use `type(instance).model_fields` instead.
- The aggregate contract test (old-path vs DOM-path) confirms structural identity: same ScorerResult fields, same category_scores keys, same final_score when given identical strength/bar_index � proving the DOM path is a drop-in replacement for existing signal producers.

## [2026-05-27] Task 10: Sweep+reload detection is safest as a per-level state machine with bounded recency.
- The clean rule set is `NORMAL -> SWEPT -> RELOADED`: only mark a sweep when previously meaningful liquidity (`>= reload_threshold`) collapses under `sweep_threshold`, and only emit on the later refill.
- Bounding tracked depth to 20 levels is easy with an LRU-style `OrderedDict`; when trimming, prefer evicting non-swept levels so active sweep windows are preserved.
- Timeout is best enforced in snapshot-count space instead of wall-clock time for replay safety: expire the swept flag once `snapshot_index - swept_at_snapshot > max_reload_snapshots`.
- Tests that import files under `deep6v2/signals/dom/` should load the detector module by file path and register it in `sys.modules` first, which avoids package side effects during collection and keeps dataclass module lookup happy under Python 3.12.

## [2026-05-27] Task 9: DOM absorption works best as persistent wall-defense state over consecutive snapshots.
- DOM snapshots do not expose executed trade prints directly, so the safest replay-safe proxy for aggression is repeated volume depletion at the same resting price while that level still remains above the wall threshold.
- For DOM absorption, direction is polarity-inverted from the resting side: bid-wall defense means sellers were absorbed (`Direction.BULLISH`), ask-wall defense means buyers were absorbed (`Direction.BEARISH`).
- Making `deep6v2.signals.__init__` lazy avoids dragging optional config dependencies into DOM-only test collection, which keeps detector modules import-safe in isolation.

## [2026-05-27] Task 12: CVD detector should distinguish accumulation from acceleration.
- Pure steady accumulation should only grow the running CVD history; acceleration detection needs a short same-direction burst with increasing trade sizes, not just repeated equal-volume prints.
- Zero-cross events should key off the prior magnitude on the opposite side of zero, so a small post-cross remainder can still confirm the regime flip when the prior move was large enough.
- Session reset should clear current CVD, trade history, and rolling acceleration state so the next session starts from a clean accumulator.

## [2026-05-27] Task 8: DOM imbalance/thinness detectors should work directly from DOMSnapshot top-of-book slices.
- `DOMSnapshot` already arrives ordered best-outward, so top-N detector math can stay pure list slicing (`snapshot.bids[:5]`, `snapshot.asks[:5]`) with no DOMState recreation.
- For asymmetric liquidity risk, direction is safest when mapped by the thin side: thin bids / thick asks => bearish risk, thin asks / thick bids => bullish risk.
- Event payloads are easiest to audit when metadata carries raw bid/ask/top-N totals plus the trigger condition (`global_thinness` vs `asymmetric_thinness`).

## [2026-05-27] Task 14: Pull/replace works best as delta matching plus confirmation counting.
- For deceptive liquidity heuristics, compare snapshot deltas directly: sharp volume decreases define pull candidates and nearby same-side increases define replacement candidates.
- Same-snapshot pull/replace should still report `replacement_speed=1`; speed semantics are snapshot steps, not zero-based index differences.
- Because `DOMIntelligenceEvent` requires a `SignalId`, heuristic-only DOM detectors can safely use `SignalId.REGIME_CHANGE` as an explicit placeholder while keeping the real semantics in `detector_id` and metadata.

## [2026-05-27] Task 16: Threshold calibration should stay heuristic-only and deterministic.
- Tier-2 calibration can be kept pure by storing only per-detector sample values in memory and deriving fire rates/recommended thresholds at report time.
- The report contract is easiest to serialize when it exposes plain dataclass fields plus explicit `to_dict()` / `to_json()` helpers.
- Tier-1 mechanical detectors must be rejected at the calibrator boundary so only heuristic detectors participate in threshold tuning.

## [2026-05-27] Task 13: Feature-row builder follows WallFeatureExtractor pattern with stable API contract.
- FEATURE_NAMES is a 10-element ordered list serving as an API contract � order must never change between versions.
- _IDX dict provides O(1) feature-index lookup by name, same pattern as wall_features.py.
- _DETECTOR_FEATURE_MAP links detector IDs to their feature names, enabling event-sourced extraction without hardcoded switch statements.
- Missing features default to 0.0 (not NaN) to keep downstream ML pipelines clean without imputation.
- For multiple events from the same detector, max-magnitude wins � prevents double-counting while preserving signal strength.
- Mechanical features (imbalance, asymmetry, thinness) are always extracted from the DOM snapshot directly, independent of events.
- Labeling strategy: Tier-2 heuristic labels derived from Task 6B golden sessions using fixture timestamps + price levels as event anchors.

