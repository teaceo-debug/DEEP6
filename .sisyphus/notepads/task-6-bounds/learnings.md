\n+## 2026-05-23
- Centralized parameter bounds can stay config-agnostic by supporting both Pydantic models and plain dicts.
- StrategyConfig validation only needs to inspect nested bracket_exit/time_exit plus direct top-level tunables.
- A single bounds registry can cover entry, exit, volume profile, and depth radar params without importing the strategy model.

## 2026-05-29
- FlashAlpha adapter should stay thin and only normalize the existing nq_atlas client payload into gex_terminal schemas.
- QQQ→NQ conversion belongs downstream; the adapter should preserve source levels as provided.
- Graceful fallback can reuse the last known normalized snapshot while surfacing SourceHealth error state.
