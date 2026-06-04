## 2026-05-12 Decisions
- Implemented prompt compaction with rolling MarketContext history and progressively smaller history sections to keep LLM context under budget.

- Kept copilot tests green by matching the implementation to the test contract instead of changing `types.py` or `config.py`.
- For missing Anthropic installs, prefer a stub module over test-only monkeypatching so import-time patch targets remain available.

## 2026-05-12 token_budget removal
- Removed `deep6/copilot/token_budget.py` and redirected imports to `deep6/copilot/budget.py`.
- Preserved backwards compatibility by patching the `budget.TokenBudgetTracker` class at package import time instead of editing `budget.py` directly.


- 2026-05-12: ContextAggregator GEX/Kronos collectors now prefer dedicated adapters but fall back to bridge_client getters (get_latest_gex/get_latest_kronos) so the default session path can surface those sources without extra adapter wiring.
