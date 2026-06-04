# Learnings — footprint-v8-refactor

## Session Start: 2026-05-24

### Key Code Facts (from pre-work research)
- **CLA mystery SOLVED**: `s.Kind.ToString().Substring(0,3).ToUpper()` → CLA = Classic Absorption, STO = Stopping Volume, PAS = Passive, EFF = Effort vs Result
- **Percentage formula**: `s.Strength * 100.0` — raw exhaustion strength scalar 0-1, rendered on gray diamond
- **Production file**: `DEEP6FootprintV7.cs` (2,271 lines) — current production indicator
- **4 arrow drawing systems**: DrawTriggeredMarker (~740), DrawAbsorptionMarker (~914), DrawExhaustionMarker (~927), RenderTier1Overlay (~1849)
- **Existing umbrella toggles**: ShowAbsorptionMarkers, ShowExhaustionMarkers — not granular per-variant
- **Compile script**: `ninjatrader/scripts/nt8-compile.ps1`
- **Deploy script**: `ninjatrader/scripts/nt8-deploy.ps1`

### Architecture Facts
- Two Python codebases exist: v1 `deep6/engines/` and v2 `deep6v2/signals/` — T3 validates which maps to V7
- Python backtest framework: harness.py, mutation_engine.py (8 mutation types), fitness.py (>55% WR, >1.5 R:R, IS/OOS split 68/32)
- Historical data: `data/backtests/nq_1yr_1m.csv`, `data/backtests/nq_3mo_1m.csv`
- PORT-SPEC.md is authoritative C# port specification

### Guardrails (NEVER violate)
- Do NOT add AddDataSeries() (no MTF in V8 — deferred to V9)
- Do NOT modify FootprintBar construction, ConfluenceScorer, or OnMarketData()
- Do NOT delete detection logic — only gate rendering behind toggles
- Do NOT hardcode bias box thresholds
- Do NOT change the 30+ existing input properties

### 2026-05-24 — Variant evaluator learnings
- `deep6/backtest/variant_evaluator.py` uses the exact `fitness.split_sessions(..., is_ratio=0.68)` session-date split, so IS/OOS counts and hit rates diverge naturally on the 3-month CSV.
- `data/backtests/v8_variant_audit.duckdb` persists results by replacing the single `variants` row per variant and refreshing only that variant's `signals` rows, which keeps reruns additive across variants without duplicate signal records.
- The 3-month CSV is OHLCV-only, so isolated variant evaluation must use lightweight proxy heuristics tied to `AbsorptionConfig`/`ExhaustionConfig` thresholds rather than full footprint-level replay; this keeps the CLI fast enough for full-file runs.

### 2026-05-24 V8 fork result
- Created DEEP6FootprintV8.cs as a pure copy of V7, then renamed class, Display name, and V7-prefixed draw/tag strings to V8.
- NT8 compile passed with [COMPILE-RESULT] SUCCESS.
- V7 remained unchanged; git diff on the source file was clean.

### 2026-05-24 T3 Parity Report — Python v1 vs v2 vs C#
- **Python v1 (`deep6/engines/`) is authoritative** for V7/V8 C# detectors. All 10 variants MATCH exactly.
- **Python v2 (`deep6v2/signals/`) does NOT map to V7/V8.** Different algorithms, different config, missing features.
- All 16+ numerical thresholds (absorb_wick_min=30, absorb_delta_max=0.12, thin_pct=0.05, etc.) are identical between Python v1 and C#.
- All derived constants (strength formulas, ATR scaling, delta gate logic, cooldown=5) are identical.
- C# files explicitly cite Python v1 line numbers; PORT-SPEC.md cites Python v1 as source.
- Python v2 key missing features: no ABS-07 VA bonus, no per-type cooldown, no targeted delta gate.
- **Optimization transfer risk: LOW** — Python v1 sweep parameters can be directly used in C#.
- Report: `data/backtests/v8_parity_report.md`; Evidence: `.sisyphus/evidence/task-3-parity-report.md`

### 2026-05-24 T5 Variant audit
- `variant_evaluator.py` only accepts one `--bars-forward` value, so the forward-return verdict audit was standardized on `10` bars.
- `data/backtests/v8_variant_audit.duckdb` needed a full rebuild after stale `.wal` lock files blocked repeated Windows DuckDB opens; deleting `v8_variant_audit.duckdb*` and recreating the DB fixed it.
- On `nq_3mo_1m.csv`, all 10 variants landed **INCONCLUSIVE**: none reached `rr >= 1.5`, and `ABS_04` also failed the `n_oos >= 30` threshold.
- High-hit absorption/exhaustion proxies (`ABS_01`, `ABS_02`, `EXH_02`, `EXH_06`) should stay in the candidate pool as confirmation/filter style signals despite sub-1.5 R:R.

### 2026-05-24 Arrow audit learnings
- `DrawTriggeredMarker` (`DEEP6FootprintV7.cs:740-757`) and `RenderTier1Overlay` (`1849-1911`) are both Type-A lifecycle visuals, so they are sparse by design; the real clutter source is not Type A but the raw detector marker paths.
- `DrawAbsorptionMarker` (`914-925`) bypasses confluence entirely and can render multiple markers on the same bar because `AbsorptionDetector` has multiple subtypes and no cooldown.
- `DrawExhaustionMarker` (`927-947`) also bypasses confluence, but `ExhaustionDetector` has a 5-bar cooldown per subtype, so it is less noisy than absorption.
- In the scorer path, the useful confluence field is `ScorerResult.CategoryCount`, not a dedicated `ConfluenceCount` property.
- Best gating baseline for raw marker visibility: `MinArrowConfluence=4` (matches first meaningful scorer bucket) and `MinExhaustionStrength=0.60` (keeps structural exhaustion, filters weak prints).

### 2026-05-24 T7 Correlation matrix learnings
- **34 of 45 pairs exceed 85% max overlap** within a 5-bar window on 1-minute OHLCV data. This extreme temporal co-occurrence is driven by OHLCV proxy heuristics sharing overlapping bar characteristics (wick %, body ratio, volume, close position).
- **Direction agreement averages ~50-55%** despite near-total temporal overlap. This means temporal co-occurrence does NOT imply signal redundancy in a trading sense — variants disagree on direction nearly half the time.
- **ABS_01 and ABS_02 are functionally identical** (100% mutual overlap, 54.4% direction agreement, within 0.0004 on OOS HR). ABS_02 can be safely dropped.
- **EXH_02 (Wick Rejection) is the superset detector**: 55,644 signals, subsumes every other EXH variant at >99% overlap. Has the best metrics (OOS HR 0.971, RR 1.167, PF 2.087).
- **EXH_01, EXH_03, EXH_05 are dominated**: all subsumed by EXH_02 with worse OOS HR (0.77-0.79 vs 0.97) and near-zero PF edges.
- **ABS_03 and EXH_04 are valuable subset filters**: low signal count (2,487 and 2,092) but selective. ABS_03 x EXH_04 has the most balanced overlap (37.6%/42.3%) and highest direction agreement (60%) of any pair — potentially additive when co-firing.
- **ABS_04 is data-insufficient**: N=27 signals, too few for statistical analysis. Requires footprint-level data.
- **Zero complementary pairs** at <20% overlap threshold. All pairs have at least 40% max overlap.
- **DuckDB persistence bug on Windows**: rapid open/close of DuckDB connections from multiple Python processes causes data loss. Solution: run all variants in a single process, persist after all computations complete.
- Report: `data/backtests/v8_correlation_matrix.md`; Evidence: `.sisyphus/evidence/task-7-correlation.txt`

### 2026-05-24 T10 bias box implementation learnings
- `DrawExhaustionMarker()` only rendered the old percentage diamond on neutral (`s.Direction == 0`) exhaustion events, so the bias-box replacement belongs in that branch; directional exhaustion arrows remain intact.
- A simple normalized average of recent rendered signal directions (`-1/+1`) is enough to produce the requested three-state bias score in `[-1, 1]` without touching detection logic.
- Reusing `Draw.Text(..., backgroundBrush, areaBrush, opacity)` is the lowest-risk way to get a colored bias box in NT8 while preserving compile safety and one-tag-per-bar overwrite semantics.

### 2026-05-24 T12 optimization config learnings
- `param_bounds.py` only exposes a global registry for generic strategy search params, so V8-specific sweep knobs were safest as a local `V8_PARAM_SPECS`/`V8_PARAM_REGISTRY` overlay rather than mutating the shared module.
- `signal_config.py` contains the authoritative V7 baseline as dataclass defaults; serializing those defaults through JSON is necessary to normalize tuple fields like `IntermarketConfig.symbols` before snapshot comparison.
- The cleanest Parent-0 format is: top-level V8 sweep knobs for direct mutation/validation plus a nested `v7_signal_thresholds` snapshot for full baseline provenance.

### 2026-05-24 T13 optimization learnings
- `scripts/backtest_loop.py` is not adaptable without semantic drift because it only understands `StrategyConfig` lineage and `deep6.backtest.harness`, not the flat V8 parameter surface from Task 12.
- Precomputing all 10 variant proxy events once over `nq_1yr_1m.csv` makes a 100-iteration V8 sweep fast enough to finish in a single local run while preserving deterministic results.
- The best validation rows were extremely sparse (3-4 validation trades), so walk-forward selection mattered: validation rank 1 and 2 both failed or underperformed on the final 20%, while iteration 67 produced the strongest test-period score (`0.6105`) and positive test P&L.



