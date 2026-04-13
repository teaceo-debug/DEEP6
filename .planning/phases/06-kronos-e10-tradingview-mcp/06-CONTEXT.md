# Phase 6: Kronos E10 + TradingView MCP - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Kronos-small runs in a dedicated subprocess with persistent GPU model load providing directional bias every 5 bars with confidence decay; TradingView MCP configured for Claude chart interaction. `kronos_bias.py` (232 lines) already exists — this phase validates, adds subprocess isolation, confidence decay, and ensures TV MCP is wired.

**Key reality:** KronosBias engine exists. Kronos model loading/inference needs to be verified on M2 Mac (MPS or CPU). TradingView MCP is a Node.js tool already in the project stack — configuration only, no Python code needed.

</domain>

<decisions>
## Implementation Decisions

### Kronos Subprocess
- **D-01:** Kronos-small (24.7M params) in dedicated subprocess via multiprocessing.Pipe. Main event loop never blocked during inference.
- **D-02:** 20 stochastic samples per inference for confidence score (0-100).
- **D-03:** Update every 5 bars with 0.95/bar decay between inferences.
- **D-04:** If GPU inference latency > bar duration budget on M2 Mac, use CPU fallback with documented tolerance.

### TradingView MCP
- **D-05:** Configuration task only — ensure tradingview-mcp is in Claude Code MCP config and can read chart state.
- **D-06:** No Python code needed — TV MCP is a Claude Code tool, not part of the DEEP6 runtime.

### Config
- **D-07:** Add `KronosConfig` to signal_config.py with inference_interval, decay_rate, sample_count, model_name.

### Claude's Discretion
- Subprocess communication protocol details
- Inference benchmarking approach
- TV MCP setup verification method

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` §KRON, §TVMCP — Requirement IDs
- `deep6/engines/kronos_bias.py` — Existing KronosBias engine
- `deep6/engines/signal_config.py` — Config pattern
- `.planning/research/STACK.md` — Kronos HuggingFace model, TV MCP setup

</canonical_refs>

<code_context>
## Existing Code Insights
- KronosBias exists but needs subprocess isolation
- Kronos model requires PyTorch + transformers
- TV MCP is Node.js, separate from Python runtime

</code_context>

<specifics>
## Specific Ideas
- Benchmark inference on M2 Mac before committing to per-bar frequency
- Kronos only needs OHLCV — can use Databento historical bars
</specifics>

<deferred>
## Deferred Ideas
None
</deferred>

---
*Phase: 06-kronos-e10-tradingview-mcp*
*Context gathered: 2026-04-13*
