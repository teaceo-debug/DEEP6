# Phase 17: NT8 Detector Refactor + Remaining Signals Port — Context

**Gathered:** 2026-04-15
**Status:** Ready for planning
**Source:** `/gsd-discuss-phase 17` — 4 gray areas, 11 decisions locked

<domain>
## Phase Boundary

Split the `DEEP6Footprint.cs` monolith (~95 KB) into per-family detector files behind an `ISignalDetector` registry, migrate the 10 already-live signals (ABS-01..04, ABS-07, EXH-01..06) into the new layout, and port the remaining 34 signals from the Python reference engine into NinjaScript — all firing bar-for-bar against live NT8 Rithmic data on NQ.

Signals in scope: IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07.

Kronos E10, TradingView MCP, FastAPI backend, and Next.js dashboard are **out of scope** for v1 (per 2026-04-15 pivot).

Phase delivers:
- `ISignalDetector` interface + detector registry in NinjaScript AddOns
- Detectors split into `AddOns/DEEP6/Detectors/{Family}/` with one file per detector (~34 new files)
- 34 newly ported signals firing under the new registry
- 10 existing signals migrated to the new registry (live code protected via feature flag)
- Parity: bit-for-bit match on synthetic fixtures; ±2 signals/type/session on recorded live replay
- Standalone NUnit test project at `ninjatrader/tests/` runnable via `dotnet test` on macOS
- Live-capture harness: record NT8 `OnMarketData` + `OnMarketDepth` to disk, replay through both engines
- Hand-rolled least-squares utility for CVD regression signals (DELT-10, EXH-05, TRAP-05)
- Pre-allocated `double[40]` DOM state per side

</domain>

<decisions>
## Implementation Decisions

### Detector interface + state ownership
- **Stateful instances.** Each detector is a class instance implementing `ISignalDetector`; owns its own rolling state (CVD deque, prior-bar ref, per-signal cooldown counters, sub-type tracking). Matches Python's engine-per-instance pattern for a near-1:1 port.
- Shared state (session POC, ATR tracker, CVD deque seed, bar history) lives on a single `SessionContext` singleton that detectors read. Detector-specific state stays on the instance.
- Registry calls each detector's `OnBar(bar, session)` method in registration order; detectors return a `SignalResult[]` that `DEEP6Strategy` consumes via the same confluence entry point.

### File/folder layout
- **One file per detector**, grouped by family: `Custom/AddOns/DEEP6/Detectors/{Imbalance,Delta,Auction,Trap,VolPattern,Engine}/`.
- Each detector file ≤ 300 LOC target (single class + its config). No single file exceeds 2000 LOC per ROADMAP success criterion #1.
- Namespace split stays as established in Phase 16: `NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.{Family}`.
- Registry + `ISignalDetector` interface at `AddOns/DEEP6/Registry/`.

### Legacy detector migration
- **Full migration in this phase.** Extract `AbsorptionDetector` and `ExhaustionDetector` from `DEEP6Footprint.cs` into the new layout (`AddOns/DEEP6/Detectors/Absorption/` and `AddOns/DEEP6/Detectors/Exhaustion/`).
- Migration verified against known-good live behavior before new detectors are layered on (parity gate in Wave 2).

### Migration sequencing
- **Refactor first, then port by family.**
  - **Wave 1:** Extract `ISignalDetector` interface + `DetectorRegistry` + migrate ABS/EXH into new layout
  - **Wave 2:** Parity verification — migrated ABS/EXH must match pre-refactor behavior bit-for-bit on captured session; no regression in DEEP6Strategy live behavior
  - **Wave 3+:** Port new families one per wave, TRIVIAL complexity first

### Port ordering
- **By complexity tier: TRIVIAL → MODERATE → HARD.** Ship easy wins early to de-risk C# port idioms, tackle hardest signals (DELT-10 CVD regression, ENG-02 logistic, ENG-03 Wasserstein) once patterns are proven.
- Port backlog groupings (from 2026-04-15 audit):
  - TRIVIAL (14): IMB-01, IMB-06, IMB-08, DELT-01, DELT-02, DELT-03, DELT-05, DELT-09, AUCT-02, VOLP-02, VOLP-03, VOLP-06, plus legacy ABS-04/EXH-01/EXH-03/EXH-04 re-verify
  - MODERATE (17): IMB-02..05, IMB-07, IMB-09, DELT-04, DELT-06, DELT-07, DELT-11, AUCT-01, AUCT-03, AUCT-04, AUCT-05, TRAP-01..04, VOLP-01, VOLP-04, VOLP-05
  - HARD (6): DELT-08, DELT-10, TRAP-05, ENG-02, ENG-03, ENG-05 + partially-complete ENG-04, ENG-06

### Mid-phase live protection
- **Feature flag the new registry.** Add `UseNewRegistry` bool property on `DEEP6Strategy`; when `false` (default until Wave 2 parity passes), strategy uses existing ABS/EXH static calls. Flip to `true` after migrated detectors pass parity.
- Allows instant rollback by toggling a single NT8 property if a live-trading regression shows up after cutover.

### Parity pass bar
- **Bit-for-bit on synthetic fixtures** (unit tests): C# output must exactly match Python on hand-crafted FootprintBar + DOMState scenarios — same boolean signal flags, strength values to 4 decimals, sub-type classifications.
- **Tolerance-bounded on session replay:** C# signal count per session within ±2 per signal type vs Python. Tolerance accounts for NT8 aggressor heuristic (`price >= bestAsk`) vs Python's Rithmic aggressor field differences.
- ROADMAP Phase 17 success criterion #3 updated to reference this tolerance envelope.

### Parity dataset source
- **Live NT8 capture, replayed through both engines.** Build a capture harness that records `OnMarketData` + `OnMarketDepth` events to a deterministic log file during live RTH on Apex sim. Replay loader feeds the log through the C# detector pipeline and (via Databento MBO proxy or log-to-MBO translator) through the Python engine.
- Minimum 5 recorded sessions covering varied regimes (trending, balanced, news-driven) before parity is declared passing.

### Test harness
- **Standalone NUnit project at `ninjatrader/tests/`** with its own `.csproj`, referencing detector classes as a library build (not via NT8 Custom/ compile path).
- Runs via `dotnet test` on macOS — no NT8 dependency, no Windows dependency, CI-ready.
- Per-detector fixture files committed to repo under `ninjatrader/tests/fixtures/{family}/{signal-id}.json` (hand-crafted FootprintBar snapshots with expected output).
- NT8 "Strategy Analyzer" replay is an additional smoke test, not the primary regression surface.

### Regression math library
- **Hand-rolled least-squares.** ~20 lines of C# for 1st/2nd-order polynomial fit. Zero external dependency. Lives at `AddOns/DEEP6/Math/LeastSquares.cs`. Deterministic match with `numpy.polyfit` at double precision.
- Consumers: DELT-10 (CVD multi-bar divergence), EXH-05 (fading momentum via CVD slope), TRAP-05 (CVD trend reversal).

### Python reference bug policy
- **Fix Python too; NT8 mirrors the fix.** Python is the source-of-truth for signal definitions; a latent bug there would poison parity validation for Phase 17 and every later phase.
- Workflow when a bug is found: (1) fix in `deep6/engines/*.py`, (2) update Python unit tests, (3) port corrected logic to C#, (4) re-run parity harness. Each correction documented in the corresponding plan's SUMMARY.md.

### DOM state representation
- **Pre-allocated `double[40]` arrays per side.** 40 bid levels + 40 ask levels as fixed-size arrays. Zero GC pressure on the hot path (`OnMarketDepth` at 1000+ upd/sec). O(1) lookup by price index (computed from best-bid/best-ask offset).
- Matches Python's NumPy `DOMState` pattern for faithful port of depth-consuming detectors (E2 trespass, E3 counter-spoof, E4 iceberg).

### Claude's Discretion
- Specific logging verbosity per detector (Print statements during development, can be silenced at registration time)
- Exact `SignalFlags` uint64 bit assignments for new signals (must be collision-free with existing ABS/EXH bits; planner to decide layout)
- Fixture JSON schema (round-trippable via Newtonsoft.Json already available in NT8)
- Thread-safety specifics for each detector (follow Phase 16 pattern: data thread reads, chart thread writes; snapshot-copy on boundary)
- Per-detector cooldown defaults (reuse Phase 16 default of 5 bars unless Python engine specifies otherwise)
- Exact replay log file format (binary vs newline-delimited JSON — planner to pick based on write throughput)
- Whether Wave 2 parity uses a freshly captured live session or a pre-recorded one committed to repo

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Python reference implementation (source-of-truth for ports)
- `deep6/engines/imbalance.py` — IMB-01..09 algorithms (single, multiple, stacked T1/T2/T3, reverse, inverse, oversized, consecutive, diagonal, reversal pattern)
- `deep6/engines/delta.py` — DELT-01..11 (rise/drop, tail, flip, divergence, sign change, aggressive reversal, level accumulation, compression-expansion, session extremes, CVD polyfit divergence, rate-of-change)
- `deep6/engines/auction.py` — AUCT-01..05 (unfinished, finished, poor high/low, volume void, market sweep) + E9 AuctionFSM
- `deep6/engines/trap.py` — TRAP-01..05 (inverse imbalance, delta trap, false breakout, record-vol rejection, CVD trend reversal)
- `deep6/engines/vol_patterns.py` — VOLP-01..06 (escalation, bubble, surge, POC wave, delta velocity spike, big delta per level)
- `deep6/engines/trespass.py` — ENG-02 multi-level weighted DOM imbalance + logistic regression
- `deep6/engines/counter_spoof.py` — ENG-03 Wasserstein-1 + large-order cancel detection
- `deep6/engines/iceberg.py` — ENG-04 native + synthetic (refill < 250ms) iceberg detection
- `deep6/engines/micro_prob.py` — ENG-05 Naïve Bayes micro probability
- `deep6/engines/vp_context_engine.py` — ENG-06 DEX-ARRAY + VWAP/IB/GEX/POC + LVN lifecycle
- `deep6/engines/signal_config.py` — ENG-07 config + threshold scaffold

### Python shared infrastructure (port-blocking dependencies)
- `deep6/state/footprint.py` — FootprintBar structure + intrabar delta tracking
- `deep6/state/dom.py` — DOMState 40-level pre-allocation pattern
- `deep6/state/session.py` — SessionContext (open/close, regime, CVD, VWAP, IB anchor)
- `deep6/signals/atr.py` — Wilder's ATR(20) incremental formula
- `deep6/signals/flags.py` — 45-bit SignalFlags bitmask layout
- `deep6/engines/zone_registry.py` — ZoneRegistry / LevelBus (17 LevelKind, merging, overlap rules)
- `deep6/scoring/scorer.py` — two-layer confluence scorer (Phase 18 primary reference, but port data layout informs Phase 17 signal output shape)

### Phase 16 C# baseline (where we extend from)
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6Footprint.cs` — monolith being split; source for ABS/EXH extraction
- `ninjatrader/Custom/Strategies/DEEP6/DEEP6Strategy.cs` — confluence consumer; needs registry integration + feature flag
- `.planning/phases/16-ninjatrader-8-footprint-indicator-standalone-parallel-delive/PORT-SPEC.md` — authoritative port-spec template for ABS/EXH; extend this pattern to the new 34

### Planning context
- `.planning/PROJECT.md` — NT8-primary pivot rationale (2026-04-15)
- `.planning/ROADMAP.md` Phase 17 entry — goal, 5 success criteria, plan outline
- `.planning/REQUIREMENTS.md` — signal IDs IMB-01..09, DELT-01..11, AUCT-01..05, TRAP-01..05, VOLP-01..06, ENG-02..07 (source of truth for requirement traceability)

### Test/validation references
- `tests/` (Python) — reference behavior for fixture generation; `test_imbalance.py`, `test_delta.py`, `test_auction.py`, etc.
- `deep6/engines/tests/` — per-engine unit test templates to mirror in C# NUnit fixtures

</canonical_refs>

<specifics>
## Specific Ideas

- Existing strategy risk gates (account whitelist, RTH window, news blackout, daily loss cap) stay intact — refactor must not touch `DEEP6Strategy.cs` risk-gate paths
- GEX timer + massive.com client (lines 769-924 of `DEEP6Footprint.cs`) stays where it is for Phase 17; can be refactored in a later phase
- Aggressor classification heuristic (NT8: `price >= bestAsk` → buy) stays unchanged in this phase — any aggressor-field-driven parity drift is accepted within the ±2 signals/type/session tolerance
- New detectors read bar data + DOM state via the `SessionContext` singleton; the singleton lifecycle stays tied to NT8's indicator lifecycle (creation on first bar, reset on session boundary)
- `ninjatrader/tests/` NUnit project uses .NET 4.8 target (matches NT8 runtime) — not .NET 6+ — to guarantee binary compat if we ever want to reference test assemblies inside NT8
- Feature flag name: `UseNewRegistry` on `DEEP6Strategy` (explicit, NT8 Properties-panel visible)
- Capture harness output file format: newline-delimited JSON under `ninjatrader/captures/YYYY-MM-DD-session.ndjson` (planner may switch to a binary format if benchmarks show NDJSON write throughput bottlenecks live capture)

</specifics>

<deferred>
## Deferred Ideas

- Kronos E10 (ENG-10 equivalent) — out of scope v1 per 2026-04-15 pivot; revisit if backtests justify
- GEX engine refactor into new detector layout — keep Phase 16 GEX code in place; eligible for Phase 18+
- Two-layer confluence scorer port — explicitly Phase 18
- Apex/Lucid paper-trade gate — explicitly Phase 19
- TradingView MCP integration — out of scope v1
- FastAPI / Next.js dashboard — out of scope v1
- Databento live feed (as live runtime) — out of scope v1; historical Databento MBO only for parity dataset generation
- EventStore / ML backend — out of scope v1

</deferred>

---

*Phase: 17-nt8-detector-refactor-remaining-signals-port*
*Context gathered: 2026-04-15 via /gsd-discuss-phase*
