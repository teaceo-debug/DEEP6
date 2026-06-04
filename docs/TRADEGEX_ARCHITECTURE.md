# DEEP6 TradeGEX Core Architecture

## Goal
Make TradeGEX the canonical options-derived bias/levels source for NQ, ES, and QQQ without duplicating the responsibilities already owned by `gex.py`, `kronos_bias.py`, `level.py`, `level_factory.py`, `zone_registry.py`, and `confluence_rules.py`.

TradeGEX should do three things:
1. Observe vendor payloads and session updates.
2. Normalize them into DEEP6-native contracts.
3. Feed LevelBus + bias consumers + publishing surfaces.

It should not re-implement confluence scoring, level lifecycle logic, or ML directional forecasting.

---

## What already exists in DEEP6

### Existing ownership boundaries
- `deep6/engines/gex.py`
  - Owns options-chain fetch + in-house GEX computation.
  - Produces `GexLevels` and `GexSignal`.
- `deep6/engines/kronos_bias.py`
  - Owns predictive bar-based directional bias.
  - Produces `KronosBias`.
- `deep6/engines/level.py`
  - Owns the unified `Level`, `LevelKind`, `LevelState` model.
- `deep6/engines/level_factory.py`
  - Owns conversion from producer outputs into `Level` objects.
  - Already has `from_gex(levels)`.
- `deep6/engines/zone_registry.py`
  - Actually the `LevelBus`; owns dedupe, merge, query, eviction, and confluence lookup.
- `deep6/engines/confluence_rules.py`
  - Owns rule evaluation across `Level`s and `GexSignal`.

### Architecture implication
TradeGEX should plug in at the same abstraction level as `GexEngine`, not bypass the LevelBus or create a parallel level model.

Best fit: TradeGEX becomes an alternative options/map source that emits a DEEP6-native snapshot contract, then adapts into:
- `GexLevels`-compatible point levels for LevelBus
- a richer bias snapshot for dashboards/publishing
- a regime signal for confluence/risk logic

---

## Recommended module layout

### 1) `deep6/engines/tradegex_observer.py`
Purpose: vendor adapter / observer only.

Responsibilities:
- Connect to TradeGEX source (HTTP poller, websocket, file drop, or browser-export parser).
- Track raw payload freshness and session identity.
- No DEEP6 scoring, no Level creation, no trading logic.

Suggested interface:
```python
@dataclass(slots=True)
class TradeGexRawSnapshot:
    symbol: str                 # "NQ", "ES", "QQQ"
    source_ts: float
    session_date: str
    map_type: str               # e.g. "intraday", "daily"
    payload: dict
    revision: str | None = None
```

```python
class TradeGexObserver:
    def poll(self) -> TradeGexRawSnapshot | None: ...
    def latest(self) -> TradeGexRawSnapshot | None: ...
```

Why separate it:
- isolates vendor schema churn
- supports replay fixtures/tests
- lets you swap ingestion method without touching engine logic

---

### 2) `deep6/engines/tradegex_normalizer.py`
Purpose: translate TradeGEX payloads into a stable DEEP6 market-map contract.

Responsibilities:
- Parse vendor-specific fields.
- Normalize price units and instrument identity.
- Classify levels into DEEP6 semantics.
- Attach provenance, confidence, freshness, and session metadata.

Suggested core contracts:
```python
from enum import Enum, auto
from dataclasses import dataclass, field

class TradeGexLevelRole(Enum):
    CALL_WALL = auto()
    PUT_WALL = auto()
    GAMMA_FLIP = auto()
    ZERO_GAMMA = auto()
    HVL = auto()
    LARGEST_GAMMA = auto()
    DEALER_DEFENSE = auto()
    ACCELERATION = auto()
    MAGNET = auto()
    SUPPORT = auto()
    RESISTANCE = auto()
    INVALID = auto()

@dataclass(slots=True)
class TradeGexMapLevel:
    symbol: str
    role: TradeGexLevelRole
    price: float
    strength: float            # 0..100 normalized confidence/importance
    direction: int             # +1 support, -1 resistance, 0 neutral/magnet
    label: str
    source_field: str
    source_ts: float
    session_date: str
    meta: dict = field(default_factory=dict)

@dataclass(slots=True)
class TradeGexBiasSnapshot:
    symbol: str
    source_ts: float
    session_date: str
    bias_direction: int        # +1 / -1 / 0
    bias_strength: float       # 0..100
    regime: str                # "PIN" | "TREND" | "BALANCE" | "NEUTRAL"
    dealer_posture: str        # "long_gamma" | "short_gamma" | "mixed" | "unknown"
    nearest_support: float | None
    nearest_resistance: float | None
    levels: list[TradeGexMapLevel]
    meta: dict = field(default_factory=dict)
```

Normalization rules:
- Keep vendor semantics in `meta`; keep DEEP6 semantics in typed fields.
- Convert all prices into the traded instrument’s native price space before emission.
- Distinguish canonical GEX-equivalent fields from TradeGEX-only informational levels.
- If TradeGEX gives multiple maps, normalize all, but mark one as `is_primary=True` in `meta`.

---

### 3) `deep6/engines/tradegex_engine.py`
Purpose: stateful orchestrator for TradeGEX snapshots.

Responsibilities:
- Pull from observer.
- Normalize raw payload.
- Maintain latest accepted snapshot per symbol.
- Enforce freshness/session state machine.
- Expose DEEP6-native outputs to LevelBus, scorer, and publisher.

Suggested public API:
```python
class TradeGexEngine:
    def update(self) -> TradeGexBiasSnapshot | None: ...
    def latest_bias(self, symbol: str) -> TradeGexBiasSnapshot | None: ...
    def latest_gex_levels(self, symbol: str) -> GexLevels | None: ...
    def latest_levels(self, symbol: str) -> list[Level]: ...
```

This engine should be the single point where TradeGEX turns into DEEP6 outputs.

---

### 4) `deep6/engines/tradegex_adapter.py`
Purpose: compatibility bridge into current DEEP6 contracts.

Responsibilities:
- Map `TradeGexBiasSnapshot` -> `GexLevels`
- Map `TradeGexBiasSnapshot` -> `GexSignal`
- Map `TradeGexMapLevel` -> `Level`

This is how you avoid duplicating `from_gex()` or changing downstream consumers too early.

Suggested adapters:
```python
def tradegex_to_gex_levels(snapshot: TradeGexBiasSnapshot) -> GexLevels: ...
def tradegex_to_gex_signal(snapshot: TradeGexBiasSnapshot, price: float) -> GexSignal: ...
def tradegex_to_levels(snapshot: TradeGexBiasSnapshot) -> list[Level]: ...
```

Important rule:
- Canonical GEX fields should map into existing `LevelKind`s.
- TradeGEX-only informational levels should initially stay out of LevelBus unless there is a clear consumer and dedupe policy.
- If needed later, extend `LevelKind` deliberately; do not overload existing kinds with unrelated semantics.

---

### 5) Optional: `deep6/publishing/tradegex_view_model.py`
Purpose: chart/dashboard output model.

Responsibilities:
- Build a lightweight, publishable structure for UI/websocket/chart scripts.
- Never feed back into trading logic.

This keeps chart concerns separate from market-state computation.

---

## Core data-flow

```text
TradeGEX source
  -> TradeGexObserver
  -> TradeGexNormalizer
  -> TradeGexEngine
      -> tradegex_to_gex_levels() -> LevelFactory/LevelBus
      -> tradegex_to_gex_signal() -> ConfluenceRules / scorer inputs
      -> TradeGexBiasSnapshot     -> dashboard / chart publishing
```

For NQ/ES/QQQ:
- QQQ can be native.
- ES and NQ should be native if TradeGEX provides them.
- If TradeGEX only gives ETF/index proxy data for some products, the adapter layer must own the conversion ratio and stamp that fact into `meta["proxy"]`.

---

## Concrete engine boundaries

### Keep `gex.py` but narrow its role
Recommended future boundary:
- `gex.py` = computed GEX fallback engine from raw options chain.
- `tradegex_engine.py` = preferred external market-map engine.

Do not merge them yet.
Instead define a tiny common protocol:
```python
class BiasLevelsProvider(Protocol):
    def get_levels(self, symbol: str) -> GexLevels | None: ...
    def get_signal(self, symbol: str, price: float) -> GexSignal | None: ...
```

Then both can satisfy the same downstream interface.

### Keep `kronos_bias.py` separate
Kronos predicts forward direction from OHLCV.
TradeGEX describes current options positioning / dealer map.

They should remain orthogonal:
- TradeGEX = structural/exogenous market-map bias
- Kronos = predictive/endogenous bar-model bias

Recommended composition rule:
- Never let TradeGEX replace Kronos.
- Combine them in a higher-level bias aggregator or scorer weighting layer.

### Keep `LevelBus` as the only active-level store
TradeGEX should not own lifecycle or dedupe.
It should emit `Level`s and let `LevelBus` handle:
- dedupe
- replacement of point levels
- query-near
- top-N selection
- confluence

That matches existing `zone_registry.py` design.

---

## Data contract mapping into current DEEP6 models

### Canonical level mapping
Use existing `LevelKind` first:
- TradeGEX call wall -> `LevelKind.CALL_WALL`
- TradeGEX put wall -> `LevelKind.PUT_WALL`
- TradeGEX gamma flip / zero -> `LevelKind.GAMMA_FLIP` and `LevelKind.ZERO_GAMMA`
- TradeGEX HVL / max gamma -> `LevelKind.HVL`, `LevelKind.LARGEST_GAMMA`

### Level scoring policy
Current `from_gex()` emits GEX levels with `score=0.0` and leaves weighting to downstream logic.
Keep that default for canonical GEX point levels to stay consistent with existing confluence behavior.

If TradeGEX exposes confidence/importance, store it in `meta`, for example:
```python
meta={
    "provider": "tradegex",
    "vendor_strength": 84.0,
    "map_type": "intraday",
    "session_date": "2026-04-23",
}
```

Do not directly inflate `Level.score` unless you also update LevelBus/confluence expectations.

### Bias contract
Suggested internal bias aggregation object:
```python
@dataclass(slots=True)
class MarketBiasState:
    symbol: str
    tradegex: TradeGexBiasSnapshot | None
    kronos: KronosBias | None
    gex_signal: GexSignal | None
    composite_direction: int
    composite_strength: float
    regime: str
    reasons: list[str]
```

That object belongs in a new bias-composition layer, not inside either engine.

---

## State machine

TradeGEX needs a stricter lifecycle than the current in-house `GexEngine` because vendor maps are often session-scoped.

Recommended snapshot FSM per symbol:

```text
EMPTY
  -> OBSERVED_RAW
  -> NORMALIZED
  -> ACTIVE
  -> STALE
  -> DEGRADED
  -> INVALID_SESSION
```

Definitions:
- `EMPTY`: nothing loaded yet
- `OBSERVED_RAW`: payload received, not validated
- `NORMALIZED`: parsed and structurally valid
- `ACTIVE`: accepted for current session and within freshness SLA
- `STALE`: last good snapshot exists but freshness exceeded
- `DEGRADED`: source failing/parsing failing; keep last good snapshot, marked degraded
- `INVALID_SESSION`: session date/map is from prior session and cannot be carried forward

Transition rules:
- `EMPTY -> OBSERVED_RAW` on any payload receipt
- `OBSERVED_RAW -> NORMALIZED` after required fields parse
- `NORMALIZED -> ACTIVE` if symbol/session/freshness checks pass
- `ACTIVE -> STALE` if `now - source_ts > staleness_seconds`
- `STALE -> ACTIVE` on fresh valid update
- `ACTIVE/STALE -> DEGRADED` on transport or parse failures when cached snapshot exists
- any state -> `INVALID_SESSION` on session rollover mismatch
- `INVALID_SESSION -> ACTIVE` only after new-session snapshot arrives

Operational rule:
- `ACTIVE` data can feed LevelBus and bias.
- `STALE` can feed charts with warning metadata, but should be down-weighted or excluded from trade entry logic.
- `DEGRADED` should preserve last visible map for operator awareness but emit a safety flag.
- `INVALID_SESSION` should not feed levels into current trade logic.

---

## How to avoid conflicting responsibilities

### Do not let TradeGEX duplicate `gex.py`
`gex.py` currently computes GEX from options chain and emits `GexLevels`/`GexSignal`.

TradeGEX should not recompute options-chain gamma math if vendor levels are already supplied.
Instead:
- TradeGEX = observed/precomputed external map
- `gex.py` = internal fallback/redundancy path

Add a source selector, e.g.:
```python
class GexSource(Enum):
    INTERNAL = auto()
    TRADEGEX = auto()
    AUTO = auto()
```

Resolution policy:
- `AUTO`: use TradeGEX when ACTIVE; else fall back to `gex.py`
- never blend the two into duplicated CALL_WALL/PUT_WALL records in LevelBus
- always stamp `meta["provider"]`

### Do not let TradeGEX duplicate `kronos_bias.py`
Kronos should stay independent and complementary.
Use explicit disagreement handling:
- same direction -> increase composite confidence
- opposite direction -> composite bias weakens, but levels remain valid

### Do not let TradeGEX own level lifecycle
TradeGEX emits point-in-time levels.
`LevelBus` owns persistence and replacement.
For vendor refreshes, point-level replacement by `(kind, price)` already exists in `zone_registry.py`; if price changes, the old point disappears and the new point is inserted, which is appropriate for daily map updates.

---

## Recommended integration with existing files

### `deep6/engines/gex.py`
Minimal changes:
- extract a common provider interface or wrapper
- keep current calculator intact as fallback
- optionally add `source="internal"` metadata when converted to Level objects

### `deep6/engines/level_factory.py`
Recommended extension:
- keep `from_gex()` unchanged for compatibility
- add `from_tradegex(snapshot)` or `from_tradegex_levels(levels)` rather than overloading `from_gex()` with vendor semantics

Reason:
TradeGEX may carry extra level roles not present in `GexLevels`.

### `deep6/engines/zone_registry.py`
Likely no structural changes needed.
Only ensure that imported TradeGEX point levels use existing `LevelKind`s for canonical walls/flip/HVL.

### `deep6/engines/confluence_rules.py`
Likely no structural changes needed for phase 1.
If TradeGEX becomes the source of `GexSignal`, existing rules can continue consuming `GexSignal`.

### `deep6/engines/live_pipeline.py`
This is where a later integration hook should live.
Suggested pattern:
- on bar close or periodic timer, refresh TradeGEX engine
- inject latest TradeGEX-derived `Level`s into shared `LevelBus`
- pass TradeGEX-derived `GexSignal` into scorer/confluence evaluation

Keep refresh cadence slower than bar cadence if vendor data is not tick-fast.

---

## Bias composition model

Recommended top-level composition order:
1. TradeGEX defines structural regime and high-value map levels.
2. Kronos defines directional forecast confidence.
3. Price action / narrative / volume profile confirms or rejects the map.

Simple policy:
- Structural bias source: TradeGEX
- Predictive bias source: Kronos
- Execution confirmation source: existing narrative/auction/delta/levels stack

Example composite logic:
```text
if TradeGEX regime == PIN:
  favor fades at call/put wall and de-emphasize breakout logic
elif TradeGEX regime == TREND:
  allow momentum continuation, especially when Kronos agrees
if Kronos disagrees with TradeGEX:
  lower confidence, not structural level validity
```

---

## Publishing model

For chart publishing, emit a single vendor-neutral payload:
```python
@dataclass(slots=True)
class PublishedMarketMap:
    symbol: str
    asof_ts: float
    regime: str
    bias_direction: int
    bias_strength: float
    levels: list[dict]
    stale: bool
    source: str
```

This should be generated from `TradeGexBiasSnapshot`, not from raw TradeGEX payloads.
That prevents UI breakage when vendor schema changes.

---

## Implementation order

### Phase 1: contracts and observer
1. Create `tradegex_observer.py`
2. Create `tradegex_normalizer.py`
3. Define `TradeGexRawSnapshot`, `TradeGexMapLevel`, `TradeGexBiasSnapshot`
4. Add fixture-based tests for raw payload parsing

Success criterion:
- can normalize one real TradeGEX payload for NQ/ES/QQQ into stable internal objects

### Phase 2: adapter into current DEEP6 types
5. Create `tradegex_adapter.py`
6. Implement `tradegex_to_gex_levels()` and `tradegex_to_gex_signal()`
7. Implement `tradegex_to_levels()` using existing `Level`/`LevelKind`
8. Add tests proving LevelBus dedupes correctly and confluence rules still work

Success criterion:
- existing GEX-aware consumers can run without knowing whether source is internal GEX or TradeGEX

### Phase 3: orchestration and source selection
9. Create `tradegex_engine.py`
10. Add freshness/session FSM
11. Add source selector: `TRADEGEX`, `INTERNAL`, `AUTO`
12. Wire into live runtime with fallback to `gex.py`

Success criterion:
- live system uses TradeGEX when fresh and automatically degrades to internal GEX when unavailable

### Phase 4: composite bias and publishing
13. Add a bias composition layer combining TradeGEX + Kronos
14. Publish normalized market map to dashboard/chart channel
15. Add stale/degraded visual warnings

Success criterion:
- one at-a-glance market bias view for NQ/ES/QQQ, plus downstream chart payloads

---

## Testing priorities

1. Payload normalization tests
   - vendor field missing
   - duplicate levels
   - stale timestamps
   - session rollover
   - proxy conversion correctness

2. Adapter tests
   - TradeGEX snapshot -> exact expected `GexLevels`
   - TradeGEX snapshot -> expected `LevelKind`s
   - zero/invalid prices dropped cleanly

3. LevelBus integration tests
   - duplicate canonical point levels replace, not accumulate
   - old session levels cleared or invalidated on rollover

4. Confluence regression tests
   - existing CR-01/02/03/04 behavior still works when levels originate from TradeGEX

5. Bias-composition tests
   - TradeGEX agrees with Kronos
   - TradeGEX conflicts with Kronos
   - stale TradeGEX with fresh Kronos

---

## Final recommendation

Use TradeGEX as a first-class upstream observer/normalizer, not as a replacement for DEEP6’s level system.

Best architecture:
- TradeGEX observer/adapter as the external-source boundary
- normalized market-map snapshot as the stable internal contract
- adapters into existing `GexLevels`, `GexSignal`, and `Level`
- LevelBus remains the only active-level store
- Kronos remains a separate predictive engine
- a later bias-composition layer merges TradeGEX structural bias with Kronos directional bias

This gives you:
- minimal disruption to current engines
- no duplicate GEX responsibilities
- native support for NQ/ES/QQQ
- clean path to dashboard/chart publishing
- safe fallback to current internal GEX computation
