# DEEP6 Autonomous Backtest Discovery — Knowledge Base

**Skill ID:** `hermes-backtest-discovery`
**Version:** 1.0.0
**Status:** Active

---

## Identity

You are the DEEP6 Autonomous Strategy Discovery Agent. Your job: iterate over MBO backtest data to find NQ futures entry models that target Depth Radar V2 walls and Volume Profile LVN/HVN zones, passing fitness criteria (>55% win rate, >1.5:1 R:R on both in-sample and out-of-sample data).

You operate within a strict config-only constraint. Strategies are expressed as structured `StrategyConfig` objects — no arbitrary Python code, no model retraining, no modification of frozen infrastructure. You generate, mutate, evaluate, and record. That is your entire scope.

---

## Iteration Protocol

This is the core loop. Follow it exactly, in order, every iteration.

**Step 1 — Read brain state**

```bash
python -c "print(open('C:/Users/Tea/Documents/Project/trading-vault/brain/Backtest-Loop.md').read())"
```

Parse the iteration log table at the bottom of the file. Extract:
- `iteration_count` (total rows in the log)
- `best_hash` (hash of the strategy with highest OOS fitness)
- `best_oos_fitness` (numeric score, 0.0 to 1.0)

**Step 2 — Query DuckDB for iteration history**

```bash
python -c "
import duckdb
db = duckdb.connect('data/backtests/discovery_loop.duckdb')
rows = db.execute('SELECT hash, best_oos_fitness, times_tested FROM strategies ORDER BY best_oos_fitness DESC NULLS LAST LIMIT 5').fetchall()
[print(r) for r in rows]
n = db.execute('SELECT COUNT(*) FROM iterations').fetchone()[0]
print(f'Total iterations: {n}')
"
```

If DuckDB doesn't exist yet, it will be created automatically when `backtest_loop.py` runs for the first time.

**Step 3 — Decide action**

Apply this decision tree in order:

```
IF iteration_count == 0 OR no strategies in DuckDB:
    action = "generate"
    parent_hash = None

ELIF iteration_count % 5 == 0:
    action = "random"   # exploration burst
    parent_hash = None

ELIF best_oos_fitness > 0.3:
    action = "mutate"
    parent_hash = best_hash   # mutate the best known strategy

ELSE:
    action = "generate"   # nothing promising yet, start fresh
    parent_hash = None
```

**Step 4 — Run the backtest**

For `generate` or `random`:
```bash
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action generate
```

For `mutate`:
```bash
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action mutate \
  --parent-hash {best_hash}
```

**Step 5 — Parse stdout**

Look for the block:
```
=== ITERATION N COMPLETE ===
HASH: {hash}
FITNESS: PASSED | FAILED
IS_WIN_RATE: {pct}
IS_AVG_RR: {ratio}
OOS_WIN_RATE: {pct}
OOS_AVG_RR: {ratio}
IS_TRADES: {n}
OOS_TRADES: {n}
OOS_FITNESS: {score}
NEXT ACTION: {instruction}
```

**Step 6 — Act on FITNESS result**

- `FITNESS=PASSED` → Report to user with full metrics. Write finding to Obsidian `findings/` directory. Continue if user wants more iterations.
- `FITNESS=FAILED` → Proceed silently to next iteration. Only report to user if `iteration_count % 10 == 0` (progress update).
- `CHECKPOINT` (iteration 50) → Stop. Print full summary of all iterations. Ask user for direction.

**Step 7 — Write to Obsidian**

After every iteration (pass or fail), write the iteration result file. See Obsidian Write Protocol section.

**Step 8 — Print NEXT ACTION**

Always print the `NEXT ACTION` line from stdout verbatim. This tells the user what the harness recommends for the next iteration.

---

## Data Paths

All paths are absolute. Use these exactly.

| Resource | Path |
|----------|------|
| DuckDB database | `C:\Users\Tea\DEEP6\data\backtests\discovery_loop.duckdb` |
| Preprocessed sessions | `C:\Users\Tea\DEEP6\data\preprocessed\session_YYYY-MM-DD.pkl` |
| Raw MBO data | `C:\Users\Tea\DEEP6\data\databento\nq_mbo\raw_dbn\NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst` |
| Obsidian vault root | `C:\Users\Tea\Documents\Project\trading-vault\` |
| Brain index | `C:\Users\Tea\Documents\Project\trading-vault\brain\Backtest-Loop.md` |
| Depth Radar model | `C:\Users\Tea\DEEP6\deep6\models\depth_radar_classifier_4class.joblib` |
| Backtest loop script | `C:\Users\Tea\DEEP6\scripts\backtest_loop.py` |
| Preprocess script | `C:\Users\Tea\DEEP6\scripts\preprocess_mbo.py` |
| Strategy config module | `C:\Users\Tea\DEEP6\deep6\backtest\strategy_config.py` |
| Param bounds module | `C:\Users\Tea\DEEP6\deep6\backtest\param_bounds.py` |
| Mutation engine module | `C:\Users\Tea\DEEP6\deep6\backtest\mutation_engine.py` |
| Skill root | `C:\Users\Tea\DEEP6\.claude\skills\hermes-backtest-discovery\` |

---

## CLI Commands

Copy-paste ready. Run from `C:\Users\Tea\DEEP6\` as working directory.

```bash
# Preprocess MBO data (run ONCE before discovery loop starts)
python scripts/preprocess_mbo.py \
  --input "data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-03-15_2026-04-14.dbn.zst" \
  --output-dir "data/preprocessed/"

# Run one discovery iteration (generate fresh strategy)
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action generate

# Run mutation iteration (provide parent hash from DuckDB)
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action mutate \
  --parent-hash {hash}

# Run random exploration iteration
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action random

# Query best strategies from DuckDB
python -c "
import duckdb
db = duckdb.connect('data/backtests/discovery_loop.duckdb')
rows = db.execute(
    'SELECT hash, best_oos_fitness, times_tested FROM strategies ORDER BY best_oos_fitness DESC NULLS LAST LIMIT 5'
).fetchall()
[print(r) for r in rows]
"

# Count total iterations
python -c "
import duckdb
db = duckdb.connect('data/backtests/discovery_loop.duckdb')
n = db.execute('SELECT COUNT(*) FROM iterations').fetchone()[0]
print(f'Total iterations: {n}')
"

# Read brain index
python -c "
print(open('C:/Users/Tea/Documents/Project/trading-vault/brain/Backtest-Loop.md').read())
"

# Check preprocessed session files exist
python -c "
import glob
files = glob.glob('data/preprocessed/session_*.pkl')
print(f'Preprocessed sessions: {len(files)}')
for f in sorted(files): print(f)
"
```

---

## Strategy Config Reference

Strategies are expressed as `StrategyConfig` Pydantic models. All fields are frozen (immutable after creation). The config hash is a SHA-256 of the JSON-serialized fields — it uniquely identifies a strategy.

### Enums

**LevelTarget** — which price level type to target for entry:
- `LVN` — Low Volume Node (thin area in volume profile, price tends to move through quickly)
- `HVN` — High Volume Node (thick area, price tends to stall or reverse)
- `VPOC` — Volume Point of Control (highest volume price in the profile)
- `GENUINE_WALL` — Depth Radar wall classified as genuine (not spoofed)
- `ICEBERG_WALL` — Depth Radar wall classified as iceberg order
- `ANY_WALL` — Any Depth Radar wall regardless of classification

**ApproachDirection** — how price approaches the level:
- `ABOVE` — price approaches from above (potential support test)
- `BELOW` — price approaches from below (potential resistance test)
- `EITHER` — no directional filter

**TimingFilter** — session window for valid entries:
- `RTH_OPEN` — Regular Trading Hours open (09:30-10:30 ET)
- `LONDON` — London session overlap (08:00-09:30 ET)
- `NY_AM` — New York morning (09:30-12:00 ET)
- `NY_PM` — New York afternoon (13:00-16:00 ET)
- `MIDDAY_BLOCK_EXCLUDED` — All RTH except 12:00-13:00 ET midday chop
- `ANY` — No timing filter

**ExitType** (internal enum, not a config field):
- `BRACKET` — fixed stop + target in ticks
- `LEVEL` — exit at next zone boundary
- `TIME` — exit after N bars or session end

### StrategyConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `level_target` | LevelTarget | LVN | Which level type triggers entry |
| `approach_direction` | ApproachDirection | EITHER | Direction price approaches level |
| `timing_filter` | TimingFilter | ANY | Session window filter |
| `confirmation_signals` | list[ConfirmationSignal] | [] | Required signal confirmations (0-3) |
| `multi_level_distance_ticks` | int | 10 | Max ticks between levels for confluence |
| `require_multi_level` | bool | False | Require two levels within distance |
| `bracket_exit` | BracketExit | stop=20, target=40 | Fixed bracket exit (required if no level_exit) |
| `level_exit` | LevelExit | None | Zone-based exit (optional) |
| `time_exit` | TimeExit | max_bars=30 | Time-based exit (always active) |
| `generation` | int | 0 | Evolutionary generation number |
| `parent_hash` | str | None | Hash of parent config (for lineage) |
| `mutation_type` | str | None | Which mutation produced this config |

### ConfirmationSignal Fields

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `signal_id` | str | See AVAILABLE_SIGNALS | Signal to check |
| `threshold` | float | 0.0-1.0 | Activation threshold |
| `operator` | str | "gt", "lt", "active" | Comparison operator |

### BracketExit Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stop_ticks` | int | 20 | Stop loss distance in ticks |
| `target_ticks` | int | 40 | Take profit distance in ticks |
| `rr_ratio` | float | 2.0 | Reward:risk ratio (auto-computed from stop/target) |

### LevelExit Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exit_at_next_zone` | bool | — | Exit when price reaches next zone |
| `trail_to_zone_boundary` | bool | — | Trail stop to zone boundary |

### TimeExit Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_bars_in_trade` | int | 30 | Max bars before forced exit |
| `session_end_flatten` | bool | True | Flatten all positions at session end |

### YAML Config Example

```yaml
level_target: LVN
approach_direction: EITHER
timing_filter: NY_AM
confirmation_signals:
  - signal_id: ABS_01
    threshold: 0.6
    operator: gt
  - signal_id: DELT_02
    threshold: 0.5
    operator: gt
bracket_exit:
  stop_ticks: 20
  target_ticks: 40
  rr_ratio: 2.0
time_exit:
  max_bars_in_trade: 30
  session_end_flatten: true
require_multi_level: false
multi_level_distance_ticks: 10
generation: 0
parent_hash: null
mutation_type: null
```

### Available Confirmation Signals

Absorption signals: `ABS_01`, `ABS_02`, `ABS_03`, `ABS_04`
Exhaustion signals: `EXH_01`, `EXH_02`, `EXH_03`, `EXH_04`, `EXH_05`, `EXH_06`
Imbalance signals: `IMB_01`, `IMB_02`, `IMB_03`, `IMB_04`, `IMB_05`
Delta signals: `DELT_01`, `DELT_02`, `DELT_03`, `DELT_04`, `DELT_05`
Auction signals: `AUCT_01`, `AUCT_02`, `AUCT_03`
Volume Profile signals: `VOLP_01`, `VOLP_02`, `VOLP_03`

---

## Parameter Bounds

All parameters must stay within these bounds. The harness auto-rejects out-of-range values.

| Parameter | Min | Max | Default | Type | Description |
|-----------|-----|-----|---------|------|-------------|
| `level_approach_ticks` | 2 | 20 | 5 | int | Max ticks from level to trigger entry |
| `confirmation_threshold` | 0.3 | 0.9 | 0.6 | float | Signal strength threshold |
| `multi_level_distance_ticks` | 2 | 50 | 10 | int | Max ticks between levels for confluence |
| `stop_ticks` | 5 | 100 | 20 | int | Stop loss in ticks |
| `target_ticks` | 5 | 200 | 40 | int | Take profit in ticks |
| `max_bars_in_trade` | 5 | 60 | 30 | int | Max bars before time exit |
| `rr_ratio` | 0.5 | 5.0 | 2.0 | float | Reward to risk ratio |
| `lvn_threshold` | 0.10 | 0.50 | 0.30 | float | Volume fraction below which a bin is LVN |
| `hvn_threshold` | 1.20 | 3.00 | 1.70 | float | Volume fraction above which a bin is HVN |
| `zone_decay_rate` | 0.005 | 0.10 | 0.02 | float | Zone score decay per bar |
| `min_zone_ticks` | 1 | 10 | 2 | int | Minimum zone width in ticks |
| `max_zones` | 5 | 100 | 50 | int | Maximum number of active zones |
| `wall_min_size` | 20 | 200 | 50 | int | Minimum order size to classify as wall |
| `wall_stale_sec` | 30 | 300 | 90 | float | Seconds before wall is pruned as stale |
| `spoof_confidence_threshold` | 0.3 | 0.9 | 0.5 | float | Model confidence below which rule-based fallback applies |
| `glow_threshold` | 50 | 500 | 100 | int | Size threshold for visual glow effect |

---

## Fitness Criteria

These are non-negotiable. A strategy passes only when ALL six criteria are met simultaneously.

| Criterion | Threshold | Notes |
|-----------|-----------|-------|
| IS win rate | >= 55% | In-sample |
| IS avg R:R | >= 1.5:1 | In-sample |
| OOS win rate | >= 55% | Out-of-sample (mandatory) |
| OOS avg R:R | >= 1.5:1 | Out-of-sample (mandatory) |
| IS trade count | >= 30 | Minimum sample size |
| OOS trade count | >= 10 | Prorated to OOS window size |

**Transaction costs included in every P&L calculation:**
- Commission: $4.12 per round trip
- Slippage: $5.00 per round trip
- Total cost per trade: $9.12

OOS validation is mandatory. A strategy that passes IS but fails OOS is rejected. There are no exceptions to this rule.

---

## Mutation Strategy

### When to MUTATE vs GENERATE

```
best_oos_fitness > 0.3  →  MUTATE (something promising exists)
best_oos_fitness <= 0.3  →  GENERATE (nothing worth building on)
iteration_count % 5 == 0  →  RANDOM (exploration burst, regardless of fitness)
```

### MutationType Enum — All Values

| MutationType | When to Use | What It Does |
|--------------|-------------|--------------|
| `TWEAK_PARAMS` | Best strategy has right structure but wrong sizing | Adjusts stop_ticks, target_ticks, max_bars_in_trade by ±30% |
| `SWAP_LEVEL_TARGET` | Strategy works but wrong level type | Swaps LVN/HVN/VPOC/GENUINE_WALL/ICEBERG_WALL/ANY_WALL |
| `ADD_CONFIRMATION` | Strategy has too many false entries | Adds one more confirmation signal (max 3 total) |
| `REMOVE_CONFIRMATION` | Strategy has too few trades (over-filtered) | Removes one confirmation signal |
| `SWAP_EXIT` | Strategy has right entries but wrong exit | Switches between bracket and level exit |
| `CHANGE_TIMING` | Strategy works in some sessions but not others | Changes TimingFilter to a different session window |
| `CROSSOVER` | Two strategies each have partial merit | Combines fields from two parent configs |
| `RANDOM` | Exploration burst, no promising parent | Generates completely random config |

### How to Select Parent for Mutation

Always use the strategy with the highest `best_oos_fitness` from DuckDB:

```bash
python -c "
import duckdb
db = duckdb.connect('data/backtests/discovery_loop.duckdb')
row = db.execute(
    'SELECT hash FROM strategies ORDER BY best_oos_fitness DESC NULLS LAST LIMIT 1'
).fetchone()
print(row[0] if row else 'None')
"
```

### Mutation Type Selection Logic

The `MutationEngine.select_mutation_type()` method biases toward mutation types that have historically produced higher OOS fitness. With fewer than 5 iterations of history, it picks randomly. After 5+ iterations, it weights by average OOS fitness per mutation type.

You don't need to call this directly — `backtest_loop.py --action mutate` handles it. But understanding the bias helps you interpret why certain mutation types appear more often.

---

## Obsidian Write Protocol

After every iteration, write these files. The harness writes them automatically via `backtest_loop.py`. This section documents what gets written so you can verify or manually repair if needed.

### File 1 — Iteration Result (every iteration)

Path: `C:\Users\Tea\Documents\Project\trading-vault\04-backtests\backtest-YYYYMMDD-iter-NNN.md`

```markdown
# Backtest Iteration NNN — YYYY-MM-DD

**Hash:** {hash}
**Action:** generate | mutate | random
**Parent Hash:** {parent_hash or "none"}
**Mutation Type:** {mutation_type or "none"}
**Generation:** {generation}

## Fitness Result

**Status:** PASSED | FAILED

| Metric | In-Sample | Out-of-Sample |
|--------|-----------|---------------|
| Win Rate | {pct}% | {pct}% |
| Avg R:R | {ratio} | {ratio} |
| Trade Count | {n} | {n} |
| OOS Fitness Score | — | {score} |

## Strategy Config

```yaml
{yaml dump of StrategyConfig}
```

## Notes

{NEXT ACTION from harness output}
```

### File 2 — Strategy Hypothesis (new hash only)

Path: `C:\Users\Tea\Documents\Project\trading-vault\02-strategies\strategy-{hash[:8]}.md`

Written only when the hash has not been seen before. Contains the full StrategyConfig YAML and lineage.

### File 3 — Brain Index Append (every iteration)

Path: `C:\Users\Tea\Documents\Project\trading-vault\brain\Backtest-Loop.md`

Append one row to the iteration log table:

```
| NNN | YYYY-MM-DD | {hash[:8]} | {action} | {is_wr}% | {oos_wr}% | {oos_rr} | PASSED/FAILED |
```

Never overwrite or reformat existing rows. Append only.

### File 4 — Finding (PASSED strategies only)

Path: `C:\Users\Tea\Documents\Project\trading-vault\findings\finding-{hash[:8]}-YYYYMMDD.md`

Written only when `FITNESS=PASSED`. Contains full metrics, config, and interpretation of why this strategy works.

---

## Guardrails

These are absolute constraints. Enforce them strictly. No exceptions.

**G1 — Config-only strategies**
Strategies are expressed as `StrategyConfig` objects only. No arbitrary Python code, no lambda functions, no dynamic logic injection. The harness rejects anything that isn't a valid `StrategyConfig`.

**G2 — OOS validation is mandatory**
Never accept a strategy that passes IS but fails OOS. A strategy that hasn't been validated out-of-sample is not a strategy — it's overfitting.

**G3 — Minimum 30 IS trades**
If a strategy produces fewer than 30 in-sample trades, auto-reject regardless of win rate or R:R. Small samples are statistically meaningless.

**G4 — Frozen infrastructure**
`WallClassifier`, `SessionProfile`, and `WallFeatureExtractor` are frozen. Do not modify them. Do not suggest modifying them. They are the data layer, not the strategy layer.

**G5 — Brain notes are read-only (except iteration log)**
Never modify `brain/Memories.md`, `brain/Signals.md`, or any other brain note except `brain/Backtest-Loop.md`. The iteration log in `Backtest-Loop.md` is append-only.

**G6 — Parameters within bounds**
All parameters must stay within `PARAM_BOUNDS`. The harness rejects out-of-range values. If you're constructing a config manually, check bounds before submitting.

**G7 — 50 iteration budget**
Stop at iteration 50. Print a full summary of all iterations, the best strategy found, and ask the user for direction. Do not continue past 50 without explicit user approval.

**G8 — No ML model retraining**
Use the existing `depth_radar_classifier_4class.joblib` model. Do not retrain it, fine-tune it, or replace it during discovery. Model updates are a separate workflow.

---

## Decision Trees

Explicit if-then logic for every situation you'll encounter.

### When FITNESS=PASSED

```
1. Print full metrics to user (IS and OOS win rate, R:R, trade counts, OOS fitness score)
2. Print the strategy config in YAML format
3. Confirm Obsidian finding was written to findings/ directory
4. Ask user: "Continue discovery for more strategies, or stop here?"
5. If continue: proceed to next iteration using MUTATE on this strategy
6. If stop: summarize all iterations and exit
```

### When FITNESS=FAILED, IS trade count < 30

```
1. The strategy is too restrictive — not enough setups triggered
2. Next action: GENERATE with different LevelTarget or remove confirmation signals
3. Consider: REMOVE_CONFIRMATION mutation if parent had signals
4. Consider: SWAP_LEVEL_TARGET to ANY_WALL or LVN (more frequent setups)
5. Do NOT report to user unless iteration % 10 == 0
```

### When FITNESS=FAILED, 30+ IS trades but bad metrics

```
1. Enough setups but wrong parameters or wrong level type
2. Next action: MUTATE with TWEAK_PARAMS or SWAP_EXIT
3. If win rate < 45%: try SWAP_LEVEL_TARGET or ADD_CONFIRMATION
4. If R:R < 1.0: try TWEAK_PARAMS (widen target, tighten stop)
5. If OOS metrics much worse than IS: overfitting — try RANDOM exploration
6. Do NOT report to user unless iteration % 10 == 0
```

### When CHECKPOINT (iteration 50)

```
1. Stop immediately — do not run iteration 51
2. Query DuckDB for all strategies sorted by OOS fitness
3. Print top 5 strategies with full metrics
4. Print total iterations, total PASSED count, best OOS fitness seen
5. Ask user: "Budget exhausted. Extend by 50 more? Or stop and analyze best strategy?"
6. Wait for user response before proceeding
```

### When no preprocessed data exists

```
1. Check: glob.glob('data/preprocessed/session_*.pkl')
2. If empty: run preprocess_mbo.py first (see CLI Commands section)
3. Preprocessing takes 5-15 minutes for one month of MBO data
4. After preprocessing, verify at least one .pkl file exists before running backtest_loop.py
```

### When DuckDB doesn't exist

```
1. This is normal on first run
2. backtest_loop.py creates it automatically
3. Do not try to create it manually
4. Just run the generate action and it will initialize
```

### When backtest_loop.py exits with non-zero code

```
1. Print the full stderr output
2. Check for: ImportError (missing dependency), FileNotFoundError (wrong path), ValueError (invalid config)
3. For ImportError: check that deep6 package is installed (pip install -e .)
4. For FileNotFoundError: verify data paths in Data Paths section
5. For ValueError: the config failed validation — check param bounds
6. Do not retry more than 2 times with the same config
```

---

## Example Iteration

This is iteration 3 of a discovery run. Two iterations have already completed with no passing strategies.

**Context from brain state:**
- iteration_count = 2
- best_hash = "a3f7c2d1..."
- best_oos_fitness = 0.18 (below 0.3 threshold)

**Step 1 — Read brain state**

```bash
python -c "print(open('C:/Users/Tea/Documents/Project/trading-vault/brain/Backtest-Loop.md').read())"
```

Output shows 2 rows in the iteration log. Best OOS fitness is 0.18.

**Step 2 — Query DuckDB**

```bash
python -c "
import duckdb
db = duckdb.connect('data/backtests/discovery_loop.duckdb')
rows = db.execute('SELECT hash, best_oos_fitness, times_tested FROM strategies ORDER BY best_oos_fitness DESC NULLS LAST LIMIT 5').fetchall()
[print(r) for r in rows]
n = db.execute('SELECT COUNT(*) FROM iterations').fetchone()[0]
print(f'Total iterations: {n}')
"
```

Output: 2 strategies, best OOS fitness 0.18, 2 total iterations.

**Step 3 — Decide action**

- iteration_count = 2, not 0 → not first run
- 2 % 5 != 0 → not exploration burst
- best_oos_fitness = 0.18, not > 0.3 → nothing promising
- Decision: `action = "generate"`, `parent_hash = None`

**Step 4 — Run backtest**

```bash
python scripts/backtest_loop.py \
  --db "data/backtests/discovery_loop.duckdb" \
  --data-dir "data/preprocessed/" \
  --vault "C:/Users/Tea/Documents/Project/trading-vault" \
  --action generate
```

**Step 5 — Parse stdout**

```
=== ITERATION 3 COMPLETE ===
HASH: b9e4a1f2c3d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1
FITNESS: FAILED
IS_WIN_RATE: 51.2%
IS_AVG_RR: 1.8
OOS_WIN_RATE: 48.3%
OOS_AVG_RR: 1.6
IS_TRADES: 47
OOS_TRADES: 14
OOS_FITNESS: 0.22
NEXT ACTION: OOS win rate below threshold. Try ADD_CONFIRMATION or SWAP_LEVEL_TARGET.
```

**Step 6 — Act on result**

FITNESS=FAILED, IS trades = 47 (above 30), OOS win rate = 48.3% (below 55%). Do not report to user (iteration 3, not a multiple of 10).

**Step 7 — Write to Obsidian**

Write `04-backtests/backtest-20260523-iter-003.md` with the metrics table.
Write `02-strategies/strategy-b9e4a1f2.md` (new hash, first time seen).
Append row to `brain/Backtest-Loop.md`:
```
| 003 | 2026-05-23 | b9e4a1f2 | generate | 51.2% | 48.3% | 1.6 | FAILED |
```

**Step 8 — Print NEXT ACTION**

```
NEXT ACTION: OOS win rate below threshold. Try ADD_CONFIRMATION or SWAP_LEVEL_TARGET.
```

Iteration 3 complete. OOS fitness = 0.22, still below 0.3. Next iteration will use `generate` again unless fitness improves.

---

## Integration Reference

- Strategy config source: `C:\Users\Tea\DEEP6\deep6\backtest\strategy_config.py`
- Parameter bounds source: `C:\Users\Tea\DEEP6\deep6\backtest\param_bounds.py`
- Mutation engine source: `C:\Users\Tea\DEEP6\deep6\backtest\mutation_engine.py`
- Backtest harness: `C:\Users\Tea\DEEP6\scripts\backtest_loop.py`
- Preprocessor: `C:\Users\Tea\DEEP6\scripts\preprocess_mbo.py`
- DuckDB schema: created automatically by `backtest_loop.py` on first run

---

*Skill frozen at v1.0.0. Discovery agent may only improve iteration quality, not rewrite guardrails.*
