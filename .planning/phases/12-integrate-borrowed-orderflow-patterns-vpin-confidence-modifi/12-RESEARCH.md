# Phase 12: Integrate Borrowed Orderflow Patterns - Research

**Researched:** 2026-04-13
**Domain:** Orderflow signal integration (VPIN, Slingshot, Delta-at-Extreme, setup state machine, walk-forward tracker)
**Confidence:** HIGH (source code reviewed line-by-line; integration points traced through DEEP6 codebase)

## Summary

Five patterns from `~/Downloads/kronos-tv-autotrader/python/` are being borrowed into DEEP6's existing 44-signal engine. The reference implementation is a small (~2.5KLOC), purpose-built TradingView-driven swing engine; **DEEP6 already has equivalents or near-equivalents for two of the five patterns** (Slingshot and Delta-At-Extreme). Direct copy-paste will create naming collisions and signal duplication. The integration must be a **port-with-adaptation**, not a graft.

The right framing is:

| Pattern | DEEP6 status | Action |
|---------|--------------|--------|
| **VPIN** | NOT present | New module — net add |
| **Delta Slingshot (multi-bar trap)** | DEEP6 has `DELT_SLINGSHOT` (different definition: compressed→explosive intra-pattern) | New signal at bit 44, rename or co-exist |
| **Delta At Extreme** | DEEP6 has `DELT_TAIL` ≈ same concept (bar delta at 95% of extreme) | Enhance existing — do NOT add duplicate bit |
| **Setup state machine** | NOT present | New module wrapping the scorer output |
| **Per-regime walk-forward tracker** | Partially present (HMM regime exists, ML attribution exists, walk_forward.py exists) | New module that joins them |

**Primary recommendation:** Integrate in this order — (1) VPIN as a confidence multiplier on the existing scorer (lowest risk, cleanly orthogonal), (2) extend `DeltaEngine` to track running intrabar max/min delta (unlocks proper Delta-At-Extreme + reuses existing `DELT_TAIL` bit), (3) add the multi-bar trapped-trader Slingshot as a NEW signal at bit 44 with a distinct name (`DELT_TRAP_SLINGSHOT` or `TRAP_REVERSAL_SHOT`) because the DEEP6 `DELT_SLINGSHOT` bit-28 definition is materially different and cannot be repurposed (STATE.md locks bit positions 0–43), (4) build the setup state machine on top of `ScorerResult`, (5) wire the walk-forward tracker into the existing `EventStore` from phase 09-01 and the `HMMRegimeDetector` from 09-02.

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for phase 12 yet (this research is being produced ahead of `/gsd-discuss-phase`). Constraints are inferred from project-wide STATE.md and CLAUDE.md:

### Locked Decisions (project-wide)
- **SignalFlags bits 0–43 are STABLE** (STATE.md) — new signals MUST append at bit 44+.
- **NumPy arrays in DOM hot path** (D-01-01) — VPIN/Slingshot run at bar-close, not in the tick hot path, so this is satisfied automatically.
- **`asyncio` single event loop** — new modules must be coroutines or sync code reachable from the bar-close handler; no threads except for ML/inference (already established with `ThreadPoolExecutor`).
- **No mid-bar weight changes** (D-20 from phase 09) — walk-forward tracker can recommend weight changes but cannot mutate them mid-bar.
- **GSD workflow enforced** (CLAUDE.md) — every change goes through `/gsd-execute-phase`.

### Claude's Discretion
- Slingshot signal name and bit assignment (44, 45, or 46).
- Whether VPIN's bucket size adapts to session vs. is fixed.
- State machine persistence (in-memory only, or also to SQLite for crash recovery).
- Whether walk-forward tracker writes to the existing `aiosqlite` event store or a new ClickHouse-style sink.

### Deferred Ideas (OUT OF SCOPE)
- Replacing the existing `DELT_SLINGSHOT` definition (would break serialization).
- Multi-asset support — NQ-only.
- TradingView-integration paths from kronos-tv-autotrader (`tv_signal_renderer.py`, `tv_bridge.py`, `tv_data_feed.py`) — DEEP6 sources from Rithmic, not TV.
- The session-context layer (ICT kill zones from kronos-tv-autotrader's `engine.py` lines 101+) — DEEP6 has its own RTH/IB logic.

## Phase Requirements

Phase 12 has not yet been formalized into REQ-IDs. Provisional mapping for the planner:

| ID (proposed) | Description | Research Support |
|---------------|-------------|------------------|
| OFP-01 | VPIN engine producing flow-toxicity percentile + confidence multiplier (0.3×–1.15×) per bar close | `vpin.py` lines 39–240, complete reference implementation |
| OFP-02 | Multi-bar trapped-trader Slingshot detector (2/3/4-bar variants) at new SignalFlags bit ≥44 | `orderflow_tv.py` lines 269–378, `_detect_slingshot()` |
| OFP-03 | Intrabar delta accumulator (running max+/min−) attached to `FootprintBar` | NEW — DEEP6 has no intrabar delta state today |
| OFP-04 | Enhance `DeltaEngine.DELT_TAIL` (bit 22) to use true intrabar extreme from OFP-03; add `delta_at_extreme` quality bias to scorer | DEEP6's `DELT_TAIL` is already the right concept; `orderflow_tv.py` lines 383–457 supply the bias-shape logic |
| OFP-05 | `SetupTracker` state machine: SCANNING → DEVELOPING → TRIGGERED → MANAGING → COOLDOWN with persistence bonus | `setup_tracker.py` lines 29–275, complete reference |
| OFP-06 | `PerformanceTracker` per-regime walk-forward outcome ledger at 5/10/20-bar horizons; auto-disable layer when rolling Sharpe < threshold | `performance_tracker.py` lines 57–345, complete reference |
| OFP-07 | VPIN confidence multiplier wired into `scoring/scorer.py` as a final stage (after category/zone/IB multipliers); never modifies direction | `orderflow_tv.py` lines 222–235 shows the wiring |
| OFP-08 | Slingshot, when fired with confidence > threshold, can short-circuit `SetupTracker` from SCANNING/DEVELOPING straight to TRIGGERED | `setup_tracker.py` lines 80–98 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 1.26+ (already pinned) | VPIN sigma estimation, percentile, slingshot threshold | [VERIFIED: existing in `pyproject.toml`] Stdlib for vector ops; reference impl uses it |
| pandas | already pinned | Walk-forward tracker DataFrames, optional bar wrapping | [VERIFIED: existing] Reference uses `pd.DataFrame` for tail/historical access |
| math (stdlib) | — | `math.erf` for normal CDF in BVC | [VERIFIED: stdlib] Reference impl `vpin.py:185` uses `math.erf` |
| dataclasses (stdlib) | — | `ActiveSetup`, `SignalRecord` | [VERIFIED: stdlib] Used by both `setup_tracker.py` and `performance_tracker.py` |
| collections.deque | — | VPIN imbalance/return ring buffers, signal history | [VERIFIED: stdlib] Used everywhere in reference |
| aiosqlite | already pinned (phase 01 + 09) | Walk-forward tracker persistence (reuse `EventStore`) | [VERIFIED: in use] Avoid introducing ClickHouse for a phase-12 add |

### Supporting (no new installs required)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | already pinned | Replace reference `logging.getLogger()` calls to match DEEP6 convention | All new modules |
| hmmlearn | 0.3.3 (phase 09-02) | Existing regime detector — walk-forward tracker reads its output | Per-regime metric slicing |
| lightgbm | 4.6.0 (phase 09-02) | Existing meta-learner — walk-forward tracker feeds it outcomes | Re-training input |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| BVC (Bulk Volume Classification) for VPIN | True bid/ask aggressor split (DEEP6 has it from DATA-02) | DEEP6 already knows aggressor side per trade — could compute exact V_buy/V_sell instead of probabilistic BVC. **Recommendation: use exact aggressor split in DEEP6's port.** It is strictly more accurate than BVC and free given existing infrastructure. BVC is a workaround for systems that lack aggressor data; DEEP6 does not need it. [ASSUMED: This is a logical improvement not present in the reference impl] |
| In-memory `SetupTracker` only | Persist state to SQLite | In-memory is fine if state is rebuilt from `signal_events` on restart; SQLite persistence adds complexity. Recommend in-memory for plan 1, defer persistence. |
| Custom `PerformanceTracker` JSON file (reference) | Reuse phase 09-01 `EventStore` (`signal_events` + `trade_events` tables) | EventStore already exists, already handles serialization, already async. **Strong recommendation: reuse EventStore, do NOT add a JSON-on-disk sink.** |

**Installation:**
No new pip installs required. All dependencies are already locked from phases 01, 02, 09.

**Version verification:** All five new modules use only libraries that are already in `pyproject.toml` and proven by phases 01–09. No `npm view` / `pip index versions` step needed for this phase.

## Architecture Patterns

### Recommended Module Structure
```
deep6/
├── orderflow/                  # NEW package
│   ├── __init__.py
│   ├── vpin.py                 # OFP-01: VPINEngine — port of vpin.py
│   ├── slingshot.py            # OFP-02: multi-bar trap detector
│   ├── intrabar_delta.py       # OFP-03: running max/min delta accumulator
│   ├── delta_at_extreme.py     # OFP-04: bias-shape logic
│   ├── setup_tracker.py        # OFP-05: state machine
│   └── walk_forward_live.py    # OFP-06: per-regime performance tracker
├── state/
│   └── footprint.py            # MODIFIED: add intrabar_max_delta / intrabar_min_delta fields
├── signals/
│   └── flags.py                # MODIFIED: append bit 44 (e.g., DELT_TRAP_SLINGSHOT)
├── engines/
│   └── delta.py                # MODIFIED: enhance DELT_TAIL using intrabar extreme
└── scoring/
    └── scorer.py               # MODIFIED: apply VPIN confidence multiplier
```

### Pattern 1: VPIN as a Final-Stage Confidence Multiplier
**What:** VPIN does not change `direction` or category counts; it only multiplies the final `confidence` (or `total_score`) emitted by `score_bar()`.
**When to use:** Always at end of `score_bar()`, after IB multiplier, before returning `ScorerResult`.
**Why this layering:** Keeps VPIN orthogonal to the existing 44-signal voting and to the LightGBM meta-learner. The meta-learner training set continues to use unmodulated signal flags; VPIN modulates the deployed score downstream. This means the meta-learner does not have to be retrained when VPIN parameters change.

```python
# Source: orderflow_tv.py:222-235 (reference pattern)
# Apply VPIN modifier — toxic tape = lower confidence
raw_confidence = abs(composite) * 0.5 + agreement * 0.5
confidence = float(np.clip(raw_confidence * vpin_conf_mod, 0, 1))
# DEEP6 port: do this in scorer.py after total_score is finalized
total_score *= vpin_engine.get_confidence_modifier()
```

### Pattern 2: Volume-Clock Update (VPIN Bucket Filling)
**What:** VPIN uses VOLUME time, not clock time. Each bar may complete 0, 1, or N buckets depending on volume.
**When to use:** Call `vpin.update(bar.close, bar.total_vol)` once per bar close. The engine internally splits the bar's volume across buckets and completes any that fill.
**Example:**
```python
# Source: vpin.py:77-111 (canonical implementation)
def update(self, price: float, volume: float, bar_close: float = None) -> Dict:
    remaining = volume
    while remaining > 0:
        space = self.bucket_volume - self._bucket_vol_accum
        if remaining >= space:
            fill = space
            self._fill_bucket(bar_close, fill)
            self._complete_bucket()
            remaining -= fill
        else:
            self._fill_bucket(bar_close, remaining)
            remaining = 0
```

### Pattern 3: Slingshot Bypass of Setup-Machine Development
**What:** When a Slingshot fires, the setup machine jumps straight from SCANNING/DEVELOPING to TRIGGERED — no minimum development bars required.
**When to use:** Inside `SetupTracker.update()`, BEFORE the normal state-machine dispatch.
**Example:**
```python
# Source: setup_tracker.py:80-98
slingshot = orderflow.get("signals", {}).get("delta_slingshot", {})
if isinstance(slingshot, dict) and slingshot.get("detected") \
        and self.state in ("SCANNING", "DEVELOPING"):
    # Slingshot is an IMMEDIATE trigger
    self.setup = ActiveSetup(setup_type=f"SLINGSHOT_{slingshot.get('variant', 2)}BAR", ...)
    self.state = "TRIGGERED"
```

### Pattern 4: Walk-Forward Outcome Resolution by Bar-Index Lag
**What:** Each recorded signal carries an `entry_bar_index`. After N more bars accumulate in the price ring buffer, the tracker resolves the outcome by reading `price_history[entry_bar_index + N]`.
**When to use:** Call `tracker.update_price(close)` once per bar close after `tracker.record_signal(...)`. It self-resolves all pending signals whose horizon has elapsed.
**Example:**
```python
# Source: performance_tracker.py:143-194 (canonical implementation)
def _resolve_pending_outcomes(self):
    current_bar = len(self.price_history)
    for pending in self.pending_outcomes:
        bars_elapsed = current_bar - pending["entry_bar"]
        for horizon in self.outcome_bars:    # [5, 10, 20]
            if bars_elapsed >= horizon:
                outcome_price = self.price_history[pending["entry_bar"] + horizon]
                # ... compute pnl, mark CORRECT/INCORRECT, store on record
```

### Anti-Patterns to Avoid
- **Reusing `DELT_SLINGSHOT` (bit 28) for the new multi-bar trap pattern.** DEEP6's existing definition (compressed-then-explosive intra-pattern, `delta.py:216-232`) is materially different. Reusing the bit silently corrupts every backtest report and meta-learner feature label.
- **Adding a parallel `delta_at_extreme` signal flag.** DEEP6 already has `DELT_TAIL` (bit 22) which is the same concept. Enhance the existing signal; don't duplicate.
- **Threading the VPIN engine.** It's O(1) per bar with negligible CPU. It runs synchronously in the bar-close handler.
- **Hand-rolling normal CDF.** Use `math.erf` (stdlib). Do not pull in scipy just for `scipy.stats.norm.cdf`.
- **Persisting walk-forward tracker as JSON file.** Phase 09-01 already has the `EventStore` with `signal_events` and `trade_events` tables. The tracker is a query-and-aggregate over those, not a new sink.
- **Letting the setup state machine block the asyncio event loop.** All transitions are O(1); no I/O. But avoid any `await asyncio.sleep` inside the machine — drive timing from bar-close events only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Normal CDF for BVC z-score | Lookup table or polynomial approximation | `math.erf` (stdlib) | One-line, exact, identical to reference impl |
| Rolling percentile for VPIN history | Sort-on-every-call | `bisect.insort` into a sorted deque OR `numpy.percentile` on the deque (reference does the latter — fine at N=2000) | At history_size=2000, `np.percentile` is ~30µs — non-issue at 1-bar cadence |
| Per-regime metric aggregation | Custom dict-of-dict-of-list | Pandas `groupby('regime').agg(...)` over `signal_events` table | EventStore is already there; pandas slicing is one line |
| Outcome lag resolution | Datetime arithmetic | Bar-index integer arithmetic (reference uses `len(self.price_history)` as the bar clock) | Bar-index avoids DST/holiday/early-close edge cases entirely |
| Linear regression for CVD slope | Custom least-squares | `numpy.polyfit(x, y, 1)` | Already used in `delta.py` for DELT-10 — be consistent |

**Key insight:** All five borrowed modules have working reference implementations totaling ~1.3KLOC. The win is **port + adapt to DEEP6 conventions** (structlog, dataclasses for config, EventStore for persistence). Almost no novel design is required.

## Runtime State Inventory

This is an **integration / additive** phase, not a rename or migration. Most categories are not applicable.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no existing VPIN/Slingshot/SetupTracker state in any database | None (greenfield additions) |
| Live service config | None — no n8n/Datadog/external services touched | None |
| OS-registered state | None — no Windows tasks, launchd, systemd entries reference these patterns | None |
| Secrets/env vars | None — no API keys introduced (FlashAlpha is out-of-scope; reuse existing keys if any) | None |
| Build artifacts | `deep6.egg-info/` already exists; will refresh on next install but no rename involved | None |

**Caveat — bit-position serialization:** If any pickled/JSON-serialized signal records exist in the repo (e.g., `backtest_apr10.csv` referencing flag bitmasks as integers), adding bit 44 is forward-compatible (existing records have bit 44 = 0). No data migration needed. **VERIFIED:** STATE.md explicitly lists "SignalFlags bit positions 0-43 are STABLE — do not reorder (serialization safety)" — appending at 44 is the documented escape hatch.

## Common Pitfalls

### Pitfall 1: BVC Sigma Underflow on Low-Volume Bars
**What goes wrong:** `_estimate_sigma()` returns `0.001` when the return history is short (< 10 buckets), so the z-score `dp / sigma` blows up and `buy_pct` saturates at 0 or 1. Early-session VPIN values are then meaningless.
**Why it happens:** VPIN needs ~10 buckets of history before sigma stabilizes.
**How to avoid:** Treat the first ~10 bucket completions as warmup. Set `vpin_engine.get_confidence_modifier() = 1.0` (neutral) until `buckets_completed >= 10`. Reference impl already returns `0.5` percentile until 20 buckets exist (`vpin.py:189`) — copy that gate into the confidence modifier as well.
**Warning signs:** Confidence multiplier oscillating between 0.3 and 1.15 in the first 30 minutes of session.

### Pitfall 2: Slingshot Threshold Drift Between Sessions
**What goes wrong:** The reference impl computes `threshold = avg_abs_delta * 1.5` over the last 50 bars. After an overnight session break, the moving average is stale; first-session-bar Slingshots fire on noise.
**Why it happens:** DEEP6 resets session-CVD at RTH start (already implemented in `delta.py:reset()`), but the rolling delta history is 500 bars deep (`orderflow_tv.py:79`) — spans sessions.
**How to avoid:** Reset `slingshot.delta_history` and `slingshot.bar_cache` on `session_reset()`. Add a minimum-bars gate: do not fire Slingshot until `len(delta_history) >= 30`.
**Warning signs:** Slingshot signals at 9:31 ET on every session.

### Pitfall 3: Walk-Forward Outcome Mis-Attribution Across Sessions
**What goes wrong:** A signal recorded at 15:55 ET has its 20-bar outcome resolve at the next session's 9:50 ET (20 bars later in the price ring buffer), measured against a price after an overnight gap. PnL is dominated by overnight macro, not the signal.
**Why it happens:** `performance_tracker.py:143-194` uses bar-index lag without session boundaries.
**How to avoid:** Enforce a session boundary in resolution — if `current_bar` is in a new RTH session vs. `entry_bar`, mark outcome as `EXPIRED` (not CORRECT/INCORRECT) and exclude from rolling Sharpe. Add `session_id` to `SignalRecord`.
**Warning signs:** Sharpe collapses nightly; rolling Sharpe whipsaws between sessions.

### Pitfall 4: Setup State Machine "Stuck in MANAGING"
**What goes wrong:** Reference auto-transitions MANAGING → COOLDOWN after 1 cycle (`setup_tracker.py:240-248`) — clearly a placeholder. In DEEP6 with real position tracking, the transition needs to wait for an actual fill/exit event.
**Why it happens:** The reference engine had no execution layer wired in.
**How to avoid:** Wire `MANAGING → COOLDOWN` to the existing `PaperTrader` (or live `RithmicExecutor`) trade-close event. Until then, time-out at `bars_managing > 30` to prevent permanent stuck state.
**Warning signs:** State machine reports MANAGING for hours; new setups never initiate.

### Pitfall 5: VPIN Multiplier × Existing IB Multiplier Compound Stacking
**What goes wrong:** The scorer already applies an IB multiplier (1.15× during first 60 bars, per `scoring/scorer.py` comments). Adding a VPIN multiplier on top can produce final scores > 100 or < 0, breaking `ScorerTier` thresholds (TYPE_A ≥ 80).
**Why it happens:** Multipliers compose multiplicatively; reference impl was a standalone confidence in [0,1], not a 0-100 score.
**How to avoid:** Apply VPIN multiplier and then `clip(0, 100)`. Document in `ScorerConfig` that multipliers are evaluated in fixed order: base → category → zone → IB → VPIN → clip.
**Warning signs:** TYPE_A frequency drops to zero in CLEAN VPIN regimes (because 1.15 × 1.15 × ... saturates), or to 99% in TOXIC (because clipping floors all scores).

### Pitfall 6: Naming Collision Between Existing `DELT_SLINGSHOT` and Borrowed Multi-Bar Slingshot
**What goes wrong:** Two things named "slingshot" with different math. Code reviewers, backtest reports, ML feature importance dumps will conflate them. Quoted "72-78% win rate" in `delta.py:216` does not apply to the new pattern.
**Why it happens:** Same word, different industry usage. Reference impl's "slingshot" is the multi-bar trapped-trader reversal; DEEP6's existing "slingshot" is the intra-pattern compressed-then-explosive variant from prior research.
**How to avoid:** Name the new bit unambiguously: **`TRAP_SHOT`** (bit 44, in TRAP category) is the cleanest — it semantically belongs in the Trapped Traders group anyway since it is a trapped-trader reversal pattern. Alternatively: `DELT_REV_SLINGSHOT` to keep it in the DELT family. **Do NOT name it `DELT_SLINGSHOT_2` or `SLINGSHOT_NEW`.**
**Warning signs:** PR review comments asking "which slingshot?"; meta-learner feature importance plots showing both.

## Code Examples

### Verified Pattern: VPIN BVC z-score → buy probability
```python
# Source: vpin.py:113-138
def _fill_bucket(self, price: float, volume: float):
    if self._bucket_vol_accum == 0:
        self._bucket_price_start = price
    self._bucket_price_end = price
    self._bucket_vol_accum += volume

    if self._bucket_price_start > 0:
        dp = price - self._bucket_price_start
        sigma = self._estimate_sigma()
        if sigma > 0:
            z = dp / sigma
            buy_pct = self._norm_cdf(z)   # = 0.5 * (1 + math.erf(z / sqrt(2)))
        else:
            buy_pct = 0.5
        self._bucket_buy_accum += volume * buy_pct
        self._bucket_sell_accum += volume * (1 - buy_pct)
```

**DEEP6 adaptation:** Replace BVC with exact aggressor split:
```python
# Proposed DEEP6 enhancement (NOT in reference impl)
def update_from_bar(self, bar: FootprintBar):
    """Use exact aggressor split from FootprintBar levels — no BVC needed."""
    buy_vol  = sum(lv.ask_vol for lv in bar.levels.values())   # aggressor=BUY
    sell_vol = sum(lv.bid_vol for lv in bar.levels.values())   # aggressor=SELL
    self._bucket_buy_accum  += buy_vol
    self._bucket_sell_accum += sell_vol
    self._bucket_vol_accum  += buy_vol + sell_vol
    if self._bucket_vol_accum >= self.bucket_volume:
        self._complete_bucket()
```

### Verified Pattern: 2-Bar Bullish Slingshot
```python
# Source: orderflow_tv.py:296-307
b2 = bars[-2]; b1 = bars[-1]
if (b2["close"] < b2["open"] and          # Bar -2 bearish
    b2["delta"] < -threshold and            # Extreme negative delta
    b1["close"] > b1["open"] and            # Bar -1 bullish
    b1["close"] > b2["high"] and            # Closes above bar -2 high
    b1["delta"] > threshold):               # Extreme positive delta
    strength = min(abs(b1["delta"]) / max(abs(b2["delta"]), 1), 3.0)
    return {"detected": True, "type": "BULL_SLINGSHOT", "variant": 2,
            "bias": min(0.6 * strength / 2, 1.0), "strength": round(strength, 2)}
```
Threshold definition: `threshold = avg_abs_delta * 1.5`, where `avg_abs_delta = np.mean(np.abs(self.delta_history[-50:]))` (`orderflow_tv.py:290`).

### Verified Pattern: Delta-At-Extreme Bias (no intrabar data)
```python
# Source: orderflow_tv.py:395-457 — proxy version using bar geometry
body_ratio    = abs(b["close"] - b["open"]) / rng         # 1.0 = full body
close_pct     = (b["close"] - b["low"]) / rng              # 1.0 = closed at high
delta_ratio   = abs(bar_delta) / max(b["volume"], 1)       # 1.0 = fully one-sided

if bar_delta > 0:    # Bullish bar
    extreme_pct = close_pct * 0.4 + body_ratio * 0.3 + delta_ratio * 0.3
elif bar_delta < 0:  # Bearish bar
    extreme_pct = (1 - close_pct) * 0.4 + body_ratio * 0.3 + delta_ratio * 0.3

at_extreme = extreme_pct >= 0.75   # confidence 1.15× equivalent
weak       = extreme_pct < 0.35    # confidence 0.7× equivalent
```
**DEEP6 enhancement:** Once `intrabar_max_delta` / `intrabar_min_delta` are tracked on `FootprintBar`, replace the proxy:
```python
# Proposed DEEP6 enhancement using true intrabar extreme
intrabar_max = bar.intrabar_max_delta
intrabar_min = bar.intrabar_min_delta
final_delta  = bar.bar_delta
if final_delta > 0 and intrabar_max > 0:
    extreme_pct = final_delta / intrabar_max         # 1.0 = closing AT max
elif final_delta < 0 and intrabar_min < 0:
    extreme_pct = final_delta / intrabar_min         # 1.0 = closing AT min
else:
    extreme_pct = 0.5
```
This is what `DELT_TAIL` (bit 22) is supposed to compute (`flags.py:73` — "delta closes at 95%+ of its extreme") but currently approximates because intrabar state was never added. **Fix `DELT_TAIL` properly while doing this work.**

### Verified Pattern: Outcome Resolution
```python
# Source: performance_tracker.py:148-186
for pending in self.pending_outcomes:
    bars_elapsed = len(self.price_history) - pending["entry_bar"]
    for horizon in [5, 10, 20]:
        if bars_elapsed >= horizon:
            outcome_price = self.price_history[pending["entry_bar"] + horizon]
            pnl = outcome_price - pending["entry_price"]
            if pending["record"].direction == "SHORT":
                pnl = -pnl
            correct = (pending["record"].direction == "LONG" and outcome_price > pending["entry_price"]) \
                   or (pending["record"].direction == "SHORT" and outcome_price < pending["entry_price"])
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| VPIN with time-bucketed CDF (Easley 2008 paper) | VPIN with volume-clock buckets + BVC (Easley/López de Prado/O'Hara 2011/2012) | 2011 paper | Volume-clock is canonical; reference impl uses this |
| Manual confidence scaling per signal | Centralized "flow toxicity" multiplier | Reference impl 2024+ | Cleaner separation: signals stay binary, sizing stays a multiplier |
| JSON-on-disk performance log | Async EventStore (DEEP6's phase 09-01 pattern) | DEEP6-specific | Avoids race conditions and missed writes on crash |
| Bar-level delta approximation for "at extreme" | True intrabar running max/min delta | DEEP6-specific upgrade | Unblocks `DELT_TAIL` (bit 22) which has been approximating since phase 03 |

**Deprecated/outdated:**
- BVC normal-CDF when exact aggressor side is available (DEEP6 case): use the exact split.
- Per-signal threshold tuning by hand: deferred to LightGBM weight file (already in phase 09-02).

**Authoritative references for the patterns:**
- **VPIN paper:** Easley, López de Prado, O'Hara (2011) "The Volume Clock: Insights into the High Frequency Paradigm" — `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1695596` [CITED: paper title in user prompt + Wikipedia VPIN page]
- **VPIN Journal of Portfolio Management version:** Easley, López de Prado, O'Hara (2012) "Flow Toxicity and Liquidity in a High Frequency World" Review of Financial Studies — [ASSUMED]
- No canonical literature for the multi-bar Trap Slingshot or the SCANNING/DEVELOPING/TRIGGERED state machine — these are practitioner patterns. Reference impl is the de facto spec.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Bucket size 1000 contracts × 50 buckets is appropriate for NQ 1-min (gives ~50–100 buckets/session) | Standard Stack / Pattern 2 | LOW — `vpin.py` docstring explicitly suggests 500–2000 for NQ; refine in plan with one-day measurement |
| A2 | DEEP6 should use exact aggressor split instead of BVC | Standard Stack — Alternatives | LOW — strictly more accurate; only risk is loss of academic comparability |
| A3 | New TRAP_SHOT signal belongs in TRAP category at bit 44 | Phase Requirements OFP-02 | LOW — semantically a trapped-trader pattern; bit 44 is first free slot |
| A4 | Walk-forward tracker should reuse `EventStore` not write JSON files | Standard Stack — Alternatives | LOW — strictly better hygiene; reference impl's JSON sink is a portability workaround |
| A5 | Apply VPIN multiplier AFTER all other scorer multipliers (final stage) | Pattern 1 / Pitfall 5 | MEDIUM — alternative ordering changes calibration; needs A/B with backtest before locking |
| A6 | Slingshot delta_history should reset at session boundary | Pitfall 2 | MEDIUM — affects first-30-min behavior; needs explicit policy decision |
| A7 | Walk-forward outcomes spanning session boundaries should be marked EXPIRED, not INCORRECT | Pitfall 3 | MEDIUM — biases reported Sharpe; needs explicit policy decision |
| A8 | "Slingshot bypass" should require Slingshot strength ≥ some threshold (not just `detected: True`) | Pattern 3 | LOW — reference impl uses any detection; tighten with backtest data |
| A9 | Easley 2012 RFS paper exists and is the canonical academic reference | State of the Art | LOW — well-known paper; only minor citation risk |
| A10 | Bit 44 is currently free (no other phase has reserved it) | Pitfall 6 / OFP-02 | LOW — VERIFIED by reading `flags.py` (highest bit is 43); STATE.md confirms 0–43 stable |

**A1, A6, A7, A8 require user confirmation in `/gsd-discuss-phase`** before locking into PLAN.md.

## Open Questions

1. **Should `intrabar_max_delta` tracking go in `FootprintBar.add_trade()` or in a separate `IntrabarDeltaAccumulator`?**
   - What we know: `add_trade` is in the hot path (1000 callbacks/sec). Adding two int comparisons + assignments per trade is cheap (~50 ns).
   - What's unclear: Whether DEEP6's hot-path budget is already saturated.
   - Recommendation: Inline into `add_trade` — it's two operations (`running_delta += sign*size; max_delta = max(max_delta, running_delta); min_delta = min(min_delta, running_delta)`). Profile in plan verification step.

2. **Should the `SetupTracker` be 1m-only or also run on 5m bars?**
   - What we know: DEEP6 has both 1m and 5m bar builders.
   - What's unclear: Reference impl is 1m-only.
   - Recommendation: 1m-only for plan 1; defer 5m to a follow-on plan.

3. **Walk-forward auto-disable: per-layer or per-signal?**
   - What we know: Reference disables at the layer level (orderflow / kronos / gex). DEEP6 has 8 categories × 44 signals — much finer granularity.
   - What's unclear: Whether per-signal disable would be too aggressive (single-signal sample sizes too small).
   - Recommendation: Per-category (8 buckets) for plan 1 — matches DEEP6's existing weight file structure (phase 09-02 `WeightFile.weights` is keyed by category). Defer per-signal.

4. **VPIN bucket size: fixed or session-adaptive?**
   - What we know: Reference uses fixed 1000.
   - What's unclear: NQ session volume varies 3–5× between FOMC days and quiet summer Mondays.
   - Recommendation: Fixed for plan 1. Adaptive sizing is a phase-13 enhancement.

5. **Where does the `flow_regime` (CLEAN/NORMAL/ELEVATED/TOXIC) get exposed?**
   - What we know: Scorer gets the multiplier. The HMM regime detector is separate.
   - What's unclear: Whether the LightGBM meta-learner should receive `flow_regime` as a feature (would make it bit 47 of the 47-feature vector).
   - Recommendation: Add `flow_regime` to one of the reserved feature slots (e.g., `reserved_44 = vpin_percentile`). This is a phase-12 win since 09-02 already left those slots open.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| numpy | All five modules | ✓ | already pinned | — |
| pandas | Walk-forward tracker | ✓ | already pinned | — |
| math.erf (stdlib) | VPIN BVC | ✓ | Python 3.12 | — |
| dataclasses (stdlib) | SetupTracker, SignalRecord | ✓ | Python 3.12 | — |
| collections.deque (stdlib) | All ring buffers | ✓ | Python 3.12 | — |
| aiosqlite | EventStore reuse | ✓ | already pinned (phase 09-01) | — |
| structlog | Logging convention | ✓ | already pinned | — |
| hmmlearn | Per-regime slicing | ✓ | 0.3.3 (phase 09-02) | — |
| lightgbm | Walk-forward → meta-learner feedback | ✓ | 4.6.0 (phase 09-02) | — |

**No missing dependencies.** All five modules can be implemented with the existing toolchain. No `pip install` step required for plan execution.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (already in use across phases 01–09) |
| Config file | `pyproject.toml` (pytest section) — verify in Wave 0 |
| Quick run command | `pytest tests/orderflow/ -x -q` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OFP-01 | VPIN engine returns increasing percentile as imbalance increases | unit | `pytest tests/orderflow/test_vpin.py::test_percentile_grows_with_imbalance -x` | ❌ Wave 0 |
| OFP-01 | VPIN confidence modifier in [0.3, 1.15] | unit | `pytest tests/orderflow/test_vpin.py::test_confidence_modifier_bounded -x` | ❌ Wave 0 |
| OFP-02 | 2-bar bullish slingshot fires on synthetic input matching template | unit | `pytest tests/orderflow/test_slingshot.py::test_2bar_bull -x` | ❌ Wave 0 |
| OFP-02 | Slingshot does not fire when delta below threshold | unit | `pytest tests/orderflow/test_slingshot.py::test_no_fire_below_threshold -x` | ❌ Wave 0 |
| OFP-03 | `intrabar_max_delta` updates monotonically over a sequence of buy ticks | unit | `pytest tests/state/test_footprint_intrabar.py::test_max_delta_monotonic -x` | ❌ Wave 0 |
| OFP-04 | `DELT_TAIL` fires when bar.bar_delta == bar.intrabar_max_delta | unit | `pytest tests/engines/test_delta.py::test_tail_uses_intrabar -x` | partial (existing test file may need update) |
| OFP-05 | SCANNING → DEVELOPING on aligned signal with conf > 0.35 | unit | `pytest tests/orderflow/test_setup_tracker.py::test_scanning_to_developing -x` | ❌ Wave 0 |
| OFP-05 | Slingshot bypass: SCANNING → TRIGGERED in one update | unit | `pytest tests/orderflow/test_setup_tracker.py::test_slingshot_bypass -x` | ❌ Wave 0 |
| OFP-06 | Walk-forward tracker resolves 5-bar outcome correctly on synthetic price stream | unit | `pytest tests/orderflow/test_walk_forward_live.py::test_5bar_resolution -x` | ❌ Wave 0 |
| OFP-06 | Auto-disable triggers when rolling Sharpe < min_sharpe over ≥30 resolved signals | unit | `pytest tests/orderflow/test_walk_forward_live.py::test_auto_disable -x` | ❌ Wave 0 |
| OFP-07 | Scorer applies VPIN multiplier as final stage; clipped to [0, 100] | integration | `pytest tests/scoring/test_scorer_with_vpin.py -x` | ❌ Wave 0 |
| OFP-08 | End-to-end: synthetic bar stream → VPIN + Slingshot + SetupTracker → ScorerResult | integration | `pytest tests/integration/test_phase12_end_to_end.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/orderflow/ -x -q` (~5–10 sec — pure unit tests on synthetic data)
- **Per wave merge:** `pytest tests/ -x` (full suite — currently ~30s based on existing phases)
- **Phase gate:** Full suite green + integration test on 1 day of recorded NQ ticks (use `footprint_databento_validation.csv` if format compatible) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/orderflow/__init__.py` — new test directory
- [ ] `tests/orderflow/test_vpin.py` — covers OFP-01
- [ ] `tests/orderflow/test_slingshot.py` — covers OFP-02
- [ ] `tests/orderflow/test_setup_tracker.py` — covers OFP-05
- [ ] `tests/orderflow/test_walk_forward_live.py` — covers OFP-06
- [ ] `tests/state/test_footprint_intrabar.py` — covers OFP-03
- [ ] `tests/scoring/test_scorer_with_vpin.py` — covers OFP-07
- [ ] `tests/integration/test_phase12_end_to_end.py` — covers OFP-08
- [ ] `tests/conftest.py` — add fixtures: `synthetic_bar_stream`, `slingshot_template_bars`, `vpin_warmup_data`

No framework install needed; pytest already in use.

## Security Domain

`security_enforcement` not explicitly set in `.planning/config.json` (verified by `init` output: only `commit_docs`, `brave_search`, `firecrawl`, `exa_search` keys present). Treating as enabled per default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | (no auth surface introduced) |
| V3 Session Management | no | (no sessions introduced) |
| V4 Access Control | no | (no new endpoints; uses existing FastAPI from phase 09 if any) |
| V5 Input Validation | yes | All bar inputs flow through existing `FootprintBar` validation; no new external input surface |
| V6 Cryptography | no | No crypto operations |

### Known Threat Patterns for Python Async Trading System

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed bar data crashing scorer | Denial of Service | Defensive `try/except` in `SetupTracker.update()` and `VPINEngine.update()`; reference impl already returns neutral state on bad input (`vpin.py:90`) |
| Walk-forward tracker memory leak from unbounded `pending_outcomes` | Denial of Service | Cap list at `max_pending = 1000`; expire stale entries after `max_horizon * 5` bars |
| Auto-disable flag flipped maliciously via tampered tracker file | Tampering | Tracker state should NOT be loadable from external file; always recompute from `EventStore` on startup |
| State machine wedged in `MANAGING` indefinitely | Denial of Service | Time-out at `bars_managing > 30` (see Pitfall 4) |

## Sources

### Primary (HIGH confidence)
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/vpin.py` — full VPIN reference impl (240 lines, read in entirety)
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/setup_tracker.py` — full state machine (275 lines, read in entirety)
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/orderflow_tv.py` — Slingshot + Delta-At-Extreme + integration pattern (506 lines, read in entirety)
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/performance_tracker.py` — walk-forward tracker (345 lines, read in entirety)
- `/Users/teaceo/Downloads/kronos-tv-autotrader/python/engine.py` — top-level integration pattern (lines 1–120 read; rest is wiring)
- `/Users/teaceo/DEEP6/deep6/signals/flags.py` — confirms bit 28 = `DELT_SLINGSHOT` (existing, different definition); bit 22 = `DELT_TAIL`; bit 43 = highest used
- `/Users/teaceo/DEEP6/deep6/state/footprint.py` — confirms NO intrabar delta tracking exists today
- `/Users/teaceo/DEEP6/deep6/engines/delta.py` — confirms existing `DELT_SLINGSHOT` definition (compressed→explosive intra-pattern, lines 216-232)
- `/Users/teaceo/DEEP6/deep6/scoring/scorer.py` — confirms current multiplier ordering (base × category × zone × IB)
- `/Users/teaceo/DEEP6/deep6/state/shared.py` — confirms `on_bar_close` dispatch pattern; new modules attach via `_on_bar_close_fn`
- `/Users/teaceo/DEEP6/.planning/STATE.md` — confirms "SignalFlags bit positions 0-43 are STABLE"
- `/Users/teaceo/DEEP6/.planning/phases/09-ml-backend/09-02-SUMMARY.md` — confirms `WeightFile` schema with category-level weights and `regime_adjustments` slot ready for walk-forward output
- `/Users/teaceo/DEEP6/.planning/phases/09-ml-backend/09-CONTEXT.md` — confirms D-22/D-23 (per-signal + per-regime metrics) is the canonical performance-tracking decision

### Secondary (MEDIUM confidence)
- VPIN paper (Easley/López de Prado/O'Hara 2011) — referenced by user prompt, content known from training; specific bucket-size guidance for NQ in reference impl docstring is the practical authority

### Tertiary (LOW confidence)
- None — every claim in this research is either (a) read from source code in this session, or (b) from DEEP6 codebase verified in this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every dependency already pinned and proven by phases 01–09
- Architecture: HIGH — integration points traced through `SharedState`, `on_bar_close`, `ScorerResult`, `SignalFlags`
- Pitfalls: HIGH — reference impl had visible footguns (placeholder MANAGING transition, threshold drift) verified from the source
- Naming/bit-position collision risk: HIGH (well-identified, documented mitigation)
- VPIN parameter values for NQ: MEDIUM (need 1-day live measurement to confirm 1000-contract bucket is sized correctly)
- Walk-forward session-boundary policy: MEDIUM (requires user decision in `/gsd-discuss-phase`)

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (30 days — reference code is static; DEEP6 phases 10-11 in flight may add adjacent surfaces)
